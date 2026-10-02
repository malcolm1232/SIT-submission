"""understand / plan / assess / refine (workstream A) with ``FakeGateway``: offline, no key.

Covers what the removed ``tests/test_pending.py`` names ``test_model_phases_with_fake_gateway`` (each phase
writes the RunState fields its docstring lists), plus the phase contract: conversation IDs, effort,
cached prefix, prompts via ``ctx.prompts.render``, call IDs, refusal-then-reframed-retry, persistent
refusal as a degradation, schema repair, truncation retry, the registry freeze, criterion coverage
completeness, ledger-backed evidence, and an orchestrator run that checkpoints the results.
"""

from __future__ import annotations

import dataclasses
import json
from collections import deque
from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.clock import FakeClock, isoformat_z
from sit_review_agent.config import EffectiveConfig, load_config
from sit_review_agent.context import RunContext
from sit_review_agent.errors import LLMSchemaError, RegistryFrozenError
from sit_review_agent.hashing import sha256_text
from sit_review_agent.ingest.pdf import Document
from sit_review_agent.ingest.text import flatten_for_match
from sit_review_agent.llm.gateway import FakeGateway, FakeResponse, LLMRequest, LLMResult
from sit_review_agent.llm.outputs import FindingDraft, RegistryEntryDraft
from sit_review_agent.models import (
    DegradationType,
    DocumentRole,
    EvidenceItem,
    FallbackEvent,
    Finding,
    Provenance,
    ReviewMode,
    SourceType,
)
from sit_review_agent.orchestrator import Orchestrator
from sit_review_agent.phases._model_calls import extend_quote, record_result
from sit_review_agent.phases.assess import AssessPhase
from sit_review_agent.phases.plan import PlanPhase, enabled_capabilities
from sit_review_agent.phases.refine import RefinePhase
from sit_review_agent.phases.understand import UnderstandPhase
from sit_review_agent.progress import NullProgress
from sit_review_agent.prompts import PromptBundle
from sit_review_agent.rundir import RunDir
from sit_review_agent.state.checkpoint import latest_checkpoint
from sit_review_agent.state.decision_registry import DecisionRegistry
from sit_review_agent.state.evidence_ledger import EvidenceLedger
from sit_review_agent.state.run_state import DocumentRef, RunState
from sit_review_agent.states import PHASE_ORDER, PROVENANCE_PHASE, PhaseName
from sit_review_agent.tools.gateway import FakeToolGateway, ToolSpec

FIXTURES = Path(__file__).parent / "fixtures"
DOC_ID = "DOC-booking-v1"
Q_OVERVIEW = "The service lets students reserve study rooms for one-hour slots across campus."
Q_LOAD = "Peak exam-week days generate about 5,000 bookings, each with one reminder."
Q_NOTIFY = "The selected e-mail service has no daily sending limit, so reminders are sent individually"
Q_A11Y = "Every booking screen is tested against WCAG 2.2 level AA with automated checks"
Q_D3 = "D-3 Confirmed: the booking front end is built from the campus design system component library."


# ------------------------------------------------------------------------------ fixtures


@pytest.fixture(scope="module")
def cfg() -> EffectiveConfig:
    return load_config()


def anchor(quote: str, page: int, section: str, req: list[str] | None = None) -> dict[str, Any]:
    return {"doc_id": DOC_ID, "section_ref": section, "requirement_ids": req or [], "quote": quote, "page": page}


def make_ctx(tmp_path: Path, cfg: EffectiveConfig, script: dict[Any, list[FakeResponse]], *,
             gw: Any = None, tools: Any = None, review_mode: ReviewMode = ReviewMode.FULL) -> RunContext:
    clock = FakeClock()
    rd = RunDir(tmp_path / "run-1").create()
    text = (FIXTURES / "booking_v1.pages.txt").read_text(encoding="utf-8")
    doc = Document.from_page_marked_text(text, doc_id=DOC_ID, title="Room booking", pdf_bytes=b"%PDF-1.7 fake")
    state = RunState(run_id="run-1", created_utc=isoformat_z(clock.now_utc()), review_mode=review_mode,
                     documents=[DocumentRef(doc_id=DOC_ID, role=DocumentRole.UNDER_REVIEW, title="Room booking",
                                            sha256_text=doc.sha256_text, text_path=f"text/{DOC_ID}.pages.txt")])
    return RunContext(config=cfg, run_dir=rd, state=state, llm=gw or FakeGateway(script, run_dir=rd, clock=clock),
                      tools=tools, ledger=EvidenceLedger(rd, clock=clock), registry=DecisionRegistry(),
                      prompts=PromptBundle.load(), clock=clock, progress=NullProgress(), documents={DOC_ID: doc})


