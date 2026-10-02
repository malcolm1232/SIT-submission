"""The single choke point for every model call (ADR-001, robustness §10 item 1).

* :class:`LLMGateway` is the protocol every phase uses; phases never touch the SDK.
* :class:`AnthropicGateway` is the live implementation (``anthropic`` 1.x ``AsyncAnthropic``,
  ``max_retries=0`` so the gateway owns retries, streaming for every call, ``thinking: adaptive``,
  ``output_config.effort``, structured outputs via ``output_format=<Pydantic type>``).
* :class:`FakeGateway` replays scripted responses keyed by phase (L0 tests, ``selftest``).
* :class:`FaultInjectingLLMGateway` wraps any gateway with a robustness fault schedule.

Contract every implementation honours:

1. Branch on ``stop_reason`` before reading content. ``refusal`` -> :class:`LLMRefusalError`
   (partial output discarded); ``max_tokens`` -> :class:`LLMTruncatedError` (never repaired).
2. Retries: 429 honours ``retry-after``; 529/503/connection/timeout back off with jitter; after
   ``llm.max_retries`` the typed error is raised (the orchestrator checkpoints, exit code 3).
3. No model switch, ever, unless ``allow_fallback`` is set; then ``fallbacks: "default"`` with
   beta ``server-side-fallback-2026-07-01`` is sent and every fallback is returned in
   ``LLMResult.fallback`` and recorded in the manifest (REPRODUCIBILITY §3).
4. One effort level per ``conversation_id`` (ADR-002); a change raises :class:`EffortChangedError`.
5. Every call (and every failed attempt) is appended to ``llm.jsonl`` via :class:`LLMCallLog`,
   with the request body minus PDF bytes (referenced by hash) and the response content blocks
   exactly as returned, so assistant turns can be replayed byte for byte (ADR-009 item 3).
6. Never sent: ``temperature``/``top_p``/``top_k``, ``budget_tokens``, forced ``tool_choice``,
   assistant prefill (all 400 on Opus 5.5).
"""

from __future__ import annotations

import copy
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ValidationError

from sit_review_agent.clock import Clock, SystemClock, isoformat_z
from sit_review_agent.config import EffectiveConfig, EffortLevel
from sit_review_agent.errors import (
    EffortChangedError,
    FakeScriptExhausted,
    LLMError,
    LLMRefusalError,
    LLMSchemaError,
    LLMTruncatedError,
)
from sit_review_agent.hashing import sha256_json, sha256_text
from sit_review_agent.models import FallbackEvent
from sit_review_agent.progress import ProgressSink
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.states import PhaseName

T = TypeVar("T", bound=BaseModel)

#: API limit on ``cache_control`` breakpoints per request (claude-api skill).
MAX_CACHE_BREAKPOINTS = 4
#: Beta header for the demo-only server-side fallback (REPRODUCIBILITY §3).
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class CacheBreakpoint:
    """Put ``cache_control`` on ``messages[message_index].content[block_index]``.

    ADR-002 plan: one explicit breakpoint after the canonical text block of the first user
    message, plus top-level automatic caching for the growing tail (``auto_cache_tail``).
    """

    message_index: int
    block_index: int
    ttl: Literal["5m", "1h"] = "5m"


@dataclass(frozen=True)
class LLMRequest:
    """One logical model call. ``messages`` is the full, append-only conversation history in SDK
    ``MessageParam`` dict form (the first user message carries the document blocks)."""

    phase: PhaseName
    conversation_id: str
    system: str
    messages: list[dict[str, Any]]
    effort: EffortLevel
    max_tokens: int
    tools: list[dict[str, Any]] = field(default_factory=list)
    output_schema: type[BaseModel] | None = None
    cache_breakpoints: tuple[CacheBreakpoint, ...] = ()
    auto_cache_tail: bool = True
    thinking_display: Literal["omitted", "summarized"] = "omitted"
    iteration: int = 0
    purpose: str = ""          # free label for logs, e.g. "refusal_retry", "anchor_repair"

    def __post_init__(self) -> None:
        n = len(self.cache_breakpoints) + (1 if self.auto_cache_tail else 0)
        if n > MAX_CACHE_BREAKPOINTS:
            raise ValueError(f"{n} cache breakpoints requested; the API allows {MAX_CACHE_BREAKPOINTS}")


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens,
                     self.cache_creation_input_tokens + other.cache_creation_input_tokens,
                     self.cache_read_input_tokens + other.cache_read_input_tokens)

    @property
    def total_input_tokens(self) -> int:
        """All input tokens including cache reads and writes (the ``budget_tokens`` stop rule)."""
        return self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens


