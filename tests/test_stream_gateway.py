"""``ClaudeCodeGateway`` over ``--output-format stream-json`` (latency redesign W1, ADR-012 draft).

The answer comes from the last ``result`` event; a call cut by the run deadline or a stage limit
raises ``LLMDeadlineError`` with the finished items and an ESTIMATED usage that never enters the
measured totals; progress comes from the event stream. Offline: scripted runners, virtual clock;
the recorded real streams are exercised in ``test_stream_fixtures.py``.
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from sit_review_agent.clock import FakeClock
from sit_review_agent.config import EffectiveConfig, load_config
from sit_review_agent.errors import (
    LLMAuthError,
    LLMDeadlineError,
    LLMRefusalError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMTruncatedError,
    LLMUnavailableError,
)
from sit_review_agent.llm.claude_code import ClaudeCodeGateway, CompletedRun, StreamTimeout, subprocess_runner
from sit_review_agent.llm.gateway import LLMRequest, Usage
from sit_review_agent.llm.partial import JSON_CHARS_PER_TOKEN
from sit_review_agent.llm.runtime import RunDeadline, RuntimeLimits, attach_runtime
from sit_review_agent.progress import NullProgress
from sit_review_agent.replay import recorded_error
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.states import PhaseName

LIMITS = {"stage_1_end": 265.0, "refine_end": 465.0, "verdict_end": 530.0}


@pytest.fixture(scope="module")
def cfg() -> EffectiveConfig:
    return load_config()


def finding(i: int) -> dict[str, Any]:
    return {"id": f"FND-{i:03d}", "severity": "high", "title": f"Finding {i}", "statement": "s " * 30}


def ev(inner: dict[str, Any]) -> str:
    return json.dumps({"type": "stream_event", "event": inner, "session_id": "S", "uuid": "U"})


def result_event(structured: Any = None, **kw: Any) -> dict[str, Any]:
    base = {"type": "result", "subtype": "success", "is_error": False, "result": "", "structured_output": structured,
            "stop_reason": "tool_use", "session_id": "S", "num_turns": 2, "total_cost_usd": 0.01,
            "terminal_reason": "completed",
            "usage": {"input_tokens": 1137, "output_tokens": 400, "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0},
            "modelUsage": {"claude-opus-5-5": {"inputTokens": 1137, "outputTokens": 400, "costUSD": 0.01}}}
    return {**base, **kw}


def stream(answer: dict[str, Any] | None, *, cut_at: int | None = None, result: dict[str, Any] | None = None,
           thinking: int = 800) -> list[str]:
    """The event lines of one ``claude -p`` attempt, in the order the CLI 2.1.288 writes them."""
    text = json.dumps(answer) if answer is not None else ""
    body = text if cut_at is None else text[:cut_at]
    lines = [json.dumps({"type": "system", "subtype": "init", "model": "claude-opus-5-5"}),
             ev({"type": "message_start", "message": {"usage": {"input_tokens": 1137, "output_tokens": 5,
                                                               "cache_creation_input_tokens": 0,
                                                               "cache_read_input_tokens": 0}}}),
             json.dumps({"type": "system", "subtype": "thinking_tokens", "estimated_tokens": thinking}),
             ev({"type": "content_block_start", "index": 1,
                 "content_block": {"type": "tool_use", "name": "StructuredOutput", "input": {}}})]
    lines += [ev({"type": "content_block_delta", "index": 1,
                  "delta": {"type": "input_json_delta", "partial_json": body[k:k + 50]}})
              for k in range(0, len(body), 50)]
    if cut_at is None:
        lines += [ev({"type": "content_block_stop", "index": 1}), ev({"type": "message_stop"}),
                  json.dumps(result if result is not None else result_event(answer))]
    return lines


class StreamRunner:
    """Scripted streaming runner: delivers each line through ``on_line`` as the real runner does.
    An item is a list of lines (a finished attempt), ``("cut", lines)`` (the attempt is killed at its
    timeout after those lines), or an exception."""

    def __init__(self, *script: Any, between: Callable[[str], Any] | None = None) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.between = between

    async def __call__(self, argv: list[str], stdin: str, env: dict[str, str], cwd: Path, timeout_s: float, *,
                       on_line: Callable[[str], None] | None = None) -> CompletedRun:
        self.calls.append({"argv": argv, "timeout_s": timeout_s, "live": on_line is not None})
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        cut = isinstance(item, tuple)
        lines = item[1] if cut else item
        for line in lines:
            if on_line is not None:
                on_line(line)
            if self.between is not None:
                self.between(line)
            await asyncio.sleep(0)
        stdout = "".join(line + "\n" for line in lines)
        if cut:
            raise StreamTimeout(stdout=stdout, stderr="")
        return CompletedRun(0, stdout, "")


def gateway(tmp_path: Path, cfg: EffectiveConfig, runner: Any, *, elapsed: float | None = None,
            progress: Any = None) -> tuple[ClaudeCodeGateway, RunDir]:
    rd = RunDir(tmp_path / "run").create()
    gw = ClaudeCodeGateway(cfg, rd, clock=FakeClock(), runner=runner, progress=progress)
    if elapsed is not None:
        attach_runtime(gw, RuntimeLimits(deadline=RunDeadline(540, 75, 200, lambda: elapsed,
                                                              stage_limits=dict(LIMITS))))
    return gw, rd


class Findings(BaseModel):
    findings: list[dict[str, Any]]


def assess_req(tools: list[dict[str, Any]] | None = None) -> LLMRequest:
    return LLMRequest(phase=PhaseName.ASSESS, conversation_id="assess-1", system="You are a reviewer.",
                      messages=[{"role": "user", "content": [{"type": "text", "text": "doc"}]}], effort="medium",
                      max_tokens=32000, tools=tools or [], output_schema=Findings)


def flag(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


def log(rd: RunDir) -> list[dict[str, Any]]:
    return JsonlWriter(rd.llm_log).read()


# ------------------------------------------------------------------------------ argv


async def test_every_argv_streams_and_is_hermetic(tmp_path: Path, cfg: EffectiveConfig) -> None:
    runner = StreamRunner(stream({"text": "a"}), stream({"text": "b"}))
    gw, _ = gateway(tmp_path, cfg, runner)
    r = LLMRequest(phase=PhaseName.PLAN, conversation_id="c", system="s",
                   messages=[{"role": "user", "content": "x"}], effort="high", max_tokens=100)
    res = await gw.call(r)
    await gw.call(LLMRequest(phase=PhaseName.PLAN, conversation_id="c", system="s",
                             messages=[*r.messages, res.assistant_message(), {"role": "user", "content": "y"}],
                             effort="high", max_tokens=100))
    for call in runner.calls:
        argv = call["argv"]
        assert flag(argv, "--output-format") == "stream-json"
        assert "--verbose" in argv and "--include-partial-messages" in argv
        assert flag(argv, "--setting-sources") == ""                  # hermetic: no user-level settings
        assert call["live"] is True                                   # lines are read as they arrive
    assert "--resume" in runner.calls[1]["argv"]


# ------------------------------------------------------------------------------ the result event


async def test_answer_comes_from_the_last_result_event(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ans = {"text": "final"}
    lines = stream(ans)
    early = json.dumps(result_event({"text": "stale"}, total_cost_usd=0.0))
    gw, rd = gateway(tmp_path, cfg, StreamRunner([early, *lines]))
    res = await gw.call(LLMRequest(phase=PhaseName.PLAN, conversation_id="c", system="s",
                                   messages=[{"role": "user", "content": "x"}], effort="high", max_tokens=100))
    assert res.text == "final" and res.usage == Usage(1137, 400, 0, 0)
    assert gw.usage_total() == Usage(1137, 400, 0, 0)
    assert log(rd)[-1]["outcome"] == "ok"


@pytest.mark.parametrize(("result", "error"), [
    (result_event(is_error=True, subtype="error_during_execution", result="Invalid API key · Please run /login"),
     LLMAuthError),
    (result_event(stop_reason="refusal"), LLMRefusalError),
    (result_event(stop_reason="max_tokens"), LLMTruncatedError),
    (result_event(is_error=True, subtype="error_during_execution",
                  result="API Error: Claude's response exceeded the 256 output token maximum."), LLMTruncatedError),
    (result_event(is_error=True, subtype="error_max_structured_output_retries", result=None, errors=["x"]),
     LLMSchemaError),
    (result_event({"not": "text"}), LLMSchemaError),
])
async def test_same_errors_on_the_same_conditions(tmp_path: Path, cfg: EffectiveConfig, result: dict[str, Any],
                                                  error: type[Exception]) -> None:
    gw, _ = gateway(tmp_path, cfg, StreamRunner(stream({"text": "x"}, result=result), stream({"text": "ok"})))
    with pytest.raises(error):
        await gw.call(LLMRequest(phase=PhaseName.PLAN, conversation_id="c", system="s",
                                 messages=[{"role": "user", "content": "x"}], effort="high", max_tokens=100))


async def test_a_stream_without_a_result_event_is_a_process_fault(tmp_path: Path, cfg: EffectiveConfig) -> None:
    cfg0 = cfg.model_copy(update={"agent": cfg.agent.model_copy(
        update={"llm": cfg.agent.llm.model_copy(update={"max_retries": 0})})})
    lines = stream({"text": "x"})[:-1]                                # the process ended before its result
    gw, rd = gateway(tmp_path, cfg0, StreamRunner(lines))
    with pytest.raises(LLMUnavailableError, match="without a JSON result"):
        await gw.call(LLMRequest(phase=PhaseName.PLAN, conversation_id="c", system="s",
                                 messages=[{"role": "user", "content": "x"}], effort="high", max_tokens=100))
    entry = log(rd)[-1]
    assert entry["usage"] is None and entry["usage_unrecorded"] == "process_fault"
    assert entry["estimated_usage"]["estimated"] is True and entry["estimated_usage"]["input_tokens"] == 1137


# ------------------------------------------------------------------------------ the cut


async def test_a_stage_limit_cut_after_3_of_6_findings_salvages_3(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ans = {"findings": [finding(i) for i in range(1, 7)]}
    text = json.dumps(ans)
    cut_at = text.index('"FND-004"') + 20
    runner = StreamRunner(("cut", stream(ans, cut_at=cut_at)), stream({"text": "never"}))
    gw, rd = gateway(tmp_path, cfg, runner, elapsed=100.0)
    before = gw.usage_total()
    with pytest.raises(LLMDeadlineError, match="by the stage 1 limit") as ei:
        await gw.call(assess_req())
    err = ei.value
    assert len(runner.calls) == 1 and runner.calls[0]["timeout_s"] == 165     # never retried past the limit
    assert err.partial == {"findings": ans["findings"][:3]} and err.salvaged_items == 3
    assert err.usage is None                                                  # measured usage: none reported
    assert err.estimated_usage == Usage(1137, 800 + math.ceil(cut_at / JSON_CHARS_PER_TOKEN), 0, 0)
    assert gw.usage_total() == before and gw.cost_total_usd == 0.0           # the estimate is never measured
    entry = log(rd)[-1]
    assert entry["outcome"] == "LLMDeadlineError" and entry["usage"] is None
    assert entry["usage_unrecorded"] == "deadline_cut" and entry["call_cost_usd"] is None
    est = entry["estimated_usage"]
    assert est["estimated"] is True and est["input_tokens"] == 1137
    assert est["output_tokens"] == err.estimated_usage.output_tokens
    assert est["basis"] == {"thinking_tokens": 800, "streamed_chars": cut_at, "chars_per_token": JSON_CHARS_PER_TOKEN}
    assert entry["salvaged_items"] == 3 and entry["partial"] == err.partial
    # the error type's names (planner ruling), never the earlier usage_estimate / salvaged_partial
    assert "usage_estimate" not in entry and "salvaged_partial" not in entry
    # and replay rebuilds the same cut from the entry
    rebuilt = recorded_error(entry, assess_req(), entry["call_id"])
    assert isinstance(rebuilt, LLMDeadlineError) and rebuilt.partial == err.partial
    assert rebuilt.estimated_usage == err.estimated_usage and rebuilt.salvaged_items == 3


async def test_a_cut_before_any_item_salvages_nothing(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ans = {"findings": [finding(1)]}
    gw, rd = gateway(tmp_path, cfg, StreamRunner(("cut", stream(ans, cut_at=30))), elapsed=200.0)
    with pytest.raises(LLMDeadlineError) as ei:
        await gw.call(assess_req())
    assert ei.value.partial is None and ei.value.salvaged_items == 0
    assert ei.value.estimated_usage is not None and log(rd)[-1]["salvaged_items"] == 0


async def test_a_cut_before_the_api_message_has_no_estimate(tmp_path: Path, cfg: EffectiveConfig) -> None:
    init = [json.dumps({"type": "system", "subtype": "init"})]
    gw, rd = gateway(tmp_path, cfg, StreamRunner(("cut", init)), elapsed=200.0)
    with pytest.raises(LLMDeadlineError) as ei:
        await gw.call(assess_req())
    assert ei.value.estimated_usage is None
    entry = log(rd)[-1]
    assert entry["usage"] is None and entry["usage_unrecorded"] == "deadline_cut" and "estimated_usage" not in entry


async def test_the_envelope_salvages_its_final_answer(tmp_path: Path, cfg: EffectiveConfig) -> None:
    tools = [{"name": "t", "description": "d", "input_schema": {"type": "object"}}]
    env = {"tool_calls": [], "final": {"findings": [finding(1), finding(2)]}}
    text = json.dumps(env)
    gw, _ = gateway(tmp_path, cfg, StreamRunner(("cut", stream(env, cut_at=text.index('"FND-002"')))),
                    elapsed=100.0)
    with pytest.raises(LLMDeadlineError) as ei:
        await gw.call(assess_req(tools))
    assert ei.value.partial == {"findings": [finding(1)]}


async def test_a_plain_timeout_is_retried_and_logs_its_estimate(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ans = {"text": "late"}
    gw, rd = gateway(tmp_path, cfg, StreamRunner(("cut", stream(ans, cut_at=5)), stream({"text": "ok"})))
    res = await gw.call(LLMRequest(phase=PhaseName.PLAN, conversation_id="c", system="s",
                                   messages=[{"role": "user", "content": "x"}], effort="high", max_tokens=100))
    assert res.text == "ok" and [a.outcome for a in res.attempts] == ["LLMTimeoutError", "ok"]
    first = log(rd)[0]
    assert first["usage"] is None and first["usage_unrecorded"] == "timeout_kill"
    assert first["estimated_usage"]["estimated"] is True
    assert gw.usage_total() == Usage(1137, 400, 0, 0)                 # the retry's measured usage only


async def test_a_legacy_runner_without_on_line_still_salvages(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ans = {"findings": [finding(1), finding(2)]}
    text = json.dumps(ans)
    stdout = "".join(line + "\n" for line in stream(ans, cut_at=text.index('"FND-002"')))

    async def legacy(argv: list[str], stdin: str, env: dict[str, str], cwd: Path, timeout_s: float) -> CompletedRun:
        raise StreamTimeout(stdout=stdout, stderr="")

    gw, _ = gateway(tmp_path, cfg, legacy, elapsed=100.0)
    with pytest.raises(LLMDeadlineError) as ei:
        await gw.call(assess_req())
    assert ei.value.salvaged_items == 1
    plain = TimeoutError()                                             # a runner with no stdout at all
    gw2, _ = gateway(tmp_path / "b", cfg, StreamRunner(plain), elapsed=100.0)
    with pytest.raises(LLMDeadlineError) as e2:
        await gw2.call(assess_req())
    assert e2.value.partial is None and e2.value.estimated_usage is None


# ------------------------------------------------------------------------------ progress


async def test_draft_findings_show_while_the_call_streams(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ans = {"findings": [finding(1), finding(2)]}
    sink = NullProgress()
    seen_during: list[int] = []
    runner = StreamRunner(stream(ans), between=lambda _: seen_during.append(
        sum(1 for e in sink.events if e.kind == "draft")))
    gw, _ = gateway(tmp_path, cfg, runner, progress=sink)
    await gw.call(assess_req())
    drafts = [e for e in sink.events if e.kind == "draft"]
    assert [d.message.split(":")[0] for d in drafts] == ["draft finding 1 (unverified; llm-0001 assess)",
                                                         "draft finding 2 (unverified; llm-0001 assess)"]
    assert max(seen_during) == 2 and seen_during.index(1) < len(seen_during) - 3   # before the call returned
    assert not gw.tracker.calls                                                      # the call left the tracker


async def test_tracker_tracks_thinking_and_items(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ans = {"findings": [finding(1)]}
    snapshots: list[str | None] = []
    sink = NullProgress()
    holder: dict[str, ClaudeCodeGateway] = {}
    runner = StreamRunner(stream(ans, thinking=4210),
                          between=lambda _: snapshots.append(holder["gw"].tracker.status_line()))
    gw, _ = gateway(tmp_path, cfg, runner, progress=sink)
    holder["gw"] = gw
    await gw.call(assess_req())
    assert any(s and "llm-0001 assess: thinking ~4,210 tokens" in s for s in snapshots)
    assert any(s and "llm-0001 assess: 1 items streamed" in s for s in snapshots)


# ------------------------------------------------------------------------------ the subprocess runner


CHILD = r"""
import sys, time
for i in range(3):
    sys.stdout.write('{"type": "system", "subtype": "thinking_tokens", "estimated_tokens": %d}\n' % (i * 10))
    sys.stdout.flush()
    time.sleep(0.05)
