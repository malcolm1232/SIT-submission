"""The single choke point for every model call (ADR-001, robustness §10 item 1).

* :class:`LLMGateway` is the protocol every phase uses; phases never touch the SDK.
* :class:`AnthropicGateway` is the live implementation (``anthropic`` 1.x ``AsyncAnthropic``,
  ``max_retries=0`` so the gateway owns retries, streaming for every call, ``thinking: adaptive``,
  ``output_config.effort``, structured outputs via ``output_config.format = {"type":
  "json_schema", "schema": llm_facing_schema(T)}`` on the stream, parsed and validated here; see
  the class docstring for why not ``messages.parse``). ``llm.claude_code.ClaudeCodeGateway`` is the
  other live backend (ADR-010); ``llm.backend.build_llm_gateway`` picks one.
* :class:`FakeGateway` replays scripted responses keyed by phase (L0 tests, ``selftest``).
* :class:`FaultInjectingLLMGateway` wraps any gateway with a robustness fault schedule.
* :func:`prepare_resume` makes a freshly built stack continue a run (call IDs, ``resumed`` flag).

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
   as returned, except that configured secrets and canary tokens are redacted in the logged copy
   (INV-08, :func:`redact_log_entry`). Conversations are replayed from the live result objects
   (``LLMResult.assistant_message``) or, for ``ClaudeCodeGateway``, the CLI's own transcript, never
   from ``llm.jsonl`` (ADR-009 item 3).
6. Never sent: ``temperature``/``top_p``/``top_k``, ``budget_tokens``, forced ``tool_choice``,
   assistant prefill (all 400 on Opus 5.5).
"""

from __future__ import annotations

import copy
import dataclasses
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
    #: True for a call of the stage that was re-run after ``sit-review resume`` (ADR-009 item 2);
    #: the same flag is written as ``resumed: true`` on its ``llm.jsonl`` entries. Set by the
    #: gateways from :func:`prepare_resume`.
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


#: Environment variables whose values never reach ``llm.jsonl`` (INV-08); the tool config's
#: ``auth_env`` is added by the live gateways.
LOG_SECRET_ENV = ("SIT_MCP_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")


def redact_log_entry(entry: dict[str, Any], redactor: Any) -> dict[str, Any]:
    """``entry`` as it may be written to ``llm.jsonl`` (INV-08: "no canary key value appears in any
    artefact ... log"): every configured secret replaced by ``tools.cassette.Redactor`` and every
    robustness canary token (``tools.policy.CANARY_RE``) masked, in every string of the entry. This
    covers the model's ``tool_use`` inputs (a canary the model writes into a tool call that the tool
    policy then blocks), request bodies, response text and error messages. Only the logged copy is
    changed: request hashes are computed before, and history is replayed from the live objects (or
    the CLI's own transcript), never from ``llm.jsonl``."""
    from sit_review_agent.tools.policy import CANARY_RE

    def walk(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list | tuple):
            return [walk(x) for x in v]
        if isinstance(v, str):
            return CANARY_RE.sub(REDACTED_CANARY, redactor.text(v))
        return v

    return walk(entry)


#: What :func:`redact_log_entry` writes in place of a canary token.
REDACTED_CANARY = "***REDACTED-CANARY***"


class LLMCallLog:
    """Appends one JSON object per call (and per failed attempt) to ``runs/<id>/llm.jsonl``.

    Every entry goes through :func:`redact_log_entry` (``redactor`` defaults to the values of
    :data:`LOG_SECRET_ENV`). ``resumed_phases`` is set by the resume path
    (:func:`prepare_resume`): entries of those phases are logged with ``resumed: true`` (ADR-009
    item 2: model calls of the stage that is re-run after a resume)."""

    def __init__(self, run_dir: RunDir, *, redactor: Any = None, secret_env: Sequence[str] = ()) -> None:
        from sit_review_agent.tools.cassette import Redactor

        self.writer = JsonlWriter(run_dir.llm_log)
        self.redactor = redactor if redactor is not None else Redactor.from_env(
            tuple(dict.fromkeys([*LOG_SECRET_ENV, *secret_env])))
        self.resumed_phases: set[str] = set()

    def is_resumed(self, phase: PhaseName | str) -> bool:
        return str(phase.value if isinstance(phase, PhaseName) else phase) in self.resumed_phases

    def log(self, entry: dict[str, Any]) -> int:
        if entry.get("phase") is not None and self.is_resumed(str(entry["phase"])):
            entry = {**entry, "resumed": True}
        return self.writer.append(redact_log_entry(entry, self.redactor))


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


#: ``backend`` value in ``llm.jsonl`` entries written by :class:`AnthropicGateway`.
_ANTHROPIC_BACKEND = "anthropic_api"
#: Stop reasons that mean the output was cut off (never repaired; robustness LLM-07).
_ANTHROPIC_TRUNCATED = frozenset({"max_tokens", "model_context_window_exceeded"})
#: Fields the SDK adds to parsed blocks that are not API fields (never sent back).
_ANTHROPIC_LOCAL_FIELDS = ("parsed_output",)


