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
    """
    raise NotImplementedError(f"judge kind {kind!r} is not implemented yet")
