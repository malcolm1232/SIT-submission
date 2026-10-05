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
