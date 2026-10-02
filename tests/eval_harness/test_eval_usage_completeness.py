"""Cost and token metrics of a run whose usage is partly unknown (SIT FABLE ruling #28, 2026-10-03).

The agent runtime lists a model call that was killed or cut, and so left no usage report, in the manifest's
``extra.model.calls_with_unrecorded_usage`` and sets ``extra.model.cost_usd_lower_bound``. The harness must then
report the run's cost and tokens as unknown (null) with the lower bounds beside them, never as a complete
figure; the FULL-run cost median of the prereg pilot checkpoint is computed over fully accounted runs only,
and a lower bound can fail that checkpoint but never pass it.

Offline: fake judge, fixtures written here. Every ``llm.jsonl`` below is a fixture of this file.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from eval_builders import (
    LIVE_RUN,
    PAYMENTS_KEY,
    PAYMENTS_PDF,
    default_table,
    make_finding,
    make_flaw,
    make_key,
    make_review,
    responder_from,
)
from eval_builders import run_pipeline as pipeline
from typer.testing import CliRunner

from sit_eval import prereg as prereg_mod
from sit_eval import usage as usage_mod
from sit_eval.aggregate import aggregate, pilot_checkpoint
from sit_eval.cli import app
from sit_eval.loaders import load_review
from sit_eval.report_md import render_scores_md
from sit_eval.scoring import validate_scores
from sit_eval.usage import COMPLETE, UNKNOWN, UNRECORDED, UsageCompleteness, unrecorded_reason, usage_completeness

runner = CliRunner()

ZERO = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
SOME = {"input_tokens": 1200, "output_tokens": 80, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 900}
#: The demo measurement run's ``llm-0003`` as the runtime logged it before 2026-10-03: a deadline cut with zeros.
LEGACY_CUT = {"call_id": "llm-0003", "phase": "assess", "purpose": "assess", "backend": "claude_code", "attempt": 0,
              "outcome": "LLMDeadlineError", "usage": dict(ZERO), "elapsed_s": 178.9, "call_cost_usd": None}
#: The same event as the runtime logs it since commit 8ef32d4.
NEW_CUT = {"call_id": "llm-0003", "phase": "assess", "purpose": "assess", "attempt": 0, "outcome": "LLMDeadlineError",
           "usage": None, "usage_unrecorded": "deadline_cut", "call_cost_usd": None, "elapsed_s": 178.9}
CUT_CALL = {"call_id": "llm-0003", "stage": "assess", "purpose": "assess", "attempt": 0, "wall_s": 178.9,
            "reason": "deadline_cut"}
USAGE = {"cost_usd": 1.10, "input_tokens": 100000, "output_tokens": 20000, "cached_tokens": 5000,
         "price_table_date": "2026-09-25", "tool_calls": 0}


def manifest(calls: list[dict[str, Any]] | None, *, cost: float = 1.10) -> dict[str, Any]:
    """A manifest in the runtime's shape; ``calls=None`` stands for a manifest that predates the field."""
    model: dict[str, Any] = {"backend": "claude_code", "truncations": []}
    if calls is not None:
        model["calls_with_unrecorded_usage"] = calls
        model["cost_usd_lower_bound"] = bool(calls)
    return {"usage": {**USAGE, "cost_usd": cost},
            "extra": {"timing": {"wall_clock_s": 1200.0, "per_stage_s": {"assess": 900.0}}, "model": model}}


def write_log(run_dir: Path, entries: list[dict[str, Any]]) -> Path:
    p = run_dir / "llm.jsonl"
    p.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return p


# ----------------------------------------------------------------------------- the rule, pinned to the runtime


