"""run_review / resume_run end to end (workstream C, "phase 3"), offline.

Covers what tests/test_pending.py's phase-3 entries ``test_resume_reuses_completed_tool_calls``
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
from sit_review_agent.llm.gateway import LLMRequest
from sit_review_agent.llm.outputs import AssessOutput, PlanOutput, RefineOutput, ResearchOutput, UnderstandOutput
from sit_review_agent.models import DegradationType, IntentSummary, SourceAuthority, StopReason, StopReasonCode
from sit_review_agent.orchestrator import RunRequest, resume_run, run_review
from sit_review_agent.phases.ingest import IngestPhase
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
    name = PhaseName.REFINE

    async def run(self, ctx: RunContext) -> RunContext:
        res = await _call(ctx, self.name, RefineOutput)
        out: RefineOutput = res.parsed
        ctx.state.finding_drafts = list(out.findings)
        _metas(ctx, out.findings, self.name, res)
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
    assert report["run_manifest"]["outcome"] == "completed_degraded"     # the unverified FND-004 is disclosed
    ids = [f["id"] for f in report["findings"]]
    assert ids == ["FND-001", "FND-002", "FND-003"]                       # FND-004 moved to unresolved
    assert any(u["text"].startswith("Unverified") for u in report["unresolved"])
    assert {"FND-003"} <= {x for u in report["unresolved"] for x in u["finding_ids"]}
    ext = report["findings"][0]["evidence"][0]
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


@pytest.mark.parametrize("phase", [p for p in PHASE_ORDER if p is not PhaseName.INGEST])
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
    if PHASE_ORDER.index(phase) > PHASE_ORDER.index(PhaseName.RESEARCH):
        assert len(CountingReplay.calls) == before                           # research not re-run
    report = json.loads((out.run_dir / "report.json").read_text(encoding="utf-8"))
    assert [r.inv_id for r in check_all(report, out.run_dir) if not r.passed] == []
    assert any(d.startswith("resumed after phase") for d in report["run_manifest"]["extra"]["deviations"])


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
    assert ids == ["EV-001", "EV-002"]                                    # no duplicate after truncation
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
    assert rec["exit_code"] == code and rec["phase"] == "assess" and rec["completed_phases"][-1] == "research"
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
    assert report["evidence_ledger"] == [] and report["research_log"]["tool_calls"] == []
    assert "No external research was possible" in (out.run_dir / "report.md").read_text()
    # findings citing evidence that does not exist were dropped, never invented
    assert all(f["evidence"] == [] for f in report["findings"])
    assert [r.inv_id for r in check_all(report, out.run_dir) if not r.passed] == []


def test_fixture_gateway_resolves_ledger_ids(tmp_path: Path) -> None:
    rd = RunDir(tmp_path / "r").create()
    gw = fixture_gateway(rd, criteria_ids=["a", "b"])
    assert gw.remaining("research") >= 2 and gw.remaining("verify") == 1
