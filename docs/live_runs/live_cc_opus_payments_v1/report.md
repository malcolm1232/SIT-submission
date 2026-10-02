# Design review: Serindit Pay — Merchant Payment Orchestration Platform

| | |
|---|---|
| Review | REV-live_cc_opus_payments_v1 (full review) |
| Under review | DOC-design_v1: Serindit Pay — Merchant Payment Orchestration Platform v1.0, 21 pages |
| Verdict | **fit with conditions** (confidence 0.68, medium) |
| Tools used | none |
| Tools disabled | mcp-internet-search, mcp-research-information, mcp-browser-automation-pw, mcp-document-intelligence |
| Reporting threshold | severity low and above (0 finding(s) in the appendix) |

> No external research was possible or used in this run: every finding rests on the document alone.


## Design intent

MPOP is the Serindit Pay Merchant Payment Orchestration Platform. It accepts payment requests from merchants, routes each one to an acquirer, e-wallet provider or bank-transfer rail, and accounts for every resulting money movement until the funds are settled to the merchant. It replaces five per-market integration stacks that share no routing and no ledger and that reconcile by spreadsheet. Scope covers five Southeast Asian markets, about 15,000 active merchants and a 2027 peak of 2,000 create-payment TPS. It includes one merchant API, rule-based routing with cascading, idempotency, a tokenising card vault that confines PCI DSS scope, a synchronous fraud hook, a double-entry ledger, daily reconciliation, payouts, signed webhooks and a merchant admin plane. Disputes and chargebacks, KYB onboarding, 3DS server internals, checkout UIs and lending products are out of scope. The document says it is written to implementation level, and Section 27 assesses where that is not yet true.

Objectives:
- Replace five per-market integration stacks with one governed payment path shared by all merchants and markets.
- FR-1: Provide one versioned merchant API covering create, authorize, capture, void, refund (full and partial) and retrieve for every payment method in Section 4.
- FR-2: Keep every payment in exactly one state of the Section 7 state machine, allow only the permitted transitions, and persist each transition before acknowledging it.
- FR-3: Support each market's payment methods through adapters that implement a common Connector interface.
- FR-5: Make mutating calls idempotent per (merchant, Idempotency-Key): at most one downstream effect and an identical response, including under concurrent duplicates. Reuse of a key with a different body returns 422.
- FR-6: Select an acquirer or provider for each attempt from an eligible set based on method, market, currency, scheme, BIN country and the merchant's contracts.
- FR-7: Cascade retryable card outcomes to the next eligible acquirer, with up to two additional attempts and never where scheme rules prohibit it.
- FR-8: Prefer the lowest-cost eligible acquirer unless doing so reduces the expected authorization rate by more than 2%.
- FR-9: Score every card payment, and every e-wallet payment above the merchant's threshold, for fraud before authorization.
- FR-10: Record every movement of money as a balanced double-entry journal.
- FR-11: Reconcile every settlement line daily by three-way match and raise an exception for every unmatched or mismatched line.
- FR-12: Deliver a signed webhook to the merchant for every payment, refund and payout state change.
- FR-13: Provide a merchant admin plane for users and roles, API keys, webhooks, refunds, reports and payout bank details.
- FR-14: Use stored credentials with MIT/CIT indicators for card-on-file and recurring payments, and use network tokens where the issuer supports them.
- FR-15: Support refunds for every payment method, falling back to a bank payout where a method has no refund API.
- FR-16: Produce an audit record for every merchant API mutation and every admin-plane action.
- FR-17: Pay out merchant balances on the contracted schedule (T+1, T+2 or weekly).
- NFR-1: Sustain 2,000 create-payment TPS for four hours without degrading latency.
- NFR-2: Keep card authorization p99 at or below 1,500 ms end-to-end including cascade, and orchestration overhead p99 at or below 250 ms.
- NFR-3: Reach at least 99.95% monthly availability of the merchant payment API.
- NFR-4: Achieve RPO zero for authorized payments and ledger postings, including on loss of a region, and RTO 30 minutes.
- NFR-8: Auto-match at least 99.9% of settlement lines and publish settlement reports for day T by 08:00 SGT on T+1.
- NFR-9: Use per-merchant rate limits so that no single merchant degrades latency or availability for others.
- NFR-10: Onboard a new acquirer or provider through an adapter and configuration only, with no core changes.
- NFR-11: Make every payment traceable end-to-end by payment_id within 5 seconds of each event.
- P1: One payment, one truth: the payment record and the ledger are the source of truth.
- P2: Card data stays in the Vault: PAN and SAD leave it only over the Card Adapter's connection to an acquirer, and all other services handle tokens only.
- P3: Idempotency is scoped to (merchant, key).
- P4: Money is integers: amounts are integer minor units with an ISO 4217 code, never floating point.
- P5: The ledger is append-only, and corrections are new journals.
- P6: Adapters absorb provider differences, and the core never branches on provider identity.
- P7: At-least-once delivery with exactly-once effect, through consumer deduplication.
- P8: Fail closed on security and degrade gracefully on enrichment.
- P9: Least privilege and separation of duties, with money-moving permissions separated from configuration permissions.
- P10: Everything is auditable and reconstructable.

Constraints:
- NFR-5: MPOP must be assessed as a PCI DSS v4.0 Level 1 service provider, with the CDE limited to the components that Section 12.2 lists as in scope.
- NFR-6: Sensitive authentication data must be handled per PCI DSS v4.0 Requirements 3.2.1 and 3.3.2: encrypted, held in the Vault, and deleted at settlement.
- NFR-7: Personal data must comply with SG PDPA 2012, MY PDPA 2010, ID Law 27/2022, TH PDPA 2019 and PH DPA 2012, including purpose limitation, retention limits and access logging.
- NFR-12: Audit records must be immutable and retained for five years.
- FR-7: Card scheme reattempt rules must never be violated by cascading.
- The ten foundational principles are binding: where a later section conflicts with one, the principle wins.
- All workloads and primary data stores run in AWS ap-southeast-1 across three AZs. The CDE runs in a separate AWS account, VPC and EKS cluster, and ap-southeast-3 is used for DR only.
- Out of scope: dispute case management (ingested as ledger events only), merchant onboarding and KYB (Merchant Risk platform), 3DS server internals (third party), checkout UIs and SDKs, and lending, BNPL and instalment products.
- ACQ-PH1 retires API v2 in Q3 2027, so the adapter must migrate to v3 before then.
- Build schedule: the first merchant cohort (Singapore, cards and PayNow) goes live after Phase 7, and the other markets follow at four-week intervals.

Key assumptions:
- 2027 volume targets are 15,000 merchants, 10.5 M attempts per day, 2,000 peak TPS on campaign days, and the largest single merchant at 45% of peak (about 900 TPS).
- Card outcome mix follows the 2025 baseline (88.1% approved, 8.1% hard declines, 3.8% retryable), and cascading recovers about 31% of retryable outcomes, based on an ACQ-SG1 to ACQ-SG2 pilot.
- Fewer than 1% of card payments cascade, so cascade latency sits above p99 and is left out of the latency budget.
- A single DynamoDB partition sustains up to 10,000 WCU per second, so keying idempotency records by merchant_id is within capacity for the largest merchant.
- PCI DSS v4.0 Requirements 3.2.1 and 3.3.2 permit encrypted CVC retention until settlement, for cascade re-presentation and incremental authorizations.
- One CloudHSM at launch is sufficient. A second will be added when sustained card volume exceeds 1,500 TPS, and daily backups allow an HSM to be recreated in any AZ.
- FRV-1's consortium velocity graph needs the full PAN, which the Fraud Hook obtains through Vault detokenise, while the Fraud Hook is still classed as out of CDE scope.
- Network tokens (VTS/MDES) will be available from launch, although the Token Requestor application has not yet been submitted.
- A db.r7g.8xlarge spike sustained 2,600 TPS of the full write mix, and production uses db.r7g.12xlarge for headroom.
- Reconciliation takes 45 minutes plus 15 minutes for reports at 2025 volume, and starts only after all expected settlement files for the day have arrived.
- Aurora Global Database cross-region replication is asynchronous with typical lag under one second. DynamoDB, Redis and MSK state is recreated empty on regional failover.
- The first merchant cohort does not need the Admin API schemas or the dispute module: it will use the portal, and Finance Operations will handle disputes manually.

Located at: p.1 §1, p.1 §1, p.2 §1.

## Fitness for purpose

**Fit with conditions** (confidence 0.68). The core architecture fits the design's purpose of replacing five per-market stacks with one governed payment path. It has a single orchestrated path, adapter isolation, a token-only core, and a ledger written atomically with state through an outbox (FND-021). Those parts need no change. The design is not ready to build as written, though. FND-001 (critical) lets one merchant receive another merchant's payment data and breaks FR-5 and P3. Nine high findings show where the design contradicts itself or cannot meet its own targets: the Fraud Hook detokenises the PAN despite P2 and the CDE scope (FND-002); a timed-out attempt can still be approved, so cascading can authorise a customer twice (FND-003); asynchronous cross-region replication cannot give the zero RPO in NFR-4 (FND-005); waiting for every settlement file makes the 08:00 SGT deadline in NFR-8 impossible (FND-006); the state machine has gaps (FND-007); a single HSM is a point of failure (FND-008); the payout bank account can be changed without strong controls (FND-009); and card traffic goes live before the controls are in place (FND-010). Most of these can be fixed by changing the text. FND-005, FND-006, FND-008 and FND-010 need an accountable decision to change either a requirement or the architecture. FND-004 needs a QSA ruling. None of these requires redesigning the platform, which is why the verdict is conditional rather than not_fit. However, FR-5/P3, NFR-4 and NFR-8 are not met as written, and the Section 27 'Ready' ratings for Idempotency, Card Vault, Retry Engine and Payouts should be withdrawn until the conditions below are closed. Confidence is lowered because no external research was possible (DEG-009) and figures could not be inspected (DEG-001).

Conditions:
- Before Phase 3, scope the Redis fast-path key to (merchant_id, idempotency_key) and check the request-body hash on every fast-path hit, returning 422 on a mismatch. Extend the FR-5 acceptance test to cover concurrent duplicates and the same key used by two different merchants. (FND-001, FND-018)
- Before Phase 2 or 8, remove PAN detokenisation from the Fraud Hook and send FRV-1 only the token, BIN, last 4 or the HMAC fingerprint. If FRV-1 truly needs the PAN, bring the Fraud Hook into the CDE under its own service identity, update P2, Section 12.1 and the Section 12.2 scope, and do not send any data until the FRV-1 DPA is signed. (FND-002, FND-016)
- Before Phase 4, define how timeouts are handled. Either send a reversal or void to the first acquirer before cascading, or do not cascade on a timeout. Record late responses rather than discarding them, and reconcile orphaned authorisations. Then restate the cascade latency budget against the 3.8% retryable baseline and the 2,500 ms timeout, or redefine NFR-2. (FND-003, FND-011)
- An accountable owner decides between NFR-4 and AD-004: either relax the RPO for an unplanned regional loss to the measured replication lag, or adopt a synchronous or quorum cross-region write path. In either case, persist the idempotency key, request hash and merchant_id with the payment so that idempotency can actually be rebuilt after failover. (FND-005)
- An accountable owner decides between NFR-8 and AD-016: either add a cut-off time with incremental or per-provider matching and a late-file path, or move the publication deadline. Show with a 2027-volume replay that the chosen deadline can be met. (FND-006)
- Fix the state machine so that payments that have been refunded or partially refunded can still be settled. Support multiple partial captures and release of the uncaptured remainder. Make the authorisation memo-ledger wording consistent across Sections 8 and 14.3, and add refund and FX journal examples. (FND-007)
- Before CVC storage is built, obtain written confirmation from a QSA (and from the acquirers) that encrypted CVC may be kept after authorisation for cascades and incremental authorisations. Otherwise redesign Section 12.4 and AD-009. (FND-004)
- Deploy CloudHSM across at least two AZs at launch, or record an explicit acceptance of the availability risk against NFR-3. Stop treating a Vault 503 as a retryable outcome that consumes cascade attempts and reattempt counters. (FND-008)
- Require step-up MFA for payout bank account changes, require a second approver or a cooling-off hold, and notify the Owner and all Finance users. Enforce MFA for every role that can move money. (FND-009)
- Make the fraud scoring required by FR-9, the PCI DSS RoC, the NFR-1 and NFR-2 load tests and the NFR-4 DR game day go-live gates for the first card cohort. Alternatively, a named accountable role must formally accept each gap. (FND-010)
- Before Phase 3 sign-off, verify the DynamoDB per-partition and item-collection limits for the largest merchant. Specify idempotency failure paths: orphaned IN_PROGRESS locks while a payment is in CREATED, the fail-open versus fail-closed rule when DynamoDB is unavailable, and the risk of order-ID keys being reused after 24 hours. (FND-012, FND-013)

| Objective | Verdict | Findings |
|---|---|---|
| Section 1 objective: one governed payment path replacing five per-market stacks | fit with conditions | FND-021, FND-002, FND-010 |
| FR-1 | fit with conditions | FND-007 |
| FR-2 | fit with conditions | FND-007, FND-021 |
| FR-3 | fit | - |
| FR-5 | not fit | FND-001, FND-005, FND-012, FND-013, FND-018 |
| FR-6 | fit | - |
| FR-7 | fit with conditions | FND-003, FND-015 |
| FR-8 | fit with conditions | FND-017 |
| FR-9 | fit with conditions | FND-002, FND-010 |
| FR-10 | fit with conditions | FND-021, FND-007, FND-019 |
| FR-11 | fit with conditions | FND-007, FND-006 |
| FR-12 | fit with conditions | FND-018 |
| FR-13 | fit with conditions | FND-009 |
| FR-14 | fit with conditions | FND-014 |
| FR-15 | fit with conditions | FND-019 |
| FR-16 | fit | - |
| FR-17 | fit with conditions | FND-006, FND-019 |
| NFR-1 | fit with conditions | FND-012, FND-010 |
| NFR-2 | fit with conditions | FND-011, FND-003 |
| NFR-3 | fit with conditions | FND-008, FND-012 |
| NFR-4 | not fit | FND-005 |
| NFR-8 | not fit | FND-006, FND-007 |
| NFR-9 | fit with conditions | FND-018 |
| NFR-10 | fit | - |
| NFR-11 | fit | - |
| P1 | fit with conditions | FND-021, FND-003 |
| P2 | fit with conditions | FND-002 |
| P3 | not fit | FND-001 |
| P4 | fit | - |
| P5 | fit | FND-021 |
| P6 | fit | - |
| P7 | fit | FND-021 |
| P8 | fit with conditions | FND-013, FND-008 |
| P9 | fit with conditions | FND-002, FND-009 |
| P10 | fit with conditions | FND-003, FND-020 |

