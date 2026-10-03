# Design review: Serindit Pay — Merchant Payment Orchestration Platform

| | |
|---|---|
| Review | REV-langgraph_payments_v1_1 (full review) |
| Under review | DOC-design_v1: Serindit Pay — Merchant Payment Orchestration Platform v1.0, 21 pages |
| Verdict | **not fit** (confidence 0.75, medium) |
| Tools used | none |
| Tools disabled | mcp-internet-search, mcp-research-information, mcp-browser-automation-pw, mcp-document-intelligence |
| Reporting threshold | severity low and above (0 finding(s) in the appendix) |

> No external research was possible or used in this run: every finding rests on the document alone.


## Design intent

MPOP is Serindit Pay's Merchant Payment Orchestration Platform. It accepts payment requests from merchants, routes each one to an acquirer, e-wallet provider or bank-transfer rail, and accounts for every resulting movement of money until it is settled to the merchant. It replaces five per-market integration stacks with one merchant API across Singapore, Malaysia, Indonesia, Thailand and the Philippines. It provides routing with cascading, idempotency, a tokenising card vault that limits PCI DSS scope, a fraud-scoring hook, a double-entry ledger, daily reconciliation, payouts, signed webhooks and a merchant admin plane. The 2027 target is about 15,000 merchants at a peak of 2,000 TPS. Disputes case management, KYB, 3DS server internals and lending/BNPL are out of scope.

Objectives:
- Replace five per-market integration stacks, which share no routing or ledger and reconcile by spreadsheet, with one governed platform.
- Provide one versioned merchant API across five markets for about 15,000 active merchants at a peak of 2,000 payment-creation TPS (2027 target).
- P1: One payment, one truth: the payment record and the ledger are the source of truth; provider responses are only inputs.
- P2: Card data stays in the Vault: PAN and SAD never leave the Vault boundary except over the Card Adapter's connection to an acquirer; all other services handle tokens only.
- P3: Idempotency is scoped to the pair (merchant, key) for every mutating call.
- P4: Money is integers: amounts are integer minor units with an ISO 4217 code, and no floating-point type ever holds an amount.
- P5: The ledger is append-only; corrections are new reversing or adjusting journals.
- P6: Adapters absorb provider differences; the core never branches on provider identity.
- P7: At-least-once delivery with exactly-once effect through consumer deduplication on stable identifiers.
- P8: Fail closed on security failures; degrade gracefully to documented defaults when optional enrichment fails.
- P9: Least privilege and separation of duties; money-moving permissions are separated from configuration permissions.
- P10: Everything is auditable: every mutation, routing decision and admin action can be reconstructed.
- NFR-10: New acquirers or providers are onboarded through the Connector interface plus configuration only.

Constraints:
- NFR-5: The platform must be assessed as a PCI DSS v4.0 Level 1 service provider, with the CDE limited to the components listed in Section 12.2.
- NFR-6: Sensitive authentication data must be handled per PCI DSS v4.0 Req. 3.2.1/3.3.2: encrypted, held only in the Vault, and deleted at settlement.
- NFR-7: Personal data must comply with SG PDPA 2012, MY PDPA 2010, ID Law 27/2022, TH PDPA 2019 and PH DPA 2012.
- FR-7: Card reattempts must never occur where card scheme rules prohibit them.
- All workloads and primary data stores run in AWS ap-southeast-1 across three AZs; ap-southeast-3 is used only for disaster recovery.
- Principles win over later sections where the two conflict (Section 3).
- Merchant onboarding/KYB is handled by the Merchant Risk platform; MPOP consumes an approved-merchant event.
- Payment and attempt records are retained 7 years, audit records 5 years, and idempotency records 24 hours.
- ACQ-PH1 v2 API retires in Q3 2027, so the adapter must migrate before then.
- The first cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week intervals.

Key assumptions:
- Volume grows from 1,140 to 2,000 peak TPS and from 9,800 to 15,000 merchants by 2027; the largest merchant reaches a 45% share of peak.
- Fewer than 1% of card payments cascade, so cascades sit above p99 and do not affect the latency budget.
- A single DynamoDB partition sustains up to 10,000 WCU/s, enough for the largest merchant at about 1,800 WCU.
- PCI DSS v4.0 Req. 3.2.1/3.3.2 permit encrypted CVC retention until settlement (max 72 hours) for cascades and incremental authorizations.
- One CloudHSM with daily backups is adequate until sustained card volume exceeds 1,500 TPS.
- FRV-1 scoring quality needs the full PAN, which the Fraud Hook obtains through Vault detokenise.
- Aurora Global Database asynchronous replication with typical lag under 1 s supports the DR objectives.
- A spike test of 2,600 TPS on db.r7g.8xlarge supports sizing the writer at db.r7g.12xlarge.
- ACQ-SG2 is licensed in all five markets and serves as the default cascade secondary.
- Cascading recovers about 31% of retryable outcomes, based on a three-month ACQ-SG1 to ACQ-SG2 pilot.
- The first cohort can operate with disputes handled manually by Finance Operations and with the portal instead of the Admin API.
- Network tokens are available from launch, although token-requestor registration has not yet been submitted (Backlog item 2).

Located at: p.1 §1 (2 passages), p.2 §1.

## Fitness for purpose

**Not fit** (confidence 0.75). As written, the design is not fit to start building. One critical finding is open, and several high findings show requirements that fail by construction or principles that the design itself breaks. The main problems:

- FND-001 (critical): the Redis idempotency fast path is keyed without the merchant. This breaks P3 and FR-5 and can return one merchant's payment object to another merchant.
- FND-029: the Fraud Hook detokenises the PAN even though it is declared out of CDE scope. This breaks P2 and the NFR-5 scoping.
- FND-028: keeping the CVC after authorization rests on a doubtful reading of PCI DSS.
- FND-019: zero RPO (NFR-4) contradicts asynchronous cross-region replication.
- FND-005: the latency budget assumes cascades fall outside p99, but 3.8% of attempts are retryable. So NFR-2 is likely to fail its own acceptance test.
- FND-020: file arrival times make the NFR-8 08:00 SGT report deadline unreachable.
- FND-044: a single HSM in one AZ is a single point of failure for all card traffic.
- FND-043 and FND-045: late approvals can leave duplicate authorization holds, and payout bank accounts can be diverted without step-up checks.
- FND-016: card payments go live before fraud scoring and before the PCI assessment.

Most of these can be fixed by editing the design text (refinement_now), so the core is recoverable. Several real strengths should be kept unchanged: the same-transaction ledger with an outbox (FND-013), integer money handling (FND-040), and the webhook signing and SSRF controls (FND-053). Even so, the number of high findings together with a critical one rules out a conditional fit at this point. Limits of this review:

- It worked from the extracted text only (DEG-001), so figures rendered as images were not seen.
- No external research was possible (DEG-002). The PCI DSS reading in FND-028, the DynamoDB limits in FND-050 and the data-localisation question in FND-039 are therefore unverified.
- One assessment shard was cut off (DEG-003), so some lower-ranked requirement findings may be missing.
- FND-050's recommendation may conflict with the approved idempotency-store decision without declaring a challenge (DEG-004), so it should be read as a validation need, not a mandated change.

The verdict does not depend on any of these unverified items. FND-001, FND-029, FND-005, FND-019 and FND-020 rest only on statements inside the document.

Conditions:
- Key the Redis fast path on (merchant_id, idempotency_key), and check the stored request hash before returning a cached response. Update the FR-5 test to cover a key shared by two merchants, a reused key with a changed body, and concurrent duplicates (owner: Payments Core tech lead). (FND-001, FND-024)
- Remove PAN detokenisation from the Fraud Hook, or bring the Fraud Hook and FRV-1 into CDE scope with a documented PCI attestation. Confirm with the QSA whether keeping the CVC after authorization is permitted, and redesign the cascade and incremental-auth credential handling if it is not (owner: PCI compliance lead). (FND-029, FND-028)
- Decide between restating NFR-4 with a non-zero cross-region RPO plus an in-flight reconciliation procedure, or adopting synchronous replication. Add idempotency data to the durable store so the idempotency state can be rebuilt after failover. Add a cross-AZ and cross-region HSM and Vault topology (owner: platform architect, with risk acceptance by the CTO). (FND-019, FND-044)
- Redo the NFR-2 latency budget with a cascade-aware p99 (timeout and cascade budget below 1,500 ms) or revise NFR-2. Redesign the reconciliation schedule (incremental matching, or a rule for late files) so that NFR-8 is achievable at 2027 volume. (FND-005, FND-020)
- Add a reversal path for late approvals that arrive after the timeout. Require step-up MFA, owner notification and a cooling-off hold for changes to the payout bank account. (FND-043, FND-045)
- Resequence go-live so that the Fraud Hook, hardening tests and the PCI assessment come before the first card cohort, or record an explicit risk acceptance with an owner and exposure limits for fraud fail-open. (FND-016, FND-052)

| Objective | Verdict | Findings |
|---|---|---|
| Replace five per-market stacks with one governed platform | fit with conditions | FND-013, FND-020, FND-023 |
| One versioned merchant API, 15,000 merchants, 2,000 TPS peak | not fit | FND-001, FND-005, FND-050, FND-024, FND-044 |
| P1 | fit with conditions | FND-013, FND-043, FND-023 |
| P2 | not fit | FND-029, FND-028 |
| P3 | not fit | FND-001 |
| P4 | fit | FND-040 |
| P5 | fit | FND-013 |
| P6 | fit | - |
| P7 | fit with conditions | FND-013, FND-053, FND-024 |
| P8 | fit with conditions | FND-052, FND-044 |
| P9 | not fit | FND-045 |
| P10 | fit | - |
| NFR-10 | fit | - |

What would change this verdict: The verdict would move to fit_with_conditions if a revised design text did the following:

- fixes the Redis key scope and hash check (FND-001);
- removes PAN from the Fraud Hook path (FND-029);
- reconciles NFR-2, NFR-4 and NFR-8 with the architecture, by redesign or by restating each requirement with owner sign-off (FND-005, FND-019, FND-020).

Also needed is a QSA or primary-standard confirmation that CVC retention until settlement is permitted. If it is not permitted, the Vault must be redesigned (FND-028). In the other direction, external evidence that the per-key DynamoDB limits or local data-localisation rules are stricter than the design assumes (FND-050, FND-039) would add further blocking issues.

## Strengths

### FND-013 Ledger is written in the same transaction as state changes, with an outbox and append-only enforcement

- **strength** · confidence 0.85 (high) · rank 19
- Disposition: **no change**

Journals, the state transition and the outbox row are committed in one PostgreSQL transaction. Balances are maintained as an asynchronous projection that is checked nightly against the postings, and UPDATE and DELETE are revoked on journal and posting. This directly meets P1, P5, P7 and FR-10, avoids dual-write inconsistency, and avoids hot-row contention at 2,000 TPS.

