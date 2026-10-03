"""``report`` (LLM for the verdict, then code; workstream C, latency redesign W2).
Prompt: ``prompts/report.md``. Output: ``VerdictOutput`` (the verdict only).

Assembles the :class:`~sit_review_agent.models.Review` (:func:`assemble_review`), validates it
against the spec (INV-03) and the invariants, writes ``report.json``, ``ledger.json``, renders
``report.md`` (``report.render.render_markdown``), and finalises ``manifest.json``. Every
degradation is cited by a limitation (INV-07). A capped run (deadline) still reports, with a
partial-evidence caveat; if the model is unavailable the verdict text falls back to an LLM-free
template that says so (fresh_eyes N3). A run with no assessment (the deadline skipped or cut
``assess``, its answer was truncated twice at the output cap, or the model declined it) gets no
verdict call: its verdict is ``not_assessed``.

What assembly guarantees by construction (each is disclosed, never hidden):

* the model's verdict may cite only known finding IDs (others are removed);
* unresolved items and limitations are written by code, never by the model (latency redesign,
  design section 9 decision 6): verify's unverified points, then one item per non-refinement
  finding; one limitation per degradation (its own event and impact). Open questions not tied to a
  finding (unanswered research questions) are not repeated as unresolved items: they are listed in
  ``research_log.unanswered_questions``. Prose limitations that grouped several degradations are
  dropped: each degradation has its own limitation;
* the verdict call is cut at ``stage_limits_s.verdict_end`` (llm.runtime); a cut, failed or
  declined verdict call gives the verdict by rule (:func:`fallback_verdict`), disclosed;
* failed tool calls, cap stops and model fallbacks that no phase recorded as a degradation get
  one (INV-07);
* a URL or DOI in free text that is not a ledger ``url_or_citation`` is replaced by
  ``[link removed: not in the evidence register]`` and disclosed as a degradation (INV-05);
* every finding ID in the text follows its finding through the run's ID map (:func:`settle_refs`,
  ``finding_refs``): a shard's own ID, a merged ID and a renumbered ID become the final ID, a reference
  to a withdrawn, dropped or unverified draft is removed with its clause, and a disclosure names a draft
  as ``draft FND-nnn``; the coverage notes of ``report.md`` the same way. The counts go to the manifest
  (``extra.finding_ids.rewrites``) and INV-12 checks the result. Model briefs are never rewritten (a
  recorded run replays with the same requests), so this happens here, after the verdict call.

Anything the invariants still reject after that is a bug: the phase writes ``failure.json`` and
``report.invalid.json`` and raises :class:`~sit_review_agent.errors.StageCrash` (exit 4).
"""

from __future__ import annotations

from typing import Any

from sit_review_agent.clock import isoformat_z
from sit_review_agent.context import RunContext
from sit_review_agent.delta import build_prior_table, mark_regressions, prior_findings_of, unknown_prior_refs
from sit_review_agent.errors import (
    ExitCode,
    LLMDeadlineError,
    LLMError,
    LLMRefusalError,
    LLMSchemaError,
    LLMTruncatedError,
    StageCrash,
)
from sit_review_agent.finding_refs import RewriteStats, chain_of, dangling_refs, mark_drafts, rewrite_tree
from sit_review_agent.hashing import sha256_file
from sit_review_agent.invariants import URL_RE, check_all, spec_validator
from sit_review_agent.llm.backend import supports_native_pdf
from sit_review_agent.llm.gateway import LLMRequest
from sit_review_agent.llm.outputs import CriterionCoverage, VerdictOutput
from sit_review_agent.llm.prefix import start_conversation
from sit_review_agent.llm.usage_budget import add_usage, cost_lower_bound_line
from sit_review_agent.manifest import build_manifest, outcome_for, report_json_sha256, write_manifest
from sit_review_agent.models import (
    NON_REFINEMENT_DISPOSITIONS,
    DegradationType,
    Disposition,
    DocumentMeta,
    DocumentRole,
    Finding,
    IntentSummary,
    Kind,
    ObjectiveVerdict,
    PriorFindingEntry,
    RegistryHash,
    ResearchLogEntry,
    Review,
    ReviewMode,
    Severity,
    StopReason,
    StopReasonCode,
    ToolCallStatus,
    UnresolvedItem,
    Verdict,
    VerdictCondition,
    VerdictLabel,
)
from sit_review_agent.progress import ctx_event
from sit_review_agent.rundir import JsonlWriter, write_json_atomic
from sit_review_agent.states import PhaseName

