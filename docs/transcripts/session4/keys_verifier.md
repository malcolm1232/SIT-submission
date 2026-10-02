# Session 4: keys verifier report (SIT FABLE key decisions #17-#20)

Date: 2026-10-03 (local, UTC+8); clock read 2026-10-02 19:17 UTC.
Verifier: one fresh-context Opus 5.5 agent session, worktree `/Users/malco/Desktop/SIT-wt/keys`, branch `s4/keys`.
Checked: base `0caa581`, builder commits `bf9fc63` and `e91683c`.
Authority: the "SIT FABLE decisions" section of `docs/transcripts/session3_coordinator.md`, read verbatim, plus the planner's rulings on the builder's three judgement calls.
No model calls, agent runs, scoring or grading were made, and nothing was signed.
Edit log: `research/audit/verify_key_signoff_s4_editlog.md`.

## Verdict

Ready to merge after this commit, with one reported gap (check 6: LC12 is not a code guard) and one disclosed interim-rule breach by this verifier (the edit log, "Interim-rule breach").
Two defects were fixed: payments F04 and F11 core insights now equal SIT FABLE's "Keep" texts verbatim, and the e2e test no longer breaks the owner's last signing step.

## Checks

1. Scope of the diff - PASS.
   `git diff --name-only 0caa581..HEAD` has no `design_v*`, PDF, `agent/`, `harness/`, `config/` or `tests/robustness/` path.
   All twelve S-dev design documents and PDFs hash the same at `0caa581`, at `HEAD` and in the worktree.
2. Each decision against the verbatim text - FIXED.
   Payments F04: the builder kept "Section 9.3 assumes ..." and "~900 TPS"; SIT FABLE's "Keep" text has neither ("peak writes"), so under the planner's ruling the core insight is now the "Keep" text exactly, first letter capitalised.
   Payments F11: the builder's removal of "and the three-AZ posture elsewhere" is right (the "Keep" text omits it, and credit items c1-c3 do not need it), but the wording was not the "Keep" text; it now is, verbatim.
   Clinical F09 equals the sheet's item-12 text (string equality).
   Lakehouse F01 lost exactly "; zero-data-retention terms do not make that endpoint a Westmoor account".
   Clinical F03, F05 and lakehouse F04 drafts are unchanged from `0caa581`.
   All 20 `external_fact.verification_note` values changed, no other external-fact field changed, and `verified` is false on every draft and canonical entry.
   Payments AD-004 `flaw_ids` is `["F03", "F15"]`, and canonical F15 `affected_decisions` is `["AD-004", "AD-006"]`.
   The canary `95c1d956-49fe-4e5a-af8d-91ae7333ac1d` is in all three keys and absent from the six Markdown files, the six PDFs' raw bytes and the six PDFs' agent-ingested text.
   The three rules are where the decisions put them: the canary rule in prereg LC10/LC11 comments, sheet section 4 step 5 and `docs/SEALING.md` §3; the external-fact rule in sheet section 4 step 4; the core-insight rule under sheet item 10; the linking rule under sheet item 7.
3. `role_of()` scope - PASS.
   Across all flaws of the three canonical keys, before against after, exactly two credit-item roles differ: lakehouse F05 c2 and F06 c2, `required` to `supporting`, texts unchanged.
   `SUPPORTING_OVERRIDES` is keyed by the item name `research_lakehouse`, so it cannot apply to `item_a`, `item_b` or a held-out key under any other name.
4. Generated files are generated - PASS.
   Regenerating at the builder's commit left all three canonical keys byte-identical; after my edits, regenerating changed only payments (two core insights and its source hash).
   `spec/convert_answer_keys.py --tier synthetic --check --verify-anchors` exits 0.
5. Hashes on the sheet - PASS (then FIXED for my edits).
   The builder's seven hashes in section 9 matched the committed files, and the sheet hash in `bf9fc63`'s message (`e673a5d2...`) matched its sheet.
   After my edits, section 9 carries the new payments hashes and all seven match the files.
6. Nothing is signed - PASS; harness refusal - FAIL as stated (reported, not changed).
   All `signoff` fields are null, every `accepted` list is empty, and every canonical key is `scored_run_ready: false` with all nine fields pending.
   The harness does not refuse a scored run on such a key: `harness/sit_eval/scoring.py` only adds the warning "answer key has scored_run_ready = false ... matcher scores are provisional", and `prereg.enforce` checks only the prereg freeze and prompt lock.
   LC12 is therefore enforced by procedure (and the unfrozen-pilot label), not by code.
   The warning is pinned by `tests/eval_harness/test_eval_e2e.py`; disabling it makes that test fail, and the guard was restored byte-exactly from a `cp` backup.
7. The owner's signing one-liner - FIXED.
   In a scratch copy, the sheet's one-liner (extracted verbatim from the sheet, NAME and DATE replaced by a dummy) signed all three keys; the converter then gave `pending: []`, `scored_run_ready True` and `key_reviewed_by` with the dummy signer for each key, with anchors checked, and `--check` exited 0.
   The sheet's last step, `pytest -q`, then failed: `test_plumbing_scores_json_is_valid` asserted the unsigned state of the real payments key.
   The test now asserts the warning exactly when the real key is unsigned, and that `inputs.scored_run_ready` equals the key's value; the signed scratch copy passes 983 and the unsigned worktree passes 983.
   The sheet tells the owner which entries to list: section 4 step 3 names all nine, and steps 4 and 5 repeat `external_fact_verification` and `canary_guid`.
