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

| Role | Model | Settings | Why |
|---|---|---|---|
| **Primary agent (orchestrator and final writer)** | **Claude Opus 5.5** (`claude-opus-5-5`) | `thinking: {type:"adaptive"}`, `output_config.effort: "medium"` for research turns and `"high"` for the final synthesis and self-check. Stream every call. Turn on prompt caching. Turn on server-side `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`). | It has native PDF input with page-level citations, a 1M-token context, structured outputs and strict tools. Anthropic reports it is "much less likely ... to state a figure or cite a source the inputs don't support", which is the main failure mode for an evidence-backed review. It costs 20% less per token than Opus 5, and cache reads cost 0.05x the input price. Its safety classifiers (`cyber`, `bio`, `reasoning_extraction`) are a narrower set than Sonnet 5.5's, which also has `frontier_llm` and `general_harms`. That matters because the demo document is an *AI platform* design. |
| **Cheaper model for bulk and sub-tasks** | **Claude Sonnet 5.5** (`claude-sonnet-5-5`) | effort `low` for extraction and summarising fetched papers, `medium` for per-section analysis | Half Opus 5.5's price ($2/$10). Same 1M context, same tokenizer, same PDF and structured-output support, so sub-agents can receive the whole document. Swapping models during the live "modify the agent" exercise is a one-string change. |
| Optional, cheapest tier | Claude Haiku 4.5 (`claude-haiku-4-5`) | `budget_tokens` thinking (it has no `effort`) | $1/$5. Use it only for short triage or classification calls. It has a **200K context** and a **100-page PDF limit**, it cannot hold the document plus the research, and its API surface differs from the 5.x models (different thinking parameter, 4096-token cache minimum). |
| **Grader ("lecturer")**, if a second provider key is available | **A different family from the agent:** GPT-6.1 Sol (`gpt-6.1-sol`, **UNVERIFIED** specs) or Gemini 3.1 Pro (`gemini-3.1-pro-preview`) | Reasoning or thinking at high. Analytic rubric with anchored levels. 3 samples per item. Evidence quotes before scores. Pairwise comparisons only for A/B ablations, run in both orders. Details in section 4. | This is the setting where self-preference and same-family "preference leakage" are documented. A cross-family judge is the cheapest mitigation with published support. |
| Grader, if only an Anthropic key is available | Claude Sonnet 5.5 at effort `high`, plus programmatic checks, plus a local open-weight judge as a cross-family check, plus a small human-labelled anchor set | See section 5 | It is a different model and configuration from the agent but the same family, so the bias is reduced, not removed. |

**Not recommended for the live agent:**

- **Claude Fable 5.1** (`claude-fable-5-1`). It costs 2.5x Opus 5.5 ($10/$50). Thinking is always on, and Anthropic warns "single requests on hard tasks can run many minutes", which is risky with a lecturer watching. It requires 30-day data retention, so an org on zero data retention gets a 400. It runs refusal classifiers, and forced `tool_choice` returns a 400. Keep it as an offline reference model if budget allows.
- **GPT-6 Astra** ($10/$50, **UNVERIFIED**). Search snippets describe a staged rollout ("a limited set of organizations"), and long-context pricing roughly doubles above 272K tokens.
- **Gemini 3.1 Pro Preview** as the *agent*. It is still a Preview model (released 2026-02-19 per snippets). Preview models can have tighter rate limits and can change without notice, which is a poor fit for a live demo. As a *grader* this matters less because grading runs offline.

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

- Claude 4.7 and later use a tokenizer that produces **about 30% more tokens for the same text**. If the 60K-token figure for the document came from a different tokenizer, scale it up. Measure the real count with `messages.count_tokens`.
- Citations (`citations: {enabled: true}` on the document block) return `page_location` page numbers for PDFs. That suits SIT's "traceable" requirement. Citations **cannot be combined with structured outputs** in the same call (400). Use citations in the analysis calls and structured output in the final assembly call.
- Assistant-turn prefill is rejected on every 4.6+ model. Use `output_config.format` instead.
- The SIT MCP servers are remote HTTPS endpoints that scale to zero, with a 1–2 minute cold start. Calling them from your own harness (client-side MCP) with retries and a warm-up ping is more controllable live than Anthropic's server-side MCP connector. That is a harness choice, but it drives tool-use reliability more than model choice does.

## 3. Cost per review run

**Workload assumption (from the brief):** a 60K-token document, 150K tokens of research material, 15–25 model calls and 20K output tokens. To model the loop, a ~5K system prompt and tool block is added to the document, giving a 65K base. Research and outputs accrue evenly across calls, and each call resends the growing history, so a 20-call run bills about **2.9M cumulative input tokens** (the last call carries about 227K). With prompt caching, about 227K of those are cache writes and the rest are cache reads.

