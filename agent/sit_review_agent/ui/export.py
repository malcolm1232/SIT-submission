"""The finished review as one self-contained HTML file (decision #36, 2026-10-03).

The review part is the run's own ``report.md``, written by ``report.render.render_markdown`` (the one
renderer of a review), converted to HTML by markdown-it in CommonMark mode with tables. No second
renderer of the review exists: the export cannot say anything ``report.md`` does not
(``tests/test_ui_outputs.py`` checks its finding text against ``report.json``). Raw HTML in the
Markdown is escaped and images are off, so model text cannot add markup or make the file load
anything. ``tokens.css`` and ``export.css`` are inlined; the file loads no external resource. A
replayed run carries the "replayed evidence" stamp, as on the page. When ``ui/chat.jsonl`` exists,
its turns follow in a separate section headed :data:`CHAT_HEADING`.

The sidebar (decision #43, 2026-10-04): the rendered report is cut at its own ``## `` headings into the
eight parts of :data:`GROUPS`. The page carries a sidebar of the parts and one fixed inline script
(:data:`NAV_JS`) that shows one part at a time; without script every section shows.

Cross-links (5 Oct 2026): every identifier a cold reader cannot resolve is a link (:mod:`.xref`): finding,
evidence, limitation, sound-area, research-question and registry ids, the document's own requirement and
principle ids, page and section references, ``[doc:...]`` anchors, the confidence number and the review's
vocabulary. The linking only wraps text that is there, so the review's words are unchanged; the targets the
review itself does not hold are in a reference part after the review, labelled as added by the export (how to
read the review, the decision registry, the evidence ledger, and the reviewed document's extracted text with
every quoted passage marked, so a reference resolves inside the one file even when it travels alone). The
zip (:func:`export_zip`) holds the page as ``index.html``, the reviewed PDF as :data:`PDF_NAME` when the run
can vouch for it (its SHA-256 matches the manifest), ``report.md`` and ``report.json``; each page of the
document text then links to its page of the PDF.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

from sit_review_agent.paths import repo_root
from sit_review_agent.report.render import APPENDIX_HEADING, SECTION_ORDER
from sit_review_agent.ui import chat
from sit_review_agent.ui.rundata import read_json
from sit_review_agent.ui.xref import Doc, Index

STATIC_DIR = Path(__file__).parent / "static"
CHAT_HEADING = "Reading-aid chat transcript (not part of the review)"
REPLAY_STAMP = "replayed evidence"
REPLAY_NOTE = ("This run was produced by dra replay from recorded model and tool calls; nothing was fetched or "
               "judged anew.")
ADDED = "added by the export"
PDF_NAME = "document.pdf"


@lru_cache(maxsize=1)
def _md() -> MarkdownIt:
    return MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False}).enable("table") \
        .disable("image")


@lru_cache(maxsize=1)
def _css() -> str:
    """``tokens.css`` without its ``@font-face`` (the page's vendored serif is a file beside it; the export
    loads nothing, so it falls back to the system serif of the same stack), then ``review.css`` (the review
    document, which the app's Review tab loads too) and ``export.css`` (the page around it)."""
    tokens = (STATIC_DIR / "tokens.css").read_text(encoding="utf-8")
    tokens = re.sub(r"@font-face\s*\{[^}]*\}\s*", "", tokens)
    return "\n".join((tokens, *((STATIC_DIR / n).read_text(encoding="utf-8") for n in ("review.css", "export.css"))))


def export_name(run_id: str) -> str:
    return f"{run_id}_review.html"


def review_html(report_md: str) -> str:
    """``report.md`` as HTML, raw HTML escaped, no images."""
    return _md().render(report_md)


def _turn(t: dict[str, Any]) -> str:
    at = str(t.get("at") or "")
    who = f"You · {at[:10]} {at[11:16]} UTC" if at else "You"
    out = [f'<div class="turn"><p class="who">{escape(who)}</p><p class="q">{escape(str(t.get("question") or ""))}</p>']
    cost = t.get("cost_usd")
    dur = t.get("duration_s")
    meta = "Review assistant · 1 model call" + (f", {dur:.1f} s" if isinstance(dur, int | float) else "") \
        + (f", ${cost:.2f}" if isinstance(cost, int | float) else ", cost unknown")
    out.append(f'<p class="who">{escape(meta)}</p>')
    shown = t.get("rendered_as")
    if shown == "answer":
        out.append(f'<p class="a">{escape(str(t.get("answer") or ""))}</p>')
        cites = ", ".join(str(c) for c in t.get("citations") or [])
        dropped = [str(d) for d in t.get("dropped") or []]
        foot = (f"Cites {cites}. " if cites else "") + (
            f"{len(dropped)} citation(s) did not resolve in this run and were dropped: {', '.join(dropped)}."
            if dropped else "Every citation resolves in this run.")
        out.append(f'<p class="foot">{escape(foot)}</p>')
    elif shown == "unsupported":
        out.append(f'<p class="a">{escape(chat.UNSUPPORTED_TEXT)}</p>')
        why = "; ".join(x for x in (str(t.get("unsupported_reason") or ""),
                                    "dropped, not in this run: " + ", ".join(t.get("dropped") or [])
                                    if t.get("dropped") else "") if x)
        if why:
            out.append(f'<p class="foot">{escape(why[0].upper() + why[1:])}.</p>')
    else:
        out.append(f'<p class="a">The call failed: {escape(str(t.get("error") or "unknown error"))}.</p>')
    out.append("</div>")
    return "".join(out)


def chat_section(run_dir: Path) -> str:
    """The chat turns, or ``""`` when the run has no ``ui/chat.jsonl``."""
    if not chat.log_path(run_dir).is_file():
        return ""
    turns = chat.history(run_dir)
    b = chat.budget(run_dir)
    note = (f"Questions asked on the review page and the Review assistant's answers ({b['model']}, effort "
            f"{b['effort']}), from {run_dir.name}/ui/chat.jsonl. A reading aid that answers only from this run's "
            "files; it is outside the evaluated agent, and nothing here changes the review above.")
    body = "".join(_turn(t) for t in turns) or "<p>No question was asked.</p>"
    return (f'<section class="chat-transcript"><h2>{escape(CHAT_HEADING)}</h2>'
            f'<p class="note">{escape(note)}</p>{body}</section>')


# ------------------------------------------------------------------ the parts of the sidebar (decision #43)

#: The eight groups of the sidebar: (slug, label, the report's ``## `` headings). A heading not named here
#: joins the group of the nearest named heading before it (or after it, when none comes before), so no part of
#: the report is ever dropped. The reference part the export adds is a ninth entry (:data:`REF_GROUP`).
GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("summary", "Summary and verdict", ("Design intent", "Fitness for purpose")),
    ("strengths", "Strengths", ("Strengths", "Areas where no change is needed")),
    ("risks", "Risks", ("Risks", "Risk register")),
    ("gaps", "Gaps", ("Gaps",)),
    ("ambiguities", "Ambiguities and assumptions", ("Ambiguities", "Unresolved assumptions")),
    ("what_to_do", "What to do", ("Validation needs", "Recommended refinements")),
    ("open_items", "Open items", ("Unresolved issues and next steps", "Evidence limitations")),
    ("traceability", "Traceability", ("Evidence register", "Review coverage", "Run details", CHAT_HEADING)),
)
REF_GROUP = len(GROUPS)                  # 0-based: the sidebar's ninth entry
REF_LABEL = "Reference"
INDEX_NAME = "index.html"
CHAT_NAV_LABEL = "Chat transcript (not part of the review)"
HEADINGS = dict(SECTION_ORDER)

