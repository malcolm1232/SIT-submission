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
