# Fresh-eyes review: evaluator memo and sceptical research review

Date: 2026-10-02. Written in two roles: (1) one of the two SIT officers grading the repository as if it were submitted today, using the lab brief (pp. 1-9) as the rubric; (2) a sceptical reviewer checking the research package against the user's "research grade" bar after both audits and the fixes. Nothing outside this file was edited and no git commands were run.

**Exposure disclosure (SEALING.md §6 rules 4 and 6).** As instructed, this session read `eval/blind/item_a/README.md` and `eval/blind/item_b/README.md` (domain, size, defect count only) and listed file names under `eval/`. It did not open any `answer_key.json` or any `design*.md`. It also read `research/audit/eval_data_audit.md`, the head of `research/audit/eval_fixes_applied.md` and `spec/README.md`, which contain S-heldout key content (see R-03). This is exposure, not an evaluation; record it in the access log when that log is created. This file does not quote or paraphrase any S-heldout item.

---

## Part 1. Evaluator memo (SIT officer, grading today's repository)

### 1.1 What I graded against

| Brief section | What it asks for |
|---|---|
| §2.3 | A professional review: design intent, fitness for purpose, strengths, risks, gaps, ambiguities, unresolved assumptions, validation needs; per refinement: issue, rationale, evidence, expected benefit; otherwise why no change is needed |
| §2.4 | Completion only after review against objectives, sufficient research and incorporated evidence; output verified as complete, consistent, accurate and traceable; unresolved issues stated |
| §5.1 | Source code, config, prompts, instructions, workflow definitions, memory configuration, orchestration logic, docs, dependencies, install steps, execution procedures; plus the lab-session outputs with evidence |
| §5.2 | GitHub repo, two SIT IDs invited, clearly organised, install/config/run instructions, dependencies, datasets, model requirements, third-party services, no secrets |
| §5.3 | Eight documentation topics |
| §5.4 | Walkthrough, laptop that runs and can be changed, live run on a new SIT artefact, live modification |

### 1.2 Overall impression

This is a planning and research submission, not yet an agent submission. There is no agent code. I count about 13,600 lines of Markdown, a probe script, a schema validator and a cost model. Against §5.1 the submission would fail today. Graded as a plan, it is far above what I would expect from a lab exercise, and the planning quality makes me confident the participant understands the problem. My concern is whether the plan can be delivered in time and whether the participant can explain it in ten minutes.

### 1.3 What is impressive

- **Traceability to the brief.** `research/grading/README.md` §2 ties every rubric dimension to a verbatim sentence from the brief. `docs/DOCUMENTATION_MAP.md` maps every §5.1-§5.4 item to a file and a status. This is exactly how I would want a submission to read.
- **Design decisions are recorded with alternatives** (`docs/DECISIONS.md`, ADR-001 to ADR-008): why a custom loop, why one model, why both PDF views, why quote anchors are checked in code. ADR-006's argument for giving the model both the native PDF and a canonical page-marked text, so every quote is checkable against what the model was told to quote from, is a good engineering judgement.
- **Lab §4.2 (doc vs research separation)** is designed in, not bolted on: `source: doc | external | inference`, ledger IDs instead of model-written URLs (`spec/README.md`, ADR-007).
- **Restraint is measurable.** Sound sections, a correctly-declined rate, `no_change` as a first-class disposition with a required rationale. Most participants will not have this.
- **The demo runbook** (`docs/DEMO_DAY_RUNBOOK.md`) anticipates cold starts, the shared-key failure, refusals and network loss, with drills and exact files and lines for live changes.
- **Honesty.** The audits criticise the participant's own plan in public, and the limitations are stated rather than hidden (e.g. the "blind" set is reclassified as not blind).

### 1.4 What is confusing

1. **`README.md` is stale and contradicts the docs.** It says `docs/` is "to come" (six docs exist) and that `eval/blind/` holds items "authored by agents with no knowledge of this project", which ADR-004 says is untrue. It has no install, configuration or run section and no status table.
2. **Identifier collisions.** "G1/G2/G3" means grader gates (`grading/README.md` §4.2), audit loopholes (`research_audit.md` §4.1, cited by ADR-007) and grounding checks (`methodology/metrics.md` §5.1). "D1-D5" are rubric dimensions and also spec deviations (`spec/README.md` §4). "C1-C32" are audit conflicts and "C01-C10" are key edits. An evaluator following a cross-reference will land in the wrong table.
3. **Too many tiers and names** for one reader: S-dev, S-heldout, Blind, Real-dev, OOD, sound controls, rehearsal pool, G⁺. The directory called `eval/blind` holds the S-heldout tier.
4. **No reading order.** I had to find out myself that the audits must be read first and that `docs/` supersedes parts of `research/`. Nothing records which of the 24 audit actions are done.
5. **Research notes claim to be "reusable outside this project"**, but large parts of them are about this repo's IDs. As an evaluator I cannot tell which statements are binding on the build. The ADRs are binding; most of `research/` is background. Say so.
6. **Model names I cannot check** (Opus 5.5, GPT-6.1 Sol, Gemini 3.1 Pro) appear with prices; some are marked UNVERIFIED and some are not. Unverified prices also sit inside budget totals (`docs/BUDGET.md` §3).