What would change this verdict: Toward fit: a revised document that makes the refinement_now changes for FND-001, FND-002, FND-003, FND-007, FND-009, FND-011, FND-013, FND-017, FND-018 and FND-019; recorded governance decisions on FND-005, FND-006, FND-008 and FND-010; a written QSA position on CVC retention (FND-004); and verified DynamoDB limits for the largest merchant (FND-012). Toward not_fit: a QSA ruling that encrypted CVC may not be kept after authorisation while acquirers still require it for cascades and incremental authorisations; a governance decision that keeps zero RPO on regional loss without changing the replication architecture; or primary evidence that DynamoDB per-partition limits are below the largest merchant's peak write load.

## Strengths

### FND-021 Ledger written atomically with state changes through a transactional outbox, append-only and with enforced balance

- **strength** · confidence 0.85 (high) · rank 21
- Disposition: **no change**

Section 14.3 writes each journal in the same PostgreSQL transaction as the state transition and its outbox row, which removes dual writes and supports P1 and P7. Section 19 revokes UPDATE and DELETE on journal and posting tables from all application roles, which enforces P5 in the database. Section 14.1 enforces the per-currency balance with a deferred trigger and re-verifies it nightly. The worked journals in Section 14.2 balance (10,000 = 9,720 + 280; 9,810 + 190 = 10,000), giving FR-10 a sound and verifiable foundation.

