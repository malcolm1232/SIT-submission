# Worker note: refine fallback same-prior merge (card A2)

Commit c1409dd on s4/refine-fallback-merge, based on 39ae688.

## Change

In the fallback branch of `RefinePhase.run`, drafts that carry the same prior finding forward are now merged by code (`merge_same_prior` in `phases/refine.py`).
A carrier is a draft whose reassessment has a prior ID and a status other than new_in_update; drafts without one are never touched.
The kept draft is the least fixed carrier (`delta.LEAST_FIXED`, renamed from `_LEAST_FIXED`, then the lower rank), so the delta table keeps its reading of the prior.
The removed drafts move their criteria to the keeper (those it lacks), the same thing a refine merge moves through `apply_revisions`.
Evidence is not moved: the code's merge meaning ("its criteria move to the target, nothing else") contradicts the brief here, so the code wins.
Ranks are re-derived 1..k, `finding_ids.refine` maps each removed ID to the keeper, both IDs get a history note, and coverage and sound areas are remapped as after a refine merge.
The `refine_fallback` event gains `merged_same_prior` (the count) and its message names the merge when there is one.
Nothing changes outside the fallback branch.

## Tests (tests/test_refine_prior_status.py)

- test_the_fallback_merges_drafts_that_carry_the_same_prior_id
- test_the_fallback_merge_leaves_drafts_without_a_carried_prior_untouched

## Gates

- ruff: All checks passed!
- pytest: 2020 passed, 1 skipped, 2 xfailed
- selftest: selftest passed
- prompts --check: PROMPTS.lock up to date

## Mutation

Grouping by the draft's own ID instead of the prior ID made both new tests fail; refine.py was restored from a cp backup and cmp showed it identical.

## Not verified

No live model run reached the fallback branch with duplicate carriers; the behaviour is shown with the fake gateway only.
The final report's delta table after verify was not inspected end to end.

## Verified (fresh-context verifier, 5 Oct 2026)

Verified with no fix: probes (three carriers, distinct priors, rank tie, delta table after merge) held, all gates matched, and the most-fixed-keeper mutation failed the first test.
