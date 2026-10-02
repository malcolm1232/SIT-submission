"""Every judge call of a scoring run goes through :class:`JudgeRunner`.

It adds what the frozen :class:`~sit_eval.judge.JudgeClient` interface leaves to the caller:

* bounded concurrency (``run.concurrency``);
* the output schema of each call kind (``schemas/judge_<kind>.schema.json``), re-validated here so a
  fake or a misbehaving client cannot slip an invalid answer through;
* a result cache, ``<out_dir>/judge_results.jsonl``, keyed by the SHA-256 of everything the model
  sees (model, effort, max_tokens, system, user, schema, sample index). Prompts are deterministic
  given the seed, so re-running ``sit-eval score`` into the same ``--out`` after a stop or a crash
  re-pays nothing that already succeeded;
* the hard cost stop (``--max-cost-usd``): a call is refused (and the stop recorded) when the spend
  so far, plus the reserve of calls in flight, plus this call's reserve would cross the limit. The
  reserve is ``judge.max_budget_usd_per_call`` when set, else the high per-call estimate. A call
  whose client reports no cost is charged its reserve.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sit_eval.judge import JudgeClient, JudgeError, JudgeRequest
from sit_eval.live_judges import schema_problems
from sit_eval.prompts import judge_schema

CACHE_NAME = "judge_results.jsonl"


class BudgetStop(JudgeError):
    """``--max-cost-usd`` would be crossed by the next call; no further calls are started."""


def derive_seed(base: int, *parts: Any) -> int:
    h = hashlib.sha256(("|".join([str(base), *map(str, parts)])).encode()).hexdigest()
    return int(h[:12], 16)


def request_key(req: JudgeRequest) -> str:
    blob = json.dumps([req.model, req.effort, req.max_tokens, req.system, req.user, req.schema, req.sample_index],
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class CallRecord:
    kind: str
    purpose: str
    sample_index: int
    ok: bool
    cached: bool
    cost_usd: float | None
    model: str | None
    elapsed_s: float
    request_key: str
    seed: int | None = None
    error: str | None = None


@dataclass
class BudgetState:
    max_cost_usd: float | None
    reserve_usd: float
    spent_usd: float = 0.0
    stopped: bool = False
    stop_detail: str | None = None
    refused_calls: int = 0


@dataclass
class JudgeRunner:
    judge: JudgeClient
    model: str
    effort: str
    max_tokens: int
    concurrency: int = 4
    max_cost_usd: float | None = None
    reserve_usd: float = 0.15
    out_dir: Path | None = None
    records: list[CallRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._sem = asyncio.Semaphore(self.concurrency)
        self._inflight = 0.0
        self._inflight_n = 0
        self.budget = BudgetState(max_cost_usd=self.max_cost_usd, reserve_usd=self.reserve_usd)
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_path = (Path(self.out_dir) / CACHE_NAME) if self.out_dir is not None else None
        if self._cache_path is not None and self._cache_path.exists():
            for line in self._cache_path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    self._cache[row["request_key"]] = row
                except (ValueError, KeyError):
                    continue

    def request(self, kind: str, purpose: str, system: str, user: str, sample_index: int = 0) -> JudgeRequest:
        return JudgeRequest(purpose=purpose, system=system, user=user, schema=judge_schema(kind), model=self.model,
                            effort=self.effort, max_tokens=self.max_tokens, sample_index=sample_index)

    def _check_budget(self) -> None:
        b = self.budget
        if b.stopped:
            b.refused_calls += 1
            raise BudgetStop(b.stop_detail or "cost stop reached")
        if b.max_cost_usd is not None and b.spent_usd + self._inflight + b.reserve_usd > b.max_cost_usd:
            b.stopped = True
            b.refused_calls += 1
            b.stop_detail = (f"--max-cost-usd {b.max_cost_usd:g} reached: spent ${b.spent_usd:.4f}, in flight "
                             f"${self._inflight:.4f}, next call reserve ${b.reserve_usd:.4f}; no further calls started")
            raise BudgetStop(b.stop_detail)

    async def ask(self, kind: str, purpose: str, system: str, user: str, *, sample_index: int = 0,
                  seed: int | None = None) -> dict[str, Any]:
        """Structured answer of one call (raises :class:`JudgeError` / :class:`BudgetStop`)."""
        req = self.request(kind, purpose, system, user, sample_index)
        key = request_key(req)
        hit = self._cache.get(key)
        if hit is not None:
            self.records.append(CallRecord(kind, purpose, sample_index, True, True, 0.0, hit.get("model"), 0.0, key,
                                           seed))
            return hit["data"]
        async with self._sem:
            self._check_budget()
            self._inflight += self.reserve_usd
            self._inflight_n += 1
            t0 = time.monotonic()
            try:
                res = await self.judge.complete(req)
                problems = schema_problems(req.schema, res.data)
                if problems:
                    raise JudgeError(f"{purpose}: answer violates the {kind} schema: " + "; ".join(problems))
            except JudgeError as exc:
                if not isinstance(exc, BudgetStop):
                    self.budget.spent_usd += self.reserve_usd if self.max_cost_usd is not None else 0.0
                    self.records.append(CallRecord(kind, purpose, sample_index, False, False, None, None,
                                                   time.monotonic() - t0, key, seed, str(exc)[:300]))
                raise
            finally:
                self._inflight -= self.reserve_usd
                self._inflight_n -= 1
            cost = res.cost_usd
            self.budget.spent_usd += cost if cost is not None else self.reserve_usd
            self.records.append(CallRecord(kind, purpose, sample_index, True, False, cost, res.model,
                                           time.monotonic() - t0, key, seed))
            if self._cache_path is not None:
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                with self._cache_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"request_key": key, "purpose": purpose, "sample_index": sample_index,
                                         "model": res.model, "cost_usd": cost, "data": res.data},
                                        sort_keys=True, ensure_ascii=False) + "\n")
            self._cache[key] = {"data": res.data, "model": res.model}
            return res.data

    async def drain(self, poll_s: float = 0.05) -> None:
        """Wait for calls already in flight (after a cost stop) so their cost is recorded and their
        answers are cached for a resumed run."""
        while self._inflight_n > 0:
            await asyncio.sleep(poll_s)

    def summary(self) -> dict[str, Any]:
        live = [r for r in self.records if not r.cached]
        costs = [r.cost_usd for r in live if r.cost_usd is not None]
        by_kind: dict[str, int] = {}
        for r in self.records:
            by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
        return {
            "calls_total": len(self.records), "calls_live": len(live),
            "calls_cached": len(self.records) - len(live), "calls_failed": sum(not r.ok for r in self.records),
            "calls_by_kind": dict(sorted(by_kind.items())),
            "cost_usd_reported": round(sum(costs), 6) if costs else (0.0 if not live else None),
            "calls_without_cost": sum(1 for r in live if r.ok and r.cost_usd is None),
            "served_models": sorted({r.model for r in self.records if r.model}),
            "budget": asdict(self.budget),
        }
