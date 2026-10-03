"""The finished review as one self-contained HTML file (decision #36, 2026-10-03).

The review part is the run's own ``report.md``, written by ``report.render.render_markdown`` (the one
renderer of a review), converted to HTML by markdown-it in CommonMark mode with tables. No second
renderer of the review exists: the export cannot say anything ``report.md`` does not
(``tests/test_ui_outputs.py`` checks its finding text against ``report.json``). Raw HTML in the
Markdown is escaped and images are off, so model text cannot add markup or make the file load
anything. ``tokens.css`` and ``export.css`` are inlined; the file has no script and no external
resource. A replayed run carries the "replayed evidence" stamp, as on the page. When
``ui/chat.jsonl`` exists, its turns follow in a separate section headed :data:`CHAT_HEADING`.
"""

from __future__ import annotations

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
    return "\n".join((STATIC_DIR / n).read_text(encoding="utf-8") for n in ("tokens.css", "export.css"))


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


def export_html(run_dir: Path, *, replayed: bool, exported_at: str | None = None) -> str:
    """The export of ``run_dir``. Raises ``FileNotFoundError`` when it has no ``report.md``."""
    report_md = (run_dir / "report.md").read_text(encoding="utf-8")
    report = read_json(run_dir / "report.json") or {}
    docs = ((report.get("metadata") or {}).get("documents") or []) if isinstance(report, dict) else []
    doc = next((d for d in docs if d.get("role") == "under_review"), docs[0] if docs else {})
    title = str(doc.get("title") or run_dir.name)
    when = exported_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = f"Run {run_dir.name} · exported {when[:10]} {when[11:16]} UTC from dra ui"
    stamp = (f'<div class="stamp"><span class="pill">{escape(REPLAY_STAMP)}</span> {escape(REPLAY_NOTE)}</div>'
             if replayed else "")
    note = ("The review below is this run's report.md as dra review wrote it, shown as HTML. "
            "report.md and report.json are the review's own files.")
    return ("<!doctype html>\n"
            '<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{escape('Design review: ' + title)}</title>"
            f"<style>\n{_css()}\n</style></head><body><div class=\"wrap\">"
            f'<header class="exp-head"><div class="brand">SIT design review</div>'
            f'<div class="meta">{escape(meta)}</div>{stamp}<p class="note">{escape(note)}</p></header>'
            f'<main class="report">\n{review_html(report_md)}</main>'
            f"{chat_section(run_dir)}"
            "</div></body></html>\n")
