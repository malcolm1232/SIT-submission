# Runtime policies: edit log (workstream W1, 2026-10-02)

Decisions by the coordinator (owner-delegated, 2026-10-02). Offline only: no live call, no network,
no `claude` CLI, no git, nothing under `eval/blind/` opened. No prompt under `prompts/` changed, so
`PROMPTS.lock` is unchanged. State at the end: `ruff check agent harness tests` clean; `pytest -q`
983 passed, 0 skipped; `tests/robustness` 113 passed in about 22 s.

## Agent edits

| # | File | Change | Why | Tests |
|---|---|---|---|---|
| 1 | `agent/sit_review_agent/llm/runtime.py` (new) | `RunDeadline`, `ContextGuard`, `FirstCallNetwork`, `RuntimeLimits`, `attach_runtime`, `build_runtime`; constants (3 chars/token, 0.8 margin, 1M windows, 2,000 tokens per native PDF page, 10 s minimum attempt) | LLM-05, LLM-10, NET-02 in one place, read from the one run clock | `tests/test_runtime_policies.py` |
| 2 | `errors.py` | New `LLMDeadlineError(LLMTimeoutError)` (exit 3), `LLMConnectionError(LLMUnavailableError)` (exit 3), `LLMContextTooLongError` (exit 2, estimated and limit tokens) | Typed outcomes the phases can catch | `test_timeout_and_deadline_errors_keep_their_exit_codes`; `test_adversarial_invariants.py` exit-code sweep |
| 3 | `config.py` | `llm.first_call_network_window_s` (10), `llm.context_window_tokens` (null), `stop_rules.assess_reserve_seconds` (0 in code, 600 in YAML), `url_policy.authority` (`AuthorityHosts`) | Configurable policies; additive keys | `test_default_deadline_and_demo_profile`, `test_context_window_comes_from_config_retrieve_or_model` |
| 4 | `llm/gateway.py` `AnthropicGateway` | Context check before sending; per-attempt timeout bounded by the deadline (`asyncio.wait_for`), a cut attempt raises `LLMDeadlineError`, never retried; no retry without time; first-call connection window; `APIConnectionError` -> `LLMConnectionError`; preflight offline -> "no network"; `timeout_s` in the log | LLM-05, LLM-10, NET-02 | `test_anthropic_*` in `test_runtime_policies.py` |
| 5 | `llm/claude_code.py` `ClaudeCodeGateway` | Same policies (runner gets the bounded timeout; PDF blocks do not count, they are dropped); connection markers in `_classify`; `elapsed_s` and `timeout_s` on successful calls | LLM-05, LLM-10, NET-02, OPS-10 | `test_claude_code_*` |
| 6 | `llm/gateway.py` `FakeGateway`, `FaultInjectingLLMGateway` | `runtime` attribute; fake refuses a call without time or over size; the wrapper's `hang` lasts the bounded timeout, `offline`/`connection_reset` are `LLMConnectionError` with the first-call window, no retry past the deadline | The offline suite exercises the same policy | `test_fault_wrapper_*`, robustness LLM-05, NET-02 |
| 7 | `llm/gateway.py` `log_unsent` | Errors raised before an attempt is made (deadline, context size, a request the gateway rejects itself, a retry the deadline refuses) are logged to `llm.jsonl` with call ID, phase, purpose, outcome and `sent: false` | W2 request: replay must see the same error at the same call | `test_unsent_errors_are_logged_with_their_call_id`, `test_retry_refused_by_the_deadline_is_logged` |
| 8 | `phases/_model_calls.py` | `call_model` catches `LLMDeadlineError`: disclosed (`budget_or_deadline_hit`), phase continues with its code fallback; `PhaseCall.cut` | Protect assess; keep assess findings when refine is cut | robustness LLM-05 |
| 9 | `phases/assess.py` | Coverage note "out of time before assessment" when cut | No fabricated findings | robustness LLM-05 |
| 10 | `phases/research.py` | Deadline rule inside research keeps `report_reserve + assess_reserve`; a cut call ends research (`deadline`); a conversation over the context limit ends research (`budget_tokens` / `context_window`); host lists passed to `extract_sources` | Research absorbs the squeeze | `test_research_keeps_the_assess_reserve` |
| 11 | `phases/verify.py` | Anchor-repair call also degrades on `LLMDeadlineError` | Verify never crashes on a cut | full suite |
| 12 | `phases/report.py` | When assessment was cut: no verdict call; `not_assessed_verdict()` (`not_fit`, confidence 0, rationale "Not assessed ..."); `assessment_cut()` | No invented verdict on an unassessed design | `test_not_assessed_verdict_is_never_a_certification`, robustness LLM-05 |
| 13 | `report/render.py` | Verdict shown as "Not assessed (out of time before assessment)" | The JSON label is a placeholder | robustness LLM-05 (`report.md`) |
| 14 | `orchestrator.py` | `_run_check_tool_key` (INF-08) in `run_review` and `resume_run`; preflight before `models.retrieve`; `_run_attach_runtime`; `_run_ProcessFault` / `_run_process_faults` (new runs only); a deadline skip before assess is disclosed as "out of time before assessment"; `RunRequest.k_index` | INF-08, NET-02, LLM-05, process faults, W2 request | `test_inf08_*`, `test_preflight_*`, `test_cli_faults_apply_process_entries`, `test_deadline_before_assess_is_disclosed_as_out_of_time`, `test_k_index_reaches_the_manifest` |
| 15 | `tools/faults.py` | `PROCESS_FAULTS`; the loader refuses a `process:` entry with an unknown stage, a non-process type or `at` other than start/end | No silent no-op | `test_loader_rejects_malformed_process_entries` |
| 16 | `tools/sources.py` | Host lists removed from code; read from `config/url_policy.yaml` `authority:` (`default_authority_hosts`, `hosts=` parameter) | OVF-07 | `test_authority_hosts_come_from_config_without_the_sample_stack`; existing `test_classify_authority` unchanged |
| 17 | `tools/gateway.py` `LoggingToolGateway` | Each `list_tools` appends `{"listed_at", "tools": [{server, name, description, input_schema, capability}]}` (redacted) to `tools_list.jsonl`; takes the clock | W2 request (replay of live claude_code runs with tools) | `test_tool_listings_are_logged_for_replay` |
| 18 | `progress.py` | `ConsoleProgress.stream` default reads `sys.stderr` at construction | W2 request | `test_console_progress_reads_stderr_at_construction` |
| 19 | `state/run_state.py`, `manifest.py` | `RunState.k_index` (default None) into `ManifestExtra.k_index` | W2 request (optional item 4) | `test_k_index_reaches_the_manifest` |
| 20 | `phases/plan.py` | `enabled_capabilities` sorted by name | W2 request (optional item 5): plan prompt independent of `tools.capabilities` order | `test_plan_capabilities_do_not_depend_on_config_order` |
| 21 | `ingest/pdf.py` | `_drop_list_items`: section numbers only go forward, so numbered list items inside a section are not sections; a repeated top-level number keeps the heading-like candidate. Comment example "10.Alert management" (from an eval document's contents) replaced | Coordinator request: exact quotes in clinical_rpm v1 §17.4 and research_lakehouse v1 §13 failed the section window | `tests/test_runtime_ingest_headings.py` (reads only `design_v1.pdf`) |

## Config

| File | Change |
|---|---|
| `config/stop_rules.yaml` | Line 6 `deadline_seconds` 540 -> 3600 (reason in the file comment); `report_reserve_seconds` 60 -> 180; new `assess_reserve_seconds: 600`. Pinned positions unchanged |
| `config/agent.yaml` | `llm.first_call_network_window_s: 10`, `llm.context_window_tokens: null`, timeout comment. Lines 1-12 untouched |
| `config/url_policy.yaml` | New `authority:` block (the lists moved from `tools/sources.py`), minus `github.com/pgvector`, `pgvector.dev`, `kafka.apache.org` |
| `config/profiles/demo.yaml` (new) | Effort plan/understand medium, research low, assess/refine/verify/report medium; deadline 540; reserves 120 / 200; marked UNMEASURED |

## Scripts

`scripts/leakage_grep.py` (new): term lists from the eval/synthetic keys and documents (and `--sample`
on the laptop): TF-IDF word pairs, one-item proper nouns, IDs and code names, numbers with units,
the known sample-stack hosts, 13-word overlaps. Gates agent/, prompts/, config/ (`--strict` adds
cassettes and fixtures). eval/blind is refused. Eight reviewed generic hits are resolved in
`DEFAULT_RESOLVED` with reasons. Tests: `tests/test_runtime_leakage.py`, robustness OVF-07.

## Tests outside my folders (edited because a decided change moved their expectation)

| File | Change | Reason |
|---|---|---|
| `tests/test_research_phase.py::test_deadline_ends_research_without_a_wrap_up_call` | Sets `report_reserve_seconds: 60, assess_reserve_seconds: 0` explicitly | Its comment relied on the old 60 s default reserve |
| `tests/test_llm_phases.py::test_plan_with_tools_and_approval` | Expects `["scholarly", "search"]` | Item 20 (sorted capabilities) |
| `tests/test_cli_replay.py::test_replay_refuses_run_dirs_lacking_data` | Case 3 deletes `tools_list.jsonl` | Item 17: listings are now logged, so the "no catalogue" case needs a run from before |

## Robustness suite (`tests/robustness/`)

Harness no longer applies `process:` faults itself (the agent does); `Scenario.env_unset`;
`long_design_pages` (150-page document generated at test time as page-marked text: a generated PDF
took pdfplumber about 50 s). New cases LLM-05 (demo profile and default deadline), LLM-10, NET-02,
INF-08 (key unset; `--no-tools`), OVF-07. Coverage registry and README updated: offline 49, laptop
28, not a schedule 4, needs decision 0. Schedule headers of LLM-05, NET-02, OPS-04 updated.
`robustness_repro.py` now prints the three drills. Regression test 1 advances to the configured
deadline instead of 1800 s. Results CSV regenerated: 49 PASS, 0 FAIL, 32 BLOCKED.

## Docs

`agent/README.md`: module rows (orchestrator, `llm/runtime.py`, faults, sources, ingest) and a
"Runtime policies" section. `docs/DEMO_DAY_RUNBOOK.md`: §4.1 line 6 value and a note on the demo
profile; §6 rows (missing key, no internet); §7 "also drilled" line (OPS-04/BEH-25 via `--faults`).
