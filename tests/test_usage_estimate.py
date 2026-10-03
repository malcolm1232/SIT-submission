"""The estimate of a cut call's output tokens uses the run's own measured output rate.

A call that ended early reports no usage; its logged estimate counts streamed characters at a fixed
characters-per-token constant, which read too low (58 and 66 output tokens per second against 96 to 140
for the calls of the same run that reported usage). The manifest therefore estimates such a call's output
tokens as the run's median output rate (output tokens per second of the calls that reported usage) times
the call's wall seconds, and falls back to the logged constant-based figure when no call reported usage.
Small ``llm.jsonl`` entries are written here; no recorded run data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sit_review_agent.manifest import journal_usage
from sit_review_agent.rundir import JsonlWriter, RunDir


def _usage(i: int = 0, o: int = 0) -> dict[str, int]:
    return {"input_tokens": i, "output_tokens": o, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}


def _ok(call_id: str, *, wall: float, out: int) -> dict[str, Any]:
    return {"call_id": call_id, "phase": "understand", "purpose": "understand", "attempt": 0, "outcome": "ok",
            "model": "claude-opus-5-5", "usage": _usage(1000, out), "elapsed_s": wall}


def _cut(call_id: str, *, wall: float, est_out: int) -> dict[str, Any]:
    return {"call_id": call_id, "phase": "assess", "purpose": "assess", "attempt": 0,
            "outcome": "LLMDeadlineError", "usage": None, "usage_unrecorded": "deadline_cut", "elapsed_s": wall,
            "estimated_usage": {**_usage(5000, est_out), "estimated": True}}


def _journal(tmp_path: Path, entries: list[dict[str, Any]]) -> dict[str, Any]:
    rd = RunDir(tmp_path / "run-u").create()
    w = JsonlWriter(rd.llm_log)
    for e in entries:
        w.append(e)
    return journal_usage(rd)


def test_a_cut_calls_output_estimate_uses_the_runs_measured_output_rate(tmp_path: Path) -> None:
    # two calls reported usage at 100 and 140 output tokens per second; the median of two is 120
    out = _journal(tmp_path, [_ok("llm-0001", wall=10.0, out=1000), _ok("llm-0002", wall=10.0, out=1400),
                              _cut("llm-0003", wall=200.0, est_out=11_600)])
    row = out["estimated_usage_of_unrecorded_calls"][0]
    assert row["output_tokens"] == 24_000                       # 120 tokens/s x 200 s, not the logged 11 600
    assert row["logged_output_tokens"] == 11_600
    assert row["output_basis"] == "measured_rate"
    assert row["input_tokens"] == 5000                          # the input side is the logged figure
    tot = out["estimated_totals"]
    assert tot["output_tokens"] == 24_000
    assert tot["output_basis"] == "measured_rate" and tot["output_tokens_per_s"] == 120.0
    assert tot["output_rate_calls"] == 2
    # the measured totals are untouched and the run stays a lower bound
    assert out["output_tokens"] == 2400
    assert [c["call_id"] for c in out["calls_with_unrecorded_usage"]] == ["llm-0003"]


def test_a_cut_calls_output_estimate_falls_back_to_the_constant_without_measured_usage(tmp_path: Path) -> None:
    out = _journal(tmp_path, [_cut("llm-0001", wall=200.0, est_out=11_600),
                              {**_ok("llm-0002", wall=5.0, out=0), "usage": _usage(0, 0)}])
    row = out["estimated_usage_of_unrecorded_calls"][0]
    assert row["output_tokens"] == 11_600 and row["logged_output_tokens"] == 11_600
    assert row["output_basis"] == "constant"
    tot = out["estimated_totals"]
    assert tot["output_basis"] == "constant" and tot["output_tokens_per_s"] is None
    assert tot["output_rate_calls"] == 0 and tot["output_tokens"] == 11_600


def test_replayed_faulted_and_timeless_calls_do_not_set_the_rate(tmp_path: Path) -> None:
    # only llm-0001 (50 tokens/s) counts: a replayed entry, an injected fault and a call without wall
    # seconds are left out of the rate
    out = _journal(tmp_path, [_ok("llm-0001", wall=10.0, out=500),
                              {**_ok("llm-0002", wall=1.0, out=9000), "replayed": True},
                              {**_ok("llm-0003", wall=1.0, out=9000), "fault": "x"},
                              {**_ok("llm-0004", wall=0.0, out=9000)},
                              _cut("llm-0005", wall=100.0, est_out=10)])
    tot = out["estimated_totals"]
    assert tot["output_tokens_per_s"] == 50.0 and tot["output_rate_calls"] == 1
    assert out["estimated_usage_of_unrecorded_calls"][0]["output_tokens"] == 5000
