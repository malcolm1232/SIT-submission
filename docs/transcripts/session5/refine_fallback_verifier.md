# Refine fallback: independent verification

Verifier: a fresh Opus agent, 3 Oct 2026, worktree `SIT-wt/refinefix`, branch `s4/refinefix`.
Branch HEAD at the start was `beb87f5`; `origin/claude/happy-darwin-d0bl94` was `481cedb` and is an ancestor of HEAD (exit 0).
The machine load stayed under 6 and free memory over 55 percent for every test run.

## Gates (exact output lines)

1. `pip install -e '.[dev,langgraph]'`: exit 0 (only the pip upgrade notice printed).
2. Full suite from the worktree: `1902 passed, 1 skipped, 2 xfailed in 209.84s (0:03:29)`.
3. Full suite from `~`: `1902 passed, 1 skipped, 2 xfailed in 216.82s (0:03:36)`.
4. `ruff check agent harness tests`: `All checks passed!`.
5. `sit-review selftest`: `selftest passed in 0.5 s`.
6. `make smoke`: `254 passed, 1 skipped in 10.15s`, exit 0.
6. `make test`: `1902 passed, 1 skipped, 2 xfailed in 215.36s (0:03:35)`, exit 0.
7. `pytest tests/robustness`: `161 passed in 20.60s`.
7. CSV regeneration: `161 passed in 21.95s`; 88 rows before and after, same header, and only the `commit` and `duration_s` columns differ (checked by a script over every row).
7. The regenerated CSV was committed as `a98e7c0`.
8. `convert_answer_keys.py --tier synthetic --check --verify-anchors`: `45 flaws converted across 3 keys; 0 key(s) failed validation`.
9. `scripts/leakage_grep.py`: `PASS: no unresolved hit in a gated area`, exit 0.
9. `python -m sit_review_agent.prompts --check`: `PROMPTS.lock up to date (bundle 6f0ee28ab9ac)`, exit 0.
9. `tests/test_export_public_snapshot.py`: `65 passed in 3.31s`.
11. Em dashes in the diff over the tip: `0`; co-authored lines in the branch commit bodies: `0`.

## Test count

The tip reported 1894 with the `[langgraph]` extra installed; this branch adds the 8 tests of `tests/test_refine_salvage.py`, so 1894 + 8 = 1902 passed.
The 2 xfailed are the two known parity xfails of the langgraph parity tests.
The 1 skip is `tests/test_skeleton_imports.py:45: langgraph is installed here`, a test that only runs when langgraph is absent.
The worker's `1874 passed, 2 skipped` was a run without langgraph, where the 28 parity tests do not run.

## Guard check

`refine.py` was copied to the scratch folder, then the single line `salvage = salvage_revisions(call.partial, drafts) if call.cut else None` was replaced by `salvage = None`, so a cut refine call discards its finished revisions.
`tests/test_refine_salvage.py` then gave `6 failed, 2 passed`.
The failing tests were `test_cut_after_10_of_20_revisions_applies_the_10`, `test_merge_whose_target_the_cut_lost_keeps_both`, `test_merge_into_a_salvaged_keep_is_applied`, `test_ranks_with_gaps_keep_the_independent_revisions`, `test_applied_evidence_reaches_the_ledger_and_the_finding` and `test_a_salvaged_revision_that_breaks_the_rules_is_dropped`.
The 2 that still passed are the two parameters of `test_cut_with_nothing_finished_keeps_the_old_fallback` (`partial` of `None` and of an empty revision list), where the old fallback is the right answer.
The file was restored from the backup, `cmp` showed no difference, and the file ran `8 passed` again.

## Not verified

No live agent run and no model call was made, so the salvage was not seen on a real cut stream from the model runtime.
The partial `revisions` payload a real cut call hands back is exercised only through the tests' stubbed `PhaseCall.partial`.
The report rendering of the new degradation impact text was not read by eye.
The code was not reviewed line by line for design quality; this pass checks the gates and that the tests guard the behaviour.
