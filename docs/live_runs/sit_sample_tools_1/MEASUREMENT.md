# First with-tools run on the lab's sample document (2026-10-03)

The owner ran the agent from his Terminal with the SIT MCP key on the lab's own sample document, with the internet-search and research-information servers enabled.
It is the first run of that configuration, measured here against the 540 s demo slot and compared with the two document-only payments rehearsals.
Every number below was extracted by script from the committed files; no model output was read except the rendered `report.md`.

## Result

The run completed in 428.0 s with a full review: verdict `fit_with_conditions` at confidence 0.72, outcome `completed_degraded` with two disclosed limitations.
Every stage ran to completion; refine and the verdict call were not cut, and no shard was salvaged (`salvaged_calls` 0).
Slack against the 540 s slot: 112.0 s.
Every internet-search call failed in under 0.05 s; the one research-information call succeeded and put 10 external entries in the ledger, of which 1 is cited.

## Setup

- Command: `sit-review review runs/input/sit_sample_v1.pdf --profile demo --run-id sit_sample_tools_1`, tools on (no `--no-tools`).
- Input: "SIT Institutional Memory Platform, Detailed Design", Version 2.0, 30 pages, the lab's own document (not committed).
- Tree: branch `s4/live` at `1b92baf` (the contents-list ingest fix), clean (`git_dirty: false`).
- Model `claude-opus-5-5` requested and served through the `claude_code` backend; effort `medium` for every stage except research (`low`).
- Started 2026-10-03T04:24:22Z (12:24 +08), ended 04:31:31Z (12:31 +08).
- Stop parameters: deadline 540 s, `stage_1_end` 265 s, `refine_end` 465 s, `verdict_end` 530 s, 30 tool calls, 4 research iterations.
- Servers: `mcp-internet-search` and `mcp-research-information` enabled; `mcp-browser-automation-pw` and `mcp-document-intelligence` disabled; transport `live`.

## Stages (run clock)

| Stage | Wall | Output tokens | Cost | Attempts | Note |
|---|---|---|---|---|---|
| ingest | 2.1 s | 0 | $0 | n/a | code only; 33 sections |
| understand | 124.2 s (2.1 to 126.3) | 17,333 | $0.54 | 1 | |
| plan | 77.5 s (2.1 to 79.6) | 8,025 | $0.36 | 1 | |
| research | 22.7 s (126.3 to 149.0) | 1,760 | $0.37 | 3 calls | one iteration, 6 tool calls |
| assess (4 shards) | longest 252.8 s; stage 1 ended at 255.0 s | 88,209 | $2.56 | 4 | limit 265 s |
| refine | 119.8 s (255.0 to 374.8) | 15,525 | $1.17 | 1 | ran in full |
| verify | 8.2 s (374.9 to 383.1) | 406 | $0.22 | 1 | one anchor-repair call |
| verdict call | 44.9 s (383.2 to 428.1) | 4,341 | $0.32 | 1 | ran in full |
| total | 428.0 s | 135,599 | $5.54 | 12 calls | slack 112.0 s against 540 s |

Stage 1 ended 10.0 s inside its 265 s limit and 25.0 s past the 230 s tuning threshold.
No call was retried (every `attempt` is 0); every call ended `end_turn` except the first two research calls, which ended `tool_use` and were resumed.

## Shards

| Shard | Start | Wall | Output tokens | Findings produced | Findings surviving by origin |
|---|---|---|---|---|---|
| 1 intent_and_fitness | 2.15 s | 155.9 s | 18,630 | 10 | 3 |
| 2 requirements_and_consistency | 2.17 s | 252.8 s | 30,119 | 15 | 9 |
| 3 claims_and_assumptions | 2.20 s | 168.9 s | 19,790 | 10 | 6 |
| 4 risk_and_operations | 2.24 s | 168.5 s | 19,670 | 11 | 6 |

