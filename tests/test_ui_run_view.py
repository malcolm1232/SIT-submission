"""The run view's polish round of 6 Oct 2026, from Malcolm's notes after using it.

* The counts on top explain themselves: each number opens exactly the items it counts, a "?" its word's meaning, and
  the numbers are ``report.json``'s own lists (``rundata.count_lists``).
* A label paragraph ("Objectives:", "Conditions:") is set as its list's label.
* "How findings are scored": one overview of severity, confidence and its band, rank and disposition, each statement
  with the line of the code or prompt it comes from; the confidence and disposition chips show they open.
* The Coverage and Evidence tabs are drawn by the review's own linker, with the same hover card and pane.
* The Download control holds what the zip is and its files; nothing about the download is under the tabs.
* The side pane leaves the run head usable; the page has an icon.

Offline on the committed run ``docs/live_runs/ui_flow_1``; the browser tests drive the app in Chromium where
Playwright has it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from sit_review_agent.paths import repo_root
from sit_review_agent.report import coverage
from sit_review_agent.ui import export, reviewtabs, rundata
from sit_review_agent.ui.server import build_app
from test_ui_export_links import text_of, walk
from test_ui_outputs import make_state
from test_ui_review_tab import RUN, app_page, centre, open_review, runs  # noqa: F401 - fixtures used by name

SEVERITIES = ("critical", "high", "medium", "low")


def report_of(runs_dir: Path) -> dict:
    return json.loads((runs_dir / RUN / "report.json").read_text(encoding="utf-8"))


def entry_of(html: str, eid: str) -> str:
    """The inside of the reference entry ``eid`` of a page or a fragment."""
    return html.split(f'id="{eid}"', 1)[1].split('<div class="x-entry', 1)[0]


# ------------------------------------------------------------------ the counts on top


def test_every_count_is_the_length_of_the_list_it_names(runs: Path) -> None:  # noqa: F811
    report = report_of(runs)
    lists = rundata.count_lists(report)
    assert rundata.counts(report) == {k: len(v) for k, v in lists.items()}
    findings = report["findings"]
    issues = [f for f in findings if f.get("kind") != "strength"]
    assert len(lists["findings"]) == len(findings)
    assert sum(len(lists[s]) for s in SEVERITIES) == len([f for f in issues if f.get("severity") in SEVERITIES])
    assert [f["id"] for f in lists["strengths"]] == [f["id"] for f in findings if f.get("kind") == "strength"]
    assert len(lists["sound_areas"]) == len(report.get("sound_areas") or [])
    assert len(lists["unresolved"]) == len(report.get("unresolved") or [])
    assert len(lists["limitations"]) == len(report.get("limitations") or [])


def test_each_number_opens_exactly_the_items_it_counts_and_its_question_mark_the_meaning(runs: Path) -> None:  # noqa: F811
    """The fragment's strip: one control per count, its number the list's length, its link the entry listing exactly
    those items (finding ids for the finding counts), its "?" the word's entry in How to read this review."""
    frag = export.review_fragment(runs / RUN, pdf_href=None)
    report = report_of(runs)
    lists = rundata.count_lists(report)
    strip = frag.split('<nav class="x-counts"', 1)[1].split("</nav>", 1)[0]
    controls = re.findall(r'<span class="x-count" data-count="(\w+)"(?: data-zero)?><a class="xref x-count-n" '
                          r'href="#([\w-]+)"><b>(\d+)</b> ([^<]+)</a>(?:<a class="xref x-count-q" href="#([\w-]+)")?',
                          strip)
    assert [c[0] for c in controls] == [k for k, *_ in reviewtabs.COUNT_ITEMS]
    ids = set(walk(frag).ids)
    for key, list_id, n, _words, q in controls:
        assert int(n) == len(lists[key]), key
        assert list_id in ids and q and q in ids, (key, list_id, q)     # both open something that is there
        entry = entry_of(frag, list_id)
        if key in ("findings", "strengths", *SEVERITIES):
            listed = re.findall(r'<li class="x-row" data-id="([\w-]+)">', entry)
            assert sorted(listed) == sorted(f["id"] for f in lists[key]), key
            for fid in listed:                                         # each row opens its finding
                assert re.search(rf'<a class="xref x-row-link" href="#{fid}">', entry), fid
        if not lists[key]:
            assert reviewtabs.NONE_TEXT in entry, key                  # a zero opens too, and says so
        assert "What " in text_of(entry) and "means" in text_of(entry)  # the definition comes first
    # the words of the counts the review standard does not define are in the one glossary
    assert {"count-findings", "count-sound", "count-unresolved", "count-limitations"} <= {
        q[2:] for *_, q in controls if q.startswith("g-count-")}


