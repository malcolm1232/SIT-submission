"""Run-level limits every model call honours, whatever the backend (robustness LLM-05, NET-02, LLM-10).

The orchestrator builds one :class:`RuntimeLimits` per run and hands it to every layer of the LLM
gateway stack with :func:`attach_runtime` (``AnthropicGateway``, ``ClaudeCodeGateway``,
``FakeGateway`` and ``FaultInjectingLLMGateway`` each have a ``runtime`` attribute; test doubles
without one are left alone).

* :class:`RunDeadline` (LLM-05). The remaining time comes from the run clock only
  (``RunContext.elapsed_s``, which resume restores from the checkpoint). Each model attempt's
  timeout is ``min(llm.timeout_s, remaining - reserve)``; the reserve is
  ``stop_rules.report_reserve_seconds`` (verify + report, the same reserve the between-phase
  ``deadline`` rule keeps) and, for ``research`` only, also ``stop_rules.refine_reserve_seconds``,
  so research absorbs the squeeze and refine keeps its time. ``verify`` and ``report`` are the
  reserve and may use what is left up to the deadline. A run whose ``stop_rules.active`` has no
  ``deadline`` rule keeps the full ``llm.timeout_s``. An attempt bounded by the deadline that times
  out raises :class:`~sit_review_agent.errors.LLMDeadlineError` and is never retried; a retry (or a
  first attempt) that would start with less than :data:`MIN_ATTEMPT_S` left is not made.
* :class:`ContextGuard` (LLM-10). Before a request is sent, its input size is estimated from
  characters (system prompt, tool definitions, output schema, every message; a native PDF block
  adds :data:`PDF_PAGE_TOKENS` per page) at a conservative :data:`CHARS_PER_TOKEN`; a request over
  :data:`CONTEXT_MARGIN` of the model's context window raises
  :class:`~sit_review_agent.errors.LLMContextTooLongError` naming the document size, and is never sent.
* :class:`FirstCallNetwork` (NET-02). Connection-type errors on the first model call of a run get a
  short retry window (``llm.first_call_network_window_s``, 10 s), then the run ends with a clear "no
  network" message (exit 3). Stage 1 starts its calls together, so every call started before the
  API has answered one is a first call; calls after an answer keep the full retry policy. Each
  gateway instance counts its own first calls, so a resumed run is covered too.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sit_review_agent.errors import LLMConnectionError, LLMContextTooLongError, LLMDeadlineError, LLMError
from sit_review_agent.states import PhaseName

#: Conservative characters per token for the pre-send estimate. English prose runs at about 4
#: characters per token on older Claude tokenizers; the tokenizer of Opus 4.7 and later (all of
#: ``config.SUPPORTED_MODELS``) produces about 1.0-1.35x as many tokens for the same text (claude-api
#: skill), so 3.0 over-estimates rather than under-estimates.
CHARS_PER_TOKEN = 3.0
#: Share of the context window a request may fill (scenarios.md LLM-10: "limit x 0.8").
CONTEXT_MARGIN = 0.8
#: Context windows (input tokens) of the supported models (claude-api skill model table, cached
#: 2026-09-25: 1M for every one). ``llm.context_window_tokens`` overrides; anything else gets 1M.
CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-5-5": 1_000_000, "claude-opus-5": 1_000_000, "claude-opus-4-8": 1_000_000,
    "claude-opus-4-7": 1_000_000, "claude-sonnet-5-5": 1_000_000, "claude-sonnet-5": 1_000_000,
}
DEFAULT_CONTEXT_WINDOW = 1_000_000
#: An attempt (or a retry) is not started with less time than this before its phase's limit.
MIN_ATTEMPT_S = 10.0
#: Phases that are the reserve themselves: they may run up to the deadline.
RESERVE_PHASES = frozenset({PhaseName.VERIFY, PhaseName.REPORT})
#: Degradation text when the deadline leaves no assessment (the report says so; no finding is made up).
OUT_OF_TIME_BEFORE_ASSESSMENT = "out of time before assessment"
#: Degradation text when a stage's answer was cut off at ``max_tokens`` on its call and on the one
#: retry (robustness LLM-07, persistent variant). The stage then degrades like a deadline cut.
TRUNCATED_TWICE = "truncated twice at the output cap"
#: Start of the stage-level degradation event when the model declined every assess shard (the
#: sharded form of ``declined_sections`` "assess"; ``report.render`` infers the not-assessed reason
#: from the report's events, so it must recognise this text).
DECLINED_EVERY_ASSESS_SHARD = "the model declined every assess shard"


def truncated_twice_event(phase: PhaseName | str) -> str:
    """Start of the degradation event of a stage whose answer was truncated twice (and the text
    ``phases.report.assessment_missing`` and ``report.render`` look for)."""
    return f"the {getattr(phase, 'value', phase)} answer was {TRUNCATED_TWICE}"


# ------------------------------------------------------------------------------ deadline


#: The ``stop_rules.stage_limits_s`` key that bounds each phase's model calls (design section 4):
#: stage 1 is understand, plan, research and the assess shards; the verify repair call and the
#: verdict call share the last limit. Ingest makes no model call.
STAGE_LIMIT_OF_PHASE: dict[PhaseName, str] = {
    PhaseName.UNDERSTAND: "stage_1_end", PhaseName.PLAN: "stage_1_end", PhaseName.RESEARCH: "stage_1_end",
    PhaseName.ASSESS: "stage_1_end", PhaseName.REFINE: "refine_end", PhaseName.VERIFY: "verdict_end",
    PhaseName.REPORT: "verdict_end",
}
#: How a stage limit is named in progress lines and errors.
STAGE_LIMIT_LABELS = {"stage_1_end": "stage 1 limit", "refine_end": "refine limit", "verdict_end": "verdict limit"}


def _phase(phase: PhaseName | str) -> PhaseName:
    return phase if isinstance(phase, PhaseName) else PhaseName(phase)


@dataclass
class RunDeadline:
    """The run deadline as seen by model calls. ``elapsed`` is the run clock (seconds since the
    run started, resume-adjusted); ``deadline_s`` ``None`` means the run has no deadline.

    ``stage_limits`` (latency redesign W1): the run-clock second by which each stage must end
    (``stop_rules.stage_limits_s``, scaled by :func:`effective_stage_limits` when ``--deadline`` differs
    from their run length). When set, a call's budget is the lesser of the time left to the deadline and the
    time left to its stage's limit (:data:`STAGE_LIMIT_OF_PHASE`), and the reserves are not applied
    again (the limits already hold them: ``stage_1_end`` = deadline - both reserves on the shipped
    profiles). ``None`` keeps the reserve rule of 2026-10-02 (tests and callers without limits)."""

    deadline_s: float | None
    reserve_s: float
    research_reserve_s: float
    elapsed: Callable[[], float]
    min_attempt_s: float = MIN_ATTEMPT_S
    stage_limits: dict[str, float] | None = None
    #: Phases whose calls no stage limit bounds: the run deadline less the verify and report reserve
    #: (condition B0: its single assess call, ``orchestrator._run_attach_runtime``).
    deadline_bound: frozenset[PhaseName] = frozenset()

    def remaining(self) -> float | None:
        if self.deadline_s is None:
            return None
        return self.deadline_s - self.elapsed()

    def _limit(self, phase: PhaseName | str) -> tuple[str, float] | None:
        """``(key, run-clock second)`` of the stage limit that bounds ``phase``, if any."""
        if self.stage_limits is None or _phase(phase) in self.deadline_bound:
            return None
        key = STAGE_LIMIT_OF_PHASE.get(_phase(phase))
        if key is None or key not in self.stage_limits:
            return None
        return key, float(self.stage_limits[key])

    def phase_budget(self, phase: PhaseName | str) -> float | None:
        """Seconds a model attempt of ``phase`` may still take, or ``None`` without a deadline."""
        rem = self.remaining()
        if rem is None:
            return None
        p = _phase(phase)
        if p in self.deadline_bound:
            return rem - self.reserve_s
        if self.stage_limits is not None:
            limit = self._limit(p)
            return rem if limit is None else min(rem, limit[1] - self.elapsed())
        if p in RESERVE_PHASES:
            return rem
        reserve = self.reserve_s + (self.research_reserve_s if p is PhaseName.RESEARCH else 0.0)
        return rem - reserve

    def describe_bound(self, phase: PhaseName | str) -> str:
        """What bounds ``phase``'s calls now, for progress lines and errors: ``"by the stage 1 limit
        (265 s on the run clock; deadline 540 s)"`` or ``"by the run deadline (540 s ...)"``."""
        limit = self._limit(phase)
        if limit is not None and self.deadline_s is not None and limit[1] < self.deadline_s:
            return (f"by the {STAGE_LIMIT_LABELS[limit[0]]} ({limit[1]:.0f} s on the run clock; deadline "
                    f"{self.deadline_s:.0f} s)")
        return f"by the run deadline ({self.deadline_s:.0f} s on the run clock)"

    def attempt_timeout(self, phase: PhaseName | str, configured_s: float) -> tuple[float, bool]:
        """``(timeout, cut)``: the attempt's timeout and whether the deadline (not ``llm.timeout_s``)
        sets it. Raises :class:`LLMDeadlineError` when less than ``min_attempt_s`` is left."""
        budget = self.phase_budget(phase)
        if budget is None or budget >= configured_s:
            return configured_s, False
        if budget < self.min_attempt_s:
            raise self.no_time(phase, budget)
        return budget, True

    def can_retry(self, phase: PhaseName | str, delay_s: float) -> bool:
        """Whether a retry after ``delay_s`` still starts with ``min_attempt_s`` before the limit."""
        budget = self.phase_budget(phase)
        return budget is None or budget - delay_s >= self.min_attempt_s

    def no_time(self, phase: PhaseName | str, budget: float | None = None, *, after: str | None = None,
                call_id: str | None = None) -> LLMDeadlineError:
        p = _phase(phase).value
        b = self.phase_budget(phase) if budget is None else budget
        why = f" after {after}" if after else ""
        limit = self._limit(phase)
        if limit is not None:
            where = (f"the {STAGE_LIMIT_LABELS[limit[0]]} ({limit[1]:.0f} s on the run clock; deadline "
                     f"{self.deadline_s:.0f} s)")
        else:
            where = (f"this stage's limit (deadline {self.deadline_s:.0f} s, reserve for verify and report "
                     f"{self.reserve_s:.0f} s)")
        return LLMDeadlineError(f"no time left for a {p} model call{why}: {max(0.0, b or 0.0):.0f} s before "
                                f"{where}", call_id=call_id, phase=p)

    def cut(self, phase: PhaseName | str, timeout_s: float, *, call_id: str | None = None,
            partial: dict[str, Any] | None = None, partial_complete: bool = False,
            estimated_usage: Any = None) -> LLMDeadlineError:
        """The error of an attempt cut at ``timeout_s`` by the deadline or its stage limit, with what
        the gateway salvaged from the stream (``partial``) and its usage estimate."""
        p = _phase(phase).value
        limit = self._limit(phase)
        if limit is not None and self.deadline_s is not None and limit[1] < self.deadline_s:
            by = (f"the {STAGE_LIMIT_LABELS[limit[0]]} ({limit[1]:.0f} s on the run clock; deadline "
                  f"{self.deadline_s:.0f} s")
        else:
            by = f"the run deadline ({self.deadline_s:.0f} s"
        return LLMDeadlineError(f"the {p} model call was cut after {timeout_s:.0f} s by {by}; not retried past it)",
                                call_id=call_id, phase=p, partial=partial, partial_complete=partial_complete,
                                estimated_usage=estimated_usage)


