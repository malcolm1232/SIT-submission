"""``dra replay <run_dir>`` (runbook §6, docs/REPRODUCIBILITY.md §6-§7 R0): a recorded run re-run
offline from its own ``llm.jsonl`` and ``tools.jsonl``, never inventing output.

The recorded runs are made here with the real phases, ``transport: fake`` (the selftest fixture
script) and the fixture cassettes. Every replay runs with outbound sockets disabled."""

from __future__ import annotations

import json
import shutil
import socket
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import sit_review_agent.progress  # noqa: F401 - bind ConsoleProgress's default stream before CliRunner swaps it
from sit_review_agent.cli import app
from sit_review_agent.clock import FakeClock
from sit_review_agent.config import load_config
from sit_review_agent.llm.gateway import AnthropicGateway, LLMRequest
from sit_review_agent.llm.outputs import PlanOutput
from sit_review_agent.paths import config_dir
from sit_review_agent.replay import (
    BANNER_PREFIX,
    JournalReplayToolGateway,
    ReplayToolGap,
    compare_reports,
    recover_catalogue,
    request_hash,
)
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.selftest import FIXTURE_DIR
from sit_review_agent.states import PhaseName

PDF = FIXTURE_DIR / "design.pages.txt"
CASSETTES = FIXTURE_DIR / "cassettes"


