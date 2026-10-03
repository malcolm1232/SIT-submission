# Edit log: a longer --deadline scales the stage limits up (2026-10-03)

Branch `s4/limits` from `ab11a0a`.

## Defect

`effective_stage_limits` (`agent/sit_review_agent/llm/runtime.py`) scaled the three stage limits only when `--deadline` was at or below `verdict_end`.
Above it the limits stayed as configured, so `--profile demo --deadline 900` kept 265 / 465 / 530 s and the added 360 s idled after the verdict limit.
The runbook's `--deadline 900` fallback in section 5 was therefore wrong.

## Edits

1. `agent/sit_review_agent/llm/runtime.py`: `planned = max(refine_end + report_reserve_seconds, verdict_end + 1)` is computed first.
   The limits are kept as set only when `verdict_end < deadline <= planned`.
   Above `planned` they scale by `deadline / planned`, with the same floor rounding as the scale-down case.
   The announcement reads "deadline N s is longer than the P s run ... scaled up by N/P to a / b / c s".
   It reaches the progress log and `progress.jsonl` through the existing path (`deadline_warnings` emits a `deadline_warning` event; `run_started` carries `stage_limits_s` and `stage_limits_scaled`).
   Docstrings of `RunDeadline` and `orchestrator._run_started` now say "differs from their run length" instead of "below".
2. `tests/test_runtime_policies.py`: new test `test_a_deadline_above_the_planned_run_scales_the_limits_up_and_says_so`.
   It covers demo 540 s (unchanged, quiet), 900 s (441 / 775 / 883 s, announced, first attempt bounded at 441 s), 3600 s (1766 / 3100 / 3533 s), and the default profile at 3600 s (unchanged) and 7200 s (5640 / 6840 / 7080 s).
   The existing 300 s test (147 / 258 / 294 s) and the 531 s edge (kept as set) are unchanged and pass.
3. `docs/DEMO_DAY_RUNBOOK.md` sections 4 and 5, `docs/DEMO_DAY_SCRIPT.md` (the stage-limit row, the paragraph after the table, the `not_assessed` line), `config/stop_rules.yaml` (one comment line), `config/profiles/demo.yaml` (three comment lines rewritten in place, so the line count stays the same and lines 27 and 42-44 do not move).

## Deviation from the brief: the cap

The brief asked to cap `verdict_end` at `deadline - report_reserve_seconds`.
That cap contradicts the shipped profiles: the demo profile's own `verdict_end` is 530 s, above 540 - 75 = 465 s, because the report reserve covers the verdict call and render after `refine_end`.
Applied literally, it would cut the verdict window at 900 s from 108 s to 50 s, below the configured 65 s.
At the profile's own deadline it would also put `verdict_end` at or below `refine_end`.
No cap was added.
Proportional scaling with a factor above 1 widens every gap, so `refine_end` always leaves at least the report reserve and `verdict_end` at least the profile's render margin (10 s on demo).
The new test asserts both invariants at 900 s and 3600 s instead.

## Mutation

The scale-up condition `verdict_end < d <= planned` was put back to `verdict_end < d`, and the new test failed (1 failed, 54 passed).
The file was restored from a `cp` backup, and the diff was checked afterwards.

## Replay

`docs/live_runs/rehearsal_concurrent_1/effective_config.json` records deadline 540 s and limits 265 / 465 / 530 s, and the new function returns the same values with no note.
`dra replay docs/live_runs/rehearsal_concurrent_1` exits 4: "replay diverged from the recording: 1 difference(s); first: $.findings[17].statement".
The same exit and the same divergence occur with `ab11a0a`'s code, so this change did not cause it.
It is not fixed here.
