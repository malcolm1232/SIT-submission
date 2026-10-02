# Research audit: is the package research-grade?

Audit date: 2026-10-02. Scope: the six research notes under `research/` (README plus companion files, all read in full), a skim of the five eval items under `eval/`, and the lab brief (`AI_Engineer_Lab_Exercise.pdf`, pp. 1-9). The eval documents themselves were not fact-checked; another auditor covers that.

**Verdict.** Each note is strong in isolation. As a package it is not yet research-grade, for four reasons:

1. The notes use six answer-key formats, five matching rules, four severity scales, five category taxonomies and three verdict vocabularies. No headline number can be computed until these are reduced to one.
2. The "blind" set is not blind. Developers can read it, it was briefed with knowledge of the eval design, and it shares the synthetic set's template and its fixed count of 14 flaws.
3. The judge-independence requirements (different model family for the matcher, the judges and the grader) have no plan that works if only an Anthropic key is available.
4. The human-labelling demands (roughly 600 or more labelled items, two or more raters) cannot be met by one person, and no note sizes them.

None of this is fatal. All of it must be settled before code is written, because it fixes the agent's output schema.

Conventions: file paths are relative to `research/` unless they start with `eval/`. "§" means a section of the cited file. "Lab §x" means the lab brief.

---

## 1. Cross-document consistency

### 1.1 Reconciliation table

Each row lists the conflict, where it occurs, and one recommended resolution. "Canonical" means a single file should own the decision (see §5).

