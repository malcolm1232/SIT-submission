# Metric definitions, matching procedure and pseudo-code

Companion to [`README.md`](README.md); reference numbers `[n]` point to README §12.
Anything marked **PROPOSED DEFAULT** is our choice, to be re-tuned on S-dev only. Anything marked **UNVERIFIED** could not be checked against a source.

---

## 0. Notation

| Symbol | Meaning |
|---|---|
| d ∈ D | evaluated documents; runs j = 1..k per (doc, condition) |
| G_d | sealed key flaws of doc d (planted plus natural flaws from the base audit) |
| S_d | sound units of d (sections or decisions marked fit-for-purpose); B_d ⊆ S_d are bait units |
| A_d | approved (confirmed) decisions in d |
| F_dj | atomic findings the agent emitted in run j on doc d, in the agent's priority order |
| Rec_dj | recommendations in run j (each linked to ≥ 1 finding) |
| s(g) ∈ {critical, high, medium, low} | gold severity, the `severities` enum of `spec/taxonomy.yaml` (`Severity` in both spec schemas); w(s) its weight. Legacy key labels are mapped by `legacy_mappings.severity`: synthetic major → high, minor → low (sensitivity variant minor → medium); blind-A capitalised labels → lower case. The key stores the mapped value in `severity` and the verbatim label in `severity_source` *(reconciled 2026-10-02, spec/README.md §3 C6)* |
| w | Geometric weights {critical: 8, high: 4, medium: 2, low: 1} = `severities[].weight_primary`; sensitivity variant linear {4, 3, 2, 1} = `severities[].weight_sensitivity` (`spec/taxonomy.yaml`; adopted, no longer only a proposed default). Report SWR under both weight schemes and both legacy mappings (L14) |
| M_dj ⊆ F_dj × G_d | one-to-one match set produced by §2 |
| cat(g), cat̂(f) | gold category, agent-assigned category |
| c_f ∈ [0,1] | agent-stated confidence for finding f |

---

## 1. Agent output contract (needed to score anything)

The agent MUST emit, in addition to its human-readable review, a machine-readable JSON with:

```json
{
  "doc_verdict": {"fit_for_purpose": "yes|partly|no", "rationale": "...", "confidence": 0.0},
  "findings": [{
    "id": "F3", "rank": 1, "category": "GAP", "severity": "critical",
    "claim": "one-sentence statement of the issue",
    "location": [{"section": "16", "req_id": "FR-8", "quote": "verbatim span from the doc"}],
    "evidence": [{"source_type": "DOC|EXTERNAL", "ref": "section id | URL | DOI", "quote_or_passage": "...", "supports": "what it shows"}],
    "confidence": 0.8,
    "kind": "risk|gap|ambiguity|assumption|inconsistency|incorrect_claim|validation_need|strength"
  }],
  "recommendations": [{
    "id": "R1", "finding_ids": ["F3"], "issue": "...", "rationale": "...",
    "evidence": [{"source_type": "...", "ref": "...", "quote_or_passage": "..."}],
    "expected_benefit": "...", "objective_refs": ["FR-8", "P3"],
    "action_type": "design_refinement|needs_investigation|needs_prototype|needs_governance_decision"
  }],
  "section_verdicts": [{"section": "11", "verdict": "sound|issues", "justification": "...", "evidence": [...]}],
  "limitations": ["research that could not be completed and why"],
  "stop_reason": "sufficient_evidence|budget|tool_failure|other"
}
```
Strengths (`kind = strength`) are excluded from defect matching. They are scored only by the rubric grader. `action_type` reflects lab §3.2: the agent must tell design refinements apart from issues that need investigation, prototyping, testing or a governance decision.

> **Superseded (reconciliation 2026-10-02):** the output contract above is replaced by **`spec/finding.schema.json`** (`Finding`, `#/$defs/Review`); the field-by-field mapping is `spec/README.md` §2.3. In short: `category` codes and `kind` → spec `kind` + `category` (two axes, `spec/taxonomy.yaml`); `claim` → `statement`; `location[]` → `doc_anchors[]` (1-3 anchors, each `{doc_id, section_ref, requirement_ids, quote ≥ 8 tokens, page}`); `evidence[].ref` → `evidence[].evidence_id` (evidence-ledger IDs only; the renderer writes URLs) with `source_type: doc | external | inference`; `action_type` → `disposition` (`refinement_now | needs_investigation | needs_prototyping | needs_testing | governance_decision | no_change`, so **testing** is included) plus `secondary_dispositions[]`; `doc_verdict.fit_for_purpose yes/partly/no` → `verdict.label fit / fit_with_conditions / not_fit`; `section_verdicts` → `sound_areas[]`; separate `recommendations[]` → one `recommendation` embedded in its finding; `stop_reason` → `{code, group}` from the union enum (`sufficient_evidence, no_marginal_gain, budget_tool_calls, budget_tokens, deadline, tool_failure, error`; groups decision / cap / error). Audit C7-C13.

