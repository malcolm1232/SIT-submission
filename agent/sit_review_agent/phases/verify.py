"""``verify`` (code, plus one optional anchor-repair LLM call; workstream C).
Prompt: ``prompts/verify.md``. Output of the repair call: ``AnchorRepairOutput``.

1. Verify every anchor (findings, sound areas, registry, intent) with
   ``ingest.anchor.verify_finding_anchors``; one repair turn for failures; rows into
   ``state.anchor_table`` and ``anchors.json`` (resolved / repaired / unresolved).
2. Hydrate drafts into canonical ``Finding`` objects (:func:`hydrate_finding`): evidence from the
   ledger, provenance from ``finding_meta``; drop anchors beyond 3.
3. Code checks (fresh_eyes §1.6 "complete, consistent, accurate, traceable"): unknown evidence IDs,
   URLs in free text not in the ledger, registry conflicts, non-refinement findings in
   ``unresolved``, verdict vs severities. A finding with no resolvable anchor cannot carry a
   recommendation (ADR-007): it is moved to ``unresolved`` and reported as unverified.
Writes: ``state.findings``, ``state.sound_areas``, ``state.anchor_table``, degradations.
"""

from __future__ import annotations

from sit_review_agent.context import RunContext
from sit_review_agent.llm.outputs import FindingDraft
from sit_review_agent.models import Finding
from sit_review_agent.state.evidence_ledger import EvidenceLedger
from sit_review_agent.state.run_state import FindingMeta
from sit_review_agent.states import PhaseName


def hydrate_finding(draft: FindingDraft, ledger: EvidenceLedger, meta: FindingMeta) -> Finding:
    """Canonical Finding from a draft: ``ledger.hydrate`` each citation, ``Provenance`` from
    ``meta`` (``states.PROVENANCE_PHASE[meta.last_phase]``, ``meta.model``, ``meta.prompt_hash``),
    ``criterion_ids`` dropped. Raises ``pydantic.ValidationError`` / ``LedgerError`` if invalid."""
    raise NotImplementedError("phase 3: hydrate_finding (workstream C)")


class VerifyPhase:
    name = PhaseName.VERIFY

    async def run(self, ctx: RunContext) -> RunContext:
        raise NotImplementedError("phase 3: VerifyPhase.run (workstream C)")
