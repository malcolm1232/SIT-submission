# Design review: Serindit Pay — Merchant Payment Orchestration Platform

| | |
|---|---|
| Review | REV-rehearsal_concurrent_1 (full review) |
| Under review | DOC-design_v1: Serindit Pay — Merchant Payment Orchestration Platform v1.0, 21 pages |
| Verdict | **not fit** (confidence 0.78, medium) |
| Tools used | none |
| Tools disabled | mcp-internet-search, mcp-research-information, mcp-browser-automation-pw, mcp-document-intelligence |
| Reporting threshold | severity low and above (0 finding(s) in the appendix) |

> No external research was possible or used in this run: every finding rests on the document alone.


## Design intent

The Serindit Pay Merchant Payment Orchestration Platform (MPOP) takes payment requests from merchants. It routes each one to an acquirer, e-wallet provider or bank-transfer rail and accounts for every resulting movement of money until it is settled to the merchant. It replaces five per-market integration stacks with one merchant API across five Southeast Asian markets (SG, MY, ID, TH, PH). In scope are payment acceptance, routing and cascading, idempotency, a PCI-scoped card vault, a synchronous fraud hook, a double-entry ledger, daily reconciliation, payouts, signed webhooks and a merchant admin plane, sized for about 15,000 merchants and a peak of 2,000 TPS. Disputes case management, KYB, 3DS server internals, and lending/BNPL are out of scope.

Objectives:
- Replace five per-market integration stacks that share no routing or ledger and reconcile by spreadsheet with one governed platform.
- Provide one versioned merchant API across five markets for about 15,000 active merchants at a peak of 2,000 payment-creation TPS (2027 target).
- Confine PCI DSS scope to a small CDE enclave (Vault Edge, Card Vault, CloudHSM, Card Adapter) through tokenisation.
- P1: One payment, one truth: the payment record and the ledger are the source of truth; provider responses are only inputs.
- P2: Card data stays in the Vault: PAN and sensitive authentication data never leave the Vault boundary except over the Card Adapter's acquirer connection.
- P3: Idempotency is scoped to (merchant, key) for every mutating call.
- P4: Money is integers: amounts are integer minor units with an ISO 4217 code, and no floating point is used.
- P5: The ledger is append-only, and corrections are new reversing or adjusting journals.
- P6: Adapters absorb provider differences, and the core never branches on provider identity.
- P7: At-least-once delivery with exactly-once effect through consumer deduplication on stable identifiers.
- P8: Fail closed on security and degrade gracefully on optional enrichment to documented defaults.
- P9: Least privilege and separation of duties; money-moving permissions are separated from configuration permissions.
- P10: Everything is auditable: every mutation, routing decision and admin action can be reconstructed.

Constraints:
- NFR-5: The platform must be assessed as a PCI DSS v4.0 Level 1 service provider, with the CDE limited to the Section 12.2 components.
- NFR-6: Sensitive authentication data must be handled per PCI DSS v4.0 Requirements 3.2.1 and 3.3.2.
- NFR-7: Personal data must be processed under SG PDPA 2012, MY PDPA 2010, ID Law 27/2022, TH PDPA 2019 and PH DPA 2012.
- FR-7: Card reattempts must never occur where card scheme rules prohibit them.
- NFR-4: RPO is zero for authorized payments and ledger postings, including on loss of a whole AWS region, and RTO is 30 minutes.
- NFR-12: Audit records must be immutable and kept for five years.
- The ten foundational principles override any later section that appears to conflict with them.
- All primary data stores are in AWS ap-southeast-1, and ap-southeast-3 is used for DR only.
- Financial records are retained for 7 years and idempotency records for 24 hours.
- ACQ-PH1 API v2 retires in Q3 2027, so the adapter must migrate to v3 before then.

Key assumptions:
- The 2027 volume baseline holds: 10.5 M attempts per day, 2,000 peak TPS, and the largest single merchant at 45% of peak (about 900 TPS).
- Fewer than 1% of card payments cascade, so cascading does not move the p99 latency; retryable outcomes were 3.8% in 2025.
- The slowest acquirer's p99 round trip is 1,100 ms (2025 production), and the summed component p99 budget is 1,338 ms.
- A single DynamoDB partition sustains up to 10,000 WCU per second, so per-merchant partition keying fits the largest merchant.
- PCI DSS v4.0 Requirements 3.2.1 and 3.3.2 allow encrypted CVC to be retained until settlement (at most 72 hours).
- FRV-1 needs the full PAN for its consortium velocity graph, and the Fraud Hook (declared out of CDE scope) obtains it through detokenise.
- One CloudHSM at launch, restorable from daily backups, is enough until sustained card volume exceeds 1,500 TPS.
- Aurora Global Database replication lag is typically under one second, and in-flight idempotency state can be rebuilt from the payment table after failover.
- An Aurora spike test (db.r7g.8xlarge, 2,600 TPS for 2 h at 58% CPU) shows enough headroom on db.r7g.12xlarge.
- Network tokens can be used from launch, although Token Requestor registration has not yet been submitted.
- The first merchant cohort (SG cards and PayNow) can go live using the portal, with disputes handled manually by Finance Operations.
- ACQ-SG2 is licensed in all five markets and acts as the default cascade secondary.

Located at: p.1 §1, p.2 §1 (2 passages).

## Fitness for purpose

**Not fit** (confidence 0.78). As written, the design is not fit for its stated purpose, which is to be a document an engineering team can begin building from. The main reason is one open critical finding. FND-001: the Redis idempotency fast path is not scoped to the merchant and skips the body-hash check. That breaks P3 and FR-5, and can disclose one merchant's payment data to another and silently lose payments. Ten open high findings strike at core objectives: - FND-002 and FND-029 conflict with P2, NFR-5 and the PCI DSS scoping objective (PAN detokenised by the Fraud Hook; CVC kept after authorization on a cited allowance that appears not to exist). - FND-004 makes zero RPO under NFR-4 unachievable with asynchronous replication. - FND-006 leaves a single HSM as a single point of failure for every card payment, which threatens NFR-3. - FND-005 shows the latency budget leaves out cascades, so the design likely fails its own NFR-2 test. - FND-020 shows the NFR-8 08:00 SGT report deadline cannot be met. - FND-016 shows a timeout cascade can create duplicate authorizations. - FND-021 sends live card traffic before fraud scoring, the PCI assessment and acceptance testing. - FND-046 opens a payout-redirection path to financial loss. Several of these need decisions by an accountable owner, not just text edits: FND-002, FND-004, FND-006 and FND-021 challenge or refine approved decisions on the Fraud Hook, disaster recovery, the HSM and phasing. Section 27 overstates readiness (FND-012). There are real strengths: the transactional, append-only ledger (FND-013), clear traceability of requirements and principles (FND-014), and webhook isolation and SSRF controls (FND-053). The overall structure is sound, and most defects can be fixed within it. Limits on this verdict: - The review was doc-only (DEG-002). No external sources were available, so PCI DSS clause wording (FND-029), DynamoDB partition and LSI limits (FND-009), scheme reattempt rules (FND-039) and data-localisation law (FND-051) are unverified. - Figures and tables were read from extracted text only (DEG-001). - FND-009's recommendation may reverse the approved idempotency-store decision without declaring a challenge (DEG-003), so it was given little weight. The not_fit verdict does not depend on these unverified items. FND-001, FND-002, FND-004, FND-005, FND-020 and FND-016 rest only on contradictions inside the document, or on the document's own figures and arithmetic.

| Objective | Verdict | Findings |
|---|---|---|
| Objective: replace five per-market stacks with one governed platform | fit with conditions | FND-013, FND-014, FND-020, FND-012 |
| Objective: one versioned merchant API, 15,000 merchants, 2,000 TPS peak | not fit | FND-001, FND-005, FND-009, FND-022, FND-023 |
| Objective: confine PCI DSS scope to a small CDE enclave | not fit | FND-002, FND-029, FND-006, FND-021 |
| P1 | fit with conditions | FND-013, FND-016, FND-004 |
| P2 | not fit | FND-002, FND-029 |
| P3 | not fit | FND-001, FND-023 |
| P4 | fit | - |
| P5 | fit | FND-013 |
| P6 | fit | - |
| P7 | fit with conditions | FND-053, FND-004, FND-016 |
| P8 | fit with conditions | FND-021 |
| P9 | fit with conditions | FND-046, FND-002 |
| P10 | fit | FND-014 |

What would change this verdict: The verdict would move to fit_with_conditions if a revised design did all of the following: - Scopes the Redis fast-path key to (merchant_id, key) and checks the request hash there (FND-001). - Removes PAN detokenisation from the Fraud Hook, or formally brings the hook into the CDE with its own role (FND-002). - Confirms through a QSA or the PCI DSS v4.0 text that CVC retention after authorization is allowed, or removes it (FND-029). - Either accepts a non-zero RPO in NFR-4 or adds synchronous cross-region replication and replicated idempotency state (FND-004). - Deploys at least two HSMs across AZs at launch (FND-006). - Re-budgets NFR-2 to include cascades (FND-005). - Makes the NFR-8 schedule feasible and defines behaviour for late files (FND-020). - Adds void/reversal handling for late approvals after a timeout (FND-016). - Reorders go-live after the Fraud Hook and the PCI and acceptance gates (FND-021). - Adds dual approval, owner notification and enforced MFA for payout-account changes (FND-046). With those fixes, the remaining medium findings would become conditions. Evidence that the cited PCI DSS clauses really do allow post-authorization SAD storage would downgrade FND-029. The verdict would be confirmed, or made firmer, by external checks of the DynamoDB partition and LSI limits (FND-009) and of scheme reattempt rules (FND-039).

## Strengths

### FND-013 Ledger is written in the same transaction as state changes, append-only and enforced by database roles

- **strength** · confidence 0.85 (high) · rank 19
- Disposition: **no change**

Section 14.3 writes the state transition, the journal and the outbox row in one PostgreSQL transaction, so there is no dual write. Section 19 revokes UPDATE and DELETE on journal and posting from all application roles, and balances are an asynchronous projection checked nightly. This directly serves FR-10, P1, P5 and P7, and avoids hot-row contention at 2,000 TPS.

