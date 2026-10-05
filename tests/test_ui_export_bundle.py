"""The export bundle (decision #43, 2026-10-04; cross-linked 5 Oct 2026): the single page with a sidebar of eight
parts and a Reference part of reference material, and the zip that holds it with the reviewed PDF (when the run
vouches for it), ``report.md`` and ``report.json``. The part files are gone: a part file had no sidebar, and a
reader took the jump to one for the sidebar closing. Offline on the committed run ``docs/live_runs/ui_flow_1``;
the browser tests run in Chromium where Playwright has it."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from sit_review_agent.report.render import SECTION_ORDER
from sit_review_agent.ui import export
from sit_review_agent.ui.server import build_app
from test_ui_outputs import FLOW, browser_page, copy_run, make_state, one_line, parse  # noqa: F401

SEC_RE = re.compile(r'<section class="sec" data-g="(\d)" id="([^"]+)">(.*?)</section>', re.S)


@pytest.fixture
def flow_runs(tmp_path: Path) -> Path:
    runs = tmp_path / "runs"
    copy_run(FLOW, runs / "ui_flow_1")
    return runs


def wait_active(pg, g: str) -> None:
    """Wait until the sidebar item ``g`` is the active one. The page's click and hashchange handlers set the
    active item, the hidden sections and the URL in one task, so once this holds the whole state can be read;
    reading right after a click raced that task under load (seen once in a full suite)."""
    pg.wait_for_function("(g) => { const a = document.querySelectorAll('.toc-item.active');"
                         " return a.length === 1 && a[0].getAttribute('data-g') === g; }", arg=g)


def sections(html: str) -> list[tuple[str, str, str]]:
    return SEC_RE.findall(html)


def zip_of(rd: Path, pdf: Path | None = None) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(export.export_zip(rd, replayed=False, exported_at="2026-10-04T04:00:00Z",
                                                      pdf=pdf))) as z:
        return {n: z.read(n) for n in z.namelist()}


# ------------------------------------------------------------------ D1: the split loses no content


def test_the_cut_report_joined_is_the_rendered_report(flow_runs: Path) -> None:
    md = (flow_runs / "ui_flow_1" / "report.md").read_text(encoding="utf-8")
    pre, secs = export.split_report(md)
    assert pre + "".join(s.html for s in secs) == export.review_html(md)
    assert pre.startswith("<h1>") and "<h2>" not in pre        # the title and the verdict table stay on top
    assert all(s.html.startswith("<h2>") and s.html.count("<h2>") == 1 for s in secs)


# ------------------------------------------------------------------ D2: every heading in exactly one group


def test_the_group_map_names_each_renderer_heading_once() -> None:
    named = [h for _, _, heads in export.GROUPS for h in heads]
    assert len(named) == len(set(named))
    rendered = {h for key, h in SECTION_ORDER if key not in ("header", "delta")}
    assert rendered <= set(named)                                     # every fixed heading of render.py is placed
    assert not hasattr(export, "PART_NAMES") and not hasattr(export, "export_part")   # no part files any more


def test_a_heading_outside_the_map_joins_the_nearest_group_before_it() -> None:
    md = "\n\n".join([
        "# Design review: x", "| | |\n|---|---|\n| Verdict | **fit** |",
        "## Executive summary", "a",
        "## Design intent", "b", "## Fitness for purpose", "c", "## Risk register", "d", "## Risks", "e",
        "## Unresolved issues and next steps", "f", "## Changes since the previous version", "g",
        "## Evidence limitations", "h", "## Run details", "i",
        "## Appendix: findings below the reporting threshold (low)", "j", "## Run details", "k"])
    pre, secs = export.split_report(md)
    got = [(s.heading, s.group + 1) for s in secs]
    assert got == [("Executive summary", 1), ("Design intent", 1), ("Fitness for purpose", 1), ("Risk register", 3),
                   ("Risks", 3), ("Unresolved issues and next steps", 7),
                   ("Changes since the previous version", 7), ("Evidence limitations", 7), ("Run details", 8),
                   ("Appendix: findings below the reporting threshold (low)", 8), ("Run details", 8)]
    assert [s.sid for s in secs][-1] == "s-run-details-2"              # ids stay unique
    assert pre + "".join(s.html for s in secs) == export.review_html(md)


def test_the_sidebar_lists_every_heading_once_under_its_group(flow_runs: Path) -> None:
    rd = flow_runs / "ui_flow_1"
    html = export.export_html(rd, replayed=False, pdf_href="doc.pdf")
    nav = html.split('<nav class="toc"', 1)[1].split("</nav>", 1)[0]
    _, secs = export.split_report((rd / "report.md").read_text(encoding="utf-8"))
    listed = re.findall(r'<li><a href="#([^"]+)" data-g="(\d)">', nav)
    refs = re.findall(r'<section class="sec x-ref" data-g="9" id="([^"]+)">', html)
    assert refs[:2] == ["r-howto", "r-registry"] or refs[:1] == ["r-howto"]
    assert listed == [(s.sid, str(s.group + 1)) for s in sorted(secs, key=lambda s: s.group)] + [("s-chat", "8")] \
        + [(r, "9") for r in refs]
    labels = re.findall(r'<span class="label">([^<]+)</span>', nav)
    assert labels == ["All sections", *(label for _, label, _ in export.GROUPS), export.REF_LABEL]
    for page in (html, export.export_html(rd, replayed=False)):
        assert "this section only" not in page and "toc-file" not in page    # a part link read as the sidebar closing


# ------------------------------------------------------------------ D3: the zip and the routes


def test_the_zip_holds_the_page_the_pdf_when_vouched_for_and_the_run_files(flow_runs: Path, tmp_path: Path) -> None:
    rd = flow_runs / "ui_flow_1"
    files = zip_of(rd)
    assert list(files) == ["index.html", "report.md", "report.json"] == export.bundle_names(rd)
    assert files["report.md"] == (FLOW / "report.md").read_bytes()
    assert files["report.json"] == (FLOW / "report.json").read_bytes()
    index = files["index.html"].decode("utf-8")
    assert "document.pdf" not in index                       # no PDF beside it: no link to one
    pdf = tmp_path / "reviewed.pdf"
    pdf.write_bytes(b"%PDF-1.4 stand-in\n")
    files = zip_of(rd, pdf)
    assert list(files) == ["index.html", export.PDF_NAME, "report.md", "report.json"] == export.bundle_names(rd, pdf)
    assert files[export.PDF_NAME] == pdf.read_bytes()
    index = files["index.html"].decode("utf-8")
    if 'class="doc-page"' in index:                          # the run has its extracted text: pages link the PDF
        assert re.search(r'class="x-pdf" href="document\.pdf#page=\d+"', index)


def test_the_routes_serve_the_page_and_the_bundle_and_no_part(flow_runs: Path) -> None:
    client = TestClient(build_app(make_state(flow_runs)))
    page = client.get("/runs/ui_flow_1/export.html")
    assert page.status_code == 200 and page.headers["content-disposition"].startswith("inline")
    assert '<nav class="toc"' in page.text and "this section only" not in page.text
    for url in ("/runs/ui_flow_1/export.zip", "/runs/ui_flow_1/export.html?download=1"):
        res = client.get(url)
        assert res.status_code == 200 and res.headers["content-type"] == "application/zip"
        assert res.headers["content-disposition"] == 'attachment; filename="ui_flow_1_review.zip"'
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            assert z.namelist()[0] == "index.html" and z.namelist()[-2:] == ["report.md", "report.json"]
    for bad in ("01_summary.html", "03_risks.html", "index.html"):
        assert client.get(f"/runs/ui_flow_1/export/{bad}").status_code == 404, bad
    assert client.get("/runs/nope/export.zip").status_code == 404
    (flow_runs / "ui_flow_1" / "report.md").unlink()
    assert client.get("/runs/ui_flow_1/export.zip").status_code == 404


# ------------------------------------------------------------------ D4: the finding text, section by section


def test_each_finding_is_in_exactly_one_section_with_its_report_json_text(flow_runs: Path) -> None:
    rd = flow_runs / "ui_flow_1"
    html = export.export_html(rd, replayed=False)
    report = json.loads((rd / "report.json").read_text(encoding="utf-8"))
    secs = {sid: parse(body) for _, sid, body in sections(html) if not sid.startswith(("r-", "doc"))}
    for f in report["findings"]:
        head = f"{f['id']} {one_line(f['title'])}"
        where = [sid for sid, doc in secs.items() if head in doc.texts("h3")]
        assert len(where) == 1, (f["id"], where)
        assert one_line(f["statement"]) in secs[where[0]].texts("p"), f["id"]


# ------------------------------------------------------------------ D5: in a browser, with and without script


def test_the_sidebar_in_a_browser_and_every_section_without_script(browser_page) -> None:  # noqa: F811
    pg, ctx, base, runs, fake, state = browser_page
    _, secs = export.split_report((runs / "ui_flow_1" / "report.md").read_text(encoding="utf-8"))
    url = base + "/runs/ui_flow_1/export.html"
    pg.goto(url)
    n_ref = pg.locator(".sec.x-ref").count()
    visible = pg.locator(".sec:visible")
    assert visible.count() == len(secs) + 1 + n_ref                      # All sections, the chat and the reference
    assert pg.locator(".toc-item.active .label").inner_text() == "All sections"
    pg.click(".toc-item[data-g='3']")
    wait_active(pg, "3")
    assert [one_line(t) for t in pg.locator(".sec:visible h2").all_inner_texts()] == ["Risks"]
    assert pg.locator(".pre h1").is_visible() and pg.locator(".pre table").is_visible()   # title and verdict stay
    assert pg.url.endswith("#g3")
    pg.click(".toc-item[data-g='2']")
    wait_active(pg, "2")
    assert [one_line(t) for t in pg.locator(".sec:visible h2").all_inner_texts()] == \
        ["Strengths", "Areas where no change is needed"]
    pg.click(".toc-heads a[href='#s-evidence-register']")                 # a heading opens its part
    pg.wait_for_function("!document.getElementById('s-evidence-register').closest('.sec').hidden"
                         " && document.getElementById('s-risks').closest('.sec').hidden")
    assert pg.locator("#s-evidence-register").is_visible() and pg.locator("#s-risks").is_hidden()
    pg.click(".toc-item[data-g='all']")
    wait_active(pg, "all")
    assert visible.count() == len(secs) + 1 + n_ref
    pg.goto(url + "#g4")                                                # a same-page hash: the route runs on hashchange
    wait_active(pg, "4")
    assert [one_line(t) for t in pg.locator(".sec:visible h2").all_inner_texts()] == ["Gaps"]
    assert pg.locator(".toc-file").count() == 0                         # no "this section only" link
    # without script: nothing is hidden and every section, the chat transcript and the reference show
    noscript = ctx.browser.new_context(java_script_enabled=False)
    p2 = noscript.new_page()
    p2.goto(url)
    assert p2.locator(".sec").count() == len(secs) + 1 + n_ref
    assert p2.locator(".sec:visible").count() == len(secs) + 1 + n_ref
    assert p2.locator(".toc-item.active").count() == 0
    noscript.close()
