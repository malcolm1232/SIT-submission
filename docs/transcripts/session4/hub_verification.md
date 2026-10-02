# Session 4: hub verification (2026-10-03)

Verifier: a fresh Opus session, one deliverable; it built none of the work it checked.
Worktree `SIT-wt/integration`, branch `s4/integration`, from `3fa04b4`.
Edits and mutations are in `research/audit/verify_runtime_cli_editlog.md`, section "Session 4 hub verification".
No model call was made; everything ran offline (fake transport, fake judges, fault schedules, replay).

## Verdict

Ready.
Two defects were found and fixed with regression tests: a merge seam that made `dra replay` crash on the committed demo run, and an LC12 bypass through `--prior-scores`.
Every gate in section F exits 0 on the final HEAD.

## Step 1: merge

| Commit | What | Conflict |
|---|---|---|
| `b44a5d9` | Merge of `s4/lc12` at `103b8e6` | `docs/USER_DECISIONS.md`: this branch's amended row #25 against the other side's unchanged row #25 plus the new LC12 section (row #26). The other side's row #25 was byte-identical to `2d84f59`, so the amended row was kept and the LC12 section appended. |
| `8b35dcd` | Merge of `feb1d9f` (by sha, not the branch name) | none |

No packaging file changed, so the editable install was not redone.
Test ids: the truncation branch had 1061, `s4/lc12` 1051, their union 1092.
The merged tree collects 1089: the union less the three ids of `test_a_stage_that_truncates_twice_never_ends_in_a_silent_success[understand|assess|refine]`, which the truncation branch replaced on purpose with the four-stage `..._ends_in_a_disclosed_degraded_report`.
With the hub's four regression tests the final count is 1093.

## A. Second-truncation fallback (aab35fa, f6ec4ef, 776cb57): PASS

