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
