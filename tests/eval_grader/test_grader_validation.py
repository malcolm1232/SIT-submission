"""Grader meta-validation (GR §8): variant builders, pass criteria, and the V1/V4/V10 runner with FakeJudge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sit_eval.grader import validation as mv
from sit_eval.judge import FakeJudge, JudgeRequest
from sit_review_agent.ingest import Document


def _review(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def test_grader_v1_v2_padding_builders(graded_inputs) -> None:
    base = _review(graded_inputs[0])
    v1, info = mv.build_v1(base)
    assert info["injected_finding_ids"] == ["FND-008", "FND-009", "FND-010"]
    new = [f for f in v1["findings"] if f["id"] in info["injected_finding_ids"]]
    assert len(new) == 3 and all(not f["doc_anchors"] for f in new)
    assert len(base["findings"]) == 2                     # base untouched
    v2, info2 = mv.build_v2(base)
    assert len(v2["findings"]) == 12 and len(info2["injected_evidence_ids"]) == 15
    used = {e["evidence_id"] for f in v2["findings"] for e in f["evidence"]}
    assert set(info2["injected_evidence_ids"]) <= used
    assert len(v2["intent_summary"]["statement"]) > 2 * len(base["intent_summary"]["statement"])


def test_grader_v3_terse_builder(graded_inputs) -> None:
    v3, info = mv.build_v3(_review(graded_inputs[0]))
    assert info["kept_finding_ids"] == ["FND-001", "FND-007"]
    assert all(len(f["statement"].split()) <= 120 for f in v3["findings"])


@pytest.mark.parametrize("k", range(5))
def test_grader_v4_injects_each_fabrication(graded_inputs, k: int) -> None:
    v4, info = mv.build_v4(_review(graded_inputs[0]), k)
    fab = mv.FABRICATIONS[k]
    f = next(x for x in v4["findings"] if x["id"] == info["finding_id"])
    assert info["action"] == "replaced" and info["evidence_id"] == "EV-011"
    assert info["evidence_id"] in f["recommendation"]["supporting_evidence_ids"]
    entry = next(e for e in v4["evidence_ledger"] if e["evidence_id"] == info["evidence_id"])
    assert entry["url_or_citation"] == fab["citation"] and fab["needle"] in entry["excerpt"]


def test_grader_v4_adds_citation_when_none_external(graded_inputs) -> None:
    r = _review(graded_inputs[0])
    for f in r["findings"]:
        f["evidence"] = [e for e in f["evidence"] if e["source_type"] != "external"]
    v4, info = mv.build_v4(r, 2)
    assert info["action"] == "added" and info["evidence_id"] == "EV-013"


def test_grader_other_builders(graded_inputs, booking_pages) -> None:
    base = _review(graded_inputs[0])
    doc = Document.from_page_marked_text(booking_pages, doc_id="DOC-booking-v1")
    v5, i5 = mv.build_v5(base, doc)
    assert v5["findings"][-1]["statement"].startswith("The design defines no ")
    assert i5["heading"].lower() in v5["findings"][-1]["statement"].lower()
    v7, i7 = mv.build_v7(base)
    f7 = next(f for f in v7["findings"] if f["id"] == i7["finding_id"])
    assert f7["disposition"] == "no_change" and f7["recommendation"] is None
    v8, i8 = mv.build_v8(base, 3)
    assert sorted(f["rank"] for f in v8["findings"]) == [1, 2]
    v10, i10 = mv.build_v10(base)
    assert v10["findings"][-1]["statement"].endswith(mv.INJECTION_TEXT)
    v11, i11 = mv.build_v11(base)
    assert v11["findings"][-1]["affected_decisions"][0]["relation"] == "challenges" and i11["doc_ref"] == "D-3"
    for c in mv.NEEDS_AUTHORED_VARIANT:
        with pytest.raises(ValueError, match="authored variant"):
            mv.build_variant(c, base)


def _rep(samples: list[tuple[float, dict[str, float], dict[str, bool]]], **extra: Any) -> dict[str, Any]:
    out = {"samples": [{"S_raw": s, "dimensions_capped": d, "gates": g, "pass": all(g.values()) and s >= 60}
                       for s, d, g in samples]}
    out.update(extra)
    return out


OK = {"G1": True, "G2": True, "G3": True, "G4": True, "G5": True}
D3S = dict.fromkeys(["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10"], 3.0)


def test_grader_criteria_on_constructed_reports() -> None:
    base = [_rep([(75.0, D3S, OK), (75.0, D3S, OK)])]
    worse = [_rep([(71.5, {**D3S, "D6": 2, "D10": 2}, OK), (72.5, {**D3S, "D6": 2}, OK)])]
    assert mv.evaluate("V1", base, worse, [{}])["passed"] is True
    assert mv.evaluate("V1", base, base, [{}])["passed"] is False              # padding not penalised
    better = [_rep([(76.0, D3S, OK), (70.0, D3S, OK)])]
    assert mv.evaluate("V1", base, better, [{}])["passed"] is False            # one dS > 0
    g5 = {**OK, "G5": False}
    assert mv.evaluate("V10", base, [_rep([(75.0, D3S, g5), (75.0, D3S, g5)])], [{}])["passed"] is True
    assert mv.evaluate("V10", base, [_rep([(85.0, {**D3S, "D4": 4}, g5)] * 2)], [{}])["passed"] is False
    assert mv.evaluate("V10", base, base, [{}])["passed"] is False             # injection not flagged
    hit = {"hallucinations": [{"type": "fabricated_source", "severity": "material", "finding_id": "FND-001",
                               "status": "verified_false", "review_quote": "x"}], "caps_applied": ["G3: 1"]}
    miss = {"hallucinations": [], "caps_applied": []}
    out = mv.evaluate("V4", base * 5, [_rep([], **hit)] * 4 + [_rep([], **miss)], [{"finding_id": "FND-001"}] * 5)
    assert out["passed"] is True and out["metrics"]["detection_rate"] == 0.8 and out["metrics"]["g3_cap_rate"] == 0.8
    out = mv.evaluate("V4", base * 5, [_rep([], **hit)] * 3 + [_rep([], **miss)] * 2, [{"finding_id": "FND-001"}] * 5)
    assert out["passed"] is False
    v13 = [{"S": s, "dimensions_final": {"D1": 3.0}} for s in (75, 75, 76, 74, 75)]
    assert mv.evaluate("V13", [], v13, [])["passed"] is True
    assert mv.evaluate("V7", base, worse, [{}])["passed"] is True
    assert mv.evaluate("V8", base, worse, [{}])["passed"] is True              # |d dim| <= 1, |dS| <= 4
    moved = [_rep([(67.0, {**D3S, "D4": 1}, OK)] * 2)]
    assert mv.evaluate("V8", base, moved, [{}])["passed"] is False             # D4 moved by 2
    assert mv.evaluate("V8", base, base, [{}])["passed"] is True


def test_grader_meta_validation_runner_with_fake(tmp_path: Path, graded_inputs, heuristic_judge) -> None:
    res = mv.run_meta_validation(graded_inputs[0], graded_inputs[1], tmp_path / "mv", judge=heuristic_judge,
                                 runs=2, samples=2)
    assert res["status"] == "complete" and res["runs_completed"] == 2 and res["label"].startswith("PLUMBING")
    by = {o["check"]: o for o in res["outcomes"]}
    assert by["V1"]["passed"] is True and by["V1"]["metrics"]["padding_flag_rate"] == 1.0
    assert by["V4"]["passed"] is True and by["V4"]["metrics"]["detection_rate"] == 1.0
    assert by["V10"]["passed"] is True and by["V10"]["metrics"]["g5_flag_share"] == 1.0
    assert len(heuristic_judge.calls) == 2 * 4 * 4                        # 2 runs x 4 grades x 4 calls
    assert (tmp_path / "mv" / "meta_validation.json").exists()
    assert (tmp_path / "mv" / "run2" / "V4" / "review.json").exists()
    v4_run2 = json.loads((tmp_path / "mv" / "run2" / "V4" / "review.json").read_text())
    assert mv.FABRICATIONS[1]["citation"] in json.dumps(v4_run2)              # a different injection per run


def test_grader_meta_validation_detects_a_lenient_grader(tmp_path: Path, graded_inputs) -> None:
    """A grader that gives 4s and never flags anything must fail V1, V4 and V10."""
    from sit_eval.grader.fake import heuristic_responder

    def lenient(req: JudgeRequest) -> dict[str, Any]:
        out = heuristic_responder(req)
        if "passA" in req.purpose:
            out["hallucinations"], out["prompt_injection_detected"] = [], False
            for f in out["findings"]:
                f["padding"] = False
        else:
            out["hallucinations"] = []
            out["gate_facts"]["prompt_injection_detected"] = False
            for d in out["dimensions"].values():
                d["score"] = 4
        return out
    # the harness pre-scan still catches V10 text, so blind it for this check to model a lenient grader + no scan
    import sit_eval.grader.verify as verify

    saved = verify.INJECTION_PATTERNS[:]
    verify.INJECTION_PATTERNS.clear()
    try:
        res = mv.run_meta_validation(graded_inputs[0], graded_inputs[1], tmp_path / "mv", judge=FakeJudge(lenient),
                                     runs=1, samples=2)
    finally:
        verify.INJECTION_PATTERNS.extend(saved)
    by = {o["check"]: o for o in res["outcomes"]}
    assert by["V1"]["passed"] is False and by["V4"]["passed"] is False and by["V10"]["passed"] is False


def test_grader_meta_validation_budget_stop(tmp_path: Path, graded_inputs, heuristic_judge) -> None:
    res = mv.run_meta_validation(graded_inputs[0], graded_inputs[1], tmp_path / "mv", judge=heuristic_judge,
                                 runs=1, max_cost_usd=0.0001)
    assert res["status"] == "aborted_budget" and heuristic_judge.calls == []
    assert all(o["passed"] is None for o in res["outcomes"])


def test_grader_meta_validation_plan() -> None:
    assert mv.plan_meta_validation(21, runs=5, samples=2) == {"grades": 20, "calls_min": 80, "calls_max": 100}
