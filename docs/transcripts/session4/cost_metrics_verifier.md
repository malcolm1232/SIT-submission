# Session 4: cost metrics verifier report (2026-10-03)

Verifier: a fresh-context Opus session that did not build the work.
Branch `s4/costmetrics`, worktree `SIT-wt/costmetrics`, builder commits 8782152 and c14cbff on base 103b8e6.
Edits and their regression tests are in `research/audit/cost_metrics_unknown_usage_editlog.md`, section "Session 4 verifier".
No model call was made, the only judge used was the fake one, nothing under `eval/blind/` was opened, and no `llm.jsonl` was printed.

## Verdict

Ready.
The builder's work implements ruling #28 on the merged tree.
Three small defects were fixed with regression tests, and the two prereg gaps the hub verifier listed were closed under the ruling's own rule, in deviation entry 10.
One point is reported for a decision and was not changed (see "Open").

## Merge

`origin/claude/happy-darwin-d0bl94` was a29acfb as expected and was merged as 5033367.
Two conflicts, both plain both-sides-added: `docs/USER_DECISIONS.md` (#27 from main, then #28; the "#27 absent" sentence removed; #24 to #28 once each, in order) and `eval/prereg_deviations.md` (main's amendment line on entry 9, then entry 10).
No reinstall was needed: the editable packages already resolve to this worktree.

## Checks

1. Per-run null cost and tokens with reason `unrecorded_usage` naming the count, lower bounds beside, a fully accounted run unchanged: PASS (`metrics._efficiency`; demo run scored, below).
2. Completeness order (manifest field, else the runtime's rule over `llm.jsonl`, else `unknown` with `usage_completeness_unknown`): PASS.
   Rule comparison: the harness's `unrecorded_reason` in `harness/sit_eval/usage.py` and the runtime's in `agent/sit_review_agent/manifest.py` are the same statement for statement (same `_LEGACY_KILLED` map, same exclusions for `sent: false`, `fault`, `replayed`, `fake`, same zero-usage, null-cost and null-status test); the call rows match `journal_usage` field for field.
   Both fixtures are the demo run's `llm-0003` shape.
   FIXED: the builder's test pinned the harness copy to expected values only, because the runtime's copy was not on its branch; `tests/eval_harness/test_eval_usage_verifier.py` now runs 23 entry shapes through both copies and the demo run's real `llm.jsonl` through both readers (both give one call, `llm-0003 assess deadline_cut`).
   `sit_eval/usage.py` imports nothing from the agent package (pinned by an AST test); the harness imported the agent package before this branch (`loaders`, `metrics`, `grounding`, `paths` and others), and this branch adds no new agent import.
3. Fully accounted median with excluded count and share, lower-bound median over all runs, never mixed: PASS, with one FIXED defect: a run whose value carried no figure at all was dropped from the lower-bound median, which could overstate it and fail the checkpoint unsoundly; it now counts at 0 and is reported as `runs_without_a_figure_counted_at_zero`.
4. Pilot checkpoint: PASS.
   My own fixtures end to end through `aggregate`: all fully accounted with the median exactly $3.24 gives `pass`; $3.25 gives `fail`; one $5 lower bound and one run with no figure gives `not_evaluable` (it gave `fail` before fix 3).
   The builder's matrix (fail on a lower-bound median above, pass, fail all accounted, `not_evaluable` with a cut run below, `not_evaluable` with an unknown run, no FULL run, no threshold) also passes on the merged tree.
   FIXED: with no threshold the console line printed `$None`; it now says "no threshold".
5. Intention-to-treat share of runs with any cut call: PASS (`runs_with_unrecorded_usage`, with `runs_with_unknown_usage_completeness` beside it).
6. Prereg and documents: PASS. `eval/prereg.yaml` parses, `frozen: false`, `measured_median_full_usd` and `b0_dollar_matching_n` still `null`, `per_run_usd` unchanged; the README and `EVAL_PLAN.md` match the code.
   FIXED: deviation entry 10's **Fields** line named one field twice across a line break; `USER_DECISIONS.md` #28 still said commit `8ef32d4` was "on another branch".

Gaps listed by the hub verifier:

- Prereg B0-$ matching (`conditions.tier_A` B0-$ `matching_rule`): FIXED in the prereg text. Both medians are over fully accounted runs, and while any pilot FULL or B0 run is not fully accounted the match is `not_evaluable`, reported, and no n is chosen. No harness code computes the match today.
- Prereg budget stop (`stop_rule.budget_stop`): FIXED in the prereg text. The spend is a lower bound when any run is not fully accounted; a lower-bound sum at or above the figure triggers the stop, and one below it is reported as "at least". No harness code computes the stop today.
- Both are recorded in deviation entry 10 (extended, no new entry).
- `report_md.py`: PASS. The efficiency section opens with the LOWER BOUND or COMPLETENESS UNKNOWN line, and the cost lines show `null` with the bounds below. The "reported cost" in the calls line is the judge spend, not the run's cost.
- Aggregate and scores schema: PASS (`$defs/Efficiency` refuses a cost figure on a run that is not complete; mutant M9 is killed).
- `ManifestExtra` docstring: FIXED. It said scorers never read `extra`; it now says the harness reads `extra.timing` and `extra.model.calls_with_unrecorded_usage`. The harness package is not named in the text, because the isolation test refuses that string in `agent/`.
- `calls.py` judge spend: PASS, unaffected. It sums the judge's own call costs and charges the reserve for an attempt of unknown cost; it never reads the run's manifest.
- Demo run (`docs/live_runs/demo_profile_measure_1`) scored with `--exploratory`, fake judge, `--no-grounding-judges`: console `cost` is `{"usage_completeness": "unrecorded", "cost_usd": null, "cost_usd_lower_bound": 1.100936, "calls_with_unrecorded_usage": 1}`.
  On stderr: "the agent run's cost is a lower bound: unrecorded_usage: 1 model call ... (llm-0003 assess attempt 0, deadline cut, 178.91 s)".
  `scores.md` opens the efficiency section with the LOWER BOUND line, and `scores.json` warns that completeness was read from `llm.jsonl` by the legacy rule.
  No bare cost appears anywhere.
- Mutations re-run: M1, M3, M5, M7 and M9, all killed (1, 10, 7, 3 and 1 failing tests); every file was restored and compared with `cmp`.

## Open (reported, not changed)

`sit-eval aggregate` drops a `scores.json` with status `stopped_budget` (a judge budget stop) before any statistic, so a FULL run whose scoring stopped is missing from the checkpoint's run count, and the checkpoint can `pass` on the runs that remain.
This was already the behaviour before this branch, and changing it is a behaviour judgement.
Options:
- (a) count such a run as unknown completeness in the cost summaries only;
- (b) make the checkpoint `not_evaluable` whenever a FULL scores file was dropped;
- (c) leave it as it is and document it.

Recommendation: (b), the smallest change that keeps "a lower bound never passes" true for missing runs.

## Gates on the final HEAD

`ruff check agent harness tests` 0; `pytest -q` 0, 1140 passed (1112 on the merge commit, plus 28 new: 23 rule-parity cases and 5 tests); `sit-review selftest` 0; `make smoke` 0 (198 passed); `make test` 0 (1140 passed); `python spec/convert_answer_keys.py --tier synthetic --check --verify-anchors` 0 (45 flaws, 3 keys, 0 failed).
No em dash on any added line since a29acfb, and no secret in the diff.
Every commit is authored by `malcolm1232 <66200354+malcolm1232@users.noreply.github.com>`, with no co-author or attribution line.

## Not verified

- No run of the new runtime has yet written `extra.model.calls_with_unrecorded_usage` into a real manifest, so the manifest path is tested on fixtures in the runtime's shape only.
- The wall-time half of the pilot checkpoint is still not computed by the harness.
- The B0-$ match and the budget stop exist as prereg text only; no code enforces either.
