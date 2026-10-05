"""The export's cross-links (5 Oct 2026): every identifier a cold reader cannot resolve is a link to a place that
exists in the page, and the linking changes none of the review's words.

Offline on the committed run ``docs/live_runs/ui_flow_1`` and on small synthetic runs; the browser test opens the
exported file itself (file://) in Chromium where Playwright has it.
"""

from __future__ import annotations

import html as _html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from sit_review_agent.paths import repo_root
from sit_review_agent.report.render import confidence_band
from sit_review_agent.ui import export
from test_ui_outputs import FLOW, copy_run

RUN_IDS = {"FND": r"\bFND-\d{3,}\b", "EV": r"\bEV-\d{3,}\b", "DEG": r"\bDEG-\d{3,}\b"}


@pytest.fixture
def flow(tmp_path: Path) -> Path:
    return copy_run(FLOW, tmp_path / "runs" / "ui_flow_1")


class Walk(HTMLParser):
    """Each text run with the href of the link it sits in (or None) and whether it is in a heading; every id."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict[str, str | None]]] = []
        self.runs: list[tuple[str, str | None, bool, bool]] = []
        self.ids: list[str] = []
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if a.get("id"):
            self.ids.append(str(a["id"]))
        if tag == "a" and a.get("href") is not None:
            self.hrefs.append(str(a["href"]))
        if tag not in ("br", "hr", "meta", "img", "input"):
            self.stack.append((tag, a))

    def handle_endtag(self, tag: str) -> None:
        while self.stack and self.stack.pop()[0] != tag:
            pass

    def handle_data(self, data: str) -> None:
        tags = [t for t, _ in self.stack]
        if "script" in tags or "style" in tags or "nav" in tags:
            return
        href = next((a.get("href") for t, a in reversed(self.stack) if t == "a"), None)
        self.runs.append((data, href, any(t in ("h1", "h2", "h3") for t in tags), "main" in tags))


def walk(page: str) -> Walk:
    w = Walk()
    w.feed(page)
    w.close()
    return w


def text_of(fragment: str) -> str:
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", "", fragment)).split())


def main_of(page: str) -> str:
    return page.split('<main class="report">', 1)[1].split("</main>", 1)[0]


# ------------------------------------------------------------------ L1: every id is a link to a target in the page


def test_every_finding_evidence_and_limitation_mention_is_a_link_to_a_target_in_the_page(flow: Path) -> None:
    """Each FND, EV and DEG id the run holds is a link wherever it is mentioned, to an id in the page; an id the run
    does not hold (a finding merged away, say) stays plain text, never a dead link."""
    page = export.export_html(flow, replayed=False)
    report = json.loads((flow / "report.json").read_text(encoding="utf-8"))
    known = {"FND": {f["id"] for f in report["findings"]},
             "EV": {e["evidence_id"] for e in report.get("evidence_ledger") or []},
             "DEG": {d["id"] for d in (report.get("research_log") or {}).get("degradations") or []}}
    w = walk(page)
    ids = set(w.ids)
    counted = {k: 0 for k in RUN_IDS}
    for text, href, heading, _ in w.runs:
        if heading:
            continue                       # a finding's own heading is where its links land
        for fam, rx in RUN_IDS.items():
            for m in re.finditer(rx, text):
                if m.group(0) not in known[fam]:
                    assert href is None, (m.group(0), href)        # not in the run: plain
                    continue
                counted[fam] += 1
                assert href is not None and href.startswith("#"), (fam, m.group(0), text[:80])
                assert href[1:] in ids and href in (f"#{m.group(0)}", f"#reg-{m.group(0)}"), (m.group(0), href)
    assert counted["FND"] >= len(report["findings"]) and counted["EV"] > 0
    assert counted["DEG"] >= len(known["DEG"])
    for f in report["findings"]:
        assert f["id"] in ids                                     # each finding's card carries its id


def test_no_in_page_link_is_dangling_and_no_id_is_repeated(flow: Path) -> None:
    pages = (export.export_html(flow, replayed=False), export.export_html(flow, replayed=False, pdf_href="doc.pdf"))
    for page in pages:
        w = walk(page)
        ids = set(w.ids)
        assert len(ids) == len(w.ids), [i for i in ids if w.ids.count(i) > 1][:5]
        dangling = [h for h in w.hrefs if h.startswith("#") and h != "#" and h[1:] not in ids]
        assert dangling == []
        assert page.count('href="#"') == 1 and 'class="x-back" href="#"' in page    # only the way back


def test_linking_changes_none_of_the_reviews_words(flow: Path) -> None:
    md = (flow / "report.md").read_text(encoding="utf-8")
    page = export.export_html(flow, replayed=False)
    assert text_of(main_of(page)) == text_of(export.review_html(md))


def test_the_single_file_resolves_inside_itself_and_names_no_pdf(flow: Path) -> None:
    page = export.export_html(flow, replayed=False)
    assert "doc.pdf" not in page and "document.pdf" not in page
    w = walk(page)
    assert all(h.startswith("#") for h in w.hrefs if not h.startswith(("http://", "https://")))


# ------------------------------------------------------------------ L2: on a synthetic run, by pattern and by data


def _run(tmp: Path, md: str, report: dict, pages: str | None = None, sections: list | None = None) -> Path:
    rd = tmp / "r"
    (rd / "text").mkdir(parents=True)
    (rd / "report.md").write_text(md, encoding="utf-8")
    (rd / "report.json").write_text(json.dumps(report), encoding="utf-8")
    if pages is not None:
        (rd / "text" / "DOC-x.pages.txt").write_text(pages, encoding="utf-8")
        starts = [m.end() for m in re.finditer(r"\[\[PAGE \d+\]\]\n", pages)]
        ends = [m.start() for m in re.finditer(r"\[\[PAGE \d+\]\]\n", pages)][1:] + [len(pages)]
        (rd / "text" / "DOC-x.sections.json").write_text(json.dumps({
            "doc_id": "DOC-x", "pages": [{"number": i + 1, "char_start": s, "char_end": e}
                                         for i, (s, e) in enumerate(zip(starts, ends, strict=True))],
            "sections": sections or []}), encoding="utf-8")
    return rd


PAGES = ("[[PAGE 1]]\nTitle page\n[[PAGE 2]]\n2. Requirements\n"
         "FR-1 The platform shall keep one namespace per learner.\n"
         "P1 Learner namespace is authoritative.\n[[PAGE 3]]\n3. Gateway\nChecks run in order before any query.\n")


def test_ids_without_a_target_stay_plain_and_known_ones_link_by_data(tmp_path: Path) -> None:
    sec_start = PAGES.index("3. Gateway")
    report = {
        "metadata": {"documents": [{"doc_id": "DOC-x", "role": "under_review", "title": "X",
                                    "text_path": "text/DOC-x.pages.txt"}]},
        "findings": [{"id": "FND-001", "title": "t", "statement": "s", "kind": "gap"}],
        "evidence_ledger": [{"evidence_id": "EV-001", "source_type": "doc", "excerpt": "Checks run in order before"
                             " any query.", "url_or_citation": "doc:DOC-x#p3/s3", "derived_from": []}],
        "decision_registry": [{"registry_id": "AD-001", "type": "requirement", "doc_ref": "FR-1", "statement": "One "
                               "namespace.", "doc_anchor": {"doc_id": "DOC-x", "page": 2, "section_ref": "2",
                                                            "quote": "The platform shall keep one namespace per "
                                                                     "learner.",
                                                            "requirement_ids": ["FR-1", "P1"]}}],
        "intent_summary": {"objectives": [{"ref": "P1", "text": "authoritative"}]},
    }
    md = ("# Design review: X\n\n## Gaps\n\n### FND-001 t\n\ns\n\n"
          "## Fitness for purpose\n\nFND-001 and FND-999 and EV-001 and EV-777 and DEG-001. FR-1, FR-2, P1 and P7. "
          "Section 3 and Section 9 and p.3 §3: \"Checks run in order before any query.\"\n")
    rd = _run(tmp_path, md, report, PAGES, [{"section_id": "3", "heading": "Gateway", "char_start": sec_start,
                                             "char_end": len(PAGES), "page_start": 3}])
    page = export.export_html(rd, replayed=False)
    main = main_of(page)
    assert '<a class="xref x-fnd" href="#FND-001">FND-001</a>' in main
    assert '<a class="xref x-ev" href="#EV-001">EV-001</a>' in main
    for plain in ("FND-999", "EV-777", "DEG-001", "FR-2", "P7"):            # no target: plain text, never a dead link
        assert re.search(rf">[^<]*\b{plain}\b", main) and f">{plain}</a>" not in main, plain
    assert 'href="#AD-001"' in main and '>FR-1</a>' in main                  # by the registry's doc_ref
    assert '>P1</a>' in main and 'href="#AD-001"' in main                    # by the registry's requirement_ids
    assert re.search(r'href="#doc-s3"[^>]*>3</a>', main)                     # Section 3 opens the section
    assert ">9</a>" not in main                                              # Section 9 is not in the document
    assert re.search(r'href="#doc-q\d+"[^>]*>p\.3 §3</a>', main)             # the quoted passage, marked
    assert text_of(main) == text_of(export.review_html(md))
    w = walk(page)
    assert [h for h in w.hrefs if h.startswith("#") and h != "#" and h[1:] not in set(w.ids)] == []


def test_a_document_id_without_a_registry_entry_links_to_the_line_that_defines_it(tmp_path: Path) -> None:
    report = {"metadata": {"documents": [{"doc_id": "DOC-x", "role": "under_review", "title": "X",
                                          "text_path": "text/DOC-x.pages.txt"}]},
              "intent_summary": {"objectives": [{"ref": "P1", "text": "a"}, {"ref": "FR-9", "text": "b"}]}}
    rd = _run(tmp_path, "# Design review: X\n\n## Design intent\n\nP1 and FR-1 and FR-9.\n", report, PAGES)
    page = export.export_html(rd, replayed=False)
    m = re.search(r'<a class="xref x-docid" href="#(doc-q\d+)"[^>]*>P1</a>', page)
    assert m, "P1 links to its defining line"
    mark = re.search(rf'<mark id="{m.group(1)}">([^<]*)</mark>', page)
    assert mark and mark.group(1) == "P1 Learner namespace is authoritative."
    assert re.search(r'href="#doc-q\d+"[^>]*>FR-1</a>', page)                # the same family, defined in the text
    assert ">FR-9</a>" not in page                                           # neither registry nor text: plain


# ------------------------------------------------------------------ L3: the confidence entry states what the code does


def test_the_confidence_entry_states_the_code_and_cites_it_at_the_right_lines(flow: Path) -> None:
    page = export.export_html(flow, replayed=False)
    entry = page.split('id="g-confidence"', 1)[1].split('<div class="x-entry', 1)[0]
    text = text_of(entry)
    assert "model's own estimate, not computed by code" in text
    assert "high at 0.80 or more, medium at 0.50 or more, low below 0.50" in text
    assert (confidence_band(0.8), confidence_band(0.79), confidence_band(0.5), confidence_band(0.49)) == \
        ("high", "medium", "medium", "low")
    cites = re.findall(r"<code>([\w/.]+):(\d+)(?:-(\d+))?</code>", entry)
    assert cites
    want = {"agent/sit_review_agent/report/render.py": "def confidence_band", "prompts/system.md": "## Confidence (",
            "agent/sit_review_agent/phases/_model_calls.py": "def _clamp"}
    for path, line, _ in cites:
        if path in want:
            got = (repo_root() / path).read_text(encoding="utf-8").splitlines()[int(line) - 1]
            assert want[path] in got, (path, line, got)
    assert {p for p, _, _ in cites} >= set(want)


# ------------------------------------------------------------------ L4: in a browser, from the file itself


def test_following_a_link_and_coming_back_in_a_browser(flow: Path, tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    f = tmp_path / "index.html"
    f.write_text(export.export_html(flow, replayed=False), encoding="utf-8")
    report = json.loads((flow / "report.json").read_text(encoding="utf-8"))
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Chromium not installed here
            pytest.skip(f"Chromium not available: {exc}")
        pg = browser.new_page(viewport={"width": 1280, "height": 800})
        pg.goto(f.as_uri())
        fid = report["findings"][-1]["id"]
        link = pg.locator(f"main a.x-fnd[href='#{fid}']").first
        if link.count() == 0:
            link = pg.locator("main a.x-fnd").first
        link.scroll_into_view_if_needed()
        y0 = pg.evaluate("window.scrollY")
        href = link.get_attribute("href")
        link.click()
        pg.wait_for_function("h => location.hash === h", arg=href)
        assert pg.locator(".x-back").is_visible()
        top = pg.evaluate("h => document.getElementById(h.slice(1)).getBoundingClientRect().top", href)
        assert 0 <= top < 200                                   # the card is at the top of the view
        assert pg.evaluate("h => document.getElementById(h.slice(1)).classList.contains('x-hit')", href)
        pg.click(".x-back")                                     # the visible way back
        pg.wait_for_function("y => Math.abs(window.scrollY - y) < 3", arg=y0)
        assert pg.locator(".x-back").is_hidden()
        link.click()
        pg.wait_for_function("h => location.hash === h", arg=href)
        pg.go_back()                                            # and the browser's own Back
        pg.wait_for_function("y => Math.abs(window.scrollY - y) < 3", arg=y0)
        pg.go_forward()
        pg.wait_for_function("h => location.hash === h", arg=href)
        browser.close()