| # | Conflict | Where | Recommended resolution |
|---|---|---|---|
| C1 | **Rubric scale.** 0-4 anchored over 10 dimensions, vs "0-3 scale", vs RevUtil 5-point aspects, vs a generic "1..K". | `grading/README.md` §3.2; `models/README.md` §4 item 3; `kaggle/README.md` Recommendation 1; `methodology/metrics.md` §11 | **Keep grading's 0-4** (it is the only fully anchored rubric, and its worked examples and V-tests already use it). Amend models §4.3. Fold RevUtil's four aspects into the Pass A per-finding booleans that already exist (`issue/rationale/evidence/expected_benefit/objective_link`). Do not add a second rubric. |
| C2 | **Grader-validity gate and sample size.** QWK ≥ 0.60 over 50 ratings from 5 items, vs Krippendorff α ≥ 0.80 over ≥ 100 reviews plus 2 LLM graders from different families, vs 10-15 reviews by 2 humans with weighted κ, vs QWK. | `grading/README.md` §7; `methodology/README.md` §8 and `metrics.md` §11; `models/README.md` §5 item 4 and §6 E5; `kaggle/README.md` Rec. 7 | Use three named tiers in `prereg.yaml`. **Smoke:** n = 5, grading §7 targets. **Tentative:** n ≥ 20, ordinal α ≥ 0.667 with bootstrap CI. **Primary:** methodology §8 gate. Report ordinal α and QWK together. Tie the wording of every claim to the tier reached. Expect tentative at best (see §4.6). |
| C3 | **Grader and judge model family.** Primary grader is GPT-6.1 Sol or Gemini 3.1 Pro, with Sonnet 5.5 as an in-family control. Grading says "differs where possible, else run paraphrase test V9". Methodology says MUST use a different family for the matcher, adjudicator, G3 premise judge and citation judge, plus a third family for the grader. | `models/README.md` §1, §4.1-2, §5; `grading/README.md` §6.2; `methodology/README.md` §3.1 R4, L35; `metrics.md` §2.3 step 2, §5.1 G3, §5.2 | Write **one instrument-routing table** with a branch for each set of available keys (§4.4 below gives the Anthropic-only branch). Every instrument gets a named model, and the same-family cases are disclosed. |
| C4 | **Two competing recall instruments.** Grading's Pass B key alignment (full / partial / none, `recall_high` and `recall_all` in the final report), vs methodology's 0-3 Hungarian matcher. | `grading/grader_prompt.md` §3.2 step 5, §5.3; `grading/README.md` §3.2 D3 anchor "key-aware: ≥ 80 % of key items"; `methodology/metrics.md` §2 | **The methodology matcher is the only source of recall.** Grading's key-aware mode stays diagnostic, is never reported as recall, and is removed from the D3 anchor. |
| C5 | **Five different matching rules** in the item READMEs. clinical: "location + core claims in must_mention; partial credit via distractor_notes". payments: "by substance". lakehouse: "section/req + at least the **first two** must_mention points". blind A: "meets `credit_requires`". blind B: "every item in `credit_requires`; one-level severity disagreement OK". Methodology: one `core_insight` + location compatibility, strict = score 3. | `eval/*/*/README.md`; `methodology/metrics.md` §2.1-2.2 | Adopt **methodology's rule** for every item. Derive one `core_insight` (plus an optional `required_points[]`) per flaw from `what_a_correct_finding_must_mention` or `credit_requires`, and have a second person review it (L12). Delete the per-item rules from the item READMEs, or mark them superseded. The "first two points" rule depends on list order and is arbitrary. |
| C6 | **Severity scales.** Agent and methodology use 4 levels (critical/high/medium/low; weights 8/4/2/1). The synthetic keys use 3 (critical/major/minor). Blind A uses capitalised 4 levels. Blind B uses 4 levels but never assigns low. Grading uses materiality (high/medium/low). | `methodology/metrics.md` §0; `eval/synthetic/*/answer_key.json`; `eval/blind/*/answer_key.json`; `grading/grader_prompt.md` §5.1 | Use the 4-level scale as canonical. **Pre-register a mapping** (recommended: major→high, minor→low; sensitivity variant minor→medium). Report SWR under both mappings and both weight schemes (L14). Materiality stays a grader-only concept. Document how it maps to severity. |
| C7 | **Category taxonomy (five of them).** (a) Methodology's 8 codes: RISK, GAP, AMBIGUITY, UNRESOLVED_ASSUMPTION, INCONSISTENCY, UNSUPPORTED_OR_INCORRECT_CLAIM, VALIDATION_NEED, OTHER. (b) The agent `kind` enum: assumption, inconsistency, incorrect_claim, … plus strength. (c) The synthetic defect-type labels: internal_contradiction, unjustified_quantitative_claim, … (d) Blind A's 11 domain categories. (e) Blind B's 14 free-text labels. Grading also has a sixth enum (Pass A category; key format `strength\|risk\|gap\|…`). The synthetic keys spell the same category two ways: `decision_depends_on_pending_backlog` (clinical) and `decision_depends_on_pending_item` (others). | `methodology/README.md` §1.2; `metrics.md` §1; `eval/*/*/answer_key.json`; `grading/grader_prompt.md` §5.1, §6 | Use **two orthogonal axes** in one `taxonomy.yaml`. **Axis 1, lab §2.3 review category** (strength, risk, gap, ambiguity, unresolved_assumption, validation_need): drives D3 and the agent's `kind`. **Axis 2, defect mechanism** (the synthetic set's 8 labels, normalised, plus OTHER): drives the per-category recall table and the taxonomy-dependence check. Map every existing label onto both axes. Domain labels stay as free `tags`. Fix the backlog/item spelling. |
| C8 | **Triage / action enum.** Grading has refinement / investigation / prototyping / testing / governance / mixed / none. Methodology's `action_type` **omits "testing"**, although lab §3.2 names it. Robustness has BEH-16 `remedy_type` and ADV-14 "validation/prototype". No eval key has a gold triage field, except grading's illustrative key. | `grading/grader_prompt.md` §5.1; `methodology/metrics.md` §1, §6.1; `robustness/scenarios.md` BEH-16, ADV-14 | Use **grading's enum**, which follows lab §3.2 word for word. Add `expected_triage` to every key. Until then, BEH-16 and the action-type accuracy metric are **uncomputable**. Mark them BLOCKED. |
| C9 | **Verdict vocabulary.** fit / fit_with_conditions / not_fit, vs yes / partly / no, vs `fit_with_refinements`. | `grading/README.md` §3.2 D2; `methodology/metrics.md` §1; `robustness/README.md` §6.3 | Use grading's three labels. |
| C10 | **Provenance tag (lab §4.2).** `source_type: DOC\|EXTERNAL`, vs `source: doc\|external\|inference`, vs `source_type: design\|external`. | `methodology/metrics.md` §1, §5.2; `robustness/scenarios.md` BEH-17; `grading/README.md` §9(a) | Use `doc \| external \| inference`. Inference is a real third class, and without it reasoning gets mislabelled as doc content. |
| C11 | **How the model cites external evidence.** Methodology's schema lets the model write a URL or DOI in `evidence.ref`. Robustness says "The LLM cites ledger IDs; the renderer turns IDs into URLs. The LLM never writes URLs." | `methodology/metrics.md` §1, §5.2 step 1; `robustness/README.md` §10 item 3, BEH-04 | **Use ledger IDs.** A fabricated citation then becomes impossible by construction. Keep methodology's existence checks, because they still catch renderer bugs and free-text URLs (A5, L21). Add `read_before_cite` from the ledger. |
| C12 | **Stop-reason enum.** sufficient_evidence / budget / tool_failure / other, vs budget / no_marginal_gain / deadline, vs agent decision / cap / error. | `methodology/metrics.md` §1, §10; `robustness/scenarios.md` BEH-01, INF-17; `methodology/README.md` L40 | Use the union: `sufficient_evidence, no_marginal_gain, budget_tool_calls, budget_tokens, deadline, tool_failure, error`. L40 groups these into decision / cap / error. |
| C13 | **Doc anchoring mechanism.** Models recommends Claude native citations (`page_location`), noting they **cannot be combined with structured outputs** in one call. Frameworks types findings with `messages.parse`. Robustness requires verbatim quote + page, checked by fuzzy match. | `models/README.md` §2 feature notes; `frameworks/README.md` Recommendation; `robustness/README.md` §10 item 4, INV-04 | **Quote + page + section inside the structured output,** checked against one canonical page-marked text (see C14). Native citations are optional in the analysis calls only. Never rely on them for the scored output. |
| C14 | **PDF ingestion path.** Frameworks: native document block, pypdf fallback. Models: native PDF. Robustness: local-first pdfplumber/PyMuPDF, then OCR. Grading: `pdftotext -layout` with `[[PAGE n]]`. Methodology G1 normalises "PDF extraction noise". | `frameworks/README.md` §4; `models/README.md` §1; `robustness/README.md` §10 item 9, INP-01; `grading/README.md` §5; `methodology/metrics.md` §5.1 | **Send the native PDF block to the model, and produce one canonical page-marked text with one extractor (pinned version).** The agent's verify step, the matcher's G1/G2, the grader and the robustness oracles all read that same text. Three different extractors would make quote-existence noise an artefact of the pipeline. |
| C15 | **Sampling / determinism.** Frameworks and models: current Claude models take no `temperature` (removed in SDK 1.x). Methodology: "k = 3 at the production temperature", and the manifest has `temperature/top_p/seed`. Robustness: L1 "temperature 0 where supported", BEH-15 "fixed seeds". Grading: "temperature 0.3". | `frameworks/README.md` Decision item 4; `models/README.md` §4.8; `methodology/README.md` §4b.2, §7.1; `robustness/README.md` §3, BEH-15; `grading/grader_prompt.md` §1 | Record `sampling: provider-default (not settable)` for Claude. Replace `temperature` and `seed` in the manifest with `thinking`, `effort`, `max_tokens` and `betas`. Rewrite BEH-15 so it measures stability with no seed assumption. Set temperature for the grader only if it is a non-Claude model that accepts it. |
| C16 | **Beta features on the critical path.** Frameworks: avoid betas (tool_runner, MCP connector). Models' snippet uses `client.beta.messages.stream` with the `server-side-fallback-2026-07-01` beta and `fallbacks: "default"`, which can **silently change the serving model**. That breaks L31 (model drift) and ablation A4. | `frameworks/README.md` §8; `models/README.md` §1, §7 | **No server-side fallback in eval runs.** Do the fallback client-side in the LLM gateway, log the actual model per call (robustness LLM-03 already asks for this), and make it opt-in for the demo. Check whether streaming and adaptive thinking need the beta namespace at all. |
| C17 | **Checkpoint / resume.** Frameworks lists "pause/resume across processes" as a trigger to **switch to LangGraph**. Robustness makes resume a P0 requirement (OPS-04, NET-01, BEH-25). | `frameworks/README.md` "Conditions that would change this"; `robustness/scenarios.md` OPS-04, NET-01 | Keep the custom loop, and build per-stage JSON checkpoints (about 60 LOC, as frameworks §6 already concedes). Change the trigger condition to "durable human-in-the-loop interrupts". Otherwise the two notes jointly argue for a switch. |
| C18 | **Plan-then-execute vs adaptive research.** Robustness: "doc and tool content never alter the plan's action set". Frameworks: a model-driven research tool loop. Lab §4.3: "adapt as new information emerges". Methodology ablation A2 (iteration) assumes adaptation. | `robustness/README.md` §1.2, §10 item 10; `frameworks/README.md` Decision item 2; Lab §4.3 | Fix the action **types** and the URL policy (fetch only URLs from search results or doc references; ADV-04 already says this). Let queries and follow-up questions adapt. State this explicitly. Otherwise the security control and the lab requirement contradict each other. |
| C19 | **Use of the blind set.** Methodology: Blind is read by nobody and evaluated once, after pre-registration. Robustness: the DEMO-05 rehearsal protocol runs "5 runs on **3** unseen docs from `eval/blind`" (only 2 exist), and OVF-12 runs on it whenever a prompt changes. Grading: internal target "≥ 80 … on held-out artefacts", which implies repeated grading. | `methodology/README.md` §1.1; `robustness/README.md` §6.3, §7.2, §7.3; `scenarios.md` DEMO-05, OVF-12; `grading/README.md` §4.4 | Treat Blind as **sealed, single use**. Run DEMO-05 rehearsals on a **separate rehearsal pool** (S-heldout or new docs). OVF-12 runs once, at the final evaluation, not at every prompt change. |
| C20 | **Overfitting gap test.** OVF-12 passes if the recall gap is ≤ 15 pp. Methodology says the gap must be judged by difference-in-differences against B0, and that with about 15 blind docs only a gap of 0.15 or more is detectable. With 2 blind docs (28 flaws), the 95 % CI on a single recall is about ±0.18 before clustering. | `robustness/scenarios.md` OVF-12; `methodology/README.md` §4b.6, §5 | Drop the pass/fail threshold. OVF-12 reports the gap, the DiD and the CI, as methodology specifies. |
| C21 | **Sample-size claims.** Methodology: about 33 docs (8 flaws each) for a 10-point recall difference, about 15 blind docs, ≥ 100 doubly graded reviews, ≥ 150 matcher pairs, H on ≥ 10 docs. Models: 31 docs for E1; "10-20 documents we can realistically produce"; 10-15 human-anchor reviews. Grading: 5, extending to 15-20. **Actual: 3 synthetic + 2 blind = 5 docs, 70 v1 flaws + 3 v2 regressions.** | `methodology/README.md` §4b.6-7, §8; `models/README.md` §6 "Sample size"; `grading/README.md` §7 | Put the **achieved n and the MDE at that n** in `prereg.yaml`. Label all ablation and per-category results exploratory. Recompute DEFF with the real m = 14 (ρ = 0.1 gives DEFF = 2.3, not 1.7). |
| C22 | **Fully sound control docs.** Methodology: SHOULD be ≥ 10 % of every split. Robustness: INP-28 `gold_clean.pdf` is **P0**, and BEH-08 needs it. **None exist.** | `methodology/README.md` §1.2; `robustness/scenarios.md` INP-28, BEH-08 | Author at least 2 (P1). Until then INP-28 is BLOCKED and the "no change needed" claim (lab §1.4) is untested at doc level. |
| C23 | **Live-modification time target.** "Under 5 minutes", vs ≤ 3 min (DEMO-01/02/08) and ≤ 5 min (DEMO-10). | `grading/README.md` §9(d); `robustness/scenarios.md` DEMO-* | Use ≤ 3 min for config changes and ≤ 5 min for code changes. Replace frameworks' estimated line counts (§3, "not measured") with rehearsal timings. |
| C24 | **Cross-vendor model swap.** Robustness DEMO-04 (P0) says "another Claude tier, **or another provider**". Frameworks: cross-vendor is a "prepared fallback, not a live-demo trick", and only the Anthropic adapter is built up front. Methodology A4 asks for a "different backbone model". | `robustness/scenarios.md` DEMO-04; `frameworks/README.md` Decision; `methodology/README.md` §4 A4 | DEMO-04 P0 means **Claude tiers only**. Cross-vendor becomes P2. A4 within one family must be reported as "within-family"; it does not support "not tied to one model". |
| C25 | **Grader cost.** Models costs a grade as 3 single-call samples. Grading's pipeline is segment + 2 × Pass A + 2 × Pass B (+1 adjudication) (+2 key-aware), with the design doc in most calls. The matcher, adjudicator, G3 and citation-judge costs are **not estimated anywhere**. | `models/README.md` §3 grader table; `grading/README.md` §6.1; `methodology/metrics.md` §2.3, §5 | Recompute (expect about 2-3× models' $0.35 per review for the grader alone). Add matcher and judge costs. Put an end-to-end eval budget in one place (§3, cost row). |
| C26 | **Unkeyed valid findings.** Blind A/B READMEs: "neither rewarded nor penalised". Methodology: VALID_UNPLANTED counts as correct in **adjudicated precision** (primary). Grading: "never penalised, must be verified". | `eval/blind/*/README.md`; `methodology/metrics.md` §2.3 step 4, §3 | Methodology wins. Report P_strict and P_adj side by side. The blind READMEs' rule governs nothing once keys are normalised. |
| C27 | **Pairwise debiasing.** Run both orders and average. Or: count a win only if both orders agree, else tie. Or: never pairwise. | `kaggle/README.md` Rec. 3; `models/README.md` §4.5; `grading/README.md` §6.2 | Pairwise only for A/B ablations, with models' agreement-or-tie rule. Headline scores stay absolute. |
| C28 | **Model ID pinning.** Frameworks: "dated model snapshot ID … never use an alias". Models uses `claude-opus-5-5`. | `frameworks/README.md` §6; `models/README.md` §1, §7 | Verify whether `claude-opus-5-5` is itself a pinned ID or an alias (§2, item U5). Record the `model` field returned in each response. |
| C29 | **Sub-agents.** Models recommends "Opus 5.5 orchestrator plus Sonnet 5.5 readers" (about $1.85 per run). Frameworks' state machine has no reader sub-agents. | `models/README.md` §3; `frameworks/README.md` Decision | Allow a per-stage `model` in config (for example `research.reader_model`). Add the reader pattern to the architecture doc, or drop it from the cost plan. |
| C30 | **Workload attributed to "the brief".** Models says the 60K-token document, 150K research tokens and 15-25 calls come "from the brief". **The lab brief contains no such figures.** The SIT sample artefact is 30 pages and about 7.6K words (about 10-13K text tokens), with 6 images. Native PDF input also bills page images, so 60K may be right for the native path but not for text. | `models/README.md` §3 | Correct the attribution. Measure with `count_tokens` for both the native-PDF and the text paths (§2, U3). Rerun `cost_model.py`. Haiku's exclusion and the latency claims depend on this. |
| C31 | **Robustness quality thresholds depend on the methodology matcher.** BEH-08 (precision ≥ 0.6), BEH-09 (critical recall ≥ 0.8), INP-12, INP-14, OVF-01/03 (overlap ≥ 0.7) all need a validated matcher. BEH-08 does not say whether precision is strict or adjudicated. | `robustness/scenarios.md` BEH-08/09, INP-12/14, OVF-*; `methodology/metrics.md` §2.3 step 6 | The matcher is on the **critical path** of the robustness P0 gate. Build and validate it before L1 P0. Define precision in robustness as methodology's P_adj. |
| C32 | **Answer-key formats (six).** Methodology §1.2 schema; grading YAML (`key_items/traps/no_change_areas`); robustness `*.gold.yaml` (`planted/expect.must_flag`); synthetic JSON; blind-A JSON; blind-B JSON. Clinical puts **F15 inside `flaws[]`** (15 entries) while the other two use `v2_new_flaws`. Only clinical has `category_counts_v1`, only payments has `flaw_counts`, only blind A has `requires_external_fact`. | as listed | One `answer_key.schema.json` (§5), with a converter that normalises the five existing keys. |

