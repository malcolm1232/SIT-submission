"""Fault schedules for the concurrent stage 1 (latency redesign of 2026-10-03, workstream W3 part B).

Stage 1 runs understand, plan, research (after both) and K assess shards side by side; a shard is
one criterion group of ``config/agent.yaml`` ``assess.shards``, and the shards of a run are
:meth:`sit_review_agent.config.AssessSettings.shards_for` of the run's criteria, numbered in that
order, which is their launch order. The schedules live in ``faults_concurrent/<ID>.yaml``, in the
format of ``faults/`` (research/robustness/README.md §5.2) plus two match keys on an ``llm:`` rule
of stage ``assess``:

* ``shard``: the shard index in launch order (0 .. K-1), or ``shard_of``: a criterion ID, naming
  the shard whose group holds that criterion (resolved to its index against the run's shards, so a
  schedule written this way follows any regrouping of ``assess.shards``; the committed schedules
  use it since the six-group config of USER_DECISIONS #40);
* ``shard_call``: the shard's own logical calls, 0-based (0 = its first call; 1 = its first
  follow-up call: the reframed retry after a refusal, the retry after a truncation, the repair turn).

``nth`` keeps its meaning: the stage's logical call index (``FaultInjectingLLMGateway``, fix 2 of
the robustness suite). The K shards start together, so their first calls are ``nth`` 0 .. K-1 in
launch order; a follow-up call of the one faulted shard comes after all K first calls, so its
``shard_call`` j (j >= 1) is ``nth`` K + j - 1. That numbering only holds when a single shard makes
follow-up calls, so a schedule that faults follow-up calls of one shard and faults any other shard
is refused. A ``process:`` entry may name a ``shard`` (or ``shard_of``) too (stage ``assess``); the
loader checks its range, writes the index as ``shard`` and adds ``shard_name``; applying it to that
shard alone is the orchestrator's job.

:func:`load_concurrent_schedule` resolves ``shard`` / ``shard_call`` into ``nth`` and returns the
agent's own :class:`~sit_review_agent.tools.faults.FaultSchedule`, so the result is what
``sit-review run --faults <file>`` loads. ``python tests/robustness/concurrent_schedules.py <ID>
--out <file>`` writes that resolved schedule for a CLI run (the integration pass, README.md).

The schedules execute only against the concurrent orchestrator (W2), which is not in this tree
yet: the results table shows them as "awaiting integration".
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from sit_review_agent.config import AssessShard, EffectiveConfig, load_config
from sit_review_agent.errors import ConfigError
from sit_review_agent.hashing import sha256_file
from sit_review_agent.tools.faults import FaultSchedule

CONCURRENT_DIR = Path(__file__).resolve().parent / "faults_concurrent"
SHARD_STAGE = "assess"


@dataclass(frozen=True)
class ShardTarget:
    """A shard a schedule faults: its launch index, group name and criteria."""

    index: int
    name: str
    criteria: tuple[str, ...]


@dataclass(frozen=True)
class ConcurrentSchedule:
    """A resolved schedule: the agent's ``FaultSchedule`` (``nth`` filled in, ``sha256`` of the
    source file), the run's shards in launch order and the shards the schedule faults."""

    schedule: FaultSchedule
    source: Path
    shards: tuple[AssessShard, ...]
    targets: tuple[ShardTarget, ...]

    @property
    def id(self) -> str:
        return self.schedule.id

    def agent_yaml(self) -> str:
        """The resolved schedule in the agent's format (no ``shard`` / ``shard_call`` keys left)."""
        data = self.schedule.model_dump(mode="json", exclude={"sha256"})
        for rule in [*data["mcp"], *data["llm"]]:                       # unset match keys only; a fault
            rule["match"] = {k: v for k, v in rule["match"].items() if v is not None}   # param may be null
        return yaml.safe_dump(data, sort_keys=False)


def run_shards(config: EffectiveConfig | None = None) -> list[AssessShard]:
    """The assess shards of a run with every configured criterion, in launch order."""
    cfg = config or load_config()
    return cfg.agent.assess.shards_for(c.id for c in cfg.criteria.criteria)


def shard_nth(shard: int, shard_call: int, k: int) -> int:
    """The stage-wide logical call index of call ``shard_call`` of shard ``shard`` of ``k``."""
    return shard if shard_call == 0 else k + shard_call - 1


