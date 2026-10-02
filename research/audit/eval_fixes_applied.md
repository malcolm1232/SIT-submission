# Eval fixes applied

Date: 2026-10-02. Source of the corrections: `research/audit/eval_data_audit.md` (prioritised fix list, P0/P1/P2) and `research/audit/research_audit.md` §4.3 and §6 P0-7 (sealing the blind set). No git commands were run. Files were written only under `eval/` and to this file. All five answer keys keep their existing schema and formatting (2-space JSON, key order preserved); edits are in place.

## Decisions and interpretations

1. **"item_a D03 tolerance" (task item 5).** The audit's tolerance item is P0-5 and concerns **item_b DEF-03** (IEEE 1547-2018 2 s trip, "unless agreed with the utility", cite the sub-clause). The audit has no tolerance item for item_a D03; its only item_a D03 item is the FR-RET-01 overlap (P1-9). I applied the tolerance fix to item_b DEF-03 (C09, C10) and the overlap annotation to item_a D03 (C06, C07). If a tolerance change to item_a D03 was intended, it still needs to be specified.
2. **v2 convention (task item 6).** In all three synthetic keys, a flaw whose fix introduced a new flaw now has `status: "fixed"` plus `introduced_new_flaw_id` (renamed from `new_flaw_id`). The new flaw F15 lives in `flaws[]` with `introduced_in: "v2"` and `introduced_by_fix_of`. For payments and lakehouse this meant moving F15 unchanged from `v2_new_flaws` into `flaws[]` and removing the now-empty `v2_new_flaws` key, so there is one copy only. The status value `regressed` no longer occurs. A tally of `status == "fixed"` now gives 6 in every key, matching the READMEs. `len(flaws)` is now 15 in all three keys; `flaw_counts.total_v1` (payments) stays 14 because it counts v1 only.
3. **Overlap annotations (task item 8).** Added as a free-text `disambiguation` field on both sides of each pair: the flaw and the sound-section entry. Besides the pairs named in the task, I also annotated lakehouse F05 / §14.6 and lakehouse F15 / §9 (v2), because both are on the audit's P1-9 list.
4. **Remedy-as-requirement (task item 4).** For "every item" credit rules (item_b), the remedy item was removed from `credit_requires`, and the existing fix field was prefixed to say that its contents are acceptable examples, not requirements. item_b's fix field is `acceptable_fix`; it was not renamed to `acceptable_recommendation`, to keep the schema unchanged. For clinical ("core claims" rule), F06's remedy item was removed (it is already in `acceptable_recommendation`). F11 item 4 was marked `(supporting, not required)`, following the `(supporting)` prefix that lakehouse F15 already uses. F04's "claim false" and "consequence" items were merged into one point. The audit lists all four of these under P0-4.
5. **New fields** (minimal, additive): `disambiguation` (task item 8); `still_valid_observations` on lakehouse sound §16 (task item 2 asks for the Art. 17(3) point to be "listed as a still-valid observation"); and `readme_notes_moved_at_sealing` on both blind keys (sealing prep). No existing field was renamed except `new_flaw_id` → `introduced_new_flaw_id` (task item 6), and no field was removed except `v2_new_flaws` (see 2).
6. **Sealing prep.** The full original text of each blind README is preserved verbatim in the key (`readme_notes_moved_at_sealing`). That text includes the defect descriptions, severity breakdown, external-fact topics, safety-relevant defects, file table and scoring guidance. item_a's scoring guidance existed only in its README, so this is also where it now lives in the key. The keys and READMEs are **not** encrypted. Encryption and the access log (research audit §6 P0-7, M5) remain to do.

## Answer-key changes (field level)

Field paths use `[id=…]`, `[flaw_id=…]` or `[section_ref=…]` to identify list entries. Text is quoted in full.

### `eval/blind/item_a/answer_key.json`

**C01.** Field `defects[id=D01].external_fact`. Resolves: Audit P0-1 (Task 1.4 D01, verdict W partial); task item 1.

- Before: 

```text
Directive 2011/83/EU Art. 13(1) and 13(3); UK Consumer Contracts (Information, Cancellation and Additional Charges) Regulations 2013 reg. 34: reimbursement without undue delay and no later than 14 days from the day the trader is informed of the withdrawal decision; trader may withhold reimbursement only until it has received the goods back or the consumer has supplied evidence of having sent them back, whichever is earliest.
```

- After: 

```text
The statutory anchor for the 14-day reimbursement deadline differs by regime, and in no regime is it warehouse inspection. EU (Directive 2011/83/EU; IE, DE, NL, FR): Art. 13(1) requires reimbursement without undue delay and no later than 14 days from the day the trader is informed of the consumer's decision to withdraw. Art. 13(3) lets the trader withhold reimbursement until it has received the goods back or the consumer has supplied evidence of having sent them back, whichever is earliest, unless the trader has offered to collect the goods itself (Commission guidance: an offer to collect at the trader's expense removes the right to withhold). UK (Consumer Contracts (Information, Cancellation and Additional Charges) Regulations 2013 reg. 34(4)-(6)): reimbursement without undue delay and in any event within the reg. 34(5) or 34(6) period. Reg. 34(5): for a sales contract where the trader has not offered to collect the goods, the period ends 14 days after the day the trader receives the goods back or, if earlier, the day the consumer supplies evidence of having sent them back. Reg. 34(6): otherwise (e.g. where the trader has offered to collect), the period ends 14 days after the day the trader is informed of the withdrawal decision. The design offers home collection in the UK and DE (FR-RET-02), so for collection returns there the clock runs from notification with no withholding right (UK reg. 34(6); CRD Art. 13(3) exception). Whether that offer also changes the rule for a UK or DE customer who chose a label or store return is a point of legal interpretation; a reviewer applying either reading is not penalised.
```


**C02.** Field `defects[id=D01].title`. Resolves: Audit P0-1 (Task 1.4 D01, verdict W partial); task item 1.

- Before: `Refund deadline anchored to warehouse inspection instead of the withdrawal notification; proof of dispatch ignored`
- After: 

```text
Refund deadline anchored to warehouse inspection instead of the statutory anchor (withdrawal notification, or receipt/evidence of sending under UK CCR reg. 34(5)); proof of dispatch ignored
```


**C03.** Field `defects[id=D01].why_it_matters`. Resolves: Audit P0-1 (Task 1.4 D01, verdict W partial); task item 1.

- Before: 

```text
For statutory withdrawals the 14-day clock runs from notification of withdrawal, and the trader may only withhold until goods are received or proof of sending is supplied, whichever is earlier. The design routinely refunds 3-5 weeks after notification and well after receipt; a customer holding a carrier drop-off receipt is entitled to be refunded. This is a systematic breach across all five markets and a direct cause of the WISMR contacts the programme is meant to reduce.
```

