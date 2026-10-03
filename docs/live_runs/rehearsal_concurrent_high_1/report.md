# Design review: Serindit Pay — Merchant Payment Orchestration Platform

| | |
|---|---|
| Review | REV-rehearsal_concurrent_high_1 (full review) |
| Under review | DOC-design_v1: Serindit Pay — Merchant Payment Orchestration Platform v1.0, 21 pages |
| Verdict | **not fit** (confidence 0.75, medium) |
| Tools used | none |
| Tools disabled | mcp-internet-search, mcp-research-information, mcp-browser-automation-pw, mcp-document-intelligence |
| Reporting threshold | severity low and above (0 finding(s) in the appendix) |

> No external research was possible or used in this run: every finding rests on the document alone.


## Design intent

MPOP is Serindit Pay's Merchant Payment Orchestration Platform. It accepts merchant payment requests, routes each one to an acquirer, e-wallet provider or bank-transfer rail, and accounts for every resulting movement of money until it is settled to the merchant. It replaces five per-market integration stacks with one merchant API across five Southeast Asian markets (SG, MY, ID, TH, PH). In scope are acceptance, routing, retries, idempotency, vaulting, fraud-scoring integration, ledger, reconciliation, payouts, webhooks and the merchant admin plane, for about 15,000 merchants at a peak of 2,000 TPS. Dispute case management, KYB, 3DS server internals and lending/BNPL are out of scope.

Objectives:
- Replace five per-market integration stacks (no shared routing or ledger, reconciliation by spreadsheet) with one platform and one versioned merchant API across five markets.
- Serve about 15,000 active merchants and 10.5 M attempts per day on average, peaking at 2,000 create-payment TPS (2027 design target).
- P1: One payment, one truth: the payment record and the ledger are the source of truth; provider responses are inputs only.
- P2: Card data stays in the Vault: PAN and SAD leave the Vault boundary only over the Card Adapter's connection to an acquirer; all other services handle tokens.
- P3: Idempotency is scoped to (merchant, key) for every mutating call.
- P4: Money is integers: integer minor units plus an ISO 4217 code; no floating-point amounts.
- P5: The ledger is append-only; corrections are new reversing or adjusting journals.
- P6: Adapters absorb provider differences; the core never branches on provider identity.
- P7: At-least-once delivery with exactly-once effect; consumers deduplicate on a stable identifier.
- P8: Fail closed on security; degrade gracefully on optional enrichment (fraud signals, BIN metadata) to documented defaults.
- P9: Least privilege and separation of duties; money-moving permissions are separated from configuration permissions.
- P10: Everything is auditable: every mutation, routing decision and admin action can be reconstructed.
- FR-8: Prefer the lowest-cost eligible acquirer unless this reduces the expected authorization rate by more than 2%.
- NFR-2: Card authorization p99 at most 1,500 ms end-to-end including cascade, and orchestration overhead at most 250 ms p99.
- NFR-3: Monthly merchant payment API availability of at least 99.95%.
- NFR-4: RPO of zero for authorized payments and ledger postings, including on loss of an AWS region; RTO of 30 minutes.
- NFR-8: Auto-match at least 99.9% of settlement lines and publish T reports by 08:00 SGT on T+1.
- NFR-10: Onboard a new acquirer or provider by adding an adapter and configuration only.

Constraints:
- NFR-5: Must be assessed as a PCI DSS v4.0 Level 1 service provider, with the CDE limited to the components listed in Section 12.2.
- NFR-6: Sensitive authentication data must be handled per PCI DSS v4.0 Req. 3.2.1 and 3.3.2: encrypted, in the Vault only, deleted at settlement.
- NFR-7: Personal data must be processed under SG PDPA 2012, MY PDPA 2010, ID Law 27/2022, TH PDPA 2019 and PH DPA 2012 (purpose limitation, retention limits, access logging).
- FR-7: Card reattempts must never occur where the card scheme's rules prohibit them; at most two additional attempts.
- NFR-12: Audit records must be immutable and kept for five years; payment and attempt records and raw settlement files are kept for 7 years.
- All workloads and primary data stores sit in AWS ap-southeast-1 across three AZs; ap-southeast-3 is used for DR only.
- Principles take precedence: where a later section conflicts with a principle, the principle wins.
- Existing external systems are kept: the Merchant Risk platform owns onboarding/KYB (MPOP consumes an approved-merchant event), and a third-party 3DS server is integrated.
- ACQ-PH1 API v2 retires in Q3 2027, so the adapter must migrate to v3 before then.

Key assumptions:
- The 2027 volume baseline holds: 2,000 peak TPS, 55% card share, and the largest merchant at 45% of peak (about 900 TPS).
- A single DynamoDB partition key (merchant_id) can sustain the largest merchant's about 1,800 WCU at peak, within a per-partition ceiling stated as 10,000 WCU/s.
- Fewer than 1% of card payments cascade, so cascade latency sits above p99 (2025 baseline gives 3.8% retryable outcomes).
- Cascading recovers about 31% of retryable outcomes, based on a three-month ACQ-SG1 to ACQ-SG2 pilot.
- PCI DSS v4.0 Req. 3.2.1 and 3.3.2 permit storing encrypted CVC until settlement (max 72 hours) so it can be re-presented in cascades and incremental authorizations.
- FRV-1 needs the full PAN for its consortium velocity graph, and scoring quality falls materially without it.
- One CloudHSM at launch is enough until sustained card volume exceeds 1,500 TPS, with daily backups allowing recreation in any AZ.
- Aurora capacity is shown by a spike of 2,600 TPS on db.r7g.8xlarge at 58% CPU; Aurora Global Database replication lag is typically under 1 second.
- The latency budget uses the 2025 slowest-acquirer p99 of 1,100 ms and a vendor HSM benchmark of 20 ms.
- The reconciliation matcher takes 45 minutes and report generation 15 minutes at 2025 volume.
- Network tokens are usable from launch, although Token Requestor onboarding is still pending (Backlog item 2).
- The first merchant cohort (Singapore, cards and PayNow) can go live without the Admin API schemas or a dispute module, using the portal and manual Finance Operations handling.

Located at: p.1 §1 (2 passages), p.2 §1.

## Fitness for purpose

**Not fit** (confidence 0.75). As written, the design is not fit to build. The core architecture is sound. FND-058 shows that committing state, ledger and outbox in one transaction, with the ledger append-only, serves FR-10, P1, P5 and P7 and needs no change. FND-014 shows that the requirements, tests and readiness verdicts trace to each other, which made this review possible. The money-handling foundations (P4 integer minor units, P6/NFR-10 adapter isolation) raised no findings. However, the review found 1 critical and 11 high findings, and several of them are internal contradictions or arithmetic that need no outside evidence. (1) FND-001 (critical): the Redis idempotency fast path is keyed without the merchant or the request hash. This breaks P3 and FR-5, and can return one merchant's payment to another, so no payment is created for the second merchant. (2) FND-018: the latency budget leaves out cascades using a 1% figure that contradicts the design's own 3.8% retryable baseline, so NFR-2 is likely to fail its own acceptance test. (3) FND-054: matching cannot start until the last file arrives at 07:30 SGT, so reports finish around 08:30 SGT and NFR-8's 08:00 deadline is missed every day. (4) FND-049: NFR-4's zero RPO cannot hold with asynchronous replication. Idempotency state cannot be rebuilt from the payment table, and one 30-minute failover uses up NFR-3's monthly downtime budget. (5) FND-046: the Fraud Hook detokenises the PAN with the Card Adapter's role, which contradicts P2, P9 and the Section 12.2 CDE scope that NFR-5 is assessed against. (6) FND-048: a single HSM is a single point of failure for all card payments. (7) FND-047: a cascade after a timeout or 5xx can leave a second, orphaned live authorization. (8) FND-052: one user, with MFA optional, can redirect a merchant's payout. (9) FND-022: the state machine is missing transitions other sections depend on. (10) FND-017: go-live comes before fraud scoring, the PCI assessment and the Section 26 acceptance gate. Most of these can be fixed by editing the design text, so this verdict reflects the document as it stands, not the architecture. Limits of this review: it was text-only (DEG-001), so figures and image-rendered tables were not checked. No external research was possible (DEG-002), so the premises behind FND-032 (PCI DSS rules on keeping the CVC) and FND-034 (DynamoDB per-partition and item-collection limits) rest on the reviewer's understanding and are unverified, as are the regulatory questions in FND-043 and FND-057. The verdict does not depend on any of these unverified findings. DEG-003 to DEG-005 note that the recommendations attached to FND-049, FND-047 and FND-029 may reverse approved decisions (idempotency store, cascade policy, routing) without declaring a challenge. FND-048 openly challenges the 'one HSM at launch' decision but has no external evidence behind it. The verdict rests on the risks these findings identify, not on their specific fixes. The fixes need to be checked against the decision registry, and fixing the problem within the approved decisions should come first.

| Objective | Verdict | Findings |
|---|---|---|
| OBJ-1 (one platform, one versioned merchant API across five markets) | fit with conditions | FND-022, FND-030, FND-017, FND-014, FND-058 |
| OBJ-2 (15,000 merchants, 10.5 M attempts/day, 2,000 TPS peak) | fit with conditions | FND-034, FND-018, FND-054 |
| P1 | fit with conditions | FND-047, FND-058 |
| P2 | not fit | FND-046, FND-032 |
| P3 | not fit | FND-001, FND-027 |
| P4 | fit | - |
| P5 | fit | FND-058 |
| P6 | fit | - |
| P7 | fit with conditions | FND-049, FND-027, FND-058 |
| P8 | fit with conditions | FND-055, FND-048 |
| P9 | not fit | FND-052, FND-046 |
| P10 | fit | FND-014 |
| FR-8 | fit with conditions | FND-029 |
| NFR-2 | not fit | FND-018 |
| NFR-3 | not fit | FND-048, FND-049, FND-034 |
| NFR-4 | not fit | FND-049, FND-048 |
| NFR-8 | not fit | FND-054, FND-022 |
| NFR-10 | fit | - |

What would change this verdict: The verdict would move to fit_with_conditions if a revised design did the following: - Keys the Redis fast path by merchant and checks the request hash on every hit (FND-001), and extends the FR-5 test to cover concurrent, cross-merchant and crash cases (FND-027). - Removes PAN detokenisation from the Fraud Hook, or formally brings the Fraud Hook into the CDE with its own role and a signed FRV-1 DPA (FND-046). - Gets a QSA's confirmation, or a citation of the primary PCI DSS text, on whether CVC may be kept after authorization (FND-032). - Gets an accountable owner to decide on NFR-4's zero RPO: either restate the target or add synchronous capture of acknowledged authorizations, and store the idempotency key on the payment so it can be rebuilt after failover (FND-049). - Adds a second HSM in another AZ and a DR path for the Vault, and stops mapping the Vault's 503 to a retryable cascade (FND-048). - Re-sequences go-live after fraud scoring, the PCI assessment and the Section 26 tests (FND-017). - Requires a status query or reversal before a cascade after a timeout or 5xx, and reconciles orphaned approvals (FND-047). - Puts cascades into the latency budget and the acceptance test (FND-018). - Reworks reconciliation so per-provider matching can run incrementally against NFR-8 (FND-054). - Adds step-up authentication, a second approver and owner notification for payout-account changes (FND-052). - Completes the state machine (FND-022). - Confirms DynamoDB capacity with a benchmark or primary AWS documentation (FND-034). The verdict would move further toward not_fit if external evidence confirmed the PCI CVC concern (FND-032), or showed that a market regulator prohibits offshore processing (FND-043).

## Strengths

### FND-058 Atomic state, ledger and outbox commit with an append-only ledger enforced in the database

- **strength** · confidence 0.85 (high) · rank 20
- Disposition: **no change**

Each state transition, its ledger journal and its outbox row are committed in one PostgreSQL transaction. UPDATE and DELETE are revoked on journal and posting, and a nightly recomputation is checked against the asynchronous balance projection, with payouts frozen on any mismatch. This removes dual-write failure modes, survives MSK outages (20.4), and avoids hot-row contention at 2,000 TPS. It directly serves FR-10, P1, P5 and P7.

