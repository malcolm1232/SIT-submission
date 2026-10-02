"""The two ``llm.jsonl`` fields the manifest and the replay of a concurrent run read (latency
integration, seam between W2's writers and W3a's readers): ``shard`` on every attempt of an assess
shard (its launch index, the same on its retries) and ``start_offset_s``, the run clock when the
attempt started. Before this pass no gateway wrote either, so a concurrent run's manifest read 0
shards and no stage 1 timing span.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sit_review_agent.clock import FakeClock
from sit_review_agent.llm.gateway import LLMCallLog, assess_shard_index
from sit_review_agent.orchestrator import RunRequest, run_review
from sit_review_agent.phases.assess import shard_conversation
from sit_review_agent.progress import NullProgress
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.selftest import FIXTURE_DIR, selftest_config


@pytest.mark.parametrize(("conversation", "shard"), [
    ("assess-0-s1", 1), ("assess-0-s4", 4), ("assess-0-s3-r1", 3), ("assess-2-s12-r1-r2", 12),
    ("assess-0", None), ("assess", None), ("refine-0", None), ("assess-0-sx", None), ("", None), (None, None)])
def test_the_shard_is_read_from_the_conversation(conversation: str | None, shard: int | None) -> None:
    assert assess_shard_index(conversation) == shard


def test_the_reader_follows_the_shard_conversation_name() -> None:
    assert [assess_shard_index(shard_conversation(0, k)) for k in range(1, 6)] == [1, 2, 3, 4, 5]
    assert assess_shard_index(shard_conversation(0, 2) + "-r1") == 2


def test_the_log_adds_the_shard_and_the_start_offset(tmp_path: Path) -> None:
    rd = RunDir(tmp_path / "r").create()
    log = LLMCallLog(rd)
    log.log({"call_id": "llm-0001", "phase": "assess", "conversation_id": "assess-0-s2"})   # no run clock yet
    log.run_elapsed = lambda: 100.0
    log.log({"call_id": "llm-0002", "phase": "assess", "conversation_id": "assess-0-s2-r1", "elapsed_s": 12.5})
    log.log({"call_id": "llm-0003", "phase": "plan", "conversation_id": "plan-0"})
    log.log({"call_id": "llm-0004", "phase": "research", "conversation_id": "research-0", "start_offset_s": 3.0})
    first, retry, plan, research = JsonlWriter(rd.llm_log).read()
    assert first["shard"] == 2 and "start_offset_s" not in first
    assert retry["shard"] == 2 and retry["start_offset_s"] == 87.5             # the attempt started 12.5 s ago
    assert "shard" not in plan and plan["start_offset_s"] == 100.0
    assert research["start_offset_s"] == 3.0                                    # a writer's own value is kept


async def test_a_concurrent_fake_run_logs_both_and_the_manifest_reads_them(tmp_path: Path) -> None:
    out = await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=selftest_config(tmp_path),
                                      run_id="fields"), clock=FakeClock(), progress=NullProgress())
    assert out.exit_code == 0
    rd = RunDir(out.run_dir)
    entries = JsonlWriter(rd.llm_log).read()
    assess = [e for e in entries if e["phase"] == "assess"]
    assert sorted(e["shard"] for e in assess) == [1, 2, 3, 4]
    assert all(e["conversation_id"] == f"assess-0-s{e['shard']}" for e in assess)
    assert not [e for e in entries if e["phase"] != "assess" and "shard" in e]
    assert all(isinstance(e["start_offset_s"], float) and e["start_offset_s"] >= 0 for e in entries)
    manifest = json.loads(rd.manifest.read_text(encoding="utf-8"))
    model = manifest["extra"]["model"]
    assert (model["assess_shards"], model["salvaged_calls"], model["salvaged_items"]) == (4, 0, 0)
    members = manifest["extra"]["timing"]["stages"]["stage_1"]["members"]
    assert {p: (m["start_offset_s"] is not None, m["end_offset_s"] is not None) for p, m in members.items()} == {
        p: (True, True) for p in ("understand", "plan", "research", "assess")}
