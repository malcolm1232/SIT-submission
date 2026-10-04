"""Second :class:`~sit_review_agent.llm.gateway.LLMGateway` backend: headless Claude Code (ADR-010).

:class:`ClaudeCodeGateway` runs ``claude -p`` once per :meth:`ClaudeCodeGateway.call`, so model calls
bill to the Claude subscription (laptop) or Claude Code cloud credits instead of an API key. The
command contract was verified in a cloud session (Claude Code 2.1.287; ADR-010):

* every CLI tool, MCP server, slash command, CLAUDE.md and attachment is switched off, and the
  phase's system prompt replaces Claude Code's (about 1.5k tokens of overhead instead of 31k);
* ``--bare`` is never passed (it breaks host-managed auth in cloud sessions) and
  ``--no-session-persistence`` is never passed (it breaks ``--resume``);
* the user prompt goes to stdin (argv strings are capped at 128 KiB on Linux);
* a conversation is a chain of CLI sessions: ``--session-id <uuid>`` on its first call, then
  ``--resume <last good uuid> --fork-session --session-id <new uuid>`` on every later attempt, always
  from the same ``cwd`` (the run directory) so the CLI finds the transcript. Forking keeps failed
  attempts (a killed ``--resume`` leaves its user turn in the transcript) out of the history;
* ``total_cost_usd`` and ``modelUsage`` are cumulative over a session (a fork inherits them), so
  cost and served model are computed as per-call deltas; ``usage`` is per invocation;
* structured output always goes through ``--json-schema``. Native ``tool_use`` is impossible with
  every CLI tool off, so when a request carries ``tools`` the gateway renders them into the system
  prompt (:func:`render_tool_catalogue`) and asks for an envelope
  ``{"tool_calls": [{id, name, input}], "final": <schema> | null}``, which it maps back onto
  ``tool_use`` / ``end_turn`` results. Phases see the same :class:`LLMResult` as with the native
  backend; ``tool_result`` blocks they send back are rendered as text.

Native PDF document blocks cannot be sent through the CLI: they are dropped (logged with
``pdf_dropped``) and the canonical text carries the document. :attr:`ClaudeCodeGateway.native_pdf`
is ``False`` so callers can skip building the PDF block (``backend.supports_native_pdf``).

Streamed output (latency redesign W1, ADR-012 draft; flags checked against ``claude --help`` of
Claude Code 2.1.288): every call runs with ``--output-format stream-json --verbose
--include-partial-messages`` and :func:`subprocess_runner` hands each event line to a
:class:`~sit_review_agent.llm.partial.StreamParser` as it arrives. The answer is the last ``result``
event, the same object ``--output-format json`` printed, so every error is raised on the same
condition as before. While the call streams, the gateway's :class:`~sit_review_agent.progress.CallTracker`
shows its thinking-token estimate or its finished items, and each finished item of the answer is
shown as a draft. An attempt cut by the run deadline or a stage limit raises
:class:`~sit_review_agent.errors.LLMDeadlineError` with the finished items (``partial``) and an
estimated usage; its ``llm.jsonl`` entry keeps ``usage: null`` with ``usage_unrecorded`` and logs the
estimate apart as ``estimated_usage`` (``estimated: true``) with ``salvaged_items`` and
``partial``. The JSON output mode is not used by the gateway any more; a single JSON object
on stdout (``--output-format json``, as the harness judges still run it) is still read.

First complete answer (measured on the 4 Oct 2026 rehearsal, ``docs/live_runs/sit_sample_ui_2``):
``--json-schema`` makes the CLI check each ``StructuredOutput`` call against the schema itself; when
its check rejects a complete answer it returns the rejection as the tool result and the model writes
the whole answer again in a new API turn (3 CLI turns instead of 2, the second turn reading the first
from the cache). Three of six assess shards did this; the two that finished spent 84 and 91 s on
the repeat. The gateway therefore
checks every complete answer block as it closes with the checks of a finished call; when the CLI
starts another API message after an answer the gateway accepts, the call ends there (the runner
kills ``claude -p``) and that answer is used, with the usage measured from the streamed messages
(``ended_at_first_answer`` in ``llm.jsonl``; the cost is at list prices, ``cost_basis: list_price``).
A call with tools (research, the one conversation that resumes) is never ended early: its next call
would resume a session that ends in the CLI's rejection of the envelope the gateway took.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import copy
import inspect
import json
import os
import random
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from sit_review_agent.clock import Clock, SystemClock, isoformat_z
from sit_review_agent.config import EffectiveConfig
from sit_review_agent.errors import (
    ConfigError,
    LLMAuthError,
    LLMBadRequestError,
    LLMConnectionError,
    LLMDeadlineError,
    LLMError,
    LLMOverloadedError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMTruncatedError,
    LLMUnavailableError,
)
from sit_review_agent.hashing import sha256_json, sha256_text
from sit_review_agent.llm.gateway import (
    EffortGuard,
    LLMAttempt,
    LLMCallLog,
    LLMRequest,
    LLMResult,
    ToolUse,
    Usage,
    assess_shard_index,
    billed,
    log_unsent,
    request_sha256,
    unrecorded_usage,
)
from sit_review_agent.llm.partial import RepeatedAnswer, StreamParser, parse_cli_stdout
from sit_review_agent.llm.runtime import (
    FirstCallNetwork,
    RuntimeLimits,
    announce_bound,
    attempt_timeout,
    check_context,
    retry_allowed,
)
from sit_review_agent.models import FallbackEvent
from sit_review_agent.progress import CallTracker, NullProgress, ProgressSink, draft_event, draft_line, emit_event
from sit_review_agent.rundir import RunDir

#: Longest ``--system-prompt`` / ``--json-schema`` value accepted (Linux caps one argv string at 128 KiB).
MAX_ARGV_TEXT_CHARS = 100_000
#: Model passed to ``--fallback-model`` when ``allow_fallback`` is set (REPRODUCIBILITY §3 expects
#: ``claude-opus-5`` as the first fallback target).
CLI_FALLBACK_MODEL = "claude-opus-5"
#: Flags that must never reach the CLI (ADR-010, verified).
FORBIDDEN_FLAGS = frozenset({"--bare", "--no-session-persistence"})
#: Output flags of every call (ADR-012 draft): the event stream with the answer's partial JSON.
#: ``--verbose`` is required by ``stream-json`` in print mode; ``--include-partial-messages`` adds
#: the ``stream_event`` lines (``input_json_delta``, ``thinking_tokens`` estimates).
STREAM_FLAGS = ("--output-format", "stream-json", "--verbose", "--include-partial-messages")
#: Bytes read from the child's stdout at a time (the ``result`` event of a long answer is one line of
#: several hundred kilobytes, above asyncio's 64 KiB line limit, so lines are split here).
READ_CHUNK = 65_536
#: Removed from the child environment unless ``claude_code.inherit_api_key`` (billing, ADR-010).
API_KEY_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
PREFLIGHT_TIMEOUT_S = 30.0
BACKEND = "claude_code"

#: Schema used when a request has no ``output_schema``: the answer is ``{"text": ...}``.
TEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class CompletedRun:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[..., Awaitable[CompletedRun]]
"""``(argv, stdin, env, cwd, timeout_s)`` -> :class:`CompletedRun`; a runner that also takes the
keyword ``on_line`` gets each stdout line as it arrives (:func:`subprocess_runner` does)."""


class StreamTimeout(TimeoutError):
    """A runner's timeout that keeps what the child wrote before it was killed."""

    def __init__(self, *, stdout: str, stderr: str) -> None:
        super().__init__("claude -p was killed at its timeout")
        self.stdout = stdout
        self.stderr = stderr


