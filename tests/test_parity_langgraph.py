"""Feature parity of the LangGraph orchestrator variant with the custom loop (docs/COMPARISON_LANGGRAPH.md).

Every test runs the same scenario through both orchestrators (``orch`` = ``custom`` | ``langgraph``):
``run_review`` / ``resume_run`` of :mod:`sit_review_agent.orchestrator` with ``Orchestrator`` swapped
for :class:`LangGraphOrchestrator` by the fixture, the way ``--orchestrator langgraph`` does it. A
behaviour the variant cannot reproduce is marked ``xfail(strict=True)`` for ``langgraph`` with the
reason, so the tally of this file is the parity checklist. Scenario helpers are the existing tests'
(stand-in phases, the selftest fixture gateway, the robustness harness), not copies.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("langgraph", reason="the parity checklist needs the optional [langgraph] extra")

sys.path.insert(0, str(Path(__file__).parent / "robustness"))

from concurrent_schedules import load_concurrent_schedule, schedule_path  # noqa: E402
from robustness_harness import Scenario  # noqa: E402
from robustness_harness import run as run_scenario

import sit_review_agent.orchestrator as _orch  # noqa: E402
import test_cli_replay as tcr  # noqa: E402
import test_progress_console as tpc  # noqa: E402
import test_progress_events as tpe  # noqa: E402
import test_run_and_resume as trr  # noqa: E402
from sit_review_agent.clock import FakeClock  # noqa: E402
from sit_review_agent.llm.gateway import LLMRequest  # noqa: E402
from sit_review_agent.orchestrator import RunRequest, run_review  # noqa: E402
from sit_review_agent.orchestrator_langgraph import LangGraphOrchestrator, using_langgraph  # noqa: E402
from sit_review_agent.progress import NullProgress  # noqa: E402
from sit_review_agent.replay import compare_reports  # noqa: E402
from sit_review_agent.rundir import JsonlWriter  # noqa: E402
from sit_review_agent.states import STAGE_MEMBERS, PhaseName, Stage  # noqa: E402
from test_cli_replay import cfgdir, no_network  # noqa: E402,F401 - fixtures used by name

ORCHESTRATORS = ("custom", "langgraph")
#: The assess shards a fixture run launches under the committed config (four before decision #40).
K = tpc.SHARD_COUNT
STAGE_1 = {p.value for p in STAGE_MEMBERS[Stage.STAGE_1]}


@pytest.fixture(params=ORCHESTRATORS)
def orch(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Swap the orchestrator class the product's entry points use; ``custom`` leaves it alone."""
    if request.param == "langgraph":
        monkeypatch.setattr(_orch, "Orchestrator", LangGraphOrchestrator)
    return str(request.param)


def xfail_langgraph(orch: str, reason: str) -> None:
    if orch == "langgraph":
        pytest.xfail(reason)


# ------------------------------------------------------------------ 1. finding IDs across completion orders


class _DelayedShards(trr.ShardScript):
    """The shard script with each shard's answer delayed by a number of event-loop turns, so the
    shards end in the order of ``delays`` (shard index -> turns), whatever their launch order."""

    def __init__(self, cfg: Any, delays: dict[int, int]) -> None:
        super().__init__(cfg)
        self.delays = delays
        self.ended: list[int] = []

    def __call__(self, rd: Any, clock: Any, progress: Any) -> Any:
        gw = super().__call__(rd, clock, progress)
        inner = gw.call
        script = self

        async def call(request: LLMRequest) -> Any:
            if request.phase is PhaseName.ASSESS:
                i = int(request.conversation_id.rsplit("-s", 1)[1])
                for _ in range(script.delays.get(i, 0)):
                    await asyncio.sleep(0)
                script.ended.append(i)
            return await inner(request)

        gw.call = call  # type: ignore[method-assign]
        return gw


