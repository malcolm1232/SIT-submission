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


def test_a_recorded_usage_dict_never_reaches_the_error_constructor() -> None:
    """Session 4 hub verification: LLMError gained ``usage`` (a Usage), and an error class that inherits
    LLMError.__init__ (a deadline cut, a timeout) was rebuilt with the log entry's ``usage`` dict, so replaying
    a run with a cut call crashed (``dict + Usage``; docs/live_runs/demo_profile_measure_1)."""
    from sit_review_agent.errors import LLMDeadlineError, LLMTimeoutError
    from sit_review_agent.llm.gateway import Usage, billed
    from sit_review_agent.replay import recorded_error

    usage = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    for name, cls in (("LLMDeadlineError", LLMDeadlineError), ("LLMTimeoutError", LLMTimeoutError)):
        err = recorded_error({"outcome": name, "error": "cut", "usage": usage}, _request(), "llm-0003")
        assert isinstance(err, cls) and err.usage is None
        assert billed(err, Usage(input_tokens=5)).usage == Usage(input_tokens=5)


def test_the_committed_demo_measurement_run_is_refused_by_name_since_the_config_redesign(
        cfgdir: Path, no_network: None) -> None:
    """The committed run (docs/live_runs/demo_profile_measure_1, recorded at 2d84f59 with a deadline-cut
    assess call) replayed offline with exit 0 until the latency redesign W0 (2026-10-03): its
    ``effective_config.json`` carries ``assess_reserve_seconds`` and lacks ``assess.shards`` and
    ``stage_limits_s``, so it is refused with the renamed key named and no traceback, like a run whose
    prompts changed; it replays at its own commit. The crash this test guarded (``dict + Usage`` on a
    recorded cut call) is pinned by ``test_a_recorded_usage_dict_never_reaches_the_error_constructor``."""
    repo = Path(__file__).resolve().parents[1]
    src = repo / "docs" / "live_runs" / "demo_profile_measure_1"
    # The run recorded its input as a repo-relative path; pass it absolute so the test does not depend
    # on pytest's working directory (it failed when started from outside the repo root).
    pdf = repo / "eval" / "synthetic" / "payments_orchestration" / "design_v1.pdf"
    assert pdf.is_file()
    res = replay(cfgdir, src, "demo-replay", "--pdf", str(pdf))
    assert res.exit_code == 2, res.output
    assert "effective_config.json: not a valid effective config" in res.output
    assert "assess_reserve_seconds was renamed refine_reserve_seconds" in res.output
    assert "demo_profile_measure_1" in res.output                      # the record, by name
    assert "made at commit 2d84f59" in res.output and "check out 2d84f59" in res.output
    assert "Traceback" not in res.output


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


# ------------------------------------------------------------------ latency redesign W3: concurrent stage 1
#
# A concurrent first stage (docs/design/latency_and_demo_design.md section 4) logs its model calls in
# completion order, and the replay requests them in whatever order its tasks reach the gateway. The
# recorded-log fixtures below are in the shape the streaming gateway (W1) logs: every attempt carries
# ``conversation_id``, ``request_sha256``, ``started_at`` and ``start_offset_s`` (the run clock's elapsed
# seconds when the attempt started); a cut call carries ``usage: null``, ``usage_unrecorded``,
# ``estimated_usage`` and the salvaged ``partial`` answer.

SRC_ID = "src"


def _stage_request(phase: PhaseName, conv: str, text: str) -> LLMRequest:
    return LLMRequest(phase=phase, conversation_id=conv, system="You are a reviewer.",
                      messages=[{"role": "user", "content": [{"type": "text", "text": text}]}],
                      effort="medium", max_tokens=1000)


