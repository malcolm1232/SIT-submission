# Worker note: refine prior-status fix, gates

Builder commit 8f3f6f2 on branch s4/refine-prior-status; the verifier squashed it with the WIP checkpoint onto cb527e5 as one linear commit.

## Files changed

- agent/sit_review_agent/llm/outputs.py (missing_prior_statuses)
- agent/sit_review_agent/phases/_model_calls.py (KeptItems.statuses, retry event)
- agent/sit_review_agent/phases/refine.py (status-only split, repair impact, degradation event)
- tests/test_refine_prior_status.py (new)

## Tests

- test_a_answer_missing_only_statuses_keeps_every_revision_and_asks_for_those
- test_b_the_repair_returns_the_statuses_and_prior_statuses_is_complete
- test_c_a_cut_or_failed_repair_applies_the_first_answer_and_discloses_the_priors (three parameters: was cut by the stage limit, did not match the output schema, failed (LLMUnavailableError))
- test_a_set_that_breaks_a_rule_with_statuses_missing_is_asked_again_whole (added by the verifier)

## Gates

- ruff check agent harness tests: All checks passed!
- full pytest: 2005 passed, 1 skipped, 2 xfailed (builder); 2006 with the verifier's test
- sit-review selftest (no API key): selftest passed in 0.4 s
- prompts --check: PROMPTS.lock up to date (bundle 2569a967015b)

The planner ruled that the degradation text does not list the prior ids because the delta table names them; the ids clause was removed from the assertion.

## Verification

Verifier result: parts (a) and (b) hold; part (c), the fallback merge of drafts carrying the same prior id, is NOT in the code and has no test, so it was left out of the commit message.
Mutation: restoring the old `if not kept_ids or not retry: return None` in split_revisions fails all 5 builder tests; dropping the revision_problems guard of the kept-all path survived the builder tests and now fails the added test.
Probes: all 5 statuses missing keeps all 55 and asks for all 5; one bad revision plus 4 missing statuses takes the normal path (54 kept, 1 retried, 4 statuses); a repair status for an unknown or non-prior id is ignored.
Gates by the verifier: ruff clean, 2006 passed 1 skipped 2 xfailed (also from ~), selftest passed, PROMPTS.lock up to date, make smoke exit 0, robustness 161 passed, leakage_grep PASS.
