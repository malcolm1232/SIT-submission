"""PDF ingestion (ADR-006): one pinned extractor (pdfplumber) produces the canonical page-marked
text every verifier reads; the raw bytes go to the model as a native ``document`` block.

:func:`ingest` is the only entry point for PDFs. :meth:`Document.from_page_marked_text` builds the
same object from canonical text alone (tests, Markdown fixtures, resume from a run directory).
"""

from __future__ import annotations

import base64
import bisect
import io
import json
import re
from dataclasses import dataclass, field
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any

from sit_review_agent.errors import InputError
from sit_review_agent.hashing import sha256_bytes, sha256_text
from sit_review_agent.ingest.text import (
    NORMALISATION_VERSION,
    PAGE_MARKER_LABEL,
    PAGE_MARKER_RE,
    normalise,
    page_marker,
)
from sit_review_agent.models import DocumentMeta, DocumentRole, ExtractorInfo
from sit_review_agent.rundir import RunDir, write_json_atomic

#: Native PDF block limits (claude-api skill): 600 pages, 32 MB per *request*. Base64 inflates by
#: 4/3 and the request also carries the canonical text, so ingest checks the encoded size.
MAX_NATIVE_PAGES = 600
MAX_REQUEST_BYTES = 32 * 1024 * 1024
#: A page with fewer extracted characters than this but at least one image is "image-only" (INP-04).
IMAGE_ONLY_MAX_CHARS = 50

#: Numbered heading at line start ("6.2 Notifications", "10.Room bookings"). Heuristic: numbered
#: lists can match too; duplicates are tolerated (find_sections returns every candidate).
_HEADING_RE = re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,3}){0,4})(?:\.\s*|\s+)(?P<title>[A-Z][^\n]*)$", re.M)
#: Requirement / decision / constraint IDs such as FR-9, NFR-7, AC-12, D-3, SEC-AUTH-2 (spec §2.2).
REQUIREMENT_ID_RE = re.compile(r"\b[A-Z]{1,4}(?:-[A-Z]+)*-\d+\b")
_SECTION_NUM_RE = re.compile(r"\d{1,2}(?:\.\d{1,3})*")


@dataclass(frozen=True)
class Page:
    number: int                 # 1-based page number as printed in the marker
    char_start: int             # offset of the page body in Document.text (after the marker line)
    char_end: int               # exclusive
    image_only: bool = False


@dataclass(frozen=True)
class Section:
    order: int                  # 0-based position in document order (the "+/-1" window uses this)
    section_id: str             # number as printed, e.g. "6.2"
    heading: str                # heading text without the number
    level: int                  # 1 for "6", 2 for "6.2", ...
    char_start: int
    char_end: int               # exclusive; start of the next section or end of text
    page_start: int
    page_end: int


@dataclass(frozen=True)
class RequirementRef:
    req_id: str
    page: int | None
    section_id: str | None
    char_start: int


