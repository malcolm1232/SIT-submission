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

### Phase 6 (second session, 2026-10-02): the agent is built

Branch `claude/great-hopper-hbx7h0`. Six Opus subagents, reports verbatim in `docs/transcripts/session2_coordinator.md`:
ClaudeCodeGateway implementer; backend verifier (7 defects, live-checked on Haiku); workstreams A (AnthropicGateway, llm_facing_schema, understand/plan/assess/refine, prompts), B (MCP/policy/fault tool gateways, research loop, sources, preflight) and C (ingest/verify/report, renderer, explain, manifest, run/resume, selftest, CLI) in parallel with disjoint file ownership; integration verifier (seams, e2e on a synthetic PDF, 37 adversarial invariant tests, ~12 defects). Result: `ruff` clean, `pytest` 444 passed 0 skipped, `sit-review selftest` passes offline in under 1 s. Then one live end-to-end run through the Claude Code backend (§8).

## 3. Decisions in force

See `docs/DECISIONS.md` and `docs/USER_DECISIONS.md`. Summary: Python; custom loop on Anthropic SDK; direct MCP client; Opus 5.5 for every agent call, high effort allowed, one effort level per conversation (switching invalidates cache, ~$1.20/run); native PDF document block + pdfplumber text; anchor rule 8 tokens / fuzzy 0.90 / 3 locations / page ±1; on-disk checkpoints; no silent fallbacks; grader Opus 5.5 high + different-provider judge if a key exists; A4 = Sonnet-as-agent ablation (Tier B), A4b = effort sweep; repo private; keys to be sealed with `age`.

## 4. Money

- **Two separate pools.** Claude Code cloud sessions (the coordinator and every subagent) bill to the account's *cloud session credits*; this session consumed about $214 of a $250 allowance (screenshot 2026-10-02: $36 left, credits expire 5 Nov). The agent we are building calls the Claude API through the `anthropic` SDK and needs `ANTHROPIC_API_KEY`; it bills to that key's Console API credit, NOT to cloud session credits. Verified: the SDK cannot use the sandbox session's own credentials (`Could not resolve authentication method`).

- Tier A core: 132 runs, ~$240 agent API spend, ~$565 all-in Anthropic-only or ~$640 with a second-provider grader (30% margin included). The ~$75 difference is the only money that would go to OpenAI or Google.
- Full programme (reference only): 442 runs, $1,150-1,800.
- Per-run ~$2.18 was the estimate. MEASURED on 2026-10-02 (§8): one doc-only run on a 21-page synthetic PDF, Opus 5.5 at `high` through the Claude Code backend, cost $3.68 by the CLI's own estimate for the five calls that completed, but four `assess` attempts were killed by the 600 s timeout after generating output and are not in that figure; the true spend is likely $8-10. With the timeout fixed, expect about $3.5-4 per doc-only run and more with research. Tier A arithmetic in `docs/BUDGET.md` should be redone from this number.
- ADR-010 (accepted): agent model calls bill to the Claude Code login, so in a cloud session they draw on cloud credits and on a laptop on the subscription's usage limits, not on Console API credit. Whether a nested `claude -p` inside a cloud session really bills to cloud credits is still UNVERIFIED by the meter.
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
13. **Probe the real tool contract yourself before writing the brief.** Thirty cents of Haiku calls established the `claude -p` flags, the JSON result shape and the argv limit; the implementer then built against facts, and the verifier found the remaining seven defects by running the CLI live, not by reading. `--bare` broke auth, `--resume` duplicated turns on retry, and costs were cumulative: none of that was in any doc.
14. **Parallel implementers on one frozen skeleton work if file ownership is disjoint and shared files are Edit-only.** Three workstreams plus a verifier ran concurrently with no clobbering. The costs were a shared `tests/test_pending.py` and `PROMPTS.lock` that nobody could own (left to the integration verifier) and a stop hook that forces WIP commits of half-finished trees.
15. **Every implementer's report ends with "writes beyond my list" and "for the other workstream"; feed those verbatim into the integration verifier's brief.** All seven seams it was given needed a fix or a test, and it found five more defects nobody had flagged.
16. **Timeouts and deadlines sized for the API do not transfer to the CLI backend.** `assess` at high effort emitted 63k output tokens and took about 520 s; a 600 s per-attempt timeout killed it four times and the retries re-sent the whole document each time (49 minutes, unrecorded spend). Measure one live run before trusting any budget number.

## 6. What is next, in order

