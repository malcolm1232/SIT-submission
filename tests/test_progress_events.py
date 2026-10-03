"""Structured progress events and ``progress.jsonl`` (UI design note section 5, workstream UI-W1).

Every emit site gives its event a type and fields (the page never parses a message); ``call_opened``
and ``call_closed`` come for every model call, ``run_started`` first and ``run_finished`` last; each
run writes ``progress.jsonl`` beside ``progress.log``, one record per event, valid against
``spec/progress_event.schema.json``, flushed per event and free of model prose. The fixture runs are
the scenarios of ``test_progress_console.py`` (fake gateway, virtual clock), plus a concurrent
variant whose stage 1 calls are held open together, and a ``dra replay`` of a recorded run.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from typer.testing import CliRunner

import sit_review_agent.progress  # noqa: F401 - bind ConsoleProgress's default stream before CliRunner swaps it
from sit_review_agent.cli import app
from sit_review_agent.clock import FakeClock
from sit_review_agent.orchestrator import RunRequest, run_review
from sit_review_agent.paths import config_dir, repo_root
from sit_review_agent.progress import (
    PROGRESS_JSONL,
    CallEventsGateway,
    CallTracker,
    ConsoleProgress,
    NullProgress,
    ProgressJsonl,
    ToolProgress,
    draft_event,
    draft_line,
    emit_event,
    milestone,
    record_event,
)
from sit_review_agent.rundir import JsonlWriter
from sit_review_agent.selftest import FIXTURE_DIR, fixture_gateway, selftest_config
from test_progress_console import CUT_KEPT, CUT_SHARD, SHARD_COUNT, cut_factory, scenario

SCHEMA = json.loads((repo_root() / "spec" / "progress_event.schema.json").read_text(encoding="utf-8"))
#: Event types that come from code this workstream does not own (plain lines, typed by the adapter).
STAGE_1_FIRST_CALLS = ("understand", "plan", "assess")


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def jsonl_sink(root: Path) -> Any:
    """A sink factory for :func:`scenario` that writes one ``progress.jsonl`` per run under ``root``."""
    made: list[Path] = []

    def make(clock: FakeClock, out: io.StringIO) -> ConsoleProgress:
        path = root / f"progress-{len(made)}.jsonl"
        made.append(path)
        return ConsoleProgress(clock=clock, stream=out, jsonl_path=path)

    make.paths = made  # type: ignore[attr-defined]
    return make


def validate(records: list[dict[str, Any]]) -> None:
    for r in records:
        jsonschema.validate(r, SCHEMA)


def model_texts(run_dir: Path, *, min_len: int = 25) -> set[str]:
    """Every string of 25 or more characters in the run's model answers (``llm.jsonl`` content,
    read by script, never printed), except finding titles, the one model text the stream may carry."""
    out: set[str] = set()

    def walk(v: Any, key: str = "") -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, str) and len(v) >= min_len and " " in v and key != "title":
            out.add(v)

    for e in JsonlWriter(run_dir / "llm.jsonl").read():
        for block in e.get("content") or []:
            if block.get("type") == "text":
                try:
                    walk(json.loads(block["text"]))
                except ValueError:
                    walk(block["text"])
            elif block.get("type") == "tool_use":
                walk(block.get("input"))
    return out


# ------------------------------------------------------------------------------ item 1: fields


def test_plain_sinks_keep_their_old_shape() -> None:
    """``events`` still holds only console lines, so callers that read it see what they saw."""
    sink = NullProgress()
    sink.emit("plan", "a plain line")
    record_event(sink, "run", "run_started", "run x started", run_id="x")
    emit_event(sink, "plan", "a typed line", event="plan_ready", questions=3)
    assert [e.message for e in sink.events] == ["a plain line", "a typed line"]
    assert [e.event for e in sink.records] == ["status", "run_started", "plan_ready"]
    assert sink.records[2].fields == {"questions": 3}

    class Bare:                                     # a test double with only emit(): gets the plain line
        def __init__(self) -> None:
            self.lines: list[tuple[str, str, str]] = []

        def emit(self, phase: str, message: str, kind: str = "step") -> None:
            self.lines.append((phase, message, kind))

    bare = Bare()
    emit_event(bare, "plan", "typed", "done", event="plan_ready", questions=1)
    record_event(bare, "run", "run_started", "silent")
    assert bare.lines == [("plan", "typed", "done")]


def test_draft_event_keeps_codes_and_a_finding_title_only() -> None:
    item = {"id": "FND-002", "severity": "high", "kind": "risk", "title": "Retries\nwithout idempotency keys",
            "statement": "MODEL PROSE that must not reach the stream", "evidence": [{"quote": "a quote"}]}
    public, fields = draft_event("findings", 1, item, call_id="llm-0004", phase="assess", shard=2)
    assert public == "draft finding 2 (unverified; llm-0004 assess): [high] Retries without idempotency keys"
    assert fields == {"item": "finding", "list": "findings", "index": 2, "call_id": "llm-0004", "shard": 2,
                      "id": "FND-002", "severity": "high", "kind": "risk",
                      "title": "Retries without idempotency keys"}
    # the console line is the one draft_line has always printed
    assert draft_line("findings", 1, item, call_id="llm-0004", phase="assess").startswith(public)
    q_public, q_fields = draft_event("questions", 0, {"id": "RQ-001", "question": "MODEL PROSE question?"},
                                     call_id="c", phase="plan")
    assert "MODEL PROSE" not in q_public + json.dumps(q_fields)
    assert q_public == "draft question 1 (unverified; c plan): RQ-001"


def test_tracker_status_line_carries_each_open_call() -> None:
    async def scenario_() -> NullProgress:
        sink = NullProgress()
        tracker = CallTracker(sink, FakeClock(), interval_s=10.0)
        tracker.open("llm-0003", "assess")
        tracker.update("llm-0003", thinking_tokens=4210, items=2, chars=900)
        await asyncio.sleep(0)
        await tracker.clock.sleep(10.0)             # FakeClock: advances, lets the ticker run once
        await asyncio.sleep(0)
        tracker.close("llm-0003")
        return sink

    sink = asyncio.run(scenario_())
    status = [e for e in sink.records if e.event == "call_status"]
    assert status and status[0].message == "1 open call: llm-0003 assess: 2 items streamed (900 chars)"
    assert status[0].fields["calls"] == [{"call_id": "llm-0003", "phase": "assess", "label": "",
                                          "thinking_tokens": 4210, "items": 2, "chars": 900}]


def test_milestone_and_tool_lines_carry_their_data() -> None:
    sink = NullProgress()
    milestone(sink, "merged", "refine", findings=17, shards=4)
    assert sink.records[0].event == "milestone"
    assert dict(sink.records[0].fields) == {"name": "merged", "findings": 17, "shards": 4}
    tools = ToolProgress(sink)
    tools.emit("research", "blocked mcp-internet-search__fetch: https://private.invalid/x?q=secret not in results")
    tools.emit("tools", "waking mcp-internet-search (~90 s)", "wait")
    blocked, waking = sink.records[1], sink.records[2]
    assert blocked.message.startswith("blocked mcp-internet-search__fetch: https://")   # the console is unchanged
    assert blocked.public == "blocked mcp-internet-search__fetch by the tool policy"
    assert blocked.fields == {"tool": "mcp-internet-search__fetch", "blocked": True}
    assert waking.event == "tool_status" and waking.public is None and waking.kind == "wait"


async def test_every_event_of_the_fixture_runs_is_typed_and_valid(tmp_path: Path) -> None:
    """Every event of the three scenarios has a documented type other than ``status`` (each emit
    site of this workstream fills its fields) and validates against the schema."""
    seen: set[str] = set()
    for name in ("selftest", "shard_cut", "fail_resume"):
        make = jsonl_sink(tmp_path / name)
        (tmp_path / name).mkdir()
        await scenario(name, tmp_path / name, progress=make)
        records = [r for p in make.paths for r in jsonl(p)]
        validate(records)
        assert not [r for r in records if r["type"] == "status"], name
        seen |= {r["type"] for r in records}
    assert {"run_started", "call_opened", "call_closed", "run_finished", "phase_started", "phase_done",
            "milestone", "shard_drafted", "shard_cut", "run_error", "run_resuming", "plan_question"} <= seen
    assert seen <= set(SCHEMA["properties"]["type"]["enum"])


# ------------------------------------------------------------------------------ item 2: call events


async def test_every_model_call_opens_once_and_closes_once(tmp_path: Path) -> None:
    make = jsonl_sink(tmp_path)
    await scenario("selftest", tmp_path, progress=make)
    records = jsonl(make.paths[0])
    run_dir = tmp_path / "pc-selftest"
    logged = [e["call_id"] for e in JsonlWriter(run_dir / "llm.jsonl").read()]
    opened = [r for r in records if r["type"] == "call_opened"]
    closed = [r for r in records if r["type"] == "call_closed"]
    assert sorted(r["fields"]["call_id"] for r in opened) == sorted(logged)
    assert sorted(r["fields"]["call_id"] for r in closed) == sorted(logged)
    pos = {(r["type"], r["fields"]["call_id"]): r["seq"] for r in opened + closed}
    assert all(pos[("call_opened", c)] < pos[("call_closed", c)] for c in logged)
    shards = sorted((r["fields"]["shard"], r["fields"]["shard_name"]) for r in opened if r["phase"] == "assess")
    groups = [(s["index"], s["name"]) for s in records[0]["fields"]["shards"]]
    assert shards == groups and len(groups) == SHARD_COUNT
    for r in closed:
        f = r["fields"]
        assert f["outcome"] == "ok" and f["usage_status"] == "measured" and f["usage"]["input_tokens"] > 0
        assert f["stage"] in ("stage_1", "refine", "verify", "report") and f["purpose"]
        assert r["console"] is False


async def test_a_cut_call_closes_as_cut_with_what_it_kept(tmp_path: Path) -> None:
    make = jsonl_sink(tmp_path)
    await scenario("shard_cut", tmp_path, progress=make)
    records = jsonl(make.paths[0])
    cut = [r for r in records if r["type"] == "call_closed" and r["fields"]["outcome"] == "cut"]
    assert len(cut) == 1
    f = cut[0]["fields"]
    assert (f["shard"], f["kept_items"], f["kept"]) == (CUT_SHARD, CUT_KEPT, {"findings": CUT_KEPT})
    assert f["usage"] is None and f["usage_status"] == "unknown" and f["error"] == "LLMDeadlineError"


# ------------------------------------------------------------------------------ item 3: run events


async def test_run_started_comes_first_and_run_finished_last(tmp_path: Path) -> None:
    make = jsonl_sink(tmp_path)
    await scenario("selftest", tmp_path, progress=make)
    records = jsonl(make.paths[0])
    first, last = records[0], records[-1]
    assert first["type"] == "run_started" and last["type"] == "run_finished"
    f = first["fields"]
    cfg = selftest_config(tmp_path)
    assert f["run_id"] == "pc-selftest" and f["resumed"] is False and f["mode"] == "dev"
    assert f["deadline_s"] == cfg.stop_rules.deadline_seconds
    assert f["stage_limits_s"] == {k: float(v) for k, v in cfg.stop_rules.stage_limits_s.as_dict().items()}
    assert [d["role"] for d in f["documents"]] == ["under_review"] and f["documents"][0]["file"] == "design.pages.txt"
    assert [s["name"] for s in f["shards"]] == [s.name for s in cfg.agent.assess.shards]
    g = last["fields"]
    run_dir = tmp_path / "pc-selftest"
    assert (g["exit_code"], g["outcome"]) == (0, json.loads((run_dir / "manifest.json").read_text())["outcome"])
    assert g["report_md"] == str(run_dir / "report.md") and g["report_json"] == str(run_dir / "report.json")
    assert g["cost_usd"] is not None and g["cost_is_lower_bound"] is False and g["wall_s"] is not None


async def test_a_failed_run_finishes_with_its_exit_code_and_resume_continues_the_file(tmp_path: Path) -> None:
    """The failing run and its resume write to one ``progress.jsonl`` (the default sink of each)."""
    from sit_review_agent.orchestrator import resume_run
    from test_progress_console import failing_understand_factory

    cfg = selftest_config(tmp_path)
    pdf = FIXTURE_DIR / "design.pages.txt"
    res = await run_review(RunRequest(pdf=pdf, config=cfg, run_id="pe-fail"), clock=FakeClock(),
                           llm_factory=failing_understand_factory)
    assert res.exit_code == 3
    records = jsonl(res.run_dir / PROGRESS_JSONL)
    assert records[-1]["type"] == "run_finished" and records[-1]["fields"]["exit_code"] == 3
    assert records[-1]["fields"]["report_md"] is None
    err = [r for r in records if r["type"] == "run_error"]
    assert err and "connection reset" not in err[0]["message"]           # the error text stays on the console
    n = len(records)
    res2 = await resume_run(res.run_dir, cfg, clock=FakeClock())
    assert res2.exit_code == 0
    records = jsonl(res.run_dir / PROGRESS_JSONL)
    assert [r["seq"] for r in records] == list(range(1, len(records) + 1))
    assert records[n]["type"] == "run_started" and records[n]["fields"]["resumed"] is True
    assert records[-1]["type"] == "run_finished" and records[-1]["fields"]["exit_code"] == 0
    validate(records)


# ------------------------------------------------------------------------------ item 4: the file


async def test_a_run_writes_progress_jsonl_beside_progress_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]
                                                               ) -> None:
    res = await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=selftest_config(tmp_path),
                                      run_id="pe-file"), clock=FakeClock())
    assert res.exit_code == 0
    log = (res.run_dir / "progress.log").read_text(encoding="utf-8").splitlines()
    records = jsonl(res.run_dir / PROGRESS_JSONL)
    validate(records)
    assert [r["seq"] for r in records] == list(range(1, len(records) + 1))
    printed = [r for r in records if r["console"]]
    assert len(printed) == len(log)                       # one record per console line, in order
    for r, line in zip(printed, log, strict=True):
        assert line.split("| ", 1)[0].strip().endswith(r["phase"][:10].strip())
    assert capsys.readouterr().err.splitlines() == log    # the console is the log, unchanged
    assert (repo_root() / ".gitignore").read_text(encoding="utf-8").count(PROGRESS_JSONL) == 1


def test_each_event_is_on_disk_when_emit_returns(tmp_path: Path) -> None:
    path = tmp_path / PROGRESS_JSONL
    sink = NullProgress(jsonl_path=path, clock=FakeClock())
    for i in range(1, 4):
        emit_event(sink, "plan", f"line {i}", event="plan_ready", questions=i, external=0, criteria_skipped=0,
                   fallback=None)
        assert [r["fields"]["questions"] for r in jsonl(path)] == list(range(1, i + 1))
    again = ProgressJsonl(path)                           # a resumed run continues the sequence
    again.write(sink.records[0])
    assert [r["seq"] for r in jsonl(path)] == [1, 2, 3, 4]


async def test_the_stream_carries_no_model_prose(tmp_path: Path) -> None:
    """Every long string of every model answer of the run (statements, evidence quotes, plan
    questions, rationales, summaries) is absent from ``progress.jsonl``; finding titles may appear."""
    for name in ("selftest", "shard_cut"):
        root = tmp_path / name
        root.mkdir()
        make = jsonl_sink(root)
        await scenario(name, root, progress=make)
        text = make.paths[0].read_text(encoding="utf-8")
        run_dir = next(p for p in root.iterdir() if p.is_dir() and (p / "llm.jsonl").is_file())
        texts = model_texts(run_dir)
        assert len(texts) > 20                            # the check has something to find
        leaked = [t for t in texts if t in text or json.dumps(t)[1:-1] in text]
        assert not leaked, f"{len(leaked)} model text(s) in progress.jsonl"


# ------------------------------------------------------------------------------ item 5: concurrent run


class HoldStage1:
    """The fixture gateway, with the first calls of stage 1 (understand, plan, the assess shards)
    answered only once all of them are open, as the concurrent design overlaps them live. Each call
    gets its ID from the fake gateway first (``call_opened``), then waits."""

    def __init__(self, inner: Any, expected: int) -> None:
        self.inner = inner
        self.expected = expected
        self.waiting = 0
        self.release = asyncio.Event()

    def __getattr__(self, name: str) -> Any:
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.inner, name)

    async def call(self, request: Any) -> Any:
        held = request.phase.value in STAGE_1_FIRST_CALLS and not self.release.is_set()
        try:
            result = await self.inner.call(request)
        except BaseException:
            if held:
                await self._hold()
            raise
        if held:
            await self._hold()
        return result

    async def _hold(self) -> None:
        self.waiting += 1
        if self.waiting >= self.expected:
            self.release.set()
        await asyncio.wait_for(self.release.wait(), timeout=10)


def held_factory(cut: bool = False) -> Any:
    inner_factory = cut_factory() if cut else (lambda rd, clk, prog: fixture_gateway(rd, clock=clk))

    def factory(rd: Any, clk: Any, prog: Any) -> Any:
        return HoldStage1(inner_factory(rd, clk, prog), expected=2 + SHARD_COUNT)   # understand, plan, the shards
    return factory


async def concurrent_run(tmp_path: Path, run_id: str, *, cut: bool = False) -> list[dict[str, Any]]:
    res = await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=selftest_config(tmp_path),
                                      run_id=run_id), clock=FakeClock(), llm_factory=held_factory(cut),
                           progress=ConsoleProgress(clock=FakeClock(), stream=io.StringIO(),
                                                    jsonl_path=tmp_path / f"{run_id}.jsonl"))
    assert res.exit_code == 0
    return jsonl(tmp_path / f"{run_id}.jsonl")


def first_index(records: list[dict[str, Any]], pred: Any) -> int:
    return next(i for i, r in enumerate(records) if pred(r))


async def test_concurrent_fixture_run_streams_the_design_order(tmp_path: Path) -> None:
    records = await concurrent_run(tmp_path, "pe-conc")
    validate(records)
    assert records[0]["type"] == "run_started"
    first_close = first_index(records, lambda r: r["type"] == "call_closed")
    opened_before = [r for r in records[:first_close] if r["type"] == "call_opened"]
    assert sorted(r["fields"]["shard"] for r in opened_before if r["phase"] == "assess") == list(
        range(1, SHARD_COUNT + 1))
    assert {r["phase"] for r in opened_before} == {"understand", "plan", "assess"}
    drafted = [r for r in records if r["type"] == "shard_drafted"]
    assert sorted(r["fields"]["shard"] for r in drafted) == list(range(1, SHARD_COUNT + 1))
    assert all(d["severity"] is not None or d["kind"] == "strength" for r in drafted for d in r["fields"]["drafts"])
    assert any(d["severity"] for r in drafted for d in r["fields"]["drafts"])
    order = [r["fields"]["name"] for r in records if r["type"] == "milestone"]
    assert order[-2:] == ["merged", "verified"] and set(order[:2]) == {"intent", "plan"}
    stages = [r["fields"]["stage"] for r in records if r["type"] == "phase_started"]
    assert stages[0] == "ingest" and stages[-3:] == ["refine", "verify", "report"]
    last = records[-1]
    assert last["type"] == "run_finished" and last["fields"]["exit_code"] == 0
    assert last["fields"]["report_md"].endswith("pe-conc/report.md")


async def test_concurrent_deadline_cut_run_shows_the_cut_and_what_it_kept(tmp_path: Path) -> None:
    records = await concurrent_run(tmp_path, "pe-conc-cut", cut=True)
    validate(records)
    cut = [r for r in records if r["type"] == "shard_cut"]
    assert len(cut) == 1
    f = cut[0]["fields"]
    assert (f["shard"], f["kept"], len(f["kept_drafts"])) == (CUT_SHARD, CUT_KEPT, CUT_KEPT)
    assert f["call_id"] and f["kept_drafts"][0]["title"]
    closed = next(r for r in records if r["type"] == "call_closed" and r["fields"]["call_id"] == f["call_id"])
    assert closed["fields"]["outcome"] == "cut" and closed["fields"]["kept_items"] == CUT_KEPT
    assert records[-1]["type"] == "run_finished" and records[-1]["fields"]["exit_code"] == 0


# ------------------------------------------------------------------------------ item 6: replay


@pytest.fixture
def cfgdir(tmp_path: Path) -> Path:
    dst = tmp_path / "config"
    shutil.copytree(config_dir(), dst)
    agent = dst / "agent.yaml"
    agent.write_text(agent.read_text(encoding="utf-8").replace("run_root: runs", f"run_root: {tmp_path / 'runs'}"),
                     encoding="utf-8")
    return dst


#: Fields that name the run itself or a place on disk: a replay is another run in another directory,
#: with its own transport (``replay``) and no spend (``cost_usd`` 0).
RUN_IDENTITY = {"run_id", "run_dir", "report_md", "report_json", "partial_report", "resume", "mode", "transport",
                "cost_usd"}
#: Fields measured on the run clock: the recorded run ran on the system clock, its replay on the
#: replay clock, which follows the recorded timeline only to the precision of the log.
CLOCK_FIELDS = {"wall_s", "seconds", "merge_s", "slack_s", "cut_at_s", "at_s", "timeout_s", "delay_s"}
_DURATION = re.compile(r"\d+(?:\.\d+)? ?s\b")


def comparable(records: list[dict[str, Any]]) -> Iterator[tuple[Any, ...]]:
    """Each record without its clock offsets (``t``, ``run_s``), its clock-measured durations and
    the run's identity; the message keeps its text with the run directory, run ID and durations masked."""
    root, run_id = records[0]["fields"]["run_dir"], records[0]["fields"]["run_id"]
    for r in records:
        fields = {k: v for k, v in r["fields"].items() if k not in RUN_IDENTITY | CLOCK_FIELDS}
        message = _DURATION.sub("<s>", r["message"].replace(root, "<run>").replace(run_id, "<id>"))
        yield (r["seq"], r["type"], r["phase"], r["kind"], r["console"], message, json.dumps(fields, sort_keys=True))


