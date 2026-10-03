# Design review: Serindit Pay — Merchant Payment Orchestration Platform

| | |
|---|---|
| Review | REV-reassess_payments_v2_1 (delta review) |
| Under review | DOC-design_v2: Serindit Pay — Merchant Payment Orchestration Platform v1.1, 22 pages |
| Prior version | DOC-design_v1: Serindit Pay - Merchant Payment Orchestration Platform v1.0, 21 pages |
| Verdict | **not fit** (confidence 0.75, medium) |
| Tools used | none |
| Tools disabled | mcp-internet-search, mcp-research-information, mcp-browser-automation-pw, mcp-document-intelligence |
| Reporting threshold | severity low and above (0 finding(s) in the appendix) |

> No external research was possible or used in this run: every finding rests on the document alone.


## Design intent

MPOP is Serindit Pay's Merchant Payment Orchestration Platform. It accepts merchants' payment requests, routes each one to an acquirer, e-wallet provider or bank-transfer rail, and accounts for every movement of money until the merchant is settled. It replaces five per-market stacks that share no routing or ledger and reconcile by spreadsheet. Its scope is one merchant API across five SEA markets (Singapore, Malaysia, Indonesia, Thailand, Philippines) for about 15,000 merchants at a peak of 2,000 payment-creation TPS. That scope covers routing, cascading, idempotency, a tokenising card vault, a fraud hook, a double-entry ledger, reconciliation, payouts, webhooks and a merchant admin plane. Dispute case management, KYB, 3DS server internals and lending/BNPL are out of scope.

Objectives:
- Give merchants one versioned API across five markets, with rule-based routing and cascading on retryable failures.
- Replace five per-market integration stacks with shared routing, one ledger and automated reconciliation.
- Support about 15,000 active merchants and a peak of 2,000 payment-creation TPS by the 2027 design target.
- P1: One payment, one truth: the payment record and the ledger are the source of truth; provider responses are inputs only.
- P2: Card data stays in the Vault: PAN and SAD leave the Vault boundary only over the Card Adapter's connection to an acquirer; all other services handle tokens.
- P3: Every mutating call is deduplicated on the pair (merchant, idempotency key).
- P4: Money is held as integer minor units with an ISO 4217 code; no floating-point type ever holds an amount.
- P5: The ledger is append-only; corrections are new reversing or adjusting journals.
- P6: Provider quirks live in adapters; the core never branches on provider identity.
- P7: Delivery is at least once and the effect exactly once: consumers deduplicate on stable identifiers.
- P8: Fail closed on security; degrade to documented defaults when optional enrichment (fraud signals, BIN metadata) is unavailable.
- P9: Least privilege and separation of duties; money-moving permissions are separated from configuration permissions.
- P10: Everything is auditable: every mutation, routing decision and admin action can be reconstructed.
- Keep PCI DSS scope confined to a small CDE enclave (Vault Edge, Card Vault, CloudHSM, Card Adapter).

Constraints:
- NFR-5: Assessment as a PCI DSS v4.0 Level 1 service provider, with the CDE limited to the components listed in Section 12.2.
- NFR-6: No sensitive authentication data retained after authorization completes, even if encrypted (PCI DSS v4.0 3.3.1, 3.3.1.2); SAD encrypted while held (3.3.2).
- NFR-7: Compliance with SG PDPA 2012, MY PDPA 2010, ID Law 27/2022, TH PDPA 2019 and PH DPA 2012: purpose limitation, retention limits and access logging.
- FR-7: Cascades must never reattempt where card scheme rules prohibit it, and stop at scheme reattempt limits.
- NFR-8: Settlement reports published by 09:00 SGT on T+1; Finance says it has confirmed this against merchant contracts.
- AWS ap-southeast-1 across three AZs is the primary region, with ap-southeast-3 for DR; the CDE runs in a separate AWS account, VPC and EKS cluster.
- Principles override later sections when they conflict.
- KYB/onboarding is owned by the Merchant Risk platform; MPOP consumes an approved-merchant event.
- The ACQ-PH1 v2 API retires in Q3 2027, so the adapter must migrate to v3 before then.
- The first merchant cohort (Singapore, cards and PayNow) goes live after Build Phase 7; other markets follow at four-week intervals.

Key assumptions:
- 2027 volume targets: 10.5 M attempts per day, 2,000 peak TPS, card share 55%, largest merchant 45% of peak (about 900 TPS, marketplace M-0001).
- Fewer than 1% of card payments cascade, so the cascade path sits above p99 (Section 21.1). The baseline retryable rate is 3.8%, and the pilot recovered about 31% of retryable outcomes.
- Acquirer round-trip p99 is 1,100 ms (2025 production, slowest acquirer). Component p99s sum to 1,338 ms; orchestration overhead is 238 ms.
- A DynamoDB global table in default multi-Region eventual consistency mode, with a conditional put on attribute_not_exists(pk), lets exactly one request across regions acquire the lock.
- Each idempotency request costs up to 6 WCU, or up to 12,000 WCU table-wide at 2,000 TPS; warm throughput is pre-set to 15,000 WCU before campaigns.
- Aurora Global Database lag is typically under one second. Payments in the regional loss window can be recovered from provider status APIs and T+1 reconciliation.
- An Aurora spike on db.r7g.8xlarge sustained 2,600 TPS of the full write mix; production uses db.r7g.12xlarge.
- Reconciliation finishes about 08:09 SGT at 2027 volume once the last file (ACQ-TH1 at 07:30 SGT) arrives.
- One HSM is enough at launch; a second is added when sustained card volume exceeds 1,500 TPS, and daily backups allow re-creation in any AZ.
- FRV-1 needs the full PAN for its consortium velocity graph; the Fraud Hook detokenises using the Card Adapter's client library and service role.
- Network tokens (VTS/MDES) are the primary card-on-file credential from launch, although the Token Requestor application has not yet been submitted (Backlog item 2).
- Several acquirers require the CVC on each cascade re-presentation; incremental and MIT authorizations do not need it.

Located at: p.2 §1 (3 passages).

## Fitness for purpose

**Not fit** (confidence 0.75). As written, v1.1 is not fit to start building. One critical finding and eight high findings remain open. The critical one is FND-001: the Redis idempotency fast path is keyed on idempotency_key alone and skips the body-hash check. One merchant can therefore receive another merchant's stored payment object, and a reused key with a different body does not get the HTTP 422 that FR-5 requires. This breaks P3, and the review standard treats a critical finding as blocking build. Two other findings break the PCI scoping objective and P2. FND-003: the Fraud Hook detokenises the PAN using the Card Adapter's role and sends it to FRV-1, which contradicts Sections 12.1 and 12.2. FND-008: the first cohort goes live before the Fraud Hook, the PCI DSS assessment and the Section 26 tests. The other high findings show money-safety and resilience claims the design relies on but does not support:

- FND-004: a cascade after a timeout can produce a duplicate authorization.
- FND-005: the latency budget leaves cascades out of the p99 and is likely to fail its own NFR-2 test.
- FND-006: a single CloudHSM in one AZ is a single point of failure, and the trigger for adding a second can never fire.
- FND-002: the cross-region lock relies on an eventually consistent global table.
- FND-014: the CDE is missing from the regional DR plan.
- FND-013: there is no working way to recover payments in the loss window.

Most of these can be fixed by editing the text (refinement_now), so the core architecture does not need replacing. The ledger, integer money handling, outbox, payout-account controls (FND-046) and DynamoDB key and capacity design (FND-047) are sound and should stay as they are. Changes from v1.0 that fixed real defects should also be kept: CVC handling now ends at the authorization outcome, MFA is mandatory, reconciliation is incremental, and routing thresholds are now precise. Limits of this review:

- It worked from extracted text only, so figures shown as images were not seen (DEG-001).
- No external research was possible (DEG-002). AWS behaviour, such as conditional writes on global tables, and the current PCI DSS version and how assessors read it are unverified (FND-002, FND-030).
- Assessment shards were cut short, so design intent was not assessed and some lower-ranked findings may be missing (DEG-003 to DEG-005).
- FND-002 in effect challenges approved decision AD-006 without enough supporting evidence (DEG-006), so its outcome is uncertain.

None of these limits would clear FND-001, FND-003 or FND-008. Those findings rest on exact text in the document and on its own principles, which supports the not_fit label even with these gaps.

| Objective | Verdict | Findings |
|---|---|---|
| Objective: one versioned API across five markets with rule-based routing and cascading | fit with conditions | FND-004, FND-005, FND-020, FND-021 |
| Objective: replace five per-market stacks with shared routing, one ledger and automated reconciliation | fit with conditions | FND-044, FND-041, FND-013 |
| Objective: about 15,000 merchants and 2,000 TPS peak by 2027 | fit with conditions | FND-047, FND-005, FND-006, FND-014 |
| P1 | fit with conditions | FND-004, FND-013 |
| P2 | not fit | FND-003 |
| P3 | not fit | FND-001, FND-002, FND-021 |
| P4 | fit | - |
| P5 | fit | - |
| P6 | fit | - |
| P7 | fit with conditions | FND-041 |
| P8 | fit with conditions | FND-022 |
| P9 | fit with conditions | FND-003, FND-046 |
| P10 | fit | - |
| Objective: keep PCI DSS scope confined to the CDE enclave | not fit | FND-003, FND-008, FND-030, FND-031 |

What would change this verdict: The verdict would move to fit_with_conditions under the following conditions. First, a v1.2 makes these fixes:

- FND-001: key the Redis fast path on merchant_id plus key and check the request hash before returning a stored response.
- FND-003: remove the Fraud Hook's PAN detokenisation, or formally bring the Fraud Hook into the CDE with its own role and get the PCI scoping memo agreed.
- FND-008: move go-live until after the Fraud Hook, the PCI assessment and the Section 26 acceptance tests, or get a documented risk acceptance from the accountable owner.
- FND-004: query the provider's status or reverse the earlier attempt before cascading after a timeout, and correct the 'cannot create a duplicate charge' claim.
- FND-005: redo the p99 latency budget with cascades included.
- FND-006: deploy two or more HSMs across AZs at launch, or set a scaling trigger that can actually fire.
- FND-014: add the CDE to the regional DR plan.
- FND-013: define a recovery mechanism that can find the payments in the loss window.

Second, FND-002 needs an AWS primary source, or a test, showing whether a conditional put is enforced across regions on the global table. The remaining medium findings could then stay open as conditions. External evidence that the Fraud Hook PAN flow is acceptable to a QSA in its current scope would also reduce the weight of FND-003.

## Strengths

### FND-046 Payout bank account change controls now protect against account takeover

- **strength** · confidence 0.80 (high) · rank 18
- Disposition: **no change**

Section 18.4 now requires a two-person rule with a different Owner and step-up MFA, a 48-hour cooling-off period with notice to all Owners and Admins, and validation of the account name against the merchant's legal name. Section 18.3 makes MFA mandatory for every user. Together these close the single-phished-credential path to redirecting payouts, and align with P9 and FR-13.

