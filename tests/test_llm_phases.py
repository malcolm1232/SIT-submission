"""understand / plan / assess / refine (workstream A) with ``FakeGateway``: offline, no key.

Covers what the removed ``tests/test_pending.py`` names ``test_model_phases_with_fake_gateway`` (each phase
writes the RunState fields its docstring lists), plus the phase contract: conversation IDs, effort,
cached prefix, prompts via ``ctx.prompts.render``, call IDs, refusal-then-reframed-retry, persistent
refusal as a degradation, schema repair, truncation retry, the registry freeze, criterion coverage
completeness, ledger-backed evidence, and an orchestrator run that checkpoints the results.
"""

from __future__ import annotations

import asyncio
import dataclasses
import itertools
import json
import re
from collections import deque
from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.clock import FakeClock, isoformat_z
from sit_review_agent.config import AssessSettings, AssessShard, EffectiveConfig, load_config
from sit_review_agent.context import RunContext
from sit_review_agent.errors import (
    AssessShardsFailed,
    LLMDeadlineError,
    LLMOverloadedError,
    LLMSchemaError,
    RegistryFrozenError,
)
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


# ------------------------------------------------------------------------------ assess shards


def shard_cfg(cfg: EffectiveConfig, groups: dict[str, list[str]]) -> EffectiveConfig:
    """``cfg`` with ``assess.shards`` replaced by ``groups`` and the run's criteria cut to theirs (a
    criterion in no group would form a shard of its own)."""
    settings = AssessSettings(shards=[AssessShard(name=n, criteria=c) for n, c in groups.items()])
    wanted = {c for cs in groups.values() for c in cs}
    criteria = cfg.criteria.model_copy(update={"criteria": [c for c in cfg.criteria.criteria if c.id in wanted]})
    return cfg.model_copy(update={"agent": cfg.agent.model_copy(update={"assess": settings}), "criteria": criteria})


def one_shard(cfg: EffectiveConfig) -> EffectiveConfig:
    return shard_cfg(cfg, {"all": cfg.criteria.ids()})


class ShardGateway(FakeGateway):
    """Answers each conversation from its own queue (``assess-0-s2`` and its retries ``-r1``...),
    optionally only once the test opens that conversation's gate (to fix the completion order)."""

    def __init__(self, answers: dict[str, list[FakeResponse]], *, gates: dict[str, asyncio.Event] | None = None,
                 **kw: Any) -> None:
        super().__init__({}, **kw)
        self.answers = {k: deque(v) for k, v in answers.items()}
        self.gates = gates or {}
        self.ended: list[str] = []

    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        base = re.sub(r"-r\d+$", "", request.conversation_id)
        if base in self.gates:
            await self.gates[base].wait()
        queue = self.answers.get(base) or self.answers.get(str(request.phase)) or deque()
        self.script[str(request.phase)] = deque([queue.popleft()]) if queue else deque()
        try:
            return await super().call(request)
        finally:
            self.ended.append(base)


def shard_finding(fid: str, rank: int, quote: str, page: int, section: str, criterion: str, n: int = 1,
                  **kw: Any) -> dict[str, Any]:
    """A doc-only finding (assess shards see no register): one ``NEW-`` doc item and an inference
    (temporary IDs ``NEW-<2n-1>`` and ``NEW-<2n>``, unique within one shard's answer)."""
    doc, inf = f"NEW-{2 * n - 1}", f"NEW-{2 * n}"
    return finding(fid, rank, doc_anchors=[anchor(quote, page, section)], criterion_ids=[criterion],
                   evidence=[{"evidence_id": doc, "source_type": "doc", "quote": quote, "supports_claim": True,
                              "derived_from": []},
                             {"evidence_id": inf, "source_type": "inference", "quote": f"Inference on {section}.",
                              "supports_claim": True, "derived_from": [doc]}],
                   recommendation={"issue": "x", "rationale": "y", "expected_benefit": "z", "change_summary": "c",
                                   "objective_refs": [], "supporting_evidence_ids": [inf], "verification": None},
                   **kw)


