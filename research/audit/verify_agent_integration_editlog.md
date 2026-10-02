# Integration verifier edit log
Baseline: ruff clean, pytest 391 passed / 10 skipped, selftest passes.
1. llm/gateway.py: LLMCallLog redacts every llm.jsonl entry (redact_log_entry: Redactor over configured secrets + CANARY_RE mask); Anthropic/ClaudeCode pass tools.auth_env (1c).
2. llm/gateway.py: LLMCallLog.resumed_phases + is_resumed; entries of the re-run stage carry resumed:true; LLMResult.resumed set by Anthropic/ClaudeCode/Fake; prepare_resume() public hook (1e, 1d).
3. llm/gateway.py: FakeGateway.next_call_id(); FaultInjectingLLMGateway: native_pdf forwards inner (setter kept), own refusal list (no poke into inner._refusals), terminal injected faults get a real call ID, injected attempts prepended to result.attempts (1d, 1f).
4. tools/gateway.py: CallIds.advance_to(); orchestrator advances every CallIds in place (policy/fault layers held a stale copy -> duplicate call IDs on resume for blocked calls) (1d, defect).
5. orchestrator.py: prepare_resume replaces _seq poke; _run_rerun_phase; native_pdf poke removed.
6. manifest.py: merged_refusals / merged_fallback_events (multiset merge state + gateway); report._ensure_disclosures uses the merge (1a; `or` dropped gateway-only entries).
7. research.py: every refusal recorded (+ call IDs); fallbacks recorded + model_fallback degradation. verify.py/report.py: refusals recorded in state; verify records fallback.
8. verify.settle_registry_anchors: was a no-op with the real understand (which records iteration-0 hash at freeze) -> unresolved registry anchors would fail INV-04 at report (exit 4). Now runs until a later phase completes and re-records the iteration-0 hash (defect).
9. orchestrator: warm-up started right after the tool stack is built (overlaps models.retrieve, preflight, ingest, understand), stopped on every exit path (_run_stop_warmup); setup failures after the run dir exists write failure.json and re-raise typed (_run_setup_failed) (1b, INV-02/11).
10. tools/mcp_client.ServerConnection.open: cancellation while waiting for initialize cancels the owner task (leaked before) (1b).
11. research.py: --no-tools run: plan sets capability none for every question when no tool is enabled, so research said "no question needs external evidence" and never disclosed the doc-only run; now ctx.tools None -> doc-only first; needs_external questions with capability none reported unanswered + disclosed (defect).
12. tests/test_research_phase.py: refusal test now expects both refusals recorded.
13. phases/ingest.py: load_input runs in asyncio.to_thread so the MCP warm-up progresses during pdfplumber extraction (1b).
14. phases/_model_calls.py: _EvidenceResolver.resolve_id — a model-written EV- ID resolves only to an entry the model was shown or one created for its own NEW-n ID. Before, an invented ID (e.g. "EV-001" cited as external in a doc-only run) silently attached to the doc entry the resolver created under the same name later in the same pass (defect, INV-05).
15. phases/verify.py: _short() names the broken rule for pydantic ValidationErrors in the "dropped by code checks" disclosure (was "1 validation error for Finding").
16. orchestrator._run_setup_failed merges with an existing failure.json (resume keeps the earlier record, completed phases, resumable flag).
17. invariants.check_INV_08 docstring: llm.jsonl is in scope (1c decision).
18. llm/gateway.py module docstring (output_config.format, not output_format=; logging/redaction contract); llm/outputs.llm_facing_schema docstring (stale "SDK output_format" line).
19. Removed tests/test_pending.py and the `phase` pytest marker (pyproject.toml); test docstrings now say "the removed tests/test_pending.py".
20. agent/README.md: module map statuses rewritten, rows added for phases/_model_calls.py, tools/mcp_client.py, tools/policy.py, tools/fault_apply.py, cli.py; workstream note updated.
21. New tests: tests/test_e2e_synthetic.py (1 test, ~5.5 s), tests/test_integration_seams.py (15), tests/test_adversarial_invariants.py (37 incl. 26 parametrised AgentError subclasses).
No prompt changed; PROMPTS.lock up to date.
