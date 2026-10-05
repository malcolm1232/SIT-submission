"""The run view in a real browser (Chromium through Playwright; skipped where either is missing) on
the recorded fixture streams and on a replayed run: a replay is stamped and never drawn as live, a
cut shard shows its disclosure ID and what it kept, and a failed run resumed continues on the page
with one sequence. The server is the real one on a loopback port; the page is the shipped page."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.ui import events
from sit_review_agent.ui.launcher import Launcher
from sit_review_agent.ui.server import UIState, build_app

REPO = Path(__file__).resolve().parents[1]
REHEARSAL = REPO / "docs" / "live_runs" / "rehearsal_concurrent_1"
REHEARSAL_PDF = REPO / "eval" / "synthetic" / "payments_orchestration" / "design_v1.pdf"
FIXTURES = Path(__file__).parent / "fixtures" / "ui"
RUN_FILES = ("report.json", "manifest.json", "anchors.json", "ledger.json", "state.json", "effective_config.json",
             "replay.json")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


@pytest.fixture(scope="module")
def replayed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """``dra replay`` of the committed rehearsal run into a scratch run root (offline: its recorded
    model calls are served from ``llm.jsonl``). The input is given by absolute path: the recording
    holds it relative to the repository, so the suite passes from any working directory."""
    from sit_review_agent.replay import replay_run

    root = tmp_path_factory.mktemp("replay_root")
    out = asyncio.run(replay_run(REHEARSAL, run_root=str(root), run_id="rehearsal_replay", pdf=REHEARSAL_PDF))
    # A record replays exactly at its own commit; later code that rewrites merged-away finding IDs in
    # report text (finding_refs.py) may change those text fields and nothing else; the delta table
    # (``prior_findings``, 2026-10-03) is new, and empty for this full review.
    assert out.report_md is not None and not out.message.startswith("replay failed"), out.message
    assert all(re.fullmatch(r"\$\.(findings|sound_areas)\[\d+\]\.(statement|why_sound)|\$\.prior_findings", d)
               for d in out.differences), out.differences
    return Path(out.run_dir)


@pytest.fixture
def served(tmp_path: Path, replayed: Path):
    uvicorn = pytest.importorskip("uvicorn")
    runs = tmp_path / "runs"
    for name in ("progress.jsonl", "progress_cut.jsonl", "progress_resume.jsonl"):
        d = runs / name[:-len(".jsonl")]
        d.mkdir(parents=True)
        shutil.copy2(FIXTURES / name, d / "progress.jsonl")
    rp = runs / replayed.name
    rp.mkdir()
    for name in (*RUN_FILES, "progress.jsonl"):
        if (replayed / name).is_file():
            shutil.copy2(replayed / name, rp / name)
    state = UIState(runs_dir=runs.resolve(), repo_root=REPO, launcher=Launcher(repo_root=REPO), chat_client=None,
                    profiles=[], tools=[])  # type: ignore[arg-type]
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(build_app(state), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", runs, state
    server.should_exit = True
    th.join(timeout=5)


@pytest.fixture
def page(served):
    sync_api = pytest.importorskip("playwright.sync_api")
    base, runs, state = served
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Chromium not installed here
            pytest.skip(f"Chromium not available: {exc}")
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        yield pg, base, runs, state
        browser.close()
    assert errors == []


def open_run(pg: Any, base: str, run_id: str, tab: str | None = None) -> None:
    pg.goto(base + f"/?run={run_id}" + (f"&tab={tab}" if tab else ""))
    pg.wait_for_function("document.querySelector('#finished-bar') && !document.querySelector('#finished-bar').hidden")


def tracks(pg: Any) -> dict[str, tuple[str, str]]:
    rows = pg.evaluate("[...document.querySelectorAll('.track')].map(t => [t.dataset.track, t.dataset.status, "
                       "t.querySelector('.status').textContent])")
    return {r[0]: (r[1], r[2]) for r in rows}


# ------------------------------------------------------------------ the replayed run (design note section 8)


def test_a_replayed_run_is_stamped_and_never_drawn_as_live(page) -> None:
    pg, base, runs, _state = page
    rp = next(p for p in runs.iterdir() if p.name.startswith("rehearsal_replay"))
    evs = records(rp / "progress.jsonl")
    assert events.started(evs)["mode"] == "replay"
    opened = {r["fields"]["call_id"]: r["run_s"] for r in evs if r["type"] == "call_opened"}
    closed = {r["fields"]["call_id"]: r["run_s"] for r in evs if r["type"] == "call_closed"}
    assert opened and all(opened[c] == closed[c] for c in opened)      # replay opens a call just before closing it
    open_run(pg, base, rp.name, tab="log")
    assert pg.locator("#replay-stamp").inner_text() == "replayed evidence"
    assert pg.locator(".pill.running").count() == 0 and pg.locator("#top-action button").count() == 0
    t = tracks(pg)
    assert all(t[k][0] == "done" for k in ("ingest", "understand", "plan", "refine", "verify", "report"))
    # The rehearsal ran document-only: research had no tool gateway, which the page shows as skipped, not failed.
    assert t["research"][0] == "skipped" and t["research"][1].startswith("document only (no tool server in use): ")
    assert sorted(k for k in t if k.startswith("assess ")) == ["assess 1/4", "assess 2/4", "assess 3/4", "assess 4/4"]
    # Fed record by record through the page's reducer, a track is never "running": in flight means "replayed".
    seen = pg.evaluate("(evs) => { const m = SIT.newRunModel(); const st = new Set(); for (const ev of evs) { "
                       "SIT.applyEvent(m, ev); for (const t of m.tracks.values()) st.add(t.status); } "
                       "return [...st]; }", evs)
    assert "running" not in seen and "replayed" in seen
    report = json.loads((rp / "report.json").read_text(encoding="utf-8"))
    assert pg.locator("#finished-bar").inner_text().endswith(f"{len(report['findings'])} findings.")


# ------------------------------------------------------------------ a run opened before its first event


class _AliveProc:
    pid = 4242

    def __init__(self) -> None:
        self.code: int | None = None

    def poll(self) -> int | None:
        return self.code

    def send_signal(self, sig: int) -> None:
        self.code = 130


def test_a_run_opened_before_its_first_event_follows_the_file_once_it_appears(page) -> None:
    """The page opens the run right after POST /runs, before the child has written progress.jsonl
    (the first live run from the page showed an empty timeline for 14 minutes for this reason):
    the stream is subscribed at once and the server follows the file from the moment it appears."""
    from sit_review_agent.ui.launcher import Launched

    pg, base, runs, state = page
    rd = runs / "just_started"
    (rd / "ui").mkdir(parents=True)
    (rd / "ui" / "launch.json").write_text(json.dumps({"run_id": "just_started", "display": "dra review x.pdf --run-id "
                                                       "just_started", "args": [], "document_name": "x.pdf"}),
                                           encoding="utf-8")
    proc = _AliveProc()
    state.launcher.runs["just_started"] = Launched("just_started", proc, "dra review x.pdf --run-id just_started",
                                                   "now")
    pg.goto(base + "/?run=just_started")
    pg.wait_for_selector("#status-feed")
    assert pg.locator("#status-feed .row").count() == 0
    assert pg.locator(".notice", has_text="no progress.jsonl").count() == 0
    assert pg.locator("#top-action button", has_text="Stop run").count() == 1
    lines = (FIXTURES / "progress.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
    (rd / "progress.jsonl").write_text("".join(lines[:40]), encoding="utf-8")
    pg.wait_for_function("document.querySelectorAll('#status-feed .row').length > 0")
    pg.wait_for_function(f"document.querySelectorAll('#status-feed .row').length === "
                         f"{sum(1 for ln in lines[:40] if json.loads(ln)['console'])}")
    assert pg.locator("#finished-bar").is_hidden()
    (rd / "progress.jsonl").write_text("".join(lines), encoding="utf-8")
    proc.code = 0
    pg.wait_for_function("!document.querySelector('#finished-bar').hidden")
    assert pg.locator("#status-feed .row").count() == sum(1 for ln in lines if json.loads(ln)["console"])


def test_stop_takes_two_clicks_and_states_what_the_signal_does(page) -> None:
    """Next to Stop, one sentence from the code: the signal, exit 130, state.json kept, no report, the exact
    resume command. The first click arms the button (Confirm stop, Keep running), only the second posts."""
    from sit_review_agent.errors import ExitCode
    from sit_review_agent.ui.launcher import Launched

    pg, base, runs, state = page
    rd = runs / "to_stop"
    (rd / "ui").mkdir(parents=True)
    display = "dra review x.pdf --run-id to_stop"
    (rd / "ui" / "launch.json").write_text(json.dumps({"run_id": "to_stop", "display": display, "args": [],
                                                       "document_name": "x.pdf"}), encoding="utf-8")
    proc = _AliveProc()
    state.launcher.runs["to_stop"] = Launched("to_stop", proc, display, "now")
    posts: list[str] = []
    pg.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    pg.goto(base + "/?run=to_stop")
    pg.wait_for_selector("#stop-btn")
    note = pg.locator("#stop-note").inner_text()
    assert note == ("Stop sends SIGINT to the dra review process, as Ctrl-C in its terminal does: the run ends with "
                    f"exit {int(ExitCode.SIGINT)}, the state of the last completed phase is kept in state.json, no "
                    "report is written, and dra resume to_stop continues it from there.")
    assert int(ExitCode.SIGINT) == 130
    assert pg.locator("#stop-btn").inner_text() == "Stop run" and pg.locator("#stop-keep").is_hidden()
    pg.click("#stop-btn")                                       # arms only
    pg.wait_for_function("document.getElementById('stop-btn').textContent === 'Confirm stop'"
                         " && !document.getElementById('stop-keep').hidden")
    assert pg.locator("#stop-btn").inner_text() == "Confirm stop" and pg.locator("#stop-keep").is_visible()
    assert posts == [] and proc.code is None
    pg.click("#stop-keep")                                      # disarms
    pg.wait_for_function("document.getElementById('stop-btn').textContent === 'Stop run'"
                         " && document.getElementById('stop-keep').hidden")
    assert pg.locator("#stop-btn").inner_text() == "Stop run" and pg.locator("#stop-keep").is_hidden()
    assert posts == []
    pg.click("#stop-btn")
    pg.click("#stop-btn")                                       # the second click sends the signal
    # The signal ends the process (the fake exits 130 on it), so the stream ends and the Stop control goes with
    # the running state; the button reads SIGINT sent until then.
    pg.wait_for_function("document.querySelector('#stop-btn') === null || "
                         "document.querySelector('#stop-btn').textContent === 'SIGINT sent'")
    assert posts == [base + "/runs/to_stop/stop"] and proc.code == 130
    pg.wait_for_function("!document.querySelector('#finished-bar').hidden")
    assert pg.locator("#finished-bar").inner_text() == "The process exited with code 130 before a run_finished event."
    assert pg.locator("#stop-btn").count() == 0


def _mmss(s: float) -> str:
    t = int(s)
    return f"{t // 60:02d}:{t % 60:02d}"


def test_the_head_clock_ticks_only_the_seconds_since_the_last_event_and_stops_with_the_stream(page) -> None:
    """While the run is live the big clock is the record's last clock plus the seconds since that event arrived,
    the record's clock is shown beside it unchanged, and the axis cursor is live; once the stream ends the clock is
    the record's last clock exactly and nothing ticks."""
    from sit_review_agent.ui.launcher import Launched

    pg, base, runs, state = page
    rd = runs / "ticking"
    (rd / "ui").mkdir(parents=True)
    display = "dra review x.pdf --run-id ticking"
    (rd / "ui" / "launch.json").write_text(json.dumps({"run_id": "ticking", "display": display, "args": [],
                                                       "document_name": "x.pdf"}), encoding="utf-8")
    proc = _AliveProc()
    state.launcher.runs["ticking"] = Launched("ticking", proc, display, "now")
    lines = (FIXTURES / "progress.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
    head = [json.loads(ln) for ln in lines[:40]]
    (rd / "progress.jsonl").write_text("".join(lines[:40]), encoding="utf-8")
    pg.goto(base + "/?run=ticking")
    shown = sum(1 for e in head if e["console"])
    pg.wait_for_function(f"document.querySelectorAll('#status-feed .row').length === {shown}")
    last = max(e["run_s"] for e in head if e["run_s"] is not None)
    assert pg.locator("#clock-last").inner_text() == _mmss(last)
    assert pg.locator("#clock-label").inner_text().startswith("run clock: last event at ")
    first = pg.locator("#top-meta .t b").inner_text()
    assert last <= int(first[:2]) * 60 + int(first[3:]) <= last + 10
    pg.wait_for_function(f"document.querySelector('#top-meta .t b').textContent !== {first!r}", timeout=5000)
    later = pg.locator("#top-meta .t b").inner_text()
    assert int(later[:2]) * 60 + int(later[3:]) > int(first[:2]) * 60 + int(first[3:])
    assert pg.locator("#clock-last").inner_text() == _mmss(last)             # the record's clock did not move
    assert pg.locator("#axis-line .cursor.live").count() == 1
    deadline = next(e["fields"]["deadline_s"] for e in head if e["type"] == "run_started")
    lim = next(e["fields"]["stage_limits_s"] for e in head if e["type"] == "run_started")
    assert pg.locator("#axis-labels .lbl").all_inner_texts() == [f"stage 1 ends {_mmss(lim['stage_1_end'])}",
                                                                  f"refine ends {_mmss(lim['refine_end'])}",
                                                                  f"verdict ends {_mmss(lim['verdict_end'])}",
                                                                  f"deadline {_mmss(deadline)}"]
    assert "the markers are the record's limits" in pg.locator("#axis-note").inner_text()
    (rd / "progress.jsonl").write_text("".join(lines), encoding="utf-8")
    proc.code = 0
    pg.wait_for_function("!document.querySelector('#finished-bar').hidden")
    evs = [json.loads(ln) for ln in lines]
    end = max(e["run_s"] for e in evs if e["run_s"] is not None)
    assert pg.locator("#top-meta .t b").inner_text() == _mmss(end)
    assert pg.locator("#clock-label").inner_text() == "run clock, as of the last event"
    assert pg.locator("#axis-line .cursor.live").count() == 0
    assert pg.locator("#axis-note").inner_text() == f"ended at {_mmss(end)} of {_mmss(deadline)}"
    assert pg.evaluate("SIT.state.tick") is None


def wait_calls_open(pg, key: str) -> None:
    """Wait until the row ``key`` is open on its calls: its name button's click repaints the run with the row's
    button expanded and its calls block under it in one task, so once this holds the block can be read; reading
    right after the click raced that repaint under load."""
    pg.wait_for_function("(k) => { const b = document.querySelector('.track[data-track=\"' + k + '\"] .name-btn');"
                         " return b !== null && b.getAttribute('aria-expanded') === 'true'"
                         " && document.querySelector('.calls[data-track=\"' + k + '\"]') !== null; }", arg=key)


def _record(seq: int, prev: dict[str, Any], type_: str, phase: str, kind: str, fields: dict[str, Any]) -> str:
    """One progress.jsonl line in the schema shape, a second after ``prev`` on both clocks."""
    return json.dumps({"v": 1, "seq": seq, "t": prev["t"] + 1, "run_s": (prev["run_s"] or 0) + 1, "type": type_,
                       "phase": phase, "kind": kind, "console": True, "message": type_, "fields": fields}) + "\n"


def test_a_stage_row_expands_to_its_calls_with_the_latest_status_and_the_drafts_so_far(page) -> None:
    """Change C: each track row opens its stage panel with its model calls (keyed by call_id), the latest call_status
    fields (reasoning tokens, items, chars) and, while the stage's file is not written, the draft items streamed from
    it (severity, kind, title); the panel survives the repaint on the next event; a finished call reads closed at its
    record time. One stage is open at a time (5 Oct 2026: the panel beside the rows)."""
    from sit_review_agent.ui.launcher import Launched

    pg, base, runs, state = page
    rd = runs / "calls"
    (rd / "ui").mkdir(parents=True)
    display = "dra review x.pdf --run-id calls"
    (rd / "ui" / "launch.json").write_text(json.dumps({"run_id": "calls", "display": display, "args": [],
                                                       "document_name": "x.pdf"}), encoding="utf-8")
    proc = _AliveProc()
    state.launcher.runs["calls"] = Launched("calls", proc, display, "now")
    lines = (FIXTURES / "progress.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)[:40]
    head = [json.loads(ln) for ln in lines]
    opened = {e["fields"]["call_id"]: e for e in head if e["type"] == "call_opened"}
    closed = {e["fields"]["call_id"]: e for e in head if e["type"] in ("call_closed", "call_cut")}
    live = next(e for cid, e in opened.items() if cid not in closed and e["fields"]["shard"])
    cid, shard, shards = live["fields"]["call_id"], live["fields"]["shard"], len(head[0]["fields"]["shards"])
    key = f"assess {shard}/{shards}"
    status = {"call_id": cid, "phase": "assess", "label": "", "thinking_tokens": 1234, "items": 2, "chars": 5678}
    lines.append(_record(41, head[-1], "call_status", "stage_1", "wait", {"calls": [status]}))
    tick = json.loads(lines[-1])
    draft = {"list": "findings", "index": 1, "call_id": cid, "shard": shard, "id": "FND-001", "severity": "high",
             "kind": "risk", "title": "A drafted title"}
    lines.append(_record(42, tick, "draft_item", "assess", "draft", draft))
    (rd / "progress.jsonl").write_text("".join(lines), encoding="utf-8")
    pg.goto(base + "/?run=calls")
    pg.wait_for_function("document.querySelectorAll('#drafts .draft').length >= 1")
    row = pg.locator(f'.track[data-track="{key}"]')
    assert row.locator(".name-btn").get_attribute("aria-expanded") == "false"
    assert row.locator(".name-btn").get_attribute("data-calls") == "1"
    assert pg.locator(f'.calls[data-track="{key}"]').count() == 0
    row.locator(".name-btn").click()
    wait_calls_open(pg, key)
    calls = pg.locator(f'.calls[data-track="{key}"] .callrow')
    assert calls.count() == 1
    assert calls.first.get_attribute("data-call") == cid and calls.first.get_attribute("data-status") == "running"
    assert calls.first.locator(".cid").inner_text() == cid
    assert calls.first.locator(".about").inner_text() == f"assess · opened {_mmss(live['run_s'])}"
    assert calls.first.locator(".pill").inner_text() == "running"
    assert calls.first.locator(".cstatus").inner_text() == ("thinking ~1,234 tokens · 2 items · 5,678 chars · as of "
                                                            + _mmss(tick["run_s"]))
    drafts = pg.locator(f'.calls[data-track="{key}"] .cdraft')
    assert drafts.count() == 1
    assert drafts.first.locator(".pill").inner_text() == "high" and drafts.first.locator(".kind").inner_text() == "risk"
    assert drafts.first.locator(".text").inner_text() == "A drafted title"
    assert pg.locator(".calls .cdraft .text").all_inner_texts() == ["A drafted title"]     # titles only, no model text
    # The row stays open through the repaint of the next event, and the new status replaces the old one.
    status2 = dict(status, thinking_tokens=2000, items=3, chars=9000)
    with (rd / "progress.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(_record(43, json.loads(lines[-1]), "call_status", "stage_1", "wait", {"calls": [status2]}))
    sel = f".calls[data-track='{key}'] .cstatus"
    pg.wait_for_function(f"document.querySelector(\"{sel}\").textContent.startsWith('thinking ~2,000')")
    assert pg.locator(f'.track[data-track="{key}"] .name-btn').get_attribute("aria-expanded") == "true"
    assert pg.locator(sel).inner_text().startswith("thinking ~2,000 tokens · 3 items · 9,000 chars")
    # A finished call: closed at its record time, no status line invented for it.
    done_cid, done_ev = next((cid, e) for cid, e in closed.items() if opened[cid]["phase"] == "understand")
    pg.locator('.track[data-track="understand"] .name-btn').click()
    wait_calls_open(pg, "understand")
    done = pg.locator('.calls[data-track="understand"] .callrow')
    assert done.count() == 1 and done.first.get_attribute("data-call") == done_cid
    assert done.first.locator(".pill").inner_text() == f"closed at {_mmss(done_ev['run_s'])}"
    assert done.first.locator(".cstatus").inner_text() == ""
    # One stage at a time: understand replaced the shard in the panel, and the shard's row is closed again.
    assert pg.locator(".calls").count() == 1 and pg.locator(".calls .cdraft").count() == 0
    assert pg.locator(f'.track[data-track="{key}"] .name-btn').get_attribute("aria-expanded") == "false"


def test_a_fired_limit_is_stated_in_plain_words(page) -> None:
    pg, base, runs, _state = page
    evs = records(runs / "progress_cut" / "progress.jsonl")
    cut = next(r["fields"] for r in evs if r["type"] == "shard_cut")
    lim = next(r["fields"]["stage_limits_s"] for r in evs if r["type"] == "run_started")
    open_run(pg, base, "progress_cut")
    notes = pg.locator("#limit-notes .limit-note")
    assert notes.count() == 1
    assert notes.first.inner_text().split("\n") == [
        _mmss(next(r["run_s"] for r in evs if r["type"] == "shard_cut")),
        f"Stage 1 limit {_mmss(lim['stage_1_end'])} reached; assess shard {cut['shard']} (requirements and "
        f"consistency) ended there at {_mmss(cut['cut_at_s'])}, {cut['kept']} draft(s) kept; not assessed: "
        + ", ".join(cut["criteria_not_assessed"]) + "."]
    assert pg.locator("#limit-notes .limit-note").count() == 1
    assert pg.locator("#run-axis").is_visible() and pg.locator("#axis-line .mark").count() == 4


# ------------------------------------------------------------------ a cut shard, a resumed run


def test_the_cut_shard_shows_its_disclosure_id_and_what_it_kept(page) -> None:
    pg, base, runs, _state = page
    evs = records(runs / "progress_cut" / "progress.jsonl")
    cut = next(r["fields"] for r in evs if r["type"] == "shard_cut")
    open_run(pg, base, "progress_cut")
    t = tracks(pg)
    key = f"assess {cut['shard']}/{cut['shards']}"
    assert t[key][0] == "cut"
    assert f"{cut['degradation_id']} in the report" in t[key][1]
    assert f"kept {cut['kept']} finished finding(s)" in t[key][1]
    assert all(c in t[key][1] for c in cut["criteria_not_assessed"])
    pill = pg.locator(f'.track[data-track="{key}"] .pill').inner_text()
    at = int(cut["cut_at_s"])
    assert pill == f"cut at {at // 60:02d}:{at % 60:02d}"
    assert [k for k, v in t.items() if v[0] == "cut"] == [key]
    kept = [d["title"] for d in cut["kept_drafts"]]
    titles = pg.locator("#drafts .draft .text").all_inner_texts()
    assert all(k in titles for k in kept)
    drafted = sum(r["fields"]["findings"] for r in evs if r["type"] == "shard_drafted")
    assert len(titles) == drafted + len(kept)


def test_a_resumed_run_continues_on_the_page_with_one_sequence(page) -> None:
    pg, base, runs, _state = page
    evs = records(runs / "progress_resume" / "progress.jsonl")
    open_run(pg, base, "progress_resume")
    t = tracks(pg)
    assert t["understand"][0] == "done" and t["report"][0] == "done"     # the failed phase ran again after the resume
    assert pg.locator("#top-meta .pill", has_text="resumed").count() == 1
    assert pg.locator("#status-feed .row").count() == sum(1 for r in evs if r["console"])
    finished = [r for r in evs if r["type"] == "run_finished"]
    assert [f["fields"]["exit_code"] for f in finished] == [3, 0]
    assert pg.locator("#finished-bar").inner_text().startswith("Run finished: completed")
    # The server streams both halves under one sequence.
    sse = pg.evaluate("async (u) => { const r = await fetch(u); return await r.text(); }",
                      base + "/runs/progress_resume/events")
    ids = [int(ln[4:]) for ln in sse.splitlines() if ln.startswith("id: ")]
    assert ids == list(range(1, len(evs) + 1)) and "event: end" in sse


# ------------------------------------------------------------------ the rail's Logs panel


LOG_BOXES = """() => { const l = document.getElementById('rail-log'), slot = document.getElementById('navrail-slot');
  const top = l.getBoundingClientRect().top + l.clientTop, bottom = top + l.clientHeight;
  const s = slot.getBoundingClientRect();
  const vis = [...l.querySelectorAll('.rail-logline')].map(e => e.getBoundingClientRect())
    .filter(r => r.bottom > top && r.top < bottom);
  return {top, bottom, slot: [s.top, s.bottom], scrolled: l.scrollTop, lines: vis.map(r => [r.top, r.bottom])}; }"""


def test_the_logs_panel_shows_whole_lines_at_the_newest_and_at_the_top(page) -> None:
    """The Logs panel follows progress.log to its newest line. Its first visible line used to sit half
    above the panel's content top (the box was not a whole number of lines tall, so scrolling to the
    bottom left the remainder at the top). Every visible line is now whole, followed and scrolled up."""
    pg, base, runs, _state = page
    (runs / "progress" / "progress.log").write_text(
        "".join(f"[00:{i:02d}] assess     | OK line {i}\n" for i in range(60)), encoding="utf-8")
    for width, height in ((1440, 900), (1280, 720)):
        pg.set_viewport_size({"width": width, "height": height})
        open_run(pg, base, "progress")
        pg.wait_for_function("document.querySelectorAll('#rail-log .rail-logline').length === 60")
        pg.evaluate("document.querySelector('.rail-log-frame').scrollIntoView({block: 'nearest'})")
        for where in ("followed", "top"):
            if where == "top":
                pg.evaluate("document.getElementById('rail-log').scrollTop = 0")
            m = pg.evaluate(LOG_BOXES)
            assert len(m["lines"]) >= 3, (width, where, m)
            assert m["lines"][0][0] >= m["top"], (width, where, m)       # the first visible line is not cut at the top
            assert m["lines"][-1][1] <= m["bottom"], (width, where, m)   # nor the last at the bottom
            # and the rail shows the whole panel, scrolled into view where the rail is short
            assert m["slot"][0] <= m["top"] and m["bottom"] <= m["slot"][1], (width, where, m)
        assert pg.locator("#rail-log .rail-logline").last.text_content() == "[00:59] assess     | OK line 59"


RUN_ROW_BOXES = """() => { const row = document.querySelector('#rail-runs .rail-run.active');
  const list = document.getElementById('rail-runs').getBoundingClientRect();
  const s = document.getElementById('navrail-slot').getBoundingClientRect(), r = row.getBoundingClientRect();
  return {row: [r.top, r.bottom], list: [list.top, list.bottom], slot: [s.top, s.bottom]}; }"""


def test_the_open_runs_row_stays_in_view_beside_the_logs_panel(page) -> None:
    """The Runs list gave way first to the Logs panel and collapsed to 0 px at 1440x900: the header showed
    with no row, so the reader could not see which run was open. The list now keeps one whole row and
    scrolls itself to the open run's row; the Logs panel keeps its 3 whole lines, both in the default view."""
    pg, base, runs, state = page
    state.tools[:] = [{"name": f"server-{i}", "enabled": True} for i in range(4)]   # four, as config/tools.yaml
    for run in runs.iterdir():   # every run has a log first: writing one moves its run up the list
        (run / "progress.log").write_text(
            "".join(f"[00:{i:02d}] assess     | OK line {i}\n" for i in range(60)), encoding="utf-8")
    pg.goto(base + "/")
    pg.wait_for_function("document.querySelectorAll('#rail-runs .rail-run').length >= 2 && "
                         "document.querySelectorAll('#rail-tools .rail-tool').length === 4")
    last = pg.locator("#rail-runs .rail-run").last.get_attribute("data-run")   # the row furthest down the list
    pg.goto(base + f"/?run={last}")
    pg.wait_for_function(f"document.querySelector('#rail-runs .rail-run.active').dataset.run === {last!r}")
    pg.wait_for_function("document.querySelectorAll('#rail-log .rail-logline').length === 60")
    # the default view at 1440x900 holds both, with no scroll of the rail: the open run's row ...
    m = pg.evaluate(RUN_ROW_BOXES)
    assert m["list"][0] <= m["row"][0] and m["row"][1] <= m["list"][1], m   # whole inside the list
    assert m["slot"][0] <= m["row"][0] and m["row"][1] <= m["slot"][1], m   # and inside the rail
    assert pg.evaluate("(s => s.scrollHeight <= s.clientHeight)(document.getElementById('navrail-slot'))")
    # ... and at least 3 whole lines of the Logs panel
    m = pg.evaluate(LOG_BOXES)
    assert len(m["lines"]) >= 3, m
    assert m["lines"][0][0] >= m["top"] and m["lines"][-1][1] <= m["bottom"], m
    assert m["slot"][0] <= m["top"] and m["bottom"] <= m["slot"][1], m


# ------------------------------------------------------------------ 5 Oct 2026: the Review form, an early exit


def test_the_deadline_field_and_a_missing_key_on_the_review_form(page, monkeypatch) -> None:
    """The deadline is set in minutes, starts at the profile's own and reaches the shown command as
    ``--deadline <s>`` only when changed; with tools on and SIT_MCP_API_KEY unset, the form says so beside the
    Tools control with the export hint and Start stays off until Document only is ticked."""
    from sit_review_agent.config import ConfigOverrides, load_config

    monkeypatch.delenv("SIT_MCP_API_KEY", raising=False)
    pg, base, _runs, state = page
    sr = load_config(None, ConfigOverrides(profile="demo")).stop_rules
    state.profiles = [{"name": "demo", "label": "demo", "deadline_s": sr.deadline_seconds,
                       "stage_limits_s": sr.stage_limits_s.as_dict(), "effort": "medium"}]
    state.stop_rules = {"demo": sr}
    state.tools = [{"name": "mcp-internet-search", "enabled": True}]
    pg.goto(base + "/")
    pg.wait_for_selector("#deadline-min")
    pg.wait_for_function("document.getElementById('profile-help').textContent.startsWith('Stage 1 ends by 07:21')")
    assert pg.input_value("#deadline-min") == "15"
    assert "--deadline" not in pg.locator("#cmd-preview").inner_text()
    warn = pg.locator("#key-warn")
    assert warn.is_visible() and "SIT_MCP_API_KEY is not set" in warn.inner_text()
    assert "export SIT_MCP_API_KEY=<key>" in warn.inner_text()
    pg.set_input_files("#doc-input", files=[{"name": "d.pdf", "mimeType": "application/pdf", "buffer": b"%PDF"}])
    assert pg.locator("#start-btn").is_disabled()
    pg.check("#no-tools")
    assert warn.is_hidden() and pg.locator("#start-btn").is_enabled()
    pg.fill("#deadline-min", "9")
    assert "--profile demo --deadline 540 --no-tools" in pg.locator("#cmd-preview").inner_text()
    pg.wait_for_function("document.getElementById('profile-help').textContent.includes('Research ends by 04:24.')")
    help_text = pg.locator("#profile-help").inner_text()
    assert help_text.startswith("Stage 1 ends by 04:24, refine by 07:45, verdict by 08:49")
    assert "with the reserves (75 s for verify and verdict, 200 s for refine)" in help_text   # USER_DECISIONS #48
    pg.fill("#deadline-min", "1")
    assert pg.locator("#start-btn").is_disabled() and "from 2 to 120" in pg.locator("#deadline-help").inner_text()
    pg.fill("#deadline-min", "15")
    assert "--deadline" not in pg.locator("#cmd-preview").inner_text() and pg.locator("#start-btn").is_enabled()
    # at the profile's own deadline the form still says when research ends (it asks the server with no --deadline)
    eff = sr.effective()
    end = eff.research_end_s()
    want = f"Research ends by {int(end) // 60:02d}:{int(end) % 60:02d}."
    pg.wait_for_function("w => document.getElementById('profile-help').textContent.includes(w)", arg=want)
    assert pg.locator("#profile-help").inner_text().startswith("Stage 1 ends by 07:21")
    assert "Scaled from the profile's" not in pg.locator("#profile-help").inner_text()
    pg.fill("#deadline-min", "")
    pg.wait_for_function("w => document.getElementById('profile-help').textContent.includes(w)", arg=want)


def test_a_run_that_died_before_its_first_event_shows_what_it_printed(page) -> None:
    """The owner saw only "it's not running" for ui-261005-125221-0958: the process exited 2 with a clear
    message in ui/console.txt and no event. The run view shows that message, no empty timeline."""
    pg, base, runs, _state = page
    rd = runs / "died"
    (rd / "ui").mkdir(parents=True)
    (rd / "ui" / "launch.json").write_text(json.dumps({"run_id": "died", "display": "dra review x.pdf --run-id died",
                                                       "args": [], "document_name": "x.pdf"}), encoding="utf-8")
    msg = "error: SIT_MCP_API_KEY is not set ... or pass --no-tools for a document-only review. No model call was made"
    (rd / "ui" / "console.txt").write_text(msg + "\n", encoding="utf-8")
    pg.goto(base + "/?run=died")
    pg.wait_for_selector("#run-console")
    assert pg.locator("#run-console .console-text").inner_text() == msg
    assert "The process ended before its first event." in pg.locator("#run-console .console-head").inner_text()
    assert "runs/died/ui/console.txt" in pg.locator("#run-console").inner_text()
    assert pg.locator(".run-wrap").is_hidden() and pg.locator("#top-meta").is_hidden()
    assert pg.locator(".notice", has_text="no progress.jsonl").count() == 0
