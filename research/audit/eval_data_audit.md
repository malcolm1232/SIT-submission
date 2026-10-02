# Evaluation dataset audit: five design-review items

Audit date: 2026-10-02. Scope: `eval/synthetic/{payments_orchestration,clinical_rpm,research_lakehouse}` and `eval/blind/{item_a,item_b}`. The eval files were read only. Nothing in `eval/` was modified and no git commands were run.

**Source access.** The egress proxy blocks docs.aws.amazon.com, learn.microsoft.com, legislation.gov.uk, eur-lex, PCI SSC, IEEE, NIST and PDPC. I used the sources below instead and labelled each one:

- **P (primary mirror).** Vendor-owned documentation published on GitHub:
  - `awsdocs/amazon-dynamodb-developer-guide`, `awsdocs/amazon-sqs-developer-guide`, `awsdocs/amazon-s3-developer-guide` and `awsdocs/aws-cloudhsm-user-guide`. These are archived, so the text dates from 2023 or earlier.
  - `MicrosoftDocs/azure-docs`. The pages fetched carry ms.date values from 2025 to 2026.
  - `opensearch-project/documentation-website`.
  - `postgres/postgres` docs source (REL_16).
- **P-snippet.** Official text that I saw only as a search-engine extract, not fetched in full. Examples: AWS SLA pages, AWS What's New posts, the IETF draft, BI regulation listings.
- **S (secondary).** Reputable secondary sources: law-firm or regulator summaries, the UL.com product pages, the libmodbus source (which cites the Modbus spec page by page), the GRIDAPPSD/IEEE 2030.5 implementer issues, and standards-preview sites.
- **K (not fetched).** A well-established fact that I did not retrieve in this session.

---

## Summary of verdicts

| Item | External-fact flaws checked | Key correct | Key wrong | Unverifiable | Leakage hits | v2 integrity | Sound-section overlaps needing a key fix |
|---|---|---|---|---|---|---|---|
| payments_orchestration | 7 (F01, F04, F06, F07, F11, F15, plus sound §15 and §23 facts) | 7 | 0 | 0 | 0 real (1 benign "deliberately" in sound §23) | All 14 statuses confirmed. F15 present. | None |
| clinical_rpm | 10 (F01, F03, F04, F06, F07, F08, F09, F11, F15, §17.1 breach rule) | 8 confirmed, 2 reasoned/known (F01, F09) | 0 | 0 | 0 real (2 benign) | All 14 statuses confirmed. F15 present. | F05 refs 4.3, inside sound §4 (the trap text covers it) |
| research_lakehouse | 6 (F04, F05, F06, F10, sound §16 Object Lock/GDPR, F15 reasoning) | 5 | **1 partial** (sound §16 rationale) | 0 | 0 | All 14 statuses confirmed. F15 present. | **F08 refs §16 (sound, no disambiguation)**; F01 refs §4 (sound) |
| blind/item_a | 8 (D01, D02, D04, D05, D06, D10, D12, sound CRD articles) | 7 | **1 partial** (D01, UK refund timing) | 0 | 0 real (enum names like `WRONG_ITEM`) | n/a | Several shared sections, all disambiguated at sub-item level |
| blind/item_b | 5 (DEF-03, DEF-04, DEF-05, DEF-06, sound FR-GRID-05) | 5 (DEF-03 with a caveat) | 0 | DEF-03 extension clause cannot be ruled out (standard paywalled) | 0 real ("unintentional" matched the "intentional" regex) | n/a | Sound "7.5 arithmetic" vs DEF-03/DEF-13; FR-GRID-01 vs DEF-14 |

**Overall count.** There are 2 key-wrong verdicts and both are partial: item_a D01 (UK Consumer Contracts Regulations reg. 34) and the research_lakehouse sound-section §16 rationale. No planted "correct value" was found to be outright false. The highest-risk mechanical issue is that some flaws cite a section the same key lists as sound, so a grader applying section-level false-positive rules could penalise a correct finding.

---

## Task 1. External-fact verification

Verdict codes: **C** means the key is correct, **W** means the key is wrong (partially or fully), **U** means unverifiable.

### 1.1 payments_orchestration

| Flaw | Claim in doc | Claim in key | What the source says (quality) | Verdict | Fix |
|---|---|---|---|---|---|
| F04 | §9.3 (v1 l.323): "a single partition sustains up to 10,000 WCU/s"; 2 WCU per request; PK `merchant_id`; LSI on `created_at` | 1,000 WCU / 3,000 RCU per partition; on-demand does not lift it; 1 WCU per KB; LSI prevents split-for-heat; 10 GB item-collection cap | P: "every partition in the table will strive to deliver the full capacity of 3,000 RCU and 1,000 WCU" (bp-partition-key-design); "Adaptive capacity will not split item collections across multiple partitions of the table when there is a local secondary index"; "For tables with local secondary indexes, there is a 10 GB size limit per partition key value" (LSI.md) | C | None |
| F15 (v2) | §9.4 (v2 l.335): MREC global table conditional put gives "exactly one request ... regardless of which region receives it" | MREC is last-writer-wins, conditions are evaluated against the local replica, so the claim is false | P: "DynamoDB global tables use a 'last writer wins' reconciliation" (globaltables_HowItWorks); transactions are ACID "ONLY within the Region where the write is made". P-snippet: MRSC "writes ... are evaluated against the latest write from any Region", in contrast to MREC. MRSC runs only in fixed Region sets (AP set = Tokyo/Seoul/Osaka) and needs exactly 3 Regions or 2 plus a witness. | C | Optional: note that MRSC is not available for ap-southeast-1/-3 as of the GA Region sets. The key's hedge "only if available" is already adequate. |
| F06 | NFR-6 / §12.4: PCI DSS v4.0 Req. 3.2.1 and 3.3.2 permit encrypted SAD "until the transaction is settled" | 3.3.1 / 3.3.1.2 forbid SAD/CVC after authorization even if encrypted; 3.3.2 only requires encryption before authorization completes; 3.2.1 is retention policy | S: 3.3.1 "SAD is not retained after authorization, even if encrypted"; 3.3.2 "SAD that is stored electronically prior to completion of authorization is encrypted using strong cryptography"; 3.2.1 covers SAD "stored prior to completion of authorization". The doc cites the wrong clauses, exactly as the key states. | C | None. Optional: mention v4.0.1's issuer carve-out, which does not apply here. |
| F01 | §13.1 sends `card_number` to FRV-1 while §12.2 says the Fraud Hook is out of scope | Any system that stores, processes or transmits PAN is in the CDE; FRV-1 is a TPSP under Req. 12.8 | K/S: CDE definition and 12.8 TPSP management are standard PCI DSS. The note that BIN8 + last 4 is acceptable truncation matches the PCI SSC FAQ on 8-digit BINs. | C | None |
| F07 | No residency requirement; ID payment data primary in Singapore | BI regulation (PBI 22/23/PBI/2020) and GR 71/2019 "can require" domestic processing | P-snippet/S: PBI 22/23/PBI/2020 requires domestic processing of domestic payment transactions (initiation, authorization, clearing, settlement) | C (hedged wording is appropriate) | None |
| F11 | §12.3: one CloudHSM HSM in one AZ | AWS recommends ≥ 2 HSMs across AZs | P: "For production clusters, you should have at least two HSM instances spread across two availability zones ... at least three ... for durability of newly generated keys" (best-practices) | C | None |
| Sound §15 | IDR exponent 2 | Correct per ISO 4217 | S: ISO 4217 lists IDR with 2 minor units | C | None |
| Sound §23 | IETF Idempotency-Key draft: 409 in-flight, 422 payload mismatch | Accurate | P-snippet: draft-ietf-httpapi-idempotency-key-header-07: 409 for a retry while processing, 422 for a reused key with a different payload | C | Nit: the "24-hour retention" in the same cell is Stripe practice, not the draft. A pedantic reviewer could raise it. Treat that as neutral, not as a false positive. |

