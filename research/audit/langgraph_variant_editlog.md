# LangGraph orchestrator variant: edit log (session 4, 2026-10-03)

Scope: a LangGraph variant of the orchestrator beside the custom loop, so the two can be compared on the same documents by the same harness (`docs/COMPARISON_LANGGRAPH.md`).
Branch `s4/langgraph`, from `430321d`, worktree `/Users/malco/Desktop/SIT-wt/langgraph`, its own virtualenv (`/opt/homebrew/bin/python3.13`).
Packages added to that venv only: `langgraph==1.2.12` (with `langgraph-checkpoint 4.2.0`, `langgraph-prebuilt 1.1.0`, `langgraph-sdk 0.4.5`, `ormsgpack 1.12.2`, `xxhash 4.0.1`); declared as the optional extra `[langgraph]` in `pyproject.toml`, never as a main dependency.
Not modified: `orchestrator.py`, `phases/`, `llm/`, `tools/`, `report/`, `replay.py`, `manifest.py`, every prompt (`prompts/PROMPTS.lock` unchanged), every config file.
Nothing against the SIT MCP hosts (every run `--no-tools` or `transport: fake`); nothing under `eval/blind/` opened; nothing under `docs/transcripts/` read.

## 1. Edits by step

### Step 1: the variant (commit `bee5f8e`)

| File | Change | Why |
|---|---|---|
| `agent/sit_review_agent/orchestrator_langgraph/graph.py` (new) | `LangGraphOrchestrator(Orchestrator)`: `run` builds a `StateGraph` per run (`build`), compiles it with the run-dir saver and invokes it; nodes `ingest`, `stage1_open`, `stage1_chain` (a compiled subgraph: understand and plan from `START`, a `gate` join, research behind the plan-only and limit gate), `assess_shard` (one `Send` per shard of `AssessSettings.shards_for`), `assess` (an unsharded assess phase, as the tests' stand-ins), `merge`, `refine`, `verify`, `report`; routers `_fan_out` and `_route_refine`; `_member` (a member's coroutine as a task with the stage 1 backstop polled on the run clock and the typed failure mapping); `_cancel_others` | The same phases, gateways, checkpoint and progress writers, scheduled by the framework; the bookkeeping (`checkpoint`, `_ended`, `_close`, `_cap`, `_skip_on_cap`, `_single`, `_member_cut`, `_member_skipped`, `_store_shard`, `_load_shards`, `_milestone`) is inherited, so the comparison is about the loop |
| `agent/sit_review_agent/orchestrator_langgraph/saver.py` (new) | `RunDirSaver(InMemorySaver)`: the framework's checkpoints, mirrored one JSON line per superstep to `<run>/langgraph/graph_checkpoints.jsonl` (thread, step, checkpoint id, the control channels) | LangGraph's checkpointer carries the graph's control state; the run state stays in the repo's `checkpoints/<nn>-<phase>.json`, which `resume` reads |
| `agent/sit_review_agent/orchestrator_langgraph/__init__.py` (new) | `using_langgraph()` (swaps `orchestrator.Orchestrator` for the duration of one call), `run_review`, `resume_run` wrappers; an `ImportError` naming the extra when `langgraph` is missing | `orchestrator._run_execute` names the class, and `orchestrator.py` is not to be modified |
| `agent/sit_review_agent/cli.py` | `--orchestrator custom|langgraph` on `run`, `review` and `resume` (`OrchestratorOpt`, `_entry_points`); `--k` with the variant is a usage error; the docstring's usage line | Selected by a flag that defaults to the custom loop, so the product is unchanged without it |
| `pyproject.toml` | Optional extra `langgraph = ["langgraph==1.2.12"]` with a comment | The variant's dependency, outside the product's |

### Step 2: the parity checklist (commit `c4d94b9`)

| File | Change | Why |
|---|---|---|
| `tests/test_parity_langgraph.py` (new) | Ten behaviours run through both orchestrators by the `orch` fixture (the class swapped as the flag swaps it); two expected failures for the variant, named | The checklist of `docs/COMPARISON_LANGGRAPH.md`, as a test file |
| `agent/sit_review_agent/orchestrator_langgraph/graph.py` | The variant's note on the progress stream is a `status` line, not a new event type | `spec/progress_event.schema.json` closes the type list; the first draft failed `tests/test_progress_events.validate` |

### Step 3: the live run (commits `7b07e92`, `99d64d5`)

| File | Change | Why |
|---|---|---|
| `docs/live_runs/langgraph_payments_v1_1/` (new) | The run directory without `progress.log`, `progress.jsonl` or `snapshots/`; `MEASUREMENT.md` with the stage table beside `rehearsal_concurrent_1` | The one live Opus run of the variant |

### Step 4: the scoring (commit `f74beda`)

