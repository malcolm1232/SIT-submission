# Worked examples on the SIT Institutional Memory Platform Detailed Design

**Artefact:** *SIT Institutional Memory Platform — Detailed Design*, v2.0 (30 pages). Cited as `p.N §X`.
**Rubric:** `README.md` §3.

This file contains:
1. How a single finding is scored
2. Example A, exemplary (A grade)
3. Example B, mediocre (C grade)
4. Example C, looks good but should score low
5. Bonus Example D, a correct "no change needed"
6. Illustrative answer key for this artefact (key items, traps, no-change areas)
7. Sources verified while writing this file

---

## 1. How a single finding is scored

The rubric scores whole reviews. To show what each level looks like, we score single findings on the
dimensions that apply at finding level, keeping their review-level weights:

| D1 | D4 | D5 | D6 | D7 | D8 | D9 | Σ |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 16 | 14 | 10 | 8 | 8 | 8 | 74 |

**Finding Quality Score** `FQS = Σ wᵢ·sᵢ/4 ÷ 74 × 100`. The same bands as the review apply:
A ≥ 85, B ≥ 70, C ≥ 60, D ≥ 50, F < 50.
D2 (verdict), D3 (coverage) and D10 (structure) need the whole review and are not scored here.

---

## 2. Example A: exemplary finding (A grade)

> **F-07: Filtered vector retrieval. The "500–800 vector search space" assumption is not validated, and the
> specified index design may not deliver it**
> *Category:* unresolved assumption, risk · *Severity:* High · *Triage:* prototyping + testing (not yet a
> design refinement) · *Confidence:* medium-high
>
> **Design basis.** §12 (p.12): "Queries are always filtered by learner_id + slot_path — the effective search
> space per query is 500–800 vectors, not 9.5 million." The DDL in §11 (p.11) defines one HNSW index on
> `embedding` and a separate B-tree index on `(learner_id, slot_path)`. NFR-2 (p.4) requires 5–15 ms filtered
> queries. Its acceptance test (§27, p.27) measures **latency only** (p95 ≤ 15 ms, p50 ≤ 10 ms). The HNSW
> parameters are a Confirmed Decision (§25, p.25).
>
> **Issue.** The design assumes the filter shrinks the HNSW search space. In pgvector, the approximate index
> is not filter-aware: "With approximate indexes, filtering is applied *after* the index is scanned. If a
> condition matches 10% of rows, with HNSW and the default `hnsw.ef_search` of 40, only 4 rows will match on
> average." [E1]. A learner + slot filter matches about 600 of 9.5 M rows (≈ 6.3 × 10⁻⁵). If the planner
> chooses the HNSW index, the expected number of matching candidates is 40 × 6.3 × 10⁻⁵ ≈ 0.003 per query.
> The query would return few or no memories while still meeting the latency target. If the planner chooses
> the B-tree index instead, the search is an exact scan over about 600 rows. That is correct, and the README
> notes "Exact indexes work well for conditions that match a low percentage of rows" [E1]. But in that case
> the ~80 GB HNSW index (§12, p.12), which drives the 128 GB SKU and the SGD 800–1,200 cost (NFR-10, p.5),
> serves little of the main workload. In both cases the stated assumption is not what produces the
> performance.
>
> **Evidence.**
> [E1] pgvector README, "Filtering" section (github.com/pgvector/pgvector, master, accessed 2026-10-02).
> [E2] Same README, "Iterative Index Scans": "Starting with 0.8.0, you can enable iterative index scans, which
> will automatically scan more of the index until enough results are found"; CHANGELOG 0.8.0 (2024-10-30).
> [E3] Same README, "Multitenancy": "sharing an approximate index between tenants means vectors from one
> tenant can affect recall (and speed) for other tenants."
> Arithmetic: 600 / 9,500,000 ≈ 6.3 × 10⁻⁵; 40 × 6.3 × 10⁻⁵ ≈ 0.0025.
>
> **Recommendation.** This is bounded and does not reopen the pgvector decision in §25.
> 1. Add a **recall** criterion to the NFR-2 acceptance test (§27): e.g. recall@k ≥ 0.95 against exact search
>    for learner + slot filtered queries on the synthetic 9.5 M dataset. Record the planner's index choice
>    with `EXPLAIN ANALYZE`.
> 2. In Build Phase 5 (store layer), prototype three in-engine options: (a) B-tree with exact distance;
>    (b) HNSW with iterative scans (needs pgvector ≥ 0.8; *needs investigation:* confirm the version
>    available on the chosen Azure Database for PostgreSQL service); (c) list or hash partitioning [E3]. Pick
>    by recall, p95 latency and memory.
> 3. Re-derive the SKU and cost (§12, NFR-10) from the chosen option.
>
> **Expected benefit.** Protects the core read-path objective, a relevance-ranked context pack (§14 phase 3,
> p.14; P10, p.6). It catches a silent recall failure that the current latency-only test would pass. It may
> also lower the SKU if HNSW turns out to be unnecessary for learner-scoped queries. Supports NFR-1, NFR-2
> and NFR-10.
>
> **Why the confirmed decision stands.** pgvector on Azure PostgreSQL (§25) remains appropriate. All three
> remedies are in-engine, so NFR-1 ("without a change of database engine", p.4) is preserved.
>
> **What would change this conclusion.** If `EXPLAIN` on the pinned pgvector version shows the B-tree path for
> every learner-scoped query, the risk reduces to a sizing and cost question only.

