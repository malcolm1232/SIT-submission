"""Verifier of the matcher candidate rule (2026-10-02) and the owner-approved follow-ups.

Part 1 regressions: under ``shortlist_bounded`` no pair outside the shortlist is ever scored, whatever path
could reach it (shortlist answers past K or repeated ids, the deterministic DUPLICATE and PARTIAL_KEY_MATCH
labels, still-valid observations, adaptive samples, resume from a cache written by a ``union`` run).
Part 2: the PARTIAL_KEY_MATCH class (docs/USER_DECISIONS.md #14) and the adaptive third sample default (#15).
"""

from __future__ import annotations

from eval_builders import (
    adj,
    default_table,
    make_finding,
    make_flaw,
    make_key,
    make_review,
    make_sound,
    pair,
    responder_from,
    run_pipeline,
)

from sit_eval.report_md import render_scores_md
from sit_eval.scoring import validate_scores


def _key():
    return make_key([make_flaw("F01", "critical", "1"), make_flaw("F02", "high", "2")])


def _findings():
    # FND-001..004 cite section 1 (overlap F01); FND-005 cites section 9 (no overlap); FND-006 cites 2 (F02)
    return [make_finding(1, "1"), make_finding(2, "1"), make_finding(3, "1"), make_finding(4, "1"),
            make_finding(5, "9"), make_finding(6, "2")]


def _pair_purposes(calls) -> set[tuple[str, str]]:
    return {tuple(c.purpose.split(":")[1:]) for c in calls if c.purpose.startswith("match.pair")}


def _shortlist(table, answers):
    table["match.shortlist"] = lambda r: {"candidate_ids": answers.get(r.purpose.split(":")[1], []),
                                          "rationale": "x"}


# ----------------------------------------------------------------------------- Part 1: the bound holds


def test_shortlist_answers_past_k_or_repeated_are_never_scored(tmp_path):
    table = default_table()
    # five distinct known ids plus a repeat and an unknown id; shortlist_k = 3
    _shortlist(table, {"F01": ["FND-005", "FND-005", "FND-999", "FND-002", "FND-006", "FND-001", "FND-003"]})
    table["match.pair"] = lambda r: pair(3)
    scores, fake, _ = run_pipeline(tmp_path, make_review(_findings()), _key(), responder_from(table))
    sl = scores["matching"]["shortlist"]["F01"]
    assert sl["ids"] == ["FND-005", "FND-002", "FND-006"]
    assert sl["ids_beyond_k"] == ["FND-001", "FND-003"] and sl["unknown_ids"] == ["FND-999"]
    assert _pair_purposes(fake.calls) == {("F01", "FND-005"), ("F01", "FND-002"), ("F01", "FND-006")}
    assert scores["matching"]["candidates"]["F01"] == {"FND-002": ["overlap", "shortlist"],
                                                       "FND-005": ["shortlist"], "FND-006": ["shortlist"]}
    w = [x for x in scores["warnings"] if x.startswith("shortlist answers outside the rule")]
    assert len(w) == 1 and "FND-999" in w[0] and "['FND-001', 'FND-003']" in w[0]
    assert validate_scores(scores) == []


