"""A stage whose answer is truncated twice at the output cap (robustness LLM-07, persistent variant;
Session 4 ruling "treat the second truncation like a deadline cut"), checked on a whole offline run
with billed usage on the truncated calls:

* the two truncated calls were paid for, so their tokens and cost are in the manifest totals and
  both are listed in ``extra.model.truncations``;
* ``resume`` on the finished, degraded run serves the existing report and makes no model call, so
  it can never repeat the two truncations.

The per-stage behaviour (understand, plan, assess, refine) is pinned end to end in
``tests/robustness/test_robustness_regressions.py`` (``truncates_twice``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sit_review_agent.clock import FakeClock
from sit_review_agent.llm.gateway import FakeResponse, LLMRequest, Usage
from sit_review_agent.manifest import PRICE_TABLE
from sit_review_agent.orchestrator import RunRequest, resume_run, run_review
from sit_review_agent.progress import NullProgress
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.selftest import FIXTURE_DIR, fixture_gateway, selftest_config

BILLED = Usage(input_tokens=7_000, output_tokens=128_000)


def _truncating_gateway(rd: Any, clock: Any, progress: Any) -> Any:
    gw = fixture_gateway(rd, clock=clock)
    for _ in range(2):
        gw.script["assess"].appendleft(FakeResponse(stop_reason="max_tokens", usage=BILLED))  # type: ignore[attr-defined]
    return gw


class _NoModel:
    """A gateway for ``resume``: any model call is a failure of the test."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def call(self, request: LLMRequest) -> Any:
        raise AssertionError(f"resume made a model call ({request.phase}, {request.purpose})")


async def test_truncated_calls_are_billed_in_the_manifest_and_resume_repeats_nothing(tmp_path: Path) -> None:
    cfg = selftest_config(tmp_path)
    out = await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=cfg, run_id="trunc2"),
                           llm_factory=_truncating_gateway, clock=FakeClock(), progress=NullProgress())
    assert out.exit_code == 0
    rd = RunDir(out.run_dir)
    entries = JsonlWriter(rd.llm_log).read()
    truncated = [e for e in entries if e.get("outcome") == "LLMTruncatedError"]
    assert [(e["phase"], e["purpose"]) for e in truncated] == [("assess", "assess"),
                                                               ("assess", "assess:max_tokens_retry")]
    assert all(e["usage"]["output_tokens"] == BILLED.output_tokens for e in truncated)

    manifest = json.loads(rd.manifest.read_text(encoding="utf-8"))
    assert manifest["outcome"] == "completed_degraded"
    assert manifest["extra"]["model"]["truncations"] == [
        {"call_id": e["call_id"], "stage": "assess", "purpose": e["purpose"]} for e in truncated]
    usage = manifest["usage"]
    logged_out = sum(int(e.get("usage", {}).get("output_tokens") or 0) for e in entries)
    logged_in = sum(int(e.get("usage", {}).get("input_tokens") or 0) for e in entries)
    assert usage["output_tokens"] == logged_out >= 2 * BILLED.output_tokens
    assert usage["input_tokens"] >= logged_in >= 2 * BILLED.input_tokens
    assert usage["cost_usd"] >= 2 * BILLED.output_tokens * PRICE_TABLE["usd_per_mtok"]["output"] / 1e6
    report = json.loads(rd.report_json.read_text(encoding="utf-8"))
    # The two truncations hit one shard (its call and its one retry): that shard's criteria are not
    # assessed and the shard is named; the other three shards still make an assessed review.
    events = [d["event"] for d in report["research_log"]["degradations"]]
    assert any(e.startswith("assess shard 1/4 (intent_and_fitness)") and "truncated twice" in e for e in events)
    assert report["verdict"]["label"] != "not_assessed" and report["findings"]
    assert report["run_manifest"]["extra"]["model"]["truncations"] == manifest["extra"]["model"]["truncations"]

    before = rd.report_json.read_bytes()
    again = await resume_run(out.run_dir, cfg, llm_factory=lambda r, c, p: _NoModel(fixture_gateway(r, clock=c)),
                             clock=FakeClock(), progress=NullProgress())
    assert again.exit_code == 0 and rd.report_json.read_bytes() == before
    assert len(JsonlWriter(rd.llm_log).read()) == len(entries)
