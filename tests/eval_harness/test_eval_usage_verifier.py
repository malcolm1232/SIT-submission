"""Session 4 verifier checks on ruling #28 (cost metrics under unknown usage), 2026-10-03.

The harness re-implements the runtime's ``unrecorded_reason`` (``harness/sit_eval/usage.py``) so that it
does not import the runtime's manifest module. These tests tie the two copies together on the merged tree:
the same entry gives the same answer in both, and the demo measurement run's real ``llm.jsonl`` gives the
same unrecorded calls through the runtime's ``journal_usage`` and the harness's ``from_call_log`` (read by
code; nothing of it is printed). They also pin the pilot checkpoint at the threshold, a run that reports no
figure in the lower-bound median, and the aggregate console with no threshold.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from test_eval_usage_completeness import CUT_CALL, LEGACY_CUT, NEW_CUT, SOME, agg, runner, scored

from sit_eval import usage as usage_mod
from sit_eval.cli import app
from sit_review_agent import manifest as runtime_manifest
from sit_review_agent.paths import repo_root
from sit_review_agent.rundir import RunDir

DEMO_RUN = repo_root() / "docs" / "live_runs" / "demo_profile_measure_1"

#: Every shape the rule distinguishes, new and legacy.
CASES: list[dict[str, Any]] = [
    NEW_CUT, {**NEW_CUT, "usage_unrecorded": "timeout_kill", "fake": True},
    {**NEW_CUT, "usage_unrecorded": "process_fault"}, {**NEW_CUT, "usage_unrecorded": "connection_lost"},
    {**NEW_CUT, "usage_unrecorded": "interrupted"}, {**NEW_CUT, "usage_unrecorded": ""},
    LEGACY_CUT, {**LEGACY_CUT, "outcome": "LLMTimeoutError"}, {**LEGACY_CUT, "usage": dict(SOME)},
    {**LEGACY_CUT, "call_cost_usd": 0.0}, {**LEGACY_CUT, "status_code": 529}, {**LEGACY_CUT, "status_code": 0},
    {**LEGACY_CUT, "sent": False}, {**LEGACY_CUT, "sent": True}, {**LEGACY_CUT, "fault": None},
    {**LEGACY_CUT, "replayed": True}, {**LEGACY_CUT, "fake": True}, {**LEGACY_CUT, "outcome": "LLMTruncatedError"},
    {**LEGACY_CUT, "outcome": "ok", "usage": dict(SOME)}, {**LEGACY_CUT, "usage": None}, {**LEGACY_CUT, "usage": {}},
    {**LEGACY_CUT, "outcome": None}, {},
]


@pytest.mark.parametrize("entry", CASES)
def test_the_harness_rule_answers_as_the_runtime_rule(entry: dict[str, Any]):
    assert usage_mod.unrecorded_reason(entry) == runtime_manifest.unrecorded_reason(entry)


def test_the_demo_run_call_log_reads_the_same_through_both_copies():
    log = DEMO_RUN / "llm.jsonl"
    assert log.is_file()
    runtime = runtime_manifest.journal_usage(RunDir(DEMO_RUN))["calls_with_unrecorded_usage"]
    harness = usage_mod.from_call_log(log)
    assert list(harness.calls) == runtime
    assert harness.status == usage_mod.UNRECORDED and harness.count == 1
    assert (runtime[0]["call_id"], runtime[0]["stage"], runtime[0]["reason"]) == ("llm-0003", "assess", "deadline_cut")


def test_the_usage_module_does_not_import_the_agent_package():
    tree = ast.parse(Path(usage_mod.__file__).read_text(encoding="utf-8"))
    names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    names += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not [m for m in names if m.startswith("sit_review_agent")]


def test_pilot_checkpoint_passes_at_exactly_the_threshold_and_fails_just_above(tmp_path: Path):
    paths = [scored(tmp_path, "t1", cost=3.0, calls=[]), scored(tmp_path, "t2", cost=3.24, calls=[]),
             scored(tmp_path, "t3", cost=3.5, calls=[])]
    cp = agg(paths)["pilot_checkpoint"]
    assert cp["median_fully_accounted"] == 3.24 and cp["verdict"] == "pass"
    paths = [scored(tmp_path, "u1", cost=3.0, calls=[]), scored(tmp_path, "u2", cost=3.25, calls=[]),
             scored(tmp_path, "u3", cost=3.5, calls=[])]
    assert agg(paths)["pilot_checkpoint"]["verdict"] == "fail"


def test_a_run_with_no_figure_counts_at_zero_in_the_lower_bound_median(tmp_path: Path):
    # one run with a $5 lower bound and one of unknown completeness that reports no cost at all: the true median
    # could be as low as $2.50, so the lower bound must not fail the checkpoint
    paths = [scored(tmp_path, "z1", cost=5.0, calls=[CUT_CALL]),
             scored(tmp_path, "z2", cost=None, calls=None)]  # type: ignore[arg-type]
    out = agg(paths)
    c = out["conditions"]["FULL"]["cost_usd"]
    assert c["median_lower_bound_all_runs"] == 2.5
    assert c["runs_with_a_lower_bound"] == 1 and c["runs_without_a_figure_counted_at_zero"] == 1
    assert out["pilot_checkpoint"]["verdict"] == "not_evaluable"


def test_the_aggregate_console_without_a_threshold_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from sit_eval import prereg as prereg_mod

    monkeypatch.setattr(prereg_mod, "pilot_cost_threshold_usd", lambda *a, **k: None)
    paths = [scored(tmp_path, "n1", cost=2.0, calls=[])]
    res = runner.invoke(app, ["aggregate", *map(str, paths), "--bootstrap-b", "100", "--out", str(tmp_path / "a.json")])
    assert res.exit_code == 0, res.output
    assert "vs no threshold): not_evaluable" in res.stderr and "$None" not in res.stderr
