# Refine fallback - worker report (3 Oct 2026)

Branch `s4/refinefix`, nothing pushed.

## Merge of claude/happy-darwin-d0bl94

The first merge conflicted in `agent/sit_review_agent/phases/refine.py` only and was aborted; the planner then ruled to resolve it keeping both sides.
Both hunks were resolved by keeping the tip's code exactly (the `kept_carry` and `ask` helpers, `ask=ask` on the call, and the `prior_statuses` filter) and placing the branch's salvage wiring after it (`since` before the call, then the salvage `if` and the old fallback as `elif`).
The `prior_statuses` filter runs only when the call returned a parsed answer, so a cut call leaves `prior_statuses` empty and the report marks every prior finding "not re-examined", as on the tip.
Ruff's import fix also removed an unused `PhaseCall` import that came from the branch side.
Before committing the merge: `tests/test_refine_salvage.py` gave 2 failed, 6 passed (as before), and `tests/test_reassessment_delta.py` plus `tests/test_llm_phases.py` gave 169 passed.

## Changes per file

- `tests/test_refine_salvage.py` (ruling 1): the `governance_decision` keep in the lost-merge-target test now passes a `next_step` through the shared `keep()` helper's keyword arguments, which the disposition rule in `revision_problems()` requires; the shared helper and `revision_problems()` are unchanged.
- `tests/test_refine_salvage.py` (ruling 2): the evidence test now finds the one existing ledger entry for `Q_NOTIFY`, checks FND-001 does not cite it before refine, and after refine asserts that FND-001 cites it and that the ledger still holds exactly that one entry for the quote.
- `agent/sit_review_agent/phases/_model_calls.py`: no change was needed.
  `_EvidenceResolver.doc_entry` already reuses an existing doc entry with the same location and quote through `_doc_index`, built from the whole ledger when the resolver starts, and `rewrite` makes the finding cite it.
  The old test failed only because it expected a new entry.
- `tests/robustness/robustness_coverage.py` and `tests/robustness/README.md`: the LLM-16 expectation now says the hang returned no revision and that revisions a cut call already returned are applied (covered by `tests/test_refine_salvage.py`).
- `tests/robustness/results/robustness_results.csv`: regenerated; it differs from the previous version only in the commit and duration columns (checked by a script over every row).

## Mutation check

The product file was backed up, and the line that indexes existing ledger doc entries in `_EvidenceResolver.__init__` was changed so it indexed none.
The evidence test then failed at `assert notify in cited` (the finding cited a new duplicate entry), and the other 7 passed.
A first mutation that disabled the reuse lookup itself also failed the test, at its precondition, because assess then duplicates the entry as well.
The file was restored from the backup and `cmp` against the backup reported no difference; afterwards all 8 tests passed.
For ruling 1 the test failed with the `next_step` removed (the state before the fix) and passes with it.

## Gates

- `ruff check agent harness tests`: `All checks passed!` (after sorting the import block of `tests/test_refine_salvage.py`, a pre-existing issue of the WIP commit).
- `pytest -q`: `1874 passed, 2 skipped in 188.90s (0:03:08)`; 1875 tests are collected here.
- `sit-review selftest`: `selftest passed in 0.4 s`.
- `pytest -q tests/robustness`: `161 passed`.

## Not verified

The brief quoted 1894 passing on the tip; this worktree collects 1875, and the branch only adds tests over the tip, so the gap is likely an environment difference, but the tip was not run here to confirm it.
`python tests/robustness/robustness_results.py` writes nothing on its own; the CSV was regenerated with the documented command `ROBUSTNESS_RESULTS_CSV=tests/robustness/results/robustness_results.csv pytest tests/robustness -q`.
No live run, no model call, and the remaining verifier gates were not run.
