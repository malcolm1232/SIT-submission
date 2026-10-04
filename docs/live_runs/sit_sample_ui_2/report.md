# Design review: SIT Institutional Memory Platform — Detailed Design

| | |
|---|---|
| Review | REV-ui-261004-034213-c5cb (full review) |
| Under review | DOC-sit_sample_v1: SIT Institutional Memory Platform — Detailed Design v2.0, 30 pages |
| Verdict | **fit with conditions** (confidence 0.60, medium) |
| Tools used | mcp-internet-search |
| Tools disabled | mcp-browser-automation-pw, mcp-document-intelligence |
| Reporting threshold | severity low and above (0 finding(s) in the appendix) |


## Design intent

The document is the detailed design for the SIT Institutional Memory Platform. The platform is meant to give all AI agents serving SIT learners one governed memory infrastructure at institution level, not a separate memory store per agent. It provides a structured namespace for each learner, access control applied before retrieval, a seven-dimension policy engine, audit trails for PDPA, a strict wall around counselling data, an async write path and cached read path, and an administrative control plane (the MMP). Scope covers six agents (Tutor, Buddy, Advisory, Counselling, Career, Orientation) serving about 15,000 learners. The separate SIT-AI-Factory-RAG system is out of scope.

Objectives:
- P1: The learner namespace is authoritative. Each agent's copy is backup only, and conflicts are resolved in favour of the namespace.
- P2: Memory is private to the learner by default, shared only by exception, and anonymised for service learning.
- P3: Access control happens before retrieval: the namespace restriction gates the query itself, not the results afterwards.
- P4: Counselling hard wall: wellbeing/counselling/ is HIGHLY_RESTRICTED, with zero cross-domain reads, no MMP override and no exceptions.
- P5: Agents share information only through the learner namespace. No agent accesses another agent's memory directly.
- P6: No uncontrolled self-writing: every write is classified and policy-checked before it is stored.
- P7: Every operation is audited (access, write, denial, compaction, deletion, escalation), as PDPA requires.
- P8: Writes go asynchronously through Kafka; reads go through a Redis L1 cache, then PostgreSQL.
- P9: Administrators, not agents, configure slot templates, sensitivity levels and retention rules.
- P10: Minimum useful context: prefer summaries and facts over full transcripts, delivered in a token-budgeted context pack.
- NFR-1: Scale to 15,000 learner namespaces and about 9.5 million vectors without changing database engine.
- NFR-8: Onboard new domains or agents with a YAML template and a registry entry only, with no code changes.

Constraints:
- P7: PDPA compliance requires audit trails for every memory operation.
- NFR-10: Vector-store cost must stay within SGD 800-1,200/month at 15,000 learners (Azure Singapore region, Memory Optimised 16-vCore tier).
- NFR-5: HIGHLY_RESTRICTED data must sit in a physically separate schema (memory_sensitive) with its own database credentials.
- SIT-AI-Factory-RAG (Azure AI Search) is a separate system with no shared infrastructure, and is out of scope.
- Authentication is OAuth 2.0 via Entra ID, and tokens are valid for 48 hours.
- The ten foundational principles take precedence over any later section that conflicts with them.

Key assumptions:
- A learner accumulates about 600 vectors over a full degree, which gives about 9.5M vectors in total at 15,000 learners.
- Every query is filtered by learner_id and slot_path, so each query searches only 500-800 vectors, not 9.5M.
- HNSW index overhead is about 1.4×, the index fits in RAM on a 128 GB SKU, and degradation starts at roughly 30-40M vectors.
- Azure Event Hubs can serve as the managed Kafka-API service (still pending confirmation).
- Cohort namespace, compaction and non-SIT identity are not needed for launch of the initial six agents.
- Human counsellors access counselling data through a separate clinical system, not through this platform.

Located at: p.3 §1 (3 passages).

## Fitness for purpose

**Fit with conditions** (confidence 0.60). The design suits its purpose as a pre-build detailed design, provided specific changes are made before Build Phases 3-7. Its structure is sound. It has ten principles with a precedence rule, ID'd requirements, an acceptance criterion for every requirement and an honest readiness self-assessment (FND-009, FND-034, FND-019). It also enforces the counselling wall in layers (FND-010) and has ordered pre-retrieval Gateway checks (FND-055). These parts need no redesign. An unconditional fit is not possible because several high-severity findings remain open, and they cut against the design's own core principles:

- The counselling hard wall can be bypassed through Super Admin, MMP override and an MMP-writable named_agents list (FND-020).
- Agent per-learner backup memory sits outside governance. It is loaded on every request, survives learner deletion, has no sensitivity tier and is served even on REVOKED tokens (FND-021, FND-045, FND-001, FND-012, FND-047, FND-003).
- The async write path sends an ACK before validation, chooses the topic before classification, and has no dead-letter or feedback path (FND-002, FND-022, FND-049).
- The MMP sits in the request path for provisioning, policy and audit, which contradicts NFR-4 and leaves audit completeness open (FND-036, FND-048).
- The filtered-HNSW latency, recall and memory-fit premise behind NFR-1, NFR-2 and the SKU choice is unbenchmarked (FND-026, FND-035).

None of these is critical. Build has not started. Each can be fixed by rewriting the design, by a named governance decision, or by a prototype benchmark. That is why the label is fit_with_conditions rather than not_fit. Conditions should preserve the approved decisions, in particular the two-tier store (Section 25). FND-001's recommendation may read as reversing that decision without saying so (DEG-005). The backup-memory condition below is therefore framed as bringing backups inside the existing two tiers, not as changing them. Limits of this review, which reduce confidence:

- Only the extracted text was reviewed; figures and image tables were not visible (DEG-001).
- External research answered 1 of 21 plan questions, and no finding cites external evidence. Vendor capabilities are therefore unverified: Entra ID 48-hour token lifetimes, Event Hubs semantics, pgvector filtered-search behaviour and Azure pricing.
- Most findings were not refined or de-duplicated (DEG-003), so several issues appear more than once. One assessment shard was cut short (DEG-002), and anchor repair was skipped (DEG-004).

The verdict rests on the internal consistency of the document, which the text supports directly.

Conditions:
- Make the counselling hard wall actually hard. The DPO / data governance officer should decide, and record in Section 19/21, whether the Super Admin, MMP overrides and the agent_registry named_agents list can ever grant access to wellbeing/counselling/. Changes to named_agents for HIGHLY_RESTRICTED slots should be blocked or put under separate controls. FR-5 acceptance should be extended to attempt the Super Admin, MMP and registry-edit paths. (FND-020, FND-010)
- Bring agent per-learner backup memory under governance within the existing two-tier store decision. Use it only when the namespace is unreachable, in line with FR-16 and P1, not as a gap-filler on every request. Give it a sensitivity tier, so the counselling agent's backup lives in memory_sensitive, and give it retention, policy checks and audit. Cover it in FR-15 deletion, together with Redis packs, pending Kafka messages and the re-embed backlog. Define REVOKED and EXPIRED behaviour that does not serve learner-specific memory without valid identity, or record an explicit risk acceptance by the DPO. Extend the FR-15 and FR-16 tests to match. (FND-021, FND-045, FND-001, FND-012, FND-047, FND-003, FND-031, FND-030)
- Re-specify the async write path:

  - classify and decide sensitivity before choosing the topic;
  - validate before embedding, and route sensitive content only to the sensitive embedding deployment;
  - add bounded retries, a dead-letter queue, idempotency keys and a rejection or status signal visible to agents and in the MMP dashboard;
  - quantify the FR-9 and NFR-3 latency budgets so the tests have fixed pass/fail thresholds. (FND-002, FND-022, FND-049, FND-016, FND-050, FND-027)
- Settle the MMP's relationship to the request path. Either move slot provisioning, policy evaluation and audit write capability into request-path services that do not depend on MMP availability, or restate NFR-4. Define an audit path that fails closed or is durably buffered for reads, denials and async writes. Extend the NFR-4 chaos test to cover unprovisioned slots, and fix the FR-13 'exactly one entry' criterion. (FND-036, FND-005, FND-014, FND-023, FND-048, FND-029)
- Before Build Phase 3, produce the Policy Engine decision table, with precedence across the seven dimensions and the ALLOW/DENY/REDACT outcomes, signed off by the DPO role. Say where the engine runs. Rewrite the FR-8 test to match the outcome type of each dimension. Define how cached context packs are invalidated, and the cache key scope (agent_id, tier), when policy changes or deletion happen. (FND-004, FND-013, FND-028, FND-040, FND-006, FND-051)
- Prototype filtered pgvector/HNSW queries at the target scale before treating the SKU, growth ceiling and cost as confirmed. Measure latency at a defined load, recall and completeness of learner-scoped results, and memory fit. Reconcile the per-learner vector arithmetic and alumni growth. Define the scope of the NFR-10 cost figure. (FND-026, FND-035, FND-008, FND-052, FND-037, FND-038)
- Before the first term-end after launch, assign owners and due dates for the compaction design, audit-log retention and PDPA sign-off. Do not defer them beyond launch scope. (FND-007, FND-015, FND-042)
- Correct the DDL and the Section 28 readiness ratings. Add retention, expiry and pii columns where NFR-7 needs them, an embedded flag and keyword index for the BM25 fallback, and the audit, registry, backup and namespace tables. (FND-024, FND-032, FND-044)

| Objective | Verdict | Findings |
|---|---|---|
| P1 | fit with conditions | FND-021, FND-001, FND-030 |
| P2 | fit with conditions | FND-012, FND-047, FND-003, FND-054 |
| P3 | fit with conditions | FND-055, FND-004, FND-006, FND-040, FND-051 |
| P4 | fit with conditions | FND-020, FND-010, FND-045, FND-053 |
| P5 | fit | FND-034, FND-055 |
| P6 | fit with conditions | FND-002, FND-022, FND-049, FND-050 |
| P7 | fit with conditions | FND-048, FND-045, FND-029, FND-015, FND-042 |
| P8 | fit with conditions | FND-039, FND-017, FND-051 |
| P9 | fit | FND-019 |
| P10 | fit | FND-009 |
| NFR-1 | fit with conditions | FND-026, FND-035, FND-037, FND-052 |
| NFR-8 | fit with conditions | FND-004, FND-013 |

What would change this verdict: The verdict would move towards an unconditional fit if two things happen. First, a revised design closes the counselling override paths and brings agent backup memory under tiering, deletion and audit. Second, a pgvector benchmark at about 9.5M vectors shows learner-scoped filtered queries within NFR-2 with complete results on the chosen SKU. It would move to not_fit if any of the following holds: governance decides to keep Super Admin or MMP access to counselling data, or to keep backups that survive deletion, and no PDPA risk acceptance is recorded; the benchmark shows filtered HNSW cannot meet NFR-2 or fit in memory without changing the engine or tier; or external checks (Entra ID token lifetime, Event Hubs semantics) show that confirmed decisions cannot work as specified.

## Strengths

### FND-009 Clear, traceable statement of intent: principles, ID'd requirements, acceptance criteria and an honest readiness assessment

- **strength** · confidence 0.85 (high) · rank 48
- Disposition: **no change**

The design states ten governing principles with a precedence rule, ID'd functional and non-functional requirements, a pass/fail acceptance criterion for every requirement, and a candid component-level readiness assessment that names its own gaps. This makes the design reviewable against its own intent and directly supports the stated purpose of being implementable from the specification.

