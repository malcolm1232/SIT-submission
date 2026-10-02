"""AnthropicGateway (workstream A) against an injected fake async SDK client: offline, no key.

Covers what the removed ``tests/test_pending.py`` names ``test_anthropic_gateway_request_shape`` and
``test_anthropic_gateway_retry_and_stop_reasons``: the request body, stop-reason handling, the
retry policy under ``FakeClock``, ``llm.jsonl`` logging, served models and fallback events, plus
``llm_facing_schema``. Responses and errors are real SDK types (``anthropic.types.Message``,
``anthropic.RateLimitError`` ...), only the transport is fake.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import jsonschema
import pytest
from anthropic.types import Message, ModelInfo
from anthropic.types.beta import BetaMessage
from pydantic import BaseModel, Field

from sit_review_agent.clock import FakeClock
from sit_review_agent.config import EffectiveConfig, load_config
from sit_review_agent.errors import (
    EffortChangedError,
    LLMAuthError,
    LLMBadRequestError,
    LLMOverloadedError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMTruncatedError,
)
from sit_review_agent.ingest.pdf import Document
from sit_review_agent.llm.backend import build_llm_gateway, supports_native_pdf
from sit_review_agent.llm.gateway import (
    FALLBACK_BETA,
    MAX_CACHE_BREAKPOINTS,
    AnthropicGateway,
    CacheBreakpoint,
    LLMRequest,
    Usage,
    request_sha256,
)
from sit_review_agent.llm.outputs import PHASE_OUTPUT_TYPES, PlanOutput, llm_facing_schema
from sit_review_agent.llm.prefix import start_conversation
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.states import PhaseName

MODEL = "claude-opus-5-5"
PLAN = {"questions": [], "criteria_skipped": [{"criterion_id": "verifiability", "reason": "no requirements"}]}
FORBIDDEN_KEYS = {"temperature", "top_p", "top_k", "budget_tokens", "tool_choice"}
PAGES = ("[[PAGE 1]]\n1 Purpose\nThe service lets students book rooms for group study in the main library.\n"
         "[[PAGE 2]]\n2 Decisions\nD-1 Confirmed: reservations remain in the existing PostgreSQL cluster for now.\n")
REQ = httpx2.Request("POST", "https://api.anthropic.invalid/v1/messages")


# ------------------------------------------------------------------------------ fakes


def message(*, stop: str = "end_turn", text: str | None = None, content: list[dict[str, Any]] | None = None,
            model: str = MODEL, stop_details: dict[str, Any] | None = None, beta: bool = False,
            usage: dict[str, Any] | None = None) -> Any:
    blocks = content if content is not None else (
        [{"type": "thinking", "thinking": "", "signature": "sig-abc"}] + ([{"type": "text", "text": text}]
                                                                         if text is not None else []))
    data = {"id": "msg_01", "type": "message", "role": "assistant", "model": model, "content": blocks,
            "stop_reason": stop, "stop_sequence": None, "stop_details": stop_details,
            "usage": usage or {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 1000,
                               "cache_read_input_tokens": 50}}
    return (BetaMessage if beta else Message).model_validate(data)


def status_error(cls: type[anthropic.APIStatusError], status: int, *, headers: dict[str, str] | None = None,
                 body: Any = None) -> anthropic.APIStatusError:
    return cls("error", response=httpx2.Response(status, headers=headers or {}, request=REQ), body=body)


class MidStream:
    """The stream opens, then fails while reading (an SSE ``error`` event or a dropped connection)."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc


class FakeStream:
    request_id = "req_fake"

    def __init__(self, item: Any) -> None:
        self.item = item

    async def get_final_message(self) -> Any:
        if isinstance(self.item, MidStream):
            raise self.item.exc
        return self.item


class FakeStreamManager:
    def __init__(self, item: Any) -> None:
        self.item = item

    async def __aenter__(self) -> FakeStream:
        if isinstance(self.item, BaseException):
            raise self.item                      # the HTTP request itself failed
        return FakeStream(self.item)

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class FakeMessages:
    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs: Any) -> FakeStreamManager:
        self.calls.append(kwargs)
        return FakeStreamManager(self.script.pop(0))


class FakeModels:
    def __init__(self, item: Any) -> None:
        self.item = item
        self.calls: list[str] = []

    async def retrieve(self, model: str) -> Any:
        self.calls.append(model)
        if isinstance(self.item, BaseException):
            raise self.item
        return self.item


