# Re-assessment rehearsal 1: design v2 against the v1 review (2026-10-03)

The first live run of the re-assessment path that the lab brief asks for (p.3 §1.5): the agent takes the updated artefact and the prior review, re-assesses, and recommends further.
Runs used: one Opus run of the two approved; the second was not needed.

## Mechanism

- Command, from the repo root: `env -u ANTHROPIC_API_KEY .venv/bin/dra review eval/synthetic/payments_orchestration/design_v2.pdf --profile demo --no-tools --previous docs/live_runs/rehearsal_concurrent_1 --run-id reassess_payments_v2_1`.
- `--previous` (`agent/sit_review_agent/cli.py:111`) reads the prior run's `report.json` and its canonical text `text/DOC-design_v1.pages.txt` (`orchestrator.py:856-875`), so no v1 PDF is needed.
- The report states `review_mode: delta`, `prior_review_id: REV-rehearsal_concurrent_1`, the v1.1 document under review and the v1.0 document as `prior_version`, and the manifest records `previous_run_id: rehearsal_concurrent_1`.
- The runbook's promise (`docs/DEMO_DAY_RUNBOOK.md:129`, "add `--previous runs/sit_v1_frozen`") matches the code.

## Result

- Exit 0, outcome `completed_degraded`, verdict `not_fit` at confidence 0.75 (v1 review: `not_fit` at 0.78).
- 19 findings: 1 critical, 8 high, 7 medium, 1 low, plus 2 strengths (the two resolved items are rendered as strengths).
- Wall 422.8 s in the manifest, 425.1 s by `/usr/bin/time`; slack 117 s against the 540 s slot.
- Cost $4.50 by the CLI's estimate, a lower bound: the three assess calls cut by the stage limit have no recorded usage.
- Recorded tokens: 375,052 input, 75,068 output, 8 calls.
- Tree: branch `s4/delta` at `886c3fc`, clean (`git_dirty: false`).
- Started 2026-10-03T08:07:42Z (16:07 +08), ended 08:14:45Z; the Mac's load average was about 10 to 12 at the end.

## Stages (run clock)

| Stage | Seconds | Span | Note |
|---|---|---|---|
| ingest | 2.3 | | code only, two documents |
| understand | 135.9 | 2.3 to 138.1 | |
| plan | 72.2 | 2.3 to 74.4 | |
| research | 0.0 | | `--no-tools`, disclosed |
| assess (4 shards) | 262.9 | 2.3 to 265.2 | three of four shards cut by the 265 s stage 1 limit |
| refine | 129.1 | 265.3 to 394.3 | ran in full |
| verify | 0.012 | | no model call |
| verdict call | 28.6 | about 394 to 423 | ran in full |
| total | 422.8 | | |

- Shards 1, 2 and 3 were cut at 265 s and salvaged (`salvaged_calls` 3), keeping 10, 12 and 9 finished findings (DEG-003 to DEG-005).
- Shard 1's cut left criterion `design_intent` not assessed (DEG-003).
- The v1 rehearsal's assess took 230.3 s with nothing cut; this run carried two documents and ran under a load of about 10, so which of the two caused the cut is not separated.

## Delta classification

| Status | Count | Findings |
|---|---|---|
| resolved | 2 | FND-046 (was FND-046), FND-047 (was FND-009) |
| partially addressed | 4 | FND-013 (was FND-004), FND-030 (was FND-029), FND-044 (was FND-020), FND-022 (was FND-046) |
| still open | 10 | FND-001, 003, 008, 006, 004, 005, 020, 021, 031, 043 |
| new in update | 3 | FND-002, FND-014, FND-041 |

- None of the 19 reassessments is the code fallback of `verify.py:483` ("no reassessment given"); every status came from the model.
- Prior FND-046 is cited twice: resolved for the payout approval controls, and partially addressed for the "optional TOTP" text left in Section 18.1.

## Against the v2 revision history (no answer key opened)

The v2 revision-history table names the changed areas: FR-8; NFR-4, NFR-6, NFR-8; idempotency and cross-region replication (Sections 9, 20, 24); CVC handling (11.2, 12.4); reconciliation scheduling (16.2); merchant authentication and payout changes (18); acceptance criteria (26).
The eval notes say six flaws were fixed and the idempotency fix introduced one critical cross-region idempotency race.
Six v1 findings sit on those changed areas, and the agent classified them as follows.

