# Robustness suite (workstream R) edit log

Changes outside `tests/robustness/`. Baseline before the first edit: ruff clean, pytest 444 passed
offline. Every agent edit fixes a defect a P0 scenario exposed, is small and local, and has a
regression test in `tests/robustness/test_robustness_regressions.py`. No prompt, config, schema,
frozen interface or other workstream's file changed; PROMPTS.lock untouched.

1. `agent/sit_review_agent/orchestrator.py` `Orchestrator.run` (LLM-05; the live run of
   docs/HANDOVER_FULL.md §8): a between-phase cap that skips a phase now always records a
   `budget_or_deadline_hit` degradation. Before, it was recorded only when `state.stop_reason` was
   still empty, so after research had set a stop reason a deadline that skipped `refine` (or `assess`)
   was hidden from the report (INV-07). The first stop reason is still kept. Test:
   `test_deadline_skip_after_research_is_disclosed`.
2. `agent/sit_review_agent/llm/gateway.py` `FaultInjectingLLMGateway.call` (LLM-06/07/08): passes
   `nth` (the stage's 0-based logical call index) to `fault_apply.match_rule`. Before, an LLM rule
   with `nth`, a documented match key, never fired, and no schedule could fault only the first call of
   a stage (phase-level retries such as the `max_tokens` retry are new calls with `attempt` 0 again).
   Docstring updated. Test: `test_llm_rule_with_nth_hits_only_that_call_of_the_stage`.
3. `agent/sit_review_agent/llm/gateway.py` `FaultInjectingLLMGateway.__init__` / `call` and
   `orchestrator._run_build_llm` (LLM-05): new keyword `policy` (the `config.agent.llm` section),
   used for `max_retries`, backoff and `timeout_s` when the wrapped gateway carries none (the fake
   transport). Before, an injected hang on `transport: fake` cost a hard-coded 600 s instead of the
   configured 1800 s. Backward compatible (keyword-only, default None). Test:
   `test_injected_hang_costs_the_configured_timeout`.
4. `agent/sit_review_agent/phases/research.py` `_finish` (INF-24): the doc-only disclosure ("No
   external research was possible: every tool call failed") is also recorded when every call that
   reached a server failed and none succeeded, not only once every breaker is open. Before, a model
   that tried each server once and stopped got a report without the doc-only statement. Test:
   `test_all_calls_failed_below_the_breaker_threshold_is_doc_only`.
5. `agent/sit_review_agent/phases/verify.py` (LLM-09): `hollow_fields()` and a `_PLACEHOLDER`
   pattern (TBD, TBA, TODO, N/A, none, placeholder, lorem ipsum, punctuation only, empty); a finding
   whose title, statement, no-change rationale, recommendation or next step is only a placeholder is
   dropped with the existing "dropped by code checks" disclosure and a history note; a sound area with
   a placeholder `why_sound` is dropped likewise. Before, a "TBD" strength finding reached the report.
   Tests: `test_placeholder_text_makes_a_draft_hollow`, `test_real_text_is_not_hollow`,
   `test_hollow_finding_is_dropped_and_disclosed`.
6. `agent/sit_review_agent/phases/_model_calls.py` `_EvidenceResolver.doc_entry` (BEH-17): when a
   `doc` citation's quote is not found in the canonical text, the fallback entry at the finding's
   anchor now holds the anchor's own quote. Before, it held the model's quote, so an external fact
   labelled `doc` became a `doc` ledger entry (document text that is not in the document; INV-05 could
   not see it because the citation matched its own excerpt). Docstring updated. Test:
   `test_doc_citation_with_a_quote_not_in_the_document_is_not_recorded_as_doc_text`.

Not fixed (reported in `tests/robustness/README.md`, "Failing, needs decision", with
`tests/robustness/robustness_repro.py`): BEH-25 (no partial report on a stage crash), LLM-05 (the
deadline does not bound an in-flight model call; 1800 s per attempt vs a 540 s deadline), NET-02 (no
fast offline detection), BEH-10 (no "no change without cause" rule), BEH-12 (unlabelled registry
conflicts not caught at L0), INF-08 (`run` does not fail fast without the MCP key), LLM-10 (no
token pre-count), OVF-07 (sample-specific hosts in `tools/sources.py`).

After: ruff clean on `agent harness tests`; full pytest passes (the count includes the other
workstreams' tests: 829 at the end of this session); `tests/robustness`: 96 tests in about 15 s.
