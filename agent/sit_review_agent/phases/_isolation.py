"""Isolated run state for work that runs side by side (latency redesign, design section 4).

Stage 1 runs understand, plan, research and the assess shards concurrently. Each of them works on
its own deep copy of the run state (and its own copy of the decision registry), so a checkpoint
written while one member is still running never holds that member's half-written state, and two
members never interleave writes to one list. When a member ends, what it changed is merged back:

* fields it replaced (``intent_summary``, ``plan``, ``tool_calls``, ...) are copied over;
* the lists every phase appends to (``degradations``, ``refusals``, ``fallback_events``,
  ``declined_sections``) and the call IDs per phase get the member's new items appended, so
  degradation IDs are renumbered in the order of merging;
* the token and tool-call counters of ``budget`` get the member's increase added.

A member that only appends and counts (an assess shard) is summarised as a :class:`StateDelta`,
which is serialisable, so a finished shard can be stored on disk and merged on resume.

Private to the phases and the orchestrator; nothing here is a frozen interface.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sit_review_agent.context import RunContext
from sit_review_agent.models import Degradation, FallbackEvent
from sit_review_agent.state.decision_registry import DecisionRegistry
from sit_review_agent.state.run_state import RunState
from sit_review_agent.states import PhaseName

#: ``Budget`` counters that members add to (merged as the member's increase).
BUDGET_COUNTERS = ("tool_calls", "input_tokens", "output_tokens", "cache_read_input_tokens",
                   "cache_creation_input_tokens")
#: ``Budget`` fields a member replaces (research's iteration record, per-phase seconds).
BUDGET_REPLACED = ("research_iterations", "new_sources_by_iteration", "phase_seconds")
#: Run-state lists every phase appends to.
APPENDED = ("degradations", "refusals", "fallback_events", "declined_sections")
#: Run-state fields the orchestrator owns; never merged from a member.
ORCHESTRATOR_FIELDS = frozenset({"completed_phases", "current_phase", "budget", "llm_calls", *APPENDED})


class MemberInterrupted(Exception):
    """Ctrl-C (``KeyboardInterrupt``) raised inside a concurrent task (a stage 1 member or an assess
    shard). A ``KeyboardInterrupt`` left inside an asyncio task escapes the event loop past every
    handler; this one is re-raised by the orchestrator as ``RunInterrupted`` (exit 130)."""


async def guarded(coro: Any) -> Any:
    """Await ``coro``, turning ``KeyboardInterrupt`` into :class:`MemberInterrupted`."""
    try:
        return await coro
    except KeyboardInterrupt as exc:
        raise MemberInterrupted("interrupted") from exc


class StateDelta(BaseModel):
    """What an append-and-count member (an assess shard) added to the run state."""

    model_config = ConfigDict(extra="forbid")

    degradations: list[Degradation] = Field(default_factory=list)
    refusals: list[dict[str, Any]] = Field(default_factory=list)
    fallback_events: list[FallbackEvent] = Field(default_factory=list)
    declined_sections: list[str] = Field(default_factory=list)
    llm_calls: dict[str, list[str]] = Field(default_factory=dict)
    budget: dict[str, int] = Field(default_factory=dict)


def clone_registry(reg: DecisionRegistry) -> DecisionRegistry:
    out = DecisionRegistry([e.model_copy(deep=True) for e in reg.entries()], frozen=reg.frozen)
    out._hashes = [h.model_copy() for h in reg.hashes()]
    return out


def same_registry(a: DecisionRegistry, b: DecisionRegistry) -> bool:
    return a.frozen == b.frozen and a.entries() == b.entries() and a.hashes() == b.hashes()


@dataclasses.dataclass
class Isolated:
    """A member's context and what it started from (for :func:`merge_member`)."""

    ctx: RunContext
    base: RunState
    base_registry: DecisionRegistry


def isolate(ctx: RunContext, phase: PhaseName) -> Isolated:
    """A context for ``phase`` with its own copy of the run state and of the decision registry; the
    other services (gateways, ledger, documents, progress) are shared."""
    state = ctx.state.model_copy(deep=True)
    state.current_phase = phase
    member = dataclasses.replace(ctx, state=state, registry=clone_registry(ctx.registry))
    return Isolated(ctx=member, base=ctx.state.model_copy(deep=True), base_registry=clone_registry(ctx.registry))


def state_delta(base: RunState, final: RunState) -> StateDelta:
    """The appended items and counter increases of ``final`` over ``base``."""
    calls: dict[str, list[str]] = {}
    for key, ids in final.llm_calls.items():
        new = ids[len(base.llm_calls.get(key, [])):]
        if new:
            calls[key] = list(new)
    return StateDelta(
        degradations=[d.model_copy() for d in final.degradations[len(base.degradations):]],
        refusals=[dict(r) for r in final.refusals[len(base.refusals):]],
        fallback_events=[f.model_copy() for f in final.fallback_events[len(base.fallback_events):]],
        declined_sections=[s for s in final.declined_sections if s not in base.declined_sections],
        llm_calls=calls,
        budget={k: getattr(final.budget, k) - getattr(base.budget, k) for k in BUDGET_COUNTERS
                if getattr(final.budget, k) != getattr(base.budget, k)})


def apply_delta(state: RunState, delta: StateDelta) -> None:
    """Append ``delta`` to ``state``: degradations get the next IDs of ``state``."""
    for d in delta.degradations:
        state.add_degradation(d.type, d.event, d.impact)
    state.refusals.extend(dict(r) for r in delta.refusals)
    state.fallback_events.extend(f.model_copy() for f in delta.fallback_events)
    for s in delta.declined_sections:
        if s not in state.declined_sections:
            state.declined_sections.append(s)
    for key, ids in delta.llm_calls.items():
        state.llm_calls.setdefault(key, []).extend(ids)
    for k, v in delta.budget.items():
        setattr(state.budget, k, getattr(state.budget, k) + v)


def merge_member(ctx: RunContext, iso: Isolated) -> None:
    """Merge a member that ran on ``iso = isolate(ctx, ...)`` into ``ctx``: replaced fields,
    appended items, counters, the registry (when the member changed it) and ``plan_only``."""
    base, final = iso.base, iso.ctx.state
    for name in RunState.model_fields:
        if name in ORCHESTRATOR_FIELDS:
            continue
        before, after = getattr(base, name), getattr(final, name)
        if before != after:
            setattr(ctx.state, name, _copy(after))
    for name in BUDGET_REPLACED:
        before, after = getattr(base.budget, name), getattr(final.budget, name)
        if name == "phase_seconds":
            ctx.state.budget.phase_seconds.update({k: v for k, v in after.items() if before.get(k) != v})
        elif before != after:
            setattr(ctx.state.budget, name, _copy(after))
    apply_delta(ctx.state, state_delta(base, final))
    if not same_registry(iso.ctx.registry, iso.base_registry):
        ctx.registry = clone_registry(iso.ctx.registry)
    if iso.ctx.plan_only:
        ctx.plan_only = True


def _copy(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_copy(deep=True)
    if isinstance(value, list):
        return [_copy(v) for v in value]
    if isinstance(value, dict):
        return {k: _copy(v) for k, v in value.items()}
    return value
