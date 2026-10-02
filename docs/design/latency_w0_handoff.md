# Latency redesign W0: hand-off to W1, W2 and W3

Date: 2026-10-03.
Source: the W0 interface change (`135bcf7`, `2cb6d4c`), its verifier commit, `agent/README.md` "Interface freeze" and `docs/design/latency_and_demo_design.md` sections 4, 5 and 7.
Every item below is open work for the named workstream; nothing here is done yet unless it says so.

## Deprecated names and who removes them

- W2 removes `llm.outputs.RefineOutput` and `RevisionNote` when `phases/refine.py` moves to `RefineRevisionsOutput`.
- W2 removes `llm.outputs.ReportOutput`, and `UnresolvedDraft` and `LimitationDraft` if nothing else uses them, when `phases/report.py` moves to `VerdictOutput`.
- W2 switches `PHASE_OUTPUT_TYPES` for refine and report, and updates the headers of `prompts/refine.md` and `prompts/report.md` and the table in `prompts/README.md`, then rewrites `PROMPTS.lock`.
- W2 removes `states.TRANSITIONS` and `states.ON_CAP` and rewrites `states.mermaid()` (read by the `cli.py` `states` command) from the stage table.
- W2 updates the two forward-only asserts in `tests/robustness/test_robustness_scenarios.py` and the text in `tests/robustness/robustness_coverage.py` and `tests/robustness/README.md`.

## W1: gateway, streaming and runtime

- `stop_rules.stage_limits_s` has no reader yet; W1's runtime is the first.
- A CLI `--deadline` below the profile's limits loads on purpose (the check is file-level), so W1 must clamp the limits to the deadline and announce it, as `deadline_warnings` does for the reserves.
- The demo reserves move to 200 s (refine) and 75 s (verify and verdict) with W1, in `config/profiles/demo.yaml`; today the profile still holds 120 s and 200 s, and `refine_reserve_seconds` is still applied to research only.
- W1 is the first writer of `LLMDeadlineError(partial=, estimated_usage=)`; `usage` must stay measured only.
- If W1 logs the estimate in `llm.jsonl`, it must not use the entry keys `partial` or `estimated_usage` unless W3 maps them in `replay.recorded_error`, which passes any entry key named like a constructor keyword straight to the error (a raw dict would reach `estimated_usage`).
- `manifest.journal_usage` and `harness/sit_eval/usage.py` sum `usage` only; a cut call must keep `usage: null` with `usage_unrecorded`, and its estimate is reported apart and marked estimated (`tests/test_interfaces_w0.py` pins that an `estimated_usage` key is ignored by both).
- `--setting-sources ""` is in every argv but unverified in a cloud session and with `--resume --fork-session`; check once there.
- The harness judges (`harness/sit_eval/live_judges.py`) build their own argv from `config/eval.yaml` and do not get the hermetic pair.

## W2: orchestration, phases and prompts

- `phases/refine.py` calls `revision_problems(out, ids, drafts=by_id)` and then `apply_revisions(drafts, out)`; that pair is the one exact meaning of a revision set.
- Settled meanings: `keep` states final values (a null severity is final, legal only for a strength); `merge` must target a kept finding, moves the merged finding's `criterion_ids` to the target and nothing else; `withdraw` drops.
- Refused by validation: a merge into a withdrawn, merged, unknown or own finding (chains and cycles included), a missing or doubled revision, ranks that are not 1..n, evidence added twice or already cited, and a kept finding that breaks the spec's finding rules after the patch.
- Left to verify, as today: a link to an unknown registry entry is dropped and recorded; evidence not in the ledger is dropped at hydration.
- Not expressible in a revision: a disposition change that needs a new recommendation, `no_change_rationale` or next step is refused, so refine cannot move a finding across the `no_change` boundary; if the rehearsal shows refine needs that, the options are adding those three fields to the revision or a second pass, and the recommendation is to measure first.
- Class docstrings of the output drafts are sent to the model as schema descriptions; check that `FindingRevisionDraft`'s text reads well as an instruction before writing `prompts/refine.md`.
- `VerdictOutput` holds the verdict only: `settle_report_output` must stop reading `unresolved` and `limitations`, and the code paths that already exist in `assemble_review` (an unresolved item per non-refinement finding, a limitation per degradation) become the only source.
- What the model wrote before and code does not yet write: unresolved items not tied to a finding (open questions, unanswered research questions) and prose limitations that group several degradations; decide whether code writes them or they are dropped.
- The orchestrator sets `Budget.elapsed_s` at every checkpoint and `resume_run` restores the clock with `elapsed_for_resume()` instead of summing `phase_seconds`.
- Stage 1 members end in any order; each writes its checkpoint, but the journal offsets in a member's checkpoint do not cover a member still running, so resume must not truncate `ledger.jsonl` to an earlier member's offset.
- `MemberOutcome` is per member; shard-level outcomes (one failed shard, resume re-runs only unfinished shards) need run-state fields W2 defines.
- A disabled research or refine phase (`OPTIONAL_PHASES`) is not in the stage helpers: `stage1_ready` still offers research, so the orchestrator treats a disabled member as ended.
- `STAGE_ON_CAP[STAGE_1]` jumps to verify when a cap fires before stage 1 starts, so understand is skipped too (the old table always ran understand); confirm the report's not-assessed path covers a run with no intent.
- `AssessSettings.shards_for(run_criteria)` names a shard of an ungrouped criterion after the criterion, so a criterion id equal to a group name gives two shards of one name; identify shards by launch index, as the design numbers them.

## W3: replay, manifest, robustness and docs

- `replay._final_state` still takes the last checkpoint by file name; use `state.checkpoint.checkpoint_file_order` (a one-line change, as in `report/coverage.py`).
- `replay.recorded_error`: map or exclude the entry keys `partial` and `estimated_usage` (see W1).
- `manifest.py` reads the new `LLMDeadlineError` fields: cut calls counted with `estimated: true`, shard count from `len(shards_for(...))`, salvage count in `extra`.
- `manifest.py` `timing.per_stage_s` overlaps in stage 1 and no longer sums to `wall_clock_s`; `harness/sit_eval/metrics.py` reads it downstream.
- `replay.py` reads `phase_seconds` for its clock; with overlapping members it must follow recorded start offsets (design section 5).
- A record made before W0 is refused by name with the commit it replays at (decision #30); the demo backup is recorded with the final code.

## Not verified by W0

- Anything live: no model call and no agent run.
- That the model can fill the revision schema, the verdict call at `medium`, and the stage limits in action.
