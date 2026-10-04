"""invariants.py on the spec's example Review (should pass) and on broken variants (should fail)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from sit_review_agent import invariants as inv


def test_example_review_passes(review_dict: dict[str, Any], booking_pages: str) -> None:
    results = inv.check_all(review_dict, texts={"DOC-booking-v1": booking_pages}, require_extra=False)
    failed = {r.inv_id: r.problems for r in results if not r.passed}
    assert failed == {}


def test_inv04_rejects_moved_quote(review_dict: dict[str, Any], booking_pages: str) -> None:
    bad = copy.deepcopy(review_dict)
    bad["findings"][0]["doc_anchors"][0]["page"] = 2
    assert not inv.check_INV_04(bad, texts={"DOC-booking-v1": booking_pages}).passed


def test_inv05_rejects_free_url_and_unknown_evidence(review_dict: dict[str, Any]) -> None:
    bad = copy.deepcopy(review_dict)
    bad["findings"][0]["statement"] += " See https://made-up.example/paper."
    bad["findings"][0]["evidence"][0]["evidence_id"] = "EV-999"
    problems = inv.check_INV_05(bad).problems
    assert any("made-up.example" in p for p in problems) and any("EV-999" in p for p in problems)


DOC_URL = "https://rooms.campus.example/stats/peak-weeks"


def test_inv05_accepts_a_url_of_the_cited_excerpt_and_of_the_document(review_dict: dict[str, Any],
                                                                     booking_pages: str) -> None:
    """A URL of the reviewed document is ledger-backed (``allowed_urls``), in a cited doc quote or in
    a statement; a URL in a doc excerpt counts only when the document text holds it (a doc excerpt
    can be a model's anchor quote, so it backs nothing by itself); a URL in no document is not."""
    ok = copy.deepcopy(review_dict)
    passage = f" Weekly counts are published at {DOC_URL}."
    ledger = next(e for e in ok["evidence_ledger"] if e["evidence_id"] == "EV-004")
    ledger["excerpt"] += passage
    cite = next(e for f in ok["findings"] for e in f["evidence"] if e["evidence_id"] == "EV-004")
    cite["quote"] += passage
    pages = booking_pages + f"\nUsage figures: {DOC_URL}\n"
    assert inv.check_INV_05(ok, texts={"DOC-booking-v1": pages}).problems == []
    assert inv.check_INV_05(ok, texts={"DOC-booking-v1": booking_pages}).problems == [
        f"URL/DOI in report text not in the ledger: {DOC_URL}."]
    in_doc = copy.deepcopy(review_dict)
    in_doc["findings"][0]["statement"] += f" The usage page is {DOC_URL}."
    assert inv.check_INV_05(in_doc, texts={"DOC-booking-v1": pages}).problems == []
    assert any(DOC_URL in p for p in inv.check_INV_05(in_doc, texts={"DOC-booking-v1": booking_pages}).problems)
    bad = copy.deepcopy(ok)
    bad["findings"][0]["statement"] += " See https://made-up.example/paper."
    problems = inv.check_INV_05(bad, texts={"DOC-booking-v1": pages}).problems
    assert problems == ["URL/DOI in report text not in the ledger: https://made-up.example/paper."]


def test_allowed_urls_ignores_inference_statements() -> None:
    """An inference excerpt is the model's own statement and a doc excerpt may be a model's anchor
    quote: neither backs a URL; an external excerpt (the tool result) and the document text do."""
    entries = [{"url_or_citation": "inference:EV-002", "source_type": "inference",
                "excerpt": "Per https://made-up.example/x the quota is low."},
               {"url_or_citation": "doc:DOC-a#p1/s1", "source_type": "doc",
                "excerpt": f"Counts are at {DOC_URL} and https://made-up.example/anchor."},
               {"url_or_citation": "https://vendor.example/limits", "source_type": "external",
                "excerpt": "Quotas: see https://vendor.example/limits/sms for SMS."}]
    assert inv.allowed_urls(entries, [f"See https://docs.example/a, then go. Counts: {DOC_URL}"]) == {
        "inference:EV-002", "doc:DOC-a#p1/s1", "https://vendor.example/limits", "https://vendor.example/limits/sms",
        DOC_URL, "https://docs.example/a"}
    assert inv.allowed_urls(entries, []) == {
        "inference:EV-002", "doc:DOC-a#p1/s1", "https://vendor.example/limits", "https://vendor.example/limits/sms"}


def test_inv07_requires_disclosure(review_dict: dict[str, Any]) -> None:
    bad = copy.deepcopy(review_dict)
    bad["stop_reason"] = {"code": "deadline", "group": "cap", "detail": None}
    assert not inv.check_INV_07(bad).passed


def test_inv08_finds_canary(tmp_path: Path) -> None:
    (tmp_path / "llm.jsonl").write_text('{"h": "CANARY-MCP-7f3a"}\n')
    assert not inv.check_INV_08(tmp_path, ["CANARY-MCP-7f3a"]).passed
    assert inv.check_INV_08(tmp_path, ["CANARY-OTHER"]).passed


def test_inv09_requires_manifest_extra(review_dict: dict[str, Any]) -> None:
    assert inv.check_INV_09(review_dict, require_extra=False).passed
    assert not inv.check_INV_09(review_dict).passed           # example has extra = {}


def test_inv10_registry_hash_constant(review_dict: dict[str, Any]) -> None:
    bad = copy.deepcopy(review_dict)
    bad["decision_registry"][0]["statement"] = "changed after iteration 1"
    assert not inv.check_INV_10(bad).passed
