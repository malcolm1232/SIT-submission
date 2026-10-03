"""Regression tests for the agent defects the robustness scenarios exposed and this workstream fixed
(each change is logged in research/audit/robustness_suite_editlog.md).

1. orchestrator: a between-phase cap that skips a phase was not disclosed when research had
   already set the stop reason (the deadline silently skipped ``refine``; LLM-05, live run in
   docs/HANDOVER_FULL.md §8).
2. FaultInjectingLLMGateway: ``nth`` (a documented match key) never matched on the LLM layer, so a
   fault could not hit only the first call of a stage and phase-level recovery (LLM-06/07/08) could
   not be driven by a schedule.
3. FaultInjectingLLMGateway: with ``transport: fake`` an injected hang cost a hard-coded 600 s, not
   the configured ``llm.timeout_s`` (1800 s) (LLM-05).
4. research: "No external research was possible" was missing when every tool call failed but too
   few calls were made to open every breaker (INF-24).
5. verify: placeholder ("TBD") findings reached the report (LLM-09).
6. _model_calls.resolve_evidence: a ``doc`` citation whose quote is not in the document became a
   ``doc`` ledger entry holding that (external) text (BEH-17).

Verifier fixes (same edit log, "Verifier edits"):

7. orchestrator: a stage crash wrote no partial report (BEH-25, ADR-009 item 5).
8. refine: a severity / disposition / kind change with no reason and no new evidence was accepted (BEH-10).
9. verify: a recommendation reversing an approved decision without a ``challenges`` label was not caught (BEH-12).
10. research: a stop vote with zero external evidence was reported as ``sufficient_evidence`` (INF-24 run).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from robustness_harness import Scenario, run

from sit_review_agent.clock import FakeClock, isoformat_z
from sit_review_agent.config import load_config
from sit_review_agent.context import RunContext
from sit_review_agent.errors import LLMTimeoutError, LLMTruncatedError
from sit_review_agent.llm.gateway import FakeGateway, FakeResponse, FaultInjectingLLMGateway, LLMRequest
from sit_review_agent.llm.outputs import FindingDraft
from sit_review_agent.models import (
    AffectedDecision,
    DegradationType,
    Finding,
    RegistryEntry,
    StopReason,
    StopReasonCode,
)
from sit_review_agent.orchestrator import Orchestrator
from sit_review_agent.phases.verify import hollow_fields, unlabelled_conflicts
from sit_review_agent.progress import NullProgress
from sit_review_agent.prompts import PromptBundle
from sit_review_agent.rundir import RunDir
from sit_review_agent.selftest import fixture_script
from sit_review_agent.state.decision_registry import DecisionRegistry
from sit_review_agent.state.evidence_ledger import EvidenceLedger
from sit_review_agent.state.run_state import RunState
from sit_review_agent.states import PHASE_ORDER, PhaseName
from sit_review_agent.stop_rules import NO_EXTERNAL_QUESTIONS
from sit_review_agent.tools.faults import FaultSchedule
from sit_review_agent.tools.gateway import PolicyToolGateway
from sit_review_agent.tools.mcp_client import find_layer

# ============================================================================= 1. orchestrator


class _Step:
    def __init__(self, name: PhaseName, log: list[str], clock: FakeClock) -> None:
        self.name, self.log, self.clock = name, log, clock

    async def run(self, ctx: RunContext) -> RunContext:
        self.log.append(self.name.value)
        if self.name is PhaseName.RESEARCH:
            ctx.state.stop_reason = StopReason.of(StopReasonCode.SUFFICIENT_EVIDENCE, "all_questions_answered")
        if self.name is PhaseName.ASSESS:
            self.clock.advance(ctx.config.stop_rules.deadline_seconds)   # assess runs to the deadline
        return ctx


async def test_deadline_skip_after_research_is_disclosed(tmp_path: Path) -> None:
    clock, log = FakeClock(), []
    rd = RunDir(tmp_path / "run").create()
    ctx = RunContext(config=load_config(), run_dir=rd, state=RunState(run_id="run", created_utc=isoformat_z(
        clock.now_utc())), llm=FakeGateway({}), tools=None, ledger=EvidenceLedger(rd, clock=clock),
        registry=DecisionRegistry(), prompts=PromptBundle.load(), clock=clock, progress=NullProgress())
    await Orchestrator({p: _Step(p, log, clock) for p in PHASE_ORDER}).run(ctx)
    assert "refine" not in log and log[-2:] == ["verify", "report"]
    assert ctx.state.stop_reason.code is StopReasonCode.SUFFICIENT_EVIDENCE   # research's reason is kept
    hit = [d for d in ctx.state.degradations if d.type is DegradationType.BUDGET_OR_DEADLINE_HIT]
    assert len(hit) == 1 and "before refine" in hit[0].event and "skipped to verify" in hit[0].impact


# ============================================================================= 2-3. LLM fault layer


def _req(phase: PhaseName = PhaseName.ASSESS) -> LLMRequest:
    return LLMRequest(phase=phase, conversation_id=f"c-{phase.value}", system="s",
                      messages=[{"role": "user", "content": "x"}], effort="high", max_tokens=1000)


def _sched(rules: list[dict[str, Any]]) -> FaultSchedule:
    return FaultSchedule.model_validate({"id": "REG", "seed": 1, "llm": rules})


async def test_llm_rule_with_nth_hits_only_that_call_of_the_stage() -> None:
    inner = FakeGateway({"assess": [FakeResponse(text="ok")] * 3, "plan": [FakeResponse(text="ok")]})
    gw = FaultInjectingLLMGateway(inner, _sched([{"match": {"stage": "assess", "nth": [0]},
                                                  "fault": {"type": "stop_reason", "value": "max_tokens"}}]))
    assert (await gw.call(_req(PhaseName.PLAN))).text == "ok"           # another stage: its own count
    with pytest.raises(LLMTruncatedError):
        await gw.call(_req())                                            # assess call 0: faulted
    assert (await gw.call(_req())).text == "ok"                          # assess call 1 (the retry): clean
    assert (await gw.call(_req())).text == "ok"


@pytest.mark.parametrize("policy, expected", [(True, 1800.0), (False, 600.0)])
async def test_injected_hang_costs_the_configured_timeout(policy: bool, expected: float) -> None:
    clock = FakeClock()
    cfg = load_config()
    assert cfg.agent.llm.timeout_s == 1800                               # config/agent.yaml (HANDOVER §8)
    inner = FakeGateway({"assess": [FakeResponse(text="ok")]}, clock=clock)
    gw = FaultInjectingLLMGateway(inner, _sched([{"match": {"stage": "assess"}, "fault": {"type": "hang"}}]),
                                  clock=clock, policy=cfg.agent.llm if policy else None)
    with pytest.raises(LLMTimeoutError) as info:
        await gw.call(_req())
    assert f"{expected:.0f} s" in str(info.value)
    assert clock.monotonic() >= (cfg.agent.llm.max_retries + 1) * expected


# ============================================================================= 4. research


def test_all_calls_failed_below_the_breaker_threshold_is_doc_only(tmp_path: Path) -> None:
    rec = run(Scenario(id="REG-4", faults="INF-24"), tmp_path)
    pol = find_layer(rec.tools, PolicyToolGateway)
    assert not pol.server_open("mcp-internet-search") and not pol.server_open("mcp-research-information")
    events = [d["event"] for d in rec.report["research_log"]["degradations"]]
    assert "No external research was possible: every tool call failed" in events


# ============================================================================= 5. verify


def _draft() -> dict[str, Any]:
    ledger = [{"evidence_id": "EV-001", "source_type": "external", "read_before_cite": True}]
    return fixture_script(["x"])["assess"][0](ledger, None).parsed["findings"][0]   # type: ignore[operator, union-attr]


@pytest.mark.parametrize("text", ["TBD", "  tbd. ", "N/A", "...", "", "-", "TODO", "Lorem ipsum dolor sit amet"])
def test_placeholder_text_makes_a_draft_hollow(text: str) -> None:
    d = _draft()
    d["statement"] = text
    assert hollow_fields(FindingDraft.model_validate(d)) == ["statement"]


def test_real_text_is_not_hollow() -> None:
    d = _draft()
    d["statement"] = "None of the reminders is sent when the daily quota is reached."
    assert hollow_fields(FindingDraft.model_validate(d)) == []


@pytest.mark.parametrize("field", ["recommendation.rationale", "title"])
def test_hollow_finding_is_dropped_and_disclosed(field: str, tmp_path: Path) -> None:
    def tbd(p: dict[str, Any]) -> None:
        if field == "title":                    # FND-001, a strength: no length floor caught this before
            next(f for f in p["findings"] if f["id"] == "FND-001")["title"] = "TBD"
        else:                                   # also below MIN_TEXT_CHARS, so it was dropped before too
            p["findings"][0]["recommendation"]["rationale"] = "TBD"

    rec = run(Scenario(id="REG-5", patches={"assess": tbd}), tmp_path)   # a refine revision carries no text
    assert "TBD" not in rec.run_dir.report_json.read_text(encoding="utf-8")
    assert any(f"placeholder text in {field}" in d["event"] for d in rec.report["research_log"]["degradations"])


# ============================================================================= 6. resolve_evidence


def test_doc_citation_with_a_quote_not_in_the_document_is_not_recorded_as_doc_text(tmp_path: Path) -> None:
    external_text = "Higher plans allow 10,000 or more messages per day."

    def mislabel(p: dict[str, Any]) -> None:
        next(f for f in p["findings"] if f["id"] == "FND-002")["evidence"].append(
            {"evidence_id": "NEW-9", "source_type": "doc", "quote": external_text, "supports_claim": True,
             "derived_from": []})

    rec = run(Scenario(id="REG-6", patches={"assess": mislabel}), tmp_path)
    for e in json.loads(rec.run_dir.ledger.read_text(encoding="utf-8")):
        if e["source_type"] == "doc":
            assert external_text not in (e["excerpt"] or ""), e


# ============================================================================= 7. partial report (BEH-25)


def _crash_in(stage: str) -> Any:
    def patch(data: dict[str, Any]) -> None:
        data["process"][0]["stage"] = stage
    return patch


def test_stage_crash_writes_a_partial_report_listing_completed_stages(tmp_path: Path) -> None:
    rec = run(Scenario(id="REG-7", faults="BEH-25", variant=_crash_in("understand")), tmp_path)
    assert rec.exit_code == 4 and rec.report is None and rec.failure["partial_report"] == "report.partial.md"
    text = (rec.run_dir.root / "report.partial.md").read_text(encoding="utf-8")
    assert "Completed stages: ingest\n" in text and "Crashed stage: understand" in text
    assert "Research questions planned: 0" in text                     # no plan yet: still renders


def test_no_partial_report_when_the_model_is_unavailable(tmp_path: Path) -> None:
    rec = run(Scenario(id="REG-7b", faults="LLM-02"), tmp_path)       # exit 3, not a stage crash
    assert rec.exit_code == 3 and not (rec.run_dir.root / "report.partial.md").exists()
    assert "partial_report" not in rec.failure



def _truncate_every(stage: str) -> Any:
    def patch(data: dict[str, Any]) -> None:
        data["llm"] = [{"match": {"stage": stage},
                        "fault": {"type": "stop_reason", "value": "max_tokens", "truncate_at_fraction": 0.6}}]
    return patch


@pytest.fixture(scope="module")
def truncation_controls(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Fault-free runs: the full pipeline, and one with refine disabled (the assess drafts as they
    are reported when refine does not run)."""
    full = run(Scenario(id="REG-TRUNC2-control"), tmp_path_factory.mktemp("trunc-control"))
    unrefined = run(Scenario(id="REG-TRUNC2-norefine", phases_enabled={"refine": False}),
                    tmp_path_factory.mktemp("trunc-norefine"))
    return {"stop_reason": full.report["stop_reason"],                # type: ignore[index]
            "unrefined_titles": [f["title"] for f in unrefined.report["findings"]]}  # type: ignore[index]