def _anthropic_dump(obj: Any) -> Any:
    """A response object (SDK Pydantic model, ``SimpleNamespace`` or dict) as plain JSON data,
    using API field names (``from`` not ``from_``) and only the fields the API returned."""
    if obj is None or isinstance(obj, str | int | float | bool):
        return obj
    if isinstance(obj, dict):
        return {k: _anthropic_dump(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_anthropic_dump(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if hasattr(obj, "__dict__"):
        return {k: _anthropic_dump(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return obj


def _anthropic_block(block: Any) -> dict[str, Any]:
    """One response content block as the dict appended to history (thinking blocks and their
    signatures kept byte for byte; SDK-local fields such as ``parsed_output`` dropped)."""
    d = _anthropic_dump(block)
    if not isinstance(d, dict):
        raise LLMSchemaError(f"unexpected content block {type(block).__name__}")
    for k in _ANTHROPIC_LOCAL_FIELDS:
        d.pop(k, None)
    return d


def _anthropic_get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _anthropic_usage(usage: Any) -> Usage:
    def n(key: str) -> int:
        v = _anthropic_get(usage, key)
        return int(v) if isinstance(v, int | float) else 0

    return Usage(n("input_tokens"), n("output_tokens"), n("cache_creation_input_tokens"),
                 n("cache_read_input_tokens"))


def _anthropic_retry_after(exc: Any) -> float | None:
    """Seconds from ``retry-after`` (or ``retry-after-ms``) on an SDK status error, else ``None``."""
    headers = _anthropic_get(_anthropic_get(exc, "response"), "headers")
    if headers is None:
        return None
    try:
        ms = headers.get("retry-after-ms")
        if ms is not None:
            return max(0.0, float(ms) / 1000.0)
        s = headers.get("retry-after")
        return max(0.0, float(s)) if s is not None else None
    except (TypeError, ValueError):
        return None


def _anthropic_classify(exc: BaseException, *, call_id: str | None,
                        phase: str | None) -> tuple[LLMError, bool, float | None, int | None] | None:
    """Map an SDK / transport exception onto ``(typed error, retry?, retry_after_s, status)``.

    Follows the typed class chain of the claude-api skill (``shared/error-codes.md``): most specific
    first, then ``APIStatusError`` by status and by error ``type`` (a mid-stream ``error`` event
    arrives as a bare ``APIStatusError`` with HTTP 200 and ``type: overloaded_error``), then
    ``APIConnectionError``. Returns ``None`` for exceptions that are not SDK/transport failures
    (bugs), which the caller re-raises unchanged.
    """
    import anthropic

    from sit_review_agent.errors import (
        LLMAuthError,
        LLMBadRequestError,
        LLMOverloadedError,
        LLMRateLimitError,
        LLMTimeoutError,
        LLMUnavailableError,
    )

    kw: dict[str, Any] = {"call_id": call_id, "phase": phase}
    key_hint = ("check ANTHROPIC_API_KEY (the value is never logged) or switch config/agent.yaml llm.backend "
                "to claude_code")
    if isinstance(exc, LLMError):
        return exc, False, None, None
    if isinstance(exc, anthropic.APITimeoutError | TimeoutError):
        return LLMTimeoutError("request to the Anthropic API timed out", **kw), True, None, None
    if isinstance(exc, anthropic.APIConnectionError):
        return LLMUnavailableError("could not reach the Anthropic API (connection error)", **kw), True, None, None
    if isinstance(exc, anthropic.APIStatusError):
        status = int(getattr(exc, "status_code", 0) or 0)
        etype = getattr(exc, "type", None)
        if (isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError)
                or status in (401, 403) or etype in ("authentication_error", "permission_error")):
            return LLMAuthError(f"the Anthropic API rejected the credentials (HTTP {status}, {etype}); {key_hint}",
                                **kw), False, None, status
        if isinstance(exc, anthropic.RateLimitError) or status == 429 or etype == "rate_limit_error":
            ra = _anthropic_retry_after(exc)
            return (LLMRateLimitError(f"rate limited by the Anthropic API (HTTP 429, retry-after {ra})",
                                      retry_after_s=ra, **kw), True, ra, status)
        if (isinstance(exc, anthropic.OverloadedError | anthropic.ServiceUnavailableError)
                or status in (503, 529) or etype == "overloaded_error"):
            return (LLMOverloadedError(f"the Anthropic API is overloaded (HTTP {status}, {etype})", **kw),
                    True, None, status)
        if isinstance(exc, anthropic.InternalServerError) or status >= 500 or etype == "api_error":
            return LLMUnavailableError(f"Anthropic API server error (HTTP {status}, {etype})", **kw), True, None, status
        if status == 402 or etype == "billing_error":
            return LLMUnavailableError(f"Anthropic API billing error (HTTP {status}); check the account's credit",
                                       **kw), False, None, status
        message = str(getattr(exc, "message", "") or "")[:300]
        if isinstance(exc, anthropic.NotFoundError):
            return LLMBadRequestError(f"HTTP 404 from the Anthropic API (is the model available to this key?): "
                                      f"{message}", **kw), False, None, status
        return (LLMBadRequestError(f"HTTP {status} ({etype}) from the Anthropic API: {message}", **kw),
                False, None, status)
    if isinstance(exc, anthropic.CredentialsError):
        return LLMAuthError(f"no usable Anthropic credentials; {key_hint}", **kw), False, None, None
    if isinstance(exc, TypeError) and "authentication" in str(exc).lower():
        return LLMAuthError(f"no usable Anthropic credentials; {key_hint}", **kw), False, None, None
    if isinstance(exc, anthropic.AnthropicError):
        return LLMUnavailableError(f"Anthropic SDK error: {type(exc).__name__}", **kw), True, None, None
    return None


def _anthropic_messages(request: LLMRequest) -> list[dict[str, Any]]:
    """Deep copy of ``request.messages`` with ``cache_control`` on every breakpointed block."""
    from sit_review_agent.errors import LLMBadRequestError

    msgs = copy.deepcopy(request.messages)
    phase = request.phase.value
    if msgs and msgs[-1].get("role") == "assistant":
        raise LLMBadRequestError("the last message is an assistant turn (prefill is rejected on Opus 5.5)",
                                 phase=phase)
    for bp in request.cache_breakpoints:
        try:
            msg = msgs[bp.message_index]
            if isinstance(msg.get("content"), str):
                msg["content"] = [{"type": "text", "text": msg["content"]}]
            block = msg["content"][bp.block_index]
        except (IndexError, KeyError, TypeError):
            raise LLMBadRequestError(f"cache breakpoint {bp} does not point at a content block",
                                     phase=phase) from None
        if not isinstance(block, dict) or block.get("type") in ("thinking", "redacted_thinking"):
            raise LLMBadRequestError(f"cache breakpoint {bp} points at a block that cannot be cached", phase=phase)
        block["cache_control"] = {"type": "ephemeral", "ttl": bp.ttl}
    return msgs


class AnthropicGateway:
    """Live gateway over ``anthropic.AsyncAnthropic`` (Claude API with ``ANTHROPIC_API_KEY``).

    Construction never touches the network. ``client`` may be injected (tests); otherwise one is
    created on first use with ``max_retries=0`` and ``timeout=config.agent.llm.timeout_s``.

    * **Transport.** Every request is streamed: ``client.messages.stream(**build_body(...))`` (or
      ``client.beta.messages.stream`` when ``allow_fallback``) and ``get_final_message()``.
    * **Structured outputs.** ``output_config.format = {"type": "json_schema", "schema":
      llm_facing_schema(T)}`` on the stream, then ``T.model_validate_json`` on the text block, rather
      than ``client.messages.parse(output_format=T)``: ``parse`` is not streamed (ADR-002 streams
      every call), the schema actually sent is then ours (hashed, logged in ``llm.jsonl`` and
      identical to the one ``ClaudeCodeGateway`` sends), and validation failures surface in one
      place as :class:`LLMSchemaError` instead of inside the SDK.
    * **Stop reasons** are classified before any content is read (module docstring, item 1).
    * **Retries** (gateway-owned, ``llm.max_retries``): 429 sleeps ``retry-after`` (backoff if
      absent); 529/503/5xx, connection errors and timeouts back off exponentially with jitter
      through ``clock.sleep``; 401/403 raise :class:`LLMAuthError` naming ``ANTHROPIC_API_KEY``;
      400/404/413 raise :class:`LLMBadRequestError`; neither is retried.
    * **Fallback.** ``response.model != requested``, a ``fallback`` content block or a
      ``fallback_message`` entry in ``usage.iterations`` becomes a :class:`FallbackEvent`.
    """

    #: Native PDF document blocks are accepted (``llm.backend.supports_native_pdf``).
    native_pdf: bool = True

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
        self.backoff_base_s = config.agent.llm.backoff_base_s
        self.backoff_max_s = config.agent.llm.backoff_max_s
        self.log = LLMCallLog(run_dir, secret_env=(config.tools.auth_env,))
        self._client = client
        self._guard = EffortGuard()
        self._usage = Usage()
        self._served: set[str] = set()
        self._fallbacks: list[FallbackEvent] = []
        self._refusals: list[dict[str, Any]] = []
        self._seq = 0
        import random

        self._rng = random.Random()

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
        and ``fallbacks``/``betas`` only when ``allow_fallback``.

        * ``system`` is a list with one text block (so a ``cache_control`` could sit on it); it is
          omitted when empty. Render order is tools -> system -> messages, so the explicit
          breakpoint after the document blocks caches tools, system and documents together.
        * Explicit breakpoints: ``messages[i].content[j].cache_control = {"type": "ephemeral",
          "ttl": ttl}`` (``llm.prefix``); a string content is first turned into one text block.
        * ``output_config = {"effort": ..., "format": {"type": "json_schema", "schema":
          llm_facing_schema(output_schema)}}``; the format is omitted without ``output_schema``.
        * With ``allow_fallback`` the body also carries ``fallbacks="default"`` and
          ``betas=[FALLBACK_BETA]`` and must be sent through ``client.beta.messages``.
        * Never present: ``temperature``/``top_p``/``top_k``, ``budget_tokens``, ``tool_choice``,
          and assistant prefill (a trailing assistant turn raises :class:`LLMBadRequestError`).
        """
        from sit_review_agent.llm.outputs import llm_facing_schema

        output_config: dict[str, Any] = {"effort": request.effort}
        if request.output_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": llm_facing_schema(request.output_schema)}
        body: dict[str, Any] = {"model": self.model, "max_tokens": request.max_tokens}
        if request.system:
            body["system"] = [{"type": "text", "text": request.system}]
        body["messages"] = _anthropic_messages(request)
        if request.tools:
            body["tools"] = copy.deepcopy(request.tools)
        body["thinking"] = {"type": "adaptive", "display": request.thinking_display}
        body["output_config"] = output_config
        if request.auto_cache_tail:
            body["cache_control"] = {"type": "ephemeral"}
        if self.allow_fallback:
            body["fallbacks"] = "default"
            body["betas"] = [FALLBACK_BETA]
        return body

    def _anthropic_backoff(self, attempt: int) -> float:
        delay = min(self.backoff_max_s, self.backoff_base_s * (2 ** attempt))
        return delay * (0.5 + 0.5 * self._rng.random())

    def _anthropic_messages_api(self) -> Any:
        return self.client.beta.messages if self.allow_fallback else self.client.messages

    async def _anthropic_stream(self, body: dict[str, Any], phase: str, call_id: str) -> tuple[Any, str | None]:
        """One streamed attempt: the final message and the request ID (``request-id`` header)."""
        from sit_review_agent.progress import heartbeat

        async def consume() -> tuple[Any, str | None]:
            async with self._anthropic_messages_api().stream(**body) as stream:
                final = await stream.get_final_message()
                rid = getattr(final, "_request_id", None)
                if rid is None:
                    try:
                        rid = getattr(stream, "request_id", None)
                    except Exception:  # noqa: BLE001 - a header lookup must never fail the call
                        rid = None
                return final, (str(rid) if rid is not None else None)

        if self.progress is None:
            return await consume()
        async with heartbeat(self.progress, phase, lambda: f"waiting on the Anthropic API ({call_id})",
                             clock=self.clock):
            return await consume()

    def _anthropic_fallback(self, phase: str, call_id: str, served: str, content: list[dict[str, Any]],
                            usage: Any) -> FallbackEvent | None:
        block = next((b for b in content if b.get("type") == "fallback"), None)
        iterations = _anthropic_get(usage, "iterations") or []
        hop = any(_anthropic_get(it, "type") == "fallback_message" for it in iterations)
        if served == self.model and block is None and not hop:
            return None
        category = ((block or {}).get("trigger") or {}).get("category")
        to_model = served if served != self.model else str(((block or {}).get("to") or {}).get("model") or served)
        how = ("server-side fallback (fallbacks: default)" if self.allow_fallback
               else "served model differs from requested")
        event = FallbackEvent(role=phase, from_model=self.model, to_model=to_model,
                              reason=f"{how}; refusal category {category}; call {call_id}")
        self._fallbacks.append(event)
        return event

    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        """Stream the request (``client.messages.stream`` + ``get_final_message``; see the class
        docstring for why not ``.parse``), apply the retry policy, check ``stop_reason`` before
        reading content, parse ``output_schema``, and log every attempt to ``llm.jsonl``."""
        self._guard.check(request)
        call_id = self.next_call_id()
        phase = request.phase.value
        body = self.build_body(request)
        logged_body, pdf_hashes = strip_pdf_bytes(body)
        req_hash = sha256_json(logged_body)
        attempts: list[LLMAttempt] = []
        t_call = self.clock.monotonic()
        attempt = 0
        while True:
            started_at = isoformat_z(self.clock.now_utc())
            t0 = self.clock.monotonic()
            base: dict[str, Any] = {
                "call_id": call_id, "phase": phase, "purpose": request.purpose,
                "conversation_id": request.conversation_id, "request_sha256": req_hash, "started_at": started_at,
                "backend": _ANTHROPIC_BACKEND, "attempt": attempt, "requested_model": self.model,
                "effort": request.effort, "max_tokens": request.max_tokens,
            }
            if attempt == 0:
                base["request"] = logged_body           # body minus PDF bytes, once per call (REPRODUCIBILITY §6)
                base["pdf_sha256"] = pdf_hashes
            try:
                message, request_id = await self._anthropic_stream(body, phase, call_id)
            except Exception as exc:  # noqa: BLE001 - classified below; non-SDK exceptions re-raised
                mapped = _anthropic_classify(exc, call_id=call_id, phase=phase)
                if mapped is None:
                    raise
                err, retry, retry_after, status = mapped
                elapsed = self.clock.monotonic() - t0
                attempts.append(LLMAttempt(attempt=attempt, started_at=started_at, elapsed_s=elapsed,
                                           outcome=type(err).__name__, status_code=status, retry_after_s=retry_after))
                self.log.log({**base, "model": self.model, "stop_reason": None, "outcome": type(err).__name__,
                              "error": str(err)[:500], "status_code": status, "retry_after_s": retry_after,
                              "usage": Usage().__dict__, "content": [], "elapsed_s": elapsed})
                if retry and attempt < self.max_retries:
                    delay = retry_after if retry_after is not None else self._anthropic_backoff(attempt)
                    if self.progress is not None:
                        self.progress.emit(phase, f"{type(err).__name__} on {call_id}; retry "
                                                  f"{attempt + 1}/{self.max_retries} in {delay:.0f} s", "warn")
                    await self.clock.sleep(delay)
                    attempt += 1
                    continue
                raise err from None
            elapsed = self.clock.monotonic() - t0
            attempts.append(LLMAttempt(attempt=attempt, started_at=started_at, elapsed_s=elapsed, outcome="ok"))
            return self._anthropic_result(request, message, request_id=request_id, call_id=call_id, base=base,
                                          req_hash=req_hash, attempts=attempts, elapsed=elapsed,
                                          latency=self.clock.monotonic() - t_call)

    def _anthropic_result(self, request: LLMRequest, message: Any, *, request_id: str | None, call_id: str,
                          base: dict[str, Any], req_hash: str, attempts: list[LLMAttempt], elapsed: float,
                          latency: float) -> LLMResult[Any]:
        """Account for a response that arrived, classify its stop reason, and build the result."""
        phase = request.phase.value
        served = str(_anthropic_get(message, "model") or self.model)
        raw_usage = _anthropic_get(message, "usage")
        usage = _anthropic_usage(raw_usage)
        self._usage = self._usage + usage
        self._served.add(served)
        stop = _anthropic_get(message, "stop_reason")
        stop = str(stop) if stop is not None else None
        details = _anthropic_get(message, "stop_details")
        content = [_anthropic_block(b) for b in (_anthropic_get(message, "content") or [])]
        fallback = self._anthropic_fallback(phase, call_id, served, content, raw_usage)
        entry: dict[str, Any] = {**base, "model": served, "stop_reason": stop, "stop_details": _anthropic_dump(details),
                                 "usage": usage.__dict__, "usage_raw": _anthropic_dump(raw_usage),
                                 "request_id": request_id, "elapsed_s": elapsed,
                                 "fallback": fallback.model_dump(mode="json") if fallback is not None else None}

        def fail(err: LLMError, *, keep_content: bool = False) -> LLMError:
            self.log.log({**entry, "outcome": type(err).__name__, "error": str(err)[:500],
                          "content": content if keep_content else []})
            return err

        if stop == "refusal":           # partial output discarded, never parsed (REPRODUCIBILITY §3)
            category = _anthropic_get(details, "category")
            explanation = _anthropic_get(details, "explanation")
            self._refusals.append({"call_id": call_id, "stage": phase, "category": category})
            raise fail(LLMRefusalError("model declined", category=category, explanation=explanation,
                                       call_id=call_id, phase=phase))
        if stop in _ANTHROPIC_TRUNCATED:
            raise fail(LLMTruncatedError(f"output truncated ({stop}) at max_tokens={request.max_tokens}",
                                         max_tokens=request.max_tokens, call_id=call_id, phase=phase))
        text = "".join(str(b.get("text", "")) for b in content if b.get("type") == "text")
        tool_uses = [ToolUse(id=str(b.get("id")), name=str(b.get("name")), input=dict(b.get("input") or {}))
                     for b in content if b.get("type") == "tool_use"]
        parsed: BaseModel | None = None
        if stop == "tool_use":
            if not tool_uses:
                raise fail(LLMSchemaError("stop_reason tool_use without a tool_use block", call_id=call_id,
                                          phase=phase), keep_content=True)
        elif stop != "pause_turn" and request.output_schema is not None:
            if not text.strip():
                raise fail(LLMSchemaError(f"no text block to parse as {request.output_schema.__name__}",
                                          call_id=call_id, phase=phase), keep_content=True)
            try:
                parsed = request.output_schema.model_validate_json(text)
            except ValidationError as exc:
                raise fail(LLMSchemaError(f"output does not match {request.output_schema.__name__}: {exc}",
                                          call_id=call_id, phase=phase), keep_content=True) from exc
        self.log.log({**entry, "outcome": "ok", "content": content})
        return LLMResult(call_id=call_id, phase=request.phase, conversation_id=request.conversation_id,
                         model=served, stop_reason=stop or "end_turn", content=copy.deepcopy(content), parsed=parsed,
                         text=text, tool_uses=tool_uses, usage=usage, request_id=request_id,
                         request_sha256=req_hash, latency_s=latency, attempts=attempts, fallback=fallback,
                         resumed=self.log.is_resumed(request.phase))

    async def _anthropic_simple(self, op: Any, *, label: str, retries: int) -> Any:
        """Run ``await op()`` with the gateway's error mapping and up to ``retries`` retries (no
        ``llm.jsonl`` entry: used for ``models.retrieve`` and the preflight ping)."""
        attempt = 0
        while True:
            try:
                return await op()
            except Exception as exc:  # noqa: BLE001 - classified below; non-SDK exceptions re-raised
                mapped = _anthropic_classify(exc, call_id=None, phase=None)
                if mapped is None:
                    raise
                err, retry, retry_after, _status = mapped
                if retry and attempt < retries:
                    if self.progress is not None:
                        self.progress.emit("run", f"{label}: {type(err).__name__}; retry {attempt + 1}/{retries}",
                                           "warn")
                    await self.clock.sleep(retry_after if retry_after is not None else self._anthropic_backoff(attempt))
                    attempt += 1
                    continue
                raise err from None

    async def models_retrieve(self) -> dict[str, Any]:
        """``client.models.retrieve(model)`` -> ``{id, created_at, max_input_tokens, max_tokens}``
        for the manifest (REPRODUCIBILITY §2). Retried like a model call; not logged to ``llm.jsonl``."""
        info = await self._anthropic_simple(lambda: self.client.models.retrieve(self.model), label="models.retrieve",
                                            retries=self.max_retries)
        created = _anthropic_get(info, "created_at")
        if hasattr(created, "isoformat"):
            created = isoformat_z(created)
        return {"id": str(_anthropic_get(info, "id") or self.model),
                "created_at": str(created) if created is not None else None,
                "max_input_tokens": _anthropic_get(info, "max_input_tokens"),
                "max_tokens": _anthropic_get(info, "max_tokens")}

    async def preflight(self) -> None:
        """1-token call (``max_tokens=1``, streamed, no retries); fail fast naming
        ``ANTHROPIC_API_KEY`` (never its value; LLM-11). Its usage and served model are counted;
        it is not logged to ``llm.jsonl`` (it is not part of the review)."""
        import os

        from sit_review_agent.errors import LLMAuthError

        if self._client is None and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise LLMAuthError("ANTHROPIC_API_KEY is not set; export it (the value is never logged) or switch "
                               "config/agent.yaml llm.backend to claude_code")

        async def ping() -> Any:
            async with self.client.messages.stream(model=self.model, max_tokens=1,
                                                   messages=[{"role": "user", "content": "ping"}]) as stream:
                return await stream.get_final_message()

        message = await self._anthropic_simple(ping, label="preflight", retries=0)
        self._usage = self._usage + _anthropic_usage(_anthropic_get(message, "usage"))
        self._served.add(str(_anthropic_get(message, "model") or self.model))

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

    def next_call_id(self) -> str:
        self._seq += 1
        return f"llm-{self._seq:04d}"

    def remaining(self, phase: PhaseName | str | None = None) -> int:
        if phase is not None:
            return len(self.script.get(str(phase), ()))
        return sum(len(q) for q in self.script.values())

    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        self._guard.check(request)
        self.calls.append(request)
        call_id = self.next_call_id()
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
                         attempts=[LLMAttempt(attempt=0, started_at=started, elapsed_s=0.0, outcome="ok")],
                         resumed=self.log.is_resumed(request.phase) if self.log is not None else False)

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
    ``latency``, ``flaky``. Match keys: ``stage``, ``attempt``, ``nth``, ``after_seconds``.

    ``policy`` (``config.agent.llm``) supplies the retry policy when the wrapped gateway does not
    carry it (``FakeGateway``), so a fake-transport drill uses the configured timeout and retries."""

    def __init__(self, inner: LLMGateway, schedule: Any, *, clock: Clock | None = None,
                 policy: Any = None) -> None:
        self.inner = inner
        self.schedule = schedule     # tools.faults.FaultSchedule (typed there to avoid an import cycle)
        self.clock = clock or SystemClock()
        self.policy = policy         # config.LLMConfig or None
        self._refusals: list[dict[str, Any]] = []      # injected refusals (the inner never saw them)

    @property
    def native_pdf(self) -> bool:
        """The wrapped backend's PDF capability (``llm.backend.supports_native_pdf``)."""
        override = self.__dict__.get("_native_pdf_override")
        return bool(getattr(self.inner, "native_pdf", True)) if override is None else bool(override)

    @native_pdf.setter
    def native_pdf(self, value: bool) -> None:
        self.__dict__["_native_pdf_override"] = bool(value)

    def _terminal_call_id(self) -> str | None:
        """A call ID from the inner gateway's sequence for an injected fault that ends the call
        (no inner call follows), so the ``llm.jsonl`` entry, the error and the refusal record can
        be joined; ``None`` when the inner gateway does not number calls."""
        fn = getattr(self.inner, "next_call_id", None)
        return str(fn()) if callable(fn) else None

    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        """One logical call. Each *attempt* is matched against the ``llm:`` rules (``stage`` =
        phase, ``attempt`` = 0-based attempt of this call, ``nth`` = 0-based index of this logical
        call among the stage's calls through this wrapper, so a phase-level retry such as the
        ``max_tokens`` retry or the schema repair turn is call ``nth + 1``; ``after_seconds`` since
        the first call through this wrapper) and against ``network: offline`` windows. An attempt with no fault
        goes to ``inner``. A retryable fault (429, 529/503/5xx, ``hang``, ``connection_reset``,
        offline) is retried here with the live gateways' policy, read from ``inner`` when it has
        it (``max_retries``, ``backoff_base_s``, ``backoff_max_s``, ``timeout_s``; else from
        ``policy``; else 4 / 2.0 / 60.0 / 600): ``retry-after`` is honoured exactly,
        otherwise exponential backoff with jitter on the injected clock; after the budget the typed
        error is raised (exit 3). Non-retryable faults raise at once: ``auth`` / 401 / 403 ->
        :class:`LLMAuthError`, 400 -> :class:`LLMBadRequestError`, ``stop_reason: refusal`` ->
        :class:`LLMRefusalError`, ``stop_reason: max_tokens`` -> :class:`LLMTruncatedError`,
        ``schema_violation`` -> the real response is corrupted and fails validation
        (:class:`LLMSchemaError`). ``latency`` delays the attempt; ``flaky`` picks one of its
        ``inner`` faults with a seeded RNG. Injected failures are logged to the inner gateway's
        ``llm.jsonl`` (``fault`` field) when it has one: a fault that is retried is logged with
        ``call_id: null`` (the attempt that succeeds is logged by the inner gateway under its own
        ID, and the result's ``attempts`` list starts with the faulted attempts); a fault that ends
        the call takes the next call ID of the inner gateway, so the entry, the raised error and an
        injected refusal (:meth:`refusals`) can be joined. Usage is the inner gateway's only."""
        import json as _json
        import random as _random

        from sit_review_agent.errors import (
            LLMAuthError,
            LLMBadRequestError,
            LLMOverloadedError,
            LLMRateLimitError,
            LLMTimeoutError,
            LLMUnavailableError,
        )
        from sit_review_agent.tools import fault_apply as fa

        st = self.__dict__.setdefault("_fault_state", {"t0": self.clock.monotonic(), "seq": 0,
                                                       "rng": _random.Random(getattr(self.schedule, "seed", 0))})
        st["seq"] += 1
        seq = st["seq"]
        phase = request.phase.value
        stage_calls = st.setdefault("stage_calls", {})
        nth = stage_calls.get(phase, 0)
        stage_calls[phase] = nth + 1
        pol = self.policy
        max_retries = int(getattr(self.inner, "max_retries", getattr(pol, "max_retries", 4)))
        base_s = float(getattr(self.inner, "backoff_base_s", getattr(pol, "backoff_base_s", 2.0)))
        max_s = float(getattr(self.inner, "backoff_max_s", getattr(pol, "backoff_max_s", 60.0)))
        timeout_s = float(getattr(self.inner, "timeout_s", getattr(pol, "timeout_s", 600.0)))
        progress = getattr(self.inner, "progress", None)
        log = getattr(self.inner, "log", None)
        seed = getattr(self.schedule, "seed", 0)
        attempt = 0
        injected: list[LLMAttempt] = []        # faulted attempts, prepended to the result's attempts
        while True:
            elapsed = self.clock.monotonic() - st["t0"]
            rng = fa.seeded_rng(seed, "llm", phase, seq, attempt)
            spec: Any = None
            delay = 0.0
            if fa.offline_now(self.schedule, elapsed):
                spec = "offline"
            else:
                for rule in self.schedule.llm:
                    if not fa.match_rule(rule.match, stage=phase, attempt=attempt, nth=nth, elapsed_s=elapsed):
                        continue
                    s = fa.resolve_flaky(rule.fault, rng)
                    if s is None:
                        continue
                    if s.type.value == "latency":
                        delay += fa.latency_seconds(s, rng)
                    elif spec is None:
                        spec = s
            if delay:
                await self.clock.sleep(delay)
            if spec is None:
                return self._with_injected(await self.inner.call(request), injected)
            kind = spec if isinstance(spec, str) else spec.type.value
            t_attempt, started_attempt = self.clock.monotonic(), isoformat_z(self.clock.now_utc())
            status_code: int | None = None
            err: LLMError
            retry = True
            wait: float | None = None
            if kind == "offline":
                err = LLMUnavailableError("network unreachable (offline) [injected fault]", phase=phase)
            elif kind == "hang":
                await self.clock.sleep(timeout_s)
                err = LLMTimeoutError(f"no response within {timeout_s:.0f} s (hang) [injected fault]", phase=phase)
            elif kind == "connection_reset":
                err = LLMUnavailableError("connection reset by peer [injected fault]", phase=phase)
            elif kind in ("http_status", "auth"):
                extra = spec.model_extra or {}
                status = int(extra.get("status", extra.get("code", extra.get("value", 401 if kind == "auth" else 500))))
                status_code = status
                ra = extra.get("retry_after")
                if status in (401, 403):
                    err, retry = LLMAuthError(f"HTTP {status}: the model API refused the credentials; check "
                                              "ANTHROPIC_API_KEY (anthropic_api) or the Claude Code login "
                                              "(claude_code) [injected fault]", phase=phase), False
                elif status == 429:
                    wait = float(ra) if ra is not None else None
                    why = f"retry after {ra} s" if ra is not None else "no retry-after: spend cap or usage limit"
                    err = LLMRateLimitError(f"HTTP 429 ({why}) [injected fault]", retry_after_s=wait, phase=phase)
                elif status in (529, 503):
                    err = LLMOverloadedError(f"HTTP {status} (overloaded) [injected fault]", phase=phase)
                elif status >= 500:
                    err = LLMUnavailableError(f"HTTP {status} [injected fault]", phase=phase)
                else:
                    err, retry = LLMBadRequestError(f"HTTP {status} [injected fault]", phase=phase), False
            elif kind == "stop_reason":
                extra = spec.model_extra or {}
                if str(extra.get("value", "refusal")) == "max_tokens":
                    err = LLMTruncatedError("output truncated at max_tokens [injected fault]",
                                            max_tokens=request.max_tokens, phase=phase)
                else:
                    category = extra.get("category")
                    err = LLMRefusalError("model declined [injected fault]", category=category, phase=phase)
                retry = False
            elif kind == "schema_violation":
                res = await self.inner.call(request)
                extra = spec.model_extra or {}
                problem = "schema_violation"
                if request.output_schema is not None and res.parsed is not None:
                    data = res.parsed.model_dump(mode="json")
                    field_name = str(extra.get("drop_field") or extra.get("bad_enum") or "")
                    if extra.get("prose_prefix") is not None or not field_name or field_name not in data:
                        payload: Any = f"Here is my answer: {_json.dumps(data)}"
                    elif extra.get("drop_field"):
                        payload = {k: v for k, v in data.items() if k != field_name}
                    else:
                        payload = {**data, field_name: "__not_an_allowed_value__"}
                    try:
                        if isinstance(payload, str):
                            request.output_schema.model_validate_json(payload)
                        else:
                            request.output_schema.model_validate(payload)
                    except ValidationError as exc:
                        problem = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}"
                                            for e in exc.errors()[:5])
                err, retry = LLMSchemaError(f"structured output did not validate: {problem} [injected fault]",
                                            call_id=res.call_id, phase=phase), False
            else:                                   # MCP- or process-level fault types: not for this layer
                return self._with_injected(await self.inner.call(request), injected)
            final = not retry or attempt >= max_retries
            if final and err.call_id is None:
                # The call ends here: number it like a real call (schema_violation keeps the
                # inner call's ID). A retried fault is logged with call_id null: the attempt that
                # succeeds later is logged by the inner gateway under its own ID.
                err.call_id = self._terminal_call_id()
            if isinstance(err, LLMRefusalError):
                self._refusals.append({"call_id": err.call_id, "stage": phase, "category": err.category})
            injected.append(LLMAttempt(attempt=attempt, started_at=started_attempt,
                                       elapsed_s=self.clock.monotonic() - t_attempt, outcome=type(err).__name__,
                                       status_code=status_code,
                                       retry_after_s=getattr(err, "retry_after_s", None)))
            if log is not None:
                log.log({"call_id": err.call_id if final else None, "phase": phase, "purpose": request.purpose,
                         "conversation_id": request.conversation_id, "attempt": attempt,
                         "outcome": type(err).__name__, "fault": kind, "message": str(err),
                         "started_at": started_attempt})
            if final:
                raise err
            if wait is None:
                wait = min(max_s, base_s * (2 ** attempt)) * (0.5 + 0.5 * st["rng"].random())
            if progress is not None:
                progress.emit(phase, f"{type(err).__name__}: {err}; retry {attempt + 1}/{max_retries} in "
                                     f"{wait:.0f} s", "warn")
            await self.clock.sleep(wait)
            attempt += 1

    @staticmethod
    def _with_injected(res: LLMResult[Any], injected: list[LLMAttempt]) -> LLMResult[Any]:
        """The inner result with the faulted attempts in front (renumbered so that ``attempts`` is
        ``0..n`` over the whole logical call); usage is the inner call's only (an injected fault
        spends nothing). ``latency_s`` is left as the inner gateway measured it."""
        if not injected:
            return res
        n = len(injected)
        inner = [dataclasses.replace(a, attempt=a.attempt + n) for a in res.attempts]
        return dataclasses.replace(res, attempts=[*injected, *inner])

    def usage_total(self) -> Usage:
        return self.inner.usage_total()

    def served_models(self) -> set[str]:
        return self.inner.served_models()

    def fallback_events(self) -> list[FallbackEvent]:
        return self.inner.fallback_events()

    def refusals(self) -> list[dict[str, Any]]:
        """The inner gateway's refusals plus the injected ones (each with its call ID)."""
        return [*self.inner.refusals(), *self._refusals]


# ------------------------------------------------------------------------------ resume hook


def prepare_resume(gw: Any, *, last_call_number: int, resumed_phase: PhaseName | str | None) -> None:
    """Make a freshly built gateway stack continue a run (ADR-009), walking ``gw`` and every
    ``.inner`` layer:

    * call numbering continues after ``llm-<last_call_number>``, so a resumed call never reuses an
      ID already in ``llm.jsonl`` (every gateway here numbers calls with ``_seq``: ``AnthropicGateway``,
      ``ClaudeCodeGateway``, ``FakeGateway``; ``FaultInjectingLLMGateway`` borrows its inner's);
    * calls of ``resumed_phase`` (the stage that is re-run from its checkpoint) are logged with
      ``resumed: true`` and returned with ``LLMResult.resumed`` (ADR-009 item 2).

    The resume path calls this instead of setting gateway internals itself. Layers that have
    neither attribute (test doubles) are left alone."""
    seen: set[int] = set()
    layer = gw
    while layer is not None and id(layer) not in seen:
        seen.add(id(layer))
        seq = layer.__dict__.get("_seq") if hasattr(layer, "__dict__") else None
        if isinstance(seq, int) and not isinstance(seq, bool):
            layer._seq = max(seq, int(last_call_number))
        log = getattr(layer, "log", None)
        if isinstance(log, LLMCallLog) and resumed_phase is not None:
            log.resumed_phases.add(str(resumed_phase.value if isinstance(resumed_phase, PhaseName)
                                       else resumed_phase))
        layer = getattr(layer, "inner", None)
