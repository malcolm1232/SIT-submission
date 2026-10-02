"""``refine`` (LLM, workstream A; optional). Prompt: ``prompts/refine.md``. Output: ``RefineOutput``.

One self-critique pass over the drafts: drop unsupported findings, merge duplicates, fix
disposition / severity against the taxonomy, make recommendations specific (BEH-07), label
registry conflicts (INV-10). Writes: ``state.finding_drafts`` (full revised set) and a
``FindingRevision`` per changed finding in ``state.finding_meta[...].history`` (phase refine ->
provenance ``revise``). Delta mode: sets ``reassessment`` on every finding.

Implementation notes (workstream A):

* conversation ``refine-<n>`` (``n`` = completed research iterations, as in ``assess``);
* IDs: a returned finding whose ID is an existing draft keeps it (a revision); any other finding is
  new and gets its own valid unused ID (the model's if it is ``FND-nnn`` and never used in the run,
  else the next free number), so IDs of withdrawn findings are never reused;
* ``finding_meta``: a changed finding gets a ``FindingRevision(phase=refine, changed_fields=
  {field: [before, after]}, note=<revision reason>)`` and ``last_phase=refine`` (provenance
  ``revise``), with the call's model and brief hash; an unchanged finding keeps its meta; a new one
  gets ``created_phase=refine``; a withdrawn or merged one keeps its meta with a history note
  ("withdrawn: ..." / "merged: ...") and leaves ``finding_drafts``. The model's ``RevisionNote``\\ s
  live only in these history notes (``RunState`` has no other field for them);
* new ``doc``/``inference`` evidence (temporary ``NEW-n`` IDs) is added to the ledger as in
  ``assess`` (``_model_calls.resolve_evidence``);
* derived fields kept consistent: ``state.coverage`` finding IDs (and outcomes) and
  ``state.sound_area_drafts`` related finding IDs drop withdrawn findings and pick up new ones;
* with no drafts there is nothing to critique and no model call is made;
* after a persistent refusal the assess drafts stay unchanged (disclosed as a degradation).
"""

from __future__ import annotations

import json

from sit_review_agent.context import RunContext
from sit_review_agent.llm.outputs import FindingDraft, RefineOutput, RevisionNote
from sit_review_agent.phases._model_calls import (
    call_model,
    changed_fields,
    criteria_vars,
    evidence_vars,
    intent_vars,
    normalise_findings,
    prior_finding_vars,
    reconcile_coverage,
    registry_vars,
    resolve_evidence,
)
from sit_review_agent.prompts import RenderedPrompt
from sit_review_agent.state.run_state import FindingMeta, FindingRevision
from sit_review_agent.states import PhaseName


def findings_json(drafts: list[FindingDraft]) -> str:
    """The current drafts as the model sees them (stable key order, so the brief is byte-stable)."""
    return json.dumps([d.model_dump(mode="json") for d in drafts], ensure_ascii=False, sort_keys=True, indent=1)


class RefinePhase:
    name = PhaseName.REFINE

    async def run(self, ctx: RunContext) -> RunContext:
        phase = self.name
        drafts = list(ctx.state.finding_drafts)
        if not drafts:
            ctx.emit("no findings to refine; skipping the critique call", "done")
            return ctx
        iteration = ctx.state.budget.research_iterations
        ctx.emit(f"critiquing {len(drafts)} findings as a second reviewer")

        def render(*, reframed: bool, schema_error: str) -> RenderedPrompt:
            return ctx.prompts.render(
                "refine.md", findings_json=findings_json(drafts), registry=registry_vars(ctx),
                criteria=criteria_vars(ctx), intent=intent_vars(ctx), evidence=evidence_vars(ctx),
                review_mode=ctx.state.review_mode.value, prior_findings=prior_finding_vars(ctx),
                reframed=reframed, schema_error=schema_error)

        call = await call_model(ctx, phase, render, RefineOutput, iteration=iteration, purpose="refine")
        result = call.result
        if result is None or not isinstance(result.parsed, RefineOutput):
            return ctx                                     # drafts unchanged; degradation already recorded
        out = result.parsed

        old = {d.id: d for d in drafts}
        reserved = set(old) | set(ctx.state.finding_meta)
        revised, id_map = normalise_findings(ctx, out.findings, keep_ids=old, reserved=reserved)
        revised, _, stats = resolve_evidence(ctx, revised)
        notes: dict[str, RevisionNote] = {}
        for n in out.revisions:
            notes.setdefault(id_map.get(n.finding_id, n.finding_id), n)

        def note_for(fid: str, default: str) -> str:
            n = notes.get(fid)
            return f"{n.change}: {n.reason}".strip() if n is not None and n.reason.strip() else default

        meta = dict(ctx.state.finding_meta)
        new_ids = {f.id for f in revised}
        counts = {"revised": 0, "unchanged": 0, "added": 0, "withdrawn": 0}
        for f in revised:
            if f.id in old:
                diff = changed_fields(old[f.id], f)
                if not diff:
                    counts["unchanged"] += 1
                    continue
                counts["revised"] += 1
                m = meta.get(f.id) or FindingMeta(finding_id=f.id, criterion_ids=list(f.criterion_ids),
                                                  created_phase=PhaseName.ASSESS, created_call_id=None,
                                                  last_phase=phase, last_call_id=None, model=None, prompt_hash=None)
                meta[f.id] = m.model_copy(update={
                    "criterion_ids": list(f.criterion_ids), "last_phase": phase, "last_call_id": result.call_id,
                    "model": result.model, "prompt_hash": call.brief.sha256, "iteration": iteration,
                    "history": [*m.history, FindingRevision(phase=phase, call_id=result.call_id, changed_fields=diff,
                                                            note=note_for(f.id, "revised"))]})
            else:
                counts["added"] += 1
                meta[f.id] = FindingMeta(
                    finding_id=f.id, criterion_ids=list(f.criterion_ids), created_phase=phase,
                    created_call_id=result.call_id, last_phase=phase, last_call_id=result.call_id,
                    model=result.model, prompt_hash=call.brief.sha256, iteration=iteration,
                    history=[FindingRevision(phase=phase, call_id=result.call_id, note=note_for(f.id, "added"))])
        for fid in old:
            if fid in new_ids:
                continue
            counts["withdrawn"] += 1
            m = meta.get(fid)
            if m is not None:
                meta[fid] = m.model_copy(update={"history": [*m.history, FindingRevision(
                    phase=phase, call_id=result.call_id, note=note_for(fid, "withdrawn: not returned by refine"))]})

        ctx.state.finding_drafts = revised
        ctx.state.finding_meta = meta
        ctx.state.coverage = reconcile_coverage(ctx, ctx.state.coverage, revised, id_map)
        ctx.state.sound_area_drafts = [
            a.model_copy(update={"related_finding_ids": [i for i in dict.fromkeys(
                id_map.get(x, x) for x in a.related_finding_ids) if i in new_ids]})
            for a in ctx.state.sound_area_drafts]
        ctx.emit(f"refined: {counts['revised']} revised, {counts['unchanged']} unchanged, {counts['added']} added, "
                 f"{counts['withdrawn']} withdrawn or merged; {len(revised)} findings", "done")
        if stats.dropped:
            ctx.emit(f"{stats.dropped} evidence citations dropped (not in the evidence register)", "warn")
        return ctx
