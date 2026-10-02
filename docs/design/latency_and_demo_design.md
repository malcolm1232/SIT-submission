# Latency and demo design: a complete review inside a 10-minute slot

Date: 2026-10-03.
Status: proposal for the planner; no product code or config was changed.
Branch `s4/demo` at `feb1d9f`; Claude Code 2.1.288 on the Mac, subscription login, load average 9 to 14 on 8 cores for every timing.
Probe scripts and their numeric results are outside the repo, in the session scratchpad folder `latency_design/` (`ld_*.py`, `ld_results.jsonl`).
Recommendation in one line: run understand, plan with research, and four assess shards concurrently, then one revision-only refine and a short verdict call, all at `medium`, predicted 443 s against the 540 s deadline.

## 1. Baseline: where every second goes

| Phase | `high`, first live run | `medium`, demo profile run | Split of the `medium` call (derived) |
|---|---|---|---|
| ingest | 2 s | 3.5 s | code |
| understand | 158 s, 22,227 tokens | 136 s, 18,033 tokens, 31,066 visible chars | JSON 100 s, thinking about 28 s, CLI 8 s |
| plan | 158 s, 17,003 tokens | 102 s, 10,065 tokens, 16,189 visible chars | JSON 52 s, thinking about 42 s, CLI 8 s |
| assess | 520 s, 63,392 tokens, about 95,000 visible chars | cut at 179 s | at `high`: JSON 306 s, thinking about 205 s |
| refine | never ran | never ran | re-emits every finding: at least the assess JSON time again |
| verify | 33 s (one repair call) | code only | |
| report (verdict call) | 88 s, 9,918 tokens, 18,500 visible chars | not run | JSON 60 s, thinking about 20 s |

The split uses the JSON emission rate measured in section 2 (310 chars per second) and the visible characters counted by script from `llm.jsonl` and `report.json`.
The time is output: about 60 % of assess is the model typing 21 findings of 4,554 chars each, and evidence (32 %) and recommendation (22 %) are the largest fields.
A complete sequential run at `medium` with refine is about 3.5 + 136 + 102 + 430 + 420 + 5 + 80 = 1,177 s, document-only.
No reserve setting can fit that into 540 s.

## 2. Measurements

Command shape, copied from `ClaudeCodeGateway.build_argv` and `env`: `claude -p --model M --system-prompt S --tools "" --strict-mcp-config --disallowedTools "mcp__*" --disable-slash-commands --output-format json|stream-json --effort E --json-schema J --session-id U`, prompt on stdin, both key variables removed.
38 calls were made: 34 on Haiku 4.5 and 4 on Opus 5.5.

