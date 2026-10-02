# Edit log: LC12 as a harness guard (SIT FABLE ruling #26)

Date: 2026-10-03 (Singapore time; clock read 2026-10-02 20:31 UTC at the end of the work).
Worker: a fresh-context agent session on `claude-opus-5-5`.
Scope: branch `s4/lc12`, base `2d84f59`, worktree `/Users/malco/Desktop/SIT-wt/lc12`.
Authority: the planner's ruling recorded as `docs/USER_DECISIONS.md` #26 ("SIT FABLE for the owner, 2026-10-03").

Isolation: nothing under `eval/blind/` was opened or listed, and `--include-blind` was never passed.
`docs/transcripts/session3_coordinator.md` was not read.
Nothing under `agent/` or `config/profiles/` was changed.
No model call was made: every scoring and grading run used the offline fake judges or `--dry-run`.
The real keys under `eval/synthetic/` were never written; `git diff --stat 2d84f59 -- eval/synthetic` is empty.

## Reproduction before the change

`sit-eval score docs/live_runs/live_cc_opus_payments_v1 --key eval/synthetic/payments_orchestration/answer_key.canonical.json --judge fake` exited 0 after 158 fake judge calls.
The only trace of the unsigned key was one warning inside `scores.json` ("scored_run_ready = false ... matcher scores are provisional"); nothing was printed to the console about it.
`sit-eval grade run ... --answer-key <the same key> --judge fake` exited 0 and ran the key-aware diagnostic with no mention of the key's state.
`sit-eval aggregate` over the pilot's `scores.json` exited 0 with only an "unfrozen pilot score" warning.

## Edits