CONVERSATION_ID = "report"
LINK_REMOVED = "[link removed: not in the evidence register]"
_RETRYABLE = (LLMRefusalError,)
_FALLBACK = (LLMRefusalError, LLMSchemaError, LLMTruncatedError, LLMDeadlineError)


def _severity_counts(findings: Any) -> dict[str, int]:
    """Findings per severity (``none`` for a finding without one), for the ``verdict`` event."""
    out: dict[str, int] = {}
    for f in findings:
        sev = getattr(getattr(f, "severity", None), "value", None) or "none"
        out[sev] = out.get(sev, 0) + 1
    return out


class InvariantViolation(Exception):
    """The assembled Review breaks an invariant: a bug upstream, never silently fixed."""


# =============================================================================== verdict call


def _brief_vars(ctx: RunContext, *, refusal_retry: bool) -> dict[str, Any]:
    st = ctx.state
    return {
        "findings": [{"id": f.id, "rank": f.rank, "kind": f.kind.value,
                      "severity": f.severity.value if f.severity else None, "disposition": f.disposition.value,
                      "title": f.title, "statement": f.statement} for f in st.findings],
        "objectives": [{"ref": o.ref, "text": o.text} for o in (st.intent_summary.objectives if st.intent_summary
                                                                  else [])],
        "degradations": [{"id": d.id, "type": d.type.value, "event": d.event, "impact": d.impact}
                         for d in st.degradations],
        "stop_reason": {"code": st.stop_reason.code.value, "detail": st.stop_reason.detail} if st.stop_reason else None,
        "unverified": [u.text for u in st.unresolved],
        "refusal_retry": refusal_retry,
    }


async def _verdict_call(ctx: RunContext) -> tuple[VerdictOutput | None, str | None]:
    """The single verdict call (plus one refusal retry with professional-review framing, LLM-06).
    Returns ``(None, reason)`` when the model's answer cannot be used."""
    persona = ctx.config.persona()
    system = ctx.prompts.render("system.md", persona_title=persona.title, persona_emphasis=persona.emphasis)
    docs = [ctx.doc_under_review()] + [d for d in ctx.documents.values() if d.role is not DocumentRole.UNDER_REVIEW]
    retries = ctx.config.agent.llm.refusal_retries
    for attempt in range(retries + 1):
        brief = ctx.prompts.render("report.md", **_brief_vars(ctx, refusal_retry=attempt > 0))
        messages, bp = start_conversation(docs, brief.text, native_pdf=supports_native_pdf(ctx.llm))
        req = LLMRequest(phase=PhaseName.REPORT, conversation_id=f"{CONVERSATION_ID}-{attempt}" if attempt
                         else CONVERSATION_ID, system=system.text, messages=messages,
                         effort=ctx.config.effort_for(PhaseName.REPORT), max_tokens=ctx.config.agent.max_tokens,
                         output_schema=VerdictOutput, cache_breakpoints=(bp,),
                         thinking_display=ctx.config.agent.thinking_display,
                         purpose="refusal_retry" if attempt else "verdict")
        try:
            res = await ctx.llm.call(req)
        except LLMError as exc:
            add_usage(ctx.state.budget, exc.usage)
            if not isinstance(exc, _FALLBACK) and exc.exit_code is not ExitCode.LLM_UNAVAILABLE:
                raise                       # bugs (bad request, effort change, exhausted fake script)
            if exc.call_id:
                ctx.state.llm_calls.setdefault(PhaseName.REPORT.value, []).append(exc.call_id)
            if isinstance(exc, LLMRefusalError):
                ctx.state.refusals.append({"call_id": exc.call_id, "stage": PhaseName.REPORT.value,
                                           "category": exc.category})
            if isinstance(exc, _RETRYABLE) and attempt < retries:
                cat = getattr(exc, "category", None) or "none given"
                ctx_event(ctx, f"model declined the verdict (category: {cat}); retrying with review framing", "warn",
                          event="call_retry", reason="refusal_retry", stage=PhaseName.REPORT.value,
                          call_id=exc.call_id, category=getattr(exc, "category", None))
                continue
            return None, f"{type(exc).__name__}: {str(exc)[:160]}"
        ctx.state.llm_calls.setdefault(PhaseName.REPORT.value, []).append(res.call_id)
        add_usage(ctx.state.budget, res.usage)
        if res.fallback is not None:
            ctx.state.fallback_events.append(res.fallback)
        if res.parsed is None:
            return None, "the verdict call returned no structured output"
        return res.parsed, None
    return None, "the model declined the verdict"