def test_a_zero_count_still_opens_and_says_none_in_this_run(tmp_path: Path) -> None:
    from test_ui_export_links import PAGES, _run
    report = {"metadata": {"documents": [{"doc_id": "DOC-x", "role": "under_review", "title": "X",
                                          "text_path": "text/DOC-x.pages.txt"}]},
              "findings": [{"id": "FND-001", "title": "One gap", "kind": "gap", "severity": "high", "rank": 1,
                            "disposition": "refinement_now"}]}
    rd = _run(tmp_path / "runs", "# Design review: X\n\n## Gaps\n\n### FND-001 One gap\n", report, PAGES)
    frag = export.review_fragment(rd, pdf_href=None)
    assert re.search(r'data-count="critical" data-zero><a class="xref x-count-n" href="#n-critical"><b>0</b>', frag)
    assert reviewtabs.NONE_TEXT in entry_of(frag, "n-critical")
    assert "What critical means" in text_of(entry_of(frag, "n-critical"))
    assert re.findall(r'data-id="(FND-\d+)"', entry_of(frag, "n-high")) == ["FND-001"]


def test_the_export_carries_the_same_counts_in_its_header(runs: Path) -> None:  # noqa: F811
    """Chrome added to both: the exported page's header has the strip the app's run head has, and the lists are in
    its reference part; the review's words are untouched (test_ui_export_links checks them)."""
    page = export.export_html(runs / RUN, replayed=False)
    frag = export.review_fragment(runs / RUN, pdf_href=None)
    strip = re.search(r'<nav class="x-counts".*?</nav>', page).group(0)
    assert strip == re.search(r'<nav class="x-counts".*?</nav>', frag).group(0)
    assert page.index(strip) < page.index('<main class="report">')       # in the header, not in the review
    assert 'id="r-counts"' in page and 'id="n-findings"' in page


# ------------------------------------------------------------------ sub-labels


def test_a_label_paragraph_is_marked_as_its_lists_label_and_keeps_its_words(tmp_path: Path) -> None:
    from test_ui_export_links import _run
    md = ("# Design review: X\n\n## Design intent\n\nText.\n\nObjectives:\n- one\n\nConstraints:\n- two\n\n"
          "## Fitness for purpose\n\n**Fit with conditions** (confidence 0.68). Words.\n\nConditions:\n- three\n\n"
          "A sentence that ends with a colon but is long and runs on: \n- four\n")
    rd = _run(tmp_path / "runs", md, {"metadata": {"documents": []}})
    page = export.export_html(rd, replayed=False)
    assert re.findall(r'<p class="x-sub">([^<]+)</p>', page) == ["Objectives:", "Constraints:", "Conditions:"]
    assert text_of(page.split('<main class="report">', 1)[1].split("</main>", 1)[0]) == text_of(export.review_html(md))


# ------------------------------------------------------------------ how findings are scored