### 1.2 clinical_rpm

| Flaw | Claim in doc | Claim in key | What the source says (quality) | Verdict | Fix |
|---|---|---|---|---|---|
| F04 | §7.3 (v1 l.341-344): S2 = 60 M msgs/day/unit; throttle "not binding" | S2 = 6 M/day/unit and 120 D2C sends/s/unit; S3 = 300 M/day and 6,000/s | P (azure-docs, iot-hub-scaling ms.date 2025-03-20): size 2 = 6,000,000/day, size 3 = 300,000,000/day. P (quotas-throttling, 2025-05-21): D2C sends "120 send operations/sec/unit" (S2), "6,000 send operations/sec/unit" (S3). Daily-quota meter is 4 KB on paid tiers. | C | None. The derived numbers (18 M/day, 360 msg/s, 7.7×, 4.4×, ~3 h, 24 and 14 units, ~17,000 devices per S3 unit) re-check correctly. |
| F08 | §15.2: group enrollment key embedded in firmware | Microsoft guidance says the group key must not be on devices | P (concepts-symmetric-key-attestation): "Ideally, device keys are derived and installed in the factory. This method guarantees that the group key is never included in any software deployed to the device." P (how-to-legacy-device-symm-key): "A compromised group key has the potential to compromise the security of all devices" | C | None |
| F11 | §8.2: `TIMESTAMP BY device_ts`, late tolerance 5 s, Drop | Replayed or late events are dropped; clock-behind devices are always late | P (stream-analytics-time-handling, 2026-03-24): "for each incoming event, Azure Stream Analytics compares the event time with the arrival time. If the event time is outside the tolerance window, you can configure the system to drop the event". Early events (more than 5 min ahead) are always dropped. | C | Optional: the key says "clock skew"; strictly it is clocks *behind*. Clocks more than 5 min *ahead* are also dropped by the fixed early-arrival rule. |
| F15 (v2) | §10.3 v2: no TTL, no DLQ, strict per-ward FIFO | Unbounded growth until the entity size limit, then sends fail | S/P-snippet (MS Learn): a full queue rejects sends with QuotaExceededException. Max entity size is 1–80 GB by tier. | C | None |
| F06 | FR-8: escalation intervals "mandated by IEC 60601-1-8 clause 6.11" | 6.11 is distributed alarm systems; it does not set staff escalation intervals | S (standards preview / test-house summaries): 6.11 requires communication failure to raise a technical alarm and does not specify escalation timings | C | Make must-mention item 3 ("timings must be sourced from clinical governance") supporting rather than required. It is a remedy, not a detection. |
| F07 | NFR-9: onshore-only "required by Section 26 of the PDPA" | s26 is the Transfer Limitation Obligation, not localisation | S (PDPC advisory guideline ch.19 title; law-firm summaries): s26 permits transfer with comparable protection, and Singapore has no general localisation mandate | C | None |
| §17.1 (distractor in F07) | Part 6A: notify PDPC within 3 calendar days of assessing a breach notifiable | Correct; should not be flagged | S: s26D, no later than 3 calendar days after determining the breach is notifiable | C | None |
| F03 | NFR-4 region RTO 15 min vs single region | Azure has only one region in Singapore | S: Southeast Asia is the only Azure region in Singapore (3 AZs). Other SEA regions are in other countries. | C | None |
| F01 | ADX on Microsoft-managed keys | ADX supports CMK, so this is a key-custody issue | K: ADX supports customer-managed keys. The azure-docs page has moved and I did not fetch it. | C (K) | None |
| F09 | 6-digit postal code plus quasi-identifiers "anonymised" | Re-identification risk, so the data remains personal data | K: matches PDPC anonymisation guidance (not fetched) | C (K) | None |

### 1.3 research_lakehouse

