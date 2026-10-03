# Session 4: scoring and grading the high rehearsal (2026-10-03)

One Opus worker on branch `s4/score2`, worktree `SIT-wt/score2`, from `a78d395`.
Task: score and grade `docs/live_runs/rehearsal_concurrent_high_1/` with the pre-registered harness setup, then write the three-way comparison.
The owner approved the spend ("go" for the high rehearsal plus scoring both runs).

## Runs and spend

- Scoring dry run: 71 to 197 calls, $9.52 to $18.43 (typical $13.97), wall time 1.5 to 16.4 min.
- Scoring live: `sit-eval score docs/live_runs/rehearsal_concurrent_high_1 --key eval/synthetic/payments_orchestration/answer_key.canonical.json --out docs/live_runs/rehearsal_concurrent_high_1/eval_pilot_bounded --judge claude_code --model claude-opus-5-5 --effort high --samples 3 --seed 20261002 --granularity pairwise --candidate-rule shortlist_bounded --adaptive-samples --grounding-judges --no-recommendation-judge --concurrency 4 --max-cost-usd 18 --exploratory`, under `env -u ANTHROPIC_API_KEY`.
- Scoring result: 93 calls, 93 live, 0 failed, $10.65 reported; exit 0; cost stop ($18) not reached.
- Grading dry run: 4 calls (up to 5), $3.07 to $3.86 at list price.
- Grading live: `sit-eval grade run docs/live_runs/rehearsal_concurrent_high_1/report.json --pdf eval/synthetic/payments_orchestration/design_v1.pdf --out docs/live_runs/rehearsal_concurrent_high_1/grade_pilot --judge claude_code --samples 2 --seed 0 --model claude-opus-5-5 --effort high --max-cost-usd 8 --exploratory`.
- Grading result: 4 calls, $5.30 of $8.00; exit 0; no third sample.
- Scoring and grading ran at the same time (the grader is key-blind and does not depend on the scoring).
- Total spend: 97 calls, $15.94 reported.

## Result in brief

- Strict recall 13 of 14 (F04 partial), lenient 14 of 14, adjudicated precision 0.947, severity-weighted recall 0.933, critical recall 4 of 4, QWK 0.266, hallucination-flag rate 0.000.
- PARTIAL_KEY_MATCH 1, VALID_UNPLANTED 4, INVALID_OPINION 1 (FND-055).
- Grader S 83.8, grade B, PASS, dimensions identical to the old sequential run; 1 grader hallucination flag, not material; no human review needed.
- The comparison with the old run and rehearsal 1 is `docs/live_runs/QUALITY_COMPARISON.md`.

## Things found along the way

- The answer key changed between the old run's scoring (sha256 `32c34fcd5628`) and both rehearsal scorings (`8eda2e5de12e`, commit `5b464ba`), which rewrote F04 and F11; the comparison says so.
- The key has no document-level verdict, so no verdict could be scored.
- The harness leaves an empty `cli_cwd/` in the scoring output; it is empty and was not committed.
- The grader's `inputs/` prompt copies were left uncommitted, as in both earlier `grade_pilot/` directories; the new `judge_calls.jsonl` there was committed.
- The sibling's `medium` results had landed on the remote and were merged before the comparison was written.

## Secret scan (counts only)

- `eval_pilot_bounded/`: `sk-` 6, all preceded by `ri` (0 otherwise); `Bearer` 0; `oauth` 0; e-mail pattern 0.
- `grade_pilot/` (committed files): `sk-` 16, all preceded by `ri` (0 otherwise); `Bearer` 0; `oauth` 0; e-mail pattern 0.
- The first grader scan passed the file list in one shell variable, which zsh did not split, so it scanned nothing; it was rerun on the directory before the commit.

## Not verified

- Billed amounts; all costs are the CLI's reported figures.
- Any statistical difference; one document, one run per arm.
- The grader's validity (GR §7 calibration not run) and independence (same model family as the agent).
- The old run on the current key; it was not re-scored.
- Whether the Mac's load affected anything beyond wall time.

## Refused or blocked

- One of my responses was stopped by a safety classifier after I read the CLI help text, before the dry run; it was not resent, and the work continued with the next step.
- Nothing else was refused.