- Where: p.14 §18.4 (FR-13, FR-17): "The new account takes effect after a 48-hour cooling-off period in which every Owner and Admin is notified and can cancel"
- Evidence EV-118 (doc, supports): "The new account takes effect after a 48-hour cooling-off period in which every Owner and Admin is notified and can cancel" [doc:DOC-design_v2#p14/s18.4]
- Why no change is needed: These controls meet P9 separation of duties and protect FR-17 payouts. The FR-13 test covers both the approval and the cancellation paths.
- Decision AD-018 (24 Confirmed Decisions - Merchant user MFA): preserves. The strength affirms the approved two-person rule, step-up and cooling-off controls.
- Decision AD-046 (FR-17): preserves. These controls protect FR-17 payouts from redirection.
- Since the previous version: resolved (was FND-046). Two-person approval, mandatory MFA, cooling-off and Owner notification were added in 1.1.

### FND-047 DynamoDB idempotency key and capacity sizing now spread the largest merchant's load

- **strength** · confidence 0.70 (medium) · rank 19
- Disposition: **no change**

The table now uses the composite key merchant_id#idempotency_key with no LSI, and sizes writes in WCU per KB (up to 6 per request, 12,000 table-wide) with warm throughput set ahead of campaign events. This spreads M-0001's roughly 900 TPS across many partitions, supporting NFR-1 and FR-5 at peak. The provisioning plan should also cover replicated writes on the Jakarta replica.

- Where: p.8 §9.3 (NFR-1): "so each request costs up to 6 WCU - 1 for the lock (item under 1 KB) and up to 5 for the completion update"
- Evidence EV-119 (doc, supports): "so each request costs up to 6 WCU - 1 for the lock (item under 1 KB) and up to 5 for the completion update" [doc:DOC-design_v2#p8/s9.3]
- Why no change is needed: A high-cardinality key and WCU-based sizing remove the hot-partition risk for NFR-1. The remaining cross-region concern is covered in FND-002.
- Decision AD-006 (24 Confirmed Decisions - Idempotency store): preserves. The strength affirms the composite partition key in the approved idempotency-store decision.
- Since the previous version: resolved (was FND-009). The key schema, LSI removal and WCU arithmetic were corrected in 1.1.

## Risks

### FND-001 Redis idempotency fast path is still not scoped to the merchant and still skips the body-hash check

- **risk** · security privacy gap · severity **critical** · confidence 0.90 (high) · rank 1
- Disposition: **refinement now** (also: needs testing)

Version 1.1 leaves Section 9.2 unchanged. The fast path still stores and reads responses at idem:resp:{idempotency_key} and returns a hit without checking the merchant or the request hash. This breaks P3, and Section 9.1 still accepts merchants' own order and invoice numbers as keys. Merchant A can therefore be sent merchant B's stored payment object, and its own payment is never created. A reused key with a different body gets the old response instead of the HTTP 422 that FR-5 requires.

- Where: p.8 §9.2 (FR-5): "the final response is written to idem:resp:{idempotency_key} with a 24-hour TTL"
- Where: p.8 §9.1: "frequently use their own order or invoice identifiers, which is accepted."
- Where: p.4 §3 (P3): "Idempotency is scoped to (merchant, key). Every mutating call is deduplicated on the pair of merchant identity and client-supplied"
- Evidence EV-001 (doc, supports): "incoming mutating request, the Payments API checks this key first; on a hit, it returns the stored response immediately" [doc:DOC-design_v2#p8/s9.2]
- Evidence EV-002 (doc, supports): "frequently use their own order or invoice identifiers, which is accepted." [doc:DOC-design_v2#p8/s9.1]
- Evidence EV-003 (doc, supports): "Idempotency is scoped to (merchant, key). Every mutating call is deduplicated on the pair of merchant identity and client-supplied" [doc:DOC-design_v2#p4/s3]
- Evidence EV-033 (inference, supports): "Across 15,000 merchants that use sequential order numbers as keys, two merchants sharing a key within 24 hours is likely, and the global fast-path key returns one merchant's response to the other before any merchant-scoped or hash check runs." [inference:EV-033] derived from EV-001, EV-002, EV-003
- Evidence EV-060 (inference, supports): "Because the fast-path key has no merchant identity and the hit path does not compare request hashes, both the P3 (merchant, key) scope and the FR-5 HTTP 422 on body mismatch are bypassed whenever Redis holds the key." [inference:EV-060] derived from EV-041, EV-001, EV-042
- Evidence EV-120 (inference, supports): "A Redis key without merchant_id, read before any hash check, lets one merchant's request match another merchant's stored response, and lets a changed body return a stale response instead of 422." [inference:EV-120] derived from EV-041, EV-092, EV-093
- Evidence EV-041 (doc, supports): "On completion of a request, the final response is written to idem:resp:{idempotency_key} with a 24-hour TTL." [doc:DOC-design_v2#p8/s9.2]
- Recommendation: In Sections 9.2 and 24, change the fast-path key to idem:resp:{merchant_id}#{idempotency_key}. Store the request_hash with the cached response and compare it on every hit; on a mismatch, fall through to the durable path so it returns 422. Add two cases to the FR-5 test in Section 26: two merchants using the same key, and the same key with a modified body while the fast-path entry is warm.
  - Issue: The fast-path key leaves out merchant_id, and a fast-path hit bypasses the request-hash check.
  - Rationale: P3 and FR-5 require deduplication on (merchant, key) and a 422 on a body mismatch. The durable path in Section 9.2 already does this, but the fast path runs first and bypasses it.
  - Expected benefit: Prevents cross-merchant disclosure of payment data and silently lost payments, and makes the 422 behaviour in FR-5 hold. (objectives: FR-5, P3, NFR-7)
  - Supporting evidence: EV-001, EV-002, EV-003, EV-033
  - Verification: The extended FR-5 test shows that each merchant gets its own payment, and that a modified body returns 422 while the Redis entry is warm.
- Next step: Payments Core tech lead: Amend Sections 9.2 and 24 and add the cross-merchant and warm-cache 422 cases to the Section 26 FR-5 test before Phase 3.
- Decision AD-006 (24 Confirmed Decisions - Idempotency store): refines. The Redis fast-path key in the approved idempotency-store decision is changed to include merchant_id and a request-hash check; the two-tier structure stays.
- Decision AD-037 (FR-5): preserves. The change restores FR-5's (merchant, key) scope and its 422 on a body mismatch.
- Decision AD-033 (3 Foundational Principles): preserves. P3 overrides Section 9.2 under the principle-precedence rule, so the fast path must follow it.
- Since the previous version: still open (was FND-001). Version 1.1 revised Sections 9 and 24 but left the fast-path key and hit behaviour unchanged.

### FND-003 Fraud Hook still detokenises PAN with the Card Adapter's role, contradicting P2, Section 12.1 and the CDE scope

- **risk** · security privacy gap · severity **high** · confidence 0.90 (high) · rank 2
- Disposition: **governance decision** (also: refinement now)

Section 13.1 is unchanged. The Fraud Hook still gets the full PAN by calling the Vault's detokenise operation with the Card Adapter's library and service role, and still sends it to FRV-1. This contradicts P2, the rule in Section 12.1 that only the Card Adapter may detokenise, and the out-of-scope classification of the Fraud Hook in Section 12.2. It also defeats P9 least privilege. As written, the NFR-5 assessment cannot use the CDE as defined.

- Where: p.11 §13.1 (NFR-5): "detokenise operation, using the Card Adapter client library and service role."
- Where: p.10 §12.1: "Only the Card Adapter's service identity may call detokenise."
- Where: p.10 §12.2 (NFR-5): "Fraud Hook Out of scope Token, BIN, last 4 only"
- Evidence EV-008 (doc, supports): "detokenise operation, using the Card Adapter client library and service role." [doc:DOC-design_v2#p11/s13.1]
- Evidence EV-009 (doc, supports): "Only the Card Adapter's service identity may call detokenise." [doc:DOC-design_v2#p10/s12.1]
- Evidence EV-010 (doc, supports): "Fraud Hook Out of scope Token, BIN, last 4 only" [doc:DOC-design_v2#p10/s12.2]
- Evidence EV-097 (doc, supports): "The Fraud Hook obtains the PAN through the Vault's detokenise operation, using the Card Adapter client library and service role." [doc:DOC-design_v2#p11/s13.1]
- Evidence EV-047 (doc, supports): "Only the Card Adapter's service identity may call detokenise. Each call unwraps the record's DEK" [doc:DOC-design_v2#p10/s12.1]
- Recommendation: Decide between: (a) send FRV-1 a keyed PAN fingerprint or network token in place of the PAN, accepting some loss of scoring quality; (b) have a CDE-resident component call FRV-1 with the PAN; or (c) bring the Fraud Hook into the CDE with its own service identity, and update P2 and Section 12.2. Record the choice in Sections 13.1 and 24.
  - Issue: The Fraud Hook handles PAN outside the declared CDE and borrows another service's identity.
  - Rationale: These cannot all hold: under P3's precedence rule P2 wins, and NFR-5 bounds the CDE to Section 12.2.
  - Expected benefit: Keeps the CDE as declared for NFR-5 and restores P2/P9. (objectives: NFR-5, P2, P9, FR-9)
  - Supporting evidence: EV-008, EV-009, EV-010
  - Verification: An IAM policy review shows detokenise is granted only to the identities listed in Section 12.2, and the QSA segmentation test passes.
- Next step: Head of Security / PCI compliance lead: Choose option (a), (b) or (c) with the risk team, before the FRV-1 contract (Backlog item 4) fixes the payload.
- Decision AD-028 (NFR-5): preserves. Each option keeps the CDE consistent with Section 12.2 as NFR-5 requires, or changes it explicitly.
- Decision AD-033 (3 Foundational Principles): preserves. P2 takes precedence over Section 13.1 under the principle rule.
- Decision AD-013 (24 Confirmed Decisions - Fraud): refines. The FRV-1 synchronous hook is kept, but the card identifier it receives changes.
- Decision AD-023 (25 Pending Backlog item 4): refines. The card-identifier choice has to be settled within the pending FRV-1 contract and DPA.
- Decision AD-039 (FR-9): preserves. FR-9 scoring continues under every option.
- Since the previous version: still open (was FND-002). Sections 12.1, 12.2 and 13.1 were not revised in 1.1.

### FND-008 First cohort still goes live before the Fraud Hook, PCI DSS assessment and acceptance testing

- **risk** · decision depends on pending item · severity **high** · confidence 0.85 (high) · rank 3
- Disposition: **governance decision**

Section 28 still puts first-cohort go-live after Phase 7. The Fraud Hook comes in Phase 8 and is blocked on the FRV-1 contract, and load testing, DR, the PCI DSS assessment and the Section 26 test plan come in Phase 9. Live card traffic would therefore run without the scoring FR-9 requires and before NFR-5 and the acceptance criteria have been demonstrated. Section 27's conclusion that only the Admin API and disputes are material gaps for the first cohort does not account for this.

- Where: p.22 §28: "The first merchant cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week"
- Where: p.22 §28 (FR-9): "Fraud Hook (FRV-1) Yes - vendor contract (Backlog item 4)"
- Where: p.22 §28 (NFR-5): "Hardening - load, chaos and DR game days; PCI DSS assessment; Section 26 test plan"
- Evidence EV-024 (doc, supports): "The first merchant cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week" [doc:DOC-design_v2#p22/s28]
- Evidence EV-025 (doc, supports): "Fraud Hook (FRV-1) Yes - vendor contract (Backlog item 4)" [doc:DOC-design_v2#p22/s28]
- Evidence EV-026 (doc, supports): "Hardening - load, chaos and DR game days; PCI DSS assessment; Section 26 test plan" [doc:DOC-design_v2#p22/s28]
- Evidence EV-089 (inference, supports): "Go-live after Phase 7 precedes both Phase 8 (fraud scoring) and Phase 9 (PCI assessment and acceptance tests), so FR-9 and NFR-5 are unmet for live card traffic." [inference:EV-089] derived from EV-024, EV-076, EV-077
- Evidence EV-051 (doc, supports): "Every card payment and every e-wallet payment above the merchant's configured threshold shall be scored by the fraud-scoring hook" [doc:DOC-design_v2#p3/s2.1]
- Evidence EV-112 (doc, supports): "4. FRV-1 contract - data processing agreement and SLA finalisation." [doc:DOC-design_v2#p20/s25]
- Recommendation: In Section 28, move go-live after Phases 8 and 9 (at least the PCI assessment, load test and the FR-5/FR-9 tests). If that is not acceptable, record a risk acceptance with interim controls (for example, rules-only fraud screening, volume caps) and add it to Section 27.
  - Issue: The phase order puts go-live ahead of the fraud scoring and compliance controls the requirements assume.
  - Rationale: FR-9 requires scoring before every card authorization, and NFR-5 compliance must be shown before card data is processed live.
  - Expected benefit: The first cohort launches meeting FR-9, NFR-5 and the Section 26 criteria. (objectives: FR-9, NFR-5, NFR-1)
  - Supporting evidence: EV-024, EV-025, EV-026
  - Verification: The release gate checklist references a passed QSA RoC, the FR-9 test and the NFR-1 load test before first live traffic.
- Next step: Programme sponsor with Head of Risk: Decide the go-live gate and either re-sequence Section 28 or sign an interim risk acceptance.
- Decision AD-035 (28 Build Phases): challenges. Going live after Phase 7 comes before fraud scoring (Phase 8) and the PCI and acceptance work (Phase 9), so FR-9 and NFR-5 cannot be met for live card traffic (EV-024, EV-025, EV-026, EV-089).
- Decision AD-039 (FR-9): preserves. The finding seeks to have FR-9 scoring in place from the first live payment.
- Decision AD-028 (NFR-5): preserves. The PCI DSS assessment would come before live card data is handled.
- Decision AD-023 (25 Pending Backlog item 4): refines. The pending FRV-1 contract becomes a critical-path item for go-live.
- Since the previous version: still open (was FND-021). Sections 27 and 28 are unchanged in 1.1.

### FND-006 A single CloudHSM in one AZ remains a single point of failure for all card payments, and its scaling trigger can never fire

- **risk** · scalability or failure mode · severity **high** · confidence 0.80 (high) · rank 4
- Disposition: **governance decision** (also: refinement now)

Every detokenise unwraps a DEK in the HSM with no caching, and the cluster has one HSM in ap-southeast-1a. Losing that AZ or HSM stops all card authorizations (about 55% of attempts) until a new HSM is restored from the daily backup. Cascading cannot help, because every candidate goes through the same Vault. The trigger for adding a second HSM (sustained card volume over 1,500 TPS) is above the design peak card volume of about 1,100 TPS, so the second HSM would never be added. This challenges the approved 'one HSM at launch' decision on the strength of the three document items cited, against the 99.95% NFR-3 target and the zero-AZ-loss posture in NFR-4.

- Where: p.10 §12.3 (NFR-3): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a."
- Where: p.11 §12.3: "cluster when sustained card volume exceeds 1,500 TPS. If the HSM is unreachable"
- Where: p.2 §1: "Card share of attempts (e-wallet ~30%, bank transfer ~15%) 54% 55%"
- Evidence EV-017 (doc, supports): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a." [doc:DOC-design_v2#p10/s12.3]
- Evidence EV-018 (doc, supports): "daily backups of the cluster to S3, from which a new HSM can be created in any AZ." [doc:DOC-design_v2#p11/s12.3]
- Evidence EV-019 (doc, supports): "cluster when sustained card volume exceeds 1,500 TPS. If the HSM is unreachable" [doc:DOC-design_v2#p11/s12.3]
- Evidence EV-020 (doc, supports): "Card share of attempts (e-wallet ~30%, bank transfer ~15%) 54% 55%" [doc:DOC-design_v2#p2/s1]
- Evidence EV-037 (inference, supports): "Peak card volume is about 2,000 TPS x 55% = 1,100 TPS, below the 1,500 TPS trigger, so the cluster stays at one HSM; a restore-from-backup outage would consume most of the roughly 22 minutes a month allowed by 99.95%." [inference:EV-037] derived from EV-017, EV-018, EV-019, EV-020
- Evidence EV-098 (doc, supports): "A second HSM will be added to the cluster when sustained card volume exceeds 1,500 TPS." [doc:DOC-design_v2#p11/s12.3]
- Evidence EV-053 (doc, supports): "inside the HSM; DEKs are not cached, so plaintext key material never persists in application memory." [doc:DOC-design_v2#p10/s12.1]
- Evidence EV-066 (inference, supports): "2,000 TPS × 55% ≈ 1,100 card TPS at the 2027 peak, below the 1,500 TPS trigger, so the second HSM is never added within the design horizon." [inference:EV-066] derived from EV-052, EV-020
- Recommendation: In Sections 12.3 and 24, run at least two HSMs in different AZs from launch, and base the trigger for further scaling on measured HSM utilisation, not card TPS. Add HSM and AZ loss to the NFR-4 AZ game day.
  - Issue: The HSM topology is sized for throughput but not for availability.
  - Rationale: NFR-3 and the AZ-loss posture in NFR-4 require card authorization to survive the loss of a single AZ.
  - Expected benefit: Card payments survive the loss of one AZ or one HSM, protecting NFR-3. (objectives: NFR-3, NFR-4)
  - Supporting evidence: EV-017, EV-019, EV-020, EV-037
  - Verification: In the AZ game day, terminating ap-southeast-1a leaves card authorizations succeeding within the NFR-2 limits.
- Next step: Payments platform owner (decision owner for Section 24): Re-decide 'one HSM at launch' against the NFR-3 budget and cost, and record the outcome in Section 24.
- Decision AD-008 (24 Confirmed Decisions - Vault): challenges. By the document's own figures (EV-017, EV-020, EV-098, EV-066), the 1,500 TPS trigger never fires at the roughly 1,100 card TPS peak, so 'one HSM at launch' leaves an AZ-level single point of failure that conflicts with NFR-3 and NFR-4.
- Decision AD-049 (NFR-3): preserves. The aim is to protect the 99.95% availability target.
- Decision AD-050 (NFR-4): preserves. The aim is to protect the AZ-loss recovery posture.
- Decision AD-001 (24 Confirmed Decisions - Cloud and primary region): preserves. Spreading HSMs across the three approved AZs is consistent with the region decision.
- Since the previous version: still open (was FND-006). Section 12.3 and the Vault decision are unchanged.

### FND-004 A cascade after a timeout can still produce duplicate authorizations; the 'cannot create a duplicate charge' claim is unchanged

- **risk** · scalability or failure mode · severity **high** · confidence 0.80 (high) · rank 5
- Disposition: **refinement now** (also: needs testing)

Section 11 still classes a non-response within 2,500 ms as retryable and discards late responses. Yet it says a cascade cannot create a duplicate charge because the previous attempt 'did not succeed'. A timed-out attempt may in fact have been approved, so the customer can end up with two authorization holds, and an orphaned approval has no reversal path. This conflicts with P1 and with the intent of FR-5 and FR-7. 1.1 made the CVC available for cascades, which keeps this path fully active.

- Where: p.10 §11.2 (FR-7): "succeed, cascading cannot create a duplicate charge: the ledger records only the approved attempt."
- Where: p.10 §11.2: "arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded."
- Where: p.10 §11.1: "acquirer HTTP 5xx; connection refused; no response within 2,500 ms"
- Evidence EV-011 (doc, supports): "succeed, cascading cannot create a duplicate charge: the ledger records only the approved attempt." [doc:DOC-design_v2#p10/s11.2]
- Evidence EV-012 (doc, supports): "arrive for an attempt after its 2,500 ms timeout are logged against the attempt and discarded." [doc:DOC-design_v2#p10/s11.2]
- Evidence EV-013 (doc, supports): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms" [doc:DOC-design_v2#p10/s11.1]
- Evidence EV-035 (inference, supports): "A timeout means the outcome is unknown, not failed; when a late approval is discarded, the issuer hold stays on the card while the second acquirer also approves." [inference:EV-035] derived from EV-011, EV-012, EV-013
- Evidence EV-084 (inference, supports): "A timeout means the outcome is unknown, not failed; discarding a late approval while cascading leaves a live issuer authorization that the ledger never sees, so the no-duplicate claim does not hold." [inference:EV-084] derived from EV-070, EV-012, EV-013
- Evidence EV-065 (inference, supports): "A timed-out attempt is of unknown outcome, not a failure, so discarding a late approval leaves an un-voided authorization at the first acquirer alongside the cascaded one." [inference:EV-065] derived from EV-049, EV-012
- Recommendation: In Section 11.2: classify timeouts and 5xx as 'unknown'; send a reversal (or a status query followed by a void) to the first acquirer before or alongside the cascade; on any late approval, reverse it automatically instead of discarding it; add a reconciliation exception type for unreversed orphaned approvals; delete the 'cannot create a duplicate charge' sentence.
  - Issue: Timeout and 5xx outcomes are treated as failed even though the first acquirer may have approved.
  - Rationale: P1 requires the payment record to be the truth; a discarded approval leaves an untracked hold on the customer's card.
  - Expected benefit: No double holds on customers, and the cascade remains safe to use under FR-7. (objectives: FR-7, FR-5, P1)
  - Supporting evidence: EV-011, EV-012, EV-035
  - Verification: Extend the FR-7 cascade simulation so the simulator approves attempt 1 after the timeout; the test passes when attempt 1 is reversed and only one hold remains.
- Decision AD-011 (24 Confirmed Decisions - Cascade policy): refines. The cascade triggers stay, but timeout and 5xx outcomes become 'unknown', with a reversal of the first attempt.
- Decision AD-031 (FR-7): preserves. The FR-7 cascade limits and scheme compliance are unchanged.
- Decision AD-033 (3 Foundational Principles): preserves. P1 requires provider outcomes to be reconciled into the payment record.
- Since the previous version: still open (was FND-016). Section 11.2 changed only for CVC handling; the duplicate-charge reasoning is unchanged.

### FND-005 Latency budget still leaves cascades out of the p99, although 3.8% of attempts are retryable

- **risk** · unsupported or incorrect claim · severity **high** · confidence 0.85 (high) · rank 6
- Disposition: **refinement now** (also: needs testing)

Section 21.1 still argues that cascades sit above the 99th percentile because fewer than 1% of card payments cascade. Section 10.5 reports 3.8% retryable outcomes, and every retryable outcome cascades. Any timeout-triggered cascade exceeds 2,500 ms, which is above the 1,500 ms NFR-2 limit that explicitly includes cascades. The NFR-2 benchmark injects 3.8% retryable outcomes, so the design as written is likely to fail its own acceptance test.

- Where: p.18 §21.1 (NFR-2): "move the p99 because fewer than 1% of card payments cascade;"
- Where: p.9 §10.5: "retryable outcomes - soft declines eligible for reattempt plus acquirer-side errors and timeouts - 3.8%."
- Where: p.3 §2.2 (NFR-2): "End-to-end p99 latency for a card authorization, measured at the API edge and including any cascade, shall not exceed 1,500 ms."
- Evidence EV-014 (doc, supports): "move the p99 because fewer than 1% of card payments cascade;" [doc:DOC-design_v2#p18/s21.1]
- Evidence EV-015 (doc, supports): "retryable outcomes - soft declines eligible for reattempt plus acquirer-side errors and timeouts - 3.8%." [doc:DOC-design_v2#p9/s10.5]
- Evidence EV-016 (doc, supports): "End-to-end p99 latency for a card authorization, measured at the API edge and including any cascade, shall not exceed 1,500 ms." [doc:DOC-design_v2#p3/s2.2]
- Evidence EV-036 (inference, supports): "About 3.8% of payments cascading puts the cascade path inside the slowest 1%, so the p99 is set by cascade latency (first attempt plus a second round trip of up to 1,100 ms, or more than 2,500 ms after a timeout), not by the 1,338 ms single-attempt sum." [inference:EV-036] derived from EV-014, EV-015, EV-016
- Evidence EV-064 (inference, supports): "With roughly 3.8% of card payments cascading, the p99 falls inside the cascade population, and any timeout-triggered cascade (≥2,500 ms plus a second round trip) exceeds the 1,500 ms NFR-2 limit." [inference:EV-064] derived from EV-048, EV-015, EV-013
- Evidence EV-013 (doc, supports): "acquirer HTTP 5xx; connection refused; no response within 2,500 ms" [doc:DOC-design_v2#p10/s11.1]
- Recommendation: Rework Section 21.1 to model the cascade path. Introduce an overall authorization deadline (for example, cap the per-attempt timeout so attempt 1 plus a cascade stays within 1,500 ms), or ask the requirement owner to restate NFR-2 so it excludes timeout-triggered cascades or uses a separate cascade percentile. Correct the '<1%' sentence.
  - Issue: The latency budget rests on a cascade rate contradicted by the document's own baseline.
  - Rationale: NFR-2 includes cascades, and the Section 26 benchmark injects 3.8% retryable outcomes.
  - Expected benefit: NFR-2 becomes achievable, or is consciously re-scoped, before build. (objectives: NFR-2, FR-7)
  - Supporting evidence: EV-014, EV-015, EV-036
  - Verification: The Section 26 NFR-2 benchmark, run with the 3.8% retryable mix including timeouts, meets the restated target.
- Decision AD-048 (NFR-2): preserves. The aim is to make NFR-2 achievable, or to have its owner restate it explicitly.
- Decision AD-011 (24 Confirmed Decisions - Cascade policy): refines. The recommended overall deadline and shorter per-attempt timeout adjust the 2,500 ms timeout trigger.
- Since the previous version: still open (was FND-005). Section 21.1 is unchanged in 1.1.

### FND-002 Cross-region idempotency lock relies on a conditional put to an eventually consistent, both-writable global table

- **risk** · unsupported or incorrect claim · severity **high** · confidence 0.70 (medium) · rank 7
- Disposition: **needs investigation** (also: needs testing)

New in 1.1: Section 9.4 claims that exactly one request can take the lock for a merchant and key regardless of which region receives it. However, each region writes its own local replica, and the table uses the default eventually consistent multi-region mode. Under asynchronous replication, a conditional put in Jakarta is checked against a replica that may not yet hold the IN_PROGRESS item written in Singapore, so both writes can succeed. That would allow duplicate authorizations during the partial outages and failovers that 9.4 is meant to protect, which breaks FR-5. The approved idempotency-store decision (both replicas writable) rests on this unverified claim, and the unreplicated Redis fast path adds a second gap.

- Where: p.8 §9.4 (FR-5, NFR-4): "exactly one request can acquire the lock for a given merchant and key regardless of which"
- Where: p.8 §9.4: "replicas in ap-southeast-1 and ap-southeast-3, using the default multi-Region eventual consistency mode."
- Where: p.19 §24: "merchant_id#idempotency_key, no indexes; replicas in ap-southeast-1 and ap-southeast-3, both writable)"
- Evidence EV-004 (doc, supports): "replicas in ap-southeast-1 and ap-southeast-3, using the default multi-Region eventual consistency mode." [doc:DOC-design_v2#p8/s9.4]
- Evidence EV-005 (doc, supports): "exactly one request can acquire the lock for a given merchant and key regardless of which" [doc:DOC-design_v2#p8/s9.4]
- Evidence EV-006 (doc, supports): "Payments API in each region reads and writes its local replica." [doc:DOC-design_v2#p8/s9.4]
- Evidence EV-007 (doc, supports): "merchant_id#idempotency_key, no indexes; replicas in ap-southeast-1 and ap-southeast-3, both writable)" [doc:DOC-design_v2#p19/s24]
- Evidence EV-034 (inference, supports): "A conditional write can only be checked against the state of the replica that receives it, so with asynchronous replication two regions can each accept attribute_not_exists(pk) for the same key before either write replicates; the global-uniqueness claim therefore needs verification against the platform's documented semantics." [inference:EV-034] derived from EV-004, EV-005, EV-006, EV-007
- Evidence EV-083 (inference, supports): "With both replicas writable, each region checking conditions against its local copy, and replication asynchronous, a duplicate arriving in the other region within the lag cannot see the first lock, so two regions can both acquire it; the exact conflict semantics of the global table must be confirmed." [inference:EV-083] derived from EV-005, EV-068, EV-069
- Evidence EV-121 (inference, supports): "With eventual consistency and region-local writes, a conditional put in one region is checked only against that region's replica, so two regions can each succeed within the replication lag — exactly the partial-outage window the design relies on." [inference:EV-121] derived from EV-095, EV-096
- Evidence EV-096 (doc, supports): "so a merchant retry that Route 53 sends to the Jakarta cell during a failover or a partial Singapore outage is deduplicated against the original request" [doc:DOC-design_v2#p8/s9.4]
- Recommendation: In Section 9.4, either (a) make Singapore the single writer for idempotency locks and let Jakarta take locks only after a declared regional failover (with a fencing step), or (b) adopt a strongly consistent multi-region mode if the platform supports one in these regions. Remove 'both writable' from Section 24 if (a) is chosen. Add a DR game-day case in which concurrent duplicates hit both regions.
  - Issue: The cross-region exactly-once lock claim is unverified and probably does not hold under eventual consistency with writes in both regions.
  - Rationale: FR-5 and the regional recovery posture in NFR-4 depend on this claim, and Section 27 marks the layer Ready.
  - Expected benefit: Merchant retries routed to Jakarta cannot cause duplicate downstream authorizations, so FR-5 holds during failover. (objectives: FR-5, NFR-4, P3)
  - Supporting evidence: EV-004, EV-005, EV-006, EV-007, EV-034
  - Verification: A game day sends the same merchant and key to both regions concurrently, and the acquirer simulator records exactly one authorization.
- Next step: Platform architect (Payments Core): Confirm the conditional-write and conflict-resolution semantics of DynamoDB global tables in the chosen consistency mode for ap-southeast-1/3, then choose option (a) or (b) and update Sections 9.4, 20.2 and 24.
- Decision AD-006 (24 Confirmed Decisions - Idempotency store): refines. The global table is kept but the lock authority may change; this is not a challenge because the global-table semantics (RQ-007) are unverified.
- Decision AD-037 (FR-5): preserves. The aim is to keep FR-5 at-most-one authorization holding during failover.
- Decision AD-004 (24 Confirmed Decisions - Disaster recovery): preserves. The regional DR posture stays; only the lock routing changes.
- Since the previous version: new in update. The global-table design and its uniqueness claim were added in 1.1 in response to the prior RPO finding.

### FND-013 The revised NFR-4 promise to recover loss-window payments from provider records has no working mechanism

- **risk** · unsupported or incorrect claim · severity **high** · confidence 0.80 (high) · rank 9
- Disposition: **refinement now** (also: needs testing)

v1.1 relaxed the regional RPO to 5 seconds and now requires every payment in the loss window to be recoverable from provider records. The mechanism in Section 20.2 queries providers for 'attempts submitted in the last 60 seconds', but those attempt rows sit in the Aurora writes that were lost, so the design has nothing to enumerate them from. T+1 reconciliation only sees captured settlement lines, and Section 16.2 turns lines without a matching attempt into exceptions rather than restored payments. Authorised-but-uncaptured payments, voids and refunds in the window therefore have no recovery path. The 4-second lag page is an alarm, not a bound, so the 5-second RPO is also not enforced. The NFR-4 game-day criterion cannot be checked because nothing defines how the set of payments in the window is known.

- Where: p.3 §2.2 (NFR-4): "On loss of the entire primary region, RPO shall not exceed 5 seconds, and every payment in the"
- Where: p.17 §20.2 (NFR-4): "Payments whose final writes fall in the lag window are recovered after failover by querying provider status APIs"
- Where: p.21 §26.2 (NFR-4): "measured loss window ≤ 5 s; every payment in the window is restored by provider"
- Evidence EV-028 (doc, supports): "for attempts submitted in the last 60 seconds, and by T+1 reconciliation against settlement lines." [doc:DOC-design_v2#p17/s20.2]
- Evidence EV-044 (doc, supports): "Matched payments transition to SETTLED and a settlement journal is posted. Unmatched and mismatched lines" [doc:DOC-design_v2#p13/s16.2]
- Evidence EV-045 (doc, supports): "typically under one second; lag pages at 4 seconds against the 5-second regional" [doc:DOC-design_v2#p17/s20.2]
- Evidence EV-062 (inference, supports): "Attempt records written in the lag window are exactly the ones absent after promotion, so the 60-second provider query has no attempt list to work from, and reconciliation will raise exceptions rather than restore uncaptured authorizations." [inference:EV-062] derived from EV-028, EV-044, EV-045
- Evidence EV-086 (inference, supports): "An alert at 4 s does not stop commits whose replication is still pending, so the RPO is a typical value rather than a bound. Recovery that starts from attempt records cannot enumerate attempts whose rows were lost, and cannot query providers that have no status endpoint." [inference:EV-086] derived from EV-072, EV-027, EV-028, EV-073
- Evidence EV-124 (inference, supports): "Attempts in the Aurora lag window are absent after promotion, so they cannot be enumerated for status queries, and the independently replicated idempotency table can reference payments that no longer exist." [inference:EV-124] derived from EV-101, EV-102
- Evidence EV-073 (doc, supports): "provider's status endpoint where one exists, and resolves the payment to AUTHORISED or FAILED" [doc:DOC-design_v2#p17/s20.3]
- Recommendation: In Section 20.2, name a replicated source of in-flight attempts, for example the payment_id and attempt identifiers held on the DynamoDB global-table idempotency records, written before submission. Define the recovery procedure for each payment type, including authorizations with no settlement line, and how an idempotency record that references a missing payment is reconciled. Either enforce the lag bound (for example, alert and shed writes) or restate RPO as a target with measured percentiles. In Section 26, require the game day to compare the provider-side attempt list against the restored records.
  - Issue: There is no replicated index of in-window attempts, and no recovery path for uncaptured payments.
  - Rationale: NFR-4 promises that every payment in the window is recoverable, and the DR test asserts it.
  - Expected benefit: Makes the NFR-4 regional RPO achievable and its game day measurable. (objectives: NFR-4, FR-5, P1)
  - Supporting evidence: EV-028, EV-044, EV-045, EV-062
  - Verification: In the regional game day, inject load, cut replication and fail over. Every simulator-side authorization is either present in the promoted database or restored by the procedure within RTO.
- Decision AD-004 (24 Confirmed Decisions - Disaster recovery): refines. The DR posture is kept, but a replicated attempt-intent source and a bound or restatement of the RPO are added.
- Decision AD-050 (NFR-4): preserves. The aim is to make NFR-4's recoverability promise executable and testable.
- Decision AD-006 (24 Confirmed Decisions - Idempotency store): refines. The recommendation uses the idempotency global table to carry attempt intent.
- Since the previous version: partially addressed (was FND-004). The impossible zero regional RPO was replaced by 5 seconds, which is a real fix. The new provider-records recovery promise has no mechanism and its test cannot be checked.

## Gaps

### FND-014 The regional DR plan leaves out the CDE (Vault, CloudHSM, Card Adapter), so card payments cannot meet the 30-minute RTO

- **gap** · missing or unverifiable requirement · severity **high** · confidence 0.75 (medium) · rank 8
- Disposition: **refinement now** (also: governance decision)

NFR-4 sets a 30-minute RTO for loss of the primary region. Section 20.2 now describes a warm API cell, the Aurora secondary and the DynamoDB replica in ap-southeast-3, but says nothing about the CDE account, the card vault store, the KEKs or the Card Adapter. The single HSM and its backups are in ap-southeast-1. Card tokens held in the Jakarta replica therefore cannot be detokenised, and card authorizations (about 55% of attempts) cannot resume within RTO. The NFR-4 game day does not say whether card authorization is part of 'service restored'.

- Where: p.17 §20.2 (NFR-4): "Regional failover is a runbook-driven managed operation (promote the Aurora secondary, scale up the standby"
- Where: p.10 §12.3: "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a."
- Where: p.3 §2.2 (NFR-4): "loss window shall be recoverable from provider records through reconciliation. Recovery time objective shall be 30 minutes in both"
- Evidence EV-022 (doc, supports): "Regional failover is a runbook-driven managed operation (promote the Aurora secondary, scale up the standby" [doc:DOC-design_v2#p17/s20.2]
- Evidence EV-017 (doc, supports): "The Vault's KEKs are held in an AWS CloudHSM cluster with one HSM in ap-southeast-1a." [doc:DOC-design_v2#p10/s12.3]
- Evidence EV-046 (doc, supports): "cross-region; on regional failover they are recreated empty in ap-southeast-3 from infrastructure-as-code." [doc:DOC-design_v2#p17/s20.2]
- Evidence EV-063 (inference, supports): "No section places vault data, KEKs or the Card Adapter in ap-southeast-3, so card detokenisation, and therefore card authorization, is unavailable after regional failover regardless of the API cell." [inference:EV-063] derived from EV-022, EV-017, EV-046
- Evidence EV-038 (inference, supports): "The runbook and data-placement sections never list a Vault replica or HSM cluster in ap-southeast-3, so after regional loss there is nothing to detokenise card tokens against and card authorizations cannot resume." [inference:EV-038] derived from EV-021, EV-022, EV-023
- Evidence EV-087 (inference, supports): "Detokenisation needs Vault records and KEKs that exist only in ap-southeast-1, so after regional loss no card authorization can be submitted from the Jakarta cell until the CDE is rebuilt elsewhere, a path with no stated design or duration." [inference:EV-087] derived from EV-017, EV-018, EV-074, EV-075
- Evidence EV-074 (doc, supports): "The API tier runs a warm standby cell in ap-southeast-3" [doc:DOC-design_v2#p17/s20.2]
- Recommendation: Add a CDE DR subsection to Section 20.2 covering: vault data replication to ap-southeast-3, a KEK and HSM cluster or cross-region backup restore in Jakarta with timed steps, Card Adapter deployment, and acquirer connectivity (IP allow-lists) from Jakarta. Alternatively, state that card payments are excluded from the regional RTO and have the owner accept that risk. Extend the NFR-4 game day to include a card authorization after failover.
  - Issue: The CDE has no cross-region recovery design.
  - Rationale: The NFR-4 RTO applies to the card authorizations that make up most of the volume, and the Vault is on that path.
  - Expected benefit: NFR-4 RTO becomes achievable for card payments, or is explicitly scoped. (objectives: NFR-4, NFR-3, NFR-5)
  - Supporting evidence: EV-022, EV-017, EV-046, EV-063
  - Verification: In the regional game day, a card authorization succeeds from ap-southeast-3 within 30 minutes of failure injection.
- Next step: Head of Platform Engineering with the PCI programme lead: Decide whether the CDE is in regional DR scope, and design the vault and HSM replication within the PCI segmentation model.
- Decision AD-004 (24 Confirmed Decisions - Disaster recovery): refines. The DR decision is extended to cover the CDE, or card payments are explicitly excluded from the regional RTO.
- Decision AD-008 (24 Confirmed Decisions - Vault): refines. The Vault and HSM need a cross-region key-availability path.
- Decision AD-002 (24 Confirmed Decisions - Compute): preserves. A DR CDE would keep the separate-account CDE model.
- Decision AD-028 (NFR-5): preserves. Any DR CDE must be listed in the Section 12.2 scope.
- Decision AD-050 (NFR-4): preserves. The aim is to make the 30-minute regional RTO true for card payments.
- Since the previous version: new in update. Latent in v1.0. It became visible with the v1.1 warm-cell and RPO rework, which still leaves the CDE out.

### FND-020 State machine still lacks transitions that FR-1, FR-15 and Section 16.2 need, and the FR-2 test cannot detect missing ones

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.80 (high) · rank 10
- Disposition: **refinement now**

Section 7.2 is unchanged. It has no PARTIALLY_REFUNDED self-transition for repeated partial refunds, no way to reach SETTLED once a payment has been refunded before settlement (although Section 16.2 settles matched payments), no failure exit from REQUIRES_ACTION (for example a failed 3DS challenge or wallet payment), and no state for REVIEW 'authorize-and-hold-capture'. The FR-2 property test checks only that no disallowed transition occurs, so these omissions would pass it.

- Where: p.20 §26.1 (FR-2): "Randomised event sequences (10^6 per run) never produce a transition outside Section 7.2; every"
- Where: p.2 §2.1 (FR-1): "The platform shall expose one versioned merchant API supporting create payment, authorize, capture (full and partial), void, refund"
- Where: p.13 §16.2 (FR-11): "Matched payments transition to SETTLED and a settlement journal is posted."
- Evidence EV-032 (doc, supports): "Randomised event sequences (10^6 per run) never produce a transition outside Section 7.2; every" [doc:DOC-design_v2#p20/s26.1]
- Evidence EV-030 (doc, supports): "The platform shall expose one versioned merchant API supporting create payment, authorize, capture (full and partial), void, refund" [doc:DOC-design_v2#p2/s2.1]
- Evidence EV-054 (doc, supports): "REQUIRES_ACTION -> AUTHORISING | CANCELLED (expiry)" [doc:DOC-design_v2#p6/s7.2]
- Evidence EV-067 (inference, supports): "Section 7.2 lists only PARTIALLY_REFUNDED -> REFUNDED and gives no refunded-to-SETTLED or REQUIRES_ACTION -> FAILED edge, so legitimate events required by FR-1, FR-15 and Section 16.2 have no permitted transition." [inference:EV-067] derived from EV-030, EV-054
- Evidence EV-040 (inference, supports): "Section 7.2 lists only PARTIALLY_REFUNDED -> REFUNDED and REQUIRES_ACTION -> AUTHORISING | CANCELLED, so a second partial refund or a declined 3DS/wallet payment has no legal transition, and a test that forbids extra transitions cannot catch absent ones." [inference:EV-040] derived from EV-030, EV-031, EV-032
- Evidence EV-031 (doc, supports): "REFUNDED / PARTIALLY_REFUNDED One or more refunds succeeded against a captured or succeeded payment." [doc:DOC-design_v2#p6/s7.1]
- Recommendation: Extend Section 7.2 with: PARTIALLY_REFUNDED -> PARTIALLY_REFUNDED; settlement as an attribute or as transitions from the refunded states; REQUIRES_ACTION -> FAILED; repeated partial captures; and the REVIEW hold. Add a positive FR-2 criterion that every operation in FR-1 is reachable from each state that should accept it.
  - Issue: The transition table is incomplete, and the test only checks for forbidden transitions.
  - Rationale: FR-2 forbids any transition that is not listed, so these omissions block required operations.
  - Expected benefit: FR-1, FR-15 and FR-11 operations become executable, and FR-2 can verify completeness. (objectives: FR-1, FR-2, FR-15, FR-11)
  - Supporting evidence: EV-032, EV-030, EV-054, EV-067
  - Verification: The FR-2 test includes a reachability matrix: every (state, operation) pair expected to succeed does succeed.
- Decision AD-036 (FR-2): preserves. Adding the missing transitions lets FR-2 hold without blocking FR-1 and FR-15 operations.
- Decision AD-041 (FR-11): preserves. Refunded payments can then reach a settled status, so FR-11 matching works.
- Since the previous version: still open (was FND-022). Sections 7.2 and 26.1 (FR-2) are unchanged.

### FND-043 No cross-border transfer or localisation basis for five markets' data, now replicated to Jakarta as well

- **gap** · security privacy gap · severity **medium** · confidence 0.60 (medium) · rank 14
- Disposition: **governance decision** · already acknowledged in the document

All primary data sits in Singapore. Version 1.1 adds a DynamoDB idempotency replica in Jakarta alongside the Aurora secondary, and PAN and hashed identifiers go to FRV-1 for a regional consortium graph. NFR-7 names each market's law, but the design states no transfer basis, no localisation assessment (notably for Indonesian payment data) and no vendor-sharing assessment. The FRV-1 DPA is pending under Backlog item 4. This review adds that the data-placement decision itself also needs per-market sign-off before build, not only the Phase 9 DPO review.

- Where: p.17 §19.1 (NFR-7): "The Aurora Global Database secondary and the DynamoDB idempotency replica in ap-southeast-3 (Jakarta) support"
- Where: p.11 §13.1 (NFR-7): "FRV-1's consortium velocity graph is keyed on the full card number, which allows it to link the same card across its"
- Evidence EV-111 (doc, supports): "The Aurora Global Database secondary and the DynamoDB idempotency replica in ap-southeast-3 (Jakarta) support" [doc:DOC-design_v2#p17/s19.1]
- Evidence EV-112 (doc, supports): "4. FRV-1 contract - data processing agreement and SLA finalisation." [doc:DOC-design_v2#p20/s25]
- Evidence EV-097 (doc, supports): "The Fraud Hook obtains the PAN through the Vault's detokenise operation, using the Card Adapter client library and service role." [doc:DOC-design_v2#p11/s13.1]
- Recommendation: Add a data-residency subsection to Section 19.1: for each market, the data categories, storage regions, transfer mechanism, any localisation constraints, and the FRV-1 sharing basis. Make sign-off a Phase 1 gate.
  - Issue: The data-residency and transfer basis is undocumented for a multi-market design.
  - Rationale: NFR-7 requires compliance with each market's law, and placement choices are costly to reverse after build.
  - Expected benefit: NFR-7 can be met without re-platforming later. (objectives: NFR-7)
  - Supporting evidence: EV-111, EV-112
  - Verification: DPO and legal sign-off per market before Phase 1 is complete.
- Next step: Group DPO with regional legal counsel: Produce the per-market transfer and localisation assessment before Phase 1 is complete.
- Decision AD-030 (NFR-7): preserves. The aim is to show NFR-7 compliance for each market.
- Decision AD-004 (24 Confirmed Decisions - Disaster recovery): preserves. Jakarta replication stays, subject to a documented transfer basis.
- Decision AD-023 (25 Pending Backlog item 4): refines. The FRV-1 DPA must cover the cross-border sharing basis.
- Since the previous version: still open (was FND-051). Not addressed. 1.1 extends the replicated footprint to DynamoDB in Jakarta.

### FND-041 Events already relayed to the Singapore MSK but not yet consumed are lost on regional failover

- **gap** · scalability or failure mode · severity **medium** · confidence 0.60 (medium) · rank 15
- Disposition: **refinement now**

The outbox relay marks rows as published once they reach MSK. On regional failover, MSK is recreated empty in Jakarta, so events published but not yet consumed by the Webhook Dispatcher, Reconciliation or Payouts are gone. The promoted outbox treats them as delivered. The result is silently missing webhooks, which breaks FR-12, and missing downstream inputs, with no stated replay step.

- Where: p.17 §20.2 (FR-12, NFR-4): "MSK and ElastiCache are not replicated cross-region; on regional failover they are recreated empty in ap-southeast-3 from infrastructure-as-code."
- Where: p.6 §5: "Topics per domain event; outbox relay publishes committed events."
- Evidence EV-108 (doc, supports): "MSK and ElastiCache are not replicated cross-region; on regional failover they are recreated empty in ap-southeast-3 from infrastructure-as-code." [doc:DOC-design_v2#p17/s20.2]
- Evidence EV-109 (doc, supports): "Topics per domain event; outbox relay publishes committed events." [doc:DOC-design_v2#p6/s5]
- Evidence EV-126 (inference, supports): "Outbox rows with published_at set before the failure point to events that existed only in the lost Singapore cluster, so nothing re-sends them after failover." [inference:EV-126] derived from EV-108, EV-109
- Recommendation: In the Section 20.2 runbook, after promotion, reset published_at for outbox rows created in the last N minutes (N greater than the maximum consumer lag) and let the relay republish them. Consumers deduplicate on event_id.
  - Issue: There is no step to replay events that were in flight between the outbox and consumers.
  - Rationale: P7 already makes consumers idempotent, so replaying events is safe.
  - Expected benefit: Webhook and downstream completeness after failover (FR-12, NFR-11). (objectives: FR-12, NFR-11, P7)
  - Supporting evidence: EV-108, EV-109, EV-126
  - Verification: In the regional game day, every state change from the 10 minutes before failover produces exactly one webhook as seen by merchant simulators.
- Decision AD-005 (24 Confirmed Decisions - Event bus): preserves. MSK stays unreplicated; a replay step is added instead.
- Decision AD-004 (24 Confirmed Decisions - Disaster recovery): refines. An outbox republish step is added to the regional failover runbook.
- Decision AD-042 (FR-12): preserves. FR-12 webhook completeness holds across failover.
- Since the previous version: new in update. This was also present in 1.0 but not raised before. 1.1 keeps MSK unreplicated.

### FND-044 Report publication has no defined behaviour for a late or missing settlement file

- **gap** · scalability or failure mode · severity **medium** · confidence 0.65 (medium) · rank 16
- Disposition: **refinement now**

Incremental matching and the 09:00 SGT deadline resolve the arithmetic: publication is estimated at about 08:09 SGT at 2027 volume. However, netting, payouts and reports still wait for 'the last file of business day T'. No cut-off or partial-publication rule is stated, so a single late provider file, for example from ACQ-TH1 with only about 50 minutes of margin, blocks every merchant's report and payout computation.

- Where: p.13 §16.2 (NFR-8): "only cross-provider netting, payout computation and report generation wait for the last file of business day T"
- Where: p.13 §16.2 (NFR-8): "at 2027 volume, about 14 and 25 minutes (≈ 08:09 SGT), inside the 09:00 SGT target in NFR-8"
- Evidence EV-113 (doc, supports): "only cross-provider netting, payout computation and report generation wait for the last file of business day T" [doc:DOC-design_v2#p13/s16.2]
- Evidence EV-114 (doc, contrary): "at 2027 volume, about 14 and 25 minutes (≈ 08:09 SGT), inside the 09:00 SGT target in NFR-8" [doc:DOC-design_v2#p13/s16.2]
- Recommendation: In Section 16.2, add a cut-off (for example 08:15 SGT) after which reports are published for merchants whose providers have all delivered, and marked provisional for the rest. Add per-provider late-file alerting and a rule for payouts that depend on missing files.
  - Issue: Late or missing files have no handling.
  - Rationale: Provider file delays are routine, and NFR-8 and FR-17 depend on on-time completion.
  - Expected benefit: NFR-8 and FR-17 are met despite single-provider delays. (objectives: NFR-8, FR-17)
  - Supporting evidence: EV-113
  - Verification: Run the NFR-8 replay with the ACQ-TH1 file withheld. Unaffected merchants' reports still publish by 09:00 SGT.
- Decision AD-016 (24 Confirmed Decisions - Reconciliation): refines. A late-file cut-off and partial-publication rule are added to the incremental reconciliation decision.
- Decision AD-051 (NFR-8): preserves. The aim is to protect the 09:00 SGT publication target.
- Decision AD-032 (16.2 / NFR-8): preserves. The deadline Finance confirmed is unchanged.
- Decision AD-046 (FR-17): preserves. FR-17 payout schedules are protected from a single late file.
- Since the previous version: partially addressed (was FND-020). The deadline and incremental matching fix the timing arithmetic. Late or missing file handling is still absent.

## Ambiguities

### FND-022 Section 18.1 still says 'optional TOTP', contradicting the mandatory MFA introduced in Section 18.3

- **ambiguity** · internal contradiction · severity **low** · confidence 0.85 (high) · rank 17
- Disposition: **refinement now**

v1.1 made MFA (TOTP or WebAuthn) mandatory for every merchant user and added two-person approval and a cooling-off period for payout-account changes. This closes the prior account-takeover path, and FR-13's test checks it. However, Section 18.1 still describes portal and Admin API authentication as 'email and password, with optional TOTP' and does not mention WebAuthn. It is also unclear how Admin API automation clients meet the mandatory MFA and step-up rules.

- Where: p.14 §18.1 (FR-13): "with optional TOTP), and both authorise every call against the user's role."
- Where: p.14 §18.3: "Multi-factor authentication (TOTP or WebAuthn) is mandatory for every merchant user; a user without an"
- Evidence EV-058 (doc, supports): "with optional TOTP), and both authorise every call against the user's role." [doc:DOC-design_v2#p14/s18.1]
- Evidence EV-059 (doc, supports): "Multi-factor authentication (TOTP or WebAuthn) is mandatory for every merchant user; a user without an" [doc:DOC-design_v2#p14/s18.3]
- Evidence EV-117 (doc, supports): "A payout bank account change is requested by a Finance or Owner user and must be approved by a different Owner" [doc:DOC-design_v2#p14/s18.4]
- Recommendation: Amend Section 18.1 to reference Section 18.3, with MFA mandatory and TOTP or WebAuthn accepted. Specify how the Admin API authenticates automation (for example, scoped admin tokens issued only after a step-up session) and which money-moving Admin API actions require interactive step-up.
  - Issue: Two sections state conflicting authentication policies.
  - Rationale: An implementer of the Admin API could follow Section 18.1 and leave MFA optional, which would reopen the payout-redirect path.
  - Expected benefit: A single unambiguous authentication policy for FR-13. (objectives: FR-13, P8, P9)
  - Supporting evidence: EV-058, EV-059
  - Verification: The FR-13 role-matrix test runs against both the portal and the Admin API, and a call without MFA fails on both.
- Decision AD-018 (24 Confirmed Decisions - Merchant user MFA): preserves. Section 18.1 is aligned with the approved mandatory-MFA decision, and the single-Owner case is defined.
- Decision AD-043 (FR-13): preserves. FR-13 admin capabilities keep consistent controls.
- Decision AD-026 (25 Pending Backlog item 7): refines. The authentication model for Admin API automation belongs with the pending Admin API schemas.
- Since the previous version: partially addressed (was FND-046). Sections 18.2–18.4 are a real fix: mandatory MFA, step-up, two-person approval and a 48-hour cooling-off. Section 18.1 was not updated and now contradicts them.

## Unresolved assumptions

### FND-031 Network tokens 'from launch' depend on a token-requestor application not yet submitted

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.75 (medium) · rank 13
- Disposition: **governance decision** · already acknowledged in the document

Section 24 confirms network tokens as the primary card-on-file credential from launch, and Phase 3 includes card-on-file with network tokens marked as not depending on open items. Backlog item 2 states that the VTS/MDES token-requestor registration, the TSP agreement and certification have not been applied for. Scheme registration and certification lead times are therefore on the critical path for FR-14, and the FR-14 test cannot run without them, yet Section 27 does not track this.

- Where: p.19 §24 (FR-14): "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch"
- Where: p.20 §25: "the commercial agreement with a token service provider; certification test plan. Application not yet submitted."
- Evidence EV-081 (doc, supports): "Network tokens (VTS/MDES) as the primary credential for all card-on-file and recurring payments from launch" [doc:DOC-design_v2#p19/s24]
- Evidence EV-082 (doc, supports): "the commercial agreement with a token service provider; certification test plan. Application not yet submitted." [doc:DOC-design_v2#p20/s25]
- Evidence EV-091 (inference, supports): "A confirmed 'from launch' decision cannot be met while the prerequisite scheme registration has not started, so either the launch date or the credential decision is at risk." [inference:EV-091] derived from EV-081, EV-082
- Recommendation: Submit the token-requestor application now and add its milestone to Sections 27 and 28. Mark Phase 3 card-on-file as 'Partially - Backlog item 2'. Define the interim behaviour (PAN with stored-credential indicators) and its exit criterion.
  - Issue: A confirmed decision depends on an external registration that has not started.
  - Rationale: Without TRID registration no network tokens can be provisioned, so card-on-file would run on PAN, contrary to the decision.
  - Expected benefit: Keeps FR-14 achievable and the go-live plan realistic. (objectives: FR-14)
  - Supporting evidence: EV-081, EV-082, EV-091
  - Verification: FR-14 stored-credential test passes against scheme test cards after registration.
- Next step: Card partnerships manager: Submit the VTS/MDES token-requestor applications and report expected certification dates.
- Decision AD-010 (24 Confirmed Decisions - Card-on-file credential): refines. 'From launch' needs an interim PAN-with-indicators path and an exit criterion, because the prerequisite is pending.
- Decision AD-021 (25 Pending Backlog item 2): refines. The pending TRID registration is put on the critical path with a milestone.
- Decision AD-044 (FR-14): preserves. FR-14 remains the target.
- Since the previous version: still open (was FND-036). Unchanged in v1.1. The backlog item still reads 'not yet submitted' and Phase 3 is still marked ready.

## Validation needs

### FND-021 FR-5 concurrency clause conflicts with the 409 response, and the replay test still checks only sequential duplicates

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.75 (medium) · rank 11
- Disposition: **needs testing** (also: refinement now)

FR-5 requires an identical response 'including when duplicate requests arrive concurrently', while Section 9.1 returns HTTP 409 to an in-flight duplicate. The FR-5 test still resends only after the first response has arrived. It does not exercise concurrent duplicates, sweeper-recovered IN_PROGRESS records, the Redis-down path or the new cross-region path, which are the paths where duplicate authorizations would occur.

- Where: p.20 §26.1 (FR-5): "Send a create-payment request; after its response is received, resend the identical request with the same"
- Where: p.3 §2.1 (FR-5): "shall return the identical response, including when duplicate requests arrive concurrently."
- Where: p.8 §9.1: "While the first request is in flight, a duplicate receives HTTP 409 request_in_progress with Retry-After: 1."
- Evidence EV-055 (doc, supports): "Send a create-payment request; after its response is received, resend the identical request with the same" [doc:DOC-design_v2#p20/s26.1]
- Evidence EV-056 (doc, supports): "shall return the identical response, including when duplicate requests arrive concurrently." [doc:DOC-design_v2#p3/s2.1]
- Evidence EV-057 (doc, supports): "While the first request is in flight, a duplicate receives HTTP 409 request_in_progress with Retry-After: 1." [doc:DOC-design_v2#p8/s9.1]
- Recommendation: Reword FR-5: 'concurrent duplicates receive 409 or the identical final response; at most one downstream effect'. Add FR-5 test cases for N parallel duplicates, Redis down, a pod crash with sweeper completion, and two regions.
  - Issue: The requirement and the contract disagree, and the test leaves out the concurrent and failure paths.
  - Rationale: An acceptance criterion that does not exercise the concurrent case cannot validate FR-5.
  - Expected benefit: FR-5 is demonstrably met on the paths where duplicates actually arise. (objectives: FR-5)
  - Supporting evidence: EV-055, EV-056, EV-057
  - Verification: Across all the added cases, the acquirer simulator records exactly one authorization per (merchant, key).
- Next step: QA lead, Payments Core: Add the concurrent, failure-path and cross-region FR-5 cases to the Phase 9 test plan.
- Decision AD-037 (FR-5): refines. The FR-5 concurrency wording is aligned with the 409 contract, and the test is extended.
- Since the previous version: still open (was FND-023). FR-5, Section 9.1 and the FR-5 test are unchanged. The v1.1 global table adds a further untested path.

### FND-030 CVC held across cascade attempts relies on an undocumented reading of 'completion of authorization'; PCI DSS version cited may be superseded

- **validation need** · external constraint violation · severity **medium** · confidence 0.60 (medium) · rank 12
- Disposition: **needs investigation**

v1.1 fixes the main defect: CVC is now deleted at the final authorization outcome (TTL 15 minutes), incremental and MIT authorizations no longer use it, and the citation now points to the before-authorization requirements. One premise remains open. The design treats a decline from the first acquirer as not completing authorization, so it can re-present the CVC to a second acquirer. Whether an assessor accepts that reading is not recorded. NFR-5/NFR-6 also name PCI DSS v4.0, which may have been superseded by the time the 2027 assessment takes place; this should be confirmed.

- Where: p.10 §11.2 (NFR-6): "which is still held because the authorization process has not completed"
- Where: p.11 §12.4 (NFR-6): "The Vault holds it encrypted under a separate KEK in a short-lived store"
- Where: p.3 §2.2 (NFR-5): "The platform shall be assessed as a PCI DSS v4.0 Level 1 service provider."
- Evidence EV-078 (doc, supports): "which is still held because the authorization process has not completed" [doc:DOC-design_v2#p10/s11.2]
- Evidence EV-079 (doc, contrary): "The Vault holds it encrypted under a separate KEK in a short-lived store" [doc:DOC-design_v2#p11/s12.4]
- Evidence EV-080 (doc, supports): "The platform shall be assessed as a PCI DSS v4.0 Level 1 service provider." [doc:DOC-design_v2#p3/s2.2]
- Evidence EV-090 (inference, supports): "The compliance of cross-acquirer CVC re-presentation depends on where the assessor places 'completion of authorization' for a multi-attempt payment, which the design asserts but does not evidence." [inference:EV-090] derived from EV-078, EV-079
- Evidence EV-106 (doc, supports): "including the card verification code, which is still held because the authorization process has not completed" [doc:DOC-design_v2#p10/s11.2]
- Recommendation: Obtain a written QSA position on holding the CVC across cascade attempts within one payment, and record it in the PCI DSS Scoping Memo referenced from Section 12.4. Confirm which PCI DSS version applies at the planned assessment date and update NFR-5/NFR-6 accordingly. If the QSA disagrees, define cascade behaviour without the CVC per acquirer.
  - Issue: The compliance of the CVC cascade path rests on an unrecorded interpretation, and the standard version may not be current.
  - Rationale: If the QSA disagrees, cross-acquirer cascades would have to drop the CVC, which would change acquirer behaviour and the 31% recovery premise.
  - Expected benefit: De-risks NFR-5 (Report on Compliance) and NFR-6 before the Vault is built in Phase 2. (objectives: NFR-5, NFR-6, FR-7)
  - Supporting evidence: EV-078, EV-080, EV-090
  - Verification: QSA memo filed, and NFR-6 Vault SAD test retained.
- Next step: PCI compliance lead: Request a QSA interpretation on CVC retention across cascade attempts, and confirm the applicable standard version.
- Decision AD-009 (24 Confirmed Decisions - CVC handling): preserves. The CVC decision stays pending QSA confirmation of the cascade interpretation.
- Decision AD-029 (NFR-6): preserves. The aim is to confirm that the NFR-6 SAD constraint is met.
- Decision AD-028 (NFR-5): preserves. This de-risks the NFR-5 Report on Compliance.
- Decision AD-031 (FR-7): preserves. Cascade behaviour may need adjusting only if the QSA disagrees.
- Since the previous version: partially addressed (was FND-029). Retention until settlement or 72 h and the use of CVC for incremental authorizations have been removed, and the citations corrected. What remains is the cascade interpretation and the version currency.

## Recommended refinements

| Finding | Change | Expected benefit |
|---|---|---|
| FND-001 | In Sections 9.2 and 24, change the fast-path key to idem:resp:{merchant_id}#{idempotency_key}. Store the request_hash with the cached response and compare it on every hit; on a mismatch, fall through to the durable path so it returns 422. Add two cases to the FR-5 test in Section 26: two merchants using the same key, and the same key with a modified body while the fast-path entry is warm. | Prevents cross-merchant disclosure of payment data and silently lost payments, and makes the 422 behaviour in FR-5 hold. |
| FND-003 | Decide between: (a) send FRV-1 a keyed PAN fingerprint or network token in place of the PAN, accepting some loss of scoring quality; (b) have a CDE-resident component call FRV-1 with the PAN; or (c) bring the Fraud Hook into the CDE with its own service identity, and update P2 and Section 12.2. Record the choice in Sections 13.1 and 24. | Keeps the CDE as declared for NFR-5 and restores P2/P9. |
| FND-008 | In Section 28, move go-live after Phases 8 and 9 (at least the PCI assessment, load test and the FR-5/FR-9 tests). If that is not acceptable, record a risk acceptance with interim controls (for example, rules-only fraud screening, volume caps) and add it to Section 27. | The first cohort launches meeting FR-9, NFR-5 and the Section 26 criteria. |
| FND-006 | In Sections 12.3 and 24, run at least two HSMs in different AZs from launch, and base the trigger for further scaling on measured HSM utilisation, not card TPS. Add HSM and AZ loss to the NFR-4 AZ game day. | Card payments survive the loss of one AZ or one HSM, protecting NFR-3. |
| FND-004 | In Section 11.2: classify timeouts and 5xx as 'unknown'; send a reversal (or a status query followed by a void) to the first acquirer before or alongside the cascade; on any late approval, reverse it automatically instead of discarding it; add a reconciliation exception type for unreversed orphaned approvals; delete the 'cannot create a duplicate charge' sentence. | No double holds on customers, and the cascade remains safe to use under FR-7. |
| FND-005 | Rework Section 21.1 to model the cascade path. Introduce an overall authorization deadline (for example, cap the per-attempt timeout so attempt 1 plus a cascade stays within 1,500 ms), or ask the requirement owner to restate NFR-2 so it excludes timeout-triggered cascades or uses a separate cascade percentile. Correct the '<1%' sentence. | NFR-2 becomes achievable, or is consciously re-scoped, before build. |
| FND-002 | In Section 9.4, either (a) make Singapore the single writer for idempotency locks and let Jakarta take locks only after a declared regional failover (with a fencing step), or (b) adopt a strongly consistent multi-region mode if the platform supports one in these regions. Remove 'both writable' from Section 24 if (a) is chosen. Add a DR game-day case in which concurrent duplicates hit both regions. | Merchant retries routed to Jakarta cannot cause duplicate downstream authorizations, so FR-5 holds during failover. |
| FND-014 | Add a CDE DR subsection to Section 20.2 covering: vault data replication to ap-southeast-3, a KEK and HSM cluster or cross-region backup restore in Jakarta with timed steps, Card Adapter deployment, and acquirer connectivity (IP allow-lists) from Jakarta. Alternatively, state that card payments are excluded from the regional RTO and have the owner accept that risk. Extend the NFR-4 game day to include a card authorization after failover. | NFR-4 RTO becomes achievable for card payments, or is explicitly scoped. |
| FND-013 | In Section 20.2, name a replicated source of in-flight attempts, for example the payment_id and attempt identifiers held on the DynamoDB global-table idempotency records, written before submission. Define the recovery procedure for each payment type, including authorizations with no settlement line, and how an idempotency record that references a missing payment is reconciled. Either enforce the lag bound (for example, alert and shed writes) or restate RPO as a target with measured percentiles. In Section 26, require the game day to compare the provider-side attempt list against the restored records. | Makes the NFR-4 regional RPO achievable and its game day measurable. |
| FND-020 | Extend Section 7.2 with: PARTIALLY_REFUNDED -> PARTIALLY_REFUNDED; settlement as an attribute or as transitions from the refunded states; REQUIRES_ACTION -> FAILED; repeated partial captures; and the REVIEW hold. Add a positive FR-2 criterion that every operation in FR-1 is reachable from each state that should accept it. | FR-1, FR-15 and FR-11 operations become executable, and FR-2 can verify completeness. |
| FND-021 | Reword FR-5: 'concurrent duplicates receive 409 or the identical final response; at most one downstream effect'. Add FR-5 test cases for N parallel duplicates, Redis down, a pod crash with sweeper completion, and two regions. | FR-5 is demonstrably met on the paths where duplicates actually arise. |
| FND-030 | Obtain a written QSA position on holding the CVC across cascade attempts within one payment, and record it in the PCI DSS Scoping Memo referenced from Section 12.4. Confirm which PCI DSS version applies at the planned assessment date and update NFR-5/NFR-6 accordingly. If the QSA disagrees, define cascade behaviour without the CVC per acquirer. | De-risks NFR-5 (Report on Compliance) and NFR-6 before the Vault is built in Phase 2. |
| FND-031 | Submit the token-requestor application now and add its milestone to Sections 27 and 28. Mark Phase 3 card-on-file as 'Partially - Backlog item 2'. Define the interim behaviour (PAN with stored-credential indicators) and its exit criterion. | Keeps FR-14 achievable and the go-live plan realistic. |
| FND-043 | Add a data-residency subsection to Section 19.1: for each market, the data categories, storage regions, transfer mechanism, any localisation constraints, and the FRV-1 sharing basis. Make sign-off a Phase 1 gate. | NFR-7 can be met without re-platforming later. |
| FND-041 | In the Section 20.2 runbook, after promotion, reset published_at for outbox rows created in the last N minutes (N greater than the maximum consumer lag) and let the relay republish them. Consumers deduplicate on event_id. | Webhook and downstream completeness after failover (FR-12, NFR-11). |
| FND-044 | In Section 16.2, add a cut-off (for example 08:15 SGT) after which reports are published for merchants whose providers have all delivered, and marked provisional for the rest. Add per-provider late-file alerting and a rule for payouts that depend on missing files. | NFR-8 and FR-17 are met despite single-provider delays. |
| FND-022 | Amend Section 18.1 to reference Section 18.3, with MFA mandatory and TOTP or WebAuthn accepted. Specify how the Admin API authenticates automation (for example, scoped admin tokens issued only after a step-up session) and which money-moving Admin API actions require interactive step-up. | A single unambiguous authentication policy for FR-13. |

## Areas where no change is needed

- FND-046 Payout bank account change controls now protect against account takeover: These controls meet P9 separation of duties and protect FR-17 payouts. The FR-13 test covers both the approval and the cancellation paths.
- FND-047 DynamoDB idempotency key and capacity sizing now spread the largest merchant's load: A high-cardinality key and WCU-based sizing remove the hot-partition risk for NFR-1. The remaining cross-region concern is covered in FND-002.
- SA-001 (sections 17): Per-endpoint in-flight caps and circuit breakers, delivery pinned to the validated address with SSRF protection, timestamped HMAC signatures, and bounded retry with a DLQ and replay together meet FR-12 and protect internal services. (see FND-041)
  - p.14 §17: "Each endpoint has a cap of 20 in-flight deliveries and its own circuit breaker, so a failing endpoint cannot starve other merchants."
- SA-002 (sections 14.3, 19): The state transition, journal and outbox are written in one transaction, UPDATE and DELETE are revoked on journal and posting, and balances are an asynchronous projection with nightly recomputation that freezes payouts on a mismatch. This serves FR-10, P1, P5 and P7, and avoids hot rows at 2,000 TPS.
  - p.12 §14.3: "Journals are written in the same PostgreSQL transaction as the payment state transition that causes them, together with an outbox row."
- SA-003 (sections 18.5, 22): Back-office access requires SSO with hardware MFA and just-in-time elevation approved by a second person, and audit records are written to S3 under compliance-mode Object Lock. This meets P9, P10, FR-16 and NFR-12. (see FND-046)
  - p.15 §18.5: "write actions (manual refunds, payout holds, merchant suspension) require just-in-time elevation approved by a second staff member"

## Unresolved issues and next steps

- FND-003 (governance decision): Fraud Hook still detokenises PAN with the Card Adapter's role, contradicting P2, Section 12.1 and the CDE scope (FND-003) Next step (Head of Security / PCI compliance lead): Choose option (a), (b) or (c) with the risk team, before the FRV-1 contract (Backlog item 4) fixes the payload.
- FND-008 (governance decision): First cohort still goes live before the Fraud Hook, PCI DSS assessment and acceptance testing (FND-008) Next step (Programme sponsor with Head of Risk): Decide the go-live gate and either re-sequence Section 28 or sign an interim risk acceptance.
- FND-006 (governance decision): A single CloudHSM in one AZ remains a single point of failure for all card payments, and its scaling trigger can never fire (FND-006) Next step (Payments platform owner (decision owner for Section 24)): Re-decide 'one HSM at launch' against the NFR-3 budget and cost, and record the outcome in Section 24.
- FND-002 (needs investigation): Cross-region idempotency lock relies on a conditional put to an eventually consistent, both-writable global table (FND-002) Next step (Platform architect (Payments Core)): Confirm the conditional-write and conflict-resolution semantics of DynamoDB global tables in the chosen consistency mode for ap-southeast-1/3, then choose option (a) or (b) and update Sections 9.4, 20.2 and 24.
- FND-021 (needs testing): FR-5 concurrency clause conflicts with the 409 response, and the replay test still checks only sequential duplicates (FND-021) Next step (QA lead, Payments Core): Add the concurrent, failure-path and cross-region FR-5 cases to the Phase 9 test plan.
- FND-030 (needs investigation): CVC held across cascade attempts relies on an undocumented reading of 'completion of authorization'; PCI DSS version cited may be superseded (FND-030) Next step (PCI compliance lead): Request a QSA interpretation on CVC retention across cascade attempts, and confirm the applicable standard version.
- FND-031 (governance decision): Network tokens 'from launch' depend on a token-requestor application not yet submitted (FND-031) Next step (Card partnerships manager): Submit the VTS/MDES token-requestor applications and report expected certification dates.
- FND-043 (governance decision): No cross-border transfer or localisation basis for five markets' data, now replicated to Jakarta as well (FND-043) Next step (Group DPO with regional legal counsel): Produce the per-market transfer and localisation assessment before Phase 1 is complete.

Research questions left unanswered:
- RQ-007: Under DynamoDB global tables in the default multi-Region eventual consistency mode, is a conditional PutItem with attribute_not_exists evaluated only against the local replica, with conflicting writes in two regions resolved by last-writer-wins? If so, the Section 9.4 claim that exactly one request can acquire the lock regardless of region is false.
- RQ-008: Are the stated DynamoDB figures correct: per-partition limits of 1,000 WCU and 3,000 RCU, 1 WCU per KB written, and warm throughput pre-setting for on-demand tables? Is replicated write capacity in a global table additional to the 12,000 WCU estimate?
- RQ-009: Does PCI DSS v4.0 Requirement 3.3.1/3.3.1.2 allow the CVC to be retained, encrypted, across cascade re-presentations to different acquirers until the final authorization outcome? Is that cascade window 'before completion of authorization' as Requirement 3.3.2 means it?
- RQ-011: Do the personal-data flows meet NFR-7 cross-border transfer obligations? These include customer data from all five markets held in Singapore and replicated to Jakarta, and email, phone, device data and PAN sent to FRV-1 while its DPA is still pending.
- RQ-013: With a single CloudHSM in ap-southeast-1a and uncached DEK unwrap on every detokenise, what happens to card authorizations on loss of that AZ or HSM, and during a regional failover where no HSM or Vault exists in ap-southeast-3? Is this compatible with NFR-3 and NFR-4 (RTO 30 minutes)?
- RQ-014: Is regional failover workable as written? Write forwarding to the Singapore writer cannot work while Singapore is down; MSK and Redis come back empty; lag-window payments must be found when their attempt records may not have replicated; and the global-table idempotency records may be inconsistent. Can NFR-4's regional RPO and recovery-through-reconciliation be met?
- RQ-017: Are the scheme reattempt rules the Retry Engine relies on (Visa reattempt limits, Mastercard MAC codes, treatment of 05/51) correctly reflected in the outcome classes, especially 51 classified as a final hard decline and 05 as retryable across acquirers?

## Changes since the previous version

Prior review: REV-rehearsal_concurrent_1

### Resolved

- FND-046 Payout bank account change controls now protect against account takeover (was FND-046)
- FND-047 DynamoDB idempotency key and capacity sizing now spread the largest merchant's load (was FND-009)

### Partially addressed

- FND-013 The revised NFR-4 promise to recover loss-window payments from provider records has no working mechanism (was FND-004)
- FND-030 CVC held across cascade attempts relies on an undocumented reading of 'completion of authorization'; PCI DSS version cited may be superseded (was FND-029)
- FND-044 Report publication has no defined behaviour for a late or missing settlement file (was FND-020)
- FND-022 Section 18.1 still says 'optional TOTP', contradicting the mandatory MFA introduced in Section 18.3 (was FND-046)

### Still open

- FND-001 Redis idempotency fast path is still not scoped to the merchant and still skips the body-hash check (was FND-001)
- FND-003 Fraud Hook still detokenises PAN with the Card Adapter's role, contradicting P2, Section 12.1 and the CDE scope (was FND-002)
- FND-008 First cohort still goes live before the Fraud Hook, PCI DSS assessment and acceptance testing (was FND-021)
- FND-006 A single CloudHSM in one AZ remains a single point of failure for all card payments, and its scaling trigger can never fire (was FND-006)
- FND-004 A cascade after a timeout can still produce duplicate authorizations; the 'cannot create a duplicate charge' claim is unchanged (was FND-016)
- FND-005 Latency budget still leaves cascades out of the p99, although 3.8% of attempts are retryable (was FND-005)
- FND-020 State machine still lacks transitions that FR-1, FR-15 and Section 16.2 need, and the FR-2 test cannot detect missing ones (was FND-022)
- FND-021 FR-5 concurrency clause conflicts with the 409 response, and the replay test still checks only sequential duplicates (was FND-023)
- FND-031 Network tokens 'from launch' depend on a token-requestor application not yet submitted (was FND-036)
- FND-043 No cross-border transfer or localisation basis for five markets' data, now replicated to Jakarta as well (was FND-051)

### New in update

- FND-002 Cross-region idempotency lock relies on a conditional put to an eventually consistent, both-writable global table
- FND-014 The regional DR plan leaves out the CDE (Vault, CloudHSM, Card Adapter), so card payments cannot meet the 30-minute RTO
- FND-041 Events already relayed to the Singapore MSK but not yet consumed are lost on regional failover

## Evidence limitations

- DOC-design_v2: native PDF block not sent because the configured model backend accepts text only. Impact: figures, diagrams and tables rendered as images were not visible to the model; the review is based on the extracted text (DEG-001)
- No external research was possible: no tool gateway (--no-tools, or every server is disabled). Impact: doc-only review: every question that needs external evidence is reported as a validation need, and confidence is lowered (DEG-002)
- assess shard 1/4 (intent_and_fitness) was cut by the stage 1 limit at 265 s; 10 finished finding(s) kept (cut call llm-0003). Impact: criteria not assessed: design_intent; the review is partial for them (no finding, coverage marked not assessed) (DEG-003)
- assess shard 2/4 (requirements_and_consistency) was cut by the stage 1 limit at 265 s; 12 finished finding(s) kept (cut call llm-0004). Impact: every criterion of the shard has a finding; the shard's lower-ranked findings, if any, are missing (DEG-004)
- assess shard 3/4 (claims_and_assumptions) was cut by the stage 1 limit at 265 s; 9 finished finding(s) kept (cut call llm-0005). Impact: every criterion of the shard has a finding; the shard's lower-ranked findings, if any, are missing (DEG-005)
- FND-002's recommendation appears to reverse approved decision AD-006 (24 Confirmed Decisions - Idempotency store) without a 'challenges' label. Impact: the conflict is not declared and not backed by the two evidence items a challenge needs; check it against the decision before acting on it (DEG-006)

## Evidence register

| ID | Type | Source | Retrieved | Cited |
|---|---|---|---|---|
| EV-001 | doc | doc:DOC-design_v2#p8/s9.2 | - | yes |
| EV-002 | doc | doc:DOC-design_v2#p8/s9.1 | - | yes |
| EV-003 | doc | doc:DOC-design_v2#p4/s3 | - | yes |
| EV-004 | doc | doc:DOC-design_v2#p8/s9.4 | - | yes |
| EV-005 | doc | doc:DOC-design_v2#p8/s9.4 | - | yes |
| EV-006 | doc | doc:DOC-design_v2#p8/s9.4 | - | yes |
| EV-007 | doc | doc:DOC-design_v2#p19/s24 | - | yes |
| EV-008 | doc | doc:DOC-design_v2#p11/s13.1 | - | yes |
| EV-009 | doc | doc:DOC-design_v2#p10/s12.1 | - | yes |
| EV-010 | doc | doc:DOC-design_v2#p10/s12.2 | - | yes |
| EV-011 | doc | doc:DOC-design_v2#p10/s11.2 | - | yes |
| EV-012 | doc | doc:DOC-design_v2#p10/s11.2 | - | yes |
| EV-013 | doc | doc:DOC-design_v2#p10/s11.1 | - | yes |
| EV-014 | doc | doc:DOC-design_v2#p18/s21.1 | - | yes |
| EV-015 | doc | doc:DOC-design_v2#p9/s10.5 | - | yes |
| EV-016 | doc | doc:DOC-design_v2#p3/s2.2 | - | yes |
| EV-017 | doc | doc:DOC-design_v2#p10/s12.3 | - | yes |
| EV-018 | doc | doc:DOC-design_v2#p11/s12.3 | - | yes |
| EV-019 | doc | doc:DOC-design_v2#p11/s12.3 | - | yes |
| EV-020 | doc | doc:DOC-design_v2#p2/s1 | - | yes |
| EV-021 | doc | doc:DOC-design_v2#p3/s2.2 | - | no |
| EV-022 | doc | doc:DOC-design_v2#p17/s20.2 | - | yes |
| EV-023 | doc | doc:DOC-design_v2#p6/s5 | - | no |
| EV-024 | doc | doc:DOC-design_v2#p22/s28 | - | yes |
| EV-025 | doc | doc:DOC-design_v2#p22/s28 | - | yes |
| EV-026 | doc | doc:DOC-design_v2#p22/s28 | - | yes |
| EV-027 | doc | doc:DOC-design_v2#p17/s20.2 | - | no |
| EV-028 | doc | doc:DOC-design_v2#p17/s20.2 | - | yes |
| EV-029 | doc | doc:DOC-design_v2#p17/s20.2 | - | no |
| EV-030 | doc | doc:DOC-design_v2#p2/s2.1 | - | yes |
| EV-031 | doc | doc:DOC-design_v2#p6/s7.1 | - | yes |
| EV-032 | doc | doc:DOC-design_v2#p20/s26.1 | - | yes |
| EV-033 | inference | inference:EV-033 from EV-001, EV-002, EV-003 | - | yes |
| EV-034 | inference | inference:EV-034 from EV-004, EV-005, EV-006, EV-007 | - | yes |
| EV-035 | inference | inference:EV-035 from EV-011, EV-012, EV-013 | - | yes |
| EV-036 | inference | inference:EV-036 from EV-014, EV-015, EV-016 | - | yes |
| EV-037 | inference | inference:EV-037 from EV-017, EV-018, EV-019, EV-020 | - | yes |
| EV-038 | inference | inference:EV-038 from EV-021, EV-022, EV-023 | - | yes |
| EV-039 | inference | inference:EV-039 from EV-027, EV-028 | - | no |
| EV-040 | inference | inference:EV-040 from EV-030, EV-031, EV-032 | - | yes |
| EV-041 | doc | doc:DOC-design_v2#p8/s9.2 | - | yes |
| EV-042 | doc | doc:DOC-design_v2#p19/s24 | - | no |
| EV-043 | doc | doc:DOC-design_v2#p8/s9.4 | - | no |
| EV-044 | doc | doc:DOC-design_v2#p13/s16.2 | - | yes |
| EV-045 | doc | doc:DOC-design_v2#p17/s20.2 | - | yes |
| EV-046 | doc | doc:DOC-design_v2#p17/s20.2 | - | yes |
| EV-047 | doc | doc:DOC-design_v2#p10/s12.1 | - | yes |
| EV-048 | doc | doc:DOC-design_v2#p18/s21.1 | - | no |
| EV-049 | doc | doc:DOC-design_v2#p10/s11.2 | - | no |
| EV-050 | doc | doc:DOC-design_v2#p22/s28 | - | no |
| EV-051 | doc | doc:DOC-design_v2#p3/s2.1 | - | yes |
| EV-052 | doc | doc:DOC-design_v2#p11/s12.3 | - | no |
| EV-053 | doc | doc:DOC-design_v2#p10/s12.1 | - | yes |
| EV-054 | doc | doc:DOC-design_v2#p6/s7.2 | - | yes |
| EV-055 | doc | doc:DOC-design_v2#p20/s26.1 | - | yes |
| EV-056 | doc | doc:DOC-design_v2#p3/s2.1 | - | yes |
| EV-057 | doc | doc:DOC-design_v2#p8/s9.1 | - | yes |
| EV-058 | doc | doc:DOC-design_v2#p14/s18.1 | - | yes |
| EV-059 | doc | doc:DOC-design_v2#p14/s18.3 | - | yes |
| EV-060 | inference | inference:EV-060 from EV-041, EV-001, EV-042 | - | yes |
| EV-061 | inference | inference:EV-061 from EV-005, EV-004, EV-043 | - | no |
| EV-062 | inference | inference:EV-062 from EV-028, EV-044, EV-045 | - | yes |
| EV-063 | inference | inference:EV-063 from EV-022, EV-017, EV-046 | - | yes |
| EV-064 | inference | inference:EV-064 from EV-048, EV-015, EV-013 | - | yes |
| EV-065 | inference | inference:EV-065 from EV-049, EV-012 | - | yes |
| EV-066 | inference | inference:EV-066 from EV-052, EV-020 | - | yes |
| EV-067 | inference | inference:EV-067 from EV-030, EV-054 | - | yes |
| EV-068 | doc | doc:DOC-design_v2#p8/s9.4 | - | no |
| EV-069 | doc | doc:DOC-design_v2#p8/s9.4 | - | no |
| EV-070 | doc | doc:DOC-design_v2#p10/s11.2 | - | no |
| EV-071 | doc | doc:DOC-design_v2#p18/s21.1 | - | no |
| EV-072 | doc | doc:DOC-design_v2#p3/s2.2 | - | no |
| EV-073 | doc | doc:DOC-design_v2#p17/s20.3 | - | yes |
| EV-074 | doc | doc:DOC-design_v2#p17/s20.2 | - | yes |
| EV-075 | doc | doc:DOC-design_v2#p3/s2.2 | - | no |
| EV-076 | doc | doc:DOC-design_v2#p22/s28 | - | no |
| EV-077 | doc | doc:DOC-design_v2#p22/s28 | - | no |
| EV-078 | doc | doc:DOC-design_v2#p10/s11.2 | - | yes |
| EV-079 | doc | doc:DOC-design_v2#p11/s12.4 | - | yes |
| EV-080 | doc | doc:DOC-design_v2#p3/s2.2 | - | yes |
| EV-081 | doc | doc:DOC-design_v2#p19/s24 | - | yes |
| EV-082 | doc | doc:DOC-design_v2#p20/s25 | - | yes |
| EV-083 | inference | inference:EV-083 from EV-005, EV-068, EV-069 | - | yes |
| EV-084 | inference | inference:EV-084 from EV-070, EV-012, EV-013 | - | yes |
| EV-085 | inference | inference:EV-085 from EV-071, EV-015, EV-016 | - | no |
| EV-086 | inference | inference:EV-086 from EV-072, EV-027, EV-028, EV-073 | - | yes |
| EV-087 | inference | inference:EV-087 from EV-017, EV-018, EV-074, EV-075 | - | yes |
| EV-088 | inference | inference:EV-088 from EV-052, EV-020, EV-047 | - | no |
| EV-089 | inference | inference:EV-089 from EV-024, EV-076, EV-077 | - | yes |
| EV-090 | inference | inference:EV-090 from EV-078, EV-079 | - | yes |
| EV-091 | inference | inference:EV-091 from EV-081, EV-082 | - | yes |
| EV-092 | doc | doc:DOC-design_v2#p8/s9.2 | - | no |
| EV-093 | doc | doc:DOC-design_v2#p8/s9.1 | - | no |
| EV-094 | doc | doc:DOC-design_v2#p8/s9.4 | - | no |
| EV-095 | doc | doc:DOC-design_v2#p8/s9.4 | - | no |
| EV-096 | doc | doc:DOC-design_v2#p8/s9.4 | - | yes |
| EV-097 | doc | doc:DOC-design_v2#p11/s13.1 | - | yes |
| EV-098 | doc | doc:DOC-design_v2#p11/s12.3 | - | yes |
| EV-099 | doc | doc:DOC-design_v2#p10/s11.2 | - | no |
| EV-100 | doc | doc:DOC-design_v2#p10/s11.2 | - | no |
| EV-101 | doc | doc:DOC-design_v2#p17/s20.2 | - | no |
| EV-102 | doc | doc:DOC-design_v2#p17/s20.2 | - | no |
| EV-103 | doc | doc:DOC-design_v2#p18/s21.1 | - | no |
| EV-104 | doc | doc:DOC-design_v2#p9/s10.5 | - | no |
| EV-105 | doc | doc:DOC-design_v2#p22/s28 | - | no |
| EV-106 | doc | doc:DOC-design_v2#p10/s11.2 | - | yes |
| EV-107 | doc | doc:DOC-design_v2#p11/s12.4 | - | no |
| EV-108 | doc | doc:DOC-design_v2#p17/s20.2 | - | yes |
| EV-109 | doc | doc:DOC-design_v2#p6/s5 | - | yes |
| EV-110 | doc | doc:DOC-design_v2#p3/s2.1 | - | no |
| EV-111 | doc | doc:DOC-design_v2#p17/s19.1 | - | yes |
| EV-112 | doc | doc:DOC-design_v2#p20/s25 | - | yes |
| EV-113 | doc | doc:DOC-design_v2#p13/s16.2 | - | yes |
| EV-114 | doc | doc:DOC-design_v2#p13/s16.2 | - | yes |
| EV-115 | doc | doc:DOC-design_v2#p14/s18.1 | - | no |
| EV-116 | doc | doc:DOC-design_v2#p14/s18.3 | - | no |
| EV-117 | doc | doc:DOC-design_v2#p14/s18.4 | - | yes |
| EV-118 | doc | doc:DOC-design_v2#p14/s18.4 | - | yes |
| EV-119 | doc | doc:DOC-design_v2#p8/s9.3 | - | yes |
| EV-120 | inference | inference:EV-120 from EV-041, EV-092, EV-093 | - | yes |
| EV-121 | inference | inference:EV-121 from EV-095, EV-096 | - | yes |
| EV-122 | inference | inference:EV-122 from EV-017, EV-098, EV-020 | - | no |
| EV-123 | inference | inference:EV-123 from EV-099, EV-100 | - | no |
| EV-124 | inference | inference:EV-124 from EV-101, EV-102 | - | yes |
| EV-125 | inference | inference:EV-125 from EV-103, EV-104 | - | no |
| EV-126 | inference | inference:EV-126 from EV-108, EV-109 | - | yes |

## Review coverage

| Criterion | Outcome | Findings | Note |
|---|---|---|---|
| design_intent | not assessed | - | not assessed: out of time before assessment (stage 1 limit) |
| fitness_for_objectives | findings | FND-001, FND-002, FND-003, FND-004, FND-005, FND-006, FND-014, FND-008, FND-013, FND-020 | no coverage row returned by the model; derived by code from the findings |
| requirement_completeness | findings | FND-013, FND-014, FND-004, FND-008, FND-020 | no coverage row returned by the model; derived by code from the findings |
| internal_consistency | findings | FND-001, FND-002, FND-013, FND-003, FND-005, FND-004, FND-008, FND-006, FND-021, FND-022 | no coverage row returned by the model; derived by code from the findings |
| claims_and_external_constraints | findings | FND-002, FND-004, FND-005, FND-013, FND-006, FND-030 | no coverage row returned by the model; derived by code from the findings |
| security_and_privacy | findings | FND-001, FND-003, FND-008, FND-030, FND-043, FND-022, FND-046 | Checked idempotency tenancy, the CDE boundary and detokenise access, SAD handling after the 1.1 revision, admin-plane authentication and payout controls, data residency, and audit. The payout-account issue is resolved and the CVC issue partially addressed. Fast-path tenancy and Fraud Hook PAN access are still open. |
| scalability_and_failure_modes | findings | FND-002, FND-006, FND-004, FND-013, FND-005, FND-041, FND-021, FND-044, FND-047, FND-001 | Checked the new cross-region idempotency and DR design, HSM topology, cascade timeouts, the latency budget, MSK failover, DynamoDB capacity and reconciliation timing. The 1.1 changes introduced a cross-region lock flaw and gaps in loss-window recovery. |
| assumptions_and_dependencies | findings | FND-013, FND-014, FND-006, FND-008, FND-031 | no coverage row returned by the model; derived by code from the findings |
| verifiability | findings | FND-001, FND-002, FND-013, FND-014, FND-005, FND-020, FND-021 | no coverage row returned by the model; derived by code from the findings |
| decision_preservation | findings | FND-001, FND-002, FND-003, FND-006 | no coverage row returned by the model; derived by code from the findings |
| operability_and_governance | findings | FND-013, FND-008, FND-043, FND-044 | Checked go-live sequencing against controls, the DR runbook, reconciliation operations and data-residency ownership. Go-live risk acceptance and residency sign-off have no named owners. |

## Run details

| | |
|---|---|
| Run | reassess_payments_v2_1 (started 2026-10-03T08:07:42Z) |
| Outcome | completed_degraded |
| Model | requested claude-opus-5-5; served claude-opus-5-5; effort per-stage (extra.model.effort_by_stage) |
| Persona | generalist_architect |
| Tool transport | live |
| Research stop | tool_failure (error): no_tools; 0 iteration(s); 0 cited of 0 retrieved |
| Tool calls | none |
| Tokens | input 375052, cached 0, output 75068; cost ~$4.50 (price table 2026-09-25); a lower bound: 3 model calls with unrecorded usage (assess, deadline cut; assess, deadline cut; assess, deadline cut) |
| Extractor | pdfplumber 0.11.10 |
| Config sha256 | 79a78b6aea40f86fd3030500a033c55c70121845d35d70a2863fb427aaf80835 |
| Prompt bundle sha256 | 6f0ee28ab9acf35152a2d4456207a8a068222149422e66d801c8195455c28ba7 |
| Git commit | 886c3fc99eb4ec875e135440919e7bdc918ee094 |
| Fault schedule | none |
| Model fallbacks | 0 |
| Canonical text DOC-design_v2 | sha256 e318322d463ba3cfd4c7ac4dbbb5d9942931367dad1818339ad783a5e1b2c1a3 |
| Canonical text DOC-design_v1 | sha256 356ac6d0f10bfbdb99d462b189b9bb63601f1b851ec429055e98c36eedc1df64 |
