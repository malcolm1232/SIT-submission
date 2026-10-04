# Rehearsal run on the lab's sample document from the review UI (2026-10-04)

The owner ran the agent from the review UI page (`dra ui --port 8791`) with the SIT MCP key on the lab's own sample document, as the rehearsal of item 1 of `docs/HANDOVER_261004_PLANNER.md`.
It is the third with-tools run on this document and the first with six assess shards; it is measured against the 540 s demo slot, against the six checks of item 2 of that handover, and against `sit_sample_ui_1`.
Every number below was extracted by script from the files in this directory and from the gitignored `progress.jsonl`, `llm.jsonl` and `tools.jsonl` of the run (counts, keys, ids and durations only); no model output was read except the header and evidence table of `report.md` and the limitation texts of `report.json`.

## Result

The run completed in 508.5 s: verdict `fit_with_conditions` at confidence 0.60, outcome `completed_degraded` with five disclosed limitations.
Two model calls ended early at a stage limit (`salvaged_calls` 2): assess shard 3 at the stage-1 limit (265 s) and the refine repair call at the refine limit (465 s); slack against the 540 s slot is 31.5 s.
Web search worked: 9 `search_web` and 1 `fetch_url` call, all succeeded; 8 of them met a closed session on the first attempt and succeeded on the retry, after 3 session reopens.
They put 41 external entries in the ledger, but no finding cites any of them.

## The six checks

| # | Check | Result | Number |
|---|---|---|---|
| 1 | Stage 1 ends at or under 230 s with six shards | fails | 265.159 s with 6 shards (35.2 s over); shard 3 ended early at the 265 s limit |
| 2 | Refine ended in full, or the revisions it had already returned were applied | holds as worded, fails in effect | refine call `llm-0012` ended in full (`end_turn`, 152.1 s, 55 revisions) but its answer broke 1 rule and was replaced by a repair call; the repair `llm-0013` ended early with 4 revisions, and 4 of 4 were applied; 51 of 55 merged findings were not refined |
| 3 | External evidence reaches the findings | fails | 0 of 41 external ledger entries cited by any of the 52 findings (152 finding evidence items: 115 doc, 37 inference) |
| 4 | `extra.tools.session_reopens` is present in the manifest | holds | 3 (`session_reopens_by_server`: `mcp-internet-search` 3) |
| 5 | The report's "Tools used" line names only servers that received a call | holds | "Tools used: mcp-internet-search", which received 10 calls; `mcp-research-information` (0 calls) is not named |
| 6 | `output_basis` is present on any model call that ended early | holds | both rows of `estimated_usage_of_unrecorded_calls` (`llm-0005`, `llm-0013`) carry `output_basis: measured_rate`, as does `estimated_usage_totals` (118.6 tokens per second from 12 calls) |

## Setup

- Launched from the review UI page: `review <run dir>/ui/input/sit_sample_v1.pdf --profile demo --run-id ui-261004-034213-c5cb`, tools ticked; input Version 2.0, 30 pages (not committed).
- Tree `s4/demo4` at `fe50a34`, clean; `claude-opus-5-5` through the `claude_code` backend, effort `medium` except research (`low`); 03:42:13Z to 03:50:42Z (11:42 to 11:50 +08).
- Limits 540 / 265 / 465 / 530 s, 30 tool calls, 4 research iterations, six assess shards from `config/agent.yaml`; internet-search and research-information enabled, browser and document-intelligence disabled, transport `live`.

## Stages (run clock)

| Stage | Wall | Output tokens | Cost | Calls | Note |
|---|---|---|---|---|---|
| ingest | 2.7 s | 0 | $0 | 0 | code only |
| understand | 106.3 s (3.1 to 109.4) | 14,494 | $0.52 | 1 | 53 registry entries |
| plan | 71.4 s (3.1 to 74.5) | 7,451 | $0.37 | 1 | 21 plan questions |
| research | 97.2 s (109.4 to 206.6) | 3,304 | $0.75 | 3 | one iteration, 10 tool calls |
| assess (6 shards) | longest 261.9 s; stage 1 ended at 265.2 s | 118,974 + about 31,076 estimated | $3.89 + estimate | 6 | shard 3 ended early at the 265 s limit |
| refine | 199.8 s (265.2 to 465.0) | 19,892 + about 5,654 estimated | $1.43 + estimate | 2 | refine 152.1 s in full; rule repair from 417.4 s, ended early at 465.0 s |
| verify | 0.02 s | 0 | $0 | 0 | anchor repair skipped, slack -0.054 s |
| verdict call | 43.4 s (465.1 to 508.5) | 4,595 | $0.41 | 1 | ran in full |
| total | 508.5 s | 168,710 + about 36,730 estimated | $7.37 lower bound | 14 | slack 31.5 s against 540 s |