def fallback_verdict(findings: list[Finding], reason: str) -> Verdict:
    """LLM-free verdict by rule (fresh_eyes N3): any open critical finding -> not_fit; any other
    open finding -> fit_with_conditions (conditions = the five highest-ranked); else fit."""
    open_ = [f for f in findings if f.disposition is not Disposition.NO_CHANGE and f.kind is not Kind.STRENGTH]
    critical = [f for f in open_ if f.severity is Severity.CRITICAL]
    why = (f"Verdict derived by rule from the severities and dispositions of the verified findings, because no "
           f"model verdict was available ({reason}). See the limitations.")
    if critical:
        return Verdict(label=VerdictLabel.NOT_FIT, rationale=why, confidence=0.5,
                       conditions=[VerdictCondition(text=f"Resolve {f.id}: {f.title}", finding_ids=[f.id])
                                   for f in critical[:5]], per_objective=[], what_would_change_it=None)
    if open_:
        top = sorted(open_, key=lambda f: f.rank)[:5]
        return Verdict(label=VerdictLabel.FIT_WITH_CONDITIONS, rationale=why, confidence=0.5,
                       conditions=[VerdictCondition(text=f"Address {f.id}: {f.title}", finding_ids=[f.id])
                                   for f in top], per_objective=[], what_would_change_it=None)
    return Verdict(label=VerdictLabel.FIT, rationale=why, confidence=0.5, conditions=[], per_objective=[],
                   what_would_change_it=None)


def assessment_cut(degradation_events: list[str]) -> bool:
    """Whether the run deadline left the design unassessed (robustness LLM-05): the orchestrator or
    ``assess`` recorded the ``out of time before assessment`` degradation."""
    from sit_review_agent.llm.runtime import OUT_OF_TIME_BEFORE_ASSESSMENT

    return any(e.startswith(OUT_OF_TIME_BEFORE_ASSESSMENT) for e in degradation_events)


#: Why a run has no assessment -> (what happened, what to do), used in the not-assessed verdict.
_NOT_ASSESSED_TEXT = {
    "deadline": ("the run ran out of time before assessment", "Rerun the review with a longer deadline."),
    "truncated": ("the model's assessment was cut off at the output cap twice (the assess call and its one "
                  "retry), and a truncated answer is never repaired",
                  "Rerun the review (answer length varies between calls); if the assessment is cut off again, "
                  "assess fewer criteria per run."),
    "declined": ("the model declined the assess call, also after one reframed retry",
                 "Rerun the review; if the model declines again, review the cited sections by hand."),
}

#: Why a run has no assessment -> the short form in progress lines and ``report.md`` labels.
NOT_ASSESSED_WHY = {
    "deadline": "out of time before assessment",
    "truncated": "answer truncated twice at the output cap",
    "declined": "the model declined the assessment",
}


def assessment_missing(degradation_events: list[str], declined_sections: list[str]) -> str | None:
    """Why the run has no assessment, or ``None`` when ``assess`` produced model output:
    ``"deadline"`` (the deadline skipped or cut assess, robustness LLM-05), ``"truncated"`` (the
    assess answer was cut off at the output cap on the call and its one retry, LLM-07) or
    ``"declined"`` (the model refused the assess call twice, LLM-06). In each case there is nothing
    a verdict could rest on, so ``report`` makes no verdict call and reports ``not_assessed``."""
    from sit_review_agent.llm.runtime import truncated_twice_event

    if assessment_cut(degradation_events):
        return "deadline"
    if any(e.startswith(truncated_twice_event(PhaseName.ASSESS)) for e in degradation_events):
        return "truncated"
    if PhaseName.ASSESS.value in declined_sections:
        return "declined"
    return None


def not_assessed_verdict(reason: str = "deadline") -> Verdict:
    """The verdict of a run that produced no assessment (``reason`` from :func:`assessment_missing`).
    The label is ``not_assessed`` (set by code only; the model's output schema does not offer it),
    at confidence 0 with no conditions, so an unreviewed design is neither certified nor called
    unfit. The rationale and ``report.md`` say plainly that no assessment took place
    (``report.render``). No finding is made up."""
    what, then = _NOT_ASSESSED_TEXT[reason]
    return Verdict(label=VerdictLabel.NOT_ASSESSED, confidence=0.0, conditions=[], per_objective=[],
                   rationale=f"Not assessed: {what}, so the design was not reviewed and no finding was produced. "
                             "This is not a judgement of the design; it must not be read as a review result.",
                   what_would_change_it=then)


