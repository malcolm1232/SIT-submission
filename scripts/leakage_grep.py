#!/usr/bin/env python3
"""Leakage grep (robustness OVF-07; eval/prereg.yaml leakage_controls LC8 and the static part of LC10).

Looks for answer-key text and document-specific strings in what the agent ships: its code, prompts,
config, cassettes and fixtures. Sample terms may appear only under ``tests/`` (outside fixtures and
cassettes), ``eval/`` and ``research/`` (research/robustness/scenarios.md OVF-07).

Run it explicitly; nothing imports it (the agent never does, and must not: it reads answer keys)::

    python scripts/leakage_grep.py                       # gate: agent/, prompts/, config/ (exit 1 on a hit)
    python scripts/leakage_grep.py --strict              # also gate cassettes and fixtures
    python scripts/leakage_grep.py --sample <sit_sample.pdf> --json
    python scripts/leakage_grep.py --keys 'eval/synthetic/*/answer_key*.json' --docs '' --top 100

What counts as a term (prereg LC10, MR §3.2 steps 1-3), from each source document:

* the top ``--top`` (200) TF-IDF word pairs (``fraud hook``) against the other items, after a
  built-in list of common English and software words (single words are not gated: without a general
  English corpus, "clock" or "finding" is shared by any design document and any review tool);
* identifiers used by one item only: requirement, decision and flaw IDs (``NFR-12``, ``F07``),
  hyphenated codes (``FRV-1``, ``EWS-ML``) and backticked code names (``card_number``);
* proper nouns used by one item only: capitalised words that never occur in lower case in any
  source (``Harbourfront``);
* numbers with units (``2,000 messages``, ``250 ms``); reported, but only gating with ``--strict``
  (generic timeouts in code look the same);
* the known sample-stack strings :data:`KNOWN_SAMPLE_STRINGS` (hosts that came from the SIT
  sample's stack and were removed from the agent's authority list, 2026-10-02);
* 13-word overlaps between a source document and a scanned file (any overlap is a hit); the longest
  overlap of 8 or more words is reported per file.

Sources (read only when this script runs): answer keys (``--keys``, default
``eval/synthetic/*/answer_key*.json``), the evaluated documents (``--docs``, default
``eval/synthetic/*/design_v*.md``), the SIT sample on the laptop (``--sample``, PDF or text) and an
optional term list (``--terms``, one per line). ``eval/blind/`` is never opened: a source path under
it is refused (exit 2) and globs skip it. ``--allow FILE`` resolves known false positives (one term
per line, ``term  # reason``); resolved hits are listed separately.

Exit codes: 0 no unresolved hit in a gated area, 1 at least one, 2 usage error.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
BLIND = "eval/blind"

#: Strings from the SIT sample's own stack that once sat in agent code (robustness OVF-07 finding).
KNOWN_SAMPLE_STRINGS = ("github.com/pgvector", "pgvector.dev", "kafka.apache.org")

#: Hits reviewed and resolved as generic (term -> reason); ``--allow FILE`` adds more. Reviewed
#: 2026-10-02 against the three eval/synthetic items; each is a general word or name, not item content.
DEFAULT_RESOLVED = {
    "apache": "apache.org, the Apache Software Foundation's documentation host (authority list)",
    "stripe": "stripe.com, a general payments vendor's documentation host (authority list); the payments item "
              "also names the vendor, which the list does not help review",
    "scholar": "Google Scholar, a scholarly index (authority list)",
    "government": "generic word (government hosts in the authority rules)",
    "platforms": "generic word (content platforms)",
    "regulations": "generic word (criteria and prompts ask about laws and regulations)",
    "terminated": "MCP session state constant",
    "request_hash": "generic code identifier",
}

DEFAULT_KEYS = ("eval/synthetic/*/answer_key*.json",)
DEFAULT_DOCS = ("eval/synthetic/*/design_v*.md",)

#: area -> (globs, gated by default). Paths are repo-relative.
AREAS: dict[str, tuple[tuple[str, ...], bool]] = {
    "agent": (("agent/sit_review_agent/**/*",), True),
    "prompts": (("prompts/**/*",), True),
    "config": (("config/**/*",), True),
    "cassettes": (("tests/fixtures/cassettes/**/*", "tests/robustness/fixtures/cassettes/**/*"), False),
    "fixtures": (("agent/sit_review_agent/fixtures/**/*", "tests/fixtures/**/*", "tests/robustness/fixtures/**/*"),
                 False),
}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".j2", ".lock", ".csv", ".toml", ".cfg", ""}
SKIP_PARTS = {"__pycache__", ".git", ".venv"}

#: Common English and software-engineering words: a term in this list is never distinctive.
COMMON = set("""
a about above access account accounts across action actions active add added adds after again against all allow
allowed allows already also always an analysis and any api apis app application applications apply approach
approved architecture are area areas as ask assess assessment at audit authentication authority available back
backend based batch be because been before being below best between both build built business but by cache call
called calls can capacity case cases central change changes check checks clear client clients cloud code common
component components config configuration connection consistent constraint constraints control controls core cost
could critical current customer customers daily data database date day days decision decisions default defined
delivery dependency deployment description design designs detail details develop development different direct
document documents does done down during each early edge either else end endpoint endpoints engine environment
error errors event events every evidence example existing expected external failure failures fall feature
features field fields file files first flow flows following for format from full function functional future gap
gaps gateway given good group groups handle handling has have high hour hours how however identity if impact
implementation in include includes including index information infrastructure initial input inputs integration
interface internal into is issue issues it item items its job jobs just key keys large last later latency layer
layers least level levels limit limits list load local log logging logs long low made main make management manual
many may means message messages method metric metrics might minute minutes mode model models monitoring month
more most must name names need needed needs network new next no node nodes non none normal not note notes number
numbers object objective objectives of off on once one only open operation operations option options or order
other others out output outputs over owner page pages part partial path pattern pay peak per performance period
phase plan platform point policy pool possible primary principle principles priority private process processing
product production provider providers public purpose queue rate read real reason record records recovery reduce
region release reliability report request requests require required requirement requirements resource resources
response result results retention retry review risk risks role roles rule rules run running runs same scale scope
section sections security see send sent server servers service services session set should single size so some
source sources specific stage standard state status step steps storage store stored stream strong such support
supported system systems table target team test testing tests than that the their them then there these they this
those through time times to token tokens tool tools total traffic trigger true two type types under update updated
upon usage use used user users uses using validation value values version versions via view volume was way we week
well were what when where whether which while who will with within without work workflow would write year years
yes your zone
breaker circuit evaluation harness template subscription traceability category terminal resolver owners
""".split())
#: Proper nouns of general technology and language (never document-specific on their own).
GENERIC_PROPER = {"python", "english", "https", "http", "oauth", "json", "yaml", "linux", "windows", "macos",
                  "github", "postgresql", "docker", "kubernetes", "azure", "google", "amazon", "microsoft",
                  "anthropic", "claude", "markdown", "unicode", "openapi", "javascript", "typescript", "java"}

WORD_RE = re.compile(r"[a-z0-9]+")
BIGRAM_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+")
#: A capitalised word in the middle of a sentence (after a lower-case word or a comma), so a word
#: capitalised only because it starts a sentence, a heading or a table cell is not taken.
CAP_RE = re.compile(r"(?<=[a-z,;] )[A-Z][a-zA-Z]{4,}\b")
ID_RES = (re.compile(r"\b[A-Z]{1,5}-\d{1,3}(?:\.\d+)?\b"),       # FR-3, NFR-12, AD-04, FRV-1
          re.compile(r"\b[A-Z]{2,6}-[A-Z]{2,6}\b"),                 # EWS-ML
          re.compile(r"\bF\d{2}\b"))                                # flaw IDs
#: Standard identifiers that look like IDs but name no document (never a hit).
GENERIC_IDS = {"sha-256", "sha-1", "utf-8", "utf-16", "iso-8601", "aes-256", "aes-128", "http-2", "tls-1",
               "x-509", "rfc-3339", "rfc-9110", "p-256", "md-5", "crc-32", "ipv-4", "ipv-6", "ecma-262"}
BACKTICK_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_.\-/]{4,})`")
UNIT_RE = re.compile(r"\b\d[\d,.]*\s?(?:ms|sec|seconds|minutes|hours|days|GB|TB|MB|KB|rps|req/s|tps|qps|%|"
                     r"messages|users|patients|devices|transactions|events|vectors|rows)\b")


@dataclass
class Source:
    path: str
    text: str


@dataclass
class Term:
    text: str
    kind: str                          # tfidf | id | name | proper | unit | known | user
    sources: set[str] = field(default_factory=set)


@dataclass
class Hit:
    area: str
    file: str
    line: int
    term: str
    kind: str
    sources: list[str]
    resolved: str | None = None


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO))
    except ValueError:
        return str(p.resolve())


def _under_blind(p: Path) -> bool:
    rel = _rel(p)
    return rel == BLIND or rel.startswith(BLIND + "/")


class UsageError(Exception):
    pass


def _expand(patterns: Iterable[str]) -> list[Path]:
    out: list[Path] = []
    for pat in patterns:
        if not pat:
            continue
        p = Path(pat)
        if not p.is_absolute() and not any(c in pat for c in "*?["):
            p = REPO / p
        if any(c in pat for c in "*?["):
            base = pat if Path(pat).is_absolute() else str(REPO / pat)
            matches = [Path(m) for m in sorted(glob.glob(base, recursive=True))]
            out += [m for m in matches if not _under_blind(m)]       # globs skip eval/blind
            continue
        if _under_blind(p):
            raise UsageError(f"{pat}: eval/blind/ is never read (sealed held-out material)")
        if not p.is_file():
            raise UsageError(f"{pat}: not a file")
        out.append(p)
    return out


def _strings(v: Any) -> Iterable[str]:
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)


def _read_source(p: Path) -> str:
    if p.suffix.lower() == ".json":
        return "\n".join(_strings(json.loads(p.read_text(encoding="utf-8"))))
    if p.suffix.lower() == ".pdf":
        import pdfplumber  # only for --sample on the laptop

        with pdfplumber.open(str(p)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    return p.read_text(encoding="utf-8", errors="replace")


def load_sources(keys: Iterable[str], docs: Iterable[str], samples: Iterable[str]) -> list[Source]:
    return [Source(_rel(p), _read_source(p)) for p in [*_expand(keys), *_expand(docs), *_expand(samples)]]


def _group(path: str) -> str:
    """Sources of one evaluated item (its key, v1 and v2) form one group for document frequency."""
    parts = Path(path).parts
    if len(parts) >= 3 and parts[0] == "eval" and parts[1] == "synthetic":
        return "/".join(parts[:3])
    return path


def _bigrams(text: str) -> list[str]:
    """Word pairs in which neither word is a common word (``fraud hook``, not ``the ledger``)."""
    words = [w.lower() for w in BIGRAM_WORD_RE.findall(text)]
    return [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)
            if len(a) >= 4 and len(b) >= 4 and a not in COMMON and b not in COMMON
            and not (a.isdigit() or b.isdigit())]


#: Parts of a code identifier that carry no document-specific meaning (``run_id``, ``created_at``).
GENERIC_NAME_PARTS = COMMON | {"id", "ids", "at", "by", "ts", "utc", "is", "created", "py", "json", "yaml", "md",
                               "txt", "src", "tmp", "min", "max", "sec", "num", "url", "uri", "http", "https"}


def _generic_name(name: str) -> bool:
    return all(p in GENERIC_NAME_PARTS or p.isdigit() for p in re.split(r"[_./\-]+", name.lower()) if p)


def extract_terms(sources: list[Source], *, top: int = 200, extra: Iterable[str] = ()) -> dict[str, Term]:
    """Distinctive terms per source group (see the module docstring). Single words are only taken
    as proper nouns or identifiers: without a general-English corpus, ordinary words ("clock",
    "finding") are shared by any design document and any review tool, so the TF-IDF part works on
    word pairs. A laptop run can add a proper term list with ``--terms``."""
    terms: dict[str, Term] = {}

    def add(text: str, kind: str, src: str) -> None:
        key = text.strip().lower()
        if len(key) < 4 or key in COMMON or key in GENERIC_IDS:
            return
        t = terms.setdefault(key, Term(text.strip(), kind))
        t.sources.add(src)

    groups: dict[str, list[Source]] = {}
    for s in sources:
        groups.setdefault(_group(s.path), []).append(s)
    gtext = {g: "\n".join(x.text for x in xs) for g, xs in groups.items()}
    counts = {g: Counter(_bigrams(t)) for g, t in gtext.items()}
    df: Counter[str] = Counter()
    for c in counts.values():
        df.update(set(c))
    n = len(counts) + 1
    for g, c in counts.items():
        total = sum(c.values()) or 1
        scored = sorted(((cnt / total) * math.log(n / df[b]), b) for b, cnt in c.items() if cnt >= 2)
        for _, b in reversed(scored[-top:]):
            add(b, "tfidf", g)
    # Proper nouns, IDs and code names count only when one item uses them (df == 1): a heading word
    # or an ID pattern every document has (``Anchor``, ``FR-7``) names no particular document.
    all_text = "\n".join(gtext.values())
    lower_seen = set(re.findall(r"\b[a-z][a-z]{4,}\b", all_text))   # words that also occur in lower case
    per_group: dict[str, dict[str, set[str]]] = {}
    for g, text in gtext.items():
        caps = Counter(CAP_RE.findall(text))
        found = {"proper": {w for w, cnt in caps.items()
                            if cnt >= 2 and w.lower() not in lower_seen and w.lower() not in GENERIC_PROPER},
                 "id": {m for rx in ID_RES for m in rx.findall(text)},
                 "name": {m for m in BACKTICK_RE.findall(text)
                          if re.search(r"[_./\d]|[a-z][A-Z]", m) and not _generic_name(m)},
                 "unit": set(UNIT_RE.findall(text))}
        per_group[g] = found
    for kind in ("proper", "id", "name", "unit"):
        seen_in: Counter[str] = Counter()
        for found in per_group.values():
            seen_in.update({x.lower() for x in found[kind]})
        for g, found in per_group.items():
            for x in found[kind]:
                if seen_in[x.lower()] == 1:
                    add(x, kind, g)
    for k in KNOWN_SAMPLE_STRINGS:
        add(k, "known", "KNOWN_SAMPLE_STRINGS")
    for k in extra:
        add(k, "user", "--terms")
    return terms


def _pattern(term: str) -> re.Pattern[str]:
    esc = re.escape(term)
    if " " in term:                                          # a word pair: any whitespace between the words
        esc = r"\s+".join(re.escape(w) for w in term.split())
    if re.fullmatch(r"[A-Za-z0-9_ ]+", term):
        return re.compile(rf"(?<![A-Za-z0-9_]){esc}(?![A-Za-z0-9_])", re.IGNORECASE)
    return re.compile(esc, re.IGNORECASE)


def scan_files(areas: dict[str, tuple[tuple[str, ...], bool]]) -> list[tuple[str, Path]]:
    seen: set[Path] = set()
    out: list[tuple[str, Path]] = []
    for area, (globs, _) in areas.items():
        for g in globs:
            for m in sorted(glob.glob(str(REPO / g), recursive=True)):
                p = Path(m)
                if not p.is_file() or p in seen or SKIP_PARTS & set(p.parts) or _under_blind(p):
                    continue
                if p.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                if area != "fixtures" and "fixtures" in Path(_rel(p)).parts:
                    continue                             # agent/sit_review_agent/fixtures is the fixtures area
                seen.add(p)
                out.append((area, p))
    return out


def _ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def longest_overlap(a: list[str], b_grams8: set[tuple[str, ...]], b_words: list[str]) -> int:
    """Length of the longest run of words of ``a`` that also occurs in ``b`` (>= 8, else 0)."""
    best = 0
    i = 0
    while i + 8 <= len(a):
        if tuple(a[i:i + 8]) in b_grams8:
            j = i + 8
            text = " " + " ".join(b_words) + " "
            while j < len(a) and (" " + " ".join(a[i:j + 1]) + " ") in text:
                j += 1
            best = max(best, j - i)
            i = j
        else:
            i += 1
    return best


def run(sources: list[Source], terms: dict[str, Term], *, areas: dict[str, tuple[tuple[str, ...], bool]] = AREAS,
        allow: dict[str, str] | None = None, strict: bool = False, defaults: bool = True) -> dict[str, Any]:
    allow = {k.lower(): v for k, v in {**(DEFAULT_RESOLVED if defaults else {}), **(allow or {})}.items()}
    compiled = [(t, _pattern(t.text)) for t in terms.values()]
    src_words = [WORD_RE.findall(s.text.lower()) for s in sources]
    src13 = set().union(*[_ngrams(w, 13) for w in src_words]) if src_words else set()
    src8 = [(_ngrams(w, 8), w, s.path) for w, s in zip(src_words, sources, strict=True)]
    hits: list[Hit] = []
    overlaps: list[dict[str, Any]] = []
    files = scan_files(areas)
    for area, p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = _rel(p)
        low = text.lower()
        for t, pat in compiled:
            if t.text.lower() not in low:
                continue
            m = pat.search(text)
            if m is None:
                continue
            ln = text.count("\n", 0, m.start()) + 1           # one hit per term and file is enough to act on
            hits.append(Hit(area, rel, ln, t.text, t.kind, sorted(t.sources), allow.get(t.text.lower())))
        words = WORD_RE.findall(text.lower())
        g13 = _ngrams(words, 13) & src13
        best, best_src = 0, ""
        for g8, sw, path in src8:
            if g8 & _ngrams(words, 8):
                n = longest_overlap(words, g8, sw)
                if n > best:
                    best, best_src = n, path
        if g13 or best:
            overlaps.append({"area": area, "file": rel, "ngram13": len(g13), "max_overlap_words": best,
                             "source": best_src})
    gated = {a for a, (_, g) in areas.items() if g or strict}
    unresolved = [h for h in hits if h.resolved is None and h.area in gated
                  and (strict or h.kind != "unit")]
    overlap_fail = [o for o in overlaps if o["ngram13"] and o["area"] in gated]
    return {"sources": [s.path for s in sources], "terms": len(terms), "files_scanned": len(files),
            "gated_areas": sorted(gated), "hits": [h.__dict__ for h in hits], "overlaps": overlaps,
            "unresolved": [h.__dict__ for h in unresolved], "overlap_failures": overlap_fail,
            "passed": not unresolved and not overlap_fail}


def _read_list(path: str | None) -> list[str]:
    if not path:
        return []
    p = Path(path)
    if _under_blind(p):
        raise UsageError(f"{path}: eval/blind/ is never read")
    return [ln.split("#", 1)[0].strip() for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.split("#", 1)[0].strip()]


def _read_allow(path: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path:
        return out
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        term, _, reason = ln.partition("#")
        if term.strip():
            out[term.strip()] = reason.strip() or "allowed"
    return out


def _report(res: dict[str, Any]) -> str:
    out = [f"leakage grep: {len(res['sources'])} source documents, {res['terms']} terms, "
           f"{res['files_scanned']} files scanned; gated areas: {', '.join(res['gated_areas'])}"]
    by_area: Counter[str] = Counter(h["area"] for h in res["hits"])
    out.append("hits by area: " + (", ".join(f"{a} {n}" for a, n in sorted(by_area.items())) or "none"))
    for h in res["unresolved"]:
        out.append(f"  UNRESOLVED {h['area']}: {h['file']}:{h['line']}: {h['term']!r} ({h['kind']}; from "
                   f"{', '.join(h['sources'][:3])})")
    for h in res["hits"]:
        if h not in res["unresolved"]:
            tag = f"resolved: {h['resolved']}" if h["resolved"] else "reported"
            out.append(f"  {tag} {h['area']}: {h['file']}:{h['line']}: {h['term']!r} ({h['kind']})")
    for o in res["overlaps"]:
        out.append(f"  overlap {o['area']}: {o['file']}: 13-grams {o['ngram13']}, longest {o['max_overlap_words']} "
                   f"words (from {o['source']})")
    out.append("PASS: no unresolved hit in a gated area" if res["passed"] else "FAIL: unresolved leakage (see above)")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--keys", action="append", help="answer-key glob (repeatable; default eval/synthetic keys)")
    ap.add_argument("--docs", action="append", help="evaluated-document glob (repeatable; '' for none)")
    ap.add_argument("--sample", action="append", default=[], help="the SIT sample (PDF or text), on the laptop")
    ap.add_argument("--terms", help="extra terms, one per line")
    ap.add_argument("--allow", help="resolved false positives: 'term  # reason' per line")
    ap.add_argument("--top", type=int, default=200, help="TF-IDF terms per source document (default 200)")
    ap.add_argument("--strict", action="store_true", help="also gate cassettes, fixtures and numbers with units")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(argv)
    try:
        sources = load_sources(a.keys if a.keys is not None else DEFAULT_KEYS,
                               a.docs if a.docs is not None else DEFAULT_DOCS, a.sample)
        terms = extract_terms(sources, top=a.top, extra=_read_list(a.terms))
        res = run(sources, terms, allow=_read_allow(a.allow), strict=a.strict)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=1) if a.json else _report(res))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
