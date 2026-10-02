"""Matcher candidate rule (owner decision 2026-10-02, docs/USER_DECISIONS.md #10).

``shortlist_bounded`` (default, metrics.md §2.3 as amended): pairwise scoring runs only on the findings
the listwise shortlist returns; location overlap is a hint in the shortlist prompt and never adds a pair.
``union`` (comparison mode, a DEVIATION): location overlap union the shortlist, the earlier rule.
"""

from __future__ import annotations

import json
import re

import pytest
from eval_builders import (
    LIVE_RUN,
    PAYMENTS_KEY,
    default_table,
    make_finding,
    make_flaw,
    make_key,
    make_review,
    options,
    overlap_hint,
    pair,
    responder_from,
    run_pipeline,
)
from typer.testing import CliRunner

from sit_eval.cli import app
from sit_eval.judge import JudgeError
from sit_eval.loaders import load_key, load_review
from sit_eval.matcher import finding_views, flaw_views
from sit_eval.scoring import plan_calls, validate_scores

FID = re.compile(r'"finding_id": "([^"]+)"')


def _key():
    return make_key([make_flaw("F01", "critical", "1"), make_flaw("F02", "high", "2")])


def _findings():
    # FND-001..004 all cite section 1 (overlap F01: four overlapping findings, more than shortlist_k = 3);
    # FND-005 cites section 9 (no overlap with any flaw); FND-006 cites section 2 (overlaps F02)
    return [make_finding(1, "1"), make_finding(2, "1"), make_finding(3, "1"), make_finding(4, "1"),
            make_finding(5, "9"), make_finding(6, "2")]


def _pair_purposes(fake) -> set[tuple[str, str]]:
    return {tuple(c.purpose.split(":")[1:]) for c in fake.calls if c.purpose.startswith("match.pair")}


def test_bounded_rule_never_scores_a_non_shortlisted_finding_even_if_it_overlaps(tmp_path):
    table = default_table()
    shortlist = {"F01": ["FND-005", "FND-002"], "F02": []}
    table["match.shortlist"] = lambda r: {"candidate_ids": shortlist[r.purpose.split(":")[1]], "rationale": "x"}
    table["match.pair"] = lambda r: pair(3)            # any scored pair would MATCH
    scores, fake, _ = run_pipeline(tmp_path, make_review(_findings()), _key(), responder_from(table))
    m = scores["matching"]
    assert m["candidate_rule"] == "shortlist_bounded"
    # only the shortlisted findings are candidates; FND-002 also overlaps (provenance), FND-005 does not
    assert m["candidates"]["F01"] == {"FND-002": ["overlap", "shortlist"], "FND-005": ["shortlist"]}
    assert m["candidates"]["F02"] == {}               # FND-006 overlaps F02 but was not shortlisted
    assert _pair_purposes(fake) == {("F01", "FND-005"), ("F01", "FND-002")}
    assert sum(c.purpose.startswith("match.pair") for c in fake.calls) == 2 * 3
    sl = m["shortlist"]["F01"]
    assert sl["overlap_hint_ids"] == ["FND-001", "FND-002", "FND-003", "FND-004"]
    assert sl["shortlisted_with_overlap"] == ["FND-002"] and sl["shortlisted_without_overlap"] == ["FND-005"]
    assert sl["overlap_not_shortlisted"] == ["FND-001", "FND-003", "FND-004"]
    assert m["shortlist"]["F02"]["overlap_not_shortlisted"] == ["FND-006"]
    # the higher-ranked of the two shortlisted MATCHes takes F01; nothing matches F02
    assert m["strict"] == [{"finding_id": "FND-002", "flaw_id": "F01", "score": 3.0}]
    assert {r["finding_id"] for r in m["pair_scores"]} == {"FND-002", "FND-005"}
    assert not any("DEVIATION" in w and "candidate_rule" in w for w in scores["warnings"])
    assert validate_scores(scores) == []