def test_the_scoring_overview_says_who_sets_each_fact_and_cites_the_line(runs: Path) -> None:  # noqa: F811
    page = export.export_html(runs / RUN, replayed=False)
    entry = entry_of(page, "g-scoring")
    text = text_of(entry)
    for word in ("Severity", "Confidence", "Rank", "Disposition"):
        assert f"{word} is" in text, word
    assert "the model's own estimate" in text and "a band code derives from the number" in text
    assert "Code ranks the merged findings by severity" in text
    cites = re.findall(r"<code>([\w/.]+):(\d+)(?:-(\d+))?</code>", entry)
    want = {"prompts/system.md": ("## Severity (", "## Confidence (", "## Disposition ("),
            "prompts/refine.md": ("A change of severity or disposition needs a", "- `keep`: the finding stays."),
            "agent/sit_review_agent/report/render.py": ("def confidence_band",),
            "agent/sit_review_agent/phases/assess.py": ("def rank_by_severity",),
            "agent/sit_review_agent/phases/report.py": ("if f.disposition in NON_REFINEMENT_DISPOSITIONS",),
            "agent/sit_review_agent/models.py": ("NON_REFINEMENT_DISPOSITIONS: frozenset",)}
    seen: dict[str, set[str]] = {}
    for path, line, _ in cites:
        got = (repo_root() / path).read_text(encoding="utf-8").splitlines()[int(line) - 1]
        hit = [n for n in want.get(path, ()) if n in got]
        assert hit, (path, line, got)                                  # every cited line says what is cited
        seen.setdefault(path, set()).update(hit)
    assert {p: set(n) for p, n in want.items()} == seen
    # the confidence chip's entry leads to it, and it sits first under its heading in How to read this review
    assert 'href="#g-scoring"' in entry_of(page, "g-confidence")
    howto = page.split('id="r-howto"', 1)[1]
    assert howto.index('id="g-scoring"') < howto.index('id="g-confidence"') < howto.index('id="g-rank"')


# ------------------------------------------------------------------ the Coverage and Evidence tabs, the server side


@pytest.mark.parametrize("view", ["coverage", "evidence"])
def test_a_tab_is_drawn_by_the_reviews_linker_with_the_review_kept_beside_it(runs: Path, view: str) -> None:  # noqa: F811
    client = TestClient(build_app(make_state(runs)))
    res = client.get(f"/runs/{RUN}/review.html?view={view}")
    assert res.status_code == 200
    frag = res.text
    assert frag.startswith(f'<div class="rv rv-tab" id="rv" data-view="{view}">')
    assert not re.search(r"<script|<style|\son[a-z]+=|javascript:", frag, re.I)
    w = walk(frag)
    ids = set(w.ids)
    assert len(ids) == len(w.ids)
    assert [h for h in w.hrefs if h.startswith("#") and h != "#" and h[1:] not in ids] == []
    body = frag.split('<div class="rv-view">', 1)[1].split('<div class="rv-store" hidden>', 1)[0]
    # an outside source's excerpt names its own sections, not the reviewed document's: those stay plain
    body = re.sub(r'<tr class="ev-row">(?:(?!</tr>).)*?src-(?:external|inference)(?:(?!</tr>).)*</tr>', "", body,
                  flags=re.S)
    report = report_of(runs)
    known = {f["id"] for f in report["findings"]} | {e["evidence_id"] for e in report["evidence_ledger"]} \
        | {s["id"] for s in report.get("sound_areas") or []}
    # every id of the run the tab mentions is a link to its target, and every section or page reference is one too
    for text, href, heading, _ in walk(body).runs:
        if heading:
            continue                                                    # a heading is where a link lands
        for m in re.finditer(r"\b(?:FND|EV|SA)-\d{3,}\b", text):
            if m.group(0) in known:
                assert href in (f"#{m.group(0)}", f"#reg-{m.group(0)}"), (view, m.group(0), href)
        for m in re.finditer(r"(?:p\.\d+ )?§\d+(?:\.\d+)*", text):
            assert href is not None and href.startswith("#doc-"), (view, m.group(0), text[:60])
    assert client.get(f"/runs/{RUN}/review.html?view=nope").status_code == 400


