"""Regression tests for the defects fixed by the E1 verifier (research/audit/verify_eval_harness_editlog.md)."""

from __future__ import annotations

import json

import pytest
from eval_builders import (
    default_table,
    make_finding,
    make_flaw,
    make_key,
    make_review,
    pair,
    responder_from,
    run_pipeline,
)
from test_eval_live_judges import GOOD, Runner, cli_out, no_sleep, req

from sit_eval.calls import JudgeRunner
from sit_eval.judge import FakeJudge, JudgeError, JudgeResult
from sit_eval.live_judges import ClaudeCodeJudge

ANS = {"candidate_ids": [], "rationale": "x"}


class LiveLike:
    """A stand-in live client: same model and prompts as the fake, but a live backend."""

    backend = "claude_code"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        return JudgeResult(data={"candidate_ids": [], "rationale": "live"}, model="m", cost_usd=0.01)


def _runner(judge, **kw) -> JudgeRunner:
    return JudgeRunner(judge, model="claude-opus-5-5", effort="high", max_tokens=100, **kw)


async def test_cache_never_serves_fake_answers_to_a_live_client(tmp_path):
    # Defect 1: the cache key ignored the client, and `--out` defaults to runs/eval/<run_id> for every
    # judge kind, so a plumbing-only fake run followed by a live run reused the fake (hash) answers.
    fake = FakeJudge(lambda r: ANS)
    await _runner(fake, out_dir=tmp_path).ask("shortlist", "match.shortlist:F01", "s", "u")
    live = LiveLike()
    r2 = _runner(live, out_dir=tmp_path)
    data = await r2.ask("shortlist", "match.shortlist:F01", "s", "u")
    assert live.calls == 1 and data["rationale"] == "live" and r2.summary()["calls_cached"] == 0
    # the same live client still resumes from its own cached answers
    live2 = LiveLike()
    r3 = _runner(live2, out_dir=tmp_path)
    assert (await r3.ask("shortlist", "match.shortlist:F01", "s", "u"))["rationale"] == "live"
    assert live2.calls == 0 and r3.summary()["calls_cached"] == 1
    rows = [json.loads(x) for x in (tmp_path / "judge_results.jsonl").read_text().splitlines()]
    assert len(rows) == 2 and len({r["request_key"] for r in rows}) == 2


async def test_retried_call_reports_the_cost_of_every_attempt(tmp_path):
    # Defect 2: a call that succeeded after retries reported only its last attempt's cost, so the
    # scorer's spend (and the cost stop) missed the failed attempts.
    run = Runner(TimeoutError(), cli_out(is_error=True, result="API Error: 529 overloaded", cost=0.07),
                 cli_out(GOOD, cost=0.1))
    j = ClaudeCodeJudge(out_dir=tmp_path, runner=run, max_retries=3, sleep=no_sleep)
    res = await j.complete(req())
    assert res.cost_usd == pytest.approx(0.17) and res.raw["unknown_cost_attempts"] == 1
    assert res.raw["cost_includes_failed_attempts"] is True
    # the runner charges the known cost plus one reserve for the timed-out attempt
    run2 = Runner(TimeoutError(), cli_out(is_error=True, result="API Error: 529 overloaded", cost=0.07),
                  cli_out(GOOD, cost=0.1))
    jr = _runner(ClaudeCodeJudge(out_dir=tmp_path, runner=run2, max_retries=3, sleep=no_sleep),
                 max_cost_usd=10.0, reserve_usd=0.5)
    await jr.ask("pair", "match.pair:F01:FND-001", "s", "u")
    assert jr.budget.spent_usd == pytest.approx(0.17 + 0.5)
    assert jr.summary()["cost_usd_reported"] == pytest.approx(0.17)


async def test_failed_call_charges_known_cost_plus_a_reserve_per_unknown_attempt(tmp_path):
    run = Runner(cli_out(is_error=True, result="API Error: 529 overloaded", cost=0.07), TimeoutError())
    j = ClaudeCodeJudge(out_dir=tmp_path, runner=run, max_retries=1, sleep=no_sleep)
    with pytest.raises(JudgeError) as ei:
        await j.complete(req())
    assert ei.value.cost_usd == pytest.approx(0.07) and ei.value.unknown_cost_attempts == 1
    run2 = Runner(cli_out(is_error=True, result="API Error: 529 overloaded", cost=0.07), TimeoutError())
    jr = _runner(ClaudeCodeJudge(out_dir=tmp_path, runner=run2, max_retries=1, sleep=no_sleep),
                 max_cost_usd=10.0, reserve_usd=0.5)
    with pytest.raises(JudgeError):
        await jr.ask("pair", "match.pair:F01:FND-001", "s", "u")
    assert jr.budget.spent_usd == pytest.approx(0.57)
    assert jr.records[-1].cost_usd == pytest.approx(0.07) and jr.summary()["cost_usd_reported"] == pytest.approx(0.07)
    # all attempts timed out: no known cost, one reserve per attempt
    run3 = Runner(TimeoutError(), TimeoutError())
    jr3 = _runner(ClaudeCodeJudge(out_dir=tmp_path, runner=run3, max_retries=1, sleep=no_sleep),
                  max_cost_usd=10.0, reserve_usd=0.5)
    with pytest.raises(JudgeError):
        await jr3.ask("pair", "match.pair:F01:FND-002", "s", "u")
    assert jr3.budget.spent_usd == pytest.approx(1.0)


