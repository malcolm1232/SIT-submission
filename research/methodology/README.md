# Research-grade evaluation of an LLM design-review agent

**Status:** specification v1.0 (2026-10-02). Self-contained and reusable outside the SIT project.
**Companion:** [`metrics.md`](metrics.md) has the formal metric definitions, the finding-to-flaw matching procedure and pseudo-code.
**Scope:** how to evaluate an agent that reads a technical design document (PDF), plans, researches with web and scholarly tools, judges fitness for purpose, lists strengths, risks, gaps, ambiguities and unresolved assumptions, and recommends refinements (issue, rationale, evidence, expected benefit) or explains why no change is needed.

**Conventions**
- MUST / SHOULD / MAY follow RFC 2119.
- `[n]` refers to the reference list in §12. Every reference marked *verified* was checked this session by web search (title, authors, venue or arXiv id). Statements marked **UNVERIFIED** are our own proposals or claims we could not check. Treat them as defaults to revisit, not as established findings.
- "Doc" means one design document that is evaluated. "Flaw" means one entry in a sealed answer key. "Finding" means one atomic issue the agent raises.

---

## 0. What "research-grade" means here (one paragraph)

A result counts as research-grade when (a) every headline number is defined by a formula that someone else can recompute from logged raw outputs; (b) it comes with an uncertainty estimate that respects the data's structure (documents are clusters of flaws; runs are noisy); (c) it is reported on data the system was never tuned on, including data written by people or agents who did not know the system or its taxonomy; (d) it is compared against baselines and ablations that isolate each claimed contribution at matched cost; (e) the measuring instruments (the matcher, the LLM grader, the citation checker) are themselves validated against humans; and (f) a sceptical reader can find no unclosed loophole on the checklist in §9. This follows the general direction of [1] Miller 2024 (error bars, clustering, paired tests, power), [2] Kapoor et al. 2024 (agent evals must be cost-controlled and must have adequate holdouts), [3] Kapoor & Narayanan 2023 (leakage taxonomy) and [4] Pineau et al. 2021 (reproducibility checklist).

### 0.1 Mapping to the SIT lab success criteria

| SIT lab requirement (section of the lab PDF) | Measured by (see `metrics.md`) |
|---|---|
| Identify strengths, risks, gaps, ambiguities, unresolved assumptions, validation needs (2.3) | Per-category P/R/F1, severity-weighted recall, ranking nDCG |
| Recommend refinements only when justified; otherwise say why the design is fine (1.2, 1.4, 2.3, 3.2) | Recommendation justification rate, correctly-declined rate, justified-decline rate |
| Evidence-based, traceable findings (2.4) | Hallucinated-finding rate, citation faithfulness (precision and recall), fabricated-citation rate |
| Know when to stop researching (1.3, 3.2, 4.5) | Stopping and efficiency metrics: research yield, overrun, cost per run |
| Keep key requirements and approved decisions (1.3) | Approved-decision violation rate |
| Re-review an updated v2 artefact (1.5) | v2 re-review metrics: resolved acknowledgement, stale-finding rate, new-flaw recall |
| Distinguish design content from externally researched content (4.2) | Citation source-type accuracy (part of citation faithfulness) |

---

## 1. Evaluation data and the ground-truth contract

### 1.1 Tiers and splits

| Split | Authored by | Knows our flaw taxonomy? | Who may read it | Use | Access budget |
|---|---|---|---|---|---|
| **S-dev** | Tier-1 synthetic authors | yes | developers | iteration, prompt tuning, threshold calibration (matcher, citation checker) | unlimited |
| **S-heldout** | Tier-1 synthetic authors, same process, different seeds, topics and generator model | yes | nobody on the agent team; the eval runner only | milestone checks | MUST be logged; **≤ 3 evaluations** in total (PROPOSED DEFAULT, UNVERIFIED as optimal; reasoning in [5] Dwork et al. 2015) |
| **Blind** | Tier-2 agents with no knowledge of the project, the taxonomy or the agent | no | nobody until the final run | final generalisation claim | **1 evaluation**, after the pre-registration is frozen |
| **Real-dev** | the SIT artefact(s) supplied for the lab | n/a (no planted key) | everyone (already read) | qualitative checks and rubric grading only; **never** a generalisation claim | unlimited |
| **OOD** | any author; an unrelated domain (e.g. a civil-engineering method statement or a clinical-trial protocol) | no | sealed | overfitting check (§5) | 1 |
| **v1→v2 pairs** | Tier-1 and Tier-2 | as per tier | as per tier | re-review scenario (lab §1.5) | as per tier |

