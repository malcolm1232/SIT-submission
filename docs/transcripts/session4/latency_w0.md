# Latency redesign W0: the interface change

Date: 2026-10-03.
Branch `s4/w0-interfaces`, base `e28b082`; interface commit `135bcf7`, not pushed.
Edit log: `research/audit/latency_w0_editlog.md`.

## Status

Partly done at `135bcf7`; completed by part 2 below (the config keys).
Brief items 1, 2, 4, 5, 6 and 7 are done and committed alone in `135bcf7`.
Brief item 3 (config keys) is not done: a Bash call that printed `config/agent.yaml`, `config/stop_rules.yaml`, `config/profiles/demo.yaml` and the baseline test log was refused by the permission classifier, and those files were not read by any other route.
W1, W2 and W3 can build against the types now; the config keys need a follow-up W0 commit once the owner or planner allows reading those files.

## Changed types (all additive)

- `llm.outputs.RefineRevisionsOutput` with `FindingRevisionDraft`, `RevisionAction` (`keep`, `merge`, `withdraw`) and `revision_problems(out, finding_ids)`.
- `llm.outputs.VerdictOutput`: the verdict only.
- `errors.LLMDeadlineError`: keywords `partial` and `estimated_usage`, property `salvaged_items`; `usage` stays measured only.
- `states`: `Stage`, `STAGE_ORDER`, `STAGE_MEMBERS`, `STAGE_TRANSITIONS`, `STAGE_ON_CAP`, `STAGE_1_DEPENDS`, `MemberOutcome`, `stage_of`, `stage1_ready`, `stage1_close`.
- `state.checkpoint.Checkpoint.ordinal`; `latest_checkpoint` picks the highest ordinal.
- `state.run_state.Budget.elapsed_s` and `elapsed_for_resume()`.

## Revision semantics

For `keep`, every field is the final value: `rank` is 1..n over kept findings, `severity` may be null as a final value, `disposition` is required, `affected_decisions` replaces the draft's list, `added_evidence` is appended.
For `merge`, `merge_into` must name a kept finding and every other field is null or empty; for `withdraw`, every other field is null or empty.
`revision_problems` reports an unknown finding, a missing or doubled revision, a merge into itself, a merge into a finding that is not kept (this covers chains and cycles), field rules per action, and ranks that are not 1..n.

## Writers and readers

New types have no writer or reader yet outside `tests/test_interfaces_w0.py`; their consumers are named per workstream.

| Name | Writers | Readers |
|---|---|---|
| `RefineRevisionsOutput` family | W2: `phases/refine.py`, `prompts/refine.md` | W2: `phases/refine.py` |
| `VerdictOutput` | W2: `phases/report.py`, `prompts/report.md` | W2: `phases/report.py` |
| `RefineOutput`, `RevisionNote` (deprecated) | `phases/refine.py` via `call_model`; scripted answers in `tests/test_llm_phases.py`, `tests/test_e2e_synthetic.py`, `selftest.py`; stub phase in `tests/test_run_and_resume.py` | `phases/refine.py`; `PHASE_OUTPUT_TYPES`, read by `tests/test_anthropic_gateway.py` and `tests/test_not_assessed_verdict.py` |
| `ReportOutput` (deprecated) | `phases/report.py` `_verdict_call`; scripted answers in `tests/test_ingest_verify_report.py`, `tests/test_e2e_synthetic.py`, `tests/test_not_assessed_verdict.py`, `selftest.py` | `phases/report.py` `settle_report_output`; `PHASE_OUTPUT_TYPES`; `tests/test_not_assessed_verdict.py` |
| `LLMDeadlineError` | `llm/runtime.RunDeadline` (`no_time`, `cut`), `llm/gateway.py` (`AnthropicGateway`, `FakeGateway`, `FaultInjectingLLMGateway`), `llm/claude_code.py`; new keywords: W1 (`llm/claude_code.py`, `llm/partial.py`) | `phases/_model_calls.call_model`, `phases/research.py`, `phases/verify.py`, `llm/gateway.py`, `llm/claude_code.py`, `manifest.py` (by class name), `replay.recorded_error`; tests `test_runtime_policies.py`, `test_unrecorded_usage.py`, `test_budget_counts_failed_calls.py`, `test_cli_replay.py`; new fields: W2 phases, W3 `manifest.py` |
| `Stage` family | none (code constants) | W2: `orchestrator.py` |
| `TRANSITIONS`, `ON_CAP` (deprecated) | none (code constants) | `orchestrator.py`, `states.mermaid`, `tests/robustness/test_robustness_scenarios.py`, text in `tests/robustness/robustness_coverage.py` |
| `Checkpoint.ordinal` | `write_checkpoint` (called by `orchestrator.py`); constructors in `orchestrator.py`, `tests/test_state_and_gateways.py` | `latest_checkpoint`, read by `orchestrator.resume_run`, `tests/test_run_and_resume.py`, `tests/test_orchestrator.py`, `tests/test_llm_phases.py` |
| `Budget.elapsed_s` | W2: `orchestrator.py` at each checkpoint | W2: `orchestrator.resume_run` (sums `phase_seconds` today); W3: `manifest.py` timing, `replay.py` |

