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

17. **Freeze the shared interface yourself before fanning out.** Writing `sit_eval/judge.py`, the package skeleton and the CLI mount point (twenty minutes) let the matcher and grader workstreams run in parallel against one contract; the only seam defect was a lint autofix one of them ran over the other's folder.
18. **Give verifiers a small live budget on the cheapest model.** Both harness verifiers found defects only a real `claude -p` call shows (a root `$schema` key rejected outright; thinking tokens three times the estimate) for $0.24 and $0.32 on Haiku. Offline tests could not have caught either.
19. **A cost estimate is a hypothesis; a capped pilot is the measurement.** The dry run priced matcher calls at $0.05-0.15 and 20-60 s; the live pilot measured $0.06-0.11 and 6-17 s for pair and shortlist calls but $0.33 for whole-document adjudication calls. Run the cheapest faithful configuration once, with a hard cap, before any budget decision.
20. **Ask verifiers to mutation-test, not just re-run.** The robustness verifier found a scenario test that still passed with its main claim removed.

## 6. What is next, in order (superseded by §10 at the end of the third session)

Owner decisions first; each is written up with options in §9 and in the reports in
`docs/transcripts/session3_coordinator.md`.

1. **Matcher candidate rule (blocks the Tier A budget).** As written, metrics.md §2.3 and prereg score
   every finding that shares any listed section with a flaw. On the payments key that is 80 pairs and
   about $25-37 per scored run, i.e. thousands for Tier A. Choose: the shortlist bounds pairwise scoring
   (matches the arithmetic in `docs/BUDGET.md` §3; one-line text change), drop listing sections from
   overlap, approve `per_flaw_batch` (measured $6.89 per run without grounding judges), add Message
   Batches, or raise the budget. Then redo `docs/BUDGET.md` from the measured costs in §9.
2. **Demo shape and deadline** (unchanged from §8) together with robustness LLM-05: bound each model
   attempt by the remaining deadline, or keep the 1800 s timeout and set the deadline to match.
3. **Four more robustness policy calls:** NET-02 (fast exit when offline), INF-08 (fail fast when the MCP
   key is missing), LLM-10 (token estimate before large calls), OVF-07 (sample-derived hosts in
   `tools/sources.py`). Options and recommendations in the R verifier report.
4. **Owner tasks unchanged:** MCP probe on the Mac; SIT answer key before any run on that PDF; author
   `core_insight`, `anchor_quote`, `expected_disposition` and `approved_decisions` for the synthetic keys
   (every payments flaw has `scored_run_ready: false`, so no scored run is allowed yet, prereg LC12);
   fund OpenAI or Google if the second-provider judge is wanted.
5. **Text fixes before freeze** (no decision needed, collected from the verifiers): MM §2.3 step 4
   (PARTIAL against an unmatched flaw), MM §5.1 G1 "token-level" -> character-level, prereg LC9 / stop
   rule `eval/score.py` -> `sit-eval score`, prereg `matcher.prompt_sha256` and `grader.prompt_sha256`
   from the two lock files, GR §4.2 cumulative G3 rows, GR §5.3 counts instead of shares, spec/README
   grader projection drops `review_id`, `run_id` and `stop_reason.detail`.
6. **Build next:** the `--k`, `dra replay` and `dra coverage` commands; reject or implement `process:`
   entries in `--faults` (now silently ignored); a live run WITH tools from the laptop (envelope tool loop
   on Opus, real MCP transport) and the 28 laptop-only robustness rows.
7. Freeze prompts and `prereg.yaml`, run Tier A; documentation per `docs/DOCUMENTATION_MAP.md`; demo
   rehearsal per `docs/DEMO_DAY_RUNBOOK.md`; collaborator access for the two SIT GitHub IDs. One Fable
   fresh-eyes audit of the whole submission before Tier A is worth paying for.

## 7. How to resume in a new session