Stage 1 ended 0.2 s past its 265 s limit, which is the early end itself, the same as in `sit_sample_ui_1` (265.2 s).
No call was retried by the gateway (every `attempt` is 0); every completed call ended `end_turn`, and the second and third research calls resumed the first CLI session after tool use.

## Shards

| Shard | Start | Wall | Output tokens | CLI turns | Findings, sound areas | Ended |
|---|---|---|---|---|---|---|
| 1 intent_and_fitness | 3.17 s | 160.8 s | 19,217 | 2 | 10, 3 | finished at 164.0 s |
| 2 decisions_and_governance | 3.20 s | 128.2 s | 15,248 | 2 | 9, 2 | finished at 131.4 s |
| 3 requirements_and_consistency | 3.23 s | 261.9 s | about 31,076 (estimated) | unrecorded | 5 kept, 0 | ended early at 265.2 s |
| 4 verifiability | 3.26 s | 232.1 s | 30,271 | 3 | 10, 3 | finished at 235.4 s |
| 5 claims_and_assumptions | 3.33 s | 174.6 s | 20,662 | 2 | 10, 2 | finished at 177.9 s |
| 6 security_and_failure | 3.36 s | 253.8 s | 33,576 | 3 | 11, 2 | finished at 257.2 s |

Three shards wrote their whole answer twice, by the item indices streamed to `progress.jsonl` (each list restarts at index 1):
- shard 4: 10 findings, 3 sound areas and its coverage row by 151.0 s, then the same counts again by 234.9 s;
- shard 6: 11 findings, 2 sound areas and 2 coverage rows by 166.1 s, then again by 255.7 s;
- shard 3: 13 findings, 2 sound areas and 2 coverage rows by 217.2 s, then 5 more findings from 227.9 s until the limit.
Shards 4 and 6 took 3 CLI turns with 37,103 and 30,960 cached tokens read, where every other shard took 2 turns and read none; the cause is not visible in these counts.
Had the first complete answers been kept, the last shard would have finished at about 217 s, under the 230 s threshold.
Shard 3 kept the 5 findings of its second pass; its complete first answer (13 findings, 2 sound areas, 2 coverage rows) is lost, and DEG-002 says "5 finished finding(s) kept".
The merge produced 55 findings and 12 sound areas; refine merged 3 duplicates, leaving 52 findings: 47 issues (0 critical, 13 high, 30 medium, 4 low) and 5 strengths, plus 12 sound areas, 53 registry decisions and 20 unresolved items.
193 anchors (124 on findings, 53 on registry decisions, 13 on sound areas, 3 on the intent): 192 exact, 1 not found (FND-004), 0 repaired, and every `section_ref` equals its resolved `section_id`.
The first streamed draft item (a plan question) reached the event stream at 28.6 s, the first draft finding at 54.5 s.

## Refine

The refine call `llm-0012` ran from 265.2 s and streamed all 55 revisions between 321.8 s and 416.4 s; it ended in full at 417.3 s.
Its answer broke 1 rule (`call_retry`, reason `rule_repair`, problems 1), so the whole answer was set aside and one repair call `llm-0013` asked for it again, from 417.4 s, writing 124,582 cached tokens.
The repair had 47.7 s before the 465 s limit; it returned 4 revisions, all 4 applied (1 revised, 3 merged), and the other 51 findings were not refined.
The `sit_sample_ui_1` defect 1 (returned revisions never applied) is fixed: the 4 returned revisions reached the report.
What the check meant to protect is still lost: 55 finished revisions were set aside for 1 rule problem.

## Load on the Mac

