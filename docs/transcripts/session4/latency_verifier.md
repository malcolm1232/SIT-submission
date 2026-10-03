# Latency redesign: verifier report

Date: 2026-10-03 (clock read 2026-10-03 00:57 UTC at the start).
Worker: a fresh-context verifier session on `claude-opus-5-5`, offline, no model call.
Branch `s4/integration2`, base `f616e73`, worktree `/Users/malco/Desktop/SIT-wt/int`.
Edit log: `research/audit/latency_verifier_editlog.md`.

## Verdict

Not ready to push, on one gate line only: commit `87a0634` (a W3a commit, "Latency W3: replay matches calls by conversation and request hash...") carries a `Co-Authored-By` line.
Removing it needs a rewrite of the unpushed history after `7be556d`; that rewrite was refused by the permission classifier and was not retried.
Every behaviour in A to L holds offline, and every other gate in K exits 0.
`git fetch origin` failed on the credential helper (`git: 'credential-manager' is not a git command`), so the remote tip was not freshly confirmed; the remote-tracking ref still reads `7be556d`.
Nothing was pushed.

## Decisions needed

- The co-author line on `87a0634`.
  Option 1: the owner rewrites the commit messages of `7be556d..s4/integration2` (for example `git filter-branch --msg-filter` that drops the `Co-Authored-By:` line), which leaves every tree identical and changes only the shas, then pushes as a fast-forward.
  Option 2: the owner accepts the one line and pushes as is.
  Recommendation: option 1, since the rule is the owner's and the branch is not yet on the remote.

## Results, section by section

- A, phase graph: PASS.
  An offline run of the selftest fixture on the scheduling clock with per-phase latencies from the design table, read by script (metadata fields only), showed the four shards and plan starting at 0 s with understand, research starting at max(understand end, plan end) in two latency settings (136 s and 150 s), shards numbered 1 to 4 in call-ID order, one refine call after research and every shard ended, one verdict call last and no call after it.
  The manifest has `extra.model.assess_shards` 4, `extra.timing.stages` with per-member spans and `wall_basis: member_spans`, and measured `usage` apart from `estimated_usage_totals` (marked estimated).
- B, cut behaviours: FIXED, then PASS.
  A shard cut named its shard but not the cut call; the disclosure now ends `(cut call <id>)` (`PhaseCall.cut_id`), tested in `tests/test_llm_phases.py::test_a_cut_shard_keeps_its_finished_findings`.
  Proofs re-run: shard cut keeps finished findings (that test, LLM-13); research cut with `stop_reason: deadline` (LLM-17, `test_deadline_ends_research_without_a_wrap_up_call`); refine cut falls back to severity then confidence order, disclosed (LLM-16, `test_refine_cut_keeps_the_merged_findings_in_severity_order`); verdict cut falls back to the rule-based verdict (`test_a_cut_verdict_call_falls_back_to_the_rule_based_verdict`); `not_assessed` only when no shard assessed (`test_not_assessed_only_when_no_shard_assessed`, `test_one_assessed_shard_is_enough_to_assess`); two truncations in a shard degrade with a disclosure (LLM-15, `test_a_stage_that_truncates_twice_ends_in_a_disclosed_degraded_report`); all four shards failing gives exit 3 with `report.partial.md` and a completed resume (LLM-03 persistent); a first-call connection error exits once with the others cancelled (NET-02, `test_anthropic_concurrent_first_calls_each_get_the_window_until_one_is_answered`).
  322 tests in that set passed.
- C, determinism: PASS, one test added.
  The 120-order test passed; completion-order merging failed 100 of 120; the sort inside `AssessPhase.merge` alone was an unguarded survivor and now has `test_merge_orders_the_shards_itself`.
- D, revisions: PASS, tests added.
  Six adversarial sets of my own are each refused with a message naming the problem, and a valid keep, merge and next-step set applies exactly; the schema guard test passed.
