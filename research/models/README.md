# Model selection: review agent and "lecturer" grader

Reusable note. It answers two questions for the SIT design-review agent:
which LLM should run the agent live on demo day, and which LLM should grade
the agent's reviews so the scores hold up as research evidence. The
evidence on judge bias is in [`judge-bias-evidence.md`](judge-bias-evidence.md).

Researched 2026-10-02. Prices and model names change often, so re-check
before quoting them in a submission.

## Verification status

| Source | How it was checked | Status |
|---|---|---|
| Claude model IDs, context, features, behaviour | Anthropic `claude-api` skill (cached 2026-09-25) | Verified |
| Claude prices | Fetched live from `platform.claude.com/docs/en/about-claude/pricing` on 2026-10-02 | Verified |
| Gemini prices | Fetched live from `cloud.google.com/vertex-ai/generative-ai/pricing` (Vertex AI) on 2026-10-02 | Verified for Vertex. AI Studio (Gemini API key) prices: **UNVERIFIED** because `ai.google.dev` was blocked by the sandbox proxy |
| Gemini model specs (context, thinking levels, PDF) | Search-engine snippets of `ai.google.dev` and `docs.cloud.google.com`; both blocked for direct fetch | **UNVERIFIED** |
| OpenAI model names, prices, specs | Search-engine snippets of `openai.com` and `developers.openai.com`; `openai.com`, `platform.openai.com`, `developers.openai.com` and `learn.microsoft.com` were all blocked for direct fetch | **UNVERIFIED** (marked per row) |
| Latency classes | No official per-model latency numbers found | **UNVERIFIED**, qualitative only. Measure them yourself (section 6) |

Before relying on any UNVERIFIED value, open the official page on a normal
network: `https://developers.openai.com/api/docs/pricing`,
`https://ai.google.dev/gemini-api/docs/pricing`.

---

## 1. Recommendation

