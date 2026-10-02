"""Typed errors and the documented process exit codes.

Every error the agent raises on purpose is an :class:`AgentError` subclass with an ``exit_code``.
The CLI maps an uncaught ``AgentError`` to that code; anything else is a stage crash (exit 4) and
is a bug (robustness INV-11: no unhandled traceback).

Exit codes are fixed by docs/DECISIONS.md ADR-009 item 5. ``RESUME_DRIFT`` is the "distinct exit
code" ADR-009 item 4 asks for without naming a number.
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    USAGE = 2               # bad arguments, unreadable input, invalid config
    LLM_UNAVAILABLE = 3     # retry budget exhausted, spend cap, auth (checkpointed, resumable)
    STAGE_CRASH = 4         # unexpected exception inside a stage (checkpoint plus partial report)
    RESUME_DRIFT = 5        # resume refused: config, prompt bundle or canonical text hash changed
    SIGINT = 130            # Ctrl-C (checkpoint flushed)


class AgentError(Exception):
    """Base class. ``exit_code`` is what the CLI returns if this error ends the run."""

    exit_code: ExitCode = ExitCode.STAGE_CRASH


# --------------------------------------------------------------------------------------- usage


class ConfigError(AgentError):
    """A config file is missing, malformed or inconsistent (e.g. an unknown stop rule)."""

    exit_code = ExitCode.USAGE


class InputError(AgentError):
    """The input PDF is unreadable, encrypted, empty or too large for any ingestion path."""

    exit_code = ExitCode.USAGE


class PromptError(AgentError):
    """A prompt file is missing, renders with an undefined variable, or PROMPTS.lock is stale."""

    exit_code = ExitCode.USAGE


# ----------------------------------------------------------------------------------------- LLM


class LLMError(AgentError):
    """Base for every failure surfaced by :class:`~sit_review_agent.llm.gateway.LLMGateway`."""

    exit_code = ExitCode.LLM_UNAVAILABLE

    def __init__(self, message: str, *, call_id: str | None = None, phase: str | None = None) -> None:
        super().__init__(message)
        self.call_id = call_id
        self.phase = phase


class LLMRefusalError(LLMError):
    """``stop_reason == "refusal"``. ``category`` may legitimately be ``None`` (REPRODUCIBILITY §3).

    Partial output of a mid-stream refusal is discarded, never parsed. The phase decides whether to
    retry once with professional-review framing (robustness LLM-06).
    """

    def __init__(self, message: str, *, category: str | None, explanation: str | None = None,
                 call_id: str | None = None, phase: str | None = None) -> None:
        super().__init__(message, call_id=call_id, phase=phase)
        self.category = category
        self.explanation = explanation


class LLMTruncatedError(LLMError):
    """``stop_reason == "max_tokens"``. Truncated JSON is never repaired (robustness LLM-07)."""

    def __init__(self, message: str, *, max_tokens: int, call_id: str | None = None,
                 phase: str | None = None) -> None:
        super().__init__(message, call_id=call_id, phase=phase)
        self.max_tokens = max_tokens


class LLMRateLimitError(LLMError):
    """429 after the gateway's retry budget. ``retry_after_s`` is ``None`` for a spend-cap 429."""

    def __init__(self, message: str, *, retry_after_s: float | None, call_id: str | None = None,
                 phase: str | None = None) -> None:
        super().__init__(message, call_id=call_id, phase=phase)
        self.retry_after_s = retry_after_s


class LLMTimeoutError(LLMError):
    """Client timeout or stalled stream after the gateway's retry budget (robustness LLM-05)."""


class LLMDeadlineError(LLMTimeoutError):
    """A model attempt was cut by the run deadline, or no time was left to start (or retry) one
    (robustness LLM-05). Never retried past the deadline. Phases catch it and degrade: research
    ends, assess reports "out of time before assessment", refine keeps the assess findings, and
    report falls back to a verdict by rule. Uncaught it ends the run like a timeout (exit 3)."""


class LLMOverloadedError(LLMError):
    """529 / 503 after the gateway's retry budget (robustness LLM-03)."""


class LLMAuthError(LLMError):
    """401 / 403 / missing credentials. Message names the env var, never its value (LLM-11)."""