def test_deterministic_labels_and_observations_never_reach_an_unshortlisted_pair(tmp_path):
    # FND-001 is shortlisted for F01 and MATCHes. FND-002 overlaps F01 and would score 3 (a deterministic
    # DUPLICATE) if it were scored; FND-006 overlaps F02 and would score 2 (a deterministic PARTIAL_KEY_MATCH).
    # Neither is shortlisted, so both go to the LLM adjudicator; FND-002 then matches a still-valid observation.
    findings = [make_finding(1, "1"), make_finding(2, "1"), make_finding(6, "2")]
    key = _key()
    key["still_valid_observations"] = [{"id": "O01", "text": "x", "origin": "eval_audit", "related_flaw_ids": []}]
    table = default_table()
    _shortlist(table, {"F01": ["FND-001"], "F02": []})
    table["match.pair"] = lambda r: pair(3 if r.purpose.endswith("FND-001") or r.purpose.endswith("FND-002") else 2)
    table["adjudicate"] = lambda r: adj("NON_SPECIFIC", obs="O01" if r.purpose.endswith("FND-002") else None)
    scores, fake, _ = run_pipeline(tmp_path, make_review(findings), key, responder_from(table))
    assert _pair_purposes(fake.calls) == {("F01", "FND-001")}
    st = {r["finding_id"]: r for r in scores["adjudication"]["strict"]}
    assert st["FND-002"]["class"] == "VALID_UNPLANTED" and st["FND-002"]["basis"] == "still_valid_observation"
    assert st["FND-006"]["class"] == "NON_SPECIFIC" and st["FND-006"]["basis"] == "llm"
    assert st["FND-006"]["partial_key_flaw_id"] is None
    assert {c.purpose for c in fake.calls if c.purpose.startswith("adjudicate")} == {"adjudicate:FND-002",
                                                                                     "adjudicate:FND-006"}
    assert scores["matching"]["shortlist"]["F02"]["overlap_not_shortlisted"] == ["FND-006"]


def test_adaptive_samples_under_the_bounded_rule(tmp_path):
    table = default_table()
    _shortlist(table, {"F01": ["FND-005", "FND-001"]})
    table["match.pair"] = lambda r: pair(3 if r.purpose.endswith("FND-001") else [1, 2, 2][r.sample_index])
    scores, fake, _ = run_pipeline(tmp_path, make_review(_findings()), _key(), responder_from(table),
                                   adaptive_samples=True)
    rows = {r["finding_id"]: r for r in scores["matching"]["pair_scores"]}
    assert set(rows) == {"FND-001", "FND-005"}
    assert rows["FND-001"]["samples"] == [3, 3, None] and rows["FND-001"]["skipped_samples"] == 1
    assert rows["FND-005"]["samples"] == [1, 2, 2] and rows["FND-005"]["median"] == 2
    assert sum(c.purpose.startswith("match.pair") for c in fake.calls) == 5
    assert _pair_purposes(fake.calls) == {("F01", "FND-001"), ("F01", "FND-005")}


def test_resume_from_a_union_cache_scores_no_unshortlisted_pair(tmp_path):
    out = tmp_path / "out"
    review = make_review(_findings())
    table = default_table()
    _shortlist(table, {"F01": ["FND-005", "FND-002"], "F02": []})
    table["match.pair"] = lambda r: pair(3)
    union, _, _ = run_pipeline(tmp_path, review, _key(), responder_from(table), candidate_rule="union", out_dir=out)
    assert len(union["matching"]["pair_scores"]) == 6          # FND-001..004, FND-005 for F01; FND-006 for F02
    bounded, fake, runner = run_pipeline(tmp_path, review, _key(), responder_from(table), out_dir=out)
    # every matcher answer the bounded run needs is in the cache (same shortlist prompt under both rules); the
    # only live calls adjudicate the overlap-only findings the union run had matched or labelled DUPLICATE
    assert not [c for c in fake.calls if c.purpose.startswith("match.")]
    assert {c.purpose for c in fake.calls} == {"adjudicate:FND-001", "adjudicate:FND-003", "adjudicate:FND-004",
                                               "adjudicate:FND-006"}
    # ... and the cached union answers for the other overlap pairs are never read
    assert {(r.purpose.split(":")[1], r.purpose.split(":")[2]) for r in runner.records
            if r.purpose.startswith("match.pair")} == {("F01", "FND-005"), ("F01", "FND-002")}
    assert {(r["flaw_id"], r["finding_id"]) for r in bounded["matching"]["pair_scores"]} == {
        ("F01", "FND-005"), ("F01", "FND-002")}
    assert bounded["matching"]["candidates"]["F02"] == {}


# ----------------------------------------------------------------------------- Part 2: PARTIAL_KEY_MATCH


