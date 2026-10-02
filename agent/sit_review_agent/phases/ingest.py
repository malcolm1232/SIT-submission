"""``ingest`` (code only, workstream C).

Reads: the input PDF path(s) given to the orchestrator (``ctx.state.documents[*].pdf_path``).
Writes: ``ctx.documents`` (Document objects), ``text/<doc_id>.pages.txt`` and ``.sections.json``,
``ctx.state.documents`` (hashes, text_path, page_count, native_pdf), degradations
``input_degraded`` / ``ocr_used`` for image-only pages or the text-only fallback.
Also starts the background MCP warm-up (``MCPToolGateway.warm_up``) so cold starts overlap
ingest and understand (robustness §10 item 2).
"""

from __future__ import annotations

from sit_review_agent.context import RunContext
from sit_review_agent.states import PhaseName


class IngestPhase:
    name = PhaseName.INGEST

    async def run(self, ctx: RunContext) -> RunContext:
        raise NotImplementedError("phase 3: IngestPhase.run (workstream C)")
