# Agent framework selection for the design review agent

Checked on 2026-10-02. The verified facts, with sources, are in [`comparison.md`](comparison.md). This note covers the decision, the reasoning at each of the eight levels, and the weighted matrix. It is self-contained, so it can be reused outside this project.

## Decision

**Keep the hypothesis, with four corrections.** Build the agent in Python as a thin, explicit state machine (`ingest → understand → plan → research → assess → refine → verify → report`) directly on the **official Anthropic Python SDK (`anthropic==1.11.0`)**, with:

1. **A direct MCP client, not the server-side MCP connector.** Use `mcp==2.2.0` `streamable_http_client` with an `httpx2.AsyncClient(headers={...})`, then `anthropic.lib.tools.mcp.async_mcp_tool` to turn each MCP tool into a runnable tool. The connector only accepts an OAuth `authorization_token`, with no arbitrary headers. It is beta, it supports MCP tools only, and its behaviour on a 1-2 min cold start is unknown. It also gives us no hook to degrade gracefully. *(Correction to "MCP connector **or** direct client".)*
2. **Own the tool loop for the research step (about 40 lines). Do not lean on `tool_runner`.** The tool runner is **beta** (`client.beta.messages.tool_runner`). Anthropic's own docs say to use the manual loop "when you need ... custom logging, or conditional execution". Our stopping rule, budget, per-tool timeouts and evidence logging are exactly that. The runner stays an acceptable shortcut for a self-contained sub-step. *(Correction to "tool runner for tool loops".)*

   > **Superseded (reconciliation 2026-10-02):** the research loop is model-driven only within fixed action *types*: queries and follow-up questions adapt, but the URL policy does not (fetch only URLs from search results or doc references), so tool content cannot add new kinds of action. See `docs/DECISIONS.md` ADR-001 (audit C18).
3. **The SDK does have hidden retries.** `DEFAULT_MAX_RETRIES = 2` and `DEFAULT_TIMEOUT = 600 s`. Set both explicitly in one place and log every retry. *(Correction to "no hidden retries".)*

   > **Superseded (reconciliation 2026-10-02):** the SDK runs with `max_retries=0`; one `LLMGateway` and one `ToolGateway` own retries, backoff, timeouts, breakers and budgets. See `docs/DECISIONS.md` ADR-001 (audit §1.2 item 1).
4. **There is no temperature knob.** SDK 1.x removed `temperature/top_p/top_k` ("Current models do not use these sampling parameters"). Reproducibility therefore has to come from pinned model IDs, frozen prompts, structured outputs and recorded tool responses (see level 6). *(This applies to every framework, not only ours.)*

Structured outputs are **GA** (`client.messages.parse(output_format=Finding)` / `output_config.format`), so typed findings need no beta. The "one-file provider adapter" is real but **not free**: tool schemas and structured outputs are Anthropic-shaped, so a non-Claude adapter is an estimated 150-250 LOC (UNVERIFIED). Treat model swap *within Claude* as one line, and model swap *across vendors* as a prepared fallback, not a live-demo trick.

**The evidence did not overturn the hypothesis.** It did expose two near-misses we would have hit: the connector's auth model, and the mcp 1.x/2.x split, which breaks smolagents out of the box and forces LangChain/LangGraph and CrewAI onto mcp<2.

## Weighted decision matrix

Scores run 1-5. Weights reflect the demo-day reality that the evaluator must *understand* and *watch us change* the agent, which counts as much as raw capability.

