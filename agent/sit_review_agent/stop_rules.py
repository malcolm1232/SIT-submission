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


# --------------------------------------------------------------- the sufficient_evidence gate

#: ``detail`` prefix of a stop reason that was ``sufficient_evidence`` until the gate below refused it.
NOT_SUFFICIENT = "sufficient_evidence not met"
#: ``detail`` of the reason research records when no plan question needs external evidence (research
#: skipped). The gate leaves it as it was before the gate existed: nothing was tried, so no other code fits.
NO_EXTERNAL_QUESTIONS = "no_external_questions"


class EvidenceTally(NamedTuple):
    questions: int
    answered: int
    cited_external: int

    def sufficient(self) -> bool:
        """At least half the plan's questions answered (half rounded up: 3 of 6, 3 of 5), or at
        least two external ledger entries cited by a finding across the run."""
        half = -(-self.questions // 2)
        return (self.questions > 0 and self.answered >= half) or self.cited_external >= 2

    def describe(self) -> str:
        return (f"{self.answered} of {self.questions} plan question(s) answered, "
                f"{self.cited_external} external source(s) cited by a finding")


def evidence_tally(state: RunState, ledger: object) -> EvidenceTally:
    """The counts the ``sufficient_evidence`` gate reads: plan questions, those answered, and the
    external ledger entries (``ledger``: iterable of ledger entries) that a finding cites."""
    from sit_review_agent.models import SourceType

    questions = list(state.plan.questions) if state.plan is not None else []
    external = {e.evidence_id for e in ledger  # type: ignore[attr-defined]
                if getattr(e, "source_type", None) is SourceType.EXTERNAL}
    cited = {ev.evidence_id for f in state.findings for ev in f.evidence}
    return EvidenceTally(questions=len(questions), answered=sum(q.status == "answered" for q in questions),
                         cited_external=len(external & cited))


def fitting_reason(state: RunState, params: StopRulesConfig, tally: EvidenceTally, was: str | None) -> StopReason:
    """The existing reason that fits a research end the gate refused as ``sufficient_evidence``: the
    tool-call or round limit when one was reached, ``tool_failure`` when calls were made and none
    succeeded, else ``no_marginal_gain``. ``detail`` names the refused claim and the counts."""
    from sit_review_agent.models import ToolCallStatus

    note = f"{NOT_SUFFICIENT} ({was or 'sufficient_evidence'}): {tally.describe()}"
    if state.budget.tool_calls >= params.max_tool_calls:
        return StopReason.of(StopReasonCode.BUDGET_TOOL_CALLS, f"max_tool_calls; {note}")
    if state.budget.research_iterations >= params.max_research_iterations:
        return StopReason.of(StopReasonCode.BUDGET_TOOL_CALLS, f"max_research_iterations; {note}")
    if state.tool_calls and not any(c.status is ToolCallStatus.OK for c in state.tool_calls):
        return StopReason.of(StopReasonCode.TOOL_FAILURE, note)
    return StopReason.of(StopReasonCode.NO_MARGINAL_GAIN, note)


def settle_sufficient_evidence(stop: StopReason, state: RunState, params: StopRulesConfig,
                               ledger: object) -> StopReason:
    """``stop`` with the ``sufficient_evidence`` gate applied: a ``sufficient_evidence`` that the
    counts do not support becomes :func:`fitting_reason`; a reason this gate refused earlier (in
    research, before any finding cited a source) becomes ``sufficient_evidence`` again when the
    counts now support it. Any other reason is returned unchanged."""
    if stop.code is StopReasonCode.SUFFICIENT_EVIDENCE and stop.detail == NO_EXTERNAL_QUESTIONS and not any(
            getattr(q, "needs_external", False) and getattr(q, "capability", "none") != "none"
            for q in (state.plan.questions if state.plan is not None else [])):
        return stop                         # research skipped: nothing was tried, the reason stays as before
    tally = evidence_tally(state, ledger)
    if stop.code is StopReasonCode.SUFFICIENT_EVIDENCE:
        return stop if tally.sufficient() else fitting_reason(state, params, tally, stop.detail)
    detail = stop.detail or ""
    at = detail.find(f"{NOT_SUFFICIENT} (")
    if at >= 0 and tally.sufficient():
        was = detail[at + len(NOT_SUFFICIENT) + 2:].split("):", 1)[0]
        return StopReason.of(StopReasonCode.SUFFICIENT_EVIDENCE, f"{was}; {tally.describe()}")
    return stop
