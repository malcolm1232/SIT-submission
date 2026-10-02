"""``RunContext``: what every phase receives and returns (the phase contract, agent/README.md).

It bundles the serialisable :class:`~sit_review_agent.state.run_state.RunState` with the run's
services. Phases read config and documents, call the model only through ``ctx.llm`` and tools only
through ``ctx.tools``, add evidence only through ``ctx.ledger``, and write results into
``ctx.state``. They never write files other than through these services.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sit_review_agent.clock import Clock
from sit_review_agent.config import EffectiveConfig
from sit_review_agent.ingest.pdf import Document
from sit_review_agent.llm.gateway import LLMGateway
from sit_review_agent.models import DocumentRole
from sit_review_agent.progress import ProgressSink
from sit_review_agent.prompts import PromptBundle
from sit_review_agent.rundir import RunDir
from sit_review_agent.state.decision_registry import DecisionRegistry
from sit_review_agent.state.evidence_ledger import EvidenceLedger
from sit_review_agent.state.run_state import RunState
from sit_review_agent.tools.gateway import ToolGateway


@dataclass
class RunContext:
    config: EffectiveConfig
    run_dir: RunDir
    state: RunState
    llm: LLMGateway
    tools: ToolGateway | None            # None = doc-only run (--no-tools or all servers down)
    ledger: EvidenceLedger
    registry: DecisionRegistry
    prompts: PromptBundle
    clock: Clock
    progress: ProgressSink
    documents: dict[str, Document] = field(default_factory=dict)   # doc_id -> Document (with bytes)
    plan_only: bool = False              # --plan-only: stop after plan, zero tool calls

    def doc_under_review(self) -> Document:
        return next(d for d in self.documents.values() if d.role is DocumentRole.UNDER_REVIEW)

    def prior_document(self) -> Document | None:
        return next((d for d in self.documents.values() if d.role is DocumentRole.PRIOR_VERSION), None)

    def elapsed_s(self) -> float:
        return self.clock.monotonic() - self.state.budget.started_monotonic

    def remaining_s(self) -> float:
        """Seconds left before the deadline (``stop_rules.deadline_seconds``)."""
        return self.config.stop_rules.deadline_seconds - self.elapsed_s()

    def emit(self, message: str, kind: str = "step") -> None:
        phase = self.state.current_phase.value if self.state.current_phase else "run"
        self.progress.emit(phase, message, kind)  # type: ignore[arg-type]

    def sync_state(self) -> RunState:
        """Copy service-held state (registry) into ``state`` before a checkpoint."""
        self.state.registry = self.registry.entries()
        self.state.registry_frozen = self.registry.frozen
        self.state.registry_hashes = self.registry.hashes()
        return self.state
