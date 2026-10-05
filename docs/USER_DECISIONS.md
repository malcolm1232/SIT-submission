# User decisions log

Decisions given by the project owner in conversation. These override research recommendations. Fold into DECISIONS.md ADRs when editing that file.

## 2026-10-02

| # | Question | Decision | Consequence |
|---|---|---|---|
| 1 | Agent model | Claude Opus 5.5 for every agent call. No Sonnet/Haiku sub-tasks. Effort may be high throughout; token budget is sufficient, but spend must be justified, not excessive. | All-Opus cost model stands. Effort default for agent phases: `high` (not `medium`); `xhigh` only where a measured ablation shows gain. |
| 2 | Grader model | Owner defers to coordinator judgement. | Coordinator decision: primary holistic grader is Opus 5.5 at `high` effort; if the Mac reports an OpenAI or Google key, add a different-provider judge at high effort as the headline bias-controlled score and report agreement between the two; Sonnet 5.5 runs as a same-family control. If Anthropic-only, disclose the same-family limitation per research/models/README.md. |
| 3 | API keys held | Being retrieved from the Mac session. | Judge branch chosen when the report arrives. |
| 4 | Repo privacy | Repository is already private. | Sealing of answer keys is still required (collaborators and future tooling can read the repo), but the web-search leakage path is closed. SEALING.md interim rule applies. |
| 5 | Ablation A4 ("different model") | Owner defers; low effort not required. | Coordinator decision: A4 remains a genuine different-model ablation, run with Sonnet 5.5 as the AGENT model for that experiment only (the product stays all-Opus). Add A4b: an effort sweep on Opus 5.5 (medium / high / xhigh) to justify the chosen effort level with data. |

## 2026-10-02 (later)

| # | Question | Decision | Consequence |
|---|---|---|---|
| 6 | Billing for agent model calls | Owner wants all agent LLM calls on cloud credits / subscription usage, not a Console API key. | ADR-010 proposed: `claude_code` backend default, `anthropic_api` kept as an option. Pending owner confirmation of ADR-010. |
| 7 | Second-provider judge | Owner will top up OpenAI and/or Google later. | ADR-003 judge branch A stays open; revisit when keys are funded. |
| 8 | Cloud credits | This account: $36 of $250 left after this session (~$214 used). Two other accounts with $250 each, expiring 5 Nov. | Continue build in another account per docs/HANDOFF.md. |
| 9 | ADR-010 (Claude Code backend) | Owner replied "CAN U CONTINUE on it please?" to the request for confirmation. Taken as confirmation. | ADR-010 accepted. `llm.backend: claude_code` is the default in `config/agent.yaml`; `anthropic_api` stays available for evaluators with an API key. |

## 2026-10-02 (third session)

| # | Question | Decision | Consequence |
|---|---|---|---|
| 10 | Matcher candidate rule | Shortlist bounds pairwise scoring (coordinator recommendation, approved by owner) | Pairwise 0-3 scoring runs only on the up-to-3 findings the listwise shortlist returns per flaw; location overlap is a hint in the shortlist prompt and adds no pair by itself; location compatibility still caps a 3 at 2. prereg `matcher.candidates`, metrics.md §2.3 and §13, and the labelling protocol T4 amended (first entry in `eval/prereg_deviations.md`). The old union rule is kept as a comparison mode (`sit-eval score --candidate-rule union`, a deviation). Shortlist prompt changed, so the prompt bundle hash changed. Tier A budget (`docs/BUDGET.md`) to be redone from measured costs after a pilot under the new rule. |
| 11 | Remaining build decisions | Owner: "can u proceed to build end to end and u decide what is necessary". | Build decisions delegated to the coordinator; owner-level choices (budget, judges, prereg semantics) are still brought to the owner. |
| 12 | Demo package | Approved: the demo effort profile, the run deadline enforced inside model calls (each attempt bounded by the remaining deadline), and one measurement run (about $3-4). | Demo profile and deadline handling built by the agent workstream; one live measurement run before the demo. |
| 13 | Robustness policies | Per coordinator recommendation ("as per ur rec"): NET-02 a short retry window for connection errors on the first model call of a run, then a clean exit; INF-08 fail fast when the MCP key is missing (unless `--no-tools`), doc-only only when the key is revoked mid-run; LLM-10 a character-based token estimate before sending, plus a 150-page fixture; OVF-07 the vendor host list moves from `tools/sources.py` to config. | Implemented in the agent and robustness workstreams; scenarios re-run against the new behaviour. |
| 14 | Partial matches | Per coordinator recommendation: a strict-unmatched finding that scores PARTIAL (2) against a key flaw nobody matched gets its own label, `PARTIAL_KEY_MATCH`, and counts as correct for adjudicated precision. | Never VALID_UNPLANTED ("missing from the key"), never in the pooled key G+, never removes a sound unit; reported as its own count. metrics.md §2.3 step 4 and §3, prereg `matcher.adjudication`, `eval/prereg_deviations.md` entry 2. |
| 15 | Adaptive third sample | Per coordinator recommendation: on by default. | The third pairwise sample is asked only when the first two disagree or one failed; the median of three is unchanged and calls are saved. `config/eval.yaml` `matcher.adaptive_third_sample: true`, prereg `matcher.pairwise_scoring`, deviations entry 3; `--no-adaptive-samples` turns it off for one run. |
| 16 | Second-provider judge | None: Anthropic only. | Matcher, adjudicator and judges on Opus (prereg `matcher.model` branch_B) and the grader on Claude, disclosed as same-family per `research/models/README.md`. Prereg `grader.second_provider.available: false` (deviations entry 5); `docs/DECISIONS.md` ADR-003 closed. Supersedes #7. |