The load was not recorded during the run; `uptime` at 11:58 +08, after it, read load averages 8.23, 7.13, 8.08 with other planner sessions open.
Every completed non-research call streamed at 104 to 136 output tokens per second (the three short research calls at 58 to 65), the same band as `sit_sample_ui_1` (96 to 138), so the completed calls show no slowdown.
The stage-1 overrun comes from shards writing their answer twice, not from a slow stream.

## Tools

- Warm-up done at 1.96 s; research started at 109.4 s with 11 open questions and 30 tool calls left.
- Round 1 at 118.0 s: 6 `search_web` (mode `answer`); 4 started together met a closed session on attempt 0 (0.04 s each) and succeeded on attempt 1 (4.3 to 24.2 s); 2 later ones succeeded at once (20.3 and 10.9 s).
- Round 2 at 153.0 s: 3 `search_web` (2 `answer`, 1 `discover`) and 1 `fetch_url`; all 4 met a closed session on attempt 0 and succeeded on attempt 1 (2.7 to 17.9 s).
- `extra.tools.session_reopens` 3, all on `mcp-internet-search`; `mcp-research-information` had 0 calls though enabled.
- This verifies live what `sit_sample_ui_1` left unverified: a closed session is reopened and the call retried; the retry cost 0.04 s per call.
- Ledger: 165 entries, 87 doc, 37 inference, 41 external; the external ones are 22 primary official, 14 informal, 5 secondary, and 2 are marked read before cite.
- Hosts in the external entries (domains only): learn.microsoft.com 12, docs.azure.cn 7, github.com 4, deepwiki.com 2, oneuptime.com 2, and one each for rajivonai.com, nerdleveltech.com, modelavailability.com, ai.azure.com, azure.microsoft.com, opstree.com, sso.agc.gov.sg, lawplayer.com, www.pdpc.gov.sg, complyhq.app, jczopek.dev, thewindowsupdate.com and stackoverflow.com; one entry cites the MCP call itself.
- Findings citing external evidence: 0 of 52; no sound area, registry decision, unresolved item, research log or verdict text cites one either (`research_log.sources_cited` 0).
- Research stopped after 1 of 4 iterations on `no_marginal_gain` (`sufficient_evidence` not met, `model_stop_vote`) with 1 of 11 open questions answered and 10 of 30 tool calls used; the run-level `stop_reason` detail says "1 of 21 plan question(s) answered".
- Research ran inside stage 1 while the shards worked, so it added no critical-path wall; it cost $0.75 (10 % of the recorded cost).

## Disclosed limitations

DEG-001 (`input_degraded`): text only, figures and image tables not visible.
DEG-002: "assess shard 3/6 (requirements_and_consistency) was cut by the stage 1 limit at 265 s; 5 finished finding(s) kept (cut call llm-0005)".
DEG-003: refine "cut after 48 s by the refine limit"; "4 of 55 refine revisions (one per merged finding) were applied", the other 51 "not refined (no duplicates merged, no registry decisions linked, no research evidence attached for them)".
DEG-004: anchor repair skipped, "-0 s of slack left before the verify and verdict reserve".
DEG-005: FND-001's recommendation appears to reverse approved decision AD-008 without a 'challenges' label.

## Comparison with `sit_sample_ui_1`

| | `sit_sample_ui_1` (UI, 4 shards) | This run (UI, 6 shards) |
|---|---|---|
| Wall | 506.9 s | 508.5 s |
| Stage 1 end | 265.2 s, shard 2 ended early | 265.2 s, shard 3 ended early |
| Refine | 199.8 s, ended early, 0 revisions applied | 199.8 s, full answer set aside for 1 rule problem, repair ended early, 4 applied |
| Model calls | 11 | 14 (6 shards, 1 repair call) |
| Cost | $3.68 lower bound (about $4.49 with the $0.81 estimate) | $7.37 lower bound (about $8.86 with the $1.50 estimate) |
| Output tokens | 93,217 recorded + about 28,411 estimated | 168,710 recorded + about 36,730 estimated |
| Verdict | `fit_with_conditions` 0.65 | `fit_with_conditions` 0.60 |
| Issues | 41 (0 critical, 19 high, 19 medium, 3 low), unmerged | 47 (0 critical, 13 high, 30 medium, 4 low), 3 merged |
| Strength findings, sound areas | 3, 8 | 5, 12 |
| Degradations | 3 | 5 |
| Web search | 7 of 7, plus 1 fetch | 9 of 9, plus 1 fetch, 8 retried on a closed session |
| External evidence | 30 entries, 0 cited | 41 entries, 0 cited |
| Anchors | 169, 0 repaired | 193, 0 repaired, 1 not found |

