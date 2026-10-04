# Logs panel: first visible line cut at the top (worker note, 4 Oct 2026)

Branch `s4/logs-clip` from `origin/claude/happy-darwin-d0bl94` at 95e2f0d.
Ruled by the planner under Malcolm's delegation (3 Oct 02:50); the panel came from decision #44.

## Reproduced

Server on port 8853 with `--runs-dir` at a copy of run `ui-261004-034213-c5cb` under the worktree's ignored `runs/`, Playwright Chromium.
Measured by script after the page followed the log to its newest line (`scrollTop = scrollHeight`):

| viewport | panel content box (y) | first visible line (y) | cut |
|---|---|---|---|
| 1440x900 | 669.6 - 738.6 (77 px box) | 659.9 - 675.6 | 9.75 px above the top |
| 1280x720 | 668.6 - 720.6 (60 px box) | 657.6 - 673.4 | 11 px above the top |

At 1280x720 the whole panel also sat below the rail slot's `overflow: hidden` edge (slot ends at y 564.9), so it was not visible at all, and a tool server row was cut in half.

## Cause

`.rail-log` was a flex item of whatever height the rail had left (77 px, 60 px) with 15.75 px lines (10.5 px at line-height 1.5), so its box was never a whole number of lines tall.
Scrolled to the bottom, the newest line ended at the bottom edge and the remainder of the height cut the first visible line at the top.

## Fix (CSS and one wrapper element, no JS change)

- `index.html`: the scroller sits in a `.rail-log-frame`.
- The frame takes the rail's free height (`flex: 1 1 100%`, which keeps the old split where the Runs list gives way first) and is a size container.
- The scroller is `max-height: max(3 * 16px, round(down, 100cqh, 16px))` with 16 px lines and no vertical padding (the frame carries the 2 px / 6 px padding), so the scroll range is a whole number of lines and both edges land on a line edge.
- `scroll-snap-type: y mandatory` with `scroll-snap-align: start` keeps a hand scroll on a line edge too (a 300 px wheel lands at 304 = 19 lines).
- The three-line floor covers one Chromium case seen at 1280x720: when the frame is held at its min-height, `100cqh` resolved to 0 and the scroller was 0 px tall.
- `.navrail-slot` now scrolls (`overflow-y: auto`) when the rail is too short for the tool servers and the panel's minimum, instead of cutting them off.
- `#rail-runs` has `flex-shrink: 1000` so it still gives way first, as its comment says.

## Verified

Same server, after the fix:

| viewport | state | panel content box (y) | first line | last line | lines |
|---|---|---|---|---|---|
| 1440x900 | followed | 668.6 - 732.6 | 668.6 - 684.6 | 716.6 - 732.6 | 4 |
| 1440x900 | scrolled to top | 668.6 - 732.6 | 668.6 - 684.6 | 716.6 - 732.6 | 4 |
| 1280x720 | followed (slot scrolled to the panel) | 510.6 - 558.6 | 510.6 - 526.6 | 542.6 - 558.6 | 3 |
| 1280x720 | scrolled to top | 510.6 - 558.6 | 510.6 - 526.6 | 542.6 - 558.6 | 3 |

A sweep of viewport heights 600 to 1300 px in 7 px steps at widths 1280 and 1440, followed and scrolled to the top, found 0 positions with a cut line or a panel outside the rail.
Screenshots: `docs/transcripts/session6/ui-live/logs_panel_fixed_1440.png`, `logs_panel_fixed_1280.png`.

New test `test_the_logs_panel_shows_whole_lines_at_the_newest_and_at_the_top` in `tests/test_ui_page.py` (60 log lines, both sizes, followed and at the top).
Mutation: removing the `round()` max-height line makes it fail; restored and `cmp` clean.

Gates: ruff `All checks passed!`; full suite `1953 passed, 1 skipped, 2 xfailed`; `sit-review selftest` passed.

## Left as found

At 1440x900 the Runs list is still squeezed to 0 px when a run is open, as before this change (it was 1 px); the open run's row shows only on taller screens.
Whether the open run's row should win over log lines is a design call for the planner.
