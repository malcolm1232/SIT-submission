# Review UI: Stop, clock and limits, per-call view, Logs (worker note)

Worker: SIT FABLE for the planner, 4 Oct 2026, worktree `SIT-wt/ui-live`, branch `s4/ui-live` from `c136554`.
Malcolm's word for this task, 4 Oct 2026 at about 11:55 after his first rehearsal run in the review UI: "What happens if stop run? Timing isn't like PER SECOND. Each 'assess' idk can I either see what it's doing? Or more into the backend or logs? To have more visibility. And why does it cut at 04.25. Can I have more visibility on each of the stages?"
The four changes are the planner's rulings (shot calling delegated to it on 3 Oct 02:50); decision row 43 in `docs/USER_DECISIONS.md` records them.
Not pushed: a separate verifier pushes.

## The four commits

1. `b26f72b` Stop: a confirm step (first click arms the button to "Confirm stop" with "Keep running" beside it, the second posts) and one sentence from the code next to it.
   The sentence, as the page prints it for run `<run_id>`: "Stop sends SIGINT to the dra review process, as Ctrl-C in its terminal does: the run ends with exit 130, the state of the last completed phase is kept in state.json, no report is written, and dra resume <run_id> continues it from there."
   Every clause is from the code: `ui/launcher.py Launcher.stop` sends SIGINT; `cli.py _guarded` turns KeyboardInterrupt into exit `ExitCode.SIGINT` (130); `orchestrator.py` flushes `state.json` on the interrupt and raises `RunInterrupted`; a partial report is written only for a stage crash or when every shard failed (`_run_partial_report`), never on SIGINT; `cli.py _resolve_run_dir` takes a run ID under the run root, where every run started from the page lives.
   The exit code reaches the page as `stop_exit_code` of `GET /meta` (read from `errors.ExitCode.SIGINT`), so `app.js` holds no new numeric literal.