`harness/` has no reader or writer of any changed name.

## Deprecated names and who removes them

- `llm.outputs.RefineOutput` and `RevisionNote`: W2, when `phases/refine.py` moves to `RefineRevisionsOutput`.
- `llm.outputs.ReportOutput` (and `UnresolvedDraft`, `LimitationDraft` if then unused): W2, when `phases/report.py` moves to `VerdictOutput`.
- `states.TRANSITIONS` and `states.ON_CAP`: W2, when `orchestrator.py` moves to the stage table.
- `PHASE_OUTPUT_TYPES` still maps refine and report to the old types; W2 switches it.

## Seams for the other workstreams

- `report/coverage.py` still takes the latest checkpoint by file name (`files[-1]`); its owner should use `latest_checkpoint`.
- `replay.recorded_error` passes any `llm.jsonl` key that matches a constructor keyword; if W1 logs `estimated_usage` or `partial` under those exact keys, replay would pass a raw dict for `estimated_usage`. W1 and W3 should either log under other keys or add them to replay's `known` map.
- `orchestrator.resume_run` should call `Budget.elapsed_for_resume()` and set `elapsed_s` at every checkpoint (W2).

## `extra_args`

`config.ClaudeCodeSettings.extra_args` already exists, and `ClaudeCodeGateway.build_argv` already appends it to every argv.
So setting `claude_code.extra_args: ["--setting-sources", ""]` in `config/agent.yaml` is enough, with no gateway change; it was not set here because the file could not be read.

## Stage limits

Not implemented (config item).
Recommendation for the follow-up: explicit seconds per profile (`stage_1_end_s: 265`, `refine_end_s: 465`, `verdict_end_s: 530` for the 540 s demo profile), because the design gives absolute numbers measured for one deadline, the thinking block per call is fixed rather than proportional, and a fraction would silently move the limits when `--deadline` changes; validation should refuse limits that are not increasing or that exceed the deadline.

## Gates at `135bcf7`

`make test` (ruff, then pytest) exit 0, 1127 passed, 0 skipped; `make smoke` exit 0, 198 passed; `sit-review selftest` exit 0.
14 mutations of the new guards, all caught.

## Not verified

- Anything live: no model call, no agent run.
- That the revision schema is easy for the model to fill: unmeasured until W2's prompt and a rehearsal.
- The config items above.

## Part 2: the config keys (second W0 commit, 2026-10-03)

A second worker (`claude-fable-5-1`) read every config file with the Read tool, one per call, and finished brief item 3.
Edit log: `research/audit/latency_w0_editlog.md`, "part 2".
Status: W0 is complete; W1, W2 and W3 build against the types of `135bcf7` and the keys below.

### Keys

