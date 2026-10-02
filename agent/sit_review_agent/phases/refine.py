"""``refine`` (LLM, workstream A; optional). Prompt: ``prompts/refine.md``. Output: ``RefineOutput``.

One self-critique pass over the drafts: drop unsupported findings, merge duplicates, fix
disposition / severity against the taxonomy, make recommendations specific (BEH-07), label
registry conflicts (INV-10). Writes: ``state.finding_drafts`` (full revised set) and a
``FindingRevision`` per changed finding in ``state.finding_meta[...].history`` (phase refine ->
provenance ``revise``). Delta mode: sets ``reassessment`` on every finding.
"""

from __future__ import annotations

from sit_review_agent.context import RunContext
from sit_review_agent.states import PhaseName


class RefinePhase:
    name = PhaseName.REFINE

    async def run(self, ctx: RunContext) -> RunContext:
        raise NotImplementedError("phase 1: RefinePhase.run (workstream A)")
