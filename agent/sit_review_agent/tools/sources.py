"""Turning tool results into evidence-ledger entries.

Each MCP server returns results in its own shape (search hits, scholarly records, page text).
:func:`extract_sources` normalises one :class:`~sit_review_agent.tools.gateway.ToolResult` into
:class:`ExternalSource` items; the research phase writes one ledger entry per item
(:meth:`~sit_review_agent.state.evidence_ledger.EvidenceLedger.add_external`) and shows the model
the result text prefixed with the new ``EV-nnn`` IDs, so the model can only cite what it has seen.

The result shapes of the lab servers are UNVERIFIED until the laptop probe records real results
(ADR-008), so the parser is shape-tolerant: structured content or JSON text first (a list of
records, or a dict holding one under ``results``/``items``/``works``/...), then plain text
(numbered hits with ``URL:`` lines, Markdown links, bare URLs), and a fetched page (a call whose
arguments name a URL) becomes one source read in full.
"""

from __future__ import annotations

import functools
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sit_review_agent.config import AuthorityHosts
from sit_review_agent.models import SourceAuthority
from sit_review_agent.tools.gateway import ToolResult
from sit_review_agent.tools.inband import TEXT_KEYS, inband_failure

#: Excerpt kept in the ledger and shown next to the ID (the full payload stays in tools.jsonl).
EXCERPT_CHARS = 600
#: At most this many sources are registered from one result (oversized lists, INF-16).
MAX_SOURCES_PER_RESULT = 20