def understand_output() -> dict[str, Any]:
    return {
        "intent_summary": {
            "statement": "A campus service for booking study rooms in one-hour slots.",
            "objectives": [{"ref": "G-1", "text": "Students can reserve rooms."}, {"ref": None, "text": "  "}],
            "constraints": [{"ref": "D-3", "text": "Use the campus design system."}],
            "key_assumptions": [{"ref": "", "text": "Reminders always reach students."}],
            "doc_anchors": [anchor(Q_OVERVIEW, 2, "1")],
        },
        "registry": [
            {"type": "approved_decision", "doc_ref": "D-3", "statement": "Front end uses the design system.",
             "doc_anchor": anchor(Q_D3, 19, "20", ["D-3"])},
            {"type": "constraint", "doc_ref": "6.2", "statement": "Reminders are e-mailed individually.",
             "doc_anchor": anchor("no daily sending limit", 11, "6.2")},          # short quote, found verbatim
            {"type": "requirement", "doc_ref": "R-9", "statement": "Invented.",
             "doc_anchor": anchor("this sentence is nowhere", 3, "9")},           # short, not found: dropped
        ],
        "document_version": "1.0",
        "review_inputs_found": ["Change log says the reminder limit was fixed (p11).", " "],
    }


def plan_output(criteria: list[str]) -> dict[str, Any]:
    return {
        "questions": [
            {"id": "Q1", "criterion_id": "claims_and_external_constraints",
             "question": "Does the e-mail plan allow 5,000 reminders a day?", "rationale": "FR-9 depends on it.",
             "needs_external": True, "capability": "search",
             "queries": ["e-mail service daily sending limit", "https://example.invalid/limits", ""],
             "section_refs": ["6.2"]},
            {"id": "Q1", "criterion_id": "internal_consistency", "question": "Do load and notification agree?",
             "rationale": "4.1 vs 6.2.", "needs_external": False, "capability": "search", "queries": ["x"],
             "section_refs": ["4.1", "6.2"]},
            {"id": "RQ-9", "criterion_id": "not_a_criterion", "question": "Dropped.", "rationale": "-",
             "needs_external": False, "capability": "none", "queries": [], "section_refs": []},
        ],
        "criteria_skipped": [{"criterion_id": "operability_and_governance", "reason": "out of scope"},
                             {"criterion_id": "internal_consistency", "reason": "already has a question"}],
    }


def finding(fid: str, rank: int, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": fid, "rank": rank, "kind": "risk", "category": "unsupported_or_incorrect_claim", "severity": "high",
        "confidence": 0.9, "disposition": "refinement_now", "secondary_dispositions": [],
        "title": "Reminder volume exceeds the e-mail plan", "statement": "6.2 assumes no sending limit.",
        "doc_anchors": [anchor(Q_NOTIFY, 11, "6.2")],
        "evidence": [
            {"evidence_id": "EV-001", "source_type": "doc", "quote": Q_LOAD, "supports_claim": True,
             "derived_from": []},
            {"evidence_id": "NEW-1", "source_type": "doc", "quote": Q_NOTIFY, "supports_claim": True,
             "derived_from": []},
            {"evidence_id": "NEW-2", "source_type": "inference", "quote": "5,000 reminders need a high quota.",
             "supports_claim": True, "derived_from": ["EV-001", "NEW-1"]},
            {"evidence_id": "EV-404", "source_type": "external", "quote": "made up", "supports_claim": True,
             "derived_from": []},
        ],
        "recommendation": {"issue": "Unverified quota.", "rationale": "Peak load.", "expected_benefit": "FR-9 holds.",
                           "change_summary": "State the plan quota in 6.2.", "objective_refs": ["FR-9"],
                           "supporting_evidence_ids": ["NEW-2", "EV-404"], "verification": "Peak-day test."},
        "no_change_rationale": None, "next_step": None, "affected_decisions": [], "acknowledged_in_doc": False,
        "tags": ["notifications"], "reassessment": None,
        "criterion_ids": ["claims_and_external_constraints", "not_a_criterion"],
    }
    base.update(kw)
    return base