async def test_finding_ids_do_not_depend_on_the_completion_order(tmp_path: Path, orch: str) -> None:
    cfg = trr.config(tmp_path)
    k = len(cfg.agent.assess.shards_for(cfg.criteria.ids()))
    reports = []
    for n, delays in enumerate(({i: 3 * (i - 1) for i in range(1, k + 1)}, {i: 3 * (k - i) for i in range(1, k + 1)})):
        script = _DelayedShards(cfg, delays)
        out = await run_review(RunRequest(pdf=trr.PDF, config=cfg, run_id=f"order{n}"), phases=trr.shard_phases(),
                               llm_factory=script, tools_factory=trr.tools_factory, clock=FakeClock(),
                               progress=NullProgress())
        assert out.exit_code == 0
        assert script.ended == sorted(script.ended, key=lambda i: delays[i])       # the order was really different
        state = json.loads((out.run_dir / "state.json").read_text(encoding="utf-8"))
        drafts = [(d["id"], d["title"]) for d in state["finding_drafts"]]      # merged in shard order
        reports.append((trr.comparable(out.run_dir), drafts, state["finding_ids"]["shards"]))
    assert reports[0] == reports[1]
    _, drafts, _ = reports[0]
    assert [t for _, t in drafts] == [f"Shard {i} finding" for i in range(1, k + 1)]
    assert [i for i, _ in drafts] == [f"FND-{n:03d}" for n in range(1, k + 1)]


# ------------------------------------------------------------------ 2 and 9. a shard cut at the stage limit


async def test_a_shard_cut_at_the_stage_limit_keeps_its_findings(tmp_path: Path, orch: str) -> None:
    records = await tpe.concurrent_run(tmp_path, "cut", cut=True)
    tpe.validate(records)
    [cut] = [r for r in records if r["type"] == "shard_cut"]
    assert (cut["fields"]["shard"], cut["fields"]["kept"]) == (tpc.CUT_SHARD, tpc.CUT_KEPT)
    report = json.loads(Path(records[-1]["fields"]["report_json"]).read_text(encoding="utf-8"))
    assert report["run_manifest"]["outcome"] == "completed_degraded"
    cut_title = cut["fields"]["kept_drafts"][0]["title"]
    assert any(f["title"] == cut_title for f in report["findings"]), "the salvaged finding reached the report"
    assert any("was cut" in d["event"] for d in report["research_log"]["degradations"])


async def test_the_deadline_is_enforced_inside_a_model_call(tmp_path: Path, orch: str) -> None:
    """The cut happens inside the gateway (``LLMDeadlineError`` from ``llm.runtime.RunDeadline``), so
    the call closes as ``cut`` with what it kept and the run still exits 0: the orchestrator is not
    what enforces it, so both reproduce it unchanged."""
    records = await tpe.concurrent_run(tmp_path, "deadline", cut=True)
    [cut] = [r for r in records if r["type"] == "shard_cut"]
    call_id = cut["fields"]["call_id"]
    closed = next(r for r in records if r["type"] == "call_closed" and r["fields"]["call_id"] == call_id)
    assert closed["fields"]["outcome"] == "cut" and closed["fields"]["kept_items"] == tpc.CUT_KEPT
    assert records[-1]["type"] == "run_finished" and records[-1]["fields"]["exit_code"] == 0


# ------------------------------------------------------------------ 3. two truncations


def _truncate_every(stage: str) -> Any:
    def patch(data: dict[str, Any]) -> None:
        data["llm"] = [{"match": {"stage": stage},
                        "fault": {"type": "stop_reason", "value": "max_tokens", "truncate_at_fraction": 0.6}}]
    return patch


