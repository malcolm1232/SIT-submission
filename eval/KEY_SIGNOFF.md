# Answer-key sign-off sheet (S-dev keys)

Date drafted: 2026-10-02. Drafted by: an agent session on `claude-opus-5-5` (workstream W3). Signer: the project owner (`eval/human_labelling_protocol.md` task T3).

**Status: nothing on this sheet is signed.** Every value below is an agent draft. All three keys stay at `scored_run_ready: false` (prereg check LC12) until you sign them with the steps in section 4.

**Decisions taken for you (2026-10-02, applied 2026-10-03).** The SIT FABLE session decided the open questions on this sheet on your behalf (`docs/USER_DECISIONS.md` #17-#20; verbatim in `docs/transcripts/session3_coordinator.md`, "SIT FABLE decisions"). They are applied to the drafts and marked "SIT FABLE" below:

- #17 canary: key-only for the three S-dev items (section 4, step 5).
- #18 external facts: the eval-data audit is accepted as the S-dev verification; `verified` stays false (section 4, step 4).
- #19 core insights: the substance-mode rule (item 10) is applied: payments F04 and F11 trimmed, clinical F09 replaced with the item-12 text, lakehouse F01 trimmed, lakehouse F05 and F06 c2 made `supporting` in `role_of()`; clinical F03 and F05 and lakehouse F04 accepted as drafted; all drafted dispositions accepted; items 7 and 8 left as they are; item 9 (`v2.changed_sections`) accepted.
- #20 payments F15 is linked to AD-004 (rule under item 7).
- #21 (SIT FABLE for the owner, 2026-10-03) clarifies the linking rule of #20: a link needs two conditions, and the links stand as drafted and verified (item 7). No key changed.
- #22 (SIT FABLE for the owner, 2026-10-03): the item-10 rule is for `substance` mode, so lakehouse F05 and F06 (`all_of`) keep their core insights as drafted; where the session record gives a "Keep" text, the core insight equals it exactly (item 10). No key changed.

SIT FABLE's instruction was that, after these, only your signature remains: rows it did not name stay as drafted and are covered by your signature (section 4, step 3). These are decisions on the drafts, not your signature. The `signoff` block in each key is still empty.

## 1. What was drafted, and what is still yours

| Field | State in all three keys | What you do |
|---|---|---|
| `core_insight` (45 flaws) | Drafted; four edited by SIT FABLE decision #19 under the substance-mode rule (item 10) | Accept, edit or reject each one (section 5) |
| `anchor_quote` + `page` (45 flaws) | Drafted and machine-checked (section 3) | Look at the quote and confirm it locates the flaw |
| `expected_disposition` + `acceptable_dispositions` (45 flaws) | Drafted | Accept or change |
| `approved_decisions[]` (19 + 20 + 18 = 57 rows) | Drafted from the "Confirmed Decisions" tables | Check the `flaw_ids` links (section 6) |
| `external_fact` claim, source and audit note (6 + 9 + 5 = 20 flaws) | Claim restated from the eval-data audit; `verified: false` everywhere; audit accepted as the S-dev verification (SIT FABLE #18, note added to each entry) | Decided: option (b) (section 4, step 4) |
| `sound_overlap_annotations` | Overlaps rechecked; 2 sound sections split into sub-locations | Accept or change (section 7) |
| `v2.changed_sections` | Drafted from a section-level diff of v1 against v2 | Accept or change (section 7) |
| `author_type`, `author_model`, `generation_date`, `generator_session_ref`, `brief_sha256` | Filled from the session record; no longer pending | Spot-check the evidence below |
| `canary_guid` | One S-dev GUID assigned (`95c1d956-49fe-4e5a-af8d-91ae7333ac1d`), **not** embedded in any document | Decided: key-only for S-dev (SIT FABLE #17, section 4, step 5); stays pending until you sign |
| `key_second_review` | Pending | Your signature is the second review (RA L12, protocol T3) |

**Provenance evidence.** `docs/transcripts/README.md` lists the generator subagents (model O = Claude Opus 5.5): payments `agent-aad4920f0c3541cf7`, clinical `agent-ac521bf703f699435`, lakehouse `agent-a21d102fbd2aa1f49`. In each transcript (`docs/transcripts/subagents/<id>.jsonl.gz`) every assistant message has `model: claude-opus-5-5`, and the timestamps run 2026-10-02 06:48-07:06 UTC. `brief_sha256` is the sha256 of the UTF-8 text of the first non-meta user message in that transcript. The keys were later edited by other Opus 5.5 agents (`research/audit/eval_fixes_applied.md`, `research/audit/verify_eval.md`), so `author_type` is `llm` for both the documents and the keys. If you edit core insights, the keys become partly human-written; you may then set `author_type` to `mixed` in the `authoring_drafts.item` block.

**Isolation.** The drafts were written only from `design_v1.md`, `design_v2.md`, the legacy key fields, `research/audit/eval_data_audit.md` and `research/audit/verify_eval.md`. The drafting session did not open `eval/blind/**`, `docs/live_runs/**`, `runs/**`, `docs/transcripts/session3_coordinator.md`, `prompts/` or `harness/sit_eval/prompts/`, and read no agent review of these documents. Please review this sheet before you look at any agent output on these documents again, so your edits are not shaped by what the agent found.

## 2. How to review (rules from protocol T3)

For each flaw, check the drafted `core_insight` against these tests:

1. It is **one proposition that names the defect**, not the topic.
2. A generic finding that would fit any design cannot satisfy it.
3. It does not require particular wording, and it fits the flaw's credit mode. Payments and clinical use `substance`: the core insight as a whole is what a finding must state, and the credit items are only guidance. Lakehouse uses `all_of`: credit items c1 and c2 are required, so the core insight must imply both (they are printed under each lakehouse flaw).
4. The anchor quote exists in the document and sits at the flaw's primary location.

For `expected_disposition`, the closed set is `refinement_now`, `needs_investigation`, `needs_prototyping`, `needs_testing`, `governance_decision` (`no_change` is not allowed for a flaw). The drafting rule was:

- `refinement_now`: the right change is known from the document plus the cited external fact.
- `needs_investigation`: a fact (a legal reading, a vendor capability) must be established first.
- `needs_testing`: the defect is in an acceptance criterion or test.
- `needs_prototyping`: only a spike or benchmark can settle it.
- `governance_decision`: the fix trades one stated requirement against another, or re-opens a confirmed decision, so an accountable owner must decide.

`acceptable_dispositions` lists the defensible alternatives.

**Time.** About 3 hours in total, in three sessions of at most 90 minutes (protocol §1 session rules):

- 45 flaws at about 3 minutes each (2.25 h): core insight, anchor and disposition.
- 57 approved-decision rows at about 20 seconds each (0.3 h).
- 20 external-fact notes (0.3 h).
- v2 sections, sound splits, canary decision and signing (0.25 h).

The 42 v1 flaws alone take about 2.1 h. The protocol's T3 line budgets 1.5 h for core insights alone.

### Look at these first

These are the flaws where the core insight was hard to state, or where the existing key looks off:

1. **research_lakehouse F05.** The legacy "first two must-mention items" rule makes c2 (the exact OpenSearch HNSW formula) required. The eval-data audit (Task 5) called that item supporting. A reviewer who says "float32 is 4 bytes per dimension, so memory is about 4 times understated and the domain is several times too small" has plainly found the flaw. Consider making c2 supporting, or reading it as "the formula *or* an equivalent overhead estimate". The drafted core insight mentions the formula only as "about".
   - **SIT FABLE (#19):** c2 made `supporting` in `role_of()`. Required: memory is understated about 4 times because float32 is 4 bytes per dimension, so the domain is too small.
2. **research_lakehouse F06.** c2 requires naming the correct controls (3.13.16 and/or 3.13.11). This is strict in the same way as F05: a finding that says "3.1.1 is access control, not encryption" may be enough for you.
   - **SIT FABLE (#19):** c2 made `supporting` in `role_of()`. Required: 3.1.1 is an access-control requirement, not encryption, so the citation does not support the claim.
3. **research_lakehouse F04.** The required items are about tier behaviour only (opt-in, restore needed). The NFR-9 cost breach is c3, which is supporting. So the draft leaves cost out. Decide whether the cost breach belongs in the core insight.
   - **SIT FABLE (#19):** accepted as drafted; the NFR-9 cost breach stays supporting (c3), not in the core insight.
4. **clinical_rpm F05.** The audit (Task 5) calls F05 arguable: IEC 60601-1-8 separates alarm-condition delay from alarm-signal delay, so whether the 10-second window counts against NFR-2 depends on where NFR-2 starts. The draft says "up to" and does not require a 15-second worst case.
   - **SIT FABLE (#19):** accepted as drafted; "up to" stands and c4 (push latency) is not required (see item 11).
5. **clinical_rpm F03 and F12, payments F04 and F12.** The drafts drop a must-mention item that is phrased as "or", "and/or" or "at least one of": clinical F03 drops the MIC@Home / residency item (c4), payments F04 drops the item-size / LSI detail (c3), clinical F12 no longer names the window and clock, and payments F12 accepts either of its two ambiguities. Under `substance` mode that keeps the core insight to the essential defect. Check you agree. (Clinical F12 and payments F12 were edited by the verifier; see their entries in section 5.)
   - **SIT FABLE (#19):** clinical F03 accepted as drafted (dropping c4 is right).
6. **The three `decision_depends_on_pending_item` flaws** (payments F14, clinical F14, lakehouse F14) were drafted as `governance_decision`, with `refinement_now` acceptable. That is a policy choice for the action-type metric. Other borderline dispositions: payments F03 (`governance_decision`), payments F07 and clinical F07 (`needs_investigation`), and payments F13, clinical F13 and lakehouse F13 (`needs_testing`).
   - **SIT FABLE (#19):** all drafted dispositions accepted, including `governance_decision` for the three pending-item flaws with `refinement_now` acceptable.
7. **Approved-decision links that were left out on purpose:**
   - lakehouse "Catalog" is not linked to F10, and "Primary storage class" is not linked to F04: neither flaw cites §20 in the legacy key.
   - payments "Fraud" is not linked to F01: the Fraud row says nothing about the PAN.

   If you link them, a correct finding that challenges those rows can no longer count as an approved-decision violation.

   - **SIT FABLE (#19, #20):** these three non-links are left as they are.
   - **Linking rule (SIT FABLE #20, clarified by #21 on 2026-10-03), for all three keys alike:** A decision row is linked to a flaw when (a) the flaw's location cites the section that row governs AND (b) the flaw's defect is in the subject that row decides. Condition (a) alone is necessary, not sufficient: a broad section that hosts several decisions does not link every flaw located in it. The links on the sheet as drafted and verified stand, including the deliberate non-links in item 7; no link is re-derived mechanically.
   - **Why payments F15 -> AD-004 meets (b):** (a) F15 (location §9.4; 20.2; 24) cites §20.2, which the "Disaster recovery" row (AD-004) governs. (b) F15's defect is that duplicates arriving in different regions can both acquire the lock, and a duplicate can arrive in a second region only because the v2 "Disaster recovery" row adds the warm API cell in ap-southeast-3 (§20.2: Route 53 shifts merchant traffic to it); §9.4 says the global table exists "to support the regional recovery posture in Section 20". So (b) holds through the two-region write topology that row decides, not through the lock itself, which is AD-006's subject (item 13).
8. **payments F05 severity.** It is still `minor` (low), although audit P2-13 suggests major. This was not changed: severity is outside this sheet.
   - **SIT FABLE (#19):** left as it is.
9. **The v2 revision logs are incomplete.** Payments v2 also changed §10.3 and §19.1, clinical v2 also changed §14.5, §17.1 and §23, and lakehouse v2 also changed §20 and the NFR-9 criterion in §22.2. The logs do not name these. They are included in `v2.changed_sections`.
   - **SIT FABLE (#19):** the `v2.changed_sections` additions are accepted.

#### Added by the verification pass (2026-10-02)

A second agent checked these drafts against the design documents and the legacy keys. It edited three core insights (payments F03 and F12, clinical F12; marked "Edited by the verifier" in section 5; log in `research/audit/verify_key_drafts_editlog.md`). These points are left for you:

10. **How strict a core insight is.** In `substance` mode (payments and clinical) the matcher is told the finding "must state the core insight as a whole". So every clause in a draft is a requirement, including clauses after a semicolon and lists in brackets. If a clause is only supporting detail, delete it. Examples to look at: payments F04 ("(and 3,000 RCU)", "at least 1,800 WCU"), payments F11 (the 1,500 TPS trigger clause), lakehouse F01 (the zero-data-retention clause, which is a supporting item).
    - **Rule for `substance` mode (SIT FABLE #19):** the core insight states the defect and why it is a defect, nothing else. Numbers, parentheticals and secondary consequences are supporting detail and come out unless a credit item requires them. Applied: payments F04 and F11 trimmed, clinical F09 replaced (item 12), lakehouse F01 trimmed; clinical F03 and F05 and lakehouse F04 accepted as drafted. The same rule applies to any later edit of a core insight.
    - **Scope of the rule, and "Keep" texts (SIT FABLE #22, 2026-10-03):** (i) Rule #19 (the core insight states the defect and why it is a defect, nothing else) applies to flaws scored in `substance` mode. Lakehouse F05 and F06 are scored in `all_of` mode, where the credit items carry the match; their core insights stand as drafted, and their c2 items stay `supporting` per #19. (ii) Where the session record gives a "Keep" text for a flaw, the core insight equals that text exactly; a figure that a credit item needs lives in the credit item, not in the core insight (applied to payments F04 in 5b464ba).
11. **clinical_rpm F05 also drops c4.** Besides the "up to" wording (item 4), the draft leaves out c4 (APNs/FCM push has no latency guarantee), which the legacy key lists as a must-mention item. The distractor note treats the push figure as secondary, so this looks right, but it is looser than the legacy list.
    - **SIT FABLE (#19):** accepted; c4 is not required.
12. **clinical_rpm F09 lists every quasi-identifier but omits c2.** The draft names the postal code, timestamps, ward and bed, age, sex and ethnicity, so a strict matcher may want all of them. It does not say why the postal code matters (c2: a 6-digit Singapore postal code usually identifies one building). A possible text: "The 'anonymised' extracts remove only direct identifiers and keep strong quasi-identifiers, notably the full 6-digit home postal code, which in Singapore usually identifies a single building, together with demographics or exact timestamps, so patients remain re-identifiable and the data is still personal data; the claim that the extracts fall outside the PDPA, and their sharing to partner tenancies without per-extract approval, is therefore unjustified."
    - **SIT FABLE (#19):** F09 now uses this text. The full list of quasi-identifiers is not required.
13. **payments F15 and the "Disaster recovery" row (AD-004).** F15 is linked only to "Idempotency store" (AD-006). The v2 "Disaster recovery" row adds the warm API cell in ap-southeast-3, which is what sends a retry to the second region. Linking AD-004 to F15 is defensible; leaving it is also defensible, because the defect is the global-table lock. Lakehouse F15, by contrast, is linked to both rows its v2 change touched.
    - **SIT FABLE (#20):** linked. F15 cites §20.2, the section the DR row governs, and the fix for F15 can change the two-region write topology, so a finding that challenges AD-004 is a legitimate affected decision.
14. **Sign last.** The sign-off is not tied to the draft text. If you edit `authoring_drafts` after signing, the key stays signed. Make all edits first, then sign; after any later edit, sign again with a new `signed_on`.
15. **Sound-section sub-locations are text only.** Clinical §4 and lakehouse §16 are split into sub-locations, but the harness reads only the section number (for example "16 Audit Plane (Content boundaries)" is section 16), so the split guides the matcher and the human rater, not the location arithmetic.

## 3. How the anchor quotes were checked

Every flaw anchor and every approved-decision anchor was checked against the text the agent itself reads:

- `sit_review_agent.ingest.pdf.ingest` was run on `design_v1.pdf`, and on `design_v2.pdf` for the three v2-only flaws (F15).
- Each quote is an **exact, case-sensitive, unique** substring of the flattened canonical page text. Its page is the page of that match.
- Each quote is also verbatim in the Markdown source once markup is removed (backticks, `**`, and table pipes, so table cells read as one line).
- The agent's own section-window check (`sit_review_agent.ingest.anchor.verify_anchor`) passes for every flaw anchor with the ingest code now in the repository (two failed with the earlier ingest; see below).

Re-run the check at any time with `python3 spec/convert_answer_keys.py --tier synthetic --check --verify-anchors` (venv active). It fails on any quote that is not an exact, unique match on the stated page.

Known limits:

- **The PDF extractor removes some hyphens at line breaks.** For example "storage-level" becomes "storagelevel" (payments §20.2) and "multi-provider" becomes "multiprovider" (§16.2). Quotes containing such words were avoided, so no anchor is a fuzzy match.
- **Long table cells are split across lines in the PDF.** Requirement-table anchors are therefore the part of the cell on one PDF line. For example, payments FR-8's anchor stops before "2%", because "authorization rate by more than 2%." is on the next page.
- **Seven decision anchors are shorter than 8 tokens:** payments "Cloud and primary region" and "Idempotency retention"; clinical D-5 and D-11; lakehouse "Cloud and primary region", "Ingestion pattern" and "Primary storage class". These short table cells cannot be quoted at 8 or more tokens without crossing into the next row. The 8-token rule applies to finding anchors, and the schema does not require it for decision anchors.
- **The agent's section-window check failed for two exact quotes when drafted: clinical F09 (§17.4) and lakehouse F03 (§13).** The ingest heading heuristic read the numbered list items ("1." to "4.") inside those sections as section headings. The ingest code now in the repository (another workstream's change, WIP snapshot `3155202`) drops such list items, and with it all 45 flaw anchors pass `verify_anchor` (checked by the verification pass, 2026-10-02). If that change is reverted, these two fail again; the exact-match check above does not depend on it.

## 4. How to sign (exact steps)

All edits go in the legacy key, `eval/synthetic/<item>/answer_key.json`, inside the top-level `authoring_drafts` block. Never edit `answer_key.canonical.json` by hand: the converter regenerates it.

1. **Edits.**
   - Core insight, anchor, disposition: change `authoring_drafts.flaws.<Fxx>.core_insight`, `.anchor_quote` and `.anchor_page`, or `.expected_disposition` and `.acceptable_dispositions`. `expected_disposition` must be one of the acceptable ones.
   - Approved decisions: change `authoring_drafts.approved_decisions[i].flaw_ids` or delete a row. The converter mirrors `flaw_ids` into each flaw's `affected_decisions`.
   - v2 sections: change `authoring_drafts.v2_changed_sections`.
   - Sound-section splits: change `authoring_drafts.sound_sections`.
   - To change a credit-item role (look-first items 1 and 2), edit `spec/convert_answer_keys.py` `role_of()`. It is the only place roles are set.
2. **Record decisions on this sheet.** Tick accept, edit or reject per row, and write any new text. Then hash the completed sheet (`sha256sum eval/KEY_SIGNOFF.md`) and commit the hash. Protocol §2 rule 7 applies: labels are never edited after comparison.
3. **Sign.** In each key's `authoring_drafts.signoff`:
   - set `signed_by` to your name;
   - set `signed_on` to the date (YYYY-MM-DD);
   - set `accepted` to the fields you sign. To make a key scoreable, this must be all of `canary_guid`, `core_insight`, `anchor_quote`, `expected_disposition`, `approved_decisions`, `key_second_review`, `external_fact_verification`, `sound_overlap_annotations`, `v2_changed_sections`.

   A one-liner that does this for all three keys (replace NAME and DATE):

   ```bash
   python3 - <<'EOF'
   import json
   FIELDS = ["canary_guid", "core_insight", "anchor_quote", "expected_disposition", "approved_decisions",
             "key_second_review", "external_fact_verification", "sound_overlap_annotations", "v2_changed_sections"]
   for item in ["payments_orchestration", "clinical_rpm", "research_lakehouse"]:
       p = f"eval/synthetic/{item}/answer_key.json"
       k = json.load(open(p, encoding="utf-8"))
       k["authoring_drafts"]["signoff"].update(signed_by="NAME", signed_on="DATE", accepted=FIELDS)
       open(p, "w", encoding="utf-8").write(json.dumps(k, indent=2, ensure_ascii=False))
   EOF
   ```
4. **External facts.** All 20 `external_fact` entries have `verified: false`. The claim, source and note were restated from the eval-data audit (2026-10-02). That audit labelled its sources P (primary mirror), P-snippet, S or K, and found every flaw-level fact correct. You have two options:
   - (a) Re-check each source with network access. In `authoring_drafts.flaws.<Fxx>.external_fact`, add `"verified": true`, `"verified_source_url"` and `"verified_at"` (YYYY-MM-DD). The converter copies them, and the schema requires the URL and date whenever `verified` is true. You still list `external_fact_verification` in `accepted` (step 3); the converter does not clear it on its own.
   - (b) Accept the audit's check as sufficient, and include `external_fact_verification` in `accepted`. The converter then prints a note that you accepted audit-level verification. Under (b) the key stays honest: `verified` remains false and the note says why.
   - **Decided (SIT FABLE #18): option (b).** `research/audit/eval_data_audit.md` is the verification for all 20 S-dev entries. `verified` stays false, and each entry's `verification_note` now says the audit was accepted. List `external_fact_verification` in `accepted` when you sign.
   - **Rule going forward (SIT FABLE #18):** an owner re-check with network access (option (a)) is required only for held-out keys, and, before Tier A, for any S-dev fact that a graded finding's credit turns on (the harness can list those from the pilot).
5. **Canary.** Methodology §1.1 rule 5 wants the per-split canary in every document and key. The GUID is in the keys only. Embedding it in `design_v*.md` and rebuilding the PDFs (`eval/build_pdfs.py`) would change the document hashes and the page text, so it was not done here. Either embed it, then set `authoring_drafts.item.canary_embedded_in_documents: true`; or accept a key-only canary by listing `canary_guid` in `accepted`, and record that choice for the LC10/LC11 canary scans.
   - **Decided (SIT FABLE #17): key-only for S-dev.** `design_v*.md` and the PDFs are not touched (the live run and the pilots cite their hashes and anchor pages, and S-dev is the open development set, so an embedded canary there protects nothing). `canary_embedded_in_documents` stays false; list `canary_guid` in `accepted` when you sign. The choice is recorded for the scans in `eval/prereg.yaml` LC10 and LC11 (`eval/prereg_deviations.md` entry 8).
   - **Rule going forward (SIT FABLE #17):** every future held-out item gets its split's canary embedded in its documents (and key) before its first run (`docs/SEALING.md` §3).
6. **Regenerate and check.** Run this from the repository root with the venv active:

   ```bash
   . .venv/bin/activate
   python3 spec/convert_answer_keys.py --tier synthetic --verify-anchors
   ```

   For each item it prints `pending: ...; scored_run_ready True|False`. A key that becomes ready always has its anchors re-checked, even without `--verify-anchors`, so the venv must be active. **`scored_run_ready` is never set by hand**; `python3 spec/convert_answer_keys.py --tier synthetic --check` fails if a canonical key on disk says `true` but differs from what the converter produces. The converter sets it to `true` exactly when `pending` is empty. The schema and `key_semantics` then refuse a key in which any flaw still lacks `core_insight`, `anchor_quote` or `expected_disposition`, or whose provenance is incomplete. Your name and date are added to `item.key_reviewed_by`. `--tier synthetic` keeps the run away from `eval/blind` (it neither lists nor opens it). Do not run the converter without `--tier synthetic` before the S-heldout keys are sealed.
7. Run `pytest -q`. Commit the three `answer_key.json`, the three `answer_key.canonical.json`, and the sheet hash.

## 5. Flaws

### 5.1 Payments orchestration (Serindit Pay MPOP): `synthetic-payments-orchestration-001` (15 flaws, credit mode `substance`)

#### F01 · critical (legacy critical) · internal_contradiction
- Location: §3 (P2); 5 (Figure 1 caption); 12.1; 12.2; 13.1 (NFR-5)
- **Core insight (draft):** The Fraud Hook is declared out of PCI DSS scope (Section 12.2, Principle P2), yet Section 13.1 has it detokenise the card and send the full card number (card_number) to FRV-1, so the Fraud Hook and the vendor actually handle PAN and fall inside the cardholder data environment, making the CDE boundary that NFR-5 relies on wrong.
- **Anchor** (design_v1.pdf p. 11): "The Fraud Hook obtains the PAN through the Vault's detokenise operation, using the Card Adapter client library and service role."
- **Expected disposition:** `refinement_now` (also acceptable: `needs_investigation`)
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F02 · low (legacy minor) · internal_contradiction
- Location: §2.2; 16.1; 16.2; 24; 26.2 (NFR-8)
- **Core insight (draft):** The last settlement file (ACQ-TH1) arrives at 06:30 ICT, which is 07:30 SGT, and the batch matcher (45 min) plus report generation (15 min) only start after it, so reports publish at about 08:30 SGT, after the 08:00 SGT deadline in NFR-8, and later as volume grows.
- **Anchor** (design_v1.pdf p. 13): "The batch matcher starts once all expected files for business day T have been received"
- **Expected disposition:** `refinement_now` (also acceptable: `governance_decision`)
- Linked approved decisions: AD-016
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F03 · high (legacy major) · internal_contradiction
- Location: §2.2; 20.2; 24; 26.2 (NFR-4)
- **Core insight (draft):** NFR-4 requires zero RPO even on loss of the whole AWS region, but the confirmed DR design replicates the payments and ledger database across regions asynchronously (Aurora Global Database, lag under about 1 s), so commits in the lag window are lost on regional failure and RPO cannot be zero. *(Edited by the verifier: the DynamoDB/MSK/Redis clause was dropped, because no credit item requires it and in `substance` mode every clause is required. W3's text added "and does not replicate DynamoDB, MSK or Redis at all".)*
- **Anchor** (design_v1.pdf p. 3): "Recovery point objective for authorized payments and ledger postings shall be zero, including on loss of an entire AWS region."
- **Expected disposition:** `governance_decision` (also acceptable: `refinement_now`)
- Linked approved decisions: AD-004
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F04 · high (legacy major) · unsupported_or_incorrect_claim
- Location: §9.2; 9.3; 24 (NFR-1, NFR-9, FR-5)
- **Core insight (draft, edited by SIT FABLE decision #19):** The 10,000 WCU per-partition claim is wrong (the limit is 1,000 WCU), so keying the idempotency table by merchant_id puts the largest merchant's peak writes on one partition key that will be throttled.
  - Before: Section 9.3 assumes a DynamoDB partition sustains 10,000 WCU/s, but the per-partition limit is 1,000 WCU (and 3,000 RCU), so keying the idempotency table by merchant_id puts the largest merchant's ~900 TPS (at least 1,800 WCU even on the document's own two-writes count) on one partition key that will be throttled.
- **Anchor** (design_v1.pdf p. 8): "DynamoDB serves each partition key value from a single partition, and a single partition sustains up to 10,000 write capacity units per second."
- **Expected disposition:** `refinement_now` (also acceptable: `needs_testing`)
- Linked approved decisions: AD-006
- ☐ accept ☒ edit ☐ reject - SIT FABLE (#19, for the owner): deleted "(and 3,000 RCU)", "at least 1,800 WCU" and "even on the document's own two-writes count"; the text is now SIT FABLE's "Keep" text verbatim (first letter capitalised). "~900 TPS" is not in the core insight: credit item c2 still names it, and a number a credit item needs lives in the credit item.

#### F05 · low (legacy minor) · unsupported_or_incorrect_claim
- Location: §21.1; 10.5; 11.2; 2.2 (NFR-2)
- **Core insight (draft):** The 1,338 ms p99 budget rests on the claim that fewer than 1% of card payments cascade, but Section 10.5 reports 3.8% retryable outcomes, all of which cascade, so the 99th percentile falls among cascaded payments (extra acquirer round trips, 2,500 ms timeouts) and NFR-2's 1,500 ms p99 is not met on the document's own figures.
- **Anchor** (design_v1.pdf p. 17): "Cascading does not move the p99 because fewer than 1% of card payments cascade; the cascade path therefore sits above the 99th percentile."
- **Expected disposition:** `refinement_now` (also acceptable: `needs_testing`)
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F06 · critical (legacy critical) · missing_or_unverifiable_requirement
- Location: §2.2; 12.4; 24; 26.2; 11.2 (NFR-6)
- **Core insight (draft):** NFR-6 and Section 12.4 claim PCI DSS v4.0 Requirements 3.2.1 and 3.3.2 allow the encrypted CVC to be kept until settlement, but PCI DSS forbids retaining sensitive authentication data, including the card verification code (Req. 3.3.1 and 3.3.1.2), after authorization even if encrypted, so keeping the CVC until settlement or for up to 72 hours is non-compliant.
- **Anchor** (design_v1.pdf p. 10): "This is permitted by PCI DSS v4.0 Requirements 3.2.1 and 3.3.2, which allow sensitive authentication data to be retained in encrypted form until the transaction is settled."
- **Expected disposition:** `refinement_now`
- Linked approved decisions: AD-009
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F07 · high (legacy major) · missing_or_unverifiable_requirement
- Location: §1; 2.2; 4; 19.1; 20.2; 24 (NFR-7)
- **Core insight (draft):** No requirement addresses data residency or localisation (NFR-7 covers privacy only), yet Indonesian payment data, the largest market, is stored and processed only in Singapore although Indonesian payment regulation may require domestic processing; the obligation has to be confirmed before the single-region data placement can be accepted.
- **Anchor** (design_v1.pdf p. 16): "All primary data stores (Aurora, DynamoDB, ElastiCache, MSK, S3 intake and archive buckets) are in ap-southeast-1."
- **Expected disposition:** `needs_investigation` (also acceptable: `governance_decision`)
- Linked approved decisions: AD-001
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F08 · critical (legacy critical) · security_privacy_gap
- Location: §18.2; 18.3; 18.4; 24 (FR-13)
- **Core insight (draft):** MFA is optional for every merchant role except Owner, yet a Finance user can change the payout bank account with no step-up, second approval or cooling-off, and only the person who made the change is notified, so one stolen Finance password lets an attacker redirect the merchant's payouts unnoticed.
- **Anchor** (design_v1.pdf p. 14): "TOTP multi-factor authentication is available to every user and is enforced for the Owner role at first login."
- **Expected disposition:** `refinement_now`
- Linked approved decisions: AD-018
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F09 · high (legacy major) · security_privacy_gap
- Location: §3 (P3); 9.1; 9.2; 24 (FR-5)
- **Core insight (draft):** The Redis fast-path key idem:resp:{idempotency_key} has no merchant identifier (contrary to P3 and the merchant-scoped DynamoDB key) and is checked first, so two merchants using the same key string, which is likely because merchants use their own order IDs, collide and one receives the other's stored payment response instead of having its payment processed.
- **Anchor** (design_v1.pdf p. 8): "On completion of a request, the final response is written to idem:resp:{idempotency_key} with a 24-hour TTL."
- **Expected disposition:** `refinement_now`
- Linked approved decisions: AD-006
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F10 · critical (legacy critical) · scalability_or_failure_mode
- Location: §11.1; 11.2; 20.3; 24 (FR-7, FR-5)
- **Core insight (draft):** Acquirer timeouts and 5xx responses after the request was sent are treated as retryable and cascaded to another acquirer with no status inquiry or reversal, although the first attempt may already have been approved, so the customer can be authorized and charged twice, and late approvals are discarded and never voided.
- **Anchor** (design_v1.pdf p. 9): "Because each attempt carries its own attempt_id and the previous attempt did not succeed, cascading cannot create a duplicate charge: the ledger records only the approved attempt."
- **Expected disposition:** `refinement_now` (also acceptable: `needs_investigation`)
- Linked approved decisions: AD-011
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F11 · high (legacy major) · scalability_or_failure_mode
- Location: §12.1; 12.3; 24; 20.1 (NFR-3)
- **Core insight (draft, edited by SIT FABLE decision #19):** Every card authorization needs an HSM unwrap with no DEK caching, and the cluster has one HSM in one AZ, so losing it stops all card payments, contrary to NFR-3.
  - Before: Every card authorization needs an HSM unwrap (no DEK caching) and the CloudHSM cluster has a single HSM in one AZ, so losing that HSM or AZ stops all card payments, contrary to NFR-3 and the three-AZ posture elsewhere; the 1,500 TPS trigger for a second HSM is above the design peak and never fires.
- **Anchor** (design_v1.pdf p. 10): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a."
- **Expected disposition:** `refinement_now`
- Linked approved decisions: AD-008
- ☐ accept ☒ edit ☐ reject - SIT FABLE (#19, for the owner): deleted the 1,500 TPS trigger clause and the secondary "three-AZ posture elsewhere" contradiction, which no credit item requires; the text is now SIT FABLE's "Keep" text verbatim (first letter capitalised).

#### F12 · low (legacy minor) · ambiguous_requirement
- Location: §2.1; 10.3; 24; 26.1 (FR-8)
- **Core insight (draft):** FR-8's 'reduces the expected authorization rate by more than 2%' is ambiguous in at least one way that changes routing outcomes, a per-transaction comparison of approval priors versus a merchant's realised authorization rate (Section 10.3 applies the same tolerance both ways), or 2 percentage points versus 2% relative, so the routing rule and its test cannot be implemented unambiguously. *(Edited by the verifier: W3's text required both ambiguities, but credit item c3 is "and/or", so one is enough.)*
- **Anchor** (design_v1.pdf p. 2): "For each transaction, the Routing Engine shall prefer the lowest-cost eligible acquirer unless doing so reduces the expected"
- **Expected disposition:** `refinement_now` (also acceptable: `governance_decision`)
- Linked approved decisions: AD-012
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F13 · high (legacy major) · acceptance_criterion_cannot_validate
- Location: §26.1; 2.1; 9 (FR-5)
- **Core insight (draft):** FR-5 requires at most one downstream operation when duplicate requests arrive concurrently, but its acceptance test resends the duplicate only after the first response is received (a sequential replay), so it cannot detect a broken concurrency lock.
- **Anchor** (design_v1.pdf p. 19): "Send a create-payment request; after its response is received, resend the identical request with the same"
- **Expected disposition:** `needs_testing` (also acceptable: `refinement_now`)
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F14 · low (legacy minor) · decision_depends_on_pending_item
- Location: §12.5; 24; 25 (item 2); 27; 28 (Phase 3) (FR-14)
- **Core insight (draft):** Network tokens are a confirmed, launch-ready decision (Section 24, Section 12.5, Build Phase 3 'No — ready'), yet Pending Backlog item 2 says the TRID registration and token-service-provider agreement have not been submitted and certification has not started, so the decision and the readiness ratings rest on an unresolved dependency.
- **Anchor** (design_v1.pdf p. 18): "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch; PAN"
- **Expected disposition:** `governance_decision` (also acceptable: `refinement_now`)
- Linked approved decisions: AD-010
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F15 · critical (legacy critical) · scalability_or_failure_mode · introduced in v2
- Location: §9.4; 20.2; 24 (FR-5, NFR-4)
- **Core insight (draft):** v2 makes the idempotency table a DynamoDB global table writable in both regions in multi-Region eventual consistency mode and claims the conditional put gives exactly one lock winner whichever region receives the request, but such conditional writes are checked only against the local replica and conflicts resolve last-writer-wins, so duplicates arriving in different regions can both acquire the lock and cause duplicate authorizations.
- **Anchor** (design_v2.pdf p. 8): "exactly one request can acquire the lock for a given merchant and key regardless of which region receives it"
- **Expected disposition:** `refinement_now` (also acceptable: `needs_investigation`)
- Linked approved decisions: AD-004, AD-006
- ☐ accept ☐ edit ☐ reject - SIT FABLE (#20, for the owner): linked to AD-004 (item 7 linking rule: F15 cites §20.2, which the DR row governs, and its defect is in the two-region write topology that row decides; #21).

### 5.2 Clinical remote patient monitoring (HPHC RPM-P): `synthetic-clinical-rpm-001` (15 flaws, credit mode `substance`)

#### F01 · low (legacy minor) · internal_contradiction
- Location: §2.2; 13.1; 20 (NFR-7, D-8)
- **Core insight (draft):** NFR-7 requires all PHI at rest to use customer-managed keys in Managed HSM, but D-8 and Section 13.1 put Azure Data Explorer, which holds every patient-attributed vital sign, on Microsoft-managed keys, so a confirmed decision breaks the NFR with no recorded waiver.
- **Anchor** (design_v1.pdf p. 18): "ADX: Microsoft-managed keys (CMK deferred to reduce key-management overhead on the ingestion cluster);"
- **Expected disposition:** `refinement_now` (also acceptable: `governance_decision`)
- Linked approved decisions: AD-008
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F02 · high (legacy major) · internal_contradiction
- Location: §3; 12.2; 20 (P4, P3, FR-11, D-14)
- **Core insight (draft):** Principle P4 says device observations enter the EMR as preliminary and become part of the legal record only after nurse validation, but Section 12.2 and D-14 post them with status final directly to the inpatient flowsheet, so unvalidated device data, including artefact, enters the legal medical record.
- **Anchor** (design_v1.pdf p. 11): "The EMR files these directly to the inpatient flowsheet, so they appear alongside nurse-entered observations without a nurse re-keying them."
- **Expected disposition:** `refinement_now`
- Linked approved decisions: AD-014
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F03 · high (legacy major) · internal_contradiction
- Location: §2.2; 3; 18.2; 20; 22.2 (NFR-4, NFR-9, P1, D-1)
- **Core insight (draft):** NFR-4 requires the alert pipeline to survive loss of the whole cloud region with an RTO of 15 minutes or less, but D-1 deploys a single region and Section 18.2 recovers only by redeploying an estimated 4-8 hours after the region returns, so the requirement cannot be met by the confirmed topology.
- **Anchor** (design_v1.pdf p. 17): "Platform recovery: redeploy from infrastructure-as-code and restore from zone-redundant backups when the region returns; estimated 4–8 hours after region availability."
- **Expected disposition:** `governance_decision` (also acceptable: `needs_investigation`)
- Linked approved decisions: AD-001
- ☒ accept ☐ edit ☐ reject - SIT FABLE (#19, for the owner): accepted as drafted (dropping c4 is right).

#### F04 · critical (legacy critical) · unsupported_or_incorrect_claim
- Location: §7.3; 20; 2.2 (NFR-1, D-2)
- **Core insight (draft):** Section 7.3 sizes IoT Hub as 3 S2 units at 60 M messages/day each and calls the send throttle non-binding, but an S2 unit allows 6 M messages/day and 120 device-to-cloud sends/s, so 3 S2 units (18 M/day, 360 msg/s) are far below the ~138 M/day and 1,600-2,000 msg/s needed and messages would be throttled and rejected, halting monitoring for most of each day.
- **Anchor** (design_v1.pdf p. 8): "At the S2 tier the device-to-cloud throttle is not a binding constraint at this message rate; the daily message quota is the sizing driver."
- **Expected disposition:** `refinement_now` (also acceptable: `needs_testing`)
- Linked approved decisions: AD-002
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F05 · high (legacy major) · unsupported_or_incorrect_claim
- Location: §10.4; 6.1; 8.3; 4.3 (NFR-2)
- **Core insight (draft):** The Section 10.4 budget concludes NFR-2 (10 s at p95) is met with 50% headroom, but it omits delays the design itself imposes, up to 5 s of on-device batching before publish and up to 10 s waiting for the 10-second tumbling window to close, so the headroom claim is unsupported and the target is unlikely to be met.
- **Anchor** (design_v1.pdf p. 10): "NFR-2 (≤ 10 s at p95) is therefore met with 5 s (50%) headroom."
- **Expected disposition:** `refinement_now` (also acceptable: `needs_testing`)
- ☒ accept ☐ edit ☐ reject - SIT FABLE (#19, for the owner): accepted as drafted; "up to" stands and c4 (push latency) is not required.

#### F06 · low (legacy minor) · missing_or_unverifiable_requirement
- Location: §2.1; 20 (FR-8, D-12)
- **Core insight (draft):** FR-8 says its escalation intervals (High 60 s and 120 s, Medium 5 min) are mandated by IEC 60601-1-8 clause 6.11, but that clause covers distributed alarm systems and sets no staff escalation intervals, so the requirement is traced to a source that does not support it.
- **Anchor** (design_v1.pdf p. 2): "These escalation intervals are mandated by IEC 60601-1-8, clause 6.11 (distributed alarm"
- **Expected disposition:** `refinement_now` (also acceptable: `governance_decision`)
- Linked approved decisions: AD-012
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F07 · low (legacy minor) · missing_or_unverifiable_requirement
- Location: §2.2; 17.1; 18.3; 22.2 (NFR-9)
- **Core insight (draft):** NFR-9 says onshore-only storage and processing is required by Section 26 of the PDPA, but Section 26 is the Transfer Limitation Obligation, which permits overseas transfer with comparable protection and does not mandate localisation, so the residency requirement is attributed to the wrong legal source.
- **Anchor** (design_v1.pdf p. 3): "by Section 26 of the Personal Data Protection Act 2012 (PDPA)."
- **Expected disposition:** `needs_investigation` (also acceptable: `refinement_now`)
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F08 · critical (legacy critical) · security_privacy_gap
- Location: §15.2; 20 (NFR-6, D-4)
- **Core insight (draft):** The DPS group enrollment key for each device class is embedded in the firmware image, so anyone who extracts it from one device or the image can derive valid keys for every device in the class, impersonate any patch and inject false vitals, defeating NFR-6's individual device authentication.
- **Anchor** (design_v1.pdf p. 15): "the group enrollment key is included in the signed firmware image and the device derives its own key at first boot."
- **Expected disposition:** `refinement_now`
- Linked approved decisions: AD-004
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F09 · high (legacy major) · security_privacy_gap
- Location: §17.4; 17.2; 20; 22.1 (FR-15, P8, D-19)
- **Core insight (draft, edited by SIT FABLE decision #19):** The 'anonymised' extracts remove only direct identifiers and keep strong quasi-identifiers, notably the full 6-digit home postal code, which in Singapore usually identifies a single building, together with demographics or exact timestamps, so patients remain re-identifiable and the data is still personal data; the claim that the extracts fall outside the PDPA, and their sharing to partner tenancies without per-extract approval, is therefore unjustified.
  - Before: The 'anonymised' extracts keep strong quasi-identifiers (full 6-digit home postal code, exact timestamps, ward and bed, age, sex, ethnicity), so patients remain re-identifiable and the data is still personal data, which makes the claim that the extracts fall outside the PDPA, and their sharing to partner tenancies without per-extract approval, unjustified.
- **Anchor** (design_v1.pdf p. 17): "Because direct identifiers are removed, extracts are anonymised data and fall outside the PDPA's obligations."
- **Expected disposition:** `refinement_now` (also acceptable: `governance_decision`)
- Linked approved decisions: AD-019
- ☐ accept ☒ edit ☐ reject - SIT FABLE (#19, for the owner): replaced with the verifier's proposed text in item 12; the full list of quasi-identifiers is not required.

#### F10 · critical (legacy critical) · scalability_or_failure_mode
- Location: §10.3; 18.1; 20; 2.2 (NFR-3, NFR-4, FR-8, D-10)
- **Core insight (draft):** The Alert Dispatcher, on the path of every notification and escalation, runs as a single replica holding deduplication state and escalation timers in memory, so a crash, restart or zone loss drops pending escalations, and with no end-to-end heartbeat a dead or stalled Dispatcher looks like a quiet ward; this single point of failure contradicts NFR-3 and NFR-4.
- **Anchor** (design_v1.pdf p. 10): "Deduplication state and escalation timers are held in process memory, which guarantees strict ordering of escalation steps and avoids the coordination cost of distributed timers."
- **Expected disposition:** `refinement_now` (also acceptable: `needs_testing`)
- Linked approved decisions: AD-010
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F11 · high (legacy major) · scalability_or_failure_mode
- Location: §8.2; 6.1; 7.2; 20 (FR-4, FR-9, D-6)
- **Core insight (draft):** Stream Analytics evaluates rules on device time with a 5-second late-arrival tolerance and drops late events, so readings replayed from the patch (30 min) or hub (4 h) buffers after a connectivity gap, and every reading from a device whose clock lags by more than about 5 s, are silently excluded from alert evaluation.
- **Anchor** (design_v1.pdf p. 9): "Late-arrival tolerance 5 s Keeps window outputs timely for the latency target"
- **Expected disposition:** `refinement_now` (also acceptable: `needs_testing`)
- Linked approved decisions: AD-006
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F12 · high (legacy major) · ambiguous_requirement
- Location: §2.1; 10.3; 20; 22.1 (FR-7, D-11)
- **Core insight (draft):** FR-7 does not define a 'duplicate' alert (any alert for the same patient, or the same patient and parameter or rule), so one valid reading suppresses a new or higher-priority alert raised within 5 minutes of a different one, and nothing in the document, including the FR-7 acceptance test (which uses identical alerts), settles which reading applies. *(Edited by the verifier: W3's text required both the window/clock gap and the test gap, but credit item c4 is "test does not disambiguate (or window semantics/clock unspecified)". The draft now requires only that nothing, including the test, settles the reading.)*
- **Anchor** (design_v1.pdf p. 2): "The Alert Service shall suppress duplicate alerts for the same patient within a 5-minute window, so that clinicians are not repeatedly"
- **Expected disposition:** `refinement_now` (also acceptable: `governance_decision`)
- Linked approved decisions: AD-011
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F13 · low (legacy minor) · acceptance_criterion_cannot_validate
- Location: §22.2; 2.2; 10.4 (NFR-2)
- **Core insight (draft):** The NFR-2 test measures from the IoT Hub enqueue timestamp to the alert row commit in PostgreSQL, whereas NFR-2 runs from sensor measurement to display on the clinician's device, so the test leaves out device batching, BLE, gateway and WAN transport and push delivery and cannot show NFR-2 is met.
- **Anchor** (design_v1.pdf p. 20): "time from IoT Hub enqueue timestamp to the alert row being committed in the alert store is ≤ 10 s"
- **Expected disposition:** `needs_testing` (also acceptable: `refinement_now`)
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F14 · critical (legacy critical) · decision_depends_on_pending_item
- Location: §20; 21; 9.1; 9.4; 23; 24 (B-3, FR-5, D-15)
- **Core insight (draft):** D-15 confirms EWS-ML as the primary deterioration alert for MIC@Home from Phase 4, and Phase 4 is marked ready, yet it depends on pending backlog item B-3 (HSA software-as-medical-device determination and prospective MIC@Home validation), and the model has been validated only on inpatients.
- **Anchor** (design_v1.pdf p. 18): "EWS-ML replaces pNEWS2 aggregate alerting as the primary deterioration alert for the MIC@Home cohort"
- **Expected disposition:** `governance_decision` (also acceptable: `needs_investigation`, `refinement_now`)
- Linked approved decisions: AD-015
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F15 · high (legacy major) · scalability_or_failure_mode · introduced in v2
- Location: §10.3 (NFR-2, NFR-3, D-10)
- **Core insight (draft):** v2's delivery assurance processes each ward's alert-delivery session in strict FIFO and never advances past an unconfirmed message, with no TTL and no dead-lettering, so one undeliverable notification blocks every later alert for that ward, including new High alerts, the queue grows without bound during an outage, and clinicians receive a burst of stale alerts on recovery.
- **Anchor** (design_v2.pdf p. 11): "The delivery worker processes each ward's session in strict FIFO order and does not advance past a message until its delivery is confirmed"
- **Expected disposition:** `refinement_now`
- Linked approved decisions: AD-010
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

### 5.3 Research data lakehouse (Westmoor RDLR): `synth-research-lakehouse-001` (15 flaws, credit mode `all_of`)

#### F01 · critical (legacy critical) · internal_contradiction
- Location: §2.2; 4; 14.4; 20 (NFR-5, FR-8)
- Required credit items: c1 "NFR-5 forbids processing Restricted content outside Westmoor AWS accounts"; c2 "generation model / external vendor API is used for Restricted tier (Section 14.4 / Section 20)"
- **Core insight (draft, edited by SIT FABLE decision #19):** NFR-5 forbids processing Restricted content outside Westmoor-controlled AWS accounts, yet Section 14.4 and the 'Generation model' decision send Restricted-tier chunks to a commercial LLM on the vendor's public endpoint.
  - Before: NFR-5 forbids processing Restricted content outside Westmoor-controlled AWS accounts, yet Section 14.4 and the 'Generation model' decision send Restricted-tier chunks to a commercial LLM on the vendor's public endpoint; zero-data-retention terms do not make that endpoint a Westmoor account.
- **Anchor** (design_v1.pdf p. 13): "The same model serves all eligible tiers (Public, Internal and Restricted); Controlled content is never indexed and so never reaches the model."
- **Expected disposition:** `refinement_now` (also acceptable: `governance_decision`)
- Linked approved decisions: AD-011
- ☐ accept ☒ edit ☐ reject - SIT FABLE (#19, for the owner): deleted the zero-data-retention clause (a supporting item, c4).

#### F02 · high (legacy major) · internal_contradiction
- Location: §2.1; 3; 8.3; 20 (FR-5, FR-10)
- Required credit items: c1 "FR-5 / P6 prohibit visibility of embargoed title/abstract/keywords/PI"; c2 "Section 8.3 Discovery Portal lists embargoed datasets with these fields"
- **Core insight (draft):** FR-5 and P6 require an embargoed dataset's descriptive metadata (title, abstract, keywords, PI name) to be invisible outside the owning project, but the Discovery Portal (Section 8.3 and its confirmed decision) lists every registered dataset, embargoed ones included, with exactly those fields to all researchers.
- **Anchor** (design_v1.pdf p. 8): "Every registered dataset, including embargoed and Restricted datasets, is listed with its title, PI, abstract, keywords, classification tier and embargo-lift date"
- **Expected disposition:** `refinement_now`
- Linked approved decisions: AD-016
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F03 · critical (legacy critical) · internal_contradiction
- Location: §2.2; 7.3; 13; 20 (NFR-7, FR-12, FR-11)
- Required credit items: c1 "Iceberg time travel / older snapshots still contain the participant's data"; c2 "400-day snapshot retention and indefinitely retained publication tags"
- **Core insight (draft):** Consent withdrawal deletes the participant's rows only in a new snapshot and verifies only the current snapshot, while older snapshots are kept 400 days and publication tags indefinitely (plus 90-day noncurrent S3 versions and replicas), so the data stays recoverable by time travel long after NFR-7's 30-day erasure deadline.
- **Anchor** (design_v1.pdf p. 11): "SELECT count(*) WHERE <participant_key> = :pseudonym on the current snapshot of each affected table returns 0."
- **Expected disposition:** `refinement_now` (also acceptable: `needs_testing`)
- Linked approved decisions: AD-006
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F04 · low (legacy minor) · unsupported_or_incorrect_claim
- Location: §17.1; 2.2 (NFR-9)
- Required credit items: c1 "Deep Archive Access tier in Intelligent-Tiering is opt-in / asynchronous (requires restore), not instant"; c2 "so 'no change in access latency' is false and incompatible with interactive query / reproducibility"
- **Core insight (draft):** The storage estimate assumes S3 Intelligent-Tiering moves 60% of bytes into the Deep Archive Access tier 'with no change in access latency', but that tier is opt-in and its objects must be restored, taking hours, before they can be read, so the claim is false and the tier cannot serve interactive queries or reproducibility.
- **Anchor** (design_v1.pdf p. 15): "with no retrieval charges and no change in access latency for the query engines."
- **Expected disposition:** `refinement_now` (also acceptable: `needs_investigation`)
- ☒ accept ☐ edit ☐ reject - SIT FABLE (#19, for the owner): accepted as drafted; the NFR-9 cost breach stays supporting (c3).

#### F05 · high (legacy major) · unsupported_or_incorrect_claim
- Location: §15; 17.1; 20 (NFR-1, NFR-3, NFR-9)
- Required credit items: c1 "float32 = 4 bytes per dimension (memory understated ~4x)" (c2 "HNSW memory formula / overhead ~1.1x(4d+8M)" is `supporting` since SIT FABLE #19)
- **Core insight (draft):** Section 15 sizes vector memory at 1 byte per dimension (180M x 1,024 = 184 GB), but float32 vectors take 4 bytes per dimension and faiss HNSW needs about 1.1 x (4d + 8M) bytes per vector, roughly 836 GB per copy, so the three-node OpenSearch domain is several times too small.
- **Anchor** (design_v1.pdf p. 14): "Vector data (180M × 1,024 dimensions) ≈ 184 GB"
- **Expected disposition:** `refinement_now` (also acceptable: `needs_prototyping`)
- Linked approved decisions: AD-010
- ☐ accept ☐ edit ☐ reject - SIT FABLE (#19, for the owner): c2 made `supporting` in `role_of()` (item 1). SIT FABLE (#22, for the owner): the core insight stands as drafted, because rule #19 is for `substance` mode and this flaw is scored `all_of` (item 10).

#### F06 · low (legacy minor) · missing_or_unverifiable_requirement
- Location: §2.2; 22.2 (NFR-6)
- Required credit items: c1 "3.1.1 is an access-control requirement, not encryption" (c2 "correct controls are 3.13.16 (CUI at rest) and/or 3.13.11 (FIPS-validated crypto)" is `supporting` since SIT FABLE #19)
- **Core insight (draft):** NFR-6 cites NIST SP 800-171 requirement 3.1.1 for customer-managed-key encryption with 90-day rotation, but 3.1.1 is an access-control requirement; protection of CUI at rest is 3.13.16 and FIPS-validated cryptography is 3.13.11, so the requirement is traced to the wrong control.
- **Anchor** (design_v1.pdf p. 3): "Datasets tagged CUI shall be encrypted at rest with customer-managed AWS KMS keys rotated every 90 days, as required by NIST"
- **Expected disposition:** `refinement_now`
- ☐ accept ☐ edit ☐ reject - SIT FABLE (#19, for the owner): c2 made `supporting` in `role_of()` (item 2). SIT FABLE (#22, for the owner): the core insight stands as drafted, because rule #19 is for `substance` mode and this flaw is scored `all_of` (item 10).

#### F07 · high (legacy major) · missing_or_unverifiable_requirement
- Location: §1; 2.1; 12.2; 22.1 (FR-7)
- Required credit items: c1 "scope (Section 1) promises end-of-term destruction/return"; c2 "no FR or AC covers DSA expiry/termination obligations"
- **Core insight (draft):** Section 1 promises DSA enforcement including end-of-term destruction or return of data, but no requirement, flow or acceptance test covers it: on expiry or termination the design only excludes the datasets from new access requests.
- **Anchor** (design_v1.pdf p. 11): "DSA record status updated; covered datasets excluded from new access requests."
- **Expected disposition:** `refinement_now`
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F08 · critical (legacy critical) · security_privacy_gap
- Location: §11; 20; 16 (FR-4, FR-15, FR-14)
- Required credit items: c1 "shared faculty-level service principal / credential"; c2 "bypasses project-scoped access (FR-4, P1)"
- **Core insight (draft):** Notebook kernels use a faculty-wide service principal holding the union of the faculty's project roles, with its secret injected into every notebook pod, so any researcher in the faculty can read every project's data, bypassing the project-scoped access of FR-4 and P1.
- **Anchor** (design_v1.pdf p. 10): "The service principal is granted the union of the faculty's project roles, and the individual user's identity is recorded in the JupyterHub access log."
- **Expected disposition:** `refinement_now`
- Linked approved decisions: AD-008
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F09 · critical (legacy critical) · security_privacy_gap
- Location: §14.5; 20; 22.1; 3 (FR-9, FR-5, FR-7, FR-4)
- Required credit items: c1 "cache scoped by faculty, not by user entitlement set"; c2 "cached answers/citations from restricted or embargoed content served to non-entitled users"
- **Core insight (draft):** The Scholar Assist answer cache is keyed by faculty and query embedding rather than by the requester's entitlements, so an answer and citations generated from one user's restricted, embargoed or DSA-limited content are served to other users in the same faculty who are not entitled to that content.
- **Anchor** (design_v1.pdf p. 13): "Scholar Assist caches generated answers, with their citations, in Amazon ElastiCache (Redis), keyed by faculty and query embedding."
- **Expected disposition:** `refinement_now`
- Linked approved decisions: AD-012
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F10 · high (legacy major) · scalability_or_failure_mode
- Location: §8.1; 18; 2.2 (NFR-2)
- Required credit items: c1 "catalog is a single point of failure on every data path"; c2 "metastore Single-AZ RDS"
- **Core insight (draft):** The Polaris catalog is on the path of every data operation (table loads, commits, credential vending, entitlement lookups), and its metastore is a single Single-AZ RDS instance, so it is a platform-wide single point of failure.
- **Anchor** (design_v1.pdf p. 8): "The metastore is a single Amazon RDS for PostgreSQL instance (db.r6g.xlarge, Single-AZ, gp3 storage)"
- **Expected disposition:** `refinement_now`
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F11 · high (legacy major) · scalability_or_failure_mode
- Location: §14.7; 20; 2.2 (NFR-4, FR-8, NFR-3)
- Required credit items: c1 "mixed embedding spaces in one index during migration"; c2 "query model switched before corpus re-embedded"
- **Core insight (draft):** A model or chunking change re-embeds the live index in place while queries switch to the new model at the start of the ~25-hour run, so throughout the run new-model query vectors are compared with mostly old-model document vectors from a different embedding space and retrieval breaks down.
- **Anchor** (design_v1.pdf p. 14): "Query embedding switches to the new model at the start of the run."
- **Expected disposition:** `refinement_now`
- Linked approved decisions: AD-013
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F12 · low (legacy minor) · ambiguous_requirement
- Location: §2.1; 12.1 (FR-6)
- Required credit items: c1 "static copy of lift date vs dynamic inheritance following source changes"; c2 "embargo extensions make the readings diverge"
- **Core insight (draft):** FR-6 does not say whether a derived dataset copies its source's embargo lift date once or keeps following the source's embargo, and the two readings diverge when a PI extends a source embargo, which Section 12.1 allows, releasing derived data early under the copy reading.
- **Anchor** (design_v1.pdf p. 2): "A dataset derived from one or more embargoed datasets shall inherit the embargo of its source dataset(s)."
- **Expected disposition:** `refinement_now` (also acceptable: `governance_decision`)
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F13 · low (legacy minor) · acceptance_criterion_cannot_validate
- Location: §22.2; 17.2; 2.2 (NFR-10)
- Required credit items: c1 "AC tests total reconciliation, not attribution share"; c2 "an unattributed/shared line of any size would pass"
- **Core insight (draft):** The NFR-10 acceptance criterion only checks that the chargeback total reconciles to the AWS Cost and Usage Report within 1%, which a report with an unattributed shared line of any size passes, so it cannot show that at least 95% of cost is attributed to projects.
- **Anchor** (design_v1.pdf p. 19): "The monthly chargeback report total reconciles to within 1% of the AWS Cost and Usage Report total for the"
- **Expected disposition:** `needs_testing` (also acceptable: `refinement_now`)
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F14 · high (legacy major) · decision_depends_on_pending_item
- Location: §20; 21; 10.2; 23; 24 (FR-4, FR-15)
- Required credit items: c1 "Section 20 confirmed decision (OPA single PDP / no Lake Formation)"; c2 "depends on Pending Backlog item 1 (Spark enforcement)"
- **Core insight (draft):** Section 20 confirms OPA as the single policy decision point with Lake Formation not used, but Pending Backlog item 1 is still deciding whether Spark can enforce row and column policies at all and says Lake Formation would then replace OPA for Trino too, so the confirmed decision depends on an open item.
- **Anchor** (design_v1.pdf p. 17): "OPA as the single policy decision point for Trino, Spark and Scholar Assist; Trino OPA plugin and RDLR Spark"
- **Expected disposition:** `governance_decision` (also acceptable: `needs_investigation`, `refinement_now`)
- Linked approved decisions: AD-004
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

#### F15 · critical (legacy critical) · scalability_or_failure_mode · introduced in v2
- Location: §8.1; 18; 20 (NFR-2, NFR-11, FR-3, FR-4)
- Required credit items: c1 "Iceberg requires single-writer atomic CAS on metadata pointer"; c2 "bidirectional async replication with last-writer-wins allows conflicting commits / lost updates"
- **Core insight (draft):** v2 runs active-active Polaris catalogs in two regions whose metastores are synchronised by bidirectional DMS replication with last-writer-wins, but Iceberg commit safety relies on an atomic compare-and-swap of the metadata pointer in one authoritative catalog, so concurrent commits to a table in both regions both succeed and one is silently lost.
- **Anchor** (design_v2.pdf p. 8): "The two metastores are kept in sync by AWS DMS ongoing replication in both directions, with last-writer-wins conflict resolution on the row update timestamp, so either region can accept catalog commits."
- **Expected disposition:** `refinement_now`
- Linked approved decisions: AD-003, AD-017
- ☐ accept ☐ edit ☐ reject — new text / note: ____________________

## 6. Approved decisions

Each row is a Confirmed Decisions table row from design_v1. `statement` is the row text (markup removed). `doc_ref` is the document's own decision ID (clinical `D-n`) or, where the table has no IDs, the row label. The harness matches it as a substring of a finding's registry `doc_ref`. `flaw_ids` lists the gold flaws anchored on that row; a row with no flaw is a sound decision that a review should preserve, and challenging it without full evidence counts as an approved-decision violation (metrics §6.3). A v2-only flaw is linked to the row whose v2 text carries it. The statements are v1 text: the v2 rows that changed are listed in section 7.

### 6.1 Payments orchestration (Serindit Pay MPOP) (19 rows, 10 anchored on a flaw)

| ID | doc_ref | Statement | Anchor page | flaw_ids | Accept? |
|---|---|---|---|---|---|
| AD-001 | Cloud and primary region | Cloud and primary region: AWS, ap-southeast-1 (Singapore), three AZs | 18 | F07 | ☐ |
| AD-002 | Compute | Compute: Amazon EKS; CDE on a separate EKS cluster in a separate AWS account | 18 | — (sound) | ☐ |
| AD-003 | Payments and ledger store | Payments and ledger store: Aurora PostgreSQL 16, db.r7g.12xlarge, writer + 2 readers | 18 | — (sound) | ☐ |
| AD-004 | Disaster recovery | Disaster recovery: Aurora Global Database secondary in ap-southeast-3; runbook failover, 30-minute target | 18 | F03, F15 (F15 linked by SIT FABLE #20) | ☐ |
| AD-005 | Event bus | Event bus: Amazon MSK, 3 brokers, RF 3 | 18 | — (sound) | ☐ |
| AD-006 | Idempotency store | Idempotency store: Redis fast path (idem:resp:{key}) + DynamoDB payments-idempotency (PK merchant_id, SK idempotency_key, LSI on created_at) | 18 | F04, F09, F15 | ☐ |
| AD-007 | Idempotency retention | Idempotency retention: 24 hours | 18 | — (sound) | ☐ |
| AD-008 | Vault | Vault: In-house, envelope encryption, KEKs in AWS CloudHSM (one HSM at launch) | 18 | F11 | ☐ |
| AD-009 | CVC handling | CVC handling: Encrypted in Vault until settlement, max 72 hours | 18 | F06 | ☐ |
| AD-010 | Card-on-file credential | Card-on-file credential: Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch; PAN fallback only where issuer unsupported | 18 | F14 | ☐ |
| AD-011 | Cascade policy | Cascade policy: Up to 2 additional attempts; triggers: soft declines 05/91/96, 5xx, connection refused, 2,500 ms timeout | 18 | F10 | ☐ |
| AD-012 | Routing | Routing: Weighted cost/approval/latency score; cost-preferred within 2 tolerance | 18 | F12 | ☐ |
| AD-013 | Fraud | Fraud: FRV-1, synchronous, 150 ms timeout, risk-tier fallback | 18 | — (sound) | ☐ |
| AD-014 | Ledger | Ledger: Double-entry, append-only, same transaction as state change, outbox | 19 | — (sound) | ☐ |
| AD-015 | Money representation | Money representation: Signed 64-bit integer minor units + ISO 4217 code | 19 | — (sound) | ☐ |
| AD-016 | Reconciliation | Reconciliation: Daily batch after all files received; three-way match | 19 | F02 | ☐ |
| AD-017 | Webhooks | Webhooks: At-least-once, HMAC-SHA256 timestamped signatures, 72-hour bounded retry, DLQ + replay | 19 | — (sound) | ☐ |
| AD-018 | Merchant user MFA | Merchant user MFA: TOTP; enforced for Owner, optional for other roles | 19 | F08 | ☐ |
| AD-019 | Back-office access | Back-office access: Corporate SSO + hardware MFA; JIT elevation with second approver | 19 | — (sound) | ☐ |

### 6.2 Clinical remote patient monitoring (HPHC RPM-P) (20 rows, 11 anchored on a flaw)

| ID | doc_ref | Statement | Anchor page | flaw_ids | Accept? |
|---|---|---|---|---|---|
| AD-001 | D-1 | Cloud and region: Azure Southeast Asia (Singapore), zone-redundant across 3 AZs; single region, no secondary region | 18 | F03 | ☐ |
| AD-002 | D-2 | Ingestion: Azure IoT Hub, S2 tier × 3 units, with DPS | 18 | F04 | ☐ |
| AD-003 | D-3 | Device protocol: MQTT 3.1.1 over TLS 1.2, port 8883 | 18 | — (sound) | ☐ |
| AD-004 | D-4 | Device credentials: DPS symmetric-key group enrollment per device class; gateways and hubs on X.509 | 18 | F08 | ☐ |
| AD-005 | D-5 | Ward patch connectivity: BLE to IoT Edge transparent gateways | 18 | — (sound) | ☐ |
| AD-006 | D-6 | Stream evaluation: Azure Stream Analytics, event time = device_ts, out-of-order and late events outside tolerance dropped | 18 | F11 | ☐ |
| AD-007 | D-7 | Time-series store: Azure Data Explorer, 90-day retention, export to ADLS | 18 | — (sound) | ☐ |
| AD-008 | D-8 | Encryption at rest: ADX: Microsoft-managed keys (CMK deferred to reduce key-management overhead on the ingestion cluster); PostgreSQL, ADLS, audit: CMK in Managed HSM | 18 | F01 | ☐ |
| AD-009 | D-9 | Alert store: PostgreSQL Flexible Server, zone-redundant HA | 18 | — (sound) | ☐ |
| AD-010 | D-10 | Alert Dispatcher topology: Single replica, in-memory dedup and escalation timers, liveness-probe restart | 18 | F10, F15 | ☐ |
| AD-011 | D-11 | Deduplication window: 5 minutes (FR-7) | 18 | F12 | ☐ |
| AD-012 | D-12 | Escalation timings: High: 60 s / 120 s; Medium: 5 min (FR-8) | 18 | F06 | ☐ |
| AD-013 | D-13 | Notification channels: Clinician mobile app via Notification Hubs; on-prem paging gateway for High priority | 18 | — (sound) | ☐ |
| AD-014 | D-14 | Outbound EMR integration: FHIR R4 Observation Bundle every 15 min per bound patient, status final, filed to flowsheet | 18 | F02 | ☐ |
| AD-015 | D-15 | EWS-ML for MIC@Home: EWS-ML replaces pNEWS2 aggregate alerting as the primary deterioration alert for the MIC@Home cohort from Phase 4; hard thresholds retained | 18 | F14 | ☐ |
| AD-016 | D-16 | pNEWS2: Partial score with freshness rules (Section 4.2), CSB-2026-014 | 18 | — (sound) | ☐ |
| AD-017 | D-17 | Skin temperature: Displayed as trend only; not used in NEWS2 or published to EMR | 18 | — (sound) | ☐ |
| AD-018 | D-18 | Attribution: Binding table join; devices carry no patient identifiers | 18 | — (sound) | ☐ |
| AD-019 | D-19 | Research extracts: Anonymised per Section 17.4; shareable with approved ML partners | 18 | F09 | ☐ |
| AD-020 | D-20 | Firmware: Dual-signed, staged rollout, AVAILABLE devices only | 18 | — (sound) | ☐ |

### 6.3 Research data lakehouse (Westmoor RDLR) (18 rows, 10 anchored on a flaw)

| ID | doc_ref | Statement | Anchor page | flaw_ids | Accept? |
|---|---|---|---|---|---|
| AD-001 | Cloud and primary region | Cloud and primary region: AWS, us-east-1; DR region us-west-2 | 17 | — (sound) | ☐ |
| AD-002 | Table format | Table format: Apache Iceberg v2, Parquet / ZSTD | 17 | — (sound) | ☐ |
| AD-003 | Catalog | Catalog: Apache Polaris (Iceberg REST), metastore on Amazon RDS for PostgreSQL | 17 | F15 | ☐ |
| AD-004 | Fine-grained policy | Fine-grained policy: OPA as the single policy decision point for Trino, Spark and Scholar Assist; Trino OPA plugin and RDLR Spark extension; Lake Formation not used | 17 | F14 | ☐ |
| AD-005 | Ingestion pattern | Ingestion pattern: Write-audit-publish with Iceberg branches | 17 | — (sound) | ☐ |
| AD-006 | Snapshot retention | Snapshot retention: 400 days; publication tags retained indefinitely | 17 | F03 | ☐ |
| AD-007 | Classification tiers | Classification tiers: Public / Internal / Restricted / Controlled; Controlled in separate enclave account | 17 | — (sound) | ☐ |
| AD-008 | Notebook credentials | Notebook credentials: Faculty analytics service principal per faculty | 17 | F08 | ☐ |
| AD-009 | Embedding model | Embedding model: BAAI bge-m3, 1,024-dim, self-hosted on g5 instances | 17 | — (sound) | ☐ |
| AD-010 | Vector store | Vector store: Amazon OpenSearch Service, faiss HNSW (M = 16), hybrid with BM25 | 17 | F05 | ☐ |
| AD-011 | Generation model | Generation model: Commercial frontier LLM via vendor enterprise API, zero-data-retention terms, for Public, Internal and Restricted content | 17 | F01 | ☐ |
| AD-012 | Answer cache | Answer cache: ElastiCache, faculty-scoped, cosine ≥ 0.97, 24 h TTL | 17 | F09 | ☐ |
| AD-013 | Re-embedding strategy | Re-embedding strategy: Full in-place re-embed on model or chunking change | 17 | F11 | ☐ |
| AD-014 | Primary storage class | Primary storage class: S3 Intelligent-Tiering | 17 | — (sound) | ☐ |
| AD-015 | Audit store | Audit store: Separate account, S3 Object Lock compliance mode, 7 years, hash-chained daily manifests | 17 | — (sound) | ☐ |
| AD-016 | Discovery Portal | Discovery Portal: OpenMetadata; all registered datasets listed with descriptive metadata | 18 | F02 | ☐ |
| AD-017 | DR | DR: CRR to us-west-2 (Glacier Instant Retrieval), MRAP failover, nightly catalog snapshot copy | 18 | F15 | ☐ |
| AD-018 | External collaborators | External collaborators: InCommon / eduGAIN federation; Analyst role only | 18 | — (sound) | ☐ |

## 7. v2 changed sections and sound-section annotations

### 7.1 Payments orchestration (Serindit Pay MPOP)

- `v2.changed_sections`: `2.1 (FR-8)`; `2.2 (NFR-4, NFR-6, NFR-8)`; `9.2`; `9.3`; `9.4 (new section)`; `10.3`; `11.2`; `12.4`; `16.2`; `18.2`; `18.3`; `18.4`; `19.1`; `20.2`; `24 (Disaster recovery, Idempotency store, CVC handling, Routing, Reconciliation, Merchant user MFA)`; `26.1 (FR-8, FR-13)`; `26.2 (NFR-4, NFR-6, NFR-8)` ☐ accept
- `v2.expected_open_flaw_ids` (derived, unchanged): F01, F05, F07, F09, F10, F11, F13, F14, F15
- S01 `14 Ledger and Double-Entry Accounting`: overlapping flaws none
- S02 `15 Amounts, Currencies and FX`: overlapping flaws none
- S03 `17 Merchant Webhooks`: overlapping flaws none
- S04 `18.5 Back-office console`: overlapping flaws none
- S05 `23 Prior Art and Reference Architecture`: overlapping flaws none
- Overlap check: every flaw location that intersects a sound-section location (harness `sit_eval.locations` rules) is annotated; the remaining annotations (clinical F06/§4, lakehouse F15/§9, F05/§14.6) are semantic links from spec/README.md §2.7. ☐ accept

### 7.2 Clinical remote patient monitoring (HPHC RPM-P)

- `v2.changed_sections`: `2.1 (FR-7)`; `2.2 (NFR-9)`; `7.3`; `10.3`; `12.2`; `14.5`; `15.2`; `17.1`; `20 (D-2, D-4, D-10, D-11, D-14)`; `22.1 (FR-7, FR-8, FR-11)`; `22.2 (NFR-3)`; `23 (Alert Service and Dispatcher row)` ☐ accept
- `v2.expected_open_flaw_ids` (derived, unchanged): F01, F03, F05, F06, F09, F11, F13, F14, F15
- S01 `4 Clinical Alerting Model / 4.2 Partial NEWS2 (pNEWS2) / 4.3 Priority mapping`: overlapping flaws F05, F06
- S02 `6.2 (Message envelope)`: overlapping flaws none
- S03 `14 (Device Lifecycle Management)`: overlapping flaws none
- S04 `16 (Identity, Access Control and Break-Glass)`: overlapping flaws none
- S05 `19 (Prior Art and Reference Architecture)`: overlapping flaws none
- Overlap check: every flaw location that intersects a sound-section location (harness `sit_eval.locations` rules) is annotated; the remaining annotations (clinical F06/§4, lakehouse F15/§9, F05/§14.6) are semantic links from spec/README.md §2.7. ☐ accept

### 7.3 Research data lakehouse (Westmoor RDLR)

- `v2.changed_sections`: `2.2 (NFR-6, NFR-9)`; `7.3`; `8.1`; `11`; `13`; `15`; `17.1`; `18 (Region loss)`; `20 (Catalog, Snapshot retention, Notebook credentials, Vector store, DR)`; `22.2 (NFR-9, NFR-10)` ☐ accept
- `v2.expected_open_flaw_ids` (derived, unchanged): F01, F02, F04, F07, F09, F11, F12, F14, F15
- S01 `4 Data Classification Tiers`: overlapping flaws F01
- S02 `9 Ingestion — Write-Audit-Publish`: overlapping flaws F15
- S03 `14.6 Latency budget`: overlapping flaws F05
- S04 `16 Audit Plane (Pipeline and storage) / 16 Audit Plane (Content boundaries)`: overlapping flaws F08
- S05 `6 Identity, Projects and Roles`: overlapping flaws none
- Overlap check: every flaw location that intersects a sound-section location (harness `sit_eval.locations` rules) is annotated; the remaining annotations (clinical F06/§4, lakehouse F15/§9, F05/§14.6) are semantic links from spec/README.md §2.7. ☐ accept

## 8. External facts (restated claims; all `verified: false`)

SIT FABLE (#18, for the owner) accepted `research/audit/eval_data_audit.md` as the verification for all 20 rows below (section 4, step 4); `verified` stays false and each entry's note says so.

| Item | Flaw | Claim (draft) | Audit verdict and source class | Accept? |
|---|---|---|---|---|
| payments_orchestration | F01 | Under PCI DSS v4.0 any system component that stores, processes or transmits PAN is part of the cardholder data environment, and a third party that receives PAN is a third-party service provider that must be managed under Requirement 12.8 (with its own Attestation of Compliance). BIN8 plus last 4 is acceptable truncation outside the CDE. | verdict C (key correct), source class K/S | ☐ |
| payments_orchestration | F04 | A single DynamoDB partition supports at most 1,000 write capacity units and 3,000 read capacity units per second, and on-demand mode does not lift this; a write costs 1 WCU per KB of item size; with a local secondary index, adaptive capacity cannot split an item collection across partitions and each partition key value is limited to 10 GB. | verdict C (key correct), source class P (awsdocs GitHub mirror, archived 2023) | ☐ |
| payments_orchestration | F06 | PCI DSS v4.0 Requirement 3.3.1 (with 3.3.1.2 for the card verification code) forbids retaining sensitive authentication data after authorization is complete, even if encrypted. Requirement 3.3.2 only requires SAD stored before completion of authorization to be encrypted with strong cryptography, and Requirement 3.2.1 covers the retention policy for SAD stored prior to completion of authorization. | verdict C (key correct), source class S | ☐ |
| payments_orchestration | F07 | Bank Indonesia regulation PBI 22/23/PBI/2020 requires domestic payment transactions (initiation, authorization, clearing and settlement) to be processed in Indonesia, and Government Regulation 71/2019 can impose localisation duties on electronic system operators, so offshore processing of Indonesian payment data may be prohibited or need regulator approval. | verdict C (hedged wording appropriate), source class P-snippet/S | ☐ |
| payments_orchestration | F11 | AWS recommends that production CloudHSM clusters have at least two HSMs in different Availability Zones (and at least three for durability of newly generated keys). | verdict C (key correct), source class P (awsdocs GitHub mirror, archived 2023) | ☐ |
| payments_orchestration | F15 | DynamoDB global tables in multi-Region eventual consistency (MREC) mode replicate asynchronously and resolve conflicting writes last-writer-wins; condition expressions are evaluated against the replica in the Region that receives the write, so they do not coordinate across Regions. Only multi-Region strong consistency (MRSC), available in fixed Region sets, evaluates writes against the latest write from any Region. | verdict C (key correct), source class P (LWW, local-Region conditions) and P-snippet (MRSC) | ☐ |
| clinical_rpm | F01 | Azure Data Explorer supports encryption at rest with customer-managed keys, so running it on Microsoft-managed keys is a key-custody choice, not a platform limitation. | verdict C (K, page not fetched), source class K | ☐ |
| clinical_rpm | F03 | Microsoft Azure has a single region in Singapore (Southeast Asia, three availability zones); the other Azure regions in the area are in other countries, so no onshore secondary Azure region exists. | verdict C (key correct), source class S | ☐ |
| clinical_rpm | F04 | An Azure IoT Hub S2 unit allows 6,000,000 messages per day and 120 device-to-cloud send operations per second; an S3 unit allows 300,000,000 messages per day and 6,000 sends per second (daily quota metered in 4 KB blocks on paid tiers). | verdict C (key correct), source class P (MicrosoftDocs azure-docs, ms.date 2025) | ☐ |
| clinical_rpm | F06 | IEC 60601-1-8 clause 6.11 deals with distributed alarm systems (delivery of alarm conditions to remote equipment and detection or indication of communication failure); it does not prescribe staff escalation intervals. | verdict C (key correct), source class S (standard is paywalled) | ☐ |
| clinical_rpm | F07 | Section 26 of Singapore's PDPA 2012 is the Transfer Limitation Obligation: it permits transfers of personal data outside Singapore when the organisation ensures a comparable standard of protection (Personal Data Protection Regulations 2021); the PDPA contains no general data-localisation mandate. | verdict C (key correct), source class S | ☐ |
| clinical_rpm | F08 | Microsoft's DPS guidance for symmetric-key group enrollments is to derive device keys and install them in the factory so the group key is never included in software deployed to devices; a compromised group key can compromise every device in the enrollment. | verdict C (key correct), source class P (MicrosoftDocs azure-docs) | ☐ |
| clinical_rpm | F09 | Under PDPC anonymisation guidance, data that carries a serious possibility of re-identification, for example through quasi-identifiers such as a full postal code combined with demographics, remains personal data under the PDPA; a 6-digit Singapore postal code usually identifies a single building. | verdict C (K, not fetched), source class K | ☐ |
| clinical_rpm | F11 | Azure Stream Analytics compares each event's event time with its arrival time; events outside the late-arrival tolerance window are dropped or adjusted according to the configured policy, and events more than 5 minutes early are always dropped or adjusted. | verdict C (key correct), source class P (MicrosoftDocs azure-docs, ms.date 2026) | ☐ |
| clinical_rpm | F15 | An Azure Service Bus queue or topic that reaches its maximum entity size rejects further sends (QuotaExceededException); the maximum size is 1-80 GB depending on tier and configuration. | verdict C (key correct), source class S/P-snippet | ☐ |
| research_lakehouse | F04 | In S3 Intelligent-Tiering the Archive Access and Deep Archive Access tiers are opt-in, and objects in them must be restored before they can be read (Deep Archive Access standard retrieval within 12 hours); objects smaller than 128 KB are never auto-tiered; monitoring and automation cost USD 0.0025 per 1,000 objects per month (us-east-1). | verdict C (key correct), source class P (archived mirror) and S/P-snippet | ☐ |
| research_lakehouse | F05 | OpenSearch estimates faiss HNSW native memory as about 1.1 x (4 x dimension + 8 x M) bytes per float32 vector, a replica doubles the vectors held, and the k-NN plugin may use only about 50% of the RAM left after the JVM heap (circuit breaker). | verdict C (key correct), source class P (opensearch-project documentation-website) | ☐ |
| research_lakehouse | F06 | NIST SP 800-171 Rev. 2 requirement 3.1.1 is 'Limit system access to authorized users, processes acting on behalf of authorized users, and devices' (access control); protecting the confidentiality of CUI at rest is 3.13.16 and FIPS-validated cryptography is 3.13.11; SP 800-171 sets no 90-day key-rotation period. | verdict C (key correct), source class S | ☐ |
| research_lakehouse | F10 | The Amazon RDS service level agreement commits to 99.95% monthly uptime for Multi-AZ DB instances but only 99.5% for Single-AZ (single-instance) deployments, below a 99.9% target. | verdict C (key correct), source class P-snippet | ☐ |
| research_lakehouse | F15 | Apache Iceberg makes commits safe through optimistic concurrency: a commit succeeds only by atomically swapping the table's current metadata pointer in one catalog (compare-and-swap); two catalogs that each accept commits and replicate asynchronously with last-writer-wins cannot provide that guarantee. | verdict C (reasoning), source class K | ☐ |

## 9. Files this sheet describes (sha256 after the SIT FABLE decisions were applied, 2026-10-03)

| File | sha256 |
|---|---|
| `eval/synthetic/payments_orchestration/answer_key.json` | `5a04fba0c23e6161418520b15c4d87ac549de2ed1891a7c4c73165c072487886` |
| `eval/synthetic/clinical_rpm/answer_key.json` | `64c71a6de410a544c89ac3fc8899c2ad129823140ed1e6388f9798c3631ebb54` |
| `eval/synthetic/research_lakehouse/answer_key.json` | `56ca982cdf4b136af1ddbcf2a1386d512dac9198687c8a6ccfa8043dccca2a51` |
| `eval/synthetic/payments_orchestration/answer_key.canonical.json` | `8eda2e5de12e54e98b2e4e4b242a2f86e8da7b8aa534594b363fa45ac4705011` |
| `eval/synthetic/clinical_rpm/answer_key.canonical.json` | `44833c1c01d8e89918c67991910ae583d6efc4aa22cdea8d20e4a436e7878735` |
| `eval/synthetic/research_lakehouse/answer_key.canonical.json` | `7c92bf91252858da076636b9e70bf4623fe049df4ab3a4e894e42c591bcce52a` |
| `spec/convert_answer_keys.py` (sets the credit-item roles) | `ce2eff3382af27950ac05c71d73e74b177160ababf6a6d63ece97c6694cd120e` |

Check with `shasum -a 256 <file>` (or `sha256sum`). The converter's hash changed on 2026-10-03 (close-out pass): it now tells the spec self-test whether to include `eval/blind` (only when the blind tier is converted); the credit-item roles and the three canonical keys it produces are unchanged. Signing changes the three `answer_key.json` (the `signoff` block) and the canonical keys, so after you sign these values describe the reviewed, unsigned state. This sheet's own hash cannot be written inside it; it is recorded in the message of the last commit that changed this sheet (the close-out pass of 2026-10-03, which wrote decisions #21 and #22 here) and in `docs/transcripts/session4/keys_closeout.md`.

## 10. Signature

Signed (name, date): ______________________ Sheet sha256: ______________________
