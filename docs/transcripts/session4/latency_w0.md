# Latency redesign W0: the interface change

Date: 2026-10-03.
Branch `s4/w0-interfaces`, base `e28b082`; interface commit `135bcf7`, not pushed.
Edit log: `research/audit/latency_w0_editlog.md`.

## Status

Partly done.
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
