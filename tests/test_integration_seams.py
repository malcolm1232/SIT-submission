"""Regression tests for the cross-workstream seams checked by the integration verifier (1a-1g).

Each test names its seam. The end-to-end flow on a real PDF is ``tests/test_e2e_synthetic.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sit_review_agent.clock import FakeClock
from sit_review_agent.config import load_config
from sit_review_agent.errors import ExitCode, LLMRefusalError
from sit_review_agent.invariants import check_all, check_INV_08
from sit_review_agent.llm.backend import supports_native_pdf
from sit_review_agent.llm.claude_code import ClaudeCodeGateway
from sit_review_agent.llm.gateway import (
    REDACTED_CANARY,
    AnthropicGateway,
    FakeGateway,
    FakeResponse,
    FaultInjectingLLMGateway,
    LLMCallLog,
    LLMRequest,
    ToolUse,
    Usage,
    prepare_resume,
)
from sit_review_agent.llm.outputs import PlanOutput
from sit_review_agent.manifest import merged_fallback_events, merged_refusals
from sit_review_agent.models import FallbackEvent
from sit_review_agent.orchestrator import RunRequest, _run_advance_ids, run_review
from sit_review_agent.phases import default_phases
from sit_review_agent.phases.plan import build_plan
from sit_review_agent.phases.research import ResearchPhase
from sit_review_agent.progress import NullProgress
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.selftest import FIXTURE_DIR, selftest_config
from sit_review_agent.state.run_state import RunState
from sit_review_agent.states import PhaseName
from sit_review_agent.tools.faults import FaultSchedule
from sit_review_agent.tools.gateway import FakeToolGateway, build_tool_gateway
from sit_review_agent.tools.mcp_client import ServerConnection

PAGES = FIXTURE_DIR / "design.pages.txt"


def req(phase: PhaseName = PhaseName.PLAN, conv: str = "c", **kw: Any) -> LLMRequest:
    kw.setdefault("messages", [{"role": "user", "content": "hi"}])
    return LLMRequest(phase=phase, conversation_id=conv, system="s", effort="high", max_tokens=100, **kw)


def schedule(*llm: dict[str, Any]) -> FaultSchedule:
    return FaultSchedule.model_validate({"id": "seam-test", "llm": list(llm)})


# =============================================================================== 1a refusals / fallbacks


def test_1a_refusals_and_fallbacks_are_merged_once() -> None:
    """state (phases, survives resume) + gateway (this process): each refusal and fallback once."""
    st = RunState(run_id="r", created_utc="2026-10-02T09:00:00Z")
    st.refusals = [{"call_id": "llm-0001", "stage": "plan", "category": "cyber"},
                   {"call_id": None, "stage": "assess", "category": None}]
    fb1 = FallbackEvent(role="plan", from_model="claude-opus-5-5", to_model="claude-opus-5", reason="call llm-0003")
    fb2 = FallbackEvent(role="research", from_model="claude-opus-5-5", to_model="claude-opus-5", reason="call llm-0007")
    st.fallback_events = [fb1]
    llm = SimpleNamespace(refusals=lambda: [{"call_id": "llm-0001", "stage": "plan", "category": "cyber"},
                                            {"call_id": None, "stage": "assess", "category": None},
                                            {"call_id": "llm-0009", "stage": "report", "category": None}],
                          fallback_events=lambda: [fb1, fb2])
    ctx = SimpleNamespace(state=st, llm=llm)
    assert [r["call_id"] for r in merged_refusals(ctx)] == ["llm-0001", None, "llm-0009"]   # type: ignore[arg-type]
    assert merged_fallback_events(ctx) == [fb1, fb2]                                         # type: ignore[arg-type]


async def test_1a_1f_injected_faults_through_the_pipeline(tmp_path: Path) -> None:
    """A 429 on plan (retried) and refusals on both report calls (rule verdict), through run_review:
    the manifest lists each refusal once with its own call ID, llm.jsonl has no duplicate call ID,
    usage counts only real calls, and the invariants hold."""
    sched = tmp_path / "faults.yaml"
    sched.write_text(json.dumps({"id": "seam-1a", "llm": [
        {"match": {"stage": "plan", "attempt": 0}, "fault": {"type": "http_status", "status": 429, "retry_after": 3}},
        {"match": {"stage": "report"}, "fault": {"type": "stop_reason", "value": "refusal", "category": "cyber"}}]}),
        encoding="utf-8")
    cfg = selftest_config(tmp_path / "runs")
    cfg = cfg.model_copy(update={"agent": cfg.agent.model_copy(update={"fault_schedule": str(sched)})})
    out = await run_review(RunRequest(pdf=PAGES, config=cfg, run_id="faults"), clock=FakeClock(),
                           progress=NullProgress())
    rd = RunDir(out.run_dir)
    assert out.exit_code == 0, rd.failure.read_text(encoding="utf-8") if rd.failure.exists() else ""
    report = json.loads(rd.report_json.read_text(encoding="utf-8"))
    assert [r.inv_id for r in check_all(report, rd.root) if not r.passed] == []
    refusals = report["run_manifest"]["extra"]["model"]["refusals"]
    assert [(r["stage"], r["category"]) for r in refusals] == [("report", "cyber"), ("report", "cyber")]
    assert len({r["call_id"] for r in refusals}) == 2 and None not in {r["call_id"] for r in refusals}
    entries = JsonlWriter(rd.llm_log).read()
    ids = [e["call_id"] for e in entries if e.get("call_id")]
    assert len(ids) == len(set(ids))                                      # 1f: no duplicate call IDs
    assert {r["call_id"] for r in refusals} <= set(ids)                  # each refusal is in llm.jsonl
    plan = [e for e in entries if e["phase"] == "plan"]
    assert [(e.get("fault"), e["call_id"]) for e in plan] == [("http_status", None), (None, "llm-0002")]
    ok = [e for e in entries if e.get("outcome", "ok") == "ok"]
    assert report["run_manifest"]["usage"]["input_tokens"] == sum(e["usage"]["input_tokens"] for e in ok)
    assert "verdict call failed" in json.dumps(report["research_log"]["degradations"])
    state = json.loads(rd.state.read_text(encoding="utf-8"))
    assert state["llm_calls"]["plan"] == ["llm-0002"]


def test_1a_assess_ledger_entries_carry_no_tool_reference(tmp_path: Path) -> None:
    """Doc and inference entries need no tool call; external entries cannot be created without one
    (covered end to end in test_e2e_synthetic; here the ledger contract itself)."""
    from sit_review_agent.errors import LedgerError
    from sit_review_agent.state.evidence_ledger import EvidenceLedger
    from sit_review_agent.tools.gateway import ToolResult
    from sit_review_agent.tools.sources import ExternalSource

    led = EvidenceLedger(RunDir(tmp_path / "r").create(), clock=FakeClock())
    d = led.add_doc(doc_id="DOC-x", page=1, section_ref="1", excerpt="a passage of the design document text")
    i = led.add_inference(statement="so the design is inconsistent", derived_from=[d.evidence_id])
    assert d.tool is None and i.tool is None and d.read_before_cite and i.derived_from == [d.evidence_id]
    failed = ToolResult(call_id="call-0001", server="s", tool_name="t", args={}, status="error", is_error=True,  # type: ignore[arg-type]
                        content=[], text="", structured_content=None, started_at="2026-10-02T09:00:00Z",
                        elapsed_s=0.0, cassette_key="k")
    with pytest.raises(LedgerError):
        led.add_external(failed, ExternalSource(url_or_citation="https://x.example/a", title="x", excerpt="x",
                                                content="x", authority=None, read_in_full=True))  # type: ignore[arg-type]


# =============================================================================== 1b warm-up


class _WarmTools:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False
        self.closed = False

    async def warm_up(self) -> dict[str, str]:
        self.started.set()
        try:
            await asyncio.Event().wait()                                 # a server that never wakes
        finally:
            self.cancelled = True
        return {}

    async def list_tools(self) -> list[Any]:
        return []

    async def call(self, *a: Any, **k: Any) -> Any:                   # pragma: no cover - not reached
        raise AssertionError("no tool call expected")

    async def aclose(self) -> None:
        self.closed = True


class _CrashAfterWarmUpStarted:
    name = PhaseName.INGEST

    def __init__(self, tools: _WarmTools) -> None:
        self.tools = tools

    async def run(self, ctx: Any) -> Any:
        await asyncio.wait_for(self.tools.started.wait(), 1.0)           # warm-up runs during ingest
        raise RuntimeError("planted bug in ingest")


async def test_1b_warm_up_overlaps_ingest_and_is_stopped_on_error(tmp_path: Path) -> None:
    tools = _WarmTools()
    phases = {**default_phases(), PhaseName.INGEST: _CrashAfterWarmUpStarted(tools)}
    out = await run_review(RunRequest(pdf=PAGES, config=selftest_config(tmp_path / "runs"), run_id="warm"),
                           phases=phases, tools_factory=lambda *a: tools, clock=FakeClock(), progress=NullProgress())
    assert out.exit_code == int(ExitCode.STAGE_CRASH)
    assert tools.cancelled and tools.closed
    assert json.loads((out.run_dir / "failure.json").read_text(encoding="utf-8"))["phase"] == "ingest"
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    assert pending == []


async def test_1b_cancelled_connect_does_not_leak_the_session_task() -> None:
    """MCPToolGateway's connection owner task was left running when the warm-up was cancelled
    while ``initialize`` was still pending (it is registered with the gateway only afterwards)."""

    @contextlib.asynccontextmanager
    async def hanging(*_a: Any) -> Any:
        await asyncio.Event().wait()
        yield None                                                      # pragma: no cover

    conn = ServerConnection()
    opening = asyncio.create_task(conn.open(hanging, "srv", "https://x.invalid", {}, 150.0, lambda *a: None))
    for _ in range(5):
        await asyncio.sleep(0)
    opening.cancel()
    with pytest.raises(asyncio.CancelledError):
        await opening
    assert [t.get_name() for t in asyncio.all_tasks() if t.get_name().startswith("mcp-session") and not t.done()] == []


async def test_1b_setup_failure_after_the_run_dir_exists_writes_failure_json(tmp_path: Path) -> None:
    """INV-02: once runs/<id>/ exists every failure leaves failure.json; a non-typed error becomes
    StageCrash (exit 4) rather than a traceback (INV-11)."""
    from sit_review_agent.errors import StageCrash

    def broken_llm(*_a: Any) -> Any:
        raise ValueError("backend construction bug")

    with pytest.raises(StageCrash) as info:
        await run_review(RunRequest(pdf=PAGES, config=selftest_config(tmp_path / "runs"), run_id="setup"),
                         llm_factory=broken_llm, clock=FakeClock(), progress=NullProgress())
    assert int(info.value.exit_code) == 4
    rec = json.loads((tmp_path / "runs" / "setup" / "failure.json").read_text(encoding="utf-8"))
    assert rec["exit_code"] == 4 and rec["stage"] == "setup" and "backend construction bug" in rec["cause"]


# =============================================================================== 1c llm.jsonl redaction


async def test_1c_llm_jsonl_never_holds_a_canary_from_a_tool_call(tmp_path: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-08 names logs: the model's tool_use input is redacted in llm.jsonl (the tool policy blocks
    the call itself); the live result the phase uses is unchanged."""
    key = "CANARY-MCP-7f3a9c0d1e2f"
    monkeypatch.setenv("SIT_MCP_API_KEY", key)
    rd = RunDir(tmp_path / "r").create()
    other = "CANARY-LLM-c21e00ff"                                        # a canary nobody configured
    gw = FakeGateway({"research": [FakeResponse(tool_uses=[ToolUse(id="t1", name="mcp-internet-search__search",
                                                                   input={"query": f"limits {key} {other}"})])]},
                     run_dir=rd)
    res = await gw.call(req(PhaseName.RESEARCH, messages=[{"role": "user", "content": f"doc mentions {key}"}]))
    assert key in res.tool_uses[0].input["query"]                        # the live object is not altered
    raw = rd.llm_log.read_text(encoding="utf-8")
    assert key not in raw and other not in raw and REDACTED_CANARY in raw
    assert check_INV_08(rd.root, [key, other]).passed