def settle_report_output(ctx: RunContext, out: VerdictOutput) -> Verdict:
    """Canonical verdict from the model's draft: unknown finding IDs removed, empty conditions
    dropped, confidence clamped to [0, 1]. Unresolved items and limitations are not the model's
    (module docstring)."""
    known = {f.id for f in ctx.state.findings}
    v = out.verdict
    conditions: list[VerdictCondition] = []
    for c in v.conditions:
        ids = list(dict.fromkeys(x for x in c.finding_ids if x in known))
        if c.text.strip() and ids:
            conditions.append(VerdictCondition(text=c.text.strip(), finding_ids=ids))
    label = VerdictLabel(v.label.value)      # the draft type admits only the assessed labels
    notes: list[str] = []
    if label is VerdictLabel.FIT_WITH_CONDITIONS and not conditions:
        rule = fallback_verdict(ctx.state.findings, "conditions cited no verified finding")
        conditions = rule.conditions
        if not conditions:
            label = VerdictLabel.FIT
            notes.append("verdict fit_with_conditions had no condition linked to a verified finding; reported as fit")
        else:
            notes.append("verdict conditions cited no verified finding; conditions derived from the open findings")
    verdict = Verdict(
        label=label, rationale=v.rationale.strip() or "No rationale was given.",
        confidence=min(1.0, max(0.0, float(v.confidence))), conditions=conditions,
        per_objective=[ObjectiveVerdict(objective_ref=o.objective_ref.strip(), label=VerdictLabel(o.label.value),
                                        finding_ids=[x for x in dict.fromkeys(o.finding_ids) if x in known])
                       for o in v.per_objective if o.objective_ref.strip()],
        what_would_change_it=v.what_would_change_it)
    for n in notes:
        ctx.state.add_degradation(DegradationType.OTHER, n, "the verdict's conditions were adjusted in code")
    open_serious = [f.id for f in ctx.state.findings if f.disposition is not Disposition.NO_CHANGE
                    and f.severity in (Severity.CRITICAL, Severity.HIGH)]
    if label is VerdictLabel.FIT and open_serious:          # disclosed, not changed: the verdict is the model's
        ctx.state.add_degradation(
            DegradationType.OTHER,
            f"the verdict 'fit' is inconsistent with open high or critical findings ({', '.join(open_serious)})",
            "read the verdict together with those findings; the code check does not override the verdict")
    return verdict


# =============================================================================== assembly


def _research_log_calls(ctx: RunContext) -> list[ResearchLogEntry]:
    calls: dict[str, ResearchLogEntry] = {c.call_id: c for c in ctx.state.tool_calls}
    for e in JsonlWriter(ctx.run_dir.tools_log).read():
        cid = e.get("call_id")
        if not cid or cid in calls:
            continue
        try:
            status = ToolCallStatus(e.get("status", "error"))
        except ValueError:
            status = ToolCallStatus.ERROR
        calls[cid] = ResearchLogEntry(call_id=cid, server=e.get("server") or "unknown",
                                      tool_name=e.get("tool") or "unknown", status=status,
                                      started_at=e.get("started_at") or ctx.state.created_utc)
    return list(calls.values())