- After: 

```text
For statutory withdrawals the 14-day clock runs from notification of withdrawal (EU Art. 13(1); UK reg. 34(6) where collection is offered) or, in the UK where collection is not offered, from receipt of the goods or evidence of sending, whichever is earlier (reg. 34(5)). Under CRD Art. 13(3) the trader may withhold only until the goods are received or proof of sending is supplied, whichever is earlier, and not at all where it offered to collect. In no regime may the deadline run from inspection, and a carrier drop-off receipt is evidence of sending that the design ignores. The design routinely refunds 3-5 weeks after notification and well after receipt; a customer holding a carrier drop-off receipt is entitled to be refunded. This is a systematic breach across all five markets and a direct cause of the WISMR contacts the programme is meant to reduce.
```


**C04.** Field `defects[id=D01].credit_requires`. Resolves: Audit P0-1 (Task 1.4 D01, verdict W partial); task item 1.

- Before: 

```text
Reviewer must state that the refund deadline must be measured from the customer's notification of withdrawal (not from inspection), and that withholding is permitted only until receipt of the goods or evidence of dispatch, whichever is earlier. Citing CRD Art. 13 or CCR 2013 reg. 34 (or an unambiguous paraphrase of the rule) is required for full credit. Merely saying 'refunds are slow' or 'inspection SLA is long' earns no credit.
```

- After: 

```text
Reviewer must state that the refund deadline must not be anchored to warehouse inspection, and must give a legally correct anchor for at least one regime: (a) 14 days from the customer's notification of withdrawal, with withholding permitted only until receipt of the goods or evidence of sending, whichever is earlier (EU CRD Art. 13(1) and 13(3)); (b) 14 days from receipt of the goods or evidence of sending, whichever is earlier (UK CCR 2013 reg. 34(5), trader has not offered collection); or (c) 14 days from notification with no right to withhold, because the trader offered to collect (UK reg. 34(6); CRD Art. 13(3) exception). Unless the reviewer relies on (c), they must also state that carrier evidence of sending (e.g. the acceptance scan the design refuses to use) must count: it starts the UK reg. 34(5) clock and ends any EU withholding. Citing CRD Art. 13 or CCR 2013 reg. 34 (or an unambiguous paraphrase of the applicable rule) is required for full credit. A reviewer who states only one regime's rule correctly, or does not discuss the collection-offer exception, still earns full credit; noting that offering home collection removes the withholding right is correct and supporting, not required. Merely saying 'refunds are slow' or 'inspection SLA is long' earns no credit.
```


**C05.** Field `defects[id=D01].acceptable_fix`. Resolves: Audit P0-1 (Task 1.4 D01, verdict W partial); task item 1.

- Before: 

```text
For returns within the statutory period, compute due_date = withdrawal_notified_at + 14 days; make the refund eligible on the earliest of returns-centre receipt or carrier acceptance scan (evidence of sending); do not gate on inspection (apply any diminished-value deduction from a fast receipt check, or recover it afterwards). Rebase FR-REF-02, the SLA monitor and AC-07 on the statutory anchor. Commercial (day 15-30) returns may keep inspection gating if disclosed. Address empty-box fraud with risk-scored exceptions and carrier weight checks rather than blanket withholding.
```

- After: 

```text
For returns within the statutory period, compute the statutory due date per regime: EU markets, due = withdrawal_notified_at + 14 days, with release allowed to wait only until the earliest of returns-centre receipt or carrier acceptance scan (evidence of sending), and no withholding for collection returns; UK label and store returns, due = earliest of returns-centre receipt or carrier acceptance scan + 14 days (reg. 34(5)); UK collection returns, due = withdrawal_notified_at + 14 days (reg. 34(6)). A single conservative rule satisfies all five markets: due = withdrawal_notified_at + 14 days, released no later than the earliest of receipt or carrier acceptance scan, with no withholding for collection returns. Do not gate on inspection (apply any diminished-value deduction from a fast receipt check, or recover it afterwards). Rebase FR-REF-02, the SLA monitor and AC-07 on the statutory anchor. Commercial (day 15-30) returns may keep inspection gating if disclosed. Address empty-box fraud with risk-scored exceptions and carrier weight checks rather than blanket withholding.
```


**C06.** Field `defects[id=D03].disambiguation`. Resolves: Audit P1-9 (Task 6 item_a 3.1.3 FR-RET-01, medium); task item 8.

- Before: *(absent)*
- After: 

```text
D03 is the implementation in section 7.4 step 2 (eligibility check `now <= order.placedAt + 30 days`). FR-RET-01 (3.1.3) is listed in requirement_ids because it is the requirement the implementation contradicts; FR-RET-01's own wording (30 days per shipment from delivery, with a 14-days-from-last-delivery floor) is a deliberately sound section. A finding that cites FR-RET-01 as the requirement violated by the 7.4 placedAt anchor matches D03 and is not a false positive. Only a finding that says FR-RET-01 itself is wrong (e.g. the window must be 14 days, or per-shipment windows breach the last-item rule) is the false positive.
```


**C07.** Field `deliberately_sound_sections[location=3.1.3 FR-RET-01].disambiguation`. Resolves: Audit P1-9 (Task 6 item_a 3.1.3 FR-RET-01, medium); task item 8.

- Before: *(absent)*
- After: 

```text
D03 is the implementation in section 7.4 step 2 (eligibility check `now <= order.placedAt + 30 days`). FR-RET-01 (3.1.3) is listed in requirement_ids because it is the requirement the implementation contradicts; FR-RET-01's own wording (30 days per shipment from delivery, with a 14-days-from-last-delivery floor) is a deliberately sound section. A finding that cites FR-RET-01 as the requirement violated by the 7.4 placedAt anchor matches D03 and is not a false positive. Only a finding that says FR-RET-01 itself is wrong (e.g. the window must be 14 days, or per-shipment windows breach the last-item rule) is the false positive.
```


**C08.** Field `readme_notes_moved_at_sealing`. Resolves: Research audit §4.3 point 1 and §6 P0-7 (sealing prep); task "Sealing prep".

- Before: *(absent)*
- After: 

```text
New top-level string field holding the full verbatim pre-sealing README.md text (prefixed with a one-sentence provenance note). See the README entries below.
```



### `eval/blind/item_b/answer_key.json`

**C09.** Field `defects[id=DEF-03].external_fact`. Resolves: Audit P0-5 (Task 1.5 DEF-03 caveat); task item 5 (see note on item_a D03 vs item_b DEF-03).

- Before: 