| Criterion (weight) | Custom on Anthropic SDK | LangGraph | PydanticAI | OpenAI Agents SDK | LangChain `create_agent` | Claude Agent SDK | CrewAI | smolagents |
|---|---|---|---|---|---|---|---|---|
| 1 Capability (15) | 4 | 4 | **5** | 4 | 4 | **5** | 3 | 3 |
| 2 Explainability (20) | **5** | 4 | 3 | 3 | 3 | 2 | 2 | 3 |
| 3 Live modifiability (20) | **5** | 4 | 4 | 4 | 3 | 3 | 3 | 3 |
| 4 Tool-failure robustness (15) | **5** | 4 | 4 | 4 | 3 | 3 | 3 | 2 |
| 5 Overfitting controls (5) | 4 | 4 | 4 | 4 | 4 | 3 | 3 | 3 |
| 6 Reproducibility (10) | 4 | **5** | 4 | 4 | 4 | 2 | 2 | 2 |
| 7 Cost / latency (5) | **5** | 4 | 4 | 4 | 4 | 3 | 2 | 3 |
| 8 Framework risk to demo day (10) | **4** | 3 | 3 | 3 | 3 | 2 | 2 | 1 |
| **Weighted score (/100)** | **92** | 80 | 77 | 74 | 67 | 58 | 51 | 51 |

**Sensitivity check.** With equal weights the custom loop still leads (90 vs LangGraph 80). With capability-heavy weights (capability 40) it leads 88 vs PydanticAI 84. If we are pessimistic about our own build and score custom capability and robustness at 3 each, it still leads 83 vs LangGraph 80. The ranking is stable, but the margin over LangGraph and PydanticAI is small enough that the conditions below matter.

**Caveat about the custom loop's scores.** Its robustness and capability scores are what *we will build*, not what ships in the box. They assume we actually implement the cold-start, degradation and logging code described below. If we do not, the custom loop drops below LangGraph.

## Justification at each level

### 1. Capability for the review task
The task is a long-horizon research-and-judgement loop: read a PDF, extract objectives and constraints, plan research, call 3 working MCP servers, weigh evidence, revise, verify, and write a traceable report. The raw API covers every part of that. The Messages API accepts PDFs natively as document blocks, so we can bypass the broken document-intelligence server. On top of that it gives us structured outputs (GA), strict tool use, extended thinking, prompt caching (a top-level `cache_control` parameter on `messages.create`), and server-side compaction for long contexts. PydanticAI and the Claude Agent SDK score higher only because they *ship* extras (durable execution, subagents, auto-compaction, a tested harness). None of those extras is needed for one review of one document, and each adds behaviour we would have to explain. We lose nothing the review needs.

### 2. Explainability to a non-author evaluator in a 10-minute walkthrough
With the custom loop, the walkthrough is one file per stage plus `states.py`, which holds an enum and a transition table that we print as a Mermaid diagram. Every prompt is a file in `prompts/`, and every model call is one `client.messages.create/parse` call visible in the code. In under 10 minutes an evaluator can follow "here is the state, here is what the model saw, here is the tool result, here is why we moved on". LangGraph comes close (`get_graph().draw_mermaid_png()` is genuinely good), but explaining channels, reducers, `Command` and ToolNode semantics, plus three packages, eats the time. PydanticAI hides the loop inside `Agent.run` and adds implicit output tools and "Fix the errors and try again." retries. The Claude Agent SDK is a 232 MB bundled CLI subprocess with its own system prompt, built-in tools, tool search and compaction, which makes it the hardest to explain honestly. CrewAI has 36 hidden prompt slices. smolagents' CodeAgent executes model-written Python, which needs a security explanation of its own.

### 3. Live modifiability: what "change it on the spot" costs
The design rule that makes this cheap under *any* framework is: **review criteria, stopping thresholds, tool allowlists and the model ID live in `config/*.yaml`, not in code.** The frameworks then differ only on control-flow changes. The estimates below are for our planned layout, not measured on finished code.

> **Superseded (reconciliation 2026-10-02):** the line counts below are to be replaced by stopwatch rehearsal timings (robustness DEMO-01 to 04, 08). Targets: ≤ 3 min for a config change, ≤ 5 min for a code change; the exact files and lines per modification are in `docs/DEMO_DAY_RUNBOOK.md` §4 (audit C23). A model swap means a change *within the Opus line* or an effort change (`docs/DECISIONS.md` ADR-002; audit C24).