@pytest.mark.parametrize("stage", ["assess", "refine"])
def test_two_truncations_end_in_a_disclosed_report(stage: str, tmp_path: Path, orch: str) -> None:
    rec = run_scenario(Scenario(id=f"PAR-TRUNC2-{stage}", faults="LLM-07", variant=_truncate_every(stage)), tmp_path)
    assert rec.raised is None and rec.exit_code == 0 and rec.failure is None
    report = rec.report
    assert report is not None and rec.run_dir.report_md.is_file()
    manifest = json.loads(rec.run_dir.manifest.read_text(encoding="utf-8"))
    assert manifest["outcome"] == "completed_degraded"
    calls = [e for e in rec.jsonl("llm.jsonl") if e.get("phase") == stage]
    assert len(calls) == (2 * K if stage == "assess" else 2)
    assert len(manifest["extra"]["model"]["truncations"]) == len(calls)
    prefix = f"the {stage} answer was truncated twice at the output cap"
    assert any(d["event"].startswith(prefix) for d in report["research_log"]["degradations"])
    if stage == "assess":
        assert report["verdict"]["label"] == "not_assessed" and report["findings"] == []
    else:
        assert report["findings"] and report["verdict"]["label"] != "not_assessed"


# ------------------------------------------------------------------ 4. a declined assess


def test_a_declined_assess_gives_not_assessed(tmp_path: Path, orch: str) -> None:
    rec = run_scenario(Scenario(id="PAR-LLM06", faults="LLM-06"), tmp_path)
    assert rec.raised is None and rec.exit_code == 0
    report = rec.report
    assert report is not None
    assert rec.state["declined_sections"] == ["assess"]
    assert report["verdict"]["label"] == "not_assessed" and report["findings"] == []
    assert not [e for e in rec.jsonl("llm.jsonl") if e.get("phase") == "report"]      # no verdict call
    assess = [e for e in rec.jsonl("llm.jsonl") if e.get("phase") == "assess"]
    assert sorted(e.get("shard") for e in assess) == sorted(2 * list(range(1, K + 1)))   # one reframed retry each
    assert "Not assessed (the model declined the assessment)" in rec.run_dir.report_md.read_text(encoding="utf-8")


# ------------------------------------------------------------------ 5. a connection error on a first call


async def test_a_connection_error_on_a_first_call_exits_once_and_resumes(tmp_path: Path, orch: str) -> None:
    lines, _ = await tpc.scenario("fail_resume", tmp_path)                     # asserts exit 3, then resume 0
    errors = [ln for ln in lines if "error (LLMConnectionError, exit 3)" in ln]
    assert len(errors) == 1 and "resume with" in errors[0]
    [run_dir] = [p.parent for p in tmp_path.rglob("report.json") if p.parent.name == "pc-fail"]
    failure = json.loads((run_dir / "failure.json").read_text(encoding="utf-8"))   # the first run's record stays
    assert failure["error"] == "LLMConnectionError" and failure["exit_code"] == 3 and failure["resumable"]
    assert any("resuming run" in ln for ln in lines)                          # and the resume finished the run


# ------------------------------------------------------------------ 6. resume runs only the unfinished members


async def test_resume_runs_only_the_unfinished_members(tmp_path: Path, orch: str) -> None:
    await trr.test_resume_after_two_of_four_shards_runs_exactly_the_other_two(tmp_path)


async def test_resume_restores_the_run_clock_from_the_checkpoint(tmp_path: Path, orch: str) -> None:
    """``budget.elapsed_s`` (150 s here) is what resume restores, never the sum of the overlapping
    members' seconds; the per-member seconds depend on the start order, which the custom loop
    fixes and LangGraph does not, so only the elapsed value is asserted."""
    cfg = trr.config(tmp_path)
    phases = trr.stub_phases(understand=trr._Slow(trr.StubUnderstand(), 100), plan=trr._Slow(trr.StubPlan(), 50),
                             research=trr.Interrupt(PhaseName.RESEARCH))
    out = await trr.start(cfg, "clock", phases=phases)
    assert out.exit_code == 130
    ckpt = trr.latest_checkpoint(trr.RunDir(out.run_dir))
    assert ckpt is not None and ckpt.state.budget.elapsed_s == 150.0
    assert sum(ckpt.state.budget.phase_seconds.values()) > 150.0            # overlap: the sum is not the clock
    res = await trr.resume(cfg, out.run_dir)
    assert res.exit_code == 0
    final = trr.latest_checkpoint(trr.RunDir(out.run_dir))
    assert final is not None and final.phase is PhaseName.REPORT and final.state.budget.elapsed_s == 150.0