def _recorded(cfg: Any, rd: RunDir, cid: str, req: LLMRequest, *, start: float, elapsed: float,
              purpose: str = "", body: str | None = None, **extra: Any) -> dict[str, Any]:
    from datetime import UTC, datetime, timedelta

    t0 = datetime(2026, 10, 3, 9, 0, 0, tzinfo=UTC)
    return {"call_id": cid, "phase": req.phase.value, "purpose": purpose, "conversation_id": req.conversation_id,
            "request_sha256": request_hash("fake", req, cfg, rd), "backend": "fake", "attempt": 0,
            "outcome": "ok", "model": cfg.agent.model, "stop_reason": "end_turn",
            "started_at": (t0 + timedelta(seconds=start)).isoformat().replace("+00:00", "Z"),
            "start_offset_s": start, "elapsed_s": elapsed,
            "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0},
            "content": [{"type": "text", "text": body if body is not None else f"answer of {cid}"}], **extra}


#: The design's stage 1 (section 4 table), as completion order would log it: plan ends first (106 s),
#: understand (140 s), the four shards (about 208 s); research starts at 140 s.
STAGE1 = [  # (call id, phase, conversation, start offset s, elapsed s)
    ("llm-0002", PhaseName.PLAN, "plan-0", 3.6, 102.0),
    ("llm-0001", PhaseName.UNDERSTAND, "understand-0", 3.5, 136.0),
    ("llm-0007", PhaseName.RESEARCH, f"{SRC_ID}-research-0", 140.2, 20.0),
    ("llm-0004", PhaseName.ASSESS, "assess-0-s2", 3.7, 199.0),
    ("llm-0003", PhaseName.ASSESS, "assess-0-s1", 3.6, 201.5),
    ("llm-0006", PhaseName.ASSESS, "assess-0-s4", 3.8, 203.0),
    ("llm-0005", PhaseName.ASSESS, "assess-0-s3", 3.7, 204.5),
    ("llm-0008", PhaseName.RESEARCH, f"{SRC_ID}-research-1", 161.0, 30.0),
]


def _source(tmp_path: Path, entries: list[dict[str, Any]]) -> Any:
    from sit_review_agent.replay import RecordedCall, SourceRun

    by: dict[str, RecordedCall] = {}
    for e in entries:
        by.setdefault(e["call_id"], RecordedCall(call_id=e["call_id"], entries=[])).entries.append(e)
    return SourceRun(rd=RunDir(tmp_path / SRC_ID), config=load_config(), state={"run_id": SRC_ID}, report={},
                     manifest={}, calls=list(by.values()), tool_entries=[], catalogue=None, catalogue_source="",
                     backend="fake")


def _stage1(tmp_path: Path) -> tuple[Any, dict[str, LLMRequest]]:
    cfg = load_config()
    rd = RunDir(tmp_path / "hash")
    reqs: dict[str, LLMRequest] = {}
    entries = []
    for cid, phase, conv, start, elapsed in STAGE1:
        live_conv = conv.replace(SRC_ID, f"{SRC_ID}-replay-1")        # research names its run in the conversation
        reqs[cid] = _stage_request(phase, live_conv, f"brief for {conv}")
        rec_req = _stage_request(phase, conv, f"brief for {conv}")
        entries.append(_recorded(cfg, rd, cid, rec_req, start=start, elapsed=elapsed))
    return _source(tmp_path, entries), reqs


@pytest.mark.parametrize("order", ["recorded", "reversed", "launch"])
async def test_concurrent_stage1_calls_are_served_by_conversation_and_hash(tmp_path: Path, order: str) -> None:
    """Whatever order the replayed tasks ask in, each request gets its own recorded answer: matching is by
    conversation ID and request hash, not by position (design section 5, "Replay")."""
    import asyncio

    from sit_review_agent.replay import ReplayLLMGateway

    source, reqs = _stage1(tmp_path)
    gw = ReplayLLMGateway(source, RunDir(tmp_path / f"{SRC_ID}-replay-1").create(), load_config())
    ids = [c[0] for c in STAGE1]
    if order == "reversed":
        ids.reverse()
    elif order == "launch":
        ids.sort()
    results = await asyncio.gather(*(gw.call(reqs[cid]) for cid in ids))
    assert [r.call_id for r in results] == ids
    assert [r.text for r in results] == [f"answer of {cid}" for cid in ids]
    assert gw.remaining() == [] and gw.served == len(STAGE1)


