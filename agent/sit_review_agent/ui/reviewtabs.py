"""What the run view shows around the review document, drawn with the export's own linker (:class:`.xref.Index`).

* The counts on top (:func:`counts_strip`): every number of ``rundata.counts`` (findings, each severity, strengths,
  areas checked with no issue, unresolved items, limitations) as a link to its list in the reference part
  (:func:`counts_section`), and a "?" beside it to the word's entry in "How to read this review". A list holds
  exactly the items its number counts, from the same lists of ``report.json``; a zero opens too and says so.
* The Coverage tab (:func:`coverage_view`): what the grid is and what its codes mean (from ``report.coverage`` and
  the coverage outcomes ``prompts/assess.md`` defines), then the criteria by section, each cell with findings a link
  to the list of them, and the outcome of each criterion.
* The Evidence tab (:func:`evidence_view`): the evidence ledger, one row per item, the whole row a link to its entry
  in the reference part, so it previews on hover and on keyboard focus and opens in the side pane on a click.

Every id, page and section reference in them is linked by the same :class:`~.xref.Index` that links the review, so
the hover card and the pane are the Review tab's. Nothing here adds to or changes the review's words: the counts are
chrome in the header of the exported page and in the run head of the app, and the lists are reference material.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from html import escape
from pathlib import Path
from typing import Any

from sit_review_agent.ui.rundata import SEVERITIES, count_lists
from sit_review_agent.ui.xref import Index, term_text

COUNTS_ID = "r-counts"
COUNTS_TITLE = "The counts on top"
#: The counts strip, in its order: (count key, the words after the number, the list's id, the glossary key).
COUNT_ITEMS: tuple[tuple[str, str, str, str], ...] = (
    ("findings", "findings", "n-findings", "count-findings"),
    *((s, s, f"n-{s}", f"sev-{s}") for s in SEVERITIES),
    ("strengths", "strengths", "n-strengths", "kind-strength"),
    ("sound_areas", "areas checked, no issue", "n-sound", "count-sound"),
    ("unresolved", "unresolved", "n-unresolved", "count-unresolved"),
    ("limitations", "limitations", "n-limitations", "count-limitations"),
)
NONE_TEXT = "None in this run."
NONE_CELL = '<span class="x-muted">none</span>'

RefHead = Callable[[str, str, str], str]
Entry = Callable[..., str]


def _chip(idx: Index, key: str, cls: str, text: str) -> str:
    if key not in idx.terms:
        return f'<span class="chip {cls}">{escape(text)}</span>'
    idx.count("term", True)
    return f'<a class="chip {cls}" href="#g-{escape(key)}">{escape(text)}</a>'


def _id_link(idx: Index, ident: str, cls: str) -> str:
    href = idx.targets.get(ident)
    return f'<a class="xref {cls}" href="{escape(href)}">{escape(ident)}</a>' if href else escape(ident)


def _finding_chips(idx: Index, f: dict[str, Any]) -> str:
    kind, sev, disp = str(f.get("kind") or ""), str(f.get("severity") or ""), str(f.get("disposition") or "")
    out = []
    if kind == "strength":
        out.append(_chip(idx, "kind-strength", "kind-strength", "strength"))
    else:
        if kind:
            out.append(_chip(idx, f"kind-{kind}", f"kind kind-{kind}", kind.replace("_", " ")))
        if sev:
            out.append(_chip(idx, f"sev-{sev}", f"sev sev-{sev}", sev))
    if disp:
        out.append(_chip(idx, f"disp-{disp}", f"disp disp-{disp}", disp.replace("_", " ")))
    return "".join(out)


def finding_rows(idx: Index, findings: list[dict[str, Any]]) -> str:
    """One row per finding, in rank order: its id and title as one link to its card, then its chips."""
    rows = []
    for f in sorted(findings, key=lambda f: (f.get("rank") if isinstance(f.get("rank"), int) else 10**6)):
        fid, title = str(f.get("id") or ""), str(f.get("title") or "")
        href = idx.targets.get(fid)
        head = (f'<span class="x-rid">{escape(fid)}</span> {escape(title)}')
        link = f'<a class="xref x-row-link" href="{escape(href)}">{head}</a>' if href else head
        rows.append(f'<li class="x-row" data-id="{escape(fid)}">{link}'
                    f'<span class="x-row-chips">{_finding_chips(idx, f)}</span></li>')
    return f'<ul class="x-rows">{"".join(rows)}</ul>'


def counts_strip(idx: Index) -> str:
    """The counts as controls: the number and its words open the list, the "?" opens the word's definition."""
    n = {k: len(v) for k, v in count_lists(idx.report).items()}
    parts = []
    for key, words, list_id, term in COUNT_ITEMS:
        q = ""
        if term in idx.terms:
            label = idx.terms[term].label
            q = (f'<a class="xref x-count-q" href="#g-{term}" '
                 f'aria-label="What {escape(words)} means ({escape(label)})">?</a>')
        zero = " data-zero" if not n[key] else ""
        parts.append(f'<span class="x-count" data-count="{key}"{zero}><a class="xref x-count-n" href="#{list_id}">'
                     f'<b>{n[key]}</b> {escape(words)}</a>{q}</span>')
    return f'<nav class="x-counts" aria-label="This review in numbers">{"".join(parts)}</nav>'