class LLMBadRequestError(LLMError):
    """400 (a request the API rejects). Not retried; this is a bug in the request builder."""

    exit_code = ExitCode.STAGE_CRASH


class LLMSchemaError(LLMError):
    """The structured output did not validate against the requested Pydantic type (LLM-08)."""

    exit_code = ExitCode.STAGE_CRASH


class LLMUnavailableError(LLMError):
    """Generic "the model cannot be reached" after all retries; the run checkpoints and exits 3."""


class LLMConnectionError(LLMUnavailableError):
    """A connection-type failure (DNS, refused or reset connection, no route), as opposed to an
    overload (429/529/5xx). On the first model call of a run it gets a short retry window and then
    ends the run with a "no network" message (robustness NET-02); later calls keep the full policy."""


class LLMContextTooLongError(LLMError):
    """The request would exceed the model's context window (estimated before sending, robustness
    LLM-10). Never sent. A usage-class error: the document is too large for one request."""

    exit_code = ExitCode.USAGE

    def __init__(self, message: str, *, estimated_tokens: int = 0, limit_tokens: int = 0, call_id: str | None = None,
                 phase: str | None = None) -> None:
        super().__init__(message, call_id=call_id, phase=phase)
        self.estimated_tokens = estimated_tokens
        self.limit_tokens = limit_tokens


class EffortChangedError(LLMError):
    """A conversation tried to change ``effort`` mid-conversation (ADR-002: one level per conversation)."""

    exit_code = ExitCode.STAGE_CRASH


class FakeScriptExhausted(LLMError):
    """``FakeGateway`` has no scripted response left for a phase (a test-authoring error)."""

    exit_code = ExitCode.STAGE_CRASH


# --------------------------------------------------------------------------------------- tools


class ToolError(AgentError):
    """Base for tool-gateway failures that are raised rather than returned as an error ToolResult."""

    exit_code = ExitCode.STAGE_CRASH


class ToolNotAllowedError(ToolError):
    """The tool is disabled, not in ``allow_tools``, or its server is down/disabled."""


class ToolBlockedError(ToolError):
    """The URL policy or the argument sanitiser refused the call (status ``blocked``; ADV-05)."""


class ToolAuthError(ToolError):
    """A confirmed 401/403 from the shared SIT key; all servers are disabled together (INF-07)."""


class ReplayMiss(ToolError):
    """Strict replay found no cassette for the call's key (REPRODUCIBILITY §6)."""

    def __init__(self, key: str, server: str, tool: str) -> None:
        super().__init__(f"no cassette for {server}/{tool} key={key}")
        self.key = key
        self.server = server
        self.tool = tool


# ---------------------------------------------------------------------------------- run / state


class BudgetExceededError(AgentError):
    """A hard budget (tokens or spend) was exceeded where a graceful stop was not possible."""

    exit_code = ExitCode.LLM_UNAVAILABLE


class RegistryFrozenError(AgentError):
    """An attempt to change the decision registry after the understand phase (INV-10)."""


class LedgerError(AgentError):
    """An evidence-ledger rule was broken (unknown ID, external entry without a tool call, ...)."""


class CheckpointError(AgentError):
    """A checkpoint could not be written or read."""


class ResumeDriftError(AgentError):
    """Resume refused: a pinned hash differs from the checkpoint and ``--accept-drift`` was not given."""

    exit_code = ExitCode.RESUME_DRIFT

    def __init__(self, drift: list[str]) -> None:
        super().__init__("resume refused, hashes changed since checkpoint: " + "; ".join(drift))
        self.drift = drift


class RunInterrupted(AgentError):
    """Ctrl-C / cancellation; the state of the last completed phase is on disk (OPS-04)."""

    exit_code = ExitCode.SIGINT


class StageCrash(AgentError):
    """Wraps an unexpected exception raised inside a phase, after the checkpoint is flushed."""

    exit_code = ExitCode.STAGE_CRASH

    def __init__(self, phase: str, cause: BaseException) -> None:
        super().__init__(f"stage {phase} crashed: {type(cause).__name__}: {cause}")
        self.phase = phase
        self.cause = cause
