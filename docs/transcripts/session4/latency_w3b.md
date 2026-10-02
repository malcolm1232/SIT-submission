# Latency W3 part B: fault schedules and robustness for the concurrent stage

Branch `s4/w3b-latency` on base `87a0634`, worktree `/Users/malco/Desktop/SIT-wt/w3b`, not pushed.
Two shifts did this work: the first committed `b50f5df` and `ea52623` and was ended mid-task by a model-side safeguard, and the second finished its uncommitted item 3 and committed `c2cb64f` and `fee8175`.
Nothing under `eval/blind/`, `docs/design/` or `docs/transcripts/` was opened, no model call was made, and no recorded model output was printed.
One Bash call of the second shift was stopped by the safety classifier and was not resent; it listed references to the results CSV and printed the head of the committed summary file, and nothing from it was needed.

## What is in the tree

`b50f5df` adds six schedules under `tests/robustness/faults_concurrent/` (LLM-13 one assess shard hangs, LLM-14 one shard declines twice, LLM-15 one shard is truncated twice, LLM-16 refine is cut, LLM-17 research is cut, BEH-29 one shard fails with an exception), a loader that resolves a shard index in launch order to the stage's logical call index `nth`, one oracle per schedule, and their tests on fixtures.
`ea52623` restates the ten P0 rows whose expectation the redesign changed and marks them and the six new rows "awaiting integration" in the coverage table and the README.
`c2cb64f` makes the results table hold 87 rows, with every awaiting row `BLOCKED` and a note that starts "awaiting integration (concurrent orchestrator, W2)", never `PASS` before integration even when its sequential-design case ran, and regenerates the CSV with the suite's own runner.
`fee8175` adds two tests in `tests/test_fault_injection.py`: shard 1 calls [0, 1] resolve to `nth` [1, K] and fault exactly those logical assess calls through `FaultInjectingLLMGateway`, and a shard index out of range is refused with an error naming the schedule, the run's K and its shards.

## Evidence

Five mutations were each caught by a test and each file was restored from a `cp` backup with a clean tree afterwards: the follow-up `nth` formula, the shard range check, the oracle's `not_assessed` verdict check, an awaiting row allowed to pass, and the six concurrent rows dropped from the table.
The regenerated CSV compared by script against the one at `87a0634` shows 81 rows become 87, the six added rows `BLOCKED` awaiting integration, ten rows moved from `PASS` to `BLOCKED` awaiting integration by design, and no other status change.
Gates at `fee8175`: `ruff check agent harness tests` exit 0, `pytest -q` 1277 passed and 6 skipped exit 0, `sit-review selftest` exit 0, `make smoke` 218 passed exit 0, `make test` 1277 passed and 6 skipped exit 0, and the robustness runner 152 passed and 6 skipped exit 0.
The six skips are the end-to-end form of the six scenarios, which waits on `AWAITING_INTEGRATION`.

## Not verified

The six schedules have never executed, because the orchestrator that runs stage 1 concurrently is W2's work and is not in this tree, so every oracle has only been shown to pass on a fixture built from the control run and to fail on each broken variant of it.
The first shift's own mutation results are unknown.

## For the integration pass

Once the W2 orchestrator is on the branch, set `AWAITING_INTEGRATION = False` in `tests/robustness/robustness_coverage.py`, which un-skips `test_concurrent_scenario_end_to_end` and lets the ten changed rows and the six new rows be evaluated.
Write each resolved schedule with `python tests/robustness/concurrent_schedules.py <ID> --out <file>` and run it with `sit-review run agent/sit_review_agent/fixtures/selftest/design.pages.txt --transport fake --replay tests/robustness/fixtures/cassettes --faults <file>`, the demo profile for LLM-13, LLM-16 and LLM-17.
Confirm the two contract names in `concurrent_oracles.py` (`NOT_ASSESSED`, `DISCLOSURE`) against what the orchestrator writes, and never drop a check to make a row pass.
Confirm from the run's `llm.jsonl` that the K assess shards reach the fault wrapper in launch order, so the first K assess calls are `nth` 0 to K-1, and add a shard-name check to the oracles if W2 logs the shard name per call.
Decide LLM-03's persistent variant, where every shard is overloaded past the retry budget: run-level exit 3 as now, or failed shards and a not-assessed report, with "overloaded" disclosed either way.
LLM-13 must show shard 2 (claims_and_assumptions) cut at `stage_limits_s.stage_1_end`, not retried, disclosed as budget_or_deadline_hit naming the shard, its criteria not assessed, the findings of shards 0, 1 and 3 present, the verdict assessed, and exit 0.
LLM-14 must show shard 0 (intent_and_fitness) refusing its call and its reframed retry at `nth` 0 and 4 with no third call, "declined" disclosed naming the shard, its criteria not assessed, the findings of shards 1, 2 and 3 present, the verdict assessed, and exit 0.
LLM-15 must show shard 1 (requirements_and_consistency) truncated at `nth` 1 and 4 with no third call, "truncated twice" disclosed naming the shard, its criteria not assessed, the findings of shards 0, 2 and 3 present, the verdict assessed, and exit 0.
LLM-16 must show the refine call cut at `stage_limits_s.refine_end` and not retried, the merged findings standing in severity then confidence order with none revised, the fallback disclosed naming refine, the verdict assessed, and exit 0.
LLM-17 must show research's second model call cut at `stage_limits_s.stage_1_end` and not retried, stop reason deadline, the first round's external evidence kept in the ledger and replaying exactly, the cut disclosed naming research, the shards' findings present, and exit 0.
BEH-29 must show an exception at the start of shard 3 (risk_and_operations) producing a partial review and never a crash, with exit 0, `report.json`, no `failure.json` and no `report.partial.md`, the failure disclosed naming the shard, its criteria not assessed, the findings of shards 0, 1 and 2 present, and the verdict assessed.
Then rewrite the ten changed rows' checks in `test_robustness_scenarios.py` to their new expectation, clear `awaiting` on each, regenerate the results with `ROBUSTNESS_RESULTS_CSV=tests/robustness/results/robustness_results.csv pytest tests/robustness -q`, and expect 87 rows with no "awaiting integration" note left for the integration pass.