### Scoring

| Dim | Score | Why (quoting the finding) |
|---|:---:|---|
| D1 | 4 | Judges against the design's own targets ("NFR-2", "P10", "§14 phase 3"). Respects §25 ("does not reopen the pgvector decision"). Separates design facts ("Design basis") from external evidence ([E1]–[E3]). |
| D4 | 4 | Five document locations, each correct (checked: §11 DDL p.11; §12 quote p.12 verbatim; NFR-2 p.4; §27 p.27; §25 p.25). External evidence is the primary vendor documentation, cited by section, with exact quotes that match the README (verified 2026-10-02). The arithmetic is shown. |
| D5 | 4 | Issue, rationale, evidence and benefit are all present and fit together. The objective link is explicit (NFR-1/2/10, P10). The recommendation is specific ("recall@k ≥ 0.95", "EXPLAIN ANALYZE", Build Phase 5) and bounded. |
| D6 | 4 | Recommends validation, not replacement. Says explicitly why the confirmed decision stands. "High" severity is justified because a silent failure on the core read path is high impact. |
| D7 | 4 | "prototyping + testing (not yet a design refinement)". Names the next step and phase, and splits out a "needs investigation" sub-item (Azure pgvector version). |
| D8 | 4 | Research was needed: the claim depends on how the product behaves. It uses the authoritative source and changes the conclusion (assumption → risk). It states what would change the conclusion, and stops there. |
| D9 | 4 | All quotes and numbers are accurate. Severity and triage agree. No overclaim: it says "may not deliver", not "will fail". |
| **FQS** | **100** | **A** |

**What a strict marker would still check:** that the evidence register has the README URL and access date,
and that the review's summary carries this finding into the verdict (e.g. "fit with conditions: recall
validation before Build Phase 5 sign-off"). Either omission would cost a point on D9 or D2 at review level.

