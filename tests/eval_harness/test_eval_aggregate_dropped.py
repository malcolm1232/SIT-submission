"""Scores files dropped from an aggregate and the pilot cost checkpoint (SIT FABLE ruling #29, 2026-10-03).

``sit-eval aggregate`` leaves a scores file out when its scoring was stopped by the judge budget before any
statistic, or when it is unreadable, schema-invalid or incomplete. A dropped run is a run of unknown cost, so
whenever a FULL scores file (or one whose condition cannot be read) is dropped, the prereg pilot checkpoint is
``not_evaluable``; every dropped file is listed with its reason in the aggregate JSON and on the console. Before
the ruling the checkpoint could ``pass`` on the FULL runs that remained.

Offline: fake judge, fixtures written here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from eval_builders import default_table, make_finding, make_review, responder_from
from eval_builders import run_pipeline as pipeline
from test_eval_usage_completeness import agg, key, manifest, runner, scored

from sit_eval import aggregate as aggregate_mod
from sit_eval.cli import app

BUDGET, UNREADABLE, SCHEMA, INCOMPLETE = "judge_budget_stop", "unreadable", "schema_invalid", "incomplete"


def stopped(tmp_path: Path, name: str, *, condition: str = "FULL", signed: bool = True) -> Path:
    """A scores.json whose scoring the judge budget stopped before any statistic (a real stop, fake judge)."""
    d = tmp_path / name
    d.mkdir()
    k = key()
    if signed:
        k["authoring_status"] = {"pending": [], "scored_run_ready": True}
    review = make_review([make_finding(1, "1")])
    review["metadata"]["run_id"] = name
    scores, _, _ = pipeline(d, review, k, responder_from(default_table()), manifest=manifest([], cost=9.0),
                            exploratory=not signed, condition=condition, reserve_usd=1.0, max_cost_usd=0.5)
    assert scores["status"] == "stopped_budget" and scores["metrics"] == {}
    p = d / "scores.json"
    p.write_text(json.dumps(scores), encoding="utf-8")
    return p


def passing(tmp_path: Path, prefix: str = "ok", condition: str = "FULL") -> list[Path]:
    """Two fully accounted runs whose median, $2.50, passes the $3.24 checkpoint on its own."""
    return [scored(tmp_path, f"{prefix}1", cost=2.0, calls=[], condition=condition),
            scored(tmp_path, f"{prefix}2", cost=3.0, calls=[], condition=condition)]


def edited(tmp_path: Path, name: str, edit: Any) -> Path:
    """A valid FULL scores file changed by ``edit`` (a function of the parsed dict, or raw text to write)."""
    p = scored(tmp_path, name, cost=1.0, calls=[])
    if isinstance(edit, str):
        p.write_text(edit, encoding="utf-8")
    else:
        s = json.loads(p.read_text())
        s = edit(s) or s
        p.write_text(json.dumps(s), encoding="utf-8")
    return p


def test_the_checkpoint_passes_on_the_remaining_runs_without_the_dropped_one(tmp_path: Path):
    """Control: the two runs alone pass; the defect was that adding a stopped third run changed nothing."""
    out = agg(passing(tmp_path))
    assert out["pilot_checkpoint"]["verdict"] == "pass" and out["dropped_inputs"] == []
    assert out["pilot_checkpoint"]["dropped_inputs"] == []


def test_a_budget_stopped_FULL_run_makes_the_checkpoint_not_evaluable(tmp_path: Path):
    stop = stopped(tmp_path, "stop")
    out = agg([*passing(tmp_path), stop])
    cp = out["pilot_checkpoint"]
    assert cp["verdict"] == "not_evaluable"
    assert "dropped" in cp["reason"] and "unknown cost" in cp["reason"] and str(stop) in cp["reason"]
    assert cp["runs"] == 2 and cp["median_fully_accounted"] == 2.5     # the remaining runs' figures stay visible
    [d] = out["dropped_inputs"]
    assert d["path"] == str(stop) and d["reason"] == BUDGET and d["condition"] == "FULL"
    assert "before any statistic" in d["detail"]
    assert cp["dropped_inputs"] == [d]
    assert str(stop) not in out["inputs"]
    assert any(str(stop) in w and BUDGET in w for w in out["warnings"])


def test_a_dropped_FULL_run_also_blocks_a_fail(tmp_path: Path):
    """The ruling makes the checkpoint not_evaluable whenever a FULL file was dropped, whatever the rest say."""
    high = [scored(tmp_path, "h1", cost=4.0, calls=[]), scored(tmp_path, "h2", cost=5.0, calls=[])]
    assert agg(high)["pilot_checkpoint"]["verdict"] == "fail"
    assert agg([*high, stopped(tmp_path, "stop")])["pilot_checkpoint"]["verdict"] == "not_evaluable"


@pytest.mark.parametrize(("edit", "reason", "condition"), [
    ('{"kind": "sit_eval.scores", "status": "fro', UNREADABLE, None),                          # truncated JSON
    ("\x00\x01 not json", UNREADABLE, None),
    ("[1, 2, 3]", SCHEMA, None),                                                               # not an object
    (lambda s: {**s, "kind": "sit_eval.aggregate"}, SCHEMA, None),                             # not a scores file
    (lambda s: {**s, "status": "finished"}, SCHEMA, "FULL"),                                   # status outside the enum
    (lambda s: {**s, "inputs": {k: v for k, v in s["inputs"].items() if k != "run_id"}}, SCHEMA, "FULL"),
    (lambda s: {**s, "inputs": None}, SCHEMA, None),
    (lambda s: {**s, "metrics": None}, SCHEMA, "FULL"),
    (lambda s: {**s, "metrics": {}}, INCOMPLETE, "FULL"),                                      # no statistic computed
], ids=["truncated", "binary", "array", "wrong_kind", "bad_status", "no_run_id", "no_inputs", "no_metrics",
        "empty_metrics"])
def test_each_drop_reason_is_listed_and_blocks_the_checkpoint(tmp_path: Path, edit: Any, reason: str,
                                                              condition: str | None):
    bad = edited(tmp_path, "bad", edit)
    out = agg([*passing(tmp_path), bad])
    [d] = out["dropped_inputs"]
    assert (d["path"], d["reason"], d["condition"]) == (str(bad), reason, condition) and d["detail"]
    cp = out["pilot_checkpoint"]
    assert cp["verdict"] == "not_evaluable" and cp["dropped_inputs"] == [d]
    if condition is None:
        assert "may be" in cp["reason"]          # a file whose condition cannot be read may be a FULL run


def test_a_missing_file_is_dropped_as_unreadable(tmp_path: Path):
    gone = tmp_path / "gone" / "scores.json"
    out = agg([*passing(tmp_path), gone])
    assert [(d["path"], d["reason"]) for d in out["dropped_inputs"]] == [(str(gone), UNREADABLE)]
    assert out["pilot_checkpoint"]["verdict"] == "not_evaluable"


def test_a_dropped_non_FULL_file_is_listed_but_does_not_block_the_FULL_checkpoint(tmp_path: Path):
    b0_stop = stopped(tmp_path, "b0stop", condition="B0")
    b0_bad = edited(tmp_path, "b0bad", lambda s: {**s, "inputs": {**s["inputs"], "condition": "B0"}, "metrics": {}})
    unlabelled = edited(tmp_path, "nolabel", lambda s: {**s, "status": "finished",
                                                        "inputs": {k: v for k, v in s["inputs"].items()
                                                                   if k != "condition"}})
    out = agg([*passing(tmp_path), *passing(tmp_path, "b", condition="B0"), b0_stop, b0_bad, unlabelled])
    listed = {d["path"]: (d["reason"], d["condition"]) for d in out["dropped_inputs"]}
    assert listed == {str(b0_stop): (BUDGET, "B0"), str(b0_bad): (INCOMPLETE, "B0"),
                      str(unlabelled): (SCHEMA, "unlabelled")}
    cp = out["pilot_checkpoint"]
    assert cp["verdict"] == "pass" and cp["dropped_inputs"] == []
    assert out["conditions"]["B0"]["cost_usd"]["runs"] == 2


def test_the_cli_lists_the_dropped_files_in_the_json_and_on_the_console(tmp_path: Path):
    stop = stopped(tmp_path, "stop")
    bad = edited(tmp_path, "bad", "{not json")
    res = runner.invoke(app, ["aggregate", *map(str, passing(tmp_path)), str(stop), str(bad), "--bootstrap-b", "100",
                              "--out", str(tmp_path / "a.json")])
    assert res.exit_code == 0, res.output
    out = json.loads((tmp_path / "a.json").read_text())
    console = json.loads(res.stdout[res.stdout.index("{"):res.stdout.rindex("}") + 1])
    for a in (out, console):
        assert [(d["path"], d["reason"]) for d in a["dropped_inputs"]] == [(str(stop), BUDGET), (str(bad), UNREADABLE)]
        assert a["pilot_checkpoint"]["verdict"] == "not_evaluable"
    err = res.stderr
    assert "2 scores files dropped from the aggregate" in err
    assert f"{stop} ({BUDGET}, condition FULL)" in err and f"{bad} ({UNREADABLE}, condition unknown)" in err
    line = next(x for x in err.splitlines() if x.startswith("pilot checkpoint"))
    assert "not_evaluable" in line and "dropped" in line


def test_the_console_says_nothing_of_drops_when_none(tmp_path: Path):
    res = runner.invoke(app, ["aggregate", *map(str, passing(tmp_path)), "--bootstrap-b", "100"])
    assert res.exit_code == 0, res.output
    assert "dropped" not in res.stderr and ": pass - " in res.stderr


def test_exploratory_interplay_is_unchanged(tmp_path: Path):
    expl = stopped(tmp_path, "expl_ok", signed=False)          # a stopped exploratory file is dropped, not refused
    out = agg([*passing(tmp_path), expl])
    assert out["exploratory"] is False and [d["path"] for d in out["dropped_inputs"]] == [str(expl)]
    assert out["pilot_checkpoint"]["verdict"] == "not_evaluable"
    # an exploratory input that is kept is still refused beside a dropped file, before any statistic
    k = key()
    d = tmp_path / "kept_expl"
    d.mkdir()
    s, _, _ = pipeline(d, make_review([make_finding(1, "1")]), k, responder_from(default_table()),
                       manifest=manifest([], cost=1.0), condition="FULL")
    assert s["exploratory"] is True
    kept = d / "scores.json"
    kept.write_text(json.dumps(s), encoding="utf-8")
    stop = stopped(tmp_path, "stop")
    conf = [str(p) for p in passing(tmp_path, "c")]
    res = runner.invoke(app, ["aggregate", *conf, str(kept), str(stop), "--bootstrap-b", "100"])
    assert res.exit_code == 2 and "refusing to aggregate" in res.output
    # with the flag: marked exploratory, the drop still listed and the checkpoint still not evaluable
    res = runner.invoke(app, ["aggregate", *conf, str(kept), str(stop),
                              "--bootstrap-b", "100", "--exploratory", "--out", str(tmp_path / "x.json")])
    assert res.exit_code == 0, res.output
    out = json.loads((tmp_path / "x.json").read_text())
    assert out["exploratory"] is True and out["exploratory_inputs"] == [str(kept)]
    assert [d["path"] for d in out["dropped_inputs"]] == [str(stop)]
    assert out["pilot_checkpoint"]["verdict"] == "not_evaluable"


def test_load_scores_keeps_its_two_value_return(tmp_path: Path):
    rows, warnings = aggregate_mod.load_scores([*passing(tmp_path), stopped(tmp_path, "stop")])
    assert len(rows) == 2 and any(BUDGET in w for w in warnings)
