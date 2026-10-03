# Deadline scaling: report (2026-10-03)

A longer `--deadline` now gives the agent more time.
`effective_stage_limits` scales the three stage limits by `deadline / (refine_end + report_reserve_seconds)` in both directions.
A deadline from `verdict_end + 1` up to that planned run length keeps the limits as set.
Either way the change is announced in the progress log and in `progress.jsonl`.

## Limits produced on the demo profile

300 s gives 147 / 258 / 294 s (scaled down, as before).
540 s gives 265 / 465 / 530 s (unchanged, no announcement).
900 s gives 441 / 775 / 883 s (scaled up by 900/540).
3600 s gives 1766 / 3100 / 3533 s (scaled up by 3600/540).
The default profile at its own 3600 s keeps 2820 / 3420 / 3540 s.

## The cap

The brief's cap (`verdict_end` no later than the deadline minus the report reserve) was not added.
It contradicts the shipped profiles, because the demo `verdict_end` of 530 s already lies after 540 - 75 s.
It would also shrink the verdict window when scaling up.
Scaling up by a factor above 1 already keeps the report reserve after `refine_end` and the render margin after `verdict_end`, and the tests assert both invariants.

## Evidence

The mutation (reverting to the scale-down-only condition) fails the new test, and the code was restored from a backup.
`ruff check agent harness tests` exits 0.
`pytest -q` passes 1837 tests and exits 0.
`sit-review selftest`, `make smoke` (249 passed) and `make test` (1837 passed) all exit 0.

## Replay

The committed run `rehearsal_concurrent_1` recorded 540 s and 265 / 465 / 530 s, and the new function returns the same limits.
`dra replay` on that run exits 4 because finding 17's statement diverged from the recording.
The same divergence happens at the base commit `ab11a0a`, so it predates this change, and it is still open.

## Not verified

No live run with `--deadline 900` was made, so the scaled-up limits have not been rehearsed against real model latency.
The runbook and demo script say "not rehearsed" where they quote these limits.