class FakeClient:
    """Duck-typed ``AsyncAnthropic``: ``messages.stream``, ``beta.messages.stream``, ``models.retrieve``."""

    def __init__(self, *script: Any, beta: list[Any] | None = None, model_info: Any = None) -> None:
        self.messages = FakeMessages(list(script))
        self.beta = SimpleNamespace(messages=FakeMessages(list(beta or [])))
        self.models = FakeModels(model_info)


# ------------------------------------------------------------------------------ helpers


@pytest.fixture(scope="module")
def base_cfg() -> EffectiveConfig:
    return load_config()


def cfg_with(base: EffectiveConfig, *, allow_fallback: bool | None = None, **llm: Any) -> EffectiveConfig:
    agent_update: dict[str, Any] = {"llm": base.agent.llm.model_copy(update=llm)}
    if allow_fallback is not None:
        agent_update["allow_fallback"] = allow_fallback
    return base.model_copy(update={"agent": base.agent.model_copy(update=agent_update)})


def gateway(tmp_path: Path, cfg: EffectiveConfig, client: FakeClient,
            clock: FakeClock | None = None) -> tuple[AnthropicGateway, RunDir, FakeClock]:
    rd = RunDir(tmp_path / "run").create()
    clk = clock or FakeClock()
    return AnthropicGateway(cfg, rd, clock=clk, client=client), rd, clk


def document() -> Document:
    return Document.from_page_marked_text(PAGES, doc_id="DOC-booking", title="Booking", pdf_bytes=b"%PDF-1.7 fake")


def plan_request(*, conv: str = "plan-0", effort: str = "high", schema: Any = PlanOutput,
                 tools: list[dict[str, Any]] | None = None) -> LLMRequest:
    msgs, bp = start_conversation([document()], "Plan the review.", native_pdf=True)
    return LLMRequest(phase=PhaseName.PLAN, conversation_id=conv, system="You are a reviewer.", messages=msgs,
                      effort=effort, max_tokens=4000, tools=tools or [], output_schema=schema,  # type: ignore[arg-type]
                      cache_breakpoints=(bp,), purpose="test")