```text
IEEE 1547-2018 clause 8.1 (unintentional islanding) requires DER to detect the island, cease to energize and trip within 2 seconds of island formation (not 5 s). UL 1741 SB / IEEE 1547.1 test to the 2 s limit.
```

- After: 

```text
IEEE 1547-2018 clause 8.1 (unintentional islanding; sub-clause 8.1.2 in the 2018 text per most secondary sources, though one secondary source cites 8.1.1) requires DER to detect the island, cease to energize the Area EPS and trip within 2 seconds of island formation (not 5 s). UL 1741 SB / IEEE 1547.1 test to the 2 s limit. The standard is paywalled and was not read in full during the 2026-10-02 audit, so a provision allowing a different clearing time by agreement with the Area EPS operator (utility) cannot be ruled out.
```


**C10.** Field `defects[id=DEF-03].credit_requires`. Resolves: Audit P0-5 (Task 1.5 DEF-03 caveat); task item 5 (see note on item_a D03 vs item_b DEF-03).

- Before: 

```text
[
  "States that IEEE 1547-2018 requires cease-to-energize/trip within 2 s for unintentional islanding, so the 5 s value in FR-GRID-04 (and AC-05 / 7.5) is wrong",
  "Notes the safety or interconnection-compliance consequence"
]
```

- After: 

```text
[
  "States that IEEE 1547-2018 requires cease-to-energize/trip within 2 s for unintentional islanding, so the 5 s value in FR-GRID-04 (and AC-05 / 7.5) is wrong or unsupported by the cited clause. Qualifying the 2 s limit as 'unless otherwise agreed with (or specified by) the utility / Area EPS operator' still earns credit, provided the reviewer says the design's unqualified 5 s claim is not supported by clause 8.1. Any clause reference within 8.1 (8.1, 8.1.1 or 8.1.2) is acceptable.",
  "Notes the safety or interconnection-compliance consequence"
]
```


**C11.** Field `defects[id=DEF-03].disambiguation`. Resolves: Audit P1-9 (Task 6 item_b 7.5 vs DEF-03/DEF-13, medium); task item 8.

- Before: *(absent)*
- After: 

```text
DEF-03 also appears in sound section '7.5 unplanned-loss timeline arithmetic': Section 7.5 step 2 carries DEF-03's 5 s separation value (FR-GRID-04), and DEF-13 cites 7.5 as the unplanned-loss sequence that AC-08 never tests. A finding that the 7.5 step-2 '<= 5 s' separation is non-compliant with IEEE 1547-2018 (2 s) matches DEF-03; a finding that the 7.5 sequence (loss-of-mains detection, dead-bus black start, restoration timing) is not verified by any acceptance test matches DEF-13. Neither is a false positive against this sound section. Only a claim that the 7.5 step times do not add up to at most 9 s (given the stated 5 s bound) is the false positive.
```


**C12.** Field `defects[id=DEF-12].credit_requires`. Resolves: Audit P0-4 (Task 5 item_b DEF-12: remedy as credit requirement); task item 4.

- Before: 

```text
[
  "States that NTP from corporate/internet servers cannot reliably deliver ±1 ms alignment",
  "Recommends a local precision time source (GNSS clock with PTP/IEEE 1588 power profile and/or IRIG-B for relays)"
]
```

- After: 

```text
[
  "States that NTP from corporate/internet servers cannot reliably deliver ±1 ms alignment"
]
```


**C13.** Field `defects[id=DEF-12].acceptable_fix`. Resolves: Audit P0-4 (Task 5 item_b DEF-12: remedy as credit requirement); task item 4.

- Before: 

```text
Install a local GNSS-disciplined grandmaster clock in Zone 1/2. Distribute time via IEEE 1588 PTP (IEC/IEEE 61850-9-3 power profile) over the PRP network and/or IRIG-B to relays, with NTP from the local clock for devices that only support NTP (and relax NFR-OBS-02 for those). Monitor sync status.
```

- After: 

```text
Acceptable recommendations (examples only; no specific remedy is required for credit, and any valid remedy is acceptable, e.g. a local precision time source under another name, IRIG-B, or relaxing NFR-OBS-02 to an achievable value with a documented rationale): Install a local GNSS-disciplined grandmaster clock in Zone 1/2. Distribute time via IEEE 1588 PTP (IEC/IEEE 61850-9-3 power profile) over the PRP network and/or IRIG-B to relays, with NTP from the local clock for devices that only support NTP (and relax NFR-OBS-02 for those). Monitor sync status.
```


**C14.** Field `defects[id=DEF-13].disambiguation`. Resolves: Audit P1-9 (Task 6 item_b 7.5 vs DEF-03/DEF-13, medium); task item 8.

- Before: *(absent)*
- After: 

```text
DEF-13 also cites sound section '7.5 unplanned-loss timeline arithmetic': Section 7.5 step 2 carries DEF-03's 5 s separation value (FR-GRID-04), and DEF-13 cites 7.5 as the unplanned-loss sequence that AC-08 never tests. A finding that the 7.5 step-2 '<= 5 s' separation is non-compliant with IEEE 1547-2018 (2 s) matches DEF-03; a finding that the 7.5 sequence (loss-of-mains detection, dead-bus black start, restoration timing) is not verified by any acceptance test matches DEF-13. Neither is a false positive against this sound section. Only a claim that the 7.5 step times do not add up to at most 9 s (given the stated 5 s bound) is the false positive.
```


**C15.** Field `defects[id=DEF-14].disambiguation`. Resolves: Audit P1-9 (Task 6 item_b FR-GRID-01 vs DEF-14, medium); task item 8.

- Before: *(absent)*
- After: 

```text
DEF-14 lists FR-GRID-01 because the utility settings file that FR-GRID-01 relies on (OI-02) is scheduled for Phase 3, while Phase 1 energises the BESS grid-parallel and AC-04 (which verifies FR-GRID-01 to FR-GRID-03 against that file) is a Phase 1 exit criterion. A sequencing finding that cites FR-GRID-01 matches DEF-14 and is not a false positive. FR-GRID-01's content (normal performance Category B, abnormal performance Category III, utility settings authority) is sound; only a claim that those categories or that delegation are wrong is the false positive.
```


**C16.** Field `deliberately_sound_sections[section=FR-GRID-01, FR-GRID-03 and 7.4: IEEE 154].disambiguation`. Resolves: Audit P1-9 (Task 6 item_b FR-GRID-01 vs DEF-14, medium); task item 8.

- Before: *(absent)*
- After: 

