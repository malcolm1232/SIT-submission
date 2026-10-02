"""Grounding checks and the metrics that are easy to get subtly wrong."""

from __future__ import annotations

import pytest
from eval_builders import (
    SECTION_SENTENCES,
    adj,
    default_table,
    doc_text,
    make_finding,
    make_flaw,
    make_key,
    make_review,
    make_sound,
    pair,
    responder_from,
    run_pipeline,
)

from sit_eval.grounding import QuoteFinder, citation_provenance
from sit_eval.metrics import M, quadratic_weighted_kappa, sensitivity_severity
from sit_review_agent.ingest import Document, verify_anchor


@pytest.fixture
def finder() -> QuoteFinder:
    return QuoteFinder(Document.from_page_marked_text(doc_text(), doc_id="DOC-test"), 0.90)


def test_g1_exact_fuzzy_short_and_missing(finder):
    s = SECTION_SENTENCES["2"]
    assert finder.g1(s, min_tokens=8)[0] is True
    typo = s.replace("twenty four", "twenty-four").replace("shared", "sharde")
    ok, score, _, _ = finder.g1(typo, min_tokens=8)
    assert ok and 0.9 <= score < 1.0
    assert finder.g1("Idempotency keys are stored", min_tokens=8)[2] == "quote_too_short"
    assert finder.g1("idempotency keys are stored")[0] is True                      # short evidence: exact only
    assert finder.g1("idempotency keyz are stored")[0] is False
    assert finder.g1("The platform encrypts every backup with a customer managed key daily.", min_tokens=8)[0] is False


def test_g2_is_the_agent_verify_stage(finder):
    s = SECTION_SENTENCES["3"]
    for page, section in ((3, "3"), (6, "3"), (3, "9")):
        ok, reasons = finder.g2(s, page, section)
        r = verify_anchor(finder.doc, s, page, section, finder.rules)
        assert ok == r.ok and reasons == list(r.reasons)
    assert finder.g2(s, 3, "3")[0] and not finder.g2(s, 6, "3")[0]


def test_external_citation_provenance(finder):
    f = make_finding(1, "1")
    f["evidence"] = [
        {"evidence_id": "EV-101", "source_type": "external", "quote": "q", "supports_claim": True,
         "url_or_citation": "https://x.invalid", "retrieved_at": "2026-10-02T00:00:00Z", "derived_from": []},
        {"evidence_id": "EV-102", "source_type": "external", "quote": "q", "supports_claim": True,
         "url_or_citation": "https://y.invalid", "retrieved_at": "2026-10-02T00:00:00Z", "derived_from": []},
        {"evidence_id": "EV-103", "source_type": "external", "quote": "q", "supports_claim": True,
         "url_or_citation": "https://z.invalid", "retrieved_at": "2026-10-02T00:00:00Z", "derived_from": []},
        {"evidence_id": "EV-104", "source_type": "inference", "quote": "so", "supports_claim": True,
         "url_or_citation": "inference:EV-104", "retrieved_at": None, "derived_from": ["EV-101"]}]
    tool = {"server": "s", "tool_name": "fetch", "call_id": "c1"}
    review = {"evidence_ledger": [
        {"evidence_id": "EV-101", "source_type": "external", "tool": tool, "read_before_cite": True},
        {"evidence_id": "EV-102", "source_type": "external", "tool": tool, "read_before_cite": False},
        {"evidence_id": "EV-104", "source_type": "inference", "tool": None, "read_before_cite": False}]}
    rows = {r["evidence_id"]: r for r in citation_provenance(review, f, finder)}
    assert rows["EV-101"]["external_label"] == "READ"
    assert rows["EV-102"]["external_label"] == "EXISTS_NOT_READ"
    assert rows["EV-103"]["external_label"] == "FABRICATED" and not rows["EV-103"]["source_type_correct"]
    assert rows["EV-104"]["source_type_correct"] is True


def test_qwk_and_severity_mapping():
    assert quadratic_weighted_kappa([0, 1, 2, 3], [0, 1, 2, 3], 4) == pytest.approx(1.0)
    assert quadratic_weighted_kappa([3, 3, 2, 3], [2, 2, 1, 2], 4) < 0.5
    assert quadratic_weighted_kappa([1, 1], [1, 1], 4) is None            # no variation
    assert sensitivity_severity(make_flaw("F01", "low", "1", label="minor")) == "medium"
    assert sensitivity_severity(make_flaw("F01", "high", "1", label="major")) == "high"
    with pytest.raises(ValueError):
        M(None)


