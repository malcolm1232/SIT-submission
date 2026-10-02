# Session 4: integration verifier report (2026-10-03)

Verifier: a fresh-context Opus session that did not build the work.
Branch `s4/integration`, worktree `SIT-wt/integration`.
Edits and their regression tests are in `research/audit/verify_runtime_cli_editlog.md`, section "Session 4 verifier".

## Verdict

Not ready to push.
Everything the builder claimed holds on the merged tree, and every gate exits 0.
One condition of a planner ruling is not met: when a stage's answer truncates twice, the run does not end in a disclosed degraded report.
It ends in a typed, resumable exit 3 with no report at all.
That needs a design decision (options below), so the branch was committed locally and not pushed.

## Merge

`origin/claude/happy-darwin-d0bl94` was 2c7fba3 as expected.
It was merged into `s4/integration` with a merge commit, 3ba6786, with no conflict.
The editable package was reinstalled into `.venv`.

## Checks

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | `not_assessed` verdict | PASS | Present and consistent in the schema (label enum, per-objective `not`, verdict and review `if/then` rules), taxonomy, `models.py` validators, `llm/outputs.py` (`AssessedVerdictLabel`, three labels), report phase, renderer, grader G4 (`FITNESS_VERDICT_LABELS`, also used by the fake grader), scorer and aggregator warnings, validator cases (37 negative, 29 adversarial), `spec/README.md`, `agent/README.md`. No LLM-facing schema contains the word (test). A model draft with it fails validation and the verdict falls back to the code rule (test). The only former `not_fit` at confidence 0 was `not_assessed_verdict`; the rule fallbacks use 0.5. A genuine `not_fit` with findings stays `not_fit` (`test_e2e_synthetic.py`). The interface change is one commit, first on the branch, naming its callers; the planner accepted the one-commit form. Mutation: `not_assessed_verdict` back to `NOT_FIT`, 8 tests failed; restored from a `cp` copy. |
| 2 | Hosts | PASS | `stripe.com`, `stripe.com/blog`, `confluent.io` appear only in the leakage gate's term list, its tests and records. Mutation: `confluent.io` put back in `vendor_docs`: `scripts/leakage_grep.py` exit 1, two tests fail; restored, exit 0. |
| 3 | `max_tokens` 128000 and truncation | FAIL (design decision) | 64000 assumptions updated (config, README, LLM-07 docs, coverage table, tests). The `claude -p` cap error is typed `LLMTruncatedError` and not retried by the gateway (test; my mutation V1 caught). Truncates twice, run offline through the robustness harness for understand, assess and refine: exactly two calls, then exit 3, `failure.json` with `LLMTruncatedError`, resumable, no `report.md`, no partial report. Not a crash and not a silent success, but not the disclosed degraded report the ruling requires. A refine that truncates twice also discards the assess findings, which a deadline-cut refine keeps. The agent README said "exit 4"; corrected. New run-level test added. |
| 4 | Makefile | PASS | No absolute path. `make smoke` and `make test` exit 0 in the worktree, and in a `git clone --no-hardlinks` of the worktree with a separate virtualenv in the scratchpad, through both `PYTHON=` and `VENV=` (1018 passed there, the same count as the worktree). |
| 5 | Runbook | FIXED | Every flag in §4 and §5 exists in `dra review --help` (`--plan-only`, `--profile`, `--deadline`, `--max-tool-calls`, `--disable-tool`, `--no-tools`, `--previous`), `dra explain --run`, `dra coverage`, `make smoke`. Demo profile lines 19-24 and 27 match. The §4.1 listing test has teeth (changed `config/agent.yaml` line 5: it failed; restored). Fixed: three source paths that do not exist and a wrong stop-rule signature in §4, plus §8 and §9 paths, one to a missing `docs/ARCHITECTURE.md`; new test pins every runbook repo path. |
| 6 | EVAL_PLAN timing | PASS | Recomputed independently (below). Every figure matches. |
| 7 | Mutations | FIXED | Five of my own: V1 cap error retried by the gateway: caught. V2 declined assess no longer "missing": caught (3 tests, including robustness LLM-06). V3 coverage `?` cell back to `ok`: caught. V4 deadline warning boundary `< min_attempt_s` weakened to `< 0`: SURVIVED; new boundary test added, now caught. V5 k-run agreement denominator without not-assessed runs: caught. Every file restored byte for byte (`filecmp`). |
| 8 | Robustness CSV | PASS | Regenerated with `ROBUSTNESS_RESULTS_CSV=<scratch>`: 81 rows, same IDs and order, 0 field differences apart from commit, date and duration; 49 PASS, 32 BLOCKED. The tracked file names commit `e087db4`, the commit before it. |
| 9 | Answer-key close-out commits | PASS | `tests/test_spec_validator_blind.py` 7 passed (default not flipped). `spec/validate_examples.py` with no flags exit 0 and prints "eval/blind not read". Converter `--tier synthetic --check --verify-anchors` exit 0, 45 flaws, 0 failed. Rows #21 to #23 read correctly. All seven sheet §9 hashes match `shasum -a 256`; the sheet's own hash matches the one in 9738dc1's message. All three `signoff.signed_by` are null. |
| 10 | Whole-tree gates | PASS | See below. |
| 11 | Em dash and secrets | FIXED | One added line since 0caa581 carried em dashes (the EVAL_PLAN E1 row the builder rewrote); now `none`. No secret pattern on any added line. |

## Gates on the final tree

`ruff check agent harness tests` exit 0.
`pytest -q` exit 0, 1023 passed, 0 skipped (1018 on the merged tree before my 5 new tests).
`sit-review selftest` exit 0.
`make smoke` exit 0 (196 tests).
`make test` exit 0 (1023 passed).
`python spec/convert_answer_keys.py --tier synthetic --check --verify-anchors` exit 0.
`scripts/leakage_grep.py` exit 0; `spec/validate_examples.py` exit 0.

