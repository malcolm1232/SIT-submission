# Latency redesign W2: orchestration, phases and prompts

Date: 2026-10-03 (clock read 2026-10-02 23:13 UTC).
Branch `s4/w2-latency` from `7be556d`; commits `047a8cb`, `6b491a7`, `b1b03be`, `4031fca` and the docs commit; not pushed.
Edit log: `research/audit/latency_w2_editlog.md`.

## Status by deliverable

1. Stage 1 concurrent: done.
   Understand, plan and the assess shards start together as asyncio tasks; research starts when understand and plan have both ended (`stage1_ready`, `STAGE_1_DEPENDS`); the stage ends when every member has ended, or at `stage_1_end` (the runtime cuts the calls; members still running `stage1_grace_s` = 30 s later are stopped and disclosed).
2. Assess shards: done.
   `shards_for(run criteria)`, conversation `assess-0-s<k>` in launch order, brief with the document, the criterion group and a scope paragraph only; findings asked in rank order; a cut shard keeps the findings `LLMDeadlineError.partial` holds (validated item by item); one failed shard leaves a partial review.
3. Merge then refine as revisions: done.
   Refine calls `revision_problems(..., drafts=)` (as `check`, one repair call, then a disclosed fallback) and `apply_revisions`; BEH-10 reverts an unexplained severity or disposition change; the fallback keeps the merged findings in severity and confidence order.
4. Verify and verdict: done.
   The repair call runs only with more than 60 s of slack before the verify and verdict reserve; the verdict call returns `VerdictOutput`; a cut, failed or declined call gives the rule-based verdict; unresolved items and limitations come from code only.
5. Prompts: done (assess, plan, refine, report, README table, lock regenerated with the repo command).
6. Checkpoints and resume: done.
   Every stage 1 member checkpoints when it ends (ordinal); `budget.elapsed_s` is set at every checkpoint; finished shards are stored in `shards/<k>-<name>.json` with the pinned hashes; resume re-runs only unfinished members and shards and restores the clock with `elapsed_for_resume()`.
7. Deprecated names: partly done.
   `RefineOutput`, `RevisionNote`, `ReportOutput`, `UnresolvedDraft` and `LimitationDraft` are removed and `PHASE_OUTPUT_TYPES` is switched (`6b491a7`).
   `TRANSITIONS` and `ON_CAP` stay: their last reader is `tests/robustness/test_robustness_scenarios.py` (W3); product code no longer reads them (the orchestrator and `mermaid()` use the stage table).
8. Preserved behaviours: done, per shard and per stage (two truncations, the three `not_assessed` reasons, declined assess, deadline disclosures).
9. Model calls: two Haiku calls, about $0.10 (below).

## Concurrency primitive

asyncio tasks on the run's event loop.
The gateways already run `claude -p` as an asyncio subprocess (`llm/claude_code.subprocess_runner`, killed on cancellation) and the MCP client is async, so a task per member overlaps all waiting with no thread.
The fault-injection wrapper counts a stage's logical calls in arrival order; tasks start in creation order and each shard reaches its first gateway call before the next shard runs, so `nth` numbers the shards in launch order.
A `KeyboardInterrupt` inside a task would escape the event loop past every handler, so member and shard coroutines are wrapped (`guarded`) and the orchestrator re-raises it as `RunInterrupted` (exit 130).

## How IDs stay deterministic

Members run on isolated copies of the run state (`phases/_isolation.py`); shards only return their answer.
When stage 1 closes, `AssessPhase.merge` walks the shards in launch order: each shard's findings in its own rank order get the next `FND-` numbers, and its new `doc` and `inference` evidence is written to the ledger then, after research has stopped writing.
Shards see no evidence register (`resolve_evidence(shown=())`), so an `EV-` ID a shard writes never resolves to a research entry.
`test_finding_and_ledger_ids_do_not_depend_on_completion_order` runs all 120 completion orders of understand, plan and three shards (research writing the ledger meanwhile) and gets the same finding IDs, ranks and ledger IDs every time.

## Decisions taken here

- Shards always run at research iteration 0 (conversation `assess-0-s<k>`, provenance iteration 0), also when resume re-runs one after research ended.
- `not_assessed` only when no shard produced an assessment (a complete answer, or at least one finished finding); the stage-level disclosure then names the reason by priority deadline, truncated, declined, as `report.assessment_missing` reads it.
- A shard that fails with a model error (rate limit, overload, timeout, a second schema error) is a disclosed partial review; when every shard fails that way, the first error is raised (exit 3, resumable), as one assess call did; a failed shard is never stored, so resume re-runs it; defects (bad request, exhausted fake script, strict-replay miss) still propagate.
- The merged findings are listed in rank order with ranks by severity, then confidence, then shard order; this is the order kept when refine does not run or falls back.
- Stage limits act as caps only when the `deadline` rule is active; research's deadline rule is bounded by `stage_1_end`.
- Code writes no unresolved item for an open question not tied to a finding (unanswered research questions stay in `research_log.unanswered_questions`) and no prose limitation grouping several degradations: one limitation per degradation.
- A plan not approved while shards run: research does not start, the shards finish and are stored, and the run stops after the plan; resume merges them.
- A member stopped by the backstop is recorded as completed with its code fallback; a member that never started (only research can) is disclosed and not recorded as completed.

