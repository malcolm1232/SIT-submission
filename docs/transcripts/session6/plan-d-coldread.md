# Worker note: cold read of the plan D write-up (2026-10-05)

Under the owner's "yes" to plan D (4 Oct 2026 22:40) and the planner's delegated shot calling (3 Oct 2026 02:50).
Cold read and verification of `docs/COMPARISON_PLAN_D.md` at 21b7977 on `s4/plan-d-writeup`.
No live model call was made.
Not opened: `eval/blind/`, any folder under `docs/live_runs/` other than `plan_d/`; `docs/live_runs/QUALITY_COMPARISON.md` was read by grep only.
No model output or finding text was printed: the scripts read metric fields of `scores.json`, `manifest.json` costs and commits, `effective_config.json` effort, `report.json` degradation types, and the `outcome`, timestamp and cost fields of `llm.jsonl` and `judge_calls.jsonl`.
Scripts: session scratchpad `coldread_pland/` (`extract.py`, `more.py`, `llm.py`, `judgecost.py`).

## Numbers checked

- Every per-document row of section 2 against `scores.json` and the three tables: all match.
- Totals recomputed: strict 98 and 88 of 112, lenient 106 and 101 of 112, flags 0 of 170 and 0 of 118, mean strict precision 0.594 and 0.755, adjudicated 0.883 and 0.973, severity 0.896 and 0.856, critical 0.906 and 0.906, scoring cost $42.63 (FULL).
- Two cent-level differences: summed before rounding, FULL run cost is $50.40 (rows sum to $50.39) and B0 scoring cost $25.39 (rows sum to $25.38); the table keeps the row sums and a sentence now gives both.
- The wall column is `RUNS.md` "wall s"; the manifests' `wall_clock_s` sum to 3,418.8 s and 2,188.8 s, within 3 s per run; stated.
- Aggregate re-run (`sit-eval aggregate` over the 16 v1 scores, `--compare unlabelled --compare B0 --exploratory`, `runs/aggregate_plan_d_coldread.json`): identical to the builder's apart from input order; +0.089, bootstrap +0.036 to +0.152, sign-flip 0.0625, permutation 0.0117, McNemar 0.0129, and every other row of the aggregate table match.
- Sections 3 to 6, the times of section 1, the per-run commits (all differ from eba6974 or 280c4b4 only under `docs/`), the degradation counts and the grades (mean S 82.15, $43.43 and $45.86) match.
- The first hand-stopped iot v2 scoring: its judge log holds 340 entries, 294 errored, where `RUNS.md` says 291 of 337; both are now in the file.

## Fixes made

1. Section 1: the eight-of-ten ruling now cites `docs/SEALING.md` (access budget S-heldout 3) and the unsigned keys, and names entry 14.
2. `eval/prereg_deviations.md` entry 14 appended.
3. Section 2: the unrounded cost sums and the wall source.
4. Section 6: the two rescores reused cached judge answers (103 of 126, 113 of 124), so their $11.33 and $5.00 cover only the live calls; the refine fix in progress (worktree branch `s4/refine-prior-status`, nothing committed) and what the v2 precision therefore describes.
5. Section 7, INV-05: the fix commits are 6980c33, e0c7925, 2ef95e4, 6ca319d plus 6ca33e7; 0da6c61 and 88abd54 are notes; the cause is fixed on the tip, the fixed code was not re-run on hospital; no run commit contains 6980c33 (checked for all 24 manifest commits).
6. Section 7, judge caps: the gap is sourced (below).
7. Section 8: six caveats added (unlabelled scorings and the checkpoint, hospital row, session limit, judge caps, effort ablation, v2 figures); the held-out bullet points at entry 14.
8. Section 9: the three sentences tightened (below).

## Source gaps

- Why the $18 cap fired at $15.90 and $15.62: `harness/sit_eval/calls.py` `JudgeRunner._check_budget` refuses a new call when committed spend plus a reserve for each call in flight and for the next call passes the cap; the reserve is `max_budget_usd_per_call` 1.0 (`harness/sit_eval/config.py`, recorded as `calls.budget.reserve_usd` 1.0), so at concurrency 4 it can stop once committed spend passes $14, and the recorded figure is the committed spend after the in-flight calls finished. The judge logs show 103 calls at $15.90 and 67 calls at $15.62.
- Cost of the hand-stopped first iot v2 scoring: $5.03 by its judge log (46 ok calls), so iot v2 scoring spent $25.65 in all; lakehouse $27.23.

## Section 9 as it now reads

- "In an exploratory test on eight synthetic design documents with 14 planted flaws each, one run per document, the agent matched 98 of 112 flaws strictly (recall 0.875), against 88 of 112 (0.786) for a single model call on the same documents."
- "The paired gain is +0.089 in strict recall, with a 95 percent bootstrap interval of +0.036 to +0.152, but the document-level sign-flip test gives only p = 0.0625, because five documents favoured the agent and three tied."
- "The scorer flagged no finding as hallucinated in any of the agent's fourteen scored v1 runs (0 of 170 findings on the eight compared runs, without the grounding judges), and a key-blind grader of the same model family passed all eight reviews at grade B, mean 82.15 of 100."

The old third sentence called the grader "independent"; it is the same model family as the agent and the judge, so the word was dropped.