- Where: p.12 §14.3 (FR-10): "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them,"
- Where: p.16 §19 (FR-10): "journal and posting have UPDATE and DELETE revoked from every application role; the migration role is the only role"
- Where: p.11 §14.1 (FR-10): "enforced by a deferred constraint trigger at commit and re-verified nightly by a full recomputation."
- Evidence EV-080 (doc, supports): "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them," [doc:DOC-design_v1#p12/s14.3]
- Evidence EV-081 (doc, supports): "journal and posting have UPDATE and DELETE revoked from every application role; the migration role is the only role" [doc:DOC-design_v1#p16/s19]
- Evidence EV-082 (doc, supports): "enforced by a deferred constraint trigger at commit and re-verified nightly by a full recomputation." [doc:DOC-design_v1#p11/s14.1]
- Evidence EV-103 (inference, supports): "The Section 14.2 example journals each balance (capture 10,000 = 9,720 + 280; settlement 9,810 + 190 = 10,000; payout 9,720 = 9,720)." [inference:EV-103] derived from EV-080, EV-082
- Why no change is needed: Atomic state, journal and outbox commits, database-enforced immutability and an enforced balance invariant directly satisfy P1, P5, P7 and FR-10. The remaining ledger gaps (refund and FX examples, state transitions) are covered in FND-007 and do not undermine this core.
- Decision AD-014 (24 Confirmed Decisions - Ledger): preserves. The review affirms the approved ledger and outbox decision.
- Decision AD-036 (P5): preserves. P5 append-only is enforced by revoked privileges.
- Decision AD-041 (P1): preserves. The payment record and the ledger stay consistent as the source of truth.

## Risks

### FND-001 Redis idempotency fast path is not scoped to merchant and skips the body-hash check

- **risk** · security privacy gap · severity **critical** · confidence 0.90 (high) · rank 1
- Disposition: **refinement now** (also: needs testing)

Section 9.2 keys the Redis fast path as idem:resp:{idempotency_key}, with no merchant_id, and returns the stored response on a hit before DynamoDB or any request-hash comparison runs. Section 9.1 accepts order and invoice numbers as keys. Two merchants that reuse the same order number within 24 hours will collide on one Redis key, so the second merchant receives the first merchant's payment object (card BIN and last 4, amounts, references) and its own payment is never created. A reused key with a different body also gets the cached response instead of HTTP 422. This breaks P3 and FR-5 and leaks cross-merchant data.

- Where: p.8 §9.2 (FR-5): "the final response is written to idem:resp:{idempotency_key} with a 24-hour TTL"
- Where: p.8 §9.2 (FR-5): "the Payments API checks this key first; on a hit, it returns the stored response immediately"
- Where: p.7 §9.1 (FR-4, FR-5): "frequently use their own order or invoice identifiers, which is accepted."
- Evidence EV-001 (doc, supports): "the final response is written to idem:resp:{idempotency_key} with a 24-hour TTL" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-002 (doc, supports): "the Payments API checks this key first; on a hit, it returns the stored response immediately" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-003 (doc, supports): "frequently use their own order or invoice identifiers, which is accepted." [doc:DOC-design_v1#p7/s9.1]
- Evidence EV-004 (doc, supports): "Idempotency is scoped to (merchant, key). Every mutating call is deduplicated on the pair of merchant identity and client-supplied" [doc:DOC-design_v1#p4/s3]
- Evidence EV-083 (inference, supports): "Two merchants that use the same order-number key within 24 hours share one Redis entry, so the second merchant gets the first merchant's stored payment object, and a changed body is answered from Redis without the 422 hash check." [inference:EV-083] derived from EV-001, EV-002, EV-003, EV-004
- Recommendation: In Section 9.2 and AD-006, change the Redis key to idem:resp:{merchant_id}:{idempotency_key}. Store request_hash with the cached response and compare it on every hit, returning 422 on a mismatch, so Redis applies the same rules as the DynamoDB path. Add a cross-merchant collision case and a different-body case to the FR-5 acceptance test in Section 26.1.
  - Issue: The fast-path key omits merchant identity and the request hash, contrary to P3 and FR-5.
  - Rationale: P3 is binding and wins over Section 9.2. Merchant-chosen keys make collisions across merchants likely.
  - Expected benefit: FR-5 and P3 hold on both tiers, and no merchant can read another merchant's payment object. (objectives: FR-5, P3, NFR-7)
  - Supporting evidence: EV-001, EV-002, EV-003, EV-004, EV-083
  - Verification: Test: merchant A and merchant B send the same key with different bodies within 24 hours. Each receives its own payment object, and A's reuse with a changed body returns 422 while the Redis entry is warm.
- Next step: Payments Core tech lead: Amend Section 9.2 and the AD-006 key format, and add collision tests to the FR-5 suite before Phase 3.
- Decision AD-006 (24 Confirmed Decisions - Idempotency store): refines. The two-tier Redis plus DynamoDB design stays; only the Redis key format and the hit check change.
- Decision AD-034 (P3): preserves. The change enforces P3's (merchant, key) scope on the fast path.
- Decision AD-052 (FR-5): preserves. The change restores the FR-5 identical-response and 422 behaviour.

### FND-002 Fraud Hook detokenises the PAN with the Card Adapter's role and sends it to FRV-1, contradicting P2 and the CDE scope

- **risk** · internal contradiction · severity **high** · confidence 0.90 (high) · rank 2
- Disposition: **refinement now** (also: governance decision)

Section 13.1 has the Fraud Hook detokenise the full card number using the Card Adapter's client library and service role, and send it to the third-party vendor FRV-1. This contradicts P2 (PAN leaves the Vault only over the Card Adapter's connection to an acquirer), Section 12.1 (only the Card Adapter's identity may detokenise) and Section 12.2, which scopes the Fraud Hook out of the CDE with 'Token, BIN, last 4 only'. Sharing the service role also breaks P9. The NFR-5 assessment against the Section 12.2 CDE boundary would not hold as written, and FRV-1 would receive cardholder data while its contract and DPA are still pending.

- Where: p.11 §13.1 (FR-9): "detokenise operation, using the Card Adapter client library and service role."
- Where: p.10 §12.1 (NFR-5): "Only the Card Adapter's service identity may call detokenise."
- Where: p.10 §12.2 (NFR-5): "Fraud Hook Out of scope Token, BIN, last 4 only"
- Evidence EV-005 (doc, supports): "detokenise operation, using the Card Adapter client library and service role." [doc:DOC-design_v1#p11/s13.1]
- Evidence EV-006 (doc, supports): "Only the Card Adapter's service identity may call detokenise." [doc:DOC-design_v1#p10/s12.1]
- Evidence EV-007 (doc, supports): "Fraud Hook Out of scope Token, BIN, last 4 only" [doc:DOC-design_v1#p10/s12.2]
- Evidence EV-008 (doc, supports): "except over the Card Adapter's connection to an acquirer. All other services handle tokens only." [doc:DOC-design_v1#p4/s3]
- Evidence EV-009 (doc, supports): "Card Adapter CDE Transmits PAN to acquirers" [doc:DOC-design_v1#p10/s12.2]
- Evidence EV-084 (inference, supports): "By the design's own scope basis, where transmitting PAN puts the Card Adapter in the CDE, a Fraud Hook that receives and transmits PAN to FRV-1 is a CDE component, so the Section 12.2 boundary that NFR-5 relies on is wrong." [inference:EV-084] derived from EV-005, EV-007, EV-009
- Recommendation: Remove card_number from the Section 13.1 payload and send the keyed PAN fingerprint (Section 12.1) or an FRV-1-specific keyed token instead. If FRV-1 cannot score without the PAN, an accountable owner must decide either to send it from a CDE-resident component under its own Vault identity, with FRV-1 added to the PCI service-provider inventory and Section 12.2, or to accept the lower scoring quality. Record the outcome in Section 12.2 and the PCI scoping memo.
  - Issue: The Fraud Hook payload includes card_number obtained with the Card Adapter's role, which breaches P2, P9 and the declared CDE.
  - Rationale: Section 3 says principles override later sections, so P2 wins over Section 13.1.
  - Expected benefit: The CDE stays confined to the Section 12.2 components (NFR-5), P2 and P9 hold, and FRV-1 does not become a cardholder-data recipient before a DPA exists. (objectives: P2, P9, NFR-5, FR-9)
  - Supporting evidence: EV-005, EV-006, EV-007, EV-008, EV-084
  - Verification: Run an IAM policy review showing that only the Card Adapter identity can call detokenise, and a segmentation test showing that the Fraud Hook cannot reach the detokenise endpoint. The QSA confirms the CDE inventory.
- Next step: Head of Security and PCI compliance lead with the Risk team: Confirm with FRV-1 whether a fingerprint or token key is enough. If not, decide on the CDE-resident option before Phase 8.
- Decision AD-033 (P2): preserves. The change restores P2 by keeping PAN inside the Vault boundary.
- Decision AD-028 (NFR-5): preserves. The change keeps the CDE limited to the components listed in Section 12.2.
- Decision AD-013 (24 Confirmed Decisions - Fraud): refines. FRV-1 remains the synchronous vendor; only the payload changes.
- Decision AD-040 (P9): preserves. The change removes the service role shared between the Fraud Hook and the Card Adapter.

### FND-003 Cascade after a timeout discards late approvals and has no reversal path, so customers can be authorised twice

- **risk** · scalability or failure mode · severity **high** · confidence 0.85 (high) · rank 3
- Disposition: **refinement now** (also: needs testing)

Section 11.1 treats 'no response within 2,500 ms' as retryable, and Section 11.2 discards responses that arrive after the timeout and then submits to the next acquirer. A late approval leaves a live authorization hold on the customer's card at the first acquirer while the second acquirer also approves. The design specifies no reversal message, no record of the orphaned authorization and no reconciliation of it. The claim that 'cascading cannot create a duplicate charge' therefore does not hold for timeouts, and discarding a provider response conflicts with P1 and P10.

- Where: p.9 §11.2 (FR-7): "arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded."
- Where: p.9 §11.2 (FR-7): "succeed, cascading cannot create a duplicate charge: the ledger records only the approved attempt."
- Where: p.9 §11.1 (FR-7): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms"
- Evidence EV-010 (doc, supports): "arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded." [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-011 (doc, supports): "succeed, cascading cannot create a duplicate charge: the ledger records only the approved attempt." [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-012 (doc, supports): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms" [doc:DOC-design_v1#p9/s11.1]
- Evidence EV-085 (inference, supports): "A timed-out attempt may have been approved by the issuer. Discarding the late approval and cascading leaves a live hold plus a second approval, with nothing sent to reverse the first and no memo or exception record of it." [inference:EV-085] derived from EV-010, EV-011, EV-012
- Recommendation: In Section 11.2, for an attempt that timed out or returned 5xx: (a) send an authorization reversal or void through the adapter's Connector interface before or in parallel with the next attempt; (b) record late responses on the attempt with outcome LATE_APPROVED and trigger automatic reversal, not discard; (c) extend the Section 20.3 sweeper and Section 16.2 matching to raise an exception for any approved attempt that is not the payment's winning attempt. Add a Connector 'reverse' operation to the FR-3 conformance suite.
  - Issue: There is no compensation for timed-out or late-approved attempts before or after a cascade.
  - Rationale: Timeouts and 5xx responses are explicitly retryable, so orphaned authorizations will occur at production volume.
  - Expected benefit: FR-7 cascades do not double-hold customer funds, P1 keeps provider responses as inputs to the payment record, and orphan holds are reconcilable under FR-11. (objectives: FR-7, FR-3, P1, P10, FR-11)
  - Supporting evidence: EV-010, EV-011, EV-012, EV-085
  - Verification: Cascade simulation in which the acquirer simulator approves after 2,600 ms. The test asserts that a reversal is sent and acknowledged, the attempt is recorded as late-approved, and only one authorization remains open.
- Next step: Payments Core tech lead: Specify the reversal flow and the late-response handling in Section 11.2, and extend the FR-7 test.
- Decision AD-011 (24 Confirmed Decisions - Cascade policy): refines. The cascade triggers and limits stay; a reversal step is added for timed-out attempts.
- Decision AD-041 (P1): preserves. Late responses update the payment record instead of being discarded.
- Decision AD-054 (FR-7): preserves. FR-7 cascading is kept and made safe.

### FND-005 RPO zero on regional loss (NFR-4) conflicts with asynchronous Aurora Global replication, and idempotency cannot be rebuilt

- **risk** · internal contradiction · severity **high** · confidence 0.85 (high) · rank 5
- Disposition: **governance decision** (also: refinement now, needs testing)

NFR-4 requires zero RPO for authorized payments and ledger postings on loss of an AWS region. Section 20.2 states that the only cross-region copy is asynchronous with 'typical lag under one second', so commits inside the lag window are lost on unplanned failover. Section 20.2 also says idempotency state is reconstructed from the payment table, but the Section 19 payment table has no idempotency_key, request hash or merchant_id column. Merchant retries after failover would therefore create new payments, which breaks FR-5. The design challenges AD-004 against NFR-4, and the NFR-4 game day cannot demonstrate zero loss for postings that had not yet replicated.

- Where: p.16 §20.2 (NFR-4): "Replication is storagelevel and asynchronous, with typical lag under one second."
- Where: p.3 §2.2 (NFR-4): "Recovery point objective for authorized payments and ledger postings shall be zero, including on loss of an entire AWS region."
- Where: p.17 §20.2 (FR-5, NFR-4): "empty in ap-southeast-3 from infrastructure-as-code, and in-flight idempotency state is reconstructed from the"
- Evidence EV-017 (doc, supports): "Replication is storagelevel and asynchronous, with typical lag under one second." [doc:DOC-design_v1#p16/s20.2]
- Evidence EV-018 (doc, supports): "Recovery point objective for authorized payments and ledger postings shall be zero, including on loss of an entire AWS region." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-019 (doc, supports): "empty in ap-southeast-3 from infrastructure-as-code, and in-flight idempotency state is reconstructed from the" [doc:DOC-design_v1#p17/s20.2]
- Evidence EV-020 (doc, supports): "Unplanned failover of the Aurora Global Database to ap-southeast-3" [doc:DOC-design_v1#p20/s26.2]
- Evidence EV-087 (inference, supports): "Asynchronous replication means commits inside the lag window before an unplanned regional loss are absent after failover, so RPO is greater than zero. The Section 19 payment table has no idempotency key or request hash column, so idempotency state cannot be reconstructed from it." [inference:EV-087] derived from EV-017, EV-018, EV-019
- Recommendation: Governance: either (a) restate NFR-4 as RPO of N seconds for unplanned regional loss (RPO zero within the region), backed by a provider-reconciliation recovery procedure that re-derives lost authorizations from acquirer reports, or (b) adopt a synchronous cross-region commit for payment and ledger writes and re-budget NFR-2. Refinement either way: add merchant_id, idempotency_key and request_hash columns (unique per merchant and key) to the payment table in Section 19, so that Section 20.2 reconstruction is possible.
  - Issue: NFR-4 as written cannot be met by the approved DR architecture (AD-004), and idempotency recovery has no data to work from.
  - Rationale: The document's own statements are mutually inconsistent. Either the requirement or the architecture must change, and that is an accountable trade-off between cost, latency and financial-data loss.
  - Expected benefit: NFR-4 becomes achievable or honestly restated, and FR-5 holds across a regional failover. (objectives: NFR-4, FR-5, P1)
  - Supporting evidence: EV-017, EV-018, EV-019, EV-087, EV-020
  - Verification: Run the NFR-4 game day under write load, measure postings missing after failover against the restated RPO, and replay idempotent retries after failover to confirm that no second payment is created.
- Next step: Head of Platform Engineering with the CFO delegate (financial-data risk owner): Choose option (a) or (b) and amend NFR-4, AD-004 and Sections 19 and 20.2 before Phase 1 completes.
- Decision AD-004 (24 Confirmed Decisions - Disaster recovery): challenges. This is an explicit challenge: by the document's own Section 20.2 text, asynchronous Aurora Global replication cannot deliver NFR-4's zero RPO on regional loss.
- Decision AD-068 (NFR-4): refines. NFR-4 may need restating to an achievable regional RPO.
- Decision AD-006 (24 Confirmed Decisions - Idempotency store): refines. Idempotency keys are persisted on the payment row to allow DR reconstruction.
- Decision AD-044 (19.1 Data placement): preserves. ap-southeast-3 remains DR-only.

### FND-006 Wait-for-all-files reconciliation cannot publish settlement reports by 08:00 SGT (NFR-8)

- **risk** · internal contradiction · severity **high** · confidence 0.85 (high) · rank 6
- Disposition: **governance decision** (also: needs prototyping)

Section 16.2 starts the matcher only after every file for day T has arrived. ACQ-TH1's file lands at 06:30 ICT, which is 07:30 SGT, and the matcher plus report generation take 60 minutes at 2025 volume, so the earliest publication is 08:30 SGT even at today's volume. 2027 daily attempts are about twice the 2025 level. No cut-off or partial-run path exists for a late or missing file, so one provider can block every merchant's report and the downstream payouts (FR-17). NFR-8 cannot be met under AD-016 as written.

- Where: p.13 §16.2 (FR-11, NFR-8): "matcher starts once all expected files for business day T have been received"
- Where: p.3 §2.2 (NFR-8): "At least 99.9% of settlement lines shall be auto-matched; merchant settlement reports for business day T shall be published by"
- Evidence EV-021 (doc, supports): "matcher starts once all expected files for business day T have been received" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-022 (doc, supports): "ACQ-TH1 CSV over SFTP Daily 06:30 ICT" [doc:DOC-design_v1#p12/s16.1]
- Evidence EV-023 (doc, supports): "the matcher's measured end-to-end run time is 45 minutes, and merchant settlement report generation takes a further" [doc:DOC-design_v1#p13/s3]
- Evidence EV-024 (doc, supports): "At least 99.9% of settlement lines shall be auto-matched; merchant settlement reports for business day T shall be published by" [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-025 (doc, supports): "Payment attempts per day (average) 5.1 M 10.5 M" [doc:DOC-design_v1#p2/s1]
- Evidence EV-088 (inference, supports): "06:30 ICT (UTC+7) is 07:30 SGT (UTC+8); adding 45 + 15 minutes gives 08:30 SGT at 2025 volume, 30 minutes past the deadline, and the roughly 2.06x volume growth to 2027 lengthens the run further." [inference:EV-088] derived from EV-021, EV-022, EV-023, EV-024, EV-025
- Recommendation: Change Section 16.2 to match each provider file incrementally on arrival, keeping a final complete-day step only for cross-provider netting and multi-provider payouts. Define a 07:45 SGT cut-off after which reports publish with late providers marked 'pending', with an escalation path for missing or malformed files. Alternatively, renegotiate the ACQ-TH1 delivery time or relax the NFR-8 deadline. Benchmark the matcher at 2027 volume.
  - Issue: The batch-start rule in AD-016 and the provider file times make NFR-8 arithmetically unattainable.
  - Rationale: The conflict follows from the document's own figures, and changing either the batch rule or the SLA is a business trade-off.
  - Expected benefit: NFR-8 report deadlines and FR-17 payout schedules are met, and a single late file no longer blocks all merchants. (objectives: NFR-8, FR-11, FR-17)
  - Supporting evidence: EV-021, EV-022, EV-023, EV-088, EV-025
  - Verification: NFR-8 replay at 2027 volume with the real file arrival schedule, plus one injected late file. Reports for the other providers publish by 08:00 SGT.
- Next step: Finance Operations lead with the Reconciliation tech lead: Decide between incremental matching with a cut-off and a revised SLA, and benchmark the matcher at 10.5 M attempts per day.
- Decision AD-016 (24 Confirmed Decisions - Reconciliation): challenges. This is an explicit challenge: the documented file times and run times show that 'daily batch after all files received' cannot meet NFR-8.
- Decision AD-069 (NFR-8): preserves. The change aims to make NFR-8 achievable.
- Decision AD-064 (FR-17): preserves. Payout schedules no longer depend on the slowest file.
- Decision AD-027 (27 Implementation Readiness - Reconciliation): preserves. The parser sample-file dependency is unchanged.

### FND-008 Single CloudHSM in one AZ is a single point of failure for all card acceptance, and the scale-out trigger never fires

- **risk** · scalability or failure mode · severity **high** · confidence 0.70 (medium) · rank 8
- Disposition: **governance decision** (also: needs prototyping)

Section 12.3 puts every KEK in one HSM in ap-southeast-1a. DEKs are not cached, so every tokenise and detokenise call needs the HSM, while Section 20.1 says every service runs across three AZs. The trigger for a second HSM (sustained card volume above 1,500 TPS) is never reached under the design target, because 55% card share of 2,000 TPS is 1,100 TPS. Mapping a Vault 503 to a retryable outcome makes every cascade candidate fail the same way while still consuming per-card reattempt counters. Losing the HSM or its AZ stops card acceptance until an HSM is restored from backup, which threatens NFR-3. AWS availability guidance and restore times are unverified in the register.

- Where: p.10 §12.3 (NFR-3): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a."
- Where: p.10 §12.3 (NFR-3, FR-7): "cluster when sustained card volume exceeds 1,500 TPS. If the HSM is unreachable, the Vault returns HTTP 503 and"
- Where: p.16 §20.1 (NFR-3): "Every service runs at least three replicas spread across three AZs."
- Evidence EV-032 (doc, supports): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a." [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-033 (doc, supports): "cluster when sustained card volume exceeds 1,500 TPS. If the HSM is unreachable, the Vault returns HTTP 503 and" [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-034 (doc, supports): "Card share of attempts (e-wallet ~30%, bank transfer ~15%) 54% 55%" [doc:DOC-design_v1#p2/s1]
- Evidence EV-035 (doc, supports): "Every service runs at least three replicas spread across three AZs." [doc:DOC-design_v1#p16/s20.1]
- Evidence EV-036 (doc, supports): "inside the HSM; DEKs are not cached, so plaintext key material never persists in application memory." [doc:DOC-design_v1#p10/s12.1]
- Evidence EV-090 (inference, supports): "55% of 2,000 TPS is 1,100 card TPS at peak, below the 1,500 TPS trigger, so the design runs on one single-AZ HSM throughout; with no DEK caching, every card payment depends on it, and a 503 classed as retryable fails every cascade candidate too." [inference:EV-090] derived from EV-032, EV-033, EV-034, EV-035, EV-036
- Recommendation: Amend Section 12.3 and AD-008 to launch with at least two HSMs in different AZs, and replace the TPS trigger with a measured-utilisation trigger (for example, sustained HSM operations above 60% of benchmarked capacity). In Section 11.1, classify a Vault or HSM 503 as a non-cascading system failure that does not increment scheme reattempt counters. Benchmark HSM unwrap throughput and latency at peak (card authorizations plus cascades plus tokenisation) and measure restore-from-backup time.
  - Issue: The approved one-HSM launch posture is inconsistent with the three-AZ resilience stance and NFR-3, and its scale trigger is unreachable.
  - Rationale: Every card payment needs an HSM operation, so HSM availability bounds card availability.
  - Expected benefit: Card acceptance survives the loss of an HSM or an AZ (NFR-3), and the cascade budget is not wasted on Vault outages. (objectives: NFR-3, NFR-2, FR-7)
  - Supporting evidence: EV-032, EV-033, EV-034, EV-035, EV-036, EV-090
  - Verification: Chaos test: kill one HSM during the NFR-1 load test. Card authorizations continue within NFR-2, and no cascades are triggered by Vault errors.
- Next step: Head of Platform Engineering (AD-008 owner) with the Vault tech lead: Decide on the HSM count at launch and run an HSM throughput and restore benchmark in Phase 2.
- Decision AD-008 (24 Confirmed Decisions - Vault): challenges. This is an explicit challenge to 'one HSM at launch': the document's own resilience stance, availability target and unreachable trigger show it cannot meet NFR-3. External AWS guidance is unverified.
- Decision AD-067 (NFR-3): preserves. The change protects NFR-3 availability.
- Decision AD-043 (5 Target Architecture - CDE isolation): preserves. The HSMs stay in the dedicated CDE account.

### FND-009 Payout bank account change lacks step-up MFA, a second approver and owner notification

- **risk** · security privacy gap · severity **high** · confidence 0.80 (high) · rank 9
- Disposition: **refinement now**

Section 18.4 lets a Finance or Owner user change the payout account in the portal, with a confirmation email sent only to the person who made the change. MFA is optional for Finance (Section 18.3), and Finance also holds refund rights (Section 18.2). A phished Finance password alone can redirect all of a merchant's payouts, and the only alert goes to the attacker. This conflicts with P9's separation of money-moving and configuration permissions, and exposes Serindit Pay and its merchants to direct financial loss.

- Where: p.14 §18.4 (FR-13, FR-17): "A confirmation email is sent to the user who made the change, and the change is written to the audit log."
- Where: p.14 §18.3 (FR-13): "TOTP multi-factor authentication is available to every user and is enforced for the Owner role at first login."
- Where: p.14 §18.2 (FR-13): "Finance Issue refunds; view and export reports; edit payout bank account"
- Evidence EV-037 (doc, supports): "A Finance or Owner user can change the payout bank account in the portal." [doc:DOC-design_v1#p14/s18.4]
- Evidence EV-038 (doc, supports): "A confirmation email is sent to the user who made the change, and the change is written to the audit log." [doc:DOC-design_v1#p14/s18.4]
- Evidence EV-039 (doc, supports): "TOTP multi-factor authentication is available to every user and is enforced for the Owner role at first login." [doc:DOC-design_v1#p14/s18.3]
- Evidence EV-040 (doc, supports): "Finance Issue refunds; view and export reports; edit payout bank account" [doc:DOC-design_v1#p14/s18.2]
- Evidence EV-041 (doc, supports): "Least privilege and separation of duties. Every human and service identity has only the permissions its role requires; money-moving" [doc:DOC-design_v1#p4/s3]
- Evidence EV-091 (inference, supports): "A compromised password-only Finance account can redirect every payout from the next cycle, and the only notification goes to the compromised account." [inference:EV-091] derived from EV-037, EV-038, EV-039, EV-040
- Recommendation: In Section 18.4: require step-up TOTP at the moment of the change, for every role (login-time policy under AD-018 is unchanged); require approval by a second user (an Owner if Finance initiated the change); notify all Owners and the previous account's registered contact; apply a cooling-off period (for example, the first payout to a new account is held 48 hours); and keep the verified_at account verification as a precondition. Remove 'edit payout bank account' from Finance in Section 18.2, or make it request-only.
  - Issue: Payout destination changes are a money-moving configuration action with single-factor, single-person control.
  - Rationale: P9 requires money-moving permissions to be separated from configuration, and payout redirection is a high-value fraud target.
  - Expected benefit: P9 holds, and payout funds under FR-17 are protected from account takeover. (objectives: P9, FR-13, FR-17)
  - Supporting evidence: EV-037, EV-038, EV-039, EV-040, EV-041, EV-091
  - Verification: Extend the FR-13 role-matrix test: a Finance user without TOTP cannot complete a change, a change without a second approval does not take effect, and all Owners receive the notification.
- Next step: Merchant Admin Plane product owner with Security: Update Sections 18.2 and 18.4 before Phase 7.
- Decision AD-018 (24 Confirmed Decisions - Merchant user MFA): refines. TOTP stays the factor and login enforcement is unchanged; step-up is added only for payout account changes.
- Decision AD-040 (P9): preserves. The change enforces P9 separation of duties.
- Decision AD-060 (FR-13): preserves. FR-13 payout management stays available with stronger control.

### FND-010 First card cohort goes live before the Fraud Hook, PCI DSS assessment, load test and DR game day

- **risk** · internal contradiction · severity **high** · confidence 0.80 (high) · rank 10
- Disposition: **governance decision**

Section 28 launches Singapore cards after Phase 7. The Fraud Hook is Phase 8, still blocked on the FRV-1 contract, and the PCI DSS assessment, load test and DR game days are Phase 9. Live card traffic would therefore run without the fraud scoring FR-9 requires for every card payment, before NFR-5 is assessed and before NFR-1, NFR-2 and NFR-4 are demonstrated. Section 27 also says neither open gap blocks the first cohort, but it does not consider these. The document names no owner for accepting that risk.

- Where: p.3 §2.1 (FR-9): "Every card payment and every e-wallet payment above the merchant's configured threshold shall be scored by the fraud-scoring hook"
- Evidence EV-042 (doc, supports): "The first merchant cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week" [doc:DOC-design_v1#p21/s9]
- Evidence EV-043 (doc, supports): "Fraud Hook (FRV-1) Yes - vendor contract (Backlog item 4)" [doc:DOC-design_v1#p21/s8]
- Evidence EV-044 (doc, supports): "Hardening - load, chaos and DR game days; PCI DSS assessment; Section 26 test plan" [doc:DOC-design_v1#p21/s9]
- Evidence EV-045 (doc, supports): "Every card payment and every e-wallet payment above the merchant's configured threshold shall be scored by the fraud-scoring hook" [doc:DOC-design_v1#p3/s2.1]
- Evidence EV-092 (inference, supports): "Because Phases 8 and 9 follow the go-live gate after Phase 7, the first cohort processes live cards without FR-9 scoring and before the NFR-5 assessment and the NFR-1/2/4 validation." [inference:EV-092] derived from EV-042, EV-043, EV-044, EV-045
- Recommendation: In Section 28, move the go-live gate for card traffic after Phase 8 and after the PCI DSS assessment, load test and DR game-day portions of Phase 9, or allow PayNow-only go-live after Phase 7. If cards must launch earlier, record a time-boxed risk acceptance signed by a named executive, with compensating controls (merchant velocity limits and low per-transaction caps).
  - Issue: The go-live gate precedes the phases that deliver mandatory card controls.
  - Rationale: FR-9 and NFR-5 are stated without exception, and operating outside them needs explicit accountable acceptance.
  - Expected benefit: FR-9 and NFR-5 are met, or deviations are knowingly accepted, before money is at risk. (objectives: FR-9, NFR-5, NFR-1, NFR-4)
  - Supporting evidence: EV-042, EV-043, EV-044, EV-045, EV-092
  - Verification: A go-live checklist requires the FR-9, NFR-5, NFR-1 and NFR-4 acceptance results, or a signed risk acceptance, before card traffic is enabled.
- Next step: Chief Risk Officer with the Head of Payments: Decide the go-live gate and record any risk acceptance in Section 28.
- Decision AD-056 (FR-9): preserves. FR-9 coverage is enforced at go-live.
- Decision AD-028 (NFR-5): preserves. The PCI assessment precedes card processing.
- Decision AD-013 (24 Confirmed Decisions - Fraud): preserves. FRV-1 integration stays as decided; only sequencing changes.

### FND-011 Latency budget excludes cascades on a '<1%' premise that contradicts the 3.8% retryable baseline and the 2,500 ms timeout

- **risk** · internal contradiction · severity **medium** · confidence 0.80 (high) · rank 11
- Disposition: **refinement now** (also: needs testing)

Section 21.1 leaves cascades out of the p99 budget because 'fewer than 1% of card payments cascade', yet Section 10.5 gives 3.8% retryable outcomes and the NFR-2 test injects 3.8%. Any attempt that hits the 2,500 ms timeout already exceeds NFR-2's 1,500 ms on its own, and NFR-2 explicitly includes any cascade. The 3DS step is absent from the budget and from NFR-2's wording. As written, NFR-2 is likely to fail its own acceptance test, or it is ambiguous about what it measures.

- Where: p.17 §21.1 (NFR-2): "move the p99 because fewer than 1% of card payments cascade; the cascade path therefore sits above the 99th"
- Where: p.9 §10.5 (FR-7): "retryable outcomes - soft declines eligible for reattempt plus acquirer-side errors and timeouts - 3.8%."
- Where: p.20 §26.2 (NFR-2): "Under the NFR-1 load with 3.8% retryable-outcome injection, p99 end-to-end card authorization ≤ 1,500"
- Evidence EV-046 (doc, supports): "move the p99 because fewer than 1% of card payments cascade; the cascade path therefore sits above the 99th" [doc:DOC-design_v1#p17/s21.1]
- Evidence EV-047 (doc, supports): "retryable outcomes - soft declines eligible for reattempt plus acquirer-side errors and timeouts - 3.8%." [doc:DOC-design_v1#p9/s10.5]
- Evidence EV-048 (doc, supports): "End-to-end p99 latency for a card authorization, measured at the API edge and including any cascade, shall not exceed 1,500 ms." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-049 (doc, supports): "Under the NFR-1 load with 3.8% retryable-outcome injection, p99 end-to-end card authorization ≤ 1,500" [doc:DOC-design_v1#p20/s26.2]
- Evidence EV-012 (doc, supports): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms" [doc:DOC-design_v1#p9/s11.1]
- Evidence EV-093 (inference, supports): "At 3.8% retryable, cascaded payments fall inside the slowest 1%, so they set the p99 rather than sitting above it; any payment whose first attempt times out spends at least 2,500 ms, so NFR-2 fails if timeouts exceed roughly 1% of card payments." [inference:EV-093] derived from EV-046, EV-047, EV-048, EV-049, EV-012
- Recommendation: In Section 21.1, budget the cascade path explicitly, using the split between timeout and soft-decline retryables from 2025 data. Either cut the per-attempt timeout to fit within the 1,500 ms end-to-end budget (with a global payment deadline that stops cascading when the remaining budget is too small), or restate NFR-2 so it excludes 3DS customer time and defines whether p99 is measured over all card payments. State that 3DS challenge time is excluded.
  - Issue: The budget premise conflicts with the baseline and the test, and the per-attempt timeout is inconsistent with the end-to-end target.
  - Rationale: NFR-2 includes cascades, and its acceptance test uses the 3.8% figure.
  - Expected benefit: NFR-2 becomes achievable and testable. (objectives: NFR-2, FR-7)
  - Supporting evidence: EV-046, EV-047, EV-048, EV-049, EV-012, EV-093
  - Verification: NFR-2 benchmark with the retryable mix split by type (timeouts versus soft declines) at production rates, reporting p99 including cascades.
- Next step: Payments Core tech lead: Extract the 2025 split of retryable outcomes by type and re-budget Section 21.1.
- Decision AD-066 (NFR-2): preserves. The change makes NFR-2 meetable and measurable.
- Decision AD-011 (24 Confirmed Decisions - Cascade policy): refines. The 2,500 ms trigger may be shortened or bounded by an overall payment deadline.

## Gaps

### FND-007 State machine blocks settlement of refunded payments and multiple partial captures, and the memo-ledger wording conflicts

- **gap** · missing or unverifiable requirement · severity **high** · confidence 0.80 (high) · rank 7
- Disposition: **refinement now**

Section 7.2 allows no transition from PARTIALLY_REFUNDED or REFUNDED to SETTLED, yet Section 16.2 moves every matched payment to SETTLED. A payment refunded before its settlement line arrives therefore cannot be settled without breaching FR-2 and will fall into exceptions, which counts against the NFR-8 99.9% auto-match target. There is no CAPTURED to CAPTURED transition, so FR-1's partial capture supports only one capture, and release of the uncaptured remainder is unspecified. Section 8 records the authorization as a 'ledger journal', while Section 14.3 puts holds in a separate memo ledger, and no refund or FX journal examples are given for FR-10.

- Where: p.2 §2.1 (FR-2): "Every payment shall be in exactly one state of the state machine in Section 7 at any time; only the transitions listed there shall be"
- Where: p.2 §2.1 (FR-1): "The platform shall expose one versioned merchant API supporting create payment, authorize, capture (full and partial), void, refund"
- Evidence EV-026 (doc, supports): "CAPTURED -> SETTLED | PARTIALLY_REFUNDED | REFUNDED" [doc:DOC-design_v1#p6/s7.2]
- Evidence EV-027 (doc, supports): "PARTIALLY_REFUNDED -> REFUNDED" [doc:DOC-design_v1#p6/s7.2]
- Evidence EV-028 (doc, supports): "Matched payments transition to SETTLED and a settlement journal is posted." [doc:DOC-design_v1#p13/s3]
- Evidence EV-029 (doc, supports): "The platform shall expose one versioned merchant API supporting create payment, authorize, capture (full and partial), void, refund" [doc:DOC-design_v1#p2/s2.1]
- Evidence EV-030 (doc, supports): "Orchestrator -> AUTHORISED or FAILED; ledger journal (authorization memo); outbox event" [doc:DOC-design_v1#p7/s9]
- Evidence EV-031 (doc, supports): "Authorization holds are recorded as memo entries in a separate memo ledger, not in the financial ledger," [doc:DOC-design_v1#p12/s14.3]
- Evidence EV-089 (inference, supports): "A payment refunded before its settlement line arrives is in PARTIALLY_REFUNDED or REFUNDED, from which SETTLED is not permitted, so matching must either violate FR-2 or raise an exception; and no CAPTURED to CAPTURED transition exists for a second partial capture." [inference:EV-089] derived from EV-026, EV-027, EV-028, EV-029
- Recommendation: In Section 7, track settlement status and refund status as separate attributes (or add PARTIALLY_REFUNDED/REFUNDED to SETTLED transitions). Add CAPTURED to CAPTURED for additional partial captures up to amount_minor, plus an explicit 'final capture' flag that releases the remainder. Correct Section 8 step 10 to 'memo-ledger entry'. Add refund, partial-capture and FX journal examples to Section 14.2.
  - Issue: A single state field conflates capture, refund and settlement progress, so common lifecycles have no legal path.
  - Rationale: Refunds before settlement and split shipments are routine for marketplace merchants, and FR-2 forbids unlisted transitions.
  - Expected benefit: FR-1, FR-2 and FR-10 cover real lifecycles, and NFR-8 auto-match is not eroded by refunded payments. (objectives: FR-1, FR-2, FR-10, NFR-8)
  - Supporting evidence: EV-026, EV-027, EV-028, EV-029, EV-030, EV-031, EV-089
  - Verification: Extend the FR-2 property test with sequences of refund-then-settle and capture-capture-settle events, and add the new journal examples to the FR-10 invariant test.
- Next step: Payments Core tech lead: Revise Sections 7.1, 7.2, 8 and 14.2 before Phase 3.
- Decision AD-049 (FR-2): preserves. The state machine is completed so that FR-2 can hold.
- Decision AD-048 (FR-1): preserves. Partial captures become fully supported.
- Decision AD-057 (FR-10): preserves. Missing journal types are specified.

### FND-013 Idempotency failure paths are unspecified: orphan IN_PROGRESS locks, DynamoDB outage, and order-ID keys reused after 24 hours

- **gap** · scalability or failure mode · severity **medium** · confidence 0.75 (medium) · rank 13
- Disposition: **refinement now** (also: needs testing)

Section 9.2 relies on the stuck-payment sweeper to clear IN_PROGRESS locks, but Section 20.3 scans only payments in AUTHORISING. A pod that crashes after the conditional put but before the payment exists, or while the payment is in CREATED (fraud or 3DS stage), leaves a key that returns 409 for up to 24 hours. Section 20.4 covers a Redis outage but not DynamoDB unavailability or throttling, so it is undefined whether the API fails open (risking duplicates) or fails closed. Because order IDs are accepted as keys, a merchant retry after the 24-hour expiry creates a second charge, a residual FR-5 risk the document does not discuss.

- Where: p.8 §9.2 (FR-5): "A lock left IN_PROGRESS by a crashed API pod is recovered by the Orchestrator's stuck-payment sweeper (Section"
- Where: p.17 §20.3 (FR-5): "Every 60 seconds, the Orchestrator's sweeper finds payments in AUTHORISING for more than 30 seconds, queries the"
- Where: p.7 §9.1 (FR-5): "Records are retained for 24 hours from first use. A request after expiry is treated as new."
- Evidence EV-054 (doc, supports): "A lock left IN_PROGRESS by a crashed API pod is recovered by the Orchestrator's stuck-payment sweeper (Section" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-055 (doc, supports): "Every 60 seconds, the Orchestrator's sweeper finds payments in AUTHORISING for more than 30 seconds, queries the" [doc:DOC-design_v1#p17/s20.3]
- Evidence EV-056 (doc, supports): "Records are retained for 24 hours from first use. A request after expiry is treated as new." [doc:DOC-design_v1#p7/s9.1]
- Evidence EV-057 (doc, supports): "Redis down Fast path skipped; DynamoDB path serves all idempotency checks" [doc:DOC-design_v1#p17/s20.4]
- Evidence EV-095 (inference, supports): "A sweeper that scans only AUTHORISING payments cannot resolve locks taken before a payment exists or while it is in CREATED or REQUIRES_ACTION, and no DynamoDB failure behaviour is defined." [inference:EV-095] derived from EV-054, EV-055, EV-057
- Recommendation: In Section 9.2, add a lease timestamp to IN_PROGRESS records; a sweeper scanning the idempotency table resolves expired leases (no payment found: delete the record so the client retry proceeds; payment found: resolve it by state). Extend the Section 20.3 sweeper to CREATED payments older than the fraud and 3DS budget. Add a 'DynamoDB unavailable or throttled' row to Section 20.4 that fails closed with 503 and Retry-After. Document the 24-hour key semantics and offer optional merchant_reference uniqueness per merchant account as protection against reuse after expiry.
  - Issue: Recovery of the idempotency lock covers only one crash point, and there is no defined behaviour when DynamoDB fails.
  - Rationale: FR-5 must hold under partial failure, not only on the happy path.
  - Expected benefit: FR-5 holds through crashes and dependency failures, with no 24-hour lockouts. (objectives: FR-5, NFR-3)
  - Supporting evidence: EV-054, EV-055, EV-056, EV-057, EV-095
  - Verification: Fault-injection tests: kill the pod after the conditional put, and throttle DynamoDB. Retries complete within the lease and no duplicate authorization occurs.
- Next step: Payments Core tech lead: Add lease-based lock recovery and the DynamoDB failure row to Sections 9.2 and 20.4.
- Decision AD-006 (24 Confirmed Decisions - Idempotency store): refines. A lease attribute is added to the existing table.
- Decision AD-007 (24 Confirmed Decisions - Idempotency retention): preserves. The 24-hour retention is unchanged and its semantics are documented.
- Decision AD-052 (FR-5): preserves. FR-5 is strengthened under failure.

### FND-016 No personal-data inventory, purpose and retention mapping, or cross-border position for NFR-7

- **gap** · security privacy gap · severity **medium** · confidence 0.60 (medium) · rank 16
- Disposition: **needs investigation** (also: refinement now)

NFR-7 requires purpose limitation, retention limits and access logging across five privacy laws. The design sends device fingerprint, IP address, hashed email and phone, and addresses to FRV-1 (whose DPA is pending), stores customer bank accounts for payout refunds, and processes all markets' data in Singapore with DR in Jakarta. The only retention rules cover payment, idempotency, webhook and settlement records. No field-level purpose and retention map, data-subject request process or transfer basis is given, and whether Indonesian or other rules require local processing is unverified in the register.

- Where: p.3 §2.2 (NFR-7): "Personal data shall be processed in accordance with the personal data protection laws of each market of operation (Singapore"
- Where: p.16 §19.1 (NFR-7): "Retention: payment and attempt records 7 years (financial records); idempotency records 24 hours; webhook events 30"
- Evidence EV-064 (doc, supports): "device fingerprint, IP address, user agent Merchant SDK Device signals" [doc:DOC-design_v1#p11/s13.1]
- Evidence EV-065 (doc, supports): "Personal data shall be processed in accordance with the personal data protection laws of each market of operation (Singapore" [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-066 (doc, supports): "Retention: payment and attempt records 7 years (financial records); idempotency records 24 hours; webhook events 30" [doc:DOC-design_v1#p16/s19.1]
- Evidence EV-067 (doc, supports): "FRV-1 contract - data processing agreement and SLA finalisation." [doc:DOC-design_v1#p19/s3]
- Evidence EV-098 (inference, supports): "Personal data fields sent to FRV-1 and held for refunds have no stated purpose, retention or transfer basis, so the NFR-7 DPO sign-off has nothing to review against." [inference:EV-098] derived from EV-064, EV-065, EV-066, EV-067
- Recommendation: Add a personal-data inventory section listing each field (device, IP, hashed contacts, addresses, customer refund bank account, merchant-user identities), its purpose, retention, access logging and recipients, including FRV-1. Define data-subject request handling. Obtain legal opinions on whether the five markets' laws and payment-system rules allow processing in ap-southeast-1, DR in ap-southeast-3 and sharing with FRV-1.
  - Issue: The NFR-7 obligations are stated but not designed.
  - Rationale: The NFR-7 acceptance test requires every field to be mapped, and cross-border rules may constrain the single-region decision.
  - Expected benefit: NFR-7 compliance per market, and early detection of any localisation constraint. (objectives: NFR-7)
  - Supporting evidence: EV-064, EV-065, EV-066, EV-067, EV-098
  - Verification: Per-market DPO sign-off (NFR-7 test) against the inventory, with legal opinions attached.
- Next step: Data Protection Officer with regional legal counsel: Commission data-localisation opinions (Indonesia first) and draft the field inventory before the Phase 1 data-store build-out.
- Decision AD-030 (NFR-7): preserves. The change operationalises NFR-7.
- Decision AD-044 (19.1 Data placement): preserves. The single-region placement is kept unless legal review finds a localisation rule.
- Decision AD-013 (24 Confirmed Decisions - Fraud): refines. FRV-1 data sharing is made subject to a DPA and the inventory.

### FND-019 Payout-based refunds, negative balances, reserves and dispute holds are unspecified, yet Payouts is rated 'Ready'

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.65 (medium) · rank 19
- Disposition: **refinement now**

FR-15 falls back to a bank payout to the customer's nominated account, but no section defines how that account is collected, verified or protected, or how the payout is journaled. Section 16.3 subtracts 'reserves and pending dispute holds' without saying how they are set, and there is no rule for a merchant_payable that goes negative when refunds or dispute debits exceed the balance. Section 27 nonetheless rates Payouts 'Ready'. Disputes themselves are an acknowledged backlog item (AD-020), but the dispute-debit and hold rules matter for v1 payouts.

- Where: p.3 §2.1 (FR-15): "Refunds shall be supported for every payment method; where a method has no refund API, the refund shall be executed as a bank"
- Where: p.13 §16.3 (FR-17): "The Payout Service computes each merchant account's payable balance after settlement, subtracts reserves and"
- Evidence EV-075 (doc, supports): "Refunds shall be supported for every payment method; where a method has no refund API, the refund shall be executed as a bank" [doc:DOC-design_v1#p3/s2.1]
- Evidence EV-076 (doc, supports): "The Payout Service computes each merchant account's payable balance after settlement, subtracts reserves and" [doc:DOC-design_v1#p13/s16.3]
- Evidence EV-077 (doc, supports): "Payouts Ready Section 16.3." [doc:DOC-design_v1#p21/s27]
- Evidence EV-101 (inference, supports): "The Payout Service cannot be built to a definite rule set without definitions for reserve and hold amounts, negative-balance handling and customer refund-account capture." [inference:EV-101] derived from EV-075, EV-076, EV-077
- Recommendation: Add to Section 16.3: the reserve and dispute-hold calculation and who configures it (the risk team, per merchant risk tier); negative-balance handling (carry-forward and netting against the next settlement, plus a direct-debit or invoice fallback); and the refund-to-bank flow (account capture through a hosted form, name-check verification, a payout journal using refund_clearing). Re-rate Payouts as 'Mostly ready' until these are added.
  - Issue: The money-movement edge paths for FR-15 and FR-17 are undefined.
  - Rationale: These paths move real funds, and the ledger invariant does not tell an engineer what to build.
  - Expected benefit: FR-15 and FR-17 can be implemented without improvised policy. (objectives: FR-15, FR-17, FR-10)
  - Supporting evidence: EV-075, EV-076, EV-077, EV-101
  - Verification: Extend the FR-15 and FR-17 tests with negative-balance and payout-refund scenarios, and confirm that the FR-10 invariant holds.
- Next step: Finance Operations lead with the Payouts tech lead: Specify the reserve, hold and negative-balance policy in Section 16.3.
- Decision AD-062 (FR-15): preserves. FR-15 fallback refunds are specified.
- Decision AD-064 (FR-17): preserves. FR-17 payouts are completed.
- Decision AD-020 (25 Pending Backlog item 1): preserves. The dispute module stays in the backlog; only the v1 hold rules are needed.
- Decision AD-045 (1 Out of scope): preserves. Dispute case management stays out of scope.

### FND-020 Operational owners and document change control are not named

- **gap** · missing or unverifiable requirement · severity **low** · confidence 0.60 (medium) · rank 20
- Disposition: **governance decision**

The design relies on recurring human processes with no named owner or SLA: the weekly Routing Review that adjusts cost and approval weights, the Finance Operations exception queue, paging and payout freezes on ledger discrepancies, the DR rehearsals and the HSM capacity trigger. The title page records a 2026-09-21 consolidation without a change log and cites a draft PCI DSS Scoping Memo on which Section 12.2 depends. None of this causes failure by itself, but it weakens the P10 auditability of decisions and the closure of the open items above.

- Where: p.1 §Title page: "Companion documents MPOP Conceptual Design v1.2; PCI DSS Scoping Memo (draft); Acquirer Connectivity Matrix"
- Where: p.9 §10.3 (FR-8): "authorization rate under cost-preferred routing against a control slice (5% of traffic routed approval-first) and adjusts"
- Evidence EV-016 (doc, supports): "Companion documents MPOP Conceptual Design v1.2; PCI DSS Scoping Memo (draft); Acquirer Connectivity Matrix" [doc:DOC-design_v1#p1/s12.4]
- Evidence EV-078 (doc, supports): "authorization rate under cost-preferred routing against a control slice (5% of traffic routed approval-first) and adjusts" [doc:DOC-design_v1#p9/s10.3]
- Evidence EV-079 (doc, supports): "become reconciliation exceptions with a reason code and are routed to the Finance Operations queue." [doc:DOC-design_v1#p13/s3]
- Evidence EV-102 (inference, supports): "Processes that change routing weights or clear financial exceptions have no accountable role or turnaround target, and design changes since 2026-09-14 are not traceable." [inference:EV-102] derived from EV-016, EV-078, EV-079
- Recommendation: Add an operational ownership table (process, owner role, cadence or SLA, approval needed) covering the Routing Review, the exception queue, discrepancy freezes, DR rehearsals and HSM capacity. Add a change log to the title page, and make finalisation of the PCI memo a Phase 2 entry criterion.
  - Issue: Owners, SLAs and document change control are missing.
  - Rationale: P9 and P10 require accountable, reconstructable changes to routing weights and to financial exceptions.
  - Expected benefit: Changes to routing and financial operations stay auditable (P10), and open items close on time. (objectives: P10, P9, NFR-5)
  - Supporting evidence: EV-016, EV-078, EV-079, EV-102
  - Verification: Design review sign-off confirms that each process has an owner role, and the change log is present in v1.1.
- Next step: Payments Core engineering manager: Publish the ownership table and the change log in the next revision.
- Decision AD-042 (P10): preserves. The change supports P10 auditability of operational changes.
- Decision AD-028 (NFR-5): preserves. Finalising the PCI memo supports the NFR-5 scoping.

## Ambiguities

### FND-017 FR-8's '2%' and the routing 'tolerance (default 2)' are undefined units, and the FR-8 test never exercises the bound

- **ambiguity** · ambiguous requirement · severity **medium** · confidence 0.70 (medium) · rank 17
- Disposition: **refinement now**

FR-8 allows cost preference unless the expected authorization rate drops by more than 2%, and Section 10.3 and AD-012 use a unitless 'tolerance (default 2)'. Percentage points and a relative 2% differ materially (on an 88% baseline, 2 points is about 2.3% relative). Section 10.3 compares the lowest-cost acquirer with the highest-approval one, while Section 10.2 ranks by a weighted score whose default emphasises cost, so the two mechanisms can disagree. The FR-8 test checks only expected choices and does not probe the bound.

- Where: p.2 §2.1 (FR-8): "For each transaction, the Routing Engine shall prefer the lowest-cost eligible acquirer unless doing so reduces the expected"
- Where: p.9 §10.3 (FR-8): "configured tolerance (default 2). Separately, the weekly Routing Review compares each merchant's realised"
- Where: p.19 §26.1 (FR-8): "For a set of synthetic transactions with configured costs and approval priors, the selected acquirer matches the"
- Evidence EV-068 (doc, supports): "For each transaction, the Routing Engine shall prefer the lowest-cost eligible acquirer unless doing so reduces the expected" [doc:DOC-design_v1#p2/s2.1]
- Evidence EV-069 (doc, supports): "configured tolerance (default 2). Separately, the weekly Routing Review compares each merchant's realised" [doc:DOC-design_v1#p9/s10.3]
- Evidence EV-070 (doc, supports): "For a set of synthetic transactions with configured costs and approval priors, the selected acquirer matches the" [doc:DOC-design_v1#p19/s26.1]
- Evidence EV-099 (inference, supports): "A unitless tolerance of 2 against an 88% approval baseline can mean either 2 percentage points or about 1.8 points relative, and a weighted score can select a cheaper acquirer beyond either bound unless the bound is applied as a hard constraint." [inference:EV-099] derived from EV-068, EV-069, EV-070
- Recommendation: Define the FR-8 and Section 10.3 tolerance as percentage points of the approval prior. State that the Section 10.2 score selects only among acquirers whose approval prior is within tolerance of the best. Add FR-8 boundary cases (1.9 and 2.1 points) to the Section 26.1 test.
  - Issue: The FR-8 bound has two readings and is not wired as a hard constraint on the weighted score.
  - Rationale: The routing trade-off directly affects merchant approval rates and revenue.
  - Expected benefit: FR-8 is unambiguous and verifiable. (objectives: FR-8)
  - Supporting evidence: EV-068, EV-069, EV-070, EV-099
  - Verification: Routing decision test with boundary cases at the tolerance.
- Next step: Routing product owner: Fix the unit and the constraint semantics in FR-8, Section 10.3 and AD-012.
- Decision AD-012 (24 Confirmed Decisions - Routing): refines. The '2' tolerance gets a unit and hard-constraint semantics.
- Decision AD-055 (FR-8): refines. FR-8's 2% is clarified as percentage points.

## Unresolved assumptions

### FND-004 Keeping the CVC until settlement rests on an unverified reading of PCI DSS v4.0 3.2.1 and 3.3.2

- **unresolved assumption** · unsupported or incorrect claim · severity **high** · confidence 0.60 (medium) · rank 4
- Disposition: **needs investigation** (also: governance decision)

Sections 12.4 and NFR-6 keep the encrypted CVC until settlement or for up to 72 hours. The stated uses include incremental authorizations (tips, hotel extensions), which happen after the initial authorization has completed, and the design asserts that Requirements 3.2.1 and 3.3.2 allow retention 'until the transaction is settled'. The evidence register contains no source confirming that reading, and the companion PCI DSS Scoping Memo is still a draft. If a QSA reads the standard as prohibiting retention of sensitive authentication data after authorization, NFR-5 fails and AD-009 would have to change. This review cannot confirm or refute the clause and treats it as unverified.

- Where: p.10 §12.4 (NFR-6, NFR-5): "3.2.1 and 3.3.2, which allow sensitive authentication data to be retained in encrypted form until the transaction is settled."
- Where: p.10 §12.4 (NFR-6): "the credential during a cascade and for incremental authorizations (ride-hailing tips, hotel extensions)."
- Where: p.3 §2.2 (NFR-6): "Sensitive authentication data shall be handled per PCI DSS v4.0 Requirements 3.2.1 and 3.3.2: stored only in encrypted form, in the"
- Evidence EV-013 (doc, supports): "3.2.1 and 3.3.2, which allow sensitive authentication data to be retained in encrypted form until the transaction is settled." [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-014 (doc, supports): "the credential during a cascade and for incremental authorizations (ride-hailing tips, hotel extensions)." [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-015 (doc, supports): "Sensitive authentication data shall be handled per PCI DSS v4.0 Requirements 3.2.1 and 3.3.2: stored only in encrypted form, in the" [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-016 (doc, supports): "Companion documents MPOP Conceptual Design v1.2; PCI DSS Scoping Memo (draft); Acquirer Connectivity Matrix" [doc:DOC-design_v1#p1/s12.4]
- Evidence EV-086 (inference, supports): "Incremental authorizations occur after the initial authorization completes, so the design depends on post-authorization retention of SAD being permitted. No register evidence confirms this, and the scoping memo is still a draft." [inference:EV-086] derived from EV-013, EV-014, EV-016
- Recommendation: Obtain a written QSA interpretation of 3.2.1, 3.3.1 and 3.3.2 for (a) CVC re-presentation within a cascade before any approval and (b) incremental authorizations after approval. If (b) is not permitted, limit CVC retention in Section 12.4 to the in-flight authorization (delete it on the first approval or final decline), drop CVC from incremental authorizations (use the acquirer's incremental-auth reference), and amend NFR-6 and AD-009 accordingly.
  - Issue: A compliance status the Vault design depends on is asserted without verification.
  - Rationale: NFR-5 is a binding constraint, and a wrong reading would put the Vault design out of compliance at assessment.
  - Expected benefit: The NFR-5 and NFR-6 position is settled before Phase 2 builds the CVC store. (objectives: NFR-5, NFR-6)
  - Supporting evidence: EV-013, EV-014, EV-015, EV-086, EV-016
  - Verification: The QSA opinion is attached to the finalised PCI DSS Scoping Memo, and the NFR-6 test asserts the confirmed deletion trigger.
- Next step: PCI compliance lead with the QSA: Request a written interpretation before Phase 2 and record the decision on AD-009.
- Decision AD-009 (24 Confirmed Decisions - CVC handling): refines. The retention window may shrink to the in-flight authorization. This would become a challenge if the QSA rules against retention, but there is no external evidence yet.
- Decision AD-029 (NFR-6): refines. NFR-6's 'deleted at settlement' trigger may need restating once the interpretation is confirmed.
- Decision AD-028 (NFR-5): preserves. The investigation protects the Level 1 assessment outcome.

### FND-014 Network tokens 'from launch' (AD-010) and the 'ready' rating for Phase 3 depend on a Token Requestor application not yet submitted

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.75 (medium) · rank 14
- Disposition: **governance decision** · already acknowledged in the document

AD-010 makes VTS and MDES network tokens the primary card-on-file credential from launch, and Phase 3 is marked 'No - ready'. Backlog item 2 shows the Token Requestor registration, the commercial agreement and certification are not yet started. The backlog acknowledges the item, but nothing links it to the decision or the phase gate, and it has no owner, date or fallback. Without a TRID, all card-on-file traffic falls back to PAN, so the confirmed decision and the readiness rating are not true at launch.

- Where: p.18 §24 (FR-14): "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch; PAN"
- Evidence EV-058 (doc, supports): "the commercial agreement with a token service provider; certification test plan. Application not yet submitted." [doc:DOC-design_v1#p19/s2]
- Evidence EV-059 (doc, supports): "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch; PAN" [doc:DOC-design_v1#p18/s24]
- Evidence EV-060 (doc, supports): "Transaction core - Payments API, idempotency, state machine, ledger, outbox; card-on-file" [doc:DOC-design_v1#p21/s2]
- Evidence EV-096 (inference, supports): "A confirmed 'from launch' decision and a 'ready' build phase both rest on a scheme registration and certification that has not been applied for." [inference:EV-096] derived from EV-058, EV-059, EV-060
- Recommendation: Mark Phase 3 card-on-file as 'Partially - Backlog item 2'. Give Backlog item 2 an owner, a submission date and a certification lead time. Either reword AD-010 to 'from TRID certification', with PAN plus MIT/CIT indicators until then, or make TRID certification a go-live gate.
  - Issue: A confirmed decision depends on a pending external dependency with no tracking.
  - Rationale: FR-14 only requires network tokens where the issuer supports them, so a PAN plus stored-credential fallback is compliant. The 'from launch' commitment is the part at risk.
  - Expected benefit: FR-14 is honestly scheduled, and Phase 3 readiness is accurate. (objectives: FR-14)
  - Supporting evidence: EV-058, EV-059, EV-060, EV-096
  - Verification: The FR-14 stored-credential test passes in both modes: network token where provisioned, and PAN with correct MIT/CIT indicators where not.
- Next step: Head of Payments Partnerships: Submit the Token Requestor application and record a certification date against AD-010.
- Decision AD-010 (24 Confirmed Decisions - Card-on-file credential): refines. Network tokens stay primary; the launch timing is made conditional on TRID certification.
- Decision AD-061 (FR-14): preserves. FR-14 is met through the PAN plus stored-credential fallback.

## Validation needs

### FND-012 DynamoDB per-merchant capacity claim (10,000 WCU per partition, 1,800 WCU at peak) is unverified

- **validation need** · unsupported or incorrect claim · severity **high** · confidence 0.50 (medium) · rank 12
- Disposition: **needs investigation** (also: needs prototyping)

Section 9.3 rests the merchant_id partition key on a single partition sustaining 10,000 WCU per second, and counts two writes per request, about 1,800 WCU for the largest merchant. The register cannot confirm that per-partition limit. The count also ignores item size, even though response_body is up to 4 KB, and ignores any item-collection size constraint from the LSI for a merchant with 45% of peak traffic. If the real limits are lower, the largest merchant's idempotency writes will throttle on campaign days, causing failed payments for 45% of peak traffic and threatening NFR-1 and NFR-3.

- Where: p.8 §9.3 (NFR-1): "single partition sustains up to 10,000 write capacity units per second."
- Where: p.8 §9.3 (NFR-1): "two writes - lock acquisition and completion update - or about 1,800 WCU at peak"
- Evidence EV-050 (doc, supports): "single partition sustains up to 10,000 write capacity units per second." [doc:DOC-design_v1#p8/s9.3]
- Evidence EV-051 (doc, supports): "two writes - lock acquisition and completion update - or about 1,800 WCU at peak" [doc:DOC-design_v1#p8/s9.3]
- Evidence EV-052 (doc, supports): "response_body String Serialised response, up to 4 KB" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-053 (doc, supports): "created_at String ISO 8601; LSI sort key lsi_created_at" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-094 (inference, supports): "The per-partition limit, per-KB write charging and LSI item-collection behaviour are not confirmed in the register; if writes are charged by item size, a 4 KB completion update costs several WCU and the 1,800 WCU estimate understates load on one partition key." [inference:EV-094] derived from EV-050, EV-051, EV-052, EV-053
- Recommendation: Verify the DynamoDB per-partition write limit, WCU charging by item size, LSI item-collection limits and adaptive-capacity behaviour against AWS documentation, then recompute Section 9.3. If the limits are insufficient, write-shard the partition key (merchant_id plus a hash-derived suffix) and serve the back-office view through a GSI instead of the LSI. Define fail-closed (HTTP 503 with Retry-After) behaviour on throttling.
  - Issue: The capacity claim relies on an unverified platform limit and omits item size and the LSI's effects.
  - Rationale: Idempotency sits on the critical path of every mutating call for the largest merchant.
  - Expected benefit: NFR-1 is met for the largest merchant at the 2,000 TPS peak. (objectives: NFR-1, FR-5, NFR-3)
  - Supporting evidence: EV-050, EV-051, EV-052, EV-053, EV-094
  - Verification: Load test of 900 TPS on a single merchant_id with 4 KB responses for 4 hours, with zero throttled writes.
- Next step: Payments Core tech lead: Confirm the DynamoDB limits from AWS documentation and run a single-merchant load prototype in Phase 3.
- Decision AD-006 (24 Confirmed Decisions - Idempotency store): refines. The table may need write-sharded keys or a GSI. This becomes a challenge to the key schema only if investigation confirms lower limits.

### FND-015 Scheme reattempt limits and cross-acquirer reattempt rules are referenced but never stated, yet the Retry Engine is rated 'Ready'

- **validation need** · missing or unverifiable requirement · severity **medium** · confidence 0.55 (medium) · rank 15
- Disposition: **needs investigation** (also: needs testing)

Section 11.3 stops reattempting 'at the scheme limits applicable to the card', and the FR-7 test checks those limits, but the document never states the limits, the source rule set, or whether a cascade of codes 05, 91 or 96 to a different acquirer counts as a reattempt. Section 27 still rates the Retry Engine 'Ready'. The register holds no Visa or Mastercard rule evidence, so the classification in Section 11.1 is unverified. Scheme non-compliance (FR-7) could bring fines or excessive-reattempt fees.

- Where: p.9 §11.3 (FR-7): "window and stops reattempting at the scheme limits applicable to the card."
- Where: p.20 §27 (FR-7): "Retry Engine Ready Outcome classes, cascade limits and scheme rules specified (Section 11)."
- Where: p.19 §26.1 (FR-7): "outcomes, never exceed two additional attempts, and stop at scheme reattempt limits."
- Evidence EV-061 (doc, supports): "window and stops reattempting at the scheme limits applicable to the card." [doc:DOC-design_v1#p9/s11.3]
- Evidence EV-062 (doc, supports): "Retry Engine Ready Outcome classes, cascade limits and scheme rules specified (Section 11)." [doc:DOC-design_v1#p20/s27]
- Evidence EV-063 (doc, supports): "outcomes, never exceed two additional attempts, and stop at scheme reattempt limits." [doc:DOC-design_v1#p19/s26.1]
- Evidence EV-097 (inference, supports): "Without stated numeric limits and a cited rule source, neither the Retry Engine nor the FR-7 test can be built to a definite pass or fail." [inference:EV-097] derived from EV-061, EV-062, EV-063
- Recommendation: Add a Section 11.3 table of per-scheme reattempt limits, windows and code categories, sourced from the current Visa and Mastercard rules and acquirer guidance, and state whether a cross-acquirer cascade counts as a reattempt. Re-rate the Retry Engine as 'Mostly ready' until the table exists, and parameterise the FR-7 test from it.
  - Issue: The scheme rules that FR-7 depends on are undefined.
  - Rationale: The outcome classification and the counters cannot be implemented without them.
  - Expected benefit: FR-7 is implementable and testable, and scheme penalties are avoided. (objectives: FR-7)
  - Supporting evidence: EV-061, EV-062, EV-063, EV-097
  - Verification: Acquirer sign-off on the table, and FR-7 simulations asserting each limit.
- Next step: Scheme compliance manager: Obtain current scheme reattempt rules from ACQ-SG1 and ACQ-SG2 and populate Section 11.3.
- Decision AD-054 (FR-7): preserves. The change makes FR-7's scheme constraint concrete.
- Decision AD-011 (24 Confirmed Decisions - Cascade policy): preserves. The cascade triggers are unchanged pending scheme confirmation.

### FND-018 Several acceptance criteria cannot demonstrate their requirements (FR-5 concurrency, FR-12 'exactly one', NFR-9 baseline)

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.80 (high) · rank 18
- Disposition: **refinement now** (also: needs testing)

The FR-5 test resends only after the first response has arrived, so it never exercises the concurrent duplicates that FR-5 names explicitly, or cross-merchant key reuse (see FND-001). The FR-12 test expects 'exactly one event' per state change, whereas Section 17 specifies at-least-once delivery, so the test either fails legitimately or checks the wrong property. The NFR-9 test measures noise relative to an unspecified rate limit and without a baseline load level, and NFR-4 limitations are covered in FND-005.

- Where: p.19 §26.1 (FR-5): "Send a create-payment request; after its response is received, resend the identical request with the same"
- Where: p.19 §26.1 (FR-12): "Every state change emits exactly one event; signatures verify with the reference library; a failing endpoint"
- Where: p.20 §26.2 (NFR-9): "One merchant at 3× its rate limit does not move other merchants' p99 by more than 5%."
- Evidence EV-071 (doc, supports): "Send a create-payment request; after its response is received, resend the identical request with the same" [doc:DOC-design_v1#p19/s26.1]
- Evidence EV-072 (doc, supports): "Every state change emits exactly one event; signatures verify with the reference library; a failing endpoint" [doc:DOC-design_v1#p19/s26.1]
- Evidence EV-073 (doc, supports): "One merchant at 3× its rate limit does not move other merchants' p99 by more than 5%." [doc:DOC-design_v1#p20/s26.2]
- Evidence EV-074 (doc, supports): "At-least-once. A delivery succeeds on any 2xx within 10 seconds." [doc:DOC-design_v1#p13/s17]
- Evidence EV-100 (inference, supports): "A sequential replay cannot detect race defects in the lock path, and an 'exactly one' delivery assertion contradicts at-least-once semantics, so these tests can pass or fail independently of the requirement." [inference:EV-100] derived from EV-071, EV-072, EV-074
- Recommendation: FR-5: add N concurrent identical requests (expect one authorization, with the others getting 409 or the identical response), cross-merchant same-key requests, and a mismatched body while Redis is warm. FR-12: assert exactly one event_id per state change and at least one successful delivery, with duplicates carrying the same event_id. NFR-9: specify the background load (for example the NFR-1 mix at 2,000 TPS) and the noisy merchant's tier limit.
  - Issue: Several acceptance tests do not exercise the property their requirement states.
  - Rationale: Section 26 is the basis for the Phase 9 test plan and the go-live evidence.
  - Expected benefit: FR-5, FR-12 and NFR-9 are demonstrably met. (objectives: FR-5, FR-12, NFR-9)
  - Supporting evidence: EV-071, EV-072, EV-073, EV-074, EV-100
  - Verification: Revised Section 26 rows are reviewed by QA and run in Phase 9.
- Next step: QA lead: Rewrite the FR-5, FR-12 and NFR-9 acceptance criteria in Section 26.
- Decision AD-052 (FR-5): preserves. The test is aligned with FR-5's concurrency clause.
- Decision AD-059 (FR-12): preserves. The test is aligned with at-least-once FR-12 delivery.
- Decision AD-070 (NFR-9): preserves. NFR-9 becomes measurable.

## Recommended refinements

| Finding | Change | Expected benefit |
|---|---|---|
| FND-001 | In Section 9.2 and AD-006, change the Redis key to idem:resp:{merchant_id}:{idempotency_key}. Store request_hash with the cached response and compare it on every hit, returning 422 on a mismatch, so Redis applies the same rules as the DynamoDB path. Add a cross-merchant collision case and a different-body case to the FR-5 acceptance test in Section 26.1. | FR-5 and P3 hold on both tiers, and no merchant can read another merchant's payment object. |
| FND-002 | Remove card_number from the Section 13.1 payload and send the keyed PAN fingerprint (Section 12.1) or an FRV-1-specific keyed token instead. If FRV-1 cannot score without the PAN, an accountable owner must decide either to send it from a CDE-resident component under its own Vault identity, with FRV-1 added to the PCI service-provider inventory and Section 12.2, or to accept the lower scoring quality. Record the outcome in Section 12.2 and the PCI scoping memo. | The CDE stays confined to the Section 12.2 components (NFR-5), P2 and P9 hold, and FRV-1 does not become a cardholder-data recipient before a DPA exists. |
| FND-003 | In Section 11.2, for an attempt that timed out or returned 5xx: (a) send an authorization reversal or void through the adapter's Connector interface before or in parallel with the next attempt; (b) record late responses on the attempt with outcome LATE_APPROVED and trigger automatic reversal, not discard; (c) extend the Section 20.3 sweeper and Section 16.2 matching to raise an exception for any approved attempt that is not the payment's winning attempt. Add a Connector 'reverse' operation to the FR-3 conformance suite. | FR-7 cascades do not double-hold customer funds, P1 keeps provider responses as inputs to the payment record, and orphan holds are reconcilable under FR-11. |
| FND-004 | Obtain a written QSA interpretation of 3.2.1, 3.3.1 and 3.3.2 for (a) CVC re-presentation within a cascade before any approval and (b) incremental authorizations after approval. If (b) is not permitted, limit CVC retention in Section 12.4 to the in-flight authorization (delete it on the first approval or final decline), drop CVC from incremental authorizations (use the acquirer's incremental-auth reference), and amend NFR-6 and AD-009 accordingly. | The NFR-5 and NFR-6 position is settled before Phase 2 builds the CVC store. |
| FND-005 | Governance: either (a) restate NFR-4 as RPO of N seconds for unplanned regional loss (RPO zero within the region), backed by a provider-reconciliation recovery procedure that re-derives lost authorizations from acquirer reports, or (b) adopt a synchronous cross-region commit for payment and ledger writes and re-budget NFR-2. Refinement either way: add merchant_id, idempotency_key and request_hash columns (unique per merchant and key) to the payment table in Section 19, so that Section 20.2 reconstruction is possible. | NFR-4 becomes achievable or honestly restated, and FR-5 holds across a regional failover. |
| FND-006 | Change Section 16.2 to match each provider file incrementally on arrival, keeping a final complete-day step only for cross-provider netting and multi-provider payouts. Define a 07:45 SGT cut-off after which reports publish with late providers marked 'pending', with an escalation path for missing or malformed files. Alternatively, renegotiate the ACQ-TH1 delivery time or relax the NFR-8 deadline. Benchmark the matcher at 2027 volume. | NFR-8 report deadlines and FR-17 payout schedules are met, and a single late file no longer blocks all merchants. |
| FND-007 | In Section 7, track settlement status and refund status as separate attributes (or add PARTIALLY_REFUNDED/REFUNDED to SETTLED transitions). Add CAPTURED to CAPTURED for additional partial captures up to amount_minor, plus an explicit 'final capture' flag that releases the remainder. Correct Section 8 step 10 to 'memo-ledger entry'. Add refund, partial-capture and FX journal examples to Section 14.2. | FR-1, FR-2 and FR-10 cover real lifecycles, and NFR-8 auto-match is not eroded by refunded payments. |
| FND-008 | Amend Section 12.3 and AD-008 to launch with at least two HSMs in different AZs, and replace the TPS trigger with a measured-utilisation trigger (for example, sustained HSM operations above 60% of benchmarked capacity). In Section 11.1, classify a Vault or HSM 503 as a non-cascading system failure that does not increment scheme reattempt counters. Benchmark HSM unwrap throughput and latency at peak (card authorizations plus cascades plus tokenisation) and measure restore-from-backup time. | Card acceptance survives the loss of an HSM or an AZ (NFR-3), and the cascade budget is not wasted on Vault outages. |
| FND-009 | In Section 18.4: require step-up TOTP at the moment of the change, for every role (login-time policy under AD-018 is unchanged); require approval by a second user (an Owner if Finance initiated the change); notify all Owners and the previous account's registered contact; apply a cooling-off period (for example, the first payout to a new account is held 48 hours); and keep the verified_at account verification as a precondition. Remove 'edit payout bank account' from Finance in Section 18.2, or make it request-only. | P9 holds, and payout funds under FR-17 are protected from account takeover. |
| FND-010 | In Section 28, move the go-live gate for card traffic after Phase 8 and after the PCI DSS assessment, load test and DR game-day portions of Phase 9, or allow PayNow-only go-live after Phase 7. If cards must launch earlier, record a time-boxed risk acceptance signed by a named executive, with compensating controls (merchant velocity limits and low per-transaction caps). | FR-9 and NFR-5 are met, or deviations are knowingly accepted, before money is at risk. |
| FND-011 | In Section 21.1, budget the cascade path explicitly, using the split between timeout and soft-decline retryables from 2025 data. Either cut the per-attempt timeout to fit within the 1,500 ms end-to-end budget (with a global payment deadline that stops cascading when the remaining budget is too small), or restate NFR-2 so it excludes 3DS customer time and defines whether p99 is measured over all card payments. State that 3DS challenge time is excluded. | NFR-2 becomes achievable and testable. |
| FND-012 | Verify the DynamoDB per-partition write limit, WCU charging by item size, LSI item-collection limits and adaptive-capacity behaviour against AWS documentation, then recompute Section 9.3. If the limits are insufficient, write-shard the partition key (merchant_id plus a hash-derived suffix) and serve the back-office view through a GSI instead of the LSI. Define fail-closed (HTTP 503 with Retry-After) behaviour on throttling. | NFR-1 is met for the largest merchant at the 2,000 TPS peak. |
| FND-013 | In Section 9.2, add a lease timestamp to IN_PROGRESS records; a sweeper scanning the idempotency table resolves expired leases (no payment found: delete the record so the client retry proceeds; payment found: resolve it by state). Extend the Section 20.3 sweeper to CREATED payments older than the fraud and 3DS budget. Add a 'DynamoDB unavailable or throttled' row to Section 20.4 that fails closed with 503 and Retry-After. Document the 24-hour key semantics and offer optional merchant_reference uniqueness per merchant account as protection against reuse after expiry. | FR-5 holds through crashes and dependency failures, with no 24-hour lockouts. |
| FND-014 | Mark Phase 3 card-on-file as 'Partially - Backlog item 2'. Give Backlog item 2 an owner, a submission date and a certification lead time. Either reword AD-010 to 'from TRID certification', with PAN plus MIT/CIT indicators until then, or make TRID certification a go-live gate. | FR-14 is honestly scheduled, and Phase 3 readiness is accurate. |
| FND-015 | Add a Section 11.3 table of per-scheme reattempt limits, windows and code categories, sourced from the current Visa and Mastercard rules and acquirer guidance, and state whether a cross-acquirer cascade counts as a reattempt. Re-rate the Retry Engine as 'Mostly ready' until the table exists, and parameterise the FR-7 test from it. | FR-7 is implementable and testable, and scheme penalties are avoided. |
| FND-016 | Add a personal-data inventory section listing each field (device, IP, hashed contacts, addresses, customer refund bank account, merchant-user identities), its purpose, retention, access logging and recipients, including FRV-1. Define data-subject request handling. Obtain legal opinions on whether the five markets' laws and payment-system rules allow processing in ap-southeast-1, DR in ap-southeast-3 and sharing with FRV-1. | NFR-7 compliance per market, and early detection of any localisation constraint. |
| FND-017 | Define the FR-8 and Section 10.3 tolerance as percentage points of the approval prior. State that the Section 10.2 score selects only among acquirers whose approval prior is within tolerance of the best. Add FR-8 boundary cases (1.9 and 2.1 points) to the Section 26.1 test. | FR-8 is unambiguous and verifiable. |
| FND-018 | FR-5: add N concurrent identical requests (expect one authorization, with the others getting 409 or the identical response), cross-merchant same-key requests, and a mismatched body while Redis is warm. FR-12: assert exactly one event_id per state change and at least one successful delivery, with duplicates carrying the same event_id. NFR-9: specify the background load (for example the NFR-1 mix at 2,000 TPS) and the noisy merchant's tier limit. | FR-5, FR-12 and NFR-9 are demonstrably met. |
| FND-019 | Add to Section 16.3: the reserve and dispute-hold calculation and who configures it (the risk team, per merchant risk tier); negative-balance handling (carry-forward and netting against the next settlement, plus a direct-debit or invoice fallback); and the refund-to-bank flow (account capture through a hosted form, name-check verification, a payout journal using refund_clearing). Re-rate Payouts as 'Mostly ready' until these are added. | FR-15 and FR-17 can be implemented without improvised policy. |
| FND-020 | Add an operational ownership table (process, owner role, cadence or SLA, approval needed) covering the Routing Review, the exception queue, discrepancy freezes, DR rehearsals and HSM capacity. Add a change log to the title page, and make finalisation of the PCI memo a Phase 2 entry criterion. | Changes to routing and financial operations stay auditable (P10), and open items close on time. |

## Areas where no change is needed

- FND-021 Ledger written atomically with state changes through a transactional outbox, append-only and with enforced balance: Atomic state, journal and outbox commits, database-enforced immutability and an enforced balance invariant directly satisfy P1, P5, P7 and FR-10. The remaining ledger gaps (refund and FX examples, state transitions) are covered in FND-007 and do not undermine this core.
- SA-001 (sections 15): Signed 64-bit minor units with a versioned ISO 4217 exponent table, explicit adapter conversion that rejects any amount needing rounding, a single half-to-even rounding step with residue tracking, and integer-only JSON together satisfy P4 and AD-015 for all five markets, including IDR provider exponent quirks.
  - p.12 §15: "No floating-point type is used for amounts in any service, schema, or API payload."
  - p.12 §15: "Where a provider expects a different exponent than ISO 4217 (for example, IDR as whole rupiah), the adapter"
- SA-002 (sections 17): Per-endpoint signing secrets, timestamped HMAC signatures, a bounded retry schedule that does add up to 12 attempts within 72 hours, per-endpoint in-flight caps and circuit breakers, and SSRF and DNS-rebinding protection through validate-then-connect meet FR-12 and P7 and isolate merchants from each other. Only the acceptance test wording needs correction (FND-018). (see FND-018)
  - p.13 §17: "Endpoints must be HTTPS on port 443. The dispatcher resolves the hostname once at send"
  - p.13 §17: "Each endpoint has a cap of 20 in-flight deliveries and its own circuit breaker, so a failing endpoint"
- SA-003 (sections 14.3): The asynchronous Balance Projector removes hot-row contention on high-volume accounts at 2,000 TPS (NFR-1). Payouts are gated on projector progress, and a nightly recomputation freezes payouts on any discrepancy, which protects P1 and FR-17. (see FND-021)
  - p.12 §14.3: "No payment-path transaction updates a balance row, which avoids hot-row contention on"
- SA-004 (sections 18.5): Back-office access combines corporate SSO, hardware-key MFA, masked read-only data by default, and just-in-time elevation with a second approver and a mandatory reason for write actions. This meets P9 and P10 for internal staff and preserves AD-019.
  - p.14 §18.5: "data by default; write actions (manual refunds, payout holds, merchant suspension) require just-in-time elevation"
- SA-005 (sections 6): Secret API keys are shown once and stored only as a SHA-256 hash with a visible prefix, and publishable keys are restricted to tokenise and confirm. This limits the impact of a credential leak and supports P8's fail-closed authentication.
  - p.6 §6: "Secret API keys are displayed once and stored only as a SHA-256 hash with a visible prefix."

## Unresolved issues and next steps

- FND-004: Whether PCI DSS v4.0 Requirements 3.2.1 and 3.3.2 allow encrypted CVC to be kept after authorisation, until settlement or for up to 72 hours, is unverified. The PCI DSS Scoping Memo is still a draft. (FND-004) Next step (PCI compliance lead with the engaged QSA): Get a written QSA interpretation for CVC retention covering cascades and incremental authorisations, and confirm with each acquirer whether the CVC is required on re-presentation. Then either confirm AD-009 or redesign Section 12.4 and NFR-6.
- FND-005: NFR-4's zero RPO on regional loss conflicts with asynchronous Aurora Global Database replication (AD-004), and idempotency state cannot be rebuilt from the payment table. (FND-005) Next step (Head of Platform Engineering with the business owner of NFR-4): Choose between relaxing NFR-4 for unplanned regional loss and adopting a synchronous or quorum cross-region write design. Add idempotency key, request hash and merchant_id columns to the payment record, and rewrite the NFR-4 game-day criterion to measure lost commits.
- FND-006: Starting reconciliation only after every file for day T has arrived (AD-016) makes publication by 08:00 SGT (NFR-8) impossible at current file times and volumes, and one late file blocks all reports and payouts. (FND-006) Next step (Finance Operations lead with the Reconciliation engineering lead): Decide between a cut-off with per-provider or incremental matching and a later NFR-8 deadline. Specify the late-file and missing-file path, and validate it with a replay at 2027 volume.
- FND-008: A single CloudHSM in one AZ is a single point of failure for all card acceptance, and the 1,500 TPS trigger for adding a second HSM is never reached. (FND-008) Next step (CDE/Vault engineering lead with the platform risk owner): Decide whether to deploy HSMs across multiple AZs at launch or to formally accept the risk against NFR-3. Measure the time to restore from an HSM backup, and change the mapping of Vault 503 responses so they do not consume cascade attempts.
- FND-010: The first card cohort goes live before the Fraud Hook, the PCI DSS assessment, the load tests and the DR game day, and no one owns that risk acceptance. (FND-010) Next step (Programme sponsor / Chief Risk Officer): Either make FR-9, NFR-5, NFR-1/NFR-2 and NFR-4 go-live gates for the Singapore card cohort, or record a formal, time-limited risk acceptance with compensating controls.
- FND-012: The DynamoDB per-partition write limit, the effect of item size on WCU, and the LSI item-collection limit for a merchant with 45% of peak traffic are all unverified. (FND-012) Next step (Payments Core tech lead): Confirm the limits from primary AWS documentation and run a load test at 900 TPS for one merchant with realistic response sizes. If the limits are too tight, reconsider the partition key or the LSI.
- FND-014: AD-010 makes network tokens the card-on-file credential from launch, but the Token Requestor application has not been submitted, and the dependency is not linked to Phase 3 readiness. (FND-014) Next step (Card partnerships / scheme relations manager): Submit the VTS and MDES Token Requestor applications with a target date, make the TRID a Phase 3 gate, and define the interim PAN-fallback posture explicitly.
- FND-015: The scheme reattempt limits, the source rule set and the treatment of cross-acquirer cascades are not stated, yet the Retry Engine is rated Ready. (FND-015) Next step (Payments Core tech lead with the scheme compliance analyst): Document the Visa and Mastercard reattempt rules and fee programmes that apply in each market, decide whether a cross-acquirer cascade counts as a reattempt, and encode the rules in Section 11 and the FR-7 test.
- FND-016: There is no personal-data inventory, no purpose and retention map, no data-subject request process and no cross-border transfer basis for NFR-7. Whether any market requires data to be processed locally is unverified. (FND-016) Next step (Data Protection Officer): Produce a field-level data map with purposes and retention periods, a cross-border transfer assessment for each market (including the Jakarta DR copy and FRV-1), and a DSR procedure. Obtain legal sign-off in each market.
- FND-020: No owners or SLAs are named for the Routing Review, the reconciliation exception queue, payout freezes, DR rehearsals or the HSM trigger, and the document has no change log. (FND-020) Next step (Head of Payments Platform Engineering): Add a RACI for each recurring operational process and a document change log, and link each pending backlog item to its owner and target date.
- Acknowledged open items that remain outside the findings: the dispute and chargeback module, the Admin API JSON schemas and error catalogue, the ACQ-PH1 v3 adapter migration, multi-currency payouts, and sample settlement files from ACQ-PH1 and WAG-1 for the reconciliation parsers. Next step (Payments Core product manager): Give each backlog item an owner, a target phase and a gating dependency in Section 28, and obtain the sample settlement files before Phase 6 starts.
- The PCI DSS Scoping Memo on which Section 12.2 relies is still a draft, so the CDE boundary behind NFR-5 is not yet agreed. (FND-002, FND-004) Next step (PCI compliance lead): Finalise the scoping memo, taking into account the Fraud Hook and CVC changes, and get the QSA to agree it before Phase 2 build.

Research questions left unanswered:
- RQ-012: What are DynamoDB's documented per-partition throughput limits (WCU and RCU per partition), and how are WCUs charged for items up to about 4–5 KB? Does a table with an LSI have a 10 GB item-collection limit per partition-key value and lose split-for-heat? How long can TTL deletion lag? Is the claim of 10,000 WCU per partition, and about 1,800 WCU for the largest merchant, correct?
- RQ-013: Do PCI DSS v4.0 Requirements 3.2.1, 3.3.1 (including 3.3.1.2) and 3.3.2 permit storing the card verification code after authorization completes, until settlement or for up to 72 hours, for cascades and incremental authorizations? Or does 3.3.2 cover only SAD stored before authorization completes?
- RQ-014: How do Visa and Mastercard rules classify the response codes in Section 11.1 (for example 51 and 05, Visa decline categories, Mastercard Merchant Advice Codes 03 and 21)? What are the reattempt limits per card over 30 days, and does resubmitting to a different acquirer count as a reattempt under those rules?
- RQ-015: What do AWS documents about Aurora Global Database replication lag, and about data loss (RPO) on unplanned cross-Region failover compared with managed switchover? Does any Aurora configuration provide RPO zero across Regions?
- RQ-016: What do AWS recommend for CloudHSM production availability (minimum number of HSMs and spread across AZs)? How long does restoring an HSM from backup take, and what per-HSM throughput is documented for symmetric key unwrap operations?
- RQ-019: Do Indonesian payment-system and data-protection rules (Law 27/2022, GR 71/2019, Bank Indonesia regulations for payment system operators) require domestic processing or storage of Indonesian transaction data? And do Singapore, Malaysia, Thailand and the Philippines impose transfer conditions that apply when all markets' data is processed in Singapore, replicated to Jakarta for DR, and shared with FRV-1?

## Evidence limitations

- Only the extracted page-marked text could be reviewed, not the original PDF. The architecture diagram (Figure 1) and the tables were read in flattened text form, so a layout detail or table cell that was garbled in extraction could have been misread. Every finding is tied to quoted text, so the effect on the verdict is small, but a diagram-only detail (for example connectivity in Figure 1) was not verified. (DEG-001)
- Pending Backlog item 2 (Token Requestor onboarding) was not treated as an approved decision. FND-014 is based on the backlog text and AD-010 directly, so the conclusion stands, but any registry-level status of that item was not taken into account. (DEG-002)
- Pending Backlog item 3 (smart-routing model) was not treated as an approved decision or constraint. Its effect on FR-8 routing was judged from the document text only, and it does not affect the verdict. (DEG-003)
- Pending Backlog item 4 (FRV-1 contract and DPA) was not treated as an approved decision. FND-002, FND-010 and FND-016 rely on the document's own statement that the contract is pending, so the verdict is unaffected. (DEG-004)
- Pending Backlog item 5 (ACQ-PH1 API v3 migration) was not treated as an approved decision or constraint. The review did not assess the migration's timing risk against the Philippines rollout. (DEG-005)
- Pending Backlog item 6 (multi-currency payouts and marketplace split rules) was not treated as an approved decision or constraint. Its interaction with FND-019 (payout rules) was judged from the document text only. (DEG-006)
- Pending Backlog item 7 (Admin API schemas) was not treated as an approved decision or constraint. The review relied on the document's own statement that the item is open and did not assess it further. (DEG-007)
- Section 28 (Build Phases) was not treated as an approved decision. FND-010 and FND-014 therefore treat the phase plan as design content that can be challenged, not as a binding constraint. If the phasing is in fact a binding commitment, the go-live condition would need a formal governance exception rather than a change to the plan. (DEG-008)
- No external research was possible, so the evidence register is empty. Several key premises remain unverified: the PCI DSS v4.0 rules on keeping sensitive authentication data (FND-004), DynamoDB partition and item-collection limits (FND-012), Visa and Mastercard reattempt rules (FND-015), CloudHSM availability and restore behaviour (FND-008), Aurora Global Database replication semantics (FND-005), and local-processing requirements in each market (FND-016). These are reported as validation needs or unresolved assumptions rather than confirmed defects. Overall confidence is reduced to 0.68, and some high findings could fall in severity, or rise, once primary sources are checked. (DEG-009)

## Evidence register

| ID | Type | Source | Retrieved | Cited |
|---|---|---|---|---|
| EV-001 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-002 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-003 | doc | doc:DOC-design_v1#p7/s9.1 | - | yes |
| EV-004 | doc | doc:DOC-design_v1#p4/s3 | - | yes |
| EV-005 | doc | doc:DOC-design_v1#p11/s13.1 | - | yes |
| EV-006 | doc | doc:DOC-design_v1#p10/s12.1 | - | yes |
| EV-007 | doc | doc:DOC-design_v1#p10/s12.2 | - | yes |
| EV-008 | doc | doc:DOC-design_v1#p4/s3 | - | yes |
| EV-009 | doc | doc:DOC-design_v1#p10/s12.2 | - | yes |
| EV-010 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-011 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-012 | doc | doc:DOC-design_v1#p9/s11.1 | - | yes |
| EV-013 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-014 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-015 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-016 | doc | doc:DOC-design_v1#p1/s12.4 | - | yes |
| EV-017 | doc | doc:DOC-design_v1#p16/s20.2 | - | yes |
| EV-018 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-019 | doc | doc:DOC-design_v1#p17/s20.2 | - | yes |
| EV-020 | doc | doc:DOC-design_v1#p20/s26.2 | - | yes |
| EV-021 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-022 | doc | doc:DOC-design_v1#p12/s16.1 | - | yes |
| EV-023 | doc | doc:DOC-design_v1#p13/s3 | - | yes |
| EV-024 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-025 | doc | doc:DOC-design_v1#p2/s1 | - | yes |
| EV-026 | doc | doc:DOC-design_v1#p6/s7.2 | - | yes |
| EV-027 | doc | doc:DOC-design_v1#p6/s7.2 | - | yes |
| EV-028 | doc | doc:DOC-design_v1#p13/s3 | - | yes |
| EV-029 | doc | doc:DOC-design_v1#p2/s2.1 | - | yes |
| EV-030 | doc | doc:DOC-design_v1#p7/s9 | - | yes |
| EV-031 | doc | doc:DOC-design_v1#p12/s14.3 | - | yes |
| EV-032 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-033 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-034 | doc | doc:DOC-design_v1#p2/s1 | - | yes |
| EV-035 | doc | doc:DOC-design_v1#p16/s20.1 | - | yes |
| EV-036 | doc | doc:DOC-design_v1#p10/s12.1 | - | yes |
| EV-037 | doc | doc:DOC-design_v1#p14/s18.4 | - | yes |
| EV-038 | doc | doc:DOC-design_v1#p14/s18.4 | - | yes |
| EV-039 | doc | doc:DOC-design_v1#p14/s18.3 | - | yes |
| EV-040 | doc | doc:DOC-design_v1#p14/s18.2 | - | yes |
| EV-041 | doc | doc:DOC-design_v1#p4/s3 | - | yes |
| EV-042 | doc | doc:DOC-design_v1#p21/s9 | - | yes |
| EV-043 | doc | doc:DOC-design_v1#p21/s8 | - | yes |
| EV-044 | doc | doc:DOC-design_v1#p21/s9 | - | yes |
| EV-045 | doc | doc:DOC-design_v1#p3/s2.1 | - | yes |
| EV-046 | doc | doc:DOC-design_v1#p17/s21.1 | - | yes |
| EV-047 | doc | doc:DOC-design_v1#p9/s10.5 | - | yes |
| EV-048 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-049 | doc | doc:DOC-design_v1#p20/s26.2 | - | yes |
| EV-050 | doc | doc:DOC-design_v1#p8/s9.3 | - | yes |
| EV-051 | doc | doc:DOC-design_v1#p8/s9.3 | - | yes |
| EV-052 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-053 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-054 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-055 | doc | doc:DOC-design_v1#p17/s20.3 | - | yes |
| EV-056 | doc | doc:DOC-design_v1#p7/s9.1 | - | yes |
| EV-057 | doc | doc:DOC-design_v1#p17/s20.4 | - | yes |
| EV-058 | doc | doc:DOC-design_v1#p19/s2 | - | yes |
| EV-059 | doc | doc:DOC-design_v1#p18/s24 | - | yes |
| EV-060 | doc | doc:DOC-design_v1#p21/s2 | - | yes |
| EV-061 | doc | doc:DOC-design_v1#p9/s11.3 | - | yes |
| EV-062 | doc | doc:DOC-design_v1#p20/s27 | - | yes |
| EV-063 | doc | doc:DOC-design_v1#p19/s26.1 | - | yes |
| EV-064 | doc | doc:DOC-design_v1#p11/s13.1 | - | yes |
| EV-065 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-066 | doc | doc:DOC-design_v1#p16/s19.1 | - | yes |
| EV-067 | doc | doc:DOC-design_v1#p19/s3 | - | yes |
| EV-068 | doc | doc:DOC-design_v1#p2/s2.1 | - | yes |
| EV-069 | doc | doc:DOC-design_v1#p9/s10.3 | - | yes |
| EV-070 | doc | doc:DOC-design_v1#p19/s26.1 | - | yes |
| EV-071 | doc | doc:DOC-design_v1#p19/s26.1 | - | yes |
| EV-072 | doc | doc:DOC-design_v1#p19/s26.1 | - | yes |
| EV-073 | doc | doc:DOC-design_v1#p20/s26.2 | - | yes |
| EV-074 | doc | doc:DOC-design_v1#p13/s17 | - | yes |
| EV-075 | doc | doc:DOC-design_v1#p3/s2.1 | - | yes |
| EV-076 | doc | doc:DOC-design_v1#p13/s16.3 | - | yes |
| EV-077 | doc | doc:DOC-design_v1#p21/s27 | - | yes |
| EV-078 | doc | doc:DOC-design_v1#p9/s10.3 | - | yes |
| EV-079 | doc | doc:DOC-design_v1#p13/s3 | - | yes |
| EV-080 | doc | doc:DOC-design_v1#p12/s14.3 | - | yes |
| EV-081 | doc | doc:DOC-design_v1#p16/s19 | - | yes |
| EV-082 | doc | doc:DOC-design_v1#p11/s14.1 | - | yes |
| EV-083 | inference | inference:EV-083 from EV-001, EV-002, EV-003, EV-004 | - | yes |
| EV-084 | inference | inference:EV-084 from EV-005, EV-007, EV-009 | - | yes |
| EV-085 | inference | inference:EV-085 from EV-010, EV-011, EV-012 | - | yes |
| EV-086 | inference | inference:EV-086 from EV-013, EV-014, EV-016 | - | yes |
| EV-087 | inference | inference:EV-087 from EV-017, EV-018, EV-019 | - | yes |
| EV-088 | inference | inference:EV-088 from EV-021, EV-022, EV-023, EV-024, EV-025 | - | yes |
| EV-089 | inference | inference:EV-089 from EV-026, EV-027, EV-028, EV-029 | - | yes |
| EV-090 | inference | inference:EV-090 from EV-032, EV-033, EV-034, EV-035, EV-036 | - | yes |
| EV-091 | inference | inference:EV-091 from EV-037, EV-038, EV-039, EV-040 | - | yes |
| EV-092 | inference | inference:EV-092 from EV-042, EV-043, EV-044, EV-045 | - | yes |
| EV-093 | inference | inference:EV-093 from EV-046, EV-047, EV-048, EV-049, EV-012 | - | yes |
| EV-094 | inference | inference:EV-094 from EV-050, EV-051, EV-052, EV-053 | - | yes |
| EV-095 | inference | inference:EV-095 from EV-054, EV-055, EV-057 | - | yes |
| EV-096 | inference | inference:EV-096 from EV-058, EV-059, EV-060 | - | yes |
| EV-097 | inference | inference:EV-097 from EV-061, EV-062, EV-063 | - | yes |
| EV-098 | inference | inference:EV-098 from EV-064, EV-065, EV-066, EV-067 | - | yes |
| EV-099 | inference | inference:EV-099 from EV-068, EV-069, EV-070 | - | yes |
| EV-100 | inference | inference:EV-100 from EV-071, EV-072, EV-074 | - | yes |
| EV-101 | inference | inference:EV-101 from EV-075, EV-076, EV-077 | - | yes |
| EV-102 | inference | inference:EV-102 from EV-016, EV-078, EV-079 | - | yes |
| EV-103 | inference | inference:EV-103 from EV-080, EV-082 | - | yes |

## Review coverage

| Criterion | Outcome | Findings | Note |
|---|---|---|---|
| design_intent | findings | FND-017, FND-011, FND-020 | Objectives, principles and confirmed decisions are generally clear. The FR-8 and routing tolerance units and the NFR-2 cascade and 3DS scope are ambiguous, and document change control is missing. |
| fitness_for_objectives | findings | FND-001, FND-003, FND-007, FND-021 | The ledger and outbox core is fit for purpose. The idempotency fast path, the cascade timeout handling and the state machine coverage do not meet FR-5, FR-7, FR-1 and FR-2 as written. |
| requirement_completeness | findings | FND-007, FND-013, FND-019, FND-016, FND-003 | Missing pieces: reversal paths, idempotency lock recovery, DynamoDB failure behaviour, payout-refund and negative-balance rules, and the personal-data inventory. Disputes are already acknowledged as backlog (AD-020). |
| internal_consistency | findings | FND-002, FND-005, FND-006, FND-011, FND-014, FND-010, FND-001, FND-007 | Contradictions found: Fraud Hook PAN use against P2 and Section 12.2; NFR-4 against asynchronous replication; NFR-8 against file times; the latency budget against the 3.8% retryable rate; AD-010 against Backlog item 2; and go-live sequencing against FR-9. |
| claims_and_external_constraints | findings | FND-004, FND-012, FND-015 | The evidence register is empty. The PCI SAD retention reading, the DynamoDB partition limits and the scheme reattempt rules are unverified and flagged for investigation, not asserted. |
| security_and_privacy | findings | FND-001, FND-002, FND-004, FND-009, FND-016 | Cross-merchant response leak, PAN outside the CDE, CVC retention, payout account takeover and the missing NFR-7 data mapping. Webhook signing, API key hashing and back-office controls are sound. |
| scalability_and_failure_modes | findings | FND-003, FND-008, FND-012, FND-013, FND-006 | Late approvals, the single HSM, DynamoDB hot-partition capacity, idempotency crash paths and late settlement files. The Aurora write budget relies on one spike on a smaller instance and should be re-measured in the Phase 9 load test. |
| assumptions_and_dependencies | findings | FND-014, FND-004, FND-012, FND-010 | Unresolved dependencies: TRID registration, the FRV-1 contract and DPA, the draft PCI memo and unverified platform limits. The 31% cascade recovery, measured on a single pilot, is noted but not material on its own. |
| verifiability | findings | FND-018, FND-011, FND-005, FND-017, FND-012, FND-015 | The FR-5, FR-12, FR-8, NFR-9 and NFR-4 criteria do not exercise their requirements. HSM, DynamoDB and matcher throughput need benchmarks. |
| decision_preservation | findings | FND-005, FND-006, FND-008, FND-021, FND-002 | Explicit challenges, each resting on two or more document items: AD-004 (against NFR-4), AD-016 (against NFR-8) and AD-008 (against NFR-3 and Section 20.1). The other recommendations refine AD-006, AD-009, AD-010, AD-011, AD-012, AD-013 and AD-018. |
| operability_and_governance | findings | FND-010, FND-020, FND-009 | Go-live before the fraud hook and the PCI assessment needs an accountable risk decision. Owners for the Routing Review, the exception queue, DR and HSM capacity, and a change log, are missing. |

## Run details

| | |
|---|---|
| Run | live_cc_opus_payments_v1 (started 2026-10-02T11:44:00Z) |
| Outcome | completed_degraded |
| Model | requested claude-opus-5-5; served claude-opus-5-5; effort high |
| Persona | generalist_architect |
| Tool transport | live |
| Research stop | tool_failure (error): no_tools; 0 iteration(s); 0 cited of 0 retrieved |
| Tool calls | none |
| Tokens | input 169004, cached 6198, output 116264; cost ~$3.68 (price table 2026-09-25) |
| Extractor | pdfplumber 0.11.10 |
| Config sha256 | 3b04b0c0a5366854b6559541ed31bfe23269f95fe91d3f91e07a0e918a541891 |
| Prompt bundle sha256 | af1b7952e21ffc77d3c3336a224909e1a84f86d54826bbe617814ce9e0e56b3a |
| Git commit | 4278b5f9ea2a86907f350bed8bb787c2d493a1aa |
| Fault schedule | none |
| Model fallbacks | 0 |
| Canonical text DOC-design_v1 | sha256 ad0bb891f073f14325b6ba716d58070d6b074ebaef9a9c64432138b89b64ec3c |