def test_replay_produces_the_same_event_sequence(cfgdir: Path) -> None:
    pdf = FIXTURE_DIR / "design.pages.txt"
    cassettes = FIXTURE_DIR / "cassettes"
    res = CliRunner().invoke(app, ["run", str(pdf), "--config", str(cfgdir), "--transport", "fake", "--replay",
                                   str(cassettes), "--run-id", "pe-rec", "--disable-tool",
                                   "mcp-research-information"])
    assert res.exit_code == 0, res.output[-2000:]
    src = cfgdir.parent / "runs" / "pe-rec"
    res = CliRunner().invoke(app, ["replay", str(src), "--config", str(cfgdir), "--run-id", "pe-rec-rp"])
    assert res.exit_code == 0, res.output[-2000:]
    a = jsonl(src / PROGRESS_JSONL)
    b = jsonl(src.parent / "pe-rec-rp" / PROGRESS_JSONL)
    validate(a + b)
    assert b[0]["fields"]["mode"] == "replay" and a[0]["fields"]["mode"] != "replay"
    left, right = list(comparable(a)), list(comparable(b))
    assert len(left) == len(right)
    assert [x for x, y in zip(left, right, strict=True) if x != y] == []


# ------------------------------------------------------------------------------ the live backend's stream


async def test_claude_code_calls_open_before_their_streamed_drafts(tmp_path: Path) -> None:
    """On ``ClaudeCodeGateway`` (scripted ``claude -p`` stream) the call opens when the gateway
    numbers it, before its draft items stream; each draft item carries the call ID and its shard."""
    from sit_review_agent.config import load_config
    from sit_review_agent.llm.gateway import LLMRequest
    from sit_review_agent.states import PhaseName
    from test_stream_gateway import Findings, StreamRunner, finding, gateway, stream

    sink = NullProgress(jsonl_path=tmp_path / PROGRESS_JSONL)
    runner = StreamRunner(stream({"findings": [finding(1), finding(2)]}))
    gw, _ = gateway(tmp_path, load_config(), runner, progress=sink)
    layer = CallEventsGateway(gw, sink, FakeClock(), shard_names=lambda: ["intent", "quality", "evidence", "ops"])
    req = LLMRequest(phase=PhaseName.ASSESS, conversation_id="assess-0-s3", system="You are a reviewer.",
                     messages=[{"role": "user", "content": [{"type": "text", "text": "doc"}]}], effort="medium",
                     max_tokens=32000, output_schema=Findings, purpose="assess")
    await layer.call(req)
    everything = jsonl(tmp_path / PROGRESS_JSONL)
    validate(everything)
    status = [r for r in everything if r["type"] == "call_status"]    # the tracker's line (virtual clock)
    assert status and all(c["call_id"] == "llm-0001" for r in status for c in r["fields"]["calls"])
    records = [r for r in everything if r["type"] != "call_status"]
    assert [r["type"] for r in records] == ["call_opened", "draft_item", "draft_item", "call_closed"]
    assert {r["fields"]["call_id"] for r in records} == {"llm-0001"}
    assert records[0]["fields"]["shard"] == 3 and records[0]["fields"]["shard_name"] == "evidence"
    assert [(r["fields"]["shard"], r["fields"]["severity"], r["fields"]["title"]) for r in records[1:3]] == \
        [(3, "high", "Finding 1"), (3, "high", "Finding 2")]
    assert records[3]["fields"]["outcome"] == "ok" and records[3]["fields"]["usage"]["output_tokens"] == 400
