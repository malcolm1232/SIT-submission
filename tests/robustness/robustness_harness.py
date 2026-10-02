"""Offline scenario runner for the robustness suite (research/robustness/README.md §4.3, §5, §6).

One :class:`Scenario` = one P0 scenario run end to end through the real orchestrator
(``orchestrator.run_review``) with every real phase, ``transport: fake`` (a strict
:class:`~sit_review_agent.tools.gateway.ReplayGateway` over ``fixtures/cassettes``), a scripted
:class:`~sit_review_agent.llm.gateway.FakeGateway`, a virtual clock and canary keys in the
environment. The fault schedule is the scenario's own ``faults/<ID>.yaml``, loaded by the agent's
loader through ``agent.fault_schedule`` exactly as ``sit-review run --faults <ID>`` does, so the
MCP and LLM fault injectors sit *below* the retry, breaker and budget policy (§5.1).

What the harness adds on top of the agent (the agent itself applies every layer of the schedule,
``process:`` entries included, since 2026-10-02: ``orchestrator._run_ProcessFault``):

* an **outbound log**: the bottom tool layer records every call that would have left the machine,
  so INV-08's "no secret in any outbound request" half can be checked offline (§2, §6.4);
* a **scripted model** built from the selftest fixture script (an invented, prompt-safe "campus
  room-booking" design, ``sit_review_agent/fixtures/selftest``): its research turn uses both enabled
  servers (web search + scholarly search, then a fetch), and a scenario may replace the research
  turns or patch any phase's structured answer (the model's adversarial or hollow output).

Nothing here touches the network or the ``claude`` CLI: the tool transport is a cassette replay and
the model is scripted (ADR-008).
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import heapq
import io
import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from sit_review_agent.clock import FakeClock
from sit_review_agent.config import ConfigOverrides, EffectiveConfig, Transport, load_config
from sit_review_agent.llm.gateway import FakeGateway, FakeResponse, LLMRequest, LLMResult, ToolUse
from sit_review_agent.orchestrator import RunOutcome, RunRequest, resume_run, run_review
from sit_review_agent.progress import ConsoleProgress
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.selftest import (
    FIXTURE_DIR,
    FIXTURE_FETCH_TOOL,
    FIXTURE_QUERY,
    FIXTURE_TOOL,
    FIXTURE_URL,
    fixture_script,
)
from sit_review_agent.states import PhaseName
from sit_review_agent.tools.faults import FaultSchedule, load_fault_schedule
from sit_review_agent.tools.gateway import ReplayGateway, ToolResult, build_tool_gateway, split_qualified

HERE = Path(__file__).resolve().parent
FAULTS_DIR = HERE / "faults"
CASSETTES = HERE / "fixtures" / "cassettes"
DOC = FIXTURE_DIR / "design.pages.txt"

WEB = FIXTURE_TOOL                                       # mcp-internet-search__search
FETCH = FIXTURE_FETCH_TOOL                               # mcp-internet-search__fetch
SCHOLAR = "mcp-research-information__search_works"
SCHOLAR_QUERY = "reminder e-mail delivery under a provider daily quota"
SERVERS = ("mcp-internet-search", "mcp-research-information")

#: Canary keys (README §6.4). Every scenario runs with these in the environment; INV-08 greps for them.
CANARY_MCP = "CANARY-MCP-7f3a9c5e1d20"
CANARY_LLM = "CANARY-LLM-c21e0b4d8a63"
CANARIES = (CANARY_MCP, CANARY_LLM)

#: Real-time watchdog per run (INV-01: nothing waits forever). Virtual time is checked separately.
WATCHDOG_S = 30.0

Patch = Callable[[dict[str, Any]], None]
ScriptEntry = FakeResponse | Callable[[list[dict[str, Any]], LLMRequest], FakeResponse]


# ============================================================================= virtual clocks


class SchedulingClock(FakeClock):
    """Virtual clock whose concurrent sleeps overlap (``FakeClock.sleep`` advances at once, so two
    parallel 90 s cold starts would cost 180 s). Every sleeper registers a wake-up time; once the
    runnable tasks have had a chance to reach their next sleep, time jumps to the earliest one.
    Same design as ``tests/test_fault_injection.py``; used for INF-01."""

    def __init__(self) -> None:
        super().__init__()
        self._heap: list[tuple[float, int, asyncio.Future[None]]] = []
        self._seq = 0
        self._driver: asyncio.Task[None] | None = None

    async def sleep(self, seconds: float) -> None:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        self._seq += 1
        heapq.heappush(self._heap, (self.monotonic() + max(0.0, seconds), self._seq, fut))
        if self._driver is None or self._driver.done():
            self._driver = loop.create_task(self._drive())
        await fut

    async def _drive(self) -> None:
        while self._heap:
            for _ in range(50):
                await asyncio.sleep(0)
            if not self._heap:
                return
            at, _, fut = heapq.heappop(self._heap)
            if at > self.monotonic():
                self.advance(at - self.monotonic())
            if not fut.done():
                fut.set_result(None)


# ============================================================================= scripted model


def ledger_ids(ledger: Sequence[Mapping[str, Any]], *, url: str | None = None) -> list[str]:
    """External ledger entries that were read in full (citable, ADR-007), optionally for one URL."""
    return [str(e["evidence_id"]) for e in ledger if e.get("source_type") == "external" and e.get("read_before_cite")
            and (url is None or e.get("url_or_citation") == url)]


def request_text(req: LLMRequest) -> str:
    """Every text string in the request's messages (the rendered briefs and tool results)."""
    out: list[str] = []

    def walk(v: Any) -> None:
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)

    walk(req.messages)
    return "\n".join(out)