- Where: p.12 §14.3 (FR-10): "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them, together with an outbox row."
- Where: p.16 §19 (P5): "journal and posting have UPDATE and DELETE revoked from every application role"
- Evidence EV-030 (doc, supports): "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them, together with an outbox row." [doc:DOC-design_v1#p12/s14.3]
- Evidence EV-031 (doc, supports): "No payment-path transaction updates a balance row, which avoids hot-row contention on high-volume accounts" [doc:DOC-design_v1#p12/s14.3]
- Why no change is needed: The design meets FR-10 and principles P1, P5 and P7 with an established pattern and checks the projection against the postings.
- Decision AD-013 (Section 24 - Ledger): preserves. Affirms the same-transaction ledger and outbox decision.
- Decision AD-040 (FR-10): preserves. Meets FR-10's balanced journals.

### FND-040 Money representation and ISO 4217 exponent handling are correct and rigorous

- **strength** · confidence 0.85 (high) · rank 20
- Disposition: **no change**

Section 15 stores amounts as signed 64-bit integer minor units with ISO 4217 codes and takes exponents from a versioned table. The exponents it lists are correct as stated. Adapters convert explicitly where a provider uses a different exponent (IDR) and reject any conversion that would need rounding. This supports P4, FR-10 and the ledger invariants without relying on unchecked assumptions.

- Where: p.12 §15 (FR-10): "the adapter converts explicitly and rejects any amount that would need rounding."
- Evidence EV-089 (doc, supports): "the adapter converts explicitly and rejects any amount that would need rounding." [doc:DOC-design_v1#p12/s15]
- Why no change is needed: Integer minor units, versioned exponent tables and conversions that reject rounding are fit for P4 and FR-10 as written.
- Decision AD-014 (Section 24 - Money representation): preserves. Affirms the integer minor-unit money representation.

### FND-053 Webhook signing, SSRF protection and per-endpoint isolation

- **strength** · confidence 0.85 (high) · rank 21
- Disposition: **no change**

Webhooks use secrets per endpoint, separate from API keys, with timestamped HMAC signatures. The dispatcher pins the validated IP address to block SSRF and DNS rebinding, and caps each endpoint at 20 in-flight deliveries with its own breaker. Together these meet FR-12 securely and stop a failing merchant from degrading others (NFR-9).

- Where: p.13 §17 (FR-12): "refuses private, loopback, link-local and cloud-metadata addresses, and connects to the validated"
- Evidence EV-109 (doc, supports): "refuses private, loopback, link-local and cloud-metadata addresses, and connects to the validated" [doc:DOC-design_v1#p13/s17]
- Why no change is needed: These controls directly address the main webhook threats and noisy-neighbour risk for FR-12 and NFR-9.
- Decision AD-016 (Section 24 - Webhooks): preserves. Affirms the signed, bounded-retry webhook decision.

## Risks

### FND-001 Redis idempotency fast path ignores merchant scope and body hash

- **risk** · security privacy gap · severity **critical** · confidence 0.85 (high) · rank 1
- Disposition: **refinement now** (also: needs testing)

Section 9.2 keys the fast-path response cache only on idem:resp:{idempotency_key} and returns a hit without any further check. This breaks principle P3, which scopes idempotency to the pair (merchant, key). Section 9.1 accepts order and invoice IDs as keys, so two merchants can easily use the same key, and one merchant can then be sent another merchant's stored payment object. Because a hit also skips the request-hash comparison, a reused key with a different body gets the cached response instead of HTTP 422, which breaks FR-5.

- Where: p.8 §9.2 (FR-5): "the final response is written to idem:resp:{idempotency_key} with a 24-hour TTL."
- Where: p.4 §3 (P3): "Idempotency is scoped to (merchant, key). Every mutating call is deduplicated on the pair of merchant identity and client-supplied"
- Where: p.7 §9.1: "merchants frequently use their own order or invoice identifiers, which is accepted."
- Evidence EV-001 (doc, supports): "the final response is written to idem:resp:{idempotency_key} with a 24-hour TTL." [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-002 (doc, supports): "on a hit, it returns the stored response immediately without touching DynamoDB or the Orchestrator." [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-003 (doc, supports): "merchants frequently use their own order or invoice identifiers, which is accepted." [doc:DOC-design_v1#p7/s9.1]
- Evidence EV-032 (inference, supports): "A key that holds no merchant identity, combined with low-entropy merchant-chosen keys and no hash check on a hit, means responses can be served across merchants and the 422 rule is skipped." [inference:EV-032] derived from EV-001, EV-002, EV-003
- Evidence EV-040 (doc, supports): "Idempotency is scoped to (merchant, key). Every mutating call is deduplicated on the pair of merchant identity and client-supplied" [doc:DOC-design_v1#p4/s3]
- Evidence EV-042 (doc, supports): "with a different request body shall be rejected with HTTP 422." [doc:DOC-design_v1#p2/s2.1]
- Evidence EV-071 (inference, supports): "With 15,000 merchants using order numbers as keys, the same key from two merchants is likely within 24 hours; the fast path then returns the first merchant's response to the second, and a same-merchant reused key with a new body gets a replay instead of a 422." [inference:EV-071] derived from EV-038, EV-039, EV-041, EV-042
- Evidence EV-112 (inference, supports): "With 15,000 merchants using sequential order IDs and a key namespace shared across merchants, collisions within 24 hours are near-certain, so one merchant gets another's response and the 422 mismatch rule is bypassed on cache hits." [inference:EV-112] derived from EV-098, EV-099, EV-041
- Recommendation: In Section 9.2 and the Section 24 idempotency row, change the key to idem:resp:{merchant_id}:{idempotency_key}. Store request_hash in the cached value and compare it on every hit, falling through to the DynamoDB path when it differs. Extend the FR-5 test in Section 26 with a cross-merchant collision case and a concurrent-duplicate case.
  - Issue: The fast-path cache key leaves out the merchant and the hit path skips the request-hash check.
  - Rationale: P3 and FR-5 require deduplication on (merchant, key) and a 422 when a key is reused with a different body.
  - Expected benefit: Stops cross-merchant data leakage and enforces FR-5 on every path. (objectives: FR-5, P3, NFR-7)
  - Supporting evidence: EV-001, EV-002, EV-003, EV-032
  - Verification: Test: two merchants send the same Idempotency-Key and each gets its own payment; a modified body on a cached key returns 422.
- Decision AD-005 (Section 24 - Idempotency store): challenges. The recommendation changes the approved Redis key format idem:resp:{key} to include merchant_id, backed by multiple doc items showing it violates P3 and FR-5.
- Decision AD-036 (FR-5): preserves. The fix restores FR-5's (merchant, key) dedup and 422 rule on the fast path.
- Decision AD-030 (Section 3): preserves. Principle P3 overrides the conflicting Section 9.2 key format.
- Decision AD-006 (Section 24 - Idempotency retention): preserves. The 24-hour retention is unchanged.

### FND-029 Fraud Hook detokenises PAN but is declared out of CDE scope

- **risk** · unsupported or incorrect claim · severity **high** · confidence 0.85 (high) · rank 2
- Disposition: **refinement now** (also: governance decision)

Section 13.1 has the Fraud Hook detokenise the PAN, using the Card Adapter's service role, and send it to FRV-1. Section 12.2 classes the Fraud Hook as out of scope with 'Token, BIN, last 4 only', and Section 12.1 limits detokenise to the Card Adapter. The CDE scoping claim behind NFR-5 is therefore wrong as written, and principle P2 is broken. PAN would also go to a vendor whose DPA and SLA are still pending (Backlog item 4), and whose PCI status the design does not establish.

- Where: p.11 §13.1 (FR-9): "The Fraud Hook obtains the PAN through the Vault's detokenise operation, using the Card Adapter client library and service role."
- Where: p.10 §12.2 (NFR-5): "Fraud Hook Out of scope Token, BIN, last 4 only"
- Where: p.10 §12.1: "Only the Card Adapter's service identity may call detokenise."
- Evidence EV-004 (doc, supports): "The Fraud Hook obtains the PAN through the Vault's detokenise operation, using the Card Adapter client library and service role." [doc:DOC-design_v1#p11/s13.1]
- Evidence EV-005 (doc, supports): "Fraud Hook Out of scope Token, BIN, last 4 only" [doc:DOC-design_v1#p10/s12.2]
- Evidence EV-081 (doc, supports): "FRV-1 contract - data processing agreement and SLA finalisation." [doc:DOC-design_v1#p19/s25]
- Evidence EV-006 (doc, supports): "Only the Card Adapter's service identity may call detokenise." [doc:DOC-design_v1#p10/s12.1]
- Evidence EV-111 (inference, supports): "A service that receives plaintext PAN and transmits it externally is part of the CDE, so the Section 12.2 scoping that NFR-5 assessment relies on is incorrect as written." [inference:EV-111] derived from EV-097, EV-006, EV-005
- Recommendation: Pick one option. (a) Send FRV-1 the HSM-keyed PAN fingerprint (12.1) or a vendor-specific keyed hash instead of the PAN. (b) Move the PAN call into the CDE: the Card Adapter or a CDE-resident fraud proxy calls FRV-1 directly, with its own service identity. Then update 12.2 and 13.1, and add FRV-1's PCI attestation as a condition of Backlog item 4.
  - Issue: The PAN flows to the Fraud Hook and FRV-1, which contradicts the declared CDE boundary and P2.
  - Rationale: A component that handles PAN is in CDE scope. Sharing a service role also defeats least privilege (P9).
  - Expected benefit: Keeps the CDE accurate for NFR-5 and preserves P2 and P9. (objectives: NFR-5, FR-9)
  - Supporting evidence: EV-004, EV-005, EV-081
  - Verification: Data-flow review and a segmentation test show no PAN outside the components listed in 12.2. QSA confirms the scope.
- Next step: Payments Core architect with the PCI compliance lead: Decide how PAN reaches FRV-1 (fingerprint or CDE proxy) and update 12.2 and 13.1.
- Decision AD-027 (NFR-5): preserves. The fix keeps the CDE limited to the Section 12.2 components, as NFR-5 requires.
- Decision AD-022 (Section 25 item 4): refines. Makes FRV-1's PCI attestation and the DPA a condition of Backlog item 4.
- Decision AD-012 (Section 24 - Fraud): preserves. Synchronous FRV-1 scoring with a 150 ms timeout is unchanged; only the payload changes.
- Decision AD-001 (Section 24 - Compute): preserves. The separate CDE cluster stays; at most a CDE-resident proxy is added.

### FND-028 CVC retention until settlement rests on a doubtful reading of PCI DSS

- **risk** · unsupported or incorrect claim · severity **high** · confidence 0.75 (medium) · rank 3
- Disposition: **needs investigation** (also: governance decision, refinement now)

Section 12.4 and NFR-6 keep the CVC encrypted after authorization, until settlement or for up to 72 hours, so it can be re-presented in cascades and incremental authorizations. The document says PCI DSS v4.0 Req. 3.2.1 and 3.3.2 allow sensitive authentication data to be kept 'until the transaction is settled'. The reviewer's reading of those clauses is that they allow pre-authorization storage only, and that keeping SAD after authorization is not allowed, even encrypted. If that reading is correct, NFR-6, the confirmed CVC decision and the NFR-5 Level 1 assessment cannot all hold, and the Vault design would put the RoC at risk. This needs checking against the standard text and with the QSA before the Vault is built.

- Where: p.10 §12.4 (NFR-6): "This is permitted by PCI DSS v4.0 Requirements 3.2.1 and 3.3.2, which allow sensitive authentication data to be retained in encrypted form until the transaction is settled."
- Where: p.3 §2.2 (NFR-6): "stored only in encrypted form, in the Vault, and deleted at settlement of the associated payment."
- Where: p.10 §12.4: "for each re-presentation of the credential during a cascade and for incremental authorizations (ride-hailing tips, hotel extensions)."
- Evidence EV-007 (doc, supports): "This is permitted by PCI DSS v4.0 Requirements 3.2.1 and 3.3.2, which allow sensitive authentication data to be retained in encrypted form until the transaction is settled." [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-080 (doc, supports): "for each re-presentation of the credential during a cascade and for incremental authorizations (ride-hailing tips, hotel extensions)." [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-090 (inference, supports): "Incremental authorizations happen after the initial authorization has completed, so meeting them means keeping the CVC after authorization. The cited clauses would have to allow that explicitly, and no source in this review confirms that they do." [inference:EV-090] derived from EV-007, EV-080
- Evidence EV-008 (doc, supports): "the Card Adapter retrieves from the Vault (including the card verification code; see Section 12.4) so that the second acquirer receives the same data as the first." [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-116 (inference, supports): "Storage for incremental authorizations necessarily extends past completion of the initial authorization, which is the point at which the reviewer expects PCI DSS to require deletion; this is unverified here." [inference:EV-116] derived from EV-104, EV-105
- Recommendation: Get a written interpretation from the QSA. If post-authorization retention is not allowed, change 12.4 and NFR-6 so the CVC is deleted when the first authorization attempt completes or the cascade window ends. Use stored-credential or incremental-authorization indicators without CVC. Update the confirmed 'CVC handling' decision and the NFR-6 acceptance criterion to match.
  - Issue: The CVC retention policy relies on an unverified interpretation of PCI DSS v4.0 Req. 3.2.1 and 3.3.2.
  - Rationale: Storing SAD in a way the standard does not allow would fail the PCI DSS assessment that NFR-5 requires.
  - Expected benefit: Protects NFR-5 (PCI DSS Level 1) and makes NFR-6 lawful and testable. (objectives: NFR-5, NFR-6, FR-7)
  - Supporting evidence: EV-007, EV-080, EV-090
  - Verification: QSA sign-off on the SAD lifecycle. Vault SAD test shows the CVC is absent once authorization completes.
- Next step: PCI compliance lead with the QSA: Get a written ruling on SAD retention between authorization and settlement before the Phase 2 Vault build starts.
- Decision AD-008 (Section 24 - CVC handling): refines. The CVC retention window may need narrowing, but RQ-007 is unanswered, so there is no evidence strong enough to challenge it.
- Decision AD-028 (NFR-6): refines. NFR-6's 'deleted at settlement' rests on the same unverified reading.
- Decision AD-027 (NFR-5): preserves. The investigation protects the Level 1 assessment.

### FND-019 Zero RPO on region loss conflicts with asynchronous Aurora replication; idempotency rebuild has no source data

- **risk** · internal contradiction · severity **high** · confidence 0.80 (high) · rank 4
- Disposition: **governance decision** (also: refinement now)

NFR-4 requires zero RPO for authorised payments and ledger postings even if a whole region is lost. Section 20.2 replicates asynchronously with typical lag under one second, so commits inside that lag window are lost. The NFR-4 game-day criterion checks only that postings committed before the failure survive, which cannot show RPO zero unless writes in flight at the cut are reconciled. Section 20.2 also rebuilds idempotency state from the payment table, but the Section 19 payment table has no idempotency_key or request_hash, so FR-5 would not hold after failover.

- Where: p.3 §2.2 (NFR-4): "Recovery point objective for authorized payments and ledger postings shall be zero, including on loss of an entire AWS region."
- Where: p.16 §20.2 (NFR-4): "Replication is storagelevel and asynchronous, with typical lag under one second."
- Where: p.17 §20.2 (FR-5): "empty in ap-southeast-3 from infrastructure-as-code, and in-flight idempotency state is reconstructed from the"
- Evidence EV-009 (doc, supports): "Recovery point objective for authorized payments and ledger postings shall be zero, including on loss of an entire AWS region." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-010 (doc, supports): "Replication is storagelevel and asynchronous, with typical lag under one second." [doc:DOC-design_v1#p16/s20.2]
- Evidence EV-053 (doc, supports): "empty in ap-southeast-3 from infrastructure-as-code, and in-flight idempotency state is reconstructed from the" [doc:DOC-design_v1#p17/s20.2]
- Evidence EV-075 (inference, supports): "At 2,000 TPS, up to about one second of lag means up to roughly 2,000 committed payments (and their postings) may be missing in ap-southeast-3; the Section 19 payment table has no idempotency_key or request_hash column to rebuild idempotency records from." [inference:EV-075] derived from EV-009, EV-010, EV-053
- Evidence EV-011 (doc, supports): "in-flight idempotency state is reconstructed from the payment table." [doc:DOC-design_v1#p17/s20.2]
- Evidence EV-033 (inference, supports): "Asynchronous replication with non-zero lag gives a non-zero RPO when the region is lost, and the payment table has no idempotency key from which to rebuild state." [inference:EV-033] derived from EV-009, EV-010, EV-011
- Evidence EV-115 (inference, supports): "At 2,000 TPS, about 1 s of asynchronous lag means up to roughly 2,000 committed payments can be lost on regional failure, and their idempotency keys then look unused in the DR region." [inference:EV-115] derived from EV-009, EV-010
- Recommendation: Decide between relaxing NFR-4 to a bounded RPO (for example, seconds of lag plus a post-failover reconciliation of acquirer authorisations against the payment record) and adding synchronous cross-region durability for authorisation commits. Add idempotency_key and request_hash to the payment table (or replicate the DynamoDB table). Revise the NFR-4 criterion to measure data loss under load at the moment of failure.
  - Issue: NFR-4's RPO cannot hold with asynchronous replication, its acceptance test cannot show it, and the idempotency rebuild has no source data.
  - Rationale: Either the requirement or the mechanism has to change. Leaving both as they are hides a real data-loss window for authorised payments.
  - Expected benefit: An honest, verifiable NFR-4 and preserved FR-5 behaviour across failover. (objectives: NFR-4, FR-5, P1)
  - Supporting evidence: EV-009, EV-010, EV-053, EV-075
  - Verification: A DR game day under NFR-1 load compares acquirer-side authorisations with recovered payment records and shows the agreed RPO.
- Next step: Head of Platform Engineering with Finance controller: Decide the RPO target and mechanism for region loss, then update NFR-4, Sections 19 and 20.2 and the NFR-4 test.
- Decision AD-048 (NFR-4): challenges. The doc's own statements that replication is asynchronous (EV-010) and that RPO must be zero (EV-009) show the zero-RPO target cannot hold as designed.
- Decision AD-003 (Section 24 - Disaster recovery): refines. Aurora Global DR stays, with either a bounded RPO plus post-failover reconciliation or an added synchronous commit.
- Decision AD-005 (Section 24 - Idempotency store): refines. The idempotency rebuild needs idempotency_key and request_hash persisted, or the DynamoDB table replicated.
- Decision AD-036 (FR-5): preserves. Aims to keep FR-5 after failover.

### FND-044 A single CloudHSM in one AZ is a single point of failure for all card traffic, and has no regional DR

- **risk** · scalability or failure mode · severity **high** · confidence 0.82 (high) · rank 5
- Disposition: **refinement now** (also: needs prototyping)

All KEKs sit in one HSM in ap-southeast-1a, and every detokenise unwraps a DEK in the HSM with no caching. Losing that AZ or that HSM stops all card tokenisation and authorization until a new HSM is restored from a daily backup. Card traffic is 55% of attempts. The trigger for adding a second HSM (1,500 card TPS) is never reached, because peak card volume is about 1,100 TPS. Section 20.2 also gives no cross-region plan for the Vault store or the HSM, so after a regional failover cards cannot be processed. This puts NFR-3 and NFR-4 at risk.

- Where: p.10 §12.3 (NFR-3): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a."
- Where: p.10 §12.3 (NFR-3): "cluster when sustained card volume exceeds 1,500 TPS. If the HSM is unreachable"
- Where: p.16 §20.2 (NFR-4): "MSK, DynamoDB and ElastiCache are not replicated cross-region; on regional failover they are recreated"
- Evidence EV-015 (doc, supports): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a." [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-101 (doc, supports): "cluster when sustained card volume exceeds 1,500 TPS. If the HSM is unreachable" [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-102 (doc, supports): "DEKs are not cached, so plaintext key material never persists in application memory." [doc:DOC-design_v1#p10/s12.1]
- Evidence EV-114 (inference, supports): "55% card share of 2,000 TPS is 1,100 TPS, below the 1,500 TPS trigger, so the design runs on one HSM in one AZ indefinitely, and a 503 classed as retryable only multiplies vault calls during the outage." [inference:EV-114] derived from EV-015, EV-101
- Evidence EV-035 (inference, supports): "55% of a 2,000 TPS peak is about 1,100 card TPS, below the 1,500 TPS trigger, so the single HSM stays in place for the whole design horizon." [inference:EV-035] derived from EV-016, EV-017
- Evidence EV-058 (doc, supports): "Monthly availability of the merchant payment API shall be at least 99.95%." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-077 (inference, supports): "Card share 55% x 2,000 peak TPS = 1,100 card TPS, below the 1,500 TPS trigger, so the single HSM persists through the design horizon; any HSM or AZ outage longer than ~22 minutes exhausts the monthly NFR-3 budget for card payments." [inference:EV-077] derived from EV-056, EV-057, EV-058
- Evidence EV-096 (inference, supports): "If ap-southeast-1a fails, or the region fails, no KEK is available until an HSM is restored from backup, so every card payment fails with 503. The DR runbook does not cover the CDE at all." [inference:EV-096] derived from EV-015, EV-085
- Recommendation: In 12.3 and Section 24, launch with at least two HSMs in different AZs and a cross-region HSM/KEK plan. Add the Vault data store to the replication plan in 20.2. Have HSM 503 errors fail fast as non-cascadable. Size HSM throughput for detokenise plus tokenise at 2,000 TPS including cascades, and set the scale trigger by measured HSM utilisation rather than card TPS.
  - Issue: The HSM has no AZ or regional redundancy, and the scaling trigger is unreachable.
  - Rationale: The whole card path depends on synchronous HSM unwraps, so the HSM's availability caps NFR-3 for cards.
  - Expected benefit: Card acceptance survives the loss of an AZ (NFR-3), and cards can be served after regional failover (NFR-4). (objectives: NFR-3, NFR-4, NFR-1)
  - Supporting evidence: EV-015, EV-101, EV-102, EV-114
  - Verification: In a chaos test, kill the HSM in AZ-a under NFR-1 load; card authorizations should continue. A DR game day should then show card authorization succeeding in ap-southeast-3.
- Next step: Vault tech lead: Benchmark HSM unwrap throughput at 2,500 TPS and document the multi-AZ and cross-region HSM topology.
- Decision AD-007 (Section 24 - Vault): challenges. Several doc items (EV-015, EV-016, EV-017, EV-058) show the 'one HSM at launch' decision cannot meet NFR-3, and its scale trigger is never reached at design load.
- Decision AD-003 (Section 24 - Disaster recovery): refines. Regional DR has to cover the HSM and Vault store as well as Aurora.
- Decision AD-047 (NFR-3): preserves. The change aims to meet the 99.95% availability target.

### FND-016 First cohort goes live before the Fraud Hook and before hardening and PCI assessment

- **risk** · internal contradiction · severity **high** · confidence 0.80 (high) · rank 6
- Disposition: **governance decision** (also: refinement now)

Section 28 puts the first merchant cohort (Singapore cards and PayNow) live after Phase 7. The Fraud Hook is Phase 8, and load testing, DR game days, the PCI DSS assessment and the Section 26 test plan are Phase 9. Card payments would therefore go live unscored (FR-9 says every card payment shall be scored) and without the PCI DSS assessment NFR-5 requires or the NFR-1 to NFR-4 tests. Section 27 says only Admin API schemas and disputes are deferred for the first cohort, which hides this sequencing.

- Where: p.21 §28 (FR-9, NFR-5): "The first merchant cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week"
- Where: p.21 §28 (NFR-5): "9 Hardening - load, chaos and DR game days; PCI DSS assessment; Section 26 test plan Follows Section 26"
- Where: p.3 §2.1 (FR-9): "Every card payment and every e-wallet payment above the merchant's configured threshold shall be scored by the fraud-scoring hook"
- Evidence EV-045 (doc, supports): "The first merchant cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week" [doc:DOC-design_v1#p21/s28]
- Evidence EV-046 (doc, supports): "8 Fraud Hook (FRV-1) Yes - vendor contract (Backlog item 4)" [doc:DOC-design_v1#p21/s28]
- Evidence EV-047 (doc, supports): "9 Hardening - load, chaos and DR game days; PCI DSS assessment; Section 26 test plan Follows Section 26" [doc:DOC-design_v1#p21/s28]
- Evidence EV-072 (inference, supports): "Go-live after Phase 7 comes before Phase 8 (fraud scoring) and Phase 9 (PCI assessment and acceptance tests), so FR-9 and NFR-5 are unmet, and NFR-1 to NFR-4 unproven, for the first cohort." [inference:EV-072] derived from EV-045, EV-046, EV-047
- Recommendation: In Section 28, make first-cohort go-live depend on Phase 8 and on the Phase 9 items needed for the Singapore cohort (PCI assessment, NFR-1 to NFR-4 tests). Alternatively, record an explicit risk acceptance for an interim fraud fallback with a named owner and update Section 27's conclusion to match.
  - Issue: The phase plan contradicts FR-9, NFR-5 and the Section 26 acceptance gate for the first live cohort.
  - Rationale: Card processing for real merchants should not start before the controls and tests that the document's own requirements make mandatory.
  - Expected benefit: FR-9 and NFR-5 are met at first go-live, and go-live rests on accepted tests. (objectives: FR-9, NFR-5, NFR-1, NFR-4)
  - Supporting evidence: EV-045, EV-046, EV-047, EV-072
  - Verification: A go-live checklist in Section 28 references the FR-9 and NFR-5 acceptance results from Section 26.
- Next step: Programme director with Head of Risk: Re-sequence Phases 7 to 9 for the first cohort, or sign a time-boxed risk acceptance.
- Decision AD-034 (Section 28): challenges. Doc items EV-045, EV-046 and EV-047 show that go-live after Phase 7 precedes fraud scoring and the PCI assessment, so the sequencing has to change or be formally risk-accepted.
- Decision AD-039 (FR-9): preserves. The recommendation is meant to ensure FR-9 is met at launch.
- Decision AD-027 (NFR-5): preserves. Requires the PCI assessment before live card processing.
- Decision AD-022 (Section 25 item 4): refines. The FRV-1 contract becomes a go-live dependency with a deadline.

### FND-043 Late approvals after the 2,500 ms timeout are discarded, risking double authorizations

- **risk** · scalability or failure mode · severity **high** · confidence 0.82 (high) · rank 7
- Disposition: **refinement now** (also: needs testing)

A no-response timeout is classed as retryable and triggers a cascade, and any response that arrives after the timeout is logged and discarded. An approval that arrives late at acquirer A, after B has also approved, leaves a live authorization hold on the cardholder at A. Nothing reverses it, and reconciliation will not see it until settlement, if at all. The claim that cascading cannot create a duplicate charge looks only at the ledger, not at what the cardholder sees. P1 and FR-5's 'at most one authorization' intent are not met.

- Where: p.9 §11.2 (FR-7): "arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded."
- Where: p.9 §11.2 (FR-7): "cascading cannot create a duplicate charge: the ledger records only the approved attempt."
- Where: p.9 §11.1 (FR-7): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms"
- Evidence EV-048 (doc, supports): "arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded." [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-100 (doc, supports): "cascading cannot create a duplicate charge: the ledger records only the approved attempt." [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-113 (inference, supports): "A timed-out attempt can still be approved at the issuer, and discarding that approval while cascading leaves two holds on the card, of which only one is recorded." [inference:EV-113] derived from EV-048, EV-100
- Evidence EV-073 (inference, supports): "A timeout means the outcome is unknown, not unsuccessful; discarding a late approval while cascading can leave two live authorisations for one payment, and the ledger-only view does not release the customer's hold at the first acquirer." [inference:EV-073] derived from EV-048, EV-049
- Evidence EV-093 (inference, supports): "A late approval that is discarded leaves funds held on the cardholder's account at the first acquirer, while the second acquirer's approval is captured, so the customer sees a duplicate hold or charge." [inference:EV-093] derived from EV-083
- Recommendation: In 11.2, on a timeout send a reversal for the attempt before cascading, or cascade and queue a reversal. Record late responses in attempt state rather than discarding them, and have a late approval on a non-winning attempt trigger an automatic void. Correct the duplicate-charge sentence.
  - Issue: There is no reversal or void path for timed-out or late-approved attempts.
  - Rationale: Ambiguous outcomes have to be resolved, not discarded, to avoid duplicate holds and customer complaints.
  - Expected benefit: Ensures at most one live authorization per payment (FR-5/FR-7) and keeps attempt records truthful (P1). (objectives: FR-5, FR-7, P1)
  - Supporting evidence: EV-048, EV-100, EV-113
  - Verification: Add a case to the FR-7 cascade simulation in which the simulator approves after 3 s. Expect a reversal sent to that acquirer and exactly one live authorization.
- Decision AD-010 (Section 24 - Cascade policy): refines. Adds a reversal step to the timeout cascade trigger without removing it.
- Decision AD-037 (FR-7): preserves. Cascading on retryable outcomes is kept.
- Decision AD-036 (FR-5): preserves. Supports at most one live authorization per payment.

### FND-005 Latency budget assumes cascades fall outside p99, but 3.8% of attempts are retryable

- **risk** · internal contradiction · severity **high** · confidence 0.85 (high) · rank 9
- Disposition: **refinement now** (also: needs prototyping)

Section 21.1 claims cascades do not affect p99 because fewer than 1% of card payments cascade. Section 10.5 reports 3.8% retryable outcomes, and the NFR-2 test injects 3.8%. With 3.8% of payments cascading, cascade latency falls inside the p99 tail. A timeout-triggered cascade alone takes 2,500 ms before the next attempt starts, which is above the 1,500 ms NFR-2 limit. As designed, NFR-2 is very likely to fail its own acceptance test.

- Where: p.17 §21.1 (NFR-2): "Cascading does not move the p99 because fewer than 1% of card payments cascade"
- Where: p.9 §10.5: "retryable outcomes - soft declines eligible for reattempt plus acquirer-side errors and timeouts - 3.8%."
- Where: p.20 §26.2 (NFR-2): "Under the NFR-1 load with 3.8% retryable-outcome injection, p99 end-to-end card authorization ≤ 1,500"
- Evidence EV-012 (doc, supports): "Cascading does not move the p99 because fewer than 1% of card payments cascade" [doc:DOC-design_v1#p17/s21.1]
- Evidence EV-013 (doc, supports): "retryable outcomes - soft declines eligible for reattempt plus acquirer-side errors and timeouts - 3.8%." [doc:DOC-design_v1#p9/s10.5]
- Evidence EV-014 (doc, supports): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms" [doc:DOC-design_v1#p9/s11.1]
- Evidence EV-034 (inference, supports): "With 3.8% of payments cascading, more than 1% of payments carry at least two acquirer round trips, and any timeout cascade exceeds 2,500 ms, so the p99 sits above 1,500 ms." [inference:EV-034] derived from EV-012, EV-013, EV-014
- Evidence EV-052 (doc, supports): "Under the NFR-1 load with 3.8% retryable-outcome injection, p99 end-to-end card authorization ≤ 1,500" [doc:DOC-design_v1#p20/s26.2]
- Evidence EV-074 (inference, supports): "About 3.8% of card payments cascade, well above 1%, so cascades fall inside the slowest 1%; any timeout-triggered cascade exceeds 2,500 ms, and two sequential ~1,100 ms acquirer round trips plus overhead exceed 1,500 ms." [inference:EV-074] derived from EV-050, EV-051, EV-052
- Evidence EV-092 (inference, supports): "About 3.8% of card payments take a cascade path, which is well inside the slowest 1%. One 2,500 ms timeout plus a second acquirer round trip gives more than 3,600 ms, so the p99 will include cascade latency and exceed 1,500 ms." [inference:EV-092] derived from EV-082, EV-013
- Recommendation: In Sections 11 and 21.1, add an overall deadline per payment (for example 1,400 ms) that stops any further cascade. Set the per-attempt timeout from that remaining budget rather than a fixed 2,500 ms. Re-derive the p99 budget with the cascade path included, or have the owner restate NFR-2 to exclude cascades.
  - Issue: The cascade latency and the 2,500 ms attempt timeout are incompatible with NFR-2.
  - Rationale: NFR-2 explicitly includes any cascade in the p99.
  - Expected benefit: Makes NFR-2 achievable and gives a correct latency budget. (objectives: NFR-2, FR-7)
  - Supporting evidence: EV-012, EV-013, EV-014, EV-034
  - Verification: Run the NFR-2 benchmark with 3.8% retryable injection, including timeout outcomes.
- Next step: Payments Core tech lead: Model the cascade latency distribution from the 2025 pilot data and set the deadline budget.
- Decision AD-010 (Section 24 - Cascade policy): challenges. Doc items EV-012, EV-013, EV-014 and EV-052 show that the fixed 2,500 ms timeout trigger cannot coexist with a 1,500 ms p99 that includes cascades.
- Decision AD-046 (NFR-2): refines. NFR-2 is either met through a deadline budget or restated by its owner.

### FND-020 Reconciliation timeline cannot meet the NFR-8 08:00 SGT report deadline

- **risk** · internal contradiction · severity **high** · confidence 0.80 (high) · rank 10
- Disposition: **refinement now** (also: needs testing)

The matcher starts only once all files for day T have arrived. ACQ-TH1 delivers at 06:30 ICT, which is 07:30 SGT. The measured run is 45 minutes of matching plus 15 minutes of report generation at 2025 volume, so reports land around 08:30 SGT even before 2027 volume roughly doubles the load. NFR-8 (reports by 08:00 SGT on T+1) therefore fails by construction. The NFR-8 acceptance test, a production-volume replay, does not model file arrival times or 2027 volume, and there is no stated path for a late or missing file.

- Where: p.13 §16.2 (NFR-8): "matcher starts once all expected files for business day T have been received, so that cross-provider netting and multi"
- Where: p.12 §16.1 (NFR-8): "ACQ-TH1 CSV over SFTP Daily 06:30 ICT ACQ-PH1"
- Where: p.3 §2.2 (NFR-8): "At least 99.9% of settlement lines shall be auto-matched; merchant settlement reports for business day T shall be published by"
- Evidence EV-054 (doc, supports): "matcher starts once all expected files for business day T have been received, so that cross-provider netting and multi" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-019 (doc, supports): "ACQ-TH1 CSV over SFTP Daily 06:30 ICT" [doc:DOC-design_v1#p12/s16.1]
- Evidence EV-055 (doc, supports): "the matcher's measured end-to-end run time is 45 minutes, and merchant settlement report generation takes a further" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-076 (inference, supports): "06:30 ICT (UTC+7) is 07:30 SGT (UTC+8); 07:30 + 45 min + 15 min = 08:30 SGT at 2025 volume, and roughly 09:30 SGT if run time scales linearly to the 10.5 M/day 2027 target." [inference:EV-076] derived from EV-054, EV-019, EV-055
- Evidence EV-020 (doc, supports): "The batch matcher starts once all expected files for business day T have been received" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-018 (doc, supports): "the matcher's measured end-to-end run time is 45 minutes, and merchant settlement report generation takes a further 15 minutes." [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-118 (inference, supports): "06:30 ICT is 07:30 SGT; 07:30 + 45 min + 15 min = 08:30 SGT > 08:00 SGT at 2025 volume, before the roughly 2× 2027 growth." [inference:EV-118] derived from EV-019, EV-055
- Recommendation: In Section 16.2, match each provider file as it arrives and keep only cross-provider netting and payout computation as a final step. Alternatively, renegotiate ACQ-TH1 delivery or move the NFR-8 deadline. Define a cut-off and partial-report behaviour for missing files. Revise the NFR-8 test to replay 2027 volume using real arrival times.
  - Issue: The batch start rule, file delivery times and run time together miss NFR-8 every day.
  - Rationale: The arithmetic follows directly from the document's own figures.
  - Expected benefit: NFR-8 can be met, and late files have a defined path. (objectives: NFR-8, FR-11, FR-17)
  - Supporting evidence: EV-054, EV-019, EV-055, EV-076
  - Verification: NFR-8 test with time-shifted file arrivals at 2027 volume publishes reports before 08:00 SGT.
- Next step: Reconciliation service lead with Finance Operations: Choose incremental matching or a revised deadline, and add a late-file policy.
- Decision AD-015 (Section 24 - Reconciliation): challenges. Doc items EV-019, EV-054 and EV-055 show that the 'start after all files received' batch cannot meet NFR-8, so the start rule needs to become per-file matching.
- Decision AD-049 (NFR-8): preserves. The change aims to meet the 08:00 SGT deadline.
- Decision AD-026 (Section 27 - Reconciliation): refines. A late-file policy also covers the parsers still pending for ACQ-PH1 and WAG-1.

### FND-023 State machine cannot represent flows that other sections require

- **risk** · internal contradiction · severity **medium** · confidence 0.75 (medium) · rank 12
- Disposition: **refinement now**

Section 7.2 has no PARTIALLY_REFUNDED to SETTLED and no REFUNDED to SETTLED transition. A payment refunded before its settlement line arrives therefore cannot move to SETTLED as Section 16.2 requires, and the SETTLED-driven CVC deletion and FR-2 conflict with reconciliation. Several other flows also have no permitted transition: REQUIRES_ACTION to FAILED (a wallet or 3DS decline notification), repeat partial captures from CAPTURED (FR-1), and the 'authorize-and-hold-capture' REVIEW outcome. FR-2 forbids every transition outside Section 7.2.

- Where: p.6 §7.2 (FR-2): "CAPTURED -> SETTLED | PARTIALLY_REFUNDED | REFUNDED SUCCEEDED"
- Where: p.13 §16.2 (FR-11): "Matched payments transition to SETTLED and a settlement journal is posted. Unmatched and mismatched lines"
- Where: p.7 §8 (FR-9): "REVIEW -> per merchant config: authorize-and-hold-capture, or FAILED"
- Evidence EV-059 (doc, supports): "CAPTURED -> SETTLED | PARTIALLY_REFUNDED | REFUNDED" [doc:DOC-design_v1#p6/s7.2]
- Evidence EV-060 (doc, supports): "Matched payments transition to SETTLED and a settlement journal is posted. Unmatched and mismatched lines" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-061 (doc, supports): "REQUIRES_ACTION -> AUTHORISING | CANCELLED (expiry)" [doc:DOC-design_v1#p6/s7.2]
- Evidence EV-078 (inference, supports): "A same-day partial refund moves CAPTURED to PARTIALLY_REFUNDED, after which no permitted transition reaches SETTLED, so the matched line cannot be applied without breaking FR-2." [inference:EV-078] derived from EV-059, EV-060
- Evidence EV-037 (inference, supports): "Section 7.2 lists no transition from PARTIALLY_REFUNDED or REFUNDED to SETTLED, so a refund before settlement prevents the reconciliation transition." [inference:EV-037] derived from EV-027
- Recommendation: In Section 7, track settlement status (and refunded_minor) as separate attributes, not lifecycle states, or add the missing transitions. Add REQUIRES_ACTION -> FAILED, define CAPTURED -> CAPTURED for further partial captures, and specify the state for 'authorize-and-hold-capture'. Extend the FR-2 property test with refund-before-settlement sequences.
  - Issue: Refund and settlement are modelled as one exclusive state dimension, and several flows have no transition.
  - Rationale: Settlement and refund status are independent of each other, and FR-2 makes any missing transition a hard failure.
  - Expected benefit: FR-1, FR-2 and FR-11 become jointly satisfiable. (objectives: FR-1, FR-2, FR-11)
  - Supporting evidence: EV-059, EV-060, EV-061, EV-078
  - Verification: FR-2 property test includes refund-before-settlement, wallet decline and multi-capture sequences with no rejected transitions.
- Decision AD-035 (FR-2): refines. Adds the missing transitions, or separates settlement status, so that FR-2 can hold alongside FR-11.

## Gaps

### FND-045 Payout bank-account changes lack step-up authentication, owner notification and a hold

- **gap** · security privacy gap · severity **high** · confidence 0.82 (high) · rank 8
- Disposition: **refinement now** (also: governance decision)

A Finance or Owner user can change the payout bank account, and the change takes effect at the next cycle. The only confirmation goes to the user who made the change. MFA is optional for Finance, and Finance can also issue refunds. A single phished Finance password is therefore enough to divert a merchant's entire payout, with no out-of-band alert to the merchant. This is a direct financial-loss path and undermines P9 separation of duties.

- Where: p.14 §18.4 (FR-13, FR-17): "A confirmation email is sent to the user who made the change, and the change is written to the audit log."
- Where: p.14 §18.3: "TOTP multi-factor authentication is available to every user and is enforced for the Owner role at first login."
- Where: p.14 §18.2 (FR-13): "Finance Issue refunds; view and export reports; edit payout bank account"
- Evidence EV-021 (doc, supports): "A confirmation email is sent to the user who made the change, and the change is written to the audit log." [doc:DOC-design_v1#p14/s18.4]
- Evidence EV-103 (doc, supports): "TOTP multi-factor authentication is available to every user and is enforced for the Owner role at first login." [doc:DOC-design_v1#p14/s18.3]
- Evidence EV-022 (doc, supports): "Finance Issue refunds; view and export reports; edit payout bank account" [doc:DOC-design_v1#p14/s18.2]
- Recommendation: In 18.3 and 18.4, require MFA for the Owner, Admin and Finance roles, plus step-up re-authentication on payout account change. Notify all Owners and the registered contact out of band. Hold the new account until it is verified (populate verified_at with a penny-drop or name check), with a 48–72 h cooling-off period, and require a second user's approval.
  - Issue: A single factor is enough to redirect money, and the merchant receives no independent notice.
  - Rationale: Changing the payout account is the most valuable account-takeover target on the platform.
  - Expected benefit: Prevents payout diversion (FR-17) and enforces P9. (objectives: FR-17, FR-13, P9)
  - Supporting evidence: EV-021, EV-103, EV-022
  - Verification: Add cases to the FR-13 role-matrix test: a change without step-up is rejected, an unverified account receives no payout, and the Owners are notified.
- Next step: Merchant platform product owner with Risk: Approve the payout-change policy (MFA scope, cooling-off period, dual approval) and update Section 24's MFA decision.
- Decision AD-017 (Section 24 - Merchant user MFA): challenges. Doc items EV-021, EV-022 and EV-103 show that optional MFA for Finance leaves payout redirection protected by a single factor, so mandatory MFA for that role is needed.
- Decision AD-018 (Section 24 - Back-office access): preserves. Back-office dual approval is the pattern being extended to merchant payout changes.

### FND-025 Scheme reattempt limits are referenced but never specified

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.70 (medium) · rank 15
- Disposition: **needs investigation** (also: refinement now)

FR-7, Section 11.3 and the FR-7 acceptance test all depend on 'scheme limits applicable to the card', but no section lists those limits per scheme, response category or window. Even so, Section 27 marks the Retry Engine 'Ready' with 'scheme rules specified'. Without the limits, the FR-7 criterion has no expected values to test against, and over-retrying can bring scheme penalties.

- Where: p.9 §11.3 (FR-7): "window and stops reattempting at the scheme limits applicable to the card."
- Where: p.20 §27 (FR-7): "Retry Engine Ready Outcome classes, cascade limits and scheme rules specified (Section 11)."
- Where: p.19 §26.1 (FR-7): "outcomes, never exceed two additional attempts, and stop at scheme reattempt limits."
- Evidence EV-065 (doc, supports): "window and stops reattempting at the scheme limits applicable to the card." [doc:DOC-design_v1#p9/s11.3]
- Evidence EV-066 (doc, supports): "Retry Engine Ready Outcome classes, cascade limits and scheme rules specified (Section 11)." [doc:DOC-design_v1#p20/s27]
- Recommendation: Add a table to Section 11.3 of per-scheme reattempt limits (count, window, response categories, which merchant advice codes stop retries) with their source and review owner. Parameterise the FR-7 test from that table. Change Section 27 to 'Mostly ready' until it is done.
  - Issue: No specification of the reattempt limits that the Retry Engine and FR-7 test rely on.
  - Rationale: These limits cannot be implemented or tested until someone writes them down.
  - Expected benefit: FR-7 becomes implementable and verifiable, and the Section 27 status becomes accurate. (objectives: FR-7)
  - Supporting evidence: EV-065, EV-066
  - Verification: FR-7 cascade simulation asserts each tabulated limit.
- Next step: Scheme compliance lead: Compile the current Visa and Mastercard (and Amex) reattempt rules into the Section 11.3 table.
- Decision AD-037 (FR-7): refines. Specifies the scheme limits that FR-7 refers to.
- Decision AD-010 (Section 24 - Cascade policy): preserves. The cascade triggers are unchanged; limits are added.

## Ambiguities

### FND-026 FR-8 tolerance unit is undefined and its test does not check the authorisation-rate bound

- **ambiguity** · ambiguous requirement · severity **medium** · confidence 0.65 (medium) · rank 18
- Disposition: **refinement now**

FR-8 says '2%' and Section 10.3 says 'default 2' without a unit, so the tolerance could mean 2 percentage points or a 2% relative drop, and those give materially different routing. Section 10.2 also applies a weighted score whose default emphasises cost, alongside the FR-8 rule, without saying which takes precedence. The FR-8 test checks only that the selected acquirer matches a preset expectation, so it cannot show that the authorisation rate stays within tolerance.

- Where: p.9 §10.3 (FR-8): "configured tolerance (default 2). Separately, the weekly Routing Review compares each merchant's realised"
- Where: p.2 §2.1 (FR-8): "FR-8 For each transaction, the Routing Engine shall prefer the lowest-cost eligible acquirer unless doing so reduces the expected"
- Evidence EV-067 (doc, supports): "configured tolerance (default 2). Separately, the weekly Routing Review compares each merchant's realised" [doc:DOC-design_v1#p9/s10.3]
- Evidence EV-068 (doc, supports): "For a set of synthetic transactions with configured costs and approval priors, the selected acquirer matches the" [doc:DOC-design_v1#p19/s26.1]
- Evidence EV-028 (doc, supports): "applies the cost preference when the difference is within the configured tolerance (default 2)." [doc:DOC-design_v1#p9/s10.3]
- Evidence EV-029 (doc, supports): "adjusts weights where the merchant's authorization rate has fallen by more than the tolerance." [doc:DOC-design_v1#p9/s10.3]
- Recommendation: State in FR-8 and Section 10.3 whether the tolerance is in percentage points or relative terms, and define how the FR-8 rule and the Section 10.2 score combine. Add an FR-8 criterion based on the control slice: the realised authorisation rate under cost-preferred routing stays within the tolerance of the approval-first control.
  - Issue: The unit is undefined, the score and the rule overlap, and the test is circular.
  - Rationale: Routing directly drives both cost and authorisation rate across all card volume.
  - Expected benefit: FR-8 becomes unambiguous and verifiable. (objectives: FR-8)
  - Supporting evidence: EV-067, EV-068
  - Verification: Routing decision tests at the tolerance boundary, plus a control-slice comparison in production.
- Decision AD-011 (Section 24 - Routing): refines. Defines the unit of 'tolerance 2' and how the score and the rule combine.
- Decision AD-038 (FR-8): refines. Makes FR-8's 2% unambiguous and testable.

## Unresolved assumptions

### FND-036 Network tokens 'from launch' rest on a Token Requestor application not yet submitted

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.85 (high) · rank 14
- Disposition: **governance decision** (also: needs investigation) · already acknowledged in the document

Section 24 confirms network tokens as the primary card-on-file credential from launch. Section 27 marks the Vault 'Ready' and Phase 3 'No - ready'. Backlog item 2, however, says the VTS/MDES token-requestor registration and certification have not been applied for. This review adds that the confirmed decision, the readiness verdict and the FR-14 test all depend on an external approval with no date, while the timeline assumes it will arrive in time.

- Where: p.19 §25 (FR-14): "the commercial agreement with a token service provider; certification test plan. Application not yet submitted."
- Where: p.18 §24: "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch; PAN"
- Where: p.20 §27: "Tokenisation, envelope encryption, HSM, SAD handling and network tokens specified"
- Evidence EV-026 (doc, supports): "the commercial agreement with a token service provider; certification test plan. Application not yet submitted." [doc:DOC-design_v1#p19/s25]
- Evidence EV-025 (doc, supports): "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch; PAN" [doc:DOC-design_v1#p18/s24]
- Recommendation: Submit the TRID applications now and record target dates in Backlog item 2. Make the Section 24 decision conditional, with PAN plus stored-credential indicators as the launch fallback. Change Phase 3 to 'Partially - Backlog item 2'.
  - Issue: A confirmed decision depends on scheme onboarding that has not started.
  - Rationale: Scheme registration and certification lead times are outside the team's control.
  - Expected benefit: A realistic FR-14 launch scope and plan. (objectives: FR-14)
  - Supporting evidence: EV-026, EV-025
  - Verification: Scheme certification is complete before the first cohort goes live, or the fallback is accepted in writing.
- Next step: Head of Payments Partnerships: Submit the VTS/MDES token-requestor applications and get onboarding timelines.
- Decision AD-009 (Section 24 - Card-on-file credential): refines. Makes 'from launch' conditional on certification, with a PAN plus MIT/CIT fallback.
- Decision AD-020 (Section 25 item 2): refines. Adds dates and an owner to the pending TRID item.
- Decision AD-043 (FR-14): preserves. FR-14 already allows PAN where tokens are unavailable.

### FND-052 Fraud fail-open for LOW and MEDIUM merchants has no risk owner or exposure limit

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.60 (medium) · rank 16
- Disposition: **governance decision** · already acknowledged in the document

When FRV-1 times out or fails, LOW and MEDIUM risk-tier merchants receive ACCEPT. That means unscored authorizations at campaign peaks, exactly when fraud attacks cluster. The vendor SLA is still pending (Backlog item 4). The document names no accountable owner for accepting this loss exposure and sets no limit (duration, amount, volume) after which the platform switches to REVIEW.

- Where: p.11 §13.2 (FR-9): "On timeout or vendor error: LOW and MEDIUM risk-tier merchants receive ACCEPT;"
- Where: p.19 §25: "FRV-1 contract - data processing agreement and SLA finalisation."
- Evidence EV-108 (doc, supports): "On timeout or vendor error: LOW and MEDIUM risk-tier merchants receive ACCEPT;" [doc:DOC-design_v1#p11/s13.2]
- Evidence EV-081 (doc, supports): "FRV-1 contract - data processing agreement and SLA finalisation." [doc:DOC-design_v1#p19/s25]
- Recommendation: In 13.2, name the Risk owner who accepts the fail-open policy. Add limits, such as an amount cap above which a payment goes to REVIEW and a maximum outage duration before switching to REVIEW, plus alerting. Tie these to the FRV-1 SLA.
  - Issue: The fraud fail-open policy has no owner and no circuit limit.
  - Rationale: P8 permits degradation, but the financial exposure needs explicit acceptance.
  - Expected benefit: Bounded fraud loss during vendor outages (FR-9). (objectives: FR-9, P8)
  - Supporting evidence: EV-108, EV-081
  - Verification: Extend the FR-9 test with a sustained vendor outage that triggers the cap and the alert.
- Next step: Head of Risk: Approve the fail-open limits and record the risk acceptance alongside the FRV-1 SLA.
- Decision AD-012 (Section 24 - Fraud): refines. Keeps the risk-tier fallback but adds an owner and exposure caps.
- Decision AD-022 (Section 25 item 4): refines. Ties fail-open limits to the pending FRV-1 SLA.

### FND-039 Data placement in Singapore and DR in Jakarta assumed compliant with all five markets' rules

- **unresolved assumption** · missing or unverifiable requirement · severity **medium** · confidence 0.50 (medium) · rank 17
- Disposition: **needs investigation**

NFR-7 names five national data-protection laws, yet all primary data sits in ap-southeast-1 and every market's data is replicated to Jakarta. The design assumes that cross-border transfer and processing are allowed for each market, and for local payment-system regulators such as domestic QR rails. It records no transfer mechanism and no regulator view. Whether a localisation or transfer condition applies is unverified here and needs legal confirmation.

- Where: p.16 §19.1 (NFR-7): "All primary data stores (Aurora, DynamoDB, ElastiCache, MSK, S3 intake and archive buckets) are in ap-southeast-1."
- Where: p.16 §19.1: "The Aurora Global Database secondary in ap-southeast-3 (Jakarta) is used for disaster recovery only"
- Evidence EV-087 (doc, supports): "All primary data stores (Aurora, DynamoDB, ElastiCache, MSK, S3 intake and archive buckets) are in ap-southeast-1." [doc:DOC-design_v1#p16/s19.1]
- Evidence EV-088 (doc, supports): "Personal data shall be processed in accordance with the personal data protection laws of each market of operation" [doc:DOC-design_v1#p3/s2.2]
- Recommendation: Add a per-market data-transfer assessment to 19.1, covering the transfer basis, regulator notification and any domestic-processing obligation for QRIS, FPX/DuitNow, PromptPay and InstaPay. Track it as a backlog item.
  - Issue: Cross-border data placement is not assessed against NFR-7 or market payment regulations.
  - Rationale: A localisation requirement found late would force re-architecture of data placement and DR.
  - Expected benefit: Confirms NFR-7 compliance before data placement is fixed. (objectives: NFR-7)
  - Supporting evidence: EV-087, EV-088
  - Verification: DPO and legal sign-off per market recorded in the NFR-7 privacy review.
- Next step: DPO and regulatory counsel: Assess cross-border processing and localisation obligations for each of the five markets.
- Decision AD-031 (Section 19.1): preserves. Data placement is checked, not changed, until legal findings exist.
- Decision AD-029 (NFR-7): preserves. The investigation serves the NFR-7 constraint.
- Decision AD-003 (Section 24 - Disaster recovery): preserves. Jakarta DR is unchanged pending assessment.

## Validation needs

### FND-050 DynamoDB idempotency table keyed by merchant_id with an LSI concentrates the largest merchant on one hot key

- **validation need** · scalability or failure mode · severity **high** · confidence 0.60 (medium) · rank 11
- Disposition: **needs investigation** (also: needs prototyping)

Section 9.3 assumes one partition key sustains 10,000 WCU/s and counts 1 WCU per write. Response bodies of up to 4 KB make each write consume several write units, and LSI writes add more. Keeping 24 h of the largest merchant's records (about 4.7 M items a day) under one partition key with an LSI may also hit item-collection size limits. If the per-key throughput or collection limits are lower than assumed, 45% of peak traffic fails at the idempotency step. Both limits must be verified before the build.

- Where: p.8 §9.3 (NFR-1): "single partition sustains up to 10,000 write capacity units per second."
- Where: p.8 §9.3 (NFR-1): "Keying by merchant_id keeps each merchant's records co-located, which the local secondary index on"
- Where: p.8 §9.2: "response_body String Serialised response, up to 4 KB"
- Evidence EV-106 (doc, supports): "single partition sustains up to 10,000 write capacity units per second." [doc:DOC-design_v1#p8/s9.3]
- Evidence EV-084 (doc, supports): "response_body String Serialised response, up to 4 KB" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-119 (inference, supports): "45% of 10.5 M daily attempts is about 4.7 M records per day under one partition key, at up to about 4–5 KB each (about 20 GB), and the 1,800 WCU figure ignores item size and LSI write amplification." [inference:EV-119] derived from EV-106, EV-084
- Evidence EV-024 (doc, supports): "Each request consumes two writes - lock acquisition and completion update - or about 1,800 WCU at peak" [doc:DOC-design_v1#p8/s9.3]
- Evidence EV-094 (inference, supports): "M-0001 handles 45% of 10.5 M attempts per day, about 4.7 M records. At up to about 4 KB each, plus two writes per request and items over 1 KB costing several WCU, both the write rate and the item collection size per merchant_id could exceed DynamoDB partition and LSI limits." [inference:EV-094] derived from EV-023, EV-084
- Recommendation: Verify the DynamoDB per-key WCU and LSI item-collection limits. Consider making the partition key merchant_id#idempotency_key, replacing the LSI with a GSI on merchant_id plus a time bucket, and storing large response bodies by reference.
  - Issue: The hot-key capacity rests on unverified per-partition and item-collection limits.
  - Rationale: Failure would take out the largest merchant at peak (NFR-1).
  - Expected benefit: Confidence in NFR-1 for the 45%-share merchant. (objectives: NFR-1, FR-5)
  - Supporting evidence: EV-106, EV-084, EV-119
  - Verification: Run a load test at 900 TPS from a single merchant for 4 h with realistic item sizes, with no throttling.
- Next step: Payments API tech lead: Confirm the DynamoDB limits from AWS documentation and prototype the key schema under single-merchant peak load.
- Decision AD-005 (Section 24 - Idempotency store): refines. The key schema and LSI may need to change if the limits are confirmed; RQ-002 is unanswered, so this is not a challenge.
- Decision AD-045 (NFR-1): preserves. The check protects NFR-1 throughput for the largest merchant.

### FND-024 FR-5 test skips concurrency and crash recovery; FR-5 conflicts with the 409 contract

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.75 (medium) · rank 13
- Disposition: **needs testing** (also: refinement now)

FR-5 requires an identical response 'including when duplicate requests arrive concurrently', but Section 9.1 returns 409 to in-flight duplicates, so the requirement and the contract disagree. The FR-5 acceptance test resends only after the first response arrives, so it never exercises the concurrent path or the conditional-put race. Section 9.2 relies on the stuck-payment sweeper to release locks left by crashed pods, but a crash before the payment row exists leaves an IN_PROGRESS record that no sweeper can resolve, which blocks the key with 409 for 24 hours.

- Where: p.19 §26.1 (FR-5): "Send a create-payment request; after its response is received, resend the identical request with the same"
- Where: p.2 §2.1 (FR-5): "downstream provider, and shall return the identical response, including when duplicate requests arrive concurrently. A reused key"
- Where: p.7 §9.1 (FR-5): "While the first request is in flight, a duplicate receives HTTP 409 request_in_progress with Retry-After: 1."
- Evidence EV-062 (doc, supports): "Send a create-payment request; after its response is received, resend the identical request with the same" [doc:DOC-design_v1#p19/s26.1]
- Evidence EV-063 (doc, supports): "While the first request is in flight, a duplicate receives HTTP 409 request_in_progress with Retry-After: 1." [doc:DOC-design_v1#p7/s9.1]
- Evidence EV-064 (doc, supports): "A lock left IN_PROGRESS by a crashed API pod is recovered by the Orchestrator's stuck-payment sweeper (Section" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-079 (inference, supports): "The sweeper scans payments in AUTHORISING, so a lock taken before step 4 (payment creation) has no payment to resolve and stays IN_PROGRESS until the 24-hour TTL." [inference:EV-079] derived from EV-064
- Evidence EV-107 (doc, supports): "Every 60 seconds, the Orchestrator's sweeper finds payments in AUTHORISING for more than 30 seconds, queries the" [doc:DOC-design_v1#p17/s20.3]
- Recommendation: Reword FR-5 to allow 409 for in-flight duplicates, or change Section 9.1. Add a lease timeout to IN_PROGRESS records with no payment_id. Extend the FR-5 test with N parallel identical requests (Redis cold and warm) and with pod kills injected before and after payment creation, asserting one downstream authorisation and no permanently blocked key.
  - Issue: The concurrency and crash paths of FR-5 are unspecified or untested.
  - Rationale: Concurrent retries during acquirer brownouts are the main reason the idempotency layer exists.
  - Expected benefit: FR-5 is demonstrably met under concurrency and failure. (objectives: FR-5)
  - Supporting evidence: EV-062, EV-063, EV-064, EV-079
  - Verification: Extended FR-5 concurrency and crash-injection tests pass.
- Next step: QA lead for Payments Core: Add concurrent and crash-injection idempotency cases to the Section 26 test plan.
- Decision AD-036 (FR-5): refines. Resolves FR-5's concurrent 'identical response' wording against the 409 contract and adds tests for it.
- Decision AD-005 (Section 24 - Idempotency store): preserves. The store design stays; a lease timeout is added to IN_PROGRESS records.

## Recommended refinements

| Finding | Change | Expected benefit |
|---|---|---|
| FND-001 | In Section 9.2 and the Section 24 idempotency row, change the key to idem:resp:{merchant_id}:{idempotency_key}. Store request_hash in the cached value and compare it on every hit, falling through to the DynamoDB path when it differs. Extend the FR-5 test in Section 26 with a cross-merchant collision case and a concurrent-duplicate case. | Stops cross-merchant data leakage and enforces FR-5 on every path. |
| FND-029 | Pick one option. (a) Send FRV-1 the HSM-keyed PAN fingerprint (12.1) or a vendor-specific keyed hash instead of the PAN. (b) Move the PAN call into the CDE: the Card Adapter or a CDE-resident fraud proxy calls FRV-1 directly, with its own service identity. Then update 12.2 and 13.1, and add FRV-1's PCI attestation as a condition of Backlog item 4. | Keeps the CDE accurate for NFR-5 and preserves P2 and P9. |
| FND-028 | Get a written interpretation from the QSA. If post-authorization retention is not allowed, change 12.4 and NFR-6 so the CVC is deleted when the first authorization attempt completes or the cascade window ends. Use stored-credential or incremental-authorization indicators without CVC. Update the confirmed 'CVC handling' decision and the NFR-6 acceptance criterion to match. | Protects NFR-5 (PCI DSS Level 1) and makes NFR-6 lawful and testable. |
| FND-019 | Decide between relaxing NFR-4 to a bounded RPO (for example, seconds of lag plus a post-failover reconciliation of acquirer authorisations against the payment record) and adding synchronous cross-region durability for authorisation commits. Add idempotency_key and request_hash to the payment table (or replicate the DynamoDB table). Revise the NFR-4 criterion to measure data loss under load at the moment of failure. | An honest, verifiable NFR-4 and preserved FR-5 behaviour across failover. |
| FND-044 | In 12.3 and Section 24, launch with at least two HSMs in different AZs and a cross-region HSM/KEK plan. Add the Vault data store to the replication plan in 20.2. Have HSM 503 errors fail fast as non-cascadable. Size HSM throughput for detokenise plus tokenise at 2,000 TPS including cascades, and set the scale trigger by measured HSM utilisation rather than card TPS. | Card acceptance survives the loss of an AZ (NFR-3), and cards can be served after regional failover (NFR-4). |
| FND-016 | In Section 28, make first-cohort go-live depend on Phase 8 and on the Phase 9 items needed for the Singapore cohort (PCI assessment, NFR-1 to NFR-4 tests). Alternatively, record an explicit risk acceptance for an interim fraud fallback with a named owner and update Section 27's conclusion to match. | FR-9 and NFR-5 are met at first go-live, and go-live rests on accepted tests. |
| FND-043 | In 11.2, on a timeout send a reversal for the attempt before cascading, or cascade and queue a reversal. Record late responses in attempt state rather than discarding them, and have a late approval on a non-winning attempt trigger an automatic void. Correct the duplicate-charge sentence. | Ensures at most one live authorization per payment (FR-5/FR-7) and keeps attempt records truthful (P1). |
| FND-045 | In 18.3 and 18.4, require MFA for the Owner, Admin and Finance roles, plus step-up re-authentication on payout account change. Notify all Owners and the registered contact out of band. Hold the new account until it is verified (populate verified_at with a penny-drop or name check), with a 48–72 h cooling-off period, and require a second user's approval. | Prevents payout diversion (FR-17) and enforces P9. |
| FND-005 | In Sections 11 and 21.1, add an overall deadline per payment (for example 1,400 ms) that stops any further cascade. Set the per-attempt timeout from that remaining budget rather than a fixed 2,500 ms. Re-derive the p99 budget with the cascade path included, or have the owner restate NFR-2 to exclude cascades. | Makes NFR-2 achievable and gives a correct latency budget. |
| FND-020 | In Section 16.2, match each provider file as it arrives and keep only cross-provider netting and payout computation as a final step. Alternatively, renegotiate ACQ-TH1 delivery or move the NFR-8 deadline. Define a cut-off and partial-report behaviour for missing files. Revise the NFR-8 test to replay 2027 volume using real arrival times. | NFR-8 can be met, and late files have a defined path. |
| FND-050 | Verify the DynamoDB per-key WCU and LSI item-collection limits. Consider making the partition key merchant_id#idempotency_key, replacing the LSI with a GSI on merchant_id plus a time bucket, and storing large response bodies by reference. | Confidence in NFR-1 for the 45%-share merchant. |
| FND-023 | In Section 7, track settlement status (and refunded_minor) as separate attributes, not lifecycle states, or add the missing transitions. Add REQUIRES_ACTION -> FAILED, define CAPTURED -> CAPTURED for further partial captures, and specify the state for 'authorize-and-hold-capture'. Extend the FR-2 property test with refund-before-settlement sequences. | FR-1, FR-2 and FR-11 become jointly satisfiable. |
| FND-024 | Reword FR-5 to allow 409 for in-flight duplicates, or change Section 9.1. Add a lease timeout to IN_PROGRESS records with no payment_id. Extend the FR-5 test with N parallel identical requests (Redis cold and warm) and with pod kills injected before and after payment creation, asserting one downstream authorisation and no permanently blocked key. | FR-5 is demonstrably met under concurrency and failure. |
| FND-036 | Submit the TRID applications now and record target dates in Backlog item 2. Make the Section 24 decision conditional, with PAN plus stored-credential indicators as the launch fallback. Change Phase 3 to 'Partially - Backlog item 2'. | A realistic FR-14 launch scope and plan. |
| FND-025 | Add a table to Section 11.3 of per-scheme reattempt limits (count, window, response categories, which merchant advice codes stop retries) with their source and review owner. Parameterise the FR-7 test from that table. Change Section 27 to 'Mostly ready' until it is done. | FR-7 becomes implementable and verifiable, and the Section 27 status becomes accurate. |
| FND-052 | In 13.2, name the Risk owner who accepts the fail-open policy. Add limits, such as an amount cap above which a payment goes to REVIEW and a maximum outage duration before switching to REVIEW, plus alerting. Tie these to the FRV-1 SLA. | Bounded fraud loss during vendor outages (FR-9). |
| FND-039 | Add a per-market data-transfer assessment to 19.1, covering the transfer basis, regulator notification and any domestic-processing obligation for QRIS, FPX/DuitNow, PromptPay and InstaPay. Track it as a backlog item. | Confirms NFR-7 compliance before data placement is fixed. |
| FND-026 | State in FR-8 and Section 10.3 whether the tolerance is in percentage points or relative terms, and define how the FR-8 rule and the Section 10.2 score combine. Add an FR-8 criterion based on the control slice: the realised authorisation rate under cost-preferred routing stays within the tolerance of the approval-first control. | FR-8 becomes unambiguous and verifiable. |

## Areas where no change is needed

- FND-013 Ledger is written in the same transaction as state changes, with an outbox and append-only enforcement: The design meets FR-10 and principles P1, P5 and P7 with an established pattern and checks the projection against the postings.
- FND-040 Money representation and ISO 4217 exponent handling are correct and rigorous: Integer minor units, versioned exponent tables and conversions that reject rounding are fit for P4 and FR-10 as written.
- FND-053 Webhook signing, SSRF protection and per-endpoint isolation: These controls directly address the main webhook threats and noisy-neighbour risk for FR-12 and NFR-9.
- SA-001 (sections 15): Money is held as integer minor units with explicit conversion of currency exponents, rejection of any amount that would need rounding, and single half-to-even rounding with residue tracking. This meets P4 and supports FR-10 balancing across IDR and other currencies. (see FND-013)
  - p.12 §15: "the adapter converts explicitly and rejects any amount that would need rounding."
- SA-002 (sections 17): Webhooks have timestamped HMAC signatures, event IDs for deduplication, per-endpoint isolation and SSRF-safe address pinning. Together these meet FR-12 and P7 without letting one merchant affect others.
  - p.13 §17: "refuses private, loopback, link-local and cloud-metadata addresses, and connects to the validated address for that delivery"
- SA-003 (sections 2, 3, 26): Requirements carry IDs that are traced to acceptance criteria and readiness ratings, and the principles state that they take precedence over later sections. This makes the design's intent clear enough to review against. (see FND-026)
  - p.2 §2: "Each requirement carries an ID used again in Section 26 (Validation and Acceptance Criteria) and Section 27"
- SA-004 (sections 18.5): Back-office write actions need just-in-time elevation approved by a second staff member, which meets P9 and P10 for internal staff. (see FND-045)
  - p.14 §18.5: "require just-in-time elevation approved by a second staff member, with a mandatory audit reason."
- SA-005 (sections 3, 15, 19): Money is represented the same way in P4, Section 15 and the Section 19 schema: BIGINT minor units with a CHAR(3) currency, positive-amount checks, adapters that convert exponents explicitly and reject amounts needing rounding, and one half-to-even rounding point. This meets FR-10 and avoids rounding defects.
  - p.12 §15: "No floating-point type is used for amounts in any service, schema, or API payload. JSON amounts are integers;"
- SA-006 (sections 14, 26.1): The ledger is append-only (UPDATE and DELETE revoked), balanced per currency through a deferred trigger, recomputed nightly against the projection, and payouts are frozen on a discrepancy. The FR-10 acceptance test checks all of this, so FR-10 and P5 are met and verifiable. (see FND-013)
  - p.12 §14.3: "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them,"
- SA-007 (sections 1, 21.2): The volume baseline and MSK throughput figures are arithmetically consistent: 10.5 M per day is about 122 TPS, and 6 × 1.8 KB × 2,000 is 21.6 MB/s. Capacity sizing for NFR-1 therefore rests on correct sums.
  - p.17 §21.2: "About six 1.8 KB events per payment; 2,000 TPS ≈ 21.6 MB/s ingress across three kafka.m7g.xlarge"
- SA-008 (sections 15): Money representation follows P4 and the ISO 4217 exponents are stated correctly. (see FND-040)
  - p.12 §15: "the adapter converts explicitly and rejects any amount that would need rounding."
- SA-009 (sections 17): Webhook signing, SSRF/DNS-rebinding protection and per-endpoint isolation meet FR-12 and NFR-9. (see FND-053)
  - p.13 §17: "refuses private, loopback, link-local and cloud-metadata addresses, and connects to the validated"
- SA-010 (sections 14.3, 19): Atomic state, ledger and outbox commits, revoked UPDATE/DELETE rights, and nightly recomputation with a payout freeze satisfy FR-10 and P5. (see FND-013)
  - p.12 §14.3: "There is no dual write between the payment store and the ledger."
- SA-011 (sections 18.5, 22): Back-office access uses SSO, hardware MFA and JIT elevation with a second approver, and audit goes to Object Lock storage. This meets P9, P10, FR-16 and NFR-12.
  - p.14 §18.5: "write actions (manual refunds, payout holds, merchant suspension) require just-in-time elevation"

## Unresolved issues and next steps

- FND-028 (needs investigation): CVC retention until settlement rests on a doubtful reading of PCI DSS (FND-028) Next step (PCI compliance lead with the QSA): Get a written ruling on SAD retention between authorization and settlement before the Phase 2 Vault build starts.
- FND-019 (governance decision): Zero RPO on region loss conflicts with asynchronous Aurora replication; idempotency rebuild has no source data (FND-019) Next step (Head of Platform Engineering with Finance controller): Decide the RPO target and mechanism for region loss, then update NFR-4, Sections 19 and 20.2 and the NFR-4 test.
- FND-016 (governance decision): First cohort goes live before the Fraud Hook and before hardening and PCI assessment (FND-016) Next step (Programme director with Head of Risk): Re-sequence Phases 7 to 9 for the first cohort, or sign a time-boxed risk acceptance.
- FND-050 (needs investigation): DynamoDB idempotency table keyed by merchant_id with an LSI concentrates the largest merchant on one hot key (FND-050) Next step (Payments API tech lead): Confirm the DynamoDB limits from AWS documentation and prototype the key schema under single-merchant peak load.
- FND-024 (needs testing): FR-5 test skips concurrency and crash recovery; FR-5 conflicts with the 409 contract (FND-024) Next step (QA lead for Payments Core): Add concurrent and crash-injection idempotency cases to the Section 26 test plan.
- FND-036 (governance decision): Network tokens 'from launch' rest on a Token Requestor application not yet submitted (FND-036) Next step (Head of Payments Partnerships): Submit the VTS/MDES token-requestor applications and get onboarding timelines.
- FND-025 (needs investigation): Scheme reattempt limits are referenced but never specified (FND-025) Next step (Scheme compliance lead): Compile the current Visa and Mastercard (and Amex) reattempt rules into the Section 11.3 table.
- FND-052 (governance decision): Fraud fail-open for LOW and MEDIUM merchants has no risk owner or exposure limit (FND-052) Next step (Head of Risk): Approve the fail-open limits and record the risk acceptance alongside the FRV-1 SLA.
- FND-039 (needs investigation): Data placement in Singapore and DR in Jakarta assumed compliant with all five markets' rules (FND-039) Next step (DPO and regulatory counsel): Assess cross-border processing and localisation obligations for each of the five markets.

Research questions left unanswered:
- RQ-002: Can the DynamoDB idempotency table (partition key merchant_id, an LSI on created_at, response bodies up to 4 KB) hold the largest merchant's 900 TPS? Two DynamoDB limits matter here: the per-partition write ceiling, which Section 9.3 states as 10,000 WCU, and the 10 GB item-collection limit that applies to tables with an LSI. One merchant's 24 hours of records could reach tens of GB.
- RQ-007: Do PCI DSS v4.0 / v4.0.1 Requirements 3.2.1 and 3.3.2 actually allow a service provider to keep an encrypted CVC after authorization, until settlement or for up to 72 hours, for cascade re-presentation and incremental authorizations? Or does Requirement 3.3.1 forbid keeping SAD after authorization completes?
- RQ-008: What are the current Visa and Mastercard rules on reattempts and cascading, including whether a soft decline 05 sent to a second acquirer counts as a reattempt, the 30-day reattempt limits, and which response codes are Category 1 or 'do not reattempt'? Does Section 11's classification follow them?
- RQ-009: Do Indonesian rules (Bank Indonesia payment-system rules, QRIS, national payment gateway (GPN) domestic routing, GR 71/2019) or other markets' rules require domestic processing or domestic storage of transaction data? If so, how does that affect hosting in Singapore only and routing Indonesian domestic cards to the regional acquirer ACQ-SG2?
- RQ-012: Can NFR-4's zero RPO for authorized payments and ledger postings be met with Aurora Global Database, whose cross-region replication is asynchronous? After a regional failover, can idempotency state really be 'reconstructed from the payment table' when that table stores no idempotency key, and if not, do merchant retries cause duplicate charges?
- RQ-013: Is a single CloudHSM in ap-southeast-1a, restored from daily backups, compatible with 99.95% availability (NFR-3), and how long does restoring an HSM from backup take? If the HSM is down, the Vault returns 503, which the Card Adapter treats as retryable. Does that make every card payment cascade three times and then fail, piling extra load on the platform?

## Evidence limitations

- DOC-design_v1: native PDF block not sent because the configured model backend accepts text only. Impact: figures, diagrams and tables rendered as images were not visible to the model; the review is based on the extracted text (DEG-001)
- No external research was possible: no tool gateway (--no-tools, or every server is disabled). Impact: doc-only review: every question that needs external evidence is reported as a validation need, and confidence is lowered (DEG-002)
- assess shard 2/4 (requirements_and_consistency) was cut by the stage 1 limit at 265 s; 14 finished finding(s) kept (cut call llm-0002). Impact: every criterion of the shard has a finding; the shard's lower-ranked findings, if any, are missing (DEG-003)
- FND-050's recommendation appears to reverse approved decision AD-005 (Section 24 - Idempotency store) without a 'challenges' label. Impact: the conflict is not declared and not backed by the two evidence items a challenge needs; check it against the decision before acting on it (DEG-004)

## Evidence register

| ID | Type | Source | Retrieved | Cited |
|---|---|---|---|---|
| EV-001 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-002 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-003 | doc | doc:DOC-design_v1#p7/s9.1 | - | yes |
| EV-004 | doc | doc:DOC-design_v1#p11/s13.1 | - | yes |
| EV-005 | doc | doc:DOC-design_v1#p10/s12.2 | - | yes |
| EV-006 | doc | doc:DOC-design_v1#p10/s12.1 | - | yes |
| EV-007 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-008 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-009 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-010 | doc | doc:DOC-design_v1#p16/s20.2 | - | yes |
| EV-011 | doc | doc:DOC-design_v1#p17/s20.2 | - | yes |
| EV-012 | doc | doc:DOC-design_v1#p17/s21.1 | - | yes |
| EV-013 | doc | doc:DOC-design_v1#p9/s10.5 | - | yes |
| EV-014 | doc | doc:DOC-design_v1#p9/s11.1 | - | yes |
| EV-015 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-016 | doc | doc:DOC-design_v1#p10/s12.3 | - | no |
| EV-017 | doc | doc:DOC-design_v1#p2/s1 | - | no |
| EV-018 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-019 | doc | doc:DOC-design_v1#p12/s16.1 | - | yes |
| EV-020 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-021 | doc | doc:DOC-design_v1#p14/s18.4 | - | yes |
| EV-022 | doc | doc:DOC-design_v1#p14/s18.2 | - | yes |
| EV-023 | doc | doc:DOC-design_v1#p8/s9.3 | - | no |
| EV-024 | doc | doc:DOC-design_v1#p8/s9.3 | - | yes |
| EV-025 | doc | doc:DOC-design_v1#p18/s24 | - | yes |
| EV-026 | doc | doc:DOC-design_v1#p19/s25 | - | yes |
| EV-027 | doc | doc:DOC-design_v1#p13/s16.2 | - | no |
| EV-028 | doc | doc:DOC-design_v1#p9/s10.3 | - | yes |
| EV-029 | doc | doc:DOC-design_v1#p9/s10.3 | - | yes |
| EV-030 | doc | doc:DOC-design_v1#p12/s14.3 | - | yes |
| EV-031 | doc | doc:DOC-design_v1#p12/s14.3 | - | yes |
| EV-032 | inference | inference:EV-032 from EV-001, EV-002, EV-003 | - | yes |
| EV-033 | inference | inference:EV-033 from EV-009, EV-010, EV-011 | - | yes |
| EV-034 | inference | inference:EV-034 from EV-012, EV-013, EV-014 | - | yes |
| EV-035 | inference | inference:EV-035 from EV-016, EV-017 | - | yes |
| EV-036 | inference | inference:EV-036 from EV-018, EV-019, EV-020 | - | no |
| EV-037 | inference | inference:EV-037 from EV-027 | - | yes |
| EV-038 | doc | doc:DOC-design_v1#p8/s9.2 | - | no |
| EV-039 | doc | doc:DOC-design_v1#p8/s9.2 | - | no |
| EV-040 | doc | doc:DOC-design_v1#p4/s3 | - | yes |
| EV-041 | doc | doc:DOC-design_v1#p7/s9.1 | - | no |
| EV-042 | doc | doc:DOC-design_v1#p2/s2.1 | - | yes |
| EV-043 | doc | doc:DOC-design_v1#p11/s13.1 | - | no |
| EV-044 | doc | doc:DOC-design_v1#p10/s12.1 | - | no |
| EV-045 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-046 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-047 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-048 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-049 | doc | doc:DOC-design_v1#p9/s11.2 | - | no |
| EV-050 | doc | doc:DOC-design_v1#p17/s21.1 | - | no |
| EV-051 | doc | doc:DOC-design_v1#p9/s10.5 | - | no |
| EV-052 | doc | doc:DOC-design_v1#p20/s26.2 | - | yes |
| EV-053 | doc | doc:DOC-design_v1#p17/s20.2 | - | yes |
| EV-054 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-055 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-056 | doc | doc:DOC-design_v1#p10/s12.3 | - | no |
| EV-057 | doc | doc:DOC-design_v1#p10/s12.3 | - | no |
| EV-058 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-059 | doc | doc:DOC-design_v1#p6/s7.2 | - | yes |
| EV-060 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-061 | doc | doc:DOC-design_v1#p6/s7.2 | - | yes |
| EV-062 | doc | doc:DOC-design_v1#p19/s26.1 | - | yes |
| EV-063 | doc | doc:DOC-design_v1#p7/s9.1 | - | yes |
| EV-064 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-065 | doc | doc:DOC-design_v1#p9/s11.3 | - | yes |
| EV-066 | doc | doc:DOC-design_v1#p20/s27 | - | yes |
| EV-067 | doc | doc:DOC-design_v1#p9/s10.3 | - | yes |
| EV-068 | doc | doc:DOC-design_v1#p19/s26.1 | - | yes |
| EV-069 | doc | doc:DOC-design_v1#p12/s14.3 | - | yes |
| EV-070 | doc | doc:DOC-design_v1#p19/s26.1 | - | yes |
| EV-071 | inference | inference:EV-071 from EV-038, EV-039, EV-041, EV-042 | - | yes |
| EV-072 | inference | inference:EV-072 from EV-045, EV-046, EV-047 | - | yes |
| EV-073 | inference | inference:EV-073 from EV-048, EV-049 | - | yes |
| EV-074 | inference | inference:EV-074 from EV-050, EV-051, EV-052 | - | yes |
| EV-075 | inference | inference:EV-075 from EV-009, EV-010, EV-053 | - | yes |
| EV-076 | inference | inference:EV-076 from EV-054, EV-019, EV-055 | - | yes |
| EV-077 | inference | inference:EV-077 from EV-056, EV-057, EV-058 | - | yes |
| EV-078 | inference | inference:EV-078 from EV-059, EV-060 | - | yes |
| EV-079 | inference | inference:EV-079 from EV-064 | - | yes |
| EV-080 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-081 | doc | doc:DOC-design_v1#p19/s25 | - | yes |
| EV-082 | doc | doc:DOC-design_v1#p17/s21.1 | - | no |
| EV-083 | doc | doc:DOC-design_v1#p9/s11.2 | - | no |
| EV-084 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-085 | doc | doc:DOC-design_v1#p16/s20.2 | - | no |
| EV-086 | doc | doc:DOC-design_v1#p21/s28 | - | no |
| EV-087 | doc | doc:DOC-design_v1#p16/s19.1 | - | yes |
| EV-088 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-089 | doc | doc:DOC-design_v1#p12/s15 | - | yes |
| EV-090 | inference | inference:EV-090 from EV-007, EV-080 | - | yes |
| EV-091 | inference | inference:EV-091 from EV-001, EV-003 | - | no |
| EV-092 | inference | inference:EV-092 from EV-082, EV-013 | - | yes |
| EV-093 | inference | inference:EV-093 from EV-083 | - | yes |
| EV-094 | inference | inference:EV-094 from EV-023, EV-084 | - | yes |
| EV-095 | inference | inference:EV-095 from EV-019, EV-018 | - | no |
| EV-096 | inference | inference:EV-096 from EV-015, EV-085 | - | yes |
| EV-097 | doc | doc:DOC-design_v1#p11/s13.1 | - | no |
| EV-098 | doc | doc:DOC-design_v1#p8/s9.2 | - | no |
| EV-099 | doc | doc:DOC-design_v1#p8/s9.2 | - | no |
| EV-100 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-101 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-102 | doc | doc:DOC-design_v1#p10/s12.1 | - | yes |
| EV-103 | doc | doc:DOC-design_v1#p14/s18.3 | - | yes |
| EV-104 | doc | doc:DOC-design_v1#p10/s12.4 | - | no |
| EV-105 | doc | doc:DOC-design_v1#p10/s12.4 | - | no |
| EV-106 | doc | doc:DOC-design_v1#p8/s9.3 | - | yes |
| EV-107 | doc | doc:DOC-design_v1#p17/s20.3 | - | yes |
| EV-108 | doc | doc:DOC-design_v1#p11/s13.2 | - | yes |
| EV-109 | doc | doc:DOC-design_v1#p13/s17 | - | yes |
| EV-110 | doc | doc:DOC-design_v1#p12/s14.3 | - | yes |
| EV-111 | inference | inference:EV-111 from EV-097, EV-006, EV-005 | - | yes |
| EV-112 | inference | inference:EV-112 from EV-098, EV-099, EV-041 | - | yes |
| EV-113 | inference | inference:EV-113 from EV-048, EV-100 | - | yes |
| EV-114 | inference | inference:EV-114 from EV-015, EV-101 | - | yes |
| EV-115 | inference | inference:EV-115 from EV-009, EV-010 | - | yes |
| EV-116 | inference | inference:EV-116 from EV-104, EV-105 | - | yes |
| EV-117 | inference | inference:EV-117 from EV-050, EV-013 | - | no |
| EV-118 | inference | inference:EV-118 from EV-019, EV-055 | - | yes |
| EV-119 | inference | inference:EV-119 from EV-106, EV-084 | - | yes |

## Review coverage

| Criterion | Outcome | Findings | Note |
|---|---|---|---|
| design_intent | findings | FND-019, FND-045, FND-036, FND-026 | Objectives, principles and requirement IDs are clear and traceable. Problems found: FR-8's tolerance has no unit, NFR-4's zero RPO conflicts with the stated architecture, payout changes break P9, and a confirmed decision depends on a pending backlog item. |
| fitness_for_objectives | findings | FND-001, FND-029, FND-028, FND-019, FND-005, FND-044, FND-020, FND-045, FND-050, FND-023, FND-013 | Checked idempotency, the vault and PCI scope, the fraud hook, DR, latency, the HSM topology, reconciliation timing, the payout admin path, the state machine and the ledger against FR and NFR targets. |
| requirement_completeness | findings | FND-016, FND-043, FND-023, FND-024, FND-025 | Checked error and rollback paths (timeouts, crashes, late files), state coverage, scheme rules and phase gating against FR and NFR requirements and the backlog. |
| internal_consistency | findings | FND-001, FND-029, FND-016, FND-005, FND-019, FND-020, FND-044, FND-036, FND-023, FND-026, FND-013 | Cross-checked principles, requirements, the latency and capacity arithmetic, delivery timelines, CDE scope, the readiness table and build phases. |
| claims_and_external_constraints | findings | FND-028, FND-029, FND-005, FND-043, FND-050, FND-019, FND-020, FND-039, FND-040 | Checked: PCI SAD and scope claims, DynamoDB limits, latency arithmetic, cascade duplicate-charge claim, RPO claim, reconciliation timing, volume and MSK arithmetic, ISO 4217 exponents. |
| security_and_privacy | findings | FND-029, FND-001, FND-045, FND-028, FND-053 | Checked: PCI scoping, vault access, SAD retention, idempotency tenancy, merchant and back-office authentication, payout changes, webhooks, logging and audit. |
| scalability_and_failure_modes | findings | FND-043, FND-044, FND-019, FND-005, FND-020, FND-050, FND-024, FND-001, FND-013, FND-053 | Checked: HSM topology, DR/RPO, cascade timeouts, latency budget, DynamoDB hot key, sweepers, reconciliation timing, Aurora and MSK capacity. |
| assumptions_and_dependencies | findings | FND-029, FND-001, FND-020, FND-036, FND-044, FND-016, FND-039 | Checked: backlog items 1-7 against confirmed decisions and build phases, the HSM single-node assumption, idempotency key uniqueness, the FRV-1 dependency and data-residency premises. |
| verifiability | findings | FND-005, FND-019, FND-020, FND-024, FND-025, FND-026, FND-013 | no coverage row returned by the model; derived by code from the findings |
| decision_preservation | findings | FND-001, FND-029, FND-028, FND-044, FND-020, FND-036, FND-013 | Several confirmed decisions in Section 24 (Redis key format, CVC handling, one HSM at launch, the batch-after-all-files rule, network tokens from launch) affect requirements. Each is framed as a refinement or as a question for a QSA or governance owner. Evidence for any formal challenge is attached later. |
| operability_and_governance | findings | FND-019, FND-020, FND-052, FND-013 | Checked: risk-acceptance owners, fail-open policy, late-file handling, DR runbook, payout freeze controls. |

## Run details

| | |
|---|---|
| Run | langgraph_payments_v1_1 (started 2026-10-03T09:28:22Z) |
| Outcome | completed_degraded |
| Model | requested claude-opus-5-5; served claude-opus-5-5; effort per-stage (extra.model.effort_by_stage) |
| Persona | generalist_architect |
| Tool transport | live |
| Research stop | tool_failure (error): no_tools; 0 iteration(s); 0 cited of 0 retrieved |
| Tool calls | none |
| Tokens | input 282243, cached 62572, output 122221; cost ~$4.71 (price table 2026-09-25); a lower bound: 1 model call with unrecorded usage (assess, deadline cut) |
| Extractor | pdfplumber 0.11.10 |
| Config sha256 | 79a78b6aea40f86fd3030500a033c55c70121845d35d70a2863fb427aaf80835 |
| Prompt bundle sha256 | 6f0ee28ab9acf35152a2d4456207a8a068222149422e66d801c8195455c28ba7 |
| Git commit | c4d94b95460be0c1cede59669053643088dd9a92 |
| Fault schedule | none |
| Model fallbacks | 0 |
| Canonical text DOC-design_v1 | sha256 ad0bb891f073f14325b6ba716d58070d6b074ebaef9a9c64432138b89b64ec3c |
