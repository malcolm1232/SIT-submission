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
    # --exploratory: the real key may be unsigned, and LC12 refuses an unsigned key without it (test_eval_lc12.py
    # pins the refusal and the confirmatory path on temporary copies); the flag marks the run whatever the key's state
    out = tmp_path_factory.mktemp("plumbing")
    res = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(PAYMENTS_KEY), "--judge", "fake",
                              "--out", str(out), "--exploratory"])
    assert res.exit_code == 0, res.output
    return out


def test_plumbing_scores_json_is_valid(plumbing_run: Path):
    s = json.loads((plumbing_run / "scores.json").read_text())
    assert validate_scores(s) == []
    assert s["status"] == "plumbing_only" and any("PLUMBING ONLY" in w for w in s["warnings"])
    assert any("UNFROZEN" in w for w in s["warnings"]) and s["prereg"]["label"] == "pilot_unfrozen"
    assert s["exploratory"] is True and "may not be reported as confirmatory" in s["exploratory_note"]
    # The warning follows the real key's state: present while the key is unsigned (LC12), absent once the owner has
    # signed it (eval/KEY_SIGNOFF.md section 4, whose last step runs this suite).
    ready = json.loads(PAYMENTS_KEY.read_text(encoding="utf-8"))["authoring_status"]["scored_run_ready"]
    assert any("scored_run_ready = false" in w for w in s["warnings"]) is (not ready)
    inp = s["inputs"]
    assert inp["scored_run_ready"] is ready
    # the canonical text came from the agent's own ingest of the PDF and equals what the agent verified
    assert inp["doc_sha256_text_matches_review"] is True and "sit_review_agent.ingest.ingest" in inp["doc_source"]
    assert len(s["findings"]) == 20 and len(s["flaws"]) == 14          # FND-021 is a strength; F15 is v2-only
    # shortlist_bounded (default): every candidate pair was shortlisted; overlap is provenance only
    m = s["matching"]
    assert m["candidate_rule"] == "shortlist_bounded"
    for g, cands in m["candidates"].items():
        sl = m["shortlist"][g]
        assert set(cands) == set(sl["ids"]) and len(cands) <= 3
        assert all(src[-1] == "shortlist" for src in cands.values())
        assert {f for f, src in cands.items() if "overlap" in src} == set(sl["shortlisted_with_overlap"])
        assert set(sl["overlap_hint_ids"]) == set(sl["shortlisted_with_overlap"]) | set(sl["overlap_not_shortlisted"])
    assert "FND-002" in m["shortlist"]["F01"]["overlap_hint_ids"]
    assert {(p["flaw_id"], p["finding_id"]) for p in m["pair_scores"]} == {
        (g, f) for g, c in m["candidates"].items() for f in c}
    assert s["calls"]["calls_failed"] == 0 and s["calls"]["calls_total"] > 0
    assert s["metrics"]["quote_fabrication_rate"]["value"] == 0.0      # every quote resolves in the canonical text
    md = (plumbing_run / "scores.md").read_text()
    assert "PLUMBING ONLY" in md and "| recall |" in md and md.splitlines()[2].startswith("**EXPLORATORY**")
    assert (plumbing_run / "judge_results.jsonl").exists()


def test_rerun_into_same_out_dir_uses_the_cache(plumbing_run: Path):
    res = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(PAYMENTS_KEY), "--judge", "fake",
                              "--out", str(plumbing_run), "--no-grounding-judges", "--exploratory"])
    assert res.exit_code == 0, res.output
    s = json.loads((plumbing_run / "scores.json").read_text())
    assert s["calls"]["calls_live"] == 0 and s["calls"]["calls_cached"] > 0


def test_dry_run_reports_call_count(tmp_path: Path):
    # candidate_rule union (comparison mode); the shortlist_bounded default is pinned in
    # test_eval_candidate_rule.py::test_dry_run_on_the_live_run_plans_far_fewer_calls
    res = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(PAYMENTS_KEY), "--dry-run",
                              "--candidate-rule", "union", "--out", str(tmp_path / "never")])
    assert res.exit_code == 0, res.output
    plan = json.loads(res.output)
    assert plan["judge"] == "claude_code" and plan["granularity"] == "pairwise" and plan["candidate_rule"] == "union"
    assert plan["calls"]["shortlist"] == 14 and plan["location_overlap_pairs"] == 80
    # adaptive third sample is on by default (UD #15): 80 overlap pairs x 2 samples at the floor
    assert plan["adaptive_third_sample"] is True
    assert plan["calls"]["pair_scoring"]["min"] == 160 and plan["calls"]["total"]["min"] > 160
    assert plan["cost_usd_estimate"]["high"] > plan["cost_usd_estimate"]["low"] > 0
    assert not (tmp_path / "never").exists()
    batch = json.loads(runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(PAYMENTS_KEY), "--dry-run",
                                           "--candidate-rule", "union", "--granularity", "per_flaw_batch",
                                           "--no-grounding-judges", "--no-adaptive-samples"]).output)
    assert batch["calls"]["pair_scoring"] == {"min": 42, "max": 42} and batch["calls"]["premise_judge"] == 0
    batch_ad = json.loads(runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(PAYMENTS_KEY), "--dry-run",
                                              "--candidate-rule", "union", "--granularity", "per_flaw_batch",
                                              "--no-grounding-judges"]).output)
    assert batch_ad["calls"]["pair_scoring"] == {"min": 28, "max": 42}


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
                              "--config", str(cfg), "--out", str(tmp_path / "o"), "--exploratory"])
    assert res.exit_code == 2 and "not found on PATH" in res.output
