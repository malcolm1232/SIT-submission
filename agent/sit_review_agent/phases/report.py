"""``report`` (LLM for verdict/unresolved/limitations text, then code; workstream C).
Prompt: ``prompts/report.md``. Output: ``ReportOutput``.

Assembles the :class:`~sit_review_agent.models.Review` (:func:`assemble_review`), validates it
against the spec (INV-03) and the invariants, writes ``report.json``, ``ledger.json``, renders
``report.md`` (``report.render.render_markdown``), and finalises ``manifest.json``. Every
degradation is cited by a limitation (INV-07). A capped run (deadline) still reports, with a
partial-evidence caveat; if the model is unavailable the verdict text falls back to an LLM-free
template that says so (fresh_eyes N3).
"""

from __future__ import annotations

from sit_review_agent.context import RunContext
from sit_review_agent.models import Review
from sit_review_agent.states import PhaseName


def assemble_review(ctx: RunContext) -> Review:
    """Build the Review envelope from ``ctx.state``, the ledger, the registry and the manifest."""
    raise NotImplementedError("phase 3: assemble_review (workstream C)")


class ReportPhase:
    name = PhaseName.REPORT

    async def run(self, ctx: RunContext) -> RunContext:
        raise NotImplementedError("phase 3: ReportPhase.run (workstream C)")
