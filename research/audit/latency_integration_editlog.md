# Latency integration pass: edit log

Branch `s4/integration2`, worktree `/Users/malco/Desktop/SIT-wt/int`, started at `c1354de` (W2's tip).
No model call was made.

## Merges (no conflicts)

| Branch | Tip | Merge commit |
|---|---|---|
| `s4/w1-latency` | `ded4394` | `fa03b61` |
| `s4/w3a-latency` | `9e41553` | `5d66838` |
| `s4/w3b-latency` | `502a256` | `a3a1c37` |
| `s4/w3c-latency` | `26795e2` | `004ca0d` |

## Commits

| Commit | Seam | Files | What |
|---|---|---|---|
| `ceb7080` | a | `llm/claude_code.py`, `llm/partial.py`, `manifest.py`, `tests/test_stream_gateway.py`, `tests/test_stream_fixtures.py`, `tests/test_manifest_concurrent.py` | A cut call logs `estimated_usage` and `partial`; replay rebuilds the cut from the entry (new assertion, mutation-checked). |
| `a3c5c35` | b | `states.py`, `agent/README.md`, `tests/robustness/test_robustness_scenarios.py`, `tests/robustness/README.md` | BEH-25 reads the stage tables; `TRANSITIONS` and `ON_CAP` deleted. |
| `492e3e5` | g, c | `selftest.py` and five test files | The selftest fixture answers per shard, refines by revisions and gives the verdict only; tests follow the merged IDs; W2 items 7 and 8. |
| `71b59c5` | i | `replay.py`, `tests/test_cli_replay.py`, `tests/test_budget_counts_failed_calls.py` | Defect: the replay wrapper hid the shard protocol; fixed, new byte-equal concurrent replay test, mutation-checked. |
| `901546a` | c | three test files | W2 item 9 and the per-shard truncation and cost expectations. |
| `b372462` | c | `orchestrator.py`, `tests/test_stream_progress.py` | The four milestones are called; new test, mutation-checked. |
| `52f8d0b` | d | three tests, `docs/DEMO_DAY_RUNBOOK.md` | The held-red tests follow the 75 s reserve; runbook pending notes removed. |
| `d135a6c` | e | `eval/prereg.yaml`, `eval/EVAL_PLAN.md`, `eval/prereg_deviations.md` | A4b-medium renamed A4b-high; entry 11 extended. |
| `8962ab5`, `68d8555` | f | `llm/outputs.py`, `tests/test_llm_schema_descriptions.py` | LLM-facing descriptions in plain prose; new test, mutation-checked. |
| `31ee48d` | f | `llm/outputs.py`, `phases/refine.py`, `prompts/refine.md`, `PROMPTS.lock`, `selftest.py`, `agent/README.md`, four test files | Interface change: `FindingRevisionDraft.next_step`; five guards mutation-checked. |
| `972114b` | j | `llm/gateway.py`, `llm/runtime.py`, `tests/test_call_log_run_fields.py` | The call log writes `shard` and `start_offset_s`; four guards mutation-checked. |
| `bdf78f1` | h | `orchestrator.py` | Defect found by OPS-10: assess had no done line. |
| `e9606d5` | h (partial) | robustness harness, scenarios, regressions | Patches split per shard, merged IDs, refine patches on revisions. |

## Not done

Seam h is incomplete: `AWAITING_INTEGRATION` is still `True`, the results CSV is not regenerated, and ten robustness tests fail (see the report).
The pass stopped there because a tool-layer safety stop ended a turn during that work; it was not resent.

## Seam h (finished 2026-10-03 08:50, second worker)

The ten failures of the first pass and the six concurrent schedules, each at its cause.
Oracles were restated to the shard form, never weakened; counts changed only where one assess call became four shards, and the reason is in the row's docstring and registry text.

| Commit | Files | What |
|---|---|---|
| `938bf6d` | `phases/_model_calls.py`, `phases/assess.py`, `tests/robustness/test_robustness_regressions.py` | Defect: the per-shard truncation note did not name its two call IDs. `PhaseCall.truncated_ids`; the LLM-07 regression test asserts 4 x 2 calls, one note per shard naming its IDs, one stage-level note. |
| `b068af1` | `test_robustness_scenarios.py`, `robustness_coverage.py` | LLM-01: the 429 on attempt 0 of each shard, each waits >= 15 s; LLM-02: each of the six stage 1 calls makes max_retries + 1 attempts, exit 3 once. |
| `1a8f215` | `errors.py`, `phases/assess.py`, `orchestrator.py`, scenarios | LLM-03 ruling: `AssessShardsFailed` (exit code of the first shard's error, resumable); `_run_fail` writes `report.partial.md` for it, listing each shard and its error, and `failure.json` names `partial_report` and `shards`. |
| `1ce41e9` | `llm/runtime.py`, `phases/assess.py`, `report/render.py`, scenarios | Defect: `report.md` rendered a bare "not assessed" when every shard declined (the renderer keyed on the sequential event text). `DECLINED_EVERY_ASSESS_SHARD` shared by the merge and the renderer. LLM-06 per shard. |
| `36de9d5`, `1caa379` | scenarios | LLM-07, LLM-10, LLM-11 restated (nth 0 = shard 1; six unsent refusals; six auth refusals, none retried). |
| `b13bca3`, `4e632f8` | `llm/runtime.py`, `llm/gateway.py`, `llm/claude_code.py`, `tests/test_runtime_policies.py`, scenarios, `robustness_repro.py` | NET-02 ruling: `FirstCallNetwork` windows every call started before the API has answered one (a result or an HTTP error status), in all three gateways; the first to give up exits 3 once, the rest are cancelled. NET-02 on the scheduling clock. |
| `59a8bcb` | scenarios | BEH-25: the plan checkpoint, completed phases ingest to plan, research not started, `stage1_ready` checks. |
| `5290705` | `phases/_model_calls.py`, `robustness_coverage.py`, `README.md`, `concurrent_oracles.py`, `test_robustness_concurrent.py`, `test_robustness_results_csv.py`, `test_robustness_schedules.py` | `AWAITING_INTEGRATION = False`, markers cleared. Contract: a not-assessed criterion is `not_applicable` with a note starting "not assessed" (the output schema's only form); the oracle maps it to `NOT_ASSESSED`. Defect: `call_model` now yields once before every logical call, so the shards' first calls are `nth` 0..K-1 in launch order whatever the backend's latency. The six schedules run on the scheduling clock. |
| `e03e255` | `orchestrator.py`, `phases/assess.py`, `tests/test_orchestrator.py` | BEH-29 defect: a `process:` fault with `shard` wrapped the whole member. It wraps that shard's `run_shard`; a shard's unexpected exception ends the shard (outcome error, disclosed by name and class), every shard crashing is a `StageCrash`. |
| `1ec643b` | scenarios, `robustness_repro.py` | LLM-05 passed on the serial clock for the wrong reason (the hang cut every shard). Scheduling clock; shard 1 cut and disclosed, three shards' findings kept, verdict assessed. |
| `1dd38e0` | scenarios | LLM-08, NET-01, OPS-04 assert the shard form (repair on shard 1; four shard files on disk; resume re-runs no shard). |
| `9729942` | `results/` | Regenerated by the suite: 87 rows, 55 PASS, 32 BLOCKED (laptop and static). |
| `53a1b6c` | `test_robustness_concurrent.py` | The surviving mutation of the not-assessed predicate is now caught by a direct test. |
| `ae08a08` | `tests/test_llm_phases.py`, `tests/test_truncation_fallback.py`, `tests/test_adversarial_invariants.py` | Unit tests follow the launch-order interleaving; `AssessShardsFailed` asserted and mapped by INV-11. |

### Mutation round

Each guard removed, the test seen failing, the file restored from a `cp` backup (tree clean after each):
the shard note's call IDs (2 tests fail); the partial report on every shard failing (LLM-03 fails); the renderer's sharded declined event (LLM-06 fails); the first-call window on the first call started only (the concurrent unit test fails; NET-02 end to end does not discriminate it, the cancellation hides it); an answer never ending the window (2 unit tests fail); no yield before a logical call (LLM-14, LLM-15 fail); a shard crash propagating (BEH-29 and 2 unit tests fail); the shard fault wrapping the whole member (BEH-29 fails); the not-assessed predicate without the note (survived, then caught after `53a1b6c`).

### Not verified

Anything live; the timed rehearsal; the `shard` and `start_offset_s` fields on a live `claude_code` log; the Anthropic gateway's cut salvage; the mutation round on W3a's replay matching (still deferred).
