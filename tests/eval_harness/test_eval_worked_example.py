"""metrics.md §14 worked example, reproduced exactly (prereg leakage control LC9).

Key: F01 critical (8), F02 high (4), F03 medium (2), F04 low (1). Findings in rank order:
f1 MATCH F02; f2 unmatched -> VALID_UNPLANTED; f3 MATCH F01; f4 scores 3 with F02 but F02 is taken ->
DUPLICATE; f5 unmatched -> HALLUCINATED (false-absence claim).

metrics.md §14 does not depend on how candidates are generated; it needs the three MATCH pairs scored.
The fixture's shortlist returns exactly those pairs (F02: f1, f4; F01: f3), so the example runs under the
default ``shortlist_bounded`` rule; under ``union`` it runs with an empty shortlist (overlap supplies the
same pairs). The expected numbers are the same for both.
"""

from __future__ import annotations

import math

import pytest
from eval_builders import (
    adj,
    default_table,
    make_finding,
    make_flaw,
    make_key,
    make_review,
    pair,
    responder_from,
    run_pipeline,
)

from sit_eval.metrics import dcg, f1, ndcg

MATCHES = {("F02", "FND-001"), ("F01", "FND-003"), ("F02", "FND-004")}
SHORTLIST = {"F01": ["FND-003"], "F02": ["FND-001", "FND-004"]}


def _scenario(rule: str = "shortlist_bounded"):
    key = make_key([make_flaw("F01", "critical", "1"), make_flaw("F02", "high", "2"),
                    make_flaw("F03", "medium", "3"), make_flaw("F04", "low", "4")])
    findings = [make_finding(1, "2", confidence=0.9), make_finding(2, "9", confidence=0.8),
                make_finding(3, "1", confidence=0.7), make_finding(4, "2", confidence=0.6),
                make_finding(5, "8", confidence=0.5)]
    table = default_table()

    def pair_score(r):
        _, g, f = r.purpose.split(":")
        return pair(3 if (g, f) in MATCHES else 0)

    table["match.pair"] = pair_score
    table["match.shortlist"] = lambda r: {"candidate_ids": SHORTLIST.get(r.purpose.split(":")[1], [])
                                          if rule == "shortlist_bounded" else [], "rationale": "x"}
    table["adjudicate"] = lambda r: adj({"adjudicate:FND-002": "VALID_UNPLANTED",
                                         "adjudicate:FND-005": "HALLUCINATED"}[r.purpose])

    def premise(r):
        absent = r.purpose.endswith("FND-005")
        return {"is_absence_claim": absent, "premise": "p", "label": "CONTRADICTED" if absent else "SUPPORTED",
                "doc_passage": None, "rationale": "x"}

    table["ground.premise"] = premise
    return make_review(findings), key, responder_from(table)


@pytest.mark.parametrize(("rule", "adaptive"), [("shortlist_bounded", True), ("shortlist_bounded", False),
                                                ("union", False)])
def test_section_14_numbers(tmp_path, rule, adaptive):
    # shortlist_bounded with the adaptive third sample is the configured default (UD #10, #15)
    review, key, responder = _scenario(rule)
    scores, fake, _ = run_pipeline(tmp_path, review, key, responder, candidate_rule=rule, adaptive_samples=adaptive)
    assert scores["matching"]["candidate_rule"] == rule
    assert {(p["flaw_id"], p["finding_id"]) for p in scores["matching"]["pair_scores"]} == MATCHES
    m = {k: v["value"] for k, v in scores["metrics"].items()}
    assert scores["metrics"]["recall"]["tp"] == 2 and scores["metrics"]["precision_adjudicated"]["v"] == 1
    assert m["recall"] == pytest.approx(0.50)
    assert m["precision_strict"] == pytest.approx(0.40)
    assert m["precision_adjudicated"] == pytest.approx(0.60)
    assert round(m["f1_strict"], 3) == 0.444
    assert round(m["f1_adjudicated"], 3) == 0.545
    assert m["severity_weighted_recall"] == pytest.approx(0.80)
    assert m["critical_recall"] == pytest.approx(1.0)
    assert round(m["ndcg_at_G"], 3) == 0.669
    assert m["mrr_critical"] == pytest.approx(1 / 3)
    assert m["critical_in_top3"] == 1
    assert m["hallucinated_finding_rate"] == pytest.approx(0.20)
    assert m["duplication_rate"] == pytest.approx(0.20)
    cal = scores["metrics"]["calibration_inputs"]
    assert cal["n"] == 4
    assert [r["finding_id"] for r in cal["value"]] == ["FND-001", "FND-002", "FND-003", "FND-005"]
    assert [r["label"] for r in cal["value"]] == [1, 1, 1, 0]
    # who matched what, and why f4 is a duplicate (deterministic, no adjudicator call)
    assert {(r["finding_id"], r["flaw_id"]) for r in scores["matching"]["strict"]} == {("FND-001", "F02"),
                                                                                        ("FND-003", "F01")}
    rows = {r["finding_id"]: r for r in scores["adjudication"]["strict"]}
    assert rows["FND-004"]["class"] == "DUPLICATE" and rows["FND-004"]["basis"] == "deterministic_duplicate"
    assert rows["FND-004"]["duplicate_of"] == "FND-001"
    assert not any(c.purpose == "adjudicate:FND-004" for c in fake.calls)
    assert scores["metrics"]["false_absence_rate"]["value"] == pytest.approx(1.0)


def test_section_14_formulas_directly():
    gains = [4, 0, 8, 0]
    assert dcg(gains) == pytest.approx(8.0)
    idcg = 8 / 1 + 4 / math.log2(3) + 2 / 2 + 1 / math.log2(5)
    assert round(idcg, 3) == 11.954
    assert round(ndcg(gains, [8, 4, 2, 1], 4), 3) == 0.669
    assert round(f1(0.4, 0.5), 3) == 0.444 and round(f1(0.6, 0.5), 3) == 0.545
    assert f1(0.0, 0.0) == 0.0 and f1(None, 0.5) is None
