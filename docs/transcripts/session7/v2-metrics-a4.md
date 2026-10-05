# Worker note: v2 metrics A4

Card A4: `resolved_acknowledgement` and `stale_finding_rate` read 0.0 on every v2 scoring.

## Cause

`_v2_metrics` in `harness/sit_eval/metrics.py` never read the report's prior table (`review["prior_findings"]`); it only read `reassessment.status` on v2 findings strictly matched to a fixed flaw.
A prior finding the agent resolves has no successor finding (`PriorFindingEntry.finding_ids` is empty), so both counts were 0 of |R|.

## Definitions

Taken from `research/methodology/metrics.md` section 8; `eval/EVAL_PLAN.md` does not define the two metrics.
Stale-finding rate: fixed flaws the agent raises as still open, with no acknowledgement of resolution, over |R|.
Resolved acknowledgement (with-context only): fixed flaws explicitly recognised as resolved, over |R|.

## Change

Prior table rows map to key flaws through the v1 scores (`--prior-scores`: `finding_id` to `matched_flaw_strict`).
A `resolved` row acknowledges its flaw; a re-examined `still_open` or `partially_addressed` row raises it as open.
The old route (a v2 finding matched to the fixed flaw, read by its reassessment status) still counts.
A flaw is stale when raised as open and not acknowledged.
A not re-examined row is not counted as raised; it is listed under `not_re_examined` on the stale metric.
A delta review with a prior table but no `--prior-scores` gives null with a reason, not 0.0; `harness/README.md` says so.

## Tests

`test_v2_metrics_read_the_prior_table`: fixed flaws F01-F04; rows resolved, resolved, still open, not re-examined; acknowledgement 2/4 = 0.5, stale 1/4 = 0.25.
`test_v2_prior_table_without_prior_scores_is_null_not_zero`: same case without prior scores, both null with a `--prior-scores` reason.
Gates: ruff clean; 2002 passed, 1 skipped, 2 xfailed; selftest passed; mutation (`rows = []`) 2 failed, 7 passed, restored, `cmp` identical.

## Not verified

No real plan D v2 run was rescored; that needs the v1 `scores.json` passed as `--prior-scores`.
Excluding not-re-examined rows from stale is a reading of "the agent raises"; the rows are listed so a reader can count them the other way.

Verifier: fresh-context check agrees with 0.5 and 0.25 by hand; ruff clean, 2002 passed 1 skipped 2 xfailed from the worktree and from home, selftest passed, smoke exit 0, leakage PASS, mutation 2 failed then restored.
