# Design review: Serindit Pay — Merchant Payment Orchestration Platform

| | |
|---|---|
| Review | REV-demo_profile_measure_1 (full review) |
| Under review | DOC-design_v1: Serindit Pay — Merchant Payment Orchestration Platform v1.0, 21 pages |
| Verdict | **not assessed (out of time before assessment)** (confidence 0.00, low) |
| Tools used | none |
| Tools disabled | mcp-internet-search, mcp-research-information, mcp-browser-automation-pw, mcp-document-intelligence |
| Reporting threshold | severity low and above (0 finding(s) in the appendix) |

> No external research was possible or used in this run: every finding rests on the document alone.


## Design intent

MPOP is Serindit Pay's Merchant Payment Orchestration Platform. It accepts merchant payment requests, routes each one to an acquirer, e-wallet provider or bank-transfer rail, and accounts for every resulting money movement until the money is settled and paid out to the merchant. It replaces five per-market integration stacks with one merchant API across five Southeast Asian markets. It covers rule-based routing with cascading, idempotency, a PCI-scoped tokenising vault, a synchronous fraud hook, a double-entry ledger, daily three-way reconciliation, payouts, signed webhooks and a merchant admin plane, sized for about 15,000 merchants and a peak of 2,000 payment-creation TPS by 2027. Disputes, KYB, 3DS server internals, lending/BNPL and checkout UIs are out of scope.

Objectives:
- Replace five per-market integration stacks that share no routing or ledger and reconcile by spreadsheet with one governed platform.
- Provide one versioned merchant API across five markets (SG, MY, ID, TH, PH) for cards, e-wallets and bank transfers.
- Support about 15,000 active merchants, 10.5M attempts per day and a peak of 2,000 create-payment TPS (2027 target).
- P1: One payment, one truth: the payment record and the ledger are the source of truth; provider responses are only inputs.
- P2: Card data stays in the Vault: PAN and SAD never leave the Vault boundary except over the Card Adapter's acquirer connection; all other services handle tokens only.
- P3: Idempotency is scoped to (merchant, key) for every mutating call.
- P4: Money is integers: amounts are integer minor units with an ISO 4217 code; no floating point.
- P5: The ledger is append-only; corrections are new reversing or adjusting journals.
- P6: Adapters absorb provider differences; the core never branches on provider identity.
- P7: At-least-once delivery with exactly-once effect through consumer deduplication on stable identifiers.
- P8: Fail closed on security; degrade gracefully to documented defaults on optional enrichment (fraud signals, BIN metadata).
- P9: Least privilege and separation of duties; money-moving permissions are separated from configuration permissions.
- P10: Everything is auditable: every mutation, routing decision and admin action can be reconstructed.

Constraints:
- NFR-5: Must be assessed as a PCI DSS v4.0 Level 1 service provider, with the CDE limited to the components in Section 12.2.
- NFR-6: Sensitive authentication data must be handled per PCI DSS v4.0 Requirements 3.2.1 and 3.3.2.
- NFR-7: Personal data must be processed under SG PDPA 2012, MY PDPA 2010, ID Law 27/2022, TH PDPA 2019 and PH DPA 2012.
- FR-7: Card reattempts must never occur where card scheme rules prohibit them.
- Principles P1-P10 override any later section that appears to conflict with them.
- All primary data stores are in AWS ap-southeast-1. The ap-southeast-3 Aurora secondary is for disaster recovery only.
- Out of scope: dispute case management (disputes are ledger events only), merchant onboarding/KYB (Merchant Risk platform), 3DS server internals (third party), lending/BNPL/instalments, and checkout UIs/SDKs.
- ACQ-PH1 retires API v2 in Q3 2027.
- Retention: payment and attempt records 7 years; idempotency records 24 hours; webhook events 30 days; raw settlement files 7 years; audit records 5 years.
- Rollout: the first cohort (Singapore, cards and PayNow) goes live after Phase 7; other markets follow at four-week intervals.

Key assumptions:
- The largest merchant (M-0001) accounts for about 45% of peak traffic (about 900 TPS). Each request uses two DynamoDB writes, staying within a stated 10,000 WCU per-partition ceiling.
- Fewer than 1% of card payments cascade, so cascading does not affect the p99 latency budget. Retryable outcomes were 3.8% in the 2025 baseline.
- The acquirer round trip p99 is 1,100 ms (2025 production, slowest acquirer), and HSM detokenise takes 20 ms per a vendor benchmark.
- An Aurora spike on db.r7g.8xlarge sustained 2,600 TPS of the full write mix. Production uses db.r7g.12xlarge for headroom.
- A single CloudHSM in one AZ is sufficient at launch. A second HSM will be added when sustained card volume exceeds 1,500 TPS.
- The document states that PCI DSS v4.0 Requirements 3.2.1 and 3.3.2 permit encrypted SAD/CVC retention until settlement.
- FRV-1 requires the full card number for its consortium velocity graph, and the Fraud Hook obtains it via detokenise.
- Network tokens (VTS/MDES) are available from launch as the primary card-on-file credential.
- The reconciliation matcher takes 45 minutes and report generation 15 minutes at 2025 volume; the matcher starts only after all files are received.
- Cascading recovered about 31% of retryable outcomes in a three-month ACQ-SG1 → ACQ-SG2 pilot.
- The first merchant cohort does not need the Admin API schemas or the dispute module (it uses the portal; Finance Operations handles disputes manually).

Located at: p.1 §1, p.2 §1, p.2 §1.

## Fitness for purpose

**Not assessed (out of time before assessment)** (confidence 0.00). Not assessed: the run ran out of time before assessment, so the design was not reviewed and no finding was produced. This is not a judgement of the design; it must not be read as a review result.

