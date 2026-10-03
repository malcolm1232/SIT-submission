# Design review: SIT Institutional Memory Platform — Detailed Design

| | |
|---|---|
| Review | REV-sit_sample_tools_1 (full review) |
| Under review | DOC-sit_sample_v1: SIT Institutional Memory Platform — Detailed Design vVersion 2.0, 30 pages |
| Verdict | **fit with conditions** (confidence 0.72, medium) |
| Tools used | mcp-internet-search, mcp-research-information |
| Tools disabled | mcp-browser-automation-pw, mcp-document-intelligence |
| Reporting threshold | severity low and above (0 finding(s) in the appendix) |


## Design intent

The document is the detailed design for the SIT Institutional Memory Platform. The platform is a governed memory infrastructure at institution level, not a per-agent memory store. It serves the AI Tutor, AI Buddy, Academic Advisory, Counselling, Career and Orientation agents for about 15,000 SIT learners. It provides a structured namespace per learner, access control applied before retrieval and backed by policy, an administrative control plane (MMP), audit trails for PDPA compliance, a strict counselling isolation wall, an asynchronous write path and a cached read path. SIT-AI-Factory-RAG is out of scope. The document is at design stage (build not started) and is intended to be detailed enough for engineers or an AI coding assistant to begin implementation. Section 28 assesses where it is and is not ready for that.

Objectives:
- P1: The learner namespace is authoritative and the agent's copy is backup only. Conflicts are resolved in favour of the learner namespace.
- P2: Memory is private by default: private to the learner, shared by exception, and anonymised for service learning.
- P3: Access control happens before retrieval: the namespace restriction gates the query itself, not the results after retrieval.
- P4: The counselling hard wall: wellbeing/counselling/ is HIGHLY_RESTRICTED, with zero cross-domain reads, no MMP override and no exceptions.
- P5: Agents share information only through the learner namespace and never access each other's memory directly.
- P6: No uncontrolled self-writing: every write is classified and policy-checked before storage.
- P7: Every operation is audited (access, write, denial, compaction, deletion, escalation), as PDPA requires.
- P8: Writes are asynchronous via Kafka (non-blocking) and reads are cached (Redis L1, then PostgreSQL).
- P9: Administrators, not agents, configure slot templates, sensitivity levels and retention rules.
- P10: Minimum useful context: summaries over transcripts, facts over full conversations, and a token-budgeted context pack.
- Cover all six layers of memory (capture, classification, storage, retrieval, governance, administration), not only layers 2-4 as typical memory products do.
- Be specified in enough detail for an engineering team or AI coding assistant to begin implementation (readiness is self-assessed in Section 28).

Constraints:
- P7: PDPA compliance requires audit trails for every memory operation. NFR-7 also requires all personal-data operations to be logged, retention to be enforceable per slot, and PII fields to be flagged.
- NFR-10: Vector-store infrastructure cost must stay within SGD 800-1,200/month at 15,000-learner scale (Azure Singapore region, Memory Optimised 16-vCore tier).
- NFR-5: HIGHLY_RESTRICTED data must be stored in a physically separate memory_sensitive schema, with database credentials separate from memory_standard.
- FR-5: The counselling hard wall must be enforced at both the policy-engine level and the schema/credential level, with no MMP override path.
- SIT-AI-Factory-RAG (Azure AI Search) is a separate system in a separate resource group and shares no infrastructure with this platform.
- The ten foundational principles take precedence: where a later section conflicts with a principle, the principle wins.
- Platform technologies are Azure based: Entra ID / OAuth 2.0, Azure Database for PostgreSQL with pgvector, Kafka/Azure Event Hubs, Redis, and Azure OpenAI text-embedding-3-small (1536-dim).

Key assumptions:
- Each learner averages about 600 vectors across a full degree, giving about 9.5M vectors in total at 15,000 learners.
- Queries are always filtered by learner_id + slot_path, so the effective search space per query is 500-800 vectors, not 9.5 million.
- The 16-vCore / 128 GB RAM SKU holds the HNSW index in memory, with a growth ceiling of about 30-40M vectors (about 50,000-60,000 learners).
- Kafka absorbs write spikes at term start, and failed writes queue and retry automatically.
- The remaining domain templates (campus_life, cocurricular, escalations, industry_attachment) can be produced by analogy with the ones written out.
- The deferred backlog items (cohort namespace, compaction, non-SIT identity) are not needed for the launch scope of the initial six agents.
- Human counsellors access counselling data through a separate clinical system outside this platform.
- SIS will reliably send webhook events (registration, enrolment, module registration and withdrawal, graduation) that drive provisioning.

Located at: p.3 §1 (3 passages).

## Fitness for purpose

**Fit with conditions** (confidence 0.72). The design is coherent and closely aligned with its own goals. Requirements carry IDs that trace to acceptance criteria and to an honest readiness map (FND-010). The two-tier store with separate credentials gives the counselling wall real enforcement at the credential level (FND-046). The six-layer scope and the governed single-path architecture suit an institution-level memory platform, and most of the structure needs no rework. It is not yet fit to build unconditionally, because seven high-severity findings are still open and none is critical: - The agent per-learner backup is an ungoverned data copy. It undermines P6, NFR-5, FR-15 and FR-16 (FND-011), and it keeps serving data after a token is revoked (FND-037). - The counselling hard wall contradicts the Super Admin and MMP emergency-access roles, and the FR-5 test cannot show that no override exists (FND-012). - Writes that fail after the ACK have no outcome, and the tier topic is chosen before classification (FND-038). - The MMP sits in the request path, against NFR-4 (FND-013). - The filtered-HNSW premise behind NFR-2 is unverified (FND-026). Each of these can be fixed by design refinement, a governance decision or a bounded prototype. None requires replacing an approved decision such as PostgreSQL + pgvector, Kafka/Event Hubs or the two tiers. FND-037 refines the confirmed auth-token decision rather than challenging it. The medium findings (cache staleness, PDPA sign-off, sizing arithmetic, DDL gaps, policy combination logic, acceptance-criterion defects) narrow the build-ready scope further, but they do not block the architecture. Limits of this review: - The review worked only from extracted text (DEG-001), so Figures 1-3 and any table content rendered as an image were not checked. - Web search failed (DEG-002), so three external premises remain unverified: Entra ID 48-hour token lifetime (FND-029), pgvector filtered-HNSW behaviour (FND-026) and Azure Singapore pricing (FND-034). Findings that rest on them are framed as validation needs, not confirmed defects. These gaps lower confidence in the performance, cost and token conditions more than in the governance conditions, which rest on internal contradictions in the document.

Conditions:
- Bring the agent per-learner backup under governance. Write it through the Gateway and policy path, or define it as a tier-aware governed store. State where it is stored, its sensitivity tier (counselling content must stay in memory_sensitive), its retention, and how FR-15 deletion applies to it. Limit its use to the FR-16 unreachable-namespace case. Owner: Data Protection Officer together with the platform architect, who should decide whether serving from backup on a REVOKED token is allowed (by default it should not be). (FND-011, FND-037)
- Resolve the counselling override contradiction. Explicitly exclude wellbeing/counselling/ and memory_sensitive from Super Admin 'Everything' and from MMP emergency access. Name who controls the named_agents list and how changes to it are approved and audited. Define the counselling write path, since counsellor-written summaries exist. Extend the FR-5 test so it shows that no admin, MMP or credential path can read the slot. (FND-012)
- Specify the failure semantics of the async write path. Define what happens to writes rejected after the ACK, including how agents are notified. Add a dead-letter queue with no retry for deterministic rejections, and define idempotency keys and per-learner or per-slot ordering. Prevent tier mis-routing by choosing the topic only after classification, or by re-routing upgrades without them passing through standard-tier processing. Confirm that Event Hubs supports the assumed retry, consumer-group and ordering behaviour. Reconcile the double audit entries per write with FR-13. (FND-038, FND-031, FND-023)
- Take the MMP out of the live request path, as NFR-4 requires. Run the PolicyEngine and AuditStore write path as request-path services that are separate from the MMP admin service. Serve published templates to the Validator from a replicated or cached registry. Define how Check 4 behaves when the MMP is unavailable. Then run the NFR-4 chaos test against that topology. (FND-013)
- Before relying on NFR-1, NFR-2 and NFR-10, prototype the vector store on the confirmed SKU with a realistic synthetic dataset. Establish how filtered queries actually execute (global HNSW with post-filtering, versus a B-tree followed by an exact scan, versus partitioning or iterative scan) and measure recall and latency for each. Correct the arithmetic for RAM fit, growth ceiling and the per-learner vector count. Source the cost estimate and align its scope with its acceptance test. (FND-026, FND-027, FND-034)
- Make cached context packs respect policy changes. Invalidate them when permissions are revoked, data is deleted or redaction rules change, or re-check them at serve time. Isolate cache entries that contain HIGHLY_RESTRICTED data (separate instance or credentials, or exclude them from the cache). (FND-041)
- Obtain DPO decisions before audit logs accumulate and agents write pattern data. The decisions cover audit retention period and PDPA alignment sign-off, how escalation content is retained in the audit log, the anonymisation method and minimum group size for cross-learner and cohort patterns, and explicit exclusion of RESTRICTED data from aggregates. (FND-030, FND-044)
- Close the specification and acceptance gaps before Build Phases 3, 4, 6 and 9: - Policy Engine combination and precedence logic, with an FR-8 test that covers REDACT and the time-based dimensions. - DDL columns for embedded status, the BM25 index, pii/retention/expires_at on all tables, consent, and escalation target and status. - An escalations template with record-level access rules. - A corrected FR-1 criterion. - Concrete thresholds for NFR-3 and FR-9, including the synchronous Gateway step. - WORKING-vs-persisted typing for orientation progress. (FND-006, FND-018, FND-019, FND-020, FND-017, FND-009)
- Confirm and assign the identity and operational premises. Confirm the token that carries the 48-hour lifetime and how revocation is detected. Key records on the immutable entra_object_id, or define a process for UPN renames. Complete the SIS lifecycle events (leaving SIT, leave of absence, transfer, term end). Assign an owner and targets for PostgreSQL backup, HA, RPO/RTO and pipeline monitoring, reconciled with FR-15 deletion. (FND-029, FND-022, FND-043)

| Objective | Verdict | Findings |
|---|---|---|
| P1 | fit with conditions | FND-011, FND-022, FND-043 |
| P2 | fit with conditions | FND-037, FND-041, FND-044 |
| P3 | fit with conditions | FND-026, FND-019, FND-041 |
| P4 | fit with conditions | FND-012, FND-011, FND-046 |
| P5 | fit with conditions | FND-011, FND-019 |
| P6 | fit with conditions | FND-011, FND-038 |
| P7 | fit with conditions | FND-030, FND-023, FND-013 |
| P8 | fit with conditions | FND-038, FND-031, FND-017, FND-041 |
| P9 | fit | FND-010 |
| P10 | fit | FND-010 |
| Six-layer coverage (Section 4) | fit with conditions | FND-043, FND-009, FND-010 |
| Implementation readiness (Section 1 / Section 28) | fit with conditions | FND-010, FND-018, FND-006, FND-020 |

What would change this verdict: The verdict would move to not_fit if the design owners decide to keep any of the following: - Super Admin or MMP access to counselling memory. - Agent backups as ungoverned stores holding HIGHLY_RESTRICTED or deleted data. - Serving personal data on a revoked token. It would also move to not_fit if the vector-store prototype shows that filtered queries on the confirmed SKU cannot meet NFR-2 latency with acceptable recall without an engine or SKU change. That would challenge the confirmed vector-store and SKU decisions, which needs at least two evidence items. The verdict would move to fit once the conditions are reflected in a revised design and the prototype, Entra ID token-lifetime and pricing checks confirm the external premises that this review could not verify (DEG-002). A review of the PDF figures (DEG-001) that turned up nothing new would also raise confidence.

## Strengths

### FND-010 Clear, traceable statement of intent: IDed requirements, ranked principles, acceptance criteria and an honest readiness map

- **strength** · confidence 0.85 (high) · rank 23
- Disposition: **no change**

Requirements carry IDs that are traced to a pass/fail acceptance row in Section 27 and to a readiness verdict in Section 28. Principles have an explicit precedence rule, and Section 28 openly states which components are not ready to build. This gives a solid basis for reviewing the design against its own objectives and for planning the spec-closure pass before Build Phases 3, 6 and 7.