def _scenario(first_two_agree: bool):
    findings = [make_finding(1, "1"), make_finding(2, "2")]
    key = make_key([make_flaw("F01", "critical", "1"), make_flaw("F02", "high", "2")])
    table = default_table()
    seq = {("F01", "FND-001"): [3, 3, 2] if first_two_agree else [3, 2, 3], ("F02", "FND-002"): [2, 2, 3]}
    table["match.pair"] = lambda r: pair(seq.get(tuple(r.purpose.split(":")[1:]), [0, 0, 0])[r.sample_index])
    return make_review(findings), key, responder_from(table)


@pytest.mark.parametrize("agree", [True, False])
def test_adaptive_third_sample_gives_the_same_medians(tmp_path, agree):
    review, key, responder = _scenario(agree)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    full, f_full, _ = run_pipeline(tmp_path / "a", review, key, responder)
    adap, f_adap, _ = run_pipeline(tmp_path / "b", review, key, responder, adaptive_samples=True)
    med = lambda s: {(p["flaw_id"], p["finding_id"]): p["median"] for p in s["matching"]["pair_scores"]}  # noqa: E731
    assert med(full) == med(adap)
    assert full["matching"]["strict"] == adap["matching"]["strict"]
    n_full = sum(c.purpose.startswith("match.pair") for c in f_full.calls)
    n_adap = sum(c.purpose.startswith("match.pair") for c in f_adap.calls)
    assert n_full == 6 and n_adap == (4 if agree else 5)
    rows = {(p["flaw_id"], p["finding_id"]): p for p in adap["matching"]["pair_scores"]}
    assert rows[("F02", "FND-002")]["skipped_samples"] == 1 and rows[("F02", "FND-002")]["samples"] == [2, 2, None]
    assert any("adaptive third sample" in w for w in adap["warnings"])


def test_score_cli_survives_a_broken_grader_package(monkeypatch):
    # Defect: `sit-eval score` imported the grader package at module import, so an error in another
    # workstream's in-progress grader edit disabled scoring (seen during verification).
    import importlib
    import sys

    from typer.testing import CliRunner

    import sit_eval.cli as cli

    monkeypatch.setitem(sys.modules, "sit_eval.grader.cli", None)   # any import of it now raises
    try:
        mod = importlib.reload(cli)
        res = CliRunner().invoke(mod.app, ["grade", "run", "x"])
        assert res.exit_code == 2
        assert CliRunner().invoke(mod.app, ["score", "--help"]).exit_code == 0
    finally:
        monkeypatch.undo()
        importlib.reload(cli)


def test_dry_run_flags_a_model_outside_the_price_basis():
    from eval_builders import LIVE_RUN, PAYMENTS_KEY, options

    from sit_eval.loaders import load_key, load_review
    from sit_eval.scoring import plan_calls

    rin, key = load_review(LIVE_RUN), load_key(PAYMENTS_KEY)
    usd, secs = {"low": 0.05, "typical": 0.1, "high": 0.15}, {"low": 20.0, "high": 60.0}
    opus = plan_calls(rin, key, "v1", options(), usd, secs)
    haiku = plan_calls(rin, key, "v1", options(model="claude-haiku-4-5"), usd, secs)
    assert not any("do not apply" in c for c in opus["caveats"])
    assert any("do not apply" in c for c in haiku["caveats"])
    # measured on the live run: 80 overlap pairs, 300-440 calls prereg-faithful; adaptive lowers the floor only
    assert opus["location_overlap_pairs"] == 80 and opus["calls"]["total"] == {"min": 300, "max": 440}
    adaptive = plan_calls(rin, key, "v1", options(adaptive_samples=True), usd, secs)
    assert adaptive["calls"]["pair_scoring"] == {"min": 160, "max": 366}


async def test_claude_code_never_sends_the_meta_schema_keyword(tmp_path):
    # Coordinator heads-up: `claude -p --json-schema` was seen to reject a root "$schema" key.
    from sit_eval.prompts import judge_schema

    # sit_eval.prompts already drops it from the harness schemas; the client now drops it for every
    # caller (the grader builds its own schemas).
    assert "$schema" not in judge_schema("pair")
    run = Runner(cli_out(GOOD))
    j = ClaudeCodeJudge(out_dir=tmp_path, runner=run, sleep=no_sleep)
    with_meta = {"$schema": "https://json-schema.org/draft/2020-12/schema", **judge_schema("pair")}
    res = await j.complete(req(schema=with_meta))
    argv = run.calls[0]["argv"]
    sent = json.loads(argv[argv.index("--json-schema") + 1])
    assert "$schema" not in sent and sent["properties"]["score"]["enum"] == [0, 1, 2, 3]
    assert res.data == GOOD


def test_build_judge_defaults_live_options_from_eval_config(tmp_path):
    # The grader calls build_judge(kind, out_dir=...) with no options; it must still get the configured
    # per-call --max-budget-usd cap, timeout and retries. Explicit options win.
    from sit_eval.config import load_eval_config
    from sit_eval.judge import build_judge

    jc = load_eval_config().judge
    j = build_judge("claude_code", out_dir=tmp_path)
    assert j.max_budget_usd_per_call == jc.max_budget_usd_per_call is not None
    assert j.timeout_s == jc.timeout_s and j.max_retries == jc.max_retries
    assert "--max-budget-usd" in j.build_argv(req(), schema_json="{}", session_id="s")
    j2 = build_judge("claude_code", out_dir=tmp_path, max_budget_usd_per_call=0.25, max_retries=0)
    assert j2.max_budget_usd_per_call == 0.25 and j2.max_retries == 0 and j2.timeout_s == jc.timeout_s
    a = build_judge("anthropic_api", out_dir=tmp_path, client=object())
    assert a.timeout_s == jc.timeout_s and a.max_retries == jc.max_retries
