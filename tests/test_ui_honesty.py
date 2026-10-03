"""Honesty and anti-slop guards of the review page (docs/design/ui_design.md sections 4 and 10;
research_anti_slop_craft.md 1.3, 4.3, 8). Static checks on the shipped files, and one real-browser
check (skipped where Playwright or its Chromium is not installed) that drives the page against the
fixture stream and the rehearsal run directory."""

from __future__ import annotations

import json
import re
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest

from sit_review_agent.ui import chat
from sit_review_agent.ui.launcher import Launcher
from sit_review_agent.ui.server import STATIC_DIR, UIState, build_app

REPO = Path(__file__).resolve().parents[1]
REHEARSAL = REPO / "docs" / "live_runs" / "rehearsal_concurrent_1"
SAMPLE = REPO / "docs" / "live_runs" / "sit_sample_tools_1"
FIXTURE_EVENTS = Path(__file__).parent / "fixtures" / "ui" / "progress.jsonl"
SERVERS = [{"name": "mcp-internet-search", "enabled": True}, {"name": "mcp-research-information", "enabled": True},
           {"name": "mcp-browser-automation-pw", "enabled": False},
           {"name": "mcp-document-intelligence", "enabled": False}]
HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
JS = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
CSS = (STATIC_DIR / "app.css").read_text(encoding="utf-8")
TOKENS = (STATIC_DIR / "tokens.css").read_text(encoding="utf-8")

#: Numeric literals app.js may hold. None is shown as a value: each formats or slices one.
JS_NUMBERS = {
    "0": "empty checks, clock floor",
    "1": "singular forms",
    "2": "two-digit padding and fixed decimals",
    "7": "length of 'assess ' when sorting shard rows; the short commit hash",
    "10": "parseInt radix",
    "11": "start of hh:mm in an ISO time",
    "16": "end of hh:mm in an ISO time",
    "60": "seconds per minute",
    "100": "percent for the bar width",
}


def _code_only(js: str) -> str:
    js = re.sub(r"//[^\n]*", "", js)
    return re.sub(r'style: "[^"]*"', 'style: ""', js)


