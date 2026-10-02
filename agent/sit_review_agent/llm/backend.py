"""Choose the live LLM backend from config (ADR-010).

Workstream C's ``orchestrator.run_review`` calls :func:`build_llm_gateway` for ``transport: live``
(and ``record``/``replay``, which only affect tools). ``transport: fake`` still uses
:class:`~sit_review_agent.llm.gateway.FakeGateway` and does not come through here.

* ``llm.backend: claude_code`` -> :class:`~sit_review_agent.llm.claude_code.ClaudeCodeGateway`
  (headless ``claude -p``; Claude subscription or Claude Code cloud credits; text-only documents).
* ``llm.backend: anthropic_api`` -> :class:`~sit_review_agent.llm.gateway.AnthropicGateway`
  (``ANTHROPIC_API_KEY``; native PDF blocks and native tool use).

Callers that build the document prefix ask :func:`supports_native_pdf` whether to include the
native PDF block (``llm.prefix.start_conversation(..., native_pdf=supports_native_pdf(gw))``).
"""

from __future__ import annotations

from sit_review_agent.clock import Clock
from sit_review_agent.config import EffectiveConfig
from sit_review_agent.llm.claude_code import ClaudeCodeGateway
from sit_review_agent.llm.gateway import AnthropicGateway, LLMGateway
from sit_review_agent.progress import ProgressSink
from sit_review_agent.rundir import RunDir


def build_llm_gateway(config: EffectiveConfig, run_dir: RunDir, *, clock: Clock | None = None,
                      progress: ProgressSink | None = None) -> LLMGateway:
    """The live gateway named by ``config.agent.llm.backend``. Never touches the network."""
    if config.agent.llm.backend == "claude_code":
        return ClaudeCodeGateway(config, run_dir, clock=clock, progress=progress)
    return AnthropicGateway(config, run_dir, clock=clock, progress=progress)


def supports_native_pdf(gw: object) -> bool:
    """Whether ``gw`` accepts native PDF document blocks (gateways without the attribute do)."""
    return bool(getattr(gw, "native_pdf", True))
