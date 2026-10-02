"""Pydantic v2 models of the output contract, ``spec/finding.schema.json`` (schema_version 1.0).

Rules:

* One class per ``$defs`` object, same field names, same required set, ``extra="forbid"``
  (every spec object is ``additionalProperties: false``). No field has a default, because every
  spec property is required (nullable ones must be present as ``null``).
* Enums are copies of ``spec/taxonomy.yaml``; ``tests/test_models.py`` fails if they drift.
* The schema's ``allOf`` if/then rules are ``model_validator``\\ s, so an invalid object cannot be
  constructed. Cross-object rules that JSON Schema cannot express (ledger membership, ID
  cross-references) are in :mod:`sit_review_agent.invariants`, not here.
* Date-time fields are ``str`` (RFC 3339, ``Z``) so ``model_dump()`` is byte-faithful to JSON.
* Serialise with ``model.model_dump(mode="json")``; the result validates against the spec.

These are the *canonical, hydrated* objects. What the model emits in structured outputs is the
smaller set of draft types in :mod:`sit_review_agent.llm.outputs`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# ============================================================================== enums (taxonomy)


class Kind(StrEnum):
    STRENGTH = "strength"
    RISK = "risk"
    GAP = "gap"
    AMBIGUITY = "ambiguity"
    UNRESOLVED_ASSUMPTION = "unresolved_assumption"
    VALIDATION_NEED = "validation_need"


class Category(StrEnum):
    INTERNAL_CONTRADICTION = "internal_contradiction"
    UNSUPPORTED_OR_INCORRECT_CLAIM = "unsupported_or_incorrect_claim"
    EXTERNAL_CONSTRAINT_VIOLATION = "external_constraint_violation"
    MISSING_OR_UNVERIFIABLE_REQUIREMENT = "missing_or_unverifiable_requirement"
    SECURITY_PRIVACY_GAP = "security_privacy_gap"
    SCALABILITY_OR_FAILURE_MODE = "scalability_or_failure_mode"
    AMBIGUOUS_REQUIREMENT = "ambiguous_requirement"
    ACCEPTANCE_CRITERION_CANNOT_VALIDATE = "acceptance_criterion_cannot_validate"
    DECISION_DEPENDS_ON_PENDING_ITEM = "decision_depends_on_pending_item"
    OTHER = "other"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


#: Taxonomy ``severities[].rank`` (critical highest). Used by the report's severity filter.
SEVERITY_RANK: dict[Severity, int] = {Severity.CRITICAL: 4, Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}


class Disposition(StrEnum):
    REFINEMENT_NOW = "refinement_now"
    NEEDS_INVESTIGATION = "needs_investigation"
    NEEDS_PROTOTYPING = "needs_prototyping"
    NEEDS_TESTING = "needs_testing"
    GOVERNANCE_DECISION = "governance_decision"
    NO_CHANGE = "no_change"


#: Dispositions that require ``next_step`` and an ``unresolved[]`` entry (lab §2.4, §3.2).
NON_REFINEMENT_DISPOSITIONS: frozenset[Disposition] = frozenset({
    Disposition.NEEDS_INVESTIGATION, Disposition.NEEDS_PROTOTYPING,
    Disposition.NEEDS_TESTING, Disposition.GOVERNANCE_DECISION,
})


class VerdictLabel(StrEnum):
    FIT = "fit"
    FIT_WITH_CONDITIONS = "fit_with_conditions"
    NOT_FIT = "not_fit"


class SourceType(StrEnum):
    DOC = "doc"
    EXTERNAL = "external"
    INFERENCE = "inference"


class SourceAuthority(StrEnum):
    PRIMARY_OFFICIAL = "primary_official"
    PEER_REVIEWED = "peer_reviewed"
    SECONDARY = "secondary"
    INFORMAL = "informal"


class StopReasonCode(StrEnum):
    """The closed stop-reason enum. A new stop rule reuses one of these codes (runbook §4.2 #2b)."""

    SUFFICIENT_EVIDENCE = "sufficient_evidence"
    NO_MARGINAL_GAIN = "no_marginal_gain"
    BUDGET_TOOL_CALLS = "budget_tool_calls"
    BUDGET_TOKENS = "budget_tokens"
    DEADLINE = "deadline"
    TOOL_FAILURE = "tool_failure"
    ERROR = "error"


class StopReasonGroup(StrEnum):
    DECISION = "decision"
    CAP = "cap"
    ERROR = "error"


#: ``taxonomy.yaml stop_reasons[].group``.
STOP_REASON_GROUP: dict[StopReasonCode, StopReasonGroup] = {
    StopReasonCode.SUFFICIENT_EVIDENCE: StopReasonGroup.DECISION,
    StopReasonCode.NO_MARGINAL_GAIN: StopReasonGroup.DECISION,
    StopReasonCode.BUDGET_TOOL_CALLS: StopReasonGroup.CAP,
    StopReasonCode.BUDGET_TOKENS: StopReasonGroup.CAP,
    StopReasonCode.DEADLINE: StopReasonGroup.CAP,
    StopReasonCode.TOOL_FAILURE: StopReasonGroup.ERROR,
    StopReasonCode.ERROR: StopReasonGroup.ERROR,
}


class DecisionRelation(StrEnum):
    PRESERVES = "preserves"
    REFINES = "refines"
    CHALLENGES = "challenges"


class RegistryEntryType(StrEnum):
    APPROVED_DECISION = "approved_decision"
    PENDING_DECISION = "pending_decision"
    CONSTRAINT = "constraint"
    REQUIREMENT = "requirement"


class ProvenancePhase(StrEnum):
    """``Finding.provenance.phase`` (taxonomy ``phases``). Not the same set as the state machine's
    :class:`~sit_review_agent.states.PhaseName`; see ``states.PROVENANCE_PHASE``."""

    UNDERSTAND = "understand"
    ASSESS = "assess"
    RESEARCH = "research"
    VERIFY = "verify"
    REVISE = "revise"
    DELTA_REVIEW = "delta_review"


class ReassessmentStatus(StrEnum):
    NEW_IN_UPDATE = "new_in_update"
    STILL_OPEN = "still_open"
    PARTIALLY_ADDRESSED = "partially_addressed"
    RESOLVED = "resolved"


class DegradationType(StrEnum):
    TOOL_UNAVAILABLE = "tool_unavailable"
    TOOL_ERROR = "tool_error"
    MODEL_FALLBACK = "model_fallback"
    OCR_USED = "ocr_used"
    INPUT_DEGRADED = "input_degraded"
    BUDGET_OR_DEADLINE_HIT = "budget_or_deadline_hit"
    OTHER = "other"


class ToolCallStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"


class ReviewMode(StrEnum):
    FULL = "full"
    DELTA = "delta"


class DocumentRole(StrEnum):
    UNDER_REVIEW = "under_review"
    PRIOR_VERSION = "prior_version"
    COMPANION = "companion"


class Outcome(StrEnum):
    COMPLETED_NOMINAL = "completed_nominal"
    COMPLETED_DEGRADED = "completed_degraded"
    ABORTED_GRACEFUL = "aborted_graceful"
    CRASHED = "crashed"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"


class ToolMode(StrEnum):
    LIVE = "live"
    RECORD = "record"
    REPLAY = "replay"


# ============================================================================== scalar types

FindingId = Annotated[str, StringConstraints(pattern=r"^FND-[0-9]{3,}$")]
EvidenceId = Annotated[str, StringConstraints(pattern=r"^EV-[0-9]{3,}$")]
RegistryId = Annotated[str, StringConstraints(pattern=r"^AD-[0-9]{3,}$")]
SoundAreaId = Annotated[str, StringConstraints(pattern=r"^SA-[0-9]{3,}$")]
DocId = Annotated[str, StringConstraints(pattern=r"^DOC-[A-Za-z0-9_.-]+$")]
DegradationId = Annotated[str, StringConstraints(pattern=r"^DEG-[0-9]{3,}$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
NonEmpty = Annotated[str, StringConstraints(min_length=1)]
#: >= 8 whitespace-separated tokens (taxonomy ``anchor_rules.min_quote_tokens``).
Quote = Annotated[str, StringConstraints(pattern=r"^\s*\S+(\s+\S+){7,}\s*$")]
GitCommit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{7,40}$")]
Probability = Annotated[float, Field(ge=0, le=1)]
NonNegInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
#: RFC 3339 date-time string (schema ``format: date-time``; not enforced by the schema validator).
DateTimeStr = str


def _fmt_id(prefix: str, n: int) -> str:
    return f"{prefix}-{n:03d}"


def finding_id(n: int) -> str:
    """``FND-001`` style ID (at least three digits)."""
    return _fmt_id("FND", n)


def evidence_id(n: int) -> str:
    return _fmt_id("EV", n)


def registry_id(n: int) -> str:
    return _fmt_id("AD", n)


def sound_area_id(n: int) -> str:
    return _fmt_id("SA", n)


def degradation_id(n: int) -> str:
    return _fmt_id("DEG", n)


class SpecModel(BaseModel):
    """Base for every spec object: no extra keys (``additionalProperties: false``)."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False, validate_assignment=False)


# ============================================================================== finding parts


class DocAnchor(SpecModel):
    """Traceability to the document under review (ADR-007). Verified by ``ingest.anchor``."""

    doc_id: DocId
    section_ref: NonEmpty
    requirement_ids: list[NonEmpty]
    quote: Quote
    page: PositiveInt | None


class EvidenceItem(SpecModel):
    """A citation of one evidence-ledger entry, hydrated from the ledger (``url_or_citation`` and
    ``retrieved_at`` are ``readOnly``: the model never writes them)."""

    evidence_id: EvidenceId
    source_type: SourceType
    url_or_citation: str
    quote: str | None
    supports_claim: bool
    retrieved_at: DateTimeStr | None
    derived_from: list[EvidenceId]

    @model_validator(mode="after")
    def _by_source_type(self) -> EvidenceItem:
        if self.source_type is SourceType.EXTERNAL:
            if self.retrieved_at is None:
                raise ValueError("external evidence needs retrieved_at")
            if not self.quote:
                raise ValueError("external evidence needs a non-empty quote")
            if not self.url_or_citation:
                raise ValueError("external evidence needs url_or_citation")
        elif self.source_type is SourceType.DOC:
            if not self.quote:
                raise ValueError("doc evidence needs a non-empty quote")
            if self.retrieved_at is not None:
                raise ValueError("doc evidence must have retrieved_at = null")
        else:
            if not self.derived_from:
                raise ValueError("inference evidence needs derived_from (>= 1 ledger ID)")
            if self.retrieved_at is not None:
                raise ValueError("inference evidence must have retrieved_at = null")
        return self


class Recommendation(SpecModel):
    """Lab §2.3: issue, rationale, supporting evidence, expected benefit."""

    issue: NonEmpty
    rationale: NonEmpty
    expected_benefit: NonEmpty
    change_summary: NonEmpty
    objective_refs: Annotated[list[NonEmpty], Field(min_length=1)]
    supporting_evidence_ids: Annotated[list[EvidenceId], Field(min_length=1)]
    verification: str | None


class NextStep(SpecModel):
    owner: NonEmpty
    action: NonEmpty


class AffectedDecision(SpecModel):
    registry_id: RegistryId
    relation: DecisionRelation
    justification: NonEmpty


class Provenance(SpecModel):
    phase: ProvenancePhase
    iteration: NonNegInt
    model: NonEmpty
    prompt_hash: Sha256


class Reassessment(SpecModel):
    prior_finding_id: FindingId | None
    status: ReassessmentStatus
    note: str | None

    @model_validator(mode="after")
    def _prior_needed(self) -> Reassessment:
        if self.status is not ReassessmentStatus.NEW_IN_UPDATE and self.prior_finding_id is None:
            raise ValueError(f"reassessment status {self.status} needs prior_finding_id")
        return self


class Finding(SpecModel):
    """One hydrated finding (root of ``spec/finding.schema.json``)."""

    id: FindingId
    rank: PositiveInt
    kind: Kind
    category: Category | None
    severity: Severity | None
    confidence: Probability
    disposition: Disposition
    secondary_dispositions: list[Disposition]
    title: NonEmpty
    statement: NonEmpty
    doc_anchors: Annotated[list[DocAnchor], Field(min_length=1, max_length=3)]
    evidence: list[EvidenceItem]
    recommendation: Recommendation | None
    no_change_rationale: str | None
    next_step: NextStep | None
    affected_decisions: list[AffectedDecision]
    acknowledged_in_doc: bool
    tags: list[str]
    reassessment: Reassessment | None
    provenance: Provenance

    @model_validator(mode="after")
    def _schema_all_of(self) -> Finding:
        problems = finding_rule_violations(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def finding_rule_violations(f: Finding) -> list[str]:
    """The ``Finding.allOf`` rules of the schema, as messages (empty list = valid)."""
    out: list[str] = []
    if f.kind is Kind.STRENGTH:
        if f.category is not None or f.severity is not None:
            out.append("strength must have category = null and severity = null")
        if f.disposition is not Disposition.NO_CHANGE:
            out.append("strength must have disposition = no_change")
    else:
        if f.category is None or f.severity is None:
            out.append(f"{f.kind} needs a category and a severity")
    if f.disposition is Disposition.NO_CHANGE:
        if f.recommendation is not None:
            out.append("no_change forbids a recommendation")
        if not f.no_change_rationale:
            out.append("no_change requires a non-empty no_change_rationale")
        if f.next_step is not None:
            out.append("no_change requires next_step = null")
        if f.secondary_dispositions:
            out.append("no_change requires no secondary_dispositions")
    else:
        if f.recommendation is None:
            out.append(f"disposition {f.disposition} requires a recommendation")
        if f.no_change_rationale is not None:
            out.append("no_change_rationale must be null unless disposition = no_change")
        if Disposition.NO_CHANGE in f.secondary_dispositions:
            out.append("secondary_dispositions must not contain no_change")
    if f.disposition in NON_REFINEMENT_DISPOSITIONS and f.next_step is None:
        out.append(f"disposition {f.disposition} requires next_step")
    if any(a.relation is DecisionRelation.CHALLENGES for a in f.affected_decisions):
        if len(f.evidence) < 2:
            out.append("challenging an approved decision needs >= 2 evidence items")
        if f.disposition is Disposition.NO_CHANGE:
            out.append("challenging an approved decision cannot have disposition no_change")
    if f.disposition in f.secondary_dispositions:
        out.append("secondary_dispositions must not repeat the primary disposition")
    if len(set(f.secondary_dispositions)) != len(f.secondary_dispositions):
        out.append("secondary_dispositions must be unique")
    return out


# ============================================================================== review parts


class LedgerToolRef(SpecModel):
    server: str
    tool_name: str
    call_id: str


class LedgerEntry(SpecModel):
    """One evidence-ledger record (robustness §10 item 3)."""

    evidence_id: EvidenceId
    source_type: SourceType
    authority: SourceAuthority | None
    tool: LedgerToolRef | None
    url_or_citation: NonEmpty
    title: str | None
    retrieved_at: DateTimeStr | None
    content_sha256: Sha256 | None
    snapshot_path: str | None
    excerpt: str | None
    read_before_cite: bool
    derived_from: list[EvidenceId]

    @model_validator(mode="after")
    def _external_needs_tool(self) -> LedgerEntry:
        if self.source_type is SourceType.EXTERNAL:
            missing = [n for n in ("tool", "retrieved_at", "content_sha256", "authority") if getattr(self, n) is None]
            if missing:
                raise ValueError(f"external ledger entry needs {', '.join(missing)}")
        return self


class RegistryEntry(SpecModel):
    registry_id: RegistryId
    type: RegistryEntryType
    doc_ref: NonEmpty
    statement: NonEmpty
    doc_anchor: DocAnchor


class SoundArea(SpecModel):
    id: SoundAreaId
    section_refs: Annotated[list[NonEmpty], Field(min_length=1)]
    why_sound: NonEmpty
    doc_anchors: Annotated[list[DocAnchor], Field(min_length=1, max_length=3)]
    evidence_ids: list[EvidenceId]
    related_finding_ids: list[FindingId]


class VerdictCondition(SpecModel):
    text: NonEmpty
    finding_ids: Annotated[list[FindingId], Field(min_length=1)]


class ObjectiveVerdict(SpecModel):
    objective_ref: NonEmpty
    label: VerdictLabel
    finding_ids: list[FindingId]


class Verdict(SpecModel):
    label: VerdictLabel
    rationale: NonEmpty
    confidence: Probability
    conditions: list[VerdictCondition]
    per_objective: list[ObjectiveVerdict]
    what_would_change_it: str | None

    @model_validator(mode="after")
    def _conditions(self) -> Verdict:
        if self.label is VerdictLabel.FIT_WITH_CONDITIONS and not self.conditions:
            raise ValueError("fit_with_conditions needs >= 1 condition")
        return self


class StopReason(SpecModel):
    code: StopReasonCode
    group: StopReasonGroup
    detail: str | None

    @model_validator(mode="after")
    def _group_matches(self) -> StopReason:
        if STOP_REASON_GROUP[self.code] is not self.group:
            raise ValueError(f"stop reason {self.code} belongs to group {STOP_REASON_GROUP[self.code]}")
        return self

    @classmethod
    def of(cls, code: StopReasonCode, detail: str | None = None) -> StopReason:
        """Build a stop reason with the taxonomy's group for ``code``."""
        return cls(code=code, group=STOP_REASON_GROUP[code], detail=detail)


class ResearchLogEntry(SpecModel):
    """One entry of ``research_log.tool_calls[]``: every tool call made or replayed in the run."""

    call_id: NonEmpty
    server: NonEmpty
    tool_name: NonEmpty
    status: ToolCallStatus
    started_at: DateTimeStr


ToolCallLogEntry = ResearchLogEntry


class RegistryHash(SpecModel):
    iteration: NonNegInt
    sha256: Sha256


class Degradation(SpecModel):
    id: DegradationId
    type: DegradationType
    event: NonEmpty
    impact: NonEmpty


class ResearchLog(SpecModel):
    iterations: NonNegInt
    tool_calls_by_tool: dict[str, NonNegInt]
    tool_calls: list[ResearchLogEntry]
    queries_issued: NonNegInt
    sources_retrieved: NonNegInt
    sources_cited: NonNegInt
    unanswered_questions: list[str]
    degradations: list[Degradation]
    registry_sha256_by_iteration: Annotated[list[RegistryHash], Field(min_length=1)]


# ============================================================================== run manifest


class ReviewConfigEcho(SpecModel):
    criteria: Annotated[list[NonEmpty], Field(min_length=1)]
    stop_rule: dict[str, Any]
    persona: str | None


class ExtractorInfo(SpecModel):
    name: str
    version: str
    page_marker: str


class ModelUse(SpecModel):
    role: str
    requested_model: str
    served_models: Annotated[list[str], Field(min_length=1)]
    thinking: str | None
    effort: str | None
    max_tokens: PositiveInt
    betas: list[str]
    sampling: str


class FallbackEvent(SpecModel):
    role: str
    from_model: str
    to_model: str
    reason: str


class ToolManifestEntry(SpecModel):
    name: str
    enabled: bool
    server_version: str | None
    mode: ToolMode


class Budgets(SpecModel):
    max_tool_calls: int | None
    max_tokens: int | None
    deadline_s: int | None


class UsageSummary(SpecModel):
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    tool_calls: int
    cost_usd: float
    price_table_date: str


class Timestamps(SpecModel):
    start_utc: DateTimeStr
    end_utc: DateTimeStr | None


class RunManifest(SpecModel):
    """``#/$defs/RunManifest``. The longer REPRODUCIBILITY §8 field list lives in ``extra``
    (see :class:`ManifestExtra`)."""

    run_id: NonEmpty
    git_commit: GitCommit
    git_dirty: Literal[False]
    config_sha256: Sha256
    prompts_bundle_sha256: Sha256
    taxonomy_sha256: Sha256
    schema_version: Literal["1.0"]
    extractor: ExtractorInfo
    models_used: Annotated[list[ModelUse], Field(min_length=1)]
    fallback_events: list[FallbackEvent]
    tools: list[ToolManifestEntry]
    budgets: Budgets
    usage: UsageSummary
    timestamps: Timestamps
    outcome: Outcome
    prereg_sha256: Sha256 | None
    split: str | None
    condition: str | None
    review_config: ReviewConfigEcho
    fault_schedule_id: str | None
    extra: dict[str, Any]


class ManifestExtra(BaseModel):
    """Typed view of ``RunManifest.extra``: the docs/REPRODUCIBILITY.md §8 fields that the spec's
    ``RunManifest`` does not carry. Stored as ``extra = ManifestExtra(...).model_dump(mode="json")``.
    Scorers never read ``extra`` (spec), but INV-09 checks it is present."""

    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal[1] = 1
    mode: Literal["eval", "dev", "rehearsal", "demo", "replay"]
    k_index: int | None = None
    previous_run_id: str | None = None
    split_assignment_sha256: str | None = None
    doc: dict[str, Any] = Field(default_factory=dict, description="id, sha256_pdf, pages, bytes, "
                                "canonical_text_sha256, normalisation_version, native_pdf_block")
    code: dict[str, Any] = Field(default_factory=dict, description="package_lock_sha256, python, os, "
                                 "anthropic_sdk_version, mcp_version")
    prompts: dict[str, Any] = Field(default_factory=dict, description="files {path: sha256}, bundle_sha256")
    config: dict[str, Any] = Field(default_factory=dict, description="files {path: sha256}, "
                                   "effective_config_sha256, cli_args")
    model: dict[str, Any] = Field(default_factory=dict, description="models_retrieve, effort_by_stage, "
                                  "max_tokens_by_stage, thinking, fallbacks (none|default), refusals")
    tools: dict[str, Any] = Field(default_factory=dict, description="transport, cassette_set_sha256, "
                                  "url_policy_sha256, servers")
    stop: dict[str, Any] = Field(default_factory=dict, description="active_rules, params")
    fault_injection: dict[str, Any] = Field(default_factory=dict, description="profile, schedule_sha256")
    timing: dict[str, Any] = Field(default_factory=dict, description="wall_clock_s, per_stage_s")
    outputs: dict[str, Any] = Field(default_factory=dict, description="report_json_sha256, report_md_sha256, "
                                    "ledger_sha256, llm_jsonl_sha256, tools_jsonl_sha256")
    deviations: list[str] = Field(default_factory=list, description="e.g. --accept-drift, model swap, fallbacks")


# ============================================================================== review envelope


class DocumentMeta(SpecModel):
    doc_id: DocId
    title: str
    version: str | None
    role: DocumentRole
    sha256_pdf: Sha256 | None
    sha256_text: Sha256
    text_path: NonEmpty
    page_count: PositiveInt | None


class ReviewMetadata(SpecModel):
    review_id: NonEmpty
    run_id: NonEmpty
    created_at: DateTimeStr
    review_mode: ReviewMode
    documents: Annotated[list[DocumentMeta], Field(min_length=1)]
    prior_review_id: str | None
    taxonomy_version: Literal["1.0"]


class RefText(SpecModel):
    ref: str | None
    text: NonEmpty


class IntentSummary(SpecModel):
    statement: NonEmpty
    objectives: list[RefText]
    constraints: list[RefText]
    key_assumptions: list[RefText]
    doc_anchors: Annotated[list[DocAnchor], Field(min_length=1)]


class UnresolvedItem(SpecModel):
    text: NonEmpty
    finding_ids: list[FindingId]
    next_step: NextStep | None


class Limitation(SpecModel):
    text: NonEmpty
    degradation_ids: list[DegradationId]


class Review(SpecModel):
    """``#/$defs/Review``: the agent's complete output (``runs/<id>/report.json``)."""

    schema_version: Literal["1.0"]
    metadata: ReviewMetadata
    intent_summary: IntentSummary
    verdict: Verdict
    findings: list[Finding]
    sound_areas: list[SoundArea]
    unresolved: list[UnresolvedItem]
    decision_registry: list[RegistryEntry]
    evidence_ledger: list[LedgerEntry]
    research_log: ResearchLog
    limitations: list[Limitation]
    stop_reason: StopReason
    run_manifest: RunManifest

    @model_validator(mode="after")
    def _delta_rules(self) -> Review:
        has_prior_doc = any(d.role is DocumentRole.PRIOR_VERSION for d in self.metadata.documents)
        if self.metadata.review_mode is ReviewMode.DELTA:
            if not self.metadata.prior_review_id:
                raise ValueError("delta review needs prior_review_id")
            if not has_prior_doc:
                raise ValueError("delta review needs a document with role prior_version")
            if any(f.reassessment is None for f in self.findings):
                raise ValueError("delta review needs a reassessment on every finding")
        else:
            if self.metadata.prior_review_id is not None:
                raise ValueError("full review must have prior_review_id = null")
            if has_prior_doc:
                raise ValueError("full review must not include a prior_version document")
            if any(f.reassessment is not None for f in self.findings):
                raise ValueError("full review must have reassessment = null on every finding")
        return self
