"""One module per state-machine phase; all implement :class:`~sit_review_agent.phases.base.Phase`."""

from sit_review_agent.phases.assess import AssessPhase
from sit_review_agent.phases.base import Phase
from sit_review_agent.phases.ingest import IngestPhase
from sit_review_agent.phases.plan import PlanPhase
from sit_review_agent.phases.refine import RefinePhase
from sit_review_agent.phases.report import ReportPhase
from sit_review_agent.phases.research import ResearchPhase
from sit_review_agent.phases.understand import UnderstandPhase
from sit_review_agent.phases.verify import VerifyPhase
from sit_review_agent.states import PhaseName


def default_phases() -> dict[PhaseName, Phase]:
    """The production phase objects, keyed by name, in PHASE_ORDER."""
    return {p.name: p for p in (IngestPhase(), UnderstandPhase(), PlanPhase(), ResearchPhase(), AssessPhase(),
                                RefinePhase(), VerifyPhase(), ReportPhase())}


__all__ = ["AssessPhase", "IngestPhase", "Phase", "PlanPhase", "RefinePhase", "ReportPhase", "ResearchPhase",
           "UnderstandPhase", "VerifyPhase", "default_phases"]
