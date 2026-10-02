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