#: The page's one script, ``static/xnav.js``: the run's Review tab in ``dra ui`` loads the same file, so the export
#: and the tab cannot drift apart. It hides and shows the sections already in the page, follows the in-page links with
#: a history entry each (so Back returns to the place the reader left, scroll position included, and a visible "Back
#: to where I was" does the same), opens a link's target in the side pane, previews a link's target on hover, and
#: marks the section in view in the sidebar. Without script every section shows and every link is a plain anchor.
NAV_JS = (STATIC_DIR / "xnav.js").read_text(encoding="utf-8").rstrip("\n")


#: The side pane the script fills with a link's target (hidden, and unused, without script).
PANE_HTML = ('<aside class="x-pane" role="dialog" aria-labelledby="x-pane-title" hidden>'
             '<div class="x-pane-bar">'
             '<button class="x-pane-nav x-pane-prev" type="button" aria-label="Back in the pane" title="Back">'
             "\u2190</button>"
             '<button class="x-pane-nav x-pane-next" type="button" aria-label="Forward in the pane" title="Forward">'
             "\u2192</button>"
             '<nav class="x-pane-crumb" aria-label="Path in the pane"></nav>'
             '<button class="x-pane-close" type="button" aria-label="Close the pane" title="Close (Esc)">'
             "\u00d7</button>"
             "</div>"
             '<div class="x-pane-head"><div class="x-pane-kicker"></div>'
             '<h2 class="x-pane-title" id="x-pane-title" tabindex="-1"></h2>'
             '<div class="x-pane-actions"><button class="x-pane-show" type="button">Show in the report</button>'
             '<a class="x-pane-pdf" target="_blank" rel="noopener" hidden></a></div></div>'
             '<div class="x-pane-body"></div></aside>')


class Section:
    """One ``## `` section of the rendered report: its heading text, its group and its HTML."""

    __slots__ = ("heading", "group", "html", "sid")

    def __init__(self, heading: str, group: int, html: str, sid: str) -> None:
        self.heading, self.group, self.html, self.sid = heading, group, html, sid


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def split_report(report_md: str) -> tuple[str, list[Section]]:
    """``report.md`` rendered once and cut at its own ``## `` headings: the part above the first one (the
    title and the verdict table) and each section with its group. The cut is of one token stream, so the
    preamble and the sections joined are exactly :func:`review_html`."""
    md = _md()
    env: dict[str, Any] = {}
    tokens = md.parse(report_md, env)
    cuts = [i for i, t in enumerate(tokens) if t.type == "heading_open" and t.tag == "h2" and t.level == 0]
    bounds = [*cuts, len(tokens)]
    preamble = md.renderer.render(tokens[:bounds[0]], md.options, env)
    known = {h: gi for gi, (_, _, heads) in enumerate(GROUPS) for h in heads}
    heads: list[str] = []
    for c in cuts:
        inline = tokens[c + 1]
        heads.append(one_line("".join(ch.content for ch in inline.children or [] if ch.type in ("text", "code_inline"))
                              or inline.content))
    groups: list[int | None] = [known.get(h) for h in heads]
    last: int | None = None
    for i, g in enumerate(groups):                       # nearest named heading before
        if g is None:
            groups[i] = last
        last = groups[i]
    first = next((g for g in groups if g is not None), 0)
    seen: dict[str, int] = {}
    sections = []
    for i, c in enumerate(cuts):
        sid = "s-" + _slug(heads[i])
        seen[sid] = seen.get(sid, 0) + 1
        if seen[sid] > 1:
            sid += f"-{seen[sid]}"
        g = groups[i]
        sections.append(Section(heads[i], first if g is None else g, md.renderer.render(tokens[c:bounds[i + 1]],
                                                                                         md.options, env), sid))
    return preamble, sections