def _definition(idx: Index, term: str, words: str) -> str:
    """The word's meaning, as the glossary has it (its first paragraph), and where that entry and its source are."""
    t = idx.terms.get(term)
    if t is None:
        return ""
    text = term_text(t)
    if not text["paras"]:
        return ""
    return (f'<p class="x-def"><span class="x-lbl">What {escape(words)} means</span> {escape(text["paras"][0])}</p>'
            f'<p class="x-src">From <a class="xref" href="#g-{term}">How to read this review</a>, '
            f"<code>{escape(t.src)}</code></p>")


def counts_section(idx: Index, ref_head: RefHead, entry: Entry) -> str:
    """One entry per count: the definition of its word, then exactly the items it counts."""
    lists = count_lists(idx.report)
    out = [ref_head(COUNTS_ID, COUNTS_TITLE,
                    "Not part of the review's text: each number above the review, with the items it counts, from "
                    "this run's report.json. The severities count the findings that are not strengths.")]
    out.append('<div class="x-grid x-counts-grid">')
    for key, words, list_id, term in COUNT_ITEMS:
        items = lists[key]
        body = _definition(idx, term, words)
        if not items:
            body += f'<p class="x-none">{NONE_TEXT}</p>'
        elif key in ("findings", "strengths", *SEVERITIES):
            body += finding_rows(idx, items)
        elif key == "sound_areas":
            body += '<ul class="x-rows">' + "".join(_sound_row(idx, s) for s in items) + "</ul>"
        elif key == "unresolved":
            body += '<ul class="x-rows">' + "".join(_unresolved_row(idx, u) for u in items) + "</ul>"
        else:
            body += '<ul class="x-rows">' + "".join(
                f'<li class="x-row">{idx.link_text(escape(str(lim.get("text") or "")))}</li>' for lim in items
            ) + "</ul>"
        out.append(entry(list_id, f"{len(items)} {escape(words)}", body, cls="x-count-entry x-wide",
                         kicker=COUNTS_TITLE))
    out.append("</div></section>")
    return "".join(out)


def _sections(idx: Index, refs: list[Any]) -> str:
    links = []
    for r in refs:
        sid = str(r)
        href = idx.section_href(sid)
        links.append(idx.a(href, f"§{escape(sid)}", "x-loc", "section", idx._sec_title(sid)) if href
                     else f"§{escape(sid)}")
    return ", ".join(links)


def _sound_row(idx: Index, s: dict[str, Any]) -> str:
    sid = str(s.get("id") or "")
    secs = _sections(idx, list(s.get("section_refs") or []))
    why = idx.link_text(escape(str(s.get("why_sound") or "")))
    return (f'<li class="x-row">{_id_link(idx, sid, "x-sa")}{" " + secs if secs else ""}'
            f'<span class="x-row-text">{why}</span></li>')


def _unresolved_row(idx: Index, u: dict[str, Any]) -> str:
    text = idx.link_text(escape(str(u.get("text") or "")))
    step = u.get("next_step") if isinstance(u.get("next_step"), dict) else None
    nxt = (f'<span class="x-row-text"><span class="x-lbl">Next step:</span> {escape(str(step.get("owner") or ""))}: '
           f'{idx.link_text(escape(str(step.get("action") or "")))}</span>' if step else "")
    return f'<li class="x-row">{text}{nxt}</li>'


# ------------------------------------------------------------------ the Coverage tab

