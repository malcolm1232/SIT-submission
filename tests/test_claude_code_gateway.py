"""ClaudeCodeGateway (ADR-010) against a fake ``claude -p`` runner: offline, no subprocess."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from sit_review_agent.clock import FakeClock
from sit_review_agent.config import EffectiveConfig, load_config
from sit_review_agent.errors import (
    EffortChangedError,
    LLMAuthError,
    LLMBadRequestError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMTruncatedError,
    LLMUnavailableError,
)
from sit_review_agent.llm.backend import build_llm_gateway, supports_native_pdf
from sit_review_agent.llm.claude_code import (
    TEXT_SCHEMA,
    ClaudeCodeGateway,
    CompletedRun,
    _schema_for,
    render_tool_catalogue,
)
from sit_review_agent.llm.gateway import AnthropicGateway, FakeGateway, LLMGateway, LLMRequest
from sit_review_agent.llm.outputs import AssessOutput, PlanOutput
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.states import PhaseName

PLAN = {"questions": [], "criteria_skipped": [{"criterion_id": "security", "reason": "n/a"}]}
TOOLS = [{"name": "mcp-internet-search__search", "description": "Web search.",
          "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}]


def cli_result(structured: Any = None, *, is_error: bool = False, result: str = "", stop: str = "tool_use",
               model: str = "claude-opus-5-5", cost: float = 0.01, n: int = 1,
               model_usage: dict[str, Any] | None = None) -> dict[str, Any]:
    """A ``claude -p`` result. ``cost`` and ``modelUsage`` are cumulative over the CLI session, as
    the real CLI reports them: ``n`` is how many calls of 100 in / 20 out tokens the session holds."""
    return {"type": "result", "subtype": "error_during_execution" if is_error else "success", "is_error": is_error,
            "result": result, "structured_output": structured, "stop_reason": stop, "session_id": "ignored",
            "num_turns": 2, "total_cost_usd": cost, "terminal_reason": "completed",
            "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 1000,
                      "cache_read_input_tokens": 50},
            "modelUsage": model_usage or {model: {"inputTokens": 100 * n, "outputTokens": 20 * n, "costUSD": cost}}}


class FakeRunner:
    """Scripted runner: each item is a dict (JSON stdout, exit 0), a CompletedRun, or an exception."""

    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, argv: list[str], stdin: str, env: dict[str, str], cwd: Path,
                       timeout_s: float) -> CompletedRun:
        self.calls.append({"argv": argv, "stdin": stdin, "env": env, "cwd": cwd, "timeout_s": timeout_s})
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, CompletedRun):
            return item
        return CompletedRun(0, json.dumps(item), "")


def flag(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


@pytest.fixture(scope="module")
def base_cfg() -> EffectiveConfig:
    return load_config()


def cfg_with(base: EffectiveConfig, **llm: Any) -> EffectiveConfig:
    agent = base.agent.model_copy(update={"llm": base.agent.llm.model_copy(update=llm)})
    return base.model_copy(update={"agent": agent})


def make(tmp_path: Path, cfg: EffectiveConfig, *script: Any) -> tuple[ClaudeCodeGateway, FakeRunner, RunDir]:
    rd = RunDir(tmp_path / "run").create()
    runner = FakeRunner(*script)
    return ClaudeCodeGateway(cfg, rd, clock=FakeClock(), runner=runner), runner, rd


def req(messages: list[dict[str, Any]], *, schema: Any = PlanOutput, tools: list[dict[str, Any]] | None = None,
        conv: str = "plan-1", effort: str = "high", phase: PhaseName = PhaseName.PLAN) -> LLMRequest:
    return LLMRequest(phase=phase, conversation_id=conv, system="You are a reviewer.", messages=messages,
                      effort=effort, max_tokens=4321, tools=tools or [], output_schema=schema)  # type: ignore[arg-type]


def user(*texts: str) -> dict[str, Any]:
    return {"role": "user", "content": [{"type": "text", "text": t} for t in texts]}


# ------------------------------------------------------------------------------ (a) (b) (c)


async def test_first_call_shape_and_resume(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, runner, rd = make(tmp_path, base_cfg, cli_result(PLAN), cli_result({"text": "second"}, cost=0.02, n=2))
    msgs = [user("DOCUMENT TEXT", "Plan the review.")]
    res = await gw.call(req(msgs))
    first = runner.calls[0]
    argv = first["argv"]
    assert argv[:2] == ["claude", "-p"] and flag(argv, "--model") == "claude-opus-5-5"
    assert flag(argv, "--system-prompt") == "You are a reviewer."
    assert flag(argv, "--tools") == "" and flag(argv, "--disallowedTools") == "mcp__*"
    assert {"--strict-mcp-config", "--disable-slash-commands"} <= set(argv)
    assert flag(argv, "--output-format") == "json" and flag(argv, "--effort") == "high"
    assert "--bare" not in argv and "--no-session-persistence" not in argv and "--resume" not in argv
    assert "--fallback-model" not in argv and "--max-budget-usd" not in argv
    assert "DOCUMENT TEXT" not in " ".join(argv)
    assert first["stdin"] == "DOCUMENT TEXT\n\nPlan the review."
    assert first["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "4321"
    assert first["env"]["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1" == first["env"]["CLAUDE_CODE_DISABLE_ATTACHMENTS"]
    assert first["cwd"] == rd.root and first["timeout_s"] == base_cfg.agent.llm.timeout_s
    schema = json.loads(flag(argv, "--json-schema"))
    assert schema["required"] == ["questions", "criteria_skipped"] and schema["additionalProperties"] is False
    sid = flag(argv, "--session-id")

    assert isinstance(res.parsed, PlanOutput) and res.stop_reason == "end_turn"
    assert res.content == [{"type": "text", "text": res.text}] and json.loads(res.text) == PLAN
    assert res.model == "claude-opus-5-5" and res.request_id is None and res.resumed is False
    assert gw.usage_total().total_input_tokens == 1150 and gw.cost_total_usd == pytest.approx(0.01)
    assert gw.served_models() == {"claude-opus-5-5"}

    msgs2 = [*msgs, res.assistant_message(), user("Now say something.")]
    res2 = await gw.call(req(msgs2, schema=None))
    argv2 = runner.calls[1]["argv"]
    assert flag(argv2, "--resume") == sid and "--fork-session" in argv2
    assert flag(argv2, "--session-id") not in (sid, "--fork-session")
    assert runner.calls[1]["stdin"] == "Now say something."
    assert json.loads(flag(argv2, "--json-schema")) == TEXT_SCHEMA
    assert res2.text == "second" and res2.parsed is None
    assert gw.usage_total().output_tokens == 40 and gw.cost_total_usd == pytest.approx(0.02)


async def test_foreign_or_edited_assistant_turn_is_rejected(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, runner, _ = make(tmp_path, base_cfg, cli_result(PLAN))
    msgs = [user("doc")]
    res = await gw.call(req(msgs))
    forged = {"role": "assistant", "content": [{"type": "text", "text": "I never said this"}]}
    with pytest.raises(LLMBadRequestError, match="plan-1"):
        await gw.call(req([*msgs, res.assistant_message(), forged, user("next")]))
    with pytest.raises(LLMBadRequestError, match="plan-1"):
        await gw.call(req([*msgs, forged, user("next")]))
    with pytest.raises(LLMBadRequestError, match="append-only"):
        await gw.call(req([user("edited doc"), res.assistant_message(), user("next")]))
    with pytest.raises(LLMBadRequestError):          # an assistant prefill on a fresh conversation
        await gw.call(req([user("x"), forged], conv="other"))
    assert len(runner.calls) == 1


# ------------------------------------------------------------------------------ (d) tools


async def test_tool_envelope_and_id_renumbering(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    calls1 = {"tool_calls": [{"id": "call-0001", "name": TOOLS[0]["name"], "input": {"query": "a"}},
                             {"id": "", "name": TOOLS[0]["name"], "input": {"query": "b"}}], "final": None}
    calls2 = {"tool_calls": [{"id": "call-0001", "name": TOOLS[0]["name"], "input": {"query": "c"}}], "final": None}
    done = {"tool_calls": [], "final": PLAN}
    gw, runner, _ = make(tmp_path, base_cfg, cli_result(calls1), cli_result(calls2), cli_result(done))
    msgs = [user("doc")]
    r1 = await gw.call(req(msgs, tools=TOOLS))
    argv = runner.calls[0]["argv"]
    system = flag(argv, "--system-prompt")
    assert system.startswith("You are a reviewer.\n\n# Tools available in this phase")
    assert TOOLS[0]["name"] in system and '"query"' in system
    env_schema = json.loads(flag(argv, "--json-schema"))
    assert env_schema["required"] == ["tool_calls", "final"]
    final_any = env_schema["properties"]["final"]["anyOf"]
    assert final_any[0] == {"type": "null"} and "$defs" in env_schema and "$defs" not in final_any[1]
    jsonschema.Draft202012Validator.check_schema(env_schema)
    jsonschema.Draft202012Validator(env_schema).validate(done)

    assert r1.stop_reason == "tool_use" and r1.parsed is None
    assert [(t.id, t.input["query"]) for t in r1.tool_uses] == [("call-0001", "a"), ("call-0002", "b")]
    assert [b["type"] for b in r1.content] == ["tool_use", "tool_use"] and r1.content[1]["id"] == "call-0002"

    results = {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "call-0001", "content": "result A"},
        {"type": "tool_result", "tool_use_id": "call-0002", "content": [{"type": "text", "text": "result B"}],
         "is_error": True}]}
    msgs2 = [*msgs, r1.assistant_message(), results]
    r2 = await gw.call(req(msgs2, tools=TOOLS))
    assert runner.calls[1]["stdin"] == ("[tool result call-0001]\nresult A\n\n"
                                        "[tool result call-0002]\nresult B\n[is_error]")
    assert flag(runner.calls[1]["argv"], "--system-prompt") == system      # byte-stable across calls
    assert [t.id for t in r2.tool_uses] == ["call-0003"]                    # duplicate of call-0001 renumbered

    msgs3 = [*msgs2, r2.assistant_message(),
             {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call-0003", "content": "C"}]}]
    r3 = await gw.call(req(msgs3, tools=TOOLS))
    assert runner.calls[2]["stdin"] == "[tool result call-0003 (your id call-0001)]\nC"
    assert r3.stop_reason == "end_turn" and isinstance(r3.parsed, PlanOutput) and r3.tool_uses == []


def test_render_tool_catalogue_is_stable() -> None:
    a = render_tool_catalogue(TOOLS)
    assert a == render_tool_catalogue(json.loads(json.dumps(TOOLS)))
    assert a.startswith("# Tools available in this phase") and "## mcp-internet-search__search" in a
    assert "call-0001" in a and "final: null" in a and "tool_calls: []" in a
    # Live check (haiku): without this warning the model called `search` natively, got "No such tool
    # available" and answered without evidence.
    assert "NOT functions you can invoke" in a and "No such tool available" in a


async def test_envelope_with_neither_calls_nor_final(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, runner, _ = make(tmp_path, base_cfg, cli_result({"tool_calls": [], "final": None}))
    with pytest.raises(LLMSchemaError):
        await gw.call(req([user("doc")], tools=TOOLS))
    assert len(runner.calls) == 1


# ------------------------------------------------------------------------------ (e) final parsing


async def test_final_validated_against_output_schema(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    bad = {"questions": "not a list", "criteria_skipped": []}
    gw, runner, _ = make(tmp_path, base_cfg, cli_result(bad), cli_result({"tool_calls": [], "final": PLAN}))
    with pytest.raises(LLMSchemaError):
        await gw.call(req([user("doc")]))
    assert len(runner.calls) == 1                      # schema errors are not retried
    res = await gw.call(req([user("doc")], tools=TOOLS, conv="c2"))
    assert isinstance(res.parsed, PlanOutput) and res.parsed.criteria_skipped[0].criterion_id == "security"
    assert res.text == res.parsed.model_dump_json()


# ------------------------------------------------------------------------------ (f) errors, (i) log


async def test_auth_error_is_not_retried(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, runner, rd = make(tmp_path, base_cfg,
                          cli_result(is_error=True, result="Authentication error: invalid credentials"))
    with pytest.raises(LLMAuthError) as info:
        await gw.call(req([user("doc")]))
    assert "Claude Code login / host credentials" in str(info.value)
    assert len(runner.calls) == 1
    log = JsonlWriter(rd.llm_log).read()
    assert [e["outcome"] for e in log] == ["LLMAuthError"] and log[0]["backend"] == "claude_code"


async def test_rate_limit_retried_then_raised(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    cfg = cfg_with(base_cfg, max_retries=2)
    limited = cli_result(is_error=True, result="API Error: 429 rate limit exceeded")
    gw, runner, rd = make(tmp_path, cfg, limited, limited, limited)
    with pytest.raises(LLMRateLimitError) as info:
        await gw.call(req([user("doc")]))
    assert info.value.retry_after_s is None
    assert len(runner.calls) == 3
    assert gw.clock.monotonic() > 0                    # backoff slept on the FakeClock
    sids = [flag(c["argv"], "--session-id") for c in runner.calls]
    assert len(set(sids)) == 3                         # unconfirmed first session: fresh uuid per attempt
    log = JsonlWriter(rd.llm_log).read()
    assert [e["attempt"] for e in log] == [0, 1, 2] and {e["outcome"] for e in log} == {"LLMRateLimitError"}


async def test_transient_failures_then_success_are_logged(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, runner, rd = make(tmp_path, base_cfg,
                          TimeoutError(),
                          CompletedRun(1, "not json", "boom: network down"),
                          cli_result(is_error=True, result="Overloaded (529)"),
                          cli_result(PLAN))
    res = await gw.call(req([user("doc")]))
    assert [a.outcome for a in res.attempts] == ["LLMTimeoutError", "LLMUnavailableError", "LLMOverloadedError",
                                                 "ok"]
    log = JsonlWriter(rd.llm_log).read()
    assert [e["outcome"] for e in log] == ["LLMTimeoutError", "LLMUnavailableError", "LLMOverloadedError", "ok"]
    assert "boom: network down" in log[1]["error"]
    ok = log[-1]
    assert ok["call_id"] == res.call_id and ok["request_sha256"] == res.request_sha256
    assert ok["content"] == res.content and ok["num_turns"] == 2 and ok["total_cost_usd"] == 0.01
    assert ok["cli_session_id"] == flag(runner.calls[-1]["argv"], "--session-id")
    assert ok["argv"][ok["argv"].index("--system-prompt") + 1].startswith("sha256:")
    assert ok["argv"][ok["argv"].index("--json-schema") + 1].startswith("sha256:")
    assert ok["prompt_sha256"] and ok["pdf_dropped"] is False and ok["terminal_reason"] == "completed"
    for key in ("phase", "purpose", "conversation_id", "model", "stop_reason", "started_at", "usage"):
        assert key in ok


async def test_timeouts_exhaust_into_timeout_error(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, runner, _ = make(tmp_path, cfg_with(base_cfg, max_retries=1), TimeoutError(), TimeoutError())
    with pytest.raises(LLMTimeoutError):
        await gw.call(req([user("doc")]))
    gw2, _, _ = make(tmp_path / "b", cfg_with(base_cfg, max_retries=0), cli_result(is_error=True, result="weird"))
    with pytest.raises(LLMUnavailableError):
        await gw2.call(req([user("doc")]))


# ------------------------------------------------------------------------------ (g) stop reasons


async def test_cli_stop_reasons(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, runner, _ = make(tmp_path, base_cfg, cli_result(None, stop="max_tokens"), cli_result(None, stop="refusal"))
    with pytest.raises(LLMTruncatedError) as trunc:
        await gw.call(req([user("doc")], conv="a"))
    assert trunc.value.max_tokens == 4321
    with pytest.raises(LLMRefusalError) as ref:
        await gw.call(req([user("doc")], conv="b"))
    assert ref.value.category is None
    assert gw.refusals() == [{"call_id": ref.value.call_id, "stage": "plan", "category": None}]
    assert len(runner.calls) == 2


async def test_cli_output_cap_error_is_a_truncation_not_an_outage(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    """What `claude -p` 2.1.287 really returns when the answer hits CLAUDE_CODE_MAX_OUTPUT_TOKENS
    (captured on Haiku, 2026-10-03): an error result, not ``stop_reason: max_tokens``. It used to
    be classed as LLMUnavailableError and retried ``llm.max_retries`` times at the same cap."""
    msg = ("API Error: Claude's response exceeded the 256 output token maximum. To configure this behavior, set "
           "the CLAUDE_CODE_MAX_OUTPUT_TOKENS environment variable.")
    out = {**cli_result(None, is_error=True, result=msg, stop="stop_sequence"), "terminal_reason": "api_error",
           "num_turns": 4}
    gw, runner, rd = make(tmp_path, base_cfg, out, cli_result(PLAN))
    with pytest.raises(LLMTruncatedError) as trunc:
        await gw.call(req([user("doc")], conv="a"))
    assert trunc.value.max_tokens == 4321 and "output token maximum" in str(trunc.value)
    assert len(runner.calls) == 1                                    # not retried by the gateway
    assert runner.calls[0]["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "4321"
    entry = json.loads(rd.llm_log.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["outcome"] == "LLMTruncatedError" and entry["usage"]["output_tokens"] == 20   # spend is counted
    # a 128000 cap reads the same way (the number is not mistaken for an HTTP status)
    big = {**out, "result": msg.replace("256", "128000")}
    gw2, runner2, _ = make(tmp_path / "b", base_cfg, big)
    with pytest.raises(LLMTruncatedError):
        await gw2.call(req([user("doc")], conv="a"))
    assert len(runner2.calls) == 1


# ------------------------------------------------------------------------------ (h) PDF


async def test_document_block_dropped_and_logged(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, runner, rd = make(tmp_path, base_cfg, cli_result(PLAN))
    doc = {"type": "document", "title": "d", "source": {"type": "base64", "media_type": "application/pdf",
                                                         "data": "JVBERi0xLjQK"}}
    await gw.call(req([{"role": "user", "content": [doc, {"type": "text", "text": "canonical"}]}]))
    stdin = runner.calls[0]["stdin"]
    assert stdin.startswith("[document omitted: application/pdf, sha256:")
    assert "JVBERi0xLjQK" not in stdin and stdin.endswith("\n\ncanonical")
    assert JsonlWriter(rd.llm_log).read()[0]["pdf_dropped"] is True
    assert gw.native_pdf is False and supports_native_pdf(gw) is False
    assert supports_native_pdf(FakeGateway({})) is True


# ------------------------------------------------------------------------------ (j) factory


def test_build_llm_gateway_picks_backend(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    rd = RunDir(tmp_path / "r").create()
    assert base_cfg.agent.llm.backend == "claude_code"
    cc = build_llm_gateway(base_cfg, rd)
    assert isinstance(cc, ClaudeCodeGateway) and isinstance(cc, LLMGateway)
    api = build_llm_gateway(cfg_with(base_cfg, backend="anthropic_api"), rd)
    assert isinstance(api, AnthropicGateway) and supports_native_pdf(api) is True


def test_fallback_and_budget_flags(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    cc = base_cfg.agent.claude_code.model_copy(update={"max_budget_usd_per_call": 0.5, "extra_args": ["--verbose"]})
    cfg = base_cfg.model_copy(update={"agent": base_cfg.agent.model_copy(
        update={"allow_fallback": True, "claude_code": cc})})
    gw = ClaudeCodeGateway(cfg, RunDir(tmp_path / "r"), runner=FakeRunner())
    argv = gw.build_argv(req([user("x")]), system_text="s", schema_json="{}", session_uuid="u")
    assert flag(argv, "--fallback-model") and flag(argv, "--max-budget-usd") == "0.5" and argv[-1] == "--verbose"
    from sit_review_agent.errors import ConfigError

    bad = base_cfg.model_copy(update={"agent": base_cfg.agent.model_copy(
        update={"claude_code": cc.model_copy(update={"extra_args": ["--bare"]})})})
    with pytest.raises(ConfigError):
        ClaudeCodeGateway(bad, RunDir(tmp_path / "r"))


async def test_fallback_event_when_served_model_differs(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    cfg = base_cfg.model_copy(update={"agent": base_cfg.agent.model_copy(update={"allow_fallback": True})})
    gw, _, _ = make(tmp_path, cfg, cli_result(PLAN, model="claude-opus-5"))
    res = await gw.call(req([user("doc")]))
    assert res.model == "claude-opus-5" and res.fallback is not None
    assert gw.fallback_events()[0].to_model == "claude-opus-5"


async def test_preflight(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, runner, _ = make(tmp_path, base_cfg, CompletedRun(0, "2.1.287 (Claude Code)", ""),
                         FileNotFoundError("claude"), CompletedRun(1, "", "bad"))
    await gw.preflight()
    assert runner.calls[0]["argv"] == ["claude", "--version"] and runner.calls[0]["timeout_s"] == 30
    for _ in range(2):
        with pytest.raises(LLMAuthError, match="claude --version"):
            await gw.preflight()


# ------------------------------------------------------------------------------ (k) schema, (l) effort


def test_schema_for_assess_output_is_closed_and_valid() -> None:
    schema = _schema_for(AssessOutput)
    jsonschema.Draft202012Validator.check_schema(schema)
    assert "$defs" in schema

    def objects(node: Any) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if isinstance(node, dict):
            if node.get("type") == "object":
                found.append(node)
            for v in node.values():
                found += objects(v)
        elif isinstance(node, list):
            for v in node:
                found += objects(v)
        return found

    objs = objects(schema)
    assert len(objs) > 5 and all(o.get("additionalProperties") is False for o in objs)
    jsonschema.Draft202012Validator(schema).validate({"findings": [], "sound_areas": [], "coverage": []})


async def test_effort_change_within_conversation(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, runner, _ = make(tmp_path, base_cfg, cli_result(PLAN))
    res = await gw.call(req([user("doc")]))
    with pytest.raises(EffortChangedError):
        await gw.call(req([user("doc"), res.assistant_message(), user("more")], effort="max"))
    assert len(runner.calls) == 1


# ------------------------------------------------------------------------------ default runner


async def test_subprocess_runner_stdin_env_cwd_and_timeout(tmp_path: Path) -> None:
    import sys

    from sit_review_agent.llm.claude_code import subprocess_runner

    code = "import os,sys; print(sys.stdin.read().upper() + os.environ['X_T'] + os.getcwd())"
    run = await subprocess_runner([sys.executable, "-c", code], "hello", {"X_T": "!", "PATH": ""}, tmp_path, 30)
    assert run.returncode == 0 and run.stdout.strip() == "HELLO!" + str(tmp_path)
    with pytest.raises(TimeoutError):
        await subprocess_runner([sys.executable, "-c", "import time; time.sleep(30)"], "", {}, tmp_path, 0.2)


# ------------------------------------------------------------------------------ verifier regressions


async def test_api_keys_stripped_from_child_env_unless_inherited(tmp_path: Path, base_cfg: EffectiveConfig,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-1")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "secret-2")
    assert base_cfg.agent.claude_code.inherit_api_key is False
    gw, runner, rd = make(tmp_path, base_cfg, cli_result(PLAN))
    await gw.call(req([user("doc")]))
    env = runner.calls[0]["env"]
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
    assert "PATH" in env and env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1"
    assert "sk-ant-secret-1" not in rd.llm_log.read_text() and "secret-2" not in rd.llm_log.read_text()

    cc = base_cfg.agent.claude_code.model_copy(update={"inherit_api_key": True})
    cfg = base_cfg.model_copy(update={"agent": base_cfg.agent.model_copy(update={"claude_code": cc})})
    gw2, runner2, _ = make(tmp_path / "b", cfg, cli_result(PLAN))
    await gw2.call(req([user("doc")]))
    assert runner2.calls[0]["env"]["ANTHROPIC_API_KEY"] == "sk-ant-secret-1"


async def test_cumulative_cost_and_model_usage_counted_per_call(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    # Verified live: on --resume (and in a fork) total_cost_usd and modelUsage are session totals.
    cfg = base_cfg.model_copy(update={"agent": base_cfg.agent.model_copy(update={"allow_fallback": True})})
    opus55 = {"inputTokens": 100, "outputTokens": 20}
    opus5 = {"inputTokens": 100, "outputTokens": 20}
    gw, _, rd = make(tmp_path, cfg,
                     cli_result({"text": "1"}, cost=0.01),
                     cli_result({"text": "2"}, cost=0.03,
                                model_usage={"claude-opus-5-5": opus55, "claude-opus-5": opus5}),
                     cli_result({"text": "3"}, cost=0.04,
                                model_usage={"claude-opus-5-5": {"inputTokens": 200, "outputTokens": 40},
                                             "claude-opus-5": opus5}))
    msgs = [user("a")]
    r1 = await gw.call(req(msgs, schema=None))
    msgs += [r1.assistant_message(), user("b")]
    # Call 2: only claude-opus-5 did work in this call (opus-5-5's counters did not move).
    r2 = await gw.call(req(msgs, schema=None))
    msgs += [r2.assistant_message(), user("c")]
    r3 = await gw.call(req(msgs, schema=None))
    assert (r1.model, r2.model, r3.model) == ("claude-opus-5-5", "claude-opus-5", "claude-opus-5-5")
    assert r1.fallback is None and r2.fallback is not None and r3.fallback is None
    assert len(gw.fallback_events()) == 1
    assert gw.cost_total_usd == pytest.approx(0.04)
    assert [e["call_cost_usd"] for e in JsonlWriter(rd.llm_log).read()] == pytest.approx([0.01, 0.02, 0.01])


async def test_failed_attempts_never_continue_a_polluted_session(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    # Verified live: a killed `--resume` call leaves its user turn in that session's transcript, so
    # every resumed attempt forks from the last good session into a fresh id.
    gw, runner, _ = make(tmp_path, base_cfg,
                         cli_result({"text": "1"}),
                         TimeoutError(),
                         cli_result({"text": "2"}, cost=0.02, n=2),
                         cli_result(None, stop="refusal", cost=0.03, n=3),
                         cli_result({"text": "3"}, cost=0.03, n=3))
    msgs = [user("a")]
    r1 = await gw.call(req(msgs, schema=None))
    sid1 = flag(runner.calls[0]["argv"], "--session-id")
    msgs += [r1.assistant_message(), user("b")]
    r2 = await gw.call(req(msgs, schema=None))
    a_timeout, a_ok = runner.calls[1]["argv"], runner.calls[2]["argv"]
    assert flag(a_timeout, "--resume") == sid1 == flag(a_ok, "--resume")
    assert "--fork-session" in a_timeout and "--fork-session" in a_ok
    assert len({sid1, flag(a_timeout, "--session-id"), flag(a_ok, "--session-id")}) == 3
    assert runner.calls[1]["stdin"] == runner.calls[2]["stdin"] == "b"
    sid2 = flag(a_ok, "--session-id")

    msgs += [r2.assistant_message(), user("c")]
    with pytest.raises(LLMRefusalError):
        await gw.call(req(msgs, schema=None))
    # The phase retries with reframed wording in place of the refused turn (robustness LLM-06).
    await gw.call(req([*msgs[:-1], user("c, reframed")], schema=None))
    assert flag(runner.calls[3]["argv"], "--resume") == sid2 == flag(runner.calls[4]["argv"], "--resume")
    assert runner.calls[4]["stdin"] == "c, reframed"
    assert gw.cost_total_usd == pytest.approx(0.04)     # 0.01 + 0.01 + 0.01 (refused) + 0.01


@pytest.mark.parametrize(("out", "error"), [
    (cli_result(is_error=True, result="Invalid API key · Please run /login"), LLMAuthError),
    (cli_result(is_error=True, result="API Error: 400 invalid_request_error: Prompt is too long"), LLMBadRequestError),
    ({**cli_result(is_error=True), "result": None, "errors": ["OAuth token has expired"]}, LLMAuthError),
    ({**cli_result(is_error=True), "subtype": "error_max_structured_output_retries", "result": None,
      "errors": ["no valid output"]}, LLMSchemaError),
])
async def test_non_retryable_cli_errors(tmp_path: Path, base_cfg: EffectiveConfig, out: dict[str, Any],
                                        error: type[Exception]) -> None:
    gw, runner, _ = make(tmp_path, base_cfg, out, cli_result(PLAN))
    with pytest.raises(error):
        await gw.call(req([user("doc")]))
    assert len(runner.calls) == 1


async def test_error_text_in_errors_list_is_classified(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    # `error_*` subtypes carry no `result`, only `errors`; status digits inside numbers do not count.
    limited = {**cli_result(is_error=True), "result": None, "errors": ["API Error: 429 rate_limit_error"]}
    gw, runner, _ = make(tmp_path, cfg_with(base_cfg, max_retries=1), limited, limited)
    with pytest.raises(LLMRateLimitError):
        await gw.call(req([user("doc")]))
    assert len(runner.calls) == 2
    gw2, _, _ = make(tmp_path / "b", cfg_with(base_cfg, max_retries=0),
                     cli_result(is_error=True, result="context of 14290 tokens lost"))
    with pytest.raises(LLMUnavailableError):
        await gw2.call(req([user("doc")]))


async def test_assistant_turn_must_stay_where_it_was_returned(tmp_path: Path, base_cfg: EffectiveConfig) -> None:
    gw, runner, _ = make(tmp_path, base_cfg, cli_result(PLAN), cli_result(PLAN, cost=0.02, n=2))
    msgs = [user("doc")]
    res = await gw.call(req(msgs))
    with pytest.raises(LLMBadRequestError, match="append-only"):
        await gw.call(req([*msgs, user("inserted"), res.assistant_message(), user("next")]))
    await gw.call(req([*msgs, res.assistant_message(), user("next")]))      # the legitimate append
    assert len(runner.calls) == 2


def test_output_schema_uses_llm_facing_schema_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    from sit_review_agent.llm import claude_code, outputs

    def stub(model: type) -> dict[str, Any]:
        raise NotImplementedError

    monkeypatch.setattr(outputs, "llm_facing_schema", stub)
    assert claude_code._output_schema(PlanOutput) == _schema_for(PlanOutput)
    monkeypatch.setattr(outputs, "llm_facing_schema", lambda model: {"type": "object", "title": model.__name__})
    assert claude_code._output_schema(PlanOutput) == {"type": "object", "title": "PlanOutput"}


def test_schema_for_keeps_maps_open() -> None:
    from pydantic import BaseModel

    class Inner(BaseModel):
        x: int

    class WithMap(BaseModel):
        counts: dict[str, int]
        inner: Inner

    schema = _schema_for(WithMap)
    assert schema["additionalProperties"] is False and schema["$defs"]["Inner"]["additionalProperties"] is False
    assert schema["properties"]["counts"]["additionalProperties"] == {"type": "integer"}
    jsonschema.Draft202012Validator(schema).validate({"counts": {"a": 1}, "inner": {"x": 1}})