1. Owner: read §8 and decide the demo shape. At `high` effort the five model calls alone take about 16 minutes without research, so the 10-minute demo budget needs one of: `medium` effort for the demo (USER_DECISIONS #1 allows `high` but asks spend to be justified), a trimmed assess prompt, or a pre-recorded run replayed with `--replay`. Also decide `deadline_seconds` (540 is unreachable with this backend at `high`).
2. Owner tasks unchanged: run the MCP probe on the Mac; write the SIT answer key before any run on that PDF; approve the Tier A budget once redone from the measured cost; fund OpenAI or Google if the second-provider judge is wanted.
3. Eval harness (next implementer): matcher + metrics from `research/methodology/metrics.md`, grader from `research/grading/grader_prompt.md`, driven by `spec/` and `eval/prereg.yaml`. First job: score `docs/live_runs/live_cc_opus_payments_v1/report.json` against `eval/synthetic/payments_orchestration/answer_key.canonical.json` (eyeball in §8: 13 of 14 planted v1 flaws found plus one partial, six unplanted findings to classify, severities under-rated on three criticals).
4. Robustness P0 suite as runnable scenarios (the fault machinery, 26 fault tests and the runbook drills exist; the 81 scenario files under `tests/robustness/faults/` do not).
5. A live run WITH tools from the laptop (MCP hosts are unreachable from the sandbox): this exercises the envelope tool loop on Opus, which has only been verified on Haiku, and the real MCP transport.
6. Freeze prompts and `prereg.yaml`, run Tier A; documentation per `docs/DOCUMENTATION_MAP.md`; demo rehearsal per `docs/DEMO_DAY_RUNBOOK.md`; collaborator access for the two SIT GitHub IDs.

## 7. How to resume in a new session

```
Read docs/HANDOFF.md and docs/HANDOVER_FULL.md, then docs/transcripts/README.md.
Continue from HANDOVER_FULL.md section 6 (read section 8 first). Spawn all subagents on Opus with the brief pattern in docs/transcripts/session2_coordinator.md. Verify every deliverable with a separate subagent. Commit and push after each one lands.
```

## 8. First live run through the Claude Code backend (2026-10-02)

Command, from this sandbox, Opus 5.5, every phase at `high`, no tools (SIT MCP hosts unreachable here):

```
sit-review run eval/synthetic/payments_orchestration/design_v1.pdf --no-tools --deadline 2400 --run-id live_cc_opus_payments_v1
```

Artefacts: `docs/live_runs/live_cc_opus_payments_v1/` (report.md, report.json, manifest.json, progress.log, effective_config.json). Exit 0, outcome `completed_degraded` (text-only input, no research), verdict `fit_with_conditions` at confidence 0.68, 21 findings (1 critical, 11 high, 8 medium, 1 low) plus 5 sound areas, 12 unresolved items, every finding anchored (one anchor-repair call, 33 s).

| Phase | Wall | Output tokens | Cost (CLI estimate) |
|---|---|---|---|
| ingest | 2 s | n/a | 0 |
| understand | 158 s | 22,227 | $0.68 |
| plan | 158 s | 17,003 (29 questions, 6 external) | $0.63 |
| research | 0 s (doc-only, disclosed) | 0 | 0 |
| assess | 2,933 s: four attempts killed at the 600 s timeout, fifth succeeded in ~520 s | 63,392 | $1.58 recorded; the four killed attempts are unrecorded |
| refine | skipped: the 2,400 s deadline had fired | 0 | 0 |
| verify | 33 s | 3,724 | $0.30 |
| report | 88 s | 9,918 | $0.49 |
| total | 3,372 s (56 min) | 116,264 | $3.68 recorded, likely $8-10 true |

Cache: the shared prefix was written on every phase (28-39k cache-creation tokens per call) and read only once (6k on the final assess attempt): forked CLI sessions per call plus a different first user turn per phase defeat the 5-minute cache. Worth a look before Tier A; a 1-hour TTL is not selectable through the CLI.

Quality, by eye against `answer_key.canonical.json` (not the matcher; the harness is not built): planted v1 flaws F01-F06, F08-F14 each map to one finding; F07 (Indonesia data residency) is covered only partially by FND-016. Six findings are not planted flaws (FND-007, 010, 013, 015, 019, 020) and need a human call on true positive versus over-reach. Severity: the agent rated three planted criticals (F06, F08, F10) as high. The `assess` output used 63k of the 64k `max_tokens`: one more finding and it would have truncated.

What this run changed: `config/agent.yaml llm.timeout_s` 600 → 1800. What it leaves open: the deadline and effort for the demo (§6 item 1), refine never ran, the envelope tool loop on Opus is still unexercised, and the money meter should be checked against the $3.68 figure to settle whether nested `claude -p` bills to cloud credits.

