# Pre-registration deviations log (`eval/prereg.yaml`)

Append-only. This log records every change to a field of `eval/prereg.yaml` that is **not** listed under
`freeze.fill_before_freeze`, measured against the draft of 2026-10-02. It follows the freeze procedure:
the `git diff` of `prereg.yaml` against the draft commit may touch only `fill_before_freeze` fields, and
anything else it touches must appear here, with its reason, before `frozen` flips to true. Changes made
after the freeze are logged here too and are reported as deviations with the results.

Never edit or delete an entry. To correct one, append a new entry that refers to it.

Each entry gives: date, field, old text, new text, reason, who decided, and whether a scored run had
already happened (none had for entries made before the freeze).

---

## 1. 2026-10-02: matcher candidate rule

- **Field:** `matcher.candidates` (with matching text in `research/methodology/metrics.md` §2.3 step 1 and
  §13, and `eval/human_labelling_protocol.md` T4 source).
- **Old text:**

  ```yaml
  candidates:
    - location overlap (finding doc_anchors vs flaw location)
    - listwise LLM shortlist, up to 3 per flaw
    - embedding top-3 per flaw (optional; used only if an embedding model is recorded at freeze)
  ```

  (metrics.md §2.3: "The candidate set is the union of a, b and c.")
- **New text:**

  ```yaml
  candidates:
    rule: the listwise LLM shortlist bounds pairwise scoring - one shortlist call per flaw sees all findings (shuffled) and returns up to 3 ids; only those pairs are scored, every other pair scores 0
    shortlist: listwise LLM shortlist, up to 3 per flaw
    hints: location overlap (finding doc_anchors vs flaw location) and, if used, embedding top-3 per flaw are shown to the shortlist call as hints (which findings share a section or requirement id with the flaw); they add no pair by themselves
    embedding_prefilter: optional; used only if an embedding model is recorded at freeze, and then only as a hint
    location_compatibility: unchanged - still governs the score (a 3 with location_ok false is capped at 2, MM §2.1 rule 3)
    shortlist_failure: the flaw gets no candidates and counts as unmatched; the failure is reported with the scores and recall is labelled a lower bound; no fallback to the overlap set
    provenance: per flaw, scores.json records the overlap hint, which shortlisted findings also overlap and which overlapping findings were not shortlisted
    comparison_mode: "union (overlap union shortlist, the draft rule) is kept in the harness as --candidate-rule union; any run under it is a deviation"
  ```

- **Reason:** As written, location overlap made every finding that shares any listed section or
  requirement id with a flaw a candidate. A flaw's key location lists every place it touches (requirement
  tables 2.1/2.2, decision list 24, acceptance criteria 26.x, FR-5), so on the payments key overlap alone
  gave 80 pairs for one 20-finding review: 300-440 judge calls and about $25-37 per scored run (planning
  prices then in use), thousands of dollars for Tier A. `docs/BUDGET.md` §3 was costed on 3 candidates x 3
  samples per flaw, which is the new rule. Under it the same review plans 60-200 calls
  (`sit-eval score --dry-run`). Background: `docs/HANDOVER_FULL.md` §6 item 1 and §9; E1 verifier report,
  `docs/transcripts/session3_coordinator.md` (section 4). The prompt bundle changed with it (the shortlist
  prompt now carries the overlap hint): `PROMPTS.lock` bundle `d9e14df5...` became
  `ac35d198ecef1c5a9176acd29e3d82fd9203c35eee4f4624d86da2b429ecc156`, the value `matcher.prompt_sha256`
  takes at freeze unless the prompts change again.