Shard 2 set the stage-1 wall: it ran 84 s longer than the next shard and wrote 10,000 more output tokens.
Refine received 46 drafts, revised 24, merged 22 and withdrew 0, leaving 24 findings.
Those are 22 issues (0 critical, 6 high, 14 medium, 2 low) and 2 strength findings, plus 10 sound areas.
130 anchors: 129 resolved exactly, 1 repaired by the verify call (FND-046, anchor 1), 0 unresolved.
The first draft FINDING line reached the console at 71 s; the first DRAFT line of any kind at 34 s.

## Tools

- Warm-up: both servers reported ready at 2 s (research-information 7 tools, internet-search 3 tools), so no cold-start wait was observed.
- Research started at 126.3 s with 9 open questions and 10 tools offered, and issued 6 calls at 132 s and 136 s.
- `mcp-internet-search` `search_web`: 5 calls in one concurrent round, all failed with `MCP error -32000: Connection closed` in 0.000 to 0.042 s each, 4 bytes returned each.
- The gateway then marked `search_web` unusable for the run after two consecutive tool errors.
- `mcp-research-information` `search_research`: 1 call, succeeded in 1.77 s, 98,655 bytes returned.
- Ledger: 117 entries, 80 doc, 27 inference, 10 external; all 10 external entries come from that one call.
- Hosts cited: `doi.org` only (10 entries; 9 peer reviewed, 1 secondary).
- Findings citing external evidence: 1 of 24, FND-026 (high, filtered HNSW search-space claim), which cites EV-002.
- FND-026 was drafted by shard 3 without it; refine added EV-002 as one of six evidence items, so the finding does not depend on it.
- No sound area and no inference entry derives from external evidence.
- Research stopped after 1 of 4 iterations on `sufficient_evidence (model_stop_vote)` with 0 of 9 questions answered; it did not hit a stage limit and used 6 of 30 tool calls.
- Research ran inside stage 1 while the shards were already working, so it added no wall time on the critical path; it cost $0.37 (6.6 % of the run).
- The four shards started at 2 s, before research began, so no shard could use external evidence; only refine and the verdict call saw it.

## Disclosed limitations

- DEG-001 (`input_degraded`): "DOC-sit_sample_v1: native PDF block not sent because the configured model backend accepts text only. Impact: figures, diagrams and tables rendered as images were not visible to the model; the review is based on the extracted text".
- DEG-002 (`tool_error`): "mcp-internet-search/search_web failed (tool_error): MCP error -32000: Connection closed. Impact: that call contributed no evidence".
- The report names three external premises left unverified because web search failed: the Entra ID 48-hour token (FND-029), pgvector filtered HNSW (FND-026) and Azure Singapore pricing (FND-034).

## Comparison with the document-only payments rehearsals

| | `rehearsal_concurrent_1` (demo, medium) | `rehearsal_concurrent_high_1` (high) | This run (demo, medium, tools) |
|---|---|---|---|
| Document | payments v1 | payments v1 | SIT sample v2.0 |
| Wall | 382.3 s | 780.3 s | 428.0 s |
| Stage 1 end | 232.6 s | 560.1 s | 255.0 s |
| Model calls | 8 | 8 | 12 |
| Cost | $5.74 | $8.21 | $5.54 |
| Output tokens | 148,957 | 258,222 | 135,599 |
| Cache read | 0 | 71,971 | 106,739 |
| Verdict | `not_fit` 0.78 | `not_fit` 0.75 | `fit_with_conditions` 0.72 |
| Issues | 18 (1 critical, 10 high, 6 medium, 1 low) | 19 (1 critical, 11 high, 7 medium) | 22 (0 critical, 6 high, 14 medium, 2 low) |
| Strength findings, sound areas | 3, 13 | 2, 17 | 2, 10 |
| Degradations | 3 | 5 | 2 |
| External evidence | 0 | 0 | 10 entries, 1 cited |