```text
DEF-14 lists FR-GRID-01 because the utility settings file that FR-GRID-01 relies on (OI-02) is scheduled for Phase 3, while Phase 1 energises the BESS grid-parallel and AC-04 (which verifies FR-GRID-01 to FR-GRID-03 against that file) is a Phase 1 exit criterion. A sequencing finding that cites FR-GRID-01 matches DEF-14 and is not a false positive. FR-GRID-01's content (normal performance Category B, abnormal performance Category III, utility settings authority) is sound; only a claim that those categories or that delegation are wrong is the false positive.
```


**C17.** Field `deliberately_sound_sections[section=7.5 unplanned-loss timeline arithmetic].disambiguation`. Resolves: Audit P1-9 (Task 6 item_b 7.5 vs DEF-03/DEF-13, medium); task item 8.

- Before: *(absent)*
- After: 

```text
Section 7.5 step 2 carries DEF-03's 5 s separation value (FR-GRID-04), and DEF-13 cites 7.5 as the unplanned-loss sequence that AC-08 never tests. A finding that the 7.5 step-2 '<= 5 s' separation is non-compliant with IEEE 1547-2018 (2 s) matches DEF-03; a finding that the 7.5 sequence (loss-of-mains detection, dead-bus black start, restoration timing) is not verified by any acceptance test matches DEF-13. Neither is a false positive against this sound section. Only a claim that the 7.5 step times do not add up to at most 9 s (given the stated 5 s bound) is the false positive.
```


**C18.** Field `readme_notes_moved_at_sealing`. Resolves: Research audit §4.3 point 1 and §6 P0-7 (sealing prep); task "Sealing prep".

- Before: *(absent)*
- After: 

```text
New top-level string field holding the full verbatim pre-sealing README.md text (prefixed with a one-sentence provenance note). See the README entries below.
```



### `eval/synthetic/payments_orchestration/answer_key.json`

**C19.** Field `version_notes`. Resolves: Audit P1-7 (Task 3 payments finding (a)); task item 6.

- Before: 

```text
design_v1.md (v1.0) contains 14 planted flaws F01-F14 (4 critical, 6 major, 4 minor) and 5 sound sections. design_v2.md (v1.1) fixes 6 of them (F02 minor, F03 major, F04 major, F06 critical, F08 critical, F12 minor). The F04 fix introduces a new critical regression, F15 (cross-region idempotency race on a DynamoDB global table). The other 8 flaws are unchanged. v2 has a neutral revision-history table listing the changed sections, as a real re-review would; it does not name flaws. Severity is the expected impact if built as written. Graders should match findings to flaws by substance (what_a_correct_finding_must_mention), not by wording. A finding that names the right section but the wrong mechanism should get no more than partial credit.
```

- After: 

```text
design_v1.md (v1.0) contains 14 planted flaws F01-F14 (4 critical, 6 major, 4 minor) and 5 sound sections. design_v2.md (v1.1) fixes 6 of them (F02 minor, F03 major, F04 major, F06 critical, F08 critical, F12 minor). The F04 fix introduces a new critical regression, F15 (cross-region idempotency race on a DynamoDB global table). The other 8 flaws are unchanged. v2 has a neutral revision-history table listing the changed sections, as a real re-review would; it does not name flaws. Severity is the expected impact if built as written. Graders should match findings to flaws by substance (what_a_correct_finding_must_mention), not by wording. A finding that names the right section but the wrong mechanism should get no more than partial credit. v2_changes convention (applied 2026-10-02): a flaw whose fix introduced a new flaw has status 'fixed' plus introduced_new_flaw_id; the new flaw is listed in flaws[] with introduced_in 'v2' and introduced_by_fix_of. So exactly six v2_changes entries have status 'fixed'.
```


**C20.** Field `flaws[id=F15]`. Resolves: Audit P1-7; task item 6 convention (new flaw lives in flaws[]).

- Before: `(absent from flaws[]; the object was in v2_new_flaws[0])`
- After: `Same F15 object moved unchanged to the end of flaws[] (keeps introduced_in "v2" and introduced_by_fix_of)`

**C21.** Field `v2_new_flaws`. Resolves: Audit P1-7; task item 6 convention (new flaw lives in flaws[]).

- Before: `list with one object (F15), see the next entry`
- After: *(removed)*

**C22.** Field `v2_changes[flaw_id=F04].status`. Resolves: Audit P1-7 (Task 3 payments finding (a)); task item 6.

- Before: `regressed`
- After: `fixed`

**C23.** Field `v2_changes[flaw_id=F04].new_flaw_id`. Resolves: Audit P1-7 (Task 3 payments finding (a)); task item 6.

- Before: `F15`
- After: *(removed)*

**C24.** Field `v2_changes[flaw_id=F04].introduced_new_flaw_id`. Resolves: Audit P1-7 (Task 3 payments finding (a)); task item 6.

- Before: *(absent)*
- After: `F15`


### `eval/synthetic/clinical_rpm/answer_key.json`

**C25.** Field `version_notes`. Resolves: Audit P1-7; task item 6.

- Before: 

```text
design_v1.md contains 14 planted flaws F01–F14 (4 critical: F04, F08, F10, F14; 6 major: F02, F03, F05, F09, F11, F12; 4 minor: F01, F06, F07, F13). design_v2.md is the 'updated artefact' for re-review. It fixes six flaws (F02, F04, F07, F08, F10, F12: three critical, two major, one minor). The F10 fix introduces a new regression flaw F15 (major, Section 10.3 delivery assurance). The remaining eight flaws (F01, F03, F05, F06, F09, F11, F13, F14) are unchanged. Section numbering is identical across versions. v2 adds a neutral revision-history table. v2's FR-7 acceptance criterion (d), which tests a device with a −10 min clock offset, would in practice expose F11, because such a device's events are dropped by ASA; credit a reviewer who notes this. Open flaws in v1: 14 (4 critical / 6 major / 4 minor). Open flaws in v2: F01, F03, F05, F06, F09, F11, F13, F14, F15 = 9 (1 critical: F14; 5 major: F03, F05, F09, F11, F15; 3 minor: F01, F06, F13).
```

- After: 

```text
design_v1.md contains 14 planted flaws F01–F14 (4 critical: F04, F08, F10, F14; 6 major: F02, F03, F05, F09, F11, F12; 4 minor: F01, F06, F07, F13). design_v2.md is the 'updated artefact' for re-review. It fixes six flaws (F02, F04, F07, F08, F10, F12: three critical, two major, one minor). The F10 fix introduces a new regression flaw F15 (major, Section 10.3 delivery assurance). The remaining eight flaws (F01, F03, F05, F06, F09, F11, F13, F14) are unchanged. Section numbering is identical across versions. v2 adds a neutral revision-history table. v2's FR-7 acceptance criterion (d), which tests a device with a −10 min clock offset, would in practice expose F11, because such a device's events are dropped by ASA; credit a reviewer who notes this. Open flaws in v1: 14 (4 critical / 6 major / 4 minor). Open flaws in v2: F01, F03, F05, F06, F09, F11, F13, F14, F15 = 9 (1 critical: F14; 5 major: F03, F05, F09, F11, F15; 3 minor: F01, F06, F13). v2_changes convention (applied 2026-10-02): a flaw whose fix introduced a new flaw has status 'fixed' plus introduced_new_flaw_id; the new flaw is listed in flaws[] with introduced_in 'v2' and introduced_by_fix_of. So exactly six v2_changes entries have status 'fixed'.
```


