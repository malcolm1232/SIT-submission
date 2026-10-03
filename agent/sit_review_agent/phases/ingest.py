"""``ingest`` (code only, workstream C).

Reads: the input PDF path(s) given to the orchestrator (``ctx.state.documents[*].pdf_path``).
Writes: ``ctx.documents`` (Document objects), ``text/<doc_id>.pages.txt`` and ``.sections.json``,
``ctx.state.documents`` (hashes, text_path, page_count, native_pdf), degradations
``input_degraded`` / ``ocr_used`` for image-only pages or the text-only fallback.

Inputs other than ``.pdf`` are read as text: a canonical page-marked text (``[[PAGE n]]``
markers, e.g. ``*.pages.txt`` from a previous run or the selftest fixture) or Markdown (no
markers: a page-less document whose anchors carry ``page: null``). Both are normalised with the
same :func:`~sit_review_agent.ingest.text.normalise` as extracted PDF text.

The background MCP warm-up is started by :func:`sit_review_agent.orchestrator.run_review` (it owns
the tool gateway and its lifetime), so cold starts still overlap ingest and understand.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from sit_review_agent.context import RunContext
from sit_review_agent.errors import InputError
from sit_review_agent.ingest.pdf import Document, ingest
from sit_review_agent.ingest.text import PAGE_MARKER_RE, normalise
from sit_review_agent.llm.backend import supports_native_pdf
from sit_review_agent.models import DegradationType, DocumentRole
from sit_review_agent.progress import ctx_event
from sit_review_agent.state.run_state import DocumentRef
from sit_review_agent.states import PhaseName

#: Suffixes stripped from a file name before it becomes a ``DOC-`` ID.
_ID_SUFFIXES = (".pages",)


def doc_id_for(path: str | Path, role: DocumentRole = DocumentRole.UNDER_REVIEW, *,
               taken: set[str] | None = None) -> str:
    """``DOC-<stem>`` (spec ``DocId``), unique within ``taken`` (a prior version with the same file
    name gets ``-prior``)."""
    stem = Path(path).name
    for suffix in (".pdf", ".txt", ".md", ".markdown"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    for suffix in _ID_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip("-.") or "document"
    did = clean if clean.startswith("DOC-") else "DOC-" + clean
    taken = taken or set()
    if did in taken:
        did += "-prior" if role is DocumentRole.PRIOR_VERSION else "-2"
    n = 2
    base = did
    while did in taken:
        n += 1
        did = f"{base}-{n}"
    return did


def placeholder_ref(path: str | Path, role: DocumentRole, *, taken: set[str] | None = None,
                    version: str | None = None) -> DocumentRef:
    """The ``DocumentRef`` the orchestrator seeds before ``ingest`` fills in hashes and paths."""
    return DocumentRef(doc_id=doc_id_for(path, role, taken=taken), role=role, title="", version=version,
                       pdf_path=str(path), sha256_text="", text_path="")


def load_input(ref: DocumentRef) -> Document:
    """Read one input into a canonical :class:`Document` (PDF via pdfplumber, else text).

    Raises :class:`InputError` for a missing, unreadable, encrypted or empty input."""
    if not ref.pdf_path:
        raise InputError(f"{ref.doc_id}: no input path")
    path = Path(ref.pdf_path)
    if not path.is_file():
        raise InputError(f"input not found: {path}")
    if path.suffix.lower() == ".pdf":
        doc = ingest(path, doc_id=ref.doc_id, role=ref.role, version=ref.version)
    else:
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise InputError(f"cannot read {path.name} as UTF-8 text: {type(exc).__name__}") from exc
        doc = Document.from_page_marked_text(normalise(raw), doc_id=ref.doc_id, role=ref.role)
        doc.source_path = str(path)
        doc.version = ref.version
        # pdfplumber is not involved: say so in the extractor record (manifest).
        doc.extractor = doc.extractor.model_copy(update={"name": "text", "version": "n/a"})
    if not PAGE_MARKER_RE.sub("", doc.text).strip():
        raise InputError(f"{path.name} contains no extractable text (empty, scanned or image-only; "
                         "OCR is not available)")
    if ref.title and not doc.title:
        doc.title = ref.title
    return doc


class IngestPhase:
    name = PhaseName.INGEST

    async def run(self, ctx: RunContext) -> RunContext:
        if not ctx.state.documents:
            raise InputError("no input document given")
        if not any(r.role is DocumentRole.UNDER_REVIEW for r in ctx.state.documents):
            raise InputError("no document with role under_review")
        native_backend = supports_native_pdf(ctx.llm)
        refs: list[DocumentRef] = []
        docs: dict[str, Document] = {}
        for ref in ctx.state.documents:
            # In a worker thread: pdfplumber is CPU-bound, and the background MCP warm-up started
            # by run_review must keep making progress while it runs (robustness §10 item 2).
            doc = await asyncio.to_thread(load_input, ref)
            meta = doc.write(ctx.run_dir)
            native = doc.pdf_bytes is not None and doc.native_pdf_ok and native_backend
            refs.append(DocumentRef(
                doc_id=doc.doc_id, role=doc.role, title=doc.title, version=doc.version, pdf_path=ref.pdf_path,
                sha256_pdf=doc.sha256_pdf, sha256_text=doc.sha256_text, text_path=meta.text_path,
                page_count=doc.page_count, native_pdf=native))
            docs[doc.doc_id] = doc
            image_only = sorted(p.number for p in doc.pages if p.image_only)
            if image_only:
                ctx.state.add_degradation(
                    DegradationType.INPUT_DEGRADED,
                    f"{doc.doc_id}: pages {image_only} are image-only (fewer than 50 extracted characters); "
                    "no OCR was run",
                    "content that exists only as images on those pages was not quoted or checked")
            if doc.pdf_bytes is not None and not native:
                why = ("the PDF exceeds the native document limits (600 pages / request size)"
                       if not doc.native_pdf_ok else "the configured model backend accepts text only")
                ctx.state.add_degradation(
                    DegradationType.INPUT_DEGRADED,
                    f"{doc.doc_id}: native PDF block not sent because {why}",
                    "figures, diagrams and tables rendered as images were not visible to the model; "
                    "the review is based on the extracted text")
            ctx_event(ctx, f"{doc.doc_id} ({doc.role.value}): {doc.page_count or 0} pages, "
                      f"{len(doc.sections)} sections, {len(doc.requirement_index)} requirement IDs, text sha256 "
                      f"{doc.sha256_text[:12]}",
                      event="document_ingested", doc_id=doc.doc_id, role=doc.role.value, pages=doc.page_count or 0,
                      sections=len(doc.sections), requirement_ids=len(doc.requirement_index),
                      sha256_text=doc.sha256_text[:12], title=doc.title or None)
        ctx.state.documents = refs
        ctx.documents = docs
        return ctx
