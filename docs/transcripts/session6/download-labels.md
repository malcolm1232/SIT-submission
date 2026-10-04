# Download control text after the bundle (decision #43), 4 Oct 2026

Worker note for branch `s4/download-labels`, based on `baf9196`.

## What changed

- `ui/server.py` `run_outputs`: the export entry now describes the zip that `export.html?download=1` saves.
  It builds the bundle with `export.export_zip` exactly as `run_export` does and reports `name` (`<run>_review.zip`), `files` (`len(export.bundle_names(rd))`, 11 with both reports) and `size` in KB.
  The size can differ from the downloaded zip by a few bytes, since each build stamps its own export time.
  Building it took 0.115 s on the 30-page demo run (about 270 KB), so the size stays.
- `ui/static/app.js`: the label reads `Download review (zip, N KB)`.
  The help line reads: "A zip of one review page with a sidebar, whose one script only shows and hides sections, the eight parts as separate files, report.md and report.json, nothing loaded from the network." with the existing replayed and chat clauses appended when they apply.
- `ui/static/index.html`: the initial label reads `Download review (zip)`.
- The email help line ("Sends the HTML file and report.md as attachments") is left as it is: email still attaches the single sidebar page.
- Tests: `tests/test_ui_outputs.py` gains `test_outputs_reports_the_bundle_the_download_saves` (name, 11 files, size within 1 KB of the real download), and the browser test pins the exact label and the help line.
- Flake fixed on the way: `tests/test_ui_honesty.py::test_the_rail_shows_the_stream_state_and_the_recorded_servers_and_never_probes` failed once in the full suite under load (`assess · 01:... 2 calls open` instead of `refine · ... 1 call open`), because it read the rail before the replayed stream was fully reduced.
  It now waits for the end state before asserting; it passed alone 3 of 3 before the fix and the full suite passed after it.

## Screenshot of the Run log tab

Own server on port 8797 with `--runs-dir` at a copy of `ui-261004-034213-c5cb` under the worktree's ignored `runs/`, Chromium at 1440x900.

- `ui-live/runlog_top_viewport.png`: viewport at scroll 0.
- `ui-live/runlog_scrolled_viewport.png`: viewport scrolled 200 px so all six assess rows show.
- `ui-live/download_zip_label.png`: the head with the new label and help line (271 KB).

Verdict: the overlap in `finished_copy_run_log_tab.png` is a capture artifact, not a CSS defect.
In both viewport shots the sticky top bar (`header.topbar`, `position: sticky; top: 0; z-index: 2`) sits at y 0 to 56 and the rail (`.navrail-inner`, sticky, logo `.navrail-brand` at y 16 to 64) stays in the rail column; nothing overlaps content.
A full-page capture taken while scrolled to 1500 px reproduces the old picture exactly: the top bar and the rail logo are drawn at y 1500 over the assess and draft-findings rows, because Chromium paints sticky elements at their current scroll position in a full-page capture.

One small nit seen, not fixed here: in the rail's LOGS panel the first visible line is clipped by half a line at the top (y about 668 in both viewport shots).