### 1.2 Robustness's "11 things the architecture needs" against the frameworks decision

Source: `robustness/README.md` §10 compared with `frameworks/README.md` Decision and Recommendation.

| # | Robustness requirement | In frameworks decision? | Gap / action |
|---|---|---|---|
| 1 | One ToolGateway and one LLMGateway | Partly: per-server health, explicit retries, timeouts | Name the two gateways in the architecture. Set SDK `max_retries=0` so the gateway owns retries (robustness §5.3). Frameworks only says "set explicitly". |
| 2 | Background parallel warm-up plus `preflight` | Yes (pre-warm in `ingest`, 150 s) | Frameworks pre-warms "all four", but DI is off by default (INF-11). Warm only the enabled servers. |
| 3 | Evidence ledger with stable IDs; the LLM never writes URLs | No. Frameworks has `tools.jsonl` record/replay, not ID-cited evidence | Adopt (C11). |
| 4 | Anchors as verbatim quotes, fuzzy-verified | Not addressed. Models proposes native citations instead | Resolve per C13/C14. |
| 5 | Decision and constraint registry pinned in state | No | Add it. It is lab §1.3 "preserve … approved decisions" and the basis of the ADV metric. |
| 6 | Checkpoint per stage, `resume`, distinct exit codes | Conflicts (C17) | Build it. Amend the switch condition. |
| 7 | Config-driven criteria, stop rules, tools, model, persona | Yes (frameworks §3) | Consistent. |
| 8 | `explain <finding_id>` and a coverage map | No | Add it. It is the cheapest evidence for explainability (lab §5.4a). |
| 9 | Local-first parsing chain | Conflicts (native PDF first) | Resolve per C14. |
| 10 | Spotlighting and plan-then-execute | Partly ("plan" stage) | Resolve per C18. |
| 11 | Template-rendered report | Implied by structured outputs | Consistent. Name the template engine (DEMO-08 says Jinja). |