### 1.5 Missing relative to §5.1-§5.4

Files I looked for and did not find (checked by path on 2026-10-02):

| Brief | Looked for | Found? |
|---|---|---|
| §5.1 source code, orchestration logic, workflow definitions | `agent/`, `agent/states.py`, `agent/stop_rules.py` | No |
| §5.1 configuration files | `config/agent.yaml`, `stop_rules.yaml`, `tools.yaml`, `criteria.yaml`, `endpoints.yaml`, `url_policy.yaml`, `persona.yaml` | No (specified only in the runbook) |
| §5.1 prompts | `prompts/`, `prompts/PROMPTS.lock` | No |
| §5.1 dependencies | `pyproject.toml`, `uv.lock`, `.python-version` | No |
| §5.1 install and execution procedures | Install/Run sections in `README.md`, `Makefile` (`make smoke`) | No |
| §5.1 memory configuration | `docs/MEMORY_STATE.md` | No |
| §5.1 lab-session outputs and evidence | `outputs/lab_session/`, `runs/` | No (produced on demo day) |
| §5.2 secrets handling | `.env.example`, `.gitignore`, gitleaks hook | No. There is no `.gitignore` at all, while ADR-005 assumes `.env` is ignored and `scripts/README.md` creates `scripts/.venv` and `mcp_probe_results.json` inside the repo |
| §5.2 "clearly identify dependencies, datasets, model requirements, third-party services" | A Requirements section in `README.md` | No |
| §5.2 no secrets | Key prefix removed from `research/robustness/scenarios.md` OPS-02 | No: the first 8 hex characters of the shared MCP key are still there (audit P0 action 7 not done) |
| §5.3 architecture | `docs/ARCHITECTURE.md` with a diagram | No |
| §5.3 context management | `docs/CONTEXT_MANAGEMENT.md` | No |
| §5.3 planning and execution | `docs/PLANNING_EXECUTION.md` | No |
| §5.3 tool orchestration | `docs/TOOL_ORCHESTRATION.md` | No |
| §5.3 validation and review | `docs/VALIDATION.md` | No (`REPRODUCIBILITY.md`, `SEALING.md` exist) |
| §5.3 assumptions and limitations | `docs/LIMITATIONS.md` | No |
| §5.3 framework and technologies | ADRs | Partly (ADR-001, 002, 006) |
| §5.4(a) deck | `docs/slides/` | No (optional) |
| §5.4(b)-(d) evidence of readiness | rehearsal log, `runs/sit_v1_frozen/`, cassettes, `mcp_probe_results.json` | No. The MCP servers have never been reached (audit U1, U2 still open) |
| Evaluation results | `prereg.yaml`, `eval/score.py`, `eval/run_matrix.py`, `eval/costs.csv`, any results table | No |
| Sealing | `scripts/seal.py`, `scripts/unseal.py`, `scripts/leakage_grep.py`, `eval/heldout/`, `ACCESS_LOG.md` | No (design only) |
| Licence | `LICENSE`, data statement for `eval/` | No |

### 1.6 What the minimum viable agent must contain to satisfy §2.3 and §2.4