@pytest.fixture
def cfgdir(tmp_path: Path) -> Path:
    dst = tmp_path / "config"
    shutil.copytree(config_dir(), dst)
    agent = dst / "agent.yaml"
    agent.write_text(agent.read_text(encoding="utf-8").replace("run_root: runs", f"run_root: {tmp_path / 'runs'}"),
                     encoding="utf-8")
    return dst


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("replay opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def invoke(args: list[str]) -> Any:
    res = CliRunner().invoke(app, args)
    assert "Traceback" not in res.output, res.output
    return res


def record(cfgdir: Path, run_id: str, *extra: str, pdf: Path = PDF) -> Path:
    res = invoke(["run", str(pdf), "--config", str(cfgdir), "--transport", "fake", "--replay", str(CASSETTES),
                  "--run-id", run_id, *extra])
    assert res.exit_code == 0, res.output
    return cfgdir.parent / "runs" / run_id


def replay(cfgdir: Path, src: Path, run_id: str, *extra: str) -> Any:
    return invoke(["replay", str(src), "--config", str(cfgdir), "--run-id", run_id, *extra])


def test_replay_reproduces_the_recorded_report_offline(cfgdir: Path, no_network: None) -> None:
    src = record(cfgdir, "rec", "--disable-tool", "mcp-research-information")
    res = replay(cfgdir, src, "rec-rp")
    assert res.exit_code == 0, res.output
    assert "replayed 9 model call(s) and 2 tool call(s)" in res.output
    assert "matches the recording" in res.output
    rd = src.parent / "rec-rp"
    assert (rd / "report.md").read_text(encoding="utf-8").startswith(BANNER_PREFIX)
    a = json.loads((src / "report.json").read_text(encoding="utf-8"))
    b = json.loads((rd / "report.json").read_text(encoding="utf-8"))
    assert compare_reports(a, b) == []
    assert [f["id"] for f in a["findings"]] == [f["id"] for f in b["findings"]]
    man = json.loads((rd / "manifest.json").read_text(encoding="utf-8"))
    assert man["extra"]["mode"] == "replay" and man["extra"]["tools"]["transport"] == "replay-strict"
    assert any(d.startswith("replayed evidence") for d in man["extra"]["deviations"])
    assert man["usage"]["cost_usd"] == 0.0                         # nothing was spent
    llm = JsonlWriter(rd / "llm.jsonl").read()
    assert len(llm) == 9 and all(e["replayed"] and e["replayed_from"].startswith("rec/") for e in llm)
    tools = JsonlWriter(rd / "tools.jsonl").read()
    assert [e["call_id"] for e in tools] == ["call-0001", "call-0002"] and all(e["replayed"] for e in tools)
    rec = json.loads((rd / "replay.json").read_text(encoding="utf-8"))
    assert rec["replayed_evidence"] and rec["matches_recording"] and rec["source_run_id"] == "rec"
    assert rec["model_calls_replayed"] == rec["model_calls_recorded"] == 9
    # explain and coverage work on the replayed run (runbook §6: walk explain and the coverage map)
    fid = b["findings"][0]["id"]
    assert invoke(["explain", str(rd), fid]).exit_code == 0
    assert invoke(["coverage", "--run", str(rd)]).exit_code == 0


@pytest.mark.parametrize("scenario", ["LLM-06", "LLM-07", "INF-07"])
def test_replay_reraises_recorded_failures(cfgdir: Path, no_network: None, scenario: str) -> None:
    """A refusal, a truncation, a shared-key 401: the recorded outcome is raised again, so the phases
    take the same path (reframed retry, degradation, doc-only) without any model or tool."""
    src = record(cfgdir, f"rec-{scenario}", "--faults", scenario)
    res = replay(cfgdir, src, f"rp-{scenario}")
    assert res.exit_code == 0, res.output
    assert "matches the recording" in res.output


def test_replay_of_a_resumed_run_uses_the_rerun_calls(cfgdir: Path, no_network: None,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    import sit_review_agent.phases as phases_mod

    real = phases_mod.default_phases

    class Interrupt:
        def __init__(self, inner: Any) -> None:
            self.inner, self.name = inner, inner.name

        async def run(self, ctx: Any) -> Any:
            await self.inner.run(ctx)                      # its model call is logged, then Ctrl-C
            raise KeyboardInterrupt

    def patched() -> Any:
        out = real()
        out[PhaseName.VERIFY] = Interrupt(out[PhaseName.VERIFY])
        return out

    monkeypatch.setattr(phases_mod, "default_phases", patched)
    res = invoke(["run", str(PDF), "--config", str(cfgdir), "--transport", "fake", "--replay", str(CASSETTES),
                  "--disable-tool", "mcp-research-information", "--run-id", "res"])
    assert res.exit_code == 130, res.output
    monkeypatch.setattr(phases_mod, "default_phases", real)
    src = cfgdir.parent / "runs" / "res"
    assert invoke(["resume", str(src)]).exit_code == 0
    logged = {e["call_id"] for e in JsonlWriter(src / "llm.jsonl").read()}
    used = {c for ids in json.loads((src / "state.json").read_text())["llm_calls"].values() for c in ids}
    assert logged - used                                   # the abandoned verify call is in the log
    res = replay(cfgdir, src, "res-rp")
    assert res.exit_code == 0, res.output
    assert f"replayed {len(used)} model call(s)" in res.output


def test_replay_rebuilds_a_moved_text_input_and_checks_a_given_one(cfgdir: Path, tmp_path: Path) -> None:
    moved = tmp_path / "inbox" / "design.pages.txt"
    moved.parent.mkdir()
    shutil.copy(PDF, moved)
    src = record(cfgdir, "mv", "--no-tools", pdf=moved)
    moved.unlink()
    res = replay(cfgdir, src, "mv-rp")
    assert res.exit_code == 0, res.output                  # rebuilt from the run's canonical text
    assert (src.parent / "mv-rp" / "input" / "design.pages.txt").is_file()
    res = replay(cfgdir, src, "mv-rp2", "--pdf", str(tmp_path / "missing.txt"))
    assert res.exit_code == 2 and "input not found" in res.output


def test_replay_divergence_is_reported_not_invented(cfgdir: Path) -> None:
    src = record(cfgdir, "div", "--disable-tool", "mcp-research-information")
    log = src / "llm.jsonl"
    entries = JsonlWriter(log).read()
    entries[1]["request_sha256"] = "0" * 64                   # the plan call no longer matches
    log.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    res = replay(cfgdir, src, "div-rp")
    assert res.exit_code == 4, res.output
    assert "request body hash" in res.output and "plan" in res.output
    rec = json.loads((src.parent / "div-rp" / "replay.json").read_text(encoding="utf-8"))
    assert rec["matches_recording"] is False
    assert not (src.parent / "div-rp" / "report.json").exists()


def test_replay_reports_a_changed_report_as_a_divergence(cfgdir: Path) -> None:
    src = record(cfgdir, "chg", "--no-tools")
    rep = json.loads((src / "report.json").read_text(encoding="utf-8"))
    rep["verdict"]["confidence"] = 0.01
    (src / "report.json").write_text(json.dumps(rep), encoding="utf-8")
    res = replay(cfgdir, src, "chg-rp")
    assert res.exit_code == 4 and "$.verdict.confidence" in res.output


def test_replay_refuses_run_dirs_lacking_data(cfgdir: Path, tmp_path: Path) -> None:
    src = record(cfgdir, "gap", "--disable-tool", "mcp-research-information")
    # 1. only what docs/live_runs keeps: report, manifest, config
    bare = tmp_path / "bare"
    bare.mkdir()
    for name in ("report.json", "manifest.json", "effective_config.json"):
        shutil.copy(src / name, bare / name)
    res = invoke(["replay", str(bare), "--config", str(cfgdir)])
    assert res.exit_code == 2 and "llm.jsonl" in res.output and "state.json" in res.output
    # 2. responses not logged
    nocontent = tmp_path / "nocontent"
    shutil.copytree(src, nocontent)
    entries = JsonlWriter(nocontent / "llm.jsonl").read()
    for e in entries:
        e.pop("content", None)
    (nocontent / "llm.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    res = invoke(["replay", str(nocontent), "--config", str(cfgdir)])
    assert res.exit_code == 2 and "no logged response content" in res.output
    # 3. a live run on the claude_code backend: the tool catalogue offered to the model is not logged
    live = tmp_path / "live"
    shutil.copytree(src, live)
    eff = json.loads((live / "effective_config.json").read_text(encoding="utf-8"))
    eff["agent"]["transport"] = "live"
    (live / "effective_config.json").write_text(json.dumps(eff), encoding="utf-8")
    (live / "tools_list.jsonl").unlink(missing_ok=True)         # a run from before listings were logged
    res = invoke(["replay", str(live), "--config", str(cfgdir)])
    assert res.exit_code == 2 and "tool catalogue" in res.output
    # 4. prompts changed since the run
    old = tmp_path / "old"
    shutil.copytree(src, old)
    man = json.loads((old / "manifest.json").read_text(encoding="utf-8"))
    man["prompts_bundle_sha256"] = "f" * 64
    (old / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    res = invoke(["replay", str(old), "--config", str(cfgdir)])
    assert res.exit_code == 2 and "prompts changed" in res.output
    # 5. no such run
    assert invoke(["replay", str(tmp_path / "nope"), "--config", str(cfgdir)]).exit_code == 2


def test_replay_with_recorded_tool_listings(cfgdir: Path, no_network: None) -> None:
    """A run that logged its tool listings (``tools_list.jsonl``, the logging change asked of the
    gateways) has them served in order, ahead of any other catalogue source."""
    src = record(cfgdir, "lst", "--disable-tool", "mcp-research-information")
    specs, _ = recover_catalogue(json_config(src), [])
    assert specs
    rows = [{"server": s.server, "name": s.name, "description": s.description, "input_schema": s.input_schema,
             "capability": s.capability} for s in specs]
    JsonlWriter(src / "tools_list.jsonl").append({"listed_at": "2026-10-02T09:00:00Z", "tools": rows})
    res = replay(cfgdir, src, "lst-rp")
    assert res.exit_code == 0, res.output
    rec = json.loads((src.parent / "lst-rp" / "replay.json").read_text(encoding="utf-8"))
    assert rec["tool_catalogue"].startswith("tools_list.jsonl")


def json_config(rd: Path) -> Any:
    from sit_review_agent.config import EffectiveConfig

    return EffectiveConfig.model_validate(json.loads((rd / "effective_config.json").read_text(encoding="utf-8")))


async def test_journal_tool_gateway_is_strict() -> None:
    gw = JournalReplayToolGateway([], None, catalogue_note="not recorded")
    with pytest.raises(ReplayToolGap):
        await gw.list_tools()
    with pytest.raises(ReplayToolGap):
        await gw.call("mcp-internet-search__search", {"query": "x"})
    listed = JournalReplayToolGateway([], [], listings=[[]])
    assert await listed.list_tools() == []
    with pytest.raises(ReplayToolGap):
        await listed.list_tools()


def test_recorded_errors_are_rebuilt_typed() -> None:
    from sit_review_agent.errors import LLMRateLimitError, LLMRefusalError, LLMTruncatedError
    from sit_review_agent.replay import ReplayDivergence, recorded_error

    req = _request()
    err = recorded_error({"outcome": "LLMRefusalError", "error": "model declined",
                          "stop_details": {"category": "cyber"}}, req, "llm-0007")
    assert isinstance(err, LLMRefusalError) and err.category == "cyber" and err.call_id == "llm-0007"
    err = recorded_error({"outcome": "LLMRateLimitError", "message": "429", "retry_after_s": 15}, req, "llm-0001")
    assert isinstance(err, LLMRateLimitError) and err.retry_after_s == 15 and err.phase == "plan"
    err = recorded_error({"outcome": "LLMTruncatedError"}, req, "llm-0002")
    assert isinstance(err, LLMTruncatedError) and err.max_tokens == 1234
    assert isinstance(recorded_error({"outcome": "SomethingElse"}, req, "llm-0003"), ReplayDivergence)


# ------------------------------------------------------------------ request-hash recipes per backend


class _Stream:
    request_id = "req_x"

    def __init__(self, msg: Any) -> None:
        self.msg = msg

    async def get_final_message(self) -> Any:
        return self.msg


class _Manager:
    def __init__(self, msg: Any) -> None:
        self.msg = msg

    async def __aenter__(self) -> _Stream:
        return _Stream(self.msg)

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class _Client:
    def __init__(self, msg: Any) -> None:
        self.messages = self
        self.msg = msg

    def stream(self, **kwargs: Any) -> _Manager:
        return _Manager(self.msg)


def _request(tools: list[dict[str, Any]] | None = None) -> LLMRequest:
    return LLMRequest(phase=PhaseName.PLAN, conversation_id="plan-0", system="You are a reviewer.",
                      messages=[{"role": "user", "content": [{"type": "text", "text": "Plan the review."}]}],
                      effort="high", max_tokens=1234, tools=tools or [], output_schema=PlanOutput)


async def test_request_hash_matches_the_anthropic_gateway(tmp_path: Path) -> None:
    from anthropic.types import Message

    plan = {"questions": [], "criteria_skipped": [{"criterion_id": "verifiability", "reason": "n/a"}]}
    msg = Message.model_validate({"id": "m", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                                  "content": [{"type": "text", "text": json.dumps(plan)}], "stop_reason": "end_turn",
                                  "stop_sequence": None,
                                  "usage": {"input_tokens": 1, "output_tokens": 1}})
    cfg = load_config()
    rd = RunDir(tmp_path / "a").create()
    gw = AnthropicGateway(cfg, rd, clock=FakeClock(), client=_Client(msg))
    tools = [{"name": "mcp-internet-search__search", "description": "Web search.",
              "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}}]
    res = await gw.call(_request(tools))
    logged = JsonlWriter(rd.llm_log).read()[-1]
    assert request_hash("anthropic_api", _request(tools), cfg, RunDir(tmp_path / "b")) == logged["request_sha256"]
    assert res.request_sha256 == logged["request_sha256"]
    # the logged body carries the tools the model was offered: the catalogue is recoverable
    from sit_review_agent.replay import RecordedCall

    entry = {**logged, "phase": "research"}
    specs, source = recover_catalogue(cfg, [RecordedCall(call_id="llm-0001", entries=[entry])])
    assert specs is not None and [s.qualified_name for s in specs] == ["mcp-internet-search__search"]
    assert "request body" in source


async def test_request_hash_matches_the_claude_code_gateway(tmp_path: Path) -> None:
    from sit_review_agent.llm.claude_code import ClaudeCodeGateway, CompletedRun

    plan = {"questions": [], "criteria_skipped": [{"criterion_id": "verifiability", "reason": "n/a"}]}
    out = {"type": "result", "subtype": "success", "is_error": False, "result": "", "structured_output": plan,
           "stop_reason": "end_turn", "session_id": "s", "num_turns": 1, "total_cost_usd": 0.01,
           "usage": {"input_tokens": 1, "output_tokens": 1},
           "modelUsage": {"claude-opus-5-5": {"inputTokens": 1, "outputTokens": 1, "costUSD": 0.01}}}

    async def runner(argv: list[str], stdin: str, env: dict[str, str], cwd: Path, timeout_s: float) -> Any:
        return CompletedRun(0, json.dumps(out), "")

    cfg = load_config()
    rd = RunDir(tmp_path / "c").create()
    gw = ClaudeCodeGateway(cfg, rd, clock=FakeClock(), runner=runner)
    await gw.call(_request())
    logged = JsonlWriter(rd.llm_log).read()[-1]
    assert request_hash("claude_code", _request(), cfg, RunDir(tmp_path / "d")) == logged["request_sha256"]
