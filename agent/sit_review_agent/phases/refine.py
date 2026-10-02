"""``refine`` (LLM; optional). Prompt: ``prompts/refine.md``. Output: ``RefineRevisionsOutput``.

Latency redesign (design section 4, levers 4 and 9): one global call over the merged assess
findings that returns one **revision** per finding, never the findings again. The brief carries the
merged findings, the intent and the frozen registry (from understand), the plan answers (from
research) and the evidence register. Revisions (``llm.outputs.FindingRevisionDraft``):

* ``keep`` with the final rank (1..n over the kept findings), severity and disposition, the registry
  links (``affected_decisions``, which assess no longer makes), research evidence to append, and a
  ``next_step`` when the new disposition needs one the finding lacks;
* ``merge`` into a kept finding (a duplicate; its criteria move to the target, nothing else);
* ``withdraw`` (unsupported, generic, or covered elsewhere).

The answer is checked with ``llm.outputs.revision_problems(..., drafts=)`` (one revision per
finding, the action rules, ranks 1..n, evidence not added twice, the spec's finding rules after the
patch) and applied with ``llm.outputs.apply_revisions``, the one exact meaning of a revision set. An
answer with problems is handled like an invalid answer: one repair call with the problems as the
correction, then the fallback below, disclosed.

Writes: ``state.finding_drafts`` (the kept findings in rank order), a ``FindingRevision`` per
changed, merged or withdrawn finding in ``state.finding_meta[...].history`` (phase refine ->
provenance ``revise``), ``state.coverage`` and ``state.sound_area_drafts`` (merged IDs point at
their target, withdrawn IDs are dropped).

Rules kept from the earlier refine:

* no change of conclusion without cause (robustness BEH-10): a ``keep`` that changes severity or
  disposition with an empty ``reason`` and no added evidence has that change reverted to the draft's
  value before validation, with a warning and a history note. ``kind`` cannot be changed by a
  revision at all;
* registry links: a ``challenges`` link needs at least two evidence items (the spec's finding rule,
  checked by ``revision_problems``); a link to an unknown registry entry is dropped in verify, as
  before;
* delta mode: the shards set ``reassessment``; a revision cannot change it.

Fallback (cut by the stage limit or the deadline, truncated twice, declined twice, or revisions that
still cannot be applied after the repair call): the merged findings stay as merged, ranked by
severity and confidence (``phases.assess.rank_by_severity``), disclosed. With no drafts there is
nothing to refine and no model call is made.
"""

from __future__ import annotations

import json

from sit_review_agent.context import RunContext
from sit_review_agent.llm.outputs import (
    FindingDraft,
    FindingRevisionDraft,
    RefineRevisionsOutput,
    RevisionAction,
    apply_revisions,
    revision_problems,
)
from sit_review_agent.models import DegradationType
from sit_review_agent.phases._model_calls import (
    REFINE_FALLBACK_IMPACT,
    answer_vars,
    call_model,
    changed_fields,
    criteria_vars,
    evidence_vars,
    intent_vars,
    prior_finding_vars,
    reconcile_coverage,
    registry_vars,
    resolve_evidence,
)
from sit_review_agent.prompts import RenderedPrompt
from sit_review_agent.state.run_state import FindingMeta, FindingRevision
from sit_review_agent.states import PhaseName

#: Fields that carry a finding's conclusion: refine may change them only with a stated reason or new
#: evidence (robustness BEH-10, "no change without cause"). ``kind`` is not in a revision at all.
CONCLUSION_FIELDS = ("severity", "disposition")


def findings_json(drafts: list[FindingDraft]) -> str:
    """The current drafts as the model sees them (stable key order, so the brief is byte-stable)."""
    return json.dumps([d.model_dump(mode="json") for d in drafts], ensure_ascii=False, sort_keys=True, indent=1)


def unexplained_changes(r: FindingRevisionDraft, draft: FindingDraft) -> list[str]:
    """``field before -> after`` for each conclusion field a ``keep`` changes without a reason or
    added evidence (BEH-10); empty when the change has a cause or nothing changes."""
    if r.action is not RevisionAction.KEEP or r.reason.strip() or r.added_evidence:
        return []
    out = []
    for name in CONCLUSION_FIELDS:
        before, after = getattr(draft, name), getattr(r, name)
        if after is not None and before != after:
            out.append(f"{name} {getattr(before, 'value', before)} -> {getattr(after, 'value', after)}")
    return out


def without_unexplained_changes(out: RefineRevisionsOutput, by_id: dict[str, FindingDraft]) -> RefineRevisionsOutput:
    """``out`` with every unexplained conclusion change (BEH-10) set back to the draft's value. A
    next step given with an unexplained disposition change goes with it (the draft's disposition
    needs no new one)."""
    revs = []
    for r in out.revisions:
        d = by_id.get(r.finding_id)
        if d is not None and unexplained_changes(r, d):
            back: dict[str, object] = {name: getattr(d, name) for name in CONCLUSION_FIELDS}
            if r.disposition != d.disposition:
                back["next_step"] = None
            r = r.model_copy(update=back)
        revs.append(r)
    return RefineRevisionsOutput(revisions=revs)