- Per stage, through the real CLI (`sit-review review --transport fake --faults <schedule> --no-tools`, each stage's every call truncated): understand, plan, assess and refine each made exactly two calls (`<stage>`, `<stage>:max_tokens_retry`, both `LLMTruncatedError`), exited 0, manifest outcome `completed_degraded`, `report.json` and `report.md` written.
- Disclosure: degradation type `other`, event "the <stage> answer was truncated twice at the output cap (max_tokens=128000; ...)" in `report.json`; the same in `report.md`; two progress lines per stage; `extra.model.truncations` lists both call IDs.
  Assess: verdict `not_assessed`, shown as "Not assessed (answer truncated twice at the output cap)", no findings, no verdict call.
  Refine: the three assess findings kept.
- Distinguishable: a deadline cut (LLM-05 under the demo profile, fake clock) is type `budget_or_deadline_hit`, "out of time before assessment"; a decline (LLM-06) is "the model declined the assessment".
- Billed tokens: an injected fault spends nothing by design (`unrecorded_reason` skips `fault` entries), so totals were checked with scripted truncations carrying usage (11,111 in, 99,999 out each): for every stage the manifest totals include both calls (2 x 99,999 output, 2 x 11,111 input).
- `sit-review resume` on each finished run: exit 0, `llm.jsonl` line count unchanged, `report.json` hash unchanged.
- Mutations (3, all caught): see the edit log.

## B. Accounting fixes (8279338, b93df32, 0e14c4c, 8ef32d4, 3a7ee4c): PASS

1. Unknown usage. A cut or killed call is logged with `usage: null` and `usage_unrecorded`; the manifest lists it in `extra.model.calls_with_unrecorded_usage` and sets `cost_usd_lower_bound`.
   Every cost total printed or exported inside `agent/` was found by grep and is qualified: the `report.md` Tokens row, the closing console line of a finished run (`phases/report.py`) and of a failed run (`orchestrator._run_fail`), and the `--k` table and group summary (`kruns.py`).
   `ClaudeCodeGateway.cost_total_usd` is read only by tests; no other `dra` command prints a cost.
   Nothing missed inside `agent/`; the `harness/` places are listed under step 4.
2. Failed calls count toward the token budget. Reproduced at the parent `b93df32` with a shape the builder's test does not use (plan declined twice at 6,000 input tokens each, budget 10,000): the budget read 5,000 and the run went through every stage.
   On the merged tree: 13,000, stop reason `budget_tokens`, no model call after plan.
   Freeze rule: the change to `LLMError` is additive, its commit message is the "interface change" note naming every writer and reader, and `agent/README.md` records it.
   The rule's word "alone" was met in substance only: the change and its readers landed in one commit, which is harmless now that the workstreams are merged.
3. Branch name: a nested branch (`feature/deep/name`) recorded in full, a detached HEAD gives `branch: null` with the commit, no `git` on `PATH` and no `.git` give `dirty: null`, no crash; this worktree records `s4/integration`.
4. "Located at": on the selftest run and the demo run (anchors duplicated by script to stress it) each location appears once and the passage counts sum to the `report.json` anchor count.
   `llm/usage_budget.py`: `scripts/leakage_grep.py` passes on the merged tree, and nothing imports the old `llm.accounting` name.
- Mutations (6 of 33, cost and budget guards first, all caught): see the edit log.

## C. Scoring guard LC12 (987078f, 33ffe39, 103b8e6): FIXED

Each clause, by command with the fake judge and a counting judge factory:

- Unsigned key, no flag: `sit-eval score` exit 2, no judge built, zero calls, no `scores.json`.
- `--exploratory`: exit 0; `scores.json`, `scores.md`, every judge cache row and the console are marked.
- Aggregate: exploratory only, mixed, and a pre-guard file on an unsigned key are each refused (exit 2); confirmatory only and mixed with the flag run, the latter marked.
- Cache: a confirmatory run (scratch copy of the key, signed) into an `--out` written by an exploratory run reused none of its 118 rows and said so.
- Frozen prereg (monkeypatched status) plus the flag: "outside the pre-registered analysis" in `scores.json`, `scores.md` and the console; the grader's `grade.json`, `grade.md` and every `grader_calls.jsonl` row are marked too.
- Pilots: one `EXPLORATORY.md` note each, nothing else under `docs/live_runs/live_cc_opus_payments_v1` changed.

Attempts to get around it:

| Attempt | Result |
|---|---|
| Legacy YAML key to the grader (CLI and `grade_review`) | refused, zero calls, no file written |
| Key without `authoring_status`, without `scored_run_ready`, or with the string "true" | `sit-eval score` rejects it as an invalid canonical key, exit 2, zero calls |
| `score_review` and `aggregate` called directly | refused before any call; an exploratory runner under confirmatory options is refused |
| Resume into an exploratory `--out` | rows withheld, calls made again, output confirmatory and correct |
| Environment variables (`SIT_EXPLORATORY`, `EXPLORATORY`, `SIT_EVAL_EXPLORATORY`) | ignored, refused |
| `exploratory: true` in `eval.yaml` | the config model forbids unknown keys, refused |
| Grader without `--answer-key` | key-blind grade runs, as ruled (it reads no key) |
| An exploratory `scores.json` as `--prior-scores` of a confirmatory score | **bypass**: accepted silently, 118 calls, output marked confirmatory |

Fixed in `bcb5981`: `lc12.require_confirmatory_prior` refuses it without `--exploratory`, in the CLI before any judge is built and in `score_review`; two regression tests.
The three real keys under `eval/synthetic/` are byte-identical to `2d84f59` and still `scored_run_ready: false`; no real key was signed.
Mutations (6 of 19, all caught), and 4 on the fix: see the edit log.

## D. Demo measurement (60c833b, feb1d9f): FIXED

- `dra replay docs/live_runs/demo_profile_measure_1` on the merged tree: exit 4 (`TypeError: dict + Usage` in assess).
  Cause, a merge seam: `replay.recorded_error` copies every constructor keyword it finds in the log entry, and since `0e14c4c` `LLMError` takes `usage`, so a deadline cut was built with the entry's `usage` dict.
  Fixed in `9aa47dd` with two regression tests, one replaying the committed run; now exit 0, "replayed report matches the recording".
- Credentials: count-only greps give 0 key-shaped values, 0 bearer values, 0 email addresses.
  Every field whose name looks like a secret is a token count, a boolean or null (by script, names and value types only).
  `effective_config.json` `config_root` holds a local home-directory path (39 characters), not a credential.
- `MEASUREMENT.md` table against `llm.jsonl` and the manifest, extracted by script: every cell agrees (understand 135.9 s, 18,033 output, $0.608, 30,890 cache writes; plan 101.7 s, 10,065, $0.493, 36,480; assess 178.9 s, cut; total 420.1 s, 28,098, $1.10, 3 calls, 67,370 / 0).
- `git diff 2d84f59 feb1d9f -- config docs/DEMO_DAY_RUNBOOK.md`: comment lines and one runbook note only; the values (`report_reserve_seconds: 120`, `assess_reserve_seconds: 200`) are unchanged.
- Read with the merged manifest reader, without rewriting the run: `journal_usage` lists `llm-0003` (assess, `deadline_cut`, 178.91 s) and the console line reads "cost ~$1.10 is a lower bound: 1 model call with unrecorded usage (assess, deadline cut)".
  The committed `manifest.json` predates the field, so a reader of that file alone (the `--k` collector, the harness) sees no flag; only a rebuilt manifest carries it.

## E. Cross-branch seams: FIXED (the replay seam, see D)

- A merged-agent run with a cut assess (`not_assessed`, one call with unrecorded usage, `cost_usd_lower_bound: true`, $0.04): `kruns.collect` reads `not_assessed`, $0.04, one unrecorded call; the harness loader reads its `manifest.json`, `_efficiency` reports $0.04.
  They agree on the verdict and the number; only the harness lacks the lower-bound flag (step 4).
- `sit-eval score` on that run (real payments key, read only, `--exploratory`): exit 0, schema-valid `scores.json` with the guard's new required fields, verdict `not_assessed`.
  Without the flag: exit 2.
- The offline end-to-end tests that cross agent and harness (`tests/eval_harness/test_eval_e2e.py`, `tests/eval_grader/test_grader_e2e_live_run.py`) pass inside the full suite.

## F. Whole-tree gates on the final HEAD: PASS

| Gate | Exit | Result |
|---|---|---|
| `ruff check agent harness tests` | 0 | All checks passed |
| `pytest -q` | 0 | 1093 passed (union 1092, less 3 replaced, plus 4 hub tests) |
| `sit-review selftest` | 0 | passed |
| `make smoke` | 0 | 198 passed |
| `make test` | 0 | 1093 passed |
| `spec/convert_answer_keys.py --tier synthetic --check --verify-anchors` | 0 | 45 flaws, 3 keys, 0 failed |
| `spec/validate_examples.py` (default: `eval/blind` neither listed nor opened) | 0 | ALL CHECKS PASSED |

- U+2014 on lines added since `2c7fba3`: 11, every one the reviewed PDF's own title recorded verbatim in the demo run directory; none in authored text.
  Not changed: editing a recorded run would falsify it and break its replay comparison, and the earlier committed live run carries the same title.
- Secrets in the diff: 0 key-shaped values, 0 bearer values, 0 secret assignments, 0 email addresses (the 16 address-shaped hits are `@pytest` decorators).
- Every commit since `2c7fba3` carries `malcolm1232 <66200354+malcolm1232@users.noreply.github.com>` as author and committer, with no co-author or agent attribution line.

## Step 3: records

`docs/USER_DECISIONS.md` holds rows #24, #25 (as amended), #26 and #27 once each, in order; row #27 records the demo latency ruling.

## Step 4: consumers of cost or token numbers that do not know about unknown usage (report only)

`harness/`:

1. `harness/sit_eval/metrics.py` `_efficiency`, lines 612 to 634: copies `usage.cost_usd`, `input_tokens`, `output_tokens` and `cached_tokens` with no `cost_usd_lower_bound` or `calls_with_unrecorded_usage`; its note says the median and IQR come from aggregate.
2. `harness/sit_eval/report_md.py`, lines 85 to 88: prints "Efficiency (from the run manifest)" with the cost unqualified.
3. `harness/sit_eval/aggregate.py`: computes no efficiency statistic at all (`DEFAULT_METRICS` has none), although the note in 1 says it does; whoever adds the median must decide how lower bounds enter it.
4. `harness/sit_eval/schemas/scores.schema.json`, line 86 (the `efficiency` metric): no field for the flag.
5. `agent/sit_review_agent/models.py` line 648, the `ManifestExtra` docstring "Scorers never read `extra`": the flag lives in `extra.model`, and `_efficiency` already reads `extra.timing`.
   Options: (a) the harness reads `extra.model.cost_usd_lower_bound` and the docstring is corrected; (b) a spec-level usage field. Recommendation: (a), no spec change.
6. Adjacent, the harness's own judge spend: `harness/sit_eval/calls.py` line 199 counts `calls_without_cost` over successful calls only, so a failed judge call with no reported cost leaves `cost_usd_reported` (printed by `report_md.py` line 63 and the `score` console) unqualified; the cost stop already charges a reserve for such calls.
7. A manifest written before `8ef32d4` has no flag; the demo run's own `manifest.json` is one. A consumer that wants the flag on such runs must call `manifest.journal_usage` on the run directory.

`eval/prereg.yaml`:

- Line 52, `fill_before_freeze: costs.measured_median_full_usd`.
- Line 265, the efficiency metric (cost, tokens, median and IQR).
- Lines 406 to 407, B0-$: n chosen so that n x median(B0 cost) matches median(FULL cost) (not in the accounting worker's list).
- Lines 596 to 598, `budget_stop`: the hard stop at the Tier A figure is a spend total (not in the worker's list).
- Line 600, the $3.24 pilot cost checkpoint.
- Line 617, efficiency reporting.
- Lines 698 to 703, the `costs` block.

## Refused or routed around

No tool call was refused.
A CLI run of LLM-05 at the default deadline waits on real wall time (the 1,800 s attempt timeout); it was stopped by pid and the deadline control was run on the robustness harness's fake clock under the demo profile instead.

## Not verified

- Anything live: no `claude -p` or API call, so the billed usage of a real truncated or killed call is as unverified as the builders said.
- Mutations: 15 of the builders' 3 + 33 + 19 were re-run, not all.
- The demo profile's timings themselves (one live run, not repeated).
