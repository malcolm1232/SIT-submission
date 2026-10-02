"""Quote-anchor verification (ADR-007, spec ``anchor_rules``, robustness INV-04).

One function, :func:`verify_anchor`, is shared by the ``verify`` phase and the INV-04 oracle.
Rules (PROPOSED DEFAULTS, frozen in ``prereg.yaml`` after S-dev calibration):

* the quote has at least 8 whitespace-separated tokens;
* the cited page exists (1..page_count); ``page`` may be ``null`` only for page-less inputs;
* the search window is the cited page +/- 1 **intersected with** the cited section +/- 1 in
  document order (if the section cannot be resolved, the page window alone is used and the result
  carries the note ``section_unresolved``);
* exact substring match on the normalised text first, else ``rapidfuzz`` partial-ratio >= 0.90;
* a finding has 1 to 3 anchors (:func:`verify_finding_anchors`).

Match metadata (method, score, matched page, character span in the canonical text) goes into the
run's ``anchors.json``, never into the Finding (``DocAnchor`` is ``additionalProperties: false``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from rapidfuzz import fuzz

from sit_review_agent.ingest.pdf import Document
from sit_review_agent.ingest.text import flatten_for_match, normalise_quote, quote_tokens
from sit_review_agent.models import DocAnchor

# rejection reasons
QUOTE_TOO_SHORT = "quote_too_short"
PAGE_MISSING = "page_missing"
PAGE_OUT_OF_RANGE = "page_out_of_range"
SECTION_MISMATCH = "section_mismatch"
NOT_FOUND = "not_found"
NO_ANCHORS = "no_anchors"
TOO_MANY_ANCHORS = "too_many_anchors"
DOC_UNKNOWN = "doc_unknown"
# notes (do not reject)
SECTION_UNRESOLVED = "section_unresolved"

AnchorMethod = Literal["exact", "fuzzy", "none"]


@dataclass(frozen=True)
class AnchorRules:
    """Taxonomy ``anchor_rules`` plus the ADR-007 window."""

    min_quote_tokens: int = 8
    fuzzy_threshold: float = 0.90
    page_window: int = 1
    section_window: int = 1
    min_anchors: int = 1
    max_anchors: int = 3


DEFAULT_RULES = AnchorRules()


@dataclass(frozen=True)
class AnchorResult:
    ok: bool
    method: AnchorMethod
    score: float                        # 1.0 for exact, rapidfuzz ratio / 100 for fuzzy, 0 if none
    matched_page: int | None
    char_start: int | None              # span in Document.text (the canonical page-marked text)
    char_end: int | None
    section_id: str | None              # the resolved cited section, if any
    reasons: tuple[str, ...] = field(default=())   # rejection reasons, plus notes such as section_unresolved

    def to_json(self) -> dict[str, Any]:
        return {"ok": self.ok, "method": self.method, "score": round(self.score, 4),
                "matched_page": self.matched_page, "char_start": self.char_start, "char_end": self.char_end,
                "section_id": self.section_id, "reasons": list(self.reasons)}


def _reject(reason: str, *, section_id: str | None = None, notes: Sequence[str] = ()) -> AnchorResult:
    return AnchorResult(ok=False, method="none", score=0.0, matched_page=None, char_start=None, char_end=None,
                        section_id=section_id, reasons=(reason, *notes))


def verify_anchor(doc: Document, quote: str, page: int | None, section: str,
                  rules: AnchorRules = DEFAULT_RULES) -> AnchorResult:
    """Check that ``quote`` occurs in ``doc`` near ``page`` and ``section`` (see module docstring)."""
    q = normalise_quote(quote)
    if quote_tokens(q) < rules.min_quote_tokens:
        return _reject(QUOTE_TOO_SHORT)

    # ---- page window
    if doc.pages:
        if page is None:
            return _reject(PAGE_MISSING)
        if page < 1 or page > (doc.page_count or 0):
            return _reject(PAGE_OUT_OF_RANGE)
        in_window = [p for p in doc.pages if abs(p.number - page) <= rules.page_window]
        if not in_window:
            return _reject(NOT_FOUND)
        ws, we = min(p.char_start for p in in_window), max(p.char_end for p in in_window)
    else:
        ws, we = 0, len(doc.text)

    # ---- section window (cited section +/- 1 in document order), per candidate section
    notes: list[str] = []
    candidates = doc.find_sections(section)
    windows: list[tuple[int, int, str | None]] = []
    if not candidates:
        notes.append(SECTION_UNRESOLVED)
        windows.append((ws, we, None))
    for sec in candidates:
        lo = doc.sections[max(0, sec.order - rules.section_window)]
        hi = doc.sections[min(len(doc.sections) - 1, sec.order + rules.section_window)]
        s0, s1 = max(ws, lo.char_start), min(we, hi.char_end)
        if s0 < s1:
            windows.append((s0, s1, sec.section_id))
    if not windows:
        return _reject(SECTION_MISMATCH, section_id=candidates[-1].section_id, notes=notes)
    for s0, s1, sec_id in windows:
        hit = _match(doc, q, s0, s1, sec_id, notes, rules)
        if hit is not None:
            return hit
    return _reject(NOT_FOUND, section_id=windows[0][2], notes=notes)


def _match(doc: Document, q: str, ws: int, we: int, sec_id: str | None, notes: list[str],
           rules: AnchorRules) -> AnchorResult | None:
    """Exact, then fuzzy match of normalised quote ``q`` in ``doc.text[ws:we]``."""
    hay = flatten_for_match(doc.text[ws:we])
    i = hay.find(q)
    if i >= 0:
        start = ws + i
        return AnchorResult(ok=True, method="exact", score=1.0, matched_page=doc.page_at(start) if doc.pages else None,
                            char_start=start, char_end=start + len(q), section_id=sec_id, reasons=tuple(notes))
    if len(q) <= len(hay):
        al = fuzz.partial_ratio_alignment(q.lower(), hay.lower(), score_cutoff=rules.fuzzy_threshold * 100)
        if al is not None and al.score >= rules.fuzzy_threshold * 100:
            start, end = ws + al.dest_start, ws + al.dest_end
            return AnchorResult(ok=True, method="fuzzy", score=al.score / 100,
                                matched_page=doc.page_at(start) if doc.pages else None,
                                char_start=start, char_end=end, section_id=sec_id, reasons=tuple(notes))
    return None


def verify_finding_anchors(docs: Mapping[str, Document], anchors: Sequence[DocAnchor],
                           rules: AnchorRules = DEFAULT_RULES) -> list[AnchorResult]:
    """Verify every anchor of one finding. Anchors beyond ``max_anchors`` are rejected with
    ``too_many_anchors`` (strict structured outputs cannot enforce ``maxItems``); an empty list
    yields one ``no_anchors`` rejection."""
    if len(anchors) < rules.min_anchors:
        return [_reject(NO_ANCHORS)]
    out: list[AnchorResult] = []
    for i, a in enumerate(anchors):
        if i >= rules.max_anchors:
            out.append(_reject(TOO_MANY_ANCHORS))
        elif a.doc_id not in docs:
            out.append(_reject(DOC_UNKNOWN))
        else:
            out.append(verify_anchor(docs[a.doc_id], a.quote, a.page, a.section_ref, rules))
    return out


def anchor_table_entry(owner_id: str, index: int, anchor: DocAnchor, result: AnchorResult,
                       *, repaired: bool = False) -> dict[str, Any]:
    """One row of ``runs/<id>/anchors.json`` (keyed by finding/sound-area/registry ID and index)."""
    status = "unresolved" if not result.ok else ("repaired" if repaired else "resolved")
    return {"owner_id": owner_id, "anchor_index": index, "doc_id": anchor.doc_id, "page": anchor.page,
            "section_ref": anchor.section_ref, "anchor_status": status, **result.to_json()}
