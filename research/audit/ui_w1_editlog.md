# Edit log: UI workstream W1, structured progress events

Date: 2026-10-03 (Singapore time; clock read 2026-10-03 03:09 UTC).
Worker: a fresh-context agent session on `claude-opus-5-5`.
Scope: branch `s4/ui1`, base `70bd658`, worktree `/Users/malco/Desktop/SIT-wt/ui1`.
Authority: `docs/design/ui_design.md` section 5 (the event contract) and section 9 (W1's files), the owner's ruling "1. Shape A as above. chat with opus. and build as recommended.", and the UI-W1 brief.

Isolation: nothing under `eval/blind/` was opened or listed; nothing under `docs/design/` other than `ui_design.md` was read; `docs/transcripts/session3_coordinator.md` was not read.
No model call was made and no agent run touched a real document: every run was a fixture run on the fake gateway or a scripted `claude -p` stream.
`llm.jsonl`, `progress.log`, stream fixtures and recorded model output were inspected by script only (event types, field names, counts); none was printed into the session.
No tool call was refused.

## Edits

| # | Commit | File | What changed | Why |
|---|---|---|---|---|
| 1 | `4e91e52` | `tests/test_progress_console.py` (new), `tests/fixtures/progress/console_*.txt` (new, written by the module's `--write` mode) | Three fixture scenarios (the selftest run, a run whose assess shard 2 is cut with one finished finding, a run whose understand call fails with exit 3 and its resume); their console lines were recorded on `70bd658` before any product edit and are compared line for line. | Item 1: the console text of every existing event is unchanged. |
| 2 | `4e91e52` | `agent/sit_review_agent/progress.py` | `ProgressEvent` gained `event`, `fields`, `console`, `public` and `run_s` (all with defaults); `ConsoleProgress` and `NullProgress` gained `emit_event`, `records`, `jsonl_path` and `run_clock` (their `events` list still holds console lines only); `ProgressJsonl` writes `progress.jsonl` (open, append, close per event; a resumed run continues `seq`); `emit_event`, `record_event`, `ctx_event`, `bind_run_clock`; `draft_event` (the JSONL form of a draft line: codes and a finding's title only); `ToolProgress` (types tool gateway lines, drops a policy refusal's reason); `CallEventsGateway` (the outermost LLM layer: `call_opened` when a backend numbers the call, via a hook on `next_call_id` and a context variable per task, `call_closed` on return or raise); the tracker, heartbeat and milestone lines carry their data. | Items 1 to 4. |
| 3 | `4e91e52` | `agent/sit_review_agent/orchestrator.py` | Every emit site typed with fields; `run_started` before any other event of `run_review` and `resume_run`; `run_finished` on every return and on a setup failure; the default sink writes `progress.jsonl` beside `progress.log`; the LLM stack is wrapped in `CallEventsGateway` (`_run_build_llm`) and told the shard names; the run clock is bound to the sink when the orchestrator starts it; tool gateways get `ToolProgress`; `run_error` leaves the exception text out of the JSONL. | Items 1 to 4. |
| 4 | `4e91e52` | `agent/sit_review_agent/phases/*.py` (ingest, understand, plan, research, assess, refine, verify, report, `_model_calls`) | Every `ctx.emit` became `ctx_event` with an event type and fields; console text unchanged; lines that quote model text (plan questions and skip reasons, repair problems, unknown IDs the model wrote, a registry entry's model-written reference) get a `public` message of codes and counts. | Item 1 and the no-prose rule of item 4. |
| 5 | `4e91e52` | `agent/sit_review_agent/llm/runtime.py`, `agent/sit_review_agent/llm/claude_code.py` | `announce_bound` emits `call_bounded` with the bound and limit; `ClaudeCodeGateway` emits `call_retry` and `draft_item` (call ID, shard, severity, a finding's title) through `emit_event`; additive calls only. | Item 1. |
| 6 | `efbec74` | `spec/progress_event.schema.json` (new), `spec/README.md` | JSON Schema 2020-12 for one record: the envelope, 77 event types and the required fields of each; a draft item's fields are closed (no extra key can carry prose); one table row in the spec README. | Item 4. |
| 7 | `efbec74` | `agent/README.md` | Section "Progress events": the record, the four console-less events, the main typed lines, the no-prose rule and replay. | Item 4. |
| 8 | `efbec74` | `.gitignore` | `progress.jsonl` (`progress.log` was already ignored by `*.log`). | Item 4. |
| 9 | `efbec74` | `tests/test_progress_events.py` (new) | 15 tests: plain sinks keep their shape, draft events, tracker and tool lines, every fixture event typed and schema-valid, call events, run events, failed run plus resume in one file, the file beside `progress.log`, per-event writes, no model prose, the concurrent fixture run, the deadline-cut run, replay. | Items 1 to 6. |
| 10 | `b3111a6` | `tests/test_progress_events.py` | One test on a scripted `claude -p` stream through `ClaudeCodeGateway` under the call-events layer: opened before the drafts, drafts with shard, severity and title. | Item 2 on the live backend's code path. |

Commit granularity: items 1 to 4 share `progress.py` and `orchestrator.py` functions, so their code landed in one commit (`4e91e52`, with the item 1 console test); the tests of items 2 to 6 and the schema landed in `efbec74`; the brief asked for a commit per item, which was not met for that reason.

## Design choices

- The four new events (`run_started`, `call_opened`, `call_closed`, `run_finished`) have no console line, so the console and `progress.log` are byte for byte unchanged; the page reads them from `progress.jsonl`.
- `call_opened` carries the backend's own call ID: the layer hooks `next_call_id` on the layers below it (Anthropic, Claude Code, fake), and a context variable names the logical call of the asking task, so four concurrent shards are never confused. `ReplayLLMGateway` takes its IDs from the recording, so in a replay `call_opened` comes when the call ends, just before `call_closed`; the event sequence is the same as the recorded fixture run's, but a replay's page shows each call as opened and closed at once.
- `t` is the console's clock (since the sink's first event); `run_s` is the run clock (resume-adjusted), bound when the orchestrator starts it, so the setup events have `run_s: null`.
- The scripted fake gateway answers without suspending, so a plain fixture run opens and closes each call in turn; the concurrent test (`HoldStage1`) holds the first stage 1 calls until all six are open, which is what a live run does.
- Run identity in `run_started` and `run_finished`: the profile is read from `cli_args` (`null` for a run without `--profile`).

## Mutation checks (remove the claim, run its test, restore from a `cp` backup; `git diff --quiet` clean after each)

| # | Mutation | Test | Result |
|---|---|---|---|
| M1 | one console message changed (assess shard drafted line) | `test_progress_console.py` | failed (AssertionError) |
| M2 | `plan_ready` typed back to `status` | `test_every_event_of_the_fixture_runs_is_typed_and_valid` | failed |
| M3 | `call_opened` only at close (ID hook off) | `test_concurrent_fixture_run_streams_the_design_order` | failed (`[4] == [1, 2, 3, 4]`) |
| M4 | no call-events layer | `test_every_model_call_opens_once_and_closes_once` | failed |
| M5 | `run_started` removed from `run_review` | `test_run_started_comes_first_and_run_finished_last` | failed |
| M6 | `run_finished` missing on the normal path | same | failed |
| M7 | JSONL buffered three events at a time | `test_each_event_is_on_disk_when_emit_returns` | failed (FileNotFoundError) |
| M8 | a resumed run restarts `seq` at 1 | `test_a_failed_run_finishes_with_its_exit_code_and_resume_continues_the_file` | failed |
| M9 | plan question written with its model text | `test_the_stream_carries_no_model_prose` | failed |
| M10 | draft item keeps the statement | `test_draft_event_keeps_codes_and_a_finding_title_only` | failed |
| M11 | no fallback open for a backend without `next_call_id` | `test_replay_produces_the_same_event_sequence` | failed |
| M12 | shard cut without what it kept | `test_concurrent_deadline_cut_run_shows_the_cut_and_what_it_kept` | failed (schema ValidationError) |
| M13 | `progress.jsonl` not gitignored | `test_a_run_writes_progress_jsonl_beside_progress_log` | failed |
| M14 | an extra envelope key | `test_every_event_of_the_fixture_runs_is_typed_and_valid` | failed (schema ValidationError) |
| M15 | `call_opened` only at close, Claude Code stream | `test_claude_code_calls_open_before_their_streamed_drafts` | failed |
| M16 | draft item without its shard | same | failed |

No mutation survived.

## Gates (exit codes read, one per call)

`ruff check agent harness tests` 0; `pytest -q` from the repo root 0 (1576 passed, 1557 at the base, 19 new); `sit-review selftest` 0; `make smoke` 0 (238 passed); `make test` 0 (1576 passed at `9d26c61`); `python scripts/leakage_grep.py` 0 (PASS).
`scripts/leakage_grep.py --strict` exits 1 on hits outside this workstream's files (none in a file this workstream touched); it is not the gate.
