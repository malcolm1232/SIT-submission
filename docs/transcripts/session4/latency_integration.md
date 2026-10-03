# Latency integration pass: report

The five workstream branches are merged into `s4/integration2` and nine of the ten seams are reconciled.
Seam h (robustness) is only partly done, and the suite is not green: 10 robustness tests fail.
No model call was made and nothing was pushed.

## Merges

All four merges went through with no conflict.
W1 `ded4394` merged as `fa03b61`, W3a `9e41553` as `5d66838`, W3b `502a256` as `a3a1c37`, W3c `26795e2` as `004ca0d`.
The final HEAD is `e9606d5` plus this report's commit.

## Seams

- a, done (`ceb7080`): the gateway logs `estimated_usage` and `partial` plus `salvaged_items`, and a test checks that replay rebuilds the same cut from the entry.
- b, done (`a3c5c35`): BEH-25 reads `STAGE_TRANSITIONS` and `STAGE_ON_CAP`, and the two deprecated names are deleted.
- c, done (`492e3e5`, `901546a`, `b372462`): W2 items 7, 8 and 9 are in, and the orchestrator now calls the four milestones, which it did not before.
- c, partly: the cut-call `partial` for a shard is written by the claude_code gateway only; the Anthropic API gateway and the fault injector's hang cut carry none.
- d, done (`52f8d0b`): W3c had already updated the runbook lines, so the three held-red tests now check the runbook's own wording and the 75 s reserve, and two "pending integration" notes are gone.
- e, done (`d135a6c`): `A4b-medium` became `A4b-high`, HB1 and EVAL_PLAN B-1 follow, entry 11 is extended, and `frozen: false` and the fill values are unchanged.
- f, done (`8962ab5`, `68d8555`, `31ee48d`): `next_step` was added, required and nullable like every other revision key, and is forbidden unless the new disposition needs it and the draft lacks one.
- f, decision: `recommendation` and `no_change_rationale` were not added (see "Decisions needed").
- f, docstrings: the LLM-facing descriptions are now plain prose, and a test guards them.
- g, done (`492e3e5`): the repo has no fixture regeneration command, because the fixture is the `selftest.fixture_script` generator, so the generator was rewritten.
- g, result: the fixture now gives one answer per shard, refine revisions and a verdict-only report, and `sit-review selftest` passes offline in 0.4 s.
- g, IDs: the fixture's finding IDs follow the merge order: FND-001 strength, FND-002 needs testing, FND-003 invented quote, FND-004 e-mail quota.
- g, test changes: the tests that pinned the old IDs were remapped, and the stand-in refine in `test_run_and_resume.py` now does the merge's ledger step.
- h, not done: `AWAITING_INTEGRATION` is still `True` and the results CSV is not regenerated.
- h, done so far: the harness splits assess patches per shard, the patches use merged IDs, and the refine patches act on revisions (`e9606d5`).
- h, failing tests: the ten awaiting or affected tests listed below still fail.
- i, done (`71b59c5`): a real concurrent fake run replays with the same report and a byte-equal `ledger.json` (new test).
- j, done (`972114b`): the manifest of a fixture run reads `assess_shards` 4 and salvage 0/0, and every stage 1 member has start and end offsets.

## Defects found and fixed

- Replay hid the shard protocol, because `replay._TimedPhase` did not forward `run_shards`, `merge` and `shards`.
  As a result the replay merged assess beside research and diverged at research's second call (exit 4).
  Fixed by forwarding the protocol.
- No writer logged `shard` or `start_offset_s`, so the manifest counted 0 shards and had no stage 1 spans.
  Fixed: `LLMCallLog` now adds both, and `attach_runtime` gives it the run clock.
- OPS-10: a sharded assess logged no "done" line, so 36 scenarios failed the oracle.
  Fixed in the orchestrator, with the oracle unchanged.
- The orchestrator never called W1's milestones.
  Fixed, with a test.

## Still failing (pytest: 10 failed, 1525 passed, 6 skipped)

- Awaiting rows that still assert the sequential design: LLM-01, LLM-03, LLM-06, LLM-07 and BEH-25.
- Rows not marked awaiting, failing on shard counts or calls made in stage 1:
  - LLM-02 expects attempts 0 to 3 once but sees them per shard.
  - LLM-10 and LLM-11 expect one refused call, and six are seen.
  - NET-02 times research at 112.7 s against its bound.
- The regression test `test_a_stage_that_truncates_twice_ends_in_a_disclosed_degraded_report[assess]` expects two calls, while four shards make eight.
  The per-shard truncation event also does not name its call IDs, which the single-call event did.
- Not started: LLM-13 to LLM-17, BEH-29, the oracle contract names in `concurrent_oracles.py`, and the LLM-03 persistent-overload ruling W3b asked for.

## Decisions needed

- LLM-03 persistent overload (all four shards fail): either the run-level exit 3 that the code gives today, or a not-assessed report.
  My recommendation is exit 3, as now, since every shard failing on a model error is an unavailable model.
- `recommendation` and `no_change_rationale` on a revision: I left them out.
  A move to `no_change` needs the recommendation removed, and a move away from it needs a whole recommendation, which is finding text that W0's interface keeps out of a revision.
  The prompt still tells the model to keep the drafted disposition in that case.

## Refused

One turn during the seam h work was ended by a safety stop.
Its content was not resent, and seam h was left incomplete instead.

## For the verifier

- Finish seam h:
  - Rewrite the awaiting rows and the four non-awaiting rows above for the shard expectations, without weakening an oracle.
  - Flip `AWAITING_INTEGRATION`.
  - Regenerate the CSV with `ROBUSTNESS_RESULTS_CSV=tests/robustness/results/robustness_results.csv pytest tests/robustness -q`.
  - Run the six new schedules.
- Run the mutation round on the replay guards that was deferred: the `_TimedPhase` forward was mutated once in this pass (the test failed, then passed when restored), but the rest of W3a's replay matching was not mutated.
- Re-check the `shard` and `start_offset_s` values on a live claude_code log, since only fake runs were checked here.
- Re-check that adding `start_offset_s` does not change how a recorded live run replays (`ReplayClock.at_recorded` now takes the exact path).
- Not verified: anything live, the timed rehearsal, the Anthropic API gateway's cut salvage, and `make test` green (it exits 2 on the same 10 failures).