## 2026-10-02 (SIT FABLE for the owner; applied 2026-10-03)

The owner said the SIT FABLE session decides on their behalf. These are its decisions on the answer-key sign-off sheet (`eval/KEY_SIGNOFF.md`), verbatim in `docs/transcripts/session3_coordinator.md` ("SIT FABLE decisions"). Attributed: SIT FABLE for the owner, 2026-10-02. Decided 2026-10-02, applied 2026-10-03. The owner's signature step stays theirs.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 17 | S-dev canary: embedded in the documents or key-only | Key-only for the three S-dev items. `design_v*.md` and the PDFs are not touched: the live run and both pilots cite their hashes and anchor pages, and S-dev is the open development set. Every future held-out item gets its canary embedded before its first run. | `authoring_drafts.item.canary_embedded_in_documents` stays false; `canary_guid` goes in `accepted` at signing. Scan note "key-only canary, S-dev" on prereg LC10 and LC11 (`eval/prereg_deviations.md` entry 8); held-out rule in `docs/SEALING.md` §3 and on the sheet (section 4, step 5). |
| 18 | External facts (20 S-dev entries): owner re-check or accept the eval-data audit | Option (b): `research/audit/eval_data_audit.md` is the verification for all 20 S-dev entries; `verified` stays false with the audit note. Owner re-check with network access is required only for held-out keys and, before Tier A, for any S-dev fact a graded finding's credit turns on. | Each entry's `verification_note` says the audit was accepted; `external_fact_verification` goes in `accepted` at signing. Rule written on the sheet (section 4, step 4). |
| 19 | Core insights in `substance` mode, and the other flagged items | Rule: the core insight states the defect and why it is a defect, nothing else; numbers, parentheticals and secondary consequences come out unless a credit item requires them. Payments F04 and F11 trimmed; clinical F03 and F05 accepted as drafted; clinical F09 replaced with the verifier's item-12 text; lakehouse F01 loses the zero-data-retention clause; lakehouse F04 accepted; lakehouse F05 and F06 c2 made `supporting` in `role_of()`; all drafted dispositions accepted; items 7 and 8 left as they are; item 9 (`v2.changed_sections`) accepted. | Four `core_insight` drafts edited in the three `answer_key.json`; `spec/convert_answer_keys.py` `SUPPORTING_OVERRIDES` (lakehouse 28 required / 30 supporting items, was 30 / 28; `eval/prereg_deviations.md` entry 8, `spec/README.md` §2.6). Rule written on the sheet next to item 10. |
| 20 | Payments F15 and the "Disaster recovery" row (AD-004) | Link it. Rule: a decision row is linked when the flaw's location cites the section that row governs; F15 cites §20.2, which the DR row governs. | AD-004 `flaw_ids` is F03, F15; F15's `affected_decisions` is AD-004, AD-006. Rule written on the sheet next to item 7, for all three keys. |

## 2026-10-03 (SIT FABLE for the owner)

