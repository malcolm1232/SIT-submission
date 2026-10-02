"""``sit-eval grade`` commands through the mounted CLI (offline: dry run and the fake judge only)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from sit_eval.cli import app

runner = CliRunner()


def test_grader_cli_dry_run_prints_calls_and_cost(graded_inputs) -> None:
    review, pages = graded_inputs
    r = runner.invoke(app, ["grade", "run", str(review), "--pdf", str(pages), "--judge", "claude_code", "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "DRY RUN" in r.output and "Planned calls: 4 (up to 5" in r.output and "Estimated cost: $" in r.output


def test_grader_cli_run_with_fake_judge(tmp_path: Path, graded_inputs) -> None:
    review, pages = graded_inputs
    out = tmp_path / "out"
    r = runner.invoke(app, ["grade", "run", str(review), "--pdf", str(pages), "--out", str(out), "--judge", "fake"])
    assert r.exit_code == 0, r.output
    assert "PLUMBING ONLY" in r.output and "S = 75.0" in r.output
    assert json.loads((out / "grade.json").read_text())["status"] == "complete"


def test_grader_cli_max_cost_stops(tmp_path: Path, graded_inputs) -> None:
    review, pages = graded_inputs
    out = tmp_path / "out"
    r = runner.invoke(app, ["grade", "run", str(review), "--pdf", str(pages), "--out", str(out), "--judge", "fake",
                            "--max-cost-usd", "0.0001"])
    assert r.exit_code == 3
    assert json.loads((out / "grade.json").read_text())["status"] == "aborted_budget"


def test_grader_cli_rejects_unknown_judge(tmp_path: Path, graded_inputs) -> None:
    review, pages = graded_inputs
    r = runner.invoke(app, ["grade", "run", str(review), "--pdf", str(pages), "--out", str(tmp_path / "o"),
                            "--judge", "gpt"])
    assert r.exit_code == 2


def test_grader_cli_validate_and_lock(tmp_path: Path, graded_inputs) -> None:
    review, pages = graded_inputs
    r = runner.invoke(app, ["grade", "validate", str(review), "--pdf", str(pages), "--dry-run"])
    assert r.exit_code == 0 and "20 grades" in r.output, r.output
    r = runner.invoke(app, ["grade", "validate", str(review), "--pdf", str(pages), "--out", str(tmp_path / "mv"),
                            "--runs", "1", "--checks", "V1,V10"])
    assert r.exit_code == 0, r.output
    assert "V1: passed=True" in r.output and "V10: passed=True" in r.output
    r = runner.invoke(app, ["grade", "validate", str(review), "--pdf", str(pages), "--checks", "V99", "--dry-run"])
    assert r.exit_code == 2
    r = runner.invoke(app, ["grade", "lock"])
    assert r.exit_code == 0 and '"ok": true' in r.output
