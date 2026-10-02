"""``assess`` (LLM). Prompt: ``prompts/assess.md``. Output per shard: ``AssessOutput``.

Latency redesign (design section 4, lever 1 and 8): assess runs as K concurrent **shards**, one
model call per criterion group (``config.agent.assess.shards_for(run criteria)``), in stage 1 beside
understand, plan and research. A shard sees the document, its criterion group and a scope
paragraph only: no intent, registry, plan answers or evidence register (they do not exist yet when
it starts; refine links decisions and attaches research evidence later).

Reads: documents, criteria, review mode, prior findings (delta mode).
Writes (at :meth:`AssessPhase.merge`, once stage 1 has closed): ``state.finding_drafts``
(``FND-nnn`` numbered in shard order, each with ``criterion_ids``), ``state.finding_meta``
(created_phase=assess, the shard's call ID, model and brief hash), ``state.sound_area_drafts``,
``state.coverage`` (every criterion: findings / no_issue / not_applicable), ledger entries for the
shards' new ``doc`` and ``inference`` evidence (written in shard order), and each shard's
bookkeeping (call IDs, usage, refusals, degradations), also in shard order.

Determinism: finding IDs and evidence IDs do not depend on which shard finished first. Shards only
return their answer (:class:`ShardResult`); :meth:`AssessPhase.merge` renumbers the findings in
shard order (each shard's findings in its own rank order) and writes the shards' evidence to the
ledger in shard order, after research has stopped writing to it. The merged findings are ranked by
severity, then confidence (the order the report keeps when refine does not run or is cut).

Per shard (``assess-0-s<k>``, ``k`` = launch order, 1-based; retries ``assess-0-s<k>-r<j>``; the
research iteration is always 0, since a shard sees no research):

* done: the model's answer;
* cut by the stage 1 limit (``LLMDeadlineError``): the findings the stream had finished
  (``partial``, validated item by item) are kept; criteria of the shard without a finding are not
  assessed; disclosed as a ``budget_or_deadline_hit`` degradation naming the shard;
* answer truncated twice at the output cap, declined after the reframed retry, or failed with a
  model error (rate limit, overload, timeout, a second schema error): no findings from the shard,
  its criteria not assessed, disclosed; the other shards still make a partial review. When every
  shard failed with a model error the first error is raised (the run stops, resumable), as a single
  assess call did before.

``not_assessed`` (``phases.report``) remains only for a run in which no shard produced an
assessment (a complete answer or at least one finished finding): the merge then records the
stage-level disclosure ``report`` reads, by priority "out of time before assessment" (a shard was
cut), "the assess answer was truncated twice at the output cap", or ``declined_sections`` "assess".
A shard that answered with no finding but checked its criteria is an assessment.

Run outside the orchestrator (``AssessPhase().run(ctx)``), the shards run concurrently and are
merged at once; the orchestrator calls :meth:`run_shards` and :meth:`merge` itself so it can store
each finished shard (resume re-runs only the unfinished ones) and merge after the stage closes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sit_review_agent.config import AssessShard
from sit_review_agent.context import RunContext
from sit_review_agent.errors import ExitCode, LLMError, LLMSchemaError
from sit_review_agent.llm.outputs import AssessOutput, CriterionCoverage, FindingDraft, SoundAreaDraft
from sit_review_agent.llm.runtime import OUT_OF_TIME_BEFORE_ASSESSMENT, truncated_twice_event
from sit_review_agent.models import SEVERITY_RANK, DegradationType, finding_id
from sit_review_agent.phases._isolation import StateDelta, apply_delta, guarded, isolate, state_delta
from sit_review_agent.phases._model_calls import (
    call_model,
    criteria_vars,
    document_vars,
    known_criteria,
    normalise_findings,
    normalise_sound_areas,
    prior_finding_vars,
    reconcile_coverage,
    resolve_evidence,
    summarise,
)
from sit_review_agent.prompts import RenderedPrompt
from sit_review_agent.state.run_state import FindingMeta
from sit_review_agent.states import PhaseName

ShardOutcome = Literal["done", "cut", "truncated", "declined", "error"]

#: Why a shard produced no assessment -> the coverage note of its criteria.
NOT_ASSESSED_NOTE = {
    "cut": "not assessed: out of time before assessment (stage 1 limit)",
    "truncated": f"not assessed: {truncated_twice_event(PhaseName.ASSESS)}",
    "declined": "not assessed: the model declined the assess call",
    "error": "not assessed: the assess call failed",
}


class ShardResult(BaseModel):
    """What one assess shard returned: its answer (or the findings it salvaged) and what its calls
    added to the run state. Serialisable, so a finished shard survives an interruption."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)              # launch order, 1-based
    name: str
    criteria: list[str]
    outcome: ShardOutcome
    output: AssessOutput | None = None    # the answer, or the salvaged findings of a cut shard
    salvaged: int = 0                     # finished findings kept from a cut stream
    call_id: str | None = None
    model: str | None = None
    prompt_hash: str | None = None
    iteration: int = 0
    detail: str = ""                      # the error of a failed shard (class and message)
    delta: StateDelta = Field(default_factory=StateDelta)

    @property
    def assessed(self) -> bool:
        """Whether the shard produced an assessment: an answer, or at least one finished finding."""
        return self.outcome == "done" or (self.output is not None and bool(self.output.findings))

    def label(self, count: int) -> str:
        return f"assess shard {self.index}/{count} ({self.name})"