## Check 6: run time, recomputed

Source: `docs/HANDOVER_FULL.md` §8 (the one measured run) and the EVAL_PLAN Tier A table for run counts.
Productive time of the measured run: 2 + 158 + 158 + 520 + 33 + 88 = 959 s (ingest, understand, plan, the successful assess attempt, verify, report).
Run counts: FULL 16 + 9 + 9 + 6 + 18 + 3 + 3 + 12 + 8 = 84; A5 9; B0 9 + 9 + 6 = 24; B0-$ 9 + 6 = 15; total 132.
Floor: 93 FULL-shaped x 959 s + 39 single-call x 520 s = 89,187 + 20,280 = 109,467 s = 30.4 h; 10.1 to 15.2 h of wall time at 3 or 2 in parallel.
Cap: 132 x 3,600 s = 132 h; 44 to 66 h of wall time.
E1: 36 FULL-shaped (A-3 FULL and A5, A-5) and 18 single-call: 34,524 + 9,360 = 43,884 s = 12.2 h; cap 54 h.
Instruments: scoring 245.61 s is `elapsed_s` in `eval_pilot2_bounded/scores.json`; grading 158.91 + 193.54 + 91.80 + 105.04 = 549.29 s from `grade_pilot/grader_calls.jsonl`; 101 x 245.6 s = 6.9 h and 101 x 549.3 s = 15.4 h.
The builder's numbers all match.

"Floor 30.4 h, cap 132 h for the 132 runs" is right as arithmetic.
What each bound assumes:

- The floor assumes no retry and no killed attempt, a FULL run no slower than the measured document-only run without refine (research and refine only add time), and a single-call baseline no slower than the 520 s assess call.
  That last one is an analogue, not a bound: B0-$ is cost-matched to FULL and may write more than one assess call.
  A-1 runs that resume from a checkpoint can be shorter than 959 s, so the floor is not strict for them.
  It is one run on one 21-page document.
- The cap assumes every run uses the 3,600 s default deadline and that the deadline holds.
  It does not cover a run that exits 3 and is resumed (for example after a second truncation), nor the baselines if their harness does not enforce the same deadline (B0 and B0-$ are not built yet).

## Planner rulings applied

- Declined assess reports `not_assessed`: accepted; verified (check 1, V2).
- One retry at the same cap after a truncation: accepted as the minimum, on condition that "truncates twice" ends in a disclosed degraded report.
  The condition is not met (check 3).
  The known-limitations line is added to `agent/README.md` (Output cap).
- Interface change in one commit with its callers: accepted; recorded.
- Hosts: all four kept (edit log).
  `databricks.com` entered in `7885679`, the same commit as `stripe.com` and `confluent.io`, about four hours after the first synthetic items.
  It belongs to a general vendor-documentation list with a peer of the same kind (`snowflake.com`) that no item mentions, and the one item that names Databricks does so in an alternatives table, not in its key.
  Kept.
  `pdpc.gov.sg` (national regulator), `opentelemetry.io` (standards project) and `apache.org` (foundation) qualify on their own; `pdpc.gov.sg` is named in the clinical item and its key, which the leakage reviewer should know.
- Row #24 and the access-log line: written.
  Row #25 and `eval/prereg_deviations.md` entry 9: written.

How `not_assessed` is handled, as implemented: in `dra review --k` (`kruns.py`) it is never the modal verdict, but its runs stay in the denominator (all completed runs), so they lower the agreement; the harness has no verdict-agreement statistic.
In grading, gate G4 fails, D2 is capped at 0, and a dimension at 0 also fails gate G1.
Corrections to the builder's note text: the entry is 9, not 8; "the per-protocol view excludes such runs" is only a warning, since no code computes a per-protocol view; the G1 consequence was missing.

## Open: a stage that truncates twice (needs a decision)

Today, at the 128000 cap, the second truncation of understand, plan, assess or refine ends the run with exit 3 and no report; a resume repeats the same two calls at the same cap.

1. **Degrade like a deadline cut (recommended).** On the second truncation, record a disclosed degradation ("the assess answer was truncated twice at the output cap") and continue with the stage's existing code fallback.
   Assess then gives `not_assessed` with a third reason ("truncated"), refine keeps the assess findings, understand and plan use their code fallbacks.
   This meets the ruling, keeps the spend at two calls, and reuses paths that are already tested.
   Cost: a third reason in `phases/report.py` (`_NOT_ASSESSED_TEXT`, `assessment_missing`), `render.verdict_label_text`, the assess coverage note, the schema description, and robustness LLM-07's persistent variant.
   The new regression test already accepts this outcome.
2. **Split the stage** (assess per criterion group) after a truncation.
   Recovers findings but is a new code path in the most expensive stage, with more calls; the ruling says the minimum is acceptable.
3. **Keep exit 3 and document it.** Smallest change, but it contradicts the condition of the ruling, and a refine truncation throws away a finished assessment.

## Refused or stopped

One of my responses was stopped by a safety classifier early in the session, after a read-only grep of the verdict labels; nothing was lost, and later calls avoided resending it.
No tool call was refused.
No model call was made; no agent run on a document, no scoring or grading run.

## Not verified

- Anything live: Opus 5.5 through `claude -p` above 64,000 output tokens; the `anthropic_api` backend at 128000; the cost of the CLI's recovery turns at a large cap.
- The demo-profile timings and the runbook §5 timeline (still UNMEASURED).
- The live grader on a not-assessed review.
- The blind-validator tests' teeth (the brief said not to flip the default again; I re-ran them only).