| Request | Custom loop | LangGraph | PydanticAI | Claude Agent SDK | CrewAI |
|---|---|---|---|---|---|
| Add a review criterion (e.g. "security and privacy") | 1 file (`config/criteria.yaml`), +3-5 lines | same | same, plus a field on the output model if typed (2 files, ~5 lines) | 1 file (prompt), +3 lines; the model decides whether to honour it | 1 file (`tasks.yaml`), +3 lines |
| Change the stopping rule (e.g. "stop when every high-risk finding has ≥2 independent sources, or after 6 searches") | 1 file (`policy.py: should_stop()`), ~3-8 lines | 1 file (conditional-edge function), ~5-10 lines | 1-2 files: `UsageLimits` plus an output validator raising `ModelRetry`, ~10-15 lines | 1 file: a `Stop` hook that inspects the transcript, ~15-25 lines; "max N searches" is `max_turns`/budget only | `max_iter` only, so a real rule needs a Flow, ~20+ lines |
| Disable or swap a tool (e.g. drop browser, add a local PDF extractor) | 1 file (`config/tools.yaml`) 1 line; or +1 file (~20 lines) for a new local tool | 1-2 files (client config + tool list) | 1-2 files (toolset list) | 1 file (`allowed_tools` / `mcp_servers`) | 1-2 files |
| Swap the model (Claude to Claude) | 1 line in config | 1 line | 1 line | 1 line | 1 line |
| Swap the model (Claude to another vendor) | prepared `providers/openai.py` (~150-250 LOC, UNVERIFIED) plus 1 config line | 1 line plus a package | **1 line** | not possible | 1 line via LiteLLM |
| Add a new stage (e.g. a "red-team the findings" pass) | 1 new file (~30-50 lines) + 2 lines in the transition table | 1 new node + 2 edges, ~30-50 lines | a new agent plus orchestration code, ~40-60 lines | a subagent definition, ~15 lines, but its order is model-decided | a new agent + task in YAML, ~15 lines, order is framework-decided |

The custom loop wins on the changes evaluators most likely ask for (stopping rule, add a stage, tool behaviour), because the change happens in code the audience has already seen. PydanticAI wins only on cross-vendor model swap.

### 4. Robustness to tool failure
The tools fail in three ways: a 1-2 min cold start, a server that rejects everything (document intelligence), and ordinary search or browser errors. The plan:

- **Pre-warm** all four servers concurrently in `ingest`, using `asyncio.gather` with a 150 s budget and one retry after the first timeout. *(Superseded, reconciliation 2026-10-02: warm only the **enabled** servers; `mcp-document-intelligence` is disabled by default, so normally three. See `docs/DECISIONS.md` ADR-001 and ADR-006 item 4; audit §1.2 item 2.)* The smoke test showed a cold start surfaces as an `ExceptionGroup` wrapping `httpx2.ReadTimeout`, and the immediate retry succeeds once the server is warm.
- **Keep per-server health state** (`ok / degraded / down`). Only tools from healthy servers are offered to the model.
- **Return tool errors to the model** as `is_error` tool results so it can re-plan.
- **Record each failure** in the report's "Limitations / unverified" section.
- **Read the PDF locally.** The document server is skipped on purpose, and the PDF goes to Claude as a native document block, with pypdf text as a fallback.

> **Superseded (reconciliation 2026-10-02):** the model receives the native PDF block **and** one canonical page-marked text (`runs/<id>/doc.pages.txt`) produced by a single pinned extractor, **pdfplumber** (not pypdf). Every verifier (verify stage, matcher, grader, robustness oracles) reads that same text. Text-only is the fallback over 600 pages / 32 MB or if the native block is rejected. See `docs/DECISIONS.md` ADR-006 (audit C14).