def test_unrecorded_reason_pins_the_runtime_rule():
    # new entries say it
    assert unrecorded_reason(NEW_CUT) == "deadline_cut"
    assert unrecorded_reason({**NEW_CUT, "usage_unrecorded": "timeout_kill", "fake": True}) == "timeout_kill"
    # the legacy demo-run entry: a deadline cut with zero usage, no cost and no HTTP status
    assert unrecorded_reason(LEGACY_CUT) == "deadline_cut"
    assert unrecorded_reason({**LEGACY_CUT, "outcome": "LLMTimeoutError"}) == "timeout_kill"
    # every condition of the legacy rule
    assert unrecorded_reason({**LEGACY_CUT, "usage": dict(SOME)}) is None             # usage known
    assert unrecorded_reason({**LEGACY_CUT, "call_cost_usd": 0.0}) is None           # cost recorded
    assert unrecorded_reason({**LEGACY_CUT, "status_code": 529}) is None             # the API answered
    assert unrecorded_reason({**LEGACY_CUT, "sent": False}) is None                  # never sent
    assert unrecorded_reason({**LEGACY_CUT, "fault": "hang"}) is None                # injected fault
    assert unrecorded_reason({**LEGACY_CUT, "replayed": True}) is None               # replayed
    assert unrecorded_reason({**LEGACY_CUT, "fake": True}) is None                   # fake gateway, legacy
    assert unrecorded_reason({**LEGACY_CUT, "outcome": "LLMTruncatedError"}) is None  # billed, usage known
    assert unrecorded_reason({**LEGACY_CUT, "outcome": "ok", "usage": dict(SOME)}) is None
    assert unrecorded_reason({**LEGACY_CUT, "usage": None}) is None                  # not the legacy shape
    assert unrecorded_reason({}) is None


def test_the_manifest_field_is_read_when_present(tmp_path: Path):
    uc = usage_completeness(manifest([CUT_CALL]), tmp_path)
    assert uc.status == UNRECORDED and uc.lower_bound and uc.count == 1 and uc.calls == (CUT_CALL,)
    assert "manifest" in uc.source and "llm.jsonl" not in uc.source
    assert "1 model call with unrecorded usage" in usage_mod.describe(uc) and "deadline cut" in usage_mod.describe(uc)
    ok = usage_completeness(manifest([]), tmp_path)
    assert ok.status == COMPLETE and not ok.lower_bound and ok.count == 0 and "manifest" in ok.source
    # the manifest wins over a call log beside it
    write_log(tmp_path, [LEGACY_CUT])
    assert usage_completeness(manifest([]), tmp_path).status == COMPLETE
    assert usage_completeness(manifest([CUT_CALL]), tmp_path).count == 1


def test_a_manifest_that_predates_the_field_is_read_from_the_call_log_and_says_so(tmp_path: Path):
    write_log(tmp_path, [{"call_id": "llm-0001", "phase": "understand", "outcome": "ok", "usage": dict(SOME)},
                         {"call_id": "llm-0002", "phase": "plan", "outcome": "ok", "usage": dict(SOME)},
                         LEGACY_CUT,
                         {"call_id": "llm-0004", "phase": "report", "attempt": 0, "outcome": "LLMDeadlineError",
                          "sent": False},
                         {"call_id": None, "phase": "assess", "attempt": 0, "outcome": "LLMTimeoutError",
                          "fault": "hang"}])
    uc = usage_completeness(manifest(None), tmp_path)
    assert uc.status == UNRECORDED and uc.count == 1 and "llm.jsonl" in uc.source
    [c] = uc.calls
    assert c == {"call_id": "llm-0003", "stage": "assess", "purpose": "assess", "attempt": 0, "wall_s": 178.9,
                 "reason": "deadline_cut"}
    # a clean legacy log is complete, and the source still says where it was read
    write_log(tmp_path, [{"call_id": "llm-0001", "phase": "understand", "outcome": "ok", "usage": dict(SOME)}])
    ok = usage_completeness(manifest(None), tmp_path)
    assert ok.status == COMPLETE and "llm.jsonl" in ok.source
    # a legacy entry in the new shape (usage null) is read too
    write_log(tmp_path, [NEW_CUT])
    assert usage_completeness(manifest(None), tmp_path).count == 1
    # the spec run_manifest (no extra) with no call log: unknown
    assert usage_completeness({"usage": USAGE}, tmp_path / "nowhere").status == UNKNOWN