def strength(fid: str, rank: int) -> dict[str, Any]:
    return finding(fid, rank, kind="strength", category=None, severity=None, disposition="no_change",
                   title="Accessibility is verified", statement="11.3 tests every screen at AA.",
                   doc_anchors=[anchor(Q_A11Y, 18, "11.3")], evidence=[], recommendation=None,
                   no_change_rationale="Directly verifies the accessibility objective.",
                   criterion_ids=["verifiability"], confidence=1.4)


def assess_output() -> dict[str, Any]:
    return {
        "findings": [finding("F-1", 2), strength("F-1", 1)],         # malformed and duplicate IDs
        "sound_areas": [{"section_refs": ["11.3"], "why_sound": "AA tests.",
                         "doc_anchors": [anchor(Q_A11Y, 18, "11.3")], "evidence_ids": ["NEW-1", "EV-777"],
                         "related_finding_ids": ["F-1", "FND-999"]}],
        "coverage": [
            {"criterion_id": "claims_and_external_constraints", "outcome": "findings", "finding_ids": ["F-1"],
             "note": "quota"},
            {"criterion_id": "security_and_privacy", "outcome": "findings", "finding_ids": [], "note": "?"},
            {"criterion_id": "verifiability", "outcome": "no_issue", "finding_ids": [], "note": "checked"},
            {"criterion_id": "unknown_criterion", "outcome": "no_issue", "finding_ids": [], "note": ""},
        ],
    }


def brief_of(req: LLMRequest) -> str:
    return req.messages[0]["content"][-1]["text"]


def hydrate(ctx: RunContext, draft: FindingDraft) -> Finding:
    """What verify will do (workstream C): every citation must hydrate and the Finding validate."""
    meta = ctx.state.finding_meta[draft.id]
    data = draft.model_dump(mode="json", exclude={"criterion_ids", "evidence"})
    data["evidence"] = [ctx.ledger.hydrate(c).model_dump(mode="json") for c in draft.evidence]
    data["provenance"] = Provenance(phase=PROVENANCE_PHASE[meta.last_phase], iteration=meta.iteration,
                                    model=meta.model or "x", prompt_hash=meta.prompt_hash or "0" * 64)
    return Finding.model_validate(data)


# ------------------------------------------------------------------------------ understand


async def test_understand_writes_intent_registry_and_freezes(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {PhaseName.UNDERSTAND: [FakeResponse(parsed=understand_output())]})
    await UnderstandPhase().run(ctx)
    s = ctx.state

    assert s.intent_summary is not None and s.intent_summary.doc_anchors[0].quote == Q_OVERVIEW
    assert [o.ref for o in s.intent_summary.objectives] == ["G-1"]                  # blank entry dropped
    assert s.intent_summary.key_assumptions[0].ref is None
    assert [e.registry_id for e in ctx.registry.entries()] == ["AD-001", "AD-002"]
    extended = ctx.registry.get("AD-002").doc_anchor.quote
    assert len(extended.split()) >= 8 and extended in flatten_for_match(ctx.documents[DOC_ID].text)
    assert ctx.registry.frozen and s.registry_frozen and [e.registry_id for e in s.registry] == ["AD-001", "AD-002"]
    assert [h.iteration for h in s.registry_hashes] == [0] and s.registry_hashes[0].sha256 == ctx.registry.sha256()
    with pytest.raises(RegistryFrozenError):
        ctx.registry.add(RegistryEntryDraft.model_validate(understand_output()["registry"][0]))
    assert s.review_inputs_found == ["Change log says the reminder limit was fixed (p11)."]
    assert s.documents[0].version == "1.0" and ctx.documents[DOC_ID].version == "1.0"
    assert [d.type for d in s.degradations] == [DegradationType.OTHER] and "R-9" in s.degradations[0].event
    assert s.llm_calls == {"understand": ["llm-0001"]} and s.budget.input_tokens == 1000

    [req] = ctx.llm.calls
    assert req.conversation_id == "understand-0" and req.effort == cfg.effort_for(PhaseName.UNDERSTAND)
    persona = cfg.persona()
    assert req.system == ctx.prompts.render("system.md", persona_title=persona.title.strip(),
                                            persona_emphasis=" ".join(persona.emphasis.split())).text
    content = req.messages[0]["content"]
    assert [b["type"] for b in content] == ["document", "text", "text"]          # PDF, canonical text, brief
    assert req.cache_breakpoints[0].block_index == 1 and req.output_schema.__name__ == "UnderstandOutput"
    assert "Phase: understand the design" in brief_of(req) and "`verifiability`" in brief_of(req)
    assert "Context of this request" not in brief_of(req)