def _ensure_disclosures(ctx: RunContext, calls: list[ResearchLogEntry], stop: StopReason) -> None:
    """INV-07 by construction: failed tool calls, cap stops and fallbacks become degradations."""
    st = ctx.state
    types = {d.type for d in st.degradations}
    failed = [c for c in calls if c.status in (ToolCallStatus.ERROR, ToolCallStatus.TIMEOUT)]
    if failed and not types & {DegradationType.TOOL_ERROR, DegradationType.TOOL_UNAVAILABLE}:
        st.add_degradation(DegradationType.TOOL_ERROR, f"{len(failed)} tool call(s) failed: "
                           + ", ".join(f"{c.server}/{c.tool_name} {c.status.value}" for c in failed[:5]),
                           "evidence those calls would have returned is missing")
    if stop.group.value == "cap" and DegradationType.BUDGET_OR_DEADLINE_HIT not in types:
        st.add_degradation(DegradationType.BUDGET_OR_DEADLINE_HIT,
                           f"research stopped by a cap: {stop.code.value} ({stop.detail or 'no detail'})",
                           "research ended before every question was answered; evidence may be partial")
    if stop.code is StopReasonCode.TOOL_FAILURE and not {d.type for d in st.degradations} & {
            DegradationType.TOOL_ERROR, DegradationType.TOOL_UNAVAILABLE}:
        st.add_degradation(DegradationType.TOOL_UNAVAILABLE, "research stopped because tools failed",
                           "external evidence is missing or partial")
    from sit_review_agent.manifest import merged_fallback_events

    fb = merged_fallback_events(ctx)
    have = sum(1 for d in st.degradations if d.type is DegradationType.MODEL_FALLBACK)
    for ev in fb[have:]:
        st.add_degradation(DegradationType.MODEL_FALLBACK, f"{ev.role}: {ev.from_model} -> {ev.to_model} ({ev.reason})",
                           "part of the review was produced by another model; the run is not eval evidence")


def _redact(node: Any, allowed: set[str], counter: list[int]) -> Any:
    if isinstance(node, str):
        def sub(m: Any) -> str:
            url = m.group(0)
            if url.rstrip(".,;:") in allowed:
                return url
            counter[0] += 1
            return LINK_REMOVED
        return URL_RE.sub(sub, node)
    if isinstance(node, list):
        return [_redact(x, allowed, counter) for x in node]
    if isinstance(node, dict):
        return {k: (v if k == "url_or_citation" else _redact(v, allowed, counter)) for k, v in node.items()}
    return node


#: Review sections the ID rewrite reads in the final numbering (written after verify, or by code).
_FINAL_SECTIONS = ("intent_summary", "verdict", "decision_registry", "stop_reason")


def settle_refs(ctx: RunContext, body: dict[str, Any]) -> dict[str, Any]:
    """``body`` (the Review as JSON, before validation) with every finding-ID reference rewritten
    through ``state.finding_ids`` (``finding_refs``), each text in the numbering it was written in: a
    finding's fields in its shard's (the fields refine wrote in the merged numbering), verify's
    unverified items in their draft's shard's, sound areas in the merged numbering (moved there at
    the merge), the verdict and code-written text in the final one; disclosures mark drafts. Also
    rewrites ``state.coverage`` notes (``report.md``) and records the counts in
    ``state.finding_ids.rewrites``. Reads only the run state, so a re-run from the verify checkpoint
    gives the same text."""
    st = ctx.state
    ids = st.finding_ids
    final = [f["id"] for f in body["findings"]]
    chain = chain_of(ids, final)
    origin = chain.origin()
    renamed = {v: k for k, v in ids.verify.items() if v is not None}
    stats = RewriteStats()
    out = dict(body)
    findings = []
    for f in body["findings"]:
        draft = renamed.get(f["id"], f["id"])
        override = {k: chain.draft for k in ids.refine_fields.get(draft, [])}
        findings.append(rewrite_tree(f, chain.shard(origin.get(draft)), stats, override=override))
    out["findings"] = findings
    out["sound_areas"] = rewrite_tree(body["sound_areas"], chain.draft, stats)
    unresolved = []
    for i, u in enumerate(body["unresolved"]):
        own = chain.shard(origin.get(ids.unverified[i])) if i < len(ids.unverified) else chain.final_id
        unresolved.append(rewrite_tree(u, own, stats))
    out["unresolved"] = unresolved
    for k in _FINAL_SECTIONS:
        out[k] = rewrite_tree(body[k], chain.final_id, stats)
    log = dict(body["research_log"])
    for k, v in log.items():
        if k != "degradations":
            log[k] = rewrite_tree(v, chain.final_id, stats)
    log["degradations"] = [{**d, "event": mark_drafts(d["event"], final, ids.prior, stats=stats),
                            "impact": mark_drafts(d["impact"], final, ids.prior, stats=stats)}
                           for d in body["research_log"]["degradations"]]
    out["research_log"] = log
    out["limitations"] = [{**lim, "text": mark_drafts(lim["text"], final, ids.prior, stats=stats)}
                          for lim in body["limitations"]]
    st.coverage = [CriterionCoverage.model_validate(rewrite_tree(c.model_dump(mode="json"), chain.draft, stats))
                   for c in st.coverage]
    st.finding_ids = ids.model_copy(update={"rewrites": stats.as_dict()})
    return out