def coverage_view(idx: Index, run_dir: Path) -> str:
    from sit_review_agent.report.coverage import build_coverage

    cm = build_coverage(run_dir).as_dict()
    crit = list(cm.get("criteria") or [])
    out = ['<section class="x-tab x-coverage" aria-labelledby="cov-title">',
           '<h2 id="cov-title">Coverage: the review criteria against the document\'s sections</h2>',
           _coverage_intro(idx)]
    head = "".join(f"<th>{_crit_link(idx, c)}</th>" for c in crit)
    rows, store = [], []
    for r in cm.get("rows") or []:
        sec = str(r.get("section") or "")
        href = idx.section_href(sec)
        name = f"§{escape(sec)} {escape(str(r.get('heading') or ''))}".strip()
        first = idx.a(href, name, "x-loc", "section", idx._sec_title(sec)) if href else name
        cells = []
        for c in crit:
            code = str((r.get("cells") or {}).get(c) or "")
            fids = [str(x) for x in (r.get("findings") or {}).get(c) or []]
            if fids:
                eid = f"cv-{_slug(sec)}-{_slug(c)}"
                store.append(_cell_entry(idx, eid, name, c, fids))
                cells.append(f'<td class="cv-hit"><a class="xref x-cell" href="#{eid}">{escape(code)}</a></td>')
            else:
                cls = "cv-ok" if code == "ok" else "cv-none"
                cells.append(f'<td class="{cls}">{escape(code)}</td>')
        sas = ", ".join(_id_link(idx, str(s), "x-sa") for s in r.get("sound_areas") or [])
        rows.append(f"<tr><th scope=\"row\">{first}</th>{''.join(cells)}<td>{sas}</td></tr>")
    out.append('<div class="x-table cv-grid"><table><thead><tr><th>Section</th>'
               f'{head}<th>SA</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    out.append('<h3>Outcome per criterion</h3><div class="x-table"><table><thead><tr><th>Criterion</th>'
               "<th>Outcome</th><th>Findings</th><th>Note</th></tr></thead><tbody>")
    for c in crit:
        outcome = str((cm.get("outcomes") or {}).get(c) or "")
        word = escape(outcome.replace("_", " "))
        fids = ", ".join(_id_link(idx, str(f), "x-fnd") for f in (cm.get("criterion_findings") or {}).get(c) or [])
        note = idx.link_text(escape(str((cm.get("notes") or {}).get(c) or "")))
        out.append(f'<tr><td>{_crit_link(idx, c)}</td><td><span class="cv-out cv-out-{escape(outcome)}">{word}</span>'
                   f'</td><td>{fids or NONE_CELL}</td><td>{note}</td></tr>')
    out.append("</tbody></table></div>")
    if store:
        out.append(f'<div class="cv-store" hidden>{"".join(store)}</div>')
    out.append("</section>")
    return "".join(out)


def _slug(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in s)


def _crit_link(idx: Index, c: str) -> str:
    return (f'<a class="xref x-term x-crit" href="#g-crit-{escape(c)}">{escape(c)}</a>' if f"crit-{c}" in idx.terms
            else escape(c))


def _cell_entry(idx: Index, eid: str, section: str, crit: str, fids: list[str]) -> str:
    """The list a coverage cell opens; ``section`` is already escaped."""
    found = [idx.findings[f] for f in fids if f in idx.findings]
    rows = finding_rows(idx, found) if found else ""
    missing = [f for f in fids if f not in idx.findings]
    extra = (f'<p class="x-muted">Not in the report: {escape(", ".join(missing))}</p>' if missing else "")
    return (f'<div class="x-entry x-cell-entry" id="{eid}" data-kicker="Coverage"><h3>{section} · {escape(crit)}</h3>'
            f'<p class="x-def">{len(fids)} finding(s) for the criterion {escape(crit)} anchored in this section.</p>'
            f"{rows}{extra}</div>")


def _coverage_intro(idx: Index) -> str:
    """What the grid is and what each code and outcome means: the coverage map's own legend, cut into its codes,
    and the coverage outcomes as ``prompts/assess.md`` asks the model for them."""
    from sit_review_agent.report import coverage

    outcomes = []
    for key, word in (("cov-findings", "findings"), ("cov-no_issue", "checked, no issue"),
                      ("cov-not_applicable", "not applicable")):
        t = idx.terms.get(key)
        if t is not None:
            text = term_text(t)["paras"][0]
            what = re.search(r"\((.*)\)", text)                # the outcome's own words, inside the definition
            what_text = (what.group(1)[0].upper() + what.group(1)[1:] + ".") if what else text
            outcomes.append(f"<dt>{escape(word)}</dt><dd>{escape(what_text)}</dd>")
    src = next((idx.terms[k].src for k in ("cov-findings", "cov-no_issue") if k in idx.terms), "prompts/assess.md")
    codes = "".join(f"<dt><code>{escape(k)}</code></dt><dd>{escape(v)}</dd>" for k, v in _legend(coverage.LEGEND))
    return ('<div class="cv-intro"><p>Each column is one review criterion of this run\'s configuration (its question '
            'opens from the column head), each row one section of the reviewed document, its subsections counted '
            "with it. A cell says what the review found for that criterion in that section; a cell with findings "
            "opens the list of them.</p>"
            f'<div class="cv-legend"><div><h3>The codes in a cell</h3><dl>{codes}</dl>'
            '<p class="x-src">From <code>agent/sit_review_agent/report/coverage.py</code></p></div>'
            f'<div><h3>Each criterion\'s outcome</h3><dl>{"".join(outcomes)}</dl>'
            f'<p class="x-src">From <code>{escape(src)}</code></p></div></div></div>')


