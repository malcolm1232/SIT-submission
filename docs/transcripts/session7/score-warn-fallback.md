# Worker note: scorer refine-fallback warning (card A5)

## Change

`harness/sit_eval/scoring.py::score_review` now reads the scored report's `research_log.degradations`.
The new `refine_fallback_events` function picks out the degradations that record a refine fallback or a failed refine repair.
Those are: an impact that contains the agent's `REFINE_FALLBACK_IMPACT` (revisions not applicable, deadline cut, truncated twice, a stop rule that skipped refine), a refine call the model declined twice, and a repair call that did not return in full.
A repair that returned in full, and a model fallback, are not counted.
When there is one, the scorer prints one stderr line with the run id and the first event's first 120 characters, and also adds that line to `warnings`.
No metric value changes.
`inputs.refine_fallback_recorded` (boolean) and `inputs.refine_fallback_events` (list of event texts), written next to `run_id`, `condition` and `verdict_label`.
`harness/sit_eval/schemas/scores.schema.json` describes both fields (they are optional, so older scores still validate).

## Tests

All 9 are in `tests/eval_harness/test_eval_score_refine_fallback.py`.
`test_refine_fallback_warns_and_records_true` runs 4 cases: invalid, declined, repair_failed, deadline_cut.
`test_refine_fallback_changes_no_metric`.
`test_no_degradations_records_false_and_prints_nothing` runs 2 cases: absent, empty.
`test_refine_degradation_that_is_not_a_fallback_records_false`.
`test_refine_fallback_events_unit`.

## Gates

ruff: All checks passed!
pytest: 2017 passed, 1 skipped, 2 xfailed.
selftest: selftest passed.
With the detection's append disabled, 6 of the 9 new tests failed.
The file was restored from a `cp` backup and `cmp` confirmed it matches.
Verifier (5 Oct 2026): the status-only refine repair (N of N revisions applied from the first answer) was flagged; the rule now excludes it, 3 new tests, ruff clean, 2020 passed, 1 skipped, 2 xfailed, selftest, smoke and leakage_grep passed, mutation 9 of 12 failed.

## Not verified

Not run against a real report that recorded a refine fallback; the test event texts are copied from the agent's own wording.
`sit-eval aggregate` and the RUNS tables do not show the field yet; they can read it from `inputs`.
A refine call cut by the deadline whose partial answer was salvaged is not counted as a fallback.
