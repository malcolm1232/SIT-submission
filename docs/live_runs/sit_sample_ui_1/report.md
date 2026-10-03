# Design review: SIT Institutional Memory Platform — Detailed Design

| | |
|---|---|
| Review | REV-ui-261003-082941-36e8 (full review) |
| Under review | DOC-sit_sample_v1: SIT Institutional Memory Platform — Detailed Design v2.0, 30 pages |
| Verdict | **fit with conditions** (confidence 0.65, medium) |
| Tools used | mcp-internet-search, mcp-research-information |
| Tools disabled | mcp-browser-automation-pw, mcp-document-intelligence |
| Reporting threshold | severity low and above (0 finding(s) in the appendix) |


## Design intent

The document describes the SIT Institutional Memory Platform. It is an institution-level, governed memory infrastructure, not a per-agent store. It serves six AI agents (Tutor, Buddy, Academic Advisory, Counselling, Career, Orientation) for about 15,000 SIT learners. Its main features are per-learner structured namespaces, pre-retrieval policy-enforced access control, a strict counselling isolation wall, PDPA-oriented audit of every operation, an async write path and cached read path, and an out-of-band Memory Management Plane for configuration and governance. The document is written to be detailed enough for an engineering team or AI coding assistant to start building, and Section 28 assesses where that is not yet true. The separate SIT-AI-Factory-RAG system is explicitly out of scope.

Objectives:
- P1: The learner namespace is authoritative and the agent's copy is backup only. Conflicts resolve in favour of the learner namespace.
- P2: Memory is private by default, shared by exception, and anonymised for service learning.
- P3: Access control is pre-retrieval: the namespace restriction gates the query itself, not the results after retrieval.
- P4: Counselling hard wall: wellbeing/counselling/ is HIGHLY_RESTRICTED, with zero cross-domain reads, no MMP override and no exceptions.
- P5: Agents share across each other only through the learner namespace and never access each other's memory directly.
- P6: No uncontrolled self-writing: all writes are classified and policy-checked before storage.
- P7: Every operation is audited (access, write, denial, compaction, deletion, escalation), as required for PDPA.
- P8: Write async via Kafka (non-blocking) and read cached via Redis L1 then PostgreSQL.
- P9: Administrators, not agents, configure slot templates, sensitivity levels and retention rules.
- P10: Minimum useful context: summary over transcript, fact over full conversation, and a token-budgeted context pack.
- Provide an institution-level memory platform covering all six layers (capture, classification, storage, retrieval, governance, administration), not only layers 2-4 as in Mem0, Zep or Letta.
- Be specified well enough for an engineering team or AI coding assistant to begin implementation (Section 28 self-assessment).

Constraints:
- PDPA compliance: audit trails are required for every operation on personal data.
- NFR-10: Vector-store infrastructure cost must stay within SGD 800-1,200/month at 15,000-learner scale (Azure Singapore region, Memory Optimised 16-vCore tier).
- SIT-AI-Factory-RAG (Azure AI Search) is a separate system, in a separate resource group, with no shared infrastructure.
- The ten foundational principles override any later section that appears to conflict with them.
- NFR-5: HIGHLY_RESTRICTED data must sit in a physically separate schema (memory_sensitive) with separate database credentials.
- Platform stack: Azure Database for PostgreSQL + pgvector, Entra ID / OAuth 2.0, Kafka (Azure Event Hubs), Redis, and Azure OpenAI text-embedding-3-small.

Key assumptions:
- About 600 vectors per learner across a full degree, giving about 9.5M vectors at 15,000 learners (including alumni and institution-level vectors).
- Queries are always filtered by learner_id + slot_path, so the effective search space per query is 500-800 vectors, which supports 5-15 ms latency.
- HNSW index overhead is about 1.4×, and the growth ceiling before degradation is about 30-40M vectors.
- The MMP is not in the critical request path, so MMP downtime does not affect agent reads and writes.
- The deferred items (cohort namespace, compaction, non-SIT identity) are not needed for the launch scope of the initial six agents.
- No open-source Memory Management Plane for agent memory exists (prior-art claim).
- Azure Event Hubs is assumed to be the managed Kafka-API alternative (pending confirmation).

Located at: p.3 §1 (3 passages).

## Fitness for purpose

**Fit with conditions** (confidence 0.65). The core architecture fits the platform's purpose. It uses ordered pre-retrieval Gateway checks, separate schemas and credentials per sensitivity tier, a namespace as the only bridge between agents, and requirements that trace to acceptance criteria. The document is also candid about its own readiness and open items (FND-044, FND-012, FND-030). No critical finding was raised, and build has not started, so the open issues can still be fixed in the design text or by accountable decisions before code is written. However, 19 high-severity findings remain open, and they cluster in the areas the platform exists to protect: (a) The agent per-learner backup is a second memory store outside governance. It escapes the Gateway, the policy engine, the sensitive tier, audit and learner deletion (FND-031, FND-001, FND-002, FND-016). (b) The Super Admin role and the unauthenticated Admin API contradict the counselling hard wall, and there is no defined path for counselling escalations (FND-014, FND-004, FND-037, FND-036). (c) Learner data is still served from backup after a token is revoked (FND-032, FND-023). (d) The MMP sits in the live request path even though NFR-4 says it does not (FND-013, FND-034). (e) The async write path has no route for rejections, no dead-letter handling and no idempotency (FND-035, FND-003, FND-015, FND-024). (f) The session cache undermines fresh policy evaluation and tier isolation (FND-033). (g) The vector sizing arithmetic does not support the confirmed SKU or the in-RAM latency claim (FND-022, FND-021). An unconditional fit is ruled out by these findings. Not fit is not warranted, because none of them invalidates the overall architecture. Limits of this review:

- Only the extracted text was reviewed; figures and image tables were not seen (DEG-001).
- One assessment shard was cut short, so lower-ranked findings for requirements and consistency may be missing (DEG-002).
- The global refine pass did not run (DEG-003). Duplicate findings were not merged, approved decisions were not linked, and no external evidence was attached. External premises (Entra ID token lifetime, pgvector filtered-HNSW behaviour, Azure pricing, BM25 availability, PDPA obligations) therefore rest on reasoning alone and are unverified. This is why confidence is moderate.

Conditions:
- Bring the agent per-learner backup under governance, or remove it. Define where it is stored and which tier it uses, with counselling backups in memory_sensitive. Route its writes through classification, policy checks and audit. Extend FR-15 deletion and the FR-15 test to backups. Get a DPO decision on whether the backup may survive learner self-deletion. Owner: data governance officer / DPO with the platform architect. (FND-031, FND-001, FND-002, FND-016, FND-027)
- Settle how the counselling hard wall applies to Super Admin and MMP emergency access, and record it in Sections 19 and 21. Specify authentication and authorisation for the Admin API, with sensitive-schema scoping. Define a safety escalation path for counselling that does not downgrade HIGHLY_RESTRICTED content into the standard tier. Extend the FR-5 test to cover admin and MMP paths. (FND-014, FND-004, FND-037, FND-036)
- Reconcile FR-4 with degraded mode. A REVOKED token must serve no learner-personal data. Handle the REFRESHING state. Check that Entra ID can support the 48-hour token window and define how revocation is detected. Extend the NFR-6 test to assert that no data is served on revocation. (FND-032, FND-009, FND-019, FND-023)
- Either move the PolicyEngine, AuditStore and inline slot provisioning out of the MMP service, or restate NFR-4. In either case, state whether the system fails open or fails closed when audit is unavailable. (FND-013, FND-034, FND-005)
- Redesign the async write path. Classify and validate before choosing the topic and before sending the ACK, or provide a defined route that returns rejections to the agent. Add dead-lettering, separation of transient from permanent failures, idempotency keys and per-learner ordering. Close the Event Hubs confirmation in the backlog. (FND-035, FND-003, FND-015, FND-024, FND-010)
- Define the context-pack cache key per agent and learner. Invalidate cached packs on policy, permission or deletion changes. State whether HIGHLY_RESTRICTED content may be cached at all, and if so how Redis is isolated and encrypted. (FND-033, FND-007, FND-020)
- Reconcile the vector sizing: the per-learner count, RAM fit against 128 GB, and the growth ceiling. Prototype filtered HNSW queries at 9.5M vectors to show NFR-2 latency and recall. Give a cost basis and scope for NFR-10, including the components that are currently unbudgeted. (FND-022, FND-021, FND-008, FND-038, FND-025, FND-043)
- Before generating code for the dependent components, complete the specification. This needs a Policy Engine decision table (and an FR-8 test derived from it), DDL columns for retention, pii, expires_at, embedded and key, and full-text support for the BM25 fallback. (FND-006, FND-026, FND-017, FND-039, FND-029, FND-018)
- Close the operational and governance gaps: HA/DR targets and monitoring, owners and dates for backlog items, an anonymisation method and minimum group size for aggregates, the SIS event contract, credential custody and rotation, and the WORKING typing of onboarding_progress. (FND-040, FND-041, FND-028, FND-042, FND-011)

| Objective | Verdict | Findings |
|---|---|---|
| P1 | fit with conditions | FND-031, FND-001, FND-002, FND-016 |
| P2 | fit with conditions | FND-002, FND-032, FND-009, FND-041, FND-027 |
| P3 | fit with conditions | FND-044, FND-001, FND-007, FND-033, FND-020 |
| P4 | fit with conditions | FND-044, FND-014, FND-004, FND-037, FND-036, FND-042 |
| P5 | fit | FND-044, FND-012 |
| P6 | fit with conditions | FND-001, FND-031, FND-003, FND-035, FND-015 |
| P7 | fit with conditions | FND-034, FND-031, FND-013, FND-027, FND-040 |
| P8 | fit with conditions | FND-035, FND-024, FND-010, FND-003, FND-033, FND-013 |
| P9 | fit | FND-012, FND-030 |
| P10 | fit | FND-012 |
| Six-layer institution-level memory platform (no ID) | fit with conditions | FND-022, FND-021, FND-008, FND-038, FND-040, FND-025, FND-043, FND-028 |
| Specified well enough to begin implementation, Section 28 (no ID) | fit with conditions | FND-006, FND-026, FND-017, FND-039, FND-029, FND-018, FND-030 |

What would change this verdict: The verdict would move towards not_fit if the DPO or a legal review found that retaining the agent backup after self-deletion, or keeping audit logs indefinitely, breaches PDPA in a way the design cannot fix without restructuring. It would also move towards not_fit if a pgvector prototype showed that filtered HNSW cannot reach NFR-2 latency and recall at 9.5M vectors on the confirmed SKU, or if Entra ID cannot support the token model. It would move towards fit if a revised design governs or removes the agent backup, closes the counselling override and escalation paths, fixes REVOKED handling, takes the MMP out of the request path, and defines error handling for the write path, with the sizing benchmark and the Event Hubs and SIS confirmations completed. A full review with figures visible, the missing shard completed and external evidence attached would also raise or lower confidence.

## Strengths

### FND-012 Clear, traceable statement of intent with explicit precedence and readiness

- **strength** · confidence 0.85 (high) · rank 42
- Disposition: **no change**

The design states numbered FR/NFR requirements, ten principles with an explicit rule that principles win on conflict, a confirmed-decision register, a pending backlog, and a per-requirement acceptance table. Section 28 honestly rates its own readiness. Together these make the intent reviewable and let conflicts such as FND-001 and FND-004 be resolved against a stated precedence.

