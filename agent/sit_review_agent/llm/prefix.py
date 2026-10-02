"""The byte-stable cached prefix shared by every conversation (ADR-002, ADR-006).

Render order is ``tools -> system -> messages``. Every phase starts its conversation with the same
system prompt (``prompts/system.md``) and the same first user message built here: for each
document, the native PDF block (when allowed) and the canonical page-marked text block. One
explicit cache breakpoint sits on the last block of that message; the phase brief follows in a
*separate* user turn so the prefix is identical across phases. Nothing volatile (dates, run IDs)
may appear in the prefix (REPRODUCIBILITY §4).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sit_review_agent.ingest.pdf import Document
from sit_review_agent.llm.gateway import CacheBreakpoint


def document_prefix_message(docs: Sequence[Document], *, native_pdf: bool = True) -> tuple[dict[str, Any], CacheBreakpoint]:
    """First user message (documents) and the cache breakpoint after its last block.

    Documents are emitted in the given order (under-review first, then prior version). A document
    whose :attr:`Document.native_pdf_ok` is false is sent as text only (disclosed by the caller).
    """
    blocks: list[dict[str, Any]] = []
    for d in docs:
        if native_pdf and d.native_pdf_ok:
            blocks.append(d.document_block())
        blocks.append(d.canonical_text_block())
    if not blocks:
        raise ValueError("document_prefix_message needs at least one document")
    return {"role": "user", "content": blocks}, CacheBreakpoint(message_index=0, block_index=len(blocks) - 1)


def start_conversation(docs: Sequence[Document], brief: str, *, native_pdf: bool = True) -> tuple[list[dict[str, Any]], CacheBreakpoint]:
    """Initial ``messages`` for a phase conversation: one user turn holding the document blocks,
    with the phase ``brief`` appended as a final text block *after* the breakpointed block, so the
    cached prefix is identical across phases. Returns the messages and the breakpoint to send."""
    msg, bp = document_prefix_message(docs, native_pdf=native_pdf)
    msg = {"role": "user", "content": [*msg["content"], {"type": "text", "text": brief}]}
    return [msg], bp
