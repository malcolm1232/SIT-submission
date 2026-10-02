# Verifier E1 edit log: evaluation harness (matcher, metrics, statistics, live judges, `sit-eval score`)

Date: 2026-10-02. Scope: `harness/sit_eval/**` except `grader/`, `tests/eval_harness/**`, `config/eval.yaml`,
`harness/README.md`. No prompt or judge schema changed: `PROMPTS.lock` bundle stays
`d9e14df564478b453b54e47560ef72a5d98a457a262f7bc31dd7809905a996dd` (`sit-eval prompts` passes).
Nothing under `eval/blind/` was opened. `eval/prereg.yaml`, `spec/` and `agent/` were not edited. No git was run.

## Edits

| # | File | What | Why |
|---|---|---|---|
| 1 | `harness/sit_eval/calls.py` | `request_key(req, namespace)` now hashes a client namespace too; `JudgeRunner.cache_namespace` defaults to the client's `backend` attribute, else its class name. | Defect: the result cache ignored which client answered. `--out` defaults to `runs/eval/<run_id>` for every judge kind, so a `--judge fake` plumbing run followed by a live run reused the fake (hash) answers as real judgements. |
| 2 | `harness/sit_eval/calls.py` | Cost accounting: on success charge `cost + reserve x unknown_cost_attempts` (one reserve when the cost is unreported); on failure charge the error's known cost plus one reserve per unknown-cost attempt, and record the known cost on the failed `CallRecord`. Docstring updated. | Defect: a call that needed retries reported only its last attempt's cost, and failed attempts with a known cost were charged a flat reserve, so spend and the cost stop under-counted. |
| 3 | `harness/sit_eval/live_judges.py` | `ClaudeCodeJudge.complete` sums the cost of every attempt into `JudgeResult.cost_usd`, adds `raw["unknown_cost_attempts"]` and `raw["cost_includes_failed_attempts"]`; on final failure the raised `JudgeError` carries `cost_usd` and `unknown_cost_attempts` attributes (no signature change). Module docstring updated. | Same defect as 2 (client side). |
| 4 | `harness/sit_eval/live_judges.py` | New `argv_schema()` drops a root `$schema` key; used for `--json-schema` (ClaudeCodeJudge) and `output_config.format` (AnthropicJudge). | Coordinator heads-up: `claude -p --json-schema` was seen to reject `$schema`. The harness's own schemas were already stripped in `prompts._schema`; this covers every caller (the grader builds its own). Validation of answers still uses the full schema. |
| 5 | `harness/sit_eval/judge.py` (`build_judge` body and docstring only) | Live-client options the caller does not pass default to `config/eval.yaml` `judge` (claude_code: executable, timeout_s, max_retries, backoff_base_s, backoff_max_s, max_budget_usd_per_call, inherit_api_key; anthropic_api: the four timing/retry options). Explicit options win. | Coordinator request: the grader calls `build_judge(kind, out_dir=...)` with no options, so no per-call `--max-budget-usd` reached its `claude -p` calls. |
| 6 | `harness/sit_eval/matcher.py` | Reverted the deterministic `partial_key_match`: a strict-unmatched finding scoring PARTIAL against a flaw nobody matched now goes to the LLM adjudicator like any unmatched finding; the flaw is recorded in the new `Adjudication.partial_key_flaw_id` (`Matcher.partial_free_flaw`). Docstring updated. | Deviation decision: the old rule labelled such findings VALID_UNPLANTED, crediting strict P_a with findings the strict rule rejects (it made strict P_a behave like lenient P_a) although metrics.md defines VALID_UNPLANTED as an issue "missing from the key"; it also bypassed the HALLUCINATED/INVALID_OPINION check. metrics.md §13 sends every unmatched finding to the adjudicator. |
| 7 | `harness/sit_eval/metrics.py` | New exploratory metric `precision_adjudicated_partial_credit` = (TP + #unmatched that are VALID_UNPLANTED or PARTIAL against a free flaw and not DUPLICATE/HALLUCINATED/UNADJUDICATED) / N. Removed the now-dead `partial_key_match` exclusion in CDR. | Keeps the old reading visible to the owner without letting it move the key-secondary P_a. |
| 8 | `harness/sit_eval/scoring.py` | Adjudication rows carry `partial_key_flaw_id`; pair rows carry `skipped_samples`. | Report the fields from 6 and 9. |
| 9 | `harness/sit_eval/matcher.py`, `scoring.py`, `config.py`, `cli.py`, `config/eval.yaml` | New option `adaptive_third_sample` (config `matcher.adaptive_third_sample: false`; CLI `--adaptive-samples/--no-adaptive-samples`): with 3 samples, ask sample 3 only when samples 1-2 disagree or one failed (pairwise and per_flaw_batch). Off by default; `scores.json` warns when on; `--dry-run` reports it and lowers only the minimum. | Cost option that cannot change any result: the median of three equals the agreed value whenever two samples agree. Needs owner approval as a reading of prereg "3 samples, median". |
| 10 | `harness/sit_eval/scoring.py`, `config.py`, `cli.py`, `config/eval.yaml` | `plan_calls` takes `basis_model` (config `cost_estimate.basis_model: claude-opus-5-5`), adds `caveats` (model mismatch, retries not counted, document-carrying calls heavier, thinking tokens unmeasured, measured Haiku output-token range) and labels the prices UNVERIFIED. | Dry-run honesty: it priced every model and every call kind at the same Opus planning figure without saying so (a `--model claude-haiku-4-5` dry run showed $1-5 for a $0.32 run). |
| 11 | `harness/sit_eval/cli.py` | The grader app is imported in a try/except; on failure a stub `grade` command reports the import error (exit 2) and `score`/`aggregate`/`prompts` keep working. | Defect seen during verification: another workstream's in-progress grader edit (a syntax error in `grader/pipeline.py`) made `sit-eval score` itself fail to start. |
| 12 | `tests/eval_harness/test_eval_matcher.py` | `test_adjudication_rules` updated to the new rule: FND-003 (PARTIAL on free F02) is LLM-adjudicated, carries `partial_key_flaw_id`; P_a = 0.5 and the exploratory partial-credit precision = 0.75. | Regression test for 6-7. |
| 13 | `tests/eval_harness/test_eval_verifier_e1.py` (new) | 8 test functions (9 cases): fake answers never served to a live client; retried call reports every attempt's cost; failed call charges known cost plus a reserve per unknown attempt; adaptive third sample gives identical medians and assignment with fewer calls (agree and disagree cases); CLI survives a broken grader import; dry run flags a model outside the price basis and pins the live-run counts (80 overlap pairs, 300-440 calls; adaptive pair calls 160-366); root `$schema` never sent; `build_judge` defaults from `config/eval.yaml`. | Regression tests for 1-5, 9-11. |
| 14 | `harness/README.md` | Partial-match rule, cache namespace, adaptive rows in the cost table, dry-run caveats, config defaults in `build_judge`, `$schema` stripping, cost of retries, guarded grader import. | Documentation of 1-11. |
| 15 | `research/audit/verify_eval_harness_editlog.md` (this file) | Created. | Mandatory log. |

## Live check (claude-haiku-4-5, effort low, made-up 2-flaw / 3-finding case, scratchpad only)

27 live `claude -p` calls, $0.320 total (largest single call $0.027). All seven call kinds' schemas were accepted,
including `score` as integer `enum [0,1,2,3]`, and every answer validated. The first `sit-eval score` run hit
`--max-cost-usd 0.60` (reserve $0.10 per call): status `stopped_budget`, exit 3, in-flight calls finished and were
cached; the re-run resumed with 0 live calls. A `per_flaw_batch` run reused the cache and added 6 batch calls. The
3 samples varied (one pair scored 3, 2, 3 because one sample set `location_ok: false`). Haiku produced 0.6k-4.8k
output tokens per call at effort low.

## Not changed (owner decisions or other owners)

See the verifier's report: candidate-set cost options, proposed prereg/metrics text, the in-flight reserve
under retries, and the per-call `--max-budget-usd` the grader now inherits ($1.00).
