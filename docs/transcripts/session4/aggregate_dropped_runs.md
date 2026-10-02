# Session 4: dropped runs and the pilot checkpoint (2026-10-03)

Worker: a fresh Opus session on branch `s4/aggdrop`, worktree `SIT-wt/costmetrics`, base 0abe223.
Ruling: SIT FABLE for the owner, 2026-10-03, `docs/USER_DECISIONS.md` #29, on the point left open in `cost_metrics_verifier.md`.
Edits and tests are in `research/audit/cost_metrics_unknown_usage_editlog.md`, section "Session 4 dropped-run guard".
No model call was made, the only judge used was the fake one, nothing under `eval/blind/` was opened, and no `llm.jsonl` was printed.

## Behaviour

Before: three FULL scores files, two fully accounted at $2.00 and $3.00 and one whose scoring the judge budget stopped before any statistic, gave `pass` (median $2.50 over 2 runs); the stopped file was only a warning.
An unreadable input stopped the command with a traceback.

After: the same inputs give `not_evaluable`, naming the dropped file and its reason.
`sit-eval aggregate` drops a scores file for one of four reasons: `judge_budget_stop`, `unreadable`, `schema_invalid` or `incomplete`.
Every dropped file is listed in the top-level `dropped_inputs` (path, reason, detail, condition), in the warnings, and on stderr.
When any dropped file is a FULL run, or one whose condition cannot be read, the pilot checkpoint is `not_evaluable` and its own `dropped_inputs` names those files.
A dropped file of another condition is listed and does not affect the checkpoint.
LC12 behaviour is unchanged.

## Choices made under the ruling

- `schema_invalid` is a structural check of what the aggregate reads (kind, a schema status, the `inputs` identity fields, a `metrics` object), not the full scores schema.
  Full validation would drop ruling #28's pre-ruling scores files, which the aggregate deliberately reads as unknown.
- `incomplete` is an empty `metrics` on a status that is not a budget stop.
- A file whose condition cannot be read (unreadable, not a scores object) counts as possibly FULL and blocks the checkpoint.
- A dropped FULL run also turns a would-be `fail` into `not_evaluable`, as the ruling says.
- `sit-eval aggregate` has no Markdown output, so none was listed there and no writer was added.

## Mutations

Removing the guard: 14 of the 18 new tests fail.
Dropping the unknown-condition rule: 6 fail.
Both restored from a `cp` backup and compared with `cmp`.

## Gates

`ruff check agent harness tests` 0; `make test` 0 (1158 passed, 0 skipped: 1140 plus 18 new); `sit-review selftest` 0; `make smoke` 0 (198 passed).

## Not verified

- No live budget-stopped scores file exists; the stop is the fake-judge pipeline's real `BudgetStop` path.
- The wall-time half of the pilot checkpoint is still not computed by the harness.
