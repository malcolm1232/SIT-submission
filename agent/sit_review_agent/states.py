"""The state machine: phase names, order, transition table and a Mermaid diagram (ADR-001).

``python -m sit_review_agent.states`` prints the diagram shown in the demo walkthrough.
"""

from __future__ import annotations

from enum import StrEnum

from sit_review_agent.models import ProvenancePhase


class PhaseName(StrEnum):
    INGEST = "ingest"
    UNDERSTAND = "understand"
    PLAN = "plan"
    RESEARCH = "research"
    ASSESS = "assess"
    REFINE = "refine"
    VERIFY = "verify"
    REPORT = "report"


PHASE_ORDER: tuple[PhaseName, ...] = tuple(PhaseName)

#: Linear happy path. ``None`` = terminal.
TRANSITIONS: dict[PhaseName, PhaseName | None] = {
    p: (PHASE_ORDER[i + 1] if i + 1 < len(PHASE_ORDER) else None) for i, p in enumerate(PHASE_ORDER)
}

#: Where the orchestrator jumps when a cap stop rule (deadline, token budget) fires before a phase:
#: verify is code-only and cheap, so a capped run still verifies anchors and then reports (BEH-24).
ON_CAP: dict[PhaseName, PhaseName] = {
    PhaseName.PLAN: PhaseName.VERIFY,
    PhaseName.RESEARCH: PhaseName.ASSESS,   # findings from the document alone are still worth having
    PhaseName.ASSESS: PhaseName.VERIFY,
    PhaseName.REFINE: PhaseName.VERIFY,
}

#: Phases that may be disabled in ``config/agent.yaml`` ``phases:`` (all others are mandatory).
OPTIONAL_PHASES: frozenset[PhaseName] = frozenset({PhaseName.RESEARCH, PhaseName.REFINE})

#: Phases that call the model. ``ingest`` and ``verify`` are code-only, except that ``verify``
#: may make one anchor-repair call (ADR-007) inside the ``verify`` conversation.
LLM_PHASES: frozenset[PhaseName] = frozenset(PHASE_ORDER) - {PhaseName.INGEST}

#: Which ``config/agent.yaml`` ``effort`` key a phase's conversation uses. One effort level per
#: conversation (ADR-002 option a). ``understand`` has no key in the runbook's pinned layout, so it
#: shares the ``plan`` level (and conversation prefix).
EFFORT_KEY: dict[PhaseName, str] = {
    PhaseName.UNDERSTAND: "plan",
    PhaseName.PLAN: "plan",
    PhaseName.RESEARCH: "research",
    PhaseName.ASSESS: "assess",
    PhaseName.REFINE: "refine",
    PhaseName.VERIFY: "verify",
    PhaseName.REPORT: "report",
}

#: ``Finding.provenance.phase`` for a finding created or last changed in a state-machine phase.
#: ``refine`` maps to the spec's ``revise``; delta reviews override with ``delta_review``.
PROVENANCE_PHASE: dict[PhaseName, ProvenancePhase] = {
    PhaseName.UNDERSTAND: ProvenancePhase.UNDERSTAND,
    PhaseName.ASSESS: ProvenancePhase.ASSESS,
    PhaseName.RESEARCH: ProvenancePhase.RESEARCH,
    PhaseName.REFINE: ProvenancePhase.REVISE,
    PhaseName.VERIFY: ProvenancePhase.VERIFY,
}


def mermaid() -> str:
    """Mermaid ``stateDiagram-v2`` source for the transition table (plus cap shortcuts, dashed)."""
    lines = ["stateDiagram-v2", f"    [*] --> {PHASE_ORDER[0].value}"]
    for src, dst in TRANSITIONS.items():
        lines.append(f"    {src.value} --> {dst.value if dst else '[*]'}")
    for src, dst in ON_CAP.items():
        lines.append(f"    {src.value} --> {dst.value} : stop rule (cap)")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    print(mermaid())
