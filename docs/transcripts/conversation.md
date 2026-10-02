# Coordinator conversation, verbatim

Session `session_01Y3B8MjA3gLDc2s475jzs5m`, 2026-10-02. Coordinator model: Claude Fable 5.1. Subagent reports are reproduced as received. Tool calls are summarised in brackets. Stop-hook messages ("There are uncommitted changes in the repository. Please commit and push") recurred after most turns and are abbreviated to `[stop hook → commit + push]`.

---

## User

> @AI_Engineer_Lab_Exercise.pdf @SIT_Memory_Platform_Detailed_Design.pdf these are the questions that i have to do for ai platform engineering role. can u help me? lets start with an overview, what is expected? why are there 2 documents

## Coordinator

[Read both PDFs in full: lab exercise pp. 1-9; design doc pp. 1-30. Checked repo: empty, branch `claude/eloquent-sagan-ah5ttk` with no commits.]

I've read both documents end to end. Here's the overview. Your repo is currently empty, so nothing exists yet to build on.

### Why there are two documents

They play completely different roles.

- **AI Engineer Lab Exercise (9 pages)** is the assignment. It tells you what to build, how it will be evaluated, what to submit, and what happens on demo day.
- **SIT Memory Platform Detailed Design (30 pages)** is the input data. It is the "design artefact" your agent must read and review. You are not being asked to build the memory platform. You are being asked to build an agent that critiques this document.

Think of it as: document 1 is the exam paper, document 2 is the case study attached to the exam paper.

### What you actually have to build

An autonomous design-review agent. Given a design PDF, it must:

1. Understand the design's objectives, principles, assumptions, constraints, and confirmed decisions.
2. Decide what needs validation, then research it using external sources (standards, docs, papers, vendor info).
3. Judge whether the design is fit for purpose. Identify strengths, risks, gaps, ambiguities, unresolved assumptions.
4. Recommend refinements only where evidence justifies them. Every recommendation needs issue, rationale, supporting evidence, and expected benefit. If no change is needed, it must say why the design is fine.
5. Know when to stop researching and verify its own output is complete, consistent, and traceable.

The key framing in the lab doc: "The goal is not to change designs automatically. The goal is to review, reason and recommend changes only when justified." Evaluators will be looking for evidence-grounded judgement, not an agent that pads out a list of generic suggestions.

### What SIT provides and does not provide

| Provided | Not provided |
|---|---|
| 4 MCP servers: internet search, Playwright browser, scholarly research, document intelligence | Any LLM. You bring your own API key and model |
| A shared API key for those MCP servers | An agent framework. Any approach is allowed |
| The design PDF | A rubric with weights |

Two warnings from the doc: the MCP containers scale to zero and take 1 to 2 minutes to wake, and the document-intelligence server currently rejects all inputs because no allowed roots are configured. So you should plan on parsing PDFs locally and treating the MCP tools as optional helpers, not dependencies.

### How you are evaluated

There are two phases.

**Submission** via a GitHub repo shared with two SIT GitHub IDs (SIT-calebying and Makienhui-sit) before the deadline. It must contain source, prompts, config, orchestration logic, setup and run instructions, and the review output your agent generated on the Memory Platform design, plus the evidence it gathered. No secrets committed. Documentation should cover architecture, framework, context management, planning and execution, tool orchestration, memory and state, validation approach, and known limitations.

**Demo day** on your laptop. Three things happen:
- You walk through the agent design and justify your choices. A short deck is optional.
- They hand you a **new design artefact** you have not seen and run your agent live on it.
- They ask you to **modify the agent on the spot** and show the changed behaviour.

Section 1.5 also says the demo may use an updated version of the design artefact, simulating a second review round after someone incorporated feedback. So your agent should handle "review v2 given that v1 was reviewed" gracefully.

### What this implies for your design

The demo-day format drives most of the architecture decisions.

- **Generalise, do not overfit.** The live artefact is new. Hard-coding anything about the Memory Platform will fail on the day.
- **Make it modifiable in minutes.** Prompts, review criteria, tool selection, and stopping rules should be config or clearly separated modules, so an on-the-spot change is a small edit, not a refactor.
- **Make it robust to tool failure.** MCP cold starts and the broken document server mean the agent needs graceful degradation and should still produce a review if research tools are down.
- **Make it traceable.** Every finding should cite where in the design it comes from and what evidence supports it. This is explicitly in the completion guide and it is what separates a good review from a plausible-sounding one.
- **Show iteration.** Chapter 4 keeps repeating plan, research, assess, refine, know when to stop. A single-pass summariser will not satisfy this. Expect a loop with explicit confidence tracking.

### The design doc itself is a gift

The Memory Platform document is unusually self-aware. Section 28 literally assesses its own code-generation readiness and names three spec gaps. Section 26 lists ten pending backlog items. Section 27 gives a validation matrix. A strong agent should find those, but also go beyond them. Some real things to probe that the document does not flag itself:

- The 48-hour token window with "continue serving on agent backup" when expired, combined with "agent backup survives learner self-deletion", creates a tension with PDPA deletion rights and with Principle 1.
- NFR-2 claims 5 to 15 ms filtered pgvector queries on 9.5M vectors, but HNSW with metadata filters is known to degrade badly when the filter is highly selective. That claim needs evidence or a partitioning strategy.
- The counselling hard wall relies on separate schema credentials, but the Redis L1 cache and Kafka topics are shared infrastructure, so the isolation claim needs checking at every layer.
- Policy decisions are "not cached, evaluated fresh on every request" while reads are cached in Redis. A rule change cannot take effect on cached context packs until TTL expiry, which contradicts the stated rationale.

Those are the kinds of findings that will show evaluators the agent is reasoning rather than paraphrasing.

### Suggested next steps

1. Decide on your LLM provider and framework. I would lean towards a thin custom orchestration loop in Python rather than a heavy framework, because it is easiest to explain and modify live.
2. Agree on the repo layout and the review output format before writing agent code.
3. Build a local PDF ingestion path first, then the review loop, then wire in the MCP tools as optional evidence sources.
4. Run it on the Memory Platform doc, save the output and evidence into the repo, and iterate on quality.
5. Write the documentation and a short demo deck last.

Tell me which framework and model you want to use, or whether you would like me to propose a concrete architecture and repo skeleton and start building it on your branch.

---

## User

> Tell me which framework and model you want to use, or whether you would like me to propose a concrete architecture and repo skeleton and start building it on your branch... can u recmmend to me and why? meanwhile, spawn as many subagents as needed to check on kaggle competitions on which is best fit for this framework and why, each agent should document what it found, so it can be reusable. in the future. and save findings and git push in /research . can also use /deep-research if you want. regarding, the task, every scenario and event must be stress tested and validated, spawn agents to make multiple copies of "fake" data for evaluation. to make it non-bias, spawn agents to give it a task, so it has no context, that will be our deeper /extended eval set?. Be explicit to why we are using each and if unsure, spawn agents to verify. i want it to be research grade. spawn another agent to make sure each section of a "Research-grade" to identify "loophole" is covered? or to verify : eg. eval metric must be XYZ.. ... and further each framework must be justified on afew levels eg. how do we verify it doesnt overfit,, how do we check if its robust to tool failure, this agent is a "lec turer that grades the work". what else and other agents should be spawned? u can spawn it. . u are just the /delegator, to ensure context is clean.

## Coordinator

[Loaded the `claude-api` skill for current model IDs and pricing. Created repo skeleton: README.md, research/README.md, folders research/{kaggle,frameworks,models,methodology,grading,robustness,audit}, eval/{synthetic,blind}. Initial commit. Launched 11 subagents in parallel: Kaggle research, framework justification, model selection, research-grade methodology, lecturer grader, robustness scenarios, three synthetic eval docs (payments orchestration; clinical remote patient monitoring; research data lakehouse; each 14 planted flaws with fixed category/severity counts plus a v2), and two blind items (authors given only "pick a domain, write a design doc, plant 10-16 defects, write a sealed key", with a domain exclusion list).]

All 11 agents are running in parallel. Here is my recommendation while they work, with the reasoning. Two agents are independently verifying it against evidence, and I'll tell you if they disagree.

### Recommendation

**Language: Python.** Evaluators must clone and run it. Python has the widest SDK and MCP client support, and it's what most of the MCP server ecosystem assumes.

**Framework: a thin custom orchestration loop on the official Anthropic SDK, not LangGraph, CrewAI, or similar.** The reason is the demo-day format, not capability. Section 5.4 says evaluators will ask you to modify the agent live and explain the design in a walkthrough. A heavy framework puts hidden prompts, implicit retry loops, and abstractions between you and the model. When an evaluator asks "why did it stop researching here?", you want to point at one function, not a framework internal. Concretely:

- An explicit state machine: ingest, understand, plan, research, assess, refine, verify, report. Each phase is one module with typed inputs and outputs. That maps directly to the lab's Chapter 4 headings, which makes the documentation write itself.
- Review criteria, stopping rules, tool allowlist, and model choice live in one YAML config. "Add a criterion live" becomes a 3-line edit.
- A tool proxy layer wraps every MCP call with timeout, retry, cold-start handling, and a fault-injection hook. That gives you robustness testing for free and makes "disable a tool live" trivial.
- Structured outputs for every finding, so the review is typed data first and prose second. That is what makes traceability and automated grading possible.

The agent framework comparison will push back on this if PydanticAI or LangGraph turns out to be a better fit on the evidence.

**Agent model: Claude Opus 5.5 as the primary** at high effort for the assess and verify phases. It is the current default Opus at $4 per million input tokens and $20 output, with a 1M context window, so a 30-page document plus research fits with no chunking. Sonnet 5.5 for bulk sub-tasks like evidence extraction, at half the cost. I will not recommend Fable 5.1 for the agent: it costs more than double, has longer turn times that are risky in a timed live demo, and runs safety classifiers that can return a refusal mid-run.

**Grader model: deliberately different from the agent model.** LLM judges favour their own family's outputs. The grader should be a different model, or at minimum the same model in a different configuration with position swapping and multiple samples. The model research agent is pulling the published evidence on how large this bias is so we can state it with numbers rather than hand-wave.

### What is running right now

| Agent | Writes to |
|---|---|
| Kaggle competitions and datasets fit | `research/kaggle/` |
| Framework comparison, 8-level justification, weighted matrix | `research/frameworks/` |
| Model selection plus judge self-preference bias bibliography | `research/models/` |
| Research-grade methodology: metrics, splits, ablations, leakage, loophole checklist | `research/methodology/` |
| Lecturer grader: rubric traced to the lab PDF, grader prompt, worked examples | `research/grading/` |
| Robustness: full scenario catalogue with fault injection plan | `research/robustness/` |
| 3 synthetic design docs with 14 planted flaws each plus v2 re-review versions | `eval/synthetic/` |
| 2 blind eval items by agents given no project context | `eval/blind/` |

Once they finish, I'll run a final loophole auditor across everything that was produced, then commit and push to your branch. I will end this turn now and pick up as each agent reports back.

---

## User

> wait, all research agents are all on opus. not fable, its too expensive. can u change it ?

## Coordinator

Understood. Subagents inherit my model unless I set one explicitly, so the 11 running agents are on Fable. I can't switch a running agent, so I'll stop them and relaunch all 11 on Opus.

[Stopped all 11 agents (each had run ~5 minutes; partial outputs discarded with `git clean`). One useful signal before the stop: kaggle.com is blocked from the sandbox, GitHub is reachable. Relaunched all 11 with `model: opus` and the same briefs, adding the network note to the Kaggle brief.]

Done. All 11 agents are stopped, their partial files were discarded, and all 11 are relaunched on Opus with the same briefs. One useful thing surfaced before the stop: kaggle.com is blocked from this environment, so I told the Kaggle agent to go through GitHub solution repos, arXiv papers, and mirrors instead.

Going forward I'll put every subagent on Opus by default, including the loophole auditor I'll run once these finish. I'll stay on Fable only as the coordinator, which is cheap since I'm mostly just routing.

Nothing else needs doing until the agents report back, so I'll end the turn here and pick up as each completes.

---

## Subagent report: Blind eval item A (first Opus attempt)

> I did not finish this task. A safety classifier stopped one of my responses partway through, and I have not tried to recreate the withheld content.
>
> 1. Domain: remote telemetry and control for a regional water utility, called "Remote Telemetry and Control Modernization (RTCM)": 212 remote sites with edge gateways sending MQTT/Sparkplug B data to a central historian, alarm engine and command service.
> 2. Only /home/user/SIT/eval/blind/item_a/design.md exists, and it is incomplete. It has about 3,500 words covering sections 1 to 5 (purpose and scope, background, requirements with IDs, principles, architecture). The rest of the document, sections 6 to 16, is missing. The append that would have added sections 6 and 7 was cut off; the file is unchanged by it.
> 3. I did not write /home/user/SIT/eval/blind/item_a/answer_key.json or /home/user/SIT/eval/blind/item_a/README.md.
> 4. The defect count is 0. I planned 14 defects, but none are in the file yet: sections 1 to 5 are deliberately sound groundwork.
> 5. No git commands were run. Please treat design.md as a partial draft: delete it, or have the item rewritten from scratch (possibly in a different domain). It is not a usable benchmark item as it stands.

## Coordinator

Blind item A's agent hit a safety classifier partway through writing a water-utility SCADA design and stopped. I'll discard the partial file and relaunch it, steering away from critical-infrastructure control systems so it can finish.

[Deleted `eval/blind/item_a`. Relaunched on Opus with domain steered to business software (library lending, timetabling, e-commerce returns, HR/payroll, permits, insurance claims, hotel PMS), excluding utilities, industrial control, water, energy, transport signalling; instructed to write in 1,500-2,500 word appends.]

Blind item A is relaunched on Opus with the domain steered toward business software, away from utility and industrial control systems, and with instructions to write in smaller appends so a single cut-off doesn't lose the whole document. The other 10 agents are still running. I'll wait for their reports.

`[stop hook → commit + push: "WIP: model selection research (agent output in progress)"; first push created the remote branch]`

---

## Subagent report: Model selection research

