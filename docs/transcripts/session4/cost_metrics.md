# Session 4: cost metrics under unknown usage (SIT FABLE ruling #28)

Date: 2026-10-03 (local, UTC+8); clock read 2026-10-02 21:21 UTC at the gates.
Worker: one fresh-context agent session (the retry of a worker stopped after reads only), worktree `/Users/malco/Desktop/SIT-wt/costmetrics`, branch `s4/costmetrics`, base `103b8e6`.
Edit log: `research/audit/cost_metrics_unknown_usage_editlog.md`.
No model call, live scoring or live grading was made, no key was signed, nothing under `eval/blind/` was opened, and no `llm.jsonl` was printed.

## Verdict

Done.
A run with any model call whose usage was not recorded, or whose completeness cannot be established, no longer scores a complete-looking cost: its cost and tokens are null with the recorded figures beside them as lower bounds, the aggregate keeps the fully accounted median apart from the lower-bound median, and the prereg pilot checkpoint can fail on a lower bound but never pass on one.

## Before and after, per ruling point

1. Per run. Before: a manifest listing one deadline-cut call and `cost_usd_lower_bound: true` scored `efficiency.value.cost_usd: 1.1` with full token counts and no qualification. After: `cost_usd`, `input_tokens`, `output_tokens` and `cached_tokens` are null, `usage_reason` is `unrecorded_usage`, `usage_note` names the count and each call ("1 model call with unrecorded usage (llm-0003 assess attempt 0, deadline cut, 178.9 s)"), and `cost_usd_lower_bound: 1.1` with the three token lower bounds stand beside them. A fully accounted run keeps its figures (new fields only: `usage_completeness: complete`, `usage_reason: null`, `usage_source`, `calls_with_unrecorded_usage: []`).
2. Completeness source. Before: the manifest's field was never read. After: the manifest field when present; for a manifest that predates it, the runtime's rule over the `llm.jsonl` beside `report.json`, read by code, with `usage_source` and a warning saying so; with neither, `unknown` and the metric null with reason `usage_completeness_unknown`. The rule is implemented once in `harness/sit_eval/usage.py` (the harness already depends on the agent package, but the runtime's `manifest.unrecorded_reason` does not exist on this branch) and pinned by a fixture in the demo run's `llm-0003` shape.
3. Aggregates. Before: no cost median at all. After: per condition `cost_usd`, `input_tokens` and `output_tokens` with `median_fully_accounted` and `iqr_fully_accounted` over fully accounted runs, `excluded_unrecorded` and `excluded_unknown` with count and share, and `median_lower_bound_all_runs` over every run at its bound; the note says no figure mixes the two. A `scores.json` written before the ruling counts as unknown.
4. Pilot checkpoint. Before: prose only, a median over whatever `cost_usd` said. After: `pilot_checkpoint` in the aggregate output, threshold from `eval/prereg.yaml` `costs.per_run_usd.heavy_case_FULL` (3.24): `fail` if the lower-bound median over all FULL runs exceeds it, `pass` only if every FULL run is fully accounted and the median is at or below it, else `not_evaluable`. The matrix is in the edit log.
5. Reporting. After: `runs_with_unrecorded_usage` per condition (count, share, run ids), intention-to-treat, with `runs_with_unknown_usage_completeness` beside it.
6. Text. `eval/prereg.yaml` (`stop_rule.pilot_checkpoint`, the Efficiency row, the secondary metric comment, `costs.usage_completeness`, cost comments), `eval/prereg_deviations.md` entry 10, `docs/USER_DECISIONS.md` row #28 (row #27 is on another branch and is noted as absent), `harness/README.md`, `eval/EVAL_PLAN.md`.

## Writers

`scores.json` (schema `$defs/Efficiency` refuses a cost figure on an incompletely accounted run), `scores.md` (a LOWER BOUND or COMPLETENESS UNKNOWN line opens the efficiency section; the cut calls are listed), the `score` console (`cost` entry and a stderr line), the aggregate JSON and the `aggregate` console (the checkpoint verdict on stderr).
`--exploratory` behaviour is unchanged (pinned by `test_exploratory_marking_is_unchanged_by_usage_completeness`).

## Effect on existing artefacts

The first live run's manifest predates the field and its `llm.jsonl` is not in the repository: `sit-eval score` on it now reports `usage_completeness: unknown`, `cost_usd: null`, `cost_usd_lower_bound: 3.678512`.
The two pilot `scores.json` files are not rewritten; aggregated, they count as unknown.

## Gates

`ruff check agent harness tests` 0; `pytest -q` 1070 passed, 0 skipped (1051 baseline + 19 new); `sit-review selftest` 0; `make smoke` 0; `make test` 0.
Twelve mutants, all killed after one fix (edit log).

## Not verified

No run of the new runtime (commit `8ef32d4`) has been scored through the harness on this branch; the manifest shape comes from that commit's diff and tests.
The wall-time half of the pilot checkpoint is still not computed by the harness.
