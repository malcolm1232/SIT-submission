"""Stop-rule registry (docs/DEMO_DAY_RUNBOOK.md §4.1, §4.2 #2b).

Each rule is a function decorated with ``@register("<name>")``. It receives the run state, the
``stop_rules.yaml`` parameters and the elapsed wall time, and returns a :class:`StopDecision`.
``config/stop_rules.yaml`` ``active:`` lists the rules to evaluate. The reported code is always one
of the **closed** :class:`~sit_review_agent.models.StopReasonCode` values; a new rule reuses an
existing code and names itself in ``detail`` (e.g. ``two_sources_agree`` reports
``sufficient_evidence``). Cap rules are evaluated before decision rules.

New rules are appended at the END of this file (runbook).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import NamedTuple

from sit_review_agent.config import StopRulesConfig
from sit_review_agent.errors import ConfigError
from sit_review_agent.models import STOP_REASON_GROUP, StopReason, StopReasonCode, StopReasonGroup
from sit_review_agent.state.run_state import RunState


class StopDecision(NamedTuple):
    stop: bool
    code: StopReasonCode
    detail: str | None = None


RuleFn = Callable[[RunState, StopRulesConfig, float], StopDecision]
REGISTRY: dict[str, RuleFn] = {}


def register(name: str) -> Callable[[RuleFn], RuleFn]:
    def deco(fn: RuleFn) -> RuleFn:
        if name in REGISTRY:
            raise ValueError(f"stop rule {name!r} registered twice")
        REGISTRY[name] = fn
        return fn

    return deco


def resolve(active: Sequence[str]) -> list[tuple[str, RuleFn]]:
    """Look up the ``active`` names; unknown names are a ConfigError (checked at run start)."""
    unknown = [n for n in active if n not in REGISTRY]
    if unknown:
        raise ConfigError(f"unknown stop rules in stop_rules.yaml active: {unknown}; registered: {sorted(REGISTRY)}")
    return [(n, REGISTRY[n]) for n in active]


def evaluate(state: RunState, params: StopRulesConfig, elapsed_s: float) -> StopReason | None:
    """First firing rule, caps first (in ``active`` order within each group), or ``None``.

    The research-iteration cap (``max_research_iterations``) is always on; it reports
    ``budget_tool_calls`` with detail ``max_research_iterations`` (the closed enum has no
    iteration code)."""
    decisions = [(n, fn(state, params, elapsed_s)) for n, fn in resolve(params.active)]
    fired = [(n, d) for n, d in decisions if d.stop]
    fired.sort(key=lambda nd: STOP_REASON_GROUP[nd[1].code] is not StopReasonGroup.CAP)
    if fired:
        name, d = fired[0]
        return StopReason.of(d.code, d.detail if d.detail is not None else name)
    if state.budget.research_iterations >= params.max_research_iterations:
        return StopReason.of(StopReasonCode.BUDGET_TOOL_CALLS, "max_research_iterations")
    return None


#: Caps the orchestrator checks between phases (the tool-call cap is enforced inside research).
BETWEEN_PHASE_CAPS = frozenset({StopReasonCode.DEADLINE, StopReasonCode.BUDGET_TOKENS})


def check_caps(state: RunState, params: StopRulesConfig, elapsed_s: float) -> StopReason | None:
    """Active deadline / token-budget rules only (used by the orchestrator before each phase)."""
    for name, fn in resolve(params.active):
        d = fn(state, params, elapsed_s)
        if d.stop and d.code in BETWEEN_PHASE_CAPS:
            return StopReason.of(d.code, d.detail if d.detail is not None else name)
    return None


# ------------------------------------------------------------------------------------ caps


@register("budget_tool_calls")
def budget_tool_calls(state: RunState, p: StopRulesConfig, elapsed_s: float) -> StopDecision:
    return StopDecision(state.budget.tool_calls >= p.max_tool_calls, StopReasonCode.BUDGET_TOOL_CALLS)


@register("budget_tokens")
def budget_tokens(state: RunState, p: StopRulesConfig, elapsed_s: float) -> StopDecision:
    over_in = state.budget.input_tokens >= p.max_input_tokens
    over_out = p.max_output_tokens is not None and state.budget.output_tokens >= p.max_output_tokens
    return StopDecision(over_in or over_out, StopReasonCode.BUDGET_TOKENS)


@register("deadline")
def deadline(state: RunState, p: StopRulesConfig, elapsed_s: float) -> StopDecision:
    """Fires ``report_reserve_seconds`` before the deadline so verify + report still fit."""
    return StopDecision(elapsed_s >= p.deadline_seconds - p.report_reserve_seconds, StopReasonCode.DEADLINE)


# ------------------------------------------------------------------------------- decisions


@register("no_marginal_gain")
def no_marginal_gain(state: RunState, p: StopRulesConfig, elapsed_s: float) -> StopDecision:
    """The last ``no_marginal_gain_window`` research iterations added no new ledger sources."""
    recent = state.budget.new_sources_by_iteration[-p.no_marginal_gain_window:]
    stop = len(recent) >= p.no_marginal_gain_window and all(n == 0 for n in recent)
    return StopDecision(stop, StopReasonCode.NO_MARGINAL_GAIN)


@register("sufficient_evidence")
def sufficient_evidence(state: RunState, p: StopRulesConfig, elapsed_s: float) -> StopDecision:
    """Every planned question that needs external evidence is answered with >= 1 ledger entry."""
    if state.plan is None:
        return StopDecision(False, StopReasonCode.SUFFICIENT_EVIDENCE)
    ext = [q for q in state.plan.questions if q.needs_external]
    done = all(q.status == "answered" and q.evidence_ids for q in ext)
    return StopDecision(done, StopReasonCode.SUFFICIENT_EVIDENCE)