| Key | Value | Validation (all `ConfigError`, the problem named) | Readers |
|---|---|---|---|
| `agent.yaml` `assess.shards` | `intent_and_fitness` (design_intent, fitness_for_objectives, decision_preservation); `requirements_and_consistency` (requirement_completeness, internal_consistency, verifiability); `claims_and_assumptions` (claims_and_external_constraints, assumptions_and_dependencies); `risk_and_operations` (security_and_privacy, scalability_and_failure_modes, operability_and_governance) | a criterion in two groups; an unknown criterion (cross-file against `criteria.yaml`); a criterion twice in one group; a group name twice; an empty group; no group at all | none yet: W2 `phases/assess.py`, `orchestrator.py` (`AssessSettings.shards_for(run_criteria)` gives the run's shards, a criterion in no group as its own shard); W3 `manifest.py`, fault schedules |
| `stop_rules.yaml` `refine_reserve_seconds` | 600 base, 200 demo (values unchanged) | `assess_reserve_seconds` in the base file, a profile or a recorded dump is an error naming `refine_reserve_seconds`; never read, dropped or mapped | `llm/runtime.build_runtime`, `deadline_warnings`, `phases/research._ResearchRun` (attribute rename, semantics unchanged until W1) |
| `stop_rules.yaml` `stage_limits_s` | demo 265 / 465 / 530; base 2820 / 3420 / 3540 (3600 - 180 - 600, 3600 - 180, 3600 - 60) | `stage_1_end < refine_end < verdict_end`; `verdict_end` below the `deadline_seconds` of the resulting file or profile (a profile that lowers the deadline must set its own); each value at least 1; a profile without the block inherits the base values | none yet: W1 `llm/runtime.py`, W2 `orchestrator.py` |
| `agent.yaml` `claude_code.extra_args` | `["--setting-sources", ""]` | `--bare` and `--no-session-persistence` still rejected (gateway); the pair pinned by `test_default_claude_code_argv_is_hermetic` | `ClaudeCodeGateway.build_argv` appends it to every argv (confirmed by reading `llm/claude_code.py`, no gateway change) |

Why the limits are absolute seconds: the thinking block per call is a fixed cost (about 105 s per assess shard at `medium`), so a fraction of the deadline would silently move the limits when `--deadline` changes.
`--deadline` is applied after the file-level check, as for the reserves, so a run may hold a deadline below its profile's limits; W1's runtime must clamp and announce it (`deadline_warnings` today covers the reserves only).
The pinned lines (`agent.yaml` 1-12, `stop_rules.yaml` 1-8, `demo.yaml` 19-24 and 27) did not move; `tests/test_config_layout.py` already pins line number and content (against the runbook listing) and needed only the key rename in its demo needle.

### Finding: the committed measurement record is refused by replay

`docs/live_runs/demo_profile_measure_1/effective_config.json` carries `assess_reserve_seconds` and lacks `assess.shards` and `stage_limits_s`; `replay.recorded_config` validates it through `EffectiveConfig`, so `dra replay` now refuses it by name with exit 2 and no traceback, as it refuses a run whose prompts changed.
Keeping it replaying needed a replay change (forbidden for W0), an edit of the record, or a silent default or mapping (forbidden); none was made.
`test_the_committed_demo_measurement_run_replays_offline` became `test_the_committed_demo_measurement_run_is_refused_by_name_since_the_config_redesign`, with the cwd fix of brief item 6 kept (`--pdf` absolute from the test file).
For W3: either a loud legacy translation in `recorded_config` or the doctrine "a record replays at its commit"; the design already lists this replay as stale after W2 (section 6), and the demo backup is recorded with the final code (section 8).

### Seams

- W1: clamp `stage_limits_s` to a `--deadline` below them and announce it; read `refine_reserve_seconds` as the stage 1 reserve; set the demo report reserve to 75 s with that change (design section 5).
- W2: `cfg.agent.assess.shards_for(criteria the run assesses)`; criterion order inside a shard is the configured order.
- W3: the record refusal above; `manifest.py` shard count from `len(shards_for(...))`.

### Gates at the config commit

`ruff check agent harness tests` exit 0.
`pytest -q` from the repo root: 1147 passed, 0 skipped, exit 0 (1127 plus 20 new); from `/Users/malco`: 1147 passed, exit 0.
`sit-review selftest` exit 0; `make smoke` exit 0, 218 passed (the config tests are in the smoke set); `make test` exit 0.
14 mutations of the new guards, all caught; `config.py` and `agent.yaml` restored byte for byte (md5 checked).

### Not verified

- `--setting-sources ""` in a cloud session (design section 7, last check), and that the flag does not change `--resume --fork-session` behaviour: no `claude -p` was run.
- The stage limits in action: no reader exists yet.
- That the four groups balance in wall time: unmeasured until a rehearsal (design section 8).