Two rulings by the SIT FABLE session on the points the session 4 keys reviewer reported (`docs/transcripts/session4/keys_verifier.md`, "Report only 1" and "Report only 2").
Attributed: SIT FABLE for the owner, 2026-10-03.
No key changed under them: the links, core insights and credit roles stay as they were at `5b464ba`.
The owner's signature step stays theirs.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 21 | The linking rule of #20: is citing the governed section enough to link a row (clarifies #20) | A decision row is linked to a flaw when (a) the flaw's location cites the section that row governs AND (b) the flaw's defect is in the subject that row decides. Condition (a) alone is necessary, not sufficient: a broad section that hosts several decisions does not link every flaw located in it. The links on the sheet as drafted and verified stand, including the deliberate non-links in item 7; no link is re-derived mechanically. | The reviewer showed that the one-condition wording of #20 would mechanically add 31 links (payments 12, clinical 11, lakehouse 8), three of which contradict sheet item 7's deliberate non-links (payments Fraud/F01, lakehouse Catalog/F10 and Primary storage class/F04); none is added. The one-condition wording next to sheet item 7 is replaced by this rule. Payments F15 -> AD-004 (#20) stands and meets (b): the v2 "Disaster recovery" row adds the warm API cell in ap-southeast-3, which is what lets a duplicate request arrive in a second region (design_v2 §9.4, §20.2); (b) holds through that two-region write topology, not through the lock, which is AD-006's subject. |
| 22 | Scope of the core-insight rule of #19, and what a "Keep" text binds | (i) Rule #19 (the core insight states the defect and why it is a defect, nothing else) applies to flaws scored in `substance` mode. Lakehouse F05 and F06 are scored in `all_of` mode, where the credit items carry the match; their core insights stand as drafted, and their c2 items stay `supporting` per #19. (ii) Where the session record gives a "Keep" text for a flaw, the core insight equals that text exactly; a figure that a credit item needs lives in the credit item, not in the core insight (applied to payments F04 in 5b464ba). | (i) Checked before writing: the lakehouse key has `scoring.default_credit_mode: all_of` and no flaw overrides it (all 15 flaws carry `credit.mode: all_of`), so the reviewer's by-analogy trims of F05 and F06 are not applied. (ii) Payments F04 and F11 already equal their "Keep" texts (`5b464ba`); "~900 TPS" stays in F04 credit item c2. Written on the sheet next to item 10 and in the lakehouse F05 and F06 entries. |

## 2026-10-03 (owner)

The owner's own decision, given in conversation on 2026-10-03.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 23 | Second-provider judge, now that OpenAI and Google keys exist on the Mac | Owner, verbatim: `"judge: no" - it stays Anthropic-only, disclosed as a limitation.` A few minutes later, verbatim: `btw, NO FOR NOW, later i might change my mind.` | #16 stands for now. The second-provider path in the harness and prereg stays in place and switchable; nothing is removed. Revisit on the owner's word. |

## 2026-10-03 (SIT FABLE for the owner, integration)

Two rulings by the SIT FABLE planner on the session 4 integration work, recorded by the session 4 integration verifier (`docs/transcripts/session4/integration_verifier.md`).
Attributed: SIT FABLE for the owner, 2026-10-03.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 24 | Do the two accesses recorded in `eval/blind/ACCESS_LOG.md` (entry 1, the accidental validator run; entry 2, exposure through derived copies) count against the three-evaluation budget for the held-out set? | No. Entry 1 does not count, because no agent output was scored against the held-out items and only flaw counts were seen. The same holds for entry 2. | One line added to `eval/blind/ACCESS_LOG.md` that records this ruling. The held-out set still has its three evaluation accesses (`eval/EVAL_PLAN.md` A-4 is access 1). |
| 25 | The `not_assessed` verdict (session 4, commit `e8a6c12`) | A `not_assessed` verdict is set by code when the agent could not assess the document: the run deadline skipped or cut the assess stage, the assess answer was truncated twice at the output cap (the call and its one retry), or the model declined the assess call twice. Amended 2026-10-03: the truncation reason was added by commit `aab35fa` after this row was first written; these three are every reason the code can produce (`agent/sit_review_agent/phases/report.py`, keys `deadline`, `truncated`, `declined`). It replaces the earlier placeholder, `not_fit` at confidence 0. It is never offered to the model: the model's verdict schema offers `fit`, `fit_with_conditions` and `not_fit` only, and a model answer that carries `not_assessed` fails schema validation, after which the verdict comes from the code rule over the findings. It is excluded from verdict-agreement statistics as implemented in the k-run group summary (`agent/sit_review_agent/kruns.py`): it is never the modal verdict, but its runs stay in the denominator (all completed runs), so they lower the agreement, intention-to-treat. The harness computes no verdict-agreement statistic. It fails the grader's gate G4 (no explicit fitness verdict), which caps D2 at 0, and a dimension at 0 also fails gate G1. | Logged in `eval/prereg_deviations.md` entry 9 (no prereg field changed). `sit-eval score` records `inputs.verdict_label` and warns; `sit-eval aggregate` warns per run; recall is 0 against every key flaw (intention-to-treat). |

## 2026-10-03 (SIT FABLE for the owner, LC12)

One ruling by the SIT FABLE planner on the gap reported in check 6 of `docs/transcripts/session4/keys_verifier.md`: prereg LC12 was enforced by procedure, while the harness only warned.
Attributed: SIT FABLE for the owner, 2026-10-03.
No key changed under it; the three S-dev keys stay unsigned until the owner signs them.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 26 | Prereg LC12 says no scored run on a key that is not signed off, but `sit_eval/scoring.py` only warned and called the scores provisional. Should the harness enforce it? | Yes. A scoring command on a key with `scored_run_ready: false` refuses: non-zero exit, no model call, no cost, and a message that names the key, the missing sign-off and the override. The override is an explicit `--exploratory` flag; with it the run proceeds and every artefact it writes carries `exploratory: true` and a line saying the scores are exploratory and may not be reported as confirmatory. Aggregation refuses to combine exploratory and confirmatory results, or to make a confirmatory analysis from exploratory inputs, unless given the same flag, and then its output is marked exploratory. The rule covers every command that reads a key to produce a score or a key-aware diagnostic; the grader's key-blind passes are not affected. With a frozen prereg an `--exploratory` run says it is outside the pre-registered analysis. The existing pilot artefacts are not rewritten; a one-line note beside each says they predate the guard and are exploratory. | `sit-eval score`, `sit-eval grade run --answer-key` (a legacy YAML key carries no sign-off and is always refused) and `sit-eval aggregate` enforce it, as do `score_review` and `grade_review`; refusal is exit 2 before any judge is built (`harness/sit_eval/lc12.py`, `harness/README.md` "LC12"). A confirmatory run never reuses a cached judge answer written by an exploratory run or before the guard. `EXPLORATORY.md` in each of `eval_pilot/`, `eval_pilot2_bounded/` and `grade_pilot/`; `eval/EVAL_PLAN.md` §1.2 notes that a pilot on unsigned keys is exploratory. No prereg field changed and no deviation entry: the code enforces what LC12 and `freeze.rule` already state. |

## 2026-10-03 (SIT FABLE for the owner, demo latency)

One ruling by the SIT FABLE planner on the demo measurement run (`docs/live_runs/demo_profile_measure_1/MEASUREMENT.md`), recorded by the session 4 hub verifier (`docs/transcripts/session4/hub_verification.md`).
Attributed: SIT FABLE for the owner, 2026-10-03.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 27 | The demo measurement showed the demo profile at `medium` cannot produce a review inside 540 s (understand 136 s, plan 102 s, assess cut at 179 s; verdict `not_assessed`). What is the demo plan? | A pre-recorded replay is the safety net, not the demo. The agent's phase structure is being redesigned for latency (concurrent assess shards, less unseen output, a code-rendered report), with the design note in `docs/design/` to follow. No effort or reserve tuning is done on the current structure. | `docs/BUDGET.md` and the Tier A plan are redone after the redesign is measured, not before. |

## 2026-10-03 (SIT FABLE for the owner, cost metrics)

One ruling by the SIT FABLE planner on the harness's cost and token metrics after the runtime began recording unknown usage as unknown (commit `8ef32d4`).
Attributed: SIT FABLE for the owner, 2026-10-03.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 28 | The runtime now logs a model call that was killed or cut with `usage: null`, lists it in the manifest's `extra.model.calls_with_unrecorded_usage` and sets `extra.model.cost_usd_lower_bound`, while `usage.cost_usd` keeps summing the recorded calls. The harness read that figure as the run's cost, and the prereg pilot checkpoint ("median FULL cost exceeds $3.24") took a median over it. How must the harness report such runs? | (1) Per run: a run with any call of unrecorded usage has null cost and token values in the `efficiency` metric, with reason `unrecorded_usage` naming the count of such calls, and `cost_usd_lower_bound` and the lower-bound token counts reported beside them; a fully accounted run is unchanged. (2) Completeness is read from the manifest field when present; for a manifest that predates it, the harness applies the runtime's rule over the run's `llm.jsonl` (read by code only) and says so; with neither, completeness is `unknown` and the metric is null with reason `usage_completeness_unknown`. The rule is implemented once in the harness with a fixture that pins it to the runtime's behaviour (the demo run's `llm-0003` entry). (3) Aggregates: the FULL-run cost median the checkpoint needs is computed over fully accounted runs and reported with the count and share of runs excluded for unrecorded usage, plus a lower-bound median over all runs; no aggregate mixes the two. (4) The pilot checkpoint, threshold `costs.per_run_usd.heavy_case_FULL`: `fail` if the lower-bound median over all runs exceeds it (a median can only rise as unknown costs are filled in); `pass` only if every run is fully accounted and the median is at or below it; otherwise `not_evaluable`. A lower bound can fail a check but never pass one. (5) Reporting adds, intention-to-treat, the share of runs with any cut call. (6) The prereg text, a deviation entry, this table, `harness/README.md` and `eval/EVAL_PLAN.md` say exactly this. | `harness/sit_eval/usage.py` (the rule, pinned by `tests/eval_harness/test_eval_usage_completeness.py`), `loaders.py` (reads completeness beside `report.json`), `metrics.py` (`efficiency` value: `usage_completeness`, `usage_reason`, `*_lower_bound`), `scoring.py` (warnings), `report_md.py` (a banner before the efficiency bullets), `cli.py` (`score` console `cost`, `aggregate` prints the checkpoint verdict), `aggregate.py` (`cost_usd`, `input_tokens`, `output_tokens` per condition with `median_fully_accounted`, `excluded_unrecorded`, `excluded_unknown`, `median_lower_bound_all_runs`; `runs_with_unrecorded_usage`; top-level `pilot_checkpoint`), `schemas/scores.schema.json` (`$defs/Efficiency` refuses a cost figure on an incompletely accounted run). `eval/prereg.yaml` `stop_rule.pilot_checkpoint`, `costs.usage_completeness` and the Efficiency rows; `eval/prereg_deviations.md` entry 10. The first live run's manifest predates the field and its `llm.jsonl` is not in the repository, so its $3.68 is now reported as a lower bound of unknown completeness; the pilot `scores.json` files are not rewritten and aggregate as unknown. |