def one_line(text: str) -> str:
    return " ".join(text.split())


# ------------------------------------------------------------------ structure around the review's words
# Each step below only adds attributes and wrapping elements; the text between the tags stays as rendered.

CARD_H3 = re.compile(r"<h3>((?:FND)-\d{3,}) ")
META_RE = re.compile(r"<ul>\n<li><strong>([a-z ]+)</strong>(.*?)</li>\n<li>Disposition: <strong>([a-z ]+)</strong>"
                     r"(.*?)</li>\n</ul>", re.S)
SEP = " · "
LINE_KINDS = (("Where: ", "where", "Where:"), ("Evidence ", "ev", "Evidence"),
              ("Recommendation: ", "rec", "Recommendation:"), ("Why no change is needed: ", "why",
                                                                 "Why no change is needed:"),
              ("Next step: ", "next", "Next step:"), ("Decision ", "dec", "Decision"),
              ("Since the previous version: ", "since", "Since the previous version:"))
VERDICT_WORDS = {"fit": "fit", "fit with conditions": "fit_with_conditions", "not fit": "not_fit",
                 "not assessed": "not_assessed"}


def _chip(href: str | None, cls: str, inner: str, idx: Index, family: str) -> str:
    if href is None:
        return f'<span class="chip {cls}">{inner}</span>'
    idx.count(family, True)
    return f'<a class="chip {cls}" href="{href}">{inner}</a>'


def _term_href(idx: Index, key: str) -> str | None:
    return f"#g-{key}" if key in idx.terms else None


def _meta(m: re.Match[str], idx: Index) -> str:
    kind, rest, disp, drest = m.group(1), m.group(2), m.group(3), m.group(4)
    kk = kind.replace(" ", "_")
    out = ['<ul class="x-meta"><li class="x-chips">',
           _chip(_term_href(idx, f"kind-{kk}"), f"kind kind-{kk}", f"<strong>{kind}</strong>", idx, "term")]
    for part in rest.split(SEP)[1:] if rest.startswith(SEP) else ([rest] if rest else []):
        out.append(f'<span class="x-sep">{SEP}</span>')
        sev = re.fullmatch(r"severity <strong>([a-z]+)</strong>", part)
        if sev:
            out.append(_chip(_term_href(idx, f"sev-{sev.group(1)}"), f"sev sev-{sev.group(1)}", part, idx, "term"))
        elif part.startswith("confidence "):
            band = re.search(r"\((\w+)\)", part)
            out.append(_chip("#g-confidence", f"conf conf-{band.group(1) if band else 'x'}", part, idx, "confidence"))
        elif part.startswith("rank "):
            out.append(_chip(_term_href(idx, "rank"), "rank", part, idx, "term"))
        else:
            out.append(_chip(_term_href(idx, "cat-" + part.replace(" ", "_")), "cat", part, idx, "term"))
    dk = disp.replace(" ", "_")
    out.append('</li>\n<li class="x-disp"><span class="x-lbl">Disposition:</span> '
               + _chip(_term_href(idx, f"disp-{dk}"), f"disp disp-{dk}", f"<strong>{disp}</strong>", idx, "term"))

    def also(a: re.Match[str]) -> str:
        words = a.group(1).split(", ")
        chips = [_chip(_term_href(idx, "disp-" + w.replace(" ", "_")), "disp disp-also", w, idx, "term") for w in words]
        return ' <span class="x-also">(also: ' + ", ".join(chips) + ")</span>"
    out.append(re.sub(r" \(also: ([a-z ,]+)\)", also, drest))
    out.append("</li>\n</ul>")
    return "".join(out)


def _lines(html: str) -> str:
    """The card's list lines get a class by their label, and the label a span."""
    def one(m: re.Match[str]) -> str:
        p, rest = m.group(1) or "", m.group(2)
        for prefix, cls, label in LINE_KINDS:
            if rest.startswith(prefix):
                body = rest[len(label):]
                if cls == "ev":
                    body = re.sub(r"^ (EV-\d{3,}) (\((?:doc|external|inference)(?: \([a-z ]+\))?, "
                                  r"(?:supports|contrary)\))",
                                  r' \1 <span class="x-tag">\2</span>', body)
                return f'<li class="x-{cls}">{p}<span class="x-lbl">{label}</span>{body}'
        return m.group(0)
    return re.sub(r"<li>(<p>)?((?:Where|Evidence|Recommendation|Why no change|Next step|Decision|Since the)[^<]*)",
                  one, html)