def test_bounded_rule_in_per_flaw_batch_mode_sends_only_shortlisted_findings(tmp_path):
    table = default_table()
    table["match.shortlist"] = lambda r: {"candidate_ids": ["FND-003"] if r.purpose.endswith("F01") else [],
                                          "rationale": "x"}
    table["match.batch"] = lambda r: {"scores": [{"finding_id": f, **pair(3)} for f in FID.findall(r.user)]}
    scores, fake, _ = run_pipeline(tmp_path, make_review(_findings()), _key(), responder_from(table),
                                   granularity="per_flaw_batch")
    batch = [c for c in fake.calls if c.purpose.startswith("match.batch")]
    assert {c.purpose for c in batch} == {"match.batch:F01"} and len(batch) == 3
    assert all(FID.findall(c.user) == ["FND-003"] for c in batch)
    assert scores["matching"]["strict"] == [{"finding_id": "FND-003", "flaw_id": "F01", "score": 3.0}]


def test_overlap_hint_reaches_the_shortlist_prompt(tmp_path):
    flaws = [make_flaw("F01", "critical", "1"), make_flaw("F02", "high", "2"), make_flaw("F03", "low", "5")]
    flaws[1]["location"]["requirement_ids"] = ["FR-9"]
    findings = _findings()
    findings[4]["doc_anchors"][0]["requirement_ids"] = ["FR-9"]    # FND-005: no shared section, shared id
    scores, fake, _ = run_pipeline(tmp_path, make_review(findings), make_key(flaws), responder_from(default_table()))
    calls = {c.purpose: c.user for c in fake.calls if c.purpose.startswith("match.shortlist")}
    for g, want in (("F01", {"FND-001", "FND-002", "FND-003", "FND-004"}), ("F02", {"FND-005", "FND-006"}),
                    ("F03", set())):
        user = calls[f"match.shortlist:{g}"]
        assert "<location_hint>" in user
        hint = overlap_hint(user)
        assert set(hint) == want
        # the hint lists the overlapping findings in the same (shuffled) order as the findings block
        shown = FID.findall(user)
        assert hint == [f for f in shown if f in want] and sorted(shown) == [f"FND-00{i}" for i in range(1, 7)]
        assert scores["matching"]["shortlist"][g]["overlap_hint_ids"] == sorted(want)
    assert "overlapping the flaw's location: none" in calls["match.shortlist:F03"]
    # the hint carries ids only: no rank, severity or confidence of the findings
    assert "rank" not in calls["match.shortlist:F01"].split("<location_hint>")[1]


def _old_union(review, key, shortlist):
    """The pre-2026-10-02 candidate rule, written out independently of the matcher."""
    findings, flaws = finding_views(review), flaw_views(key, "v1")
    out = {}
    for g in flaws:
        c: dict[str, list[str]] = {}
        for f in findings:
            if f.loc.overlaps(g.loc):
                c.setdefault(f.id, []).append("overlap")
        for fid in shortlist.get(g.id, []):
            c.setdefault(fid, []).append("shortlist")
        out[g.id] = c
    return out


def test_union_reproduces_the_old_candidate_set(tmp_path):
    review = make_review(_findings())
    shortlist = {"F01": ["FND-005", "FND-002"], "F02": ["FND-001"]}
    table = default_table()
    table["match.shortlist"] = lambda r: {"candidate_ids": shortlist[r.purpose.split(":")[1]], "rationale": "x"}
    scores, fake, _ = run_pipeline(tmp_path, review, _key(), responder_from(table), candidate_rule="union")
    want = _old_union(review, _key(), shortlist)
    assert scores["matching"]["candidates"] == want
    assert want["F01"] == {"FND-001": ["overlap"], "FND-002": ["overlap", "shortlist"], "FND-003": ["overlap"],
                           "FND-004": ["overlap"], "FND-005": ["shortlist"]}
    assert _pair_purposes(fake) == {(g, f) for g, c in want.items() for f in c}
    assert {(r["flaw_id"], r["finding_id"]): r["sources"] for r in scores["matching"]["pair_scores"]} == {
        (g, f): src for g, c in want.items() for f, src in c.items()}
    assert any("candidate_rule union" in w and "DEVIATION" in w for w in scores["warnings"])
    # the shortlist prompt is the same under both rules, so its answers are shared through the cache
    _, fake_b, _ = run_pipeline(tmp_path, review, _key(), responder_from(table))
    users = lambda f: sorted(c.user for c in f.calls if c.purpose.startswith("match.shortlist"))  # noqa: E731
    assert users(fake) == users(fake_b)


