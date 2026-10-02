"""The phase contract.

A phase is an object with a ``name`` and ``async run(ctx) -> RunContext``. It may mutate and
return ``ctx`` (the orchestrator uses the returned object). Rules:

1. Read inputs from ``ctx.state`` / ``ctx.documents`` / ``ctx.config``; write outputs to
   ``ctx.state`` (fields listed in each phase's docstring under "Writes").
2. Model calls only via ``ctx.llm`` with one ``conversation_id`` per phase and
   ``effort=ctx.config.effort_for(name)``; prompts only via ``ctx.prompts.render``; record call
   IDs in ``ctx.state.llm_calls[name]``.
3. Tool calls only via ``ctx.tools``; evidence only via ``ctx.ledger``; never invent a URL.
4. Expected failures (tool down, refusal after the retry, budget) become degradations
   (``ctx.state.add_degradation``) and the phase completes; only ``LLMError`` subclasses that the
   gateway raised after its retry budget, and bugs, propagate (the orchestrator checkpoints).
5. A phase must be safe to re-run from the previous checkpoint (resume).
6. Emit a progress line at least every 10 s of wall time (``ctx.emit`` or ``progress.heartbeat``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sit_review_agent.context import RunContext
from sit_review_agent.states import PhaseName


@runtime_checkable
class Phase(Protocol):
    name: PhaseName

    async def run(self, ctx: RunContext) -> RunContext:
        ...