def brief_questions(req: LLMRequest) -> dict[str, str]:
    """Question ID -> question text, as the research brief lists them (``- RQ-001 [search]: ...``)."""
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"(RQ-\d{3,}) \[[^\]]*\]: ([^\n]*)", request_text(req))}


def final_answer(ledger: list[dict[str, Any]], req: LLMRequest, *, stop: bool = True,
                 only: Sequence[str] | None = None) -> FakeResponse:
    """The research wrap-up: each question the brief lists (or only those whose text contains one
    of ``only``; the others stay open, i.e. not attempted) is answered with the read external
    entries, or ``unanswered`` when research produced none (a scripted model never invents IDs)."""
    ids = ledger_ids(ledger)
    qs = brief_questions(req)
    qids = sorted(q for q, text in qs.items() if only is None or any(o in text for o in only))
    answers = [{"question_id": q, "status": "answered" if ids else "unanswered",
                "summary": "The published plan allows 2,000 messages a day." if ids else "No evidence retrieved.",
                "evidence_ids": ids[:2]} for q in qids]
    return FakeResponse(parsed={"answers": answers, "stop_requested": stop,
                                "stop_rationale": "The external premises are resolved." if ids else "No evidence."})


def answer(*, stop: bool = True, only: Sequence[str] | None = None) -> ScriptEntry:
    return lambda ledger, req: final_answer(ledger, req, stop=stop, only=only)


def tool_turn(*calls: tuple[str, dict[str, Any]]) -> FakeResponse:
    def uid(name: str, args: dict[str, Any]) -> str:
        return "toolu_rb_" + hashlib.sha256(f"{name}|{json.dumps(args, sort_keys=True)}".encode()).hexdigest()[:12]

    return FakeResponse(tool_uses=[ToolUse(id=uid(n, a), name=n, input=a) for n, a in calls])


def two_source_research() -> list[ScriptEntry]:
    """Web search and scholarly search in parallel, then the fetch of the web hit (only a page read
    in full may be cited), then the wrap-up answer (repeated for wrap-up turns)."""
    return [tool_turn((WEB, {"query": FIXTURE_QUERY}), (SCHOLAR, {"query": SCHOLAR_QUERY})),
            tool_turn((FETCH, {"url": FIXTURE_URL})),
            *[final_answer] * 8]


def plan_two_sources(base: FakeResponse) -> FakeResponse:
    """The fixture plan plus a scholarly question, so both enabled servers have work."""
    parsed = copy.deepcopy(base.parsed)
    parsed["questions"].append({
        "id": "RQ-002", "criterion_id": "claims_and_external_constraints",
        "question": "Is there published evidence that providers reject over-quota messages instead of queueing them?",
        "rationale": "Section 6.2 sends reminders individually; rejected messages would be lost.",
        "needs_external": True, "capability": "scholarly", "queries": [SCHOLAR_QUERY], "section_refs": ["6.2"]})
    return FakeResponse(parsed=parsed)


def only_fixture_page(fn: Callable[..., FakeResponse]) -> Callable[..., FakeResponse]:
    """The fixture's assess/refine answers cite the first read external entry; show them only the
    fetched fixture page so the quotes they carry are in the cited excerpt (INV-05)."""
    def wrapped(ledger: list[dict[str, Any]], req: LLMRequest) -> FakeResponse:
        keep = [e for e in ledger if e.get("source_type") != "external" or e.get("url_or_citation") == FIXTURE_URL]
        return fn(keep, req)
    return wrapped


