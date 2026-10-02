"""Manifest of a concurrent run (latency redesign W3 part A): estimates of cut calls beside the
measured-null record, per-stage timing with overlapping stage 1 members, shard and salvage counts,
and the same manifest for a sequential run.

Fixtures are small run states and ``llm.jsonl`` entries written here (no recorded model text). The
entry fields assumed (writers: W1 gateway, W2 orchestrator): ``call_id``, ``phase``, ``purpose``,
``attempt``, ``conversation_id``, ``elapsed_s``, ``start_offset_s`` (run clock seconds when the
attempt started), ``usage`` (``null`` with ``usage_unrecorded`` for a cut), ``estimated_usage`` or
``usage_estimate`` (the four ``Usage`` fields as non-negative integers), ``partial`` or
``salvaged_partial`` (list fields hold the finished items) or ``salvaged_items`` (a count). The run
state fields read: ``budget.phase_seconds`` (wall seconds per member), ``budget.started_monotonic``
and ``budget.elapsed_s`` (the run clock).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.clock import FakeClock, isoformat_z
from sit_review_agent.config import load_config
from sit_review_agent.context import RunContext
from sit_review_agent.llm.gateway import FakeGateway
from sit_review_agent.manifest import build_manifest, journal_usage
from sit_review_agent.models import Outcome
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
                   usage_estimate={**usage(4000, 1000), "estimated": True, "basis": {"chars_per_token": 4}})]
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
            rows[0]["cache_read_input_tokens"]) == (5000, 3000, 100, 50)
    tot = model["estimated_usage_totals"]
    assert tot["estimated"] is True and tot["calls"] == 2
    assert (tot["input_tokens"], tot["output_tokens"]) == (9000, 4000)
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
