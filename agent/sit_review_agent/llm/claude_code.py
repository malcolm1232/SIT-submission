"""Second :class:`~sit_review_agent.llm.gateway.LLMGateway` backend: headless Claude Code (ADR-010).

:class:`ClaudeCodeGateway` runs ``claude -p`` once per :meth:`ClaudeCodeGateway.call`, so model calls
bill to the Claude subscription (laptop) or Claude Code cloud credits instead of an API key. The
command contract was verified in a cloud session (Claude Code 2.1.287; ADR-010):

* every CLI tool, MCP server, slash command, CLAUDE.md and attachment is switched off, and the
  phase's system prompt replaces Claude Code's (about 1.5k tokens of overhead instead of 31k);
* ``--bare`` is never passed (it breaks host-managed auth in cloud sessions) and
  ``--no-session-persistence`` is never passed (it breaks ``--resume``);
* the user prompt goes to stdin (argv strings are capped at 128 KiB on Linux);
* a conversation is one CLI session: ``--session-id <uuid>`` on its first call, ``--resume <uuid>``
  afterwards, always from the same ``cwd`` (the run directory) so the CLI finds the transcript;
* structured output always goes through ``--json-schema``. Native ``tool_use`` is impossible with
  every CLI tool off, so when a request carries ``tools`` the gateway renders them into the system
  prompt (:func:`render_tool_catalogue`) and asks for an envelope
  ``{"tool_calls": [{id, name, input}], "final": <schema> | null}``, which it maps back onto
  ``tool_use`` / ``end_turn`` results. Phases see the same :class:`LLMResult` as with the native
  backend; ``tool_result`` blocks they send back are rendered as text.

Native PDF document blocks cannot be sent through the CLI: they are dropped (logged with
``pdf_dropped``) and the canonical text carries the document. :attr:`ClaudeCodeGateway.native_pdf`
is ``False`` so callers can skip building the PDF block (``backend.supports_native_pdf``).
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import os
import random
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
    request_sha256,
)
from sit_review_agent.models import FallbackEvent
from sit_review_agent.progress import ProgressSink, heartbeat
from sit_review_agent.rundir import RunDir

#: Longest ``--system-prompt`` / ``--json-schema`` value accepted (Linux caps one argv string at 128 KiB).
MAX_ARGV_TEXT_CHARS = 100_000
#: Model passed to ``--fallback-model`` when ``allow_fallback`` is set (REPRODUCIBILITY §3 expects
#: ``claude-opus-5`` as the first fallback target).
CLI_FALLBACK_MODEL = "claude-opus-5"
#: Flags that must never reach the CLI (ADR-010, verified).
FORBIDDEN_FLAGS = frozenset({"--bare", "--no-session-persistence"})
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


Runner = Callable[[list[str], str, dict[str, str], Path, float], Awaitable[CompletedRun]]


async def subprocess_runner(argv: list[str], stdin: str, env: dict[str, str], cwd: Path,
                            timeout_s: float) -> CompletedRun:
    """Default runner: ``asyncio.create_subprocess_exec``, prompt on stdin, killed on timeout or
    cancellation. Raises ``TimeoutError`` on timeout and ``OSError`` if the executable is missing."""
    proc = await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=env, cwd=str(cwd))
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin.encode("utf-8")), timeout_s)
    except BaseException:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
        raise
    return CompletedRun(returncode=proc.returncode if proc.returncode is not None else -1,
                        stdout=out.decode("utf-8", "replace"), stderr=err.decode("utf-8", "replace"))


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
        "You cannot call these tools natively. To call tools, answer with `tool_calls` listing each call "
        "as {\"id\", \"name\", \"input\"} and `final: null`. Use ids `call-0001`, `call-0002`, ... and keep "
        "numbering across the conversation; several calls in one answer are fine. The results come back in "
        "the next user turn as `[tool result <id>]` sections. When you are done, answer with `tool_calls: []` "
        "and the final object in `final`.",
    ]
    for t in tools:
        schema = json.dumps(t.get("input_schema") or {"type": "object"}, sort_keys=True, ensure_ascii=False)
        lines += ["", f"## {t.get('name', '')}", "", str(t.get("description") or "").strip(), "",
                  f"Input schema: {schema}"]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------ gateway


@dataclass
class _Conversation:
    session_uuid: str
    sent_message_count: int = 0
    produced: list[list[dict[str, Any]]] = field(default_factory=list)   # assistant contents returned
    prefix_sha256: str | None = None            # hash of messages[:sent_message_count]
    started: bool = False                       # a CLI transcript is known to exist


class _AttemptFailed(Exception):
    """Internal: one attempt failed with ``error``; ``retry`` says whether the policy retries it."""

    def __init__(self, error: LLMError, retry: bool, out: dict[str, Any] | None = None) -> None:
        super().__init__(str(error))
        self.error = error
        self.retry = retry
        self.out = out


def _classify(text: str, *, call_id: str, phase: str) -> tuple[LLMError, bool]:
    t = text.lower()
    short = text[:500]
    if "authentication" in t:
        return LLMAuthError("Claude Code reported an authentication error; check the Claude Code login / host "
                            "credentials (run `claude` interactively once)", call_id=call_id, phase=phase), False
    if "rate limit" in t or "usage limit" in t or "429" in t:
        return LLMRateLimitError(f"Claude Code rate/usage limit: {short}", retry_after_s=None, call_id=call_id,
                                 phase=phase), True
    if "overloaded" in t or "529" in t or "503" in t:
        return LLMOverloadedError(f"model overloaded: {short}", call_id=call_id, phase=phase), True
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


class ClaudeCodeGateway:
    """:class:`LLMGateway` over headless Claude Code (``claude -p``), one subprocess per call.

    Construction never runs the CLI. ``runner`` may be injected (tests); it receives
    ``(argv, stdin, env, cwd, timeout_s)`` and returns a :class:`CompletedRun`, raising
    ``TimeoutError`` on timeout.
    """

    #: The CLI cannot take native PDF document blocks; callers send canonical text only.
    native_pdf: bool = False

    def __init__(self, config: EffectiveConfig, run_dir: RunDir, *, clock: Clock | None = None,
                 progress: ProgressSink | None = None, runner: Runner | None = None) -> None:
        self.config = config
        self.run_dir = run_dir
        self.clock = clock or SystemClock()
        self.progress = progress
        self.runner: Runner = runner or subprocess_runner
        cc = config.agent.claude_code
        bad = sorted(FORBIDDEN_FLAGS & set(cc.extra_args))
        if bad:
            raise ConfigError(f"claude_code.extra_args must not contain {bad} (ADR-010)")
        self.executable = cc.executable
        self.extra_args = list(cc.extra_args)
        self.max_budget_usd_per_call = cc.max_budget_usd_per_call
        self.model = config.agent.model
        self.allow_fallback = config.agent.allow_fallback
        self.max_retries = config.agent.llm.max_retries
        self.timeout_s = config.agent.llm.timeout_s
        self.backoff_base_s = config.agent.llm.backoff_base_s
        self.backoff_max_s = config.agent.llm.backoff_max_s
        self.log = LLMCallLog(run_dir)
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
        self._rng = random.Random()

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

    def build_argv(self, request: LLMRequest, *, system_text: str, schema_json: str, session_flag: str,
                   session_uuid: str) -> list[str]:
        argv = [self.executable, "-p", "--model", self.model, "--system-prompt", system_text,
                "--tools", "", "--strict-mcp-config", "--disallowedTools", "mcp__*", "--disable-slash-commands",
                "--output-format", "json", "--effort", request.effort, "--json-schema", schema_json,
                session_flag, session_uuid]
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

    def _served_model(self, out: dict[str, Any]) -> str:
        mu = out.get("modelUsage")
        if not isinstance(mu, dict) or not mu:
            return self.model
        for k in mu:
            if k == self.model or k.startswith(self.model):
                return self.model if k == self.model else k
        return max(mu, key=lambda k: (mu[k] or {}).get("outputTokens", 0) if isinstance(mu[k], dict) else 0)

    def _backoff(self, attempt: int) -> float:
        delay = min(self.backoff_max_s, self.backoff_base_s * (2 ** attempt))
        return delay * (0.5 + 0.5 * self._rng.random())

    # ---------------------------------------------------------------- the call

    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        self._guard.check(request)
        call_id = self.next_call_id()
        phase = request.phase.value
        conv = self._conversations.get(request.conversation_id)
        if conv is None:
            conv = _Conversation(session_uuid=str(uuid.uuid4()))
            self._conversations[request.conversation_id] = conv
        new_turns = self._new_turns(request, conv)
        prompt, pdf_dropped = self.render_user_turns(new_turns)

        system_text = self.system_text(request)
        schema_json = json.dumps(self.schema(request), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for label, value in (("system prompt", system_text), ("JSON schema", schema_json)):
            if len(value) > MAX_ARGV_TEXT_CHARS:
                raise LLMBadRequestError(f"{label} is {len(value)} characters; the Claude Code backend passes it "
                                         f"on argv and accepts at most {MAX_ARGV_TEXT_CHARS}",
                                         call_id=call_id, phase=phase)
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
            if not conv.started and attempt > 0:
                # The failed first attempt may or may not have created a transcript under the old
                # uuid; a fresh one avoids "session id already in use" (ADR-010 note in claude_code.py).
                conv.session_uuid = str(uuid.uuid4())
            flag = "--resume" if conv.started else "--session-id"
            argv = self.build_argv(request, system_text=system_text, schema_json=schema_json, session_flag=flag,
                                   session_uuid=conv.session_uuid)
            logged_argv = [("sha256:" + sha256_text(a)) if i > 0 and argv[i - 1] in ("--system-prompt", "--json-schema")
                           else a for i, a in enumerate(argv)]
            started_at = isoformat_z(self.clock.now_utc())
            t0 = self.clock.monotonic()
            base_entry: dict[str, Any] = {
                "call_id": call_id, "phase": phase, "purpose": request.purpose,
                "conversation_id": request.conversation_id, "request_sha256": req_hash, "started_at": started_at,
                "backend": BACKEND, "cli_session_id": conv.session_uuid, "argv": logged_argv,
                "prompt_sha256": prompt_hash, "pdf_dropped": pdf_dropped, "attempt": attempt,
            }
            try:
                result = await self._attempt(request, conv, call_id, argv, prompt, env, base_entry)
            except _AttemptFailed as fail:
                elapsed = self.clock.monotonic() - t0
                attempts.append(LLMAttempt(attempt=attempt, started_at=started_at, elapsed_s=elapsed,
                                           outcome=type(fail.error).__name__))
                self._log_failure(base_entry, fail, elapsed)
                if fail.retry and attempt < self.max_retries:
                    delay = self._backoff(attempt)
                    if self.progress is not None:
                        self.progress.emit(phase, f"{type(fail.error).__name__} on {call_id}; retry "
                                                  f"{attempt + 1}/{self.max_retries} in {delay:.0f} s", "warn")
                    await self.clock.sleep(delay)
                    attempt += 1
                    continue
                raise fail.error from None
            elapsed = self.clock.monotonic() - t0
            attempts.append(LLMAttempt(attempt=attempt, started_at=started_at, elapsed_s=elapsed, outcome="ok"))
            conv.sent_message_count = len(request.messages)
            conv.prefix_sha256 = sha256_json(request.messages)
            conv.produced.append(copy.deepcopy(result["content"]))
            return LLMResult(call_id=call_id, phase=request.phase, conversation_id=request.conversation_id,
                             model=result["served"], stop_reason=result["stop_reason"],
                             content=copy.deepcopy(result["content"]), parsed=result["parsed"],
                             text=result["text"], tool_uses=result["tool_uses"], usage=result["usage"],
                             request_id=None, request_sha256=req_hash,
                             latency_s=self.clock.monotonic() - t_call, attempts=attempts,
                             fallback=result["fallback"], resumed=False)

    def _log_failure(self, base: dict[str, Any], fail: _AttemptFailed, elapsed: float) -> None:
        out = fail.out or {}
        u = _usage_of(out) if out else Usage()
        self.log.log({**base, "model": self._served_model(out) if out else self.model,
                      "stop_reason": out.get("stop_reason"), "outcome": type(fail.error).__name__,
                      "error": str(fail.error)[:500], "usage": u.__dict__, "content": [],
                      "num_turns": out.get("num_turns"), "total_cost_usd": out.get("total_cost_usd"),
                      "terminal_reason": out.get("terminal_reason"), "elapsed_s": elapsed})

    async def _run(self, argv: list[str], prompt: str, env: dict[str, str], phase: str,
                   call_id: str) -> CompletedRun:
        if self.progress is None:
            return await self.runner(argv, prompt, env, self.cwd, self.timeout_s)
        async with heartbeat(self.progress, phase, lambda: f"waiting on claude -p ({call_id})", clock=self.clock):
            return await self.runner(argv, prompt, env, self.cwd, self.timeout_s)

    async def _attempt(self, request: LLMRequest, conv: _Conversation, call_id: str, argv: list[str], prompt: str,
                       env: dict[str, str], base_entry: dict[str, Any]) -> dict[str, Any]:
        phase = request.phase.value
        try:
            run = await self._run(argv, prompt, env, phase, call_id)
        except TimeoutError:
            raise _AttemptFailed(LLMTimeoutError(f"claude -p exceeded {self.timeout_s:g} s", call_id=call_id,
                                                 phase=phase), retry=True) from None
        except FileNotFoundError:
            raise _AttemptFailed(LLMAuthError(f"Claude Code executable {self.executable!r} not found; install "
                                              "Claude Code and log in (`claude --version`)", call_id=call_id,
                                              phase=phase), retry=False) from None
        except OSError as exc:
            raise _AttemptFailed(LLMUnavailableError(f"could not start claude -p: {exc}", call_id=call_id,
                                                     phase=phase), retry=True) from None
        try:
            out = json.loads(run.stdout)
            if not isinstance(out, dict):
                raise ValueError("result is not a JSON object")
        except ValueError:
            raise _AttemptFailed(LLMUnavailableError(
                f"claude -p exited {run.returncode} without a JSON result; stderr: {run.stderr[:500]}",
                call_id=call_id, phase=phase), retry=True) from None

        # A JSON result means the CLI ran; account for what it spent even if the answer is unusable.
        usage = _usage_of(out)
        self._usage = self._usage + usage
        cost = out.get("total_cost_usd")
        if isinstance(cost, int | float):
            self._cost += float(cost)
        mu = out.get("modelUsage")
        if isinstance(mu, dict):
            self._served.update(str(k) for k in mu)
        served = self._served_model(out)
        self._served.add(served)

        stop = out.get("stop_reason")
        if stop == "max_tokens":
            conv.started = True
            raise _AttemptFailed(LLMTruncatedError("output truncated at max_tokens", max_tokens=request.max_tokens,
                                                   call_id=call_id, phase=phase), retry=False, out=out)
        if stop == "refusal":
            conv.started = True
            self._refusals.append({"call_id": call_id, "stage": phase, "category": None})
            raise _AttemptFailed(LLMRefusalError("model declined", category=None, call_id=call_id, phase=phase),
                                 retry=False, out=out)
        if out.get("is_error"):
            text = str(out.get("result") or out.get("subtype") or "")
            if out.get("subtype") == "error_max_budget_usd":
                raise _AttemptFailed(LLMUnavailableError(
                    f"claude -p hit --max-budget-usd {self.max_budget_usd_per_call}", call_id=call_id, phase=phase),
                    retry=False, out=out)
            err, retry = _classify(text, call_id=call_id, phase=phase)
            raise _AttemptFailed(err, retry=retry, out=out)
        conv.started = True

        fallback: FallbackEvent | None = None
        if self.allow_fallback and served != self.model:
            fallback = FallbackEvent(role=phase, from_model=self.model, to_model=served,
                                     reason=f"claude_code --fallback-model ({call_id})")
            self._fallbacks.append(fallback)

        try:
            parsed_out = self._interpret(request, out, call_id)
        except LLMSchemaError as err:
            raise _AttemptFailed(err, retry=False, out=out) from None
        result = {**parsed_out, "served": served, "usage": usage, "fallback": fallback}
        self.log.log({**base_entry, "model": served, "stop_reason": result["stop_reason"], "outcome": "ok",
                      "usage": usage.__dict__, "content": result["content"], "num_turns": out.get("num_turns"),
                      "total_cost_usd": out.get("total_cost_usd"), "terminal_reason": out.get("terminal_reason"),
                      "cli_stop_reason": stop})
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
                    uses.append(ToolUse(id=self._issue_tool_id(str(c.get("id") or "")), name=c["name"],
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