@pytest.mark.parametrize("rule", ["shortlist_bounded", "union"])
def test_shortlist_failure(tmp_path, rule):
    table = default_table()

    def shortlist(r):
        if r.purpose.endswith("F01"):
            raise JudgeError("shortlist exploded after retries")
        return {"candidate_ids": ["FND-006"], "rationale": "x"}

    table["match.shortlist"] = shortlist
    table["match.pair"] = lambda r: pair(3)
    scores, fake, _ = run_pipeline(tmp_path, make_review(_findings()), _key(), responder_from(table),
                                   candidate_rule=rule)
    m = scores["matching"]
    fails = [f for f in scores["failures"] if f.startswith("shortlist F01")]
    assert len(fails) == 1 and "exploded" in fails[0]
    assert m["shortlist"]["F01"]["ok"] is False and m["shortlist"]["F02"]["ok"] is True
    rows = {r["flaw_id"]: r for r in scores["flaws"]}
    assert rows["F01"]["shortlist_ok"] is False and rows["F02"]["shortlist_ok"] is True
    assert m["candidates"]["F02"]["FND-006"][-1] == "shortlist"
    recall = scores["metrics"]["recall"]
    if rule == "shortlist_bounded":
        # no fallback to overlap: F01 gets no candidates and counts as unmatched, visibly
        assert m["candidates"]["F01"] == {} and not any(g == "F01" for g, _ in _pair_purposes(fake))
        assert "no candidates" in fails[0]
        assert recall["value"] == 0.5 and recall["shortlist_failed_flaws"] == ["F01"]
        assert "lower bound" in recall["note"]
        assert scores["metrics"]["lenient_recall"]["shortlist_failed_flaws"] == ["F01"]
        assert any("shortlist failed for F01" in w and "lower bounds" in w for w in scores["warnings"])
        # the overlap the shortlist would have been hinted with is still on record
        assert m["shortlist"]["F01"]["overlap_hint_ids"] == ["FND-001", "FND-002", "FND-003", "FND-004"]
    else:
        assert set(m["candidates"]["F01"]) == {"FND-001", "FND-002", "FND-003", "FND-004"}
        assert "location overlap only" in fails[0] and "shortlist_failed_flaws" not in recall
    assert validate_scores(scores) == []


