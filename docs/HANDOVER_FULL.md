# Full handover from the coordinating session

Written by the coordinator (Claude Fable 5.1 acting as delegator) on 2026-10-02 at the end of the research and design phase. `docs/HANDOFF.md` is the short version; this is the explicit one.

## 1. What the user asked for, in order

1. An overview of the two SIT documents and what the lab expects.
2. A framework and model recommendation with reasons, verified by agents.
3. Research into Kaggle competitions that fit, documented for reuse.
4. Synthetic "fake" evaluation data for stress testing, plus an unbiased set authored by agents with no project context.
5. A research-grade evaluation: explicit metrics, every scenario stress-tested, every framework choice justified on several levels (overfitting, tool-failure robustness, etc.), a "lecturer that grades the work", and verification agents to find loopholes.
6. The coordinator to act purely as delegator and keep its own context clean.
7. After the first batch launched: switch all subagents from Fable to Opus on cost grounds.
8. All agent calls on Opus 5.5 (no Sonnet sub-tasks); grader left to coordinator judgement; repo is private; ablation choice left to coordinator.
9. A probe of the SIT MCP servers, run via a Remote Control session on the user's Mac.
10. A full handover and a verbatim transcript, because the user is switching to another account with more credit.

## 2. What was produced (36 subagents, 32 commits)

### Phase 1: research (6 notes, all under `research/`)