**Net:** frameworks' choice (a custom loop) survives, but its decision text covers only about 4 of the 11 needs. The remaining 7 are what turns the custom loop's self-scored 5/5 on robustness into reality (frameworks itself says "if we do not [build them], the custom loop drops below LangGraph"). They must go into the architecture spec, not stay in the robustness note.

### 1.3 Duplication worth consolidating

- **LLM-judge bias controls** appear in three places: `models/README.md` §4, `grading/README.md` §6.2 and `methodology/README.md` §8-9 (L22, L23, L35, L36), with slightly different rules (C3, C27). Keep one copy, in grading. Models and methodology should reference it.
- **Overfitting checks** appear in `methodology/README.md` §5 and `robustness/scenarios.md` OVF-01 to OVF-12, in different units (paired tests vs overlap ≥ 0.7). Methodology defines the statistic. Robustness defines the fixture and invokes the statistic.
- **Demo-day probes** appear in `grading/README.md` §9 and `robustness/scenarios.md` DEMO-*, with different targets (C23). Merge them into one runbook (§5).
- **Leakage grep** appears as frameworks §5 "lint test", robustness OVF-07 and methodology §3.2 step 1. Methodology's version is the superset (all sealed docs, not only the SIT sample). Use one script.

---

## 2. Load-bearing claims marked UNVERIFIED (or from memory)

Classes: **(a)** must verify before submission because a decision rests on it; **(b)** nice to verify; **(c)** can be dropped or left as stated.

### 2.1 Class (a): verify, and how

| ID | Claim | Where | Decision that rests on it | How to verify |
|---|---|---|---|---|
| U1 | SIT MCP **auth header name** (`Authorization: Bearer` vs `X-API-Key` vs other). The servers were never reached ("proxy 403"). | `frameworks/comparison.md` §0, "Not verified" | Connector vs direct client; the shape of the client code; INF-07/08 | From an unrestricted network, POST an MCP `initialize` to each URL with each candidate header, and record the status codes. Save the working request as a cassette. About 15 minutes. |
| U2 | **Live server behaviour:** cold-start error shape (hold vs 502/503), MCP protocol version (sessions or sessionless), `tools/list` names and schemas, DI rejection message, DuckDuckGo soft-throttle as HTTP 200, and whether the browser session is shared across participants | `robustness/README.md` §5.3 transport note, §11; INF-02/06/09/21 | Retry classification, session re-init, browser URL check | Run the first L2 recording session (robustness §4.3 step 3) after 30+ minutes idle. Log the raw responses. Update INF-02/06/09/21. |
| U3 | **Document token count** ("60K", attributed to a brief that does not contain it) | `models/README.md` §3, §6 | Cost table, Haiku exclusion, latency budget, context design | `client.messages.count_tokens` on the SIT PDF as a native document block **and** as extracted text, on Opus 5.5 and Sonnet 5.5. Rerun `cost_model.py`. |
| U4 | **Latency per run** (all latency classes UNVERIFIED), plus the **demo slot length**, which the lab never states (robustness assumes 10 min) | `models/README.md` §2, §6; `robustness/scenarios.md` DEMO-05 | Effort settings, research budget, deadline-aware planner | 10 full runs per candidate model (models §6 already specifies this). Ask SIT for the slot length. Until then, design for a configurable deadline. |
| U5 | **Model ID semantics:** is `claude-opus-5-5` a pinned snapshot or an alias? Does a response report the model actually served under fallback? | `frameworks/README.md` §6 vs `models/README.md` §1 | Reproducibility claim, L31 | `client.models.retrieve("claude-opus-5-5")`, the `claude-api` skill's model table, and the `model` field in a live response. |
| U6 | **Refusal risk on AI-platform designs** (Sonnet `frontier_llm` false positives, Opus `reasoning_extraction`) | `models/README.md` §1, §2 | Choice of orchestrator vs reader model | Models §6 "Refusals will not hit live": run on the SIT sample plus a security-heavy doc and count `stop_reason == "refusal"`. |
| U7 | **Non-Claude judges exist and are callable:** GPT-6.1 Sol and Gemini 3.1 Pro names, prices, structured-output parameters (all UNVERIFIED, partly from snippets). Also: does the user actually hold such a key? | `models/README.md` verification table, §1, §7 | The whole cross-family plan (C3) | First ask the user which keys exist. If one does, make one structured-output call and record the model ID and usage. If not, take the §4.4 fallback. |
| U8 | **A local open-weight judge can handle the task** (Prometheus 2 or Qwen/Llama via Ollama). A 60-70K-token doc plus review is very unlikely to be feasible for a 7-8B model on a laptop. | `models/README.md` §5 item 3; `judge-bias-evidence.md` #4 | The Anthropic-only fallback | Test it **only on short-context instruments** (finding-vs-flaw matching, claim-vs-passage entailment, both under 2K tokens). Measure κ against the human labels from §4.6. Do not try the holistic grader locally. |
| U9 | **PDPA s.16 / s.25 and "no GDPR-style erasure right"** (secondary source); **XACML 3.0 Appendix C** (from memory) | `grading/worked_examples.md` §4, §6 (key item K5, trap T6), §7 | These are scoring truths in the illustrative key and in a grader regression test (A > B > C ordering). A wrong "truth" teaches the grader to reward an error. | Read PDPA 2012 at sso.agc.gov.sg (Parts IV-VI) and the OASIS XACML 3.0 Core spec, Appendix C. Update the worked examples. |
| U10 | **Intra-doc correlation ρ and SD values** used in every power calculation (illustrative) | `methodology/README.md` §4b.6; `models/README.md` §6 | Every "n needed" and MDE statement | Estimate ρ and σ_d from the first S-dev pilot (k = 3 on 3 docs), then recompute before freezing `prereg.yaml`. |
| U11 | **Generator model of every eval item** (not recorded anywhere). R6 requires the generator family to differ from the agent's. L7 depends on it. | `eval/*/*/README.md`; `methodology/README.md` R6, L7 | Whether self-preference and style contamination of the data is plausible | Record `generator_model`, `brief_sha256` and `author` in each item's README or key now, from the session logs that produced them. If it was Claude, disclose this as a limitation. |

### 2.2 Class (b): nice to verify

