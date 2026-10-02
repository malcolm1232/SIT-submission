"""Matcher behaviour: candidates, blinding, seeds, median, caps, batching, adjudication rules."""

from __future__ import annotations

import re

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

from sit_eval.locations import Loc, anchors_location, key_location, section_id
from sit_eval.matcher import credit_rule, render_flaw


def test_section_ids_and_overlap():
    assert section_id("3 (P2)") == "3" and section_id("5 (Figure 1 caption)") == "5"
    assert section_id("14 Ledger and Double-Entry Accounting") == "14" and section_id("Title page") is None
    assert section_id("§12.4") == "12.4" and section_id("25 (item 2)") == "25"
    k = key_location({"sections": ["3 (P2)", "12.1"], "requirement_ids": ["NFR-5"], "decision_ids": ["D-3"]})
    assert k.sections == {"3", "12.1"} and k.ids == {"P2", "NFR-5", "D-3"}
    assert anchors_location([{"section_ref": "12", "requirement_ids": []}]).overlaps(k)        # parent section
    assert anchors_location([{"section_ref": "9.2", "requirement_ids": ["NFR-5"]}]).overlaps(k)  # shared id
    assert not anchors_location([{"section_ref": "12.10", "requirement_ids": []}]).overlaps(k)
    assert not Loc().overlaps(k)


def _two_flaw_key():
    return make_key([make_flaw("F01", "critical", "1"), make_flaw("F02", "high", "2")])


def test_candidates_blinding_and_seeds(tmp_path):
    findings = [make_finding(1, "1"), make_finding(2, "2"), make_finding(3, "9"), make_finding(4, "8")]
    table = default_table()
    table["match.shortlist"] = lambda r: {"candidate_ids": ["FND-003", "FND-999"], "rationale": "x"}
    scores, fake, _ = run_pipeline(tmp_path, make_review(findings), _two_flaw_key(), responder_from(table))
    cands = scores["matching"]["candidates"]
    assert cands["F01"] == {"FND-001": ["overlap"], "FND-003": ["shortlist"]}
    assert cands["F02"] == {"FND-002": ["overlap"], "FND-003": ["shortlist"]}
    assert scores["matching"]["shortlist"]["F01"]["unknown_ids"] == ["FND-999"]
    # blinding: nothing that identifies the run, model or condition reaches any prompt
    for c in fake.calls:
        text = (c.system + c.user).lower()
        for leak in ("secret-run-opus", "rev-secret", "full-secret-condition", "claude", "opus", "prompt_hash",
                     "provenance", '"confidence"', '"severity"', '"category"', "0.8"):
            assert leak not in text, (c.purpose, leak)
    # shuffles are seeded, recorded and reproducible
    seeds = {g: v["seed"] for g, v in scores["matching"]["shortlist"].items()}
    assert all(isinstance(s, int) for s in seeds.values()) and seeds["F01"] != seeds["F02"]
    again, fake2, _ = run_pipeline(tmp_path, make_review(findings), _two_flaw_key(), responder_from(table))
    assert [c.user for c in fake.calls if c.purpose.startswith("match.shortlist")] == \
        [c.user for c in fake2.calls if c.purpose.startswith("match.shortlist")]
    other, fake3, _ = run_pipeline(tmp_path, make_review(findings), _two_flaw_key(), responder_from(table), seed=99)
    orders = [re.findall(r'"finding_id": "([^"]+)"', c.user) for c in fake.calls + fake3.calls
              if c.purpose == "match.shortlist:F01"]
    assert sorted(orders[0]) == sorted(orders[1])


def test_three_samples_median_and_location_cap(tmp_path):
    findings = [make_finding(1, "1"), make_finding(2, "2")]
    table = default_table()
    samples = {("F01", "FND-001"): [3, 2, 3], ("F02", "FND-002"): [3, 3, 3]}

    def score(r):
        _, g, f = r.purpose.split(":")
        s = samples.get((g, f), [0, 0, 0])[r.sample_index]
        return pair(s, location_ok=(g, f) != ("F02", "FND-002") or r.sample_index != 0)

    table["match.pair"] = score
    scores, fake, _ = run_pipeline(tmp_path, make_review(findings), _two_flaw_key(), responder_from(table))
    rows = {(p["flaw_id"], p["finding_id"]): p for p in scores["matching"]["pair_scores"]}
    assert rows[("F01", "FND-001")]["samples"] == [3, 2, 3] and rows[("F01", "FND-001")]["median"] == 3
    assert rows[("F02", "FND-002")]["samples"] == [2, 3, 3] and rows[("F02", "FND-002")]["capped_samples"] == 1
    assert sum(c.purpose.startswith("match.pair") for c in fake.calls) == 2 * 3
    assert {c.sample_index for c in fake.calls if c.purpose == "match.pair:F01:FND-001"} == {0, 1, 2}