| # | File | What changed | Why |
|---|---|---|---|
| 1 | `harness/sit_eval/lc12.py` (new) | The rule in one place: `key_signoff`, `require_signed` and its refusal message, the exploratory and outside-prereg lines, the artefact marker, how a `scores.json` is classed exploratory, and the aggregate refusal. | One definition for score, grade and aggregate, so the three commands cannot drift apart. |
| 2 | `harness/sit_eval/cli.py` | `score --exploratory`; an unsigned key without it exits 2 before the prereg check, the client build and the PATH preflight; the console JSON and stderr carry the marker; `--dry-run` adds an `lc12` note. `aggregate --exploratory`; exploratory inputs without it exit 2. | Ruling points 1, 2, 3 and 5. |
| 3 | `harness/sit_eval/scoring.py` | `ScoreOptions.exploratory`; `score_review` refuses an unsigned key before any call and refuses a runner whose cache mode differs from the run's; the marker goes into every `scores.json` (stopped runs too); the provisional warning now says the run was exploratory; a warning counts cached answers not reused. | Library callers get the same rule as the command line. |
| 4 | `harness/sit_eval/calls.py` | Each `judge_results.jsonl` row records `exploratory`; a confirmatory runner reuses only rows marked `"exploratory": false`. | A cache written under `--exploratory`, or before the guard (the pilots' rows carry no marker), is never served to a confirmatory run. |
| 5 | `harness/sit_eval/aggregate.py` | Refuses exploratory inputs, alone or mixed, unless `exploratory=True`; then the output carries the marker and lists `exploratory_inputs`; a mix adds a warning. | Ruling point 3. |
| 6 | `harness/sit_eval/report_md.py`, `harness/sit_eval/grader/report.py` | `scores.md` and `grade.md` open with an EXPLORATORY line when the run was exploratory. | Ruling point 2: the human-readable artefacts. |
| 7 | `harness/sit_eval/schemas/scores.schema.json` | `exploratory` is required; `exploratory_note` (required as a string when exploratory) and `outside_preregistered_analysis` are described. | Every new `scores.json` states its mode. Old pilot files are not validated by anything, so they are not rewritten. |
| 8 | `harness/sit_eval/grader/answer_key.py`, `harness/sit_eval/grader/pipeline.py`, `harness/sit_eval/grader/cli.py` | `grade run --exploratory`; with `--answer-key`, an unsigned canonical key or any legacy YAML key (it carries no sign-off) exits 2 before the judge is built, and the message also offers dropping `--answer-key`; `grade_review(exploratory=...)` enforces the same; `grade.json` carries the marker at the top and in `key_alignment_diagnostic` (with `scored_run_ready`); the dry run's warning says whether a real run would refuse. | Ruling point 4: the key-aware diagnostic reads the key, the key-blind passes do not. `grade_report.schema.json` was not edited: it allows extra fields, and it is part of the grader prompt lock. |
| 9 | `tests/eval_harness/test_eval_lc12.py`, `tests/eval_grader/test_grader_lc12.py` (new) | 26 tests: refusal (exit, message, zero clients built and zero calls), refusal before a live judge's preflight, dry runs, the marker in every artefact, a signed key with no marker, the flag on a signed key, resume refused, exploratory and pre-guard caches not served, the library guards, aggregate mix and exploratory-only refusals, a pre-guard `scores.json`, the marked aggregate, frozen prereg for score, aggregate and grade, the legacy grader key. | Written before the change; all 26 failed against `2d84f59`. Keys are temporary copies of the payments key with the sign-off state forced, so the tests hold before and after the owner signs. |
| 10 | `tests/eval_harness/test_eval_e2e.py` | The plumbing run, its cache rerun and the PATH preflight test pass `--exploratory`; the plumbing test also asserts the marker and the EXPLORATORY line in `scores.md`. | They score the real key, which is unsigned today; the signed path is covered by the new tests on copies. |
| 11 | `tests/eval_harness/eval_builders.py` | `run_pipeline` sets `exploratory` from the fixture key's state (the builder keys are unsigned), passes it to the runner, and takes `runner_exploratory` for the mismatch test. | The matcher and metric tests score unsigned fixture keys, which is exploratory scoring under the new rule; no assertion was weakened. |
| 12 | `tests/eval_grader/test_grader_pipeline.py` | The legacy-key diagnostic test passes `exploratory=True` and asserts the marker on the aware grade and its absence on the blind one. | A legacy key carries no sign-off. |
| 13 | `tests/eval_harness/test_eval_prereg_prompts.py` | The synthetic `scores.json` of the statistics test carry `"exploratory": false`. | They stand for confirmatory scores; without a marker and with no `scored_run_ready` they would now count as exploratory. |
| 14 | `harness/README.md` | The live scoring example on the S-dev key carries `--exploratory`; a key-aware `grade run` example; the `aggregate` refusal; a new section "LC12: signed keys only". | The documented command would otherwise refuse. Both new commands were checked with `--dry-run`. |
| 15 | `eval/EVAL_PLAN.md` §1.2 | A paragraph after the run matrix: scoring an unsigned key needs `--exploratory`, a pilot before T3 is exploratory, the three pilots predate the guard, lines A-3 to A-7 score only signed keys. | Where the plan describes the pilots. |
| 16 | `docs/live_runs/live_cc_opus_payments_v1/{eval_pilot,eval_pilot2_bounded,grade_pilot}/EXPLORATORY.md` (new) | One line each: the pilot predates the guard and is exploratory; the grade pilot was key-blind, so LC12 did not apply, but it is a pre-freeze pilot. | Ruling point 6; the pilot artefacts themselves are unchanged. |
| 17 | `docs/USER_DECISIONS.md` | Row #26 under a new dated heading, attributed "SIT FABLE for the owner, 2026-10-03". | The ruling's record. |
| 18 | `harness/sit_eval/live_judges.py`, `harness/sit_eval/judge.py` (docstring), `harness/sit_eval/cli.py`, `harness/sit_eval/grader/cli.py`, `harness/sit_eval/grader/pipeline.py` | `CallLog` takes `tags`, the live judges take `log_tags`, and both CLIs pass `{"exploratory": ...}`, so every attempt in `judge_calls.jsonl` records the run's mode; every row of `grader_calls.jsonl` records it too. | Ruling point 2 says every artefact; the call logs are artefacts of a live run. |
| 19 | `harness/sit_eval/grader/cli.py`, `harness/sit_eval/grader/pipeline.py` | `plan_grade` takes `exploratory`; the dry run's key warning says "a real run refuses it without --exploratory" or "run under --exploratory", whichever is true; the CLI's separate dry-run line is gone. | Found while checking the README command with `--dry-run`: the plan said "run under --exploratory" when the flag was absent. |
| 20 | `tests/eval_harness/test_eval_lc12.py`, `tests/eval_grader/test_grader_lc12.py`, `tests/eval_grader/test_grader_verify_fixes.py` | Two tests for the call-log tags; the grader artefact tests also check `grader_calls.jsonl`; a test stub of `_judge` takes the new `exploratory` argument. | Pin edit 18. |

## Checked and left as they are

- `eval/prereg.yaml` has no field describing how LC12 is enforced, so it is untouched.
- No entry in `eval/prereg_deviations.md`: the code enforces what LC12 ("every key used for scoring has scored_run_ready = true") and `freeze.rule` (pre-freeze pilot runs carry no confirmatory claim and are reported as exploratory) already state; no hypothesis, metric, test or decision rule changes.
- `eval/KEY_SIGNOFF.md` is untouched: its hash is recorded elsewhere, and signing still works as written (see the rehearsal below).
- `README.md` shows only `sit-eval score --help`, which does not refuse.
- No command in the harness writes CSV.
- `sit-eval grade validate` reads no answer key, so LC12 does not apply to it.

## Mutation checks

The code was committed first (`987078f`); each mutation removed one claim, ran the two LC12 test files and `test_eval_e2e.py`, and was restored from a `cp` backup, after which `git diff --quiet` held for the file.
All 19 mutations made a test fail (M17-M19 ran after the second commit):
M1 the `score_review` guard; M2 the `score` CLI guard; M3 the confirmatory cache filter; M4 the cache row's mode; M5 the runner and options mode check; M6 the aggregate refusal; M7 the pre-guard `scores.json` rule; M8 the `scores.json` marker; M9 the frozen-prereg line; M10 the `grade_review` guard; M11 the `grade run` CLI guard; M12 the legacy key treated as signed; M13 the `grade.json` marker; M14 the `scores.md` line; M15 the `grade.md` line; M16 the aggregate marker; M17 `CallLog` tags dropped; M18 the score CLI's `log_tags`; M19 the mode in `grader_calls.jsonl`.

## Signing rehearsal

In a scratch export of the tracked files at `987078f` (outside the worktree, deleted afterwards), the sheet's signing one-liner with a dummy name signed the three keys, and the converter gave `scored_run_ready True` for each.
The harness code came from the worktree's editable install, which already held the grader dry-run wording fix of the second commit.
There, `pytest -q tests` passed 1049, and `sit-eval score` on the signed payments key without `--exploratory` exited 0 with `exploratory: false`.

## Gates

`ruff check agent harness tests` exit 0; `pytest -q` 1051 passed, 0 skipped, exit 0; `sit-review selftest` exit 0; `make smoke` exit 0; `make test` exit 0; `python spec/convert_answer_keys.py --tier synthetic --check --verify-anchors` exit 0; `sit-eval prompts` exit 0 (bundle unchanged).
