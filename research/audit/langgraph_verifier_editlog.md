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

## 3. The live run `docs/live_runs/langgraph_payments_v1_1/`

- `dra replay docs/live_runs/langgraph_payments_v1_1 --run-id lgverify-replay-1` exit 0: 8 model calls and 0 tool calls replayed, "replayed report matches the recording".
- The orchestrator is recorded in the manifest's `code.argv` (`--orchestrator langgraph`; the manifest has no dedicated orchestrator field) and in `langgraph/variant.json` (`"orchestrator": "langgraph"`, langgraph 1.2.12).
- Secret scan, counts only: `oauth` 0; e-mail addresses 0; `Bearer` followed by a token 0 (the one `Bearer` is the scan line of `MEASUREMENT.md`); `sk-` not preceded by a letter 1, which is the literal `sk-ant-` (7 characters) in that same scan line; the other `sk-` hits are words such as `risk-`.
- By script against `manifest.json` and `report.json`: wall 424.727 s, cost 4.714814 USD with `cost_usd_lower_bound` true, 21 report entries = 18 findings (1 critical, 10 high, 7 medium) + 3 strengths, verdict `not_fit` at 0.75, degradation "assess shard 2/4 (requirements_and_consistency) was cut by the stage 1 limit at 265 s; 14 finished finding(s) kept".
- FIXED: `MEASUREMENT.md` line 7 said "21 findings (1 critical, 10 high, 7 medium) plus 3 strengths"; the severities sum to 18 and the 21 include the strengths, so it now says 18 findings.

## 4. The scoring under `eval_pilot_bounded/`

- `scores.json`: `exploratory` true (top level and `judge.exploratory`), status `pilot_unfrozen`; `stdout.txt` and `scores.md` name the exploratory setting.
- By script against `scores.json`: strict recall 12 of 14, lenient 14 of 14, adjudicated precision 0.944, severity-weighted recall 0.867, critical recall 1.0, strict precision 0.667 (12 of 18), PARTIAL_KEY_MATCH 2, VALID_UNPLANTED 3, INVALID_OPINION 1, 86 judge calls at 9.45 USD; all as in `docs/COMPARISON_LANGGRAPH.md`.
- Per flaw: strict matches cover 12 flaws, lenient 14; partial only F04 and F07 (the custom loop's run: F04 only), as the note says.
- The custom column against `docs/live_runs/QUALITY_COMPARISON.md` (concurrent `medium`) and `rehearsal_concurrent_1`'s own files: 382.274 s, 5.735748 USD, 18 scored, 13 of 14, 14 of 14, 0.944, 0.933, 4 of 4, PARTIAL_KEY_MATCH 1, VALID_UNPLANTED 3, DUPLICATE 1, 95 calls at 9.54 USD, strict precision 0.722, `not_fit` at 0.78; all match.

## 5. The note and the section 12 row

- Every file and line the note cites exists and names what it says (graph.py lines 18 to 21, 67, 98, 101, 136, 154, 180, 183, 191, 208, 225, 230, 339, 403 to 437, 465; `saver.py` line 30; `__init__.py` line 33; `orchestrator.py` lines 279 to 337, 319, 338 to 347).
- Lines of code recounted by script (no blanks, comments or docstrings): `graph.py` 365, `saver.py` 42, `__init__.py` 29 (436); the replaced `run` 12 + `_stage_1` 98 + `_member_end` 39 + `_StageFailure` 4 = 153.
- The conclusion names one document and one run per arm, the heavier Mac load (15.8 against about 5) and the exploratory status; the section 12 row of `docs/ARCHITECTURE.md` carries the same numbers. No em dash in the note, the row, the measurement, the builder's edit log or report.
- FIXED: the note said the stage 1 members "started within 0.2 s of each other in both runs, at about 2 s", and `MEASUREMENT.md` said "1.9 s to 2.1 s into the run in both runs"; the custom loop's run checkpointed ingest at 2.228 s and its own `MEASUREMENT.md` says about 2.3 s, so no committed file supports 1.9 s to 2.1 s for it. Both now give each run's own figure with its source.
- Added decision #42 to `docs/USER_DECISIONS.md` (the owner's words, the consequence, the five refused runs) and the comparison to row 8 (framework) of `docs/SUBMISSION_GAPS.md`.