def test_partial_key_match_is_its_own_class_and_counts_as_correct(tmp_path):
    # F01 matched by FND-001. FND-002 scores 2 on F02 (nobody matches F02) -> PARTIAL_KEY_MATCH, located in
    # sound unit S01. FND-003 is VALID_UNPLANTED in sound unit S02. FND-004 scores 2 on taken F01 and 2 on free
    # F02 -> DUPLICATE (the duplicate rule comes first).
    key = make_key([make_flaw("F01", "critical", "1"), make_flaw("F02", "high", "2")],
                   sound=[make_sound("S01", "5"), make_sound("S02", "9")])
    findings = [make_finding(1, "1", confidence=0.9), make_finding(2, "5", confidence=0.8, category="other"),
                make_finding(3, "9", confidence=0.7), make_finding(4, "1", confidence=0.6)]
    table = default_table()
    _shortlist(table, {"F01": ["FND-001", "FND-004"], "F02": ["FND-002", "FND-004"]})
    s = {("F01", "FND-001"): 3, ("F02", "FND-002"): 2, ("F01", "FND-004"): 2, ("F02", "FND-004"): 2}
    table["match.pair"] = lambda r: pair(s.get(tuple(r.purpose.split(":")[1:]), 0))
    table["adjudicate"] = lambda r: adj({"adjudicate:FND-003": "VALID_UNPLANTED"}[r.purpose])
    scores, fake, _ = run_pipeline(tmp_path, make_review(findings), key, responder_from(table))
    st = {r["finding_id"]: r for r in scores["adjudication"]["strict"]}
    assert st["FND-002"]["class"] == "PARTIAL_KEY_MATCH" and st["FND-002"]["partial_key_flaw_id"] == "F02"
    assert st["FND-004"]["class"] == "DUPLICATE" and st["FND-004"]["duplicate_of"] == "FND-001"
    assert {c.purpose for c in fake.calls if c.purpose.startswith("adjudicate")} == {"adjudicate:FND-003"}
    m = scores["metrics"]
    # P_a = (TP 1 + V 1 + PARTIAL_KEY_MATCH 1) / 4; strict P_s and recall are unchanged by the label
    assert m["precision_adjudicated"]["value"] == 0.75 and m["precision_adjudicated"]["partial_key_match"] == 1
    assert m["precision_strict"]["value"] == 0.25 and m["recall"]["value"] == 0.5
    assert m["partial_key_match_count"]["value"] == 1 and m["partial_key_match_count"]["not_gold"] == []
    # a PARTIAL_KEY_MATCH is no false positive on its sound unit and does not remove it; VALID_UNPLANTED does
    cdr = m["cdr"]
    assert cdr["declined"] == {"S01": True} and cdr["units_removed"] == [{"unit": "S02", "because": "FND-003"}]
    # correct for precision in the per-category table and the calibration labels too
    assert m["per_category"]["value"]["other"]["precision"] == 1.0
    labels = {r["finding_id"]: r["label"] for r in m["calibration_inputs"]["value"]}
    assert labels == {"FND-001": 1, "FND-002": 1, "FND-003": 1}
    assert "G+" in m["pooled_recall"]["reason"] and "PARTIAL_KEY_MATCH" in m["pooled_recall"]["reason"]
    row = next(f for f in scores["findings"] if f["finding_id"] == "FND-002")
    assert row["class_strict"] == "PARTIAL_KEY_MATCH" and row["partial_key_flaw_strict"] == "F02"
    assert "| PARTIAL_KEY_MATCH (F02) |" in render_scores_md(scores)
    assert "| partial_key_match_count | 1 |" in render_scores_md(scores)
    assert validate_scores(scores) == []
    bad = {**scores, "adjudication": {**scores["adjudication"], "strict": [
        {**r, "partial_key_flaw_id": None} if r["class"] == "PARTIAL_KEY_MATCH" else r
        for r in scores["adjudication"]["strict"]]}}
    assert any("partial_key_flaw_id" in e for e in validate_scores(bad))