> **User decision, 2026-10-02 (overrides the earlier research recommendation).** The agent uses **Claude Opus 5.5 (`claude-opus-5-5`) for every call**: orchestration, reading, research digestion, assessment, verification and report assembly. There are **no Sonnet or Haiku sub-tasks**. The earlier "Opus orchestrator plus Sonnet readers" split is kept, unadopted, in [Appendix A](#appendix-a-sonnet-55-sub-task-analysis-not-adopted). The judge/grader provider is **pending** until the user confirms which API keys they hold; both branches are below. The decision record is `docs/DECISIONS.md` (ADR-002, ADR-003).

| Role | Model | Settings | Why |
|---|---|---|---|
| **Agent: every call** (plan, research loop, per-section assessment, refine, verify, report) | **Claude Opus 5.5** (`claude-opus-5-5`) | `thinking: {type: "adaptive"}` (it cannot be disabled on this model). Set `output_config.effort` explicitly per stage: `"medium"` for research and reading turns, `"high"` for assessment, synthesis and the verify pass. Stream every call. Cache the stable prefix (tools, system prompt, document). **No server-side `fallbacks` in eval runs** (see the note below). | Native PDF input (600 pages, 32 MB), 1M-token context, structured outputs (`output_config.format`, GA), strict tools. Anthropic reports it is "much less likely ... to state a figure or cite a source the inputs don't support", which is the main failure mode for an evidence-backed review. Its classifier set (`cyber`, `bio`, `reasoning_extraction`) is narrower than Sonnet 5.5's, which adds `frontier_llm` and `general_harms`; that matters because the demo document is an *AI platform* design. One model also means one prompt-cache namespace, one effort scale and one behaviour profile to explain on demo day. |
| **Grader / matcher / judges, branch A** (a second provider's key exists) | **A different family:** GPT-6.1 Sol (`gpt-6.1-sol`, **UNVERIFIED** specs) or Gemini 3.1 Pro (`gemini-3.1-pro-preview`) | High reasoning. Analytic rubric with anchored levels. Evidence quotes before scores. Section 4. | Self-preference and same-family "preference leakage" are documented. A cross-family judge is the cheapest mitigation with published support. |
| **Grader / matcher / judges, branch B** (Anthropic key only) | Short-context instruments (finding↔flaw matcher, claim↔passage judge, G3 premise check) on a **local open-weight model**, validated against human labels. Long-context holistic grader on **Claude**, disclosed as same-family: Sonnet 5.5 at effort `high` is the research recommendation (a different model from the agent); Opus 5.5 if the user extends the all-Opus rule to instruments. Headline claims move to code-checked, judge-free metrics. | Section 5 and `research/audit/research_audit.md` §4.4 | The bias is reduced, not removed, and every LLM-judged number is labelled "same-family, tentative". |

**Why no server-side fallback in eval runs.** The `claude-api` skill recommends opting into `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`) for Opus 5.5. Its targets are other models (`claude-opus-5`, `claude-opus-4-8`), so a classifier refusal would be answered by a model that is not Opus 5.5. That silently breaks the all-Opus decision and the pinned-model reproducibility claim (audit C16). Eval runs therefore send no `fallbacks` field and handle `stop_reason: "refusal"` in the agent (retry once with professional framing, then mark the section "model declined"; robustness LLM-06). The demo may opt in with `--allow-fallback`; any fallback is detected from `usage.iterations` (`fallback_message` entries) and `response.model`, and is written to the run manifest. `fallbacks` is also rejected on the Batches API. Policy: `docs/REPRODUCIBILITY.md`.

**Model ID semantics (audit U5, resolved from the skill).** `claude-opus-5-5` has no dated snapshot ID; the skill's model table lists the bare ID as the only identifier. It is therefore the most specific pin available. Record `response.model` for every call and the `client.models.retrieve("claude-opus-5-5")` result once per run, and disclose possible silent server-side updates as a limitation.

**Consequence for ablation A4 ("different backbone model").** Under the all-Opus decision, A4 can only vary settings within one model (proposed A4e: every stage at effort `low`). It no longer supports a "not tied to one model" claim (audit C24). That claim is dropped.

**Not recommended for the live agent:**

- **Claude Fable 5.1** (`claude-fable-5-1`). It costs 2.5x Opus 5.5 ($10/$50). Thinking is always on, and Anthropic warns "single requests on hard tasks can run many minutes", which is risky with a lecturer watching. It requires 30-day data retention, so an org on zero data retention gets a 400. Keep it as an offline reference model if budget allows.
- **Claude Sonnet 5.5 / Haiku 4.5 sub-tasks.** Not adopted by user decision; analysis retained in Appendix A.
- **GPT-6 Astra** ($10/$50, **UNVERIFIED**). Staged rollout; long-context pricing roughly doubles above 272K tokens.
- **Gemini 3.1 Pro Preview** as the *agent*. Preview status (tighter rate limits, can change without notice). As a *grader* this matters less because grading runs offline.

## 2. Comparison table

Prices are USD per 1M tokens (input / output). Cached-read prices are in the cost section.

| Model (API ID) | Context / max out | $ in / out | Native PDF input | Structured output | Tool use | Thinking / effort control | Latency class (UNVERIFIED) | Refusal / safety behaviour that could bite live |
|---|---|---|---|---|---|---|---|---|
| Claude Fable 5.1 `claude-fable-5-1` | 1M / 128K | 10 / 50 | Yes (base64 or Files API; 600 pages, 32 MB) | Yes (`output_config.format`, `strict` tools); citations and structured output cannot be combined in one call | Strong. Forced `tool_choice` `any`/`tool` returns a 400, so use `auto` plus a prompt instruction | Always on; effort `low`..`max` | Slowest. Turns can run for minutes | Classifier refusals (`stop_reason:"refusal"`, HTTP 200). 30-day retention required |
| Claude Opus 5.5 `claude-opus-5-5` | 1M / 128K | 4 / 20 | Yes (600 pages) | Yes | Strong; MCP connector; forced `tool_choice` returns a 400 | Cannot be disabled; effort `low`..`max`, **default `medium`** | Medium. Fast mode is 2x the price ($8/$40) for up to 2.5x output speed | `cyber`, `bio`, `reasoning_extraction` classifiers. Never ask it to "print your internal reasoning" in the answer, because that triggers `reasoning_extraction`, and those refusals are *not* retried on fallback. Ask for "rationale for each finding" instead. Handle `stop_reason` before reading content |
| Claude Sonnet 5.5 `claude-sonnet-5-5` | 1M / 128K | 2 / 10 | Yes (600 pages) | Yes | Strong (Anthropic says it "uses connected tools more reliably"); forced `tool_choice` returns a 400; occasionally sends a tool name with the wrong letter case, so match names case-insensitively | Adaptive; effort default `high`. `{type:"disabled"}` returns a 400; use `{type:"between_tools"}` to turn thinking off | Fast–medium | **Widest classifier set:** `cyber`, `bio`, `frontier_llm` ("could assist the development of competing AI models"), `reasoning_extraction`, `general_harms`. An AI-platform design document is a plausible `frontier_llm` false positive, so test on the sample artefact. Server-side fallback covers only `cyber` and `frontier_llm` |
| Claude Haiku 4.5 `claude-haiku-4-5` | **200K** / 64K | 1 / 5 | Yes (**100 pages** at 200K context) | Yes | Good for simple calls | `budget_tokens` only; no `effort` | Fastest | Fewer reports of over-refusal, but it cannot hold the whole run's context |
| GPT-6 Astra `gpt-6-astra` (**UNVERIFIED**) | 1.05M / ? | 10 / 50; >272K input: 20 / 75 | Yes (Responses API `input_file`) | Yes (`json_schema`) | Strong (reported) | reasoning effort (levels UNVERIFIED) | Slow (UNVERIFIED) | Staged rollout. Refusal behaviour not researched (UNVERIFIED) |
| GPT-6.1 Sol `gpt-6.1-sol` (**UNVERIFIED**, released 2026-09-29) | ~1.05–1.1M / 128K | 2 / 10; >272K input: 4 / 15 | Yes (`input_file`) | Yes (`json_schema`) | Described as "built for complex coding and agentic workflows" | `low`, `medium` (default), `high`, `xhigh`, `max` | Medium (UNVERIFIED) | UNVERIFIED |
| GPT-6 Luna `gpt-6-luna` (**UNVERIFIED**) | 1.05M / 128K | 0.10 / 0.50 | Yes (`input_file`) | Yes | High-volume tier | UNVERIFIED | Fast | UNVERIFIED |
| Gemini 3.1 Pro Preview `gemini-3.1-pro-preview` | 1,048,576 / 64K (UNVERIFIED) | 2 / 12; >200K input: 4 / 18 (Vertex, verified) | Yes (PDF, per snippets) | Yes (response JSON schema; from memory, UNVERIFIED for 3.1) | Function calling | `thinking_level` low / medium / high | Medium (UNVERIFIED) | **Preview status.** Configurable safety filters (from memory, UNVERIFIED) |
| Gemini 3.8 Flash (GA 2026-09-02, UNVERIFIED) | 1M / 64K (UNVERIFIED) | 0.75 / 3.75 until 2026-12-31, then 1.50 / 7.50 (Vertex, verified) | Yes (UNVERIFIED) | Yes (UNVERIFIED) | Function calling | `thinking_level` low / medium / high, default medium (UNVERIFIED) | Fast | UNVERIFIED |

Claude feature notes, all from the skill:

- Claude 4.7 and later use a tokenizer that produces **about 30% more tokens for the same text**. If the 60K-token planning assumption for the document (section 3; it is **not** a figure from the lab brief, audit C30) came from a different tokenizer, scale it up. Measure the real count with `messages.count_tokens`.
- Citations (`citations: {enabled: true}` on the document block) return `page_location` page numbers for PDFs. That suits SIT's "traceable" requirement. Citations **cannot be combined with structured outputs** in the same call (400). Use citations in the analysis calls and structured output in the final assembly call.

  > **Superseded (reconciliation 2026-10-02):** scored findings carry `{page, section_ref, quote}` anchors **inside** the structured output, verified in code against the canonical page-marked text; native citations are never part of the scored output and may be used only in an unscored analysis call. See `docs/DECISIONS.md` ADR-006, ADR-007 and `spec/README.md` §3 C13.
- Assistant-turn prefill is rejected on every 4.6+ model. Use `output_config.format` instead.
- The SIT MCP servers are remote HTTPS endpoints that scale to zero, with a 1–2 minute cold start. Calling them from your own harness (client-side MCP) with retries and a warm-up ping is more controllable live than Anthropic's server-side MCP connector. That is a harness choice, but it drives tool-use reliability more than model choice does.

## 3. Cost per review run (all Opus 5.5)

**Workload assumption (a planning assumption, not from the brief).** The earlier version of this note attributed the workload to "the brief"; the lab brief contains no such figures (audit C30). The assumption is: a ~60K-token document on the native-PDF path (page images are billed as well as text), plus a ~5K system prompt and tool block (65K base); 150K tokens of research material; 15-25 model calls; 20K output tokens. The SIT sample is 30 pages and about 7.6K words (about 10-13K text tokens), so the text-only path is much smaller. **UNVERIFIED until `messages.count_tokens` is run on the SIT PDF on the laptop (audit U3).** Research and outputs accrue evenly across calls and each call resends the growing history, so a 20-call run bills about **2.9M cumulative input tokens**, almost all of it as cache reads.

The ingestion decision (`docs/DECISIONS.md` ADR-006) sends **both** the native PDF block and the canonical page-marked text (~13K) in the cached prefix, so the planning base is **78K**.

Script: [`cost_model.py`](cost_model.py) (`python3 cost_model.py`; the "ALL-OPUS" section prints every figure below).

**Per-run agent cost, every call on Opus 5.5** (Opus 5.5: $4 in / $5 cache write (5-min) / $0.20 cache read / $20 out per MTok; claude-api skill, cached 2026-09-25):

| Scenario | USD per run |
|---|---|
| **Planning figure: hybrid ingestion (78K base), 20 calls, 20K out, cached** | **$2.18** |
| Native PDF only (65K base), 20 calls, cached | $2.07 |
| Text-only ingestion (20K base) | $1.67 |
| Large PDF (100K base) | $2.38 |
| 25 calls, hybrid | $2.36 |
| Hybrid, heavy thinking (60K output) | $3.24 |
| Hybrid, 20 calls, **no caching** (for comparison; native-only base) | ~$12 |
| Reader pattern kept but readers on Opus (10 main + 12 reader calls) | $2.57 |

Plan on **$2.20 per full review, $3.25 worst case**. The reader pattern costs more when the readers are also Opus ($2.57 vs $2.18), so with all-Opus the single growing-context loop is both cheaper and simpler. Context stays under about 250K by the last call, which is well inside the 1M window; server-side compaction is not needed for one document.

**Per-condition cost** (planning shapes for the methodology conditions, all Opus 5.5, hybrid base): FULL $2.18; B0 single call $0.63; B0-$ cost-matched $2.18; A1 no research $1.02; A2 no iteration $1.52; A3 no verification $2.00; A4e effort low $1.91; A5 tools disabled $1.02.

**Caching is the biggest lever** (about 6x on Opus 5.5: $12.06 uncached vs $2.07 cached on the native-only base). Keep the tool list, system prompt, PDF and canonical text as a byte-stable prefix; note that a top-level `effort` change invalidates the messages cache (about $0.40 to rewrite a 78K prefix, not in the figures above); the per-message effort system message avoids that but is beta (`mid-conversation-output-config-2026-07-01`), so decide at build time whether one cache rewrite per run is cheaper than a beta on the critical path; check that `usage.cache_read_input_tokens` > 0 from call 2 onward. The **Batch API** halves every token (cache reads and writes included) and suits B0, B0-$ and all grading; it does not suit the interactive agent loop.

**Instrument costs (recomputed per audit C25).** The grader is the full `grading/README.md` §6.1 pipeline (segment, 2 × Pass A, 2 × Pass B, a 3rd-sample adjudication 30 % of the time; key-aware mode excluded). The matcher and judges follow `methodology/metrics.md` §2.3 and §5 (14 flaws; listwise shortlist; 3 candidates × 3 samples pairwise; adjudication of about 8 unmatched findings; G3 and citation judge on about 20 findings).

| Instrument model | Grader per review | Matcher + judges per run |
|---|---|---|
| GPT-6.1 Sol (UNVERIFIED price, no batch assumed) | $0.57 | $1.05 |
| Gemini 3.1 Pro Preview | $0.60 | $1.15 |
| Claude Sonnet 5.5 (batch) | $0.30 | $0.53 |
| Claude Opus 5.5 (batch) | $0.57 | $1.05 |
| Local open-weight (branch B short-context instruments) | n/a | $0 API |

The earlier single-call estimate ($0.35 per review) understated the grader by about 1.6x. Project totals (run counts × these figures, 30 % margin, cut order) are in `docs/BUDGET.md`.

## 4. Grader design (minimises the bias that has been measured)

The rationale and citations are in `judge-bias-evidence.md`. The design:

1. **Judge family is not the agent's family.** The primary judge is GPT-6.1 Sol or Gemini 3.1 Pro. *(Superseded, reconciliation 2026-10-02: this is branch A of `docs/DECISIONS.md` ADR-003, which is **Pending** until the user confirms which API keys exist; branch B is section 1's table row and section 5. Audit C3.)* Same-family judges show a +3.4 to +8.4 pp lift for their own family (Awuni et al. 2026), and judges favour models they are related to (Li et al., ICLR 2026).
2. **Panel, reported per judge.** Use a cross-family judge (headline score), a second cross-family judge if a third key exists, and **Claude Sonnet 5.5 as an in-family control**. The control is not there to score. It exists so you can *measure* self-preference (section 6, E1). Panels reduce intra-model bias (Verga et al. 2024), but they do not eliminate self-preference bias (SPB) ("SPB in rubric-based evaluation", arXiv 2604.06996, 2026).
3. **Absolute, analytic rubric for headline scores.** Score each criterion on a 0–3 scale. *(Superseded, reconciliation 2026-10-02: the grader's scale is **0–4 per dimension**, the anchored rubric in `research/grading/README.md` §3.2. The binary checkable items below are the Pass A per-finding booleans (`issue`, `rationale`, `evidence`, `expected_benefit`, `objective_link`); no second rubric. Audit C1.)* Every level has a written anchor plus one short exemplar. Where possible, split a criterion into binary, checkable items. For example: "every refinement states issue, rationale, evidence and expected benefit" (SIT §2.3). Rubric anchoring and reference material are what made Prometheus match human scores. arXiv 2604.06996 shows SPB survives even in binary rubrics, so do not stop here.
4. **Evidence first, score last.** The judge must quote the review span that justifies each score before giving it, and output strict JSON (structured outputs). Longer reasoning before the verdict reduces *harmful* self-preference (Chen et al. 2025). Set judge reasoning effort to high.
5. **Pairwise only for A/B ablations** (agent v1 against v2). Run every pair in **both orders**, and count a win only if the two orders agree; otherwise score a tie. Report the position-consistency rate. Swapping can raise verbosity bias and can hurt on clear-cut cases ("Judging the Judges: bias-mitigation strategies", arXiv 2604.23178, 2026), so pair it with the length control below.
6. **Length control.** The rubric states that length is not quality. Report the score–length correlation. Run the padding perturbation (E3). Verbosity bias is documented for GPT-4-class judges (Saito et al. 2023, Zheng et al. 2023).
7. **Blind authorship.** Strip model names and self-references, and render every review through the same deterministic markdown template before grading. Familiar, low-perplexity style drives self-preference (Wataoka et al. 2024), so formatting normalisation helps. A full paraphrase by a third model would also impose that model's style.
8. **Multiple samples.** Take 3 samples per item and report mean ± SD. Route items whose samples differ by more than one level to human review. Claude 4.7+ and 5.x models **reject `temperature`**, so you cannot force determinism. The variance you measure is the real run-to-run variance.
9. **Do not let any LLM judge facts it can check mechanically.** Do these in code: whether cited URLs resolve, whether quoted text appears in the fetched source, whether page references exist in the PDF, and (on `eval/synthetic/`) recall of planted flaws against the sealed answer key. These metrics involve no judge and so have no judge bias. They should carry the research claims; LLM grades should support them.

## 5. If you only have one provider's key (Anthropic)

What you lose:

- **No cross-family judge.** Every LLM-judged number then carries an unmeasured same-family lift. The published range is roughly 3–8 pp on pairwise win rate (Awuni 2026), up to 10 rubric points on subjective rubrics (arXiv 2604.06996), and more than 50% higher false "satisfied" rates on objective rubric items when the output is the judge's own.
- **No way to measure that lift.** The swap test (E1) needs judges from at least two families, so you can only bound it from the literature.
- **No jury diversity.** Ensembling several Claude models still shares training data and style priors, which is the "preference leakage" problem (Li et al. ICLR 2026).

Partial mitigations, in order of value:

1. Put the claims on judge-free metrics: planted-flaw recall and precision on `eval/synthetic/`, citation validity, and the completeness checks in section 4.9.
2. Use a *different model and configuration* as judge: Sonnet 5.5 at effort high judging Opus 5.5 output, with blinding and normalisation. Say clearly in the write-up that it is the same family.
3. Add a **local open-weight judge** as a zero-API-cost cross-family check. Prometheus 2 (7B or 8x7B, Apache-2.0) or a Qwen or Llama instruct model via Ollama on the laptop. Whether it is good enough for 10K-token design reviews is **UNVERIFIED**, so calibrate it on the human anchor set before trusting it.
4. Build a **human anchor set**: 10–15 reviews scored blind by 2 team members. *(Superseded, reconciliation 2026-10-02: one person is available. Grader validity is reported in named tiers (smoke n = 5, grading §7; tentative n ≥ 20 with ordinal α ≥ 0.667 and bootstrap CI; primary per methodology §8), with ordinal α and QWK reported together; the one-person labelling plan is audit §4.6 and is budgeted in `docs/BUDGET.md`. Tiers are frozen in `prereg.yaml` (not yet written). Audit C2.)* Report judge–human agreement (weighted κ) next to human–human agreement as the ceiling. "Judging LLM-as-a-judge" set this standard of comparison.

## 6. How to check each claim on your own data

Log `response.usage`, `stop_reason`, `stop_details`, wall-clock time and tool-call errors for every call in a JSONL file. Each claim above maps to a measurement:

| Claim | Experiment | Metric and decision rule |
|---|---|---|
| Cost per run is $2–3 on Opus 5.5 | Run the agent 5 times on the SIT sample artefact | Sum of `usage` × price per run; median and max. Cache hit ratio = `cache_read_input_tokens` / total input. If the hit ratio is below 0.7, find what is invalidating the cache |
| The document is about 60K tokens on the native-PDF path (a planning assumption, not from the brief; the SIT sample is 30 pages, ~7.6K words, ~10-13K text tokens; audit C30) | `messages.count_tokens` on the PDF, per model, for the native-PDF block **and** the canonical text | Actual tokens; rescale the cost table |
| Context and PDF limits hold | `client.models.retrieve(id)` → `max_input_tokens`, `capabilities`; send the real PDF | No 400s; page count under the limit |
| Tool use is reliable | 10 full runs per candidate model (Opus 5.5, Sonnet 5.5, plus the non-Claude option if used) | Turns with a malformed or invalid tool call; unknown-tool-name rate; runs that finish without manual intervention (target ≥ 9/10); MCP timeout rate (warm the containers first) |
| Refusals will not hit live | Run on the sample artefact, plus a security-heavy and an AI-training-heavy design document | Count of `stop_reason == "refusal"` by `stop_details.category`. Any non-zero count on Sonnet 5.5 `frontier_llm` means keep Opus 5.5 as the orchestrator |
| Latency suits a live demo | Same 10 runs | p50/p95 seconds per call and per full run. If p95 per run exceeds about 10 minutes, lower effort or try Opus fast mode |
| **E1: self-preference swap test** | Generate reviews of the same N documents with two agent families (Claude Opus 5.5 and GPT-6.1 Sol or Gemini 3.1 Pro). Grade all of them with judges from both families, 3 samples each | Fit `score ~ author + judge + author:judge + (1|doc)`. The `author:judge` interaction, or the same-family lift "hold the author fixed, compare judges" (Awuni 2026), **is** the self-preference estimate. Report it with a bootstrap 95% CI over documents. Also report weighted κ / Spearman / Krippendorff's α between judges for each criterion |
| E2: position bias (pairwise) | Run every A/B pair in both orders | Consistency rate (target ≥ 0.8); first-position win rate (should be about 0.5) |
| E3: verbosity bias | Add ~30% plausible but irrelevant text to 10 reviews; delete redundant sentences from 10 others | Mean score change (should be ≤ 0 for padding); score–length Spearman across all reviews |
| E4: judge stability | 3 samples per item | Per-criterion SD; share of items with spread > 1 level |
| E5: human validity | 10–15 reviews graded blind by 2 humans *(reconciled 2026-10-02: one rater; ≥ 20 reviews for the tentative tier, audit C2 and §4.6)* | Judge–human ordinal Krippendorff's α **and** quadratic-weighted κ, with bootstrap CI; human–human only if a peer grades a subset |
| E6: style-driven self-preference | Have model B rewrite model A's review sentence by sentence with the content unchanged, and the reverse (the "equal-quality pair" idea from Yang et al. 2026). Check by diff and human spot-check that content is preserved | Score change when only the authoring style changes |
| Judge-free validity | `eval/synthetic/` planted flaws | Recall and precision of planted flaws. Correlate with judge scores (a judge that does not track planted-flaw recall is suspect) |

**Sample size.** For a paired 0–3 criterion with SD ≈ 0.6, detecting a 0.3-point self-preference at α = 0.05 with 80% power needs n ≈ ((1.96 + 0.84) × 0.6 / 0.3)² ≈ **31 documents**. With the 10–20 documents we can realistically produce, E1 is a **sanity check, not proof**. Report CIs and do not claim "no bias" from a non-significant result. The SD of 0.6 is an assumption; replace it with the SD you observe after the first 10 items.

## 7. Implementation snippets (Claude, verified against the skill)

```python
# Agent call (Python SDK). Eval runs: no `fallbacks`, so every call is served by claude-opus-5-5.
with client.messages.stream(
    model="claude-opus-5-5", max_tokens=64000,
    thinking={"type": "adaptive"},               # cannot be disabled on Opus 5.5
    output_config={"effort": "medium"},          # "high" for assessment, synthesis and verify
    system=SYSTEM, tools=TOOLS, messages=msgs,   # PDF document block + canonical page-marked text, cache_control on the stable prefix
) as stream:
    resp = stream.get_final_message()
# Always: if resp.stop_reason == "refusal": log resp.stop_details and branch before reading content.
# Always: log resp.model and resp.usage (incl. usage.iterations) to runs/<id>/llm.jsonl.
# Never: temperature, top_p, top_k, budget_tokens, tool_choice any/tool, assistant prefill (all 400 on Opus 5.5).
# Demo-only opt-in (--allow-fallback): client.beta.messages.stream(..., betas=["server-side-fallback-2026-07-01"],
#   fallbacks="default"); a fallback_message entry in usage.iterations means another model answered -> manifest.
```

The non-Anthropic grader calls (OpenAI Responses API with `json_schema`, Gemini `response_schema`) should be written against each provider's current SDK docs. Their parameter names are not verified here (UNVERIFIED).

---

## Appendix A. Sonnet 5.5 sub-task analysis (not adopted)

**Status: not adopted.** The user decided on 2026-10-02 that every agent call uses Opus 5.5. This appendix preserves the earlier analysis for reference, because it still explains the trade-off (and Sonnet 5.5 remains a candidate *grader* in branch B, which is an instrument, not an agent call).

Earlier recommendation rows:

| Role | Model | Settings | Why |
|---|---|---|---|
| Cheaper model for bulk and sub-tasks | Claude Sonnet 5.5 (`claude-sonnet-5-5`) | effort `low` for extraction and summarising fetched papers, `medium` for per-section analysis | Half Opus 5.5's price ($2/$10). Same 1M context, same tokenizer, same PDF and structured-output support, so sub-agents can receive the whole document. |
| Optional, cheapest tier | Claude Haiku 4.5 (`claude-haiku-4-5`) | `budget_tokens` thinking (it has no `effort`) | $1/$5. 200K context and a 100-page PDF limit; it cannot hold the document plus the research, and its API surface differs from the 5.x models. |

Earlier cost table (65K base, the unverified "brief" workload):

| Model | Floor: every token billed once (210K in + 20K out) | 20 calls, cached | 20 calls, no caching | 15 calls, cached | 25 calls, cached | 20 calls, cached, 60K output |
|---|---|---|---|---|---|---|
| Claude Fable 5.1 | $3.10 | $4.50 | $30.15 | $4.28 | $4.71 | $7.06 |
| Claude Opus 5.5 | $1.24 | $2.07 | $12.06 | $1.91 | $2.23 | $3.13 |
| Claude Sonnet 5.5 | $0.62 | $1.30 | $6.03 | $1.15 | $1.46 | $1.87 |
| Claude Haiku 4.5 | $0.31 | n/a: context exceeds 200K by about call 17 without compaction | – | – | – | – |
| GPT-6 Astra (UNVERIFIED) | $3.10 | $6.52 | $30.15 | $5.74 | $7.29 | $9.34 |
| GPT-6.1 Sol (UNVERIFIED) | $0.62 | $1.04 | $6.03 | $0.95 | $1.11 | $1.56 |
| Gemini 3.1 Pro Preview | $0.66 | $1.49* | $7.80 | $1.29 | $1.68 | $2.44 |
| Gemini 3.8 Flash (intro price) | $0.23 | $0.45* | $2.26 | $0.39 | $0.50 | $0.65 |

\* Gemini caching modelled with a cache write at the input price; explicit-cache storage fees ignored. Lower bounds.

Earlier split: **Opus 5.5 orchestrator plus Sonnet 5.5 readers**, about 10 Opus calls carrying the document and distilled notes and about 12 Sonnet calls each reading about 12.5K of raw research, **about $1.85 per run** ($1.13 Opus + $0.72 Sonnet) against $2.07 for Opus alone, with the orchestrator's context kept under about 110K.

Why it was not adopted (user decision; the research reasons that support it): the saving was about $0.22-0.33 per run (on the order of $100-150 over the whole project matrix); Sonnet 5.5 has the wider classifier set, including `frontier_llm`, which an AI-platform design document could plausibly trip; prompt caches are per model, so a two-model loop forfeits cache reuse between them; and one model is simpler to explain and to reproduce.
