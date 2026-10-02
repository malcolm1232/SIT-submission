"""Structured-output types: what the model emits in each phase (``output_schema`` of an
:class:`~sit_review_agent.llm.gateway.LLMRequest`).

These are deliberately **constraint-free** drafts (no ``pattern``, ``min_length``, numeric bounds):
Claude structured outputs reject or strip those (spec/README.md "LLM-facing schema"). Code checks
them after parsing: the ``verify`` phase hydrates drafts into canonical
:class:`~sit_review_agent.models.Finding` objects (evidence from the ledger, provenance from the
call log) and validates against the full spec. Differences from the canonical objects:

* the model never writes ``url_or_citation`` or ``retrieved_at`` (``readOnly``), nor ``provenance``;
* findings carry ``criterion_ids`` (which configured criterion produced them; kept in run state for
  ``explain``, stripped from the Review because ``Finding`` admits no extra keys);
* IDs the model proposes (``FND-``, ``RQ-``) are checked and renumbered in code if needed.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from sit_review_agent.models import (
    Category,
    DecisionRelation,
    Disposition,
    Kind,
    ReassessmentStatus,
    RegistryEntryType,
    Severity,
    SourceType,
    VerdictLabel,
)


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- shared parts


class DocAnchorDraft(Draft):
    doc_id: str
    section_ref: str
    requirement_ids: list[str]
    quote: str
    page: int | None


class RefTextDraft(Draft):
    ref: str | None
    text: str


class EvidenceCitation(Draft):
    """Evidence cited by ledger ID only (ADR-007). ``quote`` is the passage relied on."""

    evidence_id: str
    source_type: SourceType
    quote: str | None
    supports_claim: bool
    derived_from: list[str]


class RecommendationDraft(Draft):
    issue: str
    rationale: str
    expected_benefit: str
    change_summary: str
    objective_refs: list[str]
    supporting_evidence_ids: list[str]
    verification: str | None


class NextStepDraft(Draft):
    owner: str
    action: str


class AffectedDecisionDraft(Draft):
    registry_id: str
    relation: DecisionRelation
    justification: str


class ReassessmentDraft(Draft):
    prior_finding_id: str | None
    status: ReassessmentStatus
    note: str | None


class FindingDraft(Draft):
    id: str
    rank: int
    kind: Kind
    category: Category | None
    severity: Severity | None
    confidence: float
    disposition: Disposition
    secondary_dispositions: list[Disposition]
    title: str
    statement: str
    doc_anchors: list[DocAnchorDraft]
    evidence: list[EvidenceCitation]
    recommendation: RecommendationDraft | None
    no_change_rationale: str | None
    next_step: NextStepDraft | None
    affected_decisions: list[AffectedDecisionDraft]
    acknowledged_in_doc: bool
    tags: list[str]
    reassessment: ReassessmentDraft | None
    criterion_ids: list[str]


class SoundAreaDraft(Draft):
    section_refs: list[str]
    why_sound: str
    doc_anchors: list[DocAnchorDraft]
    evidence_ids: list[str]
    related_finding_ids: list[str]


# --------------------------------------------------------------------------- understand


class IntentSummaryDraft(Draft):
    statement: str
    objectives: list[RefTextDraft]
    constraints: list[RefTextDraft]
    key_assumptions: list[RefTextDraft]
    doc_anchors: list[DocAnchorDraft]


class RegistryEntryDraft(Draft):
    """An approved decision, pending decision, constraint or key requirement found in the doc.
    Code assigns ``AD-nnn`` IDs and freezes the registry after ``understand`` (INV-10)."""

    type: RegistryEntryType
    doc_ref: str
    statement: str
    doc_anchor: DocAnchorDraft


class UnderstandOutput(Draft):
    intent_summary: IntentSummaryDraft
    registry: list[RegistryEntryDraft]
    document_version: str | None
    review_inputs_found: list[str]        # comments or claimed fixes from other reviewers (lab §1.5)


# --------------------------------------------------------------------------- plan


Capability = Literal["search", "scholarly", "browse", "none"]


class ResearchQuestionDraft(Draft):
    id: str                                # RQ-nnn
    criterion_id: str
    question: str
    rationale: str
    needs_external: bool
    capability: Capability                 # fixed action types (ADR-001, audit C18)
    queries: list[str]
    section_refs: list[str]


class CriterionSkip(Draft):
    criterion_id: str
    reason: str


class PlanOutput(Draft):
    questions: list[ResearchQuestionDraft]
    criteria_skipped: list[CriterionSkip]


# --------------------------------------------------------------------------- research


class QuestionAnswer(Draft):
    question_id: str
    status: Literal["answered", "partial", "unanswered", "conflicting"]
    summary: str
    evidence_ids: list[str]


class ResearchOutput(Draft):
    """Final turn of the research tool loop (one per iteration)."""

    answers: list[QuestionAnswer]
    stop_requested: bool                   # model's own "enough evidence" vote; code decides
    stop_rationale: str


# --------------------------------------------------------------------------- assess / refine


class CriterionCoverage(Draft):
    """Coverage map row: every configured criterion is reported, including "checked, no issue"."""

    criterion_id: str
    outcome: Literal["findings", "no_issue", "not_applicable"]
    finding_ids: list[str]
    note: str


class AssessOutput(Draft):
    findings: list[FindingDraft]
    sound_areas: list[SoundAreaDraft]
    coverage: list[CriterionCoverage]


class RevisionNote(Draft):
    finding_id: str
    change: Literal["revised", "withdrawn", "merged", "added", "unchanged"]
    reason: str
    evidence_ids: list[str]


class RefineOutput(Draft):
    findings: list[FindingDraft]
    revisions: list[RevisionNote]


# --------------------------------------------------------------------------- verify


class AnchorRepair(Draft):
    owner_id: str                          # FND-/SA-/AD- ID, or "intent"
    anchor_index: int
    doc_anchor: DocAnchorDraft


class AnchorRepairOutput(Draft):
    """The single repair turn for unresolved anchors (ADR-007)."""

    repairs: list[AnchorRepair]


# --------------------------------------------------------------------------- report


class VerdictConditionDraft(Draft):
    text: str
    finding_ids: list[str]


class ObjectiveVerdictDraft(Draft):
    objective_ref: str
    label: VerdictLabel
    finding_ids: list[str]


class VerdictDraft(Draft):
    label: VerdictLabel
    rationale: str
    confidence: float
    conditions: list[VerdictConditionDraft]
    per_objective: list[ObjectiveVerdictDraft]
    what_would_change_it: str | None


class UnresolvedDraft(Draft):
    text: str
    finding_ids: list[str]
    next_step: NextStepDraft | None


class LimitationDraft(Draft):
    text: str
    degradation_ids: list[str]


class ReportOutput(Draft):
    verdict: VerdictDraft
    unresolved: list[UnresolvedDraft]
    limitations: list[LimitationDraft]


PHASE_OUTPUT_TYPES: dict[str, type[Draft]] = {
    "understand": UnderstandOutput,
    "plan": PlanOutput,
    "research": ResearchOutput,
    "assess": AssessOutput,
    "refine": RefineOutput,
    "verify": AnchorRepairOutput,
    "report": ReportOutput,
}


def llm_facing_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema actually sent for ``model``: Pydantic's schema with the keywords structured
    outputs reject stripped (``minLength``, ``maxLength``, ``minimum``, ``maximum``,
    ``minItems``, ``maxItems``, ``pattern``, ``format``) and ``additionalProperties: false`` on
    every object. Used for ``count_tokens`` and logging; the SDK's ``output_format`` does its own
    transformation. Which keywords the API accepts is UNVERIFIED (spec/README.md)."""
    raise NotImplementedError("phase 1: llm_facing_schema (workstream A)")
