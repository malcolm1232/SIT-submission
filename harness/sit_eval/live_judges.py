"""Live :class:`~sit_eval.judge.JudgeClient` implementations.

:class:`ClaudeCodeJudge` (default) runs one headless ``claude -p`` per attempt and reuses the
command contract verified for the agent's backend (``sit_review_agent.llm.claude_code``, ADR-010):
the judge's system prompt replaces Claude Code's, every CLI tool / MCP server / slash command /
CLAUDE.md / attachment is off, the user prompt goes to stdin, ``--json-schema`` carries the output
schema and the answer comes back in ``structured_output``; ``--bare`` and
``--no-session-persistence`` are never passed; ``ANTHROPIC_API_KEY`` / ``ANTHROPIC_AUTH_TOKEN`` are
removed from the child environment unless ``inherit_api_key`` (billing goes to the Claude Code
login, ADR-010); errors are classified with the backend's own classifier. Every attempt starts a
fresh CLI session, so a call's cost is that session's own ``total_cost_usd``; the code still
subtracts the session's previously seen cumulative total, so a reused session would be costed
correctly (``cost_basis`` in the log says which applied). A call's reported cost is the sum over all
its attempts (failed attempts included); attempts that reported no cost (a timeout, a crash) are
counted in ``raw["unknown_cost_attempts"]`` (or ``JudgeError.unknown_cost_attempts``) so the
scorer's cost stop can charge a reserve for each.

:class:`AnthropicJudge` calls the Messages API with ``ANTHROPIC_API_KEY`` (the SDK reads it; the value
is never logged), streaming like the agent's ``AnthropicGateway``. Message Batches (50 % price,
prereg ``matcher.model.branch_B``) is not implemented yet: calls are synchronous.

Both write one JSON line per attempt to ``<out_dir>/judge_calls.jsonl``: purpose, sample index,
attempt, requested and served model, effort, outcome, error, token usage, cost, elapsed time and the
SHA-256 of the system prompt, user prompt and schema (never the prompt text or any secret).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from sit_eval.judge import JudgeError, JudgeRequest, JudgeResult
from sit_review_agent.llm.claude_code import (
    API_KEY_ENV_VARS,
    FORBIDDEN_FLAGS,
    MAX_ARGV_TEXT_CHARS,
    CompletedRun,
    _classify,
    _error_text,
    subprocess_runner,
)

Runner = Callable[[list[str], str, dict[str, str], Path, float], Awaitable[CompletedRun]]
Sleep = Callable[[float], Awaitable[None]]
CALL_LOG_NAME = "judge_calls.jsonl"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def schema_problems(schema: dict[str, Any], data: Any) -> list[str]:
    errs = list(Draft202012Validator(schema).iter_errors(data))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message[:200]}" for e in errs[:5]]


def argv_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """The schema as sent to the model: the root-level ``$schema`` meta keyword is dropped, because
    ``claude -p --json-schema`` has been seen to reject a schema carrying it ("no schema with key or
    ref", grader verifier, 2026-10-02). Answers are still validated against the full schema."""
    return {k: v for k, v in schema.items() if k != "$schema"}


class CallLog:
    """Append-only JSONL log of judge attempts. ``tags`` are written into every entry (``sit-eval`` passes
    ``{"exploratory": ...}``, the run's LC12 mode)."""

    def __init__(self, out_dir: str | Path, name: str = CALL_LOG_NAME, tags: dict[str, Any] | None = None) -> None:
        self.path = Path(out_dir) / name
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tags = dict(tags or {})

    def write(self, entry: dict[str, Any]) -> None:
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **self.tags, **entry}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")


class _Retrying:
    """Shared retry loop: exponential backoff with jitter on retryable failures."""

    def __init__(self, *, max_retries: int, backoff_base_s: float, backoff_max_s: float,
                 sleep: Sleep | None, seed: int | None) -> None:
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.backoff_max_s = backoff_max_s
        self._sleep = sleep or asyncio.sleep
        self._rng = random.Random(seed)

    def backoff(self, attempt: int) -> float:
        delay = min(self.backoff_max_s, self.backoff_base_s * (2 ** attempt))
        return delay * (0.5 + 0.5 * self._rng.random())