def build_script(criteria: list[str], research: list[ScriptEntry] | None) -> dict[str, list[ScriptEntry]]:
    base = fixture_script(criteria)
    s: dict[str, list[ScriptEntry]] = {
        "understand": [base["understand"][0]] * 3,
        "plan": [plan_two_sources(base["plan"][0])] * 3,                       # type: ignore[arg-type]
        "research": list(research) if research is not None else two_source_research(),
        "assess": [only_fixture_page(base["assess"][0])] * 4,                  # type: ignore[arg-type]
        "refine": [only_fixture_page(base["refine"][0])] * 4,                  # type: ignore[arg-type]
        "verify": [base["verify"][0]] * 3,
        "report": [base["report"][0]] * 3,
    }
    return s


class ScenarioGateway(FakeGateway):
    """``FakeGateway`` over :func:`build_script`. Callable entries are resolved against the run's
    ledger journal when their turn comes; ``patches[phase]`` then mutates a deep copy of the
    structured answer (the model's adversarial, hollow or flipping output)."""

    def __init__(self, rd: RunDir, clock: Any, script: dict[str, list[ScriptEntry]], *, model: str,
                 patches: Mapping[str, Patch] | None = None) -> None:
        super().__init__(script, run_dir=rd, clock=clock, model=model)     # type: ignore[arg-type]
        self.rd = rd
        self.patches = dict(patches or {})

    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        phase = str(request.phase)
        q = self.script.get(phase)
        if q:
            resp = q[0]
            if callable(resp):
                resp = resp(JsonlWriter(self.rd.ledger_journal).read(), request)
            if phase in self.patches and isinstance(resp.parsed, dict):
                parsed = copy.deepcopy(resp.parsed)
                self.patches[phase](parsed)
                resp = FakeResponse(parsed=parsed)
            q[0] = resp
        return await super().call(request)


# ============================================================================= outbound log


class OutboundReplayGateway(ReplayGateway):
    """The bottom tool layer: a strict cassette replay that logs every call reaching it. Calls the
    policy refused or a fault injector answered never get here, so this is the offline stand-in for
    the recording proxy's request log (README §5.1, INV-08)."""

    def __init__(self, *a: Any, outbound: list[dict[str, Any]], **k: Any) -> None:
        super().__init__(*a, **k)
        self.outbound = outbound

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        server, tool = split_qualified(tool_name)
        self.outbound.append({"server": server, "tool": tool, "args": copy.deepcopy(args),
                              "phase": phase.value if phase else None})
        return await super().call(tool_name, args, phase=phase)


# ============================================================================= generated fixtures


def long_design_pages(path: Path, pages: int = 150, lines_per_page: int = 30) -> Path:
    """The 150-page document of robustness LLM-10 (research/robustness/README.md §6.3), generated at
    test time and never committed: an invented campus-facilities design with numbered sections and
    requirement lines, about 3,700 characters per page (about 550k characters), in the page-marked
    text form the agent ingests like the selftest fixture. Text, not PDF: pdfplumber needs about a
    minute for 150 dense generated pages, past this suite's time budget, and LLM-10 is about the size
    of what would be sent, not about extraction."""
    out: list[str] = []
    for p in range(1, pages + 1):
        sec = (p - 1) // 5 + 1
        out.append(f"[[PAGE {p}]]")
        out.append(f"{sec}.{(p - 1) % 5 + 1} Facilities service area {p}. The wing {p} service is described below.")
        for i in range(1, lines_per_page):
            out.append(f"FAC-{p:03d}-{i:02d} The building service for wing {p} records each room booking, its "
                       f"cleaning slot and its sensor reading (line {i}) in the campus register.")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


# ============================================================================= scenario + run


