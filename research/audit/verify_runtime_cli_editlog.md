# Runtime and demo-CLI integration: edit log (session 4, 2026-10-03)

Scope: the six integration items left open at the end of session 3 (`docs/HANDOVER_FULL.md` §10), and the check of the runtime policies (W1) and the demo CLI (W2) together.
Branch `s4/integration`, from `0caa581`.
Offline apart from two Haiku calls for item 6 (CLI estimate $0.0234 in total).
No Opus call, no live agent run, no scoring or grading run, nothing against the SIT MCP hosts, nothing under `eval/blind/` opened.
No prompt file changed, so `prompts/PROMPTS.lock` and both harness prompt locks are unchanged.
State at the end: `ruff check agent harness tests` clean, `pytest -q` 1011 passed and 0 skipped, `sit-review selftest` passed, `make smoke` and `make test` exit 0, also in a fresh clone with its own virtualenv.

## 1. Edits by item

### Item 1: the `not_assessed` verdict (commit `e8a6c12`, interface change)

| File | Change | Why |
|---|---|---|
| `spec/finding.schema.json` | `VerdictLabel` gains `not_assessed`. `Verdict`: with that label, confidence is 0 and `conditions` and `per_objective` are empty. A `per_objective` label can never be `not_assessed`. `Review`: with that verdict, `findings` and `sound_areas` are empty and `research_log.degradations` has at least one entry | The placeholder `not_fit` at confidence 0 read as a judgement of the design |
| `spec/taxonomy.yaml` | `verdicts` gains `not_assessed` with its definition and a comment that code sets it | Enum registry |
| `spec/validate_examples.py`, `spec/README.md` | A not-assessed example Review, five new negative cases and one adversarial accept case; README counts 32 -> 37 negative and 28 -> 29 adversarial, C9 text | The validator and its cases |
| `agent/sit_review_agent/models.py` | `VerdictLabel.NOT_ASSESSED`; validators on `Verdict`, `ObjectiveVerdict` and `Review` that mirror the schema rules | Frozen file: changed together with the schema |
| `agent/sit_review_agent/llm/outputs.py` | New `AssessedVerdictLabel` (fit, fit_with_conditions, not_fit); `VerdictDraft.label` and `ObjectiveVerdictDraft.label` use it | The model cannot choose `not_assessed`: the LLM-facing schema does not offer it and a draft that carries it fails validation |
| `agent/sit_review_agent/phases/report.py` | `not_assessed_verdict(reason)` returns the new label; new `assessment_missing()`; the report phase skips the verdict call when there is no assessment; `settle_report_output` converts the draft label | Set by code on the degraded paths only |
| `agent/sit_review_agent/report/render.py` | `not_assessed()` reads the label; `verdict_label_text()` names the reason | Report rendering |
| `agent/sit_review_agent/phases/assess.py`, `agent/README.md` | Docstring and "Runtime policies" text | Documentation |
| `harness/sit_eval/grader/verify.py`, `grader/fake.py` | One constant `FITNESS_VERDICT_LABELS`; `not_assessed` is not in it | Gate G4: a not-assessed review has no explicit verdict, so D2 is capped at 0 |
| `harness/sit_eval/scoring.py`, `schemas/scores.schema.json`, `aggregate.py` | `inputs.verdict_label` in `scores.json`; a warning on a not-assessed review in `score` and in `aggregate` | The run is scored as it stands, intention-to-treat, and flagged |
| `tests/test_not_assessed_verdict.py` (new, 14 tests), `tests/test_runtime_policies.py`, `tests/robustness/test_robustness_scenarios.py`, `tests/robustness/robustness_coverage.py`, `tests/robustness/README.md` | New tests; LLM-05 and LLM-06 expectations; registry and README text | Tests |
| `agent/sit_review_agent/kruns.py`, `tests/test_cli_kruns.py` (commit `e087db4`) | Verdict agreement is over fitness verdicts; "not assessed N" in the summary | A metric that reads the verdict |

Not changed, on purpose: `prompts/report.md` (the model is still offered three labels), the grader's `pass_b_output.schema.json` (`verdict_extracted.label` is the grader model's own reading and already has `null`), `harness/sit_eval/loaders.py` (it validates with the same schema and model).

### Item 2: eval-derived hosts (commit `20a8947`)

| File | Change |
|---|---|
| `config/url_policy.yaml` | Removed `stripe.com` and `confluent.io` from `vendor_docs` and `stripe.com/blog` from `secondary`; the comment explains the rule without naming the hosts |
| `scripts/leakage_grep.py` | The two hosts join `KNOWN_SAMPLE_STRINGS`; the `stripe` entry leaves `DEFAULT_RESOLVED` |
| `tests/test_runtime_policies.py`, `tests/test_runtime_leakage.py` | Pin the removal and the general rules that still class such pages |

`tools/sources.py` holds no host list any more (W1 moved them to the config), so it needed no change.