| Claim | Where | Note |
|---|---|---|
| Size of a non-Anthropic adapter (150-250 LOC) | `frameworks/README.md` §3; `comparison.md` §1 | Only matters if cross-vendor swap is ever promised (C24). |
| Live-modification line counts ("estimates for our planned layout, not measured") | `frameworks/README.md` §3 | Replace with DEMO-01 to 04 stopwatch results. |
| The weighted-matrix scores (judgement by the author of the hypothesis being tested) | `frameworks/README.md` matrix | Arithmetic checked (92 / 80 / 77, and the equal-weight 90 / 80 hold). Disclose the scorer, or have a second person score blind. |
| The specific numbers in the 2026 judge-bias papers: +3.4 to 8.4 pp (Awuni), ">50 %" and "10 points" (2604.06996), 31.5 % (Yang), +4.7 / −2.4 pp (2604.23178). All abstract-level only. | `models/judge-bias-evidence.md` #10-15; `models/README.md` §4-5 | The decision (cross-family judge) is supported by the verified classics (#1, #7, #13). Quote the numbers only after a full-text read, otherwise cite the direction only. |
| "Rank orderings are robust to ±3 weight changes" | `grading/README.md` §10 | Run `weighted()` with perturbed weights over the V-test reviews and report the result. |
| `krippendorff` PyPI API; the pass@k / pass^k estimator form | `methodology/metrics.md` §11, §7.2 | Verify at build time with a hand-computed unit test. |
| MCP spec 2026-07-28 removes protocol sessions | `robustness/README.md` §5.3 | Superseded by U2. |
| Malkov & Yashunin bibliographic facts | `grading/worked_examples.md` §7 | Low risk. Verify if the example ships. |
| Kaggle competition licences and metrics ([S] snippets) | `kaggle/README.md`, `candidates.md` | Only if Kaggle data is actually used. The current plan uses techniques only. |
| "No Kaggle competition targets design review" | `kaggle/README.md` TL;DR 1 | Phrase it as "none found in N queries" (the note already calls it a search result, not a proof). |

### 2.3 Class (c): can be dropped or left as stated

- MCP connector timeout and cold-start behaviour (`frameworks/comparison.md`): the connector is not used.
- GitHub stars and issue counts; CrewAI structured-output and telemetry details; Claude Agent SDK Bedrock path; smolagents replay API (`frameworks/comparison.md` §5, §7, §8): these frameworks are rejected.
- AES 2.0 slug; Track3; Jigsaw winner (`kaggle/candidates.md`).
- Ref 29 "log analysis" (title only) and ref 35 SPOT matcher claim (secondary) (`methodology/README.md` §12): drop both, or cite them as "reported in a secondary summary".
- "False-absence is the most common grounding error" (`methodology/metrics.md` §5.1): it is a hypothesis to measure, not a premise.
- "Changed-section coverage" usefulness, and the overrun metric as "our operationalisation" (`metrics.md` §8, §10): keep them, labelled as such.
- Mills 1972 primary source; Sim & Wright tables; TREC pooling citation: standard, low stakes.

---

## 3. Coverage against the user's bar