def _cards(html: str, idx: Index) -> str:
    """Each finding block (its ``### FND-nnn`` heading to the next heading) in an ``<article>`` with the
    finding's id; its first line of facts as chips."""
    parts = re.split(r"(?=<h3>)", html)
    out = [parts[0]]
    for p in parts[1:]:
        m = CARD_H3.match(p)
        tail = ""
        if m:
            cut = re.search(r"<h[12]>", p)
            if cut:
                p, tail = p[:cut.start()], p[cut.start():]
            f = idx.findings.get(m.group(1)) or {}
            kind = str(f.get("kind") or "")
            sev = str(f.get("severity") or "")
            p = META_RE.sub(lambda mm: _meta(mm, idx), p, count=1)
            p = _lines(p)
            p = p.replace(f"<h3>{m.group(1)} ", f'<h3><span class="x-fid">{m.group(1)}</span> ', 1)
            out.append(f'<article class="finding kind-{kind}{" sev-" + sev if sev else ""}" id="{m.group(1)}">{p}'
                       f"</article>{tail}")
        else:
            out.append(p)
    return "".join(out)


def _tables(html: str, idx: Index) -> str:
    """Tables scroll sideways on a narrow screen; a verdict word or a coverage criterion in a cell is a chip."""
    html = html.replace("<table>", '<div class="x-table"><table>').replace("</table>", "</table></div>")

    def cell(m: re.Match[str]) -> str:
        text = m.group(1)
        if text in VERDICT_WORDS:
            key = VERDICT_WORDS[text]
            return (f"<td>{_chip(_term_href(idx, f'verdict-{key}'), f'verdict verdict-{key}', text, idx, 'term')}"
                    "</td>")
        if f"crit-{text}" in idx.terms:
            return f'<td><a class="xref x-term x-crit" href="#g-crit-{text}">{text}</a></td>'
        return m.group(0)
    return re.sub(r"<td>([a-z_ ]+)</td>", cell, html)


def _ids(html: str, heading: str, idx: Index | None = None) -> str:
    """Ids for the review's own entries that other text cites: evidence register rows, limitations (DEG),
    sound areas (SA), research questions (RQ), and findings listed only in a table (the risk-register layout)."""
    html = re.sub(r"<tr>\n<td>(EV-\d{3,})</td>", r'<tr id="reg-\1">' + "\n<td>\\1</td>", html)
    html = re.sub(r"<li>(<p>)?(SA-\d{3,}) ", r'<li class="x-sa" id="\2">\1\2 ', html)
    html = re.sub(r"<li>(<p>)?(RQ-\d{3,}):", r'<li class="x-rq" id="\2">\1\2:', html)
    if heading == HEADINGS.get("limitations"):
        def deg(m: re.Match[str]) -> str:
            ids = re.findall(r"DEG-\d{3,}", m.group(3))
            extra = "".join(f'<span class="x-anchor" id="{i}"></span>' for i in ids[1:])
            return f'<li class="x-deg" id="{ids[0]}">{extra}{m.group(1) or ""}{m.group(2)}'
        html = re.sub(r"<li>(<p>)?((?:(?!</li>).)*?\((DEG-\d{3,}(?:, DEG-\d{3,})*)\)(?:</p>)?\n?</li>)", deg, html,
                      flags=re.S)
    if heading == HEADINGS.get("unresolved"):
        def disp(m: re.Match[str]) -> str:
            key = "disp-" + m.group(3).replace(" ", "_")
            word = (f'<a class="xref x-term" href="#g-{key}">{m.group(3)}</a>' if idx is not None and key in idx.terms
                    else m.group(3))
            if idx is not None and key in idx.terms:
                idx.count("term", True)
            return f"<li>{m.group(1) or ''}{m.group(2)} ({word}):"
        html = re.sub(r"<li>(<p>)?(FND-\d{3,}) \(([a-z ]+)\):", disp, html)
    if heading in ("Risk register",) or heading.startswith(APPENDIX_HEADING):
        html = re.sub(r"<tr>\n<td>(FND-\d{3,})</td>", r'<tr id="\1">' + "\n<td>\\1</td>", html)
    return html


def _preamble(html: str, idx: Index) -> str:
    """The title and the run table on top: the verdict as a chip, the vocabulary rows linked to the glossary."""
    def row(m: re.Match[str]) -> str:
        key = {"Tools used": "tools-used", "Tools disabled": "tools-disabled", "Reporting threshold": "threshold",
               "Verdict": None}.get(m.group(1))
        cell = m.group(2)
        if m.group(1) == "Verdict":
            cell = re.sub(r"<strong>([a-z ]+)</strong>", lambda v: _chip(
                _term_href(idx, "verdict-" + VERDICT_WORDS.get(v.group(1), "")),
                f"verdict verdict-{VERDICT_WORDS.get(v.group(1), 'x')}", f"<strong>{v.group(1)}</strong>", idx,
                "term"), cell, count=1)
            return f'<tr class="x-verdict-row">\n<td>{m.group(1)}</td>\n<td>{cell}</td>'
        if key and key in idx.terms:
            idx.count("term", True)
            return f'<tr>\n<td><a class="xref x-term" href="#g-{key}">{m.group(1)}</a></td>\n<td>{cell}</td>'
        return m.group(0)
    html = re.sub(r"<tr>\n<td>([A-Z][a-z ]+)</td>\n<td>(.*?)</td>", row, html)
    return html.replace("<table>", '<div class="x-table x-runtable"><table>', 1).replace(
        "</table>", "</table></div>", 1)


def _verdict_para(html: str, idx: Index) -> str:
    """The verdict paragraph opens with the label in bold: a chip to its glossary entry."""
    def lab(m: re.Match[str]) -> str:
        key = VERDICT_WORDS.get(m.group(1).lower())
        if not key:
            return m.group(0)
        return "<p>" + _chip(_term_href(idx, f"verdict-{key}"), f"verdict verdict-{key}",
                             f"<strong>{m.group(1)}</strong>", idx, "term")
    return re.sub(r"<p><strong>([A-Z][a-z ]+)</strong>", lab, html, count=1)