def test_a_document_excerpt_links_its_references_and_an_outside_one_keeps_its_own(tmp_path: Path) -> None:
    """In the Evidence tab a passage of the reviewed document links its section references, as the review's own
    quotes do; an outside source's excerpt names that source's sections, so its "§3" stays plain text."""
    from test_ui_export_links import PAGES, _run
    report = {"metadata": {"documents": [{"doc_id": "DOC-x", "role": "under_review", "title": "X",
                                          "text_path": "text/DOC-x.pages.txt"}]},
              "findings": [{"id": "FND-001", "title": "t", "kind": "gap", "severity": "low", "rank": 1,
                            "evidence": [{"evidence_id": "EV-001", "supports_claim": True}]}],
              "evidence_ledger": [
                  {"evidence_id": "EV-001", "source_type": "doc", "excerpt": "Checks run in order, see §3.",
                   "url_or_citation": "doc:DOC-x#p3/s3", "derived_from": []},
                  {"evidence_id": "EV-002", "source_type": "external", "excerpt": "The standard's §3 says so.",
                   "url_or_citation": "https://example.org/std", "title": "A standard", "derived_from": []}]}
    rd = _run(tmp_path / "runs", "# Design review: X\n\n## Gaps\n\n### FND-001 t\n", report, PAGES,
              [{"section_id": "3", "heading": "Gateway", "char_start": PAGES.index("3. Gateway")}])
    frag = export.review_fragment(rd, pdf_href=None, view="evidence")
    rows = dict(re.findall(r'<tr class="ev-row"><td><a [^>]*href="#(EV-\d+)"[^>]*>.*?</a></td>(.*?)</tr>', frag))
    assert re.search(r'<a class="xref x-loc" href="#doc-s3"[^>]*>§3</a>', rows["EV-001"])
    assert "§3" in rows["EV-002"] and "#doc-s3" not in rows["EV-002"]
    assert "FND-001</a> (supports)" in rows["EV-001"]



def test_an_outside_sources_row_gives_its_title_and_its_address(tmp_path: Path) -> None:
    """A run with tools on (6 Oct 2026, the first one): an outside source's row in the Evidence tab gave only its
    title, so the reader could not see where it came from. It gives the title and the host, a link to the address
    (Malcolm, 6 Oct 2026: "outside links in evidence should be clickable"; tests/test_ui_outlinks.py); a tool call's
    citation is the tool and its query in words, in the same wrapping column."""
    from test_ui_export_links import PAGES, _run
    call = 'mcp:mcp-internet-search/search_web?{"mode":"answer","query":"' + "pgvector hnsw filtering " * 6 + '"}'
    report = {"metadata": {"documents": [{"doc_id": "DOC-x", "role": "under_review", "title": "X",
                                          "text_path": "text/DOC-x.pages.txt"}]},
              "findings": [{"id": "FND-001", "title": "t", "kind": "gap", "severity": "low", "rank": 1,
                            "evidence": [{"evidence_id": "EV-001", "supports_claim": True}]}],
              "evidence_ledger": [
                  {"evidence_id": "EV-001", "source_type": "external", "excerpt": "Lifetimes are set per policy.",
                   "url_or_citation": "https://learn.example.org/token-lifetimes", "title": "Token lifetimes",
                   "authority": "primary_official", "derived_from": []},
                  {"evidence_id": "EV-002", "source_type": "external", "excerpt": "No results.",
                   "url_or_citation": call, "derived_from": []}]}
    rd = _run(tmp_path / "runs", "# Design review: X\n\n## Gaps\n\n### FND-001 t\n", report, PAGES, [])
    frag = export.review_fragment(rd, pdf_href=None, view="evidence")
    rows = dict(re.findall(r'<tr class="ev-row"><td><a [^>]*href="#(EV-\d+)"[^>]*>.*?</a></td>(.*?)</tr>', frag))
    where = [re.findall(r"<td>(.*?)</td>", r)[1] for r in (rows["EV-001"], rows["EV-002"])]
    assert text_of(where[0]) == "Token lifetimes \u00b7 learn.example.org"
    assert 'href="https://learn.example.org/token-lifetimes" target="_blank"' in where[0]
    assert 'title="https://learn.example.org/token-lifetimes"' in where[0]          # the whole address on hover
    assert text_of(where[1]) == ("search_web on mcp-internet-search: \u201c" + ("pgvector hnsw filtering " * 6).strip()
                                 + " \u201d (mode answer)")
    assert 'class="x-ev-where"' in where[1] and "<a " not in where[1]


def test_the_coverage_tab_says_what_the_grid_and_each_code_mean_from_their_sources(runs: Path) -> None:  # noqa: F811
    frag = export.review_fragment(runs / RUN, pdf_href=None, view="coverage")
    html = frag.split('<div class="cv-intro">', 1)[1].split('<div class="x-table cv-grid">', 1)[0]
    assert text_of(html).startswith("Each column is one review criterion of this run's configuration")
    pairs = [(text_of(dt), text_of(dd)) for dt, dd in re.findall(r"<dt>(.*?)</dt><dd>(.*?)</dd>", html)]
    legend = reviewtabs._legend(coverage.LEGEND)
    assert [c for c, _ in legend] == ["nX", "ok", "?", "-", "SA"]
    assert pairs[:5] == legend                                          # the coverage map's own legend, every code
    assert ("checked, no issue", "Checked, nothing material found; the note says what was checked.") in pairs
    assert ("not applicable", "The note says why.") in pairs
    assert "From prompts/assess.md:" in text_of(html)


