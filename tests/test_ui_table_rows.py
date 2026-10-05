"""Table rows rebuilt for the reader (``ui/tablerows.py``, 6 Oct 2026): a document id whose line sits in a table
leads with its whole row, rebuilt from the PDF's table layout, and the extracted text it sits in is marked as a
whole; without the PDF only an unambiguous single-line row is rebuilt from the text, else a plain note says the
id sits in a table. Nothing is guessed.

The unit tests use made-up tables and page text in the layout the extractor produces. The tests on the lab's
sample document run only where a finished run of it exists on this computer (it is not in the repository).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from sit_review_agent.ui import export, tablerows
from sit_review_agent.ui.xref import _normalise

# ------------------------------------------------------------------ a made-up table in the extractor's layout

TABLE = [
    ["", None, None, "", None, None],
    ["Q1", None, None, "", "Alpha rule is the first one - it holds the line. Clashes are settled in favour", ""],
    [None, None, None, None, "of the alpha rule.", None],
    ["", None, None, "", None, None],
    ["", None, None, "", None, None],
    ["Q2", None, None, "", "Beta rule keeps things private by default, for each per-", ""],
    [None, None, None, None, "learner record at the break.", None],
    ["", None, None, "", None, None],
    ["", "Q3", "", "", "Gamma rule fits on one line.", ""],
    ["", None, None, "", None, None],
]
PAGE = ("Intro line of the page.\n"
        "Alpha rule is the first one - it holds the line. Clashes are settled in favour\n"
        "Q1\n"
        "of the alpha rule.\n"
        "Beta rule keeps things private by default, for each per-\n"
        "Q2\n"
        "learner record at the break.\n"
        "Q3 Gamma rule fits on one line.\n"
        "Closing prose after the table.\n")


def rows() -> list[tablerows.Row]:
    return tablerows._logical_rows(TABLE, 6)


def placed(row: tablerows.Row, page: str = PAGE) -> tuple[int, int] | None:
    norm, nmap = _normalise(page)
    return tablerows.place(row, page, norm, nmap, (0, len(page)), [r.key for r in rows()])


def test_logical_rows_join_the_wrapped_cells_into_one_sentence() -> None:
    got = {r.key: r.sentence for r in rows()}
    assert got == {
        "Q1": "Q1 - Alpha rule is the first one - it holds the line. Clashes are settled in favour of the alpha rule.",
        "Q2": "Q2 - Beta rule keeps things private by default, for each per-learner record at the break.",
        "Q3": "Q3 - Gamma rule fits on one line.",
    }
    assert all(r.source == "pdf" and "—" not in r.sentence for r in rows())


def test_a_row_is_placed_over_exactly_its_lines_in_the_page_text() -> None:
    by = {r.key: r for r in rows()}
    s, e = placed(by["Q1"])
    assert PAGE[s:e] == ("Alpha rule is the first one - it holds the line. Clashes are settled in favour\nQ1\n"
                         "of the alpha rule.")
    s, e = placed(by["Q3"])
    assert PAGE[s:e] == "Q3 Gamma rule fits on one line."


def test_a_row_whose_pieces_straddle_another_key_or_split_a_word_is_not_placed() -> None:
    by = {r.key: r for r in rows()}
    # Q1's tail moved below Q2's id line: the pieces now enclose another row's key
    moved = PAGE.replace("of the alpha rule.\n", "").replace("learner record at the break.\n",
                                                             "learner record at the break.\nof the alpha rule.\n")
    assert placed(by["Q1"], moved) is None
    # a piece that starts inside a word (a cell cut mid-word) is not found
    cut = tablerows.Row(6, "Q3", ["amma rule fits on one line."], ["Q3", "amma rule fits on one line."])
    assert placed(cut) is None


def _line(text: str, ident: str) -> tuple[int, int]:
    m = re.search(rf"(?m)^{ident}(?=[ \t]|$)", text)
    return m.start(), text.find("\n", m.start())


def test_the_text_only_row_is_rebuilt_only_when_it_cannot_be_wrong() -> None:
    clear = "R1 First rule on one line.\nR2 Second rule on one line.\nR3 Third rule on one line.\n"
    row = tablerows.text_row(clear, _line(clear, "R2"), "R2", 4)
    assert row is not None and row.sentence == "R2 - Second rule on one line." and row.source == "text"
    # the line above is another row's wrapped text: R2's row may own it, so nothing is rebuilt
    unclear = "R1 First rule on one line.\nwrapped words of some row\nR2 Second rule.\nR3 Third rule.\n"
    assert tablerows.text_row(unclear, _line(unclear, "R2"), "R2", 4) is None
    # the id alone on its line: its words are elsewhere, so nothing is rebuilt
    assert tablerows.text_row(PAGE, _line(PAGE, "Q1"), "Q1", 6) is None
    assert tablerows.is_table_line(PAGE, _line(PAGE, "Q1"), "Q1", (0, len(PAGE)))
    prose = "Intro.\nQ7 is mentioned at the start of a sentence here.\nMore prose.\n"
    assert not tablerows.is_table_line(prose, _line(prose, "Q7"), "Q7", (0, len(prose)))


def test_same_words_keeps_a_registry_statement_from_being_repeated_by_its_row() -> None:
    assert tablerows.same_words("Q3 - Gamma rule fits on one line.", "Gamma rule fits on one line")
    assert not tablerows.same_words("Q3 - Gamma rule fits on one line.", "The gamma rule is short and kept apart.")


def test_an_absent_or_unreadable_pdf_gives_no_rows(tmp_path: Path) -> None:
    assert tablerows.pdf_rows(None) == {} and tablerows.pdf_rows(tmp_path / "missing.pdf") == {}
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    assert tablerows.pdf_rows(bad) == {}


# ------------------------------------------------------------------ on the lab's sample document, where it exists

RUN_ID = "ui-261005-125426-adaa"


def sample_run() -> Path | None:
    for base in sorted((Path.home() / "Desktop" / "SIT-wt").glob(f"*/runs/{RUN_ID}")):
        if (base / "report.md").is_file() and (base / "ui" / "input" / "sit_sample_v1.pdf").is_file():
            return base
    return None


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    src = sample_run()
    if src is None:
        pytest.skip("the lab's sample run is not on this computer")
    dst = tmp_path / "runs" / RUN_ID
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("llm.jsonl", "checkpoints", "shards", "state.json",
                                                            "progress.*", "ledger.jsonl"))
    return dst


def _run(rd: Path, pdf: Path | str | None = export.AUTO) -> export._Run:
    r = export._Run(rd, replayed=False, exported_at=None, pdf_href=None, pdf=pdf)
    r.index_page()
    return r


def test_p1_to_p5_lead_with_their_whole_row_from_the_pdf(sample: Path) -> None:
    r = _run(sample)
    idx = r.index
    assert idx.pdf is not None                                   # the hash matches, so the PDF is used
    by = {c.row.key: c for c in idx.chrome if c.row is not None and c.row.page == 6}
    text = idx.doc.text
    for k in ("P1", "P2", "P3", "P4", "P5"):
        c = by[k]
        assert c.row.source == "pdf" and c.span == c.row.span
        lines = text[c.span[0]:c.span[1]].split("\n")
        assert k in lines                                        # the id's own line is inside the marked row
        words = " ".join(ln for ln in lines if ln != k)          # the row's sentence is exactly its lines' words
        assert c.row.sentence == f"{k} - " + tablerows.plain(words)
    assert "Conflicts are resolved in favour of the learner namespace" in by["P1"].row.sentence
    assert ("P1", 6, True, "none") in idx.coverage
    page = r.index_page()
    assert "Table row on page 6, rebuilt from the PDF&#x27;s table layout" in page


def test_without_the_pdf_or_with_a_hash_mismatch_the_note_is_shown_and_no_row_is_guessed(sample: Path) -> None:
    r = _run(sample, pdf=None)
    assert all(c.row is None and c.note for c in r.index.chrome)
    assert {fb for _, _, _, fb in r.index.coverage} == {"table note (row not rebuilt)"}
    page = r.index_page()
    assert tablerows.TABLE_NOTE.replace("'", "&#x27;") in page and "rebuilt from the PDF&#x27;s table" not in page
    # the PDF beside the run but not the one the manifest recorded: AUTO does not use it
    man = json.loads((sample / "manifest.json").read_text(encoding="utf-8"))
    man["extra"]["doc"]["sha256_pdf"] = "0" * 64
    (sample / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    r = _run(sample)
    assert r.index.pdf is None and not any(c.row is not None for c in r.index.chrome)


def test_the_export_text_stays_the_reports_words_with_the_rows(sample: Path) -> None:
    from test_ui_export_links import main_of, text_of

    page = export.export_html(sample, replayed=False)
    md = (sample / "report.md").read_text(encoding="utf-8")
    assert text_of(main_of(page)) == text_of(export.review_html(md))
    ids = re.findall(r'\sid="([^"]+)"', page)
    assert len(ids) == len(set(ids))
    for marks in re.findall(r'class="doc-row[^"]*" data-marks="([^"]+)"', page):
        assert all(f'id="{m}"' in page for m in marks.split())     # every row names marks that exist


def test_hovering_p1_shows_its_row_first(sample: Path, tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    f = tmp_path / "index.html"
    f.write_text(export.export_html(sample, replayed=False), encoding="utf-8")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Chromium not installed here
            pytest.skip(f"Chromium not available: {exc}")
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(f.as_uri())
        link = pg.locator("#s-design-intent a.x-docid", has_text=re.compile(r"^P1$")).first
        link.scroll_into_view_if_needed()
        pg.evaluate("window.scrollBy(0, -200)")
        box = link.bounding_box()
        pg.mouse.move(box["x"] + 3, box["y"] + box["height"] / 2)
        pg.wait_for_selector(".x-pop:not([hidden])")
        first = pg.locator(".x-pop").inner_text().strip().split("\n")[0]
        assert first.startswith("P1") and "Conflicts are resolved in favour of the learner namespace" in first
        pg.mouse.move(2, 2)
        pg.wait_for_selector(".x-pop", state="hidden")
        link.click()
        pg.wait_for_selector(".x-pane:not([hidden])")
        assert pg.locator(".x-pane-body .doc-row").count() == 1
        assert pg.locator(".x-pane-body .doc-row-text").inner_text().startswith("P1 - ")
        browser.close()