## Tests

New in owned files: stage 1 members ending in all 8 legal orders; state isolation of checkpoints; the backstop; plan-only; stage limits as caps; shard briefs (scope, group only, no intent, registry, answers or register); one failed shard of each kind; a cut shard keeping its salvaged findings; the three not-assessed reasons across shards; one assessed shard is enough; all shards failing raises; determinism over 120 orders; refine keep, merge and withdraw with history; BEH-10; invalid revisions repaired once then the fallback; a repaired answer applied; refine cut; resume after two of four shards runs exactly the other two (and reproduces the reference report); the clock restored from `elapsed_s`; verdict only with code-written unresolved items and limitations; a cut verdict call; the 60 s repair slack.

## Mutation results

Each guard was removed in the committed code, the named test run, and the file restored from a `cp` backup (worktree clean afterwards).

| # | Guard removed | Result |
|---|---|---|
| M1 | merge in shard order (merge in completion order instead) | determinism test fails |
| M2 | state isolation of members | isolation test fails |
| M3 | research waits for understand and plan | order tests fail |
| M4 | resume keeps finished shards | two-of-four resume test fails |
| M5 | clock from `elapsed_s` (sum of phase seconds instead) | clock test fails |
| M6 | refine's revision check | invalid-revision tests fail |
| M7 | BEH-10 revert | BEH-10 test fails |
| M8 | `not_assessed` only when no shard assessed | partial-review test fails |
| M9 | salvage of a cut stream | cut-shard test fails |
| M10 | 60 s slack rule | slack test fails |
| M11 | stage 1 backstop | backstop test hangs (killed at 60 s) |
| M12 | no intent in a shard brief | brief test fails |
| M13 | `LLMDeadlineError` in report's fallback tuple | survives: the exit-code rule already falls back for it; the entry is explicit, not load-bearing |

## Haiku schema check

Two calls on Haiku 4.5 (`low`) through `ClaudeCodeGateway`, `env -u ANTHROPIC_API_KEY`, a guard that never sends a second call per phase.
`RefineRevisionsOutput` was filled (keep, merge, keep) but broke one rule: a keep moved a finding to `needs_investigation`, which needs a `next_step` the revision cannot add.
The refine prompt now says which dispositions need fields a revision cannot add and to keep the drafted disposition then; not re-checked live.
`VerdictOutput` was filled.
Spend about $0.10 (the CLI logged no cost; estimate from the logged tokens at list prices).
For W0's owner: the schema itself can be filled; its known gap (no `next_step`, recommendation or `no_change_rationale` in a revision, `latency_w0_handoff.md`) was hit on the first try, so expect repair calls or fallbacks in the rehearsal until either a revision may carry `next_step` or the rehearsal shows the prompt fix is enough.
Also for W0's owner: the `FindingRevisionDraft` docstring, sent to the model as the schema description, contains code references (":func:`revision_problems` lists what breaks these rules; :func:`apply_revisions` applies a set ...").

## Gates at `4031fca`

- `ruff check agent harness tests`: exit 0.
- `pytest -q` from the repo root (`make test`, exit 2): 1273 passed, 53 failed, 58 errors, 0 skipped (1231 passed at `7be556d`).
  Every failure and error is in a file outside W2's list, and each was checked to fail for one of the causes below.
- `sit-review selftest`: exit 4, `FakeScriptExhausted` (the fixture scripts one assess answer for four shards); expected until W3 regenerates the fixture.
- `make smoke`: exit 2 at the selftest step; its test list then gives 145 passed, 13 failed, 5 errors, all in `test_selftest_cli.py`, `test_cli_kruns.py` and `test_cli_coverage.py` (the fixture).
- `make test`: exit 2 (the pytest result above).

Failing tests by cause:

- The selftest fixture (22 cases checked: every one ends in `FakeScriptExhausted`): `tests/robustness/test_robustness_scenarios.py` (49 errors), `tests/robustness/test_robustness_regressions.py` (10 failed, 4 errors), `tests/robustness/test_robustness_schedules.py` (2), `tests/test_selftest_cli.py` (7), `tests/test_cli_replay.py` (9), `tests/test_cli_kruns.py` (6), `tests/test_cli_coverage.py` (5 errors), `tests/test_adversarial_invariants.py` (8), `tests/test_budget_counts_failed_calls.py` (2), `tests/test_unrecorded_usage.py` (3), `tests/test_truncation_fallback.py` (1), `tests/test_integration_seams.py::test_1a_1f_injected_faults_through_the_pipeline`, `tests/test_runtime_policies.py::test_cli_faults_apply_process_entries[OPS-04-130]`.
- The verdict-only output: `tests/test_ingest_verify_report.py::test_report_writes_valid_review_and_passes_invariants` and `::test_verdict_inconsistent_with_severities_is_disclosed` script the old answer with `unresolved` and `limitations`, which `VerdictOutput` refuses.
- The concurrent order: `tests/test_runtime_policies.py::test_deadline_before_assess_is_disclosed_as_out_of_time` expects assess to wait for research.

