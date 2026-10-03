# Run fixes worker, 3 Oct 2026

Branch `s4/runfix2`, after merging `origin/claude/happy-darwin-d0bl94` at 7f86403 (clean merge, commit 8810753).
The merge also brought the refine fallback work (refine.py, tests/test_refine_salvage.py, robustness results), not only config and decisions.

## B: run_s on every progress record
Files: `agent/sit_review_agent/orchestrator.py`.
The run clock now starts when the run state is created and is bound to the progress sink before `run_started`; resume binds it before its `run_started` too.
Tests in `tests/test_run_fixes.py`: `test_b_every_record_of_a_run_and_its_resume_carries_run_s` asserts that no record of a selftest run, a failed run or its resume has a null `run_s`.
`test_b_waking_lines_written_during_setup_carry_run_s` asserts that two `waking` lines written by a warm-up during setup carry a number.

## C: Tools used
Files: `agent/sit_review_agent/report/render.py`, `agent/sit_review_agent/report/templates/report.md.j2`.
`test_c_tools_used_lists_only_servers_that_received_a_call` asserts that a server with 0 calls is left out, a disabled server stays under "Tools disabled", and no calls gives "none".

## D: session reopens
Files: `agent/sit_review_agent/manifest.py` (`extra.tools.session_reopens` and `session_reopens_by_server`), render.py and the template (run details row "Tool session reopens").
`test_d_manifest_counts_the_session_reopens_of_the_gateway_stack` asserts the count found through the gateway stack, and 0 for none or a doc-only run.
`test_d_report_shows_the_session_reopen_line_zero_included` asserts "0", "2 (mcp-search: 2)" and "not recorded" for an older manifest.
`test_d_a_run_records_the_reopen_count_in_its_manifest_and_report` asserts a selftest run writes 0 in the manifest and the report.

## E: sufficient_evidence
Files: `agent/sit_review_agent/stop_rules.py` (`evidence_tally`, `fitting_reason`, `settle_sufficient_evidence`), `phases/research.py` (`_finish`), `phases/report.py` (`_default_stop_reason`).
The gate runs when research ends and again at report time, when findings cite their sources; a refused claim is restored at report time if two external sources are then cited.
The fitting reason is `budget_tool_calls` (tool-call or round limit reached), else `tool_failure` (calls made, none succeeded), else `no_marginal_gain`, with the counts in the detail.
Six `test_e_*` tests assert: 1 of 6 is refused; 3 of 6 and 3 of 5 pass and 2 of 5 does not; two cited external entries pass and one does not; the limit that ended research is chosen; a refused claim returns; other reasons pass unchanged.
Two existing tests changed to the new rule: `test_research_disclosures.py::test_stop_vote_with_one_answer_of_three_is_not_sufficient_evidence` (renamed) and `test_research_phase.py::test_no_external_questions`.

## G: launch record
Files: `agent/sit_review_agent/ui/launcher.py`, `agent/sit_review_agent/ui/rundata.py` (`reviewed_pdf` resolves the new forms).
`test_g_the_launch_record_carries_no_path_under_the_home_folder` asserts that no home path or user name is in `launch.json`, the document is relative to the runs directory, other paths use `~`, and the reviewed PDF is still found.
`tests/test_ui_server.py::test_start_launches_dra_review_as_a_subprocess` now asserts the portable record instead of absolute arguments.

## Runbook
`docs/DEMO_DAY_RUNBOOK.md` line 130: "four assess shards" changed to "six assess shards".

## Gates
ruff: `All checks passed!`
pytest: `62 failed, 1851 passed, 1 skipped, 2 xfailed, 2 errors`.
The same 62 failures and 2 errors occur at the merge commit 8810753 without these fixes; this work adds none.
They follow from the six assess shard groups in `config/agent.yaml` (tests and replay fixtures still expect four shards, for example `assert 6 == 4` and `KeyError: 5`).
selftest: `selftest passed in 0.4 s`.
prompts: `PROMPTS.lock up to date (bundle 6f0ee28ab9ac)`.

## Not verified
No live run with tool servers, so B, D and E are not seen on a real 30-page review.
The reopen count covers the current process only: reopens before a resume are not added.
The 64 shard-count failures are not fixed, because they need fixture or answer-key changes this task may not make.

## E, planner ruling after the first report
A research skip with no external question now keeps `sufficient_evidence` / `no_external_questions`, the reason used before the gate, because nothing was tried; `test_research_phase.py::test_no_external_questions` asserts that detail again.
`test_e_research_skipped_with_no_external_question_keeps_its_reason` asserts the skip passes unchanged, and that a plan with an external question gets no such pass.