```
Read docs/HANDOFF.md, then docs/HANDOVER_FULL.md sections 10, 9 and 6 (in that order), then
docs/transcripts/session3_coordinator.md (the last three sections first). Work on branch
claude/happy-darwin-d0bl94. Continue from HANDOVER_FULL.md section 10 "Next steps", in order.
Spawn all subagents on Opus with the brief pattern in docs/transcripts/session2_coordinator.md and
session3_coordinator.md. Verify every deliverable with a separate subagent. Commit and push after each
one lands. Judgement calls go to the SIT FABLE session (session_01XFmYhcJBBHVd1QkUXyauBg) via the
claude-code-remote send_message tool; the owner has delegated decisions to it, but the answer-key
signature stays the owner's.
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


## 9. Third session: evaluation harness and robustness suite (2026-10-02)

Branch `claude/happy-darwin-d0bl94`. Coordinator started on Fable 5.1 and was switched by the owner to
Opus 5.5 before any build work; all six subagents ran on Opus 5.5. Every report is verbatim in
`docs/transcripts/session3_coordinator.md`; edit logs are under `research/audit/`
(`verify_grader_editlog.md`, `verify_eval_harness_editlog.md`, `robustness_suite_editlog.md`).

**Built and verified.**
- `harness/sit_eval` with the `sit-eval` command: loaders, matcher (shortlist plus location candidates,
  pairwise 0-3 with 3 samples and median, blinding, Hungarian assignment, strict and lenient, credit
  modes, adjudication), grounding G1-G3, every metric in metrics.md §3-§10 as value-or-null-with-reason,
  cluster bootstrap and paired tests (the §14 worked example reproduces exactly), live judges over
  `claude -p` and the API, a hard cost stop, resume from a result cache, dry run with call counts.
- The lecturer grader (`sit-eval grade`): grader-facing projection with identity scrubbing and a leak
  guard, Pass A and Pass B verbatim from `research/grading/grader_prompt.md`, sampling and third-sample
  rule per prereg, gates and caps in code, key-aware diagnostic that never emits recall, meta-validation
  V1-V13 builders.
- `tests/robustness/`: 81-row P0 coverage table, 29 fault schedules, oracles calling `invariants.py`,
  results CSV. 46 scenarios run offline (44 pass; LLM-05 and NET-02 await decisions), 28 are
  laptop-only with exact commands, 7 are not schedules (3 await decisions).
- Agent fixes exposed by the suite, each with a regression test: deadline skips always disclosed (this
  hid the skipped refine in the first live run); LLM fault `nth`; configured timeout in the fault
  wrapper; doc-only disclosure when all tools fail; placeholder findings dropped; doc citations holding
  external text fall back to the anchor quote; partial report on a stage crash; refine rejects an
  unexplained severity, disposition or kind change; approved-decision reversal flagged; research stop
  reason no longer claims sufficient evidence with none.
- State: `ruff check agent harness tests` clean, `pytest -q` 865 passed 0 skipped, selftest passes.

**Measured live** (Claude Code backend, `ANTHROPIC_API_KEY` stripped):

| What | Calls | Cost | Notes |
|---|---|---|---|
| Grader verifier, Haiku schema check | 2 | $0.24 | found the `$schema` rejection |
| Matcher verifier, Haiku end to end | 27 | $0.32 | cost stop and resume confirmed |
| Pilot scoring of the first live run, Opus high, `per_flaw_batch`, adaptive samples, grounding judges off | 57 | $6.89 | shortlist $0.11 / 6 s, pair batch $0.06 / 11 s, adjudication $0.33 / 14 s per call; about 1k output tokens each |
| Live grader, first attempt | 1 | about $1 | Pass A stopped at the $1 per-call cap; grader cap raised to $4 |
| Live grader on the first live run, Opus high, key-blind, 2 samples | 4 | $4.85 | Pass A $1.07-1.15 / 159-194 s / 19-23k output tokens; Pass B $1.30-1.32 / 92-105 s / 11-12k output |

Pilot scores (exploratory only: prereg unfrozen, key not `scored_run_ready`; artefacts in
`docs/live_runs/live_cc_opus_payments_v1/eval_pilot/`): strict recall 10/14, lenient 14/14, adjudicated
precision 0.95, severity-weighted recall 0.72, critical recall 0.75, severity agreement QWK 0.38. The
four partial matches are F04, F06, F07 and F12; the matcher agrees with the by-eye reading in §8. Open
question, since decided (USER_DECISIONS #14): such findings are now labelled PARTIAL_KEY_MATCH, count as
correct for adjudicated precision, and never enter the pooled key G+.

Grader pilot (unvalidated tier, same-family grader; artefacts in `.../grade_pilot/`): S = 83.8, grade B,
PASS, all gates pass. D8 research sufficiency 1 (expected: the run was doc-only), D9 output integrity 2,
D4 evidence 3, everything else 3.5-4; samples agreed within one point per dimension. Six hallucination
flags: two verified wrong document locations (FND-004 cites p1/s12.4, the same defect the matcher found
in EV-016; FND-006 cites p13/s3) and four suspected misreadings (FND-013 material) that need a human
check (GR §4.3). Live spend this session on model calls was about $13.3, on top of the subagents.

## 10. State at the end of the third session, and next steps (2026-10-02, evening)

Branch `claude/happy-darwin-d0bl94`, all pushed. The session ended on a context limit, mid-wave.

**Done and verified this session (details §9 and `docs/transcripts/session3_coordinator.md`):** evaluation
harness (matcher, metrics, statistics, grader); robustness P0 suite (49 offline pass, 28 laptop-only, 4
covered by tests, 0 awaiting decision); matcher rule "the shortlist bounds pairwise scoring" (owner #10);
PARTIAL_KEY_MATCH, adaptive third sample, no second-provider judge, Anthropic-only (owner #14-#16); config
profiles; demo CLI (`--profile`, `--k`, `dra coverage`, `dra replay`); runtime policies (deadline inside
model calls, default deadline 3600 s, demo profile 540 s, NET-02, INF-08, LLM-10, OVF-07, `process:`
faults, ingest heading fix, replay logging); answer-key drafts for all 45 synthetic flaws plus 57 approved
decisions, verified (`eval/KEY_SIGNOFF.md`); prereg amendments logged in `eval/prereg_deviations.md`
(entries 1-7).

**Measured live this session (Opus 5.5 high, `claude -p`):**

| Run | Calls | Cost | Result |
|---|---|---|---|
| Pilot scoring, old union rule, per-flaw batch, judges off | 57 | $6.89 | strict recall 10/14 |
| Grader, key-blind, 2 samples | 4 (+1 capped) | $4.85 (+~$1) | S 83.8, grade B |
| Re-score, pre-registered setup (bounded, pairwise, adaptive, judges on) | 98 | $10.36 | strict 11/14, lenient 14/14, P_adj 0.95, SWR 0.73, HFR 0.0 |

Per call: shortlist $0.11, pair $0.033, adjudication $0.33, premise judge $0.22, citation judge $0.06,
grader Pass A $1.07-1.15, Pass B $1.30-1.32. So scoring plus grading one run costs about $15. Artefacts
under `docs/live_runs/live_cc_opus_payments_v1/` (`eval_pilot/`, `eval_pilot2_bounded/`, `grade_pilot/`).

**In flight when the session ended (check first):**
- The runtime + demo-CLI integration verifier (one Opus subagent) was still running. Its brief: verify W1
  and W2 together, plus five coordinator decisions: a `not_assessed` verdict in the spec, models and
  harness (instead of `not_fit` at confidence 0); remove `stripe.com` and `confluent.io` from the authority
  lists; runbook fixes (`--profile demo` in §5, reserve wording, §4.1 lines 4-5, `FND-007` example);
  a `Makefile` with `smoke` and `test`; EVAL_PLAN timing from the measurement; and raise
  `config/agent.yaml` line 10 `max_tokens` from 64000 to 128000 (Opus 5.5 allows 128K output; the live
  assess used 63,392 of 64,000), with the claude_code pass-through marked UNVERIFIED. Its log, if it got
  that far, is `research/audit/verify_runtime_cli_editlog.md`. Any of its uncommitted edits were pushed in
  the final WIP commit of this session. **Next session: check `git log` and that edit log; whatever of the
  list is missing, finish it with one Opus agent and a separate verifier, then run `ruff check agent
  harness tests`, `pytest -q` and `sit-review selftest`.**

### Next steps, in order

1. **Finish and verify the integration items above.**
2. **Apply the SIT FABLE key decisions** (verbatim in the session record, section "SIT FABLE decisions";
   not yet applied): edit the drafts in the three `answer_key.json` files and `eval/KEY_SIGNOFF.md`
   (payments F04, F11; clinical F09; lakehouse F01; lakehouse F05 and F06 credit-item roles via
   `role_of()` in `spec/convert_answer_keys.py`); key-only canary for S-dev, noted for the LC10/LC11 scans;
   accept the eval-data audit for the 20 external facts; link payments F15 to AD-004 and write the linking
   rule next to item 7; record them in `docs/USER_DECISIONS.md` as #17-#20 attributed "SIT FABLE for the
   owner, 2026-10-02"; re-run `python3 spec/convert_answer_keys.py --tier synthetic --check
   --verify-anchors`; verify with a separate agent. Then tell the owner that only their signature remains.
3. **Demo measurement run** (owner approved, about $3-4): `sit-review review
   eval/synthetic/payments_orchestration/design_v1.pdf --profile demo --no-tools --run-id
   demo_profile_measure_1` in the cloud sandbox (MCP hosts are unreachable here); record per-phase wall,
   tokens and cost; check it fits 540 s; adjust `config/profiles/demo.yaml` reserves from the numbers.
   Commit the run dir under `docs/live_runs/` so `dra replay` works on it (it keeps `llm.jsonl`).
4. **Redo `docs/BUDGET.md`** from measured numbers: agent run (the §8 run plus the demo measurement),
   scoring about $10.4 and grading about $4.9 per run, the k and Tier A run counts from `eval/EVAL_PLAN.md`;
   present Tier A to the owner for approval (owner task).
5. **Owner tasks:** sign the keys (`eval/KEY_SIGNOFF.md`), MCP probe on the Mac, the SIT answer key before
   any run on the SIT PDF, the SIT questions (slot length, PDF hand-over, venue network, GitHub IDs).
6. **Then:** a live run with tools from the laptop; the demo stopwatch rehearsal; the submission documents
   per `docs/DOCUMENTATION_MAP.md`; one Fable fresh-eyes audit; freeze prompts and prereg; Tier A.