Script: `cost.py`, kept in the session scratchpad, not the repo. The formulas are in the table header.

| Model | Floor: every token billed once (210K in + 20K out) | **20 calls, cached** | 20 calls, no caching | 15 calls, cached | 25 calls, cached | 20 calls, cached, 60K output (heavy thinking) |
|---|---|---|---|---|---|---|
| Claude Fable 5.1 | $3.10 | **$4.50** | $30.15 | $4.28 | $4.71 | $7.06 |
| **Claude Opus 5.5** | $1.24 | **$2.07** | $12.06 | $1.91 | $2.23 | $3.13 |
| **Claude Sonnet 5.5** | $0.62 | **$1.30** | $6.03 | $1.15 | $1.46 | $1.87 |
| Claude Haiku 4.5 | $0.31 | n/a: the context exceeds 200K by about call 17 without compaction | – | – | – | – |
| GPT-6 Astra (UNVERIFIED) | $3.10 | $6.52 | $30.15 | $5.74 | $7.29 | $9.34 |
| GPT-6.1 Sol (UNVERIFIED) | $0.62 | $1.04 | $6.03 | $0.95 | $1.11 | $1.56 |
| Gemini 3.1 Pro Preview | $0.66 | $1.49* | $7.80 | $1.29 | $1.68 | $2.44 |
| Gemini 3.8 Flash (intro price) | $0.23 | $0.45* | $2.26 | $0.39 | $0.50 | $0.65 |

\* Gemini caching is modelled with a cache write at the input price and a cache read at the listed cached price. Explicit-cache storage fees per hour are ignored, and implicit cache hits are not guaranteed. Treat these as lower bounds.

**Recommended split: Opus 5.5 orchestrator plus Sonnet 5.5 readers.** About 10 Opus calls carry the document and distilled notes (about 36K tokens of notes rather than 150K of raw pages), and about 12 Sonnet calls each read roughly 12.5K of raw research. That costs **about $1.85 per run** ($1.13 Opus + $0.72 Sonnet), against $2.07 for Opus alone. The bigger gain is that the orchestrator's context stays under about 110K, which keeps turns faster and reasoning cleaner.

**Budget guidance:** plan on **$2–3 per full review** on the recommended stack. Development might be 50–100 runs, so **$100–300**, plus grading (below). Prompt caching is the single biggest lever: about 6x on Opus 5.5. Keep the system prompt, tool list and PDF as a byte-stable prefix, and check that `usage.cache_read_input_tokens` is greater than 0 from call 2 onward.

**Grader cost per review** (rubric plus instructions about 4K, review about 10K, design PDF about 65K for grounding, about 4K output including reasoning, 3 samples with the document cached):

| Judge | With document | Review only |
|---|---|---|
| Claude Sonnet 5.5 | $0.35 | $0.16 |
| Claude Opus 5.5 | $0.67 | $0.32 |
| GPT-6.1 Sol (UNVERIFIED) | $0.33 | $0.16 |
| Gemini 3.1 Pro Preview | $0.33 | $0.18 |
| GPT-6 Astra (UNVERIFIED) | $1.75 | $0.80 |

A 3-judge panel over 40 reviews costs about **$40**. The Batch API halves Claude grading cost (Opus 5.5 batch is $2/$10, Sonnet 5.5 is $1/$5). Grading is not latency-sensitive, so batch it.

## 4. Grader design (minimises the bias that has been measured)

The rationale and citations are in `judge-bias-evidence.md`. The design:

1. **Judge family is not the agent's family.** The primary judge is GPT-6.1 Sol or Gemini 3.1 Pro. Same-family judges show a +3.4 to +8.4 pp lift for their own family (Awuni et al. 2026), and judges favour models they are related to (Li et al., ICLR 2026).
2. **Panel, reported per judge.** Use a cross-family judge (headline score), a second cross-family judge if a third key exists, and **Claude Sonnet 5.5 as an in-family control**. The control is not there to score. It exists so you can *measure* self-preference (section 6, E1). Panels reduce intra-model bias (Verga et al. 2024), but they do not eliminate self-preference bias (SPB) ("SPB in rubric-based evaluation", arXiv 2604.06996, 2026).
3. **Absolute, analytic rubric for headline scores.** Score each criterion on a 0–3 scale. Every level has a written anchor plus one short exemplar. Where possible, split a criterion into binary, checkable items. For example: "every refinement states issue, rationale, evidence and expected benefit" (SIT §2.3). Rubric anchoring and reference material are what made Prometheus match human scores. arXiv 2604.06996 shows SPB survives even in binary rubrics, so do not stop here.
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
4. Build a **human anchor set**: 10–15 reviews scored blind by 2 team members. Report judge–human agreement (weighted κ) next to human–human agreement as the ceiling. "Judging LLM-as-a-judge" set this standard of comparison.

