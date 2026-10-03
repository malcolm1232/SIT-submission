# Design review: Serindit Pay — Merchant Payment Orchestration Platform

| | |
|---|---|
| Review | REV-ui_flow_1 (full review) |
| Under review | DOC-design_v1: Serindit Pay — Merchant Payment Orchestration Platform v1.0, 21 pages |
| Verdict | **not fit** (confidence 0.75, medium) |
| Tools used | none |
| Tools disabled | mcp-internet-search, mcp-research-information, mcp-browser-automation-pw, mcp-document-intelligence |
| Reporting threshold | severity low and above (0 finding(s) in the appendix) |

> No external research was possible or used in this run: every finding rests on the document alone.


## Design intent

MPOP is Serindit Pay's Merchant Payment Orchestration Platform. It accepts merchant payment requests, routes each one to an acquirer, e-wallet provider or bank-transfer rail, and accounts for every resulting movement of money until it is settled to the merchant. It replaces five per-market integration stacks with one merchant API across five Southeast Asian markets. Scope covers acceptance, routing, retries, idempotency, vaulting, fraud-scoring integration, a double-entry ledger, reconciliation, payouts, webhooks and a merchant admin plane, for about 15,000 merchants at a peak of 2,000 TPS. Disputes case management, KYB, 3DS server internals, lending/BNPL and checkout UIs are out of scope.

Objectives:
- Replace five per-market integration stacks (no shared routing or ledger, spreadsheet reconciliation) with one platform and one versioned merchant API across SG, MY, ID, TH and PH.
- Serve approximately 15,000 active merchants and a peak of 2,000 payment-creation TPS by the 2027 design target.
- P1: One payment, one truth: the payment record and the ledger are the source of truth; provider responses are only inputs.
- P2: Card data stays in the Vault; PAN and SAD leave the Vault boundary only over the Card Adapter's connection to an acquirer; all other services handle tokens only.
- P3: Idempotency is scoped to the (merchant, key) pair for every mutating call.
- P4: Money is integers: integer minor units with an ISO 4217 code; no floating-point amounts.
- P5: The ledger is append-only; corrections are new reversing or adjusting journals.
- P6: Adapters absorb provider differences; the core never branches on provider identity.
- P7: At-least-once delivery with exactly-once effect via consumer deduplication on stable identifiers.
- P8: Fail closed on security; degrade gracefully to documented defaults on optional enrichment (fraud signals, BIN metadata).
- P9: Least privilege and separation of duties; money-moving permissions are separate from configuration permissions.
- P10: Everything is auditable: every mutation, routing decision and admin action can be reconstructed.
- NFR-2: Card authorization p99 at most 1,500 ms end to end, including cascade; orchestration overhead p99 at most 250 ms.
- NFR-3: Merchant payment API monthly availability of at least 99.95%.
- NFR-4: RPO zero for authorized payments and ledger postings, including on loss of an AWS region; RTO 30 minutes.
- FR-8: Prefer the lowest-cost eligible acquirer unless this lowers the expected authorization rate by more than 2%.

Constraints:
- NFR-5: Assessment as a PCI DSS v4.0 Level 1 service provider, with the CDE limited to the components listed in Section 12.2.
- NFR-6: SAD handled per PCI DSS v4.0 Req. 3.2.1 and 3.3.2: stored only encrypted in the Vault and deleted at settlement.
- NFR-7: Personal data processed under SG PDPA 2012, MY PDPA 2010, ID Law 27/2022, TH PDPA 2019 and PH DPA 2012, including purpose limitation, retention limits and access logging.
- FR-7: Card scheme reattempt rules: never reattempt where the scheme prohibits it.
- Primary hosting on AWS ap-southeast-1 across three AZs; DR secondary in ap-southeast-3.
- The foundational principles take precedence over any later section that conflicts with them.
- Out of scope: KYB/onboarding (Merchant Risk platform supplies an approved-merchant event), 3DS server internals, dispute case management, and lending/BNPL.
- ACQ-PH1 retires API v2 in Q3 2027, so the adapter must migrate to v3 before then.
- NFR-12: Audit records are immutable and retained for five years; payment and attempt records are kept 7 years.

Key assumptions:
- 2027 volume targets: 10.5 M attempts/day, 2,000 peak TPS, card share 55%, and the largest merchant at 45% of peak (about 900 TPS).
- Fewer than 1% of card payments cascade, so the cascade path sits above p99 (2025 baseline: 3.8% retryable outcomes, about 31% recovered in the pilot).
- PCI DSS v4.0 Req. 3.2.1/3.3.2 permit storing encrypted CVC until settlement, and acquirers need the CVC for cascade re-presentation and incremental authorizations.
- FRV-1 needs the full PAN for its consortium velocity graph; the Fraud Hook obtains it through Vault detokenise.
- One CloudHSM with daily backups is enough until sustained card volume exceeds 1,500 TPS.
- Network tokens are available from launch, although token-requestor onboarding has not been submitted (Backlog item 2).
- Settlement files arrive daily at stated local times, and the matcher (45 min at 2025 volume) plus reports (15 min) finish by 08:00 SGT.
- Aurora sizing is based on a spike test of 2,600 TPS on db.r7g.8xlarge; latency budget components come from load tests, vendor benchmarks and 2025 production p99.
- The first cohort (Singapore, cards and PayNow) can go live after Phase 7, with Finance Operations handling disputes manually and merchants using the portal.

Located at: p.1 §1, p.2 §1 (2 passages).

## Fitness for purpose

**Not fit** (confidence 0.75). As written, the design is not fit to start building. The ledger core is sound: FND-020 shows state, journal and outbox committed atomically with append-only grants. Aurora sizing is backed by a measurement (FND-032), and webhook isolation is well designed (FND-046). However, one critical finding and about ten high findings break objectives the document makes binding. - **Idempotency (P3, FR-5):** the Redis fast path is keyed without the merchant and skips the body-hash check (FND-006, critical). This causes cross-merchant response leakage and false successes. Recovery of stuck locks and of idempotency state after failover is also incomplete (FND-043, FND-037). - **PCI scope (P2, NFR-5):** the out-of-scope Fraud Hook detokenises PAN under the Card Adapter's role and sends it to FRV-1 (FND-033). This collapses the CDE boundary that the assessment relies on. - **Latency (NFR-2):** the latency budget leaves out cascades because it assumes fewer than 1% of payments cascade. The document's own 3.8% retryable rate and the 2,500 ms timeout contradict that premise (FND-009). - **Recovery and availability (NFR-4, NFR-3):** RPO zero is claimed on asynchronous replication (FND-037). The single CloudHSM in one AZ has no DR path for the CDE (FND-036). - **Cascade safety:** cascading after a timeout can double-authorize, because late approvals are discarded without reversal (FND-035). - **Other high findings:** NFR-8 misses the 08:00 SGT deadline by design (FND-040). The first cohort launches without fraud scoring, contrary to FR-9 (FND-010). Payout bank account changes have no step-up MFA or second approver (FND-041). Most of these are refinement_now or governance items with clear fixes, so the path to fit_with_conditions is short. The document is only not fit in its current form. **Limits of this review:** - No external research was possible (DEG-002). The PCI SAD reading (FND-021), the DynamoDB per-partition and LSI quotas (FND-038) and data-localisation rules (FND-030) therefore remain unverified. - Image-rendered figures and tables were not seen (DEG-001). - The design-intent criterion was not assessed (DEG-003). These gaps lower confidence in those specific findings. They do not weaken the not_fit verdict, which rests on internal contradictions that can be checked from the document text alone.

| Objective | Verdict | Findings |
|---|---|---|
| Objective: replace five per-market stacks with one platform and one versioned merchant API | fit with conditions | FND-011, FND-016, FND-010, FND-027 |
| Objective: serve ~15,000 merchants and 2,000 peak TPS by 2027 | fit with conditions | FND-032, FND-038, FND-040 |
| P1 | fit with conditions | FND-020, FND-035, FND-037 |
| P2 | not fit | FND-033, FND-021 |
| P3 | not fit | FND-006, FND-043, FND-016 |
| P4 | fit | - |
| P5 | fit | FND-020 |
| P6 | fit | - |
| P7 | fit | FND-020, FND-046 |
| P8 | fit with conditions | FND-044, FND-036 |
| P9 | fit with conditions | FND-041 |
| P10 | fit with conditions | FND-033 |
| NFR-2 | not fit | FND-009 |
| NFR-3 | not fit | FND-036 |
| NFR-4 | not fit | FND-037, FND-036 |
| FR-8 | fit with conditions | FND-017 |

What would change this verdict: The verdict would move to fit_with_conditions if a revised design did all of the following: - Scopes the Redis fast-path key to the merchant and checks the request hash on every hit (FND-006). Links idempotency records to payments so that the sweeper and failover can recover them (FND-043, FND-037). - Removes PAN detokenisation from the Fraud Hook, or formally brings it and FRV-1 into the CDE (FND-033). - Adds reversal of late approvals and revises the cascade timeout and latency budget so that NFR-2 is achievable (FND-035, FND-009). - Either restates NFR-4 with a realistic RPO approved by an accountable owner, or adopts synchronous protection. Adds HSM redundancy and a regional DR path for the CDE (FND-037, FND-036). - Defines late-file handling or per-provider reconciliation to meet NFR-8 (FND-040). - Gates the first cohort's launch on the Fraud Hook or on a documented risk acceptance (FND-010). - Adds step-up MFA and a second approver for payout bank account changes (FND-041). External evidence could raise or lower confidence on FND-021, FND-038 and FND-030. Confirmation that PCI DSS v4.0 allows SAD to be kept after authorization, or that DynamoDB quotas and localisation rules allow the current design, would remove those concerns. Evidence to the contrary would add further blocking items.

## Strengths

### FND-020 Ledger written atomically with state and outbox; append-only enforced by role grants

- **strength** · confidence 0.85 (high) · rank 20
- Disposition: **no change**

§14.3 and §7.2 commit the state transition, journal and outbox row in one PostgreSQL transaction. §19 revokes UPDATE and DELETE on journal and posting tables, and the §14.2 example journals balance. Together these directly satisfy FR-10, P1, P5 and P7 without dual writes, and the FR-10 test checks the same invariant.

