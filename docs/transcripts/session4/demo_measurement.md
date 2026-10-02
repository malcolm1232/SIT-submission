# Session 4: demo measurement report (2026-10-03)

Worker: the retry of the demo-measurement worker, which was stopped by a model-side safeguard before it did anything.
Branch `s4/demo`, from `2d84f59`, in the worktree `SIT-wt/demo`.
Nothing was pushed.
The numbers, the arithmetic and the secret scan are in `docs/live_runs/demo_profile_measure_1/MEASUREMENT.md`.

## Result

The demo profile does not produce a review inside its 540 s deadline at `medium`.
The one measurement run ended at 420 s with exit 0 and a report that says "not assessed": verdict `not_assessed`, confidence 0, no findings.
Understand took 136 s and plan 102 s, so assess started at 241 s and was cut by the deadline after 179 s, at the 420 s limit that protects verify and report.
The first live run at `high` gave 21 findings and `fit_with_conditions` at 0.68; this run lost all 21 findings, all 5 sound areas and the verdict.
Every skipped or cut phase is disclosed in the report (DEG-001 to DEG-004).

## Runs and spend

| What | Calls | Cost (CLI estimate) | Result |
|---|---|---|---|
| Haiku pre-flight (`scripts/smoke_claude_code_backend.py --model claude-haiku-4-5 --effort low`) | 1 | $0.0062 | exit 0, 13.6 s |
| Measurement run `demo_profile_measure_1`, Opus 5.5 | 3 | $1.10 recorded, about $1.9 estimated with the cut call | exit 0, 420.9 s, not assessed |

One of the two allowed Opus runs was used.
The second was not used: its only allowed purpose here was to confirm a reserve adjustment, and no reserve adjustment can make the run fit (arithmetic in the note).
No tool call, no scoring or grading run, nothing against the SIT MCP hosts, nothing on the SIT Memory Platform PDF.

## Per-phase numbers

| Phase | Wall | Output tokens | Cost | Effort | Attempts | Cache creation / read |
|---|---|---|---|---|---|---|
| ingest | 3.5 s | n/a | 0 | n/a | n/a | n/a |
| understand | 135.9 s | 18,033 | $0.608 | medium | 1 | 30,890 / 0 |
| plan | 101.7 s | 10,065 | $0.493 | medium | 1 | 36,480 / 0 |
| research | 0.0 s (no tools) | 0 | 0 | low | 0 | n/a |
| assess | 178.9 s, cut | not recorded | not recorded | medium | 1 | not recorded |
| refine | skipped | 0 | 0 | medium | 0 | n/a |
| verify | 0.007 s, no model call | 0 | 0 | medium | 0 | n/a |
| report | 0.11 s, no model call | 0 | 0 | medium | 0 | n/a |
| total | 420.1 s | 28,098 recorded | $1.10 recorded | | 3 calls | 67,370 / 0 |

## Answers to the brief

- **Inside 540 s?** Yes, by 120 s, but only because the report had nothing to say; the slack is the unused verify and report reserve.
- **Reserves.** Not changed.
  The time is lost before assess starts (241 s), not in a reserve; even a report reserve of 0 gives assess 299 s against an estimated need of 310 to 420 s.
  `report_reserve_seconds: 120` was not exercised, since verify and report made no model call.
- **Live or replay?** Recommendation: a pre-recorded run shown with `dra replay`, with a live run started alongside at `--deadline 900` or more.
  A complete document-only run at `medium` is estimated at 600 to 770 s without refine, so it does not fit a 10-minute slot.
  A complete recorded run at the demo settings does not exist yet; this directory replays a not-assessed report.
  The decision is the planner's.
- **Prompt cache.** Not read between phases: 67,370 cache-creation tokens and 0 cache-read tokens.
- **Replay.** `dra replay docs/live_runs/demo_profile_measure_1` exits 0 in 3 to 4 s with `claude` off the `PATH`; the replayed report matches the recording.
- **Secret scan.** No credential-shaped value in any file; details and the two judgement calls (session IDs kept, `config_root` path kept on the precedent of the first live run) are in the note.

## Files changed

| File | Change |
|---|---|
| `docs/live_runs/demo_profile_measure_1/` | The run directory (17 files) and `MEASUREMENT.md`; `progress.log` left out by `.gitignore`, as in the first live run |
| `config/profiles/demo.yaml` | Comments only: the header and two reserve comments now state what was measured; no value and no line number changed |
| `docs/DEMO_DAY_RUNBOOK.md` | Section 5, the 0:30 row: the "UNMEASURED estimates" sentence replaced by the measured note; section 4.1 untouched |
| `docs/transcripts/session4/demo_measurement.md` | This report |

Not edited: `docs/BUDGET.md`, `docs/HANDOVER_FULL.md`, anything under `agent/` or `harness/`, any test.

## Gates

`ruff check agent harness tests` exit 0.
`pytest -q` exit 0, 1023 passed.
`make smoke` exit 0 (196 tests), before the run and again on the final tree.

## Agent observations (described, not fixed)

1. A model call cut by the deadline is logged with zero usage and no cost (`llm.jsonl` `llm-0003`, `outcome: LLMDeadlineError`), so the manifest's $1.10 leaves out the cut assess call.
2. The manifest records the branch as `demo` for `s4/demo` (`agent/sit_review_agent/manifest.py` line 86, last segment of the ref only).
3. `report.md` prints one location twice in "Located at: p.1 §1, p.2 §1, p.2 §1".
4. When assess is cut, the 120 s verify and report reserve is held back for a report that then needs 0.1 s.
5. Runbook section 4's short rerun (`--profile demo --deadline 300`) cannot reach assess: it leaves 180 s for understand, plan and assess, and understand plus plan took 238 s.

The known exit 3 gap (a stage truncated twice at the output cap) was not seen; no call came near the cap.

## Conditions of the run

The Mac (8 cores) was running other workers' jobs.
Load average: 8.76 / 9.99 / 10.09 just before the run, 11.43 / 10.87 / 10.47 just after.
The run's own process used 14.8 s of CPU in 421 s of wall time.

## Refused or stopped

No tool call was refused in this run.
One slip of mine: the first count-only secret scan used `cd` inside a compound command instead of a subshell; it was read-only and changed nothing.

## Not verified

- Assess, refine, verify and report at `medium` to completion.
- Opus 5.5 through `claude -p` above 64,000 output tokens.
- The true billed cost of the run, and where nested `claude -p` calls are billed.
- Any run with tools.
- The effect of the machine's load on the timings.
- A live run at `low` effort, which is the only remaining lever for a live run inside 540 s.