Six shards did not bring stage 1 forward: the four single-pass shards finished by 177.9 s, but three shards wrote their answer twice, and the last of them met the limit.
The cost nearly doubled: two more shards, the doubled answers (shards 4 and 6 wrote 30,271 and 33,576 tokens) and a refine plus repair that both wrote their full cache.
No answer key exists for this document (decision #35), so nothing was scored.

## Defects this run exposes (nothing fixed here)

1. Three of six shards wrote their whole structured answer twice (indices restart; shards 4 and 6 took 3 CLI turns); this alone pushed stage 1 from about 217 s to 265 s and fails check 1.
2. A shard that ends early keeps the items of its last, unfinished pass: shard 3 kept 5 findings and lost a complete first answer of 13 findings, 2 sound areas and 2 coverage rows.
3. One rule problem in a complete refine answer sets aside all 55 revisions and asks for the whole answer again; the repair cannot finish in the 48 s left, so 51 of 55 findings go unrefined.
4. External evidence still reaches no finding (0 of 41): evidence is attached only by refine, so when refine is degraded the research is wasted for the findings.
5. The stop detail counts 21 plan questions where research worked on 11 open ones ("1 of 21" in `stop_reason`, "1 of 11" in `research_stopped`).
6. FND-004 has one anchor not found and the anchor repair was skipped at -0.054 s of slack; the verify event still reports 0 unverified findings.
7. A UI launch still records absolute home-directory paths: the user name appears once in each of 12 committed files (`sit_sample_ui_1` defect 6).
8. 8 of 10 tool calls met a closed session on the first attempt, including the 4 calls of round 2 only seconds after round 1; the retry hides it (0.04 s each), so it costs nothing here.

## What is and is not in this directory

- Committed: `report.md`, `report.json`, `manifest.json`, `effective_config.json`, `state.json`, `tools.jsonl`, `tools_list.jsonl`, `anchors.json`, `ledger.json`, `ledger.jsonl`, `checkpoints/` (8), `shards/` (6), `text/` (2), `ui/launch.json`, all byte-identical to the run directory, and `llm_calls.json`.
- `llm_calls.json` replaces the run's `llm.jsonl`: one row per model call with ids, purpose, shard, timings, stop reasons, usage, cost, estimated usage and the count of returned items, made by script; no prompt, answer, argv or error text.
  The manifest's `llm_jsonl_sha256` therefore has no file here, and this record cannot be replayed with `dra replay`.
  This record cannot be replayed byte for byte because the raw model log is summarised, whereas `sit_sample_ui_1` was committed as a byte copy of its run directory, including its raw `llm.jsonl`.
- Left out: `llm.jsonl`, `progress.log`, `ui/console.txt`, `ui/input/sit_sample_v1.pdf` (the lab's document), the empty `snapshots/`, and `progress.jsonl` (excluded by `.gitignore`).
- `text/` holds the extracted text of the lab's document; it is the lab's material in a private repo and must be excluded from any public snapshot.
- The copied files keep the document's own title, which contains an em dash (167 occurrences across 14 files); they are not edited, so their hashes match the manifest.
- Secret scan, counts only: 64-character `[A-Za-z0-9_-]` tokens 785, every one lowercase hex (sha256 fields); `Bearer` with a value 0; `sk-` 0; an API-key field with a value 0 (`auth_env` names the variable only); e-mail pattern 3, all at the lab's own domain; `oauth` 157 hits, document vocabulary; the user name in 12 lines across 12 files, 1 of them `config_root`, the rest run paths (defect 7).
- `scripts/leakage_grep.py` printed `PASS: no unresolved hit in a gated area`.

## Not verified

Why shards 4 and 6 took a third CLI turn and wrote their answer twice; the counts show that they did, not why.
Which rule the refine answer broke; `progress.jsonl` records the count only, by design.
Whether the verdict is right (no answer key, decision #35), and the true billed cost.