def keys_anywhere(obj: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            out |= keys_anywhere(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= keys_anywhere(v)
    return out


def log_entries(rd: RunDir) -> list[dict[str, Any]]:
    return JsonlWriter(rd.llm_log).read()


# ------------------------------------------------------------------------------ request shape


def test_build_body_request_shape(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, _, _ = gateway(tmp_path, base_cfg, FakeClient())
    req = plan_request()
    before = json.dumps(req.messages, sort_keys=True)
    body = gw.build_body(req)

    assert set(body) == {"model", "max_tokens", "system", "messages", "thinking", "output_config", "cache_control"}
    assert body["model"] == MODEL and body["max_tokens"] == 4000
    assert body["system"] == [{"type": "text", "text": "You are a reviewer."}]
    assert body["thinking"] == {"type": "adaptive", "display": "omitted"}
    assert body["output_config"] == {"effort": "high", "format": {"type": "json_schema",
                                                                  "schema": llm_facing_schema(PlanOutput)}}
    assert body["cache_control"] == {"type": "ephemeral"}                 # automatic caching of the tail
    assert not keys_anywhere(body) & FORBIDDEN_KEYS
    assert "fallbacks" not in body and "betas" not in body

    blocks = body["messages"][0]["content"]
    assert [b["type"] for b in blocks] == ["document", "text", "text"]    # PDF, canonical text, brief
    bp = req.cache_breakpoints[0]
    assert (bp.message_index, bp.block_index) == (0, 1)
    assert blocks[1]["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
    assert "cache_control" not in blocks[0] and "cache_control" not in blocks[2]
    n_breakpoints = json.dumps(body).count('"cache_control"')
    assert n_breakpoints == 2 <= MAX_CACHE_BREAKPOINTS                     # explicit + automatic (ADR-002)
    assert json.dumps(req.messages, sort_keys=True) == before             # request not mutated


def test_build_body_variants(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, _, _ = gateway(tmp_path, base_cfg, FakeClient())
    tools = [{"name": "srv__search", "description": "Search.", "input_schema": {"type": "object"}}]
    body = gw.build_body(plan_request(schema=None, tools=tools))
    assert body["tools"] == tools and body["output_config"] == {"effort": "high"}
    assert "tool_choice" not in body

    req = LLMRequest(phase=PhaseName.PLAN, conversation_id="c", system="", messages=[{"role": "user", "content": "hi"}],
                     effort="medium", max_tokens=10, cache_breakpoints=(CacheBreakpoint(0, 0, "1h"),),
                     auto_cache_tail=False, thinking_display="summarized")
    body = gw.build_body(req)
    assert "system" not in body and "cache_control" not in body
    assert body["messages"][0]["content"] == [{"type": "text", "text": "hi",
                                               "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    assert body["thinking"]["display"] == "summarized"

    prefill = LLMRequest(phase=PhaseName.PLAN, conversation_id="c", system="s",
                         messages=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "{"}],
                         effort="high", max_tokens=10)
    with pytest.raises(LLMBadRequestError):
        gw.build_body(prefill)

    fb, _, _ = gateway(tmp_path / "fb", cfg_with(base_cfg, allow_fallback=True), FakeClient())
    body = fb.build_body(plan_request())
    assert body["fallbacks"] == "default" and body["betas"] == [FALLBACK_BETA]


def test_build_llm_gateway_anthropic_backend(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    cfg = base_cfg.model_copy(update={"agent": base_cfg.agent.model_copy(
        update={"llm": base_cfg.agent.llm.model_copy(update={"backend": "anthropic_api"})})})
    gw = build_llm_gateway(cfg, RunDir(tmp_path / "r").create(), clock=FakeClock())
    assert isinstance(gw, AnthropicGateway) and supports_native_pdf(gw)


def test_sdk_client_has_retries_disabled(tmp_path: Path, base_cfg: EffectiveConfig,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
    gw = AnthropicGateway(base_cfg, RunDir(tmp_path / "r").create(), clock=FakeClock())
    assert gw.client.max_retries == 0 and gw.client.timeout == base_cfg.agent.llm.timeout_s   # no network


# ------------------------------------------------------------------------------ stop reasons


async def test_end_turn_parses_logs_and_keeps_content(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    client = FakeClient(message(text=json.dumps(PLAN)))
    gw, rd, _ = gateway(tmp_path, base_cfg, client)
    req = plan_request()
    res = await gw.call(req)

    assert isinstance(res.parsed, PlanOutput) and res.parsed.criteria_skipped[0].criterion_id == "verifiability"
    assert res.stop_reason == "end_turn" and res.model == MODEL and res.call_id == "llm-0001"
    assert res.content[0] == {"type": "thinking", "thinking": "", "signature": "sig-abc"}   # byte-faithful
    assert res.assistant_message() == {"role": "assistant", "content": res.content}
    assert res.usage.total_input_tokens == 1150 and gw.usage_total() == res.usage
    assert gw.served_models() == {MODEL} and gw.fallback_events() == [] and res.fallback is None
    assert res.request_id == "req_fake" and len(res.attempts) == 1 and res.attempts[0].outcome == "ok"
    sent = client.messages.calls[0]
    assert sent == gw.build_body(req) and not client.beta.messages.calls

    [entry] = log_entries(rd)
    assert entry["backend"] == "anthropic_api" and entry["outcome"] == "ok" and entry["phase"] == "plan"
    for key in ("call_id", "purpose", "conversation_id", "request_sha256", "model", "stop_reason", "started_at",
                "usage", "content"):
        assert key in entry
    assert entry["request_sha256"] == request_sha256(sent) == res.request_sha256
    pdf = entry["request"]["messages"][0]["content"][0]["source"]["data"]
    assert pdf.startswith("sha256:") and entry["pdf_sha256"] == [pdf.removeprefix("sha256:")]
    assert entry["content"] == res.content and entry["usage"]["cache_creation_input_tokens"] == 1000


async def test_refusal_is_typed_recorded_and_not_retried(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    client = FakeClient(message(stop="refusal", text='{"questions": [', stop_details={
        "type": "refusal", "category": "cyber", "explanation": "declined"}))
    gw, rd, _ = gateway(tmp_path, base_cfg, client)
    with pytest.raises(LLMRefusalError) as info:
        await gw.call(plan_request())
    assert info.value.category == "cyber" and info.value.explanation == "declined"
    assert gw.refusals() == [{"call_id": "llm-0001", "stage": "plan", "category": "cyber"}]
    assert len(client.messages.calls) == 1
    [entry] = log_entries(rd)
    assert entry["outcome"] == "LLMRefusalError" and entry["content"] == []          # partial output discarded
    assert entry["stop_details"]["category"] == "cyber"


async def test_refusal_with_null_category(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, _, _ = gateway(tmp_path, base_cfg, FakeClient(message(stop="refusal", content=[])))
    with pytest.raises(LLMRefusalError) as info:
        await gw.call(plan_request())
    assert info.value.category is None and gw.refusals()[0]["category"] is None


async def test_max_tokens_is_truncation_not_retried(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    client = FakeClient(message(stop="max_tokens", text='{"questions": [{"id": "RQ-'))
    gw, rd, _ = gateway(tmp_path, base_cfg, client)
    with pytest.raises(LLMTruncatedError) as info:
        await gw.call(plan_request())
    assert info.value.max_tokens == 4000 and len(client.messages.calls) == 1
    assert log_entries(rd)[0]["outcome"] == "LLMTruncatedError"
    assert info.value.usage == Usage(100, 20, 1000, 50)            # billed: the phase counts it in the budget


async def test_tool_use_and_pause_turn(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    tool_msg = message(stop="tool_use", content=[
        {"type": "thinking", "thinking": "", "signature": "s"},
        {"type": "tool_use", "id": "toolu_1", "name": "srv__search", "input": {"query": "room booking limits"}}])
    client = FakeClient(tool_msg, message(stop="pause_turn", text="partial"))
    gw, _, _ = gateway(tmp_path, base_cfg, client)
    res = await gw.call(plan_request(schema=None))
    assert res.stop_reason == "tool_use" and res.parsed is None
    assert [(t.id, t.name, t.input) for t in res.tool_uses] == [("toolu_1", "srv__search",
                                                                  {"query": "room booking limits"})]
    paused = await gw.call(plan_request(conv="plan-1"))
    assert paused.stop_reason == "pause_turn" and paused.parsed is None and paused.text == "partial"


async def test_schema_error_not_retried(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    client = FakeClient(message(text='{"questions": "not a list"}'), message(content=[]))
    gw, rd, _ = gateway(tmp_path, base_cfg, client)
    with pytest.raises(LLMSchemaError):
        await gw.call(plan_request())
    with pytest.raises(LLMSchemaError):                                  # end_turn with no text block
        await gw.call(plan_request(conv="plan-1"))
    assert len(client.messages.calls) == 2
    first = log_entries(rd)[0]
    assert first["outcome"] == "LLMSchemaError" and first["content"][1]["text"] == '{"questions": "not a list"}'


async def test_effort_change_rejected(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, _, _ = gateway(tmp_path, base_cfg, FakeClient(message(text=json.dumps(PLAN))))
    await gw.call(plan_request())
    with pytest.raises(EffortChangedError):
        await gw.call(plan_request(effort="medium"))


# ------------------------------------------------------------------------------ retry policy


async def test_429_honours_retry_after(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    client = FakeClient(status_error(anthropic.RateLimitError, 429, headers={"retry-after": "7"}),
                        message(text=json.dumps(PLAN)))
    gw, rd, clock = gateway(tmp_path, base_cfg, client)
    res = await gw.call(plan_request())
    assert clock.monotonic() == pytest.approx(7.0)                       # slept exactly retry-after
    assert [a.outcome for a in res.attempts] == ["LLMRateLimitError", "ok"]
    assert res.attempts[0].status_code == 429 and res.attempts[0].retry_after_s == 7.0
    entries = log_entries(rd)
    assert [e["outcome"] for e in entries] == ["LLMRateLimitError", "ok"]
    assert [e["attempt"] for e in entries] == [0, 1] and "request" in entries[0] and "request" not in entries[1]
    assert {e["call_id"] for e in entries} == {"llm-0001"}


async def test_529_backs_off_with_jitter(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    overloaded_mid_stream = MidStream(status_error(anthropic.APIStatusError, 200, body={
        "type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}))
    client = FakeClient(status_error(anthropic.OverloadedError, 529), overloaded_mid_stream,
                        message(text=json.dumps(PLAN)))
    gw, _, clock = gateway(tmp_path, base_cfg, client)
    res = await gw.call(plan_request())
    base = base_cfg.agent.llm.backoff_base_s
    assert [a.outcome for a in res.attempts] == ["LLMOverloadedError", "LLMOverloadedError", "ok"]
    # attempt 0 sleeps in [base/2, base], attempt 1 in [base, 2*base]
    assert 1.5 * base <= clock.monotonic() <= 3 * base
    assert res.attempts[0].retry_after_s is None


async def test_retry_budget_exhausted(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    cfg = cfg_with(base_cfg, max_retries=2)
    client = FakeClient(*[status_error(anthropic.OverloadedError, 529) for _ in range(3)])
    gw, rd, _ = gateway(tmp_path, cfg, client)
    with pytest.raises(LLMOverloadedError):
        await gw.call(plan_request())
    assert len(client.messages.calls) == 3 and len(log_entries(rd)) == 3

    timeouts = FakeClient(anthropic.APIConnectionError(request=REQ), anthropic.APITimeoutError(request=REQ),
                          TimeoutError())
    gw2, _, _ = gateway(tmp_path / "t", cfg, timeouts)
    with pytest.raises(LLMTimeoutError):
        await gw2.call(plan_request())
    assert len(timeouts.messages.calls) == 3

    rate = FakeClient(*[status_error(anthropic.RateLimitError, 429) for _ in range(3)])
    gw3, _, _ = gateway(tmp_path / "r", cfg, rate)
    with pytest.raises(LLMRateLimitError) as info:
        await gw3.call(plan_request())
    assert info.value.retry_after_s is None                              # no header: backoff, then typed error


async def test_auth_error_not_retried_and_key_never_logged(tmp_path: Path, base_cfg: EffectiveConfig,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sk-ant-api03-SECRET-VALUE"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    client = FakeClient(status_error(anthropic.AuthenticationError, 401), status_error(
        anthropic.PermissionDeniedError, 403))
    gw, rd, _ = gateway(tmp_path, base_cfg, client)
    with pytest.raises(LLMAuthError) as info:
        await gw.call(plan_request())
    assert "ANTHROPIC_API_KEY" in str(info.value) and secret not in str(info.value)
    assert len(client.messages.calls) == 1
    with pytest.raises(LLMAuthError):
        await gw.call(plan_request(conv="plan-1"))
    assert secret not in rd.llm_log.read_text(encoding="utf-8")


async def test_bad_request_not_retried(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    client = FakeClient(status_error(anthropic.BadRequestError, 400, body={
        "type": "error", "error": {"type": "invalid_request_error", "message": "temperature is not supported"}}))
    gw, _, _ = gateway(tmp_path, base_cfg, client)
    with pytest.raises(LLMBadRequestError) as info:
        await gw.call(plan_request())
    assert int(info.value.exit_code) == 4 and len(client.messages.calls) == 1


async def test_non_sdk_exception_propagates(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, _, _ = gateway(tmp_path, base_cfg, FakeClient(RuntimeError("bug")))
    with pytest.raises(RuntimeError):
        await gw.call(plan_request())


# ------------------------------------------------------------------------------ fallback, served models


async def test_fallback_goes_through_beta_and_is_recorded(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    fb_msg = message(beta=True, model="claude-opus-5", content=[
        {"type": "fallback", "from": {"model": MODEL}, "to": {"model": "claude-opus-5"},
         "trigger": {"type": "refusal", "category": "cyber"}},
        {"type": "text", "text": json.dumps(PLAN)}],
        usage={"input_tokens": 10, "output_tokens": 5, "iterations": [
            {"type": "message", "input_tokens": 5, "output_tokens": 0, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 0},
            {"type": "fallback_message", "model": "claude-opus-5", "input_tokens": 5, "output_tokens": 5,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}]})
    client = FakeClient(beta=[fb_msg])
    gw, rd, _ = gateway(tmp_path, cfg_with(base_cfg, allow_fallback=True), client)
    res = await gw.call(plan_request())
    assert not client.messages.calls and client.beta.messages.calls[0]["betas"] == [FALLBACK_BETA]
    assert client.beta.messages.calls[0]["fallbacks"] == "default"
    assert res.fallback is not None and res.fallback.to_model == "claude-opus-5" and res.fallback.from_model == MODEL
    assert "cyber" in res.fallback.reason and gw.fallback_events() == [res.fallback]
    assert gw.served_models() == {"claude-opus-5"} and isinstance(res.parsed, PlanOutput)
    assert res.content[0]["from"] == {"model": MODEL}                    # API field names, as returned
    entry = log_entries(rd)[0]
    assert entry["fallback"]["to_model"] == "claude-opus-5"
    assert entry["usage_raw"]["iterations"][1]["type"] == "fallback_message"


async def test_served_model_mismatch_without_fallback_opt_in(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, _, _ = gateway(tmp_path, base_cfg, FakeClient(message(text=json.dumps(PLAN), model="claude-opus-5")))
    res = await gw.call(plan_request())
    assert res.fallback is not None and "differs" in res.fallback.reason
    assert gw.served_models() == {"claude-opus-5"}


# ------------------------------------------------------------------------------ models.retrieve, preflight


async def test_models_retrieve(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    info = ModelInfo.model_validate({"id": MODEL, "type": "model", "display_name": "Claude Opus 5.5",
                                     "created_at": "2026-09-01T00:00:00Z", "max_input_tokens": 1000000,
                                     "max_tokens": 128000})
    client = FakeClient(model_info=info)
    gw, _, _ = gateway(tmp_path, base_cfg, client)
    assert await gw.models_retrieve() == {"id": MODEL, "created_at": "2026-09-01T00:00:00Z",
                                          "max_input_tokens": 1000000, "max_tokens": 128000}
    assert client.models.calls == [MODEL]

    gw2, _, _ = gateway(tmp_path / "x", base_cfg, FakeClient(model_info=status_error(
        anthropic.AuthenticationError, 401)))
    with pytest.raises(LLMAuthError):
        await gw2.models_retrieve()


async def test_preflight(tmp_path: Path, base_cfg: EffectiveConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(message(stop="max_tokens", content=[]))
    gw, rd, _ = gateway(tmp_path, base_cfg, client)
    await gw.preflight()                                                 # max_tokens is fine for a ping
    assert client.messages.calls[0]["max_tokens"] == 1 and not rd.llm_log.exists()

    bad = FakeClient(status_error(anthropic.AuthenticationError, 401), status_error(anthropic.OverloadedError, 529))
    gw2, _, _ = gateway(tmp_path / "b", base_cfg, bad)
    with pytest.raises(LLMAuthError) as info:
        await gw2.preflight()
    assert "ANTHROPIC_API_KEY" in str(info.value)
    with pytest.raises(LLMOverloadedError):                              # fail fast: no retries in preflight
        await gw2.preflight()
    assert len(bad.messages.calls) == 2

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    no_key = AnthropicGateway(base_cfg, RunDir(tmp_path / "n").create(), clock=FakeClock())
    with pytest.raises(LLMAuthError) as info2:
        await no_key.preflight()
    assert "ANTHROPIC_API_KEY is not set" in str(info2.value)


# ------------------------------------------------------------------------------ llm_facing_schema


class _Inner(BaseModel):
    format: str = Field(pattern=r"^[a-z]+$", max_length=5)     # a property *named* like a keyword


class _WithMap(BaseModel):
    counts: dict[str, int]
    inner: _Inner
    score: float = Field(ge=0, le=1)
    tags: list[str] = Field(min_length=1, max_length=3)


def _objects(node: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            out.append(node)
        for v in node.values():
            out += _objects(v)
    elif isinstance(node, list):
        for v in node:
            out += _objects(v)
    return out


@pytest.mark.parametrize("name", sorted(PHASE_OUTPUT_TYPES))
def test_llm_facing_schema_is_closed_and_valid(name: str) -> None:
    schema = llm_facing_schema(PHASE_OUTPUT_TYPES[name])
    jsonschema.Draft202012Validator.check_schema(schema)
    assert all(o.get("additionalProperties") is False for o in _objects(schema))
    text = json.dumps(schema)
    for kw in ("minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems", "pattern", '"format"'):
        assert kw not in text


def test_llm_facing_schema_strips_keywords_keeps_maps_and_names() -> None:
    schema = llm_facing_schema(_WithMap)
    jsonschema.Draft202012Validator.check_schema(schema)
    props = schema["properties"]
    assert props["counts"]["additionalProperties"] == {"type": "integer"}          # map stays open
    assert props["score"] == {"title": "Score", "type": "number"}
    assert "minItems" not in props["tags"] and "maxItems" not in props["tags"]
    inner = schema["$defs"]["_Inner"]
    assert inner["properties"]["format"] == {"title": "Format", "type": "string"}  # name kept, keywords gone
    assert inner["required"] == ["format"] and inner["additionalProperties"] is False
    jsonschema.Draft202012Validator(schema).validate({"counts": {"a": 1}, "inner": {"format": "ABC123"},
                                                       "score": 7, "tags": []})