| Flaw | Claim in doc | Claim in key | What the source says (quality) | Verdict | Fix |
|---|---|---|---|---|---|
| F04 | §17.1 (v1 l.609): Deep Archive Access at $0.00099 "with no change in access latency" | Archive and Deep Archive Access are opt-in and need a restore (up to ~12 h); objects < 128 KB are not tiered; monitoring fee $0.0025/1,000 objects | P (older S3 guide mirror): objects < 128 KB "not eligible for automatic tiering ... always charged at the frequent access tier rates". S/P-snippet: Archive and Deep Archive Access are opt-in and "you must initiate a restore request"; Deep Archive Access standard retrieval is within 12 h (bulk 48 h). us-east-1 prices: FA $0.023, IA $0.0125, AIA $0.004, DAA $0.00099, monitoring $0.0025/1,000. | C | Optional: the key's $12,560 re-estimate ignores the Infrequent Access tier ($0.0125) for objects idle 30–90 days. It is therefore a lower bound, and the conclusion (> $10k) only strengthens. |
| F05 | §15: 180M × 1,024 ≈ 184 GB (1 byte/dim), 3 × r7g.8xlarge | float32 = 4 B/dim; faiss HNSW ≈ 1.1 × (4d + 8M) B/vector ≈ 836 GB/copy; circuit breaker 50% of non-heap RAM | P (opensearch docs, knn-methods-engines.md): "The memory required for HNSW is estimated to be `1.1 * (4 * dimension + 8 * m)` bytes/vector"; "Using a replica doubles the total number of vectors". P (settings.md): "if a machine has 100 GB of memory and the JVM uses 32 GB, then the k-NN plugin uses 50% of the remaining 68 GB". | C | Minor: the ≈ 112 GB/node figure assumes a 32 GB heap on Amazon OpenSearch Service (S/K). The conclusion holds under any heap size. |
| F06 | NFR-6 cites SP 800-171 Rev 2 3.1.1 for CMK plus 90-day rotation | 3.1.1 is access control; at-rest is 3.13.16; FIPS is 3.13.11; no 90-day rotation mandate | S: 3.1.1 "Limit system access to authorized users..."; 3.13.11 FIPS-validated cryptography; 3.13.16 "Protect the confidentiality of CUI at rest" | C | None |
| F10 | Single-AZ RDS metastore vs NFR-2 99.9% | RDS Single-AZ SLA is 99.5% | P-snippet (AWS RDS SLA): 99.95% Multi-AZ, "99.5% Instance-Level Uptime Percentage for Single-DB Instances" | C | None |
| F15 (v2) | Bidirectional DMS, last-writer-wins, active-active Polaris | Iceberg needs a single-writer CAS; LWW loses commits | K (Iceberg spec: atomic metadata-pointer swap in one catalog). Design reasoning is sound. | C | None |
| **Sound §16 (Audit plane)** | Audit holds pseudonyms; Object Lock compliance mode for 7 years | Trap: "claiming Object Lock conflicts with consent-withdrawal erasure" is a false positive "because ... audit holds only pseudonyms" | P: compliance mode cannot be shortened or deleted, even by root. K: under GDPR Recital 26, pseudonymised data *is* personal data. NFR-7 itself cites GDPR Art. 17 for EU participants. Retention can be lawful under Art. 17(3), but the design never states which exemption applies. | **W (partial)** | Change why_sound and trap. Count as a false positive only "remove Object Lock" or "audit store must be erasable". Count as neutral or valid a finding that EU participants' pseudonyms in immutable audit logs are still personal data and that the design should document the Art. 17(3) basis (b/d/e). |

### 1.4 blind/item_a

| Defect | Claim in doc | Claim in key | What the source says (quality) | Verdict | Fix |
|---|---|---|---|---|---|
| **D01** | FR-REF-02 / §7.6: refund within 14 days *of passing inspection*; carrier scans ignored | external_fact and credit_requires: the deadline "must be measured from the customer's notification of withdrawal" for CRD **and UK CCR reg. 34** | S/P-snippet (UK CCR 2013 reg. 34(4)–(6)): for a sales contract where "the trader has not offered to collect the goods", the deadline is "the end of 14 days after (a) the day on which the trader receives the goods back, or (b) if earlier, the day on which the consumer supplies evidence of having sent the goods back". Only "otherwise" (34(6)) does it run from being informed of the withdrawal. EU CRD Art. 13(1)/(3): 14 days from being informed, with withholding allowed until receipt or evidence, *unless the trader offered to collect*. The Commission guidance says an offer to collect at the trader's expense removes the withholding right. | **W (partial)**. The defect is real in both regimes, because inspection gating plus a 14-day post-inspection SLA breaches both. But the key states the UK rule wrongly, so a reviewer who correctly cites UK reg. 34(5) ("14 days from receipt or proof of postage") would fail the literal credit_requires. | Rewrite external_fact per regime. **UK:** 34(5) for label/store returns; 34(6) (from notification) where H&R offered home collection (UK and DE offer COLLECTION). **EU:** Art. 13(1) from notification, with withholding under 13(3) except where collection was offered. Change credit_requires to accept "the deadline must be anchored to notification (EU) or to receipt/evidence of dispatch (UK), not to inspection". |
| D02 | §6.4 item 6: outbound delivery never refunded on returns | Standard delivery cost must be refunded on full withdrawal; only the premium may be retained | S/P-snippet: UK reg. 34(2) "must reimburse any payment for delivery ... unless the consumer expressly chose a kind of delivery costing more than the least expensive common and generally acceptable kind"; CRD Art. 13(1)–(2) is the same in substance | C | Cosmetic: the key cites "reg. 34(2)-(3)". The delivery rule is 34(2). |
| D04 | §6.2: a 300 KB order item plus unbounded statusHistory is "within the limit" | 400 KB including attribute names | P: "The maximum item size in DynamoDB is 400 KB, which includes both attribute name binary length ... and attribute value lengths" | C | None |
| D05 | §9.3: DLQ retention 30 days | SQS maximum is 14 days; the DLQ keeps the original enqueue timestamp (standard queues) | P-snippet (CloudFormation/CDK): 60 s – 1,209,600 s (14 days). P (SQS guide mirror): "The expiration of a message is always based on its original enqueue timestamp ... unchanged" | C | Optional: the design's queues are FIFO, and current AWS docs say FIFO DLQ moves reset the timestamp. The key correctly scopes its statement to standard queues. |
| D06 | §5.4: `MessageGroupId = 'order-events'` constant | A single group is processed serially; 300 msg/s per group | P (SQS mirror): "When you receive a message with a message group ID, no more messages for the same message group ID are returned unless you delete the message or it becomes visible"; "Each message group supports 300 requests per second". S/P-snippet: SNS FIFO "Each individual message group can deliver a maximum of 300 messages per second" (high-throughput mode, 2025). | C | None |
| D10 | §6.6 / §8.5: contact data in every event, 10-year compliance-mode Object Lock, excluded from erasure | Compliance mode cannot be deleted or shortened by anyone, including root; Art. 17(3)(b) covers only the data needed for the obligation | P: "can't be overwritten or deleted by any user, including the root user ... retention period can't be shortened". K: GDPR Art. 5(1)(c),(e) and 17(3)(b). | C | None |
| D12 | §6.3: `double precision` money with `round()` to 2 dp | Floats are wrong for money; PG has no `round(double precision, int)` | P (PostgreSQL 16 func.sgml): `round(numeric)`, `round(double precision)`, `round(numeric, integer)` only | C | None |
| Sound list | CRD Art. 9(2)(b), 13(1), 14(1)/(2), 16(c)/(e); CCR reg. 28 | Lawful | K: consistent with the Directive text and the Commission guidance (not fetched) | C (K) | None |

### 1.5 blind/item_b

