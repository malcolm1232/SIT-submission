"""Frozen model-call interface shared by the matcher, adjudicator and grader.

FROZEN (coordinator, 2026-10-02): the matcher workstream implements the live clients in this
module; the grader workstream codes against :class:`JudgeClient` and :class:`FakeJudge` only.
Changing a signature here needs the coordinator.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class JudgeRequest:
    """One structured-output call. ``schema`` is a JSON Schema object the answer must satisfy."""

    purpose: str                 # e.g. "match:F03", "adjudicate:FND-007", "grader:passA"
    system: str
    user: str
    schema: dict[str, Any]
    model: str = "claude-opus-5-5"
    effort: str = "high"
    max_tokens: int = 16000
    sample_index: int = 0        # 0..n-1 when the same prompt is sampled n times


@dataclass(frozen=True)
class JudgeResult:
    data: dict[str, Any]         # parsed structured output, already schema-valid
    model: str                   # model that actually served the call
    cost_usd: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_s: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)   # backend-specific extras for the call log


class JudgeError(RuntimeError):
    """The call could not produce a schema-valid answer after the client's own retries."""


class JudgeClient(Protocol):
    async def complete(self, request: JudgeRequest) -> JudgeResult: ...


class FakeJudge:
    """Offline client for tests: ``responder(request) -> dict`` returns the structured answer.

    Records every request in ``calls``; raises :class:`JudgeError` if the responder does.
    """

    def __init__(self, responder: Callable[[JudgeRequest], dict[str, Any]], *, model: str = "fake-judge") -> None:
        self._responder = responder
        self._model = model
        self.calls: list[JudgeRequest] = []

    async def complete(self, request: JudgeRequest) -> JudgeResult:
        self.calls.append(request)
        return JudgeResult(data=self._responder(request), model=self._model, cost_usd=0.0)


def build_judge(kind: str, *, out_dir: Any, **options: Any) -> JudgeClient:
    """The client named by ``kind``: ``"claude_code"`` (headless ``claude -p``, ADR-010 billing)
    or ``"anthropic_api"`` (``ANTHROPIC_API_KEY``). ``out_dir`` receives the JSONL call log.

    Live kinds are implemented by the matcher workstream; tests build :class:`FakeJudge` directly.

    Also accepts ``"fake"`` (a deterministic offline :class:`FakeJudge`; ``responder=`` overrides the
    default plumbing responder of :mod:`sit_eval.fakes`). Options per kind (unknown options raise
    ``ValueError``): ``claude_code`` - executable, timeout_s, max_retries, backoff_base_s,
    backoff_max_s, max_budget_usd_per_call, inherit_api_key, extra_args, runner, sleep, seed,
    log_name; ``anthropic_api`` - client, timeout_s, max_retries, backoff_base_s, backoff_max_s,
    price_per_mtok, sleep, seed, log_name. The model and effort come from each
    :class:`JudgeRequest`, never from the client.

    Live-client options that the caller does not pass default to the ``judge`` section of
    ``config/eval.yaml`` (claude_code: executable, timeout_s, max_retries, backoff_base_s,
    backoff_max_s, max_budget_usd_per_call, inherit_api_key; anthropic_api: timeout_s, max_retries,
    backoff_base_s, backoff_max_s), so a caller that passes no options (the grader) still gets the
    configured per-call ``--max-budget-usd`` cap. Explicit options always win.
    """
    import inspect

    if kind == "fake":
        from sit_eval.fakes import plumbing_responder

        extra = set(options) - {"responder", "model"}
        if extra:
            raise ValueError(f"judge kind 'fake' does not take {sorted(extra)}")
        return FakeJudge(options.get("responder") or plumbing_responder, model=options.get("model", "fake-judge"))
    from sit_eval.live_judges import AnthropicJudge, ClaudeCodeJudge

    classes = {"claude_code": ClaudeCodeJudge, "anthropic_api": AnthropicJudge}
    if kind not in classes:
        raise ValueError(f"unknown judge kind {kind!r}; expected one of fake, claude_code, anthropic_api")
    cls = classes[kind]
    allowed = set(inspect.signature(cls.__init__).parameters) - {"self", "out_dir"}
    extra = set(options) - allowed
    if extra:
        raise ValueError(f"judge kind {kind!r} does not take {sorted(extra)}; allowed: {sorted(allowed)}")
    from sit_eval.config import load_eval_config

    jc = load_eval_config().judge
    common = {"timeout_s": jc.timeout_s, "max_retries": jc.max_retries, "backoff_base_s": jc.backoff_base_s,
              "backoff_max_s": jc.backoff_max_s}
    defaults = ({**common, "executable": jc.executable, "max_budget_usd_per_call": jc.max_budget_usd_per_call,
                 "inherit_api_key": jc.inherit_api_key} if kind == "claude_code" else common)
    return cls(out_dir=out_dir, **{**defaults, **options})