def test_an_evidence_row_is_one_link_to_its_entry_which_says_what_it_supports(runs: Path) -> None:  # noqa: F811
    frag = export.review_fragment(runs / RUN, pdf_href=None, view="evidence")
    report = report_of(runs)
    rows = re.findall(r'<tr class="ev-row"><td><a class="xref x-ev x-rowlink" href="#(EV-\d+)"', frag)
    assert rows == [e["evidence_id"] for e in report["evidence_ledger"]]
    cited = {(f["id"], e["evidence_id"], e.get("supports_claim")) for f in report["findings"]
             for e in f.get("evidence") or []}
    for fid, eid, sup in sorted(cited)[:20]:
        rel = {True: " (supports)", False: " (contrary)"}.get(sup, "")
        assert f"{fid}{rel}" in text_of(entry_of(frag, eid)), (fid, eid)   # the entry the row opens says it


# ------------------------------------------------------------------ the page's icon


def test_the_page_has_an_icon(runs: Path) -> None:  # noqa: F811
    client = TestClient(build_app(make_state(runs)))
    res = client.get("/favicon.ico")
    assert res.status_code == 200 and res.headers["content-type"] == "image/x-icon" and res.content[:4] == b"\0\0\1\0"
    assert client.get("/static/favicon.svg").status_code == 200
    page = client.get("/").text
    assert '<link rel="icon" href="/static/favicon.svg"' in page and '<link rel="icon" href="/favicon.ico"' in page


# ------------------------------------------------------------------ in a browser


def _pane_ids(pg) -> list[str]:
    return pg.evaluate("[...document.querySelectorAll('#rv .x-pane-body .x-row[data-id]')].map(r => r.dataset.id)")


def test_clicking_a_count_lists_exactly_its_items_and_a_row_opens_its_finding(app_page) -> None:  # noqa: F811
    pg, ctx, base, runs_dir = app_page
    open_review(pg, base)
    report = report_of(runs_dir)
    lists = rundata.count_lists(report)
    assert pg.locator("#run-counts .x-counts").count() == 1                       # in the run head
    assert pg.locator("#rv .x-counts").count() == 0
    for key in ("findings", *SEVERITIES, "strengths"):
        ctl = pg.locator(f"#run-counts .x-count[data-count={key}] a.x-count-n")
        assert ctl.inner_text().split()[0] == str(len(lists[key]))
        ctl.click()
        pg.wait_for_selector("#rv .x-pane:not([hidden])")
        assert pg.locator(".x-pane-kicker").inner_text() == reviewtabs.COUNTS_TITLE
        assert sorted(_pane_ids(pg)) == sorted(f["id"] for f in lists[key]), key
        if not lists[key]:
            assert reviewtabs.NONE_TEXT in pg.locator("#rv .x-pane-body").inner_text()
        pg.keyboard.press("Escape")
        pg.wait_for_selector("#rv .x-pane", state="hidden")
    key = next(k for k in SEVERITIES if lists[k])
    pg.locator(f"#run-counts .x-count[data-count={key}] a.x-count-n").click()
    first = lists[key][0]["id"]
    pg.locator(f"#rv .x-pane-body .x-row[data-id='{first}'] a.x-row-link").click()
    pg.wait_for_function(f"document.querySelector('.x-pane-kicker').textContent === '{first}'")
    assert pg.locator("#rv .x-pane-body article.finding").count() == 1          # the finding's card, in the pane
    assert pg.locator(".x-crumb").count() == 2                                  # and the way back to the list
    pg.keyboard.press("Escape")
    pg.locator("#run-counts .x-count[data-count=findings] a.x-count-q").click()   # the "?": the meaning
    pg.wait_for_function("document.querySelector('.x-pane-title').textContent === 'findings'")


