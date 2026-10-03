"""``dra coverage [--run runs/<id>]``: the criteria x sections map (runbook §5), offline, < 5 s."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import sit_review_agent.progress  # noqa: F401 - bind ConsoleProgress's default stream before CliRunner swaps it
from sit_review_agent.cli import app
from sit_review_agent.paths import config_dir, repo_root
from sit_review_agent.report.coverage import (
    build_coverage,
    coverage_rows_from_markdown,
    format_coverage,
    section_key,
)
from sit_review_agent.selftest import FIXTURE_DIR

PDF = FIXTURE_DIR / "design.pages.txt"
CASSETTES = FIXTURE_DIR / "cassettes"
LIVE = repo_root() / "docs" / "live_runs" / "live_cc_opus_payments_v1"


@pytest.fixture
def cfgdir(tmp_path: Path) -> Path:
    dst = tmp_path / "config"
    shutil.copytree(config_dir(), dst)
    agent = dst / "agent.yaml"
    agent.write_text(agent.read_text(encoding="utf-8").replace("run_root: runs", f"run_root: {tmp_path / 'runs'}"),
                     encoding="utf-8")
    return dst


def invoke(args: list[str]) -> Any:
    res = CliRunner().invoke(app, args)
    assert "Traceback" not in res.output, res.output
    return res


@pytest.fixture
def run(cfgdir: Path) -> Path:
    res = invoke(["run", str(PDF), "--config", str(cfgdir), "--transport", "fake", "--replay", str(CASSETTES),
                  "--disable-tool", "mcp-research-information", "--run-id", "cov"])
    assert res.exit_code == 0, res.output
    return cfgdir.parent / "runs" / "cov"


def test_coverage_map_of_a_run(run: Path, cfgdir: Path) -> None:
    t0 = time.monotonic()
    res = invoke(["coverage", "--run", str(run)])
    assert res.exit_code == 0, res.output
    assert time.monotonic() - t0 < 5                                   # robustness DEMO-06 budget
    out = res.output
    assert "Coverage map: run cov" in out and "11 criteria x 5 section(s)" in out
    assert "C1 design_intent: no issue" in out
    assert "C5 claims_and_external_constraints: findings (1: FND-004)" in out
    lines = {ln.split()[0]: ln for ln in out.splitlines() if ln[:1].isdigit()}
    assert set(lines) == {"1", "4", "6", "11", "20"}                    # 4.1 -> 4, 6.2 -> 6, 11.3 -> 11
    assert "1H" in lines["4"] and "1M" in lines["4"]                   # FND-004 (high) and FND-002 (medium)
    assert "ok" in lines["1"] and "1" not in lines["1"].split()[2:]    # checked, no issue
    assert lines["11"].rstrip().endswith("SA-001")                     # a sound area
    assert "Legend:" in out and "checked, no issue" in out
    # the same map: positional run, run ID, default latest run, JSON
    assert invoke(["coverage", str(run)]).output == out
    assert invoke(["coverage", "cov", "--config", str(cfgdir)]).output == out
    assert invoke(["coverage", "--config", str(cfgdir)]).output == out
    data = json.loads(invoke(["coverage", "--run", str(run), "--json"]).output)
    assert data["outcomes"]["design_intent"] == "no_issue"
    assert {r["section"] for r in data["rows"]} == {"1", "4", "6", "11", "20"}
    every = invoke(["coverage", "--run", str(run), "--depth", "0"]).output
    assert "4.1 Load" in every and "11.3 Accessibility" in every


def test_coverage_marks_not_applicable_criteria(run: Path) -> None:
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    state["coverage"][0]["outcome"] = "not_applicable"                 # design_intent
    (run / "state.json").write_text(json.dumps(state), encoding="utf-8")
    cm = build_coverage(run)
    assert {r.cells["design_intent"] for r in cm.rows} == {"-"}
    assert "C1 design_intent: not applicable" in format_coverage(cm)


def test_criterion_whose_findings_were_not_verified_is_not_shown_as_clear(run: Path) -> None:
    """The fixture run raises one finding under requirement_completeness whose anchor verify cannot
    confirm, so it is not in the report. The map used to show that criterion as "findings" with no
    ID and "ok" (checked, no issue) in every section."""
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    assert any(u["text"].startswith("Unverified") for u in report["unresolved"])
    cm = build_coverage(run)
    assert cm.outcomes["requirement_completeness"] == "findings"
    assert not cm.criterion_findings["requirement_completeness"]
    assert {r.cells["requirement_completeness"] for r in cm.rows} == {"?"}
    assert {r.cells["design_intent"] for r in cm.rows} == {"ok"}                 # a clear criterion is unchanged
    out = format_coverage(cm)
    assert "C3 requirement_completeness: findings (none in the report: raised but not verified" in out
    assert "? = the criterion raised" in " ".join(out.split())
    row = next(ln for ln in (run / "report.md").read_text(encoding="utf-8").splitlines()
               if ln.startswith("| requirement_completeness |"))
    assert "1 finding(s) raised here could not be verified" in row              # verify says so in the note
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    kept = next(c for c in state["coverage"] if c["criterion_id"] == "verifiability")
    testing = next(f["id"] for f in report["findings"] if f["title"] == "Peak-day reminder volume is not tested")
    assert kept["finding_ids"] == [testing] and "could not be verified" not in kept["note"]


def test_coverage_of_a_run_with_no_assessment_says_not_assessed(run: Path) -> None:
    """``assess`` marks every row ``not_applicable`` with a "not assessed: ..." note when the run
    produced no assessment; the map must not call those criteria "not applicable"."""
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    for c in state["coverage"]:
        c.update(outcome="not_applicable", finding_ids=[], note="not assessed: out of time before assessment "
                                                                 "(run deadline)")
    state["finding_meta"] = {}
    (run / "state.json").write_text(json.dumps(state), encoding="utf-8")
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    report["findings"], report["sound_areas"] = [], []
    report["verdict"]["label"] = "not_assessed"
    (run / "report.json").write_text(json.dumps(report), encoding="utf-8")
    cm = build_coverage(run)
    out = format_coverage(cm)
    assert "verdict not_assessed | 0 finding(s)" in out
    assert "C1 design_intent: not assessed: out of time before assessment (run deadline)" in out
    assert "not applicable" not in out.split("Legend:")[0]
    assert {cell for r in cm.rows for cell in r.cells.values()} == {"-"}


def test_coverage_of_a_report_only_run_directory() -> None:
    """``docs/live_runs/`` keeps only report.json, report.md and the manifest: the coverage rows
    come from the report's coverage table and the rows from the cited sections."""
    cm = build_coverage(LIVE)
    assert any("report.md" in s for s in cm.sources)
    assert len(cm.criteria) == 11 and all(o == "findings" for o in cm.outcomes.values())
    assert cm.rows and cm.rows[0].key == "2"
    assert sum(len(ids) for r in cm.rows for ids in r.findings.values()) > 0
    assert "Title page" in [r.key for r in cm.rows]


def test_coverage_usage_errors(cfgdir: Path, tmp_path: Path, run: Path) -> None:
    assert invoke(["coverage", str(tmp_path / "nope")]).exit_code == 2
    assert invoke(["coverage", str(run), "--run", str(run)]).exit_code == 2
    assert invoke(["coverage", "--run", str(run), "--depth", "-1"]).exit_code == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    assert invoke(["coverage", "--run", str(empty)]).exit_code == 2


def test_helpers() -> None:
    assert section_key("4.3.2", 1) == "4" and section_key("4.3.2", 2) == "4.3" and section_key("4.3.2", 0) == "4.3.2"
    assert section_key("Title page", 1) == "Title page"
    md = ("# x\n\n## Review coverage\n\n| Criterion | Outcome | Findings | Note |\n|---|---|---|---|\n"
          "| a | findings | FND-001, FND-002 | n |\n| b | no issue | - | ok |\n\n## Run details\n| x | y |\n")
    rows = coverage_rows_from_markdown(md)
    assert rows == [{"criterion_id": "a", "outcome": "findings", "finding_ids": ["FND-001", "FND-002"], "note": "n"},
                    {"criterion_id": "b", "outcome": "no_issue", "finding_ids": [], "note": "ok"}]