**C26.** Field `flaws[id=F04].what_a_correct_finding_must_mention`. Resolves: Audit P0-4 (Task 5 clinical F04: merge "claim false" and "consequence"); task item 4 ("any others the audit lists").

- Before: 

```text
[
  "S2 is 6 M messages/day per unit (not 60 M)",
  "3 × S2 = 18 M/day versus ~138 M/day required",
  "send throttle 120 msg/s per S2 unit (360 msg/s) versus 1,600–2,000 msg/s",
  "claim that the throttle is not binding is false",
  "consequence: messages rejected or throttled, so monitoring and alerting stop"
]
```

- After: 

```text
[
  "S2 is 6 M messages/day per unit (not 60 M)",
  "3 × S2 = 18 M/day versus ~138 M/day required",
  "send throttle 120 msg/s per S2 unit (360 msg/s) versus 1,600–2,000 msg/s",
  "claim that the throttle is not binding is false, with the consequence: messages rejected or throttled, so monitoring and alerting stop (one point)"
]
```


**C27.** Field `flaws[id=F05].disambiguation`. Resolves: Audit P1-9 (Task 6 clinical §4/4.3 vs F05/F06, medium); task item 8.

- Before: *(absent)*
- After: 

```text
F05 cites 4.3 only for the 10-s persistence window in Table 4.3b, which the Section 10.4 latency budget omits. A finding that says the 10.4 budget or the NFR-2 headroom claim ignores the 4.3 persistence window (and the 5-s batching) matches F05 and is not a false positive against Section 4. Only a finding that says the persistence window itself is a defect, or should be removed, is the Section 4 trap. Likewise, F06 is the FR-8 mis-citation of IEC 60601-1-8 clause 6.11 for escalation intervals; the 4.3 use of IEC 60601-1-8 for priority semantics is sound.
```


**C28.** Field `flaws[id=F06].what_a_correct_finding_must_mention`. Resolves: Audit P0-4 (Task 1.2 F06 fix; Task 5 clinical F06: remedy as must-mention); task item 4.

- Before: 

```text
[
  "IEC 60601-1-8 does not specify these escalation intervals",
  "citation to clause 6.11 is incorrect or unverifiable",
  "the timings must be sourced from clinical governance (CSB/clinical safety case)"
]
```

- After: 

```text
[
  "IEC 60601-1-8 does not specify these escalation intervals",
  "citation to clause 6.11 is incorrect or unverifiable"
]
```


**C29.** Field `flaws[id=F06].acceptable_recommendation`. Resolves: Audit P0-4 (Task 1.2 F06 fix; Task 5 clinical F06: remedy as must-mention); task item 4.

- Before: 

```text
Re-source FR-8 to a CSB decision and record the rationale in the clinical safety case. If IEC 60601-1-8 is cited, cite it for what it covers (alarm priorities, distributed-alarm-system delivery and communication-failure indication) and add those as requirements.
```

- After: 

```text
Examples of acceptable recommendations (not required for credit; any valid remedy is acceptable): Re-source FR-8 to a CSB decision and record the rationale in the clinical safety case. If IEC 60601-1-8 is cited, cite it for what it covers (alarm priorities, distributed-alarm-system delivery and communication-failure indication) and add those as requirements.
```


**C30.** Field `flaws[id=F06].distractor_notes`. Resolves: Audit P0-4 (Task 1.2 F06 fix; Task 5 clinical F06: remedy as must-mention); task item 4.

- Before: 

```text
Section 4.3's use of IEC 60601-1-8 for High/Medium/Low priority semantics is correct and should not be flagged. Arguing that 60 s is clinically too long or too short is a matter of clinical opinion, not this flaw.
```

- After: 

```text
Section 4.3's use of IEC 60601-1-8 for High/Medium/Low priority semantics is correct and should not be flagged. Arguing that 60 s is clinically too long or too short is a matter of clinical opinion, not this flaw. Saying that the timings must be sourced from clinical governance (CSB / clinical safety case) is a remedy, not part of detection: a finding that makes the two detection points with a different valid remedy, or none, earns full credit.
```


**C31.** Field `flaws[id=F11].what_a_correct_finding_must_mention`. Resolves: Audit P0-4 (Task 5 clinical F11 item 4 "silent in ADX" should be supporting); task item 4 ("any others the audit lists").

- Before: 

```text
[
  "event time = device_ts with 5 s late tolerance and Drop",
  "buffered/replayed readings (30 min / 4 h) are dropped from evaluation",
  "device clock skew causes all events from a device to be treated as late",
  "silent: data still appears in ADX trends but is never evaluated"
]
```

- After: 

```text
[
  "event time = device_ts with 5 s late tolerance and Drop",
  "buffered/replayed readings (30 min / 4 h) are dropped from evaluation",
  "device clock skew causes all events from a device to be treated as late",
  "(supporting, not required) silent: data still appears in ADX trends but is never evaluated"
]
```


**C32.** Field `flaws[id=F15].introduced_by_fix_of`. Resolves: Audit P1-8; task item 7.

- Before: *(absent)*
- After: `F10`

**C33.** Field `sound_sections[section_ref=4 (Clinical Alerting Model, esp. 4.2 pNE].disambiguation`. Resolves: Audit P1-9 (Task 6 clinical §4/4.3 vs F05/F06, medium); task item 8.

- Before: *(absent)*
- After: 

```text
F05 cites 4.3 only for the 10-s persistence window in Table 4.3b, which the Section 10.4 latency budget omits. A finding that says the 10.4 budget or the NFR-2 headroom claim ignores the 4.3 persistence window (and the 5-s batching) matches F05 and is not a false positive against Section 4. Only a finding that says the persistence window itself is a defect, or should be removed, is the Section 4 trap. Likewise, F06 is the FR-8 mis-citation of IEC 60601-1-8 clause 6.11 for escalation intervals; the 4.3 use of IEC 60601-1-8 for priority semantics is sound.
```


**C34.** Field `v2_changes[flaw_id=F10].status`. Resolves: Audit P1-7; task item 6.

- Before: `regressed`
- After: `fixed`