def _visible_text(html: str) -> str:
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    html = re.sub(r"<(svg|style|script)\b.*?</\1>", "", html, flags=re.S)
    html = re.sub(r"<head>.*?</head>", "", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


# ------------------------------------------------------------------ no element claims progress it cannot know


def test_no_fake_progress_or_completion_estimate() -> None:
    text = (HTML + JS).lower()
    for claim in ("<progress", "eta", "time remaining", "% complete", "almost done", "estimated completion",
                  "spinner", "indeterminate"):
        assert not re.search(rf"(?<![a-z]){re.escape(claim)}(?![a-z])", text), claim
    assert "It is not an estimate of completion." in HTML
    assert "Times are as of the last event received." in HTML


def test_the_bar_is_elapsed_over_the_limit_and_nothing_else() -> None:
    widths = re.findall(r'style: "width:" \+ (.*?)\.toFixed', JS)
    assert widths == ["Math.min(100, (100 * pos) / limit)"]
    # pos is the event clock (the track's end, or the last event's t), never the browser clock.
    assert "const pos = t.status === \"waiting\" ? null : (t.end ?? m.lastT);" in JS
    for clock_source in ("Date.now", "new Date", "performance.now", "setInterval", "setTimeout"):
        assert clock_source not in JS, clock_source


def test_the_run_view_never_parses_message_text() -> None:
    body = JS.split("function applyEvent", 1)[1].split("\nfunction ", 1)[0]
    assert "message" not in body          # draws from ev.event and ev.fields only
    assert JS.count("ev.message") == 1    # shown verbatim in the status feed, nowhere else


# ------------------------------------------------------------------ every number from the run directory or the stream


def test_the_script_holds_no_number_that_could_be_shown() -> None:
    found = set(re.findall(r"(?<![A-Za-z0-9_.#-])(\d+(?:\.\d+)?)", _code_only(JS)))
    assert found <= set(JS_NUMBERS), sorted(found - set(JS_NUMBERS))


def test_the_page_copy_holds_no_number_but_the_status_contract() -> None:
    text = _visible_text(HTML).replace("Stage 1", "Stage").replace("--v1", "--v")   # names, not values
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    assert numbers == ["10"]               # "a status line at least every 10 s" (design note section 5)


# ------------------------------------------------------------------ the chat is labelled and kept apart


def test_the_chat_panel_is_labelled_a_reading_aid() -> None:
    assert '<span class="pill" id="chat-label">reading aid, not the review</span>' in HTML
    assert chat.LABEL == "reading aid, not the review"
    assert 'aria-label="Ask the review"' in HTML
    review_tpl = HTML.split('<template id="tpl-review">', 1)[1].split("</template>", 1)[0]
    assert review_tpl.index('id="review"') < review_tpl.index('id="chat"')   # its own column, after the review


def test_chat_text_never_enters_the_review_column() -> None:
    for fn in ("reviewBody", "deltaBody", "coverageBody", "evidenceBody", "expanded", "findingList"):
        body = _code_only(JS).split(f"function {fn}(", 1)[1].split("\nfunction ", 1)[0]
        assert not re.search(r"\bturns?\b|chat", body), fn


# ------------------------------------------------------------------ no decorative motion, one token sheet, no network


def test_no_decorative_animation() -> None:
    assert "@keyframes" not in CSS and "animation" not in CSS
    for decl in re.findall(r"transition:\s*([^;]+);", CSS):
        for part in decl.split(","):
            prop, dur = part.split()
            assert prop in ("background-color", "border-color") and dur == "150ms", part
    assert ".animate(" not in JS and "transition" not in JS and "@keyframes" not in HTML


def test_no_colour_outside_the_token_sheet() -> None:
    hexes = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    assert not hexes.findall(CSS) and not hexes.findall(JS)
    assert not hexes.findall(re.sub(r'href="[^"]*"', "", HTML))
    assert not re.search(r"\brgba?\(|\bhsla?\(|\boklch\(", CSS + JS + HTML)
    assert len(hexes.findall(TOKENS)) >= 20


def test_nothing_is_loaded_from_the_network() -> None:
    for text in (HTML, JS, CSS, TOKENS):
        assert "http://" not in text and "https://" not in text and "//cdn" not in text


def test_data_is_inserted_as_text_only() -> None:
    assert "innerHTML" not in JS and "insertAdjacentHTML" not in JS and "document.write" not in JS


# ------------------------------------------------------------------ the page in a browser


#: Running animations other than the 150 ms hover change of a background or border colour.
MOTION = ("document.getAnimations().filter(a => !(a instanceof CSSTransition && "
          "['background-color', 'border-color'].includes(a.transitionProperty))).length")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def served(tmp_path: Path):
    uvicorn = pytest.importorskip("uvicorn")
    runs = tmp_path / "runs"
    reh = runs / REHEARSAL.name
    reh.mkdir(parents=True)
    for name in ("report.json", "manifest.json", "anchors.json", "ledger.json", "state.json", "effective_config.json"):
        shutil.copy2(REHEARSAL / name, reh / name)
    sample = runs / SAMPLE.name                      # a finished run with tool records: the rail's tools source
    sample.mkdir()
    for name in ("report.json", "manifest.json", "anchors.json", "ledger.json", "tools_list.jsonl", "tools.jsonl"):
        shutil.copy2(SAMPLE / name, sample / name)
    fx = runs / "fixture_run"
    fx.mkdir()
    lines = FIXTURE_EVENTS.read_text(encoding="utf-8").splitlines(keepends=True)
    (fx / "progress.jsonl").write_text("".join(lines[:70]), encoding="utf-8")
    probes: list[int] = []

    async def probe() -> dict:
        probes.append(1)
        return {"at": "", "servers": [], "auth_failed": False, "lines": []}

    sample_pdf = REPO / "eval" / "synthetic" / "payments_orchestration" / "design_v1.pdf"
    state = UIState(runs_dir=runs.resolve(), repo_root=REPO, launcher=Launcher(repo_root=REPO), chat_client=None,
                    profiles=[], tools=list(SERVERS), probe=probe,
                    documents=[{"name": "doc-1", "label": "Payments orchestration", "file": "payments_design_v1.pdf",
                                "path": "eval/synthetic/payments_orchestration/design_v1.pdf",
                                "abspath": str(sample_pdf)}])  # type: ignore[arg-type]
    state.probes = probes  # type: ignore[attr-defined]
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


def test_the_page_in_a_browser(served) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    base, runs, _state = served
    report = json.loads((REHEARSAL / "report.json").read_text(encoding="utf-8"))
    evs = [json.loads(ln) for ln in (runs / "fixture_run" / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Chromium not installed here
            pytest.skip(f"Chromium not available: {exc}")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        requests: list[str] = []
        page.on("request", lambda r: requests.append(r.url))

        # The run view: drafts and the clock come from the stream only (a draft is a shard's drafted
        # finding, ``shard_drafted``, or a streamed one, ``draft_item`` of the findings list).
        drafts = [d for e in evs if e["type"] == "shard_drafted" for d in e["fields"]["drafts"]]
        drafts += [e["fields"] for e in evs if e["type"] == "draft_item" and e["fields"].get("list") == "findings"]
        page.goto(base + "/?run=fixture_run")
        page.wait_for_function(f"document.querySelectorAll('#drafts .draft').length === {len(drafts)}")
        page.wait_for_function("document.querySelectorAll('#status-feed .row').length > 0")
        assert page.locator("#draft-count").inner_text() == str(len(drafts))
        titles = [d["title"] for d in reversed(drafts)]
        assert page.locator("#drafts .draft .text").all_inner_texts() == titles
        last = int(max(e["run_s"] for e in evs if e["run_s"] is not None))
        assert page.locator("#top-meta b").first.inner_text() == f"{last // 60:02d}:{last % 60:02d}"
        assert page.locator("#status-feed .row").count() == sum(1 for e in evs if e["console"])
        assert page.locator("#replay-stamp").count() == 0
        assert page.evaluate(MOTION) == 0

        # The review: titles and statements as report.json has them; the counts are list lengths.
        page.goto(base + f"/?run={REHEARSAL.name}")
        page.wait_for_selector(".frow")
        rows = {r.get_attribute("data-fid"): r.locator(".title").inner_text() for r in page.locator(".frow").all()}
        assert rows == {f["id"]: f["title"] for f in report["findings"]}
        for f in report["findings"][:5]:
            page.click(f'.frow[data-fid="{f["id"]}"]')
            got = page.locator(f'.frow[data-fid="{f["id"]}"] + .expanded .statement').inner_text()
            assert got == f["statement"]
            quotes = page.locator(f'.frow[data-fid="{f["id"]}"] + .expanded .quote').all_inner_texts()
            assert quotes == [f"“{a['quote']}”" for a in f["doc_anchors"]]
        counts = page.locator(".counts span").all_inner_texts()
        assert counts[0] == f"{len(report['findings'])} findings"
        assert f"{len(report['unresolved'])} unresolved" in counts
        conf = page.locator(".verdict .conf").inner_text()
        assert conf.startswith(f"confidence {report['verdict']['confidence']:.2f}")
        assert page.locator("#chat-label").inner_text() == "reading aid, not the review"
        assert page.locator("#chat-budget").inner_text().startswith("0 of 20 calls used")
        delta = page.locator(".tab", has_text="Delta")                 # no previous version: Delta is drawn disabled
        assert delta.count() == 1 and delta.is_disabled()
        assert delta.get_attribute("title") == "No previous version was given for this run"
        assert page.locator("#tab-note").inner_text() == "Delta is off: no previous version was given for this run."
        link = page.locator(".expanded a[href*='doc.pdf#page=']").first.get_attribute("href")
        assert re.search(r"/doc\.pdf#page=\d+$", link)
        assert page.evaluate(MOTION) == 0
        browser.close()
    assert all(u.startswith(base) for u in requests), [u for u in requests if not u.startswith(base)]


# ------------------------------------------------------------------ the rail: stream state, recorded servers, no probe


def _mmss(s: float) -> str:
    t = int(s)
    return f"{t // 60:02d}:{t % 60:02d}"


def test_the_rail_shows_the_stream_state_and_the_recorded_servers_and_never_probes(served, monkeypatch) -> None:
    """Three guards of the v2 rail (docs/design/ui_restyle.md section 4): the running entry is the open run's
    reduced stream (stage, run clock, open calls), the tools dots are GET /tools (a read of recorded files),
    and nothing on any page load calls POST /tools/probe; the Probe button is the only path to it."""
    sync_api = pytest.importorskip("playwright.sync_api")
    base, runs, state = served
    monkeypatch.delenv("SIT_MCP_API_KEY", raising=False)
    evs = [json.loads(ln) for ln in (runs / "fixture_run" / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Chromium not installed here
            pytest.skip(f"Chromium not available: {exc}")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        requests: list[tuple[str, str]] = []
        page.on("request", lambda r: requests.append((r.method, r.url)))

        # 1. The running entry equals the SSE state the page reduced from the stream.
        page.goto(base + "/?run=fixture_run")
        page.wait_for_function("document.querySelectorAll('#status-feed .row').length > 0")
        page.wait_for_function("document.querySelector('#rail-runs .rail-run.active .meta .live') !== null")
        last = max(e["run_s"] for e in evs if e["run_s"] is not None)
        deadline = next(e["fields"]["deadline_s"] for e in evs if e["type"] == "run_started")
        opened = {e["fields"]["call_id"]: e["phase"] for e in evs if e["type"] == "call_opened"}
        closed = {e["fields"]["call_id"] for e in evs if e["type"] in ("call_closed", "call_cut")}
        open_calls = [ph for cid, ph in opened.items() if cid not in closed]
        assert open_calls == ["refine"]
        entry = page.locator("#rail-runs .rail-run.active")
        assert entry.get_attribute("data-run") == "fixture_run" and entry.locator(".dot.live").count() == 1
        assert entry.locator(".meta").inner_text() == f"refine · {_mmss(last)} of {_mmss(deadline)} · 1 call open"
        assert entry.locator(".meta .live").inner_text() == "refine"
        assert page.locator("#top-meta b").first.inner_text() == _mmss(last)      # the same clock as the page head
        assert page.locator("#rail-runs-note").text_content() == "1 running"      # uppercase is the CSS caption
        assert page.locator("#rail-runs .rail-run .dot.live").count() == 1

        # 2. The tools dots equal GET /tools, server by server.
        tools = page.evaluate("async () => (await fetch('/tools')).json()")
        assert tools["from_run"] == SAMPLE.name
        assert [s["name"] for s in tools["servers"]] == [s["name"] for s in SERVERS]
        assert [s["warm"] for s in tools["servers"]] == [True, True, None, None]
        for s in tools["servers"]:
            dot = page.locator(f'#rail-tools .rail-tool[data-server="{s["name"]}"] .dot')
            assert dot.count() == 1
            assert ("warm" in dot.get_attribute("class").split()) is bool(s["warm"]), s["name"]
        warm = sum(1 for s in tools["servers"] if s["warm"])
        assert page.locator("#rail-tools-note").text_content() == f"{warm} of {len(SERVERS)} warm"
        assert page.locator("#top-tools b").inner_text() == f"{warm} of {len(SERVERS)}"

        # 3. No page load probes: the Review page, a run, a review and the Tools page send no POST at all.
        page.goto(base + "/")
        page.wait_for_selector(".starter")
        # A chip fills the form with the file and never starts a run (no POST below).
        page.click(".starter")
        page.wait_for_function("document.querySelector('#doc-chosen').textContent === 'payments_design_v1.pdf'")
        assert page.locator("#start-btn").is_enabled()
        assert "review runs/<new run>/ui/input/payments_design_v1.pdf " in page.locator("#cmd-preview").inner_text()
        assert page.locator(".starter").get_attribute("aria-pressed") == "true"
        page.goto(base + f"/?run={REHEARSAL.name}")
        page.wait_for_selector("#chat-budget")
        page.goto(base + "/?page=tools")
        page.wait_for_selector("#probe-btn")
        assert all(m == "GET" for m, _ in requests), [u for m, u in requests if m != "GET"]
        assert not any(u.endswith("/tools/probe") for _, u in requests)
        # The button is the one path to the probe (refused here: no key in this test's environment).
        page.click("#probe-btn")
        page.wait_for_selector("#probe-error:not([hidden])")
        assert [(m, u) for m, u in requests if u.endswith("/tools/probe")] == [("POST", base + "/tools/probe")]
        assert "SIT_MCP_API_KEY is not set" in page.locator("#probe-error").inner_text()
        assert state.probes == []                       # refused before the warm-up: no key, no network
        browser.close()
