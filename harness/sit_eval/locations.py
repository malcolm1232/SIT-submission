"""Location normalisation and overlap (metrics.md §2.1 rule 3, §2.3 step 1a, §6.2).

Key locations are free strings such as ``"3 (P2)"``, ``"5 (Figure 1 caption)"``, ``"25 (item 2)"`` or
``"14 Ledger and Double-Entry Accounting"``; finding anchors carry ``section_ref`` (``"9.2"``,
``"Title page"``) and ``requirement_ids``. Both are reduced to

* a set of numbered section ids (the leading number, e.g. ``"12.1"``), and
* a set of document IDs (requirement / decision IDs such as ``FR-5``, ``NFR-7``, ``D-3``, plus
  principle IDs ``P2`` found in the strings).

Two locations overlap when a section id is equal to, an ancestor of, or a descendant of the other
(``"12"`` overlaps ``"12.1"``), or when the ID sets intersect. This is the harness's
operationalisation of "the finding's section or req ids intersect the flaw anchor".
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

#: Same pattern as ``sit_review_agent.ingest.pdf.REQUIREMENT_ID_RE`` plus principle IDs ("P2").
DOC_ID_RE = re.compile(r"\b[A-Z]{1,4}(?:-[A-Z]+)*-\d+\b|\bP\d{1,2}\b")
_SECTION_RE = re.compile(r"^\s*(?:§\s*|section\s+)?(\d{1,2}(?:\.\d{1,3}){0,4})(?![\d-])", re.I)


def section_id(ref: str | None) -> str | None:
    """Leading section number of ``ref`` (``"3 (P2)"`` -> ``"3"``), else ``None``."""
    if not ref:
        return None
    m = _SECTION_RE.match(ref)
    return m.group(1).rstrip(".") if m else None


def ids_in(text: str | None) -> set[str]:
    return set(DOC_ID_RE.findall(text or ""))


def sections_overlap(a: str, b: str) -> bool:
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


@dataclass(frozen=True)
class Loc:
    sections: frozenset[str] = field(default_factory=frozenset)
    ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def empty(self) -> bool:
        return not self.sections and not self.ids

    def overlaps(self, other: Loc) -> bool:
        if self.ids & other.ids:
            return True
        return any(sections_overlap(a, b) for a in self.sections for b in other.sections)


def key_location(location: dict) -> Loc:
    """``Location`` of an answer-key flaw, sound section or approved decision."""
    secs = {s for s in (section_id(x) for x in location.get("sections", [])) if s}
    ids = set(location.get("requirement_ids", [])) | set(location.get("decision_ids", []))
    for x in location.get("sections", []):
        ids |= ids_in(x)
    return Loc(frozenset(secs), frozenset(ids))


def anchors_location(anchors: Iterable[dict]) -> Loc:
    """Union location of a finding's (or sound area's) ``doc_anchors``."""
    secs: set[str] = set()
    ids: set[str] = set()
    for a in anchors:
        s = section_id(a.get("section_ref"))
        if s:
            secs.add(s)
        ids |= set(a.get("requirement_ids", []))
    return Loc(frozenset(secs), frozenset(ids))
