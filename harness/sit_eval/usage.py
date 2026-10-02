"""Usage completeness of one agent run: was every billed model call's usage recorded?

A model attempt that was killed or cut (run deadline, timeout, a crashed ``claude -p``, a dropped stream,
an interrupt) may have been billed but left no usage report. Since 2026-10-03 the runtime lists such
attempts in the manifest (``extra.model.calls_with_unrecorded_usage``: ``call_id``, ``stage``, ``purpose``,
``attempt``, ``wall_s``, ``reason``) and sets ``extra.model.cost_usd_lower_bound``; ``usage.cost_usd``
and the token totals then sum the recorded calls only, so they are lower bounds of the run's true usage.

The harness (SIT FABLE ruling #28, ``docs/USER_DECISIONS.md``) reads completeness in this order:

1. the manifest field when present (``complete`` when the list is empty, else ``unrecorded``);
2. for a manifest that predates the field, the same rule the runtime applies to an older ``llm.jsonl``
   (:func:`unrecorded_reason`, implemented here once more because the harness must not import the
   runtime's manifest module; ``tests/eval_harness/test_eval_usage_completeness.py`` pins it to the
   runtime's behaviour), reading the call log beside ``report.json`` by code only;
3. else ``unknown``: the recorded figures may or may not be complete, and are reported as lower bounds.

A run that is not ``complete`` has null cost and token values in the ``efficiency`` metric, with the lower
bounds beside them; the aggregate's fully accounted median excludes it; the prereg pilot checkpoint can
fail on its lower bound but never pass on it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

COMPLETE = "complete"
UNRECORDED = "unrecorded"
UNKNOWN = "unknown"
STATUSES = (COMPLETE, UNRECORDED, UNKNOWN)

#: ``usage_reason`` codes of the ``efficiency`` metric when its cost and tokens are null.
REASON_UNRECORDED = "unrecorded_usage"
REASON_UNKNOWN = "usage_completeness_unknown"

#: The runtime's ``usage_unrecorded`` reasons (``sit_review_agent.llm.gateway.USAGE_UNRECORDED_REASONS``).
UNRECORDED_REASONS = {
    "deadline_cut": "deadline cut",
    "timeout_kill": "timeout kill",
    "process_fault": "process fault",
    "connection_lost": "connection lost",
    "interrupted": "interrupted",
}

#: Outcomes of an attempt killed before it could report usage, in an ``llm.jsonl`` written before
#: 2026-10-03 (those entries logged zero usage instead of ``usage_unrecorded``).
_LEGACY_KILLED = {"LLMDeadlineError": "deadline_cut", "LLMTimeoutError": "timeout_kill"}

MANIFEST_FIELD = "calls_with_unrecorded_usage"
CALL_LOG = "llm.jsonl"
SOURCE_MANIFEST = f"manifest extra.model.{MANIFEST_FIELD}"
SOURCE_CALL_LOG = (f"{CALL_LOG} beside report.json, read by the runtime's legacy rule (the manifest predates "
                   f"extra.model.{MANIFEST_FIELD})")
SOURCE_NONE = (f"none: the manifest predates extra.model.{MANIFEST_FIELD} and no {CALL_LOG} is beside "
               "report.json")


def unrecorded_reason(entry: Mapping[str, Any]) -> str | None:
    """Why a sent attempt's usage is unknown, or ``None`` when its usage is known (or nothing was sent).

    The runtime's rule (``sit_review_agent.manifest.unrecorded_reason``, commit 8ef32d4): a new entry says
    it (``usage_unrecorded``); an older entry of a deadline cut or timeout with zero usage, no cost and no
    HTTP status is read the same way. Unsent entries, injected faults, replayed and fake entries spent
    nothing.
    """
    if entry.get("usage_unrecorded"):
        return str(entry["usage_unrecorded"])
    if entry.get("sent") is False or "fault" in entry or entry.get("replayed") or entry.get("fake"):
        return None
    reason = _LEGACY_KILLED.get(str(entry.get("outcome")))
    usage = entry.get("usage")
    if reason and isinstance(usage, dict) and not any(usage.values()) and entry.get("call_cost_usd") is None \
            and entry.get("status_code") is None:
        return reason
    return None


@dataclass(frozen=True)
class UsageCompleteness:
    status: str                                   # complete | unrecorded | unknown
    source: str                                   # where it was read from (one of the SOURCE_* texts)
    calls: tuple[dict[str, Any], ...] = field(default_factory=tuple)   # the attempts with unrecorded usage

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"usage completeness status {self.status!r} is not one of {STATUSES}")
        if self.status == UNRECORDED and not self.calls:
            raise ValueError("an unrecorded status needs at least one call")
        if self.status != UNRECORDED and self.calls:
            raise ValueError(f"status {self.status} cannot list unrecorded calls")

    @property
    def lower_bound(self) -> bool:
        """True when the recorded cost and tokens are a lower bound (not known to be complete)."""
        return self.status != COMPLETE

    @property
    def count(self) -> int:
        return len(self.calls)

    @property
    def reason(self) -> str | None:
        """The ``usage_reason`` code of the ``efficiency`` metric (``None`` for a complete run)."""
        return {COMPLETE: None, UNRECORDED: REASON_UNRECORDED, UNKNOWN: REASON_UNKNOWN}[self.status]


def _call_row(entry: Mapping[str, Any], reason: str) -> dict[str, Any]:
    wall = entry.get("elapsed_s")
    return {"call_id": entry.get("call_id"), "stage": entry.get("phase"), "purpose": entry.get("purpose"),
            "attempt": entry.get("attempt"), "wall_s": round(float(wall), 3) if isinstance(wall, int | float) else None,
            "reason": reason}


def from_manifest(manifest: Mapping[str, Any] | None) -> UsageCompleteness | None:
    """Completeness from ``extra.model.calls_with_unrecorded_usage``; ``None`` when the manifest predates it."""
    model = ((manifest or {}).get("extra") or {}).get("model") or {}
    if MANIFEST_FIELD not in model:
        return None
    calls = tuple(dict(c) for c in (model.get(MANIFEST_FIELD) or []))
    return UsageCompleteness(status=UNRECORDED if calls else COMPLETE, source=SOURCE_MANIFEST, calls=calls)


def from_call_log(path: Path) -> UsageCompleteness:
    """Completeness by the legacy rule over every entry of an ``llm.jsonl`` (read by code; never printed)."""
    calls: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if not isinstance(entry, dict):
                continue
            reason = unrecorded_reason(entry)
            if reason is not None:
                calls.append(_call_row(entry, reason))
    return UsageCompleteness(status=UNRECORDED if calls else COMPLETE, source=SOURCE_CALL_LOG, calls=tuple(calls))


def usage_completeness(manifest: Mapping[str, Any] | None, run_dir: Path | None) -> UsageCompleteness:
    """The run's usage completeness: the manifest field, else the call log beside the report, else unknown."""
    uc = from_manifest(manifest)
    if uc is not None:
        return uc
    log = Path(run_dir) / CALL_LOG if run_dir is not None else None
    if log is not None and log.is_file():
        return from_call_log(log)
    return UsageCompleteness(status=UNKNOWN, source=SOURCE_NONE)