@dataclass(frozen=True)
class LLMAttempt:
    attempt: int
    started_at: str
    elapsed_s: float
    outcome: str                     # "ok" or the error class name
    status_code: int | None = None
    retry_after_s: float | None = None


@dataclass(frozen=True)
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class LLMResult(Generic[T]):
    call_id: str
    phase: PhaseName
    conversation_id: str
    model: str                       # response.model (served), not the requested ID
    stop_reason: str                 # end_turn | tool_use | pause_turn (refusal/max_tokens raise)
    content: list[dict[str, Any]]    # response content blocks exactly as returned (incl. thinking)
    parsed: T | None
    text: str
    tool_uses: list[ToolUse]
    usage: Usage
    request_id: str | None
    request_sha256: str
    latency_s: float
    attempts: list[LLMAttempt]
    fallback: FallbackEvent | None = None
    resumed: bool = False

    def assistant_message(self) -> dict[str, Any]:
        """The assistant turn to append to history, unmodified (preserved thinking, ADR-009)."""
        return {"role": "assistant", "content": copy.deepcopy(self.content)}


@runtime_checkable
class LLMGateway(Protocol):
    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        """Make one model call (with the gateway's retry policy). Raises an :class:`LLMError`."""
        ...

    def usage_total(self) -> Usage:
        ...

    def served_models(self) -> set[str]:
        ...

    def fallback_events(self) -> list[FallbackEvent]:
        ...

    def refusals(self) -> list[dict[str, Any]]:
        """``[{call_id, stage, category}]`` for the manifest (REPRODUCIBILITY §8)."""
        ...


# ------------------------------------------------------------------------------ shared helpers


