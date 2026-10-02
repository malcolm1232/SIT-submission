# Verification of eval dataset corrections

Date: 2026-10-02. Scope: `eval/` after the corrections logged in `research/audit/eval_fixes_applied.md`, checked against the fix list in `research/audit/eval_data_audit.md`. `spec/` and `answer_key.canonical.json` were not touched (another verifier owns them). No git commands were run.

Method notes:
- **Blind read first.** For item 6, I read all five design documents (blind `design.md` ×2 and synthetic `design_v1.md` ×3) before opening the audit, the change log or any key. I recorded my top-5 lists in a scratch file before looking at anything else.
- **Pre-edit snapshot.** The fix agent left a snapshot of `eval/` at `scratchpad/orig/eval`. I used it read-only to diff every key and document. The diff shows exactly the field changes C01–C52 and design edits D01–D02 from the change log, and nothing else.
- **Source quality labels**, as in the audit:
  - P: primary text, fetched.
  - P-snippet: official text seen only as a search-engine extract.
  - S: reputable secondary source.
  - K: known, not fetched.

---

## 1. Fix-by-fix check

### 1.1 Table

| Audit item | Claimed fix (change log) | Verified | Note |
|---|---|---|---|
| P0-1 item_a D01 legal statement | C01–C05: per-regime `external_fact`, `title`, `why_it_matters`, `credit_requires` (accepts EU 13(1)/(3), UK 34(5), or 34(6)/collection), `acceptable_fix` | **Yes**, plus one corrective edit (E1) | The legal content matches the sources (see 1.2). The original `acceptable_fix` "single conservative rule" was lawful only under the lenient reading of the collection-offer point, because it let UK/DE label returns be deferred until receipt or scan. Rewritten (E1). |
| P0-2 lakehouse sound §16 rationale | C46–C48: `why_sound` correction (Recital 26, Art. 17(3) b/d/e); narrowed `trap`; new `still_valid_observations` | **Yes** | The trap now counts as a false positive only "remove Object Lock" or "erasable audit". The Art. 17(3) documentation point is valid or neutral. |
| P0-3 lakehouse F08 vs §16 | C40, C49: `disambiguation` on both sides; `section_refs` kept | **Yes** | Anchored to the §16 "Sources" table versus the "Pipeline and storage" and "Content boundaries" subsections. |
| P0-4a item_b DEF-12 remedy | C12–C13: item 2 removed; `acceptable_fix` prefixed "examples only" | **Yes** | `credit_requires` now has one detection item. |
| P0-4b clinical F06 remedy | C28–C30: item 3 removed; recommendation marked examples; distractor note added | **Yes** | |
| P0-4c clinical F11 item 4 | C31: "(supporting, not required)" prefix | **Yes** | It is encoded as a string prefix inside the must-mention list, which follows the lakehouse F15 convention. The canonical conversion should lift it into a structured field. |
| P0-4d clinical F04 merge | C26: "claim false" and "consequence" merged into one point | **Yes** | The list now has 4 items. |
| P0-5 item_b DEF-03 | C09–C10: sub-clause note (8.1.2, with one source citing 8.1.1); "unless agreed with the utility" tolerance; any 8.1.x accepted | **Yes** | Not re-verified against IEEE 1547-2018, which is paywalled. The caveat is stated in the key. |
| P1-6 reword "deliberately" | Not applied (optional) | **No (by choice)** | Still in payments §23 and clinical §4.3. Both are benign (section 3). |
| P1-7 v2 status semantics | C19–C24, C34–C36, C50–C52: `status: fixed` plus `introduced_new_flaw_id`; F15 moved into `flaws[]`; `v2_new_flaws` removed | **Yes, identical in all three keys** | Each key has statuses {fixed ×6, unchanged ×8}, no `regressed`, no `new_flaw_id`, and no `original_fixed`. Exactly one entry carries `introduced_new_flaw_id: "F15"` (payments F04, clinical F10, lakehouse F10). The entry key order `flaw_id, status, introduced_new_flaw_id, note` is the same in all three. F15 appears exactly once, with `introduced_in: "v2"` and the correct `introduced_by_fix_of`. No other flaw carries `introduced_in`. The audit had proposed `original_fixed: true`; the different convention achieves the same tally. |
| P1-8 clinical F15 `introduced_by_fix_of` | C32 | **Yes** | `"F10"` |
| P1-9 overlap annotations | C06–C07, C11, C14–C17, C27, C33, C38–C45, C49 | **Yes** for all 9 listed pairs | Both sides are annotated for clinical F05/§4.3, lakehouse F01/§4, F05/§14.6, F15/§9, F08/§16, item_a D03/FR-RET-01, item_b DEF-03 and DEF-13/§7.5, and DEF-14/FR-GRID-01. One further ambiguous pair was found and fixed (E2, section 5). |
| P2-10 canonical schema | Deferred (other agent) | **Out of scope** | Owned by the spec/canonical verifier. |
| P2-11 normalise categories | Not applied | **No** | Clinical still uses `decision_depends_on_pending_backlog`; payments and lakehouse use `..._pending_item`. |
| P2-12 computed counts / `expected_open_flaws` | Not applied | **No** | Payments has `flaw_counts` and `expected_v2_open_flaws`. Clinical has only `category_counts_v1` (open list in prose). Lakehouse has neither. |
| P2-13 payments F05 re-severity | Not applied | **No** | Still minor. |
| P2-14 neutral observations | Partial (item_a collection-offer folded into D01) | **Partial** | The other five suggested observations are not added. |
| P2-15 realism nits | D01 ("AI coding assistant" removed), D02 (date 2026-10-12 → 2026-10-01) | **Yes**, and the PDFs are now rebuilt (section 2) | The optional "every flaw Ready" tidy-up was not done. |
| P2-16 source re-verification | Not applied | **Partial** | I re-checked the D01/D02 law (1.2). The AWS mirror facts were not re-fetched. |
| (Change log) PDFs stale | "PDFs not regenerated" | **Fixed in this pass** | Section 2. |
| (Change log) blind sealing prep | C08, C18, R01, R02 | **Yes** | Section 4. |

