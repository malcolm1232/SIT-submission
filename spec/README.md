# Review output and answer-key specification (v1.0)

This folder resolves two P0 blockers from `research/audit/research_audit.md` §6: "write `taxonomy.yaml`" (action 3, M1) and "write the canonical finding/report schema" (action 4, M2), plus the answer-key schema (M3, C32). Paths are relative to the repo root.

| File | Role | Owner of |
|---|---|---|
| `spec/taxonomy.yaml` | The only enum registry. Definitions, inclusion/exclusion notes and invented examples for every label. Also holds the converter-only `legacy_mappings`. | Kinds, categories, severities, confidence bands, dispositions, verdicts, provenance, stop reasons, decision relations, phases, credit modes, v2 statuses, splits, matcher labels, anchor rules |
| `spec/finding.schema.json` | JSON Schema 2020-12. Root = one hydrated **Finding**; `#/$defs/Review` = the **Review** envelope. | What the agent emits, what the matcher reads, what the grader and robustness oracles validate |
| `spec/answer_key.schema.json` | JSON Schema 2020-12 for one sealed **answer key**. Reuses `Kind`, `Category`, `Severity`, `Disposition` from the finding schema by `$ref`. | What a gold flaw, sound section and still-valid observation look like |
| `spec/validate_examples.py` | Checks enums match `taxonomy.yaml`, validates the examples in this README plus a full Review and a full answer key, runs negative and adversarial tests, runs the INV-04 anchor oracle, and checks that `legacy_mappings` covers every label in the five existing keys. | — |
| `spec/convert_answer_keys.py` | Converts the five legacy keys to `eval/<tier>/<item>/answer_key.canonical.json`, validates each, and prints counts, notes and any field it could not map (§2.8). | — |

**Handling.** `taxonomy.yaml` outside `legacy_mappings` is prompt-safe: its examples are invented and avoid every mechanism in the eval keys. This README and `legacy_mappings` name eval-key labels and some flaw details, and §2.6-2.7 cover the S-heldout (ex-blind) items. Never place either in an agent, matcher or grader prompt. When the S-heldout keys are sealed (audit P0 action 7), move §2.4 rows for item_a/item_b, §2.6 and §2.7 into the sealed archive.

## 1. How the three artefacts relate

```
                    taxonomy.yaml  (enums + definitions; prompt-safe except legacy_mappings)
                    /            \
     finding.schema.json      answer_key.schema.json  ($ref: Kind, Category, Severity, Disposition)
      Finding, Review                 flaws[], sound_sections[], still_valid_observations[]
           |                                   |
  agent  --emits-->  Review.findings[]         |
           |                                   |
  matcher: Finding.statement + doc_anchors  <-> Flaw.core_insight + credit + location   (metrics.md §2)
  adjudicator: unmatched findings -> DUPLICATE / VALID_UNPLANTED / ... ; still_valid_observations pre-adjudicate VALID_UNPLANTED
  grader: whole Review (Pass A uses kind, disposition, recommendation, evidence; Pass B uses verdict, intent_summary, unresolved)
  oracles: Review validates (INV-03); anchors resolve against documents[].text_path (INV-04); evidence_id in ledger, external
           ledger entries resolve to an ok research_log.tool_calls[] entry, no free-text URL outside the ledger (INV-05);
           recommendation complete (INV-06); every degradation id cited by a limitations[] entry, fallbacks and cap stops
           recorded as degradations (INV-07); manifest complete incl. review_config and fault_schedule_id (INV-09);
           registry hash constant across iterations, challenges labelled (INV-10)
```

Key design choices:

- **Two orthogonal axes** (audit C7). `kind` is the lab §2.3 review category (strength, risk, gap, ambiguity, unresolved_assumption, validation_need). `category` is the defect mechanism (9 codes + `other`). Domain words go in free `tags`.
- **One severity scale**: critical / high / medium / low, weights 8/4/2/1 (sensitivity 4/3/2/1). Strengths have `severity: null`.
- **Confidence** is one number in [0, 1] (needed for ECE/Brier/AUROC, metrics §7.1). Verbal bands (high ≥ 0.8, medium ≥ 0.5, low) are derived, never emitted, and each band has an evidence anchor (high needs ≥ 2 independent sources or one primary source, robustness ADV-14).
- **Disposition** (lab §3.2): `refinement_now`, `needs_investigation`, `needs_prototyping`, `needs_testing`, `governance_decision`, `no_change`. One primary value plus `secondary_dispositions[]`. Non-refinement dispositions need `next_step {owner, action}`. `no_change` forbids a recommendation and requires `no_change_rationale` (lab §2.3 "explain why the existing design remains appropriate").
- **Traceability**: 1-3 `doc_anchors` per finding (audit G1, G3), each with `doc_id`, `section_ref`, `requirement_ids`, a verbatim `quote` of ≥ 8 tokens (G2) and `page`.
- **Evidence by ledger ID** (audit C11). The model writes `evidence_id`, `source_type`, `quote`, `supports_claim`; the renderer copies `url_or_citation` and `retrieved_at` from the ledger (these are `readOnly` in the schema). Every evidence item is tagged `doc | external | inference` (C10); inference must list `derived_from`.
- **Approved decisions** live in `Review.decision_registry[]` (robustness §10 item 5). A finding lists `affected_decisions[]` with relation `preserves | refines | challenges`; `challenges` requires ≥ 2 evidence items and a non-`no_change` disposition (BEH-12, INV-10).
- **Cross-field rules** that JSON Schema cannot express are enforced in code (`review_semantics`, `key_semantics` and `anchors_resolve` in `validate_examples.py`, reused by the verify stage and by `convert_answer_keys.py`): every `evidence_id` and `derived_from` is in the ledger and hydrated from it; `supporting_evidence_ids` is a subset of the finding's evidence and never cites contrary (`supports_claim: false`) evidence; doc and external evidence quotes occur in the ledger excerpt; anchor pages are within `page_count`; external ledger entries resolve to an `ok` tool call of the same server and tool; `tool_calls_by_tool` equals the counted `tool_calls`; no URL or DOI appears in report text unless it is a ledger `url_or_citation`; every degradation is cited by a limitation, each fallback event and each cap or tool-failure stop has a degradation; `registry_sha256_by_iteration` is constant and equals the sha256 of the canonical JSON (sorted keys, no whitespace, UTF-8) of `decision_registry`; anchor `doc_id`s exist in `metadata.documents`; every finding needing investigation, prototyping, testing or governance appears in `unresolved[]` (lab §2.4); `stop_reason.group` matches the taxonomy; key overlap and regression links are mirrored; `v2.expected_open_flaw_ids` equals the derived set; a `scored_run_ready` key has no null provenance, `core_insight`, `anchor_quote` or `expected_disposition`.
- **Re-review** (lab §1.5): `metadata.review_mode = delta` requires a non-null `prior_review_id`, a document with `role: prior_version`, and a `reassessment {prior_finding_id, status}` on every finding; a `full` review has none of the three (schema-enforced).

