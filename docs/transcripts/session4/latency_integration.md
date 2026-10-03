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

## Seam h finished (second worker, 2026-10-03 08:50)

Branch `s4/integration2`, dcd31a2 to ae08a08 (sixteen commits, all `malcolm1232`, no attribution lines), tree clean, not pushed.
Gates: `ruff check agent harness tests` 0; `pytest -q` from the repo root 0 (1547 passed) and from `/Users/malco` 0 (1547 passed); `sit-review selftest` 0; `make smoke` 0 (238 passed); `make test` 0 (1547 passed); the robustness runner 0 (159 passed); `convert_answer_keys.py --tier synthetic --check --verify-anchors` 0; the prompt lock test 0; `leakage_grep.py` 0.
No em dash on any added line.

### Row by row

- Regression `test_a_stage_that_truncates_twice...[assess]`: defect in the agent. The per-shard truncation note did not name its call IDs. `PhaseCall.truncated_ids` and the shard note now does; the test asserts 4 x 2 calls, one note per shard naming its IDs, one stage-level note. PASS.
- LLM-01: restated. The 429 hits attempt 0 of each of the four shards' calls; each waits >= 15 s; findings as in the control. PASS.
- LLM-02: restated. Each of the six stage 1 calls (understand, plan, four shards) makes max_retries + 1 attempts and no more; exit 3 once; checkpoint. PASS.
- LLM-03: restated per the ruling. Recovering: 529 on attempts 0-3 of every shard, every shard completes, no model switch. Persistent: `AssessShardsFailed` (exit 3, resumable), `report.partial.md` written and disclosed (each shard and its error), `failure.json` names it and the shards, resume completes. PASS.
- LLM-06: restated, and a defect in the report renderer: with every shard declined `report.md` showed a bare "not assessed" because the renderer keyed on the sequential event text. Shared constant now. Per shard: 2 refusals, no third call, each shard's refusal disclosed by name, every criterion not assessed; once: shard 1 recovers on its reframed retry, the other shards untouched. PASS.
- LLM-07: restated. nth 0 is shard 1's call (one retry, the others untouched); persistent: every shard truncated twice with no third call, each note naming the shard and its two IDs, verdict not_assessed. PASS.
- LLM-10: restated. Six unsent over-limit refusals (one per concurrent first call), nothing sent, exit 2. PASS.
- LLM-11: restated. Six auth refusals, one per call, none retried, exit 3 within 10 s. PASS.
- NET-02: defect per the ruling. The window applied to the first call started only; the other five retried on the full budget until cancelled, and under the serial `FakeClock` their sleeps summed to 112 s. `FirstCallNetwork` now windows every call started before the API has answered one (a result or an HTTP error status), in all three gateways; the first to give up exits 3 once and the rest are cancelled (asserted: one error line, no call at its budget, nothing started after the exit). NET-02 and its drill run on the scheduling clock. PASS, 4.8 s virtual.
- BEH-25: restated. Understand, plan and assess start together; the crash at assess's start is handled once understand and plan have ended and before research starts: exit 4, plan checkpoint, completed phases ingest to plan, no research call, partial report, resume completes; `stage1_ready` checks. PASS.
- LLM-13 (new): PASS once the end-to-end runs use the scheduling clock. On the serial clock shard 3's hang moved virtual time past the stage limit before shard 4 started, so shard 4 was cut without a fault (a harness artefact, the one INF-01 already avoids).
- LLM-14, LLM-15 (new): defect. The scripted backend answers without suspending, so shard 1's retry reached the fault wrapper before shard 2's first call and `nth` 4 hit shard 4. `call_model` yields once before every logical call; the first calls are now `nth` 0..K-1 in launch order. PASS.
- LLM-16, LLM-17 (new): PASS as built.
- BEH-29 (new): defect. A `process:` fault with `shard` wrapped the whole member (exit 4). It now wraps that shard's `run_shard`, and a shard's unexpected exception ends that shard only (outcome error, disclosed by name and class, criteria not assessed); every shard crashing is a `StageCrash`. Unit tests in `tests/test_orchestrator.py`. PASS.
- LLM-05: it passed on the serial clock for the wrong reason (the hang cut all four shards, so the old "no finding, not_assessed" check held). Restated to the stated expectation on the scheduling clock: shard 1 cut at 265 s and disclosed, criteria not assessed, three shards' findings kept, verdict assessed; default deadline: full timeout, then retry. PASS.
- LLM-08, NET-01, OPS-04: strengthened to the shard form. BEH-10 already asserted the revision form. PASS.
- Oracle contract: `NOT_ASSESSED` confirmed against the orchestrator: the schema allows `findings`, `no_issue`, `not_applicable` only, so a not-assessed criterion is `not_applicable` with a note starting "not assessed"; `concurrent_oracles.is_not_assessed` is the predicate, the fixtures write that form, and a direct test guards it against a model-reported not-applicable criterion.

### Results CSV against 7be556d

87 rows (81 + 6). Six new rows LLM-13 to LLM-17 and BEH-29: PASS. No status change among the 81 (49 PASS, 32 BLOCKED, the laptop and static rows). Key metrics restated on LLM-01, LLM-02, LLM-05, LLM-06, LLM-08, LLM-11, NET-02, OPS-04 (listed in the edit log). No regression.

### Decisions needed

- None blocking. The one left from the first pass (`recommendation` and `no_change_rationale` on a revision) stands as it was.

### Refused

One turn (the README table edit of step 3) was ended by a safety stop; its content was not resent. The same edit was redone in smaller steps.

### For the verifier

- Cold-read `phases/assess.py` (`_shard`, `_crashed`, the all-failed branch) against the BEH-29 row: a shard's unexpected exception is contained; `LLMError`s that mean a defect (bad request, exhausted fake script, strict-replay miss), cancellation and `MemberInterrupted` still propagate.
- The `await asyncio.sleep(0)` at the top of `call_model`'s loop is a scheduling guarantee for the `nth` contract; confirm it is acceptable in production (it is a no-op in cost).
- `FirstCallNetwork.answered` is set in each gateway on a result and on an HTTP error status; confirm on a live `claude_code` run that an API error answer is classified as not a connection error (its classifier is text-based).
- Re-check the `shard` and `start_offset_s` values on a live `claude_code` log; the cut salvage of the Anthropic gateway; the timed rehearsal; W3a's replay matching mutation round (still deferred).
- `make test` is green now (it exited 2 on the ten failures before).
