# Session 4: rehearsal run 2 of the concurrent design, at `high` effort (2026-10-03)

Worker: one Opus worker, on the owner's "go" for the `high` rehearsal (the scoring of both runs is a sibling worker's job).
Branch `s4/rehearsal`, from `502979a`, in the worktree `SIT-wt/rehearsal`.
The numbers, the arithmetic and the secret scan are in `docs/live_runs/rehearsal_concurrent_high_1/MEASUREMENT.md`.

## Result

The base config (`high` on every stage, deadline 3600 s, no profile) produced a full review in 780.3 s by the manifest, 781.3 s by `/usr/bin/time`.
Verdict `not_fit` at confidence 0.75, 19 graded findings (1 critical, 11 high, 7 medium) and 2 strengths, outcome `completed_degraded` with five disclosed limitations.
Nothing was cut, salvaged, truncated or refused; every criterion has findings.
It does not fit 540 s (stage 1 ended at 560.1 s) and fits 900 s with 119.7 s of slack.

## Runs and spend

| What | Calls | Cost (CLI estimate) | Result |
|---|---|---|---|
| `rehearsal_concurrent_high_1`, Opus 5.5, `--no-tools`, base config | 8, all measured | $8.21 | exit 0, 781.3 s, `completed_degraded` |

One Opus run, no rerun.
Output 258,222 tokens, input 378,856 tokens, cache written 378,838 and read 71,971.
No tool call, no scoring or grading, nothing against the SIT MCP hosts, the answer key not opened.

## Three runs side by side

| | Rehearsal 1 (`medium`, demo) | This run (`high`) | Old sequential (`high`) |
|---|---|---|---|
| understand | 121.7 s | 174.9 s | 158 s |
| plan | 71.5 s | 178.3 s | 158 s |
| assess | 230.3 s (longest shard) | 558.8 s (longest shard) | 520 s (one attempt) |
| refine | 121.6 s | 179.2 s | n/a |
| verdict call | 28.0 s | 40.8 s | 88 s (report) |
| total | 382.3 s | 780.3 s | 3,372 s |
| verdict | `not_fit` 0.78 | `not_fit` 0.75 | `fit_with_conditions` 0.68 |
| findings | 18 + 3 strengths | 19 + 2 strengths | 21 |
| output tokens | 148,957 | 258,222 | 116,264 |
| cost | $5.74 | $8.21 | $3.68 |

Shards at `high`: 283.3, 558.8, 305.1 and 413.0 s; 34,017, 74,187, 36,005 and 44,358 output tokens; 14, 17, 13 and 14 findings; 2, 7, 3 and 9 surviving.
Shard 2 took 3 CLI turns where every other call of both rehearsals took 2, and alone set 145.8 s of stage 1; the cause is not verified.
Refine received 58 drafts, revised 21, merged 37, withdrew 0; 143 anchors resolved, none unresolved.
First draft finding on the console at 133 s (rehearsal 1: 77 s).
`dra replay` exits 0 in 2.17 s; the replay's 185 ledger IDs and 21 finding IDs match the recording.

## Findings about the agent

- Merged-away draft IDs stay in the report text: the `decision_preservation` coverage note cites FND-003, FND-008 and FND-011, sound area SA-009 cites FND-004 and FND-013, and strength FND-014 cites FND-002; none is in the report, all six were merged by refine.
- Rehearsal 1 has the same defect (FND-003 and FND-010 cited in its findings); it is described, not fixed.
- Rehearsal 1's note counts its 3 strengths inside "21 findings" while listing severities that sum to 18; the corrected counts are in the new note.

## Notes on the session

- Another session committed five files under `docs/design/` to `s4/rehearsal` (`70bd658`, 10:28:42 +08) while the run was going, so the manifest records `70bd658`; no agent code changed.
- The Mac's load average rose from 5.85 to 9.41 over the run.
- Nothing was refused.
