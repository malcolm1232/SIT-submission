"""ClaudeCodeJudge and AnthropicJudge with injected runners/clients (no CLI, no network)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from sit_eval.judge import FakeJudge, JudgeError, JudgeRequest, build_judge
from sit_eval.live_judges import AnthropicJudge, ClaudeCodeJudge
from sit_eval.prompts import judge_schema
from sit_review_agent.llm.claude_code import CompletedRun

SECRET_USER = "USER PROMPT TEXT that must never reach the call log"


def req(**kw: Any) -> JudgeRequest:
    base = dict(purpose="match.pair:F01:FND-001", system="judge system prompt", user=SECRET_USER,
                schema=judge_schema("pair"), model="claude-opus-5-5", effort="high", max_tokens=4000, sample_index=1)
    base.update(kw)
    return JudgeRequest(**base)


GOOD = {"score": 3, "core_insight_present": "yes", "location_ok": True, "credit_items_stated": ["c1"],
        "rationale": "states it"}


def cli_out(structured: Any = None, *, cost: float = 0.07, is_error: bool = False, subtype: str = "success",
            result: str = "", stop: str = "tool_use", model: str = "claude-opus-5-5") -> dict[str, Any]:
    return {"type": "result", "subtype": subtype, "is_error": is_error, "result": result,
            "structured_output": structured, "stop_reason": stop, "num_turns": 2, "total_cost_usd": cost,
            "terminal_reason": "completed",
            "usage": {"input_tokens": 1200, "output_tokens": 300, "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0},
            "modelUsage": {model: {"inputTokens": 1200, "outputTokens": 300}}}


class Runner:
    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, argv, stdin, env, cwd, timeout_s):
        self.calls.append({"argv": argv, "stdin": stdin, "env": env, "cwd": cwd, "timeout_s": timeout_s})
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return CompletedRun(0, json.dumps(item), "")


async def no_sleep(_: float) -> None:
    return None


async def test_claude_code_argv_env_and_log(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-test-not-real")
    run = Runner(cli_out(GOOD))
    j = ClaudeCodeJudge(out_dir=tmp_path, runner=run, max_budget_usd_per_call=0.5, timeout_s=999, sleep=no_sleep)
    res = await j.complete(req())
    assert res.data == GOOD and res.model == "claude-opus-5-5" and res.cost_usd == pytest.approx(0.07)
    assert res.input_tokens == 1200 and res.output_tokens == 300 and res.raw["cost_basis"] == "call_total"
    call = run.calls[0]
    argv = call["argv"]
    assert argv[:2] == ["claude", "-p"] and "--bare" not in argv and "--no-session-persistence" not in argv
    for flag, val in (("--model", "claude-opus-5-5"), ("--effort", "high"), ("--tools", ""),
                      ("--output-format", "json"), ("--system-prompt", "judge system prompt"),
                      ("--disallowedTools", "mcp__*"), ("--max-budget-usd", "0.5")):
        assert argv[argv.index(flag) + 1] == val
    assert "--strict-mcp-config" in argv and "--disable-slash-commands" in argv and "--session-id" in argv
    assert json.loads(argv[argv.index("--json-schema") + 1]) == judge_schema("pair")
    assert call["stdin"] == SECRET_USER and call["timeout_s"] == 999
    env = call["env"]
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1" and env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "4000"
    log = (tmp_path / "judge_calls.jsonl").read_text()
    assert SECRET_USER not in log and "sk-test-not-real" not in log and "judge system prompt" not in log
    row = json.loads(log.splitlines()[0])
    assert row["outcome"] == "ok" and row["call_cost_usd"] == pytest.approx(0.07) and row["sample_index"] == 1
    assert row["purpose"] == "match.pair:F01:FND-001" and len(row["user_sha256"]) == 64


async def test_claude_code_inherit_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    run = Runner(cli_out(GOOD))
    await ClaudeCodeJudge(out_dir=tmp_path, runner=run, inherit_api_key=True).complete(req())
    assert run.calls[0]["env"]["ANTHROPIC_API_KEY"] == "sk-test-not-real"


async def test_claude_code_retries_retryable_then_succeeds(tmp_path):
    slept: list[float] = []

    async def sleep(s: float) -> None:
        slept.append(s)

    run = Runner(TimeoutError(), cli_out(is_error=True, result="API Error: 529 overloaded"), cli_out(GOOD, cost=0.1))
    j = ClaudeCodeJudge(out_dir=tmp_path, runner=run, max_retries=3, backoff_base_s=2, backoff_max_s=60, sleep=sleep,
                        seed=1)
    res = await j.complete(req())
    assert res.data == GOOD and res.raw["attempts"] == 3 and len(slept) == 2
    assert 1.0 <= slept[0] <= 2.0 and 2.0 <= slept[1] <= 4.0
    rows = [json.loads(x) for x in (tmp_path / "judge_calls.jsonl").read_text().splitlines()]
    assert [r["outcome"] for r in rows] == ["error", "error", "ok"]
    assert len({r["session_id"] for r in rows}) == 3      # a fresh session per attempt
    assert j.cost_total_usd == pytest.approx(0.07 + 0.1)  # the failed JSON attempt still cost money


@pytest.mark.parametrize("out,needle", [
    (cli_out(is_error=True, result="Invalid API key · Please run /login"), "LLMAuthError"),
    (cli_out(is_error=True, subtype="error_max_budget_usd"), "max-budget-usd"),
    (cli_out(is_error=True, subtype="error_max_structured_output_retries"), "schema-valid"),
    (cli_out(GOOD, stop="max_tokens"), "truncated"),
    (cli_out(GOOD, stop="refusal"), "declined"),
    (cli_out({"score": 7, "rationale": "x"}), "violates the schema"),
])
async def test_claude_code_non_retryable(tmp_path, out, needle):
    run = Runner(out, cli_out(GOOD))
    j = ClaudeCodeJudge(out_dir=tmp_path, runner=run, max_retries=3, sleep=no_sleep)
    with pytest.raises(JudgeError, match=needle):
        await j.complete(req())
    assert len(run.calls) == 1


async def test_claude_code_gives_up_after_retries(tmp_path):
    run = Runner(TimeoutError(), TimeoutError(), TimeoutError())
    j = ClaudeCodeJudge(out_dir=tmp_path, runner=run, max_retries=2, sleep=no_sleep)
    with pytest.raises(JudgeError, match="exceeded"):
        await j.complete(req())
    assert len(run.calls) == 3


async def test_claude_code_cost_delta_when_session_reused(tmp_path):
    j = ClaudeCodeJudge(out_dir=tmp_path, runner=Runner())
    assert j._cost({"total_cost_usd": 0.10}, "s1") == (0.10, "call_total")
    assert j._cost({"total_cost_usd": 0.25}, "s1") == (pytest.approx(0.15), "cumulative_delta")
    assert j._cost({}, "s2") == (None, "unreported")


def test_claude_code_rejects_forbidden_flags(tmp_path):
    with pytest.raises(ValueError):
        ClaudeCodeJudge(out_dir=tmp_path, extra_args=["--bare"])


# ----------------------------------------------------------------------------- Anthropic API


class Msg:
    def __init__(self, text: str, stop: str = "end_turn", model: str = "claude-opus-5-5") -> None:
        self.content = [{"type": "thinking", "thinking": ""}, {"type": "text", "text": text}]
        self.stop_reason = stop
        self.model = model
        self.usage = {"input_tokens": 1000, "output_tokens": 200, "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0}


class Stream:
    def __init__(self, item: Any) -> None:
        self.item = item

    async def __aenter__(self):
        if isinstance(self.item, BaseException):
            raise self.item
        return self

    async def __aexit__(self, *a):
        return False

    async def get_final_message(self):
        return self.item


class Client:
    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.bodies: list[dict[str, Any]] = []
        self.messages = self

    def stream(self, **body):
        self.bodies.append(body)
        return Stream(self.script.pop(0))


async def test_anthropic_judge_body_cost_and_retry(tmp_path):
    client = Client(TimeoutError(), Msg(json.dumps(GOOD)))
    j = AnthropicJudge(out_dir=tmp_path, client=client, sleep=no_sleep,
                       price_per_mtok={"input": 10.0, "output": 50.0})
    res = await j.complete(req())
    assert res.data == GOOD and res.cost_usd == pytest.approx((1000 * 10 + 200 * 50) / 1e6)
    body = client.bodies[0]
    assert body["thinking"]["type"] == "adaptive" and body["output_config"]["effort"] == "high"
    assert body["output_config"]["format"] == {"type": "json_schema", "schema": judge_schema("pair")}
    assert "temperature" not in body and body["messages"][0]["content"][0]["text"] == SECRET_USER
    assert SECRET_USER not in (tmp_path / "judge_calls.jsonl").read_text()


async def test_anthropic_judge_unpriced_and_errors(tmp_path):
    j = AnthropicJudge(out_dir=tmp_path, client=Client(Msg(json.dumps(GOOD))), sleep=no_sleep)
    assert (await j.complete(req())).cost_usd is None
    for msg, needle in ((Msg("not json"), "not JSON"), (Msg(json.dumps(GOOD), stop="max_tokens"), "truncated"),
                        (Msg(json.dumps({"score": 9})), "violates")):
        with pytest.raises(JudgeError, match=needle):
            await AnthropicJudge(out_dir=tmp_path, client=Client(msg), sleep=no_sleep).complete(req())


# ----------------------------------------------------------------------------- build_judge


def test_build_judge_kinds(tmp_path):
    assert isinstance(build_judge("fake", out_dir=tmp_path), FakeJudge)
    assert isinstance(build_judge("claude_code", out_dir=tmp_path, timeout_s=10), ClaudeCodeJudge)
    assert isinstance(build_judge("anthropic_api", out_dir=tmp_path, client=object()), AnthropicJudge)
    with pytest.raises(ValueError, match="unknown judge kind"):
        build_judge("gpt", out_dir=tmp_path)
    with pytest.raises(ValueError, match="does not take"):
        build_judge("claude_code", out_dir=tmp_path, modle="typo")
    custom = build_judge("fake", out_dir=tmp_path, responder=lambda r: {"x": 1})
    assert isinstance(custom, FakeJudge)