def test_neither_field_nor_call_log_is_unknown(tmp_path: Path):
    for m, rd in ((manifest(None), tmp_path), (None, tmp_path), (manifest(None), None), (None, None)):
        uc = usage_completeness(m, rd)
        assert uc.status == UNKNOWN and uc.lower_bound and uc.count == 0 and uc.calls == ()
        assert "llm.jsonl" in uc.source and "predates" in uc.source
    assert usage_mod.describe(usage_completeness(None, None)).startswith("usage_completeness_unknown")


def test_load_review_reads_the_completeness_of_the_run_dir(tmp_path: Path):
    # a copy of the live run's report (the builders' reviews are not full spec Reviews); its manifest is not copied
    shutil.copy(LIVE_RUN / "report.json", tmp_path / "report.json")
    assert load_review(tmp_path).usage.status == UNKNOWN
    write_log(tmp_path, [LEGACY_CUT])
    assert load_review(tmp_path).usage.status == UNRECORDED
    (tmp_path / "manifest.json").write_text(json.dumps(manifest([])), encoding="utf-8")
    rin = load_review(tmp_path)
    assert rin.manifest is not None and rin.usage.status == COMPLETE


# ----------------------------------------------------------------------------- per run (ruling 1 and 2)


def key():
    return make_key([make_flaw("F01", "high", "1")])


def eff(scores: dict[str, Any]) -> dict[str, Any]:
    return scores["metrics"]["efficiency"]


def test_a_fully_accounted_run_is_unchanged(tmp_path: Path):
    scores, _, _ = pipeline(tmp_path, make_review([make_finding(1, "1")]), key(), responder_from(default_table()),
                            manifest=manifest([]))
    e = eff(scores)
    v = e["value"]
    assert (v["cost_usd"], v["input_tokens"], v["output_tokens"], v["cached_tokens"]) == (1.10, 100000, 20000, 5000)
    assert v["usage_completeness"] == COMPLETE and v["usage_reason"] is None and v["calls_with_unrecorded_usage"] == []
    assert not any(k.endswith("_lower_bound") for k in v)
    assert e["reason"] is None and e["status"] == "secondary" and e["source"] == "manifest.json"
    assert v["wall_time_s"] == 1200.0 and v["stop_reason"] == {"code": "sufficient_evidence", "group": "decision"}
    assert not any("usage" in w and "unrecorded" in w for w in scores["warnings"])
    assert validate_scores(scores) == []
    md = render_scores_md(scores)
    assert "cost_usd: 1.100" in md and "LOWER BOUND" not in md and "UNKNOWN" not in md


def test_a_run_with_a_cut_call_reports_null_cost_and_tokens_with_the_lower_bounds_beside(tmp_path: Path):
    scores, _, _ = pipeline(tmp_path, make_review([make_finding(1, "1")]), key(), responder_from(default_table()),
                            manifest=manifest([CUT_CALL]))
    e = eff(scores)
    v = e["value"]
    assert v["cost_usd"] is None and v["input_tokens"] is None and v["output_tokens"] is None
    assert v["cached_tokens"] is None
    assert (v["cost_usd_lower_bound"], v["input_tokens_lower_bound"], v["output_tokens_lower_bound"],
            v["cached_tokens_lower_bound"]) == (1.10, 100000, 20000, 5000)
    assert v["usage_completeness"] == UNRECORDED and v["usage_reason"] == "unrecorded_usage"
    assert v["calls_with_unrecorded_usage"] == [CUT_CALL]
    assert "1 model call with unrecorded usage" in v["usage_note"] and "deadline cut" in v["usage_note"]
    assert "1 model call with unrecorded usage" in e["note"]
    # the rest of the metric is untouched
    assert v["wall_time_s"] == 1200.0 and v["tool_calls"] == 0 and v["price_table_date"] == "2026-09-25"
    assert any("unrecorded usage" in w and "lower bound" in w for w in scores["warnings"])
    assert validate_scores(scores) == []
    md = render_scores_md(scores)
    assert "LOWER BOUND" in md and "cost_usd: null" in md and "cost_usd_lower_bound: 1.100" in md
    assert "llm-0003" in md and "deadline cut" in md


