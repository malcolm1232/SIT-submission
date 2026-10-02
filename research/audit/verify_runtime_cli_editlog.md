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

- `README.md` tells the reader to run `python3 spec/validate_examples.py` and `python3 spec/convert_answer_keys.py` with no tier; both then read the answer keys under `eval/blind/`, which `docs/SEALING.md` §6 rule 1 forbids until sealing. I ran the spec self-test with the blind directory filtered out (the same filter `convert_answer_keys.py --tier synthetic` uses).
- `README.md` status paragraph still says 865 offline tests (dated 2026-10-02).
- `docs/DEMO_DAY_RUNBOOK.md` header paragraph ("before the agent code exists") and §2 (`uv sync --frozen --offline`; the repository has no `uv.lock`) are older than the build.
- `docs/HANDOVER_FULL.md` §10 lists these six items as in flight.
- The runbook's §5 walk-through of one finding now has 30 s of the 10-minute slot in the worst case; the rehearsal should set the reserves from measured times.
- `docs/BUDGET.md` and the cost lines of `eval/EVAL_PLAN.md` (see item 5).
