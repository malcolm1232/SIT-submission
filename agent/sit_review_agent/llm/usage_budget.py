"""What the run spent, as the phases count it (``state.budget``, read by the ``budget_tokens`` stop rule),
and how a cost total is qualified when some of it is unknown.

Every model call that was billed is counted, whether it returned a result or raised: a truncated,
declined or schema-invalid answer costs the same tokens as a usable one. :func:`add_usage` takes
``LLMResult.usage`` or ``LLMError.usage``; ``None`` (no attempt reported usage) adds nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sit_review_agent.llm.gateway import USAGE_UNRECORDED_REASONS, Usage
from sit_review_agent.state.run_state import Budget


def add_usage(budget: Budget, usage: Usage | None) -> None:
    """Add ``usage`` to the run's token counters (input includes cache reads and writes)."""
    if usage is None:
        return
    budget.input_tokens += usage.total_input_tokens
    budget.output_tokens += usage.output_tokens
    budget.cache_read_input_tokens += usage.cache_read_input_tokens
    budget.cache_creation_input_tokens += usage.cache_creation_input_tokens


def describe_unrecorded(calls: Sequence[Mapping[str, Any]]) -> str:
    """``"2 model calls with unrecorded usage (assess, deadline cut; plan, timeout kill)"``: the
    words every cost total is qualified with when the manifest's
    ``extra.model.calls_with_unrecorded_usage`` is not empty (``""`` when it is)."""
    if not calls:
        return ""
    what = "; ".join(f"{c.get('stage') or '?'}, {USAGE_UNRECORDED_REASONS.get(str(c.get('reason')), c.get('reason'))}"
                     for c in calls)
    return f"{len(calls)} model call{'s' if len(calls) != 1 else ''} with unrecorded usage ({what})"


def cost_lower_bound_line(manifest: Mapping[str, Any]) -> str | None:
    """The console line for a run whose cost total is a lower bound, else ``None``."""
    calls = ((manifest.get("extra") or {}).get("model") or {}).get("calls_with_unrecorded_usage") or []
    if not calls:
        return None
    cost = (manifest.get("usage") or {}).get("cost_usd") or 0.0
    return (f"cost ~${cost:.2f} is a lower bound: {describe_unrecorded(calls)}; their tokens and cost are "
            "not in the totals")
