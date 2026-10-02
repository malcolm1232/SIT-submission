# Verification of `spec/` (taxonomy, finding and answer-key schemas)

Date: 2026-10-02. Scope: `spec/taxonomy.yaml`, `spec/finding.schema.json`, `spec/answer_key.schema.json`, `spec/README.md`, `spec/validate_examples.py`. These were checked against `research/audit/research_audit.md` §1, `research/audit/eval_data_audit.md` §4, the lab brief (pp. 2-6), `research/robustness/README.md` §2 and §10, and `research/grading/grader_prompt.md`. No git commands were run. Files were edited only under `spec/`. The only other files written are this report and the five `eval/*/*/answer_key.canonical.json` files.

**Result.** The spec was sound in design but had 12 enforcement gaps, one YAML parse bug, three example IDs taken from eval or sample documents, and a mapping section that had drifted from the eval keys after `eval_fixes_applied.md`. All of these are fixed. Both scripts now pass:

- `python3 spec/validate_examples.py` runs the 32 original negative tests, 28 new adversarial cases and the new INV-04 oracle: ALL CHECKS PASSED.
- `python3 spec/convert_answer_keys.py` converts all 73 flaws in the 5 keys, with 0 validation failures and 0 unmapped fields.

None of the five canonical keys is ready for a scored run. Each one still needs `core_insight`, anchor quotes and `expected_disposition` written by a person (see Open issues).

Concurrency note: during this session another agent edited `research/grading/*` (08:06-08:07) and `eval/blind/*/answer_key.json` (08:08). The grader findings in §5 are based on the re-read versions. The new item_b DEF-02 / S04 overlap note was added to the converter and to README §2.7.

---

## 1. Validator run and adversarial cases

The baseline run of `python3 spec/validate_examples.py` passed. It reported 17 enums, 2 README examples, 1 Review, 1 key and 32 negative tests, with legacy coverage of 14 + 14 + 15 + 15 + 15 = 73 flaws.

I then probed 28 adversarial cases, including every case the task named. Twelve of them exposed gaps, meaning the bad input was accepted when it should have been rejected. Each gap was fixed (§Edit log), and all 28 cases are now permanent tests in `ADVERSARIAL` in `validate_examples.py`. Each test asserts both the outcome and, through the printed reason, the rule that fires.

| # | Case | Intended | Before | After (rule that fires) |
|---|---|---|---|---|
| A01 | risk + `no_change` + non-null recommendation | reject | reject | schema: `recommendation` must be null |
| A02 | evidence item missing `supports_claim` | reject | reject | schema: required |
| A03 | anchor quote of 7 tokens | reject | reject | schema: quote pattern (≥ 8 tokens) |
| A04 | anchor quote of exactly 8 tokens | accept | accept | — |
| A05 | severity on a strength | reject | reject | schema: strength ⇒ severity null |
| A06 | unknown category `performance` | reject | reject | schema: enum |
| A07 | `all_of` credit with only `supporting` items | reject | reject | schema: `contains role=required` |
| A08 | `all_of` credit with empty items | reject | reject | schema: `minItems 1` |
| A09 | v1 flaw `fixed` with null `caused_regression_flaw_id`, while a v2 flaw names it in `introduced_by_fix_of` (the "fixed without introduced_new_flaw_id" case) | reject | reject | semantic: mirror check from the child side |
| A10 | parent names a regression, but the child's `introduced_by_fix_of` is null | reject | **accept (gap)** | semantic: new mirror check from the parent side (E5) |
| A11 | strength with `refinement_now` | reject | reject | schema: strength ⇒ `no_change` |
| A12 | accepted risk: risk + `no_change` + rationale | accept | accept | — |
| A13 | `secondary_dispositions` repeats the primary | reject | **accept (gap at Finding level; code-only before)** | schema: new if/then per disposition (E3) |
| A14 | `delta` review with no prior review, prior doc or reassessments | reject | **accept (gap)** | schema: Review `allOf` (E6) |
| A15 | `full` review carrying a reassessment block | reject | **accept (gap)** | schema: Review `allOf` (E6) |
| A16 | item with no v2 whose flaws carry v2 statuses | reject | **accept (gap)** | schema: key root `allOf` (E8) |
| A17 | item with a v2 but a flaw marked `not_applicable` | reject | **accept (gap)** | schema: key root `allOf` (E8) |
| A18 | recommendation cites contrary evidence (`supports_claim: false`) as support | reject | **accept (gap)** | semantic (E4) |
| A19 | doc evidence quote absent from the ledger excerpt | reject | **accept (gap)** | semantic (E4) |
| A20 | anchor page beyond `page_count` | reject | **accept (gap)** | semantic (E4) |
| A21 | degradation not cited by any limitation | reject | **accept (gap)** | semantic + new `limitations[].degradation_ids` (E7) |
| A22 | degradation that is cited by a limitation | accept | n/a (field new) | — |
| A23 | model fallback not recorded as a degradation | reject | **accept (gap)** | semantic (E7) |
| A24 | `cap` stop reason with no budget degradation | reject | **accept (gap)** | semantic (E7) |
| A25 | URL in a finding statement that is not in the ledger | reject | **accept (gap)** | semantic (E9) |
| A26 | external ledger entry whose tool call is not in the log | reject | n/a (no tool log) | semantic + new `research_log.tool_calls[]` (E9) |
| A27 | decision registry changed between iterations | reject | n/a (no hashes) | semantic + new `registry_sha256_by_iteration` (E10) |
| A28 | manifest without echoed criteria / stop rule | reject | n/a (field new) | schema: `review_config` required (E11) |

