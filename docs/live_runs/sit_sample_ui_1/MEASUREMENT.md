# With-tools run on the lab's sample document from the review UI (2026-10-03)

The owner ran the agent from the review UI page (`dra ui`) with the SIT MCP key on the lab's own sample document, after the MCP session fix (reopen and retry, `session_idle_reopen_s` 60 s).
It is the second with-tools run on this document and the first launched from the page, measured against the 540 s demo slot and compared with `sit_sample_tools_1`, the same document and profile run from the Terminal before the fix.
Every number below was extracted by script from the committed files and the gitignored `progress.jsonl`; no model output was read except the rendered `report.md`.

## Result

The run completed in 506.9 s: verdict `fit_with_conditions` at confidence 0.65, outcome `completed_degraded` with three disclosed limitations.
Two model calls were cut and salvaged (`salvaged_calls` 2): assess shard 2 at the stage-1 limit and refine at the refine limit; slack against the 540 s slot is 33.1 s, and the verdict call ended inside its 530 s limit.
Web search worked this time: 7 of 7 `search_web` calls and 1 `fetch_url` call succeeded, after one proactive session reopen.
They put 30 external entries in the ledger, but no finding cites any of them, because evidence is attached in refine and refine was cut.

## Setup

- Launched from the review UI page: `review <run dir>/ui/input/sit_sample_v1.pdf --profile demo --run-id ui-261003-082941-36e8`, tools on; input Version 2.0, 30 pages, 33 sections (not committed).
- Tree `s4/final` at `886c3fc`, clean; `claude-opus-5-5` through the `claude_code` backend, effort `medium` except research (`low`); 08:29:41Z to 08:38:09Z (16:29 to 16:38 +08).
- Limits 540 / 265 / 465 / 530 s, 30 tool calls, 4 research iterations; internet-search and research-information enabled, browser and document-intelligence disabled, transport `live`.

## Stages (run clock)

| Stage | Wall | Output tokens | Cost | Calls | Note |
|---|---|---|---|---|---|
| ingest | 2.2 s | 0 | $0 | 0 | code only; 33 sections |
| understand | 114.6 s (2.2 to 116.8) | 15,857 | $0.51 | 1 | |
| plan | 41.8 s (2.2 to 44.0) | 4,205 | $0.28 | 1 | |
| research | 62.3 s (116.8 to 179.1) | 2,441 | $0.60 | 3 | one iteration, 8 tool calls |
| assess (4 shards) | longest 262.9 s; stage 1 ended at 265.2 s | 66,051 + about 15,252 estimated | $1.92 + estimate | 4 | shard 2 cut at the 265 s limit |
| refine | 199.8 s (265.3 to 465.0) | about 13,159 estimated | unrecorded | 1 | cut at the 465 s limit |
| verify | 0.02 s | 0 | $0 | 0 | no anchor-repair call needed |
| verdict call | 41.7 s (465.1 to 506.9) | 4,663 | $0.36 | 1 | ran in full |
| total | 506.9 s | 93,217 + about 28,411 estimated | $3.68 lower bound | 11 | slack 33.1 s against 540 s |

Stage 1 ended 0.2 s past its 265 s limit, which is the cut itself, and 10.2 s later than in `sit_sample_tools_1`.
No call was retried (every `attempt` is 0); every completed call ended `end_turn`, and the second and third research calls resumed the first CLI session after tool use.

## Shards

| Shard | Start | Wall | Output tokens | Findings | Ended |
|---|---|---|---|---|---|
| 1 intent_and_fitness | 2.24 s | 179.0 s | 21,148 | 12 (1 strength), 3 sound areas | finished at 181.3 s |
| 2 requirements_and_consistency | 2.28 s | 262.9 s | about 15,252 (estimated) | 8 kept, 0 sound areas | cut and salvaged at 265.2 s |
| 3 claims_and_assumptions | 2.33 s | 180.3 s | 20,764 | 10 (1 strength), 2 sound areas | finished at 182.6 s |
| 4 risk_and_operations | 2.45 s | 200.9 s | 24,139 | 14 (1 strength), 3 sound areas | finished at 203.4 s |

Only one shard was salvaged: shard 2, cut at 265.2 s, kept 8 finished findings (4 high, 4 medium) and no coverage rows.
The second salvaged call is refine (`llm-0010`), cut at 465.0 s with 30 finished revisions kept in `llm.jsonl`; none of them was applied to the report.
The merge produced 44 findings and 8 sound areas; 43 of the 44 reported findings are identical to their shard drafts in title, severity, disposition and evidence count.
Those are 41 issues (0 critical, 19 high, 19 medium, 3 low) and 3 strength findings, plus 8 sound areas, with no duplicate merged.
169 anchors (104 on findings, 54 on registry decisions, 8 on sound areas, 3 on the intent): 168 exact, 1 fuzzy (FND-034, score 0.948), 0 repaired, 0 unresolved, and every `section_ref` equals its resolved `section_id`.
The first draft finding reached the event stream at 80.3 s; the first draft item of any kind (a plan question) at 12.6 s.