| # | Question | Result | Spread and n |
|---|---|---|---|
| M1 | CLI start-up | `claude --version` 0.02 to 0.03 s (n = 5); the API message starts 1.4 to 2.5 s after spawn, once 4.4 s for the first Opus shard under load 14 | n = 11 |
| M2 | Per-call overhead with this login's user settings | trivial Haiku call 9.6 to 12.7 s wall for 2.6 to 5.5 s of API time; 5.1 s pass between the last token and the result (n = 3 streamed); 2,570 input tokens | n = 6 |
| M3 | Same call with `--setting-sources ""` (or `--safe-mode`) | 3.0 to 3.5 s wall; result 0.01 s after the last token; 1,137 input tokens | n = 4 |
| M4 | Are 4 and 8 simultaneous sessions parallel? (Haiku, one fixed prompt) | yes: 4 calls end in 222 s, 8 calls in 182 s, against 135 s for one; per-call rate 119 to 131 and 112 to 235 tokens/s against 125 and 183 alone; no error, no 429 | n = 2, 4, 8 |
| M5 | Output volume of one identical prompt | 5,366 to 42,606 output tokens, almost all thinking | n = 14 |
| M6 | Opus `medium`, one assess shard of 2 or 3 criteria, 4 sessions started 4 s apart, today's assess brief (23,000 chars, with intent, registry and plan answers) and schema | thinking phase 99.5, 106.3, 108.1, 110.8 s; then JSON at 304, 305, 309, 316 chars/s; 18,028 to 21,034 chars streamed when the probe cut each call at 170 s | n = 4, all cut |
| M7 | Does the structured answer stream? | yes: 1,154 to 1,358 `input_json_delta` events per shard, and a `thinking_tokens` event about every 1.2 s; one API message per call | n = 4 |
| M8 | Cache, document and brief in one user turn (today's layout), second session with another brief | read 0, wrote 9,230 | Haiku, n = 1 |
| M9 | Cache, byte-identical request in a second session | read 18,460 | Haiku, n = 1 |
| M10 | Cache, document in `--system-prompt-file`, other brief, same schema | read 8,416, wrote 827 | Haiku, n = 1 |
| M11 | As M10 with another `--json-schema` | read 0, wrote 9,256 | Haiku, n = 1 |
| M12 | As M10, two sessions started together, and 4 s apart | together: both wrote the prefix; 4 s apart: the second read 8,417 | Haiku, n = 2 + 2 |
| M13 | Whole-call Opus rate from the two recorded runs | `high` 108 to 141 tokens/s (5 calls), `medium` 99 and 133 tokens/s | recorded |

What the numbers say.
Thinking is a fixed block per call: about 105 s for an assess call at `medium`, whatever the number of criteria.
JSON emission is steady at about 310 chars per second per session and did not slow with four Opus sessions open.
So wall time is the count of sequential model stages times their thinking block, plus the longest JSON any one call must type.
This login's user-level hooks and plugins cost about 7 s per call and add 1,433 input tokens that are not in the prompt bundle (M2 against M3).
Separate CLI sessions do share a cache entry, but only when the tool list (the `--json-schema`), the system prompt and the bytes up to the breakpoint are identical; the schema differs per phase, so phases never share (M8 to M12).
Caching changed no wall time that could be seen; it is a cost lever only.
Not measured as asked: Opus at `low` and at `high` on a fixed task, a finished shard, and a shard that lacks the understand output as the design proposes.
Both probe mistakes were mine: the Haiku prompt asked for an exact count and triggered heavy thinking, and the 170 s cut was too short.
Spend: $1.61 on the CLI's cost field (Haiku), plus the four cut Opus calls, which report no cost; estimated $2.0 to $2.4, so about $3.6 to $4.0 in all, and probing stopped there.

## 3. Levers

Savings are against the 1,177 s sequential `medium` run of section 1.

| # | Lever | Seconds saved, with the arithmetic | Quality risk | Invalidates |
|---|---|---|---|---|
| 1 | Assess as K = 4 concurrent shards | 430 to 205: one thinking block (105) plus a quarter of the JSON (30,000 chars, 97 s); saves 225 | duplicates and cross-criterion findings; no global ranking inside assess; 3 more thinking blocks (about +$0.8) | assess prompt, pilot numbers, replay order, fault `nth` |
| 2 | Smaller or merged understand and plan | merged call about 45 + 152 = 197 s against 238 sequential, but 136 s when run side by side: rejected in favour of lever 8 | trimming registry quotes would weaken INV-04 and INV-10 | nothing (not done) |
| 3 | Report by code | `report.md` is already code-rendered; dropping `unresolved` and `limitations` from the verdict call removes 9,200 of 18,500 chars; saves about 30 | limitation text becomes the code's plainer wording | `report.md` prompt, `ReportOutput` |
| 4 | Research beside assess, feeding refine | research leaves the critical path; saves its whole duration (up to 10 min sequential) | assess no longer sees external evidence; refine applies it | research start rule, refine prompt |
| 5 | Streamed output and salvage of a cut call | 0 s; first draft findings on screen at about 125 s; a cut keeps every finished finding | drafts shown before verify must be labelled as drafts | gateway output format, LLM-05 expectations |
| 6 | Shared prompt cache across shards | 0 s; about $0.40 per run (3 x 28,000 tokens x $4.80 per million); needs the document in the system prompt and a 4 s stagger | document text gains system-prompt authority (injection posture) | rejected for now |
| 7 | Effort per stage | `medium` everywhere, research `low`, as the demo profile; `low` on assess is unmeasured | lower effort on the reasoning stage | ADR-002 wording only |
| 8 | Wide first stage: understand, plan with research, and assess start together | assess stops waiting for understand and plan: saves 136 + 102 = 238 | assess works from the document and criteria only; decisions are linked in refine | assess and plan prompts, orchestrator, checkpoints |
| 9 | Refine returns revisions, not the findings again | 420 to 175: thinking 125 plus 15,000 chars of revisions (48 s); saves 245 | patch application in code must be exact | `RefineOutput`, refine prompt, BEH-10 test |
| 10 | Hermetic CLI settings | about 7 s per call, 20 s on the three-call critical path; removes 1,433 foreign input tokens per call | none known; unverified in a cloud session | config only (`claude_code.extra_args`) |
| 11 | Opus fast mode | up to 2.5 x output speed at 2 x price (`research/models/README.md`); unmeasured through the CLI | none on content; billing changes | owner decision, not in the design |

## 4. Recommended design: wide first stage, then conclude

```
ingest (code)
stage 1, concurrent:  understand                 -> intent, registry (frozen when it ends)
                      plan -> research           -> evidence ledger; research starts when plan and understand are done
                      assess shard 1..4          -> draft findings per criterion group, from the document and criteria only
merge (code)          renumber findings in shard order, write shard evidence to the ledger in shard order
refine (one call)     global: merge duplicates, withdraw, rank, fix severity and disposition, link registry decisions,
                      attach research evidence; returns one revision per finding, never the findings again
verify (code)         anchors; the one repair call only when more than 60 s of slack remains
report                verdict call (verdict only), then code renders report.md
```

The eight phase names stay; only their order changes, so `PhaseName`, effort keys, provenance phases and checkpoint names keep their meaning.
Shards are criterion groups in config: intent and fitness (3 criteria), requirements and consistency (3), claims and assumptions (2), risk and operations (3).
A criterion appended live with no group forms its own shard, so runbook change 4.2 #1 adds a parallel call, not wall time.
Shards list findings in rank order, so a cut loses the least important ones first.

| Step | Output tokens (est.) | Wall | Ends at | Basis |
|---|---|---|---|---|
| ingest | 0 | 3.5 s | 3.5 s | measured |
| understand | 18,000 | 136 s | 140 s | measured at `medium`, off the critical path |
| plan | 10,000 | 102 s | 106 s | measured at `medium`, off the critical path |
| research (tools on, effort `low`) | about 6,000 | about 75 s, hard end 265 s | 216 to 265 s | unmeasured on Opus |
| assess, 4 shards | 4 x 26,000 | 2.5 + 105 + 97 = 205 s | 208 s | thinking and rate measured (M6); volume predicted from the first run; more than 170 s measured |
| merge | 0 | 1 s | 209 s | code |
| refine | 23,000 | 2.5 + 125 + 48 = 175 s | 384 s | predicted |
| verify | 0 | 5 s | 389 s | code |
| verdict | 7,000 | 2.5 + 30 + 19 = 52 s | 441 s | predicted from 88 s at `high` and the smaller schema |
| render, invariants | 0 | 2 s | 443 s | measured 0.1 s |

Document-only total: 443 s, slack 97 s (18 %) against 540 s.
With research: 450 to 499 s, slack 41 to 90 s, because refine waits for research up to the stage 1 limit.
Output is about 165,000 tokens and the run costs about $5.0 document-only and $5.4 with research (list prices, estimate).
The pessimistic sum (shards 245, refine 215, verdict 75) is 546 s, so the cuts below are part of the design, not an afterthought.

Limits on the run clock at 540 s: stage 1 ends by 265 s, refine by 465 s, the verdict call by 530 s.
When a limit fires:
- A shard cut at 265 s keeps every finding it had finished streaming; its criteria without a finding are marked not assessed, and the cut is a disclosed degradation.
- Research cut at 265 s stops with `stop_reason: deadline` and what the ledger holds is used.
- Refine cut at 465 s falls back to the merged findings ordered by severity and confidence, disclosed.
- A cut verdict call falls back to the existing rule-based verdict.
- `not_assessed` remains only for a run in which no shard finished a single finding by 265 s.

Progress shown live, from the CLI's event stream:
- One status line at least every 10 s that lists each open call with its thinking-token estimate or its streamed item count.
- A line for each draft finding as its JSON object completes, labelled draft and unverified, from about 125 s, then about one every 3 to 4 s.
- The intent and the registry count at about 140 s, the plan at about 110 s, the merged list at about 210 s, the verified report at about 445 s.

## 5. What changes

| Area | Change | Files |
|---|---|---|
| Frozen interfaces, one PR, alone and first | `RefineOutput` becomes revisions; `ReportOutput` keeps the verdict only; `LLMDeadlineError` carries the salvaged partial answer and estimated usage; config keys `assess.shards`, `refine_reserve_seconds` (replaces `assess_reserve_seconds`); the stage 1 group and new `ON_CAP`; a checkpoint ordinal; the run's elapsed seconds in the budget | `llm/outputs.py`, `errors.py`, `config.py`, `states.py`, `state/checkpoint.py`, `state/run_state.py`, `config/agent.yaml` below line 13, `config/stop_rules.yaml` below line 9, `config/profiles/demo.yaml` |
| Freeze-rule steps | an "interface change" note naming every caller; the PR lands alone before dependent work; every workstream rebases onto it; `models.py` and the spec do not change; pinned config lines do not move | `agent/README.md` "Interface freeze" |
| Prompts and lock | assess: scope paragraph, no intent, registry or answers; plan: no intent or registry; refine: revision rules; report: verdict only; then `python -m sit_review_agent.prompts --write-lock` | `prompts/assess.md`, `plan.md`, `refine.md`, `report.md`, `PROMPTS.lock` |
| Gateway | `--output-format stream-json --verbose --include-partial-messages`; result read from the last `result` event; partial stdout kept on a cut; usage of a cut call recorded as an estimate | `llm/claude_code.py`, new `llm/partial.py` |
| Config | `claude_code.extra_args: ["--setting-sources", ""]`; demo profile reserves 200 s (refine) and 75 s (verify and verdict) | `config/agent.yaml`, `config/profiles/demo.yaml`, runbook 4.1 note |
| Checkpoints and resume (ADR-009) | each stage 1 member writes its checkpoint when it ends; the latest is chosen by ordinal, not by file name; resume re-runs only unfinished members and unfinished shards; the clock is restored from the stored elapsed seconds, since overlapping phase times no longer sum | `orchestrator.py`, `state/checkpoint.py`, `phases/assess.py` |
| Fault injection | `nth` stays the logical call index of a stage, and shards are numbered in launch order; new schedules: one shard hangs, one shard refuses twice, one shard truncates, refine cut | `tests/robustness/faults/`, `tests/test_fault_injection.py` |
| Manifest and cost | cut calls counted with `estimated: true`; per-stage seconds plus the wall total; shard count and salvage count in `extra` | `manifest.py` |
| Replay | calls matched by `conversation_id` and request hash, not by position; the replay clock follows recorded start offsets inside stage 1 | `replay.py`, `tests/test_cli_replay.py` |

Draft ADR-011, concurrent first stage and revision-only refine (amends the phase order in ADR-001).
Context: measured on 2026-10-03, a model call costs a fixed thinking block (about 105 s for assess at `medium`) plus JSON at about 310 chars per second, so six sequential model stages cannot fit 540 s.
Decision: understand, plan with research, and K assess shards run concurrently; refine is one global call that returns revisions; the verdict call returns the verdict only; one profile serves the demo and the evaluation.
Consequences: assess no longer receives the intent, the registry or research answers, and refine links decisions and applies evidence; cost per run is about $5; checkpoints, replay and fault matching become order-independent.
Status: Proposed, to be confirmed by a timed rehearsal.

Draft ADR-012, streamed CLI output, salvage and hermetic settings (amends ADR-010).
Context: `claude -p` streams the structured answer as `input_json_delta` events; user-level settings on the Mac add about 7 s and 1,433 input tokens per call; a cut call today records no usage.
Decision: the gateway reads the event stream, shows progress from it, keeps the finished items of a cut call and logs estimated usage; every call passes `--setting-sources ""`.
Consequences: a deadline cut leaves a real report; the prompt the model sees is the hashed bundle only; the flag is unverified in a cloud session and must be checked there once.
Status: Proposed.

Amendment to ADR-002.
The one-effort-level-per-conversation rule stays and already allows a level per stage, since every call is its own conversation.
Its cache rationale does not apply to the CLI backend: phases never share a cache entry because the schema differs (M11).
The frozen agent runs `medium` on every stage and `low` for research; `high` remains the A4b comparison.

## 6. Evaluation consequences

- Stale: every number scored on `live_cc_opus_payments_v1` (strict recall 11 of 14, adjudicated precision 0.95, SWR 0.73, grader S 83.8) describes a single assess call at `high` with no refine.
- Stale: the run time and cost basis of `eval/EVAL_PLAN.md` (959 s floor, 3,600 s cap, $2.18 per FULL run) and the replay of `demo_profile_measure_1` under new prompts.
- Re-pilot before A-2: three timed rehearsals on payments v1 (two document-only, one with tools, about $15) and one of them scored and graded (about $15), about $30 in all.
- Prereg text (not frozen, deviations entry 10): `agent_under_test.effort_per_stage` filled with `medium` and research `low`, plus the profile name and shard groups.
- Prereg text: `conditions.B0` says the single call is the assess brief with all criteria in one call.
- Prereg text: `runs_per_item.scheduling` says one FULL run at a time until 12 concurrent sessions are measured (a run holds up to 6).
- Prereg text: `stop_rule.pilot_checkpoint` keeps "p95 wall time exceeds the demo slot" as the gate for this design and re-bases the $3.24 figure on the redone budget.
- Prereg text: reporting adds the share of FULL runs with any deadline cut and the count of salvaged shards, intention-to-treat.
- Run count: unchanged at 132 (93 FULL-shaped, 39 single-call).
- Wall time: FULL runs are capped at 540 s, so 93 x 540 s + 39 x 520 s = 19.6 h of run time at most, against a 30.4 h floor and a 132 h cap today.
- Agent budget: about 93 x $5.4 + 39 x $1.6 = $565 before margin, against $240 planned; the old design run to completion at `high` is an estimated $5.7 per run, so the rise comes from measured prices, not from this design.

## 7. Build plan

| Workstream | Owns (disjoint) | Tests it adds |
|---|---|---|
| W0 interface PR, alone, first | `llm/outputs.py`, `errors.py`, `config.py`, `states.py`, `state/checkpoint.py`, `state/run_state.py`, `config/*.yaml`, `config/profiles/demo.yaml`, `tests/test_config*.py`, `tests/test_models.py`, `tests/test_skeleton_imports.py` | schema round trips for the new output types; config layout and profile tests; transition table covers the stage 1 group |
| W1 gateway and streaming | `llm/claude_code.py`, new `llm/partial.py`, `llm/gateway.py`, `llm/runtime.py`, `progress.py`, `tests/test_claude_code_gateway.py`, `tests/test_anthropic_gateway.py`, `tests/test_runtime_policies.py` | stream parsing from recorded event fixtures; a cut after 3 of 6 findings salvages 3; cut usage logged as estimated; stage limits for 540 s; `--setting-sources` on every argv |
| W2 orchestration, phases, prompts | `orchestrator.py`, `phases/*.py`, `prompts/*`, `tests/test_orchestrator.py`, `tests/test_llm_phases.py`, `tests/test_run_and_resume.py`, `tests/test_not_assessed_verdict.py`, `tests/test_prompts.py`, `tests/test_e2e_synthetic.py` | stage 1 runs concurrently on `FakeClock`; research waits for understand; deterministic finding and ledger IDs whatever the completion order; revision patches (merge, withdraw, rank, BEH-10); one failed shard leaves a partial review; resume re-runs only unfinished shards |
| W3 replay, manifest, robustness, docs | `replay.py`, `manifest.py`, `selftest.py` and its fixture, `tests/robustness/*`, `tests/test_fault_injection.py`, `tests/test_cli_replay.py`, `tests/test_selftest_cli.py`, `docs/*`, `agent/README.md`, `eval/EVAL_PLAN.md`, `eval/prereg.yaml`, `eval/prereg_deviations.md` | replay of a concurrent run is byte-equal; shard hang, refusal and truncation schedules; LLM-05 now expects a salvaged report; manifest totals include cut calls |

Order: W0 merges first; W1, W2 and W3 then run in parallel against its types; W3's selftest fixture and replay tests land after W2; one integration pass; then the timed rehearsals.
The verifier must check:
- `ruff`, the whole suite and `make smoke` pass, and no test was weakened to pass.
- A document-only rehearsal ends inside 540 s with refine and the verdict call both run, and its stage times are within 20 % of the table in section 4.
- A run with a 300 s deadline produces a report with findings, not `not_assessed`.
- Two runs of the same recorded input give identical finding IDs and ledger IDs.
- `dra replay` reproduces a concurrent run offline.
- The first input-token count of a trivial call equals the hermetic figure (1,137 on Haiku), on the Mac and in a cloud session.

## 8. Risks, what is unmeasured, and the fallback

- Unmeasured: a finished shard at `medium`, its finding count and the duplicate rate across shards (all four probes were cut at 170 s).
- Unmeasured: refine in revision form, the verdict call at `medium`, research turns on Opus, and Opus at `low`.
- Unmeasured: cache reads between Opus sessions, more than 4 concurrent Opus sessions, more than 8 sessions of any model, and the effect of the Mac's load.
- Unmeasured: `--setting-sources ""` in a cloud session, fast mode, and the `anthropic_api` backend under this design.
- Risk: assess without the registry and research answers may find fewer flaws that need external facts; the pilot compares it with B0 and the old run.
- Risk: identical prompts varied 8 x in thinking volume on Haiku (M5), so one slow shard is likely on some day; salvage and the stage limit bound it.
- Risk: output per run rises to about 165,000 tokens, which matters for subscription limits during Tier A.
- First tuning step if stage 1 exceeds 230 s in rehearsal: K = 6 (about 170 s, about +$0.65 per run); the second is fast mode, if the owner agrees.

Fallback on the day, if the design misses 540 s.
The live run always ends by 540 s with a report, so the fallback is about its content, not about waiting.
Record one complete run of the SIT sample and one delta pair with the final code after the freeze, and check `dra replay` on both the day before (runbook section 1).
At 0:30 start the live run; keep `dra replay runs/demo_backup_sit_v1` typed and unstarted in a second terminal.
If no draft finding has appeared by run time 265 s, say so, start the replay, and walk `explain` and `coverage` on it while the live run finishes.
If the live report is partial, show it first with its disclosed cuts, then the replay for depth; if it is `not_assessed`, show the replay and rerun with `--deadline 900` during questions.
The replay shows the SIT sample only, never the unseen PDF, and it is stamped "replayed evidence"; say both aloud.

## 9. Decisions for the planner

1. Adopt the wide first stage, in which assess does not wait for understand and plan?
   Recommended: yes; keeping the order costs 238 s and leaves no room for refine inside 540 s.
2. Is the evaluated agent the demo profile (`medium`, 540 s, same shards)?
   Recommended: yes, so Tier A describes what the demo runs; `high` stays as A4b.
3. K and the groups?
   Recommended: the four groups of section 4, moving to six only if a rehearsal shows stage 1 above 230 s.
4. Add `--setting-sources ""` through `claude_code.extra_args` now, ahead of the build?
   Recommended: yes, after one check in a cloud session; it is config only.
5. Move the document into the system prompt to share the cache across shards?
   Recommended: no; it saves about $0.40 per run and no time, and it weakens the injection posture.
6. Trim the verdict call to the verdict and let code write unresolved items and limitations?
   Recommended: yes.
7. Trim the evidence fields the model writes per finding (32 % of assess output)?
   Recommended: no; it is a quality change to measure separately.
8. Ask the owner about Opus fast mode (2 x price)?
   Recommended: ask, and measure once if allowed; the design does not depend on it.
9. Approve about $30 for three timed rehearsals and one scored pilot before A-2?
   Recommended: yes; the first rehearsal settles the three predicted rows of section 4.
