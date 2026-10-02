"""Offline end-to-end: the first live run's report.json scored against the payments key.

PLUMBING ONLY. The judge is the deterministic fake of ``sit_eval.fakes``: its answers are hashes,
not judgements. Nothing below is, or may be quoted as, a score of the live run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eval_builders import LIVE_RUN, PAYMENTS_KEY, default_table, make_finding, make_flaw, make_key, make_review
from eval_builders import run_pipeline as pipeline
from typer.testing import CliRunner

from sit_eval.cli import app
from sit_eval.judge import JudgeRequest, JudgeResult
from sit_eval.scoring import validate_scores

runner = CliRunner()


@pytest.fixture(scope="module")
def plumbing_run(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("plumbing")
    res = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(PAYMENTS_KEY), "--judge", "fake",
                              "--out", str(out)])
    assert res.exit_code == 0, res.output
    return out


def test_plumbing_scores_json_is_valid(plumbing_run: Path):
    s = json.loads((plumbing_run / "scores.json").read_text())
    assert validate_scores(s) == []
    assert s["status"] == "plumbing_only" and any("PLUMBING ONLY" in w for w in s["warnings"])
    assert any("UNFROZEN" in w for w in s["warnings"]) and s["prereg"]["label"] == "pilot_unfrozen"
    assert any("scored_run_ready = false" in w for w in s["warnings"])
    inp = s["inputs"]
    # the canonical text came from the agent's own ingest of the PDF and equals what the agent verified
    assert inp["doc_sha256_text_matches_review"] is True and "sit_review_agent.ingest.ingest" in inp["doc_source"]
    assert len(s["findings"]) == 20 and len(s["flaws"]) == 14          # FND-021 is a strength; F15 is v2-only
    assert s["matching"]["candidates"]["F01"]["FND-002"] == ["overlap"]
    assert s["calls"]["calls_failed"] == 0 and s["calls"]["calls_total"] > 0
    assert s["metrics"]["quote_fabrication_rate"]["value"] == 0.0      # every quote resolves in the canonical text
    md = (plumbing_run / "scores.md").read_text()
    assert "PLUMBING ONLY" in md and "| recall |" in md
    assert (plumbing_run / "judge_results.jsonl").exists()


def test_rerun_into_same_out_dir_uses_the_cache(plumbing_run: Path):
    res = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(PAYMENTS_KEY), "--judge", "fake",
                              "--out", str(plumbing_run), "--no-grounding-judges"])
    assert res.exit_code == 0, res.output
    s = json.loads((plumbing_run / "scores.json").read_text())
    assert s["calls"]["calls_live"] == 0 and s["calls"]["calls_cached"] > 0


def test_dry_run_reports_call_count(tmp_path: Path):
    res = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(PAYMENTS_KEY), "--dry-run",
                              "--out", str(tmp_path / "never")])
    assert res.exit_code == 0, res.output
    plan = json.loads(res.output)
    assert plan["judge"] == "claude_code" and plan["granularity"] == "pairwise"
    assert plan["calls"]["shortlist"] == 14 and plan["location_overlap_pairs"] == 80
    assert plan["calls"]["pair_scoring"]["min"] == 240 and plan["calls"]["total"]["min"] > 240
    assert plan["cost_usd_estimate"]["high"] > plan["cost_usd_estimate"]["low"] > 0
    assert not (tmp_path / "never").exists()
    batch = json.loads(runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(PAYMENTS_KEY), "--dry-run",
                                           "--granularity", "per_flaw_batch", "--no-grounding-judges"]).output)
    assert batch["calls"]["pair_scoring"] == {"min": 42, "max": 42} and batch["calls"]["premise_judge"] == 0


def test_bad_inputs_fail_cleanly(tmp_path: Path):
    bad = tmp_path / "report.json"
    bad.write_text("{}")
    res = runner.invoke(app, ["score", str(bad), "--key", str(PAYMENTS_KEY), "--judge", "fake"])
    assert res.exit_code == 2 and "not a valid Review" in res.output
    res = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(bad), "--judge", "fake"])
    assert res.exit_code == 2 and "not a valid canonical answer key" in res.output
    res = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(PAYMENTS_KEY), "--judge", "gpt"])
    assert res.exit_code == 2


class PricedJudge:
    def __init__(self) -> None:
        self.calls: list[JudgeRequest] = []

    async def complete(self, request: JudgeRequest) -> JudgeResult:
        self.calls.append(request)
        kind = request.purpose.split(":", 1)[0]
        return JudgeResult(data=default_table()[kind](request), model="m", cost_usd=0.1)


def test_cost_stop_writes_a_valid_stopped_score(tmp_path: Path):
    key = make_key([make_flaw("F01", "high", "1"), make_flaw("F02", "high", "2")])
    judge = PricedJudge()
    scores, _, r = pipeline(tmp_path, make_review([make_finding(1, "1"), make_finding(2, "2")]), key, None,
                            judge=judge, reserve_usd=0.1, max_cost_usd=0.35, concurrency=1)
    assert scores["status"] == "stopped_budget" and scores["metrics"] == {}
    assert len(judge.calls) == 3 and scores["calls"]["budget"]["stopped"] is True
    assert "max-cost-usd 0.35" in scores["stop"]["reason"]
    assert validate_scores(scores) == []


def test_live_judge_preflight_fails_fast(tmp_path: Path):
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    cfg = tmp_path / "eval.yaml"
    cfg.write_text("judge:\n  executable: definitely-not-an-installed-claude-binary\n")
    res = runner.invoke(app, ["score", str(fixtures / "review_example.json"), "--key", str(PAYMENTS_KEY),
                              "--doc", str(fixtures / "booking_v1.pages.txt"), "--judge", "claude_code",
                              "--config", str(cfg), "--out", str(tmp_path / "o")])
    assert res.exit_code == 2 and "not found on PATH" in res.output
