# Run fixes, usage estimate and six-shard fakes: verifier note (4 Oct 2026)

## Merge
The worktree `s4/shards6` at 2900284 (stacked on runfix3 f3dce06, itself on runfix2's a3ee771) took `git merge s4/runfix2` (67bd0c9) cleanly as c157cd8.
The remote tip 7f86403 was unchanged after the fetch.
`merge-base --is-ancestor` printed 0 for 67bd0c9, f3dce06, 2900284 and origin/claude/happy-darwin-d0bl94.

## Merge interaction found and fixed (d1233d1)
The first full suite after the merge printed `4 failed, 1921 passed, 1 skipped, 2 xfailed`.
Three were the console baselines in `tests/fixtures/progress/`: the shards6 baselines predate runfix2's sufficient_evidence gate.
Each scenario differs by one line becoming two: the fake research claims sufficient_evidence with 1 of 11 plan questions answered and 0 cited sources, so the gate now records it as no_marginal_gain with a WARN line.
The baselines were regenerated with `tests/test_progress_console.py --write` (2 insertions, 1 deletion per file).
The fourth was `test_a_stage_that_truncates_twice_ends_in_a_disclosed_degraded_report[plan]`, which asserted the control run's stop code.
A truncated plan is code-built with no external question, so research is skipped and keeps its labelled `sufficient_evidence` / `no_external_questions` (the runfix2 rule), while the control run is now gated to no_marginal_gain.
The plan branch of that test now asserts that skipped reason; the other three stages still assert equality with the control.

## Gates (after d1233d1)
ruff: `All checks passed!`
Full suite from the worktree: `1925 passed, 1 skipped, 2 xfailed in 223.11s (0:03:43)`
Full suite from `~`: `1925 passed, 1 skipped, 2 xfailed in 225.95s (0:03:45)`
selftest: `selftest passed in 0.5 s`
make smoke: `254 passed, 1 skipped in 10.83s`, exit=0.
make test: `1925 passed, 1 skipped, 2 xfailed in 226.45s (0:03:46)`, exit=0.
Robustness: `161 passed in 23.38s`; regenerated run `161 passed in 23.57s`.
Answer keys: `45 flaws converted across 3 keys; 0 key(s) failed validation`
Leakage grep: `PASS: no unresolved hit in a gated area`, exit=0.
Prompt lock: `PROMPTS.lock up to date (bundle 6f0ee28ab9ac)`
Public snapshot export: `65 passed in 2.00s`

## Test count
1911 on shards6 plus the 14 tests of `tests/test_run_fixes.py` that runfix2 added after a3ee771 gives 1925.

## Guard checks (cp backup, smallest edit, restore, cmp clean, 14 passed again)
(a) `render.py` "used_tools" filter reduced to `if t.enabled`: `test_c_tools_used_lists_only_servers_that_received_a_call` failed (1 failed, 13 passed).
(b) `EvidenceTally.sufficient()` made `return True`: six `test_e_*` tests failed (one_of_six, half_rounded_up, two_cited_external, fitting_reason, refused_claim_returns, research_skipped).

## CSV check
88 rows, same columns and scenario order; `commit` moved in 88 rows, `duration_s` in 40 rows and `date` in 88 rows (2026-10-03 to 2026-10-04, the run day stamp).
No result column (status, passes, value, threshold, notes and the rest) moved.
The regenerated CSV is committed.

## Diff over the remote tip
Em dashes 0, co-author lines 0, and under config, prompts and eval only `config/agent.yaml` changed (11 insertions, 4 deletions, the six groups).

## Not verified
No live run, no model call, no MCP server and no UI was exercised; all checks are offline tests and scripts.
The worker notes were not read, so their claims were checked only through the gates above.
