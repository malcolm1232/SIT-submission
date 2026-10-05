"""Table rows of the reviewed document, rebuilt for a reader (6 Oct 2026).

The text the review read is the PDF's extracted text, page by page. In a table, a vertically centred id cell lands
between the wrapped lines of its neighbour cell, and one row runs into the next with no boundary, so a reader
cannot tell where the row of ``P1`` starts and ends. This module rebuilds such rows for the export and the Review
tab only (it never changes the text the model read):

* from the reviewed PDF itself, when the run can vouch for it (the caller passes the file only when its SHA-256
  matches the manifest, ``rundata.reviewed_pdf``): pdfplumber's table extraction, its default (ruling lines)
  strategy first and its text strategy when the default finds no table on the page (then only rows keyed by an
  id, since text columns also cut plain prose into cells). A logical row is a run of
  extracted rows between blank ones, split again wherever the key column has text. A row is used only when every
  piece of its text is found in the page's extracted text, near the others and with no other row's key between
  them; that span is the row's place in the text the review read;
* otherwise from the extracted text alone, only when :func:`text_row` finds the row unambiguous (the id line
  holds the id and its text, and the lines just above and below are themselves other rows' id lines);
* otherwise not at all: the caller says the id sits inside a table, and nothing is guessed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

ID_LINE = r"[A-Z]{1,5}-?\d+(?:\.\d+)?"
PDF_LABEL = "Table row on page {page}, rebuilt from the PDF's table layout"
TEXT_LABEL = "Table row on page {page}, read from the extracted text (the row is a single line)"
TABLE_NOTE = ("This id sits inside a table; in the extracted text its row's words appear on the lines just above "
              "and below it.")


def plain(text: str) -> str:
    """Dashes made plain (as the extracted text has them) and every whitespace run one space."""
    for a, b in (("—", "-"), ("–", "-"), ("−", "-"), ("‘", "'"), ("’", "'"),
                 ("“", '"'), ("”", '"'), (" ", " ")):
        text = text.replace(a, b)
    return " ".join(text.split())


def _join(parts: list[str]) -> str:
    out = ""
    for p in parts:
        if not p:
            continue
        hyphen = out.endswith("-") and out[-2:-1].isalpha() and p[:1].islower()   # a word broken at the line
        out = out + p if hyphen else (out + " " + p if out else p)
    return out


@dataclass
class Row:
    """One logical table row: its key (the first cell), each column's text, and the pieces as extracted."""

    page: int
    key: str
    cells: list[str]
    pieces: list[str]
    span: tuple[int, int] | None = None          # its lines in the extracted page text, when they were found
    source: str = "pdf"

    @property
    def sentence(self) -> str:
        return " - ".join(c for c in [self.key, *self.cells] if c)

    @property
    def label(self) -> str:
        return (PDF_LABEL if self.source == "pdf" else TEXT_LABEL).format(page=self.page)


def _logical_rows(table: list[list[Any]], page: int) -> list[Row]:
    """The extracted rows of one table grouped into logical rows (see the module docstring)."""
    def text(c: Any) -> str:
        return plain(str(c)) if c is not None else ""

    groups: list[list[list[Any]]] = []
    cur: list[list[Any]] = []
    for r in table:
        if not any(text(c) for c in r):
            if cur:
                groups.append(cur)
            cur = []
            continue
        cur.append(r)
    if cur:
        groups.append(cur)
    rows: list[Row] = []
    for g in groups:
        key_col = next(i for i, c in enumerate(g[0]) if text(c))
        start = 0
        for i in range(1, len(g) + 1):
            if i == len(g) or text(g[i][key_col] if key_col < len(g[i]) else None):
                part = g[start:i]
                start = i
                ncols = max(len(r) for r in part)
                cols = [_join([text(r[c]) for r in part if c < len(r)]) for c in range(ncols)]
                key = cols[key_col]
                cells = [c for j, c in enumerate(cols) if j != key_col and c]
                pieces = [ln for r in part for c in r if c is not None for ln in
                          (plain(x) for x in str(c).split("\n")) if ln]
                if key and cells:
                    rows.append(Row(page, key, cells, pieces))
    return rows


@lru_cache(maxsize=8)
def _pdf_tables(path: str, mtime: float, size: int) -> dict[int, list[Row]]:
    import pdfplumber

    out: dict[int, list[Row]] = {}
    with pdfplumber.open(path) as pdf:
        for n, pg in enumerate(pdf.pages, 1):
            try:
                tables = pg.extract_tables()
                source = "lines"
                if not tables:
                    tables = pg.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text"})
                    source = "text"
            except Exception:  # noqa: BLE001 - a page pdfplumber cannot read has no rows, never a failed export
                continue
            rows = [r for t in tables for r in _logical_rows(t, n)]
            if source == "text":            # text columns also cut prose into "tables": keep id-keyed rows only
                rows = [r for r in rows if re.fullmatch(ID_LINE, r.key)]
            for r in rows:
                r.source = "pdf" if source == "lines" else "pdf-text"
            if rows:
                out[n] = rows
    return out