async def subprocess_runner(argv: list[str], stdin: str, env: dict[str, str], cwd: Path, timeout_s: float, *,
                            on_line: Callable[[str], None] | None = None) -> CompletedRun:
    """Default runner: ``asyncio.create_subprocess_exec``, prompt on stdin, stdout read as it
    arrives (each complete line goes to ``on_line``; the last line is passed on at exit even
    without a newline), killed on timeout or cancellation. Raises :class:`StreamTimeout` (a
    ``TimeoutError`` carrying the stdout read so far) on timeout and ``OSError`` if the executable
    is missing."""
    proc = await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=env, cwd=str(cwd))
    out: list[str] = []
    err: list[bytes] = []
    pending = ""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")

    async def feed_stdin() -> None:
        assert proc.stdin is not None
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            proc.stdin.write(stdin.encode("utf-8"))
            await proc.stdin.drain()
        with contextlib.suppress(Exception):
            proc.stdin.close()

    async def read_stdout() -> None:
        nonlocal pending
        assert proc.stdout is not None
        while True:
            chunk = await proc.stdout.read(READ_CHUNK)
            if not chunk:
                break
            text = decoder.decode(chunk)
            out.append(text)
            if on_line is not None:
                *lines, pending = (pending + text).split("\n")
                for line in lines:
                    on_line(line)
        tail = decoder.decode(b"", final=True)
        out.append(tail)
        if on_line is not None and (pending + tail):
            on_line(pending + tail)
            pending = ""

    async def read_stderr() -> None:
        assert proc.stderr is not None
        err.append(await proc.stderr.read())

    async def run() -> int:
        await asyncio.gather(feed_stdin(), read_stdout(), read_stderr())
        return await proc.wait()

    try:
        code = await asyncio.wait_for(run(), timeout_s)
    except TimeoutError:
        await _kill(proc)
        raise StreamTimeout(stdout="".join(out), stderr=b"".join(err).decode("utf-8", "replace")) from None
    except BaseException:
        await _kill(proc)
        raise
    return CompletedRun(returncode=code, stdout="".join(out), stderr=b"".join(err).decode("utf-8", "replace"))


async def _kill(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()


def _takes_on_line(runner: Any) -> bool:
    """Whether ``runner`` accepts the ``on_line`` keyword (live lines); injected test runners may not."""
    try:
        params = inspect.signature(runner).parameters
    except (TypeError, ValueError):
        return False
    return "on_line" in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


# ------------------------------------------------------------------------------ schemas


def _close_objects(node: Any) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" and ("properties" in node or "additionalProperties" not in node):
            node["additionalProperties"] = False
        for v in node.values():
            _close_objects(v)
    elif isinstance(node, list):
        for v in node:
            _close_objects(v)


def _schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """``model.model_json_schema()`` with ``additionalProperties: false`` on every object that
    declares properties (or says nothing about extra keys). ``$defs``/``$ref`` are kept; the CLI
    accepts them. Explicit map types (``dict[str, X]``) keep their ``additionalProperties``."""
    schema = model.model_json_schema()
    _close_objects(schema)
    return schema


def _output_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The schema sent for ``model``: workstream A's ``llm_facing_schema`` once it exists, else
    :func:`_schema_for`."""
    from sit_review_agent.llm import outputs

    try:
        return outputs.llm_facing_schema(model)
    except NotImplementedError:
        return _schema_for(model)


def envelope_schema(final_schema: dict[str, Any]) -> dict[str, Any]:
    """The tool-calling envelope. ``$defs`` of ``final_schema`` are hoisted to the root so that
    its ``#/$defs/...`` references still resolve."""
    inner = dict(final_schema)
    defs = inner.pop("$defs", None)
    env: dict[str, Any] = {
        "type": "object",
        "properties": {
            "tool_calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "name": {"type": "string"},
                                   "input": {"type": "object"}},
                    "required": ["id", "name", "input"],
                    "additionalProperties": False,
                },
            },
            "final": {"anyOf": [{"type": "null"}, inner]},
        },
        "required": ["tool_calls", "final"],
        "additionalProperties": False,
    }
    if defs:
        env["$defs"] = defs
    return env


def render_tool_catalogue(tools: list[dict[str, Any]]) -> str:
    """System-prompt section describing ``tools`` and the envelope protocol. Byte-stable: the
    same tools always render to the same text (no timestamps, sorted JSON keys)."""
    lines = [
        "# Tools available in this phase",
        "",
        "These tools are NOT functions you can invoke in this session: a direct call to them fails with "
        "\"No such tool available\". The only function you can invoke is the one that returns your structured "
        "answer, and that answer is how you call tools. To call tools, return the structured answer with "
        "`tool_calls` listing each call as {\"id\", \"name\", \"input\"} and `final: null`; the caller runs them. "
        "Use ids `call-0001`, `call-0002`, ... and keep numbering across the conversation; several calls in one "
        "answer are fine. The results come back in the next user turn as `[tool result <id>]` sections. When "
        "you are done, answer with `tool_calls: []` and the final object in `final`.",
    ]
    for t in tools:
        schema = json.dumps(t.get("input_schema") or {"type": "object"}, sort_keys=True, ensure_ascii=False)
        lines += ["", f"## {t.get('name', '')}", "", str(t.get("description") or "").strip(), "",
                  f"Input schema: {schema}"]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------ gateway