| Defect | Claim in doc | Claim in key | What the source says (quality) | Verdict | Fix |
|---|---|---|---|---|---|
| DEF-03 | FR-GRID-04: trip within 5 s "consistent with IEEE 1547-2018 clause 8.1" | 1547-2018 requires detect, cease to energize and trip within 2 s | S (EPRI crash course, NRECA guide, utility setting documents via search): "the DER shall detect the island, cease to energize the Area EPS, and trip within 2 s of the formation of an island" | C (S), with a caveat | The standard is paywalled, so I could not rule out a utility-agreement extension provision. The key should cite the sub-clause (8.1.2 in the 2018 text; one secondary source says 8.1.1). Credit should not be denied to a reviewer who says "2 s unless the utility agrees otherwise". |
| DEF-04 | IF-BMS-02: one FC03 read of 200 registers | Maximum 125 registers (0x7D); PDU 253 bytes | S-strong (libmodbus `modbus.h`, citing "Modbus_Application_Protocol_V1_1b.pdf (chapter 6 section 3 page 15) Quantity of Registers to read (2 bytes): 1 to 125 (0x7D)"; `MODBUS_MAX_PDU_LENGTH 253`) | C | None |
| DEF-05 | NFR-SAF-01 / AC-14: "certified to UL 9540A", "UL 9540A certificate" | 9540A is a test method that yields a report; the ESS listing is UL 9540 | S (UL.com "UL 9540A Test Method" pages; Mayfield): 9540A is a test method, UL 9540 is the system listing, and NFPA 855 requires UL 9540 listing | C | None |
| DEF-06 | §6.6: IEEE 2030.5 over HTTP port 80, TLS off | 2030.5-2018 mandates TLS 1.2, `TLS_ECDHE_ECDSA_WITH_AES_128_CCM_8` and device certificates; CSIP requires TLS | S (2030.5-2018 clause 6.7 excerpts; GRIDAPPSD reference server issue #428 citing clause 6.7: the CCM-8 suite "IEEE 2030.5-2018 clause 6.7 requires of all devices") | C | None |
| Sound FR-GRID-05 | Enter-service delay default 300 s | IEEE 1547-2018 default | S: return-to-service delay defaults to 5 min and is adjustable by mutual agreement | C | None |

**pgvector HNSW filtering.** pgvector is not referenced anywhere. The only HNSW use is OpenSearch/faiss in research_lakehouse, so no check was needed.

**Verdict tally.** Across all five items: about 35 facts were checked, 2 key-wrong verdicts (both partial) were found, and there were 0 unverifiable outright. One caveat remains, on the DEF-03 extension clause.

---

## Task 2. Label leakage

**Method.**
- Case-insensitive grep of every design `.md` for: flaw, defect, planted, deliberate, intentional, `note:`, TODO, FIXME, wrong, inconsistent, contradict, regression, answer key, known issue, caveat, mistake, incorrect, bug.
- A search for flaw IDs (`F\d\d`, `DEF-\d+`, `D-\d\d`).
- A 7-gram overlap between each key's evaluative fields (`why_it_is_a_flaw`, `why_it_matters`, `acceptable_recommendation`, `acceptable_fix`) and each document.

| Document | Hits | Assessment |
|---|---|---|
| payments v1 l.729 / v2 l.746 | "MPOP is **deliberately** conventional" (sound §23) | Benign. It is not near a planted flaw. The payments README's own grep list omitted "deliberate". Optionally reword to "conventional by design". |
| clinical v1 l.192 / v2 l.199 | "persistence window ... is **deliberately** part of the clinical definition" (§4.3) | Benign, and it sits in a sound section. It slightly signals that the authors anticipated the F05 debate. Low risk. |
| clinical v1 l.367 / v2 l.376 | "wrong window" in the ASA Drop rationale | Benign. It is a design rationale, though it sits in the F11 row; the wording does not hint at a defect. |
| item_a l.137, 368, 447 | `WRONG_ITEM`, `WRONG_ITEM_SENT` enum values | Benign |
| item_b l.158 | "un**intentional** island" | A false regex hit |
| item_b l.569 | "regression-tested" | Benign |
| clinical, item_b | `D-01..D-20` | These are the documents' own Decision IDs, not flaw IDs. The clinical key reuses them as requirement IDs, which is fine. |
| n-gram overlap | payments v2 F04/F06; clinical v1 F01, v2 F04/F12; lakehouse F14; item_b DEF-02/DEF-06 | All are either the key quoting the document (requirement text or principles) or v2 fix text that legitimately adopts the corrected fact. No key-only evaluative language appears in any document. |

**Verdict:** no leakage. The v2 revision logs (payments l.15-21, clinical l.16-22, lakehouse l.15-23) name sections and do not describe any change as a fix. Clinical's log names "delivery assurance" (the F15 site), which is neutral.

---

## Task 3. v2 integrity (synthetic items)

All three v2 documents were diffed against v1 in full. Every status in `v2_changes` matches the text. Line references below are to v2.

### payments_orchestration (v1.1)

| Flaw | Key status | Evidence in v2 | OK? |
|---|---|---|---|
| F01 | unchanged | l.451 `card_number` still sent to FRV-1; §12.2 unchanged | Yes |
| F02 | fixed | §16.2 incremental matching; NFR-8 moved to 09:00 (l.126); 07:52 and 08:09 SGT arithmetic re-checks | Yes |
| F03 | fixed | NFR-4 l.122 restated (RPO 0 in-region, ≤ 5 s regional) | Yes |
| F04 | regressed → F15 | l.331 states the correct 1,000 WCU, composite PK, no LSI, 6 WCU/request | Yes |
| F15 | new | l.335 §9.4 MREC "regardless of which region receives it"; §24 "both writable" | Present |
| F05 | unchanged | l.726 "<1% cascade" claim unchanged | Yes |
| F06 | fixed | NFR-6 and l.432 cite 3.3.1/3.3.1.2/3.3.2 correctly; 15-min TTL | Yes |
| F07 | unchanged | l.159 Indonesia; no residency NFR; Jakarta replicas are DR only | Yes |
| F08 | fixed | l.583-589 mandatory MFA, two-person rule, 48 h cooling-off | Yes |
| F09 | unchanged | l.308 `idem:resp:{idempotency_key}`; §24 `idem:resp:{key}` | Yes |
| F10 | unchanged | l.384 timeout/5xx still Retryable; l.376 reasoning unchanged | Yes |
| F11 | unchanged | l.428 one HSM | Yes |
| F12 | fixed | FR-8 l.104 pp and scope explicit; AC boundary values | Yes |
| F13 | unchanged | l.810 sequential replay AC | Yes |
| F14 | unchanged | l.789 TRID "not yet submitted"; Phase 3 still "No — ready" | Yes |

Findings:
- (a) `v2_changes` codes F04 as `regressed`, while the README and version_notes count it among the "6 fixed". This is consistent once explained, but a grader tallying `status == fixed` gets 5. Add an explicit `original_fixed: true`.
- (b) The v2 header date "2026-10-12" (l.11) is later than the v1 date and also later than the audit date. Harmless for grading, but it is a realism nit.

### clinical_rpm (v2.0)

| Flaw | Key status | Evidence in v2 | OK? |
|---|---|---|---|
| F01 | unchanged | l.516 ADX "Microsoft-managed keys"; D-8 unchanged | Yes |
| F02 | fixed | l.493 `status = preliminary`; D-14 | Yes |
| F03 | unchanged | D-1 l.801 single region; §18.2 unchanged | Yes |
| F04 | fixed | l.347-353 S3 × 1, correct S2 figures | Yes |
| F05 | unchanged | l.457 budget 5.0 s | Yes |
| F06 | unchanged | FR-8 l.98 still cites IEC 60601-1-8 6.11 | Yes |
| F07 | fixed | NFR-9 l.120 re-sourced to HPHC-ISP-07; s26 described correctly | Yes |
| F08 | fixed | l.652 per-device X.509 in a secure element | Yes |
| F09 | unchanged | l.729 postal code etc. | Yes |
| F10 | regressed → F15 | §10.3 active-active, Redis, Service Bus timers, heartbeat | Yes |
| F15 | new | l.444 no TTL, DLQ disabled, strict FIFO per ward | Present |
| F11 | unchanged | l.375 late tolerance 5 s, Drop | Yes |
| F12 | fixed | FR-7 l.97 defines the key, breakthrough, window and clock | Yes |
| F13 | unchanged | l.871 AC still measures IoT Hub enqueue to DB commit | Yes |
| F14 | unchanged | l.815 D-15 unchanged; Phase 4 "No — ready" | Yes |

Findings: none. The key's note about FR-7 AC (d) exposing F11 is accurate.

### research_lakehouse (v1.1)

| Flaw | Key status | Evidence in v2 | OK? |
|---|---|---|---|
| F01 | unchanged | l.728 generation model serves Restricted; §14.4 unchanged | Yes |
| F02 | unchanged | l.322 Discovery Portal lists embargoed datasets | Yes |
| F03 | fixed | l.288-289, l.446 CoW, tag re-pointing, expire_snapshots, version-id delete in both regions; target 21 days (< 30) | Yes |
| F04 | unchanged | l.641 "no change in access latency" | Yes |
| F05 | fixed | l.576-589 formula, SQfp16 (1.1 × 2,176 ≈ 2,394 B ✓), 112 GB/node, 10 nodes; total cost 78,550 ✓ | Yes |
| F06 | fixed | NFR-6 l.115 re-cited | Yes |
| F07 | unchanged | l.64 scope promise; §12.2 expiry unchanged | Yes |
| F08 | fixed | l.725 and §11 per-user OIDC | Yes |
| F09 | unchanged | l.536 faculty-keyed cache | Yes |
| F10 | regressed → F15 | Aurora Multi-AZ plus 3 Polaris replicas | Yes |
| F15 | new | l.306 bidirectional DMS, LWW, both regions commit | Present |
| F11 | unchanged | l.730 in-place re-embed | Yes |
| F12 | unchanged | FR-6 l.95 | Yes |
| F13 | fixed | NFR-10 AC l.791 | Yes |
| F14 | unchanged | l.743 backlog 1; Phase 5 still "No" | Yes |

Findings: none. Note for graders: in v2 the total run-rate ($78,550) plus the F04 correction (+≈ $5.7k) exceeds the new $80k envelope. That is consistent with F04 staying open, so a reviewer pointing it out is matching F04 and should not be scored as a new false positive.

---

## Task 4. Schema consistency

### 4.1 Field inventory

| Field (canonical) | payments | clinical | lakehouse | item_a | item_b |
|---|---|---|---|---|---|
| item id | `item_id` | `item_id` | `item_id` | `item_id` | `item_id` |
| document(s) | (README only) | (README only) | (README only) | `document` | `document`, `document_id` |
| domain | `domain` | `domain` | `domain` | `domain` | `domain` |
| free-text notes | `version_notes` | `version_notes` | `version_notes` | — | — |
| severity scale | implicit critical/major/minor | implicit | implicit | `severity_scale` {Critical,High,Medium,Low} | `severity_scale` {critical,high,medium,low} |
| category taxonomy | implicit (8 snake_case) | implicit (8; one name differs) | implicit (8) | `category_taxonomy` (11 labels) | free-text per defect |
| counts | `flaw_counts`{total_v1, by_severity, by_category} | `category_counts_v1` only | — | `defect_count` | `defect_count` |
| flaw list | `flaws` | `flaws` (includes v2 F15) | `flaws` | `defects` | `defects` |
| v2 new flaws | `v2_new_flaws` | inside `flaws` with `introduced_in` | `v2_new_flaws` | — | — |
| v2 change map | `v2_changes` | `v2_changes` | `v2_changes` | — | — |
| expected open v2 | `expected_v2_open_flaws` | in version_notes text | — | — | — |
| sound sections | `sound_sections` | `sound_sections` | `sound_sections` | `deliberately_sound_sections` | `deliberately_sound_sections` |
| scoring rule | README | `scoring_guidance` | version_notes / README ("first two must-mention") | README | `scoring_guidance` |
| neutral observations | — | — | — | — | `non_keyed_observations_acceptable_but_not_required` |

Per-flaw fields:

| Canonical | payments / lakehouse | clinical | item_a | item_b |
|---|---|---|---|---|
| `id` | `id` (F01) | `id` | `id` (D01) | `id` (DEF-01) |
| `title` | — | — | `title` | — |
| `category` | `category` | `category` | `category` | `category` |
| `severity` | critical/major/minor | same | Critical/High/Medium/Low | critical/high/medium/low |
| `location.sections` | `section_refs` (list) | `section_refs` | `location.sections` | `location.sections` |
| `location.requirement_ids` | `requirement_ids` | `requirement_ids` | `location.requirement_ids` | `location.requirement_ids` |
| `description` | `description` | `description` | `description` | `description` |
| `rationale` | `why_it_is_a_flaw` | `why_it_is_a_flaw` | `why_it_matters` | `why_it_matters` |
| `external_fact.required` | — | — | `requires_external_fact` | — (implied by non-"None" `external_fact`) |
| `external_fact.statement` | in `distractor_notes` (payments F04/F15) | — | `external_fact` | `external_fact` |
| `credit.items` | `what_a_correct_finding_must_mention` (list) | same | `credit_requires` (**string**) | `credit_requires` (**list**) |
| `credit.mode` | README "by substance" | "core claims" | text | "every item" |
| `acceptable_fix` | `acceptable_recommendation` | same | `acceptable_fix` | `acceptable_fix` |
| `distractor_notes` | `distractor_notes` | same | — | — |
| `introduced_in` / `introduced_by_fix_of` | v2_new_flaws only | `introduced_in` only | — | — |

Sound-section fields: synthetic keys use `section_ref`, `why_sound`, `trap`. item_a uses `location`, `why_sound`, `careless_flag`. item_b uses `section`, `why_sound`, `likely_false_positive`. v2 changes use `flaw_id`, `status` {fixed, unchanged, regressed}, `new_flaw_id`, `note` across all three synthetic keys.

### 4.2 Proposed canonical schema (v1.0)

```json
{
  "schema_version": "1.0",
  "item_id": "...",
  "documents": {"v1": "design_v1.md", "v2": "design_v2.md"} | {"v1": "design.md"},
  "document_id": "optional",
  "domain": "...",
  "notes": "free text (was version_notes)",
  "severity_scale": {"id": "synthetic3" | "blind4", "levels": {"<level>": "<definition or null>"}},
  "category_taxonomy": ["..."],
  "counts": {"total_v1": 14, "by_severity": {}, "by_category": {}},
  "scoring": {"default_credit_mode": "all" | "core_n" | "substance", "core_n": 2, "severity_tolerance": 1, "text": "..."},
  "flaws": [{
    "id": "F01", "title": null, "category": "...", "severity": "...",
    "introduced_in": "v1" | "v2", "introduced_by_fix_of": null,
    "location": {"sections": [], "requirement_ids": []},
    "description": "...", "rationale": "...",
    "external_fact": {"required": true, "statement": "...", "sources": []} | null,
    "credit": {"items": ["..."], "mode": "all" | "core_n" | "substance", "core_n": null, "supporting_items": []},
    "acceptable_fix": "...", "distractor_notes": "..."
  }],
  "sound_sections": [{"location": "...", "why_sound": "...", "false_positive_traps": "...", "overlapping_flaw_ids": []}],
  "v2": {"changes": [{"flaw_id": "F04", "status": "fixed|unchanged|regressed", "original_fixed": true, "new_flaw_id": "F15", "note": "..."}],
         "expected_open_flaws": ["..."]},
  "non_keyed_observations": []
}
```

The conversion is lossless. Severity labels are kept verbatim under a named scale. Mapping across scales is a scoring decision and is not stored in the flaw; the suggested ordinal is synthetic critical ≈ blind critical, major ≈ high, minor ≈ medium/low.

### 4.3 Renames per key

| Key | Required mapping |
|---|---|
| payments | `version_notes`→`notes`; `flaw_counts`→`counts`; `section_refs`→`location.sections`; `requirement_ids`→`location.requirement_ids`; `why_it_is_a_flaw`→`rationale`; `what_a_correct_finding_must_mention`→`credit.items` (mode `substance`); `acceptable_recommendation`→`acceptable_fix`; merge `v2_new_flaws` into `flaws` with `introduced_in:"v2"`; `v2_changes`→`v2.changes` (add `original_fixed:true` for `regressed`); `expected_v2_open_flaws`→`v2.expected_open_flaws`; `sound_sections[].section_ref/trap`→`location/false_positive_traps`; lift the AWS citations in F04/F15 `distractor_notes` into `external_fact.sources`; add `severity_scale: synthetic3` |
| clinical | Same field renames as payments. `category_counts_v1`→`counts.by_category` (compute `by_severity`). Rename category `decision_depends_on_pending_backlog`→`decision_depends_on_pending_item` (or add both to the taxonomy). F15 is already in `flaws`; keep `introduced_in`, normalise "v2", and add `introduced_by_fix_of:"F10"` (missing today). `scoring_guidance`→`scoring.text` (mode `core`). Derive `v2.expected_open_flaws` from version_notes. |
| lakehouse | Same as payments, minus `flaw_counts`/`expected_v2_open_flaws` (compute both). `scoring.default_credit_mode:"core_n"`, `core_n:2` (from README). |
| item_a | `document`→`documents.v1`; `defect_count`→`counts.total_v1`; `defects`→`flaws`; `why_it_matters`→`rationale`; `requires_external_fact`+`external_fact`→`external_fact{required,statement}` (null when false); `credit_requires` (string)→`credit.items:[string]`, mode `all`; `deliberately_sound_sections[].careless_flag`→`false_positive_traps`; keep `title`, `severity_scale` (`blind4`), `category_taxonomy` |
| item_b | As item_a, plus: `document_id` kept; `credit_requires` is already a list (mode `all`); `external_fact:"None"`→`null`; `deliberately_sound_sections[].section/likely_false_positive`→`location/false_positive_traps`; `non_keyed_observations_acceptable_but_not_required`→`non_keyed_observations`; `scoring_guidance`→`scoring.text` (`severity_tolerance:1`) |

Credit rules differ across items: "substance", "core claims", "first two items" and "every item". Benchmark scores will not be comparable across items until `credit.mode` is made explicit per flaw.

---

## Task 5. Realism and difficulty spot-check

### payments_orchestration
- **Critical: F10 (cascade on timeout).** Findable from §11.1–11.2 alone; the "cannot create a duplicate charge" sentence is a strong but fair lure. The must-mention list is fair (three substantive claims, no wording required). It is a genuine flaw.
- **Major: F04 (DynamoDB).** Findable with one external check. The third item ("at least one of") is generous and fair. "Cite AWS docs" is fine as a substance requirement but should not require a literal URL. It is a genuine flaw.
- **Minor: F12 (FR-8 "2%").** Findable. Fair. Genuine, though some reviewers will report it as a testability issue; the must-mention list accommodates that.
- **Others.** F05 is labelled minor, but it is a hard p99 SLO miss and its own AC injects 3.8% retryables; consider major. Nothing is a non-flaw.
- **Realism.** This reads like a competent fintech design doc. The numbers are internally consistent (TPS, row writes, MSK MB/s and ledger journals all re-check), and the decisions table, backlog and readiness sections look authentic. Tells for a senior reviewer: very tidy "Ready" ratings, a few rationales stated more confidently than a real team would ("comfortably within", "cannot create a duplicate charge"), and a structure cloned from another internal template. It would pass as a real document, possibly as a slightly over-polished one.

### clinical_rpm
- **Critical: F04 (IoT Hub quota).** Findable with the public quota table. The five must-mention claims are fair, but requiring all five is strict; graders should treat the "claim that throttle is not binding is false" and "consequence" items as one point.
- **Major: F11 (ASA late arrival).** Findable from §6.1 + §8.2. It requires ASA knowledge, but the doc's own Drop rationale points at it. The four must-mention items are fair except "silent: data still appears in ADX", which should be supporting. Note: on a strict reading of the §6.2 envelope, where samples sit at t=0..4 s from `device_ts`, even normal 5-s batches may exceed the 5-s tolerance. A reviewer saying "most live messages will be dropped" has found F11 and should be credited.
- **Minor: F06 (IEC 60601-1-8 citation).** This needs knowledge of a paywalled standard and is the hardest planted fact to check. Must-mention item 3 is a remedy, not a detection, so make it optional.
- **Is anything not a flaw?** F05 is arguable. IEC 60601-1-8 treats alarm-condition delay separately from alarm-signal generation delay, so whether the 10-s persistence window "counts" against NFR-2 depends on the NFR's start point. The key's recommendation acknowledges this. The batching omission still makes the 50% headroom claim unsupported, so it stays a flaw, but the "≈15 s worst case" framing should not be required.
- **Realism.** This is a very credible public-healthcare RPM design. The pNEWS2 handling, binding model, break-glass and FHIR details are expert-level, and the Singapore governance framing is plausible. Tells: decision IDs neatly mirror every flaw, and the HSA SaMD dependency is so clearly flagged in the backlog that D-15 reads a little staged. It would pass as a real document.

### research_lakehouse
- **Critical: F09 (answer cache).** Findable from §14.5 alone. Fair. Genuine.
- **Major: F05 (vector memory).** Findable from first principles (float32). Must-mention item 2 (the exact OpenSearch formula) and item 3 (circuit breaker) are supporting, and the README's "first two items" rule makes this fair. Keep that rule explicit in the key.
- **Minor: F12 (FR-6 embargo inheritance).** Findable. Fair. Genuine.
- **Is anything not a flaw?** None. F04 is labelled minor while breaching an NFR cap; that is acceptable, since cost is not safety. The sound §16 rationale (see Task 1) is the only legally shaky key statement.
- **Realism.** Strong and current: Polaris, Iceberg v2 WAP with branches, bge-m3, faiss HNSW and OPA in Trino are all real and appropriately used. The cost table sums correctly in both versions. Tells: §23 explicitly mentions "an AI coding assistant" (a template carry-over that a real university team would not write), and the chunk-count arithmetic is suspiciously round. It would pass as real with that one sentence removed.

### blind/item_a
- **Critical: D06 (single MessageGroupId).** Findable. The doc even explains why the constant was chosen. Fair. Genuine.
- **High: D01 (refund anchor).** Findable, but the key's legal statement is wrong for the UK (see Task 1). Fix the credit rule.
- **Low: D14 (AC-05 at 50%).** Findable. Fair.
- **Is anything not a flaw?** D11 is a genuine infeasibility. D13 is genuine. All are real flaws. One non-keyed valid observation is missing from the key: offering home collection (UK and DE) removes the trader's right to withhold under CRD Art. 13(3) / UK reg. 34(6). Add it as neutral.
- **Realism.** This is the most realistic of the five: a multi-market retail OMS with plausible volumes, a correct German 8-year invoice retention and honest trade-offs (DEC-07, DEC-09). A senior engineer would accept it as a genuine ARB pre-read. Minor tell: §6.7 scopes the idempotency key by channel rather than by customer, which a reviewer may flag. It is not keyed, so treat it as neutral.

### blind/item_b
- **Critical: DEF-01 (software E-stop).** Findable, especially by contrast with FACP-B's hardwired path. Fair. Genuine.
- **High: DEF-03 (5 s anti-islanding).** Findable with external knowledge. The 2 s default is confirmed. Add tolerance for "unless utility agrees".
- **Medium: DEF-12 (NTP ±1 ms).** Findable. But credit_requires item 2 *requires recommending GNSS/PTP/IRIG-B*, so a correct detection with a different valid remedy (for example a local PTP-capable grandmaster under a different name, or relaxing the requirement) fails. Make item 2 supporting.
- **Is anything not a flaw?** None. DEF-09 might be argued as "redefine availability", but the key's fix allows that.
- **Realism.** Excellent. Device inventory, protection functions, PRP/RedBox, SunSpec 700-series and warranty EFC arithmetic are all realistic, and the energy and availability arithmetic re-checks. A senior controls or OT engineer would treat it as a real Rev C design. Tells: the defects are almost all "clean" contradictions between two numbered statements, which is slightly denser than in real documents.

---

## Task 6. Sound-section traps

For each sound section, I checked (a) whether any flaw's `section_refs`/`location` cites it and (b) whether the text contains an unplanted defect.

| Item | Sound section | Overlap or issue | Risk | Action |
|---|---|---|---|---|
| payments | §14, §15, §17, §18.5, §23 | No flaw cites these. §23's "24-hour retention" is attributed to the IETF draft but is Stripe practice (minor nit). | Low | Add the §23 nit as a neutral observation |
| clinical | §4 (4.2/4.3) | **F05 `section_refs` includes "4.3"**; F06 concerns IEC usage that also appears in 4.3. Both trap texts disambiguate. | Medium | Add `overlapping_flaw_ids:["F05","F06"]`. Graders must not mark an F05 finding that cites the 4.3 window as a false positive. |
| clinical | §6.2 envelope | F11 cites 6.1, not 6.2. The `device_ts` semantics are ambiguous (example shows `gw_rx_ts` +180 ms, yet sample offsets 0–4 s). | Low | Neutral observation |
| clinical | §14, §16, §19 | §14.5 is mentioned in F08 distractors only; v2 edits §14.5 (adds "revokes its certificate") | Low | None |
| lakehouse | §4 Data Classification | **F01 `section_refs` includes "4"**. The trap text says to attribute F01 to 14.4/20. | Medium | Remove "4" from F01 refs, or add an overlap note |
| lakehouse | **§16 Audit Plane** | **F08 `section_refs` includes "16"** (audit attribution loss), but §16's trap does not mention F08. A correct F08 finding citing §16 may be scored as a false positive. The GDPR rationale is also partially wrong (Task 1). | **High** | Remove "16" from F08 refs or add an overlap note; fix the rationale |
| lakehouse | §14.6 latency | F05's consequence is "NFR-3 retrieval budget collapse". The trap text covers it. | Medium | Overlap note |
| lakehouse | §9 WAP | In v2, F15 breaks the WAP publish guarantee, and the F15 rationale references orphan cleanup (§7.2/§9) | Medium (v2 only) | State that §9 is sound in v1 only, or that F15 findings citing §9 are not false positives |
| lakehouse | §6 Identity | F08 trap handled | Low | None |
| item_a | 3.1.3 FR-RET-01 | D03 `location` includes 3.1.3 and FR-RET-01. The trap text says the defect is 7.4. | Medium | Remove FR-RET-01 from D03 `requirement_ids` or add an overlap note |
| item_a | 3.1.3 FR-RET-03 + 7.4 exclusions | Shares 7.4 with D03 and D09 | Low | None (sub-item scoped) |
| item_a | 3.1.4 FR-REF-01 | D01 cites 3.1.4 (FR-REF-02) | Low | None |
| item_a | 6.4 items 3 and 5; 5.4 notification; 6.2 OCC/6.5; 6.7 | Same sections as D02 (6.4 item 6), D06 (5.4), D04 (6.2) and D07 (whose mechanism relies on the 6.7 stored response) | Low–Medium | Graders must match at sub-item level. Add to scoring guidance. 6.7 is also scoped by channel, not customer (neutral observation). |
| item_a | 8.7 PCI and 7.7 | None | Low | None |
| item_b | 7.5 timeline arithmetic | Section 7.5 step 2 carries DEF-03's 5 s, and DEF-13 cites 7.5. The trap text explains. | Medium | Overlap note |
| item_b | FR-GRID-01 / 7.4 | DEF-14 `requirement_ids` includes FR-GRID-01 | Medium | Remove it from DEF-14 or add an overlap note |
| item_b | 6.3 last paragraphs; 5.2; 5.5/7.9/D-02 | Shared with DEF-04, DEF-08 and DEF-02 respectively. Disambiguated. | Low | None |
| item_b | 6.7/7.10, 8.3, D-05, FR-GRID-05 | None. FR-GRID-05 is verified correct (300 s). | Low | None |

No sound section was found to contain an *unplanted* material defect. The neutral nits are listed above.

---

## Prioritised fix list

### P0: key would penalise a correct reviewer
1. **item_a D01.** Rewrite `external_fact` and `credit_requires` to distinguish the two regimes:
   - UK reg. 34(5): where the trader has not offered collection, refund within 14 days of receipt of the goods or evidence of sending, whichever is earlier.
   - UK reg. 34(6) and CRD Art. 13(1): 14 days from notification. CRD Art. 13(3) allows withholding until receipt or evidence, except where the trader offered collection, which the design does in UK and DE.

   Credit any finding that says the anchor must be notification (EU) or receipt/evidence (UK), not inspection, and that carrier evidence must release the refund.
2. **research_lakehouse sound §16.** Correct `why_sound`: pseudonymised data is personal data under GDPR. Narrow the trap to "Object Lock must be removed / audit must be erasable". Treat "document the Art. 17(3) basis for EU participants' pseudonyms in immutable audit" as valid or neutral.
3. **research_lakehouse F08 vs sound §16.** Remove "16" from F08 `section_refs`, or add explicit guidance that an F08 finding citing audit attribution in §16 is not a false positive.
4. **Remedy-as-requirement credit items.** Downgrade these to supporting:
   - item_b DEF-12 credit item 2 (must recommend GNSS/PTP/IRIG-B).
   - clinical F06 must-mention item 3 (the remedy).
   - clinical F11 item 4 ("silent in ADX").
   - clinical F04: merge the "claim false" and "consequence" items.

   As written, correct detections with alternative remedies fail.
5. **item_b DEF-03.** Cite the exact sub-clause, and add tolerance for "2 s unless otherwise agreed with the utility". This is a low-confidence caveat because IEEE 1547-2018 could not be read in full.

### P1: leakage or v2 mismatch
6. **No leakage found.** Optional tidy-up: reword payments §23 "deliberately conventional" and clinical §4.3 "deliberately part of" to remove any lure. Neither is near a flaw.
7. **v2 status semantics.** In all three synthetic keys, `regressed` entries should carry `original_fixed: true`. As written, a naive tally gives 5 fixed while the READMEs say 6.
8. **clinical F15** lacks `introduced_by_fix_of` (payments and lakehouse have it). Add `"F10"`.
9. **Overlap annotations** (graders may otherwise mark correct findings as false positives): clinical F05/§4.3, lakehouse F01/§4, lakehouse F05/§14.6, lakehouse F15/§9 (v2), item_a D03/FR-RET-01, item_b DEF-03 and DEF-13/§7.5, item_b DEF-14/FR-GRID-01. Add `overlapping_flaw_ids` to each sound entry.

### P2: schema and realism
10. **Adopt the canonical schema in Task 4.2** using the renames in Task 4.3. Above all, make `credit.mode` explicit per flaw, because the current rules are "substance", "core claims", "first two" and "every item".
11. **Normalise categories.** Clinical's `decision_depends_on_pending_backlog` should match the others' `..._pending_item`. Declare the severity scales `synthetic3` and `blind4`, and record cross-scale mapping in scoring, not in the keys.
12. **Add the computed `counts`** to the clinical and lakehouse keys, and add `expected_open_flaws` to clinical and lakehouse.
13. **Consider re-severity of payments F05** (minor → major). It is a hard p99 miss that its own AC would expose.
14. **Add neutral observations so valid unkeyed findings are not penalised:**
    - item_a: the collection offer removes the Art. 13(3) withholding right; §6.7 idempotency is scoped by channel.
    - payments §23: the 24-h attribution belongs to Stripe, not the IETF draft.
    - clinical §6.2: `device_ts` semantics are ambiguous, and batching against the 5-s tolerance may drop live messages.
    - lakehouse v2: the total run-rate breaches $80k once F04 is corrected.
    - lakehouse: Glacier IR 128 KB minimum and initial CRR PUT costs.
    - item_b: retain the existing list.
15. **Realism nits.**
    - Remove "or an AI coding assistant" from lakehouse §23.
    - Payments v2 header date 2026-10-12 should precede the audit or use date.
    - Optionally loosen the "every flaw marked Ready" pattern in readiness tables, which is a mild tell shared by all three synthetic items.
16. **Source re-verification.** Re-verify the four primary-mirror facts against live vendor pages when egress allows. The awsdocs GitHub mirrors are archived (2023), though all four facts are also confirmed by current snippets: DynamoDB limits, the SQS DLQ timestamp, the S3 tiering mechanics and CloudHSM HA guidance.
