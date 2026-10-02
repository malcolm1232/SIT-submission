"""``research`` (LLM + tools, workstream B). Prompt: ``prompts/research.md``. Output per
iteration: ``ResearchOutput``.

The hand-written tool loop (ADR-001; not ``tool_runner``): offer ``ctx.tools.list_tools()`` as API
tools; run ``tool_use`` blocks (parallel calls returned in ONE user message, failures as
``is_error``); turn every ok result into ledger entries (``tools.sources.extract_sources`` ->
``ctx.ledger.add_external``) and show the model the result text prefixed with the new ``EV-nnn``
IDs; evaluate the stop rules (``stop_rules.evaluate``) after every tool round and at the end of
every iteration; ``pause_turn`` is continued; up to ``stop_rules.max_research_iterations``.
Reads: plan, registry, ledger. Writes: question statuses/evidence on ``state.plan``,
``state.tool_calls``, ``state.queries_issued``, ``state.budget`` counters
(``new_sources_by_iteration``), ``state.unanswered_questions``, ``state.stop_reason``,
degradations (``tool_unavailable``, ``tool_error``, ``budget_or_deadline_hit``), registry hash per
iteration (``ctx.registry.record_iteration``). With ``ctx.tools is None`` it records a
``tool_unavailable`` degradation and returns (doc-only review).
"""

from __future__ import annotations

from sit_review_agent.context import RunContext
from sit_review_agent.states import PhaseName


class ResearchPhase:
    name = PhaseName.RESEARCH

    async def run(self, ctx: RunContext) -> RunContext:
        raise NotImplementedError("phase 2: ResearchPhase.run (workstream B)")
