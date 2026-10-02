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
            self.clock.advance(1800)                                     # one model call at llm.timeout_s
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
        if field == "title":                    # FND-002, a strength: no length floor caught this before
            next(f for f in p["findings"] if f["id"] == "FND-002")["title"] = "TBD"
        else:                                   # also below MIN_TEXT_CHARS, so it was dropped before too
            p["findings"][0]["recommendation"]["rationale"] = "TBD"

    rec = run(Scenario(id="REG-5", patches={"assess": tbd, "refine": tbd}), tmp_path)
    assert "TBD" not in rec.run_dir.report_json.read_text(encoding="utf-8")
    assert any(f"placeholder text in {field}" in d["event"] for d in rec.report["research_log"]["degradations"])


# ============================================================================= 6. resolve_evidence


def test_doc_citation_with_a_quote_not_in_the_document_is_not_recorded_as_doc_text(tmp_path: Path) -> None:
    external_text = "Higher plans allow 10,000 or more messages per day."

    def mislabel(p: dict[str, Any]) -> None:
        p["findings"][2]["evidence"].append({"evidence_id": "NEW-9", "source_type": "doc", "quote": external_text,
                                             "supports_claim": True, "derived_from": []})

    rec = run(Scenario(id="REG-6", patches={"assess": mislabel, "refine": mislabel}), tmp_path)
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


# ============================================================================= 8. refine (BEH-10)


@pytest.mark.parametrize("reason, kept", [("", "high"), ("Downgraded: section 6.2 already caps reminders.", "low")])
def test_severity_change_needs_a_reason_or_new_evidence(reason: str, kept: str, tmp_path: Path) -> None:
    def flip(p: dict[str, Any]) -> None:
        next(f for f in p["findings"] if f["id"] == "FND-001")["severity"] = "low"
        p["revisions"] = [r for r in p["revisions"] if r["finding_id"] != "FND-001"]
        if reason:
            p["revisions"].append({"finding_id": "FND-001", "change": "revised", "reason": reason,
                                   "evidence_ids": []})

    rec = run(Scenario(id="REG-8", patches={"refine": flip}), tmp_path)
    f1 = next(f for f in rec.report["findings"] if f["id"] == "FND-001")
    assert f1["severity"] == kept
    notes = [h["note"] for h in rec.state["finding_meta"]["FND-001"]["history"] if h["phase"] == "refine"]
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