def test_failed_sample_uses_lower_median(tmp_path):
    findings = [make_finding(1, "1")]
    table = default_table()

    def score(r):
        if r.sample_index == 1:
            raise RuntimeError("boom")
        return pair(3 if r.sample_index == 0 else 2)

    table["match.pair"] = score
    from sit_eval.judge import JudgeError

    def guarded(r):
        try:
            return responder_from(table)(r)
        except RuntimeError as exc:
            raise JudgeError(str(exc)) from None

    scores, _, _ = run_pipeline(tmp_path, make_review(findings), make_key([make_flaw("F01", "critical", "1")]),
                                guarded)
    p = scores["matching"]["pair_scores"][0]
    assert p["samples"] == [3, None, 2] and p["median"] == 2
    assert scores["metrics"]["recall"]["value"] == 0 and scores["metrics"]["lenient_recall"]["value"] == 1
    assert any("sample 1" in f for f in scores["failures"])


def test_per_flaw_batch_mode(tmp_path):
    findings = [make_finding(1, "1"), make_finding(2, "1"), make_finding(3, "2")]
    table = default_table()
    table["match.batch"] = lambda r: {"scores": [
        {"finding_id": f, **pair(3 if f == "FND-002" else 1)} for f in re.findall(r'"finding_id": "([^"]+)"', r.user)]}
    scores, fake, _ = run_pipeline(tmp_path, make_review(findings), _two_flaw_key(), responder_from(table),
                                   granularity="per_flaw_batch")
    batch_calls = [c for c in fake.calls if c.purpose.startswith("match.batch")]
    assert len(batch_calls) == 2 * 3 and not any(c.purpose.startswith("match.pair") for c in fake.calls)
    assert scores["matching"]["strict"] == [{"finding_id": "FND-002", "flaw_id": "F01", "score": 3.0}]
    assert any("DEVIATION" in w for w in scores["warnings"])
    assert len(scores["matching"]["shortlist"]["F01"]["batch_seeds"]) == 3


def test_adjudication_rules(tmp_path):
    # FND-001 matches F01; FND-002 also scores 3 on F01 -> deterministic DUPLICATE;
    # FND-003 scores 2 on F02 (nobody matches F02 strictly) -> LLM adjudicated like any unmatched
    # finding (verifier E1: no deterministic VALID_UNPLANTED), with partial_key_flaw_id = F02;
    # FND-004 -> LLM says it matches observation O01 -> VALID_UNPLANTED via the observation.
    findings = [make_finding(1, "1"), make_finding(2, "1"), make_finding(3, "2"), make_finding(4, "9")]
    key = _two_flaw_key()
    key["still_valid_observations"] = [{"id": "O01", "text": "webhook retention", "origin": "eval_audit",
                                        "related_flaw_ids": []}]
    table = default_table()
    s = {("F01", "FND-001"): 3, ("F01", "FND-002"): 3, ("F02", "FND-003"): 2}
    table["match.pair"] = lambda r: pair(s.get(tuple(r.purpose.split(":")[1:]), 0))
    table["adjudicate"] = lambda r: adj("NON_SPECIFIC", obs="O01" if r.purpose.endswith("FND-004") else None)
    scores, fake, _ = run_pipeline(tmp_path, make_review(findings), key, responder_from(table))
    st = {r["finding_id"]: r for r in scores["adjudication"]["strict"]}
    assert st["FND-002"]["class"] == "DUPLICATE" and st["FND-002"]["basis"] == "deterministic_duplicate"
    assert st["FND-003"]["class"] == "NON_SPECIFIC" and st["FND-003"]["basis"] == "llm"
    assert st["FND-003"]["partial_key_flaw_id"] == "F02"
    assert st["FND-004"]["class"] == "VALID_UNPLANTED" and st["FND-004"]["observation_id"] == "O01"
    assert st["FND-004"]["partial_key_flaw_id"] is None
    le = {r["finding_id"]: r for r in scores["adjudication"]["lenient"]}
    assert "FND-003" not in le                                   # matched to F02 under lenient matching
    assert {c.purpose for c in fake.calls if c.purpose.startswith("adjudicate")} == {"adjudicate:FND-003",
                                                                                     "adjudicate:FND-004"}
    adj_call = next(c for c in fake.calls if c.purpose == "adjudicate:FND-004")
    assert "- O01: webhook retention" in adj_call.user
    assert scores["human_review_queue"]["all_valid_unplanted_and_hallucinated"] == ["FND-004"]
    m = scores["metrics"]
    # strict P_a counts VALID_UNPLANTED only: (TP 1 + V 1) / 4; the partial finding is not credited
    assert m["precision_adjudicated"]["value"] == 0.5 and m["precision_adjudicated"]["v"] == 1
    assert m["precision_adjudicated_partial_credit"]["value"] == 0.75
    assert m["precision_adjudicated_partial_credit"]["status"] == "exploratory"


def test_credit_rules_and_pending_core_insight():
    assert credit_rule(make_flaw("F01", "high", "1", mode="all_of")).startswith("all_of: MATCH requires every")
    assert "at least 1 of" in credit_rule(make_flaw("F01", "high", "1", mode="any_of"))
    text = render_flaw(make_flaw("F01", "high", "1"))
    assert "not yet written in the key" in text and "c3 (supporting)" in text
    g = make_flaw("F01", "high", "1")
    g["core_insight"] = "The cache key omits the merchant."
    assert "core insight: The cache key omits the merchant." in render_flaw(g)