### 1.2 Re-verification of the D01 and D02 legal statements

`legislation.gov.uk` and `eur-lex.europa.eu` are blocked by the egress proxy (CONNECT 403). The mirrors I tried were also blocked: uklawreference, lexparency, the UCL cross-reference site, gov.uk assets and enterprise.gov.ie. The text below is therefore from search-engine extracts of the official pages (**P-snippet**) plus secondary summaries such as Which? (**S**).

| Provision | Text (as extracted) | Quality | Key consistent? |
|---|---|---|---|
| UK CCR 2013 reg. 34(5) | Where "the contract is a sales contract, and the trader has not offered to collect the goods", the period ends 14 days after "(a) the day on which the trader receives the goods back, or (b) if earlier, the day on which the consumer supplies evidence of having sent the goods back" | P-snippet (legislation.gov.uk reg. 34, "made" snippet) | Yes |
| UK CCR 2013 reg. 34(6) | "Otherwise, … 14 days after the day on which the trader is informed of the consumer's decision to withdraw …" | P-snippet | Yes |
| UK CCR 2013 reg. 34(2), 34(3) | (2): "must reimburse any payment for delivery … unless the consumer expressly chose a kind of delivery costing more than the least expensive common and generally acceptable kind". (3): in that case, reimburse delivery "up to the amount the consumer would have paid" for the least expensive kind | P-snippet | Yes. The key's D02 citation "reg. 34(2)-(3)" is **correct**. The audit's "cosmetic: the delivery rule is 34(2)" note was itself imprecise, because 34(3) is the partial-delivery rule. No edit made. |
| CRD Art. 13(1) | Reimburse "all payments … including, if applicable, the costs of delivery … not later than 14 days from the day on which he is informed of the consumer's decision to withdraw" | K, with a P-snippet of 13(3) from the same page | Yes |
| CRD Art. 13(3) | "Unless the trader has offered to collect the goods himself, with regard to sales contracts, the trader may withhold the reimbursement until he has received the goods back, or until the consumer has supplied evidence of having sent back the goods, whichever is the earliest." | P-snippet (eur-lex / legislation.gov.uk eudr extracts) | Yes. The exception is in the Article text itself. The key's parenthetical about Commission guidance (the offer binds only if the trader also bears the cost) matches the guidance extract (S/P-snippet, DG JUST 2014 guidance). |