Two behaviours are accepted by design and are worth recording:

- A12 is accepted on purpose. A risk the reviewer judges acceptable is a legitimate `no_change` (lab §2.3).
- The quote pattern counts whitespace tokens, so 8 punctuation-only tokens pass the schema. The verify-stage fuzzy match against the document (INV-04 oracle) is what rejects such a quote.

## 2. The 32 conflicts in research_audit.md §1.1

"Implemented" means the resolution is in the YAML or JSON (or the converter), not only described in prose. Before this verification, README §3 recorded resolutions for 15 conflicts and listed 17 as "out of scope" with no disposition. I added a table to README §3 that gives each out-of-scope conflict an owner and its schema hook, so all 32 are now recorded.

| ID | Audit recommendation | Spec resolution | Impl. | Lab-consistent |
|---|---|---|---|---|
| C1 | Keep grading 0-4 rubric | Out of scope (grading); recorded in §3 table | n/a | n/a |
| C2 | Three validity tiers in prereg | Out of scope (prereg); recorded | n/a | n/a |
| C3 | One instrument-routing table | Out of scope (ADR-003); grader-facing projection added | n/a | n/a |
| C4 | Matcher is the only recall source | `scoring.matching_rule` const; no recall field in Review or key. Grading docs now rename recall to `key_alignment_diagnostic` (another agent) | yes | yes |
| C5 | One methodology rule, `core_insight` + optional required points | Same rule, plus per-flaw `credit.mode` (substance / all_of / any_of) with `required` / `supporting` roles. **Differs:** `required` items stand in for `required_points[]`; lakehouse "first two" becomes `all_of` with items 1-2 required | yes (`Credit`, `CreditMode`, converter) | yes |
| C6 | 4-level canonical scale; pre-register major→high, minor→low (sens. minor→medium) | Adopted. `severity` holds the primary value and `severity_source` the verbatim label. **Differs:** stores both (the eval audit wanted verbatim only) | yes (`legacy_mappings.severity`, `SeveritySource`) | n/a (lab silent) |
| C7 | Two axes; axis 2 = 8 labels + OTHER | Two axes. **Differs (D3):** 9 mechanisms + `other` (adds `external_constraint_violation`, widens two names) | yes (`kinds`, `categories`, `legacy_mappings`) | yes (axis 1 = lab §2.3) |
| C8 | Grading's triage enum incl. `mixed`, `none`; `expected_triage` per key | **Differs (D1):** `mixed` → `secondary_dispositions[]`, `none` → `no_change`; `expected_disposition` on each flaw | yes (`Disposition`; pending in every key, so BEH-16 is still BLOCKED) | yes (lab §3.2 word for word) |
| C9 | fit / fit_with_conditions / not_fit | Adopted; `fit_with_conditions` needs ≥ 1 linked condition | yes | yes (lab §1.4 "appropriate") |
| C10 | doc / external / inference | Adopted; inference needs `derived_from` | yes | yes (lab §4.2) |
| C11 | Ledger IDs; keep existence checks; `read_before_cite` | Adopted; URL and time are `readOnly`. Now also: free-text URL check, tool-call resolution (E9) | yes (`read_before_cite` recorded but not enforced, open issue P2-1) | yes |
| C12 | Union of stop reasons + decision/cap/error | Adopted | yes | yes (lab §3.2 "stop once enough evidence") |
| C13 | Quote + page + section in structured output | Adopted; `sha256_text`, and now `text_path` + oracle (E12) | yes | yes (lab §2.4 traceable) |
| C14 | Native PDF to model + one pinned extractor text | Out of scope for the extractor choice. Hooks: `sha256_text`, `text_path`, `run_manifest.extractor` | partial | n/a |
| C15 | No temperature/seed; record thinking, effort, max_tokens, betas | Adopted (`sampling` string, no temperature/seed fields) | yes | n/a |
| C16 | No server-side fallback; log the served model | `served_models[]`, `fallback_events[]`, `provenance.model` = served; fallbacks must also be disclosed as degradations (E7) | yes | n/a |
| C17 | Custom loop + checkpoints | Out of scope; recorded | n/a | n/a |
| C18 | Fix action types, adapt queries | Out of scope; hook `tool_calls[].status: blocked` | n/a | yes (lab §4.3 adapt) |
| C19 | Blind sealed, single use; rehearsal pool | Out of scope; `Split` has `Blind`, `S-heldout`, `rehearsal`; ex-blind items are `S-heldout` | partial | n/a |
| C20 | Report gap + DiD + CI | Out of scope; recorded | n/a | n/a |
| C21 | Achieved n and MDE in prereg | Out of scope; `prereg_sha256` hook | n/a | n/a |
| C22 | Author ≥ 2 sound control docs | Out of scope; a key may have `flaws: []` | partial | yes (lab §1.4 "no refinement") |
| C23 | ≤ 3 / ≤ 5 min targets | Out of scope; recorded | n/a | n/a |
| C24 | DEMO-04 = Claude tiers | Out of scope; `models_used[]` per role discloses within-family | n/a | n/a |
| C25 | Recompute grader cost | Out of scope; `usage.cost_usd` hook | n/a | n/a |
| C26 | Methodology VALID_UNPLANTED wins | Adopted: `still_valid_observations` pre-adjudicate VALID_UNPLANTED | yes (`Observation`, `adjudication_classes`) | n/a |
| C27 | Pairwise for ablations only | Out of scope; recorded | n/a | n/a |
| C28 | Record the returned model per response | Adopted (`provenance.model`, `served_models`) | yes | n/a |
| C29 | Per-stage model config | Out of scope; `models_used[].role` supports readers | n/a | n/a |
| C30 | Correct attribution; measure tokens | Out of scope; usage hook | n/a | n/a |
| C31 | Matcher on the critical path; precision = P_adj | Out of scope; matcher labels in taxonomy | n/a | n/a |
| C32 | One key schema + converter | Adopted; the converter did not exist and now does (`spec/convert_answer_keys.py`) | yes (now) | n/a |

