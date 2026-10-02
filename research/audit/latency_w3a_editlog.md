# Edit log: latency redesign W3 part A, the manifest of a concurrent run

Date: 2026-10-03 (Singapore time; clock read 2026-10-02 23:02 UTC).
Worker: two fresh-context agent sessions; the first (`claude-opus-5-5`) was ended by a model-side safeguard after item 1, the second (`claude-fable-5-1`) secured its uncommitted item 2 and finished items 2 to 6.
Scope: branch `s4/w3a-latency`, base `87a0634` (W3 replay), worktree `/Users/malco/Desktop/SIT-wt/w3a`.
Owned files: `agent/sit_review_agent/manifest.py`, `tests/test_manifest_concurrent.py`.
Authority: the W3a brief (items 1 to 6); `docs/design/` and `docs/transcripts/` were not read.

Isolation: nothing under `eval/blind/` was opened or listed; no `llm.jsonl`, recorded model call or model-output text was printed; no model call and no agent run was made.
No other folder under `/Users/malco/Desktop/SIT-wt/` or `/Users/malco/Desktop/SIT` was touched; nothing was pushed.
No call was refused in the second session.

## Edits

| # | Commit | File | What changed | Why |
|---|---|---|---|---|
| 1 | `832843e` | `manifest.py` | `logged_estimate`, `logged_salvage`; `journal_usage` returns `estimated_usage_of_unrecorded_calls`, `estimated_totals`, `salvaged_calls`, `salvaged_items`, `assess_shards`; `extra.model.estimated_usage_of_unrecorded_calls` and `extra.model.estimated_usage_totals`. | A cut call's estimate sits beside its measured-null record, never in the measured totals (item 1, first session). |
| 1 | `832843e` | `test_manifest_concurrent.py` (new) | Fixture helpers `usage`, `ok`, `cut`, `make_ctx`; 3 tests of item 1. | Small Python fixtures, no recorded text. |
| 2 | `f2a90a6` | `manifest.py` | `_offset`, `call_spans`, `stage_timing`, `run_clock_s`; `extra.timing.stages[stage] = {members, wall_s, sum_of_member_s, wall_basis}`; `wall_clock_s` falls back to the checkpointed `budget.elapsed_s`. | Overlapping stage 1 members: the stage wall is the span from the earliest member start to the latest member end, never the sum (item 2). |
| 2 | `f2a90a6` | `test_manifest_concurrent.py` | `make_ctx` starts the fake clock at 1000 s (0.0 means "not started"); 5 timing tests. | The first session's half-done work, finished. |
| 3 | `f0c8d59` | `manifest.py` | `logged_shard`; `assess_shards` counts distinct `shard` markers on assess attempts (was: distinct assess conversations); `extra.model.assess_shards`, `salvaged_calls`, `salvaged_items`. | Distinct conversations over-count retries (`assess-0-r1`) and give 1 for a sequential run; a marker gives 0 (item 3). |
| 3 | `f0c8d59` | `test_manifest_concurrent.py` | `shard` on the concurrent fixture's assess entries; 2 count tests; the sequential test asserts the three zeros. | |
| 4 | `fb97594` | `test_manifest_concurrent.py` | 1 cross test: both manifests round-trip through JSON, pass `ManifestExtra`, and `harness/sit_eval/usage.from_manifest` reads them with the old meanings. | Backward compatibility (item 4). |

## Mutations (item 5)

Each mutation was applied to a copy of `manifest.py` restored afterwards from a `cp` backup (`git status` clean after every one); the test file was run per mutation.

| # | Claim removed | Result |
|---|---|---|
| M1 | stage `wall_s` is the span, not the sum | caught by `test_overlapping_stage_1_members_give_the_span_not_the_sum` (and the longest-member test) |
| M2 | the span is at least the longest member | caught by `test_a_stage_span_is_at_least_its_longest_member` |
| M3 | a bool or negative `start_offset_s` is ignored | caught by `test_a_bad_start_offset_is_ignored` |
| M4 | `wall_clock_s` falls back to `budget.elapsed_s` | caught by `test_the_wall_total_falls_back_to_the_checkpointed_run_clock` |
| M5 | a log without offsets reads its stage wall as the sum | caught by `test_a_sequential_run_reads_its_stage_wall_as_the_sum` (and the bad-offset test) |
| M6 | a `shard` marker counts only on an assess attempt | caught by `test_a_shard_marker_counts_only_on_an_assess_attempt` |
| M7 | salvaged items are the list fields only | caught by `test_shards_and_salvage_are_counted_from_the_log` |
| M8 | the counts are wired into `extra.model` | caught by 4 tests |
| M9 | an estimate never enters the measured totals (item 1) | caught by `test_a_cut_calls_estimate_sits_beside_its_measured_null_record` and the cross test |

## Gates (exit codes read)

`ruff check agent harness tests` 0; `pytest -q` from the repo root 0 (1251 passed); `sit-review selftest` 0; `make smoke` 0 (218 passed); `make test` 0 (1251 passed).