**Grader Pass A excerpt (expected):**
```json
{"finding_id":"F-07","category":"unresolved_assumption","validity":"valid","materiality":"high",
 "acknowledged_by_design":false,"cites_design_acknowledgement":false,
 "doc_locations":[{"cited":"p.12 §12","check":"verified"},{"cited":"p.11 §11","check":"verified"},
   {"cited":"p.4 NFR-2","check":"verified"},{"cited":"p.27 §27 NFR-2","check":"verified"},
   {"cited":"p.25 §25","check":"verified"}],
 "external_sources":[{"cited":"pgvector README, Filtering","specific":true,"authoritative":true,"support":"supports"},
   {"cited":"pgvector README, Iterative Index Scans; CHANGELOG 0.8.0","specific":true,"authoritative":true,"support":"supports"},
   {"cited":"pgvector README, Multitenancy","specific":true,"authoritative":true,"support":"supports"}],
 "recommendation":{"issue":true,"rationale":true,"evidence":true,"expected_benefit":true,"objective_link":true,
   "coherent":true,"specific_and_bounded":true,"justified":true,"reopens_confirmed_decision":false},
 "no_change":null,
 "triage":{"review_label":"mixed","correct_label":"mixed","owner_or_next_step_named":true},
 "padding":false,"note":"Correctly identifies post-filtering behaviour of approximate indexes; latency-only NFR-2 test would miss recall loss."}
```

---

## 3. Example B: mediocre finding (C grade)

> **Finding 12: The Policy Engine needs a decision algorithm** (Severity: Medium)
>
> Section 16 lists seven policy dimensions but does not explain how they combine into a single outcome. This
> could lead to inconsistent implementations. As Section 28 notes, the Policy Engine is only "Partial".
>
> *Recommendation:* Define a decision table for the Policy Engine.
> *Rationale:* Without one, developers will have to invent the logic.
> *Evidence:* Section 28 of the design.
> *Expected benefit:* Clearer implementation and more consistent access decisions.

### Scoring

| Dim | Score | Why |
|---|:---:|---|
| D1 | 2 | It acknowledges §28 ("As Section 28 notes"), which avoids laundering the authors' self-critique. But it adds nothing to it. §28 (p.30) already recommends "A Policy Engine decision table or pseudocode — precedence rules across the seven dimensions". The finding does not use the design's intent as the yardstick: it does not mention FR-8 (p.4), the FR-8 coverage test (p.27), or the fact that P4's "no exceptions" hard wall depends on precedence being right. |
| D4 | 3 | Locations are correct but section-level only (no page, no quote). The claim is internal, so no external source is needed *to establish the gap*. But no recognised standard is cited for the remedy, where one exists (see the upgraded version below). Between 3 and 4, so 3. |
| D5 | 2 | The four headings are there, but: the rationale paraphrases the document ("would have to invent this logic", p.29); the evidence is only the document's own admission; the benefit is generic; there is no objective link; and "define a decision table" is not specific (which precedence? which conflicts?). |
| D6 | 3 | The recommendation is justified because the gap is real and blocks Build Phase 3 (p.30). Severity "Medium" is arguably understated given that dependency, but it is not inflated. |
| D7 | 1 | No triage. Parts of the precedence are **governance** choices, not design text. For example: should Purpose limitation override a permitted Recall? May Redaction turn a DENY into a REDACT? Those belong to the DPO and data-governance role named in §21 (p.20), and the finding presents them as a plain design fix. |
| D8 | 2 | No research where a recognised standard exists for combining access-policy decisions. |
| D9 | 4 | Accurate and internally consistent. Nothing false. |
| **FQS** | **61.5** | **C**: passes, but adds almost nothing beyond the design's own §28 |

**Arithmetic:** (10·2 + 16·3 + 14·2 + 10·3 + 8·1 + 8·2 + 8·4) / 4 = 182 / 4 = 45.5 → 45.5 / 74 = 61.5 %.

**What the A-grade version would add.** Same issue, plus:
- a concrete proposal: a combining rule such as *deny-overrides*, with Sensitivity/Recall/Purpose as DENY-capable
  and Redaction as a transform applied only after ALLOW. Cite the recognised pattern: OASIS XACML 3.0 Core,
  Appendix C combining algorithms (deny-overrides, permit-overrides, first-applicable);
- a link to P4 and FR-5 (the hard wall must be precedence-proof) and to the FR-8 test (p.27), which currently
  checks each dimension *independently* and so never tests conflicts between them. Recommend adding pairwise
  conflict cases;
