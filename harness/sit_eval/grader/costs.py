"""Call planning, cost estimates and the hard budget stop.

Prices are USD per million tokens from ``research/models/cost_model.py`` (dated 2026-10-02, from
the claude-api skill). Estimates use list prices with no caching and no batch discount, so they are
an upper bound for the API path; ``claude -p`` reports its own (notional) cost per call, which the
budget uses when the client returns it. Token counts are estimated from characters (3.5 per token,
conservative for JSON-heavy text) until a live call reports real usage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

#: (input, output) USD per MTok.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
}
DEFAULT_PRICE = PRICES["claude-opus-5-5"]
CHARS_PER_TOKEN = 3.5
#: Expected output: Pass A grows with the number of findings; Pass B is roughly fixed. The
#: thinking allowance covers adaptive thinking. It was 3000; the verifier's live smoke calls
#: (2026-10-02, `claude -p`, Haiku 4.5, a two-finding review) used about 10.5k thinking tokens per
#: call, so the old value let the pre-call budget check pass calls costing about 3x the estimate.
PASS_A_OUT_BASE, PASS_A_OUT_PER_FINDING = 600, 450
PASS_B_OUT = 7000
THINKING_ALLOWANCE = 12000
#: Wall time per call, seconds (brief: Opus via claude -p at high effort, 20-60 s; longer for a long Pass B).
SECONDS_PER_CALL = (20, 60)


#: Float tolerance for the budget comparison (a millionth of a cent).
BUDGET_EPS_USD = 1e-9


class BudgetExceeded(RuntimeError):
    """The next call would take the spend past ``max_cost_usd``; nothing was sent."""


def tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def price(model: str) -> tuple[float, float]:
    return PRICES.get(model, DEFAULT_PRICE)


def estimate_call(model: str, input_chars: int, output_tokens: int) -> dict[str, Any]:
    pin, pout = price(model)
    tin = math.ceil(input_chars / CHARS_PER_TOKEN)
    tout = output_tokens + THINKING_ALLOWANCE
    return {"input_tokens": tin, "output_tokens": tout, "cost_usd": round(tin * pin / 1e6 + tout * pout / 1e6, 4)}


def actual_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = price(model)
    return input_tokens * pin / 1e6 + output_tokens * pout / 1e6


@dataclass
class Budget:
    """Shared across every call of a grade (and across grades in a meta-validation run)."""

    max_cost_usd: float | None = None
    spent_usd: float = 0.0
    calls: int = 0
    refused: list[dict[str, Any]] = field(default_factory=list)

    def check(self, purpose: str, estimate_usd: float) -> None:
        # A call that lands exactly on the limit is allowed; the tolerance stops float sums such as
        # 0.1 + 0.2 (= 0.30000000000000004) from refusing it.
        if self.max_cost_usd is not None and self.spent_usd + estimate_usd > self.max_cost_usd + BUDGET_EPS_USD:
            self.refused.append({"purpose": purpose, "estimate_usd": round(estimate_usd, 4),
                                 "spent_usd": round(self.spent_usd, 4)})
            raise BudgetExceeded(
                f"{purpose}: spent ${self.spent_usd:.4f} + estimated ${estimate_usd:.4f} would exceed "
                f"--max-cost-usd ${self.max_cost_usd:.4f}; stopped before the call")

    def add(self, usd: float) -> None:
        self.spent_usd += usd
        self.calls += 1