Verdict: the rewritten D01 `external_fact` and `credit_requires` are legally correct for both regimes. The remaining interpretive point is whether a collection offer removes the UK reg. 34(5) or EU withholding right for customers who chose a label or store return. The key states this point and does not penalise either reading. E1 makes the "single rule" in `acceptable_fix` lawful under both readings.

### 1.3 README counts against keys

| README claim | Key | Match |
|---|---|---|
| clinical: 14 flaws, 4/6/4, 8 categories, 5 sound, fixed = F02, F04, F07, F08, F10, F12, F15 from F10, 8 unchanged | 14 v1 flaws (4/6/4), 8 categories (3/2/2/2/2/1/1/1), 5 sound, v2 tally identical | Yes |
| payments: 14, 4/6/4, categories 3/2/2/2/2/1/1/1, 5 sound, fixed = F02, F03, F04, F06, F08, F12, F15 from F04, 8 unchanged | `flaw_counts` identical; `expected_v2_open_flaws` = 8 unchanged + F15 | Yes |
| lakehouse: 14 (F01–F14), 4/6/4, 8 categories, 5 sound, fixed = F03, F05, F06, F08, F10, F13, F15 from F10, 8 remain | Identical | Yes |
| item_a: 14 defects; 9,440 words by `wc -w` | `defect_count` 14 = len(defects); `wc -w` 9,440 | Yes |
| item_b: 14 defects; 9,866 words by `wc -w` | 14 = 14; `wc -w` 9,866 | Yes |
| Sealed item_a text: 2 Critical / 6 High / 5 Medium / 1 Low; six external-fact defects; 8 sound areas | 2/6/5/1; `requires_external_fact` = D01, D02, D04, D05, D06, D10; 8 sound | Yes |
| Sealed item_b text: 1 critical / 7 high / 6 medium; 9 sound sections | 1/7/6; 9 | Yes |
| Word counts in synthetic READMEs ("about 8,200/8,900"; lakehouse "8422/8997") | `wc -w` gives 9,372/10,113 and 9,576/10,165; a token count excluding markup gives about 8,281/9,016 and 8,512/9,088 | Approximate only. The lakehouse exact figures cannot be reproduced (P3). |

---

## 2. PDF regeneration

**Pipeline.** `eval/build_pdfs.py` (new) does the following:
- Converts with python-markdown 3.11 (extensions `tables`, `fenced_code`, `sane_lists`) to HTML with a fixed embedded stylesheet.
- Wraps short ID-only table cells in `<nobr>` so that, for example, `FR-11` is not broken at the hyphen.
- Runs `soffice --headless --infilter="HTML (StarWriter)" --convert-to pdf:writer_pdf_Export` with a throwaway LibreOffice profile.
- Verifies the result with `pdftotext`. The probes are the middle eight words of the longest prose sentence in the first, middle and last H2 section, plus required and forbidden phrases.
- `--check` verifies the PDFs without rebuilding them.

**Before rebuilding,** `--check` against the old PDFs failed exactly where the change log predicted:
- payments v2 lacked "2026-10-01" and still contained "2026-10-12".
- Both lakehouse PDFs lacked "could the engineering team build …" and still contained "AI coding assistant".
- The clinical and payments v1 PDFs passed.

The old PDFs are backed up at `scratchpad/old_pdfs/`.

**After rebuilding all six with the one pipeline:**

| PDF | Pages (old → new) | First / middle / last probe | Edited phrases |
|---|---|---|---|
| clinical v1 | 25 → 21 | §1 "a level of technical detail sufficient for an" / §12 "a retry always posts the same medians for" / §24 "companion Conceptual Design and Clinical Safety Case, represents" all found | n/a |
| clinical v2 | 26 → 22 | §1 / §12 "such as artefact); accepted values are updated by" / §24 found | n/a |
| payments v1 | 23 → 21 | §1 "integration stacks that share no routing, no ledger," / §13 "allows it to link the same card across" / §28 "cards and PayNow) goes live after Phase 7;" found | n/a |
| payments v2 | 24 → 22 | same probes, found | "2026-10-01" present; "2026-10-12" absent |
| lakehouse v1 | 28 → 20 | §1 "storage, ingestion, access-control and audit layers, and to" / §11 "user server, user home directories on Amazon EFS" / §24 "with the RDLR Conceptual Design, represents the design" found | §23 "could the engineering team build each component from this document alone" present; "AI coding assistant" absent |
| lakehouse v2 | 29 → 21 | same probes, found | same |

