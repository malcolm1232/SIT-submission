"""Outside sources in the evidence, as the page shows them (6 Oct 2026, Malcolm: "outside links in evidence should be
clickable").

An evidence ledger entry's ``url_or_citation`` (``models.py`` ``LedgerEntry``; hydrated into each finding's evidence
item) is one of: a place in the reviewed document (``doc:...``), an inference (``inference:...``), the web address a
tool returned for an outside source, or a tool call's own citation (``mcp:<server>/<tool>?<json args>``, written by
``tools/sources.py`` when a call gave no page of its own). Only the third is a web address.

* :func:`web_url` is the one test of "a true web address": an absolute ``http:`` or ``https:`` URL with a host and no
  space or control character. Anything else (``javascript:``, ``data:``, ``file:``, a relative path, a tool citation)
  is never made a link.
* :func:`source_link` draws one as a link that opens in a new tab with no referrer and no access to this page
  (``target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"``): the source's title with its host
  after it ("Token lifetimes · example.org"), or, with no title, the address itself shortened by an ellipsis
  between its start and its end; the full address is the link's tooltip. The page never fetches, prefetches or
  runs the address: it is an ``href`` the reader may follow, nothing more.
* :func:`tool_citation` draws a tool call's citation as what it is, the tool and its query in words.
* :func:`safe_outside_links` is for the review's own HTML (``report.md`` rendered by markdown-it, whose evidence
  register makes an outside source's title a Markdown link): every link to outside the page gets the same
  attributes, and one whose address is not a true web address is unwrapped to its text. The words do not change.

These addresses come from tool results, not from the reader, so everything is escaped.
"""

from __future__ import annotations

import json
import re
from html import escape, unescape
from typing import Any
from urllib.parse import urlsplit

#: The attributes of every link to an outside source: a new tab, no referrer, no handle on this page.
OUT_ATTRS = 'target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"'
#: An address with no title is shown at most this many characters long, an ellipsis between its start and end.
SHORT = 64
#: The argument a tool citation is about, in the order looked for.
QUERY_KEYS = ("query", "q", "question", "url", "urls")
TOOL_RE = re.compile(r"mcp:([^/?\s]+)/([^?\s]+)(?:\?(.*))?", re.S)
_BAD = re.compile(r"[\s\x00-\x1f\x7f]")


def web_url(value: Any) -> str | None:
    """``value`` when it is an absolute ``http:`` or ``https:`` address with a host, else ``None``."""
    if not isinstance(value, str) or not value or _BAD.search(value):
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not host or not value.lower().startswith(("http://",
                                                                                                    "https://")):
        return None
    return value


def host_of(url: str) -> str:
    """The address's host, without a leading ``www.``."""
    host = urlsplit(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def short_address(url: str, limit: int = SHORT) -> str:
    """The address without its scheme, at most ``limit`` characters: its start (the host first), an ellipsis, its
    end."""
    bare = re.sub(r"^https?://", "", url, flags=re.I).rstrip("/")
    if len(bare) <= limit:
        return bare
    head = max(len(host_of(url)) + 1, limit // 2)
    head = min(head, limit - 12)
    return bare[:head] + "…" + bare[-(limit - head - 1):]


def source_link(url: str, title: str | None = None) -> str:
    """The outside source ``url`` as a link: its title and host, or its shortened address. ``url`` must have passed
    :func:`web_url`; the caller shows anything else as text."""
    title = " ".join(str(title or "").split())
    host = host_of(url)
    if title:
        inner = f'<span class="x-out-title">{escape(title)}</span> <span class="x-out-host">· {escape(host)}</span>'
    else:
        inner = f'<span class="x-out-addr">{escape(short_address(url))}</span>'
    href = escape(url, quote=True)
    return f'<a class="x-out" href="{href}" {OUT_ATTRS} title="{href}">{inner}</a>'


def tool_parts(cite: str) -> tuple[str, str, str | None, list[tuple[str, str]]] | None:
    """A tool call's citation as (server, tool, query, the other arguments), or ``None`` when ``cite`` is not one."""
    m = TOOL_RE.fullmatch(cite.strip())
    if not m:
        return None
    server, tool, raw = m.group(1), m.group(2), m.group(3)
    query: str | None = None
    rest: list[tuple[str, str]] = []
    try:
        args = json.loads(raw) if raw else {}
    except ValueError:
        args = None
    if isinstance(args, dict):
        key = next((k for k in QUERY_KEYS if k in args), None)
        if key is not None:
            v = args[key]
            query = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
        rest = [(str(k), v if isinstance(v, str) else json.dumps(v)) for k, v in args.items() if k != key]
    elif raw:
        query = raw
    return server, tool, query, rest


def tool_citation(cite: str) -> str | None:
    """A tool call's citation in words: the tool, its server, its query in quotes and its other arguments; the
    citation whole is the tooltip. ``None`` when ``cite`` is not a tool citation."""
    parts = tool_parts(cite)
    if parts is None:
        return None
    server, tool, query, rest = parts
    out = [f'<span class="x-tool-name">{escape(tool)}</span> <span class="x-tool-srv">on {escape(server)}</span>']
    if query is not None:
        out.append(f': <span class="x-tool-q">“{escape(query)}”</span>')
    if rest:
        out.append(' <span class="x-tool-args">(' + ", ".join(f"{escape(k)} {escape(v)}" for k, v in rest)
                   + ")</span>")
    return f'<span class="x-tool" title="{escape(cite, quote=True)}">{"".join(out)}</span>'


A_RE = re.compile(r'<a href="([^"]*)"((?: title="[^"]*")?)>(.*?)</a>', re.S)


def safe_outside_links(html: str) -> str:
    """The links markdown-it drew in the review (``<a href="...">`` with no class: the page's own links all carry
    one) to outside the page: a true web address opens in a new tab with no referrer; any other address is dropped
    and its text kept. An in-page ``#`` link is left as it is."""
    def one(m: re.Match[str]) -> str:
        href, title, inner = m.group(1), m.group(2), m.group(3)
        if href.startswith("#"):
            return m.group(0)
        url = web_url(unescape(href))
        if url is None:
            return inner
        tip = title or f' title="{escape(url, quote=True)}"'
        host = host_of(url)
        shown = "" if host in unescape(re.sub(r"<[^>]*>", "", inner)) else f' data-host="{escape(host, quote=True)}"'
        return f'<a class="x-out x-out-inline" href="{href}" {OUT_ATTRS}{tip}{shown}>{inner}</a>'
    return A_RE.sub(one, html)


#: An outside address cited in a finding's evidence line (``report.md.j2``: ``... [<citation>]``), in the rendered (so
#: escaped) HTML: the review's own words, so the address stays as written and only becomes a link.
CITE_RE = re.compile(r"\[(https?://[^\s\[\]<>\"]+)\]", re.I)


def link_cited_addresses(html: str) -> str:
    """Each ``[https://...]`` citation in ``html`` (rendered HTML) with its address a link, the brackets and the
    words kept."""
    def one(m: re.Match[str]) -> str:
        url = web_url(unescape(m.group(1)))
        if url is None:
            return m.group(0)
        return (f'[<a class="x-out x-out-inline" href="{escape(url, quote=True)}" {OUT_ATTRS} '
                f'title="{escape(url, quote=True)}">{m.group(1)}</a>]')
    return CITE_RE.sub(one, html)