def test_1c_every_backend_logs_through_the_redacting_call_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_MCP_KEY", "s3cr3t-value-1234")
    cfg = load_config()
    cfg = cfg.model_copy(update={"tools": cfg.tools.model_copy(update={"auth_env": "MY_MCP_KEY"})})
    rd = RunDir(tmp_path / "r").create()
    for gw in (AnthropicGateway(cfg, rd, client=object()), ClaudeCodeGateway(cfg, rd), FakeGateway({}, run_dir=rd)):
        assert isinstance(gw.log, LLMCallLog)
    live = AnthropicGateway(cfg, rd, client=object())
    live.log.log({"call_id": "llm-0001", "phase": "plan", "content": [{"type": "text", "text": "s3cr3t-value-1234"}]})
    assert "s3cr3t-value-1234" not in rd.llm_log.read_text(encoding="utf-8")


# =============================================================================== 1d resume internals


def test_1d_prepare_resume_works_on_every_backend_and_through_the_fault_wrapper(tmp_path: Path) -> None:
    cfg = load_config()
    rd = RunDir(tmp_path / "r").create()
    for inner in (AnthropicGateway(cfg, rd, client=object()), ClaudeCodeGateway(cfg, rd), FakeGateway({}, run_dir=rd)):
        gw = FaultInjectingLLMGateway(inner, schedule())
        prepare_resume(gw, last_call_number=7, resumed_phase=PhaseName.REFINE)
        assert inner.next_call_id() == "llm-0008", type(inner).__name__
        assert inner.log.resumed_phases == {"refine"}                    # type: ignore[union-attr]