- Where: p.3 §2: "Each requirement carries an ID used again in Section 27"
- Where: p.6 §3: "Where a later section appears to conflict with one of these, the principle wins."
- Where: p.29 §28: "The honest answer is partial - strong in some areas, not yet sufficient in others."
- Evidence EV-035 (doc, supports): "Each requirement carries an ID used again in Section 27" [doc:DOC-sit_sample_v1#p3/s2]
- Evidence EV-036 (doc, supports): "The honest answer is partial - strong in some areas, not yet sufficient in others." [doc:DOC-sit_sample_v1#p29/s28]
- Evidence EV-070 (doc, supports): "Each requirement from Section 2 is validated by a specific method with a concrete pass/fail acceptance criterion." [doc:DOC-sit_sample_v1#p26/s27]
- Evidence EV-018 (doc, supports): "Where a later section appears to conflict with one of these, the principle wins." [doc:DOC-sit_sample_v1#p6/s3]
- Why no change is needed: The intent, requirements and readiness are stated clearly enough to review and test against, and are traced end to end.
- Decision AD-036 (3 Foundational Principles): preserves. Affirms the principle-precedence rule.

### FND-046 Two-tier sensitive storage with separate credentials and per-tier topics

- **strength** · confidence 0.80 (high) · rank 24
- Disposition: **no change**

HIGHLY_RESTRICTED data has its own schema with separate credentials and a separate embedding deployment. Its writes go through a dedicated Kafka topic, and NFR-5 has a test that checks credentials fail across tiers. This puts the FR-5/P4 hard wall at the credential level, not only in policy logic. FND-001 and FND-006 extend the same boundary to the backup and the cache.

- Where: p.17 §18 (NFR-5): "separate topics per sensitivity tier keep HIGHLY_RESTRICTED writes physically isolated in transit"
- Where: p.27 §27.2 (NFR-5): "A credential valid for memory_standard is confirmed to fail authentication"
- Evidence EV-108 (doc, supports): "separate topics per sensitivity tier keep HIGHLY_RESTRICTED writes physically isolated in transit" [doc:DOC-sit_sample_v1#p17/s18]
- Why no change is needed: Enforcing isolation at the credential level and in transit meets FR-5 and NFR-5 as written, and the acceptance test checks it directly.
- Decision AD-009 (25 Confirmed Decisions - Two sensitivity tiers): preserves. Affirms the two-tier storage decision.
- Decision AD-053 (NFR-5): preserves. Affirms NFR-5 credential separation and its test.

## Risks

### FND-011 Agent per-learner backup is an ungoverned copy that conflicts with P6, NFR-5, FR-15 and FR-16

- **risk** · internal contradiction · severity **high** · confidence 0.80 (high) · rank 1
- Disposition: **governance decision** (also: refinement now)

Section 13 has every agent hold a full per-learner store for all learners. Section 14 writes to it 'always, immediate', outside the Gateway and Kafka path, and Sections 13 and 20 say it survives learner self-deletion. This conflicts with P6 (all writes policy-checked before storage), with Section 5 ('No agent ever touches a data store directly'), and with FR-15 (deleted memory still exists in the backups). It also conflicts with NFR-5: the Counsellor agent's backup would hold HIGHLY_RESTRICTED content outside memory_sensitive. FR-16 limits the backup to cases where the namespace is unreachable, but Sections 6 and 15 also use it when a token is EXPIRED or REVOKED. The document never says where the backup is stored, what tier it sits in, or how retention applies to it.

- Where: p.13 §13 (FR-15): "survives learner deletion of their own memory (enabling session resume); rules are written by the system"
- Where: p.4 §2.1 (FR-16): "Each agent shall maintain its own per-learner backup memory, used only when the learner namespace is"
- Where: p.6 §3 (P6): "No uncontrolled self-writing - all writes are classified and policy-checked before storage."
- Evidence EV-040 (doc, supports): "survives learner deletion of their own memory (enabling session resume); rules are written by the system" [doc:DOC-sit_sample_v1#p13/s13]
- Evidence EV-041 (doc, supports): "No uncontrolled self-writing - all writes are classified and policy-checked before storage." [doc:DOC-sit_sample_v1#p6/s3]
- Evidence EV-014 (doc, supports): "Learners shall be able to request deletion of their own user-deletable memory." [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-042 (doc, supports): "HIGHLY_RESTRICTED data shall be stored in a physically separate schema (memory_sensitive) with" [doc:DOC-sit_sample_v1#p4/s2.2]
- Evidence EV-043 (doc, supports): "Agent own memory (always, immediate)" [doc:DOC-sit_sample_v1#p14/s14]
- Evidence EV-071 (inference, supports): "An immediate, always-on agent-local write that survives learner deletion bypasses the classified and policy-checked write path, keeps deleted data, and for the Counsellor agent puts HIGHLY_RESTRICTED data outside memory_sensitive." [inference:EV-071] derived from EV-040, EV-041, EV-014, EV-042, EV-043
- Evidence EV-013 (doc, supports): "Agent per-learner backup Survives learner self-deletion; enables session resume" [doc:DOC-sit_sample_v1#p19/s20]
- Evidence EV-012 (doc, supports): "On revocation: inform the learner, serve from agent backup" [doc:DOC-sit_sample_v1#p8/s6]
- Evidence EV-037 (inference, supports): "Data that survives self-deletion and is still served after revocation, with no stated tier, credential or audit controls, cannot satisfy FR-15 or the schema/credential-level hard wall in FR-5 for counselling content." [inference:EV-037] derived from EV-011, EV-012, EV-013, EV-014
- Evidence EV-109 (inference, supports): "A backup that copies namespace content, has no stated tier or credentials, and is kept after learner deletion means deleted or HIGHLY_RESTRICTED data lives on outside the controls that NFR-5, FR-15 and FR-13 require." [inference:EV-109] derived from EV-097, EV-014, EV-042
- Recommendation: Add a section on the agent backup store that defines (a) where it is stored, split by sensitivity tier (HIGHLY_RESTRICTED backups in memory_sensitive), (b) that backup writes pass through Gateway/Policy checks, (c) that FR-15 deletion propagates to backups or a documented exemption approved by the DPO, and (d) one list of degraded-mode triggers (unreachable, EXPIRED, REVOKED) reconciled with FR-16. Extend the FR-15 and FR-16 acceptance tests to inspect the backup contents.
  - Issue: The agent backup store has no governance (no tier, no policy check, no deletion propagation), which contradicts P6, NFR-5 and FR-15. Its trigger conditions also disagree between FR-16 and Sections 6 and 15.
  - Rationale: The backup holds the same learner data as the namespace, so it must meet the same controls; otherwise it undermines the counselling wall and PDPA deletion.
  - Expected benefit: Makes FR-15, NFR-5 and P6 achievable and makes the trigger conditions for degraded mode consistent. (objectives: FR-15, FR-16, NFR-5, P6)
  - Supporting evidence: EV-040, EV-041, EV-014, EV-042, EV-071
  - Verification: FR-15 test asserts that deleted keys are absent from every agent backup; NFR-5 test asserts that the Counsellor backup is only reachable with memory_sensitive credentials.
- Next step: Data governance officer / DPO with platform architect: Decide whether the backup survives deletion, and set its storage tier and policy path; then revise Sections 13, 14 and 20 and FR-16.
- Decision AD-048 (FR-16): refines. Gives the FR-16 backup a governed tier, policy path and deletion rule while keeping it.
- Decision AD-047 (FR-15): refines. Makes FR-15 deletion apply to the backup copies too.
- Decision AD-009 (25 Confirmed Decisions - Two sensitivity tiers): preserves. Applies the two-tier split to backup storage.
- Decision AD-017 (25 Confirmed Decisions - Counselling): preserves. Extends the counselling hard wall to the Counsellor agent's backup.
- Decision AD-033 (P7 / PDPA): preserves. Brings backup operations under audit.
- Decision AD-014 (25 Confirmed Decisions - Auth token window): refines. Lines up the degraded-mode triggers in FR-16 with the EXPIRED and REVOKED branches.

### FND-012 Counselling hard wall contradicted by Super Admin 'Everything' and MMP emergency access; FR-5 test cannot show there is no override

- **risk** · internal contradiction · severity **high** · confidence 0.75 (medium) · rank 2
- Disposition: **refinement now** (also: needs testing)

FR-5 and P4 forbid any MMP override path for wellbeing/counselling/. Yet Section 19 gives Super Admin access to 'Everything', and Section 21 gives the MMP super admin 'Overrides, corrections, emergency access'. Section 15 also lets a configurable named_agents list pass Check 6, and nothing says who controls that list. Section 19 says the Counsellor agent 'reads only', while the counselling template has counsellor-written summaries, so the write path for this slot is undefined. The FR-5 acceptance test only checks three named agents and cannot show that no override path exists.

- Where: p.18 §19 (FR-5): "Super Admin Everything - always audit-logged, mandatory reason required"
- Where: p.20 §21: "Super admin Overrides, corrections, emergency access (always audit-logged)"
- Where: p.26 §27.1 (FR-5): "turn and attempts to read wellbeing/counselling/; all three attempts return"
- Evidence EV-044 (doc, supports): "wellbeing/counselling/ shall be classified HIGHLY_RESTRICTED with zero cross-domain reads and no" [doc:DOC-sit_sample_v1#p3/s2.1]
- Evidence EV-015 (doc, supports): "Super Admin Everything - always audit-logged, mandatory reason required" [doc:DOC-sit_sample_v1#p18/s19]
- Evidence EV-016 (doc, supports): "Super admin Overrides, corrections, emergency access (always audit-logged)" [doc:DOC-sit_sample_v1#p20/s21]
- Evidence EV-017 (doc, supports): "Counsellor agent reads only. Human counsellors may access via a separate clinical system." [doc:DOC-sit_sample_v1#p19/s19]
- Evidence EV-045 (doc, supports): "HIGHLY_RESTRICTED slots: hard block for all agents not in an" [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-100 (doc, supports): "request/response JSON schemas and auth on the Admin API itself are not yet specified" [doc:DOC-sit_sample_v1#p21/s21]
- Evidence EV-112 (inference, supports): "A Super Admin with 'Everything' and override rights through an Admin API with no defined auth is an MMP override path into counselling, which FR-5 forbids." [inference:EV-112] derived from EV-015, EV-016, EV-100
- Evidence EV-018 (doc, contrary): "Where a later section appears to conflict with one of these, the principle wins." [doc:DOC-sit_sample_v1#p6/s3]
- Recommendation: In Sections 19 and 21, explicitly exclude wellbeing/counselling/ and memory_sensitive from Super Admin and MMP emergency access. State that MMP credentials have no grant on memory_sensitive. Fix named_agents to the Counsellor agent through an approval process outside the MMP. Define the counselling write path (agent or clinical system). Extend the FR-5 test to the Super Admin, Institution Admin and MMP Admin API (GET /namespaces, GET /audit, DELETE) and to an attempt to add an agent to named_agents.
  - Issue: The roles and the named_agents list create override paths into the counselling slot that FR-5 forbids, and the FR-5 test does not exercise them.
  - Rationale: FR-5 requires enforcement both at the policy-engine level and at the credential level; an admin role with 'Everything' breaks that unless counselling is explicitly carved out.
  - Expected benefit: FR-5 and P4 become consistent and testable. (objectives: FR-5, P4, NFR-5)
  - Supporting evidence: EV-044, EV-015, EV-016, EV-017, EV-045
  - Verification: FR-5 test matrix covers every role and the MMP credential, and all attempts are DENIED at both the policy and database-grant levels.
- Next step: Platform architect with DPO: Revise the role tables in Sections 19 and 21 and the FR-5 acceptance criterion.
- Decision AD-017 (25 Confirmed Decisions - Counselling): preserves. Removes admin override paths so the counselling hard wall holds.
- Decision AD-040 (FR-5): preserves. Enforces FR-5 at the credential level for admin roles too.
- Decision AD-037 (P4): preserves. Makes the P4 constraint explicit in the role tables.
- Decision AD-031 (28 Code-Generation Readiness - MMP Admin API schemas): refines. Asks for the pending Admin API auth model to exclude counselling.
- Decision AD-036 (3 Foundational Principles): preserves. Writes the principle-wins outcome into the role definitions.

### FND-013 MMP is in the request path despite NFR-4 (inline slot provisioning, PolicyEngine and AuditStore hosted in MMP)

- **risk** · internal contradiction · severity **high** · confidence 0.75 (medium) · rank 4
- Disposition: **refinement now** (also: needs testing)

NFR-4 says the MMP is not in the critical request path. However, Gateway Check 4 calls the MMP to provision missing slots inline, and Section 21 places PolicyEngine and AuditStore inside the MMP. The Validator also needs the currently published template from the MMP TemplateRegistry. As written, MMP downtime would block first-time slot access and possibly all policy evaluation and audit writes, so the NFR-4 chaos test would fail.

- Where: p.4 §2.2 (NFR-4): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical"
- Where: p.15 §15 (FR-4): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed"
- Where: p.8 §5: "AuditStore, Admin API (port 8003), and a dashboard for quality, PII, usage, cost, and warnings."
- Evidence EV-025 (doc, supports): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed" [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-046 (doc, supports): "Memory Management Plane - TemplateRegistry, NamespaceRegistry, SlotProvisioner, PolicyEngine," [doc:DOC-sit_sample_v1#p8/s5]
- Evidence EV-026 (doc, supports): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical" [doc:DOC-sit_sample_v1#p4/s2.2]
- Evidence EV-072 (inference, supports): "If policy evaluation (not cached), audit writes and slot provisioning are MMP components, every agent request depends on MMP availability, which contradicts NFR-4." [inference:EV-072] derived from EV-025, EV-046, EV-026
- Evidence EV-081 (doc, supports): "+-- PolicyEngine -- cross-slot read permission decisions" [doc:DOC-sit_sample_v1#p20/s21]
- Evidence EV-101 (doc, supports): "+-- AuditStore -- append-only log of every operation" [doc:DOC-sit_sample_v1#p20/s21]
- Evidence EV-091 (inference, supports): "A synchronous call from the Gateway to MMP provisioning, plus a per-request Policy Engine hosted in the MMP, would put the MMP on the critical path, which contradicts the premise of NFR-4." [inference:EV-091] derived from EV-025, EV-026, EV-081
- Evidence EV-113 (inference, supports): "Synchronous MMP provisioning and an AuditStore hosted in the MMP make MMP availability a dependency of agent reads and writes, which contradicts NFR-4." [inference:EV-113] derived from EV-025, EV-101
- Recommendation: In Sections 5, 15 and 21, separate the runtime Policy Engine, audit sink and published-template cache (owned by the request path) from the MMP admin service, which only edits configuration. Define Check 4 behaviour when the MMP is down (deny with a reason code, or queue provisioning). Extend the NFR-4 test to cover a first access to an unprovisioned slot and a policy-rule read while the MMP is stopped.
  - Issue: The runtime components the request path needs are placed inside the MMP.
  - Rationale: NFR-4 can hold only if the policy engine, audit sink and template cache used at runtime are deployed independently of the MMP admin service.
  - Expected benefit: NFR-4 becomes achievable and its chaos test meaningful. (objectives: NFR-4, FR-4)
  - Supporting evidence: EV-025, EV-046, EV-026, EV-072
  - Verification: NFR-4 chaos test with MMP stopped, including auto-provision and audit write cases.
- Decision AD-052 (NFR-4): refines. Makes NFR-4 achievable by separating runtime components from the MMP.
- Decision AD-039 (FR-4): refines. Defines Check 4 behaviour when the MMP is down.
- Decision AD-046 (FR-13): preserves. Keeps the audit store available independently of the MMP.
- Decision AD-042 (FR-8): preserves. Policy evaluation stays fresh on every request, served by a runtime engine.

### FND-037 A revoked token still gets learner data served from the agent backup

- **risk** · security privacy gap · severity **high** · confidence 0.70 (medium) · rank 5
- Disposition: **governance decision** (also: refinement now)

Sections 6, 15 and 25 say that when a token is REVOKED the agent keeps serving the learner from its backup memory. Revocation normally signals a compromised account, a leaver or a suspended learner. Continuing to serve personal data, including counselling backup for the counselling agent, after revocation defeats the reason for revoking. This refines the confirmed auth-token decision: the issue is what happens on revocation, not the 48-hour window.

- Where: p.8 §6 (NFR-6): "On revocation: inform the learner, serve from agent backup only, no re-authentication path is offered."
- Where: p.4 §2.2 (NFR-6): "Auth tokens shall be valid for 48 hours, with defined degraded-mode behaviour for EXPIRED and REVOKED"
- Evidence EV-098 (doc, supports): "On revocation: inform the learner, serve from agent backup only, no re-authentication path is offered." [doc:DOC-sit_sample_v1#p8/s6]
- Evidence EV-110 (inference, supports): "Revoking a token without cutting off the backup leaves learner data available to the session the revocation was meant to stop." [inference:EV-110] derived from EV-098
- Evidence EV-012 (doc, supports): "On revocation: inform the learner, serve from agent backup" [doc:DOC-sit_sample_v1#p8/s6]
- Recommendation: Change the Section 15 Check 3 REVOKED branch to deny all learner-specific memory, backup included. Serve only agent-global content and log the attempt. Update Section 6 and the Section 25 decision text to match. Add an NFR-6 test step that confirms no backup content is returned under REVOKED.
  - Issue: Under REVOKED status the agent still serves learner data from its backup.
  - Rationale: Revocation should end access to personal data. Only the learner's own non-sensitive session continuity could justify any exception, and that needs an explicit policy decision.
  - Expected benefit: NFR-6 revocation then actually stops access, and the P2 private-by-default principle is protected. (objectives: NFR-6, P2, FR-4)
  - Supporting evidence: EV-098, EV-110
  - Verification: In the token lifecycle test, revoke a token mid-session and check that the context pack contains no per-learner content.
- Next step: Information security officer: Decide whether any learner-specific memory may be served after revocation, and record the decision in Section 25.
- Decision AD-014 (25 Confirmed Decisions - Auth token window): refines. Changes only the REVOKED backup-serving behaviour and keeps the 48-hour window.
- Decision AD-054 (NFR-6): refines. Tightens the defined degraded-mode behaviour for REVOKED tokens.

### FND-041 Cached context packs keep serving after permission changes, deletions or redaction updates, and the Redis cache has no tier isolation

- **risk** · security privacy gap · severity **medium** · confidence 0.65 (medium) · rank 7
- Disposition: **refinement now**

Section 16 says policy is evaluated fresh so that rule changes take effect immediately. But a cache HIT serves a context pack that was ranked, budgeted and redacted under earlier policy, and it is invalidated only at session close or token expiry. Permission revocations, learner deletions and redaction changes are therefore not reflected for the rest of the session. The Redis cache is also not split by sensitivity tier, so HIGHLY_RESTRICTED context packs for the counselling agent may sit in a shared cache outside the separate-credential boundary of NFR-5.

- Where: p.16 §16 (FR-8): "Policy decisions are not cached - they are evaluated fresh on every request, so that a rule change takes effect immediately"
- Where: p.18 §18 (FR-10): "context pack is cached so repeated queries within a session skip PostgreSQL entirely"
- Evidence EV-102 (doc, supports): "Policy decisions are not cached - they are evaluated fresh on every request, so that a rule change takes effect immediately" [doc:DOC-sit_sample_v1#p16/s16]
- Evidence EV-023 (doc, supports): "context pack is cached so repeated queries within a session skip PostgreSQL entirely" [doc:DOC-sit_sample_v1#p18/s18]
- Evidence EV-114 (inference, supports): "The cached pack contains content that was redacted and permitted earlier, so a rule change or deletion only takes effect at the next session, which contradicts the 'immediately' claim." [inference:EV-114] derived from EV-102, EV-023
- Evidence EV-024 (doc, supports): "Rank (relevance + recency) -> Budget (token limit) -> Redact (sensitivity)" [doc:DOC-sit_sample_v1#p18/s18]
- Evidence EV-051 (doc, supports): "session duration and invalidated on session close or token expiry." [doc:DOC-sit_sample_v1#p18/s18]
- Evidence EV-074 (inference, supports): "Cached packs already reflect the redaction and recall outcome at fill time, so later rule changes or deletions only apply after session close or token expiry." [inference:EV-074] derived from EV-050, EV-051
- Recommendation: In Section 18, add cache invalidation triggered by policy changes, slot permission changes, learner deletions and slot expiry. Key cache entries by agent_id and policy version. Either exclude HIGHLY_RESTRICTED content from the shared Redis cache or use a separate cache instance with separate credentials. Add an FR-10 test step.
  - Issue: Cached context packs bypass the guarantee that policy changes and deletions take effect immediately, and the cache is not tier-isolated.
  - Rationale: FR-8 redaction, recall and deletion dimensions and NFR-5 isolation have to apply to cached copies as well.
  - Expected benefit: Policy changes and deletions take effect immediately for FR-8 and FR-15, and NFR-5 isolation covers the cache. (objectives: FR-8, FR-10, FR-15, NFR-5)
  - Supporting evidence: EV-102, EV-023, EV-114
  - Verification: FR-10 test: change a slot read permission mid-session, and the next read is a cache MISS that returns DENIED.
- Decision AD-008 (25 Confirmed Decisions - Read path): preserves. Keeps the Redis L1 read path and adds invalidation.
- Decision AD-044 (FR-10): refines. Defines the cache key and invalidation for the FR-10 cache.
- Decision AD-042 (FR-8): preserves. Policy changes then reach cached content as well.
- Decision AD-047 (FR-15): preserves. Deletions invalidate cached packs.
- Decision AD-009 (25 Confirmed Decisions - Two sensitivity tiers): preserves. Extends tier isolation to the cache.

### FND-009 Orientation template stores a persistent key as WORKING memory, which is not persisted

- **risk** · internal contradiction · severity **low** · confidence 0.60 (medium) · rank 21
- Disposition: **refinement now**

The orientation template types onboarding_progress as WORKING and says it expires at orientation end, which implies it persists across sessions. The Dispatcher, however, routes WORKING to in-memory storage with no persistence, and working memory is cleared at session close. As written, onboarding progress would be lost after every session, which undermines the orientation agent's purpose.

- Where: p.16 §17 (FR-3): "WORKING -> In-memory store (no persistence, no Kafka)"
- Where: p.10 §10 (FR-3): "Working Current session, active turn state In-memory (ephemeral) Redis / dict"
- Evidence EV-033 (doc, supports): "onboarding_progress WORKING INTERNAL Expires at orientation end" [doc:DOC-sit_sample_v1#p23/s23]
- Evidence EV-034 (doc, supports): "WORKING -> In-memory store (no persistence, no Kafka)" [doc:DOC-sit_sample_v1#p16/s17]
- Evidence EV-068 (doc, supports): "PUBLIC + INTERNAL + RESTRICTED -> memory_standard schema" [doc:DOC-sit_sample_v1#p17/s17]
- Recommendation: In Section 23 (orientation template), retype onboarding_progress as SEMANTIC or META, keeping slot-level expiry.
  - Issue: The memory type does not match the required lifetime.
  - Rationale: FR-3's type determines which store is used, so a wrong type causes data loss.
  - Expected benefit: Orientation progress survives across sessions until the orientation slot expires. (objectives: FR-3, FR-2)
  - Supporting evidence: EV-033, EV-034
  - Verification: FR-2 slot-type test: write onboarding_progress, close the session, and confirm it can be read in a new session.
- Decision AD-010 (25 Confirmed Decisions - Orientation expiry): preserves. Orientation slot expiry is unchanged; only the key's memory type changes.

## Gaps

### FND-038 Async write path: no path for writes rejected after the ACK, no dead-letter handling, and the topic is chosen before classification

- **gap** · scalability or failure mode · severity **high** · confidence 0.65 (medium) · rank 3
- Disposition: **refinement now** (also: needs testing)

The agent receives an ACK as soon as its write is enqueued. Classify, embed and validate all run later in the consumer, yet the document defines no outcome for writes the Validator rejects in strict mode. Agents and learners are never told, and 'retry automatically' would retry deterministic rejections forever unless there is a dead-letter path. The tier topic (standard or sensitive) is picked at the Gateway before Classify confirms sensitivity, so content that classification upgrades has already gone through the standard topic and the standard embedding deployment. Idempotency and per-slot ordering under retry are also not specified.

- Where: p.17 §18 (FR-9): "failed writes queue and retry automatically; multiple independent consumers (audit, embedding, SIS sync) read the same event stream"
- Where: p.4 §2.1 (FR-9): "processed asynchronously by a background consumer performing classify → embed → validate → route →"
- Evidence EV-099 (doc, supports): "failed writes queue and retry automatically; multiple independent consumers (audit, embedding, SIS sync) read the same event stream" [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-047 (doc, supports): "processed asynchronously by a background consumer performing classify → embed → validate → route →" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-111 (inference, supports): "Validation runs after the ACK and there is no dead-letter or notification path, so rejected writes are either lost silently or retried without end. Embedding also runs before validation, so rejected content is still sent to the embedding service." [inference:EV-111] derived from EV-099, EV-047
- Evidence EV-073 (inference, supports): "A rejection produced after an immediate ACK cannot reach the agent unless a callback or status channel exists, and unconditional retry of a deterministic validation failure loops forever." [inference:EV-073] derived from EV-047, EV-048, EV-049
- Evidence EV-095 (inference, supports): "Because topic selection comes before classification, and validation comes after embedding and acknowledgement, a misdeclared write can transit the standard tier and be embedded before it is rejected, with no defined way to tell the agent." [inference:EV-095] derived from EV-021, EV-047
- Evidence EV-048 (doc, supports): "The Validator shall reject (strict mode) or warn-and-log (lenient mode) any write containing a key not" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-021 (doc, supports): "read the same event stream; separate topics per sensitivity tier keep HIGHLY_RESTRICTED" [doc:DOC-sit_sample_v1#p17/s18]
- Recommendation: In Section 18: (1) split failures into transient ones (retry with backoff and a maximum attempt count) and deterministic ones (validation or policy rejection, sent straight to a per-tier dead-letter topic, audited, and shown on the MMP dashboard); (2) run validation before embedding; (3) require a client-side sensitivity declaration at the Gateway, and have a standard consumer that classifies content as HIGHLY_RESTRICTED quarantine it rather than store it; (4) define an idempotency key and per-learner/slot partitioning.
  - Issue: Section 18 has no failure semantics for writes that are rejected after the ACK, and topic routing comes before classification.
  - Rationale: Writes lost silently undermine P1, because the namespace stops being authoritative. Misrouted sensitive content undermines P4 and NFR-5.
  - Expected benefit: Writes stay reliable under FR-9 and tier isolation holds in transit under NFR-5. (objectives: FR-9, FR-11, NFR-5, P1)
  - Supporting evidence: EV-099, EV-047, EV-111
  - Verification: Add FR-9 and FR-11 test cases: a strict-mode rejection appears in the dead-letter topic and the audit log exactly once, and a replayed message does not create a duplicate record.
- Decision AD-007 (25 Confirmed Decisions - Write path): preserves. Keeps the async Kafka write path and adds failure semantics.
- Decision AD-043 (FR-9): refines. Moves validation before embedding in the FR-9 order.
- Decision AD-011 (25 Confirmed Decisions - Template strictness / Unknown key in dev): preserves. Makes strict-mode rejection observable.
- Decision AD-009 (25 Confirmed Decisions - Two sensitivity tiers): preserves. Keeps tier isolation in transit.
- Decision AD-051 (NFR-3): preserves. Synchronous checks before the ACK are cheap and keep writes non-blocking on consumer work.

### FND-018 DDL rated 'complete' but lacks columns that other sections rely on

- **gap** · internal contradiction · severity **medium** · confidence 0.75 (medium) · rank 10
- Disposition: **refinement now**

Section 28 calls the DDL concrete and complete. But the embedded flag and BM25 fallback in Section 17 have no column or full-text index. memory_events and memory_documents have no pii, retention or expires_at columns, which NFR-7 needs for per-slot retention and PII flagging and FR-15 needs for deletability. The consent field named for meta-memory in Section 10 has no column, and no table records escalation target or status, which FR-7 and Section 19 need. Code generated from this DDL would not support those requirements.

- Where: p.29 §28: "Nothing further needed - DDL is concrete and complete (Section"
- Where: p.16 §17: "Fall back to BM25 keyword search for retrieval"
- Where: p.4 §2.2 (NFR-7): "All operations on personal data shall be logged; retention rules shall be enforceable per slot; PII-bearing"
- Evidence EV-057 (doc, supports): "Nothing further needed - DDL is concrete and complete (Section" [doc:DOC-sit_sample_v1#p29/s28]
- Evidence EV-058 (doc, supports): "Fall back to BM25 keyword search for retrieval" [doc:DOC-sit_sample_v1#p16/s17]
- Evidence EV-076 (inference, supports): "The memory_vectors DDL has no embedded column or tsvector index, and memory_events and memory_documents have no pii, retention or expires_at columns, so the fallback and NFR-7 cannot be implemented from the DDL." [inference:EV-076] derived from EV-057, EV-058
- Evidence EV-096 (inference, supports): "The memory_vectors DDL defines no tsvector/full-text index and no embedded column, so the BM25 fallback has no schema support and depends on an unconfirmed PostgreSQL capability." [inference:EV-096] derived from EV-058
- Recommendation: In Section 11, add embedded BOOLEAN and a tsvector/GIN index to memory_vectors; add pii, retention, expires_at and deletable columns to all three tables; add escalation target and status fields; add consent to memory_documents. Downgrade the Section 28 rating until done.
  - Issue: The schema is missing fields that the requirements depend on.
  - Rationale: The readiness rating invites direct code generation from incomplete DDL.
  - Expected benefit: NFR-7, FR-15, FR-7 and the embedder fallback become implementable. (objectives: NFR-7, FR-15, FR-7)
  - Supporting evidence: EV-057, EV-058, EV-076
  - Verification: Extend the NFR-7 schema scan to cover all three tables; add an embedder-fallback test that retrieves via BM25.
- Decision AD-055 (NFR-7): refines. Adds the columns that per-slot retention and PII flagging need.
- Decision AD-047 (FR-15): preserves. Supports deletability with schema fields.
- Decision AD-041 (FR-7): preserves. Adds escalation target and status fields.

### FND-019 Escalation access needs record-level targeting that slot-level Gateway checks do not provide; template missing

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.65 (medium) · rank 12
- Disposition: **refinement now**

FR-7 allows reads by the named target-domain agent and denies the triggering agent. That is a per-record decision based on fields such as target and author. Gateway Check 5, however, is a slot-level read/write permission. The escalations template, which would hold the target and status, is not written out and is dismissed as 'mechanical by analogy'. The document also does not define what happens if the triggering agent is itself the target domain.

- Where: p.4 §2.1 (FR-7): "Any registered agent may write to escalations/<id>/. Only human reviewers and the named target-domain"
- Where: p.29 §28: "escalations, industry_attachment) follow the same pattern but are"
- Where: p.19 §19 (FR-7): "Feedback loop blocked: the agent that triggered the escalation cannot read it back."
- Evidence EV-059 (doc, supports): "Any registered agent may write to escalations/<id>/. Only human reviewers and the named target-domain" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-060 (doc, supports): "Read permission != Write permission (checked separately)" [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-077 (inference, supports): "Slot-level permissions cannot express 'readable by the agent named in this record, not by its author', so FR-7 needs record-level attributes and logic." [inference:EV-077] derived from EV-059, EV-060
- Recommendation: Add an escalations template in Section 23 (target_domain, triggering_agent_id, status, created_at). Add a record-level rule to Check 5 or the Policy Engine. Define the self-target case and RESOLVED expiry. Extend the FR-7 test to a non-target third agent.
  - Issue: Escalation read control and the escalation schema are unspecified.
  - Rationale: FR-7 is a named novel capability and cannot be built from slot-level checks alone.
  - Expected benefit: FR-7 becomes implementable and its lifecycle test meaningful. (objectives: FR-7)
  - Supporting evidence: EV-059, EV-060, EV-077
  - Verification: FR-7 test: the triggering agent, a non-target agent and the target agent get DENY, DENY and ALLOW respectively.
- Decision AD-019 (25 Confirmed Decisions - Escalations): preserves. Implements the confirmed escalation semantics.
- Decision AD-041 (FR-7): refines. Adds the record-level rule that FR-7 needs.

### FND-043 No backup/DR, availability targets or operational monitoring for the authoritative store and pipeline

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.65 (medium) · rank 13
- Disposition: **governance decision** (also: refinement now) · already acknowledged in the document

The learner namespace is authoritative (P1), yet the document gives no PostgreSQL backup, high availability, RPO/RTO or availability SLO. It also sets no alerting for Kafka consumer lag, dead-letter growth or SIS webhook failures. SIS integration failure handling is acknowledged in the backlog. This review adds that DR and monitoring need an owner and targets before build, and that backups have to be reconciled with FR-15 deletion.

- Where: p.26 §26: "MMP in detail - template versioning conflict resolution, SIS integration failure handling."
- Where: p.6 §3: "Learner namespace is authoritative - the agent's copy is backup only. Conflicts are resolved in favour"
- Evidence EV-105 (doc, supports): "MMP in detail - template versioning conflict resolution, SIS integration failure handling." [doc:DOC-sit_sample_v1#p26/s26]
- Evidence EV-106 (doc, supports): "Learner namespace is authoritative - the agent's copy is backup only. Conflicts are resolved in favour" [doc:DOC-sit_sample_v1#p6/s3]
- Evidence EV-116 (inference, supports): "An authoritative store with no stated backup, RPO/RTO or pipeline monitoring has no defined recovery from data loss or a stalled consumer." [inference:EV-116] derived from EV-105, EV-106
- Recommendation: Add an Operations section setting out: PostgreSQL HA and point-in-time-restore with stated RPO/RTO; how backup retention handles learner deletion; alerts on consumer lag, dead-letter count, unembedded backlog and SIS webhook failures; and a named on-call owner. Add matching NFR rows and Section 27 criteria.
  - Issue: Recovery and operational monitoring are not specified.
  - Rationale: Losing the authoritative namespace, or a stalled consumer going unnoticed, would break P1 and FR-9 for every agent.
  - Expected benefit: Recovery is defined for P1/FR-9, and backups stay consistent with FR-15. (objectives: P1, FR-9, FR-12, FR-15)
  - Supporting evidence: EV-105, EV-106, EV-116
  - Verification: Restore drill meets the stated RTO, and a simulated consumer stall raises an alert within the agreed threshold.
- Next step: Platform operations lead: Propose RPO/RTO and availability targets for approval, and assign on-call ownership.
- Decision AD-027 (26 Pending Backlog - MMP in detail): refines. Adds monitoring and recovery around the pending SIS failure handling.
- Decision AD-047 (FR-15): preserves. Database backups must respect deletion.

### FND-022 Mutable UPN used as primary key with no rename process; SIS lifecycle events incomplete

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.60 (medium) · rank 17
- Disposition: **refinement now** (also: governance decision)

Section 6 makes the UPN the primary key while noting that only entra_object_id is immutable 'even if the UPN changes'. No requirement covers re-keying records, audit entries and agent backups when a UPN changes. FR-12 also lists only five SIS events: there is no withdrawal from SIT, leave of absence, programme transfer or term-end trigger. Yet Section 20 ties core/ retention to 'while at SIT' and term-end compaction to the end of term.

- Where: p.8 §6: "learner_id UPN: a103605@singaporetech.edu.sg Primary key used everywhere in the platform."
- Where: p.4 §2.1 (FR-12): "SIS events - registration, programme enrolment, module registration, module withdrawal, graduation -"
- Where: p.19 §20: "core/ identity Permanent Never expires while the learner is at SIT"
- Evidence EV-064 (doc, supports): "changes even if the UPN changes." [doc:DOC-sit_sample_v1#p8/s6]
- Evidence EV-065 (doc, supports): "core/ identity Permanent Never expires while the learner is at SIT" [doc:DOC-sit_sample_v1#p19/s20]
- Evidence EV-061 (doc, supports): "Learner registration -> create_namespace() + provision core/ + orientation/" [doc:DOC-sit_sample_v1#p21/s21]
- Recommendation: This refines the confirmed learner_id decision rather than challenging it. Add a requirement for UPN-change handling: a lookup keyed on entra_object_id and a re-key job with audit. Extend FR-12 with SIT withdrawal/termination, leave of absence, programme transfer and term-end events, each with a namespace action, and add them to the FR-12 test.
  - Issue: There is no identity-change process and no lifecycle events for learners who leave or pause.
  - Rationale: Without them, records are orphaned or kept indefinitely, which undermines NFR-7 retention enforcement.
  - Expected benefit: FR-12 and NFR-7 cover the full learner lifecycle. (objectives: FR-12, NFR-7)
  - Supporting evidence: EV-064, EV-065
  - Verification: FR-12 simulation includes the new events and a UPN rename.
- Next step: Platform architect with SIS integration owner: Enumerate SIS lifecycle events and decide how UPN changes are handled.
- Decision AD-001 (25 Confirmed Decisions - learner_id / Identity fields): refines. Adds UPN-change handling and keeps UPN as learner_id.
- Decision AD-045 (FR-12): refines. Extends the list of SIS lifecycle events.
- Decision AD-020 (26 Pending Backlog - Non-SIT / lifelong learner identity): preserves. Non-SIT identity stays deferred.

## Ambiguities

### FND-017 NFR-3 write-latency bound ignores the synchronous Gateway/policy step, and its budget is undefined

- **ambiguity** · acceptance criterion cannot validate · severity **medium** · confidence 0.70 (medium) · rank 15
- Disposition: **refinement now** (also: needs testing)

NFR-3 limits the agent-visible write latency to the time it takes to enqueue the write. But Section 18 runs synchronous auth and a fresh, uncached 7-dimension policy evaluation before the enqueue, so the bound cannot hold as written. The FR-9 and NFR-3 acceptance criteria use an undefined 'enqueue time budget' and an 'e.g. ±10%' tolerance, so neither gives a concrete pass/fail threshold. NFR-2's 'normal load' is likewise undefined in its benchmark.

- Where: p.4 §2.2 (NFR-3): "The agent-visible latency added by a memory write shall not exceed the time to enqueue the write to the"
- Where: p.27 §27.1 (FR-9): "Under load, the p99 agent-visible latency for a write call is within the Kafka"
- Where: p.27 §27.2 (NFR-3): "Agent-observed write latency tracks Kafka enqueue time within an agreed"
- Evidence EV-055 (doc, supports): "Memory Access Gateway (auth + policy check -- synchronous)" [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-056 (doc, supports): "The agent-visible latency added by a memory write shall not exceed the time to enqueue the write to the" [doc:DOC-sit_sample_v1#p4/s2.2]
- Recommendation: Restate NFR-3 as 'Gateway + policy + enqueue ≤ X ms p99 and independent of consumer processing', set X and the load profile (requests/s, concurrent sessions), and define 'normal load' for NFR-2. Update the FR-9, NFR-2 and NFR-3 criteria with these numbers.
  - Issue: The latency requirement excludes a mandatory synchronous step and has no numeric threshold.
  - Rationale: A requirement that cannot hold by construction, with a non-numeric criterion, cannot be verified.
  - Expected benefit: NFR-3, FR-9 and NFR-2 become testable. (objectives: NFR-2, NFR-3, FR-9)
  - Supporting evidence: EV-055, EV-056
  - Verification: Load test at the defined profile with consumers throttled reports a numeric p99 against X.
- Next step: Platform architect: Set numeric latency budgets and the load profile in Sections 2.2 and 27.
- Decision AD-051 (NFR-3): refines. Restates the NFR-3 bound to include the synchronous Gateway step.
- Decision AD-050 (NFR-2): refines. Defines 'normal load' for NFR-2.

### FND-023 Audit 'exactly one entry per operation' conflicts with double logging of async writes

- **ambiguity** · acceptance criterion cannot validate · severity **low** · confidence 0.60 (medium) · rank 22
- Disposition: **refinement now**

Section 17 logs a write at Kafka enqueue, and the consumer writes a second audit log after storage. The FR-13 test requires exactly one entry per operation. This makes it unclear whether a write is one operation or two, and if audit runs last in the consumer, a crash after storage could leave a stored record with no audit entry.

- Where: p.27 §27.1 (FR-13): "log contains exactly one entry per operation with all required fields"
- Where: p.17 §17 (FR-13): "Logs every operation. Non-negotiable for PDPA compliance (implements FR-13)."
- Evidence EV-066 (doc, supports): "Every write (including async Kafka enqueue)" [doc:DOC-sit_sample_v1#p17/s17]
- Evidence EV-067 (doc, supports): "log contains exactly one entry per operation with all required fields" [doc:DOC-sit_sample_v1#p27/s27.1]
- Recommendation: Define write audit as linked ENQUEUED and COMMITTED/REJECTED entries sharing a write_id. Require the audit entry to be written in the same transaction as storage (or an outbox). Update the FR-13 criterion accordingly.
  - Issue: The audit granularity for async writes is ambiguous, and storage and audit are not atomic.
  - Rationale: A completeness test needs a precise definition of what counts as an operation.
  - Expected benefit: FR-13 is testable and audit gaps are prevented. (objectives: FR-13, P7)
  - Supporting evidence: EV-066, EV-067
  - Verification: FR-13 test with an injected consumer crash shows no committed record without a COMMITTED audit entry.
- Decision AD-046 (FR-13): refines. Defines audit granularity and atomicity for async writes.
- Decision AD-033 (P7 / PDPA): preserves. Keeps the audit-everything rule.

## Unresolved assumptions

### FND-030 PDPA compliance is asserted but PDPA sign-off and retention period are still pending

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.60 (medium) · rank 8
- Disposition: **governance decision** (also: refinement now) · already acknowledged in the document

The design says many times that audit trails are 'required for PDPA' and are 'retained per PDPA requirements', and it holds escalation content in the audit log after the slot itself expires. Yet the Auditor's retention period and its PDPA alignment sign-off are still in the Pending Backlog. Which PDPA obligation applies (for example retention limitation versus indefinite append-only logs keyed by learner_id) has not been established. The review adds that FR-13, FR-15 and the escalation lifecycle are treated as settled while their legal basis is still open.

- Where: p.17 §17 (FR-13): "Audit logs are append-only. Never modified. Retained per PDPA requirements."
- Where: p.26 §26: "Memory Router Component 5 (Auditor) - log schema detail, retention period, PDPA alignment sign-off."
- Where: p.19 §19 (FR-7): "Retention: retained in the audit log after RESOLVED status; the slot itself expires."
- Evidence EV-084 (doc, supports): "Audit logs are append-only. Never modified. Retained per PDPA requirements." [doc:DOC-sit_sample_v1#p17/s17]
- Evidence EV-085 (doc, supports): "Memory Router Component 5 (Auditor) - log schema detail, retention period, PDPA alignment sign-off." [doc:DOC-sit_sample_v1#p26/s26]
- Evidence EV-093 (inference, supports): "Compliance is asserted while the retention period and the PDPA sign-off are both open, so the audit and escalation designs rest on an unconfirmed legal interpretation." [inference:EV-093] derived from EV-084, EV-085
- Recommendation: Have the DPO decide the audit retention period, whether escalation content (as opposed to metadata) may stay in the audit log, and how learner deletion requests affect audit and agent-backup copies. Record the outcomes in Sections 17, 19 and 20, and replace 'retained per PDPA requirements' with the concrete period.
  - Issue: PDPA claims rest on a sign-off that has not happened, and no retention period is defined for append-only audit logs that contain personal data.
  - Rationale: Append-only, never-modified logs with no retention limit, which also hold escalation content, may conflict with retention or deletion obligations once the DPO has ruled.
  - Expected benefit: NFR-7 and FR-13 become legally grounded, and the risk of rework after the DPO's review is avoided. (objectives: NFR-7, FR-13, FR-15)
  - Supporting evidence: EV-084, EV-085, EV-093
  - Verification: The DPO sign-off is recorded, and NFR-7 tests verify that audit-log expiry follows the defined retention period.
- Next step: Data Protection Officer: Issue a PDPA interpretation covering audit-log retention, escalation content and the deletion scope, before the Auditor is built.
- Decision AD-023 (26 Pending Backlog - Auditor): refines. Asks for the pending Auditor retention and PDPA sign-off to be closed before build.
- Decision AD-033 (P7 / PDPA): preserves. Keeps the audit-everything constraint.
- Decision AD-046 (FR-13): preserves. The audit store stays append-only, with a defined retention period.

### FND-031 Write path is marked confirmed and 'Ready' while Event Hubs and retry behaviour are still pending

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.65 (medium) · rank 14
- Disposition: **needs investigation** (also: refinement now) · already acknowledged in the document

Section 25 lists 'Async via Kafka (Azure Event Hubs)' as confirmed, and Section 28 rates the write path 'Ready'. Section 26, however, still has confirming Event Hubs as an open item. Section 18 also claims failed writes 'queue and retry automatically', but no retry, poison-message or dead-letter mechanism is specified, and broker-level capabilities (consumer groups, retention, ordering per learner) are assumed rather than checked. The review adds that FR-9's guarantee of durability after acknowledgement depends on these unconfirmed behaviours.

- Where: p.26 §26: "Kafka vs Azure Event Hubs - confirm Azure Event Hubs as the managed Kafka-API alternative."
- Where: p.17 §18 (FR-9): "overwhelm the store; failed writes queue and retry automatically"
- Where: p.25 §25: "Write path Async via Kafka (Azure Event Hubs)"
- Evidence EV-032 (doc, supports): "Kafka vs Azure Event Hubs - confirm Azure Event Hubs as the managed Kafka-API alternative." [doc:DOC-sit_sample_v1#p26/s26]
- Evidence EV-086 (doc, supports): "overwhelm the store; failed writes queue and retry automatically" [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-094 (inference, supports): "A confirmed decision and a 'Ready' rating depend on a broker choice that is still pending, and on automatic retry behaviour that no component is specified to provide." [inference:EV-094] derived from EV-032, EV-086
- Evidence EV-031 (doc, supports): "Write path Async via Kafka (Azure Event Hubs)" [doc:DOC-sit_sample_v1#p25/s25]
- Recommendation: Close the Event Hubs backlog item before Phase 4/5 build. In Section 18, specify the consumer retry policy, dead-letter topic, idempotency key (memory_id), partition key (learner_id) for ordering, and the broker retention tier. Downgrade the Section 28 write-path rating to 'Mostly ready' until this is done.
  - Issue: The broker choice and the retry semantics are unconfirmed, but the write path is treated as ready to build.
  - Rationale: Writes are acknowledged before they are processed, so lost or poisoned messages mean silent data loss under FR-9.
  - Expected benefit: FR-9 durability and NFR-3 non-blocking writes rest on verified broker behaviour. (objectives: FR-9, NFR-3)
  - Supporting evidence: EV-032, EV-086, EV-094
  - Verification: A fault-injection test in which the consumer fails mid-batch shows every acknowledged write is either stored once or sits in the DLQ with an audit entry.
- Next step: Platform engineering lead: Confirm Event Hubs tier and Kafka-API feature support, and specify retry/DLQ semantics.
- Decision AD-007 (25 Confirmed Decisions - Write path): preserves. Keeps the async write path.
- Decision AD-028 (26 Pending Backlog - Kafka vs Azure Event Hubs): refines. Asks for the pending Event Hubs choice to be closed before Phase 4/5.
- Decision AD-029 (26 Pending Backlog - Redis): refines. Marks the dependent read-path decision as conditional on the pending Redis choice.

### FND-044 Anonymisation standard, audit retention and PDPA sign-off have no accountable decision

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.60 (medium) · rank 18
- Disposition: **governance decision** · already acknowledged in the document

Cross-learner and cohort patterns are said to be 'anonymised' and are readable by all agents. No anonymisation method or minimum group size is defined, and RESTRICTED data (at-risk flags, financial aid, accessibility) is excluded only implicitly. Audit retention and PDPA alignment sign-off are acknowledged as pending. This review adds that both should be decided by the DPO before agents start writing pattern data or audit logs build up, because both decisions affect what gets stored.

- Where: p.26 §26 (FR-13): "Memory Router Component 5 (Auditor) - log schema detail, retention period, PDPA alignment sign-off."
- Where: p.6 §3: "Private by default - memory is private to the learner, shared by exception, anonymised for service"
- Evidence EV-085 (doc, supports): "Memory Router Component 5 (Auditor) - log schema detail, retention period, PDPA alignment sign-off." [doc:DOC-sit_sample_v1#p26/s26]
- Evidence EV-107 (doc, supports): "Private by default - memory is private to the learner, shared by exception, anonymised for service" [doc:DOC-sit_sample_v1#p6/s3]
- Evidence EV-117 (inference, supports): "With no anonymisation method or minimum group size, cohort-level patterns readable by every agent could re-identify learners in small cohorts." [inference:EV-117] derived from EV-107
- Recommendation: Add to Section 19 a defined anonymisation rule: which sensitivity tiers are excluded, a minimum aggregation group size, and an owner. Have the DPO set the audit retention period in Section 17 before Build Phase 4. Add a test that cohort aggregates below the minimum group size are suppressed.
  - Issue: Anonymisation and audit retention are assumed compliant, with no decision owner.
  - Rationale: P2 and P7 compliance depend on these choices.
  - Expected benefit: The P2 and FR-13/NFR-7 PDPA obligations rest on signed-off rules. (objectives: P2, P7, FR-13, NFR-7)
  - Supporting evidence: EV-085, EV-107, EV-117
  - Verification: DPO sign-off is recorded in Section 25, and the aggregate suppression test passes.
- Next step: Data Protection Officer: Approve the anonymisation rule and the audit retention period.
- Decision AD-023 (26 Pending Backlog - Auditor): refines. Assigns the audit retention decision to the DPO.
- Decision AD-021 (26 Pending Backlog - Cohort namespace design): refines. The anonymisation rule constrains the pending cohort design.

## Validation needs

### FND-026 Filtered HNSW search-space claim is unverified and drives NFR-2

- **validation need** · unsupported or incorrect claim · severity **high** · confidence 0.65 (medium) · rank 6
- Disposition: **needs prototyping** (also: needs investigation)

Section 12 says that because queries filter by learner_id + slot_path, the effective search space is only 500-800 vectors. Section 11, however, defines a single global HNSW index over all ~9.5M rows, plus a separate B-tree on (learner_id, slot_path). With a global approximate index, the WHERE filter does not obviously shrink the graph traversal. Depending on the query plan, the database either scans the graph and filters afterwards (which risks returning too few or no results for one learner out of 15,000) or uses the B-tree and does an exact scan (which makes the 80 GB HNSW index largely redundant). NFR-2's 5-15 ms target and the retrieval quality of every context pack depend on which of these happens, and the document does not establish it.

- Where: p.12 §12: "the effective search space per query is 500-800 vectors, not 9.5 million."
- Where: p.11 §11: "CREATE INDEX ON memory_vectors USING hnsw (embedding vector_cosine_ops)"
- Where: p.4 §2.2 (NFR-2): "Filtered vector similarity queries (scoped by learner_id and slot_path) shall return within 5-15 ms"
- Evidence EV-078 (doc, supports): "the effective search space per query is 500-800 vectors, not 9.5 million." [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-030 (doc, supports): "CREATE INDEX ON memory_vectors USING hnsw (embedding vector_cosine_ops)" [doc:DOC-sit_sample_v1#p11/s11]
- Evidence EV-089 (inference, supports): "A single unpartitioned HNSW index built over all learners cannot, by itself, restrict traversal to one learner's ~600 vectors. The claimed search-space reduction therefore depends on planner behaviour and pgvector filtering features that the design neither specifies nor verifies." [inference:EV-089] derived from EV-078, EV-030
- Evidence EV-002 (external, supports): "current indices have high search latency or low recall" [https://doi.org/10.1145/3543507.3583552]
- Evidence EV-039 (inference, supports): "A single global HNSW index plus a separate B-tree does not by itself guarantee that ANN search is confined to the filtered rows, so the 500-800 figure is an assumption about query planning, not a property of the schema." [inference:EV-039] derived from EV-029, EV-030
- Evidence EV-104 (doc, contrary): "p95 filtered similarity query latency ≤ 15 ms, p50 ≤ 10 ms, measured against" [doc:DOC-sit_sample_v1#p27/s27.2]
- Recommendation: In Sections 11-12, state the intended filtered-query strategy explicitly. Options are: exact scan via the (learner_id, slot_path) index; partitioning memory_vectors by learner hash or slot; or a pgvector version with iterative/filtered HNSW scans and a defined ef_search. Prototype on the synthetic 9.5M dataset, and measure both latency and recall@k against an exact baseline.
  - Issue: The claim about filtered vector search on a global HNSW index is unverified, and it underpins NFR-2 and recall quality.
  - Rationale: If the HNSW index filters after the search, highly selective per-learner filters can return incomplete results. If the planner uses exact scans instead, the HNSW index and its RAM cost bring no benefit.
  - Expected benefit: NFR-2 latency is met with correct recall, and the Section 12 sizing reflects the indexes actually used. (objectives: NFR-2, NFR-1, FR-10)
  - Supporting evidence: EV-078, EV-030, EV-089
  - Verification: Extend the NFR-2 benchmark to report recall@k against an exact scan, together with EXPLAIN plans, for per-learner filtered queries.
- Next step: Platform data architect: Build a 9.5M-vector pgvector prototype on the target Azure PostgreSQL version and benchmark filtered query plans for latency and recall.
- Decision AD-004 (25 Confirmed Decisions - HNSW params): preserves. Keeps the HNSW parameters and verifies the filtered-query strategy.
- Decision AD-002 (25 Confirmed Decisions - Vector store): preserves. Stays on pgvector.
- Decision AD-050 (NFR-2): refines. Adds recall@k to the NFR-2 latency validation.
- Decision AD-049 (NFR-1): preserves. Benchmarks run at the NFR-1 scale.

### FND-027 Vector sizing, RAM fit and growth ceiling do not add up

- **validation need** · unsupported or incorrect claim · severity **medium** · confidence 0.70 (medium) · rank 9
- Disposition: **needs testing** (also: refinement now)

Section 12 gives ~57 GB of raw vectors and ~80 GB of HNSW index on a 128 GB RAM SKU, and claims an in-RAM index and a growth ceiling of 30-40M vectors. Together, 57 GB and 80 GB already exceed 128 GB before counting content/TOAST, the event and document tables, and PostgreSQL's own memory. At 30-40M vectors, the index alone would be several times the RAM. In addition, the per-learner breakdown adds up to about 340 vectors, not the ~600 used for the total. The SKU decision, the latency claim and NFR-1's 'no engine change' all rest on these figures.

- Where: p.12 §12: "Growth ceiling before degradation ~30-40M vectors (~50,000-60,000 learners)"
- Where: p.12 §12: "Azure SKU required Memory Optimised, 16 vCores, 128 GB RAM"
- Where: p.12 §12: "Per-learner breakdown (~600 vectors across a full degree): core/identity 10, advisory 15, modules (6 active × 20)"
- Evidence EV-079 (doc, supports): "Growth ceiling before degradation ~30-40M vectors (~50,000-60,000 learners)" [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-080 (doc, supports): "Azure SKU required Memory Optimised, 16 vCores, 128 GB RAM" [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-052 (doc, supports): "Per-learner breakdown (~600 vectors across a full degree): core/identity 10, advisory 15, modules (6 active × 20)" [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-090 (inference, supports): "9.5M × 1536 × 4 bytes ≈ 58 GB raw, plus ~80 GB of index, is ≈ 138 GB, which is more than 128 GB of RAM. At 30-40M vectors the index alone would be roughly 250-340 GB. The listed per-learner items sum to about 340 vectors, not 600." [inference:EV-090] derived from EV-079, EV-080, EV-052
- Evidence EV-075 (inference, supports): "10+15+120+60+30+30+20+30+5+20 = 340, leaving ~260 of the stated ~600 per learner unexplained; 57 GB + 80 GB = 137 GB if additive, which exceeds 128 GB RAM." [inference:EV-075] derived from EV-052, EV-053, EV-054
- Evidence EV-103 (doc, supports): "Raw vector storage (1536-dim, 9.5M) ~57 GB" [doc:DOC-sit_sample_v1#p12/s12]
- Recommendation: Recompute Section 12 from first principles. Use a consistent per-learner count, counting only SEMANTIC/PROCEDURAL keys, because episodic writes are not vector-indexed (Section 17). State whether 80 GB is the total index or overhead on top of the raw vectors, and include shared_buffers and working-set assumptions. Restate the growth ceiling as 'to be measured', or derive it. Consider halfvec or reduced dimensions if RAM fit is required.
  - Issue: The capacity figures are internally inconsistent, and the in-RAM index assumption is not supported at the stated SKU.
  - Rationale: Under-sizing RAM means index pages are read from disk, which affects NFR-2. An overstated growth ceiling misleads capacity planning under NFR-1.
  - Expected benefit: A defensible SKU choice and a correct growth ceiling for NFR-1, NFR-2 and NFR-10. (objectives: NFR-1, NFR-2, NFR-10)
  - Supporting evidence: EV-079, EV-080, EV-052, EV-090
  - Verification: Measure the actual table and index sizes (pg_relation_size) on the NFR-1 synthetic dataset and compare the cache hit ratio with the RAM available.
- Next step: Platform data architect: Recalculate sizing and confirm it with measured relation sizes from the load-test dataset.
- Decision AD-003 (25 Confirmed Decisions - Azure SKU): preserves. Verifies the SKU by measurement rather than challenging it; the only evidence is in-document arithmetic.
- Decision AD-005 (25 Confirmed Decisions - Vector count estimate): refines. Asks for the per-learner vector breakdown to be reconciled.
- Decision AD-034 (NFR-10): preserves. The sizing feeds the cost constraint.
- Decision AD-049 (NFR-1): preserves. Measures at the NFR-1 scale.

### FND-006 Policy Engine combination logic is unspecified and the FR-8 test assumes every dimension yields DENY

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.70 (medium) · rank 11
- Disposition: **refinement now** (also: needs testing) · already acknowledged in the document

Section 28 already acknowledges that the decision algorithm across the seven dimensions is unspecified. This review adds that the FR-8 acceptance test expects each dimension to produce a 'DENY attributable to that dimension'. Redaction yields REDACT, and Retention and Deletion act over time rather than per request. The test therefore cannot validate the dimensions as designed, and it does not test precedence when dimensions disagree, which is the part that is actually missing.

- Where: p.27 §27.1 (FR-8): "A test matrix exercises all seven dimensions independently (one violating"
- Where: p.29 §28 (FR-8): "Each dimension is named with a one-line question (Section 16), but"
- Evidence EV-027 (doc, supports): "condition per dimension) and confirms each produces a DENY attributable to" [doc:DOC-sit_sample_v1#p27/s27.1]
- Evidence EV-028 (doc, supports): "Redaction Should part of the memory be masked before serving to this agent?" [doc:DOC-sit_sample_v1#p15/s16]
- Evidence EV-063 (doc, supports): "the decision algorithm - how the seven dimensions combine into a" [doc:DOC-sit_sample_v1#p29/s28]
- Recommendation: When writing the Section 28 decision table, define the outcome type per dimension (DENY, REDACT, EXPIRE, PURGE) and a precedence order. Rewrite the FR-8 criterion to assert the expected outcome per dimension plus at least one case per conflicting pair.
  - Issue: The FR-8 acceptance criterion does not match the per-dimension outcomes and omits precedence.
  - Rationale: The decision table that Section 28 already calls for should also drive the FR-8 test.
  - Expected benefit: FR-8 becomes verifiable, and Build Phase 3 has a concrete specification. (objectives: FR-8)
  - Supporting evidence: EV-027, EV-028
  - Verification: Review the FR-8 test matrix against the decision table: every cell has an expected outcome.
- Next step: Policy Engine lead: Produce the decision table before Build Phase 3 and revise the FR-8 acceptance row.
- Decision AD-030 (28 Code-Generation Readiness - Policy Engine decision table): refines. Ties the pending decision table to the FR-8 test.
- Decision AD-042 (FR-8): refines. Corrects the FR-8 acceptance outcomes for each dimension.

### FND-029 48-hour Entra ID token validity is assumed, not shown to be configurable

- **validation need** · external constraint violation · severity **medium** · confidence 0.55 (medium) · rank 16
- Disposition: **needs investigation** (also: refinement now)

Sections 6 and 15, NFR-6 and the confirmed decisions all assume that Entra ID OAuth tokens are valid for 48 hours. The document does not say whether this means the access token, the refresh token, or a platform-issued session token. It also does not say how an Entra ID-issued token could be held at a 48-hour lifetime, or how REVOKED is detected before expiry. Whether Entra ID permits a 48-hour access-token lifetime is unverified here. If it does not, both the NFR-6 test (ACTIVE until T+48h) and the degraded-mode design built on it are invalid.

- Where: p.8 §6: "Authentication is OAuth 2.0 via Entra ID. Tokens are valid for 48 hours."
- Where: p.4 §2.2 (NFR-6): "Auth tokens shall be valid for 48 hours, with defined degraded-mode behaviour for EXPIRED and REVOKED"
- Where: p.27 §27.2 (NFR-6): "Tokens issued at T are ACTIVE until T+48h, then transition to EXPIRED; a"
- Evidence EV-082 (doc, supports): "Authentication is OAuth 2.0 via Entra ID. Tokens are valid for 48 hours." [doc:DOC-sit_sample_v1#p8/s6]
- Evidence EV-083 (doc, supports): "Tokens issued at T are ACTIVE until T+48h, then transition to EXPIRED; a" [doc:DOC-sit_sample_v1#p27/s27.2]
- Evidence EV-092 (inference, supports): "The design treats a 48-hour lifetime as an inherent property of Entra ID tokens without naming the token type or the configuration that achieves it, so both NFR-6 and its test rest on an unverified identity-platform capability." [inference:EV-092] derived from EV-082, EV-083
- Recommendation: In Sections 6 and 15, name the token whose 48-hour lifetime is meant (Entra access token, refresh token, or a platform session token minted after Entra login). Cite the Entra configuration that supports it, and define how revocation is detected (for example introspection or a revocation list). Update the NFR-6 acceptance criterion to match.
  - Issue: The 48-hour token window depends on an identity-platform lifetime setting that has not been verified.
  - Rationale: NFR-6, the Gateway's check 3, and the per-learner auth/ structure in agent memory all depend on this lifetime.
  - Expected benefit: NFR-6 can actually be built and tested on Entra ID. (objectives: NFR-6, FR-4)
  - Supporting evidence: EV-082, EV-083, EV-092
  - Verification: In a test tenant, configure Entra ID and confirm the issued token's lifetime and that revocation is detected by the Gateway.
- Next step: Identity / IAM lead: Confirm which Entra ID token lifetimes are configurable and choose the token model that delivers the 48-hour session window.
- Decision AD-014 (25 Confirmed Decisions - Auth token window): preserves. Keeps the 48-hour window and clarifies which token carries it.
- Decision AD-054 (NFR-6): refines. Names the token type and how revocation is detected.

### FND-020 FR-1 acceptance criterion contradicts the provisioning triggers

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.70 (medium) · rank 19
- Disposition: **refinement now**

The FR-1 test expects all nine top-level areas to exist after a registration event. But Section 21 provisions only core/ and orientation/ at registration, and other areas are created per programme, module, session or escalation. Escalations and buddy areas are keyed by an ID that does not exist at registration. Either the test will fail against the documented design, or FR-1 means a logical namespace map rather than provisioned slots; the document does not say which.

- Where: p.26 §27.1 (FR-1): "Given a fresh learner registration event, all nine top-level areas exist in the"
- Where: p.3 §2.1 (FR-1): "The platform shall provide one structured namespace per learner at learner:<learner_id>/, containing the"
- Evidence EV-061 (doc, supports): "Learner registration -> create_namespace() + provision core/ + orientation/" [doc:DOC-sit_sample_v1#p21/s21]
- Evidence EV-062 (doc, supports): "Given a fresh learner registration event, all nine top-level areas exist in the" [doc:DOC-sit_sample_v1#p26/s27.1]
- Recommendation: State in FR-1 whether the top-level areas are logical containers created at registration (and update the Section 21 triggers) or are provisioned lazily; align the FR-1 test with that choice, listing which slots must exist after registration.
  - Issue: The FR-1 criterion and the provisioning rules disagree.
  - Rationale: An acceptance test must match the designed behaviour.
  - Expected benefit: FR-1 becomes verifiable. (objectives: FR-1, FR-12)
  - Supporting evidence: EV-061, EV-062
  - Verification: FR-1 test asserts the explicit post-registration slot list.
- Decision AD-038 (FR-1): refines. Clarifies whether the nine areas are logical containers or provisioned slots.
- Decision AD-012 (25 Confirmed Decisions - MMP provisioning): preserves. SIS-triggered provisioning is unchanged.

### FND-034 SGD 800-1,200/month cost figure is unsourced and its scope does not match its test

- **validation need** · unsupported or incorrect claim · severity **medium** · confidence 0.50 (medium) · rank 20
- Disposition: **needs investigation**

NFR-10 commits to SGD 800-1,200/month for vector-store infrastructure on a Memory Optimised 16-vCore tier in Azure Singapore, but no pricing source, storage/IOPS, HA replica or backup assumptions are given. Its acceptance test also includes 'measured embedding volume', which is outside the vector-store scope the requirement names. Whether the figure covers the SKU at current pricing is unverified, and the requirement and its test measure different things.

- Where: p.5 §2.2 (NFR-10): "Vector-store infrastructure cost shall remain within the SGD 800-1,200/month estimate at 15,000-learner"
- Where: p.28 §27.2 (NFR-10): "Projected monthly cost at 15,000-learner scale, computed from the actual"
- Evidence EV-069 (doc, supports): "Vector-store infrastructure cost shall remain within the SGD 800-1,200/month estimate at 15,000-learner" [doc:DOC-sit_sample_v1#p5/s2.2]
- Evidence EV-087 (doc, supports): "Projected monthly cost at 15,000-learner scale, computed from the actual" [doc:DOC-sit_sample_v1#p28/s27.2]
- Recommendation: Add a cost breakdown to Section 12: compute SKU, storage, HA/backup, Event Hubs, Redis and embeddings, each with its pricing date. Restate NFR-10's scope so it matches the NFR-10 acceptance test.
  - Issue: The cost estimate is unsourced, and its scope differs between NFR-10 and its acceptance test.
  - Rationale: Budget approval relies on this figure, and FND-002 suggests a larger SKU may be needed.
  - Expected benefit: NFR-10 rests on a verifiable, correctly scoped cost baseline. (objectives: NFR-10)
  - Supporting evidence: EV-069, EV-087
  - Verification: Run the Azure pricing calculator for the Singapore region using the measured sizing from the NFR-1 dataset.
- Next step: Platform finance / FinOps owner: Produce a dated Azure Singapore cost model for the selected SKU and its supporting services.
- Decision AD-034 (NFR-10): preserves. Verifies the cost constraint and does not challenge it, because pricing was not retrieved.
- Decision AD-003 (25 Confirmed Decisions - Azure SKU): preserves. The cost model is for the confirmed SKU.

## Recommended refinements

| Finding | Change | Expected benefit |
|---|---|---|
| FND-011 | Add a section on the agent backup store that defines (a) where it is stored, split by sensitivity tier (HIGHLY_RESTRICTED backups in memory_sensitive), (b) that backup writes pass through Gateway/Policy checks, (c) that FR-15 deletion propagates to backups or a documented exemption approved by the DPO, and (d) one list of degraded-mode triggers (unreachable, EXPIRED, REVOKED) reconciled with FR-16. Extend the FR-15 and FR-16 acceptance tests to inspect the backup contents. | Makes FR-15, NFR-5 and P6 achievable and makes the trigger conditions for degraded mode consistent. |
| FND-012 | In Sections 19 and 21, explicitly exclude wellbeing/counselling/ and memory_sensitive from Super Admin and MMP emergency access. State that MMP credentials have no grant on memory_sensitive. Fix named_agents to the Counsellor agent through an approval process outside the MMP. Define the counselling write path (agent or clinical system). Extend the FR-5 test to the Super Admin, Institution Admin and MMP Admin API (GET /namespaces, GET /audit, DELETE) and to an attempt to add an agent to named_agents. | FR-5 and P4 become consistent and testable. |
| FND-038 | In Section 18: (1) split failures into transient ones (retry with backoff and a maximum attempt count) and deterministic ones (validation or policy rejection, sent straight to a per-tier dead-letter topic, audited, and shown on the MMP dashboard); (2) run validation before embedding; (3) require a client-side sensitivity declaration at the Gateway, and have a standard consumer that classifies content as HIGHLY_RESTRICTED quarantine it rather than store it; (4) define an idempotency key and per-learner/slot partitioning. | Writes stay reliable under FR-9 and tier isolation holds in transit under NFR-5. |
| FND-013 | In Sections 5, 15 and 21, separate the runtime Policy Engine, audit sink and published-template cache (owned by the request path) from the MMP admin service, which only edits configuration. Define Check 4 behaviour when the MMP is down (deny with a reason code, or queue provisioning). Extend the NFR-4 test to cover a first access to an unprovisioned slot and a policy-rule read while the MMP is stopped. | NFR-4 becomes achievable and its chaos test meaningful. |
| FND-037 | Change the Section 15 Check 3 REVOKED branch to deny all learner-specific memory, backup included. Serve only agent-global content and log the attempt. Update Section 6 and the Section 25 decision text to match. Add an NFR-6 test step that confirms no backup content is returned under REVOKED. | NFR-6 revocation then actually stops access, and the P2 private-by-default principle is protected. |
| FND-026 | In Sections 11-12, state the intended filtered-query strategy explicitly. Options are: exact scan via the (learner_id, slot_path) index; partitioning memory_vectors by learner hash or slot; or a pgvector version with iterative/filtered HNSW scans and a defined ef_search. Prototype on the synthetic 9.5M dataset, and measure both latency and recall@k against an exact baseline. | NFR-2 latency is met with correct recall, and the Section 12 sizing reflects the indexes actually used. |
| FND-041 | In Section 18, add cache invalidation triggered by policy changes, slot permission changes, learner deletions and slot expiry. Key cache entries by agent_id and policy version. Either exclude HIGHLY_RESTRICTED content from the shared Redis cache or use a separate cache instance with separate credentials. Add an FR-10 test step. | Policy changes and deletions take effect immediately for FR-8 and FR-15, and NFR-5 isolation covers the cache. |
| FND-030 | Have the DPO decide the audit retention period, whether escalation content (as opposed to metadata) may stay in the audit log, and how learner deletion requests affect audit and agent-backup copies. Record the outcomes in Sections 17, 19 and 20, and replace 'retained per PDPA requirements' with the concrete period. | NFR-7 and FR-13 become legally grounded, and the risk of rework after the DPO's review is avoided. |
| FND-027 | Recompute Section 12 from first principles. Use a consistent per-learner count, counting only SEMANTIC/PROCEDURAL keys, because episodic writes are not vector-indexed (Section 17). State whether 80 GB is the total index or overhead on top of the raw vectors, and include shared_buffers and working-set assumptions. Restate the growth ceiling as 'to be measured', or derive it. Consider halfvec or reduced dimensions if RAM fit is required. | A defensible SKU choice and a correct growth ceiling for NFR-1, NFR-2 and NFR-10. |
| FND-018 | In Section 11, add embedded BOOLEAN and a tsvector/GIN index to memory_vectors; add pii, retention, expires_at and deletable columns to all three tables; add escalation target and status fields; add consent to memory_documents. Downgrade the Section 28 rating until done. | NFR-7, FR-15, FR-7 and the embedder fallback become implementable. |
| FND-006 | When writing the Section 28 decision table, define the outcome type per dimension (DENY, REDACT, EXPIRE, PURGE) and a precedence order. Rewrite the FR-8 criterion to assert the expected outcome per dimension plus at least one case per conflicting pair. | FR-8 becomes verifiable, and Build Phase 3 has a concrete specification. |
| FND-019 | Add an escalations template in Section 23 (target_domain, triggering_agent_id, status, created_at). Add a record-level rule to Check 5 or the Policy Engine. Define the self-target case and RESOLVED expiry. Extend the FR-7 test to a non-target third agent. | FR-7 becomes implementable and its lifecycle test meaningful. |
| FND-043 | Add an Operations section setting out: PostgreSQL HA and point-in-time-restore with stated RPO/RTO; how backup retention handles learner deletion; alerts on consumer lag, dead-letter count, unembedded backlog and SIS webhook failures; and a named on-call owner. Add matching NFR rows and Section 27 criteria. | Recovery is defined for P1/FR-9, and backups stay consistent with FR-15. |
| FND-031 | Close the Event Hubs backlog item before Phase 4/5 build. In Section 18, specify the consumer retry policy, dead-letter topic, idempotency key (memory_id), partition key (learner_id) for ordering, and the broker retention tier. Downgrade the Section 28 write-path rating to 'Mostly ready' until this is done. | FR-9 durability and NFR-3 non-blocking writes rest on verified broker behaviour. |
| FND-017 | Restate NFR-3 as 'Gateway + policy + enqueue ≤ X ms p99 and independent of consumer processing', set X and the load profile (requests/s, concurrent sessions), and define 'normal load' for NFR-2. Update the FR-9, NFR-2 and NFR-3 criteria with these numbers. | NFR-3, FR-9 and NFR-2 become testable. |
| FND-029 | In Sections 6 and 15, name the token whose 48-hour lifetime is meant (Entra access token, refresh token, or a platform session token minted after Entra login). Cite the Entra configuration that supports it, and define how revocation is detected (for example introspection or a revocation list). Update the NFR-6 acceptance criterion to match. | NFR-6 can actually be built and tested on Entra ID. |
| FND-022 | This refines the confirmed learner_id decision rather than challenging it. Add a requirement for UPN-change handling: a lookup keyed on entra_object_id and a re-key job with audit. Extend FR-12 with SIT withdrawal/termination, leave of absence, programme transfer and term-end events, each with a namespace action, and add them to the FR-12 test. | FR-12 and NFR-7 cover the full learner lifecycle. |
| FND-044 | Add to Section 19 a defined anonymisation rule: which sensitivity tiers are excluded, a minimum aggregation group size, and an owner. Have the DPO set the audit retention period in Section 17 before Build Phase 4. Add a test that cohort aggregates below the minimum group size are suppressed. | The P2 and FR-13/NFR-7 PDPA obligations rest on signed-off rules. |
| FND-020 | State in FR-1 whether the top-level areas are logical containers created at registration (and update the Section 21 triggers) or are provisioned lazily; align the FR-1 test with that choice, listing which slots must exist after registration. | FR-1 becomes verifiable. |
| FND-034 | Add a cost breakdown to Section 12: compute SKU, storage, HA/backup, Event Hubs, Redis and embeddings, each with its pricing date. Restate NFR-10's scope so it matches the NFR-10 acceptance test. | NFR-10 rests on a verifiable, correctly scoped cost baseline. |
| FND-009 | In Section 23 (orientation template), retype onboarding_progress as SEMANTIC or META, keeping slot-level expiry. | Orientation progress survives across sessions until the orientation slot expires. |
| FND-023 | Define write audit as linked ENQUEUED and COMMITTED/REJECTED entries sharing a write_id. Require the audit entry to be written in the same transaction as storage (or an outbox). Update the FR-13 criterion accordingly. | FR-13 is testable and audit gaps are prevented. |

## Areas where no change is needed

- FND-010 Clear, traceable statement of intent: IDed requirements, ranked principles, acceptance criteria and an honest readiness map: The intent, requirements and readiness are stated clearly enough to review and test against, and are traced end to end.
- FND-046 Two-tier sensitive storage with separate credentials and per-tier topics: Enforcing isolation at the credential level and in transit meets FR-5 and NFR-5 as written, and the acceptance test checks it directly.
- SA-001 (sections 11, 17, 2.2): For data in the namespace, physically separating HIGHLY_RESTRICTED data into memory_sensitive with separate credentials and a separate embedding deployment meets NFR-5 and enforces FR-5 at the credential level, not only in policy. The schema-isolation test in NFR-5 checks this directly. (see FND-011, FND-012)
  - p.4 §2.2: "HIGHLY_RESTRICTED data shall be stored in a physically separate schema (memory_sensitive) with"
- SA-002 (sections 15): Six ordered pre-retrieval checks, each failure denied and logged, implement P3 and FR-4 directly and can be tested one check at a time. The only exception is the MMP dependency in Check 4. (see FND-013)
  - p.15 §15: "Access control is pre-retrieval. The namespace check gates the query itself - not the returned results."
- SA-003 (sections 15, 2.1): The six ordered Gateway checks map one-to-one to FR-4, each with a defined failure outcome and log reason, and the FR-4 test exercises each check in isolation; this is consistent and verifiable (apart from the MMP dependency in Check 4 raised in FND-003). (see FND-013)
  - p.26 §27.1: "Six test cases, one per check, each asserting a DENY with the correct reason"
- SA-004 (sections 2.2, 27.2): NFR-5 schema isolation with separate credentials has a direct, executable acceptance test (cross-credential authentication failure in both directions) that verifies the requirement. (see FND-011)
  - p.27 §27.2: "A credential valid for memory_standard is confirmed to fail authentication"
- SA-005 (sections 27, 28): Every requirement has a matching acceptance criterion, and Section 28 openly lists the components not yet ready to build, which supports a planned build. (see FND-010)
  - p.26 §27: "Each requirement from Section 2 is validated by a specific method with a concrete pass/fail acceptance criterion."
- SA-006 (sections 17): The embedding model's dimension (1536) matches the vector(1536) column in the DDL, so the Embedder and schema are consistent for FR-10 and NFR-1.
  - p.16 §17: "Generates vector embeddings for semantic memory operations. Runs"
- SA-007 (sections 26, 28): Open items (cohort namespace, compaction, non-SIT identity) are explicitly deferred with a rationale tied to launch scope, so these dependencies are tracked rather than hidden. (see FND-010)
  - p.26 §26: "Items confirmed as in-scope but not yet fully designed:"
- SA-008 (sections 15): The ordered six-check Gateway denies on any failure and logs a reason code, which gives the pre-retrieval control and auditability that FR-4 and P3 require. The FR-4 test checks each check on its own. (see FND-037)
  - p.15 §15: "Access control is pre-retrieval. The namespace check gates the query itself - not the returned results."
- SA-009 (sections 17): The Auditor's log fields include source (namespace, backup or global) and it covers cache hits and enqueues, which supports the FR-13 audit trail. Retention is a separate pending item (FND-009). (see FND-044)
  - p.17 §17: "timestamp, outcome (ALLOWED | DENIED), denial_reason (if denied),"
- SA-010 (sections 17): The embedding fallback flags records as unembedded, uses BM25 for retrieval and queues them for re-embedding. This keeps reads available when the embedding service is down, and the MMP backlog dashboard makes the gap visible to operators.
  - p.16 §17: "Fallback path (embedding service unavailable): - Flag record"

## Unresolved issues and next steps

- FND-011 (governance decision): Agent per-learner backup is an ungoverned copy that conflicts with P6, NFR-5, FR-15 and FR-16 (FND-011) Next step (Data governance officer / DPO with platform architect): Decide whether the backup survives deletion, and set its storage tier and policy path; then revise Sections 13, 14 and 20 and FR-16.
- FND-037 (governance decision): A revoked token still gets learner data served from the agent backup (FND-037) Next step (Information security officer): Decide whether any learner-specific memory may be served after revocation, and record the decision in Section 25.
- FND-026 (needs prototyping): Filtered HNSW search-space claim is unverified and drives NFR-2 (FND-026) Next step (Platform data architect): Build a 9.5M-vector pgvector prototype on the target Azure PostgreSQL version and benchmark filtered query plans for latency and recall.
- FND-030 (governance decision): PDPA compliance is asserted but PDPA sign-off and retention period are still pending (FND-030) Next step (Data Protection Officer): Issue a PDPA interpretation covering audit-log retention, escalation content and the deletion scope, before the Auditor is built.
- FND-027 (needs testing): Vector sizing, RAM fit and growth ceiling do not add up (FND-027) Next step (Platform data architect): Recalculate sizing and confirm it with measured relation sizes from the load-test dataset.
- FND-043 (governance decision): No backup/DR, availability targets or operational monitoring for the authoritative store and pipeline (FND-043) Next step (Platform operations lead): Propose RPO/RTO and availability targets for approval, and assign on-call ownership.
- FND-031 (needs investigation): Write path is marked confirmed and 'Ready' while Event Hubs and retry behaviour are still pending (FND-031) Next step (Platform engineering lead): Confirm Event Hubs tier and Kafka-API feature support, and specify retry/DLQ semantics.
- FND-029 (needs investigation): 48-hour Entra ID token validity is assumed, not shown to be configurable (FND-029) Next step (Identity / IAM lead): Confirm which Entra ID token lifetimes are configurable and choose the token model that delivers the 48-hour session window.
- FND-044 (governance decision): Anonymisation standard, audit retention and PDPA sign-off have no accountable decision (FND-044) Next step (Data Protection Officer): Approve the anonymisation rule and the audit retention period.
- FND-034 (needs investigation): SGD 800-1,200/month cost figure is unsourced and its scope does not match its test (FND-034) Next step (Platform finance / FinOps owner): Produce a dated Azure Singapore cost model for the selected SKU and its supporting services.

Research questions left unanswered:
- RQ-003: With an HNSW index plus a selective WHERE filter on learner_id and slot_path (about 500-800 of 9.5M rows), does pgvector search only the filtered subset as Section 12 claims? Or does it post-filter the ef_search candidates, which can return too few results unless the planner uses the B-tree index or iterative index scans?
- RQ-004: Does Azure Database for PostgreSQL Flexible Server support the stated BM25 keyword fallback natively, or only ts_rank full-text ranking? Is pgvector HNSW available there at the required version?
- RQ-010: Can Microsoft Entra ID issue 48-hour access tokens? Default access-token lifetimes are about 60-90 minutes, with configurable lifetime limits and refresh tokens. Is UPN mutable, which would make it unsuitable as the immutable primary key learner_id?
- RQ-011: Is SGD 800-1,200/month realistic for an Azure Database for PostgreSQL Flexible Server Memory Optimised 16 vCore (128 GB) in Southeast Asia, including storage, HA and backup? Does about 9.5M × 1536-dim vectors with HNSW (~57 GB raw, ~80 GB index) fit in 128 GB RAM with headroom?
- RQ-012: Does Azure Event Hubs Kafka support (tier needed, message size limit, partition counts, no native dead-letter queue, consumer-group limits) fit the write path's 'failed writes queue and retry automatically' claim? Is text-embedding-3-small deployable in an Azure Singapore region for data residency?
- RQ-014: Is serving from an agent backup after a token is REVOKED compatible with access-control intent? Is keeping the agent backup after a learner self-deletes compatible with FR-15 and with PDPA retention-limitation and consent-withdrawal obligations?
- RQ-015: Does PDPA require the specific audit-log retention or access-request support the design implies ('Retained per PDPA requirements')? Do access/correction obligations and data-breach notification create requirements the design lacks? Is the unauthenticated Admin API (acknowledged in Section 28) a launch blocker?
- RQ-016: How does the design behave under term-start write spikes, consumer lag, retries with duplicates, out-of-order writes for one learner (no partition key is defined), Azure OpenAI embedding throttling, and Redis failure? Does the cached read path serve stale or now-forbidden data after a write or a policy change, given that policy decisions are 'not cached' but context packs are?
- RQ-020: What recognised benchmark method (for example ANN-benchmarks-style recall@k versus latency with filtered queries under concurrent load) should validate NFR-2 and retrieval quality?

## Evidence limitations

- DOC-sit_sample_v1: native PDF block not sent because the configured model backend accepts text only. Impact: figures, diagrams and tables rendered as images were not visible to the model; the review is based on the extracted text (DEG-001)
- mcp-internet-search/search_web failed (tool_error): MCP error -32000: Connection closed. Impact: that call contributed no evidence (DEG-002)

## Evidence register

| ID | Type | Source | Retrieved | Cited |
|---|---|---|---|---|
| EV-001 | external (secondary) | [Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs](https://doi.org/10.48550/arxiv.1603.09320) via mcp-research-information/search_research call-0006 | 2026-10-03T04:26:38Z | no |
| EV-002 | external (peer reviewed) | [Filtered-DiskANN: Graph Algorithms for Approximate Nearest Neighbor Search with Filters](https://doi.org/10.1145/3543507.3583552) via mcp-research-information/search_research call-0006 | 2026-10-03T04:26:38Z | yes |
| EV-003 | external (peer reviewed) | [ParlayANN: Scalable and Deterministic Parallel Graph-Based Approximate Nearest Neighbor Search Algorithms](https://doi.org/10.1145/3627535.3638475) via mcp-research-information/search_research call-0006 | 2026-10-03T04:26:38Z | no |
| EV-004 | external (peer reviewed) | [Medical image retrieval via nearest neighbor search on pre-trained image features](https://doi.org/10.1016/j.knosys.2023.110907) via mcp-research-information/search_research call-0006 | 2026-10-03T04:26:38Z | no |
| EV-005 | external (peer reviewed) | [Neuromorphic Nearest Neighbor Search Using Intel's Pohoiki Springs](https://doi.org/10.1145/3381755.3398695) via mcp-research-information/search_research call-0006 | 2026-10-03T04:26:38Z | no |
| EV-006 | external (peer reviewed) | [pHNSW: PCA-Based Filtering to Accelerate HNSW Approximate Nearest Neighbor Search](https://doi.org/10.1109/asp-dac66049.2026.11420341) via mcp-research-information/search_research call-0006 | 2026-10-03T04:26:38Z | no |
| EV-007 | external (peer reviewed) | [A Comparative Study of HNSW Implementations for Scalable Approximate Nearest Neighbor Search](https://doi.org/10.36227/techrxiv.175321947.71782908/v1) via mcp-research-information/search_research call-0006 | 2026-10-03T04:26:38Z | no |
| EV-008 | external (peer reviewed) | [Zonal HNSW: Scalable Approximate Nearest Neighbor Search for Billion-Scale Datasets](https://doi.org/10.1109/icssas66150.2025.11081070) via mcp-research-information/search_research call-0006 | 2026-10-03T04:26:38Z | no |
| EV-009 | external (peer reviewed) | [P-HNSW: Software-Hardware Co-design for HNSW Nearest Neighbor Search based on PCAF](https://doi.org/10.36227/techrxiv.173317879.95077587/v1) via mcp-research-information/search_research call-0006 | 2026-10-03T04:26:38Z | no |
| EV-010 | external (peer reviewed) | [Near Memory Accelerators for Approximate Nearest Neighbor Search](https://doi.org/10.37099/mtu.dc.etdr/1961) via mcp-research-information/search_research call-0006 | 2026-10-03T04:26:38Z | no |
| EV-011 | doc | doc:DOC-sit_sample_v1#p13/s13 | - | no |
| EV-012 | doc | doc:DOC-sit_sample_v1#p8/s6 | - | yes |
| EV-013 | doc | doc:DOC-sit_sample_v1#p19/s20 | - | yes |
| EV-014 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-015 | doc | doc:DOC-sit_sample_v1#p18/s19 | - | yes |
| EV-016 | doc | doc:DOC-sit_sample_v1#p20/s21 | - | yes |
| EV-017 | doc | doc:DOC-sit_sample_v1#p19/s19 | - | yes |
| EV-018 | doc | doc:DOC-sit_sample_v1#p6/s3 | - | yes |
| EV-019 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | no |
| EV-020 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | no |
| EV-021 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-022 | doc | doc:DOC-sit_sample_v1#p16/s16 | - | no |
| EV-023 | doc | doc:DOC-sit_sample_v1#p18/s18 | - | yes |
| EV-024 | doc | doc:DOC-sit_sample_v1#p18/s18 | - | yes |
| EV-025 | doc | doc:DOC-sit_sample_v1#p15/s15 | - | yes |
| EV-026 | doc | doc:DOC-sit_sample_v1#p4/s2.2 | - | yes |
| EV-027 | doc | doc:DOC-sit_sample_v1#p27/s27.1 | - | yes |
| EV-028 | doc | doc:DOC-sit_sample_v1#p15/s16 | - | yes |
| EV-029 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | no |
| EV-030 | doc | doc:DOC-sit_sample_v1#p11/s11 | - | yes |
| EV-031 | doc | doc:DOC-sit_sample_v1#p25/s25 | - | yes |
| EV-032 | doc | doc:DOC-sit_sample_v1#p26/s26 | - | yes |
| EV-033 | doc | doc:DOC-sit_sample_v1#p23/s23 | - | yes |
| EV-034 | doc | doc:DOC-sit_sample_v1#p16/s17 | - | yes |
| EV-035 | doc | doc:DOC-sit_sample_v1#p3/s2 | - | yes |
| EV-036 | doc | doc:DOC-sit_sample_v1#p29/s28 | - | yes |
| EV-037 | inference | inference:EV-037 from EV-011, EV-012, EV-013, EV-014 | - | yes |
| EV-038 | inference | inference:EV-038 from EV-019, EV-020, EV-021 | - | no |
| EV-039 | inference | inference:EV-039 from EV-029, EV-030 | - | yes |
| EV-040 | doc | doc:DOC-sit_sample_v1#p13/s13 | - | yes |
| EV-041 | doc | doc:DOC-sit_sample_v1#p6/s3 | - | yes |
| EV-042 | doc | doc:DOC-sit_sample_v1#p4/s2.2 | - | yes |
| EV-043 | doc | doc:DOC-sit_sample_v1#p14/s14 | - | yes |
| EV-044 | doc | doc:DOC-sit_sample_v1#p3/s2.1 | - | yes |
| EV-045 | doc | doc:DOC-sit_sample_v1#p15/s15 | - | yes |
| EV-046 | doc | doc:DOC-sit_sample_v1#p8/s5 | - | yes |
| EV-047 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-048 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-049 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | no |
| EV-050 | doc | doc:DOC-sit_sample_v1#p16/s16 | - | no |
| EV-051 | doc | doc:DOC-sit_sample_v1#p18/s18 | - | yes |
| EV-052 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-053 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | no |
| EV-054 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | no |
| EV-055 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-056 | doc | doc:DOC-sit_sample_v1#p4/s2.2 | - | yes |
| EV-057 | doc | doc:DOC-sit_sample_v1#p29/s28 | - | yes |
| EV-058 | doc | doc:DOC-sit_sample_v1#p16/s17 | - | yes |
| EV-059 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-060 | doc | doc:DOC-sit_sample_v1#p15/s15 | - | yes |
| EV-061 | doc | doc:DOC-sit_sample_v1#p21/s21 | - | yes |
| EV-062 | doc | doc:DOC-sit_sample_v1#p26/s27.1 | - | yes |
| EV-063 | doc | doc:DOC-sit_sample_v1#p29/s28 | - | yes |
| EV-064 | doc | doc:DOC-sit_sample_v1#p8/s6 | - | yes |
| EV-065 | doc | doc:DOC-sit_sample_v1#p19/s20 | - | yes |
| EV-066 | doc | doc:DOC-sit_sample_v1#p17/s17 | - | yes |
| EV-067 | doc | doc:DOC-sit_sample_v1#p27/s27.1 | - | yes |
| EV-068 | doc | doc:DOC-sit_sample_v1#p17/s17 | - | yes |
| EV-069 | doc | doc:DOC-sit_sample_v1#p5/s2.2 | - | yes |
| EV-070 | doc | doc:DOC-sit_sample_v1#p26/s27 | - | yes |
| EV-071 | inference | inference:EV-071 from EV-040, EV-041, EV-014, EV-042, EV-043 | - | yes |
| EV-072 | inference | inference:EV-072 from EV-025, EV-046, EV-026 | - | yes |
| EV-073 | inference | inference:EV-073 from EV-047, EV-048, EV-049 | - | yes |
| EV-074 | inference | inference:EV-074 from EV-050, EV-051 | - | yes |
| EV-075 | inference | inference:EV-075 from EV-052, EV-053, EV-054 | - | yes |
| EV-076 | inference | inference:EV-076 from EV-057, EV-058 | - | yes |
| EV-077 | inference | inference:EV-077 from EV-059, EV-060 | - | yes |
| EV-078 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-079 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-080 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-081 | doc | doc:DOC-sit_sample_v1#p20/s21 | - | yes |
| EV-082 | doc | doc:DOC-sit_sample_v1#p8/s6 | - | yes |
| EV-083 | doc | doc:DOC-sit_sample_v1#p27/s27.2 | - | yes |
| EV-084 | doc | doc:DOC-sit_sample_v1#p17/s17 | - | yes |
| EV-085 | doc | doc:DOC-sit_sample_v1#p26/s26 | - | yes |
| EV-086 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-087 | doc | doc:DOC-sit_sample_v1#p28/s27.2 | - | yes |
| EV-088 | doc | doc:DOC-sit_sample_v1#p29/s28 | - | yes |
| EV-089 | inference | inference:EV-089 from EV-078, EV-030 | - | yes |
| EV-090 | inference | inference:EV-090 from EV-079, EV-080, EV-052 | - | yes |
| EV-091 | inference | inference:EV-091 from EV-025, EV-026, EV-081 | - | yes |
| EV-092 | inference | inference:EV-092 from EV-082, EV-083 | - | yes |
| EV-093 | inference | inference:EV-093 from EV-084, EV-085 | - | yes |
| EV-094 | inference | inference:EV-094 from EV-032, EV-086 | - | yes |
| EV-095 | inference | inference:EV-095 from EV-021, EV-047 | - | yes |
| EV-096 | inference | inference:EV-096 from EV-058 | - | yes |
| EV-097 | doc | doc:DOC-sit_sample_v1#p13/s13 | - | no |
| EV-098 | doc | doc:DOC-sit_sample_v1#p8/s6 | - | yes |
| EV-099 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-100 | doc | doc:DOC-sit_sample_v1#p21/s21 | - | yes |
| EV-101 | doc | doc:DOC-sit_sample_v1#p20/s21 | - | yes |
| EV-102 | doc | doc:DOC-sit_sample_v1#p16/s16 | - | yes |
| EV-103 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-104 | doc | doc:DOC-sit_sample_v1#p27/s27.2 | - | yes |
| EV-105 | doc | doc:DOC-sit_sample_v1#p26/s26 | - | yes |
| EV-106 | doc | doc:DOC-sit_sample_v1#p6/s3 | - | yes |
| EV-107 | doc | doc:DOC-sit_sample_v1#p6/s3 | - | yes |
| EV-108 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-109 | inference | inference:EV-109 from EV-097, EV-014, EV-042 | - | yes |
| EV-110 | inference | inference:EV-110 from EV-098 | - | yes |
| EV-111 | inference | inference:EV-111 from EV-099, EV-047 | - | yes |
| EV-112 | inference | inference:EV-112 from EV-015, EV-016, EV-100 | - | yes |
| EV-113 | inference | inference:EV-113 from EV-025, EV-101 | - | yes |
| EV-114 | inference | inference:EV-114 from EV-102, EV-023 | - | yes |
| EV-115 | inference | inference:EV-115 from EV-103, EV-080 | - | no |
| EV-116 | inference | inference:EV-116 from EV-105, EV-106 | - | yes |
| EV-117 | inference | inference:EV-117 from EV-107 | - | yes |

## Review coverage

| Criterion | Outcome | Findings | Note |
|---|---|---|---|
| design_intent | findings | FND-010, FND-006, FND-031 | Checked objectives, principles, FR/NFR, the decision register and the readiness map. Intent is clear and traceable. The open gaps (Policy Engine algorithm, conditional decisions) are acknowledged in the document. |
| fitness_for_objectives | findings | FND-011, FND-012, FND-038, FND-041, FND-013, FND-006, FND-026, FND-009 | The core governed path is fit for purpose. The agent backup store, the async validation ordering, cache-versus-policy freshness, the MMP dependency in the Gateway and the filtered-ANN latency undermine specific requirements. |
| requirement_completeness | findings | FND-011, FND-038, FND-018, FND-019, FND-022 | Checked FR and NFR coverage against Sections 6-23 and the backlog. Gaps found: no governance for the agent backup, no error path for async writes after the ACK, missing schema fields, missing record-level escalation access, and no UPN-change or SIS lifecycle events. Gaps the document already acknowledges in Section 26/28 (policy algorithm, Admin API, SDK, compaction) are not re-raised except where they invalidate an acceptance criterion (FND-011). |
| internal_consistency | findings | FND-011, FND-012, FND-013, FND-038, FND-041, FND-027, FND-018, FND-020, FND-023, FND-009, FND-017 | Cross-checked principles, requirements, flows, role tables, DDL, sizing arithmetic and confirmed decisions; found contradictions in the counselling wall, MMP critical path, pipeline order, cache versus policy freshness, and sizing figures. |
| claims_and_external_constraints | findings | FND-026, FND-027, FND-029, FND-018, FND-034, FND-030 | Checked the vector sizing arithmetic, filtered-HNSW claims, the Entra token lifetime, the BM25 fallback, the cost estimate, the PDPA claims and the embedding model/dimension. The embedding dimension is consistent with the DDL. External facts could not be verified here and are framed as validation needs. |
| security_and_privacy | findings | FND-011, FND-037, FND-012, FND-041, FND-038, FND-044, FND-046 | Checked tier isolation, the agent backup, token revocation, admin roles and Admin API auth, cache isolation, anonymisation and audit. |
| scalability_and_failure_modes | findings | FND-038, FND-013, FND-041, FND-026, FND-043 | Checked async write failure semantics, MMP dependency, cache staleness, vector capacity and recovery. |
| assumptions_and_dependencies | findings | FND-013, FND-030, FND-031, FND-038, FND-029, FND-010 | Checked confirmed decisions against the Pending Backlog (Event Hubs, Auditor/PDPA), the MMP's request-path dependency, and the ordering assumptions in the write path. The backlog is otherwise well tracked. |
| verifiability | findings | FND-012, FND-027, FND-017, FND-020, FND-006, FND-023, FND-010, FND-013, FND-041 | Reviewed each Section 27 criterion against its requirement. FR-1, FR-5, FR-8, FR-13, NFR-2 and NFR-3 criteria cannot validate as written or lack numeric thresholds; the sizing claims need a benchmark. |
| decision_preservation | findings | FND-011, FND-012, FND-031 | The counselling hard wall decision conflicts with the admin role definitions and the backup store. Some confirmed decisions depend on pending backlog items. No finding challenges an approved decision; the recommendations refine them. |
| operability_and_governance | findings | FND-043, FND-044, FND-034, FND-012 | Checked DR/monitoring ownership, DPO decisions, cost scope and admin governance. |

## Run details

| | |
|---|---|
| Run | sit_sample_tools_1 (started 2026-10-03T04:24:22Z) |
| Outcome | completed_degraded |
| Model | requested claude-opus-5-5; served claude-opus-5-5; effort per-stage (extra.model.effort_by_stage) |
| Persona | generalist_architect |
| Tool transport | live |
| Research stop | sufficient_evidence (decision): model_stop_vote; 1 iteration(s); 1 cited of 10 retrieved |
| Tool calls | mcp-internet-search: 5, mcp-research-information: 1 |
| Tokens | input 351269, cached 106739, output 135599; cost ~$5.54 (price table 2026-09-25) |
| Extractor | pdfplumber 0.11.10 |
| Config sha256 | 52966ed8963969945d1ce0f129f8d5596d9db4d4409e0f7b63d5dcb1af53f3d6 |
| Prompt bundle sha256 | 6f0ee28ab9acf35152a2d4456207a8a068222149422e66d801c8195455c28ba7 |
| Git commit | 1b92baf0fef94f2a95d1f1e7e7698718e4b2c8dd |
| Fault schedule | none |
| Model fallbacks | 0 |
| Canonical text DOC-sit_sample_v1 | sha256 7be073ff2e98e50998367a46b92ed5dbf85815177eb36c2e2c12a0f52a458de8 |