- Where: p.12 §14.3 (FR-10): "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them,"
- Where: p.16 §19 (FR-10): "journal and posting have UPDATE and DELETE revoked from every application role; the migration role is the only role"
- Where: p.12 §14.3 (FR-10): "The nightly recomputation from postings must equal the projection exactly; any difference pages the on-call"
- Evidence EV-040 (doc, supports): "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them," [doc:DOC-design_v1#p12/s14.3]
- Evidence EV-042 (doc, supports): "journal and posting have UPDATE and DELETE revoked from every application role; the migration role is the only role" [doc:DOC-design_v1#p16/s19]
- Evidence EV-171 (doc, supports): "MSK down Outbox accumulates in Aurora; relay drains on recovery; webhooks delayed, payments unaffected" [doc:DOC-design_v1#p17/s20.4]
- Evidence EV-041 (doc, supports): "A transition and its ledger journal (where one applies) and its outbox event are committed in one" [doc:DOC-design_v1#p7/s7.2]
- Evidence EV-107 (doc, supports): "This invariant is enforced by a deferred constraint trigger at commit and re-verified nightly by a full recomputation." [doc:DOC-design_v1#p11/s14.1]
- Evidence EV-150 (inference, supports): "The 14.2 example journals each balance (10,000 = 9,720 + 280; 9,810 + 190 = 10,000; 9,720 = 9,720), and settlement_cash retains 90, equal to fee revenue 280 less acquirer cost 190." [inference:EV-150] derived from EV-138
- Why no change is needed: The design meets FR-10 and P5 through database-enforced mechanisms rather than convention, and keeps the payment path available when the event bus fails, so no change is justified.
- Decision AD-014 (24 Ledger): preserves. Affirms the approved same-transaction ledger and outbox decision.
- Decision AD-044 (FR-10): preserves. Meets FR-10's balanced double-entry requirement.
- Decision AD-015 (24 Money representation): preserves. Integer minor-unit postings are consistent with the money representation.

### FND-014 Design intent is explicit and traceable

- **strength** · confidence 0.80 (high) · rank 21
- Disposition: **no change**

Every requirement has an ID and is traced to an acceptance criterion in Section 26 and a readiness verdict in Section 27. Ten numbered principles are given precedence, and confirmed decisions and the pending backlog are kept separate. That makes the design reviewable against its own intent. The weakness is that the 'principle wins' rule turns contradictions such as FND-001 and FND-002 into build ambiguity, so those sections still have to be fixed.

- Where: p.2 §2: "Each requirement carries an ID used again in Section 26 (Validation and Acceptance Criteria) and Section 27"
- Where: p.3 §3: "These ten principles govern every design decision in the platform. Where a later section appears to conflict with one of"
- Evidence EV-043 (doc, supports): "Each requirement carries an ID used again in Section 26 (Validation and Acceptance Criteria) and Section 27" [doc:DOC-design_v1#p2/s2]
- Evidence EV-044 (doc, supports): "These ten principles govern every design decision in the platform. Where a later section appears to conflict with one of" [doc:DOC-design_v1#p3/s3]
- Evidence EV-045 (doc, supports): "Items confirmed as in scope but not yet fully designed:" [doc:DOC-design_v1#p19/s25]
- Why no change is needed: Explicit IDs, principles, decisions and backlog give a sound basis for reviewing and verifying the design. The contradictions are handled in their own findings.
- Decision AD-033 (3 Foundational Principles): preserves. Affirms the explicit principle-precedence structure.

## Risks

### FND-001 Redis idempotency fast path keyed without merchant or body hash

- **risk** · internal contradiction · severity **critical** · confidence 0.85 (high) · rank 1
- Disposition: **refinement now** (also: needs testing)

Section 9.2 caches final responses under idem:resp:{idempotency_key} and, on a hit, returns the stored response without going to DynamoDB. The key does not include merchant_id or the request hash, which contradicts P3 and FR-5. Section 9.1 says merchants often use their own order or invoice IDs, so two merchants sending the same key (for example "1001") is likely. When that happens the second merchant gets the first merchant's payment object and no payment is created for it, which can mean data disclosure and goods shipped without payment. A reused key with a different body also gets the cached response instead of HTTP 422.

- Where: p.8 §9.2 (FR-5): "completion of a request, the final response is written to idem:resp:{idempotency_key} with a 24-hour TTL"
- Where: p.4 §3 (P3): "Idempotency is scoped to (merchant, key). Every mutating call is deduplicated on the pair of merchant identity and client-supplied"
- Where: p.7 §9.1 (FR-4): "frequently use their own order or invoice identifiers, which is accepted."
- Evidence EV-001 (doc, supports): "incoming mutating request, the Payments API checks this key first; on a hit, it returns the stored response immediately" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-002 (doc, supports): "Idempotency is scoped to (merchant, key). Every mutating call is deduplicated on the pair of merchant identity and client-supplied" [doc:DOC-design_v1#p4/s3]
- Evidence EV-003 (doc, supports): "frequently use their own order or invoice identifiers, which is accepted." [doc:DOC-design_v1#p7/s9.1]
- Evidence EV-046 (inference, supports): "A cache key made of the client key alone, with no hash check, will collide across merchants that use sequential order IDs and will return another merchant's stored response, and it also skips the 422 body-mismatch check that FR-5 requires." [inference:EV-046] derived from EV-001, EV-002, EV-003
- Evidence EV-059 (doc, supports): "on a hit, it returns the stored response immediately without touching DynamoDB or the Orchestrator" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-172 (inference, supports): "With 15,000 merchants using order numbers such as sequential invoice IDs as keys, collisions on a merchant-agnostic Redis key are likely in normal use. Each one returns another merchant's response and suppresses a payment, and a reused key with a changed body gets the stale response instead of HTTP 422." [inference:EV-172] derived from EV-151, EV-001, EV-003
- Recommendation: In Section 9.2 and in the Section 24 idempotency row, change the Redis key to idem:resp:{merchant_id}:{idempotency_key}. Store request_hash with the cached response and compare it on every hit, returning 422 on mismatch. Add tests to Section 26 FR-5: two merchants using the same key get independent payments, and a same-key request with a different body is rejected on the fast path.
  - Issue: The fast-path cache key leaves out merchant identity and the request hash.
  - Rationale: P3 and FR-5 scope deduplication to (merchant, key) and require a 422 on body mismatch. The fast path as written breaks both before the durable path is ever reached.
  - Expected benefit: FR-5 holds on the fast path too, and responses cannot leak between merchants. (objectives: FR-5, P3, NFR-7)
  - Supporting evidence: EV-001, EV-002, EV-003, EV-046
  - Verification: Extended FR-5 replay test: cross-merchant same-key test and fast-path body-mismatch test both pass.
- Next step: Payments Core tech lead: Amend the Section 9.2 key schema and add the cross-merchant and mismatch cases to the FR-5 test plan.
- Decision AD-006 (24 Idempotency store): refines. Keeps the approved Redis plus DynamoDB two-tier store and only scopes the Redis key by merchant and adds a hash check.
- Decision AD-040 (FR-5): preserves. The change restores FR-5's (merchant, key) dedup and 422 rule on the fast path.
- Decision AD-033 (3 Foundational Principles): preserves. Brings the fast path into line with principle P3, which takes precedence.
- Decision AD-007 (24 Idempotency retention): preserves. The 24-hour retention is unchanged.

### FND-046 Fraud Hook detokenises PAN with the Card Adapter's role and sends it to FRV-1, outside the declared CDE

- **risk** · security privacy gap · severity **high** · confidence 0.85 (high) · rank 2
- Disposition: **governance decision** (also: refinement now)

Section 13.1 has the Fraud Hook obtain the full PAN through detokenise, using the Card Adapter's client library and service role, and send it to FRV-1. This contradicts P2, the rule in 12.1 that only the Card Adapter may detokenise, and the 12.2 scope table, which lists the Fraud Hook as handling tokens, BIN and last 4 only. It also explains why Section 5 exposes detokenise across the segmentation boundary to the core VPC. As written, the Fraud Hook, the Orchestrator path that calls it, and the core VPC fall into CDE scope, so NFR-5 cannot be assessed against Section 12.2. Sharing a service role also breaks P9. PAN goes to a third party whose data processing agreement is still pending (Backlog 4).

- Where: p.11 §13.1 (NFR-5): "detokenise operation, using the Card Adapter client library and service role."
- Where: p.10 §12.1 (P2): "Only the Card Adapter's service identity may call detokenise."
- Where: p.10 §12.2 (NFR-5): "Fraud Hook Out of scope Token, BIN, last 4 only"
- Evidence EV-152 (doc, supports): "FRV-1's consortium velocity graph is keyed on the full card number, which allows it to link the same card across its" [doc:DOC-design_v1#p11/s13.1]
- Evidence EV-153 (doc, supports): "detokenise operation, using the Card Adapter client library and service role." [doc:DOC-design_v1#p11/s13.1]
- Evidence EV-006 (doc, supports): "Only the Card Adapter's service identity may call detokenise." [doc:DOC-design_v1#p10/s12.1]
- Evidence EV-005 (doc, supports): "Fraud Hook Out of scope Token, BIN, last 4 only" [doc:DOC-design_v1#p10/s12.2]
- Evidence EV-154 (doc, supports): "Card data stays in the Vault. Primary account numbers (PAN) and sensitive authentication data never leave the Vault boundary" [doc:DOC-design_v1#p3/s3]
- Evidence EV-155 (doc, supports): "exposing the Vault's tokenise, detokenise-for-adapter and card-metadata operations." [doc:DOC-design_v1#p5/s5]
- Evidence EV-127 (doc, supports): "FRV-1 contract - data processing agreement and SLA finalisation." [doc:DOC-design_v1#p19/s25]
- Evidence EV-173 (inference, supports): "A component outside the CDE that receives plaintext PAN, and a detokenise operation reachable from the core VPC, together mean the CDE boundary in 12.2 does not match the data flow, so the Report on Compliance in the NFR-5 test cannot pass against that scope." [inference:EV-173] derived from EV-153, EV-005, EV-155
- Evidence EV-062 (doc, supports): "The Fraud Hook obtains the PAN through the Vault's detokenise operation, using the Card Adapter client library and service role." [doc:DOC-design_v1#p11/s13.1]
- Evidence EV-109 (inference, supports): "A component that receives the PAN and sends it to a third party cannot be both outside the CDE and compliant with P2. Either Section 13.1 changes or Section 12.2 and NFR-5 must bring the Fraud Hook, its role, and the FRV-1 link into scope." [inference:EV-109] derived from EV-062, EV-006, EV-005, EV-063
- Recommendation: Decide one of two options. (a) Remove card_number from the 13.1 payload and send FRV-1 the keyed PAN fingerprint or another vendor-accepted surrogate. (b) Move the FRV-1 call that needs PAN into a CDE-resident relay with its own service identity, add it and FRV-1 (as a third-party service provider) to 12.2, and make PCI responsibilities part of the Backlog 4 contract. In both cases, remove detokenise from the core-VPC private endpoint in Section 5.
  - Issue: PAN flows to an out-of-scope service and to a third party, using a borrowed CDE service identity.
  - Rationale: P2, P9, 12.1 and 12.2 all forbid this. Left unresolved, it either fails NFR-5 or silently widens PCI scope to most of the platform.
  - Expected benefit: Keeps the CDE limited to the four components in 12.2 (NFR-5) and restores least privilege (P9). (objectives: NFR-5, P2, P9)
  - Supporting evidence: EV-152, EV-153, EV-006, EV-005, EV-154, EV-155, EV-127, EV-173
  - Verification: The segmentation penetration test shows detokenise cannot be called from any core-VPC identity, and the QSA scoping memo confirms the CDE boundary before Phase 2.
- Next step: PCI compliance lead with the Payments Core architect and the Head of Risk: Choose option (a) or (b) and agree the CDE scope with the QSA before Phase 2 (CDE build) and Phase 8 (Fraud Hook) start.
- Decision AD-029 (NFR-5): preserves. The fix keeps the CDE limited to the Section 12.2 components, or formally extends it, as NFR-5 requires.
- Decision AD-013 (24 Fraud): refines. FRV-1 synchronous scoring is kept, but the payload changes or the call moves into the CDE.
- Decision AD-023 (25 item 4): refines. The FRV-1 contract must cover PCI responsibilities if the PAN is still sent.
- Decision AD-033 (3 Foundational Principles): preserves. Restores principles P2 and P9, which take precedence.
- Decision AD-043 (FR-9): preserves. FR-9 scoring is still met under either option.

### FND-032 CVC retention until settlement relies on an unverified reading of PCI DSS

- **risk** · unsupported or incorrect claim · severity **high** · confidence 0.70 (medium) · rank 3
- Disposition: **needs investigation** (also: refinement now)

Section 12.4, NFR-6 and the confirmed CVC decision store the CVC, encrypted, until settlement or for up to 72 hours. The basis given is that PCI DSS v4.0 Requirements 3.2.1 and 3.3.2 allow sensitive authentication data to be kept until the transaction settles. As the reviewer understands PCI DSS, card verification codes may not be kept once authorization is complete, even in encrypted form. The incremental-authorization use case needs the CVC after the first authorization has completed, so the design keeps it past authorization by construction. If the cited reading is wrong, the CDE cannot pass the Level 1 assessment required by NFR-5. The document also cites v4.0, and whether that is the version that will be in force at assessment has not been checked.

- Where: p.10 §12.4 (NFR-6): "3.2.1 and 3.3.2, which allow sensitive authentication data to be retained in encrypted form until the transaction is settled."
- Where: p.3 §2.2 (NFR-6): "Sensitive authentication data shall be handled per PCI DSS v4.0 Requirements 3.2.1 and 3.3.2: stored only in encrypted form, in the"
- Where: p.18 §24: "CVC handling Encrypted in Vault until settlement, max 72 hours"
- Evidence EV-125 (doc, supports): "therefore stores the CVC encrypted under a separate KEK, and deletes it when the Reconciliation Service marks the" [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-021 (doc, supports): "3.2.1 and 3.3.2, which allow sensitive authentication data to be retained in encrypted form until the transaction is settled." [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-126 (doc, supports): "the credential during a cascade and for incremental authorizations (ride-hailing tips, hotel extensions). The Vault" [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-139 (inference, supports): "An incremental authorization happens after the initial authorization has completed, so the design keeps the CVC past authorization by intent. Whether the cited requirements permit this is the open question, and the document's own text does not settle it." [inference:EV-139] derived from EV-125, EV-021, EV-126
- Evidence EV-023 (doc, supports): "CVC handling Encrypted in Vault until settlement, max 72 hours" [doc:DOC-design_v1#p18/s24]
- Evidence EV-087 (doc, supports): "deletes it when the Reconciliation Service marks the associated payment SETTLED, or after 72 hours, whichever is first." [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-118 (inference, supports): "NFR-6 and Section 12.4 give different deletion triggers, the 72-hour limit makes later incremental authorisations impossible, and the claimed PCI permission is not checked in the document. The CVC design and NFR-5 depend on an unverified premise." [inference:EV-118] derived from EV-086, EV-087, EV-088, EV-089
- Evidence EV-179 (inference, supports): "Cascades finish within one authorization request (about 7.5 s at most), so only incremental authorizations need CVC after the customer session, and these are exactly the cases where the reviewer doubts post-authorization storage is allowed." [inference:EV-179] derived from EV-161, EV-022
- Recommendation: Get a written QSA interpretation of 12.4 against the PCI DSS version that will be in force at assessment. If retention after authorization is not allowed: (1) limit CVC use to the synchronous initial authorization request, including any cascade within that request, and delete the CVC when the request completes; (2) perform incremental authorizations by referencing the original authorization, without the CVC; (3) rewrite 12.4, NFR-6, the Section 24 CVC decision and the NFR-6 test to say 'absent upon completion of authorization'.
  - Issue: CVC retention after authorization rests on an unverified interpretation of PCI DSS Requirements 3.2.1 and 3.3.2.
  - Rationale: A wrong interpretation puts the whole CDE design and the Level 1 assessment at risk. Settling it now is cheaper than redesigning after a QSA rejects it.
  - Expected benefit: Makes NFR-5 (Level 1 service provider assessment) and NFR-6 achievable. (objectives: NFR-5, NFR-6)
  - Supporting evidence: EV-125, EV-021, EV-126, EV-139
  - Verification: QSA written opinion filed with the PCI DSS Scoping Memo. The revised NFR-6 test shows no CVC in the Vault after the authorization response is returned.
- Next step: PCI DSS compliance lead with the QSA: Get a written interpretation of the CVC retention model in 12.4, including the cascade and incremental-authorization cases, before Phase 2 (CDE) build starts.
- Decision AD-009 (24 CVC handling): refines. The CVC retention decision may need a shorter deletion trigger, but the PCI premise is unverified, so this is not yet a challenge.
- Decision AD-030 (NFR-6): refines. The NFR-6 deletion trigger may need restating to match the QSA's interpretation.
- Decision AD-029 (NFR-5): preserves. The aim is to keep the Level 1 assessment achievable.
- Decision AD-011 (24 Cascade policy): preserves. Cascades inside one request can still re-present the CVC under the proposed fallback.

### FND-049 Zero RPO on region loss cannot hold with async replication, and idempotency state cannot be rebuilt

- **risk** · scalability or failure mode · severity **high** · confidence 0.80 (high) · rank 4
- Disposition: **governance decision** (also: refinement now, needs testing)

NFR-4 requires an RPO of zero for authorizations and ledger postings on loss of a region, but 20.2 relies on asynchronous Aurora Global Database replication with lag under one second. Authorizations acknowledged in that last second exist at the acquirer but not in the promoted database. Section 20.2 also says idempotency state is 'reconstructed from the payment table', but the payment table in Section 19 stores no idempotency key or request hash. After failover, merchant retries therefore create new payments and new authorizations, breaking FR-5. In addition, one 30-minute failover uses more than NFR-3's monthly downtime budget of about 22 minutes.

- Where: p.3 §2.2 (NFR-4): "Recovery point objective for authorized payments and ledger postings shall be zero, including on loss of an entire AWS region."
- Where: p.16 §20.2 (NFR-4): "Replication is storagelevel and asynchronous, with typical lag under one second."
- Where: p.17 §20.2 (FR-5): "empty in ap-southeast-3 from infrastructure-as-code, and in-flight idempotency state is reconstructed from the"
- Evidence EV-008 (doc, supports): "Recovery point objective for authorized payments and ledger postings shall be zero, including on loss of an entire AWS region." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-068 (doc, supports): "Replication is storagelevel and asynchronous, with typical lag under one second." [doc:DOC-design_v1#p16/s20.2]
- Evidence EV-157 (doc, supports): "empty in ap-southeast-3 from infrastructure-as-code, and in-flight idempotency state is reconstructed from the" [doc:DOC-design_v1#p17/s20.2]
- Evidence EV-158 (doc, supports): "EKS cluster, switch Route 53 records), rehearsed twice a year. Target duration: 30 minutes." [doc:DOC-design_v1#p17/s20.2]
- Evidence EV-176 (inference, supports): "Asynchronous replication with non-zero lag cannot guarantee zero RPO. The Section 19 payment table has no idempotency_key column, so idempotency records cannot be rebuilt from it. At 2,000 TPS, one second of lag is up to about 2,000 payments." [inference:EV-176] derived from EV-008, EV-068, EV-157
- Evidence EV-177 (inference, supports): "99.95% monthly availability allows about 21.9 minutes of downtime in a 30-day month, less than the 30-minute failover target." [inference:EV-177] derived from EV-158
- Evidence EV-070 (doc, supports): "Unplanned failover of the Aurora Global Database to ap-southeast-3" [doc:DOC-design_v1#p20/s26.2]
- Evidence EV-027 (doc, supports): "Monthly availability of the merchant payment API shall be at least 99.95%." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-144 (inference, supports): "With asynchronous replication and sub-second typical lag, an unplanned regional loss at 2,000 TPS can drop up to roughly one second's commits (on the order of 2,000 payments), so RPO is bounded by the lag, not zero." [inference:EV-144] derived from EV-008, EV-068
- Recommendation: The accountable owner chooses either (a) restating NFR-4 as a bounded RPO (for example ≤ 1 s for the database) plus mandatory post-failover recovery of in-flight authorizations from acquirer reports and reversal or recording of orphans, or (b) a synchronous cross-region commit design and its latency cost. Separately, add idempotency_key and request_hash columns to payment, with a unique constraint on (merchant_account_id, idempotency_key), so the 20.2 rebuild is possible. Document regional failover as excluded from, or in conflict with, NFR-3.
  - Issue: NFR-4 is unachievable with the chosen replication, and the idempotency rebuild depends on data that is not stored.
  - Rationale: Leaving an unachievable RPO in place means the NFR-4 game day passes only if replication lag happens to be near zero, while real failovers can lose authorizations and produce duplicate charges.
  - Expected benefit: An honest, testable DR objective (NFR-4), FR-5 that holds across failover, and an NFR-3 budget consistent with the DR plan. (objectives: NFR-4, NFR-3, FR-5)
  - Supporting evidence: EV-008, EV-068, EV-157, EV-158, EV-176, EV-177
  - Verification: Run the NFR-4 game day under NFR-1 load and compare acquirer-simulator authorizations with the promoted ledger. Replay merchant retries with the same keys after failover and check that no second authorization is made.
- Next step: Head of Platform Engineering with the Finance risk owner: Decide the RPO restatement or the synchronous design, and approve the payment schema change before Phase 3.
- Decision AD-055 (NFR-4): challenges. Explicit challenge: the document states both zero regional RPO (EV-008) and asynchronous replication (EV-068), and the game day (EV-070) cannot reliably pass, so either NFR-4 or the mechanism must change.
- Decision AD-004 (24 Disaster recovery): refines. Aurora Global DR is kept under option (a); option (b) adds a synchronous commit path.
- Decision AD-054 (NFR-3): refines. How a regional failover counts against the NFR-3 budget must be stated.
- Decision AD-040 (FR-5): preserves. Adding idempotency columns keeps FR-5 holding across failover.
- Decision AD-035 (19.1 Data placement): preserves. Data placement and DR-only use of ap-southeast-3 are unchanged.

### FND-048 Single CloudHSM in one AZ is a single point of failure for all card payments, and the Vault has no DR region

- **risk** · scalability or failure mode · severity **high** · confidence 0.75 (medium) · rank 5
- Disposition: **refinement now** (also: needs prototyping)

The KEKs sit on one HSM in ap-southeast-1a. Section 12.1 does not cache DEKs, so every tokenise and detokenise needs the HSM: losing that HSM or that AZ stops all card acceptance (about 55% of attempts) until a new HSM is built from the daily backup. This undercuts the three-AZ posture in 20.1 and NFR-3. Section 12.3 maps the Vault's 503 to a retryable outcome, so each payment cascades up to three times against the same failed Vault, multiplying load when the HSM is degraded. Section 20.2 does not cover the CDE, Vault data or HSM in ap-southeast-3, so a regional failover cannot restore card payments within the NFR-4 target of 30 minutes. This challenges the confirmed decision 'one HSM at launch'.

- Where: p.10 §12.3 (NFR-3): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a."
- Where: p.10 §12.3 (NFR-3): "cluster when sustained card volume exceeds 1,500 TPS. If the HSM is unreachable, the Vault returns HTTP 503 and"
- Where: p.16 §20.2 (NFR-4): "Aurora Global Database replicates the payments and ledger cluster to ap-southeast-3."
- Evidence EV-024 (doc, supports): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a." [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-026 (doc, supports): "inside the HSM; DEKs are not cached, so plaintext key material never persists in application memory." [doc:DOC-design_v1#p10/s12.1]
- Evidence EV-025 (doc, supports): "cluster when sustained card volume exceeds 1,500 TPS. If the HSM is unreachable, the Vault returns HTTP 503 and" [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-082 (doc, supports): "Every service runs at least three replicas spread across three AZs." [doc:DOC-design_v1#p16/s20.1]
- Evidence EV-156 (doc, supports): "Aurora Global Database replicates the payments and ledger cluster to ap-southeast-3." [doc:DOC-design_v1#p16/s20.2]
- Evidence EV-175 (inference, supports): "At the design peak, 55% of 2,000 TPS is about 1,100 card TPS, and each payment needs several HSM operations (tokenise wrap, HMAC fingerprint, CVC wrap, one unwrap per attempt). One HSM therefore carries several thousand operations per second with no redundancy, and the 1,500 TPS trigger for a second HSM is never reached at the 2027 target." [inference:EV-175] derived from EV-024, EV-026, EV-025
- Evidence EV-081 (doc, supports): "A second HSM will be added to the cluster when sustained card volume exceeds 1,500 TPS." [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-083 (doc, supports): "Card share of attempts (e-wallet ~30%, bank transfer ~15%) 54% 55%" [doc:DOC-design_v1#p2/s1]
- Evidence EV-084 (doc, supports): "If the HSM is unreachable, the Vault returns HTTP 503 and the Card Adapter maps this to a retryable outcome." [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-027 (doc, supports): "Monthly availability of the merchant payment API shall be at least 99.95%." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-116 (inference, supports): "55% of 2,000 TPS is 1,100 card TPS, below the 1,500 TPS trigger, so there is one HSM through 2027. Losing it fails every card authorisation, cascades included, for the whole restore time, which conflicts with Section 20.1 and NFR-3." [inference:EV-116] derived from EV-024, EV-081, EV-082, EV-083, EV-084
- Recommendation: In 12.3, provision at least two HSMs in different AZs from launch, and update the Section 24 decision. Classify Vault 503 as a non-cascading platform error with fast failure, rather than retryable. Add to 20.2 a standby CDE in ap-southeast-3: a CloudHSM cluster restored from a cross-region backup copy, replicated Vault storage, and Card Adapter steps in the failover runbook. Benchmark HSM operations per second for the 2,000 TPS card mix.
  - Issue: Card acceptance depends on one HSM in one AZ, has no cross-region path, and a Vault outage triggers cascades that add load.
  - Rationale: NFR-3 allows about 22 minutes of downtime a month. An AZ or HSM loss with backup-based recovery, or a regional failover without a CDE, exceeds that and NFR-4's 30-minute RTO.
  - Expected benefit: Card acceptance survives the loss of one AZ (NFR-3) and the loss of the region (NFR-4), and HSM capacity is confirmed for NFR-1. (objectives: NFR-1, NFR-3, NFR-4)
  - Supporting evidence: EV-024, EV-026, EV-025, EV-082, EV-156, EV-175
  - Verification: A chaos test that terminates the AZ-a HSM during NFR-1 load must keep card success within the SLO. The NFR-4 game day must include card authorizations in ap-southeast-3. The HSM benchmark must show at least 2× headroom at the peak operation rate.
- Next step: Vault/CDE tech lead: Prototype a two-HSM cluster and run the operations-per-second benchmark and the cross-region backup-restore drill before Phase 2 exits.
- Decision AD-008 (24 Vault): challenges. Explicit challenge to 'one HSM at launch': the document shows one HSM in one AZ (EV-024), a scale-out trigger above the 2027 card peak (EV-081, EV-083), and a three-AZ posture and 99.95% target (EV-082, EV-027) that it cannot meet; the HSM restore time remains unverified.
- Decision AD-028 (12.3 HSM topology): refines. Replaces the card-TPS trigger with a measured HSM-operations trigger.
- Decision AD-004 (24 Disaster recovery): refines. Adds CDE components to the regional DR runbook.
- Decision AD-002 (24 Compute): preserves. The separate-account CDE is kept.
- Decision AD-054 (NFR-3): preserves. The aim is to make NFR-3 achievable for cards.

### FND-017 Go-live comes before fraud scoring, PCI assessment and load/DR validation

- **risk** · internal contradiction · severity **high** · confidence 0.80 (high) · rank 6
- Disposition: **governance decision** (also: refinement now)

Section 28 puts the first cohort (Singapore cards and PayNow) live after Phase 7. The Fraud Hook is Phase 8, and Phase 9 holds the PCI DSS assessment, load, chaos and DR game days, and the Section 26 test plan. As written, real card payments would be taken without the fraud scoring that FR-9 requires, before the NFR-5 assessment, and before any of the Section 26 acceptance criteria have been run. That contradicts Section 26's role as the acceptance gate, and the readiness conclusion in Section 27.

- Where: p.21 §28 (FR-9, NFR-5): "The first merchant cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week intervals."
- Where: p.21 §28: "Hardening - load, chaos and DR game days; PCI DSS assessment; Section 26 test plan"
- Where: p.3 §2.1 (FR-9): "Every card payment and every e-wallet payment above the merchant's configured threshold shall be scored by the fraud-scoring hook"
- Evidence EV-064 (doc, supports): "The first merchant cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week intervals." [doc:DOC-design_v1#p21/s28]
- Evidence EV-019 (doc, supports): "8 Fraud Hook (FRV-1) Yes - vendor contract (Backlog item 4)" [doc:DOC-design_v1#p21/s28]
- Evidence EV-065 (doc, supports): "Hardening - load, chaos and DR game days; PCI DSS assessment; Section 26 test plan" [doc:DOC-design_v1#p21/s28]
- Evidence EV-020 (doc, supports): "Every card payment and every e-wallet payment above the merchant's configured threshold shall be scored by the fraud-scoring hook" [doc:DOC-design_v1#p3/s2.1]
- Evidence EV-110 (inference, supports): "Going live after Phase 7 means Phases 8 and 9 (fraud hook, PCI assessment, Section 26 validation) are not done when real card traffic starts. FR-9 and NFR-5 are therefore unmet at launch, and the acceptance criteria do not act as a release gate." [inference:EV-110] derived from EV-064, EV-019, EV-065, EV-020
- Evidence EV-142 (inference, supports): "Because Phases 8 and 9 follow the go-live gate after Phase 7, the cohort would run live card traffic with no fraud scoring (FR-9), no completed PCI DSS assessment (NFR-5) and no executed Section 26 test plan." [inference:EV-142] derived from EV-129, EV-065
- Evidence EV-051 (inference, supports): "Go-live after Phase 7 comes before the Phase 8 Fraud Hook, so the first cohort's card payments go unscored, contrary to FR-9 and the Section 27 conclusion." [inference:EV-051] derived from EV-018, EV-019, EV-020
- Recommendation: In Section 28, make go-live depend on completing Phase 8 (Fraud Hook, which needs Backlog item 4 closed) and the Phase 9 items needed for the cohort: PCI DSS ROC, NFR-1/2 load test and NFR-4 game day. If an earlier launch is still wanted, record an explicit risk-acceptance decision with interim controls, such as acquirer-side fraud screening and lower limits.
  - Issue: The Section 28 order puts live card processing ahead of fraud scoring, the PCI assessment and the acceptance tests.
  - Rationale: FR-9, NFR-5 and the Section 26 criteria have to be met before real payments are accepted.
  - Expected benefit: Launch meets FR-9 and NFR-5, and fraud loss and compliance exposure at go-live are bounded. (objectives: FR-9, NFR-5, NFR-1, NFR-4)
  - Supporting evidence: EV-064, EV-019, EV-065, EV-020, EV-110
  - Verification: Release checklist ties go-live to signed-off Section 26 criteria for FR-9, NFR-5, NFR-1, NFR-2 and NFR-4.
- Next step: Head of Payments Engineering with Risk and Compliance leads: Decide the go-live gate and record any interim risk acceptance in Section 28.
- Decision AD-037 (28 Build Phases): challenges. Explicit challenge: the document's own phase table (EV-064, EV-019, EV-065) shows that going live after Phase 7 leaves FR-9 and NFR-5 unmet, so the go-live gate must move or be covered by a formal risk acceptance.
- Decision AD-043 (FR-9): preserves. Aims to have FR-9 scoring in place at launch.
- Decision AD-029 (NFR-5): preserves. Aims to have the NFR-5 assessment complete before card traffic.
- Decision AD-023 (25 item 4): preserves. Records that go-live depends on closing the pending FRV-1 contract.

### FND-047 Cascading after a timeout or 5xx can leave duplicate live authorizations; late approvals are discarded

- **risk** · scalability or failure mode · severity **high** · confidence 0.75 (medium) · rank 7
- Disposition: **refinement now** (also: needs testing)

Sections 11.1 and 11.2 cascade immediately on a 2,500 ms timeout or an HTTP 5xx, and discard any response that arrives after the timeout. In both cases the first acquirer may already have approved. A second approval then puts two holds on the cardholder's funds, and the first is never reversed because the ledger and state machine know only the approved attempt. The claim that cascading 'cannot create a duplicate charge' holds only for definite failures such as connection refused. The sweeper in 20.3 handles payments stuck in AUTHORISING, not orphaned approvals on attempts that were superseded.

- Where: p.9 §11.2 (FR-7): "arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded."
- Where: p.9 §11.2 (FR-7): "succeed, cascading cannot create a duplicate charge: the ledger records only the approved attempt."
- Where: p.9 §11.1 (FR-7): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms"
- Evidence EV-133 (doc, supports): "arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded." [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-132 (doc, supports): "succeed, cascading cannot create a duplicate charge: the ledger records only the approved attempt." [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-013 (doc, supports): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms" [doc:DOC-design_v1#p9/s11.1]
- Evidence EV-174 (inference, supports): "A timeout or 5xx is an ambiguous outcome. If the first acquirer approved, cascading produces a second approval while the first hold stays live and unrecorded, which ties up cardholder funds and leaves an attempt that cannot be reconciled." [inference:EV-174] derived from EV-133, EV-132, EV-013
- Evidence EV-075 (doc, supports): "Requests carrying the same merchant and Idempotency-Key shall produce at most one authorization, capture, void or refund at the" [doc:DOC-design_v1#p2/s2.1]
- Evidence EV-146 (inference, supports): "A timeout means the attempt's outcome is unknown, not failed, so a late approval that is discarded leaves a live authorization at the first acquirer alongside the approved cascade attempt." [inference:EV-146] derived from EV-132, EV-133
- Evidence EV-114 (inference, supports): "A timeout does not mean the issuer declined. Discarding a late approval while a cascade succeeds elsewhere leaves a second live authorisation for the same payment with no void, which contradicts FR-5 and P1." [inference:EV-114] derived from EV-073, EV-074, EV-075
- Recommendation: In 11.1, split Retryable into 'definite' (connection refused, explicit soft decline) and 'ambiguous' (timeout, 5xx). Before cascading an ambiguous attempt, the adapter sends an authorization reversal or a status inquiry for it. In 11.2, replace 'logged and discarded' with: a late approval on a superseded attempt triggers an automatic reversal and an audit event, and is tracked until confirmed. Correct the 'cannot create a duplicate charge' sentence.
  - Issue: Ambiguous outcomes (timeout, 5xx) are cascaded as if they were definite failures, and late approvals are dropped.
  - Rationale: FR-2 and P1 require the payment record to be the single truth. An authorization at the acquirer that the platform does not know about breaks this and harms cardholders.
  - Expected benefit: No double holds on cardholder funds, and every acquirer-side authorization is accounted for (FR-2, FR-10, P1). (objectives: FR-7, FR-2, P1)
  - Supporting evidence: EV-133, EV-132, EV-013, EV-174
  - Verification: Add an FR-7 case in which the simulator approves attempt 1 at 2,600 ms. Pass if a reversal is sent for attempt 1 and exactly one authorization stays live at the simulator.
- Decision AD-011 (24 Cascade policy): refines. Keeps the cascade triggers but adds a reversal or status inquiry for ambiguous outcomes before cascading.
- Decision AD-032 (FR-7): preserves. The attempt limits and scheme rules are unchanged.
- Decision AD-040 (FR-5): preserves. Restores 'at most one authorization' per request.
- Decision AD-038 (FR-2): preserves. The state machine keeps a single truth for each payment.

### FND-018 Latency budget excludes cascades using a 1% figure that contradicts the 3.8% retryable baseline

- **risk** · internal contradiction · severity **high** · confidence 0.85 (high) · rank 8
- Disposition: **refinement now** (also: needs testing)

Section 21.1 leaves cascades out of the p99 because 'fewer than 1% of card payments cascade'. Section 10.5 gives 3.8% retryable outcomes, cascading recovers about 31% of them, and the NFR-2 acceptance test injects 3.8% retryable outcomes. With about 3.8% of payments cascading, the cascade path falls inside the 99th percentile. A timeout-triggered cascade alone takes at least 2,500 ms plus a second round trip, well over the 1,500 ms in NFR-2. As specified, NFR-2 (which explicitly includes 'any cascade') is likely to fail its own acceptance test.

- Where: p.17 §21.1 (NFR-2): "Cascading does not move the p99 because fewer than 1% of card payments cascade; the cascade path therefore sits above the 99th percentile."
- Where: p.9 §10.5: "retryable outcomes - soft declines eligible for reattempt plus acquirer-side errors and timeouts - 3.8%."
- Where: p.9 §11.1 (FR-7): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms"
- Evidence EV-066 (doc, supports): "Cascading does not move the p99 because fewer than 1% of card payments cascade; the cascade path therefore sits above the 99th percentile." [doc:DOC-design_v1#p17/s21.1]
- Evidence EV-011 (doc, supports): "retryable outcomes - soft declines eligible for reattempt plus acquirer-side errors and timeouts - 3.8%." [doc:DOC-design_v1#p9/s10.5]
- Evidence EV-013 (doc, supports): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms" [doc:DOC-design_v1#p9/s11.1]
- Evidence EV-012 (doc, supports): "End-to-end p99 latency for a card authorization, measured at the API edge and including any cascade, shall not exceed 1,500 ms." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-067 (doc, supports): "Under the NFR-1 load with 3.8% retryable-outcome injection, p99 end-to-end card authorization ≤ 1,500" [doc:DOC-design_v1#p20/s26.2]
- Evidence EV-111 (inference, supports): "If about 3.8% of card payments cascade, the slowest 1% are mostly cascaded payments. Any of those triggered by the 2,500 ms timeout already exceed 1,500 ms, so the p99 in Section 21.1 cannot leave cascades out and NFR-2 is likely to fail its own test." [inference:EV-111] derived from EV-066, EV-011, EV-013, EV-012, EV-067
- Recommendation: Rewrite the Section 21.1 cascade paragraph using the 3.8% retryable rate. Then choose one: (a) cut the per-attempt timeout and set a total cascade deadline that fits within 1,500 ms; (b) cascade only on fast-fail outcomes (5xx, connection refused, soft declines) and not on timeouts; or (c) restate NFR-2 as a separate p99 for non-cascaded and cascaded payments. Model the cascade tail separately in the budget.
  - Issue: The latency budget's cascade-share figure contradicts the baseline, and the cascade timeout is longer than the whole NFR-2 budget.
  - Rationale: NFR-2 explicitly includes cascades, and the acceptance test injects 3.8% retryable outcomes.
  - Expected benefit: A latency budget that holds together and an NFR-2 that can actually be achieved and verified. (objectives: NFR-2, FR-7)
  - Supporting evidence: EV-066, EV-011, EV-013, EV-012, EV-067, EV-111
  - Verification: NFR-2 benchmark with 3.8% retryable injection that includes the timeout share, reporting p99 for all payments and for cascaded payments separately.
- Next step: Payments Core tech lead: Measure the timeout share of retryable outcomes from 2025 data and choose the timeout or requirement change before Phase 4.
- Decision AD-011 (24 Cascade policy): refines. Keeps the cascade triggers and two-attempt limit but bounds them with a per-payment deadline or a shorter per-attempt timeout.
- Decision AD-053 (NFR-2): refines. One option restates NFR-2 separately for payments with and without a cascade.
- Decision AD-032 (FR-7): preserves. The scheme reattempt limits are unaffected.

### FND-054 All-files-received batch matching misses the NFR-8 08:00 SGT deadline, and one late file blocks every payout

- **risk** · scalability or failure mode · severity **high** · confidence 0.80 (high) · rank 9
- Disposition: **refinement now** (also: needs testing)

The matcher starts only after every expected file has arrived. ACQ-TH1 delivers at 06:30 ICT (07:30 SGT), and at 2025 volume matching takes 45 minutes and reports 15 more, so reports are ready around 08:30 SGT even before volume roughly doubles by 2027. NFR-8 is therefore missed every day. Because matching gates SETTLED transitions and payouts, a single late or missing provider file holds up reconciliation and FR-17 payouts for all markets. At 99.9% auto-match, several thousand exceptions a day go to Finance Operations, and no capacity or service level is defined for handling them.

- Where: p.13 §16.2 (NFR-8, FR-11): "matcher starts once all expected files for business day T have been received"
- Where: p.13 §16.2 (NFR-8): "the matcher's measured end-to-end run time is 45 minutes, and merchant settlement report generation takes a further"
- Where: p.3 §2.2 (NFR-8): "At least 99.9% of settlement lines shall be auto-matched; merchant settlement reports for business day T shall be published by"
- Evidence EV-163 (doc, supports): "matcher starts once all expected files for business day T have been received" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-016 (doc, supports): "the matcher's measured end-to-end run time is 45 minutes, and merchant settlement report generation takes a further" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-014 (doc, supports): "ACQ-TH1 CSV over SFTP Daily 06:30 ICT" [doc:DOC-design_v1#p12/s16.1]
- Evidence EV-131 (doc, supports): "Payment attempts per day (average) 5.1 M 10.5 M" [doc:DOC-design_v1#p2/s1]
- Evidence EV-182 (inference, supports): "06:30 ICT is 07:30 SGT; adding 45 minutes of matching and 15 minutes of reporting gives about 08:30 SGT at 2025 volume, later at about 2× volume in 2027. At 0.1% unmatched, roughly 10 M daily lines produce on the order of 10,000 exceptions a day." [inference:EV-182] derived from EV-163, EV-016, EV-014, EV-131
- Evidence EV-071 (doc, supports): "The batch matcher starts once all expected files for business day T have been received" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-017 (doc, supports): "08:00 SGT on T+1." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-145 (inference, supports): "06:30 ICT (UTC+7) is 07:30 SGT (UTC+8); 07:30 + 45 min + 15 min = 08:30 SGT at 2025 volume, 30 minutes past the 08:00 SGT target, before any scaling to the 2027 volume of about 2x." [inference:EV-145] derived from EV-014, EV-016, EV-131
- Recommendation: In 16.2, match each provider file as it arrives and run only cross-provider netting and payout computation as a final step at a set cut-off. Define a late-file policy: publish partial reports at 08:00 SGT and release payouts for merchant accounts whose providers are complete. Benchmark the matcher at 2027 volume, and size and assign an owner for the Finance Operations exception queue.
  - Issue: The reconciliation schedule fails NFR-8 arithmetically and has no policy for late files.
  - Rationale: Settlement reports and T+1 payouts are commitments to merchants. Putting every provider behind the slowest file creates a daily miss and a single point of failure.
  - Expected benefit: Meets NFR-8 and protects FR-17 payout schedules against one provider's late delivery. (objectives: NFR-8, FR-11, FR-17)
  - Supporting evidence: EV-163, EV-016, EV-014, EV-131, EV-182
  - Verification: Extend the NFR-8 test to replay 2027 volume with ACQ-TH1 arriving at 07:30 SGT and one provider file missing. Reports must publish by 08:00 SGT, and unaffected merchants' payouts must be released.
- Decision AD-016 (24 Reconciliation): challenges. Explicit challenge: the document's own times (EV-014, EV-016, EV-163, EV-131) show that the 'start after all files received' trigger publishes at about 08:30 SGT, so it cannot meet NFR-8; the three-way match is kept.
- Decision AD-056 (NFR-8): preserves. The change exists to meet NFR-8.
- Decision AD-045 (FR-11): preserves. The three-way match and exception raising are unchanged.
- Decision AD-051 (FR-17): preserves. Protects FR-17 payout schedules from a single late file.

### FND-022 State machine lacks transitions that other sections depend on

- **risk** · internal contradiction · severity **high** · confidence 0.80 (high) · rank 12
- Disposition: **refinement now**

FR-2 allows only the transitions in Section 7.2, but several flows elsewhere need ones that are missing. Section 11.4 returns FAILED for a wallet or bank payment sitting in REQUIRES_ACTION, and a failed 3DS challenge needs the same, but REQUIRES_ACTION can only go to AUTHORISING or CANCELLED. Section 16.2 moves matched payments to SETTLED, but a payment refunded before settlement (PARTIALLY_REFUNDED or REFUNDED) cannot reach SETTLED, which would create reconciliation exceptions and put NFR-8's 99.9% auto-match at risk. The REVIEW 'authorize-and-hold-capture' outcome and repeated partial captures have no state representation either. The FR-2 property test checks conformance to Section 7.2, so it cannot detect these gaps.

- Where: p.9 §11.4 (FR-2): "A failure returns FAILED and the merchant may create a new payment."
- Where: p.13 §16.2 (FR-2, NFR-8): "Matched payments transition to SETTLED and a settlement journal is posted."
- Where: p.2 §2.1 (FR-2): "Every payment shall be in exactly one state of the state machine in Section 7 at any time; only the transitions listed there shall be"
- Evidence EV-076 (doc, supports): "REQUIRES_ACTION -> AUTHORISING | CANCELLED (expiry)" [doc:DOC-design_v1#p6/s7.2]
- Evidence EV-077 (doc, supports): "PARTIALLY_REFUNDED -> REFUNDED" [doc:DOC-design_v1#p6/s7.2]
- Evidence EV-078 (doc, supports): "A failure returns FAILED and the merchant may create a new payment." [doc:DOC-design_v1#p9/s11.4]
- Evidence EV-079 (doc, supports): "Matched payments transition to SETTLED and a settlement journal is posted." [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-080 (doc, supports): "REVIEW -> per merchant config: authorize-and-hold-capture, or FAILED" [doc:DOC-design_v1#p7/s8]
- Evidence EV-115 (inference, supports): "Wallet, bank or 3DS failure from REQUIRES_ACTION, settlement of payments already refunded, review holds, and multiple partial captures all need transitions or states that Section 7.2 does not list. FR-2 would therefore either reject real events or be broken by them." [inference:EV-115] derived from EV-076, EV-077, EV-078, EV-079, EV-080
- Recommendation: Add REQUIRES_ACTION -> FAILED. Model settlement separately from refund state, either as a settlement_status attribute or by allowing PARTIALLY_REFUNDED/REFUNDED -> SETTLED. Define how REVIEW holds are represented (a capture_hold flag or an AUTHORISED_ON_HOLD state) and what REVIEW does for wallets, which have no capture. Define multiple partial captures (CAPTURED -> CAPTURED with captured_minor ≤ amount_minor). Build the FR-2 property test from end-to-end flow scenarios as well as from the Section 7.2 graph.
  - Issue: Section 7.2 is incomplete compared with the flows in Sections 8, 11.4 and 16.2.
  - Rationale: FR-2 makes Section 7.2 the full set of allowed transitions, and Section 27 rates it Ready.
  - Expected benefit: FR-2 can be met in practice, and reconciliation of refunded payments matches automatically, which supports NFR-8. (objectives: FR-2, FR-1, FR-9, NFR-8)
  - Supporting evidence: EV-076, EV-077, EV-078, EV-079, EV-080, EV-115
  - Verification: Scenario tests for wallet decline, 3DS failure, refund before settlement then settlement, REVIEW hold then release, and two partial captures all complete with only permitted transitions.
- Decision AD-038 (FR-2): refines. Completes the Section 7.2 transition set that FR-2 makes exhaustive.
- Decision AD-016 (24 Reconciliation): preserves. Reconciliation can mark refunded payments as settled without changing the batch decision.

### FND-055 Fraud fallback accepts LOW and MEDIUM merchant payments unscored, with no limit or risk owner

- **risk** · scalability or failure mode · severity **medium** · confidence 0.65 (medium) · rank 14
- Disposition: **governance decision** (also: needs testing) · already acknowledged in the document

If FRV-1 times out or returns an error, payments for LOW and MEDIUM risk-tier merchants are accepted unscored. With a 150 ms hard timeout and the vendor SLA not yet agreed (Backlog 4), a vendor brownout during a campaign peak would let most card volume through without scoring. P8 treats fraud signals as optional enrichment, while FR-9 requires every card payment to be scored, and the design names no risk owner, exposure cap or alert for the unscored share.

- Where: p.11 §13.2 (FR-9): "Hard timeout 150 ms. On timeout or vendor error: LOW and MEDIUM risk-tier merchants receive ACCEPT;"
- Where: p.4 §3 (P8): "Fail closed on security, degrade gracefully on enrichment. Authentication and authorization failures deny. Optional enrichment"
- Where: p.19 §25: "FRV-1 contract - data processing agreement and SLA finalisation."
- Evidence EV-164 (doc, supports): "Hard timeout 150 ms. On timeout or vendor error: LOW and MEDIUM risk-tier merchants receive ACCEPT;" [doc:DOC-design_v1#p11/s13.2]
- Evidence EV-020 (doc, supports): "Every card payment and every e-wallet payment above the merchant's configured threshold shall be scored by the fraud-scoring hook" [doc:DOC-design_v1#p3/s2.1]
- Evidence EV-165 (doc, supports): "Fail closed on security, degrade gracefully on enrichment. Authentication and authorization failures deny. Optional enrichment" [doc:DOC-design_v1#p4/s3]
- Evidence EV-183 (inference, supports): "Without a time or amount cap, a vendor outage at 2,000 TPS turns into unbounded fraud exposure for the business, which is a risk-acceptance choice the document leaves unowned." [inference:EV-183] derived from EV-164, EV-020, EV-165
- Recommendation: In 13.2, record the risk owner's decision on fallback. Bound fail-open by amount, duration and local velocity rules using the PAN-fingerprint counters already kept in 11.3. Add a metric and alert for the unscored share, plus an automatic switch to REVIEW when it exceeds a threshold. Amend FR-9 to state the permitted exception.
  - Issue: Fail-open fraud behaviour has no bound, no owner and no monitoring.
  - Rationale: Accepting unscored payments is a financial-risk decision that conflicts with FR-9 and needs explicit acceptance and limits.
  - Expected benefit: Bounded fraud loss during vendor outages and a documented exception to FR-9. (objectives: FR-9, P8)
  - Supporting evidence: EV-164, EV-020, EV-165, EV-183
  - Verification: Extend the FR-9 test with a 30-minute FRV-1 outage under load. The unscored share and caps must behave as configured and the alert must fire.
- Next step: Head of Risk: Approve the fallback policy and caps, and make the FRV-1 SLA terms consistent with them before Phase 8.
- Decision AD-013 (24 Fraud): refines. Keeps the risk-tier fallback but bounds and monitors fail-open ACCEPT.
- Decision AD-043 (FR-9): refines. FR-9 needs a documented exception for vendor outages.
- Decision AD-023 (25 item 4): preserves. The pending FRV-1 SLA terms should match the fallback policy.
- Decision AD-033 (3 Foundational Principles): preserves. Consistent with P8's degrade-to-documented-defaults rule.

## Gaps

### FND-052 Payout bank-account change by a single user, MFA optional, notification only to the changer

- **gap** · security privacy gap · severity **high** · confidence 0.75 (medium) · rank 10
- Disposition: **refinement now**

Section 18.4 lets one Finance or Owner user change the payout bank account in the portal. The only notice goes to the person who made the change, and there is no step-up authentication, second approver, cooling-off period or verification gate, even though the payout account entity has a verified_at field. MFA is enforced only for Owners, so a phished Finance password is enough to redirect a merchant's next payout. The Finance role also both issues refunds and edits the payout account, against P9's separation of money-moving duties. The back-office console (18.5) already requires a second approver for comparable actions; the merchant plane does not.

- Where: p.14 §18.4 (FR-13, FR-17): "A confirmation email is sent to the user who made the change, and the change is written to the audit log."
- Where: p.14 §18.3 (FR-13): "TOTP multi-factor authentication is available to every user and is enforced for the Owner role at first login."
- Where: p.4 §3 (P9): "Least privilege and separation of duties. Every human and service identity has only the permissions its role requires; money-moving"
- Evidence EV-031 (doc, supports): "A Finance or Owner user can change the payout bank account in the portal." [doc:DOC-design_v1#p14/s18.4]
- Evidence EV-032 (doc, supports): "A confirmation email is sent to the user who made the change, and the change is written to the audit log." [doc:DOC-design_v1#p14/s18.4]
- Evidence EV-162 (doc, supports): "TOTP multi-factor authentication is available to every user and is enforced for the Owner role at first login." [doc:DOC-design_v1#p14/s18.3]
- Evidence EV-085 (doc, supports): "Finance Issue refunds; view and export reports; edit payout bank account" [doc:DOC-design_v1#p14/s18.2]
- Evidence EV-180 (inference, supports): "Taking over one Finance account protected only by a password lets an attacker redirect the merchant's whole T+1 payout, and the only notification goes to the attacker-controlled session's own user." [inference:EV-180] derived from EV-031, EV-032, EV-162
- Evidence EV-034 (doc, supports): "Other roles may enable it in their profile." [doc:DOC-design_v1#p14/s18.3]
- Evidence EV-033 (doc, supports): "permissions are separated from configuration permissions." [doc:DOC-design_v1#p4/s3]
- Evidence EV-117 (inference, supports): "With one role holding both refund and payout-destination rights, optional MFA, no second approver and a notice only to the actor, one compromised account can redirect funds unnoticed. That contradicts P9." [inference:EV-117] derived from EV-085, EV-032, EV-034
- Recommendation: In 18.3, require MFA for every role with money-moving permissions (Owner, Admin, Finance, Support) and step-up TOTP re-authentication for payout-account changes, API key creation and refunds. In 18.4, notify all Owners and the merchant's registered contact; require Owner approval when Finance initiates a change; hold payouts to a new account until verified_at is set by account-name or penny-drop verification; and apply a cooling-off period.
  - Issue: The highest-value fraud path, changing where payouts go, has weaker controls than the internal console.
  - Rationale: P9 requires money-moving permissions to be separated, and FR-17 payouts go to the 'registered' account. Without verification and multi-party control, a takeover means direct financial loss.
  - Expected benefit: Prevents payout diversion and enforces P9 in the merchant plane. (objectives: P9, FR-13, FR-17)
  - Supporting evidence: EV-031, EV-032, EV-162, EV-085, EV-180
  - Verification: Extend the FR-13 role-matrix test: a change without step-up fails, a Finance change stays pending until an Owner approves, and the FR-17 test shows no payout to an unverified account.
- Decision AD-018 (24 Merchant user MFA): challenges. Explicit challenge to 'MFA optional for other roles': the document shows Finance can redirect payouts (EV-031, EV-085), MFA is optional for Finance (EV-034, EV-162) and only the actor is notified (EV-032), which contradicts P9 (EV-033).
- Decision AD-033 (3 Foundational Principles): preserves. Applies principle P9, which takes precedence.
- Decision AD-047 (FR-13): preserves. Payout bank details stay manageable in the admin plane, with stronger controls.
- Decision AD-051 (FR-17): preserves. Protects payouts to the registered account.

### FND-057 No cross-border transfer or retention analysis for personal data sent to Singapore, Jakarta DR and FRV-1

- **gap** · security privacy gap · severity **medium** · confidence 0.50 (medium) · rank 16
- Disposition: **needs investigation** (also: governance decision) · already acknowledged in the document

Personal data from customers in five markets is stored only in ap-southeast-1 and replicated to ap-southeast-3. FRV-1 receives IP address, device fingerprint and hashed email and phone (pseudonymous personal data) while its DPA is still pending. Audit records with before and after values are kept immutable for five years. The design records no transfer basis per market, no field-level retention mapping, and no way to reconcile immutable audit payloads with the retention limits NFR-7 requires. Its only check is a DPO sign-off in Phase 9, after the data flows are built. Whether any market law restricts these transfers is unverified here.

- Where: p.3 §2.2 (NFR-7): "Personal data shall be processed in accordance with the personal data protection laws of each market of operation (Singapore"
- Where: p.16 §19.1 (NFR-7): "All primary data stores (Aurora, DynamoDB, ElastiCache, MSK, S3 intake and archive buckets) are in ap-southeast-1."
- Where: p.19 §25: "FRV-1 contract - data processing agreement and SLA finalisation."
- Evidence EV-137 (doc, supports): "Personal data shall be processed in accordance with the personal data protection laws of each market of operation (Singapore" [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-169 (doc, supports): "All primary data stores (Aurora, DynamoDB, ElastiCache, MSK, S3 intake and archive buckets) are in ap-southeast-1." [doc:DOC-design_v1#p16/s19.1]
- Evidence EV-170 (doc, supports): "device fingerprint, IP address, user agent Merchant SDK Device signals" [doc:DOC-design_v1#p11/s13.1]
- Evidence EV-127 (doc, supports): "FRV-1 contract - data processing agreement and SLA finalisation." [doc:DOC-design_v1#p19/s25]
- Evidence EV-185 (inference, supports): "Customer personal data from MY, ID, TH and PH is processed in Singapore and by a third-party vendor without a DPA, and the only check on NFR-7 comes after build, so any transfer restriction would surface too late to change data placement cheaply." [inference:EV-185] derived from EV-137, EV-169, EV-170, EV-127
- Recommendation: Before Phase 3, carry out a privacy impact assessment per market covering the transfer basis for Singapore storage, Jakarta DR and FRV-1. Add a field-level personal-data inventory with purpose and retention to Section 19. Restrict audit before/after payloads to references or masked values. Make the FRV-1 DPA a gate for Phase 8.
  - Issue: Personal-data flows across borders and to FRV-1 are not analysed before build.
  - Rationale: NFR-7 names five national laws, and changing data placement or the vendor payload after Phase 3 is expensive.
  - Expected benefit: Confirms NFR-7 compliance of data placement and of the FRV-1 data sharing early. (objectives: NFR-7)
  - Supporting evidence: EV-137, EV-169, EV-170, EV-127, EV-185
  - Verification: DPO sign-off on the impact assessment before Phase 3, and the NFR-7 field mapping checked against the schema in Section 19.
- Next step: Data Protection Officer: Run a cross-border transfer and retention assessment for the five markets and FRV-1, and report constraints on data placement before Phase 3.
- Decision AD-031 (NFR-7): preserves. The investigation exists to show NFR-7 compliance.
- Decision AD-035 (19.1 Data placement): preserves. Data placement is kept unless the assessment finds a restriction.
- Decision AD-023 (25 item 4): preserves. Makes the pending FRV-1 DPA a phase gate.

### FND-030 Refunds paid to a customer's bank account have no data capture, verification or privacy design

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.65 (medium) · rank 18
- Disposition: **refinement now**

FR-15 pays refunds as bank transfers to the customer's nominated account when a method has no refund API. Nothing in the document says how that account is collected, by the merchant or the customer, or how it is validated, stored or encrypted, or kept under NFR-7. The Section 6 payout account is the merchant's only, and Section 19 has no field for it. The FR-15 test only checks that a payout instruction is produced, so a mistaken or fraudulent destination would not be detected.

- Where: p.3 §2.1 (FR-15): "where a method has no refund API, the refund shall be executed as a bank"
- Where: p.20 §26.1 (FR-15): "Full and partial refunds succeed per method; payout-based refunds produce a payout instruction."
- Evidence EV-103 (doc, supports): "where a method has no refund API, the refund shall be executed as a bank" [doc:DOC-design_v1#p3/s2.1]
- Evidence EV-104 (doc, supports): "Full and partial refunds succeed per method; payout-based refunds produce a payout instruction." [doc:DOC-design_v1#p20/s26.1]
- Evidence EV-105 (doc, supports): "Bank account for merchant payouts." [doc:DOC-design_v1#p6/s6]
- Evidence EV-123 (inference, supports): "FR-15 needs customer bank details, which are personal data and a payment destination, but no section defines how they are captured, verified or stored. The acceptance test cannot catch a wrong destination." [inference:EV-123] derived from EV-103, EV-104, EV-105
- Recommendation: Add a subsection to Section 16.3 or 18 that defines: the API field or hosted form for the customer's account, name or account validation where the rail supports it, encrypted storage and retention, the refund_clearing ledger flow, and failure handling (returned payouts). List which Section 4 methods use this path. Extend the FR-15 acceptance test to cover validation failure and returned-payout cases.
  - Issue: Refunds via customer bank payout are under-specified.
  - Rationale: FR-15 moves money to a destination that is not otherwise held in the system, and that destination is personal data under NFR-7.
  - Expected benefit: FR-15 refunds go to the right account and are handled in line with NFR-7. (objectives: FR-15, NFR-7, FR-10)
  - Supporting evidence: EV-103, EV-104, EV-105, EV-123
  - Verification: FR-15 test covers a payout refund rejected for an invalid account and a returned payout reversing the refund_clearing posting.
- Decision AD-049 (FR-15): refines. Specifies how the bank-payout refund fallback in FR-15 works.
- Decision AD-031 (NFR-7): preserves. Brings customer bank details under the NFR-7 handling rules.

## Ambiguities

### FND-029 FR-8's 2% tolerance has no unit and the routing mechanisms conflict

- **ambiguity** · ambiguous requirement · severity **medium** · confidence 0.70 (medium) · rank 19
- Disposition: **refinement now**

FR-8 says 'more than 2%' and Section 10.3 says 'tolerance (default 2)', without stating whether this is 2 percentage points or a 2% relative change. Section 10.2 ranks acquirers by a weighted score, while Section 10.3 compares the cheapest acquirer with the highest-approval one, and a weekly review checks realised rates against a control slice. It is unclear which of these enforces the per-transaction FR-8. The FR-8 acceptance test only checks that the 'expected choice' is picked, so it cannot settle these readings.

- Where: p.9 §10.3 (FR-8): "applies the cost preference when the difference is within the configured tolerance (default 2)."
- Where: p.2 §2.1 (FR-8): "For each transaction, the Routing Engine shall prefer the lowest-cost eligible acquirer unless doing so reduces the expected"
- Where: p.19 §26.1 (FR-8): "For a set of synthetic transactions with configured costs and approval priors, the selected acquirer matches the"
- Evidence EV-099 (doc, supports): "applies the cost preference when the difference is within the configured tolerance (default 2)." [doc:DOC-design_v1#p9/s10.3]
- Evidence EV-100 (doc, supports): "For each transaction, the Routing Engine shall prefer the lowest-cost eligible acquirer unless doing so reduces the expected" [doc:DOC-design_v1#p2/s2.1]
- Evidence EV-101 (doc, supports): "Weights are configured per merchant account; the default emphasises cost." [doc:DOC-design_v1#p9/s10.2]
- Evidence EV-102 (doc, supports): "For a set of synthetic transactions with configured costs and approval priors, the selected acquirer matches the" [doc:DOC-design_v1#p19/s26.1]
- Evidence EV-122 (inference, supports): "At an 88% approval rate, 2 percentage points and a 2% relative change differ by about 0.24 points. With both a weighted score and a pairwise rule in play, the 'expected choice' in the FR-8 test is not uniquely defined." [inference:EV-122] derived from EV-099, EV-100, EV-101, EV-102
- Evidence EV-038 (doc, supports): "authorization rate by more than 2%." [doc:DOC-design_v1#p3/s2.1]
- Evidence EV-039 (doc, supports): "Routing Weighted cost/approval/latency score; cost-preferred within 2 tolerance" [doc:DOC-design_v1#p18/s24]
- Recommendation: State the unit in FR-8, Section 10.3 and the Section 24 routing row (for example '2.0 percentage points of approval_prior'). Specify the order of operations: compute the weighted score, then apply the FR-8 guard as an override, or the reverse. Add FR-8 boundary test cases at tolerance ±0.1.
  - Issue: FR-8 has no stated unit and two routing mechanisms that may disagree.
  - Rationale: Routing cost and approval rate are central business objectives, and the test needs one defined rule.
  - Expected benefit: FR-8 can be implemented and tested without guesswork. (objectives: FR-8)
  - Supporting evidence: EV-099, EV-100, EV-101, EV-102, EV-122
  - Verification: FR-8 boundary tests pass with the documented unit and order of operations.
- Decision AD-012 (24 Routing): refines. States the unit and order of operations for the approved 'within 2 tolerance'.
- Decision AD-042 (FR-8): refines. Makes FR-8's '2%' unambiguous and testable.

## Unresolved assumptions

### FND-026 Network tokens 'from launch' depend on a token-requestor application not yet submitted

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.85 (high) · rank 15
- Disposition: **refinement now** (also: governance decision) · already acknowledged in the document

Section 24 confirms network tokens as the main card-on-file credential from launch. Section 27 rates the Vault Ready, and Section 28 marks Phase 3 (card-on-file with network tokens) 'No - ready'. Backlog item 2, however, says the VTS/MDES token-requestor registration and the commercial agreement have not been applied for. FR-14 and the Phase 3 dependency therefore rest on an open item with an unknown lead time. The backlog acknowledges the item; this finding points out that the readiness and phase tables do not reflect it.

- Where: p.19 §25 (FR-14): "the commercial agreement with a token service provider; certification test plan. Application not yet submitted."
- Where: p.18 §24 (FR-14): "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch; PAN"
- Where: p.21 §28 (FR-14): "Transaction core - Payments API, idempotency, state machine, ledger, outbox; card-on-file"
- Evidence EV-036 (doc, supports): "the commercial agreement with a token service provider; certification test plan. Application not yet submitted." [doc:DOC-design_v1#p19/s25]
- Evidence EV-035 (doc, supports): "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch; PAN" [doc:DOC-design_v1#p18/s24]
- Evidence EV-090 (doc, supports): "Transaction core - Payments API, idempotency, state machine, ledger, outbox; card-on-file" [doc:DOC-design_v1#p21/s28]
- Evidence EV-037 (doc, supports): "Tokenisation, envelope encryption, HSM, SAD handling and network tokens specified" [doc:DOC-design_v1#p20/s27]
- Evidence EV-119 (inference, supports): "A decision confirmed 'from launch' and a phase marked ready both depend on a registration that has not been applied for, so the readiness tables overstate FR-14." [inference:EV-119] derived from EV-036, EV-035, EV-090, EV-037
- Evidence EV-056 (inference, supports): "A confirmed 'from launch' decision and a 'Ready' rating cannot be relied on while the token-requestor application and certification on which they depend have not started." [inference:EV-056] derived from EV-035, EV-036, EV-037
- Recommendation: In Sections 27 and 28, mark the card-on-file network-token work as depending on Backlog item 2, with an owner and target date. State that the launch credential is the PAN with MIT/CIT indicators until registration is complete, and adjust the Section 24 wording to match.
  - Issue: Phase 3 and FR-14 readiness are marked ready while they depend on Backlog item 2.
  - Rationale: Without a token-requestor registration, FR-14 network tokens cannot be provisioned at launch.
  - Expected benefit: An accurate launch plan for FR-14 and a defined PAN-based interim. (objectives: FR-14)
  - Supporting evidence: EV-036, EV-035, EV-090, EV-037, EV-119
  - Verification: Section 28 dependency column cites Backlog item 2, and the FR-14 test runs once certification is done.
- Next step: Card partnerships manager: Submit the VTS/MDES token-requestor applications and report the lead time against the Phase 3 schedule.
- Decision AD-010 (24 Card-on-file credential): refines. Network tokens stay the target, with a PAN plus MIT/CIT interim until token-requestor certification.
- Decision AD-021 (25 item 2): preserves. Links the pending token-requestor onboarding item to the plan, with an owner.
- Decision AD-048 (FR-14): preserves. FR-14 already allows PAN where tokens are unavailable.

### FND-043 Single-region Singapore hosting assumed permissible under all five markets' payment regulation

- **unresolved assumption** · missing or unverifiable requirement · severity **medium** · confidence 0.45 (low) · rank 17
- Disposition: **needs investigation**

All workloads and primary data stores sit in Singapore, with DR in Jakarta. NFR-7 considers only personal data protection laws. The design does not show that the payment-system and financial-sector regulators in the five markets permit offshore processing and storage of domestic payment transactions. Indonesia is the largest market (4,200 merchants) and has domestic QRIS and bank-transfer flows. The design also does not address the cross-border transfer implications of replicating all markets' data into Indonesia for DR. Whether any such constraint applies is unverified, but if it does it would change the hosting architecture.

- Where: p.5 §5: "All workloads run on Amazon EKS in ap-southeast-1 (Singapore) across three Availability Zones. The CDE runs in a"
- Where: p.3 §2.2 (NFR-7): "Personal data shall be processed in accordance with the personal data protection laws of each market of operation (Singapore"
- Where: p.16 §19.1: "The Aurora Global Database secondary in ap-southeast-3 (Jakarta) is used for disaster recovery only (Section 20)."
- Evidence EV-136 (doc, supports): "All workloads run on Amazon EKS in ap-southeast-1 (Singapore) across three Availability Zones. The CDE runs in a" [doc:DOC-design_v1#p5/s5]
- Evidence EV-137 (doc, supports): "Personal data shall be processed in accordance with the personal data protection laws of each market of operation (Singapore" [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-149 (inference, supports): "The requirement set covers data protection only. No requirement, decision or backlog item records a review of payment-system or financial-sector data-location and licensing rules for the five markets, so single-region hosting is an untracked premise." [inference:EV-149] derived from EV-136, EV-137
- Recommendation: Add an NFR or a Section 25 item: a per-market regulatory review (payment-system licensing, data-location and domestic-processing rules, cross-border transfer for DR), with sign-off by market counsel before Phase 5 adapters go live in each market. Record the outcome in Section 24.
  - Issue: No regulatory check is recorded for offshore processing of domestic payments or for cross-border DR replication.
  - Rationale: A data-location constraint discovered after build would force regional re-architecture, and Indonesia carries the most merchants.
  - Expected benefit: Lawful operation in all five markets, and the NFR-7 coverage the design intends. (objectives: NFR-7)
  - Supporting evidence: EV-136, EV-137, EV-149
  - Verification: Per-market legal sign-off is attached to the go-live gate for each market.
- Next step: Head of Compliance with market legal counsel: Confirm, per market, whether payment transactions and records may be processed and stored in Singapore and replicated to Jakarta.
- Decision AD-001 (24 Cloud and primary region): preserves. The Singapore primary region is kept pending per-market legal confirmation.
- Decision AD-035 (19.1 Data placement): preserves. DR-only use of Jakarta is unchanged unless counsel finds a constraint.
- Decision AD-031 (NFR-7): preserves. Complements NFR-7 with payment-system regulation.

## Validation needs

### FND-034 DynamoDB capacity claims for idempotency keyed by merchant_id are unverified

- **validation need** · unsupported or incorrect claim · severity **high** · confidence 0.65 (medium) · rank 11
- Disposition: **needs investigation** (also: needs prototyping, refinement now)

Section 9.3 says one partition sustains 10,000 WCU per second and that two writes per request give about 1,800 WCU for M-0001 at 900 TPS. The per-partition figure is far above the reviewer's understanding of DynamoDB's documented limit and must be checked. The WCU arithmetic also ignores item size (response_body up to 4 KB) and the extra writes from the LSI. Separately, the LSI keeps each merchant's whole item collection together, which may hit a size limit for a merchant writing millions of records a day. If any of these premises fails, idempotency throttles for the merchant carrying 45% of peak traffic, which would be an outage at expected load against NFR-1 and NFR-3. Separately, 9.1's 'after expiry is treated as new' assumes TTL deletion is immediate. If expired items persist, the attribute_not_exists put fails and the request is wrongly treated as a duplicate.

- Where: p.8 §9.3 (NFR-1): "single partition sustains up to 10,000 write capacity units per second."
- Where: p.8 §9.3 (NFR-1): "two writes - lock acquisition and completion update - or about 1,800 WCU at peak"
- Where: p.7 §9.1 (FR-5): "Records are retained for 24 hours from first use. A request after expiry is treated as new."
- Evidence EV-028 (doc, supports): "single partition sustains up to 10,000 write capacity units per second." [doc:DOC-design_v1#p8/s9.3]
- Evidence EV-030 (doc, supports): "response_body String Serialised response, up to 4 KB" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-128 (doc, supports): "created_at String ISO 8601; LSI sort key lsi_created_at" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-141 (inference, supports): "At about 45% of 10.5 M daily attempts, M-0001 writes roughly 4.7 M items a day of up to about 4-5 KB each, i.e. roughly 20 GB under one partition key value within the 24-hour retention, and each completion write costs several WCU rather than one; whether the platform limits allow this is unverified." [inference:EV-141] derived from EV-028, EV-030, EV-128
- Evidence EV-159 (doc, supports): "two writes - lock acquisition and completion update - or about 1,800 WCU at peak, comfortably within the perpartition ceiling." [doc:DOC-design_v1#p8/s9.3]
- Evidence EV-160 (doc, supports): "Largest single merchant share at peak 41% 45%" [doc:DOC-design_v1#p2/s1]
- Evidence EV-178 (inference, supports): "If writes are metered per KB of item size (to be verified), 900 TPS × (1 lock unit + about 5 completion units) is about 5,400 WCU, not 1,800. At about 45% of 10.5 M daily attempts, M-0001 holds about 4.7 M items of up to about 4.5 KB, roughly 20 GB, under one partition-key value with an LSI." [inference:EV-178] derived from EV-159, EV-030, EV-160
- Evidence EV-121 (inference, supports): "The 1,800 WCU figure assumes small items and no index write cost, and the per-partition ceiling is unsourced. A uniform load test would not reveal throttling on M-0001's partition key." [inference:EV-121] derived from EV-095, EV-096, EV-097, EV-098
- Recommendation: In 9.2 and 9.3: check the per-partition throughput and LSI item-collection limits against current AWS documentation. Change the partition key to a composite merchant_id#idempotency_key and drop the LSI. Serve the back-office 'recent requests by merchant' view from Aurora or analytics, or from a write-sharded GSI. Store large response bodies by reference or compressed. Add a ttl > now condition so expired-but-undeleted items count as absent. Recompute WCU per request including item size.
  - Issue: Idempotency-store capacity rests on unverified DynamoDB limits and leaves out item size and LSI write cost.
  - Rationale: The idempotency check is on every mutating call. Throttling for the largest merchant would block 45% of peak traffic.
  - Expected benefit: NFR-1 throughput and NFR-3 availability for the largest merchant; FR-5 correctness after expiry. (objectives: NFR-1, NFR-3, FR-5)
  - Supporting evidence: EV-028, EV-030, EV-128, EV-141
  - Verification: Single-merchant load test at 1,350 TPS (1.5x M-0001 peak) for four hours with zero DynamoDB throttling events. Expiry test confirms a reused key after ttl is accepted as new.
- Next step: Payments Core tech lead: Check the DynamoDB limits against AWS documentation and run a single-tenant hot-key load test on the current key schema before Phase 3.
- Decision AD-006 (24 Idempotency store): refines. The key or LSI change is conditional on the investigation showing that DynamoDB limits bind; the evidence does not yet justify reversing the approved schema.
- Decision AD-007 (24 Idempotency retention): preserves. The 24-hour retention is kept; only the handling of expired items still present is tightened.
- Decision AD-052 (NFR-1): preserves. The aim is to protect NFR-1 throughput for the largest merchant.

### FND-027 FR-5 acceptance test omits concurrency, cross-merchant and crash cases

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.80 (high) · rank 13
- Disposition: **needs testing** (also: refinement now)

FR-5 requires the same response and at most one provider call 'including when duplicate requests arrive concurrently'. The acceptance test only resends after the first response has arrived, so it never exercises the conditional-put lock, the 409 path, the Redis fast path across merchants, or crash recovery. There is also a missing error path: the sweeper scans payments in AUTHORISING, so a pod that crashes after the DynamoDB put but before the payment row is created leaves an IN_PROGRESS record with no payment to resolve. That key then returns 409 until the 24-hour TTL expires.

- Where: p.19 §26.1 (FR-5): "Send a create-payment request; after its response is received, resend the identical request with the same"
- Where: p.2 §2.1 (FR-5): "shall return the identical response, including when duplicate requests arrive concurrently."
- Where: p.8 §9.2 (FR-5): "A lock left IN_PROGRESS by a crashed API pod is recovered by the Orchestrator's stuck-payment sweeper"
- Evidence EV-091 (doc, supports): "Send a create-payment request; after its response is received, resend the identical request with the same" [doc:DOC-design_v1#p19/s26.1]
- Evidence EV-092 (doc, supports): "shall return the identical response, including when duplicate requests arrive concurrently." [doc:DOC-design_v1#p2/s2.1]
- Evidence EV-093 (doc, supports): "A lock left IN_PROGRESS by a crashed API pod is recovered by the Orchestrator's stuck-payment sweeper" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-094 (doc, supports): "Every 60 seconds, the Orchestrator's sweeper finds payments in AUTHORISING for more than 30 seconds" [doc:DOC-design_v1#p17/s20.3]
- Evidence EV-120 (inference, supports): "A sequential replay test cannot show concurrent deduplication. A sweeper that starts from payments cannot find idempotency locks taken before any payment existed." [inference:EV-120] derived from EV-091, EV-092, EV-093, EV-094
- Evidence EV-168 (doc, supports): "payment_id String Set once known" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-184 (inference, supports): "A lock acquired before the payment exists, or for a payment that never reaches AUTHORISING, has no payment for the sweeper to find, so it stays IN_PROGRESS until the 24-hour TTL expires." [inference:EV-184] derived from EV-166, EV-167, EV-168
- Recommendation: Extend the FR-5 test in Section 26.1: N parallel identical requests give exactly one simulator authorisation, one 201 and the others 409 or an identical replay; two merchants send the same key; a pod is killed between lock and payment creation, and between authorisation and completion. In Sections 9.2 and 20.3, add a sweep of DynamoDB IN_PROGRESS records older than a threshold with no payment_id, releasing them or marking them failed.
  - Issue: The FR-5 criterion does not cover the concurrency it is meant to verify, and lock recovery has a hole.
  - Rationale: Concurrent duplicates during retry storms are the main risk FR-5 addresses.
  - Expected benefit: FR-5 is demonstrated under the conditions that matter, and keys cannot be locked out for 24 hours. (objectives: FR-5)
  - Supporting evidence: EV-091, EV-092, EV-093, EV-094, EV-120
  - Verification: Extended FR-5 test suite passes in CI and in the Phase 9 chaos runs.
- Next step: QA lead, Payments Core: Add the concurrent, cross-merchant and crash-injection cases to the FR-5 test design.
- Decision AD-040 (FR-5): preserves. Makes FR-5's concurrency clause verifiable.
- Decision AD-006 (24 Idempotency store): preserves. The store design is kept; only the sweeper scope is extended.
- Decision AD-007 (24 Idempotency retention): preserves. Retention is unchanged.

## Recommended refinements

| Finding | Change | Expected benefit |
|---|---|---|
| FND-001 | In Section 9.2 and in the Section 24 idempotency row, change the Redis key to idem:resp:{merchant_id}:{idempotency_key}. Store request_hash with the cached response and compare it on every hit, returning 422 on mismatch. Add tests to Section 26 FR-5: two merchants using the same key get independent payments, and a same-key request with a different body is rejected on the fast path. | FR-5 holds on the fast path too, and responses cannot leak between merchants. |
| FND-046 | Decide one of two options. (a) Remove card_number from the 13.1 payload and send FRV-1 the keyed PAN fingerprint or another vendor-accepted surrogate. (b) Move the FRV-1 call that needs PAN into a CDE-resident relay with its own service identity, add it and FRV-1 (as a third-party service provider) to 12.2, and make PCI responsibilities part of the Backlog 4 contract. In both cases, remove detokenise from the core-VPC private endpoint in Section 5. | Keeps the CDE limited to the four components in 12.2 (NFR-5) and restores least privilege (P9). |
| FND-032 | Get a written QSA interpretation of 12.4 against the PCI DSS version that will be in force at assessment. If retention after authorization is not allowed: (1) limit CVC use to the synchronous initial authorization request, including any cascade within that request, and delete the CVC when the request completes; (2) perform incremental authorizations by referencing the original authorization, without the CVC; (3) rewrite 12.4, NFR-6, the Section 24 CVC decision and the NFR-6 test to say 'absent upon completion of authorization'. | Makes NFR-5 (Level 1 service provider assessment) and NFR-6 achievable. |
| FND-049 | The accountable owner chooses either (a) restating NFR-4 as a bounded RPO (for example ≤ 1 s for the database) plus mandatory post-failover recovery of in-flight authorizations from acquirer reports and reversal or recording of orphans, or (b) a synchronous cross-region commit design and its latency cost. Separately, add idempotency_key and request_hash columns to payment, with a unique constraint on (merchant_account_id, idempotency_key), so the 20.2 rebuild is possible. Document regional failover as excluded from, or in conflict with, NFR-3. | An honest, testable DR objective (NFR-4), FR-5 that holds across failover, and an NFR-3 budget consistent with the DR plan. |
| FND-048 | In 12.3, provision at least two HSMs in different AZs from launch, and update the Section 24 decision. Classify Vault 503 as a non-cascading platform error with fast failure, rather than retryable. Add to 20.2 a standby CDE in ap-southeast-3: a CloudHSM cluster restored from a cross-region backup copy, replicated Vault storage, and Card Adapter steps in the failover runbook. Benchmark HSM operations per second for the 2,000 TPS card mix. | Card acceptance survives the loss of one AZ (NFR-3) and the loss of the region (NFR-4), and HSM capacity is confirmed for NFR-1. |
| FND-017 | In Section 28, make go-live depend on completing Phase 8 (Fraud Hook, which needs Backlog item 4 closed) and the Phase 9 items needed for the cohort: PCI DSS ROC, NFR-1/2 load test and NFR-4 game day. If an earlier launch is still wanted, record an explicit risk-acceptance decision with interim controls, such as acquirer-side fraud screening and lower limits. | Launch meets FR-9 and NFR-5, and fraud loss and compliance exposure at go-live are bounded. |
| FND-047 | In 11.1, split Retryable into 'definite' (connection refused, explicit soft decline) and 'ambiguous' (timeout, 5xx). Before cascading an ambiguous attempt, the adapter sends an authorization reversal or a status inquiry for it. In 11.2, replace 'logged and discarded' with: a late approval on a superseded attempt triggers an automatic reversal and an audit event, and is tracked until confirmed. Correct the 'cannot create a duplicate charge' sentence. | No double holds on cardholder funds, and every acquirer-side authorization is accounted for (FR-2, FR-10, P1). |
| FND-018 | Rewrite the Section 21.1 cascade paragraph using the 3.8% retryable rate. Then choose one: (a) cut the per-attempt timeout and set a total cascade deadline that fits within 1,500 ms; (b) cascade only on fast-fail outcomes (5xx, connection refused, soft declines) and not on timeouts; or (c) restate NFR-2 as a separate p99 for non-cascaded and cascaded payments. Model the cascade tail separately in the budget. | A latency budget that holds together and an NFR-2 that can actually be achieved and verified. |
| FND-054 | In 16.2, match each provider file as it arrives and run only cross-provider netting and payout computation as a final step at a set cut-off. Define a late-file policy: publish partial reports at 08:00 SGT and release payouts for merchant accounts whose providers are complete. Benchmark the matcher at 2027 volume, and size and assign an owner for the Finance Operations exception queue. | Meets NFR-8 and protects FR-17 payout schedules against one provider's late delivery. |
| FND-052 | In 18.3, require MFA for every role with money-moving permissions (Owner, Admin, Finance, Support) and step-up TOTP re-authentication for payout-account changes, API key creation and refunds. In 18.4, notify all Owners and the merchant's registered contact; require Owner approval when Finance initiates a change; hold payouts to a new account until verified_at is set by account-name or penny-drop verification; and apply a cooling-off period. | Prevents payout diversion and enforces P9 in the merchant plane. |
| FND-034 | In 9.2 and 9.3: check the per-partition throughput and LSI item-collection limits against current AWS documentation. Change the partition key to a composite merchant_id#idempotency_key and drop the LSI. Serve the back-office 'recent requests by merchant' view from Aurora or analytics, or from a write-sharded GSI. Store large response bodies by reference or compressed. Add a ttl > now condition so expired-but-undeleted items count as absent. Recompute WCU per request including item size. | NFR-1 throughput and NFR-3 availability for the largest merchant; FR-5 correctness after expiry. |
| FND-022 | Add REQUIRES_ACTION -> FAILED. Model settlement separately from refund state, either as a settlement_status attribute or by allowing PARTIALLY_REFUNDED/REFUNDED -> SETTLED. Define how REVIEW holds are represented (a capture_hold flag or an AUTHORISED_ON_HOLD state) and what REVIEW does for wallets, which have no capture. Define multiple partial captures (CAPTURED -> CAPTURED with captured_minor ≤ amount_minor). Build the FR-2 property test from end-to-end flow scenarios as well as from the Section 7.2 graph. | FR-2 can be met in practice, and reconciliation of refunded payments matches automatically, which supports NFR-8. |
| FND-027 | Extend the FR-5 test in Section 26.1: N parallel identical requests give exactly one simulator authorisation, one 201 and the others 409 or an identical replay; two merchants send the same key; a pod is killed between lock and payment creation, and between authorisation and completion. In Sections 9.2 and 20.3, add a sweep of DynamoDB IN_PROGRESS records older than a threshold with no payment_id, releasing them or marking them failed. | FR-5 is demonstrated under the conditions that matter, and keys cannot be locked out for 24 hours. |
| FND-055 | In 13.2, record the risk owner's decision on fallback. Bound fail-open by amount, duration and local velocity rules using the PAN-fingerprint counters already kept in 11.3. Add a metric and alert for the unscored share, plus an automatic switch to REVIEW when it exceeds a threshold. Amend FR-9 to state the permitted exception. | Bounded fraud loss during vendor outages and a documented exception to FR-9. |
| FND-026 | In Sections 27 and 28, mark the card-on-file network-token work as depending on Backlog item 2, with an owner and target date. State that the launch credential is the PAN with MIT/CIT indicators until registration is complete, and adjust the Section 24 wording to match. | An accurate launch plan for FR-14 and a defined PAN-based interim. |
| FND-057 | Before Phase 3, carry out a privacy impact assessment per market covering the transfer basis for Singapore storage, Jakarta DR and FRV-1. Add a field-level personal-data inventory with purpose and retention to Section 19. Restrict audit before/after payloads to references or masked values. Make the FRV-1 DPA a gate for Phase 8. | Confirms NFR-7 compliance of data placement and of the FRV-1 data sharing early. |
| FND-043 | Add an NFR or a Section 25 item: a per-market regulatory review (payment-system licensing, data-location and domestic-processing rules, cross-border transfer for DR), with sign-off by market counsel before Phase 5 adapters go live in each market. Record the outcome in Section 24. | Lawful operation in all five markets, and the NFR-7 coverage the design intends. |
| FND-030 | Add a subsection to Section 16.3 or 18 that defines: the API field or hosted form for the customer's account, name or account validation where the rail supports it, encrypted storage and retention, the refund_clearing ledger flow, and failure handling (returned payouts). List which Section 4 methods use this path. Extend the FR-15 acceptance test to cover validation failure and returned-payout cases. | FR-15 refunds go to the right account and are handled in line with NFR-7. |
| FND-029 | State the unit in FR-8, Section 10.3 and the Section 24 routing row (for example '2.0 percentage points of approval_prior'). Specify the order of operations: compute the weighted score, then apply the FR-8 guard as an override, or the reverse. Add FR-8 boundary test cases at tolerance ±0.1. | FR-8 can be implemented and tested without guesswork. |

## Areas where no change is needed

- FND-058 Atomic state, ledger and outbox commit with an append-only ledger enforced in the database: The design meets FR-10 and P5 through database-enforced mechanisms rather than convention, and keeps the payment path available when the event bus fails, so no change is justified.
- FND-014 Design intent is explicit and traceable: Explicit IDs, principles, decisions and backlog give a sound basis for reviewing and verifying the design. The contradictions are handled in their own findings.
- SA-001 (sections 14, 19): The atomic state, ledger and outbox commit and the append-only, database-enforced journals meet FR-2, FR-10, P1 and P5. (see FND-058)
  - p.12 §14.3: "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them,"
- SA-002 (sections 15): Signed 64-bit integer minor units, a versioned ISO 4217 exponent table, explicit adapter conversion that rejects any amount needing rounding, and a single half-to-even rounding of fees all satisfy P4 and protect the integrity of FR-10.
  - p.12 §15: "No floating-point type is used for amounts in any service, schema, or API payload."
- SA-003 (sections 17): Timestamped HMAC signatures, per-endpoint secrets with rollover, a bounded at-least-once retry schedule (whose attempt count matches), a DLQ with replay, per-endpoint isolation and SSRF-safe resolution all meet FR-12 and P7 without cross-merchant starvation.
  - p.13 §17: "Each endpoint has a cap of 20 in-flight deliveries and its own circuit breaker, so a failing endpoint"
- SA-004 (sections 11.4, 4): Not cascading redirect and QR methods is correct, because the customer has already committed to a specific wallet or bank. This keeps FR-7 limited to cards and avoids duplicate customer-side payments.
  - p.9 §11.4: "E-wallet and bank-transfer payments are never cascaded: the customer has already been directed to a specific wallet or"
- SA-005 (sections 18.5): For staff write actions, the back-office console uses corporate SSO with hardware MFA, read-only masked defaults and just-in-time elevation approved by a second person, which meets P9 and FR-16. (see FND-052)
  - p.14 §18.5: "write actions (manual refunds, payout holds, merchant suspension) require just-in-time elevation"
- SA-006 (sections 14, 19): Same-transaction journals with an outbox, append-only enforced by revoked DML rights, and a per-currency invariant checked at commit and every night together meet FR-10, P1 and P5. The worked examples balance. (see FND-058)
  - p.12 §14.3: "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them,"
- SA-007 (sections 15, 19): Amounts are integer minor units with ISO 4217 codes, and adapters reject any amount that would need rounding. This is consistent across P4, Section 15 and the BIGINT schema columns, so money values cannot be represented inconsistently.
  - p.12 §15: "No floating-point type is used for amounts in any service, schema, or API payload."
- SA-008 (sections 17): The webhook retry schedule adds up to 12 attempts within 72 hours under either reading of the intervals, and the dead-letter store, replay and 30-day retention line up with Section 19.1 and the FR-12 acceptance test.
  - p.13 §17: "up to 72 hours from first attempt (12 attempts including the first)."
- SA-009 (sections 26): Every FR and NFR in Section 2 has a named validation method and a pass/fail criterion. Most are concrete and measurable (for example NFR-9 noisy-neighbour at 3× the limit with ≤5% p99 shift), which gives the build a usable test baseline. The exceptions are covered in FND-004, FND-013 and FND-014. (see FND-018, FND-027, FND-034)
  - p.20 §26.2: "One merchant at 3× its rate limit does not move other merchants' p99 by more than 5%."
- SA-010 (sections 21.2): The Aurora write-capacity claim rests on a measured test at 2,600 TPS (above the 2,000 TPS NFR-1 target) on a smaller instance than production. The row-write and MSK ingress arithmetic (9 × 2,000 ≈ 18,000 rows/s; 6 × 1.8 KB × 2,000 = 21.6 MB/s) is correct, so the NFR-1 capacity claims for these stores are supported.
  - p.17 §21.2: "At 2,000 TPS that is about 18,000 row writes per second."
  - p.17 §21.2: "db.r7g.8xlarge sustained 2,600 TPS of the full write mix for two hours at 58% writer CPU with commit latency"
- SA-011 (sections 17): The webhook retry schedule adds up correctly. The cumulative retries (1 m, 6 m, 21 m, 1 h 21 m, 4 h 21 m, 10 h 21 m, then five 12-hour steps to about 70 h 21 m) give exactly 12 attempts within 72 hours, matching the FR-12 acceptance test.
  - p.13 §17: "exponential backoff at approximately 1 min, 5 min, 15 min, 1 h, 3 h, 6 h, then every 12 h, up to 72 hours from"
- SA-012 (sections 14.1, 14.2, 14.3): The ledger invariants, same-transaction journaling and balance projection meet FR-10 and P1/P5, and the worked examples balance. (see FND-058)
  - p.11 §14.1: "is valid only if, for each currency, the sum of debit postings equals the sum of credit postings."
- SA-013 (sections 17): Webhook delivery has per-endpoint signing secrets, timestamped HMAC, SSRF and DNS-rebinding protection by resolving and checking the address at send time, and per-endpoint in-flight caps and circuit breakers. This meets FR-12 and stops one merchant's failing endpoint degrading others (NFR-9).
  - p.13 §17: "time, refuses private, loopback, link-local and cloud-metadata addresses, and connects to the validated"
  - p.13 §17: "Isolation. Each endpoint has a cap of 20 in-flight deliveries and its own circuit breaker, so a failing endpoint"
- SA-014 (sections 18.5): Internal back-office access uses SSO with hardware-key MFA, is read-only on masked data by default, and requires just-in-time elevation with a second approver and an audit reason for money-moving actions. This applies P9 and P10 to staff access. (see FND-052)
  - p.14 §18.5: "data by default; write actions (manual refunds, payout holds, merchant suspension) require just-in-time elevation"
- SA-015 (sections 14.3, 19, 20.4): Ledger atomicity, database-enforced append-only postings, the asynchronous balance projection with nightly verification, and outbox buffering during MSK outages meet FR-10, P5 and P7 under partial failure. (see FND-058)
  - p.12 §14.3: "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them,"
- SA-016 (sections 21.2): The Aurora writer capacity rests on a measured spike: 2,600 TPS of the full write mix for two hours on a smaller instance class than production. This gives credible headroom for NFR-1's 2,000 TPS.
  - p.17 §21.2: "db.r7g.8xlarge sustained 2,600 TPS of the full write mix for two hours at 58% writer CPU with commit latency"
- SA-017 (sections 6): Secret API keys are shown once and stored only as hashes, and publishable keys are limited to tokenise and confirm. This limits exposure if the credential store leaks, consistent with P8 and P9.
  - p.6 §6: "Secret API keys are displayed once and stored only as a SHA-256 hash with a visible prefix."

## Unresolved issues and next steps

- FND-046 (governance decision): Fraud Hook detokenises PAN with the Card Adapter's role and sends it to FRV-1, outside the declared CDE (FND-046) Next step (PCI compliance lead with the Payments Core architect and the Head of Risk): Choose option (a) or (b) and agree the CDE scope with the QSA before Phase 2 (CDE build) and Phase 8 (Fraud Hook) start.
- FND-032 (needs investigation): CVC retention until settlement relies on an unverified reading of PCI DSS (FND-032) Next step (PCI DSS compliance lead with the QSA): Get a written interpretation of the CVC retention model in 12.4, including the cascade and incremental-authorization cases, before Phase 2 (CDE) build starts.
- FND-049 (governance decision): Zero RPO on region loss cannot hold with async replication, and idempotency state cannot be rebuilt (FND-049) Next step (Head of Platform Engineering with the Finance risk owner): Decide the RPO restatement or the synchronous design, and approve the payment schema change before Phase 3.
- FND-017 (governance decision): Go-live comes before fraud scoring, PCI assessment and load/DR validation (FND-017) Next step (Head of Payments Engineering with Risk and Compliance leads): Decide the go-live gate and record any interim risk acceptance in Section 28.
- FND-034 (needs investigation): DynamoDB capacity claims for idempotency keyed by merchant_id are unverified (FND-034) Next step (Payments Core tech lead): Check the DynamoDB limits against AWS documentation and run a single-tenant hot-key load test on the current key schema before Phase 3.
- FND-027 (needs testing): FR-5 acceptance test omits concurrency, cross-merchant and crash cases (FND-027) Next step (QA lead, Payments Core): Add the concurrent, cross-merchant and crash-injection cases to the FR-5 test design.
- FND-055 (governance decision): Fraud fallback accepts LOW and MEDIUM merchant payments unscored, with no limit or risk owner (FND-055) Next step (Head of Risk): Approve the fallback policy and caps, and make the FRV-1 SLA terms consistent with them before Phase 8.
- FND-057 (needs investigation): No cross-border transfer or retention analysis for personal data sent to Singapore, Jakarta DR and FRV-1 (FND-057) Next step (Data Protection Officer): Run a cross-border transfer and retention assessment for the five markets and FRV-1, and report constraints on data placement before Phase 3.
- FND-043 (needs investigation): Single-region Singapore hosting assumed permissible under all five markets' payment regulation (FND-043) Next step (Head of Compliance with market legal counsel): Confirm, per market, whether payment transactions and records may be processed and stored in Singapore and replicated to Jakarta.

Research questions left unanswered:
- RQ-012: Does PCI DSS v4.0 (Requirements 3.2.1, 3.3.1/3.3.1.2, 3.3.2) allow a merchant or service provider to keep the card verification code in encrypted form after authorization until settlement? Or must sensitive authentication data be deleted once authorization completes, except for issuers?
- RQ-013: What are DynamoDB's actual per-partition write limit (the document claims 10,000 WCU/s), the WCU cost of items of up to about 4 KB, the 10 GB item-collection limit for tables with a local secondary index, and TTL deletion delay? Given these, does keying by merchant_id with an LSI support the largest merchant at about 900 TPS and about 4.7M requests a day?
- RQ-014: What are the Visa and Mastercard reattempt rules? Specifically: Visa decline categories and limits per card over 30 days, Mastercard Merchant Advice Codes such as 03/21/24-30, whether response 05 counts as retryable, and whether resubmitting to a different acquirer after a soft decline counts toward, or is restricted by, these rules.
- RQ-015: How does Aurora Global Database actually behave? Specifically: its RPO for an unplanned cross-region failover compared with a managed switchover, typical replication lag under heavy write load (about 18,000 row writes/s), and the realistic time to promote the secondary.
- RQ-016: Does the IETF HTTPAPI Idempotency-Key header draft actually specify 409 for an in-flight duplicate, 422 for payload mismatch and 400 for a missing key? Is 24-hour retention stated in the cited reference practice?
- RQ-020: Do the markets' data protection and payment-system rules (Indonesia Law 27/2022, GR 71/2019 and Bank Indonesia payment-system data localisation; cross-border transfer rules in Malaysia, Thailand and the Philippines) allow processing all data in Singapore, replicating DR to Jakarta, and sharing card and identity data in FRV-1's cross-client consortium?
- RQ-022: Does the single-HSM CDE hold at load and under failure? Points to check: AWS guidance on a minimum HSM count across AZs for production, the time to create an HSM from backup, the risk of losing keys created since the last backup, per-HSM operation throughput compared with about 1,100 card TPS (doubled if the Fraud Hook also detokenises), and the second-HSM trigger at 1,500 card TPS, which 55%×2,000 TPS never reaches.
- RQ-023: Do the remaining components hold at campaign peak? Points to check: whether DynamoDB on-demand absorbs a jump from baseline to 2,000 TPS without throttling; whether three kafka.m7g.xlarge brokers sustain 21.6 MB/s ingress with RF3; whether a 20-in-flight cap per webhook endpoint drains events for a 900-TPS merchant; and whether the Aurora test (2 hours on a smaller instance) supports the 4-hour NFR-1.
- RQ-025: Is running 3DS before routing, then cascading to a different acquirer, valid? Does a 3DS authentication result (CAVV/ECI) obtained under one acquirer's merchant and acquirer BIN stay valid, and keep its liability shift, when the authorization goes to a second acquirer?

## Evidence limitations

- DOC-design_v1: native PDF block not sent because the configured model backend accepts text only. Impact: figures, diagrams and tables rendered as images were not visible to the model; the review is based on the extracted text (DEG-001)
- No external research was possible: no tool gateway (--no-tools, or every server is disabled). Impact: doc-only review: every question that needs external evidence is reported as a validation need, and confidence is lowered (DEG-002)
- FND-049's recommendation appears to reverse approved decision AD-006 (24 Idempotency store) without a 'challenges' label. Impact: the conflict is not declared and not backed by the two evidence items a challenge needs; check it against the decision before acting on it (DEG-003)
- FND-047's recommendation appears to reverse approved decision AD-011 (24 Cascade policy) without a 'challenges' label. Impact: the conflict is not declared and not backed by the two evidence items a challenge needs; check it against the decision before acting on it (DEG-004)
- FND-029's recommendation appears to reverse approved decision AD-012 (24 Routing) without a 'challenges' label. Impact: the conflict is not declared and not backed by the two evidence items a challenge needs; check it against the decision before acting on it (DEG-005)

## Evidence register

| ID | Type | Source | Retrieved | Cited |
|---|---|---|---|---|
| EV-001 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-002 | doc | doc:DOC-design_v1#p4/s3 | - | yes |
| EV-003 | doc | doc:DOC-design_v1#p7/s9.1 | - | yes |
| EV-004 | doc | doc:DOC-design_v1#p11/s13.1 | - | no |
| EV-005 | doc | doc:DOC-design_v1#p10/s12.2 | - | yes |
| EV-006 | doc | doc:DOC-design_v1#p10/s12.1 | - | yes |
| EV-007 | doc | doc:DOC-design_v1#p16/s20.2 | - | no |
| EV-008 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-009 | doc | doc:DOC-design_v1#p16/s20.2 | - | no |
| EV-010 | doc | doc:DOC-design_v1#p17/s21.1 | - | no |
| EV-011 | doc | doc:DOC-design_v1#p9/s10.5 | - | yes |
| EV-012 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-013 | doc | doc:DOC-design_v1#p9/s11.1 | - | yes |
| EV-014 | doc | doc:DOC-design_v1#p12/s16.1 | - | yes |
| EV-015 | doc | doc:DOC-design_v1#p13/s16.2 | - | no |
| EV-016 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-017 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-018 | doc | doc:DOC-design_v1#p21/s28 | - | no |
| EV-019 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-020 | doc | doc:DOC-design_v1#p3/s2.1 | - | yes |
| EV-021 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-022 | doc | doc:DOC-design_v1#p10/s12.4 | - | no |
| EV-023 | doc | doc:DOC-design_v1#p18/s24 | - | yes |
| EV-024 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-025 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-026 | doc | doc:DOC-design_v1#p10/s12.1 | - | yes |
| EV-027 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-028 | doc | doc:DOC-design_v1#p8/s9.3 | - | yes |
| EV-029 | doc | doc:DOC-design_v1#p8/s9.3 | - | no |
| EV-030 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-031 | doc | doc:DOC-design_v1#p14/s18.4 | - | yes |
| EV-032 | doc | doc:DOC-design_v1#p14/s18.4 | - | yes |
| EV-033 | doc | doc:DOC-design_v1#p4/s3 | - | yes |
| EV-034 | doc | doc:DOC-design_v1#p14/s18.3 | - | yes |
| EV-035 | doc | doc:DOC-design_v1#p18/s24 | - | yes |
| EV-036 | doc | doc:DOC-design_v1#p19/s25 | - | yes |
| EV-037 | doc | doc:DOC-design_v1#p20/s27 | - | yes |
| EV-038 | doc | doc:DOC-design_v1#p3/s2.1 | - | yes |
| EV-039 | doc | doc:DOC-design_v1#p18/s24 | - | yes |
| EV-040 | doc | doc:DOC-design_v1#p12/s14.3 | - | yes |
| EV-041 | doc | doc:DOC-design_v1#p7/s7.2 | - | yes |
| EV-042 | doc | doc:DOC-design_v1#p16/s19 | - | yes |
| EV-043 | doc | doc:DOC-design_v1#p2/s2 | - | yes |
| EV-044 | doc | doc:DOC-design_v1#p3/s3 | - | yes |
| EV-045 | doc | doc:DOC-design_v1#p19/s25 | - | yes |
| EV-046 | inference | inference:EV-046 from EV-001, EV-002, EV-003 | - | yes |
| EV-047 | inference | inference:EV-047 from EV-004, EV-005, EV-006 | - | no |
| EV-048 | inference | inference:EV-048 from EV-007, EV-008, EV-009 | - | no |
| EV-049 | inference | inference:EV-049 from EV-010, EV-011, EV-013 | - | no |
| EV-050 | inference | inference:EV-050 from EV-014, EV-015, EV-016, EV-017 | - | no |
| EV-051 | inference | inference:EV-051 from EV-018, EV-019, EV-020 | - | yes |
| EV-052 | inference | inference:EV-052 from EV-021, EV-022, EV-023 | - | no |
| EV-053 | inference | inference:EV-053 from EV-024, EV-025, EV-026, EV-027 | - | no |
| EV-054 | inference | inference:EV-054 from EV-028, EV-029, EV-030 | - | no |
| EV-055 | inference | inference:EV-055 from EV-031, EV-032, EV-034 | - | no |
| EV-056 | inference | inference:EV-056 from EV-035, EV-036, EV-037 | - | yes |
| EV-057 | inference | inference:EV-057 from EV-038, EV-039 | - | no |
| EV-058 | doc | doc:DOC-design_v1#p8/s9.2 | - | no |
| EV-059 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-060 | doc | doc:DOC-design_v1#p4/s3 | - | no |
| EV-061 | doc | doc:DOC-design_v1#p7/s9.1 | - | no |
| EV-062 | doc | doc:DOC-design_v1#p11/s13.1 | - | yes |
| EV-063 | doc | doc:DOC-design_v1#p3/s3 | - | no |
| EV-064 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-065 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-066 | doc | doc:DOC-design_v1#p17/s21.1 | - | yes |
| EV-067 | doc | doc:DOC-design_v1#p20/s26.2 | - | yes |
| EV-068 | doc | doc:DOC-design_v1#p16/s20.2 | - | yes |
| EV-069 | doc | doc:DOC-design_v1#p17/s20.2 | - | no |
| EV-070 | doc | doc:DOC-design_v1#p20/s26.2 | - | yes |
| EV-071 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-072 | doc | doc:DOC-design_v1#p13/s16.2 | - | no |
| EV-073 | doc | doc:DOC-design_v1#p9/s11.2 | - | no |
| EV-074 | doc | doc:DOC-design_v1#p9/s11.2 | - | no |
| EV-075 | doc | doc:DOC-design_v1#p2/s2.1 | - | yes |
| EV-076 | doc | doc:DOC-design_v1#p6/s7.2 | - | yes |
| EV-077 | doc | doc:DOC-design_v1#p6/s7.2 | - | yes |
| EV-078 | doc | doc:DOC-design_v1#p9/s11.4 | - | yes |
| EV-079 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-080 | doc | doc:DOC-design_v1#p7/s8 | - | yes |
| EV-081 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-082 | doc | doc:DOC-design_v1#p16/s20.1 | - | yes |
| EV-083 | doc | doc:DOC-design_v1#p2/s1 | - | yes |
| EV-084 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-085 | doc | doc:DOC-design_v1#p14/s18.2 | - | yes |
| EV-086 | doc | doc:DOC-design_v1#p3/s2.2 | - | no |
| EV-087 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-088 | doc | doc:DOC-design_v1#p10/s12.4 | - | no |
| EV-089 | doc | doc:DOC-design_v1#p10/s12.4 | - | no |
| EV-090 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-091 | doc | doc:DOC-design_v1#p19/s26.1 | - | yes |
| EV-092 | doc | doc:DOC-design_v1#p2/s2.1 | - | yes |
| EV-093 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-094 | doc | doc:DOC-design_v1#p17/s20.3 | - | yes |
| EV-095 | doc | doc:DOC-design_v1#p8/s9.3 | - | no |
| EV-096 | doc | doc:DOC-design_v1#p8/s9.3 | - | no |
| EV-097 | doc | doc:DOC-design_v1#p8/s9.2 | - | no |
| EV-098 | doc | doc:DOC-design_v1#p20/s26.2 | - | no |
| EV-099 | doc | doc:DOC-design_v1#p9/s10.3 | - | yes |
| EV-100 | doc | doc:DOC-design_v1#p2/s2.1 | - | yes |
| EV-101 | doc | doc:DOC-design_v1#p9/s10.2 | - | yes |
| EV-102 | doc | doc:DOC-design_v1#p19/s26.1 | - | yes |
| EV-103 | doc | doc:DOC-design_v1#p3/s2.1 | - | yes |
| EV-104 | doc | doc:DOC-design_v1#p20/s26.1 | - | yes |
| EV-105 | doc | doc:DOC-design_v1#p6/s6 | - | yes |
| EV-106 | doc | doc:DOC-design_v1#p16/s19 | - | yes |
| EV-107 | doc | doc:DOC-design_v1#p11/s14.1 | - | yes |
| EV-108 | inference | inference:EV-108 from EV-058, EV-059, EV-060, EV-061 | - | no |
| EV-109 | inference | inference:EV-109 from EV-062, EV-006, EV-005, EV-063 | - | yes |
| EV-110 | inference | inference:EV-110 from EV-064, EV-019, EV-065, EV-020 | - | yes |
| EV-111 | inference | inference:EV-111 from EV-066, EV-011, EV-013, EV-012, EV-067 | - | yes |
| EV-112 | inference | inference:EV-112 from EV-008, EV-068, EV-069, EV-027 | - | no |
| EV-113 | inference | inference:EV-113 from EV-014, EV-071, EV-072 | - | no |
| EV-114 | inference | inference:EV-114 from EV-073, EV-074, EV-075 | - | yes |
| EV-115 | inference | inference:EV-115 from EV-076, EV-077, EV-078, EV-079, EV-080 | - | yes |
| EV-116 | inference | inference:EV-116 from EV-024, EV-081, EV-082, EV-083, EV-084 | - | yes |
| EV-117 | inference | inference:EV-117 from EV-085, EV-032, EV-034 | - | yes |
| EV-118 | inference | inference:EV-118 from EV-086, EV-087, EV-088, EV-089 | - | yes |
| EV-119 | inference | inference:EV-119 from EV-036, EV-035, EV-090, EV-037 | - | yes |
| EV-120 | inference | inference:EV-120 from EV-091, EV-092, EV-093, EV-094 | - | yes |
| EV-121 | inference | inference:EV-121 from EV-095, EV-096, EV-097, EV-098 | - | yes |
| EV-122 | inference | inference:EV-122 from EV-099, EV-100, EV-101, EV-102 | - | yes |
| EV-123 | inference | inference:EV-123 from EV-103, EV-104, EV-105 | - | yes |
| EV-124 | inference | inference:EV-124 from EV-040, EV-106, EV-107 | - | yes |
| EV-125 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-126 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-127 | doc | doc:DOC-design_v1#p19/s25 | - | yes |
| EV-128 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-129 | doc | doc:DOC-design_v1#p21/s28 | - | no |
| EV-130 | doc | doc:DOC-design_v1#p21/s27 | - | no |
| EV-131 | doc | doc:DOC-design_v1#p2/s1 | - | yes |
| EV-132 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-133 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-134 | doc | doc:DOC-design_v1#p8/s9.2 | - | no |
| EV-135 | doc | doc:DOC-design_v1#p17/s21.1 | - | no |
| EV-136 | doc | doc:DOC-design_v1#p5/s5 | - | yes |
| EV-137 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-138 | doc | doc:DOC-design_v1#p11/s14.1 | - | yes |
| EV-139 | inference | inference:EV-139 from EV-125, EV-021, EV-126 | - | yes |
| EV-140 | inference | inference:EV-140 from EV-004, EV-005, EV-127 | - | no |
| EV-141 | inference | inference:EV-141 from EV-028, EV-030, EV-128 | - | yes |
| EV-142 | inference | inference:EV-142 from EV-129, EV-065 | - | yes |
| EV-143 | inference | inference:EV-143 from EV-010, EV-011, EV-013 | - | no |
| EV-144 | inference | inference:EV-144 from EV-008, EV-068 | - | yes |
| EV-145 | inference | inference:EV-145 from EV-014, EV-016, EV-131 | - | yes |
| EV-146 | inference | inference:EV-146 from EV-132, EV-133 | - | yes |
| EV-147 | inference | inference:EV-147 from EV-134, EV-003 | - | no |
| EV-148 | inference | inference:EV-148 from EV-024, EV-135, EV-083 | - | no |
| EV-149 | inference | inference:EV-149 from EV-136, EV-137 | - | yes |
| EV-150 | inference | inference:EV-150 from EV-138 | - | yes |
| EV-151 | doc | doc:DOC-design_v1#p8/s9.2 | - | no |
| EV-152 | doc | doc:DOC-design_v1#p11/s13.1 | - | yes |
| EV-153 | doc | doc:DOC-design_v1#p11/s13.1 | - | yes |
| EV-154 | doc | doc:DOC-design_v1#p3/s3 | - | yes |
| EV-155 | doc | doc:DOC-design_v1#p5/s5 | - | yes |
| EV-156 | doc | doc:DOC-design_v1#p16/s20.2 | - | yes |
| EV-157 | doc | doc:DOC-design_v1#p17/s20.2 | - | yes |
| EV-158 | doc | doc:DOC-design_v1#p17/s20.2 | - | yes |
| EV-159 | doc | doc:DOC-design_v1#p8/s9.3 | - | yes |
| EV-160 | doc | doc:DOC-design_v1#p2/s1 | - | yes |
| EV-161 | doc | doc:DOC-design_v1#p10/s12.4 | - | no |
| EV-162 | doc | doc:DOC-design_v1#p14/s18.3 | - | yes |
| EV-163 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-164 | doc | doc:DOC-design_v1#p11/s13.2 | - | yes |
| EV-165 | doc | doc:DOC-design_v1#p4/s3 | - | yes |
| EV-166 | doc | doc:DOC-design_v1#p8/s9.2 | - | no |
| EV-167 | doc | doc:DOC-design_v1#p17/s20.3 | - | no |
| EV-168 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-169 | doc | doc:DOC-design_v1#p16/s19.1 | - | yes |
| EV-170 | doc | doc:DOC-design_v1#p11/s13.1 | - | yes |
| EV-171 | doc | doc:DOC-design_v1#p17/s20.4 | - | yes |
| EV-172 | inference | inference:EV-172 from EV-151, EV-001, EV-003 | - | yes |
| EV-173 | inference | inference:EV-173 from EV-153, EV-005, EV-155 | - | yes |
| EV-174 | inference | inference:EV-174 from EV-133, EV-132, EV-013 | - | yes |
| EV-175 | inference | inference:EV-175 from EV-024, EV-026, EV-025 | - | yes |
| EV-176 | inference | inference:EV-176 from EV-008, EV-068, EV-157 | - | yes |
| EV-177 | inference | inference:EV-177 from EV-158 | - | yes |
| EV-178 | inference | inference:EV-178 from EV-159, EV-030, EV-160 | - | yes |
| EV-179 | inference | inference:EV-179 from EV-161, EV-022 | - | yes |
| EV-180 | inference | inference:EV-180 from EV-031, EV-032, EV-162 | - | yes |
| EV-181 | inference | inference:EV-181 from EV-010, EV-011, EV-012 | - | no |
| EV-182 | inference | inference:EV-182 from EV-163, EV-016, EV-014, EV-131 | - | yes |
| EV-183 | inference | inference:EV-183 from EV-164, EV-020, EV-165 | - | yes |
| EV-184 | inference | inference:EV-184 from EV-166, EV-167, EV-168 | - | yes |
| EV-185 | inference | inference:EV-185 from EV-137, EV-169, EV-170, EV-127 | - | yes |

## Review coverage

| Criterion | Outcome | Findings | Note |
|---|---|---|---|
| design_intent | findings | FND-014, FND-029, FND-026 | Objectives, the volume baseline, FR/NFR IDs, principles, confirmed decisions, backlog and the readiness table are explicit and traceable. Main clarity defects: the unit and scope of the FR-8 tolerance, and a confirmed decision that depends on an unrecorded pending item. |
| fitness_for_objectives | findings | FND-001, FND-046, FND-049, FND-018, FND-054, FND-017, FND-032, FND-048, FND-034, FND-052, FND-058 | Checked idempotency, CDE scoping, DR, the latency budget, reconciliation timing, the build phase order against FR-9, SAD handling, HSM availability, DynamoDB capacity and payout-account control. Several requirements (FR-5, NFR-2, NFR-4, NFR-5, NFR-8, FR-9) cannot be met as written. The ledger, money handling and webhooks are fit for purpose. |
| requirement_completeness | findings | FND-017, FND-047, FND-022, FND-048, FND-052, FND-027, FND-030 | Checked error and rollback paths (cascade timeouts, idempotency crash recovery, HSM loss, late settlement files), missing controls (payout-account changes), go-live gating against requirements, and the backlog in Section 25. Disputes are acknowledged as out of scope and backlog, so no finding was raised for them. |
| internal_consistency | findings | FND-001, FND-046, FND-017, FND-018, FND-049, FND-054, FND-022, FND-048, FND-052, FND-032, FND-026, FND-029, FND-058 | Cross-checked principles P1–P10 against component designs, the NFR numbers against the Section 16, 20 and 21 figures (timezone and latency arithmetic, RPO, availability), the CDE scope against data flows, and readiness and phase tables against the backlog. |
| claims_and_external_constraints | findings | FND-032, FND-046, FND-034, FND-018, FND-049, FND-054, FND-047, FND-048, FND-043, FND-058 | Checked the PCI DSS citations and CDE scope claims, the DynamoDB/CloudHSM/Aurora platform claims, the latency budget, the RPO claim, reconciliation timing arithmetic, cascade duplicate-safety, the volume baseline, MSK/Aurora capacity arithmetic, the webhook schedule and the ledger examples. The baseline, capacity, webhook and ledger arithmetic is consistent. The PCI and DynamoDB external premises need confirmation. |
| security_and_privacy | findings | FND-001, FND-046, FND-032, FND-052, FND-057, FND-058 | Checked: CDE scoping and detokenise access, SAD retention, idempotency tenant isolation, merchant admin authentication and payout controls, webhook and API key secrets, audit and privacy obligations. Material gaps are the cross-merchant idempotency leak, PAN reaching the Fraud Hook and FRV-1, the CVC retention claim, payout-account takeover, and the cross-border privacy analysis. |
| scalability_and_failure_modes | findings | FND-047, FND-048, FND-049, FND-034, FND-018, FND-054, FND-027, FND-058, FND-001, FND-055 | Checked: cascade and timeout semantics, HSM redundancy, regional DR and RPO, DynamoDB hot-key capacity, the p99 latency budget, reconciliation timing, crash recovery of idempotency locks, Aurora and MSK capacity, and dependency degradation. |
| assumptions_and_dependencies | findings | FND-046, FND-017, FND-001, FND-048, FND-026, FND-043 | Checked the pending backlog items against the confirmed decisions, the readiness assessment and the build phases. Found untracked dependencies: go-live ahead of PCI assessment and fraud scoring, network tokens depending on an unsubmitted TRID, FRV-1 receiving PAN under a pending contract, globally unique idempotency keys, and the regulatory basis for single-region hosting. Backlog items 3, 5 and 7 are tracked adequately. |
| verifiability | findings | FND-018, FND-049, FND-054, FND-047, FND-032, FND-027, FND-034, FND-029, FND-022, FND-058 | Checked each Section 26 criterion against its requirement. FR-5, FR-8, NFR-1, NFR-2, NFR-4 and NFR-6 either cannot demonstrate their requirement as written or would fail against the design. FR-10, FR-12 and NFR-9 are adequate. |
| decision_preservation | findings | FND-049, FND-048, FND-032, FND-026, FND-001, FND-046, FND-017, FND-058 | Findings that challenge approved decisions: Aurora Global DR against zero RPO (FND-003), and one HSM at launch against NFR-3 (FND-008). Both rest on at least two document evidence items. The CVC retention decision is framed as an unresolved assumption pending QSA confirmation. Refinements that keep decisions in place: the idempotency key schema (FND-001) and network tokens from launch (FND-011). |
| operability_and_governance | findings | FND-048, FND-049, FND-054, FND-055, FND-057 | Checked: DR runbook coverage, ownership of the reconciliation exception queue, the late-file policy, fraud fail-open risk acceptance, and vendor and privacy governance gates relative to the build phases. Several decisions need a named accountable owner before the phases that depend on them. |

## Run details

| | |
|---|---|
| Run | rehearsal_concurrent_high_1 (started 2026-10-03T02:24:30Z) |
| Outcome | completed_degraded |
| Model | requested claude-opus-5-5; served claude-opus-5-5; effort high |
| Persona | generalist_architect |
| Tool transport | live |
| Research stop | tool_failure (error): no_tools; 0 iteration(s); 0 cited of 0 retrieved |
| Tool calls | none |
| Tokens | input 378856, cached 71971, output 258222; cost ~$8.21 (price table 2026-09-25) |
| Extractor | pdfplumber 0.11.10 |
| Config sha256 | 95b957550fca570e914da5c56c6675e597e4fd699b33d680e12206ac8b428d66 |
| Prompt bundle sha256 | 6f0ee28ab9acf35152a2d4456207a8a068222149422e66d801c8195455c28ba7 |
| Git commit | 70bd6588c8920a7dc47888ece8b940aba36eeb6c |
| Fault schedule | none |
| Model fallbacks | 0 |
| Canonical text DOC-design_v1 | sha256 ad0bb891f073f14325b6ba716d58070d6b074ebaef9a9c64432138b89b64ec3c |