# ------------------------------------------------------------------ the reference part (added by the export)


def _entry(eid: str, title: str, body: str, src: str | None = None, cls: str = "") -> str:
    s = f'<p class="x-src">From <code>{escape(src)}</code></p>' if src else ""
    return f'<div class="x-entry{" " + cls if cls else ""}" id="{eid}"><h3>{title}</h3>{body}{s}</div>'


def _ref_head(sid: str, title: str, note: str) -> str:
    return (f'<section class="sec x-ref" data-g="{REF_GROUP + 1}" id="{sid}"><h2>{escape(title)} '
            f'<span class="x-added">{ADDED}</span></h2><p class="x-note">{note}</p>')


def _howto(idx: Index) -> str:
    t = idx.terms
    groups = [
        ("Confidence and rank", ["confidence", "rank"]),
        ("Verdict", [k for k in t if k.startswith("verdict-")]),
        ("Finding kinds", [k for k in t if k.startswith("kind-")]),
        ("Severity", [k for k in t if k.startswith("sev-")]),
        ("Disposition", [k for k in t if k.startswith("disp-")]),
        ("Defect categories", [k for k in t if k.startswith("cat-")]),
        ("The run table on top", ["threshold", "tools-used", "tools-disabled"]),
        ("Review coverage criteria (this run's configuration)", [k for k in t if k.startswith("crit-")]),
        ("Identifiers", [k for k in t if k.startswith("id-")]),
    ]
    out = [_ref_head("r-howto", "How to read this review",
                     "Not part of the review. The meaning of the review's own words, taken from the code and the "
                     "prompts the agent ran with (each entry names its source), and the abbreviations the reviewed "
                     "document defines.")]
    for title, keys in groups:
        keys = [k for k in keys if k in t]
        if not keys:
            continue
        out.append(f'<h3 class="x-group">{escape(title)}</h3><div class="x-grid">')
        for k in keys:
            term = t[k]
            body = term.html if term.html.startswith("<p>") else f"<p>{term.html}</p>"
            out.append(_entry(f"g-{k}", escape(term.label), body, term.src,
                              "x-term-entry x-wide" if k == "confidence" else "x-term-entry"))
        out.append("</div>")
    if idx.abbrs:
        out.append('<h3 class="x-group">Abbreviations the document defines</h3><div class="x-grid">')
        for ab, (exp, where) in sorted(idx.abbrs.items()):
            out.append(_entry(f"g-abbr-{ab}", escape(ab), f"<p>{escape(exp)}</p>",
                              f"the reviewed document, {where}" if where else "the reviewed document",
                              "x-term-entry"))
        out.append("</div>")
    out.append("</section>")
    return "".join(out)


def _place(idx: Index, a: dict[str, Any]) -> str:
    """A document anchor of report.json (page, section, quote) as a linked location and the quote."""
    page, sec, quote = a.get("page"), str(a.get("section_ref") or ""), str(a.get("quote") or "")
    doc = idx.by_doc.get(str(a.get("doc_id") or "")) or idx.doc
    loc = f"p.{page if page is not None else '-'} §{sec}" if sec else (f"p.{page}" if page else "")
    href = idx.location(str(page or ""), sec, quote, doc) if doc else None
    loc_html = idx.a(href, escape(loc), "x-loc", "page/section", idx._loc_title(str(page), sec)) if href else \
        escape(loc)
    q = f' <span class="x-q">&quot;{idx.link_ids(escape(quote))}&quot;</span>' if quote else ""
    return f'<p class="x-place"><span class="x-lbl">In the document:</span> {loc_html}{q}</p>'


def _cited_by(idx: Index, ident: str, field: str) -> str:
    refs: list[str] = []
    for fid, f in idx.findings.items():
        if field == "evidence":
            if any(str(e.get("evidence_id")) == ident for e in f.get("evidence") or [] if isinstance(e, dict)):
                refs.append(fid)
        else:
            for d in f.get("affected_decisions") or []:
                if isinstance(d, dict) and str(d.get("registry_id")) == ident:
                    refs.append(f"{fid} ({d.get('relation')})")
    for sid, s in idx.sound.items():
        if field == "evidence" and ident in (s.get("evidence_ids") or []):
            refs.append(sid)
    if not refs:
        return ""
    return f'<p class="x-cited"><span class="x-lbl">Cited by:</span> {idx.link_ids(escape(", ".join(refs)))}</p>'


def _registry(idx: Index) -> str:
    if not idx.registry:
        return ""
    out = [_ref_head("r-registry", "Decision registry",
                     "Not part of the review's text: the decisions, constraints and requirements the review "
                     "extracted from the document (this run's report.json, decision_registry) and checked each "
                     "finding against. A finding preserves, refines or challenges an entry.")]
    for rid, e in idx.registry.items():
        typ = str(e.get("type") or "").replace("_", " ")
        ref = str(e.get("doc_ref") or "")
        title = (f'<span class="x-eid">{escape(rid)}</span> <span class="chip reg reg-{escape(str(e.get("type")))}">'
                 f'{escape(typ)}</span> <span class="x-eref">{idx.link_ids(escape(ref))}</span>')
        body = f'<p>{idx.link_text(escape(str(e.get("statement") or "")))}</p>'
        if isinstance(e.get("doc_anchor"), dict):
            body += _place(idx, e["doc_anchor"])
        body += _cited_by(idx, rid, "decision")
        out.append(_entry(rid, title, body, cls="x-reg"))
    out.append("</section>")
    return "".join(out)


