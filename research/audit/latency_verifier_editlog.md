# Edit log: latency redesign verifier

Date: 2026-10-03 (clock read 2026-10-03 00:57 UTC).
Worker: a fresh-context verifier session on `claude-opus-5-5`.
Scope: branch `s4/integration2`, base `f616e73`, worktree `/Users/malco/Desktop/SIT-wt/int`.
Authority: the verifier brief, `docs/design/latency_and_demo_design.md` section 4 and the verifier list of section 7.

Isolation: nothing under `eval/blind/` was opened or listed; no `llm.jsonl`, recorded model call, stream fixture or model output was printed; only metadata fields were read by script.
No model call was made.

## Refused call

The first call of the session (`git fetch origin` with the head check) was ended by a safety stop; its content was not resent.
The fetch itself had already failed on the credential helper (`git: 'credential-manager' is not a git command`), so the remote-tracking ref `origin/claude/happy-darwin-d0bl94` (7be556d) is as last fetched, not freshly confirmed.

## Edits

- B (shard cut disclosure): a shard cut at the stage 1 limit named its shard but not the cut call.
  `PhaseCall.cut_id` now carries the cut attempt's call ID (`LLMDeadlineError.call_id`), and the shard's degradation event ends with `(cut call <id>)`, or `(cut call none started)` when no attempt had started.
  Files: `agent/sit_review_agent/phases/_model_calls.py`, `agent/sit_review_agent/phases/assess.py`.
  Test: `tests/test_llm_phases.py::test_a_cut_shard_keeps_its_finished_findings` now asserts the shard label and the call ID in the event.
- C (determinism): the 120-order test passed (120 of 120).
  Mutating the shard results to completion order, in the orchestrator's merge call and in `AssessPhase.merge`, failed 100 of the 120 orders; restored from a `cp` backup.
  Mutating only the sort inside `AssessPhase.merge` survived, because the orchestrator already passes the results in plan order.
  Test added: `tests/test_llm_phases.py::test_merge_orders_the_shards_itself` merges the same shard results forward and reversed and asserts equal finding and ledger IDs; it fails under that mutation.
- D (revisions): six adversarial revision sets of the verifier's own (a move to `governance_decision` without a next step; a next step on `refinement_now`; a merge into a withdrawn finding; a duplicate rank; a revision for an unknown finding; a move to `no_change` for a finding with a recommendation) are each refused with a message naming the problem, and `apply_revisions` raises on each; a valid keep, merge and next-step set applies exactly.
  Tests added: `tests/test_refine_next_step.py::test_verifier_adversarial_revisions_are_refused` and `::test_verifier_valid_set_applies_exactly`.
  `agent/README.md`: a "Known limitation" line on the `no_change` boundary (judgement call 3), which the paragraph described but did not label.
- E (resume): `test_resume_after_two_of_four_shards_runs_exactly_the_other_two` passed; it failed when the shard skip in `AssessPhase.run_shards` (`if i in done: continue`) was removed, and again when the orchestrator handed `run_shards` an empty `done`; both restored from `cp` backups.
- F (replay): the deferred mutation round on `replay.py`, one claim at a time, each restored from a `cp` backup, against the replay, kruns, resume, selftest and seam tests.
  Killed: the conversation filter dropped (`test_a_changed_request_in_a_recorded_conversation_still_diverges`), the request hash not compared (`test_replay_divergence_is_reported_not_invented`), the start offsets ignored (`test_replay_clock_follows_recorded_start_offsets_inside_stage_1`), the checkpoint order by file name (`test_final_state_takes_the_latest_checkpoint_by_ordinal`), the recorded conversation not renamed (`test_replay_reproduces_the_recorded_report_offline`).
  Survived: a hash match with another phase or purpose served silently instead of raising `ReplayDivergence`.
  Test added: `tests/test_cli_replay.py::test_a_hash_match_with_another_purpose_diverges`; it fails under that mutation.
  The `_TimedPhase` forward was mutated by the integration pass and was not mutated again.