## 2026-10-03 (SIT FABLE for the owner, dropped runs)

One ruling by the SIT FABLE planner on the point the session 4 cost metrics verifier left open (`docs/transcripts/session4/cost_metrics_verifier.md`, "Open").
Attributed: SIT FABLE for the owner, 2026-10-03.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 29 | `sit-eval aggregate` drops a `scores.json` whose scoring the judge budget stopped before any statistic, so a FULL run whose scoring stopped was missing from the pilot checkpoint's run count and the checkpoint could `pass` on the FULL runs that remained. How must a dropped run count? | A dropped run is a run of unknown cost. Whenever a FULL scores file is dropped from an aggregate for any reason (judge budget stop, unreadable, schema-invalid, incomplete), the pilot cost checkpoint is `not_evaluable`, the dropped files are listed in the aggregate output with the reason each was dropped, and the console says so. This extends #28's rule that a lower bound can fail a check but never pass one. | `harness/sit_eval/aggregate.py` (`load_scores_with_drops`; reasons `judge_budget_stop`, `unreadable`, `schema_invalid`, `incomplete`; top-level `dropped_inputs` and `pilot_checkpoint.dropped_inputs`; a file whose condition cannot be read counts as possibly FULL; a dropped file of another condition is listed and does not affect the checkpoint; an unreadable file is now dropped and listed where it used to stop the command with a traceback), `cli.py` (`aggregate` lists each dropped file on stderr), tests in `tests/eval_harness/test_eval_aggregate_dropped.py`. `eval/prereg.yaml` `stop_rule.pilot_checkpoint` amended; `eval/prereg_deviations.md` entry 10 extended; `harness/README.md`. `sit-eval aggregate` has no Markdown output, so the listing is in the JSON and on the console. |