- Where: p.12 §14.3 (FR-10): "• Journals are written in the same PostgreSQL transaction as the payment state transition that causes them,"
- Where: p.16 §19 (FR-10): "journal and posting have UPDATE and DELETE revoked from every application role"
- Evidence EV-037 (doc, supports): "• Journals are written in the same PostgreSQL transaction as the payment state transition that causes them," [doc:DOC-design_v1#p12/s14.3]
- Evidence EV-038 (doc, supports): "journal and posting have UPDATE and DELETE revoked from every application role" [doc:DOC-design_v1#p16/s19]
- Evidence EV-117 (doc, supports): "There is no dual write between the payment store and the ledger." [doc:DOC-design_v1#p12/s14.3]
- Evidence EV-086 (inference, supports): "The Section 14.2 capture, settlement and payout journals each balance in minor units, consistent with the per-currency invariant." [inference:EV-086] derived from EV-077
- Why no change is needed: Atomic state, journal and outbox writes, append-only enforcement through database privileges, and a projection checked against postings meet FR-10 and principles P1, P5 and P7 without further change.
- Decision AD-014 (24 Confirmed Decisions - Ledger): preserves. Affirms the approved design: a same-transaction, append-only ledger with an outbox.
- Decision AD-044 (FR-10): preserves. Serves FR-10.

### FND-014 Intent is explicit: requirement IDs, ranked principles and a confirmed-decision register

- **strength** · confidence 0.80 (high) · rank 20
- Disposition: **no change**

The design states numbered FR and NFR requirements traced to Section 26 acceptance criteria and to Section 27 readiness. It sets ten principles with an explicit precedence rule, and it lists confirmed decisions and a pending backlog. This makes the design reviewable against its own intent, and is what allowed the conflicts above to be identified.

- Where: p.3 §3: "These ten principles govern every design decision in the platform. Where a later section appears to conflict with one of"
- Where: p.2 §2: "Each requirement carries an ID used again in Section 26 (Validation and Acceptance Criteria) and Section 27"
- Evidence EV-039 (doc, supports): "These ten principles govern every design decision in the platform. Where a later section appears to conflict with one of" [doc:DOC-design_v1#p3/s3]
- Evidence EV-040 (doc, supports): "Each requirement carries an ID used again in Section 26 (Validation and Acceptance Criteria) and Section 27" [doc:DOC-design_v1#p2/s2]
- Why no change is needed: Objectives, principles, decisions and acceptance criteria are stated clearly enough, and with traceable IDs, to review against.
- Decision AD-034 (3 Foundational Principles): preserves. Affirms the precedence rule that the principles win over later sections.

### FND-053 Webhook dispatcher isolation and SSRF controls

- **strength** · confidence 0.80 (high) · rank 21
- Disposition: **no change**

Each endpoint has a 20-delivery in-flight cap and its own circuit breaker, so one merchant's failing endpoint cannot starve others. The dispatcher pins the validated resolved address and refuses private, loopback, link-local and metadata ranges. Together with timestamped HMAC signatures and a bounded retry plus DLQ, this meets FR-12 and protects the internal network.

- Where: p.13 §17 (FR-12): "refuses private, loopback, link-local and cloud-metadata addresses, and connects to the validated"
- Where: p.13 §17 (NFR-9): "Each endpoint has a cap of 20 in-flight deliveries and its own circuit breaker, so a failing endpoint"
- Evidence EV-119 (doc, supports): "refuses private, loopback, link-local and cloud-metadata addresses, and connects to the validated" [doc:DOC-design_v1#p13/s17]
- Evidence EV-120 (doc, supports): "Each endpoint has a cap of 20 in-flight deliveries and its own circuit breaker, so a failing endpoint" [doc:DOC-design_v1#p13/s17]
- Why no change is needed: Delivery isolation and DNS-pinned SSRF protection are specific and sufficient for FR-12 and NFR-9 at the stated merchant count.
- Decision AD-017 (24 Confirmed Decisions - Webhooks): preserves. Affirms the approved webhook delivery design.
- Decision AD-046 (FR-12): preserves. Serves FR-12.

## Risks

### FND-001 Redis idempotency fast path is not merchant-scoped and skips body-hash check

- **risk** · security privacy gap · severity **critical** · confidence 0.85 (high) · rank 1
- Disposition: **refinement now** (also: needs testing)

Section 9.2 writes and reads the fast-path response at idem:resp:{idempotency_key}, which has no merchant_id and no request-hash comparison. This breaks principle P3, which scopes idempotency to (merchant, key). Section 9.1 also accepts merchants' own order and invoice numbers as keys, so collisions across merchants are likely. Merchant A could receive merchant B's stored payment response, and its own payment would never be created. A reused key with a different body would get the old response instead of the HTTP 422 that FR-5 requires. That means cross-merchant data disclosure plus silent loss of payments.

- Where: p.8 §9.2 (FR-5): "completion of a request, the final response is written to idem:resp:{idempotency_key} with a 24-hour TTL. On every"
- Where: p.4 §3 (P3): "Idempotency is scoped to (merchant, key). Every mutating call is deduplicated on the pair of merchant identity and client-supplied"
- Where: p.7 §9.1 (FR-4): "frequently use their own order or invoice identifiers, which is accepted."
- Evidence EV-001 (doc, supports): "completion of a request, the final response is written to idem:resp:{idempotency_key} with a 24-hour TTL. On every" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-002 (doc, supports): "incoming mutating request, the Payments API checks this key first; on a hit, it returns the stored response immediately" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-003 (doc, supports): "Idempotency is scoped to (merchant, key). Every mutating call is deduplicated on the pair of merchant identity and client-supplied" [doc:DOC-design_v1#p4/s3]
- Evidence EV-004 (doc, supports): "frequently use their own order or invoice identifiers, which is accepted." [doc:DOC-design_v1#p7/s9.1]
- Evidence EV-041 (inference, supports): "With 15,000 merchants using order numbers as keys and a cache keyed on the key alone, cross-merchant collisions will return another merchant's response, and a hit returns before any body-hash check, so the 422 rule is bypassed." [inference:EV-041] derived from EV-001, EV-002, EV-003, EV-004
- Evidence EV-078 (inference, supports): "Because the fast-path key omits merchant_id and the request hash is not checked on a hit, two merchants that use the same order number receive each other's responses, and a reused key with a changed body returns the cached response instead of HTTP 422." [inference:EV-078] derived from EV-002, EV-003, EV-052
- Evidence EV-101 (inference, supports): "Order identifiers such as '10001' are very likely to repeat across 15,000 merchants within 24 hours. A merchant-agnostic cache key with no hash check would then serve one merchant another merchant's response." [inference:EV-101] derived from EV-090, EV-004
- Recommendation: In Section 9.2 and in the Confirmed Decisions idempotency row, change the key to idem:resp:{merchant_id}:{idempotency_key}. Store request_hash with the cached response and compare it on every hit: a mismatch returns 422. Add to the FR-5 acceptance criteria a two-merchant same-key test and a reused-key-different-body test that hits the fast path.
  - Issue: The fast-path key leaves out merchant identity and the request hash.
  - Rationale: P3 and FR-5 need deduplication on (merchant, key) and a 422 when the body differs. The fast path as written provides neither.
  - Expected benefit: Merchants' responses stay isolated from each other, and FR-5 and P3 hold on both tiers. (objectives: FR-5, P3, NFR-7)
  - Supporting evidence: EV-001, EV-002, EV-003, EV-041
  - Verification: Add an FR-5 test: merchants A and B send the same key with different bodies, and each gets its own payment. The same merchant resending the same key with a changed body gets 422 while the Redis entry exists.
- Next step: Payments API tech lead: Amend Section 9.2 and the FR-5 test cases before Phase 3 build.
- Decision AD-006 (24 Confirmed Decisions - Idempotency store): refines. Adds merchant_id and a request-hash check to the Redis key but keeps the approved two-tier Redis plus DynamoDB design.
- Decision AD-040 (FR-5): preserves. The change makes FR-5's (merchant, key) scope and its 422 rule hold on the fast path.
- Decision AD-034 (3 Foundational Principles): preserves. Brings the fast path back in line with principle P3, which takes precedence over Section 9.2.

### FND-002 Fraud Hook detokenises PAN, breaking P2, the CDE boundary and Vault access rules

- **risk** · internal contradiction · severity **high** · confidence 0.90 (high) · rank 2
- Disposition: **governance decision** (also: refinement now)

Section 13.1 has the Fraud Hook detokenise the full card number, using the Card Adapter's library and service role, and send it to FRV-1. Several other parts of the design contradict this: principle P2 (PAN only leaves the Vault over the Card Adapter's acquirer connection), Section 12.1 (only the Card Adapter's identity may detokenise), and Section 12.2 (Fraud Hook out of scope, token and BIN only). Sharing the role also defeats P9 least privilege. As written, the Fraud Hook and probably the Orchestrator path come into the CDE, so the NFR-5 scope cannot be assessed as defined. The FRV-1 data-processing agreement is still pending (Backlog item 4).

- Where: p.11 §13.1 (FR-9): "other clients in the region; scoring quality falls materially without it. The Fraud Hook obtains the PAN through the Vault's"
- Where: p.10 §12.2 (NFR-5): "Fraud Hook Out of scope Token, BIN, last 4 only"
- Where: p.3 §3 (P2): "Card data stays in the Vault. Primary account numbers (PAN) and sensitive authentication data never leave the Vault boundary"
- Evidence EV-005 (doc, supports): "other clients in the region; scoring quality falls materially without it. The Fraud Hook obtains the PAN through the Vault's" [doc:DOC-design_v1#p11/s13.1]
- Evidence EV-006 (doc, supports): "Fraud Hook Out of scope Token, BIN, last 4 only" [doc:DOC-design_v1#p10/s12.2]
- Evidence EV-007 (doc, supports): "Card data stays in the Vault. Primary account numbers (PAN) and sensitive authentication data never leave the Vault boundary" [doc:DOC-design_v1#p3/s3]
- Evidence EV-042 (inference, supports): "A non-CDE service that receives plaintext PAN through a borrowed CDE role cannot remain out of scope, so either the Section 12.2 scope table or the Section 13.1 payload is wrong." [inference:EV-042] derived from EV-005, EV-006, EV-007
- Evidence EV-055 (doc, supports): "detokenise operation, using the Card Adapter client library and service role." [doc:DOC-design_v1#p11/s13.1]
- Evidence EV-056 (doc, supports): "Only the Card Adapter's service identity may call detokenise." [doc:DOC-design_v1#p10/s12.1]
- Evidence EV-110 (doc, supports): "FRV-1's consortium velocity graph is keyed on the full card number, which allows it to link the same card across its" [doc:DOC-design_v1#p11/s13.1]
- Evidence EV-099 (inference, supports): "A component that handles PAN is part of the CDE, so the Fraud Hook, its network path and the FRV-1 connection are in scope. That contradicts both the 12.2 scope table and the NFR-5 constraint." [inference:EV-099] derived from EV-055, EV-006, EV-056
- Recommendation: In Section 13.1, replace card_number with the HMAC PAN fingerprint, or with a vendor-specific keyed hash or token computed inside the Vault. Alternatively, if the risk owner accepts expanding the CDE, add the Fraud Hook to Section 12.2 with its own service role. Remove the reuse of the Card Adapter role either way.
  - Issue: The fraud payload needs the PAN, which conflicts with the approved CDE scope and P2.
  - Rationale: P2 is stated to win over any conflicting section, and NFR-5 binds the CDE to the Section 12.2 list.
  - Expected benefit: Keeps the CDE minimal as NFR-5 intends, and restores P2 and P9. (objectives: NFR-5, P2, P9, FR-9)
  - Supporting evidence: EV-005, EV-006, EV-042
  - Verification: Run the NFR-5 segmentation test with the Fraud Hook role denied detokenise. Confirm with FRV-1 the scoring quality using a hashed identifier.
- Next step: Head of Payments Security with Risk lead: Decide between a hashed identifier and CDE expansion, and settle FRV-1's identifier support before the Phase 8 contract.
- Decision AD-029 (NFR-5): preserves. Both options (a fingerprint, or adding the Fraud Hook to the CDE explicitly) make the NFR-5 CDE definition true again.
- Decision AD-035 (P2): preserves. Removing PAN from the Fraud Hook payload restores P2.
- Decision AD-013 (24 Confirmed Decisions - Fraud): preserves. The synchronous FRV-1 call, its 150 ms timeout and the fallback are unchanged; only the payload changes.
- Decision AD-023 (25 Pending Backlog item 4): refines. The FRV-1 contract item should also cover FRV-1's PCI service-provider status and whether it supports a hashed identifier.

### FND-029 CVC retained after authorization, citing a PCI DSS allowance that appears not to exist

- **risk** · external constraint violation · severity **high** · confidence 0.75 (medium) · rank 3
- Disposition: **needs investigation** (also: refinement now)

Section 12.4 stores the CVC encrypted until settlement or for up to 72 hours. It also re-uses it for cascades and for incremental authorizations, which happen after the first authorization. The design says PCI DSS v4.0 Requirements 3.2.1 and 3.3.2 allow sensitive authentication data to be kept until settlement. The usual reading of the standard is that SAD may not be kept after authorization completes, and the requirements cited appear to cover storage before authorization, not after. If that reading is right, NFR-6 itself rests on a wrong premise, NFR-5 (Level 1 Report on Compliance) cannot be achieved, and the incremental-authorization use case is unlawful under the standard as built. No external source was available here to confirm the clause wording, so it must be checked before the Vault is built.

- Where: p.10 §12.4 (NFR-6): "3.2.1 and 3.3.2, which allow sensitive authentication data to be retained in encrypted form until the transaction is settled."
- Where: p.10 §12.4: "The CVC is required for the initial customer-initiated authorization and, at several acquirers, for each re-presentation of"
- Where: p.3 §2.2 (NFR-6): "Sensitive authentication data shall be handled per PCI DSS v4.0 Requirements 3.2.1 and 3.3.2: stored only in encrypted form, in the"
- Evidence EV-008 (doc, supports): "3.2.1 and 3.3.2, which allow sensitive authentication data to be retained in encrypted form until the transaction is settled." [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-087 (doc, supports): "The CVC is required for the initial customer-initiated authorization and, at several acquirers, for each re-presentation of" [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-098 (inference, supports): "Incremental authorizations by definition happen after the original authorization has completed, so keeping the CVC for them means storing SAD after authorization. This is the case the cited requirements are generally understood to prohibit; the clause wording still needs confirming against the standard." [inference:EV-098] derived from EV-008, EV-087
- Evidence EV-010 (doc, supports): "the Vault (including the card verification code; see Section 12.4) so that the second acquirer receives the same data as the first." [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-115 (doc, supports): "therefore stores the CVC encrypted under a separate KEK, and deletes it when the Reconciliation Service marks the" [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-043 (inference, supports): "Cascades, incremental authorizations and NFR-6 all depend on one regulatory reading that the document does not support with evidence; if it is wrong, three features and the PCI assessment fail together." [inference:EV-043] derived from EV-008, EV-009, EV-010
- Evidence EV-125 (inference, supports): "Retention extends past authorization to cover incremental authorizations, so compliance depends entirely on whether the cited requirements permit post-authorization SAD storage, which the document asserts without a source." [inference:EV-125] derived from EV-008, EV-115
- Recommendation: Have the QSA confirm the exact requirement text and get a written scoping opinion. If confirmed, rewrite 12.4 and NFR-6 so the CVC is purged when the first authorization reaches a final outcome (or when the cascade ends). Remove CVC from incremental authorizations and use scheme stored-credential/incremental indicators instead. Update the 'CVC handling' confirmed decision and the NFR-6 test so it asserts the CVC is absent after authorization completes.
  - Issue: The CVC retention policy rests on a reading of PCI DSS v4.0 Req. 3.2.1/3.3.2 that has not been checked and is probably wrong.
  - Rationale: If SAD may not be kept after authorization, the Vault design, NFR-6 and the cascade and incremental-auth flows all fail the QSA assessment.
  - Expected benefit: Keeps the NFR-5 Level 1 assessment achievable and avoids building a non-compliant Vault. (objectives: NFR-5, NFR-6, FR-7)
  - Supporting evidence: EV-008, EV-087, EV-098
  - Verification: Written QSA opinion on file. The NFR-6 test asserts no CVC exists in the Vault after the final authorization outcome.
- Next step: PCI compliance lead with the QSA: Get a written interpretation of v4.0 Req. 3.2.1/3.3.2 applied to Section 12.4 before Phase 2 (CDE) begins.
- Decision AD-009 (24 Confirmed Decisions - CVC handling): challenges. If the QSA confirms that SAD may not be kept after authorization, the confirmed rule (CVC kept until settlement, at most 72 hours) cannot meet NFR-5 and NFR-6; the challenge depends on that confirmation.
- Decision AD-030 (NFR-6): refines. The NFR-6 wording would need to match the confirmed reading of Requirements 3.2.1 and 3.3.2.
- Decision AD-029 (NFR-5): preserves. The aim is to keep the Level 1 assessment achievable.

### FND-004 Zero RPO for NFR-4 cannot be met with asynchronous Aurora Global replication and unreplicated idempotency state

- **risk** · internal contradiction · severity **high** · confidence 0.85 (high) · rank 4
- Disposition: **governance decision** (also: refinement now)

NFR-4 requires zero RPO for authorized payments and ledger postings, including when a whole region is lost. Section 20.2 replicates asynchronously with lag usually under a second, so postings committed in that window are lost. DynamoDB, Redis and MSK are rebuilt empty, so idempotency state for requests still in flight cannot be fully rebuilt. Merchant retries after failover can then produce duplicate authorizations, which breaks FR-5. The NFR-4 game day only checks postings committed before the failure, which does not exercise the loss window.

- Where: p.3 §2.2 (NFR-4): "Recovery point objective for authorized payments and ledger postings shall be zero, including on loss of an entire AWS region."
- Where: p.16 §20.2 (NFR-4): "• Aurora Global Database replicates the payments and ledger cluster to ap-southeast-3. Replication is storagelevel and asynchronous, with typical lag under one second."
- Where: p.17 §20.2 (FR-5): "empty in ap-southeast-3 from infrastructure-as-code, and in-flight idempotency state is reconstructed from the payment table."
- Evidence EV-011 (doc, supports): "Recovery point objective for authorized payments and ledger postings shall be zero, including on loss of an entire AWS region." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-012 (doc, supports): "• Aurora Global Database replicates the payments and ledger cluster to ap-southeast-3. Replication is storagelevel and asynchronous, with typical lag under one second." [doc:DOC-design_v1#p16/s20.2]
- Evidence EV-013 (doc, supports): "empty in ap-southeast-3 from infrastructure-as-code, and in-flight idempotency state is reconstructed from the payment table." [doc:DOC-design_v1#p17/s20.2]
- Evidence EV-044 (inference, supports): "Asynchronous replication with non-zero lag means RPO is greater than zero by construction, and up to about one second at 2,000 TPS is roughly 2,000 payments whose authorization or posting may be lost while the acquirer has already authorized them." [inference:EV-044] derived from EV-011, EV-012
- Evidence EV-057 (doc, supports): "Replication is storagelevel and asynchronous, with typical lag under one second." [doc:DOC-design_v1#p16/s20.2]
- Evidence EV-080 (inference, supports): "Asynchronous replication with non-zero lag implies a non-zero RPO on unplanned regional loss, so NFR-4 and Section 20.2 cannot both hold." [inference:EV-080] derived from EV-011, EV-057
- Evidence EV-124 (inference, supports): "The Section 19 payment DDL has no idempotency_key or request_hash column, so (merchant, key) dedup cannot be rebuilt after failover; asynchronous replication with non-zero lag cannot give RPO zero." [inference:EV-124] derived from EV-112, EV-057, EV-011
- Recommendation: Either relax NFR-4 to a bounded RPO (for example, the replication lag) and add a Section 20.2 recovery procedure: reconcile in-window authorizations from acquirer reports and settlement files and void orphans, with idempotency rebuilt from those reports. Or keep RPO 0 and add synchronous cross-region commit for authorization outcomes, accepting the latency cost against NFR-2. Update the NFR-4 game day to fail under load and count lost commits.
  - Issue: NFR-4 and the approved DR architecture cannot both hold.
  - Rationale: With asynchronous replication, the RPO is set by replication lag and cannot be zero.
  - Expected benefit: Gives NFR-4 an honest, testable target and a defined recovery path for authorizations lost in the replication window. (objectives: NFR-4, FR-5, FR-10)
  - Supporting evidence: EV-011, EV-012, EV-044
  - Verification: DR game day at 2,000 TPS: measured lost commits, and orphan authorizations found and resolved by the recovery procedure.
- Next step: Head of Platform Engineering: Decide whether to accept a bounded RPO or fund a synchronous design, and update NFR-4 and Section 20.2.
- Decision AD-032 (NFR-4): challenges. Asynchronous replication with non-zero lag cannot give zero RPO on loss of a region, so NFR-4 must be restated or the mechanism changed.
- Decision AD-004 (24 Confirmed Decisions - Disaster recovery): refines. Option (a) keeps Aurora Global Database DR and adds a procedure to recover lost-window authorizations from acquirer records.
- Decision AD-006 (24 Confirmed Decisions - Idempotency store): refines. Idempotency state needs a source that survives failover (for example, key columns in Aurora).

### FND-006 A single CloudHSM in one AZ is a single point of failure for every card authorization

- **risk** · scalability or failure mode · severity **high** · confidence 0.80 (high) · rank 5
- Disposition: **governance decision** (also: refinement now)

Section 12.1 unwraps every DEK in the HSM with no caching, and Section 12.3 runs one HSM in ap-southeast-1a. Losing that AZ or that HSM therefore stops all card payments. Mapping the resulting 503 to retryable does not help, because every cascade candidate goes through the same Vault. Cards are about 55% of attempts, against a 99.95% target (about 22 minutes a month) in NFR-3. The trigger for adding a second HSM (sustained card volume over 1,500 TPS) would never fire, because peak card volume is about 1,100 TPS. This challenges the approved 'one HSM at launch' decision, based on the three document items cited.

- Where: p.10 §12.3 (NFR-3): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a."
- Where: p.10 §12.1: "inside the HSM; DEKs are not cached, so plaintext key material never persists in application memory."
- Where: p.3 §2.2 (NFR-3): "Monthly availability of the merchant payment API shall be at least 99.95%."
- Evidence EV-018 (doc, supports): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a." [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-019 (doc, supports): "cluster when sustained card volume exceeds 1,500 TPS. If the HSM is unreachable, the Vault returns HTTP 503 and" [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-020 (doc, supports): "inside the HSM; DEKs are not cached, so plaintext key material never persists in application memory." [doc:DOC-design_v1#p10/s12.1]
- Evidence EV-021 (doc, supports): "Monthly availability of the merchant payment API shall be at least 99.95%." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-046 (inference, supports): "Peak card TPS is about 55% of 2,000, or 1,100, so the 1,500 TPS trigger never fires, and one HSM outage that needs a restore from backup could use up the roughly 22-minute monthly 99.95% budget." [inference:EV-046] derived from EV-018, EV-019, EV-020, EV-021
- Evidence EV-072 (doc, supports): "DEKs are not cached, so plaintext key material never persists in application memory." [doc:DOC-design_v1#p10/s12.1]
- Evidence EV-093 (doc, supports): "Card share of attempts (e-wallet ~30%, bank transfer ~15%) 54% 55%" [doc:DOC-design_v1#p2/s1]
- Evidence EV-084 (inference, supports): "Every card authorization and cascade attempt requires an HSM unwrap, so loss of the single HSM or of its AZ halts all card payments (about 55% of attempts) until a new HSM is restored from backup." [inference:EV-084] derived from EV-018, EV-072
- Evidence EV-123 (inference, supports): "55% of the 2,000 TPS peak is about 1,100 card TPS, below the 1,500 TPS trigger, so the single-HSM topology persists through the 2027 design target, and every card authorization depends on that one HSM." [inference:EV-123] derived from EV-018, EV-072, EV-093
- Recommendation: Amend Section 12.3 and the Vault decision to at least two HSMs in different AZs at launch, with a third for maintenance headroom, and an HSM cluster in the DR region for NFR-4. Replace the 1,500 TPS trigger with an HSM throughput benchmark. Add 'HSM unavailable' to the Section 20.4 degradation table.
  - Issue: The HSM topology does not meet the platform's three-AZ availability posture or NFR-3.
  - Rationale: Every card authorization depends synchronously on this single HSM.
  - Expected benefit: Card acceptance survives the loss of one AZ or one HSM, which protects NFR-3 and NFR-1. (objectives: NFR-3, NFR-4, NFR-1)
  - Supporting evidence: EV-018, EV-020, EV-046
  - Verification: Chaos test: terminate one HSM under 1,100 card TPS. Card authorizations continue within NFR-2.
- Next step: Vault tech lead with Head of Platform Engineering: Revisit the one-HSM decision, cost multi-AZ and DR-region HSMs, and benchmark unwrap throughput.
- Decision AD-008 (24 Confirmed Decisions - Vault): challenges. Several document items show that one HSM in one AZ is a single point of failure for every card authorization, against NFR-3 and the three-AZ posture.
- Decision AD-028 (12.3 HSM topology): challenges. The 1,500 TPS trigger for a second HSM cannot fire at the roughly 1,100 card TPS design peak.
- Decision AD-052 (NFR-3): preserves. The aim is to protect the 99.95% availability target.

### FND-005 Latency budget leaves cascades out of the p99, but 3.8% of attempts are retryable

- **risk** · unsupported or incorrect claim · severity **high** · confidence 0.85 (high) · rank 6
- Disposition: **refinement now** (also: needs testing)

Section 21.1 keeps cascades out of the p99 by claiming fewer than 1% of card payments cascade. Section 10.5 reports 3.8% retryable outcomes, and every one of them triggers a cascade under Section 11.2. Timeout-triggered cascades alone take more than 2,500 ms, which is over the 1,500 ms NFR-2 target. NFR-2 explicitly includes cascades, and the NFR-2 test injects 3.8% retryable outcomes, so the design as written is likely to fail its own acceptance test.

- Where: p.17 §21.1 (NFR-2): "Cascading does not move the p99 because fewer than 1% of card payments cascade; the cascade path therefore sits above the 99th"
- Where: p.9 §10.5 (FR-7): "retryable outcomes - soft declines eligible for reattempt plus acquirer-side errors and timeouts - 3.8%. Cascading"
- Where: p.3 §2.2 (NFR-2): "End-to-end p99 latency for a card authorization, measured at the API edge and including any cascade, shall not exceed 1,500 ms."
- Evidence EV-014 (doc, supports): "Cascading does not move the p99 because fewer than 1% of card payments cascade; the cascade path therefore sits above the 99th" [doc:DOC-design_v1#p17/s21.1]
- Evidence EV-015 (doc, supports): "retryable outcomes - soft declines eligible for reattempt plus acquirer-side errors and timeouts - 3.8%. Cascading" [doc:DOC-design_v1#p9/s10.5]
- Evidence EV-016 (doc, supports): "End-to-end p99 latency for a card authorization, measured at the API edge and including any cascade, shall not exceed 1,500 ms." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-017 (doc, supports): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms" [doc:DOC-design_v1#p9/s11.1]
- Evidence EV-045 (inference, supports): "About 3.8% of card payments cascade, which is more than the 1% tail, so the p99 falls inside the cascade population, and any cascade after a 2,500 ms timeout alone exceeds 1,500 ms." [inference:EV-045] derived from EV-014, EV-015, EV-016, EV-017
- Evidence EV-060 (doc, supports): "Under the NFR-1 load with 3.8% retryable-outcome injection, p99 end-to-end card authorization ≤ 1,500" [doc:DOC-design_v1#p20/s26.2]
- Evidence EV-081 (inference, supports): "About 3.8% of payments cascade, so the slowest 1% are cascades; a timeout cascade costs at least 2,500 ms plus a second round trip, and even a fast soft decline plus a second 1,100 ms p99 round trip exceeds the 1,338 ms budget." [inference:EV-081] derived from EV-058, EV-059, EV-060
- Recommendation: In Sections 11.2 and 21.1, add a per-payment deadline. Each attempt's timeout becomes the remaining budget minus orchestration overhead, and a cascade starts only if enough budget remains. Otherwise, the owner explicitly redefines NFR-2, for example to exclude timeout-triggered cascades or to set a separate cascade p99. Correct the under-1% claim.
  - Issue: The cascade path is not budgeted, and the stated cascade rate contradicts the baseline.
  - Rationale: NFR-2 counts cascades, and the 2,500 ms per-attempt timeout is longer than the whole end-to-end budget.
  - Expected benefit: Makes NFR-2 achievable and testable without dropping FR-7. (objectives: NFR-2, FR-7)
  - Supporting evidence: EV-015, EV-017, EV-045
  - Verification: Run the NFR-2 benchmark with the 3.8% retryable mix (including timeouts) and measure p99 against the revised budget.
- Next step: Orchestrator tech lead: Model the cascade latency distribution from the 2025 pilot data and propose a deadline-based cascade budget.
- Decision AD-011 (24 Confirmed Decisions - Cascade policy): refines. Keeps up to two cascade attempts and the same triggers, but derives each attempt's timeout from an overall deadline instead of a fixed 2,500 ms.
- Decision AD-051 (NFR-2): preserves. The aim is to make NFR-2 achievable as written.

### FND-020 NFR-8 08:00 SGT report deadline cannot be met given file arrival times and measured run times

- **risk** · internal contradiction · severity **high** · confidence 0.82 (high) · rank 7
- Disposition: **refinement now** (also: needs testing)

The batch matcher waits for every file for day T. ACQ-TH1 delivers at 06:30 ICT (07:30 SGT) and ACQ-ID1 at 05:00 WIB (06:00 SGT). Matching takes 45 minutes and report generation a further 15 minutes at 2025 volume. Reports therefore finish around 08:30 SGT at best, and later at the roughly doubled 2027 volume. NFR-8 requires publication by 08:00 SGT on T+1. There is also no defined behaviour when a file is late or missing, which would block all merchants' reports.

- Where: p.13 §16.2 (NFR-8): "matcher starts once all expected files for business day T have been received"
- Where: p.13 §16.2 (NFR-8): "the matcher's measured end-to-end run time is 45 minutes, and merchant settlement report generation takes a further"
- Where: p.3 §2.2 (NFR-8): "merchant settlement reports for business day T shall be published by"
- Evidence EV-061 (doc, supports): "ACQ-TH1 CSV over SFTP Daily 06:30 ICT" [doc:DOC-design_v1#p12/s16.1]
- Evidence EV-022 (doc, supports): "matcher starts once all expected files for business day T have been received" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-023 (doc, supports): "the matcher's measured end-to-end run time is 45 minutes, and merchant settlement report generation takes a further" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-082 (inference, supports): "06:30 ICT is 07:30 SGT; 07:30 + 45 min + 15 min = 08:30 SGT at 2025 volume, already after the 08:00 deadline before any volume growth or late file." [inference:EV-082] derived from EV-061, EV-022, EV-023
- Evidence EV-024 (doc, supports): "At least 99.9% of settlement lines shall be auto-matched; merchant settlement reports for business day T shall be published by" [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-047 (inference, supports): "ACQ-TH1's 06:30 ICT file arrives at 07:30 SGT, and 45 + 15 minutes at 2025 volume gives about 08:30 SGT, already after the 08:00 deadline before volume doubles from 5.1 M to 10.5 M attempts per day." [inference:EV-047] derived from EV-022, EV-023, EV-024
- Recommendation: In Section 16.2, match each provider's file incrementally on arrival and keep only cross-provider netting and payouts behind the 'all files' barrier. Publish each merchant's report once its providers have been matched. Define late or missing file handling (cut-off time, partial report flag, exception). Alternatively, restate NFR-8 with a deadline tied to the latest file.
  - Issue: An all-files-then-batch design and the latest file arrival time make the NFR-8 deadline unreachable.
  - Rationale: The arithmetic from the document's own figures exceeds the deadline.
  - Expected benefit: NFR-8 becomes achievable, and late files are contained. (objectives: NFR-8, FR-11)
  - Supporting evidence: EV-061, EV-082
  - Verification: NFR-8 replay at 2027 volume with production file arrival times, including one late file, publishes affected reports by the deadline.
- Decision AD-016 (24 Confirmed Decisions - Reconciliation): refines. Keeps the daily batch and three-way match but matches each provider's file as it arrives, leaving only netting behind the all-files barrier.
- Decision AD-053 (NFR-8): preserves. The aim is to make the NFR-8 08:00 SGT deadline achievable.

### FND-016 Cascade after a timeout can produce duplicate authorizations; the 'cannot create a duplicate charge' claim is unsupported

- **risk** · unsupported or incorrect claim · severity **high** · confidence 0.80 (high) · rank 8
- Disposition: **refinement now** (also: needs testing)

Section 11.1 classes 'no response within 2,500 ms' as retryable, and Section 11.2 discards late responses. Yet Section 11.2 says cascading cannot create a duplicate charge because the previous attempt 'did not succeed'. A timed-out attempt may still have been approved by the first acquirer, and the second acquirer may then approve too, leaving two holds on the customer's card. The design has no path to reverse or void an orphaned late approval, which conflicts with P1 and with the intent of FR-5 and FR-7.

- Where: p.9 §11.2 (FR-7): "succeed, cascading cannot create a duplicate charge: the ledger records only the approved attempt."
- Where: p.9 §11.2 (FR-7): "arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded."
- Where: p.9 §11.1 (FR-7): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms"
- Evidence EV-053 (doc, supports): "succeed, cascading cannot create a duplicate charge: the ledger records only the approved attempt." [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-054 (doc, supports): "arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded." [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-079 (inference, supports): "A timeout means the outcome is unknown, not failed, so a late approval from acquirer 1 plus an approval from acquirer 2 leaves two authorizations on the card, and discarding the late response leaves the first one unreversed." [inference:EV-079] derived from EV-053, EV-054
- Evidence EV-122 (inference, supports): "A timed-out attempt that the acquirer approved leaves a live issuer authorization that MPOP never reverses, alongside the approved cascade attempt." [inference:EV-122] derived from EV-054, EV-111
- Recommendation: In Section 11.2, replace 'logged and discarded' with: a late approval on a superseded attempt triggers an automatic authorization reversal through the adapter and a reconciliation flag. Before cascading after a timeout, send a reversal or status query where the acquirer supports one. Remove the 'cannot create a duplicate charge' sentence. Add a late-approval case to the FR-7 cascade simulation in Section 26.1.
  - Issue: Timeouts are treated as definite failures, and late approvals are discarded with no reversal.
  - Rationale: Leaving an approved authorization unreversed ties up customer funds and contradicts P1 (the payment record as the single truth).
  - Expected benefit: Prevents double holds on the cardholder and keeps attempt records consistent with acquirer state (FR-7, P1). (objectives: FR-7, P1, FR-5)
  - Supporting evidence: EV-053, EV-054, EV-079
  - Verification: Cascade simulation: the simulator approves attempt 1 after 3 s, attempt 2 approves, and the test asserts a reversal is sent for attempt 1 and exactly one authorization remains open.
- Decision AD-011 (24 Confirmed Decisions - Cascade policy): refines. Keeps the cascade policy and adds a reversal or status query for timed-out and late-approved attempts.
- Decision AD-041 (FR-7): preserves. Cascading under FR-7 is kept and made safe.

### FND-021 First cohort goes live before the Fraud Hook, the PCI DSS assessment and the Section 26 test plan

- **risk** · internal contradiction · severity **high** · confidence 0.80 (high) · rank 9
- Disposition: **governance decision** (also: refinement now)

Section 28 puts first-cohort go-live after Phase 7. The Fraud Hook comes in Phase 8 (blocked on the FRV-1 contract), and the load, DR, PCI DSS assessment and Section 26 acceptance testing come in Phase 9. Live card traffic would therefore run without the fraud scoring that FR-9 requires and before NFR-5 and the acceptance criteria have been demonstrated. Section 27's conclusion that only the Admin API and disputes are material gaps for the first cohort overlooks this.

- Where: p.21 §28 (FR-9, NFR-5): "The first merchant cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week"
- Where: p.21 §28 (NFR-5): "Hardening - load, chaos and DR game days; PCI DSS assessment; Section 26 test plan"
- Where: p.3 §2.1 (FR-9): "Every card payment and every e-wallet payment above the merchant's configured threshold shall be scored by the fraud-scoring hook"
- Evidence EV-062 (doc, supports): "The first merchant cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week" [doc:DOC-design_v1#p21/s28]
- Evidence EV-063 (doc, supports): "8 Fraud Hook (FRV-1) Yes - vendor contract (Backlog item 4)" [doc:DOC-design_v1#p21/s28]
- Evidence EV-064 (doc, supports): "Hardening - load, chaos and DR game days; PCI DSS assessment; Section 26 test plan" [doc:DOC-design_v1#p21/s28]
- Evidence EV-092 (doc, supports): "FRV-1 contract - data processing agreement and SLA finalisation." [doc:DOC-design_v1#p19/s25]
- Evidence EV-106 (inference, supports): "Since Phase 8 (Fraud Hook) comes after the Phase 7 go-live, card payments in the first cohort are not scored, contrary to FR-9." [inference:EV-106] derived from EV-062, EV-092
- Recommendation: In Section 28, make go-live follow Phase 8 and the cohort-relevant parts of Phase 9 (PCI DSS RoC, NFR-1/2/4 tests for SG). Alternatively, document an explicit, owner-approved interim fraud control and risk acceptance. Update the Section 27 overall conclusion.
  - Issue: The phase order lets production card traffic start before mandatory controls and verification are in place.
  - Rationale: FR-9 has no exception for a launch cohort, and NFR-5 compliance and the Section 26 tests are what show the design is fit to go live.
  - Expected benefit: First-cohort launch meets FR-9 and NFR-5, with acceptance evidence in hand. (objectives: FR-9, NFR-5)
  - Supporting evidence: EV-062, EV-063, EV-064
  - Verification: Go-live checklist requires a FR-9 test pass, a QSA RoC and NFR-1/NFR-2/NFR-4 results.
- Next step: Programme director with Head of Risk: Re-sequence go-live gates, or sign a time-boxed risk acceptance for the interim fraud and PCI posture.
- Decision AD-043 (FR-9): preserves. Re-sequencing the go-live gates makes FR-9 hold from the first live card payment.
- Decision AD-023 (25 Pending Backlog item 4): refines. The FRV-1 contract and DPA become a gate before go-live.
- Decision AD-029 (NFR-5): preserves. Go-live waits for the NFR-5 assessment evidence.

## Gaps

### FND-046 A single Finance user, with MFA optional, can change the payout bank account with no second approval or owner alert

- **gap** · security privacy gap · severity **high** · confidence 0.80 (high) · rank 10
- Disposition: **refinement now**

Section 18.4 lets one Finance or Owner user change the payout account. The only notice goes to the user who made the change. MFA is enforced only for the Owner role. One phished Finance password is therefore enough to redirect all of a merchant's payouts: an account-takeover path to direct financial loss. Finance also holds both refund and payout-account rights, which conflicts with P9's separation of money-moving and configuration permissions.

- Where: p.14 §18.4 (FR-13): "A confirmation email is sent to the user who made the change, and the change is written to the audit log."
- Where: p.14 §18.3: "TOTP multi-factor authentication is available to every user and is enforced for the Owner role at first login."
- Where: p.14 §18.2: "Finance Issue refunds; view and export reports; edit payout bank account"
- Evidence EV-113 (doc, supports): "A confirmation email is sent to the user who made the change, and the change is written to the audit log." [doc:DOC-design_v1#p14/s18.4]
- Evidence EV-027 (doc, supports): "TOTP multi-factor authentication is available to every user and is enforced for the Owner role at first login." [doc:DOC-design_v1#p14/s18.3]
- Evidence EV-114 (doc, supports): "Least privilege and separation of duties. Every human and service identity has only the permissions its role requires; money-moving" [doc:DOC-design_v1#p4/s3]
- Evidence EV-025 (doc, supports): "A Finance or Owner user can change the payout bank account in the portal. The change takes effect from the next" [doc:DOC-design_v1#p14/s18.4]
- Evidence EV-048 (inference, supports): "A credential compromise of a Finance user without MFA lets one person redirect the next payout, and the only notice goes to the attacker's own session email." [inference:EV-048] derived from EV-025, EV-026, EV-027
- Recommendation: In Section 18.3, enforce MFA for every role with money-moving or credential rights (Owner, Admin, Finance, Support). In Section 18.4, require step-up MFA, notify all Owners and the previous account contact, apply a cooling-off hold (e.g. first payout to a new account held for review), and re-verify the account (verified_at). Separate refund and payout-account rights or require a second approver.
  - Issue: Payout redirection is protected by a single factor and a single actor.
  - Rationale: P8 (fail closed on security) and P9 (separation of duties). Payout-account change is the highest-value fraud target in the admin plane.
  - Expected benefit: Closes the account-takeover-to-payout-fraud path and protects merchant funds under FR-13 and FR-17. (objectives: FR-13, FR-17, P9, P8)
  - Supporting evidence: EV-113, EV-027, EV-114
  - Verification: FR-13 role-matrix test extended: a payout-account change without MFA is rejected; Owners are notified; the first payout to the new account is held.
- Decision AD-018 (24 Confirmed Decisions - Merchant user MFA): challenges. Optional MFA for the Finance role lets one stolen password redirect payouts, so MFA must be enforced for roles that can move money.
- Decision AD-049 (FR-17): preserves. Protects payouts to the registered account under FR-17.

### FND-022 State machine omits transitions that FR-1, FR-15 and the flows require; FR-2 test cannot detect this

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.78 (medium) · rank 12
- Disposition: **refinement now**

Section 7.2 permits PARTIALLY_REFUNDED -> REFUNDED only, so a second partial refund, which FR-1 and FR-15 require, has no permitted transition. A payment refunded before settlement can never reach SETTLED, although Section 16.2 moves matched payments to SETTLED. Other paths have no clear transition: a failed 3DS challenge or wallet payment from REQUIRES_ACTION, the Section 8 REVIEW 'authorize-and-hold-capture' outcome, and repeated partial captures. The FR-2 property test only checks that no transition outside Section 7.2 occurs, so it cannot reveal missing transitions.

- Where: p.6 §7.1 (FR-2): "One or more refunds succeeded against a captured or succeeded payment."
- Where: p.19 §26.1 (FR-2): "Randomised event sequences (10^6 per run) never produce a transition outside Section 7.2"
- Where: p.2 §2.1 (FR-2): "Every payment shall be in exactly one state of the state machine in Section 7 at any time; only the transitions listed there shall be"
- Evidence EV-065 (doc, supports): "PARTIALLY_REFUNDED -> REFUNDED" [doc:DOC-design_v1#p6/s7.2]
- Evidence EV-066 (doc, supports): "REQUIRES_ACTION -> AUTHORISING | CANCELLED (expiry)" [doc:DOC-design_v1#p6/s7.2]
- Evidence EV-067 (doc, supports): "Matched payments transition to SETTLED and a settlement journal is posted." [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-083 (inference, supports): "No self-transition on PARTIALLY_REFUNDED or CAPTURED and no PARTIALLY_REFUNDED/REFUNDED -> SETTLED edge exists, so multiple partial refunds, multiple partial captures and settlement after an early refund are not representable." [inference:EV-083] derived from EV-065, EV-066, EV-067
- Recommendation: In Section 7.2, add PARTIALLY_REFUNDED -> PARTIALLY_REFUNDED, CAPTURED -> CAPTURED (additional partial capture), REQUIRES_ACTION -> FAILED/SUCCEEDED, and a hold state or flag for REVIEW. Model settlement status separately from refund status (or add transitions from the refund states to SETTLED). Extend the FR-2 criterion with a positive test: every documented operation sequence from Sections 8, 11 and 16 completes.
  - Issue: The transition table is incomplete for the operations and flows the design requires.
  - Rationale: FR-2 forbids transitions not listed, so the gaps become hard functional failures.
  - Expected benefit: FR-1, FR-2 and FR-15 are satisfiable together. (objectives: FR-1, FR-2, FR-15)
  - Supporting evidence: EV-065, EV-066, EV-067, EV-083
  - Verification: Scenario test suite covering multi-partial refund, refund-before-settlement, 3DS failure and REVIEW hold reaches the expected terminal states.
- Decision AD-039 (FR-2): refines. Adds the transitions that FR-1 and FR-15 need, so that FR-2's 'only listed transitions' rule can be satisfied.

### FND-051 Cross-border transfer and localisation basis for personal and payment data is not addressed

- **gap** · security privacy gap · severity **medium** · confidence 0.50 (medium) · rank 16
- Disposition: **governance decision** (also: needs investigation) · already acknowledged in the document

All primary data for five markets sits in Singapore, DR is in Jakarta, and card numbers plus hashed identifiers go to FRV-1 for a regional consortium graph. NFR-7 names each market's law but the design gives no transfer basis, localisation assessment (notably for Indonesian payment data) or vendor-sharing assessment. The FRV-1 DPA is acknowledged as pending in Backlog item 4. This review adds that the gap is wider than the vendor contract: the data-placement decision itself needs a per-market sign-off before build, not only the DPO review in Phase 9.

- Where: p.16 §19.1 (NFR-7): "All primary data stores (Aurora, DynamoDB, ElastiCache, MSK, S3 intake and archive buckets) are in ap-southeast-1."
- Where: p.19 §25: "FRV-1 contract - data processing agreement and SLA finalisation."
- Evidence EV-096 (doc, supports): "All primary data stores (Aurora, DynamoDB, ElastiCache, MSK, S3 intake and archive buckets) are in ap-southeast-1." [doc:DOC-design_v1#p16/s19.1]
- Evidence EV-092 (doc, supports): "FRV-1 contract - data processing agreement and SLA finalisation." [doc:DOC-design_v1#p19/s25]
- Evidence EV-097 (doc, supports): "Personal data shall be processed in accordance with the personal data protection laws of each market of operation (Singapore" [doc:DOC-design_v1#p3/s2.2]
- Recommendation: Add a per-market data-transfer and localisation assessment to Section 19.1 (transfer mechanism, any localisation obligations for payment data, DR copy in Jakarta), make DPO pre-approval a Phase 1 gate, and widen Backlog item 4 to cover the lawful basis for consortium data sharing.
  - Issue: There is no documented legal basis for centralising five markets' data in Singapore or for sharing it with FRV-1.
  - Rationale: NFR-7 compliance is assessed only at the end (DPO sign-off), but localisation findings would change the Section 19.1 placement and DR design.
  - Expected benefit: Avoids late re-architecture of data placement and protects NFR-7 compliance. (objectives: NFR-7)
  - Supporting evidence: EV-096, EV-092, EV-097
  - Verification: Signed per-market DPO/legal assessment recorded before Phase 1 exit.
- Next step: Data Protection Officer with Legal (per market): Assess cross-border transfer and localisation obligations for each market and approve or amend Section 19.1 placement.
- Decision AD-036 (19.1 Data placement): refines. Adds a per-market legal sign-off for the single-region placement; it does not reverse the placement.
- Decision AD-031 (NFR-7): preserves. The aim is to show NFR-7 compliance before build.
- Decision AD-001 (24 Confirmed Decisions - Cloud and primary region): preserves. No change to the primary region unless a localisation rule is confirmed.

### FND-012 The readiness assessment marks components 'Ready' that carry unresolved conflicts

- **gap** · other · severity **low** · confidence 0.70 (medium) · rank 18
- Disposition: **refinement now**

Section 27 marks the Idempotency Layer and the Card Vault 'Ready', and concludes that the transaction core is specified to implementation level. Yet this review found principle and requirement conflicts in exactly those components: fast-path scoping (FND-001), Fraud Hook PAN access (FND-002), CVC retention (FND-003), HSM topology (FND-006) and the network-token dependency (FND-010). Section 27 is the document's own fitness verdict, so overstating it means build starts on parts that will need redesign.

- Where: p.20 §27: "Tokenisation, envelope encryption, HSM, SAD handling and network tokens specified"
- Where: p.21 §27: "The transaction core is specified to implementation level. The Admin API schemas and the dispute module are the two"
- Evidence EV-035 (doc, supports): "Tokenisation, envelope encryption, HSM, SAD handling and network tokens specified" [doc:DOC-design_v1#p20/s27]
- Evidence EV-036 (doc, supports): "The transaction core is specified to implementation level. The Admin API schemas and the dispute module are the two" [doc:DOC-design_v1#p21/s27]
- Evidence EV-051 (inference, supports): "Components marked Ready contain the open conflicts identified in this review, so the readiness verdict is overstated." [inference:EV-051] derived from EV-035, EV-036, EV-001, EV-005, EV-008, EV-018, EV-031
- Recommendation: Re-grade the Section 27 rows for Card Vault, Idempotency Layer and Fraud Hook to 'Mostly ready' or 'Partial', listing the open items. Update the 'Depends on open design items?' column for Phases 2 and 3 in Section 28.
  - Issue: The readiness verdict does not reflect the unresolved design conflicts.
  - Rationale: Build phases 2 and 3 are gated on these 'Ready' labels.
  - Expected benefit: Build starts only on components that are actually settled. (objectives: NFR-5, FR-5, FR-14)
  - Supporting evidence: EV-035, EV-036, EV-051
  - Verification: Design review sign-off on the revised Section 27 table.
- Decision AD-026 (25 Pending Backlog item 7): preserves. The Admin API gap stays acknowledged; the change only re-grades the other components.

## Ambiguities

### FND-011 FR-8's '2%' cost-approval tolerance has an undefined unit and mechanism

- **ambiguity** · ambiguous requirement · severity **medium** · confidence 0.75 (medium) · rank 17
- Disposition: **refinement now**

FR-8 caps the loss of authorization rate at 'more than 2%'. Section 10.3 and the confirmed Routing decision use a tolerance of 'default 2' with no unit. This could mean 2 percentage points or 2% relative, and either a per-transaction comparison of priors or a weekly realised-rate check. The weighted score in Section 10.2 can also choose a cheaper acquirer whatever the tolerance. With a default weighting that favours cost, the readings lead to materially different routing, and the FR-8 test cannot confirm the requirement.

- Where: p.2 §2.1 (FR-8): "FR-8 For each transaction, the Routing Engine shall prefer the lowest-cost eligible acquirer unless doing so reduces the expected"
- Where: p.9 §10.3 (FR-8): "acquirer against that of the highest-approval acquirer and applies the cost preference when the difference is within the"
- Where: p.18 §24 (FR-8): "Routing Weighted cost/approval/latency score; cost-preferred within 2 tolerance"
- Evidence EV-032 (doc, supports): "FR-8 For each transaction, the Routing Engine shall prefer the lowest-cost eligible acquirer unless doing so reduces the expected" [doc:DOC-design_v1#p2/s2.1]
- Evidence EV-033 (doc, supports): "configured tolerance (default 2). Separately, the weekly Routing Review compares each merchant's realised" [doc:DOC-design_v1#p9/s10.3]
- Evidence EV-034 (doc, supports): "Routing Weighted cost/approval/latency score; cost-preferred within 2 tolerance" [doc:DOC-design_v1#p18/s24]
- Evidence EV-075 (doc, supports): "configured tolerance (default 2)" [doc:DOC-design_v1#p9/s10.3]
- Evidence EV-076 (doc, supports): "authorization rate by more than 2%." [doc:DOC-design_v1#p3/s2.1]
- Recommendation: State in FR-8 and Section 10.3 that the tolerance is in percentage points of approval prior and is a hard filter applied before the weighted score. Treat the weekly review as a monitoring control. Update the FR-8 acceptance criterion to include boundary cases at the tolerance.
  - Issue: Neither the unit nor the enforcement point of the tolerance is defined.
  - Rationale: With 88% approval, a 2-percentage-point gap and a 2% relative gap differ only slightly, but the per-transaction rule and the weekly realised-rate rule produce different behaviour.
  - Expected benefit: Makes FR-8 unambiguous and testable. (objectives: FR-8)
  - Supporting evidence: EV-032, EV-033, EV-034
  - Verification: FR-8 routing tests at a gap of tolerance ±0.1.
- Decision AD-012 (24 Confirmed Decisions - Routing): refines. Defines the unit and the enforcement point of the approved tolerance of 2.
- Decision AD-042 (FR-8): refines. Makes FR-8 unambiguous and testable.

## Unresolved assumptions

### FND-036 Network tokens 'from launch' and Phase 3 marked ready while the token requestor application is unsubmitted

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.85 (high) · rank 14
- Disposition: **governance decision** (also: refinement now) · already acknowledged in the document

Section 24 confirms network tokens as the primary card-on-file credential from launch, and Phase 3 (including card-on-file with network tokens) is marked 'No - ready'. Backlog item 2 says the VTS/MDES token-requestor application, the TSP agreement and certification have not started. The review adds two points. First, scheme registration and certification lead times sit on the critical path to first go-live, yet the readiness assessment does not track them. Second, the FR-14 test needs live network-token-enabled test cards, which depend on that registration.

- Where: p.18 §24 (FR-14): "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch; PAN"
- Where: p.19 §25: "the commercial agreement with a token service provider; certification test plan. Application not yet submitted."
- Where: p.21 §28: "Transaction core - Payments API, idempotency, state machine, ledger, outbox; card-on-file"
- Evidence EV-030 (doc, supports): "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch; PAN" [doc:DOC-design_v1#p18/s24]
- Evidence EV-031 (doc, supports): "the commercial agreement with a token service provider; certification test plan. Application not yet submitted." [doc:DOC-design_v1#p19/s25]
- Evidence EV-105 (inference, supports): "A confirmed decision and a 'ready' build phase both depend on a registration that has not been applied for, so the readiness verdict for card-on-file is overstated." [inference:EV-105] derived from EV-030, EV-031
- Evidence EV-071 (doc, supports): "3 No - ready" [doc:DOC-design_v1#p21/s28]
- Evidence EV-050 (inference, supports): "A confirmed launch decision and a 'ready' build phase depend on an external registration that has not started, so either the launch date or the decision is at risk." [inference:EV-050] derived from EV-030, EV-031
- Recommendation: Mark Phase 3 card-on-file as 'Partially - Backlog item 2' in Sections 27 and 28. Add a dated milestone and owner for the TRID submission. Define a launch fallback (PAN-based stored credential with MIT/CIT indicators) in 12.5 until certification completes.
  - Issue: The network-token decision and Phase 3 readiness depend on Backlog item 2, which has not started.
  - Rationale: An unsubmitted scheme registration can delay or block card-on-file at launch.
  - Expected benefit: A realistic FR-14 delivery date and a defined launch fallback. (objectives: FR-14)
  - Supporting evidence: EV-030, EV-031, EV-105
  - Verification: Readiness table updated; TRID submission date tracked; FR-14 test runs once certification is granted.
- Next step: Head of Card Partnerships: Submit the VTS/MDES token-requestor applications and get scheme lead times to set the Phase 3 critical path.
- Decision AD-010 (24 Confirmed Decisions - Card-on-file credential): refines. Keeps network tokens as the primary credential and adds an explicit PAN plus MIT/CIT fallback at launch until certification is complete.
- Decision AD-021 (25 Pending Backlog item 2): refines. Gives the token-requestor registration an owner and a date on the critical path.
- Decision AD-047 (FR-14): preserves. FR-14 already allows PAN where tokens are unsupported.

## Validation needs

### FND-009 DynamoDB per-partition capacity and LSI layout claims for the largest merchant are unverified

- **validation need** · unsupported or incorrect claim · severity **high** · confidence 0.60 (medium) · rank 11
- Disposition: **needs investigation** (also: needs testing)

Section 9.3 assumes a single partition sustains 10,000 WCU per second and that one merchant's roughly 1,800 writes per second fit comfortably. It also uses an LSI, which ties all of a merchant's items to one partition key. Both are external platform facts that the document does not support. It also counts writes rather than WCU for response bodies of up to 4 KB. If the per-partition limit or the LSI item-collection limits are lower than assumed, the durable idempotency path for M-0001 would throttle at campaign peak. That would break FR-5 and NFR-1 for 45% of peak traffic.

- Where: p.8 §9.3 (NFR-1, FR-5): "single partition sustains up to 10,000 write capacity units per second. Our largest merchant (marketplace M-0001)"
- Where: p.8 §9.3: "Keying by merchant_id keeps each merchant's records co-located, which the local secondary index on"
- Evidence EV-028 (doc, supports): "single partition sustains up to 10,000 write capacity units per second. Our largest merchant (marketplace M-0001)" [doc:DOC-design_v1#p8/s9.3]
- Evidence EV-029 (doc, supports): "Keying by merchant_id keeps each merchant's records co-located, which the local secondary index on" [doc:DOC-design_v1#p8/s9.3]
- Evidence EV-049 (inference, supports): "About 900 TPS with two writes each, and items of up to 4 KB, could consume several thousand WCU per second on a single partition key, so the margin depends entirely on the unverified per-partition limit and on LSI constraints." [inference:EV-049] derived from EV-028, EV-029
- Evidence EV-088 (doc, supports): "two writes - lock acquisition and completion update - or about 1,800 WCU at peak" [doc:DOC-design_v1#p8/s9.3]
- Evidence EV-089 (doc, supports): "response_body String Serialised response, up to 4 KB" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-074 (doc, supports): "Largest single merchant share at peak 41% 45%" [doc:DOC-design_v1#p2/s1]
- Evidence EV-126 (inference, supports): "A completion write carrying up to 4 KB of response consumes several WCU, so actual demand exceeds 1,800 WCU, and headroom depends on an unsourced per-partition ceiling." [inference:EV-126] derived from EV-116, EV-088, EV-089
- Evidence EV-085 (inference, supports): "45% of 10.5 M daily attempts is about 4.7 M items per day under one partition key, at up to about 4 KB each, so tens of GB sit in one item collection, and the NFR-1 test as written would not exercise this concentration." [inference:EV-085] derived from EV-073, EV-074
- Recommendation: Check the per-partition throughput and LSI item-collection limits against AWS primary documentation. If they constrain the design, key the table on merchant_id#idempotency_key (or a sharded merchant prefix) and replace the LSI with a GSI or a separate query path for the back-office view. Restate the Section 9.3 arithmetic in WCU including item size.
  - Issue: The idempotency table's capacity rests on unverified service limits.
  - Rationale: A hot partition on the durable idempotency path fails the requests of the largest merchant.
  - Expected benefit: Confirms or corrects NFR-1 capacity for the largest merchant before Phase 3. (objectives: NFR-1, FR-5)
  - Supporting evidence: EV-028, EV-029, EV-049
  - Verification: Load test of the idempotency table at 900 TPS on a single merchant with 4 KB responses for 4 hours, with zero throttled writes.
- Next step: Payments API tech lead: Verify the DynamoDB partition and LSI limits and run a single-merchant hot-key load test.
- Decision AD-006 (24 Confirmed Decisions - Idempotency store): refines. A change to the partition key or the LSI is proposed only if verification shows the limits bind, so this is not yet a challenge.
- Decision AD-050 (NFR-1): preserves. The aim is to confirm NFR-1 for the largest merchant.

### FND-023 FR-5 concurrency clause conflicts with the 409 behaviour, and the replay test only checks sequential duplicates

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.78 (medium) · rank 13
- Disposition: **needs testing** (also: refinement now)

FR-5 requires the identical response even for concurrent duplicates, while Section 9.1 returns HTTP 409 request_in_progress to an in-flight duplicate. The FR-5 acceptance test resends only after the first response has arrived. It therefore never exercises the concurrent case, the sweeper-recovered IN_PROGRESS case, or the Redis-down path in Section 20.4, which are where duplicate downstream authorizations would arise.

- Where: p.2 §2.1 (FR-5): "and shall return the identical response, including when duplicate requests arrive concurrently"
- Where: p.7 §9.1 (FR-5): "While the first request is in flight, a duplicate receives HTTP 409 request_in_progress with Retry-After: 1."
- Where: p.19 §26.1 (FR-5): "Send a create-payment request; after its response is received, resend the identical request with the same"
- Evidence EV-068 (doc, supports): "and shall return the identical response, including when duplicate requests arrive concurrently" [doc:DOC-design_v1#p2/s2.1]
- Evidence EV-069 (doc, supports): "While the first request is in flight, a duplicate receives HTTP 409 request_in_progress with Retry-After: 1." [doc:DOC-design_v1#p7/s9.1]
- Evidence EV-070 (doc, supports): "Send a create-payment request; after its response is received, resend the identical request with the same" [doc:DOC-design_v1#p19/s26.1]
- Recommendation: Restate FR-5 as: concurrent duplicates receive either the identical final response or 409 request_in_progress, and never a second downstream call. Extend the Section 26.1 FR-5 test with N parallel duplicates, a pod kill between lock and completion, and a Redis outage, asserting exactly one acquirer authorization each time.
  - Issue: The requirement text and the mechanism disagree, and the test does not cover the concurrent case.
  - Rationale: The concurrent and crash-recovery cases are where at-most-one-authorization is at risk.
  - Expected benefit: FR-5 becomes consistent and actually demonstrated. (objectives: FR-5)
  - Supporting evidence: EV-068, EV-069, EV-070
  - Verification: The extended FR-5 test passes against the acquirer simulator.
- Next step: QA lead, Payments Core: Add concurrency, crash and Redis-outage cases to the FR-5 test plan.
- Decision AD-040 (FR-5): refines. Reconciles FR-5's 'identical response' wording with the 409 in-flight behaviour and adds tests for the concurrent case.

### FND-039 Cross-acquirer cascading of issuer soft declines is assumed scheme-compliant without stated limits

- **validation need** · external constraint violation · severity **medium** · confidence 0.50 (medium) · rank 15
- Disposition: **needs investigation**

Section 11 cascades issuer responses such as 05 'do not honour' to a different acquirer and says it stops 'at the scheme limits applicable to the card'. However, it does not state those limits or whether the schemes treat re-presenting an issuer decline through another acquirer as a reattempt or as a breach of their rules. The 31% recovery figure comes from a single-corridor pilot (ACQ-SG1 to ACQ-SG2) and is not split between issuer declines and acquirer errors. If scheme rules are stricter, FR-7 exposes merchants to excessive-reattempt fees, and the recovery benefit is unproven.

- Where: p.9 §11.1 (FR-7): "Soft declines 05 (do not honour) and 91 (issuer unavailable) and 96 (system malfunction);"
- Where: p.9 §11.3 (FR-7): "window and stops reattempting at the scheme limits applicable to the card."
- Where: p.9 §10.5: "recovered approximately 31% of retryable outcomes in a three-month pilot on ACQ-SG1 → ACQ-SG2."
- Evidence EV-094 (doc, supports): "Soft declines 05 (do not honour) and 91 (issuer unavailable) and 96 (system malfunction);" [doc:DOC-design_v1#p9/s11.1]
- Evidence EV-095 (doc, supports): "window and stops reattempting at the scheme limits applicable to the card." [doc:DOC-design_v1#p9/s11.3]
- Evidence EV-108 (inference, supports): "The scheme limits are referenced but never quantified, so neither the Retry Engine configuration nor the FR-7 test can show compliance." [inference:EV-108] derived from EV-094, EV-095
- Recommendation: Add a table to 11.3 of Visa and Mastercard reattempt limits and the decline categories eligible for cross-acquirer cascade, confirmed by each acquirer. Split the pilot recovery rate by response class.
  - Issue: Scheme reattempt rules for cross-acquirer cascades are referenced but not specified or verified.
  - Rationale: FR-7 requires never reattempting where scheme rules forbid it, which cannot be implemented or tested without the actual rules.
  - Expected benefit: FR-7 can be implemented and tested. (objectives: FR-7)
  - Supporting evidence: EV-094, EV-095, EV-108
  - Verification: Acquirer sign-off on the table. The FR-7 simulation is parameterised from it.
- Next step: Payments Core routing lead: Get current scheme reattempt rules from ACQ-SG2 and the scheme manuals.
- Decision AD-033 (FR-7 (scheme rules)): preserves. Writing the scheme limits down is what lets the constraint be implemented and tested.
- Decision AD-011 (24 Confirmed Decisions - Cascade policy): refines. Cascading on response code 05 may need to be restricted once the scheme rules are confirmed.

## Recommended refinements

| Finding | Change | Expected benefit |
|---|---|---|
| FND-001 | In Section 9.2 and in the Confirmed Decisions idempotency row, change the key to idem:resp:{merchant_id}:{idempotency_key}. Store request_hash with the cached response and compare it on every hit: a mismatch returns 422. Add to the FR-5 acceptance criteria a two-merchant same-key test and a reused-key-different-body test that hits the fast path. | Merchants' responses stay isolated from each other, and FR-5 and P3 hold on both tiers. |
| FND-002 | In Section 13.1, replace card_number with the HMAC PAN fingerprint, or with a vendor-specific keyed hash or token computed inside the Vault. Alternatively, if the risk owner accepts expanding the CDE, add the Fraud Hook to Section 12.2 with its own service role. Remove the reuse of the Card Adapter role either way. | Keeps the CDE minimal as NFR-5 intends, and restores P2 and P9. |
| FND-029 | Have the QSA confirm the exact requirement text and get a written scoping opinion. If confirmed, rewrite 12.4 and NFR-6 so the CVC is purged when the first authorization reaches a final outcome (or when the cascade ends). Remove CVC from incremental authorizations and use scheme stored-credential/incremental indicators instead. Update the 'CVC handling' confirmed decision and the NFR-6 test so it asserts the CVC is absent after authorization completes. | Keeps the NFR-5 Level 1 assessment achievable and avoids building a non-compliant Vault. |
| FND-004 | Either relax NFR-4 to a bounded RPO (for example, the replication lag) and add a Section 20.2 recovery procedure: reconcile in-window authorizations from acquirer reports and settlement files and void orphans, with idempotency rebuilt from those reports. Or keep RPO 0 and add synchronous cross-region commit for authorization outcomes, accepting the latency cost against NFR-2. Update the NFR-4 game day to fail under load and count lost commits. | Gives NFR-4 an honest, testable target and a defined recovery path for authorizations lost in the replication window. |
| FND-006 | Amend Section 12.3 and the Vault decision to at least two HSMs in different AZs at launch, with a third for maintenance headroom, and an HSM cluster in the DR region for NFR-4. Replace the 1,500 TPS trigger with an HSM throughput benchmark. Add 'HSM unavailable' to the Section 20.4 degradation table. | Card acceptance survives the loss of one AZ or one HSM, which protects NFR-3 and NFR-1. |
| FND-005 | In Sections 11.2 and 21.1, add a per-payment deadline. Each attempt's timeout becomes the remaining budget minus orchestration overhead, and a cascade starts only if enough budget remains. Otherwise, the owner explicitly redefines NFR-2, for example to exclude timeout-triggered cascades or to set a separate cascade p99. Correct the under-1% claim. | Makes NFR-2 achievable and testable without dropping FR-7. |
| FND-020 | In Section 16.2, match each provider's file incrementally on arrival and keep only cross-provider netting and payouts behind the 'all files' barrier. Publish each merchant's report once its providers have been matched. Define late or missing file handling (cut-off time, partial report flag, exception). Alternatively, restate NFR-8 with a deadline tied to the latest file. | NFR-8 becomes achievable, and late files are contained. |
| FND-016 | In Section 11.2, replace 'logged and discarded' with: a late approval on a superseded attempt triggers an automatic authorization reversal through the adapter and a reconciliation flag. Before cascading after a timeout, send a reversal or status query where the acquirer supports one. Remove the 'cannot create a duplicate charge' sentence. Add a late-approval case to the FR-7 cascade simulation in Section 26.1. | Prevents double holds on the cardholder and keeps attempt records consistent with acquirer state (FR-7, P1). |
| FND-021 | In Section 28, make go-live follow Phase 8 and the cohort-relevant parts of Phase 9 (PCI DSS RoC, NFR-1/2/4 tests for SG). Alternatively, document an explicit, owner-approved interim fraud control and risk acceptance. Update the Section 27 overall conclusion. | First-cohort launch meets FR-9 and NFR-5, with acceptance evidence in hand. |
| FND-046 | In Section 18.3, enforce MFA for every role with money-moving or credential rights (Owner, Admin, Finance, Support). In Section 18.4, require step-up MFA, notify all Owners and the previous account contact, apply a cooling-off hold (e.g. first payout to a new account held for review), and re-verify the account (verified_at). Separate refund and payout-account rights or require a second approver. | Closes the account-takeover-to-payout-fraud path and protects merchant funds under FR-13 and FR-17. |
| FND-009 | Check the per-partition throughput and LSI item-collection limits against AWS primary documentation. If they constrain the design, key the table on merchant_id#idempotency_key (or a sharded merchant prefix) and replace the LSI with a GSI or a separate query path for the back-office view. Restate the Section 9.3 arithmetic in WCU including item size. | Confirms or corrects NFR-1 capacity for the largest merchant before Phase 3. |
| FND-022 | In Section 7.2, add PARTIALLY_REFUNDED -> PARTIALLY_REFUNDED, CAPTURED -> CAPTURED (additional partial capture), REQUIRES_ACTION -> FAILED/SUCCEEDED, and a hold state or flag for REVIEW. Model settlement status separately from refund status (or add transitions from the refund states to SETTLED). Extend the FR-2 criterion with a positive test: every documented operation sequence from Sections 8, 11 and 16 completes. | FR-1, FR-2 and FR-15 are satisfiable together. |
| FND-023 | Restate FR-5 as: concurrent duplicates receive either the identical final response or 409 request_in_progress, and never a second downstream call. Extend the Section 26.1 FR-5 test with N parallel duplicates, a pod kill between lock and completion, and a Redis outage, asserting exactly one acquirer authorization each time. | FR-5 becomes consistent and actually demonstrated. |
| FND-036 | Mark Phase 3 card-on-file as 'Partially - Backlog item 2' in Sections 27 and 28. Add a dated milestone and owner for the TRID submission. Define a launch fallback (PAN-based stored credential with MIT/CIT indicators) in 12.5 until certification completes. | A realistic FR-14 delivery date and a defined launch fallback. |
| FND-039 | Add a table to 11.3 of Visa and Mastercard reattempt limits and the decline categories eligible for cross-acquirer cascade, confirmed by each acquirer. Split the pilot recovery rate by response class. | FR-7 can be implemented and tested. |
| FND-051 | Add a per-market data-transfer and localisation assessment to Section 19.1 (transfer mechanism, any localisation obligations for payment data, DR copy in Jakarta), make DPO pre-approval a Phase 1 gate, and widen Backlog item 4 to cover the lawful basis for consortium data sharing. | Avoids late re-architecture of data placement and protects NFR-7 compliance. |
| FND-011 | State in FR-8 and Section 10.3 that the tolerance is in percentage points of approval prior and is a hard filter applied before the weighted score. Treat the weekly review as a monitoring control. Update the FR-8 acceptance criterion to include boundary cases at the tolerance. | Makes FR-8 unambiguous and testable. |
| FND-012 | Re-grade the Section 27 rows for Card Vault, Idempotency Layer and Fraud Hook to 'Mostly ready' or 'Partial', listing the open items. Update the 'Depends on open design items?' column for Phases 2 and 3 in Section 28. | Build starts only on components that are actually settled. |

## Areas where no change is needed

- FND-013 Ledger is written in the same transaction as state changes, append-only and enforced by database roles: Atomic state, journal and outbox writes, append-only enforcement through database privileges, and a projection checked against postings meet FR-10 and principles P1, P5 and P7 without further change.
- FND-014 Intent is explicit: requirement IDs, ranked principles and a confirmed-decision register: Objectives, principles, decisions and acceptance criteria are stated clearly enough, and with traceable IDs, to review against.
- FND-053 Webhook dispatcher isolation and SSRF controls: Delivery isolation and DNS-pinned SSRF protection are specific and sufficient for FR-12 and NFR-9 at the stated merchant count.
- SA-001 (sections 14, 19): The atomic state, journal and outbox commit, append-only postings and the nightly projection check meet FR-10 and principles P1, P5 and P7. (see FND-013)
  - p.12 §14.3: "• Journals are written in the same PostgreSQL transaction as the payment state transition that causes them,"
- SA-002 (sections 15): Integer minor units with versioned ISO 4217 exponents, explicit conversion in adapters and a single half-to-even rounding step meet P4 and support exact matching for FR-11.
  - p.12 §15: "No floating-point type is used for amounts in any service, schema, or API payload."
- SA-003 (sections 17): Per-endpoint secrets, timestamped HMAC signatures, bounded retry with a dead-letter store and replay, per-endpoint isolation, and SSRF protection that pins the resolved address meet FR-12 and NFR-9 for webhook delivery.
  - p.13 §17: "• Endpoint safety. Endpoints must be HTTPS on port 443. The dispatcher resolves the hostname once at send"
- SA-004 (sections 15): Integer minor units with a versioned ISO 4217 exponent table, explicit adapter conversion that rejects any amount needing rounding, and single half-to-even fee rounding meet P4 and support FR-10 balancing. (see FND-013)
  - p.12 §15: "Where a provider expects a different exponent than ISO 4217 (for example, IDR as whole rupiah), the"
- SA-005 (sections 17): Webhook delivery semantics (event_id deduplication, object versioning, timestamped HMAC, bounded retry to DLQ with replay) match FR-12 and P7, and the FR-12 acceptance criterion checks them directly.
  - p.13 §17: "Merchants deduplicate on event_id and order by object version; delivery order is not guaranteed."
- SA-006 (sections 14, 19): Same-transaction journaling, revoked UPDATE/DELETE and nightly recomputation meet FR-10 and P5. (see FND-013)
  - p.12 §14.3: "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them,"
- SA-007 (sections 1): The volume baseline is arithmetically consistent: 10.5 M/day ÷ 86,400 s ≈ 122 TPS and 5.1 M ≈ 59 TPS. That gives a reliable basis for the NFR-1 capacity targets.
  - p.2 §1: "Payment attempts per day (average) 5.1 M 10.5 M"
- SA-008 (sections 21.2): The Aurora and MSK capacity claims rest on a measured spike (2,600 TPS sustained at 58% CPU on a smaller instance than production) and correct arithmetic (6 × 1.8 KB × 2,000 ≈ 21.6 MB/s). Both support NFR-1.
  - p.17 §21.2: "db.r7g.8xlarge sustained 2,600 TPS of the full write mix for two hours at 58% writer CPU"
  - p.17 §21.2: "About six 1.8 KB events per payment; 2,000 TPS ≈ 21.6 MB/s ingress across three kafka.m7g.xlarge"
- SA-009 (sections 14.2, 15): The example journals balance (9,720 + 280 = 10,000; 9,810 + 190 = 10,000), and the money representation (integer minor units, ISO 4217 exponent table, explicit no-rounding conversion in adapters) correctly supports FR-10 and P4.
  - p.11 §14.2: "Capture: Dr acquirer_receivable[ACQ-SG1,SGD] 10000 Cr merchant_payable[M-1234,SGD] 9720 Cr"
  - p.12 §15: "converts explicitly and rejects any amount that would need rounding."
- SA-010 (sections 14.3, 19): The single-transaction journal, state and outbox write, revoked UPDATE/DELETE and nightly projection recomputation meet FR-10 and P5 under load and partial failure. (see FND-013)
  - p.12 §14.3: "There is no dual write between the payment store and the ledger."
- SA-011 (sections 17): Per-endpoint caps, circuit breakers and address-pinned SSRF protection keep webhook delivery isolated and safe (FR-12, NFR-9). (see FND-053)
  - p.13 §17: "Each endpoint has a cap of 20 in-flight deliveries and its own circuit breaker, so a failing endpoint"
- SA-012 (sections 18.5): Back-office write actions require just-in-time elevation with a second approver and hardware MFA, which meets P9 and P10 for internal staff.
  - p.14 §18.5: "write actions (manual refunds, payout holds, merchant suspension) require just-in-time elevation"
- SA-013 (sections 20.4): MSK and Redis outages degrade to documented safe behaviour (the outbox buffers in Aurora; DynamoDB serves idempotency), so payment acceptance continues (NFR-3).
  - p.17 §20.4: "Outbox accumulates in Aurora; relay drains on recovery; webhooks delayed, payments unaffected"

## Unresolved issues and next steps

- FND-002 (governance decision): Fraud Hook detokenises PAN, breaking P2, the CDE boundary and Vault access rules (FND-002) Next step (Head of Payments Security with Risk lead): Decide between a hashed identifier and CDE expansion, and settle FRV-1's identifier support before the Phase 8 contract.
- FND-029 (needs investigation): CVC retained after authorization, citing a PCI DSS allowance that appears not to exist (FND-029) Next step (PCI compliance lead with the QSA): Get a written interpretation of v4.0 Req. 3.2.1/3.3.2 applied to Section 12.4 before Phase 2 (CDE) begins.
- FND-004 (governance decision): Zero RPO for NFR-4 cannot be met with asynchronous Aurora Global replication and unreplicated idempotency state (FND-004) Next step (Head of Platform Engineering): Decide whether to accept a bounded RPO or fund a synchronous design, and update NFR-4 and Section 20.2.
- FND-006 (governance decision): A single CloudHSM in one AZ is a single point of failure for every card authorization (FND-006) Next step (Vault tech lead with Head of Platform Engineering): Revisit the one-HSM decision, cost multi-AZ and DR-region HSMs, and benchmark unwrap throughput.
- FND-021 (governance decision): First cohort goes live before the Fraud Hook, the PCI DSS assessment and the Section 26 test plan (FND-021) Next step (Programme director with Head of Risk): Re-sequence go-live gates, or sign a time-boxed risk acceptance for the interim fraud and PCI posture.
- FND-009 (needs investigation): DynamoDB per-partition capacity and LSI layout claims for the largest merchant are unverified (FND-009) Next step (Payments API tech lead): Verify the DynamoDB partition and LSI limits and run a single-merchant hot-key load test.
- FND-023 (needs testing): FR-5 concurrency clause conflicts with the 409 behaviour, and the replay test only checks sequential duplicates (FND-023) Next step (QA lead, Payments Core): Add concurrency, crash and Redis-outage cases to the FR-5 test plan.
- FND-036 (governance decision): Network tokens 'from launch' and Phase 3 marked ready while the token requestor application is unsubmitted (FND-036) Next step (Head of Card Partnerships): Submit the VTS/MDES token-requestor applications and get scheme lead times to set the Phase 3 critical path.
- FND-039 (needs investigation): Cross-acquirer cascading of issuer soft declines is assumed scheme-compliant without stated limits (FND-039) Next step (Payments Core routing lead): Get current scheme reattempt rules from ACQ-SG2 and the scheme manuals.
- FND-051 (governance decision): Cross-border transfer and localisation basis for personal and payment data is not addressed (FND-051) Next step (Data Protection Officer with Legal (per market)): Assess cross-border transfer and localisation obligations for each market and approve or amend Section 19.1 placement.

Research questions left unanswered:
- RQ-009: What is DynamoDB's documented per-partition write throughput (1,000 WCU/s or 10,000), and how do tables with a local secondary index behave (10 GB item-collection limit, no split for heat)? Can a merchant_id partition key absorb about 1,800 WCU/s from the largest merchant?
- RQ-010: Do PCI DSS v4.0 Requirements 3.2.1, 3.3.1 and 3.3.2 permit a merchant or service provider to keep the CVC, even encrypted, after authorization until settlement or for 72 hours, for cascades and incremental authorizations?
- RQ-011: Do Visa and Mastercard reattempt rules allow cascading a response-code-05 decline to a different acquirer, and how do Visa decline categories and the Mastercard Merchant Advice Code rules treat reattempts across acquirers on the same card?
- RQ-014: Do Indonesian (Bank Indonesia payment-system and GR 71/2019) or other market rules require domestic processing or storage of payment transaction data? Does that conflict with placing all primary data in ap-southeast-1, and does NFR-7 cover cross-border transfer obligations under the listed PDP laws?
- RQ-015: Does a single CloudHSM in one AZ (Section 12.3) support about 1,100 card TPS of detokenise unwraps, plus cascade and Fraud Hook calls, under the 99.95% availability target? Since every acquirer path depends on the Vault, does treating HSM failure as 'retryable' achieve anything?

## Evidence limitations

- DOC-design_v1: native PDF block not sent because the configured model backend accepts text only. Impact: figures, diagrams and tables rendered as images were not visible to the model; the review is based on the extracted text (DEG-001)
- No external research was possible: no tool gateway (--no-tools, or every server is disabled). Impact: doc-only review: every question that needs external evidence is reported as a validation need, and confidence is lowered (DEG-002)
- FND-009's recommendation appears to reverse approved decision AD-006 (24 Confirmed Decisions - Idempotency store) without a 'challenges' label. Impact: the conflict is not declared and not backed by the two evidence items a challenge needs; check it against the decision before acting on it (DEG-003)

## Evidence register

| ID | Type | Source | Retrieved | Cited |
|---|---|---|---|---|
| EV-001 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-002 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-003 | doc | doc:DOC-design_v1#p4/s3 | - | yes |
| EV-004 | doc | doc:DOC-design_v1#p7/s9.1 | - | yes |
| EV-005 | doc | doc:DOC-design_v1#p11/s13.1 | - | yes |
| EV-006 | doc | doc:DOC-design_v1#p10/s12.2 | - | yes |
| EV-007 | doc | doc:DOC-design_v1#p3/s3 | - | yes |
| EV-008 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-009 | doc | doc:DOC-design_v1#p3/s2.2 | - | no |
| EV-010 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-011 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-012 | doc | doc:DOC-design_v1#p16/s20.2 | - | yes |
| EV-013 | doc | doc:DOC-design_v1#p17/s20.2 | - | yes |
| EV-014 | doc | doc:DOC-design_v1#p17/s21.1 | - | yes |
| EV-015 | doc | doc:DOC-design_v1#p9/s10.5 | - | yes |
| EV-016 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-017 | doc | doc:DOC-design_v1#p9/s11.1 | - | yes |
| EV-018 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-019 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-020 | doc | doc:DOC-design_v1#p10/s12.1 | - | yes |
| EV-021 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-022 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-023 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-024 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-025 | doc | doc:DOC-design_v1#p14/s18.4 | - | yes |
| EV-026 | doc | doc:DOC-design_v1#p14/s18.4 | - | no |
| EV-027 | doc | doc:DOC-design_v1#p14/s18.3 | - | yes |
| EV-028 | doc | doc:DOC-design_v1#p8/s9.3 | - | yes |
| EV-029 | doc | doc:DOC-design_v1#p8/s9.3 | - | yes |
| EV-030 | doc | doc:DOC-design_v1#p18/s24 | - | yes |
| EV-031 | doc | doc:DOC-design_v1#p19/s25 | - | yes |
| EV-032 | doc | doc:DOC-design_v1#p2/s2.1 | - | yes |
| EV-033 | doc | doc:DOC-design_v1#p9/s10.3 | - | yes |
| EV-034 | doc | doc:DOC-design_v1#p18/s24 | - | yes |
| EV-035 | doc | doc:DOC-design_v1#p20/s27 | - | yes |
| EV-036 | doc | doc:DOC-design_v1#p21/s27 | - | yes |
| EV-037 | doc | doc:DOC-design_v1#p12/s14.3 | - | yes |
| EV-038 | doc | doc:DOC-design_v1#p16/s19 | - | yes |
| EV-039 | doc | doc:DOC-design_v1#p3/s3 | - | yes |
| EV-040 | doc | doc:DOC-design_v1#p2/s2 | - | yes |
| EV-041 | inference | inference:EV-041 from EV-001, EV-002, EV-003, EV-004 | - | yes |
| EV-042 | inference | inference:EV-042 from EV-005, EV-006, EV-007 | - | yes |
| EV-043 | inference | inference:EV-043 from EV-008, EV-009, EV-010 | - | yes |
| EV-044 | inference | inference:EV-044 from EV-011, EV-012 | - | yes |
| EV-045 | inference | inference:EV-045 from EV-014, EV-015, EV-016, EV-017 | - | yes |
| EV-046 | inference | inference:EV-046 from EV-018, EV-019, EV-020, EV-021 | - | yes |
| EV-047 | inference | inference:EV-047 from EV-022, EV-023, EV-024 | - | yes |
| EV-048 | inference | inference:EV-048 from EV-025, EV-026, EV-027 | - | yes |
| EV-049 | inference | inference:EV-049 from EV-028, EV-029 | - | yes |
| EV-050 | inference | inference:EV-050 from EV-030, EV-031 | - | yes |
| EV-051 | inference | inference:EV-051 from EV-035, EV-036, EV-001, EV-005, EV-008, EV-018, EV-031 | - | yes |
| EV-052 | doc | doc:DOC-design_v1#p7/s9.1 | - | no |
| EV-053 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-054 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-055 | doc | doc:DOC-design_v1#p11/s13.1 | - | yes |
| EV-056 | doc | doc:DOC-design_v1#p10/s12.1 | - | yes |
| EV-057 | doc | doc:DOC-design_v1#p16/s20.2 | - | yes |
| EV-058 | doc | doc:DOC-design_v1#p17/s21.1 | - | no |
| EV-059 | doc | doc:DOC-design_v1#p9/s10.5 | - | no |
| EV-060 | doc | doc:DOC-design_v1#p20/s26.2 | - | yes |
| EV-061 | doc | doc:DOC-design_v1#p12/s16.1 | - | yes |
| EV-062 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-063 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-064 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-065 | doc | doc:DOC-design_v1#p6/s7.2 | - | yes |
| EV-066 | doc | doc:DOC-design_v1#p6/s7.2 | - | yes |
| EV-067 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-068 | doc | doc:DOC-design_v1#p2/s2.1 | - | yes |
| EV-069 | doc | doc:DOC-design_v1#p7/s9.1 | - | yes |
| EV-070 | doc | doc:DOC-design_v1#p19/s26.1 | - | yes |
| EV-071 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-072 | doc | doc:DOC-design_v1#p10/s12.1 | - | yes |
| EV-073 | doc | doc:DOC-design_v1#p8/s9.3 | - | no |
| EV-074 | doc | doc:DOC-design_v1#p2/s1 | - | yes |
| EV-075 | doc | doc:DOC-design_v1#p9/s10.3 | - | yes |
| EV-076 | doc | doc:DOC-design_v1#p3/s2.1 | - | yes |
| EV-077 | doc | doc:DOC-design_v1#p12/s14.3 | - | yes |
| EV-078 | inference | inference:EV-078 from EV-002, EV-003, EV-052 | - | yes |
| EV-079 | inference | inference:EV-079 from EV-053, EV-054 | - | yes |
| EV-080 | inference | inference:EV-080 from EV-011, EV-057 | - | yes |
| EV-081 | inference | inference:EV-081 from EV-058, EV-059, EV-060 | - | yes |
| EV-082 | inference | inference:EV-082 from EV-061, EV-022, EV-023 | - | yes |
| EV-083 | inference | inference:EV-083 from EV-065, EV-066, EV-067 | - | yes |
| EV-084 | inference | inference:EV-084 from EV-018, EV-072 | - | yes |
| EV-085 | inference | inference:EV-085 from EV-073, EV-074 | - | yes |
| EV-086 | inference | inference:EV-086 from EV-077 | - | yes |
| EV-087 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-088 | doc | doc:DOC-design_v1#p8/s9.3 | - | yes |
| EV-089 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-090 | doc | doc:DOC-design_v1#p8/s9.2 | - | no |
| EV-091 | doc | doc:DOC-design_v1#p16/s20.2 | - | no |
| EV-092 | doc | doc:DOC-design_v1#p19/s25 | - | yes |
| EV-093 | doc | doc:DOC-design_v1#p2/s1 | - | yes |
| EV-094 | doc | doc:DOC-design_v1#p9/s11.1 | - | yes |
| EV-095 | doc | doc:DOC-design_v1#p9/s11.3 | - | yes |
| EV-096 | doc | doc:DOC-design_v1#p16/s19.1 | - | yes |
| EV-097 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-098 | inference | inference:EV-098 from EV-008, EV-087 | - | yes |
| EV-099 | inference | inference:EV-099 from EV-055, EV-006, EV-056 | - | yes |
| EV-100 | inference | inference:EV-100 from EV-073, EV-088, EV-089 | - | no |
| EV-101 | inference | inference:EV-101 from EV-090, EV-004 | - | yes |
| EV-102 | inference | inference:EV-102 from EV-058, EV-059, EV-017 | - | no |
| EV-103 | inference | inference:EV-103 from EV-011, EV-091 | - | no |
| EV-104 | inference | inference:EV-104 from EV-061, EV-022, EV-023 | - | no |
| EV-105 | inference | inference:EV-105 from EV-030, EV-031 | - | yes |
| EV-106 | inference | inference:EV-106 from EV-062, EV-092 | - | yes |
| EV-107 | inference | inference:EV-107 from EV-018, EV-020, EV-093 | - | no |
| EV-108 | inference | inference:EV-108 from EV-094, EV-095 | - | yes |
| EV-109 | doc | doc:DOC-design_v1#p8/s9.2 | - | no |
| EV-110 | doc | doc:DOC-design_v1#p11/s13.1 | - | yes |
| EV-111 | doc | doc:DOC-design_v1#p9/s11.2 | - | no |
| EV-112 | doc | doc:DOC-design_v1#p17/s20.2 | - | no |
| EV-113 | doc | doc:DOC-design_v1#p14/s18.4 | - | yes |
| EV-114 | doc | doc:DOC-design_v1#p4/s3 | - | yes |
| EV-115 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-116 | doc | doc:DOC-design_v1#p8/s9.3 | - | no |
| EV-117 | doc | doc:DOC-design_v1#p12/s14.3 | - | yes |
| EV-118 | doc | doc:DOC-design_v1#p16/s19 | - | yes |
| EV-119 | doc | doc:DOC-design_v1#p13/s17 | - | yes |
| EV-120 | doc | doc:DOC-design_v1#p13/s17 | - | yes |
| EV-121 | inference | inference:EV-121 from EV-109, EV-002, EV-052 | - | no |
| EV-122 | inference | inference:EV-122 from EV-054, EV-111 | - | yes |
| EV-123 | inference | inference:EV-123 from EV-018, EV-072, EV-093 | - | yes |
| EV-124 | inference | inference:EV-124 from EV-112, EV-057, EV-011 | - | yes |
| EV-125 | inference | inference:EV-125 from EV-008, EV-115 | - | yes |
| EV-126 | inference | inference:EV-126 from EV-116, EV-088, EV-089 | - | yes |
| EV-127 | inference | inference:EV-127 from EV-022, EV-023, EV-061 | - | no |
| EV-128 | inference | inference:EV-128 from EV-058, EV-059 | - | no |

## Review coverage

| Criterion | Outcome | Findings | Note |
|---|---|---|---|
| design_intent | findings | FND-014, FND-011, FND-004, FND-036, FND-012 | Requirements, principles, decisions and backlog are clearly stated (a strength). Gaps: the FR-8 tolerance is ambiguous, NFR-4 contradicts the DR design, and Section 27 overstates readiness. |
| fitness_for_objectives | findings | FND-001, FND-002, FND-029, FND-004, FND-005, FND-006, FND-020, FND-046, FND-009, FND-012, FND-013 | Checked each major element against its FR or NFR. Idempotency, Vault, HSM, latency budget, DR, reconciliation timing and the payout-change control have material fitness issues. The ledger, money representation and webhooks are fit for purpose. |
| requirement_completeness | findings | FND-016, FND-020, FND-021, FND-022, FND-006 | Gaps found: no reversal path for late approvals, no late or missing settlement file handling, missing state transitions, missing go-live gates, and no HSM degradation path. The backlog (Section 25) and readiness table (Section 27) were checked before raising them. |
| internal_consistency | findings | FND-001, FND-016, FND-002, FND-004, FND-005, FND-020, FND-021, FND-023, FND-036, FND-006, FND-011, FND-013 | Requirements, principles, decisions, flows and numbers were cross-checked across Sections 2-28. Contradictions found in idempotency scoping, CDE scope, RPO, the latency budget, the reconciliation timeline, the phase plan and network-token readiness. Ledger arithmetic and the latency sum (1,338 ms, 238 ms overhead) are internally correct. |
| claims_and_external_constraints | findings | FND-029, FND-002, FND-009, FND-005, FND-004, FND-020, FND-006, FND-039, FND-051 | Checked PCI DSS claims, DynamoDB limits, latency, RPO and reconciliation arithmetic, HSM topology and scheme reattempt rules. Volume, MSK, Aurora and ledger arithmetic are sound. |
| security_and_privacy | findings | FND-001, FND-002, FND-046, FND-029, FND-051, FND-013, FND-053 | Checked CDE scope, detokenise access, SAD retention, idempotency tenancy, admin-plane authentication and payout controls, audit, logging and cross-border data placement. Back-office access and API-key hashing are sound. |
| scalability_and_failure_modes | findings | FND-001, FND-016, FND-006, FND-004, FND-009, FND-020, FND-005, FND-013, FND-053 | Checked cascade/timeout semantics, HSM topology, DR/RPO, DynamoDB partitioning, reconciliation timing, the latency budget, Aurora/MSK capacity and dependency degradation. |
| assumptions_and_dependencies | findings | FND-002, FND-001, FND-020, FND-036, FND-021, FND-006, FND-051 | Checked backlog items against confirmed decisions and build phases, vendor dependencies (FRV-1, token service provider), idempotency key uniqueness and data-placement premises. |
| verifiability | findings | FND-004, FND-005, FND-022, FND-023, FND-009, FND-011 | Each Section 26 criterion was checked against its requirement. The FR-2, FR-5, FR-8 and NFR-1 criteria cannot demonstrate their requirements as written, and the NFR-2 and NFR-4 criteria will fail by design. The other criteria (FR-3, FR-4, FR-10 to FR-17, NFR-3, NFR-5 to NFR-7, NFR-9 to NFR-12) are adequate. |
| decision_preservation | findings | FND-001, FND-002, FND-029, FND-006, FND-036, FND-013 | The Fraud Hook PAN access and the Redis key scoping break principles P2 and P3. FND-006 explicitly challenges the one-HSM decision, citing three document items. The CVC handling and network-token decisions rest on unverified or pending items. |
| operability_and_governance | findings | FND-004, FND-020, FND-051 | Checked DR runbook scope, reconciliation SLA operations and privacy governance gates. Payout freeze on projection discrepancy and stuck-payment escalation are adequately specified. |

## Run details

| | |
|---|---|
| Run | rehearsal_concurrent_1 (started 2026-10-03T02:09:22Z) |
| Outcome | completed_degraded |
| Model | requested claude-opus-5-5; served claude-opus-5-5; effort per-stage (extra.model.effort_by_stage) |
| Persona | generalist_architect |
| Tool transport | live |
| Research stop | tool_failure (error): no_tools; 0 iteration(s); 0 cited of 0 retrieved |
| Tool calls | none |
| Tokens | input 344584, cached 0, output 148957; cost ~$5.74 (price table 2026-09-25) |
| Extractor | pdfplumber 0.11.10 |
| Config sha256 | bdec44450f5811185fe0da49f4d81ff184e14af203b44c42f8d2f947e42ccfab |
| Prompt bundle sha256 | 6f0ee28ab9acf35152a2d4456207a8a068222149422e66d801c8195455c28ba7 |
| Git commit | d008a74d42f0ebc9e0843373da62ba439c3d591f |
| Fault schedule | none |
| Model fallbacks | 0 |
| Canonical text DOC-design_v1 | sha256 ad0bb891f073f14325b6ba716d58070d6b074ebaef9a9c64432138b89b64ec3c |
