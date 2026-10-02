"""Grader-facing projection: nothing prereg forbids reaches a grader input (GR §6.2; prereg grader.input)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from sit_eval.grader import projection as pj
from sit_eval.grader.costs import Budget
from sit_eval.grader.pipeline import _make

SENTINELS = ["REV-cc_opus_SENTINEL", "RUN-SENTINEL-7781", "claude-opus-5-5", "claude-sonnet-5-5", "deadbeefcafe1234",
             "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90", "CALL-SENTINEL-42",
             "snapshots/SENTINEL.html", "runs/RUN-SENTINEL-7781/text/doc.txt", "mcp-sentinel-search"]


def _poisoned(review: dict[str, Any]) -> dict[str, Any]:
    r = copy.deepcopy(review)
    r["metadata"]["review_id"] = "REV-cc_opus_SENTINEL"
    r["metadata"]["run_id"] = "RUN-SENTINEL-7781"
    r["metadata"]["documents"][0]["text_path"] = "runs/RUN-SENTINEL-7781/text/doc.txt"
    r["run_manifest"]["run_id"] = "RUN-SENTINEL-7781"
    r["run_manifest"]["git_commit"] = "deadbeefcafe1234"
    r["run_manifest"]["condition"] = "A5-no-tools-SENTINEL"
    r["run_manifest"]["models_used"][0]["served_models"] = ["claude-sonnet-5-5"]
    for f in r["findings"]:
        f["provenance"]["model"] = "claude-opus-5-5"
        f["provenance"]["prompt_hash"] = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
    ext = next(e for e in r["evidence_ledger"] if e["source_type"] == "external")
    ext["tool"] = {"server": "mcp-sentinel-search", "tool_name": "search", "call_id": "CALL-SENTINEL-42"}
    ext["snapshot_path"] = "snapshots/SENTINEL.html"
    r["research_log"]["tool_calls"] = [{"call_id": "CALL-SENTINEL-42", "server": "mcp-sentinel-search",
                                        "tool_name": "search", "status": "ok", "started_at": "2026-10-02T09:00:00Z"}]
    r["stop_reason"]["detail"] = "no_tools A5-no-tools-SENTINEL"
    r["limitations"] = [{"text": "Run RUN-SENTINEL-7781 used claude-opus-5-5 at effort high.",
                         "degradation_ids": ["DEG-001"]}]
    r["brand_new_top_level_field"] = {"secret": "UNKNOWN-FIELD-SENTINEL"}
    r["findings"][0]["brand_new_finding_field"] = "UNKNOWN-FINDING-SENTINEL"
    return r


def test_grader_projection_drops_and_scrubs_everything_forbidden(review_dict: dict[str, Any]) -> None:
    proj, audit = pj.project_review(_poisoned(review_dict))
    text = json.dumps(proj)
    for s in [*SENTINELS, "UNKNOWN-FIELD-SENTINEL", "UNKNOWN-FINDING-SENTINEL", "A5-no-tools-SENTINEL", "no_tools"]:
        assert s not in text, s
    for key in pj.FORBIDDEN_KEYS:
        assert f'"{key}"' not in text, key
    assert set(audit["dropped_top_level"]) >= {"run_manifest", "research_log", "brand_new_top_level_field"}
    assert audit["strings_scrubbed"] >= 2          # run id and model id inside the limitation text
    assert proj["limitations"][0]["text"].count(pj.REDACTED) == 2
    # what the grader needs is still there
    assert [f["id"] for f in proj["findings"]] == ["FND-001", "FND-007"]
    assert proj["verdict"]["label"] == "fit_with_conditions"
    sr = review_dict["stop_reason"]
    assert proj["stop_reason"] == {"code": sr["code"], "group": sr["group"]}
    assert all("tool" not in e and "snapshot_path" not in e for e in proj["evidence_ledger"])


def test_grader_rendered_inputs_have_no_leaks(tmp_path: Path, review_dict: dict[str, Any], booking_pages: str,
                                              write_review) -> None:
    pages = tmp_path / "p.pages.txt"
    pages.write_text(booking_pages, encoding="utf-8")
    review = _poisoned(review_dict)
    path = write_review(review)
    g = _make(path, pages, tmp_path / "o", None, None, None, None, 2, 0, Budget(), "claude-opus-5-5", "high", None)
    _, ua, _ = g.render_pass_a(0)
    _, _, ub = g.render_pass_b(0, "{}", key_aware=False)
    for text in (g.system, ua, ub):
        for s in [*SENTINELS, "A5-no-tools-SENTINEL", "UNKNOWN-FIELD-SENTINEL", '"provenance"', '"run_manifest"',
                  '"research_log"', '"prompt_hash"', '"snapshot_path"']:
            assert s not in text, s
    assert pj.leak_report([g.system, ua, ub], review, design_text=booking_pages) == []
    # and the guard would have caught a leak
    assert pj.leak_report(["the agent ran on claude-opus-5-5"], review) == ["claude-opus-5-5"]


def test_grader_scrub_keeps_values_the_design_itself_contains(review_dict: dict[str, Any]) -> None:
    r = copy.deepcopy(review_dict)
    r["run_manifest"]["models_used"][0]["served_models"] = ["claude-opus-5-5"]
    r["findings"][0]["statement"] += " The design pins claude-opus-5-5 for summarisation."
    proj, _ = pj.project_review(r, design_text="The summariser uses claude-opus-5-5 (section 9).")
    assert "claude-opus-5-5" in proj["findings"][0]["statement"]
    proj2, _ = pj.project_review(r, design_text="")
    assert "claude-opus-5-5" not in json.dumps(proj2)


def test_grader_pass_a_view_hides_rank_and_resolves_decisions(review_dict: dict[str, Any]) -> None:
    proj, _ = pj.project_review(review_dict)
    items = pj.findings_for_pass_a(proj)
    assert all("rank" not in f for f in items)
    ad = next(f for f in items if f["affected_decisions"])["affected_decisions"][0]
    assert ad["decision"]["doc_ref"] == "D-3"


def test_grader_shuffle_is_seeded_and_recorded(review_dict: dict[str, Any]) -> None:
    r = copy.deepcopy(review_dict)
    base = r["findings"][0]
    r["findings"] = [{**copy.deepcopy(base), "id": f"FND-{i:03d}", "rank": i} for i in range(1, 9)]
    proj, _ = pj.project_review(r)
    t1, o1 = pj.shuffle_findings(proj, 1001)
    t1b, o1b = pj.shuffle_findings(proj, 1001)
    _, o2 = pj.shuffle_findings(proj, 1002)
    assert (t1, o1) == (t1b, o1b)
    assert o1 != o2 and sorted(o1) == sorted(o2)
    assert [json.loads(line)["id"] for line in t1.splitlines()] == o1


def test_grader_review_full_text_is_json_in_rank_order(review_dict: dict[str, Any]) -> None:
    r = copy.deepcopy(review_dict)
    r["findings"].reverse()
    proj, _ = pj.project_review(r)
    body = json.loads(pj.review_full_text(proj))
    assert [f["rank"] for f in body["findings"]] == [1, 2]
    assert "evidence_ledger" not in body
    assert pj.evidence_register({"evidence_ledger": []}) == "NONE"


def test_grader_rejects_non_json_review(tmp_path: Path) -> None:
    p = tmp_path / "review.md"
    p.write_text("# A review in Markdown", encoding="utf-8")
    with pytest.raises(pj.GraderInputError, match="not JSON"):
        pj.load_review(p)
    p.write_text("{}", encoding="utf-8")
    with pytest.raises(pj.GraderInputError, match="not a Review"):
        pj.load_review(p)