# ------------------------------------------------------------------ 7. byte-equal replay


def test_replay_of_a_recorded_run_is_byte_equal(cfgdir: Path, no_network: None, orch: str) -> None:  # noqa: F811
    """The run is recorded through the chosen orchestrator (the CLI flag); ``dra replay`` always
    re-runs through the product's replay path, so this also shows the variant's logs are the
    product's logs."""
    flag = ["--orchestrator", orch]
    src = tcr.record(cfgdir, f"rec-{orch}", "--disable-tool", "mcp-research-information", *flag)
    recorded = JsonlWriter(src / "llm.jsonl").read()
    assert sorted({e["conversation_id"] for e in recorded if e.get("phase") == "assess"}) == [
        f"assess-0-s{k}" for k in range(1, tcr.recorded_shard_count(src) + 1)]
    res = tcr.replay(cfgdir, src, f"rp-{orch}")
    assert res.exit_code == 0, res.output
    assert "matches the recording" in res.output
    rd = src.parent / f"rp-{orch}"
    a = json.loads((src / "report.json").read_text(encoding="utf-8"))
    b = json.loads((rd / "report.json").read_text(encoding="utf-8"))
    assert compare_reports(a, b) == []
    assert (src / "ledger.json").read_bytes() == (rd / "ledger.json").read_bytes()
    assert len(JsonlWriter(rd / "llm.jsonl").read()) == len(recorded)
    assert (src / "langgraph" / "variant.json").is_file() == (orch == "langgraph")


# ------------------------------------------------------------------ 8. per-shard fault injection


def test_a_process_fault_on_one_shard_ends_that_shard_only(tmp_path: Path, orch: str) -> None:
    """BEH-29 through ``faults_concurrent``: its shard (``shard_of``) raises at the start; the other
    shards' findings survive, the shard is disclosed by name, no crash."""
    cs = load_concurrent_schedule(schedule_path("BEH-29"))
    resolved = tmp_path / "BEH-29.resolved.yaml"
    resolved.write_text(cs.agent_yaml(), encoding="utf-8")
    rec = run_scenario(Scenario(id="PAR-BEH29", faults=str(resolved)), tmp_path / "run")
    assert rec.raised is None and rec.exit_code == 0 and rec.failure is None
    report = rec.report
    assert report is not None and report["findings"]
    [(index, name)] = [(t.index + 1, t.name) for t in cs.targets]           # schedules count shards from 0
    degs = [d["event"] for d in report["research_log"]["degradations"]]
    assert any(d.startswith(f"assess shard {index}/{len(cs.shards)} ({name}) failed (RuntimeError") for d in degs), degs
    lost = next(s.criteria for s in cs.shards if s.name == name)
    rows = {c["criterion_id"]: c for c in rec.state["coverage"]}
    assert all(rows[c]["outcome"] == "not_applicable" and rows[c]["note"].startswith("not assessed") for c in lost)
    assert report["verdict"]["label"] != "not_assessed"


def _refuse_nth(nth: int) -> Any:
    def patch(data: dict[str, Any]) -> None:
        data["llm"][0]["match"]["nth"] = [nth]
    return patch