# ------------------------------------------------------------------------------ context size


def _payload_chars(v: Any) -> int:
    """Characters the model reads as text in ``v``. Base64 payloads (native PDF blocks) are not
    text and count as 0 here; :meth:`ContextGuard.estimate` adds a per-page allowance for them.
    Dict keys, block types and IDs are ignored."""
    if isinstance(v, str):
        return len(v)
    if isinstance(v, dict):
        if v.get("type") == "base64":
            return 0
        return sum(_payload_chars(x) for k, x in v.items() if k not in ("type", "cache_control", "role", "id",
                                                                          "tool_use_id", "media_type", "signature"))
    if isinstance(v, list | tuple):
        return sum(_payload_chars(x) for x in v)
    return 0


def _pdf_blocks(v: Any) -> int:
    if isinstance(v, dict):
        if v.get("type") == "document" and isinstance(v.get("source"), dict) \
                and v["source"].get("type") == "base64":
            return 1
        return sum(_pdf_blocks(x) for x in v.values())
    if isinstance(v, list | tuple):
        return sum(_pdf_blocks(x) for x in v)
    return 0


#: Tokens allowed per page for a native PDF block's page image (the page text is counted from the
#: canonical text block that always travels with it, ADR-006). UNVERIFIED until ``count_tokens``
#: is run on the laptop (audit U3); only the ``anthropic_api`` backend sends PDF blocks.
PDF_PAGE_TOKENS = 2_000


