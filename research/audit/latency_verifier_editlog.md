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
