# Rehearsal run 2 of the concurrent design, at `high` effort (2026-10-03)

The second timed live run of the redesigned agent, this time with the base config (`high` on every stage, deadline 3600 s), measured beside rehearsal 1 (`medium`, demo profile) and the old sequential run at `high`.
Runs used: one Opus run, no rerun, no pre-flight call.

## Result

The run completed in 780.3 s with a full review: verdict `not_fit` at confidence 0.75, 19 graded findings and 2 strengths, outcome `completed_degraded` with five disclosed limitations.
Every stage ran to completion; nothing was cut, no shard was salvaged (`salvaged_calls` 0), no truncation, refusal or fallback.
It would NOT fit the 540 s demo slot: stage 1 alone ended at 560.1 s.
It would fit 900 s with 119.7 s of slack.

## Setup

- Command: `sit-review review eval/synthetic/payments_orchestration/design_v1.pdf --no-tools --run-id rehearsal_concurrent_high_1`, no `--profile`, under `env -u ANTHROPIC_API_KEY` (the key was not set in the shell either).
- Preconditions: `make smoke` passed (selftest and 238 tests); backend `claude_code`; model `claude-opus-5-5` requested and served.
- Config: effort `high` for understand, plan, research, assess, refine, verify and report; deadline 3600 s; stage limits 2820, 3420 and 3540 s; refine reserve 600 s; report reserve 180 s; four shard groups; per-call timeout 1800 s.
- Started 2026-10-03T02:24:30Z (10:24 +08), ended 02:37:30Z (10:37 +08).
- Load average (1, 5, 15 min): 5.85, 6.13, 5.74 before; 9.41, 7.35, 6.96 after.
- Tree: the agent code was `502979a`, but the manifest records `70bd658` with `git_dirty: false`, because another session committed five files under `docs/design/` to this branch at 10:28:42 +08, during the run; no file outside `docs/design/` changed.

## Stages (run clock)

| Stage | Rehearsal 1 (`medium`, demo) | This run (`high`) | Old sequential (`high`) |
|---|---|---|---|
| ingest | 2.2 s | 1.3 s | n/a |
| understand | 121.7 s | 174.9 s | 158 s |
| plan | 71.5 s | 178.3 s | 158 s |
| research | 0.0 s | 0.0 s | n/a |
| assess | longest shard 230.3 s | longest shard 558.8 s | 520 s (one successful attempt) |
| stage 1 end | 232.6 s (limit 265) | 560.1 s (limit 2820) | n/a (sequential) |
| refine | 121.6 s, ending at 354.2 s | 179.2 s, ending at 739.4 s | n/a |
| verify | 0.013 s | 0.016 s | 33 s |
| verdict call (report) | 28.0 s | 40.8 s (report stage 41.1 s) | 88 s |
| total | 382.3 s (`time` 383.1 s) | 780.3 s (`time` 781.3 s) | 3,372 s |

Against rehearsal 1: understand +44 %, plan +149 %, stage 1 +141 %, refine +47 %, verdict call +46 %, total +104 %.
Understand, plan and all four shards started within 1.4 s of the run start, so stage 1 is the longest shard.

## Fit against 540 s and 900 s

- 540 s: no; stage 1 ended 20.1 s past the whole slot, and the demo profile's stage 1 limit (265 s) would have cut all four shards (the shortest took 283.3 s).
- 900 s: yes, the run as measured ends 119.7 s inside it.
- With the demo profile's reserves (75 s report, 200 s refine) a 900 s profile would put stage 1 at 625 s, refine at 825 s and the verdict at 890 s; this run would pass all three (arithmetic only, not run).
- Without shard 2 the longest shard was 413.0 s, so shard 2 alone set 145.8 s of stage 1.

## Shards

| Shard | Wall | Output tokens | Findings produced | Surviving by origin |
|---|---|---|---|---|
| 1 intent_and_fitness | 283.3 s | 34,017 | 14 | 2 |
| 2 requirements_and_consistency | 558.8 s | 74,187 | 17 | 7 |
| 3 claims_and_assumptions | 305.1 s | 36,005 | 13 | 3 |
| 4 risk_and_operations | 413.0 s | 44,358 | 14 | 9 |

Shard 2 is the outlier: 3 CLI turns where every other call of both rehearsals took 2, 71,885 cache-write and 37,739 cache-read tokens against about 25,000 and 6,000 for its siblings, and $2.07 against $0.88 to $1.09.
The extra turn's cause is not verified; the cache-write size fits a second model turn that re-reads a long first answer, and the call still ended `end_turn` with outcome `ok`.