def pdf_rows(pdf: Path | None) -> dict[int, list[Row]]:
    """Every logical row of every table in ``pdf``, by page (cached per file and modification)."""
    if pdf is None or not pdf.is_file():
        return {}
    st = os.stat(pdf)
    try:
        return _pdf_tables(str(pdf), st.st_mtime, st.st_size)
    except Exception:  # noqa: BLE001 - an unreadable PDF falls back to the text, never a failed export
        return {}


def _locate(norm: str, nmap: list[int], piece: str, lo: int, hi: int) -> list[tuple[int, int]]:
    """Where ``piece`` occurs in the page as whole words: a piece that starts or ends inside a word (a cell
    split mid-word by the text strategy) is not found."""
    q = plain(piece)
    out, i = [], norm.find(q, lo, hi)
    while i >= 0 and q:
        j = i + len(q)
        starts = i == 0 or not (norm[i - 1].isalnum() and q[0].isalnum())
        ends = j >= len(norm) or not (norm[j].isalnum() and q[-1].isalnum())
        if starts and ends:
            out.append((nmap[i], nmap[j - 1] + 1))
        i = norm.find(q, i + 1, hi)
    return out


def place(row: Row, text: str, norm: str, nmap: list[int], page_range: tuple[int, int],
          other_keys: list[str]) -> tuple[int, int] | None:
    """The span of the page text that ``row``'s pieces account for, or ``None`` when a piece is missing, the
    pieces are not together, or another row's key line falls inside them."""
    from bisect import bisect_right

    lo = bisect_right(nmap, page_range[0] - 1)
    hi = bisect_right(nmap, page_range[1])
    key_hits = [(m.start(), m.end()) for m in re.finditer(rf"(?m)^{re.escape(row.key)}(?=[ \t]|$)",
                                                          text[page_range[0]:page_range[1]])]
    key_hits = [(a + page_range[0], b + page_range[0]) for a, b in key_hits]
    others = [p for p in row.pieces if p != row.key and len(p) >= 3]
    hits = [_locate(norm, nmap, p, lo, hi) for p in others]
    if not others or any(not h for h in hits):
        return None
    anchors = key_hits or hits[min(range(len(hits)), key=lambda i: len(hits[i]))]
    best: tuple[int, int] | None = None
    for a in anchors:
        mid = a[0]
        chosen = [min(h, key=lambda s: abs(s[0] - mid)) for h in hits]
        span = (min([a[0], *(s[0] for s in chosen)]), max([a[1], *(s[1] for s in chosen)]))
        if best is None or span[1] - span[0] < best[1] - best[0]:
            best = span
    if best is None:
        return None
    s, e = best
    s = text.rfind("\n", 0, s) + 1
    e2 = text.find("\n", e)
    e = len(text) if e2 < 0 else e2
    inside = text[s:e].split("\n")
    if len(inside) > len(row.pieces) + 2:                 # the pieces are not together
        return None
    for ln in inside:
        for k in other_keys:
            if k != row.key and re.match(rf"{re.escape(k)}(?=[ \t]|$)", ln):
                return None
    return s, e


def text_row(text: str, line: tuple[int, int], ident: str, page: int) -> Row | None:
    """A row rebuilt from the extracted text alone, only when it cannot be wrong: the id line holds the id and
    its text, and the lines just above and below it are themselves id lines of the same family (so the row
    has no words on the lines around it)."""
    s, e = line
    body = text[s:e]
    m = re.match(rf"{re.escape(ident)}[ \t]+(\S.*)$", body)
    if not m:
        return None
    prefix = re.match(r"[A-Z]+-?", ident).group(0)
    fam = rf"{re.escape(prefix)}\d+(?:\.\d+)?(?=[ \t]|$)"
    above_end = s - 1
    above = text[text.rfind("\n", 0, max(0, above_end)) + 1:above_end] if s > 0 else ""
    nxt = text.find("\n", e + 1)
    below = text[e + 1:len(text) if nxt < 0 else nxt] if e < len(text) else ""
    if re.match(fam, above) and re.match(fam, below):
        return Row(page, ident, [plain(m.group(1))], [plain(body)], span=(s, e), source="text")
    return None


def is_table_line(text: str, line: tuple[int, int], ident: str, page_range: tuple[int, int]) -> bool:
    """Whether the id's line looks like a table cell: the id alone on its line, or other lines of the same page
    that start with ids of the same family."""
    body = text[line[0]:line[1]].strip()
    if body == ident:
        return True
    prefix = re.match(r"[A-Z]+-?", ident).group(0)
    same = re.findall(rf"(?m)^{re.escape(prefix)}\d+(?:\.\d+)?(?=[ \t]|$)", text[page_range[0]:page_range[1]])
    return len(same) >= 2


@dataclass
class Chrome:
    """What the export shows beside a passage of the page text: a rebuilt row, or the plain table note."""

    span: tuple[int, int]
    page: int
    row: Row | None = None
    note: bool = False
    marks: list[str] = field(default_factory=list)


def same_words(a: str, b: str) -> bool:
    """Whether two texts say the same thing (word sets nearly equal), so a row is not shown twice."""
    wa, wb = (set(re.findall(r"[a-z0-9]+", plain(x).lower())) for x in (a, b))
    return bool(wa) and len(wa & wb) / len(wa | wb) >= 0.8