> Both files are written. I recommend Claude Opus 5.5 for the agent, Claude Sonnet 5.5 for sub-tasks, and a judge from a different provider. All Claude facts and all Gemini prices were checked against official pages. Every OpenAI figure, most Gemini specs and all latency classes are marked UNVERIFIED: the sandbox proxy blocked the official OpenAI and Google docs sites (and Microsoft's), so those came from search results.
>
> 1. **Primary agent: Claude Opus 5.5** (`claude-opus-5-5`, $4/$20 per 1M tokens, 1M context, reads PDFs directly with page-level citations, structured outputs). Run it at `medium` effort for research and `high` for the final write-up, with prompt caching and `fallbacks: "default"` turned on. Anthropic says it is much less likely to cite sources the inputs don't support, which is our main failure mode. Its safety filters cover fewer categories than Sonnet 5.5's: Sonnet 5.5 can also refuse anything that might help build competing AI models, a plausible false alarm on an AI-platform design document.
> 2. **Cheaper sub-task model: Claude Sonnet 5.5** ($2/$10, same 1M context and PDF support). Haiku 4.5 ($1/$5) only fits small triage calls: it has a 200K context and a 100-page PDF limit, and our runs grow past 200K. Fable 5.1 is not worth it: 2.5x the price, single requests can take minutes, and it requires 30-day data retention.
> 3. **Cost per review:** about $2.07 on Opus 5.5 alone with caching, versus about $12 without caching, because each call resends a history that adds up to about 2.9M input tokens over 20 calls. Opus plus Sonnet sub-agents is about $1.85. Budget $2–3 per run. Unverified comparisons: GPT-6.1 Sol about $1.04, Gemini 3.1 Pro Preview about $1.49. Claude's newer tokenizer counts about 30% more tokens for the same text, so measure the real document size first.
> 4. **Grader:** use a judge from a different provider (GPT-6.1 Sol or Gemini 3.1 Pro) at high reasoning effort, with Sonnet 5.5 alongside as a same-family control so the bias can be measured. Score with a per-criterion 0–3 rubric with written anchors, have the judge quote evidence before each score, take 3 samples per review, and blind and normalise the reviews' formatting. Use pairwise comparison only for A/B tests, run in both orders and paired with a length check. Facts that code can check (citations, quotes, planted flaws in `eval/synthetic/`) should be checked in code, not by any model. Grading costs about $0.33 per review per judge.
> 5. **What the evidence says:** 15 papers (2023–2026) all find judges favour their own or same-family outputs. Recent work puts the same-family lift at 3–8 percentage points in head-to-head comparisons, up to 10 points on subjective rubrics, and over 50% more false "pass" marks on objective rubric items when the output is the judge's own. Corrected estimates are smaller than naive ones, but the bias is worst exactly where the agent is wrong.
> 6. **With only an Anthropic key:** we lose the ability to measure that same-family lift at all, so every model-judged score carries an unknown inflation. Partial fixes: rely on code-checked metrics, use Sonnet 5.5 as a different-model judge and label it same-family, add a local open-weight judge such as Prometheus 2 (its quality on long reviews is unverified), and score a 10–15 review human anchor set.
> 7. **Checking it on our own data:** the README lists a test and pass rule for every claim. The main one is a swap test: two agent families times two judge families, with the author-by-judge interaction reported with confidence intervals. The others cover position bias, padding, judge stability, agreement with humans, rewriting the same content in another model's style, refusal counts by category, latency and cost logging. Detecting a 0.3-point bias needs about 31 documents, so with 10–20 the swap test is a sanity check, not proof.
> 8. All of the papers are 2026 ones I could only check at abstract level. The 2025 Preference Leakage paper and the classics are standard, though I couldn't open arXiv for those either. The specific 2026 numbers should be read in full before they go into a submission.
>
> Files are in /home/user/SIT/research/models: README.md, judge-bias-evidence.md, cost_model.py (re-runs the cost tables; edit its price list as prices change)

## Coordinator

[Commit + push "Add model selection research and judge-bias evidence".]

Model research is committed and pushed. Headline from it: Opus 5.5 as the agent, Sonnet 5.5 for sub-tasks, roughly $2 to $3 per full review run with prompt caching, and a judge from a different provider because the published evidence puts same-family judge bias at 3 to 8 percentage points. One caveat it flagged: the proxy blocked OpenAI and Google doc sites, so non-Anthropic prices are marked unverified in the write-up.

Ten agents still running. Waiting on them.

`[stop hook → commit + push: Kaggle in progress]`

---

## Subagent report: Kaggle benchmark research

> The Kaggle research is written up in `/home/user/SIT/research/kaggle/README.md` (overview, top 5, recommendations, how to reuse) and `/home/user/SIT/research/kaggle/candidates.md` (20 Kaggle competitions or platforms, 8 Kaggle datasets and 9 non-Kaggle resources). The main finding: no Kaggle competition has ever targeted peer review, design or architecture review, requirements quality or technical-document QA, as far as searches could find. Kaggle's value here is techniques, not domain data.
>
> kaggle.com, Hugging Face, arXiv, archive.org, r.jina.ai and most blogs were blocked by the proxy. Facts are tagged [GH] when I read them first-hand from GitHub files, [S] when they come only from a web-search snippet, and UNVERIFIED otherwise. Kaggle data licences and most details of the winning writeups are [S] or UNVERIFIED.
>
> Top findings:
> 1. **#1, Chatbot Arena preference competitions (LMSYS 2024, WSDM Cup 2025).** These are effectively "make an LLM judge agree with humans" contests, and their code is public [GH]. Score both answer orders and average: a small judge changed its verdict on 29.2% of pairs when the order was swapped. Allow ties, and turn the A/B log-probs into a calibrated score. Keep the head and tail of long inputs, and use large-to-small distillation (WSDM 1st place). Human labels carry a strong length bias: "longer answer wins" alone is right 58.4% of the time on 48,439 pairs.
> 2. **#2, RevUtil (not on Kaggle, CC BY-NC-SA).** 1,430 three-rater human labels plus 10k synthetic labels on Actionability, Grounding & Specificity, Verifiability and Helpfulness. These map almost one-to-one onto the SIT issue / rationale / evidence / benefit requirement [GH]. It is the best rubric source for our grader.
> 3. **#3, Feedback Prize – Predicting Effective Arguments plus PERSUADE 2.0 (CC BY-NC-SA [GH]).** The only Kaggle data with expert Effective / Adequate / Ineffective ratings on individual claims, evidence and rebuttals. The 1st-place insight transfers: score all elements of one document together in a single pass [S].
> 4. **#4, ReviewCritique.** Expert labels for deficient review segments, the best benchmark for the agent's self-verification step. Its licence forbids training on it [GH].
> 5. **#5, Automated Essay Scoring 2.0.** Gives the method for an ordinal rubric grader: measure agreement with QWK. The winner went from 619th public to 1st private by noticing that two label sources were graded to different standards [S]. That is a warning about our LLM grader versus the SIT evaluators.
> 6. **Expert reviewers agree only moderately.** Two ICLR reviewers' scores on the same paper correlate at 0.40 [GH]. Measure human-to-human agreement before trying to improve the grader's.
> 7. **LLMs – You Can't Please Them All (2024–25)** was a Kaggle competition on attacking a panel of LLM judges. It is useful for red-teaming our grader, but has no labelled data and no winning writeup I could read.
> 8. **Smaller reusable techniques [S]:** Eedi: retrieve candidates, then rerank in a cascade, to map findings onto a standards catalogue. MAP 2025: report results over multiple seeds, because single runs mislead on small eval sets. Konwinski Prize: test on items written after the agent is frozen, which matches our `eval/blind`. The `kaggle-benchmarks` SDK (Apache-2.0 [GH]) could host our eval as a reproducible benchmark.
> 9. **Low fit (reasons in candidates.md):** CommonLit Readability, AI4Code, PII Detection, Detect AI Text, Feedback Prize ELL, Standardized Agent Exams, and LLM Science Exam as data. Jigsaw Rules 2025 and the 2026 long-context Track3 competition fit in concept, but no winning technique could be verified.
>
> The README also lists ten concrete grader and agent practices drawn from these sources. It advises against fine-tuning on Kaggle essay or chat data and expecting it to transfer to design reviews. No git commands were run, and nothing was written outside `research/kaggle/`.

## Coordinator

[Commit + push "Add Kaggle benchmark and technique research".]

Kaggle research is committed and pushed. The honest headline: no Kaggle competition has ever targeted design or technical-document review, so Kaggle's value here is techniques, not data. The most useful transfers are the Chatbot Arena judge tricks (score both answer orders, since one judge flipped its verdict on 29% of pairs when swapped), the RevUtil review-quality dataset whose four labels map almost directly onto the lab's issue/rationale/evidence/benefit requirement, and a warning from the essay scoring competition that two label sources graded to different standards, which is exactly the risk between our LLM grader and the SIT evaluators.

Nine agents still running. Waiting.

`[stop hook → commit + push]`

---

## Subagent report: Framework selection justification

> The hypothesis holds, with four corrections: build a custom state-machine loop on anthropic 1.11.0 with mcp 2.2.0. I wrote both files, /home/user/SIT/research/frameworks/README.md (decision, weighted matrix, the eight-level justification, when to switch) and /home/user/SIT/research/frameworks/comparison.md (per-framework facts with URLs, checked 2026-10-02, open items marked UNVERIFIED).
>
> 1. **Matrix result:** custom loop 92/100, LangGraph 80, PydanticAI 77, OpenAI Agents SDK 74, plain LangChain 67, Claude Agent SDK 58, CrewAI 51, smolagents 51. Custom still leads with equal weights, with capability weighted heavily, and with pessimistic scores for our own build. Its lead depends on actually building the pre-warm, degradation and logging code.
> 2. **Correction, MCP:** use a direct MCP client, not the server-side MCP connector. The connector only accepts an OAuth `authorization_token` (no custom headers), is beta, and supports MCP tools only. Instead, `httpx2.AsyncClient(headers=...)` with `streamable_http_client` and the SDK's `async_mcp_tool` worked in a local smoke test. A cold start shows up as an `ExceptionGroup` wrapping `ReadTimeout`, and one retry after the server wakes succeeds.
> 3. **Correction, tool loop:** write our own research loop (about 40 lines). `tool_runner` is beta, and Anthropic's docs say to use the manual loop when you need custom logging or conditional execution, which our stopping rule and budget are.
> 4. **Correction, retries:** the SDK does have hidden retries (`DEFAULT_MAX_RETRIES=2`, 600 s timeout). Set both explicitly.
> 5. **Correction, determinism:** SDK 1.x removed `temperature`/`top_p`/`top_k` because current models do not use them, and this applies to every framework. Reproducibility has to come from pinned model IDs, frozen prompts, structured outputs (GA via `messages.parse`) and recording/replaying tool calls.
> 6. **Ecosystem split on MCP 1.x vs 2.x:** langchain-mcp-adapters and CrewAI require mcp<2 (pip confirmed the conflict). I confirmed smolagents is broken on a fresh install: its MCP client raises `ImportError` because mcp 2.x renamed `streamablehttp_client`. CrewAI's `[anthropic]` extra also pins anthropic ~0.73 and cannot install alongside 1.11.0.
> 7. **Cold-start defaults:** PydanticAI's MCP connection fails after 5 s by default, OpenAI Agents after 5 s, and the Claude Agent SDK after 30 s; all are too short for a 1-2 min wake unless raised. The Claude Agent SDK bundles a 232 MB CLI and its own system prompt, which hurts explainability.
> 8. **When to switch:** PydanticAI if the model must be swappable across vendors (it is a one-line change there, versus an estimated 150-250 line adapter for us); LangGraph if we need pause/resume across processes. The document server should be bypassed by sending the PDF to Claude as a native document block.
> 9. **Unverified:** The auth header name the SIT servers expect. The proxy here blocked those hosts. It decides whether the connector is even an option. The connector's timeout on a cold start. Some CrewAI details. The size of the cross-vendor adapter.
> 10. **How facts were checked:** the proxy blocked the docs sites for PydanticAI, LangChain and the OpenAI Agents SDK, and the GitHub API. For those, facts come from reading the published package source for each pinned version. The smoke test and install checks ran only in a temporary folder, and I ran no git commands.

## Coordinator

[Commit + push "Add framework selection research with weighted comparison".]

Framework research is committed and pushed. It confirms the custom state-machine loop recommendation, scoring it 92 out of 100 against LangGraph at 80 and PydanticAI at 77, but with four corrections I'll carry into the build:

- **Use a direct MCP client, not Anthropic's server-side MCP connector.** The connector only takes an OAuth token and can't send the custom API key header SIT's servers need. The agent smoke-tested a direct client and confirmed a cold start surfaces as a read timeout that succeeds on one retry.
- **Write our own 40-line tool loop** rather than the SDK's beta tool runner, since our stopping rule and budget need custom control.
- **Set SDK retries and timeout explicitly.** The SDK silently retries twice by default, which would hide failures from our robustness tests.
- **Temperature no longer exists on current models**, so reproducibility must come from pinned model IDs, frozen prompts, structured outputs, and recorded tool calls.

It also found that several frameworks are currently broken on fresh installs due to an MCP 1.x versus 2.x split, which is a good argument to put in the demo walkthrough.

Eight agents still running.

---

## Subagent report: Research-grade eval methodology

> I wrote the methodology spec and the formal metric definitions to `/home/user/SIT/research/methodology/`. I ran no git commands and wrote nothing outside that folder.
>
> 1. **Files.** `README.md` (about 7.4k words) is the spec and covers all 9 parts of the brief. `metrics.md` (about 4.9k words) has the formulas, the matching procedure, Python-style pseudo-code, and a worked example (nDCG 0.669, F1 0.444 strict / 0.545 adjudicated) that a scoring implementation should reproduce as a unit test.
> 2. **Matching a finding to a planted flaw.** A finding gets candidate flaws from section overlap, embedding similarity and an LLM shortlist. A matcher model from a different family than the agent then scores each pair 0–3, and a finding only counts as a match if it states the flaw's key point, not just its topic. Each flaw is credited at most once (Hungarian assignment); strict = score 3, lenient = 2 or more.
> 3. **Unmatched findings** go into six classes, including "valid but not in the key" and "hallucinated". A human checks every finding in those two classes. Precision is reported both strict and adjudicated. Before use, the matcher must agree with humans at κ ≥ 0.80, and a generic-checklist baseline must score recall ≤ 0.05.
> 4. **Metrics cover everything you listed**, plus a few extras tied to the lab PDF: preserving approved decisions (§1.3), stale findings and new-flaw recall on the v2 re-review (§1.5), and research yield and overrun for knowing when to stop (§3.2).
> 5. **Splits and leakage.** Splits are dev, held-out (at most 3 evaluations), blind (1 evaluation), out-of-domain, and the real SIT doc kept separate from any generalisation claim. Six leakage rules are paired with a six-step audit (term grep, n-gram overlap, canary strings, access scan, paraphrase probe, template-tell probe). One concrete risk: if the repo is public, an agent with web search can find the answer keys, so keys must be encrypted and the repo's domains blocked in the search tool.
> 6. **Baselines and ablations.** The spec defines baselines B0, B0-$ and B-gen, ablations A1–A5, and a human ceiling H. Each comes with a category-specific prediction to pre-register, all use the same output schema, and cost is reported throughout.
> 7. **Statistics.** Use at least 3 runs per doc (5 preferred), a doc-then-run cluster bootstrap, and paired differences. Correct the main comparisons with Holm and the per-category breakdowns with Benjamini–Hochberg. From the power calculations: detecting a 10-point recall difference takes about 33 docs of 8 flaws; about 15 blind docs can only rule out a large gap (≥ 0.15); trusting the LLM grader needs at least 100 doubly graded reviews.
> 8. **Overfitting.** The dev-to-blind gap is compared against the untuned B0 baseline's gap, because a harder blind set can cause a drop on its own. Further checks are reordering and paraphrase tests, an out-of-domain doc, and clean-versus-flawed pairs. The README also covers robustness reporting (fault-free and fault-injected runs reported separately, failed runs counted, disclosure rate), the run-manifest YAML, and a 10-table results template.
> 9. **Loopholes.** There are 40 numbered items in four groups (leakage, dataset construction, agent gaming, analysis), each with a control and the evidence the report must show.
> 10. **Sources and what is unverified.** All 43 references were checked by web search; arxiv.org could not be fetched, so details come from search summaries. Marked UNVERIFIED or PROPOSED DEFAULT: all numeric thresholds, the intra-doc correlation values behind the sample sizes, the "overrun" metric, the exact pass^k estimator, the claim that SPOT never validated its matcher, the SPOT author list, the `krippendorff` package API, and the content of arXiv:2605.08545.
>
> **Open item:** the default flaw taxonomy is aligned to lab §2.3 and should be replaced by the project taxonomy once it exists, since `research/` had no taxonomy file.

## Subagent report: Lecturer grader rubric design

> I wrote the three grading files; the grader has not been run on a real review yet.
>
> 1. **Rubric** (`/home/user/SIT/research/grading/README.md`): 10 dimensions scored 0–4 with descriptors per level, plus an optional D11 for re-reviewing an updated artefact. Every criterion is tied to a verbatim quote from the lab brief with page and section. Weights: evidence/traceability 16, recommendation quality 14, fitness verdict 12, restraint 10, intent 10, coverage 10, triage 8, research sufficiency 8, consistency/accuracy 8, professional quality 4.
> 2. **Pass rule**: weighted score ≥ 60 and all gates pass. Failing gates are any dimension at 0, evidence/recommendations/restraint below 2, two or more material hallucinations, a missing verdict, or text aimed at the grader. One material hallucination caps the grade at C. A needs ≥ 85 with no dimension below 3.
> 3. **Protocol**: a split-into-findings step, then Pass A (findings shuffled, scored one by one, two samples) and Pass B (whole review, two samples). Pass B starts with the grader listing the issues it sees before reading the review. Quoted design text is checked by string match in code. Any dimension differing by 2 or more triggers a third sample and a human-review flag. Key-blind is the headline score; key-aware runs in a separate context and never penalises valid findings outside the key.
> 4. **Grader prompt** (`/home/user/SIT/research/grading/grader_prompt.md`): the full system prompt, both user-message templates, the splitter prompt, two output schemas (checked as valid JSON Schema 2020-12), a harness report example and the answer-key format. Hallucinations are only marked "verified false" when the grader can show the contradiction; otherwise they are "suspected" and don't trigger caps.
> 5. **Human calibration**: one person blind-scores 5 reviews spanning strong, mediocre, padded, terse and hallucinated. Targets are weighted kappa ≥ 0.6, within-1 agreement ≥ 90%, score gap ≤ 8 points, and 5/5 pass/fail agreement. Fixes are re-checked on 5 new items, not the same ones.
> 6. **Grader validation**: 13 controlled tests (V1–V13) built from one competent review scoring 75. A heavily padded version should score 63 and fail on restraint; a terse correct version should score 75–78.5. Other tests cover a correct "no change" (must not lose marks), injected fake sources and false gaps, reordering, style changes, injected grader instructions, and re-opening confirmed design decisions.
> 7. **Worked examples** (`/home/user/SIT/research/grading/worked_examples.md`), on the Memory Platform doc: **A (100):** the pgvector issue. The approximate index applies the learner/slot filter only after its search, so "500–800 vectors searched" is unproven, and the NFR-2 test measures latency only. Supported by quotes from the pgvector README that I fetched and checked. **C (61.5):** a finding that only restates the doc's own self-assessment in section 28. **Looks good, scores low (14.2):** a fake "PDPA s.22A right to erasure", a misattributed HNSW paper, and "migrate to Pinecone" against a confirmed decision. **Bonus (94.6):** a correct "no change needed".
> 8. **Answer key** (illustrative): 10 key issues, 6 traps and 3 no-change areas, all checked against the PDF. A strong example is that Gateway Check 4 calls the admin plane during a live request, contradicting NFR-4.
> 9. **Unverified citations**: the XACML 3.0 reference (in the A-grade rewrite of the C example) and the HNSW paper's bibliographic details come from memory. The PDPA s.16/s.25 points come from a secondary source (IAPP), and the official statute site was not checked. The Microsoft token-lifetime question was left out because the docs site was blocked.
> 10. **Demo-day checklist**: likely evaluator probes for the four demo-day parts in section 5.4 and what earns marks, plus a 12-item rehearsal sheet. It flags that the MCP containers take 1–2 minutes to wake from idle, so warm them up before the live run.

## Coordinator

[Commit + push "Add research-grade evaluation methodology and metric definitions" (grading files swept into the same commit).]

Both the methodology and the grading work were already captured in the last push, since the grading files landed just before that commit. Everything is on the remote.

Six research deliverables are now done: models, Kaggle, frameworks, methodology, grading. Two things worth noting from the latest two:

- **The methodology spec flags a real leakage risk.** If the repo is public, an agent with web search could find its own answer keys. The keys need encrypting and the repo's domain blocked in the search tool before any blind evaluation counts.
- **The grader found a strong finding on the real SIT document** while writing worked examples: Gateway Check 4 calls the admin plane during a live request, which contradicts NFR-4's claim that the admin plane is never in the request path. That's a good seed for the agent's first real run.

Still running: robustness scenarios, three synthetic eval docs, and both blind items.

---

## Subagent report: Robustness and stress scenarios

> I wrote the scenario catalogue and the test plan: **166 scenarios**, of which 81 must pass before submission (P0), 68 before demo day (P1) and 17 are stretch goals (P2). Each scenario has a stable ID, category, trigger, expected behaviour, a deterministic way to simulate it, a pass/fail criterion, severity, priority and test level. Nothing has been run yet; these are the tests to build.
>
> 1. **Categories:** MCP tool and infrastructure failures (28), LLM API failures (12), network (5), input variations (32), adversarial content (24), agent behaviour (28), demo day (15), overfitting (12). I added an operational/environment category (10): fresh-clone reproduction, committed secrets, Ctrl-C and resume, awkward file paths.
> 2. **Facts from the brief that shaped the scenarios:** The shared key means one 401 disables all four servers at once. The key is printed in the brief, so a check that it never enters git history is P0. The document-intelligence server rejects everything, so local parsing must be the primary path. Scale-to-zero means a cold start is the normal first call on demo day, and it also drops MCP sessions (the spec requires re-initialising after a 404). The browser server keeps one Chromium session shared by every participant, so another user can change the page between our calls. DuckDuckGo signals rate limits inside an HTTP 200 response.
> 3. **Sample-document traps:** the requirements tables span pages 3 to 5, Figure 1 exists only as an image, section 8 has a heading but no text, and it cites a companion "Conceptual Design" that isn't supplied.
> 4. **Shared invariants:** 11 checks run after every test (INV-01 to INV-11). They include: always terminates, every finding's quote resolves to the doc, every citation resolves to a real tool call, degradations are disclosed, no secret leaks, approved decisions are preserved.
> 5. **Three test levels:** **L0:** fake LLM, fake or replayed tools and a virtual clock. Offline, under 60 s, so a 90 s cold start costs about 0 ms. **L1:** real LLM with recorded tool responses, run k times and scored as pass^k. Attack success rate and secret leaks must be zero in every run. **L2:** live servers, time-boxed rehearsals.
> 6. **Fault injection:** faults go in below the agent's retry and circuit-breaker logic, so that logic is what gets tested. One YAML schedule per scenario ID covers MCP, LLM, network and process faults (19 fault types). Real TLS, DNS and bandwidth faults use Toxiproxy or OS network isolation.
> 7. **Fixtures:** recorded MCP responses with strict replay and key redaction, which also give an offline fallback for the demo. Test documents are generated reproducibly (scanned, hidden-text, corrupted, 150-page, renamed, paraphrased, v2 variants), each with an answer-key file. Injection tests compare a clean twin against an injected twin.
> 8. **Priorities:** README section 4.2 gives a 20-item minimum gate if time runs short, then an implementation order (harness first) and a demo rehearsal protocol: 5 runs on held-out docs, servers left idle 30+ minutes so they start cold, 10-minute stopwatch, one random live change per run.
> 9. **Results template:** a CSV header plus a markdown table with status values and a per-tier summary.
> 10. **Caveats:** thresholds such as overlap ≥ 0.7 and recall ≥ 0.8 are my initial guesses and need calibrating once the agent exists. The live servers' error codes and MCP protocol version are inferred from the docs and should be confirmed on the first recording session. Without a local LLM, a fully offline laptop can only fail cleanly or replay recorded runs; it cannot review an unseen doc.
>
> README section 10 also lists 11 things the architecture needs for these tests to be passable (central tool and LLM gateways, an evidence ledger the model cites by ID, a decision registry, checkpoints, config-driven criteria and stop rules, an `explain` command), and it cites 37 references with URLs. I spot-checked several of the newer references by web search. arXiv itself was blocked from this environment, so the remaining arXiv IDs are from memory.

## Coordinator

[Commit + push "Add robustness scenario catalogue and stress-test plan".]

Robustness catalogue is committed and pushed: 166 scenarios across 9 categories, 81 of them must-pass before submission, with a three-level test design (offline fakes, real LLM with recorded tools, live rehearsals). Two findings from the brief that I hadn't spotted and that shape the build:

- **The shared MCP API key is printed in the lab PDF.** A check that it never enters git history is now a must-pass test.
- **The browser MCP server shares one Chromium session across all participants**, so another candidate can change the page between our calls. That tool should be treated as unreliable by default.

All six research notes are now done. Remaining: three synthetic eval docs and two blind items, all still running. Once they land I'll run the loophole auditor across the whole `research/` and `eval/` tree.

---

## Subagent report: Blind eval item B

> 1. Domain: the control system for a 2 MW / 4 MWh battery store at a fictional cold-storage warehouse that also has 1.8 MWac of rooftop solar. It covers the 500 kW export cap, utility demand-response events and backup power for a 380 kW critical feeder, under US grid and battery rules (IEEE 1547-2018, UL 9540, NFPA 855, IEEE 2030.5).
> 2. `/home/user/SIT/eval/blind/item_b/design.md` is about 8,900 words (excluding table markup), in 15 numbered sections with requirement IDs. It covers scope, requirements, principles, architecture, interfaces, key flows, safety, security, governance, operations, decisions, open items, acceptance criteria and a phased plan. No defect is labelled or hinted at; I checked the file for hint words.
> 3. There are 14 defects: 1 critical, 7 high, 6 medium. Four need an outside fact to confirm: IEEE 1547 requires an island trip within 2 s; the document says 5 s. A single Modbus read is limited to 125 registers; the document reads 200 in one request. UL 9540A is a test method, not a certification. IEEE 2030.5 requires TLS; the document sends it as plain HTTP.
> 4. Three defects are safety-relevant: an emergency stop that works through controller software, the inverter holding its last power command forever if communication is lost, and the 5 s island trip time. The rest are cross-section inconsistencies: a 5 s meter refresh against a 2 s export limit; a peak-shaving energy check that ignores the 35% backup reserve; a 99.95% availability claim alongside 48 h/yr of planned maintenance; planned battery cycling above the warranty's 365 cycles/yr; a supplier VPN that bypasses the DMZ; NTP time sync claimed at ±1 ms; unplanned islanding never tested; utility settings scheduled after grid-connected energisation.
> 5. `/home/user/SIT/eval/blind/item_b/answer_key.json` (valid JSON) gives each defect's location, why it matters, what a review must say for credit, and an acceptable fix. It also lists 9 deliberately sound sections with the false flags a careless reviewer might raise there. `/home/user/SIT/eval/blind/item_b/README.md` explains the item and confirms no defect is labelled. I ran no git commands.

## Coordinator

[Validated key JSON (14 defects, 9,866 words). Commit + push "Add blind eval item B: battery energy storage control system".]

Blind item B is validated and pushed: a battery energy storage control system design, about 9,900 words, with 14 defects including 4 that require checking an external standard and 3 that are safety-relevant. This one went through fine despite being an energy-control domain, so the earlier classifier stop on item A was specific to that draft rather than the category.

Still running: three synthetic docs and the blind item A retry.

`[stop hook → commit + push]`

---

## Subagent report: Synthetic eval doc: clinical IoT

> 1. **v1 is written:** `/home/user/SIT/eval/synthetic/clinical_rpm/design_v1.md` is a 24-section remote patient monitoring design for a fictional Singapore cluster (HPHC), about 7,600 prose words, with requirement IDs FR-1–16, NFR-1–12, P1–P9, D-1–20 and B-1–8.
> 2. **14 flaws are planted, none labelled:** 4 critical, 6 major, 4 minor, in the requested category counts. Examples: IoT Hub S2 quota stated as 60M/day (Microsoft's documented figure is 6M), the device group-enrollment key shipped in firmware, a single-replica alert dispatcher with no heartbeat, ML made the primary home-patient alert while its HSA review is still in the backlog, and Stream Analytics dropping late events despite device clock skew. Five sound sections are recorded as traps for over-eager reviewers.
> 3. **v2 is written:** `/home/user/SIT/eval/synthetic/clinical_rpm/design_v2.md` fixes 6 flaws (F02, F04, F07, F08, F10, F12: 3 critical, 2 major, 1 minor) and leaves 8 unchanged. The F10 fix introduces a new major flaw, F15: a blocking first-in-first-out delivery queue with no expiry and no dead-letter queue. v2 is about 8,300 prose words.
> 4. **Answer key is complete:** `/home/user/SIT/eval/synthetic/clinical_rpm/answer_key.json` (valid JSON) has 15 flaw entries with all requested fields, 5 sound sections, the per-flaw v2 status, and scoring guidance.
> 5. **README and PDFs are done:** `/home/user/SIT/eval/synthetic/clinical_rpm/README.md` has the usage paragraph and the no-label checklist, checked by grep across both docs. I checked page images of both PDFs and they render cleanly. The container's LibreOffice had no Writer component, so I installed `libreoffice-writer-nogui` with apt to make the conversion work; the README notes this.
> 6. **Caveats:** the IoT Hub figures (S2 6M/day and 120 msg/s, S3 300M/day and 6,000 msg/s) are from my own knowledge and were not looked up during this run. v2's new FR-7 acceptance test (d), a device with its clock 10 minutes behind, would in practice expose the unchanged late-event flaw (F11), and the key says to credit that. No git commands were run.

## Coordinator

[Validated (15 flaws, 5 sound). Commit + push "Add synthetic eval item: clinical remote patient monitoring (v1, v2, key)".]

Clinical remote patient monitoring item is validated and pushed: v1 and v2 in markdown and PDF, 14 planted flaws plus the v2 regression flaw, 5 sound-section traps. One caveat it flagged for the audit: the Azure IoT Hub quota figures it used as a "checkable against vendor docs" flaw came from memory, not a lookup, so the auditor should verify them.

Remaining: two synthetic docs and blind item A.

---

## Subagent report: Blind eval item A (retry)

> 1. Domain: e-commerce order management and returns. The design document describes "Meridian", a fictional replacement for a retailer's old order system, trading online in the UK, Ireland, Germany, the Netherlands and France and built on AWS. It is in `/home/user/SIT/eval/blind/item_a/design.md`: about 8,400 words of prose in 13 numbered sections plus a glossary, with requirement IDs, written in four appends.
> 2. It contains 14 defects: 2 Critical, 6 High, 5 Medium, 1 Low. Six need an external fact to confirm: EU/UK rules on refund timing and on refunding delivery charges, the DynamoDB 400 KB item limit, the 14-day SQS retention maximum, how SQS FIFO message groups serialise processing, and GDPR erasure rules combined with how S3 Object Lock compliance mode works.
> 3. The other defects are spread through the document: return window counted from order date instead of delivery date, event lost because the order write and the event publish are not atomic, a new PSP refund idempotency key on every retry, an unauthenticated return-status endpoint with guessable IDs that shows names and addresses, a 99.95% availability target that a 99.5% fraud-check dependency makes impossible, money stored as floating point, a rollback that strands orders already in Meridian, and a load test run at only half of peak.
> 4. The answer key is `/home/user/SIT/eval/blind/item_a/answer_key.json` and is valid JSON. For each defect it gives category, severity, location, why it matters, what a review must say for credit, and a fix. It also lists 8 deliberately sound areas, such as the lawful return exclusions, the return-shipping charge and the notification queues, and says what a careless reviewer would wrongly flag there.
> 5. `/home/user/SIT/eval/blind/item_a/README.md` describes the item and confirms no defect is labelled or hinted at in the document; a word search found no marker terms. Before seeding the defects I removed several accidental errors (Aurora PostgreSQL has no backtrack, the German retention period, the mattress hygiene ruling, and a decommission date inside the change freeze). I wrote only the three files and ran no git commands.

## Coordinator

[Validated (14 defects, 9,440 words). Commit + push "Add blind eval item A: e-commerce order management and returns".]

Blind item A retry succeeded and is pushed: an e-commerce order management and returns system, about 9,400 words, 14 defects, 6 of which require checking an external fact such as consumer-rights refund rules or AWS service limits. Both blind items are now complete.

Remaining: payments orchestration and research lakehouse synthetic docs. Once those land I'll launch the loophole auditor.

`[stop hook → commit + push]`

---

## Subagent report: Synthetic eval doc: data platform (research lakehouse)

> 1. I wrote `design_v1.md` (8,422 words, 24 numbered sections, FR-1..15 and NFR-1..12) for "Westmoor University Research Data Lakehouse and Retrieval Platform", a fictional institution. It follows the reference document's structure: scope, requirements, principles, architecture, data model, flows, governance, prior art, confirmed decisions, pending backlog, acceptance criteria, readiness and build phases. The stack is S3, Iceberg, Polaris, OPA, Trino/Spark, and RAG on OpenSearch.
> 2. It plants exactly 14 flaws in the requested category counts, rated 4 critical, 6 major and 4 minor. The critical ones are F01 (Restricted content sent to an external LLM, against the no-external-processing requirement), F03 (consent-withdrawal erasure undone by snapshot, tag and object-version retention), F08 (a faculty-wide service credential in notebook environment variables) and F09 (a faculty-scoped answer cache that leaks embargoed content). F04 can be checked against AWS docs: it relies on the opt-in Intelligent-Tiering Deep Archive tier, which needs a restore before reads. F05 can be checked against OpenSearch's k-NN memory formula: it counts float32 vectors as 1 byte per dimension.
> 3. Five sections are deliberately sound and recorded in the key as traps: §4 classification tiers, §6 identity and roles, §9 ingestion (write-audit-publish), §14.6 latency budget, and §16 audit plane. Each has a note on what a weak reviewer would wrongly flag there.
> 4. `design_v2.md` (8,997 words) fixes F03, F05, F06, F08, F10 and F13 (2 critical, 2 major, 2 minor). The F10 fix adds a new critical flaw, F15: an active-active cross-region Iceberg catalog with last-writer-wins replication, which can silently lose commits. The other 8 flaws are unchanged; I checked that with grep. It includes a neutral "Changes since 1.0" list that names only the sections touched.
> 5. `answer_key.json` contains every field you specified, plus a `v2_new_flaws` array holding F15. I recorded F10 as "regressed" with `new_flaw_id` F15 and a note that its original single-point-of-failure issue is resolved. The README is one paragraph plus a no-label checklist; a regex scan found 0 flaw-hinting words in either document.
> 6. Both PDFs converted successfully (python-markdown, then `soffice` with the Writer/Web PDF filter: 28 and 29 pages). All files are in `/home/user/SIT/eval/synthetic/research_lakehouse/`: `design_v1.md`, `design_v1.pdf`, `design_v2.md`, `design_v2.pdf`, `answer_key.json` and `README.md`. Nothing was committed to git.

## Coordinator

[Validated (14 flaws, 5 sound); already captured in the preceding WIP push.]

The research lakehouse item was already captured in the push a moment ago, so it's on the remote: 14 flaws, 5 sound-section traps, both PDFs rendered. Only the payments orchestration item is still running, and its three core files are already on disk, so it's close.

Once it reports, I'll launch the loophole auditor over everything.

---

## Subagent report: Synthetic eval doc: payments

> 1. `design_v1.md` (about 8,200 words, 28 sections) is a design for a fictional SEA fintech, "Serindit Pay", in the same shape as the reference PDF. It has 14 planted flaws (4 critical, 6 major, 4 minor) in exactly the category counts you asked for, plus 5 sound sections: ledger, amounts/FX, webhooks, back-office console and prior art.
> 2. The quantitative flaw that can be checked against vendor docs is F04: the doc claims 10,000 WCU per DynamoDB partition, but AWS documents 1,000, and it keys by merchant_id with an LSI. The other critical flaws are F06 (cites PCI DSS 3.2.1/3.3.2 as allowing CVC retention until settlement), F08 (payout bank account can be changed without MFA), F10 (a timed-out payment is cascaded to another acquirer, which can double-charge), and F01 (full PAN goes to the fraud vendor from a service declared out of PCI scope). F09, the subtle security gap, is the Redis idempotency key missing the merchant scope.
> 3. `design_v2.md` (about 8,900 words) fixes 6 flaws: F02 and F12 (minor), F03 and F04 (major), F06 and F08 (critical). The F04 fix adds a new critical flaw, F15: a two-region writable DynamoDB global table with a false claim that its conditional write guarantees one winner across regions. The other 8 flaws are unchanged.
> 4. `answer_key.json` has every field you specified. I added `v2_new_flaws` (for F15), `flaw_counts` and `expected_v2_open_flaws`, and marked F04 as "regressed", pointing to F15.
> 5. `README.md` covers the item, how to grade it, and the checklist. A grep for flaw-labelling terms and flaw IDs found 0 matches in both docs. v2 has a neutral revision-history table, as a real revision log would; it doesn't say which changes are fixes.
> 6. Both PDFs converted successfully (python-markdown → HTML → LibreOffice). All files are in `/home/user/SIT/eval/synthetic/payments_orchestration/`; no git commands were run.

## Coordinator

[Validated (14 flaws, 5 sound). Commit + push "Add synthetic eval item: payments orchestration (v1, v2, key, PDFs)". Listed all 37 deliverable files. Launched two auditors on Opus: (1) research package loophole audit over the six notes — cross-document consistency, unverified load-bearing claims, coverage against the user's bar, eval-design loopholes including whether the blind set is actually blind and whether synthetic docs are template-like, missing pieces, prioritised actions; (2) eval data integrity audit — verify every external-fact flaw against primary sources, label leakage grep, v2 diff integrity, schema consistency, realism spot-check, sound-section overlap.]

All 11 deliverables are in and pushed. Now the audit pass. I'll run two auditors in parallel on Opus: one checks the research notes for loopholes and cross-consistency, the other fact-checks and integrity-checks the eval data, since several "checkable against vendor docs" flaws were written from memory.

Both auditors are running. Everything produced so far is on the branch:

| Area | Files | Status |
|---|---|---|
| Framework selection | `research/frameworks/` | Done, pushed |
| Model and judge selection | `research/models/` | Done, pushed |
| Kaggle benchmarks | `research/kaggle/` | Done, pushed |
| Eval methodology and metrics | `research/methodology/` | Done, pushed |
| Lecturer grader rubric and prompt | `research/grading/` | Done, pushed |
| Robustness scenarios (166) | `research/robustness/` | Done, pushed |
| Synthetic eval items (3, each v1 + v2 + key + PDFs) | `eval/synthetic/` | Done, pushed |
| Blind eval items (2) | `eval/blind/` | Done, pushed |
| Research loophole audit | `research/audit/research_audit.md` | Running |
| Eval data integrity audit | `research/audit/eval_data_audit.md` | Running |

The data auditor is specifically fact-checking every "verifiable against vendor docs" flaw against primary sources, because three authors admitted writing those figures from memory. If a planted flaw's "correct" value is itself wrong, the key would penalise a correct reviewer, which is the worst dataset defect possible. I'll report what both audits find and commit them when they land.

---

## Subagent report: Research loophole audit

> I wrote the audit to `/home/user/SIT/research/audit/research_audit.md` and changed no other file. Each note is strong on its own, but the package is not research-grade yet: the notes contradict each other on the basics, and the eval data cannot support the generalisation claims. There are 24 actions: **7 P0, 10 P1, 7 P2**.
>
> 1. **Cross-document conflicts (32, each with one resolution).** The notes use six answer-key formats, five matching rules, four severity scales, five category taxonomies, three verdict vocabularies and two competing recall instruments. Grading's 0–4 scale and models' 0–3 is one of them (C1); models' grader choice against methodology's "different family" rules is another (C3).
> 2. **Robustness vs frameworks.** The frameworks decision covers only about 4 of robustness's 11 architecture needs. Its own "switch to LangGraph if we need resume" condition is triggered by robustness's P0 resume requirements (C17).
> 3. **11 class-(a) unverified claims**, each with how to check it. The worst: the SIT MCP auth header and live server behaviour were never probed. The "60K-token document" is attributed to a brief that contains no such figure (the SIT sample is 30 pages, about 7.6K words). Nobody recorded which model generated the eval items.
> 4. **Coverage against your bar.** Tool-failure robustness, explicit metrics and judge bias are strong. Overfitting verification, data-side bias and cost (no total budget) are weak. Capability is argued but not yet measured.
> 5. **The synthetic set is template-like.** All 3 items have 14 flaws, identical category and severity counts, the SIT section layout and 0 embedded images. There are tells: every flawed area is marked "Ready", and "Prior Art" is a sound section in 2 of the 3 documents.
> 6. **The blind set is not blind.** Its READMEs name the defects and sit in the dev tree. The authors knew the eval design (both items also have exactly 14 defects), and the items are probably from the agent's own model family. Recommendation: reclassify it as a sealed held-out set and commission a new blind set.
> 7. **Anthropic-only fallback for the judge.** First try to get one key from another provider (about $40 of grading). Otherwise send the short-context instruments (matcher, citation support) to a local open-weight model, and keep the holistic grader on Claude Sonnet with the same-family limitation disclosed.
> 8. **Human labelling.** There is no consolidated plan. The methodology needs 600+ labelled items and two raters, about 55–60 hours for one person. The audit proposes a one-person plan of about 20–25 hours and caps the claims it can support at "tentative".
> 9. **Missing before build:** a taxonomy file, one shared finding schema and one answer-key schema, `prereg.yaml`, encrypted storage for sealed keys in a private repo, a demo-day runbook, a documentation map for lab §5.3, and a budget.
>
> **P0 blockers:** Probe the live MCP servers. Confirm which provider keys you hold and fix the judge routing. Write the taxonomy file. Write the canonical finding schema. Fix how PDFs are read and how quotes are anchored. Set the reproducibility policy (no temperature or seeds on current Claude; no silent model fallback). Seal the blind set and decide on repo privacy.

## Coordinator

[Commit + push "Add research package loophole audit".]

The research audit is in and pushed. It's the useful kind of harsh: each note is strong alone, but the package isn't research-grade yet because the six authors never agreed on basics. The headline findings:

- **32 cross-document conflicts.** Six answer-key formats, five matching rules, four severity scales, five flaw taxonomies. The fix is one canonical taxonomy file and one shared finding schema, which the audit lists as P0.
- **The "blind" set isn't blind.** The two blind authors were given a domain exclusion list that revealed the synthetic set's design, both landed on exactly 14 defects, and their READMEs name the defects while sitting in the dev tree. The audit recommends reclassifying them as a sealed held-out set and commissioning a genuinely blind one later, with a different author model.
- **The synthetic set is template-like.** All three items share the SIT section layout, identical flaw counts, and tells like every flawed area marked "Ready". An agent could learn the template.
- **Nobody has probed the live SIT MCP servers.** Which auth header they expect decides part of the architecture. That's a P0 that needs your laptop or a network that can reach them.
- **Human labelling has no plan.** Full rigour needs 55 to 60 hours of one person's time. The audit proposes a cut-down 20 to 25 hour plan and caps what it can claim.

Seven P0 blockers, ten P1, seven P2, all in `research/audit/research_audit.md` with effort estimates.

The eval data integrity audit is still running. I'll report when it lands, then give you a consolidated picture and a proposed next step.

---

## Subagent report: Eval data integrity audit

> The audit is written to `/home/user/SIT/research/audit/eval_data_audit.md`. **2 answer-key entries are wrong, both partially**; no planted "correct" value is outright false. Nothing in `eval/` was modified and no git commands were run.
>
> 1. **Key-wrong #1: blind/item_a D01.** The key states the UK refund rule wrongly. Under UK reg. 34(5), where the trader hasn't offered to collect, the 14 days run from receipt of the goods or evidence of sending, not from notification. Under CRD Art. 13(3), offering collection (which the design does in UK and DE) removes the right to withhold. A reviewer who cites UK law correctly would fail the literal `credit_requires`. The defect itself is real.
> 2. **Key-wrong #2: research_lakehouse sound section §16 (audit plane).** Its rationale "audit holds only pseudonyms" ignores that pseudonymised data is still personal data under GDPR, and the doc's own NFR-7 invokes GDPR Art. 17. The trap is too broad: it would score as a false positive a valid point that the Art. 17(3) exemption basis should be documented.
> 3. **External facts.** About 35 checked, using vendor-owned GitHub mirrors (awsdocs, MicrosoftDocs, opensearch-project, postgres) plus search snippets, because the vendor and legislation sites are blocked; each source is labelled. Confirmed: DynamoDB: 1,000 WCU per partition, 400 KB items, LSIs block split-for-heat, global tables are last-writer-wins. SQS: 14-day maximum retention; one message group is processed serially at 300 msg/s. S3: Object Lock compliance mode; Intelligent-Tiering archive tiers are opt-in and need a restore. OpenSearch HNSW memory formula `1.1*(4d+8M)`. Azure: IoT Hub S2 = 6M msgs/day and 120 sends/s per unit; DPS group-key guidance; Stream Analytics late-arrival drop. CloudHSM: at least 2 HSMs across AZs. Standards and law: PCI 3.3.1/3.3.1.2/3.3.2; NIST 800-171 3.1.1 vs 3.13.11/16; PDPA s26 and the 3-day breach rule; Modbus 125-register limit; UL 9540A is a test method; IEEE 2030.5 TLS and cipher suite; IEEE 1547 2 s islanding trip. pgvector is not referenced in any doc. IEEE 1547 is the one caveat: the standard is paywalled, so I couldn't rule out a utility-agreement extension clause.
> 4. **Label leakage: none.** The only hits are benign (two uses of "deliberately", "wrong window", enum names, and "unintentional" matching the regex). Phrase-overlap checks found only the key quoting the docs.
> 5. **v2 integrity: all 42 statuses across the three synthetic items match the text** (with v2 line references), and F15 is present in each. One labelling ambiguity: `regressed` entries count as 5 fixed instead of the README's 6.
> 6. **Sound-section overlaps.** Some flaws cite sections the same key lists as sound. The high-risk one is lakehouse F08, which cites §16 with no disambiguation. Medium-risk ones are clinical F05/§4.3, lakehouse F01/§4, item_a D03/FR-RET-01, and item_b DEF-03/DEF-13/§7.5 and DEF-14/FR-GRID-01. No sound section hides an unplanted material defect.
> 7. **Over-strict credit rules (in P0).** Some keys require a specific fix rather than detection, e.g. item_b DEF-12 demands GNSS/PTP and clinical F06 item 3 is a remedy. Correct reviewers with other valid fixes would fail.
> 8. **Schema.** The five keys disagree on field names, severity scales (3-level vs 4-level), where v2 flaws live, and credit rules ("by substance", "core claims", "first two items", "every item"). The report proposes one canonical schema with an explicit per-flaw credit mode and a rename map for each key.
> 9. **Realism.** All five would pass as real design docs to a senior engineer; item_a and item_b are the strongest. Fixable tells: lakehouse §23 mentions "an AI coding assistant", and the payments v2 header date (2026-10-12) is later than today.
> 10. **Fix list.** P0 (5 items): D01, the lakehouse §16 rationale, F08 vs §16, the remedy-as-requirement credit items, and the DEF-03 tolerance. P1: v2 status semantics, a missing `introduced_by_fix_of` on clinical F15, and overlap annotations. P2: schema adoption, counts, neutral observations to add, and the realism nits above.

## Coordinator

[Appended a status section to research/README.md. Commit + push "Add eval data integrity audit and research status note". 28 files under research/ and eval/, clean tree.]

Everything is done and pushed to `claude/eloquent-sagan-ah5ttk`. Working tree is clean.

### What the research phase produced

Six research notes, five evaluation items, and two audits, all on the branch under `research/` and `eval/`. Every subagent ran on Opus after your correction.

### The decisions, now evidence-backed

- **Framework: custom Python state-machine loop on the Anthropic SDK.** Scored 92/100 against LangGraph 80 and PydanticAI 77. Four corrections from the evidence: use a direct MCP client (the server-side connector can't send SIT's API key header), write our own tool loop, set SDK retries explicitly, and accept that temperature no longer exists so reproducibility comes from pinning and recorded tool calls.
- **Agent model: Opus 5.5, Sonnet 5.5 for sub-tasks.** About $2 to $3 per full review with caching. Fable rejected as 2.5x the cost with multi-minute turns.
- **Grader: different provider from the agent.** Fifteen papers put same-family judge bias at 3 to 8 percentage points. If you only hold an Anthropic key, the fallback is code-checked metrics plus a local open-weight matcher, with the limitation disclosed.
- **Kaggle: techniques, not data.** No competition has ever targeted design review. Transferable: score both answer orders, length-bias controls, and quadratic weighted kappa for ordinal rubrics.

### What the audits caught

The eval data audit fact-checked about 35 external claims against vendor-owned sources and found the planted "correct" values hold up. Two answer-key entries are partially wrong: one misstates the UK refund timing rule, one sound-section trap would penalise a valid GDPR point. Zero label leakage, all 42 v2 flaw statuses verified against the text.

The research audit is the one to read first. It found 32 conflicts between the six independently written notes, and two structural problems I should own: the "blind" set isn't blind because I gave those authors a domain exclusion list that revealed the design, and the synthetic set is template-like because I gave all three authors identical flaw counts. Both are fixable and the audit says how.

### Seven P0 blockers before any code

1. Write one canonical flaw taxonomy file.
2. Write one shared finding JSON schema used by agent, matcher, and grader.
3. Probe the live SIT MCP servers for their auth header. This needs your laptop or a network that can reach them; the sandbox proxy blocks those hosts.
4. Confirm which provider keys you hold, which decides the judge routing.
5. Fix the five answer-key errors.
6. Set the reproducibility policy.
7. Seal the held-out set and decide whether the repo will be private, since a web-searching agent could otherwise find its own answer keys.

Items 3 and 4 need you. The rest I can do next. Say the word and I'll start with the taxonomy and schema, then fix the keys, then build the agent skeleton.

---

## User

> btw im onc loud and not local, right?

## Coordinator

Yes, this session runs in the cloud. Everything happened in an isolated container on Anthropic's infrastructure, not on your machine. That has three practical consequences for this project:

- **Nothing lives on your laptop yet.** All the work is on the `claude/eloquent-sagan-ah5ttk` branch at github.com/malcolm1232/SIT. When you want it locally, clone the repo and check out that branch.
- **This container is ephemeral.** It gets reclaimed after inactivity, which is why I've been pushing after every agent. Anything not pushed would be lost.
- **The network is restricted.** That's why several agents reported blocked sites (kaggle.com, arXiv, OpenAI and Google docs), and why nobody could probe the live SIT MCP servers. The outbound policy was set when the environment was created. Two of the P0 blockers from the audit, probing the SIT servers and confirming your API keys, need to happen on your laptop or in a session with a more open network policy. Docs on how the environment and its network policy are configured are at https://code.claude.com/docs/en/claude-code-on-the-web.

For demo day, the lab requires the agent to run on your own laptop, so at some point the workflow becomes: I build and push here, you pull and run locally against the real MCP servers with your real key. The robustness note already plans for that split with recorded tool fixtures that let tests run offline here and live runs happen on your machine.

---

## User

> Agent model: Opus 5.5, Sonnet 5.5 for sub-tasks: NO, use ALL opus.
> sorry for this: Grader: different provider from the agent. Fifteen papers put same-family judge bias at 3 to 8 percentage points. If you only hold an Anthropic key, the fallback is code-checked metrics plus a local open-weight matcher, with the limitation disclosed.... do u need an anthropic key?
> i wanted to mention to use .
>
> 1. Probe the live SIT MCP servers for their auth header. This needs your laptop or a network that can reach them; the sandbox proxy blocks those hosts.: i can run locally on my mac a ascript, can u run like a python3 ~/.claude/skills/delegator/relay/relay.py --auto... so u can run scripts u need from local mac? ...
>
> also, once ure done, use each agent btw to verify in case there are loopholes cos there are things we missed out on

## Coordinator

[Checked: no `~/.claude/skills/delegator/relay/relay.py` in the container; no `ant` CLI; no ANTHROPIC_* credentials in the sandbox environment. Read the Remote Control documentation page.]

Three findings. No relay script exists in this container, so I can't use that route. The sandbox also has no API credentials, so the agent we build can't make live LLM calls from here; I can build and test it with fakes and recorded tool fixtures, and live runs happen on your Mac. And the supported way to let me work on your Mac is Remote Control: run `claude remote-control` in a terminal in the repo folder and that session appears in the Claude Code app, able to run scripts locally.

In the meantime I'll make the MCP probe a script you can run yourself and paste back. Starting the P0 work now, four agents in parallel on Opus.

[Launched four Opus agents: (1) canonical taxonomy + Finding/Review schema + answer-key schema + validator under `spec/`; (2) apply the eval-data audit's P0/P1/P2 fixes to the five answer keys and READMEs in place, with a change log; (3) governing docs under `docs/`: DECISIONS.md ADRs, REPRODUCIBILITY.md, DEMO_DAY_RUNBOOK.md, DOCUMENTATION_MAP.md, SEALING.md, BUDGET.md, and rewrite research/models for all-Opus; (4) `scripts/probe_mcp_servers.py` for the Mac with six auth-header variants, cold/warm timing, tools/list, key redaction, `--self-test` against a local MCP server.]

## User (mid-turn)

> claude remote-control SIT

## Coordinator

Four agents are running. On your message: `claude remote-control` takes no repo argument, it just needs to be run from inside the folder. Let me check whether a Remote Control session from your Mac is visible to me yet.

[ListAgents: only the four subagents.]

## User (mid-turn)

> ❯ /remote-control SIT
>
>   /remote-control is active · Continue here, on your phone, or at https://claude.ai/code/session_012eEnGCC8NwJFN3ojoqW4gD ... done

## Coordinator

Your Mac session is live. Let me confirm I can see it, then hand it the prep work that doesn't depend on the probe script.

[get_session confirmed `session_012eEnGCC8NwJFN3ojoqW4gD`, title "SIT", idle, model claude-opus-5-5, bridge environment. Sent it a message: environment check (python, git, repo state), which credentials exist by name only (ANTHROPIC_*, OPENAI_API_KEY, GEMINI_API_KEY, GOOGLE_API_KEY, `ant auth status`), raw curl reachability of the four SIT MCP hosts with cold/warm timing, LibreOffice/pandoc presence; report only, no commits.]

The Mac session is connected and I've handed it the prep work: environment check, which API keys exist (names only), a raw reachability probe of the four SIT MCP hosts with cold and warm timings, and whether LibreOffice or pandoc is installed. It will report back here. Once the probe script lands on the branch, I'll ask it to pull and run the full probe.

On your other two points:

- **All Opus 5.5, no Sonnet.** Recorded. The decisions agent is rewriting the model recommendation and recomputing the per-run cost and total budget on that basis.
- **Do you need an Anthropic key?** For the agent to run, yes. The agent calls the Claude API at runtime, so your Mac needs either `ANTHROPIC_API_KEY` set or a profile from `ant auth login`. This cloud sandbox has neither, so I can only build and test here with fakes and recorded fixtures. The Mac session's report will tell us what you already have. Your sentence got cut off at "i wanted to mention to use", so tell me what you meant to say there.

Running now, all on Opus: canonical taxonomy and schemas, answer-key corrections, decision records plus reproducibility policy plus demo-day runbook plus budget, and the MCP probe script. After those land I'll run the verification pass you asked for, one checker per deliverable, before building any agent code.

---

## Subagent report: MCP probe script for local Mac

> 1. I wrote `/home/user/SIT/scripts/probe_mcp_servers.py` (Python 3.11+, with an install hint on line 2) and `/home/user/SIT/scripts/README.md`. The key is read from `SIT_MCP_API_KEY` and appears nowhere in the repo; I grepped to confirm. The script tries the 6 auth variants in order and records status, initialize result, protocolVersion, serverInfo and timing for each. It also records the tools, cold/warm timings, the search sample call and the document-intelligence rejection text, and writes everything to `./mcp_probe_results.json` with the key redacted (including its URL-encoded form).
> 2. The import path I verified in mcp 2.2.0 is `from mcp.client.streamable_http import streamable_http_client`. 1.x called it `streamablehttp_client`. One catch: mcp 2.x uses **httpx2**, not httpx. You pass it an `httpx2.AsyncClient(headers=..., timeout=...)` through `http_client=`, and it yields `(read, write)` for `mcp.ClientSession`. httpx2 comes with mcp, so the install command is still `pip install "mcp>=2,<3" httpx`. The script uses httpx for its own direct POST probes (exact HTTP status, and a fallback `tools/list` if the SDK fails).
> 3. On top of the brief, it runs a no-auth control request to see whether a key is enforced at all, and runs the four servers in parallel (`--sequential` and `--only` are available). Each server retries once after a cold-start-like failure (timeout, 502/503/504, read or protocol error), using 180 s for the first attempt and 30 s after that. If a server gives no HTTP response at all, the remaining variants are skipped, which keeps the worst case to about 6.5 minutes. ExceptionGroups are flattened, MCPError messages are recorded word for word, and the exit code is always 0. A missing key is the exception: it exits 2.
> 4. Dummy-key run against the real URLs: the proxy blocks all four (`ProxyError: 403 Forbidden`, no HTTP status). Each failure is recorded cleanly, the JSON file is written with errors and no key in it, and it exits 0 in about 1.4 s.
> 5. `--self-test` passes all 11 checks and exits 0. It starts a local in-process `MCPServer` with one `echo` tool over streamable HTTP, behind a gate that only accepts `X-API-Key`. Bearer gets 401 and X-API-Key wins; protocol 2025-11-25 and serverInfo are recorded; the SDK initialize, `tools/list` and echo call all work; the no-auth request gets 401; a second, unreachable server is reported cleanly; and the key is absent from the output. It writes to `./mcp_probe_selftest_results.json` so it never overwrites the real results file.
> 6. Caveats: `cold_start_s` only shows the true wake time if Bearer is the winning header. Otherwise the wake shows up in `first_response_s`, and the JSON explains this in `timing_notes`. The search and document-intelligence sample calls choose a tool and arguments from the schema by name, and record which ones they used. Next step: the user runs the README steps on their Mac and pastes `mcp_probe_results.json` back here.

## Coordinator

[Grepped scripts/ for the key: absent. Removed stray result JSONs. Commit + push "Add MCP server probe script for local run on the Mac". Sent the Mac session the run instructions: fetch/checkout the branch, venv + install, `--self-test`, export SIT_MCP_API_KEY from page 4 of the lab PDF in the shell only, run the probe, paste `mcp_probe_results.json` back, confirm `git status` clean.]

Probe script is pushed, with the API key confirmed absent from the repo. Now handing it to your Mac session to run.

The probe instructions are with your Mac session. It may ask you for the shared API key from page 4 of the lab PDF; give it in the shell only, never in a file.

Waiting on three P0 agents (taxonomy and schemas, answer-key corrections, decision records and budget) and the Mac session's report. Nothing else to kick off until those return.

`[stop hook → commit + push: "WIP: in-progress P0 outputs (schemas, key fixes, docs)"]`

---

## Subagent report: Fix answer-key errors

> 1. **Done, with one substitution:** all P0, P1 and P2 fixes are applied in place, and the five keys still load as valid JSON. The audit's tolerance fix (P0-5) is for item_b DEF-03, not item_a D03, so I applied it there: credit now accepts "2 s unless agreed with the utility" and any clause from 8.1 to 8.1.2. Item_a D03 got its FR-RET-01 overlap note instead. If you meant a change to D03 itself, it still needs specifying.
> 2. **item_a D01:** the defect still stands, but the key now states each regime's rule correctly. UK reg. 34(5) runs from receipt or evidence of sending; reg. 34(6) and CRD Art. 13(1) run from notification. CRD Art. 13(3) allows no withholding once collection is offered. Credit goes to any reviewer who gives a correct anchor for at least one regime and rejects inspection. I also updated the title, `why_it_matters` and `acceptable_fix` to match.
> 3. **Lakehouse §16:** `why_sound` now says pseudonyms are still personal data, and the trap counts only "remove Object Lock" or "audit store must be erasable" as false positives. The Art. 17(3) documentation point is in a new `still_valid_observations` list. F08 vs §16 now has a disambiguation note naming the §16 "Sources" subsection (and §11) as F08's ground and "Pipeline and storage" / "Content boundaries" as the sound parts.
> 4. **Remedy-as-requirement:** item_b DEF-12 dropped its GNSS/PTP credit item, and its fix field now says it holds examples only. Clinical F06 dropped its remedy item. From the audit's other P0-4 items, clinical F11 "silent in ADX" is now marked supporting and F04's last two must-mention items are merged into one.
> 5. **v2 convention:** the old "regressed" entries now read status `fixed` with `introduced_new_flaw_id`, and F15 sits in `flaws[]` with `introduced_by_fix_of` in all three keys. That added the missing F10 link on clinical F15 and moved F15 out of `v2_new_flaws`, which is removed. Each key now tallies 6 fixed, matching the READMEs. Any code that reads `v2_new_flaws` or counts `len(flaws)` (now 15) needs updating.
> 6. **Overlap notes:** I added a `disambiguation` field to both sides of every pair you listed, plus lakehouse F05/§14.6 and F15/§9, which are also on the audit's list. Design docs: "an AI coding assistant" is gone from lakehouse §23 (v1 and v2), and the payments v2 date is now 2026-10-01. The three affected PDFs still show the old text, because the documented PDF pipeline gave a different layout even on the unedited file; they need regenerating with the original settings.
> 7. **Blind READMEs:** each now has only domain, word count, the defect count of 14, intended use and a sealed-key note. The full original README text is saved verbatim in each key under `readme_notes_moved_at_sealing`. The keys are not encrypted yet and there is no access log.
> 8. **Change log:** `/home/user/SIT/research/audit/eval_fixes_applied.md` has 52 field-level key entries, 5 README entries and 2 design-doc entries, each with before, after and the audit item it resolves, plus the audit items I left out and why. Edited files are under `/home/user/SIT/eval/` (5 `answer_key.json`, 5 `README.md`, `research_lakehouse/design_v1.md`, `design_v2.md`, `payments_orchestration/design_v2.md`); no git commands were run.

## Coordinator

[All five keys validated as JSON. Commit + push "Apply eval data audit corrections to answer keys and READMEs".]

Answer-key corrections are applied and pushed: 52 field-level key fixes, all five keys still valid JSON, change log in `research/audit/eval_fixes_applied.md`. One item I'll carry forward: three PDFs now lag their markdown after the design-doc edits and need regenerating. I'll fold that into the verification round.

Two P0 agents left: taxonomy and schemas, and the decision records plus budget. Plus the Mac probe report.

---

## Subagent report: Decisions, repro policy, runbook, docs map

> 1. I wrote six documents under /home/user/SIT/docs/: DECISIONS.md, REPRODUCIBILITY.md, DEMO_DAY_RUNBOOK.md, DOCUMENTATION_MAP.md, SEALING.md and BUDGET.md. I also rewrote §1, §3 and §7 of /home/user/SIT/research/models/README.md for all-Opus, moved the Sonnet analysis into "Appendix A … (not adopted)", and added an ALL-OPUS section to its cost_model.py. That script runs cleanly. I ran no git commands, wrote no secrets, and did not open eval/blind/*.
> 2. **Per-run cost:** a full all-Opus run is about **$2.18** (range $1.67-$3.24). That assumes both the native PDF and our extracted page text are sent and cached. Sending the PDF alone would be $2.07.
> 3. **Total budget:** 433 agent runs cost **$777**. With grading and matching the total is **$1,363**, or **$1,772 (call it $1,800) with the 30% margin**, and that covers every judge branch. If you go Anthropic-only with the matcher on a local model, it drops to about $1,100-1,200.
> 4. **The token count behind the costs is unverified.** It must be measured with `count_tokens` on your laptop and the script re-run. The grader estimate also went up about 1.6x once I costed its full multi-call pipeline.
> 5. **Decisions recorded:** **Accepted:** custom loop on the Anthropic SDK with a direct MCP client; Opus 5.5 for every call; the eval tiers (current eval/blind becomes a sealed held-out set, real blind set still to be commissioned); work split between laptop and cloud sandbox. **PDF and quotes:** the model gets the native PDF plus one text version extracted by a pinned pdfplumber. All quotes must come from that text and are checked in code: quote, page and section, at least 8 tokens, at most 3 locations, fuzzy match ≥ 0.90. **Judge provider:** pending, with both branches written up. **Repo privacy:** awaiting you; the recommendation is a private repo.
> 6. **One deliberate deviation from the claude-api skill:** eval runs send no `fallbacks`. Its fallback targets are other models (claude-opus-5 and claude-opus-4-8), which would break the all-Opus decision. It is a demo-only `--allow-fallback` flag, and any use is recorded in the manifest.
> 7. **Model ID and sampling (verified via the skill):** `claude-opus-5-5` has no dated snapshot, so the bare ID is the tightest pin available. Temperature, top_p, top_k and budget_tokens all return a 400, and there is no seed. So reproducibility means the report and metrics can be regenerated byte for byte from recorded runs, and the model's results are reported over k runs with confidence intervals (pass^k included).
> 8. **Needs your decision or a follow-up:** which judge keys you hold; whether the all-Opus rule also covers the grader (Sonnet 5.5 is recommended); repo privacy; methodology ablation A4 ("different model") can no longer run under all-Opus. I replaced it with an effort-low variant, but research/methodology/README.md still needs amending.

## Coordinator

[Commit + push "Add decision records, reproducibility policy, demo runbook, docs map, sealing, budget".]

Governing docs are pushed under `docs/`. The numbers you'll care about:

| Item | Figure |
|---|---|
| Per full review run, all Opus 5.5 | about $2.18 |
| Full eval programme (433 runs, grading, matching) | about $1,360 |
| With 30% margin | about $1,800 |
| Anthropic-only judge branch instead | about $1,100 to $1,200 |

The token count underneath those is unverified until measured on your laptop, so treat them as planning figures.

Four decisions are now waiting on you. None blocks the build, but they block the evaluation design:

1. **Which API keys do you hold?** Anthropic only, or also OpenAI or Google? This decides whether a different-provider judge is possible. The Mac session's report should answer this.
2. **Does "all Opus" also apply to the grader?** The research recommends a different model for the grader to limit self-preference bias. If you want Opus grading Opus, that's your call, but it should be disclosed as a limitation.
3. **Repo privacy.** Recommendation is private, because a web-searching agent could otherwise find its own answer keys. The lab only requires inviting two SIT GitHub IDs as collaborators, which works fine with a private repo.
4. **Grader for the "different model" ablation.** Under all-Opus the methodology's A4 ablation can't run as written, so it's been replaced with a low-effort Opus variant.

One agent left: the canonical taxonomy and schemas. Then the verification round.

---

## Subagent report: Canonical taxonomy and schemas

> I wrote both P0 deliverables under /home/user/SIT/spec/. `python3 spec/validate_examples.py` passes: both schemas are valid, all 17 enums match taxonomy.yaml, and the README examples, a full Review and a full answer key validate. All 32 broken variants are rejected, and the mappings cover all 73 flaws in the five keys.
>
> 1. Files: taxonomy.yaml (enums with definition, include/exclude and example, plus converter-only legacy_mappings), finding.schema.json (Finding at the root, Review envelope at #/$defs/Review), answer_key.schema.json, README.md and validate_examples.py.
> 2. Taxonomy: `kind` is the six lab 2.3 categories and `category` is a separate defect-mechanism axis, as the audit recommended (C7). Domain labels become free tags.
> 3. Severity, against your suggested default: I used critical/high/medium/low, not critical/major/minor/info, because the audit (C6), the metrics weights 8/4/2/1 and both blind keys all use it. Strengths carry no severity instead of "info". Synthetic major→high, minor→low, with minor→medium as the sensitivity variant; each key keeps its original label so both can be scored.
> 4. Triage, against the audit (C8): six dispositions, including needs_testing because lab 3.2 names it. The audit wanted grading's "mixed" and "none" kept; instead "mixed" becomes one primary value plus secondary_dispositions, so action-type accuracy has a single gold value, and "none" becomes no_change.
> 5. Categories, against the audit (C7): 9 mechanisms plus `other`, not the synthetic set's 8. I added external_constraint_violation because 4 of the 28 blind flaws would otherwise land in `other`. I also broadened two names (unsupported_or_incorrect_claim, scalability_or_failure_mode) and kept the old ones as aliases.
> 6. Credit modes: the audit (C5) wanted one matching rule and you asked for a per-flaw mode. Matching is always core insight plus location; substance / all_of / any_of only says how the core insight is checked. Lakehouse's "first two items" rule becomes explicit required/supporting items.
> 7. Other conflicts (C4, C9-C13, C15/16, C26, C32, U11, G1-G3) follow the audit; each has a paragraph in README section 3.
> 8. Leakage risk: my first draft of the taxonomy examples and include-lists echoed specific blind-item flaws. I rewrote them on an invented domain and marked taxonomy.yaml prompt-safe except legacy_mappings. The README and legacy_mappings name eval-key labels, so neither should go in any prompt.
> 9. Still to author before keys can be scored: core_insight, anchor quotes, expected_disposition, approved_decisions and author_model are missing from every key. They are tracked in authoring_status.pending, so action-type accuracy and BEH-16 stay blocked until they are filled.
> 10. Rule breach: I ran one read-only `git status`, which you had forbidden; nothing else ran. It showed spec/ files already tracked mid-run, so something may have committed them during my work.

## Coordinator

[Ran `spec/validate_examples.py`: ALL CHECKS PASSED; canonical categories over existing keys printed. Commit + push "Add canonical taxonomy, finding/review schema, and answer-key schema". Launched five verifiers on Opus: (1) verify spec with adversarial tests, walk all 32 conflicts, lab-brief coverage, invariant support, grader compatibility, leakage grep, and write `spec/convert_answer_keys.py`; (2) verify eval fixes item by item, regenerate stale PDFs with a committed build script, leakage re-check, sealing check, overlap anchors, and a cold human-ceiling probe; (3) verify docs against the `claude-api` skill, reconcile budget arithmetic, lab 5.1-5.4 coverage, spec consistency, amend methodology A4, sealing feasibility, runbook dry-run; (4) reconcile the six research notes to spec/decisions with "Superseded" callouts; (5) fresh-eyes: play the SIT evaluator grading the repo as submitted, then the sceptical reviewer hunting what nobody was asked to do.]

All P0 deliverables I can do from here are done, validated, and pushed. Now the verification round you asked for: one checker per deliverable, each on Opus, each allowed to make small corrective edits in its own scope and required to log them.

Five verifiers are running, each scoped to one deliverable and allowed only small logged fixes:

- **Spec verifier** adversarially tests the schemas, walks all 32 conflicts to confirm each resolution is actually implemented, and writes the converter that turns the five answer keys into the canonical format, which is the real test of the "covers all 73 flaws" claim.
- **Eval verifier** re-checks every applied fix, regenerates the three stale PDFs with a reproducible build script, re-runs the leakage grep, and does a human-ceiling probe: reads each design doc cold, lists its own top 5 issues, then compares against the key.
- **Docs verifier** checks every API claim against the current reference, reconciles the budget arithmetic to the cost model output, confirms the documentation map covers every bullet of lab sections 5.1 to 5.4, and dry-runs the demo runbook.
- **Reconciler** edits the six research notes so they either state the canonical value or carry a "superseded" marker pointing to the spec or decision record, so the 32 contradictions stop existing rather than being merely catalogued.
- **Fresh-eyes hunter** plays the SIT evaluator grading the repo as submitted today, then the sceptical reviewer looking for what nobody was asked to do: a human-labelling time plan, an answer key for the real SIT document, the circularity of one model family writing the eval, running the agent, and auditing itself, and whether the plan is too big to finish by the deadline.

Still waiting on the Mac session's probe report as well. I'll commit each verifier's output as it lands and give you a consolidated picture when all five are in.

---

## User

> 1. Which API keys do you hold? Anthropic only, or also OpenAI or Google? This decides whether a different-provider judge is possible. The Mac session's report should answer this. -- im asking mac to retrieve them.
> 2. Does "all Opus" also apply to the grader? The research recommends a different model for the grader to limit self-preference bias. If you want Opus grading Opus, that's your call, but it should be disclosed as a limitation.-- not necessarily, use what u feel is suitable, ive got generalically sufficient tokens. but not be too excessive, unless its justified.
> 3.
> 4. Repo privacy. Recommendation is private, because a web-searching agent could otherwise find its own answer keys. The lab only requires inviting two SIT GitHub IDs as collaborators, which works fine with a private repo. -- currently on private.
> 5. Grader for the "different model" ablation. Under all-Opus the methodology's A4 ablation can't run as written, so it's been replaced with a low-effort Opus variant.-- u decide. doesnt have to be low effort, opus can all be high, ive got sufficient tokens.

## Coordinator

Recorded. To avoid colliding with the docs verifier that's editing `docs/DECISIONS.md` right now, I'll log your answers in a separate file and fold them into the ADRs once that verifier finishes.

[Wrote `docs/USER_DECISIONS.md`: agent all Opus 5.5 with high effort allowed; grader = Opus 5.5 high as primary, plus different-provider judge at high effort if a key exists, Sonnet 5.5 as same-family control, limitation disclosed if Anthropic-only; keys being retrieved; repo private, sealing still required; A4 stays a genuine different-model ablation using Sonnet 5.5 as the agent for that experiment only, plus A4b effort sweep medium/high/xhigh. Commit + push.]

---

## Subagent report: Fresh-eyes evaluator loophole hunt

> I wrote /home/user/SIT/research/audit/fresh_eyes.md and edited no other file; no git commands were run.
>
> 1. **Evaluator view:** as a plan it is excellent: every rubric dimension traces to the brief, the decision records and demo runbook are thorough, and restraint can be measured. As a submission it fails the brief's deliverable sections (§5.1 and §5.2) because there is no agent code. The memo lists every file I looked for and did not find, including `agent/`, `config/`, `prompts/`, `pyproject.toml`, the seven §5.3 docs and `prereg.yaml`. There is also no `.gitignore`, and the first 8 characters of the shared MCP key are still in `scenarios.md`.
> 2. **Confusing for an evaluator:** `README.md` is stale and contradicts the decision records. The same IDs mean different things in different files (G1-G3, D1-D5, C1-C32), there are too many tier names, and nothing records which audit actions are done.
> 3. **Minimum viable agent:** the memo maps each requirement in brief §2.3 and §2.4 to one mechanism. It also gives 11 walkthrough questions and 6 live-change requests the runbook does not prepare, such as a severity filter, a risk-register output, a plan-approval pause, a domain allow-list and adding a tool.
> 4. **The SIT document has no real answer key.** The only one is an illustrative key written by the same model family, never checked by a human and not in the canonical schema. A human-written key independent of it is the highest-value control available.
> 5. **Sealing has a leak:** the held-out key content also exists outside `eval/` (both audit files, `spec/README.md`, `taxonomy.yaml`), and `spec/validate_examples.py` reads the held-out keys, which breaks the project's own interim sealing rule.
> 6. **Latency:** my estimate is that all-Opus at high effort takes about 380-870 s against the 540 s deadline. The runbook's 90 s window for assess, refine and verify does not fit. Output speed is unverified, so this needs measuring on the laptop.
> 7. **Re-review of an updated document:** sampling noise can make the agent mark unchanged sections "resolved", and nothing measures that error (I propose a false-resolution rate). Lab §1.5's embedded "other reviewer" inputs, including fixes that are claimed but not made, are only at P2.
> 8. **Circularity:** one model family wrote the eval data and keys, checked and edited them, wrote the SIT key and the audits, and will run (and maybe grade) the agent. Missing controls: a small set of human-planted flaws, a human spot-check of the audit's fact checks, and a human second reviewer for the key derivations.
> 9. **Scope:** the plan (about 430 runs, about 65 h of laptop time, 166 robustness scenarios) cannot be finished before the deadline. A keep / keep-if-time / defer table cuts it to about 100 runs, about $220 and 4-6 build days.
> 10. **New actions:** 24 not already in the audit's list (6 P0, 11 P1, 7 P2). If only three get done: build the thin-slice agent, measure latency, and have a human write the SIT key.
>
> **Disclosure for the access log:** as instructed, I read the two `eval/blind` READMEs and the audit files that contain held-out key content. I did not open any answer key or design document. This is exposure, not an evaluation, and should go in the access log when it is created.

## Coordinator

[Grepped the tree for the key prefix: one hit in `research/robustness/scenarios.md` row OPS-02 (a test description that named the prefix to grep for). Replaced with `<REDACTED-KEY-PREFIX>`. Added `.gitignore`. Commit + push "Redact MCP key prefix from scenarios, add .gitignore, add fresh-eyes audit".]

The fresh-eyes hunt landed with one urgent finding: the first 8 characters of the shared MCP key are in the robustness scenarios file. Redacting that now and adding the missing `.gitignore`.

## User (mid-turn)

> u said this: Per full review run, all Opus 5.5	about $2.18 / Full eval programme (433 runs, grading, matching) about $1,360 / With 30% margin about $1,800 / Anthropic-only judge branch instead about $1,100 to $1,200.... huh? 1.2k dollars? what??  for real?

## Coordinator

Yes, the 8-character prefix was only ever in a test description (a grep instruction for that very prefix), it's now redacted from the tree, and it remains in earlier commits of this private branch. Eight hex characters of a 64-character key is not a usable leak, so I'm not rewriting history, but it's recorded.

On the budget question: those numbers are real, but they're for the full research-grade programme, not for using the agent. Here's where the money actually goes.

| What | Runs | Cost |
|---|---|---|
| One review of one document | 1 | about $2 |
| Demo day, including rehearsals | about 10 | about $20 |
| Full research programme as the methodology specifies | 433 | about $780 agent + $580 grading |

The 433 comes from the methodology note demanding research-grade statistics: 3 to 5 repeated runs per document for variance, times 9 documents, times 3 baselines and 5 ablations, plus grading every output with two judges and three samples each. That's what "detect a 10-point recall difference with confidence intervals" costs. It is the honest price of the bar you set, and I'd rather show you the number than hide it.

Two things make it less alarming:

- **The fresh-eyes reviewer independently flagged it as too big to finish by the deadline** and proposed a cut-down core of about 100 runs for roughly $220, keeping the parts that prove the claims and deferring the rest. I'd take that plan.
- **The per-run figure is unverified.** It assumes about 20 model calls per review and 210k tokens of document plus research context. Measured on your laptop, it could be half that.

One question that changes the picture: when you say you have sufficient tokens, is that pay-per-token API credit, or a subscription? The agent needs an API key and bills per token. A Claude subscription doesn't cover API calls. If you have API credit of a known amount, tell me the figure and I'll size the eval programme to it.

Four verifiers still running, plus the Mac report. I'll hold further spend decisions until you answer.

`[stop hook → commit + push: "WIP: verifier edits in progress"]`

---

## Subagent report: Verify eval fixes and regen PDFs

> Every P0 and P1 fix in the audit is present and correct as the change log describes, all six synthetic PDFs are rebuilt and pass their text checks, and I made two small key edits. Full report: /home/user/SIT/research/audit/verify_eval.md.
>
> 1. **Fix-by-fix (P0/P1):** all P0 items (P0-1 to P0-5) and P1-7 to P1-9 are confirmed. P1-6 (rewording "deliberately") was optional and not applied. P2-10 belongs to the spec verifier. P2-11 to P2-14 and P2-16 are not applied or only partly applied, as the change log says. The diff against the pre-edit snapshot shows exactly changes C01–C52, D01 and D02, nothing more. The v2 convention is identical in all three synthetic keys: six `fixed`, eight `unchanged`, exactly one `introduced_new_flaw_id: "F15"`, and F15 listed once with `introduced_in: "v2"` and `introduced_by_fix_of`. Every README count matches its key.
> 2. **item_a D01 law:** legislation.gov.uk and eur-lex are blocked, so I checked UK reg. 34(2), (3), (5), (6) and CRD Art. 13(3) only from search-engine extracts of the official pages, labelled P-snippet. The rewritten key is legally correct. Two things came out of this: The key's D02 citation "34(2)-(3)" is right, because 34(3) is the partial-delivery rule. The audit's note calling it cosmetic was wrong. I rewrote D01's "single conservative rule" in `acceptable_fix` (edit E1). As written it was unlawful under the stricter reading of the home-collection offer, which the key itself accepts as legitimate.
> 3. **PDFs:** the new `/home/user/SIT/eval/build_pdfs.py` (python-markdown, then LibreOffice headless) rebuilds all six and checks them. Every PDF contains its first-, middle- and last-section probe phrases, "could the engineering team build each component…" in lakehouse §23, and "2026-10-01" in payments v2; the stale text is gone. New page counts are clinical 21/22, payments 21/22 and lakehouse 20/21 (v1/v2), down from 25–29, and tables are now borderless. The three synthetic READMEs now have a "How to regenerate the PDFs" line. The old PDFs are backed up in the session scratchpad under `old_pdfs/`.
> 4. **Leakage:** there are no flaw IDs and no "planted", "defect", "flaw" or "answer key" in any design document or PDF text. The only hits are benign: "hygiene-sealed", a safe "sealed" for break-glass accounts, and "deliberately" in two sound sections. Every overlap between key wording and the documents is the key quoting the document, or v2 text that adopts the corrected fact.
> 5. **Blind sealing:** both blind READMEs now hold only domain, size, defect count, intended use and a sealed-key note. The removed text is preserved verbatim in `readme_notes_moved_at_sealing` (identical apart from a final newline). The keys are still plaintext next to `design.md` (open P1).
> 6. **Sound-section overlaps:** all nine annotated pairs have a sentence-, row- or subsection-level anchor that separates them. One unannotated pair was genuinely ambiguous, item_b DEF-02 against the sound entry for §5.5/§7.9; I added a `disambiguation` field on both sides (edit E2). None remain ambiguous. All five keys still load as valid JSON.
> 7. **Difficulty probe** (written blind, before opening any key): my top 5 were all planted flaws in every document, 25/25 overall, and I found 0 valid issues the keys lack.
>
> | Document | Top 5 planted | Criticals missed from my top 5 | Wider-list recall |
> |---|---|---|---|
> | item_a | 5/5 | 0/2 | 13/14 |
> | item_b | 5/5 | 0/1 | 11/14 |
> | clinical v1 | 5/5 | 1/4 (F04) | 14/14 |
> | payments v1 | 5/5 | 1/4 (F08) | 12/14 |
> | lakehouse v1 | 5/5 | 0/4 | 12/14 |
>
> Both missed criticals were in my wider list. This points to a risk that strong reviewers will find every critical flaw (open P1). I am probably the same model family that wrote these documents, so treat these numbers as an upper bound.
> 8. **Open issues:** P1: encrypt or relocate the blind keys before any held-out run. P1: the high detection rate above. Score must-mention detail, minor flaws and false-positive traps separately from detection. P2: items P2-11 to P2-14 are still unapplied. P2: the legal sources are snippet-only, and IEEE 1547-2018 (DEF-03) has not been read. P3: the lakehouse README's exact word counts can't be reproduced; the "deliberately" wording is optional to change; PDF-based runs from before today aren't comparable with later ones. I also deleted my own `*.png` renders from the scratchpad with a glob without listing the directory first.
>
> No git commands were run, and `spec/` and the canonical keys were not touched.

## Subagent report: Verify docs and budget

> I verified all 8 items against the claude-api skill, the lab brief (pp. 7-9) and a run of `cost_model.py`. Fixes are in place and the full report with edit log is at /home/user/SIT/research/audit/verify_docs.md. No git commands were run, and nothing under `eval/blind/` was opened.
>
> 1. **API facts** (22 claims): the ID, no snapshot, no sampling params or seed, effort levels with `medium` default, and PDF support are correct. Corrected the `fallbacks: "default"` description (routes by refusal category; never retries `reasoning_extraction`; fallback model loses Opus 5.5's thinking blocks). 32 MB is the request limit, so about 23 MB of PDF. Added refusal handling: branch on `stop_reason`, category may be null, discard mid-stream partials. Added the 512-token cache minimum and 4-breakpoint limit, which no doc stated.
> 2. **Budget**: the old 433 runs / $777 was wrong. "Matched runs, lines 2-8" was really lines 1-8; v2 re-review needs two variants per doc (methodology §5); SIT v2 belongs on demo day. Corrected plan: 442 runs / $796, budget to approve $1,812 (was $1,772). With the 9 items that exist today: 300 runs / $582, so 142 runs depend on documents not yet commissioned.
> 3. **Lab coverage**: every 5.1, 5.3 and 5.4 a-d item has a row. Added four missing 5.2/5.4 rows to DOCUMENTATION_MAP: access granted before the deadline, repo accessible through evaluation, "review, deploy and execute", and the session format.
> 4. **Consistency**: the 8-token minimum, the 0.90 threshold and the 3-location cap match the schema and taxonomy. ADR-007 contradicted the spec on the match window and used different field names (`locations[]` vs `doc_anchors[]`). Fixed: match metadata now goes in `anchors.json`. The LangGraph-for-resume condition was never fully resolved, so I added ADR-009: on-disk checkpoints in our own loop, and completed tool calls are reused on resume.
> 5. **Methodology**: a concurrent edit had already swapped A4 for A4e. I added the one-line note on what is lost and listed A4e in the Holm correction family.
> 6. **Judge branches**: ADR-002 now explicitly covers the agent only, with the grader pending under ADR-003. The models note now matches ADR-003's branch-B wording, including the "local model fails validation" path and the disclosed limitation.
> 7. **SEALING**: the `age` commands were confirmed against its README and an actual encrypt/decrypt round trip, and work on macOS and Linux. Fixed portability: tar is built with Python's `tarfile`, the plaintext tar never touches disk, and `shred` is gone. The GPG alternative could not be tested (its agent would not start in the sandbox). The interim rule is stated in §6.
> 8. **Runbook dry-run**: none of the code or config it uses exists yet; a new §9 lists what must be built. Two live-change steps would have failed as written: the new stop rule needs a code from the closed stop-reason enum, and `executive_summary` is not in the schema. **Top open issue (P1):** switching effort between stages invalidates the prompt cache, adding about $1.20 per run (roughly $500 overall). That is more than the 30% margin on agent spend and is not in the budget. Decide at build time: keep one effort level per conversation, or use the per-message effort beta.

## Coordinator

[Commit + push "Verify eval fixes, rebuild synthetic PDFs reproducibly, add verify_eval audit" (docs verification swept into the same push).]

Both verification reports are already on the remote (the docs one was swept up in the previous push). Two verifiers left: spec and the research reconciliation, plus the Mac probe report.

Two findings from this pair that change the plan:

- **The planted flaws may be too easy.** The eval verifier read each design doc cold and found every one of its top-5 issues was a planted flaw, 25 of 25, and recovered 12 to 14 of 14 on the wider list. It's likely the same model family that wrote them, so that's an upper bound, but it means detection alone won't separate a good agent from a great one. The scoring must weight must-mention detail, minor flaws, and the false-positive traps separately, which the metrics note already supports.
- **The budget had an arithmetic error and a hidden cost.** Corrected count is 442 runs, about $800 agent spend, with only 300 of those runs possible on the documents that exist today. Separately, switching effort level between phases invalidates the prompt cache and would add roughly $1.20 per run, about $500 across the programme. The fix is one effort level per conversation, decided at build time.

Smaller items handled: the UK refund-law statement in blind item A was re-verified and tightened, all six synthetic PDFs were rebuilt with a committed build script and now match their markdown, and the decision record gained an ADR for on-disk checkpointing in our own loop so the "switch to LangGraph if we need resume" question is closed.

---

## Subagent report: Reconcile research notes to decisions

> 1. All 32 conflicts and both factual slips are reconciled in place across the six notes and their companion files (frameworks, models, methodology + metrics, grading + grader_prompt + worked_examples, robustness + scenarios, kaggle + candidates). Analysis text keeps its wording with a "Superseded (reconciliation 2026-10-02)" callout naming the ADR, spec section or audit item; tables and schemas now state the canonical value. Nothing in spec/, docs/ or eval/ was touched, and no git commands were run.
> 2. Grading: the rubric stays 0-4. Severity, category and triage wording now uses the spec taxonomy, and matching defers to metrics.md §2 and the spec credit modes. Key-aware "recall" is diagnostic only and was removed from the D3 anchor. In grader_prompt.md every finding reference now uses the spec finding-ID format (FND-nnn), key_id uses the spec flaw-ID format, and a new required severity_assessed field uses critical/high/medium/low; both schemas still pass Draft 2020-12 validation.
> 3. Methodology: the taxonomy and key schema now point to spec/taxonomy.yaml and spec/answer_key.schema.json, severity weights map to the spec enum, and §2.1 now explains the credit modes. A4 had not been changed by anyone else, so I replaced it with A4e (README table, Table 1, metrics Holm family). Robustness: added a legend note on spec enum names (S1-S3 is test-failure impact, not finding severity), tied INV-03 to INV-10 to spec fields, and added a §10 table mapping each architecture need to the ADR and spec fields that satisfy it.
> 4. Models: the grader section matches pending ADR-003; I added small notes on the 0-3 scale (C1), the two-rater plan (C2), sample size (C21) and the two remaining "60K" mentions. Frameworks: the "switch to LangGraph" row now follows ADR-009, which appeared during this pass (durable human-in-the-loop interrupts, or the resume tests can't be passed within about 200 LOC). Kaggle: no contradiction with the grader design; Recs 1, 3 and 7 got notes for C1, C27 and C2, and Rec 8 and candidates.md now say eval/blind is not blind.
> 5. Not fully resolved: C2 tiers and the C21 minimum detectable effect have no canonical home until prereg.yaml exists. C27 and C1 follow the audit's recommendation because no ADR or spec entry covers them. C3 is only made conditional because ADR-003 is pending. Action-type accuracy, BEH-16, INP-28 and BEH-08 are marked BLOCKED (no expected_disposition values or sound control docs yet). The eval READMEs and keys are out of scope. ADR-007's evidence-ID format (E-012) disagrees with the spec's EV-nnn format, and spec anchor_rules lacks ADR-007's page ±1 bound.
> 6. The full table (conflict, files edited, what changed) and the unresolved items are in /home/user/SIT/research/audit/reconciliation_log.md. docs/DECISIONS.md and spec/README.md changed while I worked and the notes are aligned to the new text; re-check if they change again.

## Coordinator

[Commit + push "Reconcile research notes to canonical spec and decisions".]

Reconciliation is pushed. All 32 cross-note conflicts now either state the canonical value or carry a superseded marker pointing to the spec or decision record. Two small residual mismatches surfaced that the spec verifier can close: the evidence-ID format differs between an ADR and the spec, and the spec's anchor rules lack the page bound the ADR specifies.

One verifier left, the spec one, plus the Mac probe report. Nothing to request until those arrive.

---

## Subagent report: Verify spec against everything

> 1. **Validator now passes with new tests.** `python3 spec/validate_examples.py` passed at the start. I added 28 adversarial cases plus a check that anchor quotes resolve against the page-marked text (robustness INV-04); it passes with all of them. 12 of the 28 cases were wrongly accepted before I fixed the schemas: delta/full review rules, items without a v2, secondary disposition repeating the primary, contrary evidence cited as support, quote not matching the ledger, page out of range, undisclosed degradations or fallbacks, stray URLs, and a one-sided regression link.
> 2. **Two real bugs fixed.** In `taxonomy.yaml`, the unquoted `yes`/`no` keys in `legacy_mappings.verdict` were read by YAML as `True`/`False`, so that mapping silently did nothing. `finding.schema.json` used example IDs from a real eval flaw (clinical F14's `D-15`, section `9.3`) and from the SIT sample; those descriptions go to the model. `answer_key.schema.json` used item_b's document ID. All replaced with invented IDs; the leakage grep is now clean.
> 3. **The 32 conflicts.** The spec README recorded resolutions for only 15; it listed the other 17 as out of scope with no disposition. I added a table giving each of the 17 an owner and the schema field that supports it. All 15 adopted resolutions are actually in the YAML/JSON. Three differ from the audit (dispositions, 9 categories, the per-flaw credit mode), and none conflicts with the lab brief.
> 4. **Lab brief and grader.** Everything in the brief is representable. The one gap is that an approved decision contradicted without a `challenges` label can only be caught by a judge. The grading docs were updated by another agent during my run to use the spec's `FND-` IDs. I defined a grader view that drops model names and tool traces, and mapped the grader's `not_applicable` triage label.
> 5. **Robustness invariants.** INV-04, 05, 07, 09 and 10 could not be checked from a Review. I added fields for each: the text path, a tool-call log, degradation IDs linked to limitations, echoed criteria and fault schedule, and per-iteration registry hashes. INV-01, 02, 08 and 11 are process-level checks.
> 6. **Converter.** `spec/convert_answer_keys.py` converts all 73 flaws to the five `answer_key.canonical.json` files, with 0 validation failures and 0 unmapped fields. Partial mappings: 8 blind external facts keep the citation inside the claim, and 20 synthetic external-fact claims are placeholders. I wrote the canary as null and pending rather than generating a new UUID as the README said. All five keys stay not ready for scoring.
> 7. **Open issues.** P0: every key still needs `core_insight`, anchor quotes, `expected_disposition` and approved decisions, written by a person. P0: the converter added two more plaintext copies of the held-out keys, which the sealing step must cover. P1: putting `categories` in the agent prompt reveals the planted mechanisms. The blind keys were edited concurrently during my run (a new item_b DEF-02 overlap, now in the converter); rerun the converter after any key edit.
> 8. **Files and one slip.** All edits are logged in `/home/user/SIT/research/audit/verify_spec.md`; other changes are under `/home/user/SIT/spec/` (including the new `/home/user/SIT/spec/convert_answer_keys.py`) and the five `eval/*/*/answer_key.canonical.json` files. Against instructions, my final check command included a read-only `git status`. It printed nothing and changed nothing.

## Coordinator

[Ran validator (ALL CHECKS PASSED) and converter (73 flaws, 0 failures); already captured in prior push. Refreshed `README.md` to the current layout and status; commit + push. Sent the Mac session a status-check message. Launched two Opus agents: (1) agent package skeleton with frozen interfaces, config, prompts, tests; (2) `eval/prereg.yaml`, `eval/EVAL_PLAN.md` Tier A/B/C, `eval/human_labelling_protocol.md`, Tier A rows in BUDGET.md.]

All five verifications are complete and pushed. The next phase is the agent itself, and the fresh-eyes audit named the three things that matter most: build a thin-slice agent, measure real latency on your laptop, and get a human-written answer key for the SIT document. I'll start the first now, with the architecture skeleton and interfaces first so parallel module builds can't drift apart, plus the pre-registration file the methodology needs, and I'll nudge the Mac session which hasn't reported yet.

Here's where things stand after the full research, audit, and verification cycle. Everything is on the branch; 28 commits.

### What exists now

| Layer | Contents | Verified by |
|---|---|---|
| Research (6 notes) | Framework, model and judge, Kaggle, methodology, grader rubric, 166 robustness scenarios | Loophole audit, reconciliation pass |
| Eval data (5 items) | 3 synthetic docs with v1/v2 and PDFs, 2 held-out docs, 73 planted flaws | Fact-check of ~35 external claims, fix pass, re-verification |
| Spec | Canonical taxonomy, Finding/Review schema, answer-key schema, converter | 28 adversarial schema tests, all 73 flaws convert |
| Governing docs | ADRs, your decisions, reproducibility, demo runbook, sealing, budget | API-reference check, budget arithmetic reconciled |
| Scripts | MCP probe for your Mac | Self-tested against a local MCP server |

### Running now

- **Agent skeleton**: package layout, typed interfaces, config YAMLs that serve as the live-modification surface, prompts with leakage rules, and test scaffolding. Once it lands, three implementers fill the modules in parallel without interface drift.
- **Pre-registration and scoped eval plan**: a Tier A core of roughly 100 runs sized to support every claim the submission will make, plus the one-person human-labelling protocol.
- **Mac session**: nudged for its probe report; no reply yet.

### What I need from you

1. **API credit, not subscription tokens.** The agent bills per token through an API key. Tell me whether you have API credit and roughly how much, so the eval plan is sized to it.
2. **A human-written answer key for the SIT Memory Platform document.** This is the single highest-value control against the circularity problem, where one model family wrote the eval data, the audits, and will run the agent. It needs to be you, done before you ever see the agent's output on that document. Budget two to three hours. I'll have the protocol ready in `eval/human_labelling_protocol.md`.
3. **The Mac session**: if it's waiting on you for the shared MCP key from page 4 of the lab PDF, give it the key in the shell. Its report decides the judge branch and part of the tool architecture.

---

## Subagent report: Pre-registration and cut-down eval plan

> I wrote and updated the four files. Tier A comes to 132 runs: 96 scored and 36 support (dev iteration, robustness gate, rehearsals). That costs $564 for Anthropic only or $639 with a second-provider grader, both including the 30% margin, so **the owner should approve $650**. Agent runs alone are $240.12. It needs about 18 human hours: 14.9 of labelling and 3 of writing the SIT v2 fixture. Tier B adds 63 runs for $278-323, and the full 442-run programme ($1,147-1,812) stays the reference in docs/BUDGET.md.
>
> - **The power is low and the plan says so.** The minimum effect of interest is 0.10 recall. With 5 keyed documents (70 flaws) the smallest detectable difference is about 0.22-0.27, and about 0.33-0.40 on the two held-out documents alone. The confirmatory test is FULL vs B0 and FULL vs B0-$ on recall (Holm). H1 counts as supported only if the pooled result is significant and the held-out-only estimate is also positive. A null is reported as "no evidence at this n", with the minimum detectable effect.
> - **I made three changes to the fresh_eyes scope:** B0-$ moved into Tier A, because the methodology and BUDGET's "never cut" list require a cost-matched baseline. It adds 15 runs ($33). A4 is a Tier B Sonnet-5.5-as-agent ablation and A4b a Tier B effort sweep, per USER_DECISIONS. The old low-effort A4e is dropped. The owner grades 10 reviews: 5 for calibration plus a 5-review sample from the frozen agent.
> - **Tier A supports 12 claims**, each mapped to the runs that back them in EVAL_PLAN §1.4. The schedule allows 4-6 build days then 5 eval days. Two owner tasks are on the critical path: the SIT key must be written and hashed before any agent run on the SIT document, and the 45 S-dev `core_insight` sign-offs must be done before the matcher can be validated.
> - **The pre-registration is a draft (`frozen: false`).** Only the fields listed under `freeze.fill_before_freeze` may change before the freeze. Those are pilot-measured values, model ID, and prompt and commit hashes. The freeze steps include an outside timestamp: email the hash to the SIT officer or push a signed tag. The draft hash is 63cd8a6f…c40, recorded in EVAL_PLAN §4.
> - **Three gaps are written into the plan:** The held-out items have no PDF, so a script must render them inside the unseal session. The held-out `core_insight` fields are completed in that same session, after the frozen agent has run. Reviews of the SIT document go to a second-provider grader only with SIT's written agreement.
> - **Sealed material:** I opened nothing under eval/blind/, no answer keys, and skipped spec/README.md §2.4, §2.6 and §2.7. research_audit.md §4.3 names the held-out defects, so this session counts as exposure. It is listed in the prereg's `access_log_policy.prior_exposures_to_record`.
>
> Files are in /home/user/SIT: eval/prereg.yaml, eval/EVAL_PLAN.md, eval/human_labelling_protocol.md, docs/BUDGET.md (new §6 plus a pointer in §4)

## Coordinator

[Validated prereg.yaml; commit + push "Add pre-registration draft, scoped eval plan, and human labelling protocol".]

The scoped eval plan is pushed. This is the figure to approve instead of the $1,800 one:

| Tier A core | Figure |
|---|---|
| Runs | 132 (96 scored, 36 support) |
| Agent API spend | about $240 |
| Total with grading and 30% margin | about $565 Anthropic-only, $640 with a second-provider grader |
| Your time | about 18 hours (15 labelling, 3 writing the SIT v2 fixture) |

The plan is honest about statistical power: with five keyed documents the smallest detectable recall difference is about 0.22 to 0.27, so it reports a null result as "no evidence at this sample size" rather than claiming the agent doesn't help. Twelve claims the submission will make are each mapped to the runs that support them.

Two things sit on your critical path and no agent can do them: write the SIT document answer key before any agent run touches that document, and sign off the 45 core-insight fields on the dev keys so the matcher can be validated.

The agent skeleton is still being built. Mac session still silent.

---

## User

> the current running task, how long will it take / approx amountof tokens? i have about THIS account mex3woofz has ~50 dollars left. but i ahve 2 other accounts, have 250 dollars left. can i "Continue runing"? in the other account ? that is also linked to same github account

## Coordinator

[ListAgents: skeleton builder running 19 minutes. Wrote `docs/HANDOFF.md`; commit + push.]

The skeleton build has been running 19 minutes. Based on the previous builders, it's probably 5 to 15 minutes from finishing, at roughly 400k to 600k tokens total. Stopping it now would waste what's already spent, so I'll let it finish and then stop launching new work until you say otherwise.

Yes, you can continue from another account. Nothing in this session is needed except the GitHub branch. I'll write a handoff file now so a fresh session in the other account can pick up with no conversation context.

Handoff is pushed. Here's the picture on cost and switching.

**Cost of what's been run.** I can't see your billing, but I can see token usage. The 24 subagents so far used about 5.2 million tokens between them, mostly cached input. The one still running is the biggest single build and will likely finish in 5 to 15 minutes. I'm not launching anything new after it until you say so.

**Continuing in another account: yes.** Everything is on the GitHub branch, nothing depends on this session. In the other account, start a cloud session on `malcolm1232/SIT`, branch `claude/eloquent-sagan-ah5ttk`, and give it this first message:

```
Read docs/HANDOFF.md and continue from "Next build steps". Keep the operating rules in that file.
```

Three things do not transfer:

- This conversation's context. The handoff file covers it.
- The Mac Remote Control session, which belongs to this account. You'd start a new one from the other account with `claude remote-control` in the repo folder.
- Any check-in I'd schedule here. Don't rely on this session after you switch.

**One warning on the $50.** The remaining spend in *this* session is the running build only. The API spend for actually running the agent, the $240 to $640 Tier A figure, is separate and bills to whatever API key the agent uses, not to the account running Claude Code. Make sure the API key you give the agent is on the account with the $250.

When the skeleton build reports back, I'll commit it, push, and stop. Tell me if you'd rather I stop it now.

`[stop hook → commit + push: "WIP: agent skeleton in progress"]`

---

## User

> also u mean the money might be distributed to not just cladude but google and openai? how much do u reocmmend i top up? and also, can u write a very explicit handover to what was done, what agents were used and files pointed etc. and lessons learned and u as the delegator, to hand over what is next and save entire conversation verbatim?

## User (mid-turn)

> also i added keys into environment. can u check?

## Coordinator

[Found: main session transcript is stored server-side, not in the container; 36 subagent JSONL transcripts (88 MB) exist locally, 5 containing the key prefix. Copied all 36 into `docs/transcripts/subagents/*.jsonl.gz` with the key redacted. Wrote `docs/transcripts/README.md` (subagent index with roles and outcomes) and `docs/HANDOVER_FULL.md`. Checked the environment: no API key variables visible in this running session; environment-level secrets reach new sessions only. Began writing this verbatim transcript.]

No API keys are visible in this running session. Keys added in the environment settings reach new sessions only, so this one will never see them, but the next session you start (in either account) will. The agent code reads `ANTHROPIC_API_KEY`, and the judge branch will look for `OPENAI_API_KEY` or `GEMINI_API_KEY`; the probe reads `SIT_MCP_API_KEY`. Please don't paste any key into the chat.

---

## Subagent report: Agent package skeleton and interfaces

> 1. **Built:** the package skeleton, interfaces, config, prompts and test scaffolding are in place, and all three workstreams can start now. `pip install -e ".[dev]"` (venv in the scratchpad), `ruff check .` and pytest all pass: **158 passed, 10 skipped**. The 10 skips are the not-yet-built modules in `tests/test_pending.py`, each labelled "phase 1/2/3 (workstream A/B/C)". `spec/validate_examples.py` still passes.
> 2. **Fully working now:** `models.py` (mirrors `spec/finding.schema.json` exactly; round-trips the spec's example Review byte for byte and validates with jsonschema), `config.py`, `verify_anchor` (15 anchor tests, plus 75 of 75 sample anchors resolving on a synthetic dev PDF), the evidence ledger, decision registry, checkpoints, the orchestrator loop, stop rules, `FakeGateway`, record/replay cassettes, the fault-schedule loader and `check_INV_03`..`check_INV_10`. Everything else is a typed stub.
> 3. **Pins (checked on PyPI today):** anthropic 1.11.0, mcp 2.2.0, httpx2 2.13.1, httpx 0.28.1, pydantic 2.13.5, pdfplumber 0.11.10, pyyaml 6.0.3, jsonschema 4.26.0, jinja2 3.1.6, typer 0.27.2, rapidfuzz 3.14.6; dev: pytest 9.1.1, pytest-asyncio 1.4.0, ruff 0.16.10. Entry points are `sit-review` plus a `dra` alias, so the runbook commands work as written.
> 4. **Where I departed from the brief, to match the repo docs:** The page marker is `[[PAGE n]]`, not `<<page N>>`, because ADR-006, the spec oracle and the grader all use it. Config is split across `agent.yaml`, `stop_rules.yaml` and `tools.yaml`, with the runbook's pinned lines (enforced by `tests/test_config_layout.py`). `agent.yaml` adds phase flags, transport/replay, fault schedule and report options below line 12, plus a `files:` block pointing at the other files.
> 5. **More departures:** `Phase.run` is `async`, so the MCP warm-up can overlap ingest. Every stage's effort is `high` (USER_DECISIONS #1), not `research: medium` as the runbook shows. The browser server is off by default (fresh_eyes N15). Criteria use `question` (`description` also accepted, so the runbook's 4-line append works), `lab_ref`, and a `kinds` list rather than a single kind.
> 6. **Interfaces the docs left open, which I decided:** `understand` uses the `plan` effort level, since the runbook's pinned effort block has no `understand` key. `refine` maps to provenance phase `revise`. The research-iteration cap reports `budget_tool_calls` with detail `max_research_iterations`, since the closed enum has no iteration code. Each document gets its own text file, `text/<doc_id>.pages.txt`, because delta mode has two documents. The ledger is journalled per entry to `ledger.jsonl`; `ledger.json` is the final snapshot.
> 7. **More open interfaces, decided:** Tool names shown to the model are `<server>__<tool>`. The model emits constraint-free draft types (`llm/outputs.py`), which `verify` turns into canonical Findings. Criterion IDs are stored in `RunState.finding_meta` for `explain`, because Finding allows no extra fields. `ExitCode` 5 is resume-on-drift, the "distinct code" ADR-009 asks for without a number. I also added `prompts/system.md` (the shared cached prefix) and `prompts/PROMPTS.lock`.
> 8. **Workstreams and open issues:** `/home/user/SIT/agent/README.md` has the module map, phase contract, freeze rule and ownership: A = model calls, B = tools and research, C = verify, report, resume and the CLI run. Heading detection in `ingest/pdf.py` is heuristic: it drops table-of-contents entries, but numbered lists still create duplicate section IDs, and anchor checking tries each candidate. That is for C to refine. I removed the generated egg-info and caches. I ran one read-only `git status` despite the no-git instruction; it showed that some of my files had already been committed by someone else mid-session.

## Coordinator

[Commit + push "Add agent package skeleton with frozen interfaces, config, prompts, tests; handover docs and subagent transcripts". Completed this transcript; final commit + push. Final reply to the user with the money recommendation and handover pointers follows in the session.]

*End of transcript at the point of handover. The Mac Remote Control session (`session_012eEnGCC8NwJFN3ojoqW4gD`) had not reported back when this transcript was written.*
