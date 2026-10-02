# Edit log: latency redesign W0, the interface change

Date: 2026-10-03 (Singapore time; clock read 2026-10-02 21:39 UTC).
Worker: a fresh-context agent session on `claude-opus-5-5`.
Scope: branch `s4/w0-interfaces`, base `e28b082`, worktree `/Users/malco/Desktop/SIT-wt/w0`.
Authority: `docs/design/latency_and_demo_design.md` sections 4, 5 and 7, and the planner's rulings in the W0 brief.

Isolation: nothing under `eval/blind/` was opened or listed; `docs/transcripts/session3_coordinator.md` was not read; no `llm.jsonl` was opened.
No model call and no agent run was made.
`models.py`, `spec/`, prompts, the gateway, the orchestrator, replay and the manifest were not changed.

## Refused call and the scope it removed

One Bash call that printed `config/agent.yaml`, `config/stop_rules.yaml`, `config/profiles/demo.yaml` and the baseline test log was refused by the permission classifier.
It was not resent and those files were not read by any other route.
So the config part of W0 (brief item 3) was not done: `assess.shards`, `refine_reserve_seconds` with its migration error, the stage limits, the `claude_code.extra_args` value, and their profile and layout tests.
Doing it needs the three config files read, and the owner or planner to allow that read.

## Edits (commit `135bcf7`, the interface change alone)

| # | File | What changed | Why |
|---|---|---|---|
| 1 | `agent/sit_review_agent/llm/outputs.py` | New `RevisionAction`, `FindingRevisionDraft`, `RefineRevisionsOutput`, `revision_problems`, `VerdictOutput`; `RefineOutput`, `RevisionNote` and `ReportOutput` marked deprecated (W2 removes). | Refine returns one revision per finding; the verdict call returns the verdict only (design section 4, levers 3 and 9). |
| 2 | `agent/sit_review_agent/errors.py` | `LLMDeadlineError` keywords `partial` and `estimated_usage`, property `salvaged_items`. | A cut call keeps its finished items; its estimated usage stays apart from measured `usage` (accounting fixes). |
| 3 | `agent/sit_review_agent/states.py` | `Stage`, `STAGE_ORDER`, `STAGE_MEMBERS`, `STAGE_TRANSITIONS`, `STAGE_ON_CAP`, `STAGE_1_DEPENDS`, `MemberOutcome`, `stage_of`, `stage1_ready`, `stage1_close`; `TRANSITIONS` and `ON_CAP` marked deprecated (W2 removes). | Stage 1 runs understand, plan, research and assess concurrently; research waits for understand and plan. |
| 4 | `agent/sit_review_agent/state/checkpoint.py` | `Checkpoint.ordinal`, assigned by `write_checkpoint`; `latest_checkpoint` by highest ordinal; a legacy file reads its ordinal as `seq`. | Stage 1 members end in any order, so the file name no longer says which is latest. |
| 5 | `agent/sit_review_agent/state/run_state.py` | `Budget.elapsed_s` and `Budget.elapsed_for_resume()`. | Overlapping phase times no longer sum to the run clock. |
| 6 | `agent/README.md` | Interface-change note with every writer and reader. | Freeze rule. |
| 7 | `tests/test_interfaces_w0.py` (new) | 34 tests. | Failing first (import error), then green. |

## Design choices

- Revisions state final values, not deltas, so a null severity on `keep` is the final value and never means "unchanged".
- Every revision key is required, so the LLM-facing schema has no optional keys to misread.
- Rule checks live in `revision_problems`, not in a Pydantic validator, so a bad revision does not fail the whole parse; the refine phase (W2) decides what to drop and disclose.
- A merge must target a kept finding; this one rule rejects a merge into a withdrawn finding, chains and cycles.
- `estimated_usage` is a separate attribute from `usage`, so `llm.usage_budget.add_usage` and every reader of `usage` keep reading measured usage only.
- `write_checkpoint` assigns the ordinal itself, so `orchestrator.py` needs no change to stay correct.

## Gates at `135bcf7`

| Gate | Exit | Result |
|---|---|---|
| `make -C <worktree> test` (ruff, then `pytest -q`) | 0 | ruff clean; 1127 passed (1093 before plus 34), 0 skipped |
| `make -C <worktree> smoke` | 0 | selftest ok; 198 passed |
| `sit-review selftest` | 0 | passed |

A first full `pytest` run started from `/Users/malco` failed one test (`test_the_committed_demo_measurement_run_replays_offline`, "input not found").
The test resolves the recorded PDF path from the working directory; from the repo root (`make -C`) it passes.

## Mutations (commit first, `cp` backup, restore checked by `cmp`)

| # | Guard removed | Result |
|---|---|---|
| M1 | merge into itself | caught |
| M2 | merge into a finding that is not kept (cycle) | caught (2 tests) |
| M3 | revision for an unknown finding | caught |
| M4 | withdraw or merge setting rank, severity or disposition | caught |
| M5 | finding without a revision | caught |
| M6 | kept ranks form 1..n | caught |
| M7 | research waits for understand and plan | caught (3 tests) |
| M8 | a running member is cut, not skipped | caught |
| M9 | latest checkpoint by ordinal (mutated to `seq`) | caught (2 tests) |
| M10 | legacy ordinal reads `seq` | caught |
| M11 | next ordinal on write | caught (2 tests) |
| M12 | `elapsed_s` non-negative | caught |
| M13 | `elapsed_s` used before the phase sum | caught |
| M14 | estimate kept apart from measured usage | caught |

`git status` was clean after the run.