@dataclass
class Scenario:
    """One end-to-end scenario run. ``faults`` names ``faults/<ID>.yaml`` (``None`` for scenarios
    driven by config or the scripted model only); ``variant`` patches the schedule data (a seed, a
    ``malformed_body`` kind) into a temp copy."""

    id: str
    faults: str | None = None
    variant: Callable[[dict[str, Any]], None] | None = None
    overrides: dict[str, Any] = field(default_factory=dict)             # ConfigOverrides fields (CLI flags)
    stop_rules: dict[str, Any] = field(default_factory=dict)
    agent: dict[str, Any] = field(default_factory=dict)                 # AgentConfig fields
    phases_enabled: dict[str, bool] = field(default_factory=dict)
    effort: dict[str, str] = field(default_factory=dict)                # per-phase effort (config/agent.yaml)
    research: list[ScriptEntry] | None = None
    patches: dict[str, Patch] = field(default_factory=dict)
    config_dir: Path | None = None                                       # a copied, edited config/ (DEMO-01)
    doc: Path = DOC
    clock: str = "fake"                                                  # fake | scheduling
    run_id: str | None = None
    env_unset: tuple[str, ...] = ()                                      # env vars removed for the run (INF-08)


@dataclass
class RunRecord:
    scenario: Scenario
    config: EffectiveConfig
    run_dir: RunDir
    exit_code: int | None
    raised: BaseException | None
    virtual_s: float
    wall_s: float
    stdout: str
    outbound: list[dict[str, Any]]
    gateway: ScenarioGateway | None
    tools: Any
    schedule: FaultSchedule | None

    @property
    def report(self) -> dict[str, Any] | None:
        p = self.run_dir.report_json
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    @property
    def failure(self) -> dict[str, Any] | None:
        p = self.run_dir.failure
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def jsonl(self, name: str) -> list[dict[str, Any]]:
        return JsonlWriter(self.run_dir.root / name).read()

    @property
    def state(self) -> dict[str, Any]:
        return json.loads(self.run_dir.state.read_text(encoding="utf-8")) if self.run_dir.state.is_file() else {}


def schedule_path(sc: Scenario, workdir: Path) -> Path | None:
    if sc.faults is None:
        return None
    src = FAULTS_DIR / f"{sc.faults}.yaml"
    if sc.variant is None:
        return src
    data = yaml.safe_load(src.read_text(encoding="utf-8"))
    sc.variant(data)
    dst = workdir / f"{sc.faults}.variant.yaml"
    dst.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return dst


def scenario_config(sc: Scenario, workdir: Path, faults: Path | None) -> EffectiveConfig:
    """``sit-review run <doc> --transport fake --replay tests/robustness/fixtures/cassettes
    --faults <ID> [flags]`` with runs under ``workdir``."""
    ov = ConfigOverrides(transport=Transport.FAKE, replay_fixtures=str(CASSETTES),
                         fault_schedule=str(faults) if faults is not None else None, **sc.overrides)
    cfg = load_config(sc.config_dir, ov)
    agent = cfg.agent.model_copy(update={"run_root": str(workdir / "runs"), "plan_approval": False, **sc.agent})
    if sc.phases_enabled:
        agent = agent.model_copy(update={"phases": agent.phases.model_copy(update=sc.phases_enabled)})
    if sc.effort:
        agent = agent.model_copy(update={"effort": agent.effort.model_copy(update=sc.effort)})
    stop = cfg.stop_rules.model_copy(update=sc.stop_rules) if sc.stop_rules else cfg.stop_rules
    return cfg.model_copy(update={"agent": agent, "stop_rules": stop})


class _Env:
    """Canary keys in the environment for the duration of a run (README §6.4); ``unset`` names
    variables removed instead (INF-08: the MCP key missing at start)."""

    def __init__(self, unset: tuple[str, ...] = ()) -> None:
        self.unset = unset

    def __enter__(self) -> None:
        self.saved = {k: os.environ.get(k) for k in ("SIT_MCP_API_KEY", "ANTHROPIC_API_KEY", *self.unset)}
        os.environ["SIT_MCP_API_KEY"] = CANARY_MCP
        os.environ["ANTHROPIC_API_KEY"] = CANARY_LLM
        for k in self.unset:
            os.environ.pop(k, None)

    def __exit__(self, *exc: object) -> None:
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _factories(sc: Scenario, cfg: EffectiveConfig, sched: FaultSchedule | None, outbound: list[dict[str, Any]],
               holder: dict[str, Any]) -> tuple[Any, Any]:
    def llm_factory(rd: RunDir, clock: Any, progress: Any) -> ScenarioGateway:
        gw = ScenarioGateway(rd, clock, build_script(cfg.criteria.ids(), sc.research), model=cfg.agent.model,
                             patches=sc.patches)
        gw.progress = progress                       # type: ignore[attr-defined]  (retry lines of the fault layer)
        holder["llm"] = gw
        return gw

    def tools_factory(rd: RunDir, resume_offset: int | None, clock: Any, progress: Any) -> Any:
        enabled = [s.name for s in cfg.tools.enabled_servers()]
        if not enabled:
            return None                              # doc-only run, as orchestrator._run_build_tools
        base = OutboundReplayGateway(CASSETTES, strict=True, servers=enabled, clock=clock,
                                     capabilities=cfg.tools.capabilities, outbound=outbound)
        gw = build_tool_gateway(cfg, rd, clock=clock, progress=progress, fault_schedule=sched,
                                resume_offset=resume_offset, base=base)
        holder["tools"] = gw
        return gw

    return llm_factory, tools_factory


