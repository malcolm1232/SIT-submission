# Worker note: the open run's row stays in the rail's Runs list (4 Oct 2026)

## The bug, reproduced
At 1440x900 with run ui-261004-034213-c5cb open (a copy under the worktree's ignored runs/, own server on port 8797), `#rail-runs` measured 0 px tall.
The header "RUNS NONE RUNNING" showed with no row under it.
The list had `flex-shrink: 1000` and `min-height: 0`, so it gave way entirely before the Logs frame shrank.

## The fix
app.css: `#rail-runs` carries the row's own geometry as variables (`--run-pad`, `--run-line`, `--run-meta-line`).
`.rail-run` and its meta line use them, and `#rail-runs:has(.rail-run)` keeps a minimum height of one whole row built from them (46 px, the row measured 46.06 px before).
The Logs frame then gives way below that, down to its 3-line minimum.
app.js: `renderRailRuns` keeps a hand scroll of the list across re-renders and then scrolls the list, and only the list, to the open run's row.
It does this with offset arithmetic and no numeric literals.
`scrollIntoView` was not used because it also scrolls the rail's `.navrail-slot` ancestor, which on every poll would pull the slot away from the Logs panel at short heights.

## Measured (Playwright, the copied run)
- 1440x900, default view: row 420.3 to 466.3 (46 px), list 46 px, slot 384.8 to 744.9; the row is inside the list and the slot.
- 1440x900, Logs frame scrolled into view: row 396.3 to 442.3, still inside the slot; the Logs box is 690.6 to 738.6 with 3 whole lines inside the slot.
- 1280x720, default view: row 420.3 to 466.3, inside the slot (384.8 to 564.9).
- 1280x720, Logs frame scrolled into view: 3 whole log lines, but the row is above the slot. The slot is 180 px tall, which cannot hold both. This was already the case before the change, and the existing Logs test scrolls the slot there too.

## Open for the planner
At 1440x900 with 4 tool servers, the slot needs 384 px for its content and has 360 px (3 headers of 34.5, 4 tools 173, the run row 46, the Logs minimum 56).
The 24 px overflow means the default view shows 1 whole log line until the slot is scrolled.
Scrolled to show the Logs, the RUNS header goes out of view above the row.
Getting all of it on one screen needs 24 px from the rail chrome (for example the rail headers' 14 px top padding), which is a design call this card did not make.

## Test and mutation
New: `test_the_open_runs_row_stays_in_view_beside_the_logs_panel` (tests/test_ui_page.py, 1440x900, four tool servers as in config/tools.yaml, the open run is the last row of the list).
Removing the `:has` min-height rule makes it fail; removing the list scroll line makes it fail; both files were restored and checked with `cmp`.

## Screenshots
docs/transcripts/session6/ui-live/rail_runs_row_1440.png (Logs frame in view) and rail_runs_row_1280.png (default view).
