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

from enum import StrEnum
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


# Deprecated (latency redesign W0, 2026-10-03): the refine answer that re-emits every finding.
# W2 removes it when phases/refine.py moves to RefineRevisionsOutput.
class RevisionNote(Draft):
    finding_id: str
    change: Literal["revised", "withdrawn", "merged", "added", "unchanged"]
    reason: str
    evidence_ids: list[str]


# Deprecated (latency redesign W0, 2026-10-03): W2 removes it with RevisionNote.
class RefineOutput(Draft):
    findings: list[FindingDraft]
    revisions: list[RevisionNote]


class RevisionAction(StrEnum):
    """What refine does with one merged draft finding (latency redesign, design section 4)."""

    KEEP = "keep"
    MERGE = "merge"
    WITHDRAW = "withdraw"


class FindingRevisionDraft(Draft):
    """One revision per draft finding: a patch that code applies, never the finding re-emitted.

    Every key is required and every value is final, so code applies it exactly:

    * ``keep``: ``rank`` (1..n over the kept findings), ``severity`` (null is the final value for a
      finding without a severity, never "unchanged") and ``disposition`` are the finding's values
      after refine; ``affected_decisions`` replaces the draft's list (registry links, which assess no
      longer makes); ``added_evidence`` is appended to the draft's evidence (research results);
      ``merge_into`` is null.
    * ``merge``: the finding is folded into ``merge_into``, which must be a kept finding; every other
      field is null or empty.
    * ``withdraw``: the finding is dropped; every other field is null or empty.

    :func:`revision_problems` lists what breaks these rules; the refine phase decides what to do.
    """

    finding_id: str
    action: RevisionAction
    merge_into: str | None
    rank: int | None
    severity: Severity | None
    disposition: Disposition | None
    affected_decisions: list[AffectedDecisionDraft]
    added_evidence: list[EvidenceCitation]
    reason: str


class RefineRevisionsOutput(Draft):
    """The refine answer of the latency redesign: one global call, one revision per finding."""

    revisions: list[FindingRevisionDraft]


def revision_problems(out: RefineRevisionsOutput, finding_ids: list[str]) -> list[str]:
    """Every rule of :class:`FindingRevisionDraft` that ``out`` breaks against the merged draft
    findings ``finding_ids``; empty when code can apply it exactly. Checks: one revision per known
    finding, per-action field rules, merges only into a known kept finding (which also rules out a
    merge into itself, chains and cycles), and kept ranks forming 1..n."""
    problems: list[str] = []
    known = set(finding_ids)
    by_id: dict[str, list[FindingRevisionDraft]] = {}
    for r in out.revisions:
        if r.finding_id not in known:
            problems.append(f"revision for unknown finding {r.finding_id}")
            continue
        by_id.setdefault(r.finding_id, []).append(r)
    for fid in finding_ids:
        n = len(by_id.get(fid, []))
        if n == 0:
            problems.append(f"no revision for {fid}")
        elif n > 1:
            problems.append(f"{fid} has {n} revisions")
    kept = {fid for fid, rs in by_id.items() if len(rs) == 1 and rs[0].action is RevisionAction.KEEP}
    ranks: list[int] = []
    for r in out.revisions:
        if r.finding_id not in known:
            continue
        a = r.action.value
        if r.action is RevisionAction.KEEP:
            if r.merge_into is not None:
                problems.append(f"{r.finding_id} is keep but sets merge_into")
            if r.rank is None:
                problems.append(f"{r.finding_id} is keep without rank")
            else:
                ranks.append(r.rank)
            if r.disposition is None:
                problems.append(f"{r.finding_id} is keep without disposition")
            continue
        for field in ("rank", "severity", "disposition"):
            if getattr(r, field) is not None:
                problems.append(f"{r.finding_id} is {a} but sets {field}")
        for field in ("affected_decisions", "added_evidence"):
            if getattr(r, field):
                problems.append(f"{r.finding_id} is {a} but sets {field}")
        if r.action is RevisionAction.MERGE:
            if r.merge_into is None:
                problems.append(f"{r.finding_id} is merge without merge_into")
            elif r.merge_into == r.finding_id:
                problems.append(f"{r.finding_id} merges into itself")
            elif r.merge_into not in known:
                problems.append(f"{r.finding_id}: merge into unknown finding {r.merge_into}")
            elif r.merge_into not in kept:
                problems.append(f"{r.finding_id}: merge into {r.merge_into}, which is not kept")
        elif r.merge_into is not None:
            problems.append(f"{r.finding_id} is withdraw but sets merge_into")
    if sorted(ranks) != list(range(1, len(kept) + 1)):
        problems.append(f"ranks of kept findings must be 1..{len(kept)} with no gaps or repeats, got {sorted(ranks)}")
    return problems