**C35.** Field `v2_changes[flaw_id=F10].new_flaw_id`. Resolves: Audit P1-7; task item 6.

- Before: `F15`
- After: *(removed)*

**C36.** Field `v2_changes[flaw_id=F10].introduced_new_flaw_id`. Resolves: Audit P1-7; task item 6.

- Before: *(absent)*
- After: `F15`


### `eval/synthetic/research_lakehouse/answer_key.json`

**C37.** Field `version_notes`. Resolves: Audit P1-7; task item 6.

- Before: 

```text
design_v1.md (v1.0) contains 14 planted flaws F01–F14: 3 internal contradictions, 2 unjustified quantitative claims (F04 checkable against AWS S3 Intelligent-Tiering documentation and pricing; F05 against the OpenSearch k-NN memory formula), 2 missing or unverifiable requirements, 2 security/privacy gaps (F08 obvious, F09 subtle), 2 scalability/failure-mode gaps, 1 ambiguous requirement, 1 acceptance criterion that cannot validate its requirement, and 1 confirmed decision that depends on a pending item. Severity: critical F01, F03, F08, F09; major F02, F05, F07, F10, F11, F14; minor F04, F06, F12, F13. design_v2.md (v1.1) fixes 6 flaws (F03, F05, F06, F08, F10, F13: 2 critical, 2 major, 2 minor). The F10 fix introduces regression F15 (critical; cross-region active-active catalog). The other 8 flaws are unchanged. v2 has a neutral 'Changes since version 1.0' list naming the touched sections; it does not describe any change as a fix. Scoring suggestion: a finding matches a flaw if it names the cited sections/requirements and at least the first two 'what_a_correct_finding_must_mention' items. Penalise recommendations made against 'sound_sections'.
```

- After: 

```text
design_v1.md (v1.0) contains 14 planted flaws F01–F14: 3 internal contradictions, 2 unjustified quantitative claims (F04 checkable against AWS S3 Intelligent-Tiering documentation and pricing; F05 against the OpenSearch k-NN memory formula), 2 missing or unverifiable requirements, 2 security/privacy gaps (F08 obvious, F09 subtle), 2 scalability/failure-mode gaps, 1 ambiguous requirement, 1 acceptance criterion that cannot validate its requirement, and 1 confirmed decision that depends on a pending item. Severity: critical F01, F03, F08, F09; major F02, F05, F07, F10, F11, F14; minor F04, F06, F12, F13. design_v2.md (v1.1) fixes 6 flaws (F03, F05, F06, F08, F10, F13: 2 critical, 2 major, 2 minor). The F10 fix introduces regression F15 (critical; cross-region active-active catalog). The other 8 flaws are unchanged. v2 has a neutral 'Changes since version 1.0' list naming the touched sections; it does not describe any change as a fix. Scoring suggestion: a finding matches a flaw if it names the cited sections/requirements and at least the first two 'what_a_correct_finding_must_mention' items. Penalise recommendations made against 'sound_sections'. v2_changes convention (applied 2026-10-02): a flaw whose fix introduced a new flaw has status 'fixed' plus introduced_new_flaw_id; the new flaw is listed in flaws[] with introduced_in 'v2' and introduced_by_fix_of. So exactly six v2_changes entries have status 'fixed'.
```


**C38.** Field `flaws[id=F01].disambiguation`. Resolves: Audit P1-9 (Task 6 lakehouse §4 vs F01, medium); task item 8.

- Before: *(absent)*
- After: 

```text
F01 cites Section 4 only because the Section 4 tier table (Restricted row: 'Processing outside Westmoor accounts: Not permitted (NFR-5)'; 'Scholar Assist: Indexed (documentation and notebook text only)') states the rule that Section 14.4 and the Section 20 'Generation model' row violate. A finding that cites the Section 4 table as the requirement being contradicted matches F01 and is not a false positive. Only a finding that says the Section 4 tier design itself is wrong (e.g. Restricted documentation must not be indexed at all) is the Section 4 trap.
```


**C39.** Field `flaws[id=F05].disambiguation`. Resolves: Audit P1-9 (Task 6 lakehouse §14.6 vs F05, medium); in the audit's P1-9 list though not in the task's parenthetical.

- Before: *(absent)*
- After: 

```text
F05's consequence (the NFR-3 retrieval budget collapsing at full scale) touches Section 14.6. A finding that says the 14.6 retrieval budget will not hold at full scale because the vector index does not fit in memory (Section 15) matches F05 and is not a false positive against 14.6. Only a finding that attacks the 14.6 budgeting method or its arithmetic (360 ms retrieval, about 1.98 s TTFT) is the 14.6 trap.
```


**C40.** Field `flaws[id=F08].disambiguation`. Resolves: Audit P0-3 (Task 6 lakehouse §16 vs F08, HIGH); task item 3.

- Before: *(absent)*
- After: 

```text
F08 cites Section 16 only for the audit-attribution consequence: because notebook kernels use the faculty service principal (Section 11 'Credentials'), the principal recorded by the Section 16 'Sources' table (CloudTrail session tags with principal `wid`, the Trino event listener principal, OPA decision input) is `svc-<faculty>-analytics`, not the individual researcher, so FR-14 attribution is lost for notebook access. A finding that makes this point, citing the Section 16 'Sources' subsection and/or Section 11, matches F08 and is not a false positive against Section 16. The sound parts of Section 16 are the 'Pipeline and storage' subsection (separate account, Object Lock compliance mode, hash-chained signed manifests, write-only delivery) and the 'Content boundaries' subsection; findings that attack those are judged against the Section 16 trap.
```


**C41.** Field `flaws[id=F15]`. Resolves: Audit P1-7; task item 6 convention (new flaw lives in flaws[]). Also adds F15.disambiguation for Audit P1-9 lakehouse §9 (v2) overlap.

- Before: `(absent from flaws[]; the object was in v2_new_flaws[0])`
- After: 

```text
Same F15 object moved unchanged to the end of flaws[] (keeps introduced_in "v2" and introduced_by_fix_of), plus a new "disambiguation" field: "v2 only: F15 (cross-region active-active catalog with last-writer-wins replication) defeats the atomic compare-and-swap publish described in Section 9 and turns lost commits into deleted data through orphan-file cleanup. Section 9 is sound as written; a v2 finding that cites Section 9 to explain how F15 breaks the WAP publish guarantee or orphan cleanup matches F15 and is not a false positive. Claims that WAP duplicates storage, should validate before writing, or exposes audit-branch data remain the Section 9 trap."
```


**C42.** Field `v2_new_flaws`. Resolves: Audit P1-7; task item 6 convention (new flaw lives in flaws[]).

- Before: `list with one object (F15), see the next entry`
- After: *(removed)*