def test_1d_fault_wrapper_forwards_the_backends_pdf_capability(tmp_path: Path) -> None:
    cfg = load_config()
    rd = RunDir(tmp_path / "r").create()
    assert supports_native_pdf(FaultInjectingLLMGateway(ClaudeCodeGateway(cfg, rd), schedule())) is False
    assert supports_native_pdf(FaultInjectingLLMGateway(AnthropicGateway(cfg, rd, client=object()), schedule()))
    gw = FaultInjectingLLMGateway(AnthropicGateway(cfg, rd, client=object()), schedule())
    gw.native_pdf = False
    assert supports_native_pdf(gw) is False


async def test_1d_resumed_tool_call_ids_continue_on_every_layer(tmp_path: Path) -> None:
    """The policy layer keeps its own reference to the shared CallIds; replacing the base layer's
    object on resume left the policy counting from 0, so a refused call reused ``call-0001``."""
    cfg = selftest_config(tmp_path / "runs")
    rd = RunDir(tmp_path / "r").create()
    base = FakeToolGateway([], {}, clock=FakeClock())
    gw = build_tool_gateway(cfg, rd, clock=FakeClock(), progress=NullProgress(), resume_offset=0, base=base)
    _run_advance_ids(gw, 5)
    refused = await gw.call("not-a-qualified-name", {})
    assert refused.call_id == "call-0006"
    other = await gw.call("mcp-document-intelligence__parse", {})      # disabled server: refused by policy
    assert other.call_id == "call-0007"