## Load on the Mac

Another Opus run, the re-assessment rehearsal, shared the Mac during this run, by the caller's account; it is not in these files, and the committed `reassess_payments_v2_1` ended at 08:14:45Z, before this run began.
`sit_sample_tools_1` also shared the Mac: `ui_flow_1` (8 Opus calls) ran from 04:25:13Z to 04:32:23Z, overlapping it almost entirely.
Every completed call here streamed at 96 to 138 output tokens per second, the same band as `sit_sample_tools_1` (97 to 140), so the completed calls show no slowdown.
The three finished shards wrote 21,148 to 24,139 tokens each, against 18,630 to 19,790 in `sit_sample_tools_1`, so they ran longer because they wrote more; the cut calls' estimated rates (58 and 66 per second) are not comparable with recorded usage (defect 5).
The two cuts are therefore attributed to load or design, not separable here.

## Tools

- Warm-up: `mcp-internet-search` ready at 1.19 s (3 tools), `mcp-research-information` at 1.31 s (7 tools); research started at 116.8 s with 6 questions and 10 tools offered.
- At 123.3 s the gateway reopened the `mcp-internet-search` session before the first call: "idle longer than session_idle_reopen_s 60 s; idle 122 s".
  That was the only reopen; no call met a closed session, and every call succeeded on its first attempt.
- Round 1 (6 `search_web`, mode `answer`): started at about 124 s (4 calls), 129 s and 139 s; walls 5.2, 15.5, 22.6, 29.1, 24.0 and 15.7 s.
- Five of them returned 5 results each through the duckduckgo provider (47 to 121 KB of text); one returned no structured results (330 bytes).
- Round 2 at about 160 s: 1 `search_web` (mode `discover`, 2.0 s, 5 results) and 1 `fetch_url` (3.1 s, 6.4 KB); `mcp-research-information` had 0 calls though ready.
- Ledger: 121 entries, 71 doc, 20 inference, 30 external; the external ones are 16 primary official, 12 informal, 2 secondary, and 2 are marked read before cite.
- Hosts in the external entries (domains only): learn.microsoft.com 9, docs.azure.cn 4, github.com 3, rajivonai.com 2, and one each for azure.microsoft.com, ai.azure.com, developers.openai.com, deepwiki.com, nerdleveltech.com, www.datastudios.org, nebularatech.com, 1bench.dev, lawplayer.com, sqlview.com.sg and sso.agc.gov.sg; one entry cites the MCP call itself.
- Findings citing external evidence: 0 of 44; no sound area, inference entry, registry decision, unresolved item or verdict text cites one either.
- Research stopped after 1 of 4 iterations on `sufficient_evidence (model_stop_vote)` with 1 of 6 questions answered and 8 of 30 tool calls used.
- The five unanswered questions are disclosed in the report: Entra ID token lifetime, Azure PostgreSQL cost and pgvector features, PDPA against backups and audit retention, single-instance scale and failure, and Event Hubs Kafka support.
- Research ran inside stage 1 while the shards worked, so it added no critical-path wall; it cost $0.60 (16 % of the recorded cost).

## Disclosed limitations

DEG-001 (`input_degraded`): text only, figures and image tables not visible.
DEG-002: "assess shard 2/4 (requirements_and_consistency) was cut by the stage 1 limit at 265 s; 8 finished finding(s) kept (cut call llm-0004)".
DEG-003: refine cut at 465 s, findings reported "without the global refine pass (no duplicates merged, no registry decisions linked, no research evidence attached)".
The fitness text names the external premises left unverified for that reason: Entra ID token lifetime, pgvector filtered HNSW, Azure pricing, BM25 availability and PDPA obligations.

## Comparison with `sit_sample_tools_1`

| | `sit_sample_tools_1` (Terminal, before the fix) | This run (UI, after the fix) |
|---|---|---|
| Wall | 428.0 s | 506.9 s |
| Stage 1 end | 255.0 s, no cut | 265.2 s, shard 2 cut |
| Refine | 119.8 s, ran in full | 199.8 s, cut, 0 revisions applied |
| Model calls | 12 | 11 (no anchor-repair call) |
| Cost | $5.54 | $3.68 lower bound (about $4.49 with the $0.81 estimate) |
| Output tokens | 135,599 | 93,217 recorded + about 28,411 estimated |
| Cache written, read | 351,241, 106,739 | 223,373, 123,565 recorded (+ about 42,954, 136,309 estimated) |
| Verdict | `fit_with_conditions` 0.72 | `fit_with_conditions` 0.65 |
| Issues | 22 (0 critical, 6 high, 14 medium, 2 low) | 41 (0 critical, 19 high, 19 medium, 3 low), unmerged |
| Strength findings, sound areas | 2, 10 | 3, 8 |
| Degradations | 2 | 3 |
| Web search | 0 of 5 (closed session) | 7 of 7, plus 1 fetch |
| External evidence | 10 entries, 1 cited | 30 entries, 0 cited |
| Anchors | 130, 1 repaired | 169, 0 repaired |