def test_dry_run_on_the_live_run_plans_far_fewer_calls(tmp_path):
    runner = CliRunner()

    def plan(*extra: str) -> dict:
        res = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(PAYMENTS_KEY), "--dry-run", *extra])
        assert res.exit_code == 0, res.output
        return json.loads(res.output)

    bounded = plan()
    assert bounded["candidate_rule"] == "shortlist_bounded" and bounded["granularity"] == "pairwise"
    assert bounded["findings_scored"] == 20 and bounded["key_flaws"] == 14
    assert bounded["location_overlap_pairs"] == 80                       # still reported: it is the hint
    assert bounded["candidate_pairs"] == {"min": 0, "max": 42}           # 14 flaws x shortlist_k 3
    c = bounded["calls"]
    assert c["shortlist"] == 14 and c["pair_scoring"] == {"min": 0, "max": 126}
    assert c["adjudication"] == {"min": 6, "max": 20} and c["premise_judge"] == 20 and c["citation_judge"] == 20
    assert c["total"] == {"min": 60, "max": 200}
    assert "shortlist_bounded" in bounded["note"]
    assert plan("--no-grounding-judges")["calls"]["total"] == {"min": 20, "max": 160}
    assert plan("--granularity", "per_flaw_batch")["calls"]["pair_scoring"] == {"min": 0, "max": 42}
    union = plan("--candidate-rule", "union")
    assert union["candidate_pairs"] == {"min": 80, "max": 122}
    assert union["calls"]["pair_scoring"] == {"min": 240, "max": 366}
    assert union["calls"]["total"] == {"min": 300, "max": 440}
    assert plan("--candidate-rule", "union", "--no-grounding-judges")["calls"]["total"] == {"min": 260, "max": 400}
    assert bounded["cost_usd_estimate"]["high"] < union["cost_usd_estimate"]["high"]
    assert bounded["cost_usd_estimate"]["low"] < union["cost_usd_estimate"]["low"]
    bad = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(PAYMENTS_KEY), "--dry-run",
                              "--candidate-rule", "overlap"])
    assert bad.exit_code == 2 and "--candidate-rule" in bad.output


def test_dry_run_prices_call_kinds_separately():
    rin, key = load_review(LIVE_RUN), load_key(PAYMENTS_KEY)
    usd, secs = {"low": 0.03, "typical": 0.11, "high": 0.33}, {"low": 5.0, "high": 20.0}
    kinds = {"shortlist": 0.11, "pair": 0.03, "batch": 0.06, "adjudicate": 0.33, "premise": 0.33, "citation": 0.03,
             "recommendation": 0.03}
    p = plan_calls(rin, key, "v1", options(), usd, secs, per_kind_usd=kinds)
    est = p["cost_usd_estimate"]
    # min plan: 14 shortlist + 6 adjudicate + 20 premise + 20 citation; max adds 126 pair calls, 20 adjudicate
    assert est["low"] == pytest.approx(14 * 0.11 + 6 * 0.33 + 20 * 0.33 + 20 * 0.03) == 10.72
    assert est["high"] == pytest.approx(14 * 0.11 + 126 * 0.03 + 20 * 0.33 + 20 * 0.33 + 20 * 0.03) == 19.12
    assert est["by_kind_at_max"] == {"shortlist": 1.54, "pair": 3.78, "adjudicate": 6.6, "premise": 6.6,
                                     "citation": 0.6}
    off = plan_calls(rin, key, "v1", options(grounding_judges=False), usd, secs, per_kind_usd=kinds)
    assert (off["cost_usd_estimate"]["low"], off["cost_usd_estimate"]["high"]) == (3.52, 11.92)
    un = plan_calls(rin, key, "v1", options(candidate_rule="union"), usd, secs, per_kind_usd=kinds)
    assert (un["cost_usd_estimate"]["low"], un["cost_usd_estimate"]["high"]) == (17.92, 26.32)
    batch = plan_calls(rin, key, "v1", options(granularity="per_flaw_batch", grounding_judges=False), usd, secs,
                       per_kind_usd=kinds)
    assert batch["cost_usd_estimate"]["by_kind_at_max"]["batch"] == 2.52
    # without a per-kind table the flat per-call prices still work
    flat = plan_calls(rin, key, "v1", options(), usd, secs)
    assert flat["cost_usd_estimate"]["low"] == round(60 * 0.03, 2) and "by_kind_at_max" not in flat["cost_usd_estimate"]


def test_default_config_is_shortlist_bounded():
    from sit_eval.config import load_eval_config

    cfg = load_eval_config()
    assert cfg.matcher.candidate_rule == "shortlist_bounded" and cfg.matcher.shortlist_k == 3
    assert cfg.cost_estimate.per_kind_usd is not None
    assert {"shortlist", "pair", "batch", "adjudicate", "premise", "citation"} <= set(cfg.cost_estimate.per_kind_usd)
