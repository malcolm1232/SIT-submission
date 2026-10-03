# The custom loop against a LangGraph variant of the same agent (2026-10-03)

The question this answers is the one interviewers keep asking: why a custom loop and not LangGraph.
The answer here is measured, not argued: the same agent was re-expressed as a LangGraph `StateGraph` (`agent/sit_review_agent/orchestrator_langgraph/`), selected by `sit-review run --orchestrator langgraph`, with the same phases, prompts, gateways, checkpoint writers, progress stream and run directory, so the two orchestrators can be run on the same documents and scored by the same harness.
Without the flag the product is the custom loop, unchanged; the variant's dependency is the optional extra `[langgraph]` (`langgraph==1.2.12`), never a product dependency.

## What the variant is

The run is a graph of nodes that call the same phase objects: `ingest`, then a fan-out of `Send`s to one `assess_shard` node per shard of `AssessSettings.shards_for` and to a compiled subgraph `stage1_chain` (understand and plan from its start, a join edge, then research), then `merge`, `refine` or `verify` by a conditional edge, `verify`, `report` (`graph.py` `build`, line 154; `_chain`, line 180; `_fan_out`, line 208).
The subgraph exists because a LangGraph superstep is a barrier: a join edge at the top level from understand and plan to research would also wait for every assess shard, so research would start only after the slowest shard; inside its own subgraph the join waits for the two it depends on and nothing else (`graph.py` lines 18 to 21).
The run state stays on the `RunContext` and each member runs on an isolated copy merged back by the repo's own `phases._isolation` code; the graph state carries only the control state, which stage 1 members ended and how, which shards produced a result, and why the run stops early (`graph.py` `GraphState`, line 67).
LangGraph's checkpointer carries that control state, mirrored per superstep to `<run>/langgraph/graph_checkpoints.jsonl`; the run state is in the repo's `checkpoints/<nn>-<phase>.json`, which `resume` reads unchanged (`saver.py` `RunDirSaver`, line 30).
The bookkeeping around a phase (checkpoint with ordinal and `elapsed_s`, milestones, the stage 1 close with the merge in shard order, the cap skips and their disclosures, the cut and skipped fallbacks, the finished shards on disk) is inherited from `Orchestrator`, so the comparison is about scheduling, not about two copies of the bookkeeping.

## The same document, the same profile, the same harness

Both runs reviewed `eval/synthetic/payments_orchestration/design_v1.pdf` with `--profile demo --no-tools`, Opus 5.5 at `medium` through the `claude_code` backend, and were scored by `sit-eval score` in the pre-registered setup with `--exploratory` (judge `claude_code`, Opus `high`, pairwise 0-3, 3 samples with the adaptive third, `shortlist_bounded`, grounding judges on, seed 20261002, concurrency 4, cost stop $18).
The custom loop's column is the concurrent `medium` row of `docs/live_runs/QUALITY_COMPARISON.md` (`rehearsal_concurrent_1`); the variant's is `docs/live_runs/langgraph_payments_v1_1/`.

