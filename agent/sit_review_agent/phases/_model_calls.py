"""Shared plumbing of the model-calling phases owned by workstream A (``understand``, ``plan``,
``assess``, ``refine``). Private to those phases; nothing here is a frozen interface.

The phase contract (``phases/base.py``, agent/README.md) as implemented here:

* **Conversation IDs.** A phase's call uses ``"<phase>-<iteration>"`` (``understand-0``,
  ``plan-0``, ``refine-<n>`` where ``n`` is the number of completed research iterations); an assess
  shard uses ``assess-0-s<k>`` (``conversation=``; latency redesign). A retry of that call
  (refusal reframing, schema repair, larger ``max_tokens``) is a fresh conversation
  ``"<conversation>-r<k>"``: the failed turn is never appended to history
  (its output is discarded, ADR-009 item 3), and with ``ClaudeCodeGateway`` a fresh conversation is
  a fresh CLI session. Every conversation of a phase uses ``config.effort_for(phase)``.
* **Prefix.** Every conversation starts with :func:`llm.prefix.start_conversation` over the
  documents (under review first), with ``native_pdf=supports_native_pdf(ctx.llm)``; the system
  prompt is ``prompts/system.md`` rendered from the persona only, so it is byte-stable in a run.
* **Prompts** are rendered only through ``ctx.prompts.render``. Each phase template takes two
  retry variables besides its own: ``reframed`` (bool; adds the professional-review framing of
  robustness LLM-06) and ``schema_error`` (str; the validation error of the previous answer,
  robustness LLM-08).
* **Retries in the phase** (the gateway already retried transport errors): a refusal is retried
  ``llm.refusal_retries`` times (at most once) with ``reframed=True``, then recorded as a degradation
  plus ``declined_sections`` and the phase continues with a code fallback; a schema error gets one
  repair call, then propagates; a ``max_tokens`` truncation gets one more call with doubled
  ``max_tokens`` (capped at 128k; with the configured value already at that cap, as in
  ``config/agent.yaml`` since 2026-10-03, the one retry runs at the same cap, because nothing wider
  exists and output length varies from call to call). A second truncation is not retried again and
  never repaired: it is disclosed as an ``other`` degradation "the <phase> answer was truncated
  twice at the output cap" and the phase continues with the same code fallback as a deadline cut
  (Session 4 ruling). A call cut by the run deadline (:class:`LLMDeadlineError`, robustness LLM-05)
  is not retried: it is disclosed as a ``budget_or_deadline_hit`` degradation and the phase
  continues with its code fallback (understand: no intent or registry; plan: one document-only
  question per criterion; refine: the merged findings in severity and confidence order). An assess
  shard (``disclose=False``) discloses its own cut, keeping the findings the stream had finished
  (``PhaseCall.partial``). Other :class:`LLMError`\\ s propagate. A complete answer that broke the
  phase's rules (``check``) gets one repair call; refine keeps the revisions that pass on their own and
  asks that call only for the failing ones (``split``, :class:`KeptItems`), so a repair cut at the
  stage limit costs the failing revisions, never the valid ones (rehearsal of 2026-10-04).
* **Progress (rule 6):** a step line before and after every call and on every retry; the 10 s
  heartbeat during a call comes from the live gateways (``AnthropicGateway`` and
  ``ClaudeCodeGateway`` emit it when built with ``progress``, as ``llm.backend.build_llm_gateway``
  does). The phase adds none of its own: a second heartbeat would advance a ``FakeClock`` in tests.
* **Bookkeeping per call:** call IDs in ``state.llm_calls[phase]`` (including refused and failed
  calls that have an ID), token counters in ``state.budget`` (read by the ``budget_tokens`` stop
  rule; a failed call counts with the usage it was billed for, ``LLMError.usage``), refusals in
  ``state.refusals``, fallbacks in ``state.fallback_events`` plus a ``model_fallback`` degradation
  (INV-07).
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from sit_review_agent.context import RunContext
from sit_review_agent.errors import LLMDeadlineError, LLMRefusalError, LLMSchemaError, LLMTruncatedError
from sit_review_agent.ingest.pdf import Document
from sit_review_agent.ingest.text import flatten_for_match, normalise_quote, quote_tokens
from sit_review_agent.llm.backend import supports_native_pdf
from sit_review_agent.llm.gateway import LLMRequest, LLMResult
from sit_review_agent.llm.outputs import (
    CriterionCoverage,
    DocAnchorDraft,
    EvidenceCitation,
    FindingDraft,
    ReassessmentDraft,
    SoundAreaDraft,
)
from sit_review_agent.llm.prefix import start_conversation
from sit_review_agent.llm.usage_budget import add_usage
from sit_review_agent.models import (
    DegradationType,
    DocAnchor,
    DocumentRole,
    ReassessmentStatus,
    ReviewMode,
    SourceType,
    finding_id,
)
from sit_review_agent.progress import ctx_event
from sit_review_agent.prompts import RenderedPrompt
from sit_review_agent.states import PhaseName

#: Largest ``max_tokens`` a truncation retry asks for (``config.AgentConfig.max_tokens`` bound).
MAX_OUTPUT_TOKENS = 128_000
#: ``taxonomy.yaml anchor_rules.min_quote_tokens``.
MIN_QUOTE_TOKENS = 8
#: Longest excerpt of a ledger entry shown to the model in a brief.
EXCERPT_CHARS = 700
FINDING_ID_RE = re.compile(r"^FND-[0-9]{3,}$")
_URL_RE = re.compile(r"\S+://\S+")
_AnchorT = TypeVar("_AnchorT", DocAnchor, DocAnchorDraft)


class BriefRenderer(Protocol):
    def __call__(self, *, reframed: bool, schema_error: str) -> RenderedPrompt:
        ...


@dataclass(frozen=True)
class PhaseCall:
    """Outcome of :func:`call_model`. ``result`` is ``None`` when the model declined twice."""

    result: LLMResult[Any] | None
    brief: RenderedPrompt
    refusal_category: str | None = None
    cut: bool = False                    # the run deadline cut the call (robustness LLM-05)
    truncated: bool = False              # the answer was cut off at max_tokens twice (LLM-07)
    #: The call IDs of both truncated attempts (the call and its one retry), when ``truncated``.
    truncated_ids: tuple[str | None, ...] = ()
    #: What a cut stream had finished (``LLMDeadlineError.partial``; latency redesign), else ``None``.
    partial: dict[str, Any] | None = None
    #: The call ID of the attempt the deadline cut, when ``cut`` (``None`` if no attempt had started).
    cut_id: str | None = None
    #: Problems ``check`` still found after the one repair call (the answer is not used).
    invalid: tuple[str, ...] = ()
    #: Omissions ``ask`` still found after the one repair call (the answer is used; the caller fills them in).
    omitted: tuple[str, ...] = ()
    #: With ``split``: the complete first answer whose valid items were kept while the one repair call
    #: asked only for the rest. The caller merges ``split.kept`` with what the repair call gave
    #: (``result``, or ``partial`` when it was cut; nothing when it was declined or truncated twice)
    #: and checks the merged set itself; ``check`` and ``ask`` are not run on the repair answer.
    first: LLMResult[Any] | None = None
    split: KeptItems | None = None

    @property
    def declined(self) -> bool:
        return self.result is None and not self.cut and not self.truncated and not self.invalid


@dataclass(frozen=True)
class KeptItems:
    """The valid items of a complete answer that broke rules (``call_model(split=...)``), kept while
    the one repair call asks only for the rest (refine, sit_sample_ui_1 rehearsal of 2026-10-04: one
    revision of 55 failed, the whole answer was asked again, the repair ran into the stage limit and
    51 findings were never refined)."""

    #: The items of the first answer that pass on their own, as the model gave them.
    kept: tuple[Any, ...]
    #: The IDs of the items the repair call must answer for (failed or missing).
    retry: tuple[str, ...]
    #: Added to the correction of the repair brief: what is kept, what to answer again.
    instruction: str


# ------------------------------------------------------------------------------ prompt inputs


def ordered_documents(ctx: RunContext) -> list[Document]:
    """Documents in prefix order: under review, prior version, then companions (by ID)."""
    rank = {DocumentRole.UNDER_REVIEW: 0, DocumentRole.PRIOR_VERSION: 1, DocumentRole.COMPANION: 2}
    return sorted(ctx.documents.values(), key=lambda d: (rank.get(d.role, 3), d.doc_id))


def system_prompt(ctx: RunContext) -> RenderedPrompt:
    persona = ctx.config.persona()
    return ctx.prompts.render("system.md", persona_title=persona.title.strip(),
                              persona_emphasis=" ".join(persona.emphasis.split()))


def criteria_vars(ctx: RunContext) -> list[dict[str, Any]]:
    return [{"id": c.id, "question": c.question, "kinds": [k.value for k in c.kinds],
             "research_hints": list(c.research_hints)} for c in ctx.config.criteria.criteria]


def document_vars(ctx: RunContext) -> list[dict[str, Any]]:
    return [{"doc_id": d.doc_id, "role": d.role.value, "title": d.title} for d in ordered_documents(ctx)]


def registry_vars(ctx: RunContext) -> list[dict[str, Any]]:
    return [{"registry_id": e.registry_id, "type": e.type.value, "doc_ref": e.doc_ref, "statement": e.statement}
            for e in ctx.registry.entries()]


def intent_vars(ctx: RunContext) -> dict[str, Any]:
    i = ctx.state.intent_summary
    if i is None:
        return {"statement": "", "objectives": [], "constraints": [], "key_assumptions": []}

    def items(xs: Iterable[Any]) -> list[dict[str, Any]]:
        return [{"ref": x.ref, "text": x.text} for x in xs]

    return {"statement": i.statement, "objectives": items(i.objectives), "constraints": items(i.constraints),
            "key_assumptions": items(i.key_assumptions)}


def evidence_vars(ctx: RunContext) -> list[dict[str, Any]]:
    """Ledger entries as the model may see them: ID, type, authority, title, excerpt. Never the URL."""
    out = []
    for e in ctx.ledger:
        excerpt = " ".join((e.excerpt or "").split())
        if len(excerpt) > EXCERPT_CHARS:
            excerpt = excerpt[:EXCERPT_CHARS].rstrip() + " [...]"
        out.append({"evidence_id": e.evidence_id, "source_type": e.source_type.value,
                    "authority": e.authority.value if e.authority is not None else "",
                    "title": _URL_RE.sub("[link removed]", e.title or ""),
                    "excerpt": _URL_RE.sub("[link removed]", excerpt),
                    "derived_from": list(e.derived_from)})
    return out


def answer_vars(ctx: RunContext) -> list[dict[str, Any]]:
    plan = ctx.state.plan
    if plan is None:
        return []
    return [{"question_id": q.id, "criterion_id": q.criterion_id, "question": q.question, "status": q.status,
             "summary": q.summary, "evidence_ids": list(q.evidence_ids)} for q in plan.questions]


def prior_finding_vars(ctx: RunContext) -> list[dict[str, Any]]:
    """Findings of the prior review (delta mode with ``previous_run_dir``), else ``[]``."""
    if ctx.state.review_mode is not ReviewMode.DELTA or not ctx.state.previous_run_dir:
        return []
    path = Path(ctx.state.previous_run_dir) / "report.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [{"id": f.get("id", ""), "title": f.get("title", ""), "statement": f.get("statement", ""),
             "disposition": f.get("disposition", "")} for f in data.get("findings", []) if isinstance(f, dict)]


def known_criteria(ctx: RunContext) -> list[str]:
    return ctx.config.criteria.ids()


# ------------------------------------------------------------------------------ the model call


def _short_error(exc: Exception, limit: int = 1500) -> str:
    lines = [ln for ln in str(exc).splitlines() if "://" not in ln]
    text = "\n".join(lines).strip()
    return text[:limit] + (" [...]" if len(text) > limit else "")


def _note_call(ctx: RunContext, phase: PhaseName, call_id: str | None) -> None:
    if call_id:
        ctx.state.llm_calls.setdefault(phase.value, []).append(call_id)


def record_result(ctx: RunContext, phase: PhaseName, result: LLMResult[Any]) -> None:
    """Call ID, token counters, fallback event (with its ``model_fallback`` degradation)."""
    _note_call(ctx, phase, result.call_id)
    add_usage(ctx.state.budget, result.usage)
    if result.fallback is not None:
        ctx.state.fallback_events.append(result.fallback)
        ctx.state.add_degradation(DegradationType.MODEL_FALLBACK,
                                  f"{phase.value} call {result.call_id} was served by {result.fallback.to_model} "
                                  f"instead of {result.fallback.from_model}",
                                  "part of this review was produced by another model; the run is not eval evidence")


#: Impact of every refine fallback (cut, truncated twice, declined, revisions that cannot be applied).
REFINE_FALLBACK_IMPACT = ("the merged assess findings are reported in severity and confidence order, without the "
                          "global refine pass (no duplicates merged, no registry decisions linked, no research "
                          "evidence attached)")


def deadline_cut(ctx: RunContext, phase: PhaseName, exc: Exception) -> None:
    """Disclose a model call the run deadline cut (robustness LLM-05; INV-07)."""
    from sit_review_agent.llm.runtime import OUT_OF_TIME_BEFORE_ASSESSMENT

    if phase is PhaseName.ASSESS:
        event = f"{OUT_OF_TIME_BEFORE_ASSESSMENT}: the assess call was cut by the run deadline ({exc})"
        impact = ("the design was not assessed: the report has no findings and its verdict is not a judgement of "
                  "the design; rerun with a longer deadline")
    elif phase is PhaseName.REFINE:
        event = f"the refine call was cut by the run deadline ({exc})"
        impact = REFINE_FALLBACK_IMPACT
    else:
        event = f"the {phase.value} call was cut by the run deadline ({exc})"
        impact = f"the {phase.value} step was completed by code without model output"
    ctx.state.add_degradation(DegradationType.BUDGET_OR_DEADLINE_HIT, event, impact)
    partial = getattr(exc, "partial", None)
    ctx_event(ctx, f"{phase.value}: model call cut by the run deadline; {impact}", "warn", event="call_cut",
              stage=phase.value, call_id=getattr(exc, "call_id", None), at_s=ctx.elapsed_s(),
              kept_items=getattr(exc, "salvaged_items", 0),
              kept={str(k): len(v) for k, v in partial.items() if isinstance(v, list)} if isinstance(partial, dict)
              else {})


def truncated_twice(ctx: RunContext, phase: PhaseName, max_tokens: int, call_ids: Sequence[str | None]) -> None:
    """Disclose a stage whose answer was cut off at the output cap on its call and on the one retry
    (robustness LLM-07, persistent variant; INV-07). The stage then continues with the same code
    fallback as a deadline cut, so the event names the truncation and never the deadline."""
    from sit_review_agent.llm.runtime import truncated_twice_event

    ids = ", ".join(c for c in call_ids if c) or "no call IDs"
    event = (f"{truncated_twice_event(phase)} (max_tokens={max_tokens}; the call and its one retry, {ids}); "
             "the truncated output was discarded, not repaired")
    if phase is PhaseName.ASSESS:
        impact = ("the design was not assessed: the report has no findings and its verdict is not a judgement of "
                  "the design; rerun the review (answer length varies between calls)")
    elif phase is PhaseName.REFINE:
        impact = REFINE_FALLBACK_IMPACT
    else:
        impact = f"the {phase.value} step was completed by code without model output"
    ctx.state.add_degradation(DegradationType.OTHER, event, impact)
    ctx_event(ctx, f"{phase.value}: answer truncated twice at the output cap (max_tokens={max_tokens}); {impact}",
              "warn", event="truncated_twice", stage=phase.value, max_tokens=max_tokens,
              call_ids=[c for c in call_ids if c])


async def call_model(ctx: RunContext, phase: PhaseName, render: BriefRenderer, schema: type[BaseModel] | None, *,
                     iteration: int = 0, purpose: str | None = None, conversation: str | None = None,
                     disclose: bool = True, check: Callable[[Any], list[str]] | None = None,
                     ask: Callable[[Any], list[str]] | None = None,
                     split: Callable[[Any, list[str]], KeptItems | None] | None = None) -> PhaseCall:
    """One logical model call of ``phase`` with the phase-level retries described in the module
    docstring. Returns the result, or a declined :class:`PhaseCall` after a persistent refusal.

    ``conversation`` replaces the conversation ID ``<phase>-<iteration>`` (an assess shard uses
    ``assess-<n>-s<k>``). With ``disclose=False`` (assess shards) a deadline cut, a second truncation
    or a persistent refusal is returned without the phase-level degradation, ``declined_sections``
    entry or deadline text, because the caller discloses it in its own terms; call IDs, usage and
    refusals are recorded either way. ``check`` (refine) lists what makes a parsed answer unusable;
    a non-empty list is treated like a schema error: one repair call with the list as
    ``schema_error``, then the call returns with ``invalid`` set (never raises). ``ask`` (refine in a
    re-review: prior findings with no status) lists what the answer left out: a non-empty list asks
    once through the same repair call (with ``check``'s problems, if any); what the repair answer still
    leaves out is returned in ``omitted`` with the answer, which is used, and the caller fills the gap
    in code. A call already repaired once (a schema error) is not asked again.

    ``split`` (refine) is given a complete answer that ``check`` or ``ask`` found problems with and the
    problems; when it returns :class:`KeptItems`, those items are kept, the repair call asks only for
    the rest (``KeptItems.instruction`` joins the correction) and the call returns right after the
    repair call with ``first`` (the first answer) and ``split`` set, whatever the repair call's end:
    the repair answer in ``result``, a cut with ``partial``, a persistent refusal or a second
    truncation with neither. The caller merges the kept items with what came back and checks the whole;
    ``check`` and ``ask`` are not run on a repair answer that covers only part of the whole. With
    ``None`` from ``split`` (nothing to keep) the whole answer is asked again, as without ``split``."""
    effort = ctx.config.effort_for(phase)
    system = system_prompt(ctx).text
    docs = ordered_documents(ctx)
    if not docs:
        raise ValueError(f"{phase.value}: no documents in the run context")
    native = supports_native_pdf(ctx.llm)
    max_tokens = ctx.config.agent.max_tokens
    base_conv = conversation or f"{phase.value}-{iteration}"
    label = purpose or phase.value
    reframed, schema_error = False, ""
    refusals_left = ctx.config.agent.llm.refusal_retries
    repaired = widened = False
    k, reason = 0, ""
    truncated_ids: list[str | None] = []
    first: LLMResult[Any] | None = None             # the answer whose valid items ``kept`` holds (``split``)
    kept: KeptItems | None = None
    while True:
        # Yield once before every logical call, so the concurrent members of stage 1 (the K assess
        # shards, launched in order) reach their own first calls before a retry of this one: the
        # stage's logical call index (``nth`` of the fault schedules) numbers the shards' first calls
        # 0..K-1 in launch order whatever the backend's latency (the scripted backend answers without
        # suspending). Costs nothing on a live backend.
        await asyncio.sleep(0)
        brief = render(reframed=reframed, schema_error=schema_error)
        messages, bp = start_conversation(docs, brief.text, native_pdf=native)
        conv = base_conv if k == 0 else f"{base_conv}-r{k}"
        tag = label if k == 0 else f"{label}:{reason}"
        req = LLMRequest(phase=phase, conversation_id=conv, system=system, messages=messages, effort=effort,
                         max_tokens=max_tokens, output_schema=schema, cache_breakpoints=(bp,),
                         thinking_display=ctx.config.agent.thinking_display, iteration=iteration, purpose=tag)
        try:
            result = await ctx.llm.call(req)
            if schema is not None and result.parsed is None and result.stop_reason == "end_turn":
                _note_call(ctx, phase, result.call_id)
                raise LLMSchemaError(f"no structured output ({schema.__name__}) in the answer",
                                     call_id=result.call_id, phase=phase.value)
        except LLMRefusalError as exc:
            _note_call(ctx, phase, exc.call_id)
            add_usage(ctx.state.budget, exc.usage)
            ctx.state.refusals.append({"call_id": exc.call_id, "stage": phase.value, "category": exc.category})
            if refusals_left > 0:
                refusals_left -= 1
                reframed, k, reason = True, k + 1, "refusal_retry"
                ctx_event(ctx, f"model declined ({exc.category or 'no category'}); retrying once with "
                          "professional-review framing", "warn", event="call_retry", reason="refusal_retry",
                          stage=phase.value, call_id=exc.call_id, category=exc.category)
                continue
            if not disclose:
                return PhaseCall(result=None, brief=brief, refusal_category=exc.category, first=first, split=kept)
            ctx.state.add_degradation(
                DegradationType.OTHER,
                f"the model declined the {phase.value} call after a reframed retry (refusal category: "
                f"{exc.category or 'none given'})",
                f"the {phase.value} step was completed without model output; see the report's limitations")
            if phase.value not in ctx.state.declined_sections:
                ctx.state.declined_sections.append(phase.value)
            ctx_event(ctx, f"model declined {phase.value} twice; continuing without it", "warn", event="declined",
                      stage=phase.value, call_id=exc.call_id, category=exc.category)
            return PhaseCall(result=None, brief=brief, refusal_category=exc.category, first=first, split=kept)
        except LLMSchemaError as exc:
            if exc.call_id and exc.call_id not in ctx.state.llm_calls.get(phase.value, []):
                _note_call(ctx, phase, exc.call_id)
            add_usage(ctx.state.budget, exc.usage)
            if repaired:
                raise
            repaired, schema_error, k, reason = True, _short_error(exc), k + 1, "schema_repair"
            ctx_event(ctx, "answer did not match the output schema; one repair call", "warn", event="call_retry",
                      reason="schema_repair", stage=phase.value, call_id=exc.call_id)
            continue
        except LLMDeadlineError as exc:
            _note_call(ctx, phase, exc.call_id)
            add_usage(ctx.state.budget, exc.usage)       # measured usage only; never estimated_usage
            if disclose:
                deadline_cut(ctx, phase, exc)
            return PhaseCall(result=None, brief=brief, cut=True, partial=getattr(exc, "partial", None),
                             cut_id=exc.call_id, first=first, split=kept)
        except LLMTruncatedError as exc:
            _note_call(ctx, phase, exc.call_id)
            add_usage(ctx.state.budget, exc.usage)
            truncated_ids.append(exc.call_id)
            if widened:                     # second truncation: degrade like a deadline cut, no third call
                if disclose:
                    truncated_twice(ctx, phase, max_tokens, truncated_ids)
                return PhaseCall(result=None, brief=brief, truncated=True, truncated_ids=tuple(truncated_ids),
                                 first=first, split=kept)
            wider = min(MAX_OUTPUT_TOKENS, max_tokens * 2)
            how = (f"with max_tokens={wider}" if wider > max_tokens
                   else f"at the same max_tokens={wider} (the output cap; it cannot be raised)")
            widened, max_tokens, k = True, wider, k + 1
            reason = "max_tokens_retry"
            ctx_event(ctx, f"answer truncated at max_tokens; retrying once {how}", "warn", event="call_retry",
                      reason="max_tokens_retry", stage=phase.value, call_id=exc.call_id, max_tokens=wider)
            continue
        record_result(ctx, phase, result)
        if kept is not None:                # the repair call answered for the rest; the caller merges and checks
            return PhaseCall(result=result, brief=brief, first=first, split=kept)
        problems = check(result.parsed) if check is not None and result.parsed is not None else []
        omitted = ask(result.parsed) if ask is not None and result.parsed is not None else []
        if omitted and not problems and repaired:
            ctx_event(ctx, f"{phase.value} answer still leaves out {len(omitted)} item(s) after one repair call; "
                      "the answer is used and code fills them in", "warn", event="answer_incomplete",
                      stage=phase.value, call_id=result.call_id, omitted=len(omitted))
            return PhaseCall(result=result, brief=brief, omitted=tuple(omitted))
        problems = problems + omitted
        if problems:
            if repaired:
                # The problems can quote the answer, so progress.jsonl gets their count only.
                head = f"{phase.value} answer still unusable after one repair call"
                ctx_event(ctx, f"{head}: {'; '.join(problems)[:300]}", "warn", event="answer_unusable",
                          stage=phase.value, call_id=result.call_id, problems=len(problems),
                          public=f"{head} ({len(problems)} problem(s))")
                return PhaseCall(result=None, brief=brief, invalid=tuple(problems))
            # Rule repair. Of the four callers (understand, plan, the assess shards, refine) only refine
            # passes ``check``/``ask``, so only refine reaches this retry; the others come through the
            # schema and transport retries above, where a failed answer has no parsed items to keep.
            # An answer that is a list of independently applicable items keeps its valid items through
            # ``split`` and the repair call asks only for the rest; a single-object answer (understand,
            # plan: one intent, one question list applied as a whole) would be asked again whole. A
            # phase that later adds a ``check`` over a list answer (the assess shards' findings) must
            # also pass ``split``, or a complete answer loses its valid items to one bad one
            # (docs/transcripts/session6/refine-keep-good.md).
            repaired, k, reason = True, k + 1, "schema_repair"
            schema_error = ("The answer had the required structure but broke these rules:\n"
                            + "\n".join(f"- {p}" for p in problems))[:4000]
            kept = split(result.parsed, problems) if split is not None else None
            if kept is not None:
                first = result
                schema_error += "\n\n" + kept.instruction[:4000]
            ctx_event(ctx, f"{phase.value} answer broke {len(problems)} rule(s); one repair call"
                      + (f" for {len(kept.retry)} item(s), {len(kept.kept)} kept" if kept is not None else ""),
                      "warn", event="call_retry", reason="rule_repair", stage=phase.value, call_id=result.call_id,
                      problems=len(problems), **({"kept": len(kept.kept), "retry": len(kept.retry)} if kept else {}))
            continue
        return PhaseCall(result=result, brief=brief)


# ------------------------------------------------------------------------------ anchors


def extend_quote(doc: Document, quote: str, min_tokens: int = MIN_QUOTE_TOKENS) -> str | None:
    """A quote found verbatim in ``doc`` but shorter than ``min_tokens`` is extended with the words
    that follow it (then precede it) in the canonical text, never across a page marker. Returns
    the extended quote (still a verbatim substring), the quote itself if long enough, or ``None``."""
    q = normalise_quote(quote)
    if not q:
        return None
    if quote_tokens(q) >= min_tokens:
        return q
    hay = flatten_for_match(doc.text)
    i = hay.find(q)
    if i < 0:
        return None
    start, end = i, i + len(q)
    while end < len(hay) and hay[end] != " ":
        end += 1
    while start > 0 and hay[start - 1] != " ":
        start -= 1

    def marker(word: str) -> bool:
        return word.startswith("[[PAGE") or word.endswith("]]")

    while len(hay[start:end].split()) < min_tokens:
        j = end
        while j < len(hay) and hay[j] == " ":
            j += 1
        k = j
        while k < len(hay) and hay[k] != " ":
            k += 1
        if j >= len(hay) or marker(hay[j:k]):
            break
        end = k
    while len(hay[start:end].split()) < min_tokens:
        j = start
        while j > 0 and hay[j - 1] == " ":
            j -= 1
        k = j
        while k > 0 and hay[k - 1] != " ":
            k -= 1
        if j <= 0 or marker(hay[k:j]):
            break
        start = k
    out = hay[start:end].strip()
    return out if quote_tokens(out) >= min_tokens else None


def fix_anchor(ctx: RunContext, a: DocAnchorDraft) -> DocAnchorDraft:
    """Cheap code fixes: unknown ``doc_id`` -> the document under review; ``page < 1`` -> ``None``;
    a short quote found verbatim is extended (:func:`extend_quote`). Quotes are never invented."""
    docs = ctx.documents
    doc_id = a.doc_id
    if doc_id not in docs and docs:
        doc_id = ordered_documents(ctx)[0].doc_id
    page = a.page if a.page is None or a.page >= 1 else None
    quote = a.quote
    doc = docs.get(doc_id)
    if doc is not None and quote_tokens(normalise_quote(quote)) < MIN_QUOTE_TOKENS:
        quote = extend_quote(doc, quote) or quote
    return a.model_copy(update={"doc_id": doc_id, "page": page, "quote": quote,
                                "requirement_ids": [r for r in a.requirement_ids if r.strip()]})


def unique_anchors(anchors: Iterable[_AnchorT]) -> list[_AnchorT]:
    """``anchors`` with exact repeats removed (same document, page, section and normalised quote;
    first kept, order kept). A model that cites one passage twice would otherwise make the report
    list that location twice."""
    seen: set[tuple[str, int | None, str, str]] = set()
    out: list[_AnchorT] = []
    for a in anchors:
        key = (a.doc_id, a.page, a.section_ref, normalise_quote(a.quote))
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


def spec_anchor(ctx: RunContext, a: DocAnchorDraft) -> DocAnchor | None:
    """The fixed draft as a canonical :class:`DocAnchor`, or ``None`` if it still breaks the spec."""
    try:
        return DocAnchor.model_validate(fix_anchor(ctx, a).model_dump())
    except ValidationError:
        return None


def fallback_anchor(ctx: RunContext) -> DocAnchor | None:
    """A verbatim anchor on the first page of the document under review that has enough words
    (used only when the model gave no valid intent anchor; disclosed as a degradation)."""
    docs = ordered_documents(ctx)
    if not docs:
        return None
    doc = docs[0]
    pages = doc.pages or []
    for p in pages or [None]:
        text = doc.page_text(p.number) if p is not None else doc.text
        lines = [ln for ln in text.split("\n") if quote_tokens(ln) >= MIN_QUOTE_TOKENS]
        if not lines:
            continue
        quote = " ".join(lines[0].split()[:20])
        section = doc.section_at(p.char_start if p is not None else 0)
        try:
            return DocAnchor(doc_id=doc.doc_id, section_ref=section.section_id if section else "1",
                             requirement_ids=[], quote=quote, page=p.number if p is not None else None)
        except ValidationError:
            continue
    return None


# ------------------------------------------------------------------------------ findings


def _id_number(fid: str) -> int:
    return int(fid.split("-", 1)[1]) if FINDING_ID_RE.match(fid) else 0


def _clamp(x: float) -> float:
    return min(1.0, max(0.0, float(x)))


def normalise_findings(ctx: RunContext, drafts: Sequence[FindingDraft], *, keep_ids: Iterable[str] = (),
                       reserved: Iterable[str] = ()) -> tuple[list[FindingDraft], dict[str, str]]:
    """Code-side fixes the structured output cannot enforce. Returns the drafts and a map from the
    model's ID to the final ID (first occurrence wins).

    * IDs: a draft keeps its ID if it is ``FND-nnn``, unique in this output, and either in
      ``keep_ids`` (existing findings) or not in ``reserved`` (IDs used earlier in the run); every
      other draft gets the next free number. ``assess`` passes no ``keep_ids``.
    * ``rank`` becomes ``1..n`` ordered by the model's rank, then by output order.
    * ``confidence`` clamped to [0, 1]; ``criterion_ids`` filtered to configured criteria (order kept).
    * anchors fixed with :func:`fix_anchor`; exact repeats removed (:func:`unique_anchors`).
    * ``reassessment``: ``None`` in a full review; in a delta review a missing one becomes
      ``new_in_update`` (the spec requires one on every delta finding).
    """
    keep = set(keep_ids)
    used = set(reserved) | keep
    taken: set[str] = set()
    next_n = max([_id_number(i) for i in used] + [0]) + 1
    criteria = set(known_criteria(ctx))
    delta = ctx.state.review_mode is ReviewMode.DELTA
    id_map: dict[str, str] = {}
    out: list[FindingDraft] = []
    for d in drafts:
        fid = d.id.strip()
        ok = bool(FINDING_ID_RE.match(fid)) and fid not in taken and (fid in keep or fid not in used)
        if not ok:
            while finding_id(next_n) in used or finding_id(next_n) in taken:
                next_n += 1
            fid = finding_id(next_n)
            next_n += 1
        taken.add(fid)
        id_map.setdefault(d.id, fid)
        reassessment = d.reassessment if delta else None
        if delta and reassessment is None:
            reassessment = ReassessmentDraft(prior_finding_id=None, status=ReassessmentStatus.NEW_IN_UPDATE,
                                             note="no reassessment returned; set by code")
        out.append(d.model_copy(update={
            "id": fid, "confidence": _clamp(d.confidence),
            "criterion_ids": [c for c in dict.fromkeys(d.criterion_ids) if c in criteria],
            "doc_anchors": unique_anchors(fix_anchor(ctx, a) for a in d.doc_anchors),
            "reassessment": reassessment,
        }))
    order = sorted(range(len(out)), key=lambda i: (drafts[i].rank, i))
    ranks = {i: r + 1 for r, i in enumerate(order)}
    return [f.model_copy(update={"rank": ranks[i]}) for i, f in enumerate(out)], id_map


def normalise_sound_areas(ctx: RunContext, areas: Sequence[SoundAreaDraft], id_map: dict[str, str],
                          finding_ids: set[str]) -> list[SoundAreaDraft]:
    out = []
    for a in areas:
        related = [id_map.get(i, i) for i in a.related_finding_ids]
        out.append(a.model_copy(update={
            "doc_anchors": unique_anchors(fix_anchor(ctx, x) for x in a.doc_anchors),
            "related_finding_ids": [i for i in dict.fromkeys(related) if i in finding_ids]}))
    return out


def reconcile_coverage(ctx: RunContext, rows: Sequence[CriterionCoverage], findings: Sequence[FindingDraft],
                       id_map: dict[str, str] | None = None, *,
                       criteria: Sequence[str] | None = None) -> list[CriterionCoverage]:
    """One coverage row per configured criterion (or per criterion of ``criteria``, an assess
    shard's group), in config order, consistent with the findings' ``criterion_ids``. Rows for
    unknown criteria are dropped; a missing row is added as ``not_applicable`` with a note saying
    the model did not report it (or ``findings`` if a finding cites the criterion)."""
    id_map = id_map or {}
    by_criterion: dict[str, list[str]] = {}
    for f in findings:
        for c in f.criterion_ids:
            by_criterion.setdefault(c, []).append(f.id)
    existing = {f.id for f in findings}
    given: dict[str, CriterionCoverage] = {}
    for r in rows:
        given.setdefault(r.criterion_id, r)
    out = []
    wanted = set(criteria) if criteria is not None else None
    for cid in known_criteria(ctx):
        if wanted is not None and cid not in wanted:
            continue
        cited = by_criterion.get(cid, [])
        row = given.get(cid)
        if row is None:
            out.append(CriterionCoverage(
                criterion_id=cid, outcome="findings" if cited else "not_applicable", finding_ids=cited,
                note="no coverage row returned by the model; derived by code from the findings" if cited
                else "no coverage row returned by the model for this criterion (not reported as checked)"))
            continue
        ids = [i for i in dict.fromkeys([id_map.get(i, i) for i in row.finding_ids] + cited) if i in existing]
        outcome, note = row.outcome, row.note
        if ids and outcome != "findings":
            outcome, note = "findings", (note + " " if note else "") + "(findings cite this criterion)"
        elif not ids and outcome == "findings":
            outcome, note = "no_issue", (note + " " if note else "") + "(no remaining finding cites this criterion)"
        out.append(row.model_copy(update={"outcome": outcome, "finding_ids": ids, "note": note.strip()}))
    return out


def changed_fields(before: BaseModel, after: BaseModel, *, ignore: Iterable[str] = ("id",)) -> dict[str, list[Any]]:
    """``{field: [before, after]}`` for every top-level field that differs (JSON values)."""
    b, a = before.model_dump(mode="json"), after.model_dump(mode="json")
    skip = set(ignore)
    return {k: [b.get(k), a.get(k)] for k in a if k not in skip and b.get(k) != a.get(k)}


def summarise(items: Sequence[Any], key: Callable[[Any], str]) -> str:
    counts: dict[str, int] = {}
    for x in items:
        counts[key(x)] = counts.get(key(x), 0) + 1
    return ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "none"


# ------------------------------------------------------------------------------ evidence


#: Prefix of the temporary IDs the model gives new ``doc``/``inference`` evidence (prompts).
LOCAL_EVIDENCE_PREFIX = "NEW-"


@dataclass
class EvidenceStats:
    doc_added: int = 0
    inference_added: int = 0
    dropped: int = 0              # citations of unknown external IDs, or unresolvable items


class _EvidenceResolver:
    """Turns the model's evidence citations into ledger-backed ones (see :func:`resolve_evidence`)."""

    def __init__(self, ctx: RunContext, shown: Iterable[str] | None = None) -> None:
        self.ctx = ctx
        self.ledger = ctx.ledger
        self.map: dict[str, str] = {}
        self.stats = EvidenceStats()
        self._doc_index: dict[tuple[str, str], str] = {
            (e.url_or_citation, e.excerpt or ""): e.evidence_id for e in self.ledger if e.source_type is SourceType.DOC}
        #: Ledger IDs that existed when the model answered: the only register IDs it can have meant.
        self._shown: set[str] = ({e.evidence_id for e in self.ledger} if shown is None
                                 else set(shown) & {e.evidence_id for e in self.ledger})

    def resolve_id(self, model_id: str) -> str | None:
        """The ledger entry an ID written by the model stands for: the entry created here for one
        of its temporary IDs, or a register ID it was shown; else ``None``. An ``EV-`` ID the model
        invented never resolves to an entry this resolver adds later in the same pass under the
        same name (that would silently cite unrelated evidence, e.g. "external" evidence in a
        document-only run)."""
        if model_id in self.map:
            return self.map[model_id]
        return model_id if model_id in self._shown else None

    def doc_entry(self, quote: str | None, anchor: DocAnchorDraft | None) -> str | None:
        """A ledger ``doc`` entry for ``quote`` (located in the canonical text when found there,
        else the anchor's own quote at ``anchor``); reuses an identical existing entry."""
        q = normalise_quote(quote or "")
        loc: tuple[str, int | None, str] | None = None
        if q:
            for doc in ordered_documents(self.ctx):
                i = flatten_for_match(doc.text).find(q)
                if i >= 0:
                    sec = doc.section_at(i)
                    loc = (doc.doc_id, doc.page_at(i) if doc.pages else None,
                           sec.section_id if sec else (anchor.section_ref if anchor else "1"))
                    break
        if loc is None and anchor is not None:
            loc = (anchor.doc_id, anchor.page, anchor.section_ref.strip() or "1")
            # The cited quote is not in the document: never record it as document text (an external
            # fact labelled "doc" would become doc evidence; robustness BEH-17). Use the anchor's quote,
            # which verify checks.
            q = normalise_quote(anchor.quote)
        if loc is None or not q:
            return None
        doc_id, page, section = loc
        url = f"doc:{doc_id}#p{page}/s{section}" if page is not None else f"doc:{doc_id}#s{section}"
        hit = self._doc_index.get((url, q))
        if hit is not None:
            return hit
        e = self.ledger.add_doc(doc_id=doc_id, page=page, section_ref=section, excerpt=q)
        self._doc_index[(url, q)] = e.evidence_id
        self.stats.doc_added += 1
        return e.evidence_id

    def resolve(self, findings: Sequence[FindingDraft]) -> None:
        """Register every new doc citation, then every new inference (dependencies first)."""
        for f in findings:
            anchor = f.doc_anchors[0] if f.doc_anchors else None
            for c in f.evidence:
                if c.source_type is SourceType.DOC and self.resolve_id(c.evidence_id) is None:
                    eid = self.doc_entry(c.quote, anchor)
                    if eid is not None:
                        self.map[c.evidence_id] = eid
        pending = [(f, c) for f in findings for c in f.evidence
                   if c.source_type is SourceType.INFERENCE and self.resolve_id(c.evidence_id) is None]
        local = {c.evidence_id for _, c in pending}
        while pending:
            progress = False
            for item in list(pending):
                f, c = item
                if c.evidence_id in self.map:
                    pending.remove(item)
                    progress = True
                    continue
                if any(d in local and self.resolve_id(d) is None for d in c.derived_from):
                    continue                                      # wait for a local dependency
                self._add_inference(f, c, c.derived_from)
                pending.remove(item)
                progress = True
            if not progress:                                      # a cycle: resolve with known deps only
                f, c = pending.pop(0)
                self._add_inference(f, c, c.derived_from)

    def _add_inference(self, f: FindingDraft, c: Any, deps: Sequence[str]) -> None:
        known = [d for d in dict.fromkeys(self.resolve_id(x) for x in deps) if d is not None]
        if not known:
            anchor = f.doc_anchors[0] if f.doc_anchors else None
            base = self.doc_entry(anchor.quote if anchor else None, anchor)
            known = [base] if base is not None else []
        statement = " ".join((c.quote or "").split()) or " ".join(f.title.split())
        if not known or not statement:
            self.stats.dropped += 1
            return
        self.map[c.evidence_id] = self.ledger.add_inference(statement=statement, derived_from=known).evidence_id
        self.stats.inference_added += 1

    def rewrite(self, f: FindingDraft) -> FindingDraft:
        cites: list[EvidenceCitation] = []
        seen: set[str] = set()
        for c in f.evidence:
            eid = self.resolve_id(c.evidence_id)
            if eid is None:
                self.stats.dropped += 1
                continue
            if eid in seen:
                continue
            seen.add(eid)
            e = self.ledger.get(eid)
            quote = c.quote
            if e.source_type in (SourceType.DOC, SourceType.EXTERNAL) and not (quote or "").strip():
                quote = e.excerpt or quote
            cites.append(c.model_copy(update={
                "evidence_id": eid, "source_type": e.source_type, "quote": quote,
                "derived_from": list(e.derived_from) if e.source_type is SourceType.INFERENCE else []}))
        rec = f.recommendation
        if rec is not None:
            supporting = {c.evidence_id for c in cites if c.supports_claim}
            sup = [i for i in dict.fromkeys(self.resolve_id(x) for x in rec.supporting_evidence_ids)
                   if i is not None and i in supporting]
            if not sup:
                sup = [c.evidence_id for c in cites if c.supports_claim]
            if not sup and f.doc_anchors:
                eid = self.doc_entry(f.doc_anchors[0].quote, f.doc_anchors[0])
                if eid is not None:
                    e = self.ledger.get(eid)
                    cites.append(EvidenceCitation(evidence_id=eid, source_type=SourceType.DOC, quote=e.excerpt,
                                                  supports_claim=True, derived_from=[]))
                    sup = [eid]
            rec = rec.model_copy(update={"supporting_evidence_ids": sup})
        return f.model_copy(update={"evidence": cites, "recommendation": rec})


def resolve_evidence(ctx: RunContext, findings: Sequence[FindingDraft],
                     sound_areas: Sequence[SoundAreaDraft] = (), *,
                     shown: Iterable[str] | None = None) -> tuple[list[FindingDraft], list[SoundAreaDraft],
                                                                  EvidenceStats]:
    """Make every evidence citation ledger-backed, so ``verify`` can hydrate it.

    The model cites register IDs, and gives *new* ``doc`` and ``inference`` items temporary IDs
    (``NEW-1``, ...; any ID the model was not shown is treated the same way, and an unknown ID of
    another source type is dropped, even if this pass later creates an entry with that name;
    :meth:`_EvidenceResolver.resolve_id`). This function adds them to
    the ledger through ``ctx.ledger.add_doc`` / ``add_inference`` (doc items located in the canonical
    text where the quote is found, else at the finding's first anchor; inferences after their
    dependencies, falling back to a doc entry for the finding's first anchor), rewrites the IDs in
    ``evidence``, ``derived_from``, ``recommendation.supporting_evidence_ids`` and sound areas'
    ``evidence_ids``, aligns each citation's ``source_type`` with its ledger entry, fills a missing
    quote from the ledger excerpt, and drops citations of unknown external IDs (INV-05). A
    recommendation left with no supporting evidence cites a doc entry for its first anchor.

    ``shown`` is the set of register IDs the model was shown (default: the whole ledger now). An assess
    shard is shown none (it runs beside research), so every ``EV-`` ID it writes is treated as
    invented, even when research has since added an entry of that name."""
    r = _EvidenceResolver(ctx, shown)
    r.resolve(findings)
    out = [r.rewrite(f) for f in findings]
    areas = [a.model_copy(update={"evidence_ids": [i for i in dict.fromkeys(r.resolve_id(x) for x in a.evidence_ids)
                                                   if i is not None]}) for a in sound_areas]
    return out, areas, r.stats
