"""Usage that is unknown is recorded as unknown, never as zero (Session 4 accounting fixes).

The demo measurement run of 2026-10-03 cut its assess call at the run deadline after 179 s; the
call was billed (about $0.7 to $0.9 by estimate) but ``llm.jsonl`` logged zero usage, so the
manifest said $1.10 for a run that cost about $1.9. Now:

* a sent attempt that ends without a usage report (cut by the deadline, killed at the timeout,
  a ``claude -p`` that exited without a JSON result, a dropped API stream, an interrupt) is logged
  with ``usage: null`` and ``usage_unrecorded: <reason>``;
* the manifest lists those attempts in ``extra.model.calls_with_unrecorded_usage`` (call ID,
  stage, purpose, attempt, wall seconds, reason) and sets ``extra.model.cost_usd_lower_bound``;
* every place that prints a cost total says it is a lower bound when that list is not empty:
  ``report.md``, the run's closing console lines and the ``--k`` group summary.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import anthropic
import pytest

from sit_review_agent.clock import FakeClock
from sit_review_agent.config import EffectiveConfig, load_config
from sit_review_agent.errors import LLMDeadlineError, LLMOverloadedError, LLMTimeoutError, LLMUnavailableError
from sit_review_agent.kruns import KGroup, KRun, collect, format_group
from sit_review_agent.llm.claude_code import ClaudeCodeGateway, CompletedRun
from sit_review_agent.llm.gateway import FakeResponse, LLMRequest
from sit_review_agent.llm.runtime import RunDeadline, RuntimeLimits, attach_runtime
from sit_review_agent.manifest import journal_usage
from sit_review_agent.orchestrator import RunRequest, run_review
from sit_review_agent.progress import NullProgress
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.selftest import FIXTURE_DIR, fixture_gateway, selftest_config
from sit_review_agent.states import PhaseName

A = PhaseName.ASSESS


@pytest.fixture(scope="module")
def cfg() -> EffectiveConfig:
    base = load_config()
    llm = base.agent.llm.model_copy(update={"backoff_base_s": 0.0, "backoff_max_s": 0.0})
    return base.model_copy(update={"agent": base.agent.model_copy(update={"llm": llm})})


def req(phase: PhaseName = A) -> LLMRequest:
    return LLMRequest(phase=phase, conversation_id=f"{phase.value}-0", system="You are a reviewer.",
                      messages=[{"role": "user", "content": [{"type": "text", "text": "Assess."}]}], effort="high",
                      max_tokens=1000)


class Runner:
    """Scripted ``claude -p``: a dict is a JSON result, a CompletedRun is returned as is, an
    exception is raised, ``"hang"`` waits until cancelled. ``seconds`` advances the fake clock."""

    def __init__(self, clock: FakeClock, *script: Any, seconds: float = 0.0) -> None:
        self.clock, self.script, self.seconds = clock, list(script), seconds

    async def __call__(self, argv: list[str], stdin: str, env: dict[str, str], cwd: Path,
                       timeout_s: float) -> CompletedRun:
        item = self.script.pop(0)
        await self.clock.sleep(self.seconds)
        if item == "hang":
            await asyncio.sleep(30)
        if isinstance(item, BaseException):
            raise item
        return item if isinstance(item, CompletedRun) else CompletedRun(0, json.dumps(item), "")


def cli_ok() -> dict[str, Any]:
    return {"type": "result", "subtype": "success", "is_error": False, "result": "",
            "structured_output": {"text": "ok"}, "stop_reason": "end_turn", "num_turns": 2, "total_cost_usd": 0.5,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "modelUsage": {"claude-opus-5-5": {"inputTokens": 10, "outputTokens": 5}}}


def claude(tmp_path: Path, cfg: EffectiveConfig, *script: Any,
           seconds: float = 0.0) -> tuple[ClaudeCodeGateway, RunDir]:
    rd = RunDir(tmp_path / "run").create()
    clock = FakeClock()
    return ClaudeCodeGateway(cfg, rd, clock=clock, runner=Runner(clock, *script, seconds=seconds)), rd


def log(rd: RunDir) -> list[dict[str, Any]]:
    return JsonlWriter(rd.llm_log).read()


# ============================================================================== llm.jsonl


async def test_claude_code_deadline_cut_is_logged_as_unrecorded(tmp_path: Path, cfg: EffectiveConfig) -> None:
    gw, rd = claude(tmp_path, cfg, TimeoutError(), seconds=178.9)
    attach_runtime(gw, RuntimeLimits(deadline=RunDeadline(540, 120, 200, lambda: 241.1)))
    with pytest.raises(LLMDeadlineError):
        await gw.call(req())
    [entry] = log(rd)
    assert entry["usage"] is None and entry["usage_unrecorded"] == "deadline_cut"
    assert entry["call_cost_usd"] is None and entry["elapsed_s"] == pytest.approx(178.9)
    usage = journal_usage(rd)
    assert usage["calls_with_unrecorded_usage"] == [{"call_id": "llm-0001", "stage": "assess", "purpose": "",
                                                     "attempt": 0, "wall_s": 178.9, "reason": "deadline_cut"}]
    assert usage["output_tokens"] == 0 and usage["cost_usd"] == 0.0


async def test_claude_code_timeout_kill_and_process_fault(tmp_path: Path, cfg: EffectiveConfig) -> None:
    gw, rd = claude(tmp_path, cfg, TimeoutError(), CompletedRun(1, "Segmentation fault", ""), cli_ok())
    res = await gw.call(req())
    assert res.text == "ok"
    reasons = [(e["attempt"], e.get("usage_unrecorded"), e["usage"] is None) for e in log(rd)]
    assert reasons == [(0, "timeout_kill", True), (1, "process_fault", True), (2, None, False)]
    assert [c["reason"] for c in journal_usage(rd)["calls_with_unrecorded_usage"]] == ["timeout_kill",
                                                                                      "process_fault"]


async def test_a_cli_that_never_started_spent_nothing(tmp_path: Path, cfg: EffectiveConfig) -> None:
    gw, rd = claude(tmp_path, cfg, PermissionError("not executable"), cli_ok())
    await gw.call(req())
    first = log(rd)[0]
    assert first["outcome"] == "LLMUnavailableError" and "usage_unrecorded" not in first
    assert first["usage"]["output_tokens"] == 0
    assert journal_usage(rd)["calls_with_unrecorded_usage"] == []


async def test_an_error_result_reports_its_usage(tmp_path: Path, cfg: EffectiveConfig) -> None:
    err = {**cli_ok(), "is_error": True, "subtype": "error_during_execution", "result": "API Error: 529 overloaded",
           "structured_output": None, "usage": {"input_tokens": 7, "output_tokens": 0}}
    gw, rd = claude(tmp_path, cfg, err, cli_ok())
    await gw.call(req())
    first = log(rd)[0]
    assert first["outcome"] == LLMOverloadedError.__name__ and first["usage"]["input_tokens"] == 7
    assert "usage_unrecorded" not in first


async def test_an_interrupted_call_is_logged_as_unrecorded(tmp_path: Path, cfg: EffectiveConfig) -> None:
    gw, rd = claude(tmp_path, cfg, "hang")
    task = asyncio.create_task(gw.call(req()))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    [entry] = log(rd)
    assert entry["outcome"] == "CancelledError" and entry["usage_unrecorded"] == "interrupted"


def test_a_legacy_deadline_entry_with_zero_usage_counts_as_unrecorded(tmp_path: Path) -> None:
    """``llm.jsonl`` written before this fix (the demo measurement run's ``llm-0003``) logged zeros."""
    rd = RunDir(tmp_path / "run").create()
    w = JsonlWriter(rd.llm_log)
    zero = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    w.append({"call_id": "llm-0003", "phase": "assess", "purpose": "assess", "backend": "claude_code", "attempt": 0,
              "outcome": "LLMDeadlineError", "usage": zero, "elapsed_s": 178.9, "call_cost_usd": None})
    w.append({"call_id": "llm-0004", "phase": "report", "attempt": 0, "outcome": "LLMDeadlineError",
              "sent": False})                                               # never sent: spent nothing
    w.append({"call_id": None, "phase": "assess", "attempt": 0, "outcome": "LLMTimeoutError",
              "fault": "hang"})                                             # injected: spent nothing
    [c] = journal_usage(rd)["calls_with_unrecorded_usage"]
    assert (c["call_id"], c["reason"], c["wall_s"]) == ("llm-0003", "deadline_cut", 178.9)


async def test_anthropic_cut_or_dropped_stream_is_unrecorded_but_a_status_error_is_not(
        tmp_path: Path, cfg: EffectiveConfig) -> None:
    from types import SimpleNamespace

    import httpx2

    from sit_review_agent.llm.gateway import AnthropicGateway

    request = httpx2.Request("POST", "https://api.anthropic.invalid/v1/messages")

    class Manager:
        def __init__(self, item: Any) -> None:
            self.item = item

        async def __aenter__(self) -> Any:
            raise self.item

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    script = [anthropic.InternalServerError("boom", response=httpx2.Response(529, request=request), body=None),
              anthropic.APIConnectionError(request=request)]
    msgs = SimpleNamespace(stream=lambda **kw: Manager(script.pop(0)))
    client = SimpleNamespace(messages=msgs, beta=SimpleNamespace(messages=msgs))
    one_retry = cfg.agent.llm.model_copy(update={"max_retries": 1})
    c = cfg.model_copy(update={"agent": cfg.agent.model_copy(update={"llm": one_retry})})
    rd = RunDir(tmp_path / "run").create()
    gw = AnthropicGateway(c, rd, clock=FakeClock(), client=client)
    gw._net.start_call()                                                    # not the run's first call (NET-02)
    with pytest.raises((LLMUnavailableError, LLMTimeoutError)):
        await gw.call(req(PhaseName.PLAN))
    first, second = log(rd)
    assert first["status_code"] == 529 and "usage_unrecorded" not in first and first["usage"]["input_tokens"] == 0
    assert second["usage"] is None and second["usage_unrecorded"] == "connection_lost"


# ============================================================================== a whole run


def _cut_assess(rd: Any, clock: Any, progress: Any) -> Any:
    gw = fixture_gateway(rd, clock=clock)
    cut = LLMDeadlineError("the assess call was cut after 179 s by the run deadline")
    gw.script["assess"].appendleft(FakeResponse(raises=cut))  # type: ignore[attr-defined]
    return gw


async def test_a_cut_call_makes_every_cost_total_a_lower_bound(tmp_path: Path) -> None:
    progress = NullProgress()
    out = await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=selftest_config(tmp_path),
                                      run_id="cut"), llm_factory=_cut_assess, clock=FakeClock(), progress=progress)
    assert out.exit_code == 0
    rd = RunDir(out.run_dir)
    manifest = json.loads(rd.manifest.read_text(encoding="utf-8"))
    model = manifest["extra"]["model"]
    assert model["cost_usd_lower_bound"] is True
    [c] = model["calls_with_unrecorded_usage"]
    assert (c["stage"], c["reason"]) == ("assess", "deadline_cut")
    report = json.loads(rd.report_json.read_text(encoding="utf-8"))
    assert report["run_manifest"]["extra"]["model"]["calls_with_unrecorded_usage"] == [c]
    md = rd.report_md.read_text(encoding="utf-8")
    tokens = next(line for line in md.splitlines() if line.startswith("| Tokens |"))
    assert "lower bound" in tokens and "1 model call with unrecorded usage (assess, deadline cut)" in tokens
    lines = [e.message for e in progress.events if "lower bound" in e.message]
    assert len(lines) == 1 and lines[0].startswith("cost ~$") and "assess, deadline cut" in lines[0]

    group = KGroup(group_id="g", k=1, input="design.pdf", input_sha256=None, created_utc="t", run_root="runs",
                   argv=[], cli_args={}, config_sha256="0" * 64, mode="dev")
    kr = KRun(k_index=1, run_id="g-k1", status="completed", exit_code=0)
    collect(kr, rd.root)
    group.runs = [kr]
    assert kr.calls_with_unrecorded_usage == 1
    s = group.summary()
    assert s["cost_usd_lower_bound"] is True and s["calls_with_unrecorded_usage"] == 1
    text = format_group(group)
    assert f">={kr.cost_usd:.2f}" in text
    assert "(a lower bound: 1 model call with unrecorded usage)" in text


