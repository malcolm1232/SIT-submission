# Session 4: keys builder report (SIT FABLE key decisions applied)

Date: 2026-10-03 (local, UTC+8); clock read 2026-10-02 19:04 UTC.
Worker: one Opus 5.5 agent session, worktree `/Users/malco/Desktop/SIT-wt/keys`, branch `s4/keys`, base 0caa581.
Authority: the SIT FABLE decisions verbatim in `docs/transcripts/session3_coordinator.md`, section "SIT FABLE decisions".
No model calls, agent runs, scoring or grading were made.
Nothing was signed: every `authoring_drafts.signoff` block still has `signed_by: null`, `signed_on: null`, `accepted: []`, and all three canonical keys say `scored_run_ready: false`.

## Decision 1 (#17): canary key-only for S-dev - applied

No `design_v*.md` or PDF was touched.
`authoring_drafts.item.canary_embedded_in_documents` stays `false` in all three keys.
`authoring_drafts.note` in each key gained a sentence recording the decisions (it reaches the canonical `authoring_status.drafts.note`).
`eval/prereg.yaml` LC10 and LC11 each gained a YAML comment with the scan note "key-only canary, S-dev"; the check text is unchanged.
`eval/prereg_deviations.md` entry 8 logs those comments, because the freeze procedure logs every non-fill line the diff touches.
The rule for future held-out items (canary embedded before the first run) is written in `docs/SEALING.md` §3 step 3 and on the sheet (section 4, step 5).
`canary_guid` stays in `pending` until the owner lists it in `accepted` at signing; the sheet says so.

## Decision 2 (#18): external facts - applied