---

## 2. Matching findings to ground-truth flaws

### 2.1 Principles

> **Superseded (reconciliation 2026-10-02):** this section is the **only** source of recall (the grader's key-aware Pass B alignment is diagnostic and is never reported as recall; `spec/README.md` §3 C4). It is the one matching rule for every item; the per-item rules in the eval READMEs are superseded (C5). Rule 2's "states the core insight" is operationalised per flaw by the answer key's **`credit.mode`** (`spec/taxonomy.yaml` `credit_modes`): `substance`, the finding states the flaw's `core_insight` in substance at a compatible location (credit items are guidance only); `all_of`, every credit item with `role: required` is stated; `any_of`, at least `credit.min_required` of the required items are stated. `credit.mode` does not create a second rule; it only says how the core insight is checked (`spec/README.md` §3 C5, deviation D4). Location compatibility uses the finding's `doc_anchors[]` (1-3 per finding, which also caps location spraying, G3) against the flaw's `location`. Score labels are `spec/taxonomy.yaml` `match_scores` (MATCH / PARTIAL / RELATED / UNRELATED) and adjudication labels are `adjudication_classes`. A finding that matches a key's `still_valid_observations` entry is pre-adjudicated VALID_UNPLANTED (C26).

1. **One-to-one.** A gold flaw can be credited at most once per run, and a finding can match at most one flaw. Extra findings for the same flaw are **duplicates**.
2. **Core-insight rule.** A finding matches a flaw only if it states the flaw's `core_insight` (e.g. "the 7 policy dimensions have no precedence rule, so conflicting outcomes are undefined"), not merely its topic ("the policy engine needs more detail").
3. **Location compatibility.** The finding's location must overlap the flaw's anchor section(s) or requirement id(s), or a section that explicitly cross-references them. A finding with no location can at most be PARTIAL.
4. **Matching ignores category labels.** Category agreement is scored separately (§3.3), so a correctly described flaw with the wrong label still counts as detected.
5. **The matcher is blind to the condition and to the agent's identity.** It never sees which ablation produced the output. Findings are shuffled before scoring.
6. **Thresholds are tuned on S-dev only** and frozen in `prereg.yaml`.

### 2.2 Score scale (per finding–flaw pair)
| Score | Label | Definition |
|---|---|---|
| 3 | MATCH | Same underlying defect; core insight explicitly present; location compatible |
| 2 | PARTIAL | Same defect, but the core insight is only partly stated, **or** the location is missing or vague |
| 1 | RELATED | Same area or topic, but a different or generic defect |
| 0 | UNRELATED | No relation |

- **Strict matching:** pairs with score = 3 are eligible. **This is the primary setting.**
- **Lenient matching:** pairs with score ≥ 2 are eligible. Report it as secondary (loophole L33).

### 2.3 Procedure
1. **Candidate generation** (recall-oriented; keeps cost bounded):
   a. Location overlap: every finding whose section or req ids intersect the flaw anchor.
   b. Embedding similarity between `claim` and `description + core_insight`: top-3 findings per flaw, plus every pair with cosine ≥ τ_pre. Calibrate τ_pre on S-dev so that **≥ 0.98 of human-confirmed matches survive the prefilter** (PROPOSED DEFAULT; any embedding model, recorded in the manifest).
   c. Listwise LLM shortlist: one call per flaw that sees all findings and returns up to 3 candidate ids or "none".
   The candidate set is the union of a, b and c. Pairs outside it score 0.
2. **Pairwise scoring.** An LLM matcher (from a model family **different** from the agent's) scores each candidate pair on the 0–3 scale. *(Superseded, reconciliation 2026-10-02: the matcher's model is set by `docs/DECISIONS.md` ADR-003, Pending; branch B uses a local open-weight model validated against the user's 150 labelled S-dev pairs, else Claude in batch disclosed as same-family. The same applies to the adjudicator, G3 judge and citation judge. Audit C3.)* It returns JSON `{score, core_insight_present, location_ok, rationale}`. Use 3 samples, or a deterministic call plus a re-ask with the two texts in swapped order, and take the **median** score.
3. **Assignment.** Solve a maximum-weight bipartite assignment (Hungarian algorithm, e.g. `scipy.optimize.linear_sum_assignment`) on weight = score + ε·w(s(g)), with ε = 0.01 to break ties toward more severe flaws. Ineligible pairs get weight 0. Drop assigned pairs below the eligibility threshold.
4. **Adjudication of unmatched findings.** Each unmatched finding gets exactly one class:

| Class | Meaning | Counts as correct for precision? |
|---|---|---|
| DUPLICATE | Restates a finding already matched (score ≥ 2 to an already-assigned flaw, or semantically the same as another finding) | strict: no; adjudicated: no |
| VALID_UNPLANTED | Correct, specific, doc-grounded issue missing from the key | strict: no; **adjudicated: yes** |
| HALLUCINATED | Central premise about the doc is false (fabricated quote or section, false-absence claim, misreading) | no |
| NON_SPECIFIC | Generic advice that would apply to any design ("add monitoring") | no |
| INVALID_OPINION | Grounded, but the claimed problem is technically wrong or criticises a justified choice | no |
| OUT_OF_SCOPE | About something the doc explicitly puts out of scope | no |

   An LLM adjudicator (different family) makes the first pass. A human then reviews **100% of VALID_UNPLANTED and HALLUCINATED** labels (they move precision and HFR the most) and a random 20% of the rest. Disagreements go to a second human, and the majority decides.
5. **Key maintenance.** A VALID_UNPLANTED finding that the humans confirm is a key defect. Add it to a **pooled supplementary key** G⁺_d, the union over **all** conditions in the same evaluation round (TREC-style pooling, standard IR practice; citation not verified this session). The sealed key G_d is never edited after a held-out or blind run. Recall is reported against G_d (primary) and G_d ∪ G⁺_d (secondary).
6. **Matcher validation** (gate before use): at least 150 candidate pairs from S-dev, each labelled by 2 humans. Report human–human κ and matcher-vs-consensus κ on the binary decision MATCH vs not (strict). The gate is κ ≥ 0.80 (PROPOSED DEFAULT, following Krippendorff's reliability threshold [30]). The B-gen generic-checklist baseline must also score strict recall ≤ 0.05.

---

## 3. Detection metrics

For one run (d, j): let TP = |M_dj| (strict), N = |F_dj \ strengths|, V = #VALID_UNPLANTED, G = |G_d|.

| Metric | Formula | Notes |
|---|---|---|
| Recall | R = TP / G | Undefined if G = 0 (fully sound doc). Excluded from recall, scored by CDR instead |
| Precision, strict | P_s = TP / N | Undefined if N = 0. Excluded from macro-P; the number of zero-finding runs is reported |
| Precision, adjudicated | P_a = (TP + V) / N | Primary precision |
| F1 | F1_x = 2·P_x·R / (P_x + R), x ∈ {s, a} | 0 if P_x + R = 0 |
| Pooled recall (secondary) | R⁺ = (TP + TP⁺) / (G + |G⁺_d|) | TP⁺ = matches to the pooled supplementary key |
| Duplication rate | #DUPLICATE / N | |
| Non-specific rate | #NON_SPECIFIC / N | Shotgun indicator (L16) |

### 3.1 Per category

> **Superseded (reconciliation 2026-10-02):** "category" here is the `category` axis of `spec/taxonomy.yaml` (defect mechanism: 9 codes plus `other`), which drives the per-category recall table and the taxonomy-dependence check; the lab §2.3 `kind` axis drives grader D3. Audit C7.

- Per-category **recall** uses the **gold** category: R_c = |{g ∈ M : cat(g) = c}| / |{g ∈ G : cat(g) = c}|.
- Per-category **precision** uses the **agent's** category: P_c = |{f matched or VALID_UNPLANTED : cat̂(f) = c}| / |{f : cat̂(f) = c}|.
- F1_c = harmonic mean of P_c and R_c.
- **Typed (strict-category) variant:** a match counts for category c only if cat̂(f) = cat(g).
- **Category-label accuracy** on matched pairs, plus the full confusion matrix.
- Report **micro** values (pooled counts across docs) and **macro** values (mean of per-doc values, then mean over categories). Pre-register which one is primary. **PROPOSED DEFAULT: macro-over-docs is primary**, because the doc is the unit of the lab task.

### 3.2 Severity-weighted recall
SWR_dj = Σ_{g ∈ G_d matched} w(s(g)) / Σ_{g ∈ G_d} w(s(g))

**Critical recall** = matched criticals / all criticals. Report SWR under both weight schemes (L14).

### 3.3 Severity agreement
On matched pairs, the quadratic-weighted κ between the agent's severity and the gold severity (§11 formula).

---

## 4. Ranking quality (are critical flaws surfaced first?)

The agent's findings are ordered by `rank` (ties broken by output order). For position i, define the gain

  gain_i = w(s(g)) if finding i is matched to g (first, non-duplicate occurrence), else 0.

- **DCG@k** = Σ_{i=1..k} gain_i / log₂(i + 1)
- **IDCG@k** is the same sum over the gold severities sorted in descending order.
- **nDCG@k** = DCG@k / IDCG@k [43]. Use **k = |G_d|** (primary) and k = 5. Linear gain is used because w is already geometric.
- **MRR_crit** = 1 / rank of the first finding matched to a critical flaw (0 if none). Only defined for docs that have a critical flaw.
- **Critical-in-top-3** = 1 if every critical flaw of d (or, when there are more than 3, the first 3) is matched within ranks 1..3.
- nDCG does not punish false positives directly, except by pushing true positives down. Always read it next to precision.

---

## 5. Grounding: hallucinated findings and citation faithfulness

### 5.1 Grounding checks (run on **every** finding, matched or not)
- **G1 Quote existence.** *(Superseded, reconciliation 2026-10-02: "the doc text" is the canonical page-marked text `doc.pages.txt` produced once by the pinned pdfplumber extractor and read by every verifier; G1 and G2 share one function with the agent's verify stage; quotes must be ≥ 8 tokens and match inside the cited section ±1 page. `docs/DECISIONS.md` ADR-006, ADR-007; audit C14, G1-G3.)* Normalise both the quote and the doc text (Unicode NFKC, lowercase, collapse whitespace, undo PDF hyphenation and ligatures). Pass if the best token-level partial-match ratio is ≥ θ_q. **PROPOSED DEFAULT θ_q = 0.90**, calibrated on S-dev against human judgements because PDF extraction adds noise. This step is deterministic.
- **G2 Location validity.** The cited section or req id exists in the doc, and the quote lies in that location or ±1 adjacent section.
- **G3 Premise faithfulness.** An LLM judge (different family) gets the claim and the cited location text. It labels the claim's premise about the doc SUPPORTED, CONTRADICTED or NOT_FOUND. For **absence claims** ("the doc never defines X"), the judge gets retrieval over the whole doc for X and its synonyms. If X is present, the claim is a **false-absence** hallucination. This is the most common grounding error for document reviewers (**UNVERIFIED** generalisation; it should be measured).

A finding is **HALLUCINATED** if its central premise fails G3 (CONTRADICTED, or NOT_FOUND for a positive claim), **or** if every one of its quotes fails G1.

| Metric | Formula |
|---|---|
| Hallucinated-finding rate | HFR = #HALLUCINATED / N |
| Quote fabrication rate | #quotes failing G1 / #quotes |
| False-absence rate | #absence claims refuted / #absence claims |

A matched (TP) finding can still contain a fabricated quote. It stays a TP for detection and counts in the quote fabrication rate.

### 5.2 Citation faithfulness
Unit = a (claim, citation) pair, taken from finding evidence and recommendation evidence. External factual assertions inside the rationale are split into atomic claims by an LLM claim splitter (an approach in the spirit of ALCE [10] and AIS [40]).

**Step 1: existence and provenance (deterministic).**
- DOC citations: G1 + G2.
- EXTERNAL citations: *(Superseded, reconciliation 2026-10-02: the model cites **evidence-ledger IDs** only (`evidence_id`); `url_or_citation` and `retrieved_at` are read-only and filled by the renderer, and the ledger records `read_before_cite`. The existence checks below are kept to catch renderer bugs and free-text URLs. `spec/README.md` §3 C11.)* (i) is the URL or DOI in the run's **fetched-content snapshot store**? If yes, label **READ**. (ii) If not, resolve it live: DOI via doi.org or Crossref, title via OpenAlex or Crossref with fuzzy title match ≥ 0.9, URL with HTTP 200. If it resolves, label **EXISTS_NOT_READ** (cited without being read in this run); if not, label **FABRICATED**. Record **UNREACHABLE** separately for transient failures.

**Step 2: support (judged against the snapshot the agent actually saw).** An entailment judge (different family) labels each pair FULL, PARTIAL or NONE: "According to the source passage, is the claim true?" (AIS framing [40]). ALCE used an NLI model for this step [10]. We use an LLM judge, validated with weighted κ ≥ 0.70 against humans on at least 100 pairs (PROPOSED DEFAULT).

| Metric | Formula |
|---|---|
| Citation precision | CP = #pairs FULL / #pairs (UNREACHABLE pairs excluded and counted separately) |
| Citation precision, lenient | (#FULL + #PARTIAL) / #pairs |
| Citation recall | CR = #claims needing support whose citation set contains ≥ 1 FULL / #claims needing support. "Claims needing support" = each finding's claim, each recommendation's evidence field, and each atomic external assertion |
| Fabricated-citation rate | FCR = #FABRICATED / #external citations |
| Read-before-cite rate | #READ / #external citations |
| Source-type accuracy | share of evidence items whose `source_type` (`doc \| external \| inference`; reconciled 2026-10-02, spec C10) is correct: `doc` items resolve in the doc, `external` items resolve to a ledger entry from a real tool call, `inference` items list `derived_from`. Measures lab §4.2, "distinguish design content from researched content" |

---

## 6. Recommendation and restraint metrics

### 6.1 Recommendation justification rate (RJR)
For each recommendation r:
- **S(r)** structural = issue, rationale, evidence and expected_benefit are all non-empty.
- **Q_issue(r)** = at least one linked finding is a TP or VALID_UNPLANTED.
- **Q_evid(r)** = at least one evidence item has support FULL (§5.2).
- **Q_benefit(r)** = expected_benefit names at least one doc objective, requirement or principle (`objective_refs` resolve in the doc), **and** a judge rates the stated benefit as following from the change (binary).
- **Q_rat(r)** = a judge rates that the rationale explains why the change addresses the issue (binary).

| Metric | Formula |
|---|---|
| RJR_struct | mean_r S(r) |
| RJR_subst (primary) | mean_r [S ∧ Q_issue ∧ Q_evid ∧ Q_benefit ∧ Q_rat] |
| Unjustified-recommendation rate | share of r whose linked findings are all FP (HALLUCINATED, INVALID_OPINION, NON_SPECIFIC) |
| Action-type accuracy | on matched flaws whose key gives an `expected_disposition`: share where the finding's primary `disposition` agrees (spec enum; reconciled 2026-10-02, spec C8). **BLOCKED** until a person authors `expected_disposition` in the keys |

### 6.2 Correctly declined on sound units
Map each finding to units by location overlap. For u ∈ S_d, let FP_u be the findings located in u that (a) have severity ≥ medium **or** carry a recommendation, and (b) are **not** TP and **not** VALID_UNPLANTED. If a VALID_UNPLANTED finding lands in u, the key was wrong: remove u from S_d and log it.

- declined(u) = 1 if FP_u = ∅, else 0
- **CDR** = Σ_u declined(u) / |S_d| (pooled over docs for micro; per doc for macro)
- **Bait resistance** = CDR restricted to bait units B_d
- **Justified-decline rate** JDR = Σ_u [declined(u) ∧ the section verdict for u is "sound" with a justification that passes G1/G3] / |S_d|. Report N/A if the agent emits no section verdicts.
- **Fully-sound doc accuracy** = share of runs on G_d = ∅ docs where `verdict.label = fit` (was doc_verdict = "yes"; reconciled, spec C9) and no recommendation of severity ≥ medium is made.
- **Balanced unit accuracy** = ½ · (unit detection rate + CDR), where unit detection rate = share of flawed units (units containing ≥ 1 gold flaw) with ≥ 1 matched flaw. This guards against the "never recommend" strategy (L18).

### 6.3 Approved-decision violation rate (lab §1.3: keep approved decisions)
For a ∈ A_d, a **violation** is a recommendation to reverse or replace a where (i) a is not the anchor of a gold flaw, and (ii) the recommendation has no FULL-support evidence of a defect in a.

ADV = #violated a / |A_d|. Flagging a genuinely flawed approved decision with evidence is **not** a violation; it is a TP.

---

## 7. Calibration and stability

### 7.1 Calibration (findings only; duplicates excluded)
The label is y_f = 1 if f is a TP or VALID_UNPLANTED, else 0.
- **ECE** (equal-mass bins b = 1..B; B = 10 if n ≥ 200, else 5): ECE = Σ_b (|b|/n) · | mean_{f∈b} y_f − mean_{f∈b} c_f | [11]
- **Brier** = (1/n) Σ_f (c_f − y_f)²; **Brier skill** = 1 − Brier / (ȳ(1 − ȳ))
- **AUROC** of c_f for predicting y_f (Mann–Whitney). It catches constant-confidence gaming (L19).
- **Reliability diagram**, plus **selective precision**: P_a among findings with c_f ≥ t, for t ∈ {0.5, 0.7, 0.9}.
- If the agent uses verbal levels only: report accuracy per level and Spearman's ρ between level and accuracy, with no ECE. Eliciting verbalised confidence is documented in [12].
- Doc-level calibration: doc_verdict.confidence against whether the verdict agrees with the key's fitness label (if the key has one).

### 7.2 Stability across runs
For doc d with runs j = 1..k and matched-gold sets M_j:
- Mean pairwise **Jaccard** J_d = mean_{j<j'} |M_j ∩ M_j'| / |M_j ∪ M_j'| (define 1 if both are empty)
- **Detect-in-all-k** = |∩_j M_j| / |G_d|; **detect-in-any-k** = |∪_j M_j| / |G_d|
- With n > k runs and c detections of flaw g, use the unbiased estimators pass@k = 1 − C(n−c, k)/C(n, k) (Chen et al. 2021, HumanEval; not re-verified) and pass^k = C(c, k)/C(n, k), the "all k succeed" notion of τ-bench [13]. The exact estimator form is **UNVERIFIED** against [13].

---

## 8. v1 → v2 re-review metrics (lab §1.5)

Diff key: R (resolved in v2), P (persisted), N (introduced in v2), A₂ (approved decisions in v2), C (changed sections). Run two variants: **fresh** (v2 only) and **with-context** (v2 plus the agent's own v1 review).

| Metric | Formula | Desired |
|---|---|---|
| Stale-finding rate | #r ∈ R that the agent raises as still open (matched to r's v1 description, with no acknowledgement of resolution) / |R| | ↓ |
| Resolved acknowledgement (with-context only) | #r ∈ R explicitly recognised as resolved / |R| | ↑ |
| Persisted recall | matched P / |P| | ↑ |
| New-flaw recall | matched N / |N| | ↑ |
| Changed-section coverage | #c ∈ C addressed by ≥ 1 finding or section verdict / |C| | ↑ (**UNVERIFIED** usefulness) |
| ADV on v2 | as in §6.3, with A₂ | ↓ |
| Copy-through rate (with-context) | share of v2 findings that are near-verbatim copies (≥ 0.9 similarity) of v1 findings about **resolved** flaws | ↓ |

---

## 9. Estimating key incompleteness (capture–recapture)

Two independent reviewers X and Y review the **base** (pre-plant) doc. Let n_X and n_Y be their valid natural-flaw counts and m the number found by both.
- Chapman's estimator: N̂ = (n_X + 1)(n_Y + 1)/(m + 1) − 1; the residual estimate is N̂ − |X ∪ Y|.
- Assumptions: independent reviewers, equal detectability. Both are usually violated (some flaws are just easier to see), which biases N̂ **downward** [7], [8]. Treat it as a lower-bound indicator, not a correction factor.
- The same idea applies across conditions after a run: use the agent and a human expert as X and Y on the same doc.
- Mills-style seeding logic [9]: if the agent finds a fraction q of the **planted** flaws and n_nat valid natural flaws, then n_nat / q is a rough estimate of the total natural flaws, assuming planted flaws are as detectable as natural ones (**UNVERIFIED** for LLM reviewers).

---

## 10. Efficiency and "knowing when to stop"

From the transcript and manifest:
- Cost (USD at a dated price table), input/output/cached tokens, number of tool calls by tool, wall time. Report median and IQR [2], [28].
- **Research yield** = #unique external sources cited in the final output / #unique external sources retrieved.
- **Overrun** = #tool calls made after step t*, where t* is the step at which the **last** finding that survives into the final output (TP or VALID_UNPLANTED) first appears in the agent's working state or findings ledger. A high overrun means the agent kept researching after it stopped learning anything it used. (Our operationalisation; **UNVERIFIED** as an established metric.)
- **Stop-reason distribution:** agent decision vs budget cap vs tool failure (L40), i.e. the `group` (decision / cap / error) of `spec/taxonomy.yaml` `stop_reasons` (reconciled, spec C12).
- **Cost-normalised quality:** report the Pareto frontier of (cost, SWR) across conditions. Do not divide accuracy by cost into one number [2].

---

## 11. Grader reliability (rubric scores)

Items are reviews (one run's output). Each rubric criterion r is ordinal, 1..K. *(Superseded, reconciliation 2026-10-02: the lecturer rubric is **0-4 per dimension** (K = 5 levels), `research/grading/README.md` §3.2; there is no second rubric (audit C1). The human comparisons below assume more raters than exist: with one person, grader validity is tiered smoke / tentative / primary, ordinal α and QWK are reported together, and human–human agreement is available only if a peer grades a subset (audit C2, §4.6). The "different families" comparison depends on `docs/DECISIONS.md` ADR-003, Pending (C3).)* Compare LLM grader vs human (at least one human; independent of the agent authors), LLM grader A vs LLM grader B (different model families), and human vs human (at least 30 items, as a ceiling; PROPOSED DEFAULT).

- **Cohen's κ** (nominal) = (p_o − p_e) / (1 − p_e), with p_o = observed agreement and p_e = Σ_q p_{1q} p_{2q}.
- **Quadratic-weighted κ** [41] = 1 − (Σ_{q,q'} v_{qq'} o_{qq'}) / (Σ_{q,q'} v_{qq'} e_{qq'}), with disagreement weights v_{qq'} = (q − q')² / (K − 1)², observed proportions o and expected proportions e = row marginal × column marginal. Implementation: `sklearn.metrics.cohen_kappa_score(a, b, weights="quadratic")`.
- **Krippendorff's α** [30] = 1 − D_o / D_e. From the coincidence matrix o_{qq'} with n pairable values and n_q = Σ_{q'} o_{qq'}:
  D_o = (1/n) Σ_q Σ_{q'} o_{qq'} δ²_{qq'},  D_e = (1/(n(n−1))) Σ_q Σ_{q'} n_q n_{q'} δ²_{qq'}
  - interval: δ²_{qq'} = (q − q')²
  - ordinal: δ²_{qq'} = ( Σ_{g=q..q'} n_g − (n_q + n_{q'})/2 )²
  - α handles any number of raters and missing ratings. Get CIs by bootstrapping over items. Implementation: a vetted library such as the `krippendorff` PyPI package (API **UNVERIFIED**), cross-checked once against a hand computation.
- **Gwet's AC1** (when one category holds more than 70% of ratings; PROPOSED trigger): AC1 = (p_o − p_e^γ) / (1 − p_e^γ), with p_e^γ = (1/(K−1)) Σ_q π_q (1 − π_q) and π_q = mean marginal proportion of category q. It avoids the high-agreement/low-κ paradox [42].
- **Percent agreement** is reported too, but never alone [34].
- **Bland–Altman** on total scores: bias d̄ = mean(LLM − human), limits of agreement d̄ ± 1.96·s_d. Report the slope of the differences on the means (proportional bias).
- **System-level validity:** Kendall's τ between the ranking of conditions by human scores and by LLM scores. Item-level κ can be fair while rank correlation is high [34], so report both.
- **Gates** (PROPOSED DEFAULTS, using Krippendorff's thresholds [30]): α_ordinal(LLM, human) ≥ 0.80 → the LLM grader can be primary; 0.667 ≤ α < 0.80 → tentative, every reported score MUST be accompanied by human co-grading on ≥ 30% of items; < 0.667 → the LLM grader is not used.

---

## 12. Aggregation, intervals, paired comparisons, multiple testing

### 12.1 Aggregation
Per run → per doc (mean over the k runs) → over docs (macro). For micro metrics, pool counts across docs **within each run index**, compute the ratio, then average over runs. Every table states which it uses.

### 12.2 Two-level cluster bootstrap (CI for one condition) [17], [1]
```python
def cluster_bootstrap(per_doc_runs, stat=np.mean, B=10_000, rng=np.random.default_rng(0)):
    """per_doc_runs: dict doc_id -> list of per-run metric values (NaN = undefined, skipped)."""
    docs = [d for d, v in per_doc_runs.items() if np.isfinite(v).any()]
    boot = np.empty(B)
    for b in range(B):
        sampled_docs = rng.choice(docs, size=len(docs), replace=True)   # level 1: docs
        doc_means = []
        for d in sampled_docs:
            runs = np.array([x for x in per_doc_runs[d] if np.isfinite(x)])
            doc_means.append(rng.choice(runs, size=len(runs), replace=True).mean())  # level 2: runs
        boot[b] = stat(doc_means)
    point = stat([np.nanmean(per_doc_runs[d]) for d in docs])
    return point, np.percentile(boot, [2.5, 97.5])
```
For micro (ratio) metrics, resample docs and recompute the pooled numerator and denominator inside the loop. Do not average ratios.

### 12.3 Paired difference between conditions A and B
```python
def paired_diff(perA, perB, B=10_000, rng=np.random.default_rng(1)):
    docs = sorted(set(perA) & set(perB))              # same docs in both conditions
    diffs = np.empty(B)
    for b in range(B):
        ds = rng.choice(docs, size=len(docs), replace=True)
        a = [rng.choice(perA[d], len(perA[d])).mean() for d in ds]
        c = [rng.choice(perB[d], len(perB[d])).mean() for d in ds]
        diffs[b] = np.mean(a) - np.mean(c)
    point = np.mean([np.mean(perA[d]) - np.mean(perB[d]) for d in docs])
    ci = np.percentile(diffs, [2.5, 97.5])
    p_two_sided = 2 * min((diffs <= 0).mean(), (diffs >= 0).mean())   # bootstrap p (approx.)
    return point, ci, min(p_two_sided, 1.0)
```
Analytic check for per-flaw binary outcomes: McNemar's test on discordant flaws (b, c): χ² = (|b − c| − 1)² / (b + c), or the exact binomial test when b + c < 25. Treat it as a sanity check only, since it ignores clustering [18].

### 12.4 Multiple comparisons
```python
def holm(pvals, alpha=0.05):
    order = np.argsort(pvals); m = len(pvals); reject = np.zeros(m, bool)
    for rank, i in enumerate(order):
        if pvals[i] <= alpha / (m - rank): reject[i] = True
        else: break
    return reject

def benjamini_hochberg(pvals, q=0.10):
    p = np.asarray(pvals); m = len(p); order = np.argsort(p)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    k = np.max(np.where(passed)[0]) + 1 if passed.any() else 0
    reject = np.zeros(m, bool); reject[order[:k]] = True
    return reject
```
Primary family = {FULL vs each of B0, B0-$, A1, A2, A3, A4e, A5} (A4e replaces A4, `docs/DECISIONS.md` ADR-002) on the pre-registered primary metric → Holm. Per-category and per-split breakdowns → BH, labelled exploratory [19].

### 12.5 Power
Paired proportions (Connor [21]): n = [z_{1−α/2}·√ψ + z_{1−β}·√(ψ − δ²)]² / δ², multiplied by DEFF = 1 + (m − 1)ρ. Doc-level paired means: n_docs = ((z_{1−α/2} + z_{1−β})·σ_d / δ)². README §4b has the worked table. Report the **minimum detectable effect** at the achieved n for every non-significant comparison.

---

## 13. Consolidated scoring pseudo-code

```python
W = {"critical": 8, "high": 4, "medium": 2, "low": 1}          # = spec/taxonomy.yaml severities[].weight_primary

def score_run(doc, key, out, matcher, adjudicator, judge, strict=True):
    F = [f for f in out.findings if f.kind != "strength"]
    G = key.flaws
    # --- 2.3.1 candidates
    cand = set()
    for g in G:
        cand |= {(f.id, g.id) for f in F if overlaps(f.location, g.location)}
        cand |= {(f.id, g.id) for f in top_k_by_embedding(F, g, k=3, min_cos=TAU_PRE)}
        cand |= {(f.id, g.id) for f in matcher.shortlist(g, shuffled(F), k=3)}
    # --- 2.3.2 pairwise scores (median of 3; matcher blind to condition)
    S = {(fi, gi): median(matcher.score(F[fi], G[gi]) for _ in range(3)) for (fi, gi) in cand}
    # --- 2.3.3 Hungarian assignment
    thr = 3 if strict else 2
    Wm = np.zeros((len(F), len(G)))
    for (fi, gi), s in S.items():
        if s >= thr: Wm[fi, gi] = s + 0.01 * W[G[gi].severity]
    rows, cols = linear_sum_assignment(Wm, maximize=True)
    M = [(r, c) for r, c in zip(rows, cols) if Wm[r, c] > 0]
    matched_f = {r for r, _ in M}; matched_g = {c for _, c in M}
    # --- 2.3.4 adjudicate unmatched (LLM first pass; human review queued per protocol)
    cls = {i: adjudicator.classify(F[i], doc, key) for i in range(len(F)) if i not in matched_f}
    queue_for_human([i for i, c in cls.items() if c in ("VALID_UNPLANTED", "HALLUCINATED")])
    queue_for_human(random_sample([i for i, c in cls.items() if c not in ("VALID_UNPLANTED", "HALLUCINATED")], frac=0.2))
    # --- 5.1 grounding on ALL findings
    halluc = {i for i in range(len(F)) if not grounded(F[i], doc, judge)} | {i for i, c in cls.items() if c == "HALLUCINATED"}
    TP, N, V = len(M), len(F), sum(c == "VALID_UNPLANTED" for c in cls.values())
    R  = TP / len(G) if G else None
    Ps = TP / N if N else None
    Pa = (TP + V) / N if N else None
    SWR = (sum(W[G[c].severity] for c in matched_g) / sum(W[g.severity] for g in G)) if G else None
    gains = [W[G[dict(M)[i]].severity] if i in matched_f else 0 for i in rank_order(F)]
    ideal = sorted((W[g.severity] for g in G), reverse=True)
    k = len(G)
    ndcg = (dcg(gains[:k]) / dcg(ideal[:k])) if G else None
    HFR = len(halluc) / N if N else None
    cite = citation_faithfulness(out, doc, snapshots=out.snapshot_store, judge=judge)   # §5.2
    rjr  = recommendation_justification(out, M, cls, cite, judge)                       # §6.1
    cdr  = correctly_declined(out, key, M, cls)                                           # §6.2
    adv  = approved_decision_violations(out, key, cite)                                   # §6.3
    cal  = calibration([F[i].confidence for i in range(N) if cls.get(i) != "DUPLICATE"],
                       [1 if (i in matched_f or cls.get(i) == "VALID_UNPLANTED") else 0
                        for i in range(N) if cls.get(i) != "DUPLICATE"])                 # §7.1
    return dict(R=R, Ps=Ps, Pa=Pa, F1s=f1(Ps, R), F1a=f1(Pa, R), SWR=SWR, nDCG=ndcg,
                HFR=HFR, **cite, **rjr, **cdr, ADV=adv, **cal,
                dup_rate=sum(c == "DUPLICATE" for c in cls.values()) / N if N else None)

def dcg(g): return sum(x / np.log2(i + 2) for i, x in enumerate(g))
def f1(p, r): return None if p is None or r is None else (0 if p + r == 0 else 2 * p * r / (p + r))
```

---

## 14. Worked example (sanity check of the formulas)

The key has 4 flaws: F1 critical (w = 8), F2 high (4), F3 medium (2), F4 low (1); Σw = 15. The agent emits 5 findings in rank order:

| Rank | Finding | Outcome |
|---|---|---|
| 1 | f1 | MATCH F2 |
| 2 | f2 | unmatched → VALID_UNPLANTED |
| 3 | f3 | MATCH F1 |
| 4 | f4 | score 3 with F2, but F2 is already taken → DUPLICATE |
| 5 | f5 | unmatched → HALLUCINATED (false-absence claim) |

- TP = 2, N = 5, V = 1, G = 4
- R = 0.50; P_s = 0.40; P_a = 0.60; F1_s = 0.444; F1_a = 0.545
- SWR = (8 + 4)/15 = 0.80; critical recall = 1.0
- nDCG@4: gains [4, 0, 8, 0], so DCG = 4/1 + 8/2 = 8.0. IDCG = 8/1 + 4/log₂3 + 2/2 + 1/log₂5 = 11.954. nDCG = **0.669**
- MRR_crit = 1/3; critical-in-top-3 = 1
- HFR = 1/5 = 0.20; duplication rate = 0.20
- Calibration set excludes f4, so n = 4 with labels y = [1, 1, 1, 0]

These numbers were computed with the formulas above (Python check during authoring). Any scoring implementation MUST reproduce them as a unit test.