def test_a_legacy_manifest_with_a_call_log_is_read_by_the_rule_and_the_scores_say_so(tmp_path: Path):
    write_log(tmp_path, [LEGACY_CUT, {"call_id": "llm-0005", "phase": "report", "outcome": "ok", "usage": dict(SOME)}])
    scores, _, _ = pipeline(tmp_path, make_review([make_finding(1, "1")]), key(), responder_from(default_table()),
                            manifest=manifest(None))
    v = eff(scores)["value"]
    assert v["usage_completeness"] == UNRECORDED and v["cost_usd"] is None and v["cost_usd_lower_bound"] == 1.10
    assert "llm.jsonl" in v["usage_source"]
    assert v["calls_with_unrecorded_usage"][0]["call_id"] == "llm-0003"
    assert any("llm.jsonl" in w and "predates" in w for w in scores["warnings"])
    assert validate_scores(scores) == []
    assert "llm.jsonl" in render_scores_md(scores)


def test_a_run_with_neither_is_unknown_and_its_cost_is_null(tmp_path: Path):
    scores, _, _ = pipeline(tmp_path, make_review([make_finding(1, "1")]), key(), responder_from(default_table()),
                            manifest=manifest(None))
    v = eff(scores)["value"]
    assert v["usage_completeness"] == UNKNOWN and v["usage_reason"] == "usage_completeness_unknown"
    assert v["cost_usd"] is None and v["input_tokens"] is None
    assert v["cost_usd_lower_bound"] == 1.10 and v["calls_with_unrecorded_usage"] == []
    assert any("usage completeness unknown" in w for w in scores["warnings"])
    assert validate_scores(scores) == []
    md = render_scores_md(scores)
    assert "USAGE COMPLETENESS UNKNOWN" in md and "cost_usd: null" in md
    # no manifest at all: the review's own run_manifest (spec field, no extra) and no call log
    scores2, _, _ = pipeline(tmp_path, make_review([make_finding(1, "1")]), key(), responder_from(default_table()))
    v2 = eff(scores2)["value"]
    assert v2["usage_completeness"] == UNKNOWN and v2["cost_usd"] is None and v2["cost_usd_lower_bound"] == 1.5
    assert eff(scores2)["source"] == "report.json run_manifest"


def test_exploratory_marking_is_unchanged_by_usage_completeness(tmp_path: Path):
    scores, _, _ = pipeline(tmp_path, make_review([make_finding(1, "1")]), key(), responder_from(default_table()),
                            manifest=manifest([CUT_CALL]))
    assert scores["exploratory"] is True and "may not be reported as confirmatory" in scores["exploratory_note"]
    assert scores["outside_preregistered_analysis"] is False
    assert render_scores_md(scores).splitlines()[2].startswith("**EXPLORATORY**")
    signed = key()
    signed["authoring_status"] = {"pending": [], "scored_run_ready": True}
    conf, _, _ = pipeline(tmp_path, make_review([make_finding(1, "1")]), signed, responder_from(default_table()),
                          manifest=manifest([CUT_CALL]), exploratory=False)
    assert conf["exploratory"] is False and conf["exploratory_note"] is None
    assert eff(conf)["value"]["usage_completeness"] == UNRECORDED


def test_the_scores_schema_refuses_a_cost_figure_on_an_incompletely_accounted_run(tmp_path: Path):
    scores, _, _ = pipeline(tmp_path, make_review([make_finding(1, "1")]), key(), responder_from(default_table()),
                            manifest=manifest([CUT_CALL]))
    assert validate_scores(scores) == []
    bad = json.loads(json.dumps(scores))
    bad["metrics"]["efficiency"]["value"]["cost_usd"] = 1.10
    assert any("cost_usd" in e for e in validate_scores(bad))
    bad = json.loads(json.dumps(scores))
    del bad["metrics"]["efficiency"]["value"]["cost_usd_lower_bound"]
    assert any("cost_usd_lower_bound" in e for e in validate_scores(bad))
    bad = json.loads(json.dumps(scores))
    bad["metrics"]["efficiency"]["value"]["usage_reason"] = None
    assert any("usage_reason" in e for e in validate_scores(bad))
    bad = json.loads(json.dumps(scores))
    del bad["metrics"]["efficiency"]["value"]["usage_completeness"]
    assert any("usage_completeness" in e for e in validate_scores(bad))