def test_partial_key_match_against_a_fixed_v2_flaw_is_not_credited(tmp_path):
    key = make_key([make_flaw("F01", "high", "1", v2_status="unchanged"),
                    make_flaw("F02", "high", "2", v2_status="fixed")], v2=True)
    findings = [make_finding(1, "1"), make_finding(2, "2")]
    table = default_table()
    _shortlist(table, {"F01": ["FND-001"], "F02": ["FND-002"]})
    table["match.pair"] = lambda r: pair({"match.pair:F01:FND-001": 3, "match.pair:F02:FND-002": 2}.get(r.purpose, 0))
    scores, _, _ = run_pipeline(tmp_path, make_review(findings, mode="delta"), key, responder_from(table),
                                version="v2")
    m = scores["metrics"]
    st = {r["finding_id"]: r for r in scores["adjudication"]["strict"]}
    assert st["FND-002"]["class"] == "PARTIAL_KEY_MATCH"
    # F02 is fixed in v2, so it is not gold: the label stays, the credit does not
    assert m["partial_key_match_count"]["value"] == 0 and m["partial_key_match_count"]["not_gold"] == ["FND-002"]
    assert m["precision_adjudicated"]["value"] == 0.5
    assert {r["finding_id"]: r["label"] for r in m["calibration_inputs"]["value"]} == {"FND-001": 1, "FND-002": 0}


def test_partial_key_match_tie_goes_to_the_more_severe_flaw(tmp_path):
    key = make_key([make_flaw("F01", "low", "1"), make_flaw("F02", "critical", "2"), make_flaw("F03", "low", "3")])
    findings = [make_finding(1, "1")]
    table = default_table()
    _shortlist(table, {"F01": ["FND-001"], "F02": ["FND-001"], "F03": ["FND-001"]})
    table["match.pair"] = lambda r: pair(2)
    scores, _, _ = run_pipeline(tmp_path, make_review(findings), key, responder_from(table))
    st = {r["finding_id"]: r for r in scores["adjudication"]["strict"]}
    assert st["FND-001"]["class"] == "PARTIAL_KEY_MATCH" and st["FND-001"]["partial_key_flaw_id"] == "F02"
    key["flaws"][1]["severity"] = "low"          # all equal: the earlier flaw in the key
    scores, _, _ = run_pipeline(tmp_path, make_review(findings), key, responder_from(table))
    assert scores["adjudication"]["strict"][0]["partial_key_flaw_id"] == "F01"


def test_dry_run_lower_bound_uses_free_batch_slots():
    from eval_builders import options

    from sit_eval.loaders import ReviewInput
    from sit_eval.scoring import plan_calls

    # union, per_flaw_batch, adaptive: F01 overlaps FND-001 (so its batch is always asked) and has two free
    # shortlist slots; FND-002 and FND-003 overlap nothing and ride in F01's batch at no extra call
    key = make_key([make_flaw("F01", "high", "1"), make_flaw("F02", "high", "2")])
    review = make_review([make_finding(1, "1"), make_finding(2, "9"), make_finding(3, "8")])
    rin = ReviewInput(data=review, review=None, report_path=None, run_dir=None, manifest=None)  # type: ignore[arg-type]
    usd, secs = {"low": 0.03, "typical": 0.11, "high": 0.33}, {"low": 5.0, "high": 20.0}
    p = plan_calls(rin, key, "v1", options(candidate_rule="union", granularity="per_flaw_batch", adaptive_samples=True,
                                           grounding_judges=False), usd, secs)
    # 2 shortlist + 1 flaw x 2 batch samples + 0 adjudications
    assert p["calls"]["adjudication"]["min"] == 0 and p["calls"]["total"]["min"] == 4


def test_adaptive_third_sample_is_the_config_default():
    from sit_eval.config import MatcherCfg, load_eval_config

    assert load_eval_config().matcher.adaptive_third_sample is True
    assert MatcherCfg().adaptive_third_sample is True


def test_shortlist_k_zero_is_flagged_not_silent(tmp_path):
    scores, fake, _ = run_pipeline(tmp_path, make_review(_findings()), _key(), responder_from(default_table()),
                                   shortlist_k=0)
    assert not [c for c in fake.calls if c.purpose.startswith("match.")]
    assert scores["metrics"]["recall"]["value"] == 0
    assert any(w.startswith("shortlist_k = 0 under shortlist_bounded") for w in scores["warnings"])