| Note | Headline result | Caveats recorded in the note |
|---|---|---|
| `frameworks/` | Custom state-machine loop on the Anthropic Python SDK + direct MCP client. Weighted matrix: custom 92, LangGraph 80, PydanticAI 77, OpenAI Agents 74, LangChain 67, Claude Agent SDK 58, CrewAI 51, smolagents 51. Four corrections: direct MCP client (the server-side connector can't send a custom header), own 40-line tool loop, explicit SDK retries/timeout, no temperature on current models. | SIT auth header unverified; several frameworks broken on fresh install due to mcp 1.x/2.x split. |
| `models/` | Agent: Opus 5.5 (user later made it all-Opus). Grader: different provider at high effort; same-family bias 3-8 pp in 15 papers. Per-run ~$2.18 all-Opus with caching. | Non-Anthropic prices unverified (docs sites blocked). |
| `kaggle/` | No competition ever targeted design review; value is techniques: score both answer orders, length-bias control, QWK for ordinal rubrics, RevUtil dataset labels map to lab's issue/rationale/evidence/benefit. | kaggle.com blocked; facts from GitHub mirrors and snippets. |
| `methodology/` | Metrics (P/R/F1 per category, severity-weighted recall, nDCG, hallucination rate, citation faithfulness, correct-decline rate, calibration, kappa), splits, baselines B0/B0-$/B-gen, ablations A1-A5, bootstrap stats, 40-item loophole checklist, results template. | Thresholds are proposed defaults; power is low at 5 docs. |
| `grading/` | 10-dimension 0-4 rubric, every criterion quoted to a lab page; full grader prompt + JSON schema; 13 grader validation tests; 3 worked examples on the SIT doc; demo-day checklist. | Found a real SIT-doc issue: Gateway Check 4 calls the admin plane in-request, contradicting NFR-4. |
| `robustness/` | 166 scenarios (81 P0), 11 invariants, 3 test levels (fake / recorded / live), fault-injection via YAML schedule, 11 architecture needs. | Found: shared key printed in brief; browser MCP shares one Chromium across participants; DDG rate-limits inside HTTP 200. |

### Phase 2: evaluation data (`eval/`)

- 3 synthetic items (payments orchestration, clinical remote patient monitoring, research lakehouse): v1 + v2 markdown and PDFs, 14 planted flaws each in fixed category/severity counts, 5 sound-section traps, v2 fixes 6 and introduces 1 regression.
- 2 "blind" items (e-commerce returns; battery storage control), 14 defects each, authored without project context. Later reclassified as sealed held-out, not blind, because the authors were given a domain exclusion list and the same model family.
- `eval/build_pdfs.py` rebuilds PDFs reproducibly.

### Phase 3: audits (`research/audit/`)

- `research_audit.md`: 32 cross-note conflicts, 11 load-bearing unverified claims, blind set not blind, synthetic set template-like, 24 actions (7 P0).
- `eval_data_audit.md`: ~35 external facts verified against vendor-owned sources; 2 key entries partially wrong (UK refund timing; a GDPR sound-section trap); 0 leakage; all 42 v2 statuses correct.

### Phase 4: P0 resolution

- `spec/`: taxonomy.yaml, finding.schema.json (Finding + Review envelope), answer_key.schema.json, validator with 28 adversarial cases, converter producing `answer_key.canonical.json` for all 73 flaws.
- Answer-key corrections applied (52 field edits) and re-verified.
- `docs/`: DECISIONS.md (ADR-001..009), USER_DECISIONS.md, REPRODUCIBILITY.md, DEMO_DAY_RUNBOOK.md, DOCUMENTATION_MAP.md, SEALING.md, BUDGET.md, HANDOFF.md.
- `scripts/probe_mcp_servers.py` (+ README): self-tested against a local MCP server; the Mac must run it.
- `eval/prereg.yaml` (draft, `frozen: false`), `eval/EVAL_PLAN.md` (Tier A 132 runs), `eval/human_labelling_protocol.md`.
- `agent/` skeleton with frozen interfaces (see `agent/README.md`).

### Phase 5: verification (one verifier per deliverable)

`verify_spec.md`, `verify_eval.md`, `verify_docs.md`, `reconciliation_log.md`, `fresh_eyes.md`. Key outcomes: 12 schema holes closed; taxonomy YAML bug (`yes`/`no` keys parsed as booleans) fixed; eval-doc IDs leaking into schema examples removed; budget arithmetic corrected (442 runs full / 132 Tier A); ADR-009 checkpointing added; fresh-eyes found the MCP key prefix in `scenarios.md` (redacted; remains in git history of this private branch) and no `.gitignore` (added).

## 3. Decisions in force

See `docs/DECISIONS.md` and `docs/USER_DECISIONS.md`. Summary: Python; custom loop on Anthropic SDK; direct MCP client; Opus 5.5 for every agent call, high effort allowed, one effort level per conversation (switching invalidates cache, ~$1.20/run); native PDF document block + pdfplumber text; anchor rule 8 tokens / fuzzy 0.90 / 3 locations / page ±1; on-disk checkpoints; no silent fallbacks; grader Opus 5.5 high + different-provider judge if a key exists; A4 = Sonnet-as-agent ablation (Tier B), A4b = effort sweep; repo private; keys to be sealed with `age`.

## 4. Money

- Tier A core: 132 runs, ~$240 agent API spend, ~$565 all-in Anthropic-only or ~$640 with a second-provider grader (30% margin included). The ~$75 difference is the only money that would go to OpenAI or Google.
- Full programme (reference only): 442 runs, $1,150-1,800.
- Per-run ~$2.18 is UNVERIFIED until `count_tokens` is run on the real document on the laptop.
- API spend bills to the API key the agent uses, not to the Claude Code account. Claude Code subscription credit does not pay for API calls.

## 5. Lessons learned as delegator

1. **Set the model explicitly on every subagent.** Subagents inherit the parent model; the first 11 ran on Fable until the user noticed. Five minutes of work was discarded.
2. **Give independent authors identical constraints and you get a template.** All three synthetic items have 14 flaws in identical category counts and the SIT section order. Vary counts, structures and section orders next time, or let authors choose within ranges.
3. **A domain exclusion list leaks the design.** Telling the "blind" authors which domains to avoid told them what the other set covered. Truly blind items need a different author model, no exclusion list, and the agent frozen first.
4. **Independent notes contradict each other on basics.** Six authors produced six answer-key formats and four severity scales. Write the shared taxonomy and schema FIRST, then fan out.
5. **Safety classifiers can stop a long generation mid-file.** A water-utility SCADA design with planted defects was cut off. Ask authors to write in 1,500-2,500 word appends and to prefer business-software domains.
6. **"Checkable against vendor docs" flaws written from memory must be fact-checked** before they enter a key. The audit found the figures held, but two legal statements were partially wrong.
7. **Sweep the whole tree for secrets after every batch.** The brief prints the MCP key; a robustness author copied its prefix into a test description.
8. **Commit after every agent lands.** The container is ephemeral and a stop hook demanded it anyway; it also made the per-agent provenance clear in git history.
9. **Verifiers need write access to fix small things, with a mandatory edit log.** Report-only verifiers would have added a third round-trip.
10. **The research-grade bar is expensive.** The honest full programme is ~$1,800; the user's reaction ("1.2k dollars? for real?") shows the scoped Tier A should have been produced alongside the full figure from the start.
11. **The sandbox cannot reach kaggle.com, arXiv, OpenAI/Google docs, legislation sites, or the SIT MCP hosts.** Agents coped via GitHub mirrors and search snippets, and marked sources; the probe and all live runs must happen on the laptop.
12. **Human work is on the critical path and no agent can do it:** the SIT document answer key, the core_insight sign-offs, and grading calibration.

## 6. What is next, in order

1. Commit the agent skeleton when it lands (if this session ended before that, re-run the skeleton brief; it is in `docs/transcripts/conversation.md`).
2. Owner: run the MCP probe on the Mac; report API keys held; approve Tier A budget; write the SIT answer key before any agent run on that document.
3. Three parallel implementers on Opus with disjoint module ownership per `agent/README.md`: (a) LLM gateway + PDF ingest, (b) tool gateway with MCP/fault-injection/record-replay, (c) phases + orchestrator + report + CLI. Then a verifier pass.
4. Eval harness: matcher + metrics + grader, driven by `spec/` and `eval/prereg.yaml`.
5. Thin-slice run on one synthetic item with recorded fixtures in the cloud, then a live run on the laptop to measure latency against the 10-minute demo budget (fresh-eyes estimate: 380-870 s at high effort; likely needs trimming).
6. Robustness P0 suite (81 scenarios), then freeze prompts, freeze `prereg.yaml`, run Tier A.
7. Documentation per `docs/DOCUMENTATION_MAP.md`; demo rehearsal per `docs/DEMO_DAY_RUNBOOK.md`; grant the two SIT GitHub IDs collaborator access before the deadline.

## 7. How to resume in a new session

```
Read docs/HANDOFF.md and docs/HANDOVER_FULL.md, then docs/transcripts/README.md.
Continue from HANDOVER_FULL.md section 6. Spawn all subagents on Opus. Commit and push after each one lands.
```