Sweep for other hosts present only because a synthetic item names them.
Method: every authority-list entry's name was searched in the three synthetic items (design v1 and v2, both key files).
40 entries match by name.
Almost all are general by any reading: standards bodies (ISO, IEC, IETF, NIST, IEEE, WHO), the hyperscalers and their documentation, PostgreSQL, Redis, Kubernetes, Python, GitHub, ACM, DOI.
Named by one item only and not a standards body or hyperscaler: `pdpc.gov.sg` (clinical, 12 mentions), `opentelemetry.io` (payments, 2), `databricks.com` (lakehouse, 2), `apache.org` (lakehouse, 32).
None of these was removed: each sits in a list of peers that no item names (`imda.gov.sg`, `csa.gov.sg` and `mas.gov.sg` beside `pdpc.gov.sg`; `snowflake.com` beside `databricks.com`), so the evidence that an item caused the entry is not clear-cut.
`confluent.io` is named by no item; the payments item uses Kafka, and `kafka.apache.org` was already removed as a sample-stack host.

### Item 3: runbook (commit `2c416b0`)

| Section | Change | Checked against |
|---|---|---|
| Header | `make smoke` and `make test` are built | `make smoke`, 9.9 s |
| §4 intro | Short rerun is `--profile demo --deadline 300`; what a 300 s deadline does with each set of reserves | `sit-review run --help`; a run with `--deadline 300` |
| §4.1 `agent.yaml` | Line 5 `research: high`, line 10 `max_tokens: 128000` | `config/agent.yaml` |
| §4.1 `tools.yaml` | Line 12 `enabled: false`, line 17 `url_policy: url_policy.yaml` | `config/tools.yaml` |
| §4.1 note, §4.2 row 4 | The demo profile's values win over the pinned effort and deadline lines; edit `config/profiles/demo.yaml` lines 19-24 or 27 for a demo run | `effective_config.json` of a `--profile demo` run |
| §5 | `--profile demo` instead of `--deadline 540`; the reserve wording; timeline rows from the profile's limits; what a cut assess produces | `config/profiles/demo.yaml`; a demo-profile run whose assess is cut (robustness LLM-05) |
| §5.1 | The list follows the real section numbers; the made-up `F-07` / `E-004` example is replaced by real output | `dra explain FND-001` on an offline run |
| §9 | Makefile row marked built; `hooks` not built | `Makefile` |

`tests/test_config_layout.py` now compares each §4.1 listing with its config file line by line, and pins the `demo.yaml` lines and the §5 statements the runbook makes.

Timeline arithmetic (session clock; the run starts at 0:30):
research ends by run time 540 - 120 - 200 = 220 s, which is 0:30 + 3:40 = 4:10;
model calls before verify are cut at 540 - 120 = 420 s, which is 0:30 + 7:00 = 7:30;
the run ends by 540 s, which is 0:30 + 9:00 = 9:30.

### Item 4: Makefile (commit `719f485`)

`Makefile` (new): `smoke`, `test`, `lint`, `check-env`, `help`.
`README.md`: the "Reproducing checks" block names `make smoke` and `make test`.
`PYTHON` is the repository's `.venv/bin/python` when that exists, else `python3` on PATH; no absolute path is written in the file.

### Item 5: `eval/EVAL_PLAN.md` timing (commit `329247f`)

Three places changed: the "Run time" note, the wall-time line under the instruments table, and the E1 row of the schedule.
`config/stop_rules.yaml`: one comment line that quoted the withdrawn estimate.

Sources (all measured on 2026-10-02):
`docs/HANDOVER_FULL.md` §8 for the agent run;
`docs/live_runs/live_cc_opus_payments_v1/eval_pilot2_bounded/scores.json` (`elapsed_s`) and `judge_calls.jsonl` (`elapsed_s` per call) for scoring;
`docs/live_runs/live_cc_opus_payments_v1/grade_pilot/grader_calls.jsonl` (`elapsed_s` per call) for grading.

Arithmetic:

| Figure | Calculation | Result |
|---|---|---|
| Successful work of the agent run | 2 + 158 + 158 + 0 + 520 + 33 + 88 | 959 s = 15.98 min |
| Wall time of the agent run | 2 + 158 + 158 + 2,933 + 33 + 88 | 3,372 s = 56.2 min |
| Time lost to the four killed attempts | 2,933 - 520 | 2,413 s |
| Assess call | 520 / 60 | 8.67 min |
| Scoring wall time, one review | `elapsed_s` | 245.61 s = 4.09 min |
| Scoring call time | sum of 98 `elapsed_s` | 943.7 s, 9.63 s per call |
| Grading, one review | 158.91 + 193.54 + 91.80 + 105.04 | 549.29 s = 9.15 min |
| Instruments per scored and graded run | 245.61 + 549.29 | 794.90 s = 13.25 min |
| Runs by condition | FULL 16+9+9+6+18+3+3+12+8; B0 9+9+6; B0-$ 9+6; A5 9 | 84, 24, 15, 9; sum 132 |
| FULL-shaped and single-call runs | 84 + 9; 24 + 15 | 93; 39 |
| Floor, 132 runs | 93 x 959 + 39 x 520 = 89,187 + 20,280 | 109,467 s = 30.41 h |
| Floor, laptop wall time | 30.41 / 3; 30.41 / 2 | 10.14 h; 15.20 h |
| Cap, 132 runs | 132 x 3,600 | 475,200 s = 132 h; 44 h and 66 h at 3 and 2 in parallel |
| Scoring, 101 matched runs | 101 x 245.61 | 24,806.6 s = 6.89 h |
| Grading, 101 reviews | 101 x 549.29 | 55,478.3 s = 15.41 h |
| E1 (A-3 and A-5): FULL-shaped and single-call | 9 + 9 + 18; 9 + 9 | 36; 18 |
| E1 floor | 36 x 959 + 18 x 520 = 34,524 + 9,360 | 43,884 s = 12.19 h; 4.06 h and 6.09 h at 3 and 2 in parallel |
| E1 cap | 54 x 3,600 | 54 h; 18 h and 27 h at 3 and 2 in parallel |

