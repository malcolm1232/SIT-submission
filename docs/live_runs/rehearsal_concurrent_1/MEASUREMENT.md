# Rehearsal run 1 of the concurrent design (2026-10-03)

The first timed live run of the redesigned agent (four concurrent assess shards, merge, refine, verdict call), measured against the 540 s demo slot.
Runs used: one Opus run of the two approved, plus one Haiku pre-flight call ($0.0048).

## Result

The run completed in 382.3 s with a full review: verdict `not_fit` at confidence 0.78, 21 findings and 3 strengths, outcome `completed_degraded` with three disclosed limitations.
Every stage ran to completion; refine and the verdict call were not cut, and no shard was salvaged (`salvaged_calls` 0).
Slack against the 540 s slot: 157.7 s.

## Setup

- Command: `--profile demo --no-tools` on `eval/synthetic/payments_orchestration/design_v1.pdf`, run id `rehearsal_concurrent_1`.
- Tree: branch `s4/rehearsal` at `d008a74`, clean (`git_dirty: false` in the manifest).
- Model `claude-opus-5-5` requested and served through the `claude_code` backend; every argv carries `--setting-sources ''`.
- Started 2026-10-03T02:09:22Z (10:09 +08), ended 02:15:44Z (10:15 +08); the Mac's load average was about 5.
- Stop parameters: deadline 540 s, `stage_1_end` 265 s, `refine_end` 465 s, `verdict_end` 530 s, refine reserve 200 s, report reserve 75 s.
- Manifest: `assess_shards` 4, `salvaged_calls` 0, timing spans present, `wall_clock_s` 382.274, fault injection `none`.

## Measured against predicted (run clock)

| Stage | Measured | Predicted | Delta | Note |
|---|---|---|---|---|
| ingest | 2.2 s | n/a | | code only |
| understand | 121.7 s | 136 s | -10 % | |
| plan | 71.5 s | 102 s | -30 % | |
| research | 0.0 s | n/a | | `--no-tools`, disclosed |
| assess (4 shards) | longest 230.3 s; stage 1 ended at 232.6 s | 208 s | +12 % | limit 265 s; all shards started at about 2.3 s into the stage |
| merge | 0.0 s | n/a | | code only |
| refine | 121.6 s, ending at 354.2 s | 175 s | -30 % | ran in full |
| verify | 0.013 s | n/a | | no model call |
| verdict call | 28.0 s | 52 s | -46 % | ran in full |
| total | 382.3 s (manifest), 383.1 s (`/usr/bin/time`) | 443 s | -14 % | slack 157.7 s against 540 s |

Stage 1 ended 2.6 s past the 230 s tuning threshold and 32.4 s inside its 265 s limit.

## Shards

| Shard | Wall | Output tokens | Findings produced | Findings surviving by origin |
|---|---|---|---|---|
| 1 intent_and_fitness | 218.0 s | 27,109 | 14 | 10 |
| 2 requirements_and_consistency | 230.3 s | 28,005 | 14 | 5 |
| 3 claims_and_assumptions | 209.9 s | 25,570 | 12 | 3 |
| 4 risk_and_operations | 201.6 s | 24,763 | 13 | 3 |

Refine received 53 merged findings, revised 21, merged 32 and withdrew 0, leaving 21 findings: 1 critical, 10 high, 6 medium, 1 low.
131 anchors resolved, none unresolved, 2 or 3 per finding.
The first draft FINDING line reached the console at 77 s; registry and question DRAFT lines streamed from 29 s.

## Disclosed limitations

- No PDF image block: the backend takes the extracted text only.
- No tools: research did not run.
- FND-009 appears to reverse decision AD-006 without a challenge label.

## Comparison with the first live run

| | First live run (`high`, old sequential design, 3,372 s) | This run (concurrent design, demo profile, 382 s) |
|---|---|---|
| Verdict | `fit_with_conditions`, confidence 0.68 | `not_fit`, confidence 0.78 |
| Findings | 21 | 21 (1 critical, 10 high, 6 medium, 1 low) plus 3 strengths |

The two verdicts differ on the same document; which is closer to the answer key was not scored here, and nothing was graded.

## Cost and cache

- Cost $5.74 by the CLI's estimate, all 8 calls measured, none estimated.
- Output 148,957 tokens, input 344,584 tokens, all written to the cache and none read.
- Each stage's first call shows 2 uncached input tokens plus 28k to 34k cache-write tokens, so the hermetic overhead of `--setting-sources ''` cannot be separated from the prompt in a real run (unverified).

## Replay

`dra replay docs/live_runs/rehearsal_concurrent_1` exits 0 in 2.48 s.
The replayed report matches the recording and the 128 ledger IDs are identical.

## Run 2 ruling

The second approved run was NOT run.
Stage 1 ended 2.6 s past the 230 s tuning threshold with 158 s of slack, so K stays at 4 shards and there is no retuning to confirm.
The second rehearsal is reserved for a `high`-effort run pending the owner's word, because the lab brief sets no time limit; the 540 s slot is a project assumption (audit item U4).

## What is and is not in this directory

- Committed: `report.md`, `report.json`, `manifest.json`, `effective_config.json`, `state.json`, `llm.jsonl`, `anchors.json`, `ledger.json`, `ledger.jsonl`, `checkpoints/` (8 files), `shards/` (4 files), `text/` (2 files), `snapshots/` (empty, not tracked by git).
- Left out: `progress.log`, which `.gitignore` excludes (`*.log`), as in `demo_profile_measure_1`.
- Secret scan, counts only: `sk-` 23 hits, all inside the word `risk-` in the document text (0 hits of `sk-` not preceded by `ri`); `Bearer` 0; `oauth` 0; e-mail pattern 0.
- `Authorization` and `session` hits are document text plus the 36-character CLI session IDs kept per precedent; `api_key` hits are the field name `inherit_api_key` and the env-var name `SIT_MCP_API_KEY`; no value is a credential.
- One home-directory path is committed, `effective_config.json` `config_root`, per the precedent of the two earlier live runs.

## Not verified

- The hermetic overhead of `--setting-sources ''` as a separate number.
- Any run with tools; nothing touched the SIT MCP hosts.
- The true billed cost, and the effect of the Mac's load (about 5) on the timings.
- A `high`-effort run of the concurrent design, which is what run 2 is reserved for.
- Whether the verdict `not_fit` or the first live run's `fit_with_conditions` is closer to the answer key.