def describe(uc: UsageCompleteness) -> str:
    """The words a cost figure is qualified with (``""`` for a complete run)."""
    if uc.status == COMPLETE:
        return ""
    if uc.status == UNKNOWN:
        return (f"{REASON_UNKNOWN}: the run's usage may be incomplete ({uc.source}); its recorded cost and tokens "
                "are reported as lower bounds only")
    calls = "; ".join(f"{c.get('call_id') or '?'} {c.get('stage') or '?'}"
                      + (f" attempt {c['attempt']}" if c.get("attempt") is not None else "")
                      + f", {UNRECORDED_REASONS.get(str(c.get('reason')), c.get('reason'))}"
                      + (f", {c['wall_s']:g} s" if isinstance(c.get("wall_s"), int | float) else "")
                      for c in uc.calls)
    n = uc.count
    return (f"{REASON_UNRECORDED}: {n} model call{'s' if n != 1 else ''} with unrecorded usage ({calls}); their "
            "tokens and cost are not in the totals, so the recorded cost and tokens are lower bounds")


def warnings_for(uc: UsageCompleteness) -> list[str]:
    """The ``scores.json`` warnings a run's completeness adds (none for a complete run read from the manifest)."""
    out: list[str] = []
    if uc.source == SOURCE_CALL_LOG:
        out.append(f"usage completeness was read from {uc.source}")
    if uc.status == UNRECORDED:
        out.append(f"usage incomplete: {describe(uc)}; the efficiency metric's cost and tokens are null and the "
                   "lower bounds are reported beside them")
    elif uc.status == UNKNOWN:
        out.append(f"usage completeness unknown: {describe(uc)}; the efficiency metric's cost and tokens are null")
    return out


def lower_bound_of(value: Mapping[str, Any] | None, name: str) -> float | None:
    """A run's lower bound for ``name`` (``cost_usd``, ``input_tokens``, ...) from its ``efficiency`` value: the
    figure itself for a complete run, else ``<name>_lower_bound``."""
    if not value:
        return None
    if value.get("usage_completeness") == COMPLETE:
        return value.get(name)
    if f"{name}_lower_bound" in value:
        return value.get(f"{name}_lower_bound")
    # a scores.json written before ruling #28 carries the figure itself and no completeness: unknown, so a bound
    return value.get(name)


def is_complete(value: Mapping[str, Any] | None) -> bool:
    return bool(value) and value.get("usage_completeness") == COMPLETE


def status_of(value: Mapping[str, Any] | None) -> str:
    """The completeness status recorded in an ``efficiency`` value (``unknown`` when it carries none)."""
    s = (value or {}).get("usage_completeness")
    return s if s in STATUSES else UNKNOWN


__all__: Sequence[str] = ["COMPLETE", "UNRECORDED", "UNKNOWN", "UsageCompleteness", "unrecorded_reason",
                          "usage_completeness", "from_manifest", "from_call_log", "describe", "warnings_for",
                          "lower_bound_of", "is_complete", "status_of"]