What the plan now says is unmeasured: research, refine, the single-call baselines (B0, B0-$; the 520 s assess call is used as the nearest analogue), the Sonnet control grader, and running 2-3 runs in parallel on the `claude -p` backend.

`docs/BUDGET.md` was not edited.
Stale lines seen in it: line 11 and line 18 (per-run $2.18, B0 $0.63 and the rest; the measured run recorded $3.68 for the calls that completed); lines 66-69 and 131-134 (matcher $1.05 per run and grader $0.57 per review, in batch or on a second provider; measured $10.36 and $4.85 through synchronous `claude -p`, and the second provider was dropped by owner decision #16); line 84 (says `research` runs at `medium`; the config says `high`); line 86 (440 runs x 8-10 minutes = 60-75 hours); lines 138-146 (totals $564-639 and the $650 approval figure built on those prices); line 142 (the $3.24 pilot checkpoint).
The cost lines of `eval/EVAL_PLAN.md` (the cost basis note, the run matrix USD column, the instruments table, Tier B) carry the same estimates and were left for the BUDGET rework; the plan now says so.

### Item 6: `max_tokens` 128000 (commit `ab4d0b2`)

| File | Change |
|---|---|
| `config/agent.yaml` | Line 10 `max_tokens: 128000`; a comment below the pinned lines says how each backend applies it and what is not verified |
| `agent/sit_review_agent/phases/_model_calls.py` | The one truncation retry also runs when the configured value is already 128000 (at the same cap) |
| `agent/sit_review_agent/llm/claude_code.py` | The CLI's output-cap error is typed `LLMTruncatedError` and not retried by the gateway |
| `tests/test_llm_phases.py`, `tests/test_claude_code_gateway.py`, `tests/test_config.py` | New tests; the config anchor string |
| `tests/robustness/faults/LLM-07.yaml`, `robustness_coverage.py`, `README.md`; `agent/README.md` | Wording of the truncation retry; the output-cap policy |

Places that assumed 64000: `config/agent.yaml` line 10, the runbook listing, the anchor string in `tests/test_config.py`.
Places that already assumed 128000: `config.py` (`le=128000`), `_model_calls.MAX_OUTPUT_TOKENS`, `tests/test_anthropic_gateway.py`.
Profiles: `config/profiles/demo.yaml` sets no `max_tokens`, so the demo inherits 128000.
LLM-10 estimate: `llm/runtime.py` counts input only, against 80 % of the context window.
For every supported model the window is 1,000,000 tokens, so the limit is 800,000 and 800,000 + 128,000 = 928,000 <= 1,000,000.
A test pins that sum.

How the `claude -p` backend applies the value, read from the code and checked with two Haiku calls through `ClaudeCodeGateway` (Claude Code 2.1.287):
the gateway sets `CLAUDE_CODE_MAX_OUTPUT_TOKENS=<max_tokens>` in the child environment.
Call 1, cap 256, a request for a 1,200-word essay: the CLI answered "API Error: Claude's response exceeded the 256 output token maximum", after 4 turns and 1,024 output tokens, CLI estimate $0.0157.
So the cap is applied.
Call 2, cap 128000, a one-word answer: accepted, `end_turn`, CLI estimate $0.0077.
So a value above Haiku's own limit does not fail the call.

## 2. Defects found, each with a regression test

| # | Defect | Fix | Test |
|---|---|---|---|
| D1 | A run that produced no assessment reported `not_fit` at confidence 0; the grader's G4 gate counted that as an explicit fitness verdict | Item 1 | `test_harness_loads_flags_and_does_not_credit_a_not_assessed_review`, `test_not_assessed_verdict_carries_no_judgement` |
| D2 | When the model declined the assess call twice, the report phase still asked the model for a verdict, on a review with no findings; the scripted or live model could answer `fit` | `assessment_missing()` covers the declined path: no verdict call, verdict `not_assessed` | `test_report_sets_not_assessed_in_code_without_a_verdict_call[declined]`; robustness LLM-06 |
| D3 | `claude -p` reports an answer that hit the output cap as an error result, not as `stop_reason: max_tokens`. The gateway typed it `LLMUnavailableError` and retried it `llm.max_retries` (4) times at the same cap, each retry repeating the CLI's own recovery turns | Typed `LLMTruncatedError`, not retried by the gateway | `test_cli_output_cap_error_is_a_truncation_not_an_outage` (uses the message captured from the CLI) |
| D4 | With `max_tokens` at 128000 the truncation retry never ran (`max_tokens >= 128000` skipped it), so the first truncation ended the stage with exit 4 | The one retry runs at the cap | `test_truncation_retry_at_and_below_the_output_cap`; robustness LLM-07 |
| D5 | A criterion whose findings verify dropped kept outcome `findings` with no ID: `report.md` showed "findings / -" and `dra coverage` showed `ok` (checked, no issue) in every section | verify notes the dropped count on the row; `dra coverage` shows `?` and says why | `test_criterion_whose_findings_were_not_verified_is_not_shown_as_clear` |
| D6 | `dra coverage` listed the criteria of a not-assessed run as "not applicable" | The criteria line shows the row's "not assessed: ..." note | `test_coverage_of_a_run_with_no_assessment_says_not_assessed` |
| D7 | `--deadline` shorter than the reserves it runs with gave an unassessed or document-only report with no hint why; the runbook's own short rerun (`--deadline 300`) did this against the default reserves | One WARN line at the start of the run (`llm.runtime.deadline_warnings`) | `test_a_deadline_that_does_not_fit_its_reserves_is_announced`, `test_demo_profile_and_a_deadline_that_does_not_fit_the_reserves` |
| D8 | The runbook's §4.1 listings had drifted from the config files in four lines; the layout test compared prefixes only | Listings corrected; the test compares whole lines | `test_runbook_listing_equals_the_config_file` |
| D9 | The k-run summary counted `not_assessed` as a verdict, so a group of unassessed runs showed "verdict agreement 1.00" | Agreement is over fitness verdicts; unassessed runs are counted separately | `test_not_assessed_runs_are_not_a_verdict_in_the_group_summary` |
| D10 | `stripe` was excused in the leakage gate's default allow-list, so the gate could not catch the host coming back | Entry removed; hosts added to the known strings | `test_known_sample_hosts_and_blind_refusal`, `test_cli_passes_on_the_repository_and_is_never_imported_by_the_agent` |

## 3. Integration check of W1 and W2

Run offline with the real console script and a copied config (`--transport fake`, the selftest cassettes), and in process with the robustness harness on a `FakeClock`.

| Path | Result |
|---|---|
| `review --profile demo --k 2` | Exit 0; deadline 540, reserves 120 and 200, effort medium (research low) in `effective_config.json`; profile in `extra.config.cli_args`; `k_index` 1 and 2; group manifest written |
| `--profile demo --deadline 300` | The CLI value wins (300); reserves from the profile; the new warning is printed |
| Unknown profile; `--k 0`; `--k` with `--plan-only`; `--k` with `--resume` | Exit 2 each, one-line error, no traceback |
| `coverage --run`, positional, `--json`, `--depth 0` | Exit 0; defects D5 and D6 found and fixed |
| `coverage` on the committed live run | Exit 0 from `report.json` and the table in `report.md` |
| `explain FND-001`; an unknown ID | Exit 0; exit 2 with a one-line error |
| `replay` of an offline run | Exit 0, 9 model calls and 2 tool calls replayed, report equal to the recording |
| `replay` of the committed live run | Exit 2: "it lacks llm.jsonl (the recorded model outputs); state.json or checkpoints/" |
| Demo profile, assess hangs (LLM-05) | Assess cut at 420 s of virtual time, not retried; refine skipped; verdict `not_assessed`; report headed "not assessed (out of time before assessment)"; `replay` of that run reproduces the report |
| Demo profile, assess declined twice (LLM-06) | Verdict `not_assessed`, no verdict call; `replay` reproduces the report |

Seams reported by the implementers:
the committed live run cannot be replayed (confirmed; the refusal is clear, and the next demo measurement run is to be committed with its `llm.jsonl`);
`not_fit` at confidence 0 (item 1);
runbook §5 and §4.1 (item 3);
`eval/EVAL_PLAN.md` and `docs/BUDGET.md` timing (item 5; BUDGET listed only);
the two hosts left in the vendor list (item 2).

## 4. Mutation tests

Each guard was removed or reverted in the working tree after its commit, the named tests were run, and the file was restored byte for byte from a copy.
All 21 mutations were caught.

| # | Mutation | Caught by |
|---|---|---|
| M1 | `not_assessed_verdict` returns `not_fit` again | `test_not_assessed_verdict_carries_no_judgement` |
| M2 | `VerdictDraft.label` takes `VerdictLabel` (the model may choose `not_assessed`) | `test_no_llm_facing_schema_offers_not_assessed` |
| M3 | The declined path is no longer "assessment missing" | `test_report_sets_not_assessed_in_code_without_a_verdict_call[declined]` |
| M4 | Schema: a not-assessed review may carry findings | `test_review_rules_for_a_not_assessed_verdict` |
| M5 | Model: `Verdict` accepts `not_assessed` with a confidence | `test_model_and_schema_reject_a_not_assessed_verdict_with_a_judgement` |
| M6 | Grader counts `not_assessed` as a fitness verdict | `test_harness_loads_flags_and_does_not_credit_a_not_assessed_review` |
| M7 | Schema: a per-objective label may be `not_assessed` | `test_per_objective_label_can_never_be_not_assessed` |
| M8 | `stripe.com` back in `vendor_docs` | `test_authority_hosts_come_from_config_without_the_sample_stack` |
| M9 | `confluent.io` back in `vendor_docs` | `test_cli_passes_on_the_repository_and_is_never_imported_by_the_agent` (the leakage gate fails) |
| M10 | The leakage gate excuses `stripe` again | `test_known_sample_hosts_and_blind_refusal` |
| M11 | The CLI's output-cap error is an outage again | `test_cli_output_cap_error_is_a_truncation_not_an_outage` |
| M12 | No truncation retry at the cap | `test_truncation_retried_with_more_tokens` |
| M13 | `max_tokens` back to 64000 | `test_configured_output_cap_is_the_model_maximum_and_fits_the_context_margin` |
| M14 | Coverage shows `ok` for a criterion whose findings were dropped | `test_criterion_whose_findings_were_not_verified_is_not_shown_as_clear` |
| M15 | verify does not note the findings it dropped | the same test |
| M16 | No warning for a deadline shorter than its reserves | `test_a_deadline_that_does_not_fit_its_reserves_is_announced` |
| M17 | Runbook listing drifts from `config/agent.yaml` | `test_runbook_listing_equals_the_config_file[agent.yaml]` |
| M18 | Runbook §5 back to `--deadline 540` | `test_demo_profile_lines_named_by_the_runbook` |
| M19 | Unassessed criteria listed as "not applicable" | `test_coverage_of_a_run_with_no_assessment_says_not_assessed` |
| M20 | The orchestrator does not emit the deadline warning | `test_demo_profile_and_a_deadline_that_does_not_fit_the_reserves` |
| M21 | `not_assessed` is the modal verdict of a k-run group again | `test_not_assessed_runs_are_not_a_verdict_in_the_group_summary` |

The leakage gate also caught one of my own edits while I worked: the first wording of the `config/url_policy.yaml` comment named the removed hosts, and `scripts/leakage_grep.py` failed on it.

## 5. Judgement calls

1. **Declined assess is "not assessed" too.**
   The brief named the deadline paths; the same reasoning applies when the model declines the assess call twice, and the old behaviour there (a model verdict on no findings) was worse than the placeholder.
   Consistent with the runtime-policy decision recorded for LLM-05 ("no invented verdict on an unassessed design", `research/audit/runtime_policies_editlog.md` item 12) and with owner decision #13 (robustness policies per coordinator recommendation).
2. **`not_assessed` requires no findings, no sound areas and a degradation, in the schema.**
   Stricter than asked, so that the label cannot be combined with a partial result.
3. **The interface change is one commit that contains the frozen-file changes and the adaptation of every caller.**
   The freeze rule asks for the change "alone, in its own PR"; this repository has no PRs in flight and one branch, so the commit message carries the interface-change note and the caller list.
4. **Truncation at the cap: one retry at the same cap.**
   With `max_tokens` at the model maximum nothing wider exists.
   Not retrying would turn every truncation into exit 4; retrying keeps the LLM-07 contract (one retry, never a repaired object), and the run deadline bounds it.
   On the `claude -p` backend each attempt can include the CLI's own recovery turns, so a truncation there is expensive; the deadline, not the retry count, is what limits it.
5. **No further hosts removed in the sweep** (see item 2).
6. **`dra coverage` marks a criterion with dropped findings `?` in every section**, because the dropped finding's anchor is exactly what could not be verified, so no section can be named.
7. **A deadline that does not fit its reserves gets a warning, not an error.**
   The run still produces its disclosed, degraded report, as designed.
8. **k-run agreement keeps completed runs as the denominator**, so an unassessed run lowers the agreement instead of dropping out (intention-to-treat).
9. **`eval/EVAL_PLAN.md` gives a floor and a cap, not a central figure**, because research and refine have not been timed; a central figure would be a new estimate.
10. **The robustness results file was regenerated** with the documented command at the last code commit (`e087db4`), not edited by hand.

## 6. Not verified

- That Opus 5.5 through `claude -p` can emit more than 64,000 tokens in one call with the cap at 128000.
  No Opus call was made; the CLI may clamp the value per model.
- The `anthropic_api` backend with `max_tokens` 128000 (never run live).
- How many recovery turns the CLI makes at a large cap, and what they cost; 4 turns were seen at a cap of 256 on Haiku.
- Every timing in the demo profile and in the runbook §5 timeline (the profile says UNMEASURED; the demo measurement run is next).
- Research and refine run times, the single-call baselines, the Sonnet control grader, and 2-3 runs in parallel on `claude -p` (`eval/EVAL_PLAN.md` says so).
- `dra replay` on a live run: only fixture runs and fault-injected runs were replayed.
- Whether a not-assessed review is graded as intended by the live grader (the fake grader and the code gate were checked).

## 7. Seen and not changed

- `README.md` tells the reader to run `python3 spec/validate_examples.py` and `python3 spec/convert_answer_keys.py` with no tier; both then read the answer keys under `eval/blind/`, which `docs/SEALING.md` §6 rule 1 forbids until sealing. I ran the spec self-test with the blind directory filtered out (the same filter `convert_answer_keys.py --tier synthetic` uses). The keys worker's upstream commit `10ceb5a` (not in this branch) makes the validator skip `eval/blind/` unless `--include-blind` is given, which settles this point once the branches are merged.
- `README.md` status paragraph still says 865 offline tests (dated 2026-10-02).
- `docs/DEMO_DAY_RUNBOOK.md` header paragraph ("before the agent code exists") and §2 (`uv sync --frozen --offline`; the repository has no `uv.lock`) are older than the build.
- `docs/HANDOVER_FULL.md` §10 lists these six items as in flight.
- The runbook's §5 walk-through of one finding now has 30 s of the 10-minute slot in the worst case; the rehearsal should set the reserves from measured times.
- `docs/BUDGET.md` and the cost lines of `eval/EVAL_PLAN.md` (see item 5).

## Session 4 verifier

Fresh-context Opus verifier, 2026-10-03.
Merged `origin/claude/happy-darwin-d0bl94` (2c7fba3) into `s4/integration` with a merge commit (3ba6786); no conflict.
Every check below ran on the merged tree.
Full report: `docs/transcripts/session4/integration_verifier.md`.

### Edits

| File | Edit | Regression test |
|---|---|---|
| `tests/robustness/test_robustness_regressions.py` | New `test_a_stage_that_truncates_twice_never_ends_in_a_silent_success` (understand, assess, refine): exactly two calls, no third at the same cap, no traceback, and either a typed resumable exit 3 with no report or a report that discloses the truncation (an unassessed one being `not_assessed`) | itself; mutation "a second retry at the same cap" (`if widened and k >= 2`) fails all three cases |
| `agent/README.md` (Output cap) | "a second truncation ends the stage (exit 4)" was wrong: the run ends with a typed, resumable exit 3, `failure.json` names the stage, and no report or partial report is written (measured offline for understand, assess and refine). Added the known limitation the planner asked for: a second truncation is not recovered by splitting the stage, and `sit-review resume` repeats the same call at the same cap | the test above |
| `tests/test_runtime_policies.py` | New `test_deadline_warning_boundary_is_one_model_attempt`: mutation V4 (`before_verify - a < min_attempt_s` weakened to `< 0`) survived every existing test | itself; V4 now caught |
| `docs/DEMO_DAY_RUNBOOK.md` §4.1, §4.2, §8, §9 | Source paths that do not exist: `agent/stop_rules.py`, `agent/states.py`, `agent/templates/report.md.j2` now point under `agent/sit_review_agent/`; the stop-rule signature is `(state, config, elapsed_s) -> StopDecision(stop, code, detail)`, not `(stop: bool, reason: str)`; the §8 talking point cited `docs/ARCHITECTURE.md`, which does not exist, and now cites the `agent/README.md` sections that cover the same ground | `tests/test_config_layout.py::test_runbook_source_paths_exist` (fails with the old path restored) |
| `eval/EVAL_PLAN.md` E1 row | The row the builder rewrote kept two em dash cells; they read `none`, as in rows B6 and E4 | none (text) |
| `docs/USER_DECISIONS.md` | Rows #24 and #25, "SIT FABLE for the owner, 2026-10-03" | none (record) |
| `eval/blind/ACCESS_LOG.md` | One appended line recording ruling #24 (nothing else in `eval/blind/` was listed or opened) | none (record) |
| `eval/prereg_deviations.md` | Entry 9 (the builder's proposed entry "8", renumbered), corrected: the per-protocol exclusion is only a warning (no code computes that view); G4 false caps D2 at 0 and so also fails G1; the k-run agreement keeps not-assessed runs in the denominator; decided by the session 3 coordinator and confirmed by #25 | none (record) |

### Corrections to the builder's records

- The builder's §2 D4 and §5 item 2 say a truncation without the retry "ended the stage with exit 4". A truncation that escapes the phase ends the run with exit 3 (resumable), as measured above.
- Builder's report "1011 passed" was before the merge; on the merged tree the suite gave 1018 passed before my tests and 1023 after.

### Hosts kept, with the planner's test (`git log -S`)

All four kept hosts and the two removed vendor hosts entered the authority list in the same commit, `7885679` (2026-10-02 11:01 UTC, "WIP: workstreams B/C in progress", in `agent/sit_review_agent/tools/sources.py`), about four hours after the first synthetic items were committed (`35656ac`, 06:57 UTC).
So the date alone does not separate them, and each host was judged by the planner's principle.

- `databricks.com`: kept. It is one of about 45 hosts in a general `vendor_docs` list (official vendor and project documentation), next to a peer of the same kind, `snowflake.com`, that no evaluation item mentions. One synthetic item names Databricks Unity Catalog once, as a row of an alternatives table (`research_lakehouse/design_v1.md`, `design_v2.md`); no answer key mentions it. The leakage gate does not flag it, and nothing in the evidence shows it was added because of that item, so it is kept.
- `pdpc.gov.sg`: kept. A national regulator qualifies on its own; it sits in `standards` with other regulators (`ico.org.uk`, `cnil.fr`). The clinical item and its key do mention it, so the leakage reviewer should know it is there.
- `opentelemetry.io`: kept. A standards project, listed with `cloudevents.io` and `spec.openapis.org`; the payments item names OpenTelemetry once.
- `apache.org`: kept. A major open-source foundation; the lakehouse item names Apache projects, not the host.

## Session 4 second-truncation fallback

Fresh Opus worker, 2026-10-03.
Planner ruling (final): a stage whose answer is truncated twice at the output cap degrades like a deadline cut.
Full report: `docs/transcripts/session4/truncation_fallback.md`.
Commits: `aab35fa` (behaviour and tests), `f6ec4ef` (docs and a `PhaseCall` test), then the results file and this record.

### Reproduced first

Offline fault schedule truncating every call of one stage (`tests/robustness` harness), before the change: understand, plan, assess and refine each made exactly two calls and ended with exit 3, `failure.json` (`LLMTruncatedError`, resumable) and no report.
Research, verify and report already degraded after one truncation (they make no truncation retry) and were not changed.

### Edits

| File | Edit | Regression test |
|---|---|---|
| `agent/sit_review_agent/phases/_model_calls.py` | Second truncation: no third call; `other` degradation "the <stage> answer was truncated twice at the output cap (max_tokens=N; the call and its one retry, <call IDs>)", a progress warning, and `PhaseCall(truncated=True)`; the phase continues with its deadline fallback | `test_a_stage_that_truncates_twice_ends_in_a_disclosed_degraded_report` (understand, plan, assess, refine) |
| `agent/sit_review_agent/llm/runtime.py` | `TRUNCATED_TWICE` and `truncated_twice_event(phase)`, next to `OUT_OF_TIME_BEFORE_ASSESSMENT` | same |
| `agent/sit_review_agent/phases/assess.py` | Coverage note "not assessed: the assess answer was truncated twice at the output cap" | same, assess case |
| `agent/sit_review_agent/phases/plan.py` | `build_plan(..., missing=)`: the code-built questions name why there is no model plan (declined, deadline, truncated); before, a deadline cut was also called "declined" | same, plan case |
| `agent/sit_review_agent/phases/report.py` | Third not-assessed reason `truncated` (`_NOT_ASSESSED_TEXT`, `NOT_ASSESSED_WHY`, `assessment_missing`) | `tests/test_not_assessed_verdict.py` (truncated cases) |
| `agent/sit_review_agent/report/render.py` | Verdict label "not assessed (answer truncated twice at the output cap)"; coverage cell of an unassessed criterion reads "not assessed", not "not applicable" (also for the deadline and declined paths, as `dra coverage` already did) | regression test, assess case |
| `agent/sit_review_agent/manifest.py` | `extra.model.truncations` lists every truncated call (`call_id`, `stage`, `purpose`); usage and cost were already summed from `llm.jsonl` | `tests/test_truncation_fallback.py` (billed usage) |
| `spec/finding.schema.json`, `spec/taxonomy.yaml` | `not_assessed` description and comment name the new reason; no enum value changed | none (text) |
| `tests/robustness/test_robustness_scenarios.py`, `robustness_coverage.py`, `README.md` | LLM-07 persistent variant | the scenario itself |
| `tests/robustness/results/robustness_results.csv` | Regenerated with the documented command at `f6ec4ef`: only LLM-07 changed (k 2, passes 2); 81 rows, 49 PASS, 32 BLOCKED | `test_robustness_results_csv.py` |
| `agent/README.md`, `docs/REPRODUCIBILITY.md` §5 | Exit codes (a disclosed degraded run exits 0); output-cap paragraph and known limitation rewritten | none (text) |

### Correction to the Session 4 verifier record

The known-limitation line "`sit-review resume` repeats the same call at the same cap" no longer holds: the run now finishes with a report, and `resume` on it serves that report and makes no model call (tested).
The limitation that remains is that a second truncation is not recovered by splitting the stage.

### Mutations (each restored from a `cp` copy, checked with `filecmp` and `git status`)

All 12 caught: second truncation raising again; a third call at the same cap; event without call IDs; assess truncation not a not-assessed reason; truncation typed `budget_or_deadline_hit`; manifest list emptied; plan rationale "declined"; assess coverage note dropped; label without reason; coverage cell back to "not applicable"; rationale reason "deadline"; `PhaseCall.declined` ignoring `truncated` (survived at first, caught after `test_a_call_truncated_twice_is_neither_declined_nor_cut` was added).

## Session 4 accounting fixes

Fresh Opus worker, 2026-10-03.
Source: the agent observations of the demo measurement run (`SIT-wt/demo/docs/live_runs/demo_profile_measure_1/MEASUREMENT.md`) and the "not verified" list of `docs/transcripts/session4/truncation_fallback.md`.
Full report: `docs/transcripts/session4/accounting_fixes.md`.
Commits: `8279338` (branch name), `b93df32` (Located at), `0e14c4c` (failed calls in the budget, interface change), `8ef32d4` (unknown usage), `3a7ee4c` (decision #25 and deviation entry 9), then this record and the report.

### Reproduced first (offline, each as a failing test before the fix)

- Branch: a `.git` whose HEAD is `ref: refs/heads/s4/demo` gave `branch: demo`; a detached HEAD gave `branch: null` and a missing `git` binary gave `dirty: null`, both without a crash (already correct, now pinned).
- Located at: the live `report.json` holds three different intent quotes, two of them on p.2 §1; the renderer printed page and section only, so the location read twice. The data was not duplicated; the renderer was the cause. A model that repeats one quote exactly would also have printed twice (no dedupe anywhere).
- Budget: understand truncated twice at 7,500 input tokens per call left `state.budget.input_tokens` at 0, and with a 10,000-token budget the run went on to plan.
- Unknown usage: a `claude -p` attempt cut by the deadline (fake runner) was logged with zero usage and the manifest summed it as zero.

### Edits

| File | Edit | Regression test |
|---|---|---|
| `agent/sit_review_agent/manifest.py` | `git_state` keeps the full branch name (strips `refs/heads/` only) | `tests/test_accounting_fixes.py` (slashed branch, packed refs in a linked worktree, detached HEAD, no `git` binary) |
| `agent/sit_review_agent/report/render.py`, `templates/report.md.j2` | `intent_locations`: each location once, first-seen order, "(N passages)" when a section holds several anchors | `test_located_at_names_each_location_once` |
| `agent/sit_review_agent/phases/_model_calls.py`, `phases/understand.py` | `unique_anchors`: an exact repeat of an anchor (document, page, section, normalised quote) is dropped for intent, findings and sound areas | `test_understand_keeps_a_repeated_anchor_once`, `test_finding_and_sound_area_anchors_keep_a_repeat_once` |
| `agent/sit_review_agent/errors.py` | Interface change: `LLMError(..., usage=None)` and `LLMError.usage` (billed usage of the failed call's attempts; `None` = no attempt reported usage) | `tests/test_budget_counts_failed_calls.py` |
| `agent/sit_review_agent/llm/gateway.py` | `billed(err, usage)`; set by `AnthropicGateway` (a response that arrived and failed), `FakeGateway` (scripted refusal, truncation, schema error), `FaultInjectingLLMGateway` (`schema_violation` keeps the inner call's usage) | same, plus `test_max_tokens_is_truncation_not_retried` |
| `agent/sit_review_agent/llm/claude_code.py` | Failed attempts with a JSON result summed per call and attached to the raised error | `test_claude_code_error_carries_the_billed_usage_of_every_attempt` |
| `agent/sit_review_agent/replay.py` | A replayed recorded failure carries the recorded usage, so a replay counts the budget like the live run | `test_replay_counts_a_recorded_failed_call_like_the_live_run` |
| `agent/sit_review_agent/llm/usage_budget.py` (new) | `add_usage(budget, usage)`, used for results and errors in every phase; `describe_unrecorded`, `cost_lower_bound_line` | all of the above |
| `phases/_model_calls.py`, `research.py`, `verify.py`, `report.py` | Every handler of a model error adds `exc.usage` to `state.budget` | phase tests in `test_budget_counts_failed_calls.py` |
| `agent/sit_review_agent/llm/gateway.py` | `USAGE_UNRECORDED_REASONS`, `unrecorded_usage(reason)`; `AnthropicGateway` logs `usage: null` and `usage_unrecorded` for a failure without an HTTP status (`deadline_cut`, `timeout_kill`, `connection_lost`) and for an interrupt; `FakeGateway` for a scripted cut or timeout | `tests/test_unrecorded_usage.py` |
| `agent/sit_review_agent/llm/claude_code.py` | Same marker for `deadline_cut`, `timeout_kill`, `process_fault` (no JSON result) and `interrupted`; a CLI that never started keeps zero usage | same |
| `agent/sit_review_agent/manifest.py` | `unrecorded_reason` (also reads older zero-usage cut or timeout entries), `journal_usage()["calls_with_unrecorded_usage"]`, `extra.model.calls_with_unrecorded_usage` and `extra.model.cost_usd_lower_bound` | same |
| `report/templates/report.md.j2`, `phases/report.py`, `orchestrator.py`, `kruns.py` | Tokens row "a lower bound: N model calls with unrecorded usage (stage, reason)"; a closing console warning for a finished or failed run; `--k` table `>=` per run and a note on the total, `calls_with_unrecorded_usage` and `cost_usd_lower_bound` in the group summary | same |
| `agent/README.md`, `docs/REPRODUCIBILITY.md` §6 and §8 | Module map row, interface-change note, unknown-usage policy; manifest schema lines | none (text) |
| `docs/USER_DECISIONS.md` #25, `eval/prereg_deviations.md` entry 9 | Three not-assessed reasons (`deadline`, `truncated`, `declined`), dated amendment | none (text) |

The helper module was first named `llm/accounting.py`; the repository leakage check flagged "Accounting" as a term of a synthetic eval document, so it was renamed `usage_budget.py` rather than allow-listed.

### Mutations (each restored from a `cp` copy; `git status` checked after each batch)

All 33 caught.
Branch: `rsplit` back (3 tests fail).
Located at: renderer without grouping; understand without dedupe; findings and sound areas without dedupe.
Budget (12): `add_usage` removed from each `call_model` handler (truncation, refusal, schema, deadline), from all research handlers, from verify, from report; `billed` made a no-op; the Claude Code per-call sum dropped; `schema_violation` without the inner usage; replay without recorded usage; `add_usage` a no-op.
Unknown usage (17): each Claude Code reason label dropped (3); the log override; the Claude Code and Anthropic interrupt entries; the Anthropic no-status branch; the fake gateway's killed flag; the explicit marker ignored; the legacy inference; the lower-bound flag; the report.md note; the report and failed-run console lines; the `--k` cell, total note and collector.
