# Worker note: the export bundle (decision #43), 2026-10-04

Brief: the planner's ruling on the owner's words about "Download review" (one page is too much): both a sidebar on the single HTML and a bundle of part files.
Branch `s4/export-bundle` from `origin/claude/happy-darwin-d0bl94` at fccf6d7.

## What changed

- `agent/sit_review_agent/ui/export.py`: `split_report` renders report.md once with markdown-it and cuts the token stream at each top-level `## ` heading, so the preamble (title and verdict table) and the sections joined are byte for byte `review_html(report.md)`.
  `GROUPS` maps the report's headings to eight parts; "Risk register" (the risk_register template) is placed with Risks; any other heading (Executive summary, the delta heading, the appendix) joins the part of the nearest named heading before it, or the first part after it when none comes before.
  `export_html` now draws the sidebar page (one fixed inline script, `NAV_JS`; nothing hidden until it runs); `part_links` sets the prefix of the "this section only" links (`"export/"` on the server, `""` in the zip, `None` for the emailed file, which then has no part links).
  `export_part` gives one standalone part (no script) or `index.html`; `export_zip` gives the bundle.
- `agent/sit_review_agent/ui/server.py`: `run_export` serves `export.html` (sidebar page, inline), `export.html?download=1` and `export.zip` (the zip, `<run>_review.zip`), and `export/<part>` (a part, or `export/index.html`, the page whose links sit beside the parts); two route lines, both to `run_export`. `run_email` is unchanged and still attaches the single page.
- `agent/sit_review_agent/ui/static/export.css`: the sidebar in the review page's rail idiom (dark band, pill items, mono group label, tokens only, no transition); one column under 820 px with the heading lists hidden; the sidebar is not printed.
- Tests: `tests/test_ui_export_bundle.py` (9 tests: the cut joins to the rendered report; the eight parts together equal the full page section for section and the chat transcript sits only in Traceability; each renderer heading is mapped once; the positional rule; the sidebar lists every heading once; the zip holds exactly the eleven names with report.md and report.json byte equal; the routes; each finding in exactly one part with its report.json text; the sidebar in Chromium with script and every section without script). `tests/test_ui_outputs.py`: the no-script test now allows exactly the one fixed script on the page (parts have none), the download test and the browser test expect the zip.

## Browser check

Own server `dra ui --port 8813 --runs-dir runs` on a copy of `demo4/runs/ui-261004-034213-c5cb` (cp -R, original untouched; llm.jsonl and tools.jsonl not read), driven by a Playwright script; killed by pid after.
Clicking each sidebar part showed only its headings (1: Design intent, Fitness for purpose; 2: Strengths, Areas where no change is needed; 3: Risks; 4: Gaps; 5: Ambiguities, Unresolved assumptions; 6: Validation needs, Recommended refinements; 7: Unresolved issues and next steps, Evidence limitations; 8: Evidence register, Review coverage, Run details), "All sections" showed 15 of 15, no page error, no horizontal scroll at 390 px.
The Download control on the review page saved `ui-261004-034213-c5cb_review.zip` holding index.html, 01_summary.html ... 08_traceability.html, report.md, report.json.
Screenshots in `docs/transcripts/session6/export-bundle/`: `0_all_sections.png`, `1_summary_view.png`, `3_risks_view.png`, `8_traceability_view.png`, `part_03_risks.png`, `mobile_390.png`.

## Gates

`ruff check agent harness tests`: All checks passed. Full suite: 1934 passed, 1 skipped, 2 xfailed. `sit-review selftest`: selftest passed.

## Not done, and why

- `ui/static/app.js` (out of bounds for this worker, another worker edits it) still labels the control "Download review (HTML, N KB)" and its help line says "One file, no script"; both are now wrong (it saves a zip of eleven files, and the page has one fixed script). A follow-up after the merge should change those two strings, and `/outputs` (`run_outputs`, also left alone) still reports the single page's size and name.