**C43.** Field `sound_sections[section_ref=4 Data Classification Tiers].disambiguation`. Resolves: Audit P1-9 (Task 6 lakehouse §4 vs F01, medium); task item 8.

- Before: *(absent)*
- After: 

```text
F01 cites Section 4 only because the Section 4 tier table (Restricted row: 'Processing outside Westmoor accounts: Not permitted (NFR-5)'; 'Scholar Assist: Indexed (documentation and notebook text only)') states the rule that Section 14.4 and the Section 20 'Generation model' row violate. A finding that cites the Section 4 table as the requirement being contradicted matches F01 and is not a false positive. Only a finding that says the Section 4 tier design itself is wrong (e.g. Restricted documentation must not be indexed at all) is the Section 4 trap.
```


**C44.** Field `sound_sections[section_ref=9 Ingestion — Write-Audit-Publish].disambiguation`. Resolves: Audit P1-9 (Task 6 lakehouse §9 vs F15, v2 only, medium); in the audit's P1-9 list though not in the task's parenthetical.

- Before: *(absent)*
- After: 

```text
v2 only: F15 (cross-region active-active catalog with last-writer-wins replication) defeats the atomic compare-and-swap publish described in Section 9 and turns lost commits into deleted data through orphan-file cleanup. Section 9 is sound as written; a v2 finding that cites Section 9 to explain how F15 breaks the WAP publish guarantee or orphan cleanup matches F15 and is not a false positive. Claims that WAP duplicates storage, should validate before writing, or exposes audit-branch data remain the Section 9 trap.
```


**C45.** Field `sound_sections[section_ref=14.6 Latency budget].disambiguation`. Resolves: Audit P1-9 (Task 6 lakehouse §14.6 vs F05, medium); in the audit's P1-9 list though not in the task's parenthetical.

- Before: *(absent)*
- After: 

```text
F05's consequence (the NFR-3 retrieval budget collapsing at full scale) touches Section 14.6. A finding that says the 14.6 retrieval budget will not hold at full scale because the vector index does not fit in memory (Section 15) matches F05 and is not a false positive against 14.6. Only a finding that attacks the 14.6 budgeting method or its arithmetic (360 ms retrieval, about 1.98 s TTFT) is the 14.6 trap.
```


**C46.** Field `sound_sections[section_ref=16 Audit Plane].why_sound`. Resolves: Audit P0-2 (Task 1.3 sound §16, verdict W partial); task item 2.

- Before: 

```text
Separate account administered by a different team; S3 Object Lock in compliance mode (root cannot shorten retention); hash-chained, KMS-signed daily manifests; write-only cross-account delivery; identifiers rather than contents; IRB-scoped treatment of audit metadata, consistent with NFR-7 and NFR-8.
```

- After: 

```text
Separate account administered by a different team; S3 Object Lock in compliance mode (root cannot shorten retention); hash-chained, KMS-signed daily manifests; write-only cross-account delivery; identifiers rather than contents; IRB-scoped treatment of audit metadata, consistent with NFR-7 and NFR-8. Correction (2026-10-02 audit): participant pseudonyms that can appear in audit SQL text remain personal data under GDPR (Recital 26), and NFR-7 cites GDPR Art. 17 for EU-resident participants. Retaining them in an immutable audit store can be lawful under an Art. 17(3) exemption (e.g. (b) legal obligation, (d) scientific research, (e) legal claims), but the design does not state which basis applies. That documentation gap is a valid observation; the audit-plane mechanism itself is sound.
```


**C47.** Field `sound_sections[section_ref=16 Audit Plane].trap`. Resolves: Audit P0-2 (Task 1.3 sound §16, verdict W partial); task item 2.

- Before: 

```text
A reviewer may claim Object Lock conflicts with consent-withdrawal erasure (NFR-7 explicitly excludes audit metadata, and audit holds only pseudonyms), or that storing SQL text is a privacy breach.
```

- After: 

```text
False positive only if the reviewer claims that S3 Object Lock must be removed, or that the audit store must be made erasable, to satisfy consent withdrawal (NFR-7 explicitly routes audit metadata to NFR-8, and retention can be lawful under GDPR Art. 17(3)); or that storing SQL text is a privacy breach. Noting that EU participants' pseudonyms in immutable audit records are still personal data and that the design should document its Art. 17(3) basis is NOT a false positive (see still_valid_observations).
```


**C48.** Field `sound_sections[section_ref=16 Audit Plane].still_valid_observations`. Resolves: Audit P0-2 (Task 1.3 sound §16, verdict W partial); task item 2.

- Before: *(absent)*
- After: 

```text
[
  "EU-resident participants' pseudonyms in the immutable audit store are still personal data under GDPR, so the design should document which GDPR Art. 17(3) exemption (b, d or e) justifies retaining them despite consent withdrawal and NFR-7. Score as valid or neutral, never as a false positive, provided the reviewer does not demand removal of Object Lock or an erasable audit store."
]
```


**C49.** Field `sound_sections[section_ref=16 Audit Plane].disambiguation`. Resolves: Audit P0-3 (Task 6 lakehouse §16 vs F08, HIGH); task item 3.

- Before: *(absent)*
- After: 

```text
F08 cites Section 16 only for the audit-attribution consequence: because notebook kernels use the faculty service principal (Section 11 'Credentials'), the principal recorded by the Section 16 'Sources' table (CloudTrail session tags with principal `wid`, the Trino event listener principal, OPA decision input) is `svc-<faculty>-analytics`, not the individual researcher, so FR-14 attribution is lost for notebook access. A finding that makes this point, citing the Section 16 'Sources' subsection and/or Section 11, matches F08 and is not a false positive against Section 16. The sound parts of Section 16 are the 'Pipeline and storage' subsection (separate account, Object Lock compliance mode, hash-chained signed manifests, write-only delivery) and the 'Content boundaries' subsection; findings that attack those are judged against the Section 16 trap.
```


**C50.** Field `v2_changes[flaw_id=F10].status`. Resolves: Audit P1-7; task item 6.

- Before: `regressed`
- After: `fixed`

**C51.** Field `v2_changes[flaw_id=F10].new_flaw_id`. Resolves: Audit P1-7; task item 6.

- Before: `F15`
- After: *(removed)*

**C52.** Field `v2_changes[flaw_id=F10].introduced_new_flaw_id`. Resolves: Audit P1-7; task item 6.

- Before: *(absent)*
- After: `F15`


## README changes