- Where: p.3 §2: "Each requirement carries an ID used again in Section 27"
- Where: p.26 §27: "Each requirement from Section 2 is validated by a specific method with a concrete pass/fail acceptance criterion."
- Where: p.6 §3: "These ten principles govern every design decision in the platform, from the schema of a single table to the shape"
- Evidence EV-060 (doc, supports): "Each requirement from Section 2 is validated by a specific method with a concrete pass/fail acceptance criterion." [doc:DOC-sit_sample_v1#p26/s27]
- Why no change is needed: The traceability structure is fit for the document's purpose of guiding implementation and review; the individual gaps are covered by other findings.

### FND-034 Requirement-by-requirement acceptance matrix with honest readiness assessment

- **strength** · confidence 0.85 (high) · rank 49
- Disposition: **no change**

Every FR and NFR in Section 2 has a named validation method and a concrete pass/fail criterion in Section 27, and Section 28 openly rates components Partial or Not ready where the spec is thin. This traceability is what the design's goal of build-readiness depends on. The defects found here are fixable refinements to individual criteria, not missing test coverage.

- Where: p.26 §27: "Each requirement from Section 2 is validated by a specific method with a concrete pass/fail acceptance criterion."
- Evidence EV-060 (doc, supports): "Each requirement from Section 2 is validated by a specific method with a concrete pass/fail acceptance criterion." [doc:DOC-sit_sample_v1#p26/s27]
- Why no change is needed: Full FR/NFR-to-test traceability already serves the stated build-readiness purpose.

### FND-010 Counselling hard wall enforced in layers: policy, schema and credentials, with matching tests

- **strength** · confidence 0.80 (high) · rank 50
- Disposition: **no change**

FR-5/P4 is enforced by Gateway sensitivity clearance, a physically separate memory_sensitive schema with its own credentials and embedding deployment, and dedicated tests (FR-5 cross-domain read, NFR-5 credential isolation). This defence in depth fits the stated objective of strict domain isolation for the most sensitive data, subject to the backup-memory and write-routing caveats in FND-001 and FND-002.

- Where: p.3 §2.1 (FR-5): "Memory Management Plane override path, enforced at both the policy-engine level and the"
- Where: p.27 §27.2 (NFR-5): "A credential valid for memory_standard is confirmed to fail authentication"
- Evidence EV-061 (doc, supports): "HIGHLY_RESTRICTED data shall be stored in a physically separate schema (memory_sensitive) with" [doc:DOC-sit_sample_v1#p4/s2.2]
- Why no change is needed: The layered enforcement and its tests serve FR-5, NFR-5 and P4 directly; no change is needed beyond the caveats raised in FND-001 and FND-002.

### FND-019 Explicit decision register, principle precedence and honest readiness gating

- **strength** · confidence 0.80 (high) · rank 51
- Disposition: **no change**

The design keeps a confirmed-decisions register (Section 25) separate from a pending backlog (Section 26). It declares that principles override conflicting later sections, and Section 28 rates each component's readiness and makes Build Phases 3, 6 and 7 wait on named specification gaps. Together these make preserving decisions traceable and stop unready components from being generated by guesswork. This supports the stated objective of a specification that is buildable.

- Where: p.6 §3: "Where a later section appears to conflict with one of these, the principle wins."
- Where: p.29 §28: "The honest answer is partial - strong in some areas, not"
- Evidence EV-086 (doc, supports): "Where a later section appears to conflict with one of these, the principle wins." [doc:DOC-sit_sample_v1#p6/s3]
- Evidence EV-087 (doc, supports): "Items confirmed as in-scope but not yet fully designed:" [doc:DOC-sit_sample_v1#p26/s26]
- Why no change is needed: The decision register, the principle-precedence rule and readiness gating already give clear governance of design decisions. Findings FND-020, FND-015 and FND-017 refine how they are applied, but the mechanism itself needs no change.

### FND-055 Ordered pre-retrieval Gateway checks with deny-and-log and per-check tests

- **strength** · confidence 0.80 (high) · rank 52
- Disposition: **no change**

Section 15 defines six ordered checks that gate the query itself, deny on any failure with a logged reason, and check read and write permissions separately. FR-4 is backed by one acceptance test per check. This gives a concrete, testable enforcement point for P3 and FR-4.

- Where: p.15 §15 (FR-4): "Access control is pre-retrieval. The namespace check gates the query itself - not the returned results."
- Where: p.26 §27.1 (FR-4): "Six test cases, one per check, each asserting a DENY with the correct reason"
- Evidence EV-156 (doc, supports): "Access control is pre-retrieval. The namespace check gates the query itself - not the returned results." [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-157 (doc, supports): "Six test cases, one per check, each asserting a DENY with the correct reason" [doc:DOC-sit_sample_v1#p26/s27.1]
- Why no change is needed: The checks fail closed, are logged and are testable per check, which directly meets FR-4 and P3.

## Risks

### FND-020 Counselling hard wall contradicted by Super Admin, MMP override and configurable named_agents

- **risk** · internal contradiction · severity **high** · confidence 0.80 (high) · rank 1
- Disposition: **governance decision** (also: refinement now, needs testing)

FR-5, P4 and Section 19 say wellbeing/counselling/ has no MMP override and no exceptions. Yet Section 19 gives the Super Admin access to 'Everything', Section 21 gives the super admin 'Overrides, corrections, emergency access', and Check 6 relies on a named_agents list held in the MMP-writable agent_registry, so the MMP can grant access. As written, the hard wall can be bypassed through governance paths, and the FR-5 test never tries them because it only covers three agents.

- Where: p.18 §19 (FR-5): "Super Admin Everything - always audit-logged, mandatory reason required"
- Where: p.15 §15 (FR-4, FR-5): "HIGHLY_RESTRICTED slots: hard block for all agents not in an"
- Where: p.3 §2.1 (FR-5): "wellbeing/counselling/ shall be classified HIGHLY_RESTRICTED with zero cross-domain reads and no"
- Evidence EV-070 (doc, supports): "Super Admin Everything - always audit-logged, mandatory reason required" [doc:DOC-sit_sample_v1#p18/s19]
- Evidence EV-071 (doc, supports): "Super admin Overrides, corrections, emergency access (always audit-logged)" [doc:DOC-sit_sample_v1#p20/s21]
- Evidence EV-092 (doc, supports): "agent_registry/ All registered agents, permitted slots, versions, owners" [doc:DOC-sit_sample_v1#p21/s22]
- Evidence EV-099 (inference, supports): "Because agent_registry is writable by the MMP only and holds permitted slots, an MMP or super-admin edit to named_agents is itself an MMP override path that FR-5 prohibits." [inference:EV-099] derived from EV-071, EV-092
- Evidence EV-072 (doc, supports): "wellbeing/counselling/ shall be classified HIGHLY_RESTRICTED with zero cross-domain reads and no" [doc:DOC-sit_sample_v1#p3/s2.1]
- Evidence EV-088 (inference, supports): "An unrestricted Super Admin/MMP override role is a cross-domain override path into memory_sensitive unless counselling is explicitly carved out, so FR-5 and the role model cannot both hold as written." [inference:EV-088] derived from EV-070, EV-071, EV-072
- Evidence EV-123 (inference, supports): "A test that only checks three agents and merely avoids the MMP path cannot show that Super Admin/MMP calls, other agents, cached context packs or memory_standard credentials are blocked from wellbeing/counselling/." [inference:EV-123] derived from EV-103, EV-104, EV-070
- Recommendation: In Section 19, exclude memory_sensitive from Super Admin and Institution Admin access. In Section 21, state that emergency access does not apply to counselling. Make the counselling named_agents list fixed at deployment (credential-level, not changeable by the MMP), or record an explicit, owned exception. Extend the FR-5 test to cover super-admin, Admin API and agent_registry-edit attempts.
  - Issue: The governance roles and the configurable clearance list contradict the absolute no-override rule for counselling memory.
  - Rationale: FR-5 and P4 say 'no exceptions', but Sections 19 and 21 and Check 6 each allow one.
  - Expected benefit: FR-5 and P4 become consistent and enforceable, and counselling data is protected from administrative access. (objectives: FR-5, P4, NFR-5)
  - Supporting evidence: EV-070, EV-071, EV-092, EV-099
  - Verification: Extend the FR-5 test: Super Admin reads via the Admin API and a named_agents edit via the MMP are both denied or rejected.
- Next step: Data governance officer / DPO: Decide whether any human or administrative break-glass access to counselling memory is permitted, then update Sections 15, 19 and 21 to match.
- Decision AD-016 (25 Confirmed Decisions - Counselling): preserves. The recommendation enforces the approved counselling hard wall by removing the admin and registry bypasses.
- Decision AD-036 (FR-5): preserves. FR-5's no-MMP-override, credential-level enforcement becomes consistent with the role model.
- Decision AD-034 (3 Foundational Principles): preserves. P4 wins over the conflicting Section 19/21 role scopes, as the precedence rule requires.
- Decision AD-024 (26 Pending Backlog - Agent Dimension): refines. Fixing named_agents for counselling at deployment constrains the pending agent-registration design.

### FND-021 Agent backup memory always used and survives deletion, defeating FR-15/FR-16

- **risk** · internal contradiction · severity **high** · confidence 0.80 (high) · rank 2
- Disposition: **refinement now** (also: governance decision)

FR-16 says the backup is used only when the namespace is unreachable. Sections 14 and 17, however, load the backup on every request as Source 3 to fill gaps. Sections 13 and 20 say the backup survives learner self-deletion, so data a learner deletes under FR-15 can come back into context through gap-filling. Where agent backup memory is stored and how its sensitivity tier is set are not specified either, so the counselling agent's backup may hold HIGHLY_RESTRICTED data outside memory_sensitive (NFR-5).

- Where: p.4 §2.1 (FR-16): "Each agent shall maintain its own per-learner backup memory, used only when the learner namespace is"
- Where: p.13 §14: "Source 3: Agent per-learner backup (fills gaps; backup only)"
- Where: p.13 §13 (FR-15): "survives learner deletion of their own memory (enabling session resume)"
- Evidence EV-093 (doc, supports): "Each agent shall maintain its own per-learner backup memory, used only when the learner namespace is" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-044 (doc, supports): "Source 3: Agent per-learner backup (fills gaps; backup only)" [doc:DOC-sit_sample_v1#p13/s14]
- Evidence EV-094 (doc, supports): "survives learner deletion of their own memory (enabling session resume)" [doc:DOC-sit_sample_v1#p13/s13]
- Evidence EV-043 (doc, supports): "Learners shall be able to request deletion of their own user-deletable memory." [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-100 (inference, supports): "A record deleted from the namespace becomes a 'gap' that Source 3 fills from the surviving backup, so the deletion has no effect on what the agent sees." [inference:EV-100] derived from EV-044, EV-094, EV-043
- Recommendation: Choose one rule for Sections 14 and 17: backup used only in degraded mode, or backup gap-filling allowed with FR-16 reworded. Add a deletion-propagation rule: learner deletion events purge or tombstone the matching agent backup entries. Specify where agent backup is stored and require HIGHLY_RESTRICTED backup data to sit under memory_sensitive credentials.
  - Issue: How the backup is used and retained contradicts FR-16 and undermines learner deletion under FR-15.
  - Rationale: The text supports two incompatible readings of when the backup is read, and gives no rule for propagating deletions.
  - Expected benefit: Learner deletion takes effect everywhere (FR-15, P2, PDPA), and the backup role matches FR-16 and P1. (objectives: FR-15, FR-16, NFR-5, P1, P2)
  - Supporting evidence: EV-093, EV-044, EV-094, EV-043, EV-100
  - Verification: Extend the FR-15 test: after deletion, a fresh read with the namespace available returns no deleted record from any source, including backup.
- Next step: Platform architect with DPO: Decide whether deletion propagates to agent backups and update Sections 13, 14, 17 and 20.

### FND-001 Agent per-learner backup memory sits outside the governed path and survives deletion

- **risk** · security privacy gap · severity **high** · confidence 0.75 (medium) · rank 4
- Disposition: **governance decision** (also: refinement now)

Section 5 says every memory operation flows through the governed path, and FR-16 limits backup memory to periods when the namespace is unreachable. However, Section 14 writes to the agent's own memory 'always, immediate' outside Kafka and the Gateway. Context assembly also loads the backup as Source 3 on every request to 'fill gaps', and Sections 13 and 20 keep the backup after a learner deletes their own memory. As written, a second, ungoverned copy of every learner's memory exists for each agent. That copy undermines FR-15 (deletion), FR-13 and P7 (audit of every operation), P2 (private by default) and the FR-16 'used only when unreachable' limit. For the counselling agent, the copy also holds HIGHLY_RESTRICTED data outside memory_sensitive.

- Where: p.19 §20 (FR-15): "Agent per-learner backup Survives learner self-deletion; enables session resume"
- Where: p.4 §2.1 (FR-16): "Each agent shall maintain its own per-learner backup memory, used only when the learner namespace is"
- Where: p.7 §5: "Every memory operation, from every agent, for every learner, flows through the same governed path."
- Evidence EV-042 (doc, supports): "Agent per-learner backup Survives learner self-deletion; enables session resume" [doc:DOC-sit_sample_v1#p19/s20]
- Evidence EV-043 (doc, supports): "Learners shall be able to request deletion of their own user-deletable memory." [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-044 (doc, supports): "Source 3: Agent per-learner backup (fills gaps; backup only)" [doc:DOC-sit_sample_v1#p13/s14]
- Evidence EV-062 (inference, supports): "Because the backup is written on every interaction, read on every context assembly and kept after self-deletion, deleted or HIGHLY_RESTRICTED learner data stays retrievable outside the namespace controls, so FR-15, FR-16 and P7 cannot all hold." [inference:EV-062] derived from EV-042, EV-043, EV-044
- Recommendation: In Sections 13, 14 and 20, specify the backup as a bounded cache: governed by the same policy dimensions, audited, scoped to the fields needed for degraded mode, excluded for HIGHLY_RESTRICTED slots (or held in a memory_sensitive-equivalent store), and purged when the learner deletes their own memory. Remove 'fills gaps' from Source 3 when the token is ACTIVE, or amend FR-16 to allow it. Extend the FR-15 test to assert the backup is purged.
  - Issue: The agent backup store has no governance: no Gateway check, no audit, no deletion propagation and no sensitivity tiering, and it is used outside degraded mode.
  - Rationale: FR-15, FR-13/P7 and FR-5 assume that the namespace is the only persistent copy, or at least a governed one.
  - Expected benefit: Learner deletion and the counselling hard wall stay effective, and FR-16 holds as written. (objectives: FR-15, FR-16, FR-13, FR-5, P2, P7)
  - Supporting evidence: EV-042, EV-043, EV-044, EV-062
  - Verification: Extended FR-15 deletion boundary test that inspects the agent backup; FR-13 audit completeness test that covers backup reads and writes.
- Next step: Data governance officer / DPO with the platform architect: Decide the retention and deletion semantics for agent backup memory, then update Sections 13, 14 and 20 and the FR-15/FR-16 criteria.

### FND-036 NFR-4 assumes the MMP is off the request path, but the Gateway and audit depend on MMP components

- **risk** · internal contradiction · severity **high** · confidence 0.75 (medium) · rank 6
- Disposition: **refinement now** (also: needs testing)

NFR-4 claims that MMP downtime cannot affect agent reads or writes because the MMP is not in the critical path. But Gateway Check 4 calls the MMP to provision missing slots during a request. The MMP also owns the PolicyEngine and the AuditStore, which every operation needs: FR-8 evaluates policy and FR-13 audits each one. If the MMP is down, requests touching new slots, policy evaluation or audit writes could fail or go unaudited. That undermines NFR-4 and P7.

- Where: p.4 §2.2 (NFR-4): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical"
- Where: p.15 §15 (FR-4): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed"
- Where: p.19 §21: "The MMP is a standalone admin service. It is not an agent and is not in the critical request path."
- Evidence EV-052 (doc, supports): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed" [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-130 (doc, supports): "+-- PolicyEngine -- cross-slot read permission decisions +-- AuditStore -- append-only log of every operation" [doc:DOC-sit_sample_v1#p20/s21]
- Evidence EV-139 (inference, supports): "Because slot provisioning, policy decisions and the audit store are MMP components invoked during live requests, the premise that MMP downtime cannot affect agent availability does not hold as designed." [inference:EV-139] derived from EV-052, EV-130
- Recommendation: In Sections 15, 16 and 21, state which runtime components (the policy evaluator, audit writer, and a provisioning queue) are deployed in the request path separately from the MMP admin service. Define Check 4 behaviour when the MMP is unavailable, for example deny-and-log or defer through a queue. Extend the NFR-4 test in Section 27.2 to include a write to a not-yet-provisioned slot and an audit-completeness check while the MMP is down.
  - Issue: The availability premise of NFR-4 contradicts the dependencies shown in Sections 15 and 21.
  - Rationale: The NFR-4 chaos test would fail, or would pass only by skipping slot provisioning or audit, if these dependencies are not separated.
  - Expected benefit: NFR-4 becomes achievable without weakening FR-8 or FR-13. (objectives: NFR-4, FR-8, FR-13)
  - Supporting evidence: EV-052, EV-130, EV-139
  - Verification: MMP-down chaos test that includes auto-provisioning and audit-completeness assertions.
- Next step: Solution architect: Separate the runtime policy and audit services from the MMP admin plane in Sections 16 and 21, and define the Check 4 fallback.

### FND-002 Async write ordering: ACK before validation, topic chosen before classification, embedding before validation

- **risk** · scalability or failure mode · severity **high** · confidence 0.70 (medium) · rank 7
- Disposition: **refinement now** (also: needs testing)

FR-9 acknowledges the agent at enqueue time. The Kafka topic (standard or sensitive) is chosen at enqueue, but sensitivity is only 'confirmed' by the consumer's Classify step afterwards. Validation runs after embedding. As a result: (a) a strict-mode rejection under FR-11 cannot reach the agent, which has already received an ACK, and the design defines no rejection or dead-letter feedback path; (b) content that classification raises to HIGHLY_RESTRICTED has already passed through the standard topic, which contradicts the claim that separate topics keep it isolated in transit; (c) invalid or HIGHLY_RESTRICTED content may be sent to the standard embedding deployment before it is rejected.

- Where: p.4 §2.1 (FR-9): "processed asynchronously by a background consumer performing classify → embed → validate → route →"
- Where: p.17 §18: "embedding, SIS sync) read the same event stream; separate topics per sensitivity tier keep HIGHLY_RESTRICTED"
- Where: p.6 §3 (P6): "No uncontrolled self-writing - all writes are classified and policy-checked before storage."
- Evidence EV-045 (doc, supports): "Writes shall be enqueued to a message broker (agent receives an immediate acknowledgement) and" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-046 (doc, supports): "processed asynchronously by a background consumer performing classify → embed → validate → route →" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-047 (doc, supports): "embedding, SIS sync) read the same event stream; separate topics per sensitivity tier keep HIGHLY_RESTRICTED" [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-063 (inference, supports): "Topic selection happens before the consumer classifies sensitivity, and validation happens after the ACK and after embedding, so tier isolation in transit and agent-visible strict-mode rejection cannot both be guaranteed." [inference:EV-063] derived from EV-045, EV-046, EV-047
- Recommendation: In Section 18 and FR-9, run the cheap synchronous checks at the Gateway before enqueue: the declared sensitivity against the slot ceiling (which selects the topic) and the template key check. Reorder the consumer to classify → validate → embed → route → audit. Define a rejection/dead-letter topic plus a write-status or callback mechanism, and state what happens when the consumer reclassifies to a higher tier (re-route without persisting to the standard tier).
  - Issue: Sensitivity routing and template validation happen too late in the write pipeline, and rejected writes have no feedback path.
  - Rationale: FR-5/NFR-5 isolation and FR-11 strict mode both assume that classification and validation happen before data moves or is processed.
  - Expected benefit: HIGHLY_RESTRICTED isolation holds end to end, and agents learn when a write was rejected. (objectives: FR-9, FR-11, FR-5, NFR-5, P6)
  - Supporting evidence: EV-045, EV-046, EV-047, EV-063
  - Verification: Test: write a HIGHLY_RESTRICTED-classified payload declared as INTERNAL and assert it never lands on memory.write.standard or the standard embedding deployment; the FR-11 test asserts the agent can observe the rejection.

### FND-012 Agent backup deliberately retains data after a learner deletes it

- **risk** · security privacy gap · severity **high** · confidence 0.70 (medium) · rank 8
- Disposition: **governance decision** (also: refinement now)

Section 13 and Section 20 state that each agent's per-learner backup survives the learner's deletion of their own memory, so that sessions can resume. FR-15 promises learner-initiated deletion and P2 promises 'private by default'. As designed, deleted data stays in up to six agent stores, and Section 14 phase 3 can serve it back into context whenever it fills gaps in the namespace. No owner has been assigned to decide whether this retention is acceptable under PDPA, and no deletion acceptance test covers the backups.

- Where: p.13 §13: "the agent backup survives learner deletion of their own memory (enabling session resume)"
- Where: p.4 §2.1 (FR-15): "Learners shall be able to request deletion of their own user-deletable memory."
- Where: p.6 §3 (P2): "Private by default - memory is private to the learner, shared by exception, anonymised for service"
- Evidence EV-073 (doc, supports): "the agent backup survives learner deletion of their own memory (enabling session resume)" [doc:DOC-sit_sample_v1#p13/s13]
- Evidence EV-043 (doc, supports): "Learners shall be able to request deletion of their own user-deletable memory." [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-089 (inference, supports): "Because the backup fills gaps in the context pack (Section 14 Source 3), data a learner deleted from the namespace can reappear in agent context, which defeats the purpose of FR-15." [inference:EV-089] derived from EV-073, EV-043
- Recommendation: Have the DPO decide the deletion scope. Recommended: propagate learner deletions to agent per-learner backups, for example through a deletion event on Kafka consumed by every agent, keeping only non-content session metadata. Record the outcome in Section 25 and amend Sections 13 and 20. Extend the FR-15 test to assert that backups are purged.
  - Issue: The backup-retention rule undermines learner deletion, and no accountable owner has decided on it.
  - Rationale: Deletion and PDPA obligations are governance matters, and the current rule is an engineering convenience (session resume).
  - Expected benefit: FR-15 and P2 are honoured end-to-end, and the deletion scope is defensible to the DPO. (objectives: FR-15, P2, NFR-7)
  - Supporting evidence: EV-073, EV-043, EV-089
  - Verification: FR-15 deletion boundary test checks that every registered agent's backup holds no deleted content and that no context pack returns it.
- Next step: Data Protection Officer: Rule on whether agent backups fall within learner deletion scope, and record the decision in Section 25.

### FND-047 Revoked token still yields learner data via agent backup

- **risk** · security privacy gap · severity **high** · confidence 0.70 (medium) · rank 9
- Disposition: **governance decision** (also: refinement now)

On REVOKED, the design keeps serving the session from the agent's per-learner backup. Revocation usually signals a compromised account or a terminated relationship, so continuing to surface that learner's stored memory to the unauthenticated requester defeats the purpose of revoking. The same applies, more mildly, to EXPIRED tokens, where serving continues before re-authentication.

- Where: p.8 §6 (NFR-6): "On revocation: inform the learner, serve from agent backup only, no re-authentication path is offered."
- Where: p.15 §15 (FR-4): "REVOKED -> inform learner (token revoked, contact support)."
- Evidence EV-148 (doc, supports): "On revocation: inform the learner, serve from agent backup only, no re-authentication path is offered." [doc:DOC-sit_sample_v1#p8/s6]
- Evidence EV-159 (inference, supports): "If the requester behind a revoked token is not the learner, serving from the backup discloses that learner's memory to the person whose access was just cut off." [inference:EV-159] derived from EV-148
- Recommendation: In Sections 6, 14 and 15: on REVOKED, serve only agent-global (non-learner) context and load no per_learner backup. On EXPIRED, limit backup use to the current session's working memory until re-authentication.
  - Issue: Degraded mode on REVOKED discloses stored learner memory.
  - Rationale: Revocation is the control used to stop access, and the backup holds the same personal data as the namespace.
  - Expected benefit: Revocation would be effective, protecting learner privacy (P2) and FR-4 check 3. (objectives: FR-4, NFR-6, P2)
  - Supporting evidence: EV-148, EV-159
  - Verification: Extend the NFR-6 test: with a REVOKED token, the context pack contains no per-learner entries.
- Next step: Platform security lead: Decide degraded-mode scope per token state and update Sections 6, 14 and 15.

### FND-003 REVOKED tokens still receive learner-specific memory from the agent backup

- **risk** · security privacy gap · severity **high** · confidence 0.65 (medium) · rank 10
- Disposition: **governance decision** (also: refinement now)

Sections 6, 15 and 25 specify that on revocation the agent serves 'from agent backup only'. Revocation is the control used when an account is compromised or a learner's access is withdrawn. Continuing to serve per-learner memory to the holder of a revoked session defeats it. This also conflicts with Check 2's statement that learner memory cannot be accessed without identity. The review frames this as a refinement within the approved token-window decision, not a challenge to the 48-hour window itself.

- Where: p.8 §6 (NFR-6): "continue serving on the agent's backup memory. On revocation: inform the learner, serve from agent backup"
- Where: p.25 §25: "Auth token window 48 hours; EXPIRED → re-auth + agent backup; REVOKED → backup only"
- Evidence EV-048 (doc, supports): "continue serving on the agent's backup memory. On revocation: inform the learner, serve from agent backup" [doc:DOC-sit_sample_v1#p8/s6]
- Evidence EV-049 (doc, supports): "FAIL -> denied. Cannot access learner memory without identity." [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-064 (inference, supports): "If revocation still yields per-learner context from the backup, a revoked or compromised session keeps access to that learner's memory, which defeats revocation." [inference:EV-064] derived from EV-048, EV-049
- Recommendation: In Sections 6, 15 and 25, change REVOKED to 'no per-learner memory served; agent global only'. Keep backup-serving for EXPIRED only, bounded by a maximum degraded-session duration. Add an NFR-6 test asserting that no per_learner content is served on a REVOKED token.
  - Issue: Revoked-token behaviour keeps learner-specific memory flowing.
  - Rationale: Revocation must cut access to personal data. Only EXPIRED, where identity was valid recently, plausibly justifies degraded continuity.
  - Expected benefit: NFR-6 degraded-mode behaviour no longer exposes personal data after revocation. (objectives: NFR-6, FR-4, P2)
  - Supporting evidence: EV-048, EV-049, EV-064
  - Verification: NFR-6 token lifecycle test extended with a REVOKED-token context request that returns no learner-specific memory.
- Next step: Information security lead with the DPO: Decide revoked-session behaviour and amend the auth decision in Section 25 accordingly.

### FND-048 Audit completeness depends on async consumer and MMP-hosted AuditStore

- **risk** · scalability or failure mode · severity **high** · confidence 0.65 (medium) · rank 13
- Disposition: **refinement now** (also: needs testing) · already acknowledged in the document

The write audit entry is the last step of the background consumer, so a consumer crash, a poison message or a validation reject before that step can leave an ACKed write with no audit entry. The AuditStore is listed as an MMP component, yet NFR-4 says MMP downtime must not affect agent reads and writes. The design does not say where read and denial audits are written when the MMP is down, or whether operations block when audit fails. FR-13 and P7 (PDPA) need a defined, fail-closed or durably buffered audit path.

- Where: p.3 §2.1 (FR-9): "processed asynchronously by a background consumer performing classify → embed → validate → route →"
- Where: p.4 §2.2 (NFR-4): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical"
- Where: p.8 §5: "AuditStore, Admin API (port 8003), and a dashboard for quality, PII, usage, cost, and warnings."
- Evidence EV-046 (doc, supports): "processed asynchronously by a background consumer performing classify → embed → validate → route →" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-076 (doc, supports): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical" [doc:DOC-sit_sample_v1#p4/s2.2]
- Evidence EV-149 (doc, supports): "AuditStore, Admin API (port 8003), and a dashboard for quality, PII, usage, cost, and warnings." [doc:DOC-sit_sample_v1#p8/s5]
- Evidence EV-160 (inference, supports): "If the audit sink is part of the MMP, then either audit entries are lost while the MMP is down (breaking FR-13) or agent operations fail (breaking NFR-4)." [inference:EV-160] derived from EV-076, EV-149
- Recommendation: In Sections 17, 18 and 21: place the audit sink in the request path, separate from the MMP (for example a dedicated append-only audit topic and table). Write the enqueue audit at the Gateway before the ACK and the outcome audit at the consumer, including validation rejects. Define fail-closed or buffered behaviour if the audit sink is unavailable.
  - Issue: The audit write point and its failure behaviour are undefined.
  - Rationale: PDPA auditability (P7) must hold under partial failure, and NFR-4 isolates the MMP.
  - Expected benefit: FR-13 completeness and NFR-4 availability can both be met. (objectives: FR-13, NFR-4, P7)
  - Supporting evidence: EV-046, EV-076, EV-149, EV-160
  - Verification: Combine the NFR-4 chaos test with the FR-13 completeness test: with the MMP stopped and a consumer killed mid-batch, every operation still has exactly one audit entry.
- Next step: Platform architect: Specify the audit sink placement and failure semantics as part of Pending Backlog item 4.

### FND-024 DDL declared 'complete' but lacks columns that other sections require

- **risk** · internal contradiction · severity **medium** · confidence 0.80 (high) · rank 15
- Disposition: **refinement now**

Section 28 calls the DDL concrete and complete. But memory_events and memory_documents have no expires_at, retention or pii columns, which NFR-7 needs for per-slot retention and pii flagging. memory_vectors has no 'embedded' flag and no keyword index for the BM25 fallback in Section 17. memory_events has no key column, although the Validator checks keys for EPISODIC template entries such as quiz_history. Generating migrations 'directly' as Section 28 suggests would produce a schema that cannot meet NFR-7 or the embedder fallback.

- Where: p.29 §28: "Nothing further needed - DDL is concrete and complete (Section"
- Where: p.4 §2.2 (NFR-7): "All operations on personal data shall be logged; retention rules shall be enforceable per slot; PII-bearing"
- Where: p.12 §11: "DDL for the three table types. This DDL is duplicated once per schema (memory_standard, memory_sensitive)."
- Evidence EV-096 (doc, supports): "Nothing further needed - DDL is concrete and complete (Section" [doc:DOC-sit_sample_v1#p29/s28]
- Evidence EV-097 (doc, supports): "- Flag record as unembedded (embedded: false)" [doc:DOC-sit_sample_v1#p16/s17]
- Evidence EV-098 (doc, supports): "- Fall back to BM25 keyword search for retrieval" [doc:DOC-sit_sample_v1#p16/s17]
- Evidence EV-102 (inference, supports): "The memory_events and memory_documents DDL in Section 11 has no pii, retention or expires_at columns, and memory_vectors has no embedded column or text-search index, so the stated behaviours have nowhere to live." [inference:EV-102] derived from EV-096, EV-097, EV-098
- Recommendation: In Section 11, add retention, expires_at and pii to all three tables. Add a key column to memory_events. Add embedded BOOLEAN and a tsvector column with a GIN index to memory_vectors. Downgrade the Section 28 rating to 'Mostly ready' until this is done.
  - Issue: The schema does not support retention, PII flagging, the unembedded flag or the BM25 fallback.
  - Rationale: NFR-7 and the Section 17 fallback depend on columns that are missing from the DDL.
  - Expected benefit: NFR-7 becomes verifiable and the embedder fallback becomes implementable, and the readiness claim becomes accurate. (objectives: NFR-7, FR-13, FR-15)
  - Supporting evidence: EV-096, EV-097, EV-098, EV-102
  - Verification: Run the NFR-7 schema scan across all three tables, and an embedder-outage test that confirms BM25 retrieval of unembedded rows.

### FND-005 Gateway Check 4 calls the MMP in the request path, contrary to NFR-4

- **risk** · internal contradiction · severity **medium** · confidence 0.70 (medium) · rank 20
- Disposition: **refinement now** (also: needs testing)

NFR-4 and Section 21 state that the MMP is not in the critical request path, so MMP downtime cannot affect agents. Gateway Check 4, however, has the MMP provision missing auto-provisionable slots in-line during a request. Section 8 also lists PolicyEngine as an MMP component. As written, an MMP outage would fail first-time writes to new slots (and possibly policy evaluation), so NFR-4 is not achievable without clarification.

- Where: p.15 §15 (FR-4): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed"
- Where: p.4 §2.2 (NFR-4): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical"
- Evidence EV-052 (doc, supports): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed" [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-053 (doc, supports): "The MMP is a standalone admin service. It is not an agent and is not in the critical request path." [doc:DOC-sit_sample_v1#p19/s21]
- Evidence EV-066 (inference, supports): "A synchronous MMP provisioning call inside Check 4 places the MMP on the request path for any not-yet-provisioned slot, so MMP downtime affects those requests." [inference:EV-066] derived from EV-052, EV-053
- Recommendation: In Section 15 Check 4, define provisioning through a Gateway-local provisioner using cached published templates, or deny with a retryable code and an async provisioning request. Clarify in Sections 5, 8 and 21 that the runtime policy evaluation lives in the Gateway. Extend the NFR-4 test to include a first write to an unprovisioned auto-provisionable slot.
  - Issue: In-line provisioning and the placement of PolicyEngine contradict NFR-4.
  - Rationale: NFR-4 availability depends on the MMP never being called synchronously by the Gateway.
  - Expected benefit: NFR-4 holds and the MMP-down chaos test is meaningful. (objectives: NFR-4, FR-4)
  - Supporting evidence: EV-052, EV-053, EV-066
  - Verification: NFR-4 chaos test with the MMP stopped, covering a new-slot write.

### FND-014 MMP sits in the request path despite NFR-4

- **risk** · internal contradiction · severity **medium** · confidence 0.70 (medium) · rank 21
- Disposition: **refinement now**

NFR-4 states that the MMP is not in the critical request path. However, Gateway Check 4 has the MMP provision missing auto-provisionable slots inline before proceeding. Section 21 also places the PolicyEngine inside the MMP, while Section 16 requires policy to be evaluated fresh on every request with no caching. If either holds, MMP downtime blocks agent reads and writes, and the NFR-4 chaos test would not catch the failure unless it exercises unprovisioned slots.

- Where: p.15 §15 (FR-4): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed"
- Where: p.4 §2.2 (NFR-4): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical"
- Where: p.16 §16 (FR-8): "Policy decisions are not cached - they are evaluated fresh on every request"
- Evidence EV-052 (doc, supports): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed" [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-076 (doc, supports): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical" [doc:DOC-sit_sample_v1#p4/s2.2]
- Evidence EV-077 (doc, supports): "Policy decisions are not cached - they are evaluated fresh on every request" [doc:DOC-sit_sample_v1#p16/s16]
- Recommendation: In Section 15 Check 4, specify behaviour when the MMP is down: deny with reason MMP_UNAVAILABLE, or provision from a Gateway-local template cache. In Sections 5, 16 and 21, state whether the runtime Policy Engine is a Gateway-side library or service distinct from the MMP PolicyEngine. Extend the NFR-4 test to include a first write to an unprovisioned module slot.
  - Issue: Inline provisioning, and possibly policy evaluation, depend on the MMP at request time.
  - Rationale: NFR-4 is a stated availability objective, and the design should make clear which runtime components the Gateway depends on.
  - Expected benefit: NFR-4 holds in practice, and operators know which components are tier-1. (objectives: NFR-4, FR-4)
  - Supporting evidence: EV-052, EV-076, EV-077
  - Verification: The NFR-4 chaos test with the MMP stopped covers both a first write to an unprovisioned slot and a policy-evaluated read.

### FND-023 MMP placed in the request path despite NFR-4

- **risk** · internal contradiction · severity **medium** · confidence 0.70 (medium) · rank 22
- Disposition: **refinement now** (also: needs testing)

NFR-4 says the MMP is not in the critical request path. However, Gateway Check 4 has the MMP provision missing slots inline before proceeding, and Sections 5 and 21 list PolicyEngine and AuditStore as MMP components, while policies are evaluated fresh on every request and every operation must be audited. If those components run in the MMP service, MMP downtime blocks reads and writes, and the NFR-4 chaos test would fail.

- Where: p.15 §15 (FR-4): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed"
- Where: p.4 §2.2 (NFR-4): "MMP downtime shall not affect agent read or write availability, because the MMP is not in the critical"
- Evidence EV-052 (doc, supports): "Not exists + auto-provisionable slot type -> MMP provisions slot, proceed" [doc:DOC-sit_sample_v1#p15/s15]
- Evidence EV-095 (doc, supports): "● Memory Management Plane - TemplateRegistry, NamespaceRegistry, SlotProvisioner, PolicyEngine," [doc:DOC-sit_sample_v1#p8/s5]
- Evidence EV-054 (doc, supports): "evaluated fresh on every request, so that a rule change takes effect immediately rather than waiting for a cache" [doc:DOC-sit_sample_v1#p16/s16]
- Recommendation: In Section 15 Check 4, either deny with 'slot pending' and enqueue provisioning, or move SlotProvisioner logic into the request-path service. In Sections 5 and 21, state that the runtime Policy Engine and audit writer are request-path services and the MMP only configures them.
  - Issue: Inline provisioning and per-request policy and audit components are attributed to the MMP.
  - Rationale: This contradicts NFR-4, and the MMP-down test cannot pass if it holds.
  - Expected benefit: NFR-4 becomes achievable and agent availability does not depend on the admin plane. (objectives: NFR-4, FR-4, FR-8, FR-13)
  - Supporting evidence: EV-052, EV-095, EV-054
  - Verification: In the NFR-4 chaos test, include a first-access slot and policy-evaluated reads with the MMP stopped.

### FND-040 The claim that policy changes take effect immediately conflicts with the session-cached, already-redacted context pack

- **risk** · internal contradiction · severity **medium** · confidence 0.70 (medium) · rank 26
- Disposition: **refinement now**

Section 16 claims that policy decisions are never cached, so a rule change takes effect immediately. Section 18, however, applies redaction before writing the context pack to Redis and serves it for the whole session on a cache hit. A revoked permission or a tightened redaction rule would therefore not apply to cached content until the session ends. That weakens the Recall and Redaction dimensions of FR-8.

- Where: p.16 §16 (FR-8): "evaluated fresh on every request, so that a rule change takes effect immediately rather than waiting for a cache"
- Where: p.18 §18 (FR-10): "session context pack is cached so repeated queries within a session skip PostgreSQL entirely; TTL is aligned to"
- Evidence EV-134 (doc, supports): "Rank (relevance + recency) -> Budget (token limit) -> Redact (sensitivity) | Write result to Redis (TTL = session duration)" [doc:DOC-sit_sample_v1#p18/s18]
- Evidence EV-143 (inference, supports): "Because redaction output is cached for the session, a policy change cannot affect already-cached context until the TTL expires or the session closes." [inference:EV-143] derived from EV-134
- Recommendation: In Section 18, add cache invalidation on policy or template publication and on deletion events, for example a policy-version key in the cache entry. Alternatively, restate Section 16 to bound the delay to the session TTL. Add a test to Section 27 in which a mid-session policy change is reflected on the next read.
  - Issue: The immediacy claim does not hold for cached context packs.
  - Rationale: Policy revocations (for example a withdrawn permission, or a learner's deletion request) must not be served stale.
  - Expected benefit: FR-8 recall and redaction decisions are enforced consistently with Section 16. (objectives: FR-8, FR-10, FR-15)
  - Supporting evidence: EV-134, EV-143
  - Verification: Integration test: change a redaction rule mid-session and assert that the next read is re-evaluated.

### FND-007 Compaction deferred past launch, although term-end and graduation lifecycle rules depend on it

- **risk** · decision depends on pending item · severity **medium** · confidence 0.65 (medium) · rank 28
- Disposition: **governance decision** (also: refinement now) · already acknowledged in the document

Section 28 says compaction can be deferred because it is not needed for the initial six agents' launch scope. However, the Section 20 lifecycle rules (module tutor/lab memory compacted at end of term), the FR-12 graduation trigger and the alumni sizing all depend on it. The first term-end after launch would therefore arrive with no defined behaviour. The review adds that this deferral rationale does not hold against the design's own lifecycle and retention objectives.

- Where: p.30 §28: "The remaining Pending Backlog items (cohort namespace, compaction, non-SIT identity) can"
- Where: p.19 §20 (NFR-7): "modules/<code>/tutor, lab Term-scoped End of term: compacted to episodic summary; raw archived"
- Where: p.4 §2.1 (FR-12): "SIS events - registration, programme enrolment, module registration, module withdrawal, graduation -"
- Evidence EV-056 (doc, supports): "The remaining Pending Backlog items (cohort namespace, compaction, non-SIT identity) can" [doc:DOC-sit_sample_v1#p30/s28]
- Evidence EV-057 (doc, supports): "modules/<code>/tutor, lab Term-scoped End of term: compacted to episodic summary; raw archived" [doc:DOC-sit_sample_v1#p19/s20]
- Evidence EV-068 (inference, supports): "Term-scoped module slots reach end of term within the first academic term after launch, so compaction behaviour is needed within launch scope, not later." [inference:EV-068] derived from EV-056, EV-057
- Recommendation: Move a minimal term-end and graduation rule (at least: archive raw records, mark the slot expired, no summarisation) into the Phase 2/5 scope in Section 29. Leave full summarisation-fidelity design in the backlog.
  - Issue: The deferral rationale contradicts the lifecycle rules.
  - Rationale: Retention enforcement (NFR-7) and FR-12 graduation handling need at least a minimal compaction/archival rule at launch.
  - Expected benefit: Lifecycle and retention rules can be enforced from the first term-end. (objectives: FR-12, NFR-7)
  - Supporting evidence: EV-056, EV-057, EV-068
  - Verification: FR-12 simulation test covering module term-end and graduation, verified against the namespace map.
- Next step: Platform architect: Define the minimal launch compaction/archival rule and re-plan the build phases.

### FND-050 Sensitivity confirmed only after topic selection; single embedding model in write pipeline

- **risk** · security privacy gap · severity **medium** · confidence 0.60 (medium) · rank 37
- Disposition: **refinement now**

The tier topic is chosen at enqueue time, but the consumer's first step 'confirms' sensitivity. A write the classifier upgrades to HIGHLY_RESTRICTED has therefore already passed through memory.write.standard. The pipeline also embeds before validating, so content that will be rejected is still sent to the embedding service. Section 11 calls for a separate embedding deployment for the sensitive tier, while the pipeline names a single model, so the sensitive-tier isolation claim is not carried through end to end.

- Where: p.17 §18: "separate topics per sensitivity tier keep HIGHLY_RESTRICTED writes physically isolated in transit."
- Where: p.3 §2.1 (FR-9): "processed asynchronously by a background consumer performing classify → embed → validate → route →"
- Evidence EV-151 (doc, supports): "separate topics per sensitivity tier keep HIGHLY_RESTRICTED writes physically isolated in transit." [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-046 (doc, supports): "processed asynchronously by a background consumer performing classify → embed → validate → route →" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-162 (inference, supports): "Because classification happens after topic routing and embedding happens before validation, misclassified or invalid sensitive content can transit the standard topic and the embedding service." [inference:EV-162] derived from EV-151, EV-046
- Recommendation: In Section 18 and FR-9: derive the tier from the slot's template ceiling at the Gateway before choosing a topic, and fail closed (route to sensitive) when unknown. Reorder the consumer to classify → validate → embed → route → audit. State that consumers on the sensitive topic use the separate embedding deployment named in Section 11.
  - Issue: Tier routing and embedding precede the checks that should govern them.
  - Rationale: NFR-5 and FR-5 rely on HIGHLY_RESTRICTED data never entering standard-tier components.
  - Expected benefit: End-to-end tier isolation for counselling data. (objectives: FR-5, NFR-5, FR-9)
  - Supporting evidence: EV-151, EV-046, EV-162
  - Verification: Test: a write to wellbeing/counselling/ never appears on memory.write.standard, and a rejected write produces no embedding call.

## Gaps

### FND-045 Agent per-learner backup memory sits outside governance, deletion and audit

- **gap** · security privacy gap · severity **high** · confidence 0.80 (high) · rank 3
- Disposition: **refinement now** (also: governance decision)

Each agent keeps a full per-learner copy (session, episodic, long_term, procedural). It is written 'always, immediate', outside the Kafka/Gateway path, and it deliberately survives learner self-deletion. This contradicts the claim that every operation flows through the governed path. It also undermines FR-15 deletion, FR-13 audit completeness and the counselling hard wall: the counsellor agent's backup would hold HIGHLY_RESTRICTED data outside memory_sensitive. No sensitivity tier, retention rule, policy check or audit applies to the backup.

- Where: p.13 §13 (FR-16): "the agent backup survives learner deletion of their own memory (enabling session resume)"
- Where: p.4 §2.1 (FR-15): "Learners shall be able to request deletion of their own user-deletable memory."
- Where: p.7 §5: "Every memory operation, from every agent, for every learner, flows through the same governed path."
- Evidence EV-073 (doc, supports): "the agent backup survives learner deletion of their own memory (enabling session resume)" [doc:DOC-sit_sample_v1#p13/s13]
- Evidence EV-043 (doc, supports): "Learners shall be able to request deletion of their own user-deletable memory." [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-146 (doc, supports): "Every memory operation, from every agent, for every learner, flows through the same governed path." [doc:DOC-sit_sample_v1#p7/s5]
- Evidence EV-158 (inference, supports): "A deleted record that persists in every agent's backup is not deleted in substance, and backup writes that bypass the Router are neither policy-checked nor audited, so FR-13, FR-15 and P7 cannot all hold as written." [inference:EV-158] derived from EV-073, EV-043, EV-146
- Recommendation: In Sections 13, 20 and FR-16: (a) apply tier, retention and pii rules to agent backup; (b) propagate learner deletion to backups, or limit backup to a short-lived cache with a TTL; (c) forbid HIGHLY_RESTRICTED content in backups outside memory_sensitive; (d) audit backup reads and writes. Add the backup to the FR-15 test.
  - Issue: Agent backup memory is an ungoverned second copy of learner data. It outlives deletion and holds counselling data outside the sensitive tier.
  - Rationale: FR-15, FR-13, P4 and P7 all assume that the namespace is the only governed copy of learner data.
  - Expected benefit: Deletion, audit and the counselling hard wall would hold across every copy of learner data. (objectives: FR-13, FR-15, FR-5, FR-16, P7)
  - Supporting evidence: EV-073, EV-043, EV-146, EV-158
  - Verification: Extend the FR-15 deletion boundary test: after a learner deletion, each agent's backup holds no user-deletable records. Extend the FR-13 audit test to cover backup reads.
- Next step: Data governance officer / DPO: Decide the retention and deletion policy for agent backups and record it in Section 20.

### FND-022 Async write path has no rejection, dead-letter or feedback path after ACK

- **gap** · scalability or failure mode · severity **high** · confidence 0.75 (medium) · rank 5
- Disposition: **refinement now** (also: needs testing)

FR-9 acknowledges a write as soon as it is enqueued, but validation (FR-11 strict REJECT, type and sensitivity-ceiling checks) and classification run later in the consumer. No path tells the agent, or surfaces anywhere, that an acknowledged write was rejected. The claim that 'failed writes queue and retry automatically' gives no limit or dead-letter queue, so writes that will always fail validation may retry indefinitely. The Kafka topic is also chosen before Classify runs, so content reclassified as HIGHLY_RESTRICTED may already have passed through the standard topic.

- Where: p.4 §2.1 (FR-9, FR-11): "Writes shall be enqueued to a message broker (agent receives an immediate acknowledgement) and"
- Where: p.17 §18 (FR-9): "failed writes queue and retry automatically; multiple independent consumers (audit,"
- Where: p.17 §18 (NFR-5): "embedding, SIS sync) read the same event stream; separate topics per sensitivity tier keep HIGHLY_RESTRICTED"
- Evidence EV-045 (doc, supports): "Writes shall be enqueued to a message broker (agent receives an immediate acknowledgement) and" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-080 (doc, supports): "failed writes queue and retry automatically; multiple independent consumers (audit," [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-046 (doc, supports): "processed asynchronously by a background consumer performing classify → embed → validate → route →" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-101 (inference, supports): "Validation happens after the ACK and after embedding, so rejected writes are silently lost (or retried forever) and embedding cost is incurred on writes that are then rejected." [inference:EV-101] derived from EV-045, EV-080, EV-046
- Recommendation: In Sections 17 and 18, run schema validation (key, type, sensitivity ceiling) synchronously at the Gateway before enqueue, or define a dead-letter topic with an audit entry, a dashboard surface and an agent-visible status lookup. Add bounded retries for transient errors only. Choose the sensitivity topic after a synchronous tier determination, or forbid the consumer from upgrading the tier.
  - Issue: Rejected or poison writes after ACK have no defined outcome.
  - Rationale: FR-11 rejection is unobservable to the agent, and retry semantics do not separate transient from permanent failures.
  - Expected benefit: Writes are not lost silently, retry storms are prevented, and FR-11 and NFR-5 isolation hold in practice. (objectives: FR-9, FR-11, NFR-3, NFR-5, P6)
  - Supporting evidence: EV-045, EV-080, EV-046, EV-101
  - Verification: Test: a strict-mode write with an unknown key is either rejected synchronously or lands in the dead-letter queue with an audit entry, and is not retried more than N times.

### FND-004 Policy Engine combination logic is unspecified, and the FR-8 test assumes every dimension yields DENY

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.80 (high) · rank 14
- Disposition: **refinement now** · already acknowledged in the document

Section 28 acknowledges that the seven-dimension decision algorithm is not specified. The review adds two points. First, the FR-8 acceptance test expects each dimension to produce a DENY, yet Redaction and Retention produce masking and expiry outcomes rather than denials, so the test cannot validate the requirement as written. Second, the design does not say where the engine runs: Section 15's six Gateway checks, Section 16, and an MMP 'PolicyEngine' component all claim the role. Because the engine is the core of P3 (pre-retrieval control), this gap is on the critical path for the six-agent launch.

- Where: p.27 §27.1 (FR-8): "A test matrix exercises all seven dimensions independently (one violating"
- Evidence EV-050 (doc, supports): "the decision algorithm - how the seven dimensions combine into a single ALLOW/DENY/REDACT outcome, and their" [doc:DOC-sit_sample_v1#p29/s28]
- Evidence EV-051 (doc, supports): "Redaction Should part of the memory be masked before serving to this agent?" [doc:DOC-sit_sample_v1#p15/s16]
- Evidence EV-065 (inference, supports): "A redaction or retention outcome is not a DENY, so a test requiring a DENY per dimension cannot pass against a correct engine." [inference:EV-065] derived from EV-050, EV-051
- Recommendation: Add a decision table to Section 16 giving the outcome type per dimension (ALLOW/DENY/REDACT/EXPIRE) and the precedence rules. State that the engine runs in-process at the Gateway, with MMP only publishing rules. Rewrite the FR-8 criterion as 'each dimension produces its expected outcome type attributable to that dimension'.
  - Issue: There is no decision table, the engine has no defined location, and the FR-8 criterion does not match the outcome types.
  - Rationale: FR-8 and P3 cannot be built or verified without these.
  - Expected benefit: FR-8 becomes implementable and testable within Build Phase 3. (objectives: FR-8, FR-4, P3, NFR-4)
  - Supporting evidence: EV-050, EV-051, EV-065
  - Verification: Design review sign-off of the decision table, followed by the revised FR-8 matrix test.

### FND-013 Policy precedence across the seven dimensions is a governance decision with no owner

- **gap** · missing or unverifiable requirement · severity **medium** · confidence 0.75 (medium) · rank 16
- Disposition: **governance decision** (also: refinement now) · already acknowledged in the document

Section 28 already acknowledges that the Policy Engine's combination and precedence logic is unspecified, and frames closing it as an engineering specification pass in Build Phase 3. The review adds that precedence, for example whether Purpose Limitation overrides Recall or when to REDACT instead of DENY, is data-governance policy that the DPO role in Section 21 owns. If engineers write it as specification, it becomes de facto policy without accountable sign-off. FR-8 cannot be met or tested until this is settled.

- Where: p.29 §28 (FR-8): "the decision algorithm - how the seven dimensions combine into a"
- Where: p.30 §28: "Recommendation: treat this as the first deliverable of Build Phase 3 (Policy Engine)"
- Evidence EV-074 (doc, supports): "the decision algorithm - how the seven dimensions combine into a" [doc:DOC-sit_sample_v1#p29/s28]
- Evidence EV-075 (doc, supports): "Recommendation: treat this as the first deliverable of Build Phase 3 (Policy Engine)" [doc:DOC-sit_sample_v1#p30/s28]
- Recommendation: In Section 28 and Build Phase 3 (Section 29), make the decision table a DPO-approved artefact: engineering drafts it, the DPO signs it off, and it is added to Section 25 as a confirmed decision. Add FR-8 test cases for conflicting dimensions as well as single violations.
  - Issue: The policy precedence table is treated as an engineering deliverable with no governance owner or approval step.
  - Rationale: Precedence decides what learners' data is served or redacted, which is policy rather than implementation.
  - Expected benefit: FR-8 becomes implementable and testable, with DPO-approved semantics. (objectives: FR-8, P2, P7)
  - Supporting evidence: EV-074, EV-075
  - Verification: A signed decision table appears in Section 25, and the FR-8 test matrix includes cases where dimensions conflict.
- Next step: Data Protection Officer with Policy Engine lead: Draft and approve the seven-dimension precedence table before Build Phase 3 code generation.

### FND-049 Async write path lacks dead-letter, idempotency and post-ACK rejection feedback

- **gap** · scalability or failure mode · severity **medium** · confidence 0.70 (medium) · rank 27
- Disposition: **refinement now**

Agents get an ACK before validation, so strict-mode rejects, sensitivity-ceiling rejects and type mismatches happen after the agent believes the write succeeded. No mechanism tells the agent or learner about the failure. The claim that failed writes 'retry automatically' gives no bound: a deterministically invalid message would retry forever or block a partition. At-least-once redelivery could also duplicate rows in the append-only event table, because no idempotency key is defined.

- Where: p.17 §18 (FR-9): "overwhelm the store; failed writes queue and retry automatically"
- Where: p.3 §2.1 (FR-9): "Writes shall be enqueued to a message broker (agent receives an immediate acknowledgement) and"
- Evidence EV-150 (doc, supports): "overwhelm the store; failed writes queue and retry automatically" [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-045 (doc, supports): "Writes shall be enqueued to a message broker (agent receives an immediate acknowledgement) and" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-161 (inference, supports): "Validation runs in the consumer after the ACK, so permanent rejects cannot be fixed by retrying and need a terminal path; redelivery without a stable message ID duplicates append-only events." [inference:EV-161] derived from EV-150, EV-045
- Recommendation: In Section 18: classify errors as transient (retry with backoff and a maximum attempt count) or permanent (dead-letter topic, audit entry, MMP dashboard warning). Require a client-generated memory_id/event_id as an idempotency key with upsert-or-ignore semantics. Optionally run a synchronous Validator pre-check at the Gateway so most rejects happen before the ACK.
  - Issue: Retry, poison-message and duplicate handling are unspecified.
  - Rationale: Writes peak when 15,000 learners start term, so unbounded retries or partition blocking would stall all writes.
  - Expected benefit: FR-9 stays reliable under failure, FR-11 rejects are visible, and episodic memory is free of duplicates. (objectives: FR-9, FR-11, NFR-3)
  - Supporting evidence: EV-150, EV-045, EV-161
  - Verification: Fault-injection test: an invalid write lands in the dead-letter queue within N attempts; a duplicated Kafka message produces one row.

### FND-015 Audit retention and compaction are deferred but needed at launch

- **gap** · decision depends on pending item · severity **medium** · confidence 0.65 (medium) · rank 29
- Disposition: **governance decision** (also: refinement now) · already acknowledged in the document

The audit log retention period and PDPA sign-off (backlog item 4) and the compaction design (item 7) are pending, and Section 28 suggests deferring compaction beyond the launch scope. However, Section 20 requires compaction at every end of term, and FR-12 triggers compaction at graduation, so the first term-end after launch already depends on it. Audit records are needed for P7 and FR-13 from day one. The review adds that these items have no owner or due date, even though launch depends on them.

- Where: p.26 §26 (FR-13): "Memory Router Component 5 (Auditor) - log schema detail, retention period, PDPA alignment sign-off."
- Where: p.30 §28: "The remaining Pending Backlog items (cohort namespace, compaction, non-SIT identity) can"
- Where: p.19 §20 (FR-12): "End of term: compacted to episodic summary; raw archived"
- Evidence EV-078 (doc, supports): "Memory Router Component 5 (Auditor) - log schema detail, retention period, PDPA alignment sign-off." [doc:DOC-sit_sample_v1#p26/s26]
- Evidence EV-056 (doc, supports): "The remaining Pending Backlog items (cohort namespace, compaction, non-SIT identity) can" [doc:DOC-sit_sample_v1#p30/s28]
- Evidence EV-079 (doc, supports): "End of term: compacted to episodic summary; raw archived" [doc:DOC-sit_sample_v1#p19/s20]
- Evidence EV-090 (inference, supports): "Because term-scoped module slots require compaction at the first term end after launch, deferring the compaction design leaves the lifecycle rules unimplementable within one term of go-live." [inference:EV-090] derived from EV-056, EV-079
- Recommendation: Add an owner role and target build phase to each Section 26 item. Reclassify audit retention sign-off (DPO) and term-end compaction rules as gating items before go-live, rather than deferrable items in Section 28. At minimum, define an interim rule such as 'no compaction; retain raw until spec closed' and record it in Section 25.
  - Issue: Backlog items that launch depends on have no owner, deadline or gating phase.
  - Rationale: Lifecycle and audit retention are operational obligations from day one, not post-launch features.
  - Expected benefit: FR-13, FR-12 and the Section 20 lifecycle rules are implementable before the first term end, and PDPA retention is signed off. (objectives: FR-12, FR-13, P7, NFR-7)
  - Supporting evidence: EV-078, EV-056, EV-079, EV-090
  - Verification: Section 26 shows an owner and phase for each item, and the go-live checklist includes DPO audit-retention sign-off and a compaction or interim rule.
- Next step: Platform Team lead with Data Protection Officer: Assign owners and phases to the backlog items and confirm the audit retention period before Build Phase 4.

### FND-051 Redis context-pack cache is not tier-separated and serves stale authorisation

- **gap** · security privacy gap · severity **medium** · confidence 0.65 (medium) · rank 31
- Disposition: **refinement now**

Whole context packs are cached for the session TTL, and repeated queries skip PostgreSQL. The design does not separate the Redis cache by sensitivity tier, so the counsellor's packs (HIGHLY_RESTRICTED) share a cache and credentials with the standard tier. Cached packs also reflect the policy and redaction in force when they were built. A permission or template change, or a learner deletion, mid-session therefore does not take effect, which contradicts the stated intent that rule changes take effect immediately.

- Where: p.16 §16 (FR-8): "Policy decisions are not cached - they are evaluated fresh on every request"
- Where: p.18 §18 (FR-10): "session context pack is cached so repeated queries within a session skip PostgreSQL entirely"
- Evidence EV-077 (doc, supports): "Policy decisions are not cached - they are evaluated fresh on every request" [doc:DOC-sit_sample_v1#p16/s16]
- Evidence EV-152 (doc, supports): "session context pack is cached so repeated queries within a session skip PostgreSQL entirely" [doc:DOC-sit_sample_v1#p18/s18]
- Evidence EV-163 (inference, supports): "A fresh policy decision on top of a cached, already-redacted pack does not re-apply redaction or deletion, so the cache determines what is served until the session closes." [inference:EV-163] derived from EV-077, EV-152
- Recommendation: In Section 18: use a separate Redis instance or credentials for the sensitive tier, or do not cache HIGHLY_RESTRICTED packs. Key cache entries by agent, learner, slot set and policy/template version, and invalidate them on policy change, permission change, deletion and token revocation events.
  - Issue: The cache bypasses tier isolation and the freshness of policy decisions.
  - Rationale: NFR-5 isolation and the Section 16 intent that rule changes apply immediately both need to cover the cache.
  - Expected benefit: Counselling isolation and timely enforcement of revocations and deletions. (objectives: NFR-5, FR-8, FR-15, FR-10)
  - Supporting evidence: EV-077, EV-152, EV-163
  - Verification: Test: revoke an agent's read permission mid-session; the next read is DENIED and served from no cache.

### FND-016 No operational path for async write rejections and failed retries

- **gap** · scalability or failure mode · severity **medium** · confidence 0.60 (medium) · rank 33
- Disposition: **refinement now**

Writes are acknowledged once enqueued, but the Validator's strict-mode REJECT, the sensitivity-ceiling checks and storage retries all run later in the background consumer. The design states that failed writes 'retry automatically', but it defines no dead-letter handling, no notice to the agent or learner that a write was dropped, no consumer-lag monitoring, and no operational owner. The MMP dashboard surfaces only lenient-mode warnings, so strict-mode rejections in production, which matter most, are not visible to operators.

- Where: p.17 §18 (FR-9): "failed writes queue and retry automatically; multiple independent consumers (audit,"
- Where: p.4 §2.1 (FR-11): "The Validator shall reject (strict mode) or warn-and-log (lenient mode) any write containing a key not"
- Evidence EV-080 (doc, supports): "failed writes queue and retry automatically; multiple independent consumers (audit," [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-081 (doc, supports): "The Validator shall reject (strict mode) or warn-and-log (lenient mode) any write containing a key not" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-091 (inference, supports): "Because validation runs after the ACK, a strict-mode rejection is invisible to the agent, and without a dead-letter or monitoring path the memory is silently lost." [inference:EV-091] derived from EV-080, EV-081
- Recommendation: In Section 18, add a dead-letter topic per tier, a bounded retry policy, and audit and dashboard entries for every post-ACK rejection. Add a /dashboard/write-failures endpoint and consumer-lag alerting to Section 21, and name the operational owner. Add a test to Section 27 for an FR-11 strict-mode rejection appearing in the dead-letter topic and dashboard.
  - Issue: Post-ACK write failures have no handling, visibility or owner.
  - Rationale: Silent loss of learner memory undermines FR-9 and FR-11 and the 'no silent errors' stance in Section 15.
  - Expected benefit: Reliable FR-9 and FR-11 behaviour, with operator visibility of write failures. (objectives: FR-9, FR-11, FR-13)
  - Supporting evidence: EV-080, EV-081, EV-091
  - Verification: The FR-11 test asserts that a strict-mode rejection produces an audit entry, a dead-letter record and a dashboard item.

### FND-053 Credential separation not tied to process isolation; learner refresh tokens stored in agent memory

- **gap** · security privacy gap · severity **medium** · confidence 0.60 (medium) · rank 38
- Disposition: **refinement now** (also: needs investigation)

NFR-5 separates credentials for memory_sensitive, but one Dispatcher routes to both schemas. If a single Router process holds both credentials, the separation does not stop a compromised or buggy Router from reading counselling data, and the NFR-5 test only checks that the credentials differ. Separately, every agent's per-learner store holds access and refresh tokens for all learners, with no requirement for secret storage, encryption or rotation. The 48-hour token lifetime also needs checking against Entra ID policy.

- Where: p.27 §27.2 (NFR-5): "A credential valid for memory_standard is confirmed to fail authentication"
- Where: p.8 §6 (NFR-6): "Authentication is OAuth 2.0 via Entra ID. Tokens are valid for 48 hours."
- Where: p.13 §13: "Only the authenticated learner's entry loads into context per session."
- Evidence EV-153 (doc, supports): "A credential valid for memory_standard is confirmed to fail authentication" [doc:DOC-sit_sample_v1#p27/s27.2]
- Evidence EV-122 (doc, supports): "Authentication is OAuth 2.0 via Entra ID. Tokens are valid for 48 hours." [doc:DOC-sit_sample_v1#p8/s6]
- Evidence EV-165 (inference, supports): "Separate credentials protect the sensitive schema only if they are held by a separate workload; and a per-agent store of all learners' refresh tokens is a high-value secret store with no stated protection." [inference:EV-165] derived from EV-153, EV-122
- Recommendation: In Sections 11 and 17: run sensitive-tier Dispatcher/consumer workloads with a separate managed identity, the only holder of the memory_sensitive credential. In Section 13: store tokens in a secrets vault or keep them in session only, never in persistent agent memory. Confirm the 48-hour token validity against Entra ID token lifetime policy.
  - Issue: Credential and token custody is unspecified.
  - Rationale: FR-5 requires enforcement at the credential level, and stored tokens are reusable secrets.
  - Expected benefit: A meaningful credential-level hard wall and less exposure from token theft. (objectives: FR-5, NFR-5, NFR-6)
  - Supporting evidence: EV-153, EV-122, EV-165
  - Verification: Extend the NFR-5 test: the standard-tier workload identity cannot obtain the memory_sensitive credential. Scan agent stores for token material.
- Next step: Identity / security architect: Confirm the achievable Entra ID token lifetime and the vault approach for refresh tokens.

### FND-054 Anonymisation method for cross-learner and cohort patterns unspecified

- **gap** · security privacy gap · severity **medium** · confidence 0.55 (medium) · rank 42
- Disposition: **refinement now** (also: governance decision)

Cross-learner patterns and cohort aggregates are readable by all agents and described as 'anonymised' or 'sensitivity-stripped'. No method, minimum group size or re-identification test is defined. Cohort-level patterns from small intakes or modules can identify individuals, which undercuts P2 'private by default'. Cohort design is in the backlog, but the anonymisation standard is not listed there.

- Where: p.6 §3 (P2): "Private by default - memory is private to the learner, shared by exception, anonymised for service"
- Where: p.21 §22: "Example: ICT-2024-intake concept difficulty patterns from AI Tutor aggregate."
- Evidence EV-154 (doc, supports): "Private by default - memory is private to the learner, shared by exception, anonymised for service" [doc:DOC-sit_sample_v1#p6/s3]
- Evidence EV-155 (doc, supports): "Example: ICT-2024-intake concept difficulty patterns from AI Tutor aggregate." [doc:DOC-sit_sample_v1#p21/s22]
- Recommendation: Add a subsection to Section 22 defining aggregation rules (minimum group size k, suppression of free text, exclusion of RESTRICTED as well as HIGHLY_RESTRICTED sources) and a DPO sign-off gate. Add an acceptance test.
  - Issue: No anonymisation standard covers data shared across learners.
  - Rationale: P2 depends on aggregates being genuinely non-identifying.
  - Expected benefit: Aggregate sharing stays consistent with P2 and PDPA obligations. (objectives: P2, NFR-7)
  - Supporting evidence: EV-154, EV-155
  - Verification: Test: aggregates for groups smaller than k are suppressed, and no aggregate record contains learner_id or pii fields.
- Next step: Data governance officer / DPO: Set the minimum aggregation threshold and the approved anonymisation technique.

### FND-018 Cost objective covers only the vector store and has no owner

- **gap** · missing or unverifiable requirement · severity **low** · confidence 0.60 (medium) · rank 45
- Disposition: **governance decision** (also: refinement now)

NFR-10 bounds only vector-store infrastructure cost. The NFR-10 acceptance check, however, mixes in measured embedding volume. Event Hubs, Redis, the separate sensitive-tier embedding deployment and the MMP are not costed anywhere, and Section 21 provides cost monitoring without naming who owns the budget or what happens when it is exceeded. Total running cost, which governance needs to approve, is therefore unknown, and the acceptance criterion does not match the requirement it validates.

- Where: p.5 §2.2 (NFR-10): "Vector-store infrastructure cost shall remain within the SGD 800-1,200/month estimate at 15,000-learner"
- Where: p.28 §27.2 (NFR-10): "Projected monthly cost at 15,000-learner scale, computed from the actual"
- Evidence EV-084 (doc, supports): "Vector-store infrastructure cost shall remain within the SGD 800-1,200/month estimate at 15,000-learner" [doc:DOC-sit_sample_v1#p5/s2.2]
- Evidence EV-085 (doc, supports): "Projected monthly cost at 15,000-learner scale, computed from the actual" [doc:DOC-sit_sample_v1#p28/s27.2]
- Recommendation: Split NFR-10 into a vector-store cost bound and a total platform cost estimate covering Event Hubs, Redis, both embedding deployments and the MMP. Name a budget owner and an alert threshold on /dashboard/cost, and align the Section 27 NFR-10 criterion to each part.
  - Issue: No total cost of ownership and no budget owner.
  - Rationale: Cost tracking is in scope (Layer 6, MMP dashboard), but a dashboard without a budget and owner cannot support governance.
  - Expected benefit: NFR-10 becomes verifiable, and the platform's full run cost is approved by an accountable owner. (objectives: NFR-10)
  - Supporting evidence: EV-084, EV-085
  - Verification: A cost model reviewed by the budget owner, with the NFR-10 checks run per component.
- Next step: Platform Team lead (budget owner): Produce a total platform cost estimate and set a cost alert threshold.

### FND-044 The BM25 fallback and the 'embedded' flag are missing from the DDL that is rated 'complete'

- **gap** · unsupported or incorrect claim · severity **low** · confidence 0.60 (medium) · rank 46
- Disposition: **refinement now** (also: needs investigation)

The Embedder fallback flags records 'embedded: false' and falls back to BM25 keyword search. Yet the memory_vectors DDL has no embedded column and no full-text index. Native BM25 ranking in Azure PostgreSQL is assumed, not confirmed. Section 28 nonetheless calls the DDL complete, so code generated from it would not support the stated degraded-retrieval path.

- Where: p.16 §17: "Fall back to BM25 keyword search for retrieval"
- Where: p.29 §28: "Nothing further needed - DDL is concrete and complete (Section"
- Evidence EV-137 (doc, supports): "- Flag record as unembedded (embedded: false) - Fall back to BM25 keyword search for retrieval" [doc:DOC-sit_sample_v1#p16/s17]
- Evidence EV-145 (inference, supports): "The memory_vectors DDL in Section 11 lists no embedded column and no text-search index, so the fallback cannot be implemented from the DDL as written." [inference:EV-145] derived from EV-137
- Recommendation: In Section 11, add an embedded boolean and a full-text search column and index. Name the ranking method (built-in full-text ranking, or a confirmed extension available on Azure PostgreSQL). Change the Section 28 database schema rating accordingly.
  - Issue: The fallback retrieval path has no schema support and relies on an unconfirmed ranking capability.
  - Rationale: Retrieval degrades silently when the embedding service is unavailable.
  - Expected benefit: FR-10 reads stay functional during embedding outages. (objectives: FR-10)
  - Supporting evidence: EV-137, EV-145
  - Verification: Test with the embedding service disabled: the write is stored unembedded and a keyword read returns it.

## Ambiguities

### FND-029 FR-13 'exactly one entry per operation' conflicts with multi-event logging per request

- **ambiguity** · acceptance criterion cannot validate · severity **medium** · confidence 0.65 (medium) · rank 30
- Disposition: **refinement now**

The FR-13 criterion requires exactly one audit entry per operation. But the Auditor logs token-validation outcomes, Kafka enqueue, and the consumer's write as separate events, so a single read or write produces several entries. The criterion also does not cover completeness when the write consumer fails, which matters because writes are async. Testers will either fail correct behaviour or loosen the criterion arbitrarily.

- Where: p.27 §27.1 (FR-13): "log contains exactly one entry per operation with all required fields"
- Where: p.4 §2.1 (FR-13): "Every read, write, denial, token-validation outcome, provisioning event, compaction, deletion, and"
- Evidence EV-113 (doc, supports): "log contains exactly one entry per operation with all required fields" [doc:DOC-sit_sample_v1#p27/s27.1]
- Evidence EV-114 (doc, supports): "Every read, write, denial, token-validation outcome, provisioning event, compaction, deletion, and" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-115 (doc, supports): "- Every write (including async Kafka enqueue)" [doc:DOC-sit_sample_v1#p17/s17]
- Recommendation: In Section 17 Auditor / Section 27.1 FR-13, define the expected audit event set per operation type (e.g. read = token_validation + read; write = token_validation + enqueue + persist or DLQ). Give each set a shared request/correlation ID, and add a test that a consumer failure still yields a terminal audit event.
  - Issue: The audit-completeness oracle is ambiguous.
  - Rationale: One request produces several logged events, so 'exactly one' is undefined without a correlation model.
  - Expected benefit: FR-13 and the PDPA audit claim (P7) can be verified. (objectives: FR-13, P7)
  - Supporting evidence: EV-113, EV-114, EV-115
  - Verification: The scripted test checks the expected event set per correlation ID, including the failure case.

### FND-006 Session-TTL context-pack cache conflicts with 'policy not cached', and the cache key scope is undefined

- **ambiguity** · ambiguous requirement · severity **medium** · confidence 0.60 (medium) · rank 32
- Disposition: **refinement now**

Section 16 says policy decisions are evaluated fresh so that rule changes take effect immediately. The read path, however, caches an already ranked, budgeted and redacted context pack for the whole session and serves it on a HIT. A redaction or recall rule change therefore does not apply until the session ends. The design also does not say whether the cache key includes agent_id. If it does not, one agent's pack, redacted for that agent's clearance, could be served to another agent in the same learner session.

- Where: p.16 §16 (FR-8): "evaluated fresh on every request, so that a rule change takes effect immediately rather than waiting for a cache"
- Where: p.18 §18 (FR-10): "Rank (relevance + recency) -> Budget (token limit) -> Redact (sensitivity)"
- Where: p.4 §2.1 (FR-10): "Reads shall check an L1 cache first; on a cache miss, the platform shall query PostgreSQL, then rank,"
- Evidence EV-054 (doc, supports): "evaluated fresh on every request, so that a rule change takes effect immediately rather than waiting for a cache" [doc:DOC-sit_sample_v1#p16/s16]
- Evidence EV-055 (doc, supports): "context pack is cached so repeated queries within a session skip PostgreSQL entirely" [doc:DOC-sit_sample_v1#p18/s18]
- Evidence EV-067 (inference, supports): "A redacted pack cached for the session embeds the policy outcome at caching time, so policy freshness and session-TTL caching cannot both hold." [inference:EV-067] derived from EV-054, EV-055
- Recommendation: In Section 18, define the cache key as (learner_id, agent_id, session_id, policy_version). Invalidate on policy or template publication, or cache unredacted-but-permitted records and apply redaction on every serve. Add a cache-isolation case to the FR-10 test.
  - Issue: Cache semantics are not reconciled with fresh policy evaluation or with per-agent clearance.
  - Rationale: Domain isolation (FR-5, P4) and immediate rule changes are stated objectives.
  - Expected benefit: A cached read cannot bypass a policy change or another agent's clearance. (objectives: FR-10, FR-8, FR-5)
  - Supporting evidence: EV-054, EV-055, EV-067
  - Verification: FR-10 test: two agents in the same learner session receive differently redacted packs; a policy change mid-session takes effect on the next read.

## Unresolved assumptions

### FND-037 The 600-vectors-per-learner estimate does not add up and leaves out growth over time

- **unresolved assumption** · unsupported or incorrect claim · severity **medium** · confidence 0.75 (medium) · rank 19
- Disposition: **refinement now** (also: needs investigation)

The items in the per-learner breakdown add up to about 340 vectors, not ~600. To reach 600, 'other 20+' would have to be about 260. The breakdown also counts only 6 active modules, although module slots are term-scoped and stack across a whole degree. No basis is given for the 500,000 alumni vectors or for how alumni accumulate each year. The 9.5M total drives the SKU, the RAM fit of the ~80 GB index, the growth ceiling and NFR-10, so the confirmed figures rest on an unsupported estimate.

- Where: p.12 §12 (NFR-1): "Per-learner breakdown (~600 vectors across a full degree): core/identity 10, advisory 15, modules (6 active × 20)"
- Where: p.12 §12: "120, assessment/interview 60, career 30, cocurricular 30, orientation 20, buddy 30, counselling (avg) 5, other"
- Evidence EV-131 (doc, supports): "Per-learner breakdown (~600 vectors across a full degree): core/identity 10, advisory 15, modules (6 active × 20) 120, assessment/interview 60, career 30, cocurricular 30, orientation 20, buddy 30, counselling (avg) 5, other 20+." [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-140 (inference, supports): "10+15+120+60+30+30+20+30+5+20 = 340, so about 43% of the stated 600 per learner is unexplained, and only 6 of the modules taken over a degree are counted." [inference:EV-140] derived from EV-131
- Recommendation: Rework the Section 12 table so the per-learner items add up to the stated total. Model module vectors across a full degree after term-end compaction, and add an alumni growth model (graduates per year × retained vectors × retention years). Restate the total and the growth-ceiling year, and include table and other-index storage alongside the HNSW index in the RAM budget.
  - Issue: The vector-count estimate behind the SKU and cost decisions is internally inconsistent and does not model growth.
  - Rationale: Under- or over-estimating vector counts directly changes whether the index fits in 128 GB RAM and whether the NFR-10 cost holds.
  - Expected benefit: A defensible sizing basis for NFR-1, NFR-2 and NFR-10. (objectives: NFR-1, NFR-10)
  - Supporting evidence: EV-131, EV-140
  - Verification: Peer review of the revised sizing model, and a check against vector counts from pilot agents.

### FND-039 The Kafka/Event Hubs write path is 'confirmed' while still pending, and its broker claims are unverified

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.70 (medium) · rank 25
- Disposition: **needs investigation** (also: refinement now) · already acknowledged in the document

The write path is listed as a confirmed decision ('Async via Kafka (Azure Event Hubs)'), yet the Pending Backlog still asks to confirm Event Hubs. Section 18 also credits the broker with properties it does not provide by itself. Automatic retry of failed writes needs consumer-side retry and dead-letter handling, which is not designed. Separate topics on a shared broker are a logical separation, not the physical isolation in transit the design claims. FR-9 and NFR-5-style isolation for HIGHLY_RESTRICTED data therefore depend on unverified capabilities.

- Where: p.26 §26: "Kafka vs Azure Event Hubs - confirm Azure Event Hubs as the managed Kafka-API alternative."
- Where: p.17 §18 (FR-9): "overwhelm the store; failed writes queue and retry automatically; multiple independent consumers (audit,"
- Where: p.17 §18 (NFR-5): "read the same event stream; separate topics per sensitivity tier keep HIGHLY_RESTRICTED"
- Evidence EV-133 (doc, supports): "Write path Async via Kafka (Azure Event Hubs)" [doc:DOC-sit_sample_v1#p25/s25]
- Evidence EV-082 (doc, supports): "Kafka vs Azure Event Hubs - confirm Azure Event Hubs as the managed Kafka-API alternative." [doc:DOC-sit_sample_v1#p26/s26]
- Evidence EV-142 (inference, supports): "A decision marked confirmed rests on a backlog item still open, and the retry and physical-isolation properties attributed to the broker are not backed by any designed retry, dead-letter or separate-namespace mechanism." [inference:EV-142] derived from EV-133, EV-082
- Recommendation: Close backlog item 9 before Phase 4. Then, in Section 18, specify the consumer retry policy, a dead-letter topic and monitoring, and idempotent processing. State whether the sensitive topic uses a separate namespace or cluster with its own credentials. Mark the Section 25 write-path decision as conditional until the backlog item is closed.
  - Issue: The broker choice and the guarantees attributed to it are assumed, not verified.
  - Rationale: Write durability (FR-9) and the in-transit isolation of HIGHLY_RESTRICTED writes depend on broker features and configuration that the design does not specify.
  - Expected benefit: FR-9 durability and sensitive-tier isolation rest on specified mechanisms. (objectives: FR-9, NFR-5, FR-5)
  - Supporting evidence: EV-133, EV-082, EV-142
  - Verification: Fault-injection test: a consumer failure mid-write leads to a retried write, or a dead-letter entry with an audit record and no data loss.
- Next step: Platform engineering lead: Confirm Event Hubs (Kafka API) feature fit and the isolation option for the sensitive tier, and record the decision.

### FND-042 PDPA compliance is asserted throughout, but PDPA sign-off and retention basis are still pending

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.60 (medium) · rank 35
- Disposition: **governance decision** (also: needs investigation) · already acknowledged in the document

Several sections present audit and retention as meeting PDPA ('Retained per PDPA requirements'), yet the Auditor's retention period and PDPA alignment sign-off are still in the Pending Backlog. Agent backups also survive a learner's own deletion, and nobody has assessed whether that is consistent with FR-15 deletion or with PDPA retention obligations. This review adds that compliance is assumed in decisions, not verified. The legal position on audit retention and on backups surviving deletion was not checked here.

- Where: p.26 §26 (FR-13): "Memory Router Component 5 (Auditor) - log schema detail, retention period, PDPA alignment sign-off."
- Where: p.17 §17 (FR-13, NFR-7): "Audit logs are append-only. Never modified. Retained per PDPA requirements."
- Where: p.13 §13 (FR-15, FR-16): "survives learner deletion of their own memory (enabling session resume); rules are written by the system"
- Evidence EV-078 (doc, supports): "Memory Router Component 5 (Auditor) - log schema detail, retention period, PDPA alignment sign-off." [doc:DOC-sit_sample_v1#p26/s26]
- Evidence EV-073 (doc, supports): "the agent backup survives learner deletion of their own memory (enabling session resume)" [doc:DOC-sit_sample_v1#p13/s13]
- Evidence EV-144 (inference, supports): "PDPA conformance is stated as fact while its sign-off is open, and backup retention after learner deletion has no recorded legal basis." [inference:EV-144] derived from EV-078, EV-073
- Recommendation: Make the DPO sign-off of the audit retention period and of the backup-survives-deletion rule a gate before Build Phase 4. Record the outcome in Sections 17, 20 and 25, and add a backup-deletion case to the FR-15 test.
  - Issue: Compliance claims rest on a pending sign-off and on an unassessed deletion exception.
  - Rationale: The six agents could launch with retention and deletion behaviour that is later found non-compliant.
  - Expected benefit: NFR-7 and FR-15 rest on a DPO-approved retention and deletion basis. (objectives: NFR-7, FR-13, FR-15)
  - Supporting evidence: EV-078, EV-073, EV-144
  - Verification: Signed DPO decision record referenced from Section 25, plus an updated FR-15 test.
- Next step: Data Protection Officer: Decide the audit-log retention period and whether agent backups must be purged when a learner deletes their memory.

### FND-043 FR-12 assumes the SIS can emit lifecycle webhooks, which is not verified

- **unresolved assumption** · decision depends on pending item · severity **medium** · confidence 0.60 (medium) · rank 36
- Disposition: **needs investigation** · already acknowledged in the document

FR-12 requires fully automatic provisioning from SIS events, including module withdrawal and graduation. The design assumes the SIS can emit these as webhooks, but gives no event contract and no confirmation from the SIS owner, and handling of SIS integration failures is still pending. If the SIS cannot push these events, FR-12 and the Check 4 auto-provisioning path cannot work without manual intervention.

- Where: p.4 §2.1 (FR-12): "SIS events - registration, programme enrolment, module registration, module withdrawal, graduation -"
- Where: p.26 §26: "MMP in detail - template versioning conflict resolution, SIS integration failure handling."
- Evidence EV-135 (doc, supports): "SIS webhook (automated): - Learner registration -> create_namespace() + provision core/ + orientation/" [doc:DOC-sit_sample_v1#p21/s21]
- Evidence EV-136 (doc, supports): "MMP in detail - template versioning conflict resolution, SIS integration failure handling." [doc:DOC-sit_sample_v1#p26/s26]
- Recommendation: Confirm with the SIS owner which events can be emitted (webhook, batch or CDC), and add an event contract (payload, delivery guarantees, replay) plus a reconciliation job to Section 21.
  - Issue: The SIS event capability and contract are assumed.
  - Rationale: Namespace provisioning and expiry, and therefore FR-1, FR-12 and term-scoped lifecycle rules, depend on these events.
  - Expected benefit: FR-12 becomes achievable, or a polling or batch fallback is designed early. (objectives: FR-12, FR-1)
  - Supporting evidence: EV-135, EV-136
  - Verification: The FR-12 simulation test run against real SIS payload samples, plus a reconciliation test for missed events.
- Next step: SIS integration owner: Confirm SIS event emission capability and agree an event contract.

### FND-017 Confirmed write and read path decisions rest on pending platform choices

- **unresolved assumption** · decision depends on pending item · severity **low** · confidence 0.70 (medium) · rank 44
- Disposition: **needs investigation** (also: refinement now) · already acknowledged in the document

Section 25 lists 'Async via Kafka (Azure Event Hubs)' and 'Redis L1' as confirmed decisions. Section 26 still lists confirming Event Hubs as the Kafka alternative, and choosing Azure Cache for Redis versus local Redis, as pending. The design depends on Kafka-specific behaviour (per-tier topics, several independent consumers, retry), which the chosen managed service must actually provide. The confirmed status therefore overstates closure.

- Where: p.26 §26: "Kafka vs Azure Event Hubs - confirm Azure Event Hubs as the managed Kafka-API alternative."
- Where: p.26 §26: "Redis - confirm Azure Cache for Redis versus local Redis for development environments."
- Evidence EV-082 (doc, supports): "Kafka vs Azure Event Hubs - confirm Azure Event Hubs as the managed Kafka-API alternative." [doc:DOC-sit_sample_v1#p26/s26]
- Evidence EV-083 (doc, supports): "Read path Redis L1 → PostgreSQL (pgvector + event + doc tables)" [doc:DOC-sit_sample_v1#p25/s25]
- Recommendation: Mark the write-path and read-path rows in Section 25 as 'confirmed pattern; platform pending' with a link to the backlog items. Check that the Event Hubs tier chosen supports the per-tier topics, consumer groups and retry semantics assumed in Section 18 before Build Phase 4.
  - Issue: Decisions marked confirmed depend on open platform choices.
  - Rationale: Decision status should reflect the actual state so that downstream build phases do not treat open items as fixed.
  - Expected benefit: An accurate decision register, and the FR-9 and NFR-3 behaviour confirmed on the chosen broker. (objectives: FR-9, NFR-3)
  - Supporting evidence: EV-082, EV-083
  - Verification: A spike confirms that the broker features used in Section 18 work on the selected Event Hubs tier, and Section 25 is updated.
- Next step: Platform Architect: Close the Event Hubs and Redis platform choices with a short feature-compatibility check before Build Phase 4.

## Validation needs

### FND-026 NFR-2 5-15 ms filtered-HNSW latency rests on unbenchmarked sizing and search-space assumptions

- **validation need** · unsupported or incorrect claim · severity **high** · confidence 0.65 (medium) · rank 11
- Disposition: **needs prototyping** (also: refinement now)

Section 12 claims the per-query search space is 500-800 vectors because queries are filtered. But the HNSW index is built over the whole embedding column, with only a separate B-tree on (learner_id, slot_path). Whether the planner pre-filters or post-filters, and whether filtered HNSW returns enough rows, has to be measured; it cannot be assumed. The memory figures (about 57 GB raw plus about 80 GB index) add up to more than the 128 GB of RAM on the chosen SKU, which weakens the 'in-RAM index' premise. NFR-2's 'normal load' is undefined, and the acceptance criterion measures latency only, with no concurrency level and no recall check.

- Where: p.12 §12 (NFR-2): "HNSW parameters: m=16, ef_construction=64. Queries are always filtered by learner_id + slot_path - the"
- Where: p.12 §12 (NFR-1): "Azure SKU required Memory Optimised, 16 vCores, 128 GB RAM"
- Where: p.27 §27.2 (NFR-2): "p95 filtered similarity query latency ≤ 15 ms, p50 ≤ 10 ms, measured against"
- Evidence EV-105 (doc, supports): "HNSW parameters: m=16, ef_construction=64. Queries are always filtered by learner_id + slot_path - the" [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-106 (doc, supports): "HNSW index overhead (~1.4×) ~80 GB" [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-107 (doc, supports): "Azure SKU required Memory Optimised, 16 vCores, 128 GB RAM" [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-108 (doc, supports): "Filtered vector similarity queries (scoped by learner_id and slot_path) shall return within 5-15 ms under" [doc:DOC-sit_sample_v1#p4/s2.2]
- Evidence EV-124 (inference, supports): "57 GB of raw vectors plus an ~80 GB HNSW index is about 137 GB, more than the 128 GB of RAM, before OS, shared buffers, the event/document tables and the duplicated memory_sensitive schema; the in-RAM latency premise is therefore unproven." [inference:EV-124] derived from EV-106, EV-107
- Evidence EV-125 (inference, supports): "A global HNSW index plus a separate B-tree on learner_id/slot_path does not by itself confine the ANN search to 500-800 vectors; filtered recall and latency must be measured." [inference:EV-125] derived from EV-105
- Recommendation: Build a prototype in an early phase: load 9.5M synthetic 1536-dim vectors with the realistic per-learner distribution on the chosen SKU and measure p50/p95 latency and recall@k against exact search, for filtered queries at a defined concurrent QPS. Define 'normal load' in NFR-2 (e.g. peak concurrent sessions × reads/turn). Add a recall threshold and the load level to the Section 27.2 NFR-2 criterion. Correct the Section 12 memory arithmetic and say whether the index is meant to be fully RAM-resident.
  - Issue: The NFR-2 latency and the Section 12 search-space/RAM claims are unverified, and the acceptance criterion lacks a load level and a recall check.
  - Rationale: The SKU, HNSW parameters and cost estimate all depend on these claims. If they are wrong, retrieval quality or latency will fail at 15,000 learners.
  - Expected benefit: NFR-1, NFR-2 and NFR-10 are confirmed before the SKU and index design are fixed. (objectives: NFR-1, NFR-2, NFR-10)
  - Supporting evidence: EV-105, EV-106, EV-107, EV-108, EV-124, EV-125
  - Verification: Benchmark report showing latency and recall at the defined load on the provisioned SKU, attached to Section 12.
- Next step: Platform architect / database engineer: Run a filtered pgvector benchmark at full synthetic scale before confirming the SKU and HNSW parameters.

### FND-035 Filtered HNSW search-space claim underpins NFR-2 and SKU sizing but is unverified

- **validation need** · unsupported or incorrect claim · severity **high** · confidence 0.65 (medium) · rank 12
- Disposition: **needs prototyping** (also: refinement now)

Section 12 says filtering by learner_id + slot_path shrinks the effective search space to 500-800 vectors. The DDL, however, defines one global HNSW index over all ~9.5M vectors plus a separate B-tree on (learner_id, slot_path). With an approximate graph index, the WHERE filter may be applied only to the candidates the graph returns. A per-learner subset is about 0.006% of the table, so such a query could return few or no rows. If the planner uses the B-tree instead and scans the rows exactly, the ~80 GB in-RAM HNSW index that drives the 128 GB SKU choice may not be needed for learner-scoped queries at all. Either way, the latency in NFR-2 and the result completeness that NFR-2 assumes are not shown to hold.

- Where: p.12 §12 (NFR-2): "effective search space per query is 500-800 vectors, not 9.5 million."
- Where: p.11 §11: "CREATE INDEX ON memory_vectors USING hnsw (embedding vector_cosine_ops)"
- Where: p.4 §2.2 (NFR-2): "Filtered vector similarity queries (scoped by learner_id and slot_path) shall return within 5-15 ms under"
- Evidence EV-128 (doc, supports): "HNSW parameters: m=16, ef_construction=64. Queries are always filtered by learner_id + slot_path - the effective search space per query is 500-800 vectors, not 9.5 million." [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-129 (doc, supports): "CREATE INDEX ON memory_vectors USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64); CREATE INDEX ON memory_vectors (learner_id, slot_path);" [doc:DOC-sit_sample_v1#p11/s11]
- Evidence EV-138 (inference, supports): "About 600 of 9.5M rows (~0.006%) match a learner filter, so a single global ANN index gives no guarantee of either the claimed reduced search space or complete top-k results; whichever index the planner uses changes both latency and whether the 80 GB in-RAM index is needed." [inference:EV-138] derived from EV-128, EV-129
- Recommendation: Build a prototype on synthetic data (~9.5M vectors, ~600 per learner) and compare three options: (a) HNSW with the filter, (b) an exact scan through the B-tree, (c) partitioning by learner or slot. Record EXPLAIN plans, recall@k against brute force, and p50/p95 latency. Then rewrite the Section 12 claim and the NFR-2 test in Section 27.2 to state the chosen query strategy and add a recall criterion.
  - Issue: The latency and recall claim for learner-scoped vector search rests on an unverified assumption about how a global HNSW index behaves under a highly selective filter.
  - Rationale: NFR-2, the SKU decision and the cost estimate (NFR-10) all depend on this assumption.
  - Expected benefit: NFR-2 latency and result completeness are shown before the SKU is committed, and the platform avoids over- or under-provisioning RAM. (objectives: NFR-2, NFR-1, NFR-10)
  - Supporting evidence: EV-128, EV-129, EV-138
  - Verification: Prototype report showing recall@k ≥ the agreed threshold and p95 ≤ 15 ms for learner-scoped queries, with the query plan used.
- Next step: Platform data architect: Run a pgvector filtered-query prototype on synthetic data at full scale before committing the 16 vCore / 128 GB SKU.

### FND-027 Async write path makes FR-11 rejection and FR-9 latency budget unobservable as specified

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.75 (medium) · rank 17
- Disposition: **refinement now**

The agent gets an immediate ACK at Kafka enqueue, and template validation runs later in the background consumer. So the FR-11 criterion's 'write... is rejected' cannot be seen by the caller, and the design defines no rejection or dead-letter signal back to the agent. FR-9's acceptance criterion refers to a 'Kafka enqueue time budget' that is never quantified, and NFR-3's tolerance is only an example ('e.g. ±10%'). As written, neither criterion has a fixed pass/fail threshold or a defined observable outcome.

- Where: p.17 §18 (FR-9): "<- Agent receives immediate ACK -- non-blocking |"
- Where: p.27 §27.1 (FR-11): "With MEMORY_STRICT_MODE=true, a write with an undeclared key is"
- Where: p.27 §27.1 (FR-9): "Under load, the p99 agent-visible latency for a write call is within the Kafka"
- Evidence EV-109 (doc, supports): "<- Agent receives immediate ACK -- non-blocking" [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-110 (doc, supports): "+-- Validate against slot template (Validator)" [doc:DOC-sit_sample_v1#p17/s18]
- Evidence EV-111 (doc, supports): "Under load, the p99 agent-visible latency for a write call is within the Kafka" [doc:DOC-sit_sample_v1#p27/s27.1]
- Evidence EV-126 (inference, supports): "Validation happens after the ACK, so a strict-mode rejection is only visible in storage or audit state, not to the writing agent; the criterion must name where rejection is observed." [inference:EV-126] derived from EV-109, EV-110
- Recommendation: In Section 18, define the outcome of a rejected async write (e.g. a dead-letter topic plus an audit entry with outcome=DENIED and reason=UNKNOWN_KEY, optionally a callback or status endpoint). Alternatively, move the template-key check into the synchronous Gateway step. Rewrite the FR-11 criterion to assert that the record is not stored and that the DLQ/audit entry exists. Set a numeric p99 enqueue budget (ms) in FR-9/NFR-3 and fix the NFR-3 tolerance.
  - Issue: FR-11 rejection has no observable outcome, and the FR-9/NFR-3 thresholds are unquantified.
  - Rationale: A test needs a defined observable and a numeric threshold to pass or fail.
  - Expected benefit: FR-9, FR-11 and NFR-3 become testable, and agents and admins can see when writes are silently dropped. (objectives: FR-9, FR-11, NFR-3)
  - Supporting evidence: EV-109, EV-110, EV-111, EV-126
  - Verification: Updated criteria contain numeric thresholds and a named rejection observable, and the test harness asserts both.

### FND-028 FR-8 policy-dimension test presumes DENY outcomes the unspecified algorithm does not define

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.75 (medium) · rank 18
- Disposition: **refinement now** · already acknowledged in the document

The FR-8 criterion expects each of the seven dimensions to produce 'a DENY attributable to that dimension'. Redaction yields REDACT, and Retention and Deletion govern lifecycle rather than per-request denial. Section 28 also admits that the combination and precedence algorithm is unspecified. The review adds that this test cannot be written or passed until the decision table exists, and that the criterion itself needs rewriting to match the outcome types per dimension.

- Where: p.27 §27.1 (FR-8): "condition per dimension) and confirms each produces a DENY attributable to"
- Where: p.29 §28 (FR-8): "the decision algorithm - how the seven dimensions combine into a"
- Evidence EV-112 (doc, supports): "condition per dimension) and confirms each produces a DENY attributable to" [doc:DOC-sit_sample_v1#p27/s27.1]
- Evidence EV-051 (doc, supports): "Redaction Should part of the memory be masked before serving to this agent?" [doc:DOC-sit_sample_v1#p15/s16]
- Evidence EV-074 (doc, supports): "the decision algorithm - how the seven dimensions combine into a" [doc:DOC-sit_sample_v1#p29/s28]
- Recommendation: When writing the Section 28 decision table, add the expected outcome per dimension (DENY, REDACT, EXPIRE/PURGE, ALLOW) and at least one test per pairwise precedence conflict. Update the Section 27.1 FR-8 criterion to assert those outcomes and reason codes.
  - Issue: The FR-8 criterion assumes DENY for every dimension and depends on an undefined algorithm.
  - Rationale: Redaction and retention produce different outcomes, and precedence is undefined, so testers would have to make up the expected results.
  - Expected benefit: FR-8 becomes testable, and Build Phase 3 has a defined oracle to test against. (objectives: FR-8)
  - Supporting evidence: EV-112, EV-051, EV-074
  - Verification: FR-8 test cases trace one-to-one to rows in the published decision table.

### FND-030 FR-16 degraded-mode test does not verify 'backup never overrides namespace' nor define reconciliation

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.70 (medium) · rank 23
- Disposition: **refinement now** · already acknowledged in the document

FR-16's key clause is that the backup must never override the authoritative namespace when both are available (P1). The test checks only that serving continues during an outage and that nothing conflicting is written back afterwards. It never asserts that, after restoration, a namespace value wins over a different backup value in the context pack. 'Conflicting data' is also undefined while conflict resolution sits in the Pending Backlog, so the pass condition cannot be judged.

- Where: p.27 §27.1 (FR-16): "continues serving from its own backup memory and does not attempt to"
- Where: p.4 §2.1 (FR-16): "unreachable (degraded mode). The backup shall never override the authoritative learner namespace when"
- Evidence EV-116 (doc, supports): "continues serving from its own backup memory and does not attempt to" [doc:DOC-sit_sample_v1#p27/s27.1]
- Evidence EV-117 (doc, supports): "unreachable (degraded mode). The backup shall never override the authoritative learner namespace when" [doc:DOC-sit_sample_v1#p4/s2.1]
- Evidence EV-118 (doc, supports): "Memory Router Component 4 (Dispatcher) - full internal design including conflict-resolution edge cases." [doc:DOC-sit_sample_v1#p26/s26]
- Recommendation: Add to the Section 27.1 FR-16 criterion: seed key K with value A in the namespace and value B in the agent backup; with both available, the context pack contains A, and the audit source field = namespace. Define 'conflicting write-back' in the Dispatcher spec as the Pending Backlog item 3 is closed.
  - Issue: The FR-16 criterion omits the precedence assertion and relies on an undefined notion of conflict.
  - Rationale: P1 is a foundational principle, and its test needs a positive precedence check.
  - Expected benefit: FR-16 and P1 can be verified. (objectives: FR-16, P1)
  - Supporting evidence: EV-116, EV-117, EV-118
  - Verification: The test asserts context-pack content and the audit source for the seeded conflict.

### FND-032 Section 28 'Ready' ratings overstate completeness of DDL and Embedder fallback

- **validation need** · internal contradiction · severity **medium** · confidence 0.70 (medium) · rank 24
- Disposition: **refinement now**

Section 28 rates the DDL 'concrete and complete' and the Embedder 'directly codeable'. But the memory_vectors DDL has no embedded flag for the 'embedded: false' fallback, and nothing in the DDL supports the BM25 keyword fallback. The append-only audit store, agent registry, agent backup and namespace-registry tables are also undefined. No acceptance criterion exercises the embedding-unavailable fallback. The readiness self-assessment is the document's main verifiability claim, so these gaps would surface during code generation.

- Where: p.29 §28: "Nothing further needed - DDL is concrete and complete (Section"
- Where: p.16 §17: "- Fall back to BM25 keyword search for retrieval"
- Evidence EV-096 (doc, supports): "Nothing further needed - DDL is concrete and complete (Section" [doc:DOC-sit_sample_v1#p29/s28]
- Evidence EV-098 (doc, supports): "- Fall back to BM25 keyword search for retrieval" [doc:DOC-sit_sample_v1#p16/s17]
- Evidence EV-127 (inference, supports): "The Section 11 DDL defines only memory_vectors, memory_events and memory_documents, with no embedded column, no full-text index, and no audit, registry or backup tables, so the fallback and the audit store cannot be generated from it." [inference:EV-127] derived from EV-096, EV-098
- Recommendation: Add the following to the Section 11 DDL: an embedded BOOLEAN column, a tsvector/full-text index for the keyword fallback, and tables for the audit store, agent_registry and agent backup (or state where these live). Add an acceptance test for the embedding-outage fallback (record stored with embedded=false, keyword retrieval works, backlog entry created). Downgrade the Section 28 ratings until this is done.
  - Issue: The readiness ratings do not match the specified DDL.
  - Rationale: Code generation from the spec would have to invent schema for the fallback and the audit store.
  - Expected benefit: An accurate Section 28, and FR-13 and the embedder fallback become verifiable. (objectives: FR-13, FR-10)
  - Supporting evidence: EV-096, EV-098, EV-127
  - Verification: Generated migrations include the tables and columns, and the fallback test passes.

### FND-031 FR-15 deletion test checks primary records only, not cache, embeddings or agent backup copies

- **validation need** · acceptance criterion cannot validate · severity **medium** · confidence 0.60 (medium) · rank 34
- Disposition: **refinement now** (also: governance decision)

The FR-15 criterion checks that user-deletable records are removed and institutional records remain. It does not check derived copies: Redis context packs, unprocessed Kafka messages, re-embed backlog entries, or the agent per-learner backup, which the design says survives learner self-deletion. A pass would show deletion only from the primary tables, and the learner-facing deletion claim would remain unverified.

- Where: p.27 §27.1 (FR-15): "A learner-initiated deletion request removes user-deletable records and"
- Where: p.13 §13: "survives learner deletion of their own memory (enabling session resume); rules are written by the system"
- Evidence EV-119 (doc, supports): "A learner-initiated deletion request removes user-deletable records and" [doc:DOC-sit_sample_v1#p27/s27.1]
- Evidence EV-120 (doc, supports): "survives learner deletion of their own memory (enabling session resume); rules are written by the system" [doc:DOC-sit_sample_v1#p13/s13]
- Recommendation: Extend the Section 27.1 FR-15 criterion to assert that the deleted keys are absent from the Redis cache, are not re-materialised by in-flight Kafka messages, and are absent from the re-embed backlog. For the agent backup, either assert removal or have the DPO explicitly record the retention exception in Section 20.
  - Issue: The deletion test's scope leaves out derived and backup copies.
  - Rationale: Verifying deletion means checking every place the data is held.
  - Expected benefit: FR-15 and NFR-7 claims can be shown to hold, or the retained copies are explicitly accepted. (objectives: FR-15, NFR-7)
  - Supporting evidence: EV-119, EV-120
  - Verification: Deletion test inspects every store and logs the result per store.
- Next step: DPO: Decide whether agent-backup retention after learner deletion is acceptable, and record the decision.

### FND-008 Filtered HNSW latency and recall premise for NFR-2 is unverified

- **validation need** · unsupported or incorrect claim · severity **medium** · confidence 0.55 (medium) · rank 39
- Disposition: **needs prototyping** (also: needs testing)

NFR-2 and Section 12 rely on the premise that filtering by learner_id and slot_path shrinks the effective search space to 500-800 vectors. The design pairs one global HNSW index with a separate B-tree index. Whether a query uses the B-tree with an exact scan or the HNSW index with filtering decides both latency and recall, and the NFR-2 acceptance criterion measures latency only. The premise needs a benchmark before Section 12's SKU and growth-ceiling figures can be relied on.

- Where: p.12 §12 (NFR-2): "effective search space per query is 500-800 vectors, not 9.5 million."
- Where: p.4 §2.2 (NFR-2): "Filtered vector similarity queries (scoped by learner_id and slot_path) shall return within 5-15 ms under"
- Evidence EV-058 (doc, supports): "effective search space per query is 500-800 vectors, not 9.5 million." [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-059 (doc, supports): "p95 filtered similarity query latency ≤ 15 ms, p50 ≤ 10 ms, measured against" [doc:DOC-sit_sample_v1#p27/s27.2]
- Evidence EV-069 (inference, supports): "A global ANN index does not by itself restrict traversal to the filtered subset, so the 500-800 figure holds only if the query plan uses the B-tree path; the actual plan, latency and recall need measuring." [inference:EV-069] derived from EV-058, EV-059
- Recommendation: Add a Phase 5 prototype benchmark that captures query plans, p50/p95 latency and recall@k against an exact-scan baseline on the 9.5M synthetic dataset. Add a recall threshold to the NFR-2 acceptance criterion in Section 27.2.
  - Issue: The latency premise and retrieval quality under filtering are unproven.
  - Rationale: NFR-1, NFR-2 and NFR-10 sizing all rest on this premise.
  - Expected benefit: NFR-2 is confirmed, or the index strategy is corrected, before SKU commitment. (objectives: NFR-2, NFR-1, NFR-10)
  - Supporting evidence: EV-058, EV-059, EV-069
  - Verification: Benchmark report meeting both the latency and recall thresholds.
- Next step: Platform engineering lead: Build the pgvector benchmark on the target SKU and record plans, latency and recall.

### FND-038 The SGD 800-1,200/month cost (NFR-10) is unsourced and its scope is unclear

- **validation need** · unsupported or incorrect claim · severity **medium** · confidence 0.55 (medium) · rank 40
- Disposition: **needs investigation** (also: refinement now)

NFR-10 makes a requirement out of an estimate for a 16 vCore / 128 GB Memory Optimised server in Singapore, but gives no pricing basis. Nothing says whether it covers high availability, storage, backups, or the second (memory_sensitive) tier. The NFR-10 acceptance criterion also adds measured embedding volume, which is not 'vector-store infrastructure', so the requirement and its test cover different scopes. Current Azure pricing for this SKU could not be checked in this review.

- Where: p.5 §2.2 (NFR-10): "Vector-store infrastructure cost shall remain within the SGD 800-1,200/month estimate at 15,000-learner"
- Where: p.28 §27.2 (NFR-10): "Projected monthly cost at 15,000-learner scale, computed from the actual"
- Evidence EV-132 (doc, supports): "Cost estimate (Azure, Singapore region) SGD 800-1,200/month" [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-084 (doc, supports): "Vector-store infrastructure cost shall remain within the SGD 800-1,200/month estimate at 15,000-learner" [doc:DOC-sit_sample_v1#p5/s2.2]
- Evidence EV-141 (inference, supports): "The requirement covers vector-store infrastructure while the test adds embedding volume, and neither states whether HA, storage, backup or the sensitive tier are included, so the cost ceiling cannot be checked consistently." [inference:EV-141] derived from EV-132, EV-084
- Recommendation: In Section 12, add a dated cost breakdown from the Azure pricing calculator for the Singapore region, itemising compute, storage, backup, HA, and both schemas or servers. Separately list Event Hubs, Redis and embedding costs. Align the NFR-10 text and its Section 27.2 criterion to the same scope.
  - Issue: The cost ceiling has no stated pricing source or scope.
  - Rationale: A wrong ceiling either fails NFR-10 at go-live or forces a SKU downgrade that would put NFR-2 at risk.
  - Expected benefit: NFR-10 can be tested and relied on for budgeting. (objectives: NFR-10)
  - Supporting evidence: EV-132, EV-084, EV-141
  - Verification: Dated pricing-calculator export attached to the design, then reconciled with the first month's actual bill.
- Next step: Cloud FinOps / platform lead: Produce an itemised, dated Azure Singapore price quote for the confirmed SKU and supporting services.

### FND-052 Filtered HNSW latency/recall and memory fit at 9.5M vectors unproven

- **validation need** · scalability or failure mode · severity **medium** · confidence 0.55 (medium) · rank 41
- Disposition: **needs prototyping** (also: needs testing)

The design assumes the learner_id + slot_path filter shrinks the search space to 500-800 vectors. With a single global HNSW index, whether the filter narrows the graph search or is applied after it depends on the query plan; post-filtering can return too few results. The sizing also puts about 57 GB of raw vectors plus about 80 GB of index against 128 GB RAM, so the 'in-RAM index' basis of NFR-2 is doubtful. This needs a benchmark, not an assertion.

- Where: p.12 §12 (NFR-2): "effective search space per query is 500-800 vectors, not 9.5 million."
- Where: p.4 §2.2 (NFR-2): "Filtered vector similarity queries (scoped by learner_id and slot_path) shall return within 5-15 ms under"
- Evidence EV-058 (doc, supports): "effective search space per query is 500-800 vectors, not 9.5 million." [doc:DOC-sit_sample_v1#p12/s12]
- Evidence EV-108 (doc, supports): "Filtered vector similarity queries (scoped by learner_id and slot_path) shall return within 5-15 ms under" [doc:DOC-sit_sample_v1#p4/s2.2]
- Evidence EV-164 (inference, supports): "The Section 12 figures (~57 GB raw plus ~80 GB HNSW index, about 137 GB) exceed the 128 GB RAM of the chosen SKU before OS and other overheads, so a fully in-RAM index is not assured." [inference:EV-164] derived from EV-058
- Recommendation: Before Build Phase 5, benchmark three options on a synthetic 9.5M-vector set: (a) the B-tree pre-filter with exact distance, (b) HNSW with a filter, and (c) partitioning by learner hash. Measure p95 latency and recall@k. Record the plan choice and memory footprint in Section 12.
  - Issue: The latency and recall premise for filtered vector search is unverified.
  - Rationale: NFR-1, NFR-2 and NFR-10 cost all rest on this premise.
  - Expected benefit: Confidence that NFR-1, NFR-2 and NFR-10 hold, or an early change of index strategy. (objectives: NFR-1, NFR-2, NFR-10)
  - Supporting evidence: EV-058, EV-108, EV-164
  - Verification: The NFR-2 benchmark is extended with recall@k ≥ an agreed threshold alongside p95 ≤ 15 ms.
- Next step: Platform data engineer: Run a pgvector filtered-search prototype at full synthetic scale and report latency, recall and RAM use.

### FND-041 The 48-hour token lifetime is attributed to Entra ID without saying which token or how it is configured

- **validation need** · unsupported or incorrect claim · severity **medium** · confidence 0.50 (medium) · rank 43
- Disposition: **needs investigation** (also: refinement now)

The design states that OAuth 2.0 tokens via Entra ID are valid for 48 hours, and NFR-6 tests ACTIVE status until T+48h. It does not say whether this means the Entra ID access token, the refresh token, or a platform-issued session token, nor how a 48-hour lifetime is configured. Whether Entra ID access tokens can be configured to 48 hours was not verified here. If they cannot, the Check 3 state machine and the NFR-6 test rest on a premise that does not hold.

- Where: p.8 §6 (NFR-6): "Authentication is OAuth 2.0 via Entra ID. Tokens are valid for 48 hours."
- Where: p.4 §2.2 (NFR-6): "Auth tokens shall be valid for 48 hours, with defined degraded-mode behaviour for EXPIRED and REVOKED"
- Evidence EV-122 (doc, supports): "Authentication is OAuth 2.0 via Entra ID. Tokens are valid for 48 hours." [doc:DOC-sit_sample_v1#p8/s6]
- Recommendation: In Section 6, name the token that carries the 48-hour lifetime (Entra access token, refresh token, or platform session token), the configuration mechanism, and how revocation is detected. Update the NFR-6 test in Section 27.2 accordingly.
  - Issue: It is unclear which token has the 48-hour lifetime, and whether Entra ID can be configured that way.
  - Rationale: Token states drive the Gateway's degraded-mode behaviour and the NFR-6 test.
  - Expected benefit: Check 3 and NFR-6 are implementable and testable against the real identity provider. (objectives: NFR-6, FR-4)
  - Supporting evidence: EV-122
  - Verification: Identity team confirmation plus a token-lifecycle test against the SIT Entra tenant.
- Next step: Identity / IAM engineer: Confirm the configurable token lifetimes and revocation signals in the SIT Entra ID tenant.

### FND-033 NFR-6 token-lifecycle test assumes the platform controls a 48-hour Entra ID token lifetime

- **validation need** · unsupported or incorrect claim · severity **low** · confidence 0.50 (medium) · rank 47
- Disposition: **needs investigation** (also: refinement now)

NFR-6 and its test treat a 48-hour token lifetime and the ACTIVE→EXPIRED transition as behaviour the platform controls. Authentication is delegated to Entra ID, so it needs checking whether the 48 hours is an access-token lifetime set by Entra ID or a platform session window built on refresh tokens. The test needs a different design depending on the answer.

- Where: p.27 §27.2 (NFR-6): "Tokens issued at T are ACTIVE until T+48h, then transition to EXPIRED; a"
- Where: p.8 §6 (NFR-6): "Authentication is OAuth 2.0 via Entra ID. Tokens are valid for 48 hours."
- Evidence EV-121 (doc, supports): "Tokens issued at T are ACTIVE until T+48h, then transition to EXPIRED; a" [doc:DOC-sit_sample_v1#p27/s27.2]
- Evidence EV-122 (doc, supports): "Authentication is OAuth 2.0 via Entra ID. Tokens are valid for 48 hours." [doc:DOC-sit_sample_v1#p8/s6]
- Recommendation: Find out whether Entra ID can be configured for 48-hour access tokens, or redefine NFR-6 as a platform session window (refresh-token based) with its own ACTIVE/EXPIRED state. Update the Section 27.2 test to use a controllable clock on that state machine.
  - Issue: It is unclear who owns the 48-hour lifetime, so the NFR-6 test may be untestable as written.
  - Rationale: Token issuance is delegated to Entra ID, so the platform may not be able to set the token's validity.
  - Expected benefit: NFR-6 becomes testable and the degraded-mode triggers are accurate. (objectives: NFR-6)
  - Supporting evidence: EV-121, EV-122
  - Verification: Identity-team confirmation recorded in Section 6, and the test runs against the defined state owner.
- Next step: Identity / Entra ID administrator: Confirm which token lifetime can be configured, and the mechanism for the 48-hour window.

## Recommended refinements

| Finding | Change | Expected benefit |
|---|---|---|
| FND-020 | In Section 19, exclude memory_sensitive from Super Admin and Institution Admin access. In Section 21, state that emergency access does not apply to counselling. Make the counselling named_agents list fixed at deployment (credential-level, not changeable by the MMP), or record an explicit, owned exception. Extend the FR-5 test to cover super-admin, Admin API and agent_registry-edit attempts. | FR-5 and P4 become consistent and enforceable, and counselling data is protected from administrative access. |
| FND-021 | Choose one rule for Sections 14 and 17: backup used only in degraded mode, or backup gap-filling allowed with FR-16 reworded. Add a deletion-propagation rule: learner deletion events purge or tombstone the matching agent backup entries. Specify where agent backup is stored and require HIGHLY_RESTRICTED backup data to sit under memory_sensitive credentials. | Learner deletion takes effect everywhere (FR-15, P2, PDPA), and the backup role matches FR-16 and P1. |
| FND-045 | In Sections 13, 20 and FR-16: (a) apply tier, retention and pii rules to agent backup; (b) propagate learner deletion to backups, or limit backup to a short-lived cache with a TTL; (c) forbid HIGHLY_RESTRICTED content in backups outside memory_sensitive; (d) audit backup reads and writes. Add the backup to the FR-15 test. | Deletion, audit and the counselling hard wall would hold across every copy of learner data. |
| FND-001 | In Sections 13, 14 and 20, specify the backup as a bounded cache: governed by the same policy dimensions, audited, scoped to the fields needed for degraded mode, excluded for HIGHLY_RESTRICTED slots (or held in a memory_sensitive-equivalent store), and purged when the learner deletes their own memory. Remove 'fills gaps' from Source 3 when the token is ACTIVE, or amend FR-16 to allow it. Extend the FR-15 test to assert the backup is purged. | Learner deletion and the counselling hard wall stay effective, and FR-16 holds as written. |
| FND-022 | In Sections 17 and 18, run schema validation (key, type, sensitivity ceiling) synchronously at the Gateway before enqueue, or define a dead-letter topic with an audit entry, a dashboard surface and an agent-visible status lookup. Add bounded retries for transient errors only. Choose the sensitivity topic after a synchronous tier determination, or forbid the consumer from upgrading the tier. | Writes are not lost silently, retry storms are prevented, and FR-11 and NFR-5 isolation hold in practice. |
| FND-036 | In Sections 15, 16 and 21, state which runtime components (the policy evaluator, audit writer, and a provisioning queue) are deployed in the request path separately from the MMP admin service. Define Check 4 behaviour when the MMP is unavailable, for example deny-and-log or defer through a queue. Extend the NFR-4 test in Section 27.2 to include a write to a not-yet-provisioned slot and an audit-completeness check while the MMP is down. | NFR-4 becomes achievable without weakening FR-8 or FR-13. |
| FND-002 | In Section 18 and FR-9, run the cheap synchronous checks at the Gateway before enqueue: the declared sensitivity against the slot ceiling (which selects the topic) and the template key check. Reorder the consumer to classify → validate → embed → route → audit. Define a rejection/dead-letter topic plus a write-status or callback mechanism, and state what happens when the consumer reclassifies to a higher tier (re-route without persisting to the standard tier). | HIGHLY_RESTRICTED isolation holds end to end, and agents learn when a write was rejected. |
| FND-012 | Have the DPO decide the deletion scope. Recommended: propagate learner deletions to agent per-learner backups, for example through a deletion event on Kafka consumed by every agent, keeping only non-content session metadata. Record the outcome in Section 25 and amend Sections 13 and 20. Extend the FR-15 test to assert that backups are purged. | FR-15 and P2 are honoured end-to-end, and the deletion scope is defensible to the DPO. |
| FND-047 | In Sections 6, 14 and 15: on REVOKED, serve only agent-global (non-learner) context and load no per_learner backup. On EXPIRED, limit backup use to the current session's working memory until re-authentication. | Revocation would be effective, protecting learner privacy (P2) and FR-4 check 3. |
| FND-003 | In Sections 6, 15 and 25, change REVOKED to 'no per-learner memory served; agent global only'. Keep backup-serving for EXPIRED only, bounded by a maximum degraded-session duration. Add an NFR-6 test asserting that no per_learner content is served on a REVOKED token. | NFR-6 degraded-mode behaviour no longer exposes personal data after revocation. |
| FND-026 | Build a prototype in an early phase: load 9.5M synthetic 1536-dim vectors with the realistic per-learner distribution on the chosen SKU and measure p50/p95 latency and recall@k against exact search, for filtered queries at a defined concurrent QPS. Define 'normal load' in NFR-2 (e.g. peak concurrent sessions × reads/turn). Add a recall threshold and the load level to the Section 27.2 NFR-2 criterion. Correct the Section 12 memory arithmetic and say whether the index is meant to be fully RAM-resident. | NFR-1, NFR-2 and NFR-10 are confirmed before the SKU and index design are fixed. |
| FND-035 | Build a prototype on synthetic data (~9.5M vectors, ~600 per learner) and compare three options: (a) HNSW with the filter, (b) an exact scan through the B-tree, (c) partitioning by learner or slot. Record EXPLAIN plans, recall@k against brute force, and p50/p95 latency. Then rewrite the Section 12 claim and the NFR-2 test in Section 27.2 to state the chosen query strategy and add a recall criterion. | NFR-2 latency and result completeness are shown before the SKU is committed, and the platform avoids over- or under-provisioning RAM. |
| FND-048 | In Sections 17, 18 and 21: place the audit sink in the request path, separate from the MMP (for example a dedicated append-only audit topic and table). Write the enqueue audit at the Gateway before the ACK and the outcome audit at the consumer, including validation rejects. Define fail-closed or buffered behaviour if the audit sink is unavailable. | FR-13 completeness and NFR-4 availability can both be met. |
| FND-004 | Add a decision table to Section 16 giving the outcome type per dimension (ALLOW/DENY/REDACT/EXPIRE) and the precedence rules. State that the engine runs in-process at the Gateway, with MMP only publishing rules. Rewrite the FR-8 criterion as 'each dimension produces its expected outcome type attributable to that dimension'. | FR-8 becomes implementable and testable within Build Phase 3. |
| FND-024 | In Section 11, add retention, expires_at and pii to all three tables. Add a key column to memory_events. Add embedded BOOLEAN and a tsvector column with a GIN index to memory_vectors. Downgrade the Section 28 rating to 'Mostly ready' until this is done. | NFR-7 becomes verifiable and the embedder fallback becomes implementable, and the readiness claim becomes accurate. |
| FND-013 | In Section 28 and Build Phase 3 (Section 29), make the decision table a DPO-approved artefact: engineering drafts it, the DPO signs it off, and it is added to Section 25 as a confirmed decision. Add FR-8 test cases for conflicting dimensions as well as single violations. | FR-8 becomes implementable and testable, with DPO-approved semantics. |
| FND-027 | In Section 18, define the outcome of a rejected async write (e.g. a dead-letter topic plus an audit entry with outcome=DENIED and reason=UNKNOWN_KEY, optionally a callback or status endpoint). Alternatively, move the template-key check into the synchronous Gateway step. Rewrite the FR-11 criterion to assert that the record is not stored and that the DLQ/audit entry exists. Set a numeric p99 enqueue budget (ms) in FR-9/NFR-3 and fix the NFR-3 tolerance. | FR-9, FR-11 and NFR-3 become testable, and agents and admins can see when writes are silently dropped. |
| FND-028 | When writing the Section 28 decision table, add the expected outcome per dimension (DENY, REDACT, EXPIRE/PURGE, ALLOW) and at least one test per pairwise precedence conflict. Update the Section 27.1 FR-8 criterion to assert those outcomes and reason codes. | FR-8 becomes testable, and Build Phase 3 has a defined oracle to test against. |
| FND-037 | Rework the Section 12 table so the per-learner items add up to the stated total. Model module vectors across a full degree after term-end compaction, and add an alumni growth model (graduates per year × retained vectors × retention years). Restate the total and the growth-ceiling year, and include table and other-index storage alongside the HNSW index in the RAM budget. | A defensible sizing basis for NFR-1, NFR-2 and NFR-10. |
| FND-005 | In Section 15 Check 4, define provisioning through a Gateway-local provisioner using cached published templates, or deny with a retryable code and an async provisioning request. Clarify in Sections 5, 8 and 21 that the runtime policy evaluation lives in the Gateway. Extend the NFR-4 test to include a first write to an unprovisioned auto-provisionable slot. | NFR-4 holds and the MMP-down chaos test is meaningful. |
| FND-014 | In Section 15 Check 4, specify behaviour when the MMP is down: deny with reason MMP_UNAVAILABLE, or provision from a Gateway-local template cache. In Sections 5, 16 and 21, state whether the runtime Policy Engine is a Gateway-side library or service distinct from the MMP PolicyEngine. Extend the NFR-4 test to include a first write to an unprovisioned module slot. | NFR-4 holds in practice, and operators know which components are tier-1. |
| FND-023 | In Section 15 Check 4, either deny with 'slot pending' and enqueue provisioning, or move SlotProvisioner logic into the request-path service. In Sections 5 and 21, state that the runtime Policy Engine and audit writer are request-path services and the MMP only configures them. | NFR-4 becomes achievable and agent availability does not depend on the admin plane. |
| FND-030 | Add to the Section 27.1 FR-16 criterion: seed key K with value A in the namespace and value B in the agent backup; with both available, the context pack contains A, and the audit source field = namespace. Define 'conflicting write-back' in the Dispatcher spec as the Pending Backlog item 3 is closed. | FR-16 and P1 can be verified. |
| FND-032 | Add the following to the Section 11 DDL: an embedded BOOLEAN column, a tsvector/full-text index for the keyword fallback, and tables for the audit store, agent_registry and agent backup (or state where these live). Add an acceptance test for the embedding-outage fallback (record stored with embedded=false, keyword retrieval works, backlog entry created). Downgrade the Section 28 ratings until this is done. | An accurate Section 28, and FR-13 and the embedder fallback become verifiable. |
| FND-039 | Close backlog item 9 before Phase 4. Then, in Section 18, specify the consumer retry policy, a dead-letter topic and monitoring, and idempotent processing. State whether the sensitive topic uses a separate namespace or cluster with its own credentials. Mark the Section 25 write-path decision as conditional until the backlog item is closed. | FR-9 durability and sensitive-tier isolation rest on specified mechanisms. |
| FND-040 | In Section 18, add cache invalidation on policy or template publication and on deletion events, for example a policy-version key in the cache entry. Alternatively, restate Section 16 to bound the delay to the session TTL. Add a test to Section 27 in which a mid-session policy change is reflected on the next read. | FR-8 recall and redaction decisions are enforced consistently with Section 16. |
| FND-049 | In Section 18: classify errors as transient (retry with backoff and a maximum attempt count) or permanent (dead-letter topic, audit entry, MMP dashboard warning). Require a client-generated memory_id/event_id as an idempotency key with upsert-or-ignore semantics. Optionally run a synchronous Validator pre-check at the Gateway so most rejects happen before the ACK. | FR-9 stays reliable under failure, FR-11 rejects are visible, and episodic memory is free of duplicates. |
| FND-007 | Move a minimal term-end and graduation rule (at least: archive raw records, mark the slot expired, no summarisation) into the Phase 2/5 scope in Section 29. Leave full summarisation-fidelity design in the backlog. | Lifecycle and retention rules can be enforced from the first term-end. |
| FND-015 | Add an owner role and target build phase to each Section 26 item. Reclassify audit retention sign-off (DPO) and term-end compaction rules as gating items before go-live, rather than deferrable items in Section 28. At minimum, define an interim rule such as 'no compaction; retain raw until spec closed' and record it in Section 25. | FR-13, FR-12 and the Section 20 lifecycle rules are implementable before the first term end, and PDPA retention is signed off. |
| FND-029 | In Section 17 Auditor / Section 27.1 FR-13, define the expected audit event set per operation type (e.g. read = token_validation + read; write = token_validation + enqueue + persist or DLQ). Give each set a shared request/correlation ID, and add a test that a consumer failure still yields a terminal audit event. | FR-13 and the PDPA audit claim (P7) can be verified. |
| FND-051 | In Section 18: use a separate Redis instance or credentials for the sensitive tier, or do not cache HIGHLY_RESTRICTED packs. Key cache entries by agent, learner, slot set and policy/template version, and invalidate them on policy change, permission change, deletion and token revocation events. | Counselling isolation and timely enforcement of revocations and deletions. |
| FND-006 | In Section 18, define the cache key as (learner_id, agent_id, session_id, policy_version). Invalidate on policy or template publication, or cache unredacted-but-permitted records and apply redaction on every serve. Add a cache-isolation case to the FR-10 test. | A cached read cannot bypass a policy change or another agent's clearance. |
| FND-016 | In Section 18, add a dead-letter topic per tier, a bounded retry policy, and audit and dashboard entries for every post-ACK rejection. Add a /dashboard/write-failures endpoint and consumer-lag alerting to Section 21, and name the operational owner. Add a test to Section 27 for an FR-11 strict-mode rejection appearing in the dead-letter topic and dashboard. | Reliable FR-9 and FR-11 behaviour, with operator visibility of write failures. |
| FND-031 | Extend the Section 27.1 FR-15 criterion to assert that the deleted keys are absent from the Redis cache, are not re-materialised by in-flight Kafka messages, and are absent from the re-embed backlog. For the agent backup, either assert removal or have the DPO explicitly record the retention exception in Section 20. | FR-15 and NFR-7 claims can be shown to hold, or the retained copies are explicitly accepted. |
| FND-042 | Make the DPO sign-off of the audit retention period and of the backup-survives-deletion rule a gate before Build Phase 4. Record the outcome in Sections 17, 20 and 25, and add a backup-deletion case to the FR-15 test. | NFR-7 and FR-15 rest on a DPO-approved retention and deletion basis. |
| FND-043 | Confirm with the SIS owner which events can be emitted (webhook, batch or CDC), and add an event contract (payload, delivery guarantees, replay) plus a reconciliation job to Section 21. | FR-12 becomes achievable, or a polling or batch fallback is designed early. |
| FND-050 | In Section 18 and FR-9: derive the tier from the slot's template ceiling at the Gateway before choosing a topic, and fail closed (route to sensitive) when unknown. Reorder the consumer to classify → validate → embed → route → audit. State that consumers on the sensitive topic use the separate embedding deployment named in Section 11. | End-to-end tier isolation for counselling data. |
| FND-053 | In Sections 11 and 17: run sensitive-tier Dispatcher/consumer workloads with a separate managed identity, the only holder of the memory_sensitive credential. In Section 13: store tokens in a secrets vault or keep them in session only, never in persistent agent memory. Confirm the 48-hour token validity against Entra ID token lifetime policy. | A meaningful credential-level hard wall and less exposure from token theft. |
| FND-008 | Add a Phase 5 prototype benchmark that captures query plans, p50/p95 latency and recall@k against an exact-scan baseline on the 9.5M synthetic dataset. Add a recall threshold to the NFR-2 acceptance criterion in Section 27.2. | NFR-2 is confirmed, or the index strategy is corrected, before SKU commitment. |
| FND-038 | In Section 12, add a dated cost breakdown from the Azure pricing calculator for the Singapore region, itemising compute, storage, backup, HA, and both schemas or servers. Separately list Event Hubs, Redis and embedding costs. Align the NFR-10 text and its Section 27.2 criterion to the same scope. | NFR-10 can be tested and relied on for budgeting. |
| FND-052 | Before Build Phase 5, benchmark three options on a synthetic 9.5M-vector set: (a) the B-tree pre-filter with exact distance, (b) HNSW with a filter, and (c) partitioning by learner hash. Measure p95 latency and recall@k. Record the plan choice and memory footprint in Section 12. | Confidence that NFR-1, NFR-2 and NFR-10 hold, or an early change of index strategy. |
| FND-054 | Add a subsection to Section 22 defining aggregation rules (minimum group size k, suppression of free text, exclusion of RESTRICTED as well as HIGHLY_RESTRICTED sources) and a DPO sign-off gate. Add an acceptance test. | Aggregate sharing stays consistent with P2 and PDPA obligations. |
| FND-041 | In Section 6, name the token that carries the 48-hour lifetime (Entra access token, refresh token, or platform session token), the configuration mechanism, and how revocation is detected. Update the NFR-6 test in Section 27.2 accordingly. | Check 3 and NFR-6 are implementable and testable against the real identity provider. |
| FND-017 | Mark the write-path and read-path rows in Section 25 as 'confirmed pattern; platform pending' with a link to the backlog items. Check that the Event Hubs tier chosen supports the per-tier topics, consumer groups and retry semantics assumed in Section 18 before Build Phase 4. | An accurate decision register, and the FR-9 and NFR-3 behaviour confirmed on the chosen broker. |
| FND-018 | Split NFR-10 into a vector-store cost bound and a total platform cost estimate covering Event Hubs, Redis, both embedding deployments and the MMP. Name a budget owner and an alert threshold on /dashboard/cost, and align the Section 27 NFR-10 criterion to each part. | NFR-10 becomes verifiable, and the platform's full run cost is approved by an accountable owner. |
| FND-044 | In Section 11, add an embedded boolean and a full-text search column and index. Name the ranking method (built-in full-text ranking, or a confirmed extension available on Azure PostgreSQL). Change the Section 28 database schema rating accordingly. | FR-10 reads stay functional during embedding outages. |
| FND-033 | Find out whether Entra ID can be configured for 48-hour access tokens, or redefine NFR-6 as a platform session window (refresh-token based) with its own ACTIVE/EXPIRED state. Update the Section 27.2 test to use a controllable clock on that state machine. | NFR-6 becomes testable and the degraded-mode triggers are accurate. |

## Areas where no change is needed

- FND-009 Clear, traceable statement of intent: principles, ID'd requirements, acceptance criteria and an honest readiness assessment: The traceability structure is fit for the document's purpose of guiding implementation and review; the individual gaps are covered by other findings.
- FND-034 Requirement-by-requirement acceptance matrix with honest readiness assessment: Full FR/NFR-to-test traceability already serves the stated build-readiness purpose.
- FND-010 Counselling hard wall enforced in layers: policy, schema and credentials, with matching tests: The layered enforcement and its tests serve FR-5, NFR-5 and P4 directly; no change is needed beyond the caveats raised in FND-001 and FND-002.
- FND-019 Explicit decision register, principle precedence and honest readiness gating: The decision register, the principle-precedence rule and readiness gating already give clear governance of design decisions. Findings FND-020, FND-015 and FND-017 refine how they are applied, but the mechanism itself needs no change.
- FND-055 Ordered pre-retrieval Gateway checks with deny-and-log and per-check tests: The checks fail closed, are logged and are testable per check, which directly meets FR-4 and P3.
- SA-001 (sections 15): The six ordered, individually logged pre-retrieval checks map one-to-one onto FR-4 and P3. Each check has a defined pass/fail action and a dedicated test case in 27.1. (see FND-005)
  - p.15 §15: "Access control is pre-retrieval. The namespace check gates the query itself - not the returned results."
- SA-002 (sections 10, 11, 17): The mapping from memory type to store type, and the routing by sensitivity tier to two schemas on one PostgreSQL engine, are explicit and consistent. They serve FR-3, NFR-1 (no engine change) and NFR-5 with concrete DDL. (see FND-010)
  - p.12 §11: "DDL for the three table types. This DDL is duplicated once per schema (memory_standard, memory_sensitive)."
- SA-003 (sections 2, 27, 28): The requirement IDs, acceptance criteria and readiness assessment give a clear, reviewable statement of intent and of which gaps are known. (see FND-009)
  - p.26 §27: "Each requirement from Section 2 is validated by a specific method with a concrete pass/fail acceptance criterion."
- SA-004 (sections 25, 3): Recording each confirmed decision as a one-line answer, together with the rule that principles prevail, gives reviewers and builders a single reference for preserving decisions (P1–P10, FR-5). (see FND-019)
  - p.6 §3: "Where a later section appears to conflict with one of these, the principle wins."
- SA-005 (sections 28, 29): The readiness assessment and the phase-gating table explicitly block code generation for the Policy Engine, the Admin API and the SDK until their specifications exist. This is sound governance of the build sequence. (see FND-013, FND-019)
  - p.29 §28: "The honest answer is partial - strong in some areas, not"
- SA-006 (sections 27.1, 15): The FR-4 criterion tests each of the six Gateway checks on its own, with a reason code and an all-pass ALLOW case. This directly verifies the ordered pre-retrieval control (P3). (see FND-034)
  - p.26 §27.1: "Six test cases, one per check, each asserting a DENY with the correct reason"
- SA-007 (sections 27.2): The NFR-5 test checks credential isolation in both directions, and the NFR-4 chaos test stops the MMP and runs agent traffic. Both are direct, falsifiable checks of their requirements. (see FND-034)
  - p.27 §27.2: "A credential valid for memory_standard is confirmed to fail authentication"
  - p.27 §27.2: "With the MMP process stopped, a scripted sequence of agent reads and"
- SA-008 (sections 27.1): The FR-7 escalation test covers all three access rules (the triggering agent is denied, the target agent and a human reviewer are allowed), matching the requirement's wording.
  - p.27 §27.1: "Agent A writes an escalation; Agent A's own read attempt is denied; the"
- SA-009 (sections 26, 28): The design tracks its open premises (cohort namespace, compaction, Dispatcher edge cases, Auditor sign-off, broker and cache choices) in an explicit backlog. Section 28 links them to readiness, which supports traceable closure of assumptions before code generation. (see FND-039, FND-042)
  - p.29 §28: "The honest answer is partial - strong in some areas, not yet sufficient in others."
- SA-010 (sections 12, 11): The raw storage figure matches the declared embedding dimension: 9.5M × 1536 × 4 bytes ≈ 58 GB, against ~57 GB stated. The vector(1536) column matches the 1536-dimension embedding model, so this part of the sizing claim is internally sound. (see FND-035, FND-037)
  - p.12 §12: "Raw vector storage (1536-dim, 9.5M) ~57 GB HNSW"
- SA-011 (sections 15, 27.1): The Gateway enforces access before retrieval with ordered, fail-closed, logged checks, and each check has a matching test. This meets FR-4 and P3. (see FND-055)
  - p.15 §15: "Access control is pre-retrieval. The namespace check gates the query itself - not the returned results."
- SA-012 (sections 18): An async Kafka write path with separate per-tier topics is an appropriate way to absorb term-start write spikes without blocking agents (NFR-3), subject to the failure handling in FND-049. (see FND-049, FND-050)
  - p.17 §18: "separate topics per sensitivity tier keep HIGHLY_RESTRICTED writes physically isolated in transit."

## Unresolved issues and next steps

- FND-020 (governance decision): Counselling hard wall contradicted by Super Admin, MMP override and configurable named_agents (FND-020) Next step (Data governance officer / DPO): Decide whether any human or administrative break-glass access to counselling memory is permitted, then update Sections 15, 19 and 21 to match.
- FND-001 (governance decision): Agent per-learner backup memory sits outside the governed path and survives deletion (FND-001) Next step (Data governance officer / DPO with the platform architect): Decide the retention and deletion semantics for agent backup memory, then update Sections 13, 14 and 20 and the FR-15/FR-16 criteria.
- FND-012 (governance decision): Agent backup deliberately retains data after a learner deletes it (FND-012) Next step (Data Protection Officer): Rule on whether agent backups fall within learner deletion scope, and record the decision in Section 25.
- FND-047 (governance decision): Revoked token still yields learner data via agent backup (FND-047) Next step (Platform security lead): Decide degraded-mode scope per token state and update Sections 6, 14 and 15.
- FND-003 (governance decision): REVOKED tokens still receive learner-specific memory from the agent backup (FND-003) Next step (Information security lead with the DPO): Decide revoked-session behaviour and amend the auth decision in Section 25 accordingly.
- FND-026 (needs prototyping): NFR-2 5-15 ms filtered-HNSW latency rests on unbenchmarked sizing and search-space assumptions (FND-026) Next step (Platform architect / database engineer): Run a filtered pgvector benchmark at full synthetic scale before confirming the SKU and HNSW parameters.
- FND-035 (needs prototyping): Filtered HNSW search-space claim underpins NFR-2 and SKU sizing but is unverified (FND-035) Next step (Platform data architect): Run a pgvector filtered-query prototype on synthetic data at full scale before committing the 16 vCore / 128 GB SKU.
- FND-013 (governance decision): Policy precedence across the seven dimensions is a governance decision with no owner (FND-013) Next step (Data Protection Officer with Policy Engine lead): Draft and approve the seven-dimension precedence table before Build Phase 3 code generation.
- FND-039 (needs investigation): The Kafka/Event Hubs write path is 'confirmed' while still pending, and its broker claims are unverified (FND-039) Next step (Platform engineering lead): Confirm Event Hubs (Kafka API) feature fit and the isolation option for the sensitive tier, and record the decision.
- FND-007 (governance decision): Compaction deferred past launch, although term-end and graduation lifecycle rules depend on it (FND-007) Next step (Platform architect): Define the minimal launch compaction/archival rule and re-plan the build phases.
- FND-015 (governance decision): Audit retention and compaction are deferred but needed at launch (FND-015) Next step (Platform Team lead with Data Protection Officer): Assign owners and phases to the backlog items and confirm the audit retention period before Build Phase 4.
- FND-042 (governance decision): PDPA compliance is asserted throughout, but PDPA sign-off and retention basis are still pending (FND-042) Next step (Data Protection Officer): Decide the audit-log retention period and whether agent backups must be purged when a learner deletes their memory.
- FND-043 (needs investigation): FR-12 assumes the SIS can emit lifecycle webhooks, which is not verified (FND-043) Next step (SIS integration owner): Confirm SIS event emission capability and agree an event contract.
- FND-008 (needs prototyping): Filtered HNSW latency and recall premise for NFR-2 is unverified (FND-008) Next step (Platform engineering lead): Build the pgvector benchmark on the target SKU and record plans, latency and recall.
- FND-038 (needs investigation): The SGD 800-1,200/month cost (NFR-10) is unsourced and its scope is unclear (FND-038) Next step (Cloud FinOps / platform lead): Produce an itemised, dated Azure Singapore price quote for the confirmed SKU and supporting services.
- FND-052 (needs prototyping): Filtered HNSW latency/recall and memory fit at 9.5M vectors unproven (FND-052) Next step (Platform data engineer): Run a pgvector filtered-search prototype at full synthetic scale and report latency, recall and RAM use.
- FND-041 (needs investigation): The 48-hour token lifetime is attributed to Entra ID without saying which token or how it is configured (FND-041) Next step (Identity / IAM engineer): Confirm the configurable token lifetimes and revocation signals in the SIT Entra ID tenant.
- FND-017 (needs investigation): Confirmed write and read path decisions rest on pending platform choices (FND-017) Next step (Platform Architect): Close the Event Hubs and Redis platform choices with a short feature-compatibility check before Build Phase 4.
- FND-018 (governance decision): Cost objective covers only the vector store and has no owner (FND-018) Next step (Platform Team lead (budget owner)): Produce a total platform cost estimate and set a cost alert threshold.
- FND-033 (needs investigation): NFR-6 token-lifecycle test assumes the platform controls a 48-hour Entra ID token lifetime (FND-033) Next step (Identity / Entra ID administrator): Confirm which token lifetime can be configured, and the mechanism for the 48-hour window.

Research questions left unanswered:
- RQ-003: Does Azure Database for PostgreSQL Flexible Server in the Singapore region support pgvector with HNSW at the needed version? Do 128 GB RAM hold a ~57 GB raw vector set plus an ~80 GB HNSW index in memory, as the 'in-RAM index' latency claim assumes?
- RQ-004: Is the BM25 keyword fallback in the Embedder realistic on Azure PostgreSQL, given that native full-text ranking (ts_rank) is not BM25? And is the read path specified for records flagged embedded:false?
- RQ-009: Can Microsoft Entra ID OAuth 2.0 issue or honour 48-hour access tokens? What are the default and configurable access/refresh token lifetimes, and how is revocation detected for a self-contained JWT?
- RQ-010: Is the SGD 800-1,200/month estimate credible for a Memory Optimised 16-vCore Azure Database for PostgreSQL Flexible Server in Southeast Asia, with storage, HA and backup? Is Event Hubs (Kafka-enabled tier), Redis and embedding cost included or excluded?
- RQ-011: Is Azure OpenAI text-embedding-3-small available in an Azure Singapore (Southeast Asia) region or deployment type that keeps data in the region? Does sending HIGHLY_RESTRICTED counselling content to it raise data-residency or transfer concerns under the Singapore PDPA Transfer Limitation Obligation?
- RQ-012: Does the per-agent per-learner backup (FR-16, 'survives learner self-deletion', 'full store always present for all learners') conflict with the FR-15 deletion promise, the P2/P4 counselling hard wall and the Singapore PDPA obligations on retention limitation, consent withdrawal and protection? Is the backup covered by the Gateway, the tiering and audit?
- RQ-014: Is using the mutable UPN as learner_id, the primary key everywhere, while the immutable oid is held as a secondary field, a risk to identity integrity and correct access control when a UPN changes or is reassigned?
- RQ-015: How do Azure Event Hubs in Kafka mode behave on consumer failure and retry? Is there automatic retry or a dead-letter queue, what is the delivery guarantee (at-least-once), and what limits apply to partitions, throughput units or message size? Does the claim 'failed writes queue and retry automatically' hold for the term-start spike?
- RQ-016: Does the design handle concurrent writes from several agents to the same slot, ordering per learner, audit volume (logging every cache hit across 15,000 learners), HNSW index build and maintenance at 9.5M vectors with deletions, and the 30-40M growth ceiling?
- RQ-019: Is there a recognised benchmark method for filtered approximate-nearest-neighbour latency together with recall (for example ann-benchmarks style recall@k at a target QPS) that should be added to the NFR-2 benchmark?

## Evidence limitations

- DOC-sit_sample_v1: native PDF block not sent because the configured model backend accepts text only. Impact: figures, diagrams and tables rendered as images were not visible to the model; the review is based on the extracted text (DEG-001)
- assess shard 3/6 (requirements_and_consistency) was cut by the stage 1 limit at 265 s; 5 finished finding(s) kept (cut call llm-0005). Impact: every criterion of the shard has a finding; the shard's lower-ranked findings, if any, are missing (DEG-002)
- the refine call was cut by the run deadline (the refine model call was cut after 48 s by the refine limit (465 s on the run clock; deadline 540 s; not retried past it)). Impact: 4 of 55 refine revisions (one per merged finding) were applied from the cut answer, which had finished 4; the other 51 merged findings were not refined (no duplicates merged, no registry decisions linked, no research evidence attached for them) and follow the refined ones in their merged severity and confidence order (DEG-003)
- anchor repair call skipped: -0 s of slack left before the verify and verdict reserve (the call needs more than 60 s). Impact: unresolved anchors were not re-quoted; affected findings may be listed as unverified (DEG-004)
- FND-001's recommendation appears to reverse approved decision AD-008 (25 Confirmed Decisions - Two sensitivity tiers) without a 'challenges' label. Impact: the conflict is not declared and not backed by the two evidence items a challenge needs; check it against the decision before acting on it (DEG-005)

## Evidence register

| ID | Type | Source | Retrieved | Cited |
|---|---|---|---|---|
| EV-001 | external (informal) | [Iterative Scanning | pgvector/pgvector | DeepWiki](https://deepwiki.com/pgvector/pgvector/6.2-iterative-scanning) via mcp-internet-search/search_web call-0001 | 2026-10-04T03:44:11Z | no |
| EV-002 | external (secondary) | [Why pgvector Returns Too Few Results: Filtered HNSW, ef_search, and ...](https://rajivonai.com/blog/2026-04-27-pgvector-filtered-search-too-few-results/) via mcp-internet-search/search_web call-0001 | 2026-10-04T03:44:11Z | no |
| EV-003 | external (informal) | [Filtering and Advanced Queries | antheham/pgvector | DeepWiki](https://deepwiki.com/antheham/pgvector/5.4-filtering-and-advanced-queries) via mcp-internet-search/search_web call-0001 | 2026-10-04T03:44:11Z | no |
| EV-004 | external (informal) | [pgvector HNSW Postgres 18 Production Tuning Tutorial 2026](https://nerdleveltech.com/pgvector-hnsw-postgres-18-production-tuning-tutorial) via mcp-internet-search/search_web call-0001 | 2026-10-04T03:44:11Z | no |
| EV-005 | external (informal) | [Understanding HNSW + filtering · Issue #259 · pgvector/pgvector - GitHub](https://github.com/pgvector/pgvector/issues/259) via mcp-internet-search/search_web call-0001 | 2026-10-04T03:44:11Z | no |
| EV-006 | external (informal) | mcp:mcp-internet-search/search_web?{"fetch_top_n":2,"mode":"answer","query":"microsoft entra id access token lifetime default configurable token lifetime"} via mcp-internet-search/search_web call-0002 | 2026-10-04T03:44:11Z | no |
| EV-007 | external (primary official) | [Region availability for Foundry Models sold by Azure ...](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability) via mcp-internet-search/search_web call-0003 | 2026-10-04T03:44:11Z | no |
| EV-008 | external (informal) | [text-embedding-3-small by OpenAI — Availability on Microsoft ...](https://modelavailability.com/models/openai/text-embedding-3-small) via mcp-internet-search/search_web call-0003 | 2026-10-04T03:44:11Z | no |
| EV-009 | external (primary official) | [Can't find region availability for Text-Embeddings. Grrrr](https://learn.microsoft.com/en-us/answers/questions/5660082/cant-find-region-availability-for-text-embeddings) via mcp-internet-search/search_web call-0003 | 2026-10-04T03:44:11Z | no |
| EV-010 | external (informal) | [text-embedding-3-small | Model Catalog | Microsoft Foundry](https://ai.azure.com/catalog/models/text-embedding-3-small) via mcp-internet-search/search_web call-0003 | 2026-10-04T03:44:11Z | no |
| EV-011 | external (primary official) | [Product Availability by Region](https://azure.microsoft.com/en-us/explore/global-infrastructure/products-by-region/table) via mcp-internet-search/search_web call-0003 | 2026-10-04T03:44:11Z | no |
| EV-012 | external (primary official) | [ID token claims reference - Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference) via mcp-internet-search/search_web call-0004 | 2026-10-04T03:44:11Z | no |
| EV-013 | external (primary official) | [Access token claims reference - Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference) via mcp-internet-search/search_web call-0004 | 2026-10-04T03:44:11Z | no |
| EV-014 | external (primary official) | [Access token claims reference | Azure Docs](https://docs.azure.cn/en-us/entra/identity-platform/access-token-claims-reference) via mcp-internet-search/search_web call-0004 | 2026-10-04T03:44:11Z | no |
| EV-015 | external (primary official) | [ID token claims reference | Azure Docs](https://docs.azure.cn/en-us/entra/identity-platform/id-token-claims-reference) via mcp-internet-search/search_web call-0004 | 2026-10-04T03:44:11Z | no |
| EV-016 | external (informal) | [entra-docs/docs/identity-platform/optional-claims-reference ...](https://github.com/MicrosoftDocs/entra-docs/blob/main/docs/identity-platform/optional-claims-reference.md) via mcp-internet-search/search_web call-0004 | 2026-10-04T03:44:11Z | no |
| EV-017 | external (primary official) | [Azure Event Hubs Quotas and Limits Overview - Azure Event ...](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-quotas) via mcp-internet-search/search_web call-0005 | 2026-10-04T03:44:16Z | no |
| EV-018 | external (primary official) | [Azure Event Hubs Scalability Guide - Azure Event Hubs ...](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-scalability) via mcp-internet-search/search_web call-0005 | 2026-10-04T03:44:16Z | no |
| EV-019 | external (secondary) | [How to Configure Partitions and Throughput Units in Azure ...](https://oneuptime.com/blog/post/2026-02-16-how-to-configure-partitions-and-throughput-units-in-azure-event-hubs/view) via mcp-internet-search/search_web call-0005 | 2026-10-04T03:44:16Z | no |
| EV-020 | external (secondary) | [Azure Event Hubs Scaling Guide: Throughput Units (TUs ...](https://opstree.com/blog/azure-event-hubs-scaling-guide/) via mcp-internet-search/search_web call-0005 | 2026-10-04T03:44:16Z | no |
| EV-021 | external (primary official) | [Frequently asked questions - Azure Event Hubs | Azure Docs](https://docs.azure.cn/en-us/event-hubs/event-hubs-faq) via mcp-internet-search/search_web call-0005 | 2026-10-04T03:44:16Z | no |
| EV-022 | external (primary official) | [Personal Data Protection Act 2012 - Singapore Statutes Online](https://sso.agc.gov.sg/Act/PDPA2012?ProvIds=P14-) via mcp-internet-search/search_web call-0006 | 2026-10-04T03:44:27Z | no |
| EV-023 | external (informal) | [PDPA2012 § 25 — Retention of personal data | LawPlayer SG](https://lawplayer.com/sg/act/PDPA2012/25) via mcp-internet-search/search_web call-0006 | 2026-10-04T03:44:27Z | no |
| EV-024 | external (primary official) | [Data Protection Obligations - PDPC](https://www.pdpc.gov.sg/data-protection-obligations) via mcp-internet-search/search_web call-0006 | 2026-10-04T03:44:27Z | no |
| EV-025 | external (secondary) | [PDPA Withdrawal of Consent: What Happens When Customers Opt ...](https://complyhq.app/blog/pdpa-withdrawal-consent-singapore) via mcp-internet-search/search_web call-0006 | 2026-10-04T03:44:27Z | no |
| EV-026 | external (informal) | [https://github.com/pgvector/pgvector](https://github.com/pgvector/pgvector) via mcp-internet-search/fetch_url call-0007 | 2026-10-04T03:44:46Z | no |
| EV-027 | external (primary official) | [Configurable Token Lifetimes - Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/configurable-token-lifetimes) via mcp-internet-search/search_web call-0008 | 2026-10-04T03:44:46Z | no |
| EV-028 | external (primary official) | [Set token lifetimes - Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/configure-token-lifetimes) via mcp-internet-search/search_web call-0008 | 2026-10-04T03:44:46Z | no |
| EV-029 | external (primary official) | [Access tokens in the Microsoft identity platform | Azure Docs](https://docs.azure.cn/en-us/entra/identity-platform/access-tokens) via mcp-internet-search/search_web call-0008 | 2026-10-04T03:44:46Z | no |
| EV-030 | external (secondary) | [How to Set Up Microsoft Entra ID Token Lifetime Policies](https://oneuptime.com/blog/post/2026-02-16-how-to-set-up-microsoft-entra-id-token-lifetime-policies-for-access-and-refresh-tokens/view) via mcp-internet-search/search_web call-0008 | 2026-10-04T03:44:46Z | no |
| EV-031 | external (primary official) | [Set token lifetimes | Azure Docs](https://docs.azure.cn/en-us/entra/identity-platform/configure-token-lifetimes) via mcp-internet-search/search_web call-0008 | 2026-10-04T03:44:46Z | no |
| EV-032 | external (primary official) | [Vector Search in Azure Database for PostgreSQL Flexible ...](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector) via mcp-internet-search/search_web call-0009 | 2026-10-04T03:44:46Z | no |
| EV-033 | external (primary official) | [Optimize performance when using pgvector in Azure Database ...](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-optimize-performance-pgvector) via mcp-internet-search/search_web call-0009 | 2026-10-04T03:44:46Z | no |
| EV-034 | external (informal) | [Deploy Azure PostgreSQL flexible server with pgvector extension](https://jczopek.dev/post/azure-deploy-postgres-with-pgvector/) via mcp-internet-search/search_web call-0009 | 2026-10-04T03:44:46Z | no |
| EV-035 | external (informal) | [Easily deploy a pgvector-enabled PostgreSQL server to Azure](https://thewindowsupdate.com/2024/04/10/easily-deploy-a-pgvector-enabled-postgresql-server-to-azure/) via mcp-internet-search/search_web call-0009 | 2026-10-04T03:44:46Z | no |
| EV-036 | external (primary official) | [List of the PostgreSQL Extensions and Modules for an Azure ...](https://docs.azure.cn/en-us/postgresql/extensions/concepts-extensions-by-engine) via mcp-internet-search/search_web call-0009 | 2026-10-04T03:44:46Z | no |
| EV-037 | external (primary official) | [Resilient Azure Event Hubs and Azure Functions design](https://learn.microsoft.com/en-us/azure/architecture/serverless/event-hubs-functions/resilient-design) via mcp-internet-search/search_web call-0010 | 2026-10-04T03:44:46Z | no |
| EV-038 | external (primary official) | [Apache Kafka client configurations for Azure Event Hubs](https://learn.microsoft.com/en-us/azure/event-hubs/apache-kafka-configurations) via mcp-internet-search/search_web call-0010 | 2026-10-04T03:44:46Z | no |
| EV-039 | external (informal) | [Does Microsoft Azure Event Hub have support for dead-letter ...](https://stackoverflow.com/questions/75457860/does-microsoft-azure-event-hub-have-support-for-dead-letter-topic-and-dead-lette) via mcp-internet-search/search_web call-0010 | 2026-10-04T03:44:46Z | no |
| EV-040 | external (primary official) | [Use Azure Event Hubs from Apache Kafka applications](https://docs.azure.cn/en-us/event-hubs/event-hubs-for-kafka-ecosystem-overview) via mcp-internet-search/search_web call-0010 | 2026-10-04T03:44:46Z | no |
| EV-041 | external (informal) | [azure-event-hubs-for-kafka/CONFIGURATION.md at master · Azure ...](https://github.com/Azure/azure-event-hubs-for-kafka/blob/master/CONFIGURATION.md) via mcp-internet-search/search_web call-0010 | 2026-10-04T03:44:46Z | no |
| EV-042 | doc | doc:DOC-sit_sample_v1#p19/s20 | - | yes |
| EV-043 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-044 | doc | doc:DOC-sit_sample_v1#p13/s14 | - | yes |
| EV-045 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-046 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-047 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-048 | doc | doc:DOC-sit_sample_v1#p8/s6 | - | yes |
| EV-049 | doc | doc:DOC-sit_sample_v1#p15/s15 | - | yes |
| EV-050 | doc | doc:DOC-sit_sample_v1#p29/s28 | - | yes |
| EV-051 | doc | doc:DOC-sit_sample_v1#p15/s16 | - | yes |
| EV-052 | doc | doc:DOC-sit_sample_v1#p15/s15 | - | yes |
| EV-053 | doc | doc:DOC-sit_sample_v1#p19/s21 | - | yes |
| EV-054 | doc | doc:DOC-sit_sample_v1#p16/s16 | - | yes |
| EV-055 | doc | doc:DOC-sit_sample_v1#p18/s18 | - | yes |
| EV-056 | doc | doc:DOC-sit_sample_v1#p30/s28 | - | yes |
| EV-057 | doc | doc:DOC-sit_sample_v1#p19/s20 | - | yes |
| EV-058 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-059 | doc | doc:DOC-sit_sample_v1#p27/s27.2 | - | yes |
| EV-060 | doc | doc:DOC-sit_sample_v1#p26/s27 | - | yes |
| EV-061 | doc | doc:DOC-sit_sample_v1#p4/s2.2 | - | yes |
| EV-062 | inference | inference:EV-062 from EV-042, EV-043, EV-044 | - | yes |
| EV-063 | inference | inference:EV-063 from EV-045, EV-046, EV-047 | - | yes |
| EV-064 | inference | inference:EV-064 from EV-048, EV-049 | - | yes |
| EV-065 | inference | inference:EV-065 from EV-050, EV-051 | - | yes |
| EV-066 | inference | inference:EV-066 from EV-052, EV-053 | - | yes |
| EV-067 | inference | inference:EV-067 from EV-054, EV-055 | - | yes |
| EV-068 | inference | inference:EV-068 from EV-056, EV-057 | - | yes |
| EV-069 | inference | inference:EV-069 from EV-058, EV-059 | - | yes |
| EV-070 | doc | doc:DOC-sit_sample_v1#p18/s19 | - | yes |
| EV-071 | doc | doc:DOC-sit_sample_v1#p20/s21 | - | yes |
| EV-072 | doc | doc:DOC-sit_sample_v1#p3/s2.1 | - | yes |
| EV-073 | doc | doc:DOC-sit_sample_v1#p13/s13 | - | yes |
| EV-074 | doc | doc:DOC-sit_sample_v1#p29/s28 | - | yes |
| EV-075 | doc | doc:DOC-sit_sample_v1#p30/s28 | - | yes |
| EV-076 | doc | doc:DOC-sit_sample_v1#p4/s2.2 | - | yes |
| EV-077 | doc | doc:DOC-sit_sample_v1#p16/s16 | - | yes |
| EV-078 | doc | doc:DOC-sit_sample_v1#p26/s26 | - | yes |
| EV-079 | doc | doc:DOC-sit_sample_v1#p19/s20 | - | yes |
| EV-080 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-081 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-082 | doc | doc:DOC-sit_sample_v1#p26/s26 | - | yes |
| EV-083 | doc | doc:DOC-sit_sample_v1#p25/s25 | - | yes |
| EV-084 | doc | doc:DOC-sit_sample_v1#p5/s2.2 | - | yes |
| EV-085 | doc | doc:DOC-sit_sample_v1#p28/s27.2 | - | yes |
| EV-086 | doc | doc:DOC-sit_sample_v1#p6/s3 | - | yes |
| EV-087 | doc | doc:DOC-sit_sample_v1#p26/s26 | - | yes |
| EV-088 | inference | inference:EV-088 from EV-070, EV-071, EV-072 | - | yes |
| EV-089 | inference | inference:EV-089 from EV-073, EV-043 | - | yes |
| EV-090 | inference | inference:EV-090 from EV-056, EV-079 | - | yes |
| EV-091 | inference | inference:EV-091 from EV-080, EV-081 | - | yes |
| EV-092 | doc | doc:DOC-sit_sample_v1#p21/s22 | - | yes |
| EV-093 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-094 | doc | doc:DOC-sit_sample_v1#p13/s13 | - | yes |
| EV-095 | doc | doc:DOC-sit_sample_v1#p8/s5 | - | yes |
| EV-096 | doc | doc:DOC-sit_sample_v1#p29/s28 | - | yes |
| EV-097 | doc | doc:DOC-sit_sample_v1#p16/s17 | - | yes |
| EV-098 | doc | doc:DOC-sit_sample_v1#p16/s17 | - | yes |
| EV-099 | inference | inference:EV-099 from EV-071, EV-092 | - | yes |
| EV-100 | inference | inference:EV-100 from EV-044, EV-094, EV-043 | - | yes |
| EV-101 | inference | inference:EV-101 from EV-045, EV-080, EV-046 | - | yes |
| EV-102 | inference | inference:EV-102 from EV-096, EV-097, EV-098 | - | yes |
| EV-103 | doc | doc:DOC-sit_sample_v1#p26/s27.1 | - | no |
| EV-104 | doc | doc:DOC-sit_sample_v1#p3/s2.1 | - | no |
| EV-105 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-106 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-107 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-108 | doc | doc:DOC-sit_sample_v1#p4/s2.2 | - | yes |
| EV-109 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-110 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-111 | doc | doc:DOC-sit_sample_v1#p27/s27.1 | - | yes |
| EV-112 | doc | doc:DOC-sit_sample_v1#p27/s27.1 | - | yes |
| EV-113 | doc | doc:DOC-sit_sample_v1#p27/s27.1 | - | yes |
| EV-114 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-115 | doc | doc:DOC-sit_sample_v1#p17/s17 | - | yes |
| EV-116 | doc | doc:DOC-sit_sample_v1#p27/s27.1 | - | yes |
| EV-117 | doc | doc:DOC-sit_sample_v1#p4/s2.1 | - | yes |
| EV-118 | doc | doc:DOC-sit_sample_v1#p26/s26 | - | yes |
| EV-119 | doc | doc:DOC-sit_sample_v1#p27/s27.1 | - | yes |
| EV-120 | doc | doc:DOC-sit_sample_v1#p13/s13 | - | yes |
| EV-121 | doc | doc:DOC-sit_sample_v1#p27/s27.2 | - | yes |
| EV-122 | doc | doc:DOC-sit_sample_v1#p8/s6 | - | yes |
| EV-123 | inference | inference:EV-123 from EV-103, EV-104, EV-070 | - | yes |
| EV-124 | inference | inference:EV-124 from EV-106, EV-107 | - | yes |
| EV-125 | inference | inference:EV-125 from EV-105 | - | yes |
| EV-126 | inference | inference:EV-126 from EV-109, EV-110 | - | yes |
| EV-127 | inference | inference:EV-127 from EV-096, EV-098 | - | yes |
| EV-128 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-129 | doc | doc:DOC-sit_sample_v1#p11/s11 | - | yes |
| EV-130 | doc | doc:DOC-sit_sample_v1#p20/s21 | - | yes |
| EV-131 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-132 | doc | doc:DOC-sit_sample_v1#p12/s12 | - | yes |
| EV-133 | doc | doc:DOC-sit_sample_v1#p25/s25 | - | yes |
| EV-134 | doc | doc:DOC-sit_sample_v1#p18/s18 | - | yes |
| EV-135 | doc | doc:DOC-sit_sample_v1#p21/s21 | - | yes |
| EV-136 | doc | doc:DOC-sit_sample_v1#p26/s26 | - | yes |
| EV-137 | doc | doc:DOC-sit_sample_v1#p16/s17 | - | yes |
| EV-138 | inference | inference:EV-138 from EV-128, EV-129 | - | yes |
| EV-139 | inference | inference:EV-139 from EV-052, EV-130 | - | yes |
| EV-140 | inference | inference:EV-140 from EV-131 | - | yes |
| EV-141 | inference | inference:EV-141 from EV-132, EV-084 | - | yes |
| EV-142 | inference | inference:EV-142 from EV-133, EV-082 | - | yes |
| EV-143 | inference | inference:EV-143 from EV-134 | - | yes |
| EV-144 | inference | inference:EV-144 from EV-078, EV-073 | - | yes |
| EV-145 | inference | inference:EV-145 from EV-137 | - | yes |
| EV-146 | doc | doc:DOC-sit_sample_v1#p7/s5 | - | yes |
| EV-147 | doc | doc:DOC-sit_sample_v1#p21/s21 | - | no |
| EV-148 | doc | doc:DOC-sit_sample_v1#p8/s6 | - | yes |
| EV-149 | doc | doc:DOC-sit_sample_v1#p8/s5 | - | yes |
| EV-150 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-151 | doc | doc:DOC-sit_sample_v1#p17/s18 | - | yes |
| EV-152 | doc | doc:DOC-sit_sample_v1#p18/s18 | - | yes |
| EV-153 | doc | doc:DOC-sit_sample_v1#p27/s27.2 | - | yes |
| EV-154 | doc | doc:DOC-sit_sample_v1#p6/s3 | - | yes |
| EV-155 | doc | doc:DOC-sit_sample_v1#p21/s22 | - | yes |
| EV-156 | doc | doc:DOC-sit_sample_v1#p15/s15 | - | yes |
| EV-157 | doc | doc:DOC-sit_sample_v1#p26/s27.1 | - | yes |
| EV-158 | inference | inference:EV-158 from EV-073, EV-043, EV-146 | - | yes |
| EV-159 | inference | inference:EV-159 from EV-148 | - | yes |
| EV-160 | inference | inference:EV-160 from EV-076, EV-149 | - | yes |
| EV-161 | inference | inference:EV-161 from EV-150, EV-045 | - | yes |
| EV-162 | inference | inference:EV-162 from EV-151, EV-046 | - | yes |
| EV-163 | inference | inference:EV-163 from EV-077, EV-152 | - | yes |
| EV-164 | inference | inference:EV-164 from EV-058 | - | yes |
| EV-165 | inference | inference:EV-165 from EV-153, EV-122 | - | yes |

## Review coverage

| Criterion | Outcome | Findings | Note |
|---|---|---|---|
| design_intent | findings | FND-009, FND-001, FND-004 | Checked the purpose and scope, principles P1-P10, FR/NFR lists, confirmed decisions and the readiness assessment. Intent is clearly stated and traceable (FND-009). Where principles and sections disagree, the conflicts are reported in FND-001 (backup memory against P2/P7/FR-16) and FND-004 (where the policy engine runs). |
| fitness_for_objectives | findings | FND-001, FND-002, FND-003, FND-004, FND-005, FND-006, FND-007, FND-008, FND-010 | Assessed the Gateway, Policy Engine, Router, the write and read paths, the agent backup, the MMP, lifecycle and vector sizing against the FR/NFR targets. Significant fitness risks were found in backup governance, write-path ordering, revoked-token handling, MMP coupling and cache semantics. Counselling isolation is affirmed as a strength. |
| requirement_completeness | findings | FND-021, FND-022, FND-024 | no coverage row returned by the model; derived by code from the findings |
| internal_consistency | findings | FND-020, FND-021, FND-022, FND-023, FND-024 | no coverage row returned by the model; derived by code from the findings |
| claims_and_external_constraints | findings | FND-035, FND-037, FND-038, FND-039, FND-040, FND-041, FND-044 | Checked the vector sizing and latency claims, the cost estimate, broker and cache guarantees, the Entra ID token lifetime and the embedding fallback. The external facts could not be verified here and are framed as validation or investigation needs. |
| security_and_privacy | findings | FND-045, FND-020, FND-047, FND-048, FND-050, FND-051, FND-053, FND-054, FND-055 | Checked: agent backup governance, admin roles against the counselling wall, token states, audit path, tier isolation across Kafka, embedder, Redis and credentials, and aggregates. |
| scalability_and_failure_modes | findings | FND-047, FND-048, FND-049, FND-052 | Checked: async retry and idempotency, audit under MMP or consumer failure, degraded mode, and filtered pgvector latency and RAM fit at 9.5M vectors. |
| assumptions_and_dependencies | findings | FND-036, FND-039, FND-042, FND-043, FND-035, FND-037 | Checked the pending backlog against the confirmed decisions, and checked the dependencies on the MMP, the SIS, the broker and the DPO sign-off. |
| verifiability | findings | FND-020, FND-026, FND-027, FND-028, FND-029, FND-030, FND-031, FND-032, FND-033, FND-034 | Checked every FR/NFR criterion in Section 27 against its Section 2 requirement, plus the Section 12 sizing claims and the Section 28 readiness claims. FR-1, FR-2, FR-3, FR-4, FR-7, FR-10, FR-12, FR-14, NFR-4, NFR-5, NFR-8 and NFR-9 criteria are adequate. NFR-10 is a projection rather than a measurement, which is a minor point that was not raised. |
| decision_preservation | findings | FND-020, FND-014, FND-017, FND-019 | Checked Sections 19 and 21 against the confirmed counselling decision, the MMP-off-path decision (NFR-4) against Gateway Check 4, and the confirmed platform decisions against the pending backlog. The decision register is a strength. |
| operability_and_governance | findings | FND-020, FND-012, FND-013, FND-014, FND-015, FND-016, FND-018 | Checked owner roles, the backlog's ownership and gating, PDPA-related governance (deletion, audit retention, policy precedence), operability of async failures, and the scope and ownership of cost. |

## Run details

| | |
|---|---|
| Run | ui-261004-034213-c5cb (started 2026-10-04T03:42:13Z) |
| Outcome | completed_degraded |
| Model | requested claude-opus-5-5; served claude-opus-5-5; effort per-stage (extra.model.effort_by_stage) |
| Persona | generalist_architect |
| Tool transport | live |
| Tool session reopens | 3 (mcp-internet-search: 3) |
| Research stop | no_marginal_gain (decision): sufficient_evidence not met (model_stop_vote): 1 of 21 plan question(s) answered, 0 external source(s) cited by a finding; 1 iteration(s); 0 cited of 41 retrieved |
| Tool calls | mcp-internet-search: 10 |
| Tokens | input 494884, cached 164297, output 168710; cost ~$7.37 (price table 2026-09-25); a lower bound: 2 model calls with unrecorded usage (assess, deadline cut; refine, deadline cut) |
| Extractor | pdfplumber 0.11.10 |
| Config sha256 | 4556235eb170f756870b38a75e94353fd213f06b73abde51c9921c5ea7bb033a |
| Prompt bundle sha256 | 6f0ee28ab9acf35152a2d4456207a8a068222149422e66d801c8195455c28ba7 |
| Git commit | fe50a34b87da47a0e9f8e3087667e41ae35a1489 |
| Fault schedule | none |
| Model fallbacks | 0 |
| Canonical text DOC-sit_sample_v1 | sha256 7be073ff2e98e50998367a46b92ed5dbf85815177eb36c2e2c12a0f52a458de8 |