The 45.8 s over the demo rehearsal comes mostly from a longer stage 1 (+22.4 s, shard 2 on a different document), the anchor-repair call (+8.2 s) and a longer verdict call (+16.9 s), offset by a refine 1.8 s shorter, not from research.
The tools added 10 external ledger entries, one supporting citation in FND-026, three model calls and $0.37.
The documents differ, so the verdicts and finding counts are not comparable as quality.
No answer key exists for this document (decision #35), so nothing was scored.

## Cost and cache

- Cost $5.54 by the CLI's estimate, all 12 calls measured, none estimated (`cost_usd_lower_bound: false`).
- Output 135,599 tokens, input 351,269 tokens, of which 351,241 were written to the cache and 106,739 read from it.
- Each first-stage call read about 3,400 to 6,200 cached tokens, and the two resumed research calls read 32,715 and 33,597.

## Defects this run exposes (nothing fixed here)

1. A closed MCP session is reported as a tool error.
   `mcp_client.classify_exception` maps any `MCPError` code it does not list to `TOOL_ERROR` (line 191), and -32000 "Connection closed" is not listed.
   So the gateway neither drops nor reconnects the session (`gateway.py` line 493 lists only connection, timeout, session-expired, malformed and unknown) and counts the failures toward the tool-error streak that marks `search_web` unusable.
   The session was opened by the warm-up at 2 s and failed at 132 s; the research-information session opened at the same time still worked; a server-side idle close is the likely cause (unverified).
2. DEG-002 reads as one failed call ("that call contributed no evidence") when five calls failed and the tool was then disabled for the run.
3. The research stop reads `sufficient_evidence` with 0 of 9 questions answered and the only web tool unusable; the run-level `stop_reason` repeats it.
4. The fitness text of `report.md` says "seven high-severity findings are still open"; `report.json` holds six.
5. The header row reads "vVersion 2.0": the version field already holds "Version 2.0" and the renderer adds a "v".
6. The bullet lists inside the fitness text and "What would change this verdict" are rendered inline as " - " inside one paragraph.
7. Structural: research begins after understand (126 s) while the shards start at 2 s, so external evidence can never reach a shard.

The ingest fix held: 33 sections, numbered 1 to 29 in page order with 2.1, 2.2, 27.1 and 27.2, and every anchor's `section_ref` equals its resolved `section_id`.

## What is and is not in this directory

- Committed: `report.md`, `report.json`, `manifest.json`, `effective_config.json`, `state.json`, `llm.jsonl`, `tools.jsonl`, `tools_list.jsonl`, `anchors.json`, `ledger.json`, `ledger.jsonl`, `checkpoints/` (8 files), `shards/` (4 files), `text/` (2 files), `snapshots/` (empty, not tracked by git).
- Left out: `progress.log`, which `.gitignore` excludes (`*.log`).
- `text/` holds the extracted text of the lab's document; it is the lab's material in a private repo and must be excluded from any public snapshot.
- Secret scan, counts only: 64-character `[A-Za-z0-9_-]` tokens 571, every one lowercase hex in a sha256 field (config, prompt, request, schema, cassette and output hashes); `Bearer` with a value 0; `sk-` 0; e-mail pattern 15, two distinct addresses at the lab's own domain that appear in the document text.
- `oauth` 62 hits, all document vocabulary ("OAuth 2.0") or a keyword list; `Authorization` 1, the config field `auth_header`; `api_key` 2, the field `inherit_api_key` and the env-var name `SIT_MCP_API_KEY`; no value is a credential.
- One home-directory path is committed, `effective_config.json` `config_root`, per the precedent of the earlier live runs.

## Not verified

- Why the internet-search server closed the session, and whether a reconnect would have succeeded.
- Whether the agent's verdict on this document is right; there is no answer key (decision #35).
- `dra replay` of this run, which was not executed here.
- The true billed cost.