async def test_a_changed_request_in_a_recorded_conversation_still_diverges(tmp_path: Path) -> None:
    from sit_review_agent.replay import ReplayDivergence, ReplayLLMGateway

    source, reqs = _stage1(tmp_path)
    gw = ReplayLLMGateway(source, RunDir(tmp_path / f"{SRC_ID}-replay-1").create(), load_config())
    bad = _stage_request(PhaseName.ASSESS, "assess-0-s3", "a brief the recording never saw")
    with pytest.raises(ReplayDivergence, match="request body hash"):
        await gw.call(bad)
    with pytest.raises(ReplayDivergence, match="no recorded response"):
        await gw.call(_stage_request(PhaseName.ASSESS, "assess-0-s9", "brief for assess-0-s9"))
    assert gw.served == 0                                   # nothing was consumed by the failed requests


async def test_identical_requests_of_one_conversation_are_served_in_log_order(tmp_path: Path) -> None:
    from sit_review_agent.replay import ReplayLLMGateway

    cfg = load_config()
    rd = RunDir(tmp_path / "hash")
    req = _stage_request(PhaseName.VERIFY, "verify", "repair the anchors")
    source = _source(tmp_path, [_recorded(cfg, rd, "llm-0010", req, start=390.0, elapsed=5.0),
                                _recorded(cfg, rd, "llm-0011", req, start=396.0, elapsed=4.0)])
    gw = ReplayLLMGateway(source, RunDir(tmp_path / "rp").create(), cfg)
    assert [(await gw.call(req)).call_id for _ in range(2)] == ["llm-0010", "llm-0011"]


async def test_replay_clock_follows_recorded_start_offsets_inside_stage_1(tmp_path: Path) -> None:
    """Each stage 1 member sees the run clock its own recorded calls saw, however the replay interleaves
    them; after the stage the clock stands at the latest member's end."""
    import asyncio
    from datetime import UTC, datetime

    from sit_review_agent.replay import ReplayClock, ReplayLLMGateway

    source, reqs = _stage1(tmp_path)
    clock = ReplayClock(datetime(2026, 10, 3, 9, 0, 0, tzinfo=UTC),
                        {"ingest": 3.5, "understand": 136.0, "plan": 102.0, "research": 51.0, "assess": 204.6})
    gw = ReplayLLMGateway(source, RunDir(tmp_path / f"{SRC_ID}-replay-1").create(), load_config(), clock=clock)
    clock.begin_phase("ingest")
    clock.end_phase("ingest")
    seen: dict[str, list[float]] = {}

    async def member(phase: PhaseName, cids: list[str]) -> None:
        clock.begin_phase(phase.value)
        try:
            for cid in cids:
                await gw.call(reqs[cid])
                seen.setdefault(phase.value, []).append(round(clock.monotonic(), 1))
                await asyncio.sleep(0)                         # let the other members interleave
        finally:
            clock.end_phase(phase.value)

    shards = ["llm-0006", "llm-0003", "llm-0005", "llm-0004"]   # served out of recorded order
    await asyncio.gather(member(PhaseName.ASSESS, shards), member(PhaseName.UNDERSTAND, ["llm-0001"]),
                         member(PhaseName.PLAN, ["llm-0002"]), member(PhaseName.RESEARCH, ["llm-0007", "llm-0008"]))
    assert seen["plan"] == [105.6] and seen["understand"] == [139.5]
    assert seen["research"] == [160.2, 191.0]                  # not pushed to 208 by the shards served first
    assert seen["assess"] == [206.8, 206.8, 208.2, 208.2]      # never backwards inside one member
    assert round(clock.monotonic(), 1) == 208.2                # the stage ends with its latest member
    clock.begin_phase("refine")
    assert round(clock.monotonic(), 1) == 208.2


