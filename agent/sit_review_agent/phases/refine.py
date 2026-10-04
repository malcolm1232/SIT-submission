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
* delta mode: the shards set ``reassessment``; a revision cannot change it. Every finding of the
  previous review that no kept finding carries forward (``delta.carried_prior_ids``) needs a status in
  ``prior_statuses`` (resolved, partially_addressed, still_open, or withdrawn_on_reassessment with a
  one-line reason; ``llm.outputs.prior_status_problems``). An answer that leaves one out is asked
  once, through the same repair call as an invalid answer (``call_model(ask=...)``), whose correction
  names each missing prior ID (``prompts/refine.md`` is unchanged: the rule reaches the model through
  the field's schema description and that correction, since a prompt edit would stop the replay of
  committed runs); what the repair answer still leaves out is filled in by the report as
  ``still_open``, "not re-examined", disclosed (``delta.build_prior_table``). The usable statuses go
  to ``state.prior_statuses``.

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

Repair for the failing revisions only (sit_sample_ui_1 rehearsal of 2026-10-04: one revision of 55
broke a rule, the whole answer was asked again, the repair ran into the stage limit with 4 revisions
and 51 findings were never refined, so none of the 41 external ledger entries reached a finding): a
complete answer with problems is split (``call_model(split=...)``, :func:`split_revisions`). Every
revision that holds on its own (the same test as the salvage above) is kept as the model gave it; the
findings without one are named in the correction of the one repair call, which is asked for those
only and told the free ranks. What comes back (the repair answer, or the finished revisions of a repair
cut at the stage limit; nothing from one declined or truncated twice) is merged with the kept revisions
and goes through :func:`salvage_revisions` as one set (:func:`repair_outcome`): a repaired revision
that still fails is dropped, never applied, and its finding is unrefined as above. A revision the
repair gives for a kept finding is ignored. The disclosure states the counts ("54 of 55 refine
revisions ... applied: 54 kept from the first answer ..., and 0 repaired at the limit ...; 1 unrefined
(FND-030)"); none is recorded when every revision was applied as given. Each refined finding's history
names the call that gave its revision. An answer where nothing holds, or nothing is missing, is asked
again whole, as before.

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
from sit_review_agent.delta import carried_prior_ids
from sit_review_agent.llm.outputs import (
    FindingDraft,
    FindingRevisionDraft,
    RefineRevisionsOutput,
    RevisionAction,
    apply_revisions,
    prior_status_problems,
    revision_problems,
)
from sit_review_agent.models import DegradationType, PriorFindingStatus
from sit_review_agent.phases._model_calls import (
    REFINE_FALLBACK_IMPACT,
    KeptItems,
    PhaseCall,
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


def _parse_items(items: Sequence[Any],
                 by_id: Mapping[str, FindingDraft]) -> tuple[list[FindingRevisionDraft], list[str]]:
    """The revisions among ``items`` (drafts or their JSON) that parse, name a known finding and are
    the first for it, with why each other item was dropped."""
    dropped: list[str] = []
    parsed: list[FindingRevisionDraft] = []
    for item in items:
        if isinstance(item, FindingRevisionDraft):
            r = item
        else:
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
    return parsed, dropped


def independent_revisions(fixed: Sequence[FindingRevisionDraft],
                          by_id: Mapping[str, FindingDraft]) -> tuple[list[FindingRevisionDraft], list[str]]:
    """The revisions of ``fixed`` (BEH-10 already reverted, one per finding) that hold on their own:
    each keep and withdrawal that passes ``revision_problems`` alone, and each merge into one of those
    keeps that passes with it; in ``fixed`` order, ranks as given. The second list says why each other
    revision was dropped."""
    dropped: list[str] = []
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
    return [r for r in fixed if r in chosen], dropped


def _reranked(chosen: Sequence[FindingRevisionDraft],
              fixed: Sequence[FindingRevisionDraft]) -> list[FindingRevisionDraft]:
    """``chosen`` with its kept ranks re-derived (1..k) from the given ranks, then ``fixed`` order."""
    keeps = [r for r in chosen if r.action is RevisionAction.KEEP]
    order = sorted(keeps, key=lambda r: (r.rank if r.rank is not None else len(fixed) + 1, fixed.index(r)))
    rank = {r.finding_id: i + 1 for i, r in enumerate(order)}
    return [r.model_copy(update={"rank": rank[r.finding_id]}) if r.finding_id in rank else r for r in chosen]


def salvage_revisions(partial: Mapping[str, Any] | None, drafts: Sequence[FindingDraft]) -> Salvage | None:
    """The revision set a cut refine call's finished revisions (``partial["revisions"]``) give over
    ``drafts`` (module docstring, "Cut with finished revisions"); ``None`` when nothing had finished.
    The items may be drafts as well as their JSON (the merge of kept and repaired revisions)."""
    items = list((partial or {}).get("revisions") or [])
    if not items:
        return None
    by_id = {d.id: d for d in drafts}
    parsed, dropped = _parse_items(items, by_id)
    raw = {r.finding_id: r for r in parsed}
    fixed = without_unexplained_changes(RefineRevisionsOutput(revisions=parsed), by_id).revisions
    set_problems = revision_problems(RefineRevisionsOutput(revisions=fixed), [r.finding_id for r in fixed],
                                     drafts=by_id)
    if set_problems:                                   # degrade to the independent revisions
        chosen, more = independent_revisions(fixed, by_id)
        dropped += more
        chosen = _reranked(chosen, fixed)
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


def split_revisions(out: RefineRevisionsOutput, drafts: Sequence[FindingDraft]) -> KeptItems | None:
    """What a complete refine answer that broke the rules keeps (module docstring, "Repair for the
    failing revisions only"): every revision that holds on its own (:func:`independent_revisions`
    after the BEH-10 revert), as the model gave it; the findings without one are asked again. ``None``
    when nothing holds or nothing is missing (then the whole answer is asked again, as before)."""
    by_id = {d.id: d for d in drafts}
    parsed, _ = _parse_items(out.revisions, by_id)
    fixed = without_unexplained_changes(RefineRevisionsOutput(revisions=parsed), by_id).revisions
    chosen, _ = independent_revisions(fixed, by_id)
    kept_ids = {r.finding_id for r in chosen}
    retry = [d.id for d in drafts if d.id not in kept_ids]
    if not kept_ids or not retry:
        return None
    kept = tuple(r for r in parsed if r.finding_id in kept_ids)
    taken = {r.rank for r in chosen if r.action is RevisionAction.KEEP and r.rank is not None}
    free = [i for i in range(1, len(taken) + len(retry) + 1) if i not in taken]
    instruction = (
        f"Your revisions for {len(kept)} of the {len(drafts)} findings were accepted and are kept exactly as you "
        f"gave them; do not send them again. The complete answer this time is one revision for each of these "
        f"{len(retry)} finding(s) only: {', '.join(retry)}. A finding you keep among them takes one of the free "
        f"ranks {', '.join(str(i) for i in free[:20])}{', ...' if len(free) > 20 else ''} (lowest first), so the "
        "kept ranks still run 1..n without gaps once a merged or withdrawn finding frees its rank. In a re-review "
        "also give prior_statuses in full, as the rules say.")
    return KeptItems(kept=kept, retry=tuple(retry), instruction=instruction)


@dataclass(frozen=True)
class Repair:
    """The merge of the kept revisions of a first answer with what the repair call gave for the rest
    (module docstring, "Repair for the failing revisions only")."""

    #: How the repair call ended: "returned in full", "was cut by the stage limit", ...
    how: str
    #: The findings the repair call was asked for.
    retry: tuple[str, ...]
    #: Revisions the repair call gave for them (a revision for a kept finding is ignored, not counted).
    returned: int
    #: Revisions the repair call gave for kept findings, ignored.
    extra: int
    #: Kept revisions from the first answer that the merged set applied.
    kept_applied: int
    #: Repaired revisions that the merged set applied.
    repaired_applied: int
    #: The merged set over the drafts (``salvage_revisions`` of kept plus repaired).
    salvage: Salvage

    @property
    def unrefined(self) -> list[str]:
        return [r.finding_id for r in self.salvage.out.revisions if r.finding_id not in self.salvage.raw]


def repair_outcome(call: PhaseCall, drafts: Sequence[FindingDraft]) -> Repair | None:
    """The kept revisions of ``call.first`` merged with the repair answer (``call.result``, or the cut
    call's ``partial``) through :func:`salvage_revisions`; ``None`` when the merged set applies nothing."""
    split = call.split
    assert split is not None
    kept_ids = {r.finding_id for r in split.kept}
    result = call.result
    if result is not None and isinstance(result.parsed, RefineRevisionsOutput):
        given: list[Any] = list(result.parsed.revisions)
        how = "returned in full"
    elif call.cut:
        given = list((call.partial or {}).get("revisions") or [])
        how = "was cut by the stage limit" + (f" after {len(given)} finished revision(s)" if given else
                                              " with nothing finished")
    elif call.truncated:
        given, how = [], "was truncated twice at the output cap"
    else:
        given, how = [], "was declined"

    def fid(item: Any) -> str | None:
        return item.finding_id if isinstance(item, FindingRevisionDraft) else (
            item.get("finding_id") if isinstance(item, Mapping) else None)

    repaired = [g for g in given if fid(g) not in kept_ids]
    s = salvage_revisions({"revisions": [*split.kept, *repaired]}, drafts)
    if s is None or s.applied == 0:
        return None
    return Repair(how=how, retry=split.retry, returned=len(repaired), extra=len(given) - len(repaired),
                  kept_applied=sum(1 for f in s.raw if f in kept_ids),
                  repaired_applied=sum(1 for f in s.raw if f not in kept_ids), salvage=s)


def repair_impact(r: Repair, findings: int) -> str:
    """The degradation impact when the first answer's kept revisions were applied with the repaired ones."""
    at_limit = " at the limit" if r.how.startswith("was cut") else ""
    text = (f"{r.salvage.applied} of {findings} refine revisions (one per merged finding) were applied: "
            f"{r.kept_applied} kept from the first answer, which broke the revision rules for {len(r.retry)} "
            f"finding(s) ({_listed(list(r.retry), 5)}), and {r.repaired_applied} repaired{at_limit} by the one "
            f"repair call, which {r.how} with {r.returned} revision(s) for them")
    if r.salvage.set_problems:
        text += (". The merged set did not hold together (" + _listed(r.salvage.set_problems, 2) + "), so only its "
                 "independent revisions were applied (keeps, withdrawals, merges into a kept finding; ranks "
                 "re-derived from the given order)")
    if r.salvage.dropped:
        text += f"; {len(r.salvage.dropped)} dropped: " + _listed(r.salvage.dropped)
    rest = r.unrefined
    if not rest:
        return text + "; 0 unrefined"
    return (text + f"; {len(rest)} unrefined ({_listed(rest, 5)}): not refined (no duplicates merged, no registry "
            "decisions linked, no research evidence attached) and following the refined findings in merged "
            "severity and confidence order")


def _disclose(ctx: RunContext, since: int, impact: str, event: str, dtype: DegradationType) -> None:
    """Give the degradations ``call_model`` recorded for this call (after index ``since``; never a
    model fallback) the impact of what was applied, or record one with ``event`` when it recorded none."""
    degs = ctx.state.degradations
    replaced = False
    for i in range(since, len(degs)):
        if degs[i].type is not DegradationType.MODEL_FALLBACK:
            degs[i] = degs[i].model_copy(update={"impact": impact})
            replaced = True
    if not replaced:
        ctx.state.add_degradation(dtype, event, impact)


class RefinePhase:
    name = PhaseName.REFINE

    async def run(self, ctx: RunContext) -> RunContext:
        phase = self.name
        drafts = list(ctx.state.finding_drafts)
        ctx.state.prior_statuses = []                  # a re-run from the checkpoint starts clean
        if not drafts:
            ctx_event(ctx, "no findings to refine; skipping the refine call", "done", event="refine_skipped",
                      findings=0)
            return ctx
        iteration = ctx.state.budget.research_iterations
        by_id = {d.id: d for d in drafts}
        ids = [d.id for d in drafts]
        ctx_event(ctx, f"refining {len(drafts)} merged findings as one global reviewer (revisions only)",
                  event="refine_started", findings=len(drafts))

        prior = prior_finding_vars(ctx)
        prior_ids = [p["id"] for p in prior if p["id"]]

        def render(*, reframed: bool, schema_error: str) -> RenderedPrompt:
            return ctx.prompts.render(
                "refine.md", findings_json=findings_json(drafts), registry=registry_vars(ctx),
                criteria=criteria_vars(ctx), intent=intent_vars(ctx), answers=answer_vars(ctx),
                unanswered=list(ctx.state.unanswered_questions), evidence=evidence_vars(ctx),
                review_mode=ctx.state.review_mode.value, prior_findings=prior_finding_vars(ctx),
                reframed=reframed, schema_error=schema_error)

        def check(out: RefineRevisionsOutput) -> list[str]:
            return revision_problems(without_unexplained_changes(out, by_id), ids, drafts=by_id)

        def kept_carry(out: RefineRevisionsOutput) -> set[str]:
            kept = {r.finding_id for r in out.revisions if r.action is RevisionAction.KEEP}
            return carried_prior_ids(d for d in drafts if d.id in kept)

        def ask(out: RefineRevisionsOutput) -> list[str]:
            return prior_status_problems(out, prior_ids, kept_carry(out)) if prior_ids else []

        def split(out: RefineRevisionsOutput, problems: list[str]) -> KeptItems | None:
            return split_revisions(out, drafts)

        def prior_statuses(answers: Sequence[RefineRevisionsOutput], kept_ids: set[str]) -> None:
            """The usable prior statuses of ``answers`` (the first that gives one for a prior ID counts),
            given the findings kept; what is still missing: the report, "not re-examined"."""
            if not prior_ids:
                return
            carried, seen = carried_prior_ids(d for d in drafts if d.id in kept_ids), set()
            usable = []
            for a in answers:
                for p in a.prior_statuses:
                    if p.prior_finding_id in prior_ids and p.prior_finding_id not in carried | seen and (
                            p.note.strip() or p.status is not PriorFindingStatus.WITHDRAWN_ON_REASSESSMENT):
                        usable.append(p)
                        seen.add(p.prior_finding_id)
            ctx.state.prior_statuses = usable

        since = len(ctx.state.degradations)             # call_model's degradations for this call land after this
        call = await call_model(ctx, phase, render, RefineRevisionsOutput, iteration=iteration, purpose="refine",
                                check=check, ask=ask, split=split)
        result = call.result
        # The repair answer first, then the first answer (whose kept revisions stand): a complete answer
        # that is not applied as a whole still gives its prior statuses.
        answers = [r.parsed for r in (result, call.first)
                   if r is not None and isinstance(r.parsed, RefineRevisionsOutput)]
        repair = repair_outcome(call, drafts) if call.split is not None else None
        salvage = repair.salvage if repair is not None else (
            salvage_revisions(call.partial, drafts) if call.cut else None)
        if salvage is not None and (salvage.applied == 0
                                    or revision_problems(salvage.out, ids, drafts=by_id)):
            salvage = repair = None                    # nothing applicable: the old fallback, disclosed by call_model
        # Each refined finding's call and model: the repair call's for a repaired revision, the first
        # call's for a kept one, the one call's otherwise.
        call_of: dict[str, str | None] = {}
        model_of: dict[str, str | None] = {}
        if salvage is not None:
            raw = RefineRevisionsOutput(revisions=[salvage.raw.get(r.finding_id, r) for r in salvage.out.revisions])
            out = salvage.out
            refined_ids = set(salvage.raw)
            if repair is not None:
                assert call.first is not None and call.split is not None
                kept_ids = {r.finding_id for r in call.split.kept}
                later = result.call_id if result is not None else call.cut_id
                for fid in refined_ids:
                    call_of[fid] = call.first.call_id if fid in kept_ids else later
                    model_of[fid] = call.first.model if fid in kept_ids else (
                        result.model if result is not None else ctx.config.agent.model)
                if repair.unrefined or salvage.set_problems or salvage.dropped or not result:
                    _disclose(ctx, since, repair_impact(repair, len(drafts)),
                              f"the refine answer broke the revision rules for {len(repair.retry)} finding(s); the one "
                              f"repair call, asked for those only, {repair.how}", DegradationType.OTHER)
                call_id = later
            else:
                call_id = call.cut_id
                _disclose(ctx, since, salvage_impact(salvage, len(drafts)), "the refine call was cut",
                          DegradationType.BUDGET_OR_DEADLINE_HIT)
            for fid in refined_ids:
                call_of.setdefault(fid, call_id)
                model_of.setdefault(fid, ctx.config.agent.model)
        elif call.split is not None or result is None or not isinstance(result.parsed, RefineRevisionsOutput):
            if call.invalid:
                ctx.state.add_degradation(
                    DegradationType.OTHER,
                    "the refine revisions could not be applied after one repair call: "
                    + "; ".join(call.invalid)[:1500], REFINE_FALLBACK_IMPACT)
            elif call.split is not None and not call.cut and not call.truncated and result is not None:
                ctx.state.add_degradation(
                    DegradationType.OTHER,
                    "the refine revisions could not be applied after one repair call for the failing ones",
                    REFINE_FALLBACK_IMPACT)
            prior_statuses(answers, set(ids))
            ctx_event(ctx, "refine fallback: the merged findings stand, in severity and confidence order", "warn",
                      event="refine_fallback", cut=call.cut, truncated=call.truncated, invalid=bool(call.invalid),
                      declined=not (call.cut or call.truncated or call.invalid))
            return ctx                                     # cut, truncated or declined: disclosed by call_model
        else:
            raw = result.parsed
            out = without_unexplained_changes(raw, by_id)
            refined_ids = set(ids)
            call_id = result.call_id
            call_of = dict.fromkeys(ids, call_id)
            model_of = dict.fromkeys(ids, result.model)
        prior_statuses(answers, {r.finding_id for r in out.revisions if r.action is RevisionAction.KEEP})
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
                add_history(f.id, FindingRevision(phase=phase, call_id=call_of[f.id],
                                                  note=f"rejected: {what} without a revision reason or new evidence "
                                                       "(BEH-10); the draft's value kept"))
            diff = changed_fields(old, f)
            if not diff:
                counts["unchanged"] += 1
                continue
            counts["revised"] += 1
            add_history(f.id, FindingRevision(phase=phase, call_id=call_of[f.id], changed_fields=diff,
                                              note=f"revised: {r.reason.strip()}" if r.reason.strip() else "revised"),
                        criterion_ids=list(f.criterion_ids), last_phase=phase, last_call_id=call_of[f.id],
                        model=model_of[f.id], prompt_hash=call.brief.sha256, iteration=iteration)
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
            add_history(fid, FindingRevision(phase=phase, call_id=call_of[fid], note=note))

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
                  + (f" ({repair.kept_applied} kept from the first answer, {repair.repaired_applied} of "
                     f"{len(repair.retry)} repaired, {len(repair.unrefined)} unrefined)" if repair else
                     f" ({salvage.applied} of {len(drafts)} revisions salvaged from the cut call)" if salvage else ""),
                  "done", event="refined", call_id=call_id, revised=counts["revised"], unchanged=counts["unchanged"],
                  merged=counts["merged"], withdrawn=counts["withdrawn"], findings=len(revised),
                  salvaged=salvage is not None,
                  **({"salvaged_items": salvage.finished, "applied": salvage.applied, "dropped": len(salvage.dropped)}
                     if salvage else {}),
                  **({"kept": repair.kept_applied, "repaired": repair.repaired_applied, "retry": len(repair.retry),
                      "unrefined": len(repair.unrefined)} if repair else {}))
        if stats.dropped:
            ctx_event(ctx, f"{stats.dropped} evidence citations dropped (not in the evidence register)", "warn",
                      event="citations_dropped", count=stats.dropped)
        return ctx