**R01.** `eval/blind/item_a/README.md`, whole file. Resolves: research audit §4.3 point 1 and §6 P0-7; task "Sealing prep".
- Before: a 4-section README ("What this item is", "Seeded defects", "Files", "Scoring guidance"). It gave the defect severities (2 Critical, 6 High, 5 Medium, 1 Low), the categories, the six external-fact topics (EU/UK refund rules, DynamoDB and SQS limits, SQS FIFO message groups, GDPR / S3 Object Lock), the 8 sound areas and the scoring rules. The full text is preserved in `eval/blind/item_a/answer_key.json` → `readme_notes_moved_at_sealing`.
- After: five short sections only. Domain ("E-commerce order management and returns platform for a fictional multi-market UK/EU retailer"); size ("about 8,400 words of prose (9,440 words by `wc -w`…)"); defect count (14); intended use (held-out evaluation, give only `design.md`, final run only); and a note that `answer_key.json` is sealed.

**R02.** `eval/blind/item_b/README.md`, whole file. Resolves: research audit §4.3 point 1 and §6 P0-7; task "Sealing prep".
- Before: a 4-section README naming the defects. It gave severities (1 critical, 7 high, 6 medium), the four external-fact defects (IEEE 1547-2018 island trip time, Modbus FC03 register limit, UL 9540 vs 9540A, IEEE 2030.5 TLS), the three safety-relevant defects (software E-stop, hold-last-setpoint, anti-islanding time), cross-reading hints, the file table and the scoring rules. The full text is preserved in `eval/blind/item_b/answer_key.json` → `readme_notes_moved_at_sealing`.
- After: the same five-section layout. Domain ("Industrial energy management: site energy management system and battery energy storage controls for a fictional distribution centre (US interconnection context)"); size ("about 8,900 words (9,866 words by `wc -w`…)"); defect count (14); intended use; sealed-key note.

**R03.** `eval/synthetic/payments_orchestration/README.md`, paragraph 2 and Files table. Resolves: audit P1-7; task item 6.
- Before: "…the F04 fix introduces one new critical regression (F15, a cross-region idempotency race), and the other 8 flaws are unchanged." / Files row: "Sealed key: flaws F01–F14, v2 regression F15, sound sections, v2 change map".
- After: the same sentence plus: "In `v2_changes`, the six fixed flaws all have status `fixed`; the one whose fix introduced the regression also carries `introduced_new_flaw_id: "F15"`. F15 is listed in `flaws[]` with `introduced_in: "v2"` and `introduced_by_fix_of`." / Files row: "Sealed key: flaws F01–F14 plus v2 regression F15 (all in `flaws[]`), sound sections, v2 change map". The counts (6 fixed, 1 regression, 8 unchanged) were already correct and now match the key's status tally.

**R04.** `eval/synthetic/clinical_rpm/README.md`, paragraph 2. Resolves: audit P1-7; task item 6.
- Before: "It fixes six flaws, one of those fixes introduces a new regression (F15), and the other eight flaws are unchanged."
- After: "It fixes six flaws (F02, F04, F07, F08, F10, F12), the F10 fix introduces a new regression (F15), and the other eight flaws are unchanged." followed by the same convention sentence as R03.

**R05.** `eval/synthetic/research_lakehouse/README.md`, single paragraph. Resolves: audit P1-7; task item 6.
- Before: "…and 8 flaws remain. `answer_key.json` is sealed…" and "score against `v2_changes` and `v2_new_flaws`:".
- After: the convention sentence (as R03) is inserted after "and 8 flaws remain.", and the scoring clause now reads "score against `v2_changes` and F15 (in `flaws[]` with `introduced_in: "v2"`):".

## Design-document changes (P2 realism nits)

**D01.** `eval/synthetic/research_lakehouse/design_v1.md` line 767 and `design_v2.md` line 799 (§23 Readiness Assessment). Resolves: audit P2-15 (Task 5 lakehouse realism tell); task P2.
- Before: "This section answers a direct question: could an engineering team, or an AI coding assistant, build each component from this document alone? The honest answer is partial."
- After: "This section answers a direct question: could the engineering team build each component from this document alone? The honest answer is partial."

**D02.** `eval/synthetic/payments_orchestration/design_v2.md` line 11 (header "Last updated") and line 20 (revision history, v1.1 row). Resolves: audit P2-15 and Task 3 payments finding (b); task P2.
- Before: `2026-10-12` (both places).
- After: `2026-10-01` (both places). This is after v1.0 (2026-09-21) and before the audit date (2026-10-02). No other date in the document depends on it.

Nothing else in any design document was changed.

**PDFs not regenerated.** `research_lakehouse/design_v1.pdf`, `design_v2.pdf` and `payments_orchestration/design_v2.pdf` still contain the old sentence and date. I tested the documented pipeline (python-markdown → LibreOffice `writer_web_pdf_Export`) on the *unmodified* lakehouse v1 Markdown. It did not reproduce the shipped PDF: 27 pages instead of 28, with different line wrapping and around 3,300 differing lines of `pdftotext` output. The original styling or extensions are unknown. Regenerating would therefore have changed far more than the two nits, so I left the PDFs untouched. Regenerate all three with the original settings before PDF inputs are used.

## Audit items deliberately not applied (out of this task's scope)

- P1-6: optional rewording of "deliberately" in payments §23 and clinical §4.3 (design docs; the task said to change nothing else).
- P2-10 to P2-14: canonical schema migration (another agent owns it), category normalisation, computed counts, re-severity of payments F05, and the other neutral observations. These include clinical §6.2 batching vs the 5-s tolerance ("most live messages dropped" should earn F11 credit), payments §23 Stripe 24-h attribution, lakehouse v2 run-rate vs $80k, the Glacier IR minimum and the item_a §6.7 channel scope. One exception: the item_a collection-offer point is now covered inside D01's `external_fact` and `credit_requires`.
- Optional fact notes: payments F15 MRSC regions, clinical F11 clock-ahead wording, lakehouse F04 IA tier, item_a D02 "34(2)-(3)" citation.
- Removing "16" from lakehouse F08 `section_refs`, "4" from F01 and FR-RET-01 from item_a D03: the audit offered "remove or annotate", and I annotated instead (the task asked for disambiguation, not restructuring).

## Validation

- `python3 -c "import json; json.load(open(path))"` passes for all five keys after every edit.
- `v2_changes` status tally: payments fixed = F02, F03, F04, F06, F08, F12; clinical fixed = F02, F04, F07, F08, F10, F12; lakehouse fixed = F03, F05, F06, F08, F10, F13. That is 6 each, with 8 `unchanged` each and no `regressed`. F15 is present once in each `flaws[]` with `introduced_by_fix_of` = F04 / F10 / F10.
- A recursive diff of every file under `eval/` against a pre-edit snapshot shows changes only in the 5 keys, 5 READMEs and the 3 Markdown design files listed above.
