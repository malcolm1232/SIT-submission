"""Manifest of a concurrent run (latency redesign W3 part A): estimates of cut calls beside the
measured-null record, per-stage timing with overlapping stage 1 members, shard and salvage counts,
and the same manifest for a sequential run.

Fixtures are small run states and ``llm.jsonl`` entries written here (no recorded model text). The
entry fields assumed (writers: W1 gateway, W2 orchestrator): ``call_id``, ``phase``, ``purpose``,
``attempt``, ``conversation_id``, ``elapsed_s``, ``start_offset_s`` (run clock seconds when the
attempt started), ``usage`` (``null`` with ``usage_unrecorded`` for a cut), ``estimated_usage``
(the four ``Usage`` fields as non-negative integers), ``partial`` (list fields hold the finished items)
and ``salvaged_items`` (a count), the names of ``LLMDeadlineError`` (planner ruling), ``shard``
(the assess shard's name or index, on every attempt of that shard; absent in a sequential run). The run
state fields read: ``budget.phase_seconds`` (wall seconds per member), ``budget.started_monotonic``
and ``budget.elapsed_s`` (the run clock).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sit_eval import usage as harness_usage
from sit_review_agent.clock import FakeClock, isoformat_z
from sit_review_agent.config import load_config
from sit_review_agent.context import RunContext
from sit_review_agent.llm.gateway import FakeGateway
from sit_review_agent.manifest import build_manifest, journal_usage
from sit_review_agent.models import ManifestExtra, Outcome
from sit_review_agent.progress import NullProgress
from sit_review_agent.prompts import PromptBundle
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.state.decision_registry import DecisionRegistry
from sit_review_agent.state.evidence_ledger import EvidenceLedger
from sit_review_agent.state.run_state import RunState

RUN = "run-c"


def usage(i: int = 0, o: int = 0, cw: int = 0, cr: int = 0) -> dict[str, int]:
    return {"input_tokens": i, "output_tokens": o, "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}


def ok(call_id: str, phase: str, conv: str, *, start: float | None, wall: float, u: dict[str, int]) -> dict[str, Any]:
    e: dict[str, Any] = {"call_id": call_id, "phase": phase, "purpose": phase, "attempt": 0, "conversation_id": conv,
                         "request_sha256": "0" * 64, "outcome": "ok", "model": "claude-opus-5-5", "usage": u,
                         "elapsed_s": wall}
    if start is not None:
        e["start_offset_s"] = start
    return e


def cut(call_id: str, phase: str, conv: str, *, start: float | None, wall: float, **extra: Any) -> dict[str, Any]:
    e: dict[str, Any] = {"call_id": call_id, "phase": phase, "purpose": phase, "attempt": 0, "conversation_id": conv,
                         "request_sha256": "1" * 64, "outcome": "LLMDeadlineError", "usage": None,
                         "usage_unrecorded": "deadline_cut", "elapsed_s": wall, **extra}
    if start is not None:
        e["start_offset_s"] = start
    return e


def make_ctx(tmp_path: Path, entries: list[dict[str, Any]], *, phase_seconds: dict[str, float] | None = None,
             run_clock_s: float = 0.0, elapsed_s: float = 0.0) -> RunContext:
    clock = FakeClock()
    rd = RunDir(tmp_path / RUN).create()
    w = JsonlWriter(rd.llm_log)
    for e in entries:
        w.append(e)
    state = RunState(run_id=RUN, created_utc=isoformat_z(clock.now_utc()))
    state.budget.phase_seconds = dict(phase_seconds or {})
    state.budget.elapsed_s = elapsed_s
    if run_clock_s:
        clock.advance(1000.0)                       # started_monotonic 0.0 means "not started"
        state.budget.started_monotonic = clock.monotonic()
        clock.advance(run_clock_s)
    return RunContext(config=load_config(), run_dir=rd, state=state, llm=FakeGateway({}), tools=None,
                      ledger=EvidenceLedger(rd, clock=clock), registry=DecisionRegistry(),
                      prompts=PromptBundle.load(), clock=clock, progress=NullProgress())


def model_extra(ctx: RunContext) -> dict[str, Any]:
    return build_manifest(ctx, Outcome.COMPLETED_DEGRADED).extra["model"]


# ------------------------------------------------------------------------- 1. estimates of cut calls


def test_a_cut_calls_estimate_sits_beside_its_measured_null_record(tmp_path: Path) -> None:
    entries = [ok("llm-0001", "understand", f"{RUN}-understand", start=0.0, wall=40.0, u=usage(1000, 200)),
               cut("llm-0002", "assess", f"{RUN}-assess-a", start=0.5, wall=170.0,
                   estimated_usage=usage(5000, 3000, 100, 50)),
               cut("llm-0003", "assess", f"{RUN}-assess-b", start=0.5, wall=170.0,
                   estimated_usage={**usage(4000, 1000), "estimated": True, "basis": {"chars_per_token": 4}})]
    ctx = make_ctx(tmp_path, entries)
    m = build_manifest(ctx, Outcome.COMPLETED_DEGRADED)
    model = m.extra["model"]
    # the measured record and flag are exactly as before
    assert [c["call_id"] for c in model["calls_with_unrecorded_usage"]] == ["llm-0002", "llm-0003"]
    assert model["cost_usd_lower_bound"] is True
    # the estimates are separate rows, each marked estimated
    rows = model["estimated_usage_of_unrecorded_calls"]
    assert [(r["call_id"], r["stage"], r["estimated"], r["reason"]) for r in rows] == [
        ("llm-0002", "assess", True, "deadline_cut"), ("llm-0003", "assess", True, "deadline_cut")]
    assert (rows[0]["input_tokens"], rows[0]["output_tokens"], rows[0]["cache_creation_input_tokens"],
            rows[0]["cache_read_input_tokens"]) == (5000, 850, 100, 50)  # 5 tokens/s measured x 170 s
    tot = model["estimated_usage_totals"]
    assert tot["estimated"] is True and tot["calls"] == 2
    assert (tot["input_tokens"], tot["output_tokens"]) == (9000, 1700)
    # the measured totals never include an estimate
    assert (m.usage.input_tokens, m.usage.output_tokens, m.usage.cached_tokens) == (1000, 200, 0)
    assert m.usage.cost_usd == pytest.approx((1000 * 4.0 + 200 * 20.0) / 1e6)


def test_a_malformed_estimate_is_not_listed_and_a_recorded_call_has_no_estimate_row(tmp_path: Path) -> None:
    entries = [cut("llm-0001", "assess", f"{RUN}-assess-a", start=0.0, wall=10.0,
                   estimated_usage={"input_tokens": -1, "output_tokens": 5}),
               cut("llm-0002", "plan", f"{RUN}-plan", start=0.0, wall=10.0,
                   estimated_usage={"input_tokens": True, "output_tokens": 5}),
               {**ok("llm-0003", "refine", f"{RUN}-refine", start=200.0, wall=30.0, u=usage(10, 10)),
                "estimated_usage": usage(99, 99)}]
    usage_out = journal_usage(make_ctx(tmp_path, entries).run_dir)
    assert usage_out["estimated_usage_of_unrecorded_calls"] == []
    assert usage_out["estimated_totals"]["calls"] == 0
    assert len(usage_out["calls_with_unrecorded_usage"]) == 2


def test_a_sequential_run_without_estimates_keeps_the_old_model_keys(tmp_path: Path) -> None:
    entries = [ok("llm-0001", "understand", f"{RUN}-plan", start=None, wall=10.0, u=usage(100, 10)),
               ok("llm-0002", "assess", f"{RUN}-assess", start=None, wall=20.0, u=usage(200, 20))]
    model = model_extra(make_ctx(tmp_path, entries))
    assert model["calls_with_unrecorded_usage"] == [] and model["cost_usd_lower_bound"] is False
    assert model["estimated_usage_of_unrecorded_calls"] == []
    assert model["estimated_usage_totals"]["calls"] == 0 and model["estimated_usage_totals"]["cost_usd"] == 0.0
    assert (model["assess_shards"], model["salvaged_calls"], model["salvaged_items"]) == (0, 0, 0)


# ------------------------------------------------------------------------- 2. per-stage and wall seconds

CONCURRENT_SECONDS = {"ingest": 2.0, "understand": 40.0, "plan": 60.0, "research": 90.0, "assess": 300.0,
                      "refine": 50.0, "verify": 1.5, "report": 20.0}


def concurrent_entries() -> list[dict[str, Any]]:
    """Stage 1 starts at 2.0 s: understand, plan and two assess shards together; research after plan."""
    return [ok("llm-0001", "understand", f"{RUN}-understand", start=2.0, wall=38.0, u=usage(100, 10)),
            ok("llm-0002", "plan", f"{RUN}-plan", start=2.0, wall=58.0, u=usage(100, 10)),
            {**ok("llm-0003", "assess", f"{RUN}-assess-a", start=2.1, wall=250.0, u=usage(100, 10)), "shard": "a"},
            ok("llm-0004", "research", f"{RUN}-research-0", start=61.0, wall=40.0, u=usage(100, 10)),
            ok("llm-0005", "research", f"{RUN}-research-1", start=102.0, wall=45.0, u=usage(100, 10)),
            {**ok("llm-0006", "assess", f"{RUN}-assess-b", start=2.1, wall=299.9, u=usage(100, 10)), "shard": "b"},
            ok("llm-0007", "refine", f"{RUN}-refine", start=303.0, wall=48.0, u=usage(100, 10)),
            ok("llm-0008", "report", f"{RUN}-report", start=354.0, wall=18.0, u=usage(100, 10))]


def test_overlapping_stage_1_members_give_the_span_not_the_sum(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path, concurrent_entries(), phase_seconds=CONCURRENT_SECONDS, run_clock_s=374.0)
    timing = build_manifest(ctx, Outcome.COMPLETED_NOMINAL).extra["timing"]
    assert timing["wall_clock_s"] == 374.0                     # the run clock
    assert timing["per_stage_s"] == CONCURRENT_SECONDS         # unchanged shape for the harness
    s1 = timing["stages"]["stage_1"]
    assert list(s1["members"]) == ["understand", "plan", "research", "assess"]
    assert {p: m["seconds"] for p, m in s1["members"].items()} == {
        "understand": 40.0, "plan": 60.0, "research": 90.0, "assess": 300.0}
    assert s1["members"]["research"]["start_offset_s"] == 61.0 and s1["members"]["research"]["end_offset_s"] == 147.0
    assert s1["sum_of_member_s"] == 490.0
    assert s1["wall_s"] == 300.0 and s1["wall_basis"] == "member_spans"   # 2.0 .. 302.0
    assert s1["wall_s"] < s1["sum_of_member_s"]
    assert list(timing["stages"]) == ["ingest", "stage_1", "refine", "verify", "report"]
    assert timing["stages"]["refine"] == {"members": {"refine": {"seconds": 50.0, "start_offset_s": 303.0,
                                                                 "end_offset_s": 351.0}},
                                          "wall_s": 50.0, "sum_of_member_s": 50.0, "wall_basis": "single_member"}
    assert timing["stages"]["verify"]["members"]["verify"]["start_offset_s"] is None   # code-only


def test_a_stage_span_is_at_least_its_longest_member(tmp_path: Path) -> None:
    entries = [ok("llm-0001", "understand", f"{RUN}-understand", start=5.0, wall=10.0, u=usage(1, 1)),
               ok("llm-0002", "assess", f"{RUN}-assess-a", start=5.0, wall=20.0, u=usage(1, 1))]
    ctx = make_ctx(tmp_path, entries, phase_seconds={"understand": 12.0, "assess": 26.0})
    s1 = build_manifest(ctx, Outcome.COMPLETED_NOMINAL).extra["timing"]["stages"]["stage_1"]
    assert s1["wall_s"] == 26.0 and s1["sum_of_member_s"] == 38.0


def test_a_sequential_run_reads_its_stage_wall_as_the_sum(tmp_path: Path) -> None:
    seconds = {"ingest": 1.0, "understand": 10.0, "plan": 20.0, "research": 30.0, "assess": 40.0, "report": 5.0}
    entries = [ok(f"llm-000{i}", p, f"{RUN}-{p}", start=None, wall=s - 1.0, u=usage(1, 1))
               for i, (p, s) in enumerate(seconds.items()) if p != "ingest"]
    ctx = make_ctx(tmp_path, entries, phase_seconds=seconds, run_clock_s=106.0)
    timing = build_manifest(ctx, Outcome.COMPLETED_NOMINAL).extra["timing"]
    s1 = timing["stages"]["stage_1"]
    assert s1["wall_s"] == s1["sum_of_member_s"] == 100.0 and s1["wall_basis"] == "sequential_sum"
    assert all(m["start_offset_s"] is None for m in s1["members"].values())
    assert "refine" not in timing["stages"]                    # a phase that did not run has no stage row
    assert timing["wall_clock_s"] == 106.0 and timing["per_stage_s"] == seconds


def test_the_wall_total_falls_back_to_the_checkpointed_run_clock(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path, [], phase_seconds={"ingest": 1.0}, elapsed_s=321.5)
    assert build_manifest(ctx, Outcome.CRASHED).extra["timing"]["wall_clock_s"] == 321.5
    ctx = make_ctx(tmp_path / "b", [], phase_seconds={})
    timing = build_manifest(ctx, Outcome.CRASHED).extra["timing"]
    assert timing["wall_clock_s"] == 0.0 and timing["stages"] == {}


def test_a_bad_start_offset_is_ignored(tmp_path: Path) -> None:
    entries = [ok("llm-0001", "understand", f"{RUN}-u", start=None, wall=5.0, u=usage(1, 1)),
               {**ok("llm-0002", "plan", f"{RUN}-p", start=None, wall=5.0, u=usage(1, 1)), "start_offset_s": True},
               {**ok("llm-0003", "assess", f"{RUN}-a", start=None, wall=5.0, u=usage(1, 1)), "start_offset_s": -3.0}]
    ctx = make_ctx(tmp_path, entries, phase_seconds={"understand": 6.0, "plan": 6.0, "assess": 6.0})
    s1 = build_manifest(ctx, Outcome.COMPLETED_NOMINAL).extra["timing"]["stages"]["stage_1"]
    assert s1["wall_basis"] == "sequential_sum" and s1["wall_s"] == 18.0


# ------------------------------------------------------------------------- 3. shard and salvage counts


def test_shards_and_salvage_are_counted_from_the_log(tmp_path: Path) -> None:
    entries = concurrent_entries() + [
        # the retry of shard "a" (a new conversation, latency W2) is the same shard, not another one
        {**ok("llm-0009", "assess", f"{RUN}-assess-a-r1", start=252.5, wall=20.0, u=usage(1, 1)), "shard": "a",
         "attempt": 1},
        # a shard cut with two finished findings salvaged
        {**cut("llm-0010", "assess", f"{RUN}-assess-c", start=2.1, wall=299.9, partial={"findings": [{}, {}]}),
         "shard": 2},
        # research cut, three items in two calls; a non-list field is not an item
        cut("llm-0011", "research", f"{RUN}-research-2", start=150.0, wall=152.0,
            partial={"answers": [{}], "note": "x"}),
        cut("llm-0012", "research", f"{RUN}-research-3", start=150.0, wall=152.0, salvaged_items=2),
        # a cut that salvaged nothing, and malformed counts, add nothing
        cut("llm-0013", "research", f"{RUN}-research-4", start=150.0, wall=152.0, partial=None),
        cut("llm-0014", "research", f"{RUN}-research-5", start=150.0, wall=152.0, salvaged_items=True),
        cut("llm-0015", "research", f"{RUN}-research-6", start=150.0, wall=152.0, partial={"findings": "x"})]
    model = model_extra(make_ctx(tmp_path, entries, phase_seconds=CONCURRENT_SECONDS, run_clock_s=374.0))
    assert model["assess_shards"] == 3
    assert model["salvaged_calls"] == 3 and model["salvaged_items"] == 5
    # the measured-null record of the cuts is unchanged by the counts
    assert len(model["calls_with_unrecorded_usage"]) == 6 and model["cost_usd_lower_bound"] is True


def test_a_shard_marker_counts_only_on_an_assess_attempt(tmp_path: Path) -> None:
    entries = [{**ok("llm-0001", "research", f"{RUN}-research-0", start=1.0, wall=5.0, u=usage(1, 1)), "shard": "a"},
               {**ok("llm-0002", "assess", f"{RUN}-assess-a", start=1.0, wall=5.0, u=usage(1, 1)), "shard": True},
               {**ok("llm-0003", "assess", f"{RUN}-assess-b", start=1.0, wall=5.0, u=usage(1, 1)), "shard": None},
               {**ok("llm-0004", "assess", f"{RUN}-assess-c", start=1.0, wall=5.0, u=usage(1, 1)), "shard": 0},
               {**ok("llm-0005", "assess", f"{RUN}-assess-c", start=1.0, wall=5.0, u=usage(1, 1)), "shard": "0"}]
    assert model_extra(make_ctx(tmp_path, entries))["assess_shards"] == 1


# ------------------------------------------------------------------------- 4. the harness reads both manifests


def test_the_harness_reads_a_sequential_and_a_concurrent_manifest_the_same_way(tmp_path: Path) -> None:
    sequential = [ok("llm-0001", "understand", f"{RUN}-understand", start=None, wall=10.0, u=usage(100, 10)),
                  ok("llm-0002", "assess", f"{RUN}-assess", start=None, wall=20.0, u=usage(200, 20))]
    concurrent = concurrent_entries() + [
        {**cut("llm-0009", "assess", f"{RUN}-assess-c", start=2.1, wall=299.9, estimated_usage=usage(5000, 3000),
               partial={"findings": [{}]}), "shard": "c"}]
    old = build_manifest(make_ctx(tmp_path / "s", sequential, phase_seconds={"understand": 10.0, "assess": 20.0},
                                  run_clock_s=31.0), Outcome.COMPLETED_NOMINAL)
    new = build_manifest(make_ctx(tmp_path / "c", concurrent, phase_seconds=CONCURRENT_SECONDS, run_clock_s=374.0),
                         Outcome.COMPLETED_DEGRADED)
    for m in (old, new):
        dumped = json.loads(json.dumps(m.model_dump(mode="json")))     # as manifest.json is written and read
        assert ManifestExtra.model_validate(dumped["extra"])          # INV-09 still accepts the extra block
        assert set(dumped["extra"]["timing"]) == {"wall_clock_s", "per_stage_s", "stages"}
        for key in ("assess_shards", "salvaged_calls", "salvaged_items", "calls_with_unrecorded_usage",
                    "cost_usd_lower_bound", "estimated_usage_of_unrecorded_calls", "estimated_usage_totals"):
            assert key in dumped["extra"]["model"]
    # the sequential run: complete usage, no shards, no estimates, the stage wall is the sum
    seq = harness_usage.from_manifest(json.loads(json.dumps(old.model_dump(mode="json"))))
    assert seq is not None and seq.status == harness_usage.COMPLETE and seq.lower_bound is False and seq.calls == ()
    assert old.extra["model"]["cost_usd_lower_bound"] is False
    assert old.extra["timing"]["stages"]["stage_1"]["wall_basis"] == "sequential_sum"
    # the concurrent run: one cut call makes the recorded figures a lower bound, whatever was estimated or salvaged
    con = harness_usage.from_manifest(json.loads(json.dumps(new.model_dump(mode="json"))))
    assert con is not None and con.status == harness_usage.UNRECORDED and con.lower_bound is True
    assert [c["call_id"] for c in con.calls] == ["llm-0009"] and con.calls[0]["reason"] == "deadline_cut"
    assert new.extra["model"]["cost_usd_lower_bound"] is True
    assert new.extra["model"]["estimated_usage_totals"]["calls"] == 1
    assert new.extra["model"]["salvaged_items"] == 1 and new.extra["model"]["assess_shards"] == 3
    assert new.usage.input_tokens == 800                                 # 8 recorded calls, never the estimate