@pytest.mark.parametrize("width", [1440, 1024])
def test_the_open_pane_leaves_the_run_head_and_the_tabs_usable(app_page, width: int) -> None:  # noqa: F811
    """With the pane open the Download, Email and Share controls and every tab are on top where they are drawn (the
    pane starts under them), and the pane reaches up to the topbar once they have scrolled away."""
    pg, ctx, base, runs_dir = app_page
    pg.set_viewport_size({"width": width, "height": 900})
    open_review(pg, base)
    pg.locator("#run-counts .x-count[data-count=findings] a.x-count-n").click()
    pg.wait_for_selector("#rv .x-pane:not([hidden])")
    on_top = """sel => [...document.querySelectorAll(sel)].map(e => { const r = e.getBoundingClientRect();
      const t = document.elementFromPoint(r.left + r.width - 4, r.top + r.height / 2);
      return !!t && e.contains(t); })"""
    for sel in ("#out-download", "#dl-more", "#email-btn", "#share-btn", "#top-tabs .tab"):
        assert all(pg.evaluate(on_top, sel)), (width, sel)
    pane_top = pg.evaluate("document.querySelector('#rv .x-pane').getBoundingClientRect().top")
    tabs_bottom = pg.evaluate("document.querySelector('#app .tabrow').getBoundingClientRect().bottom")
    assert pane_top >= tabs_bottom
    pg.mouse.wheel(0, 1500)
    pg.wait_for_function("document.querySelector('#app .tabrow').getBoundingClientRect().bottom < 0")
    pg.wait_for_function("(() => { const p = document.querySelector('#rv .x-pane').getBoundingClientRect().top;"
                         " const t = parseFloat(getComputedStyle(document.getElementById('rv'))"
                         ".getPropertyValue('--rv-top')); return Math.abs(p - t) < 1; })()")


def test_the_download_control_holds_what_the_zip_is_and_its_files(app_page) -> None:  # noqa: F811
    pg, ctx, base, runs_dir = app_page
    open_review(pg, base)
    pg.wait_for_selector("#outputs:not([hidden])")
    assert pg.locator("#out-line").count() == 0                                  # nothing under the tabs
    assert "A zip of one" not in pg.locator("#app .tabrow").inner_text()
    pop = pg.locator("#dl-pop")
    assert pop.is_hidden()
    pg.hover("#out-download")
    pop.wait_for(state="visible")
    assert pop.inner_text().startswith("A zip of one cross-linked review page")
    assert [a.inner_text() for a in pop.locator("a").all()] == ["Open it in a new tab", "report.md", "report.json"]
    pg.mouse.move(5, 5)
    pop.wait_for(state="hidden")
    pg.focus("#out-download")                                                    # the keyboard reaches it too
    pop.wait_for(state="visible")
    assert pg.get_attribute("#out-download", "aria-describedby") == "out-download-help"
    pg.keyboard.press("Tab")                                                     # the chevron
    pg.keyboard.press("Tab")                                                     # then into the popover's links
    assert pg.evaluate("document.activeElement.id") == "out-open"
    pg.keyboard.press("Escape")
    pop.wait_for(state="hidden")
    pg.click("#dl-more")                                                         # touch: the chevron keeps it open
    pop.wait_for(state="visible")
    assert pg.get_attribute("#dl-more", "aria-expanded") == "true"


def test_the_label_paragraphs_and_the_chips_that_open_their_meaning_look_the_part(app_page) -> None:  # noqa: F811
    pg, ctx, base, runs_dir = app_page
    open_review(pg, base)
    sub = pg.locator("#rv p.x-sub").first
    assert sub.count() == 1
    style = sub.evaluate("e => { const s = getComputedStyle(e), b = getComputedStyle(e.closest('.sec').querySelector("
                         "'p:not(.x-sub)')); return [s.fontFamily === b.fontFamily, s.fontSize, b.fontSize, "
                         "s.fontWeight]; }")
    assert style[0] and style[1] == style[2] and style[3] == "600"
    chip = pg.locator("#rv .report a.chip.conf").first
    assert chip.evaluate("e => getComputedStyle(e, '::after').content") == '"i"'
    assert chip.evaluate("e => getComputedStyle(e).cursor") == "pointer"
    centre(pg, chip)
    box = chip.bounding_box()
    pg.mouse.move(box["x"] + 8, box["y"] + box["height"] / 2)
    pg.wait_for_selector(".x-pop:not([hidden])")                                 # hovering it previews the meaning
    assert "the probability that the finding is correct and material" in pg.locator(".x-pop").inner_text()