async def test_assess_shard_writes_drafts_meta_coverage_and_ledger(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, one_shard(cfg), {PhaseName.ASSESS: [FakeResponse(parsed=assess_output())]})
    pre = ctx.ledger.add_doc(doc_id=DOC_ID, page=6, section_ref="4.1", excerpt=Q_LOAD)       # EV-001
    ctx.state.budget.research_iterations = 2
    await AssessPhase().run(ctx)
    s = ctx.state

    risk, good = s.finding_drafts                     # listed in rank order; IDs in the shard's own rank order
    assert [f.id for f in s.finding_drafts] == ["FND-002", "FND-001"]
    assert (risk.rank, good.rank) == (1, 2) and good.confidence == 1.0         # merged rank: severity first
    assert risk.criterion_ids == ["claims_and_external_constraints"]
    # The shard saw no register: "EV-001" is an invented ID; its doc quote is located in the text and
    # reuses the identical entry; NEW-1 (doc) and NEW-2 (inference) are added; EV-404 is dropped.
    assert [c.evidence_id for c in risk.evidence] == [pre.evidence_id, "EV-002", "EV-003"]
    assert [c.source_type for c in risk.evidence] == [SourceType.DOC, SourceType.DOC, SourceType.INFERENCE]
    assert ctx.ledger.get("EV-003").derived_from == ["EV-001", "EV-002"]
    assert risk.recommendation is not None and risk.recommendation.supporting_evidence_ids == ["EV-003"]
    assert {e.evidence_id for e in EvidenceLedger.load(ctx.run_dir)} == {"EV-001", "EV-002", "EV-003"}  # journaled
    for draft in s.finding_drafts:                                             # verify can hydrate them
        f = hydrate(ctx, draft)
        assert all(isinstance(e, EvidenceItem) for e in f.evidence)

    meta = s.finding_meta["FND-002"]
    [req] = ctx.llm.calls
    # A shard sees no research: iteration 0 whatever research has done (conversation assess-0-s<k>).
    assert meta.created_phase is PhaseName.ASSESS and meta.last_call_id == "llm-0001" and meta.iteration == 0
    assert meta.model == "claude-opus-5-5" and meta.prompt_hash == sha256_text(brief_of(req))
    assert req.conversation_id == "assess-0-s1" and req.effort == cfg.effort_for(PhaseName.ASSESS)
    assert req.purpose == "assess" and "http" not in brief_of(req)

    [area] = s.sound_area_drafts                      # the duplicated model ID "F-1": first in rank order wins
    assert area.related_finding_ids == ["FND-001"] and area.evidence_ids == ["EV-002"]
    cov = {c.criterion_id: c for c in s.coverage}
    assert list(cov) == cfg.criteria.ids()                                     # one row per criterion, in order
    # The row's "F-1" maps to FND-001 (as above); FND-002 cites the criterion itself.
    assert cov["claims_and_external_constraints"].finding_ids == ["FND-001", "FND-002"]
    assert cov["security_and_privacy"].outcome == "no_issue"                   # "findings" with none attached
    assert cov["verifiability"].outcome == "findings" and cov["verifiability"].finding_ids == ["FND-001"]
    assert cov["design_intent"].outcome == "not_applicable" and "no coverage row" in cov["design_intent"].note
    assert any("dropped" in e.message for e in ctx.progress.events)


