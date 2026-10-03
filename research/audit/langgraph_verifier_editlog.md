# Edit log: the independent verification of the LangGraph variant (2026-10-03)

Verifier in a fresh context on branch `s4/langgraph` from 527c60e (7 commits from 430321d).
No model calls; nothing against the SIT MCP hosts.

## 1. Isolation

- `git diff --stat 430321d..527c60e` touches no file under `orchestrator.py`, `phases/`, `llm/`, `tools/`, `report/`, `replay.py`, `manifest.py`; in `agent/` only `cli.py` changed, plus the new package `orchestrator_langgraph/`, plus `pyproject.toml` (the optional extra).
- `cli.py`: `--orchestrator` defaults to `custom`, whose entry points are `sit_review_agent.orchestrator.run_review` and `resume_run` as before; `langgraph` without the extra exits 2 (usage) with a message naming the extra (checked in a venv without it).
- A scratch venv with the base install and `[dev]` only (`langgraph` absent): the package, `cli` and `orchestrator` import; `sit-review selftest` exits 0.
- FAIL found: `make smoke` in that venv exited 2 with `test_skeleton_imports.py::test_module_imports[sit_review_agent.orchestrator_langgraph]` failing, and `tests/test_parity_langgraph.py` imported the variant at module level, so the full suite could not be collected without the extra.
- FIXED: `test_module_imports` skips the variant's modules when langgraph is absent (`pytest.importorskip`); a new test checks the variant's import error names the `[langgraph]` extra when it is absent; the parity module skips at collection without langgraph.
- After the fix, without langgraph: `make smoke` exit 0 (250 passed, 1 skipped); full suite 1838 passed, 2 skipped, 0 failed.

## 2. Parity checklist

- `tests/test_parity_langgraph.py` with langgraph 1.2.12: 26 passed, 2 xfailed; the xfail reasons are the two stated (LangGraph starts parallel nodes in its own order; a process fault on the whole assess member wraps `run_shards`, which the variant never calls).
- Vacuity: the `orch` fixture monkeypatches `sit_review_agent.orchestrator.Orchestrator` to `LangGraphOrchestrator`, and `orchestrator.py` line 1359 looks the class up as a module global at call time, so `run_review` (the ID test), `test_progress_events.concurrent_run` (the shard cut test, which imports `run_review` from the module) and the CLI `--orchestrator` flag (the replay test, which also asserts `langgraph/variant.json` exists on the LangGraph arm only) all run the graph on that arm.
- Mutation: in `orchestrator_langgraph/graph.py` the shard results were stored under their completion position instead of their plan index (`_shard_results[len(_shard_results) + 1]`, both writes); `test_finding_ids_do_not_depend_on_the_completion_order` then failed on `[langgraph]` only, `[custom]` passed. Restored from a `cp` backup; `git status` clean.