@dataclass(frozen=True)
class ContextEstimate:
    total_chars: int
    document_chars: int
    estimated_tokens: int
    limit_tokens: int
    window_tokens: int

    @property
    def over(self) -> bool:
        return self.estimated_tokens > self.limit_tokens


@dataclass
class ContextGuard:
    """Pre-send size check (robustness LLM-10). ``pages`` returns the page count of the run's
    documents once ingest has run (the orchestrator passes it), for the native-PDF allowance and so
    the error can name the document's size in pages."""

    window_tokens: int
    margin: float = CONTEXT_MARGIN
    chars_per_token: float = CHARS_PER_TOKEN
    pages: Callable[[], int] | None = None

    @property
    def limit_tokens(self) -> int:
        return int(self.window_tokens * self.margin)

    def _pages(self) -> int:
        try:
            return int(self.pages()) if self.pages is not None else 0
        except Exception:  # noqa: BLE001 - a size hint must never fail a call
            return 0

    def estimate(self, request: Any, *, native_pdf: bool = True) -> ContextEstimate:
        """``request`` is an :class:`~sit_review_agent.llm.gateway.LLMRequest`. The first user
        message holds the documents (``llm.prefix``), so its text size is the document size.
        ``native_pdf`` false: the backend drops PDF blocks (``ClaudeCodeGateway``), so they cost nothing."""
        doc = _payload_chars(request.messages[0].get("content")) if request.messages else 0
        total = _payload_chars(request.system) + _payload_chars(request.messages)
        if request.tools:
            total += len(json.dumps(request.tools, ensure_ascii=False))
        if request.output_schema is not None:
            total += len(json.dumps(request.output_schema.model_json_schema(), ensure_ascii=False))
        est = int(total / self.chars_per_token) + 1
        if native_pdf and _pdf_blocks(request.messages):
            est += self._pages() * PDF_PAGE_TOKENS
        return ContextEstimate(total, doc, est, self.limit_tokens, self.window_tokens)

    def check(self, request: Any, *, model: str = "", native_pdf: bool = True) -> ContextEstimate:
        e = self.estimate(request, native_pdf=native_pdf)
        if not e.over:
            return e
        pages = self._pages()
        size = f"{e.document_chars:,} characters" + (f" over {pages} pages" if pages else "")
        phase = request.phase.value
        raise LLMContextTooLongError(
            f"the {phase} request was not sent: about {e.estimated_tokens:,} input tokens (estimated at "
            f"{self.chars_per_token:g} characters per token) exceed {self.margin:.0%} of the "
            f"{e.window_tokens:,}-token context window of {model or 'the model'} ({e.limit_tokens:,} tokens). "
            f"The document under review is {size} (about {int(e.document_chars / self.chars_per_token):,} "
            "tokens); split it into parts and review them separately", estimated_tokens=e.estimated_tokens,
            limit_tokens=e.limit_tokens, phase=phase)