@dataclass
class _Conversation:
    """Gateway-side state of one ``conversation_id``.

    ``session_uuid`` is the CLI session of the last *successful* call. Every later call resumes it
    with ``--fork-session`` into a fresh session id, so a failed attempt (timeout kill, refusal,
    truncation, schema error, API error) never leaves its user turn or answer in the transcript the
    next attempt continues from (verified: a killed ``--resume`` call leaves its user turn behind).
    """

    session_uuid: str | None = None
    sent_message_count: int = 0
    produced: list[list[dict[str, Any]]] = field(default_factory=list)   # assistant contents returned
    produced_at: list[int] = field(default_factory=list)                 # message index each must take
    prefix_sha256: str | None = None            # hash of messages[:sent_message_count]
    # The CLI reports total_cost_usd and modelUsage cumulatively over the session (and a fork
    # inherits its parent's totals), so per-call figures are deltas against the last good session.
    cost_seen: float = 0.0
    model_usage_seen: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def started(self) -> bool:
        return self.session_uuid is not None


class _Unsent(Exception):
    """Internal: ``error`` ends the call before attempt ``attempt`` was made (logged ``sent: false``)."""

    def __init__(self, error: LLMError, attempt: int = 0) -> None:
        super().__init__(str(error))
        self.error = error
        self.attempt = attempt


class _AttemptFailed(Exception):
    """Internal: one attempt failed with ``error``; ``retry`` says whether the policy retries it.
    ``unrecorded`` names why a ``claude -p`` that ran left no usage report (a
    :data:`~sit_review_agent.llm.gateway.USAGE_UNRECORDED_REASONS` key); ``None`` when ``out``
    carries the usage or the process never started (nothing was spent)."""

    def __init__(self, error: LLMError, retry: bool, out: dict[str, Any] | None = None,
                 unrecorded: str | None = None, stream: StreamParser | None = None) -> None:
        super().__init__(str(error))
        self.error = error
        self.retry = retry
        self.out = out
        self.unrecorded = unrecorded
        self.stream = stream            # what the attempt streamed before it ended (estimate, salvage)


_AUTH_MARKERS = ("authentication", "invalid api key", "/login", "oauth token", "not logged in", "login expired")
_BAD_REQUEST_MARKERS = ("invalid_request_error", "prompt is too long", "credit balance is too low")
#: Error text of a connection-type failure (robustness NET-02). How ``claude -p`` words an offline
#: network is UNVERIFIED; these are the usual Node / undici / fetch messages.
_CONNECTION_MARKERS = ("connection error", "unable to connect", "could not connect", "econnrefused", "econnreset",
                       "enotfound", "eai_again", "getaddrinfo", "enetunreach", "ehostunreach", "network is unreachable",
                       "fetch failed", "socket hang up", "connect etimedout", "no internet", "offline")
#: How ``claude -p`` reports an answer that hit ``CLAUDE_CODE_MAX_OUTPUT_TOKENS``: not as
#: ``stop_reason: max_tokens`` but as an error result ("API Error: Claude's response exceeded the
#: 256 output token maximum. To configure this behavior, set the CLAUDE_CODE_MAX_OUTPUT_TOKENS
#: environment variable."), after its own recovery turns. Observed 2026-10-03 with Claude Code
#: 2.1.287 on Haiku at a cap of 256 (4 turns, 1,024 output tokens billed).
_OUTPUT_CAP_RE = re.compile(r"exceeded the [\d,._]+ output token maximum", re.IGNORECASE)


def _classify(text: str, *, call_id: str, phase: str) -> tuple[LLMError, bool]:
    """Typed error for the CLI's error text, and whether the retry policy retries it. Auth and
    bad-request errors are never retried (gateway contract item 2)."""
    t = text.lower()
    short = text[:500]
    if any(m in t for m in _AUTH_MARKERS) or re.search(r"\b40[13]\b", t):
        return LLMAuthError("Claude Code reported an authentication error; check the Claude Code login / host "
                            "credentials (run `claude` interactively once)", call_id=call_id, phase=phase), False
    if any(m in t for m in _BAD_REQUEST_MARKERS) or re.search(r"\b400\b", t):
        return LLMBadRequestError(f"Claude Code request rejected: {short}", call_id=call_id, phase=phase), False
    if "rate limit" in t or "usage limit" in t or re.search(r"\b429\b", t):
        return LLMRateLimitError(f"Claude Code rate/usage limit: {short}", retry_after_s=None, call_id=call_id,
                                 phase=phase), True
    if "overloaded" in t or re.search(r"\b(529|503)\b", t):
        return LLMOverloadedError(f"model overloaded: {short}", call_id=call_id, phase=phase), True
    if any(m in t for m in _CONNECTION_MARKERS):
        return LLMConnectionError(f"Claude Code could not reach the model API: {short}", call_id=call_id,
                                  phase=phase), True
    if "timed out" in t or "timeout" in t:
        return LLMTimeoutError(f"Claude Code timed out: {short}", call_id=call_id, phase=phase), True
    return LLMUnavailableError(f"Claude Code error: {short}", call_id=call_id, phase=phase), True


def _usage_of(out: dict[str, Any]) -> Usage:
    u = out.get("usage") or {}

    def n(key: str) -> int:
        v = u.get(key)
        return int(v) if isinstance(v, int | float) else 0

    return Usage(n("input_tokens"), n("output_tokens"), n("cache_creation_input_tokens"),
                 n("cache_read_input_tokens"))


_MODEL_USAGE_COUNTERS = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")


def _model_counters(out: dict[str, Any]) -> dict[str, dict[str, float]]:
    """``modelUsage`` token counters per model (cumulative over the CLI session)."""
    mu = out.get("modelUsage")
    if not isinstance(mu, dict):
        return {}
    res: dict[str, dict[str, float]] = {}
    for k, v in mu.items():
        v = v if isinstance(v, dict) else {}
        res[str(k)] = {c: float(v[c]) if isinstance(v.get(c), int | float) else 0.0 for c in _MODEL_USAGE_COUNTERS}
    return res


def _error_text(out: dict[str, Any]) -> str:
    """Error text of an ``is_error`` result: ``result`` (API errors) plus ``errors`` (the
    ``error_*`` subtypes carry no ``result``, only ``errors: [str]``)."""
    parts = [str(out["result"])] if out.get("result") else []
    errs = out.get("errors")
    if isinstance(errs, list):
        parts += [str(e) for e in errs if e]
    return "; ".join(parts) or str(out.get("subtype") or "")