- **Decided by:** the project owner, 2026-10-02 (coordinator recommendation, approved by the owner;
  `docs/USER_DECISIONS.md` #10).
- **Scored runs before the change:** none. `frozen: false`; the only matcher run so far is the exploratory
  pilot in `docs/live_runs/live_cc_opus_payments_v1/eval_pilot/` (union rule, per_flaw_batch).

---

## 2. 2026-10-02: adjudication class PARTIAL_KEY_MATCH

- **Field:** `matcher.adjudication` (new key `deterministic`) and `matcher.key_freeze`, with matching text in
  `research/methodology/metrics.md` §2.3 steps 4-5, §3 (P_a), §3.1, §6.1, §6.2, §7.1 and §13.
- **Old text:** `first_pass: same model as the matcher; classes DUPLICATE, VALID_UNPLANTED, HALLUCINATED,
  NON_SPECIFIC, INVALID_OPINION, OUT_OF_SCOPE` (no `deterministic` key); `key_freeze: ... confirmed
  VALID_UNPLANTED go to the pooled supplementary key G+`; metrics.md §3 `P_a = (TP + V) / N`.
- **New text:** `deterministic: before the first pass, DUPLICATE when the finding scores >= 2 against a flaw
  matched to another finding; then, under strict matching, PARTIAL_KEY_MATCH when its best median is 2 against
  a flaw nobody matched (the flaw id is recorded). PARTIAL_KEY_MATCH counts as correct for Precision,
  adjudicated (only if the flaw is in the run's gold set), is reported as its own count, is never
  VALID_UNPLANTED, never enters the pooled key G+ and never removes a sound unit`; `key_freeze` adds
  "(PARTIAL_KEY_MATCH never does)"; metrics.md §3 `P_a = (TP + V + PK) / N`.
- **Reason:** a finding that is unmatched under strict matching but scores PARTIAL against a key flaw nobody
  matched states a real issue that is already in the key. The adjudicator could only call it VALID_UNPLANTED
  ("missing from the key"), which also sent it to the pooled key G+ and let it remove a sound unit from CDR.
  The new label keeps it out of both, credits it in P_a (it is a real issue), and reports it as its own
  count. It is assigned from the matcher's scored pairs, like the deterministic DUPLICATE, so it costs no
  adjudicator call and is covered by the matcher validation (H10). The verifier-E1 exploratory metric
  `precision_adjudicated_partial_credit` is retired. The LLM adjudicator's six classes and its prompt are
  unchanged (prompt bundle unchanged). The deterministic DUPLICATE (already in metrics.md §2.3's class
  table) is now written into the prereg too; it is checked first.
- **Decided by:** the project owner, 2026-10-02 (`docs/USER_DECISIONS.md` #14).
- **Scored runs before the change:** none (`frozen: false`).

---

## 3. 2026-10-02: adaptive third pairwise sample

- **Field:** `matcher.pairwise_scoring` (with metrics.md §2.3 step 2 and §13).
- **Old text:** `0-3 scale (MATCH 3, PARTIAL 2, RELATED 1, UNRELATED 0); 3 samples, median`
- **New text:** `...; 3 samples, median; the third sample is asked only when the first two disagree or one
  failed, which leaves the median of 3 unchanged`
- **Reason:** when two of three samples agree, the median of three is their value whatever the third says,
  so the third call cannot change any score; skipping it saves up to a third of pair calls. Verifier E1
  showed identical medians and assignments with fewer calls (`tests/eval_harness/test_eval_verifier_e1.py`).
  `config/eval.yaml` `matcher.adaptive_third_sample: true`; `sit-eval score --no-adaptive-samples` asks all
  three for one run.
- **Decided by:** the project owner, 2026-10-02 (`docs/USER_DECISIONS.md` #15).
- **Scored runs before the change:** none (`frozen: false`).

---

## 4. 2026-10-02: shortlist recall sample in the matcher validation

- **Field:** `matcher.shortlist_recall` (new), with `eval/human_labelling_protocol.md` T4 and §6.
- **Old text:** none (`validation: human_labelling_protocol.md task T4 (100 S-dev pairs) and H10` only).
- **New text:** `shortlist_recall: T4 also labels 12 overlap_not_shortlisted pairs (pairs whose locations
  overlap but which the shortlist did not return, so the matcher never scored them), mixed blind into the
  T4 sheet and not counted in the 100; the share the rater scores 3 estimates the shortlist's miss rate on
  overlapping pairs and is reported with a Wilson 95 % CI in the instrument validity table; it is not a gate`
- **Reason:** since entry 1 the shortlist is the only way into scoring, and T4 samples shortlisted pairs
  only, so it validates the scorer but not the shortlist. A match the shortlist leaves out lowers recall with
  no error. The overlapping pairs it did not return are recorded per flaw
  (`matching.shortlist.<flaw>.overlap_not_shortlisted`), so a small blind sample of them estimates the miss
  rate where misses are most likely. Misses at non-overlapping locations leave no trace and stay unmeasured
  (stated as a limitation). Size: 12 pairs at about 1 minute each (0.2 h), within the protocol's T4 budget
  line (now 1.95 h; labelling total 15.1 h, Tier A still about 18 h).
- **Decided by:** the project owner, 2026-10-02 (verifier follow-up approved by the owner; implementer
  report in `docs/transcripts/session3_coordinator.md`, "Report: matcher rule implementer", item 6).
- **Scored runs before the change:** none (`frozen: false`).

---

## 5. 2026-10-02: no second-provider judge; tool names in LC9 and the stop rule

- **Fields:** `grader.second_provider.available` (a `fill_before_freeze` field, filled: `null` -> `false`
  with the reason as a comment), a comment on `matcher.model.branch_A`, `stop_rule.done_when` item 5 and
  `leakage_controls.before_first_scored_run` LC9; comments on `grader.prompt_sha256` and
  `matcher.prompt_sha256` (both `fill_before_freeze`, still `null`).
- **Old text:** `available: null      # fill before freeze from the key report (UD #3)`; `branch_A: the
  second-provider model, if a key exists (cross-family)`; `Every table in reporting.always_reported is
  produced by eval/score.py from logs alone.`; `check: eval/score.py reproduces the MM §14 worked example
  exactly (unit test)`.
- **New text:** `available: false` (Anthropic only; the same-family limitation is disclosed per
  research/models/README.md; ADR-003 closed); branch_A annotated "not available (UD #16)"; "produced by
  `sit-eval score` and `sit-eval aggregate` (harness/sit_eval) from logs alone"; "`sit-eval score`
  reproduces the MM §14 worked example exactly (unit test tests/eval_harness/test_eval_worked_example.py)".
  The two `prompt_sha256` comments record the current lock values: matcher
  `ac35d198ecef1c5a9176acd29e3d82fd9203c35eee4f4624d86da2b429ecc156` (`harness/sit_eval/prompts/PROMPTS.lock`),
  grader `64efe6b88489ac5542d7028f62782ed3c0b3096b0dfbfc0ac9ead22b4db75df0`
  (`harness/sit_eval/grader/prompts.lock.json`).
- **Reason:** the owner decided there is no second-provider judge, so `grader.second_provider.rule` takes
  its "if not" branch and `matcher.model` stays branch_B (Opus, disclosed as same-family). The semantics of
  the rule do not change. `eval/score.py` never existed; the scoring tool is the `sit-eval` CLI. These are
  clerical corrections, logged because the freeze procedure lists every non-fill field the diff touches.
- **Decided by:** the project owner, 2026-10-02 (`docs/USER_DECISIONS.md` #16) for the judge; the tool names
  are verifier text fixes collected before the freeze.
- **Scored runs before the change:** none (`frozen: false`).

---

## 6. 2026-10-02: correction to entry 1 (dry-run numbers)

- **Refers to:** entry 1, "Reason", the sentence "Under it the same review plans 60-200 calls".
- **Correction:** the `--dry-run` minimum of the first implementation assumed 0 pair calls and 14 matched
  flaws at the same time, which cannot happen (with no pair scored, nothing is matched and every finding is
  adjudicated). The dry run now reports true bounds: under `shortlist_bounded` the live-run review plans
  74-200 calls (pairwise, grounding judges on), $9.94-19.12 with the adaptive third sample (entry 3) or
  $10.54-19.12 without; the fewest calls and the lowest cost come from different outcomes. Under
  `--candidate-rule union` the same bounds give 294-440 calls without the adaptive sample (entry 1's
  "300-440" assumed N - G adjudications; every finding of that review overlaps a flaw, so none must reach
  the adjudicator). The rule of entry 1 is unchanged; only the reported numbers were wrong.
- **Found by:** the matcher-rule verifier, 2026-10-02 (`research/audit/verify_matcher_rule_editlog.md`).
- **Scored runs before the change:** none (`frozen: false`).

---

## 7. 2026-10-02: grader and matcher call path (Message Batches -> synchronous `claude -p`)

- **Fields:** `grader.primary.api`; `matcher.model.branch_B`.
- **Old text:** "Message Batches (50 % price)"; "claude-opus-5-5 via Message Batches, disclosed as same-family".
- **New text:** synchronous `claude -p` calls through the Claude Code backend; Message Batches applies only to
  the `anthropic_api` judge and is not implemented.
- **Reason:** the owner chose to bill model calls to the Claude Code login rather than a Console API key
  (`docs/DECISIONS.md` ADR-010, `docs/USER_DECISIONS.md` #6 and #9); the CLI has no batch interface. The model,
  effort and prompts are unchanged; only the transport and price basis differ. Measured per-call costs on this
  path are in `docs/HANDOVER_FULL.md` §9.
- **Decided by:** the coordinator under the owner's delegation (`docs/USER_DECISIONS.md` #11).
- **Scored runs before the change:** none (`frozen: false`).

---

## 8. 2026-10-03: S-dev canary key-only (LC10/LC11 notes); two lakehouse credit items made supporting

- **Fields:** comments on `leakage_controls.before_unsealing_s_heldout` LC10 and
  `leakage_controls.after_runs_before_scoring` LC11 (the checks themselves are unchanged). Also logged, although it
  is not a `prereg.yaml` field: the credit-item roles of the S-dev lakehouse key, which `matcher.credit_mode`
  ("per flaw from the key") reads.
- **Old text:** no comment on LC10 or LC11. Lakehouse F05 c2 ("HNSW memory formula / overhead ~1.1x(4d+8M)") and
  F06 c2 ("correct controls are 3.13.16 (CUI at rest) and/or 3.13.11 (FIPS-validated crypto)") were `required`
  under the legacy "first two must-mention items" rule (`spec/README.md` §2.6), so under `all_of` a finding had to
  state them.
- **New text:** LC10 and LC11 carry the scan note "key-only canary, S-dev": the three S-dev items carry the canary
  GUID in `answer_key.json` only, not in `design_v*.md` or the PDFs, and every held-out item gets its canary
  embedded before its first run (`docs/SEALING.md` §3). Lakehouse F05 c2 and F06 c2 are `supporting`
  (`spec/convert_answer_keys.py` `SUPPORTING_OVERRIDES`, read by `role_of()`); the lakehouse key now has 28
  required and 30 supporting credit items (was 30 and 28). F05 requires c1 only (memory understated about 4 times
  because float32 is 4 bytes per dimension); F06 requires c1 only (3.1.1 is access control, not encryption).
- **Reason:** the S-dev documents are cited by hash and anchor page in the live run and both pilots, and S-dev is
  the open development set, so an embedded canary there protects nothing; LC10 and LC11 would otherwise read a
  missing S-dev canary as an unavailable control. For F05 and F06, a finding that states c1 has plainly found the
  flaw; requiring the exact formula or the correct control numbers made the key stricter than the defect (the
  eval-data audit, Task 5, already called F05 c2 supporting). These are key content decisions taken before any key
  was signed; they are logged here because they change what a lakehouse finding must state to match.
- **Decided by:** SIT FABLE for the owner, 2026-10-02 (`docs/USER_DECISIONS.md` #17 and #19); applied 2026-10-03.
- **Scored runs before the change:** none (`frozen: false`; no key is `scored_run_ready`, and no lakehouse run has
  been matched).

---

## 9. 2026-10-03: note on runs with no assessment (no prereg field changed)

- **Field:** none. `runs.population` is unchanged ("Intention-to-treat - every launched run counts").
- **What changed outside the prereg:** the agent's output schema has a fourth verdict label, `not_assessed`,
  set by code when a run produced no assessment (the deadline skipped or cut the assess stage, the assess
  answer was truncated twice at the output cap, or the model declined the assess call twice). Before, such a
  run reported `not_fit` at confidence 0. The model is never
  offered the label: its verdict schema has `fit`, `fit_with_conditions` and `not_fit` only.
- **Effect on scoring:** none on the primary metric. A not-assessed run has no findings, so it scores 0
  recall against every key flaw and is counted (intention-to-treat). `sit-eval score` records
  `inputs.verdict_label` and adds a warning that says to exclude such a run only in the per-protocol view;
  `sit-eval aggregate` warns per run. No code computes the per-protocol view yet, so that exclusion is not
  implemented.
- **Effect on verdict agreement:** in the k-run group summary (`dra review --k`) a not-assessed run is never
  the modal verdict but stays in the denominator, so it lowers the agreement. The harness computes no
  verdict-agreement statistic.
- **Effect on grading:** gate G4 (explicit verdict present) is false for such a run, so D2 is capped at 0,
  and with a dimension at 0 gate G1 fails as well. Under the old placeholder G4 was true.
- **Reason:** `not_fit` read as a judgement of a design that nobody had assessed.
- **Decided by:** the session 3 coordinator (`docs/HANDOVER_FULL.md` §10), implemented in session 4 (`e8a6c12`);
  confirmed by SIT FABLE for the owner, 2026-10-03 (`docs/USER_DECISIONS.md` #25).
- **Scored runs before the change:** none (`frozen: false`). The pilot scoring and grading of the first live
  run are unaffected (its verdict is `fit_with_conditions`).
- **Amended 2026-10-03:** this entry first listed two reasons. Commit `aab35fa` added a third, an assess answer
  truncated at the output cap on the call and on its one retry (code-side key `truncated`). The three reasons
  above are every reason the code can produce today (`agent/sit_review_agent/phases/report.py`,
  `assessment_missing`: `deadline`, `truncated`, `declined`). The effects on scoring, verdict agreement and
  grading are the same for all three.

---

## 10. 2026-10-03: cost and token metrics of runs whose usage is partly unknown

- **Fields:** `stop_rule.pilot_checkpoint`; `reporting.always_reported` (the Efficiency row); the comment on
  `secondary_metrics` "Cost (USD), tokens, tool calls, wall time"; `costs.usage_completeness` (new) and comments on
  `costs.per_run_usd`, `costs.measured_median_full_usd` (a `fill_before_freeze` field, still `null`; only its
  comment changed) and its `freeze.fill_before_freeze` entry; amended by the session 4 verifier:
  `conditions.tier_A` B0-$ `matching_rule` and `stop_rule.budget_stop`.
- **Old text:** `pilot_checkpoint: If the pilot median FULL cost exceeds $3.24 or the p95 wall time exceeds the demo
  slot, re-plan before freezing (BUDGET.md §5); this is a pre-freeze change, not a deviation.`; Efficiency row
  `cost, tokens, tool calls, wall time median and IQR, stop reasons`; secondary metric comment `MM §10, median and
  IQR`; no `costs.usage_completeness`; B0-$ `matching_rule` ended `n recorded in costs.b0_dollar_matching_n; the
  best-of-n selection is by the model's own self-ranking ...` with no word on incomplete costs; `budget_stop` was
  its first two sentences only.
- **New text:** the cost check is `sit-eval aggregate` `pilot_checkpoint` against
  `costs.per_run_usd.heavy_case_FULL`: `fail` if the lower-bound median over all FULL runs exceeds the threshold,
  `pass` only if every FULL run is fully accounted and the median is at or below it, otherwise `not_evaluable`; a
  lower bound can fail the check but never pass it. `costs.usage_completeness` defines "fully accounted" (the run
  manifest's `extra.model.calls_with_unrecorded_usage` is empty, or the same rule over an older run's `llm.jsonl`
  finds no cut call; neither available means unknown), says that an incompletely accounted run's cost and tokens are
  null with the recorded figures beside them as lower bounds, that medians and IQRs are over fully accounted runs
  with the excluded count and share, that a lower-bound median over all runs stands beside them, that no aggregate
  mixes the two, and that the share of runs with any cut call is reported intention-to-treat. The Efficiency row and
  the secondary metric comment say the same. Added by the session 4 verifier under the same ruling: a run that reports
  no figure counts at 0 in the lower-bound median (leaving it out could overstate the bound); the B0-$ match uses
  fully accounted medians only and is `not_evaluable`, reported and with no n chosen, while any pilot FULL or B0 run
  is not fully accounted; the budget stop's spend is a lower bound when any run is not fully accounted, and a
  lower-bound sum at or above the Tier A figure triggers the stop while one below it is reported as "at least".
  A lower bound can fail a check or trigger a stop but never satisfy a match or a pass.
  Added under ruling #29 (`docs/USER_DECISIONS.md`): `stop_rule.pilot_checkpoint` now also says that a dropped run
  is a run of unknown cost; when any FULL scores file, or one whose condition cannot be read, is left out of the
  aggregate (judge budget stop, unreadable, schema-invalid, incomplete), the check is `not_evaluable` and the
  dropped files are listed with their reasons. Before it, a FULL run whose scoring the judge budget stopped was
  missing from the run count and the check could `pass` on the runs that remained.
- **Reason:** the agent runtime (commit `8ef32d4`) records a model attempt that was killed or cut (run deadline,
  timeout, crashed `claude -p`, dropped stream, interrupt) with `usage: null` instead of zeros, lists it in the
  manifest and marks `usage.cost_usd` a lower bound. The harness read `usage.cost_usd` as a complete figure (the
  demo measurement run showed $1.10 for a run of about $1.9), so a median over such runs understated the pilot cost
  and the "$3.24" checkpoint could pass on a lower bound. The rule is pinned to the runtime's in
  `harness/sit_eval/usage.py` (`tests/eval_harness/test_eval_usage_completeness.py`, with the demo run's `llm-0003`
  entry shape as the legacy fixture; `tests/eval_harness/test_eval_usage_verifier.py` checks both copies agree). The first live run's manifest predates the field and its `llm.jsonl` is not
  in the repository, so the harness reports its cost ($3.68) as a lower bound of unknown completeness.
- **Decided by:** SIT FABLE for the owner, 2026-10-03 (`docs/USER_DECISIONS.md` #28; the dropped-run rule #29).
- **Scored runs before the change:** none (`frozen: false`; no key is `scored_run_ready`). The two pilot `scores.json`
  files under `docs/live_runs/live_cc_opus_payments_v1/` are not rewritten; `sit-eval aggregate` treats a scores file
  that carries no completeness as unknown (its cost is a lower bound, never fully accounted).

---

## 11. 2026-10-03: the latency design (effort per stage, B0 wording, scheduling, pilot checkpoint, reporting)

- **Fields:** `agent_under_test.effort_per_stage` (a `fill_before_freeze` field, filled here and logged because the
  value departs from the draft's stated default); `conditions.tier_A` B0 `description`; `runs_per_item.scheduling`;
  `stop_rule.pilot_checkpoint`; `reporting.always_reported` (the Efficiency row). `frozen` stays false; no other
  `fill_before_freeze` value changed (`costs.per_run_usd`, `costs.measured_median_full_usd` and
  `costs.b0_dollar_matching_n` are as they were).
- **Old text:** `effort_per_stage: null   # fill before freeze; default high everywhere (UD #1); a lower stage effort
  is allowed only if the pilot latency measurement (FE N3) requires it, and is recorded here`; B0 `Single call, no
  tools, whole document plus the same task prompt and output schema (MR §4)`; scheduling ended `2-3 runs in
  parallel.`; `pilot_checkpoint` ended `the check is not_evaluable and the dropped files are listed with their
  reasons.`; the Efficiency row ended `the share of runs with any cut model call (intention-to-treat); stop reasons`.
- **New text:** `effort_per_stage` is the demo profile (`config/profiles/demo.yaml`, deadline 540 s): `medium` for
  understand, plan, assess, refine, verify and report, `low` for research, with the four assess shards of
  `config/agent.yaml` `assess.shards` (`intent_and_fitness`, `requirements_and_consistency`,
  `claims_and_assumptions`, `risk_and_operations`; K = 4). B0 adds: the single call is the assess brief with all
  criteria in one call. Scheduling: one FULL run at a time until 12 concurrent CLI sessions are measured, because a
  FULL run holds up to 6 at once (understand, plan and four shards in stage 1; 2 runs × 6 = 12, and 4 and 8 have
  been measured). `pilot_checkpoint` keeps all its earlier text, including the lower-bound and dropped-run rules of
  entry 10, and adds: the wall-time gate stays "p95 wall time exceeds the demo slot" (540 s) for this design; the
  cost figure is re-based on `docs/BUDGET.md` as redone after the first timed rehearsal (predicted about $5.4 per
  FULL run); until then a pilot of the new design is expected to fail the $3.24 figure, which is a re-plan, not a
  deviation. The Efficiency row adds, for FULL runs and intention-to-treat, the share with any deadline cut and the
  count of salvaged assess shards.
- **Reason:** measured on 2026-10-03 on the owner's Mac, a model call through the CLI has a fixed start-up latency
  (about 105 s for an assess call at `medium`) and then emits about 310 characters per second, so six sequential
  phases cannot fit 540 s (a sequential `medium` run with refine is about 1,177 s; the measured demo-profile run
  ended at 420 s with `not_assessed`, `docs/USER_DECISIONS.md` #27). The redesign (`docs/DECISIONS.md` ADR-011,
  ADR-012) runs stage 1 concurrently and cuts each stage at a fixed run-clock limit, keeping what a cut call
  finished; `high` cannot fit the slot at all, so the evaluated agent is the demo profile. Predicted, to be confirmed
  by the first timed rehearsal: 443 s document-only, 450 to 499 s with research, about $5.0 to $5.4 per FULL run.
  Every number scored on `live_cc_opus_payments_v1` describes the old single-call agent at `high` and is stale.
- **A4b arms (planner ruling, latency integration pass, 2026-10-03):** with FULL at `medium`, the former arm
  `A4b-medium` ("FULL with every stage at effort medium") was FULL itself but for research (`medium` against `low`),
  so A4b now compares `high` and `xhigh` against FULL. Old text: `conditions.tier_B` `- id: A4b-medium` /
  `description: FULL with every stage at effort medium (UD #5)`; HB1 `comparison: FULL at effort medium, high (the
  FULL reference), xhigh on the 3 S-dev v1 documents` and `high - medium >= 0.05; xhigh - high < 0.05`. New text:
  `- id: A4b-high` / `description: FULL with every stage at effort high (UD #5; FULL itself runs at medium,
  deviations entry 11)`; HB1 compares FULL (the reference) against A4b-high and A4b-xhigh, with `A4b-high - FULL >=
  0.05; A4b-xhigh - A4b-high < 0.05`, the same effect sizes. `A4b-xhigh` is unchanged; `EVAL_PLAN.md` line B-1
  follows, its USD figure marked as predating the redesign. `frozen` stays false and no `fill_before_freeze` value
  changed.
- **Decided by:** SIT FABLE for the owner, 2026-10-03 (`docs/USER_DECISIONS.md` #31; ruling 2 overrides the `high`
  default of #1, and the owner may reverse it).
- **Scored runs before the change:** none (`frozen: false`; no key is `scored_run_ready`). The pilot scores under
  `docs/live_runs/live_cc_opus_payments_v1/` are exploratory (ruling #26) and describe the old agent.

## 12. 2026-10-03: real-dev withdrawn (no answer key for the SIT sample)

- **Fields:** `analysis_sets.real_dev`, `hypotheses` H9 (a new `status` line), the `claimed_fix_verification_accuracy`
  metric `status`, `splits.real_dev.items` and `use`, `conditions.tier_A` FULL `documents`, `stop_rule.done_when`
  (first item), and the reporting list (the SIT comparison item removed).
- **Old text:** `real_dev: The SIT sample artefact v1 (line A-6) and the owner-written SIT v2 fixture (line A-7).`;
  H9 had no `status`; `status: exploratory, SIT v2 only, counts reported`; `splits.real_dev.items` listed
  `SIT sample artefact v1 (not committed; ADR-005)` and `SIT v2 fixture written by the owner to FE R-06, with a gold
  diff written before any agent run on it`, with `use: descriptive only (H9, H7 extras); never a generalisation claim
  (MR L39)`; FULL `documents: keyed_frozen, v2_pairs (fresh and with-context), real_dev`; `Every Tier A scored cell
  (EVAL_PLAN.md lines A-3 to A-7) has k = 3 launched runs, counted intention-to-treat.`; reporting item `SIT document
  comparison with the owner's key - both-found, owner-only, model-only items`.
- **New text:** `real_dev` is marked withdrawn (formerly lines A-6 and A-7); H9 `status: withdrawn 2026-10-03`;
  the SIT v2 metric `status: withdrawn 2026-10-03 with the SIT v2 fixture`; `splits.real_dev.items: []` with
  `use: none`; FULL documents `keyed_frozen, v2_pairs (fresh and with-context)`; the stop rule counts lines A-3 to
  A-5; the reporting item is removed. `eval/EVAL_PLAN.md` carries a note under §1; its tables keep A-6, A-7, T1, T8
  and CL9 as a record, and the Tier A run count and cost are recomputed by the budget lane.
- **Reason:** the owner, 2026-10-03, verbatim: "lets assume there is not answer key" for the SIT Memory Platform
  PDF. Without an owner key there is nothing to score the SIT sample against, so it becomes a demo and rehearsal
  document, not an evaluation item, and the agent may run on it. Tier A rests on the three S-dev synthetic items and
  the two sealed S-heldout items.
- **Decided by:** the owner, 2026-10-03 (`docs/USER_DECISIONS.md` #35, which supersedes #32).
- **Scored runs before the change:** none (`frozen: false`; no key is `scored_run_ready`; no SIT run was ever scored).

## 13. 2026-10-05: plan D, more documents and fewer runs per document; five new synthetic items

- **Fields:** `splits.S-dev.items` (five items added: `eval/synthetic/iot_fleet`, `consent_service`,
  `hospital_scheduling`, `ledger_migration` and `exam_platform`, each with its `item_id` and
  `documents: [design_v1.pdf, design_v2.pdf]`). No other field of `eval/prereg.yaml` is edited: the run counts of
  `conditions`, `stop_rule` and the S-dev `counts` line keep their old text in the file and are superseded by this
  entry until the file is next revised.
- **Old text:** the run counts of plans A to C: three S-dev synthetic items and two S-heldout items, and every Tier A
  scored cell with `k = 3` launched runs.
- **New text (plan D):** ten keyed documents, the three S-dev synthetic items, the two S-heldout items and the five
  new synthetic items; one full-agent run and one single-call baseline run per document, all at effort `medium`;
  five v2 re-assessments; two extra full-agent runs on each of two documents to estimate run-to-run variance; one
  `low` and one `high` effort run on one document.
- **Reason:** the document is the unit of analysis and between-document variance dominates run-to-run variance, so
  more documents with fewer repeats buys a tighter estimate for the same number of runs. The owner, 2026-10-04,
  verbatim: "less runs, but more variants document wise".
- **Decided by:** the owner, 2026-10-04 22:40, with the planner's shaping (`docs/USER_DECISIONS.md` #46).
- **Scored runs before the change:** none (`frozen: false`; no key is `scored_run_ready`). Every score stays
  exploratory until the owner signs the keys (ruling #26).

## 14. 2026-10-05: plan D ran the eight synthetic keyed documents only; the two held-out items were not run

- **Fields:** none of `eval/prereg.yaml` is edited; this entry narrows the run plan of entry 13.
- **Old text (entry 13):** ten keyed documents, the three S-dev synthetic items, the two S-heldout items and the
  five new synthetic items, each with one full-agent run and one single-call baseline run.
- **New text:** plan D ran the eight synthetic keyed documents only (the three S-dev synthetic items and the five
  new synthetic items); the two S-heldout items in `eval/blind/` were not run, by the agent or by the baseline.
- **Reason:** to keep the held-out set's budget of three evaluations (`docs/SEALING.md`, access budget S-heldout 3)
  for the frozen stage, and because the keys are unsigned, so a held-out score now could only be exploratory and
  would spend that budget without a confirmatory result.
- **Decided by:** the planner's ruling under the owner's delegation (the owner, 2026-10-03 02:50, "u make the shot
  calling"; plan D approved by the owner, 2026-10-04 22:40).
- **Scored runs before the change:** none on the held-out items; the plan D scores of the eight synthetic documents
  are exploratory (`frozen: false`, no key `scored_run_ready`, ruling #26) and are reported in
  `docs/COMPARISON_PLAN_D.md`.