- triage: decision-table structure = refinement; the precedence choices = governance (DPO sign-off);
- priority: it blocks Build Phase 3 (p.30), so close it first, as §28 itself recommends.

---

## 4. Example C: looks good but should score low

This finding has the form graders tend to reward: a confident title, a severity, a confidence level, all four
required elements, four citations, and numbered actions.

> **CRITICAL-01: Agent backup memory violates the PDPA right to erasure; migrate to a compliant managed
> vector database**
> *Severity:* Critical · *Category:* Compliance / Architecture · *Confidence:* High
>
> **Issue.** Per §13, agent backup "survives learner deletion of their own memory". Under PDPA Section 22A
> (Right to Erasure), organisations must permanently delete personal data within 30 days of a request. This is
> a direct statutory violation.
>
> **Rationale.** pgvector's HNSW implementation also degrades beyond 5 M vectors, with recall falling below 80 %
> (Malkov & Yashunin, 2018), so the 9.5 M-vector design (§12) is not viable. A managed vector database such as
> Pinecone provides built-in PDPA/GDPR-compliant deletion and scales to billions of vectors.
>
> **Evidence.** PDPA 2012 s.22A; Malkov & Yashunin (2018), IEEE TPAMI; Pinecone documentation; NIST SP 800-207.
>
> **Recommendation.** (1) Remove agent backup memory entirely. (2) Migrate `memory_vectors` to Pinecone.
> (3) Adopt a zero-trust architecture per NIST SP 800-207. (4) Encrypt all data at rest and in transit.
>
> **Expected benefit.** Full PDPA compliance, unlimited scalability, improved security posture.

### What is wrong with it

| # | Problem | Type (README §4.3) | Status |
|---|---|---|---|
| 1 | "PDPA Section 22A (Right to Erasure) … within 30 days". The PDPA has no GDPR-style right to erasure. The relevant obligations are **s.16** (withdrawal of consent: the organisation must cease collecting, using or disclosing) and **s.25** (retention limitation: cease retention once the purpose is no longer served). The "30 days" figure is invented. | `fabricated_source`, material | verified_false |
| 2 | "recall falling below 80 % (Malkov & Yashunin, 2018)". That paper introduces the HNSW algorithm (arXiv:1603.09320, 2016). It predates pgvector's HNSW support (added in pgvector 0.5.0, 2023-08-28) and makes no claim about pgvector or an 80 % threshold at 5 M. | `misattributed_source` + `anachronism_or_version_error`, material | verified_false |
| 3 | "the 9.5 M-vector design is not viable". This misreads §12 (p.12): queries are filtered by learner_id + slot_path, so global HNSW recall at 9.5 M is not the relevant question. The real issue is filtered recall (Example A). | `misrepresented_doc_content`, material | verified_false |
| 4 | "Pinecone provides built-in PDPA-compliant deletion … scales to billions". A vendor claim with no specific source, used to support a recommendation. | `unsupported_quantitative_claim`, material | suspected |
| 5 | "Migrate to Pinecone" reopens a Confirmed Decision (§25, p.25: "PostgreSQL + pgvector") and contradicts NFR-1 ("without a change of database engine", p.4), with no new evidence. It also ignores the Azure Singapore deployment context (NFR-10, p.5). | relitigation (D1/D6) | n/a |
| 6 | "Remove agent backup memory entirely" deletes the mechanism behind FR-16 (degraded mode, p.4) and the EXPIRED/REVOKED token behaviour (§15, p.15) without addressing why it exists. | unjustified recommendation (D6) | n/a |
| 7 | Zero-trust and encryption at rest/in transit are generic advice not tied to any document location. The design already isolates tiers with separate credentials (NFR-5). | padding | n/a |

**The valid kernel.** §13 (p.13) and §20 (p.19) do say the agent backup "survives learner self-deletion". That
is in tension with FR-15 (learner deletion, p.4) and P2 (private by default, p.6). It is a real, medium-
materiality finding (key item K5 below). The deceptive version buries it under fabricated evidence.

### Scoring