async def _guarded(coro: Any) -> tuple[RunOutcome | None, BaseException | None]:
    try:
        return await asyncio.wait_for(coro, timeout=WATCHDOG_S), None
    except BaseException as exc:  # noqa: BLE001 - INV-11: anything escaping the entry point is recorded
        return None, exc


async def run_scenario(sc: Scenario, workdir: Path) -> RunRecord:
    """Run ``sc`` once, end to end, and return everything the oracles need."""
    workdir.mkdir(parents=True, exist_ok=True)
    faults = schedule_path(sc, workdir)
    cfg = scenario_config(sc, workdir, faults)
    sched = load_fault_schedule(faults) if faults is not None else None
    run_id = sc.run_id or sc.id
    rd = RunDir(workdir / "runs" / run_id)
    clock: FakeClock = SchedulingClock() if sc.clock == "scheduling" else FakeClock()
    out = io.StringIO()
    progress = ConsoleProgress(clock=clock, stream=out, log_path=rd.progress_log)
    outbound: list[dict[str, Any]] = []
    holder: dict[str, Any] = {}
    llm_factory, tools_factory = _factories(sc, cfg, sched, outbound, holder)
    t0 = time.monotonic()
    with _Env(sc.env_unset):
        outcome, raised = await _guarded(run_review(
            RunRequest(pdf=sc.doc, config=cfg, run_id=run_id), llm_factory=llm_factory,
            tools_factory=tools_factory, clock=clock, progress=progress))
    return RunRecord(scenario=sc, config=cfg, run_dir=rd, exit_code=outcome.exit_code if outcome else None,
                     raised=raised, virtual_s=clock.monotonic(), wall_s=time.monotonic() - t0, stdout=out.getvalue(),
                     outbound=outbound, gateway=holder.get("llm"), tools=holder.get("tools"), schedule=sched)


async def resume_scenario(rec: RunRecord, *, config: EffectiveConfig | None = None,
                          accept_drift: bool = False) -> RunRecord:
    """``sit-review resume <run_dir>`` on a recorded run, same harness services (a fresh virtual
    clock: the laptop clock keeps running, the run's own budget clock is restored from the
    checkpoint). The agent does not re-apply process faults on resume (the interruption is over)."""
    sc = rec.scenario
    cfg = config or rec.config
    sched = None
    if cfg.agent.fault_schedule:
        sched = load_fault_schedule(cfg.resolve_repo_path(cfg.agent.fault_schedule))
    clock = FakeClock()
    out = io.StringIO()
    progress = ConsoleProgress(clock=clock, stream=out, log_path=rec.run_dir.progress_log)
    outbound: list[dict[str, Any]] = []
    holder: dict[str, Any] = {}
    llm_factory, tools_factory = _factories(sc, cfg, sched, outbound, holder)
    t0 = time.monotonic()
    with _Env():
        outcome, raised = await _guarded(resume_run(rec.run_dir.root, cfg, accept_drift=accept_drift,
                                                    llm_factory=llm_factory, tools_factory=tools_factory,
                                                    clock=clock, progress=progress))
    return RunRecord(scenario=sc, config=cfg, run_dir=rec.run_dir, exit_code=outcome.exit_code if outcome else None,
                     raised=raised, virtual_s=clock.monotonic(), wall_s=time.monotonic() - t0, stdout=out.getvalue(),
                     outbound=outbound, gateway=holder.get("llm"), tools=holder.get("tools"), schedule=sched)


def run(sc: Scenario, workdir: Path | None = None) -> RunRecord:
    """Synchronous wrapper (scripts and the results command)."""
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix=f"robustness-{sc.id}-"))
    return asyncio.run(run_scenario(sc, workdir))


def resume(rec: RunRecord, **kw: Any) -> RunRecord:
    """Synchronous wrapper of :func:`resume_scenario`."""
    return asyncio.run(resume_scenario(rec, **kw))
