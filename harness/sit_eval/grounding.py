"""Grounding checks (metrics.md §5, prereg ``grounding``).

* **G1 quote existence** (deterministic): the quote, normalised with the agent's own
  ``normalise_quote`` (NFKC, typographic quotes and dashes, de-hyphenation, whitespace), occurs in
  the canonical page-marked text: exact substring, else ``rapidfuzz`` partial-ratio >= ``theta_q``
  on lower-cased text, searched over the whole document. Anchor quotes under 8 tokens fail (the
  ``DocAnchor`` rule); shorter doc-evidence quotes are allowed but must match exactly
  (case-insensitive), since a fuzzy ratio on a few tokens is meaningless.
* **G2 location validity** (deterministic): exactly the agent's verify-stage check,
  ``sit_review_agent.ingest.anchor.verify_anchor`` (cited page +/- 1 intersected with the cited
  section +/- 1), with ``fuzzy_threshold = theta_q``. Differences from the metrics.md wording,
  reported in the harness README: the ratio is character-level partial-ratio (metrics.md says
  "token-level"), the exact pass is case-sensitive before the case-insensitive fuzzy pass, and an
  unresolvable section falls back to the page window alone (noted ``section_unresolved``).
* **G3 premise** (judge): SUPPORTED / CONTRADICTED / NOT_FOUND plus ``is_absence_claim``, with the
  whole document in the prompt (which also serves as the retrieval for absence claims).
* **Citation support** (judge, step 2 of §5.2): FULL / PARTIAL / NONE per supporting evidence item,
  one call per finding. Step 1 (existence and provenance) is deterministic from the evidence
  ledger: READ, EXISTS_NOT_READ or FABRICATED. Live URL / DOI resolution is not done (offline).
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from sit_eval import prompts
from sit_eval.calls import BudgetStop, JudgeRunner
from sit_eval.judge import JudgeError
from sit_eval.matcher import FindingView, render_finding
from sit_review_agent.ingest import AnchorRules, Document, verify_anchor
from sit_review_agent.ingest.text import flatten_for_match, normalise_quote, quote_tokens

_DOC_CITE = re.compile(r"#p(?P<page>\d+)(?:/s(?P<section>[^/\s]+))?")
CONTEXT_CHARS = 400


@dataclass
class QuoteCheck:
    finding_id: str
    origin: str                  # anchor[i] | evidence:EV-xxx
    quote: str
    g1: bool
    g1_score: float
    g1_reason: str | None
    g2: bool | None              # None when no page/section is cited (evidence without a doc citation)
    g2_reasons: list[str] = field(default_factory=list)
    char_span: tuple[int, int] | None = None


class QuoteFinder:
    def __init__(self, doc: Document, theta_q: float) -> None:
        self.doc = doc
        self.theta_q = theta_q
        self.hay = flatten_for_match(doc.text)
        self.hay_lower = self.hay.lower()
        self.rules = AnchorRules(fuzzy_threshold=theta_q)

    def g1(self, quote: str, page: int | None = None, *, min_tokens: int | None = None
           ) -> tuple[bool, float, str | None, tuple[int, int] | None]:
        """Anchor quotes need ``min_quote_tokens`` (8) tokens; shorter evidence quotes (table cells,
        state names) must match exactly (case-insensitive), never fuzzily."""
        q = normalise_quote(quote or "")
        n_tok = quote_tokens(q)
        if n_tok == 0 or (min_tokens is not None and n_tok < min_tokens):
            return False, 0.0, "quote_too_short", None
        i = self.hay.find(q)
        if i >= 0:
            return True, 1.0, None, (i, i + len(q))
        if n_tok < self.rules.min_quote_tokens:
            j = self.hay_lower.find(q.lower())
            return (True, 1.0, None, (j, j + len(q))) if j >= 0 else (False, 0.0, "short_quote_not_found", None)
        windows: list[tuple[int, int]] = []
        if page is not None and self.doc.pages:
            near = [p for p in self.doc.pages if abs(p.number - page) <= 1]
            if near:
                windows.append((min(p.char_start for p in near), max(p.char_end for p in near)))
        windows.append((0, len(self.hay)))
        best = 0.0
        for ws, we in windows:
            hay = self.hay_lower[ws:we]
            if len(q) > len(hay):
                continue
            al = fuzz.partial_ratio_alignment(q.lower(), hay)
            if al is None:
                continue
            best = max(best, al.score / 100)
            if al.score >= self.theta_q * 100:
                return True, al.score / 100, None, (ws + al.dest_start, ws + al.dest_end)
        return False, best, "not_found", None

    def g2(self, quote: str, page: int | None, section: str | None) -> tuple[bool, list[str]]:
        r = verify_anchor(self.doc, quote or "", page, section or "", self.rules)
        return r.ok, list(r.reasons)

    def context(self, span: tuple[int, int] | None) -> str | None:
        if span is None:
            return None
        a, b = span
        return self.hay[max(0, a - CONTEXT_CHARS): min(len(self.hay), b + CONTEXT_CHARS)].strip()


def _norm_key(q: str) -> str:
    return " ".join(normalise_quote(q or "").lower().split())


def quote_checks(f: dict[str, Any], finder: QuoteFinder) -> list[QuoteCheck]:
    """G1/G2 on every distinct quote of a finding: its anchor quotes and its doc-evidence quotes."""
    out: list[QuoteCheck] = []
    seen: set[str] = set()
    for i, a in enumerate(f.get("doc_anchors", [])):
        k = _norm_key(a.get("quote", ""))
        if k in seen:
            continue
        seen.add(k)
        ok, score, reason, span = finder.g1(a.get("quote", ""), a.get("page"),
                                            min_tokens=finder.rules.min_quote_tokens)
        g2, reasons = finder.g2(a.get("quote", ""), a.get("page"), a.get("section_ref"))
        out.append(QuoteCheck(f["id"], f"anchor[{i}]", a.get("quote", ""), ok, score, reason, g2, reasons, span))
    for e in f.get("evidence", []):
        if e.get("source_type") != "doc" or not e.get("quote"):
            continue
        k = _norm_key(e["quote"])
        if k in seen:
            continue
        seen.add(k)
        m = _DOC_CITE.search(e.get("url_or_citation") or "")
        page = int(m.group("page")) if m else None
        section = m.group("section") if m and m.group("section") else None
        ok, score, reason, span = finder.g1(e["quote"], page)
        g2, reasons = (finder.g2(e["quote"], page, section) if page is not None else (None, []))
        out.append(QuoteCheck(f["id"], f"evidence:{e.get('evidence_id')}", e["quote"], ok, score, reason, g2,
                              reasons, span))
    return out


# ----------------------------------------------------------------------------- citations, step 1


def citation_provenance(review: dict[str, Any], f: dict[str, Any], finder: QuoteFinder) -> list[dict[str, Any]]:
    """Per evidence item of the finding: existence/provenance label and source-type correctness."""
    ledger = {e["evidence_id"]: e for e in review.get("evidence_ledger", [])}
    rows = []
    for e in f.get("evidence", []):
        led = ledger.get(e.get("evidence_id"))
        st = e.get("source_type")
        label = None
        if st == "external":
            if led is None or led.get("source_type") != "external" or not led.get("tool"):
                label = "FABRICATED"
            elif led.get("read_before_cite"):
                label = "READ"
            else:
                label = "EXISTS_NOT_READ"
        if st == "doc":
            correct = bool(e.get("quote")) and finder.g1(e["quote"])[0]
        elif st == "external":
            correct = led is not None and led.get("source_type") == "external" and bool(led.get("tool"))
        else:
            der = e.get("derived_from") or []
            correct = bool(der) and all(d in ledger for d in der)
        rows.append({"finding_id": f["id"], "evidence_id": e.get("evidence_id"), "source_type": st,
                     "in_ledger": led is not None, "external_label": label, "source_type_correct": correct,
                     "supports_claim": e.get("supports_claim")})
    return rows


def _passage(review: dict[str, Any], e: dict[str, Any], finder: QuoteFinder, depth: int = 0) -> str:
    ledger = {x["evidence_id"]: x for x in review.get("evidence_ledger", [])}
    st = e.get("source_type")
    if st == "doc":
        ok, _, _, span = finder.g1(e.get("quote") or "")
        ctx = finder.context(span) if ok else None
        return ctx or f"(this quote was not found in the document) {e.get('quote')}"
    if st == "external":
        led = ledger.get(e.get("evidence_id")) or {}
        return led.get("excerpt") or e.get("quote") or "(no passage recorded)"
    parts = [f"inference: {e.get('quote')}"]
    if depth < 2:
        for d in e.get("derived_from") or []:
            src = ledger.get(d)
            if src is not None:
                parts.append(f"derived from {d}: " + _passage(review, {**src, "quote": src.get("excerpt")}, finder,
                                                               depth + 1))
    return "\n".join(parts)


# ----------------------------------------------------------------------------- judge calls


@dataclass
class GroundingResult:
    quotes: list[QuoteCheck]
    provenance: list[dict[str, Any]]
    premise: dict[str, dict[str, Any]]          # finding_id -> answer or {"ok": False}
    citation: dict[str, dict[str, Any]]         # finding_id -> {"ok", "items": [{evidence_id, support}]}
    recommendation: dict[str, dict[str, Any]]   # finding_id -> answer
    judges_on: bool
    recommendation_judge_on: bool
    failures: list[str] = field(default_factory=list)
    finder: QuoteFinder | None = None


async def run_grounding(review: dict[str, Any], findings: list[FindingView], finder: QuoteFinder,
                        runner: JudgeRunner | None, *, judges: bool, recommendation_judge: bool,
                        doc_text: str) -> GroundingResult:
    quotes = [q for f in findings for q in quote_checks(f.data, finder)]
    prov = [r for f in findings for r in citation_provenance(review, f.data, finder)]
    failures: list[str] = []
    premise: dict[str, dict[str, Any]] = {}
    citation: dict[str, dict[str, Any]] = {}
    rec: dict[str, dict[str, Any]] = {}

    async def ask(kind: str, purpose: str, system: str, user: str) -> dict[str, Any]:
        assert runner is not None
        try:
            return {"ok": True, **(await runner.ask(kind, purpose, system, user))}
        except BudgetStop:
            raise
        except JudgeError as exc:
            failures.append(f"{purpose}: {str(exc)[:200]}")
            return {"ok": False, "error": str(exc)[:300]}

    async def premise_one(f: FindingView) -> None:
        user = prompts.render("premise_user", DOCUMENT=doc_text, FINDING=render_finding(f.data, finder.doc))
        premise[f.id] = await ask("premise", f"ground.premise:{f.id}", prompts.template("premise_system"), user)

    async def cite_one(f: FindingView) -> None:
        items = [e for e in f.data.get("evidence", []) if e.get("supports_claim")]
        if not items:
            citation[f.id] = {"ok": True, "items": [], "note": "no supporting evidence items"}
            return
        ev = "\n".join(json.dumps({"evidence_id": e.get("evidence_id"), "source_type": e.get("source_type"),
                                   "cited_text": e.get("quote"), "passage": _passage(review, e, finder)},
                                  ensure_ascii=False, indent=1) for e in items)
        ans = await ask("citation", f"ground.cite:{f.id}", prompts.template("citation_system"),
                        prompts.render("citation_user", CLAIM=f.data.get("statement", ""), EVIDENCE=ev))
        if ans.get("ok"):
            want = {e.get("evidence_id") for e in items}
            got = {i["evidence_id"]: i for i in ans.get("items", []) if i.get("evidence_id") in want}
            missing = sorted(want - set(got))
            if missing:
                failures.append(f"ground.cite:{f.id}: no label for {missing}")
            ans = {"ok": True, "items": list(got.values()), "missing": missing}
        citation[f.id] = ans

    async def rec_one(f: FindingView) -> None:
        r = f.data.get("recommendation")
        if not r:
            return
        objectives = "\n".join(f"- {ref}" for ref in r.get("objective_refs", [])) or "(none)"
        body = json.dumps({k: r.get(k) for k in ("issue", "rationale", "change_summary", "expected_benefit",
                                                  "objective_refs")}, ensure_ascii=False, indent=1)
        rec[f.id] = await ask("recommendation", f"rec:{f.id}", prompts.template("recommendation_system"),
                              prompts.render("recommendation_user", RECOMMENDATION=body, OBJECTIVES=objectives))

    jobs = []
    if judges and runner is not None:
        jobs += [premise_one(f) for f in findings] + [cite_one(f) for f in findings]
    if recommendation_judge and runner is not None:
        jobs += [rec_one(f) for f in findings]
    await asyncio.gather(*jobs)
    return GroundingResult(quotes=quotes, provenance=prov, premise=premise, citation=citation, recommendation=rec,
                           judges_on=judges, recommendation_judge_on=recommendation_judge, failures=failures,
                           finder=finder)
