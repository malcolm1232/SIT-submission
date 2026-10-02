"""The results writer (research/robustness/README.md §8): one row per P0 scenario, the template's
columns, valid statuses, the summary block, "awaiting integration" rows for the concurrent redesign;
the suite itself writes the file at session end (conftest.py ``results_sink``)."""

from __future__ import annotations

import csv
from pathlib import Path

from robustness_coverage import AWAITING_INTEGRATION, CONCURRENT, CONCURRENT_META, COVERAGE, p0_rows
from robustness_results import COLUMNS, STATUSES, ResultRow, ResultSink, summary, table, write_csv

TEMPLATE = ("scenario_id,category,severity,tier,level,k,passes,pass_rate,pass_hat_k,key_metric,value,threshold,"
            "status,commit,model,date,duration_s,artefacts,notes")


def test_writer_produces_the_template_table(tmp_path: Path) -> None:
    sink = ResultSink()
    with sink.row("INF-03", runs=1) as r:
        r.key_metric, r.value, r.threshold, r.duration_s = "ledger entries from the dead server", 0, "0", 0.2
    try:
        with sink.row("INF-18", runs=10):
            raise AssertionError("seed 7 did not complete")
    except AssertionError:
        pass
    path = write_csv(tmp_path / "results" / "robustness_results.csv", sink.rows)
    text = path.read_text(encoding="utf-8")
    assert text.splitlines()[0] == TEMPLATE == ",".join(COLUMNS)
    rows = list(csv.DictReader(text.splitlines()))
    assert [r["scenario_id"] for r in rows] == [*p0_rows(), *CONCURRENT_META]   # 81 in scenarios.md order, then 6
    by = {r["scenario_id"]: r for r in rows}
    assert all(r["status"] in STATUSES and r["tier"] == "P0" for r in rows)
    assert by["INF-03"]["status"] == "PASS" and by["INF-03"]["pass_hat_k"] == "1.00" and by["INF-03"]["k"] == "1"
    inf18 = by["INF-18"]
    assert inf18["status"] == "FAIL" and inf18["pass_hat_k"] == "0.00" and "seed 7" in inf18["notes"]
    for sid, cov in COVERAGE.items():                                    # rows the session did not run
        if sid in ("INF-03", "INF-18"):
            continue
        if cov.decision:
            assert by[sid]["status"] == "FAIL" and by[sid]["notes"].startswith("needs decision"), sid
        else:
            assert by[sid]["status"] == "BLOCKED", sid
        if cov.awaiting:
            assert by[sid]["notes"].startswith("awaiting integration") and cov.how in by[sid]["notes"], sid
    for sid in CONCURRENT:
        assert by[sid]["status"] == "BLOCKED" and by[sid]["notes"].startswith("awaiting integration"), sid
        assert (by[sid]["severity"], by[sid]["tier"]) == (CONCURRENT_META[sid]["sev"], "P0"), sid
    block = (path.parent / "robustness_summary.txt").read_text(encoding="utf-8")
    assert block.startswith("Tier  Total  PASS  FAIL") and "P0       87     1" in block


def test_a_changed_row_that_ran_stays_awaiting_integration() -> None:
    """A row whose expectation the concurrent redesign changed is never PASS before integration, even
    when its sequential-design case passed this session; that result is kept in the note."""
    assert AWAITING_INTEGRATION and COVERAGE["LLM-05"].awaiting
    rows = {r["scenario_id"]: r for r in table([ResultRow("LLM-05", status="PASS", passes=2, k=2,
                                                          key_metric="virtual run time", value=420)])}
    r = rows["LLM-05"]
    assert r["status"] == "BLOCKED" and r["k"] == "" and r["pass_hat_k"] == ""
    assert r["notes"].startswith("awaiting integration") and "sequential-design case this session: PASS" in r["notes"]
    assert "salvaged, disclosed report, exit 0" in r["notes"]


def test_summary_counts() -> None:
    rows = table([ResultRow("ADV-05", status="PASS", passes=1), ResultRow("OPS-03", status="PASS", passes=1),
                  ResultRow("BEH-04", status="PASS", passes=1)])
    text = summary(rows)
    assert "| yes" in text and f"{len(rows):>5}" in text