The 78.9 s over `sit_sample_tools_1` comes from refine (80.0 s longer, cut instead of finished) and stage 1 (10.2 s later), offset by the absent anchor-repair call (8.2 s) and a verdict call 3.2 s shorter.
The session fix worked (the idle session was reopened before use and every web call returned results), but the tools changed nothing in the findings, because the one stage that attaches external evidence was cut.
The documents are the same, but no answer key exists (decision #35), so nothing was scored.

What changed in the agent's reading of the lab document, from `report.md`:
1. Same verdict, fit with conditions, at lower confidence (0.65 against 0.72), which the report ties to the cut refine and the unverified external premises.
2. All six high themes of the first run recur (agent backup, counselling wall against Super Admin, async write path, MMP in the request path, revoked token served from backup, filtered HNSW claim), now as 19 high findings with unmerged duplicates (the backup alone 4 times).
3. New high themes: vector sizing against the 128 GB SKU (FND-022), Kafka retry and Event Hubs (FND-024), the Redis context-pack cache (FND-033), counselling escalations (FND-036) and the 48-hour Entra ID token (FND-023).
4. Strengths: the traceable intent (FND-012), the gaps tracked in the backlog (FND-030), and the ordered pre-retrieval Gateway checks with tier isolation (FND-044).
5. Limitations disclosed: text only, the cut shard, and the refine cut with no external evidence attached, so the external premises rest on reasoning alone.

Cost: $3.68 by the CLI's estimate for the 9 calls with recorded usage (`cost_usd_lower_bound: true`); the price-table estimate for the two cut calls adds $0.81.
Cache: each shard read 6,195 cached tokens; the two resumed research calls read 32,126 and 61,809.

## Defects this run exposes (nothing fixed here)

1. A cut refine discards every finished revision: `llm.jsonl` keeps 30 salvaged revisions and `salvaged_items` 38 counts them, but 0 reach the report, so no external entry is cited, no duplicate merged, and 19 high findings stand for about 11 distinct themes.
2. Research stops on `sufficient_evidence` with 1 of 6 questions answered, as in `sit_sample_tools_1`; the run-level `stop_reason` repeats it.
3. The report header lists "Tools used: mcp-internet-search, mcp-research-information" when `mcp-research-information` had 0 calls; the run details row ("mcp-internet-search: 8") is right.
4. The session reopen is recorded only in `progress.jsonl` (gitignored) and in one `tools.jsonl` attempt message; the manifest and the report carry no session event, though the gateway calls it disclosed.
5. The usage estimate of a cut call (streamed characters over 3.3 plus thinking) gives 58 and 66 tokens per second when every recorded call ran at 96 to 140, so the $0.81 and the lower bound probably understate.
6. A UI launch records absolute home-directory paths: 13 committed files hold the user name outside `config_root` (argv, `pdf_path`, `ui/launch.json`), where Terminal runs record relative paths; `ui_flow_1` has the same.
7. The two "waking" status records in `progress.jsonl` carry `run_s` null.
8. Design pressure: with shards writing 21,000 to 24,000 tokens, a shard that writes about 30,000 (as shard 2 did in the first run, 252.8 s) meets the 265 s limit, and refine has 200 s for a pass that took 120 s last time.

## What is and is not in this directory

- Committed: `report.md`, `report.json`, `manifest.json`, `effective_config.json`, `state.json`, `llm.jsonl`, `tools.jsonl`, `tools_list.jsonl`, `anchors.json`, `ledger.json`, `ledger.jsonl`, `checkpoints/` (8), `shards/` (4), `text/` (2), `ui/launch.json`.
- Left out: `progress.log` and `ui/console.txt` (366 of its 367 lines are the same console stream), `ui/input/sit_sample_v1.pdf` (the lab's document), and `progress.jsonl` (excluded by `.gitignore`); no `ui/chat.jsonl` was written.
- `text/` holds the extracted text of the lab's document; it is the lab's material in a private repo and must be excluded from any public snapshot.
- Secret scan, counts only: 64-character `[A-Za-z0-9_-]` tokens 699, every one lowercase hex (sha256 fields); `Bearer` with a value 0; `sk-` 0; e-mail pattern 12, all at the lab's own domain in the document text;
  `oauth` 67 hits, all document vocabulary in the text, drafts and report; the user name appears in 14 committed lines across 13 files, 1 of them `config_root`, the rest run paths (defect 6).

## Not verified

Whether the concurrent run caused the two cuts; the files here cannot separate load from design.
Whether a closed session is now reopened and retried live; this run reopened on idle and met no closed session.
Whether the verdict is right (no answer key, decision #35), `dra replay` of this run, and the true billed cost.
