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
their target, withdrawn IDs are dropped), and ``state.finding_ids``: ``refine`` (each merged ID to its
kept ID, each withdrawn ID to null) and ``refine_fields`` (the fields refine wrote into each kept
finding, whose text cites merged IDs, not a shard's own). The text of findings, sound areas and
coverage notes is rewritten through that map when the report is assembled (``finding_refs``), never
in a model brief.

Rules kept from the earlier refine:

* no change of conclusion without cause (robustness BEH-10): a ``keep`` that changes severity or
  disposition with an empty ``reason`` and no added evidence has that change reverted to the draft's
  value before validation, with a warning and a history note. ``kind`` cannot be changed by a
  revision at all;
* registry links: a ``challenges`` link needs at least two evidence items (the spec's finding rule,
  checked by ``revision_problems``); a link to an unknown registry entry is dropped in verify, as
  before;
* delta mode: the shards set ``reassessment``; a revision cannot change it.

Cut with finished revisions (sit_sample_ui_1 defect 1; planner ruling of 2026-10-03): a call cut by
the stage limit or the deadline hands back the revisions its stream had finished
(``PhaseCall.partial["revisions"]``). :func:`salvage_revisions` validates each one on its own
(dropping what does not parse, names an unknown finding or repeats one), reverts unexplained
conclusion changes (BEH-10), and checks the finished set as a whole with ``revision_problems`` over
the findings it covers. A set that passes is used with its ranks; a set that fails (a merge whose
target the cut lost, kept ranks with gaps because later revisions are missing) degrades to its
independent revisions: each keep and withdrawal that passes on its own, and each merge into one of
those keeps, with the kept ranks re-derived from the salvaged order. Every finding without an
applied revision gets a keep of its merged values, ranked after the refined findings in its merged
order, and the whole set goes through ``apply_revisions`` as in a full refine (evidence attached, the
ledger updated, history and ID maps for the refined findings only). The refine-cut degradation then
says how many of the n revisions (one per merged finding) were applied, how many had finished and why
the others were dropped, and that the rest of the findings were not refined; the ``refined`` event
carries ``salvaged_items`` (the runtime's count for the cut call) = ``applied`` + ``dropped``.

Fallback (cut with no finished revision that can be applied, truncated twice, declined twice, or
revisions that still cannot be applied after the repair call): the merged findings stay as merged,
ranked by severity and confidence (``phases.assess.rank_by_severity``), disclosed. With no drafts
there is nothing to refine and no model call is made.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

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
    PhaseCall,
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
from sit_review_agent.progress import ctx_event
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


@dataclass(frozen=True)
class Salvage:
    """What a cut refine call's finished revisions become (:func:`salvage_revisions`)."""

    #: The full revision set to apply: the applied salvaged revisions (BEH-10 reverted), then a keep
    #: of its merged values for every other finding, ranked after them in merged order.
    out: RefineRevisionsOutput
    #: The applied salvaged revisions as the model gave them (before BEH-10), by finding ID.
    raw: dict[str, FindingRevisionDraft]
    #: Finished revisions in the cut answer (the runtime's ``salvaged_items`` for the call).
    finished: int
    #: Why each finished revision that is not applied was dropped (``finished = len(raw) + len(dropped)``).
    dropped: tuple[str, ...]
    #: ``revision_problems`` of the finished set as a whole; empty when it passed and was used as given.
    set_problems: tuple[str, ...]

    @property
    def applied(self) -> int:
        return len(self.raw)


def _one(r: FindingRevisionDraft) -> FindingRevisionDraft:
    """``r`` as the only kept finding of a set (rank 1), so ``revision_problems`` checks it alone."""
    return r.model_copy(update={"rank": 1}) if r.action is RevisionAction.KEEP else r


def salvage_revisions(partial: Mapping[str, Any] | None, drafts: Sequence[FindingDraft]) -> Salvage | None:
    """The revision set a cut refine call's finished revisions (``partial["revisions"]``) give over
    ``drafts`` (module docstring, "Cut with finished revisions"); ``None`` when nothing had finished."""
    items = list((partial or {}).get("revisions") or [])
    if not items:
        return None
    by_id = {d.id: d for d in drafts}
    dropped: list[str] = []
    parsed: list[FindingRevisionDraft] = []
    for item in items:
        try:
            r = FindingRevisionDraft.model_validate(item)
        except ValidationError:
            dropped.append("a revision that does not match the schema")
            continue
        if r.finding_id not in by_id:
            dropped.append(f"a revision for unknown finding {r.finding_id}")
        elif any(p.finding_id == r.finding_id for p in parsed):
            dropped.append(f"a second revision for {r.finding_id}")
        else:
            parsed.append(r)
    raw = {r.finding_id: r for r in parsed}
    fixed = without_unexplained_changes(RefineRevisionsOutput(revisions=parsed), by_id).revisions
    set_problems = revision_problems(RefineRevisionsOutput(revisions=fixed), [r.finding_id for r in fixed],
                                     drafts=by_id)
    if set_problems:                                   # degrade to the independent revisions
        chosen: list[FindingRevisionDraft] = []
        for r in fixed:
            if r.action is RevisionAction.MERGE:
                continue
            problems = revision_problems(RefineRevisionsOutput(revisions=[_one(r)]), [r.finding_id], drafts=by_id)
            if problems:
                dropped.append(f"{r.finding_id} ({'; '.join(problems)})")
            else:
                chosen.append(r)
        keeps = {r.finding_id: r for r in chosen if r.action is RevisionAction.KEEP}
        for r in fixed:
            if r.action is not RevisionAction.MERGE:
                continue
            into = r.merge_into
            if into is None or into not in keeps:
                dropped.append(f"{r.finding_id} (a merge into {into}, whose revision did not finish or was dropped)")
                continue
            problems = revision_problems(RefineRevisionsOutput(revisions=[_one(keeps[into]), r]),
                                         [into, r.finding_id], drafts=by_id)
            if problems:
                dropped.append(f"{r.finding_id} ({'; '.join(problems)})")
            else:
                chosen.append(r)
        order = sorted(keeps.values(), key=lambda r: (r.rank if r.rank is not None else len(fixed) + 1,
                                                      fixed.index(r)))
        rank = {r.finding_id: i + 1 for i, r in enumerate(order)}
        chosen = [r.model_copy(update={"rank": rank[r.finding_id]}) if r.finding_id in rank else r
                  for r in fixed if r in chosen]
    else:
        chosen = list(fixed)
    applied = {r.finding_id for r in chosen}
    raw = {fid: r for fid, r in raw.items() if fid in applied}
    k = sum(1 for r in chosen if r.action is RevisionAction.KEEP)
    rest = sorted((d for d in drafts if d.id not in applied), key=lambda d: d.rank)
    unrefined = [FindingRevisionDraft(finding_id=d.id, action=RevisionAction.KEEP, merge_into=None, rank=k + i + 1,
                                      severity=d.severity, disposition=d.disposition,
                                      affected_decisions=[a.model_copy() for a in d.affected_decisions],
                                      added_evidence=[], next_step=None, reason="")
                 for i, d in enumerate(rest)]
    return Salvage(out=RefineRevisionsOutput(revisions=[*chosen, *unrefined]), raw=raw, finished=len(items),
                   dropped=tuple(dropped), set_problems=tuple(set_problems))


def _listed(reasons: Sequence[str], limit: int = 3) -> str:
    head = "; ".join(reasons[:limit])
    return head + (f"; and {len(reasons) - limit} more" if len(reasons) > limit else "")


def salvage_impact(s: Salvage, findings: int) -> str:
    """The refine-cut degradation's impact when the finished revisions ``s`` were applied."""
    text = (f"{s.applied} of {findings} refine revisions (one per merged finding) were applied from the cut "
            f"answer, which had finished {s.finished}")
    if s.set_problems:
        text += (" and did not hold together as a set (" + _listed(s.set_problems, 2) + "), so only its "
                 "independent revisions were applied (keeps, withdrawals, merges into a kept finding; ranks "
                 "re-derived from the salvaged order)")
    if s.dropped:
        text += f"; {len(s.dropped)} dropped: " + _listed(s.dropped)
    rest = sum(1 for r in s.out.revisions if r.finding_id not in s.raw)
    return (text + f"; the other {rest} merged findings were not refined (no duplicates merged, no registry "
            "decisions linked, no research evidence attached for them) and follow the refined ones in their "
            "merged severity and confidence order")


def _disclose_salvage(ctx: RunContext, since: int, impact: str) -> None:
    """Replace the impact of the refine-cut degradation ``call_model`` recorded (after index ``since``)."""
    degs = ctx.state.degradations
    for i in range(since, len(degs)):
        if degs[i].type is DegradationType.BUDGET_OR_DEADLINE_HIT and degs[i].impact == REFINE_FALLBACK_IMPACT:
            degs[i] = degs[i].model_copy(update={"impact": impact})
            return
    ctx.state.add_degradation(DegradationType.BUDGET_OR_DEADLINE_HIT, "the refine call was cut", impact)


class RefinePhase:
    name = PhaseName.REFINE

    async def run(self, ctx: RunContext) -> RunContext:
        phase = self.name
        drafts = list(ctx.state.finding_drafts)
        if not drafts:
            ctx_event(ctx, "no findings to refine; skipping the refine call", "done", event="refine_skipped",
                      findings=0)
            return ctx
        iteration = ctx.state.budget.research_iterations
        by_id = {d.id: d for d in drafts}
        ids = [d.id for d in drafts]
        ctx_event(ctx, f"refining {len(drafts)} merged findings as one global reviewer (revisions only)",
                  event="refine_started", findings=len(drafts))

        def render(*, reframed: bool, schema_error: str) -> RenderedPrompt:
            return ctx.prompts.render(
                "refine.md", findings_json=findings_json(drafts), registry=registry_vars(ctx),
                criteria=criteria_vars(ctx), intent=intent_vars(ctx), answers=answer_vars(ctx),
                unanswered=list(ctx.state.unanswered_questions), evidence=evidence_vars(ctx),
                review_mode=ctx.state.review_mode.value, prior_findings=prior_finding_vars(ctx),
                reframed=reframed, schema_error=schema_error)

        def check(out: RefineRevisionsOutput) -> list[str]:
            return revision_problems(without_unexplained_changes(out, by_id), ids, drafts=by_id)

        since = len(ctx.state.degradations)             # call_model's refine-cut degradation lands after this
        call = await call_model(ctx, phase, render, RefineRevisionsOutput, iteration=iteration, purpose="refine",
                                check=check)
        result = call.result
        salvage = salvage_revisions(call.partial, drafts) if call.cut else None
        if salvage is not None and (salvage.applied == 0
                                    or revision_problems(salvage.out, ids, drafts=by_id)):
            salvage = None                             # nothing applicable: the old fallback, disclosed by call_model
        if salvage is not None:
            raw = RefineRevisionsOutput(revisions=[salvage.raw.get(r.finding_id, r) for r in salvage.out.revisions])
            out = salvage.out
            refined_ids = set(salvage.raw)
            call_id, model = call.cut_id, ctx.config.agent.model
            _disclose_salvage(ctx, since, salvage_impact(salvage, len(drafts)))
        elif result is None or not isinstance(result.parsed, RefineRevisionsOutput):
            if call.invalid:
                ctx.state.add_degradation(
                    DegradationType.OTHER,
                    "the refine revisions could not be applied after one repair call: "
                    + "; ".join(call.invalid)[:1500], REFINE_FALLBACK_IMPACT)
            ctx_event(ctx, "refine fallback: the merged findings stand, in severity and confidence order", "warn",
                      event="refine_fallback", cut=call.cut, truncated=call.truncated, invalid=bool(call.invalid),
                      declined=not (call.cut or call.truncated or call.invalid))
            return ctx                                     # cut, truncated or declined: disclosed by call_model
        else:
            raw = result.parsed
            out = without_unexplained_changes(raw, by_id)
            refined_ids = set(ids)
            call_id, model = result.call_id, result.model
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
            if f.id not in refined_ids:                    # a cut left it unrefined: no history, counted unchanged
                counts["unchanged"] += 1
                continue
            flips = unexplained_changes(raw_revs[f.id], old)
            if flips:
                what = ", ".join(flips)
                ctx_event(ctx, f"{f.id}: {what} rejected (no revision reason, no new evidence)", "warn",
                          event="revision_rejected", finding_id=f.id, fields_rejected=list(flips))
                add_history(f.id, FindingRevision(phase=phase, call_id=call_id,
                                                  note=f"rejected: {what} without a revision reason or new evidence "
                                                       "(BEH-10); the draft's value kept"))
            diff = changed_fields(old, f)
            if not diff:
                counts["unchanged"] += 1
                continue
            counts["revised"] += 1
            add_history(f.id, FindingRevision(phase=phase, call_id=call_id, changed_fields=diff,
                                              note=f"revised: {r.reason.strip()}" if r.reason.strip() else "revised"),
                        criterion_ids=list(f.criterion_ids), last_phase=phase, last_call_id=call_id,
                        model=model, prompt_hash=call.brief.sha256, iteration=iteration)
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
            add_history(fid, FindingRevision(phase=phase, call_id=call_id, note=note))

        kept = {f.id for f in revised}
        ctx.state.finding_ids = ctx.state.finding_ids.model_copy(update={
            "refine": {fid: (revs[fid].merge_into if revs[fid].action is RevisionAction.MERGE else None)
                       for fid in ids if revs[fid].action is not RevisionAction.KEEP},
            "refine_fields": {fid: ["affected_decisions", *(["next_step"] if revs[fid].next_step is not None else [])]
                              for fid in kept if fid in refined_ids}})
        ctx.state.finding_drafts = revised
        ctx.state.finding_meta = meta
        ctx.state.coverage = reconcile_coverage(ctx, ctx.state.coverage, revised, target)
        ctx.state.sound_area_drafts = [
            a.model_copy(update={"related_finding_ids": [i for i in dict.fromkeys(
                target.get(x, x) for x in a.related_finding_ids) if i in kept]})
            for a in ctx.state.sound_area_drafts]
        ctx_event(ctx, f"refined: {counts['revised']} revised, {counts['unchanged']} unchanged, {counts['merged']} "
                  f"merged, {counts['withdrawn']} withdrawn; {len(revised)} findings"
                  + (f" ({salvage.applied} of {len(drafts)} revisions salvaged from the cut call)" if salvage else ""),
                  "done", event="refined", call_id=call_id, revised=counts["revised"], unchanged=counts["unchanged"],
                  merged=counts["merged"], withdrawn=counts["withdrawn"], findings=len(revised),
                  salvaged=salvage is not None,
                  **({"salvaged_items": salvage.finished, "applied": salvage.applied, "dropped": len(salvage.dropped)}
                     if salvage else {}))
        if stats.dropped:
            ctx_event(ctx, f"{stats.dropped} evidence citations dropped (not in the evidence register)", "warn",
                      event="citations_dropped", count=stats.dropped)
        return ctx