> **Superseded (reconciliation 2026-10-02):** the actual assignment of items to these tiers is `docs/DECISIONS.md` ADR-004. S-dev = `eval/synthetic/*` (3 items). **S-heldout = the current `eval/blind/item_a` and `item_b`, reclassified**: they are *not* blind (developers can read them, their briefs carried knowledge of this eval design, and they were probably generated by the agent's model family), so they do not meet the "different generator model" or "nobody on the agent team" conditions above; they are sealed per `docs/SEALING.md` with ≤ 3 logged evaluations. **Blind** (Tier-2) is **to be commissioned** and does not exist yet. OOD and fully sound controls are also to be authored. DEMO-05 rehearsals use a separate **rehearsal pool**, never Blind (audit C19).

Rules:
1. Every doc MUST be assigned to exactly one split before anyone reads it. The assignment table MUST be hashed (SHA-256) and the hash recorded in the run manifest.
2. S-dev and S-heldout MUST be split **by generation batch / template family**, not by random document. Otherwise template artefacts leak across the split (see §9 item L8).
3. Tier-2 authors write their own answer key in free text (flaw, location, why it matters, severity on a 4-level scale with anchors we provide). A third party who has not seen the agent's outputs maps each key entry onto our taxonomy, or into an `OTHER` bucket, **before** the blind run. The mapping MUST NOT edit flaw content.
4. Every synthetic or blind doc MUST also be rendered to PDF through the same pipeline the lab uses (tables, headers and footers, at least one figure), because the lab input is a PDF. Clean markdown alone does not test ingestion.
5. Each eval doc and key MUST contain a per-split **canary GUID** (practice from BIG-bench [6]) so it can be detected wherever it leaks.

### 1.2 Answer-key schema (per doc)

Each key MUST contain:
- `flaws[]`: `id`, `category` (taxonomy), `severity` ∈ {critical, high, medium, low} with written anchors, `location` (one or more section or requirement ids plus a quoted anchor span), `description`, **`core_insight`** (the one proposition a finding must contain to count as detecting this flaw), `needs_external_research` (bool), `acceptable_evidence` (what a correct justification would cite), `planted` (bool; `false` means a natural flaw found during the base-doc audit).
- `sound_units[]`: sections or decisions that are deliberately **fit for purpose**, each with a `why_sound` note. A subset are **bait** units: unusual-looking but justified within the doc (e.g. a surprising technology choice with a documented rationale). These units drive the correctly-declined metric.
- **Fully sound control docs:** at least 10% of docs in each split SHOULD contain **no** planted flaw (after the base audit), so that "this design is fit for purpose, no change recommended" is a scoreable outcome (PROPOSED DEFAULT).
- `approved_decisions[]`: decisions the doc marks as confirmed (cf. "Confirmed Decisions" tables in real artefacts). Used for the approved-decision violation rate.
- For v2 docs: `diff_key` with `resolved[]`, `persisted[]`, `introduced[]` flaw ids and `changed_sections[]`.

A default taxonomy that follows lab §2.3 (the project taxonomy overrides it): `RISK`, `GAP` (missing element), `AMBIGUITY` (underspecified or multi-reading), `UNRESOLVED_ASSUMPTION`, `INCONSISTENCY` (internal contradiction), `UNSUPPORTED_OR_INCORRECT_CLAIM` (needs external research to refute), `VALIDATION_NEED` (untestable or unvalidated requirement), `OTHER`.

> **Superseded (reconciliation 2026-10-02):** the project taxonomy is **`spec/taxonomy.yaml`**, the only enum registry. It has two orthogonal axes: `kind` (lab §2.3: strength, risk, gap, ambiguity, unresolved_assumption, validation_need) and `category` (defect mechanism: 9 codes plus `other`). The eight codes above map onto them via `legacy_mappings.methodology_codes` (e.g. `INCONSISTENCY` → kind `risk` + category `internal_contradiction`). Severity is `critical | high | medium | low` with weights 8/4/2/1 (sensitivity 4/3/2/1); strengths carry `severity: null`. The answer-key schema above is superseded by **`spec/answer_key.schema.json`**: `sound_units[]` → `sound_sections[]` (bait → `bait: true`), `diff_key` → the `v2` block plus per-flaw `v2_status`, plus `credit {mode, items}`, `expected_disposition`, `still_valid_observations[]`, `canary_guid` and generator provenance. Fully sound control docs do not exist yet; at least 2 are to be authored (ADR-004; audit C22). See `spec/README.md` §3 (C6, C7, C32).

### 1.3 Base-document audit (closes the "incomplete key" loophole at the source)
Before planting, at least two independent reviewers (human or agent; at least one MUST be a model family different from the agent's) review each base doc. Every natural flaw that either reviewer finds is added to the key with `planted=false`. Use a capture-recapture estimate (`metrics.md` §9) to judge how many natural flaws are probably still missing. This is the software-inspection practice of Eick et al. 1992 and Briand et al. [7], [8]. Seeding known faults to estimate the unknown ones goes back to Mills 1972 [9].

---

## 2. Metrics (summary; formal definitions in `metrics.md`)

| Family | Metric | One-line definition | Primary? |
|---|---|---|---|
| Detection | Precision (strict, adjudicated), Recall, F1, each per category and overall (micro and macro) | 1:1 matching of findings to key flaws (Hungarian), validated LLM matcher plus human adjudication | **Recall, adjudicated precision** |
| Detection | Severity-weighted recall (SWR), critical recall | Σ weights of matched flaws / Σ weights of all flaws | **SWR** |
| Ranking | nDCG@k (gain = severity weight), MRR of first critical, critical-in-top-3 | Does the agent put critical flaws first? | yes |
| Grounding | Hallucinated-finding rate (HFR) | Share of findings whose central premise about the doc is false (fabricated quote or location, false-absence claim) | **yes** |
| Grounding | Citation precision, citation recall, fabricated-citation rate | ALCE-style [10] support judgments on (claim, citation) pairs, plus existence checks | yes |
| Recommendation | Recommendation justification rate (structural and substantive) | All four fields present **and** each passes its quality check | yes |
| Restraint | Correctly-declined rate (CDR) on sound units, bait resistance, justified-decline rate, balanced unit accuracy | No unjustified finding or recommendation on deliberately sound sections | **yes** |
| Restraint | Approved-decision violation rate | Recommends reversing a confirmed decision without new evidence | yes |
| Calibration | ECE (equal-mass bins), Brier, AUROC, reliability diagram | Stated confidence vs adjudicated correctness [11], [12] | secondary |
| Stability | Run-to-run Jaccard, detect-in-all-k (pass^k-style [13]), detect-in-any-k | Consistency over k runs (no seed exists on Claude; reconciled, audit C15) | secondary |
| Efficiency | Cost (USD), tokens, tool calls, wall time, research yield, overrun | Knowing when to stop | secondary |
| v2 re-review | Resolved acknowledgement, stale-finding rate, persisted and new-flaw recall | Lab §1.5 scenario | yes (on v2 pairs) |
| Grader reliability | Weighted Cohen's κ, Krippendorff's α, Gwet AC1, Bland–Altman bias | LLM grader vs human, LLM grader vs second-family LLM grader, human vs human | **gate** |

**Pre-registration (MUST).** Before the first S-heldout run, freeze a file `prereg.yaml` that lists: the primary metrics (bold above), the primary comparison (full agent vs B0 single-call), the ablation family, the α level, the correction method, the number of runs per doc, and the matcher and grader versions. Store its hash in every manifest. Anything not listed is **exploratory** and MUST be labelled as such in the report.

---

## 3. Splits and leakage

### 3.1 Hard rules
- **R1. No eval-doc-specific text in any agent artefact.** This covers system and task prompts, few-shot examples, tool descriptions, memory or seed stores, retrieval indices, code constants and test fixtures. "Specific" means any distinctive n-gram, entity name, requirement id, number or section title taken from an S-heldout, Blind, OOD or v2 doc. General domain vocabulary is allowed only if it is on a pre-registered allow-list with an independent justification.
- **R2. No access to keys at agent runtime.** Keys MUST be stored encrypted (e.g. `age` or `gpg`) or outside the agent's sandbox. The agent process MUST run with a filesystem allow-list that excludes `eval/**/key*` and the keys' decryption material. Tool-call logs MUST be scanned for any read of eval paths.
- **R3. No web route to keys.** If the repository is or will become public, the keys MUST NOT be in it in plaintext. The search tool MUST block the project's own repository domains, and logs MUST be scanned for hits on them. Without this, an agent with web search can simply find the answer key.
- **R4. The grader and the matcher are separate code paths** from the agent. Private rubric anchors and exemplars MUST NOT appear in agent prompts. The lab's public criteria may.
- **R5. Real-dev artefact terms.** The SIT artefact used for development (and its expected v2) MUST be treated as a held-out item for leakage purposes, even though the team has read it. Its distinctive terms (product names, requirement ids, named components and policies) MUST NOT appear in prompts. Otherwise the demo-day v2 re-review would partly measure memorised tuning.
- **R6. Generator ≠ agent model family** for Tier-1 docs where feasible. Tier-2 authors SHOULD use yet another family, or be humans.

> **Superseded (reconciliation 2026-10-02):** every "different family" requirement for the matcher, adjudicator, G3 premise judge, citation judge and grader (R4, L35, §8) is conditional on `docs/DECISIONS.md` **ADR-003 (Pending)**. Branch A: a cross-family model. Branch B (Anthropic key only): short-context instruments on a local open-weight model validated against human labels, the holistic grader on Claude disclosed as same-family, and every Claude-judged number labelled "same-family, tentative". Nothing judge-dependent is frozen in `prereg.yaml` until ADR-003 is decided (audit C3).

### 3.2 Leakage detection procedure (run before every held-out or blind evaluation; results go in the report)
1. **Distinctive-term grep.** For each sealed doc d, extract its top distinctive 1–4-grams by TF-IDF against a general corpus plus the S-dev pool (keep the top 200 per doc, plus all requirement ids, numbers with units, and proper nouns). Grep every agent artefact listed in R1. Any hit fails the audit until it is resolved or allow-listed with justification.
2. **N-gram overlap.** Compute 13-gram overlap (the window used in the GPT-3 contamination analysis [14]) and 8-gram overlap between the concatenated agent artefacts and each sealed doc. Report the maximum overlap per doc. Target: 0 13-gram hits.
3. **Canary scan.** Grep agent artefacts, memory stores, vector indices and logs for every canary GUID.
4. **Runtime access scan.** Parse tool-call logs for reads of eval paths, own-repo URLs or canary strings in retrieved web content.
5. **Paraphrase and rename probe.** For a sample of at least 10 sealed docs, create a meaning-preserving paraphrase with all entity names, ids and numbers consistently renamed. A drop in recall beyond run-to-run noise (paired test, §4) on the paraphrased version signals memorisation of surface strings rather than reasoning. Compare with the GSM1k-style "fresh but matched" check in [15].
6. **Template-tell probe.** Train a trivial model (bag-of-words logistic regression on section text, or a "headings-only" LLM prompt that never sees section bodies) to predict which sections contain planted flaws. If it is clearly above chance on S-heldout, the generator leaves artefacts and the agent can exploit them. This is the analogue of hypothesis-only baselines for annotation artefacts [16].

---

## 4. Baselines and ablations

All conditions MUST use **the same output schema** (so the matcher sees comparable structure), the same doc rendering, the same runs per doc, and MUST report cost. Following [2], every accuracy claim MUST be shown next to cost.

| ID | Condition | What changes | What it proves if the full agent is significantly better | Prediction to check (category-specific) |
|---|---|---|---|---|
| **B0** | Single call, no tools | Whole doc text plus task prompt in one call, same schema | Value of the agentic loop as a whole | Full > B0 on recall and on grounding |
| **B0-$** | Cost-matched single call | B0 with self-consistency or best-of-n until its cost matches the full agent's median cost | Gains are not just more compute [2] | If Full ≈ B0-$, the architecture adds nothing beyond spend |
| **B-gen** | Generic-checklist floor | Emits a fixed list of 20 generic design-review findings regardless of the doc | Calibrates the **matcher**: strict recall MUST be ≈ 0. If not, the matcher is lenient (loophole L4) | Recall_strict(B-gen) ≤ 0.05 (PROPOSED GATE) |
| **A1** | No research | Web and scholarly tools off; loop, iteration and verification kept | Research contributes to judgement | Drop concentrated in `needs_external_research=true` flaws and in citation recall; little change on `INCONSISTENCY` |
| **A2** | No iteration | One plan→execute pass, no revise loop | Iterative refinement (lab §4.5) matters | Drop in recall of subtle or multi-section flaws; possible precision change |
| **A3** | No verification pass | Final self-check removed | Verification reduces ungrounded output (lab §2.4) | HFR and fabricated-citation rate rise; recall roughly flat |
| **A4e** | Low-effort backbone *(replaces A4 "different backbone model"; reconciled 2026-10-02 per `docs/DECISIONS.md` ADR-002, audit C24)* | Same model (Claude Opus 5.5), every stage at effort `low`; harness unchanged | How much of the result depends on reasoning effort rather than the harness. It does **not** show that results are not tied to one model; that claim is dropped | If FULL's advantage over B0 shrinks sharply at effort `low`, the harness claims depend on high effort |
| **A5** | All tools disabled | Every MCP tool off (doc text supplied directly) | Graceful degradation; **honesty** | Fabricated-citation rate MUST be 0, and the output MUST disclose that no research was done. Any external citation here is fabricated |
| **H** | Human expert (subset, at least 10 docs) *(reconciled 2026-10-02: dropped, or cut to the 3-doc pilot and labelled anecdotal, under the one-person plan; audit §4.6, C21; `docs/BUDGET.md` §2)* | Independent qualified reviewer, same schema | Ceiling and realism anchor | Human P/R also bound how good the keys are |

Interpretation rules:
- An ablation "shows a component contributes" only if the paired difference's CI excludes 0 after the family-wise correction (§4b item 5 / `metrics.md` §12). A null result means "no evidence at this sample size". Report the minimum detectable effect at the achieved n.
- Category-specific predictions (last column) MUST be written in `prereg.yaml` beforehand. A predicted pattern that holds is much stronger evidence than an overall drop alone.
- Treat ablation runs as interleaved and randomised in time (alternate conditions per doc), so that silent API model drift does not line up with the conditions.
- **What is lost by replacing A4 with A4e** (all-Opus decision, `docs/DECISIONS.md` ADR-002): no condition separates harness value from model value any more, so no result here may be described as model-independent; A4e only measures sensitivity to reasoning effort within Claude Opus 5.5.

---

## 4b. Statistical rigour (§4 of the brief)

1. **Units and structure.** Data are nested: doc → flaw (or finding) → run. Docs are the independent units. Flaws within a doc are correlated (one misreading of the doc hides several flaws). Treating flaws as independent understates the error bars [1].
2. **Runs.** At least **k = 3** runs per (doc, condition) at the production temperature. *(Superseded, reconciliation 2026-10-02: Claude Opus 5.5 exposes no `temperature`, `top_p`, `top_k` or `seed`; sampling is "provider-default (not settable)", and the manifest records `thinking`, `effort`, `max_tokens` and `betas` instead. Results are statistically, not bitwise, reproducible. See `docs/REPRODUCIBILITY.md` §1, §8 and `spec/README.md` §3 C15.)* k = 5 is preferred for the primary comparison. Report the mean, the between-run SD, and the share of variance due to runs versus docs (ICC). Do not use temperature 0 to hide variance unless production also uses 0, and say so. pass^k-style consistency [13] is reported as a secondary metric.
3. **Intervals.** Use a **two-level cluster bootstrap** (resample docs with replacement, then runs within each sampled doc), B = 10,000, percentile intervals (BCa if skew is visible). This follows Field & Welsh [17] and the clustered-SE advice in [1]. For single proportions with no clustering (e.g. one human audit sample), use Wilson intervals.
4. **Comparisons.** Always **paired**: the same docs and the same run indices across conditions. Report the paired difference and its bootstrap CI. For a binary per-flaw outcome (detected or not), McNemar's test or a paired permutation test is the analytic check [18]. Report effect sizes, not only p-values [18].
5. **Multiple comparisons.** Treat the ablation set {A1, A2, A3, A4e, A5, B0, B0-$} on the primary metric as one family and apply **Holm** correction. Treat per-category and per-split breakdowns as exploratory, use **Benjamini–Hochberg** FDR at q = 0.10 [19], and label them exploratory.
6. **Power and minimum sizes.** NLP experiments are often underpowered [20]. Computed with Connor's paired-proportion formula [21] (α = 0.05 two-sided; ψ is the share of flaws on which the two conditions disagree):

| Detectable difference in recall | ψ (discordance) | 80% power: flaws needed (independent) | 90% power |
|---|---|---|---|
| 0.20 | 0.30 | 57 | 75 |
| 0.15 | 0.20 | 68 | 90 |
| 0.15 | 0.30 | 103 | 136 |
| 0.10 | 0.20 | 155 | 206 |
| 0.10 | 0.30 | 234 | 312 |
| 0.05 | 0.10 | 312 | 417 |
| 0.05 | 0.20 | 626 | 837 |

   Inflate these by the design effect DEFF = 1 + (m − 1)ρ for m flaws per doc and intra-doc correlation ρ. Example: m = 8 and ρ = 0.1 give DEFF = 1.7, so a 10-point recall difference at ψ = 0.2 needs about 264 flaws, about **33 docs of 8 flaws**. Estimate ρ from S-dev pilot runs. The ρ values here are illustrative, not measured (**UNVERIFIED** for this task).
   Doc-level paired differences (e.g. macro-F1) need n = ((z₀.₉₇₅ + z_power)·σ_d/δ)² docs. With σ_d = 0.10: δ = 0.05 needs **32 docs** and δ = 0.10 needs **8 docs** at 80% power. With σ_d = 0.15: 71 and 18 docs. Estimate σ_d from the pilot.
   Wilson 95% half-widths for a single proportion near 0.7: ±0.12 at n = 50, ±0.088 at n = 100, ±0.063 at n = 200.
   **Implication for the Blind split:** with about 15 blind docs the only defensible claim is "no large (≥ 0.15) dev→blind gap". State the minimum detectable gap explicitly instead of claiming parity.

> **Superseded (reconciliation 2026-10-02):** the achieved n is far smaller: 3 S-dev + 2 S-heldout docs (70 v1 flaws + 3 v2 regressions, m = 14 per doc, so ρ = 0.1 gives DEFF = 2.3, not 1.7), and a Blind set still to be commissioned (`docs/BUDGET.md` assumes 4 docs). Per-category and ablation results are **exploratory** at this n; any dev→held-out gap is reported with its CI and as a DiD against B0, with no pass/fail threshold. The achieved n and the MDE at that n go in `prereg.yaml`. See `docs/DECISIONS.md` ADR-004 (audit C20, C21).
7. **Grader-agreement sample size.** The asymptotic 95% half-width of κ at p_o = 0.8 and p_e = 0.5 is about ±0.22 at n = 50, ±0.16 at n = 100 and ±0.11 at n = 200 (large-sample approximation; compute exact bootstrap CIs on real data). Target **at least 100 doubly graded items** before trusting the LLM grader. *(Superseded, reconciliation 2026-10-02: with one rater this is the "primary" tier and is not expected to be reached; claims are tied to the tier achieved: smoke n = 5 (grading §7), tentative n ≥ 20 with ordinal α ≥ 0.667 and bootstrap CI, primary as in §8. Report ordinal α and QWK together. Audit C2 and §4.6; tiers to be frozen in `prereg.yaml`.)* See also Sim & Wright 2005 for κ sample-size tables (not re-verified this session, **UNVERIFIED**).
8. **Report everything that was run.** No seed or run cherry-picking. The run count per condition is fixed in `prereg.yaml`, and failed runs are reported (§6) [22].

---

## 5. Overfitting checks

| Check | Procedure | Signal of overfitting | Caveat and control |
|---|---|---|---|
| **Dev→held-out→blind gap** | Same metrics on S-dev, S-heldout and Blind | Full-agent recall or SWR drops more than noise | A gap can come from a **harder** blind distribution, not from overfitting (Recht et al. found drops that were due to harder data, not adaptivity [23]). Control: compute the gap for **B0 as well** and report the **difference-in-differences** Δ_Full − Δ_B0. Overfitting is indicated when the tuned agent loses more than the untuned baseline |
| **Taxonomy dependence** | Recall on Blind flaws mapped to `OTHER` vs mapped to taxonomy categories | Much lower recall on `OTHER` | Shows the agent learned our taxonomy rather than design review |
| **Paraphrase and rename invariance** | §3.2 step 5 | Significant paired drop | A CheckList-style invariance test [24] |
| **Section reordering** | Shuffle the order of independent sections (keep cross-references valid), move planted flaws to different positions | Recall depends on position (e.g. middle sections missed) | Position effects in long contexts are documented in [25]. Report recall by relative position decile |
| **Format perturbation** | Same content, different template, heading style, table vs prose | Drop beyond noise | Prompt and format sensitivity is documented in [26] |
| **Unrelated-domain doc (OOD)** | Run on a sound or flawed doc from an unrelated field | (a) Software-specific findings imposed on a non-software doc; (b) HFR rises; (c) the agent invents IT concerns | Also tests honest scoping: the agent should say when the domain is outside its competence |
| **Clean-vs-flawed counterfactual** | Review the clean base doc and the planted version (identical except for the plant) | The finding set barely changes, so the agent is not sensitive to the flaw | Paired counterfactual design from Dycke & Gurevych [27]. Credit only **differential** findings for the planted flaw |
| **v2 re-review (lab §1.5)** | Run on v1, then on v2 (some flaws fixed, some kept, some new, some sections changed by "other reviewers"), each as a fresh session, plus a variant where the v1 review is supplied as context | Stale findings re-raised on fixed sections; new flaws in changed sections missed; recommendations to revert approved v2 decisions | Report the v2 metrics in `metrics.md` §8. With v1 review in context, check that the agent does not just copy v1 findings: the stale-finding rate is the key number |
| **Held-out reuse** | Count S-heldout evaluations | More than the budget | Adaptive overfitting to a reused holdout [5]. Log every access |

---

## 6. Robustness reporting

The robustness scenarios themselves live in `research/robustness/`. This section fixes **how they are reported**.

1. **Separate tables.** Report nominal runs (no injected faults, all tools healthy) separately from fault-injected runs. Never average them silently.
2. **Two populations.** Report on **intention-to-treat** (all launched runs; a crashed run scores 0 recall and is counted) and on **per-protocol** (completed runs only). Survivorship bias otherwise hides failures.
3. **Run outcome taxonomy** (one per run): `completed_nominal`, `completed_degraded` (a tool failed and the agent continued), `aborted_graceful` (stopped with a partial report and a disclosure), `crashed`, `timeout`, `budget_exceeded`. Report counts per condition.
4. **Degraded-mode quality.** On docs run both nominally and with faults, report paired differences in recall, HFR, citation precision and fabricated-citation rate. A good agent loses recall on research-dependent flaws but **must not** increase fabrication.
5. **Disclosure rate.** The share of degraded runs whose final report correctly states which research could not be done and how that limits conclusions. A missing disclosure is a traceability failure (lab §2.4).
6. **Realistic fault classes** to include: MCP container cold start of 1–2 minutes (stated in the lab PDF §2.2), timeouts, HTTP 5xx and 429, empty search results, paywalled or garbled scholarly content, the document-extraction tool rejecting inputs (also stated in the lab PDF), and malformed tool output.
7. **Cost of robustness.** Report retries, extra wall time and extra cost per degraded run.

---

## 7. Reproducibility

### 7.1 Run manifest (one JSON or YAML per run, written before the first model call and finalised at the end)
```yaml
run_id: uuid4
prereg_sha256: ...
split: S-heldout | Blind | ...
split_assignment_sha256: ...
doc: {id: ..., sha256_pdf: ..., sha256_extracted_text: ..., version: v1|v2}
condition: FULL | B0 | B0-$ | B-gen | A1 | A2 | A3 | A4 | A5 | H
agent:
  git_commit: ...            # repo state; dirty tree MUST be refused
  prompts_sha256: {system: ..., planner: ..., reviewer: ..., verifier: ...}
  prompts_bundle_sha256: ... # hash over all prompt files, sorted
  config_sha256: ...
model:
  provider: ...
  model_id: ...              # exact, dated/pinned version string as returned by the API
  params: {temperature: ..., top_p: ..., max_tokens: ..., reasoning_budget: ...}
  seed: ...                  # if the API supports it; else record "unsupported"
tools:
  - {name: mcp-internet-search, url_hash: ..., server_version: ..., backend: duckduckgo}
  - {name: mcp-research-information, ...}
  - {name: mcp-document-intelligence, ..., extractor: markitdown|docling, extractor_version: ...}
fault_injection: {profile: none|<id>, seed: ...}
grader: {matcher_model_id: ..., matcher_prompt_sha256: ..., grader_model_id: ..., rubric_sha256: ...}
env: {python: ..., os: ..., package_lock_sha256: ...}
timestamps: {start_utc: ..., end_utc: ..., per_step: "see transcript"}
usage: {input_tokens: ..., output_tokens: ..., cached_tokens: ..., tool_calls: ..., cost_usd: ..., price_table_date: ...}
outcome: completed_nominal | completed_degraded | aborted_graceful | crashed | timeout | budget_exceeded
outputs: {review_json_sha256: ..., review_pdf_sha256: ..., transcript_path: ..., web_snapshot_dir: ...}
```

> **Superseded (reconciliation 2026-10-02):** this manifest is replaced by `docs/REPRODUCIBILITY.md` §8 and `spec/finding.schema.json#/$defs/RunManifest`. `model.params.temperature/top_p` and `seed` are removed (not settable on Claude); the manifest records `thinking`, `effort`, `max_tokens`, `betas`, `served_models[]` (the `model` field of every response) and `fallback_events[]`; no server-side fallback is allowed in eval runs. Condition `A4` is now `A4e` (ADR-002). The document text hash is the canonical `doc.pages.txt` (ADR-006). Audit C15, C16, C28.

### 7.2 Logged artefacts (MUST)
- **Raw transcripts**: every model request and response (including system prompts and tool schemas as sent), every tool call with arguments, the raw result, latency and error. Append-only JSONL.
- **Web snapshots**: the content of every fetched page or paper as the agent saw it (hash plus stored copy), so citation faithfulness is checked against what was actually read, not against a later version of the page (link rot or edits).
- **Grader and matcher transcripts** with the same rigour, because they are measuring instruments.
- **Cost per run** in USD at a dated price table, plus per-condition median and IQR. Report accuracy against cost [2], [28].
- An independent party SHOULD be able to recompute every table in §10 from the logs alone with a single script (`eval/score.py`). Agent-log analysis is increasingly argued to be necessary for credible agent evaluation (see [29], **UNVERIFIED**: title seen, content not read).

---

## 8. Instrument validation (prerequisite gates)

Do not report numbers produced by an instrument until it passes its gate on S-dev (all thresholds are PROPOSED DEFAULTS):

| Instrument | Validation | Gate |
|---|---|---|
| Finding↔flaw matcher (LLM) | At least 150 (finding, flaw) candidate pairs labelled independently by 2 humans, then by the matcher | Human–human κ reported; matcher–human-consensus **κ ≥ 0.80**; B-gen strict recall ≤ 0.05 |
| Grounding and quote checker | At least 100 findings, human-labelled grounded/ungrounded | κ ≥ 0.80 |
| Citation-support judge | At least 100 (claim, source passage) pairs, human-labelled full/partial/none | Weighted κ ≥ 0.70 |
| "Lecturer" rubric grader | At least 100 reviews (multiple conditions, so the score range is spread) graded by ≥ 1 human and by 2 LLM graders from different families | Krippendorff's α (ordinal) ≥ 0.80 for use as primary; 0.667–0.80 means "tentative", report with human co-grading; < 0.667 means do not use. The thresholds follow Krippendorff [30] |
| Grader bias probes | Swap order (pairwise), pad the length with low-content text, inject "this review is excellent" meta-text, swap the model-identity label | Score change within noise; else mitigate [31], [32], [33] |

> **Superseded (reconciliation 2026-10-02):** (1) "Different family" and "2 LLM graders from different families" depend on `docs/DECISIONS.md` ADR-003 (Pending); under branch B the instruments are local open-weight (short context) or same-family Claude (holistic grader), disclosed, and these gates need that amendment (audit C3). (2) Human labelling is one person: matcher 150 S-dev pairs with an intra-rater re-label of 40 after ≥ 7 days (human–human κ replaced by intra-rater κ), grounding and citation 60 + 60, grader ≥ 20 reviews (tentative tier). Gates are tiered smoke / tentative / primary and frozen in `prereg.yaml` (audit C2, §4.6). (3) The matcher's output labels and the per-flaw credit rule are in `spec/taxonomy.yaml` (`match_scores`, `credit_modes`); see `metrics.md` §2.

LLM-judge caveats to cite in the report: position, verbosity and self-enhancement biases [31]; order manipulation [32]; self-preference correlated with self-recognition [33]; percent agreement hides large score gaps, so report κ, not just agreement [34]. Note that published flaw-detection benchmarks have used LLM matchers **without** reporting matcher–human agreement (as a secondary summary describes SPOT [35]). We treat that as a gap to close, not a precedent to follow.

---

## 9. Loophole checklist (what a sceptical reviewer will look for)

Each item gives the loophole, then the **control**, then the **evidence that must appear in the report**.

**A. Information leakage**
1. **L1 Agent can read the answer key** (same repo, file tool, memory store, web search finding the public repo). Control: R2 and R3 (encrypted keys, sandbox allow-list, domain blocklist). Evidence: runtime access scan = 0 hits.
2. **L2 Prompts or few-shots contain eval-doc specifics** (tuning on the test). Control: R1 and R5. Evidence: distinctive-term grep, 13-gram overlap = 0, canary scan clean.
3. **L3 Held-out peeking** (repeated held-out evaluations steer development). Control: access budget and log [5]. Evidence: access log with count.
4. **L4 The matcher or judge sees the ground truth and "reads it into" vague findings.** Control: strict `core_insight` requirement, 1:1 matching, matcher blind to condition, matcher validated (κ ≥ 0.80), B-gen floor ≈ 0. Evidence: matcher validation table and B-gen row.
5. **L5 The holistic rubric grader sees the answer key** and grades by key overlap, which double-counts detection and turns "quality" into recall. Control: the rubric grader is key-blind; detection is scored only by the matcher. Evidence: grader prompt hash and content audit.
6. **L6 Grader shares prompts or rubric with the agent** (agent optimises to the grader's wording; rubric exemplars copied into the agent). Control: R4; n-gram overlap between agent prompts and private grader artefacts reported. Evidence: overlap score.
7. **L7 Pretraining contamination**: the real SIT doc or public design docs may be in model training data, and synthetic docs written by the agent's own model family share its "style" of flaws. Control: R6, Tier-2 by another family or humans, paraphrase probe. Evidence: probe results.

**B. Dataset construction**
8. **L8 Shared template**: synthetic docs share structure, so the agent learns where flaws live (e.g. always in "Assumptions", always marked "TBD", numbers off by exactly 10×). Control: several generators and templates, randomised flaw positions and surface forms, split by template family, template-tell probe [16]. Evidence: probe accuracy vs chance.
9. **L9 Planted flaws too obvious** (signposted, contradicting the very next sentence). Control: difficulty calibration, i.e. pilot with B0 and drop or harden flaws that B0 detects in 3 of 3 runs. Also apply a FLAWS-style filter: discard plants that the inserting model trivially re-finds [36]. Evidence: distribution of B0 detection rates per flaw.
10. **L10 Planted flaws unrealistic** (not the kind real design reviews catch). Control: build the taxonomy and exemplars from real review defects, have humans rate realism (1–5) for a sample, use the Blind split and the expert ceiling H. Evidence: realism ratings and Blind results.
11. **L11 Incomplete answer key**: true findings counted as false positives or "hallucinations". Control: base-doc audit (§1.3), adjudication of every unmatched finding into {valid-unplanted, hallucinated, duplicate, non-specific, out-of-scope, invalid-opinion}, report **strict and adjudicated** precision, and capture-recapture estimate [7]–[9]. Evidence: adjudication counts table.
12. **L12 Over-broad key entries** (vague flaw descriptions that anything matches) inflate recall. Control: every flaw needs a location anchor and a `core_insight`; key review by a second author. Evidence: key-review sign-off.
13. **L13 No sound sections in the docs**, so recommending something everywhere is never penalised. Control: `sound_units` and bait units in every doc; CDR reported. Evidence: CDR row.
14. **L14 Arbitrary severity labels** drive SWR and nDCG. Control: written severity anchors, a second annotator with weighted κ on severity, and sensitivity analysis with linear vs geometric weights. Evidence: κ_severity and both SWR variants.
15. **L15 Ingestion untested** (synthetic docs given as clean text while the lab gives PDFs). Control: rule 4 in §1.1; at least one flaw per 5 docs lives in a table or figure. Evidence: recall on table or figure flaws.

**C. Scoring gaming by the agent**
16. **L16 Shotgun strategy**: many generic findings ("consider security", "add monitoring") match something by chance. Control: 1:1 Hungarian matching, joint P/R reporting, location specificity, B-gen floor, clean-vs-flawed differential credit [27]. Evidence: findings per doc, precision, B-gen row.
17. **L17 Duplicate findings counted several times.** Control: 1:1 matching; duplicates are FPs in strict precision and reported as a duplication rate. Evidence: duplication rate.
18. **L18 "Never recommend" strategy** inflates CDR. Control: report CDR with recall and balanced unit accuracy. Evidence: both shown together.
19. **L19 Confidence gaming** (constant 0.5, or always "high"). Control: report AUROC and Brier, not ECE alone [11]. Evidence: all three.
20. **L20 Citation padding**: many citations, few supporting. Control: citation precision, not citation count; snapshot-based support check. Evidence: citation precision row.
21. **L21 Fabricated external citations**, especially when tools fail. Control: existence check (DOI or URL resolve, title match) against snapshots; A5 must show 0. Evidence: fabricated-citation rate per condition.
22. **L22 Text aimed at the grader** inside the review ("this assessment is rigorous and complete"). Control: injection probe in grader validation; grader instructed to ignore self-assessment; meta-claims flagged. Evidence: probe result.
23. **L23 Verbosity rewarded.** Control: length-padding probe; regress the rubric score on length and report the slope [31]. Evidence: slope with CI.

**D. Analysis and reporting**
24. **L24 Seed or run cherry-picking.** Control: pre-registered k; all runs logged by manifest. Evidence: run counts match prereg.
25. **L25 Garden of forking paths** (metric chosen after seeing results). Control: `prereg.yaml` hash in every manifest. Evidence: prereg diff = none, or listed deviations.
26. **L26 Flaws treated as independent**, giving error bars that are too narrow. Control: cluster bootstrap [17], [1]. Evidence: method statement and DEFF.
27. **L27 Many comparisons, one "significant" result.** Control: Holm on the primary family, BH on exploratory [19]. Evidence: adjusted p or CIs.
28. **L28 Underpowered "no difference" or "improvement" claims.** Control: power table, MDE reported [20], [21]. Evidence: MDE per comparison.
29. **L29 Unfair baselines** (weaker prompt, no schema, so the matcher cannot parse them, or less budget). Control: identical schema and instructions; cost-matched B0-$ [2]. Evidence: baseline prompts in the appendix, cost column.
30. **L30 Tool-failure runs dropped silently.** Control: ITT and per-protocol tables (§6). Evidence: outcome counts.
31. **L31 Silent model drift** (API model updated between conditions). Control: pinned versions, interleaved scheduling, model id recorded per call. Evidence: manifest model ids are consistent.
32. **L32 Dev→blind gap misread** (difficulty shift taken as overfitting, or overfitting hidden by an easier blind set). Control: difference-in-differences against B0 [23]. Evidence: DiD row.
33. **L33 Partial matches counted as full.** Control: strict counts score-3 matches only; lenient (score ≥ 2) is reported separately. Evidence: both.
34. **L34 Non-independent human rater** (the prompt author grades their own agent). Control: independent rater, blinded to condition and to the agent's identity. Evidence: rater statement.
35. **L35 Grader self-preference** (grader from the agent's model family). Control: grader family ≠ agent family; a second grader from a third family; report the cross-grader α [33]. Evidence: grader agreement table. *(Superseded, reconciliation 2026-10-02: conditional on `docs/DECISIONS.md` ADR-003, Pending; under branch B the grader is same-family, disclosed, mitigated by blinding, template normalisation and paraphrase test V9, and its numbers are labelled tentative. Audit C3.)*
36. **L36 Grader nondeterminism hidden.** Control: grade each item 3 times, report grader SD, use the median. Evidence: grader variance.
37. **L37 Citation checking against live pages** (link rot or edits cause false "unsupported"; later content causes false "supported"). Control: check against run-time snapshots; report "unreachable" separately. Evidence: snapshot hashes.
38. **L38 Construct validity**: the rubric measures what is easy to measure, not the lab criteria. Control: rubric items mapped to lab sections (§0.1), with expert review of the mapping. Evidence: mapping table.
39. **L39 The demo artefact family is over-represented in tuning** (the SIT doc and its v2). Control: R5; report results on Real-dev separately from all generalisation claims. Evidence: separate section.
40. **L40 Stopping rule gamed by a budget cap**: the agent "knows when to stop" only because a hard cap stops it. Control: report the share of runs that end by cap vs by the agent's own decision, and the overrun metric. Evidence: stop-reason counts.

---

## 10. Minimal results-table template (the final report MUST contain all of these)

**Table 1. Main results (Blind split; repeat for S-heldout).** Values are mean [95% cluster-bootstrap CI]. n_docs = …, k runs per doc = …, flaws = …

| Condition | Recall | Precision (strict / adj.) | F1 (adj.) | SWR | Critical recall | nDCG@k | HFR ↓ | Citation precision | Fabricated citations ↓ | Rec. justification | CDR | Bal. unit acc. | ECE ↓ / AUROC | Cost $/run (median) | Outcome: completed / degraded / failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FULL | | | | | | | | | | | | | | | |
| B0 single-call | | | | | | | | | | | | | | | |
| B0-$ cost-matched | | | | | | | | | | | | | | | |
| B-gen floor | | | | | | | | | | | | | | | |
| A1 no-research | | | | | | | | | | | | | | | |
| A2 no-iteration | | | | | | | | | | | | | | | |
| A3 no-verification | | | | | | | | | | | | | | | |
| A4e effort-low *(was A4 alt. model; ADR-002)* | | | | | | | | | | | | | | | |
| A5 tools-disabled | | | | | | | | | | | | | | | |
| H human expert (subset) | | | | | | | | | | | | | | | |

**Table 2. Paired differences vs FULL** (Δ [95% CI], Holm-adjusted p, MDE at this n) for each primary metric.

**Table 3. Per-category detection** (FULL and B0): rows = taxonomy categories plus `OTHER`; columns = #flaws, recall, precision (by agent label), F1, category-label accuracy. Exploratory, BH-adjusted.

**Table 4. Generalisation and overfitting**

| Metric | S-dev | S-heldout | Blind | OOD | Δ dev→blind (FULL) | Δ dev→blind (B0) | DiD | Paraphrase Δ | Reorder Δ |
|---|---|---|---|---|---|---|---|---|---|

**Table 5. v1→v2 re-review**: resolved acknowledgement, stale-finding rate, persisted recall, new-flaw recall, approved-decision violation rate, each for fresh-session and with-v1-context variants.

**Table 6. Instrument validity**: matcher κ vs humans, grounding-checker κ, citation-judge weighted κ, rubric grader: human–LLM α, LLM–LLM α (different families), human–human α, Bland–Altman bias [LoA], bias-probe outcomes.

**Table 7. Robustness**: per fault profile, with ITT and per-protocol recall, HFR, fabricated-citation rate, disclosure rate, extra cost and time.

**Table 8. Leakage and integrity audit**: distinctive-term grep hits, max 13-gram overlap, canary hits, runtime eval-path or own-repo access, held-out access count, template-tell probe accuracy vs chance, prereg deviations.

**Table 9. Efficiency and stopping**: tool calls, tokens, cost, wall time (median, IQR), research yield, overrun steps, stop reason (agent decision / cap / error).

**Table 10. Adjudication of unmatched findings**: counts of valid-unplanted, hallucinated, duplicate, non-specific, out-of-scope and invalid-opinion, plus the capture-recapture estimate of residual natural flaws.

---

## 11. Known limitations of this spec
- Synthetic flaws measure detection of **our** notion of a flaw. Blind and expert-ceiling results are the only partial check on external validity.
- An LLM matcher, even when validated, is a model of human judgement. Report its κ next to every number it produces.
- Calibration requires the agent to emit numeric confidence. If it emits only verbal levels, report per-level accuracy and monotonicity instead of ECE.
- Sample sizes in §4b assume pilot-estimated variances. Recompute after the S-dev pilot.

---

## 12. References
Verified in this session by web search unless marked otherwise.

1. E. Miller (2024). *Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations.* arXiv:2411.00640. https://arxiv.org/abs/2411.00640
2. S. Kapoor, B. Stroebl, Z. Siegel, N. Nadgir, A. Narayanan (2024). *AI Agents That Matter.* arXiv:2407.01502. https://arxiv.org/abs/2407.01502
3. S. Kapoor, A. Narayanan (2023). *Leakage and the reproducibility crisis in machine-learning-based science.* Patterns. https://www.cell.com/patterns/fulltext/S2666-3899(23)00159-9
4. J. Pineau et al. (2021). *Improving Reproducibility in Machine Learning Research (NeurIPS 2019 Reproducibility Program).* JMLR 22. https://www.jmlr.org/papers/v22/20-303.html
5. C. Dwork, V. Feldman, M. Hardt, T. Pitassi, O. Reingold, A. Roth (2015). *The reusable holdout: Preserving validity in adaptive data analysis.* Science 349(6248):636–638. https://www.science.org/doi/10.1126/science.aaa9375
6. BIG-bench canary string documentation. https://github.com/google/BIG-bench/blob/main/docs/doc.md ; paper arXiv:2206.04615 https://arxiv.org/abs/2206.04615
7. S. Eick, C. Loader, D. Long, L. Votta, S. Vander Wiel (1992). *Estimating software fault content before coding.* ICSE '92. Context and review: Petersson, Thelin, Runeson, Wohlin (2004), *Capture–recapture in software inspections after 10 years research*, JSS. https://www.sciencedirect.com/science/article/abs/pii/S0164121203000906
8. L. Briand, K. El Emam, B. Freimut, O. Laitenberger (1997/2000). *Quantitative evaluation of capture-recapture models to control software inspections* / *A comprehensive evaluation of capture-recapture models for estimating software defect content.* https://www.researchgate.net/publication/3188084_A_Comprehensive_Evaluation_of_Capture-Recapture_Models_for_Estimating_Software_Defect_Content
9. H. D. Mills (1972). *On the Statistical Validation of Computer Programs.* IBM FSD (fault or error seeding). Secondary summary: https://en.wikipedia.org/wiki/Bebugging (primary not retrieved, **UNVERIFIED** beyond the secondary source)
10. T. Gao, H. Yen, J. Yu, D. Chen (2023). *Enabling Large Language Models to Generate Text with Citations* (ALCE; citation recall and precision). EMNLP. https://aclanthology.org/2023.emnlp-main.398/
11. C. Guo, G. Pleiss, Y. Sun, K. Weinberger (2017). *On Calibration of Modern Neural Networks* (ECE). arXiv:1706.04599. https://arxiv.org/abs/1706.04599
12. K. Tian et al. (2023). *Just Ask for Calibration* (verbalised confidence). EMNLP. https://aclanthology.org/2023.emnlp-main.330/
13. S. Yao, N. Shinn, P. Razavi, K. Narasimhan (2024). *τ-bench* (pass^k). arXiv:2406.12045. https://arxiv.org/abs/2406.12045
14. T. Brown et al. (2020). *Language Models are Few-Shot Learners* (13-gram contamination analysis). NeurIPS. https://proceedings.neurips.cc/paper/2020/file/1457c0d6bfcb4967418bfb8ac142f64a-Paper.pdf
15. H. Zhang et al. (2024). *A Careful Examination of Large Language Model Performance on Grade School Arithmetic* (GSM1k). arXiv:2405.00332. https://arxiv.org/abs/2405.00332
16. S. Gururangan et al. (2018). *Annotation Artifacts in Natural Language Inference Data.* NAACL. https://aclanthology.org/N18-2017/
17. C. Field, A. Welsh (2007). *Bootstrapping clustered data.* JRSS-B 69(3):369–390. https://doi.org/10.1111/j.1467-9868.2007.00593.x
18. R. Dror, G. Baumer, S. Shlomov, R. Reichart (2018). *The Hitchhiker's Guide to Testing Statistical Significance in NLP.* ACL. https://aclanthology.org/P18-1128/
19. Y. Benjamini, Y. Hochberg (1995). *Controlling the false discovery rate.* JRSS-B 57(1):289–300. https://doi.org/10.1111/j.2517-6161.1995.tb02031.x . Holm (1979), *A simple sequentially rejective multiple test procedure*, Scand. J. Stat. 6(2):65–70 (standard reference, not re-verified this session).
20. D. Card et al. (2020). *With Little Power Comes Great Responsibility.* EMNLP. https://aclanthology.org/2020.emnlp-main.745/
21. R. J. Connor (1987). *Sample size for testing differences in proportions for the paired-sample design.* Biometrics 43(1):207–211. https://www.semanticscholar.org/paper/Sample-size-for-testing-differences-in-proportions-Connor/1a67898e70b76266809ef150e221e40b5d05a8e0
22. J. Dodge et al. (2019). *Show Your Work: Improved Reporting of Experimental Results.* EMNLP. https://aclanthology.org/D19-1224/
23. B. Recht, R. Roelofs, L. Schmidt, V. Shankar (2019). *Do ImageNet Classifiers Generalize to ImageNet?* arXiv:1902.10811. https://arxiv.org/abs/1902.10811
24. M. T. Ribeiro, T. Wu, C. Guestrin, S. Singh (2020). *Beyond Accuracy: Behavioral Testing of NLP Models with CheckList.* ACL. https://aclanthology.org/2020.acl-main.442/
25. N. F. Liu et al. (2024). *Lost in the Middle: How Language Models Use Long Contexts.* TACL. https://aclanthology.org/2024.tacl-1.9/
26. M. Sclar, Y. Choi, Y. Tsvetkov, A. Suhr (2024). *Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design.* ICLR. https://arxiv.org/abs/2310.11324
27. N. Dycke, I. Gurevych (2026). *Automatic Reviewers Fail to Detect Faulty Reasoning in Research Papers: A New Counterfactual Evaluation Framework.* TACL 14:465–488. https://aclanthology.org/2026.tacl-1.22/
28. S. Kapoor et al. (2025). *Holistic Agent Leaderboard: The Missing Infrastructure for AI Agent Evaluation.* arXiv:2510.11977. https://arxiv.org/abs/2510.11977
29. *Log analysis is necessary for credible evaluation of AI agents* (2026). arXiv:2605.08545. https://arxiv.org/abs/2605.08545 (**UNVERIFIED**: title seen in search results only)
30. K. Krippendorff (2004). *Reliability in Content Analysis: Some Common Misconceptions and Recommendations.* Human Communication Research 30(3):411–433 (α ≥ .800 reliable; ≥ .667 tentative). https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1468-2958.2004.tb00738.x ; A. Hayes, K. Krippendorff (2007), *Answering the Call for a Standard Reliability Measure for Coding Data*, CMM 1:77–89. https://doi.org/10.1080/19312450709336664
31. L. Zheng et al. (2023). *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* NeurIPS. https://arxiv.org/abs/2306.05685
32. P. Wang et al. (2023). *Large Language Models are not Fair Evaluators.* arXiv:2305.17926. https://arxiv.org/abs/2305.17926
33. A. Panickssery, S. R. Bowman, et al. (2024). *LLM Evaluators Recognize and Favor Their Own Generations.* NeurIPS. https://arxiv.org/abs/2404.13076
34. A. S. Thakur et al. (2024). *Judging the Judges: Evaluating Alignment and Vulnerabilities in LLMs-as-Judges.* arXiv:2406.12624. https://arxiv.org/abs/2406.12624
35. (2025; authors not verified). *When AI Co-Scientists Fail: SPOT, a Benchmark for Automated Verification of Scientific Research.* arXiv:2505.11855. https://arxiv.org/abs/2505.11855 (the claim that matcher accuracy was not validated comes from a secondary summary, **UNVERIFIED** against the paper)
36. *FLAWS: A Benchmark for Error Identification and Localization in Scientific Papers* (2025). arXiv:2511.21843. https://arxiv.org/abs/2511.21843 ; code https://github.com/VijayBalajiN/FLAWS
37. R. Liu, N. Shah (2023). *ReviewerGPT? An Exploratory Study on Using Large Language Models for Paper Reviewing* (deliberately inserted errors; precedent for the planted-flaw paradigm). arXiv:2306.00622. https://arxiv.org/abs/2306.00622
38. W. Liang et al. (2023). *Can large language models provide useful feedback on research papers?* (extract-then-semantic-match pipeline for comparing LLM and human review comments). arXiv:2310.01783. https://arxiv.org/abs/2310.01783
39. M. D'Arcy, T. Hope, L. Birnbaum, D. Downey (2024). *MARG: Multi-Agent Review Generation for Scientific Papers.* arXiv:2401.04259. https://arxiv.org/abs/2401.04259
40. H. Rashkin et al. (2021/2023). *Measuring Attribution in Natural Language Generation Models* (AIS). arXiv:2112.12870. https://arxiv.org/abs/2112.12870
41. J. Cohen (1968). *Weighted kappa.* Psychological Bulletin 70:213–220. https://doi.org/10.1037/h0026256 ; J. Cohen (1960), *A coefficient of agreement for nominal scales*, EPM 20:37–46 (standard, not re-verified).
42. A. Feinstein, D. Cicchetti (1990). *High agreement but low kappa: I. The problems of two paradoxes.* J Clin Epidemiol 43(6):543–549; Gwet AC1 as a prevalence-robust alternative. https://www.semanticscholar.org/paper/High-agreement-but-low-kappa:-II.-Resolving-the-Cicchetti-Feinstein/3fc791c02fbbb89a1a6c772a2c084773cfc39468
43. K. Järvelin, J. Kekäläinen (2002). *Cumulated gain-based evaluation of IR techniques* (nDCG). ACM TOIS 20(4):422–446. https://doi.org/10.1145/582415.582418

Standard statistical references used but not re-verified this session: Efron (1979) bootstrap; Wilson (1927) score interval; McNemar (1947); Kuhn (1955) Hungarian method; Brier (1950); Bland & Altman (1986); Chapman (1951) capture-recapture estimator; Sim & Wright (2005) κ sample size.