# =============================================================================== 1e resumed flag


async def test_1e_resumed_calls_are_flagged_in_the_result_and_the_log(tmp_path: Path) -> None:
    rd = RunDir(tmp_path / "r").create()
    gw = FakeGateway({"refine": [FakeResponse(text="a")], "verify": [FakeResponse(text="b")]}, run_dir=rd)
    prepare_resume(gw, last_call_number=4, resumed_phase=PhaseName.REFINE)
    r1 = await gw.call(req(PhaseName.REFINE))
    r2 = await gw.call(req(PhaseName.VERIFY, conv="v"))
    assert (r1.call_id, r1.resumed, r2.call_id, r2.resumed) == ("llm-0005", True, "llm-0006", False)
    assert [e.get("resumed", False) for e in JsonlWriter(rd.llm_log).read()] == [True, False]


# =============================================================================== 1f fault wrapper accounting


async def test_1f_faulted_429_then_success_is_one_call(tmp_path: Path) -> None:
    rd = RunDir(tmp_path / "r").create()
    clock = FakeClock()
    inner = FakeGateway({"plan": [FakeResponse(text="ok", usage=Usage(input_tokens=10, output_tokens=2))]},
                        run_dir=rd, clock=clock)
    gw = FaultInjectingLLMGateway(inner, schedule({"match": {"attempt": 0}, "fault": {
        "type": "http_status", "status": 429, "retry_after": 5}}), clock=clock)
    res = await gw.call(req())
    assert gw.usage_total() == Usage(input_tokens=10, output_tokens=2)
    assert [(a.attempt, a.outcome, a.status_code) for a in res.attempts] == [
        (0, "LLMRateLimitError", 429), (1, "ok", None)]
    log = JsonlWriter(rd.llm_log).read()
    assert [(e["call_id"], e.get("fault")) for e in log] == [(None, "http_status"), ("llm-0001", None)]


