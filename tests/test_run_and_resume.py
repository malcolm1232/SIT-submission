"""run_review / resume_run end to end (workstream C, "phase 3"), offline.

Covers what the removed tests/test_pending.py's phase-3 entries ``test_resume_reuses_completed_tool_calls``
and (with test_ingest_verify_report.py) ``test_verify_and_report_produce_valid_review`` describe:
``run_review`` with ``transport: fake`` and strict replay cassettes, resume after every phase with
an identical report (ADR-009), resume in the middle of research without repeating a tool call or
duplicating a ledger ID, drift refusal and ``--accept-drift``, exit-code mapping, plan-only and
plan approval.

The model phases owned by workstreams A and B are replaced by small stand-ins (``stub_phases``)
that call the same scripted ``FakeGateway`` and tool gateway and write the RunState fields their
docstrings list, so these tests do not depend on A/B's implementations.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.clock import FakeClock
from sit_review_agent.config import EffectiveConfig
from sit_review_agent.context import RunContext
from sit_review_agent.errors import ExitCode, LLMOverloadedError, ResumeDriftError
from sit_review_agent.hashing import sha256_text
from sit_review_agent.invariants import check_all
from sit_review_agent.llm.gateway import FakeResponse, LLMRequest
from sit_review_agent.llm.outputs import (
    AssessOutput,
    PlanOutput,
    RefineRevisionsOutput,
    ResearchOutput,
    UnderstandOutput,
    apply_revisions,
)
from sit_review_agent.models import DegradationType, IntentSummary, SourceAuthority, StopReason, StopReasonCode
from sit_review_agent.orchestrator import RunRequest, resume_run, run_review
from sit_review_agent.phases._model_calls import resolve_evidence
from sit_review_agent.phases.assess import AssessPhase
from sit_review_agent.phases.ingest import IngestPhase
from sit_review_agent.phases.refine import findings_json
from sit_review_agent.phases.report import ReportPhase
from sit_review_agent.phases.verify import VerifyPhase
from sit_review_agent.progress import NullProgress
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.selftest import FIXTURE_DIR, fixture_gateway, selftest_config
from sit_review_agent.state.checkpoint import latest_checkpoint
from sit_review_agent.state.run_state import FindingMeta, ResearchPlan, ResearchQuestion
from sit_review_agent.states import PHASE_ORDER, PhaseName
from sit_review_agent.tools.cassette import Redactor
from sit_review_agent.tools.gateway import (
    LoggingToolGateway,
    ReplayGateway,
    SelfReplayGateway,
    ToolGateway,
)
from sit_review_agent.tools.sources import ExternalSource

PDF = FIXTURE_DIR / "design.pages.txt"


# ============================================================================ stand-in A/B phases


async def _call(ctx: RunContext, phase: PhaseName, schema: Any, conv: str | None = None,
                messages: list[dict[str, Any]] | None = None, tools: list[dict[str, Any]] | None = None) -> Any:
    req = LLMRequest(phase=phase, conversation_id=conv or phase.value, system="stub system",
                     messages=messages or [{"role": "user", "content": f"{phase.value} brief"}],
                     effort=ctx.config.effort_for(phase), max_tokens=1000, output_schema=schema, tools=tools or [])
    res = await ctx.llm.call(req)
    ctx.state.llm_calls.setdefault(phase.value, []).append(res.call_id)
    return res


class StubUnderstand:
    name = PhaseName.UNDERSTAND

    async def run(self, ctx: RunContext) -> RunContext:
        out: UnderstandOutput = (await _call(ctx, self.name, UnderstandOutput)).parsed
        ctx.state.intent_summary = IntentSummary.model_validate(out.intent_summary.model_dump())
        for r in out.registry:
            ctx.registry.add(r)
        ctx.registry.freeze()
        return ctx


class StubPlan:
    name = PhaseName.PLAN

    async def run(self, ctx: RunContext) -> RunContext:
        out: PlanOutput = (await _call(ctx, self.name, PlanOutput)).parsed
        ctx.state.plan = ResearchPlan(questions=[ResearchQuestion(**q.model_dump()) for q in out.questions],
                                      criteria_skipped=out.criteria_skipped)
        return ctx


class StubResearch:
    """One iteration: the scripted tool rounds (search, then fetch), each result into the ledger
    (search hits unread, a fetched page read in full), then the final answer."""

    name = PhaseName.RESEARCH

    def __init__(self, after_tool_call: Callable[[], None] | None = None) -> None:
        self.after_tool_call = after_tool_call

    @staticmethod
    def sources(tr: Any) -> list[ExternalSource]:
        if tr.tool_name == "fetch":
            return [ExternalSource(url_or_citation=tr.args["url"], title=tr.text.splitlines()[0], excerpt=tr.text,
                                   content=tr.text, authority=SourceAuthority.PRIMARY_OFFICIAL, read_in_full=True)]
        return [ExternalSource(url_or_citation=h["url"], title=h["title"], excerpt=h["content"], content=h["content"],
                               authority=SourceAuthority.PRIMARY_OFFICIAL, read_in_full=False)
                for h in json.loads(tr.text)["results"]]

    async def run(self, ctx: RunContext) -> RunContext:
        if ctx.tools is None:
            ctx.state.add_degradation(DegradationType.TOOL_UNAVAILABLE, "no tools enabled",
                                      "doc-only review: no external research")
            ctx.state.stop_reason = StopReason.of(StopReasonCode.TOOL_FAILURE, "no tools")
            return ctx
        res = await _call(ctx, self.name, ResearchOutput)
        while res.tool_uses:
            for tu in res.tool_uses:
                tr = await ctx.tools.call(tu.name, tu.input, phase=self.name)
                ctx.state.tool_calls.append(tr.research_log_entry())
                ctx.state.budget.tool_calls += 1
                ctx.state.queries_issued += 1
                if tr.ok:
                    for src in self.sources(tr):
                        ctx.ledger.add_external(tr, src)
                if self.after_tool_call is not None:
                    self.after_tool_call()
            res = await _call(ctx, self.name, ResearchOutput)
        final = res.parsed
        for a in final.answers:
            for q in ctx.state.plan.questions:
                if q.id == a.question_id:
                    q.status, q.summary, q.evidence_ids = a.status, a.summary, a.evidence_ids
        ctx.state.budget.research_iterations = 1
        ctx.state.budget.new_sources_by_iteration = [len(ctx.ledger)]
        ctx.registry.record_iteration(1)
        ctx.state.stop_reason = StopReason.of(StopReasonCode.SUFFICIENT_EVIDENCE)
        return ctx


def _metas(ctx: RunContext, drafts: list[Any], phase: PhaseName, res: Any) -> None:
    for d in drafts:
        prev = ctx.state.finding_meta.get(d.id)
        ctx.state.finding_meta[d.id] = FindingMeta(
            finding_id=d.id, criterion_ids=list(d.criterion_ids),
            created_phase=prev.created_phase if prev else phase,
            created_call_id=prev.created_call_id if prev else res.call_id, last_phase=phase,
            last_call_id=res.call_id, model=res.model, prompt_hash=sha256_text(f"{phase.value} brief"),
            history=list(prev.history) if prev else [])


class StubAssess:
    name = PhaseName.ASSESS

    async def run(self, ctx: RunContext) -> RunContext:
        res = await _call(ctx, self.name, AssessOutput)
        out: AssessOutput = res.parsed
        ctx.state.finding_drafts = list(out.findings)
        ctx.state.sound_area_drafts = list(out.sound_areas)
        ctx.state.coverage = list(out.coverage)
        _metas(ctx, out.findings, self.name, res)
        return ctx


class StubRefine:
    """The merge's ledger step and the refine call without the phase's checks. The stand-in assess
    runs beside research, so the new doc items its answer cites go to the ledger here, after stage 1,
    as ``AssessPhase.merge`` writes them (a shard is shown no register). The brief lists the merged
    findings as ``prompts/refine.md`` does, and the revisions are applied as given."""

    name = PhaseName.REFINE

    async def run(self, ctx: RunContext) -> RunContext:
        ctx.state.finding_drafts, ctx.state.sound_area_drafts, _ = resolve_evidence(
            ctx, list(ctx.state.finding_drafts), list(ctx.state.sound_area_drafts), shown=())
        brief = f"refine brief\n\n## Merged findings\n\n{findings_json(list(ctx.state.finding_drafts))}"
        res = await _call(ctx, self.name, RefineRevisionsOutput, messages=[{"role": "user", "content": brief}])
        drafts = apply_revisions(ctx.state.finding_drafts, res.parsed)
        ctx.state.finding_drafts = drafts
        _metas(ctx, drafts, self.name, res)
        return ctx


def stub_phases(**override: Any) -> dict[PhaseName, Any]:
    phases = {PhaseName.INGEST: IngestPhase(), PhaseName.UNDERSTAND: StubUnderstand(), PhaseName.PLAN: StubPlan(),
              PhaseName.RESEARCH: StubResearch(), PhaseName.ASSESS: StubAssess(), PhaseName.REFINE: StubRefine(),
              PhaseName.VERIFY: VerifyPhase(), PhaseName.REPORT: ReportPhase()}
    phases.update({PhaseName(k): v for k, v in override.items()})
    return phases


class Interrupt:
    """Raises KeyboardInterrupt (Ctrl-C) instead of running ``name``."""

    def __init__(self, name: PhaseName) -> None:
        self.name = name

    async def run(self, ctx: RunContext) -> RunContext:
        raise KeyboardInterrupt


class CountingReplay(ReplayGateway):
    calls: list[str] = []

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: Any = None) -> Any:
        CountingReplay.calls.append(tool_name)
        return await super().call(tool_name, args, phase=phase)


def tools_factory(rd: RunDir, resume_offset: int | None, clock: Any, progress: Any) -> ToolGateway:
    """Replay base (strict) + self-replay on resume + tools.jsonl logging, without B's policy layer."""
    gw: ToolGateway = CountingReplay(FIXTURE_DIR / "cassettes", strict=True, servers=["mcp-internet-search"],
                                     clock=clock)
    if resume_offset is not None:
        gw = SelfReplayGateway(gw, rd, upto_offset=resume_offset)
    return LoggingToolGateway(gw, rd, Redactor([]))