@pytest.mark.parametrize("stage", ["understand", "plan", "assess", "refine"])
def test_a_stage_that_truncates_twice_ends_in_a_disclosed_degraded_report(
        stage: str, tmp_path: Path, truncation_controls: dict[str, Any]) -> None:
    """LLM-07, persistent variant ("truncates twice"). The one retry runs at the same 128000 cap,
    so a second truncation is possible. Ruling (Session 4, "treat the second truncation like a
    deadline cut"): no third call, no truncated object, and the run continues with the stage's
    deadline fallback and discloses it, naming the truncation, not the deadline and not a refusal.
    The report is written, the run exits 0 as ``completed_degraded`` like a deadline-degraded run,
    the manifest lists both truncated calls, and ``resume`` on the finished run repeats nothing."""
    from robustness_harness import resume

    rec = run(Scenario(id=f"REG-TRUNC2-{stage}", faults="LLM-07", variant=_truncate_every(stage)), tmp_path)
    calls = [e for e in rec.jsonl("llm.jsonl") if e.get("phase") == stage]
    # Assess runs as K concurrent shards (the configured groups, latency redesign): each shard is one
    # logical call with its one retry, so the stage makes K x 2 calls; every other stage makes its 2.
    shards = sorted({e.get("shard") for e in calls}, key=lambda s: (s is None, s)) if stage == "assess" else [None]
    k = len(rec.config.agent.assess.shards_for(rec.config.criteria.ids()))
    assert shards == (list(range(1, k + 1)) if stage == "assess" else [None])
    per_shard = {s: [e for e in calls if e.get("shard") == s] for s in shards}
    for s in shards:
        assert [e.get("outcome") for e in per_shard[s]] == ["LLMTruncatedError", "LLMTruncatedError"], s
        assert [e.get("purpose") for e in per_shard[s]] == [stage, f"{stage}:max_tokens_retry"], s
    assert len(calls) == 2 * len(shards)
    assert rec.raised is None and rec.exit_code == 0 and rec.failure is None
    report = rec.report
    assert report is not None and rec.run_dir.report_md.is_file()
    manifest = json.loads(rec.run_dir.manifest.read_text(encoding="utf-8"))
    assert manifest["outcome"] == "completed_degraded"
    assert manifest["extra"]["model"]["truncations"] == [
        {"call_id": e["call_id"], "stage": stage, "purpose": e["purpose"]} for e in calls]

    prefix = f"the {stage} answer was truncated twice at the output cap"
    degs = report["research_log"]["degradations"]
    mine = [d for d in degs if d["event"].startswith(prefix)]
    assert len(mine) == 1 and mine[0]["type"] == "other", degs
    if stage == "assess":
        # One note per shard, naming the shard and the shard's two call IDs (as the single-call
        # note did), and the one stage-level note above (no shard produced an assessment).
        for s in shards:
            notes = [d for d in degs if d["event"].startswith(f"assess shard {s}/{k} (") and prefix in d["event"]]
            assert len(notes) == 1 and notes[0]["type"] == "other", (s, degs)
            assert all(c["call_id"] in notes[0]["event"] for c in per_shard[s]), (s, notes[0]["event"])
    else:
        assert all(c["call_id"] in mine[0]["event"] for c in calls)
    assert not any(stage in d["event"] and ("deadline" in d["event"] or "declined" in d["event"]) for d in degs)
    assert any(mine[0]["id"] in lim["degradation_ids"] for lim in report["limitations"])
    md = rec.run_dir.report_md.read_text(encoding="utf-8")
    assert prefix in md
    progress = rec.run_dir.progress_log.read_text(encoding="utf-8")
    if stage == "assess":
        for s in shards:
            assert f"assess shard {s}/{k} (" in progress and (
                "): answer truncated twice at the output cap; its criteria are not assessed" in progress), s
        assert progress.count("answer truncated twice at the output cap; its criteria are not assessed") == k
    else:
        assert f"{stage}: answer truncated twice at the output cap" in progress
    stop = report["stop_reason"]                     # research's own stop reason, never a deadline
    assert "deadline" not in stop["detail"]
    if stage == "plan":                              # a code-built plan has no external question: research
        assert (stop["code"], stop["detail"]) == ("sufficient_evidence", NO_EXTERNAL_QUESTIONS)  # skipped (#40)
    else:
        assert stop == truncation_controls["stop_reason"]

    if stage == "assess":
        v = report["verdict"]
        assert v["label"] == "not_assessed" and report["findings"] == [] and report["sound_areas"] == []
        assert "cut off at the output cap" in v["rationale"] and "deadline" not in v["rationale"]
        assert "Not assessed (answer truncated twice at the output cap)" in md
        assert not [e for e in rec.jsonl("llm.jsonl") if e.get("phase") == "report"]     # no verdict call
        assert {c["note"] for c in rec.state["coverage"]} == {
            "not assessed: the assess answer was truncated twice at the output cap"}
        rows = [ln for ln in md.splitlines() if ln.endswith("| not assessed: the assess answer was truncated twice "
                                                             "at the output cap |")]
        assert len(rows) == len(rec.state["coverage"]) and all("| not assessed |" in r for r in rows)
    elif stage == "refine":
        assert [f["title"] for f in report["findings"]] == truncation_controls["unrefined_titles"]
        assert {f["provenance"]["phase"] for f in report["findings"]} == {"assess"}       # kept, unrefined
        assert report["verdict"]["label"] != "not_assessed"
    elif stage == "plan":
        questions = rec.state["plan"]["questions"]
        assert questions and all(not q["needs_external"] for q in questions)
        assert all("truncated twice at the output cap" in q["rationale"] for q in questions)
    else:
        assert rec.state["intent_summary"] is None and report["verdict"]["label"] != "not_assessed"

    llm_before = len(rec.jsonl("llm.jsonl"))
    report_bytes = rec.run_dir.report_json.read_bytes()
    again = resume(rec)
    assert again.raised is None and again.exit_code == 0
    assert len(rec.jsonl("llm.jsonl")) == llm_before                     # the two truncations are not repeated
    assert rec.run_dir.report_json.read_bytes() == report_bytes

