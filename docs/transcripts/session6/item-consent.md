# Worker note: synthetic item consent_service (synthetic-consent-service-001)

Date: 2026-10-04.
Brief: the SIT planner's S4 item-authoring brief under Malcolm's word of 4 Oct 2026 22:40 ("yes" to plan D: ten documents, five of them new), with his delegation of shot calling (3 Oct 02:50).
Branch `s4/item-consent` from `origin/claude/happy-darwin-d0bl94` at 5f4eeb6.
Not opened: `eval/blind/`, `docs/live_runs/`, the clinical_rpm and research_lakehouse items.
Read as models: the payments_orchestration README, key and first 60 lines of its design (plus its Sections 24 to 28 for table formats), `eval/human_labelling_protocol.md`, `docs/SEALING.md`, `spec/taxonomy.yaml`, `eval/build_pdfs.py`, the item-list and `main`/`verify_anchors` parts of `spec/convert_answer_keys.py`, and the iot_fleet README, key metadata and worker note.

## Process notes

- `eval/build_pdfs.py` and `spec/convert_answer_keys.py` were run unchanged on disk through scratchpad wrappers (`author_consent3/build_consent_pdfs.py`, `author_consent3/convert_consent.py`) that add this item to `ITEMS` (and `NEEDS_EXTERNAL = {"F05", "F15"}`) in memory only, as the iot_fleet worker did. The registering worker must add these entries for real; `eval/prereg.yaml` was not edited.
- PDFs: built with system `python3` (the venv lacks `markdown`); 17 and 18 pages; `ALL CHECKS PASSED`.
- Converter (`--tier synthetic --verify-anchors`, this worktree's venv): `60 flaws converted across 4 keys; 0 key(s) failed validation`; the other three canonical keys were rewritten byte-identical (git shows no change). All 15 flaw anchors and 12 approved-decision anchors are exact, unique matches on their recorded pages (checked first with `sit_review_agent.ingest.pdf.ingest` by `author_consent3/anchors.py`). Two table-cell anchors (F12, F13) had to be shortened to the first line of the cell, because the ingested text interleaves wrapped table cells.
- F05 external fact: fetched on 2026-10-04 from https://www.pdpc.gov.sg/-/media/Files/PDPC/PDF-Files/Advisory-Guidelines/Advisory-Guidelines-on-the-DNC-Provisions-1-Feb-2021.pdf (text extracted with pdftotext): "The 'prescribed duration' within which a person must check with the DNC Registry before sending a specified message to a Singapore telephone number has been prescribed as 21 days", with the validity table "From 1 February 2021 onwards: 21 days from receipt of results" (results of 2 February 2021 valid until 23 February 2021). The same guidelines put the period to effect a withdrawal of DNC consent (s47(3)) at 21 days. The PDPC e-services page also refers to "the 21-day DNC check validity".
- `scripts/leakage_grep.py`: with this item present it first reported `recorded_at` (a column name, against `agent/sit_review_agent/tools/gateway.py`) and `email address` (TF-IDF, against `agent/sit_review_agent/ui/mail.py`), both from this item. The column was renamed `stored_at` and "email address" was reworded to "email" (and "an email account" for the contact-point definition) in both designs and the key, after which the script prints `PASS: no unresolved hit in a gated area`. No hit from another item appeared in this configuration (the payments "never leave" pair that iot_fleet saw did not surface here; it may still surface once all new items are present together).
- Tests: no test was run (no code changed); load at the PDF build was 4.99 with 36% free memory.

## Word counts (wc -w)

        8460 design_v1.md
        8951 design_v2.md
       17411 total

## No-label scan

    $ grep -ciE '\bF[0-9]{2}\b|flaw|planted|intentional|deliberate|bug|TODO|FIXME|incorrect|mistake|wrong|regression|known issue|answer key' design_v1.md design_v2.md
    design_v1.md:0
    design_v2.md:0

Em dash count (grep -c of U+2014) in both designs, the key, the canonical key, the README and this note: 0 each.

## Per-flaw carrying sentences (v1) and their v2 state

Fixed in v2: F01, F02, F04, F05, F06, F11, F12. Unchanged: F03, F07, F08, F09, F10, F13, F14. New in v2: F15 (from the F05 change).

### F01

- v1: Customers with no recorded preference in the legacy systems who were sent the 2019 privacy notice and did not opt out are migrated with all four marketing purposes in state GRANTED, source MIGRATION and notice version N-2019-03.
- v2: Customers with no recorded preference in the legacy systems are migrated with no event for the marketing purposes, so the Eligibility API treats those purposes as not granted (Section 10).

### F02

- v1: The topic has 24 partitions and is keyed by `mid`, with `cleanup.policy=compact`, `segment.ms` of one hour and `min.compaction.lag.ms` of one hour, so the topic keeps the latest event for every customer indefinitely and a new consumer can bootstrap from it without a database extract.
- v2: The topic has 24 partitions and is keyed by subject and purpose (`subject_id:purpose_code`), with `cleanup.policy=compact`, `segment.ms` of one hour and `min.compaction.lag.ms` of one hour, so the topic keeps the latest event for every subject and purpose indefinitely and a new consumer can bootstrap from it without a database extract.

### F03

- v1: Consent events older than 24 months are deleted by dropping their monthly partition, and the current position for every subject and purpose remains in `consent_state`, so Izin always knows what each customer has agreed to.
- v2: Consent events older than 24 months are deleted by dropping their monthly partition, and the current position for every subject and purpose remains in `consent_state`, so Izin always knows what each customer has agreed to.

### F04

- v1: A receipt is viewable at `https://izin.keruing.sg/r/{receipt_number}` without signing in, so that customers who changed their preferences through the contact centre or in a store can open it from the SMS link.
- v2: The receipt link carries a separate random 128-bit token (`https://izin.keruing.sg/r/{token}`), stored only as its SHA-256 hash, and the link expires 30 days after issue.

### F05

- v1: Under the PDPA, the result of a DNC Registry check remains valid for 30 days from receipt, so the DNC Service re-checks every number in the marketing base once every 28 days and serves campaign checks from its cache.
- v2: Under the PDPA, the result of a DNC Registry check remains valid for 21 days from receipt, so the DNC Service re-checks every number in the marketing base once every 14 days and serves campaign checks from its cache.

### F06

- v1: The largest campaign, the monthly Rewards newsletter, goes to 3.0 million recipients in a one-hour send window, which is about 83 requests per second.
- v2: The largest campaign, the monthly Rewards newsletter, goes to 3.0 million recipients in a one-hour send window, which is about 833 requests per second.

### F07

- v1: Residency is fully met by this placement: every Izin data store is in ap-southeast-1, and partner processing after the nightly file is delivered is the partner's own responsibility.
- v2: Residency is fully met by this placement: every Izin data store is in ap-southeast-1, and partner processing after the nightly file is delivered is the partner's own responsibility.

### F08

- v1: Each event also carries the customer's full profile snapshot (name, NRIC number, date of birth, mobile number, email and postal address), so that consumers never need to call back into Izin to act on an event.
- v2: Each event also carries the customer's full profile snapshot (name, NRIC number, date of birth, mobile number, email and postal address), so that consumers never need to call back into Izin to act on an event.

### F09

- v1: When a mobile line is terminated, the consents held on its number remain on the contact point record, which keeps the history of the number complete for audit.
- v2: When a mobile line is terminated, the consents held on its number remain on the contact point record, which keeps the history of the number complete for audit.

### F10

- v1: `FAILED` rows are listed on the operations dashboard and replayed after review at the weekly operations meeting.
- v2: `FAILED` rows are listed on the operations dashboard and replayed after review at the weekly operations meeting.

### F11

- v1: | FR-9 | Send the customer a consent receipt for all significant preference changes. |
- v2: | FR-9 | Send the customer a consent receipt for every consent change, within five minutes of the change, by SMS to the mobile number on the profile or by email where the customer has no mobile number. |

### F12

- v1: | NFR-2 | UAT withdrawal check | In UAT, withdraw marketing consent for 20 test customers in the app and confirm that each shows as withdrawn in Seruan within 24 hours. |
- v2: | NFR-2 | Propagation test in pre-production at design-target load | Over 24 hours, record 1,000 withdrawals spread across every channel (app, web, contact centre, store, partner API, STOP reply and IVR), a third of them followed within an hour by another change for the same customer; restart the relay and each consumer once during the run. Every withdrawal is applied in Seruan, the Group Analytics Platform, the contact centre CRM and the Rewards platform within 24 hours of being recorded, and every partner-purpose withdrawal appears in the next nightly partner file. |

### F13

- v1: | DEC-09 | Seri Assurance captures Keruing consent (PTN-INS and MKT-EMAIL) in its own app through the Partner Consent API from Phase 4 | Partner programme launch in Q2 2027 |
- v2: | DEC-09 | Seri Assurance captures Keruing consent (PTN-INS and MKT-EMAIL) in its own app through the Partner Consent API from Phase 4 | Partner programme launch in Q2 2027 |

### F14

- v1: | `consent_state` | 5.2 million customers × 7 consent purposes × 180 bytes | about 6.6 GB |
- v2: | `consent_state` | 5.2 million customers × 7 consent purposes × 180 bytes | about 6.6 GB |

### F15

- v1: (not present in v1; introduced in v2)
- v2: A number whose result is older than 21 days because its cohort's refresh has not succeeded keeps its last result and is served from it until the next successful refresh, so a registry outage or a rejected bulk file never blocks a campaign.


## Cold read

Date: 2026-10-04, by a separate cold-reader worker that had not seen the item.
Read: handover section 6, this item's two designs, key and README, this note, `eval/human_labelling_protocol.md`, `docs/SEALING.md`, `spec/taxonomy.yaml`.
Not opened: `eval/blind/`, `docs/live_runs/`, the other synthetic items, the source of `spec/convert_answer_keys.py` and `eval/build_pdfs.py`.
Scripts are in the scratchpad folder `coldread_consent/`.

### Flaws found cold

All fourteen v1 flaws were found from `design_v1.md` alone before the key was opened: F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13 and F14.
F05 was found from knowing the 21-day PDPC rule, which a domain reader would also know; the first lines of the README, read before the design, name the DNC validity period as the external fact, so the finding of F05 alone is not fully blind.
No planted flaw needed rewording to be findable, so no flaw anchor sentence changed.

### Defects found in the sections the key called sound (fixed)

Each of these is a real defect that a careful reviewer would rightly flag, so each was a key error waiting to happen; the section was fixed in both designs, identically, and the key's `why_sound` was updated.

1. Section 9 with Section 18: the lost-update and idempotency guarantees rested on unique constraints on `consent_event`, which is range-partitioned by `stored_at`; PostgreSQL requires a unique or primary key on a partitioned table to include the partition column, so the DDL as written is rejected and the guarantees did not hold. Now: `consent_event` has `PRIMARY KEY (event_id, stored_at)`, the lost update is prevented by the state-row lock and the `consent_state` primary key for a first change, and idempotency is held in a new unpartitioned `request_key` table (90-day retention row added to Section 19, and the step named in the 24.1 budget).
2. Section 10: the idempotency key was generated when the screen opened, so a second, different change on the same screen (for example a grant then a withdrawal) would have been answered with the first result and silently dropped. Now: a key per change, reused for its retries.
3. Section 13 against FR-4 and P4: the withdrawal had a confirmation step after the consequence notice, one step more than a grant. Now: the consequence is shown beside the toggle and turning it off is the whole withdrawal.
4. Section 13 against the Section 16 table: it said that after withdrawal the DNC result decides later marketing, while the table refuses a WITHDRAWN number whatever its DNC result. Now it agrees with the table.
5. Section 7 with Section 18: an old-purpose-version grant was to be treated as not granted, but `consent_state` held no purpose version, so nothing could make that check. Now `consent_state` has `purpose_version` and the Eligibility API compares it with the current version.
6. Section 23 against Section 14.1: "every Izin service with at least three replicas" contradicted the single active Outbox Relay with a standby. Now API services have three replicas and the relay's two pods sit in different AZs.

One defect outside the sound sections was also fixed because it was cheap and would otherwise score as an unplanted finding: Section 11, a queued offline store change submitted after a newer change for the same subject and purpose would have overridden it (state follows `seq`, not `captured_at`); the Consent API now rejects such a queued change.

### Valid but unkeyed observations left in place

A reviewer may still raise these; graders should class them VALID_UNPLANTED (or PARTIAL_KEY_MATCH to F03 where noted), not as false positives:
- Section 19 keeps DNC results for 90 days, so a complaint about a contact more than about three months old cannot be answered with the DNC result held at the time (related to F03).
- Section 19 leaves call recordings and signed store forms, the targets of `evidence_ref`, to other systems' retention policies (related to F03).
- Section 23.2: withdrawals in the four-hour region-loss RPO window would be lost; the risk is recorded and accepted (RR-118), so this is at most an observation.

### Key consistency

- F15 severity changed from critical to major: it serves expired results only when a cohort refresh fails, a narrower exposure than F05 (major), which serves results 22 to 28 days old every cycle for the same population (migrated grants without evidence). README and `version_notes` updated; the canonical severity is now `high`.
- All other severities and categories match the substance and map to the taxonomy through the converter (`could not map: none`). `flaw_counts` match (4/6/4). `v2_changes` match the line diff: the seven "fixed" flaws are gone in v2, the seven "unchanged" carrying sentences are byte-identical, F15 is only in v2 and is carried by the F05 change. `expected_v2_open_flaws` (F03, F07, F08, F09, F10, F13, F14, F15) is correct. `distractor_notes` do not point at other flaws.
- The v2 "Changes since version 1.0" bullet for Section 16 named "the handling of results awaiting refresh", which pointed straight at F15; it now reads "validity of DNC Registry results and the refresh cycle".

### Names

Web searches on 2026-10-04: "Merbau" matched a real company in a real conglomerate (Merbau Corporation, the renewable-energy arm of JG Summit, Philippines, plus a Swiss property firm Merbau GmbH), and "Kempen" is the name of a real asset manager (Kempen, of Van Lanschot Kempen, known without a search).
Renamed throughout the designs, key, README and this note: Merbau to Keruing (and `izin.merbau.sg` to `izin.keruing.sg`), Kempen to Seruan.
No real organisation or product was found for Izin, Seri Assurance, Lintang Bank, Keruing (as a company) or Seruan (as a product); Arus and Mata are common Malay words with no matching product found.

### External fact

Re-fetched on 2026-10-04 from the URL named in the key (58-page PDF, text by `pdftotext`): "The 'prescribed duration' within which a person must check with the DNC Registry before sending a specified message to a Singapore telephone number has been prescribed as 21 days", and the validity table: "From 1 February 2021 onwards: 21 days from receipt of results" (results of 2 February 2021 valid until 23 February 2021). Confirmed.

### Rebuild and checks

- PDFs rebuilt with system `python3` through `coldread_consent/build_consent_pdfs.py`: `design_v1.pdf` 17 pages, `design_v2.pdf` 18 pages, `ALL CHECKS PASSED`.
- Anchor pages re-measured with `coldread_consent/anchors.py` (all 15 flaw anchors and 12 approved-decision anchors exact and unique); pages updated in `authoring_drafts` (F03 13, F06 15, F07 14, F08 9, F12 17, F13 16, F14 15, F15 10; AD-008 to AD-012 on page 16).
- Converter through `coldread_consent/convert_consent.py --tier synthetic --verify-anchors` with the venv: `60 flaws converted across 4 keys; 0 key(s) failed validation`; the other three canonical keys unchanged.
- No-label scan: `design_v1.md:0`, `design_v2.md:0`. Em dash count 0 in both designs, both keys, the README and this note.
- `scripts/leakage_grep.py` now prints FAIL with one unresolved hit, and it is not from this item: 'never leave' (TF-IDF, from eval/synthetic/payments_orchestration) against `agent/sit_review_agent/tools/gateway.py:1080`, the pair the iot_fleet worker saw; the TF-IDF weights shift with this item's text. No term from this item is unresolved (`request_key` and the new names raise no hit). Left for the registering worker, who sees all new items together.