## 2026-10-03 (SIT FABLE for the owner, replay of records made before the latency redesign)

One ruling by the SIT FABLE planner on the deviation the latency redesign W0 found (`docs/transcripts/session4/latency_w0.md`, "Finding: the committed measurement record is refused by replay"), confirmed by the W0 verifier (`docs/transcripts/session4/latency_w0_verifier.md`).
Attributed: SIT FABLE for the owner, 2026-10-03.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 30 | After W0, the committed demo measurement run (`docs/live_runs/demo_profile_measure_1`, recorded at `2d84f59`) carries `assess_reserve_seconds` and lacks `assess.shards` and `stage_limits_s`, so its `effective_config.json` no longer validates and `dra replay` refuses it. Should replay translate old records, or the record be edited? | Neither. The refusal is correct behaviour: a record replays only under the phase graph and config schema it was recorded with, so `dra replay` refuses it by name with exit 2 and no traceback, naming the offending key and the commit at which the record replays. The record is not edited and no legacy key is mapped. The demo safety-net recording is made with the final code after the freeze (design section 8). | `agent/sit_review_agent/replay.py` (message only: the refusal names the commit from the record's `manifest.json`, "check out 2d84f59"), `tests/test_cli_replay.py` (`test_the_committed_demo_measurement_run_is_refused_by_name_since_the_config_redesign` asserts the record, the key, the commit and no traceback). The same holds for every run recorded before W0; `docs/design/latency_and_demo_design.md` section 6 already lists that replay as stale. |

## 2026-10-03 (SIT FABLE for the owner, latency design)

Nine rulings by the SIT FABLE planner on the latency design (`docs/design/latency_and_demo_design.md`, measured on 2026-10-03 on the owner's Mac), recorded by the latency W3c documentation worker.
Attributed: SIT FABLE for the owner, 2026-10-03.
The owner may reverse any of them.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 31 | The latency design: six sequential model phases cannot fit the 540 s demo deadline (a complete sequential `medium` run with refine is about 1,177 s; #27). Is the redesign adopted, and on what terms? | Adopted, with nine rulings. (1) Wide first stage: assess does not wait for understand and plan; yes. (2) The evaluated agent is the demo profile: `medium` on every stage, research `low`, 540 s. This overrides the `high` default of #1 on the measured ground that `high` cannot fit the slot; `high` stays as the A4b effort comparison; the owner may reverse this. (3) K = 4 assess shards; K = 6 is the first tuning step if stage 1 exceeds 230 s in rehearsal. (4) `--setting-sources ""` on every CLI call now; the cloud check when a cloud session next exists. (5) The document stays out of the system prompt. (6) A verdict-only report call; the report is rendered in code. (7) No evidence trimming. (8) Opus fast mode is held for the owner. (9) Two document-only rehearsals are approved; the with-tools rehearsal waits for the MCP key; the scored pilot waits for the owner. | `docs/DECISIONS.md` ADR-011 and ADR-012 (Proposed, to be confirmed by a timed rehearsal) and the ADR-002 amendment note. `eval/prereg.yaml` `agent_under_test.effort_per_stage`, `conditions.tier_A` B0, `runs_per_item.scheduling`, `stop_rule.pilot_checkpoint` and the Efficiency row (`eval/prereg_deviations.md` entry 11). `eval/EVAL_PLAN.md` run-time and cost basis marked to be re-measured; `docs/BUDGET.md` is redone after the first rehearsal. `docs/DEMO_DAY_RUNBOOK.md` §1, §4.1 and §5. The scores on `live_cc_opus_payments_v1` describe the old single-call agent at `high` and are stale. |

## 2026-10-03 (the owner, the SIT Memory Platform PDF)

One decision by the owner, recorded by the session 4 budget worker.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 32 | May the agent run on the SIT Memory Platform PDF before the owner's human answer key for it exists? | The owner, verbatim: "sure then, as per ur rec." to the planner's recommendation (a): the key is written first. | No agent run on that PDF until the owner's key exists, written per `eval/human_labelling_protocol.md` (task T1: written before any model output on the SIT document is seen, then hashed). The SIT sample stays an evaluation item (`eval/EVAL_PLAN.md` A-6, real-dev). |

## 2026-10-03 (SIT FABLE for the owner, effort and the demo deadline)

Two rulings by the SIT FABLE planner after the two timed rehearsals of the concurrent design (`docs/live_runs/QUALITY_COMPARISON.md`), recorded by the session 4 budget worker.
Attributed: SIT FABLE for the owner, 2026-10-03.
The owner may reverse either.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 33 | After the measured ablation, what is the default effort for the demo and for the evaluated agent? | `medium` stays the default, now on measured ground: on the payments design, concurrent `medium` and concurrent `high` found the same 13 of 14 flaws strictly, adjudicated precision 0.944 and 0.947, severity-weighted recall 0.933 both, grader S 83.0 and 83.8, at 382 s and $5.74 against 780 s and $8.21. `high` remains the A4b comparison arm (A4b-high). The basis is the clause of #1 that effort is justified by a measured ablation; the evidence is n = 1 document, one run per arm, exploratory (unsigned key, unfrozen prereg). The owner may reverse this. | Config unchanged (`config/profiles/demo.yaml`, `eval/prereg.yaml` `agent_under_test.effort_per_stage` as entry 11 of `eval/prereg_deviations.md` set it). The ablation is re-run in Tier A at larger n. The current plan still has A4b in Tier B (`eval/EVAL_PLAN.md` line B-1: A4b-high and A4b-xhigh on 3 S-dev v1 documents × 3, against A-3 FULL); this row does not change the run matrix or the Tier A budget, so moving A4b-high into Tier A is still to be done. `docs/BUDGET.md` §1.1 prices A4b-high at the measured $8.21, so 9 runs add 9 × $8.21 = $73.89 before margin. |
| 34 | Does the lab brief set a time limit for the live execution? | No. The lab brief (`AI Engineer Lab Exercise.pdf`, SIT, September 2026) states no time limit for the live execution. The 540 s demo deadline is a project assumption (research audit item U4), kept as a configurable safety net until SIT answers the slot-length question. | `docs/DEMO_DAY_RUNBOOK.md` (the unknowns line and the §5 clock) and `config/profiles/demo.yaml` (a comment on `deadline_seconds`) say the 540 s figure is an assumption pending SIT's answer. The value is unchanged; `--deadline` and the profile still change it. |

## 2026-10-03 (the owner, no answer key for the SIT PDF)

Recorded by the session 4 probe-findings worker from the owner's words, relayed by the planner.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 35 | Will the owner write a human answer key for the SIT Memory Platform PDF before the agent runs on it (#32)? | The owner, 2026-10-03, verbatim: "lets assume there is not answer key". | #32 is superseded. The SIT sample is a demo and rehearsal document, not an evaluation item, and the agent may run on it. Tier A rests on the three synthetic items (S-dev) and the two sealed held-out items (S-heldout). Real-dev lines A-6 and A-7, tasks T1 and T8, claim CL9 and hypothesis H9 are withdrawn (`eval/EVAL_PLAN.md` note under §1, `eval/prereg.yaml`, `eval/prereg_deviations.md` entry 12). The Tier A run count and cost are recomputed by the budget lane. |

## 2026-10-03 (review outputs, assess timing, MCP session rule)

Recorded by the session 4 final hub from the planner's brief.
Row 36 is the owner's word; rows 37 and 38 are SIT FABLE decisions for the owner.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 36 | What can a reader do with a finished review on the `dra ui` page? | The owner, 2026-10-03, verbatim: "yes", to the planner's shape for the review outputs: Download (one self-contained HTML file, plus `report.md` and `report.json`); Email (SMTP from the owner's Mac, the password from the environment, shown disabled with its reason when unconfigured); a session-only share link on the laptop's wifi address, with no login and no persistence. No hosted public link. | Built in `agent/sit_review_agent/ui/export.py`, `mail.py` and `share.py`, configured by `config/ui.yaml` (email off as shipped). The pasted-link fetch of `ui/fetch.py` is not part of the shape the owner answered; it has its own row, #39. |
| 37 | The assess shards start at about 2 s and research at about 126 s, so no shard sees external evidence. Is that acceptable before the interview? | SIT FABLE for the owner, 2026-10-03: yes. Refine applies the external evidence to the merged findings; this is the designed trade for the time slot, confirmed by the first with-tools run on the lab document (428 s, nothing cut). | Stays as is before the interview. A future variant may start a second assess pass after research. |
| 38 | How does the agent treat an MCP session the server has closed or left idle? | SIT FABLE for the owner, 2026-10-03: a closed session is reopened once and the call retried once; a session idle over 60 s is reopened before a call; a tool is disabled only after two genuine failures. | From the first with-tools run, where all five web searches failed on a session the server had closed. Implemented in `agent/sit_review_agent/tools/gateway.py` (`MCPToolGateway`, `PolicyToolGateway.TOOL_ERROR_LIMIT`), `config/tools.yaml` `session_idle_reopen_s: 60`; robustness scenario NET-06. |

## 2026-10-03 (SIT FABLE for the owner, the pasted link)

Recorded by the demo-day script worker from the planner's brief.
Row 36 covers the three outputs of a finished review only; this row covers the input side of the drop screen, which `agent/sit_review_agent/ui/fetch.py` had cited under #36.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 39 | How does the day's artefact reach the agent when SIT hands it over as a link rather than a file? | SIT FABLE for the owner, 2026-10-03: a pasted https link on the `dra ui` drop screen is the hand-over path for the day's artefact (the owner's words on 3 Oct 2026: "download link"). The server fetches it before the run starts, with these guards: https only, no user name or password in the link, a host whose every address is public (checked again on each redirect), the URL policy of `config/url_policy.yaml`, at most 50 MB, and a body that must be a PDF (`%PDF-`). | Built in `agent/sit_review_agent/ui/fetch.py` (`MAX_BYTES`, `MAX_REDIRECTS`), which now cites this row; the file is saved under `runs/<id>/ui/input/`, so the command the page shows names it. Known limit, from the module: DNS rebinding between the check and the fetch is not caught. A file dropped or given by USB stays the first path; `docs/DEMO_DAY_SCRIPT.md` names both. |

## 2026-10-03 (SIT FABLE for the owner, six assess shard groups)

Recorded by the planner on 3 Oct 2026, 22:18, under the owner's delegation of 3 Oct 2026 02:50.
This is the first tuning step that ruling (3) of row 31 named.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 40 | Stage 1 ended at 265.2 s and at 255 s in the two with-tools runs on the lab's 30-page document (`docs/live_runs/sit_sample_tools_1`, `docs/live_runs/sit_sample_ui_1`), past the 230 s tuning threshold of row 31. How many assess shard groups does the demo profile use? | SIT FABLE for the owner, 2026-10-03: six assess shard groups instead of four, as row 31 ruling (3) set out for a stage 1 above 230 s in rehearsal. The owner may reverse this. | `config/agent.yaml` holds six groups since 9e6c2fb on `s4/runfix2`, with the config tests green; the next rehearsal with the UI and the tools on the lab document checks that stage 1 ends at or under 230 s (`extra.timing.stages` in the manifest). |

## 2026-10-03 (the owner, the v2 look of the review page)

Recorded by the UI v2 verifier from the planner's brief.
Row 40 is not in this file at the time of writing; the number 41 is the one the brief assigned.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 41 | Is the v2 mockup of the review page (the DBSearch idiom: a dark rail, a top bar, a composer at the foot of the review) the look to build? | The owner, 2026-10-03, on the v2 mockup (`docs/design/ui_mockup_v2/frame_1_review.png`, `frame_2_run.png`, `frame_3_finished.png`): "ok it looks good". | The v2 look is the review UI; the v1 look is not kept. Built in `agent/sit_review_agent/ui/static/` (`index.html`, `app.css`, `tokens.css`, `app.js`) and merged with the Delta tab fixes on `s4/final2`; the merged page is shot in `docs/design/ui_mockup_v2/merged_1_review.png`, `merged_2_finished.png` and `merged_3_delta.png`. |

## 2026-10-03 (the owner, the LangGraph comparison)

Recorded by the verifier of the LangGraph variant from the planner's brief.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 42 | Should the agent's orchestrator also be built on LangGraph, to compare it with the custom loop? | The owner, 2026-10-03, his words: "can we spawn another fable agent to work on langraph? ... let it run and compare it" and "no need to budget . and just work normally, no rush to complete, just make sure its a job well done. then we can effectively compare both custom and langraph". | The variant lives behind `--orchestrator langgraph` (`agent/sit_review_agent/orchestrator_langgraph/`, optional extra `[langgraph]`); the custom loop stays the product; the comparison is `docs/COMPARISON_LANGGRAPH.md` on one paired document (payments). The five further paired runs (the custom loop on payments again, both arms on clinical and on lakehouse) were refused to the worker by the permission classifier and are for the owner or the next session to run (`docs/transcripts/session4/langgraph_verifier.md`). |

## 2026-10-04 (the owner, the export bundle)

Recorded by the export-bundle worker from the planner's brief; the owner delegated the shot calling to the planner on 2026-10-03 02:50.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 43 | The owner, 2026-10-04 about 12:10, on "Download review" after his rehearsal: "its just ONE page... im wondering if can break into either different documents or... different sidebar? ... or both! so u download to get ALL documents, so maybe 7-8 documents depending on each task or smth? and if they want a SINGLE .html, they can click sidebar as well." | SIT FABLE for the owner, 2026-10-04 12:25: both. A: the single HTML (`export.html`) gets a left sidebar of 8 parts (Summary and verdict, Strengths, Risks, Gaps, Ambiguities and assumptions, What to do, Open items, Traceability), one part in view at a time with the title and the verdict on top, "All sections" first, each part with a "this section only" link; inline CSS and one fixed inline script, and without script every section shows. B: each part is also a standalone file `01_summary.html` ... `08_traceability.html`, cut from the same rendered report.md. C: `GET /runs/<id>/export.zip` (and `export.html?download=1`, the Download control) returns the bundle of `index.html`, the eight parts, `report.md` and `report.json`; `GET /runs/<id>/export/<part>` returns one part. | Built in `agent/sit_review_agent/ui/export.py` (`GROUPS`, `split_report`, `export_part`, `export_zip`), the export route in `ui/server.py` and `ui/static/export.css`; the split is at the report's own `## ` headings, so the export still says nothing report.md does not; a heading outside the map joins the part of the nearest named heading before it. Email still attaches the single sidebar page. Tests in `tests/test_ui_export_bundle.py`; the browser check in `docs/transcripts/session6/export-bundle.md`. |
| 44 | After his first rehearsal in the review UI (4 Oct 2026, about 11:55) he asked what Stop does, why the clock is not per second, whether he can see what each assess is doing or look into the backend or logs, why a run cuts at 04:25, and for more visibility on each stage. What changes in the page? | The planner (shot calling delegated to it on 3 Oct 02:50) ruled four changes, built one commit each on branch s4/ui-live: (A) a confirm step on Stop with one sentence from the code (SIGINT, exit 130 from the CLI, state.json kept, no report, dra resume <run_id>); (B) a head clock that ticks once a second as the record's last run clock plus the wall seconds since that event arrived, labelled as such, the recorded limits as markers on one whole-run axis, and a fired limit stated in plain words with the kept counts; (C) each stage row expands to its model calls with the latest call_status fields and the draft items streamed so far, titles only; (D) a Logs panel in the rail tailing progress.log through a new read-only route. Recorded by SIT FABLE for the owner, 2026-10-04 12:37. | The page keeps its honesty contract in a new form: the only browser-clock read adds the seconds since the last event and stops with the stream, no completion estimate or percentage is ever shown, every limit comes from the run_started record, and no model text reaches the page. The honesty tests were rewritten for that contract, not deleted. |
| 45 | The owner, 2026-10-04 15:30, on the run page: "since it's an interview and they are testing me and I'm studying the architecture, I too, need to be able to explain it as to what is happening as it runs, so I need to create visibility". | SIT FABLE for the owner, 2026-10-04 15:47 (shot calling delegated to the planner on 3 Oct 02:50): a "What is happening" panel above the stage rows of the open run's page, labelled "explanation, not the record". For the current stage (every member in flight during stage 1, the finished run's paragraph at the end) it shows two to four plain sentences on what the agent is doing and why, with the run's own numbers filled in from its event stream; a Why control on each stage row, and on the limits axis, opens the same entry in place. Ten entries: ingest, understand, plan, assess, research, refine, verify, report, the stage limits and the finished run. | The text is the `#explain-map` JSON in `ui/static/index.html`, written from `docs/ARCHITECTURE.md` and the code each entry names in its "From" line; app.js `FACTS` fills each `{name}` from fields the reducer keeps (`recordFacts`), and a sentence whose names are not in the stream yet gives way to its alternative or is left out, so no empty or invented number is shown and app.js gains no numeric literal. `tests/test_ui_explain.py` pins every name to FACTS and the schema, every cited decision to its row here, every named file and symbol to the repository, and drives the panel from assess to refine to finished in Chromium. Worker note: `docs/transcripts/session6/explain-panel.md`. |
| 46 | How many documents and runs does the evaluation use? | The owner, 2026-10-04 22:40, with the planner's shaping: plan D, more documents and fewer runs per document (his words: "less runs, but more variants document wise"). Ten keyed documents (the three synthetic, the two held-out, the five new synthetic); one full-agent run and one single-call baseline per document, all at effort medium; five v2 re-assessments; two extra agent runs on two documents for run-to-run variance; one low and one high effort run on one document. The five new items are `iot_fleet`, `consent_service`, `hospital_scheduling`, `ledger_migration` and `exam_platform` under `eval/synthetic/`. | Replaces the run counts of plans A to C; recorded as `eval/prereg_deviations.md` entry 13, and the five items are registered in `spec/convert_answer_keys.py`, `eval/build_pdfs.py` and the S-dev items of `eval/prereg.yaml`. The document is the unit of analysis because between-document variance dominates. Scores stay exploratory until the keys are signed (#26). |

## 2026-10-05 (the owner, a longer demo deadline)

Recorded by the demo-deadline worker on branch `s4/demo-deadline-15` from the planner's brief.

| # | Question | Decision | Consequence |
|---|---|---|---|
| 47 | How long is the demo profile's deadline? His document-only run `ui-261005-125426-adaa` (demo profile, `--no-tools`, 540 s) ended understand at 02:16 and the six assess shards by 03:46, then refine was cut by its 465 s limit at 07:45, so the report (08:48, 30 findings, at least $5.71) shipped without the global refine pass: no duplicates merged, no registry decisions linked. A run with research on would be tighter still. | The owner, 5 Oct 2026 21:15, his words: "longer than 9 mins". The demo profile's deadline is 900 s (15 minutes). The three stage limits are the design's 265 / 465 / 530 s scaled by 900/540 as `llm/runtime.py` `effective_stage_limits` computes it: 441 / 775 / 883 s. The two reserves keep the split the limits encode: verify and verdict 125 s (900 - 775), refine 334 s (775 - 441). This supersedes the 540 s assumption of #34; the brief still sets no limit. | `config/profiles/demo.yaml`, the runbook §5 clock, the demo-day script, `docs/EXPLAIN_AS_IT_RUNS.md`, `docs/ARCHITECTURE.md`, `docs/LIMITATIONS.md` and the tests that pin the profile say 900 s. Still UNMEASURED at 900 s. `--deadline 540` (or 9 in the Review form's new Deadline field) gives the old stage limits back (264 / 465 / 529 s) but not the old clock: the reserves do not scale, so research's own deadline rule then ends research by run time 81 s, and a 9-minute run with tools gets no research; the form says so before the run starts. The evaluated agent is this profile (`eval/prereg.yaml` `agent_under_test.effort_per_stage.profile`), so the change is recorded as `eval/prereg_deviations.md` entry 15. |