8. Full gates - PASS.
   Spec validator: exit 0, "ALL CHECKS PASSED", 32 negative tests, 28 adversarial cases, INV-04 oracle 1 positive and 2 negative.
   `ruff check agent harness tests`: exit 0.
   `pytest -q`: 983 passed, 0 skipped, 0 failed.
   Converter `--tier synthetic --check --verify-anchors`: exit 0.
9. Prereg deviation entry 8 and USER_DECISIONS #17-#20 - PASS.
   Both follow their files' existing structure (entry fields Fields / Old text / New text / Reason / Decided by / Scored runs; a dated heading and the four-column table), are attributed "SIT FABLE for the owner, 2026-10-02", and their facts match the keys (lakehouse 28 required and 30 supporting, was 30 and 28; only payments has scored pilots, so "no lakehouse run has been matched" holds).
   Row #19 says "Payments F04 and F11 trimmed", which stays true after my edits.
10. No em dash, no secret - PASS.
    No added line in `git diff 0caa581` contains U+2014, and none matches a key, token or password pattern.

## Planner rulings applied

- Payments F11, three-AZ phrase: accepted; the verbatim "Keep" text leaves it out and no credit item needs it.
- Payments F04, "~900 TPS": the verbatim "Keep" text omits the figure, so the core insight is now that text exactly; credit item c2 still names ~900 TPS.
- Empty `accepted` lists: correct, they are part of the owner's signature, and the sheet lists the nine entries.

## Report only 1: links under the new rule

The rule is "a decision row is linked when the flaw's location cites the section that row governs".
The keys do not record which section a row governs, so I mapped each row to the design section that describes its subject (for example payments "Idempotency store" to §9.2-9.4, clinical D-11 to §10.3 and FR-7, lakehouse "Primary storage class" to §7.1 and §17.1); this mapping is my reading.
A cited parent or child section counts as citing the governed section, and citing the Confirmed Decisions table alone does not.
No current link would be removed.
These links would be added (row, flaw):

- Payments (12): AD-001/F01, AD-002/F01, AD-005/F01, AD-008/F01, AD-013/F01 (Fraud), AD-011/F05, AD-011/F06, AD-003/F07, AD-004/F07, AD-007/F09, AD-006/F13, AD-007/F13.
- Clinical (11): AD-005/F05, AD-011/F10, AD-012/F10, AD-013/F10, AD-005/F11, AD-010/F12, AD-012/F12, AD-013/F12, AD-011/F15, AD-012/F15, AD-013/F15.
- Lakehouse (8): AD-007/F01, AD-014/F04 (Primary storage class), AD-014/F05, AD-015/F08, AD-001/F10, AD-003/F10 (Catalog), AD-017/F10, AD-001/F15.

Three of these contradict sheet item 7's deliberate non-links that SIT FABLE told us to leave: payments Fraud/F01, lakehouse Catalog/F10 and Primary storage class/F04.
Broad sections (payments §5, clinical §10.3) produce most of the additions, so the rule as worded links far more than the drafting rule did; whether to re-derive is a decision for SIT FABLE or the owner.

## Report only 2: lakehouse F05 and F06 under the #19 rule

The #19 rule is written for `substance` mode, and lakehouse uses `all_of`, so this applies it by analogy; nothing was changed.

F05 now: "Section 15 sizes vector memory at 1 byte per dimension (180M x 1,024 = 184 GB), but float32 vectors take 4 bytes per dimension and faiss HNSW needs about 1.1 x (4d + 8M) bytes per vector, roughly 836 GB per copy, so the three-node OpenSearch domain is several times too small."
Out: "(180M x 1,024 = 184 GB)"; "and faiss HNSW needs about 1.1 x (4d + 8M) bytes per vector, roughly 836 GB per copy" (c2 is now supporting); "three-node".
Result: "Section 15 sizes vector memory at 1 byte per dimension, but float32 vectors take 4 bytes per dimension, so the OpenSearch domain is several times too small."

F06 now: "NFR-6 cites NIST SP 800-171 requirement 3.1.1 for customer-managed-key encryption with 90-day rotation, but 3.1.1 is an access-control requirement; protection of CUI at rest is 3.13.16 and FIPS-validated cryptography is 3.13.11, so the requirement is traced to the wrong control."
Out: "with 90-day rotation" (c3, supporting); "; protection of CUI at rest is 3.13.16 and FIPS-validated cryptography is 3.13.11" (c2, now supporting).
Result: "NFR-6 cites NIST SP 800-171 requirement 3.1.1 for customer-managed-key encryption, but 3.1.1 is an access-control requirement, so the requirement is traced to the wrong control."
"customer-managed-key" is a borderline modifier; c1 needs only "encryption".

## Not verified

- Whether the external facts themselves are true (no network; the audit's verdicts are taken as the decision says).
- That the anchor quotes locate the flaws semantically; only exact match and page were machine-checked.
- My row-to-section mapping in report 1 is a judgement, not a key fact.
- The harness under a frozen prereg with a signed key (the prereg is unfrozen).

## Hashes (sha256, after this commit)

`eval/KEY_SIGNOFF.md`: 74a761ddd61e9774fc042ba54f66227ce443aceb12654d50c4baee80700a2016.
`eval/synthetic/payments_orchestration/answer_key.json`: 5a04fba0c23e6161418520b15c4d87ac549de2ed1891a7c4c73165c072487886.
`eval/synthetic/payments_orchestration/answer_key.canonical.json`: 8eda2e5de12e54e98b2e4e4b242a2f86e8da7b8aa534594b363fa45ac4705011.
The clinical and lakehouse keys and the converter keep the builder's hashes, which are on the sheet in section 9.