_URL_RE = re.compile(r"https?://[^\s<>\"'`\])}]+", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\[([^\]]{2,300})\]\((https?://[^)\s]+)\)")
_LIST_KEYS = ("results", "items", "hits", "data", "works", "papers", "records", "entries", "organic",
              "organic_results", "web", "documents", "references", "articles", "matches")
_URL_KEYS = ("url", "link", "href", "landing_page_url", "pdf_url", "uri", "source_url", "page_url")
_TITLE_KEYS = ("title", "name", "display_name", "headline")
_SNIPPET_KEYS = ("snippet", "description", "body", "abstract", "summary", "excerpt", "content", "text", "tldr")
_SCHOLARLY_KEYS = ("doi", "venue", "journal", "authors", "authorships", "publication_year", "year",
                   "host_venue", "primary_location", "citationCount", "cited_by_count", "externalIds", "arxiv_id")
_FETCH_TOOL_WORDS = ("fetch", "get_page", "read_url", "scrape", "navigate", "extract", "download", "open_url",
                     "browse", "crawl", "page_content", "get_content")
_FETCH_ARG_KEYS = ("url", "uri", "href", "link", "page_url", "target_url", "address", "source_url")
#: DOI prefixes of preprint servers (not peer reviewed): arXiv, bioRxiv/medRxiv, SSRN, Research Square.
_PREPRINT_DOI_PREFIXES = ("10.48550/", "10.1101/", "10.2139/", "10.21203/")


@dataclass(frozen=True)
class ExternalSource:
    url_or_citation: str
    title: str | None
    excerpt: str                        # the snippet as the agent saw it
    content: str                        # full fetched content if read, else the excerpt
    authority: SourceAuthority
    read_in_full: bool                  # -> LedgerEntry.read_before_cite


# ------------------------------------------------------------------------------ extraction


def extract_sources(result: ToolResult, hosts: AuthorityHosts | None = None) -> list[ExternalSource]:
    """Server-specific parsing of search hits / records / fetched pages (UNVERIFIED shapes until
    the laptop probe records real results). Authority is classified by domain heuristics.

    * Not ``ok`` or empty -> ``[]`` (failed calls never become evidence, INV-05).
    * A fetch (a URL-valued argument, or a fetch-like tool name with a URL in the text) -> one
      source, ``read_in_full=True``, content = the page text.
    * Records (JSON) -> one source per record; scholarly records (DOI, venue, authors, ...) are
      ``peer_reviewed`` unless the DOI or host is a preprint server, and count as read in full
      when they carry an abstract (the record is what is cited). Web hits are snippets
      (``read_in_full=False``): the agent must fetch the page before citing it (ADR-007
      ``read_before_cite``).
    * Plain text -> one source per URL found, titled by the preceding line or Markdown link text.
    * Anything else non-empty plain text -> one pseudo-citation ``mcp:<server>/<tool>?<args>``
      holding the text (``informal``), so whatever the model saw is still citable only by ID.
    * Excerpts are readable text, never a JSON dump: a search hit's excerpt is its title plus
      snippet; a fetched page's is a passage of its extracted text (:func:`_passage`). A JSON
      payload with no readable text, or one that reports a failure (``inband``), gives ``[]``.
    """
    if not result.ok:
        return []
    text = result.text or ""
    data = result.structured_content
    if isinstance(data, dict) and set(data) == {"result"}:      # MCPServer wraps a str return value
        inner = data["result"]
        data = inner if not isinstance(inner, str) else None
        text = inner if isinstance(inner, str) else text
    if data is None:
        data = _json_or_none(text)
    if not text.strip() and data is None:
        return []
    if data is not None and inband_failure(result.tool_name, data) is not None:
        return []

    fetch_url = _fetch_target(result.args)
    if fetch_url is None and any(w in result.tool_name.lower() for w in _FETCH_TOOL_WORDS):
        m = _URL_RE.search(text)
        fetch_url = m.group(0).rstrip(".,;:") if m else None
    if fetch_url is not None:
        if data is not None:
            return _from_pages(result.tool_name, data, fetch_url, hosts)[:MAX_SOURCES_PER_RESULT]
        return [ExternalSource(url_or_citation=fetch_url, title=_page_title(text, None), excerpt=_passage(text),
                               content=text, authority=classify_authority(fetch_url, hosts), read_in_full=True)]

    out: list[ExternalSource] = []
    if data is not None:
        for rec in _records(data):
            src = _from_record(rec, hosts)
            if src is not None:
                out.append(src)
    if not out and text.strip():
        out = _from_text(text, hosts)
    if not out and data is None:
        args = json.dumps(result.args, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        out = [ExternalSource(url_or_citation=f"mcp:{result.server}/{result.tool_name}?{args}",
                              title=f"{result.server} {result.tool_name} result", excerpt=_clip(text), content=text,
                              authority=SourceAuthority.INFORMAL, read_in_full=True)]
    seen: set[str] = set()
    unique: list[ExternalSource] = []
    for s in out:
        k = s.url_or_citation.rstrip("/").lower()
        if k not in seen:
            seen.add(k)
            unique.append(s)
    return unique[:MAX_SOURCES_PER_RESULT]


def _json_or_none(text: str) -> Any:
    t = text.strip()
    if not t or t[0] not in "[{":
        return None
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return None


def _clip(text: str, n: int = EXCERPT_CHARS) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _passage(text: str, n: int = EXCERPT_CHARS) -> str:
    """The first ``n`` characters of ``text`` (whitespace collapsed), cut back to the last sentence
    end when one falls in the second half; else clipped like :func:`_clip`."""
    t = re.sub(r"\s+", " ", text).strip()
    if len(t) <= n:
        return t
    head = t[:n]
    ends = [m.end() for m in re.finditer(r"[.!?][\"')\]]?(?=\s)", head)]
    if ends and ends[-1] >= n // 2:
        return head[: ends[-1]]
    return _clip(t, n)


def _page_text(d: dict[str, Any]) -> str | None:
    return _first_str(d, TEXT_KEYS)


def _from_pages(tool_name: str, data: Any, fetch_url: str, hosts: AuthorityHosts | None) -> list[ExternalSource]:
    """A fetched page given as JSON (one record, or a list of records with ``title``,
    ``final_url``, ``extracted_text``, ``status``): one source per record that carries readable
    text and does not report a failure. A record's own URL wins over the call's argument."""
    pages = [data] if isinstance(data, dict) and _page_text(data) else _records(data)
    if not pages and isinstance(data, list):
        pages = [d for d in data if isinstance(d, dict)]
    out: list[ExternalSource] = []
    for p in pages:
        body = _page_text(p)
        if body is None or inband_failure(tool_name, p) is not None:
            continue
        url = _first_str(p, ("final_url", *_URL_KEYS))
        url = url if url is not None and _URL_RE.fullmatch(url) else fetch_url
        title = _first_str(p, _TITLE_KEYS)
        out.append(ExternalSource(url_or_citation=url, title=title[:300] if title else _page_title(body, None),
                                  excerpt=_passage(body), content=body, authority=classify_authority(url, hosts),
                                  read_in_full=True))
    return out


def _fetch_target(args: dict[str, Any]) -> str | None:
    for k in _FETCH_ARG_KEYS:
        v = args.get(k)
        if isinstance(v, str) and _URL_RE.fullmatch(v.strip()):
            return v.strip()
    return None


def _page_title(text: str, data: Any) -> str | None:
    if isinstance(data, dict):
        for k in _TITLE_KEYS:
            if isinstance(data.get(k), str) and data[k].strip():
                return data[k].strip()[:300]
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(?:#+\s*|title:\s*)(.+)$", s, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:300]
        if len(s) <= 200 and not _URL_RE.fullmatch(s):
            return s
        break
    return None


def _records(data: Any, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 2:
        return []
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for k in _LIST_KEYS:
            v = data.get(k)
            if isinstance(v, list) and any(isinstance(d, dict) for d in v):
                return [d for d in v if isinstance(d, dict)]
            if isinstance(v, dict):
                inner = _records(v, depth + 1)
                if inner:
                    return inner
        if any(k in data for k in (*_URL_KEYS, "doi", "title")):
            return [data]
    return []


def _first_str(d: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _abstract(d: dict[str, Any]) -> str | None:
    s = _first_str(d, ("abstract", "summary", "tldr"))
    if s is None and isinstance(d.get("tldr"), dict):
        s = _first_str(d["tldr"], ("text",))
    inv = d.get("abstract_inverted_index")                     # OpenAlex
    if s is None and isinstance(inv, dict) and inv:
        pos: dict[int, str] = {}
        for word, idx in inv.items():
            for i in idx if isinstance(idx, list) else []:
                pos[int(i)] = str(word)
        s = " ".join(pos[i] for i in sorted(pos)) or None
    return s


def _doi(d: dict[str, Any]) -> str | None:
    raw = d.get("doi")
    if raw is None and isinstance(d.get("externalIds"), dict):
        raw = d["externalIds"].get("DOI")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", raw.strip(), flags=re.IGNORECASE)


def _authors(d: dict[str, Any]) -> str:
    names: list[str] = []
    raw = d.get("authors") or d.get("authorships") or []
    for a in raw if isinstance(raw, list) else []:
        if isinstance(a, str):
            names.append(a)
        elif isinstance(a, dict):
            n = a.get("name") or a.get("display_name") or (a.get("author") or {}).get("display_name")
            if isinstance(n, str):
                names.append(n)
    if not names:
        return ""
    return names[0] + (" et al." if len(names) > 1 else "")


def _from_record(d: dict[str, Any], hosts: AuthorityHosts | None = None) -> ExternalSource | None:
    url = _first_str(d, _URL_KEYS)
    if url is not None and not _URL_RE.fullmatch(url):
        url = None
    if url is None and isinstance(d.get("id"), str) and _URL_RE.fullmatch(d["id"]):
        url = d["id"]
    doi = _doi(d)
    title = _first_str(d, _TITLE_KEYS)
    scholarly = doi is not None or any(k in d for k in _SCHOLARLY_KEYS)
    abstract = _abstract(d) if scholarly else None
    snippet = abstract or _first_str(d, _SNIPPET_KEYS) or ""
    if doi is not None:
        url = f"https://doi.org/{doi}"                          # the DOI is the stable citation
    if url is None:
        if not (scholarly and title):
            return None
        year = d.get("year") or d.get("publication_year")
        venue = d.get("venue") or d.get("journal")
        venue = venue.get("name") if isinstance(venue, dict) else venue
        parts = [p for p in (_authors(d), f"({year})" if year else "", title, venue if isinstance(venue, str) else "")
                 if p]
        cite = ". ".join(parts)
    else:
        cite = url
    if scholarly:
        authority = classify_authority(url, hosts) if url else SourceAuthority.SECONDARY
        preprint = (doi or "").lower().startswith(_PREPRINT_DOI_PREFIXES) or _is_preprint_host(url or "", hosts)
        if not preprint and (doi or d.get("venue") or d.get("journal")):
            authority = SourceAuthority.PEER_REVIEWED
        content = json.dumps(d, ensure_ascii=False, sort_keys=True)
        read = bool(abstract)
    else:
        authority = classify_authority(cite, hosts)
        content = snippet or (title or "")
        read = False
    if not scholarly and not (title or snippet):
        return None                                             # a bare link: nothing readable to cite
    excerpt = _clip(snippet or title or cite) if scholarly else _clip(" - ".join(p for p in (title, snippet) if p))
    return ExternalSource(url_or_citation=cite, title=title, excerpt=excerpt, content=content or excerpt,
                          authority=authority, read_in_full=read)


def _from_text(text: str, hosts: AuthorityHosts | None = None) -> list[ExternalSource]:
    out: list[ExternalSource] = []
    md = {m.group(2).rstrip(".,;:"): m.group(1).strip() for m in _MD_LINK_RE.finditer(text)}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        for m in _URL_RE.finditer(line):
            url = m.group(0).rstrip(".,;:")
            title = md.get(url)
            if title is None:
                rest = _URL_RE.sub("", line)
                rest = re.sub(r"^\s*(\d+[.)]|[-*•]|url:|link:|source:)\s*", "", rest, flags=re.IGNORECASE).strip(" :-|")
                title = rest or None
                j = i - 1
                while title is None and j >= 0 and i - j <= 2:
                    prev = lines[j].strip()
                    if prev and not _URL_RE.search(prev):
                        title = re.sub(r"^\s*(\d+[.)]|[-*•]|#+|title:)\s*", "", prev, flags=re.IGNORECASE)
                        title = title.strip("* ").strip() or None
                    j -= 1
            snippet_lines: list[str] = []
            for nxt in lines[i + 1:i + 5]:
                if _URL_RE.search(nxt) or re.match(r"^\s*\d+[.)]\s", nxt):
                    break
                if nxt.strip():
                    snippet_lines.append(re.sub(r"^\s*(summary|snippet|description):\s*", "", nxt.strip(),
                                                flags=re.IGNORECASE))
            snippet = " ".join(snippet_lines) or (title or url)
            out.append(ExternalSource(url_or_citation=url, title=title[:300] if title else None,
                                      excerpt=_clip(snippet), content=snippet, authority=classify_authority(url, hosts),
                                      read_in_full=False))
    return out


# ------------------------------------------------------------------------------ authority

# The host lists live in config/url_policy.yaml ``authority:`` (robustness OVF-07: no evaluated
# document's own stack hard-coded in agent code). ``classify_authority`` and ``extract_sources`` take
# them from the run's config (``EffectiveConfig.url_policy.authority``); without one they read the
# repository's config/url_policy.yaml once.


@functools.lru_cache(maxsize=1)
def default_authority_hosts() -> AuthorityHosts:
    """``authority:`` of the repository's ``config/url_policy.yaml`` (callers without a run config)."""
    import yaml

    from sit_review_agent.paths import config_dir

    data = yaml.safe_load((config_dir() / "url_policy.yaml").read_text(encoding="utf-8")) or {}
    return AuthorityHosts.model_validate(data.get("authority") or {})


def _hosts(hosts: AuthorityHosts | None) -> AuthorityHosts:
    return hosts if hosts is not None else default_authority_hosts()


def _host_path(url: str) -> tuple[str, str]:
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return "", ""
    host = (p.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return host, (p.path or "").lower()


def _matches(host: str, path: str, entries: Sequence[str]) -> bool:
    for e in entries:
        dom, _, sub = e.partition("/")
        if (host == dom or host.endswith("." + dom)) and (not sub or path.startswith("/" + sub)):
            return True
    return False


def _is_gov(host: str) -> bool:
    labels = host.split(".")
    if not labels or len(labels) < 2:
        return False
    if labels[-1] in ("gov", "mil", "int"):
        return True
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in ("gov", "gouv", "gob", "go", "govt", "gv"):
        return True
    return False


def _is_preprint_host(url: str, hosts: AuthorityHosts | None = None) -> bool:
    host, path = _host_path(url)
    return _matches(host, path, _hosts(hosts).preprint)


def classify_authority(url: str, hosts: AuthorityHosts | None = None) -> SourceAuthority:
    """Domain heuristics: standards bodies, regulators, official vendor docs -> primary_official;
    DOI / journals -> peer_reviewed; known reference sites -> secondary; else informal.

    Classes and their definitions are ``spec/taxonomy.yaml`` ``source_authority``
    (primary_official: "the standard, statute or official vendor/product documentation itself";
    peer_reviewed: "peer-reviewed paper or recognised technical report"; secondary: "reputable
    secondary summary"; informal: "blog, forum, Q&A, marketing page"). The ordering follows
    ``research/robustness/scenarios.md`` ADV-16 ("standards bodies, official docs, peer-reviewed >
    reputable engineering blogs > forums > content farms"; ADV-15 weighs conflicts by authority)
    and ``research/robustness/README.md`` §10 item 3 (the ledger records the source class).
    Decisions the notes leave open: preprint servers and scholarly indexes (arXiv, SSRN,
    OpenAlex, Semantic Scholar) are ``secondary`` (not peer reviewed); preprint DOIs
    (``10.48550/`` arXiv, ``10.1101/`` bioRxiv, ...) likewise; government hosts (``.gov``,
    ``gov.<cc>``, ``.int``) and ``docs.``/``developer.``/``learn.`` hosts are ``primary_official``;
    vendor *blogs* are ``secondary``; anything unknown is ``informal``, so an unrecognised site
    never outranks a recognised one. A non-URL citation (a scholarly record without a link, or the
    ``mcp:`` pseudo-citation) is ``informal`` here; scholarly records are upgraded by
    :func:`extract_sources`. ``hosts``: the run's ``url_policy.authority`` (default: the
    repository's ``config/url_policy.yaml``).
    """
    h = _hosts(hosts)
    u = url.strip()
    if u.lower().startswith("doi:"):
        doi = u[4:].strip().lower()
        return SourceAuthority.SECONDARY if doi.startswith(_PREPRINT_DOI_PREFIXES) else SourceAuthority.PEER_REVIEWED
    host, path = _host_path(u)
    if not host:
        return SourceAuthority.INFORMAL
    if host in ("doi.org", "dx.doi.org"):
        doi = path.lstrip("/")
        return SourceAuthority.SECONDARY if doi.startswith(_PREPRINT_DOI_PREFIXES) else SourceAuthority.PEER_REVIEWED
    if _matches(host, path, h.informal):
        return SourceAuthority.INFORMAL
    if _matches(host, path, h.secondary) or "/blog" in path or host.startswith("blog."):
        return SourceAuthority.SECONDARY
    if _matches(host, path, h.standards) or _is_gov(host):
        return SourceAuthority.PRIMARY_OFFICIAL
    if _matches(host, path, h.preprint):
        return SourceAuthority.SECONDARY
    if _matches(host, path, h.peer_reviewed):
        return SourceAuthority.PEER_REVIEWED
    if _matches(host, path, h.vendor_docs) or host.startswith(tuple(h.docs_prefixes)):
        return SourceAuthority.PRIMARY_OFFICIAL
    if host.endswith(".edu") or ".ac." in host or host.endswith(".edu.sg"):
        return SourceAuthority.SECONDARY
    return SourceAuthority.INFORMAL


def independence_key(url_or_citation: str) -> str:
    """Key under which two sources count as *not* independent (``min_independent_sources``):
    the registrable domain for URLs (``docs.example.com`` and ``www.example.com`` are one
    source), the full DOI for DOI links (two papers are independent even from one publisher),
    and the citation text otherwise."""
    u = url_or_citation.strip()
    host, path = _host_path(u)
    if host in ("doi.org", "dx.doi.org"):
        return "doi:" + path.lstrip("/")
    if not host:
        return u.lower()
    labels = host.split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in ("co", "com", "ac", "gov", "edu", "org", "net",
                                                                      "go", "or", "ne", "gob", "gouv"):
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])
