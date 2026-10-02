# Session 4: LC12 guard report (SIT FABLE ruling #26)

Date: 2026-10-03 (local, UTC+8); clock read 2026-10-02 20:31 UTC.
Worker: one fresh-context Opus 5.5 agent session, worktree `/Users/malco/Desktop/SIT-wt/lc12`, branch `s4/lc12`, base `2d84f59`.
Edit log: `research/audit/lc12_guard_editlog.md`.
No model call, live scoring or live grading was made, and no key was signed.

## Verdict

Done.
Prereg LC12 is now enforced in code: every command that reads an answer key to produce a score or a key-aware diagnostic refuses a key that is not signed off, unless it is given `--exploratory`, and then every artefact it writes says the run is exploratory.
This closes check 6 of `docs/transcripts/session4/keys_verifier.md`.

## Commands covered

- `sit-eval score`: refuses an unsigned key; `--exploratory` overrides.
- `sit-eval grade run --answer-key`: the key-aware diagnostic refuses an unsigned canonical key and any legacy YAML key (it carries no sign-off); `--exploratory` overrides; without `--answer-key` the key-blind grade reads no key and is not affected.
- `sit-eval aggregate`: refuses exploratory inputs, alone or mixed with confirmatory ones; `--exploratory` overrides and marks the output.
- The library calls `score_review` and `grade_review` apply the same rule.
- Not covered because they read no key: `sit-eval grade validate`, `sit-eval prompts`, `sit-eval grade lock`.
- `--dry-run` (score and grade) still plans and makes no call; its output says that a real run would refuse.

## The refusal

Exit code 2 (the harness's existing code for a refused run), raised before the prereg check, the judge client and the live-judge PATH preflight, so no call is made and nothing is spent.
On the real payments key today:

```
error: refusing a scored run: answer key eval/synthetic/payments_orchestration/answer_key.canonical.json is not signed off: scored_run_ready is false (pending: canary_guid, core_insight, anchor_quote, expected_disposition, approved_decisions, key_second_review, external_fact_verification, sound_overlap_annotations, v2_changed_sections). eval/prereg.yaml LC12 allows a scored run only on a key the owner has signed off (eval/KEY_SIGNOFF.md section 4 sets scored_run_ready). No judge call was made. Pass --exploratory to run anyway: every artefact is then marked exploratory and may not be reported as confirmatory
```

`grade run` prints the same with "refusing a key-aware grade" and adds "or drop --answer-key for the key-blind grade, which reads no key".
`aggregate` prints "refusing to aggregate: the inputs mix exploratory and confirmatory scores (...)" or "every input is exploratory, so no confirmatory analysis can be made from them (...)", naming each file, and the override.

## Where the marker appears

- `scores.json`: `exploratory`, `exploratory_note` and `outside_preregistered_analysis` at the top level (`exploratory` is now required by the schema), and the note first in `warnings`.
- `scores.md` and `grade.md`: an EXPLORATORY line directly under the title.
- `grade.json`: the same three fields at the top level, plus `exploratory` and `scored_run_ready` inside `key_alignment_diagnostic`.
- `judge_results.jsonl` (the result cache), `judge_calls.jsonl` (the live judges' per-attempt log) and `grader_calls.jsonl`: every row records `exploratory`.
- The aggregate JSON (file and console): the three fields plus `exploratory_inputs`.
- The console: the score summary JSON carries the fields, and the exploratory line is printed (stderr for score and aggregate, stdout for grade).
- With `eval/prereg.yaml` frozen, the note adds "OUTSIDE THE PRE-REGISTERED ANALYSIS ..." and `outside_preregistered_analysis` is true.
- The flag always marks, so an `--exploratory` run on a signed key is exploratory too.
- No harness command writes CSV.

## The result cache

A confirmatory run (no `--exploratory`) reuses only cache rows marked `"exploratory": false`.
Rows written by an exploratory run, and rows written before the guard (the pilots' `judge_results.jsonl` have no marker), are not served; those calls are made again and a warning gives the count.
Resuming into an exploratory `--out` without the flag on the still-unsigned key is refused like any other run, and the existing `scores.json` is left as it was.
`score_review` also refuses a runner whose cache mode differs from the run's.

## Pilot artefacts

`eval_pilot/`, `eval_pilot2_bounded/` and `grade_pilot/` under `docs/live_runs/live_cc_opus_payments_v1/` are unchanged.
Each has a new one-line `EXPLORATORY.md` saying it predates the guard and is exploratory (the grade pilot was key-blind, so LC12 did not apply to it, but it is a pre-freeze pilot).
`sit-eval aggregate` classes the two scoring pilots as exploratory because their keys were not signed off.

## Prereg and deviations

`eval/prereg.yaml` has no field describing how LC12 is enforced, so it is untouched.
No deviation entry was written: the code enforces what LC12 and `freeze.rule` already say, and no hypothesis, metric, test or decision rule changes.

## Tests and mutation

26 new tests (`tests/eval_harness/test_eval_lc12.py`, `tests/eval_grader/test_grader_lc12.py`) were written first and all failed against `2d84f59`; two more pin the call-log tags, added with that change.
Signed keys in tests are temporary copies of the payments key with the sign-off state forced; the real keys were never written.
Five existing test files were updated to the new rule (the flag where they score an unsigned key, and one stub's signature; no assertion weakened).
19 mutations, one per guard or marker, each made a test fail and was restored from a `cp` backup with `git diff --quiet` holding afterwards (list in the edit log).

## Signing rehearsal

In a scratch export of the tracked files (deleted afterwards) the sheet's one-liner signed the three keys with a dummy name; the suite (as of the first commit, before the call-log tests) then passed 1049, and `sit-eval score` on the signed payments key without the flag exited 0 with `exploratory: false`.
So the owner's last signing step (`pytest -q`, sheet section 4 step 7) stays green.

## Gates

`ruff check agent harness tests` exit 0.
`pytest -q`: 1051 passed, 0 skipped, exit 0 (1023 before).
`sit-review selftest` exit 0.
`make smoke` exit 0; `make test` exit 0.
`python spec/convert_answer_keys.py --tier synthetic --check --verify-anchors` exit 0.
`sit-eval prompts` exit 0, bundle unchanged.
`git diff --stat 2d84f59 -- eval/synthetic` is empty: the three real keys are byte-identical to `2d84f59`.

## Not verified

- A live judge path end to end: only the fake judges and dry runs were used, so the refusal before a live client and the marker on a live run are shown with fakes and the PATH-preflight ordering test only.
- The frozen-prereg message on the real `eval/prereg.yaml`: it is unfrozen, so the tests use a temporary frozen prereg and lock.
- The `exploratory` tag in a live judge's `judge_calls.jsonl` is shown by unit tests of `CallLog` and of the options the CLIs pass, not by a logged live attempt.
