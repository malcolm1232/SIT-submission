"""The page's event contract against the agent's: ``ui/events.py`` reads what ``progress.ProgressJsonl``
writes (``spec/progress_event.schema.json``). The fixtures under ``tests/fixtures/ui/`` are real streams
of fixture runs on the fake gateway (``record_fixtures.py``): the concurrent selftest path, a deadline
cut and a failure resumed; every record of each validates against the schema here."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from sit_review_agent.ui import events, rundata

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "ui"
SCHEMA = json.loads((REPO / "spec" / "progress_event.schema.json").read_text(encoding="utf-8"))
NAMES = ("progress.jsonl", "progress_cut.jsonl", "progress_resume.jsonl")


def records(name: str) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in (FIXTURES / name).read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_the_readers_type_list_is_the_schemas_enum() -> None:
    assert list(events.TYPES) == SCHEMA["properties"]["type"]["enum"]
    assert list(events.KINDS) == SCHEMA["properties"]["kind"]["enum"]
    assert events.VERSION == SCHEMA["properties"]["v"]["const"]
    assert set(SCHEMA["required"]) == {"v", "seq", "t", "run_s", "type", "phase", "kind", "console", "message",
                                       "fields"}


@pytest.mark.parametrize("name", NAMES)
def test_every_fixture_record_validates_against_the_schema(name: str) -> None:
    recs = records(name)
    for r in recs:
        jsonschema.validate(r, SCHEMA)
        assert not events.event_problems(r), (name, r["seq"])
    assert [r["seq"] for r in recs] == list(range(1, len(recs) + 1))
    assert len(events.read_all(FIXTURES / name)) == len(recs)
    assert recs[0]["type"] == events.STARTED and recs[-1]["type"] == events.FINISHED
    assert recs[-1]["fields"]["exit_code"] == 0
    assert all("<run_root>" in r["fields"]["run_dir"] for r in recs if r["type"] == events.STARTED)


@pytest.mark.parametrize("name", NAMES)
def test_fixture_records_carry_no_prose_beyond_finding_titles(name: str) -> None:
    """No field string is longer than a finding title may be (schema: 110), except a code-built path
    or command; the recorder checked the records against the run's model answers when it wrote them."""
    long_keys = {"run_dir", "report_md", "report_json", "partial_report", "resume", "detail", "sha256_text",
                 "registry_sha256"}

    def walk(v: Any, key: str) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, str) and key not in long_keys:
            assert len(v) <= 110, (name, key, len(v))

    for r in records(name):
        walk(r["fields"], "")


def test_the_concurrent_fixture_opens_stage_1_together_and_drafts_per_shard() -> None:
    recs = records("progress.jsonl")
    started = events.started(recs)
    assert started and started["mode"] == "dev" and started["resumed"] is False
    assert sorted(started["stage_limits_s"]) == ["refine_end", "stage_1_end", "verdict_end"]
    assert len(started["shards"]) == 4 and events.under_review(started)["role"] == "under_review"
    first_close = next(i for i, r in enumerate(recs) if r["type"] == "call_closed")
    opened = [r["fields"] for r in recs[:first_close] if r["type"] == "call_opened"]
    assert sorted(f["shard"] for f in opened if f["shard"]) == [1, 2, 3, 4]
    drafted = [r["fields"] for r in recs if r["type"] == "shard_drafted"]
    assert sorted(f["shard"] for f in drafted) == [1, 2, 3, 4]
    assert sum(len(f["drafts"]) for f in drafted) == sum(f["findings"] for f in drafted) > 0
    assert all(set(d) == {"index", "kind", "severity", "title"} for f in drafted for d in f["drafts"])
    assert all(r["run_s"] <= s["run_s"] for r, s in zip(recs[3:], recs[4:], strict=False))   # the run clock


def test_the_cut_fixture_names_the_cut_shard_its_disclosure_id_and_what_it_kept() -> None:
    recs = records("progress_cut.jsonl")
    cut = [r for r in recs if r["type"] == "shard_cut"]
    assert len(cut) == 1
    f = cut[0]["fields"]
    assert f["shard"] == 2 and f["kept"] == 1 and len(f["kept_drafts"]) == 1 and f["criteria_not_assessed"]
    assert f["degradation_id"].startswith("DEG-")
    closed = next(r["fields"] for r in recs if r["type"] == "call_closed" and r["fields"]["call_id"] == f["call_id"])
    assert closed["outcome"] == "cut" and closed["kept_items"] == 1


def test_the_resume_fixture_continues_the_sequence_across_the_resume() -> None:
    recs = records("progress_resume.jsonl")
    starts = [i for i, r in enumerate(recs) if r["type"] == events.STARTED]
    assert len(starts) == 2 and recs[starts[1]]["fields"]["resumed"] is True
    err = next(i for i, r in enumerate(recs) if r["type"] == "run_error")
    assert starts[0] < err < starts[1]
    assert recs[err]["fields"]["exit_code"] == 3 and recs[err]["fields"]["resumable"] is True
    assert any(r["type"] == "run_resuming" for r in recs[starts[1]:])
    assert [r["seq"] for r in recs] == list(range(1, len(recs) + 1))
    assert recs[-1]["type"] == events.FINISHED and recs[-1]["fields"]["exit_code"] == 0


def test_old_shape_lines_are_not_events(tmp_path: Path) -> None:
    old = {"seq": 1, "t": 0.0, "phase": "run", "kind": "step", "message": "x", "event": "run started", "fields": {}}
    assert events.event_problems(old)
    new = records("progress.jsonl")[0]
    assert not events.event_problems(new)
    assert not events.event_problems({**new, "type": "a_type_added_later"})   # passed through, never dropped
    assert events.event_problems({**new, "v": 2}) and events.event_problems({**new, "run_s": -1})


def test_a_run_directory_with_only_a_stream_is_summarised_from_run_started(tmp_path: Path) -> None:
    rd = tmp_path / "only_events"
    rd.mkdir()
    (rd / "progress.jsonl").write_text((FIXTURES / "progress.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    row = rundata.summary(rd)
    started = events.started(records("progress.jsonl"))
    doc = events.under_review(started)
    assert row["document"] == doc["title"] and row["pages"] == doc["pages"]
    assert row["mode"] == "dev" and row["replayed"] is False and row["resumed"] is False
    assert row["status"] == "ended" and row["has_events"] and not row["has_report"]
    lines = (FIXTURES / "progress_resume.jsonl").read_text(encoding="utf-8")
    (rd / "progress.jsonl").write_text(lines, encoding="utf-8")
    assert rundata.summary(rd)["resumed"] is False       # the first run_started was not a resume
    replayed = {**records("progress.jsonl")[0], "fields": {**started, "mode": "replay"}}
    (rd / "progress.jsonl").write_text(json.dumps(replayed) + "\n", encoding="utf-8")
    assert rundata.summary(rd)["replayed"] is True
