# Quality of three runs on the payments design (2026-10-03)

**EXPLORATORY.** The payments answer key is not signed off (`scored_run_ready: false`), so every scoring here ran under `--exploratory` (SIT FABLE ruling #26).
The prereg is unfrozen too, so every score is an UNFROZEN PILOT score; no number here may be reported as confirmatory.

## Runs and setup

- Old: `live_cc_opus_payments_v1`, sequential agent, `high`, one assess call; scored in `eval_pilot2_bounded/`, graded in `grade_pilot/`.
- Medium: `rehearsal_concurrent_1`, concurrent agent (four shards, refine, verdict call), `medium`, demo profile; scored and graded by a sibling worker (`rehearsal_concurrent_1/QUALITY.md`).
- High: `rehearsal_concurrent_high_1`, the same concurrent agent with the base config, `high` on every stage; scored and graded here.
- Scoring in all three: `sit-eval score`, judge `claude_code`, `claude-opus-5-5` effort `high`, pairwise 0-3, 3 samples with the adaptive third sample, `shortlist_bounded`, grounding judges on, seed 20261002, concurrency 4.
- Grading in all three: `sit-eval grade run`, key-blind, 2 samples, seed 0, Opus `high`, `--max-cost-usd 8`.
- This run's dry run planned 71 to 197 calls and $9.52 to $18.43; the cost stop was $18 and was not reached.

## Side by side

| Measure | Old sequential `high` | Concurrent `medium` | Concurrent `high` |
|---|---|---|---|
| Agent wall time | 3,372 s | 382 s | 780 s |
| Agent cost | $3.68 (lower bound, completeness unknown) | $5.74 (complete) | $8.21 (complete) |
| Findings scored (strengths excluded) | 20 | 18 | 19 |
| Strict recall | 11 of 14 (0.786) | 13 of 14 (0.929) | 13 of 14 (0.929) |
| Lenient recall | 14 of 14 (1.000) | 14 of 14 (1.000) | 14 of 14 (1.000) |
| Adjudicated precision | 0.950 | 0.944 | 0.947 |
| Severity-weighted recall | 0.733 | 0.933 | 0.933 |
| Critical recall | 0.750 (3 of 4) | 1.000 (4 of 4) | 1.000 (4 of 4) |
| QWK severity agreement | 0.436 | 0.266 | 0.266 |
| Hallucination-flag rate (harness) | 0.000 | 0.000 | 0.000 |
| PARTIAL_KEY_MATCH count | 3 | 1 | 1 |
| VALID_UNPLANTED count | 5 | 3 | 4 |
| Other adjudicated classes | NON_SPECIFIC 1 | DUPLICATE 1 | INVALID_OPINION 1 |
| Grader S | 83.8 | 83.0 | 83.8 |
| Grade | B, PASS | B, PASS | B, PASS |
| Grader D1 to D10 | 4, 4, 4, 3, 4, 3.5, 4, 1, 2, 3 | 4, 4, 4, 3, 4, 4, 3, 1, 2, 3 | 4, 4, 4, 3, 4, 3.5, 4, 1, 2, 3 |
| Grader hallucination flags | 6 (1 material suspected) | 2 (none material) | 1 (none material) |
| Grader needs human review | yes | no | no |
| Scoring judge calls and cost | 98, $10.36 | 95, $9.54 | 93, $10.65 |
| Grading calls and cost | 4, $4.85 (plus one capped call, about $1) | 4, $5.30 | 4, $5.30 |

Grader dimensions: D1 intent, D2 fitness, D3 coverage, D4 evidence, D5 recommendations, D6 restraint, D7 triage, D8 research, D9 output integrity, D10 professional quality.
The high run's two grader samples gave S 85 and 82.5, differing on D6 only, exactly as the old run's did.
The high run's single INVALID_OPINION finding is FND-055; no run had an OUT_OF_SCOPE or HALLUCINATED finding.

## Planted flaws

Finding ids are each run's own, so the same id in two columns names different findings.

| Flaw | Severity | Old sequential `high` | Concurrent `medium` | Concurrent `high` |
|---|---|---|---|---|
| F01 | critical | strict (FND-002) | strict (FND-002) | strict (FND-046) |
| F02 | low | strict (FND-006) | strict (FND-020) | strict (FND-054) |
| F03 | high | strict (FND-005) | strict (FND-004) | strict (FND-049) |
| F04 | high | partial (FND-012) | partial (FND-009) | partial (FND-034) |
| F05 | low | strict (FND-011) | strict (FND-005) | strict (FND-018) |
| F06 | critical | partial (FND-004) | strict (FND-029) | strict (FND-032) |
| F07 | high | partial (FND-016) | strict (FND-051) | strict (FND-043) |
| F08 | critical | strict (FND-009) | strict (FND-046) | strict (FND-052) |
| F09 | high | strict (FND-001) | strict (FND-001) | strict (FND-001) |
| F10 | critical | strict (FND-003) | strict (FND-016) | strict (FND-047) |
| F11 | high | strict (FND-008) | strict (FND-006) | strict (FND-048) |
| F12 | low | strict (FND-017) | strict (FND-011) | strict (FND-029) |
| F13 | high | strict (FND-018) | strict (FND-023) | strict (FND-027) |
| F14 | low | strict (FND-014) | strict (FND-036) | strict (FND-026) |

No run missed a flaw outright.
Both concurrent runs match the same 13 flaws strictly and leave the same one, F04, partial.

## Verdicts

- Old sequential `high`: `fit_with_conditions` at confidence 0.68.
- Concurrent `medium`: `not_fit` at confidence 0.78.
- Concurrent `high`: `not_fit` at confidence 0.75.
- The key states no document-level verdict, so `doc_verdict_calibration` is null in all three scorings.
- The key's v1 flaws carry expected dispositions instead: 10 `refinement_now`, 2 `governance_decision`, 1 `needs_investigation` and 1 `needs_testing`.
- That shape reads closer to "fit after changes" than to "not fit", but this is a reading, not a scored result.
- The grader gave D2 fitness-for-purpose judgement 4 to all three verdicts, so it preferred none.

## What changed with effort alone (concurrent `medium` against concurrent `high`)

On the key the two concurrent runs are the same: strict, lenient, severity-weighted and critical recall are equal, and so is the per-flaw pattern.
Adjudicated precision moved by 0.003 and QWK not at all.
The `high` run had one more valid unplanted finding and one INVALID_OPINION where `medium` had one DUPLICATE.
The grader put `high` 0.8 points above `medium` (83.8 against 83.0), from D6 restraint down half a point and D7 triage up one point; both are a B.
The grader raised fewer hallucination flags on `high` (1 against 2), none material in either.
For this, `high` took 104 % more agent wall time (780 s against 382 s) and 43 % more agent cost ($8.21 against $5.74).

## What changed with structure alone (old sequential `high` against concurrent `high`)

Both ran at `high`, so the difference is the concurrent structure (four shards, refine and a verdict call) against one assess call.
Strict recall rose from 11 to 13 of 14: F06 and F07 moved from partial to strict, and F06 is critical, so critical recall rose from 3 of 4 to 4 of 4 and severity-weighted recall from 0.733 to 0.933.
Adjudicated precision stayed level (0.950 against 0.947), PARTIAL_KEY_MATCH fell from 3 to 1 because two of those flaws are now strict matches, and QWK severity agreement fell from 0.436 to 0.266.
The verdict changed from `fit_with_conditions` to `not_fit`.
The grader's dimension scores and S are identical (83.8, B); grader hallucination flags fell from 6 to 1 and the human-review flag went away.
Agent wall time fell from 3,372 s to 780 s, while the recorded agent cost rose from at least $3.68 to $8.21.

## Caveats

- One document, one run per arm: no difference above is statistically meaningful.
- Exploratory: the key is unsigned (decision #26), and the prereg is unfrozen.
- Same-family judge: the agent, the scoring judge and the grader are all Opus 5.5, and the grader is unvalidated (GR §7 calibration not run).
- The key changed between scorings: the old run was scored on key sha256 `32c34fcd5628` (commit `22e3e71`), both concurrent runs on `8eda2e5de12e` (commit `5b464ba`), which rewrote the `core_insight` of F04 and F11.
- So the old column's F04 and F11 rows are not strictly like for like; the old run was not re-scored on the current key.
- The old run's agent cost is a lower bound of unknown completeness (decision #28); the two concurrent runs are fully accounted.
- Mac load: the high agent run saw load averages of 5.85 rising to 9.41; its scoring and grading ran at the same time as each other and beside other sessions, with a load average of 6.34 (1 min) when they ended.
- Load may have slowed the agent's wall time; it does not change the scores.
- All judge and grader costs are the CLI's reported figures, not billed amounts.
- The medium column is copied from `rehearsal_concurrent_1/QUALITY.md` and its `scores.md` and `grade.md`; it was not re-scored here.
- Plan D (5 Oct 2026, eight synthetic documents, the agent against a single call, one run each, exploratory) is reported in `docs/COMPARISON_PLAN_D.md`.
