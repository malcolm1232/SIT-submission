# Edit log: re-assessment delta fixes (rehearsal defects 1 to 4)

Date: 2026-10-03 (Singapore time; clock read 2026-10-03 17:15 +08).
Worker: a fresh-context agent session on `claude-opus-5-5`.
Scope: branch `s4/deltafix`, base `9958706`, worktree `/Users/malco/Desktop/SIT-wt/deltafix`.
Authority: the planner's brief, `docs/transcripts/session4/reassessment_rehearsal.md` section "Defects", and `docs/design/ui_design.md` section 7.

Isolation: nothing under `eval/blind/` was opened or listed; nothing under `docs/design/` was read except `ui_design.md` section 7 (the delta view; section 6 is the chat and was not needed); nothing under `docs/transcripts/` was read except the "Defects" section named above.
No `llm.jsonl`, `progress.jsonl` record, `ui/chat.jsonl` or recorded model output was printed.
No model call and no agent run beyond the fake gateway was made, and no call was refused.
Files the other two workers own (`llm/runtime.py`, `config/stop_rules.yaml`, the demo runbook and script, `README.md`, `docs/LIMITATIONS.md`, `docs/DOCUMENTATION_MAP.md`) were not touched.

## Commits

- `75b7ebe` Interface change, alone, under the freeze rule of `agent/README.md` (note added there): `PriorFindingStatus`, `PriorFindingEntry`, `Review.prior_findings`, `Reassessment.regression`, `PriorStatusDraft`, `RefineRevisionsOutput.prior_statuses`, `RunState.prior_statuses`, the matching schema `$defs`, taxonomy `prior_finding_statuses`, and the three tests whose expected dumps gained the new default keys.
- `1905eed` Defects 1 and 2 (they share the table): `delta.py` (new), refine asks once, report builds the table and the regression mark, INV-13, `finding_refs` skips the table, the report.md delta section keyed on the prior ID, the `answer_incomplete` progress event, console baselines, `tests/test_reassessment_delta.py`.
- `a2a2850` A docstring line over the lint limit, left by the previous commit.
- `037ab1d` Defects 3 and 4 (same tab code): `ui/rundata.delta_view`, the Delta tab rows and the disabled tab, `tests/test_ui_delta_tab.py`, two existing UI tests updated.
- The docs commit with this log, the report, `docs/ARCHITECTURE.md`, `spec/README.md`, `research/robustness/README.md` (INV-13 row) and the screenshot.

## Decisions

- Every new field is optional in the schema and defaults in the models, so committed runs, checkpoints and recordings still load and validate; INV-13 is skipped for a report that has no `prior_findings` key.
- `reassessment.prior_finding_id` already is the prior ID beside the finding's own ID, so no second `prior_id` field was added to the reassessment; the delta table's key is named `prior_id`.
- The question "which prior findings have no status" is asked of refine, the one global call that sees every merged finding, the prior findings and the document; an omission goes through `call_model`'s existing repair path (the new `ask=` argument), and an omission that survives the repair keeps the answer and is filled in code.
- `prompts/refine.md` was not changed: a prompt edit changes the prompt bundle hash and `replay_run` refuses a committed run recorded under the old bundle (`tests/test_ui_page.py` replays `rehearsal_concurrent_1`); the rule reaches the model through the field's schema description and the repair message, which names each missing prior ID.
- When several findings carry one prior finding forward (the committed run's prior FND-046), the least fixed status stands and the note names each carrier.
- `regression` is computed per section number: the anchor's matched section in the updated text differs from the same-numbered section of the prior text, or the prior text lacks it.
- The disabled Delta tab carries `aria-disabled="true"` and the reason as its title, and still opens to show the sentence, so the reason is readable and not only on hover.

## Mutation results (each guard removed, the tests run, the file restored from a `cp` backup)

- M1 duplicate prior status in `Review`: killed.
- M2 INV-13 missing-status problem: killed.
- M3 the ask in `call_model`: killed.
- M4 a missing status dropped instead of recorded: killed.
- M5 regression never marked: killed.
- M6 refine never asks: killed.
- M7 withdrawal without a reason: killed.
- M8 Delta tab hidden without a previous version: killed.
- M9 note column empty: killed.
- M10 prior ID column dropped: killed.
- M11 regression mark dropped: killed.