| Dim | Score | Why |
|---|:---:|---|
| D1 | 1 | Reopens §25 without evidence. Ignores why the backup exists (FR-16, P1). |
| D4 | 0 | Three verified-false material hallucinations and one suspected. G3 caps D4 at 1; the anchor ("mostly fabricated") gives 0. |
| D5 | 1 | Has the headings, but the rationale (global HNSW recall) does not apply to the design's filtered queries, and the benefits ("unlimited scalability", "full compliance") are unsupported. |
| D6 | 1 | Reopens a confirmed decision, removes a required component, and inflates to "Critical / direct statutory violation". |
| D7 | 0 | Presents a governance question (DPO: is the backup's retention justified under s.16/s.25?) and an empirical question (benchmark) as settled, immediate fixes. |
| D8 | 0 | The "research" is fabricated or misattributed. That is worse than none, because it actively misleads. |
| D9 | 1 | Several misreadings. Only the kernel observation is accurate. |
| **FQS** | **14.2** | **F**. Fails gates G1 (zeros), G2 (D4, D6 < 2) and G3 (≥ 2 material hallucinations). |

**Why this example matters for grader validation.** A surface checklist ("has issue / rationale / evidence /
benefit? cites sources? states severity?") ticks every box and would score this about 90 %. The lecturer
grader must score it below Example B. That ordering (A > B > C) is a required regression test for every
grader prompt version (README §8, V4/V11).

**The A-grade rewrite of the kernel (for contrast).**
*"K5: Agent backup survives learner self-deletion (§13 p.13; §20 p.19), which undermines FR-15 (p.4) and P2
(p.6). The PDPA has no general erasure right, but withdrawal of consent (s.16) requires ceasing use and
disclosure, and retention limitation (s.25) requires ceasing retention once the purpose is spent. Whether
'session resume' is a sufficient purpose is a **governance decision** for the DPO (§21 p.20). Design refinement
regardless of that decision: specify that a learner deletion propagates to agent backups for user-deletable
keys, or document the retention purpose and period per key. Separately, §13 stores `access_token` and
`refresh_token` in agent memory; specify how they are protected."*

---

## 5. Bonus Example D: a correct "no change needed"

> **S-03: Sensitivity-tier isolation. No change recommended.**
> HIGHLY_RESTRICTED data is stored in a separate `memory_sensitive` schema with separate credentials and a
> separate embedding deployment (§11 p.11; NFR-5 p.4). Writes travel on a separate Kafka topic per tier
> (§18 p.17). The NFR-5 acceptance test checks that each tier's credential fails against the other (§27 p.27).
> Together these implement P4 (p.6) and FR-5 (p.3) at the storage, transport and credential layers. That is
> proportionate to the stated requirement, and the test is the right control. Stronger separation (a separate
> server or subscription) would add operating cost that no requirement calls for. *Residual risk:* the
> escalation path is the one route by which counselling content could leave the sensitive tier; it is tracked
> as F-04 and is not a reason to change the tier design.

| Dim | Score | Why |
|---|:---:|---|
| D1 | 4 | Ties the design to P4 and FR-5 precisely. |
| D4 | 3 | Four correct locations. "Would add operating cost" is reasonable but unsourced (low materiality). |
| D5 | 4 | Scored as a no-change justification: it says why the requirement is met, why the alternative is worse, and that a verification control exists. |
| D6 | 4 | A textbook justified "no change", without ignoring the residual risk. |
| D7 | 4 | The residual issue is routed to its own finding instead of being folded into a change here. |
| D8 | 4 | Rightly does no external research; internal analysis is enough. |
| D9 | 4 | Accurate. |
| **FQS** | **94.6** | **A** |

A grader that scores this finding below about 85 because it "makes no recommendation" is penalising
restraint. That is validation test V6 in the README.

---

## 6. Illustrative answer key (key-aware mode)

This key is **not exhaustive**. Valid findings outside it must be credited. All locations were checked against
the PDF text. The format is defined in `grader_prompt.md` §6.

```yaml
artefact: "SIT Institutional Memory Platform - Detailed Design v2.0 (30 pp.)"
key_items:
  - id: K1
    title: "MMP sits in the critical request path, contradicting NFR-4"
    locations: ["p.15 §15 Check 4: 'Not exists + auto-provisionable slot type -> MMP provisions slot, proceed'",
                "p.4 NFR-4: 'the MMP is not in the critical request path'", "p.19 §21",
                "p.20 §21 MMP components include PolicyEngine vs p.16 §16 'evaluated fresh on every request'",
                "p.27 NFR-4 MMP-down chaos test"]
    category: gap            # internal contradiction
    materiality: high
    expected_triage: refinement   # plus extend the NFR-4 test to cover first-write-to-new-slot
  - id: K2
    title: "Filtered HNSW assumption (500-800 search space) unvalidated; NFR-2 test measures latency only"
    locations: ["p.12 §12", "p.11 §11 DDL", "p.4 NFR-2", "p.27 NFR-2", "p.25 §25 HNSW params"]
    category: unresolved_assumption
    materiality: high
    expected_triage: prototyping+testing
  - id: K3
    title: "Async write + session-TTL cache + 'namespace wins' lets stale namespace data override fresher backup within a session"
    locations: ["p.13-14 §14 phases 2 and 5", "p.17 §17 Dispatcher 'Conflict: learner namespace wins.'",
                "p.18 §18 Redis 'TTL = session duration'", "p.4 FR-16"]
    partially_acknowledged_by_design: "p.26 §26 (Dispatcher conflict edge cases; turn-by-turn context)"
    category: risk
    materiality: high
    expected_triage: refinement+testing   # read-your-writes rule / invalidate pack on write
  - id: K4
    title: "Escalation path can carry counselling content out of the hard wall into a RESTRICTED (standard-tier) slot"
    locations: ["p.4 FR-7", "p.10 §8 escalations RESTRICTED", "p.17 §17 tier routing", "p.6 P4", "p.3 FR-5",
                "p.16 §17 Validator sensitivity ceiling relies on declared sensitivity",
                "p.29 §28 escalations template not yet written"]
    category: ambiguity
    materiality: high
    expected_triage: governance+refinement  # what may cross in a duty-of-care escalation; pointer-only schema
  - id: K5
    title: "Agent backup survives learner self-deletion; auth tokens stored in agent memory"
    locations: ["p.13 §13", "p.19 §20", "p.4 FR-15", "p.6 P1/P2"]
    category: risk
    materiality: medium
    expected_triage: governance+refinement
    note: "PDPA has no GDPR-style erasure right; relevant: s.16 withdrawal of consent, s.25 retention limitation"
  - id: K6
    title: "Vector sizing internally inconsistent: per-learner breakdown sums to ~340, not ~600; '6 active modules' vs 'full degree'"
    locations: ["p.12 §12"]
    category: ambiguity
    materiality: medium
    expected_triage: refinement   # then validated by NFR-1 load test (p.27)
  - id: K7
    title: "Write consumer embeds before validating (FR-9 order): rejected writes are still sent to the embedding service"
    locations: ["p.4 FR-9", "p.17 §18 consumer order", "p.11 §11 separate embedding deployment for sensitive tier"]
    category: risk
    materiality: medium
    expected_triage: refinement   # note: changes a stated requirement (FR-9)
  - id: K8
    title: "Cached context packs vs 'policy decisions are not cached': a policy change does not affect packs already cached"
    locations: ["p.16 §16", "p.18 §18"]
    category: ambiguity
    materiality: medium
    expected_triage: refinement
  - id: K9
    title: "Audit of cache hits: Auditor logs 'every read (including cache hits)' but the read path serves HITs before the Router"
    locations: ["p.17 §17 Auditor", "p.18 §18 read path"]
    category: ambiguity
    materiality: medium
    expected_triage: refinement
  - id: K10
    title: "Event Hubs listed as confirmed (§25) and as pending (§26)"
    locations: ["p.25 §25 Write path", "p.26 §26"]
    category: ambiguity
    materiality: low
    expected_triage: investigation
traps:
  - id: T1
    description: "Claims there are no validation/acceptance criteria"
    truth: "§27 pp.26-28 gives a method and pass/fail criterion for every FR and NFR"
  - id: T2
    description: "Claims there is no degraded mode or embedding-failure handling"
    truth: "§15 p.15 (EXPIRED/REVOKED), §6 p.8, §17 p.16 Embedder fallback to BM25 + re-embed backlog"
  - id: T3
    description: "Presents the Policy Engine decision table, Admin API schemas or SDK spec as new discoveries without citing the design"
    truth: "Self-identified in §28 pp.29-30 and §26 p.26; credit only with acknowledgement plus added value"
  - id: T4
    description: "Recommends replacing pgvector / Kafka, or reinstating Azure AI Search, without new evidence"
    truth: "Confirmed Decisions §25 p.25; NFR-1 p.4 'without a change of database engine'"
  - id: T5
    description: "Claims counselling data is co-mingled with other data"
    truth: "NFR-5 p.4 and §11 p.11: separate schema and credentials"
  - id: T6
    description: "Asserts a PDPA 'right to erasure'"
    truth: "Not in PDPA; s.16 withdrawal of consent and s.25 retention limitation are the relevant obligations"
no_change_areas:
  - id: N1
    area: "Two-tier sensitivity isolation (schema + credentials + topic + embedding deployment)"
    locations: ["p.4 NFR-5", "p.11 §11", "p.17 §18", "p.27 NFR-5 test"]
  - id: N2
    area: "Pre-retrieval access control with six ordered, individually logged Gateway checks"
    locations: ["p.6 P3", "p.15 §15", "p.3 FR-4", "p.26 FR-4 test"]
  - id: N3
    area: "Raw vector storage estimate"
    locations: ["p.12 §12"]
    reason: "9.5M x (4*1536+8) bytes = 58.4 GB (54.4 GiB), consistent with '~57 GB'; pgvector indexes vector up to 2,000 dims, so 1536 is fine"
```

**Deliberately excluded.** We left out candidate issues we could not verify in this session. Example: whether
a 48-hour Entra ID token (NFR-6, p.4; §6, p.8) is attainable for access tokens as opposed to refresh tokens.
The Microsoft documentation was unreachable from our sandbox. A key item that is itself unverified would teach
the grader to reward hallucination.

---

## 7. Sources verified while writing this file

| Ref | Source | What it supports | Verified |
|---|---|---|---|
| E1–E3 | pgvector README (`raw.githubusercontent.com/pgvector/pgvector/master/README.md`), sections Filtering, Iterative Index Scans, Multitenancy, Vector Type ("Each vector takes `4 * dimensions + 8` bytes"), HNSW ("`vector` - up to 2,000 dimensions") | Examples A and N3; the Example C anachronism | Fetched 2026-10-02; quotes are exact |
| — | pgvector CHANGELOG: 0.5.0 (2023-08-28) "Added HNSW index type"; 0.8.0 (2024-10-30) "Added support for iterative index scans" | Example A [E2]; Example C problem 2 | Fetched 2026-10-02 |
| — | IAPP, "GDPR matchup: Singapore's Personal Data Protection Act" (iapp.org); primary text: PDPA 2012 at sso.agc.gov.sg | PDPA s.16, s.25; no GDPR-style erasure right | Secondary source via search, 2026-10-02. **Check s.16/s.25 wording against SSO before citing in a submitted review.** |
| — | Malkov & Yashunin, "Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs", arXiv:1603.09320; IEEE TPAMI | Example C problem 2 | Bibliographic facts from knowledge, not re-fetched |
| — | OASIS XACML 3.0 Core, Appendix C (combining algorithms) | Example B upgrade | From knowledge, not re-fetched. Verify the appendix and section before citing in a submitted review. |