class RefinePhase:
    name = PhaseName.REFINE

    async def run(self, ctx: RunContext) -> RunContext:
        phase = self.name
        drafts = list(ctx.state.finding_drafts)
        if not drafts:
            ctx.emit("no findings to refine; skipping the refine call", "done")
            return ctx
        iteration = ctx.state.budget.research_iterations
        by_id = {d.id: d for d in drafts}
        ids = [d.id for d in drafts]
        ctx.emit(f"refining {len(drafts)} merged findings as one global reviewer (revisions only)")

        def render(*, reframed: bool, schema_error: str) -> RenderedPrompt:
            return ctx.prompts.render(
                "refine.md", findings_json=findings_json(drafts), registry=registry_vars(ctx),
                criteria=criteria_vars(ctx), intent=intent_vars(ctx), answers=answer_vars(ctx),
                unanswered=list(ctx.state.unanswered_questions), evidence=evidence_vars(ctx),
                review_mode=ctx.state.review_mode.value, prior_findings=prior_finding_vars(ctx),
                reframed=reframed, schema_error=schema_error)

        def check(out: RefineRevisionsOutput) -> list[str]:
            return revision_problems(without_unexplained_changes(out, by_id), ids, drafts=by_id)

        call = await call_model(ctx, phase, render, RefineRevisionsOutput, iteration=iteration, purpose="refine",
                                check=check)
        result = call.result
        if result is None or not isinstance(result.parsed, RefineRevisionsOutput):
            if call.invalid:
                ctx.state.add_degradation(
                    DegradationType.OTHER,
                    "the refine revisions could not be applied after one repair call: "
                    + "; ".join(call.invalid)[:1500], REFINE_FALLBACK_IMPACT)
            ctx.emit("refine fallback: the merged findings stand, in severity and confidence order", "warn")
            return ctx                                     # cut, truncated or declined: disclosed by call_model
        raw = result.parsed
        out = without_unexplained_changes(raw, by_id)
        revised = apply_revisions(drafts, out)
        revised, _, stats = resolve_evidence(ctx, revised)
        revs = {r.finding_id: r for r in out.revisions}
        raw_revs = {r.finding_id: r for r in raw.revisions}

        meta = dict(ctx.state.finding_meta)
        counts = {"revised": 0, "unchanged": 0, "merged": 0, "withdrawn": 0}

        def add_history(fid: str, entry: FindingRevision, **update: object) -> None:
            m = meta.get(fid) or FindingMeta(finding_id=fid, criterion_ids=list(by_id[fid].criterion_ids),
                                             created_phase=PhaseName.ASSESS, created_call_id=None,
                                             last_phase=PhaseName.ASSESS, last_call_id=None, model=None,
                                             prompt_hash=None)
            meta[fid] = m.model_copy(update={"history": [*m.history, entry], **update})

        for f in revised:
            r, old = revs[f.id], by_id[f.id]
            flips = unexplained_changes(raw_revs[f.id], old)
            if flips:
                what = ", ".join(flips)
                ctx.emit(f"{f.id}: {what} rejected (no revision reason, no new evidence)", "warn")
                add_history(f.id, FindingRevision(phase=phase, call_id=result.call_id,
                                                  note=f"rejected: {what} without a revision reason or new evidence "
                                                       "(BEH-10); the draft's value kept"))
            diff = changed_fields(old, f)
            if not diff:
                counts["unchanged"] += 1
                continue
            counts["revised"] += 1
            add_history(f.id, FindingRevision(phase=phase, call_id=result.call_id, changed_fields=diff,
                                              note=f"revised: {r.reason.strip()}" if r.reason.strip() else "revised"),
                        criterion_ids=list(f.criterion_ids), last_phase=phase, last_call_id=result.call_id,
                        model=result.model, prompt_hash=call.brief.sha256, iteration=iteration)
        target: dict[str, str] = {}
        for fid in ids:
            r = revs[fid]
            if r.action is RevisionAction.KEEP:
                continue
            if r.action is RevisionAction.MERGE and r.merge_into is not None:
                counts["merged"] += 1
                target[fid] = r.merge_into
                note = f"merged into {r.merge_into}: {r.reason.strip()}".rstrip(": ")
            else:
                counts["withdrawn"] += 1
                note = f"withdrawn: {r.reason.strip()}".rstrip(": ")
            add_history(fid, FindingRevision(phase=phase, call_id=result.call_id, note=note))

        kept = {f.id for f in revised}
        ctx.state.finding_drafts = revised
        ctx.state.finding_meta = meta
        ctx.state.coverage = reconcile_coverage(ctx, ctx.state.coverage, revised, target)
        ctx.state.sound_area_drafts = [
            a.model_copy(update={"related_finding_ids": [i for i in dict.fromkeys(
                target.get(x, x) for x in a.related_finding_ids) if i in kept]})
            for a in ctx.state.sound_area_drafts]
        ctx.emit(f"refined: {counts['revised']} revised, {counts['unchanged']} unchanged, {counts['merged']} merged, "
                 f"{counts['withdrawn']} withdrawn; {len(revised)} findings", "done")
        if stats.dropped:
            ctx.emit(f"{stats.dropped} evidence citations dropped (not in the evidence register)", "warn")
        return ctx