def _ledger(idx: Index) -> str:
    if not idx.ledger:
        return ""
    out = [_ref_head("r-ledger", "Evidence ledger",
                     "Not part of the review's text: every evidence item of this run (report.json, "
                     "evidence_ledger) with its excerpt, where it comes from and the findings that cite it. The "
                     "review's own Evidence register lists the same items in a table.")]
    for eid, e in idx.ledger.items():
        typ = str(e.get("source_type") or "")
        auth = str(e.get("authority") or "").replace("_", " ")
        title = (f'<span class="x-eid">{escape(eid)}</span> <span class="chip src src-{escape(typ)}">'
                 f'{escape(typ)}{" · " + escape(auth) if auth else ""}</span>')
        body = ""
        if e.get("excerpt"):
            body += f'<p class="x-q">&quot;{idx.link_ids(escape(str(e["excerpt"])))}&quot;</p>'
        cite = str(e.get("url_or_citation") or "")
        m = re.fullmatch(r"doc:([A-Za-z0-9_.-]+)#p(\d+)/s([0-9.]*[0-9])", cite)
        if m and (d := idx.by_doc.get(m.group(1))) is not None:
            href = idx.location(m.group(2), m.group(3), str(e.get("excerpt") or ""), d)
            loc = f"p.{m.group(2)} §{m.group(3)}"
            body += ('<p class="x-place"><span class="x-lbl">In the document:</span> '
                     + (idx.a(href, loc, "x-loc", "page/section", idx._loc_title(m.group(2), m.group(3)))
                        if href else loc) + f' <span class="x-muted">({escape(cite)})</span></p>')
        elif re.match(r"https?://", cite):
            body += (f'<p class="x-place"><span class="x-lbl">Source:</span> {escape(str(e.get("title") or cite))} '
                     f'<span class="x-muted">{escape(cite)}</span></p>')
        if e.get("derived_from"):
            body += ('<p class="x-place"><span class="x-lbl">Derived from:</span> '
                     + idx.link_ids(escape(", ".join(str(x) for x in e["derived_from"]))) + "</p>")
        body += _cited_by(idx, eid, "evidence")
        if f"reg-{eid}" in idx.targets:
            body += (f'<p class="x-cited"><a class="xref" href="#reg-{escape(eid)}">Its row in the Evidence register'
                     "</a></p>")
        out.append(_entry(eid, title, body, cls="x-ev-entry"))
    out.append("</section>")
    return "".join(out)


def _doc_pre(d: Doc, segs: list[tuple[int, int]], ps: int, pe: int, used: set[str]) -> str:
    """One page's text with the quoted passages marked and the section starts as anchors."""
    events: list[tuple[int, int, str]] = []
    for i, (s, e) in enumerate(segs):
        if e <= ps or s >= pe:
            continue
        mid = f"{d.prefix}-q{i + 1}"
        first = mid not in used
        used.add(mid)
        events.append((max(s, ps), 1, f'<mark{f" id={chr(34)}{mid}{chr(34)}" if first else ""}>'))
        events.append((min(e, pe), 0, "</mark>"))
    for sec in d.sections:
        try:
            cs = int(sec.get("char_start"))
        except (TypeError, ValueError):
            continue
        sid = str(sec.get("section_id") or "")
        if ps <= cs < pe and sid and f"{d.prefix}-s{sid}" not in used:
            used.add(f"{d.prefix}-s{sid}")
            lab = escape(f"§{sid} {sec.get('heading') or ''}".strip(), quote=True)
            events.append((cs, 2, f'<span class="doc-sec" id="{d.prefix}-s{sid}" data-label="{lab}"></span>'))
    events.sort(key=lambda x: (x[0], x[1]))
    out, pos, open_mark = [], ps, False
    for at, kind, tag in events:
        out.append(escape(d.text[pos:at], quote=False))
        pos = at
        if kind == 2 and open_mark:                      # a section start inside a passage: close and reopen
            out.append("</mark>" + tag + "<mark>")
            continue
        if kind in (0, 1):
            open_mark = kind == 1
        out.append(tag)
    out.append(escape(d.text[pos:pe], quote=False))
    return "".join(out).strip("\n")


def _doc_text(idx: Index, pdf_href: str | None) -> str:
    out: list[str] = []
    for d in idx.docs:
        segs = d.segments()
        # the same words wherever the page is shown (the zip, the server's export.html, the app's Review tab)
        pdf = ("Each page below links to the same page of the reviewed PDF." if pdf_href and d is idx.doc else
               "The PDF is not linked from here; the text below is what the review read.")
        out.append(_ref_head(f"{d.prefix}-text", f"The reviewed document: {d.title}" if d is idx.doc else
                             f"Document {d.doc_id}: {d.title}",
                             f"Not part of the review: the text of {escape(d.doc_id)} as the review read it, "
                             "extracted from the PDF (figures and images are not in it), page by page. Each "
                             "passage the review quotes is highlighted; page and section references in the review "
                             f"open here. {pdf}"))
        used: set[str] = set()
        for n, ps, pe in d.pages:
            link = (f'<a class="x-pdf" href="{escape(pdf_href)}#page={n}" target="_blank" rel="noopener">'
                    f"Open page {n} of the PDF</a>" if pdf_href and d is idx.doc else "")
            secs = [s for s in d.sections if isinstance(s.get("char_start"), int) and ps <= s["char_start"] < pe]
            label = f"Page {n}" + (f" · §{secs[0].get('section_id')} {secs[0].get('heading')}" if secs else "")
            out.append(f'<div class="doc-page" id="{d.prefix}-p{n}" data-label="{escape(f"Page {n} · {d.doc_id}")}">'
                       f'<div class="doc-page-head"><span>{escape(label)}</span>{link}</div>'
                       f'<pre class="doc-text">{_doc_pre(d, segs, ps, pe, used)}</pre></div>')
        out.append("</section>")
    return "".join(out)