def config(tmp_path: Path, **agent: Any) -> EffectiveConfig:
    cfg = selftest_config(tmp_path / "runs")
    if agent:
        cfg = cfg.model_copy(update={"agent": cfg.agent.model_copy(update=agent)})
    return cfg


async def start(cfg: EffectiveConfig, run_id: str, phases: dict[PhaseName, Any] | None = None, **kw: Any) -> Any:
    return await run_review(RunRequest(pdf=PDF, config=cfg, run_id=run_id, **kw), phases=phases or stub_phases(),
                            tools_factory=tools_factory, clock=FakeClock(), progress=NullProgress())


async def resume(cfg: EffectiveConfig, run_dir: Path, **kw: Any) -> Any:
    return await resume_run(run_dir, cfg, phases=kw.pop("phases", None) or stub_phases(), tools_factory=tools_factory,
                            clock=FakeClock(), progress=NullProgress(), **kw)


def comparable(rd: Path) -> dict[str, Any]:
    r = json.loads((rd / "report.json").read_text(encoding="utf-8"))
    r.pop("run_manifest")
    r["metadata"].pop("run_id")
    r["metadata"].pop("review_id")
    return r


# ============================================================================ tests


async def test_run_review_end_to_end_fake_transport(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    out = await start(cfg, "full")
    assert out.exit_code == 0, (out.run_dir / "failure.json").read_text() if (out.run_dir / "failure.json").exists() \
        else ""
    rd = RunDir(out.run_dir)
    assert out.report_md == rd.report_md and rd.report_md.is_file() and rd.ledger.is_file() and rd.anchors.is_file()
    report = json.loads(rd.report_json.read_text(encoding="utf-8"))
    assert [r.inv_id for r in check_all(report, rd.root) if not r.passed] == []
    assert json.loads(rd.manifest.read_text(encoding="utf-8")) == report["run_manifest"]       # INV-09
    assert report["run_manifest"]["outcome"] == "completed_degraded"     # the unverified FND-003 is disclosed
    ids = [f["id"] for f in report["findings"]]
    assert ids == ["FND-004", "FND-002", "FND-001"]                       # rank order; FND-003 moved to unresolved
    assert any(u["text"].startswith("Unverified") for u in report["unresolved"])
    assert {"FND-002"} <= {x for u in report["unresolved"] for x in u["finding_ids"]}
    ext = report["findings"][0]["evidence"][-1]                            # added by refine after the doc item
    assert ext["evidence_id"] == "EV-002"                                  # the fetched page, not the snippet
    assert ext["source_type"] == "external" and ext["url_or_citation"].startswith("https://docs.example-mail.invalid")
    assert ext["retrieved_at"] == "2026-10-02T09:00:00Z"
    assert report["findings"][0]["provenance"]["phase"] == "revise"
    extra = report["run_manifest"]["extra"]
    assert extra["outputs"]["report_md_sha256"] == sha256_text(rd.report_md.read_text(encoding="utf-8"))
    assert extra["tools"]["transport"] == "fake+replay-strict" and extra["mode"] == "dev"
    assert sorted(p.name for p in rd.checkpoints.iterdir()) == [f"{i + 1:02d}-{p.value}.json"
                                                                  for i, p in enumerate(PHASE_ORDER)]
    assert len(CountingReplay.calls) >= 1


@pytest.mark.parametrize("phase", list(PHASE_ORDER))
async def test_resume_after_each_phase_gives_identical_report(tmp_path: Path, phase: PhaseName) -> None:
    cfg = config(tmp_path)
    ref = await start(cfg, "reference")
    assert ref.exit_code == 0
    out = await start(cfg, f"cut-{phase.value}", phases=stub_phases(**{phase.value: Interrupt(phase)}))
    assert out.exit_code == int(ExitCode.SIGINT)
    failure = json.loads((out.run_dir / "failure.json").read_text(encoding="utf-8"))
    assert failure["error"] == "RunInterrupted" and failure["resumable"]
    manifest = json.loads((out.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["outcome"] == "aborted_graceful"
    before = len(CountingReplay.calls)
    res = await resume(cfg, out.run_dir)
    assert res.exit_code == 0
    assert comparable(out.run_dir) == comparable(ref.run_dir)
    if phase in (PhaseName.REFINE, PhaseName.VERIFY, PhaseName.REPORT):
        assert len(CountingReplay.calls) == before                           # research not re-run
    report = json.loads((out.run_dir / "report.json").read_text(encoding="utf-8"))
    assert [r.inv_id for r in check_all(report, out.run_dir) if not r.passed] == []
    assert any(d.startswith("resumed") for d in report["run_manifest"]["extra"]["deviations"])


async def test_resume_mid_research_replays_tool_calls_from_the_run(tmp_path: Path) -> None:
    """NET-01: the run dies after the tool call inside research; resume serves that call from
    tools.jsonl (no live repeat), the ledger journal is cut back so no EV ID is duplicated, and
    new tool/LLM call IDs continue after the logged ones."""
    cfg = config(tmp_path)

    def die() -> None:
        raise KeyboardInterrupt

    out = await start(cfg, "net01", phases=stub_phases(research=StubResearch(after_tool_call=die)))
    assert out.exit_code == 130
    rd = RunDir(out.run_dir)
    assert latest_checkpoint(rd).phase is PhaseName.PLAN
    assert len(JsonlWriter(rd.ledger_journal).read()) == 1                # written before the interrupt
    live_before = len(CountingReplay.calls)
    llm_before = [e["call_id"] for e in JsonlWriter(rd.llm_log).read()]
    res = await resume(cfg, rd.root)
    assert res.exit_code == 0
    assert len(CountingReplay.calls) == live_before + 1                    # only the fetch goes below
    logged = JsonlWriter(rd.tools_log).read()
    assert [(e["tool"], e["call_id"]) for e in logged] == [("search", "call-0001"), ("search", "call-0001"),
                                                            ("fetch", "call-0002")]
    ids = [e["evidence_id"] for e in JsonlWriter(rd.ledger_journal).read()]
    assert ids[:2] == ["EV-001", "EV-002"] and len(ids) == len(set(ids))  # no duplicate after truncation
    assert {e["source_type"] for e in JsonlWriter(rd.ledger_journal).read()[2:]} <= {"doc"}   # the merge's doc items
    llm_after = [e["call_id"] for e in JsonlWriter(rd.llm_log).read()][len(llm_before):]
    assert not set(llm_after) & set(llm_before)                           # numbering continues
    report = json.loads(rd.report_json.read_text(encoding="utf-8"))
    assert [r.inv_id for r in check_all(report, rd.root) if not r.passed] == []


async def test_resume_refuses_drift_unless_accepted(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    out = await start(cfg, "drift", phases=stub_phases(assess=Interrupt(PhaseName.ASSESS)))
    assert out.exit_code == 130
    changed = cfg.model_copy(update={"stop_rules": cfg.stop_rules.model_copy(update={"max_tool_calls": 5})})
    with pytest.raises(ResumeDriftError) as info:
        await resume(changed, out.run_dir)
    assert int(info.value.exit_code) == 5 and "effective_config" in str(info.value)
    text = out.run_dir / "text" / "DOC-design.pages.txt"
    text.write_text(text.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    with pytest.raises(ResumeDriftError) as info2:
        await resume(cfg, out.run_dir)
    assert "canonical_text" in str(info2.value)
    res = await resume(changed, out.run_dir, accept_drift=True)
    assert res.exit_code == 0
    devs = json.loads((out.run_dir / "manifest.json").read_text(encoding="utf-8"))["extra"]["deviations"]
    assert any(d.startswith("--accept-drift: effective_config") for d in devs)
    assert any(d.startswith("--accept-drift: canonical_text") for d in devs)


async def test_eval_mode_never_accepts_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sit_review_agent.manifest as manifest

    monkeypatch.setattr(manifest, "check_eval_preconditions", lambda ctx: {"dirty": False})
    cfg = config(tmp_path)
    out = await start(cfg, "eval-drift", phases=stub_phases(assess=Interrupt(PhaseName.ASSESS)), mode="eval")
    assert out.exit_code == 130
    changed = cfg.model_copy(update={"stop_rules": cfg.stop_rules.model_copy(update={"max_tool_calls": 5})})
    with pytest.raises(ResumeDriftError):
        await resume(changed, out.run_dir, accept_drift=True)


class Boom:
    def __init__(self, name: PhaseName, exc: BaseException) -> None:
        self.name, self.exc = name, exc

    async def run(self, ctx: RunContext) -> RunContext:
        raise self.exc


@pytest.mark.parametrize(("exc", "code", "outcome"), [
    (RuntimeError("bug"), 4, "crashed"),
    (LLMOverloadedError("529 after retries"), 3, "aborted_graceful"),
    (KeyboardInterrupt(), 130, "aborted_graceful"),
])
async def test_exit_code_mapping_and_failure_record(tmp_path: Path, exc: BaseException, code: int,
                                                    outcome: str) -> None:
    cfg = config(tmp_path)
    out = await start(cfg, "fail", phases=stub_phases(assess=Boom(PhaseName.ASSESS, exc)))
    assert out.exit_code == code and out.report_md is None
    rec = json.loads((out.run_dir / "failure.json").read_text(encoding="utf-8"))
    # assess starts beside understand and plan: they ended (and checkpointed); research never started.
    assert rec["exit_code"] == code and rec["phase"] == "assess" and rec["completed_phases"] == ["ingest", "understand",
                                                                                                 "plan"]
    assert json.loads((out.run_dir / "manifest.json").read_text(encoding="utf-8"))["outcome"] == outcome
    assert (out.run_dir / "state.json").is_file()
    res = await resume(cfg, out.run_dir)
    assert res.exit_code == 0 and (out.run_dir / "report.json").is_file()


async def test_input_errors_are_raised_before_a_run_dir_exists(tmp_path: Path) -> None:
    from sit_review_agent.errors import InputError

    cfg = config(tmp_path)
    with pytest.raises(InputError):
        await run_review(RunRequest(pdf=tmp_path / "missing.pdf", config=cfg), phases=stub_phases())
    empty = tmp_path / "empty.txt"
    empty.write_text("[[PAGE 1]]\n\n", encoding="utf-8")
    out = await run_review(
        RunRequest(pdf=empty, config=cfg, run_id="empty"), phases=stub_phases(), tools_factory=tools_factory,
        clock=FakeClock(), progress=NullProgress())
    assert out.exit_code == int(ExitCode.USAGE)                            # InputError inside ingest -> 2
    assert json.loads((out.run_dir / "failure.json").read_text())["error"] == "InputError"


async def test_plan_only_prints_plan_and_makes_no_tool_call(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    before = len(CountingReplay.calls)
    buf = io.StringIO()
    out = await run_review(RunRequest(pdf=PDF, config=cfg, run_id="plan-only", plan_only=True), phases=stub_phases(),
                           tools_factory=tools_factory, clock=FakeClock(), progress=NullProgress(), stdout=buf)
    assert out.exit_code == 0 and out.report_md is None
    assert "RQ-001" in buf.getvalue() and len(CountingReplay.calls) == before
    assert json.loads((out.run_dir / "manifest.json").read_text())["outcome"] == "aborted_graceful"
    assert not JsonlWriter(out.run_dir / "tools.jsonl").read()


@pytest.mark.parametrize(("answer", "expect_report"), [("y\n", True), ("n\n", False)])
async def test_plan_approval_reads_stdin(tmp_path: Path, answer: str, expect_report: bool) -> None:
    cfg = config(tmp_path, plan_approval=True)
    buf = io.StringIO()
    out = await run_review(RunRequest(pdf=PDF, config=cfg, run_id=f"approval-{answer.strip()}"), phases=stub_phases(),
                           tools_factory=tools_factory, clock=FakeClock(), progress=NullProgress(),
                           stdin=io.StringIO(answer), stdout=buf)
    assert out.exit_code == 0 and "Approve this plan" in buf.getvalue()
    assert (out.report_md is not None) is expect_report
    if not expect_report:
        state = json.loads((out.run_dir / "state.json").read_text())
        assert state["plan"]["approved"] is False


async def test_no_tools_is_a_doc_only_run(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    cfg = cfg.model_copy(update={"tools": cfg.tools.model_copy(update={
        "servers": [s.model_copy(update={"enabled": False}) for s in cfg.tools.servers]})})
    out = await run_review(RunRequest(pdf=PDF, config=cfg, run_id="doc-only"), phases=stub_phases(),
                           clock=FakeClock(), progress=NullProgress())
    assert out.exit_code == 0
    report = json.loads((out.run_dir / "report.json").read_text())
    assert report["stop_reason"]["code"] == "tool_failure"
    assert [e for e in report["evidence_ledger"] if e["source_type"] != "doc"] == []   # doc items only
    assert report["research_log"]["tool_calls"] == []
    assert "No external research was possible" in (out.run_dir / "report.md").read_text()
    # external evidence that does not exist (refine adds the fixture's EV-001) was dropped, never invented
    assert report["findings"] and all(e["source_type"] == "doc" for f in report["findings"] for e in f["evidence"])
    assert [r.inv_id for r in check_all(report, out.run_dir) if not r.passed] == []


def test_fixture_gateway_resolves_ledger_ids(tmp_path: Path) -> None:
    rd = RunDir(tmp_path / "r").create()
    gw = fixture_gateway(rd, criteria_ids=["a", "b"])
    assert gw.remaining("research") >= 2 and gw.remaining("verify") == 1


async def test_live_backend_preflight_failure_exits_3_before_ingest(tmp_path: Path) -> None:
    from sit_review_agent.config import Transport
    from sit_review_agent.errors import LLMAuthError

    cfg = config(tmp_path, transport=Transport.REPLAY)

    def factory(fail: bool) -> Callable[..., Any]:
        def make(rd: RunDir, clock: Any, progress: Any) -> Any:
            gw = fixture_gateway(rd, clock=clock)

            async def preflight() -> None:
                if fail:
                    raise LLMAuthError("ANTHROPIC_API_KEY is not set")

            gw.preflight = preflight
            return gw
        return make

    out = await run_review(RunRequest(pdf=PDF, config=cfg, run_id="no-key"), phases=stub_phases(),
                           llm_factory=factory(True), tools_factory=tools_factory, clock=FakeClock(),
                           progress=NullProgress())
    assert out.exit_code == int(ExitCode.LLM_UNAVAILABLE)
    rec = json.loads((out.run_dir / "failure.json").read_text(encoding="utf-8"))
    assert rec["error"] == "LLMAuthError" and rec["completed_phases"] == []
    assert "sk-" not in json.dumps(rec)
    ok = await run_review(RunRequest(pdf=PDF, config=cfg, run_id="key-ok"), phases=stub_phases(),
                          llm_factory=factory(False), tools_factory=tools_factory, clock=FakeClock(),
                          progress=NullProgress())
    assert ok.exit_code == 0
    manifest = json.loads((ok.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["extra"]["model"]["models_retrieve"]["status"].startswith("not available")


async def test_fault_schedule_wraps_the_llm_gateway(tmp_path: Path) -> None:
    """A persistent refusal in report (LLM-06) through the fault-injecting layer: the verdict falls
    back to the rule, the run still reports and passes the invariants, the schedule is recorded."""
    sched = tmp_path / "LLM-06-report.yaml"
    sched.write_text("id: LLM-06-report\nllm:\n  - match: {stage: report}\n    fault: {type: stop_reason, "
                     "value: refusal}\n", encoding="utf-8")
    cfg = config(tmp_path, fault_schedule=str(sched))
    out = await start(cfg, "faulted")
    assert out.exit_code == 0
    report = json.loads((out.run_dir / "report.json").read_text(encoding="utf-8"))
    assert "derived by rule" in report["verdict"]["rationale"]
    assert report["run_manifest"]["fault_schedule_id"] == "LLM-06-report"
    assert report["run_manifest"]["extra"]["fault_injection"]["profile"] == "LLM-06-report"
    assert [r.inv_id for r in check_all(report, out.run_dir) if not r.passed] == []


async def test_self_replay_serves_each_logged_ok_call_once(tmp_path: Path) -> None:
    from sit_review_agent.models import ToolCallStatus
    from sit_review_agent.tools.gateway import FakeToolGateway, ToolSpec

    rd = RunDir(tmp_path / "r").create()
    spec = ToolSpec(server="srv", name="search", description="", input_schema={})
    live = FakeToolGateway([spec], {"srv__search": lambda a: f"live {a['q']}"})
    logged = LoggingToolGateway(live, rd, Redactor([]))
    await logged.call("srv__search", {"q": "a"})
    await logged.call("srv__search", {"q": "a"})
    failed = FakeToolGateway([spec], {})                          # unknown tool -> error result
    await LoggingToolGateway(failed, rd, Redactor([])).call("srv__other", {"q": "b"})
    offset = rd.tools_log.stat().st_size
    replay = SelfReplayGateway(FakeToolGateway([spec], {"srv__search": lambda a: "new", "srv__other": lambda a: "ok"}),
                               rd, upto_offset=offset)
    first, second, third = [await replay.call("srv__search", {"q": "a"}) for _ in range(3)]
    assert (first.replayed, second.replayed, third.replayed) == (True, True, False)
    assert [first.call_id, second.call_id] == ["call-0001", "call-0002"] and third.text == "new"
    other = await replay.call("srv__other", {"q": "b"})          # a failed call is never replayed
    assert other.status is ToolCallStatus.OK and not other.replayed
    assert replay.served == ["call-0001", "call-0002"]


@pytest.mark.parametrize("how", ["v1", "previous"])
async def test_delta_review_against_a_prior_version(tmp_path: Path, how: str) -> None:
    cfg = config(tmp_path)
    if how == "v1":
        prior = tmp_path / "design_v0.pages.txt"
        prior.write_text(PDF.read_text(encoding="utf-8"), encoding="utf-8")
        out = await start(cfg, "delta-v1", v1_pdf=prior)
        prior_id = "DOC-design_v0"
    else:
        ref = await start(cfg, "frozen-v1")
        out = await start(cfg, "delta-prev", previous_run=ref.run_dir)
        prior_id = "DOC-design-prior"
    assert out.exit_code == 0, (out.run_dir / "failure.json").read_text() if (out.run_dir / "failure.json").exists() \
        else ""
    report = json.loads((out.run_dir / "report.json").read_text(encoding="utf-8"))
    md = report["metadata"]
    assert md["review_mode"] == "delta" and md["prior_review_id"]
    assert [(d["doc_id"], d["role"]) for d in md["documents"]] == [("DOC-design", "under_review"),
                                                                   (prior_id, "prior_version")]
    if how == "previous":
        assert md["prior_review_id"] == "REV-frozen-v1"
    assert all(f["reassessment"] is not None and f["provenance"]["phase"] == "delta_review"
               for f in report["findings"])
    assert "## Changes since the previous version" in (out.run_dir / "report.md").read_text(encoding="utf-8")
    assert [r.inv_id for r in check_all(report, out.run_dir) if not r.passed] == []


# ============================================================================ stage 1 resume (ADR-009)


Q_OVERVIEW = "The service lets students reserve study rooms for one-hour slots across campus."
Q_LOAD = "Peak exam-week days generate about 5,000 bookings, each with one reminder."


def _shard_answer(i: int, criteria: list[str]) -> dict[str, Any]:
    quote, page, section = (Q_OVERVIEW, 2, "1") if i % 2 else (Q_LOAD, 6, "4.1")
    return {"findings": [{
        "id": "FND-001", "rank": 1, "kind": "gap", "category": "missing_or_unverifiable_requirement",
        "severity": "medium", "confidence": 0.6, "disposition": "needs_investigation", "secondary_dispositions": [],
        "title": f"Shard {i} finding", "statement": f"Shard {i} statement about section {section}.",
        "doc_anchors": [{"doc_id": "DOC-design", "section_ref": section, "requirement_ids": [], "quote": quote,
                         "page": page}],
        "evidence": [{"evidence_id": "NEW-1", "source_type": "doc", "quote": quote, "supports_claim": True,
                      "derived_from": []}],
        "recommendation": {"issue": "i", "rationale": "r", "expected_benefit": "b", "change_summary": "c",
                           "objective_refs": [], "supporting_evidence_ids": ["NEW-1"], "verification": None},
        "no_change_rationale": None, "next_step": {"owner": "Design owner", "action": f"Check section {section}."},
        "affected_decisions": [], "acknowledged_in_doc": False, "tags": [], "reassessment": None,
        "criterion_ids": [criteria[0]]}],
        "sound_areas": [],
        "coverage": [{"criterion_id": c, "outcome": "no_issue", "finding_ids": [], "note": "checked"}
                     for c in criteria[1:]]}


class ShardScript:
    """The fixture gateway for every other phase; the assess shards answered per conversation,
    and a conversation in ``interrupt`` raises Ctrl-C instead of answering."""

    def __init__(self, cfg: EffectiveConfig, interrupt: set[str] | None = None) -> None:
        self.shards = cfg.agent.assess.shards_for(cfg.criteria.ids())
        self.interrupt = interrupt or set()
        self.assess_calls: list[str] = []

    def __call__(self, rd: Any, clock: Any, progress: Any) -> Any:
        gw = fixture_gateway(rd, clock=clock)
        inner_call = gw.call
        script = self

        async def call(request: LLMRequest) -> Any:
            if request.phase is PhaseName.ASSESS:
                script.assess_calls.append(request.conversation_id)
                if request.conversation_id in script.interrupt:
                    raise KeyboardInterrupt
                i = int(request.conversation_id.rsplit("-s", 1)[1])
                gw.script["assess"].appendleft(FakeResponse(parsed=_shard_answer(i, script.shards[i - 1].criteria)))
            return await inner_call(request)

        gw.call = call  # type: ignore[method-assign]
        return gw


def shard_phases() -> dict[PhaseName, Any]:
    return stub_phases(assess=AssessPhase())


async def test_resume_after_two_of_four_shards_runs_exactly_the_other_two(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    assert len(cfg.agent.assess.shards_for(cfg.criteria.ids())) == 4
    ref_script = ShardScript(cfg)
    ref = await run_review(RunRequest(pdf=PDF, config=cfg, run_id="ref4"), phases=shard_phases(),
                           llm_factory=ref_script, tools_factory=tools_factory, clock=FakeClock(),
                           progress=NullProgress())
    assert ref.exit_code == 0 and ref_script.assess_calls == [f"assess-0-s{i}" for i in range(1, 5)]

    cut = ShardScript(cfg, interrupt={"assess-0-s3", "assess-0-s4"})
    out = await run_review(RunRequest(pdf=PDF, config=cfg, run_id="cut4"), phases=shard_phases(), llm_factory=cut,
                           tools_factory=tools_factory, clock=FakeClock(), progress=NullProgress())
    assert out.exit_code == int(ExitCode.SIGINT)
    stored = sorted(p.name for p in (out.run_dir / "shards").iterdir())
    assert stored == ["01-intent_and_fitness.json", "02-requirements_and_consistency.json"]

    again = ShardScript(cfg)
    res = await resume_run(out.run_dir, cfg, phases=shard_phases(), llm_factory=again, tools_factory=tools_factory,
                           clock=FakeClock(), progress=NullProgress())
    assert res.exit_code == 0
    assert again.assess_calls == ["assess-0-s3", "assess-0-s4"]             # exactly the unfinished shards
    assert comparable(out.run_dir) == comparable(ref.run_dir)              # same IDs, ledger and report
    entries = JsonlWriter(RunDir(out.run_dir).llm_log).read()
    assert not [e for e in entries if e.get("phase") in ("understand", "plan") and e.get("resumed")]


class _Slow:
    """A stand-in that moves the run clock forward while it works."""

    def __init__(self, inner: Any, seconds: float) -> None:
        self.inner, self.name, self.seconds = inner, inner.name, seconds

    async def run(self, ctx: RunContext) -> RunContext:
        ctx.clock.advance(self.seconds)  # type: ignore[attr-defined]
        return await self.inner.run(ctx)


async def test_resume_restores_the_clock_from_elapsed_seconds(tmp_path: Path) -> None:
    """Stage 1 members overlap, so their seconds do not sum to the run's: resume restores the clock
    from the checkpoint's budget.elapsed_s (100 + 50 s here), never from the sum (100 + 150 s)."""
    cfg = config(tmp_path)
    phases = stub_phases(understand=_Slow(StubUnderstand(), 100), plan=_Slow(StubPlan(), 50),
                         research=Interrupt(PhaseName.RESEARCH))
    out = await start(cfg, "clock", phases=phases)
    assert out.exit_code == 130
    ckpt = latest_checkpoint(RunDir(out.run_dir))
    assert ckpt is not None and ckpt.state.budget.elapsed_s == 150.0
    assert sum(ckpt.state.budget.phase_seconds.values()) == 250.0            # understand 100 + plan 150 (overlap)
    assert ckpt.state.budget.phase_seconds["plan"] == 150.0
    res = await resume(cfg, out.run_dir)
    assert res.exit_code == 0
    final = latest_checkpoint(RunDir(out.run_dir))
    assert final is not None and final.phase is PhaseName.REPORT and final.state.budget.elapsed_s == 150.0
