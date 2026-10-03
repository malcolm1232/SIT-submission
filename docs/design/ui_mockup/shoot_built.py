"""Screenshot the built page (``dra ui``) in its three states at 1440 px wide, then stack them.

    .venv/bin/python docs/design/ui_mockup/shoot_built.py

Writes ``built_1_drop.png``, ``built_2_running.png``, ``built_3_review.png`` and
``for_him_ui_built.png`` beside this file. Needs the ``playwright`` package with its Chromium.

Data, all offline: a scratch runs directory holding the recorded fixture stream
``tests/fixtures/ui/progress.jsonl`` (a fixture run on the fake gateway, ``tests/fixtures/ui/record_fixtures.py``)
cut at the run clock 01:00 (frame 2, served over SSE as a run still in progress) and the report files
of ``docs/live_runs/rehearsal_concurrent_1`` (frames 1 and 3). No model call is made and no run is started. Before each picture the script checks the page
against the run directory and prints counts only: the findings' titles and statements in the DOM
equal ``report.json``, and the draft rows equal the fixture's draft events.
"""

from __future__ import annotations

import json
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
REHEARSAL = REPO / "docs" / "live_runs" / "rehearsal_concurrent_1"
FIXTURE = REPO / "tests" / "fixtures" / "ui" / "progress.jsonl"
RUN_FILES = ("report.json", "manifest.json", "anchors.json", "ledger.json", "state.json", "effective_config.json")
RUNNING_UNTIL_T = 60.0    # run-clock seconds: stage 1 of the fixture run is still open at 01:00
EXPAND = "FND-005"        # the finding frame 3 of the mockup shows expanded


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def scratch_runs(root: Path) -> None:
    reh = root / REHEARSAL.name
    reh.mkdir()
    for name in RUN_FILES:
        shutil.copy2(REHEARSAL / name, reh / name)
    fx = root / "fixture_run"
    fx.mkdir()
    lines = [ln for ln in FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
             if (json.loads(ln)["run_s"] or 0.0) <= RUNNING_UNTIL_T]
    (fx / "progress.jsonl").write_text("".join(lines), encoding="utf-8")


def start_server(runs: Path, port: int):
    import uvicorn

    from sit_review_agent.config import load_config
    from sit_review_agent.ui.launcher import Launcher
    from sit_review_agent.ui.server import UIState, _git_commit, _profiles, build_app

    class NoLaunch:
        def __call__(self, *a, **k):
            raise RuntimeError("the screenshot script starts no run")

    class NoChat:
        async def ask(self, **kw):
            raise RuntimeError("the screenshot script makes no model call")

    cfg = load_config(None)
    state = UIState(runs_dir=runs.resolve(), repo_root=REPO, launcher=Launcher(repo_root=REPO, popen=NoLaunch()),
                    chat_client=NoChat(), profiles=_profiles(None),
                    tools=[{"name": s.name, "enabled": s.enabled} for s in cfg.tools.servers], commit=_git_commit(REPO))
    server = uvicorn.Server(uvicorn.Config(build_app(state), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(200):
        if server.started:
            return server, th
        time.sleep(0.05)
    raise RuntimeError("server did not start")


def check_review(page, report: dict) -> list[str]:
    problems = []
    rows = page.locator(".frow")
    titles = {r.get_attribute("data-fid"): r.locator(".title").inner_text() for r in rows.all()}
    for f in report["findings"]:
        if titles.get(f["id"]) != f["title"]:
            problems.append(f"{f['id']}: title differs")
    st = page.locator(f'.frow[data-fid="{EXPAND}"] + .expanded .statement').inner_text()
    want = next(f["statement"] for f in report["findings"] if f["id"] == EXPAND)
    if st != want:
        problems.append(f"{EXPAND}: statement differs")
    if page.locator("#chat-label").inner_text() != "reading aid, not the review":
        problems.append("chat label missing")
    print(f"review: {len(titles)} finding rows, {len(report['findings'])} in report.json, problems {len(problems)}")
    return problems


def main() -> int:
    port = free_port()
    report = json.loads((REHEARSAL / "report.json").read_text(encoding="utf-8"))
    out = {"drop": HERE / "built_1_drop.png", "running": HERE / "built_2_running.png",
           "review": HERE / "built_3_review.png"}
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        runs.mkdir()
        scratch_runs(runs)
        server, th = start_server(runs, port)
        base = f"http://127.0.0.1:{port}"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
                page.goto(base + "/")
                page.wait_for_selector("#runs-table tbody tr")
                page.screenshot(path=str(out["drop"]), full_page=True)

                evs = [json.loads(ln) for ln in (runs / "fixture_run" / "progress.jsonl").read_text().splitlines()]
                drafts = sum(len(e["fields"]["drafts"]) for e in evs if e["type"] == "shard_drafted") \
                    + sum(1 for e in evs if e["type"] == "draft_item" and e["fields"].get("list") == "findings")
                page.goto(base + "/?run=fixture_run")
                page.wait_for_function(f"document.querySelectorAll('#drafts .draft').length === {drafts}")
                page.wait_for_timeout(300)
                shown = page.locator("#drafts .draft").count()
                print(f"running: {shown} draft rows, {drafts} draft events")
                if shown != drafts:
                    problems.append("draft rows differ from the stream")
                page.screenshot(path=str(out["running"]), full_page=True)

                page.goto(base + f"/?run={REHEARSAL.name}")
                page.wait_for_selector(f'.frow[data-fid="{EXPAND}"]')
                page.click(f'.frow[data-fid="{EXPAND}"]')
                page.wait_for_selector(".expanded")
                problems += check_review(page, report)
                page.evaluate("window.scrollTo(0, 0)")
                page.screenshot(path=str(out["review"]), full_page=True)

                frames = "".join(
                    f'<p class="cap"><b>{i}</b> {cap}</p><img src="{path.as_uri()}">'
                    for i, (cap, path) in enumerate([
                        ("Drop screen, built (dra ui), with the recent runs read from the run directories.", out["drop"]),
                        ("A run in progress: the fixture stream replayed over SSE, cut at the run clock 02:38.",
                         out["running"]),
                        (f"The finished review of {REHEARSAL.name} with {EXPAND} expanded, and the chat panel.",
                         out["review"])], 1))
                comp = Path(tmp) / "composite.html"
                comp.write_text(
                    "<!doctype html><meta charset='utf-8'><style>body{margin:0;padding:24px 0 32px;width:1440px;"
                    "background:#f0f0f0;font:13px -apple-system,system-ui,sans-serif;color:#646464}"
                    ".cap{padding:0 32px;margin:0 0 8px}.cap b{color:#202020}img{display:block;width:1440px;"
                    "margin:0 0 32px;border-top:1px solid #d9d9d9;border-bottom:1px solid #d9d9d9}</style>" + frames,
                    encoding="utf-8")
                page.goto(comp.as_uri())
                page.wait_for_load_state("load")
                page.screenshot(path=str(HERE / "for_him_ui_built.png"), full_page=True)
                browser.close()
        finally:
            server.should_exit = True
            th.join(timeout=5)
    for p_ in [*out.values(), HERE / "for_him_ui_built.png"]:
        print(p_)
    print(f"problems: {len(problems)}")
    for pr in problems:
        print(f"  {pr}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
