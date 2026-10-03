"""``understand`` (LLM, workstream A). Prompt: ``prompts/understand.md``. Output: ``UnderstandOutput``.

Reads: documents, criteria, persona.
Writes: ``ctx.state.intent_summary`` (IntentSummary; anchors verified later by verify),
``ctx.registry`` entries (``AD-nnn``) then ``ctx.registry.freeze()``, ``review_inputs_found``.
Effort: ``config.effort_for(UNDERSTAND)`` (= the ``plan`` level; same conversation prefix).

Implementation notes (workstream A):

* conversation ``understand-0`` (retries ``understand-0-r<k>``, see ``phases/_model_calls.py``);
* anchors get the cheap code fixes of :func:`~sit_review_agent.phases._model_calls.fix_anchor`; an
  intent anchor or registry entry that still breaks the spec (for example a quote under 8 words that
  is not found verbatim) is dropped and disclosed as a degradation, because ``RunState`` holds the
  canonical types. If no intent anchor survives, a verbatim anchor from the first page is used
  (also disclosed);
* after the registry is frozen its hash is recorded as iteration 0
  (``research_log.registry_sha256_by_iteration`` needs at least one entry even when research is
  disabled); ``ctx.sync_state()`` copies the registry into ``state``;
* ``UnderstandOutput.document_version`` has no field of its own: it fills the under-review
  document's ``version`` (``state.documents`` and ``ctx.documents``) when that is still empty;
* a persistent refusal leaves ``intent_summary`` empty and the registry empty but frozen.
"""

from __future__ import annotations

from sit_review_agent.context import RunContext
from sit_review_agent.errors import RegistryFrozenError
from sit_review_agent.llm.outputs import RefTextDraft, UnderstandOutput
from sit_review_agent.models import DegradationType, DocumentRole, IntentSummary, RefText, RegistryEntryType
from sit_review_agent.phases._model_calls import (
    call_model,
    criteria_vars,
    document_vars,
    fallback_anchor,
    fix_anchor,
    spec_anchor,
    summarise,
    unique_anchors,
)
from sit_review_agent.progress import ctx_event
from sit_review_agent.prompts import RenderedPrompt
from sit_review_agent.states import PhaseName


def _ref_texts(items: list[RefTextDraft]) -> list[RefText]:
    return [RefText(ref=(i.ref or "").strip() or None, text=i.text.strip()) for i in items if i.text.strip()]


class UnderstandPhase:
    name = PhaseName.UNDERSTAND

    async def run(self, ctx: RunContext) -> RunContext:
        phase = self.name
        ctx_event(ctx, "reading the design: intent, objectives, constraints and the decision registry",
                  event="understand_started")

        def render(*, reframed: bool, schema_error: str) -> RenderedPrompt:
            return ctx.prompts.render("understand.md", criteria=criteria_vars(ctx), documents=document_vars(ctx),
                                      review_mode=ctx.state.review_mode.value, reframed=reframed,
                                      schema_error=schema_error)

        call = await call_model(ctx, phase, render, UnderstandOutput, iteration=0, purpose="understand")
        if call.result is None or not isinstance(call.result.parsed, UnderstandOutput):
            self._freeze(ctx)
            return ctx
        out = call.result.parsed

        # ---- decision registry (before the intent: its anchors are a fallback for the intent)
        dropped: list[str] = []
        if not ctx.registry.frozen:
            for draft in out.registry:
                if not draft.statement.strip() or not draft.doc_ref.strip():
                    dropped.append(draft.doc_ref or "(no reference)")
                    continue
                fixed = draft.model_copy(update={"doc_anchor": fix_anchor(ctx, draft.doc_anchor),
                                                 "doc_ref": draft.doc_ref.strip(),
                                                 "statement": draft.statement.strip()})
                if spec_anchor(ctx, fixed.doc_anchor) is None:
                    dropped.append(fixed.doc_ref)
                    continue
                try:
                    ctx.registry.add(fixed)
                except RegistryFrozenError:  # pragma: no cover - guarded above
                    break
        if dropped:
            ctx.state.add_degradation(
                DegradationType.OTHER,
                f"{len(dropped)} decision-registry entries had no valid verbatim location and were dropped: "
                + ", ".join(dropped[:10]),
                "decision-preservation checks (INV-10) cannot reference these entries")

        # ---- intent summary
        anchors = unique_anchors(a for a in (spec_anchor(ctx, x) for x in out.intent_summary.doc_anchors)
                                 if a is not None)
        if not anchors:
            fb = next((e.doc_anchor for e in ctx.registry.entries()), None) or fallback_anchor(ctx)
            if fb is not None:
                anchors = [fb]
                ctx.state.add_degradation(
                    DegradationType.OTHER, "the intent summary had no valid verbatim location; a location from "
                    "the document was attached by code", "the intent summary's location is less specific")
        statement = out.intent_summary.statement.strip()
        if anchors and statement:
            ctx.state.intent_summary = IntentSummary(
                statement=statement, objectives=_ref_texts(out.intent_summary.objectives),
                constraints=_ref_texts(out.intent_summary.constraints),
                key_assumptions=_ref_texts(out.intent_summary.key_assumptions), doc_anchors=anchors[:3])
        else:
            ctx.state.add_degradation(DegradationType.OTHER, "the model returned no usable intent summary",
                                      "the report has no cited restatement of the design intent")

        ctx.state.review_inputs_found = [s.strip() for s in out.review_inputs_found if s.strip()]
        version = (out.document_version or "").strip()
        if version:
            for ref in ctx.state.documents:
                if ref.role is DocumentRole.UNDER_REVIEW and ref.version is None:
                    ref.version = version
            for doc in ctx.documents.values():
                if doc.role is DocumentRole.UNDER_REVIEW and doc.version is None:
                    doc.version = version

        self._freeze(ctx)
        intent = ctx.state.intent_summary
        ctx_event(ctx, f"intent: {len(intent.objectives) if intent else 0} objectives, "
                  f"{len(intent.constraints) if intent else 0} constraints; registry: "
                  f"{summarise(ctx.registry.entries(), lambda e: e.type.value)} "
                  f"(frozen, sha256 {ctx.registry.sha256()[:12]})", "done", event="intent_ready",
                  objectives=len(intent.objectives) if intent else 0,
                  constraints=len(intent.constraints) if intent else 0, registry_entries=len(ctx.registry.entries()),
                  registry_sha256=ctx.registry.sha256()[:12])
        approved = len([e for e in ctx.registry.entries() if e.type is RegistryEntryType.APPROVED_DECISION])
        if ctx.state.review_inputs_found:
            ctx_event(ctx, f"{len(ctx.state.review_inputs_found)} review comments or claimed fixes found in the "
                      f"document (treated as claims to check); {approved} approved decisions to preserve",
                      event="review_inputs_found", review_inputs=len(ctx.state.review_inputs_found),
                      approved_decisions=approved)
        return ctx

    @staticmethod
    def _freeze(ctx: RunContext) -> None:
        if not ctx.registry.frozen:
            ctx.registry.freeze()
        if not ctx.registry.hashes():
            ctx.registry.record_iteration(0)
        ctx.sync_state()