- Where: p.12 §14.3 (FR-10): "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them,"
- Where: p.16 §19 (FR-10): "journal and posting have UPDATE and DELETE revoked from every application role;"
- Evidence EV-046 (doc, supports): "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them," [doc:DOC-design_v1#p12/s14.3]
- Evidence EV-054 (inference, supports): "In the §14.2 example, capture 10000 = 9720 + 280 and settlement 9810 + 190 = 10000, so each example journal balances." [inference:EV-054] derived from EV-046
- Evidence EV-095 (doc, supports): "There is no dual write between the payment store and the ledger." [doc:DOC-design_v1#p12/s14.3]
- Evidence EV-096 (doc, supports): "journal and posting have UPDATE and DELETE revoked from every application role" [doc:DOC-design_v1#p16/s19]
- Why no change is needed: The atomic transaction and the role-level append-only grants enforce FR-10 and P5 by construction, and the FR-10 test verifies them.
- Decision AD-014 (24 Ledger): preserves. Affirms the same-transaction ledger and outbox decision.
- Decision AD-041 (FR-10): preserves. FR-10 is met by construction.

### FND-046 Webhook dispatcher SSRF protection and per-endpoint isolation

- **strength** · confidence 0.80 (high) · rank 21
- Disposition: **no change**

The dispatcher resolves the hostname once, rejects private and metadata addresses, connects to the validated address, and caps in-flight deliveries per endpoint with its own breaker. This addresses SSRF and DNS-rebinding risk against internal services, and prevents one merchant's endpoint from degrading webhooks for others (FR-12, NFR-9).

- Where: p.13 §17 (FR-12): "refuses private, loopback, link-local and cloud-metadata addresses, and connects to the validated"
- Evidence EV-097 (doc, supports): "refuses private, loopback, link-local and cloud-metadata addresses, and connects to the validated" [doc:DOC-design_v1#p13/s17]
- Why no change is needed: These controls are specific and fit FR-12 and NFR-9 as written.
- Decision AD-017 (24 Webhooks): preserves. Affirms the webhook design decision.

### FND-032 Aurora write capacity claim backed by a measured spike

- **strength** · confidence 0.75 (medium) · rank 22
- Disposition: **no change**

The Aurora sizing in 21.2 derives the row-write rate from the per-payment write mix and backs it with a measured 2,600 TPS, two-hour spike on a smaller instance class. The production class is larger again. This makes the NFR-1 capacity premise for the transactional store evidence-based rather than assumed.

- Where: p.17 §21.2 (NFR-1): "db.r7g.8xlarge sustained 2,600 TPS of the full write mix for two hours at 58% writer CPU with commit latency"
- Evidence EV-065 (doc, supports): "db.r7g.8xlarge sustained 2,600 TPS of the full write mix for two hours at 58% writer CPU with commit latency" [doc:DOC-design_v1#p17/s21.2]
- Why no change is needed: The measured headroom (130% of target TPS at 58% CPU on a smaller class) supports NFR-1 for the ledger and payment store; the four-hour run in 26.2 will confirm it.
- Decision AD-003 (24 Payments and ledger store): preserves. The measured spike supports the Aurora instance choice.

## Risks

### FND-006 Redis idempotency fast path is not merchant-scoped and skips the body-hash check

- **risk** · internal contradiction · severity **critical** · confidence 0.85 (high) · rank 1
- Disposition: **refinement now** (also: needs testing)

§9.2 keys the Redis fast path as idem:resp:{idempotency_key} and returns the stored response on a hit without any other check. This contradicts P3 and FR-5, which scope idempotency to the pair (merchant, key). §9.1 accepts merchants' own order or invoice numbers as keys, so two merchants can easily use the same key. Merchant B would then receive merchant A's payment object, which is a cross-merchant data leak and a false success with no authorization. A reused key with a different body would also get the stored response instead of the HTTP 422 that FR-5 requires.

- Where: p.8 §9.2 (FR-5): "incoming mutating request, the Payments API checks this key first; on a hit, it returns the stored response immediately"
- Where: p.3 §3 (P3): "Idempotency is scoped to (merchant, key). Every mutating call is deduplicated on the pair of merchant identity and client-supplied"
- Where: p.8 §9.1 (FR-5): "frequently use their own order or invoice identifiers, which is accepted."
- Evidence EV-018 (doc, supports): "the final response is written to idem:resp:{idempotency_key} with a 24-hour TTL" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-019 (doc, supports): "Idempotency is scoped to (merchant, key). Every mutating call is deduplicated on the pair of merchant identity and client-supplied" [doc:DOC-design_v1#p4/s3]
- Evidence EV-020 (doc, supports): "frequently use their own order or invoice identifiers, which is accepted." [doc:DOC-design_v1#p7/s9.1]
- Evidence EV-047 (inference, supports): "The Redis key has no merchant_id and no request_hash comparison, and keys like order numbers are low-entropy and likely to collide across 15,000 merchants. A fast-path hit therefore returns another merchant's response, or a stale response where 422 is required." [inference:EV-047] derived from EV-018, EV-019, EV-020
- Evidence EV-004 (doc, supports): "incoming mutating request, the Payments API checks this key first; on a hit, it returns the stored response immediately" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-099 (inference, supports): "With 15,000 merchants using sequential order numbers as keys, collisions within the 24-hour TTL are near certain, and each collision returns another merchant's stored response." [inference:EV-099] derived from EV-018, EV-005
- Recommendation: In §9.2 and §24, change the Redis key to idem:resp:{merchant_id}:{idempotency_key}. Store request_hash with the cached response and compare it on every hit (return 422 on mismatch). Extend the FR-5 test in §26.1 with cases for two merchants using the same key and for a fast-path hit with a different body.
  - Issue: The fast-path key omits the merchant and the request hash, which breaks P3 and FR-5.
  - Rationale: Every other tier (DynamoDB PK merchant_id, SK key) is merchant-scoped. Only the Redis tier is not, and it short-circuits the durable checks.
  - Expected benefit: FR-5 holds on every path, and responses cannot leak across merchants (NFR-7). (objectives: FR-5, P3, NFR-7)
  - Supporting evidence: EV-018, EV-019, EV-020, EV-047
  - Verification: FR-5 test: merchant B reusing merchant A's key gets a new payment. A fast-path replay with a modified body returns 422.
- Next step: Payments Core tech lead: Amend §9.2 key schema and the FR-5 acceptance criteria before Phase 3 starts.
- Decision AD-006 (24 Idempotency store): refines. Keeps the two-tier Redis plus DynamoDB store but changes the Redis key format to include merchant_id and store the request hash.
- Decision AD-037 (FR-5): preserves. The change restores the FR-5 contract on the fast path.
- Decision AD-032 (3 Foundational Principles): preserves. Aligns §9.2 with P3, which the principles say takes precedence.
- Decision AD-007 (24 Idempotency retention): preserves. The 24-hour retention is unchanged.

### FND-033 Fraud Hook detokenises PAN under the Card Adapter's role and sends it to FRV-1

- **risk** · security privacy gap · severity **high** · confidence 0.90 (high) · rank 2
- Disposition: **governance decision** (also: refinement now)

Section 13.1 has the Fraud Hook, which Section 12.2 places out of PCI scope, detokenise the full PAN using the Card Adapter's service role and send it to the third-party vendor FRV-1. That contradicts principle P2, the rule in 12.1 that only the Card Adapter may detokenise, and the CDE boundary that NFR-5 depends on. It also hides which service is actually reading PANs in the audit trail, and the FRV-1 data processing agreement is still pending (Backlog item 4). As written, the Fraud Hook, its host cluster and the core VPC path would all fall into the CDE, so the PCI DSS assessment against Section 12.2 would fail.

- Where: p.11 §13.1 (NFR-5): "The Fraud Hook obtains the PAN through the Vault's detokenise operation, using the Card Adapter client library and service role."
- Where: p.10 §12.1: "Only the Card Adapter's service identity may call detokenise."
- Where: p.10 §12.2 (NFR-5): "Fraud Hook Out of scope Token, BIN, last 4 only"
- Evidence EV-072 (doc, supports): "The Fraud Hook obtains the PAN through the Vault's detokenise operation, using the Card Adapter client library and service role." [doc:DOC-design_v1#p11/s13.1]
- Evidence EV-003 (doc, supports): "Only the Card Adapter's service identity may call detokenise." [doc:DOC-design_v1#p10/s12.1]
- Evidence EV-002 (doc, supports): "Fraud Hook Out of scope Token, BIN, last 4 only" [doc:DOC-design_v1#p10/s12.2]
- Evidence EV-073 (doc, supports): "FRV-1 contract - data processing agreement and SLA finalisation." [doc:DOC-design_v1#p19/s25]
- Evidence EV-098 (inference, supports): "A service outside the CDE that receives plaintext PAN by borrowing another service's identity breaks both the stated CDE scope and the least-privilege principle, so the Section 12.2 scoping cannot pass assessment as written." [inference:EV-098] derived from EV-072, EV-003, EV-002
- Evidence EV-013 (inference, supports): "A non-CDE service that holds PAN and forwards it to a vendor puts that service and the vendor into cardholder-data scope, so the CDE in 12.2 is understated." [inference:EV-013] derived from EV-001, EV-002, EV-003
- Evidence EV-059 (doc, supports): "The Fraud Hook obtains the PAN through the Vault's" [doc:DOC-design_v1#p11/s13.1]
- Recommendation: In 13.1, replace card_number with the HMAC PAN fingerprint, or with a vendor-specific keyed hash computed inside the Vault. If FRV-1 really needs the raw PAN, have the Card Adapter (inside the CDE) make the vendor call, add FRV-1 to the 12.2 table as a third-party service provider, and require a signed DPA before Phase 8. Give the Fraud Hook its own identity with no detokenise permission.
  - Issue: PAN leaves the Vault boundary through a service that is out of CDE scope, using a borrowed identity.
  - Rationale: Breaks P2 and P9 and the 12.1 access rule, and invalidates the CDE definition that NFR-5 is assessed against.
  - Expected benefit: Keeps the CDE limited to the Section 12.2 components so NFR-5 is achievable, and keeps detokenise audit attribution accurate (P10). (objectives: NFR-5, NFR-7, P2, P9)
  - Supporting evidence: EV-072, EV-003, EV-002, EV-073
  - Verification: Vault IAM policy test: a detokenise call from the Fraud Hook identity is denied; the QSA scoping review confirms the Fraud Hook is outside the CDE.
- Next step: Head of Payments Security / PCI programme owner: Decide with the QSA and the FRV-1 vendor whether a fingerprint can replace the PAN; update 13.1 and 12.2 before Phase 8.
- Decision AD-029 (NFR-5): preserves. The recommendation keeps the CDE limited to the components listed in §12.2.
- Decision AD-013 (24 Fraud): refines. FRV-1 is still called synchronously, but with a fingerprint instead of the PAN, or through a component inside the CDE.
- Decision AD-023 (25 Backlog item 4): refines. Makes the pending FRV-1 DPA, and the vendor's PCI status, a gate before Phase 8.
- Decision AD-032 (3 Foundational Principles): preserves. Brings §13.1 back in line with P2 and P9, which take precedence.

### FND-035 Cascading after a timeout can double-authorize; late approvals are discarded without reversal

- **risk** · scalability or failure mode · severity **high** · confidence 0.80 (high) · rank 3
- Disposition: **refinement now** (also: needs testing)

Section 11 treats 'no response within 2,500 ms' as retryable and immediately cascades to another acquirer, and any response arriving after the timeout is logged and discarded. A timed-out attempt may still have been approved by the issuer, which leaves the cardholder with two authorization holds and possibly a double capture. The design's claim that 'cascading cannot create a duplicate charge' rests only on internal attempt_ids, not on what the acquirer did. No reversal or void of late approvals is specified, which puts the at-most-one-authorization intent of FR-5 and FR-7 at risk.

- Where: p.9 §11.2 (FR-7): "Responses that arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded."
- Where: p.9 §11.2 (FR-7): "Because each attempt carries its own attempt_id and the previous attempt did not succeed, cascading cannot create a duplicate charge"
- Where: p.9 §11.1 (FR-7): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms"
- Evidence EV-074 (doc, supports): "Responses that arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded." [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-075 (doc, supports): "Because each attempt carries its own attempt_id and the previous attempt did not succeed, cascading cannot create a duplicate charge" [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-009 (doc, supports): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms" [doc:DOC-design_v1#p9/s11.1]
- Evidence EV-100 (inference, supports): "A timeout or 5xx is an unknown outcome, not a failure; cascading on it without reversing the first attempt can produce two approved authorizations for one payment." [inference:EV-100] derived from EV-074, EV-075, EV-009
- Evidence EV-033 (doc, supports): "arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded." [doc:DOC-design_v1#p9/s11.2]
- Evidence EV-053 (inference, supports): "A timeout means the outcome is unknown, not failed. Ledger-only accounting does not undo an issuer-side hold, so a late approval plus a cascaded approval leaves two authorizations at the network." [inference:EV-053] derived from EV-033, EV-034
- Recommendation: In 11.1 and 11.2, add an UNKNOWN outcome class for timeouts and 5xx after the request was sent. Before cascading, send a reversal (or a status query plus reversal) for the timed-out attempt. Any late approval on a superseded attempt triggers an automatic reversal or void and a reconciliation flag, never a silent discard. Cascade on connection-refused only when the request is known not to have been delivered.
  - Issue: Timeouts and 5xx are handled as definite failures, and late approvals are ignored.
  - Rationale: An attempt with an unknown outcome can still turn into an approval at the issuer.
  - Expected benefit: Prevents duplicate authorizations and charges (FR-5, FR-7) and keeps the payment record and ledger as the single source of truth (P1). (objectives: FR-5, FR-7, P1)
  - Supporting evidence: EV-074, EV-075, EV-009
  - Verification: Extend the FR-7 cascade simulation: the simulator approves after the timeout; check that exactly one authorization remains open and a reversal was sent.
- Decision AD-011 (24 Cascade policy): refines. Keeps the cascade triggers but requires the timed-out attempt to be reversed or its status checked before cascading.
- Decision AD-037 (FR-5): preserves. Protects the at-most-one-authorization intent of FR-5.
- Decision AD-038 (FR-7): preserves. The two-additional-attempt cascade limit is unchanged.

### FND-021 CVC retention until settlement rests on a likely misreading of PCI DSS

- **risk** · external constraint violation · severity **high** · confidence 0.75 (medium) · rank 4
- Disposition: **needs investigation** (also: refinement now)

Section 12.4 and NFR-6 keep the CVC encrypted after authorization, until settlement or for up to 72 hours, and reuse it for incremental authorizations. They justify this by saying PCI DSS v4.0 Req. 3.2.1/3.3.2 allow SAD to be kept until the transaction is settled. Our understanding is that those clauses cover SAD stored only before authorization completes, and that keeping it after authorization is not allowed for a non-issuer service provider. If that is right, both the confirmed CVC decision and NFR-6 fail the Level 1 assessment that NFR-5 requires. This is unverified here and must be checked against the standard's text.

- Where: p.10 §12.4: "3.2.1 and 3.3.2, which allow sensitive authentication data to be retained in encrypted form until the transaction is settled."
- Where: p.10 §12.4: "therefore stores the CVC encrypted under a separate KEK, and deletes it when the Reconciliation Service marks the"
- Where: p.3 §2.2 (NFR-6): "Sensitive authentication data shall be handled per PCI DSS v4.0 Requirements 3.2.1 and 3.3.2: stored only in encrypted form, in the"
- Evidence EV-055 (doc, supports): "3.2.1 and 3.3.2, which allow sensitive authentication data to be retained in encrypted form until the transaction is settled." [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-056 (doc, supports): "the credential during a cascade and for incremental authorizations (ride-hailing tips, hotel extensions). The Vault" [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-066 (inference, supports): "Incremental authorizations and settlement-bound deletion both mean SAD is kept after the initial authorization completes, which falls outside a pre-authorization allowance if 3.2.1 is limited to that." [inference:EV-066] derived from EV-055, EV-056
- Evidence EV-090 (doc, supports): "This is permitted by PCI DSS v4.0 Requirements 3.2.1 and 3.3.2, which allow sensitive authentication data to be retained in encrypted form until the transaction is settled." [doc:DOC-design_v1#p10/s12.4]
- Evidence EV-106 (inference, supports): "The compliance basis for SAD retention is asserted in the document without any QSA confirmation, and both the cascade and incremental-authorization behaviour depend on it." [inference:EV-106] derived from EV-090, EV-091
- Recommendation: Get the QSA's written interpretation of Req. 3.2.1/3.3.1/3.3.2. If it confirms that SAD may not be kept after authorization: rewrite 12.4 and NFR-6 so the CVC is deleted when the final authorization outcome of the payment (including the cascade) is reached, and remove CVC reuse for incremental authorizations. Update the CVC handling decision in Section 24 and the NFR-6 acceptance criterion in 26.2 to match.
  - Issue: The SAD retention period rests on a compliance reading that may be wrong.
  - Rationale: A retention model the QSA rejects puts PCI DSS Level 1 status (NFR-5) at risk and creates exposure to scheme penalties.
  - Expected benefit: NFR-5 and NFR-6 can be achieved, and the scope of stored SAD shrinks. (objectives: NFR-5, NFR-6)
  - Supporting evidence: EV-055, EV-056, EV-066
  - Verification: QSA sign-off on the revised 12.4, plus a Vault SAD test showing no CVC is present after the payment leaves AUTHORISING.
- Next step: PCI compliance lead with QSA: Obtain a written QSA ruling on keeping SAD after authorization for cascades and incremental authorizations.
- Decision AD-009 (24 CVC handling): refines. Retention may be shortened to the end of the authorization if the QSA rejects the §12.4 reading; the PCI premise is not yet verified, so the decision is not challenged at this point.
- Decision AD-030 (NFR-6): refines. NFR-6 wording would be aligned with whatever SAD rule the QSA confirms.
- Decision AD-029 (NFR-5): preserves. The aim is to protect the Level 1 assessment.

### FND-037 RPO of zero is not achievable with asynchronous Aurora Global replication, and idempotency state is lost on failover

- **risk** · internal contradiction · severity **high** · confidence 0.80 (high) · rank 5
- Disposition: **governance decision** (also: refinement now)

NFR-4 requires zero data loss for authorized payments and ledger postings on loss of a region, but Section 20.2 uses asynchronous replication with lag 'typically under one second'. Payments authorized at the acquirer during that window will be missing from the ledger. DynamoDB idempotency records are recreated empty and 'reconstructed from the payment table', but the payment table schema (Section 19) has no idempotency_key column. Merchant retries after failover would therefore create new payments and duplicate charges, which breaks FR-5.

- Where: p.3 §2.2 (NFR-4): "Recovery point objective for authorized payments and ledger postings shall be zero, including on loss of an entire AWS region."
- Where: p.16 §20.2 (NFR-4): "and asynchronous, with typical lag under one second."
- Where: p.17 §20.2 (FR-5): "in-flight idempotency state is reconstructed from the payment table."
- Evidence EV-006 (doc, supports): "Recovery point objective for authorized payments and ledger postings shall be zero, including on loss of an entire AWS region." [doc:DOC-design_v1#p3/s2.2]
- Evidence EV-079 (doc, supports): "and asynchronous, with typical lag under one second." [doc:DOC-design_v1#p16/s20.2]
- Evidence EV-080 (doc, supports): "in-flight idempotency state is reconstructed from the payment table." [doc:DOC-design_v1#p17/s20.2]
- Evidence EV-102 (inference, supports): "Asynchronous replication with non-zero lag cannot guarantee RPO zero, and the payment table defined in Section 19 has no idempotency_key or merchant key column from which to rebuild the dedup state." [inference:EV-102] derived from EV-006, EV-079, EV-080
- Evidence EV-007 (doc, supports): "Replication is storagelevel and asynchronous, with typical lag under one second." [doc:DOC-design_v1#p16/s20.2]
- Evidence EV-067 (inference, supports): "With asynchronous replication, the RPO on region loss equals the replication lag at the time of failure (about 1 s, roughly 2,000 payments at peak), not zero." [inference:EV-067] derived from EV-006, EV-007
- Evidence EV-051 (inference, supports): "Asynchronous replication with non-zero lag means commits inside the lag window are lost on regional loss. The §19 payment table has no idempotency_key column, so the claimed reconstruction has no data to work from." [inference:EV-051] derived from EV-006, EV-007, EV-029
- Recommendation: Either restate NFR-4 as RPO ≤ N seconds, with a post-failover reconciliation that rebuilds missing payments from acquirer records, or adopt synchronous cross-region commit for authorization records and accept the latency cost (a governance trade-off). Add idempotency_key and request_hash to the payment table so dedup state can be rebuilt, and define how failover handles in-flight AUTHORISING payments.
  - Issue: The RPO target and the replication mechanism contradict each other, and idempotency reconstruction has no data source.
  - Rationale: Lost postings for approved authorizations leave money unaccounted for, and lost dedup state causes duplicate charges.
  - Expected benefit: Gives an honest, achievable NFR-4 and preserves FR-5 across failover. (objectives: NFR-4, FR-5, FR-10)
  - Supporting evidence: EV-006, EV-079, EV-080
  - Verification: In the NFR-4 game day, inject writes during failover and check that merchant retries with the same key after failover return the original payment.
- Next step: Platform Engineering lead with Finance Operations: Decide whether to accept a non-zero RPO with a compensating reconciliation, or to pay for synchronous replication; update NFR-4 and 20.2.
- Decision AD-048 (NFR-4): challenges. Explicit challenge: the design's own statement that replication is asynchronous (EV-007, EV-079) means NFR-4's zero RPO on region loss cannot be met as written.
- Decision AD-004 (24 Disaster recovery): refines. Option (a) keeps Aurora Global DR and adds post-failover reconciliation; option (b) adds synchronous commit on top of it.
- Decision AD-006 (24 Idempotency store): preserves. The idempotency store is unchanged; idempotency_key is added to payment so dedup state can be rebuilt after failover.
- Decision AD-037 (FR-5): preserves. Keeps FR-5 holding across failover.

### FND-036 Single CloudHSM in one AZ is a single point of failure for all card payments; the CDE has no regional DR path

- **risk** · scalability or failure mode · severity **high** · confidence 0.80 (high) · rank 6
- Disposition: **refinement now** (also: needs prototyping)

All tokenise, detokenise and fingerprint operations depend on one HSM in ap-southeast-1a, and DEKs are not cached, so every card authorization needs that HSM. Losing the AZ or the HSM stops all card payments until a new HSM is restored from backup. Mapping the resulting 503 to 'retryable' only makes it cascade into the same failure. The regional failover runbook covers Aurora, EKS and Route 53 but not the CDE (Vault data, HSM, Card Adapter), so card payments cannot run after a regional failover. This puts NFR-3 (99.95%) and NFR-4 (RTO 30 min) at risk for about 55% of traffic.

- Where: p.10 §12.3 (NFR-3): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a."
- Where: p.10 §12.1: "DEKs are not cached, so plaintext key material never persists in application memory."
- Where: p.17 §20.2 (NFR-4): "Regional failover is a runbook-driven managed operation (promote the Aurora secondary, scale up the standby"
- Evidence EV-030 (doc, supports): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a." [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-076 (doc, supports): "If the HSM is unreachable, the Vault returns HTTP 503 and the Card Adapter maps this to a retryable outcome." [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-077 (doc, supports): "Regional failover is a runbook-driven managed operation (promote the Aurora secondary, scale up the standby" [doc:DOC-design_v1#p17/s20.2]
- Evidence EV-078 (doc, supports): "A second HSM will be added to the cluster when sustained card volume exceeds 1,500 TPS." [doc:DOC-design_v1#p10/s12.3]
- Evidence EV-101 (inference, supports): "A 99.95% monthly target allows about 22 minutes of downtime; restoring an HSM from backup after an AZ loss, plus the absence of any cross-region CDE, can use up that budget in a single incident." [inference:EV-101] derived from EV-030, EV-076, EV-077
- Evidence EV-031 (doc, supports): "Every service runs at least three replicas spread across three AZs." [doc:DOC-design_v1#p16/s20.1]
- Evidence EV-060 (doc, supports): "inside the HSM; DEKs are not cached, so plaintext key material never persists in application memory." [doc:DOC-design_v1#p10/s12.1]
- Evidence EV-052 (inference, supports): "All card detokenisation depends on the one HSM, and §20 has no CDE recovery steps. An AZ or region loss therefore halts card payments (55% of attempts) for longer than the NFR-3 monthly downtime allowance or the NFR-4 RTO." [inference:EV-052] derived from EV-030, EV-031, EV-032
- Recommendation: In 12.3 and Section 24, start with at least two HSMs in different AZs at launch and size HSM throughput for peak card TPS × HSM operations per payment (tokenise, fingerprint, detokenise per attempt). In 20.2, add CDE regional DR: a replicated vault store, a CloudHSM cluster in ap-southeast-3, and a standby Card Adapter. Classify Vault 503 as a platform error that is not cascaded.
  - Issue: The card path has a single-AZ HSM dependency, and the CDE has no DR.
  - Rationale: Every other tier is deployed across three AZs; the HSM sets the availability ceiling for card payments.
  - Expected benefit: Makes NFR-3 and NFR-4 achievable for card payments. (objectives: NFR-3, NFR-4, NFR-1)
  - Supporting evidence: EV-030, EV-076, EV-077, EV-078
  - Verification: Chaos test: kill the 1a HSM under NFR-1 load and confirm card authorizations continue. The DR game day must include card authorizations in ap-southeast-3.
- Decision AD-008 (24 Vault): challenges. Explicit challenge to one HSM at launch: one HSM in one AZ (EV-030), uncached DEKs (EV-060) and the absence of any CDE DR step (EV-077) put the whole card path at odds with NFR-3.
- Decision AD-028 (12.3 HSM topology): refines. Replaces the 1,500 TPS scale-out trigger with multi-AZ HSMs from launch.
- Decision AD-004 (24 Disaster recovery): refines. Extends the regional failover runbook to cover the Vault, the HSM and the Card Adapter.
- Decision AD-002 (24 Compute): preserves. The separate CDE cluster and account are kept.
- Decision AD-047 (NFR-3): preserves. The aim is to make NFR-3 achievable for card payments.

### FND-010 First cohort goes live before the Fraud Hook is built, contradicting FR-9

- **risk** · internal contradiction · severity **high** · confidence 0.85 (high) · rank 7
- Disposition: **governance decision** (also: refinement now)

§28 puts the Fraud Hook in Phase 8 and depends on the unsigned FRV-1 contract, yet the first cohort (Singapore cards) goes live after Phase 7. FR-9 requires every card payment to be scored before authorization. §27's overall conclusion names only the Admin API schemas and disputes as material gaps, so launch without fraud scoring is neither acknowledged nor risk-accepted.

- Where: p.21 §28 (FR-9): "The first merchant cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week"
- Where: p.21 §28: "8 Fraud Hook (FRV-1) Yes - vendor contract (Backlog item 4)"
- Where: p.2 §2.1 (FR-9): "Every card payment and every e-wallet payment above the merchant's configured threshold shall be scored by the fraud-scoring hook"
- Evidence EV-023 (doc, supports): "The first merchant cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week" [doc:DOC-design_v1#p21/s28]
- Evidence EV-024 (doc, supports): "8 Fraud Hook (FRV-1) Yes - vendor contract (Backlog item 4)" [doc:DOC-design_v1#p21/s28]
- Evidence EV-025 (doc, supports): "The Admin API schemas and the dispute module are the two" [doc:DOC-design_v1#p21/s27]
- Recommendation: Either move the Fraud Hook ahead of go-live in §28 and gate it on Backlog item 4, or define an interim control (rules-only scoring, or a different vendor) and record an explicit risk acceptance. Update the §27 overall conclusion to match.
  - Issue: The phase plan launches card acceptance without the fraud scoring that FR-9 mandates.
  - Rationale: Unscored live card traffic exposes the business to fraud losses and breaks FR-9.
  - Expected benefit: FR-9 is met at go-live, or a deliberate, owned risk acceptance replaces it. (objectives: FR-9)
  - Supporting evidence: EV-023, EV-024, EV-025
  - Verification: The go-live checklist requires FR-9 acceptance tests to pass, or a signed risk acceptance.
- Next step: Head of Risk and Programme lead: Decide the go-live fraud control and resequence the build phases.
- Decision AD-035 (28 Build Phases): refines. The go-live sequence either brings the Fraud Hook forward or adds an interim control with a recorded risk acceptance.
- Decision AD-023 (25 Backlog item 4): refines. Makes the FRV-1 contract a gate for go-live.
- Decision AD-040 (FR-9): preserves. Aims to have FR-9 met at launch.

### FND-009 Latency budget excludes cascades on a premise contradicted by the 3.8% retryable rate

- **risk** · internal contradiction · severity **high** · confidence 0.80 (high) · rank 8
- Disposition: **refinement now** (also: needs prototyping)

§21.1 says cascades sit above p99 because fewer than 1% of card payments cascade. §10.5 gives 3.8% retryable outcomes, and §11.2 cascades every one of them, so the cascade path lies inside the p99 population. A single timed-out attempt takes 2,500 ms, which already exceeds the 1,500 ms in NFR-2, and NFR-2 explicitly includes 'any cascade'. The NFR-2 benchmark injects exactly 3.8% retryables, so built as written it should fail.

- Where: p.17 §21.1 (NFR-2): "move the p99 because fewer than 1% of card payments cascade; the cascade path therefore sits above the 99th"
- Where: p.9 §10.5 (FR-7): "retryable outcomes - soft declines eligible for reattempt plus acquirer-side errors and timeouts - 3.8%."
- Where: p.3 §2.2 (NFR-2): "End-to-end p99 latency for a card authorization, measured at the API edge and including any cascade, shall not exceed 1,500 ms."
- Evidence EV-022 (doc, supports): "move the p99 because fewer than 1% of card payments cascade; the cascade path therefore sits above the 99th" [doc:DOC-design_v1#p17/s21.1]
- Evidence EV-008 (doc, supports): "retryable outcomes - soft declines eligible for reattempt plus acquirer-side errors and timeouts - 3.8%." [doc:DOC-design_v1#p9/s10.5]
- Evidence EV-009 (doc, supports): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms" [doc:DOC-design_v1#p9/s11.1]
- Evidence EV-049 (inference, supports): "If 3.8% of first attempts are retryable and all of them cascade, about 3.8% of payments take two or more acquirer round trips. That puts cascades well inside the slowest 1%, and any timeout-triggered cascade exceeds 2,500 ms on its own." [inference:EV-049] derived from EV-022, EV-008, EV-009
- Evidence EV-084 (doc, supports): "Cascading does not move the p99 because fewer than 1% of card payments cascade; the cascade path therefore sits above the 99th percentile." [doc:DOC-design_v1#p17/s21.1]
- Evidence EV-016 (inference, supports): "With 3.8% of attempts retryable, the top 1% of latencies includes cascade paths. Any timeout-triggered cascade takes over 2,500 ms, so p99 exceeds 1,500 ms whenever timeouts make up more than about 1% of attempts." [inference:EV-016] derived from EV-008, EV-009
- Recommendation: In §21.1, budget the cascade path explicitly. Either add an overall authorization deadline (for example, no new attempt once remaining budget is below the slowest acquirer p95) with a per-attempt timeout well under 2,500 ms, or restate NFR-2 as a non-cascade p99 plus a separate cascade-inclusive p99.9 target. Then align §11.1, §11.2 and §24.
  - Issue: NFR-2 does not hold with cascades included, and the timeout and cascade limits are not tied to the latency budget.
  - Rationale: The document's own figures contradict the exclusion premise.
  - Expected benefit: NFR-2 becomes achievable and verifiable, or is restated honestly. (objectives: NFR-2, FR-7)
  - Supporting evidence: EV-022, EV-008, EV-009, EV-049
  - Verification: NFR-2 benchmark with 3.8% retryable injection, including timeout-class retryables, meets the restated budget.
- Next step: Payments Core architect: Model the latency distribution with cascades from 2025 attempt data and set the deadline and timeout values.
- Decision AD-011 (24 Cascade policy): refines. Ties the 2,500 ms per-attempt timeout and the cascade limit to an overall latency deadline.
- Decision AD-046 (NFR-2): preserves. Aims to make NFR-2 achievable, or to restate it openly.
- Decision AD-038 (FR-7): preserves. Cascading on retryable outcomes is kept.

### FND-040 Reconciliation that waits for all files cannot publish reports by 08:00 SGT

- **risk** · scalability or failure mode · severity **high** · confidence 0.80 (high) · rank 11
- Disposition: **refinement now** (also: governance decision)

The batch matcher waits for every expected file, and ACQ-TH1 delivers at 06:30 ICT (07:30 SGT). Adding the measured 45-minute match and the 15-minute report generation, both at 2025 volume, gives about 08:30 SGT before any growth to 2027 volume. NFR-8 is therefore missed every day, and one late or missing file blocks reconciliation and payouts for all merchants. No late-file handling or partial-run policy is defined.

- Where: p.13 §16.2 (NFR-8): "The batch matcher starts once all expected files for business day T have been received"
- Where: p.12 §16.1: "ACQ-TH1 CSV over SFTP Daily 06:30 ICT ACQ-PH1"
- Where: p.13 §16.2 (NFR-8): "the matcher's measured end-to-end run time is 45 minutes"
- Evidence EV-085 (doc, supports): "The batch matcher starts once all expected files for business day T have been received" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-010 (doc, supports): "ACQ-TH1 CSV over SFTP Daily 06:30 ICT" [doc:DOC-design_v1#p12/s16.1]
- Evidence EV-086 (doc, supports): "the matcher's measured end-to-end run time is 45 minutes" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-105 (inference, supports): "06:30 ICT = 07:30 SGT; 07:30 + 45 min + 15 min = 08:30 SGT at 2025 volume, already 30 minutes past the NFR-8 deadline before volume doubles." [inference:EV-105] derived from EV-085, EV-010, EV-086
- Evidence EV-011 (doc, supports): "the matcher's measured end-to-end run time is 45 minutes, and merchant settlement report generation takes a further" [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-012 (doc, supports): "Payment attempts per day (average) 5.1 M 10.5 M" [doc:DOC-design_v1#p2/s1]
- Evidence EV-017 (inference, supports): "06:30 ICT is 07:30 SGT; adding 45 and 15 minutes gives 08:30 SGT at 2025 volume, and the 2027 volume is about twice as large." [inference:EV-017] derived from EV-010, EV-011, EV-012
- Recommendation: In 16.2, match each provider's file incrementally as it arrives, and run cross-provider netting and the report as a final step. Define a cutoff with partial reports and a late-file policy. Agree with an accountable owner whether ACQ-TH1's timing makes NFR-8 renegotiable.
  - Issue: Gating on all files, plus the latest file's arrival time, makes NFR-8 impossible to meet.
  - Rationale: The arithmetic from the design's own figures misses the deadline.
  - Expected benefit: Meets NFR-8 and isolates late providers. (objectives: NFR-8, FR-11, FR-17)
  - Supporting evidence: EV-085, EV-010, EV-086
  - Verification: Replay a production-volume day for 2027 with real arrival times and confirm reports are published by 08:00 SGT; also test with one file withheld.
- Next step: Finance Operations lead: Approve the late-file and partial-report policy.
- Decision AD-016 (24 Reconciliation): refines. Keeps daily three-way matching but runs it per provider as each file arrives, leaving only netting until all files are in.
- Decision AD-049 (NFR-8): preserves. Aims to make NFR-8 achievable.
- Decision AD-042 (FR-11): preserves. The three-way match is unchanged.

## Gaps

### FND-041 Payout bank account changes lack step-up MFA, second approval, and out-of-band notice

- **gap** · security privacy gap · severity **high** · confidence 0.75 (medium) · rank 9
- Disposition: **refinement now**

A Finance user can change the payout bank account with only a password, because MFA is optional for every role except Owner. The only confirmation goes to the user who made the change, so an attacker who takes over a Finance account can redirect a merchant's payouts without the Owner being told. This conflicts with P9 (money-moving separation of duties) and creates a direct financial-loss path that the back-office console is protected against (JIT plus second approver) but the merchant plane is not.

- Where: p.14 §18.4 (FR-13): "A confirmation email is sent to the user who made the change, and the change is written to the audit log."
- Where: p.14 §18.3: "TOTP multi-factor authentication is available to every user and is enforced for the Owner role at first login."
- Where: p.14 §18.2 (FR-13): "Finance Issue refunds; view and export reports; edit payout bank account"
- Evidence EV-087 (doc, supports): "A confirmation email is sent to the user who made the change, and the change is written to the audit log." [doc:DOC-design_v1#p14/s18.4]
- Evidence EV-088 (doc, supports): "TOTP multi-factor authentication is available to every user and is enforced for the Owner role at first login." [doc:DOC-design_v1#p14/s18.3]
- Evidence EV-089 (doc, supports): "Finance Issue refunds; view and export reports; edit payout bank account" [doc:DOC-design_v1#p14/s18.2]
- Recommendation: In 18.3 and 18.4, require MFA for the Finance, Admin and Owner roles. Require step-up re-authentication plus a second approver (Owner) for payout account changes, notify all Owners out of band, verify the new account by name check or penny test (verified_at), and hold the first payout to the new account for a cooling-off period.
  - Issue: The highest-value merchant-side action is protected by a password only.
  - Rationale: P9 requires separation of money-moving permissions.
  - Expected benefit: Reduces the risk of payout diversion (FR-13, FR-17). (objectives: FR-13, FR-17, P9)
  - Supporting evidence: EV-087, EV-088, EV-089
  - Verification: Extend the FR-13 role-matrix test: a payout account change without step-up and approval is rejected, and Owners receive a notification.
- Decision AD-018 (24 Merchant user MFA): challenges. Explicit challenge: optional MFA for Finance users (EV-088, EV-089), plus a confirmation sent only to the acting user (EV-087), leaves payout diversion protected by a password alone, contrary to P9.
- Decision AD-019 (24 Back-office access): preserves. Brings the merchant plane up to the back-office second-approver pattern.

### FND-011 State machine lacks transitions that the documented flows require (FR-2)

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.75 (medium) · rank 12
- Disposition: **refinement now**

FR-2 allows only the transitions in §7.2, but the documented flows need others. (a) A wallet or bank notification and a failed 3DS challenge both start from REQUIRES_ACTION, which can only move to AUTHORISING or CANCELLED, so it cannot reach FAILED or SUCCEEDED directly. (b) A refund before settlement moves CAPTURED to PARTIALLY_REFUNDED, but nothing allows PARTIALLY_REFUNDED to move to SETTLED, so the reconciliation transition in §16.2 and the CVC deletion triggered at SETTLED cannot happen. (c) Multiple partial captures (FR-1) have no CAPTURED-to-CAPTURED transition. (d) The REVIEW option 'authorize-and-hold-capture' has no state of its own. Section 27 rates this component 'Ready', but engineers would have to invent these rules.

- Where: p.2 §2.1 (FR-2): "Every payment shall be in exactly one state of the state machine in Section 7 at any time; only the transitions listed there shall be"
- Where: p.7 §8 (FR-3): "moves to REQUIRES_ACTION, and the provider's signed asynchronous notification, deduplicated on the provider's"
- Where: p.13 §16.2 (FR-11): "Matched payments transition to SETTLED and a settlement journal is posted."
- Evidence EV-026 (doc, supports): "REQUIRES_ACTION -> AUTHORISING | CANCELLED (expiry)" [doc:DOC-design_v1#p6/s7.2]
- Evidence EV-027 (doc, supports): "PARTIALLY_REFUNDED -> REFUNDED" [doc:DOC-design_v1#p6/s7.2]
- Evidence EV-028 (doc, supports): "Matched payments transition to SETTLED and a settlement journal is posted." [doc:DOC-design_v1#p13/s16.2]
- Evidence EV-050 (inference, supports): "A payment refunded before its settlement line arrives cannot legally reach SETTLED. Reconciliation would therefore fail the transition, and the CVC deletion keyed on SETTLED falls back to the 72-hour timer." [inference:EV-050] derived from EV-027, EV-028
- Recommendation: In §7.2, add REQUIRES_ACTION to FAILED and to SUCCEEDED (or state that notifications go through AUTHORISING). Track settlement as a separate attribute, or allow PARTIALLY_REFUNDED and REFUNDED to move to SETTLED. Define how multiple partial captures are represented, define a hold state or flag for REVIEW, and add refund-in-progress handling for payout-based refunds. Extend the FR-2 property test to drive every flow in §8, §11 and §16.
  - Issue: The §7.2 transitions are incomplete for wallet/3DS failures, refund-before-settlement, multiple captures and fraud review holds.
  - Rationale: FR-2 forbids unlisted transitions, so the flows in §8, §11.4 and §16.2 cannot be implemented as written.
  - Expected benefit: FR-1, FR-2, FR-11 and FR-15 can all be implemented consistently. (objectives: FR-1, FR-2, FR-11, FR-15)
  - Supporting evidence: EV-026, EV-027, EV-028, EV-050
  - Verification: The FR-2 property test runs scenario sequences derived from §8 and §16 with no rejected transitions.
- Decision AD-036 (FR-2): refines. Adds the missing transitions to the §7.2 list that FR-2 makes binding.
- Decision AD-016 (24 Reconciliation): preserves. Lets reconciliation mark refunded payments as settled.

### FND-043 Stuck-sweeper does not recover idempotency locks left before AUTHORISING

- **gap** · scalability or failure mode · severity **medium** · confidence 0.70 (medium) · rank 13
- Disposition: **refinement now**

Section 9.2 relies on the stuck-payment sweeper to release IN_PROGRESS locks left by crashed pods. But the sweeper only scans payments in AUTHORISING, and the lock is taken before the payment record exists (step 3 versus step 4), with no link from a lock to a payment. A crash before AUTHORISING, or before the payment is created, leaves the merchant receiving 409 for up to 24 hours, which blocks retries of a payment that never happened.

- Where: p.8 §9.2 (FR-5): "A lock left IN_PROGRESS by a crashed API pod is recovered by the Orchestrator's stuck-payment sweeper"
- Where: p.17 §20.3: "Every 60 seconds, the Orchestrator's sweeper finds payments in AUTHORISING for more than 30 seconds"
- Evidence EV-092 (doc, supports): "A lock left IN_PROGRESS by a crashed API pod is recovered by the Orchestrator's stuck-payment sweeper" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-093 (doc, supports): "Every 60 seconds, the Orchestrator's sweeper finds payments in AUTHORISING for more than 30 seconds" [doc:DOC-design_v1#p17/s20.3]
- Evidence EV-107 (inference, supports): "A lock acquired at step 3 with no payment yet, or with the payment in CREATED or REQUIRES_ACTION, is never picked up by a sweeper that scans only AUTHORISING payments." [inference:EV-107] derived from EV-092, EV-093
- Evidence EV-044 (doc, supports): "A lock left IN_PROGRESS by a crashed API pod is recovered by the Orchestrator's stuck-payment sweeper (Section" [doc:DOC-design_v1#p8/s9.2]
- Recommendation: In 9.2 and 20.3, add a lease expiry (locked_until) to IN_PROGRESS items, and have the sweeper scan the idempotency table by age. If no payment exists, delete the lock; if a payment exists in CREATED, resume or fail it.
  - Issue: Orphaned idempotency locks have no recovery path.
  - Rationale: FR-5 assumes in-flight states eventually resolve.
  - Expected benefit: Merchants can safely retry after a crash (FR-5, NFR-3). (objectives: FR-5, NFR-3)
  - Supporting evidence: EV-092, EV-093
  - Verification: Fault-injection test: kill the pod at steps 3, 4 and 5; a retry with the same key succeeds within the lease period.
- Decision AD-006 (24 Idempotency store): preserves. Adds a lease field to the existing table without changing the key design.
- Decision AD-037 (FR-5): preserves. Lets FR-5 retries recover after a crash.

## Ambiguities

### FND-017 FR-8 '2%' tolerance is undefined in unit and basis, and its test cannot verify it

- **ambiguity** · ambiguous requirement · severity **medium** · confidence 0.70 (medium) · rank 19
- Disposition: **refinement now**

FR-8 caps the expected authorization-rate reduction at 2%, while §10.3 uses a tolerance of 'default 2', which could mean 2 percentage points or 2% relative. §10.2 ranks acquirers by a weighted score whose default emphasises cost, which can pick an acquirer FR-8 forbids. §10.3 also mixes a per-transaction prior comparison with a weekly realised-rate review. The FR-8 test only checks that the chosen acquirer matches an expected choice, so it never checks the 2% bound.

- Where: p.2 §2.1 (FR-8): "For each transaction, the Routing Engine shall prefer the lowest-cost eligible acquirer unless doing so reduces the expected"
- Where: p.9 §10.3 (FR-8): "acquirer against that of the highest-approval acquirer and applies the cost preference when the difference is within the"
- Where: p.19 §26.1 (FR-8): "For a set of synthetic transactions with configured costs and approval priors, the selected acquirer matches the"
- Evidence EV-040 (doc, supports): "configured tolerance (default 2). Separately, the weekly Routing Review compares each merchant's realised" [doc:DOC-design_v1#p9/s10.3]
- Evidence EV-041 (doc, supports): "falling back to coarser cells when the sample is under 500 attempts. Weights are configured per merchant account; the" [doc:DOC-design_v1#p9/s10.2]
- Recommendation: Define the FR-8 tolerance as percentage points (or relative) on approval_prior. Make the §10.3 check a hard constraint applied after the §10.2 scoring. Add FR-8 test cases at 1.9, 2.0 and 2.1 points.
  - Issue: The FR-8 bound has two readings, and the weighted score is not shown to respect it.
  - Rationale: Read one way or the other, the threshold changes routing decisions and merchant approval rates.
  - Expected benefit: FR-8 becomes implementable and verifiable. (objectives: FR-8)
  - Supporting evidence: EV-040, EV-041
  - Verification: Boundary test cases pass under the defined unit.
- Decision AD-012 (24 Routing): refines. Defines the unit of the 'tolerance of 2' and makes the FR-8 check a hard constraint after scoring.
- Decision AD-039 (FR-8): refines. Makes the FR-8 bound unambiguous and testable.

## Unresolved assumptions

### FND-027 Network tokens 'from launch' depend on a TRID application not yet submitted

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.85 (high) · rank 15
- Disposition: **governance decision** (also: refinement now) · already acknowledged in the document

Network tokens are confirmed as the primary card-on-file credential from launch, and Phase 3 is marked 'No - ready'. Token Requestor registration, the TSP agreement and certification have not been started (Backlog 2). Because these have external lead times, either FR-14 is unmet at go-live or Phase 3 is blocked. The review adds that the dependency is on the critical path for the first cohort, yet Section 27 and Section 28 do not show it.

- Where: p.19 §25: "the commercial agreement with a token service provider; certification test plan. Application not yet submitted."
- Where: p.18 §24 (FR-14): "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch; PAN"
- Where: p.21 §28: "Transaction core - Payments API, idempotency, state machine, ledger, outbox; card-on-file"
- Evidence EV-035 (doc, supports): "the commercial agreement with a token service provider; certification test plan. Application not yet submitted." [doc:DOC-design_v1#p19/s25]
- Evidence EV-036 (doc, supports): "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch; PAN" [doc:DOC-design_v1#p18/s24]
- Recommendation: Mark Phase 3 card-on-file as 'Partially - Backlog item 2'. Add a dated TRID milestone with an owner. Define an interim PAN-based stored-credential mode (with MIT/CIT indicators) in 12.5 for launch.
  - Issue: A confirmed decision and a 'ready' build phase depend on an external approval that has not been started.
  - Rationale: Scheme onboarding has lead times outside the team's control.
  - Expected benefit: A predictable go-live for FR-14 card-on-file. (objectives: FR-14)
  - Supporting evidence: EV-035, EV-036
  - Verification: TRID issued and certification passed before Phase 3 exit, or the interim mode passes the FR-14 test.
- Next step: Product owner, card partnerships: Submit the VTS/MDES token-requestor applications and publish the expected certification date.
- Decision AD-010 (24 Card-on-file credential): refines. Adds an interim PAN stored-credential mode until token-requestor certification is complete.
- Decision AD-021 (25 Backlog item 2): refines. Asks for an owner and a date for the pending TRID application.
- Decision AD-044 (FR-14): preserves. FR-14 already allows PAN where network tokens are unsupported.

### FND-030 Single-region Singapore data placement assumed compliant with all five markets' rules

- **unresolved assumption** · missing or unverifiable requirement · severity **medium** · confidence 0.50 (medium) · rank 17
- Disposition: **needs investigation**

All primary data, including Indonesian, Thai and Philippine payment and personal data, is stored and processed in Singapore. Yet NFR-7 claims compliance with every market's data protection law, and the document has no analysis of cross-border transfer or local-processing rules (for example central-bank payment-data localisation in Indonesia). This is unverified here. If localisation applies, the confirmed single-region decision does not hold for at least one market.

- Where: p.16 §19.1: "All primary data stores (Aurora, DynamoDB, ElastiCache, MSK, S3 intake and archive buckets) are in ap-southeast-1."
- Where: p.3 §2.2 (NFR-7): "Personal data shall be processed in accordance with the personal data protection laws of each market of operation (Singapore"
- Evidence EV-061 (doc, supports): "All primary data stores (Aurora, DynamoDB, ElastiCache, MSK, S3 intake and archive buckets) are in ap-southeast-1." [doc:DOC-design_v1#p16/s19.1]
- Evidence EV-062 (doc, supports): "Personal data shall be processed in accordance with the personal data protection laws of each market of operation (Singapore" [doc:DOC-design_v1#p3/s2.2]
- Recommendation: Add a per-market data-residency assessment to NFR-7 and Section 19.1, covering payment-system regulator rules as well as privacy laws, with legal sign-off before Phase 1 infrastructure is fixed.
  - Issue: Cross-border data and payment-data localisation rules are not assessed.
  - Rationale: Market licences may make local processing a condition, which would affect the region decision.
  - Expected benefit: NFR-7 compliance and a lawful operation in all markets. (objectives: NFR-7)
  - Supporting evidence: EV-061, EV-062
  - Verification: Legal opinion per market recorded alongside the NFR-7 DPO sign-off.
- Next step: Legal / DPO: Obtain localisation and cross-border transfer opinions for ID, TH, PH and MY.
- Decision AD-001 (24 Cloud and primary region): preserves. The single-region decision stands until the legal opinions are in; no challenge without evidence.
- Decision AD-031 (NFR-7): preserves. Aims to show NFR-7 compliance.

### FND-044 Fraud fail-open policy has no owner, no exposure cap, and no monitoring

- **unresolved assumption** · other · severity **medium** · confidence 0.65 (medium) · rank 18
- Disposition: **governance decision** · already acknowledged in the document

When FRV-1 times out or fails, LOW and MEDIUM risk-tier merchants (the majority) get ACCEPT. A vendor outage during a 12.12 campaign would therefore let all card traffic through unscored. P8 allows degrading to defaults, but the document names no risk owner who accepts this fraud exposure, no fallback-rate alert, and no cap or time limit. The FRV-1 SLA is also still pending (Backlog item 4).

- Where: p.11 §13.2 (FR-9): "On timeout or vendor error: LOW and MEDIUM risk-tier merchants receive ACCEPT; HIGH risk-tier merchants receive REVIEW."
- Where: p.19 §25: "FRV-1 contract - data processing agreement and SLA finalisation."
- Evidence EV-094 (doc, supports): "On timeout or vendor error: LOW and MEDIUM risk-tier merchants receive ACCEPT; HIGH risk-tier merchants receive REVIEW." [doc:DOC-design_v1#p11/s13.2]
- Evidence EV-073 (doc, supports): "FRV-1 contract - data processing agreement and SLA finalisation." [doc:DOC-design_v1#p19/s25]
- Recommendation: In 13.2, name the risk owner, alert when the fallback rate exceeds a threshold, and switch to REVIEW or amount-capped ACCEPT after N minutes of vendor outage. Add the fallback rate to the FRV-1 SLA.
  - Issue: Fail-open fraud behaviour is an unowned risk acceptance.
  - Rationale: Fraud losses during a vendor outage fall on Serindit Pay or its merchants.
  - Expected benefit: Bounded fraud exposure and an accountable decision (FR-9). (objectives: FR-9, P8)
  - Supporting evidence: EV-094, EV-073
  - Verification: Extend the FR-9 test: a sustained vendor outage triggers the alert and the policy switch.
- Next step: Head of Risk: Approve the fail-open policy, its exposure cap and the escalation path.
- Decision AD-013 (24 Fraud): refines. Keeps the risk-tier fallback but adds an owner, a fallback-rate alert and an exposure cap.
- Decision AD-023 (25 Backlog item 4): refines. Adds a fallback-rate term to the pending FRV-1 SLA.

## Validation needs

### FND-038 DynamoDB idempotency capacity for the largest merchant rests on an unverified per-partition figure and leaves out LSI effects

- **validation need** · scalability or failure mode · severity **high** · confidence 0.65 (medium) · rank 10
- Disposition: **needs investigation** (also: needs prototyping)

Section 9.3 assumes a single partition sustains 10,000 WCU/s and counts 1,800 WCU for M-0001, but items carry up to a 4 KB response body plus the LSI write, so each request consumes more than two WCU. A table with an LSI also limits the total data stored per partition key value. At 900 TPS with 24-hour retention, M-0001 would accumulate tens of millions of items per day under one partition key. The per-partition throughput figure and the LSI item-collection limit both need checking against current DynamoDB quotas; if either fails, idempotency for the 45% merchant breaks at peak, which breaks NFR-1 and FR-5.

- Where: p.8 §9.3 (NFR-1): "a single partition sustains up to 10,000 write capacity units per second."
- Where: p.8 §9.3 (NFR-1): "two writes - lock acquisition and completion update - or about 1,800 WCU at peak"
- Where: p.8 §9.2: "response_body String Serialised response, up to 4 KB"
- Evidence EV-081 (doc, supports): "a single partition sustains up to 10,000 write capacity units per second." [doc:DOC-design_v1#p8/s9.3]
- Evidence EV-082 (doc, supports): "two writes - lock acquisition and completion update - or about 1,800 WCU at peak" [doc:DOC-design_v1#p8/s9.3]
- Evidence EV-083 (doc, supports): "response_body String Serialised response, up to 4 KB" [doc:DOC-design_v1#p8/s9.2]
- Evidence EV-103 (inference, supports): "900 TPS × 86,400 s ≈ 78 million items per day for one partition key, each up to about 4 KB, plus LSI writes; both the WCU arithmetic and the per-key data volume are well beyond what the section accounts for." [inference:EV-103] derived from EV-081, EV-082, EV-083
- Evidence EV-068 (inference, supports): "At 45% of ~10.5 M daily attempts, M-0001 holds several million items of roughly 4-5 KB within the 24 h TTL window under a single partition key with an LSI; both the WCU cost per completion write and the item-collection size need checking against current DynamoDB limits." [inference:EV-068] derived from EV-057, EV-058
- Recommendation: Check the per-partition throughput and LSI item-collection limits against current DynamoDB quotas. Change the key to a high-cardinality partition key (merchant_id#idempotency_key), move the 'recent requests by merchant' view to a GSI or the payment table, and recompute WCU including item size and index writes in 9.3.
  - Issue: The hot-key capacity calculation for M-0001 is unverified and incomplete.
  - Rationale: One merchant is 45% of peak traffic, and an idempotency write failure blocks payment creation.
  - Expected benefit: Ensures NFR-1 and FR-5 hold for the largest merchant at campaign peaks. (objectives: NFR-1, FR-5)
  - Supporting evidence: EV-081, EV-082, EV-083
  - Verification: Load test with 45% of 2,000 TPS on one merchant_id for four hours, with zero throttled writes.
- Next step: Payments Core tech lead: Confirm the DynamoDB partition and LSI quotas and prototype the hot-key load before Phase 3 is marked ready.
- Decision AD-006 (24 Idempotency store): refines. May change the DynamoDB partition key and replace the LSI with a GSI if the limits are confirmed.
- Decision AD-045 (NFR-1): preserves. Aims to protect NFR-1 for the largest merchant.
- Decision AD-037 (FR-5): preserves. Idempotency correctness is unaffected.

### FND-016 FR-5 concurrency clause contradicts the 409 contract and is untested

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.80 (high) · rank 14
- Disposition: **refinement now** (also: needs testing)

FR-5 requires the identical response even when duplicates arrive concurrently, but §9.1 returns HTTP 409 to a concurrent duplicate. The FR-5 acceptance test only replays after the first response arrives, so it never exercises the concurrent case, the DynamoDB race, or the fast path behaviour raised in FND-001.

- Where: p.2 §2.1 (FR-5): "downstream provider, and shall return the identical response, including when duplicate requests arrive concurrently."
- Where: p.7 §9.1 (FR-5): "While the first request is in flight, a duplicate receives HTTP 409 request_in_progress with Retry-After: 1."
- Where: p.19 §26.1 (FR-5): "Send a create-payment request; after its response is received, resend the identical request with the same"
- Evidence EV-037 (doc, supports): "downstream provider, and shall return the identical response, including when duplicate requests arrive concurrently." [doc:DOC-design_v1#p2/s2.1]
- Evidence EV-038 (doc, supports): "While the first request is in flight, a duplicate receives HTTP 409 request_in_progress with Retry-After: 1." [doc:DOC-design_v1#p7/s9.1]
- Evidence EV-039 (doc, supports): "Send a create-payment request; after its response is received, resend the identical request with the same" [doc:DOC-design_v1#p19/s26.1]
- Recommendation: Reword FR-5 so concurrent duplicates receive either the final response or a 409 with Retry-After, with at most one downstream effect. Extend the §26.1 FR-5 test with N parallel identical requests (exactly one acquirer authorization, the rest getting 409 or an identical body), a pod kill mid-request, and Redis-down and Redis-hit variants.
  - Issue: The requirement and the contract disagree on concurrent duplicates, and the test covers only sequential replay.
  - Rationale: Concurrent retries during acquirer brownouts are the main risk scenario that FR-5 exists for.
  - Expected benefit: FR-5 is unambiguous and actually verified. (objectives: FR-5)
  - Supporting evidence: EV-037, EV-038, EV-039
  - Verification: A concurrency test with 100 parallel duplicates shows exactly one simulator authorization.
- Next step: QA lead: Add concurrent and failure-injected idempotency cases to the Phase 9 test plan.
- Decision AD-037 (FR-5): refines. Rewords FR-5 so a concurrent duplicate may receive either 409 or the final response, and adds a concurrency test.

### FND-018 Scheme reattempt limits referenced but never specified; FR-7 test has no oracle

- **validation need** · missing or unverifiable requirement · severity **medium** · confidence 0.65 (medium) · rank 16
- Disposition: **needs investigation** (also: refinement now)

FR-7 and §11.3 depend on 'scheme limits applicable to the card', but the document never lists the limits, windows or response-code categories per scheme. §27 still rates the Retry Engine 'Ready'. Without the limits, the FR-7 criterion 'stop at scheme reattempt limits' cannot be checked, and scheme non-compliance (fees) is possible.

- Where: p.9 §11.3 (FR-7): "window and stops reattempting at the scheme limits applicable to the card."
- Where: p.20 §27 (FR-7): "Retry Engine Ready Outcome classes, cascade limits and scheme rules specified (Section 11)."
- Where: p.19 §26.1 (FR-7): "outcomes, never exceed two additional attempts, and stop at scheme reattempt limits."
- Evidence EV-042 (doc, supports): "window and stops reattempting at the scheme limits applicable to the card." [doc:DOC-design_v1#p9/s11.3]
- Evidence EV-043 (doc, supports): "Retry Engine Ready Outcome classes, cascade limits and scheme rules specified (Section 11)." [doc:DOC-design_v1#p20/s27]
- Evidence EV-063 (doc, supports): "Soft declines 05 (do not honour) and 91 (issuer unavailable) and 96 (system malfunction);" [doc:DOC-design_v1#p9/s11.1]
- Evidence EV-064 (doc, supports): "Hard declines (14 invalid card, 41/43 lost/stolen, 54 expired, 51 insufficient funds, 57 not" [doc:DOC-design_v1#p9/s11.1]
- Recommendation: Add a §11.3 table of per-scheme reattempt limits, windows and code categories (Visa, Mastercard, Amex), with version and source, held as configuration. Have the FR-7 test assert against that table.
  - Issue: The scheme reattempt rules are not captured in the design.
  - Rationale: Both the implementation and the test need concrete limits.
  - Expected benefit: FR-7 compliance can be verified. (objectives: FR-7)
  - Supporting evidence: EV-042, EV-043
  - Verification: FR-7 test cases are derived from the table.
- Next step: Scheme compliance analyst: Compile the current reattempt rules from the scheme manuals for each card scheme and add them to §11.3.
- Decision AD-011 (24 Cascade policy): refines. The 05 cascade trigger and the decline classification need to be traced to current scheme rules; RQ-017 is unanswered, so they are not challenged.
- Decision AD-038 (FR-7): preserves. Gives FR-7 a concrete set of limits to test against.

## Recommended refinements

| Finding | Change | Expected benefit |
|---|---|---|
| FND-006 | In §9.2 and §24, change the Redis key to idem:resp:{merchant_id}:{idempotency_key}. Store request_hash with the cached response and compare it on every hit (return 422 on mismatch). Extend the FR-5 test in §26.1 with cases for two merchants using the same key and for a fast-path hit with a different body. | FR-5 holds on every path, and responses cannot leak across merchants (NFR-7). |
| FND-033 | In 13.1, replace card_number with the HMAC PAN fingerprint, or with a vendor-specific keyed hash computed inside the Vault. If FRV-1 really needs the raw PAN, have the Card Adapter (inside the CDE) make the vendor call, add FRV-1 to the 12.2 table as a third-party service provider, and require a signed DPA before Phase 8. Give the Fraud Hook its own identity with no detokenise permission. | Keeps the CDE limited to the Section 12.2 components so NFR-5 is achievable, and keeps detokenise audit attribution accurate (P10). |
| FND-035 | In 11.1 and 11.2, add an UNKNOWN outcome class for timeouts and 5xx after the request was sent. Before cascading, send a reversal (or a status query plus reversal) for the timed-out attempt. Any late approval on a superseded attempt triggers an automatic reversal or void and a reconciliation flag, never a silent discard. Cascade on connection-refused only when the request is known not to have been delivered. | Prevents duplicate authorizations and charges (FR-5, FR-7) and keeps the payment record and ledger as the single source of truth (P1). |
| FND-021 | Get the QSA's written interpretation of Req. 3.2.1/3.3.1/3.3.2. If it confirms that SAD may not be kept after authorization: rewrite 12.4 and NFR-6 so the CVC is deleted when the final authorization outcome of the payment (including the cascade) is reached, and remove CVC reuse for incremental authorizations. Update the CVC handling decision in Section 24 and the NFR-6 acceptance criterion in 26.2 to match. | NFR-5 and NFR-6 can be achieved, and the scope of stored SAD shrinks. |
| FND-037 | Either restate NFR-4 as RPO ≤ N seconds, with a post-failover reconciliation that rebuilds missing payments from acquirer records, or adopt synchronous cross-region commit for authorization records and accept the latency cost (a governance trade-off). Add idempotency_key and request_hash to the payment table so dedup state can be rebuilt, and define how failover handles in-flight AUTHORISING payments. | Gives an honest, achievable NFR-4 and preserves FR-5 across failover. |
| FND-036 | In 12.3 and Section 24, start with at least two HSMs in different AZs at launch and size HSM throughput for peak card TPS × HSM operations per payment (tokenise, fingerprint, detokenise per attempt). In 20.2, add CDE regional DR: a replicated vault store, a CloudHSM cluster in ap-southeast-3, and a standby Card Adapter. Classify Vault 503 as a platform error that is not cascaded. | Makes NFR-3 and NFR-4 achievable for card payments. |
| FND-010 | Either move the Fraud Hook ahead of go-live in §28 and gate it on Backlog item 4, or define an interim control (rules-only scoring, or a different vendor) and record an explicit risk acceptance. Update the §27 overall conclusion to match. | FR-9 is met at go-live, or a deliberate, owned risk acceptance replaces it. |
| FND-009 | In §21.1, budget the cascade path explicitly. Either add an overall authorization deadline (for example, no new attempt once remaining budget is below the slowest acquirer p95) with a per-attempt timeout well under 2,500 ms, or restate NFR-2 as a non-cascade p99 plus a separate cascade-inclusive p99.9 target. Then align §11.1, §11.2 and §24. | NFR-2 becomes achievable and verifiable, or is restated honestly. |
| FND-041 | In 18.3 and 18.4, require MFA for the Finance, Admin and Owner roles. Require step-up re-authentication plus a second approver (Owner) for payout account changes, notify all Owners out of band, verify the new account by name check or penny test (verified_at), and hold the first payout to the new account for a cooling-off period. | Reduces the risk of payout diversion (FR-13, FR-17). |
| FND-038 | Check the per-partition throughput and LSI item-collection limits against current DynamoDB quotas. Change the key to a high-cardinality partition key (merchant_id#idempotency_key), move the 'recent requests by merchant' view to a GSI or the payment table, and recompute WCU including item size and index writes in 9.3. | Ensures NFR-1 and FR-5 hold for the largest merchant at campaign peaks. |
| FND-040 | In 16.2, match each provider's file incrementally as it arrives, and run cross-provider netting and the report as a final step. Define a cutoff with partial reports and a late-file policy. Agree with an accountable owner whether ACQ-TH1's timing makes NFR-8 renegotiable. | Meets NFR-8 and isolates late providers. |
| FND-011 | In §7.2, add REQUIRES_ACTION to FAILED and to SUCCEEDED (or state that notifications go through AUTHORISING). Track settlement as a separate attribute, or allow PARTIALLY_REFUNDED and REFUNDED to move to SETTLED. Define how multiple partial captures are represented, define a hold state or flag for REVIEW, and add refund-in-progress handling for payout-based refunds. Extend the FR-2 property test to drive every flow in §8, §11 and §16. | FR-1, FR-2, FR-11 and FR-15 can all be implemented consistently. |
| FND-043 | In 9.2 and 20.3, add a lease expiry (locked_until) to IN_PROGRESS items, and have the sweeper scan the idempotency table by age. If no payment exists, delete the lock; if a payment exists in CREATED, resume or fail it. | Merchants can safely retry after a crash (FR-5, NFR-3). |
| FND-016 | Reword FR-5 so concurrent duplicates receive either the final response or a 409 with Retry-After, with at most one downstream effect. Extend the §26.1 FR-5 test with N parallel identical requests (exactly one acquirer authorization, the rest getting 409 or an identical body), a pod kill mid-request, and Redis-down and Redis-hit variants. | FR-5 is unambiguous and actually verified. |
| FND-027 | Mark Phase 3 card-on-file as 'Partially - Backlog item 2'. Add a dated TRID milestone with an owner. Define an interim PAN-based stored-credential mode (with MIT/CIT indicators) in 12.5 for launch. | A predictable go-live for FR-14 card-on-file. |
| FND-018 | Add a §11.3 table of per-scheme reattempt limits, windows and code categories (Visa, Mastercard, Amex), with version and source, held as configuration. Have the FR-7 test assert against that table. | FR-7 compliance can be verified. |
| FND-030 | Add a per-market data-residency assessment to NFR-7 and Section 19.1, covering payment-system regulator rules as well as privacy laws, with legal sign-off before Phase 1 infrastructure is fixed. | NFR-7 compliance and a lawful operation in all markets. |
| FND-044 | In 13.2, name the risk owner, alert when the fallback rate exceeds a threshold, and switch to REVIEW or amount-capped ACCEPT after N minutes of vendor outage. Add the fallback rate to the FRV-1 SLA. | Bounded fraud exposure and an accountable decision (FR-9). |
| FND-017 | Define the FR-8 tolerance as percentage points (or relative) on approval_prior. Make the §10.3 check a hard constraint applied after the §10.2 scoring. Add FR-8 test cases at 1.9, 2.0 and 2.1 points. | FR-8 becomes implementable and verifiable. |

## Areas where no change is needed

- FND-020 Ledger written atomically with state and outbox; append-only enforced by role grants: The atomic transaction and the role-level append-only grants enforce FR-10 and P5 by construction, and the FR-10 test verifies them.
- FND-046 Webhook dispatcher SSRF protection and per-endpoint isolation: These controls are specific and fit FR-12 and NFR-9 as written.
- FND-032 Aurora write capacity claim backed by a measured spike: The measured headroom (130% of target TPS at 58% CPU on a smaller class) supports NFR-1 for the ledger and payment store; the four-hour run in 26.2 will confirm it.
- SA-001 (sections 14, 19, 26.1): The ledger model, the same-transaction outbox and role-revoked mutation satisfy FR-10 and P5, and the FR-10 test checks the balancing invariant and the projection. (see FND-020)
  - p.12 §14.3: "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them,"
- SA-002 (sections 17, 26.1): The webhook retry schedule adds up correctly: seven attempts by about 10 hours, then 12-hourly to about 70 hours, gives 12 attempts within the 72-hour bound. This matches FR-12 and its DLQ acceptance test.
  - p.13 §17: "1 min, 5 min, 15 min, 1 h, 3 h, 6 h, then every 12 h, up to 72 hours from"
- SA-003 (sections 1, 21.2): The volume baseline and capacity arithmetic agree: 10.5 M/day is about 122 TPS, the market merchant counts sum to 15,000, 9 writes × 2,000 TPS is 18,000 writes/s, and 6 × 1.8 KB × 2,000 is 21.6 MB/s. This supports NFR-1 sizing.
  - p.17 §21.2: "MSK. About six 1.8 KB events per payment; 2,000 TPS ≈ 21.6 MB/s ingress across three kafka.m7g.xlarge"
- SA-004 (sections 14.2, 14.3): The example journals balance (9810 + 190 = 10000), and posting the journal in the same transaction as the state change, with an outbox, removes the risk of dual writes. This supports FR-10 and P1/P5.
  - p.12 §14.3: "together with an outbox row. There is no dual write between the payment store and the ledger."
- SA-005 (sections 17, 21.2): The webhook retry schedule adds up to 12 attempts within 72 h as stated, and the MSK ingress arithmetic (6 × 1.8 KB × 2,000 ≈ 21.6 MB/s) is correct. These quantitative claims are internally consistent.
  - p.13 §17: "1 min, 5 min, 15 min, 1 h, 3 h, 6 h, then every 12 h, up to 72 hours from"
- SA-006 (sections 21.2): The Aurora write capacity is backed by a measured spike with headroom. (see FND-032)
  - p.17 §21.2: "db.r7g.8xlarge sustained 2,600 TPS of the full write mix for two hours at 58% writer CPU with commit latency"
- SA-007 (sections 18.5): Back-office write actions require JIT elevation with a second approver and an audit reason behind SSO with hardware MFA, which meets P9 and FR-16 for internal staff. (see FND-041)
  - p.14 §18.5: "write actions (manual refunds, payout holds, merchant suspension) require just-in-time elevation"
- SA-008 (sections 22, 19): Audit records go to an append-only table and to S3 with compliance-mode Object Lock for five years, and ledger tables have UPDATE and DELETE revoked, which meets NFR-12 and P10. (see FND-020)
  - p.18 §22: "go to an append-only table and to S3 with compliance-mode Object Lock for five years"
- SA-009 (sections 20.4): Degradation behaviour for an MSK outage (outbox accumulates in Aurora, payments unaffected) follows from the outbox design and protects NFR-3. (see FND-020)
  - p.17 §20.4: "MSK down Outbox accumulates in Aurora; relay drains on recovery; webhooks delayed, payments unaffected"

## Unresolved issues and next steps

- FND-033 (governance decision): Fraud Hook detokenises PAN under the Card Adapter's role and sends it to FRV-1 (FND-033) Next step (Head of Payments Security / PCI programme owner): Decide with the QSA and the FRV-1 vendor whether a fingerprint can replace the PAN; update 13.1 and 12.2 before Phase 8.
- FND-021 (needs investigation): CVC retention until settlement rests on a likely misreading of PCI DSS (FND-021) Next step (PCI compliance lead with QSA): Obtain a written QSA ruling on keeping SAD after authorization for cascades and incremental authorizations.
- FND-037 (governance decision): RPO of zero is not achievable with asynchronous Aurora Global replication, and idempotency state is lost on failover (FND-037) Next step (Platform Engineering lead with Finance Operations): Decide whether to accept a non-zero RPO with a compensating reconciliation, or to pay for synchronous replication; update NFR-4 and 20.2.
- FND-010 (governance decision): First cohort goes live before the Fraud Hook is built, contradicting FR-9 (FND-010) Next step (Head of Risk and Programme lead): Decide the go-live fraud control and resequence the build phases.
- FND-038 (needs investigation): DynamoDB idempotency capacity for the largest merchant rests on an unverified per-partition figure and leaves out LSI effects (FND-038) Next step (Payments Core tech lead): Confirm the DynamoDB partition and LSI quotas and prototype the hot-key load before Phase 3 is marked ready.
- FND-027 (governance decision): Network tokens 'from launch' depend on a TRID application not yet submitted (FND-027) Next step (Product owner, card partnerships): Submit the VTS/MDES token-requestor applications and publish the expected certification date.
- FND-018 (needs investigation): Scheme reattempt limits referenced but never specified; FR-7 test has no oracle (FND-018) Next step (Scheme compliance analyst): Compile the current reattempt rules from the scheme manuals for each card scheme and add them to §11.3.
- FND-030 (needs investigation): Single-region Singapore data placement assumed compliant with all five markets' rules (FND-030) Next step (Legal / DPO): Obtain localisation and cross-border transfer opinions for ID, TH, PH and MY.
- FND-044 (governance decision): Fraud fail-open policy has no owner, no exposure cap, and no monitoring (FND-044) Next step (Head of Risk): Approve the fail-open policy, its exposure cap and the escalation path.

Research questions left unanswered:
- RQ-005: Can NFR-4 (RPO zero on loss of a region) hold when Aurora Global Database replication is asynchronous (20.2)? Can the NFR-4 acceptance test, which requires every posting committed before the failure to be present after failover, pass?
- RQ-008: Is Section 9.3's claim correct that a single DynamoDB partition sustains 10,000 WCU/s? Can a merchant_id partition key with an LSI carry about 1,800 WCU at peak for one merchant, given the per-partition limit, the 10 GB LSI item-collection limit and the fact that an LSI blocks partition splitting?
- RQ-009: Do PCI DSS v4.0 Requirements 3.2.1 and 3.3.2 really allow a merchant or service provider to keep the CVC in encrypted form after authorization, until settlement or for 72 hours, for cascades and incremental authorizations? Or does Requirement 3.3.1 forbid storing SAD after authorization, with 3.3.2 covering only pre-authorization storage and 3.3.3 covering issuers?
- RQ-012: Does running all primary data stores in Singapore, with DR in Jakarta, meet the data-localisation and cross-border transfer obligations for payment data in the markets served (especially Indonesia under Bank Indonesia payment-system rules and Law 27/2022)? Does sending personal data to FRV-1 without a signed DPA conflict with NFR-7?
- RQ-014: Is a single CloudHSM in one AZ (with scale-out triggered at 1,500 card TPS, which the design's 55% card share of 2,000 TPS never reaches) compatible with NFR-3 at 99.95% and with the throughput needed for detokenise and tokenise at about 1,100 card TPS plus cascades? Also, does a Vault 503 mapped to 'retryable' just cascade into the same failure?
- RQ-017: Which unverified premises does the design depend on: TRID/network-token certification timing, the FRV-1 contract and SLA, sample files from ACQ-PH1 and WAG-1, scheme approval of cross-acquirer cascading on soft decline 05, and the cascade recovery rate taken from a single pilot? Is each tracked to closure with an owner and a date?

## Evidence limitations

- DOC-design_v1: native PDF block not sent because the configured model backend accepts text only. Impact: figures, diagrams and tables rendered as images were not visible to the model; the review is based on the extracted text (DEG-001)
- No external research was possible: no tool gateway (--no-tools, or every server is disabled). Impact: doc-only review: every question that needs external evidence is reported as a validation need, and confidence is lowered (DEG-002)
- assess shard 1/4 (intent_and_fitness) was cut by the stage 1 limit at 265 s; 5 finished finding(s) kept (cut call llm-0003). Impact: criteria not assessed: design_intent; the review is partial for them (no finding, coverage marked not assessed) (DEG-003)

## Evidence register

| ID | Type | Source | Retrieved | Cited |
|---|---|---|---|---|
| EV-001 | doc | doc:DOC-design_v1#p11/s13.1 | - | no |
| EV-002 | doc | doc:DOC-design_v1#p10/s12.2 | - | yes |
| EV-003 | doc | doc:DOC-design_v1#p10/s12.1 | - | yes |
| EV-004 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-005 | doc | doc:DOC-design_v1#p7/s9.1 | - | no |
| EV-006 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-007 | doc | doc:DOC-design_v1#p16/s20.2 | - | yes |
| EV-008 | doc | doc:DOC-design_v1#p9/s10.5 | - | yes |
| EV-009 | doc | doc:DOC-design_v1#p9/s11.1 | - | yes |
| EV-010 | doc | doc:DOC-design_v1#p12/s16.1 | - | yes |
| EV-011 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-012 | doc | doc:DOC-design_v1#p2/s1 | - | yes |
| EV-013 | inference | inference:EV-013 from EV-001, EV-002, EV-003 | - | yes |
| EV-014 | inference | inference:EV-014 from EV-004, EV-005 | - | no |
| EV-015 | inference | inference:EV-015 from EV-006, EV-007 | - | no |
| EV-016 | inference | inference:EV-016 from EV-008, EV-009 | - | yes |
| EV-017 | inference | inference:EV-017 from EV-010, EV-011, EV-012 | - | yes |
| EV-018 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-019 | doc | doc:DOC-design_v1#p4/s3 | - | yes |
| EV-020 | doc | doc:DOC-design_v1#p7/s9.1 | - | yes |
| EV-021 | doc | doc:DOC-design_v1#p3/s2.2 | - | no |
| EV-022 | doc | doc:DOC-design_v1#p17/s21.1 | - | yes |
| EV-023 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-024 | doc | doc:DOC-design_v1#p21/s28 | - | yes |
| EV-025 | doc | doc:DOC-design_v1#p21/s27 | - | yes |
| EV-026 | doc | doc:DOC-design_v1#p6/s7.2 | - | yes |
| EV-027 | doc | doc:DOC-design_v1#p6/s7.2 | - | yes |
| EV-028 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-029 | doc | doc:DOC-design_v1#p17/s20.2 | - | no |
| EV-030 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-031 | doc | doc:DOC-design_v1#p16/s20.1 | - | yes |
| EV-032 | doc | doc:DOC-design_v1#p10/s12.3 | - | no |
| EV-033 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-034 | doc | doc:DOC-design_v1#p9/s11.2 | - | no |
| EV-035 | doc | doc:DOC-design_v1#p19/s25 | - | yes |
| EV-036 | doc | doc:DOC-design_v1#p18/s24 | - | yes |
| EV-037 | doc | doc:DOC-design_v1#p2/s2.1 | - | yes |
| EV-038 | doc | doc:DOC-design_v1#p7/s9.1 | - | yes |
| EV-039 | doc | doc:DOC-design_v1#p19/s26.1 | - | yes |
| EV-040 | doc | doc:DOC-design_v1#p9/s10.3 | - | yes |
| EV-041 | doc | doc:DOC-design_v1#p9/s10.2 | - | yes |
| EV-042 | doc | doc:DOC-design_v1#p9/s11.3 | - | yes |
| EV-043 | doc | doc:DOC-design_v1#p20/s27 | - | yes |
| EV-044 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-045 | doc | doc:DOC-design_v1#p17/s20.3 | - | no |
| EV-046 | doc | doc:DOC-design_v1#p12/s14.3 | - | yes |
| EV-047 | inference | inference:EV-047 from EV-018, EV-019, EV-020 | - | yes |
| EV-048 | inference | inference:EV-048 from EV-010, EV-021, EV-011 | - | no |
| EV-049 | inference | inference:EV-049 from EV-022, EV-008, EV-009 | - | yes |
| EV-050 | inference | inference:EV-050 from EV-027, EV-028 | - | yes |
| EV-051 | inference | inference:EV-051 from EV-006, EV-007, EV-029 | - | yes |
| EV-052 | inference | inference:EV-052 from EV-030, EV-031, EV-032 | - | yes |
| EV-053 | inference | inference:EV-053 from EV-033, EV-034 | - | yes |
| EV-054 | inference | inference:EV-054 from EV-046 | - | yes |
| EV-055 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-056 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-057 | doc | doc:DOC-design_v1#p8/s9.3 | - | no |
| EV-058 | doc | doc:DOC-design_v1#p8/s9.3 | - | no |
| EV-059 | doc | doc:DOC-design_v1#p11/s13.1 | - | yes |
| EV-060 | doc | doc:DOC-design_v1#p10/s12.1 | - | yes |
| EV-061 | doc | doc:DOC-design_v1#p16/s19.1 | - | yes |
| EV-062 | doc | doc:DOC-design_v1#p3/s2.2 | - | yes |
| EV-063 | doc | doc:DOC-design_v1#p9/s11.1 | - | yes |
| EV-064 | doc | doc:DOC-design_v1#p9/s11.1 | - | yes |
| EV-065 | doc | doc:DOC-design_v1#p17/s21.2 | - | yes |
| EV-066 | inference | inference:EV-066 from EV-055, EV-056 | - | yes |
| EV-067 | inference | inference:EV-067 from EV-006, EV-007 | - | yes |
| EV-068 | inference | inference:EV-068 from EV-057, EV-058 | - | yes |
| EV-069 | inference | inference:EV-069 from EV-022, EV-008 | - | no |
| EV-070 | inference | inference:EV-070 from EV-010, EV-011 | - | no |
| EV-071 | inference | inference:EV-071 from EV-030, EV-060 | - | no |
| EV-072 | doc | doc:DOC-design_v1#p11/s13.1 | - | yes |
| EV-073 | doc | doc:DOC-design_v1#p19/s25 | - | yes |
| EV-074 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-075 | doc | doc:DOC-design_v1#p9/s11.2 | - | yes |
| EV-076 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-077 | doc | doc:DOC-design_v1#p17/s20.2 | - | yes |
| EV-078 | doc | doc:DOC-design_v1#p10/s12.3 | - | yes |
| EV-079 | doc | doc:DOC-design_v1#p16/s20.2 | - | yes |
| EV-080 | doc | doc:DOC-design_v1#p17/s20.2 | - | yes |
| EV-081 | doc | doc:DOC-design_v1#p8/s9.3 | - | yes |
| EV-082 | doc | doc:DOC-design_v1#p8/s9.3 | - | yes |
| EV-083 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-084 | doc | doc:DOC-design_v1#p17/s21.1 | - | yes |
| EV-085 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-086 | doc | doc:DOC-design_v1#p13/s16.2 | - | yes |
| EV-087 | doc | doc:DOC-design_v1#p14/s18.4 | - | yes |
| EV-088 | doc | doc:DOC-design_v1#p14/s18.3 | - | yes |
| EV-089 | doc | doc:DOC-design_v1#p14/s18.2 | - | yes |
| EV-090 | doc | doc:DOC-design_v1#p10/s12.4 | - | yes |
| EV-091 | doc | doc:DOC-design_v1#p1/s12.4 | - | no |
| EV-092 | doc | doc:DOC-design_v1#p8/s9.2 | - | yes |
| EV-093 | doc | doc:DOC-design_v1#p17/s20.3 | - | yes |
| EV-094 | doc | doc:DOC-design_v1#p11/s13.2 | - | yes |
| EV-095 | doc | doc:DOC-design_v1#p12/s14.3 | - | yes |
| EV-096 | doc | doc:DOC-design_v1#p16/s19 | - | yes |
| EV-097 | doc | doc:DOC-design_v1#p13/s17 | - | yes |
| EV-098 | inference | inference:EV-098 from EV-072, EV-003, EV-002 | - | yes |
| EV-099 | inference | inference:EV-099 from EV-018, EV-005 | - | yes |
| EV-100 | inference | inference:EV-100 from EV-074, EV-075, EV-009 | - | yes |
| EV-101 | inference | inference:EV-101 from EV-030, EV-076, EV-077 | - | yes |
| EV-102 | inference | inference:EV-102 from EV-006, EV-079, EV-080 | - | yes |
| EV-103 | inference | inference:EV-103 from EV-081, EV-082, EV-083 | - | yes |
| EV-104 | inference | inference:EV-104 from EV-084, EV-008 | - | no |
| EV-105 | inference | inference:EV-105 from EV-085, EV-010, EV-086 | - | yes |
| EV-106 | inference | inference:EV-106 from EV-090, EV-091 | - | yes |
| EV-107 | inference | inference:EV-107 from EV-092, EV-093 | - | yes |

## Review coverage

| Criterion | Outcome | Findings | Note |
|---|---|---|---|
| design_intent | not assessed | - | not assessed: out of time before assessment (stage 1 limit) |
| fitness_for_objectives | findings | FND-033, FND-006, FND-037, FND-009, FND-040 | no coverage row returned by the model; derived by code from the findings |
| requirement_completeness | findings | FND-010, FND-011, FND-036, FND-035, FND-018, FND-043 | Checked the state machine against the flows, the DR and multi-AZ coverage of the CDE, cascade timeout handling, scheme rules, idempotency crash recovery, and the phase plan against the FRs. |
| internal_consistency | findings | FND-006, FND-033, FND-040, FND-009, FND-010, FND-011, FND-037, FND-036, FND-027, FND-016, FND-017, FND-020 | Cross-checked principles, FRs and NFRs against §§7–28, including timing arithmetic, latency, capacity and webhook figures. Several contradictions are material. |
| claims_and_external_constraints | findings | FND-021, FND-037, FND-038, FND-009, FND-040, FND-033, FND-036, FND-030, FND-018, FND-032 | Checked the PCI DSS SAD claims, DR/RPO claims, DynamoDB limits, the latency budget arithmetic, reconciliation timing, CDE scoping, HSM topology, data residency and scheme reattempt rules. External facts are flagged for verification, not asserted. |
| security_and_privacy | findings | FND-033, FND-006, FND-041, FND-021, FND-046 | Checked CDE scoping, Vault access, the idempotency cache, SAD retention, admin-plane authentication, payout controls, webhook signing and SSRF, logging and audit. |
| scalability_and_failure_modes | findings | FND-035, FND-036, FND-037, FND-038, FND-009, FND-040, FND-043, FND-020, FND-006 | Checked cascade semantics, HSM and DR topology, RPO, DynamoDB hot keys, the latency budget, reconciliation timing and crash recovery. |
| assumptions_and_dependencies | findings | FND-027, FND-010, FND-040, FND-033, FND-036, FND-030 | Checked the Backlog items against confirmed decisions and the build-phase readiness claims. The TRID and FRV-1 dependencies are on the critical path for go-live but are marked ready or not blocking. |
| verifiability | findings | FND-006, FND-040, FND-009, FND-037, FND-035, FND-016, FND-017, FND-018, FND-020 | Each criterion in §26 was compared with its requirement. The FR-5, FR-7, FR-8, NFR-2, NFR-4 and NFR-8 criteria either cannot validate the requirement or would fail by design. |
| decision_preservation | findings | FND-033, FND-006, FND-037, FND-040 | no coverage row returned by the model; derived by code from the findings |
| operability_and_governance | findings | FND-040, FND-044 | Checked risk ownership for fraud fail-open and the late settlement file policy; the back-office governance controls are sound. |

## Run details

| | |
|---|---|
| Run | ui_flow_1 (started 2026-10-03T04:25:13Z) |
| Outcome | completed_degraded |
| Model | requested claude-opus-5-5; served claude-opus-5-5; effort per-stage (extra.model.effort_by_stage) |
| Persona | generalist_architect |
| Tool transport | live |
| Research stop | tool_failure (error): no_tools; 0 iteration(s); 0 cited of 0 retrieved |
| Tool calls | none |
| Tokens | input 136549, cached 160125, output 119778; cost ~$3.52 (price table 2026-09-25); a lower bound: 1 model call with unrecorded usage (assess, deadline cut) |
| Extractor | pdfplumber 0.11.10 |
| Config sha256 | bdec44450f5811185fe0da49f4d81ff184e14af203b44c42f8d2f947e42ccfab |
| Prompt bundle sha256 | 6f0ee28ab9acf35152a2d4456207a8a068222149422e66d801c8195455c28ba7 |
| Git commit | 5f620651ba95133422132338fc9f20f61644c064 |
| Fault schedule | none |
| Model fallbacks | 0 |
| Canonical text DOC-design_v1 | sha256 ad0bb891f073f14325b6ba716d58070d6b074ebaef9a9c64432138b89b64ec3c |