- Where: p.6 §3: "Where a later section appears to conflict with one of these, the principle wins."
- Where: p.3 §2: "Each requirement carries an ID used again in Section 27"
- Evidence EV-055 (doc, supports): "Where a later section appears to conflict with one of these, the principle wins." [doc:DOC-sit_sample_v1#p6/s3]
- Evidence EV-056 (doc, supports): "Each requirement carries an ID used again in Section 27" [doc:DOC-sit_sample_v1#p3/s2]
- Why no change is needed: The objectives, principles, decisions and acceptance criteria are explicit and traceable, which is what a build-ready design needs to be reviewed and tested against.

### FND-030 Gaps are explicitly tracked in the Pending Backlog and readiness assessment

- **strength** · confidence 0.80 (high) · rank 43
- Disposition: **no change** · already acknowledged in the document

Sections 26 and 28 set out which items are confirmed and which are still open, and tie each open item to a build phase. Assumptions about the Dispatcher, the Auditor, compaction and the Policy Engine algorithm are therefore visible, not hidden. This supports the stated aim of a specification that can be built from, and lets the remaining assumption findings be closed against named backlog items.

- Where: p.29 §28: "The honest answer is partial - strong in some areas, not"
- Where: p.26 §26: "Items confirmed as in-scope but not yet fully designed:"
- Evidence EV-091 (doc, supports): "Items confirmed as in-scope but not yet fully designed:" [doc:DOC-sit_sample_v1#p26/s26]
- Why no change is needed: Tracking open items explicitly, each linked to a build phase, is the right control for the design's aim of being build-ready; keep it and extend it with the items raised above.

### FND-044 Ordered pre-retrieval Gateway checks with schema and credential isolation and matching tests

- **strength** · confidence 0.80 (high) · rank 44
- Disposition: **no change**

The six ordered, logged Gateway checks, the hard block for HIGHLY_RESTRICTED slots, and the separate-credential sensitive schema directly implement P3/P4 and FR-4/FR-5. They are paired with concrete negative tests (a per-check DENY, and a cross-credential failure). This is defence in depth that fits the platform's privacy objective.

- Where: p.15 §15 (FR-4, FR-5): "HIGHLY_RESTRICTED slots: hard block for all agents not in an"
- Where: p.27 §27.2 (NFR-5): "A credential valid for memory_standard is confirmed to fail authentication"
- Evidence EV-115 (doc, supports): "HIGHLY_RESTRICTED slots: hard block for all agents not in an" [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-116 (doc, supports): "A credential valid for memory_standard is confirmed to fail authentication" [doc:DOC-sit_sample_v1#p27/s27.2]
- Why no change is needed: These controls meet FR-4, FR-5 and NFR-5 as stated, and they are verifiable through the Section 27 tests.

## Risks

### FND-031 Agent per-learner backup memory sits outside the governed path (deletion, audit, sensitivity tiering)

- **risk** · security privacy gap · severity **high** · confidence 0.80 (high) · rank 1
- Disposition: **governance decision** (also: refinement now)

Every agent keeps a full per-learner store that is written 'always, immediate' outside the Kafka/Gateway path, and the design states that this backup survives learner self-deletion. This copy is not covered by the Gateway checks, the seven-dimension policy evaluation, the memory_sensitive tier or the Auditor. In practice this means the counselling agent's backup holds HIGHLY_RESTRICTED data with none of the controls in NFR-5. It also means a learner's FR-15 deletion request leaves a full copy behind. This undermines P6/P7, FR-15 and the PDPA objective the platform is built for.

- Where: p.13 §13 (FR-16): "the agent backup survives learner deletion of their own memory (enabling session resume)"
- Where: p.4 §2.1 (FR-15): "Learners shall be able to request deletion of their own user-deletable memory."
- Where: p.6 §3 (P7): "Audit every operation - access, write, denial, compaction, deletion, escalation are all logged."
- Evidence EV-034 (doc, supports): "the agent backup survives learner deletion of their own memory (enabling session resume)" [doc:DOC-sit_sample_v1#p13/s13]
- Evidence EV-035 (doc, supports): "Learners shall be able to request deletion of their own user-deletable memory." [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-100 (doc, supports): "Audit every operation - access, write, denial, compaction, deletion, escalation are all logged." [doc:DOC-sit_sample_v1#p6/s3]
- Evidence EV-117 (inference, supports): "A per-agent copy written directly and kept after learner deletion is outside the Gateway, Auditor and sensitive-schema controls, so deletion and audit guarantees cannot hold for it." [inference:EV-117] derived from EV-034, EV-035, EV-100
- Recommendation: In Sections 13, 14 and 20, specify that: the backup is written through the Router (or a governed local store) with the same sensitivity tiering and audit; FR-15 deletion propagates to all agent backups; HIGHLY_RESTRICTED content is never kept in the backup, or is kept only in an encrypted sensitive-tier store; and the backup has a bounded TTL. Add an FR-15 acceptance case that checks the backups after deletion.
  - Issue: Agent backup memory is an ungoverned second copy of learner data, including counselling content, and it survives deletion.
  - Rationale: FR-15, NFR-5 and P7 only hold if every copy of learner data goes through the same controls.
  - Expected benefit: Learner deletion and audit become complete, and the counselling hard wall extends to backup copies. (objectives: FR-15, FR-16, NFR-5, NFR-7, P7)
  - Supporting evidence: EV-034, EV-035, EV-100, EV-117
  - Verification: Extend the FR-15 deletion boundary test to assert that the agent backups hold no user-deletable records after deletion. Extend FR-13 to assert that backup reads and writes are audited.
- Next step: Data Protection Officer with Platform Architect: Decide whether agent backups may survive learner deletion and whether they may hold HIGHLY_RESTRICTED data, then amend Sections 13 and 20.

### FND-001 Agent per-learner backup is an ungoverned second memory store

- **risk** · internal contradiction · severity **high** · confidence 0.75 (medium) · rank 2
- Disposition: **refinement now** (also: governance decision)

Section 5 says every operation goes through one governed path, and P6 requires every write to be classified and policy-checked. However, Sections 13 and 14 have every agent keep a full per-learner store that is written 'always, immediate' outside the Kafka/Validator path. The counsellor agent's backup would therefore hold HIGHLY_RESTRICTED content outside memory_sensitive, with no stated Gateway, Policy Engine, audit or retention control. This undermines FR-5, NFR-5, P3, P6 and P7 for whatever the backup holds.

- Where: p.7 §5 (P6): "Every memory operation, from every agent, for every learner, flows through the same governed path."
- Where: p.4 §2.1 (FR-16): "Each agent shall maintain its own per-learner backup memory, used only when the learner namespace is"
- Where: p.6 §3 (P6): "No uncontrolled self-writing - all writes are classified and policy-checked before storage."
- Evidence EV-031 (doc, supports): "Every memory operation, from every agent, for every learner, flows through the same governed path." [doc:DOC-sit_sample_v1#p7/s5]
- Evidence EV-032 (doc, supports): "Each agent shall maintain its own per-learner backup memory, used only when the learner namespace is" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-033 (doc, supports): "No uncontrolled self-writing - all writes are classified and policy-checked before storage." [doc:DOC-sit_sample_v1#p6/s3]
- Evidence EV-057 (inference, supports): "Because writeback to agent own memory is 'always, immediate' and skips Kafka and the Validator, the backup store sits outside the governed path, so counselling content held by the counsellor agent's backup is not protected by the memory_sensitive schema or its credentials." [inference:EV-057] derived from EV-031, EV-032, EV-033
- Recommendation: In Sections 13, 14 and 2.1 (FR-16), state where agent backups are stored (a schema per tier, with the sensitive tier for the counsellor agent). Route backup writes through the Gateway and Auditor with the same sensitivity ceiling, or limit backups to INTERNAL keys. Add FR-16 acceptance cases for audit and tier placement.
  - Issue: The backup store sits outside the governance, sensitivity-tier and audit controls that the design treats as non-negotiable.
  - Rationale: P6 and P7 apply to every write and every operation, and Section 3 says the principles win over later sections.
  - Expected benefit: FR-5, NFR-5 and P7 also hold for degraded-mode data, so the counselling hard wall cannot be bypassed through an agent's own backup. (objectives: FR-5, NFR-5, FR-16, P6, P7)
  - Supporting evidence: EV-031, EV-032, EV-033, EV-057
  - Verification: Extend the FR-16 test: a counsellor-agent backup write lands in memory_sensitive and produces an audit entry, and a standard-credential read of it fails.

### FND-002 Agent backup surviving self-deletion defeats FR-15 learner deletion

- **risk** · internal contradiction · severity **high** · confidence 0.75 (medium) · rank 3
- Disposition: **governance decision** (also: refinement now)

FR-15 lets learners delete their own user-deletable memory, and P2 says memory is private by default. Section 13, however, makes the agent backup deliberately survive learner self-deletion so that sessions can resume. Deleted content therefore stays readable by agents, and the FR-15 deletion boundary test only checks the namespace. As written, the deletion right is met in form but not in effect.

- Where: p.13 §13: "the agent backup survives learner deletion of their own memory (enabling session resume)"
- Where: p.4 §2.1 (FR-15): "Learners shall be able to request deletion of their own user-deletable memory."
- Evidence EV-034 (doc, supports): "the agent backup survives learner deletion of their own memory (enabling session resume)" [doc:DOC-sit_sample_v1#p13/s13]
- Evidence EV-035 (doc, supports): "Learners shall be able to request deletion of their own user-deletable memory." [doc:DOC-sit_sample_v1#p4/s2.1]
- Recommendation: Decide whether a learner deletion request cascades to agent backups, with the Deletion dimension in Section 16 fanning out to them. If backups are kept, list exactly which non-content state survives (for example a session cursor) and why. Update Sections 13 and 20 and the FR-15 acceptance criterion to cover backups.
  - Issue: Learner-deleted memory survives in every agent's backup.
  - Rationale: A deletion that leaves copies readable by agents does not achieve the FR-15 intent or P2.
  - Expected benefit: FR-15 and the Deletion policy dimension (FR-8) become effective across all copies. (objectives: FR-15, P2, FR-8)
  - Supporting evidence: EV-034, EV-035
  - Verification: FR-15 test: after deletion, a read from the agent's backup for the same keys returns nothing, and the cascade is audit-logged.
- Next step: Data governance officer / DPO: Decide the cascade scope of learner deletion to agent backups and record it in Section 20.

### FND-013 MMP placed in the live request path despite NFR-4

- **risk** · internal contradiction · severity **high** · confidence 0.75 (medium) · rank 4
- Disposition: **refinement now** (also: needs testing)

NFR-4 and Section 21 say the MMP is not in the critical request path. However, the MMP's component list includes the PolicyEngine, Section 16 says policy decisions are evaluated fresh on every request, and Gateway Check 4 calls the MMP to provision missing slots during a live request. Read together, an MMP outage would block reads and writes. That breaks NFR-4 and would fail the NFR-4 chaos test.

- Where: p.4 §2.2 (NFR-4): "MMP downtime shall not affect agent read or write availability"
- Where: p.15 §15 (FR-4): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed"
- Where: p.8 §5: "Memory Management Plane - TemplateRegistry, NamespaceRegistry, SlotProvisioner, PolicyEngine, AuditStore, Admin API (port 8003)"
- Evidence EV-061 (doc, supports): "MMP downtime shall not affect agent read or write availability" [doc:DOC-sit_sample_v1#p4/s2.2]
- Evidence EV-041 (doc, supports): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed" [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-045 (doc, supports): "Policy decisions are not cached - they are evaluated fresh on every request" [doc:DOC-sit_sample_v1#p16/s16]
- Evidence EV-075 (inference, supports): "If the PolicyEngine is hosted in the MMP and every request goes to it uncached, and if slot provisioning happens inline through the MMP, then MMP availability is on the request path." [inference:EV-075] derived from EV-061, EV-041, EV-045
- Recommendation: In Sections 5, 16 and 21, state that runtime policy evaluation runs in the Gateway or Router data plane, reading policy data replicated from the MMP, and that the MMP only authors policy. In Section 15 Check 4, define the behaviour when the MMP is unavailable: either deny with reason 'slot not provisioned' or provision through a data-plane provisioner. Extend the NFR-4 test to cover a first write to an unprovisioned auto-provisionable slot.
  - Issue: The deployment boundary of the PolicyEngine and the inline slot provisioning in Check 4 contradict NFR-4.
  - Rationale: The document has a per-request policy engine and inline provisioning while also claiming the MMP can be down without affecting agents.
  - Expected benefit: NFR-4 becomes achievable and testable, and agent availability no longer depends on the admin plane. (objectives: NFR-4, FR-4, FR-8)
  - Supporting evidence: EV-061, EV-041, EV-045, EV-075
  - Verification: NFR-4 chaos test, with the MMP stopped, includes policy-evaluated reads and writes and a Check-4 auto-provision case.
- Next step: Platform architect: Fix the runtime deployment boundary of the PolicyEngine and SlotProvisioner, then update the NFR-4 chaos test.

### FND-014 Super-admin 'Everything'/emergency access contradicts the counselling 'no MMP override' wall

- **risk** · internal contradiction · severity **high** · confidence 0.75 (medium) · rank 5
- Disposition: **refinement now** (also: governance decision)

FR-5 and P4 forbid any MMP override path for wellbeing/counselling/. Section 19, however, grants Super Admin access to 'Everything', and Section 21 gives the super admin 'Overrides, corrections, emergency access'. On top of that, the Admin API DELETE and GET /audit endpoints are not scoped to exclude the sensitive schema. The FR-5 acceptance test only tries reads as three agents, so it cannot show that no MMP or admin override path exists.

- Where: p.3 §2.1 (FR-5): "wellbeing/counselling/ shall be classified HIGHLY_RESTRICTED with zero cross-domain reads and no"
- Where: p.18 §19: "Super Admin Everything - always audit-logged, mandatory reason required"
- Where: p.26 §27.1 (FR-5): "An automated test authenticates as the advisory, tutor, and career agents in"
- Evidence EV-039 (doc, supports): "Super admin Overrides, corrections, emergency access (always audit-logged)" [doc:DOC-sit_sample_v1#p20/s21]
- Evidence EV-038 (doc, supports): "Super Admin Everything - always audit-logged, mandatory reason required" [doc:DOC-sit_sample_v1#p18/s19]
- Evidence EV-062 (doc, supports): "An automated test authenticates as the advisory, tutor, and career agents in" [doc:DOC-sit_sample_v1#p26/s27.1]
- Recommendation: In Sections 19 and 21, explicitly exclude memory_sensitive from Super Admin and Institution Admin scope. The MMP service identity should hold no memory_sensitive credentials, and Admin API endpoints should reject wellbeing/counselling/ paths. Extend the FR-5 test to call the Admin API GET and DELETE and /policy/check as a super admin against counselling paths, and to confirm that MMP credentials fail against memory_sensitive.
  - Issue: Admin roles have override and emergency rights that conflict with FR-5, and the FR-5 test does not exercise admin paths.
  - Rationale: Under P3, a principle wins over a later section, but the conflict should be resolved in the text, not left for implementers to decide.
  - Expected benefit: FR-5 and P4 become enforceable and verifiable. (objectives: FR-5, NFR-5, P4)
  - Supporting evidence: EV-039, EV-038, EV-062
  - Verification: The extended FR-5 test returns DENIED for every admin path, and a credential scan shows no MMP access to memory_sensitive.
- Next step: Data governance officer / DPO: Confirm that no admin role has emergency access to counselling memory, and record any case-management exception outside the platform.

### FND-032 REVOKED token still serves learner data from the agent backup

- **risk** · security privacy gap · severity **high** · confidence 0.75 (medium) · rank 6
- Disposition: **governance decision** (also: refinement now)

On token revocation the design keeps serving the session from agent backup memory. Revocation is the control used for compromised accounts, departed learners or suspended access. Continuing to serve learner context to the holder of a revoked token defeats it and exposes personal data to a possibly unauthorised party. The NFR-6 test only checks that the token is rejected, not that no learner data is served.

- Where: p.8 §6 (NFR-6): "On revocation: inform the learner, serve from agent backup only, no re-authentication path is offered."
- Where: p.25 §25: "48 hours; EXPIRED → re-auth + agent backup; REVOKED → backup only"
- Evidence EV-072 (doc, supports): "On revocation: inform the learner, serve from agent backup only, no re-authentication path is offered." [doc:DOC-sit_sample_v1#p8/s6]
- Evidence EV-101 (doc, supports): "48 hours; EXPIRED → re-auth + agent backup; REVOKED → backup only" [doc:DOC-sit_sample_v1#p25/s25]
- Recommendation: In Sections 6, 15 and 25, change REVOKED behaviour to: end the session, load no per-learner backup, and serve only non-personal agent-global content. Add this case to the NFR-6 token lifecycle test.
  - Issue: Revocation does not stop learner-specific data from being served.
  - Rationale: A revoked identity should not receive personal data from any copy.
  - Expected benefit: Revocation becomes an effective access-termination control, in line with P2 and NFR-6. (objectives: NFR-6, P2)
  - Supporting evidence: EV-072, EV-101
  - Verification: Token lifecycle test: with a REVOKED token, the context pack contains no per_learner entries and the audit log records the denial.
- Next step: Security lead / DPO: Confirm the intended semantics of revocation and amend the confirmed decision on auth token behaviour.

### FND-034 MMP declared off the critical path but hosts AuditStore, PolicyEngine and on-demand slot provisioning

- **risk** · internal contradiction · severity **high** · confidence 0.75 (medium) · rank 7
- Disposition: **refinement now** (also: needs testing)

NFR-4 says MMP downtime cannot affect agent reads or writes. Yet AuditStore and PolicyEngine are listed as MMP components, Gateway Check 4 calls the MMP to provision slots inline, and every read (including cache hits) must be audited. If the MMP is down, either reads and writes fail (breaking NFR-4) or they proceed unaudited (breaking FR-13/P7). The design does not say whether audit failure is fail-open or fail-closed.

- Where: p.4 §2.2 (NFR-4): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical request path."
- Where: p.15 §15 (FR-4): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed"
- Where: p.8 §5: "Memory Management Plane - TemplateRegistry, NamespaceRegistry, SlotProvisioner, PolicyEngine, AuditStore, Admin API (port 8003)"
- Evidence EV-103 (doc, supports): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical request path." [doc:DOC-sit_sample_v1#p4/s2.2]
- Evidence EV-041 (doc, supports): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed" [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-104 (doc, supports): "Memory Management Plane - TemplateRegistry, NamespaceRegistry, SlotProvisioner, PolicyEngine, AuditStore, Admin API (port 8003)" [doc:DOC-sit_sample_v1#p8/s5]
- Evidence EV-119 (inference, supports): "Components called synchronously on every request (audit, policy, provisioning) are listed inside the MMP, so the MMP is in fact on the request path unless runtime copies are separated out." [inference:EV-119] derived from EV-103, EV-041, EV-104
- Recommendation: In Sections 5 and 21, separate the runtime data plane (audit sink, policy evaluation against replicated config, slot registry) from the MMP admin service. Define audit as durable and fail-closed (for example, an audit Kafka topic before ACK). Have Check 4 deny or queue provisioning when the MMP is unavailable.
  - Issue: Runtime dependencies on MMP components contradict NFR-4, and the behaviour when audit fails is undefined.
  - Rationale: NFR-4 and FR-13 both have to hold during an MMP outage.
  - Expected benefit: Availability during MMP outages without losing audit completeness. (objectives: NFR-4, FR-13, P7)
  - Supporting evidence: EV-103, EV-041, EV-104, EV-119
  - Verification: In the NFR-4 chaos test, stop the MMP and also verify that the FR-13 audit completeness holds and that a read of an unprovisioned slot behaves as specified.

### FND-003 Write ordering: tier topic chosen before classification, embed before validate, ACK before rejection

- **risk** · scalability or failure mode · severity **high** · confidence 0.70 (medium) · rank 9
- Disposition: **refinement now** (also: needs testing)

The write is placed on a sensitivity-tier Kafka topic before the consumer classifies sensitivity. The consumer also embeds before it validates, and the agent receives an ACK before the Validator can reject the write. A write that classification upgrades to HIGHLY_RESTRICTED has therefore already travelled the standard topic and may go through the standard embedding deployment. Strict-mode rejections are also never returned to the agent. This weakens the in-transit isolation claim and the FR-11 strict-mode intent.

- Where: p.4 §2.1 (FR-9): "processed asynchronously by a background consumer performing classify → embed → validate → route →"
- Where: p.17 §18: "separate topics per sensitivity tier keep HIGHLY_RESTRICTED writes physically isolated in transit."
- Where: p.16 §17 (FR-11): "Validates the write request against the slot template before any storage occurs."
- Evidence EV-036 (doc, supports): "processed asynchronously by a background consumer performing classify → embed → validate → route →" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-037 (doc, supports): "separate topics per sensitivity tier keep HIGHLY_RESTRICTED writes physically isolated in transit." [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-058 (inference, supports): "Topic selection happens before the consumer's classify step, so the tier of the topic rests on the agent's declared sensitivity; a misdeclared write crosses the standard topic and is embedded before the Validator's sensitivity-ceiling check, and the agent already holds an ACK when rejection occurs." [inference:EV-058] derived from EV-036, EV-037
- Recommendation: In Sections 2.1 (FR-9), 17 and 18, move template validation and sensitivity-ceiling checks into the synchronous Gateway step before topic selection. Reorder the consumer to classify → validate → embed → route → audit. Define what happens to a rejected or reclassified message (dead-letter topic, agent notification) and which embedding deployment each topic uses.
  - Issue: The pipeline order and the ACK timing do not match the isolation and rejection guarantees.
  - Rationale: Template and sensitivity-ceiling checks are deterministic and cheap, so they can run synchronously at the Gateway without blocking on embedding or storage (NFR-3).
  - Expected benefit: Keeps HIGHLY_RESTRICTED isolated in transit (NFR-5, P4), makes FR-11 rejections visible to agents, and avoids embedding cost for writes that will be rejected. (objectives: FR-9, FR-11, NFR-3, NFR-5)
  - Supporting evidence: EV-036, EV-037, EV-058
  - Verification: Integration test: a write that declares INTERNAL but carries a HIGHLY_RESTRICTED key is rejected synchronously and never appears on memory.write.standard. NFR-3 p99 is re-measured with validation inline.

### FND-022 Vector sizing arithmetic doesn't support the 128 GB SKU, the in-RAM claim or the growth ceiling

- **risk** · unsupported or incorrect claim · severity **high** · confidence 0.70 (medium) · rank 13
- Disposition: **refinement now** (also: needs prototyping)

Section 12 puts raw vectors at about 57 GB and the HNSW index at about 80 GB, which is roughly 137 GB before content text, B-tree indexes and the other tables. That is more than the 128 GB RAM of the confirmed SKU, so the 'in-RAM index' basis for 5-15 ms latency isn't shown. The stated growth ceiling of 30-40M vectors would mean about 180-245 GB of raw vectors alone on the same SKU. The per-learner breakdown adds up to about 340 vectors, not the ~600 used for the 9M estimate. NFR-1, NFR-2 and NFR-10 all rely on these figures.

- Where: p.12 §12 (NFR-1): "Azure SKU required Memory Optimised, 16 vCores, 128 GB RAM"
- Where: p.12 §12: "Growth ceiling before degradation ~30-40M vectors (~50,000-60,000 learners)"
- Where: p.12 §12: "Per-learner breakdown (~600 vectors across a full degree): core/identity 10, advisory 15, modules (6 active × 20)"
- Evidence EV-078 (doc, supports): "Azure SKU required Memory Optimised, 16 vCores, 128 GB RAM" [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-079 (doc, supports): "Growth ceiling before degradation ~30-40M vectors (~50,000-60,000 learners)" [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-080 (doc, supports): "Per-learner breakdown (~600 vectors across a full degree): core/identity 10, advisory 15, modules (6 active × 20)" [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-093 (inference, supports): "57 GB raw + 80 GB HNSW ≈ 137 GB > 128 GB RAM; 30-40M × 1536 × 4 bytes ≈ 184-246 GB raw; the listed per-learner items sum to 10+15+120+60+30+30+20+30+5+20 = 340, not ~600." [inference:EV-093] derived from EV-078, EV-079, EV-080
- Recommendation: Redo Section 12: reconcile the per-learner breakdown with the 600 figure, separate index size from heap size, give a total working-set estimate versus RAM, and replace the 30-40M ceiling with a derived figure or remove it. Consider options such as halfvec, reduced dimensions or partitioning, and re-check the SKU.
  - Issue: The sizing table is inconsistent with the SKU and the latency assumption it is meant to justify.
  - Rationale: The SKU, the latency target and the cost estimate are all derived from these numbers.
  - Expected benefit: A sizing basis that supports NFR-1/NFR-2 and a cost estimate (NFR-10) that can be defended. (objectives: NFR-1, NFR-2, NFR-10)
  - Supporting evidence: EV-078, EV-079, EV-080, EV-093
  - Verification: Measure table and index sizes after loading the NFR-1 synthetic dataset and compare them with the revised table.

### FND-033 Redis context-pack cache undermines fresh policy evaluation and tier isolation

- **risk** · security privacy gap · severity **high** · confidence 0.70 (medium) · rank 15
- Disposition: **refinement now** (also: needs testing)

Policy decisions are said to be evaluated fresh so that rule changes take effect immediately. However, the read path serves already-redacted context packs from Redis for the whole session TTL, so a policy change, permission revocation or deletion is not reflected until the session closes. The design separates HIGHLY_RESTRICTED data by schema, credentials and Kafka topic, but says nothing about whether sensitive-tier content is cached in the shared Redis, or about Redis encryption and access. This reopens the isolation that NFR-5 establishes.

- Where: p.16 §16 (FR-8): "Policy decisions are not cached - they are evaluated fresh on every request, so that a rule change takes effect immediately rather than waiting for a cache expiry."
- Where: p.18 §18 (FR-10): "context pack is cached so repeated queries within a session skip PostgreSQL entirely"
- Where: p.17 §18 (NFR-5): "separate topics per sensitivity tier keep HIGHLY_RESTRICTED writes physically isolated in transit."
- Evidence EV-102 (doc, supports): "Policy decisions are not cached - they are evaluated fresh on every request, so that a rule change takes effect immediately rather than waiting for a cache expiry." [doc:DOC-sit_sample_v1#p16/s16]
- Evidence EV-074 (doc, supports): "context pack is cached so repeated queries within a session skip PostgreSQL entirely" [doc:DOC-sit_sample_v1#p18/s18]
- Evidence EV-037 (doc, supports): "separate topics per sensitivity tier keep HIGHLY_RESTRICTED writes physically isolated in transit." [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-118 (inference, supports): "A cached pack reflects the policy outcome at caching time, so 'takes effect immediately' cannot hold for cache hits, and nothing extends tier isolation to Redis." [inference:EV-118] derived from EV-102, EV-074, EV-037
- Recommendation: In Section 18: invalidate cached packs on policy, permission, template or deletion events, or cap the TTL to a short bound; exclude HIGHLY_RESTRICTED content from the shared cache or use a separate cache instance with its own credentials; require encryption in transit and at rest for Redis. Update the Section 16 wording to match.
  - Issue: Cached context packs bypass policy freshness, and there is no stated isolation of sensitive-tier data in Redis.
  - Rationale: FR-8 and NFR-5 promise immediate policy effect and tier isolation, and the cache design does not preserve either.
  - Expected benefit: Policy changes, revocations and deletions take effect within a bounded time, and HIGHLY_RESTRICTED data stays isolated. (objectives: FR-8, FR-10, NFR-5)
  - Supporting evidence: EV-102, EV-074, EV-037, EV-118
  - Verification: Add a test to the FR-10 suite: revoke a slot permission mid-session, and the next read must not return the revoked slot's content. Add an NFR-5 check that sensitive keys never appear in the standard Redis instance.

### FND-037 Super Admin 'Everything' and an unauthenticated-by-design Admin API conflict with the counselling hard wall

- **risk** · security privacy gap · severity **high** · confidence 0.70 (medium) · rank 16
- Disposition: **refinement now** (also: governance decision) · already acknowledged in the document

Section 19 grants Super Admin access to everything, and Section 21 gives super admins overrides and emergency access, while FR-5/P4 forbid any MMP override of counselling data. The Admin API, which exposes audit logs, namespace maps and slot deletion, has no specified authentication or authorisation. Section 28 acknowledges the missing Admin API auth. This review adds that the role model itself contradicts FR-5 and that this is a security exposure, not only a code-generation gap.

- Where: p.18 §19 (FR-5): "Super Admin Everything - always audit-logged, mandatory reason required"
- Where: p.21 §21 (FR-14): "request/response JSON schemas and auth on the Admin API itself are not yet specified"
- Where: p.20 §21: "Super admin Overrides, corrections, emergency access (always audit-logged)"
- Evidence EV-038 (doc, supports): "Super Admin Everything - always audit-logged, mandatory reason required" [doc:DOC-sit_sample_v1#p18/s19]
- Evidence EV-109 (doc, supports): "request/response JSON schemas and auth on the Admin API itself are not yet specified" [doc:DOC-sit_sample_v1#p21/s21]
- Evidence EV-039 (doc, supports): "Super admin Overrides, corrections, emergency access (always audit-logged)" [doc:DOC-sit_sample_v1#p20/s21]
- Recommendation: In Section 19, restate Super Admin scope as 'everything except memory_sensitive content'. In Section 21, specify Admin API auth (Entra ID app roles, MFA, per-endpoint role mapping), ensure the MMP holds no memory_sensitive credentials, and add a break-glass procedure with dual approval if one is needed. Add a test that super-admin calls to counselling slots are denied.
  - Issue: The privileged admin scope is undefined and contradicts the counselling hard wall.
  - Rationale: FR-5 states there is no MMP override, so admin roles must be technically excluded from memory_sensitive.
  - Expected benefit: FR-5 holds against insiders, and admin access is least-privilege. (objectives: FR-5, FR-14, P4)
  - Supporting evidence: EV-038, EV-109, EV-039
  - Verification: Extend the FR-5 test with Super Admin and Institution Admin roles calling Admin API endpoints against wellbeing/counselling/, and expect DENIED.
- Next step: Security lead: Define the Admin API role model and confirm that the MMP has no credentials for memory_sensitive.

### FND-026 The claim that the DDL is 'complete' is contradicted by fields the design relies on

- **risk** · unsupported or incorrect claim · severity **medium** · confidence 0.80 (high) · rank 21
- Disposition: **refinement now**

Section 28 calls the DDL 'concrete and complete' and ready for migrations. But Section 17 relies on an embedded flag that no table has. memory_events and memory_documents have no retention, expires_at or pii columns, although NFR-7 requires per-slot retention and pii flagging. Section 10 places consent in meta-memory, but there is no column for it. Code generated from Section 11 would therefore miss NFR-7 and the embedder fallback.

- Where: p.29 §28: "Nothing further needed - DDL is concrete and complete (Section"
- Where: p.4 §2.2 (NFR-7): "All operations on personal data shall be logged; retention rules shall be enforceable per slot; PII-bearing"
- Where: p.16 §17: "Add to MMP ingestion backlog for re-embed -"
- Evidence EV-085 (doc, supports): "Nothing further needed - DDL is concrete and complete (Section" [doc:DOC-sit_sample_v1#p29/s28]
- Evidence EV-068 (doc, supports): "Flag record as unembedded (embedded: false)" [doc:DOC-sit_sample_v1#p16/s17]
- Evidence EV-097 (inference, supports): "The Section 11 DDL has no embedded column, and memory_events/memory_documents have no retention, expiry or pii columns, so the 'complete' claim does not cover the Section 17 fallback or NFR-7." [inference:EV-097] derived from EV-085, EV-068
- Recommendation: Add embedded BOOLEAN, plus retention/expires_at/pii to all three tables, template_version, consent fields and an audit table DDL to Section 11. Downgrade the Section 28 database schema row to 'Mostly ready' until this is done.
  - Issue: The DDL is missing columns that other sections and NFR-7 require.
  - Rationale: Section 28 tells builders to generate migrations from this DDL directly.
  - Expected benefit: A schema that supports NFR-7 and the embedder fallback when first built. (objectives: NFR-7, FR-13)
  - Supporting evidence: EV-085, EV-068, EV-097
  - Verification: Trace every field named in Sections 10, 17 and 23 to a DDL column.

### FND-017 DDL declared 'complete' lacks columns other sections require

- **risk** · internal contradiction · severity **medium** · confidence 0.75 (medium) · rank 22
- Disposition: **refinement now**

Section 28 calls the DDL 'concrete and complete', but other sections rely on columns it lacks. memory_events and memory_documents have no pii, retention or expires_at columns, so the per-slot retention and PII flagging in NFR-7 cannot be enforced for episodic or meta records. memory_events has no key column, although templates define EPISODIC keys (e.g. advisor_notes) that the Validator checks. memory_vectors has no 'embedded' flag, which the Embedder fallback needs. No table records template version or agent_id/source. Code generated from this DDL 'directly' would miss these behaviours.

- Where: p.29 §28: "Nothing further needed - DDL is concrete and complete"
- Where: p.4 §2.2 (NFR-7): "All operations on personal data shall be logged; retention rules shall be enforceable per slot; PII-bearing"
- Evidence EV-067 (doc, supports): "Nothing further needed - DDL is concrete and complete" [doc:DOC-sit_sample_v1#p29/s28]
- Evidence EV-068 (doc, supports): "Flag record as unembedded (embedded: false)" [doc:DOC-sit_sample_v1#p16/s17]
- Evidence EV-077 (inference, supports): "The Section 11 DDL for memory_events has no key, pii, retention or expires_at column and memory_vectors has no embedded column, so the requirements quoted cannot be met by the schema as written." [inference:EV-077] derived from EV-067, EV-068
- Recommendation: In Section 11, add key, pii, retention and expires_at to memory_events, and pii, retention and expires_at to memory_documents. Add embedded BOOLEAN to memory_vectors, and add template_version and writer agent_id to all three tables. In Section 28, change the DDL rating to 'Mostly ready' until this is done.
  - Issue: The schema does not support the Embedder fallback, NFR-7, or key validation for episodic keys.
  - Rationale: Section 28 marks the DDL ready for direct migration generation, so any gaps will carry into the build.
  - Expected benefit: NFR-7 retention and PII enforcement, and the Embedder fallback, become implementable. (objectives: NFR-7, FR-11, FR-3)
  - Supporting evidence: EV-067, EV-068, EV-077
  - Verification: The NFR-7 schema scan covers all three table types, and an Embedder-outage test persists embedded=false.

### FND-005 MMP sits in the live request path despite NFR-4

- **risk** · internal contradiction · severity **medium** · confidence 0.70 (medium) · rank 24
- Disposition: **refinement now**

NFR-4 relies on the MMP being outside the critical path. Yet Gateway Check 4 has the MMP provision missing slots inline, the PolicyEngine and AuditStore are listed as MMP components, and the Auditor must log every read and write. If any of these is hosted by the MMP service, MMP downtime blocks or degrades agent requests, so the NFR-4 rationale does not hold as written.

- Where: p.15 §15 (FR-4): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed"
- Where: p.4 §2.2 (NFR-4): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical"
- Where: p.8 §5: "Memory Management Plane - TemplateRegistry, NamespaceRegistry, SlotProvisioner, PolicyEngine,"
- Evidence EV-041 (doc, supports): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed" [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-042 (doc, supports): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical" [doc:DOC-sit_sample_v1#p4/s2.2]
- Evidence EV-059 (inference, supports): "Inline slot provisioning, an MMP-hosted PolicyEngine evaluated fresh on every request, and an MMP-hosted AuditStore written on every operation each put the MMP on the synchronous path." [inference:EV-059] derived from EV-041, EV-042
- Recommendation: In Sections 5, 15 and 21, separate the runtime components (policy evaluation, audit sink, slot existence) from MMP admin functions. Make Check 4 either deny or queue provisioning when the MMP is unavailable, and state where the runtime PolicyEngine and the audit sink run.
  - Issue: Several runtime dependencies on the MMP contradict NFR-4.
  - Rationale: NFR-4 is an availability objective, and the design's placement of components decides whether it is met.
  - Expected benefit: Agent read and write availability is independent of the MMP admin service (NFR-4). (objectives: NFR-4, FR-4, FR-13)
  - Supporting evidence: EV-041, EV-042, EV-059
  - Verification: Extend the NFR-4 chaos test to include a first write to an auto-provisionable slot that does not yet exist, and a fresh policy evaluation, while the MMP is down.

### FND-007 Session-long context-pack cache undercuts fresh policy evaluation and deletion

- **risk** · internal contradiction · severity **medium** · confidence 0.65 (medium) · rank 27
- Disposition: **refinement now**

Section 16 says policy is never cached, so that rule changes take effect immediately. Section 18, however, caches the already ranked and redacted context pack for the whole session, so a cache hit serves content that reflects the policy, permissions and deletions in force when the pack was built. The cache key (per agent, or per learner) is also unspecified, so a pack redacted for one agent could be served to another. This weakens P3 and FR-15 during a session.

- Where: p.16 §16 (FR-8): "Policy decisions are not cached - they are evaluated fresh on every request"
- Where: p.18 §18 (FR-10): "the persession context pack is cached so repeated queries within a session skip PostgreSQL entirely"
- Evidence EV-045 (doc, supports): "Policy decisions are not cached - they are evaluated fresh on every request" [doc:DOC-sit_sample_v1#p16/s16]
- Evidence EV-046 (doc, supports): "the persession context pack is cached so repeated queries within a session skip PostgreSQL entirely" [doc:DOC-sit_sample_v1#p18/s18]
- Recommendation: In Section 18, specify the cache key (learner_id, agent_id, purpose and policy version) and invalidation triggers (policy publish, permission change, deletion, write to a slot in the pack). Alternatively, state a bounded staleness accepted by the DPO.
  - Issue: The invalidation and keying rules for the cached context pack are missing.
  - Rationale: Without them, the design's 'immediate effect' claim for policy changes does not hold on the read path.
  - Expected benefit: Policy changes, permission revocations and FR-15 deletions take effect within a bounded time. (objectives: FR-10, FR-15, P3)
  - Supporting evidence: EV-045, EV-046
  - Verification: Extend the FR-10 test: revoke an agent's read permission mid-session, and the next read is denied or re-filtered rather than served from the cache.

### FND-009 Degraded mode serves learner memory on EXPIRED/REVOKED tokens, contrary to FR-4 deny-on-failure

- **risk** · security privacy gap · severity **medium** · confidence 0.60 (medium) · rank 30
- Disposition: **governance decision** (also: refinement now)

FR-4 says failing any check denies the request. Check 3, however, continues serving the learner's personal backup memory when the token is EXPIRED or even REVOKED. A revoked token means the learner's identity is no longer vouched for, so personal context may be served to an unverified party, against P2. This review keeps the approved 48-hour token decision and asks only that degraded-mode scope be bounded.

- Where: p.8 §6 (NFR-6): "On revocation: inform the learner, serve from agent backup"
- Where: p.4 §2.1 (FR-4): "at any check denies the request and logs the reason."
- Evidence EV-049 (doc, supports): "On revocation: inform the learner, serve from agent backup" [doc:DOC-sit_sample_v1#p8/s6]
- Evidence EV-050 (doc, supports): "at any check denies the request and logs the reason." [doc:DOC-sit_sample_v1#p3/s2.1]
- Recommendation: In Sections 6 and 15, restrict REVOKED to non-personal service (agent global only), and define which backup keys may be served while EXPIRED. Amend FR-4 to name the degraded-mode exception explicitly.
  - Issue: The degraded-mode behaviour contradicts FR-4 and serves personal data without a valid identity.
  - Rationale: Revocation usually means a compromised or terminated account. P2 private-by-default favours not serving personal context.
  - Expected benefit: FR-4 and P2 hold, and degraded-mode behaviour (NFR-6) is bounded. (objectives: FR-4, NFR-6, P2)
  - Supporting evidence: EV-049, EV-050
  - Verification: NFR-6 test: a REVOKED token yields no per-learner backup content in the response.
- Next step: Data governance officer / DPO: Decide what learner data, if any, may be served under EXPIRED and REVOKED tokens.

### FND-020 Session-TTL context-pack cache undermines 'policy takes effect immediately' and deletion

- **risk** · internal contradiction · severity **medium** · confidence 0.60 (medium) · rank 31
- Disposition: **refinement now**

Section 16 says policy is never cached, so that rule changes take effect immediately. But the read path serves an already ranked and redacted context pack from Redis for the whole session TTL, and it is invalidated only on session close or token expiry. Policy changes, permission revocations, FR-15 deletions and new async writes are therefore not reflected until the session ends. The cache key, and whether one agent's pack could be served to another agent, is also not specified.

- Where: p.16 §16 (FR-8): "Policy decisions are not cached - they are evaluated fresh on every request"
- Where: p.18 §18 (FR-10): "context pack is cached so repeated queries within a session skip PostgreSQL entirely"
- Evidence EV-045 (doc, supports): "Policy decisions are not cached - they are evaluated fresh on every request" [doc:DOC-sit_sample_v1#p16/s16]
- Evidence EV-074 (doc, supports): "context pack is cached so repeated queries within a session skip PostgreSQL entirely" [doc:DOC-sit_sample_v1#p18/s18]
- Recommendation: In Section 18, key the cache by (agent_id, learner_id, session_id, policy_version). Invalidate on policy publish, deletion, and writes to cached slots. Add an FR-10 test case where a policy change mid-session causes a cache MISS.
  - Issue: There are no cache invalidation rules for policy changes, deletions or writes, and no cache-key scope.
  - Rationale: Without them the immediacy claim in Section 16 is not true for cached content.
  - Expected benefit: FR-8 immediacy and FR-15 deletion apply to served content, not only to stored content. (objectives: FR-8, FR-10, FR-15)
  - Supporting evidence: EV-045, EV-074
  - Verification: An extended FR-10 test checks a mid-session policy change and a mid-session deletion.

## Gaps

### FND-035 Async write path has no rejection feedback, dead-letter, idempotency or ordering rules

- **gap** · scalability or failure mode · severity **high** · confidence 0.75 (medium) · rank 8
- Disposition: **refinement now** (also: needs testing)

Agents get an ACK at enqueue time, but template validation (strict-mode REJECT) runs later in the consumer, after embedding. Writes rejected or failing after the ACK are therefore silently lost to the agent, which contradicts the Gateway's 'no silent errors' claim. Kafka retry is mentioned without poison-message handling, a dead-letter queue, idempotency keys (duplicates in the append-only event table) or per-learner ordering. Running embed before validate also spends embedding cost on writes that will be rejected.

- Where: p.4 §2.1 (FR-9): "processed asynchronously by a background consumer performing classify → embed → validate → route →"
- Where: p.17 §18 (FR-9): "failed writes queue and retry automatically; multiple independent consumers (audit, embedding, SIS sync) read the same event stream"
- Where: p.15 §15 (FR-4): "Any failure denies the request and logs the reason. There are no silent errors."
- Evidence EV-036 (doc, supports): "processed asynchronously by a background consumer performing classify → embed → validate → route →" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-105 (doc, supports): "failed writes queue and retry automatically; multiple independent consumers (audit, embedding, SIS sync) read the same event stream" [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-106 (doc, supports): "Any failure denies the request and logs the reason. There are no silent errors." [doc:DOC-sit_sample_v1#p15/s15]
- Recommendation: In Section 18: move the synchronous schema/key validation to the Gateway before the ACK (cheap and template-local); reorder the consumer to classify → validate → embed; add a dead-letter topic with a retry limit, idempotency keys on memory_id/event_id, per-learner partitioning for ordering, and a status/notification channel (MMP dashboard) for rejected writes.
  - Issue: Undefined failure semantics after the ACK on the write path.
  - Rationale: FR-9/NFR-3 make writes non-blocking, so post-ACK failures need an explicit path to stay observable and non-lossy.
  - Expected benefit: No silent data loss, no duplicate memories under retry, and lower embedding cost. (objectives: FR-9, FR-11, NFR-3, FR-13)
  - Supporting evidence: EV-036, EV-105, EV-106
  - Verification: Fault-injection test: duplicate delivery produces one record, a poison message lands in the DLQ with an audit entry, and a strict-mode rejection is visible to the agent or dashboard.

### FND-015 No error path for async writes rejected after ACK

- **gap** · scalability or failure mode · severity **high** · confidence 0.70 (medium) · rank 11
- Disposition: **refinement now**

Writes are ACKed when they are enqueued. Validation (FR-11 strict rejection, memory_type mismatch, sensitivity ceiling) happens later in the background consumer. The design has no dead-letter queue, no notification back to the agent, and no rule separating validation rejections from transient failures. Since 'failed writes queue and retry automatically', a write that will always be rejected could retry forever. Meanwhile the agent believes the memory was persisted, which undermines FR-9 and FR-11, and the FR-11 test does not say where the rejection is observable.

- Where: p.17 §18 (FR-9): "overwhelm the store; failed writes queue and retry automatically; multiple independent consumers"
- Where: p.4 §2.1 (FR-11): "The Validator shall reject (strict mode) or warn-and-log (lenient mode) any write containing a key not"
- Where: p.4 §2.1 (FR-9): "Writes shall be enqueued to a message broker (agent receives an immediate acknowledgement) and"
- Evidence EV-063 (doc, supports): "overwhelm the store; failed writes queue and retry automatically; multiple independent consumers" [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-064 (doc, supports): "Writes shall be enqueued to a message broker (agent receives an immediate acknowledgement) and" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-076 (inference, supports): "Because rejection happens after the ACK and retries are automatic, a deterministic validation failure has no defined terminal state or feedback to the agent." [inference:EV-076] derived from EV-063, EV-064
- Recommendation: In Section 18, add the following: classify consumer failures as permanent (validation) or transient (embedding, DB); send permanent failures to a dead-letter topic per tier with an audit DENIED entry and a dashboard warning; set a retry limit and backoff for transient failures; and either define a write-status callback or query for agents, or have the Gateway pre-validate template keys synchronously before enqueueing. Update the FR-11 acceptance test to state where the rejection is observed.
  - Issue: Rejected and poison writes have no defined handling after the ACK.
  - Rationale: The async design moves validation after the acknowledgement, so the failure path has to be designed explicitly.
  - Expected benefit: FR-11 rejections can be observed and acted on, and the consumer cannot get stuck on poison messages (FR-9). (objectives: FR-9, FR-11, FR-13)
  - Supporting evidence: EV-063, EV-064, EV-076
  - Verification: A test injects an undeclared-key write in strict mode and asserts a dead-letter entry, a single audit DENIED entry, and no repeated retries.

### FND-016 Agent backup copies are outside deletion, tiering and the FR-15 test

- **gap** · security privacy gap · severity **high** · confidence 0.70 (medium) · rank 12
- Disposition: **refinement now** (also: governance decision)

Every agent writes to its own per-learner backup 'always, immediate', and that backup survives a learner's self-deletion. The FR-15 test, however, only checks the namespace. The design never says where agent backups are stored, whether the counselling agent's backup sits in the memory_sensitive tier (NFR-5), or how retention, PII and deletion rules apply to backups. As written, a learner's deletion request leaves copies of the data behind, and highly restricted content can live outside the two-tier store.

- Where: p.13 §13 (FR-16): "the agent backup survives learner deletion of their own memory (enabling session resume)"
- Where: p.27 §27.1 (FR-15): "A learner-initiated deletion request removes user-deletable records and"
- Evidence EV-034 (doc, supports): "the agent backup survives learner deletion of their own memory (enabling session resume)" [doc:DOC-sit_sample_v1#p13/s13]
- Evidence EV-065 (doc, supports): "Agent own memory (always, immediate)" [doc:DOC-sit_sample_v1#p14/s14]
- Evidence EV-066 (doc, supports): "A learner-initiated deletion request removes user-deletable records and" [doc:DOC-sit_sample_v1#p27/s27.1]
- Recommendation: In Sections 13 and 20, specify where per-learner agent backups are stored (schema and tier), require the counselling agent's backup to sit in memory_sensitive, and decide whether learner deletion cascades to backups. The DPO should decide whether the 'session resume' benefit justifies keeping the data. Extend the FR-15 and NFR-5 tests to include agent backups.
  - Issue: Agent backups are a second store of personal data, with no defined storage tier, retention or deletion semantics.
  - Rationale: FR-15, NFR-5 and NFR-7 apply to all personal data. The test covers only the namespace, so retained backups would go undetected.
  - Expected benefit: FR-15 deletion becomes complete and checkable, and the NFR-5 isolation also covers backups. (objectives: FR-15, FR-16, NFR-5, NFR-7)
  - Supporting evidence: EV-034, EV-065, EV-066
  - Verification: The FR-15 test asserts that after deletion no user-deletable data remains in any agent backup, or that retention matches a documented DPO decision.
- Next step: Data governance officer / DPO: Decide whether learner deletion cascades to agent backups and record the retention basis.

### FND-036 Counselling escalations either blocked by the sensitivity ceiling or leak HIGHLY_RESTRICTED content into the standard tier

- **gap** · security privacy gap · severity **high** · confidence 0.65 (medium) · rank 18
- Disposition: **governance decision** (also: refinement now)

Escalation slots are RESTRICTED and readable by humans and the target-domain agent. The Validator rejects writes that exceed a slot's ceiling. A counselling-agent escalation (for example, risk of self-harm) carrying HIGHLY_RESTRICTED content is therefore either rejected, which is a safety failure, or must be downgraded into memory_standard, which breaches the counselling hard wall. The design does not define this path.

- Where: p.10 §8 (FR-7): "RESTRICTED. Any agent writes. Human + target domain read only."
- Where: p.16 §17 (FR-11): "e.g. writing HIGHLY_RESTRICTED to an INTERNAL slot -> REJECT"
- Where: p.19 §19 (FR-5): "Counsellor agent reads only. Human counsellors may access via a separate clinical system."
- Evidence EV-107 (doc, supports): "RESTRICTED. Any agent writes. Human + target domain read only." [doc:DOC-sit_sample_v1#p10/s8]
- Evidence EV-108 (doc, supports): "e.g. writing HIGHLY_RESTRICTED to an INTERNAL slot -> REJECT" [doc:DOC-sit_sample_v1#p16/s17]
- Evidence EV-120 (inference, supports): "A HIGHLY_RESTRICTED escalation exceeds the RESTRICTED ceiling of escalations/, so it is either rejected or must be downgraded, and neither outcome is acceptable for welfare risk." [inference:EV-120] derived from EV-107, EV-108
- Recommendation: In Sections 8, 19 and 23, define a sensitive-tier escalation variant (stored in memory_sensitive and readable only by human counsellors or the clinical system) or a minimal-content RESTRICTED escalation template (flag plus referral only, with the content field forbidden). Add it to the FR-7 test.
  - Issue: No defined escalation path for counselling-originated risk.
  - Rationale: Learner safety and FR-5 both need an explicit route.
  - Expected benefit: Welfare escalations reach humans without breaching the hard wall. (objectives: FR-5, FR-7)
  - Supporting evidence: EV-107, EV-108, EV-120
  - Verification: In the FR-7 escalation test, a counselling-agent escalation reaches the human reviewer, and no HIGHLY_RESTRICTED key appears in memory_standard.
- Next step: Head of Counselling Services with DPO: Decide the content and storage tier allowed for counselling-originated escalations.

### FND-006 Policy Engine combination logic is unspecified while dependent components are rated Ready

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.80 (high) · rank 20
- Disposition: **refinement now** · already acknowledged in the document

Section 28 itself acknowledges that the seven-dimension decision algorithm is unspecified. The review adds two points. First, Gateway Checks 5 and 6, the Validator and the Read path's Redact step all depend on that logic, yet they are rated 'Ready', which overstates readiness. Second, the FR-8 test expects a DENY per dimension even though Retention and Redaction produce expiry or masking outcomes rather than denials.

- Where: p.30 §28 (FR-8): "A Policy Engine decision table or pseudocode - precedence rules across the seven dimensions, expressed as"
- Where: p.27 §27.1 (FR-8): "A test matrix exercises all seven dimensions independently (one violating"
- Evidence EV-043 (doc, supports): "A Policy Engine decision table or pseudocode - precedence rules across the seven dimensions, expressed as" [doc:DOC-sit_sample_v1#p30/s28]
- Evidence EV-044 (doc, supports): "A test matrix exercises all seven dimensions independently (one violating" [doc:DOC-sit_sample_v1#p27/s27.1]
- Recommendation: In Section 16, add a decision table with the outcome set (ALLOW/DENY/REDACT/EXPIRE), the precedence order, and the point in the read and write paths where each dimension is evaluated. Downgrade the Gateway and Validator rows in Section 28 to 'Mostly ready' until then, and revise the FR-8 criteria in Section 27 so each dimension asserts its own outcome type.
  - Issue: Policy outcomes, their precedence and their integration points are undefined.
  - Rationale: FR-8 applies to every operation, so the Gateway and the Router cannot be built correctly without it.
  - Expected benefit: FR-8 can be implemented, and the FR-8 test can verify it. (objectives: FR-8, FR-4)
  - Supporting evidence: EV-043, EV-044
  - Verification: FR-8 test matrix with the expected outcome per dimension, reviewed against the decision table.

### FND-039 Embedding-outage fallback relies on columns and indexes absent from the 'complete' DDL

- **gap** · scalability or failure mode · severity **medium** · confidence 0.75 (medium) · rank 23
- Disposition: **refinement now**

The Embedder fallback flags records as embedded:false and switches to BM25 keyword search. However, the Section 11 DDL has no embedded column and no full-text (tsvector/GIN) index, and Section 28 calls the DDL complete. As written, an Azure OpenAI outage leaves semantic reads without a working retrieval path, and unembedded records cannot be found for re-embedding.

- Where: p.16 §17: "Fall back to BM25 keyword search for retrieval"
- Where: p.29 §28: "Nothing further needed - DDL is concrete and complete (Section"
- Evidence EV-090 (doc, supports): "Fall back to BM25 keyword search for retrieval" [doc:DOC-sit_sample_v1#p16/s17]
- Evidence EV-085 (doc, supports): "Nothing further needed - DDL is concrete and complete (Section" [doc:DOC-sit_sample_v1#p29/s28]
- Recommendation: Add an 'embedded BOOLEAN' column and a tsvector column with a GIN index to memory_vectors in Section 11 (both schemas). State the ranking used in fallback mode. Correct the Section 28 readiness note.
  - Issue: The fallback path is not supported by the schema.
  - Rationale: Degraded retrieval must work when the embedding service is down.
  - Expected benefit: Reads keep working during embedding outages, and the re-embed backlog can be queried. (objectives: FR-10, NFR-2)
  - Supporting evidence: EV-090, EV-085
  - Verification: Chaos test: with the embedding endpoint blocked, a semantic read returns keyword results, and the unembedded records appear in the MMP ingestion backlog.

### FND-040 No HA/DR, backup/restore, operational monitoring or owners for open items

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.70 (medium) · rank 26
- Disposition: **refinement now** (also: governance decision) · already acknowledged in the document

The design specifies no RPO/RTO, PostgreSQL HA or backup, point-in-time restore, or Redis/Event Hubs failover. It sets no alerting on consumer lag, DLQ depth, cache hit rate or denial spikes; the MMP dashboard covers quality, PII, usage and cost only. The Pending Backlog lists material governance items (audit retention, PDPA sign-off, SIS failure handling) with no owner or target date. For a platform that is the authoritative store for all six agents, this leaves outage recovery and accountability undefined.

- Where: p.26 §26: "Memory Router Component 5 (Auditor) - log schema detail, retention period, PDPA alignment sign-off."
- Where: p.26 §26: "MMP in detail - template versioning conflict resolution, SIS integration failure handling."
- Evidence EV-086 (doc, supports): "Memory Router Component 5 (Auditor) - log schema detail, retention period, PDPA alignment sign-off." [doc:DOC-sit_sample_v1#p26/s26]
- Evidence EV-089 (doc, supports): "MMP in detail - template versioning conflict resolution, SIS integration failure handling." [doc:DOC-sit_sample_v1#p26/s26]
- Recommendation: Add an Operations section with: RPO/RTO targets; PostgreSQL zone-redundant HA and PITR retention; Event Hubs/Redis failover behaviour; an alert list (consumer lag, DLQ, audit write failures, Gateway deny rate); and on-call ownership. Add an owner and target phase to each Section 26 item.
  - Issue: Operational resilience and accountability are unspecified.
  - Rationale: P1 makes the namespace authoritative, so losing it is losing the system of record.
  - Expected benefit: Defined recovery targets and named owners for the PDPA-critical open items. (objectives: NFR-4, NFR-7, FR-13)
  - Supporting evidence: EV-086, EV-089
  - Verification: A restore drill meets the RPO/RTO, and every backlog item has a named owner before Build Phase 3.
- Next step: Platform lead: Assign owners to the Pending Backlog items and draft RPO/RTO with the DPO.

### FND-041 Anonymisation of cross-learner and cohort aggregates is undefined

- **gap** · security privacy gap · severity **medium** · confidence 0.60 (medium) · rank 36
- Disposition: **refinement now** (also: governance decision)

Cross-learner patterns and cohort aggregates are readable by all agents. Only HIGHLY_RESTRICTED data is excluded, so RESTRICTED data (financial aid, accessibility, at-risk flags) can feed them. No anonymisation method, minimum group size or re-identification test is specified, and small cohorts or modules are easily re-identifiable. This weakens P2 and PDPA compliance.

- Where: p.6 §3 (P2): "Private by default - memory is private to the learner, shared by exception, anonymised for service"
- Where: p.21 §22: "Example: ICT-2024-intake concept difficulty patterns from AI Tutor aggregate."
- Evidence EV-111 (doc, supports): "Private by default - memory is private to the learner, shared by exception, anonymised for service" [doc:DOC-sit_sample_v1#p6/s3]
- Evidence EV-112 (doc, supports): "Example: ICT-2024-intake concept difficulty patterns from AI Tutor aggregate." [doc:DOC-sit_sample_v1#p21/s22]
- Recommendation: In Sections 13 and 22, specify: the source sensitivity allowed in aggregates (INTERNAL only, by default); a minimum group size (k threshold); suppression rules; and a DPO approval step for each aggregate type.
  - Issue: Aggregates are shared institution-wide without a defined anonymisation standard.
  - Rationale: P2 depends on anonymisation being effective.
  - Expected benefit: Aggregate sharing does not re-identify learners. (objectives: P2, NFR-7)
  - Supporting evidence: EV-111, EV-112
  - Verification: A test asserts that aggregates below the k threshold are suppressed and that no RESTRICTED-sourced fields appear.

### FND-043 Cost requirement covers only the vector store

- **gap** · missing or unverifiable requirement · severity **low** · confidence 0.60 (medium) · rank 41
- Disposition: **refinement now**

NFR-10 bounds only the vector-store cost. Event Hubs, Redis, embedding calls (including a separate sensitive embedding deployment) and audit storage growth from logging every read are unbudgeted, although the MMP tracks embedding cost. The total cost of operation therefore has no target to monitor against.

- Where: p.5 §2.2 (NFR-10): "Vector-store infrastructure cost shall remain within the SGD 800-1,200/month estimate at 15,000-learner"
- Evidence EV-084 (doc, supports): "Vector-store infrastructure cost shall remain within the SGD 800-1,200/month estimate at 15,000-learner" [doc:DOC-sit_sample_v1#p5/s2.2]
- Recommendation: Extend NFR-10 or add a requirement with per-component budgets (Event Hubs, Redis, embeddings, audit storage) and a projection of audit log volume.
  - Issue: Total platform cost has no budget.
  - Rationale: The cost-monitoring dashboard needs a target to alert against.
  - Expected benefit: Cost overruns are detectable. (objectives: NFR-10)
  - Supporting evidence: EV-084
  - Verification: The NFR-10 cost model check covers all components.

## Ambiguities

### FND-004 Super Admin 'Everything' and emergency override conflict with the counselling hard wall

- **ambiguity** · internal contradiction · severity **high** · confidence 0.70 (medium) · rank 10
- Disposition: **governance decision** (also: refinement now)

P4 and FR-5 forbid any MMP override of wellbeing/counselling/, with no exceptions. Section 19, however, gives Super Admin access to 'Everything', and Section 21 gives the super admin overrides and emergency access through the MMP. There are two materially different readings: the Super Admin can read counselling records, or the Super Admin is excluded. FR-5 cannot be implemented or tested unambiguously until one is chosen. The text 'Counsellor agent reads only' also sits uneasily with the counsellor-written session_summaries key, which leaves unclear who may write to the slot.

- Where: p.18 §19: "Super Admin Everything - always audit-logged, mandatory reason required"
- Where: p.20 §21: "Super admin Overrides, corrections, emergency access (always audit-logged)"
- Where: p.6 §3 (P4, FR-5): "Counselling hard wall - wellbeing/counselling/ is HIGHLY_RESTRICTED. Zero cross-domain reads."
- Evidence EV-038 (doc, supports): "Super Admin Everything - always audit-logged, mandatory reason required" [doc:DOC-sit_sample_v1#p18/s19]
- Evidence EV-039 (doc, supports): "Super admin Overrides, corrections, emergency access (always audit-logged)" [doc:DOC-sit_sample_v1#p20/s21]
- Evidence EV-040 (doc, supports): "Counselling hard wall - wellbeing/counselling/ is HIGHLY_RESTRICTED. Zero cross-domain reads." [doc:DOC-sit_sample_v1#p6/s3]
- Recommendation: In the Section 19 roles table and the Section 21 users table, state explicitly that the Super Admin and MMP credentials have no access to memory_sensitive, or define a separately governed break-glass path outside the MMP. In Section 23, state which roles write to the counselling keys.
  - Issue: The Super Admin's scope against the counselling hard wall is undefined.
  - Rationale: Section 3 says the principle wins, but implementers need the exclusion written where the roles are defined.
  - Expected benefit: FR-5 and P4 become unambiguous to implement and test. (objectives: FR-5, P4, NFR-5)
  - Supporting evidence: EV-038, EV-039, EV-040
  - Verification: Add a case to the FR-5 test: a Super Admin read of wellbeing/counselling/ through the Admin API is DENIED, and MMP database credentials fail against memory_sensitive.
- Next step: Data governance officer / DPO: Confirm whether any break-glass access to counselling records exists and record it in Sections 19 and 21.

### FND-019 Token-check failure: deny (FR-4) or degraded serving (Section 15)?

- **ambiguity** · ambiguous requirement · severity **medium** · confidence 0.65 (medium) · rank 28
- Disposition: **refinement now** (also: governance decision)

FR-4 says failure at any check denies the request, and the FR-4 test expects a DENY when the token check alone fails. Section 15 and Section 6 instead say that EXPIRED and REVOKED tokens continue in degraded mode using the agent's backup, which for REVOKED means serving the learner's data after revocation. Section 13 also defines a REFRESHING state that Check 3 does not handle. These readings lead to different implementations and different test outcomes.

- Where: p.3 §2.1 (FR-4): "at any check denies the request and logs the reason"
- Where: p.8 §6 (NFR-6): "On revocation: inform the learner, serve from agent backup only, no re-authentication path is offered."
- Evidence EV-071 (doc, supports): "at any check denies the request and logs the reason" [doc:DOC-sit_sample_v1#p3/s2.1]
- Evidence EV-072 (doc, supports): "On revocation: inform the learner, serve from agent backup only, no re-authentication path is offered." [doc:DOC-sit_sample_v1#p8/s6]
- Evidence EV-073 (doc, supports): "status: ACTIVE | EXPIRED | REFRESHING | REVOKED" [doc:DOC-sit_sample_v1#p13/s13]
- Recommendation: In Sections 15 and 2.1, state that Check 3 denies namespace access while the agent may serve from its backup. Add an explicit governance decision on whether a REVOKED state also blocks backup use. Define how REFRESHING is handled. Align the FR-4 and NFR-6 tests with these rules.
  - Issue: Behaviour on token failure, and whether backup serving is allowed after revocation, is ambiguous.
  - Rationale: A revoked token normally signals that access should stop, but the design keeps serving data from the backup.
  - Expected benefit: FR-4, NFR-6 and FR-16 are consistent and testable. (objectives: FR-4, NFR-6, FR-16)
  - Supporting evidence: EV-071, EV-072, EV-073
  - Verification: The token lifecycle test asserts the namespace is DENIED and backup behaviour matches the decision for each of ACTIVE, EXPIRED, REFRESHING and REVOKED.
- Next step: Data governance officer / DPO: Decide whether learner data in agent backups may be served after token revocation.

### FND-042 Holder of tier credentials and secrets management unspecified

- **ambiguity** · security privacy gap · severity **medium** · confidence 0.55 (medium) · rank 38
- Disposition: **refinement now**

The design says no agent touches a store directly, but describes memory_sensitive access as 'designated agents only' with separate credentials. It does not say whether the Gateway/Router, the consumers or the agents hold these credentials, or how they are stored and rotated. If agents hold the credentials, the Gateway can be bypassed; if one Router process holds both, NFR-5 separation collapses to a single process.

- Where: p.7 §5 (FR-6): "No agent ever touches a data store directly."
- Where: p.4 §2.2 (NFR-5): "HIGHLY_RESTRICTED data shall be stored in a physically separate schema (memory_sensitive) with"
- Evidence EV-113 (doc, supports): "No agent ever touches a data store directly." [doc:DOC-sit_sample_v1#p7/s5]
- Evidence EV-114 (doc, supports): "HIGHLY_RESTRICTED data shall be stored in a physically separate schema (memory_sensitive) with" [doc:DOC-sit_sample_v1#p4/s2.2]
- Recommendation: In Section 11, state that only a dedicated sensitive-tier Router/consumer instance holds memory_sensitive credentials, using managed identity and Key Vault with rotation, and that agents hold no database credentials.
  - Issue: The credential custody model is ambiguous.
  - Rationale: NFR-5 isolation is only as strong as the process boundary that holds the credentials.
  - Expected benefit: Enforceable tier isolation. (objectives: NFR-5, FR-5)
  - Supporting evidence: EV-113, EV-114
  - Verification: Extend the NFR-5 isolation test to check that the standard Router identity cannot connect to memory_sensitive.

### FND-011 onboarding_progress typed WORKING yet expected to persist through orientation

- **ambiguity** · internal contradiction · severity **low** · confidence 0.65 (medium) · rank 40
- Disposition: **refinement now**

The orientation template types onboarding_progress as WORKING with expiry at the end of orientation. The Dispatcher, however, routes WORKING to an in-memory store with no persistence, and working memory is cleared at session close. The key would therefore be lost after each session, so the orientation agent could not track progress as intended.

- Where: p.23 §23 (FR-3): "onboarding_progress WORKING INTERNAL Expires at orientation end campus_questions"
- Where: p.16 §17: "WORKING -> In-memory store (no persistence, no Kafka)"
- Evidence EV-053 (doc, supports): "onboarding_progress WORKING INTERNAL Expires at orientation end" [doc:DOC-sit_sample_v1#p23/s23]
- Evidence EV-054 (doc, supports): "WORKING -> In-memory store (no persistence, no Kafka)" [doc:DOC-sit_sample_v1#p16/s17]
- Recommendation: Retype onboarding_progress as SEMANTIC or META in Section 23, or define slot-scoped WORKING persistence in Sections 10 and 17.
  - Issue: A memory-type mismatch for a key that needs to persist.
  - Rationale: FR-3 classification determines storage, so a wrong type silently drops the data.
  - Expected benefit: Orientation progress survives across sessions until the slot expires. (objectives: FR-3, FR-2)
  - Supporting evidence: EV-053, EV-054
  - Verification: FR-2 slot-type test: onboarding_progress written in session 1 is readable in session 2.

## Unresolved assumptions

### FND-024 The claim that Kafka retries failed writes automatically is unsupported, and the Event Hubs decision is still pending

- **unresolved assumption** · unsupported or incorrect claim · severity **high** · confidence 0.70 (medium) · rank 14
- Disposition: **refinement now** (also: needs investigation) · already acknowledged in the document

Section 18 says failed writes 'queue and retry automatically'. A broker only keeps messages; retries, dead-lettering and idempotent re-processing have to be built into the consumer, and none of this is designed. The agent gets an ACK before classification and validation, so a write that fails permanently (for example a strict-mode reject in the consumer) would be lost silently. Separately, 'Kafka (Azure Event Hubs)' is listed as a confirmed decision while the backlog still asks for Event Hubs to be confirmed. The document records the Event Hubs question; this review adds the unsupported retry claim and the missing route for reporting failures.

- Where: p.17 §18 (FR-9, NFR-3): "overwhelm the store; failed writes queue and retry automatically; multiple independent consumers (audit,"
- Where: p.26 §26: "Kafka vs Azure Event Hubs - confirm Azure Event Hubs as the managed Kafka-API alternative."
- Evidence EV-083 (doc, supports): "overwhelm the store; failed writes queue and retry automatically; multiple independent consumers (audit," [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-052 (doc, supports): "Kafka vs Azure Event Hubs - confirm Azure Event Hubs as the managed Kafka-API alternative." [doc:DOC-sit_sample_v1#p26/s26]
- Evidence EV-095 (inference, supports): "Validation happens in the background consumer after the immediate ACK, so without a designed retry/DLQ and failure-notification path, writes that are rejected or fail are lost without the agent knowing." [inference:EV-095] derived from EV-083
- Recommendation: In Section 18, specify consumer retry policy, idempotency keys, a dead-letter topic per tier, how rejected writes are reported (audit entry plus MMP dashboard), and replay. Close the Event Hubs backlog item, confirming the Kafka-API features the consumers need (consumer groups, retention), before marking the decision as confirmed.
  - Issue: The write path assumes retry behaviour that has not been designed, and the broker choice is unconfirmed.
  - Rationale: Writes that have been acknowledged but fail later are lost, which undermines FR-9 and FR-13 auditability.
  - Expected benefit: Writes are durable and failures are visible (FR-9, FR-11, FR-13). (objectives: FR-9, FR-11, FR-13)
  - Supporting evidence: EV-083, EV-052, EV-095
  - Verification: Fault-injection test: kill the consumer, fail the embedding call and send a strict-mode reject; confirm retry, dead-lettering and audit entries.
- Next step: Platform integration lead: Confirm Event Hubs Kafka-surface capabilities and draft the retry/DLQ design.

### FND-027 PDPA compliance is asserted while the PDPA sign-off is still pending

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.60 (medium) · rank 33
- Disposition: **governance decision** (also: needs investigation) · already acknowledged in the document

The design says its audit and retention approach meets PDPA, but the backlog shows PDPA alignment sign-off and the audit retention period are still open. The backlog records the sign-off gap. This review adds two specific choices that need DPO review before build: the agent backup is kept after a learner deletes their own memory, and audit logs (which hold learner_id and slot_path) are never modified and have no defined retention period. Either could conflict with retention-limitation or consent-withdrawal obligations; this has not been verified.

- Where: p.26 §26 (FR-13): "Memory Router Component 5 (Auditor) - log schema detail, retention period, PDPA alignment sign-off."
- Where: p.13 §13 (FR-15): "survives learner deletion of their own memory (enabling session resume)"
- Where: p.17 §17 (FR-13): "Audit logs are append-only. Never modified. Retained per PDPA requirements."
- Evidence EV-086 (doc, supports): "Memory Router Component 5 (Auditor) - log schema detail, retention period, PDPA alignment sign-off." [doc:DOC-sit_sample_v1#p26/s26]
- Evidence EV-087 (doc, supports): "survives learner deletion of their own memory (enabling session resume)" [doc:DOC-sit_sample_v1#p13/s13]
- Evidence EV-098 (inference, supports): "Data kept after learner deletion and audit records kept indefinitely are design choices whose PDPA position depends on the pending sign-off, not on anything stated in the document." [inference:EV-098] derived from EV-086, EV-087
- Recommendation: Before Build Phases 4/5, have the DPO rule on (a) whether the agent backup is kept after learner deletion, (b) the audit log retention period and pseudonymisation, and (c) consent records. Record the outcomes in Sections 17, 19 and 20 and change 'required for PDPA' wording to cite the sign-off.
  - Issue: Statements of compliance come before the regulatory review they depend on.
  - Rationale: FR-15 and P7 claim PDPA alignment, which has not been confirmed.
  - Expected benefit: Defensible PDPA position for FR-13, FR-15 and NFR-7. (objectives: FR-13, FR-15, NFR-7)
  - Supporting evidence: EV-086, EV-087, EV-098
  - Verification: A signed DPO review is attached, and the FR-15 test is extended to cover the agent backup.
- Next step: Data Protection Officer: Review backup retention after deletion and audit log retention, and issue the PDPA alignment sign-off.

### FND-028 The assumption that SIS can emit lifecycle events as webhooks is not verified

- **unresolved assumption** · missing or unverifiable requirement · severity **medium** · confidence 0.60 (medium) · rank 34
- Disposition: **needs investigation** · already acknowledged in the document

FR-12 requires slots to be provisioned and expired automatically from five SIS events, with no manual intervention, through an 'SIS webhook'. The document does not show that SIS can emit these events, who owns the integration, or what the event contract is. SIS failure handling is listed in the backlog. If SIS can only offer batch or polled exports, FR-12 and the provisioning flow in Section 21 would need redesign.

- Where: p.4 §2.1 (FR-12): "SIS events - registration, programme enrolment, module registration, module withdrawal, graduation -"
- Where: p.26 §26: "MMP in detail - template versioning conflict resolution, SIS integration failure handling."
- Evidence EV-088 (doc, supports): "SIS events - registration, programme enrolment, module registration, module withdrawal, graduation -" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-089 (doc, supports): "MMP in detail - template versioning conflict resolution, SIS integration failure handling." [doc:DOC-sit_sample_v1#p26/s26]
- Recommendation: Confirm with the SIS owner that these events are available and how they are delivered. Add an SIS event contract (payload, delivery guarantees, reconciliation job) to Section 21 and name the integration owner.
  - Issue: Automatic provisioning depends on an SIS capability that has not been confirmed.
  - Rationale: FR-12 cannot be met without it.
  - Expected benefit: FR-12 is achievable and has a defined contract. (objectives: FR-12)
  - Supporting evidence: EV-088, EV-089
  - Verification: Run the FR-12 simulation test against real SIS sandbox events.
- Next step: SIS system owner with the platform architect: Confirm SIS event emission capability and agree the event contract.

### FND-010 Confirmed write-path decision rests on the pending Event Hubs confirmation

- **unresolved assumption** · decision depends on pending item · severity **low** · confidence 0.70 (medium) · rank 39
- Disposition: **needs investigation** · already acknowledged in the document

Section 25 records Kafka via Azure Event Hubs as confirmed, while Section 26 lists confirming Event Hubs as pending. The Section 18 rationale assumes capabilities that need confirming on the chosen service: automatic retry, multiple independent consumers, and per-tier topic isolation. The decision itself is preserved, but its basis is open.

- Where: p.25 §25: "Write path Async via Kafka (Azure Event Hubs)"
- Where: p.26 §26: "Kafka vs Azure Event Hubs - confirm Azure Event Hubs as the managed Kafka-API alternative."
- Evidence EV-051 (doc, supports): "Write path Async via Kafka (Azure Event Hubs)" [doc:DOC-sit_sample_v1#p25/s25]
- Evidence EV-052 (doc, supports): "Kafka vs Azure Event Hubs - confirm Azure Event Hubs as the managed Kafka-API alternative." [doc:DOC-sit_sample_v1#p26/s26]
- Recommendation: In Section 25, mark the broker choice 'confirmed, pending validation', and list the capabilities the backlog item must confirm (consumer groups, retry/dead-letter, per-topic isolation and access control, throughput at term-start peak).
  - Issue: A decision marked confirmed depends on an open backlog item.
  - Rationale: The FR-9 and NFR-3 guarantees depend on the broker's actual behaviour.
  - Expected benefit: FR-9 and NFR-3 rest on verified broker capabilities. (objectives: FR-9, NFR-3)
  - Supporting evidence: EV-051, EV-052
  - Verification: Close backlog item 9 with a short spike that records each capability.
- Next step: Platform architect: Run an Event Hubs (Kafka API) spike against the Section 18 capability list and close backlog item 9.

## Validation needs

### FND-021 Filtered HNSW query claim ('500-800 vector search space') is unverified

- **validation need** · unsupported or incorrect claim · severity **high** · confidence 0.65 (medium) · rank 17
- Disposition: **needs prototyping** (also: refinement now)

Section 12 says that because every query filters on learner_id + slot_path, each search only covers 500-800 vectors. NFR-2 (5-15 ms) and the HNSW index in Section 11 both depend on that. The document does not say how the global HNSW index and the B-tree filter work together. If the planner traverses the HNSW graph first and filters afterwards, a filter that matches roughly 0.006% of rows may return few or no in-slot neighbours, so recall drops. If the planner uses the B-tree and scans those rows exactly, results are correct but the ~80 GB HNSW index adds no value. Also, about 600 vectors per learner across all slots means a single slot_path holds far fewer than 500-800, so the stated figure doesn't match the document's own breakdown.

- Where: p.12 §12 (NFR-2): "effective search space per query is 500-800 vectors, not 9.5 million."
- Where: p.4 §2.2 (NFR-2): "Filtered vector similarity queries (scoped by learner_id and slot_path) shall return within 5-15 ms under"
- Where: p.11 §11: "CREATE INDEX ON memory_vectors USING hnsw (embedding vector_cosine_ops)"
- Evidence EV-047 (doc, supports): "effective search space per query is 500-800 vectors, not 9.5 million." [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-048 (doc, supports): "CREATE INDEX ON memory_vectors USING hnsw (embedding vector_cosine_ops)" [doc:DOC-sit_sample_v1#p11/s11]
- Evidence EV-092 (inference, supports): "A single global HNSW index has no knowledge of learner_id/slot_path, so the 500-800 figure only holds if the planner chooses the B-tree path; with the HNSW path, filtering happens after the graph search and recall at ~0.006% selectivity has to be measured, not assumed." [inference:EV-092] derived from EV-047, EV-048
- Recommendation: In Section 12, state the intended access path: either exact search over the B-tree-filtered rows, which may make the HNSW index unnecessary, or HNSW with a defined filtered/iterative-scan strategy, or partitioning. Then benchmark p50/p95 latency and recall@k on the synthetic 9.5M dataset (NFR-2 test) and record the results.
  - Issue: NFR-2 and the HNSW index choice rest on an unstated assumption about how filtered pgvector queries are executed.
  - Rationale: Whether the latency target and recall are both met depends on the query plan, and the document does not specify it.
  - Expected benefit: NFR-2 is shown to be achievable with correct recall, and index size and cost (NFR-1, NFR-10) are justified. (objectives: NFR-2, NFR-1, NFR-10)
  - Supporting evidence: EV-047, EV-048, EV-092
  - Verification: Extend the NFR-2 benchmark to record EXPLAIN plans and recall@k against exact search for random learner/slot filters.
- Next step: Platform data engineer: Build a 9.5M-vector prototype on the target SKU and measure query plans, latency and recall for filtered queries.

### FND-023 The 48-hour Entra ID token lifetime and REVOKED-state detection are unverified

- **validation need** · unsupported or incorrect claim · severity **high** · confidence 0.60 (medium) · rank 19
- Disposition: **needs investigation** (also: refinement now)

The document assumes Entra ID will issue learner tokens valid for 48 hours and that the Gateway can tell when a token has been REVOKED. It has not been checked whether Entra ID allows access tokens that long. A self-contained JWT also does not reveal that it has been revoked unless there is introspection or an event mechanism, and none is designed. If either assumption fails, NFR-6, the degraded-mode behaviour and the NFR-6 test cannot work as written, and revoked learners could keep access.

- Where: p.8 §6 (NFR-6): "Authentication is OAuth 2.0 via Entra ID. Tokens are valid for 48 hours."
- Where: p.4 §2.2 (NFR-6): "Auth tokens shall be valid for 48 hours, with defined degraded-mode behaviour for EXPIRED and REVOKED"
- Evidence EV-081 (doc, supports): "Authentication is OAuth 2.0 via Entra ID. Tokens are valid for 48 hours." [doc:DOC-sit_sample_v1#p8/s6]
- Evidence EV-082 (doc, supports): "REVOKED -> inform learner (token revoked, contact support)." [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-094 (inference, supports): "The document does not say which token (access, refresh or a platform session token) carries the 48h window, or how revocation is learned, so both the issuing-platform limit and the revocation mechanism are unverified dependencies." [inference:EV-094] derived from EV-081, EV-082
- Recommendation: Confirm what Entra ID supports for token lifetime and revocation signalling. In Section 6/15, state which token holds the 48h window (for example, a platform-issued session token backed by Entra refresh) and the revocation mechanism (introspection, continuous access evaluation or event feed), including the maximum detection delay.
  - Issue: The token lifetime and revocation detection depend on identity-platform capabilities that have not been confirmed.
  - Rationale: NFR-6 and the Gateway's Check 3 cannot be built until it is known what Entra ID supports.
  - Expected benefit: NFR-6 can be implemented and revocation is enforced promptly (FR-4 Check 3). (objectives: NFR-6, FR-4)
  - Supporting evidence: EV-081, EV-082, EV-094
  - Verification: Run the NFR-6 test against a real Entra tenant, including revoking a session mid-window and measuring how long the Gateway takes to detect it.
- Next step: Identity/security architect: Check Entra ID token lifetime policy limits and revocation options, and update Sections 6 and 15.

### FND-018 FR-8 test expects DENY from every dimension, including Redaction and Retention

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.70 (medium) · rank 25
- Disposition: **refinement now** · already acknowledged in the document

The FR-8 test requires each of the seven dimensions to produce a DENY. But Redaction masks content, Retention sets expiry, and Section 28 itself names a REDACT outcome. The test therefore cannot check correct behaviour for those dimensions. The underlying cause, the missing algorithm for combining dimensions, is already acknowledged in Section 28. This review adds that the acceptance criterion itself has to change, and should be derived from the decision table.

- Where: p.27 §27.1 (FR-8): "A test matrix exercises all seven dimensions independently (one violating"
- Where: p.29 §28 (FR-8): "the decision algorithm - how the seven dimensions combine into a"
- Evidence EV-069 (doc, supports): "condition per dimension) and confirms each produces a DENY attributable to" [doc:DOC-sit_sample_v1#p27/s27.1]
- Evidence EV-070 (doc, supports): "Redaction Should part of the memory be masked before serving to this agent?" [doc:DOC-sit_sample_v1#p15/s16]
- Recommendation: Rewrite the FR-8 criterion in Section 27.1 to assert the expected outcome per dimension (DENY, REDACT, EXPIRE/FILTER, PURGE) as set out in the Phase 3 decision table, including precedence cases where dimensions conflict.
  - Issue: The FR-8 criterion assumes the same outcome for every dimension.
  - Rationale: Redaction and retention have outcomes other than deny, so the test would either fail correct behaviour or force incorrect behaviour.
  - Expected benefit: FR-8 becomes verifiable against the planned Phase 3 decision table. (objectives: FR-8)
  - Supporting evidence: EV-069, EV-070
  - Verification: The test matrix rows map one-to-one to the decision table entries.

### FND-008 Filtered-HNSW search-space claim and vector sizing need a benchmark

- **validation need** · unsupported or incorrect claim · severity **medium** · confidence 0.60 (medium) · rank 29
- Disposition: **needs prototyping** (also: refinement now)

The design claims the filter shrinks each search to 500-800 vectors. However, the DDL builds one global HNSW index plus a separate B-tree, and whether the planner pre-filters, post-filters (with possible loss of recall) or bypasses HNSW is not stated, so NFR-2 latency and recall are unproven. Separately, the per-learner breakdown sums to about 340 vectors rather than the ~600 used for 9.5M. The sizing behind the confirmed SKU and NFR-10 therefore needs reconciling. This review keeps the pgvector decision and asks for evidence within it.

- Where: p.12 §12 (NFR-2): "effective search space per query is 500-800 vectors, not 9.5 million."
- Where: p.11 §11: "CREATE INDEX ON memory_vectors USING hnsw (embedding vector_cosine_ops)"
- Where: p.4 §2.2 (NFR-2): "Filtered vector similarity queries (scoped by learner_id and slot_path) shall return within 5-15 ms under"
- Evidence EV-047 (doc, supports): "effective search space per query is 500-800 vectors, not 9.5 million." [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-048 (doc, supports): "CREATE INDEX ON memory_vectors USING hnsw (embedding vector_cosine_ops)" [doc:DOC-sit_sample_v1#p11/s11]
- Evidence EV-060 (inference, supports): "The listed per-learner components (10+15+120+60+30+30+20+30+5+20) sum to 340, not ~600, so the 9M active-learner figure is not derived from the stated breakdown; and a single global HNSW index does not by itself restrict traversal to the filtered rows." [inference:EV-060] derived from EV-047, EV-048
- Recommendation: In Section 12, reconcile the per-learner breakdown with the ~600 figure. Add a recall target to NFR-2, and state the intended query plan (exact search over the B-tree-filtered rows, or HNSW with iterative or filtered scan). Prototype both plans on the synthetic 9.5M dataset.
  - Issue: Latency, recall and sizing claims rest on an unstated query-plan assumption and on figures that do not reconcile.
  - Rationale: NFR-1, NFR-2 and NFR-10 and the SKU decision all depend on these figures.
  - Expected benefit: Evidence that NFR-2 is met with acceptable recall, and a SKU sized correctly for NFR-10. (objectives: NFR-1, NFR-2, NFR-10)
  - Supporting evidence: EV-047, EV-048, EV-060
  - Verification: NFR-2 benchmark that reports p50/p95 and recall@k against brute force on the full synthetic dataset.
- Next step: Platform architect: Run a pgvector filtered-query prototype on 9.5M synthetic vectors and record the query plan, latency and recall.

### FND-025 The SGD 800-1,200/month cost estimate has no stated basis and an unclear scope

- **validation need** · unsupported or incorrect claim · severity **medium** · confidence 0.60 (medium) · rank 32
- Disposition: **needs investigation** (also: refinement now)

NFR-10 and Section 12 give SGD 800-1,200/month for a 16-vCore, 128 GB Azure PostgreSQL in Singapore with no breakdown. They do not say whether storage (more than 140 GB of index and data), IOPS, backups, high-availability standby or the separate sensitive-tier deployment are included. The NFR-10 acceptance test also brings in 'measured embedding volume', which goes beyond 'vector-store infrastructure', so the target being tested is unclear. Current Azure pricing has not been checked in this review.

- Where: p.5 §2.2 (NFR-10): "Vector-store infrastructure cost shall remain within the SGD 800-1,200/month estimate at 15,000-learner"
- Where: p.28 §27.2 (NFR-10): "Projected monthly cost at 15,000-learner scale, computed from the actual"
- Evidence EV-084 (doc, supports): "Vector-store infrastructure cost shall remain within the SGD 800-1,200/month estimate at 15,000-learner" [doc:DOC-sit_sample_v1#p5/s2.2]
- Evidence EV-096 (inference, supports): "Without a breakdown, and with the requirement and its acceptance test covering different scopes, NFR-10 cannot be confirmed and may not include HA, storage or the separate sensitive tier." [inference:EV-096] derived from EV-084
- Recommendation: Add a cost table to Section 12: compute, storage and IOPS, backup, HA, the sensitive tier, and optionally Event Hubs, Redis and embeddings, priced from the current Azure Singapore price list. Align the NFR-10 wording with the scope of its acceptance criterion.
  - Issue: The cost figure is not derived from anything and its scope is ambiguous.
  - Rationale: Budget approval and the SKU choice depend on it.
  - Expected benefit: An NFR-10 target that can be verified and reflects the real cost. (objectives: NFR-10)
  - Supporting evidence: EV-084, EV-096
  - Verification: Compare against the Azure pricing calculator and the first month of actual billing.
- Next step: Cloud FinOps / platform lead: Price the confirmed SKU, plus HA and storage, in the Singapore region and update NFR-10.

### FND-038 Filtered HNSW search-space claim and RAM fit at 9.5M vectors are unproven

- **validation need** · scalability or failure mode · severity **medium** · confidence 0.60 (medium) · rank 35
- Disposition: **needs prototyping** (also: needs testing)

The design assumes that filtering by learner_id and slot_path shrinks the search to 500-800 vectors, but the only vector index is a single global HNSW index alongside a separate B-tree. Whether the planner pre-filters or traverses the global graph and post-filters (with possible recall loss on small per-learner sets) is unverified. Raw vectors (~57 GB) plus the HNSW index (~80 GB), plus the duplicated sensitive schema, may exceed 128 GB RAM, which affects NFR-1/NFR-2.

- Where: p.12 §12 (NFR-2): "Queries are always filtered by learner_id + slot_path - the effective search space per query is 500-800 vectors, not 9.5 million."
- Where: p.11 §11 (NFR-1): "CREATE INDEX ON memory_vectors USING hnsw (embedding vector_cosine_ops)"
- Evidence EV-110 (doc, supports): "Queries are always filtered by learner_id + slot_path - the effective search space per query is 500-800 vectors, not 9.5 million." [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-048 (doc, supports): "CREATE INDEX ON memory_vectors USING hnsw (embedding vector_cosine_ops)" [doc:DOC-sit_sample_v1#p11/s11]
- Evidence EV-121 (inference, supports): "Section 12 lists ~57 GB raw vectors and ~80 GB HNSW index against 128 GB RAM, so the working set is close to or above memory before heap, other tables and the sensitive schema." [inference:EV-121] derived from EV-110, EV-048
- Recommendation: Prototype on 9.5M synthetic vectors: measure p50/p95 latency and recall@k for filtered queries. Compare the global HNSW index against exact (non-ANN) search using the B-tree on learner_id, which may suffice for 500-800 rows. Record the RAM working set. Update Section 12 with the results.
  - Issue: Filtered-ANN behaviour and memory fit at full scale are assumed, not measured.
  - Rationale: NFR-1/NFR-2 and the confirmed SKU depend on these assumptions.
  - Expected benefit: Confidence that the SKU and latency targets hold, or an early pivot (partitioning by learner, exact search on small per-learner sets). (objectives: NFR-1, NFR-2, NFR-10)
  - Supporting evidence: EV-110, EV-048, EV-121
  - Verification: The NFR-2 benchmark adds a recall@k ≥ agreed threshold alongside the latency limits.
- Next step: Platform data engineer: Run a pgvector filtered-query benchmark at full synthetic scale before Build Phase 5.

### FND-029 BM25 fallback assumes a capability the schema doesn't provide

- **validation need** · unsupported or incorrect claim · severity **medium** · confidence 0.55 (medium) · rank 37
- Disposition: **needs investigation** (also: refinement now)

When embedding is unavailable, the Embedder says it falls back to BM25 keyword search. The Section 11 DDL has no full-text column or index. The document does not check whether the chosen Azure PostgreSQL service provides BM25 ranking natively or through a supported extension. Without that, the degraded retrieval path for unembedded records may not exist.

- Where: p.16 §17 (FR-10): "Fall back to BM25 keyword search for retrieval"
- Evidence EV-090 (doc, supports): "Fall back to BM25 keyword search for retrieval" [doc:DOC-sit_sample_v1#p16/s17]
- Evidence EV-099 (inference, supports): "No tsvector column or text index appears in the Section 11 DDL, so the fallback has no schema support as written." [inference:EV-099] derived from EV-090
- Recommendation: Confirm which keyword-ranking options Azure Database for PostgreSQL supports. Add the matching column and index to Section 11 and name the ranking method accurately in Section 17.
  - Issue: The fallback retrieval method is not backed by the schema or a confirmed platform capability.
  - Rationale: Records written while embedding is down would not be retrievable.
  - Expected benefit: FR-10 reads keep working while embedding is degraded. (objectives: FR-10)
  - Supporting evidence: EV-090, EV-099
  - Verification: Test: with the embedding service disabled, write and then read back records through keyword search.
- Next step: Platform data engineer: Check the supported full-text and BM25 options on the target Azure PostgreSQL service.

## Recommended refinements

| Finding | Change | Expected benefit |
|---|---|---|
| FND-031 | In Sections 13, 14 and 20, specify that: the backup is written through the Router (or a governed local store) with the same sensitivity tiering and audit; FR-15 deletion propagates to all agent backups; HIGHLY_RESTRICTED content is never kept in the backup, or is kept only in an encrypted sensitive-tier store; and the backup has a bounded TTL. Add an FR-15 acceptance case that checks the backups after deletion. | Learner deletion and audit become complete, and the counselling hard wall extends to backup copies. |
| FND-001 | In Sections 13, 14 and 2.1 (FR-16), state where agent backups are stored (a schema per tier, with the sensitive tier for the counsellor agent). Route backup writes through the Gateway and Auditor with the same sensitivity ceiling, or limit backups to INTERNAL keys. Add FR-16 acceptance cases for audit and tier placement. | FR-5, NFR-5 and P7 also hold for degraded-mode data, so the counselling hard wall cannot be bypassed through an agent's own backup. |
| FND-002 | Decide whether a learner deletion request cascades to agent backups, with the Deletion dimension in Section 16 fanning out to them. If backups are kept, list exactly which non-content state survives (for example a session cursor) and why. Update Sections 13 and 20 and the FR-15 acceptance criterion to cover backups. | FR-15 and the Deletion policy dimension (FR-8) become effective across all copies. |
| FND-013 | In Sections 5, 16 and 21, state that runtime policy evaluation runs in the Gateway or Router data plane, reading policy data replicated from the MMP, and that the MMP only authors policy. In Section 15 Check 4, define the behaviour when the MMP is unavailable: either deny with reason 'slot not provisioned' or provision through a data-plane provisioner. Extend the NFR-4 test to cover a first write to an unprovisioned auto-provisionable slot. | NFR-4 becomes achievable and testable, and agent availability no longer depends on the admin plane. |
| FND-014 | In Sections 19 and 21, explicitly exclude memory_sensitive from Super Admin and Institution Admin scope. The MMP service identity should hold no memory_sensitive credentials, and Admin API endpoints should reject wellbeing/counselling/ paths. Extend the FR-5 test to call the Admin API GET and DELETE and /policy/check as a super admin against counselling paths, and to confirm that MMP credentials fail against memory_sensitive. | FR-5 and P4 become enforceable and verifiable. |
| FND-032 | In Sections 6, 15 and 25, change REVOKED behaviour to: end the session, load no per-learner backup, and serve only non-personal agent-global content. Add this case to the NFR-6 token lifecycle test. | Revocation becomes an effective access-termination control, in line with P2 and NFR-6. |
| FND-034 | In Sections 5 and 21, separate the runtime data plane (audit sink, policy evaluation against replicated config, slot registry) from the MMP admin service. Define audit as durable and fail-closed (for example, an audit Kafka topic before ACK). Have Check 4 deny or queue provisioning when the MMP is unavailable. | Availability during MMP outages without losing audit completeness. |
| FND-035 | In Section 18: move the synchronous schema/key validation to the Gateway before the ACK (cheap and template-local); reorder the consumer to classify → validate → embed; add a dead-letter topic with a retry limit, idempotency keys on memory_id/event_id, per-learner partitioning for ordering, and a status/notification channel (MMP dashboard) for rejected writes. | No silent data loss, no duplicate memories under retry, and lower embedding cost. |
| FND-003 | In Sections 2.1 (FR-9), 17 and 18, move template validation and sensitivity-ceiling checks into the synchronous Gateway step before topic selection. Reorder the consumer to classify → validate → embed → route → audit. Define what happens to a rejected or reclassified message (dead-letter topic, agent notification) and which embedding deployment each topic uses. | Keeps HIGHLY_RESTRICTED isolated in transit (NFR-5, P4), makes FR-11 rejections visible to agents, and avoids embedding cost for writes that will be rejected. |
| FND-004 | In the Section 19 roles table and the Section 21 users table, state explicitly that the Super Admin and MMP credentials have no access to memory_sensitive, or define a separately governed break-glass path outside the MMP. In Section 23, state which roles write to the counselling keys. | FR-5 and P4 become unambiguous to implement and test. |
| FND-015 | In Section 18, add the following: classify consumer failures as permanent (validation) or transient (embedding, DB); send permanent failures to a dead-letter topic per tier with an audit DENIED entry and a dashboard warning; set a retry limit and backoff for transient failures; and either define a write-status callback or query for agents, or have the Gateway pre-validate template keys synchronously before enqueueing. Update the FR-11 acceptance test to state where the rejection is observed. | FR-11 rejections can be observed and acted on, and the consumer cannot get stuck on poison messages (FR-9). |
| FND-016 | In Sections 13 and 20, specify where per-learner agent backups are stored (schema and tier), require the counselling agent's backup to sit in memory_sensitive, and decide whether learner deletion cascades to backups. The DPO should decide whether the 'session resume' benefit justifies keeping the data. Extend the FR-15 and NFR-5 tests to include agent backups. | FR-15 deletion becomes complete and checkable, and the NFR-5 isolation also covers backups. |
| FND-022 | Redo Section 12: reconcile the per-learner breakdown with the 600 figure, separate index size from heap size, give a total working-set estimate versus RAM, and replace the 30-40M ceiling with a derived figure or remove it. Consider options such as halfvec, reduced dimensions or partitioning, and re-check the SKU. | A sizing basis that supports NFR-1/NFR-2 and a cost estimate (NFR-10) that can be defended. |
| FND-024 | In Section 18, specify consumer retry policy, idempotency keys, a dead-letter topic per tier, how rejected writes are reported (audit entry plus MMP dashboard), and replay. Close the Event Hubs backlog item, confirming the Kafka-API features the consumers need (consumer groups, retention), before marking the decision as confirmed. | Writes are durable and failures are visible (FR-9, FR-11, FR-13). |
| FND-033 | In Section 18: invalidate cached packs on policy, permission, template or deletion events, or cap the TTL to a short bound; exclude HIGHLY_RESTRICTED content from the shared cache or use a separate cache instance with its own credentials; require encryption in transit and at rest for Redis. Update the Section 16 wording to match. | Policy changes, revocations and deletions take effect within a bounded time, and HIGHLY_RESTRICTED data stays isolated. |
| FND-037 | In Section 19, restate Super Admin scope as 'everything except memory_sensitive content'. In Section 21, specify Admin API auth (Entra ID app roles, MFA, per-endpoint role mapping), ensure the MMP holds no memory_sensitive credentials, and add a break-glass procedure with dual approval if one is needed. Add a test that super-admin calls to counselling slots are denied. | FR-5 holds against insiders, and admin access is least-privilege. |
| FND-021 | In Section 12, state the intended access path: either exact search over the B-tree-filtered rows, which may make the HNSW index unnecessary, or HNSW with a defined filtered/iterative-scan strategy, or partitioning. Then benchmark p50/p95 latency and recall@k on the synthetic 9.5M dataset (NFR-2 test) and record the results. | NFR-2 is shown to be achievable with correct recall, and index size and cost (NFR-1, NFR-10) are justified. |
| FND-036 | In Sections 8, 19 and 23, define a sensitive-tier escalation variant (stored in memory_sensitive and readable only by human counsellors or the clinical system) or a minimal-content RESTRICTED escalation template (flag plus referral only, with the content field forbidden). Add it to the FR-7 test. | Welfare escalations reach humans without breaching the hard wall. |
| FND-023 | Confirm what Entra ID supports for token lifetime and revocation signalling. In Section 6/15, state which token holds the 48h window (for example, a platform-issued session token backed by Entra refresh) and the revocation mechanism (introspection, continuous access evaluation or event feed), including the maximum detection delay. | NFR-6 can be implemented and revocation is enforced promptly (FR-4 Check 3). |
| FND-006 | In Section 16, add a decision table with the outcome set (ALLOW/DENY/REDACT/EXPIRE), the precedence order, and the point in the read and write paths where each dimension is evaluated. Downgrade the Gateway and Validator rows in Section 28 to 'Mostly ready' until then, and revise the FR-8 criteria in Section 27 so each dimension asserts its own outcome type. | FR-8 can be implemented, and the FR-8 test can verify it. |
| FND-026 | Add embedded BOOLEAN, plus retention/expires_at/pii to all three tables, template_version, consent fields and an audit table DDL to Section 11. Downgrade the Section 28 database schema row to 'Mostly ready' until this is done. | A schema that supports NFR-7 and the embedder fallback when first built. |
| FND-017 | In Section 11, add key, pii, retention and expires_at to memory_events, and pii, retention and expires_at to memory_documents. Add embedded BOOLEAN to memory_vectors, and add template_version and writer agent_id to all three tables. In Section 28, change the DDL rating to 'Mostly ready' until this is done. | NFR-7 retention and PII enforcement, and the Embedder fallback, become implementable. |
| FND-039 | Add an 'embedded BOOLEAN' column and a tsvector column with a GIN index to memory_vectors in Section 11 (both schemas). State the ranking used in fallback mode. Correct the Section 28 readiness note. | Reads keep working during embedding outages, and the re-embed backlog can be queried. |
| FND-005 | In Sections 5, 15 and 21, separate the runtime components (policy evaluation, audit sink, slot existence) from MMP admin functions. Make Check 4 either deny or queue provisioning when the MMP is unavailable, and state where the runtime PolicyEngine and the audit sink run. | Agent read and write availability is independent of the MMP admin service (NFR-4). |
| FND-018 | Rewrite the FR-8 criterion in Section 27.1 to assert the expected outcome per dimension (DENY, REDACT, EXPIRE/FILTER, PURGE) as set out in the Phase 3 decision table, including precedence cases where dimensions conflict. | FR-8 becomes verifiable against the planned Phase 3 decision table. |
| FND-040 | Add an Operations section with: RPO/RTO targets; PostgreSQL zone-redundant HA and PITR retention; Event Hubs/Redis failover behaviour; an alert list (consumer lag, DLQ, audit write failures, Gateway deny rate); and on-call ownership. Add an owner and target phase to each Section 26 item. | Defined recovery targets and named owners for the PDPA-critical open items. |
| FND-007 | In Section 18, specify the cache key (learner_id, agent_id, purpose and policy version) and invalidation triggers (policy publish, permission change, deletion, write to a slot in the pack). Alternatively, state a bounded staleness accepted by the DPO. | Policy changes, permission revocations and FR-15 deletions take effect within a bounded time. |
| FND-019 | In Sections 15 and 2.1, state that Check 3 denies namespace access while the agent may serve from its backup. Add an explicit governance decision on whether a REVOKED state also blocks backup use. Define how REFRESHING is handled. Align the FR-4 and NFR-6 tests with these rules. | FR-4, NFR-6 and FR-16 are consistent and testable. |
| FND-008 | In Section 12, reconcile the per-learner breakdown with the ~600 figure. Add a recall target to NFR-2, and state the intended query plan (exact search over the B-tree-filtered rows, or HNSW with iterative or filtered scan). Prototype both plans on the synthetic 9.5M dataset. | Evidence that NFR-2 is met with acceptable recall, and a SKU sized correctly for NFR-10. |
| FND-009 | In Sections 6 and 15, restrict REVOKED to non-personal service (agent global only), and define which backup keys may be served while EXPIRED. Amend FR-4 to name the degraded-mode exception explicitly. | FR-4 and P2 hold, and degraded-mode behaviour (NFR-6) is bounded. |
| FND-020 | In Section 18, key the cache by (agent_id, learner_id, session_id, policy_version). Invalidate on policy publish, deletion, and writes to cached slots. Add an FR-10 test case where a policy change mid-session causes a cache MISS. | FR-8 immediacy and FR-15 deletion apply to served content, not only to stored content. |
| FND-025 | Add a cost table to Section 12: compute, storage and IOPS, backup, HA, the sensitive tier, and optionally Event Hubs, Redis and embeddings, priced from the current Azure Singapore price list. Align the NFR-10 wording with the scope of its acceptance criterion. | An NFR-10 target that can be verified and reflects the real cost. |
| FND-027 | Before Build Phases 4/5, have the DPO rule on (a) whether the agent backup is kept after learner deletion, (b) the audit log retention period and pseudonymisation, and (c) consent records. Record the outcomes in Sections 17, 19 and 20 and change 'required for PDPA' wording to cite the sign-off. | Defensible PDPA position for FR-13, FR-15 and NFR-7. |
| FND-028 | Confirm with the SIS owner that these events are available and how they are delivered. Add an SIS event contract (payload, delivery guarantees, reconciliation job) to Section 21 and name the integration owner. | FR-12 is achievable and has a defined contract. |
| FND-038 | Prototype on 9.5M synthetic vectors: measure p50/p95 latency and recall@k for filtered queries. Compare the global HNSW index against exact (non-ANN) search using the B-tree on learner_id, which may suffice for 500-800 rows. Record the RAM working set. Update Section 12 with the results. | Confidence that the SKU and latency targets hold, or an early pivot (partitioning by learner, exact search on small per-learner sets). |
| FND-041 | In Sections 13 and 22, specify: the source sensitivity allowed in aggregates (INTERNAL only, by default); a minimum group size (k threshold); suppression rules; and a DPO approval step for each aggregate type. | Aggregate sharing does not re-identify learners. |
| FND-029 | Confirm which keyword-ranking options Azure Database for PostgreSQL supports. Add the matching column and index to Section 11 and name the ranking method accurately in Section 17. | FR-10 reads keep working while embedding is degraded. |
| FND-042 | In Section 11, state that only a dedicated sensitive-tier Router/consumer instance holds memory_sensitive credentials, using managed identity and Key Vault with rotation, and that agents hold no database credentials. | Enforceable tier isolation. |
| FND-010 | In Section 25, mark the broker choice 'confirmed, pending validation', and list the capabilities the backlog item must confirm (consumer groups, retry/dead-letter, per-topic isolation and access control, throughput at term-start peak). | FR-9 and NFR-3 rest on verified broker capabilities. |
| FND-011 | Retype onboarding_progress as SEMANTIC or META in Section 23, or define slot-scoped WORKING persistence in Sections 10 and 17. | Orientation progress survives across sessions until the slot expires. |
| FND-043 | Extend NFR-10 or add a requirement with per-component budgets (Event Hubs, Redis, embeddings, audit storage) and a projection of audit log volume. | Cost overruns are detectable. |

## Areas where no change is needed

- FND-012 Clear, traceable statement of intent with explicit precedence and readiness: The objectives, principles, decisions and acceptance criteria are explicit and traceable, which is what a build-ready design needs to be reviewed and tested against.
- FND-030 Gaps are explicitly tracked in the Pending Backlog and readiness assessment: Tracking open items explicitly, each linked to a build phase, is the right control for the design's aim of being build-ready; keep it and extend it with the items raised above.
- FND-044 Ordered pre-retrieval Gateway checks with schema and credential isolation and matching tests: These controls meet FR-4, FR-5 and NFR-5 as stated, and they are verifiable through the Section 27 tests.
- SA-001 (sections 11, 2.2): A physically separate memory_sensitive schema with its own credentials, separate Kafka topics and a separate embedding deployment directly serves NFR-5 and FR-5, and is testable through the NFR-5 credential test. The remaining gaps are in the paths that bypass it (FND-001, FND-003), not in the tier design itself. (see FND-001, FND-003)
  - p.4 §2.2: "HIGHLY_RESTRICTED data shall be stored in a physically separate schema (memory_sensitive) with"
- SA-002 (sections 15): Six ordered pre-retrieval checks, each with a logged denial reason, implement P3 and FR-4 in a form that can be coded as middleware. Each check maps to one acceptance test case. (see FND-009)
  - p.15 §15: "Access control is pre-retrieval. The namespace check gates the query itself - not the returned results."
- SA-003 (sections 19, 2.1): The escalation semantics (any agent writes, only the target domain and humans read, no read-back by the triggering agent) are stated consistently in FR-7, Section 19 and the decision register, and the FR-7 lifecycle test verifies them.
  - p.19 §19: "Feedback loop blocked: the agent that triggered the escalation cannot read it back."
- SA-004 (sections 1, 25): Keeping the memory platform separate from the Azure AI Search RAG project, with no shared infrastructure, removes a dependency on another system's capacity and change cycle. It also keeps the PostgreSQL+pgvector choice self-contained.
  - p.3 §1: "SIT-AI-Factory-RAG (the Azure AI Search RAG project) - a separate system, in a separate resource group, with"
- SA-005 (sections 26, 28): Open items are recorded and given a phase, so most assumptions can be traced to a closure point. (see FND-030)
  - p.26 §26: "Items confirmed as in-scope but not yet fully designed:"
- SA-006 (sections 15, 27.2): The pre-retrieval Gateway chain and the schema/credential separation directly implement P3/P4, FR-4, FR-5 and NFR-5, and they have concrete negative tests. (see FND-044, FND-042)
  - p.15 §15: "HIGHLY_RESTRICTED slots: hard block for all agents not in an"
- SA-007 (sections 17): The Auditor log shape (agent, learner, slot, outcome, denial reason, source) and its coverage of cache hits and Kafka enqueues support FR-13 and P7. The remaining gaps are availability and retention, not content. (see FND-034, FND-040)
  - p.17 §17: "Audit logs are append-only. Never modified. Retained per PDPA requirements."
- SA-008 (sections 18): Separate Kafka topics per sensitivity tier extend NFR-5 isolation into transit, and buffering absorbs term-start write spikes, in line with NFR-3. (see FND-035)
  - p.17 §18: "separate topics per sensitivity tier keep HIGHLY_RESTRICTED writes physically isolated in transit."

## Unresolved issues and next steps

- FND-031 (governance decision): Agent per-learner backup memory sits outside the governed path (deletion, audit, sensitivity tiering) (FND-031) Next step (Data Protection Officer with Platform Architect): Decide whether agent backups may survive learner deletion and whether they may hold HIGHLY_RESTRICTED data, then amend Sections 13 and 20.
- FND-002 (governance decision): Agent backup surviving self-deletion defeats FR-15 learner deletion (FND-002) Next step (Data governance officer / DPO): Decide the cascade scope of learner deletion to agent backups and record it in Section 20.
- FND-032 (governance decision): REVOKED token still serves learner data from the agent backup (FND-032) Next step (Security lead / DPO): Confirm the intended semantics of revocation and amend the confirmed decision on auth token behaviour.
- FND-004 (governance decision): Super Admin 'Everything' and emergency override conflict with the counselling hard wall (FND-004) Next step (Data governance officer / DPO): Confirm whether any break-glass access to counselling records exists and record it in Sections 19 and 21.
- FND-021 (needs prototyping): Filtered HNSW query claim ('500-800 vector search space') is unverified (FND-021) Next step (Platform data engineer): Build a 9.5M-vector prototype on the target SKU and measure query plans, latency and recall for filtered queries.
- FND-036 (governance decision): Counselling escalations either blocked by the sensitivity ceiling or leak HIGHLY_RESTRICTED content into the standard tier (FND-036) Next step (Head of Counselling Services with DPO): Decide the content and storage tier allowed for counselling-originated escalations.
- FND-023 (needs investigation): The 48-hour Entra ID token lifetime and REVOKED-state detection are unverified (FND-023) Next step (Identity/security architect): Check Entra ID token lifetime policy limits and revocation options, and update Sections 6 and 15.
- FND-008 (needs prototyping): Filtered-HNSW search-space claim and vector sizing need a benchmark (FND-008) Next step (Platform architect): Run a pgvector filtered-query prototype on 9.5M synthetic vectors and record the query plan, latency and recall.
- FND-009 (governance decision): Degraded mode serves learner memory on EXPIRED/REVOKED tokens, contrary to FR-4 deny-on-failure (FND-009) Next step (Data governance officer / DPO): Decide what learner data, if any, may be served under EXPIRED and REVOKED tokens.
- FND-025 (needs investigation): The SGD 800-1,200/month cost estimate has no stated basis and an unclear scope (FND-025) Next step (Cloud FinOps / platform lead): Price the confirmed SKU, plus HA and storage, in the Singapore region and update NFR-10.
- FND-027 (governance decision): PDPA compliance is asserted while the PDPA sign-off is still pending (FND-027) Next step (Data Protection Officer): Review backup retention after deletion and audit log retention, and issue the PDPA alignment sign-off.
- FND-028 (needs investigation): The assumption that SIS can emit lifecycle events as webhooks is not verified (FND-028) Next step (SIS system owner with the platform architect): Confirm SIS event emission capability and agree the event contract.
- FND-038 (needs prototyping): Filtered HNSW search-space claim and RAM fit at 9.5M vectors are unproven (FND-038) Next step (Platform data engineer): Run a pgvector filtered-query benchmark at full synthetic scale before Build Phase 5.
- FND-029 (needs investigation): BM25 fallback assumes a capability the schema doesn't provide (FND-029) Next step (Platform data engineer): Check the supported full-text and BM25 options on the target Azure PostgreSQL service.
- FND-010 (needs investigation): Confirmed write-path decision rests on the pending Event Hubs confirmation (FND-010) Next step (Platform architect): Run an Event Hubs (Kafka API) spike against the Section 18 capability list and close backlog item 9.

Research questions left unanswered:
- RQ-005: Can Entra ID OAuth 2.0 access tokens be valid for 48 hours (default and maximum configurable lifetimes), and does the design confuse access-token lifetime with refresh-token or session lifetime?
- RQ-006: Is SGD 800-1,200/month realistic for Azure Database for PostgreSQL Flexible Server Memory Optimised 16 vCores / 128 GB in Southeast Asia, including storage, HA and backups, and does the pgvector extension supported there include the needed HNSW and iterative-scan features?
- RQ-007: Do Singapore PDPA obligations (retention limitation, access and correction, protection, breach notification) conflict with agent per-learner backups that survive learner self-deletion, with audit logs that are append-only and never modified, and with an unspecified audit retention period?
- RQ-009: Does the design hold for 15,000 learners and ~9.5M vectors in a single 128 GB instance with high availability, and what happens when PostgreSQL, Redis or the embedding service fails (the BM25 fallback has no defined index; Azure OpenAI rate limits during re-embedding)?
- RQ-010: Does Azure Event Hubs' Kafka endpoint support what the write path assumes (consumer groups, retries, ordering per partition, retention), and are there tier limits on throughput, retention or consumer groups that matter for term-start write spikes?

## Evidence limitations

- DOC-sit_sample_v1: native PDF block not sent because the configured model backend accepts text only. Impact: figures, diagrams and tables rendered as images were not visible to the model; the review is based on the extracted text (DEG-001)
- assess shard 2/4 (requirements_and_consistency) was cut by the stage 1 limit at 265 s; 8 finished finding(s) kept (cut call llm-0004). Impact: every criterion of the shard has a finding; the shard's lower-ranked findings, if any, are missing (DEG-002)
- the refine call was cut by the run deadline (the refine model call was cut after 200 s by the refine limit (465 s on the run clock; deadline 540 s; not retried past it)). Impact: the merged assess findings are reported in severity and confidence order, without the global refine pass (no duplicates merged, no registry decisions linked, no research evidence attached) (DEG-003)

## Evidence register

| ID | Type | Source | Retrieved | Cited |
|---|---|---|---|---|
| EV-001 | external (informal) | [Iterative Scanning | pgvector/pgvector | DeepWiki](https://deepwiki.com/pgvector/pgvector/6.2-iterative-scanning) via mcp-internet-search/search_web call-0001 | 2026-10-03T08:31:45Z | no |
| EV-002 | external (informal) | [Iterative index scans · Issue #678 · pgvector/pgvector - GitHub](https://github.com/pgvector/pgvector/issues/678) via mcp-internet-search/search_web call-0001 | 2026-10-03T08:31:45Z | no |
| EV-003 | external (informal) | [pgvector HNSW Postgres 18 Production Tuning Tutorial 2026](https://nerdleveltech.com/pgvector-hnsw-postgres-18-production-tuning-tutorial) via mcp-internet-search/search_web call-0001 | 2026-10-03T08:31:45Z | no |
| EV-004 | external (secondary) | [Why pgvector Returns Too Few Results: Filtered HNSW, ef_search, and ...](https://rajivonai.com/blog/2026-04-27-pgvector-filtered-search-too-few-results/) via mcp-internet-search/search_web call-0001 | 2026-10-03T08:31:45Z | no |
| EV-005 | external (informal) | [Supabase pgvector: Embeddings, HNSW Indexes, Filtering, and RAG Performance](https://www.datastudios.org/post/supabase-pgvector-embeddings-hnsw-indexes-filtering-and-rag-performance) via mcp-internet-search/search_web call-0001 | 2026-10-03T08:31:45Z | no |
| EV-006 | external (primary official) | [Configurable Token Lifetimes - Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/configurable-token-lifetimes) via mcp-internet-search/search_web call-0002 | 2026-10-03T08:31:45Z | no |
| EV-007 | external (primary official) | [Set token lifetimes - Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/configure-token-lifetimes) via mcp-internet-search/search_web call-0002 | 2026-10-03T08:31:45Z | no |
| EV-008 | external (informal) | [entra-docs/docs/identity-platform/configurable-token ... - GitHub](https://github.com/MicrosoftDocs/entra-docs/blob/main/docs/identity-platform/configurable-token-lifetimes.md) via mcp-internet-search/search_web call-0002 | 2026-10-03T08:31:45Z | no |
| EV-009 | external (primary official) | [Set token lifetimes | Azure Docs](https://docs.azure.cn/en-us/entra/identity-platform/configure-token-lifetimes) via mcp-internet-search/search_web call-0002 | 2026-10-03T08:31:45Z | no |
| EV-010 | external (informal) | [Microsoft Entra Configurable Token Lifetimes: What They Are ...](https://nebularatech.com/microsoft-entra-configurable-token-lifetimes/) via mcp-internet-search/search_web call-0002 | 2026-10-03T08:31:45Z | no |
| EV-011 | external (informal) | mcp:mcp-internet-search/search_web?{"fetch_top_n":2,"mode":"answer","query":"pdpc advisory guidelines retention limitation obligation cease to retain"} via mcp-internet-search/search_web call-0003 | 2026-10-03T08:31:45Z | no |
| EV-012 | external (primary official) | [Azure Event Hubs Quotas and Limits Overview - Azure Event ...](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-quotas) via mcp-internet-search/search_web call-0004 | 2026-10-03T08:31:45Z | no |
| EV-013 | external (primary official) | [Azure Event Hubs quotas and limits](https://docs.azure.cn/en-us/event-hubs/event-hubs-quotas) via mcp-internet-search/search_web call-0004 | 2026-10-03T08:31:45Z | no |
| EV-014 | external (primary official) | [Compare Azure Event Hubs tiers - learn.microsoft.com](https://learn.microsoft.com/en-us/azure/event-hubs/compare-tiers) via mcp-internet-search/search_web call-0004 | 2026-10-03T08:31:45Z | no |
| EV-015 | external (primary official) | [Compare Azure Event Hubs tiers](https://docs.azure.cn/en-us/event-hubs/compare-tiers) via mcp-internet-search/search_web call-0004 | 2026-10-03T08:31:45Z | no |
| EV-016 | external (primary official) | [Consumer Group Limits per Namespace - Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/2200688/consumer-group-limits-per-namespace) via mcp-internet-search/search_web call-0004 | 2026-10-03T08:31:45Z | no |
| EV-017 | external (primary official) | [List of extensions and modules by name in Azure Database for ...](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-versions) via mcp-internet-search/search_web call-0005 | 2026-10-03T08:31:50Z | no |
| EV-018 | external (primary official) | [Vector Search in Azure Database for PostgreSQL Flexible ...](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector) via mcp-internet-search/search_web call-0005 | 2026-10-03T08:31:50Z | no |
| EV-019 | external (informal) | [66+ PostgreSQL Extensions on Azure, Ranked (2026)](https://1bench.dev/extensions/postgresql/on-azure-flexible) via mcp-internet-search/search_web call-0005 | 2026-10-03T08:31:50Z | no |
| EV-020 | external (primary official) | [Extensions and modules in Azure Database for PostgreSQL ...](https://docs.azure.cn/en-us/postgresql/extensions/concepts-extensions) via mcp-internet-search/search_web call-0005 | 2026-10-03T08:31:50Z | no |
| EV-021 | external (primary official) | [Azure Database for PostgreSQL](https://azure.microsoft.com/en-us/products/postgresql/) via mcp-internet-search/search_web call-0005 | 2026-10-03T08:31:50Z | no |
| EV-022 | external (primary official) | [Azure OpenAI in Microsoft Foundry Models quotas and limits](https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits) via mcp-internet-search/search_web call-0006 | 2026-10-03T08:32:00Z | no |
| EV-023 | external (primary official) | [Manage Azure OpenAI in Microsoft Foundry Models quota](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota) via mcp-internet-search/search_web call-0006 | 2026-10-03T08:32:00Z | no |
| EV-024 | external (primary official) | [text-embedding-3-small Model | OpenAI API](https://developers.openai.com/api/docs/models/text-embedding-3-small) via mcp-internet-search/search_web call-0006 | 2026-10-03T08:32:00Z | no |
| EV-025 | external (informal) | [text-embedding-3-small | Model Catalog | Microsoft Foundry](https://ai.azure.com/catalog/models/text-embedding-3-small) via mcp-internet-search/search_web call-0006 | 2026-10-03T08:32:00Z | no |
| EV-026 | external (informal) | [Azure Cognitive Deployment: Configure Token Per Minute Quota](https://github.com/hashicorp/terraform-provider-azurerm/issues/22195) via mcp-internet-search/search_web call-0006 | 2026-10-03T08:32:00Z | no |
| EV-027 | external (secondary) | [https://rajivonai.com/blog/2026-04-27-pgvector-filtered-search-too-few-results/](https://rajivonai.com/blog/2026-04-27-pgvector-filtered-search-too-few-results/) via mcp-internet-search/fetch_url call-0007 | 2026-10-03T08:32:21Z | no |
| EV-028 | external (informal) | [PDPA2012 § 25 — Retention of personal data | LawPlayer SG](https://lawplayer.com/sg/act/PDPA2012/25) via mcp-internet-search/search_web call-0008 | 2026-10-03T08:32:21Z | no |
| EV-029 | external (informal) | [HR And PDPA Retention Limit Obligation - SQL View](https://sqlview.com.sg/document-management-system-singapore/hr-document-management-system/hr-and-pdpa-retention-limit-obligation/) via mcp-internet-search/search_web call-0008 | 2026-10-03T08:32:21Z | no |
| EV-030 | external (primary official) | [Personal Data Protection Act 2012 - Singapore Statutes Online](https://sso.agc.gov.sg/Act/PDPA2012?ProvIds=pr25-) via mcp-internet-search/search_web call-0008 | 2026-10-03T08:32:21Z | no |
| EV-031 | doc | doc:DOC-sit_sample_v1#p7/s5 | - | yes |
| EV-032 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-033 | doc | doc:DOC-sit_sample_v1#p6/s3 | - | yes |
| EV-034 | doc | doc:DOC-sit_sample_v1#p13/s13 | - | yes |
| EV-035 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-036 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-037 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-038 | doc | doc:DOC-sit_sample_v1#p18/s19 | - | yes |
| EV-039 | doc | doc:DOC-sit_sample_v1#p20/s21 | - | yes |
| EV-040 | doc | doc:DOC-sit_sample_v1#p6/s3 | - | yes |
| EV-041 | doc | doc:DOC-sit_sample_v1#p15/s15 | - | yes |
| EV-042 | doc | doc:DOC-sit_sample_v1#p4/s2.2 | - | yes |
| EV-043 | doc | doc:DOC-sit_sample_v1#p30/s28 | - | yes |
| EV-044 | doc | doc:DOC-sit_sample_v1#p27/s27.1 | - | yes |
| EV-045 | doc | doc:DOC-sit_sample_v1#p16/s16 | - | yes |
| EV-046 | doc | doc:DOC-sit_sample_v1#p18/s18 | - | yes |
| EV-047 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-048 | doc | doc:DOC-sit_sample_v1#p11/s11 | - | yes |
| EV-049 | doc | doc:DOC-sit_sample_v1#p8/s6 | - | yes |
| EV-050 | doc | doc:DOC-sit_sample_v1#p3/s2.1 | - | yes |
| EV-051 | doc | doc:DOC-sit_sample_v1#p25/s25 | - | yes |
| EV-052 | doc | doc:DOC-sit_sample_v1#p26/s26 | - | yes |
| EV-053 | doc | doc:DOC-sit_sample_v1#p23/s23 | - | yes |
| EV-054 | doc | doc:DOC-sit_sample_v1#p16/s17 | - | yes |
| EV-055 | doc | doc:DOC-sit_sample_v1#p6/s3 | - | yes |
| EV-056 | doc | doc:DOC-sit_sample_v1#p3/s2 | - | yes |
| EV-057 | inference | inference:EV-057 from EV-031, EV-032, EV-033 | - | yes |
| EV-058 | inference | inference:EV-058 from EV-036, EV-037 | - | yes |
| EV-059 | inference | inference:EV-059 from EV-041, EV-042 | - | yes |
| EV-060 | inference | inference:EV-060 from EV-047, EV-048 | - | yes |
| EV-061 | doc | doc:DOC-sit_sample_v1#p4/s2.2 | - | yes |
| EV-062 | doc | doc:DOC-sit_sample_v1#p26/s27.1 | - | yes |
| EV-063 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-064 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-065 | doc | doc:DOC-sit_sample_v1#p14/s14 | - | yes |
| EV-066 | doc | doc:DOC-sit_sample_v1#p27/s27.1 | - | yes |
| EV-067 | doc | doc:DOC-sit_sample_v1#p29/s28 | - | yes |
| EV-068 | doc | doc:DOC-sit_sample_v1#p16/s17 | - | yes |
| EV-069 | doc | doc:DOC-sit_sample_v1#p27/s27.1 | - | yes |
| EV-070 | doc | doc:DOC-sit_sample_v1#p15/s16 | - | yes |
| EV-071 | doc | doc:DOC-sit_sample_v1#p3/s2.1 | - | yes |
| EV-072 | doc | doc:DOC-sit_sample_v1#p8/s6 | - | yes |
| EV-073 | doc | doc:DOC-sit_sample_v1#p13/s13 | - | yes |
| EV-074 | doc | doc:DOC-sit_sample_v1#p18/s18 | - | yes |
| EV-075 | inference | inference:EV-075 from EV-061, EV-041, EV-045 | - | yes |
| EV-076 | inference | inference:EV-076 from EV-063, EV-064 | - | yes |
| EV-077 | inference | inference:EV-077 from EV-067, EV-068 | - | yes |
| EV-078 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-079 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-080 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-081 | doc | doc:DOC-sit_sample_v1#p8/s6 | - | yes |
| EV-082 | doc | doc:DOC-sit_sample_v1#p15/s15 | - | yes |
| EV-083 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-084 | doc | doc:DOC-sit_sample_v1#p5/s2.2 | - | yes |
| EV-085 | doc | doc:DOC-sit_sample_v1#p29/s28 | - | yes |
| EV-086 | doc | doc:DOC-sit_sample_v1#p26/s26 | - | yes |
| EV-087 | doc | doc:DOC-sit_sample_v1#p13/s13 | - | yes |
| EV-088 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-089 | doc | doc:DOC-sit_sample_v1#p26/s26 | - | yes |
| EV-090 | doc | doc:DOC-sit_sample_v1#p16/s17 | - | yes |
| EV-091 | doc | doc:DOC-sit_sample_v1#p26/s26 | - | yes |
| EV-092 | inference | inference:EV-092 from EV-047, EV-048 | - | yes |
| EV-093 | inference | inference:EV-093 from EV-078, EV-079, EV-080 | - | yes |
| EV-094 | inference | inference:EV-094 from EV-081, EV-082 | - | yes |
| EV-095 | inference | inference:EV-095 from EV-083 | - | yes |
| EV-096 | inference | inference:EV-096 from EV-084 | - | yes |
| EV-097 | inference | inference:EV-097 from EV-085, EV-068 | - | yes |
| EV-098 | inference | inference:EV-098 from EV-086, EV-087 | - | yes |
| EV-099 | inference | inference:EV-099 from EV-090 | - | yes |
| EV-100 | doc | doc:DOC-sit_sample_v1#p6/s3 | - | yes |
| EV-101 | doc | doc:DOC-sit_sample_v1#p25/s25 | - | yes |
| EV-102 | doc | doc:DOC-sit_sample_v1#p16/s16 | - | yes |
| EV-103 | doc | doc:DOC-sit_sample_v1#p4/s2.2 | - | yes |
| EV-104 | doc | doc:DOC-sit_sample_v1#p8/s5 | - | yes |
| EV-105 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-106 | doc | doc:DOC-sit_sample_v1#p15/s15 | - | yes |
| EV-107 | doc | doc:DOC-sit_sample_v1#p10/s8 | - | yes |
| EV-108 | doc | doc:DOC-sit_sample_v1#p16/s17 | - | yes |
| EV-109 | doc | doc:DOC-sit_sample_v1#p21/s21 | - | yes |
| EV-110 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-111 | doc | doc:DOC-sit_sample_v1#p6/s3 | - | yes |
| EV-112 | doc | doc:DOC-sit_sample_v1#p21/s22 | - | yes |
| EV-113 | doc | doc:DOC-sit_sample_v1#p7/s5 | - | yes |
| EV-114 | doc | doc:DOC-sit_sample_v1#p4/s2.2 | - | yes |
| EV-115 | doc | doc:DOC-sit_sample_v1#p15/s15 | - | yes |
| EV-116 | doc | doc:DOC-sit_sample_v1#p27/s27.2 | - | yes |
| EV-117 | inference | inference:EV-117 from EV-034, EV-035, EV-100 | - | yes |
| EV-118 | inference | inference:EV-118 from EV-102, EV-074, EV-037 | - | yes |
| EV-119 | inference | inference:EV-119 from EV-103, EV-041, EV-104 | - | yes |
| EV-120 | inference | inference:EV-120 from EV-107, EV-108 | - | yes |
| EV-121 | inference | inference:EV-121 from EV-110, EV-048 | - | yes |

## Review coverage

| Criterion | Outcome | Findings | Note |
|---|---|---|---|
| design_intent | findings | FND-012, FND-004, FND-006, FND-001 | Objectives, requirements, principles, decisions and backlog are explicit and traceable (strength). The main intent ambiguities are the Super Admin's scope against the hard wall and the undefined policy combination logic. |
| fitness_for_objectives | findings | FND-001, FND-002, FND-003, FND-004, FND-005, FND-006, FND-007, FND-008, FND-009, FND-011 | The core elements fit their purpose, but the agent backup, the write ordering, the MMP's runtime role and cache invalidation undermine FR-5, FR-15, NFR-4 and NFR-5 as written. |
| requirement_completeness | findings | FND-015, FND-016, FND-017 | no coverage row returned by the model; derived by code from the findings |
| internal_consistency | findings | FND-013, FND-014, FND-017, FND-019, FND-020 | no coverage row returned by the model; derived by code from the findings |
| claims_and_external_constraints | findings | FND-021, FND-022, FND-023, FND-024, FND-025, FND-026, FND-029, FND-027 | Checked the vector sizing arithmetic, the pgvector filtered-search claim, SKU and cost figures, the Entra token lifetime, Kafka retry claims, the BM25 fallback, DDL completeness and PDPA statements. The raw 57 GB vector estimate is consistent with 1536-dim float32. |
| security_and_privacy | findings | FND-031, FND-032, FND-033, FND-036, FND-037, FND-041, FND-042, FND-044 | Checked: access control, tier isolation, backup copies, revocation, caching, admin privilege, escalations, aggregates and credential custody. |
| scalability_and_failure_modes | findings | FND-033, FND-034, FND-035, FND-038, FND-039, FND-040 | Checked: the async write semantics, MMP dependency, vector capacity and filtered ANN, embedding outage and recovery. |
| assumptions_and_dependencies | findings | FND-023, FND-024, FND-027, FND-028, FND-030 | Checked the confirmed decisions against the Pending Backlog (Event Hubs, Redis, Auditor/PDPA sign-off, SIS failure handling) and dependencies on outside capabilities (Entra ID, SIS). The Redis confirmation item is low impact and is not raised separately. |
| verifiability | findings | FND-014, FND-015, FND-016, FND-018 | no coverage row returned by the model; derived by code from the findings |
| decision_preservation | findings | FND-008, FND-009, FND-010 | No finding challenges an approved decision. FND-008 and FND-009 refine the pgvector and token decisions within their scope, and FND-010 flags a confirmed decision that rests on a pending backlog item. |
| operability_and_governance | findings | FND-034, FND-036, FND-037, FND-040, FND-043 | Checked: monitoring, DR, ownership of backlog items, privileged roles, cost scope and governance decisions that need accountable owners. |

## Run details

| | |
|---|---|
| Run | ui-261003-082941-36e8 (started 2026-10-03T08:29:41Z) |
| Outcome | completed_degraded |
| Model | requested claude-opus-5-5; served claude-opus-5-5; effort per-stage (extra.model.effort_by_stage) |
| Persona | generalist_architect |
| Tool transport | live |
| Research stop | sufficient_evidence (decision): model_stop_vote; 1 iteration(s); 0 cited of 30 retrieved |
| Tool calls | mcp-internet-search: 8 |
| Tokens | input 223395, cached 123565, output 93217; cost ~$3.68 (price table 2026-09-25); a lower bound: 2 model calls with unrecorded usage (assess, deadline cut; refine, deadline cut) |
| Extractor | pdfplumber 0.11.10 |
| Config sha256 | 8c7850e04ab0f44723fc5620c62ec5a18e5725804a2923840a4c7b5cdca07ffa |
| Prompt bundle sha256 | 6f0ee28ab9acf35152a2d4456207a8a068222149422e66d801c8195455c28ba7 |
| Git commit | 886c3fc99eb4ec875e135440919e7bdc918ee094 |
| Fault schedule | none |
| Model fallbacks | 0 |
| Canonical text DOC-sit_sample_v1 | sha256 7be073ff2e98e50998367a46b92ed5dbf85815177eb36c2e2c12a0f52a458de8 |