How each framework surfaces the same failures (verified in source):

- **LangChain/LangGraph:** transport failures "propagate" past `handle_tool_error`, and ToolNode re-raises non-validation errors by default. That needs wrapper code, and the `mcp<2` pin is required.
- **PydanticAI:** `MCPToolset` defaults to `init_timeout=5` s, so a cold start fails unless it is raised. `tool_error_behavior='retry'` is reasonable.
- **OpenAI Agents SDK:** `max_retry_attempts`, `retry_backoff_seconds_*` and `failure_error_function` are good primitives, but the default timeout is 5 s.
- **Claude Agent SDK:** failed servers do not raise. You must poll `status`, the connect timeout is 30 s, and "Claude can fall back to built-in tools", which is graceful but opaque.
- **CrewAI:** retries the whole task (`max_retry_limit=2`).
- **smolagents:** its MCP client does not import on mcp 2.x.

Graceful degradation is possible everywhere. Only the custom loop makes it *visible* in our own code.

### 5. Overfitting risk
This is mostly architecture, not framework, but a thin loop makes the controls trivial to put in place:

- **A pure entry point** `review(pdf_path, config) -> Report`, called both by the CLI and by the eval harness on `eval/synthetic` (in-distribution) and `eval/blind` (held out). *(Superseded, reconciliation 2026-10-02: `eval/blind` is **not** blind; it is the sealed **S-heldout** set, renamed `eval/heldout/` on sealing, ≤ 3 logged evaluations. A true Blind set is still to be commissioned. See `docs/DECISIONS.md` ADR-004.)* Results go in a per-run JSONL.
- **A lint test** that fails if any prompt or config contains document-specific tokens (titles, component names from the sample artefact).
- **Generic criteria** in `config/criteria.yaml`, reviewed against the SIT success criteria and not against the sample PDF.
- **A frozen prompt hash** recorded in every run log, so a score cannot be quietly tuned between runs.

Frameworks with hidden prompts (CrewAI, the Claude Agent SDK preset, smolagents) make the last control weaker, because part of the prompt is not ours to hash or audit.

### 6. Reproducibility
- **Pin everything:** a lock file (recommend `uv lock`, or `pip-compile` with hashes), with `anthropic==1.11.0` and `mcp==2.2.0` pinned exactly, plus `.python-version` (3.11 or 3.12).
- **Use a dated model snapshot ID** from config. Never use an alias.

  > **Superseded (reconciliation 2026-10-02):** `claude-opus-5-5` has no dated snapshot ID; the bare ID is the most specific pin available. Log `response.model` for every call and reject an eval run whose `served_models` is not `{"claude-opus-5-5"}`. See `docs/DECISIONS.md` ADR-002 and `docs/REPRODUCIBILITY.md` §2 (audit C28, U5).
- **No sampling knobs exist**, so determinism comes from structured outputs (schema-constrained), frozen prompts, and a **record/replay mode**: every MCP call and response is written to `runs/<id>/tools.jsonl` and can be replayed offline. That also protects a live demo against cold starts.
- **Log every model request and response, with usage and `request_id`,** to `runs/<id>/llm.jsonl`.

LangGraph scores 5 here because checkpointing and replay are built in. We are re-creating about 60 lines of that, deliberately. The Claude Agent SDK (0.x, 53 releases in 90 days, a bundled CLI) and CrewAI (94 releases in 90 days, an old pinned anthropic, 137 transitive packages) are the hardest to pin and reproduce.

### 7. Cost and latency
Wall-clock time is dominated by MCP cold starts (up to 4 × 1-2 min if done serially), so concurrent pre-warming is the biggest single latency win, whatever the framework. On token cost, the custom loop sends exactly our prompts and lets us place `cache_control` on the large stable prefix (system prompt + PDF), which is re-read at every stage. The framework options add overhead in different ways:

