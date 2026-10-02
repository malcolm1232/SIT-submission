# Cost metrics under unknown usage: edit log (SIT FABLE ruling #28)

Date: 2026-10-03 (local, UTC+8); clock read 2026-10-02 21:21 UTC at the gates.
Scope: make the evaluation harness's cost and token metrics, and the pre-registration's pilot cost checkpoint, honest about agent runs whose usage is partly unknown (`docs/USER_DECISIONS.md` #28; the runtime side is commit `8ef32d4` on another branch).
Worktree `/Users/malco/Desktop/SIT-wt/costmetrics`, branch `s4/costmetrics`, base `103b8e6`.
Offline only: fake judge and fixtures, no model call, no key signed, nothing under `eval/blind/` opened, no `llm.jsonl` printed (the only call logs touched are fixtures written by the tests).
This worker is the retry of one stopped after reads only; nothing from that attempt was on disk.

## Baseline

`ruff check agent harness tests` exit 0; `pytest -q` 1051 passed, 0 skipped.

## Reproduction

A manifest in the runtime's shape (`usage.cost_usd: 1.10`, one `calls_with_unrecorded_usage` entry for `llm-0003 assess deadline_cut 178.9 s`, `cost_usd_lower_bound: true`) through `sit_eval.metrics._efficiency` gave `cost_usd: 1.1`, the full token counts, `reason: None` and the unchanged note "cost is the backend's own estimate", with no word about the cut call.
The first live run (`docs/live_runs/live_cc_opus_payments_v1`, manifest without the field, no `llm.jsonl` in the repository) scored the same way at $3.68, although four of its assess attempts were killed by a timeout (`eval/EVAL_PLAN.md` run-time note).

## Edits

| # | File | Change |
|---|---|---|
| 1 | `harness/sit_eval/usage.py` (new) | `unrecorded_reason` (the runtime's rule over an `llm.jsonl` entry, re-implemented because the harness must not import the runtime's manifest module and that module does not exist on this branch), `UsageCompleteness` (`complete`, `unrecorded`, `unknown`; source; the unrecorded calls), `from_manifest`, `from_call_log` (read by code; never printed), `usage_completeness` (manifest field, else call log beside the report, else unknown), `describe`, `warnings_for`, `lower_bound_of`, `status_of`. |
| 2 | `harness/sit_eval/loaders.py` | `ReviewInput.usage` (default `None`), filled by `load_review` from `manifest.json` or the review's `run_manifest` and the `llm.jsonl` beside `report.json`. |
| 3 | `harness/sit_eval/metrics.py` | `compute_metrics(..., usage=)`; `_efficiency` nulls `cost_usd`, `input_tokens`, `output_tokens`, `cached_tokens` on any run that is not fully accounted and reports `*_lower_bound` beside them, plus `usage_completeness`, `usage_reason` (`unrecorded_usage` or `usage_completeness_unknown`), `usage_note` (count and each call), `usage_source`, `calls_with_unrecorded_usage`; the metric note carries the words. A fully accounted run keeps its figures. |
| 4 | `harness/sit_eval/scoring.py` | Reads the completeness (the loader's, else computed) and adds the warnings (read from the call log; usage incomplete; completeness unknown); passes it to `compute_metrics`. |
| 5 | `harness/sit_eval/report_md.py` | The efficiency section opens with "COST AND TOKENS ARE A LOWER BOUND" or "USAGE COMPLETENESS UNKNOWN" and lists the unrecorded calls one per line. |
| 6 | `harness/sit_eval/schemas/scores.schema.json` | `$defs/Efficiency`: the value requires the completeness fields; when not `complete` the four figures must be null, the four lower bounds and the note present, and the reason the matching code; `unrecorded` needs at least one call, `complete` and `unknown` none. |
| 7 | `harness/sit_eval/aggregate.py` | Per condition `cost_usd`, `input_tokens`, `output_tokens`: `median_fully_accounted`, `iqr_fully_accounted`, `runs_fully_accounted`, `excluded_unrecorded` and `excluded_unknown` (count, share), `median_lower_bound_all_runs`, `iqr_lower_bound_all_runs`, `runs_with_a_lower_bound`, note; `runs_with_unrecorded_usage` (intention-to-treat) and `runs_with_unknown_usage_completeness`; top-level `pilot_checkpoint` (`pilot_checkpoint()` on the FULL `cost_usd` summary; `pilot_threshold_usd` argument). A `scores.json` without completeness counts as unknown with its figure as the bound. |
| 8 | `harness/sit_eval/prereg.py` | `pilot_cost_threshold_usd()` reads `costs.per_run_usd.heavy_case_FULL`. |
| 9 | `harness/sit_eval/cli.py` | `score` console JSON gains `cost` (completeness, cost, lower bound, count) and a stderr line when the cost is a bound; `aggregate` passes the prereg threshold and prints the checkpoint verdict on stderr. |
| 10 | `tests/eval_harness/eval_builders.py` | `run_pipeline(manifest=...)`. |
| 11 | `tests/eval_harness/test_eval_usage_completeness.py` (new, 19 tests) | The rule pinned to the runtime (demo run `llm-0003` legacy shape, new shape, every exclusion); manifest field wins; legacy manifest with a call log; neither; `load_review`; per-run metric for complete, cut, legacy-log and unknown runs; `--exploratory` unchanged; schema refusals; aggregate medians and shares; a pre-ruling `scores.json`; the checkpoint matrix; the checkpoint rule on summaries; the threshold from the prereg; the aggregate CLI and the score console. |
| 12 | `eval/prereg.yaml` | `stop_rule.pilot_checkpoint`, `reporting.always_reported` Efficiency row, the secondary metric comment, `costs.usage_completeness` (new), comments on `costs.per_run_usd`, `costs.measured_median_full_usd` and the `fill_before_freeze` entry. Parses; `frozen: false` unchanged. |
| 13 | `eval/prereg_deviations.md` | Entry 10. |
| 14 | `docs/USER_DECISIONS.md` | Row #28 with the note that #27 lives on another branch. |
| 15 | `harness/README.md`, `eval/EVAL_PLAN.md` | A section on unknown usage; the checkpoint paragraph and the CL11 row. |

## Checkpoint matrix as tested (`test_pilot_checkpoint_matrix`, threshold $3.24)

| FULL runs (cost, completeness) | Lower-bound median | Fully accounted median | Verdict |
|---|---|---|---|
| 3.5 unrecorded, 4.0 complete, 3.3 unknown | 3.5 | 4.0 (1 of 3) | fail |
| 2.0, 3.0, 3.24 all complete | 3.0 | 3.0 | pass |
| 3.0, 3.5, 3.3 all complete | 3.3 | 3.3 | fail |
| 2.0 complete, 2.0 unrecorded, 2.0 complete | 2.0 | 2.0 (2 of 3) | not_evaluable |
| 1.0 complete, 1.0 unknown | 1.0 | 1.0 (1 of 2) | not_evaluable |
| no FULL run; or no threshold | - | - | not_evaluable |

## Mutation runs

Scratch script: `cp` backup, one substitution, the new test file, restore from the backup, `cmp`.

| # | Mutant | Result |
|---|---|---|
| M1 | legacy rule ignores `status_code` | killed (rule test) |
| M2 | legacy rule counts unsent, fault, replayed and fake entries | killed (rule test) |
| M3 | manifest field ignored | killed (9 tests) |
| M4 | call-log fallback skipped | killed (3 tests) |
| M5 | metric keeps the cost figure on an incomplete run | killed (7 tests, including the schema) |
| M6 | aggregate's fully accounted set drops the completeness filter | **survived at first**: the per-run null already keeps a cut run's cost out, so the filter only matters for a `scores.json` written before the ruling (the pilots). Added `lower_bound_of`'s fallback for such a file and `test_aggregate_treats_a_scores_file_written_before_the_ruling_as_unknown`; killed on retry |
| M6b | aggregate's lower bound reads the null cost instead of the bound | killed (2 tests) |
| M7 | checkpoint passes on a lower bound | killed (3 tests) |
| M8 | checkpoint never fails on the lower-bound median | killed (2 tests) |
| M9 | schema allows a cost figure on an incomplete run | killed |
| M10 | markdown drops the lower-bound banner | killed |
| M11 | `scores.json` carries no completeness warning | killed (3 tests) |
| M12 | console `cost` reports the bound as the cost | killed |

Every file was restored byte for byte (`cmp`).

## Gates (exit codes read)

`ruff check agent harness tests` 0; `pytest -q` 1070 passed, 0 skipped (1051 + 19); `sit-review selftest` 0; `make smoke` 0 (196 passed); `make test` 0 (1070 passed).

## Not verified

- No live run exists on this branch with the new manifest field; the manifest shape is taken from `git show 8ef32d4` (`agent/sit_review_agent/manifest.py`, `tests/test_unrecorded_usage.py`) and pinned by fixtures, not by a run of the new runtime through the harness.
- The runtime's `unrecorded_reason` is re-implemented, not imported; `test_unrecorded_reason_pins_the_runtime_rule` is the only tie between the two, so a later change to the runtime's rule must be mirrored here.
- Wall-time p95 in `stop_rule.pilot_checkpoint` is not computed by the harness (unchanged).

## Session 4 verifier

Date: 2026-10-03 (local, UTC+8); clock read 2026-10-02 21:33 UTC.
Verifier: a fresh-context Opus session that did not build the work; report `docs/transcripts/session4/cost_metrics_verifier.md`.
Offline only: no model call, fake judge only, nothing under `eval/blind/` opened, no `llm.jsonl` printed (the demo run's call log was read by code for numeric and key fields only).

### Merge

`origin/claude/happy-darwin-d0bl94` (a29acfb) merged into `s4/costmetrics` as 5033367.
Two both-sides-added conflicts: `docs/USER_DECISIONS.md` (section #27 from main, then section #28 from this branch, the "#27 absent" sentence removed) and `eval/prereg_deviations.md` (main's amendment line on entry 9, then this branch's entry 10).

### Edits

| # | File | Change | Regression test |
|---|---|---|---|
| V1 | `tests/eval_harness/test_eval_usage_verifier.py` (new) | 23 entry shapes through the harness's and the runtime's `unrecorded_reason`; the demo run's real `llm.jsonl` through the runtime's `journal_usage` and the harness's `from_call_log` (same rows, `llm-0003 assess deadline_cut`); `sit_eval/usage.py` imports nothing from `sit_review_agent`. The builder's test pinned the harness copy to expected values only, not to the runtime's copy, which was absent from its branch. | itself |
| V2 | `harness/sit_eval/aggregate.py` `usage_summary` | A run whose `efficiency` value carries no figure at all (no cost, no bound) was left out of the lower-bound median, so the median of the rest could exceed the true median's floor and fail the checkpoint unsoundly (runs at $5 bound and no figure: bound median $5, true median could be $2.50). It now counts at 0 and is reported as `runs_without_a_figure_counted_at_zero`; `runs_with_a_lower_bound` keeps its meaning. | `test_a_run_with_no_figure_counts_at_zero_in_the_lower_bound_median` (fails on the old line, checked) |
| V3 | `harness/sit_eval/cli.py` `aggregate` | The checkpoint console line printed `$None` when the prereg has no threshold; it now says "no threshold". | `test_the_aggregate_console_without_a_threshold_says_so` |
| V4 | `agent/sit_review_agent/models.py` `ManifestExtra` docstring | "Scorers never read `extra`" was untrue (the harness reads `extra.timing` and now `extra.model.calls_with_unrecorded_usage`); corrected without naming the harness package (the isolation test refuses that string in `agent/`). | `test_agent_package_is_isolated_from_the_harness` |
| V5 | `eval/prereg.yaml` B0-$ `matching_rule`, `stop_rule.budget_stop`, `costs.usage_completeness` | B0-$ matching uses fully accounted medians only and is `not_evaluable` (reported, no n chosen) while any pilot FULL or B0 run is not fully accounted; the budget stop's spend is a lower bound when any run is not fully accounted, a lower-bound sum at or above the figure triggers the stop and one below is reported as "at least"; the zero-count rule of V2. No fill value changed, `frozen: false`, parses. | the prereg parse in `test_the_threshold_is_read_from_the_prereg` |
| V6 | `eval/prereg_deviations.md` entry 10 | The garbled **Fields** line (a field named twice across a line break) rewritten; V5's fields, old text and new text added to the same entry. | none (text) |
| V7 | `docs/USER_DECISIONS.md` #28, `harness/README.md` | "commit `8ef32d4`, on another branch" is no longer true after the merge; README names the parity test and the zero-count rule. | none (text) |

### Re-run mutations (builder's numbering)

M1 (legacy rule ignores `status_code`) killed, 1 test; M3 (manifest field ignored) killed, 10; M5 (metric keeps the cost on an incomplete run) killed, 7; M7 (checkpoint passes on a lower bound) killed, 3; M9 (schema allows a cost figure) killed, 1.
Each by `cp` backup, one substitution, the builder's test file, restore, `cmp` equal.
