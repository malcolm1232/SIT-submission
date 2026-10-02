"""``plan`` (LLM, workstream A). Prompt: ``prompts/plan.md``. Output: ``PlanOutput``.

Reads: intent summary, frozen registry, every configured criterion, enabled capabilities
(``config.tools.capabilities`` of enabled servers), remaining time and tool-call budget.
Writes: ``ctx.state.plan`` (ResearchPlan; one or more questions per applicable criterion, each with
a fixed capability). ``--plan-only`` prints the plan and the orchestrator stops after this phase.
With ``plan_approval: true`` the plan is printed and the run waits for approval before research.
"""

from __future__ import annotations

from sit_review_agent.context import RunContext
from sit_review_agent.states import PhaseName


class PlanPhase:
    name = PhaseName.PLAN

    async def run(self, ctx: RunContext) -> RunContext:
        raise NotImplementedError("phase 1: PlanPhase.run (workstream A)")