def context_window_for(model: str, configured: int | None = None, retrieved: Any = None) -> int:
    """``llm.context_window_tokens`` if set, else ``models.retrieve``'s ``max_input_tokens`` when the
    backend returned one, else the known window of ``model``."""
    if configured:
        return int(configured)
    if isinstance(retrieved, int) and not isinstance(retrieved, bool) and retrieved > 0:
        return retrieved
    return CONTEXT_WINDOWS.get(model, DEFAULT_CONTEXT_WINDOW)


# ------------------------------------------------------------------------------ first call / network


NO_NETWORK_HINT = ("no network: the model API could not be reached on the first model call of this run. Check the "
                   "connection (switch to the phone hotspot), then `sit-review resume <run_dir>`; a known document "
                   "can be shown from a recorded run with `--replay` (docs/DEMO_DAY_RUNBOOK.md §6)")


@dataclass
class FirstCallNetwork:
    """NET-02 policy for one gateway instance.

    Stage 1 starts understand, plan and the K assess shards together (latency redesign), so the
    run's "first model call" is every call started before the API has answered any of them: each
    of those gets the window on a connection error, and the first to give up ends the run (the
    orchestrator cancels the other stage 1 members: the run exits once). An answer is a result or
    an HTTP error status (the API was reached); a connection error, a timeout or a cut is not. A
    call started after an answer keeps the full retry policy."""

    window_s: float = 10.0
    calls_started: int = 0
    answered: bool = False     # some attempt of some call got an answer from the API

    def start_call(self) -> bool:
        """Count a logical call; ``True`` while no call of this gateway (this run) has been answered."""
        self.calls_started += 1
        return not self.answered

    def answer(self) -> None:
        """An attempt reached the API: later calls are not first calls."""
        self.answered = True

    def give_up(self, err: LLMError, elapsed_s: float, delay_s: float) -> bool:
        """On a first call, a connection error stops retrying once the next attempt would start
        after the window; not once the API has answered another call (the network is there)."""
        return not self.answered and isinstance(err, LLMConnectionError) and elapsed_s + delay_s > self.window_s

    def error(self, err: LLMError, attempts: int) -> LLMConnectionError:
        return LLMConnectionError(f"{NO_NETWORK_HINT} ({attempts} attempt(s) within "
                                  f"{self.window_s:g} s; last error: {str(err)[:200]})",
                                  call_id=err.call_id, phase=err.phase)


