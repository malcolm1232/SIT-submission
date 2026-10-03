"""verify_anchor implements the spec anchor rule: >= 8 tokens, exact then fuzzy >= 0.90, cited page
+/- 1 intersected with cited section +/- 1, 1-3 anchors per finding (ADR-007, INV-04)."""

from __future__ import annotations

import pytest

from sit_review_agent.ingest.anchor import (
    NO_ANCHORS,
    NOT_FOUND,
    PAGE_OUT_OF_RANGE,
    QUOTE_TOO_SHORT,
    SECTION_MISMATCH,
    SECTION_UNRESOLVED,
    TOO_MANY_ANCHORS,
    verify_anchor,
    verify_finding_anchors,
)
from sit_review_agent.ingest.pdf import Document
from sit_review_agent.ingest.text import normalise
from sit_review_agent.models import DocAnchor

# Invented, prompt-safe fixture. Raw text includes a ligature, curly quotes and an en dash, which
# normalise() must turn into the canonical forms the model is told to quote.
RAW = """[[PAGE 1]]
1 Introduction
The campus room booking service lets students reserve quiet study rooms for one-hour slots.
[[PAGE 2]]
2 Requirements
FR-1 A student may hold up to three active bookings at any one time across all buildings.
FR-2 Every booking receives a reminder message one hour before the slot begins.
[[PAGE 3]]
3 Architecture
3.1 Booking service
The booking service stores reservations in the existing campus PostgreSQL cluster with nightly backups.
3.2 Notifications
The notiﬁcation worker sends “reminders” through the selected e-mail service as each slot approaches.
[[PAGE 4]]
4 Operations
The operations team monitors queue depth and restarts the notification worker if it stalls.
[[PAGE 5]]
5 Security
All staff accounts use single sign-on with multi-factor authentication enforced by the identity provider.
[[PAGE 6]]
6 Decisions
D-1 Confirmed: reservations remain in the existing PostgreSQL cluster – no change of database engine.
"""

DOC = Document.from_page_marked_text(normalise(RAW), doc_id="DOC-rooms-v1")


def test_fixture_parses() -> None:
    assert [p.number for p in DOC.pages] == [1, 2, 3, 4, 5, 6]
    assert [s.section_id for s in DOC.sections] == ["1", "2", "3", "3.1", "3.2", "4", "5", "6"]
    assert set(DOC.requirement_index) == {"FR-1", "FR-2", "D-1"}
    assert DOC.requirement_index["FR-2"][0].page == 2


# ------------------------------------------------------------------------------- accepted


def test_exact_match_on_cited_page() -> None:
    q = "The booking service stores reservations in the existing campus PostgreSQL cluster with nightly backups."
    r = verify_anchor(DOC, q, 3, "3.1")
    assert r.ok and r.method == "exact" and r.score == 1.0 and r.matched_page == 3 and r.section_id == "3.1"
    assert DOC.text[r.char_start:r.char_end] == q


def test_fuzzy_match_with_small_typos() -> None:
    q = "The operations team monitors queue depth and restart the notification worker if it stals."
    r = verify_anchor(DOC, q, 4, "4")
    assert r.ok and r.method == "fuzzy" and r.score >= 0.90 and r.matched_page == 4


def test_adjacent_page_is_accepted() -> None:
    q = "The operations team monitors queue depth and restarts the notification worker if it stalls."
    r = verify_anchor(DOC, q, 3, "4")          # cited one page early
    assert r.ok and r.matched_page == 4


def test_quote_across_a_line_break() -> None:
    q = "at any one time across all buildings. FR-2 Every booking receives a reminder"
    r = verify_anchor(DOC, q, 2, "2")
    assert r.ok and r.method == "exact"


def test_ligatures_and_typographic_quotes_are_normalised() -> None:
    q = 'The notification worker sends "reminders" through the selected e-mail service'
    r = verify_anchor(DOC, q, 3, "3.2")
    assert r.ok and r.method == "exact"


def test_unresolved_section_falls_back_to_page_window_with_note() -> None:
    q = "All staff accounts use single sign-on with multi-factor authentication enforced"
    r = verify_anchor(DOC, q, 5, "Appendix Z")
    assert r.ok and SECTION_UNRESOLVED in r.reasons


# ------------------------------------------------------------------------------- rejected