async def test_shard_briefs_carry_scope_and_group_only(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """Lever 8: a shard's brief has the document, its criterion group and the scope paragraph; no
    intent, registry, plan answers or evidence register, even when they exist."""
    shards = cfg.agent.assess.shards_for(cfg.criteria.ids())
    empty = {"findings": [], "sound_areas": [], "coverage": []}
    ctx = make_ctx(tmp_path, cfg, {PhaseName.ASSESS: [FakeResponse(parsed=empty) for _ in shards]})
    ctx.ledger.add_doc(doc_id=DOC_ID, page=6, section_ref="4.1", excerpt=Q_LOAD)
    ctx.state.review_inputs_found = ["a reviewer comment"]
    await AssessPhase().run(ctx)
    assert [r.conversation_id for r in ctx.llm.calls] == [f"assess-0-s{i}" for i in range(1, len(shards) + 1)]
    for req, shard in zip(ctx.llm.calls, shards, strict=True):
        brief = brief_of(req)
        assert "## Scope of this assessment" in brief and f"`{shard.name}`" in brief
        listed = brief.split("## Criteria of this assessment")[1]
        assert all(f"`{c}`" in listed for c in shard.criteria)
        assert not [c for c in cfg.criteria.ids() if c not in shard.criteria and f"`{c}`:" in listed]
        for absent in ("Design intent", "Decision registry", "Research questions", "Evidence register", "EV-001",
                       "a reviewer comment"):
            assert absent not in brief
    assert [c.outcome for c in ctx.state.coverage] == ["not_applicable"] * len(cfg.criteria.ids())


async def test_assess_persistent_refusal_completes(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, one_shard(cfg), {PhaseName.ASSESS: [
        FakeResponse(stop_reason="refusal", refusal_category="bio"),
        FakeResponse(stop_reason="refusal", refusal_category="bio")]})
    await AssessPhase().run(ctx)
    assert ctx.state.declined_sections == ["assess"] and ctx.state.finding_drafts == []
    assert [c.criterion_id for c in ctx.state.coverage] == cfg.criteria.ids()
    assert all("declined" in c.note for c in ctx.state.coverage)
    assert "bio" in ctx.state.degradations[0].event and "assess shard 1/1 (all)" in ctx.state.degradations[0].event
    assert [c.conversation_id for c in ctx.llm.calls] == ["assess-0-s1", "assess-0-s1-r1"]


async def test_one_failed_shard_leaves_a_partial_review(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """Shard 1 answers; shard 2 is declined twice, shard 3 truncated twice, shard 4 fails with a model
    error: a partial review with every failure disclosed, never a crash and never not_assessed."""
    groups = {"a": ["claims_and_external_constraints", "verifiability"], "b": ["design_intent"],
              "c": ["internal_consistency"], "d": ["security_and_privacy"]}
    c2 = shard_cfg(cfg, groups)
    # consumed in the stage's logical call order: the four shards' first calls in launch order
    # (call_model yields once before every call), then shard 2's reframed retry and shard 3's
    # truncation retry
    script = {PhaseName.ASSESS: [
        FakeResponse(parsed=assess_output()),
        FakeResponse(stop_reason="refusal"),
        FakeResponse(stop_reason="max_tokens"),
        FakeResponse(raises=LLMOverloadedError("529 after retries")),
        FakeResponse(stop_reason="refusal"),
        FakeResponse(stop_reason="max_tokens")]}
    ctx = make_ctx(tmp_path, c2, script)
    await AssessPhase().run(ctx)
    s = ctx.state
    assert len(s.finding_drafts) == 2 and s.declined_sections == []            # partial review, not "declined"
    cov = {c.criterion_id: c for c in s.coverage}
    assert cov["design_intent"].note == "not assessed: the model declined the assess call"
    assert cov["internal_consistency"].note.startswith("not assessed: the assess answer was truncated twice")
    assert cov["security_and_privacy"].note == "not assessed: the assess call failed"
    events = [d.event for d in s.degradations]
    assert any(e.startswith("the model declined assess shard 2/") for e in events)
    assert any(e.startswith("assess shard 3/") and "truncated twice" in e for e in events)
    assert any(e.startswith("assess shard 4/") and "LLMOverloadedError" in e for e in events)
    from sit_review_agent.phases.report import assessment_missing

    assert not [e for e in events if e.startswith("out of time before assessment")]
    assert s.finding_drafts and assessment_missing(events, s.declined_sections) in (None, "truncated")


async def test_a_cut_shard_keeps_its_finished_findings(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """W1's runtime raises LLMDeadlineError with the finished items at the stage limit: each item is
    validated on its own; the shard's criteria without a finding are not assessed; disclosed."""
    c2 = shard_cfg(cfg, {"a": ["claims_and_external_constraints", "verifiability", "security_and_privacy"]})
    kept = finding("FND-001", 1, criterion_ids=["claims_and_external_constraints"])
    cut = LLMDeadlineError("cut at the stage 1 limit", call_id="llm-0007",
                           partial={"findings": [kept, {"id": "FND-002", "rank": 2}]})
    ctx = make_ctx(tmp_path, c2, {PhaseName.ASSESS: [FakeResponse(raises=cut)]})
    await AssessPhase().run(ctx)
    s = ctx.state
    assert [f.title for f in s.finding_drafts] == [kept["title"]]
    cov = {c.criterion_id: c for c in s.coverage}
    assert cov["claims_and_external_constraints"].outcome == "findings"
    assert cov["verifiability"].note == cov["security_and_privacy"].note == \
        "not assessed: out of time before assessment (stage 1 limit)"
    [d] = s.degradations
    assert d.type is DegradationType.BUDGET_OR_DEADLINE_HIT and "1 finished finding(s) kept" in d.event
    # the disclosure names the shard and the cut call (verifier B)
    assert d.event.startswith("assess shard 1/1 (a) was cut by the stage 1 limit")
    assert d.event.endswith("(cut call llm-0007)")
    assert "verifiability, security_and_privacy" in d.impact
    assert not d.event.startswith("out of time before assessment")           # the design was assessed


async def test_a_shard_cut_while_repeating_keeps_its_complete_answer(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """Shard 3 of ``sit_sample_ui_2``: a complete answer (13 findings, 2 sound areas, 2 coverage rows),
    then the model wrote it again and the stage 1 limit came during the repeat. The gateway keeps the
    complete answer (``partial_complete``), not the half-written repeat, and the disclosure says so."""
    crit = ["claims_and_external_constraints", "verifiability"]
    c2 = shard_cfg(cfg, {"a": crit})
    findings = [finding(f"FND-{i:03d}", i, title=f"Finding {i}", criterion_ids=[crit[i % 2]]) for i in range(1, 14)]
    area = assess_output()["sound_areas"][0]
    answer = {"findings": findings, "sound_areas": [area, {**area, "section_refs": ["11.2"]}],
              "coverage": [{"criterion_id": c, "outcome": "findings", "finding_ids": ["FND-001"], "note": "n"}
                           for c in crit]}
    cut = LLMDeadlineError("cut at the stage 1 limit", call_id="llm-0005", partial=answer, partial_complete=True)
    assert cut.salvaged_items == 17
    ctx = make_ctx(tmp_path, c2, {PhaseName.ASSESS: [FakeResponse(raises=cut)]})
    await AssessPhase().run(ctx)
    s = ctx.state
    assert len(s.finding_drafts) == 13 and len(s.sound_area_drafts) == 2
    cov = {c.criterion_id: c for c in s.coverage}
    assert set(cov) == set(crit) and all(c.outcome == "findings" for c in cov.values())
    [d] = s.degradations
    assert d.type is DegradationType.BUDGET_OR_DEADLINE_HIT
    assert d.event.startswith("assess shard 1/1 (a) ended at the stage 1 limit at ")
    assert "after a complete answer" in d.event
    assert "the complete answer was kept: 13 finding(s), 2 sound area(s), 2 coverage row(s)" in d.event
    assert d.event.endswith("(cut call llm-0005)") and "only its unfinished repeat was lost" in d.impact


def _failing(reason: str) -> list[FakeResponse]:
    """The answers that leave one shard without an assessment for ``reason``."""
    if reason == "deadline":
        return [FakeResponse(raises=LLMDeadlineError("cut at the stage 1 limit"))]
    stop = "max_tokens" if reason == "truncated" else "refusal"
    return [FakeResponse(stop_reason=stop), FakeResponse(stop_reason=stop)]


@pytest.mark.parametrize("reason", ["deadline", "truncated", "declined"])
async def test_not_assessed_only_when_no_shard_assessed(tmp_path: Path, cfg: EffectiveConfig, reason: str) -> None:
    """The three not-assessed reasons, now when every shard failed that way (one stage-level disclosure)."""
    from sit_review_agent.phases.report import assessment_missing

    c2 = shard_cfg(cfg, {"a": ["design_intent"], "b": ["verifiability"]})
    ctx = make_ctx(tmp_path, c2, {PhaseName.ASSESS: [*_failing(reason), *_failing(reason)]})
    await AssessPhase().run(ctx)
    events = [d.event for d in ctx.state.degradations]
    assert assessment_missing(events, ctx.state.declined_sections) == reason
    assert ctx.state.finding_drafts == [] and len(events) == 3            # one per shard, one for the stage


async def test_one_assessed_shard_is_enough_to_assess(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """A shard that checked its criteria and found nothing is an assessment: no not-assessed disclosure."""
    from sit_review_agent.phases.report import assessment_missing

    c2 = shard_cfg(cfg, {"a": ["design_intent"], "b": ["verifiability"]})
    nothing = {"findings": [], "sound_areas": [], "coverage": [{"criterion_id": "design_intent", "outcome": "no_issue",
                                                                "finding_ids": [], "note": "checked"}]}
    ctx = make_ctx(tmp_path, c2, {PhaseName.ASSESS: [FakeResponse(parsed=nothing), *_failing("deadline")]})
    await AssessPhase().run(ctx)
    events = [d.event for d in ctx.state.degradations]
    assert not [e for e in events if e.startswith("out of time before assessment")]
    assert assessment_missing(events, ctx.state.declined_sections) is None


async def test_every_shard_failing_with_a_model_error_stops_the_run(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """AssessShardsFailed: an LLMError with the first shard's exit code (3) and cause, naming every
    shard; the orchestrator writes the partial run record for it (robustness LLM-03, persistent)."""
    c2 = shard_cfg(cfg, {"a": ["design_intent"], "b": ["verifiability"]})
    ctx = make_ctx(tmp_path, c2, {PhaseName.ASSESS: [FakeResponse(raises=LLMOverloadedError("529")),
                                                     FakeResponse(raises=LLMOverloadedError("529"))]})
    with pytest.raises(AssessShardsFailed) as info:
        await AssessPhase().run(ctx)
    exc = info.value
    assert int(exc.exit_code) == 3 and isinstance(exc.cause, LLMOverloadedError) and exc.phase == "assess"
    assert [(i, name) for i, name, _ in exc.shards] == [(1, "a"), (2, "b")]
    assert str(exc).startswith("every assess shard failed (2 of 2)") and "LLMOverloadedError" in str(exc)


async def test_delta_mode_sets_reassessment(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, one_shard(cfg), {PhaseName.ASSESS: [FakeResponse(parsed=assess_output())]},
                   review_mode=ReviewMode.DELTA)
    await AssessPhase().run(ctx)
    assert all(f.reassessment is not None and f.reassessment.status.value == "new_in_update"
               for f in ctx.state.finding_drafts)
    assert "Re-review of an updated document" in brief_of(ctx.llm.calls[0])


# ------------------------------------------------------------------------------ determinism


GROUPS = {"g1": ["claims_and_external_constraints"], "g2": ["verifiability"], "g3": ["internal_consistency"]}
SHARD_ANSWERS = {
    "assess-0-s1": {"findings": [shard_finding("FND-001", 1, Q_NOTIFY, 11, "6.2", "claims_and_external_constraints",
                                               title="Quota")], "sound_areas": [], "coverage": []},
    "assess-0-s2": {"findings": [shard_finding("FND-001", 1, Q_A11Y, 18, "11.3", "verifiability", title="A11y",
                                               severity="medium")], "sound_areas": [], "coverage": []},
    "assess-0-s3": {"findings": [shard_finding("FND-001", 2, Q_LOAD, 6, "4.1", "internal_consistency", title="Load",
                                               severity="low"),
                                 shard_finding("FND-002", 1, Q_OVERVIEW, 2, "1", "internal_consistency", n=2,
                                               title="Overview", severity="critical")],
                    "sound_areas": [], "coverage": []},
}


class LedgerResearch:
    """Research that writes two ledger entries while the shards are still running."""

    name = PhaseName.RESEARCH

    async def run(self, ctx: RunContext) -> RunContext:
        ctx.ledger.add_doc(doc_id=DOC_ID, page=19, section_ref="20", excerpt=Q_D3)
        await asyncio.sleep(0)
        ctx.ledger.add_doc(doc_id=DOC_ID, page=6, section_ref="4.1", excerpt="research saw this")
        return ctx


def _orders() -> list[tuple[str, ...]]:
    convs = ["understand-0", "plan-0", "assess-0-s1", "assess-0-s2", "assess-0-s3"]
    return list(itertools.permutations(convs))


@pytest.mark.parametrize("order", _orders(), ids=lambda o: ">".join(c[-2:] for c in o))
async def test_finding_and_ledger_ids_do_not_depend_on_completion_order(tmp_path: Path, cfg: EffectiveConfig,
                                                                        order: tuple[str, ...]) -> None:
    c3 = shard_cfg(cfg, GROUPS)
    gates = {c: asyncio.Event() for c in order}
    answers = {"understand-0": [FakeResponse(parsed=understand_output())],
               "plan-0": [FakeResponse(parsed=plan_output(cfg.criteria.ids()))],
               **{k: [FakeResponse(parsed=v)] for k, v in SHARD_ANSWERS.items()}}
    ctx = make_ctx(tmp_path / "-".join(order), c3, {})
    gw = ShardGateway(answers, gates=gates, run_dir=ctx.run_dir, clock=ctx.clock)
    ctx.llm = gw
    phases: dict[PhaseName, Any] = {p: _Noop(p) for p in PHASE_ORDER}
    phases.update({PhaseName.UNDERSTAND: UnderstandPhase(), PhaseName.PLAN: PlanPhase(),
                   PhaseName.RESEARCH: LedgerResearch(), PhaseName.ASSESS: AssessPhase()})
    run = asyncio.create_task(Orchestrator(phases).run(ctx))
    for conv in order:                                       # each call ends only after the previous one
        gates[conv].set()
        for _ in range(200):
            await asyncio.sleep(0)
            if conv in gw.ended:
                break
        assert conv in gw.ended, f"{conv} did not end"
    ctx = await run
    assert gw.ended == list(order)
    got = {f.id: (f.title, f.rank, [c.evidence_id for c in f.evidence]) for f in ctx.state.finding_drafts}
    assert got == {"FND-001": ("Quota", 2, ["EV-003", "EV-004"]), "FND-002": ("A11y", 3, ["EV-005", "EV-006"]),
                   "FND-003": ("Overview", 1, ["EV-007", "EV-009"]), "FND-004": ("Load", 4, ["EV-008", "EV-010"])}
    ledger = [(e.evidence_id, e.excerpt or e.statement) for e in ctx.ledger]
    assert [x[0] for x in ledger] == [f"EV-{i:03d}" for i in range(1, 11)]
    assert ledger[:2] == [("EV-001", Q_D3), ("EV-002", "research saw this")]  # research first, then shards in order
    assert ledger[2][1] == Q_NOTIFY and ledger[4][1] == Q_A11Y and ledger[6][1] == Q_OVERVIEW


async def test_merge_orders_the_shards_itself(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """``merge`` sorts its results by shard index, so a caller that hands them over in completion
    order gets the same finding and ledger IDs (the orchestrator passes them in plan order today)."""
    c3 = shard_cfg(cfg, GROUPS)
    got = []
    for name, flip in (("fwd", False), ("rev", True)):
        ctx = make_ctx(tmp_path / name, c3, {})
        ctx.llm = ShardGateway({k: [FakeResponse(parsed=v)] for k, v in SHARD_ANSWERS.items()},
                               run_dir=ctx.run_dir, clock=ctx.clock)
        phase = AssessPhase()
        results = await phase.run_shards(ctx)
        phase.merge(ctx, list(reversed(results)) if flip else results)
        got.append(([(f.id, f.title) for f in ctx.state.finding_drafts],
                    [(e.evidence_id, e.excerpt) for e in ctx.ledger]))
    assert got[0] == got[1] and got[0][0]


# ------------------------------------------------------------------------------ refine


def keep(fid: str, rank: int, severity: str | None, disposition: str, reason: str = "checked",
         **kw: Any) -> dict[str, Any]:
    return {"finding_id": fid, "action": "keep", "merge_into": None, "rank": rank, "severity": severity,
            "disposition": disposition, "affected_decisions": [], "added_evidence": [], "next_step": None,
            "reason": reason, **kw}


def gone(fid: str, action: str, into: str | None = None, reason: str = "duplicate") -> dict[str, Any]:
    return {"finding_id": fid, "action": action, "merge_into": into, "rank": None, "severity": None,
            "disposition": None, "affected_decisions": [], "added_evidence": [], "next_step": None, "reason": reason}


async def _merged(tmp_path: Path, cfg: EffectiveConfig, refine: list[FakeResponse]) -> RunContext:
    """Three merged findings (two shards) ready for refine: FND-001 risk (high), FND-002 strength,
    FND-003 a second risk (medium, criterion security_and_privacy)."""
    c2 = shard_cfg(cfg, {"a": ["claims_and_external_constraints", "verifiability"], "b": ["security_and_privacy"]})
    second = {"findings": [shard_finding("X", 1, Q_LOAD, 6, "4.1", "security_and_privacy", title="Second issue",
                                         severity="medium")], "sound_areas": [], "coverage": []}
    ctx = make_ctx(tmp_path, c2, {PhaseName.ASSESS: [FakeResponse(parsed=assess_output()), FakeResponse(parsed=second)],
                                  PhaseName.REFINE: refine})
    await AssessPhase().run(ctx)
    assert [(f.id, f.kind.value) for f in ctx.state.finding_drafts] == [
        ("FND-002", "risk"), ("FND-003", "risk"), ("FND-001", "strength")]
    return ctx


async def test_refine_applies_keep_merge_withdraw_with_history(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ev = "EV-001"
    out = {"revisions": [
        keep("FND-002", 1, "medium", "refinement_now", reason="impact is bounded by the retry queue",
             affected_decisions=[{"registry_id": "AD-001", "relation": "refines", "justification": "j"}]),
        gone("FND-003", "merge", "FND-002", reason="same quota issue"),
        gone("FND-001", "withdraw", reason="covered elsewhere")]}
    ctx = await _merged(tmp_path, cfg, [FakeResponse(parsed=out)])
    ctx.state.plan = None
    await RefinePhase().run(ctx)
    s = ctx.state
    [f] = s.finding_drafts
    assert f.id == "FND-002" and f.rank == 1 and f.severity.value == "medium"
    assert f.affected_decisions[0].registry_id == "AD-001"
    assert f.criterion_ids == ["claims_and_external_constraints", "security_and_privacy"]   # merge moves criteria
    m = s.finding_meta["FND-002"]
    assert m.last_phase is PhaseName.REFINE and PROVENANCE_PHASE[m.last_phase].value == "revise"
    assert m.history[-1].changed_fields["severity"] == ["high", "medium"]
    assert m.history[-1].note == "revised: impact is bounded by the retry queue"
    assert s.finding_meta["FND-003"].history[-1].note == "merged into FND-002: same quota issue"
    assert s.finding_meta["FND-001"].history[-1].note == "withdrawn: covered elsewhere"
    cov = {c.criterion_id: c for c in s.coverage}
    assert cov["security_and_privacy"].finding_ids == ["FND-002"]             # the merged finding's criterion
    assert cov["verifiability"].outcome == "no_issue"                         # its only finding was withdrawn
    assert s.sound_area_drafts[0].related_finding_ids == []                   # FND-001 withdrawn
    req = ctx.llm.calls[-1]
    assert req.conversation_id == "refine-0" and req.purpose == "refine"
    brief = brief_of(req)
    assert '"id": "FND-003"' in brief and "## Revision rules" in brief and "## Design intent" in brief
    assert "## Research questions and answers" in brief and f"{ev} [doc]" in brief
    assert len(s.llm_calls["refine"]) == 1


async def test_refine_rejects_an_unexplained_conclusion_change(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """BEH-10: a keep that changes severity with no reason and no added evidence keeps the draft's value."""
    out = {"revisions": [keep("FND-002", 1, "low", "refinement_now", reason=""),
                         keep("FND-003", 2, "medium", "refinement_now"),
                         keep("FND-001", 3, None, "no_change")]}
    ctx = await _merged(tmp_path, cfg, [FakeResponse(parsed=out)])
    await RefinePhase().run(ctx)
    f = next(x for x in ctx.state.finding_drafts if x.id == "FND-002")
    assert f.severity.value == "high"
    assert any("rejected" in h.note and "BEH-10" in h.note for h in ctx.state.finding_meta["FND-002"].history)
    assert any("rejected (no revision reason" in e.message for e in ctx.progress.events)


async def test_refine_revisions_that_break_the_rules_get_one_repair_then_the_fallback(
        tmp_path: Path, cfg: EffectiveConfig) -> None:
    bad = {"revisions": [keep("FND-002", 1, "high", "refinement_now"), gone("FND-003", "merge", "FND-001"),
                         gone("FND-001", "withdraw")]}          # merge into a withdrawn finding, twice
    ctx = await _merged(tmp_path, cfg, [FakeResponse(parsed=bad), FakeResponse(parsed=bad)])
    before = [f.model_dump() for f in ctx.state.finding_drafts]
    await RefinePhase().run(ctx)
    first, repair = ctx.llm.calls[-2:]
    assert repair.conversation_id == "refine-0-r1" and repair.purpose == "refine:schema_repair"
    assert "merge into FND-001, which is not kept" in brief_of(repair)
    assert [f.model_dump() for f in ctx.state.finding_drafts] == before     # merged findings stand, severity order
    [d] = [d for d in ctx.state.degradations if "refine revisions could not be applied" in d.event]
    assert "severity and confidence order" in d.impact
    assert len(ctx.state.llm_calls["refine"]) == 2


async def test_refine_repaired_answer_is_applied(tmp_path: Path, cfg: EffectiveConfig) -> None:
    bad = {"revisions": [keep("FND-002", 1, "high", "refinement_now")]}       # two findings without a revision
    good = {"revisions": [keep("FND-002", 1, "high", "refinement_now"), keep("FND-003", 2, "medium",
                                                                             "refinement_now"),
                          keep("FND-001", 3, None, "no_change")]}
    ctx = await _merged(tmp_path, cfg, [FakeResponse(parsed=bad), FakeResponse(parsed=good)])
    await RefinePhase().run(ctx)
    assert [f.id for f in ctx.state.finding_drafts] == ["FND-002", "FND-003", "FND-001"]
    assert not [d for d in ctx.state.degradations if "refine" in d.event]


async def test_refine_cut_keeps_the_merged_findings_in_severity_order(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = await _merged(tmp_path, cfg, [FakeResponse(raises=LLMDeadlineError("cut at refine_end"))])
    before = [f.model_dump() for f in ctx.state.finding_drafts]
    await RefinePhase().run(ctx)
    assert [f.model_dump() for f in ctx.state.finding_drafts] == before
    assert [f.rank for f in ctx.state.finding_drafts] == [1, 2, 3]
    [d] = [d for d in ctx.state.degradations if d.event.startswith("the refine call was cut")]
    assert d.type is DegradationType.BUDGET_OR_DEADLINE_HIT and "severity and confidence order" in d.impact


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
              PhaseName.REFINE: [FakeResponse(parsed={"revisions": [gone("FND-001", "withdraw"),
                                                                    gone("FND-002", "withdraw")]})]}
    ctx = make_ctx(tmp_path, one_shard(cfg), script)
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
    stored = sorted(p.name for p in (ctx.run_dir.root / "shards").iterdir())
    assert stored == ["01-all.json"]                                           # the finished shard, for resume


@pytest.mark.parametrize(("slack", "repairs"), [(61.0, True), (60.0, False)])
async def test_anchor_repair_call_needs_more_than_60_s_of_slack(tmp_path: Path, slack: float, repairs: bool) -> None:
    """Design section 4: verify makes its one repair call only when more than 60 s remain before the
    verify and verdict reserve; otherwise the unresolved anchors stay unresolved, disclosed."""
    from sit_review_agent.phases.verify import VerifyPhase
    from test_ingest_verify_report import Q_LOAD as R_LOAD
    from test_ingest_verify_report import Q_MAIL, REPAIR, add_external, draft, ext_cite, ingested, meta
    from test_ingest_verify_report import anchor as r_anchor

    ctx = await ingested(tmp_path, {"verify": [REPAIR]})
    ev = add_external(ctx)
    ctx.state.finding_drafts = [draft("FND-001", anchors=[r_anchor("6.2", 11, Q_MAIL), r_anchor("4.1", 2, R_LOAD)],
                                      evidence=[ext_cite(ev)])]
    ctx.state.finding_meta = {"FND-001": meta("FND-001")}
    sr = ctx.config.stop_rules
    ctx.clock.advance(sr.deadline_seconds - sr.report_reserve_seconds - slack)  # type: ignore[attr-defined]
    ctx = await VerifyPhase().run(ctx)
    assert bool(ctx.llm.calls) is repairs
    skipped = [d for d in ctx.state.degradations if d.event.startswith("anchor repair call skipped")]
    assert bool(skipped) is not repairs


def test_llm_result_type_is_what_phases_consume() -> None:
    assert {f.name for f in dataclasses.fields(LLMResult)} >= {"call_id", "model", "parsed", "usage", "fallback"}
