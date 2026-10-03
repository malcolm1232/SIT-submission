"""``plan`` (LLM, workstream A). Prompt: ``prompts/plan.md``. Output: ``PlanOutput``.

Reads: every configured criterion, enabled capabilities (``config.tools.capabilities`` of enabled
servers), the configured tool-call budget and deadline. Not the intent summary, the registry or the
review inputs found by understand: plan runs beside understand in stage 1 (latency redesign, design
section 4, lever 8), so its brief carries the document and the criteria only.
Writes: ``ctx.state.plan`` (ResearchPlan; one or more questions per applicable criterion, each with
a fixed capability). ``--plan-only`` prints the plan and the orchestrator stops after this phase.
With ``plan_approval: true`` the plan is printed and the run waits for approval before research.

Implementation notes (workstream A):

* conversation ``plan-0``; the brief carries the configured tool-call budget and deadline (not the
  time remaining, which would make the prompt volatile, REPRODUCIBILITY §4);
* question IDs are always renumbered ``RQ-001..`` in output order; questions for unknown criteria
  are dropped; a capability that is not enabled (or any capability on a doc-only question) becomes
  ``none``; queries containing a URL are dropped (the model never writes URLs);
* **coverage completeness:** every configured criterion ends up with at least one question or a
  ``criteria_skipped`` entry. A criterion the model left out gets a document-only question added by
  code (its own wording), so ``assess`` still checks it; this is reported as a progress warning;
* ``ResearchPlan.approved`` is ``False`` when ``plan_approval`` is on (the orchestrator/CLI waits);
* a persistent refusal, a call cut by the run deadline, or an answer truncated twice at the output
  cap produces the same code-built plan: one document-only question per criterion, disclosed as a
  degradation by the model-call helper; each question's rationale names which of the three it was.
"""

from __future__ import annotations

from sit_review_agent.context import RunContext
from sit_review_agent.llm.outputs import CriterionSkip, PlanOutput, ResearchQuestionDraft
from sit_review_agent.phases._model_calls import call_model, criteria_vars, known_criteria
from sit_review_agent.progress import ctx_event
from sit_review_agent.prompts import RenderedPrompt
from sit_review_agent.state.run_state import ResearchPlan, ResearchQuestion
from sit_review_agent.states import PhaseName

CAPABILITY_NONE = "none"


def enabled_capabilities(ctx: RunContext) -> list[str]:
    """Capabilities whose server is enabled, sorted by name (so the plan prompt does not depend on
    the order of ``tools.capabilities``: ``effective_config.json`` is written with sorted keys and
    replay rebuilds the config from it); none for a doc-only run."""
    if ctx.tools is None:
        return []
    out = []
    for cap, server in sorted(ctx.config.tools.capabilities.items()):
        s = ctx.config.tools.server(server)
        if s is not None and s.enabled and cap != CAPABILITY_NONE:
            out.append(cap)
    return out


def doc_only_question(ctx: RunContext, criterion_id: str, rationale: str) -> ResearchQuestionDraft:
    c = ctx.config.criteria.get(criterion_id)
    return ResearchQuestionDraft(id="", criterion_id=criterion_id, question=c.question, rationale=rationale,
                                 needs_external=False, capability=CAPABILITY_NONE, queries=[], section_refs=[])


#: Why there is no model plan -> the rationale of the document-only questions code adds instead.
NO_PLAN_WHY = {
    "declined": "the model declined to plan",
    "deadline": "the plan call was cut by the run deadline",
    "truncated": "the plan answer was truncated twice at the output cap",
}


