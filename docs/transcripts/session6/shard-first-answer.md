# Worker note: a shard ends at its first complete answer, 2026-10-04

Brief: the planner's fix of defects 1 and 2 of `docs/live_runs/sit_sample_ui_2/MEASUREMENT.md` (stage 1 at 265.2 s with six shards; three shards wrote their answer twice; shard 3 kept its half-written repeat).
Malcolm's word: 3 Oct 2026 22:55, "fix what u need to fix", under his delegation of shot calling to the planner.
Branch `s4/shard-first-answer` from `origin/claude/happy-darwin-d0bl94` at 4a2a8b5.
Only `MEASUREMENT.md` and `llm_calls.json` of the run were read (counts and durations); the recorded stream fixtures were summarised by script (event types and counts only).

## The cause

`claude -p --json-schema` checks each `StructuredOutput` call against the schema itself.
In a normal call the stream is: one API message writing the answer block, the CLI's tool result, the message's final counts, then the `result` event with `num_turns` 2 and no second API message (the three recorded fixtures under `tests/fixtures/stream/` all end this way).
When the CLI's own check rejects a complete answer, it sends the rejection back as the tool result and the model writes the whole answer again in a new API message; the CLI has a retry limit for this (`error_max_structured_output_retries`, already handled by the gateway).
The run's numbers match that and nothing else: shards 4 and 6 took 3 CLI turns where every other call took 2, they are the only shards with cache reads (37,103 and 30,960 tokens, the second request reading the first from the cache), their output tokens are about double (30,271 and 33,576 against 15,248 to 20,662), and the streamed item numbers restarted at 1.
The gateway did nothing to cause it: it sends no "continue" turn, does no retry (every `attempt` is 0), and reads only the last `result` event.

