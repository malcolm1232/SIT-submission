# Card A3: a resolved prior is a prior-table row only

A prior finding that the agent judges resolved now becomes a row of the prior table only, not a finding of the current report.
The verdict and the counts no longer include it.
Recorded as decision 47 in `docs/USER_DECISIONS.md`.

## Files

- `agent/sit_review_agent/delta.py`
- `agent/sit_review_agent/finding_refs.py`
- `agent/sit_review_agent/phases/report.py`
- `agent/sit_review_agent/state/run_state.py`
- `tests/test_reassessment_delta.py`

## New tests

- `test_a_resolved_prior_is_a_table_row_not_a_finding`
- `test_a_still_open_carrier_keeps_the_row_open_when_another_is_resolved`

## Gates

- Targeted (delta, refine prior status, eval grounding metrics): 28 passed.
- Ruff: All checks passed!
- Full suite: 2032 passed, 1 skipped, 2 xfailed.
- Selftest: selftest passed.
- Prompt lock: PROMPTS.lock up to date (bundle 2569a967015b).
- Robustness: 161 passed.

Gates run by a mechanical worker after the builder was stopped; the mutation test and the push are the verifier's.

## Verifier (second review, 6 Oct 2026 11:18)

The first verifier stalled after mutation 1 and its review lines were lost, so this review was redone from `git diff 7fad84e..9e019bd -- agent tests docs/USER_DECISIONS.md`.
Review: `move_resolved_to_prior_table` runs in `ReportPhase.run` before the verdict call (and before the B0 rule and `assemble_review`), only in delta mode.
`split_resolved` moves out each finding reassessed `resolved` whose prior ID the previous review has, keeps the IDs unrenumbered, records them in `state.finding_ids.report`, and gives one `resolved` entry per prior finding with no kept carrier, with the carriers' notes joined.
An existing entry as fixed as `resolved` or less stands; a withdrawal gives way.
References to a moved ID have no final ID, so `settle_refs` removes them from unresolved items, sound areas and the verdict; the cited set is computed from the kept findings.
The Review validator (`models.py` 805 to 815) still holds: the moved row has `finding_ids=[]`, so no listed ID fails the carrier check.
Probe P1 (two resolved carriers of one prior plus one new finding): both moved, the row is `resolved`, `finding_ids=[]`, `re_examined=True`, both notes joined; the verdict brief holds neither title; no moved ID in unresolved, sound areas or verdict; all invariants and INV-13 pass.
Probe P2 (a resolved carrier whose prior also gets a `still_open` refine status): run exits 0, the carrier is moved, invariants pass; refine's status for a carried prior never reaches `state.prior_statuses` (the answer is not taken, the uncarried prior is then "not re-examined", pre-existing behaviour), so the row is `resolved`; the less-fixed-stands rule is reachable only through `split_resolved` directly, as its test says.
Probe P3 (non-delta run): no `resolved_to_prior_table` event, no `report` key in `extra.finding_ids`, all three findings kept.
Mutation 2 (drop the less-fixed-stands rule): killed by `test_split_resolved_keeps_a_less_fixed_entry_and_replaces_a_withdrawal`.
Mutation 3 (move the split after the verdict call): killed by `test_a_resolved_prior_is_a_table_row_not_a_finding` (the verdict brief then holds the resolved title).
Mutation 4 (drop the `still_carried` skip): survives, and is equivalent in output: `build_prior_table` ignores a status for a prior that a final finding carries, so the skip only keeps `state.prior_statuses` tidy.
Mutation 1 (disable the split) was killed by the first verifier.
Result: verified; the tip merge and the gate chain follow in this branch's next commits.