class _AttemptError(Exception):
    def __init__(self, message: str, *, retry: bool, entry: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.retry = retry
        self.entry = entry or {}


# ============================================================================ Claude Code


class ClaudeCodeJudge(_Retrying):
    backend = "claude_code"

    def __init__(self, *, out_dir: str | Path, executable: str = "claude", timeout_s: float = 1200.0,
                 max_retries: int = 3, backoff_base_s: float = 5.0, backoff_max_s: float = 120.0,
                 max_budget_usd_per_call: float | None = None, inherit_api_key: bool = False,
                 extra_args: list[str] | tuple[str, ...] = (), runner: Runner | None = None,
                 sleep: Sleep | None = None, seed: int | None = None, log_name: str = CALL_LOG_NAME,
                 log_tags: dict[str, Any] | None = None) -> None:
        super().__init__(max_retries=max_retries, backoff_base_s=backoff_base_s, backoff_max_s=backoff_max_s,
                         sleep=sleep, seed=seed)
        bad = sorted(FORBIDDEN_FLAGS & set(extra_args))
        if bad:
            raise ValueError(f"extra_args must not contain {bad} (ADR-010)")
        self.out_dir = Path(out_dir)
        self.cwd = self.out_dir / "cli_cwd"
        self.executable = executable
        self.timeout_s = timeout_s
        self.max_budget_usd_per_call = max_budget_usd_per_call
        self.inherit_api_key = inherit_api_key
        self.extra_args = list(extra_args)
        self.runner: Runner = runner or subprocess_runner
        self.log = CallLog(out_dir, log_name, log_tags)
        self._session_cost_seen: dict[str, float] = {}
        self.cost_total_usd = 0.0

    def env(self, request: JudgeRequest) -> dict[str, str]:
        env = dict(os.environ)
        if not self.inherit_api_key:
            for name in API_KEY_ENV_VARS:    # only names, never values, are referenced
                env.pop(name, None)
        env.update({"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_ATTACHMENTS": "1",
                    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(request.max_tokens)})
        return env

    def build_argv(self, request: JudgeRequest, *, schema_json: str, session_id: str) -> list[str]:
        argv = [self.executable, "-p", "--model", request.model, "--system-prompt", request.system,
                "--tools", "", "--strict-mcp-config", "--disallowedTools", "mcp__*", "--disable-slash-commands",
                "--output-format", "json", "--effort", request.effort, "--json-schema", schema_json,
                "--session-id", session_id]
        if self.max_budget_usd_per_call is not None:
            argv += ["--max-budget-usd", f"{self.max_budget_usd_per_call:g}"]
        return argv + self.extra_args

    async def complete(self, request: JudgeRequest) -> JudgeResult:
        schema_json = json.dumps(argv_schema(request.schema), sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False)
        for label, value in (("system prompt", request.system), ("JSON schema", schema_json)):
            if len(value) > MAX_ARGV_TEXT_CHARS:
                raise JudgeError(f"{request.purpose}: {label} has {len(value)} characters; claude -p takes it on "
                                 f"argv and accepts at most {MAX_ARGV_TEXT_CHARS}")
        base = {"backend": self.backend, "purpose": request.purpose, "sample_index": request.sample_index,
                "requested_model": request.model, "effort": request.effort, "max_tokens": request.max_tokens,
                "system_sha256": _sha(request.system), "user_sha256": _sha(request.user),
                "schema_sha256": _sha(schema_json)}
        env = self.env(request)
        self.cwd.mkdir(parents=True, exist_ok=True)
        attempt = 0
        t_call = time.monotonic()
        known_cost = 0.0          # summed over every attempt of this call, failed ones included
        unknown_attempts = 0      # attempts that may have cost money but reported nothing (timeouts, crashes)
        while True:
            session_id = str(uuid.uuid4())
            t0 = time.monotonic()
            entry = {**base, "attempt": attempt, "session_id": session_id}
            try:
                data, info = await self._attempt(request, schema_json, session_id, env, entry)
            except _AttemptError as err:
                c = err.entry.get("call_cost_usd")
                if isinstance(c, int | float):
                    known_cost += float(c)
                else:
                    unknown_attempts += 1
                self.log.write({**entry, **err.entry, "outcome": "error", "error": str(err)[:500],
                                "elapsed_s": round(time.monotonic() - t0, 3)})
                if err.retry and attempt < self.max_retries:
                    await self._sleep(self.backoff(attempt))
                    attempt += 1
                    continue
                exc = JudgeError(f"{request.purpose}: {err}")
                exc.cost_usd = known_cost if attempt + 1 > unknown_attempts else None  # type: ignore[attr-defined]
                exc.unknown_cost_attempts = unknown_attempts  # type: ignore[attr-defined]
                raise exc from None
            elapsed = time.monotonic() - t0
            self.log.write({**entry, **info, "outcome": "ok", "elapsed_s": round(elapsed, 3)})
            c = info["call_cost_usd"]
            if c is None:
                unknown_attempts += 1
            total = known_cost + (c or 0.0) if (c is not None or known_cost > 0) else None
            return JudgeResult(data=data, model=info["served_model"], cost_usd=total,
                               input_tokens=info["usage"].get("input_tokens", 0),
                               output_tokens=info["usage"].get("output_tokens", 0),
                               elapsed_s=time.monotonic() - t_call,
                               raw={"backend": self.backend, "session_id": session_id, "attempts": attempt + 1,
                                    "num_turns": info.get("num_turns"), "cost_basis": info["cost_basis"],
                                    "unknown_cost_attempts": unknown_attempts,
                                    "cost_includes_failed_attempts": attempt > 0})

    def _cost(self, out: dict[str, Any], session_id: str) -> tuple[float | None, str]:
        total = out.get("total_cost_usd")
        if not isinstance(total, int | float):
            return None, "unreported"
        seen = self._session_cost_seen.get(session_id)
        self._session_cost_seen[session_id] = float(total)
        if seen is None:
            return float(total), "call_total"
        return max(0.0, float(total) - seen), "cumulative_delta"

    @staticmethod
    def _served(out: dict[str, Any], requested: str) -> str:
        mu = out.get("modelUsage")
        if not isinstance(mu, dict) or not mu:
            return requested
        if requested in mu:
            return requested
        for k in mu:
            if str(k).startswith(requested):
                return str(k)
        return str(max(mu, key=lambda k: (mu[k] or {}).get("outputTokens", 0) if isinstance(mu[k], dict) else 0))

    async def _attempt(self, request: JudgeRequest, schema_json: str, session_id: str, env: dict[str, str],
                       entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        argv = self.build_argv(request, schema_json=schema_json, session_id=session_id)
        try:
            run = await self.runner(argv, request.user, env, self.cwd, self.timeout_s)
        except TimeoutError:
            raise _AttemptError(f"claude -p exceeded {self.timeout_s:g} s", retry=True) from None
        except FileNotFoundError:
            raise _AttemptError(f"Claude Code executable {self.executable!r} not found; install Claude Code and "
                                "log in (`claude --version`)", retry=False) from None
        except OSError as exc:
            raise _AttemptError(f"could not start claude -p: {exc}", retry=True) from None
        try:
            out = json.loads(run.stdout)
            if not isinstance(out, dict):
                raise ValueError("not an object")
        except ValueError:
            raise _AttemptError(f"claude -p exited {run.returncode} without a JSON result; stderr: "
                                f"{run.stderr[:300]}", retry=True) from None
        cost, basis = self._cost(out, session_id)
        if cost is not None:
            self.cost_total_usd += cost
        u = out.get("usage") if isinstance(out.get("usage"), dict) else {}
        usage = {k: int(u[k]) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                        "cache_read_input_tokens") if isinstance(u.get(k), int | float)}
        info = {"served_model": self._served(out, request.model), "usage": usage, "call_cost_usd": cost,
                "cost_basis": basis, "total_cost_usd": out.get("total_cost_usd"), "num_turns": out.get("num_turns"),
                "cli_stop_reason": out.get("stop_reason"), "terminal_reason": out.get("terminal_reason")}
        stop = out.get("stop_reason")
        if stop == "max_tokens":
            raise _AttemptError(f"output truncated at max_tokens={request.max_tokens}", retry=False, entry=info)
        if stop == "refusal":
            raise _AttemptError("model declined (refusal)", retry=False, entry=info)
        if out.get("is_error"):
            subtype = out.get("subtype")
            if subtype == "error_max_budget_usd":
                raise _AttemptError(f"hit --max-budget-usd {self.max_budget_usd_per_call}", retry=False, entry=info)
            if subtype == "error_max_structured_output_retries":
                raise _AttemptError(f"no schema-valid output: {_error_text(out)[:300]}", retry=False, entry=info)
            err, retry = _classify(_error_text(out), call_id=request.purpose, phase="judge")
            raise _AttemptError(f"{type(err).__name__}: {err}", retry=retry, entry=info)
        data = out.get("structured_output")
        if data is None:
            try:
                data = json.loads(str(out.get("result") or ""))
            except ValueError:
                raise _AttemptError("claude -p returned no structured_output", retry=False, entry=info) from None
        if not isinstance(data, dict):
            raise _AttemptError("structured output is not a JSON object", retry=False, entry=info)
        problems = schema_problems(request.schema, data)
        if problems:
            raise _AttemptError("structured output violates the schema: " + "; ".join(problems), retry=False,
                                entry=info)
        return data, info


# ============================================================================ Anthropic API


class AnthropicJudge(_Retrying):
    """Messages API judge (``ANTHROPIC_API_KEY``). ``price_per_mtok`` (USD per million tokens:
    ``input``, ``output``, ``cache_write``, ``cache_read``) enables per-call cost; without it
    ``cost_usd`` is ``None`` and the scorer's cost stop uses its per-call reserve instead."""

    backend = "anthropic_api"

    def __init__(self, *, out_dir: str | Path, client: Any | None = None, timeout_s: float = 1200.0,
                 max_retries: int = 3, backoff_base_s: float = 5.0, backoff_max_s: float = 120.0,
                 price_per_mtok: dict[str, float] | None = None, sleep: Sleep | None = None,
                 seed: int | None = None, log_name: str = CALL_LOG_NAME,
                 log_tags: dict[str, Any] | None = None) -> None:
        super().__init__(max_retries=max_retries, backoff_base_s=backoff_base_s, backoff_max_s=backoff_max_s,
                         sleep=sleep, seed=seed)
        self._client = client
        self.timeout_s = timeout_s
        self.price_per_mtok = price_per_mtok
        self.log = CallLog(out_dir, log_name, log_tags)
        self.cost_total_usd = 0.0

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic

            try:
                self._client = anthropic.AsyncAnthropic(max_retries=0, timeout=self.timeout_s)
            except anthropic.AnthropicError as exc:
                raise JudgeError(f"cannot create the Anthropic client ({type(exc).__name__}); is ANTHROPIC_API_KEY "
                                 "set? (its value is never logged)") from None
        return self._client

    @staticmethod
    def build_body(request: JudgeRequest) -> dict[str, Any]:
        """Same request shape as the agent's ``AnthropicGateway.build_body`` (adaptive thinking,
        ``output_config.effort`` and ``output_config.format`` json_schema; no sampling knobs)."""
        return {"model": request.model, "max_tokens": request.max_tokens,
                "system": [{"type": "text", "text": request.system}],
                "messages": [{"role": "user", "content": [{"type": "text", "text": request.user}]}],
                "thinking": {"type": "adaptive", "display": "omitted"},
                "output_config": {"effort": request.effort,
                                  "format": {"type": "json_schema", "schema": argv_schema(request.schema)}}}

    def _price(self, usage: dict[str, int]) -> float | None:
        p = self.price_per_mtok
        if not p:
            return None
        return (usage.get("input_tokens", 0) * p.get("input", 0.0)
                + usage.get("output_tokens", 0) * p.get("output", 0.0)
                + usage.get("cache_creation_input_tokens", 0) * p.get("cache_write", 0.0)
                + usage.get("cache_read_input_tokens", 0) * p.get("cache_read", 0.0)) / 1e6

    async def complete(self, request: JudgeRequest) -> JudgeResult:
        from sit_review_agent.llm.gateway import _anthropic_classify

        body = self.build_body(request)
        base = {"backend": self.backend, "purpose": request.purpose, "sample_index": request.sample_index,
                "requested_model": request.model, "effort": request.effort, "max_tokens": request.max_tokens,
                "system_sha256": _sha(request.system), "user_sha256": _sha(request.user),
                "schema_sha256": _sha(json.dumps(request.schema, sort_keys=True))}
        attempt = 0
        t_call = time.monotonic()
        while True:
            t0 = time.monotonic()
            entry = {**base, "attempt": attempt}
            try:
                async with self.client.messages.stream(**body) as stream:
                    message = await stream.get_final_message()
            except Exception as exc:  # noqa: BLE001 - classified below; bugs re-raised
                mapped = _anthropic_classify(exc, call_id=request.purpose, phase="judge")
                if mapped is None:
                    raise
                err, retry, retry_after, status = mapped
                self.log.write({**entry, "outcome": "error", "error": f"{type(err).__name__}: {err}"[:500],
                                "status": status, "elapsed_s": round(time.monotonic() - t0, 3)})
                if retry and attempt < self.max_retries:
                    await self._sleep(retry_after if retry_after is not None else self.backoff(attempt))
                    attempt += 1
                    continue
                raise JudgeError(f"{request.purpose}: {type(err).__name__}: {err}") from None
            data, info, problem = self._interpret(message, request)
            if problem is not None:
                self.log.write({**entry, **info, "outcome": "error", "error": problem,
                                "elapsed_s": round(time.monotonic() - t0, 3)})
                raise JudgeError(f"{request.purpose}: {problem}")
            self.log.write({**entry, **info, "outcome": "ok", "elapsed_s": round(time.monotonic() - t0, 3)})
            return JudgeResult(data=data, model=info["served_model"], cost_usd=info["call_cost_usd"],
                               input_tokens=info["usage"].get("input_tokens", 0),
                               output_tokens=info["usage"].get("output_tokens", 0),
                               elapsed_s=time.monotonic() - t_call,
                               raw={"backend": self.backend, "attempts": attempt + 1,
                                    "request_id": getattr(message, "_request_id", None)})

    def _interpret(self, message: Any, request: JudgeRequest) -> tuple[dict[str, Any], dict[str, Any], str | None]:
        def get(obj: Any, name: str) -> Any:
            return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)

        u = get(message, "usage")
        usage = {k: int(get(u, k) or 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                                   "cache_read_input_tokens")} if u is not None else {}
        cost = self._price(usage)
        if cost is not None:
            self.cost_total_usd += cost
        info = {"served_model": str(get(message, "model") or request.model), "usage": usage, "call_cost_usd": cost,
                "cost_basis": "price_table" if cost is not None else "unpriced",
                "stop_reason": get(message, "stop_reason")}
        stop = info["stop_reason"]
        if stop in ("max_tokens", "model_context_window_exceeded"):
            return {}, info, f"output truncated ({stop})"
        if stop == "refusal":
            return {}, info, "model declined (refusal)"
        text = "".join(str(get(b, "text") or "") for b in (get(message, "content") or [])
                       if get(b, "type") == "text")
        try:
            data = json.loads(text)
        except ValueError:
            return {}, info, "response text is not JSON"
        if not isinstance(data, dict):
            return {}, info, "structured output is not a JSON object"
        problems = schema_problems(request.schema, data)
        if problems:
            return {}, info, "structured output violates the schema: " + "; ".join(problems)
        return data, info, None
