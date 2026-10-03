# Session 4: rehearsal run 1 of the concurrent design (2026-10-03)

Workers: the rehearsal worker, which ran the measurement and was stopped by a tool-layer classifier just before committing, and this follow-up worker, which wrote the note and committed.
Branch `s4/rehearsal`, from `d008a74`, in the worktree `SIT-wt/rehearsal`.
The numbers, the arithmetic and the secret scan are in `docs/live_runs/rehearsal_concurrent_1/MEASUREMENT.md`.

## Result

The redesigned agent produced a full review inside the 540 s demo slot: 382.3 s by the manifest, 383.1 s by `/usr/bin/time`, against a predicted 443 s.
Verdict `not_fit` at confidence 0.78, 21 findings (1 critical, 10 high, 6 medium, 1 low) and 3 strengths, outcome `completed_degraded` with three disclosed limitations (no PDF image block, no tools, FND-009 appears to reverse AD-006 without a challenge label).
Refine and the verdict call both ran; nothing was cut and no shard was salvaged.
Slack against 540 s: 157.7 s.

## Runs and spend

| What | Calls | Cost (CLI estimate) | Result |
|---|---|---|---|
| Haiku pre-flight | 1 | $0.0048 | exit 0 |
| Rehearsal run `rehearsal_concurrent_1`, Opus 5.5, `--profile demo --no-tools` | 8, all measured | $5.74 | exit 0, 383.1 s, `completed_degraded` |

One of the two approved Opus runs was used.
Output 148,957 tokens, input 344,584 tokens, all cache writes and no cache reads.
No tool call, no scoring or grading run, nothing against the SIT MCP hosts.

## Measured against predicted

| Stage | Measured | Predicted | Delta |
|---|---|---|---|
| understand | 121.7 s | 136 s | -10 % |
| plan | 71.5 s | 102 s | -30 % |
| assess, stage 1 end | 232.6 s (longest shard 230.3 s) | 208 s | +12 %, limit 265 s |
| merge | 0.0 s | n/a | |
| refine | 121.6 s, ending at 354.2 s | 175 s | -30 % |
| verify | 0.013 s | n/a | |
| verdict call | 28.0 s | 52 s | -46 % |
| total | 382.3 s | 443 s | -14 % |

Shards: 1 = 218.0 s, 27,109 output tokens, 14 findings; 2 = 230.3 s, 28,005, 14; 3 = 209.9 s, 25,570, 12; 4 = 201.6 s, 24,763, 13.
Surviving findings by shard of origin: 10, 5, 3, 3.
Refine received 53 merged findings, revised 21, merged 32, withdrew 0; 131 anchors resolved, none unresolved.

## Answers to the brief

- **Inside 540 s?** Yes, by 157.7 s, with every stage run in full.
- **Shard count.** K stays at 4: stage 1 ended 2.6 s past the 230 s tuning threshold with 158 s of slack, so no retuning was warranted.
- **Run 2.** Not run; it is reserved for a `high`-effort run pending the owner's word, because the lab brief sets no time limit and the 540 s slot is a project assumption (audit item U4).
- **Comparison.** The first live run at `high` on the old sequential design gave 21 findings and `fit_with_conditions` at 0.68; this run gave 21 findings and `not_fit` at 0.78; neither was scored against the answer key.
- **Prompt cache.** Not read between calls; each stage's first call shows 2 uncached input tokens plus 28k to 34k cache-write tokens, so the hermetic overhead of `--setting-sources ''` cannot be separated in a real run.
- **Replay.** `dra replay docs/live_runs/rehearsal_concurrent_1` exits 0 in 2.48 s; the report matches and the 128 ledger IDs are identical.
- **Secret scan.** Counts only: `sk-` 23, all inside `risk-` in the document text; `Bearer` 0; `oauth` 0; e-mail pattern 0; the `Authorization`, `session` and `api_key` hits are document text, CLI session IDs and field or env-var names, as detailed in the note.

## Files changed

| File | Change |
|---|---|
| `docs/live_runs/rehearsal_concurrent_1/` | The run directory and `MEASUREMENT.md`; `progress.log` left out by `.gitignore`, as in `demo_profile_measure_1` |
| `docs/transcripts/session4/rehearsal_1.md` | This report |

Not edited: any config, any file under `agent/` or `harness/`, any test, `docs/BUDGET.md`, `docs/HANDOVER_FULL.md`.

## Conditions of the run

The Mac was running other lanes, with a load average of about 5.
The run started at 10:09 +08 and ended at 10:15 +08 on 2026-10-03.

## Refused or stopped

The first worker completed the run, the replay and the secret scan, and was stopped by a tool-layer classifier at its commit step; nothing had been committed.
This follow-up worker made no model call and started no run; it confirmed the run directory's file names and the count-only secret greps, wrote the note and this record, committed the run directory with both files, and pushed.
No tool call of this follow-up worker was refused.

## Not verified

- The hermetic overhead of `--setting-sources ''` as a separate number.
- Any run with tools.
- The true billed cost, and the effect of the Mac's load on the timings.
- A `high`-effort run of the concurrent design.
- Which of the two verdicts on the payments design is closer to the answer key.
