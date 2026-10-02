"""What the run spent, as the phases count it (``state.budget``, read by the ``budget_tokens`` stop rule).

Every model call that was billed is counted, whether it returned a result or raised: a truncated,
declined or schema-invalid answer costs the same tokens as a usable one. :func:`add_usage` takes
``LLMResult.usage`` or ``LLMError.usage``; ``None`` (no attempt reported usage) adds nothing.
"""

from __future__ import annotations

from sit_review_agent.llm.gateway import Usage
from sit_review_agent.state.run_state import Budget


def add_usage(budget: Budget, usage: Usage | None) -> None:
    """Add ``usage`` to the run's token counters (input includes cache reads and writes)."""
    if usage is None:
        return
    budget.input_tokens += usage.total_input_tokens
    budget.output_tokens += usage.output_tokens
    budget.cache_read_input_tokens += usage.cache_read_input_tokens
    budget.cache_creation_input_tokens += usage.cache_creation_input_tokens
