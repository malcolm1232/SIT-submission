"""The run's Review tab in ``dra ui`` is the export's review document (5 Oct 2026): the same renderer and linker
(``export.review_fragment``), served as a fragment by ``GET /runs/<id>/review.html`` and run by the export's own
script (``static/xnav.js``), so the tab and the exported page cannot drift apart.

Offline on the committed run ``docs/live_runs/ui_flow_1`` (with its extracted text, so page and passage references
resolve) and on small synthetic runs; the browser tests drive the app page in Chromium where Playwright has it.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from sit_review_agent.ui import export, rundata, server
from sit_review_agent.ui.server import build_app
from test_ui_export_links import PAGES, _hover_card, _run, text_of, walk
from test_ui_outputs import FLOW, _free_port, copy_run, make_state

RUN = "ui_flow_1"
FAMILIES = {"FND": r"\bFND-\d{3,}\b", "EV": r"\bEV-\d{3,}\b", "DEG": r"\bDEG-\d{3,}\b"}


def flow_run(runs: Path, name: str = RUN, *, text: bool = True) -> Path:
    rd = copy_run(FLOW, runs / name)
    if text and (FLOW / "text").is_dir():
        shutil.copytree(FLOW / "text", rd / "text")
    return rd


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    r = tmp_path / "runs"
    flow_run(r)
    return r


def part(html: str, cls: str) -> str:
    """The inside of the element of class ``cls`` (``report`` or ``x-reference``) in an export page or a fragment."""
    if cls == "report":
        return re.split(r'</main>|</div><div class="x-reference">', html.split('class="report">', 1)[1], maxsplit=1)[0]
    return re.split(r'<a class="x-back"|<nav class="toc"', html.split('<div class="x-reference">', 1)[1], maxsplit=1)[0]


# ------------------------------------------------------------------ the route


def test_the_fragment_is_the_export_review_with_no_script(runs: Path) -> None:
    client = TestClient(build_app(make_state(runs)))
    res = client.get(f"/runs/{RUN}/review.html")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/html")
    frag = res.text
    assert frag.startswith('<div class="rv" id="rv">') and frag.endswith("</aside></div>")
    # the app inserts it: no script, no style, no handler attribute, no script URL, nothing loaded
    assert not re.search(r"<script|<style|<iframe|<img|\son[a-z]+=|javascript:|<link", frag, re.I)
    page = client.get(f"/runs/{RUN}/export.html").text                  # the export as this server serves it
    # one renderer: the review's words and the reference part are the export's, character for character
    assert part(frag, "report") == part(page, "report").replace('href="doc.pdf#', f'href="/runs/{RUN}/doc.pdf#')
    assert text_of(part(frag, "report")) == text_of(export.review_html((runs / RUN / "report.md").read_text("utf-8")))
    assert text_of(part(frag, "x-reference")) == text_of(part(page, "x-reference"))
    # the export's pane and way back, the app's slim table of contents (no brand, no "All sections")
    assert export.PANE_HTML in frag and frag.count('href="#"') == 1 and 'class="x-back" href="#"' in frag
    assert '<nav class="toc"' in frag and "toc-brand" not in frag and 'data-g="all"' not in frag
    w = walk(frag)
    assert len(w.ids) == len(set(w.ids))
    assert [h for h in w.hrefs if h.startswith("#") and h != "#" and h[1:] not in set(w.ids)] == []


def test_the_chat_has_its_own_panel_and_is_not_in_the_fragment(runs: Path) -> None:
    rd = runs / RUN
    assert (rd / "ui" / "chat.jsonl").is_file()                    # the flow run has a chat
    frag = export.review_fragment(rd, pdf_href=None)
    assert export.CHAT_HEADING not in frag and 'id="s-chat"' not in frag
    assert export.CHAT_HEADING in export.export_html(rd, replayed=False)


def test_a_page_of_the_document_opens_the_apps_own_pdf_route(tmp_path: Path, monkeypatch) -> None:
    report = {"metadata": {"documents": [{"doc_id": "DOC-x", "role": "under_review", "title": "X",
                                          "text_path": "text/DOC-x.pages.txt"}]}}
    md = "# Design review: X\n\n## Gaps\n\n- Where: p.2: \"FR-1 The platform shall keep one namespace per learner.\"\n"
    rd = _run(tmp_path / "runs", md, report, PAGES)
    client = TestClient(build_app(make_state(tmp_path / "runs")))
    assert "doc.pdf" not in client.get("/runs/r/review.html").text            # no vouched PDF: no PDF link
    monkeypatch.setattr(rundata, "reviewed_pdf", lambda run_dir, root: tmp_path / "x.pdf")
    frag = client.get("/runs/r/review.html").text
    pages = re.findall(r'class="x-pdf" href="([^"]+)"', frag)
    assert pages == [f"/runs/r/doc.pdf#page={n}" for n in (1, 2, 3)], pages
    assert rd.is_dir()


def test_each_state_without_a_review_says_what_is_missing(runs: Path) -> None:
    client = TestClient(build_app(make_state(runs)))
    assert client.get("/runs/nope/review.html").json() == {"error": "No such run."}
    (runs / "no_md").mkdir()
    shutil.copy2(FLOW / "report.json", runs / "no_md" / "report.json")    # an older run, or one cut between the files
    res = client.get("/runs/no_md/review.html")
    assert res.status_code == 404 and res.json()["error"] == server.REVIEW_NO_MD
    (runs / "not_yet").mkdir()                                              # in progress, or ended before its report
    res = client.get("/runs/not_yet/review.html")
    assert res.status_code == 404 and res.json()["error"] == server.REVIEW_NOT_YET
    odd = runs / "odd"
    odd.mkdir()
    (odd / "report.md").write_text("# Design review: X\n\n## Gaps\n\nWords.\n", encoding="utf-8")
    (odd / "report.json").write_text(json.dumps({"metadata": {"documents": ["not an object"]}}), encoding="utf-8")
    res = client.get("/runs/odd/review.html")
    assert res.status_code == 422 and res.json()["error"].startswith(server.REVIEW_UNREADABLE + " (")
    replayed = flow_run(runs, "replayed", text=False)
    (replayed / "replay.json").write_text("{}", encoding="utf-8")  # a replay: the same document, its head stamped
    assert rundata.summary(replayed)["replayed"] is True
    assert client.get("/runs/replayed/review.html").status_code == 200


# ------------------------------------------------------------------ in a browser


@pytest.fixture
def app_page(runs: Path):
    uvicorn = pytest.importorskip("uvicorn")
    sync_api = pytest.importorskip("playwright.sync_api")
    (runs / "no_md").mkdir()
    shutil.copy2(FLOW / "report.json", runs / "no_md" / "report.json")
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(build_app(make_state(runs)), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.05)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Chromium not installed here
            pytest.skip(f"Chromium not available: {exc}")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        base = f"http://127.0.0.1:{port}"
        yield pg, ctx, base, runs
        assert errors == []
        browser.close()
    srv.should_exit = True
    th.join(timeout=5)


def open_review(pg, base: str, run: str = RUN) -> None:
    pg.goto(f"{base}/?run={run}")
    pg.wait_for_selector("#rv .report")
    pg.wait_for_selector("#chat-turns")


def _y(pg) -> float:
    return pg.evaluate("window.scrollY")


def centre(pg, link) -> None:
    """The link in the middle of the viewport, clear of the sticky topbar: a link the topbar covers would make
    Playwright scroll before its click, and the test would measure Playwright's scroll, not the page's."""
    link.evaluate("e => e.scrollIntoView({ block: 'center' })")
    pg.wait_for_timeout(50)


def top(link) -> float:
    return link.evaluate("e => e.getBoundingClientRect().top")


#: Where the review column's text ends against where the open pane begins: the column's right edge and the right end
#: of every line of text on screen (at 1440 the column makes room for the pane, so both are left of it).
BESIDE = """() => {
  const col = document.querySelector('#rv .rv-doc'), pane = document.querySelector('#rv .x-pane');
  const w = document.createTreeWalker(col, NodeFilter.SHOW_TEXT), r = document.createRange();
  let text = 0;
  for (let n; (n = w.nextNode());) {
    if (!n.data.trim()) continue;
    r.selectNodeContents(n);
    const clip = n.parentElement.closest('.x-table');                 // a wide table scrolls inside its own box
    const edge = clip ? clip.getBoundingClientRect().right : Infinity;
    for (const b of r.getClientRects()) {
      if (b.width && b.bottom > 0 && b.top < innerHeight) text = Math.max(text, Math.min(b.right, edge));
    }
  }
  return { col: col.getBoundingClientRect().right, text, pane: pane.getBoundingClientRect().left };
}"""


def clear_of_pane(pg) -> None:
    m = pg.evaluate(BESIDE)
    assert m["text"] > 0 and m["col"] <= m["pane"] and m["text"] <= m["pane"], m


#: Per family: [mentions, links, links whose target is in the Review tab] over the review's text (headings are where
#: links land), and the mentions that are not a link to a target there.
TALLY = """(arg) => {
  const rv = document.getElementById('rv'), doc = rv.querySelector('.rv-doc'), out = {}, bad = [];
  const walker = document.createTreeWalker(doc, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode());) {
    const el = n.parentElement;
    if (el.closest('h1, h2, h3')) continue;
    for (const [fam, rx] of Object.entries(arg.fams)) {
      for (const m of n.data.matchAll(new RegExp(rx, 'g'))) {
        if (!arg.known[fam].includes(m[0])) { if (el.closest('a')) bad.push('linked unknown ' + m[0]); continue; }
        const c = out[fam] = out[fam] || [0, 0, 0];
        c[0] += 1;
        const a = el.closest('a[href]');
        if (!a) { bad.push('plain ' + m[0]); continue; }
        c[1] += 1;
        const href = a.getAttribute('href'), t = document.getElementById(decodeURIComponent(href.slice(1)));
        if (href.charAt(0) === '#' && t && rv.contains(t) && [m[0], 'reg-' + m[0]].includes(t.id)) c[2] += 1;
        else bad.push('dangling ' + m[0] + ' ' + href);
      }
    }
  }
  return { out, bad };
}"""


def test_every_mention_is_a_link_to_a_target_in_the_tab_and_the_text_is_the_exports(app_page) -> None:
    pg, ctx, base, runs = app_page
    open_review(pg, base)
    report = json.loads((runs / RUN / "report.json").read_text(encoding="utf-8"))
    known = {"FND": [f["id"] for f in report["findings"]],
             "EV": [e["evidence_id"] for e in report.get("evidence_ledger") or []],
             "DEG": [d["id"] for d in (report.get("research_log") or {}).get("degradations") or []]}
    # each finding card says the finding's own id and title, as report.json has them
    heads = pg.evaluate("[...document.querySelectorAll('#rv article.finding > h3')].map(h => [h.parentNode.id, "
                        "h.textContent])")
    by = {f["id"]: f for f in report["findings"]}
    assert len(heads) >= len(by) // 2
    for fid, text in heads:
        assert " ".join(text.split()) == " ".join(f"{fid} {by[fid]['title']}".split()), fid
    got = pg.evaluate(TALLY, {"fams": FAMILIES, "known": known})
    assert got["bad"] == []
    for fam, (mentions, links, targets) in got["out"].items():
        assert mentions == links == targets, (fam, mentions, links, targets)
    assert got["out"]["FND"][0] >= len(known["FND"]) and got["out"]["EV"][0] > 0
    assert got["out"].get("DEG", [0])[0] >= len(known["DEG"])
    # no dangling in-document href and no repeated id anywhere on the page
    hrefs = pg.evaluate("[...document.querySelectorAll('#rv a[href^=\"#\"]')].map(a => a.getAttribute('href'))")
    assert [h for h in hrefs if h != "#" and pg.evaluate("h => !document.getElementById(h)", h[1:])] == []
    ids = pg.evaluate("[...document.querySelectorAll('[id]')].map(e => e.id)")
    assert len(ids) == len(set(ids)), sorted({i for i in ids if ids.count(i) > 1})[:5]
    # one implementation: the tab's text is the export body's text, part for part
    tab = pg.evaluate("['.report', '.x-reference'].map(s => document.querySelector('#rv ' + s).textContent)")
    exp = ctx.new_page()
    exp.goto(f"{base}/runs/{RUN}/export.html")
    body = exp.evaluate("['main.report', '.x-reference'].map(s => document.querySelector(s).textContent)")
    exp.close()
    assert [" ".join(t.split()) for t in tab] == [" ".join(t.split()) for t in body]


def test_a_link_opens_the_pane_beside_the_review_and_the_clicked_link_keeps_its_place(app_page) -> None:
    pg, ctx, base, runs = app_page
    open_review(pg, base)
    report = json.loads((runs / RUN / "report.json").read_text(encoding="utf-8"))
    mid = report["findings"][len(report["findings"]) // 2]["id"]
    pg.evaluate("id => window.scrollTo(0, document.getElementById(id).getBoundingClientRect().top + scrollY - 120)",
                mid)
    pg.wait_for_timeout(100)
    seen = 0
    for name, sel in (("finding", "#rv .report a.x-fnd"), ("evidence", "#rv .report a.x-ev"),
                      ("limitation", "#rv .report a.x-deg"), ("passage", "#rv .report a.x-cite"),
                      ("page", "#rv .report li.x-where a.x-loc"), ("confidence", "#rv .report a.chip.conf"),
                      ("glossary chip", "#rv .report a.chip.disp")):
        link = pg.locator(sel).first
        if link.count() == 0:
            continue
        seen += 1
        centre(pg, link)
        t0, href, url = top(link), link.get_attribute("href"), pg.url
        link.click()
        pg.wait_for_selector("#rv .x-pane:not([hidden])")
        assert abs(top(link) - t0) < 1, name                         # the clicked link kept its place, to the pixel
        clear_of_pane(pg)                                            # and no line of the review runs under the pane
        assert pg.url == url, name                                   # the app's router saw nothing
        assert pg.evaluate("() => document.querySelector('.x-pane-body').textContent.trim().length") > 0, name
        ids = pg.evaluate("() => [...document.querySelectorAll('[id]')].map(e => e.id)")
        assert len(ids) == len(set(ids)), name                       # the pane's copy carries no id
        assert pg.evaluate("h => document.querySelector('#rv .report a.x-opener').getAttribute('href') === h", href)
        assert pg.evaluate("() => document.activeElement.classList.contains('x-pane-title')"), name
        pg.keyboard.press("Escape")
        pg.wait_for_selector("#rv .x-pane", state="hidden")
        assert abs(top(link) - t0) < 1, name                         # closed: the full measure, the link in place
        assert pg.evaluate("h => document.activeElement.getAttribute('href') === h", href), name   # focus came back
        assert pg.locator("#rv .x-opener").count() == 0
    assert seen >= 6
    # a chain inside the pane: its own back and forward and the breadcrumb; the review column never moves
    link = pg.locator("#rv .report a.x-ev").first
    centre(pg, link)
    t0 = top(link)
    link.click()
    pg.wait_for_selector("#rv .x-pane:not([hidden])")
    y1 = _y(pg)                                                     # links inside the pane never move the review
    first = pg.locator(".x-pane-kicker").inner_text()
    pg.locator(".x-pane-body a.xref").first.click()
    pg.wait_for_function("k => document.querySelector('.x-pane-kicker').textContent !== k", arg=first)
    assert pg.locator(".x-pane-crumb .x-crumb").count() == 2 and pg.locator(".x-pane-crumb").is_visible()
    second = pg.locator(".x-pane-kicker").inner_text()
    pg.click(".x-pane-prev")
    pg.wait_for_function("k => document.querySelector('.x-pane-kicker').textContent === k", arg=first)
    pg.click(".x-pane-next")
    pg.wait_for_function("k => document.querySelector('.x-pane-kicker').textContent === k", arg=second)
    pg.locator(".x-pane-crumb .x-crumb").first.click()
    pg.wait_for_function("k => document.querySelector('.x-pane-kicker').textContent === k", arg=first)
    assert pg.locator("#rv .x-pane").is_visible() and pg.locator(".x-pane-crumb .x-crumb").count() == 2
    assert _y(pg) == y1
    pg.keyboard.press("Escape")
    pg.wait_for_selector("#rv .x-pane", state="hidden")
    assert abs(top(link) - t0) < 1 and pg.url == f"{base}/?run={RUN}"
    y0 = _y(pg)
    # a click on the review outside a link closes the pane
    link.click()
    pg.wait_for_selector("#rv .x-pane:not([hidden])")
    box = pg.locator("#rv .report").bounding_box()
    pg.mouse.click(box["x"] + 4, 400)
    pg.wait_for_selector("#rv .x-pane", state="hidden")
    assert abs(top(link) - t0) < 1
    # "Show in the report" moves the review to the target, and "Back to where I was" returns
    link.click()
    pg.wait_for_selector("#rv .x-pane:not([hidden])")
    pg.click(".x-pane-show")
    pg.wait_for_selector("#rv .x-pane", state="hidden")
    assert _y(pg) != y0 and pg.locator("#rv .x-back").is_visible()
    assert pg.evaluate("h => location.hash === h", link.get_attribute("href"))
    pg.click("#rv .x-back")
    pg.wait_for_function("y => Math.abs(window.scrollY - y) < 1", arg=y0)
    assert pg.locator("#rv .x-back").is_hidden()
    # a modified click opens the anchor in its own tab, which lands on the target
    href = pg.locator("#rv .report a.x-fnd").first.get_attribute("href")
    with ctx.expect_page() as tab:
        pg.locator("#rv .report a.x-fnd").first.click(modifiers=["ControlOrMeta"])
    t = tab.value
    t.wait_for_selector("#rv .report")
    assert t.url.endswith(href)
    t.wait_for_function("id => document.getElementById(id).classList.contains('x-hit')", arg=href[1:])
    land = t.evaluate("id => document.getElementById(id).getBoundingClientRect().top", href[1:])
    assert 56 <= land <= 140, land                                  # under the topbar, not behind it
    t.close()
    assert pg.locator("#rv .x-pane").is_hidden()


def test_the_hover_card_stays_open_and_scrolls_on_its_own(app_page) -> None:
    pg, ctx, base, runs = app_page
    open_review(pg, base)
    link = pg.locator("#rv .report a.x-cite").first
    if link.count() == 0:
        link = pg.locator("#rv .report li.x-where a.x-loc").first
    _hover_card(pg, link)


def test_a_coverage_criterion_offers_the_coverage_tab_and_a_chat_citation_opens_the_pane(app_page) -> None:
    pg, ctx, base, runs = app_page
    open_review(pg, base)
    cite = pg.locator("#chat-turns a.cite")
    if cite.count():
        centre(pg, cite.first)
        t0 = top(cite.first)
        cite.first.click()
        pg.wait_for_selector("#rv .x-pane:not([hidden])")
        assert abs(top(cite.first) - t0) < 1 and pg.locator(".x-pane-kicker").inner_text() == cite.first.inner_text()
        pg.keyboard.press("Escape")
        pg.wait_for_selector("#rv .x-pane", state="hidden")
    crit = pg.locator("#rv .report a.x-crit").first
    assert crit.count() == 1
    centre(pg, crit)
    crit.click()
    pg.wait_for_selector("#rv .x-pane:not([hidden])")
    more = pg.locator(".x-pane-more")
    assert more.is_visible() and more.inner_text() == "Open in the Coverage tab"
    more.click()
    pg.wait_for_function("location.search.includes('tab=coverage')")
    pg.wait_for_selector("#review h2:text-is('Coverage: criteria by section')")
    assert pg.locator("#rv").count() == 0
    pg.go_back()                                                    # the app's router: back to the Review tab
    pg.wait_for_selector("#rv .report")
    link = pg.locator("#rv .report a.x-ev").first
    centre(pg, link)
    link.click()                                                    # the new document's script is the live one
    pg.wait_for_selector("#rv .x-pane:not([hidden])")
    assert pg.locator(".x-pane-more").is_hidden()                   # an evidence item: the pane shows the most


def test_a_run_without_report_md_says_so_in_the_review_tab(app_page) -> None:
    pg, ctx, base, runs = app_page
    pg.goto(f"{base}/?run=no_md")
    pg.wait_for_selector("#review .review-missing")
    assert pg.locator("#review .review-missing").inner_text() == server.REVIEW_NO_MD
    assert pg.locator(".tab", has_text="Coverage").count() == 1
    pg.click(".tab:has-text('Evidence')")
    pg.wait_for_selector("#review h2:has-text('Evidence register')")


def test_the_table_of_contents_marks_the_part_in_view(app_page) -> None:
    pg, ctx, base, runs = app_page
    open_review(pg, base)
    item = pg.locator("#rv .toc a.toc-item").nth(2)
    g = item.get_attribute("data-g")
    url = pg.url
    item.click()
    pg.wait_for_function("g => document.querySelector('#rv .toc a.toc-item.cur').getAttribute('data-g') === g", arg=g)
    assert pg.url == url
    first = item.get_attribute("href")[1:]
    land = pg.evaluate("id => document.getElementById(id).getBoundingClientRect().top", first)
    assert 56 <= land <= 140, land
    pg.set_viewport_size({"width": 1024, "height": 800})            # the strip on top: the same marking
    pg.wait_for_timeout(100)
    assert pg.evaluate("() => getComputedStyle(document.querySelector('#rv .toc-heads')).display") == "none"
    fades = "() => ['x-fade-l', 'x-fade-r'].map(c => document.querySelector('#rv .toc-inner').classList.contains(c))"
    pg.evaluate("window.scrollTo(0, 0)")
    pg.wait_for_function("document.querySelector('#rv .toc-inner').scrollLeft === 0")
    assert pg.evaluate(fades) == [False, True]                      # more parts to the right: that edge fades
    pg.evaluate("document.getElementById('r-howto').scrollIntoView()")   # the last part, at the strip's far end
    pg.wait_for_function("g => document.querySelector('#rv .toc a.toc-item.cur').getAttribute('data-g') === g",
                         arg=str(export.REF_GROUP + 1))
    pg.wait_for_function(f"(({fades})()).join() === 'true,false'")    # at the far end only the left edge fades
    cur = pg.locator("#rv .toc a.toc-item.cur").bounding_box()
    strip = pg.locator("#rv .toc-inner").bounding_box()
    assert strip["x"] - 1 <= cur["x"] and cur["x"] + cur["width"] <= strip["x"] + strip["width"] + 1   # in view
