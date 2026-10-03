# Live run langgraph_payments_v1_1 (2026-10-03)

The one live run of the LangGraph orchestrator variant (`docs/COMPARISON_LANGGRAPH.md`), on the document, profile and effort of `rehearsal_concurrent_1`, so the two orchestrators can be compared by the same harness.

## Result

The run completed in 424.7 s with a full review: verdict `not_fit` at confidence 0.75, 18 findings (1 critical, 10 high, 7 medium) plus 3 strengths, outcome `completed_degraded` with four disclosed limitations.
Assess shard 2 (`requirements_and_consistency`) was cut by the runtime at the stage 1 limit (265 s on the run clock) after 263.2 s, with 14 finished findings salvaged from its stream; the other three shards ended at 183.8 s, 193.0 s and 215.7 s.
Refine (129.6 s) and the verdict call (29.8 s) ran in full.

## Setup

- Command: `env -u ANTHROPIC_API_KEY sit-review review eval/synthetic/payments_orchestration/design_v1.pdf --profile demo --no-tools --orchestrator langgraph --run-id langgraph_payments_v1_1`.
- Tree: branch `s4/langgraph` at `c4d94b9`; model `claude-opus-5-5` through the `claude_code` backend; efforts `medium` on every stage and `low` for research, as `rehearsal_concurrent_1`.
- Started 17:28:21 +08, ended 17:35:28 +08; the Mac's load average was 15.8 (1 min) and 11.2 (5 min) when the run ended, beside other sessions.
- Stop parameters: deadline 540 s, `stage_1_end` 265 s, `refine_end` 465 s, `verdict_end` 530 s.
- `langgraph/variant.json` names the variant and the framework versions (`langgraph 1.2.12`); `langgraph/graph.mmd` is the framework's own drawing of the graph; `langgraph/graph_checkpoints.jsonl` mirrors the framework's 28 checkpoints (one per superstep and per subgraph step).

## Measured, run clock

| Stage | This run (LangGraph variant) | `rehearsal_concurrent_1` (custom loop) |
|---|---|---|
| ingest | 1.9 s | 2.2 s |
| understand | 125.0 s | 121.7 s |
| plan | 113.6 s | 71.5 s |
| research | 0.0 s (`--no-tools`) | 0.0 s (`--no-tools`) |
| assess (4 shards) | longest cut at 263.3 s; stage 1 ended at 265.2 s | longest 230.3 s; stage 1 ended at 232.6 s |
| refine | 129.6 s, ending at 394.8 s | 121.6 s, ending at 354.2 s |
| verify | 0.013 s | 0.013 s |
| verdict call | 29.8 s | 28.0 s |
| total | 424.7 s | 382.3 s |

The stage 1 members started at 1.9 s to 2.1 s into the run in both runs: the framework's fan-out added no measurable start-up over the custom loop's task creation.
The first assess draft item reached the stream at 75.7 s (77 s on the custom loop's run).

## Shards

| Shard | Wall | Output tokens | Findings produced |
|---|---|---|---|
| 1 intent_and_fitness | 193.0 s | 24,032 | 13 |
| 2 requirements_and_consistency | cut at 263.2 s | about 26,504 (estimated: the cut call left no usage report) | 14 salvaged |
| 3 claims_and_assumptions | 183.8 s | 21,975 | 13 |
| 4 risk_and_operations | 215.7 s | 25,714 | 14 |

Refine received 54 merged findings, revised 21, merged 33 and withdrew 0, leaving 21 findings.
121 anchors resolved, none repaired, none unresolved.

## Cost

$4.71 by the CLI's estimate, a lower bound: the cut shard call has no measured usage (`calls_with_unrecorded_usage` 1, its estimate 26.5k output tokens), so the true figure is near the custom loop run's $5.74.

## Disclosed limitations

- No PDF image block: the backend takes the extracted text only.
- No tools: research did not run.
- Assess shard 2 was cut by the stage 1 limit with 14 findings kept.
- FND-050's recommendation appears to reverse decision AD-005 without a challenge label.

## What is and is not in this directory

- Committed: `report.md`, `report.json`, `manifest.json`, `effective_config.json`, `state.json`, `llm.jsonl`, `anchors.json`, `ledger.json`, `ledger.jsonl`, `checkpoints/`, `shards/`, `text/`, `langgraph/`, and `eval_pilot_bounded/` (the scoring).
- Left out: `progress.log` and `progress.jsonl` (gitignored) and `snapshots/`.
- Secret scan, counts only: `sk-ant-` 0, `ANTHROPIC_API_KEY=` 0, `Bearer ` 0, `ghp_` 0; `SIT_MCP` and `api_key` 1 file each, the env-var name `SIT_MCP_API_KEY` and the field name in `effective_config.json`, as in `rehearsal_concurrent_1`.