class ClaudeCodeGateway:
    """:class:`LLMGateway` over headless Claude Code (``claude -p``), one subprocess per call.

    Construction never runs the CLI. ``runner`` may be injected (tests); it receives
    ``(argv, stdin, env, cwd, timeout_s)`` and returns a :class:`CompletedRun`, raising
    ``TimeoutError`` on timeout.
    """

    #: The CLI cannot take native PDF document blocks; callers send canonical text only.
    native_pdf: bool = False
    #: Run deadline and context guard (``llm.runtime.attach_runtime``); ``None`` = no run limits.
    runtime: RuntimeLimits | None = None

    def __init__(self, config: EffectiveConfig, run_dir: RunDir, *, clock: Clock | None = None,
                 progress: ProgressSink | None = None, runner: Runner | None = None) -> None:
        self.config = config
        self.run_dir = run_dir
        self.clock = clock or SystemClock()
        self.progress = progress
        self.runner: Runner = runner or subprocess_runner
        self._runner_streams = _takes_on_line(self.runner)
        #: Open calls and their status line (design section 4); its ticker runs only with a progress sink.
        self.tracker = CallTracker(progress or NullProgress(), self.clock)
        cc = config.agent.claude_code
        bad = sorted(FORBIDDEN_FLAGS & set(cc.extra_args))
        if bad:
            raise ConfigError(f"claude_code.extra_args must not contain {bad} (ADR-010)")
        self.executable = cc.executable
        self.extra_args = list(cc.extra_args)
        self.max_budget_usd_per_call = cc.max_budget_usd_per_call
        self.inherit_api_key = cc.inherit_api_key
        self.model = config.agent.model
        self.allow_fallback = config.agent.allow_fallback
        self.max_retries = config.agent.llm.max_retries
        self.timeout_s = config.agent.llm.timeout_s
        self.backoff_base_s = config.agent.llm.backoff_base_s
        self.backoff_max_s = config.agent.llm.backoff_max_s
        self.log = LLMCallLog(run_dir, secret_env=(config.tools.auth_env,))
        self._guard = EffortGuard()
        self._conversations: dict[str, _Conversation] = {}
        self._usage = Usage()
        self._cost = 0.0
        self._served: set[str] = set()
        self._fallbacks: list[FallbackEvent] = []
        self._refusals: list[dict[str, Any]] = []
        self._issued_tool_ids: set[str] = set()
        self._tool_id_alias: dict[str, str] = {}     # issued id -> the id the model wrote
        self._tool_seq = 0
        self._seq = 0
        self._net = FirstCallNetwork(config.agent.llm.first_call_network_window_s)
        self._rng = random.Random()
        self._spent: dict[str, Usage] = {}            # call ID -> usage reported by its failed attempts

    # ---------------------------------------------------------------- protocol accessors

    def usage_total(self) -> Usage:
        return self._usage

    def served_models(self) -> set[str]:
        return set(self._served)

    def fallback_events(self) -> list[FallbackEvent]:
        return list(self._fallbacks)

    def refusals(self) -> list[dict[str, Any]]:
        return list(self._refusals)

    @property
    def cost_total_usd(self) -> float:
        """Sum of the CLI's ``total_cost_usd`` (a client-side list-price estimate, not the bill)."""
        return self._cost

    @property
    def cwd(self) -> Path:
        return self.run_dir.root

    def next_call_id(self) -> str:
        self._seq += 1
        return f"llm-{self._seq:04d}"

    # ---------------------------------------------------------------- building blocks

    def env(self, request: LLMRequest) -> dict[str, str]:
        env = dict(os.environ)
        if not self.inherit_api_key:
            # An API key in the environment would make `claude -p` bill that key instead of the
            # subscription / cloud credits (ADR-010). Only the names are ever mentioned, never values.
            for name in API_KEY_ENV_VARS:
                env.pop(name, None)
        env.update({"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_ATTACHMENTS": "1",
                    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(request.max_tokens)})
        return env

    def system_text(self, request: LLMRequest) -> str:
        if not request.tools:
            return request.system
        return request.system.rstrip("\n") + "\n\n" + render_tool_catalogue(request.tools)

    def schema(self, request: LLMRequest) -> dict[str, Any]:
        final = _output_schema(request.output_schema) if request.output_schema is not None else dict(TEXT_SCHEMA)
        return envelope_schema(final) if request.tools else final

    def build_argv(self, request: LLMRequest, *, system_text: str, schema_json: str, session_uuid: str,
                   resume_from: str | None = None) -> list[str]:
        """``session_uuid`` is the id this attempt's transcript gets. With ``resume_from`` the call
        continues that session through ``--resume <id> --fork-session``, leaving it untouched."""
        resume = ["--resume", resume_from, "--fork-session"] if resume_from is not None else []
        argv = [self.executable, "-p", "--model", self.model, "--system-prompt", system_text,
                "--tools", "", "--strict-mcp-config", "--disallowedTools", "mcp__*", "--disable-slash-commands",
                *STREAM_FLAGS, "--effort", request.effort, "--json-schema", schema_json,
                *resume, "--session-id", session_uuid]
        if self.allow_fallback:
            argv += ["--fallback-model", CLI_FALLBACK_MODEL]
        if self.max_budget_usd_per_call is not None:
            argv += ["--max-budget-usd", f"{self.max_budget_usd_per_call:g}"]
        argv += self.extra_args
        return argv

    def _render_block(self, block: Any) -> tuple[str, bool]:
        """One user content block as prompt text; the flag is true for a dropped PDF block."""
        if isinstance(block, str):
            return block, False
        if not isinstance(block, dict):
            return str(block), False
        kind = block.get("type")
        if kind == "text":
            return str(block.get("text", "")), False
        if kind == "document":
            src = block.get("source") or {}
            media = src.get("media_type", "unknown")
            data = src.get("data")
            digest = sha256_text(data) if isinstance(data, str) else "none"
            return f"[document omitted: {media}, sha256:{digest}]", True
        if kind == "tool_result":
            tid = str(block.get("tool_use_id", ""))
            alias = self._tool_id_alias.get(tid)
            head = f"[tool result {tid}]" if alias is None else f"[tool result {tid} (your id {alias})]"
            content = block.get("content", "")
            if isinstance(content, list):
                body = "\n".join(str(b.get("text", "")) for b in content
                                 if isinstance(b, dict) and b.get("type") == "text")
            else:
                body = str(content)
            parts = [head, body] + (["[is_error]"] if block.get("is_error") else [])
            return "\n".join(parts), False
        return f"[{kind} block omitted]", False

    def render_user_turns(self, turns: list[dict[str, Any]]) -> tuple[str, bool]:
        """The stdin prompt for the new user turns, and whether a PDF block was dropped."""
        rendered: list[str] = []
        dropped = False
        for turn in turns:
            content = turn.get("content", "")
            blocks = content if isinstance(content, list) else [content]
            parts: list[str] = []
            for b in blocks:
                text, pdf = self._render_block(b)
                dropped = dropped or pdf
                parts.append(text)
            rendered.append("\n\n".join(parts))
        return "\n\n".join(rendered), dropped

    def _new_turns(self, request: LLMRequest, conv: _Conversation) -> list[dict[str, Any]]:
        """Validate append-only history and return the user turns not yet sent to the CLI."""
        msgs = request.messages
        cid = request.conversation_id

        def bad(msg: str) -> LLMBadRequestError:
            return LLMBadRequestError(f"conversation {cid}: {msg}", phase=request.phase.value)

        if len(msgs) < conv.sent_message_count:
            raise bad(f"history shrank from {conv.sent_message_count} to {len(msgs)} messages (must be append-only)")
        if conv.prefix_sha256 is not None and sha256_json(msgs[:conv.sent_message_count]) != conv.prefix_sha256:
            raise bad("earlier messages were edited (history must be append-only)")
        roles = {m.get("role") for m in msgs}
        if not roles <= {"user", "assistant"}:
            raise bad(f"unsupported message roles {sorted(map(str, roles - {'user', 'assistant'}))}")
        assistant = [m for m in msgs if m.get("role") == "assistant"]
        if len(assistant) != len(conv.produced):
            raise bad(f"{len(assistant)} assistant turns in history but this gateway produced {len(conv.produced)} "
                      "(history must be append-only; assistant turns come only from this gateway)")
        for i, (m, mine) in enumerate(zip(assistant, conv.produced, strict=True)):
            if m.get("content") != mine:
                raise bad(f"assistant turn {i + 1} differs from the one this gateway returned")
        for i, pos in enumerate(conv.produced_at):
            if pos >= len(msgs) or msgs[pos].get("role") != "assistant":
                raise bad(f"assistant turn {i + 1} must be message {pos + 1}, right after the turns it answered "
                          "(history must be append-only)")
        new_user = [m for m in msgs[conv.sent_message_count:] if m.get("role") == "user"]
        if not new_user:
            raise bad("no new user turn to send")
        return new_user

    def _issue_tool_id(self, model_id: str) -> str:
        if model_id and model_id not in self._issued_tool_ids:
            self._issued_tool_ids.add(model_id)
            return model_id
        while True:
            self._tool_seq += 1
            cand = f"call-{self._tool_seq:04d}"
            if cand not in self._issued_tool_ids:
                self._issued_tool_ids.add(cand)
                if model_id:
                    self._tool_id_alias[cand] = model_id
                return cand

    def _call_model_usage(self, out: dict[str, Any], conv: _Conversation) -> dict[str, dict[str, float]]:
        """Per-model counters spent by this call only: ``modelUsage`` minus the last good session's
        totals (``modelUsage`` is cumulative over a session and inherited by a fork)."""
        res: dict[str, dict[str, float]] = {}
        for k, now in _model_counters(out).items():
            seen = conv.model_usage_seen.get(k, {})
            delta = {c: now[c] - seen.get(c, 0.0) for c in _MODEL_USAGE_COUNTERS}
            if any(v > 0 for v in delta.values()):
                res[k] = delta
        return res

    def _served_model(self, call_usage: dict[str, dict[str, float]]) -> str:
        """The model that served this call: the requested one if it did any work, else the one
        with the most output tokens in this call."""
        if not call_usage:
            return self.model
        for k in call_usage:
            if k == self.model or k.startswith(self.model):
                return self.model if k == self.model else k
        return max(call_usage, key=lambda k: call_usage[k]["outputTokens"])

    def _backoff(self, attempt: int) -> float:
        delay = min(self.backoff_max_s, self.backoff_base_s * (2 ** attempt))
        return delay * (0.5 + 0.5 * self._rng.random())

    # ---------------------------------------------------------------- the call

    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        """One logical call (one ``claude -p`` per attempt) under the retry policy and the run
        limits (``llm.runtime``): the request's size is checked before anything runs (LLM-10; PDF
        blocks are dropped here, so they do not count), each attempt's timeout is bounded by the run
        deadline and a cut attempt is not retried (LLM-05), and connection errors on the first call
        of the run are retried only within ``llm.first_call_network_window_s`` (NET-02)."""
        self._guard.check(request)
        call_id = self.next_call_id()
        try:
            try:
                return await self._call(request, call_id)
            except _Unsent as u:
                u.error.call_id = u.error.call_id or call_id
                log_unsent(self.log, request, call_id, u.error, attempt=u.attempt, backend=BACKEND)
                raise u.error from None
        except LLMError as exc:
            billed(exc, self._spent.get(call_id))     # what the failed attempts of this call were billed for
            raise
        finally:
            self._spent.pop(call_id, None)

    async def _call(self, request: LLMRequest, call_id: str) -> LLMResult[Any]:
        try:
            check_context(self.runtime, request, model=self.model, native_pdf=False)
        except LLMError as exc:
            raise _Unsent(exc) from None
        first = self._net.start_call()
        phase = request.phase.value
        conv = self._conversations.get(request.conversation_id)
        if conv is None:
            conv = _Conversation()
            self._conversations[request.conversation_id] = conv
        try:
            new_turns = self._new_turns(request, conv)
        except LLMError as exc:
            raise _Unsent(exc) from None
        prompt, pdf_dropped = self.render_user_turns(new_turns)

        system_text = self.system_text(request)
        schema_json = json.dumps(self.schema(request), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for label, value in (("system prompt", system_text), ("JSON schema", schema_json)):
            if len(value) > MAX_ARGV_TEXT_CHARS:
                raise _Unsent(LLMBadRequestError(f"{label} is {len(value)} characters; the Claude Code backend "
                                                 f"passes it on argv and accepts at most {MAX_ARGV_TEXT_CHARS}",
                                                 call_id=call_id, phase=phase))
        req_hash = request_sha256({"backend": BACKEND, "model": self.model, "system": request.system,
                                   "messages": request.messages, "tools": request.tools, "effort": request.effort,
                                   "max_tokens": request.max_tokens})
        prompt_hash = sha256_text(prompt)
        env = self.env(request)
        self.cwd.mkdir(parents=True, exist_ok=True)

        attempts: list[LLMAttempt] = []
        t_call = self.clock.monotonic()
        attempt = 0
        while True:
            # A fresh session id per attempt: a failed attempt may have created (or, resuming in
            # place, polluted) a transcript, so retries never reuse it (see _Conversation).
            try:
                timeout_s, cut = attempt_timeout(self.runtime, request.phase, self.timeout_s)
            except LLMDeadlineError as exc:
                raise _Unsent(exc, attempt) from None
            if cut:
                announce_bound(self.progress, self.runtime, request.phase, call_id, timeout_s)
            attempt_uuid = str(uuid.uuid4())
            argv = self.build_argv(request, system_text=system_text, schema_json=schema_json,
                                   session_uuid=attempt_uuid, resume_from=conv.session_uuid)
            logged_argv = [("sha256:" + sha256_text(a)) if i > 0 and argv[i - 1] in ("--system-prompt", "--json-schema")
                           else a for i, a in enumerate(argv)]
            started_at = isoformat_z(self.clock.now_utc())
            t0 = self.clock.monotonic()
            base_entry: dict[str, Any] = {
                "call_id": call_id, "phase": phase, "purpose": request.purpose,
                "conversation_id": request.conversation_id, "request_sha256": req_hash, "started_at": started_at,
                "backend": BACKEND, "cli_session_id": attempt_uuid, "cli_resumed_from": conv.session_uuid,
                "argv": logged_argv,
                "prompt_sha256": prompt_hash, "pdf_dropped": pdf_dropped, "attempt": attempt,
                "timeout_s": round(timeout_s, 3),
            }
            try:
                result = await self._attempt(request, conv, call_id, argv, prompt, env, base_entry,
                                             timeout_s=timeout_s, cut=cut)
            except (asyncio.CancelledError, KeyboardInterrupt):
                # The runner kills claude -p; whatever it spent was not reported.
                self.log.log({**base_entry, "model": self.model, "stop_reason": None, "outcome": "CancelledError",
                              "error": "interrupted during the attempt", **unrecorded_usage("interrupted"),
                              "content": [], "elapsed_s": self.clock.monotonic() - t0})
                raise
            except _AttemptFailed as fail:
                elapsed = self.clock.monotonic() - t0
                attempts.append(LLMAttempt(attempt=attempt, started_at=started_at, elapsed_s=elapsed,
                                           outcome=type(fail.error).__name__))
                self._log_failure(base_entry, fail, elapsed, conv)
                if not isinstance(fail.error, LLMConnectionError | LLMTimeoutError):
                    self._net.answer()          # the API answered (an error from it): the network is there
                if fail.retry and attempt < self.max_retries:
                    delay = self._backoff(attempt)
                    if first and self._net.give_up(fail.error, self.clock.monotonic() - t_call, delay):
                        raise self._net.error(fail.error, attempt + 1) from None
                    if not retry_allowed(self.runtime, request.phase, delay):
                        assert self.runtime is not None and self.runtime.deadline is not None
                        raise _Unsent(self.runtime.deadline.no_time(request.phase, after=type(fail.error).__name__,
                                                                    call_id=call_id), attempt + 1) from None
                    emit_event(self.progress, phase, f"{type(fail.error).__name__} on {call_id}; retry "
                                                     f"{attempt + 1}/{self.max_retries} in {delay:.0f} s", "warn",
                               event="call_retry", reason="transient", stage=phase, call_id=call_id,
                               error=type(fail.error).__name__, attempt=attempt + 1, retries=self.max_retries,
                               delay_s=delay)
                    await self.clock.sleep(delay)
                    attempt += 1
                    continue
                if first and not self._net.answered and isinstance(fail.error, LLMConnectionError):
                    raise self._net.error(fail.error, attempt + 1) from None
                raise fail.error from None
            self._net.answer()
            elapsed = self.clock.monotonic() - t0
            attempts.append(LLMAttempt(attempt=attempt, started_at=started_at, elapsed_s=elapsed, outcome="ok"))
            conv.session_uuid = attempt_uuid
            conv.cost_seen = result["cost_cumulative"]
            conv.model_usage_seen = result["model_usage_cumulative"]
            conv.sent_message_count = len(request.messages)
            conv.prefix_sha256 = sha256_json(request.messages)
            conv.produced.append(copy.deepcopy(result["content"]))
            conv.produced_at.append(len(request.messages))
            return LLMResult(call_id=call_id, phase=request.phase, conversation_id=request.conversation_id,
                             model=result["served"], stop_reason=result["stop_reason"],
                             content=copy.deepcopy(result["content"]), parsed=result["parsed"],
                             text=result["text"], tool_uses=result["tool_uses"], usage=result["usage"],
                             request_id=None, request_sha256=req_hash,
                             latency_s=self.clock.monotonic() - t_call, attempts=attempts,
                             fallback=result["fallback"], resumed=self.log.is_resumed(request.phase))

    def _log_failure(self, base: dict[str, Any], fail: _AttemptFailed, elapsed: float, conv: _Conversation) -> None:
        out = fail.out or {}
        u = _usage_of(out) if out else Usage()
        if out:                                       # a JSON result: the CLI reported what the attempt cost
            cid = str(base["call_id"])
            self._spent[cid] = self._spent[cid] + u if cid in self._spent else u
        spent: dict[str, Any] = {"usage": u.__dict__, "call_cost_usd": (
            max(0.0, float(out["total_cost_usd"]) - conv.cost_seen)
            if isinstance(out.get("total_cost_usd"), int | float) else None)}
        if not out and fail.unrecorded is not None:   # the CLI ran and was killed or crashed: unknown, not zero
            spent = unrecorded_usage(fail.unrecorded)
            spent.update(_estimate_fields(fail.stream))
        self.log.log({**base, "model": self._served_model(self._call_model_usage(out, conv)) if out else self.model,
                      "stop_reason": out.get("stop_reason"), "outcome": type(fail.error).__name__,
                      "error": str(fail.error)[:500], **spent, "content": [],
                      "num_turns": out.get("num_turns"), "total_cost_usd": out.get("total_cost_usd"),
                      "terminal_reason": out.get("terminal_reason"), "elapsed_s": elapsed})

    async def _run(self, argv: list[str], prompt: str, env: dict[str, str], phase: str,
                   call_id: str, timeout_s: float | None = None, stream: StreamParser | None = None) -> CompletedRun:
        """One ``claude -p``. With a streaming runner each line goes to ``stream`` as it arrives;
        otherwise the gateway reads stdout when the runner returns (or from :class:`StreamTimeout`)."""
        t = self.timeout_s if timeout_s is None else timeout_s
        kwargs: dict[str, Any] = {}
        if stream is not None and self._runner_streams:
            kwargs["on_line"] = stream.feed_line
        if self.progress is not None:
            self.tracker.open(call_id, phase)
        try:
            return await self.runner(argv, prompt, env, self.cwd, t, **kwargs)
        finally:
            if self.progress is not None:
                self.tracker.close(call_id)

    def _stream_parser(self, request: LLMRequest, call_id: str) -> StreamParser:
        """The parser of one attempt: the answer's root is ``final`` inside the tool envelope; each
        finished root-level item becomes a draft line and the tracker follows the counters."""
        phase = request.phase.value
        shard = assess_shard_index(request.conversation_id)

        def on_item(key: str, index: int, item: Any) -> None:
            if self.progress is not None and key != "tool_calls":
                # progress.jsonl gets the item's codes and a finding's title only (draft_event).
                public, fields = draft_event(key, index, item, call_id=call_id, phase=phase, shard=shard)
                emit_event(self.progress, phase, draft_line(key, index, item, call_id=call_id, phase=phase), "draft",
                           event="draft_item", public=public, data=fields)

        def on_event(p: StreamParser) -> None:
            self.tracker.update(call_id, thinking_tokens=p.thinking_tokens, items=p.item_count(),
                              chars=p.answer_chars)

        # Not with tools: a resumed research session would end in the CLI's rejection of the envelope taken.
        return StreamParser(root=("final",) if request.tools else (), on_item=on_item,
                            on_event=on_event if self.progress is not None else None,
                            accept=lambda data: self._usable(request, data),
                            stop_on_repeat=self._runner_streams and not request.tools)

    async def _attempt(self, request: LLMRequest, conv: _Conversation, call_id: str, argv: list[str], prompt: str,
                       env: dict[str, str], base_entry: dict[str, Any], *, timeout_s: float | None = None,
                       cut: bool = False) -> dict[str, Any]:
        phase = request.phase.value
        t = self.timeout_s if timeout_s is None else timeout_s
        t0 = self.clock.monotonic()
        stream = self._stream_parser(request, call_id)
        early = False
        try:
            run = await self._run(argv, prompt, env, phase, call_id, t, stream)
        except RepeatedAnswer:
            # The CLI rejected a complete answer this gateway accepts and the model began writing it
            # again; the runner killed claude -p and the accepted answer is the call's answer.
            early = True
            run = CompletedRun(returncode=0, stdout="", stderr="")
        except TimeoutError as exc:
            if not self._runner_streams:
                stream.feed_text(getattr(exc, "stdout", "") or "")
            if cut and self.runtime is not None and self.runtime.deadline is not None:
                # Salvage (design section 4): the items whose JSON closed before the cut, and an
                # estimate of what the killed attempt used (the CLI reports nothing for it).
                raise _AttemptFailed(self.runtime.deadline.cut(request.phase, t, call_id=call_id,
                                                               partial=stream.partial(),
                                                               partial_complete=stream.partial_complete(),
                                                               estimated_usage=stream.estimated_usage()),
                                     retry=False, unrecorded="deadline_cut", stream=stream) from None
            raise _AttemptFailed(LLMTimeoutError(f"claude -p exceeded {t:g} s", call_id=call_id,
                                                 phase=phase), retry=True, unrecorded="timeout_kill",
                                 stream=stream) from None
        except FileNotFoundError:
            raise _AttemptFailed(LLMAuthError(f"Claude Code executable {self.executable!r} not found; install "
                                              "Claude Code and log in (`claude --version`)", call_id=call_id,
                                              phase=phase), retry=False) from None
        except OSError as exc:
            raise _AttemptFailed(LLMUnavailableError(f"could not start claude -p: {exc}", call_id=call_id,
                                                     phase=phase), retry=True) from None
        if early:
            assert stream.accepted is not None
            found = _first_answer_result(stream)
        elif self._runner_streams:
            stream.flush()
            found, _ = parse_cli_stdout(run.stdout, stream)
        else:
            stream.feed_text(run.stdout)
            stream.flush()
            found, _ = parse_cli_stdout(run.stdout, stream)
        if found is None:
            raise _AttemptFailed(LLMUnavailableError(
                f"claude -p exited {run.returncode} without a JSON result; stderr: {run.stderr[:500]}",
                call_id=call_id, phase=phase), retry=True, unrecorded="process_fault", stream=stream)
        out = found

        # A JSON result means the CLI ran; account for what it spent even if the answer is unusable.
        # ``usage`` is per invocation; ``total_cost_usd`` and ``modelUsage`` are cumulative over the
        # session (verified with Claude Code 2.1.287), so those two are taken as deltas.
        usage = _usage_of(out)
        self._usage = self._usage + usage
        cost = out.get("total_cost_usd")
        cost_cumulative = float(cost) if isinstance(cost, int | float) else conv.cost_seen
        call_cost = max(0.0, cost_cumulative - conv.cost_seen)
        if early:                   # no result event: the cost of the measured usage at list prices
            call_cost = _list_price_usd(usage)
            cost_cumulative = conv.cost_seen + call_cost
        self._cost += call_cost
        call_usage = self._call_model_usage(out, conv)
        self._served.update(call_usage)
        served = self._served_model(call_usage)
        self._served.add(served)

        stop = out.get("stop_reason")
        if stop == "max_tokens":
            raise _AttemptFailed(LLMTruncatedError("output truncated at max_tokens", max_tokens=request.max_tokens,
                                                   call_id=call_id, phase=phase), retry=False, out=out)
        if stop == "refusal":
            self._refusals.append({"call_id": call_id, "stage": phase, "category": None})
            raise _AttemptFailed(LLMRefusalError("model declined", category=None, call_id=call_id, phase=phase),
                                 retry=False, out=out)
        if out.get("is_error"):
            subtype = out.get("subtype")
            if subtype == "error_max_budget_usd":
                raise _AttemptFailed(LLMUnavailableError(
                    f"claude -p hit --max-budget-usd {self.max_budget_usd_per_call}", call_id=call_id, phase=phase),
                    retry=False, out=out)
            if subtype == "error_max_structured_output_retries":
                # The CLI already re-asked the model for schema-valid output; like any schema
                # violation this is not retried (LLM-08).
                raise _AttemptFailed(LLMSchemaError(f"claude -p found no schema-valid output: {_error_text(out)[:500]}",
                                                    call_id=call_id, phase=phase), retry=False, out=out)
            text = _error_text(out)
            if _OUTPUT_CAP_RE.search(text):
                # Truncation, not an outage: never retried here at the same cap (each retry would
                # repeat the CLI's recovery turns); the phase decides (one wider call, LLM-07).
                raise _AttemptFailed(LLMTruncatedError(
                    f"output truncated at max_tokens (claude -p: {text[:200]})", max_tokens=request.max_tokens,
                    call_id=call_id, phase=phase), retry=False, out=out)
            err, retry = _classify(text, call_id=call_id, phase=phase)
            raise _AttemptFailed(err, retry=retry, out=out)

        fallback: FallbackEvent | None = None
        if self.allow_fallback and served != self.model:
            fallback = FallbackEvent(role=phase, from_model=self.model, to_model=served,
                                     reason=f"claude_code --fallback-model ({call_id})")
            self._fallbacks.append(fallback)

        try:
            parsed_out = self._interpret(request, out, call_id)
        except LLMSchemaError as err:
            raise _AttemptFailed(err, retry=False, out=out) from None
        result = {**parsed_out, "served": served, "usage": usage, "fallback": fallback,
                  "cost_cumulative": cost_cumulative,
                  "model_usage_cumulative": _model_counters(out) or conv.model_usage_seen}
        self.log.log({**base_entry, "model": served, "stop_reason": result["stop_reason"], "outcome": "ok",
                      "usage": usage.__dict__, "content": result["content"], "num_turns": out.get("num_turns"),
                      "total_cost_usd": out.get("total_cost_usd"), "call_cost_usd": call_cost,
                      "terminal_reason": out.get("terminal_reason"), "cli_stop_reason": stop,
                      **({"cli_answer_rejections": stream.rejections} if stream.rejections else {}),
                      **({"ended_at_first_answer": True, "complete_answers": len(stream.answers),
                          "cli_messages": stream.messages, "usage_basis": "stream_messages",
                          "cost_basis": "list_price"} if early else {}),
                      "elapsed_s": round(self.clock.monotonic() - t0, 3)})   # latency (robustness OPS-10)
        return result

    def _interpret(self, request: LLMRequest, out: dict[str, Any], call_id: str) -> dict[str, Any]:
        """Map the CLI's structured output onto ``stop_reason`` / ``content`` / ``parsed`` / ``text``."""
        phase = request.phase.value

        def schema_error(msg: str) -> LLMSchemaError:
            return LLMSchemaError(msg, call_id=call_id, phase=phase)

        data = out.get("structured_output")
        if data is None:
            try:
                data = json.loads(str(out.get("result") or ""))
            except ValueError:
                raise schema_error("claude -p returned no structured_output") from None
        return self._interpret_data(request, data, call_id)

    def _usable(self, request: LLMRequest, data: dict[str, Any]) -> bool:
        """Whether a complete streamed answer passes the same checks as the answer of a finished
        call (:meth:`_interpret_data`), without issuing tool-call ids."""
        try:
            self._interpret_data(request, data, "", issue_ids=False)
        except LLMSchemaError:
            return False
        return True

    def _interpret_data(self, request: LLMRequest, data: Any, call_id: str, *,
                        issue_ids: bool = True) -> dict[str, Any]:
        phase = request.phase.value

        def schema_error(msg: str) -> LLMSchemaError:
            return LLMSchemaError(msg, call_id=call_id, phase=phase)

        if not isinstance(data, dict):
            raise schema_error("structured output is not a JSON object")

        final: Any = data
        if request.tools:
            calls = data.get("tool_calls")
            if not isinstance(calls, list):
                raise schema_error("envelope has no tool_calls array")
            if calls:
                uses: list[ToolUse] = []
                for c in calls:
                    if not isinstance(c, dict) or not isinstance(c.get("name"), str) \
                            or not isinstance(c.get("input"), dict):
                        raise schema_error(f"malformed tool call in envelope: {str(c)[:200]}")
                    tid = str(c.get("id") or "")
                    uses.append(ToolUse(id=self._issue_tool_id(tid) if issue_ids else tid, name=c["name"],
                                        input=c["input"]))
                content = [{"type": "tool_use", "id": u.id, "name": u.name, "input": u.input} for u in uses]
                return {"stop_reason": "tool_use", "content": content, "parsed": None, "text": "",
                        "tool_uses": uses}
            final = data.get("final")
            if final is None:
                raise schema_error("envelope has neither tool_calls nor final")
            if not isinstance(final, dict):
                raise schema_error("envelope final is not a JSON object")

        parsed: BaseModel | None = None
        if request.output_schema is not None:
            try:
                parsed = request.output_schema.model_validate(final)
            except ValidationError as exc:
                raise schema_error(f"output does not match {request.output_schema.__name__}: {exc}") from exc
            text = parsed.model_dump_json()
        else:
            if not isinstance(final.get("text"), str):
                raise schema_error("text answer has no 'text' string")
            text = final["text"]
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}], "parsed": parsed,
                "text": text, "tool_uses": []}

    # ---------------------------------------------------------------- preflight

    async def preflight(self) -> None:
        """``claude --version`` through the runner (no model call). Raises :class:`LLMAuthError`."""
        hint = "install Claude Code and log in (check with `claude --version`)"
        self.cwd.mkdir(parents=True, exist_ok=True)
        try:
            run = await self.runner([self.executable, "--version"], "", dict(os.environ), self.cwd,
                                    PREFLIGHT_TIMEOUT_S)
        except (OSError, TimeoutError) as exc:
            raise LLMAuthError(f"Claude Code executable {self.executable!r} is not usable "
                               f"({type(exc).__name__}); {hint}") from None
        if run.returncode != 0:
            raise LLMAuthError(f"`{self.executable} --version` exited {run.returncode}; {hint}")


