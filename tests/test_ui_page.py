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
    # report text (finding_refs.py) may change those text fields and nothing else.
    assert out.report_md is not None and not out.message.startswith("replay failed"), out.message
    assert all(re.fullmatch(r"\$\.(findings|sound_areas)\[\d+\]\.(statement|why_sound)", d)
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
    assert all(t[k][0] == "done" for k in ("ingest", "understand", "plan", "research", "refine", "verify", "report"))
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