What would change this verdict: Rerun the review with a longer deadline.

## Strengths

None found.

## Risks

None found.

## Gaps

None found.

## Ambiguities

None found.

## Unresolved assumptions

None found.

## Validation needs

None found.

## Recommended refinements

No refinement is recommended.

## Areas where no change is needed

None recorded.

## Unresolved issues and next steps

None.

Research questions left unanswered:
- RQ-005: Can NFR-4's zero RPO 'including loss of an entire region' hold with asynchronous Aurora Global Database replication (AD-004)? And on regional failover, how are idempotency records rebuilt 'from the payment table' (which has no idempotency_key column), the CDE/Vault/CloudHSM restored, and MSK outbox state and in-flight acquirer attempts recovered?
- RQ-007: What is DynamoDB's documented per-partition write throughput (WCU per second), how many WCU does a write of up to 4 KB consume, and does a table with an LSI limit item-collection size or prevent splitting a hot partition key? Is the 900 TPS single-merchant design in 9.3 within those limits?
- RQ-008: Do PCI DSS v4.0 Requirements 3.2.1 and 3.3.1/3.3.2 permit a service provider to keep CVC after authorization, up to settlement or 72 hours, for cascade re-presentation and incremental authorizations? Or is SAD storage after authorization prohibited even when encrypted?
- RQ-009: Under Visa and Mastercard reattempt rules, how many times may a declined or failed transaction be reattempted over what window, and are cascading soft declines such as 05 to a different acquirer and the MAC/Category handling in 11.1 and 11.3 compliant? Are fees for excessive reattempts relevant?
- RQ-013: Does running primary processing of Indonesian, Thai, Malaysian and Philippine payment data in Singapore (and DR in Jakarta) meet the market regulations on cross-border transfer and payment-system data localisation, such as Bank Indonesia rules for payment service providers, and is this covered by NFR-7 or the privacy review?
- RQ-014: With one CloudHSM in a single AZ, uncached DEK unwraps on every detokenise, and detokenise calls from the Card Adapter, cascades and the Fraud Hook, can the HSM sustain about 1,100+ card TPS? And does an HSM or AZ failure (mapped to 'retryable', which every cascade candidate also hits) stop all card payments, given NFR-3?
- RQ-017: Two decisions depend on items that are still open. AD-010 makes network tokens primary 'from launch' and Phase 3 is marked 'ready', yet the TRID application has not been submitted (Backlog 2). Phase 8 Fraud Hook is blocked on the FRV-1 contract, yet go-live is after Phase 7, which would leave the first cohort without the FR-9 fraud scoring. What lead times and fallbacks are needed?

## Evidence limitations

- DOC-design_v1: native PDF block not sent because the configured model backend accepts text only. Impact: figures, diagrams and tables rendered as images were not visible to the model; the review is based on the extracted text (DEG-001)
- No external research was possible: no tool gateway (--no-tools, or every server is disabled). Impact: doc-only review: every question that needs external evidence is reported as a validation need, and confidence is lowered (DEG-002)
- out of time before assessment: the assess call was cut by the run deadline (the assess model call was cut after 179 s by the run deadline (540 s; not retried past it)). Impact: the design was not assessed: the report has no findings and its verdict is not a judgement of the design; rerun with a longer deadline (DEG-003)
- stop rule deadline (deadline) before refine. Impact: skipped to verify; evidence may be partial (DEG-004)

## Evidence register

The evidence register is empty.

## Review coverage

| Criterion | Outcome | Findings | Note |
|---|---|---|---|
| design_intent | not applicable | - | not assessed: out of time before assessment (run deadline) |
| fitness_for_objectives | not applicable | - | not assessed: out of time before assessment (run deadline) |
| requirement_completeness | not applicable | - | not assessed: out of time before assessment (run deadline) |
| internal_consistency | not applicable | - | not assessed: out of time before assessment (run deadline) |
| claims_and_external_constraints | not applicable | - | not assessed: out of time before assessment (run deadline) |
| security_and_privacy | not applicable | - | not assessed: out of time before assessment (run deadline) |
| scalability_and_failure_modes | not applicable | - | not assessed: out of time before assessment (run deadline) |
| assumptions_and_dependencies | not applicable | - | not assessed: out of time before assessment (run deadline) |
| verifiability | not applicable | - | not assessed: out of time before assessment (run deadline) |
| decision_preservation | not applicable | - | not assessed: out of time before assessment (run deadline) |
| operability_and_governance | not applicable | - | not assessed: out of time before assessment (run deadline) |

## Run details

| | |
|---|---|
| Run | demo_profile_measure_1 (started 2026-10-02T20:03:05Z) |
| Outcome | completed_degraded |
| Model | requested claude-opus-5-5; served claude-opus-5-5; effort per-stage (extra.model.effort_by_stage) |
| Persona | generalist_architect |
| Tool transport | live |
| Research stop | tool_failure (error): no_tools; 0 iteration(s); 0 cited of 0 retrieved |
| Tool calls | none |
| Tokens | input 67374, cached 0, output 28098; cost ~$1.10 (price table 2026-09-25) |
| Extractor | pdfplumber 0.11.10 |
| Config sha256 | a7db587d677529d25d7afdfc52b3e91d6d3533f596381a206d84ef15b3d77e5e |
| Prompt bundle sha256 | af1b7952e21ffc77d3c3336a224909e1a84f86d54826bbe617814ce9e0e56b3a |
| Git commit | 2d84f5926458ec5610b1af9081895e637ff8fb16 |
| Fault schedule | none |
| Model fallbacks | 0 |
| Canonical text DOC-design_v1 | sha256 ad0bb891f073f14325b6ba716d58070d6b074ebaef9a9c64432138b89b64ec3c |