#: The research iteration of every shard (conversation ``assess-0-s<k>``, provenance iteration 0): a
#: shard runs beside research and sees none of it, also when resume re-runs it after research ended.
SHARD_ITERATION = 0


def shard_conversation(iteration: int, index: int) -> str:
    return f"assess-{iteration}-s{index}"


def salvage(partial: Mapping[str, Any] | None) -> AssessOutput | None:
    """The items of a cut stream that validate, each on its own; ``None`` when none does."""
    if not partial:
        return None

    def items(key: str, model: type[BaseModel]) -> list[Any]:
        out = []
        for raw in partial.get(key) or []:
            try:
                out.append(model.model_validate(raw))
            except ValidationError:
                continue
        return out

    findings = items("findings", FindingDraft)
    if not findings:
        return None
    return AssessOutput(findings=findings, sound_areas=items("sound_areas", SoundAreaDraft),
                        coverage=items("coverage", CriterionCoverage))


def _is_bug(exc: LLMError) -> bool:
    """Errors that mean a defect (bad request, exhausted fake script, strict-replay miss), never a
    model outcome: they propagate as before. A second schema error is a model outcome."""
    return exc.exit_code is not ExitCode.LLM_UNAVAILABLE and not isinstance(exc, LLMSchemaError)


class AssessPhase:
    name = PhaseName.ASSESS

    def __init__(self) -> None:
        #: The error of each shard whose call failed (raised when every shard failed).
        self._errors: dict[int, LLMError] = {}

    @staticmethod
    def shards(ctx: RunContext) -> list[AssessShard]:
        """The run's shards in launch order."""
        return ctx.config.agent.assess.shards_for(known_criteria(ctx))

    async def run(self, ctx: RunContext) -> RunContext:
        results = await self.run_shards(ctx)
        self.merge(ctx, results)
        return ctx

    async def run_shards(self, ctx: RunContext, *, done: Mapping[int, ShardResult] | None = None,
                         on_end: Callable[[ShardResult], None] | None = None) -> list[ShardResult]:
        """Run every shard not in ``done`` concurrently, each on its own copy of the run state;
        ``on_end`` is called as each one ends (the orchestrator stores it). Returns the results in
        shard order. ``ctx.state`` is not changed: :meth:`merge` applies the results."""
        shards = self.shards(ctx)
        done = dict(done or {})
        count = len(shards)
        ctx.emit(f"assessing {len(known_criteria(ctx))} criteria in {count} concurrent shard(s)"
                 + (f"; {len(done)} already finished" if done else ""))
        tasks: dict[int, asyncio.Task[ShardResult]] = {}
        for i, shard in enumerate(shards, start=1):
            if i in done:
                continue
            tasks[i] = asyncio.create_task(guarded(self._shard(ctx, shard, i, count, on_end)),
                                           name=f"assess-shard-{i}")
        try:
            if tasks:
                # A model failure ends a shard normally (outcome "error"); an exception here is a
                # defect or an interruption, which stops the other shards too.
                await asyncio.wait(tasks.values(), return_when=asyncio.FIRST_EXCEPTION)
        finally:
            pending = [t for t in tasks.values() if not t.done()]
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        results = dict(done)
        raised = [e for t in tasks.values() if not t.cancelled() and (e := t.exception()) is not None]
        if raised:                                       # every exception is retrieved; the first is raised
            raise raised[0]
        for i, t in tasks.items():
            results[i] = t.result()
        ordered = [results[i] for i in sorted(results)]
        errors = [r for r in ordered if r.outcome == "error"]
        if ordered and len(errors) == len(ordered):
            raise self._errors.get(errors[0].index) or RuntimeError(errors[0].detail)
        return ordered

    async def _shard(self, ctx: RunContext, shard: AssessShard, index: int, count: int,
                     on_end: Callable[[ShardResult], None] | None) -> ShardResult:
        result = await self.run_shard(ctx, shard, index, count)
        if on_end is not None and result.outcome != "error":
            on_end(result)                  # a failed call is re-run on resume, never stored
        return result

    async def run_shard(self, ctx: RunContext, shard: AssessShard, index: int, count: int) -> ShardResult:
        """One shard on an isolated copy of the run state."""
        iso = isolate(ctx, PhaseName.ASSESS)
        sctx = iso.ctx
        phase = self.name
        iteration = SHARD_ITERATION
        criteria = [c for c in criteria_vars(sctx) if c["id"] in set(shard.criteria)]
        others = [c for c in known_criteria(sctx) if c not in set(shard.criteria)]
        label = f"assess shard {index}/{count} ({shard.name})"

        def render(*, reframed: bool, schema_error: str) -> RenderedPrompt:
            return sctx.prompts.render(
                "assess.md", criteria=criteria, other_criteria=others, shard_name=shard.name, shard_index=index,
                shard_count=count, documents=document_vars(sctx), review_mode=sctx.state.review_mode.value,
                prior_findings=prior_finding_vars(sctx), reframed=reframed, schema_error=schema_error)

        sctx.emit(f"{label}: {', '.join(shard.criteria)}")
        base = dict(index=index, name=shard.name, criteria=list(shard.criteria), iteration=iteration)
        try:
            call = await call_model(sctx, phase, render, AssessOutput, iteration=iteration, purpose="assess",
                                    conversation=shard_conversation(iteration, index), disclose=False)
        except LLMError as exc:
            if _is_bug(exc):
                raise
            self._errors[index] = exc
            sctx.state.add_degradation(DegradationType.OTHER, f"{label} failed ({type(exc).__name__}: "
                                       f"{str(exc)[:200]})", _not_assessed_impact(shard.criteria))
            sctx.emit(f"{label} failed ({type(exc).__name__}); its criteria are not assessed", "warn")
            return ShardResult(**base, outcome="error", detail=f"{type(exc).__name__}: {str(exc)[:500]}",
                               delta=state_delta(iso.base, sctx.state))
        result = call.result
        if result is not None and isinstance(result.parsed, AssessOutput):
            out = result.parsed
            sctx.emit(f"{label}: {len(out.findings)} draft finding(s) "
                      f"({summarise(out.findings, lambda f: f.kind.value)}), unverified", "done")
            return ShardResult(**base, outcome="done", output=out, call_id=result.call_id, model=result.model,
                               prompt_hash=call.brief.sha256, delta=state_delta(iso.base, sctx.state))
        calls = sctx.state.llm_calls.get(phase.value, [])
        last = calls[-1] if calls else None
        if call.cut:
            kept = salvage(call.partial)
            n = len(kept.findings) if kept is not None else 0
            covered = {c for f in (kept.findings if kept else []) for c in f.criterion_ids}
            missing = [c for c in shard.criteria if c not in covered]
            sctx.state.add_degradation(
                DegradationType.BUDGET_OR_DEADLINE_HIT,
                f"{label} was cut by the stage 1 limit at {sctx.elapsed_s():.0f} s; {n} finished finding(s) kept",
                _not_assessed_impact(missing) if missing else "every criterion of the shard has a finding; the shard's "
                "lower-ranked findings, if any, are missing")
            sctx.emit(f"{label} cut by the stage 1 limit; {n} finished finding(s) kept", "warn")
            return ShardResult(**base, outcome="cut", output=kept, salvaged=n, call_id=last,
                               model=sctx.config.agent.model, prompt_hash=call.brief.sha256,
                               delta=state_delta(iso.base, sctx.state))
        if call.truncated:
            sctx.state.add_degradation(
                DegradationType.OTHER,
                f"{label}: {truncated_twice_event(phase)} (max_tokens={sctx.config.agent.max_tokens}; the call and "
                "its one retry); the truncated output was discarded, not repaired",
                _not_assessed_impact(shard.criteria))
            sctx.emit(f"{label}: answer truncated twice at the output cap; its criteria are not assessed", "warn")
            return ShardResult(**base, outcome="truncated", call_id=last, prompt_hash=call.brief.sha256,
                               delta=state_delta(iso.base, sctx.state))
        sctx.state.add_degradation(
            DegradationType.OTHER,
            f"the model declined {label} after a reframed retry (refusal category: "
            f"{call.refusal_category or 'none given'})", _not_assessed_impact(shard.criteria))
        sctx.emit(f"model declined {label} twice; its criteria are not assessed", "warn")
        return ShardResult(**base, outcome="declined", call_id=last, prompt_hash=call.brief.sha256,
                           delta=state_delta(iso.base, sctx.state))

    # ------------------------------------------------------------------ merge (code)

    def merge(self, ctx: RunContext, results: Sequence[ShardResult]) -> None:
        """Merge the shards in shard order (see the module docstring). Replaces the four assess
        fields, so a re-run from the checkpoint is safe."""
        ordered = sorted(results, key=lambda r: r.index)
        count = len(ordered)
        for r in ordered:
            apply_delta(ctx.state, r.delta)
        findings: list[FindingDraft] = []
        areas: list[SoundAreaDraft] = []
        coverage: dict[str, CriterionCoverage] = {}
        meta: dict[str, FindingMeta] = {}
        reserved: set[str] = set(ctx.state.finding_meta)
        next_n = 1
        doc_added = inference_added = dropped = 0
        for r in ordered:
            out = r.output
            if out is None:
                for c in r.criteria:
                    coverage[c] = CriterionCoverage(criterion_id=c, outcome="not_applicable", finding_ids=[],
                                                    note=NOT_ASSESSED_NOTE[r.outcome])
                continue
            order = sorted(range(len(out.findings)), key=lambda i: (out.findings[i].rank, i))
            renamed: list[FindingDraft] = []
            id_map: dict[str, str] = {}
            for i in order:
                d = out.findings[i]
                while finding_id(next_n) in reserved:
                    next_n += 1
                new = finding_id(next_n)
                next_n += 1
                id_map.setdefault(d.id, new)
                renamed.append(d.model_copy(update={"id": new}))
            new_ids = [f.id for f in renamed]
            shard_findings, _ = normalise_findings(ctx, renamed, keep_ids=new_ids, reserved=reserved)
            ids = set(new_ids)
            shard_areas = normalise_sound_areas(ctx, out.sound_areas, id_map, ids)
            shard_findings, shard_areas, stats = resolve_evidence(ctx, shard_findings, shard_areas, shown=())
            doc_added, inference_added = doc_added + stats.doc_added, inference_added + stats.inference_added
            dropped += stats.dropped
            reserved |= ids
            rows = reconcile_coverage(ctx, out.coverage, shard_findings, id_map, criteria=r.criteria)
            if r.outcome != "done":                     # a cut shard: criteria without a finding were not assessed
                rows = [row if row.finding_ids else row.model_copy(update={
                    "outcome": "not_applicable", "note": NOT_ASSESSED_NOTE["cut"]}) for row in rows]
            for row in rows:
                coverage[row.criterion_id] = row
            for f in shard_findings:
                meta[f.id] = FindingMeta(finding_id=f.id, criterion_ids=list(f.criterion_ids),
                                         created_phase=self.name, created_call_id=r.call_id, last_phase=self.name,
                                         last_call_id=r.call_id, model=r.model, prompt_hash=r.prompt_hash,
                                         iteration=r.iteration)
            findings += shard_findings
            areas += shard_areas
        findings = sorted(rank_by_severity(findings), key=lambda f: f.rank)    # rank order, IDs in shard order
        ctx.state.finding_drafts = findings
        ctx.state.finding_meta = meta
        ctx.state.sound_area_drafts = areas
        # One row per criterion in config order; a finding that cites a criterion of another shard's
        # group is credited there too.
        ctx.state.coverage = reconcile_coverage(ctx, list(coverage.values()), findings)
        if ordered and not any(r.assessed for r in ordered):
            self._not_assessed(ctx, ordered)
        failed = [r for r in ordered if r.outcome != "done"]
        ctx.emit(f"merged {count} shard(s): {len(findings)} findings ({summarise(findings, lambda f: f.kind.value)}); "
                 f"{len(areas)} sound areas; coverage: {summarise(ctx.state.coverage, lambda c: c.outcome)}; "
                 f"evidence: {doc_added} doc and {inference_added} inference entries added to the ledger"
                 + (f"; {len(failed)} shard(s) degraded" if failed else ""), "done")
        if dropped:
            ctx.emit(f"{dropped} evidence citations dropped (not in the evidence register)", "warn")

    @staticmethod
    def _not_assessed(ctx: RunContext, ordered: Sequence[ShardResult]) -> None:
        """No shard produced an assessment: the stage-level disclosure ``report`` turns into the
        ``not_assessed`` verdict, by priority deadline, truncation, refusal (the three reasons)."""
        outcomes = {r.outcome for r in ordered}
        impact = ("the design was not assessed: the report has no findings and its verdict is not a judgement of the "
                  "design")
        if "cut" in outcomes:
            ctx.state.add_degradation(DegradationType.BUDGET_OR_DEADLINE_HIT,
                                      f"{OUT_OF_TIME_BEFORE_ASSESSMENT}: no assess shard finished a single finding by "
                                      "the stage 1 limit", impact + "; rerun with a longer deadline")
        elif "truncated" in outcomes:
            ctx.state.add_degradation(DegradationType.OTHER,
                                      f"{truncated_twice_event(PhaseName.ASSESS)} in every assess shard that did not "
                                      "fail otherwise; no shard produced an assessment",
                                      impact + "; rerun the review (answer length varies between calls)")
        elif "declined" in outcomes:
            if PhaseName.ASSESS.value not in ctx.state.declined_sections:
                ctx.state.declined_sections.append(PhaseName.ASSESS.value)
            ctx.state.add_degradation(DegradationType.OTHER,
                                      "the model declined every assess shard; no shard produced an assessment", impact)


def rank_by_severity(findings: Sequence[FindingDraft]) -> list[FindingDraft]:
    """Ranks 1..n by severity (critical first; a strength, which has none, last), then confidence,
    then the given order. The order of the merged findings, and the order the report keeps when
    refine does not run or falls back."""
    order = sorted(range(len(findings)), key=lambda i: (
        -SEVERITY_RANK.get(findings[i].severity, 0) if findings[i].severity is not None else 1,
        -findings[i].confidence, i))
    return [findings[i].model_copy(update={"rank": r + 1}) for r, i in enumerate(order)]


def _not_assessed_impact(criteria: Sequence[str]) -> str:
    return (f"criteria not assessed: {', '.join(criteria)}; the review is partial for them (no finding, coverage "
            "marked not assessed)")
