"""The state machine: phase names, order, transition table and a Mermaid diagram (ADR-001).

``python -m sit_review_agent.states`` prints the diagram shown in the demo walkthrough.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Literal

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

# Deprecated (latency redesign W0, 2026-10-03): the sequential table; W2 moves orchestrator.py to
# STAGE_TRANSITIONS / STAGE_ON_CAP and removes TRANSITIONS and ON_CAP.
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


# --------------------------------------------------------------------------- stages (latency redesign)
#
# Interface change of 2026-10-03 (W0, docs/design/latency_and_demo_design.md section 4): the eight
# phase names stay; understand, plan, research and assess form one concurrent stage. Inside it,
# research waits for understand and plan; the others start together. Merge (code) runs when the
# stage closes, before refine.


class Stage(StrEnum):
    INGEST = "ingest"
    STAGE_1 = "stage_1"
    REFINE = "refine"
    VERIFY = "verify"
    REPORT = "report"


STAGE_ORDER: tuple[Stage, ...] = tuple(Stage)

#: Phases of each stage, in phase order (the order shards and members are numbered in).
STAGE_MEMBERS: dict[Stage, tuple[PhaseName, ...]] = {
    Stage.INGEST: (PhaseName.INGEST,),
    Stage.STAGE_1: (PhaseName.UNDERSTAND, PhaseName.PLAN, PhaseName.RESEARCH, PhaseName.ASSESS),
    Stage.REFINE: (PhaseName.REFINE,),
    Stage.VERIFY: (PhaseName.VERIFY,),
    Stage.REPORT: (PhaseName.REPORT,),
}

#: Linear stage path. ``None`` = terminal.
STAGE_TRANSITIONS: dict[Stage, Stage | None] = {
    s: (STAGE_ORDER[i + 1] if i + 1 < len(STAGE_ORDER) else None) for i, s in enumerate(STAGE_ORDER)
}

#: Where the run jumps when a cap stop rule fires before a stage starts (verify is code-only).
#: A stage 1 limit that fires while members run does not jump: :func:`stage1_close` ends them.
STAGE_ON_CAP: dict[Stage, Stage] = {
    Stage.STAGE_1: Stage.VERIFY,
    Stage.REFINE: Stage.VERIFY,
}

#: Members of stage 1 that must have ended before a member may start.
STAGE_1_DEPENDS: dict[PhaseName, frozenset[PhaseName]] = {
    PhaseName.UNDERSTAND: frozenset(),
    PhaseName.PLAN: frozenset(),
    PhaseName.RESEARCH: frozenset({PhaseName.UNDERSTAND, PhaseName.PLAN}),
    PhaseName.ASSESS: frozenset(),
}

#: How a stage 1 member ended: ``done`` (completed, possibly degraded), ``cut`` (running when the
#: stage limit fired; keeps what it salvaged), ``skipped`` (never started before the limit).
MemberOutcome = Literal["done", "cut", "skipped"]


def stage_of(phase: PhaseName) -> Stage:
    return next(s for s, members in STAGE_MEMBERS.items() if phase in members)


def _stage1_members(phases: Iterable[PhaseName]) -> None:
    bad = sorted(p.value for p in phases if p not in STAGE_1_DEPENDS)
    if bad:
        raise ValueError(f"{', '.join(bad)} is not a stage 1 member")


def stage1_ready(ended: Mapping[PhaseName, MemberOutcome], running: Iterable[PhaseName]) -> set[PhaseName]:
    """Stage 1 members that may start now: not ended, not running, every dependency ended (in any
    order, with any outcome; a cut plan has its fallback questions)."""
    running = set(running)
    _stage1_members([*ended, *running])
    return {p for p, deps in STAGE_1_DEPENDS.items()
            if p not in ended and p not in running and deps <= set(ended)}


def stage1_close(ended: Mapping[PhaseName, MemberOutcome],
                 running: Iterable[PhaseName]) -> dict[PhaseName, MemberOutcome]:
    """Outcomes when the stage 1 limit fires: running members are cut, members never started are
    skipped, ended members keep their outcome. Returns a new mapping covering every member."""
    running = set(running)
    _stage1_members([*ended, *running])
    both = sorted(p.value for p in running if p in ended)
    if both:
        raise ValueError(f"{', '.join(both)} both ended and running")
    out: dict[PhaseName, MemberOutcome] = dict(ended)
    for p in STAGE_1_DEPENDS:
        if p not in out:
            out[p] = "cut" if p in running else "skipped"
    return out


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