**Visual spot check** (pages 3–4 of lakehouse v1 and page 3 of payments v1, rendered with pdftoppm):
- Headings, tables with shaded header rows and the ASCII architecture diagrams render legibly.
- LibreOffice's HTML import ignores CSS cell borders, so tables are borderless.
- The page counts fall because the new stylesheet is denser.

**README updates.** The PDF note in each of the three synthetic READMEs is replaced by a "How to regenerate the PDFs" line that names the script, the pipeline, `--check` and the page counts. The blind items have no PDFs, and their sealed READMEs were left unchanged.

---

## 3. Leakage re-check after the edits

**Corpus.**
- All 8 design Markdown files: item_a, item_b, and synthetic v1 and v2 ×3.
- The `pdftotext` output of the 6 rebuilt PDFs.

**Patterns.**
- `\bF(0[1-9]|1[0-6])\b`, `\bD(0[1-9]|1[0-6])\b`, `\bDEF-\d+\b`, planted, deliberate, defect, flaw, sealed, answer key.
- Five hand-picked key-only evaluative phrases per key.
- An automatic 6-gram overlap between each key's evaluative fields (`why_it_is_a_flaw`/`why_it_matters`/`acceptable_*`) and its documents.

| Hit | Where | Context | Judgement |
|---|---|---|---|
| "sealed" | item_a l.135, l.434 | "hygiene-sealed items (pierced earrings…)" | Benign (domain term; sound FR-RET-03) |
| "sealed" | item_b l.555 | "break-glass accounts, sealed in the control room safe" | Benign |
| "deliberately" | clinical v1 l.192 / v2 l.199 and both PDFs | "persistence window … is deliberately part of the clinical definition" (sound §4.3) | Benign. It sits next to the F05 overlap, but it defends the window itself, which the key treats as sound. Optional rewording (P1-6 still open). |
| "deliberately" | payments v1 l.729 / v2 l.746 and both PDFs | "MPOP is deliberately conventional in its core" (sound §23) | Benign |
| Flaw-ID, D01–D16, DEF-xx, planted, defect, flaw, answer key | none | — | 0 hits. The documents' own `D-01`… decision IDs carry a hyphen and do not match. |
| Phrase "test method" | item_b R5 reference row | "UL 9540A, thermal runaway fire propagation test method" | Benign. This is the real standard title in the reference list. It is the clue that makes DEF-05 findable and is not a label. |
| Phrase "cross-merchant" | payments v1/v2 §13.1 | "cross-merchant velocity graph" | Benign (document's own rationale for sending the PAN) |
| Phrase "4 bytes" | lakehouse v2 §15 | "≈ 2,394 bytes" (substring match) | False match |
| Phrase "last-writer-wins" | lakehouse v2 §8.1 | "with last-writer-wins conflict resolution on the row update timestamp" | Benign. It is the v2 design statement that *is* F15. A reviewer must reason that LWW breaks Iceberg CAS; the text does not call it a problem. |
| Other phrases ("serialises the entire", "dual write", "regenerated on every", "sequential IDs", "strands orders", "implemented in software", "not hardwired", "bypasses the", "cannot meet", "single point of failure", "re-identif", "head-of-line", "fleet-wide", "silently", "double authori", "hot partition", "account takeover", "cross-project", "mixed vector") | none | — | 0 hits |
| 6-gram overlaps: item_a 0, item_b 8, clinical 52 (6 flaw/field groups), payments 18, lakehouse 16 | various | Every overlap is the key quoting the document. Examples: the NFR-7 text "cluster can revoke the platform's access to data independently of the cloud provider"; P3 "the EMR is the legal"; P-02; NFR-SEC-02; FR-BK-02/FR-EXP-03; FR-5 "a reused key with a different"; Backlog 1 "can disable planner extensions"; the NFR-7 AC "every retained snapshot and tag". The rest is v2 fix text that legitimately adopts the corrected fact (payments F04/F06; clinical F04/F12 recommendations). | Benign. No key-only evaluative language appears in any document or PDF. |

---

## 4. Blind README sealing

| Check | item_a | item_b |
|---|---|---|
| README contains no defect description, severity mix, external-fact topic, sound-area list or scoring rule | Yes. Only domain, size, "14 seeded defects", intended use and the sealed-key note remain. | Yes, same layout |
| `readme_notes_moved_at_sealing` holds the removed text | Yes. The text after the one-sentence provenance note equals the pre-edit README in `scratchpad/orig/eval/blind/item_a/README.md` exactly, except for the final newline (2,584 vs 2,585 chars). | Yes, identical apart from the final newline (3,277 vs 3,278) |
| Sealed text consistent with the key | 2/6/5/1 severities, 6 external-fact defects, 8 sound areas all match | 1/7/6, 9 sound sections all match |

**Residual issue.** The keys are still plaintext JSON sitting next to `design.md`. Sealing depends on convention only (see Open issues, P1).

---

## 5. Sound-section and flaw overlap

I computed overlaps by matching each flaw's sections and requirement IDs against each sound entry's location. Spurious numeric matches inside free-text descriptions were filtered out.

| Item | Pair | Anchor that separates them | Precise enough? |
|---|---|---|---|
| clinical | F05 × §4 (4.3) | Table 4.3b 10-s persistence window *omitted from the §10.4 budget* (F05) vs "the window itself is a defect" (trap). F06 is pinned to the FR-8 citation, not the 4.3 priority semantics. | Yes (table/sentence level) |
| lakehouse | F01 × §4 | The §4 tier-table Restricted row ("Not permitted (NFR-5)") as the rule violated by 14.4 and §20 "Generation model", vs "§4 tier design is wrong" | Yes (table row) |
| lakehouse | F08 × §16 | §16 "Sources" table principal attribution vs the "Pipeline and storage" and "Content boundaries" subsections | Yes (subsection) |
| lakehouse | F05 × §14.6 | "Budget won't hold because the index doesn't fit in memory (§15)" vs "attacks the 14.6 method or arithmetic (360 ms, 1.98 s)" | Yes (claim plus figures) |
| lakehouse | F15 × §9 (v2 only) | CAS publish and orphan-cleanup consequence of LWW replication vs "WAP duplicates storage / validate-before-write / branch exposure" | Yes |
| item_a | D03 × 3.1.3 FR-RET-01 | 7.4 step 2 `now <= order.placedAt + 30 days` vs FR-RET-01's own wording | Yes (sentence level) |
| item_b | DEF-03, DEF-13 × §7.5 | Step-2 "≤ 5 s" separation (DEF-03) vs no AC for the unplanned sequence (DEF-13) vs "steps don't add up to ≤ 9 s" (trap) | Yes (step level) |
| item_b | DEF-14 × FR-GRID-01 | Sequencing (OI-02 in Phase 3 vs Phase 1 energisation, AC-04) vs category content | Adequate. It is claim-type based rather than location based, but FR-GRID-01 is a single sentence, so no finer anchor exists. |
| item_b | **DEF-02 × "5.5, 7.9 and D-02"** (shares 7.9 step 3 and NFR-AV-02) | Before this pass the distinction lived only in `why_sound`. The trap also lists "calling holding setpoints during switchover unsafe", which a matcher could confuse with a DEF-02 finding citing 7.9. | **Was ambiguous. Fixed (E2):** `disambiguation` added on both sides, separating on duration: unbounded hold after a loss longer than switchover (DEF-02) vs the sub-second switchover hold (sound). |
| item_b | DEF-08 × "5.2 ratings table and FR-BK-02 reserve arithmetic" | `why_sound` says the 5.2 figures are correct and that the defect is 7.2 ignoring the reserve. DEF-08 location says "7.2 (Energy check)". | Yes (subsection). No field needed. |
| item_b | DEF-04 × "6.3 (last paragraphs), 9.4, D-03" | IF-BMS-02 bullet (125-register limit) vs the last-paragraph encryption point; `why_sound` names DEF-04 | Yes |
| item_a | D02 × "6.4 items 3 and 5"; D12 × 6.4 | Item 6 (delivery charge) and column types/rounding vs items 3 and 5 | Yes (item level) |
| item_a | D06 × "5.4 notification stream"; D04 × "6.2 optimistic concurrency"; D01 × "3.1.4 FR-REF-01"; D03/D09 × "7.4 exclusions" | Order-event MessageGroupId bullet vs notification stream; "Sizing" paragraph vs OCC bullet; FR-REF-02 vs FR-REF-01; window bullet and step 5 vs exclusions bullet | Yes (sub-item level in the sound location strings) |
| payments | none | — | — |

**Still ambiguous after E2:** none that a matcher with the location and description text could not separate.

**Minor tension, not ambiguity.** The pre-existing `trap` texts for lakehouse §4 ("attribute F01 to this section") and §14.6 ("fold F05 into it") read more strictly than the new `disambiguation` fields. The canonical conversion should state that `disambiguation` takes precedence (P2).

---

## 6. Difficulty sanity check (rough human-ceiling probe)

**Procedure.**
- I read the five v1 or blind design documents cold.
- I wrote my 5 most serious issues per document to a scratch file, with an "also noticed" list, before opening any key or the audit.
- I then mapped each issue to the keys.

The v2 documents were not probed.

| Document | My top 5 → key | Top-5 that are planted | Valid top-5 issues missing from key | Key critical flaws missed in my top 5 | Coverage incl. "also noticed" |
|---|---|---|---|---|---|
| item_a (Meridian OMS) | refund per-attempt idempotency key → D08; dual write with no outbox → D07; constant MessageGroupId → D06; PII + 10-year compliance lock → D10; unauthenticated sequential return IDs → D09 | 5/5 | 0 | 0 of 2 (D06, D08 both found) | 13/14 (missed D13 rollback strands orders) |
| item_b (Fenwick SEMS) | software E-stop → DEF-01; hold-last-setpoint with no timeout → DEF-02; 5-s meter vs 2-s export limit → DEF-07; energy check ignores 35% reserve → DEF-08; supplier VR-1 tunnel → DEF-11 | 5/5 | 0 | 0 of 1 | 11/14 (missed DEF-05 UL 9540 vs 9540A, DEF-13 untested unplanned island, DEF-14 settings-file sequencing) |
| clinical_rpm v1 | single-replica dispatcher → F10; late-arrival drop → F11; group key in firmware → F08; re-identifiable extracts → F09; EWS-ML primary for MIC@Home → F14 | 5/5 | 0 | 1 of 4 (F04 IoT Hub quota; it was in my wider list) | 14/14 |
| payments_orchestration v1 | Redis key without merchant → F09; CVC retention → F06; Fraud Hook PAN → F01; timeout cascade → F10; RPO 0 vs async replication → F03 | 5/5 | 0 | 1 of 4 (F08 payout-account change; it was in my wider list) | 12/14 (missed F07 Indonesia residency, F12 FR-8 "2%") |
| research_lakehouse v1 | faculty service principal → F08; faculty answer cache → F09; Restricted to external LLM → F01; erasure vs snapshots/tags/versions → F03; Discovery Portal embargo leak → F02 | 5/5 | 0 | 0 of 4 | 12/14 (missed F12 FR-6 ambiguity, F13 NFR-10 AC) |

**Totals.**
- Top-5 precision: 25/25 planted.
- Key-missing valid issues: 0.
- Critical flaws missed from the top 5: 2 of 15. Both were caught in the wider list.
- Wider-list recall: 62/70.

**Interpretation, stated honestly.**
- The planted flaws are real and findable, and the keys are complete relative to what I found: I recorded no valid issue the key lacks.
- The most serious flaws in every document are detectable in one careful read, so a strong reviewer will sit near the ceiling on detection of critical and major flaws.
- The items discriminate mainly through three things:
  - the "must mention" detail (exact limits, the correct legal anchor);
  - the minor, ambiguity and testability flaws, which are where my misses were;
  - the sound-section traps.
- **Bias caveat.** I am likely the same model family that generated these documents, which may inflate recall. Treat this as an upper-bound probe.

---

## Edit log (this pass)

| # | File | Change | Reason |
|---|---|---|---|
| E1 | `eval/blind/item_a/answer_key.json` | `defects[D01].acceptable_fix`: replaced the "single conservative rule" sentence. The new rule: due = notification + 14 days for all statutory returns. Deferral up to the earliest of receipt or scan is allowed only in IE, NL and FR. No deferral in the UK or DE, where collection is offered. A note explains why this also satisfies UK reg. 34(5). | The old rule was non-compliant under the strict reading of the collection-offer point, which the key itself says is a legitimate reading. |
| E2 | `eval/blind/item_b/answer_key.json` | New `disambiguation` on `defects[DEF-02]` and on sound entry "5.5, 7.9 and D-02 …" (same text, as in the C-series convention) | The overlap on 7.9 step 3 and NFR-AV-02 was not annotated, and the trap wording could swallow a correct DEF-02 finding. |
| E3 | `eval/build_pdfs.py` (new) | Reproducible PDF build and verify script | Task 2 |
| E4 | `eval/synthetic/{clinical_rpm,payments_orchestration,research_lakehouse}/design_v1.pdf, design_v2.pdf` | Rebuilt with E3 | Three were stale. All six now use one pipeline. |
| E5 | `eval/synthetic/{clinical_rpm,payments_orchestration,research_lakehouse}/README.md` | Replaced the PDF-conversion sentence with a "How to regenerate the PDFs" line (script, pipeline, `--check`, page counts) | Task 2 |

**Validation.**
- `json.load` passes on all five keys after the edits.
- Both blind keys were written with `indent=2, ensure_ascii=False` and no trailing newline, which matches their prior serialisation (round-trip checked before editing).
- `python3 eval/build_pdfs.py --check` reports ALL CHECKS PASSED.

**Not changed:** `spec/`, any `answer_key.canonical.json`, the design Markdown, and the synthetic keys.

**Housekeeping note.** I removed my own temporary `*.png` renders from the session scratchpad with a glob. I did not list the directory first.

---

## Open issues

| Priority | Issue | Suggested action |
|---|---|---|
| P1 | The blind keys are plaintext JSON next to `design.md`. Sealing is by README instruction only (research audit P0-7: encryption and access log still to do). | Encrypt the blind keys, or move them out of the tree given to reviewers, before any held-out run. |
| P1 | Ceiling risk (section 6): 25/25 top-5 precision and every critical flaw found in one read. | Rely on must-mention detail, minor/ambiguity/testability flaws and false-positive traps for discrimination. Consider adding harder, cross-section-only flaws, or report detection and precision separately. |
| P2 | P2-11/P2-12 not applied: clinical category name differs; counts and `expected_open_flaws` are missing in clinical and lakehouse. | Handle in the canonical conversion (other verifier), or add them to the legacy keys. |
| P2 | P2-13: payments F05 is still minor, although it is a hard p99 miss its own AC exposes. | Decide and record. |
| P2 | P2-14: five neutral observations are still absent: payments §23 Stripe 24-h attribution; clinical §6.2 `device_ts` and batching vs the 5-s tolerance; lakehouse v2 run-rate over $80k after F04; lakehouse Glacier IR 128 KB minimum and CRR PUT cost; item_a §6.7 channel-scoped idempotency. | Add them as neutral observations so valid unkeyed findings are not penalised. |
| P2 | The `trap` text for lakehouse §4 and §14.6 is stricter than the new `disambiguation`. Clinical F11 "(supporting, not required)" is a string prefix. | In the canonical schema, give `disambiguation` precedence and lift "supporting" into a structured flag. |
| P2 | Legal sources for D01/D02 are P-snippet and S only, because primary sites are blocked. IEEE 1547-2018 (DEF-03) is still unread. | Re-verify when egress allows. The AWS mirror facts (P2-16) are also still to re-fetch. |
| P3 | "deliberately" remains in payments §23 and clinical §4.3 (benign). | Optional rewording (P1-6). |
| P3 | The lakehouse README states exact word counts (8422/8997) that no counting method reproduces. The other READMEs say "about". | Change to "about 8,500 / 9,100 words" or state the method. |
| P3 | The rebuilt PDFs differ in layout from the originals (20–22 vs 23–29 pages; borderless tables). | Do not compare PDF-input runs made before 2026-10-02 with later ones. |
