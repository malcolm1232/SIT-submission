# Session 4: second-truncation fallback (2026-10-03)

Worker: a fresh Opus session, one deliverable.
Branch `s4/integration`, worktree `SIT-wt/integration`, from `2d84f59`.
Edits and mutations are in `research/audit/verify_runtime_cli_editlog.md`, section "Session 4 second-truncation fallback".

## Ruling applied

A stage whose answer is cut off at the output cap on its call and on its one retry is treated like a deadline cut.
The run continues with the stage's deadline fallback and discloses the truncation.
No stage splitting, no prompt change, no third attempt.

## Behaviour per stage

| Stage | Before | After |
|---|---|---|
| understand | 2 calls, exit 3, no report | 2 calls; no intent or registry (the deadline fallback); report written, exit 0 |
| plan | 2 calls, exit 3, no report | 2 calls; one document-only question per criterion, each rationale saying "the plan answer was truncated twice at the output cap"; exit 0 |
| assess | 2 calls, exit 3, no report | 2 calls; no findings; verdict `not_assessed`, shown as "Not assessed (answer truncated twice at the output cap)"; no verdict call; exit 0 |
| refine | 2 calls, exit 3, no report, assess findings lost | 2 calls; the assess findings kept, unrefined (provenance `assess`); exit 0 |
| research, verify, report | 1 call, disclosed degradation, exit 0 | unchanged (they make no truncation retry, so they do not share this path) |

Every degraded run above ends with manifest outcome `completed_degraded`, the exit code a deadline-degraded run already uses (0).

## How a reader tells the causes apart

- Truncation: degradation type `other`, event "the <stage> answer was truncated twice at the output cap (max_tokens=N; the call and its one retry, <call IDs>)".
- Deadline: type `budget_or_deadline_hit`, event "out of time before assessment: ..." or "the <stage> call was cut by the run deadline".
- Refusal: type `other`, event "the model declined the <stage> call ...", and the stage is in `declined_sections`.

The same wording reaches `report.json` (degradation, limitation, verdict rationale, coverage notes), `report.md` (verdict label, limitations, coverage table), the progress log ("<stage>: answer truncated twice at the output cap") and the manifest (`extra.model.truncations`).
The stop reason stays research's own; it never says `deadline` for a truncation.

## Enums

No enum value was added or changed.
The not-assessed reason is a code-side key (`deadline`, `truncated`, `declined` in `phases/report.py`), not a schema value; the schema and taxonomy text of `not_assessed` now name the truncation.

## Accounting

Both truncated calls are in `llm.jsonl` with their usage, so the manifest's token and cost totals include them; a run-level test with billed usage on the truncated calls checks this.
`state.budget` (read by the `budget_tokens` stop rule) still does not count failed calls, as before, because `LLMTruncatedError` carries no usage (`errors.py` is frozen).

## Resume

The run no longer fails, so no `failure.json` offers it as resumable.
`sit-review resume` on it prints the existing report path, exits 0 and makes no model call (tested in the harness and through the CLI).
A rerun is a new run, which may or may not fit (answer length varies between calls).

## Harness

`harness/` was not touched.

## Gates

`ruff check agent harness tests` exit 0.
`pytest -q` exit 0, 1027 passed, 0 skipped (1023 before).
`sit-review selftest` exit 0.
`make smoke` exit 0 (197 tests).
`make test` exit 0 (1027 passed).

## Not verified

- Anything live: a real Opus answer truncated at 128000 through `claude -p` or the API.
- The billed usage the CLI reports on a truncated `claude -p` call (only `FakeGateway` usage was tested; `ClaudeCodeGateway` logs `usage` and `call_cost_usd` on failures, read, not run).
- `docs/USER_DECISIONS.md` #25 and `eval/prereg_deviations.md` entry 9 list two not-assessed reasons; they are owner and planner records and were left for the planner.
