# Quality of rehearsal run 1 against the first live run (2026-10-03)

**EXPLORATORY.** The payments answer key is not signed off (`scored_run_ready: false`), so both scorings ran under `--exploratory` (SIT FABLE ruling #26) and no number here may be reported as confirmatory.
The prereg is also unfrozen, so every score is an UNFROZEN PILOT score.

## Setup

- Scoring: `sit-eval score` with the pre-registered setup of `live_cc_opus_payments_v1/eval_pilot2_bounded/`: judge `claude_code`, `claude-opus-5-5` effort `high`, pairwise 0-3, 3 samples with the adaptive third sample, `shortlist_bounded`, grounding judges on, seed 20261002, concurrency 4, `--exploratory`.
- Cost stop: `--max-cost-usd 18` (the old run used 20); the dry run planned 68 to 194 calls and $9.10 to $17.74.
- Grading: `sit-eval grade run` key-blind (no `--answer-key`), 2 samples, seed 0, Opus `high`, `--max-cost-usd 8`, `--exploratory`, the same flags as `grade_pilot/`.
- Outputs: `eval_pilot_bounded/` and `grade_pilot/` in this directory; the grader's `inputs/` prompt copies are left uncommitted, as in the old `grade_pilot/`.

## Side by side

| Measure | Old run (sequential, `high`, one assess call) | This run (concurrent, `medium`, four shards) |
|---|---|---|
| Findings scored (strengths excluded) | 20 | 18 |
| Strict recall | 11 of 14 (0.786) | 13 of 14 (0.929) |
| Lenient recall | 14 of 14 (1.000) | 14 of 14 (1.000) |
| Strict precision | 0.550 | 0.722 |
| Adjudicated precision | 0.950 | 0.944 |
| Severity-weighted recall | 0.733 | 0.933 |
| Critical recall | 0.750 (3 of 4) | 1.000 (4 of 4) |
| QWK severity agreement | 0.436 | 0.266 |
| Hallucination-flag rate (harness) | 0.000 | 0.000 |
| PARTIAL_KEY_MATCH count | 3 | 1 |
| Location validity (G2) | 0.817 | 0.925 |
| Citation precision | 0.703 | 0.657 |
| Duplication rate | 0.000 | 0.056 |
| Grader S and grade | 83.8, B, PASS | 83.0, B, PASS |
| Grader D1 to D10 | 4, 4, 4, 3, 4, 3.5, 4, 1, 2, 3 | 4, 4, 4, 3, 4, 4, 3, 1, 2, 3 |
| Grader hallucination flags | 6 (1 material suspected); human review needed | 2 (none material); no human review needed |
| Scoring judge calls and cost | 98, $10.36 | 95, $9.54 |
| Grading calls and cost | 4, $4.85 (plus one capped call, about $1) | 4, $5.30 |
| Agent run cost | $3.68 (lower bound, completeness unknown) | $5.74 (complete, all 8 calls recorded) |

The grader dimensions moved in two places only: D6 restraint rose from 3.5 to 4 and D7 issue triage fell from 4 to 3.
The two grader samples of this run agreed exactly (S delta 0).

## Planted flaws

| Flaw | Severity | Old run | This run |
|---|---|---|---|
| F01 | critical | strict (FND-002) | strict (FND-002) |
| F02 | low | strict (FND-006) | strict (FND-020) |
| F03 | high | strict (FND-005) | strict (FND-004) |
| F04 | high | partial (FND-012) | partial (FND-009) |
| F05 | low | strict (FND-011) | strict (FND-005) |
| F06 | critical | partial (FND-004) | strict (FND-029) |
| F07 | high | partial (FND-016) | strict (FND-051) |
| F08 | critical | strict (FND-009) | strict (FND-046) |
| F09 | high | strict (FND-001) | strict (FND-001) |
| F10 | critical | strict (FND-003) | strict (FND-016) |
| F11 | high | strict (FND-008) | strict (FND-006) |
| F12 | low | strict (FND-017) | strict (FND-011) |
| F13 | high | strict (FND-018) | strict (FND-023) |
| F14 | low | strict (FND-014) | strict (FND-036) |

Neither run missed a flaw outright.
This run turned F06 and F07 from partial into strict matches; F04 stayed partial in both.
Finding ids are each run's own, so the same id in the two columns names different findings.

## Findings that matched no flaw

- Old run: VALID_UNPLANTED FND-007, FND-010, FND-013, FND-015, FND-019 (5); NON_SPECIFIC FND-020 (1).
- This run: VALID_UNPLANTED FND-021, FND-022, FND-039 (3); DUPLICATE FND-012 (1).
- Over-reach (INVALID_OPINION, OUT_OF_SCOPE or HALLUCINATED by the adjudicator): none in either run.
- This run's DUPLICATE, FND-012, cross-references FND-003 and FND-010, which do not exist in the final report because refine merged them away; the grader flagged this as a wrong document location.
- A dangling cross-reference after the merge step is an agent defect worth a card; it was not fixed here.

## Verdict

- Old run: `fit_with_conditions` at confidence 0.68.
- This run: `not_fit` at confidence 0.78.
- The key states no document-level verdict; `doc_verdict_calibration` is null in both scorings for that reason.
- Its v1 flaws carry expected dispositions instead: 10 `refinement_now`, 2 `governance_decision` (F03, F14), 1 `needs_investigation` (F07) and 1 `needs_testing` (F13).
- That shape reads closer to "fit after changes" than to "not fit", but this is my reading, not a scored result.
- The grader gave D2 fitness-for-purpose judgement 4 to both verdicts, so it did not prefer either.

## Caveats

- Two things changed at once between the runs: effort (`high` to `medium`) and structure (one assess call to four concurrent shards plus refine and a verdict call).
- The `high`-effort concurrent rehearsal, run by a sibling worker, separates them; until it is scored, no difference above can be put on either change.
- The key changed between the two scorings: the old run was scored on key sha256 `32c34fcd5628` (commit `22e3e71`), this run on `8eda2e5de12e` (commit `5b464ba`).
- The change rewrote the `core_insight` of F04 and F11, which the matcher reads, plus verification notes and a v2-only flaw; F04 was partial and F11 strict under both keys.
- The old run was not re-scored on the current key, so the F04 and F11 rows are not strictly like for like.
- One document, one run per arm, one judge model family as the agent: no difference here is statistically meaningful.
- All judge and grader costs are the CLI's reported figures, not billed amounts.
- This scoring's `scores.json` records the prereg path as an absolute home-directory path; it is not a credential.
