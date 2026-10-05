"""invariants.py on the spec's example Review (should pass) and on broken variants (should fail)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

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


def test_inv05_quote_cut_inside_a_url_passes_only_when_the_excerpt_urls_are_backed(
        review_dict: dict[str, Any], booking_pages: str) -> None:
    """A doc quote that ends partway through a URL of its excerpt is skipped by the URL scan when
    every URL of the excerpt is allowed (here: in the document text); when the excerpt's URL is not
    allowed (an excerpt that is a model's anchor quote, URL in no document), the cut URL still fails."""
    r = copy.deepcopy(review_dict)
    passage = f" Weekly counts are published at {DOC_URL} for planning."
    ledger = next(e for e in r["evidence_ledger"] if e["evidence_id"] == "EV-004")
    ledger["excerpt"] += passage
    cite = next(e for f in r["findings"] for e in f["evidence"] if e["evidence_id"] == "EV-004")
    cut = DOC_URL[: DOC_URL.index("/stats") + 4]
    cite["quote"] = f"Weekly counts are published at {cut}"
    pages = booking_pages + f"\nUsage figures: {DOC_URL}\n"
    assert inv.check_INV_05(r, texts={"DOC-booking-v1": pages}).problems == []
    assert inv.check_INV_05(r, texts={"DOC-booking-v1": booking_pages}).problems == [
        f"URL/DOI in report text not in the ledger: {cut}"]
    other = copy.deepcopy(r)                                            # a URL of its own in a quote
    other_cite = next(e for f in other["findings"] for e in f["evidence"] if e["evidence_id"] == "EV-004")
    other_cite["quote"] += " https://made-up.example/x"
    problems = inv.check_INV_05(other, texts={"DOC-booking-v1": pages}).problems
    assert any(p.endswith("evidence EV-004 quote not in the ledger excerpt") for p in problems)
    assert "URL/DOI in report text not in the ledger: https://made-up.example/x" in problems


def test_inv05_quote_urls_must_match_their_excerpt_in_exact_case(
        review_dict: dict[str, Any], booking_pages: str) -> None:
    """Prose in a quote is matched case-insensitively, a URL is not: a quote's URL (whole or cut
    partway) must be an exact-case URL of its excerpt or the start of one. The same quote with the
    URL's path in another case is in the excerpt after case folding, but is not exempt from the scan."""
    excerpt = f"Weekly counts are published at {DOC_URL} for planning."
    cut = DOC_URL[: DOC_URL.index("/stats") + 4]
    allowed = {DOC_URL}
    for q in (f"WEEKLY counts are published at {cut}", f"weekly counts are published at {DOC_URL}"):
        assert inv.quote_urls_in_excerpt(q, excerpt) and inv.quote_backed_by_excerpt(q, excerpt, allowed)
    for q in (f"Weekly counts are published at {cut.replace('/sta', '/STA')}",
              f"Weekly counts are published at {DOC_URL.replace('peak-weeks', 'Peak-Weeks')}"):
        assert inv.quote_in_excerpt(q, excerpt)                         # case folded, prose rule
        assert not inv.quote_urls_in_excerpt(q, excerpt)
        assert not inv.quote_backed_by_excerpt(q, excerpt, allowed)
    r = copy.deepcopy(review_dict)
    ledger = next(e for e in r["evidence_ledger"] if e["evidence_id"] == "EV-004")
    ledger["excerpt"] += f" {excerpt}"
    cite = next(e for f in r["findings"] for e in f["evidence"] if e["evidence_id"] == "EV-004")
    bad = DOC_URL.replace("/stats/", "/Stats/")
    cite["quote"] = f"Weekly counts are published at {bad}"
    pages = booking_pages + f"\nUsage figures: {DOC_URL}\n"
    assert inv.check_INV_05(r, texts={"DOC-booking-v1": pages}).problems == [
        f"URL/DOI in report text not in the ledger: {bad}"]


def test_inv05_quote_that_ends_inside_a_document_url_is_backed_by_the_document(
        review_dict: dict[str, Any], booking_pages: str) -> None:
    """E1: an anchor quote, or a doc quote whose ledger excerpt is that same cut text (the model's
    anchor quote), that ends partway through a URL of the document is a contiguous run of the
    document text, so INV-05 does not scan it; the same quote fails when the document lacks the URL."""
    passage = f"Weekly counts are published at {DOC_URL} for planning."
    cut = passage[: passage.index("/stats") + 4]                         # ends inside DOC_URL
    pages = booking_pages + f"\n{passage}\n"
    anchor = copy.deepcopy(review_dict)
    anchor["findings"][0]["doc_anchors"][0]["quote"] = cut
    assert inv.check_INV_05(anchor, texts={"DOC-booking-v1": pages}).problems == []
    cited = copy.deepcopy(review_dict)
    ledger = next(e for e in cited["evidence_ledger"] if e["evidence_id"] == "EV-004")
    ledger["excerpt"] = cut
    cite = next(e for f in cited["findings"] for e in f["evidence"] if e["evidence_id"] == "EV-004")
    cite["quote"] = cut
    assert inv.check_INV_05(cited, texts={"DOC-booking-v1": pages}).problems == []
    for r in (anchor, cited):
        assert inv.check_INV_05(r, texts={"DOC-booking-v1": booking_pages}).problems == [
            f"URL/DOI in report text not in the ledger: {cut[cut.index('https'):]}"]
    moved = copy.deepcopy(anchor)                                       # not a run of the document text
    moved["findings"][0]["doc_anchors"][0]["quote"] = cut.replace("Weekly", "Monthly")
    assert inv.check_INV_05(moved, texts={"DOC-booking-v1": pages}).problems == [
        f"URL/DOI in report text not in the ledger: {cut[cut.index('https'):]}"]


#: DOC_URL as a PDF extraction can break it across two lines: at a slash, inside a hyphen of the
#: URL, and with a break hyphen the extraction added inside a word.
BROKEN_DOC_URLS = ["https://rooms.campus.example/stats/\npeak-weeks", "https://rooms.campus.example/stats/peak-\nweeks",
                   "https://rooms.campus.example/sta-\nts/peak-weeks"]


@pytest.mark.parametrize("broken", BROKEN_DOC_URLS, ids=["slash", "url-hyphen", "break-hyphen"])
def test_inv05_url_the_document_breaks_across_lines_is_backed(review_dict: dict[str, Any], booking_pages: str,
                                                               broken: str) -> None:
    """E2: a URL of the document broken across two lines (a line break, with or without a break
    hyphen) is ledger-backed in its joined form, so a finding that cites the whole URL passes; a URL
    the document does not hold, joined or not, still fails."""
    pages = booking_pages + f"\nWeekly counts are published at {broken} for planning.\n"
    assert DOC_URL in inv.allowed_urls([], [pages])
    r = copy.deepcopy(review_dict)
    r["findings"][0]["statement"] += f" The usage page is {DOC_URL}."
    assert inv.check_INV_05(r, texts={"DOC-booking-v1": pages}).problems == []
    other = copy.deepcopy(review_dict)
    other["findings"][0]["statement"] += " The usage page is https://rooms.campus.example/stats/peak-days."
    assert inv.check_INV_05(other, texts={"DOC-booking-v1": pages}).problems == [
        "URL/DOI in report text not in the ledger: https://rooms.campus.example/stats/peak-days."]


def test_report_redaction_covers_a_url_inside_a_quote_inv05_does_not_exempt(
        review_dict: dict[str, Any], booking_pages: str) -> None:
    """E3: a doc quote that occurs in its excerpt only after case folding carries a URL the document
    does not have (path case changed); INV-05 does not exempt it, so the report's redaction rewrites
    that URL as it would outside a quote, and INV-05 passes on the redacted review. A quote INV-05
    has verified (cut inside a backed document URL) stays exactly as it was."""
    from sit_review_agent.phases.report import LINK_REMOVED, _redact

    pages = booking_pages + f"\nUsage figures: {DOC_URL}\n"
    r = copy.deepcopy(review_dict)
    ledger = next(e for e in r["evidence_ledger"] if e["evidence_id"] == "EV-004")
    ledger["excerpt"] += f" Weekly counts are published at {DOC_URL} for planning."
    cites = [e for f in r["findings"] for e in f["evidence"] if e["evidence_id"] == "EV-004"]
    bad = DOC_URL.replace("/stats/", "/Stats/")
    cites[0]["quote"] = f"Weekly counts are published at {bad} for planning."
    cut = f"Weekly counts are published at {DOC_URL[: DOC_URL.index('/stats') + 4]}"
    r["findings"][0]["evidence"].append({**cites[0], "quote": cut})
    assert inv.check_INV_05(r, texts={"DOC-booking-v1": pages}).problems == [
        f"URL/DOI in report text not in the ledger: {bad}"]
    allowed = inv.allowed_urls(r["evidence_ledger"], [pages])
    excerpts = {e["evidence_id"]: e["excerpt"] or "" for e in r["evidence_ledger"]}
    counter = [0]
    out = {k: (v if k in ("evidence_ledger", "metadata") else _redact(v, allowed, counter, excerpts, (pages,)))
           for k, v in r.items()}
    quotes = [e["quote"] for f in out["findings"] for e in f["evidence"] if e["evidence_id"] == "EV-004"]
    assert f"Weekly counts are published at {LINK_REMOVED} for planning." in quotes and counter == [1]
    assert cut in quotes                                                # verified: untouched
    assert inv.check_INV_05(out, texts={"DOC-booking-v1": pages}).problems == []


@pytest.mark.parametrize("scheme", ["HTTPS", "Http", "hTtP"])
def test_inv05_finds_a_url_whose_scheme_is_not_lowercase(review_dict: dict[str, Any], booking_pages: str,
                                                        scheme: str) -> None:
    """A URL whose scheme is not lowercase is a URL: INV-05 names a made-up one, and a document URL
    whose only change is its scheme's case is not the document's URL (the model does not get to
    rewrite it). An allowed URL written as the document writes it still passes."""
    made_up = f"{scheme}://made-up.example/p"
    bad = copy.deepcopy(review_dict)
    bad["findings"][0]["statement"] += f" See {made_up}."
    assert inv.check_INV_05(bad, texts={"DOC-booking-v1": booking_pages}).problems == [
        f"URL/DOI in report text not in the ledger: {made_up}."]
    pages = booking_pages + f"\nUsage figures: {DOC_URL}\n"
    recased = DOC_URL.replace("https", scheme, 1)
    moved = copy.deepcopy(review_dict)
    moved["findings"][0]["statement"] += f" The usage page is {recased}."
    assert inv.check_INV_05(moved, texts={"DOC-booking-v1": pages}).problems == [
        f"URL/DOI in report text not in the ledger: {recased}."]
    assert inv.allowed_urls([], [f"Figures at {recased} weekly."]) == {recased}     # kept as written


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