def build_plan(ctx: RunContext, out: PlanOutput | None, *, missing: str = "declined") -> tuple[ResearchPlan, list[str]]:
    """Normalise the model's plan (see module docstring). Returns the plan and the criteria for
    which code added a question. ``missing`` (a :data:`NO_PLAN_WHY` key) says why ``out`` is
    ``None``."""
    criteria = known_criteria(ctx)
    caps = set(enabled_capabilities(ctx))
    questions: list[ResearchQuestionDraft] = []
    skipped: list[CriterionSkip] = []
    if out is not None:
        for q in out.questions:
            if q.criterion_id not in criteria or not q.question.strip():
                continue
            capability = q.capability if (q.needs_external and q.capability in caps) else CAPABILITY_NONE
            queries = [x.strip() for x in dict.fromkeys(q.queries) if x.strip() and "://" not in x]
            questions.append(q.model_copy(update={"capability": capability, "queries": queries,
                                                  "question": q.question.strip()}))
        covered = {q.criterion_id for q in questions}
        seen: set[str] = set()
        for s in out.criteria_skipped:
            if s.criterion_id in criteria and s.criterion_id not in covered and s.criterion_id not in seen:
                seen.add(s.criterion_id)
                skipped.append(s.model_copy(update={"reason": s.reason.strip() or "not applicable to this design"}))
    covered = {q.criterion_id for q in questions} | {s.criterion_id for s in skipped}
    added = [c for c in criteria if c not in covered]
    why = (f"Added by code: {NO_PLAN_WHY[missing]}; this criterion is checked against the document."
           if out is None else
           "Added by code: the plan did not map this criterion to a question or a skip reason.")
    questions += [doc_only_question(ctx, c, why) for c in added]
    order = {c: i for i, c in enumerate(criteria)}
    questions.sort(key=lambda q: order[q.criterion_id])           # stable: model order within a criterion
    final = [ResearchQuestion(**q.model_copy(update={"id": f"RQ-{i + 1:03d}"}).model_dump())
             for i, q in enumerate(questions)]
    return ResearchPlan(questions=final, criteria_skipped=skipped,
                        approved=not ctx.config.agent.plan_approval), added


class PlanPhase:
    name = PhaseName.PLAN

    async def run(self, ctx: RunContext) -> RunContext:
        phase = self.name
        caps = enabled_capabilities(ctx)
        ctx_event(ctx, f"planning the review over {len(known_criteria(ctx))} criteria "
                  f"(capabilities: {', '.join(caps) or 'none'})", event="plan_started",
                  criteria=len(known_criteria(ctx)), capabilities=list(caps))
        stop = ctx.config.stop_rules

        def render(*, reframed: bool, schema_error: str) -> RenderedPrompt:
            return ctx.prompts.render(
                "plan.md", criteria=criteria_vars(ctx), capabilities=caps, max_tool_calls=stop.max_tool_calls,
                time_budget_minutes=max(1, stop.deadline_seconds // 60), review_mode=ctx.state.review_mode.value,
                reframed=reframed, schema_error=schema_error)

        call = await call_model(ctx, phase, render, PlanOutput, iteration=0, purpose="plan")
        out = call.result.parsed if call.result is not None and isinstance(call.result.parsed, PlanOutput) else None
        missing = "deadline" if call.cut else "truncated" if call.truncated else "declined"
        plan, added = build_plan(ctx, out, missing=missing)
        ctx.state.plan = plan
        if added and out is not None:
            ctx_event(ctx, f"plan left out {len(added)} criteria; added document-only questions for: "
                      f"{', '.join(added)}", "warn", event="plan_criteria_added", criteria=list(added))
        n_ext = sum(1 for q in plan.questions if q.needs_external)
        ctx_event(ctx, f"plan: {len(plan.questions)} questions ({n_ext} need external research), "
                  f"{len(plan.criteria_skipped)} criteria skipped", "done", event="plan_ready",
                  questions=len(plan.questions), external=n_ext, criteria_skipped=len(plan.criteria_skipped),
                  fallback=None if out is not None else missing)
        # The question and the skip reason are model text: progress.jsonl gets the IDs only.
        for q in plan.questions:
            ctx_event(ctx, f"{q.id} [{q.capability}] {q.criterion_id}: {q.question}", event="plan_question",
                      public=f"{q.id} [{q.capability}] {q.criterion_id}", question_id=q.id,
                      capability=getattr(q.capability, "value", q.capability), criterion_id=q.criterion_id,
                      needs_external=q.needs_external)
        for s in plan.criteria_skipped:
            ctx_event(ctx, f"skipped {s.criterion_id}: {s.reason}", event="plan_criterion_skipped",
                      public=f"skipped {s.criterion_id}", criterion_id=s.criterion_id)
        if not plan.approved:
            ctx_event(ctx, "plan_approval is on: waiting for approval before research", "wait",
                      event="plan_approval_waiting")
        return ctx