def _legend(text: str) -> list[tuple[str, str]]:
    """``coverage.LEGEND`` cut at its codes: ``nX = ...; ok = ...; ? = ...; - = ...; SA = ...``."""
    parts = re.split(r"(?:^|; )(nX|ok|\?|-|SA) = ", text)
    return [(parts[i], parts[i + 1].strip().rstrip(";")) for i in range(1, len(parts) - 1, 2)]


# ------------------------------------------------------------------ the Evidence tab

def evidence_view(idx: Index) -> str:
    rows = []
    for eid, e in idx.ledger.items():
        typ = str(e.get("source_type") or "")
        auth = str(e.get("authority") or "").replace("_", " ")
        href = idx.targets.get(eid)
        ident = (f'<a class="xref x-ev x-rowlink" href="{escape(href)}" aria-label="{escape(eid)}: open its entry">'
                 f"{escape(eid)}</a>" if href else escape(eid))
        cite = str(e.get("url_or_citation") or "")
        derived = ", ".join(_id_link(idx, str(x), "x-ev") for x in e.get("derived_from") or [])
        where = (f'<span class="x-muted">drawn from</span> {derived}' if typ == "inference" and derived
                 else _ev_where(idx, e, cite))
        # a passage of the reviewed document: its ids and its section and page references link, as in the review's
        # own quotes; an outside source's excerpt keeps its references to its own sections as plain text
        raw = escape(str(e.get("excerpt") or ""))
        excerpt = idx.link_text(raw, quotes=False) if typ == "doc" else idx.link_ids(raw)
        cited = _cited(idx, eid)
        rows.append(f'<tr class="ev-row"><td>{ident}</td><td><span class="chip src src-{escape(typ)}">{escape(typ)}'
                    f'{" · " + escape(auth) if auth else ""}</span></td><td>{where}</td><td>{excerpt}</td>'
                    f"<td>{cited}</td></tr>")
    return ('<section class="x-tab x-evidence" aria-labelledby="ev-title"><h2 id="ev-title">Evidence register '
            f'<span class="x-n">{len(idx.ledger)}</span></h2>'
            '<p class="x-note">Every evidence item of this run (report.json, evidence_ledger). Hover a row, or move to '
            "it with the keyboard, to read its entry; click it to open the entry beside the list.</p>"
            '<div class="x-table ev-grid"><table><thead><tr><th>ID</th><th>Source</th><th>Where</th><th>Excerpt</th>'
            f'<th>Cited by</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>')


def _ev_where(idx: Index, e: dict[str, Any], cite: str) -> str:
    m = re.fullmatch(r"doc:([A-Za-z0-9_.-]+)#p(\d+)/s([0-9.]*[0-9])", cite)
    if m and (d := idx.by_doc.get(m.group(1))) is not None:
        href = idx.location(m.group(2), m.group(3), str(e.get("excerpt") or ""), d)
        loc = f"p.{m.group(2)} §{m.group(3)}"
        return idx.a(href, loc, "x-loc", "page/section", idx._loc_title(m.group(2), m.group(3))) if href else loc
    # an outside source: its title, then its address as text (as its entry in the reference part says it; an address
    # a tool returned is not made a link here); a tool call's citation, its ids linked. Both wrap in their column.
    if re.match(r"https?://", cite):
        title = str(e.get("title") or "")
        return (f'<span class="x-ev-where">{f"{escape(title)} " if title else ""}'
                f'<span class="x-muted x-url">{escape(cite)}</span></span>')
    return f'<span class="x-ev-where x-muted">{idx.link_ids(escape(cite))}</span>' if cite else ""


def _cited(idx: Index, eid: str) -> str:
    """The findings that cite the item, each with what the item does for it (supports or contrary, as the finding's
    evidence line says), and the sound areas that cite it."""
    refs = []
    for fid, f in idx.findings.items():
        ev = next((x for x in f.get("evidence") or []
                   if isinstance(x, dict) and str(x.get("evidence_id")) == eid), None)
        if ev is not None:
            rel = {True: " (supports)", False: " (contrary)"}.get(ev.get("supports_claim"), "")
            refs.append(f'<span class="x-nw">{_id_link(idx, fid, "x-fnd")}{rel}</span>')
    for sid, s in idx.sound.items():
        if eid in (s.get("evidence_ids") or []):
            refs.append(_id_link(idx, sid, "x-sa"))
    return ", ".join(refs) or NONE_CELL