def test_reject_quote_shorter_than_eight_tokens() -> None:
    r = verify_anchor(DOC, "stores reservations in the existing campus PostgreSQL", 3, "3.1")
    assert not r.ok and r.reasons == (QUOTE_TOO_SHORT,)


def test_reject_invented_quote() -> None:
    q = "The booking service replicates every reservation to three regions with synchronous commits."
    r = verify_anchor(DOC, q, 3, "3.1")
    assert not r.ok and NOT_FOUND in r.reasons


def test_reject_real_quote_cited_two_pages_away() -> None:
    q = "The campus room booking service lets students reserve quiet study rooms for one-hour slots."
    r = verify_anchor(DOC, q, 3, "3")          # really on page 1
    assert not r.ok and NOT_FOUND in r.reasons


def test_reject_page_out_of_range() -> None:
    q = "The booking service stores reservations in the existing campus PostgreSQL cluster with nightly backups."
    r = verify_anchor(DOC, q, 99, "3.1")
    assert not r.ok and r.reasons == (PAGE_OUT_OF_RANGE,)


def test_reject_quote_outside_cited_section_window() -> None:
    q = "The booking service stores reservations in the existing campus PostgreSQL cluster with nightly backups."
    r = verify_anchor(DOC, q, 3, "6")          # right page, section 6 +/- 1 does not reach page 3
    assert not r.ok and SECTION_MISMATCH in r.reasons


def _anchor(quote: str, page: int, section: str) -> DocAnchor:
    return DocAnchor(doc_id="DOC-rooms-v1", section_ref=section, requirement_ids=[], quote=quote, page=page)


def test_reject_more_than_three_anchors_and_none() -> None:
    a = _anchor("The booking service stores reservations in the existing campus PostgreSQL cluster", 3, "3.1")
    results = verify_finding_anchors({"DOC-rooms-v1": DOC}, [a, a, a, a])
    assert [r.ok for r in results] == [True, True, True, False]
    assert results[3].reasons == (TOO_MANY_ANCHORS,)
    none = verify_finding_anchors({"DOC-rooms-v1": DOC}, [])
    assert len(none) == 1 and none[0].reasons == (NO_ANCHORS,)


@pytest.mark.parametrize("page", [2, 3, 4])
def test_window_is_page_plus_minus_one(page: int) -> None:
    q = "The booking service stores reservations in the existing campus PostgreSQL cluster with nightly backups."
    assert verify_anchor(DOC, q, page, "3.1").ok


def test_table_of_contents_does_not_capture_section_refs() -> None:
    raw = ("[[PAGE 1]]\nContents\n1 Introduction\n2 Requirements\n3 Design\n"
           "[[PAGE 2]]\n1 Introduction\nThe service lets students reserve study rooms across the whole campus.\n"
           "[[PAGE 3]]\n2 Requirements\nFR-1 A student may hold up to three active bookings at any one time.\n"
           "3 Design\nBookings are stored in the existing campus database cluster with nightly backups.\n")
    doc = Document.from_page_marked_text(normalise(raw), doc_id="DOC-toc")
    assert [(s.section_id, s.page_start) for s in doc.sections] == [("1", 2), ("2", 3), ("3", 3)]
    r = verify_anchor(doc, "FR-1 A student may hold up to three active bookings at any one time.", 3, "2")
    assert r.ok and r.section_id == "2"


def test_toc_whose_last_entry_is_followed_by_a_footer_is_still_dropped() -> None:
    # The last contents line is followed by a page footer and a running header, so its "body" is not
    # empty; it must still be read as a contents entry, not as a real section that swallows the rest.
    raw = ("[[PAGE 1]]\nRoom Booking - Design\nTable of Contents\n1. Introduction\n2. Requirements\n3. Design\n"
           "Page 1\n[[PAGE 2]]\nRoom Booking - Design\n1. Introduction\n"
           "The service lets students reserve study rooms across the whole campus.\n"
           "[[PAGE 3]]\nRoom Booking - Design\n2. Requirements\n"
           "FR-1 A student may hold up to three active bookings at any one time.\n"
           "The booking flow has three layers:\n1 Search\n2 Hold\n3 Confirm\n"
           "3. Design\nBookings are stored in the existing campus database cluster with nightly backups.\n")
    doc = Document.from_page_marked_text(normalise(raw), doc_id="DOC-toc-footer")
    assert [(s.section_id, s.heading, s.page_start) for s in doc.sections] == [
        ("1", "Introduction", 2), ("2", "Requirements", 3), ("3", "Design", 3)]