def strip_pdf_bytes(body: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Copy of a request body with every base64 document payload replaced by ``sha256:<hex>``."""
    out = copy.deepcopy(body)
    hashes: list[str] = []
    for msg in out.get("messages", []):
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            src = block.get("source") if isinstance(block, dict) else None
            if isinstance(src, dict) and src.get("type") == "base64" and isinstance(src.get("data"), str):
                h = sha256_text(src["data"])
                hashes.append(h)
                src["data"] = f"sha256:{h}"
    return out, hashes


def request_sha256(body: dict[str, Any]) -> str:
    """Hash of the request body as logged (PDF bytes replaced by their hash). LLM replay key."""
    return sha256_json(strip_pdf_bytes(body)[0])


class LLMCallLog:
    """Appends one JSON object per call (and per failed attempt) to ``runs/<id>/llm.jsonl``."""

    def __init__(self, run_dir: RunDir) -> None:
        self.writer = JsonlWriter(run_dir.llm_log)

    def log(self, entry: dict[str, Any]) -> int:
        return self.writer.append(entry)


class EffortGuard:
    """Enforces one effort level per conversation (ADR-002 option a)."""

    def __init__(self) -> None:
        self._effort: dict[str, str] = {}

    def check(self, request: LLMRequest) -> None:
        prev = self._effort.setdefault(request.conversation_id, request.effort)
        if prev != request.effort:
            raise EffortChangedError(f"conversation {request.conversation_id} uses effort {prev}; "
                                     f"got {request.effort}", phase=request.phase.value)


# ------------------------------------------------------------------------------ live gateway


class AnthropicGateway:
    """Live gateway over ``anthropic.AsyncAnthropic`` (stub: :meth:`call` is not implemented yet).

    Construction never touches the network. ``client`` may be injected (tests); otherwise one is
    created on first use with ``max_retries=0`` and ``timeout=config.agent.llm.timeout_s``.
    """

    def __init__(self, config: EffectiveConfig, run_dir: RunDir, *, clock: Clock | None = None,
                 progress: ProgressSink | None = None, client: Any | None = None) -> None:
        self.config = config
        self.run_dir = run_dir
        self.clock = clock or SystemClock()
        self.progress = progress
        self.model = config.agent.model
        self.allow_fallback = config.agent.allow_fallback
        self.max_retries = config.agent.llm.max_retries
        self.timeout_s = config.agent.llm.timeout_s
        self.log = LLMCallLog(run_dir)
        self._client = client
        self._guard = EffortGuard()
        self._usage = Usage()
        self._served: set[str] = set()
        self._fallbacks: list[FallbackEvent] = []
        self._refusals: list[dict[str, Any]] = []
        self._seq = 0

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(max_retries=0, timeout=self.timeout_s)
        return self._client

    def next_call_id(self) -> str:
        self._seq += 1
        return f"llm-{self._seq:04d}"

    def build_body(self, request: LLMRequest) -> dict[str, Any]:
        """SDK keyword arguments for ``request``: model, max_tokens, system, messages (with
        ``cache_control`` placed per ``cache_breakpoints``), tools, ``thinking: adaptive`` with
        ``display``, ``output_config.effort``, top-level ``cache_control`` when ``auto_cache_tail``,
        and ``fallbacks``/``betas`` only when ``allow_fallback``."""
        raise NotImplementedError("phase 1: AnthropicGateway.build_body (workstream A)")

    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        """Stream the request (``client.messages.stream`` / ``.parse``), apply the retry policy,
        check ``stop_reason``, parse ``output_schema``, log to ``llm.jsonl``."""
        raise NotImplementedError("phase 1: AnthropicGateway.call (workstream A)")

    async def models_retrieve(self) -> dict[str, Any]:
        """``client.models.retrieve(model)`` -> ``{id, created_at, max_input_tokens, max_tokens}``
        for the manifest (REPRODUCIBILITY §2)."""
        raise NotImplementedError("phase 1: AnthropicGateway.models_retrieve (workstream A)")

    async def preflight(self) -> None:
        """1-token call; fail fast naming ``ANTHROPIC_API_KEY`` (never its value; LLM-11)."""
        raise NotImplementedError("phase 1: AnthropicGateway.preflight (workstream A)")

    def usage_total(self) -> Usage:
        return self._usage

    def served_models(self) -> set[str]:
        return set(self._served)

    def fallback_events(self) -> list[FallbackEvent]:
        return list(self._fallbacks)

    def refusals(self) -> list[dict[str, Any]]:
        return list(self._refusals)


# ------------------------------------------------------------------------------ fake gateway


@dataclass
class FakeResponse:
    """One scripted model response. Exactly one of ``parsed``/``text``/``tool_uses``/``raises``
    is normally set. ``parsed`` may be a model instance or a dict validated against the request's
    ``output_schema``. ``stop_reason`` ``refusal``/``max_tokens`` raise the gateway's typed errors."""

    parsed: BaseModel | dict[str, Any] | None = None
    text: str = ""
    tool_uses: list[ToolUse] = field(default_factory=list)
    stop_reason: str | None = None          # default: tool_use if tool_uses else end_turn
    raises: LLMError | None = None
    refusal_category: str | None = None
    usage: Usage = field(default_factory=lambda: Usage(input_tokens=1000, output_tokens=200))
    model: str | None = None                 # served model; default = the gateway's model


class FakeGateway:
    """Deterministic gateway for tests: pops the next :class:`FakeResponse` scripted for the
    request's phase. Logs to ``llm.jsonl`` like the live gateway when ``run_dir`` is given."""

    def __init__(self, script: Mapping[PhaseName | str, Sequence[FakeResponse]], *,
                 run_dir: RunDir | None = None, model: str = "claude-opus-5-5",
                 clock: Clock | None = None) -> None:
        self.script: dict[str, deque[FakeResponse]] = {str(k): deque(v) for k, v in script.items()}
        self.model = model
        self.clock = clock or SystemClock()
        self.log = LLMCallLog(run_dir) if run_dir is not None else None
        self.calls: list[LLMRequest] = []
        self._guard = EffortGuard()
        self._usage = Usage()
        self._served: set[str] = set()
        self._refusals: list[dict[str, Any]] = []
        self._seq = 0

    def remaining(self, phase: PhaseName | str | None = None) -> int:
        if phase is not None:
            return len(self.script.get(str(phase), ()))
        return sum(len(q) for q in self.script.values())

    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        self._guard.check(request)
        self.calls.append(request)
        self._seq += 1
        call_id = f"llm-{self._seq:04d}"
        queue = self.script.get(str(request.phase))
        if not queue:
            raise FakeScriptExhausted(f"no scripted response left for phase {request.phase}",
                                      call_id=call_id, phase=request.phase.value)
        resp = queue.popleft()
        body = {"model": self.model, "system": request.system, "messages": request.messages,
                "tools": request.tools, "effort": request.effort, "max_tokens": request.max_tokens}
        req_hash = request_sha256(body)
        served = resp.model or self.model
        started = isoformat_z(self.clock.now_utc())
        stop = resp.stop_reason or ("tool_use" if resp.tool_uses else "end_turn")
        self._usage = self._usage + resp.usage
        self._served.add(served)

        def _log(outcome: str, content: list[dict[str, Any]]) -> None:
            if self.log is not None:
                self.log.log({"call_id": call_id, "phase": request.phase.value, "purpose": request.purpose,
                              "conversation_id": request.conversation_id, "request_sha256": req_hash,
                              "model": served, "stop_reason": stop, "outcome": outcome, "started_at": started,
                              "usage": resp.usage.__dict__, "content": content, "fake": True})

        if resp.raises is not None:
            _log(type(resp.raises).__name__, [])
            raise resp.raises
        if stop == "refusal":
            self._refusals.append({"call_id": call_id, "stage": request.phase.value, "category": resp.refusal_category})
            _log("LLMRefusalError", [])
            raise LLMRefusalError("model declined", category=resp.refusal_category, call_id=call_id,
                                  phase=request.phase.value)
        if stop == "max_tokens":
            _log("LLMTruncatedError", [])
            raise LLMTruncatedError("output truncated at max_tokens", max_tokens=request.max_tokens,
                                    call_id=call_id, phase=request.phase.value)

        parsed: BaseModel | None = None
        if request.output_schema is not None and resp.parsed is not None:
            try:
                parsed = (resp.parsed if isinstance(resp.parsed, request.output_schema)
                          else request.output_schema.model_validate(
                              resp.parsed.model_dump(mode="json") if isinstance(resp.parsed, BaseModel)
                              else resp.parsed))
            except ValidationError as exc:
                _log("LLMSchemaError", [])
                raise LLMSchemaError(f"scripted output does not match {request.output_schema.__name__}: {exc}",
                                     call_id=call_id, phase=request.phase.value) from exc
        text = resp.text or (parsed.model_dump_json() if parsed is not None else "")
        content: list[dict[str, Any]] = [{"type": "thinking", "thinking": "", "signature": "fake"}]
        if text:
            content.append({"type": "text", "text": text})
        content += [{"type": "tool_use", "id": t.id, "name": t.name, "input": t.input} for t in resp.tool_uses]
        _log("ok", content)
        return LLMResult(call_id=call_id, phase=request.phase, conversation_id=request.conversation_id,
                         model=served, stop_reason=stop, content=content, parsed=parsed, text=text,
                         tool_uses=list(resp.tool_uses), usage=resp.usage, request_id=None,
                         request_sha256=req_hash, latency_s=0.0,
                         attempts=[LLMAttempt(attempt=0, started_at=started, elapsed_s=0.0, outcome="ok")])

    def usage_total(self) -> Usage:
        return self._usage

    def served_models(self) -> set[str]:
        return set(self._served)

    def fallback_events(self) -> list[FallbackEvent]:
        return []

    def refusals(self) -> list[dict[str, Any]]:
        return list(self._refusals)


# ------------------------------------------------------------------------------ fault injection


class FaultInjectingLLMGateway:
    """Applies the ``llm:`` rules of a robustness fault schedule *below* the retry policy
    (robustness §5.1): ``http_status`` (429/529/503 with optional ``retry_after``), ``hang``,
    ``auth``, ``connection_reset``, ``stop_reason`` (refusal / max_tokens), ``schema_violation``,
    ``latency``, ``flaky``. Match keys: ``stage``, ``attempt``, ``after_seconds``."""

    def __init__(self, inner: LLMGateway, schedule: Any, *, clock: Clock | None = None) -> None:
        self.inner = inner
        self.schedule = schedule     # tools.faults.FaultSchedule (typed there to avoid an import cycle)
        self.clock = clock or SystemClock()

    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        raise NotImplementedError("phase 2: FaultInjectingLLMGateway.call (workstream B)")

    def usage_total(self) -> Usage:
        return self.inner.usage_total()

    def served_models(self) -> set[str]:
        return self.inner.served_models()

    def fallback_events(self) -> list[FallbackEvent]:
        return self.inner.fallback_events()

    def refusals(self) -> list[dict[str, Any]]:
        return self.inner.refusals()
