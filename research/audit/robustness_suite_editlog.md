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

## Verifier edits

Verifier for workstream R, 2026-10-02. Baseline: `ruff check agent harness tests` had one E501 in
`harness/sit_eval/matcher.py` (a parallel verifier's area, not touched here); the robustness folder
passed 96 tests. Every agent edit below is small and local, has a regression test, and was checked to
fail against the unfixed agent (a scratch copy of the repo with the change reverted). No prompt,
config, schema or PROMPTS.lock changed.

Agent edits:

7. `agent/sit_review_agent/orchestrator.py` `_run_fail` and new `_run_partial_report` (BEH-25,
   ADR-009 item 5): on exit 4 (stage crash) the run directory now gets `report.partial.md` (completed
   stages, crashed stage, counts of planned questions, ledger entries and unverified drafts, earlier
   degradations, the resume command), named in `failure.json` as `partial_report`. It prints no
   finding (none has passed verify) and names the error by class only (details stay in
   `failure.json`). It is not `report.json`, so INV-02 ("a failed run must not look complete") holds.
   Tests: `test_robustness_scenario[BEH-25]` (now in the passing suite, with resume),
   `test_stage_crash_writes_a_partial_report_listing_completed_stages`,
   `test_no_partial_report_when_the_model_is_unavailable`.
8. `agent/sit_review_agent/phases/refine.py` (BEH-10): new `CONCLUSION_FIELDS` (`kind`, `severity`,
   `disposition`). A refine answer that changes one of them for an existing finding with no revision
   note reason and no new evidence ID is rejected: the earlier draft is kept and the finding's history
   gets "rejected: severity high -> low without a revision reason or new evidence (BEH-10)". A change
   with a reason (the prompt already requires one per finding) or a new evidence ID is accepted as
   before. Tests: `test_robustness_scenario[BEH-10]`, `test_severity_change_needs_a_reason_or_new_evidence`
   (both branches).
9. `agent/sit_review_agent/phases/verify.py` new `unlabelled_conflicts` (BEH-12, L0): after hydration, a
   finding whose recommendation `change_summary` uses a reversal verb (replace, remove, drop, abandon,
   retire, reverse, eliminate, stop using, instead of, switch/migrate/move away from) and at least three
   of an approved decision's content words, without an `affected_decisions` `challenges` label for that
   decision, is disclosed as a degradation (and so in the limitations). It never drops the finding,
   because the check is lexical. Tests: `test_robustness_scenario[BEH-12]` (also asserts no false alarm
   on the control run), `test_unlabelled_reversal_of_an_approved_decision_is_detected` (4 cases).
10. `agent/sit_review_agent/phases/research.py` (stop reason with zero evidence): a model stop vote when
    the ledger holds no external evidence is now reported as `tool_failure` (no tool call succeeded)
    or `no_marginal_gain` (calls answered but found nothing), detail "model_stop_vote with no external
    evidence", instead of `sufficient_evidence (model_stop_vote)`. Module docstring updated. Test:
    `test_robustness_scenario[INF-24]` now asserts `stop_reason.code == "tool_failure"`.

Suite edits (`tests/robustness/**`):

- `test_robustness_scenarios.py`: new cases BEH-10, BEH-12, BEH-25; INF-07 now asserts that only the
  first call reaches the transport (a mutation that removed "disable every server after a confirmed
  401" passed the old check); INF-24 asserts the stop reason.
- `test_robustness_regressions.py`: tests for edits 7-9; the fix-5 test is parametrised over
  `title` too (its old field, `recommendation.rationale = "TBD"`, was already dropped by the 15-character
  minimum before fix 5, so it pinned only the message wording).
- `robustness_coverage.py`, `README.md`: BEH-10, BEH-12, BEH-25 moved to the passing suite (needs
  decision: 8 -> 5); INF-11 names `test_fault_injection.py::test_inf11_tool_error_not_retried_then_unusable`
  (the end-to-end run never reaches the fault because the server is disabled by default); BEH-25 says
  plainly that the "illegal transition raises" half has no `transition()` API to call and is asserted
  structurally (TRANSITIONS and ON_CAP only move forward); fixed-defects table rows 7-10.
- `robustness_repro.py`: BEH-25, BEH-10, BEH-12 reproductions removed (they pass now).
- `faults/BEH-25.yaml`: header comment updated.
- `results/robustness_results.csv` and `robustness_summary.txt` regenerated: 44 PASS, 5 FAIL (needs
  decision), 32 BLOCKED.

After: `tests/robustness` 108 passed, three consecutive runs, 15-16 s each.