#: Number of CLI turns of a call that ends at its first complete answer, as ``claude -p`` counts a
#: call that ends normally: the answering API turn and the StructuredOutput tool result.
FIRST_ANSWER_TURNS = 2


def _first_answer_result(stream: StreamParser) -> dict[str, Any]:
    """The result object of a call ended at :class:`~sit_review_agent.llm.partial.RepeatedAnswer`:
    the accepted answer, the measured usage of the streamed API messages and the turn count of a
    call that ends there. The CLI never wrote its own ``result`` event, so there is no
    ``total_cost_usd`` or ``modelUsage``."""
    u = stream.accepted_usage()
    return {"type": "result", "subtype": "success", "is_error": False, "structured_output": stream.accepted,
            "stop_reason": "tool_use", "num_turns": FIRST_ANSWER_TURNS, "terminal_reason": "first_complete_answer",
            "usage": dict(u.__dict__)}


def _list_price_usd(usage: Usage) -> float:
    """``usage`` at the list prices the manifest uses for its estimates (``manifest.PRICE_TABLE``)."""
    from sit_review_agent.manifest import PRICE_TABLE

    p = PRICE_TABLE["usd_per_mtok"]
    return (usage.input_tokens * p["input"] + usage.cache_creation_input_tokens * p["cache_write"]
            + usage.cache_read_input_tokens * p["cache_read"] + usage.output_tokens * p["output"]) / 1e6


def _estimate_fields(stream: StreamParser | None) -> dict[str, Any]:
    """``llm.jsonl`` fields of an attempt that streamed but reported no usage: the estimate, kept
    apart from ``usage`` and marked estimated, and what was salvaged. The keys are the names of the
    error type (``LLMDeadlineError.estimated_usage`` and ``.partial``), which ``replay.recorded_error``
    maps back to the rebuilt error; ``salvaged_items`` is the count."""
    if stream is None:
        return {}
    fields: dict[str, Any] = {}
    est = stream.estimated_usage()
    if est is not None:
        fields["estimated_usage"] = {**est.__dict__, "estimated": True, "basis": stream.estimate_basis()}
    if stream.rejections:
        fields["cli_answer_rejections"] = stream.rejections
    partial = stream.partial()
    fields["salvaged_items"] = stream.salvaged_count()
    if partial is not None:
        fields["partial"] = partial
        if stream.partial_complete():
            fields["partial_complete"] = True
    return fields
