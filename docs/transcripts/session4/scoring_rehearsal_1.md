# Session 4: scoring and grading rehearsal run 1 (2026-10-03)

Worker: one Opus worker on branch `s4/score`, from `502979a`, in the worktree `SIT-wt/score`.
Spend approved by the owner ("go" for the high rehearsal plus scoring both runs).
The comparison with the first live run is in `docs/live_runs/rehearsal_concurrent_1/QUALITY.md`.

## Runs and spend

| What | Calls | Cost (CLI reported) | Cap | Result |
|---|---|---|---|---|
| `sit-eval score --dry-run` | 0 | $0 | | planned 68 to 194 calls, $9.10 to $17.74 |
| `sit-eval grade run --dry-run` | 0 | $0 | | planned 4 (up to 5) calls, $2.85 to $3.57 list price |
| `sit-eval score`, pre-registered setup, `--exploratory` | 95 live, 0 failed | $9.54 | $18 | exit 0, `pilot_unfrozen`, cost stop not reached |
| `sit-eval grade run`, key-blind, 2 samples, `--exploratory` | 4 | $5.30 | $8 | exit 0, S 83.0, grade B, PASS, no third sample |

Total judge and grader spend: $14.84.
Flags reused from `live_cc_opus_payments_v1/eval_pilot2_bounded/scores.json` (`judge` block) and `grade_pilot/grade.json`; the only change is the scoring cap, 18 instead of 20.

## Result in brief

- Strict recall 13 of 14 (old run 11 of 14), lenient 14 of 14 (same), adjudicated precision 0.944 (0.950), severity-weighted recall 0.933 (0.733), critical recall 1.000 (0.750), QWK 0.266 (0.436), hallucination-flag rate 0.0 (0.0), PARTIAL_KEY_MATCH 1 (3).
- Grader S 83.0 grade B (old run 83.8 grade B); D6 up from 3.5 to 4, D7 down from 4 to 3, the rest equal.
- F06 and F07 became strict matches; F04 is partial in both runs; no flaw was missed by either.
- No adjudicated over-reach in either run.

## Things found along the way

- The answer key changed between the two scorings (`32c34fcd5628` at `22e3e71` to `8eda2e5de12e` at `5b464ba`); the change rewrote `core_insight` of F04 and F11, which the matcher reads.
- The old run was not re-scored on the new key; QUALITY.md says so.
- This run's FND-012 cross-references FND-003 and FND-010, which refine merged away, so the final report holds dangling finding references; not fixed here, worth a card.
- The scoring and grading commands write an empty `cli_cwd/` directory into the output; git does not track it.
- The grader now writes `inputs/` (prompt copies, about 1 MB) and `judge_calls.jsonl`; `inputs/` is left uncommitted as in the old `grade_pilot/`.
- `zsh` reads `$c:e...` in `git show $c:eval/...` as a history modifier; `${c}` is needed.

## Secret scan (counts only)

- `eval_pilot_bounded/`: `sk-` 0, `Bearer` 0, `oauth` 0, e-mail pattern 0; one home-directory path, the prereg path in `scores.json`.
- `grade_pilot/` (committed files): `sk-` 8, all inside `risk-` (0 not preceded by `ri`), `Bearer` 0, `oauth` 0, e-mail pattern 0, home paths 0.

## Not verified

- Whether the differences come from effort or from structure; the `high` concurrent rehearsal separates them once it is scored.
- The old run on the current key.
- Billed cost, as against the CLI's reported cost.
- Any statistic across runs: one document, one run per arm.

## Refused or blocked

Nothing was refused.
