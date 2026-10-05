# Worker note: plan D write-up (2026-10-05)

Under the owner's word of 4 Oct 2026 22:40 ("yes" to plan D) and the planner's delegated shot calling (3 Oct 02:50).
Branch `s4/plan-d-writeup` from `origin/claude/happy-darwin-d0bl94` at 6ca319d, with `s4/plan-d-runs`, `s4/plan-d-b0` and `s4/plan-d-grade` merged in (no conflicts); nothing pushed, a cold reader checks the numbers and a verifier pushes.
No live model call was made.
Not opened: `eval/blind/`, any folder under `docs/live_runs/` other than `plan_d/`; `docs/live_runs/QUALITY_COMPARISON.md` was read by grep only and appended to.
No model output or finding text was printed: the scripts read `scores.json`, `manifest.json`, `effective_config.json`, `report.json` degradation types and `llm.jsonl` or `judge_calls.jsonl` outcomes and timestamps, and print counts, metric values, commits and times only.
The scripts are in the session scratchpad under `plan_d_writeup/` (`extract.py`, `totals.py`, `manif.py`, `limit2.py`, `limit3.py`, `c2.py`, `deg.py`, `keys.py`).

## What was written

- `docs/COMPARISON_PLAN_D.md`: the nine sections of the brief.
- `docs/EXPLAIN_AS_IT_RUNS.md`: a short paragraph at the end of section 6 with the headline numbers; the four `[TO FILL FROM REHEARSAL 2]` lines are untouched.
- `docs/live_runs/QUALITY_COMPARISON.md`: one line appended at its end pointing at the new file.

## Findings worth the planner's attention

- The FULL scorings were made without `--condition`, so their `scores.json` `inputs.condition` is null and `sit-eval aggregate` files them as `unlabelled`.
  `--compare FULL --compare B0` as briefed pairs no documents; the reported comparison is `--compare unlabelled --compare B0`, which pairs all eight, and no score file was edited.
  The prereg pilot checkpoint therefore reads `not_evaluable` ("no FULL run in the inputs"); by hand, the FULL lower-bound median cost $6.15 exceeds the $3.24 threshold, which the rule calls `fail`.
- Running eight of the ten documents named in prereg deviation entry 13 is not yet recorded in `eval/prereg_deviations.md`.
- The FULL runs are at eba6974 and B0 at 280c4b4; the per-run commits in the manifests differ from those only under `docs/`, but 280c4b4 changed files on the FULL path to add B0, and FULL was not run there.
- `d_payments_v1_high` had 7 of 10 calls cut at a deadline, so the high arm of the ablation is confounded by time limits; its $1.36 is a far lower bound.
- The first refused call of the session limit is at 06:05:32 SGT (`d_consent_v2_1/llm.jsonl`), so the consent v2 first attempt was also a casualty of the limit.
- The v2 diagnosis appeared at `~/Desktop/SIT-wt/v2-diag/docs/transcripts/session6/v2-diagnosis.md` (commit 2a91b83 on `s4/v2-diag`) while this was written; its classification and its INV-04 finding are summarised with that source and marked unverified.
- Two judge-cap stops recorded spend below the $18 cap ($15.90 and $15.62); the records do not say why, and the file says so.

## Checks

- `scripts/leakage_grep.py` printed `PASS: no unresolved hit in a gated area`, `python -m sit_review_agent.prompts --check` printed `PROMPTS.lock up to date (bundle 2569a967015b)`, and `tests/test_export_public_snapshot.py` gave `65 passed`.
- No em dash in any written file, and one sentence per line.
- No test suite was run beyond those: the change is documentation only.
- Every numeric claim was re-derived by script from the run folders or recomputed from the committed tables; the strict recall totals 98 of 112 and 88 of 112 agree with the tables.
