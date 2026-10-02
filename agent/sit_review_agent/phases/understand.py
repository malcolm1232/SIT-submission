"""``understand`` (LLM, workstream A). Prompt: ``prompts/understand.md``. Output: ``UnderstandOutput``.

Reads: documents, criteria, persona.
Writes: ``ctx.state.intent_summary`` (IntentSummary; anchors verified later by verify),
``ctx.registry`` entries (``AD-nnn``) then ``ctx.registry.freeze()``, ``review_inputs_found``.
Effort: ``config.effort_for(UNDERSTAND)`` (= the ``plan`` level; same conversation prefix).
"""

from __future__ import annotations

from sit_review_agent.context import RunContext
from sit_review_agent.states import PhaseName


class UnderstandPhase:
    name = PhaseName.UNDERSTAND

    async def run(self, ctx: RunContext) -> RunContext:
        raise NotImplementedError("phase 1: UnderstandPhase.run (workstream A)")