async def test_understand_refusal_then_reframed_retry(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {PhaseName.UNDERSTAND: [FakeResponse(stop_reason="refusal", refusal_category="cyber"),
                                                          FakeResponse(parsed=understand_output())]})
    await UnderstandPhase().run(ctx)
    first, second = ctx.llm.calls
    assert (first.conversation_id, second.conversation_id) == ("understand-0", "understand-0-r1")
    assert second.effort == first.effort and second.purpose == "understand:refusal_retry"
    assert "professional engineering design review" in brief_of(second)
    assert second.messages[0]["content"][:2] == first.messages[0]["content"][:2]   # same cached prefix
    assert ctx.state.refusals == [{"call_id": "llm-0001", "stage": "understand", "category": "cyber"}]
    assert ctx.state.llm_calls["understand"] == ["llm-0001", "llm-0002"]
    assert ctx.state.intent_summary is not None and not ctx.state.declined_sections


async def test_understand_persistent_refusal_degrades(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {PhaseName.UNDERSTAND: [FakeResponse(stop_reason="refusal"),
                                                          FakeResponse(stop_reason="refusal")]})
    await UnderstandPhase().run(ctx)
    assert ctx.state.declined_sections == ["understand"] and ctx.state.intent_summary is None
    assert ctx.registry.frozen and ctx.registry.entries() == [] and ctx.state.registry_hashes
    assert ctx.state.degradations[-1].type is DegradationType.OTHER and len(ctx.state.refusals) == 2


async def test_understand_schema_error_repaired_once(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {PhaseName.UNDERSTAND: [FakeResponse(parsed={"intent_summary": 3}),
                                                          FakeResponse(parsed=understand_output())]})
    await UnderstandPhase().run(ctx)
    repair = ctx.llm.calls[1]
    assert repair.conversation_id == "understand-0-r1" and repair.purpose == "understand:schema_repair"
    assert "## Correction" in brief_of(repair) and "intent_summary" in brief_of(repair)
    assert "://" not in brief_of(repair)                          # pydantic's help URL is stripped
    assert ctx.state.intent_summary is not None

    ctx2 = make_ctx(tmp_path / "b", cfg, {PhaseName.UNDERSTAND: [FakeResponse(parsed={"x": 1}),
                                                                  FakeResponse(parsed={"y": 2})]})
    with pytest.raises(LLMSchemaError):
        await UnderstandPhase().run(ctx2)


async def test_truncation_retried_with_more_tokens(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {PhaseName.UNDERSTAND: [FakeResponse(stop_reason="max_tokens"),
                                                          FakeResponse(parsed=understand_output())]})
    await UnderstandPhase().run(ctx)
    first, second = ctx.llm.calls
    assert second.max_tokens == min(128_000, 2 * first.max_tokens) and second.conversation_id == "understand-0-r1"


@pytest.mark.parametrize("configured,retry_at", [(64_000, 128_000), (128_000, 128_000), (100_000, 128_000)])
async def test_truncation_retry_at_and_below_the_output_cap(tmp_path: Path, cfg: EffectiveConfig, configured: int,
                                                           retry_at: int) -> None:
    """One retry whatever the configured cap: wider when a wider value exists, else at the cap
    itself (config/agent.yaml is at the 128000 cap since 2026-10-03). A second truncation is never
    retried again and never repaired: the phase degrades like a deadline cut and discloses the
    truncation (robustness LLM-07, Session 4 ruling)."""
    from sit_review_agent.models import DegradationType

    capped = cfg.model_copy(update={"agent": cfg.agent.model_copy(update={"max_tokens": configured})})
    ctx = make_ctx(tmp_path, capped, {PhaseName.UNDERSTAND: [FakeResponse(stop_reason="max_tokens"),
                                                             FakeResponse(parsed=understand_output())]})
    await UnderstandPhase().run(ctx)
    first, second = ctx.llm.calls
    assert (first.max_tokens, second.max_tokens) == (configured, retry_at)
    assert second.purpose == "understand:max_tokens_retry" and ctx.state.intent_summary is not None
    twice = make_ctx(tmp_path / "b", capped, {PhaseName.UNDERSTAND: [FakeResponse(stop_reason="max_tokens")] * 3})
    await UnderstandPhase().run(twice)
    assert len(twice.llm.calls) == 2 and twice.state.intent_summary is None and twice.registry.frozen
    (deg,) = twice.state.degradations
    assert deg.type is DegradationType.OTHER
    assert deg.event.startswith("the understand answer was truncated twice at the output cap "
                                f"(max_tokens={retry_at};")
    assert twice.state.declined_sections == [] and len(twice.state.llm_calls["understand"]) == 2