### Grader-facing projection

`research/grading/grader_prompt.md` §1 forbids putting the agent's model name or tool traces into any grader input. The harness therefore renders grader inputs from a projection of the Review that drops `run_manifest`, `research_log`, every `provenance` block, `evidence_ledger[].tool` / `snapshot_path`, `metadata.review_id` and `run_id`, and `stop_reason.detail`. `{{EVIDENCE_REGISTER}}` is the projected ledger, `{{SHUFFLED_FINDINGS_WITH_IDS}}` uses `Finding.id` (`FND-nnn`) verbatim (the segmenter is only for unstructured reviews), and the key-aware projection of an answer key maps `flaws[]` to `key_items` (`id` = `FlawId`, `title` = `title` or else `description`, since synthetic and item_b flaws have no title; `locations` from `location.sections` and `page`; `category` = `kind`, `materiality` per `legacy_mappings.severity.grading_materiality`, `expected_triage` = `expected_disposition`), `sound_sections[].trap` to `traps` with `trap_id` = the sound-section `id`, and `sound_sections` to `no_change_areas`.

### LLM-facing schema

Claude structured outputs reject numeric and string-length constraints and any `additionalProperties` other than `false` (`research/frameworks/comparison.md` §1). The agent therefore sends a **derived** schema, generated in code from `#/$defs/Finding`, which:

1. drops every `readOnly` property (`url_or_citation`, `retrieved_at`);
2. strips `minLength`, `maxLength`, `minimum`, `maximum`, `minItems`, `maxItems`, `pattern`, `format` and the `allOf` if/then rules.

The verify stage then hydrates evidence from the ledger and validates the result against the **full** canonical schema; a failure triggers one repair attempt. Which other keywords the API accepts (for example `pattern`, `anyOf` with `null`) is **UNVERIFIED**; check it at build time and strip less if possible.

## 2. Mapping from the five existing answer keys

`taxonomy.yaml → legacy_mappings` is the machine-readable copy of §2.4-2.5 and is authoritative if the two disagree. "Pending" means the converter writes `null` (or `[]`) and adds the name to `authoring_status.pending`; `scored_run_ready` stays `false` until a human fills it. Keys under `eval/` are not modified by this spec; a converter writes new files.

### 2.1 Top-level fields