def test_the_coverage_and_evidence_tabs_use_the_reviews_hover_card_and_pane(app_page) -> None:  # noqa: F811
    pg, ctx, base, runs_dir = app_page
    open_review(pg, base, tab="evidence")
    row = pg.locator("#rv tr.ev-row").nth(1)
    eid = row.locator("a.x-rowlink").inner_text()
    centre(pg, row)
    cell = row.locator("td").nth(3).bounding_box()                              # the excerpt, not the id: the row
    pg.mouse.move(cell["x"] + 20, cell["y"] + cell["height"] / 2)
    pg.wait_for_selector(".x-pop:not([hidden])")
    card = pg.locator(".x-pop").inner_text()
    assert card.startswith(eid) and ("Cited by" in card or "In the document" in card or "Source" in card)
    pg.mouse.click(cell["x"] + 20, cell["y"] + cell["height"] / 2)               # a click opens the same entry
    pg.wait_for_function(f"document.querySelector('.x-pane-kicker').textContent === '{eid}'")
    assert pg.locator(".x-pane-more").inner_text() == "Show in the review"
    pg.keyboard.press("Escape")
    pg.wait_for_selector("#rv .x-pane", state="hidden")
    pg.keyboard.press("Tab")
    pg.focus("#rv tr.ev-row a.x-rowlink >> nth=0")                              # the keyboard: focus shows it
    pg.wait_for_selector(".x-pop:not([hidden])")
    open_review(pg, base, tab="coverage")
    cell_link = pg.locator("#rv .cv-grid td.cv-hit a").first
    centre(pg, cell_link)
    cell_link.click()
    pg.wait_for_selector("#rv .x-pane:not([hidden])")
    assert pg.locator(".x-pane-kicker").inner_text() == "Coverage"
    assert pg.locator("#rv .x-pane-body .x-row").count() >= 1



def test_a_long_citation_wraps_inside_the_registers_column(app_page) -> None:  # noqa: F811
    """A tool call's citation is one long word: it wraps in the Where column, so the register keeps the width of
    the reading column and its excerpts stay in view (it ran 420 px past it on the first run with tools on)."""
    pg, ctx, base, runs_dir = app_page
    open_review(pg, base, tab="evidence")
    m = pg.evaluate("""() => {
      const cell = document.querySelectorAll('#rv .rv-view tr.ev-row')[1].children[2];
      cell.innerHTML = '<span class="x-ev-where x-muted">mcp:mcp-internet-search/search_web?{"fetch_top_n":2,'
        + '"mode":"answer","query":"pgvector hnsw filtering iterative index scans ef_search"}</span>';
      const g = document.querySelector('#rv .rv-view .ev-grid');
      return { box: g.getBoundingClientRect().width, table: g.querySelector('table').getBoundingClientRect().width,
               where: cell.getBoundingClientRect().width };
    }""")
    assert m["table"] <= m["box"] + 1 and m["where"] <= 330, m

def test_the_rail_scrollers_use_the_rails_colours(app_page) -> None:  # noqa: F811
    pg, ctx, base, runs_dir = app_page
    open_review(pg, base)
    for sel in ("#rail-runs", "#rail-log", ".navrail-slot"):
        got = pg.evaluate("s => { const c = getComputedStyle(document.querySelector(s)); "
                          "return [c.scrollbarWidth, c.scrollbarColor]; }", sel)
        assert got[0] == "thin" and got[1] != "auto" and "255, 255, 255" in got[1], (sel, got)


# ------------------------------------------------------------------ the chat: streamed, and no money shown


