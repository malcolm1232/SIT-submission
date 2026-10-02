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

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sit_review_agent.models import SourceAuthority
from sit_review_agent.tools.gateway import ToolResult

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


def extract_sources(result: ToolResult) -> list[ExternalSource]:
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
    * Anything else non-empty -> one pseudo-citation ``mcp:<server>/<tool>?<args>`` holding the
      text (``informal``), so whatever the model saw is still citable only by ID.
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

    fetch_url = _fetch_target(result.args)
    if fetch_url is None and any(w in result.tool_name.lower() for w in _FETCH_TOOL_WORDS):
        m = _URL_RE.search(text)
        fetch_url = m.group(0).rstrip(".,;:") if m else None
    if fetch_url is not None:
        body = text if text.strip() else json.dumps(data, ensure_ascii=False, sort_keys=True)
        return [ExternalSource(url_or_citation=fetch_url, title=_page_title(body, data), excerpt=_clip(body),
                               content=body, authority=classify_authority(fetch_url), read_in_full=True)]

    out: list[ExternalSource] = []
    if data is not None:
        for rec in _records(data):
            src = _from_record(rec)
            if src is not None:
                out.append(src)
    if not out and text.strip():
        out = _from_text(text)
    if not out:
        body = text if text.strip() else json.dumps(data, ensure_ascii=False, sort_keys=True)
        args = json.dumps(result.args, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        out = [ExternalSource(url_or_citation=f"mcp:{result.server}/{result.tool_name}?{args}",
                              title=f"{result.server} {result.tool_name} result", excerpt=_clip(body), content=body,
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


def _from_record(d: dict[str, Any]) -> ExternalSource | None:
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
        authority = classify_authority(url) if url else SourceAuthority.SECONDARY
        preprint = (doi or "").lower().startswith(_PREPRINT_DOI_PREFIXES) or _is_preprint_host(url or "")
        if not preprint and (doi or d.get("venue") or d.get("journal")):
            authority = SourceAuthority.PEER_REVIEWED
        content = json.dumps(d, ensure_ascii=False, sort_keys=True)
        read = bool(abstract)
    else:
        authority = classify_authority(cite)
        content = snippet or (title or "")
        read = False
    excerpt = _clip(snippet or title or cite)
    return ExternalSource(url_or_citation=cite, title=title, excerpt=excerpt, content=content or excerpt,
                          authority=authority, read_in_full=read)


def _from_text(text: str) -> list[ExternalSource]:
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
                                      excerpt=_clip(snippet), content=snippet, authority=classify_authority(url),
                                      read_in_full=False))
    return out


# ------------------------------------------------------------------------------ authority

#: Standards bodies, regulators and intergovernmental organisations (``primary_official``).
_STANDARDS = ("iso.org", "iec.ch", "ietf.org", "rfc-editor.org", "w3.org", "nist.gov", "etsi.org", "itu.int",
              "standards.ieee.org", "owasp.org", "cisecurity.org", "pcisecuritystandards.org", "oasis-open.org",
              "ecma-international.org", "whatwg.org", "unicode.org", "openid.net", "fidoalliance.org",
              "cloudevents.io", "opentelemetry.io", "spec.openapis.org", "json-schema.org", "europa.eu",
              "legislation.gov.uk", "who.int", "ich.org", "oecd.org", "un.org", "cnil.fr", "ico.org.uk",
              "pdpc.gov.sg", "imda.gov.sg", "csa.gov.sg", "mas.gov.sg", "hhs.gov", "fda.gov", "cisa.gov",
              "enisa.europa.eu", "bsi.bund.de", "ncsc.gov.uk", "modelcontextprotocol.io")
#: Official vendor / project documentation hosts (``primary_official``).
_VENDOR_DOCS = ("learn.microsoft.com", "docs.microsoft.com", "docs.aws.amazon.com", "cloud.google.com",
                "developer.apple.com", "developers.google.com", "docs.oracle.com", "docs.github.com",
                "kubernetes.io", "postgresql.org", "python.org", "docs.python.org", "apache.org", "redis.io",
                "nginx.org", "mongodb.com", "elastic.co", "docker.com", "hashicorp.com", "terraform.io",
                "openai.com", "anthropic.com", "docs.anthropic.com", "platform.claude.com", "code.claude.com",
                "azure.microsoft.com", "aws.amazon.com", "cloudflare.com", "stripe.com", "twilio.com",
                "mysql.com", "sqlite.org", "nodejs.org", "rust-lang.org", "go.dev", "golang.org", "java.com",
                "openjdk.org", "spring.io", "djangoproject.com", "fastapi.tiangolo.com", "pydantic.dev",
                "github.com/pgvector", "pgvector.dev", "snowflake.com", "databricks.com", "confluent.io",
                "kafka.apache.org", "grafana.com", "prometheus.io")
#: Publishers, indexes of peer-reviewed work and proceedings (``peer_reviewed``).
_PEER = ("doi.org", "dl.acm.org", "acm.org", "ieeexplore.ieee.org", "ieee.org", "springer.com", "link.springer.com",
         "sciencedirect.com", "elsevier.com", "nature.com", "science.org", "wiley.com", "onlinelibrary.wiley.com",
         "tandfonline.com", "sagepub.com", "plos.org", "mdpi.com", "frontiersin.org", "bmj.com", "thelancet.com",
         "nejm.org", "jamanetwork.com", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "usenix.org",
         "aclanthology.org", "openreview.net", "jmlr.org", "proceedings.mlr.press", "neurips.cc", "papers.nips.cc",
         "aaai.org", "ojs.aaai.org", "vldb.org", "cambridge.org", "academic.oup.com", "jstor.org",
         "cochranelibrary.com", "iopscience.iop.org", "asce.org", "ascelibrary.org", "icevirtuallibrary.com")
#: Preprint servers and scholarly indexes: reputable but not peer reviewed (``secondary``).
_PREPRINT = ("arxiv.org", "biorxiv.org", "medrxiv.org", "ssrn.com", "researchsquare.com", "preprints.org",
             "researchgate.net", "semanticscholar.org", "openalex.org", "crossref.org", "scholar.google.com",
             "core.ac.uk", "hal.science", "zenodo.org")
#: Reputable secondary summaries: references, quality engineering publications, textbooks (``secondary``).
_SECONDARY = ("wikipedia.org", "britannica.com", "martinfowler.com", "infoq.com", "thoughtworks.com",
              "queue.acm.org", "lwn.net", "oreilly.com", "highscalability.com", "brendangregg.com",
              "netflixtechblog.com", "engineering.fb.com", "engineering.atspotify.com", "blog.cloudflare.com",
              "aws.amazon.com/blogs", "cloud.google.com/blog", "techcommunity.microsoft.com", "devblogs.microsoft.com",
              "github.blog", "uber.com/blog", "dropbox.tech", "slack.engineering", "stripe.com/blog",
              "gartner.com", "forrester.com", "mckinsey.com", "iapp.org", "lexology.com", "jdsupra.com")
#: Forums, Q&A, self-publishing and content platforms (``informal``; checked first).
_INFORMAL = ("medium.com", "dev.to", "stackoverflow.com", "stackexchange.com", "serverfault.com", "superuser.com",
             "reddit.com", "quora.com", "hashnode.dev", "hashnode.com", "substack.com", "blogspot.com",
             "wordpress.com", "linkedin.com", "youtube.com", "twitter.com", "x.com", "news.ycombinator.com",
             "geeksforgeeks.org", "tutorialspoint.com", "w3schools.com", "javatpoint.com", "facebook.com",
             "tiktok.com", "pinterest.com", "slideshare.net", "scribd.com", "towardsdatascience.com")
_DOCS_PREFIXES = ("docs.", "developer.", "developers.", "learn.", "spec.", "specs.", "documentation.")


def _host_path(url: str) -> tuple[str, str]:
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return "", ""
    host = (p.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return host, (p.path or "").lower()


def _matches(host: str, path: str, entries: tuple[str, ...]) -> bool:
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


def _is_preprint_host(url: str) -> bool:
    host, path = _host_path(url)
    return _matches(host, path, _PREPRINT)


def classify_authority(url: str) -> SourceAuthority:
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
    :func:`extract_sources`.
    """
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
    if _matches(host, path, _INFORMAL):
        return SourceAuthority.INFORMAL
    if _matches(host, path, _SECONDARY) or "/blog" in path or host.startswith("blog."):
        return SourceAuthority.SECONDARY
    if _matches(host, path, _STANDARDS) or _is_gov(host):
        return SourceAuthority.PRIMARY_OFFICIAL
    if _matches(host, path, _PREPRINT):
        return SourceAuthority.SECONDARY
    if _matches(host, path, _PEER):
        return SourceAuthority.PEER_REVIEWED
    if _matches(host, path, _VENDOR_DOCS) or host.startswith(_DOCS_PREFIXES):
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