def _default_stop_reason(ctx: RunContext) -> StopReason:
    """The run's stop reason, with the ``sufficient_evidence`` gate applied over the whole run (the
    findings now cite their sources); the settled reason is kept in the state, so the manifest agrees."""
    from sit_review_agent import stop_rules

    stop = ctx.state.stop_reason
    if stop is None:
        ran = PhaseName.RESEARCH in ctx.state.completed_phases
        stop = StopReason.of(StopReasonCode.SUFFICIENT_EVIDENCE, "research_completed" if ran else "research_not_run")
    settled = stop_rules.settle_sufficient_evidence(stop, ctx.state, ctx.config.stop_rules, ctx.ledger)
    if ctx.state.stop_reason is not None or settled is not stop:
        ctx.state.stop_reason = settled
    return settled


def _intent(ctx: RunContext) -> IntentSummary:
    if ctx.state.intent_summary is not None:
        return ctx.state.intent_summary
    from sit_review_agent.phases.verify import intent_fallback_anchor

    anchor = intent_fallback_anchor(ctx.doc_under_review())
    if anchor is None:
        raise InvariantViolation("no intent summary and no verifiable passage to anchor one")
    ctx.state.add_degradation(DegradationType.OTHER, "no design-intent summary was produced",
                              "the review states no design intent; objectives were not checked one by one")
    return IntentSummary(statement="The design intent could not be summarised in this run; see the document's "
                                   "opening section.", objectives=[], constraints=[], key_assumptions=[],
                         doc_anchors=[anchor])


def _delta_table(ctx: RunContext, findings: list[Finding]) -> tuple[list[Finding], list[PriorFindingEntry]]:
    """Delta mode (``delta``): the findings with ``reassessment.regression`` computed from the two
    texts, and the delta table with one status per finding of the previous review. Prior findings
    that got no status, and reassessments citing an ID the previous review does not have, are
    disclosed (each once, so a re-run of the phase adds nothing)."""
    st = ctx.state
    findings = mark_regressions(findings, ctx.doc_under_review(), ctx.prior_document())
    prior = prior_findings_of(st.previous_run_dir)
    if prior and not st.finding_ids.prior:              # assess did not run: disclosures still cite prior IDs
        st.finding_ids = st.finding_ids.model_copy(update={"prior": [p["id"] for p in prior]})
    table, missing = build_prior_table(prior, findings, st.prior_statuses)

    def disclose(event: str, impact: str) -> None:
        if not any(d.event == event for d in st.degradations):
            st.add_degradation(DegradationType.OTHER, event, impact)

    if missing:
        disclose(f"{len(missing)} of {len(prior)} findings of the previous review were not re-examined (no status "
                 f"from the model, or their only successor was not kept): previous review's "
                 f"{', '.join(missing)}",
                 "recorded as still open with the note 'not re-examined' in the delta table; whether the update "
                 "fixed them was not judged")
    unknown = unknown_prior_refs(prior, findings)
    if unknown:
        disclose(f"{len(unknown)} reassessment(s) cite an ID the previous review does not have ({'; '.join(unknown)})",
                 "those findings are not in the delta table; their stated prior link is unchecked")
    return findings, table