class GatedStream:
    """A fake chat client (no model call): it passes the answer on word by word, holding at ``hold`` words until the
    test releases it, so the page can be seen mid-stream; ``stop`` notes whether the call was cancelled."""

    def __init__(self, fid: str, hold: int = 6) -> None:
        import threading

        self.fid, self.hold, self.release, self.cancelled = fid, hold, threading.Event(), threading.Event()
        self.text = f"{fid} is ranked first because the review finds the counselling wall has an override path."

    async def ask(self, **kw):  # noqa: ANN201 - the ChatClient protocol
        import asyncio

        from sit_review_agent.ui import chat

        words = self.text.split(" ")
        try:
            for i in range(1, len(words) + 1):
                kw["on_partial"](" ".join(words[:i]))
                await asyncio.sleep(0.02)
                while i == self.hold and not self.release.is_set():
                    await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return chat.ChatReply({"answer": self.text, "cited_finding_ids": [self.fid], "cited_evidence_ids": [],
                               "cited_other_ids": [], "supported": True}, None, 0.37, chat.MODEL, 4.2)


@pytest.fixture
def chat_page(tmp_path: Path):
    import threading
    import time

    uvicorn = pytest.importorskip("uvicorn")
    sync_api = pytest.importorskip("playwright.sync_api")
    from sit_review_agent.ui.launcher import Launcher
    from sit_review_agent.ui.server import UIState
    from test_ui_outputs import _free_port
    from test_ui_review_tab import flow_run

    runs_dir = tmp_path / "runs"
    flow_run(runs_dir)
    fake = GatedStream(report_of(runs_dir)["findings"][0]["id"])           # a finding of this run, so it resolves
    state = UIState(runs_dir=runs_dir.resolve(), repo_root=repo_root(), launcher=Launcher(repo_root=repo_root()),
                    chat_client=fake, profiles=[], tools=[])
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(build_app(state), host="127.0.0.1", port=port, log_level="warning"))
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
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        yield pg, f"http://127.0.0.1:{port}", runs_dir / RUN, fake
        assert errors == []
        browser.close()
    fake.release.set()
    srv.should_exit = True
    th.join(timeout=5)


def test_the_answer_appears_as_it_is_written_and_stop_ends_the_call(chat_page) -> None:
    from sit_review_agent.ui import chat

    pg, base, run_dir, fake = chat_page
    open_review(pg, base)
    before = len(chat.history(run_dir))
    assert "$" not in pg.locator("#chat").inner_text()                   # no money anywhere in the chat panel
    pg.fill("#chat-input", "Why is FND-019 first?")
    pg.press("#chat-input", "Enter")
    words = " ".join(fake.text.split(" ")[:fake.hold])
    pg.wait_for_function(f"document.querySelector('.turn .answer.streaming')?.textContent === {words!r}")
    assert pg.locator("#chat-stop").is_visible() and pg.locator("#chat-send").is_hidden()
    assert pg.locator(".turn.pending .who").inner_text() == "Review assistant · writing the answer…"
    assert len(chat.history(run_dir)) == before                           # nothing logged while it streams
    fake.release.set()                                                   # the rest of the answer, then the turn
    pg.wait_for_selector(".turn.pending", state="detached")
    last = pg.locator("#chat-turns .turn").last
    assert last.locator("p.answer").inner_text() == fake.text
    assert last.locator(".cites a.cite").inner_text() == fake.fid       # its citation is a link once it is whole
    assert last.locator(".who").inner_text() == "Review assistant · 1 model call, 4.2 s"
    assert "$" not in pg.locator("#chat").inner_text() and pg.locator("#chat-send").is_visible()
    assert chat.history(run_dir)[-1]["answer"] == fake.text and chat.history(run_dir)[-1]["cost_usd"] == 0.37
    # a second question, stopped mid-stream: the server ends the call and logs it as counted
    fake.release.clear()
    pg.fill("#chat-input", "And FND-018?")
    pg.press("#chat-input", "Enter")
    pg.wait_for_function(f"document.querySelector('.turn .answer.streaming')?.textContent === {words!r}")
    pg.click("#chat-stop")
    pg.wait_for_selector(".turn.pending", state="detached")
    assert fake.cancelled.wait(5)
    assert chat.history(run_dir)[-1]["error"] == chat.STOPPED_ERROR
    assert pg.locator("#chat-turns .turn .stopped").last.inner_text() == chat.STOPPED_TEXT
    used = chat.budget(run_dir)["calls_used"]
    assert pg.locator("#chat-budget").inner_text().startswith(f"{used} of {chat.MAX_CALLS} asks used")
    assert pg.locator("#chat-send").is_visible() and pg.locator("#chat-input").is_enabled()