@dataclass
class Document:
    """A document under review (or a prior version) in canonical form."""

    doc_id: str
    title: str
    text: str                                   # canonical page-marked text (doc.pages.txt)
    pages: list[Page]
    sections: list[Section]
    requirement_index: dict[str, list[RequirementRef]]
    pdf_bytes: bytes | None = None
    source_path: str | None = None
    role: DocumentRole = DocumentRole.UNDER_REVIEW
    version: str | None = None
    extractor: ExtractorInfo = field(default_factory=lambda: ExtractorInfo(
        name="pdfplumber", version=_safe_version("pdfplumber"), page_marker=PAGE_MARKER_LABEL))
    normalisation_version: str = NORMALISATION_VERSION
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ derived properties
    @property
    def sha256_text(self) -> str:
        return sha256_text(self.text)

    @property
    def sha256_pdf(self) -> str | None:
        return sha256_bytes(self.pdf_bytes) if self.pdf_bytes is not None else None

    @property
    def page_count(self) -> int | None:
        return max((p.number for p in self.pages), default=None)

    @property
    def native_pdf_ok(self) -> bool:
        """Whether the native PDF block can be sent (else text only, disclosed; ADR-006 item 3)."""
        if self.pdf_bytes is None or (self.page_count or 0) > MAX_NATIVE_PAGES:
            return False
        encoded = 4 * ((len(self.pdf_bytes) + 2) // 3)
        return encoded + len(self.text.encode("utf-8")) + 1_000_000 < MAX_REQUEST_BYTES

    # ------------------------------------------------------------------ lookups
    def page(self, number: int) -> Page | None:
        return next((p for p in self.pages if p.number == number), None)

    def page_text(self, number: int) -> str:
        p = self.page(number)
        return self.text[p.char_start:p.char_end] if p else ""

    def page_at(self, offset: int) -> int | None:
        """Page number containing character ``offset`` of :attr:`text`."""
        starts = [p.char_start for p in self.pages]
        i = bisect.bisect_right(starts, offset) - 1
        return self.pages[i].number if i >= 0 else None

    def section_at(self, offset: int) -> Section | None:
        starts = [s.char_start for s in self.sections]
        i = bisect.bisect_right(starts, offset) - 1
        return self.sections[i] if i >= 0 else None

    def find_sections(self, section_ref: str) -> list[Section]:
        """Every section a ``DocAnchor.section_ref`` ("6.2", "§6.2", "20 Decisions", a heading) may
        mean, in document order. Several candidates are possible when numbering repeats (a table of
        contents that survived filtering, numbered lists); the anchor check tries each."""
        m = _SECTION_NUM_RE.search(section_ref)
        if m:
            hits = [s for s in self.sections if s.section_id == m.group(0)]
            if hits:
                return hits
        ref = section_ref.strip().lower()
        if not ref:
            return []
        return [s for s in self.sections if s.heading.lower() == ref or (len(ref) >= 4 and ref in s.heading.lower())]

    def find_section(self, section_ref: str) -> Section | None:
        """The last candidate of :meth:`find_sections` (body text follows any table of contents)."""
        hits = self.find_sections(section_ref)
        return hits[-1] if hits else None

    # ------------------------------------------------------------------ model-facing blocks
    def document_block(self) -> dict[str, Any]:
        """Native PDF content block (base64, no beta). Raises if there are no PDF bytes."""
        if self.pdf_bytes is None:
            raise InputError(f"{self.doc_id}: no PDF bytes for a native document block")
        return {"type": "document", "title": self.title,
                "source": {"type": "base64", "media_type": "application/pdf",
                           "data": base64.b64encode(self.pdf_bytes).decode("ascii")}}

    def canonical_text_block(self) -> dict[str, Any]:
        """The page-marked text as a text block. Byte-stable (part of the cached prefix)."""
        header = (f"<canonical_text doc_id=\"{self.doc_id}\">\n"
                  f"Quote only from this text. Page markers look like {PAGE_MARKER_LABEL}.\n")
        return {"type": "text", "text": header + self.text + "\n</canonical_text>"}

    # ------------------------------------------------------------------ persistence
    def meta(self, run_dir: RunDir) -> DocumentMeta:
        return DocumentMeta(doc_id=self.doc_id, title=self.title, version=self.version, role=self.role,
                            sha256_pdf=self.sha256_pdf, sha256_text=self.sha256_text,
                            text_path=run_dir.relative(run_dir.doc_text(self.doc_id)),
                            page_count=self.page_count)

    def write(self, run_dir: RunDir) -> DocumentMeta:
        """Write ``text/<doc_id>.pages.txt`` and ``.sections.json``; return the Review metadata."""
        path = run_dir.doc_text(self.doc_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.text, encoding="utf-8")
        write_json_atomic(run_dir.doc_sections(self.doc_id), {
            "doc_id": self.doc_id, "sha256_text": self.sha256_text,
            "sections": [s.__dict__ for s in self.sections],
            "pages": [p.__dict__ for p in self.pages], "warnings": self.warnings,
        })
        return self.meta(run_dir)

    @classmethod
    def load(cls, run_dir: RunDir, doc_id: str, *, pdf_path: str | Path | None = None,
             title: str = "", role: DocumentRole = DocumentRole.UNDER_REVIEW) -> Document:
        """Rebuild from a run directory (resume, ``explain``, invariants)."""
        text = run_dir.doc_text(doc_id).read_text(encoding="utf-8")
        doc = cls.from_page_marked_text(text, doc_id=doc_id, title=title, role=role)
        side = run_dir.doc_sections(doc_id)
        if side.exists():
            data = json.loads(side.read_text(encoding="utf-8"))
            image_only = {p["number"] for p in data.get("pages", []) if p.get("image_only")}
            doc.pages = [Page(p.number, p.char_start, p.char_end, p.number in image_only) for p in doc.pages]
            doc.warnings = list(data.get("warnings", []))
        if pdf_path is not None:
            doc.pdf_bytes = Path(pdf_path).read_bytes()
            doc.source_path = str(pdf_path)
        return doc

    @classmethod
    def from_page_marked_text(cls, text: str, *, doc_id: str, title: str = "",
                              role: DocumentRole = DocumentRole.UNDER_REVIEW,
                              pdf_bytes: bytes | None = None) -> Document:
        """Parse canonical page-marked text into pages, sections and the requirement index.

        ``text`` must already be canonical (see :func:`~sit_review_agent.ingest.text.normalise`).
        Text without any page marker is treated as a single page-less document (Markdown).
        """
        pages = _parse_pages(text)
        sections = _parse_sections(text, pages)
        doc = cls(doc_id=doc_id, title=title or _first_line(text), text=text, pages=pages, sections=sections,
                  requirement_index={}, pdf_bytes=pdf_bytes, role=role)
        doc.requirement_index = _index_requirements(doc)
        return doc


def _safe_version(pkg: str) -> str:
    try:
        return _pkg_version(pkg)
    except Exception:  # noqa: BLE001 - metadata missing in odd installs
        return "unknown"


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip() and not PAGE_MARKER_RE.fullmatch(line.strip()):
            return line.strip()[:120]
    return ""


def _parse_pages(text: str) -> list[Page]:
    marks = list(PAGE_MARKER_RE.finditer(text))
    pages: list[Page] = []
    for i, m in enumerate(marks):
        start = m.end() + (1 if text[m.end():m.end() + 1] == "\n" else 0)
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        pages.append(Page(number=int(m.group(1)), char_start=start, char_end=end))
    return pages


def _page_of(pages: list[Page], offset: int) -> int:
    starts = [p.char_start for p in pages]
    i = bisect.bisect_right(starts, offset) - 1
    return pages[max(i, 0)].number if pages else 1


def _parse_sections(text: str, pages: list[Page]) -> list[Section]:
    heads = []
    for m in _HEADING_RE.finditer(text):
        title = m.group("title").strip()
        cut = title.find(". ")
        if 0 < cut <= 80:
            title = title[:cut]
        heads.append((m.start(), m.group("num"), title[:120], m.end()))
    # Drop table-of-contents entries: a heading with no body text before the next heading whose
    # number appears again later in the document.
    kept: list[tuple[int, str, str]] = []
    for i, (start, num, title, line_end) in enumerate(heads):
        next_start = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        empty_body = not PAGE_MARKER_RE.sub("", text[line_end:next_start]).strip()
        if empty_body and any(h[1] == num for h in heads[i + 1:]):
            continue
        kept.append((start, num, title))
    out: list[Section] = []
    for i, (start, num, title) in enumerate(kept):
        end = kept[i + 1][0] if i + 1 < len(kept) else len(text)
        out.append(Section(order=i, section_id=num, heading=title.rstrip("."), level=num.count(".") + 1,
                           char_start=start, char_end=end, page_start=_page_of(pages, start),
                           page_end=_page_of(pages, max(start, end - 1))))
    return out


def _index_requirements(doc: Document) -> dict[str, list[RequirementRef]]:
    idx: dict[str, list[RequirementRef]] = {}
    for m in REQUIREMENT_ID_RE.finditer(doc.text):
        sec = doc.section_at(m.start())
        idx.setdefault(m.group(0), []).append(RequirementRef(
            req_id=m.group(0), page=doc.page_at(m.start()) if doc.pages else None,
            section_id=sec.section_id if sec else None, char_start=m.start()))
    return idx


def ingest(path: str | Path, *, doc_id: str | None = None, role: DocumentRole = DocumentRole.UNDER_REVIEW,
           version: str | None = None) -> Document:
    """Read a PDF with pdfplumber and return its canonical :class:`Document`.

    Every page's text is normalised and prefixed with its ``[[PAGE n]]`` marker. Pages with almost
    no text but an image are flagged ``image_only`` (OCR is a P1 add-on). Raises
    :class:`~sit_review_agent.errors.InputError` for unreadable, encrypted or empty PDFs.
    """
    import pdfplumber  # local import: heavy, and not needed by tests that build Documents from text

    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise InputError(f"cannot read {p}: {exc}") from exc
    chunks: list[str] = []
    image_only: set[int] = set()
    title = ""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            title = str((pdf.metadata or {}).get("Title") or "").strip()
            for i, page in enumerate(pdf.pages, start=1):
                body = normalise(page.extract_text() or "")
                if len(body) < IMAGE_ONLY_MAX_CHARS and page.images:
                    image_only.add(i)
                chunks.append(f"{page_marker(i)}\n{body}\n")
    except Exception as exc:  # noqa: BLE001 - pdfminer raises many unrelated types for bad input
        raise InputError(f"cannot extract text from {p.name}: {type(exc).__name__}: {exc}") from exc
    if not chunks:
        raise InputError(f"{p.name} has no pages")
    text = "".join(chunks)
    did = doc_id or "DOC-" + re.sub(r"[^A-Za-z0-9_.-]+", "-", p.stem).strip("-")
    doc = Document.from_page_marked_text(text, doc_id=did, title=title, role=role, pdf_bytes=data)
    doc.source_path = str(p)
    doc.version = version
    doc.pages = [Page(pg.number, pg.char_start, pg.char_end, pg.number in image_only) for pg in doc.pages]
    if image_only:
        doc.warnings.append(f"image-only pages (no OCR): {sorted(image_only)}")
    if not doc.native_pdf_ok:
        doc.warnings.append("native PDF block not sent (page or size limit); text-only review")
    return doc