| Canonical | payments_orchestration | clinical_rpm | research_lakehouse | blind/item_a | blind/item_b |
|---|---|---|---|---|---|
| `schema_version` | "1.0" | "1.0" | "1.0" | "1.0" | "1.0" |
| `item.item_id` | `item_id` | `item_id` | `item_id` | `item_id` | `item_id` |
| `item.split` | `S-dev` | `S-dev` | `S-dev` | `S-heldout` (audit §4.3) | `S-heldout` |
| `item.domain` | `domain` | `domain` | `domain` | `domain` | `domain` |
| `item.documents.v1 / v2` | `design_v1.md` / `design_v2.md` (+ sha256) | same | same | `document` / `null` | `document` / `null` |
| `item.document_id` | `null` | `null` | `null` | `null` | `document_id` |
| `item.notes` | `version_notes` | `version_notes` | `version_notes` | `readme_notes_moved_at_sealing` | `readme_notes_moved_at_sealing` |
| `item.canary_guid` | `null` + pending (assigned per split when the canary is embedded in the documents) | same | same | same | same |
| `item.author_type / author_model / generation_date` | `unknown` / `null` / `null` + pending (U11) | same | same | same | same |
| `item.source_key` | `{path, format: synthetic_json_v0, sha256}` | same | same | `blind_a_json_v0` | `blind_b_json_v0` |
| `scoring.default_credit_mode` | `substance` | `substance` | `all_of` (items 1-2 `required`, the legacy "first two" rule) | `all_of` | `all_of` |
| `scoring.severity_mapping.source_scale` | `synthetic3` | `synthetic3` | `synthetic3` | `blind4_capitalised` | `blind4` |
| `scoring.severity_tolerance` | `null` | `null` | `null` | `null` | `1` |
| `scoring.notes` | README "by substance" rule (superseded) | `scoring_guidance` | `version_notes` "first two" rule (superseded) | "Scoring guidance" section of `readme_notes_moved_at_sealing` | `scoring_guidance` |
| `flaws[]` | `flaws` (F15 inside since the eval fixes; legacy `v2_new_flaws` still accepted) | `flaws` | `flaws` (as payments) | `defects` | `defects` |
| `sound_sections[]` | `sound_sections` | `sound_sections` | `sound_sections` | `deliberately_sound_sections` | `deliberately_sound_sections` |
| `still_valid_observations[]` | eval-audit P2 #14 items (verbatim, origin `eval_audit`; section-specific ones go on that sound section) | same | same, plus sound §16 `still_valid_observations` | eval-audit P2 #14 | `non_keyed_observations_acceptable_but_not_required` (origin `key_author`) |
| `v2.expected_open_flaw_ids` | computed; converter asserts it equals `expected_v2_open_flaws` | computed | computed | `v2: null` | `v2: null` |
| `v2.changed_sections` | `[]` + pending `v2_changed_sections`; the verbatim revision-history text goes in `v2.notes` | same | same (from "Changes since version 1.0") | — | — |
| `approved_decisions[]` | `[]` + pending | same | same | same | same |
| dropped (recomputed; converter asserts equality) | `flaw_counts` | `category_counts_v1` | — | `defect_count`, `severity_scale`, `category_taxonomy` | `defect_count`, `severity_scale` |

### 2.2 Per-flaw fields

| Canonical | synthetic (all three) | blind/item_a | blind/item_b |
|---|---|---|---|
| `id` | `id` | `id` | `id` |
| `title` | `null` | `title` | `null` |
| `kind`, `category` | from §2.4 via `category` | §2.4 (with D04/D12 overrides) | §2.4 |
| `acceptable_kinds` | `taxonomy.categories[category].acceptable_kinds` | same | same |
| `tags` | `[]` | `[category]` (verbatim) | `[category]` (verbatim) |
| `severity` / `severity_source` | §2.5 primary / `{synthetic3, label}` | §2.5 / `{blind4_capitalised, label}` | §2.5 / `{blind4, label}` |
| `planted` | `true` | `true` | `true` |
| `introduced_in` | `introduced_in` or `"v1"` | `"v1"` | `"v1"` |
| `introduced_by_fix_of` | `introduced_by_fix_of`; for clinical F15, the `flaw_id` of the `v2_changes` entry whose `new_flaw_id` = F15 (→ F10) | `null` | `null` |
| `v2_status` | `v2_changes[flaw_id].status` (legacy `regressed` → `fixed`); v2-only flaws → `introduced` | `not_applicable` | `not_applicable` |
| `caused_regression_flaw_id` | `v2_changes[].introduced_new_flaw_id` (legacy `new_flaw_id`) | `null` | `null` |
| `v2_note` | `v2_changes[].note` | `null` | `null` |
| `location.sections` | `section_refs` (verbatim strings) | `location.sections` | `location.sections` |
| `location.requirement_ids` | `requirement_ids` | `location.requirement_ids` | `location.requirement_ids` |
| `location.decision_ids` | IDs matching `^D(EC)?-\d+$` moved out of `requirement_ids` | same rule | same rule |
| `location.anchor_quote`, `page` | pending | pending | pending |
| `description` | `description` | `description` | `description` |
| `rationale` | `why_it_is_a_flaw` | `why_it_matters` | `why_it_matters` |
| `core_insight` | pending (derive from required credit items; second reviewer, L12) | pending | pending |
| `credit.mode` | payments, clinical `substance`; lakehouse `all_of` | `all_of` | `all_of` |
| `credit.items` | `what_a_correct_finding_must_mention[i]` → `c{i+1}`, role `required`, except text starting "(supporting" and lakehouse items 3+ → `supporting` | `credit_requires` (string) → one item `c1`, `required` | `credit_requires[i]` → `c{i+1}`, `required` |
| `credit.min_required` | `null` | `null` | `null` |
| `needs_external_research` | `true` for the flaws eval_data_audit Task 1 checked as external facts (payments F01 F04 F06 F07 F11 F15; clinical F01 F03 F04 F06 F07 F08 F09 F11 F15; lakehouse F04 F05 F06 F10 F15), else `false` | `requires_external_fact` | `external_fact` not null/"None" |
| `external_fact` | when needed: `claim` = `why_it_is_a_flaw` (placeholder: restate as the external fact during verification), `source` = URLs in `distractor_notes` or "unspecified in legacy key", `verified: false`, pending `external_fact_verification` | split `external_fact` at the first ": " → `source`, `claim` when the head is ≤ 150 characters; otherwise `claim` = whole string and `source` = "unspecified in legacy key (citation embedded in claim)"; `verified: false` + pending | same as item_a |
| `expected_disposition`, `acceptable_dispositions` | pending / `[]` | pending / `[]` | pending / `[]` |
| `affected_decisions` | `[]` (filled with `approved_decisions`) | `[]` | `[]` |
| `acceptable_fix` | `acceptable_recommendation` | `acceptable_fix` | `acceptable_fix` |
| `distractor_notes` | `distractor_notes` | `null` | `null` |
| `overlapping_sound_section_ids` | §2.7 | §2.7 | §2.7 |
| `disambiguation` | `disambiguation` (added by the eval fixes) | same | same |