- **PydanticAI:** output-tool round trips and retry turns.
- **CrewAI:** ReAct scaffolding plus automatic summarisation calls (`respect_context_window=True`).
- **Claude Agent SDK:** the Claude Code system prompt, tool-search turns and subprocess start-up.

Exact per-model prices belong in `research/models/`. They are not repeated here.

### 8. Risk of the framework breaking before demo day
- **Anthropic SDK:** a major release (1.0) landed on 2026-08-20, followed by 11 minor releases. Its changelog shows CI breaking-change detection, and 1.x pinned exactly is low risk over a few weeks. The beta pieces (`tool_runner`, MCP connector) are the parts most likely to change, which is another reason to use neither on the critical path.
- **mcp 2.x:** 2.0 is four months old and renamed core APIs (`streamable_http_client`, `MCPServer`), so pin it exactly.
- **PydanticAI:** v2 is four months old and ships about 5 releases a week.
- **LangGraph:** 1.x is stable, but its MCP adapter is 0.x and pinned to mcp<2.
- **Claude Agent SDK and OpenAI Agents SDK:** both still 0.x.
- **CrewAI:** pins `anthropic~=0.73`, so it cannot share an environment with a current Anthropic SDK.
- **smolagents:** has had no release since May, and its MCP path is already broken on a default install.

## Recommendation

Build on the **official Anthropic Python SDK 1.11.0 with mcp 2.2.0**, using:

- a hand-written state machine;
- a hand-written research tool loop;
- `messages.parse()` for typed findings, each carrying 1-3 `{page, section, quote}` anchors verified in code against the canonical text (*reconciled 2026-10-02: `docs/DECISIONS.md` ADR-007, audit C13*);
- direct MCP sessions with a header-carrying `httpx2` client;
- explicit retries and timeouts, plus pre-warm and per-server health;
- a native PDF document block **plus one canonical page-marked text from pinned pdfplumber**, instead of the document-intelligence server (*reconciled 2026-10-02: `docs/DECISIONS.md` ADR-006, audit C14*);
- JSONL run logs with record/replay;
- a provider adapter interface with only the Anthropic implementation built up front.

## Conditions that would change this

| If... | Switch to |
|---|---|
| The model must be swappable *across vendors* live, or we cannot keep using Claude | **PydanticAI 2.x** (raise `init_timeout` to ≥150 s, set `retries` explicitly) |
| We need **durable human-in-the-loop interrupts**, or the team is already fluent in LangGraph. *(Reconciled 2026-10-02: the earlier trigger "pause/resume across processes" is removed. Resume is a P0 robustness requirement (OPS-04, NET-01, BEH-25) and is met inside the custom loop by a JSON checkpoint after every stage plus `resume <run_id>` and distinct exit codes, about 60 LOC. See `docs/DECISIONS.md` ADR-001 and ADR-009 (the ADR on checkpointing: durable resume, and what would still justify a switch), audit C17.)* | **LangGraph 1.2.x** (pin `mcp<2`, wrap MCP transport errors, set `handle_tool_errors`) |
| Build time collapses to under 2 days, Claude-only is acceptable, and explainability can be argued at the level of hooks | **Claude Agent SDK** (custom `system_prompt`, `setting_sources=[]`, `MCP_TIMEOUT≥150000`, explicit `allowed_tools`) |
| The SIT servers turn out to use `Authorization: Bearer`, stay warm, and we want fewer moving parts | Use the **MCP connector** for search and scholarly tools only, keeping the direct client as fallback |
| Anthropic ships a breaking change to `messages.parse` or structured outputs before the demo | Stay on the pinned version. Do not upgrade after a code freeze one week before the demo. |

Not recommended for this project: **CrewAI** (dependency conflict with current anthropic, heavy hidden prompts), **smolagents** (MCP broken on mcp 2.x, executes generated code, release activity stalled), and **plain LangChain `create_agent`** (all of LangGraph's dependencies without its explicit control flow).