| v1 finding (topic) | Changed area | v2 classification |
|---|---|---|
| FND-009 DynamoDB partition and LSI sizing | 9, 24 | resolved (FND-047) |
| FND-046 payout bank account change | 18 | resolved (FND-046), residue partial (FND-022) |
| FND-004 zero RPO under async replication | NFR-4, 20 | partially addressed (FND-013) |
| FND-029 CVC retained after authorization | 11.2, 12.4 | partially addressed (FND-030) |
| FND-020 08:00 SGT report deadline | NFR-8, 16.2 | partially addressed (FND-044) |
| FND-011 FR-8 "2%" tolerance unit | FR-8 | not cited at all |

- So the agent marked 2 resolved, 3 partially addressed and dropped 1 silently, against about 6 expected resolved; it leans to "partially addressed" where the fix leaves a residue it can name.
- The regression is caught: FND-002 "Cross-region idempotency lock relies on a conditional put to an eventually consistent, both-writable global table" is new in update, high (the eval notes call the regression critical).
- Two further new findings (CDE left out of the regional DR plan, relayed MSK events lost on failover) also follow the new cross-region text; whether they are true flaws or false positives is not graded.
- This mapping is mine from section numbers and titles, not a grade against the answer key.

## Prior findings not accounted for

- Three v1 findings are cited by no v2 finding and appear in no delta group: FND-011 (FR-8 tolerance, a changed area), FND-039 (cross-acquirer soft-decline cascading) and FND-012 (readiness marked "Ready").
- The v1 strengths FND-013, FND-014 and FND-053 are also not cited; the v2 report lists its own sound areas SA-001 to SA-003 instead.
- Nothing in the code requires every prior finding to be classified: `models.py:747-755` checks only that each finding of this run carries a reassessment.
- A shard cut (DEG-003 to DEG-005) can drop a prior finding the same way, so a reader cannot tell "fixed" from "not re-examined" for these three.

## What the agent said changed (report.md)

1. Payout bank account change controls now protect against account takeover, and the DynamoDB key and capacity sizing now spread the largest merchant's load: both resolved.
2. NFR-4, CVC handling, the 08:00 report deadline and the MFA text were revised but each leaves a named gap (no recovery mechanism, an unconfirmed PCI reading, no behaviour for a late file, "optional TOTP" still in 18.1).
3. The critical Redis idempotency fast path, the Fraud Hook detokenising PAN, the single CloudHSM, cascade duplicates, the latency budget and the first-cohort go-live are unchanged.
4. The new cross-region idempotency design is unsafe: a conditional put on a both-writable, eventually consistent global table cannot guarantee one lock holder.
5. The new regional DR plan omits the CDE and loses relayed events on failover; the verdict stays `not_fit` at 0.75.

## UI

- `dra ui --port 8797 --runs-dir docs/live_runs` shows the run with tabs Review, Delta, Coverage, Evidence and Run log; the Delta tab groups 2, 4, 10 and 3 under the four headings of the design note and shows the previous verdict beside the new one.
- Screenshot at 1440 px: `docs/design/ui_mockup/for_him_ui_delta.png`; no console errors, no horizontal scroll.
- The Delta rows do not show the prior ID or the reassessment note, which the design note §7 asks for (`app.js:625-634`; they appear only in the finding detail, `app.js:552-553`).

## What is and is not in this directory

- Committed: `report.md`, `report.json`, `manifest.json`, `effective_config.json`, `state.json`, `llm.jsonl`, `anchors.json`, `ledger.json`, `ledger.jsonl`, `checkpoints/` (8 files), `shards/` (4 files), `text/` (4 files, v1 and v2).
- Left out: `progress.log` (excluded by `.gitignore` and by the brief) and `progress.jsonl` (ignored by `.gitignore`).
- Secret scan, counts only, without `progress.log`: `sk-` 24 hits, all inside the word `risk-` (0 hits not preceded by `ri`); `Bearer` 0; `oauth` 0; e-mail pattern 0.

## Not verified

- Any grade against the answer key; the resolved and regression mapping above is by section and title only.
- Whether the three shard cuts came from the second document or from the Mac's load.
- The true billed cost, including the three cut calls.
- `dra replay` of this delta run.
- Any run with tools; nothing touched the SIT MCP hosts.
