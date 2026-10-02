"""JudgeRunner: cost stop, result cache, bounded concurrency, schema re-validation."""

from __future__ import annotations

import asyncio

import pytest

from sit_eval.calls import BudgetStop, JudgeRunner
from sit_eval.judge import JudgeError, JudgeRequest, JudgeResult

ANS = {"candidate_ids": [], "rationale": "x"}


class CostJudge:
    def __init__(self, cost: float | None = 0.1, delay: float = 0.0, data: dict | None = None) -> None:
        self.cost = cost
        self.delay = delay
        self.data = data or ANS
        self.calls: list[JudgeRequest] = []
        self.active = 0
        self.max_active = 0

    async def complete(self, request: JudgeRequest) -> JudgeResult:
        self.calls.append(request)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(self.delay)
        self.active -= 1
        return JudgeResult(data=self.data, model="m", cost_usd=self.cost)


def runner(judge, **kw) -> JudgeRunner:
    return JudgeRunner(judge, model="claude-opus-5-5", effort="high", max_tokens=100, **kw)


async def test_cost_stop_refuses_the_call_that_would_cross():
    j = CostJudge(cost=0.1)
    r = runner(j, max_cost_usd=0.35, reserve_usd=0.1)
    for i in range(3):
        await r.ask("shortlist", f"match.shortlist:F0{i}", "s", f"u{i}")
    # spent 0.30; the next reserve (0.10) would make 0.40 > 0.35
    with pytest.raises(BudgetStop, match="max-cost-usd 0.35"):
        await r.ask("shortlist", "match.shortlist:F09", "s", "u9")
    assert len(j.calls) == 3
    with pytest.raises(BudgetStop):
        await r.ask("shortlist", "match.shortlist:F10", "s", "u10")
    s = r.summary()
    assert s["budget"]["stopped"] and s["budget"]["refused_calls"] == 2 and s["calls_live"] == 3
    assert s["cost_usd_reported"] == pytest.approx(0.3)


async def test_unreported_cost_is_charged_the_reserve():
    j = CostJudge(cost=None)
    r = runner(j, max_cost_usd=0.25, reserve_usd=0.1)
    await r.ask("shortlist", "p1", "s", "u1")
    await r.ask("shortlist", "p2", "s", "u2")
    with pytest.raises(BudgetStop):
        await r.ask("shortlist", "p3", "s", "u3")
    assert r.summary()["calls_without_cost"] == 2


async def test_cache_reuses_identical_requests_across_runs(tmp_path):
    j = CostJudge()
    r1 = runner(j, out_dir=tmp_path)
    await r1.ask("shortlist", "p", "s", "u", sample_index=0)
    await r1.ask("shortlist", "p", "s", "u", sample_index=1)       # different sample -> new call
    assert len(j.calls) == 2
    j2 = CostJudge()
    r2 = runner(j2, out_dir=tmp_path, max_cost_usd=0.0001, reserve_usd=1.0)
    assert await r2.ask("shortlist", "p", "s", "u", sample_index=1) == ANS   # cached: no budget needed
    assert j2.calls == [] and r2.summary()["calls_cached"] == 1


async def test_concurrency_is_bounded():
    j = CostJudge(delay=0.01)
    r = runner(j, concurrency=3)
    await asyncio.gather(*(r.ask("shortlist", f"p{i}", "s", f"u{i}") for i in range(12)))
    assert j.max_active == 3 and len(j.calls) == 12


async def test_answers_are_revalidated_against_the_schema():
    r = runner(CostJudge(data={"candidate_ids": "not a list", "rationale": "x"}))
    with pytest.raises(JudgeError, match="violates the shortlist schema"):
        await r.ask("shortlist", "p", "s", "u")
    assert r.summary()["calls_failed"] == 1