## Review content (counts only)

| | Rehearsal 1 | This run | Old sequential |
|---|---|---|---|
| Verdict | `not_fit`, 0.78 | `not_fit`, 0.75 | `fit_with_conditions`, 0.68 |
| Items in `findings` | 21 | 21 | 21 findings |
| Graded findings | 18: 1 critical, 10 high, 6 medium, 1 low | 19: 1 critical, 11 high, 7 medium, 0 low | not broken down here |
| Strengths | 3 | 2 | n/a |
| Drafts into refine | 53 | 58 | n/a |
| Revised, merged, withdrawn | 21, 32, 0 | 21, 37, 0 | n/a |
| Anchors resolved, unresolved | 131, 0 | 143, 0 (2 per item for 2 items, 3 for 19) | n/a |
| Evidence ledger, registry, sound areas | 128, 56, 13 | 185, 60, 17 | n/a |
| Disclosed limitations | 3 | 5 | n/a |

Rehearsal 1's note gives "21 findings (1 critical, 10 high, 6 medium, 1 low) and 3 strengths"; by script the 21 items include the 3 strengths, so it has 18 graded findings.
Every criterion has outcome `findings`; no criterion is `not_assessed`.
The five limitations: no PDF image block (DEG-001), no tools (DEG-002), and three recommendations that appear to reverse approved decisions without a challenge label: FND-049 against AD-006, FND-047 against AD-011, FND-029 against AD-012 (DEG-003 to DEG-005).
Which verdict is closer to the answer key was not checked; scoring is the sibling worker's job and the answer key was not opened.

## Cost and tokens (CLI estimate, 8 calls, all measured)

| | Rehearsal 1 | This run | Old sequential |
|---|---|---|---|
| Cost | $5.74 | $8.21 | $3.68 recorded |
| Output tokens | 148,957 | 258,222 | 116,264 |
| Input tokens (manifest) | 344,584 | 378,856 | n/a |
| Cache written, read | 344,568, 0 | 378,838, 71,971 | n/a |

Unlike rehearsal 1, every call of this run read 3,379 to 37,739 tokens from the cache; the cause is not verified.

## Console

The first draft finding line reached the console at 2:13 (133 s), against 1:17 (77 s) in rehearsal 1; registry drafts streamed from 1:50 and plan questions from 1:53.

## Replay

`dra replay docs/live_runs/rehearsal_concurrent_high_1` exits 0 in 2.17 s and the replayed report matches the recording (rehearsal 1: exit 0, 2.38 s).
The 185 ledger IDs and the 21 finding IDs of the replay are identical to the recording, in order.

## Agent defect: merged-away finding IDs stay in the report

Refine merges drafts into survivors, but the free text that cites a draft ID is not remapped, so the rendered report names findings that do not exist in it.
In this run: the `decision_preservation` coverage note cites FND-003, FND-008 and FND-011; sound area SA-009 cites FND-004 and FND-013; strength FND-014 cites FND-002.
All six were produced by shard 1 (`llm-0003`) and merged away by refine (`finding_meta` history verb `merged`).
Rehearsal 1 has the same defect in its findings (FND-003 and FND-010 cited, neither in its report); nothing in `agent/` or `harness/` was changed.

## What is and is not in this directory

- Committed: `report.md`, `report.json`, `manifest.json`, `effective_config.json`, `state.json`, `llm.jsonl`, `anchors.json`, `ledger.json`, `ledger.jsonl`, `checkpoints/` (8 files), `shards/` (4 files), `text/` (2 files), `snapshots/` (empty, not tracked by git).
- Left out: `progress.log`, excluded by `.gitignore`, as in rehearsal 1.
- Secret scan, counts only: `sk-` 105 hits, all inside `risk-` (0 not preceded by `ri`); `Bearer` 0; `oauth` 0 (any case); e-mail pattern 0.
- `api_key` hits are the field name `inherit_api_key` and the env-var name `SIT_MCP_API_KEY`; no `ANTHROPIC_` name appears.
- One home-directory path is committed, `effective_config.json` `config_root`, per precedent.

## Not verified

- Why shard 2 took a third CLI turn and why cache reads appeared in this run and not in rehearsal 1.
- The effect of the Mac's load (rising to 9.4) on the timings, and the true billed cost.
- That a 900 s profile would behave as the arithmetic above says; no such profile was run.
- Any run with tools; nothing touched the SIT MCP hosts.
- Which of the three verdicts is closer to the answer key.