# ------------------------------------------------------------------------------ the bundle


@dataclass
class RuntimeLimits:
    deadline: RunDeadline | None = None
    context: ContextGuard | None = None


def attach_runtime(gw: Any, limits: RuntimeLimits) -> None:
    """Give ``limits`` to ``gw`` and every ``.inner`` layer that has a ``runtime`` attribute, and the
    run clock to each layer's call log (``llm.gateway.LLMCallLog.run_elapsed``, for ``start_offset_s``)."""
    seen: set[int] = set()
    layer = gw
    while layer is not None and id(layer) not in seen:
        seen.add(id(layer))
        if hasattr(layer, "runtime"):
            layer.runtime = limits
        log = getattr(layer, "log", None)
        if limits.deadline is not None and hasattr(log, "run_elapsed"):
            log.run_elapsed = limits.deadline.elapsed  # type: ignore[union-attr]
        layer = getattr(layer, "inner", None)


def build_runtime(config: Any, elapsed: Callable[[], float], *, retrieved_window: Any = None,
                  pages: Callable[[], int] | None = None,
                  deadline_bound: frozenset[PhaseName] = frozenset()) -> RuntimeLimits:
    """Limits for a run with ``config`` (an ``EffectiveConfig``) and the run clock ``elapsed``;
    ``deadline_bound`` names the phases no stage limit bounds (:attr:`RunDeadline.deadline_bound`)."""
    sr = config.stop_rules.effective()
    active = "deadline" in sr.active
    limits = effective_stage_limits(sr)[0] if active else None
    deadline = RunDeadline(deadline_s=float(sr.deadline_seconds) if active else None,
                           reserve_s=float(sr.report_reserve_seconds),
                           research_reserve_s=float(sr.refine_reserve_seconds), elapsed=elapsed,
                           stage_limits=limits, deadline_bound=deadline_bound)
    window = context_window_for(config.agent.model, config.agent.llm.context_window_tokens, retrieved_window)
    return RuntimeLimits(deadline=deadline, context=ContextGuard(window_tokens=window, pages=pages))


def effective_stage_limits(stop_rules: Any) -> tuple[dict[str, float], str | None]:
    """The stage limits a run uses, and the announcement when they differ from the profile's: a view of
    ``StopRulesConfig.effective`` (``config.py``), the one place a non-profile deadline scales the three stage
    limits and the two reserves. ``load_config`` already returns effective rules; rules built by hand (a test, the
    Review form's ``GET /limits``) are made effective here the same way."""
    eff = stop_rules.effective()
    return {k: float(v) for k, v in eff.stage_limits_s.as_dict().items()}, eff.scaling_note()


