# Session 4: accounting fixes (2026-10-03)

Worker: a fresh Opus session, one deliverable.
Branch `s4/integration`, worktree `SIT-wt/integration`, from `776cb57`.
Edits and mutations are in `research/audit/verify_runtime_cli_editlog.md`, section "Session 4 accounting fixes".

## Commits

| Commit | Item |
|---|---|
| `8279338` | 3. The manifest records the full git branch name |
| `b93df32` | 4. `report.md` names each intent location once |
| `0e14c4c` | 2. The token budget counts failed model calls (interface change) |
| `8ef32d4` | 1. Unknown usage is recorded as unknown; cost totals say when they are a lower bound |
| `3a7ee4c` | Decision #25 and prereg deviation entry 9 name all three not-assessed reasons |

Not pushed.

## 1. A call cut by the deadline was recorded as free

Before: a sent attempt that ended without a usage report was logged with zero usage, and the manifest summed it as zero.
The demo measurement run's assess call ran 179 s before the cut and showed $0; the manifest said $1.10 for a run estimated at about $1.9.

After: such an attempt is logged with `usage: null` and `usage_unrecorded: <reason>`.
The reasons are `deadline_cut`, `timeout_kill`, `process_fault` (a `claude -p` that exited without a JSON result), `connection_lost` (an API stream that failed with no HTTP status) and `interrupted`.
A `claude -p` that never started, and an API error with an HTTP status, keep zero usage: nothing was billed.
The manifest lists the attempts in `extra.model.calls_with_unrecorded_usage` (call ID, stage, purpose, attempt, wall seconds, reason) and sets `extra.model.cost_usd_lower_bound`.
An older `llm.jsonl` entry of a deadline cut or timeout with zero usage, no cost and no HTTP status is read the same way, so the demo run's `llm-0003` would be listed if its manifest were rebuilt.
Every place that prints a cost total says it is a lower bound when the list is not empty: the `report.md` Tokens row, a closing console warning (finished and failed runs), and the `--k` table (`>=` per run, a note on the total, and `calls_with_unrecorded_usage` and `cost_usd_lower_bound` in the group summary).
No other `dra` command prints a cost total.
`usage.cost_usd` keeps its spec meaning (the sum of what was recorded); the lower-bound flag lives in `extra.model`, so no schema or enum changed.

### Can partial usage be recovered from a killed `claude -p` call?

Not reliably, so it is not done and the unknown marker stays for the whole attempt.
The gateway runs `claude -p --output-format json`, which prints one result object at the end (`claude --help`: "json (single result)"); a killed process has printed nothing.
The alternative is `--output-format stream-json` with `--include-partial-messages`, read incrementally.
From the API's streaming format, that stream would carry the usage of each assistant turn the CLI completed, and for the turn in flight only the `message_start` usage (input and cache tokens); output tokens arrive in the final `message_delta`, which a killed turn never sends.
Output tokens are most of the cost of a long assess call (the demo run's cut call was estimated at 18k to 24k output tokens, against about 31k to 36k cache-write tokens for a whole prefix), so the recovered figure would still be a lower bound, and changing the CLI contract from one JSON object to a stream would need live verification on Opus.
No live check was made: the project gateway cannot request stream-json without that change, and the brief allows live checks only through it.
Haiku spend: $0.

## 2. The token budget did not count failed calls

Before: `state.budget` (read by the `budget_tokens` stop rule) counted only calls that returned a result.
Reproduced offline: understand truncated twice at 7,500 input tokens per call left the budget at 0, and under a 10,000-token budget the run went on to plan.

After: every `LLMError` carries `usage`, the usage the failed call was billed for, summed over its attempts that reported usage (`None` when none did).
The gateways set it (`AnthropicGateway`, `ClaudeCodeGateway`, `FakeGateway`, `FaultInjectingLLMGateway` for `schema_violation`, and replay for a recorded failure), and every phase that handles a model error adds it to the budget through `llm.usage_budget.add_usage`, which successful calls now use too.
The same run now stops with `budget_tokens` before plan.

### Interface change and the freeze rule

`errors.py` is frozen (`agent/README.md`, "Interface freeze").
The rule's procedure: an "interface change" note that names every caller, the change made alone before any work that depends on it, and the workstreams rebased onto it.
It asks for no owner sign-off, so it was followed, not bypassed.
Commit `0e14c4c` is that change alone, with every caller and the tests; its message is the note and names each writer and reader.
The change is additive: `LLMError.__init__` gains the keyword `usage=None`, subclasses keep their signatures, and no existing constructor call changes.
The three workstreams are merged, so there was nothing to rebase.
`agent/README.md` records the change under the freeze rule.

## 3. The manifest cut the branch name

Before: `refs/heads/s4/demo` was recorded as `demo` (the last path segment).
After: `s4/demo`.
A detached HEAD records `branch: null` and the commit; a missing `git` binary or no `.git` gives `dirty: null` and no crash (both already true, now tested).

## 4. "Located at" printed one location twice

Cause: the renderer, not the data.
The demo run's `report.json` has three distinct intent quotes (p.1 §1, p.2 §1, p.2 §1); `report.md` printed page and section only.
After: each location once in first-seen order, with the passage count when there are several ("p.1 §1, p.2 §1 (2 passages)"), so `report.md` agrees with `report.json`.
At the source, an exact repeat of an anchor (same document, page, section and normalised quote) is now dropped for the intent summary, findings and sound areas, so a model that cites one passage twice no longer produces a duplicate either.

## Records

`docs/USER_DECISIONS.md` #25 and `eval/prereg_deviations.md` entry 9 now name the three reasons `phases/report.py` can produce (`deadline`, `truncated`, `declined`), each with an amendment dated 2026-10-03.
Nothing was renumbered.

## Harness follow-ups (not edited; another worker owns `harness/`)

- `harness/sit_eval/metrics.py` `_efficiency` (lines 612 to 626) reports `run_manifest.usage.cost_usd`, `input_tokens` and `output_tokens` without the new flag; it should carry `extra.model.cost_usd_lower_bound` and `calls_with_unrecorded_usage` with them, or mark the cost as a lower bound.
- `eval/prereg.yaml` consumes those numbers: `costs.measured_median_full_usd` (lines 52 and 698), the efficiency metric (lines 265 and 617) and the $3.24 pilot cost gate (line 600). A median over lower bounds is a lower bound; the planner should decide whether such runs are flagged or excluded from cost statistics.
- `ManifestExtra`'s docstring says scorers never read `extra`, but `_efficiency` already reads `extra.timing`; the follow-up should settle that wording.

## Gates

`ruff check agent harness tests` exit 0.
`pytest -q` exit 0, 1061 passed, 0 skipped (1027 before).
`sit-review selftest` exit 0.
`make smoke` exit 0 (198 tests).
`make test` exit 0 (1061 passed).

## Not verified

- Anything live: no model call was made. The `usage_unrecorded` paths were exercised with injected runners, fake API clients and fake gateways only.
- How the real `claude -p` behaves when killed mid-answer (whether any usage line can be read), and whether the API bills a deadline-cut stream in full or in part.
- `connection_lost` is assigned to every API failure without an HTTP status; a connection refused before anything was sent is therefore also listed (the total is flagged as a lower bound when it may in fact be exact). That errs towards disclosure.
- A call that fails an attempt and then succeeds still adds only the successful attempt's usage to `state.budget` (`LLMResult.usage` is unchanged); the manifest totals count every attempt, as before.
- The demo run's own manifest in `SIT-wt/demo` was not rebuilt (out of scope for this worktree).
