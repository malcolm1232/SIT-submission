"""``assess`` (LLM, workstream A). Prompt: ``prompts/assess.md``. Output: ``AssessOutput``.

Reads: intent, registry, criteria, plan answers, ledger (IDs + excerpts only).
Writes: ``state.finding_drafts`` (FND-nnn, each with ``criterion_ids``), ``state.finding_meta``
(created_phase=assess, call ID, model, prompt hash), ``state.sound_area_drafts``,
``state.coverage`` (every criterion: findings / no_issue / not_applicable).
Refusal: one retry with professional-review framing, then the section is recorded in
``state.declined_sections`` and the phase completes (robustness LLM-06).

Implementation notes (workstream A):

* conversation ``assess-<n>`` with ``n = state.budget.research_iterations`` (also the
  ``FindingMeta.iteration`` / provenance iteration of every finding raised here);
* ``FindingMeta.prompt_hash`` is the SHA-256 of the rendered phase brief (``RenderedPrompt.sha256``);
* drafts are normalised in code (``_model_calls.normalise_findings``): IDs renumbered
  ``FND-001..`` when the model's are malformed or duplicated (references in sound areas and
  coverage follow the renumbering), ranks made ``1..n``, confidence clamped, criteria filtered,
  short verbatim quotes extended, ``reassessment`` set per review mode. Taxonomy rules (strength
  has no severity, ``no_change`` has no recommendation, ...) are left to ``refine`` and ``verify``;
* evidence: the model cites register IDs and gives new ``doc``/``inference`` items temporary
  ``NEW-n`` IDs; ``_model_calls.resolve_evidence`` adds those to the ledger (``ctx.ledger.add_doc`` /
  ``add_inference``) and rewrites the citations, so ``verify`` can hydrate every one. This writes
  ledger entries, which the "Writes" list above does not name: without them doc-only findings
  could not carry the ``supporting_evidence_ids`` the spec requires;
* coverage has exactly one row per configured criterion, consistent with the findings
  (``_model_calls.reconcile_coverage``);
* the phase replaces (not appends to) the four fields, so a re-run from the checkpoint is safe;
* after a persistent refusal: no findings, every criterion's coverage row says it was not assessed;
* when the run deadline cuts the call (robustness LLM-05): the same, disclosed as "out of time
  before assessment"; nothing is made up, and ``report`` skips the model verdict.
"""

from __future__ import annotations

from sit_review_agent.context import RunContext
from sit_review_agent.llm.outputs import AssessOutput, CriterionCoverage
from sit_review_agent.phases._model_calls import (
    answer_vars,
    call_model,
    criteria_vars,
    document_vars,
    evidence_vars,
    intent_vars,
    known_criteria,
    normalise_findings,
    normalise_sound_areas,
    prior_finding_vars,
    reconcile_coverage,
    registry_vars,
    resolve_evidence,
    summarise,
)
from sit_review_agent.prompts import RenderedPrompt
from sit_review_agent.state.run_state import FindingMeta
from sit_review_agent.states import PhaseName


class AssessPhase:
    name = PhaseName.ASSESS

    async def run(self, ctx: RunContext) -> RunContext:
        phase = self.name
        iteration = ctx.state.budget.research_iterations
        evidence = evidence_vars(ctx)
        ctx.emit(f"assessing the design against {len(known_criteria(ctx))} criteria with "
                 f"{len(evidence)} evidence entries")

        def render(*, reframed: bool, schema_error: str) -> RenderedPrompt:
            return ctx.prompts.render(
                "assess.md", criteria=criteria_vars(ctx), registry=registry_vars(ctx), intent=intent_vars(ctx),
                answers=answer_vars(ctx), evidence=evidence, documents=document_vars(ctx),
                unanswered=list(ctx.state.unanswered_questions), review_inputs=list(ctx.state.review_inputs_found),
                review_mode=ctx.state.review_mode.value, prior_findings=prior_finding_vars(ctx),
                reframed=reframed, schema_error=schema_error)

        call = await call_model(ctx, phase, render, AssessOutput, iteration=iteration, purpose="assess")
        result = call.result
        if result is None or not isinstance(result.parsed, AssessOutput):
            ctx.state.finding_drafts = []
            ctx.state.finding_meta = {}
            ctx.state.sound_area_drafts = []
            note = ("not assessed: out of time before assessment (run deadline)" if call.cut
                    else "not assessed: the model declined the assess call")
            ctx.state.coverage = [CriterionCoverage(criterion_id=c, outcome="not_applicable", finding_ids=[],
                                                    note=note) for c in known_criteria(ctx)]
            return ctx
        out = result.parsed

        findings, id_map = normalise_findings(ctx, out.findings)
        ids = {f.id for f in findings}
        areas = normalise_sound_areas(ctx, out.sound_areas, id_map, ids)
        findings, areas, stats = resolve_evidence(ctx, findings, areas)
        ctx.state.finding_drafts = findings
        ctx.state.finding_meta = {
            f.id: FindingMeta(finding_id=f.id, criterion_ids=list(f.criterion_ids), created_phase=phase,
                              created_call_id=result.call_id, last_phase=phase, last_call_id=result.call_id,
                              model=result.model, prompt_hash=call.brief.sha256, iteration=iteration)
            for f in findings}
        ctx.state.sound_area_drafts = areas
        ctx.state.coverage = reconcile_coverage(ctx, out.coverage, findings, id_map)

        ctx.emit(f"{len(findings)} findings ({summarise(findings, lambda f: f.kind.value)}); "
                 f"{len(ctx.state.sound_area_drafts)} sound areas; coverage: "
                 f"{summarise(ctx.state.coverage, lambda c: c.outcome)}; evidence: {stats.doc_added} doc and "
                 f"{stats.inference_added} inference entries added to the ledger", "done")
        if stats.dropped:
            ctx.emit(f"{stats.dropped} evidence citations dropped (not in the evidence register)", "warn")
        return ctx