- E, resume: PASS.
  The two-of-four resume test failed under each of two mutations of the shard skip (in `run_shards` and in the orchestrator's hand-over) and passed when restored.
- F, replay: PASS, one test added.
  Byte-equal replay of a concurrent fake run passed; the older-config refusal names the record, the renamed key and the commit.
  Mutation round: five of six claims killed; the phase or purpose check on a hash match survived and now has `test_a_hash_match_with_another_purpose_diverges`.
- G, salvage and accounting: PASS.
  Stream, scanner, gateway, unrecorded-usage, accounting and harness usage tests passed (123); the fixture run scored with `--judge fake --exploratory` exited 0 and the harness read `calls_with_unrecorded_usage`.
- H, hermetic argv: PASS for the agent.
  The harness judge's `claude -p` argv is outside the redesign and carries no `--setting-sources ""`; recorded as an observation.
- I, config: FIXED, then PASS.
  Demo 265/465/530 and reserves 200/75, the hard error on `assess_reserve_seconds`, four shards covering every criterion once in both profiles, the runbook listing test green.
  The runtime's short-deadline warning called the refine reserve "for assess"; it now says refine, tested.
- J, judgement calls: PASS.
  (1) The `asyncio.sleep(0)` in `call_model` is documented at the call site and removing it fails LLM-14, LLM-15 and one unit test; kept.
  (2) The Anthropic cut raises `LLMDeadlineError` with no partial and the shard degrades honestly; new test `test_an_anthropic_cut_has_no_partial_and_the_shard_degrades_honestly`.
  (3) The validator refuses a move across `no_change`, the refine prompt says to keep the drafted disposition, and `agent/README.md` now labels it a known limitation.
- K, gates: FAIL on the co-author line only.
  `ruff check agent harness tests` 0; `pytest -q` from the repo root 0 (1557 passed) and from `/Users/malco` 0 (1557 passed); `sit-review selftest` 0; `make smoke` 0 (238 passed); `make test` 0 (1557 passed); the robustness runner 0 (159 passed) and its regenerated CSV equal to the committed one in every column but commit and duration; `convert_answer_keys.py --tier synthetic --check --verify-anchors` 0; prompt locks 0 (`sit-eval prompts`, `tests/test_prompts.py`); `leakage_grep.py` 0; `validate_examples.py` 0.
  No em dash on added lines since `7be556d`; every commit authored by `malcolm1232`; no secret in the diff (the stream fixtures' session IDs are the scrub placeholders, email-shaped hits are decorators, the user name appears only in worktree paths of the audit logs).
- L, records: FIXED, then PASS.
  USER_DECISIONS rows 27 to 31 once each in order, ADR-011 and ADR-012 Proposed with the ADR-002 amendment, prereg deviation 11 on the A4b rename; the module map lacked `phases/_isolation.py` and showed `llm/partial.py` as pending, both corrected.

## Refused

The first call of the session (fetch and head check) was ended by a safety stop and not resent.
The history rewrite that would drop the co-author line was refused by the permission classifier, and a follow-up read of the branch refs was refused with it; neither was retried.

## Not verified

- Anything live: the timed rehearsal, the hermetic token count, the `shard` and `start_offset_s` values on a live `claude_code` log, and the claude_code classifier of an API error answer.
- Degradation IDs are renumbered in the order stage 1 members merge (`phases/_isolation.py`), which follows completion order; only finding and ledger IDs were checked for determinism.
- The `_TimedPhase` forward in `replay.py` was mutated by the integration pass, not again here.

## For the rehearsal

The first timed live run (document-only, demo profile) must show:
- it ends inside 540 s with the refine call and the verdict call both run, not their fallbacks;
- its stage times within 20 % of the design table (understand 136 s, plan 102 s, assess shards about 205 s, refine about 175 s, verdict about 52 s, total about 443 s);
- a run with `--deadline 300` still yields a report with findings, not `not_assessed`;
- the first input-token count of a trivial call equals the hermetic figure (1,137 on Haiku), on the Mac and in a cloud session;
- two runs of the same recorded input give identical finding and ledger IDs, and `dra replay` reproduces the live concurrent run offline.