def test_an_llm_fault_by_nth_hits_the_shard_in_launch_order(tmp_path: Path, orch: str) -> None:
    """``nth`` counts the stage's logical calls as they reach the gateway; the K shards' first calls
    are nth 0..K-1 in launch order (``concurrent_schedules``), so nth 1 is shard 2."""
    rec = run_scenario(Scenario(id="PAR-LLM06-nth1", faults="LLM-06", variant=_refuse_nth(1)), tmp_path)
    assert rec.raised is None and rec.exit_code == 0
    assess = [e for e in rec.jsonl("llm.jsonl") if e.get("phase") == "assess"]
    refused = [e for e in assess if e.get("outcome") == "LLMRefusalError"]
    assert [e.get("shard") for e in refused] == [2] and refused[0]["purpose"] == "assess"
    assert len([e for e in assess if e.get("shard") == 2]) == 2 and len(assess) == K + 1


# ------------------------------------------------------------------ 10. progress events


async def _events(tmp_path: Path, orch: str) -> list[dict[str, Any]]:
    if orch == "langgraph":
        with using_langgraph():
            records = await tpe.concurrent_run(tmp_path / orch, f"ev-{orch}")
    else:
        records = await tpe.concurrent_run(tmp_path / orch, f"ev-{orch}")
    return [r for r in records if not (r["type"] == "status" and r["message"].startswith("orchestrator:"))]


def _types(records: list[dict[str, Any]]) -> list[str]:
    return [r["type"] for r in records]


def _merged_at(records: list[dict[str, Any]]) -> int:
    return next(i for i, r in enumerate(records) if r["type"] == "milestone" and r["fields"]["name"] == "merged")


def _stage1_at(records: list[dict[str, Any]]) -> int:
    return next(i for i, r in enumerate(records) if r["type"] == "phase_started" and r["fields"]["stage"] == "stage_1")


async def test_progress_events_are_the_same_set_and_the_same_outside_stage_1(tmp_path: Path) -> None:
    a, b = await _events(tmp_path, "custom"), await _events(tmp_path, "langgraph")
    assert sorted(_types(a)) == sorted(_types(b))
    ia, ib = _merged_at(a), _merged_at(b)
    assert _types(a[ia:]) == _types(b[ib:])                                  # after stage 1 closes: identical
    sa, sb = _stage1_at(a), _stage1_at(b)
    assert _types(a[:sa]) == _types(b[:sb])                                  # before stage 1 starts: identical
    assert sorted(_types(a[sa:ia])) == sorted(_types(b[sb:ib]))             # stage 1: the same events


async def test_progress_events_follow_the_same_sequence(tmp_path: Path) -> None:
    """Strict sequence equality. Expected to fail for the variant: the custom loop starts the stage 1
    members in ``STAGE_1`` order (understand, plan, assess), LangGraph starts parallel nodes in its
    own order (by node name: assess shards, then the chain's plan before understand), so the stage 1
    stretch is a permutation of the same events."""
    a, b = _types(await _events(tmp_path, "custom")), _types(await _events(tmp_path, "langgraph"))
    if a != b:
        pytest.xfail("LangGraph starts parallel nodes in its own order (by node name), not in STAGE_1 order; "
                     "the stage 1 stretch of the stream is a permutation of the same events")
    assert a == b


# ------------------------------------------------------------------ what the variant cannot do


def test_a_process_fault_around_the_whole_assess_member(tmp_path: Path, orch: str) -> None:
    """BEH-25 on assess (``raise_in_stage`` with no ``shard``): the custom loop wraps the whole
    member (``_run_ProcessFault.run_shards``); the variant runs each shard as its own node through
    the phase's shard runner, so the member-level wrapper is never called. Per-shard faults
    (``shard: k``) apply in both (the test above)."""
    xfail_langgraph(orch, "the assess member is split into one node per shard; a process fault on the whole "
                          "member (no `shard` key) wraps `run_shards`, which the variant never calls")
    rec = run_scenario(Scenario(id="PAR-BEH25", faults="BEH-25"), tmp_path)
    assert rec.exit_code == 4 and rec.failure is not None and rec.failure["phase"] == "assess"