## 6. How to check each claim on your own data

Log `response.usage`, `stop_reason`, `stop_details`, wall-clock time and tool-call errors for every call in a JSONL file. Each claim above maps to a measurement:

| Claim | Experiment | Metric and decision rule |
|---|---|---|
| Cost per run is $2–3 on Opus 5.5 | Run the agent 5 times on the SIT sample artefact | Sum of `usage` × price per run; median and max. Cache hit ratio = `cache_read_input_tokens` / total input. If the hit ratio is below 0.7, find what is invalidating the cache |
| The document is about 60K tokens | `messages.count_tokens` on the PDF, per model | Actual tokens; rescale the cost table |
| Context and PDF limits hold | `client.models.retrieve(id)` → `max_input_tokens`, `capabilities`; send the real PDF | No 400s; page count under the limit |
| Tool use is reliable | 10 full runs per candidate model (Opus 5.5, Sonnet 5.5, plus the non-Claude option if used) | Turns with a malformed or invalid tool call; unknown-tool-name rate; runs that finish without manual intervention (target ≥ 9/10); MCP timeout rate (warm the containers first) |
| Refusals will not hit live | Run on the sample artefact, plus a security-heavy and an AI-training-heavy design document | Count of `stop_reason == "refusal"` by `stop_details.category`. Any non-zero count on Sonnet 5.5 `frontier_llm` means keep Opus 5.5 as the orchestrator |
| Latency suits a live demo | Same 10 runs | p50/p95 seconds per call and per full run. If p95 per run exceeds about 10 minutes, lower effort or try Opus fast mode |
| **E1: self-preference swap test** | Generate reviews of the same N documents with two agent families (Claude Opus 5.5 and GPT-6.1 Sol or Gemini 3.1 Pro). Grade all of them with judges from both families, 3 samples each | Fit `score ~ author + judge + author:judge + (1|doc)`. The `author:judge` interaction, or the same-family lift "hold the author fixed, compare judges" (Awuni 2026), **is** the self-preference estimate. Report it with a bootstrap 95% CI over documents. Also report weighted κ / Spearman / Krippendorff's α between judges for each criterion |
| E2: position bias (pairwise) | Run every A/B pair in both orders | Consistency rate (target ≥ 0.8); first-position win rate (should be about 0.5) |
| E3: verbosity bias | Add ~30% plausible but irrelevant text to 10 reviews; delete redundant sentences from 10 others | Mean score change (should be ≤ 0 for padding); score–length Spearman across all reviews |
| E4: judge stability | 3 samples per item | Per-criterion SD; share of items with spread > 1 level |
| E5: human validity | 10–15 reviews graded blind by 2 humans | Judge–human quadratic-weighted κ compared with human–human κ. Report both |
| E6: style-driven self-preference | Have model B rewrite model A's review sentence by sentence with the content unchanged, and the reverse (the "equal-quality pair" idea from Yang et al. 2026). Check by diff and human spot-check that content is preserved | Score change when only the authoring style changes |
| Judge-free validity | `eval/synthetic/` planted flaws | Recall and precision of planted flaws. Correlate with judge scores (a judge that does not track planted-flaw recall is suspect) |

**Sample size.** For a paired 0–3 criterion with SD ≈ 0.6, detecting a 0.3-point self-preference at α = 0.05 with 80% power needs n ≈ ((1.96 + 0.84) × 0.6 / 0.3)² ≈ **31 documents**. With the 10–20 documents we can realistically produce, E1 is a **sanity check, not proof**. Report CIs and do not claim "no bias" from a non-significant result. The SD of 0.6 is an assumption; replace it with the SD you observe after the first 10 items.

## 7. Implementation snippets (Claude, verified against the skill)

```python
# Agent call (Python SDK)
client.beta.messages.stream(
    model="claude-opus-5-5", max_tokens=64000,
    thinking={"type": "adaptive"},
    output_config={"effort": "medium"},          # "high" for final synthesis
    betas=["server-side-fallback-2026-07-01"],
    fallbacks="default",
    system=SYSTEM, tools=TOOLS, messages=msgs,   # PDF as a document block, cache_control on the stable prefix
)
# Always: if resp.stop_reason == "refusal": log resp.stop_details and branch before reading content.
# Never: temperature, budget_tokens, tool_choice any/tool, assistant prefill (all 400 on Opus 5.5).
```

The non-Anthropic grader calls (OpenAI Responses API with `json_schema`, Gemini `response_schema`) should be written against each provider's current SDK docs. Their parameter names are not verified here (UNVERIFIED).
