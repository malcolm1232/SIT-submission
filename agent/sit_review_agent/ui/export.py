"""The finished review as one self-contained HTML file (decision #36, 2026-10-03).

The review part is the run's own ``report.md``, written by ``report.render.render_markdown`` (the one
renderer of a review), converted to HTML by markdown-it in CommonMark mode with tables. No second
renderer of the review exists: the export cannot say anything ``report.md`` does not
(``tests/test_ui_outputs.py`` checks its finding text against ``report.json``). Raw HTML in the
Markdown is escaped and images are off, so model text cannot add markup or make the file load
anything. ``tokens.css`` and ``export.css`` are inlined; the file loads no external resource. A
replayed run carries the "replayed evidence" stamp, as on the page. When ``ui/chat.jsonl`` exists,
its turns follow in a separate section headed :data:`CHAT_HEADING`.

The bundle (decision #43, 2026-10-04): the rendered report is cut at its own ``## `` headings into
the eight parts of :data:`GROUPS`. The single page carries a sidebar of the parts and one fixed
inline script (:data:`NAV_JS`) that shows one part at a time; without script every section shows.
Each part is also a standalone file with no script (:data:`PART_NAMES`), and :func:`export_zip`
holds the page as ``index.html``, the eight parts, ``report.md`` and ``report.json``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

from sit_review_agent.ui import chat
from sit_review_agent.ui.rundata import read_json

STATIC_DIR = Path(__file__).parent / "static"
CHAT_HEADING = "Reading-aid chat transcript (not part of the review)"
REPLAY_STAMP = "replayed evidence"
REPLAY_NOTE = ("This run was produced by dra replay from recorded model and tool calls; nothing was fetched or "
               "judged anew.")


@lru_cache(maxsize=1)
def _md() -> MarkdownIt:
    return MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False}).enable("table") \
        .disable("image")


@lru_cache(maxsize=1)
def _css() -> str:
    """``tokens.css`` without its ``@font-face`` (the page's vendored serif is a file beside it; the export
    loads nothing, so it falls back to the system serif of the same stack), then ``export.css``."""
    tokens = (STATIC_DIR / "tokens.css").read_text(encoding="utf-8")
    tokens = re.sub(r"@font-face\s*\{[^}]*\}\s*", "", tokens)
    return "\n".join((tokens, (STATIC_DIR / "export.css").read_text(encoding="utf-8")))


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




# ------------------------------------------------------------------ the bundle (decision #43, 2026-10-04)

#: The eight groups of the sidebar and of the standalone files: (slug, label, the report's ``## `` headings).
#: A heading not named here joins the group of the nearest named heading before it (or after it, when none
#: comes before), so no part of the report is ever dropped.
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
PART_NAMES: tuple[str, ...] = tuple(f"{i + 1:02d}_{slug}.html" for i, (slug, _, _) in enumerate(GROUPS))
INDEX_NAME = "index.html"
CHAT_NAV_LABEL = "Chat transcript (not part of the review)"

#: The sidebar page's one script. It only hides and shows the sections already in the page; before it runs
#: (or without script) every section shows, so the file reads the same as the plain export.
NAV_JS = """(function () {
  var secs = document.querySelectorAll(".sec"), items = document.querySelectorAll(".toc-item");
  function show(g, top) {
    for (var i = 0; i < secs.length; i++) secs[i].hidden = g !== "all" && secs[i].getAttribute("data-g") !== g;
    for (var j = 0; j < items.length; j++) items[j].classList.toggle("active", items[j].getAttribute("data-g") === g);
    if (top) window.scrollTo(0, 0);
  }
  document.querySelector(".toc").addEventListener("click", function (e) {
    var a = e.target.closest("a[data-g]");
    if (!a) return;
    var g = a.getAttribute("data-g");
    if (!a.classList.contains("toc-item")) { show(g, false); return; }
    e.preventDefault();
    show(g, true);
    try { history.replaceState(null, "", g === "all" ? location.pathname + location.search : "#g" + g); } catch (x) {}
  });
  function route() {
    var h = location.hash, m = /^#g(\\d)$/.exec(h), t = h.length > 1 ? document.getElementById(h.slice(1)) : null;
    var sec = t && t.closest(".sec");
    if (m) show(m[1], true);
    else if (sec) { show(sec.getAttribute("data-g"), false); t.scrollIntoView(); }
    else show("all", false);
  }
  window.addEventListener("hashchange", route);
  route();
})();"""


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


class _Run:
    """What every page of one export shares: the title, the header and the cut report."""

    def __init__(self, run_dir: Path, *, replayed: bool, exported_at: str | None) -> None:
        report_md = (run_dir / "report.md").read_text(encoding="utf-8")
        report = read_json(run_dir / "report.json") or {}
        docs = ((report.get("metadata") or {}).get("documents") or []) if isinstance(report, dict) else []
        doc = next((d for d in docs if d.get("role") == "under_review"), docs[0] if docs else {})
        self.title = str(doc.get("title") or run_dir.name)
        when = exported_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.meta = f"Run {run_dir.name} · exported {when[:10]} {when[11:16]} UTC from dra ui"
        self.stamp = (f'<div class="stamp"><span class="pill">{escape(REPLAY_STAMP)}</span> {escape(REPLAY_NOTE)}'
                      "</div>" if replayed else "")
        self.preamble, self.sections = split_report(report_md)
        self.chat = chat_section(run_dir)
        self.chat_group = len(GROUPS) - 1

    def head(self) -> str:
        return ("<!doctype html>\n"
                '<html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                f"<title>{escape('Design review: ' + self.title)}</title>"
                f"<style>\n{_css()}\n</style></head>")

    def header(self, note: str, extra: str = "") -> str:
        return (f'<header class="exp-head"><div class="brand">SIT design review</div>'
                f'<div class="meta">{escape(self.meta)}</div>{self.stamp}<p class="note">{escape(note)}</p>'
                f"{extra}</header>")

    def body(self, group: int | None) -> str:
        """The preamble, then the sections (of one group, or all), then the chat section when in view."""
        out = [f'<main class="report">\n<div class="pre">{self.preamble}</div>']
        for s in self.sections:
            if group is None or s.group == group:
                out.append(f'<section class="sec" data-g="{s.group + 1}" id="{s.sid}">{s.html}</section>')
        if group is not None and not any(s.group == group for s in self.sections) and not (
                self.chat and group == self.chat_group):
            out.append('<p class="empty">This run\'s report.md has no section in this part.</p>')
        out.append("</main>")
        if self.chat and group in (None, self.chat_group):
            out.append(f'<div class="sec" data-g="{self.chat_group + 1}" id="s-chat">{self.chat}</div>')
        return "".join(out)

    def nav(self, links: str | None) -> str:
        out = ['<nav class="toc" aria-label="Parts of the review"><div class="toc-inner">'
               '<div class="toc-brand">SIT review<span class="ai">.</span></div>'
               '<div class="toc-group">Parts</div>'
               '<a class="toc-item" href="#top" data-g="all"><span class="num"></span>'
               '<span class="label">All sections</span></a>']
        for gi, (_, label, _) in enumerate(GROUPS):
            mine = [(s.sid, s.heading) for s in self.sections if s.group == gi]
            if self.chat and gi == self.chat_group:
                mine.append(("s-chat", CHAT_NAV_LABEL))
            g = str(gi + 1)
            target = f"#{mine[0][0]}" if mine else "#top"
            out.append(f'<div class="toc-entry"><a class="toc-item" href="{target}" data-g="{g}">'
                       f'<span class="num">{g}</span><span class="label">{escape(label)}</span></a>')
            if links is not None:
                out.append(f'<a class="toc-file" href="{escape(links + PART_NAMES[gi])}" '
                           f'title="{escape(PART_NAMES[gi])}">this section only</a>')
            out.append('<ul class="toc-heads">' + "".join(
                f'<li><a href="#{sid}" data-g="{g}">{escape(h)}</a></li>' for sid, h in mine) + "</ul></div>")
        out.append("</div></nav>")
        return "".join(out)

    def index_page(self, links: str | None) -> str:
        note = ("The review below is this run's report.md as dra review wrote it, shown as HTML. "
                "report.md and report.json are the review's own files.")
        return (f'{self.head()}<body id="top"><div class="layout">{self.nav(links)}<div class="wrap">'
                f"{self.header(note)}{self.body(None)}</div></div><script>{NAV_JS}</script></body></html>\n")

    def part_page(self, group: int) -> str:
        label = GROUPS[group][1]
        note = (f"Part {group + 1} of {len(GROUPS)} of this run's report.md as dra review wrote it, shown as "
                "HTML: the title and the verdict, then the sections of this part only.")
        extra = (f'<p class="part">{escape(label)} · <a href="{INDEX_NAME}">the full review</a> holds every '
                 "part</p>")
        return (f'{self.head()}<body id="top"><div class="wrap">{self.header(note, extra)}{self.body(group)}'
                "</div></body></html>\n")


def export_html(run_dir: Path, *, replayed: bool, exported_at: str | None = None,
                part_links: str | None = None) -> str:
    """The export of ``run_dir`` as one page with the sidebar of :data:`GROUPS`. ``part_links`` is the prefix
    of each part's "this section only" link (``""`` beside the part files, ``"export/"`` on the server);
    ``None`` leaves the links out, for a file sent on its own. Raises ``FileNotFoundError`` when the run has
    no ``report.md``."""
    return _Run(run_dir, replayed=replayed, exported_at=exported_at).index_page(part_links)


def export_part(run_dir: Path, name: str, *, replayed: bool, exported_at: str | None = None) -> str:
    """One standalone file of the bundle by its name (one of :data:`PART_NAMES`, or :data:`INDEX_NAME` for
    the sidebar page linking to its neighbours). Raises ``KeyError`` for any other name."""
    if name != INDEX_NAME and name not in PART_NAMES:
        raise KeyError(name)
    run = _Run(run_dir, replayed=replayed, exported_at=exported_at)
    return run.index_page("") if name == INDEX_NAME else run.part_page(PART_NAMES.index(name))


def bundle_name(run_id: str) -> str:
    return f"{run_id}_review.zip"


def bundle_names(run_dir: Path) -> list[str]:
    """The names in the bundle, in order."""
    return [INDEX_NAME, *PART_NAMES, *(n for n in ("report.md", "report.json") if (run_dir / n).is_file())]


def export_zip(run_dir: Path, *, replayed: bool, exported_at: str | None = None) -> bytes:
    """The bundle: the sidebar page as ``index.html``, the eight part files, and the run's own ``report.md``
    and ``report.json`` byte for byte."""
    import io
    import zipfile

    run = _Run(run_dir, replayed=replayed, exported_at=exported_at)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(INDEX_NAME, run.index_page(""))
        for gi, name in enumerate(PART_NAMES):
            z.writestr(name, run.part_page(gi))
        for name in ("report.md", "report.json"):
            if (run_dir / name).is_file():
                z.writestr(name, (run_dir / name).read_bytes())
    return buf.getvalue()
