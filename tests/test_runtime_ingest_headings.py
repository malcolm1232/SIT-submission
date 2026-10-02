"""Heading detection keeps numbered list items out of the section list (coordinator request,
2026-10-02): a list ``1. ... 4.`` inside section 17.4 or 13 used to become sections "1".."4", so the
cited section +/- 1 window of ``verify_anchor`` missed exact quotes later in the section. Reads only
the evaluated documents' ``design_v1.pdf`` (never an answer key)."""

from __future__ import annotations

import pytest

from sit_review_agent.ingest.anchor import verify_anchor
from sit_review_agent.ingest.pdf import Document, _drop_list_items, ingest
from sit_review_agent.paths import repo_root

SYN = repo_root() / "eval" / "synthetic"


@pytest.mark.parametrize("item, section, page, quote", [
    ("clinical_rpm", "17.4", 17, "Because direct identifiers are removed, extracts are anonymised data and fall "
                                 "outside the PDPA's obligations."),
    ("research_lakehouse", "13", 12, "Because erasure uses ordinary Iceberg row-level deletes, it runs through the "
                                     "same commit path and audit events as"),
])
def test_exact_quote_after_a_numbered_list_resolves_in_its_section(item: str, section: str, page: int,
                                                                   quote: str) -> None:
    doc = ingest(SYN / item / "design_v1.pdf")
    res = verify_anchor(doc, quote, page, section)
    assert res.ok and res.method == "exact" and res.section_id == section, res
    ids = [s.section_id for s in doc.sections]
    top = [int(i.split(".")[0]) for i in ids]
    assert top == sorted(top)                                        # numbering only goes forward


def test_list_items_dropped_real_headings_kept() -> None:
    heads = [(0, "3", "Ingestion"), (10, "1", "Land the file in the bucket."), (20, "2", "Write: the job runs"),
             (30, "4", "Publish the branch when the audit passes."), (40, "4", "Access Control"),
             (50, "4.1", "Roles"), (60, "1", "Grant read access to the analysts."), (70, "5", "Operations")]
    kept = _drop_list_items(heads)
    assert [(n, t) for _, n, t in kept] == [("3", "Ingestion"), ("4", "Access Control"), ("4.1", "Roles"),
                                            ("5", "Operations")]


def test_sparse_numbering_still_detected() -> None:
    text = ("[[PAGE 1]]\n1 Overview\nThe service books rooms.\n[[PAGE 2]]\n4.1 Load\nPeak days see 5,000 bookings.\n"
            "1. Every booking sends one reminder by e-mail.\n[[PAGE 3]]\n20 Decisions\nD-3 Confirmed.\n")
    doc = Document.from_page_marked_text(text, doc_id="DOC-x", title="x")
    assert [s.section_id for s in doc.sections] == ["1", "4.1", "20"]