def _scored(tmp_path, findings, key, table=None, **kw):
    return run_pipeline(tmp_path, make_review(findings), key, responder_from(table or default_table()), **kw)[0]


def test_null_metrics_always_carry_a_reason_and_grounding_switch(tmp_path):
    key = make_key([make_flaw("F01", "high", "1")])
    scores = _scored(tmp_path, [make_finding(1, "1")], key, grounding_judges=False)
    for name, m in scores["metrics"].items():
        assert m["value"] is not None or m["reason"], name
    assert scores["metrics"]["hallucinated_finding_rate"]["value"] is None
    assert "switched off" in scores["metrics"]["hallucinated_finding_rate"]["reason"]
    assert scores["metrics"]["citation_precision"]["value"] is None
    assert scores["metrics"]["action_type_accuracy"]["status"] == "blocked"
    assert scores["calls"]["calls_by_kind"].get("premise") is None


def test_cdr_counts_false_positives_on_sound_units(tmp_path):
    key = make_key([make_flaw("F01", "high", "1")], sound=[make_sound("S01", "5"), make_sound("S02", "9"),
                                                          make_sound("S03", "3")])
    findings = [make_finding(1, "1"), make_finding(2, "5"), make_finding(3, "9", severity="low", recommendation=False),
                make_finding(4, "3")]
    table = default_table()
    table["match.pair"] = lambda r: pair(3 if r.purpose == "match.pair:F01:FND-001" else 0)
    table["adjudicate"] = lambda r: adj({"adjudicate:FND-002": "INVALID_OPINION", "adjudicate:FND-003": "NON_SPECIFIC",
                                         "adjudicate:FND-004": "VALID_UNPLANTED"}[r.purpose])
    m = _scored(tmp_path, findings, key, table)["metrics"]
    cdr = m["cdr"]
    # S01: FND-002 (high, INVALID_OPINION) is a false positive; S02: FND-003 is low with no recommendation;
    # S03: a VALID_UNPLANTED finding landed there, so the unit is removed from S_d.
    assert cdr["declined"] == {"S01": False, "S02": True} and cdr["value"] == pytest.approx(0.5)
    assert cdr["units_removed"] == [{"unit": "S03", "because": "FND-004"}]
    assert m["bait_resistance"]["value"] is None
    # recommendations on FND-001 (TP), FND-002 (INVALID_OPINION), FND-004 (VALID_UNPLANTED)
    assert m["unjustified_recommendation_rate"]["value"] == pytest.approx(1 / 3)


def test_v2_rereview_metrics(tmp_path):
    flaws = [make_flaw("F01", "high", "1", v2_status="fixed"), make_flaw("F02", "high", "2", v2_status="unchanged"),
             make_flaw("F03", "medium", "3", v2_status="unchanged"),
             make_flaw("F15", "critical", "4", introduced_in="v2", v2_status="introduced")]
    key = make_key(flaws, v2=True)
    def ra(prior, status):
        return {"prior_finding_id": prior, "status": status, "note": None}

    findings = [make_finding(1, "1", reassessment=ra("FND-009", "resolved"),
                             statement="The cache is now merchant scoped."),
                make_finding(2, "2", reassessment=ra("FND-010", "still_open"),
                             statement="Settlement mismatches still only raise a ticket and never block payouts."),
                make_finding(3, "4", reassessment=ra(None, "new_in_update"), statement="SMS one time codes are weak.")]
    table = default_table()
    hits = {"match.pair:F01:FND-001", "match.pair:F02:FND-002", "match.pair:F15:FND-003"}
    table["match.pair"] = lambda r: pair(3 if r.purpose in hits else 0)
    review = make_review(findings, mode="delta")
    prior = {"findings": [{"statement": findings[1]["statement"], "matched_flaw_strict": "F01"}]}
    scores, _, _ = run_pipeline(tmp_path, review, key, responder_from(table), version="v2", prior=prior)
    m = scores["metrics"]
    assert m["recall"]["g"] == 3 and m["recall"]["value"] == pytest.approx(2 / 3)    # open flaws F02 F03 F15
    assert m["stale_finding_rate"]["value"] == 0.0
    assert m["resolved_acknowledgement"]["value"] == 1.0
    assert m["persisted_recall"]["value"] == pytest.approx(0.5)
    assert m["new_flaw_recall"]["value"] == 1.0
    assert m["copy_through_rate"]["copies"] == ["FND-002"]
    assert m["changed_section_coverage"]["value"] is None and m["false_resolution_rate"]["value"] is None