# ------------------------------------------------------------------ the page


class _Run:
    """The export of one run: the header, the cut and linked report, the chat and the reference part."""

    def __init__(self, run_dir: Path, *, replayed: bool, exported_at: str | None, pdf_href: str | None,
                 with_chat: bool = True) -> None:
        report_md = (run_dir / "report.md").read_text(encoding="utf-8")
        report = read_json(run_dir / "report.json") or {}
        report = report if isinstance(report, dict) else {}
        docs = (report.get("metadata") or {}).get("documents") or []
        doc = next((d for d in docs if d.get("role") == "under_review"), docs[0] if docs else {})
        self.title = str(doc.get("title") or run_dir.name)
        when = exported_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.meta = f"Run {run_dir.name} · exported {when[:10]} {when[11:16]} UTC from dra ui"
        self.stamp = (f'<div class="stamp"><span class="pill">{escape(REPLAY_STAMP)}</span> {escape(REPLAY_NOTE)}'
                      "</div>" if replayed else "")
        preamble, self.sections = split_report(report_md)
        self.chat = chat_section(run_dir) if with_chat else ""
        self.chat_group = len(GROUPS) - 1
        self.index = idx = Index(run_dir, report, root=repo_root(), pdf_href=pdf_href)
        # 1. structure: cards, chips, ids (no text changes)
        pre = _preamble(preamble, idx)
        for s in self.sections:
            h = _cards(s.html, idx)
            h = _ids(_tables(h, idx), s.heading, idx)
            if s.heading == HEADINGS.get("verdict"):
                h = _verdict_para(h, idx)
            s.html = h
        # 2. the targets that exist: what the page now holds, and the reference entries
        for h in [pre, *(s.html for s in self.sections)]:
            for ident in re.findall(r'id="((?:FND|DEG|SA|RQ)-\d{3,})"', h):
                idx.declare(ident)
            for ident in re.findall(r'id="reg-(EV-\d{3,})"', h):
                idx.declare(f"reg-{ident}")
                if ident not in idx.ledger:
                    idx.declare(ident, f"#reg-{ident}")
        for eid in idx.ledger:
            idx.declare(eid)
        for rid in idx.registry:
            idx.declare(rid)
        # 3. the reference entries, then the review's text linked, then the document text with every mark
        self.ref = [_howto(idx), _registry(idx), _ledger(idx)]
        self.preamble = idx.link_html(pre)
        self.chat = idx.link_html(self.chat)          # the chat's citations too; its words stay as they are
        for s in self.sections:
            s.html = idx.link_html(s.html)
        self.ref.append(_doc_text(idx, pdf_href))
        self.preamble = idx.resolve(self.preamble)
        for s in self.sections:
            s.html = idx.resolve(s.html)
        self.ref = [idx.resolve(r) for r in self.ref if r]
        self.pdf_href = pdf_href

    def head(self) -> str:
        return ("<!doctype html>\n"
                '<html lang="en" class="export-doc rv"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<meta name="color-scheme" content="light dark">'
                f"<title>{escape('Design review: ' + self.title)}</title>"
                f"<style>\n{_css()}\n</style></head>")

    def header(self, note: str) -> str:
        return (f'<header class="exp-head"><div class="brand">SIT design review</div>'
                f'<div class="meta">{escape(self.meta)}</div>{self.stamp}<p class="note">{note}</p></header>')

    def report(self, tag: str = "main") -> str:
        """The preamble and every section: the review's own words, linked."""
        return (f'<{tag} class="report">\n<div class="pre">{self.preamble}</div>'
                + "".join(f'<section class="sec" data-g="{s.group + 1}" id="{s.sid}">{s.html}</section>'
                          for s in self.sections) + f"</{tag}>")

    def reference(self) -> str:
        return f'<div class="x-reference">{"".join(self.ref)}</div>'

    def body(self) -> str:
        """The preamble, then every section, then the chat section, then the reference part."""
        chat_part = (f'<div class="sec" data-g="{self.chat_group + 1}" id="s-chat">{self.chat}</div>' if self.chat
                     else "")
        return self.report() + chat_part + self.reference()

    def fragment(self) -> str:
        """The review as the run's Review tab in ``dra ui`` shows it: the same report and reference part as
        :meth:`body` (the chat has its own panel there), a slim table of contents of the same parts, the way back
        and the side pane; no script (the tab runs ``static/xnav.js``, this page's own) and no header (the app
        has its own)."""
        return (f'<div class="rv" id="rv"><div class="rv-grid"><div class="rv-doc">{self.report("div")}'
                f"{self.reference()}</div>{self.nav(slim=True)}</div>"
                f'<a class="x-back" href="#" hidden>Back to where I was</a>{PANE_HTML}</div>')

    def nav(self, *, slim: bool = False) -> str:
        """The sidebar of the parts, each with its headings. ``slim``: the app's in-tab table of contents, every
        section shown at once, so no brand, no "All sections" and no entry for a part without a section."""
        out = ['<nav class="toc" aria-label="Parts of the review"><div class="toc-inner">']
        if not slim:
            out.append('<div class="toc-brand">SIT review<span class="ai">.</span></div>'
                       '<div class="toc-group">Parts</div>'
                       '<a class="toc-item" href="#top" data-g="all"><span class="num"></span>'
                       '<span class="label">All sections</span></a>')
        for gi, (_, label, _) in enumerate(GROUPS):
            mine = [(s.sid, s.heading) for s in self.sections if s.group == gi]
            if self.chat and gi == self.chat_group:
                mine.append(("s-chat", CHAT_NAV_LABEL))
            if mine or not slim:
                out.append(self._nav_entry(gi, label, mine))
        refs = [(sid, title) for sid, title in re.findall(r'<section class="sec x-ref" data-g="\d+" id="([^"]+)">'
                                                          r"<h2>(.*?) <span", "".join(self.ref))]
        if refs:
            out.append(f'<div class="toc-group">{escape(ADDED.capitalize())}</div>')
            out.append(self._nav_entry(REF_GROUP, REF_LABEL, refs))
        out.append("</div></nav>")
        return "".join(out)

    @staticmethod
    def _nav_entry(gi: int, label: str, mine: list[tuple[str, str]]) -> str:
        g = str(gi + 1)
        target = f"#{mine[0][0]}" if mine else "#top"
        return (f'<div class="toc-entry"><a class="toc-item" href="{target}" data-g="{g}">'
                f'<span class="num">{g}</span><span class="label">{escape(label)}</span></a>'
                '<ul class="toc-heads">' + "".join(f'<li><a href="#{sid}" data-g="{g}">{escape(h)}</a></li>'
                                                   for sid, h in mine) + "</ul></div>")

    def index_page(self) -> str:
        note = ("The review below is this run's report.md as dra review wrote it, shown as HTML. Its identifiers, "
                "page and section references are links; the Reference part that follows was "
                f'<a href="#r-howto">{ADDED}</a> and is not part of the review. report.md and report.json are the '
                "review's own files.")
        return (f'{self.head()}<body id="top"><div class="layout">{self.nav()}<div class="wrap">'
                f"{self.header(note)}{self.body()}</div></div>"
                '<a class="x-back" href="#" hidden>Back to where I was</a>'
                f"{PANE_HTML}"
                f"<script>{NAV_JS}</script></body></html>\n")