def _index(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def load_concurrent_schedule(path: str | Path, shards: Sequence[AssessShard] | None = None) -> ConcurrentSchedule:
    """Load ``path`` and resolve its shard keys against ``shards`` (default: :func:`run_shards`).

    Raises :class:`ConfigError` naming the schedule for a shard index out of range, a shard key on
    another stage, ``shard`` together with ``nth``, an ambiguous follow-up numbering, or anything
    the agent's loader refuses."""
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"fault schedule not found: {p}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid fault schedule {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"invalid fault schedule {p}: not a mapping")
    sid = str(raw.get("id") or p.stem)
    run = tuple(shards if shards is not None else run_shards())
    k = len(run)
    names = ", ".join(f"{i} {s.name}" for i, s in enumerate(run))

    def refuse(msg: str) -> ConfigError:
        return ConfigError(f"fault schedule {sid} ({p}): {msg}")

    def check_shard(where: str, value: Any, stage: Any) -> int:
        if stage != SHARD_STAGE:
            raise refuse(f"{where}: shard needs stage {SHARD_STAGE}, got {stage!r}")
        if not _index(value) or not 0 <= value < k:
            raise refuse(f"{where}: shard {value!r} is out of range: this run has {k} assess shards ({names})")
        return int(value)

    def pop_shard(where: str, entry: dict[str, Any]) -> Any:
        """The entry's shard index: ``shard`` as given, or ``shard_of`` resolved (both popped)."""
        if "shard_of" not in entry:
            return entry.pop("shard")
        if "shard" in entry:
            raise refuse(f"{where}: shard and shard_of together (name the shard one way)")
        crit = entry.pop("shard_of")
        holders = [i for i, s in enumerate(run) if crit in s.criteria]
        if len(holders) != 1:
            raise refuse(f"{where}: shard_of {crit!r} is in no assess shard of this run ({names})")
        return holders[0]

    targeted: set[int] = set()
    follow_ups: set[int] = set()
    llm: list[Any] = []
    for i, rule in enumerate(raw.get("llm") or []):
        if not isinstance(rule, dict):
            raise refuse(f"llm[{i}]: a rule is a mapping")
        match = dict(rule.get("match") or {})
        if "shard" not in match and "shard_of" not in match:
            if "shard_call" in match:
                raise refuse(f"llm[{i}]: shard_call without shard")
            llm.append(rule)
            continue
        if "nth" in match:
            raise refuse(f"llm[{i}]: shard and nth together (shard_call names the shard's own calls)")
        s = check_shard(f"llm[{i}]", pop_shard(f"llm[{i}]", match), match.get("stage"))
        calls = match.pop("shard_call", None)
        if not isinstance(calls, list) or not calls or not all(_index(c) and c >= 0 for c in calls):
            raise refuse(f"llm[{i}]: shard_call must be a non-empty list of call indexes >= 0, got {calls!r}")
        match["nth"] = sorted({shard_nth(s, c, k) for c in calls})
        targeted.add(s)
        if any(c >= 1 for c in calls):
            follow_ups.add(s)
        llm.append({**rule, "match": match})
    if follow_ups and len(targeted) > 1:
        raise refuse(f"follow-up calls (shard_call >= 1) of shard {sorted(follow_ups)} are numbered after the "
                     f"{k} first calls only when no other shard is faulted; shards faulted: {sorted(targeted)}")

    process: list[Any] = []
    for i, spec in enumerate(raw.get("process") or []):
        if isinstance(spec, dict) and ("shard" in spec or "shard_of" in spec):
            spec = dict(spec)
            s = check_shard(f"process[{i}]", pop_shard(f"process[{i}]", spec), spec.get("stage"))
            targeted.add(s)
            spec = {**spec, "shard": s, "shard_name": run[s].name}
        process.append(spec)

    data = {**raw, "llm": llm, "process": process}
    try:
        sched = FaultSchedule.model_validate(data)
    except ValidationError as exc:
        raise refuse(f"invalid: {exc}") from exc
    targets = tuple(ShardTarget(s, run[s].name, tuple(run[s].criteria)) for s in sorted(targeted))
    return ConcurrentSchedule(sched.model_copy(update={"sha256": sha256_file(p)}), p, run, targets)


def schedule_path(sid: str) -> Path:
    return CONCURRENT_DIR / f"{sid}.yaml"


def concurrent_files() -> set[str]:
    return {p.stem for p in CONCURRENT_DIR.glob("*.yaml")}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write a concurrent-stage fault schedule in the agent's format.")
    ap.add_argument("sid", help="scenario ID under tests/robustness/faults_concurrent/")
    ap.add_argument("--out", type=Path, required=True, help="where to write the resolved schedule")
    args = ap.parse_args(argv)
    cs = load_concurrent_schedule(schedule_path(args.sid))
    args.out.write_text(f"# resolved from {cs.source.name} (shard -> nth, launch order: "
                        f"{', '.join(s.name for s in cs.shards)})\n{cs.agent_yaml()}", encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
