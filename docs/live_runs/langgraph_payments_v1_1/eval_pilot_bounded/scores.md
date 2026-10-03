# Scores: langgraph_payments_v1_1 vs synthetic-payments-orchestration-001 (v1)

**EXPLORATORY** - this run was started with --exploratory (eval/prereg.yaml LC12 override); these scores are exploratory and may not be reported as confirmatory

**UNFROZEN PILOT** - eval/prereg.yaml is not frozen; exploratory only.

- Review: `runs/langgraph_payments_v1_1/report.json` (sha256 14d40d839105), condition: unlabelled
- Key: `eval/synthetic/payments_orchestration/answer_key.canonical.json` (sha256 8eda2e5de12e), scored_run_ready: false
- Document text: text:runs/langgraph_payments_v1_1/text/DOC-design_v1.pages.txt (sha256 ad0bb891f073, matches the review: true)
- Judge: claude_code / claude-opus-5-5 / effort high; pairwise, candidates shortlist_bounded, 3 samples, seed 20261002; grounding judges true
- Prompt bundle: ac35d198ecef (lock ok: true)

Judge calls: 86 (86 live, 0 cached, 0 failed); reported cost $9.446

## Warnings

- EXPLORATORY: this run was started with --exploratory (eval/prereg.yaml LC12 override); these scores are exploratory and may not be reported as confirmatory
- eval/prereg.yaml is not frozen (frozen: false): these scores are UNFROZEN PILOT scores, exploratory only, and carry no confirmatory claim
- answer key has scored_run_ready = false (pending: canary_guid, core_insight, anchor_quote, expected_disposition, approved_decisions, key_second_review, external_fact_verification, sound_overlap_annotations, v2_changed_sections): scored under --exploratory (LC12 override); core_insight is filled from the description and credit items, so matcher scores are provisional
- adaptive third sample: the third pairwise sample is asked only when the first two disagree or one failed (the median of 3 is then unchanged; prereg matcher.pairwise_scoring as amended 2026-10-02, USER_DECISIONS #15)
- usage incomplete: unrecorded_usage: 1 model call with unrecorded usage (llm-0002 assess attempt 0, deadline cut, 263.212 s); their tokens and cost are not in the totals, so the recorded cost and tokens are lower bounds; the efficiency metric's cost and tokens are null and the lower bounds are reported beside them
- 1 judge calls failed after retries; affected metrics are null or noted

## Metrics

| Metric | Value | Status | Reason / note |
|---|---|---|---|
| recall | 0.857 | primary |  |
| lenient_recall | 1.000 | secondary |  |
| precision_strict | 0.667 | secondary |  |
| precision_adjudicated | 0.944 | key_secondary | P_a = (TP + VALID_UNPLANTED + PARTIAL_KEY_MATCH) / N (metrics.md §3, amended 2026-10-02, UD #14) |
| partial_key_match_count | 2 | secondary | strict-unmatched findings scoring PARTIAL (2) against a key flaw no finding matches; counted as correct in precision_adjudicated, not VALID_UNPLANTED (not_gold: the flaw is not in this version's gold set, so the finding is not credited) |
| lenient_precision_adjudicated | 0.944 | secondary | P_a = (TP + VALID_UNPLANTED + PARTIAL_KEY_MATCH) / N (metrics.md §3, amended 2026-10-02, UD #14) |
| f1_strict | 0.750 | secondary |  |
| f1_adjudicated | 0.899 | secondary |  |
| severity_weighted_recall | 0.867 | key_secondary |  |
| critical_recall | 1.000 | secondary |  |
| severity_agreement_qwk | 0.294 | secondary |  |
| hallucinated_finding_rate | 0.000 | key_secondary |  |
| hallucinated_finding_rate_without_g3 | 0.000 | exploratory | G1 failures plus adjudicated HALLUCINATED only |
| quote_fabrication_rate | 0.000 | secondary |  |
| citation_precision | null | secondary | citation judge failed or was incomplete for 1 findings |
| fabricated_citation_rate | null | key_secondary | no external citations in this review |
| source_type_accuracy | 1.000 | secondary |  |
| cdr | 1.000 | key_secondary |  |
| balanced_unit_accuracy | 0.944 | secondary | flawed unit = a section id named in a gold flaw location |
| rjr_struct | 1.000 | secondary |  |
| rjr_subst | null | deferred | needs the citation judge (Q_evid) and the recommendation judge (Q_benefit, Q_rat); recommendation_judge is off (prereg deferred metric) |
| unjustified_recommendation_rate | 0.056 | secondary |  |
| duplication_rate | 0.000 | secondary |  |
| non_specific_rate | 0.000 | secondary |  |
| ndcg_at_G | 0.794 | deferred |  |
| ndcg_at_5 | 0.740 | deferred |  |
| mrr_critical | 0.500 | deferred |  |
| critical_in_top3 | 0 | deferred | all critical flaws (first 3 by key order when more than 3) matched within ranks 1-3 |
| ece | 0.191 | deferred |  |
| brier | 0.082 | deferred |  |
| auroc | 0.912 | deferred |  |
| action_type_accuracy | 0.917 | blocked |  |
| approved_decision_violation_rate | 0.000 | blocked |  |
| bait_resistance | null | blocked | BLOCKED: no sound section has bait = true |
| pooled_recall | null | secondary | no pooled supplementary key G+ exists yet (built from human-confirmed VALID_UNPLANTED after an evaluation round, metrics.md §2.3 step 5; PARTIAL_KEY_MATCH findings are already key flaws and never enter G+) |
| stale_finding_rate | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| resolved_acknowledgement | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| persisted_recall | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| new_flaw_recall | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| copy_through_rate | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| adjudication_counts | INVALID_OPINION: 1, PARTIAL_KEY_MATCH: 2, VALID_UNPLANTED: 3 | secondary |  |
| adv_v2 | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| brier_skill | -0.564 | deferred |  |
| category_label_accuracy | 0.750 | exploratory |  |
| changed_section_coverage | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| citation_precision_lenient | null | secondary | citation judge failed or was incomplete for 1 findings |
| citation_recall | null | deferred | citation judge failed or was incomplete for 1 findings |
| doc_verdict_calibration | null | deferred | the key has no document-level fitness label |
| false_absence_rate | 0.000 | deferred |  |
| false_resolution_rate | null | exploratory | v1 review: re-review metrics apply only to a v2 document |
| fully_sound_doc_accuracy | null | blocked | BLOCKED: this key has flaws (no fully sound control document exists) |
| justified_decline_rate | 0.800 | exploratory | G1 on the sound area's anchors only; G3 is not run on sound-area justifications |
| lenient_adjudication_counts | INVALID_OPINION: 1, VALID_UNPLANTED: 3 | secondary |  |
| lenient_duplication_rate | 0.000 | secondary |  |
| lenient_f1_adjudicated | 0.971 | secondary |  |
| lenient_f1_strict | 0.875 | secondary |  |
| lenient_non_specific_rate | 0.000 | secondary |  |
| lenient_precision_strict | 0.778 | secondary |  |
| location_validity_rate | 0.959 | exploratory | G2 (agent verify_anchor) pass rate |
| overrun | null | deferred | needs per-step working state (not in report.json or manifest.json) |
| read_before_cite_rate | null | secondary | no external citations |
| research_yield | null | deferred | no external sources retrieved |
| selective_precision | 0.5: 0.944, 0.7: 1.000, 0.9: null | deferred | adjudicated precision among findings with confidence >= t (duplicates excluded) |

## Per category (exploratory)

| Category | Gold | Matched | Recall | Agent findings | Precision |
|---|---|---|---|---|---|
| acceptance_criterion_cannot_validate | 1 | 1 | 1.000 | 1 | 1.000 |
| ambiguous_requirement | 1 | 1 | 1.000 | 1 | 1.000 |
| decision_depends_on_pending_item | 1 | 1 | 1.000 | 2 | 0.500 |
| internal_contradiction | 3 | 3 | 1.000 | 5 | 1.000 |
| missing_or_unverifiable_requirement | 2 | 1 | 0.500 | 2 | 1.000 |
| scalability_or_failure_mode | 2 | 2 | 1.000 | 3 | 1.000 |
| security_privacy_gap | 2 | 2 | 1.000 | 2 | 1.000 |
| unsupported_or_incorrect_claim | 2 | 1 | 0.500 | 2 | 1.000 |

## Efficiency (from the run manifest)

**COST AND TOKENS ARE A LOWER BOUND** - unrecorded_usage: 1 model call with unrecorded usage (llm-0002 assess attempt 0, deadline cut, 263.212 s); their tokens and cost are not in the totals, so the recorded cost and tokens are lower bounds

- cost_usd: null
- input_tokens: null
- output_tokens: null
- cached_tokens: null
- cost_usd_lower_bound: 4.715
- input_tokens_lower_bound: 282243
- output_tokens_lower_bound: 122221
- cached_tokens_lower_bound: 62572
- price_table_date: 2026-09-25
- tool_calls: 0
- tool_calls_by_tool: 
- wall_time_s: 424.727
- per_stage_s: assess: 263.282, ingest: 1.857, plan: 113.610, refine: 129.571, research: 0.006, understand: 124.958, verify: 0.013
- stop_reason: code: tool_failure, group: error
- usage_completeness: unrecorded
- usage_reason: unrecorded_usage
- usage_source: manifest extra.model.calls_with_unrecorded_usage
- calls_with_unrecorded_usage:
  - llm-0002 assess attempt 0: deadline cut, wall 263.212 s

## Key flaws

| Flaw | Severity | Strict match | Lenient match | Best median score |
|---|---|---|---|---|
| F01 | critical | FND-029 | FND-029 | 3.000 |
| F02 | low | FND-020 | FND-020 | 3.000 |
| F03 | high | FND-019 | FND-019 | 3.000 |
| F04 | high | - | FND-050 | 2.000 |
| F05 | low | FND-005 | FND-005 | 3.000 |
| F06 | critical | FND-028 | FND-028 | 3.000 |
| F07 | high | - | FND-039 | 2.000 |
| F08 | critical | FND-045 | FND-045 | 3.000 |
| F09 | high | FND-001 | FND-001 | 3.000 |
| F10 | critical | FND-043 | FND-043 | 3.000 |
| F11 | high | FND-044 | FND-044 | 3.000 |
| F12 | low | FND-026 | FND-026 | 3.000 |
| F13 | high | FND-024 | FND-024 | 3.000 |
| F14 | low | FND-036 | FND-036 | 3.000 |

## Findings

| Finding | Rank | Severity | Strict | Class (strict) | Lenient |
|---|---|---|---|---|---|
| FND-001 | 1 | critical | F09 | - | F09 |
| FND-029 | 2 | high | F01 | - | F01 |
| FND-028 | 3 | high | F06 | - | F06 |
| FND-019 | 4 | high | F03 | - | F03 |
| FND-044 | 5 | high | F11 | - | F11 |
| FND-016 | 6 | high | - | VALID_UNPLANTED | - |
| FND-043 | 7 | high | F10 | - | F10 |
| FND-045 | 8 | high | F08 | - | F08 |
| FND-005 | 9 | high | F05 | - | F05 |
| FND-020 | 10 | high | F02 | - | F02 |
| FND-050 | 11 | high | - | PARTIAL_KEY_MATCH (F04) | F04 |
| FND-023 | 12 | medium | - | VALID_UNPLANTED | - |
| FND-024 | 13 | medium | F13 | - | F13 |
| FND-036 | 14 | medium | F14 | - | F14 |
| FND-025 | 15 | medium | - | VALID_UNPLANTED | - |
| FND-052 | 16 | medium | - | INVALID_OPINION | - |
| FND-039 | 17 | medium | - | PARTIAL_KEY_MATCH (F07) | F07 |
| FND-026 | 18 | medium | F12 | - | F12 |

## Failed judge calls

- ground.cite:FND-005: no label for ['EV-052']
