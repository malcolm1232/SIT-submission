"""The serialisable run state: everything a checkpoint must hold to resume (ADR-009 item 1).

Runtime services (gateways, ledger, registry, documents with their bytes) live on
:class:`~sit_review_agent.context.RunContext`; :meth:`RunContext.sync_state` copies the
registry into this object before every checkpoint. The ledger is persisted by its own journal;
checkpoints store its byte offset.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from sit_review_agent.llm.outputs import (
    CriterionCoverage,
    CriterionSkip,
    FindingDraft,
    ResearchQuestionDraft,
    SoundAreaDraft,
)
from sit_review_agent.models import (
    Degradation,
    DegradationType,
    DocumentRole,
    FallbackEvent,
    Finding,
    IntentSummary,
    Limitation,
    RegistryEntry,
    RegistryHash,
    ResearchLogEntry,
    ReviewMode,
    SoundArea,
    StopReason,
    UnresolvedItem,
    Verdict,
    degradation_id,
)
from sit_review_agent.states import PhaseName

RunMode = Literal["eval", "dev", "rehearsal", "demo", "replay"]


class _State(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentRef(_State):
    """Where a document's bytes and canonical text are; enough to rebuild the Document."""

    doc_id: str
    role: DocumentRole
    title: str
    version: str | None = None
    pdf_path: str | None = None
    sha256_pdf: str | None = None
    sha256_text: str
    text_path: str                      # run-relative
    page_count: int | None = None
    native_pdf: bool = True             # false = text-only fallback (disclosed)


class ResearchQuestion(ResearchQuestionDraft):
    status: Literal["open", "answered", "partial", "unanswered", "conflicting"] = "open"
    summary: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class ResearchPlan(_State):
    questions: list[ResearchQuestion]
    criteria_skipped: list[CriterionSkip] = Field(default_factory=list)
    approved: bool = True               # false while waiting for --plan-approval


class FindingRevision(_State):
    phase: PhaseName
    call_id: str | None
    changed_fields: dict[str, list[Any]] = Field(default_factory=dict, description="field -> [before, after]")
    note: str = ""


class FindingMeta(_State):
    """Per-finding provenance kept outside the Finding (which admits no extra keys); read by
    ``explain`` and used to build ``Finding.provenance``."""

    finding_id: str
    criterion_ids: list[str]
    created_phase: PhaseName
    created_call_id: str | None
    last_phase: PhaseName
    last_call_id: str | None
    model: str | None                   # response.model of last_call_id
    prompt_hash: str | None             # sha256 of the rendered prompt of last_call_id
    iteration: int = 0
    history: list[FindingRevision] = Field(default_factory=list)


class Budget(_State):
    """Counters the stop rules read."""

    tool_calls: int = 0
    input_tokens: int = 0               # incl. cache reads and writes
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    research_iterations: int = 0
    new_sources_by_iteration: list[int] = Field(default_factory=list)
    started_monotonic: float = 0.0
    #: Wall seconds per phase. Stage 1 members overlap (latency redesign), so these no longer sum
    #: to the run's elapsed time; use ``elapsed_s``.
    phase_seconds: dict[str, float] = Field(default_factory=dict)
    #: The run clock's elapsed seconds when the state was last checkpointed (interface change of
    #: 2026-10-03, latency redesign W0). Resume restores the clock from it. 0.0 = not recorded
    #: (a state written before 2026-10-03, or before the first checkpoint).
    elapsed_s: float = Field(0.0, ge=0.0)

    def elapsed_for_resume(self) -> float:
        """Seconds the run clock had used when checkpointed: ``elapsed_s`` when recorded, else the
        sum of ``phase_seconds`` (exact only for the sequential runs that wrote such states)."""
        return self.elapsed_s if self.elapsed_s > 0.0 else sum(self.phase_seconds.values())


class RunState(_State):
    run_id: str
    mode: RunMode = "dev"
    review_mode: ReviewMode = ReviewMode.FULL
    created_utc: str
    prior_review_id: str | None = None
    previous_run_dir: str | None = None
    k_index: int | None = None          # 1..k within a k-run group (REPRODUCIBILITY §8; set by RunRequest)

    documents: list[DocumentRef] = Field(default_factory=list)
    intent_summary: IntentSummary | None = None
    registry: list[RegistryEntry] = Field(default_factory=list)
    registry_frozen: bool = False
    registry_hashes: list[RegistryHash] = Field(default_factory=list)
    review_inputs_found: list[str] = Field(default_factory=list)

    plan: ResearchPlan | None = None
    tool_calls: list[ResearchLogEntry] = Field(default_factory=list)
    queries_issued: int = 0
    unanswered_questions: list[str] = Field(default_factory=list)

    finding_drafts: list[FindingDraft] = Field(default_factory=list)
    finding_meta: dict[str, FindingMeta] = Field(default_factory=dict)
    sound_area_drafts: list[SoundAreaDraft] = Field(default_factory=list)
    coverage: list[CriterionCoverage] = Field(default_factory=list)

    findings: list[Finding] = Field(default_factory=list)          # hydrated by verify
    sound_areas: list[SoundArea] = Field(default_factory=list)
    anchor_table: list[dict[str, Any]] = Field(default_factory=list)

    verdict: Verdict | None = None
    unresolved: list[UnresolvedItem] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    degradations: list[Degradation] = Field(default_factory=list)
    declined_sections: list[str] = Field(default_factory=list)     # model refusals that persisted

    stop_reason: StopReason | None = None
    budget: Budget = Field(default_factory=Budget)
    completed_phases: list[PhaseName] = Field(default_factory=list)
    current_phase: PhaseName | None = None
    llm_calls: dict[str, list[str]] = Field(default_factory=dict, description="phase -> llm call IDs")
    refusals: list[dict[str, Any]] = Field(default_factory=list)
    fallback_events: list[FallbackEvent] = Field(default_factory=list)

    def add_degradation(self, type: DegradationType, event: str, impact: str) -> Degradation:
        """Record a fault event that the report must disclose (INV-07)."""
        d = Degradation(id=degradation_id(len(self.degradations) + 1), type=type, event=event, impact=impact)
        self.degradations.append(d)
        return d

    def under_review(self) -> DocumentRef:
        return next(d for d in self.documents if d.role is DocumentRole.UNDER_REVIEW)
