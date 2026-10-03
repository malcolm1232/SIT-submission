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