def assemble_review(ctx: RunContext) -> Review:
    """Build the Review envelope from ``ctx.state``, the ledger, the registry and the manifest."""
    st = ctx.state
    intent = _intent(ctx)
    findings = list(st.findings)
    verdict = st.verdict or fallback_verdict(findings, "no verdict was produced")
    prior_table: list[PriorFindingEntry] = []
    if st.review_mode is ReviewMode.DELTA:
        findings, prior_table = _delta_table(ctx, findings)

    unresolved = list(st.unresolved)
    listed = {x for u in unresolved for x in u.finding_ids}
    for f in sorted(findings, key=lambda f: f.rank):
        if f.disposition in NON_REFINEMENT_DISPOSITIONS and f.id not in listed:
            unresolved.append(UnresolvedItem(text=f"{f.id} ({f.disposition.value.replace('_', ' ')}): {f.title}",
                                             finding_ids=[f.id], next_step=f.next_step))

    calls = _research_log_calls(ctx)
    stop = _default_stop_reason(ctx)
    _ensure_disclosures(ctx, calls, stop)
    ledger = ctx.ledger.entries()
    external = [e for e in ledger if e.source_type.value == "external"]
    cited = {e.evidence_id for f in findings for e in f.evidence} | {x for s in st.sound_areas for x in s.evidence_ids}
    by_server: dict[str, int] = {}
    for c in calls:
        by_server[c.server] = by_server.get(c.server, 0) + 1
    hashes = list(ctx.registry.hashes()) or [RegistryHash(iteration=0, sha256=ctx.registry.sha256())]

    documents = [DocumentMeta(doc_id=d.doc_id, title=d.title, version=d.version, role=d.role, sha256_pdf=d.sha256_pdf,
                              sha256_text=d.sha256_text, text_path=d.text_path, page_count=d.page_count)
                 for d in st.documents]
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "metadata": {"review_id": f"REV-{st.run_id}", "run_id": st.run_id, "created_at": st.created_utc,
                     "review_mode": st.review_mode.value, "documents": [d.model_dump(mode="json") for d in documents],
                     "prior_review_id": st.prior_review_id if st.review_mode is ReviewMode.DELTA else None,
                     "taxonomy_version": "1.0"},
        "intent_summary": intent.model_dump(mode="json"),
        "verdict": verdict.model_dump(mode="json"),
        "findings": [f.model_dump(mode="json") for f in findings],
        "sound_areas": [s.model_dump(mode="json") for s in st.sound_areas],
        "unresolved": [u.model_dump(mode="json") for u in unresolved],
        "decision_registry": [e.model_dump(mode="json") for e in ctx.registry.entries()],
        "evidence_ledger": [e.model_dump(mode="json") for e in ledger],
        "research_log": {
            "iterations": st.budget.research_iterations, "tool_calls_by_tool": by_server,
            "tool_calls": [c.model_dump(mode="json") for c in calls],
            "queries_issued": st.queries_issued, "sources_retrieved": len(external),
            "sources_cited": len({e.evidence_id for e in external} & cited),
            "unanswered_questions": list(st.unanswered_questions),
            "degradations": [d.model_dump(mode="json") for d in st.degradations],
            "registry_sha256_by_iteration": [h.model_dump(mode="json") for h in hashes]},
        "limitations": [lim.model_dump(mode="json") for lim in st.limitations],
        "stop_reason": stop.model_dump(mode="json"),
        "prior_findings": [e.model_dump(mode="json") for e in prior_table],
    }
    allowed = {e.url_or_citation for e in ledger}
    counter = [0]
    redacted = {k: (v if k in ("evidence_ledger", "metadata") else _redact(v, allowed, counter))
                for k, v in body.items()}
    if counter[0]:
        event = f"{counter[0]} URL(s) or DOI(s) in model-written text were not in the evidence register"
        if not any(d.event == event for d in st.degradations):
            d = st.add_degradation(DegradationType.OTHER, event,
                                   f"they were replaced by '{LINK_REMOVED}'; only ledger sources are cited")
            redacted["research_log"]["degradations"].append(d.model_dump(mode="json"))
    deg_ids = [d["id"] for d in redacted["research_log"]["degradations"]]
    lims = [lim for lim in redacted["limitations"] if lim["degradation_ids"] or lim["text"]]
    covered = {x for lim in lims for x in lim["degradation_ids"]}
    for d in redacted["research_log"]["degradations"]:
        if d["id"] not in covered:
            lims.append({"text": f"{d['event']}. Impact: {d['impact']}", "degradation_ids": [d["id"]]})
    lims = [lim for lim in lims if all(x in deg_ids for x in lim["degradation_ids"])]
    redacted["limitations"] = lims
    redacted = settle_refs(ctx, redacted)
    manifest = build_manifest(ctx, outcome_for(ctx), end_utc=isoformat_z(ctx.clock.now_utc()))
    redacted["run_manifest"] = manifest.model_dump(mode="json")
    return Review.model_validate(redacted)


# =============================================================================== phase


