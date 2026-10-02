# Latency redesign W3 part A: the manifest of a concurrent run

Branch `s4/w3a-latency` on worktree `/Users/malco/Desktop/SIT-wt/w3a`, base `87a0634`, commits `832843e`, `f2a90a6`, `f0c8d59`, `fb97594`, nothing pushed.
The first worker committed item 1 and was ended by a model-side safeguard with item 2 uncommitted; this session found that work green, finished it, and did items 3 to 6.
Edit log: `research/audit/latency_w3a_editlog.md`.

## What the manifest now says

`extra.model.estimated_usage_of_unrecorded_calls` lists one row per cut attempt that logged an estimate (`estimated: true`, call ID, stage, purpose, attempt, reason, the four token fields), and `extra.model.estimated_usage_totals` sums them with a price-table cost; the measured totals, `usage.cost_usd`, `calls_with_unrecorded_usage` and `cost_usd_lower_bound` are unchanged by an estimate (item 1).
`extra.timing.stages[stage]` has `members` (per member: `seconds`, `start_offset_s`, `end_offset_s`), `wall_s`, `sum_of_member_s` and `wall_basis`, so a reader cannot confuse the stage's span with its members' sum (item 2).
`wall_s` is the span from the earliest member start to the latest member end on the run clock, read from the members' model attempts, and at least the longest member (`wall_basis: member_spans`); it is a lower bound of the stage's wall time because code work before a member's first call is not seen.
A stage with one member has `wall_s` equal to that member's seconds (`single_member`), and a log without start offsets (a sequential run) has `wall_s` equal to the sum (`sequential_sum`), so a sequential run produces the same shape.
`extra.timing.wall_clock_s` is the live run clock, or the clock recorded at the last checkpoint (`budget.elapsed_s`) when the process is not the one that ran, else 0.0; `per_stage_s` is kept unchanged for the harness.
`extra.model.assess_shards`, `salvaged_calls` and `salvaged_items` are counts read from `llm.jsonl`, all 0 for a sequential run (item 3).
`assess_shards` was changed from "distinct assess conversations" (the first worker's draft) to "distinct `shard` markers on assess attempts", because an assess retry opens a new conversation (`assess-0-r1`) and a sequential run has one assess conversation, so the old rule over-counted retries and could not be zero.
A sequential manifest without shards or estimates is still produced, passes `ManifestExtra`, and `harness/sit_eval/usage.from_manifest` reads it as complete; a concurrent one with a cut reads as unrecorded with the same call rows, so the harness keys keep their exact meanings (item 4).

## Evidence

Nine mutations, each a removed claim restored from a `cp` backup, were all caught by the test named for the claim (table in the edit log) (item 5).
Gates, exit codes read one per call: `ruff check agent harness tests` 0, `pytest -q` 0 with 1251 passed, `sit-review selftest` 0, `make smoke` 0 with 218 passed, `make test` 0 with 1251 passed.
`tests/test_manifest_concurrent.py` has 11 tests; the four manifest-reading harness test files (`test_unrecorded_usage`, `test_interfaces_w0`, `test_eval_usage_verifier`, `test_eval_usage_completeness`) pass unchanged.
No model call was made, no `llm.jsonl` or recorded text was printed, nothing under `eval/blind/`, `docs/design/` or `docs/transcripts/` was opened, and no call was refused in this session.

## Not verified

No real concurrent run has been recorded yet, so every timing and count claim rests on authored fixtures; the first live run of W2 should have its `manifest.json` checked against the fields below.
The stage span is read from model attempts only, so a member whose code work runs long before its first call reads shorter than it was; `budget.phase_seconds` still carries each member's own wall time.
`stage_timing` lists only members present in `budget.phase_seconds`, so a member skipped before it started has no row.

## Fields assumed for the other workstream

Each `llm.jsonl` attempt (writers: the W1 gateway and the W2 orchestrator) carries `call_id`, `phase`, `purpose`, `attempt`, `conversation_id`, `elapsed_s` and `start_offset_s`, the run-clock seconds at which the attempt started, so a member's start offset is its earliest attempt's `start_offset_s` and its end offset is the latest `start_offset_s + elapsed_s`.
An assess attempt carries `shard`, the shard's name from `assess.shards` or its index, as a string or an integer, the same value on every attempt of that shard including retries; `assess_shards` is the number of distinct values and a run that logs none reads 0.
A cut attempt (`usage: null`, `usage_unrecorded: <reason>`) may carry `estimated_usage` or `usage_estimate` (the four `Usage` fields as non-negative integers) and `partial` or `salvaged_partial` (an object whose list fields hold the finished items, as `LLMDeadlineError.partial`) or `salvaged_items` (an integer count); `salvaged_calls` counts the attempts with at least one item and `salvaged_items` sums them.
The run state read is `budget.phase_seconds` (wall seconds per member, a member that never started absent), `budget.started_monotonic` (0.0 means not started) and `budget.elapsed_s` (the run clock at the last checkpoint), which are the fields assumed for the other workstream.
