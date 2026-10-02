"""Rule matching shared by the two fault injectors (robustness §5.1-5.3; workstream B).

:class:`~sit_review_agent.tools.gateway.FaultInjectingGateway` (``mcp:`` rules) and
:class:`~sit_review_agent.llm.gateway.FaultInjectingLLMGateway` (``llm:`` rules) both sit *below*
the retry policy, read time only from the injected clock, and draw ``flaky`` outcomes from
``Random(sha256(seed, key...))`` so a given call always gets the same outcome regardless of task
scheduling (robustness §5.1 "Determinism"; Python's ``hash`` is salted, so SHA-256 is used).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import random
import re
from typing import Any

from sit_review_agent.tools.faults import FaultMatch, FaultRule, FaultSchedule, FaultSpec, FaultType


def seeded_rng(*parts: Any) -> random.Random:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def match_rule(m: FaultMatch, *, server: str | None = None, tool: str | None = None,
               call_index: int | None = None, nth: int | None = None, stage: str | None = None,
               attempt: int | None = None, elapsed_s: float = 0.0, args: dict[str, Any] | None = None) -> bool:
    """All set match keys must hold (AND). A key the layer cannot evaluate (``server`` on the LLM
    layer, ``attempt`` on a layer that does not count attempts) does not match."""
    if m.server is not None and (server is None or not fnmatch.fnmatchcase(server, m.server)):
        return False
    if m.tool is not None and (tool is None or not fnmatch.fnmatchcase(tool, m.tool)):
        return False
    if m.call_index is not None and call_index != m.call_index:
        return False
    if m.nth is not None and (nth is None or nth not in m.nth):
        return False
    if m.stage is not None and stage != m.stage:
        return False
    if m.attempt is not None and attempt != m.attempt:
        return False
    if m.after_seconds is not None and elapsed_s < m.after_seconds:
        return False
    if m.args_regex is not None:
        text = json.dumps(args or {}, sort_keys=True, ensure_ascii=False)
        if not re.search(m.args_regex, text):
            return False
    return True


def param(spec: FaultSpec, name: str, default: Any = None) -> Any:
    extra = spec.model_extra or {}
    return extra.get(name, default)


def down_active(rule: FaultRule, elapsed_s: float) -> bool:
    """``down {duration_seconds?}``: active from ``after_seconds`` (or 0) for ``duration_seconds``
    (or for the whole run)."""
    start = rule.match.after_seconds or 0.0
    dur = param(rule.fault, "duration_seconds")
    return elapsed_s >= start and (dur is None or elapsed_s < start + float(dur))


def offline_now(schedule: FaultSchedule, elapsed_s: float) -> bool:
    """``network: [{type: offline, from_seconds, duration_seconds}]``: every transport fails."""
    for spec in schedule.network:
        if spec.type is not FaultType.OFFLINE:
            continue
        start = float(param(spec, "from_seconds", 0.0))
        dur = param(spec, "duration_seconds")
        if elapsed_s >= start and (dur is None or elapsed_s < start + float(dur)):
            return True
    return False


def resolve_flaky(spec: FaultSpec, rng: random.Random) -> FaultSpec | None:
    """``flaky {p, inner: [...]}``: with probability ``p`` one of ``inner`` (uniform), else no fault."""
    if spec.type is not FaultType.FLAKY:
        return spec
    p = float(param(spec, "p", 0.0))
    inner = param(spec, "inner", []) or []
    if not inner or rng.random() >= p:
        return None
    choice = inner[rng.randrange(len(inner))]
    return FaultSpec.model_validate(choice) if isinstance(choice, dict) else None


def latency_seconds(spec: FaultSpec, rng: random.Random) -> float:
    """``latency {seconds}`` or ``latency {min, max}`` (seeded uniform)."""
    if param(spec, "seconds") is not None:
        return float(param(spec, "seconds"))
    lo, hi = float(param(spec, "min", 0.0)), float(param(spec, "max", 0.0))
    return rng.uniform(lo, hi) if hi > lo else lo