| Measure | Custom loop (`rehearsal_concurrent_1`) | LangGraph variant (`langgraph_payments_v1_1`) |
|---|---|---|
| Agent wall time | 382.3 s | 424.7 s |
| Stage 1 end on the run clock | 232.6 s (no shard cut) | 265.2 s (shard 2 cut at the limit, 14 findings salvaged) |
| Agent cost | $5.74 (complete) | $4.71 (lower bound: the cut call's usage is unrecorded, estimated 26.5k output tokens) |
| Findings scored (strengths excluded) | 18 | 18 |
| Strict recall | 13 of 14 (0.929) | 12 of 14 (0.857) |
| Lenient recall | 14 of 14 (1.000) | 14 of 14 (1.000) |
| Adjudicated precision | 0.944 | 0.944 |
| Severity-weighted recall | 0.933 | 0.867 |
| Critical recall | 1.000 (4 of 4) | 1.000 (4 of 4) |
| Hallucination-flag rate (harness) | 0.000 | 0.000 |
| Verdict | `not_fit` at 0.78 | `not_fit` at 0.75 |
| Scoring judge calls and cost | 95, $9.54 | 86, $9.45 |
| Strict precision | 0.722 | 0.667 |
| PARTIAL_KEY_MATCH count | 1 | 2 |
| VALID_UNPLANTED count | 3 | 3 |
| Other adjudicated classes | DUPLICATE 1 | INVALID_OPINION 1 |

Per flaw, the variant's run matched the same 13 flaws the custom loop's run did except F07 (high), which it matched partially where the custom loop's run matched it strictly, and F04 (high) stayed partial in both; that one flaw is the whole of the strict-recall and severity-weighted differences, and the scored finding counts, the adjudicated precision, the critical recall and the hallucination rate are equal.
The shard cut is the one visible difference in the agent's behaviour, and it is not the framework's doing: the cut is made by the runtime inside the model call (`llm/runtime.py` `RunDeadline`) in both orchestrators, and on this run shard 2 needed 263 s where the custom loop's run had its longest shard at 230 s, under a Mac load average of 15.8 against about 5 (`docs/live_runs/langgraph_payments_v1_1/MEASUREMENT.md`, `rehearsal_concurrent_1/MEASUREMENT.md`).
The stage 1 members started within 0.2 s of each other in both runs, at about 2 s into the run, so the framework's fan-out cost nothing measurable.

## The parity checklist

`tests/test_parity_langgraph.py` runs ten behaviours through both orchestrators by swapping the class the product's entry points use, as the flag does; the tally is 26 passed and 2 expected failures, each named.

| Behaviour | Custom | LangGraph | Where |
|---|---|---|---|
| Deterministic finding IDs across completion orders | pass | pass | the merge in shard order is the inherited `_close` |
| A shard cut at the stage limit keeps its findings | pass | pass | the cut is the runtime's, the salvage the phase's |
| Two truncations end in a disclosed report (assess, refine) | pass | pass | the phase's fallback |
| A declined assess gives `not_assessed` | pass | pass | the phase and the report |
| A connection error on a first call exits once, resumable | pass | pass | `_member` maps the typed error after stopping its siblings (`graph.py` line 403) |
| Resume runs only the unfinished members and shards | pass | pass | `_load_shards` and `completed_phases` build the graph (`graph.py` `_chain`, `_fan_out`) |
| Byte-equal replay | pass | pass | `dra replay` reads the same logs |
| Per-shard fault injection by `nth` and by `shard` | pass | pass | the shard node calls the phase's own shard runner, which the fault wrapper patches (`graph.py` line 339) |
| The deadline enforced inside a model call | pass | pass | `llm/runtime.py`, not the orchestrator |
| Progress events: the same set, identical before and after stage 1 | pass | pass | the same emit sites |
| Progress events in the same sequence | pass | expected failure | LangGraph starts parallel nodes in its own order (by node name), not in `STAGE_1` order |
| A process fault around the whole assess member (BEH-25) | pass | expected failure | the member is one node per shard, so the member-level wrapper is never called |

The six launch-order assertions of `tests/test_orchestrator.py` (for example `log == ["ingest", "understand", "plan", "assess", ...]`) fail under the variant for the first reason above and are re-asserted order-free in the parity file; everything else in that file passes.

## Lines of code

Counting code lines without blanks, comments and docstrings: the custom loop's `Orchestrator` class with its two helpers is 356 lines, of which the variant replaces 153 (`run`, `_stage_1`, `_member_end`, `_StageFailure`) and inherits 203.
The variant is 436 lines: `graph.py` 365, `saver.py` 42, `__init__.py` 29.
So the framework did not shorten the loop: 153 lines of hand-written scheduling became 365 lines of graph construction, routers, nodes and the hand-written pieces below, plus 71 lines to fit the checkpointer and the entry points.

## What the framework made easier

- The drawing: `app.get_graph(xray=True).draw_mermaid()` gives the run's graph with the subgraph inside it for free (`graph.py` line 136, written to `<run>/langgraph/graph.mmd`), where the custom loop's `states.mermaid` is hand-maintained.
- The fan-out and the join: `Send` per shard and a join edge on `[understand, plan]` say what the stage is in four lines (`graph.py` lines 191 and 225), where `_stage_1` keeps a task table, a ready set and a wait loop (`orchestrator.py` lines 279 to 337).
- The failure path of a sibling: when one node raises, the framework cancels the superstep's other nodes and propagates the exception typed as raised (`graph.py` line 403 maps it), where `_stage_1` cancels and gathers by hand (`orchestrator.py` lines 338 to 347).

## What the framework made awkward

- The barrier: research after understand and plan but beside the shards needed a subgraph, because every join at one level waits for the whole superstep (`graph.py` line 180).
- The control state outside the run state: the run state holds gateways, a ledger and a registry that cannot go through the framework's channels, so the graph carries a shadow of it and the nodes reach the real one through the orchestrator object (`graph.py` lines 67 and 98), which is the framework's "state" in name only.
- Disclosures inside edge functions: a cap that skips refine must record a degradation and a progress event, so the router has side effects (`graph.py` `_route_refine`, line 230), which LangGraph's model treats as a pure function.
- The seam: `orchestrator._run_execute` names the class, so the variant swaps `orchestrator.Orchestrator` for the duration of a call (`__init__.py` `using_langgraph`, line 33), a monkeypatch the product would need a constructor argument to replace.
- The start order: parallel nodes start in the framework's order (by node name), so the per-member seconds of overlapping members and the stage 1 stretch of the progress stream differ from the custom loop's run to run; the checkpoint ordinal and `elapsed_s` absorb it, the launch-order tests do not.

## What the framework could not do

- A per-node time limit on the run clock: LangGraph has no node timeout, and none that reads a `FakeClock`, so the stage 1 backstop (`stage1_grace_s`) is a hand-written poll loop around each member's task (`graph.py` `_member`, lines 403 to 437), the same loop `_stage_1` has once (`orchestrator.py` line 319).
- Stopping siblings before the failed node's state flush: the framework cancels the other nodes only after the exception has left the node, so the flush of `state.json` that must happen first needs the variant's own task table (`graph.py` `_cancel_others`, line 465).
- A process fault around the whole assess member (BEH-25 with no `shard` key): the member is one node per shard, so `run_shards` is never called and the wrapper never fires (the expected failure above).
- Resume from the framework's checkpoint: the framework's checkpoint holds the control state only, so a resumed run starts a new thread and rebuilds the graph from the repo's checkpoint (`graph.py` lines 101 and 183); the framework's checkpointer is a mirror, not the record.

## Conclusion

On one document and one run per arm, the LangGraph variant produced a review of the same shape (18 findings and 3 strengths, the same verdict label) at a wall time 42 s longer that is explained by one shard reaching the stage 1 limit under a heavier Mac load, and the scoring numbers above are exploratory, so no quality difference can be claimed either way.
The framework paid for itself in the fan-out, the join and the drawing, and charged for it in a subgraph forced by the superstep barrier, a shadow state, side effects in routers, a hand-written backstop and sibling cancellation, and a swapped class name, for 436 lines against the 153 it replaces.
The custom loop stays because every one of those charges is a behaviour the product tests (the parity file shows which), and the variant stays in the tree so the next person who asks can run both on the same document with one flag.

## Row for `docs/ARCHITECTURE.md` section 12

| The choice | Compared against | What decided it, with the number and the file |
|---|---|---|
| The custom loop kept after building a LangGraph variant of the same agent | `--orchestrator langgraph` (`agent/sit_review_agent/orchestrator_langgraph/`) | The same review on the same document (18 findings, `not_fit`) at 424.7 s against 382.3 s; parity 26 of 28 with the two failures named; 436 lines against the 153 replaced; the backstop, sibling cancellation and resume still hand-written beside the framework (`docs/COMPARISON_LANGGRAPH.md`, `tests/test_parity_langgraph.py`, `docs/live_runs/langgraph_payments_v1_1/`) |