2. `972e75e` Clock and limits: the head clock ticks once a second as the record's last run clock plus the wall seconds since that event arrived, labelled "run clock: last event at mm:ss, plus the seconds since it arrived (this browser's clock)"; it stops with the stream.
   One whole-run axis carries the `run_started` record's limits as markers (stage 1 ends, refine ends, verdict ends, deadline) with the elapsed fill, a live cursor and the next limit named; labels that would overlap step down a row, a label at the end is anchored to its right.
   A fired limit is stated in plain words with the run clock it fired at, from `phase_done.stopped_at_limit`, `stage_limit_passed`, `shard_cut` (n of m drafts kept, m being the distinct `draft_item` records of that call) and `call_cut` (the call, the time, the stage's limit, the finished items kept).
   On the demo run the two notes read "Stage 1 limit 04:25 reached; assess shard 3 (requirements and consistency) ended there at 04:25, 5 of 13 drafts kept." and "Refine: the model call llm-0013 was cut at 07:45 (refine ends by 07:45); 4 finished item(s) kept." That is the answer to "why does it cut at 04.25": the demo profile's stage 1 limit is 04:25 (`stage_limits_s.stage_1_end` 265 s), and the page now says so where it happens.
3. `d06de9b` Per-stage, per-shard live view: each track row expands (a chevron button on its name) to its model calls keyed by `call_id`, each with its purpose, the run clock it opened at, the latest `call_status` fields (label, reasoning tokens, items, chars, as of the record's clock), its close (ok, cut with the kept count, or the failed outcome) and the draft items streamed from it (severity, kind, title). Titles only: the record carries no model text to the page.
4. (this commit) Logs: a Logs panel in the rail tails the open run's `progress.log` through the new read-only route `GET /runs/<id>/log` (`rundata.tail_log`: the last 200 complete lines, then `?after=<byte offset>` for what was appended since; a half-written last line waits for its newline; an offset past the end starts over). The page re-reads it on the one-second tick while the run is live and once more when the stream ends.

## The honesty contract, rewritten not deleted

`tests/test_ui_honesty.py`:
- `test_no_fake_progress_or_completion_estimate` now requires the new legend sentence ("Event times are the record's own run clock; the head clock and the axis cursor add only the seconds since the last event arrived, counted on this browser's clock, and the limit markers are the run's recorded limits.") and that no percentage is visible: the two `"%"` in the script go into styles only.
- `test_the_clock_adds_only_the_wall_seconds_since_the_last_event` (was `test_the_bar_is_elapsed_over_the_limit_and_nothing_else`) pins the track bars to the record's clock as before and pins the one browser-clock read: `(Date.now() - S.lastAt) / 1000` only while `isLive(m)`, `Date.now` twice in code, `setInterval(tick, 1000)` once, no `setTimeout`, `new Date` or `performance.now`; the axis span, markers and cursor expressions are pinned to the record.
- `JS_NUMBERS` gains `1000` (milliseconds per second).
- The two browser checks read the record's clock from `#clock-last` and bound the big clock above it.

## Gates (exact output lines)

- `ruff check agent harness tests`: `All checks passed!` after every change.
- Full suite from the worktree at the last change: `1931 passed, 1 skipped, 2 xfailed in 267.74s (0:04:27)` (1925 at `c136554` plus the six tests below).
- `sit-review selftest`: `selftest passed in 0.4 s`.
- `uptime` and `memory_pressure` before each test run: 5-minute load between 4.9 and 8.7, free memory 42 to 58 percent.

New tests (six): `tests/test_ui_page.py` `test_stop_takes_two_clicks_and_states_what_the_signal_does`, `test_the_head_clock_ticks_only_the_seconds_since_the_last_event_and_stops_with_the_stream`, `test_a_fired_limit_is_stated_in_plain_words`, `test_a_stage_row_expands_to_its_calls_with_the_latest_status_and_the_drafts_so_far`; `tests/test_ui_server.py` `test_meta_states_the_stop_exit_code_from_the_cli`, `test_the_log_route_tails_progress_log_and_follows_it`.

## The replay, end to end

My own server: `dra ui --port 8799 --runs-dir runs/ui-live-verify` (killed by pid at the end; 8791 untouched).
`runs/ui-live-verify/` (ignored) holds a `cp -R` of `~/Desktop/SIT-wt/demo4/runs/ui-261004-034213-c5cb` (455 progress records, 425 console lines, the same count as `progress.log`; the original was not modified and no record content was printed).
A Playwright script wrote a fresh `ui-261004-replay/` (the copy's `ui/launch.json`, then `progress.jsonl` and `progress.log` appended line by line at 0.12 s) while the page was open, and read the page at three points:
- mid stage 1 (record 120): head clock `01:23` against `last event at 01:22`; axis note "elapsed 01:23 of 09:00 · next limit: stage 1 ends 04:25 ..."; two rows expanded to their calls; Logs panel "last 117 lines"; the Stop button drawn with its sentence;
- after the stage 1 limit (record 352): the amber note "Stage 1 limit 04:25 reached; assess shard 3 (requirements and consistency) ended there at 04:25, 5 of 13 drafts kept."; axis "next limit: refine ends 07:45";
- the end: "Run finished: completed degraded, exit 0 · 8:29 on the run clock · ≥ $7.37 · verdict fit with conditions, 52 findings."; clock `08:28` labelled "run clock, as of the last event"; `SIT.state.tick` null; the Stop control gone; Logs "last 200 of 425 lines"; no page error.
The finished copy's Run log tab shows the same two notes and the refine calls "closed at 06:57" and "cut at 07:45, 4 kept".

Screenshots (full page, 1440 wide) under `docs/transcripts/session6/ui-live/`: `live_stage1_mid_replay.png`, `live_after_stage1_limit.png`, `finished_replay_end.png`, `finished_copy_run_log_tab.png`, `finished_copy_review.png`, `axis_labels_two_rows.png`.

## Found along the way

- A record repeated for the same call and index (the cut shard's `draft_item` 1 to 5 appear twice in the demo stream) is one draft on the page: the "n of m kept" count uses the distinct set, as the drafts list already did.
- A run opened before `progress.jsonl` exists is followed only when the server owns the live process; a replay by file must write its first record before the page opens (the script does; nothing changed in the product).
- The stray `inspect.py` in the shared scratchpad root shadows the standard library for any script run from there; my script lives in a subfolder.
