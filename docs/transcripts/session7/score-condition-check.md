# Worker note: sit-eval score condition guard

Commit 0dd8fa4 on branch s4/score-condition-check, based on cb527e5.

## The change

`harness/sit_eval/scoring.py` gains `ConditionMismatch` and `check_condition(flag, manifest, run_manifest)`.
It checks `--condition` against both recorded copies of the run's condition: `manifest.json` beside the report and the report's `run_manifest`.
A recorded condition that is present and different from the flag raises `ConditionMismatch`, naming the flag value, the source and the recorded value.
A null or absent recorded condition (runs made before the condition field was set) takes the flag as given, and no flag is unchanged.
`harness/sit_eval/cli.py` calls it in `score` right after the run is loaded, before the dry run, before the LC12 checks, before any judge is built and before `--out` is created.
It exits 2 with one line: "refusing to score: --condition X contradicts the run's <source> condition Y; drop the flag or correct it".

## Tests

New file `tests/eval_harness/test_eval_score_condition.py` (8 tests, offline, fake judge, temporary copies of the live payments report):
- test_score_refuses_a_condition_that_contradicts_the_manifest (non-zero exit, both values in the line, no `--out` folder, no judge built)
- test_score_refuses_a_contradiction_recorded_only_in_the_report
- test_dry_run_refuses_a_contradicting_condition_too
- test_check_condition_unit
- test_score_accepts_a_condition_that_matches_the_manifest
- test_score_accepts_the_flag_when_the_manifest_records_no_condition[null] and [absent]
- test_score_without_the_flag_reads_the_manifest_condition

The Review schema requires `run_manifest.condition` in the report (null allowed), so the "absent" case is a `manifest.json` without the field.

## Gates and mutation

ruff: All checks passed!
pytest: 2008 passed, 1 skipped, 2 xfailed.
selftest: selftest passed in 0.6 s.
With the refusal condition replaced by `if False`, 4 tests failed (the three refusal tests and the unit test) and 4 passed.
The file was restored from a `cp` backup and `cmp` reported it identical.

## Not verified

The guard sits in the CLI only: `score_review` called directly as a library does not check, because the shared test builders pass conditions over a fixture manifest that deliberately records a different one.
No real agent run folder was scored with the guard; the tests use copies of one live report with the condition rewritten.
A run whose `manifest.json` and report disagree with each other is refused for any flag that differs from either; no test covers that case.