Not known: which schema rule the CLI applied.
The rejection text is not in the record (the gateway did not keep the stream's tool results).
The schema the CLI checks (`outputs.llm_facing_schema`) has the length, range and pattern keywords stripped, so the CLI enforces only types, `enum`, `required` and `additionalProperties: false`; the gateway's own check (Pydantic, `extra="forbid"` on every assess model, lax mode) is stricter on lengths and ranges and looser on types (it coerces a number written as a string, for example).
So an answer the CLI rejects may or may not pass the gateway's check; the fix helps exactly when it does, and the next run now records the rejection text so the rule can be named (below).

## Part 1: end the call at the first complete answer the gateway accepts (af12daf)

- `llm/partial.py`: `StreamParser` keeps every complete answer block (`answers`, parsed at the block's `content_block_stop`), asks an `accept` callback whether it is usable, and remembers the first one accepted (`accepted`, with the API message that wrote it).
  With `stop_on_repeat` a new `message_start` after an accepted answer raises `RepeatedAnswer`.
  It also keeps each API message's usage (`message_start` counts, replaced by the `message_delta` final counts) and the CLI's tool results for answers it did not take (`rejections`: `is_error` true, or followed by another API message; first 500 characters).
- `llm/claude_code.py`: `_interpret` is split into `_interpret_data`; `_usable` runs the same checks without issuing tool-call ids, and is the parser's `accept`.
  `stop_on_repeat` is on only for a live runner (one that takes `on_line`, as `subprocess_runner` does).
  `RepeatedAnswer` raised inside `on_line` ends `subprocess_runner`, which kills `claude -p` (its existing `except BaseException` path); `_attempt` then builds the result from the accepted answer: `num_turns` 2, `terminal_reason: first_complete_answer`, usage measured from the streamed messages (the answering message in full plus the input of the message the CLI had just started; nothing estimated), cost at the manifest's list prices (`cost_basis: list_price`, as no `result` event carries `total_cost_usd`).
  `llm.jsonl` gets `ended_at_first_answer`, `complete_answers`, `cli_messages`, `usage_basis: stream_messages`, and `cli_answer_rejections` whenever the CLI rejected an answer (also on calls that ran to the end, and on cut calls).
- The trigger is the next API message, not the answer block itself, so a normal call still ends on the CLI's own `result` event with its measured usage and cost; the wait it adds over ending at the block is the CLI's tool result plus the start of the next message (the record shows 10.7 s from shard 3's first complete answer to the first finding of its repeat; the next message starts early in that gap).
- An answer the gateway's check also rejects is left to the CLI's retry, as before (a schema-invalid answer would otherwise cost the phase's own repair call).
- A runner that is not live (`on_line` not accepted) cannot be ended early; it keeps the CLI's final answer, as before.
- Tests (`tests/test_stream_gateway.py`, 7): two identical complete answers end the call as the second API message starts (`num_turns` 2, measured usage 4 / 15,001 / 42,549 / 37,103, list-price cost, the rejection logged); a second, different answer is not used; a first answer the gateway rejects lets the CLI ask again (`num_turns` 3, the result event's usage); a single answer still ends on the result event; a repeated tool-call envelope ends at the first; a legacy runner keeps the CLI's answer; the real `subprocess_runner` is killed at the repeat (the child sleeps 30 s after its lines; the call returns in under 10 s).
  Mutation check: with `stop_on_repeat=False` four of them fail; restored and `cmp`-checked.

## Part 2: keep the last complete answer when the limit ends a repeat (5b3908b)

- Cause of the lost answer: `StreamParser` started a fresh item scanner at every `StructuredOutput` block, so `partial()` after a cut held only the items of the half-written repeat.
- `llm/partial.py`: `partial()` returns the last complete answer block (at the envelope's `final` for a tool envelope) when there is one, else the finished items of the block being written; `partial_complete()` says which; `salvaged_count()` counts what `partial()` holds (the live `item_count()` still follows the block being written, for the progress line).
- `errors.py`: `LLMDeadlineError(partial_complete=...)`; `llm/runtime.py`: `RunDeadline.cut` passes it; `llm/claude_code.py`: logged as `partial_complete: true`, and `salvaged_items` is now the kept answer's count. The manifest's `salvaged_items` was already computed from the logged `partial`, so it follows the kept answer with no change; `replay.recorded_error` rebuilds the flag from the entry by name.
- `phases/_model_calls.py`: `PhaseCall.partial_complete`; the `call_cut` event carries `complete`.
- `phases/assess.py`: a shard whose kept answer is complete is disclosed as "assess shard k/n (name) ended at the stage 1 limit at T s after a complete answer, while the model was writing it a second time; the complete answer was kept: F finding(s), S sound area(s), C coverage row(s) (cut call ...)", impact "the shard's complete answer is in the report; only its unfinished repeat was lost" (or the not-assessed criteria, if any lack a finding); the `shard_cut` event carries `complete`.
- Tests: `tests/test_stream_gateway.py` (2): one complete answer of 13 findings, 2 sound areas and 2 coverage rows followed by a repeat cut at the limit after 5 findings keeps 13 / 2 / 2 (`partial_complete`, `salvaged_items` 17, the manifest's `logged_salvage` 17, replay rebuilds the flag); a cut inside the first answer is not complete and keeps 5. `tests/test_llm_phases.py` (1): the assess phase given that cut keeps 13 finding drafts, 2 sound areas and 2 coverage rows and writes the disclosure above.
  Mutation check: with `partial()` back to the scanner snapshot the 13 / 2 / 2 test fails; restored and `cmp`-checked.

## Two flaky tests fixed on the way (66e056f, 6fb4579)

- `tests/test_ui_honesty.py::test_the_rail_shows_the_stream_state_and_the_recorded_servers_and_never_probes` failed once in the full suite at a 5-minute load near 6: it read the rail entry as soon as the first status rows showed, with the page part way through the fixture stream ("assess · 01:33"). It now waits for the expected entry text.
- `tests/test_stream_gateway.py::test_subprocess_runner_streams_lines_as_they_arrive` failed once at a load near 9 (two lines 0.05 s apart arrived in one read: 0.051 s against 0.08). The child now writes one line and waits until the parent's `on_line` has seen it, so the run ends only if lines are delivered live.

## Offline check

`sit-review selftest` before and after: `selftest passed`, every check `ok` (INV-08 `skip` as before), 0.4 s; the selftest and the replay path run on `FakeGateway` and `ReplayLLMGateway`, which never read a `claude -p` stream, so no timing or count of theirs can change.
No offline fixture reproduces the repeat itself (no recorded stream has a rejected answer); the new scripted streams above are the offline evidence.
What would have changed on the 4 Oct run, if the gateway's check accepts the rejected answers: shards 4 and 6 end at about 151 and 166 s plus the start of the next message instead of 235.4 and 257.2 s, shard 3 at about 217 s instead of being cut, so stage 1 ends near 220 s; if it does not accept them, part 2 still keeps shard 3's 13 findings, 2 sound areas and 2 coverage rows instead of 5 findings.

## Gates

Run before the last commit, at 5-minute loads of 8.9 to 10.1 with 41 to 52 percent free memory:
`ruff check agent harness tests`: All checks passed.
Full suite from the worktree: 1944 passed, 1 skipped, 2 xfailed; from `~`: the same.
`sit-review selftest`: selftest passed. `make smoke`: exit 0. `scripts/leakage_grep.py`: PASS. `python -m sit_review_agent.prompts --check`: PROMPTS.lock up to date.

## Not done, and why

- The live check (stage 1 at or under 230 s) is a later rehearsal from Malcolm's Terminal; it is also the run that will log `cli_answer_rejections` and so name the rule the CLI applies.
  If the rejected answers turn out to fail the gateway's check too, the next step is a schema change (make the CLI's schema and the Pydantic check agree), not a timeout.
- After an early end the conversation's next call, if any, resumes from the killed CLI session; that transcript ends with the CLI's rejection tool result. Assess shards make one call per conversation, so this does not arise for them; a refine rule repair or a research turn after an early end would see it. The CLI's cumulative `total_cost_usd` and `modelUsage` for such a resumed session are not known; the gateway carries its own list-price figure forward.
- The usage estimate of a call cut during a repeat still counts only the block being written (`answer_chars` resets per block), so it reads low for such a call; the measured counts of the finished first message are available in the parser but are not yet added to the estimate.