| Level | Where it is covered | Adequate? | What is missing |
|---|---|---|---|
| **Capability** | `frameworks/README.md` §1 (qualitative); `models/README.md` §1-2; `methodology/README.md` §4 (B0, B0-$, A1-A5) | **Plan: yes. Evidence: none.** | No pilot run on the SIT sample yet. Capability is argued, not measured. One B0 vs FULL pilot on 3 synthetic docs would turn §1 claims into data and calibrate flaw difficulty (L9). |
| **Explainability** | `frameworks/README.md` §2; `grading/README.md` §9(a); `robustness/scenarios.md` DEMO-06 (`explain`), DEMO-11 (coverage map), DEMO-12 (`--plan-only`) | Adequate as a plan | `explain` and the coverage map are not in the frameworks decision (1.2 items 8 and 5). No architecture diagram exists yet. No documentation plan maps to lab §5.3 (see §5). |
| **Live modifiability** | `frameworks/README.md` §3; `robustness/scenarios.md` DEMO-01 to 04, 08 to 10; `grading/README.md` §9(d) | Adequate as a plan | Targets conflict (C23). The line counts are estimates. "Swap provider" is promised by DEMO-04 but not built (C24). No rehearsal log exists. |
| **Tool-failure robustness** | `robustness/` (INF, LLM, NET, 66 scenarios); `frameworks/README.md` §4 and smoke test; `methodology/README.md` §6 (ITT and per-protocol reporting) | **Strong** | Real server behaviour is unverified (U1, U2). The smoke test used a local server with an assumed `X-API-Key`. |
| **Overfitting verification** | `methodology/README.md` §3, §5, §9 L1-L15; `robustness/scenarios.md` OVF-01 to 12; `frameworks/README.md` §5 | **Method strong, data inadequate** | The methods need S-heldout, OOD, paraphrase, reorder and clean-vs-flawed fixtures. **None exist.** There are 3 synthetic docs from a single template family (§4.2), so the L8 rule "split by template family" cannot be applied. The blind set is compromised (§4.3). No SIT-doc term list for OVF-07 has been generated. |
| **Reproducibility** | `frameworks/README.md` §6; `methodology/README.md` §7; `robustness/README.md` §6.2 (cassettes), OPS-01, OPS-10 | Adequate, with fixes | The temperature/seed vocabulary is wrong for Claude (C15). Silent server-side fallback (C16). Tools are replayable, but **LLM responses are not**: add an `llm.jsonl` replay transport so an evaluator can re-render the report offline after the SIT MCP key is revoked. State plainly that results are **statistically** reproducible (k runs plus CIs), not bitwise. |
| **Cost** | `models/README.md` §3 and `cost_model.py`; `frameworks/README.md` §7; `methodology/metrics.md` §10 (Pareto); B0-$ | **Per-run only** | The token base is unverified (C30, U3). Grader cost is underestimated (C25). Matcher and judge costs are absent. **No total budget:** for example, 9 conditions × k = 3 × 5 docs ≈ 135 agent runs ≈ $300-400, plus robustness L1 P0 (about 30 scenarios × k = 3-5) ≈ $200-300, plus grading and matching. A one-page budget with a stop-loss is needed. |
| **Bias in evaluation** | `models/judge-bias-evidence.md`; `models/README.md` §4-5; `grading/README.md` §6.2, §8 (V1-V13); `methodology/README.md` L1-L40 | **Judge bias: strong. Data bias: weak.** | Data-side bias is under-addressed. Generator provenance is unrecorded (U11). All 5 items were probably produced by the agent's own model family (R6, L7). Severity labels come from the generator alone (L14: no second annotator). The difficulty is uncalibrated (L9: no B0 pilot). There are no human-authored items. Template homogeneity is covered in §4.2. |
| **Eval metrics explicit** | `methodology/metrics.md` (formal, with pseudo-code and a worked example whose arithmetic re-checks); `grading/README.md` §3-4 | **Strong** | No `prereg.yaml` has been written. Two recall instruments compete (C4). Robustness thresholds do not reference methodology definitions (C31). The primary micro/macro choice is "PROPOSED" but not frozen. |
| **Every scenario stress-tested** | `robustness/scenarios.md` (166 scenarios: 81 P0, 68 P1, 17 P2; the counts re-check with the §9 snippet) | **Catalogue: excellent. Feasibility: no.** | (1) 81 P0 scenarios is not one person's pre-submission workload. Make §4.2's 20-item minimum gate the real P0. (2) Many fixtures do not exist (`gold_clean.pdf`, `far_*`, `docs/adv/*`, `sample_v2.pdf`, `contradictions.pdf`, `long_doc.py`). (3) **Missing scenario: multiple design documents supplied together.** Lab §1.5 says "one or more SIT AI platform component designs". INP-29 covers only a companion doc that is referenced but missing. (4) **Missing scenario: the demo v2 is an update of the SIT Memory Platform doc itself** (lab §1.5 strongly implies it). This needs a frozen v1 review of the SIT doc by the final agent, and it interacts with R5 (no SIT terms in prompts). (5) No scenario covers **failure of the measuring instruments** (matcher or grader API down, schema drift in a judge's output). |

---

## 4. Loopholes in the evaluation design

### 4.1 Can the agent be gamed into a high score?

| # | Loophole | Evidence | Fix |
|---|---|---|---|
| G1 | **Location-less recommendations escape CDR.** CDR maps findings to sound units by location overlap. A finding with no location lands in no unit and is never a sound-unit false positive. | `methodology/metrics.md` §6.2 | Count unlocated findings as NON_SPECIFIC (precision penalty) and report an "unlocated rate". Make the agent schema require ≥ 1 location (P1 in grading already treats such a finding as "an opinion"). |
| G2 | **Trivial quotes pass G1.** A fuzzy ratio ≥ 0.90 on a short generic span ("the system shall") matches somewhere in almost any doc. | `metrics.md` §5.1 G1; `robustness/README.md` INV-04 | Require quote length ≥ 8 tokens, and G2 (quote inside the cited section ±1). Report the quote-length distribution. |
| G3 | **Location spraying widens the matcher's candidate set.** Candidates include any finding whose locations intersect the flaw anchor, so citing many sections per finding raises the chance of a match. | `metrics.md` §2.3 step 1a | Cap the number of locations per finding (for example 3) in the schema. The core-insight rule still has to hold, but cap it anyway. |
| G4 | **"Flag every changed section" on v2.** In all three synthetic v2 docs the regression (F15) sits in a section named by the neutral revision-history table. | `eval/synthetic/*/README.md` (v2 description); keys `v2_changes` | The stale-finding rate partly counters this. Also add benign changed sections and at least one regression outside the change log. Report new-flaw recall together with the stale-finding rate. n(new flaws) = 3 in total, which is anecdotal, so say so. |
| G5 | **Tuning toward our own LLM grader (Goodhart).** R4 bars private exemplars from prompts, but iterating prompts on S-dev grader scores optimises toward the grader's quirks. | `methodology/README.md` R4, L6; `grading/README.md` §4.4 internal target "≥ 80" | Primary claims rest on judge-free metrics (models §4.9 already says this). Human-grade a sample from the **final** frozen agent. Report the grader–human gap on it. |
| G6 | **Prior on flaw count.** Every one of the 5 items has exactly 14 flaws (and synthetic: 4/6/4 severity, 3/2/2/2/2/1/1/1 categories). An agent tuned on S-dev can learn "about 14 issues, about 4 critical", and no item can detect that. | key metadata (`flaw_counts`, `category_counts_v1`); `eval/blind/*/README.md` | Vary the counts (0, 3-6, 10-20), including fully sound docs (C22). |

### 4.2 Are the synthetic docs too template-like?

**Yes, and measurably so.**

- All three synthetic READMEs say they follow the structure of the SIT Memory Platform design. The heading lists confirm it: Requirements, Foundational Principles, … Prior Art, Confirmed Decisions, Pending Backlog, Validation and Acceptance Criteria, (Build/Implementation) Readiness Assessment, Build Phases. All three have identical counts (14 flaws; 4/6/4 severities; identical category counts; 5 sound sections), similar length (9.3-9.6K words), and the same rendering (python-markdown → LibreOffice, **0 embedded images**, versus 6 in the SIT sample).
- **Specific tells:**
  - Every synthetic doc has a `decision_depends_on_pending_*` flaw, which can be found by cross-checking "Confirmed Decisions" against "Pending Backlog".
  - Every doc's "Readiness" table marks the flawed areas "Ready". Each README states this as a design property.
  - "Prior Art and Reference Architecture" is a **sound** section in 2 of 3 docs (clinical §19, payments §23).
  - An agent that learns "challenge everything marked Ready; never fault Prior Art" scores well here for reasons unrelated to review skill.
- **This cuts both ways.** The demo artefact is very likely another SIT component design in the same template, so template fidelity is good ecological validity for the demo. It is fatal for any *generalisation* claim. Report the two separately (methodology L39 already separates Real-dev).
- **No figures or tables-as-images** means methodology L15 (ingestion) and robustness INP-03/04 are untested by the eval set. The blind items have **no PDF at all**.
- **Required control:** run the template-tell probe (`methodology/README.md` §3.2 step 6) on the 3 synthetic docs before any tuning. Add at least one synthetic item in a different structure (for example an ADR set, an RFC, or a one-page architecture brief) and at least one with figures and requirement tables.

### 4.3 Is the blind set actually blind?

No, for five independent reasons:

1. **Developer exposure.** `eval/blind/item_*/README.md` names the defects outright. Item B lists "IEEE 1547-2018 island trip time, Modbus FC03 register limit, UL 9540 vs UL 9540A, IEEE 2030.5 TLS … software-routed E-stop". Item A lists "EU/UK consumer-law refund rules, DynamoDB and SQS service limits, SQS FIFO". The files sit in the development tree, and this audit was asked to skim them. Methodology's "nobody until the final run" (§1.1) is already violated.
2. **The authors knew the eval design.** Both blind items have exactly 14 defects, a severity scale, "deliberately sound sections" with likely false positives, and per-defect credit criteria. That mirrors the synthetic brief and methodology §1.2. Methodology's Tier-2 definition requires "no knowledge of the project, the taxonomy or the agent".
3. **The domain exclusion list.** Telling the blind authors which domains to avoid makes the blind set different-domain by construction. That alone is acceptable, but it means the dev→blind gap mixes domain shift with overfitting. Methodology's DiD against B0 (§5) partly controls for this, and that is the only valid way to read the gap. The list did not stop **topical overlap**: blind A tests DynamoDB limits and idempotency, as payments_orchestration F04 does.
4. **Probably the same model family** as the agent (U11 unrecorded). L7 and R6 apply.
5. **Structure.** The blind items share the synthetic sections (Purpose, Requirements, Principles, Architecture, Decisions, Open Items, Acceptance Criteria, Plan). They have no v2 and no PDF.

**Resolution.**

- **Reclassify the current `eval/blind` as S-heldout.** Seal it (encrypt its keys and READMEs), and log every access, with ≤ 3 accesses.
- **Commission a genuinely blind set.** Use a short brief that does not fix the flaw count, does not mention sound-section traps, and asks for the author's own free-text key (methodology §1.1 rule 3). Use a different model family, or a human. Have the brief issued and the items stored by someone (or something) the developer does not read: for example, an encrypted archive whose passphrase is held until the final run.
- Ask for PDFs with at least one figure and table.

### 4.4 Is a different-provider judge feasible with only an Anthropic key? The fallback

The research sandbox blocked `openai.com`, `ai.google.dev` and similar sites, so even model names are unverified (U7). If the user holds only an Anthropic key, every methodology "different family" MUST fails. Recommended fallback, in order of value:

1. **Get one cross-family key.** This is the cheapest real fix. Models §3 puts a 3-judge panel over 40 reviews at about $40. Any one provider with structured outputs is enough for the matcher and a second grader.
2. **If that is impossible, route instruments by context length:**
   - **Short-context instruments go to a local open-weight model** (U8): the finding↔flaw matcher (§2.3; about 1-2K tokens per pair), the claim↔passage support judge (§5.2) and the G3 premise check with retrieved spans. These are feasible on a laptop. Validate each against the human labels from §4.6.
   - **Long-context instruments use Claude Sonnet 5.5, disclosed as same-family:** the holistic lecturer grader, with the doc in context. Mitigate with blinding, normalisation and V9.
   - **Move every headline claim to judge-free or locally judged metrics:** recall, SWR, CDR, HFR via G1/G2, fabricated-citation rate. Models §4.9 and §5 already recommend this.
3. **Amend methodology R4, L35 and the §8 gates** to state which instruments are same-family and that their claims are capped at "tentative".

### 4.5 Can the grader be fooled?

- **Correlated blind spots in key-blind mode.** Pass B's "independent pre-read" (up to 8 issues) is the coverage reference. If the grader shares the agent's family, it misses the same issues, and D3 is inflated exactly where the agent is weak. (`grading/grader_prompt.md` §3.2 step 1; `judge-bias-evidence.md` #9, #12.) **Fix:** coverage claims come only from planted-key recall. D3 key-blind is reported as a supporting number.
- **The V-tests rest on a review that does not exist yet.** R_base, "a competent review covering K1-K6", must be authored. If an LLM writes it, V9 (style / self-preference) partly tests that LLM's style. Write R_base by hand, or from the final agent's output with human edits, and record its provenance (`grading/README.md` §8).
- **All grader validation is on one document** (the SIT sample, which is also the main tuning doc). Run at least V1-V4 and V10 on one synthetic item as well.
- Prompt injection, padding and authority are well covered (V1-V13, G5, ADV-*). No further action is needed beyond running them.

### 4.6 Is there a human-label plan, and is it realistic for one person?

**There is no consolidated plan.** The human-label demands are scattered:

| Source | Demand |
|---|---|
| `methodology/README.md` §8 | Matcher: 150 pairs × 2 humans. Grounding: 100. Citation: 100. Grader: ≥ 100 reviews. Human–human: ≥ 30. |
| `methodology/metrics.md` §2.3 step 4 | 100 % of VALID_UNPLANTED and HALLUCINATED, plus 20 % of the rest |
| `methodology/README.md` §1.3, L10, L12, §4 H | Base-doc audit, realism ratings, key review, ≥ 10 expert reviews |
| `models/README.md` §5 | 10-15 reviews × 2 team members |
| `grading/README.md` §7 | 5 items (extend to 15-20) |

That totals well over 600 labelled items and assumes two or more raters. At about 1 min per matcher pair, 2 min per grounding or citation pair, and 25 min per review graded on 10 dimensions, the methodology minimum alone is about 55-60 person-hours for one rater. Inter-rater agreement is impossible with one person, and L34 (an independent rater) cannot be met.

**Realistic one-person plan** (about 20-25 h; claims tiered accordingly):

1. **Matcher:** 150 S-dev pairs labelled by the user (about 3 h). Re-label a random 40 after a gap of at least 7 days for **intra-rater** κ, which is the substitute ceiling. Compare with the matcher.
2. **Grounding and citation judges:** 60 + 60 items (about 4 h).
3. **Lecturer grader:** 20 reviews spanning conditions (B0, A3, FULL, padded, terse; about 8 h), giving tentative-tier α.
4. **Adjudication:** 100 % of VALID_UNPLANTED and HALLUCINATED on held-out runs only. This is bounded by the number of findings, so estimate it from the pilot.
5. **Optional:** one peer grades 10 of the 20 reviews (about 4 h of their time) to get one human–human number.
6. **Disclose L34:** the rater is the developer, and blinding to condition is done by shuffling and stripping metadata.
7. **Drop H (human expert ceiling) and realism ratings**, or cut them to the 3-doc pilot, and label them anecdotal.

---

## 5. Missing pieces (needed before building)

| # | Missing artefact | Why it blocks | Content |
|---|---|---|---|
| M1 | **`eval/schema/taxonomy.yaml`**: the single canonical enum file | C6-C10, C12 | Both category axes plus mappings from all five existing taxonomies; 4-level severity with anchors and the mapping from major/minor; triage enum (lab §3.2); verdict enum; provenance enum; stop-reason enum. |
| M2 | **A canonical finding / report schema** (Pydantic, exported to JSON Schema) shared by the agent, the matcher, the grader segmenter and the robustness oracles | The agent's output is the contract for every instrument; it cannot be written twice | Start from `methodology/metrics.md` §1. Add: page in `location`; `evidence_ids` (ledger) instead of free refs; `source: doc\|external\|inference`; `triage` with `owner_or_next_step`; `challenges_decision`; `no_change` items; `intent_summary`; `unresolved[]`; verdict with conditions and confidence; a cap on locations per finding; minimum quote length. Version it (`schema_version`). Ensure it fits structured-output limits (no length or numeric constraints; `frameworks/comparison.md` §1). |
| M3 | **A canonical answer-key schema plus a converter** for the 5 existing keys | C5, C32 | Fields from `methodology/README.md` §1.2 (`core_insight`, `location` with quoted anchor, `needs_external_research`, `planted`, `expected_triage`, `approved_decisions[]`, `diff_key`), `generator_model`, and a canary GUID (§1.1 rule 5). The current keys lack `core_insight`, `approved_decisions`, `expected_triage` and canaries. The synthetic keys also lack `needs_external_research`, so ablation A1's category prediction is uncomputable. Use the 6 fixed flaws per v2 doc as natural **clean-vs-flawed counterfactual** pairs (§5, Dycke & Gurevych), since no clean base docs exist. |
| M4 | **`prereg.yaml`** | L24, L25, C2, C21 | Primary metrics; the single recall instrument; micro or macro; severity mapping; k; α and corrections; achieved n and MDE; matcher, grader and judge model IDs; grader tiers; what counts as exploratory. |
| M5 | **Where answer keys and sealed sets live** | R2, R3; §4.3 | **Decide that the repo is private.** The lab only requires inviting two SIT GitHub IDs (lab §5.2), which works with a private repo. Even so, encrypt S-heldout and Blind keys with `age`, keeping the identity outside the repo and outside the agent's filesystem allow-list. S-dev keys can stay in plaintext. Add a pre-commit hook that refuses plaintext keys in sealed paths. |
| M6 | **Confidentiality handling for SIT material** | Lab cover page ("SIT Internal", "All rights reserved"); lab §5.2 (no committed secrets) | Do not commit the lab PDF, the SIT sample PDF or the shared MCP key. `grading/worked_examples.md` quotes the SIT sample at length, which is fine in a private repo but should be reviewed before anything is published. `robustness/scenarios.md` OPS-02 contains the key's first 8 hex characters as a grep pattern. Replace it with a pattern read from the environment. |
| M7 | **Instrument-routing table** (which model runs which instrument, per set of available keys) | C3, §4.4 | One table, owned by grading or methodology, referenced by everyone else. |
| M8 | **An eval data expansion plan** | §4.2, §4.3, C21, C22 | At least 2 fully sound docs; at least 1 OOD doc (methodology "OOD", robustness INP-14); a v2 of the SIT sample (expected demo input); a rehearsal pool for DEMO-05; new genuinely blind items; variable flaw counts; PDFs with figures and tables; a B0 difficulty pilot; a template-tell probe. |
| M9 | **A demo-day runbook** | `grading/README.md` §9 and `robustness/README.md` §7.2 overlap and conflict (C23) | T−30 min: preflight and warm-up; T−3 min: preflight again. Cassette fallback. A frozen v1 review of the SIT doc for delta mode. A modification playbook with stopwatch targets. Talking points per lab §5.4(a). Recovery steps per failure class (NET-01/02, INF-07, LLM-02). Laptop checklist. |
| M10 | **A documentation plan matching lab §5.3 and §5.1** | Deliverables | One `docs/` file or section per §5.3 bullet: architecture; framework and technologies; context management; planning and execution; tool orchestration; memory and state; validation and review approach; assumptions, limitations and constraints. Plus the §5.1 items: prompts, workflow definitions, memory configuration, install and run steps, the review outputs generated **during the lab session** with their evidence ledger, and the §5.2 env-configuration instructions. Each research note maps to one or more of these bullets. Write the map now so that nothing is left out. |
| M11 | **Ingestion and anchoring spec** | C13, C14 | Which extractor (pinned), page-marking format, normalisation (NFKC, de-hyphenation), how image-only content is handled (INP-04), and that every verifier uses this text. |
| M12 | **Budget and schedule** | §3 cost row | Total USD and person-hours for development, the eval matrix, robustness L1 and grading, with a stop-loss. The submission deadline is not in the brief: get it from SIT. |
| M13 | **Architecture spec that absorbs the 11 robustness needs** | §1.2 | Gateways, ledger, registry, checkpoint, explain and coverage map, stop-rule registry, per-stage model config. |

---

## 6. Prioritised action list

Effort: S = under half a day; M = 0.5-2 days; L = more than 2 days.

### P0: blockers (settle before writing agent code)

1. **Probe the live SIT MCP servers** from an unrestricted network. Find the auth header, protocol and session behaviour, `tools/list` schemas, cold-start shape and DI rejection text. Record the first cassettes. Covers U1 and U2. **S**
2. **Confirm which LLM provider keys are available.** Write the instrument-routing table, including the Anthropic-only branch from §4.4 (local cross-family model for short-context instruments; disclosed same-family holistic grader). Covers U7, U8, C3, M7. **S**
3. **Write `taxonomy.yaml`:** both category axes, the 4-level severity scale and the mapping from the existing scales, plus the triage, verdict, provenance and stop-reason enums. Covers C6-C10, C12, M1. **S**
4. **Write the canonical finding/report schema** shared by the agent, matcher, grader segmenter and oracles. Use ledger-ID citations, quote + page anchors, triage, `challenges_decision`, no-change items, a location cap and a minimum quote length. Covers C11, C13, G1-G3, M2. **M**
5. **Fix the ingestion and anchoring path:** native PDF to the model, plus one pinned extractor producing canonical page-marked text for every verifier. Measure token counts on both paths and rerun the cost model. Covers C14, C30, U3, M11. **S**
6. **Freeze the reproducibility policy:** confirm model ID semantics; no server-side fallback in eval runs; client-side fallback with the served model logged; manifest fields `thinking`/`effort`/`betas` instead of `temperature`/`seed`. Covers C15, C16, C28, U5. **S**
7. **Seal the current `eval/blind` and reclassify it as S-heldout:** encrypt its keys and READMEs, start an access log, and stop reading them. Make the repo private, keep SIT material and the MCP key out of git, and remove the key prefix from `scenarios.md`. Covers §4.3, M5, M6. **S**

### P1: before the build is tuned (first week of build)

8. **Normalise all 5 answer keys** to the canonical schema with a converter. Add `core_insight`, location quotes, `needs_external_research`, `expected_triage`, `approved_decisions`, canary GUIDs and `generator_model`. Fix clinical's F15 placement and the `pending_backlog`/`pending_item` spelling. Have a second reviewer check the `core_insight`s. Covers C5, C32, U11, M3. **M**
9. **Build and validate the matcher first,** before L1 robustness or any tuning. Use 150 S-dev pairs labelled by the user with an intra-rater re-label, plus the B-gen floor. It is on the critical path for the robustness P0 thresholds. Covers C4, C31. **M**
10. **Run an S-dev pilot:** FULL vs B0, k = 3, 3 synthetic docs. Estimate ρ and σ_d, recompute power and MDE with m = 14, run the template-tell probe and calibrate flaw difficulty. Covers U10, C21, §4.2, L9. **M**
11. **Write `prereg.yaml`:** primary metrics, the single recall instrument, the severity mapping, grader tiers, achieved n and MDE, and the exploratory labels. Covers C2, C21, M4. **S**
12. **Write the architecture spec** that absorbs the 11 robustness needs. Amend frameworks' resume condition (C17) and the plan-then-execute wording (C18). Add per-stage models for the reader pattern (C29). Covers §1.2, M13. **M**
13. **Expand the eval data:** at least 2 fully sound docs, 1 OOD doc, a v2 of the SIT sample, a DEMO-05 rehearsal pool separate from Blind, variable flaw counts, and PDFs with figures and tables. Covers C19, C22, §4.2, M8. **L**
14. **Commission a genuinely blind set** with an independent brief (no count, no trap hints, a free-text key), a different model family or a human author, and sealed storage. Covers §4.3. **M**
15. **Cut robustness P0 to the 20-item minimum gate** (`robustness/README.md` §4.2). Mark BLOCKED the scenarios whose fixtures are missing (INP-28, BEH-16, …). Add the missing scenarios: multiple input documents; demo v2 of the SIT doc; instrument failure. Define robustness precision as P_adj. Covers §3 "every scenario", C31. **S**
16. **Adopt the one-person human-label plan** (§4.6, about 20-25 h) and schedule it. Amend the methodology gates and L34 disclosure. Covers C2, §4.6. **S**
17. **Write the one-page budget:** agent runs × conditions × k, robustness L1, grader (recomputed per C25), matcher and judges, plus the stop-loss and the submission deadline. Covers C25, M12. **S**

### P2: before submission

18. **Verify or drop the class (a) and (b) citations that will appear in the write-up:** PDPA s.16/s.25 and XACML in the worked examples (U9); the specific numbers in the 2026 judge-bias papers; refs 29 and 35. **S**
19. **Run grader meta-validation:** V1-V13 on the SIT sample with a hand-authored R_base, plus V1-V4 and V10 on one synthetic item. Run the weight-perturbation check backing "robust to ±3". **M**
20. **Rehearse the live modifications** (DEMO-01 to 04, 08) with a stopwatch, and replace frameworks §3's estimated line counts with measured times. **S**
21. **Write the demo-day runbook** (M9), merging `grading/README.md` §9 and `robustness/README.md` §7.2. Include a frozen v1 review of the SIT doc by the final agent. **M**
22. **Write the documentation per lab §5.3 and §5.1** (M10). Map each bullet to the research notes and code. Include the review outputs and evidence ledger from the lab session. **M**
23. **Add an LLM-response replay transport** so evaluators can reproduce a reported run offline. State "statistically reproducible" with k and CIs. **S**
24. **Run the single final Blind evaluation** after `prereg.yaml` is frozen. Report the DiD against B0, the CIs, the MDE and every limitation from §4 (same-family judges, template homogeneity, one rater). **M**

**Counts: 7 P0, 10 P1, 7 P2 (24 actions).**