Sound sections: synthetic `{section_ref, why_sound, trap}`, item_a `{location, why_sound, careless_flag}`, item_b `{section, why_sound, likely_false_positive}` (all may carry `disambiguation`; lakehouse §16 carries `still_valid_observations`) → `{id: S01.. in legacy order, location.sections: [verbatim string], why_sound, trap, disambiguation}`. Requirement and decision IDs are extracted from the string with `[A-Z]{1,4}(-[A-Z]+)*-\d+`. `applies_to_versions`: synthetic `["v1","v2"]` (lakehouse §9 WAP: `["v1"]`, eval-audit Task 6), blind `["v1"]`. `bait: false`. Splitting multi-section strings into separate entries is part of pending `sound_overlap_annotations`.

### 2.3 Research-note vocabularies

| Source | Field | Canonical |
|---|---|---|
| `methodology/metrics.md` §1 | `category` RISK/GAP/AMBIGUITY/UNRESOLVED_ASSUMPTION/VALIDATION_NEED | `kind` of the same name (lower case) |
| | INCONSISTENCY / UNSUPPORTED_OR_INCORRECT_CLAIM / OTHER | `kind: risk` + `category` internal_contradiction / unsupported_or_incorrect_claim / other |
| | `kind` assumption / inconsistency / incorrect_claim | unresolved_assumption / risk + internal_contradiction / risk + unsupported_or_incorrect_claim |
| | `claim`, `location[]`, `evidence[].ref`, `action_type`, `doc_verdict`, `section_verdicts` | `statement`, `doc_anchors[]`, `evidence[].evidence_id` (ledger), `disposition`, `verdict`, `sound_areas[]` |
| | `recommendations[]` (separate list, `finding_ids`) | `recommendation` embedded in its finding (one per finding; a cross-cutting recommendation is a finding of its own) |
| `grading/grader_prompt.md` §5.1 | Pass A `category` (incl. `no_change`) | `kind`; `no_change` → `disposition: no_change` |
| | `triage.review_label` | `disposition` (+ `secondary_dispositions` for `mixed`, `none` → `no_change`) |
| | `materiality` | grader-only; ≈ high→{critical, high}, medium→medium, low→low |
| grading illustrative key (§6) | `key_items / traps / no_change_areas`, `expected_triage` | `flaws / sound_sections[].trap / sound_sections`, `expected_disposition` |
| `robustness/scenarios.md` | BEH-16 `remedy_type`; ADV-14 `validation/prototype`; BEH-17 `source`; BEH-12 `challenges_decision: D-x` | `disposition`; `needs_prototyping`; `evidence[].source_type`; `affected_decisions[{relation: challenges}]` |
| verdict | yes / partly / no; `fit_with_refinements` | fit / fit_with_conditions / not_fit; fit_with_conditions (`not_assessed` has no legacy source: it is set by the agent's code) |
| stop reason | `budget`; `other`; agent decision / cap / error | budget_tool_calls or budget_tokens; error; `group` decision / cap / error |

### 2.4 Category → (category, kind)

| Legacy label | Key(s) | Canonical category | Kind |
|---|---|---|---|
| internal_contradiction | synthetic ×3 | internal_contradiction | risk |
| unjustified_quantitative_claim | synthetic ×3 | unsupported_or_incorrect_claim | risk |
| missing_or_unverifiable_requirement | synthetic ×3 | missing_or_unverifiable_requirement | gap |
| security_privacy_gap | synthetic ×3 | security_privacy_gap | gap |
| scalability_failure_mode | synthetic ×3 | scalability_or_failure_mode | risk |
| ambiguous_requirement | synthetic ×3 | ambiguous_requirement | ambiguity |
| acceptance_criterion_cannot_validate | synthetic ×3 | acceptance_criterion_cannot_validate | validation_need |
| decision_depends_on_pending_item / `_pending_backlog` (clinical) | synthetic ×3 | decision_depends_on_pending_item | unresolved_assumption |
| Regulatory compliance | item_a | external_constraint_violation | risk |
| Functional logic / internal inconsistency | item_a | internal_contradiction | risk |
| Data model and platform limits | item_a | external_constraint_violation (D04 → unsupported_or_incorrect_claim; D12 → scalability_or_failure_mode) | risk |
| Messaging and scalability | item_a | scalability_or_failure_mode | risk |
| Consistency and reliability | item_a | scalability_or_failure_mode | risk |
| Idempotency and financial integrity | item_a | scalability_or_failure_mode | risk |
| Security | item_a | security_privacy_gap | gap |
| Privacy and data governance | item_a | security_privacy_gap | risk |
| Availability and NFR feasibility | item_a | internal_contradiction | risk |
| Rollout and rollback | item_a | scalability_or_failure_mode | risk |
| Testability and acceptance | item_a | acceptance_criterion_cannot_validate | validation_need |
| safety / safety-function architecture | item_b | scalability_or_failure_mode | risk |
| safety / failure-mode behaviour | item_b | scalability_or_failure_mode | risk |
| external standard / grid safety | item_b | unsupported_or_incorrect_claim | risk |
| external protocol limit / interface feasibility | item_b | external_constraint_violation | risk |
| external standard / compliance | item_b | unsupported_or_incorrect_claim | risk |
| security / external standard | item_b | security_privacy_gap | risk |
| internal inconsistency / timing infeasibility | item_b | internal_contradiction | risk |
| arithmetic / capacity sizing | item_b | unsupported_or_incorrect_claim | risk |
| arithmetic / requirement not met | item_b | unsupported_or_incorrect_claim | risk |
| internal inconsistency / contractual constraint | item_b | internal_contradiction | risk |
| security architecture | item_b | security_privacy_gap | risk |
| time synchronisation / requirement not achievable | item_b | unsupported_or_incorrect_claim | risk |
| verification gap | item_b | acceptance_criterion_cannot_validate | validation_need |
| planning / dependency sequencing | item_b | decision_depends_on_pending_item | unresolved_assumption |

### 2.5 Severity

| Scale | Labels | Primary mapping | Sensitivity mapping |
|---|---|---|---|
| `synthetic3` (3 synthetic keys) | critical, major, minor | critical, **high**, **low** | critical, high, **medium** |
| `blind4_capitalised` (item_a) | Critical, High, Medium, Low | lower-case identity | — |
| `blind4` (item_b) | critical, high, medium, low | identity | — |

The key stores the **primary** value in `severity` and the verbatim label in `severity_source`, so SWR can be recomputed under the sensitivity mapping and both weight schemes (audit L14).

### 2.6 Credit-item role overrides (content fixes from eval_data_audit P0 #4)

`research/audit/eval_fixes_applied.md` has since applied the four flaw-level rows below to the legacy keys themselves (clinical F06 remedy removed, F11 item 4 prefixed "(supporting, not required)", F04 merged, item_b DEF-12 remedy removed). The converter therefore applies only the lakehouse rule and the "(supporting" prefix rule; the rows are kept as history.

| Item / flaw | Change |
|---|---|
| research_lakehouse, every flaw | items 1-2 `required`, items 3+ `supporting` (makes the README "first two" rule explicit instead of order-dependent) |
| clinical_rpm F06 | item 3 (a remedy) → `supporting` |
| clinical_rpm F11 | item 4 ("silent: data still appears in ADX") → `supporting` |
| clinical_rpm F04 | merge the "claim is false" and "consequence" items into one `required` item (manual edit) |
| blind/item_b DEF-12 | item 2 (must recommend GNSS/PTP/IRIG-B) → `supporting` |

Other content fixes the eval audit requires are **not** mechanical and need a second reviewer: item_a D01 `external_fact` and credit (UK reg. 34(5) vs 34(6)); lakehouse sound §16 `why_sound` and trap; item_b DEF-03 tolerance ("2 s unless otherwise agreed with the utility"); optional payments F05 minor → major.

### 2.7 Overlap annotations (eval_data_audit Task 6 / P1 #9)

| Item | Sound section | `overlapping_flaw_ids` |
|---|---|---|
| clinical_rpm | §4 (4.2/4.3) | F05, F06 |
| research_lakehouse | §4 Data Classification | F01 |
| research_lakehouse | §14.6 latency | F05 |
| research_lakehouse | §16 Audit Plane | F08 |
| research_lakehouse | §9 WAP (v1 only) | F15 |
| blind/item_a | 3.1.3 FR-RET-01 | D03 |
| blind/item_b | 7.5 timeline arithmetic | DEF-03, DEF-13 |
| blind/item_b | FR-GRID-01 / 7.4 | DEF-14 |
| blind/item_b | 5.5, 7.9 and D-02 (hot-standby pair) | DEF-02 (disambiguation added to the key on 2026-10-02 after this table was first written) |

The converter writes the reverse links into `flaws[].overlapping_sound_section_ids`, and reports any `disambiguation` note that has no row here. Clinical F06 is listed because the §4 trap names it, not because it shares a location (F06 cites 2.1 and 20).

### 2.8 Converter

`python3 spec/convert_answer_keys.py` (add `--check` to validate without writing) reads each legacy key, applies §2.1-2.7, validates the result against `answer_key.schema.json` and `key_semantics`, writes `answer_key.canonical.json` next to the legacy key, and prints per-key counts, notes (count assertions, partial mappings) and every legacy field it could not map. It never edits `answer_key.json`. Every output has `scored_run_ready: false` until the pending fields are authored and second-reviewed.

`--tier synthetic` converts only the S-dev items; the spec self-test the converter runs on import then expands its `eval/*/*/answer_key.json` glob without listing or opening anything under `eval/blind` (SEALING.md §6 rule 1). `--verify-anchors` checks every flaw and approved-decision `anchor_quote` as an exact match, on the stated page, in the PDF text from the agent's own ingest (`sit_review_agent.ingest.pdf.ingest`); a v2-only flaw (`introduced_in: v2`) is checked against `design_v2.pdf`, everything else against `design_v1.pdf`.

### 2.9 Agent drafts and owner sign-off

Pending judgement fields may be drafted by an agent session (human_labelling_protocol.md T3: "a Claude session drafts each `core_insight`"). The drafts live in the legacy key under a top-level `authoring_drafts` block (`item` provenance, per-flaw `core_insight` / `anchor_quote` / `anchor_page` / `expected_disposition` / `acceptable_dispositions` / restated `external_fact`, `approved_decisions[]`, sound-section splits, `v2_changed_sections`, and a `signoff` record). The converter copies them into the canonical key and records them in the optional `authoring_status.drafts {drafted_by, drafted_on, fields[], note}`:

- Every field in `drafts.fields` also stays in `pending`, so `scored_run_ready` stays `false` (the converter rejects a `drafts.fields` that is not a subset of `pending`; the schema rejects `scored_run_ready: true` with a non-empty `drafts.fields`).
- Provenance facts read from the session record (`author_type`, `author_model`, `generation_date`) leave `pending` when set. `canary_guid` leaves it only when `canary_embedded_in_documents` is true or the owner accepts it.
- The owner signs by filling `authoring_drafts.signoff {signed_by, signed_on, accepted[]}` and re-running the converter. Accepted fields leave `pending` and `drafts.fields`, the signer is added to `item.key_reviewed_by` (this is the second review of RA L12, so `key_second_review` is accepted the same way), and `scored_run_ready` becomes `true` exactly when `pending` is empty. The review sheet for the S-dev keys is `eval/KEY_SIGNOFF.md`.
- For a flaw with `introduced_in: v2`, `location.anchor_quote` and `location.page` refer to `design_v2`.
- A key that comes out `scored_run_ready: true` always has its anchor quotes checked against the agent's ingest, as with `--verify-anchors`; if the agent package cannot be imported, that key fails. With `--check`, a canonical key on disk that says `scored_run_ready: true` but differs from the key regenerated from `answer_key.json` fails (a hand edit or a stale file). The schema alone cannot tell a hand-set `true` from a converter-set one.
- The sign-off is not tied to the draft text: an edit to `authoring_drafts` after signing keeps the key signed. Sign last, and re-sign (new `signed_on`) after any later edit.

## 3. Conflicts resolved (research_audit.md §1.1)

**C4 (two recall instruments).** Recall comes only from the methodology matcher. The answer key's `scoring.matching_rule` is the constant `core_insight_plus_location_v1`, and the grader's key-aware Pass B has no field in either schema to report recall from. Adopted as recommended.

**C5 (five matching rules).** Every flaw is matched by methodology's rule: one-to-one, core insight stated, location compatible, labels ignored. The task also asked for a per-flaw `credit.mode`. It does not create a second rule; it says how the core insight is checked. `substance` judges the `core_insight` sentence as a whole. `all_of` means every `required` item must be stated. `any_of` means at least `min_required` items must be stated. Lakehouse's order-dependent "first two" rule becomes explicit `required`/`supporting` roles. Adopted, with that reconciliation.

**C6 (severity scales).** The canonical scale is critical/high/medium/low, with weights 8/4/2/1 and a sensitivity variant of 4/3/2/1. Synthetic labels are pre-registered as major→high and minor→low, with minor→medium as the sensitivity variant. The task suggested critical/major/minor/info. I did not use it, for three reasons: the audit argues for the methodology scale; metrics §0 weights and both blind keys already use it; and "info" has no defect meaning, because strengths and no-change findings carry `severity: null` instead. The eval-data audit wanted verbatim labels with mapping deferred to scoring time. The key covers both: the mapped value is in `severity` and the original is in `severity_source`.

**C7 (five category taxonomies).** The taxonomy has two orthogonal axes: `kind` (lab §2.3) and `category` (defect mechanism). Every legacy label maps to both (§2.4). Domain labels are kept as `tags`. The clinical `_pending_backlog` spelling is aliased. This follows the audit, except that the mechanism list has 9 codes rather than 8 (deviation D3 below).

**C8 (triage enum).** Grading's enum is kept, but `mixed` and `none` are not values. `mixed` becomes a primary disposition plus `secondary_dispositions[]`. A bare "mixed" says nothing about which action comes first, and action-type accuracy needs a single gold value to compare against. `none` becomes `no_change`. `testing` is kept (lab §3.2). The key gains `expected_disposition`. Until a person authors it, BEH-16 and action-type accuracy remain BLOCKED, as the audit says.

**C9 (verdict vocabulary).** The labels are fit / fit_with_conditions / not_fit. `fit_with_conditions` requires at least one condition linked to a finding (grader D2). Adopted. Added on 2026-10-03: a fourth label, `not_assessed`, for a run that produced no assessment (the deadline skipped or cut the assess stage, or the model declined it). It replaces the earlier placeholder (`not_fit` at confidence 0), which read as a judgement of the design. It is set by code only: the LLM-facing verdict schema offers the three fitness labels, never this one. The schema requires confidence 0, no conditions, no per-objective labels, no findings, no sound areas and at least one degradation (which INV-07 ties to a limitation); a per-objective label can never be `not_assessed`. The grader does not count it as an explicit verdict (gate G4), and the scorer flags the run and counts it intention-to-treat.

**C10 (provenance tag).** Every evidence item carries one of `doc | external | inference`. Inference must name what it is derived from, so the agent's reasoning cannot pass as document content. Adopted.

**C11 (how external evidence is cited).** Evidence is cited by ledger ID only. `url_or_citation` and `retrieved_at` are `readOnly` and are filled in by the renderer. The ledger records `read_before_cite`. Adopted.

**C12 (stop reasons).** The enum is the union of the three lists, and each value carries a `group` (decision / cap / error, per L40). Adopted.

**C13 (doc anchoring).** Each anchor carries a quote, page and section inside the structured output. Native citations are never part of the scored output. The canonical page-marked text is identified by `documents[].sha256_text`, which also fixes the anchoring half of C14. Adopted.

**C15, C16, C28 (sampling, silent fallback, model pinning).** The manifest has no `temperature` or `seed` fields. It records `thinking`, `effort`, `max_tokens`, `betas` and `sampling` per role, plus `served_models[]` and `fallback_events[]`. `provenance.model` is the served model ID, not the alias. Adopted.

**C26 (unkeyed valid findings).** Methodology's rule is used. A finding that matches a `still_valid_observations` entry is pre-adjudicated VALID_UNPLANTED: it counts as correct for adjudicated precision, is excluded from recall, and is never a sound-section false positive. This replaces the blind READMEs' "neither rewarded nor penalised" rule.

**C32 (six answer-key formats).** There is one `answer_key.schema.json` (§2 is the converter spec). Clinical's F15 and the other keys' `v2_new_flaws` both become `flaws[]` entries with `introduced_in: v2`. The legacy `regressed` status becomes `fixed` plus `caused_regression_flaw_id`, which also fixes the eval audit's "5 vs 6 fixed" tally. Adopted.

**U11 (who generated each item).** `author_type`, `author_model`, `generation_date`, `generator_session_ref` and `brief_sha256` are required fields. They may be `null` only while listed in `authoring_status.pending`, so the missing provenance shows up mechanically rather than being forgotten.

**G1-G3 (gameable locations).** Each finding has 1 to 3 anchors, and each quote has at least 8 tokens. The verify stage fuzzy-matches the quote within the cited section ±1. Adopted.

**§1.2 items 3, 5, 8 (ledger, registry, explain).** `Review.evidence_ledger[]` and `Review.decision_registry[]` are first-class. Stable `FND-`/`EV-`/`AD-` IDs make `explain <finding_id>` a join over the Review.

The remaining conflicts are out of scope for a schema, but each now has a recorded disposition so none is silently dropped (added by `research/audit/verify_spec.md`):

| Conflict | Owner | Hook in this spec |
|---|---|---|
| C1 rubric scale, C2 grader-validity tiers, C3 judge family, C27 pairwise debiasing | grading / `prereg.yaml` / ADR-003 | none needed; grader inputs come from the grader-facing projection (§1) |
| C14 extractor | architecture | `documents[].sha256_text` + `text_path` and `run_manifest.extractor{name, version, page_marker}` fix *which* text every verifier reads; the extractor choice itself stays open |
| C17 checkpoint/resume, C18 plan-then-execute, C23 demo timings | architecture / runbook | `research_log.tool_calls[].status: blocked` records URL-policy refusals (C18) |
| C19 blind set use | methodology | `Split` has `Blind` (single use), `S-heldout` (ex-blind items) and `rehearsal` |
| C20 overfitting gap, C21 sample sizes | `prereg.yaml` | `run_manifest.prereg_sha256`, `split`, `condition` |
| C22 sound control docs | eval authoring | a key may have `flaws: []` with `sound_sections` only |
| C24 cross-vendor swap, C29 reader sub-agents | config | `run_manifest.models_used[]` per `role`, with `requested_model` vs `served_models` (discloses within-family A4) |
| C25 grader cost, C30 token workload | cost model | `run_manifest.usage{input_tokens, output_tokens, cached_tokens, cost_usd, price_table_date}` |
| C31 matcher on the robustness critical path | methodology | `taxonomy.match_scores` and `adjudication_classes` give the matcher's labels; P_adj itself is defined in `metrics.md` |

## 4. Deviations from the audit's recommendations

| # | Audit said | This spec | Why |
|---|---|---|---|
| D1 | C8: use grading's triage enum (includes `mixed`, `none`) | `mixed` → `secondary_dispositions[]`; `none` → `no_change` | A single gold value is needed for action-type accuracy; "mixed" hides the primary action. |
| D2 | M1: file at `eval/schema/taxonomy.yaml` | `spec/taxonomy.yaml` | The task restricted writes to `spec/`. Move it when the eval tree is reorganised. |
| D3 | C7: axis 2 = the synthetic set's 8 labels + OTHER | 9 mechanisms + `other`. Added `external_constraint_violation`. Renamed `unjustified_quantitative_claim` → `unsupported_or_incorrect_claim` and `scalability_failure_mode` → `scalability_or_failure_mode`, keeping the old names as aliases. | 4 of the 28 blind flaws (statutory rules, a protocol limit, a platform quota) are design choices that break an external constraint without any quantitative claim. Under the 8 labels they would land in `other`. The renames widen the definitions to cover the non-numeric claims and the failure modes in the blind keys. |
| D4 | C5: one methodology rule; no per-item rules | One rule, plus a per-flaw `credit.mode` that only operationalises `core_insight` | The task requires `credit_mode`. Kept consistent with C5 as described in §3. |
| D5 | Task brief: critical/major/minor/info | critical/high/medium/low | As argued in C6 above. |

## 5. Examples

Both validate against `spec/finding.schema.json` (`validate_examples.py` extracts them from this file).

A strength with `disposition: no_change`:

<!-- example:finding:no_change -->
```json
{
  "id": "FND-007", "rank": 2, "kind": "strength", "category": null, "severity": null, "confidence": 0.85,
  "disposition": "no_change", "secondary_dispositions": [],
  "title": "Accessibility is verified, not just promised",
  "statement": "NFR-7 (WCAG 2.2 AA) is backed by an acceptance criterion that combines automated checks with a manual screen-reader pass on every booking screen, so the accessibility objective is verifiable as written.",
  "doc_anchors": [{"doc_id": "DOC-booking-v1", "section_ref": "11.3", "requirement_ids": ["NFR-7", "AC-12"],
                   "quote": "Every booking screen is tested against WCAG 2.2 level AA with automated checks and a manual screen-reader pass.", "page": 18}],
  "evidence": [{"evidence_id": "EV-004", "source_type": "doc", "url_or_citation": "doc:DOC-booking-v1#p18/s11.3",
                "quote": "Every booking screen is tested against WCAG 2.2 level AA with automated checks and a manual screen-reader pass.",
                "supports_claim": true, "retrieved_at": null, "derived_from": []}],
  "recommendation": null,
  "no_change_rationale": "Automated checks alone miss screen-reader problems; the manual pass covers them and the criterion is traced to NFR-7. More tooling would not change the outcome.",
  "next_step": null,
  "affected_decisions": [{"registry_id": "AD-002", "relation": "preserves", "justification": "Affirms decision D-3 (front end built from the campus design-system components)."}],
  "acknowledged_in_doc": false, "tags": ["accessibility"], "reassessment": null,
  "provenance": {"phase": "verify", "iteration": 1, "model": "claude-opus-5-5",
                 "prompt_hash": "3f1c0e5a9b7d2c4e6f8a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e"}
}
```

A risk with a recommendation:

<!-- example:finding:recommendation -->
```json
{
  "id": "FND-001", "rank": 1, "kind": "risk", "category": "unsupported_or_incorrect_claim", "severity": "high", "confidence": 0.9,
  "disposition": "refinement_now", "secondary_dispositions": ["needs_testing"],
  "title": "E-mail plan cannot send peak-day reminders",
  "statement": "Section 6.2 states the e-mail service has no daily sending limit, but its published plan allows 2,000 messages a day, below the 5,000 reminders the design sends on exam-week peak days, so most reminders are rejected and FR-9 ('every booking gets a reminder one hour before') fails.",
  "doc_anchors": [{"doc_id": "DOC-booking-v1", "section_ref": "6.2", "requirement_ids": ["FR-9"],
                   "quote": "The selected e-mail service has no daily sending limit, so reminders are sent individually as each slot approaches.", "page": 11}],
  "evidence": [
    {"evidence_id": "EV-011", "source_type": "external", "url_or_citation": "https://docs.example-mail.invalid/plans#limits",
     "quote": "The Starter plan allows up to 2,000 messages per day.", "supports_claim": true,
     "retrieved_at": "2026-10-02T09:14:00Z", "derived_from": []},
    {"evidence_id": "EV-012", "source_type": "inference", "url_or_citation": "inference:EV-012",
     "quote": "5,000 peak-day reminders (section 4.1) exceed the 2,000-per-day plan limit.", "supports_claim": true,
     "retrieved_at": null, "derived_from": ["EV-011", "EV-005"]}
  ],
  "recommendation": {
    "issue": "The reminder design depends on a sending limit the chosen plan does not provide.",
    "rationale": "Reminders over the daily quota are rejected, so the plan, not the design, decides which students get reminders.",
    "expected_benefit": "FR-9 holds on peak days: every booking receives its reminder.",
    "change_summary": "In 6.2, state the plan's quota and either move to a plan with at least 10,000 messages a day or send overflow reminders as campus-app push notifications.",
    "objective_refs": ["FR-9"], "supporting_evidence_ids": ["EV-011", "EV-012"],
    "verification": "Peak-day load test: 5,000 reminders in one day, all delivered."
  },
  "no_change_rationale": null,
  "next_step": {"owner": "Build Phase 2 test lead", "action": "Add the peak-day reminder load test traced to FR-9."},
  "affected_decisions": [], "acknowledged_in_doc": false, "tags": ["notifications"], "reassessment": null,
  "provenance": {"phase": "research", "iteration": 2, "model": "claude-opus-5-5",
                 "prompt_hash": "9a8b7c6d5e4f30211203f4e5d6c7b8a99a8b7c6d5e4f30211203f4e5d6c7b8a9"}
}
```

`validate_examples.py` also builds a complete `Review` around these two findings and a complete answer key (a v1 flaw whose fix introduced a v2 regression, one sound section with a still-valid observation, one approved decision, a v2 block), and checks that 37 deliberately broken variants are rejected (31 by the schemas, 6 by the cross-field checks the schema cannot express: ledger membership, ID cross-references, stop-reason group, v2 derivations, readiness). It also runs 29 adversarial cases, 28 from `research/audit/verify_spec.md` plus the not-assessed review (25 must be rejected, 4 accepted: an 8-token quote, an accepted risk with `no_change`, a disclosed degradation, a `not_assessed` review with no findings and its reason disclosed) and the INV-04 anchor oracle on a page-marked text (one valid Review, one invented quote, one quote cited on the wrong page).

## 6. Running the checks

```bash
pip install jsonschema pyyaml   # jsonschema >= 4.18 (uses `referencing`)
python3 spec/validate_examples.py
```

The legacy-coverage check reads `eval/*/*/answer_key.json` read-only and skips if `eval/` is absent.