def export_html(run_dir: Path, *, replayed: bool, exported_at: str | None = None,
                pdf_href: str | None = None) -> str:
    """The export of ``run_dir`` as one page. ``pdf_href`` is where the reviewed PDF sits beside the page
    (:data:`PDF_NAME` in the zip, ``doc.pdf`` on the server); ``None`` for a file sent on its own, whose page
    and section references then resolve to the document text inside it. Raises ``FileNotFoundError`` when the
    run has no ``report.md``."""
    return _Run(run_dir, replayed=replayed, exported_at=exported_at, pdf_href=pdf_href).index_page()


def review_fragment(run_dir: Path, *, pdf_href: str | None) -> str:
    """The run's Review tab in ``dra ui`` (:meth:`_Run.fragment`): the same renderer and linker as
    :func:`export_html`, so the tab and the export say the same words with the same links. ``pdf_href`` is the
    app's own ``/runs/<id>/doc.pdf`` (or ``None`` when the run cannot vouch for its PDF). Raises
    ``FileNotFoundError`` when the run has no ``report.md``."""
    return _Run(run_dir, replayed=False, exported_at=None, pdf_href=pdf_href, with_chat=False).fragment()


def link_counts(run_dir: Path, *, pdf_href: str | None = None) -> dict[str, list[int]]:
    """Per family, [mentions, links] the export made of ``run_dir`` (for the preview's tally)."""
    return _Run(run_dir, replayed=False, exported_at=None, pdf_href=pdf_href).index.counts


def bundle_name(run_id: str) -> str:
    return f"{run_id}_review.zip"


def bundle_names(run_dir: Path, pdf: Path | None = None) -> list[str]:
    """The names in the bundle, in order."""
    return [INDEX_NAME, *([PDF_NAME] if pdf is not None else []),
            *(n for n in ("report.md", "report.json") if (run_dir / n).is_file())]


def export_zip(run_dir: Path, *, replayed: bool, exported_at: str | None = None, pdf: Path | None = None) -> bytes:
    """The bundle: the page as ``index.html``, the reviewed PDF as :data:`PDF_NAME` when given (the caller
    passes only the one whose SHA-256 the manifest vouches for), and the run's own ``report.md`` and
    ``report.json`` byte for byte."""
    import io
    import zipfile

    html = export_html(run_dir, replayed=replayed, exported_at=exported_at,
                       pdf_href=PDF_NAME if pdf is not None else None)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(INDEX_NAME, html)
        if pdf is not None:
            z.write(pdf, PDF_NAME)
        for name in ("report.md", "report.json"):
            if (run_dir / name).is_file():
                z.writestr(name, (run_dir / name).read_bytes())
    return buf.getvalue()

