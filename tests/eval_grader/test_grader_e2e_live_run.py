"""PLUMBING ONLY: grade the real live run (docs/live_runs/live_cc_opus_payments_v1) with a deterministic FakeJudge.

The scores mean nothing. The test checks that the whole path works on a real 21-finding Review and the real
PDF through the agent's own ingest: projection, rendering, harness quote checks, Pass A/B, aggregation,
outputs, and that no forbidden run metadata reaches any grader input.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sit_eval.grader import grade_review, schemas
from sit_eval.grader.pipeline import load_document, plan_grade
from sit_eval.judge import FakeJudge

REPO = Path(__file__).resolve().parents[2]
LIVE = REPO / "docs" / "live_runs" / "live_cc_opus_payments_v1"
PDF = REPO / "eval" / "synthetic" / "payments_orchestration" / "design_v1.pdf"
FORBIDDEN = ["claude-opus", "claude_code", "live_cc_opus", "REV-live", "no_tools", "4278b5f9ea2a",
             "great-hopper", "run_manifest", "research_log", "provenance", "prompt_hash", "effective_config"]


@pytest.fixture(scope="module")
def live_doc():
    review = json.loads((LIVE / "report.json").read_text(encoding="utf-8"))
    return load_document(PDF, doc_id=review["metadata"]["documents"][0]["doc_id"])


def test_grader_plumbing_only_live_run(tmp_path: Path, live_doc, heuristic_judge: FakeJudge) -> None:
    res = grade_review(LIVE / "report.json", live_doc, tmp_path / "grade", judge=heuristic_judge)
    rep = res.report
    assert rep["label"].startswith("PLUMBING ONLY")
    assert rep["status"] == "complete" and len(heuristic_judge.calls) == 4
    assert rep["document"]["matches_review"] is True                     # same canonical text as the agent read
    assert rep["harness_checks"]["review_schema_errors"] == []
    anchors = rep["harness_checks"]["anchors"]
    assert anchors["verified"] > 0 and anchors["not_found"] == 0
    assert len(rep["pass_a"]["merged_table"]["findings"]) == 21
    assert schemas.errors(schemas.GRADE_REPORT, rep) == []
    assert rep["labels"]["same_family"] is None or isinstance(rep["labels"]["same_family"], bool)
    texts = [c.system + c.user for c in heuristic_judge.calls]
    texts += [p.read_text(encoding="utf-8") for p in (tmp_path / "grade" / "inputs").iterdir()]
    texts.append((tmp_path / "grade" / "grader_projection.json").read_text(encoding="utf-8"))
    for t in texts:
        for s in FORBIDDEN:
            assert s not in t, s
    # the two Pass A samples saw different finding orders
    a1, a2 = rep["pass_a"]["samples"]
    assert a1["order"] != a2["order"] and sorted(a1["order"]) == sorted(a2["order"])


def test_grader_live_run_dry_run_plan(live_doc) -> None:
    plan = plan_grade(LIVE / "report.json", live_doc)
    assert plan["calls_min"] == 4 and plan["calls_max"] == 5 and plan["findings"] == 21
    assert 0.5 < plan["cost_usd_min"] < plan["cost_usd_max"] < 10