async def test_1f_terminal_injected_fault_gets_a_call_id_and_is_counted_once(tmp_path: Path) -> None:
    rd = RunDir(tmp_path / "r").create()
    inner = FakeGateway({"plan": [FakeResponse(text="never")]}, run_dir=rd)
    gw = FaultInjectingLLMGateway(inner, schedule({"match": {}, "fault": {"type": "stop_reason", "value": "refusal",
                                                                           "category": "bio"}}))
    with pytest.raises(LLMRefusalError) as info:
        await gw.call(req())
    assert info.value.call_id == "llm-0001"
    assert gw.refusals() == [{"call_id": "llm-0001", "stage": "plan", "category": "bio"}]
    assert inner.refusals() == []                                        # the inner gateway is not poked
    assert [e["call_id"] for e in JsonlWriter(rd.llm_log).read()] == ["llm-0001"]


# =============================================================================== 1g question IDs


async def test_1g_research_uses_the_plans_ids_never_the_models(tmp_path: Path) -> None:
    """plan renumbers to RQ-nnn (criteria order); research shows the model only those IDs and merges
    answers by them; an answer under the model's original ID is ignored."""
    from collections import deque

    from test_research_phase import config, final, make_ctx  # type: ignore[import-not-found]

    ctx = make_ctx(tmp_path, [], c=config(max_research_iterations=1))
    out = PlanOutput.model_validate({"questions": [
        {"id": "Q-model-1", "criterion_id": "claims_and_external_constraints", "question": "Is the mail limit real?",
         "rationale": "claim", "needs_external": True, "capability": "search", "queries": ["mail limit"],
         "section_refs": ["1"]}], "criteria_skipped": []})
    ctx.state.plan, _ = build_plan(ctx, out)
    assert [q.id for q in ctx.state.plan.questions] == [f"RQ-{i + 1:03d}" for i in range(len(ctx.state.plan.questions))]
    [ext] = [q for q in ctx.state.plan.questions if q.needs_external]
    ctx.llm.script["research"] = deque([final((ext.id, "partial", []), ("Q-model-1", "answered", []))])  # type: ignore[attr-defined]
    await ResearchPhase().run(ctx)
    brief = json.dumps(ctx.llm.calls[0].messages)                       # type: ignore[attr-defined]
    assert ext.id in brief and "Q-model-1" not in brief
    assert ext.status == "partial"                                       # merged under the plan's ID only