def deadline_warnings(stop_rules: Any, *, min_attempt_s: float = MIN_ATTEMPT_S) -> list[str]:
    """What the run's deadline will do, said in WARN lines before the first model call (``stop_rules``: the
    run's rules, made effective here). First the scaling note when the deadline is not the profile's own
    (``StopRulesConfig.scaling_note``: limits and reserves, USER_DECISIONS #48); then every stage whose window
    is too short to start one model attempt, since the runtime refuses an attempt with less than
    ``min_attempt_s`` (``MIN_ATTEMPT_S``, 10 s) before its limit and the stage would otherwise be skipped or
    cut in silence. Research needs two attempts' time from the run start, because the plan call runs before it.
    The windows: before verify (the deadline less the verify and verdict reserve), stage 1 (0 to
    ``stage_1_end``), research (to ``research_end_s``), refine (``stage_1_end`` to ``refine_end``) and the
    verdict call (``refine_end`` to ``verdict_end``)."""
    if "deadline" not in stop_rules.active:
        return []
    eff = stop_rules.effective()
    out: list[str] = []
    note = eff.scaling_note()
    if note is not None:
        out.append(note)
    d, r, a = eff.deadline_seconds, eff.report_reserve_seconds, eff.refine_reserve_seconds
    lim = eff.stage_limits_s
    fix = "raise --deadline"
    before_verify = d - r
    if before_verify < min_attempt_s:
        return [*out, f"deadline {d} s does not exceed the verify + report reserve ({r} s) by one model attempt: "
                      f"no model call can run before verify, so the report will say the design was not assessed; "
                      f"{fix}"]
    research_end = eff.research_end_s()
    if research_end - min_attempt_s < min_attempt_s:
        out.append(f"deadline {d} s leaves research no time: its deadline rule ends it at {research_end} s on the run "
                   f"clock ({r} s kept for verify + report and {a} s for refine), less than one plan attempt and "
                   f"one research attempt of {min_attempt_s:g} s each, so the review will be document-only; {fix}")
    windows = (("stage 1 (understand, plan and the assess shards)", lim.stage_1_end, "the design will not be "
                "assessed"),
               ("refine", lim.refine_end - lim.stage_1_end, "the merged findings will stand unrefined"),
               ("the verdict call", lim.verdict_end - lim.refine_end, "the rule-based verdict will be used"))
    for name, span, then in windows:
        if span < min_attempt_s:
            out.append(f"deadline {d} s leaves {name} {span} s, less than one model attempt ({min_attempt_s:g} s): "
                       f"{then}; {fix}")
    return out


def announce_bound(progress: Any, runtime: RuntimeLimits | None, phase: PhaseName | str, call_id: str,
                   timeout_s: float) -> None:
    """One progress line when an attempt's timeout is set by the deadline or a stage limit (not by
    ``llm.timeout_s``): ``llm-0003 bounded at 165 s by the stage 1 limit (265 s on the run clock; ...)``."""
    if progress is None or runtime is None or runtime.deadline is None:
        return
    from sit_review_agent.progress import emit_event

    d = runtime.deadline
    limit = d._limit(phase)
    emit_event(progress, _phase(phase).value, f"{call_id} bounded at {timeout_s:.0f} s {d.describe_bound(phase)}",
               "step", event="call_bounded", call_id=call_id, timeout_s=timeout_s,
               bound=limit[0] if limit is not None and d.deadline_s is not None and limit[1] < d.deadline_s
               else "deadline", limit_s=limit[1] if limit is not None else None, deadline_s=d.deadline_s)


def attempt_timeout(runtime: RuntimeLimits | None, phase: PhaseName | str, configured_s: float) -> tuple[float, bool]:
    if runtime is None or runtime.deadline is None:
        return configured_s, False
    return runtime.deadline.attempt_timeout(phase, configured_s)


def retry_allowed(runtime: RuntimeLimits | None, phase: PhaseName | str, delay_s: float) -> bool:
    if runtime is None or runtime.deadline is None:
        return True
    return runtime.deadline.can_retry(phase, delay_s)


def check_context(runtime: RuntimeLimits | None, request: Any, *, model: str = "", native_pdf: bool = True) -> None:
    if runtime is not None and runtime.context is not None:
        runtime.context.check(request, model=model, native_pdf=native_pdf)
