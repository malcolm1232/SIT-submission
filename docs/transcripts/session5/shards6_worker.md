# Six assess shard groups: test suite worker (3 to 4 Oct 2026)
## Cause
Decision #40 moved `config/agent.yaml` from four assess shard groups to six, and only the config tests were run.
The scripted fakes were written for four shards: `SHARD_FINDINGS` in `tests/test_e2e_synthetic.py` had keys 1 to 4, so the fifth shard raised `KeyError: 5`.
Many other tests hard-coded four shards, the four group names, merged finding IDs that follow from the four-group order, or the four-group console lines.
The full suite on the branch tip gave `62 failed, 1841 passed, 1 skipped, 2 xfailed, 2 errors`.

## Shape of the fix
The synthetic fake deals each planted finding to the shard whose group holds its first criterion (`shard_findings(shards)`), so any group count is served; the planted findings, `MERGED_ID` and every finding assertion are unchanged.
The merged-ID fixture (`tests/test_merged_id_references.py`) names its two answering shards by group name; every other group answers with no finding.
Tests that counted shards, listed `assess-0-s1..s4`, wrote `/4` or summed call totals now read K from the config.
Where a merged ID depends on the grouping (the selftest fixture's needs-testing finding, the invented-quote draft in BEH-06), the test looks the finding up by title.
The concurrent fault schedules name their shard by criterion with a new `shard_of` key, resolved to the launch index by `tests/robustness/concurrent_schedules.py`, so a regrouping keeps each fault on the intended group (LLM-13 claims_and_external_constraints, LLM-14 fitness_for_objectives, LLM-15 verifiability, BEH-29 security_and_privacy).
The cut scenario of the console baselines now cuts the shard of claims_and_external_constraints, which holds one finding and one criterion without a finding, so the cut still leaves a criterion not assessed.
No product code under `agent/`, no prompt, no `config/agent.yaml` and no answer key was changed.

## Files changed
Fakes: `tests/test_e2e_synthetic.py`, `tests/test_merged_id_references.py`, `tests/test_adversarial_invariants.py`, `tests/test_cli_coverage.py`.
Counts: `tests/test_run_and_resume.py`, `tests/test_parity_langgraph.py`, `tests/test_progress_console.py`, `tests/test_progress_events.py`, `tests/test_orchestrator.py`, `tests/test_stream_progress.py`, `tests/test_call_log_run_fields.py`, `tests/test_truncation_fallback.py`, `tests/test_cli_replay.py`, `tests/test_fault_injection.py`.
Robustness: `test_robustness_scenarios.py`, `test_robustness_regressions.py`, `test_robustness_concurrent.py`, `concurrent_schedules.py`, `robustness_coverage.py`, `faults_concurrent/{BEH-29,LLM-13,LLM-14,LLM-15}.yaml`, `results/robustness_results.csv`.
Regenerated baselines: `tests/fixtures/progress/console_{selftest,shard_cut,fail_resume}.txt` (only shard lines and the cut scenario's counts changed).
New guard: `tests/test_shard_fakes_guard.py` reads the group count from the config and asserts every fake answers every group, and that each planted finding is dealt once on the configured and on a one-criterion-per-group split; `shard_of` has its own loader test in `tests/test_fault_injection.py`.

## Replay tests
No prerecorded replay fixture depends on the shard count; the cassettes under the selftest fixtures hold tool calls only.
The record-then-replay tests in `tests/test_cli_replay.py` (and the parity replay test) read the shard count from the recording's own `effective_config.json` (`recorded_shard_count`), not from the live config.

## Gates
Full suite: `1911 passed, 1 skipped, 2 xfailed` (1906 plus the 5 guard tests).
`ruff check agent harness tests`: `All checks passed!`.
`sit-review selftest`: `selftest passed in 0.4 s`.
`pytest tests/robustness`: `161 passed`.
The CSV changed in commit and duration, in the shard-count wording of LLM-01, LLM-02, LLM-05, LLM-11 and NET-02, in the notes of the four concurrent rows, and in NET-02's value (virtual time to the no-network exit, 4.8 s to 3.7 s, with eight stage 1 calls instead of six).

## Not verified
Nothing was run live, against a model or on the lab document; stage 1 timing with six groups is not measured here.
The concurrent schedules still run only on fixtures (awaiting integration), so `shard_of` is proven by the loader tests, not by a live faulted run.