# ----------------------------------------------------------------------------- aggregate (rulings 3 to 5)


def scored(tmp_path: Path, name: str, *, cost: float, calls: list[dict[str, Any]] | None, condition: str = "FULL",
           run_id: str | None = None) -> Path:
    """A confirmatory scores.json of one run with the given cost and usage completeness."""
    d = tmp_path / name
    d.mkdir()
    signed = key()
    signed["authoring_status"] = {"pending": [], "scored_run_ready": True}
    review = make_review([make_finding(1, "1")])
    review["metadata"]["run_id"] = run_id or name
    scores, _, _ = pipeline(d, review, signed, responder_from(default_table()), manifest=manifest(calls, cost=cost),
                            exploratory=False, condition=condition)
    assert validate_scores(scores) == []
    p = d / "scores.json"
    p.write_text(json.dumps(scores), encoding="utf-8")
    return p


def agg(paths: list[Path], threshold: float | None = 3.24) -> dict[str, Any]:
    return aggregate(paths, B=100, pilot_threshold_usd=threshold)


def test_aggregate_separates_the_fully_accounted_median_from_the_lower_bound_median(tmp_path: Path):
    paths = [scored(tmp_path, "r1", cost=2.0, calls=[]), scored(tmp_path, "r2", cost=3.0, calls=[]),
             scored(tmp_path, "r3", cost=1.0, calls=[CUT_CALL]), scored(tmp_path, "r4", cost=2.5, calls=None)]
    c = agg(paths)["conditions"]["FULL"]["cost_usd"]
    assert c["runs"] == 4 and c["runs_fully_accounted"] == 2
    assert c["median_fully_accounted"] == 2.5 and c["iqr_fully_accounted"] == [2.25, 2.75]
    assert c["excluded_unrecorded"] == {"count": 1, "share": 0.25}
    assert c["excluded_unknown"] == {"count": 1, "share": 0.25}
    # the lower-bound median counts every run at its lower bound: 1.0, 2.0, 2.5, 3.0
    assert c["median_lower_bound_all_runs"] == 2.25 and c["runs_with_a_lower_bound"] == 4
    assert "never mixes" in c["note"] or "no figure mixes" in c["note"]
    t = agg(paths)["conditions"]["FULL"]["input_tokens"]
    assert t["median_fully_accounted"] == 100000 and t["runs_fully_accounted"] == 2
    # intention-to-treat share of runs with any cut call (ruling 5), unknown runs apart
    u = agg(paths)["conditions"]["FULL"]["runs_with_unrecorded_usage"]
    assert u == {"count": 1, "share": 0.25, "runs": ["r3"]}
    assert agg(paths)["conditions"]["FULL"]["runs_with_unknown_usage_completeness"] == {"count": 1, "share": 0.25,
                                                                                        "runs": ["r4"]}


def test_aggregate_treats_a_scores_file_written_before_the_ruling_as_unknown(tmp_path: Path):
    """A pre-ruling scores.json carries cost_usd and no usage_completeness (the pilots): never fully accounted."""
    old = scored(tmp_path, "old", cost=9.0, calls=[])
    s = json.loads(old.read_text())
    v = s["metrics"]["efficiency"]["value"]
    added = [k for k in v if k.startswith("usage_") or k.endswith("_lower_bound") or k == "calls_with_unrecorded_usage"]
    for k in added:
        del v[k]
    assert v["cost_usd"] == 9.0
    old.write_text(json.dumps(s))
    paths = [old, scored(tmp_path, "r1", cost=2.0, calls=[])]
    c = agg(paths)["conditions"]["FULL"]["cost_usd"]
    assert c["runs_fully_accounted"] == 1 and c["median_fully_accounted"] == 2.0
    assert c["excluded_unknown"] == {"count": 1, "share": 0.5}
    assert c["median_lower_bound_all_runs"] == 5.5 and c["runs_with_a_lower_bound"] == 2
    assert agg(paths)["pilot_checkpoint"]["verdict"] == "fail"       # the lower-bound median 5.5 exceeds 3.24