All 20 `external_fact.verification_note` values (payments 6, clinical 9, lakehouse 5) gained one sentence saying the eval-data audit is accepted as the S-dev verification, that `verified` stays false, and the re-check rule.
`verified` is still `false` everywhere.
The rule (owner re-check only for held-out keys and, before Tier A, for any S-dev fact a graded finding's credit turns on) is on the sheet in section 4, step 4, and noted at the head of section 8.
`external_fact_verification` stays pending until the owner lists it in `accepted`; the sheet says so.

## Decision 3 (#19): core insights - applied

The rule is written on the sheet under item 10 (the core-insight strictness item) and in the sheet's section 1 row for `core_insight`.

payments F04, `authoring_drafts.flaws.F04.core_insight`.
Before: "Section 9.3 assumes a DynamoDB partition sustains 10,000 WCU/s, but the per-partition limit is 1,000 WCU (and 3,000 RCU), so keying the idempotency table by merchant_id puts the largest merchant's ~900 TPS (at least 1,800 WCU even on the document's own two-writes count) on one partition key that will be throttled."
After: "Section 9.3 assumes a DynamoDB partition sustains 10,000 WCU/s, but the per-partition limit is 1,000 WCU, so keying the idempotency table by merchant_id puts the largest merchant's ~900 TPS on one partition key that will be throttled."
Removed exactly the three named phrases and the parentheses they left empty.
"~900 TPS" was kept: it is not in the delete list and credit item c2 names it, although SIT FABLE's "Keep" paraphrase says "peak writes".

payments F11, `authoring_drafts.flaws.F11.core_insight`.
Before: "Every card authorization needs an HSM unwrap (no DEK caching) and the CloudHSM cluster has a single HSM in one AZ, so losing that HSM or AZ stops all card payments, contrary to NFR-3 and the three-AZ posture elsewhere; the 1,500 TPS trigger for a second HSM is above the design peak and never fires."
After: "Every card authorization needs an HSM unwrap (no DEK caching) and the CloudHSM cluster has a single HSM in one AZ, so losing that HSM or AZ stops all card payments, contrary to NFR-3."
Removed the 1,500 TPS trigger clause (named) and "and the three-AZ posture elsewhere" (a secondary consequence no credit item requires; SIT FABLE's "Keep" text also omits it).
This second removal is my application of the rule, not a phrase SIT FABLE named; it is flagged on the sheet.
"(no DEK caching)" was kept because credit item c2 requires it.

clinical F09, `authoring_drafts.flaws.F09.core_insight`.
Before: "The 'anonymised' extracts keep strong quasi-identifiers (full 6-digit home postal code, exact timestamps, ward and bed, age, sex, ethnicity), so patients remain re-identifiable and the data is still personal data, which makes the claim that the extracts fall outside the PDPA, and their sharing to partner tenancies without per-extract approval, unjustified."
After: the verifier's item-12 text, verbatim (checked by script against the sheet's item 12): "The 'anonymised' extracts remove only direct identifiers and keep strong quasi-identifiers, notably the full 6-digit home postal code, which in Singapore usually identifies a single building, together with demographics or exact timestamps, so patients remain re-identifiable and the data is still personal data; the claim that the extracts fall outside the PDPA, and their sharing to partner tenancies without per-extract approval, is therefore unjustified."

lakehouse F01, `authoring_drafts.flaws.F01.core_insight`.
Before: "NFR-5 forbids processing Restricted content outside Westmoor-controlled AWS accounts, yet Section 14.4 and the 'Generation model' decision send Restricted-tier chunks to a commercial LLM on the vendor's public endpoint; zero-data-retention terms do not make that endpoint a Westmoor account."
After: "NFR-5 forbids processing Restricted content outside Westmoor-controlled AWS accounts, yet Section 14.4 and the 'Generation model' decision send Restricted-tier chunks to a commercial LLM on the vendor's public endpoint."

lakehouse F05 and F06: `spec/convert_answer_keys.py` gained `SUPPORTING_OVERRIDES = {("research_lakehouse", "F05"): {1}, ("research_lakehouse", "F06"): {1}}`, and `role_of()` takes the flaw id and returns `supporting` for those indexes.
In the canonical lakehouse key F05 c2 and F06 c2 are now `supporting`; the key has 28 required and 30 supporting credit items (was 30 and 28).
The F05 and F06 core insights were not changed, because SIT FABLE ruled only on the credit roles.
`spec/README.md` §2.6 (new table row), the §2 credit-mode row and the `credit.items` mapping row describe the override.

Accepted as drafted, no key change: clinical F03, clinical F05, lakehouse F04, all 45 drafted dispositions, items 7 and 8 (left as they are), item 9 (`v2.changed_sections`).
Each is marked "SIT FABLE" on the sheet; per-flaw boxes are ticked only where SIT FABLE named the flaw.

## Decision 4 (#20): payments F15 to AD-004 - applied

`authoring_drafts.approved_decisions[AD-004].flaw_ids` in the payments key: before `["F03"]`, after `["F03", "F15"]`.
The converter mirrors it: canonical payments F15 `affected_decisions` is now `["AD-004", "AD-006"]`.
The linking rule is written under item 7 on the sheet, with item 13 and the F15 entry and the section 6 AD-004 row updated.
The other drafted links were not re-derived under the rule, because that would be a new decision; the sheet says so.

## Other records

`docs/USER_DECISIONS.md` has a new heading "2026-10-02 (SIT FABLE for the owner; applied 2026-10-03)" with rows #17 to #20 in the existing table style.
`eval/prereg_deviations.md` entry 8 logs the LC10/LC11 comments and the lakehouse credit-role change, which is not a `prereg.yaml` field but changes what `matcher.credit_mode` (`all_of`) requires of a lakehouse finding.
The sheet has a new header block listing the decisions, and a new section 9 with the sha256 of the six key files and the converter; the signature section is now section 10 and is empty.

## Commands and exit codes

`/opt/homebrew/bin/python3.13 -m venv .venv` and `pip install -e ".[dev]"` inside the worktree: exit 0 (no conda env named `sit` existed; none was created; `.venv/` is already in `.gitignore`).
Baseline before edits, `python3 spec/convert_answer_keys.py --tier synthetic --check --verify-anchors`: exit 0; regenerating at baseline left the canonical keys byte-identical.
After edits, `python3 spec/convert_answer_keys.py --tier synthetic --verify-anchors` (write): exit 0.
After edits, `python3 spec/convert_answer_keys.py --tier synthetic --check --verify-anchors`: exit 0, "45 flaws converted across 3 keys; 0 key(s) failed validation", each key `scored_run_ready False`.
Spec validator `spec/validate_examples.py`, run under the converter's `_no_blind_glob` filter so it never opens `eval/blind` (SEALING.md §6 rule 1): exit 0, "ALL CHECKS PASSED", 32 negative tests and 28 adversarial cases.
Run directly it would glob `eval/blind/*/answer_key.json`, so it was not run directly.
`ruff check agent harness tests`: exit 0.
`pytest -q`: exit 0, 983 passed, 0 skipped, 0 failed (the 865 baseline predates later workstreams); with no failures there was nothing to compare against 0caa581.

## Hashes (sha256)

`eval/KEY_SIGNOFF.md` (the sheet, final): e673a5d2572a8de129ce55635059c610708e71887230a31e5075735110e8ed4a.
`eval/synthetic/payments_orchestration/answer_key.json`: b9ba2b5d7adcc92c7e849d5bef31cd0e2d4fbeecd7c4b8a47c37c30a89db811d.
`eval/synthetic/clinical_rpm/answer_key.json`: 64c71a6de410a544c89ac3fc8899c2ad129823140ed1e6388f9798c3631ebb54.
`eval/synthetic/research_lakehouse/answer_key.json`: 56ca982cdf4b136af1ddbcf2a1386d512dac9198687c8a6ccfa8043dccca2a51.
`eval/synthetic/payments_orchestration/answer_key.canonical.json`: 51ca4fbf508efa78e1d870264a7ef581d777f86083dc88fe464679d59442c219.
`eval/synthetic/clinical_rpm/answer_key.canonical.json`: 44833c1c01d8e89918c67991910ae583d6efc4aa22cdea8d20e4a436e7878735.
`eval/synthetic/research_lakehouse/answer_key.canonical.json`: 7c92bf91252858da076636b9e70bf4623fe049df4ab3a4e894e42c591bcce52a.
`spec/convert_answer_keys.py`: 7986801c9b7b0f1476c93a96842287caa261016b04e3819dccfca5e6ad3e26a8.
The six key hashes and the converter hash are also on the sheet (section 9); the sheet's own hash cannot be inside it and is recorded here and in the commit message.

## Not applied, and open points

Nothing in the four decisions was left unapplied.
SIT FABLE's message says `external_fact_verification` and `canary_guid` "go in `accepted`"; `accepted` is part of the owner's signature (the converter ignores it without `signed_by` and `signed_on`), so it was left empty and the sheet tells the owner to list both when signing (the sheet's one-liner already lists all nine fields).
Rows SIT FABLE did not name (other core insights, anchors, the 57 decision rows, sound sections) were not ticked; the sheet's header records SIT FABLE's instruction that only the signature remains, so the owner's signature covers them as drafted.
The lakehouse F05 core insight still names the HNSW formula and F06 still names 3.13.16 and 3.13.11; under `all_of` only the required items bind, but whether the core-insight text should also drop them was not ruled on.
No separate verifier agent checked this work (`docs/HANDOVER_FULL.md` §10 step 2 asks for one).

## Remaining for the owner

Sign: fill `signed_by`, `signed_on` and `accepted` (all nine fields) in the three keys with the sheet's section 4 one-liner, re-run the converter with `--verify-anchors`, run `pytest -q`, and fill the sheet's signature line.