Lab consistency: none of the resolutions conflicts with the brief. The three deviations (D1 dispositions, D3 categories, D5 severity scale) all stay inside what the brief allows.

## 3. Lab brief coverage (pp. 2-6)

| Brief requirement | Representation | OK |
|---|---|---|
| §2.3 strengths, risks, gaps, ambiguities, unresolved assumptions, validation needs | `Finding.kind` enum (all six, verbatim) | yes |
| §2.3 refinement: issue, rationale, supporting evidence, expected benefit | `Recommendation.issue`, `.rationale`, `.supporting_evidence_ids` (≥ 1, subset of the finding's evidence, now supporting-only), `.expected_benefit` | yes |
| §2.3 / §1.4 "if no refinement, explain why the design remains appropriate" | `disposition: no_change` ⇒ `no_change_rationale` required and recommendation null; review level via `sound_areas[]` and `verdict.rationale` | yes |
| §1.4 "how the change better supports the original objectives" | `expected_benefit` + `objective_refs[]` (≥ 1) | yes |
| §3.2 refinement vs investigation / prototyping / testing / governance | `disposition` (`refinement_now`, `needs_investigation`, `needs_prototyping`, `needs_testing`, `governance_decision`) + `secondary_dispositions[]`; non-refinement ⇒ `next_step{owner, action}` and an entry in `unresolved[]` | yes |
| §1.3 preserve key requirements and approved decisions | `decision_registry[]` (types `approved_decision`, `constraint`, `requirement`) + `affected_decisions[{relation}]`; `challenges` needs ≥ 2 evidence items; registry hash constant (E10) | yes, but see note |
| §2.3 explains design intent; assesses fitness for purpose | `intent_summary`, `verdict` | yes |
| §2.4 unresolved issues clearly stated; traceable | `unresolved[]`, `limitations[]`, anchors | yes |
| §4.2 distinguish design content from external research | `evidence[].source_type` doc / external / inference | yes |
| §1.5 re-assess an updated artefact | `review_mode: delta`, `prior_version` doc, `reassessment` (now enforced, E6) | yes |

Nothing in the brief is unrepresentable. One limit: the schema can show that a recommendation is labelled `challenges`, but it cannot detect a recommendation that silently contradicts an approved decision without the label. That needs a judge (INV-10 L1).

## 4. Robustness invariants and §10 architecture needs

| Invariant | Mechanically checkable from a Review? | Field added |
|---|---|---|
| INV-01 terminates | Partly: `run_manifest.timestamps` vs `budgets.deadline_s`; the watchdog is authoritative | — |
| INV-02 useful output / failure record | No. This is a process-level check; `outcome` covers the report case only | none (open issue P2-3: `failure.json` schema) |
| INV-03 schema-valid, all brief sections | Yes | — |
| INV-04 anchors resolve, page in range | **Before: no** (no path to the canonical text, no page bound check) | `documents[].text_path`; `anchors_resolve()` oracle (fuzzy ≥ 0.90 on page ± 1) and page ≤ `page_count` check |
| INV-05 citations resolve to a real tool call in this run; no stray URLs | **Before: no** (ledger `tool.call_id` resolved to nothing) | `research_log.tool_calls[]` {call_id, server, tool_name, status, started_at}; checks for ledger→call resolution, per-server counts and free-text URLs |
| INV-06 recommendation complete | Yes (schema) | — |
| INV-07 degradations disclosed | **Before: no** (limitations were strings with no link) | `degradations[].{id, type}`, `limitations[].{text, degradation_ids}`, `DegradationType` enum; checks that fallbacks, cap stops and failed calls are disclosed |
| INV-08 no secrets | Yes for the Review artefact (grep for canaries); other artefacts are out of scope | — |
| INV-09 manifest complete | **Before: partly** (no criteria, stop rule or fault-schedule ID) | `run_manifest.review_config{criteria, stop_rule, persona}`, `fault_schedule_id` |
| INV-10 registry constant; challenges labelled | **Before: partly** (no per-iteration hash) | `research_log.registry_sha256_by_iteration[]` + hash check (canonical JSON, sorted keys) |
| INV-11 no traceback | No (stderr, process-level) | — |

§10 needs: 3 (ledger IDs), 4 (verbatim anchors), 5 (registry), 7 (config echo, now complete) and 11 (template-rendered report from the Review) are represented. Item 8 is half covered. `explain <finding_id>` is a join over stable `FND`/`EV`/`AD` IDs, but there is **no coverage map** (open issue P2-2). Items 1, 2, 6, 9 and 10 are runtime architecture, not schema; their observable traces are covered by `tool_calls[].status`, `fallback_events`, `extractor` and the `ocr_used` degradation type.

## 5. Grader compatibility (`research/grading/grader_prompt.md`, re-read after 08:07)

| Grader need | Source in Review / key | Status |
|---|---|---|
| Shuffled findings with IDs; `finding_id` pattern `^FND-[0-9]{3,}$` | `Finding.id` (same pattern) | compatible |
| Evidence register | `evidence_ledger` (projected) | compatible |
| Framing withheld in Pass A; intent / verdict / unresolved in Pass B | `intent_summary`, `verdict`, `unresolved` | compatible |
| Recommendation booleans (issue, rationale, evidence, expected_benefit, objective_link) | `Recommendation` fields, `objective_refs` | compatible |
| `acknowledged_by_design`, `reopens_confirmed_decision`, `owner_or_next_step_named` | `acknowledged_in_doc`, `affected_decisions[relation=challenges]`, `next_step` | compatible |
| `severity_assessed` on the spec enum | `Severity` | compatible |
| Verdict label | `VerdictLabel` (grader adds `unclear`) | compatible |
| D11 delta | `reassessment`, `prior_review_id` | compatible |
| Key-aware `key_id`, `trap_id`, `no_change_areas_affirmed` | `FlawId`; `trap_id` = sound-section `id` | compatible (documented in README §1 projection) |
| No model name / tool traces in grader input | Review carries `provenance.model`, `run_manifest`, `research_log`, ledger `tool` | **mismatch until projected**: README now defines the grader-facing projection that drops these |
| Pass A `triage.review_label` / `correct_label` legacy enums | `disposition` via `legacy_mappings.triage` | `correct_label: not_applicable` was unmapped; added (`not_applicable: no_change`) |
| Key `key_items[].title` | `Flaw.title` is null for synthetic and item_b flaws | projection uses `description` when `title` is null (documented) |
| Final report recall fields | — | already renamed to `key_alignment_diagnostic` by the grading reconciliation; consistent with C4 |

## 6. Leakage

I grepped `taxonomy.yaml` (excluding `legacy_mappings`), `finding.schema.json` and `answer_key.schema.json` for about 60 distinctive terms from the five keys and the SIT sample, including DynamoDB, SQS FIFO, GDPR, Object Lock, IEEE 1547, Modbus, UL 9540A, Iceberg, Polaris, NEWS2, IEC 60601, Stripe, CVC, PDPA, Meridian, SEMS and Westmoor. I also ran a 4- and 5-gram overlap against all key text.

- **Found and fixed:** `finding.schema.json` used `'D-15'` and section `'9.3'` as examples. These are the confirmed decision and section behind clinical_rpm F14, and the finding-schema descriptions are sent to the model in the derived LLM schema. It also used `'25 Confirmed Decisions'`, a section of the SIT sample, and `'NFR-1'`. `answer_key.schema.json` used item_b's document ID `'FDC-SEMS-DD-001 Rev C'` (an S-heldout item) and `'D-15'`. All are replaced with invented IDs (E2). The re-grep is clean.
- **Shared n-grams that are not leaks:** the severity definitions reuse wording from the blind keys' `severity_scale` definitions. This is generic rubric text, not flaw content. The category names equal the legacy labels by design.
- **Structural (not fixed, open issue P1-1):** the 8 synthetic mechanisms are the generator's planted-flaw types. Putting `categories` in the agent prompt tells it which mechanisms the synthetic items contain.

## 7. Mechanical conversion

I wrote `spec/convert_answer_keys.py` and ran it. It reuses `validate_examples.py`'s validators, so it refuses to run if the spec self-test fails. It also asserts the dropped count fields against recomputed values.

| Key | Flaws (v1 / v2) | Severity (primary) | v2 status | Credit (mode: req / sup) | Ext. research | Sound / overlaps / obs. | Notes |
|---|---|---|---|---|---|---|---|
| payments_orchestration | 15 (14 / 1) | crit 5, high 6, low 4 | 6 fixed, 8 unchanged, 1 introduced | substance: 46 / 0 | 6 | 5 / 0 / 1 | `flaw_counts` equal; `expected_v2_open_flaws` equals derived |
| clinical_rpm | 15 (14 / 1) | crit 4, high 7, low 4 | 6 / 8 / 1 | substance: 55 / 1 | 9 | 5 / 2 / 1 | `category_counts_v1` equal |
| research_lakehouse | 15 (14 / 1) | crit 5, high 6, low 4 | 6 / 8 / 1 | all_of: 30 / 28 | 5 | 5 / 4 / 3 | §9 WAP `applies_to_versions: [v1]` |
| blind/item_a | 14 | crit 2, high 6, med 5, low 1 | not_applicable | all_of: 14 / 0 | 6 | 8 / 1 / 2 | `defect_count`, `category_taxonomy`, `severity_scale` consistent |
| blind/item_b | 14 | crit 1, high 7, med 6 | not_applicable | all_of: 26 / 0 | 4 | 9 / 4 / 4 | as item_a |

Totals: 73 flaws and 32 sound sections. 0 unmapped legacy fields and 0 schema or semantic failures. All five outputs have `scored_run_ready: false`. The pending fields are `canary_guid`, `author_type`, `author_model`, `generation_date`, `core_insight`, `anchor_quote`, `expected_disposition`, `approved_decisions`, `key_second_review`, `external_fact_verification` and `sound_overlap_annotations`, plus `v2_changed_sections` for the synthetic keys.

The README's "covers all 73 flaws" claim holds for categories and severities. Two mappings are only partial:

- **8 blind external facts** have no short "source: claim" prefix: item_a D01, D04, D05, D06, D10 and item_b DEF-03, DEF-05, DEF-06. The converter keeps the whole string as `claim` and writes `source: "unspecified in legacy key (citation embedded in claim)"`.
- **20 synthetic external facts** use `claim` = `why_it_is_a_flaw` as the README prescribes. That is a placeholder, not an external fact. Clinical F01, for example, concerns an NFR and a decision. The `verification_note` says so.

What the converter does not do:

- **`canary_guid`:** README §2.1 said "new uuid4". The converter writes null and lists `canary_guid` as pending instead, because a canary only works if it is embedded in the documents and fixed per split.
- **`v2.changed_sections`:** left as `[]` and pending. The verbatim revision-history text is copied into `v2.notes`.

## Edit log

| # | File | Change | Why |
|---|---|---|---|
| E1 | taxonomy.yaml; validate_examples.py | Quoted the `"yes"` / `"no"` keys in `legacy_mappings.verdict`; the validator now fails on any non-string mapping key | YAML 1.1 parsed them as `True` / `False`, so the verdict mapping was silently broken |
| E2 | finding.schema.json; answer_key.schema.json | Example IDs `D-15`, `9.3`, `25 Confirmed Decisions`, `NFR-1`, `FDC-SEMS-DD-001 Rev C` → invented `D-3`, `6.2`, `20 Decisions`, `NFR-7`, `BKG-DD-001 Rev A` | Leakage (§6) |
| E3 | finding.schema.json | Five if/then clauses: `secondary_dispositions` must not contain the primary | A13 (was code-only, so the LLM-facing repair loop could not cite a schema error) |
| E4 | validate_examples.py `review_semantics` | Supporting evidence must have `supports_claim: true`; doc and external quotes must occur in the ledger excerpt; anchor page ≤ `page_count` (all anchors, incl. registry, intent, sound areas) | A18-A20 |
| E5 | validate_examples.py `key_semantics` | `caused_regression_flaw_id` target must be a v2 flaw naming the parent | A10 |
| E6 | finding.schema.json Review `allOf` | delta ⇒ `prior_review_id`, a `prior_version` doc and a reassessment on every finding; full ⇒ none of them | A14, A15 (lab §1.5) |
| E7 | finding.schema.json; taxonomy.yaml; validate_examples.py | `DegradationType` / `degradation_types`; `degradations[].{id, type}`; `limitations` became `{text, degradation_ids}`; disclosure checks (fallbacks, cap and tool-failure stops, failed calls) | INV-07; A21-A24 |
| E8 | answer_key.schema.json root `allOf` | `v2: null` ⇔ `documents.v2: null` and every flaw `not_applicable`; with a v2, no flaw is `not_applicable` | A16, A17 |
| E9 | finding.schema.json; taxonomy.yaml; validate_examples.py | `research_log.tool_calls[]`, `ToolCallStatus` / `tool_call_statuses`; checks for ledger→call resolution, per-server counts and free-text URLs/DOIs ⊆ ledger | INV-05; A25, A26 |
| E10 | finding.schema.json; validate_examples.py | `research_log.registry_sha256_by_iteration[]` + `registry_sha256()` check | INV-10; A27 |
| E11 | finding.schema.json | `run_manifest.review_config{criteria, stop_rule, persona}`, `fault_schedule_id` | INV-09; A28 |
| E12 | finding.schema.json; validate_examples.py | `documents[].text_path`; `parse_page_marked`, `best_ratio`, `anchors_resolve` oracle plus 3 tests | INV-04 |
| E13 | answer_key.schema.json; validate_examples.py example | `disambiguation` (string or null) on `Flaw` and `SoundSection` | Field added to the legacy keys by `eval_fixes_applied.md`; it had no home |
| E14 | taxonomy.yaml | `legacy_mappings.v2_status` documents `introduced_new_flaw_id`; `legacy_mappings.triage.not_applicable: no_change` | Keys renamed `new_flaw_id`; grader `correct_label` was unmapped |
| E15 | validate_examples.py | 28 `ADVERSARIAL` cases; 2 new enum pairs (19 checked) | §1 |
| E16 | README.md | File table; §1 oracle list, cross-field rules, delta rule, new "Grader-facing projection"; §2.1/§2.2 updated for the post-fix keys (no `v2_new_flaws`, `introduced_new_flaw_id`, `readme_notes_moved_at_sealing`, lakehouse `all_of`, canary pending, external-fact split rule, `disambiguation`); §2.6 note that four overrides are already applied in the keys; §2.7 note on F06 and the new DEF-02/S04 row; new §2.8 converter; §3 table for the 17 out-of-scope conflicts; §5 test counts | §2, §5, §7 |
| E17 | spec/convert_answer_keys.py (new) | Converter; writes 5 `eval/*/*/answer_key.canonical.json` | §7 |

## Open issues

| Pri | Issue | Action |
|---|---|---|
| P0-1 | Every canonical key lacks `core_insight` (73), anchor quotes (73 flaws, 32 sound sections), `expected_disposition` (73) and `approved_decisions` (all 5 keys). Strict MATCH, action-type accuracy, BEH-16 and the approved-decision violation rate remain BLOCKED | Author them, get a second review (L12), set `scored_run_ready` |
| P0-2 | S-heldout keys are still plaintext. The converter added two more plaintext copies (`eval/blind/*/answer_key.canonical.json`) | Include the canonical files in the sealing step (audit P0-7); consider writing blind outputs straight into the sealed archive |
| P1-1 | The canonical `categories` are the synthetic generator's planted mechanisms. Prompting the agent with them advantages it on synthetic items | Keep categories out of the agent prompt, or run and report the taxonomy-dependence check (with and without) |
| P1-2 | External facts: 20 synthetic `claim`s are placeholders (`why_it_is_a_flaw`); 8 blind ones have no separate `source` | Restate and verify during `external_fact_verification` |
| P1-3 | The LLM-facing derived schema generator does not exist, and which keywords Claude structured outputs accept is UNVERIFIED (README §1). The new `allOf` rules (E3, E6) are verify-stage only | Write the generator; test against the API at build time |
| P1-4 | The INV-04 oracle checks page ± 1, not the "section ± 1" in metrics G2; the canonical text has page markers only | Add section markers to the extractor output, or accept page ± 1 and amend G2 |
| P1-5 | `v2.changed_sections` is pending for all 3 synthetic keys (the verbatim text is in `v2.notes`) | Fill by hand from the revision-history rows |
| P1-6 | The eval keys are being edited concurrently (item_b gained DEF-02/S04 at 08:08). The canonical files are snapshots | Rerun `convert_answer_keys.py` after any key edit; consider a CI check that the canonical file is newer than the legacy key |
| P2-1 | `read_before_cite` is recorded but not enforced for cited external evidence | Decide the policy (snippet-only sources?) and add a check if required |
| P2-2 | No coverage map in the Review (robustness §10 item 8) | Add `coverage_map[{section_ref, status, finding_ids, sound_area_ids}]` when the explain command is built |
| P2-3 | INV-02 `failure.json` has no schema; INV-01, INV-08 and INV-11 are process-level | Define a `FailureRecord` in `spec/` with the exit-code set |
| P2-4 | The confidence-band evidence anchor (high ⇒ ≥ 2 independent sources or 1 primary) is not checked | Add a semantic check over ledger `authority` |
| P2-5 | Clinical F06 is in the §4 overlap row only because the trap names it, and item_a's P2 #14 observation on the collection offer now overlaps the corrected D01 | Confirm both with the key author; the matcher should match flaws before observations |
| P2-6 | `legacy_mappings.v2_status`, `stop_reason` and `triage.mixed` values are prose, not machine-applicable | Acceptable for a converter-only table; keep the converter as the executable copy |