def test_aggregate_with_every_run_accounted_has_no_exclusions(tmp_path: Path):
    paths = [scored(tmp_path, "r1", cost=2.0, calls=[]), scored(tmp_path, "r2", cost=3.0, calls=[])]
    c = agg(paths)["conditions"]["FULL"]["cost_usd"]
    assert c["median_fully_accounted"] == 2.5 == c["median_lower_bound_all_runs"]
    assert c["excluded_unrecorded"]["count"] == 0 and c["excluded_unknown"]["count"] == 0


def test_pilot_checkpoint_matrix(tmp_path: Path):
    # lower-bound median over all runs above the threshold: fail, even with unknown costs in the set
    paths = [scored(tmp_path, "a1", cost=3.5, calls=[CUT_CALL]), scored(tmp_path, "a2", cost=4.0, calls=[]),
             scored(tmp_path, "a3", cost=3.3, calls=None)]
    cp = agg(paths)["pilot_checkpoint"]
    assert cp["verdict"] == "fail" and cp["threshold_usd"] == 3.24 and cp["condition"] == "FULL"
    assert cp["median_lower_bound_all_runs"] == 3.5 and cp["runs"] == 3 and cp["runs_fully_accounted"] == 1
    # all accounted and below: pass
    paths = [scored(tmp_path, "b1", cost=2.0, calls=[]), scored(tmp_path, "b2", cost=3.0, calls=[]),
             scored(tmp_path, "b3", cost=3.24, calls=[])]
    cp = agg(paths)["pilot_checkpoint"]
    assert cp["verdict"] == "pass" and cp["median_fully_accounted"] == 3.0
    # all accounted and above: fail
    paths = [scored(tmp_path, "c1", cost=3.0, calls=[]), scored(tmp_path, "c2", cost=3.5, calls=[]),
             scored(tmp_path, "c3", cost=3.3, calls=[])]
    cp = agg(paths)["pilot_checkpoint"]
    assert cp["verdict"] == "fail" and cp["median_fully_accounted"] == 3.3
    # some unknown and the lower-bound median below: not evaluable (a lower bound never passes)
    paths = [scored(tmp_path, "d1", cost=2.0, calls=[]), scored(tmp_path, "d2", cost=2.0, calls=[CUT_CALL]),
             scored(tmp_path, "d3", cost=2.0, calls=[])]
    cp = agg(paths)["pilot_checkpoint"]
    assert cp["verdict"] == "not_evaluable" and cp["median_fully_accounted"] == 2.0
    assert cp["median_lower_bound_all_runs"] == 2.0 and "lower bound" in cp["reason"]
    # the fully accounted median alone would pass here; it must not
    paths = [scored(tmp_path, "e1", cost=1.0, calls=[]), scored(tmp_path, "e2", cost=1.0, calls=None)]
    assert agg(paths)["pilot_checkpoint"]["verdict"] == "not_evaluable"
    # no FULL run, or no threshold: not evaluable
    paths = [scored(tmp_path, "f1", cost=1.0, calls=[], condition="B0")]
    assert agg(paths)["pilot_checkpoint"]["verdict"] == "not_evaluable"
    assert agg(paths, threshold=None)["pilot_checkpoint"]["verdict"] == "not_evaluable"


