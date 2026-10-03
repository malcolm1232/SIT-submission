# Session 4: re-assessment rehearsal report (2026-10-03)

Worker: the re-assessment rehearsal worker, one deliverable: the first live run of the delta path (lab brief p.3 §1.5).
Branch `s4/delta`, from `886c3fc`, in the worktree `SIT-wt/delta`.
The numbers, the classification table and the secret scan are in `docs/live_runs/reassess_payments_v2_1/MEASUREMENT.md`.

## Result

The re-assessment path works end to end on a live run.
`dra review design_v2.pdf --profile demo --no-tools --previous docs/live_runs/rehearsal_concurrent_1` produced a delta review in 422.8 s for at least $4.50, exit 0, outcome `completed_degraded`.
The report has the "Changes since the previous version" section: 2 resolved, 4 partially addressed, 10 still open, 3 new in update.
The regression the v2 idempotency fix introduced was caught as a new high finding (FND-002, the conditional put on a both-writable global table).
Against the six v1 findings on the areas the v2 revision history names, the agent marked 2 resolved, 3 partially addressed and dropped 1 (FND-011, FR-8) without classifying it.
The verdict stayed `not_fit` (0.75, was 0.78).

## Runs and spend

| What | Calls | Cost (CLI estimate) | Result |
|---|---|---|---|
| Opus delta run `reassess_payments_v2_1` | 8 | $4.50, lower bound (3 cut calls unrecorded) | exit 0, 425.1 s by `/usr/bin/time` |

The second approved run was not used: the first did not fail.

## What the runbook promises and what the code has

- The runbook (`docs/DEMO_DAY_RUNBOOK.md:129`) says to add `--previous runs/sit_v1_frozen` for an updated SIT design; the flag exists (`cli.py:111`) and needs only the prior run's `report.json` and canonical text.
- The runbook (line 132) promises "the delta section (resolved / open / regressed / new)"; the code has no "regressed" status, so a regression is reported as new in update, which the UI heading "new in update, including regressions" says openly.

## Defects (none fixed; nothing in `agent/` changed)

1. A prior finding can vanish from a delta review without a status: `agent/sit_review_agent/models.py:747-755` checks only that each finding of this run has a reassessment, not that each prior finding is cited. This run dropped FND-011, FND-039 and FND-012, one of them on a changed area, so "fixed" and "not re-examined" look the same.
2. Finding numbering is shared between the two reviews: this run's FND-002 (the regression) is not the prior FND-002 (Fraud Hook, now FND-003), and FND-046 is both a current ID and a prior ID. The rule in `agent/sit_review_agent/finding_refs.py:24-25` and `:242-245` keeps a prior ID only when it is no ID of this run, so a "FND-002" in a disclosure means this run's finding; a reader of both reports can still confuse them.
3. The Delta tab rows omit the prior ID and the reassessment note that `docs/design/ui_design.md` §7 asks for (`agent/sit_review_agent/ui/static/app.js:625-634`); they appear only in the finding detail (`app.js:552-553`).
4. Without a previous version the Delta tab is hidden (`app.js:660`), where the design note §7 says it is shown disabled with a reason.
5. Three of four assess shards were cut by the 265 s stage 1 limit, with `design_intent` left not assessed; the v1 run of the same profile finished assess in 230 s, so delta mode may need its own stage 1 tuning (load average was about 10, not separated).

## Screenshot

`docs/design/ui_mockup/for_him_ui_delta.png`, the Delta tab of this run at 1440 px from `dra ui --port 8797 --runs-dir docs/live_runs`.

## Precautions kept

- Every agent command ran with `env -u ANTHROPIC_API_KEY` and `--no-tools`; nothing touched the SIT MCP hosts.
- No recorded model output, `llm.jsonl` or progress record was printed; numbers came by script, and only the rendered `report.md` was read.
- No answer key, nothing under `eval/blind/`, and nothing under `docs/design/` except the delta-view section of `ui_design.md`.

## Not verified

- A grade against the answer key; the mapping to the fixed flaws is by section and title only.
- `dra replay` of this delta run.
- Whether the shard cuts come from delta mode or from the Mac's load.