async def test_a_clean_run_states_no_lower_bound(tmp_path: Path) -> None:
    progress = NullProgress()
    out = await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=selftest_config(tmp_path),
                                      run_id="clean"),
                           llm_factory=lambda rd, clock, p: fixture_gateway(rd, clock=clock),
                           clock=FakeClock(), progress=progress)
    rd = RunDir(out.run_dir)
    model = json.loads(rd.manifest.read_text(encoding="utf-8"))["extra"]["model"]
    assert model["cost_usd_lower_bound"] is False and model["calls_with_unrecorded_usage"] == []
    assert "lower bound" not in rd.report_md.read_text(encoding="utf-8")
    assert not [e for e in progress.events if "lower bound" in e.message]


async def test_a_failed_run_also_says_its_cost_is_a_lower_bound(tmp_path: Path) -> None:
    def killed(rd: Any, clock: Any, progress: Any) -> Any:
        gw = fixture_gateway(rd, clock=clock)
        gw.script["understand"].appendleft(FakeResponse(raises=LLMTimeoutError("claude -p exceeded 1800 s")))  # type: ignore[attr-defined]
        return gw

    progress = NullProgress()
    out = await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=selftest_config(tmp_path),
                                      run_id="killed"), llm_factory=killed, clock=FakeClock(), progress=progress)
    assert out.exit_code == 3
    manifest = json.loads(RunDir(out.run_dir).manifest.read_text(encoding="utf-8"))
    model = manifest["extra"]["model"]
    assert [c["reason"] for c in model["calls_with_unrecorded_usage"]] == ["timeout_kill"]
    # plan and the assess shards ran beside understand in stage 1, so the measured cost is theirs
    assert manifest["usage"]["cost_usd"] > 0
    assert [e.message for e in progress.events if "lower bound" in e.message] == [
        f"cost ~${manifest['usage']['cost_usd']:.2f} is a lower bound: 1 model call with unrecorded usage "
        "(understand, timeout kill); their tokens and cost are not in the totals"]


async def test_anthropic_interrupted_attempt_is_logged_as_unrecorded(tmp_path: Path, cfg: EffectiveConfig) -> None:
    from types import SimpleNamespace

    from sit_review_agent.llm.gateway import AnthropicGateway

    class Hang:
        async def __aenter__(self) -> Any:
            await asyncio.sleep(30)

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    msgs = SimpleNamespace(stream=lambda **kw: Hang())
    rd = RunDir(tmp_path / "run").create()
    gw = AnthropicGateway(cfg, rd, clock=FakeClock(), client=SimpleNamespace(messages=msgs,
                                                                            beta=SimpleNamespace(messages=msgs)))
    task = asyncio.create_task(gw.call(req(PhaseName.PLAN)))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    [entry] = log(rd)
    assert entry["usage"] is None and entry["usage_unrecorded"] == "interrupted"