def test_pilot_checkpoint_rule_on_summaries():
    def summary(n: int, n_acc: int, med: float | None, lb: float | None) -> dict[str, Any]:
        return {"runs": n, "runs_fully_accounted": n_acc, "median_fully_accounted": med,
                "median_lower_bound_all_runs": lb, "runs_with_a_lower_bound": n}

    assert pilot_checkpoint(summary(3, 3, 3.0, 3.0), 3.24, "FULL")["verdict"] == "pass"
    assert pilot_checkpoint(summary(3, 3, 3.24, 3.24), 3.24, "FULL")["verdict"] == "pass"
    assert pilot_checkpoint(summary(3, 3, 3.25, 3.25), 3.24, "FULL")["verdict"] == "fail"
    assert pilot_checkpoint(summary(3, 1, 1.0, 3.5), 3.24, "FULL")["verdict"] == "fail"
    assert pilot_checkpoint(summary(3, 2, 1.0, 1.0), 3.24, "FULL")["verdict"] == "not_evaluable"
    assert pilot_checkpoint(summary(3, 3, None, None), 3.24, "FULL")["verdict"] == "not_evaluable"
    assert pilot_checkpoint(summary(0, 0, None, None), 3.24, "FULL")["verdict"] == "not_evaluable"
    assert pilot_checkpoint(summary(3, 3, 1.0, 1.0), None, "FULL")["verdict"] == "not_evaluable"


def test_the_threshold_is_read_from_the_prereg():
    assert prereg_mod.pilot_cost_threshold_usd() == 3.24


def test_aggregate_cli_and_score_console_report_the_checkpoint_and_the_completeness(tmp_path: Path):
    paths = [scored(tmp_path, "r1", cost=2.0, calls=[]), scored(tmp_path, "r2", cost=1.0, calls=[CUT_CALL])]
    res = runner.invoke(app, ["aggregate", *map(str, paths), "--bootstrap-b", "100", "--out", str(tmp_path / "a.json")])
    assert res.exit_code == 0, res.output
    out = json.loads((tmp_path / "a.json").read_text())
    console = json.loads(res.stdout[res.stdout.index("{"):res.stdout.rindex("}") + 1])
    for a in (out, console):
        cp = a["pilot_checkpoint"]
        assert cp["threshold_usd"] == 3.24 and "heavy_case_FULL" in cp["threshold_source"]
        assert cp["verdict"] == "not_evaluable" and cp["runs_fully_accounted"] == 1
        assert a["conditions"]["FULL"]["runs_with_unrecorded_usage"]["share"] == 0.5
        assert a["conditions"]["FULL"]["cost_usd"]["median_fully_accounted"] == 2.0
    assert "not_evaluable" in res.stderr and "lower bound" in res.stderr
    # score console: the cost line carries the completeness
    run = tmp_path / "run"
    run.mkdir()
    shutil.copy(LIVE_RUN / "report.json", run / "report.json")
    (run / "manifest.json").write_text(json.dumps(manifest([CUT_CALL])), encoding="utf-8")
    res = runner.invoke(app, ["score", str(run), "--key", str(PAYMENTS_KEY), "--doc", str(PAYMENTS_PDF),
                              "--judge", "fake", "--out", str(tmp_path / "o"), "--exploratory",
                              "--no-grounding-judges"])
    assert res.exit_code == 0, res.output
    console = json.loads(res.stdout[res.stdout.index("{"):res.stdout.rindex("}") + 1])
    assert console["cost"] == {"usage_completeness": "unrecorded", "cost_usd": None, "cost_usd_lower_bound": 1.10,
                               "calls_with_unrecorded_usage": 1}
    assert "lower bound" in res.stderr


def test_usage_completeness_dataclass_describe_counts_and_reasons():
    uc = UsageCompleteness(status=UNRECORDED, source="manifest",
                           calls=(CUT_CALL, {**CUT_CALL, "call_id": "llm-0007", "stage": "plan",
                                             "reason": "timeout_kill", "wall_s": None}))
    d = usage_mod.describe(uc)
    assert d.startswith("unrecorded_usage: 2 model calls with unrecorded usage")
    assert "llm-0003 assess" in d and "deadline cut" in d and "llm-0007 plan" in d and "timeout kill" in d
    with pytest.raises(ValueError):
        UsageCompleteness(status="partial", source="x", calls=())
