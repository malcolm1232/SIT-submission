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

# Edit log, part 2: the config keys of W0

Date: 2026-10-03 (Singapore time; clock read 2026-10-02 21:58 UTC).
Worker: a second fresh-context agent session (`claude-fable-5-1`), same branch and worktree, base `da3907c`.
Every document and config file was read with the Read tool, one file per call; no Bash call bundled a config file with anything else, and the refused call of part 1 was not resent.

Isolation: nothing under `eval/blind/` was opened or listed; `docs/transcripts/session3_coordinator.md` was not read; no `llm.jsonl` was opened.
No model call and no agent run was made.
`models.py`, `spec/`, prompts, the gateway, the orchestrator, replay and the manifest were not changed; the two renames in `llm/runtime.py` and `phases/research.py` are the attribute rename the brief asked for, nothing else.

## Edits

| # | File | What changed | Why |
|---|---|---|---|
| 1 | `agent/sit_review_agent/config.py` | `AssessShard`, `AssessSettings` (`shards`, `shards_for`, `grouped_criteria`), `AgentConfig.assess` (required); `StageLimits` and `StopRulesConfig.stage_limits_s` (required), `stage_limits_problem()`; `refine_reserve_seconds` replaces `assess_reserve_seconds`; `RENAMED_STOP_RULE_KEYS` and `_refuse_renamed_keys` (a before-validator on `StopRulesConfig` plus a per-file check in `load_config`); unknown shard criteria checked in `EffectiveConfig._cross_file`; the deadline fit checked in `load_config` before overrides. | Design section 5, first row; brief items 1 to 3. |
| 2 | `config/agent.yaml` | `claude_code.extra_args: ["--setting-sources", ""]` with its comment (unverified in a cloud session); new `assess.shards` block with the four groups. Lines 1-12 unchanged. | Brief items 1 and 4. |
| 3 | `config/stop_rules.yaml` | `assess_reserve_seconds` line becomes `refine_reserve_seconds: 600`; new `stage_limits_s: 2820 / 3420 / 3540` with the comment on why absolute seconds. Lines 1-8 unchanged. | Brief items 2 and 3. |
| 4 | `config/profiles/demo.yaml` | `refine_reserve_seconds: 200` (value as before); `stage_limits_s: 265 / 465 / 530`; note that the design's 75 s report reserve lands with W1. Lines 19-24 and 27 unchanged. | Brief items 2 and 3. |
| 5 | `agent/sit_review_agent/llm/runtime.py`, `phases/research.py` | Attribute rename only (`sr.refine_reserve_seconds`), docstrings and comments with it. | Brief item 2: every file that used the old key. |
| 6 | `tests/test_config.py` | 20 tests in the "latency redesign W0" block (shards, own shard, five shard errors, zero groups, rename, old key in base and profile, limits per profile, four limit errors and one range error, inheritance, CLI deadline below limits, hermetic argv). | Failing first (19 failures, one trivially green case sharpened to `greater than or equal to 1`), then green. |
| 7 | `tests/test_runtime_policies.py`, `test_research_phase.py`, `test_cli_kruns.py`, `test_config_layout.py` | Key rename; the 321 s test profiles get their own `stage_limits_s` (150 / 270 / 310), because inherited base limits above a lowered deadline are now refused. | Brief item 2; the new validation. |
| 8 | `tests/test_config_profiles.py` | Same 321 s profiles. | Same. |
| 9 | `tests/test_cli_replay.py` | The committed-run test passes `--pdf` as an absolute path (the cwd fix of brief item 6) and is re-targeted: the record is refused by name with exit 2 (see "Finding" below). | Brief item 6 and the consequence of item 2. |
| 10 | `agent/README.md`, `tests/robustness/README.md`, `config/profiles/README.md` | Interface-change note with every key and its readers; the key rename where the runtime policy is described; profile rules. | Freeze rule. |

## Finding: the committed measurement record no longer validates

`replay.recorded_config` validates `docs/live_runs/demo_profile_measure_1/effective_config.json` through `EffectiveConfig.model_validate`.
That record carries `assess_reserve_seconds` and lacks `assess.shards` and `stage_limits_s`, so under this commit it is refused ("not a valid effective config", the renamed key named, exit 2, no traceback), as replay already refuses a run whose prompts changed.
The three ways to keep it replaying were all outside this brief: a legacy translation in `replay.py` (item 7 forbids replay changes), editing the record (a measurement artefact), or a silent default or mapping in the model (item 2 forbids it).
The record replays at its own commit `2d84f59`; the design (section 6) already lists its replay as stale once W2 changes the prompts, and the demo backup is recorded with the final code (section 8).
The crash that test guarded is pinned by `test_a_recorded_usage_dict_never_reaches_the_error_constructor`.

## Design choices

- The deadline fit of the stage limits is a file-level rule in `load_config`, not a model invariant: pydantic 2.13 re-validates a `model_copy(update=...)` instance when it is passed to `EffectiveConfig`, so a model invariant would also refuse a legitimate `--deadline 300` override and any recorded dump of such a run. `--deadline` keeps today's contract (applied after validation, announced by the runtime).
- `stage_limits_s` lives in `stop_rules.yaml` beside the reserves it is derived from (base: 3600 - 180 - 600, 3600 - 180, 3600 - 60), so one file holds the whole clock.
- The old key is checked twice on purpose: the per-file check names the profile that holds it; the model check covers any other route (a recorded dump).
- The reserve values of the demo profile (120 s and 200 s) are unchanged: the design's 200 s and 75 s pair belongs with W1, which makes the limits the reader; changing it now would change the live demo behaviour of the current runtime.

## Gates

See the report section "Gates at the config commit" in `docs/transcripts/session4/latency_w0.md`.

## Mutations (`cp` backup, restore checked by md5 before and after)

| # | Guard removed | Result |
|---|---|---|
| M1 | empty group | caught |
| M2 | criterion twice in one group | caught |
| M3 | zero groups | caught |
| M4 | group name twice | caught |
| M5 | criterion in two groups | caught |
| M6 | unknown criterion | caught |
| M7 | ungrouped criterion forms its own shard | caught |
| M8 | group restricted to the run's criteria | caught |
| M9 | limits increasing | caught |
| M10 | limits below the deadline | caught |
| M11 | old key refused (model) | caught |
| M12 | old key refused (profile names its file) | caught |
| M13 | deadline fit checked at load | caught |
| M14 | hermetic `extra_args` in `agent.yaml` | caught |

`config.py` and `agent.yaml` had the same md5 before and after the run.
