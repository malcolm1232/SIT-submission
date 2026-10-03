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

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict

from sit_review_agent.models import (
    NON_REFINEMENT_DISPOSITIONS,
    Category,
    DecisionRelation,
    Disposition,
    Kind,
    PriorFindingStatus,
    ReassessmentStatus,
    RegistryEntryType,
    Severity,
    SourceType,
    VerdictLabel,
    finding_rule_violations,
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


# Docstrings of the draft types are sent to the model as schema descriptions (Pydantic's
# ``description``): plain prose only, no reStructuredText roles or backticks
# (tests/test_llm_schema_descriptions.py). Notes for developers go in comments.


class EvidenceCitation(Draft):
    """Evidence cited by ledger ID only (ADR-007). The quote is the passage relied on."""

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
    Code assigns AD-nnn IDs and freezes the registry after the understand step (INV-10)."""

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


class RevisionAction(StrEnum):
    """What refine does with one merged draft finding (latency redesign, design section 4)."""

    KEEP = "keep"
    MERGE = "merge"
    WITHDRAW = "withdraw"


# revision_problems() lists what breaks the rules of FindingRevisionDraft; apply_revisions()
# applies a set that has none. The refine phase decides what to do with a set that has problems.
class FindingRevisionDraft(Draft):
    """One revision per draft finding: a patch that code applies, never the finding re-emitted.

    Every key is required and every value is final, so code applies it exactly:

    * keep: rank (1..n over the kept findings), severity (null is the final value for a finding
      without a severity, never "unchanged") and disposition are the finding's values after refine;
      affected_decisions replaces the draft's list (registry links, which assess no longer makes);
      added_evidence is appended to the draft's evidence (research results); merge_into is null.
      next_step (an owner and an action) is given only when the new disposition needs one
      (needs_investigation, needs_prototyping, needs_testing, governance_decision) and the finding
      has none; otherwise it is null.
    * merge: the finding is folded into merge_into, which must be a kept finding; every other field
      is null or empty. It leaves the review; its criteria count for the kept finding; nothing else
      moves (evidence the kept finding should gain goes in that finding's added_evidence).
    * withdraw: the finding is dropped; every other field is null or empty.
    """

    finding_id: str
    action: RevisionAction
    merge_into: str | None
    rank: int | None
    severity: Severity | None
    disposition: Disposition | None
    affected_decisions: list[AffectedDecisionDraft]
    added_evidence: list[EvidenceCitation]
    next_step: NextStepDraft | None
    reason: str


class PriorStatusDraft(Draft):
    """The status of a finding of the previous review that no kept finding carries forward: resolved,
    partially_addressed, still_open, or withdrawn_on_reassessment (you no longer assert it; the note
    gives the one-line reason)."""

    prior_finding_id: str
    status: PriorFindingStatus
    note: str


class RefineRevisionsOutput(Draft):
    """The refine answer of the latency redesign: one global call, one revision per finding; in a
    re-review also one prior status per finding of the previous review that no kept finding carries."""

    revisions: list[FindingRevisionDraft]
    # Optional so full-review answers and recordings made before 2026-10-03 still parse.
    prior_statuses: list[PriorStatusDraft] = []


def prior_status_problems(out: RefineRevisionsOutput, prior_ids: Sequence[str], carried: set[str]) -> list[str]:
    """What keeps ``out.prior_statuses`` from giving exactly one status to every prior finding in
    ``prior_ids`` that no kept finding carries (``carried``): a missing one, one given twice, one for
    an unknown ID or for a carried finding, and a withdrawal with no reason. Empty in a full review
    (no ``prior_ids``)."""
    problems: list[str] = []
    known = set(prior_ids)
    given: dict[str, int] = {}
    for p in out.prior_statuses:
        given[p.prior_finding_id] = given.get(p.prior_finding_id, 0) + 1
        if p.prior_finding_id not in known:
            problems.append(f"prior_statuses: {p.prior_finding_id} is not a finding of the previous review")
        elif p.prior_finding_id in carried:
            problems.append(f"prior_statuses: {p.prior_finding_id} is already carried forward by a kept finding's "
                            "reassessment; give no prior status for it")
        if p.status is PriorFindingStatus.WITHDRAWN_ON_REASSESSMENT and not p.note.strip():
            problems.append(f"prior_statuses: {p.prior_finding_id} is withdrawn without a one-line reason in note")
    problems += [f"prior_statuses: {pid} is given {n} times; give it exactly once" for pid, n in given.items() if n > 1]
    missing = [pid for pid in prior_ids if pid not in carried and pid not in given]
    if missing:
        problems.append("prior_statuses: no status for prior finding(s) " + ", ".join(missing) + " (no kept finding "
                        "carries them forward); give each resolved, partially_addressed, still_open or "
                        "withdrawn_on_reassessment with a one-line note")
    return problems


def revision_problems(out: RefineRevisionsOutput, finding_ids: list[str], *,
                      drafts: Mapping[str, FindingDraft] | None = None) -> list[str]:
    """Every rule of :class:`FindingRevisionDraft` that ``out`` breaks against the merged draft
    findings ``finding_ids``; empty when code can apply it exactly. Checks: one revision per known
    finding, per-action field rules, merges only into a known kept finding (which also rules out a
    merge into itself, chains and cycles), kept ranks forming 1..n, no evidence ID added twice, and a
    ``next_step`` only on a ``keep`` whose disposition needs one.

    With ``drafts`` (the merged drafts by ID; the refine phase always passes them) each kept finding
    is also checked as it will be after the revision: evidence it already cites is not added again,
    a ``next_step`` is not given to a draft that has one (a revision adds a step, it never replaces
    one), and the finding rules of the spec (``models.finding_rule_violations``) hold, so a null severity on
    a finding that needs one, a disposition the draft's recommendation, rationale or next step cannot
    support, or a ``challenges`` link with fewer than two evidence items is a problem here, not a
    finding dropped later in verify. Registry IDs are not checked here: verify drops a link to an
    unknown registry entry and records the change (``phases/verify.py``), as before."""
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
            elif r.next_step is not None and r.disposition not in NON_REFINEMENT_DISPOSITIONS:
                problems.append(f"{r.finding_id} sets next_step, but {r.disposition.value} needs none")
            added = [e.evidence_id for e in r.added_evidence]
            twice = sorted({e for e in added if added.count(e) > 1})
            if twice:
                problems.append(f"{r.finding_id} adds evidence {', '.join(twice)} more than once")
            draft = drafts.get(r.finding_id) if drafts is not None else None
            if draft is not None and r.next_step is not None and draft.next_step is not None:
                problems.append(f"{r.finding_id} sets next_step, but the draft already has one")
            if draft is not None and r.disposition is not None:
                cited = sorted({e.evidence_id for e in draft.evidence} & set(added))
                if cited:
                    problems.append(f"{r.finding_id} adds evidence {', '.join(cited)} it already cites")
                problems += [f"{r.finding_id} after keep: {p}"
                             for p in finding_rule_violations(cast(Any, _kept_draft(draft, r)))]
            continue
        for field in ("rank", "severity", "disposition", "next_step"):
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


def _kept_draft(draft: FindingDraft, r: FindingRevisionDraft) -> FindingDraft:
    """``draft`` after the ``keep`` revision ``r``: rank, severity, disposition and the decision links
    replaced, the added evidence appended, the revision's next step set when it gives one, every
    other field as the draft had it."""
    return draft.model_copy(deep=True, update={
        "rank": r.rank, "severity": r.severity, "disposition": r.disposition,
        "affected_decisions": [a.model_copy() for a in r.affected_decisions],
        "evidence": [*draft.evidence, *(e.model_copy() for e in r.added_evidence)],
        **({"next_step": r.next_step.model_copy()} if r.next_step is not None else {}),
    })


def apply_revisions(drafts: Sequence[FindingDraft], out: RefineRevisionsOutput) -> list[FindingDraft]:
    """The kept findings after ``out``, in rank order: the one exact meaning of a revision set. ``keep``
    replaces rank, severity, disposition and ``affected_decisions`` with the revision's values,
    appends ``added_evidence`` to the draft's evidence and sets ``next_step`` when given; ``merge``
    removes the finding and appends its ``criterion_ids`` (those the target lacks, in draft order)
    to the target's, so coverage still credits its criterion; ``withdraw`` removes the finding.
    ``drafts`` are not changed. Raises ``ValueError`` listing :func:`revision_problems` (with
    ``drafts``) when there are any."""
    by_id = {d.id: d for d in drafts}
    problems = revision_problems(out, [d.id for d in drafts], drafts=by_id)
    if problems:
        raise ValueError("refine revisions cannot be applied: " + "; ".join(problems))
    revs = {r.finding_id: r for r in out.revisions}
    kept = {fid: _kept_draft(by_id[fid], r) for fid, r in revs.items() if r.action is RevisionAction.KEEP}
    for d in drafts:
        r = revs[d.id]
        if r.action is RevisionAction.MERGE and r.merge_into is not None:
            target = kept[r.merge_into]
            gained = [c for c in d.criterion_ids if c not in target.criterion_ids]
            target.criterion_ids = [*target.criterion_ids, *gained]
    return sorted(kept.values(), key=lambda f: f.rank)


# --------------------------------------------------------------------------- verify


class AnchorRepair(Draft):
    owner_id: str                          # FND-/SA-/AD- ID, or "intent"
    anchor_index: int
    doc_anchor: DocAnchorDraft


class AnchorRepairOutput(Draft):
    """The single repair turn for unresolved anchors (ADR-007)."""

    repairs: list[AnchorRepair]


# --------------------------------------------------------------------------- report


# VerdictLabel.NOT_ASSESSED is left out of AssessedVerdictLabel on purpose: phases.report sets it in
# code only, when the run produced no assessment.
class AssessedVerdictLabel(StrEnum):
    """The verdict labels the model may choose. The label for a run that assessed nothing is left out
    on purpose: code sets it only when the run produced no assessment, so this schema never offers it
    and an answer that carries it fails validation."""

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


class VerdictOutput(Draft):
    """The verdict call of the latency redesign: the verdict only; code writes unresolved items and
    limitations (design section 9, decision 6)."""

    verdict: VerdictDraft


PHASE_OUTPUT_TYPES: dict[str, type[Draft]] = {
    "understand": UnderstandOutput,
    "plan": PlanOutput,
    "research": ResearchOutput,
    "assess": AssessOutput,
    "refine": RefineRevisionsOutput,
    "verify": AnchorRepairOutput,
    "report": VerdictOutput,
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