# --------------------------------------------------------------------------- verify


class AnchorRepair(Draft):
    owner_id: str                          # FND-/SA-/AD- ID, or "intent"
    anchor_index: int
    doc_anchor: DocAnchorDraft


class AnchorRepairOutput(Draft):
    """The single repair turn for unresolved anchors (ADR-007)."""

    repairs: list[AnchorRepair]


# --------------------------------------------------------------------------- report


class AssessedVerdictLabel(StrEnum):
    """The verdict labels the model may choose. ``VerdictLabel.NOT_ASSESSED`` is left out on purpose:
    it is set by code only, when the run produced no assessment (``phases.report``), so the
    LLM-facing schema never offers it and a draft that carries it fails validation."""

    FIT = VerdictLabel.FIT.value
    FIT_WITH_CONDITIONS = VerdictLabel.FIT_WITH_CONDITIONS.value
    NOT_FIT = VerdictLabel.NOT_FIT.value


class VerdictConditionDraft(Draft):
    text: str
    finding_ids: list[str]


class ObjectiveVerdictDraft(Draft):
    objective_ref: str
    label: AssessedVerdictLabel
    finding_ids: list[str]


class VerdictDraft(Draft):
    label: AssessedVerdictLabel
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


# Deprecated (latency redesign W0, 2026-10-03): the verdict call that also writes unresolved items
# and limitations. W2 removes it (with UnresolvedDraft and LimitationDraft if unused) when
# phases/report.py moves to VerdictOutput.
class ReportOutput(Draft):
    verdict: VerdictDraft
    unresolved: list[UnresolvedDraft]
    limitations: list[LimitationDraft]


class VerdictOutput(Draft):
    """The verdict call of the latency redesign: the verdict only; code writes unresolved items and
    limitations (design section 9, decision 6)."""

    verdict: VerdictDraft


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
    every object. This is the schema actually sent (see the closing note below); which keywords
    the API accepts is UNVERIFIED (spec/README.md).

    Details (workstream A):

    * keywords are stripped only where they are schema keywords, never where they are property
      names (a field called ``format`` survives); ``enum``/``const``/``required`` values are copied;
    * also stripped: ``exclusiveMinimum``/``exclusiveMaximum``/``multipleOf``/``uniqueItems``/
      ``minProperties``/``maxProperties`` (same family) and the ``if``/``then``/``else`` rules;
    * ``$defs``/``$ref``, ``anyOf`` (including ``null`` branches), ``enum``, ``title`` and
      ``description`` are kept;
    * closing rule (identical to ``llm.claude_code._schema_for``): an object that declares
      ``properties`` or says nothing about extra keys gets ``additionalProperties: false``; an
      explicit map (``dict[str, X]`` -> ``additionalProperties: {schema}``) stays open.

    This is what :class:`~sit_review_agent.llm.gateway.AnthropicGateway` sends as
    ``output_config.format.schema`` and what ``ClaudeCodeGateway`` passes to ``--json-schema``.
    """
    return _llm_strip(model.model_json_schema())


#: JSON Schema keywords removed from the LLM-facing schema (see :func:`llm_facing_schema`).
_LLM_STRIPPED_KEYWORDS = frozenset({
    "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minItems", "maxItems", "uniqueItems", "minProperties", "maxProperties", "pattern", "format",
    "if", "then", "else",
})
#: Keywords whose value maps names to sub-schemas (the names are not keywords).
_LLM_SCHEMA_MAPS = frozenset({"properties", "$defs", "definitions", "patternProperties", "dependentSchemas"})
#: Keywords whose value is data, not a schema.
_LLM_DATA_KEYWORDS = frozenset({"enum", "const", "required", "examples", "default"})


def _llm_strip(node: Any) -> Any:
    if isinstance(node, list):
        return [_llm_strip(v) for v in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _LLM_STRIPPED_KEYWORDS:
            continue
        if key in _LLM_SCHEMA_MAPS and isinstance(value, dict):
            out[key] = {name: _llm_strip(sub) for name, sub in value.items()}
        elif key in _LLM_DATA_KEYWORDS:
            out[key] = value if not isinstance(value, dict | list) else _llm_copy(value)
        elif key == "allOf" and isinstance(value, list):
            kept = [_llm_strip(v) for v in value]
            kept = [v for v in kept if v != {}]
            if kept:
                out[key] = kept
        else:
            out[key] = _llm_strip(value)
    if out.get("type") == "object" and ("properties" in out or "additionalProperties" not in out):
        out["additionalProperties"] = False
    return out


def _llm_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _llm_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_llm_copy(v) for v in value]
    return value
