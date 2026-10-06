"""Outside sources in the evidence are links (6 Oct 2026, Malcolm: "outside links in evidence should be clickable").

Every true web address of an outside source (``url_or_citation`` of an evidence ledger entry) is a link that opens in
a new tab with no referrer: in the Evidence tab's row (and so its hover card and side pane, which copy the ledger
entry), in the reference part's ledger entry, in the review's own evidence register and in a finding's evidence line.
It shows the source's title with its host; the full address is its tooltip. A tool call's citation (``mcp:...``) is
shown as the tool and its query, not as an address; a ``javascript:`` or ``data:`` value, or anything else that is not
an ``http(s)`` address with a host, stays text. Offline: synthetic runs only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sit_review_agent.ui import export, outlinks
from test_ui_explain import page, served  # noqa: F401 - fixtures used by name
from test_ui_export_links import _run, text_of

ATTRS = 'target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"'
CALL = 'mcp:mcp-internet-search/search_web?{"fetch_top_n":2,"mode":"answer","query":"pgvector hnsw filtering"}'
LONG = ("https://oneuptime.com/blog/post/2026-02-16-how-to-set-up-microsoft-entra-id-token-lifetime-policies-for-"
        "access-and-refresh-tokens/view")
HOSTILE = ("javascript:alert(document.cookie)", "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
           "JaVaScRiPt:alert(1)", "file:///etc/passwd", "//evil.example/x", "https://", "https://exa mple.org/x",
           "vbscript:msgbox(1)", "https://example.org/\njavascript:alert(1)")


@pytest.mark.parametrize("value", ["https://learn.microsoft.com/a", "http://example.org", "HTTPS://Example.org/x?a=1&b=2"])
def test_a_true_web_address_is_one(value: str) -> None:
    assert outlinks.web_url(value) == value


@pytest.mark.parametrize("value", [*HOSTILE, CALL, "doc:DOC-x#p3/s3", "inference:EV-001", "", None, 42])
def test_anything_else_is_not(value: object) -> None:
    assert outlinks.web_url(value) is None


def test_a_link_opens_a_new_tab_with_no_referrer_and_shows_the_title_and_the_host() -> None:
    url = "https://www.learn.example.org/token-lifetimes?a=1&b=2"
    html = outlinks.source_link(url, 'Token "lifetimes" <b>x</b>')
    assert html.startswith('<a class="x-out" href="https://www.learn.example.org/token-lifetimes?a=1&amp;b=2" '
                           + ATTRS + ' title="https://www.learn.example.org/token-lifetimes?a=1&amp;b=2">')
    assert text_of(html) == 'Token "lifetimes" <b>x</b> · learn.example.org'     # the title escaped, the host after
    assert "<b>" not in html


def test_an_address_with_no_title_is_shown_cut_in_the_middle_with_its_host_first() -> None:
    html = outlinks.source_link(LONG)
    shown = text_of(html)
    assert shown.startswith("oneuptime.com/") and "…" in shown and shown.endswith("refresh-tokens/view")
    assert len(shown) <= outlinks.SHORT
    assert f'title="{LONG}"' in html                                             # the whole address on hover
    assert text_of(outlinks.source_link("https://example.org/a")) == "example.org/a"


def test_a_tool_citation_is_the_tool_and_its_query_in_words_not_a_link() -> None:
    html = outlinks.tool_citation(CALL)
    assert html is not None and "<a" not in html and "href" not in html
    assert text_of(html) == "search_web on mcp-internet-search: “pgvector hnsw filtering” (fetch_top_n 2, mode answer)"
    assert 'title="mcp:mcp-internet-search/search_web?{&quot;fetch_top_n&quot;' in html
    assert outlinks.tool_citation("https://example.org") is None
    bad = outlinks.tool_citation('mcp:s/t?{"query":"<script>x</script>"}')
    assert bad is not None and "<script>" not in bad and "&lt;script&gt;" in bad


def test_the_reviews_own_links_get_the_same_attributes_and_a_bad_one_is_unwrapped() -> None:
    html = ('<p><a href="https://example.org/a">A source</a> <a href="#FND-001">FND-001</a> '
            '<a href="javascript:alert(1)">click</a> <a href="mailto:x@example.org">mail</a></p>')
    out = outlinks.safe_outside_links(html)
    assert (f'<a class="x-out x-out-inline" href="https://example.org/a" {ATTRS} title="https://example.org/a" '
            'data-host="example.org">A source</a>') in out
    assert '<a href="#FND-001">FND-001</a>' in out                              # an in-page link is left alone
    assert "javascript:" not in out and "mailto:" not in out
    assert text_of(out) == text_of(html)                                         # the words are the same


def test_an_address_cited_in_an_evidence_line_becomes_a_link_and_its_words_stay() -> None:
    line = '<li class="x-ev">Evidence EV-002 (external, supports): &quot;q&quot; [https://e.org/p?a=1&amp;b=2]</li>'
    out = export._cited_addresses(line)
    assert f'[<a class="x-out x-out-inline" href="https://e.org/p?a=1&amp;b=2" {ATTRS} ' in out
    assert text_of(out) == text_of(line)
    tool = f'<li class="x-ev">Evidence EV-003 (external, contrary): [{CALL}]</li>'
    assert export._cited_addresses(tool) == tool                                 # a tool citation stays as written


def _tools_run(tmp: Path) -> Path:
    from test_ui_export_links import PAGES
    ledger = [
        {"evidence_id": "EV-001", "source_type": "external", "excerpt": "Lifetimes are set per policy.",
         "url_or_citation": "https://learn.example.org/token-lifetimes", "title": "Token lifetimes",
         "authority": "primary_official", "derived_from": []},
        {"evidence_id": "EV-002", "source_type": "external", "excerpt": "No results.", "url_or_citation": CALL,
         "title": "mcp-internet-search search_web result", "derived_from": []},
        *({"evidence_id": f"EV-{i + 3:03d}", "source_type": "external", "excerpt": "Hostile.", "url_or_citation": v,
           "title": "T", "derived_from": []} for i, v in enumerate(HOSTILE[:2])),
        # one long word each: a tool call's query, and an address with no title
        {"evidence_id": "EV-005", "source_type": "external", "excerpt": "No results.", "derived_from": [],
         "url_or_citation": 'mcp:mcp-internet-search/search_web?{"query":"' + "pgvector_hnsw_" * 20 + '"}'},
        {"evidence_id": "EV-006", "source_type": "external", "excerpt": "A page.", "url_or_citation": LONG,
         "derived_from": []}]
    report = {"metadata": {"documents": [{"doc_id": "DOC-x", "role": "under_review", "title": "X",
                                          "text_path": "text/DOC-x.pages.txt"}]},
              "findings": [{"id": "FND-001", "title": "t", "kind": "gap", "severity": "low", "rank": 1,
                            "evidence": [{"evidence_id": "EV-001", "supports_claim": True}]}],
              "evidence_ledger": ledger}
    md = ("# Design review: X\n\n## Gaps\n\n### FND-001 t\n\n"
          "- Evidence EV-001 (external, supports): \"Lifetimes are set per policy.\" "
          "[https://learn.example.org/token-lifetimes]\n\n"
          "## Evidence register\n\n| ID | Source | Citation |\n|---|---|---|\n"
          "| EV-001 | external | [Token lifetimes](https://learn.example.org/token-lifetimes) via s/t call-0001 |\n")
    return _run(tmp, md, report, PAGES, [])


def test_every_outside_address_of_the_evidence_is_a_link_and_nothing_else_is(tmp_path: Path) -> None:
    """The Evidence tab's rows and the ledger entries they open (the hover card and the pane copy those), and the
    review's own register and evidence line: the https source is a link with the new-tab, no-referrer attributes,
    the tool citation is words, and a javascript: or data: value is text."""
    rd = _tools_run(tmp_path)
    frag = export.review_fragment(rd, pdf_href=None, view="evidence")
    view = frag.split('<div class="rv-view">', 1)[1].split('<div class="rv-store" hidden>', 1)[0]
    rows = dict(re.findall(r'<tr class="ev-row"><td><a [^>]*href="#(EV-\d+)"[^>]*>.*?</a></td>(.*?)</tr>', view))
    where = {k: re.findall(r"<td>(.*?)</td>", v)[1] for k, v in rows.items()}
    assert where["EV-001"].startswith('<span class="x-ev-where"><a class="x-out" '
                                      'href="https://learn.example.org/token-lifetimes" ' + ATTRS)
    assert text_of(where["EV-001"]) == "Token lifetimes · learn.example.org"
    assert "<a" not in where["EV-002"] and text_of(where["EV-002"]).startswith("search_web on mcp-internet-search")
    for eid in ("EV-003", "EV-004"):
        assert "<a" not in where[eid] and "href" not in where[eid], eid
    ledger = frag.split('id="r-ledger"', 1)[1]

    def entry(eid: str) -> str:
        return ledger.split(f'id="{eid}"', 1)[1].split('<div class="x-entry', 1)[0]
    assert f'<a class="x-out" href="https://learn.example.org/token-lifetimes" {ATTRS}' in entry("EV-001")
    assert "Tool call: search_web on mcp-internet-search" in text_of(entry("EV-002"))
    for eid in ("EV-003", "EV-004"):
        assert "x-out" not in entry(eid) and 'href="javascript' not in entry(eid) and 'href="data' not in entry(eid)
    exported = export.export_html(rd, replayed=False)
    outside = re.findall(r'<a [^>]*href="(?!#)([^"]*)"[^>]*>', exported)
    assert sorted(set(outside)) == ["https://learn.example.org/token-lifetimes", LONG], outside
    assert all(ATTRS in a for a in re.findall(r'<a [^>]*href="https:[^>]*>', exported))
    assert exported.count('class="x-out x-out-inline"') == 2                    # the register and the evidence line


def test_the_outside_link_opens_a_new_tab_and_the_register_stays_in_its_column(tmp_path: Path) -> None:
    """In Chromium, on a run with outside evidence: the row's link carries target and rel, sits above the row's own
    link (a click on it is not taken by the row), and a long address keeps the register inside its column."""
    sync_api = pytest.importorskip("playwright.sync_api")
    rd = _tools_run(tmp_path)
    exported = export.export_html(rd, replayed=False)
    frag = export.review_fragment(rd, pdf_href=None, view="evidence")
    css = exported.split("<style>", 1)[1].split("</style>", 1)[0]
    view = frag
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Chromium not installed here
            pytest.skip(f"Chromium not available: {exc}")
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        requests: list[str] = []
        pg.on("request", lambda r: requests.append(r.url))
        pg.set_content(f'<html class="rv"><head><style>{css}</style></head><body style="margin:0">'
                       f'<div style="width:1120px">{view}</div></body></html>')
        a = pg.locator(".rv-view tr.ev-row a.x-out").first
        assert a.get_attribute("target") == "_blank" and a.get_attribute("rel") == "noopener noreferrer"
        assert a.get_attribute("referrerpolicy") == "no-referrer"
        assert a.get_attribute("title") == "https://learn.example.org/token-lifetimes"
        box = a.bounding_box()
        hit = pg.evaluate("([x, y]) => document.elementFromPoint(x, y).closest('a').className",
                          [box["x"] + 4, box["y"] + box["height"] / 2])
        assert hit == "x-out"                                                    # the link, not the row's own
        m = pg.evaluate("""() => { const g = document.querySelector('.rv-view .ev-grid');
          const cells = [...document.querySelectorAll('.rv-view .x-ev-where')]
            .map(e => e.getBoundingClientRect().width);
          return { box: g.getBoundingClientRect().width, table: g.querySelector('table').getBoundingClientRect().width,
                   where: Math.max(...cells) }; }""")
        assert m["table"] <= m["box"] + 1 and m["where"] <= 300.5, m
        assert [u for u in requests if not u.startswith(("about:", "data:"))] == []     # nothing fetched
        browser.close()


def test_the_run_logs_ledger_list_links_the_same_addresses_and_no_others(page) -> None:  # noqa: F811
    """The research panel's "Ledger entries from outside sources" (app.js, the same test as ui/outlinks.py web_url):
    an https source is a link with the same attributes, its host the text; anything else is no link."""
    pg, base, _runs = page
    pg.goto(base + "/")
    pg.wait_for_function("window.SIT !== undefined")
    vals = [*HOSTILE, CALL, "https://www.example.org/a?b=1"]
    got = pg.evaluate("(vals) => vals.map((v) => SIT.webUrl(v))", vals)
    assert got == [None] * (len(HOSTILE) + 1) + ["https://www.example.org/a?b=1"], got
    a = pg.evaluate("""() => { const a = SIT.outLink("https://www.example.org/a?b=1");
        return [a.getAttribute("href"), a.target, a.rel, a.getAttribute("referrerpolicy"), a.title,
                a.textContent]; }""")
    assert a == ["https://www.example.org/a?b=1", "_blank", "noopener noreferrer", "no-referrer",
                 "https://www.example.org/a?b=1", "example.org \u2197"]