| Brief requirement | Minimum mechanism | Where it is already specified |
|---|---|---|
| §2.3 explain design intent | `understand` stage writes `intent_summary` (purpose, scope, objectives, constraints, requirements) and a pinned `decision_registry[]` | `spec/finding.schema.json` `Review`; ADR-001 |
| §2.3 assess fitness for purpose | One verdict `fit / fit_with_conditions / not_fit`, conditions linked to finding IDs, a confidence and "what would change it" | `spec/taxonomy.yaml` verdicts |
| §2.3 six categories | Findings typed by `kind`; the report has one section per kind and writes "none found, because …" for an empty kind | schema `kind` |
| §2.3 per refinement: issue, rationale, evidence, benefit | `recommendation{issue, rationale, supporting_evidence_ids, expected_benefit, objective_refs}`; code rejects a recommendation missing any field | schema; INV-06 |
| §2.3 no-change justification | `disposition: no_change` requires `no_change_rationale`; at least one affirmed area or an explicit statement that none was found | schema |
| §2.4 reviewed against objectives | Every finding cites `objective_refs` or a requirement ID; a coverage check lists objectives with no finding and no affirmation | runbook `dra coverage` (could be a report table instead) |
| §2.4 sufficient research | A stop rule with a recorded `stop_reason`; every finding that needs an external fact has ≥ 1 ledger entry read before citing, or is moved to `unresolved[]` | `config/stop_rules.yaml` spec; `read_before_cite` |
| §2.4 evidence incorporated | Ledger-ID citations only; renderer turns IDs into URLs and dates | ADR-007 |
| §2.4 complete, consistent, accurate, traceable | A code `verify` stage: schema-valid; anchors resolve in `doc.pages.txt`; ledger IDs exist; verdict consistent with the highest severities; every non-refinement disposition is in `unresolved[]`; the same checks over the summary and verdict prose (see R-12) | ADR-007; `spec/validate_examples.py` `review_semantics` |
| §2.4 unresolved issues stated | `unresolved[]` section with owner and next step | schema `next_step` |
| §1.5 updated artefact | Delta mode: document diff first, then prior-finding status (see R-09) | INP-22 |
| §2.2 / §4.4 tool use | Two MCP servers (search, scholarly) behind one gateway with timeouts and a doc-only fallback; browser and document-intelligence off by default | ADR-001; runbook §4.1 |
| §5.4 (c) live run | Progress line every ≤ 10 s; finishes inside the slot; report renderable without an LLM call (see R-08) | DEMO-15; DEMO-05 |

Everything else in the plan (resume, `explain`, coverage command, personas, fault-injection framework, LLM replay transport, sealing tooling) is valuable but not required by §2.3 or §2.4.

### 1.7 What I would ask in the walkthrough

1. "Show me the line of code where the agent decides it has done enough research. What does it do when search returns nothing?"
2. "How long does one run take on our document, and what does it cost? Measured or estimated?" (Today: estimated only; latency is UNVERIFIED.)
3. "Your evaluation documents follow the structure of our Memory Platform design. Who wrote them, which model, and did you have our permission to derive material from an SIT Internal document?"
4. "Your agent, your test documents, your audits and possibly your grader are all the same model family. Why should I believe the numbers?"
5. "If the updated design contains comments from other AI reviewers or humans (§1.5), does your agent treat them as design content, as evidence, or as claims to check?"
6. "Your delta mode compares against your own v1 review. Our v2 was changed in response to other reviewers. How does the agent handle changes it never asked for, and fixes it suggested that were not made?"
7. "An 8-token quote proves the text exists. How do you catch a finding that quotes correctly but misrepresents what the text means?"
8. "Which of the 166 robustness scenarios have you actually run?"
9. "What is one failure you observed in testing, and what did you change because of it?"
10. "Why Opus for every call at high effort, and what happens to run time if I ask for `max` effort?"
11. "Where do findings about our confirmed decisions go? Show me one that the agent chose not to challenge."

### 1.8 What I would ask the participant to modify live

The runbook prepares four requests. I would probably ask for at least one it does not cover:

| Request | Covered? |
|---|---|
| Add a review criterion (e.g. PDPA, cost) | Yes (runbook §4.2 #1) |
| Stop after N searches / new stop rule | Yes (#2a, #2b) |
| Disable a tool | Yes (#3) |
| Change model or effort | Yes (#4) |
| "Only report high and critical findings" / "be more conservative" | No. It is in `grading/README.md` §9(d) but not in the runbook's pinned lines |
| "Give me the output as a risk register table with Likelihood, Impact, Owner" | Partly (template exists in plan, DEMO-08 covers only an executive summary) |
| "Only use authoritative sources: allow-list these three domains" | No (`url_policy.yaml` is a deny list; no allow-list mode is rehearsed) |
| "Pause and let me approve the research plan before it searches" | No. `--plan-only` prints and exits; there is no approve-then-continue. ADR-001 names durable human-in-the-loop interrupts as the reason to switch frameworks, so this request lands on a stated weakness |
| "Add a tool: a calculator or Python check for the arithmetic in section X" | No. Fixed action types make a new tool a code change that is not rehearsed |
| "Write it for an executive audience in one page" | Partly (persona switch is prepared; length cap is not) |

### 1.9 Provisional grade (plan only)

If SIT graded the plan and research alone: strong on §4 (design guidance), §5.3 intent and §5.4 preparation; failing on §5.1 and §5.2 deliverables because nothing runs. The single most valuable thing the participant can do next is build a thin, working agent on the SIT sample and stop adding research.

---

## Part 2. Sceptical research reviewer: what is still missing or wrong after the audits

Each finding has an ID (R-nn), the evidence, and why it matters for the "research grade" bar. Items already in `research_audit.md` §6 are not repeated except where something there is still not done or is incomplete in a way that matters.

### 2.1 Things no agent was asked to do

**R-01. The SIT document has no real answer key.** The only key for the document that matters most (the demo artefact family) is the "illustrative" key in `research/grading/worked_examples.md` §6 (K1-K10, T1-T6, N1-N3). It was written by the same model family as the agent, says it is not exhaustive, is in the grader's YAML format rather than `spec/answer_key.schema.json`, has no `core_insight`, no `approved_decisions[]` (although the document has a Confirmed Decisions section), and rests on the unverified PDPA statements (audit U9). It was never reviewed by a human. Consequences: (a) Real-dev has no quantitative signal at all, so the participant cannot say how well the agent does on the one document family SIT will use; (b) the K-items are what a Claude reviewer finds, so agreement between the Claude agent and this key is partly self-agreement (R-14). **Needed:** the user writes an independent SIT key first (without reading K1-K10 again; about 3-4 h for 30 pages), then both keys are converted to the canonical schema and compared. The overlap gives a capture-recapture estimate of what both miss, and the human-only items measure what the model family does not see.

**R-02. Human labelling has demands but no protocol and no calendar.** `research_audit.md` §4.6 sizes a one-person plan (about 20-25 h) and action 16 says "schedule it". Missing: (a) a written codebook (what counts as a match, as grounded, as supported, with worked edge cases); (b) the labelling tool (a CSV or HTML sheet with blinding and shuffling done by script); (c) dates. The intra-rater κ needs a re-label "after a gap of at least 7 days", which must fit before the deadline and after the matcher's pairs exist, which in turn need agent runs, which need agent code. That chain is the critical path for every validated number, and nobody has put dates on it. Action 8 asks for "a second reviewer" of the `core_insight`s; it does not say the second reviewer must be a human. If it is another Claude session, the check is circular (R-14).

**R-03. Sealing does not cover the copies of the S-heldout keys that already exist outside `eval/`.** `docs/SEALING.md` §1 seals `eval/blind/*`. But S-heldout key content is in plaintext in `research/audit/eval_data_audit.md` (Task 1.4-1.5, Task 5, Task 6), `research/audit/eval_fixes_applied.md` (item_a and item_b sections quote fields before and after), `spec/README.md` §2.4, §2.6, §2.7, and `spec/taxonomy.yaml` `legacy_mappings`. These copies carry no canary GUID, so neither the planned canary hook nor the canary scan will see them. They are read by every coding-assistant session that writes prompts and `criteria.yaml` `research_hints`, which is the most likely real leakage path (a "research hint" naming a platform limit that a held-out flaw depends on). Separately, `spec/validate_examples.py` line 495 globs `eval/*/*/answer_key.json`, which includes the S-heldout keys; that breaks SEALING.md §6 rule 1 ("not a script") every time it runs.

**R-04. No pre-registration exists, and the planned one cannot prove when it was written.** Action 11 covers writing `prereg.yaml`. A file in a repository the developer controls can be rewritten along with its history. For the claim "pre-registered" to mean anything to a third party, the hash must be timestamped outside the developer's control: email the SHA-256 to the SIT officer, or use a signed tag pushed to GitHub before the first S-heldout access, and keep a `prereg_deviations.md` log.

**R-05. Lab §1.5 "other AI agents or human review inputs" is designed for as P2.** `research/robustness/scenarios.md` INP-27 (another reviewer's change conflicts with the agent's v1 advice) and INP-31 (annotations) are P2. The brief states this as the demo scenario. Missing pieces:
- A provenance class for text that is inside the artefact but is review input, not design (a "review response" table, an appendix of AI-reviewer comments, tracked comments). Today it would be tagged `doc` and treated as design fact. Add `review_input` (or `doc_annotation`) to `spec/taxonomy.yaml` provenance.
- A behaviour rule: claims of the form "fixed per reviewer comment" are claims to verify against the v2 text, never accepted as evidence; reviewer recommendations embedded in the artefact are neither instructions nor authority.
- A fixture where the v2 change log or a "comments addressed" table claims fixes that were not made, or were made partly. None of the three synthetic v2s has this: every listed change is real and the log is neutral.
- A metric: claimed-fix verification accuracy.

**R-06. No plan for what the SIT v2 rehearsal fixture should contain.** Action 13 lists "a v2 of the SIT sample". It does not say who writes it or what it must exercise. If Claude writes the SIT v2 and Claude reviews it, the rehearsal measures self-consistency (R-14). It should be written by the user, simulate §1.5 literally (some K-items fixed, some partly fixed, one claimed but not fixed, one regression, one new section, an embedded reviewer-comment appendix, a cosmetic repagination), and have a gold diff written before the agent sees it.

**R-07. The demo document may sit in a domain no eval item covers.** The brief says "SIT AI platform component designs". The eval set covers payments, clinical monitoring, a research lakehouse with RAG, e-commerce returns and energy controls. The SIT sample is an AI memory platform. The likeliest next SIT document is another AI-platform component (for example an LLM gateway, guardrail or policy service, agent orchestration, evaluation or observability service). Only one item (lakehouse RAG) is near it, and it is S-dev. Nothing measures behaviour on LLM-serving designs, where refusal risk (audit U6) and the model's own self-knowledge (reviewing designs that use Claude-like models) both apply. Add one rehearsal-pool document in this family, human-planted or at least human-reviewed. It is not a scored item; it protects the demo.

**R-08. Latency: the all-Opus, high-effort plan probably does not fit 540 s, and nobody has done the arithmetic.** Budget planning figure: 20 calls and about 20K output tokens per run (`docs/BUDGET.md` §1); heavy case 60K. Opus output speed is UNVERIFIED (models note §2). At an assumed 50-80 tokens/s, 20K tokens is 250-400 s of generation, plus time to first token on a 78K-token prefix for 20 calls (roughly 40-80 s), plus up to 30 tool calls (roughly 90-240 s if sequential), plus any cold start not hidden by ingest. That is about 380-870 s against a 540 s deadline; the heavy case needs 750-1,200 s for generation alone. The runbook gives assess, refine and verify 90 s together (§5, 6:30-8:00) at effort `high`; 15-20 structured findings at about 400 tokens each is 6-8K visible tokens, i.e. 75-160 s before any thinking. Also: `max_tokens: 64000` on a single call means one runaway high-effort call can consume the whole slot; the per-call cap must be derived from remaining time; and "report guaranteed by T−60 s" holds only if the fallback report is rendered from structured findings with no LLM call (config sets `report: high`, implying an LLM report stage). **Needed before anything else is tuned:** time each stage on the SIT sample in the first laptop session; set effort per stage to hit p95 ≤ 7 min; parallelise assess by section if needed; make verify mostly code.

**R-09. Delta mode can declare findings "resolved" because of sampling noise.** Two runs of the same agent on the same document will differ (no seed, no temperature; `docs/REPRODUCIBILITY.md` §1). If the v2 run simply does not re-raise a v1 finding on a section whose text did not change, the delta report will say "resolved", which an evaluator will catch live ("section 12 is identical in both versions"). The metrics cover the opposite error (stale-finding rate, `metrics.md` §8) but not this one. **Needed:** a code-computed section-level text diff between `doc.pages.txt` of v1 and v2; a rule that a prior finding anchored to unchanged text keeps its status unless new evidence is cited; and a metric, the **false-resolution rate** (prior findings on unchanged text marked resolved / prior findings on unchanged text). This also covers the case where the frozen v1 review was produced by an earlier agent version.

**R-10. Confidentiality and licence questions to settle with SIT.**
- The three synthetic items state that they "follow the structure and register of the SIT Memory Platform Detailed Design", an SIT Internal, all-rights-reserved document. They are derivative works. Fine inside a private repo submitted to SIT; ADR-005 option 3 (a later public mirror) would need SIT's permission.
- ADR-003 branch A sends the SIT document to a second provider (OpenAI or Google) as grader input, and the human plan may give it to a peer rater. Both send SIT Internal material to third parties. Ask SIT before doing either.
- There is no `LICENSE` and no data statement. The eval keys and audits quote vendor documentation verbatim (from the awsdocs and MicrosoftDocs GitHub mirrors); check those repositories' licences and attribution terms before any redistribution. A short datasheet for `eval/` (provenance, generator model, intended use, licence, canary, known defects) is the research-grade minimum.
- Lab §5.1 requires the lab-session outputs in the submission, but the session may be after the submission deadline. Ask whether post-deadline commits are accepted or whether the outputs go by email (§5.2 allows email).

**R-11. Ethics and consent for raters.** Low risk, but unstated. If a peer rates reviews (audit §4.6 step 5): a one-paragraph rater statement (what they rate, time required, that their labels and agreement figures may appear in the submission, whether they are named, that they saw SIT material only with SIT's agreement). If only the developer rates: the L34 disclosure, plus how blinding was actually done.

**R-12. Verification covers finding anchors only, not the rest of the report.** ADR-007 checks each finding's quotes. The intent summary, the verdict, the executive summary and the delta narrative are free prose that can name a requirement ID, a number or a quote that is not in the document. That is the most likely "finding that quotes text not in the document" in front of an evaluator. Extend verify to every quoted string, requirement or section ID and numeral that the report attributes to the document, anywhere in the report.

**R-13. Browser automation is enabled by default in the demo config while its isolation is unknown.** The brief says the browser server has "one persistent Chromium session per server", shared by every participant using the shared key. `config/tools.yaml` (runbook §4.1 line 12) enables it. Until the probe shows per-client isolation, turn it off by default: another participant's navigation could change what the agent sees, which is a reproducibility and integrity problem, not only a robustness one.

### 2.2 Circularity: same model family everywhere

The same model family (very probably; audit U11 is still unrecorded) wrote the five eval documents and keys, verified the keys (`eval_data_audit.md`), edited the keys (`eval_fixes_applied.md`), wrote the illustrative SIT key, wrote both audits and this review, will run the agent, and may grade it (ADR-003 branch B).

| Where it bites | Effect | Control that exists | Control still missing |
|---|---|---|---|
| Eval documents and keys | Flaws are the kind this family plants and therefore notices; recall is inflated in a way no held-out split from the same generator can detect | Plan for a commissioned blind set by a different family or a human (action 14) | A small **human-planted** set now: the user plants 5-8 flaws by hand into a real public design document (an open RFC or ADR set), with a key written before any run. About 3-4 h. It is the only non-LLM flaw distribution the project would have, and it is enough to report "recall on human-planted flaws" with an honest CI |
| Key verification and fixes | Legal and standards "truths" were corrected by the same family from secondary sources (the proxy blocked primary legal and standards sites). A wrong truth trains the matcher and grader to reward the error | Source-quality labels in `eval_data_audit.md` | A **human spot-check** from the laptop of a random 8 of the ~35 fact verdicts against primary sources, recorded with the source URL and date |
| Illustrative SIT key | Agent-key agreement is self-agreement | None | R-01 (independent human key, then compare) |
| `core_insight` derivation (action 8) | If Claude writes and Claude reviews, a lenient insight lets anything match | "Second reviewer" | State that the second reviewer is the human; record who signed off |
| Grader R_base for V-tests | V9 (style) partly tests the author's own style | Audit §4.5 says write it by hand | Nothing new; just do it |
| The audits themselves | Correlated blind spots: neither audit raised the latency arithmetic (R-08), false resolution in delta mode (R-09), derivative-work licensing (R-10) or the leaked copies (R-03) | None | A 30-minute **human red-team read** of `README.md` and `docs/` by someone who did not write them, asking "what would embarrass us live?" Record the questions; they are the best walkthrough rehearsal available |

### 2.3 Over-engineering: is the plan finishable?

**No, not as written, before a deadline that is probably weeks away.** The brief is dated September 2026; today is 2026-10-02; the deadline is still unknown (audit M12). The plan implies: about 430 agent runs (about 60-70 h of laptop wall time, `docs/BUDGET.md` §4); 20-25 h of human labelling with a 7-day re-label gap; a local open-weight judge that must pass validation; sealing tooling with `age`, hooks and canaries; a commissioned blind set, OOD and sound-control documents; seven new docs; 166 robustness scenarios (81 P0); and an agent with eleven architectural subsystems. None of the agent exists. The research is excellent and the risk is that it consumes the time needed to build the thing it evaluates.

**Minimum research-grade core** (assumes about three weeks; if less, cut the "Keep if time" rows):

| Area | Keep (core) | Keep if time | Defer (state as future work in `LIMITATIONS.md`) |
|---|---|---|---|
| Agent | Ingest (pdfplumber text + native PDF); understand with decision registry; plan; research loop over 2 MCP servers with timeouts and doc-only fallback; ledger; assess; one refine pass; code verify (anchors, ledger, completeness, whole-report check R-12); template report; delta mode with text diff (R-09); progress line; run directory with manifest, `llm.jsonl`, `tools.jsonl` | `explain <id>`; checkpoint and resume; LLM replay for the offline fallback | Coverage command (render as a report table instead); personas beyond one; fault-injection framework beyond the 5 runbook drills; cross-vendor adapter |
| Config for live changes | `agent.yaml`, `stop_rules.yaml`, `tools.yaml`, `criteria.yaml`, report template, severity threshold | URL allow-list mode; plan approval pause | Line-number pinning test (keep the runbook's line table, drop the test) |
| Data | 3 S-dev items (v1 and v2); 2 S-heldout items, used once; human-authored SIT key (R-01); human-written SIT v2 (R-06) | Human-planted mini-set (§2.2); 1 sound control document; 1 AI-platform rehearsal document (R-07) | Commissioned blind set; OOD; paraphrase and reorder probes; template-tell probe; capture-recapture on synthetic items |
| Metrics | Recall, adjudicated precision, SWR, CDR, hallucinated-finding rate (code-checked), fabricated-citation rate, v2 metrics plus false-resolution rate, cost and wall time | Critical recall; stability (Jaccard over k) | nDCG, MRR, ECE/Brier/AUROC, research yield and overrun |
| Comparisons | FULL vs B0, k = 3, paired, two-level cluster bootstrap CIs, MDE stated; A5 (tools off) for the honesty check | B0-$ (cost-matched) | A1-A4e ablations; Holm/BH machinery beyond one family |
| Instruments | Matcher on Claude, disclosed as same-family, validated against about 100 user-labelled pairs; code-checked grounding; grader V1, V4, V10 only, reported as supporting | Intra-rater re-label of 40 pairs | Local open-weight judges; cross-family grader; full V1-V13; ≥ 100 doubly graded reviews |
| Governance | `prereg.yaml` timestamped externally (R-04); `.gitignore`, `.env.example`, gitleaks; S-heldout moved out of the repo into one encrypted archive held by the user, plus the derived copies (R-03) | Access log | `seal.py`/`unseal.py` tooling, canary hooks, query filter with salted n-grams |
| Robustness | The 20-item minimum gate (robustness §4.2), with INF-01, INF-24, LLM-06, BEH-24, INP-22 and DEMO-15 first | Remaining P0 items with existing fixtures | P1 and P2 scenarios |
| Docs | The seven §5.3 docs, each 1-2 pages, plus `README.md` install/config/run | Slides | Long-form research consolidation |

Rough size of the core: about 90-100 agent runs (about $200-230 at the planning figure, 13-15 h of laptop time), about 8-10 h of labelling, 4-6 days of build, 1.5 days of docs, 1 day of rehearsal.

### 2.4 Things that would embarrass the participant live

| Risk | Status in the plan | Gap |
|---|---|---|
| Run overruns the slot or stops at the deadline with a partial report | Deadline-aware planner, 540 s | Arithmetic suggests the planned effort settings overrun (R-08); no measured timings |
| Silence during a long model call (not only during cold start) | DEMO-15, P1 | Raise to P0 and include a heartbeat during streaming model calls (tokens so far, stage), not only during tool waits |
| A refusal mid-run | Runbook drill 4; LLM-06 | Covered; rehearse on the AI-platform rehearsal document (R-07), where it is most likely |
| A quote or ID in the summary that is not in the document | Findings only | R-12 |
| Delta report says "resolved" for an unchanged section | Not covered | R-09 |
| Agent accepts an embedded "fixed per review" claim | INP-27 P2 | R-05 |
| `--previous` points at the wrong baseline (SIT hands over v2 of a different component, or a v1 and v2 pair the agent has never seen) | Runbook covers "new design" and "updated SIT sample" only | Add a third path: `--previous-pdf v1.pdf` that reviews v1 quickly or diffs text only, and say so in the report |
| Shared browser session shows another participant's page | U2 unverified | R-13 |
| A requested live change the runbook did not prepare (severity filter, output table, plan approval, allow-list, new tool) | §1.8 above | Prepare at least the severity filter and the output-table template; have a scripted answer for plan approval |
| A secret on screen | Runbook says never `cat .env` | The key prefix in `scenarios.md` OPS-02 would appear in any grep on the projector |
| "What results do you have?" | None yet | Even one FULL vs B0 table on S-dev with k = 3 and CIs changes this answer completely |

### 2.5 Smaller corrections

- `research/methodology/README.md` §7.1 still lists `temperature`, `top_p` and `seed` in the manifest and A4 as "different backbone model". `docs/REPRODUCIBILITY.md` and ADR-002 supersede these (audit C15, C24), but the methodology note was not amended, and it is the file an evaluator is most likely to read on metrics.
- `research/grading/README.md` §5 still specifies `pdftotext -layout` for grader input and §6.2 "temperature ≥ 0.3"; both conflict with ADR-006 and ADR-002.
- `docs/BUDGET.md` relies on cache reads across stages that use different effort levels. Whether changing `effort` between calls invalidates the cached message prefix is UNVERIFIED here; check it with the `claude-api` skill, because the cost per run and the latency both depend on it.
- `research/robustness/scenarios.md` DEMO-05 still says "Rehearse on 3 docs from `eval/blind`"; ADR-004 forbids this. The scenario text was not updated.

---

## Part 3. New actions (not already in `research_audit.md` §6)

Checked against the 24 actions in `research_audit.md` §6. Where an action extends an existing one, the existing number is given. Effort: S under half a day, M 0.5-2 days, L over 2 days.

### P0: this week, before more research

| # | Action | Extends | Effort |
|---|---|---|---|
| N1 | Get the submission deadline, demo date and slot length from SIT, and write a **dated schedule** with one milestone first: a working thin-slice agent on the SIT sample. Adopt the minimum core in §2.3 and move the rest to `LIMITATIONS.md` as future work | #17 (adds dates and scope cut) | S |
| N2 | **Build the thin slice now** (ingest → understand → plan → research → assess → verify → report on the SIT sample) before any further research notes or eval tooling | none | M |
| N3 | **Measure latency per stage** on the SIT sample in the first laptop session; set per-stage effort so p95 ≤ 7 min; cap each call's output from the remaining time; make the deadline fallback report LLM-free (R-08) | U4 (adds the budget arithmetic and the fallback) | S |
| N4 | **Add `.gitignore` and `.env.example`** before running the probe (`.env`, `scripts/.venv/`, `mcp_probe_results.json`, `runs/`, `inbox/`, `outputs/` staging) | none | S |
| N5 | **Extend sealing to the derived copies** of S-heldout key content (`eval_data_audit.md`, `eval_fixes_applied.md`, `spec/README.md` §2.4/2.6/2.7, `taxonomy.yaml` legacy blind tables), and make `spec/validate_examples.py` skip `eval/blind/` (R-03). Run the distinctive-term grep on `prompts/` and `config/` from the first commit, not only before held-out runs | #7 | S |
| N6 | **Ask SIT** about: derivative use of the Memory Platform template in eval items; sending SIT material to a second LLM provider or a peer rater; committing lab-session outputs after the deadline (R-10) | none | S |

### P1: during the build

| # | Action | Extends | Effort |
|---|---|---|---|
| N7 | **Human-authored SIT key**, written independently of K1-K10, then both converted to the canonical schema with `approved_decisions[]`; report the human-only and model-only items (R-01) | none | M |
| N8 | **Delta-mode integrity:** section-level text diff in code; prior findings on unchanged text keep their status unless new evidence is cited; add the false-resolution rate to `metrics.md` §8; add a `--previous-pdf` path (R-09, §2.4) | INP-22 | M |
| N9 | **Lab §1.5 review inputs:** add a `review_input` provenance class; rule that claimed fixes are verified against the text; raise INP-27 and INP-31 to P1; a fixture with claimed-but-not-made fixes; claimed-fix verification accuracy metric (R-05) | none | M |
| N10 | **Human-written SIT v2 fixture** to the R-06 specification, with a gold diff written before any run | #13 (adds author and content) | M |
| N11 | **Whole-report verification:** every quote, requirement or section ID and numeral attributed to the document, anywhere in the report, resolves in `doc.pages.txt` (R-12) | ADR-007 | S |
| N12 | **Circularity controls:** a human-planted mini-set of 5-8 flaws in a real public design document; a human spot-check of 8 audit fact verdicts against primary sources; state in action #8 that the `core_insight` second reviewer is the human (§2.2) | #8, #14 | M |
| N13 | **Labelling codebook, tool and calendar:** written match / grounded / supported definitions with edge cases; a shuffled, blinded CSV or HTML sheet; dates that fit the 7-day re-label gap before the deadline (R-02) | #16 | S |
| N14 | **Timestamp `prereg.yaml` externally** (hash emailed to the SIT officer or a signed tag pushed before the first S-heldout access) and keep `prereg_deviations.md` (R-04) | #11 | S |
| N15 | **Default the browser server off** in `config/tools.yaml` until the probe shows per-client isolation (R-13) | U2 | S |
| N16 | **Prepare the unrehearsed live changes:** severity threshold, risk-register output template, URL allow-list mode, a plan-approval pause (or a scripted answer), and the steps to add one new tool (§1.8) | #20 | M |
| N17 | **One AI-platform-family rehearsal document** (LLM gateway, guardrails or orchestration), human-planted or human-reviewed; use it for refusal and latency rehearsals (R-07) | #13 | M |

### P2: before submission

| # | Action | Extends | Effort |
|---|---|---|---|
| N18 | **Fix the README:** remove "to come" and the false blind claim, add install/config/run and Requirements sections, a reading order, and a status table of the audit actions (done / open / deferred) | #22 | S |
| N19 | **Rename colliding identifiers** (gate G*, loophole G*, grounding G*; rubric D*, spec deviation D*; conflict C*, key edit C*) to distinct prefixes | none | S |
| N20 | **Licence and datasheet:** `LICENSE` for the code; a datasheet for `eval/` (provenance, generator model, intended use, licence, canary, known defects); check the licence terms of quoted vendor docs (R-10) | none | S |
| N21 | **Rater statement** (ethics and consent, R-11) and the L34 disclosure in `LIMITATIONS.md` | #16 | S |
| N22 | **Amend superseded text** in `methodology/README.md` §7.1 and §4 A4, `grading/README.md` §5 and §6.2, and `scenarios.md` DEMO-05 (§2.5) | C15, C19, C24 | S |
| N23 | **Verify cache behaviour across per-stage effort changes** and re-run `cost_model.py` if the cache is invalidated (§2.5) | U3 | S |
| N24 | **30-minute human red-team read** of `README.md` and `docs/` by someone who did not write them; keep their questions as walkthrough rehearsal (§2.2) | none | S |

**Counts: 6 P0, 11 P1, 7 P2 (24 new actions).** If only three are done, do N2, N3 and N7: a working agent, a run that fits the slot, and one key for the SIT document that a human wrote.