def test_final_state_takes_the_latest_checkpoint_by_ordinal(tmp_path: Path) -> None:
    """A record without state.json: the latest checkpoint is the highest ordinal (W0
    ``checkpoint_file_order``), not the last file name; overlapping stage 1 members end in any order."""
    from sit_review_agent.replay import _final_state

    rd = RunDir(tmp_path / "run").create()
    for name, ordinal in (("02-understand", 3), ("03-plan", 1), ("04-research", 4), ("05-assess", 2)):
        (rd.checkpoints / f"{name}.json").write_text(
            json.dumps({"ordinal": ordinal, "state": {"run_id": "run", "last": name}}), encoding="utf-8")
    assert _final_state(rd)["last"] == "04-research"


def test_a_cut_call_is_rebuilt_with_its_salvage_and_estimate() -> None:
    """W1 logs a cut call's salvaged answer under ``partial`` and its estimate under the literal key
    ``estimated_usage`` (a dict). Replay raises the cut again with both mapped to the constructor's types,
    so the phase salvages the same findings; the measured ``usage`` stays None (accounting fixes)."""
    from sit_review_agent.errors import LLMDeadlineError
    from sit_review_agent.llm.gateway import Usage
    from sit_review_agent.replay import recorded_error

    partial = {"findings": [{"id": "draft-1"}, {"id": "draft-2"}]}
    est = {"input_tokens": 30000, "output_tokens": 12000, "cache_creation_input_tokens": 0,
           "cache_read_input_tokens": 0}
    err = recorded_error({"outcome": "LLMDeadlineError", "error": "cut at 265 s", "usage": None,
                          "usage_unrecorded": "deadline_cut", "partial": partial, "estimated_usage": est},
                         _request(), "llm-0005")
    assert isinstance(err, LLMDeadlineError) and err.usage is None
    assert err.partial == partial and err.salvaged_items == 2
    assert err.estimated_usage == Usage(input_tokens=30000, output_tokens=12000)
    for bad in ("not a dict", ["x"], {"input_tokens": "many"}):
        odd = recorded_error({"outcome": "LLMDeadlineError", "error": "cut", "partial": bad,
                              "estimated_usage": bad}, _request(), "llm-0006")
        assert isinstance(odd, LLMDeadlineError) and odd.partial is None and odd.estimated_usage is None


def _reorder_as_stage1(src: Path) -> list[str]:
    """Rewrite a sequential record's llm.jsonl in the order a concurrent stage 1 completes: plan, then
    understand, then research, then assess, then the rest. Returns the new phase order."""
    entries = JsonlWriter(src / "llm.jsonl").read()
    rank = {"plan": 0, "understand": 1, "research": 2, "assess": 3}
    stage1 = sorted((e for e in entries if e.get("phase") in rank), key=lambda e: rank[e["phase"]])
    rest = [e for e in entries if e.get("phase") not in rank]
    first = next(i for i, e in enumerate(entries) if e.get("phase") in rank)
    out = entries[:first] + stage1 + [e for e in rest if entries.index(e) >= first]
    (src / "llm.jsonl").write_text("".join(json.dumps(e) + "\n" for e in out), encoding="utf-8")
    return [e.get("phase") for e in out]


def test_replay_of_a_record_logged_in_completion_order_is_byte_equal(cfgdir: Path, no_network: None) -> None:
    """The fixture form of "replay of a concurrent run is byte-equal" (design section 7, W3 row): a record
    whose llm.jsonl is in stage 1 completion order replays to the same review (same finding and ledger
    IDs). The live form, a real concurrent run, is the integration pass's job (after W1 and W2)."""
    src = record(cfgdir, "conc", "--disable-tool", "mcp-research-information")
    phases = _reorder_as_stage1(src)
    assert phases.index("plan") < phases.index("understand")         # positional matching would diverge here
    res = replay(cfgdir, src, "conc-rp")
    assert res.exit_code == 0, res.output
    a = json.loads((src / "report.json").read_text(encoding="utf-8"))
    b = json.loads((src.parent / "conc-rp" / "report.json").read_text(encoding="utf-8"))
    assert compare_reports(a, b) == []
    assert [f["id"] for f in a["findings"]] == [f["id"] for f in b["findings"]]
    assert [e["evidence_id"] for e in a["evidence_ledger"]] == [e["evidence_id"] for e in b["evidence_ledger"]]