# ============================================================================= 8. refine (BEH-10)


@pytest.mark.parametrize("reason, kept", [("", "high"), ("Downgraded: section 6.2 already caps reminders.", "low")])
def test_severity_change_needs_a_reason_or_new_evidence(reason: str, kept: str, tmp_path: Path) -> None:
    def flip(p: dict[str, Any]) -> None:
        r = next(r for r in p["revisions"] if r["finding_id"] == "FND-004")     # the e-mail quota finding
        r["severity"], r["added_evidence"], r["reason"] = "low", [], reason

    rec = run(Scenario(id="REG-8", patches={"refine": flip}), tmp_path)
    f1 = next(f for f in rec.report["findings"] if f["id"] == "FND-004")
    assert f1["severity"] == kept
    notes = [h["note"] for h in rec.state["finding_meta"]["FND-004"]["history"] if h["phase"] == "refine"]
    assert any(n.startswith("rejected: severity high -> low") for n in notes) == (not reason), notes


# ============================================================================= 9. verify (BEH-12)


@pytest.fixture(scope="module")
def fixture_review(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return run(Scenario(id="REG-9"), tmp_path_factory.mktemp("reg9")).report   # type: ignore[return-value]


def _finding_with(review: dict[str, Any], change: str, relation: str | None) -> Finding:
    f = json.loads(json.dumps(next(f for f in review["findings"] if f["recommendation"] is not None)))
    f["recommendation"]["change_summary"] = change
    f["affected_decisions"] = []
    out = Finding.model_validate(f)
    if relation:                                # a label only (the >= 2 evidence rule is INV-10's, not this check's)
        out = out.model_copy(update={"affected_decisions": [AffectedDecision(
            registry_id="AD-001", relation=relation, justification="The change replaces the approved library.")]})
    return out


@pytest.mark.parametrize("change, relation, expected", [
    ("Replace the campus design system with a bespoke component library.", None, ["AD-001"]),
    ("Replace the campus design system with a bespoke component library.", "challenges", []),
    ("Add the campus design system's date picker component library entry to section 5.", None, []),
    ("Replace the polling worker with a queue.", None, []),
])
def test_unlabelled_reversal_of_an_approved_decision_is_detected(fixture_review: dict[str, Any], change: str,
                                                                 relation: str | None, expected: list[str]) -> None:
    registry = [RegistryEntry.model_validate(e) for e in fixture_review["decision_registry"]]
    assert [e.registry_id for e in registry] == ["AD-001"]
    assert unlabelled_conflicts(_finding_with(fixture_review, change, relation), registry) == expected
