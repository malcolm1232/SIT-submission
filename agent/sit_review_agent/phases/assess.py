"""``assess`` (LLM, workstream A). Prompt: ``prompts/assess.md``. Output: ``AssessOutput``.

Reads: intent, registry, criteria, plan answers, ledger (IDs + excerpts only).
Writes: ``state.finding_drafts`` (FND-nnn, each with ``criterion_ids``), ``state.finding_meta``
(created_phase=assess, call ID, model, prompt hash), ``state.sound_area_drafts``,
``state.coverage`` (every criterion: findings / no_issue / not_applicable).
Refusal: one retry with professional-review framing, then the section is recorded in
``state.declined_sections`` and the phase completes (robustness LLM-06).
"""

from __future__ import annotations

from sit_review_agent.context import RunContext
from sit_review_agent.states import PhaseName


class AssessPhase:
    name = PhaseName.ASSESS

    async def run(self, ctx: RunContext) -> RunContext:
        raise NotImplementedError("phase 1: AssessPhase.run (workstream A)")