## Not verified

- Anything live beyond the two Haiku calls: no Opus call, no run on a document, no timing; stage timings, cuts at the real limits and the 443 s prediction wait for the timed rehearsal.
- W1's salvage path end to end: the shards read `LLMDeadlineError.partial` as `{"findings": [...]}` (plus optional `sound_areas`, `coverage`), tested only with a scripted error.
- That the refine prompt fix stops the `next_step` violation (no third model call was made).
- That the fixture-dependent tests pass once W3 regenerates the fixture.
- Replay of a concurrent run (W3), the Mermaid output in a renderer, and a real Ctrl-C (the tests raise `KeyboardInterrupt` inside a member).

## Writes beyond my list

- `research/audit/latency_w2_editlog.md` and this report (asked for by the brief; `docs/` is otherwise W3's).
- `agent/sit_review_agent/states.py`: besides the deletions the brief allows, `mermaid()` was rewritten from the stage table and the deprecation comment of `TRANSITIONS` and `ON_CAP` updated (both needed so no product code reads the deprecated table).
- `agent/sit_review_agent/phases/_isolation.py` is new (inside `phases/`).
- Nothing in W1's or W3's files was edited.

## For the other workstream

W3 (selftest fixture, robustness, replay, manifest, README):

1. `selftest.fixture_script`: answer `assess` once per shard in `shards_for(criteria_ids)` order (four with the shipped config), each with findings, sound areas and coverage rows for its own group only, citing `NEW-` doc and inference items only (a shard sees no register, so an `EV-` ID a shard writes is dropped as invented); move the external evidence the fixture cites today to the refine answer.
   Refine answers `{"revisions": [...]}`, one per merged finding (merged IDs: shard order, then each shard's rank order), external evidence in a keep's `added_evidence`.
   Report answers `{"verdict": {...}}` only.
2. `tests/robustness/test_robustness_scenarios.py` line 51: import `STAGE_ORDER, STAGE_TRANSITIONS, STAGE_ON_CAP` instead of `ON_CAP, PHASE_ORDER, TRANSITIONS`; lines 877-878: `assert all(STAGE_ORDER.index(b) == STAGE_ORDER.index(a) + 1 for a, b in STAGE_TRANSITIONS.items() if b is not None)` and `assert all(STAGE_ORDER.index(b) > STAGE_ORDER.index(a) for a, b in STAGE_ON_CAP.items())`; the matching text in `tests/robustness/robustness_coverage.py` lines 227-228 and `tests/robustness/README.md` lines 166 and 238.
   Then `TRANSITIONS` and `ON_CAP` can be deleted from `states.py` (lines 28-43, the comment and both tables).
3. Robustness expectations: an assess fault now hits one shard (`nth` 0..K-1 are the shards' first calls in launch order; retries come later); LLM-05, LLM-06 and LLM-07 on one shard give a partial review with a per-shard disclosure, and `not_assessed` only when every shard failed; OPS-04 and BEH-25 on `assess` fire around all shards (finished shards are stored before the fault, so resume makes no assess call for them).
4. Replay and resume: shard calls are conversations `assess-0-s<k>`, purpose `assess`; finished shards live in `runs/<id>/shards/<k>-<name>.json` (`{"hashes", "result"}`); `phase_seconds` of stage 1 members overlap, `budget.elapsed_s` is the run clock at each checkpoint.
5. `manifest.py`: shard count `len(config.agent.assess.shards_for(criteria))`; salvage count is the sum of `result.salvaged` in `shards/`, or the per-shard degradations "assess shard k/K (name) was cut by the stage 1 limit ...; N finished finding(s) kept".
6. `agent/README.md`: module map (`phases/_isolation.py`; `orchestrator.py` stage loop, backstop `stage1_grace_s` and `stage1_poll_s`, `shards/`); prompts table; the interface notes: `PHASE_OUTPUT_TYPES` switched and the five output names removed, `TRANSITIONS` and `ON_CAP` pending item 2.

Not assigned to a workstream in the brief (integration pass):

7. `tests/test_ingest_verify_report.py` line 203: drop `"unresolved": [], "limitations": [...]` from `REPORT_OK`; line 541: drop `"unresolved": [], "limitations": []`.
8. `tests/test_adversarial_invariants.py` line 121: pass `report={"verdict": ...}` only (the INV-03 case now checks that code adds the unresolved item); the rest follows the fixture (item 1).

W1:

9. `tests/test_runtime_policies.py::test_deadline_before_assess_is_disclosed_as_out_of_time`: assess no longer waits for research; the equivalent case is a cap before stage 1 (advance the clock in `ingest` past the deadline rule: phases run are ingest, verify, report and the degradation starts "out of time before assessment"), and a research overrun now skips refine ("stop rule ... before refine").
10. The runtime must cut stage 1 calls at `stage_1_end`, refine at `refine_end` and the verdict call at `verdict_end` with `LLMDeadlineError`; for an assess shard put the finished items in `partial={"findings": [...]}`; the orchestrator's own stop at the stage 1 limit plus 30 s is only a backstop and salvages nothing.
