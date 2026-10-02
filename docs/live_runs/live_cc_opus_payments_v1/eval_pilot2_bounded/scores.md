# Scores: live_cc_opus_payments_v1 vs synthetic-payments-orchestration-001 (v1)

**UNFROZEN PILOT** - eval/prereg.yaml is not frozen; exploratory only.

- Review: `docs/live_runs/live_cc_opus_payments_v1/report.json` (sha256 d1637d57e45a), condition: unlabelled
- Key: `eval/synthetic/payments_orchestration/answer_key.canonical.json` (sha256 32c34fcd5628), scored_run_ready: false
- Document text: pdf:eval/synthetic/payments_orchestration/design_v1.pdf (sit_review_agent.ingest.ingest, pdfplumber) (sha256 ad0bb891f073, matches the review: true)
- Judge: claude_code / claude-opus-5-5 / effort high; pairwise, candidates shortlist_bounded, 3 samples, seed 20261002; grounding judges true
- Prompt bundle: ac35d198ecef (lock ok: true)

Judge calls: 98 (98 live, 0 cached, 0 failed); reported cost $10.364

## Warnings

- eval/prereg.yaml is not frozen (frozen: false): these scores are UNFROZEN PILOT scores, exploratory only, and carry no confirmatory claim
- answer key has scored_run_ready = false (pending: canary_guid, core_insight, anchor_quote, expected_disposition, approved_decisions, key_second_review, external_fact_verification, sound_overlap_annotations, v2_changed_sections); core_insight is filled from the description and credit items, so matcher scores are provisional
- adaptive third sample: the third pairwise sample is asked only when the first two disagree or one failed (the median of 3 is then unchanged; prereg matcher.pairwise_scoring as amended 2026-10-02, USER_DECISIONS #15)

## Metrics

| Metric | Value | Status | Reason / note |
|---|---|---|---|
| recall | 0.786 | primary |  |
| lenient_recall | 1.000 | secondary |  |
| precision_strict | 0.550 | secondary |  |
| precision_adjudicated | 0.950 | key_secondary | P_a = (TP + VALID_UNPLANTED + PARTIAL_KEY_MATCH) / N (metrics.md §3, amended 2026-10-02, UD #14) |
| partial_key_match_count | 3 | secondary | strict-unmatched findings scoring PARTIAL (2) against a key flaw no finding matches; counted as correct in precision_adjudicated, not VALID_UNPLANTED (not_gold: the flaw is not in this version's gold set, so the finding is not credited) |
| lenient_precision_adjudicated | 0.950 | secondary | P_a = (TP + VALID_UNPLANTED + PARTIAL_KEY_MATCH) / N (metrics.md §3, amended 2026-10-02, UD #14) |
| f1_strict | 0.647 | secondary |  |
| f1_adjudicated | 0.860 | secondary |  |
| severity_weighted_recall | 0.733 | key_secondary |  |
| critical_recall | 0.750 | secondary |  |
| severity_agreement_qwk | 0.436 | secondary |  |
| hallucinated_finding_rate | 0.000 | key_secondary |  |
| hallucinated_finding_rate_without_g3 | 0.000 | exploratory | G1 failures plus adjudicated HALLUCINATED only |
| quote_fabrication_rate | 0.000 | secondary |  |
| citation_precision | 0.703 | secondary |  |
| fabricated_citation_rate | null | key_secondary | no external citations in this review |
| source_type_accuracy | 1.000 | secondary |  |
| cdr | 1.000 | key_secondary |  |
| balanced_unit_accuracy | 0.931 | secondary | flawed unit = a section id named in a gold flaw location |
| rjr_struct | 1.000 | secondary |  |
| rjr_subst | null | deferred | needs the citation judge (Q_evid) and the recommendation judge (Q_benefit, Q_rat); recommendation_judge is off (prereg deferred metric) |
| unjustified_recommendation_rate | 0.050 | secondary |  |
| duplication_rate | 0.000 | secondary |  |
| non_specific_rate | 0.050 | secondary |  |
| ndcg_at_G | 0.650 | deferred |  |
| ndcg_at_5 | 0.662 | deferred |  |
| mrr_critical | 0.500 | deferred |  |
| critical_in_top3 | 0 | deferred | all critical flaws (first 3 by key order when more than 3) matched within ranks 1-3 |
| ece | 0.212 | deferred |  |
| brier | 0.092 | deferred |  |
| auroc | 0.842 | deferred |  |
| action_type_accuracy | 0.727 | blocked |  |
| approved_decision_violation_rate | 0.000 | blocked |  |
| bait_resistance | null | blocked | BLOCKED: no sound section has bait = true |
| pooled_recall | null | secondary | no pooled supplementary key G+ exists yet (built from human-confirmed VALID_UNPLANTED after an evaluation round, metrics.md §2.3 step 5; PARTIAL_KEY_MATCH findings are already key flaws and never enter G+) |
| stale_finding_rate | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| resolved_acknowledgement | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| persisted_recall | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| new_flaw_recall | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| copy_through_rate | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| adjudication_counts | NON_SPECIFIC: 1, PARTIAL_KEY_MATCH: 3, VALID_UNPLANTED: 5 | secondary |  |
| adv_v2 | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| brier_skill | -0.945 | deferred |  |
| category_label_accuracy | 0.909 | exploratory |  |
| changed_section_coverage | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| citation_precision_lenient | 1.000 | secondary |  |
| citation_recall | 0.950 | deferred | finding claims only; recommendation evidence fields and atomic external assertions need the claim splitter, which is not implemented |
| doc_verdict_calibration | null | deferred | the key has no document-level fitness label |
| false_absence_rate | 0.000 | deferred |  |
| false_resolution_rate | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| fully_sound_doc_accuracy | null | blocked | BLOCKED: this key has flaws (no fully sound control document exists) |
| justified_decline_rate | 0.800 | exploratory | G1 on the sound area's anchors only; G3 is not run on sound-area justifications |
| lenient_adjudication_counts | NON_SPECIFIC: 1, VALID_UNPLANTED: 5 | secondary |  |
| lenient_duplication_rate | 0.000 | secondary |  |
| lenient_f1_adjudicated | 0.974 | secondary |  |
| lenient_f1_strict | 0.824 | secondary |  |
| lenient_non_specific_rate | 0.050 | secondary |  |
| lenient_precision_strict | 0.700 | secondary |  |
| location_validity_rate | 0.817 | exploratory | G2 (agent verify_anchor) pass rate |
| overrun | null | deferred | needs per-step working state (not in report.json or manifest.json) |
| read_before_cite_rate | null | secondary | no external citations |
| research_yield | null | deferred | no external sources retrieved |
| selective_precision | 0.5: 0.950, 0.7: 1.000, 0.9: 1.000 | deferred | adjudicated precision among findings with confidence >= t (duplicates excluded) |

## Per category (exploratory)

| Category | Gold | Matched | Recall | Agent findings | Precision |
|---|---|---|---|---|---|
| acceptance_criterion_cannot_validate | 1 | 1 | 1.000 | 1 | 1.000 |
| ambiguous_requirement | 1 | 1 | 1.000 | 1 | 1.000 |
| decision_depends_on_pending_item | 1 | 1 | 1.000 | 1 | 1.000 |
| internal_contradiction | 3 | 3 | 1.000 | 5 | 1.000 |
| missing_or_unverifiable_requirement | 2 | 0 | 0.000 | 4 | 0.750 |
| scalability_or_failure_mode | 2 | 2 | 1.000 | 3 | 1.000 |
| security_privacy_gap | 2 | 2 | 1.000 | 3 | 1.000 |
| unsupported_or_incorrect_claim | 2 | 1 | 0.500 | 2 | 1.000 |

## Efficiency (from the run manifest)

- cost_usd: 3.679
- input_tokens: 169004
- output_tokens: 116264
- cached_tokens: 6198
- price_table_date: 2026-09-25
- tool_calls: 0
- tool_calls_by_tool: 
- wall_time_s: 3372.195
- per_stage_s: assess: 2933.181, ingest: 2.064, plan: 157.991, research: 0.000, understand: 158.276, verify: 32.697
- stop_reason: code: tool_failure, group: error

## Key flaws

| Flaw | Severity | Strict match | Lenient match | Best median score |
|---|---|---|---|---|
| F01 | critical | FND-002 | FND-002 | 3.000 |
| F02 | low | FND-006 | FND-006 | 3.000 |
| F03 | high | FND-005 | FND-005 | 3.000 |
| F04 | high | - | FND-012 | 2.000 |
| F05 | low | FND-011 | FND-011 | 3.000 |
| F06 | critical | - | FND-004 | 2.000 |
| F07 | high | - | FND-016 | 2.000 |
| F08 | critical | FND-009 | FND-009 | 3.000 |
| F09 | high | FND-001 | FND-001 | 3.000 |
| F10 | critical | FND-003 | FND-003 | 3.000 |
| F11 | high | FND-008 | FND-008 | 3.000 |
| F12 | low | FND-017 | FND-017 | 3.000 |
| F13 | high | FND-018 | FND-018 | 3.000 |
| F14 | low | FND-014 | FND-014 | 3.000 |

## Findings

| Finding | Rank | Severity | Strict | Class (strict) | Lenient |
|---|---|---|---|---|---|
| FND-001 | 1 | critical | F09 | - | F09 |
| FND-002 | 2 | high | F01 | - | F01 |
| FND-003 | 3 | high | F10 | - | F10 |
| FND-004 | 4 | high | - | PARTIAL_KEY_MATCH (F06) | F06 |
| FND-005 | 5 | high | F03 | - | F03 |
| FND-006 | 6 | high | F02 | - | F02 |
| FND-007 | 7 | high | - | VALID_UNPLANTED | - |
| FND-008 | 8 | high | F11 | - | F11 |
| FND-009 | 9 | high | F08 | - | F08 |
| FND-010 | 10 | high | - | VALID_UNPLANTED | - |
| FND-011 | 11 | medium | F05 | - | F05 |
| FND-012 | 12 | high | - | PARTIAL_KEY_MATCH (F04) | F04 |
| FND-013 | 13 | medium | - | VALID_UNPLANTED | - |
| FND-014 | 14 | medium | F14 | - | F14 |
| FND-015 | 15 | medium | - | VALID_UNPLANTED | - |
| FND-016 | 16 | medium | - | PARTIAL_KEY_MATCH (F07) | F07 |
| FND-017 | 17 | medium | F12 | - | F12 |
| FND-018 | 18 | medium | F13 | - | F13 |
| FND-019 | 19 | medium | - | VALID_UNPLANTED | - |
| FND-020 | 20 | low | - | NON_SPECIFIC | - |
