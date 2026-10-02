"""Results table writer: ``tests/robustness/results/robustness_results.csv`` (research/robustness/
README.md §8). One row per P0 scenario for the evaluated commit, plus the generated summary block
(``robustness_summary.txt`` next to the CSV).

Rows come from two places:

* scenarios the offline suite ran in this session (``test_robustness_scenarios.py``): ``PASS`` /
  ``FAIL`` from the run, k = number of variants, pass^k = 1.0 only if every variant passed;
* every other P0 scenario, from :mod:`robustness_coverage`: ``FAIL`` for a known agent defect that
  needs a decision, otherwise ``BLOCKED`` (not evaluated by this offline suite: it needs the live
  model or MCP, a fixture that is not authored yet, or it is a static check covered elsewhere; the
  note says which and gives the command).

The suite writes to a temp directory; ``ROBUSTNESS_RESULTS_CSV=<path>`` writes the real file
(command in README.md).
"""

from __future__ import annotations

import contextlib
import csv
import io
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from robustness_coverage import COVERAGE, offline_command, p0_rows

from sit_review_agent.manifest import git_state
from sit_review_agent.paths import repo_root

COLUMNS = ("scenario_id", "category", "severity", "tier", "level", "k", "passes", "pass_rate", "pass_hat_k",
           "key_metric", "value", "threshold", "status", "commit", "model", "date", "duration_s", "artefacts", "notes")
STATUSES = ("PASS", "FAIL", "FLAKY", "BLOCKED", "N/A", "RETIRED")
MODEL_L0 = "fake (scripted FakeGateway)"


@dataclass
class ResultRow:
    scenario_id: str
    status: str = "FAIL"
    k: int = 1
    passes: int = 0
    key_metric: str = ""
    value: Any = ""
    threshold: str = ""
    duration_s: float = 0.0
    artefacts: str = ""
    notes: str = ""
    level: str = "L0"
    model: str = MODEL_L0


@dataclass
class ResultSink:
    """Collects the rows of the scenarios run in this session."""

    rows: list[ResultRow] = field(default_factory=list)

    @contextlib.contextmanager
    def row(self, scenario_id: str, *, notes: str = "", runs: int = 1) -> Iterator[ResultRow]:
        r = ResultRow(scenario_id, k=runs, notes=notes)
        self.rows.append(r)
        try:
            yield r
        except BaseException as exc:
            r.status, r.passes = "FAIL", 0
            r.notes = (r.notes + "; " if r.notes else "") + f"{type(exc).__name__}: {str(exc)[:300]}"
            raise
        r.status, r.passes = "PASS", runs


def _static_row(sid: str) -> ResultRow:
    cov = COVERAGE[sid]
    if cov.decision:
        note = f"needs decision: {cov.decision}"
        if cov.kind == "offline" and cov.schedule:
            note += f"; reproduce: {offline_command(sid)}"
        return ResultRow(sid, status="FAIL", passes=0, notes=note, key_metric="known agent defect")
    if cov.kind == "offline":
        return ResultRow(sid, status="BLOCKED", notes="offline scenario not run in this session")
    note = "not evaluated offline: " + cov.how
    if cov.laptop:
        note += f"; laptop: {cov.laptop}"
    if cov.covered_by:
        note += f"; covered by {cov.covered_by}"
    return ResultRow(sid, status="BLOCKED", notes=note, level="L1/L2" if cov.kind == "laptop" else "-", model="-")


def table(session_rows: list[ResultRow]) -> list[dict[str, Any]]:
    """Every P0 scenario, in scenarios.md order: the session's row when it ran, else the static row."""
    meta = p0_rows()
    ran = {r.scenario_id: r for r in session_rows}
    commit = git_state(repo_root()).get("commit") or "unknown"
    today = date.today().isoformat()
    out: list[dict[str, Any]] = []
    for sid, m in meta.items():
        r = ran.get(sid) or _static_row(sid)
        evaluated = sid in ran
        out.append({
            "scenario_id": sid, "category": sid.split("-")[0], "severity": m["sev"], "tier": m["tier"],
            "level": r.level, "k": r.k if evaluated else "", "passes": r.passes if evaluated else "",
            "pass_rate": f"{r.passes / r.k:.2f}" if evaluated and r.k else "",
            "pass_hat_k": ("1.00" if r.passes == r.k else "0.00") if evaluated else "",
            "key_metric": r.key_metric, "value": r.value, "threshold": r.threshold, "status": r.status,
            "commit": commit[:12], "model": r.model, "date": today,
            "duration_s": f"{r.duration_s:.2f}" if evaluated else "", "artefacts": r.artefacts, "notes": r.notes})
    return out


def summary(rows: list[dict[str, Any]]) -> str:
    """The README §8 summary block (P0 only: this table holds the P0 tier)."""
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("PASS", "FAIL", "FLAKY", "BLOCKED", "N/A")}
    safety = [r for r in rows if r["scenario_id"] in ("ADV-05", "OPS-03", "BEH-04")]
    safe = "yes" if safety and all(r["status"] == "PASS" for r in safety) else "no"
    return ("Tier  Total  PASS  FAIL  FLAKY  BLOCKED  N/A   | Safety (ASR, canary, INV-05): k/k?\n"
            f"P0    {len(rows):>5}  {counts['PASS']:>4}  {counts['FAIL']:>4}  {counts['FLAKY']:>5}  "
            f"{counts['BLOCKED']:>7}  {counts['N/A']:>3}   | {safe} (offline L0 only)\n")


def write_csv(path: Path, session_rows: list[ResultRow]) -> Path:
    rows = table(session_rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")
    (path.parent / "robustness_summary.txt").write_text(summary(rows), encoding="utf-8")
    return path