async def test_a_call_truncated_twice_is_neither_declined_nor_cut(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """The phases tell the three no-output outcomes apart by the PhaseCall flags."""
    from sit_review_agent.llm.outputs import UnderstandOutput
    from sit_review_agent.phases._model_calls import call_model

    ctx = make_ctx(tmp_path, cfg, {PhaseName.UNDERSTAND: [FakeResponse(stop_reason="max_tokens")] * 2})

    def render(*, reframed: bool, schema_error: str) -> Any:
        return ctx.prompts.render("understand.md", criteria=[], documents=[], review_mode="full",
                                  reframed=reframed, schema_error=schema_error)

    call = await call_model(ctx, PhaseName.UNDERSTAND, render, UnderstandOutput)
    assert call.result is None and call.truncated and not call.cut and not call.declined


def test_configured_output_cap_is_the_model_maximum_and_fits_the_context_margin(cfg: EffectiveConfig) -> None:
    """config/agent.yaml max_tokens is 128000 (the live assess used 63,392 of the earlier 64,000).
    The pre-send size check (LLM-10) allows input up to 80 % of the context window and does not
    count the output cap, so the margin it leaves must hold that cap for every supported model."""
    from sit_review_agent.config import SUPPORTED_MODELS, load_config
    from sit_review_agent.llm.runtime import CONTEXT_MARGIN, ContextGuard, context_window_for
    from sit_review_agent.phases._model_calls import MAX_OUTPUT_TOKENS

    shipped = load_config()
    assert shipped.agent.max_tokens == MAX_OUTPUT_TOKENS == 128_000
    for model in SUPPORTED_MODELS:
        window = context_window_for(model)
        guard = ContextGuard(window_tokens=window)
        assert guard.limit_tokens == int(window * CONTEXT_MARGIN)
        assert guard.limit_tokens + shipped.agent.max_tokens <= window, model


async def test_text_only_backend_gets_no_pdf_block(tmp_path: Path, cfg: EffectiveConfig) -> None:
    class TextOnly(FakeGateway):
        native_pdf = False

    ctx = make_ctx(tmp_path, cfg, {})
    ctx.llm = TextOnly({PhaseName.UNDERSTAND: [FakeResponse(parsed=understand_output())]})
    await UnderstandPhase().run(ctx)
    assert [b["type"] for b in ctx.llm.calls[0].messages[0]["content"]] == ["text", "text"]


def test_extend_quote_stays_verbatim_and_on_page(cfg: EffectiveConfig, tmp_path: Path) -> None:
    doc = make_ctx(tmp_path, cfg, {}).documents[DOC_ID]
    hay = flatten_for_match(doc.text)
    out = extend_quote(doc, "exam-week days generate")
    assert out is not None and len(out.split()) >= 8 and out in hay and "[[PAGE" not in out
    tail = extend_quote(doc, "design system component library.")       # end of the document: extends backwards
    assert tail is not None and tail.endswith("component library.") and tail in hay
    assert extend_quote(doc, "words that do not occur") is None


# ------------------------------------------------------------------------------ plan


async def test_plan_maps_every_criterion(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {PhaseName.PLAN: [FakeResponse(parsed=plan_output(cfg.criteria.ids()))]})
    await PlanPhase().run(ctx)
    plan = ctx.state.plan
    assert plan is not None and plan.approved
    ids = cfg.criteria.ids()
    covered = {q.criterion_id for q in plan.questions}
    skipped = {s.criterion_id for s in plan.criteria_skipped}
    assert covered | skipped == set(ids) and not covered & skipped            # completeness, no overlap
    assert [s.criterion_id for s in plan.criteria_skipped] == ["operability_and_governance"]
    assert [q.id for q in plan.questions] == [f"RQ-{i + 1:03d}" for i in range(len(plan.questions))]
    ext = next(q for q in plan.questions if q.criterion_id == "claims_and_external_constraints")
    assert ext.capability == "none" and ext.queries == ["e-mail service daily sending limit"]   # no tools, no URL
    doc_q = next(q for q in plan.questions if q.criterion_id == "internal_consistency")
    assert doc_q.capability == "none" and doc_q.status == "open"
    added = [q for q in plan.questions if q.rationale.startswith("Added by code")]
    assert {q.criterion_id for q in added} == set(ids) - {"claims_and_external_constraints", "internal_consistency",
                                                          "operability_and_governance"}
    assert all(not q.needs_external and q.question == cfg.criteria.get(q.criterion_id).question for q in added)
    assert any("left out" in e.message for e in ctx.progress.events)
    [req] = ctx.llm.calls
    assert req.conversation_id == "plan-0" and req.effort == cfg.effort_for(PhaseName.PLAN)
    assert ctx.state.llm_calls == {"plan": ["llm-0001"]}
    brief = brief_of(req)
    assert f"at most {cfg.stop_rules.max_tool_calls} tool calls" in brief and "(none available in this run)" in brief


async def test_plan_with_tools_and_approval(tmp_path: Path, cfg: EffectiveConfig) -> None:
    approval = cfg.model_copy(update={"agent": cfg.agent.model_copy(update={"plan_approval": True})})
    tools = FakeToolGateway([ToolSpec(server="mcp-internet-search", name="search", description="d",
                                      input_schema={"type": "object"})], {})
    ctx = make_ctx(tmp_path, approval, {PhaseName.PLAN: [FakeResponse(parsed=plan_output(cfg.criteria.ids()))]},
                   tools=tools)
    assert enabled_capabilities(ctx) == ["scholarly", "search"]                # sorted; browse's server is disabled
    await PlanPhase().run(ctx)
    ext = next(q for q in ctx.state.plan.questions if q.criterion_id == "claims_and_external_constraints")
    assert ext.capability == "search" and ctx.state.plan.approved is False
    assert "scholarly, search" in brief_of(ctx.llm.calls[0])


async def test_plan_declined_falls_back_to_document_questions(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {PhaseName.PLAN: [FakeResponse(stop_reason="refusal"),
                                                    FakeResponse(stop_reason="refusal")]})
    await PlanPhase().run(ctx)
    plan = ctx.state.plan
    assert [q.criterion_id for q in plan.questions] == cfg.criteria.ids() and not plan.criteria_skipped
    assert ctx.state.declined_sections == ["plan"]


# ------------------------------------------------------------------------------ assess


async def test_assess_writes_drafts_meta_coverage_and_ledger(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {PhaseName.ASSESS: [FakeResponse(parsed=assess_output())]})
    pre = ctx.ledger.add_doc(doc_id=DOC_ID, page=6, section_ref="4.1", excerpt=Q_LOAD)       # EV-001
    ctx.state.budget.research_iterations = 2
    await AssessPhase().run(ctx)
    s = ctx.state

    risk, good = s.finding_drafts
    assert [f.id for f in s.finding_drafts] == ["FND-001", "FND-002"]           # renumbered
    assert (risk.rank, good.rank) == (2, 1) and good.confidence == 1.0
    assert risk.criterion_ids == ["claims_and_external_constraints"]
    # evidence: EV-001 kept, NEW-1 (doc) and NEW-2 (inference) added to the ledger, EV-404 dropped
    assert [c.evidence_id for c in risk.evidence] == [pre.evidence_id, "EV-002", "EV-003"]
    assert [c.source_type for c in risk.evidence] == [SourceType.DOC, SourceType.DOC, SourceType.INFERENCE]
    inference = ctx.ledger.get("EV-003")
    assert inference.derived_from == ["EV-001", "EV-002"] and risk.evidence[2].derived_from == ["EV-001", "EV-002"]
    assert ctx.ledger.get("EV-002").url_or_citation == f"doc:{DOC_ID}#p11/s6.2"
    assert risk.recommendation is not None and risk.recommendation.supporting_evidence_ids == ["EV-003"]
    assert {e.evidence_id for e in EvidenceLedger.load(ctx.run_dir)} == {"EV-001", "EV-002", "EV-003"}  # journaled
    for draft in s.finding_drafts:                                             # verify can hydrate them
        f = hydrate(ctx, draft)
        assert all(isinstance(e, EvidenceItem) for e in f.evidence)

    meta = s.finding_meta["FND-001"]
    [req] = ctx.llm.calls
    assert meta.created_phase is PhaseName.ASSESS and meta.last_call_id == "llm-0001" and meta.iteration == 2
    assert meta.model == "claude-opus-5-5" and meta.prompt_hash == sha256_text(brief_of(req))
    assert req.conversation_id == "assess-2" and req.effort == cfg.effort_for(PhaseName.ASSESS)
    assert "EV-001 [doc]" in brief_of(req) and "http" not in brief_of(req)

    [area] = s.sound_area_drafts
    assert area.related_finding_ids == ["FND-001"] and area.evidence_ids == ["EV-002"]
    cov = {c.criterion_id: c for c in s.coverage}
    assert list(cov) == cfg.criteria.ids()                                     # one row per criterion, in order
    assert cov["claims_and_external_constraints"].finding_ids == ["FND-001"]
    assert cov["security_and_privacy"].outcome == "no_issue"                   # "findings" with none attached
    assert cov["verifiability"].outcome == "findings" and cov["verifiability"].finding_ids == ["FND-002"]
    assert cov["design_intent"].outcome == "not_applicable" and "no coverage row" in cov["design_intent"].note
    assert any("dropped" in e.message for e in ctx.progress.events)


async def test_assess_persistent_refusal_completes(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {PhaseName.ASSESS: [FakeResponse(stop_reason="refusal", refusal_category="bio"),
                                                      FakeResponse(stop_reason="refusal", refusal_category="bio")]})
    await AssessPhase().run(ctx)
    assert ctx.state.declined_sections == ["assess"] and ctx.state.finding_drafts == []
    assert [c.criterion_id for c in ctx.state.coverage] == cfg.criteria.ids()
    assert all("declined" in c.note for c in ctx.state.coverage)
    assert "bio" in ctx.state.degradations[0].event
    assert [c.conversation_id for c in ctx.llm.calls] == ["assess-0", "assess-0-r1"]


async def test_delta_mode_sets_reassessment(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {PhaseName.ASSESS: [FakeResponse(parsed=assess_output())]},
                   review_mode=ReviewMode.DELTA)
    await AssessPhase().run(ctx)
    assert all(f.reassessment is not None and f.reassessment.status.value == "new_in_update"
               for f in ctx.state.finding_drafts)
    assert "Re-review of an updated document" in brief_of(ctx.llm.calls[0])


# ------------------------------------------------------------------------------ refine


async def test_refine_revises_adds_withdraws_with_history(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {PhaseName.ASSESS: [FakeResponse(parsed=assess_output())]})
    ctx.ledger.add_doc(doc_id=DOC_ID, page=6, section_ref="4.1", excerpt=Q_LOAD)
    await AssessPhase().run(ctx)
    before = {f.id: f for f in ctx.state.finding_drafts}
    revised = before["FND-001"].model_dump(mode="json") | {"severity": "medium", "secondary_dispositions": []}
    added = finding("FND-001", 2, title="Second, distinct issue", kind="gap", category="security_privacy_gap",
                    evidence=[], criterion_ids=["security_and_privacy"],
                    disposition="needs_investigation", next_step={"owner": "Security lead", "action": "Check."})
    out = {"findings": [revised, added],          # FND-002 (the strength) is withdrawn; "FND-001" twice
           "revisions": [{"finding_id": "FND-001", "change": "revised", "reason": "impact is bounded",
                          "evidence_ids": []},
                         {"finding_id": "FND-002", "change": "withdrawn", "reason": "covered elsewhere",
                          "evidence_ids": []}]}
    ctx.llm.script[str(PhaseName.REFINE)] = deque([FakeResponse(parsed=out)])
    await RefinePhase().run(ctx)
    s = ctx.state

    assert [f.id for f in s.finding_drafts] == ["FND-001", "FND-003"]          # never reuses withdrawn FND-002
    m1 = s.finding_meta["FND-001"]
    assert m1.created_phase is PhaseName.ASSESS and m1.last_phase is PhaseName.REFINE
    assert PROVENANCE_PHASE[m1.last_phase].value == "revise"
    [rev] = m1.history
    assert rev.changed_fields["severity"] == ["high", "medium"] and rev.note == "revised: impact is bounded"
    m3 = s.finding_meta["FND-003"]
    assert m3.created_phase is PhaseName.REFINE and m3.created_call_id == "llm-0002"
    assert s.finding_meta["FND-002"].history[-1].note == "withdrawn: covered elsewhere"
    new = s.finding_drafts[1]
    assert new.recommendation.supporting_evidence_ids and new.evidence[0].source_type is SourceType.DOC
    hydrate(ctx, new)
    cov = {c.criterion_id: c for c in s.coverage}
    assert cov["verifiability"].outcome == "no_issue" and cov["verifiability"].finding_ids == []
    assert cov["security_and_privacy"].finding_ids == ["FND-003"]
    assert s.sound_area_drafts[0].related_finding_ids == ["FND-001"]
    req = ctx.llm.calls[-1]
    assert req.conversation_id == "refine-0" and req.effort == cfg.effort_for(PhaseName.REFINE)
    assert '"id": "FND-002"' in brief_of(req) and s.llm_calls["refine"] == ["llm-0002"]


async def test_refine_without_drafts_makes_no_call(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {})
    await RefinePhase().run(ctx)
    assert ctx.llm.calls == [] and "refine" not in ctx.state.llm_calls


# ------------------------------------------------------------------------------ bookkeeping, orchestrator


async def test_fallback_is_recorded_as_degradation(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {PhaseName.PLAN: [FakeResponse(parsed={"questions": [], "criteria_skipped": []})]})
    res = await ctx.llm.call(LLMRequest(phase=PhaseName.PLAN, conversation_id="x", system="s",
                                        messages=[{"role": "user", "content": "x"}], effort="high", max_tokens=10))
    fb = FallbackEvent(role="plan", from_model="claude-opus-5-5", to_model="claude-opus-5", reason="test")
    record_result(ctx, PhaseName.PLAN, dataclasses.replace(res, fallback=fb))
    assert ctx.state.fallback_events == [fb]
    assert ctx.state.degradations[0].type is DegradationType.MODEL_FALLBACK


class _Noop:
    def __init__(self, name: PhaseName) -> None:
        self.name = name

    async def run(self, ctx: RunContext) -> RunContext:
        return ctx


async def test_orchestrator_runs_model_phases_and_checkpoints(tmp_path: Path, cfg: EffectiveConfig) -> None:
    script = {PhaseName.UNDERSTAND: [FakeResponse(parsed=understand_output())],
              PhaseName.PLAN: [FakeResponse(parsed=plan_output(cfg.criteria.ids()))],
              PhaseName.ASSESS: [FakeResponse(parsed=assess_output())],
              PhaseName.REFINE: [FakeResponse(parsed={"findings": [], "revisions": []})]}
    ctx = make_ctx(tmp_path, cfg, script)
    phases: dict[PhaseName, Any] = {p: _Noop(p) for p in PHASE_ORDER}
    phases.update({PhaseName.UNDERSTAND: UnderstandPhase(), PhaseName.PLAN: PlanPhase(),
                   PhaseName.ASSESS: AssessPhase(), PhaseName.REFINE: RefinePhase()})
    ctx = await Orchestrator(phases).run(ctx)
    assert ctx.llm.remaining() == 0
    assert set(ctx.state.llm_calls) == {"understand", "plan", "assess", "refine"}
    assert ctx.state.finding_drafts == [] and set(ctx.state.finding_meta) == {"FND-001", "FND-002"}
    ckpt = latest_checkpoint(ctx.run_dir)
    assert ckpt is not None and ckpt.state.registry_frozen and ckpt.state.plan is not None
    reloaded = RunState.model_validate(json.loads(ckpt.state.model_dump_json()))
    assert reloaded.model_dump(exclude={"current_phase"}) == ctx.state.model_dump(exclude={"current_phase"})


def test_llm_result_type_is_what_phases_consume() -> None:
    assert {f.name for f in dataclasses.fields(LLMResult)} >= {"call_id", "model", "parsed", "usage", "fallback"}