| File | Change | Why |
|---|---|---|
| `docs/live_runs/langgraph_payments_v1_1/eval_pilot_bounded/` (new) | `scores.json`, `scores.md`, `judge_calls.jsonl`, `judge_results.jsonl`, `stdout.txt` (the harness's `cli_cwd/` scratch left out) | The one scoring, the setup of `rehearsal_concurrent_1/eval_pilot_bounded/` |

### Step 5: the comparison note (this commit)

| File | Change | Why |
|---|---|---|
| `docs/COMPARISON_LANGGRAPH.md` (new) | The measured table, the parity checklist, the lines of code, what the framework made easier, awkward and could not do with file and line, the conclusion, the row for section 12 | The deliverable |
| `docs/ARCHITECTURE.md` | Section 12 gains the row | Where the comparisons are listed |
| `research/audit/langgraph_variant_editlog.md`, `docs/transcripts/session4/langgraph_variant.md` (new) | This log and the worker report | Session record |

## 2. What was verified offline, with the command

| Check | Command (from the repo root, the worktree's venv) | Result |
|---|---|---|
| The fixture run through the variant | `sit-review run agent/sit_review_agent/fixtures/selftest/design.pages.txt --transport fake --replay agent/sit_review_agent/fixtures/selftest/cassettes --orchestrator langgraph --run-id lg-selftest` | exit 0, `report.md` written; `report.json` equals the custom loop's on the same fixture (`replay.compare_reports` empty); `ledger.json` differs only in `retrieved_at` (system clock) |
| `dra replay` of that run | `sit-review replay runs/lg-selftest --run-id lg-selftest-rp` | exit 0, "replayed report matches the recording", `ledger.json` byte-equal to the record |
| `dra coverage` of that run | `sit-review coverage runs/lg-selftest` | exit 0, the criteria x sections map |
| Progress events | the two fixture runs' `progress.jsonl` | the same multiset of event types (87), plus the variant's one `status` line |
| The custom loop's own orchestrator tests under the variant | `tests/test_orchestrator.py` with the class swapped | 15 of 21 pass; the 6 failures assert the launch order of the stage 1 members (`log == ["ingest", "understand", "plan", "assess", ...]`), which LangGraph does not keep (it starts parallel nodes by node name: `assess`, then the chain's `plan` before `understand`); nothing else differs |
| The resume, synthetic e2e, truncation, verdict and disclosure tests under the variant | `tests/test_e2e_synthetic.py`, `test_run_and_resume.py`, `test_truncation_fallback.py`, `test_not_assessed_verdict.py`, `test_research_disclosures.py` with the class swapped | 46 of 51 pass; the 5 failures are the same launch-order assertions (the latest checkpoint's phase, the per-member seconds of overlapping members); the behaviours are re-asserted order-free in the parity file |
| The parity file | `pytest -q --tb=no -p no:warnings tests/test_parity_langgraph.py` | 26 passed, 2 xfailed |

## 3. The live run and the scoring

- Run: `env -u ANTHROPIC_API_KEY sit-review review eval/synthetic/payments_orchestration/design_v1.pdf --profile demo --no-tools --orchestrator langgraph --run-id langgraph_payments_v1_1`, 17:28:21 to 17:35:28 +08, exit 0, output to a scratchpad file and read by tail only.
- Result: 424.7 s, $4.71 lower bound (one cut call with unrecorded usage), verdict `not_fit` 0.75, 18 findings and 3 strengths, `completed_degraded`; assess shard 2 cut by the runtime at the 265 s stage 1 limit with 14 findings salvaged; Mac load average 15.8 at the end.
- Secret greps over the run directory, counts only: `sk-ant-` 0, `ANTHROPIC_API_KEY=` 0, `Bearer ` 0, `ghp_` 0, `SIT_MCP` 1 file and `api_key` 1 file (the env-var and field names in `effective_config.json`, as in the committed rehearsal run).
- Scoring: `env -u ANTHROPIC_API_KEY sit-eval score runs/langgraph_payments_v1_1 --key eval/synthetic/payments_orchestration/answer_key.canonical.json --out runs/langgraph_payments_v1_1/eval_pilot_bounded --judge claude_code --model claude-opus-5-5 --effort high --samples 3 --seed 20261002 --concurrency 4 --max-cost-usd 18 --candidate-rule shortlist_bounded --exploratory`, 17:36:13 to 17:42:26 +08, exit 0, 86 judge calls, $9.45 reported, `status: pilot_unfrozen`, exploratory.
- Numbers (beside `rehearsal_concurrent_1`): strict recall 12 of 14 (13 of 14), lenient 14 of 14 (14 of 14), adjudicated precision 0.944 (0.944), severity-weighted recall 0.867 (0.933), critical recall 1.000 (1.000), hallucination rate 0 (0); the difference is F07 matched partially instead of strictly.
- Haiku: no Haiku call was made (every mechanics check ran on the fake gateway).

## 4. Gates at the end

| Gate | Command | Exit | Result |
|---|---|---|---|
| ruff | `ruff check agent harness tests` | 0 | All checks passed |
| pytest | `pytest -q --tb=no -p no:warnings` from the repo root | PYTEST_EXIT | 1866 passed, 2 xfailed (the two expected failures of the parity file) |
| selftest | `sit-review selftest` | 0 | passed |
| smoke | `make smoke` | 0 | selftest plus 252 passed |
| test | `make test` | MAKETEST_EXIT | ruff clean, 1866 passed, 2 xfailed |

Not run: `make smoke` and `make test` in a fresh clone (the venv here is the worktree's own, created today).
