# Matcher-rule verifier edit log (candidate rule, owner follow-ups #11-#16)

Date: 2026-10-02. Scope: Part 1 verifies the change "the listwise shortlist bounds pairwise scoring"
(owner decision `docs/USER_DECISIONS.md` #10; commits `f146aa7` and `94147a7`). Part 2 applies the owner-approved
follow-ups (#14 partial matches, #15 adaptive third sample, #16 no second-provider judge, T4 shortlist-miss
sample, pre-freeze text fixes, USER_DECISIONS rows #11-#16).

Offline only: no live call, no network, no `claude` CLI. Nothing under `eval/blind/` was opened. Git was used
read-only (`git show`, `git log`, `git diff`, `git status`). No matcher prompt or judge schema changed: the matcher
bundle stays `ac35d198ecef1c5a9176acd29e3d82fd9203c35eee4f4624d86da2b429ecc156` (`sit-eval prompts` passes) and the
grader bundle stays `64efe6b88489ac5542d7028f62782ed3c0b3096b0dfbfc0ac9ead22b4db75df0` (only prose outside the
extracted code blocks of `grader_prompt.md` changed; `tests/eval_grader` passes).

## Part 1: what was checked

| Claim | How checked | Result |
|---|---|---|
| Under `shortlist_bounded` no non-shortlisted pair is scored | Code read (`Matcher.candidates_for`, `run`, `score_pair`, `score_flaw_batch`, `pre_adjudicate`, `partial_free_flaw`); new tests for shortlist answers past K or repeated, deterministic DUPLICATE / PARTIAL paths, still-valid observations, adaptive samples, per_flaw_batch, resume from a cache written by a `union` run; mutation tests | Holds. One gap: ids past `shortlist_k` were cut silently and the cut was untested (mutant survived). Fixed (edit 2) |
| The hint leaks no key text beyond the old prompt | Prompt and `Matcher.shortlist` read: the `<location_hint>` lists finding ids only, in the shuffled order (not rank order); the flaw block is the unchanged `render_flaw` | Holds (mutants "hint in rank order", "hint always none" killed) |
| Shortlist failure handling is honest | Failure path read; test `test_shortlist_failure` | Holds for recall; SWR and critical recall did not carry the lower-bound note although the warning says "recall-based metrics" (edit 3). Unknown ids and ids past K were recorded but not surfaced (edit 2). `shortlist_k = 0` was silent (edit 4) |
| `union` reproduces the old candidate set | `test_union_reproduces_the_old_candidate_set` against an independent rewrite of the pre-change rule; diff of `566af80..f146aa7` | Holds, given the same shortlist answers. The shortlist prompt itself changed (hint added), so a `union` run today does not reproduce the old pilot end to end |
| Dry-run numbers | Recomputed by hand for the live run (20 findings, 14 flaws, 80 overlap pairs, all 20 findings overlap a flaw) | **Defect.** The bounded minimum (60 calls, $10.72) assumed 0 pair calls and 14 matched flaws at once, which cannot happen. Fixed (edit 1) |
| metrics.md §2.3 / §13, prereg `matcher.candidates`, protocol T4 say what the code does | Text read against code | Hold. Wall times in `harness/README.md` were stale (computed at the old 20-60 s per call) |
| §14 worked example | `test_eval_worked_example.py` under both rules and with the adaptive default | Holds |

Mutation runs (scratch script, each mutant applied, tests run, file restored): 13 + 17 + 3 mutants. Killed after the
fixes: all, including the three that first survived (K truncation, dedupe of repeated ids, non-gold partial
credit in calibration, free batch slots in the dry-run bound, partial tie-break).

## Edits

| # | File | What | Why |
|---|---|---|---|
| 1 | `harness/sit_eval/scoring.py` (`plan_calls`) | Min calls and low cost are now true lower bounds, searched over m = findings covered beyond the pairs every outcome scores: a finding with no scored pair is always adjudicated; one with a scored pair can avoid the adjudicator (matched, DUPLICATE, PARTIAL_KEY_MATCH). Batch mode counts free slots in batches that are asked anyway. `pair_scoring.min` and `adjudication.min` are the components of the min-calls plan. Notes and cost basis reworded. | Part 1 defect: the bounded min (60 calls) was an impossible outcome. Live run now: bounded 74-200 calls, $10.54-19.12 (adaptive on: $9.94-19.12); union 294-440 (was 300: N - G adjudications assumed, but every finding overlaps a flaw). |
| 2 | `harness/sit_eval/matcher.py` (`shortlist`), `scoring.py` (`score_review`) | Shortlist record gains `ids_beyond_k`; a warning names ids not in the review and ids past `shortlist_k` ("ignored, never scored"). | Part 1: the K bound was untested and the cut silent. |
| 3 | `harness/sit_eval/metrics.py` | `severity_weighted_recall` and (when a failed flaw is critical) `critical_recall` carry `shortlist_failed_flaws` and the lower-bound note, like recall. | Part 1: the warning promised "recall-based metrics are lower bounds". |
| 4 | `harness/sit_eval/scoring.py` | Warning when `shortlist_k = 0` under `shortlist_bounded` (no pair can be scored). | Part 1: silent zero recall. |
| 5 | `harness/sit_eval/matcher.py` | `PARTIAL_KEY_MATCH`: after the deterministic DUPLICATE check, a strict-unmatched finding whose best median is 2 against a free flaw is labelled `PARTIAL_KEY_MATCH` (basis `deterministic_partial`, `partial_key_flaw_id` and `related_flaw_id` = the flaw), with no adjudicator call. Ties: more severe flaw, then earlier in the key. Docstring rewritten. The LLM adjudicator's six classes are unchanged. | Part 2 item 1 (UD #14). |
| 6 | `harness/sit_eval/metrics.py` | `correct_unmatched()`: VALID_UNPLANTED, or PARTIAL_KEY_MATCH against a gold flaw. P_a = (TP + V + PK) / N with `partial_key_match` on the metric; new `partial_key_match_count` (secondary; findings, `not_gold`). Per-category precision, RJR Q_issue, calibration labels and the CDR false-positive test use `correct_unmatched`; only VALID_UNPLANTED removes a sound unit; `pooled_recall` reason says PARTIAL_KEY_MATCH never enters G+. Retired `precision_adjudicated_partial_credit`. | Part 2 item 1. |
| 7 | `harness/sit_eval/schemas/scores.schema.json` | `AdjClass` adds `PARTIAL_KEY_MATCH`; basis adds `deterministic_partial`; a PARTIAL_KEY_MATCH row requires `partial_key_flaw_id`. | Part 2 item 1. |
| 8 | `harness/sit_eval/scoring.py`, `report_md.py` | Finding rows carry `partial_key_flaw_strict`; scores.md shows `PARTIAL_KEY_MATCH (F0n)` and the `partial_key_match_count` row. | Part 2 item 1. |
| 9 | `config/eval.yaml`, `harness/sit_eval/config.py`, `cli.py`, `scoring.py`, `matcher.py` | `matcher.adaptive_third_sample: true` (config and `MatcherCfg` default); help text and the scores warning no longer say "needs owner approval". `--no-adaptive-samples` kept. | Part 2 item 2 (UD #15). |
| 10 | `tests/eval_harness/eval_builders.py` | `run_pipeline(out_dir=...)` so a test can resume from a result cache. | Test support. |
| 11 | `tests/eval_harness/test_eval_matcher_rule_verify.py` (new, 10 tests) | K bound and repeats; deterministic labels and observations never reach an unshortlisted pair; adaptive under the bounded rule; resume from a union cache; PARTIAL_KEY_MATCH class, P_a, count, CDR, per-category, calibration, scores.md, schema; non-gold partial in v2; partial tie-break; dry-run bound with free batch slots; adaptive default; `shortlist_k = 0` warning. | Regression tests for edits 1-9. |
| 12 | `tests/eval_harness/test_eval_candidate_rule.py`, `test_eval_verifier_e1.py`, `test_eval_e2e.py` | Dry-run pins updated to the true bounds (bounded 74-200; union 294-440 without adaptive, 214-440 with; costs $10.54 / $9.94 / $15.94 low); shortlist-failure test also checks SWR and critical recall. | Edits 1, 3, 9. |
| 13 | `tests/eval_harness/test_eval_matcher.py` | `test_adjudication_rules`: FND-003 is now PARTIAL_KEY_MATCH (no adjudicator call), P_a 0.75, counts, retired metric absent. | Edit 5-6. |
| 14 | `tests/eval_harness/test_eval_worked_example.py` | §14 runs also with the adaptive default. | LC9 under the configured default. |
| 15 | `harness/README.md` | Cost table regenerated from `--dry-run` (true bounds, adaptive default, wall times at 5-20 s per call); adjudication step and known-gaps text for PARTIAL_KEY_MATCH; G1 wording matches MM. | Edits 1, 5, 9. |
| 16 | `research/methodology/metrics.md` | §2.3 step 2 adaptive sample (dated); step 4 order of rules, PARTIAL_KEY_MATCH row, human-review note, dated amendment; step 5 G+; §3 PK and P_a; §3.1, §6.1, §6.2, §7.1; §5.1 G1 "token-level" -> character-level partial ratio (agent's `verify_anchor`), 8-token minimum for anchors only; §13 pseudo-code (adaptive sample, deterministic labels, P_a, calibration). §14 unchanged (still holds). | Part 2 items 1, 2, 5. |
| 17 | `eval/prereg.yaml` | `grader.second_provider.available: false` + reason; `grader.prompt_sha256` and `matcher.prompt_sha256` comments with the lock files and current hashes (values stay null); `matcher.model.branch_A` comment; `matcher.pairwise_scoring` adaptive wording; `matcher.adjudication.deterministic` (DUPLICATE, PARTIAL_KEY_MATCH); `key_freeze`; new `matcher.shortlist_recall`; stop rule and LC9 name `sit-eval score` (and `aggregate`). | Part 2 items 1-5. |
| 18 | `eval/prereg_deviations.md` | Entries 2 (PARTIAL_KEY_MATCH), 3 (adaptive sample), 4 (shortlist recall sample), 5 (no second provider; tool names; hash comments), 6 (correction to entry 1's dry-run numbers). Entry 1 untouched (append-only). | Freeze procedure: every non-fill field the diff touches is logged. |
| 19 | `eval/human_labelling_protocol.md` | T4: 12 `overlap_not_shortlisted` pairs mixed blind into the sheet (not in the 100), estimate with Wilson CI, not a gate; budget 1.75 -> 1.95 h, labelling total 14.9 -> 15.1 h; §6 row; T6b queue and §5.2 codebook gain PARTIAL_KEY_MATCH; κ over the classes. | Part 2 items 4 and 1. |
| 20 | `docs/DECISIONS.md` | ADR-003 closing note (Anthropic only; same-family disclosed per `research/models/README.md`). | Part 2 item 3. |
| 21 | `docs/USER_DECISIONS.md` | Rows #11-#16 under the third-session table. | Part 2 item 6. |
| 22 | `research/grading/README.md` | GR §4.2 G3 row states the caps are cumulative (>= 2 keeps D9 <= 2 and grade <= C). | Part 2 item 5; matches `grader/scoring.py`. |
| 23 | `research/grading/grader_prompt.md` (prose and the §5.3 example only) | §5.3 example uses `counts_median` with denominators, not shares; note on counts and cumulative `caps_applied`; §1 ADR-003 closed. No extracted block changed; grader lock unchanged. | Part 2 item 5. |
| 24 | `spec/README.md` (Edit-only, projection list) | Grader-facing projection also drops `metadata.review_id`, `run_id` and `stop_reason.detail`. | Part 2 item 5 (matches `grader/projection.py`). This edit was swept into W3's commit `27d2ec5`. |
| 25 | `research/audit/verify_matcher_rule_editlog.md` | This file. | Mandatory log. |

## Found, not fixed (outside this scope)

- `spec/taxonomy.yaml` `adjudication_classes` lists six classes; PARTIAL_KEY_MATCH is a harness-only seventh
  label (stated in metrics.md §2.3). The taxonomy owner may add it.
- `docs/HANDOVER_FULL.md` line ~208 still describes partial matches as adjudicated VALID_UNPLANTED.
- `eval/prereg.yaml` `matcher.model.branch_B` and `grader.primary.api` say "Message Batches"; the harness uses
  `claude -p` (ADR-010) and synchronous calls.
- metrics.md §2.3 step 6 says 150 validation pairs; prereg H10 and protocol T4 say 100 (Tier B adds 50).
- The pilot `runs/eval/pilot_payments_v1/` and `docs/live_runs/.../eval_pilot/` scores were made under the union
  rule with the old prompt; left as is.