sys.stdout.write('{"type": "result", "pad": "' + 'x' * 200000 + '"}\n')
sys.stdout.write('{"type": "tail"}')
sys.stdout.flush()
if len(sys.argv) > 1:
    time.sleep(30)
"""


async def test_subprocess_runner_streams_lines_as_they_arrive(tmp_path: Path) -> None:
    got: list[tuple[float, str]] = []
    loop = asyncio.get_running_loop()
    run = await subprocess_runner([sys.executable, "-c", CHILD], "", {}, tmp_path, 30,
                                  on_line=lambda s: got.append((loop.time(), s)))
    assert run.returncode == 0
    assert [json.loads(s)["type"] for _, s in got] == ["system", "system", "system", "result", "tail"]
    assert len(got[3][1]) > 200_000                                    # a line longer than asyncio's 64 KiB limit
    assert got[2][0] - got[0][0] >= 0.08                               # delivered live, not at exit
    assert run.stdout.endswith('{"type": "tail"}')


async def test_subprocess_runner_cut_keeps_what_streamed(tmp_path: Path) -> None:
    got: list[str] = []
    with pytest.raises(StreamTimeout) as ei:
        await subprocess_runner([sys.executable, "-c", CHILD, "hang"], "", {}, tmp_path, 1.0, on_line=got.append)
    assert isinstance(ei.value, TimeoutError)
    assert ei.value.stdout.endswith('{"type": "tail"}')               # everything read is kept
    assert len(got) == 4                                               # an unterminated line may be cut mid-way
    assert isinstance(ei.value, LLMTimeoutError) is False


# ------------------------------------------------------------------------------ a repeated answer


def answer_message(answer: dict[str, Any], *, start: dict[str, int], end: dict[str, int] | None,
                   cut_at: int | None = None, rejected: bool = True) -> list[str]:
    """One API message of ``claude -p --json-schema`` that writes ``answer`` in a StructuredOutput
    block, in the order the CLI 2.1.288 writes it: the block, the tool result, then the message's
    final counts. ``cut_at`` stops the lines inside the block (the message is still being written);
    ``rejected`` makes the tool result the CLI's schema rejection."""
    text = json.dumps(answer)
    body = text if cut_at is None else text[:cut_at]
    lines = [ev({"type": "message_start", "message": {"usage": {**start}}}),
             ev({"type": "content_block_start", "index": 1,
                 "content_block": {"type": "tool_use", "name": "StructuredOutput", "input": {}}})]
    lines += [ev({"type": "content_block_delta", "index": 1,
                  "delta": {"type": "input_json_delta", "partial_json": body[k:k + 50]}})
              for k in range(0, len(body), 50)]
    if cut_at is not None:
        return lines
    lines += [ev({"type": "content_block_stop", "index": 1}),
              json.dumps({"type": "user", "message": {"role": "user", "content": [
                  {"type": "tool_result", "tool_use_id": "t", "is_error": rejected,
                   "content": "rejected" if rejected else "ok"}]}})]
    if end is not None:
        lines.append(ev({"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {**end}}))
    lines.append(ev({"type": "message_stop"}))
    return lines


FIRST_START = {"input_tokens": 2, "output_tokens": 4, "cache_creation_input_tokens": 30976,
               "cache_read_input_tokens": 0}
FIRST_END = {**FIRST_START, "output_tokens": 15000}
SECOND_START = {"input_tokens": 2, "output_tokens": 1, "cache_creation_input_tokens": 11573,
                "cache_read_input_tokens": 37103}


def repeat_stream(first: dict[str, Any], second: dict[str, Any], *, second_cut_at: int | None = None) -> list[str]:
    """A call whose first complete answer the CLI rejects and whose model writes a second one (the
    shards 4 and 6 of ``sit_sample_ui_2``: 3 CLI turns)."""
    lines = [json.dumps({"type": "system", "subtype": "init", "model": "claude-opus-5-5"})]
    lines += answer_message(first, start=FIRST_START, end=FIRST_END)
    lines += answer_message(second, start=SECOND_START, end={**SECOND_START, "output_tokens": 14000},
                            cut_at=second_cut_at, rejected=False)
    if second_cut_at is None:
        lines.append(json.dumps(result_event(second, num_turns=3)))
    return lines


def delivered(runner: StreamRunner) -> list[str]:
    """Lines a scripted runner passes on; ``between`` runs after ``on_line``, so the line on which
    the gateway ended the call is not in it."""
    got: list[str] = []
    runner.between = got.append
    return got


async def test_a_repeated_answer_ends_the_call_at_the_first(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ans = {"findings": [finding(i) for i in range(1, 4)]}
    lines = repeat_stream(ans, ans)
    runner = StreamRunner(lines)
    got = delivered(runner)
    gw, rd = gateway(tmp_path, cfg, runner)
    res = await gw.call(assess_req())
    assert res.parsed == Findings.model_validate(ans) and res.stop_reason == "end_turn"
    assert len(runner.calls) == 1 and [a.outcome for a in res.attempts] == ["ok"]
    second_start = lines.index(ev({"type": "message_start", "message": {"usage": SECOND_START}}))
    assert len(got) == second_start                     # ended as the second API message started
    entry = log(rd)[-1]
    assert entry["outcome"] == "ok" and entry["num_turns"] == 2 and entry["ended_at_first_answer"] is True
    assert entry["complete_answers"] == 1 and entry["cli_messages"] == 2
    assert entry["cli_answer_rejections"] == [{"is_error": True, "text": "rejected"}]   # the CLI's schema check
    assert entry["terminal_reason"] == "first_complete_answer" and entry["usage_basis"] == "stream_messages"
    # measured usage of the streamed messages: the answering message in full, the input of the next
    measured = Usage(4, 15001, 30976 + 11573, 37103)
    assert res.usage == measured and gw.usage_total() == measured and entry["usage"] == measured.__dict__
    assert entry["cost_basis"] == "list_price" and entry["call_cost_usd"] == pytest.approx(
        (4 * 4.0 + 42549 * 5.0 + 37103 * 0.20 + 15001 * 20.0) / 1e6)
    assert gw.cost_total_usd == pytest.approx(entry["call_cost_usd"])


async def test_a_different_second_answer_is_not_used(tmp_path: Path, cfg: EffectiveConfig) -> None:
    first = {"findings": [finding(i) for i in range(1, 4)]}
    second = {"findings": [finding(9)]}
    runner = StreamRunner(repeat_stream(first, second))
    gw, rd = gateway(tmp_path, cfg, runner)
    res = await gw.call(assess_req())
    assert res.parsed == Findings.model_validate(first)
    assert log(rd)[-1]["num_turns"] == 2 and log(rd)[-1]["ended_at_first_answer"] is True


async def test_an_unusable_first_answer_lets_the_cli_ask_again(tmp_path: Path, cfg: EffectiveConfig) -> None:
    first = {"findings": "not a list"}                  # fails the gateway's own check too
    second = {"findings": [finding(1)]}
    lines = repeat_stream(first, second)
    runner = StreamRunner(lines)
    got = delivered(runner)
    gw, rd = gateway(tmp_path, cfg, runner)
    res = await gw.call(assess_req())
    assert res.parsed == Findings.model_validate(second) and len(got) == len(lines)
    entry = log(rd)[-1]
    assert entry["num_turns"] == 3 and "ended_at_first_answer" not in entry
    assert entry["cli_answer_rejections"] == [{"is_error": True, "text": "rejected"}]
    assert res.usage == Usage(1137, 400, 0, 0)          # the result event's usage, as before


async def test_a_single_answer_still_ends_with_the_result_event(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ans = {"findings": [finding(1)]}
    lines = [json.dumps({"type": "system", "subtype": "init"}),
             *answer_message(ans, start=FIRST_START, end=FIRST_END, rejected=False),
             json.dumps(result_event(ans))]
    runner = StreamRunner(lines)
    got = delivered(runner)
    gw, rd = gateway(tmp_path, cfg, runner)
    res = await gw.call(assess_req())
    assert len(got) == len(lines) and res.usage == Usage(1137, 400, 0, 0)
    assert log(rd)[-1]["num_turns"] == 2 and "ended_at_first_answer" not in log(rd)[-1]
    assert "cli_answer_rejections" not in log(rd)[-1]                 # a taken answer is no rejection


async def test_a_repeated_tool_call_envelope_ends_at_the_first(tmp_path: Path, cfg: EffectiveConfig) -> None:
    tools = [{"name": "search_web", "description": "d", "input_schema": {"type": "object"}}]
    first = {"tool_calls": [{"id": "call-0001", "name": "search_web", "input": {"q": "a"}}], "final": None}
    second = {"tool_calls": [{"id": "call-0001", "name": "search_web", "input": {"q": "b"}}], "final": None}
    gw, rd = gateway(tmp_path, cfg, StreamRunner(repeat_stream(first, second)))
    res = await gw.call(assess_req(tools))
    assert res.stop_reason == "tool_use" and [u.input for u in res.tool_uses] == [{"q": "a"}]
    assert [u.id for u in res.tool_uses] == ["call-0001"] and log(rd)[-1]["ended_at_first_answer"] is True


async def test_a_legacy_runner_keeps_the_cli_answer(tmp_path: Path, cfg: EffectiveConfig) -> None:
    first = {"findings": [finding(1)]}
    second = {"findings": [finding(2)]}
    stdout = "".join(line + "\n" for line in repeat_stream(first, second))

    async def legacy(argv: list[str], stdin: str, env: dict[str, str], cwd: Path, timeout_s: float) -> CompletedRun:
        return CompletedRun(0, stdout, "")

    gw, rd = gateway(tmp_path, cfg, legacy)
    res = await gw.call(assess_req())
    # a runner that is not live cannot be ended early; the call ran to the CLI's own end
    assert res.parsed == Findings.model_validate(second) and log(rd)[-1]["num_turns"] == 3


REPEAT_CHILD = r"""
import sys, time
for line in open(sys.argv[1]):
    sys.stdout.write(line)
    sys.stdout.flush()
time.sleep(30)
"""


async def test_the_subprocess_runner_is_killed_at_the_repeat(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ans = {"findings": [finding(1), finding(2)]}
    script = tmp_path / "lines.jsonl"
    script.write_text("".join(line + "\n" for line in repeat_stream(ans, ans, second_cut_at=40)))

    async def runner(argv: list[str], stdin: str, env: dict[str, str], cwd: Path, timeout_s: float, *,
                     on_line: Callable[[str], None] | None = None) -> CompletedRun:
        return await subprocess_runner([sys.executable, "-c", REPEAT_CHILD, str(script)], "", {}, cwd, 20,
                                       on_line=on_line)

    gw, rd = gateway(tmp_path, cfg, runner)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    res = await gw.call(assess_req())
    assert loop.time() - t0 < 10                        # the child sleeps 30 s after its lines: it was killed
    assert res.parsed == Findings.model_validate(ans) and log(rd)[-1]["num_turns"] == 2