class ReportPhase:
    name = PhaseName.REPORT

    async def run(self, ctx: RunContext) -> RunContext:
        st = ctx.state
        if not ctx.documents:
            raise StageCrash(PhaseName.REPORT.value, InvariantViolation("no documents loaded"))
        missing = assessment_missing([d.event for d in st.degradations], st.declined_sections)
        if missing is not None and not st.findings and not st.sound_areas:
            # No assessment (out of time, robustness LLM-05; truncated twice, LLM-07; declined, LLM-06):
            # no model verdict on an unassessed design. A verdict call could only invent one.
            why = NOT_ASSESSED_WHY[missing]
            ctx_event(ctx, f"{why}: no verdict call; the report says the design was not assessed", "warn",
                      event="not_assessed", reason=missing)
            st.verdict = not_assessed_verdict(missing)
            st.limitations = []
        else:
            out, reason = await _verdict_call(ctx)
            if out is None:
                st.add_degradation(DegradationType.BUDGET_OR_DEADLINE_HIT if reason and reason.startswith(
                    LLMDeadlineError.__name__) else DegradationType.OTHER, f"verdict call failed: {reason}",
                    "the verdict was derived by rule from the findings (no model judgement)")
                st.verdict = fallback_verdict(st.findings, reason or "unavailable")
            else:
                st.verdict = settle_report_output(ctx, out)
            st.limitations = []                                     # one per degradation, by assemble_review

        try:
            review = assemble_review(ctx)
        except InvariantViolation as exc:
            raise StageCrash(PhaseName.REPORT.value, exc) from exc
        ctx.ledger.write_snapshot()
        md = self._render(ctx, review)
        rd = ctx.run_dir
        outputs = {"ledger_sha256": sha256_file(rd.ledger),
                   "llm_jsonl_sha256": sha256_file(rd.llm_log) if rd.llm_log.exists() else None,
                   "tools_jsonl_sha256": sha256_file(rd.tools_log) if rd.tools_log.exists() else None,
                   "anchors_sha256": sha256_file(rd.anchors) if rd.anchors.exists() else None,
                   "report_md_sha256": _sha_text(md), "report_json_sha256": None}
        review.run_manifest.extra["outputs"] = outputs
        data = review.model_dump(mode="json")
        outputs["report_json_sha256"] = report_json_sha256(data)
        data = review.model_dump(mode="json")
        if self._render(ctx, review) != md:
            raise StageCrash(PhaseName.REPORT.value, InvariantViolation("report.md depends on extra.outputs"))
        write_manifest(rd, review.run_manifest)

        problems = [f"schema: {'/'.join(map(str, e.absolute_path))}: {e.message}"
                    for e in spec_validator("Review").iter_errors(data)]
        delta_kw = ({"prior_ids": [p["id"] for p in prior_findings_of(st.previous_run_dir)]}
                    if st.review_mode is ReviewMode.DELTA and st.previous_run_dir else {})
        results = check_all(review, rd.root, **delta_kw)
        problems += [f"{r.inv_id}: {p}" for r in results if not r.passed for p in r.problems]
        problems += [f"INV-12 (report.md): {p}" for p in dangling_refs({   # coverage notes are in report.md only
            "findings": data["findings"], "run_manifest": data["run_manifest"],
            "coverage": [c.model_dump(mode="json") for c in st.coverage]})]
        if problems:
            write_json_atomic(rd.root / "report.invalid.json", data)
            write_json_atomic(rd.failure, {"phase": "report", "error": "InvariantViolation", "problems": problems,
                                           "partial_report": "report.invalid.json"})
            raise StageCrash(PhaseName.REPORT.value, InvariantViolation("; ".join(problems)[:2000]))
        write_json_atomic(rd.report_json, data)
        rd.report_md.write_text(md, encoding="utf-8")
        ctx_event(ctx, f"verdict {review.verdict.label.value}; {len(review.findings)} findings, "
                  f"{len(review.unresolved)} unresolved, {len(review.limitations)} limitations; "
                  f"invariants INV-03..10, INV-12 and INV-13 pass; wrote {rd.relative(rd.report_md)}", event="verdict",
                  label=review.verdict.label.value, confidence=getattr(review.verdict, "confidence", None),
                  findings=len(review.findings), unresolved=len(review.unresolved),
                  limitations=len(review.limitations), by_severity=_severity_counts(review.findings),
                  report_md=str(rd.report_md), report_json=str(rd.report_json))
        lower = cost_lower_bound_line(data["run_manifest"])
        if lower is not None:
            ctx_event(ctx, lower, "warn", event="cost_lower_bound")
        return ctx

    @staticmethod
    def _render(ctx: RunContext, review: Review) -> str:
        from sit_review_agent.report.render import render_markdown

        rep = ctx.config.agent.report
        return render_markdown(review, template=rep.template, min_severity=rep.min_severity,
                               coverage=list(ctx.state.coverage))


def _sha_text(text: str) -> str:
    from sit_review_agent.hashing import sha256_text

    return sha256_text(text)

