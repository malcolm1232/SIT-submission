# Edit log: latency redesign W1, gateway and streaming

Date: 2026-10-03 (Singapore time; clock read 2026-10-02 22:52 UTC).
Worker: a fresh-context agent session on `claude-opus-5-5`.
Scope: branch `s4/w1-latency`, base `7be556d`, worktree `/Users/malco/Desktop/SIT-wt/w1`.
Authority: `docs/design/latency_and_demo_design.md` sections 2, 4, 5, 7 and 8, `docs/design/latency_w0_handoff.md` and the W1 brief.

Isolation: nothing under `eval/blind/` was opened or listed; `docs/transcripts/session3_coordinator.md` was not read.
Recorded streams were summarised by script (event types and numeric fields only); no model text was printed into the session.
Live calls: four Haiku 4.5 calls through `claude -p` with `ANTHROPIC_API_KEY` unset, no Opus call, no agent run on a document.

## Edits

| # | Commit | File | What changed | Why |
|---|---|---|---|---|
| 1 | `f020d97` | `agent/sit_review_agent/llm/runtime.py` | `RunDeadline.stage_limits`, `STAGE_LIMIT_OF_PHASE`, `describe_bound`, `effective_stage_limits`, `announce_bound`; `build_runtime` reads `stop_rules.stage_limits_s`; `cut` takes `partial` and `estimated_usage`; `deadline_warnings` puts the scaling note first. | Brief item 3: the first reader of the stage limits; a `--deadline` below them is scaled and announced. |
| 2 | `f020d97` | `agent/sit_review_agent/llm/gateway.py` | `AnthropicGateway.call` announces its bound. | Item 3: the bound is announced in the progress log on both backends. |
| 3 | `f020d97` | `tests/test_runtime_policies.py` | Seven new tests (stage budgets, the deadline winning, the cut naming its limit, `build_runtime`, scaling and its boundary, the announcement in both gateways); three reserve-warning tests now expect the scaling note first; the demo assess bound at t = 0 is 265 s, not 420 s. | Failing first (`TypeError` on `stage_limits`), then green. |
| 4 | `7d2ac15` | `agent/sit_review_agent/llm/partial.py` (new) | `JsonItemScanner`, `StreamParser`, `parse_cli_stdout`, `JSON_CHARS_PER_TOKEN` (3.3, measured). | Item 2: finished items of a streaming answer and the estimate of a cut call. |
| 5 | `7d2ac15`, `51a25c4` | `tests/test_partial_scanner.py` (new) | 17 tests; `51a25c4` adds an escaped quote before structure after mutation M1 survived. | Item 2 and the design's "a cut after 3 of 6 findings salvages 3". |
| 6 | `389880b` | `agent/sit_review_agent/progress.py` | `CallTracker`, `OpenCall`, `draft_line`, `MILESTONES`, `milestone`, `one_line`, kind `draft`; `ConsoleProgress` writes one sanitised line per event. | Item 4. |
| 7 | `389880b` | `tests/test_stream_progress.py` (new) | 6 tests. | Failing first (import error), then green. |
| 8 | `2aba936` | `agent/sit_review_agent/llm/claude_code.py` | `STREAM_FLAGS` on every argv; `subprocess_runner` streams stdout lines to `on_line` (chunked reads, no 64 KiB limit) and raises `StreamTimeout` with the stdout read so far; the answer from the last `result` event; salvage and estimate on a cut; `usage_estimate`, `salvaged_items`, `salvaged_partial` in `llm.jsonl`; draft lines and the open-call tracker. | Items 1, 2 and 4. |
| 9 | `2aba936` | `tests/test_claude_code_gateway.py` | The argv test expects `stream-json`, `--verbose`, `--include-partial-messages` and `--setting-sources ""` on the first and the resumed call. | Items 1 and 5. |
| 10 | `2aba936` | `tests/test_stream_gateway.py` (new) | 19 tests. | Failing first (import error on `StreamTimeout`), then green. |
| 11 | `2aba936` | `tests/test_stream_fixtures.py` (new), `tests/fixtures/stream/haiku_short.jsonl`, `haiku_cut.jsonl`, `haiku_trivial.jsonl`, `scrub_stream.py` | Three real streams recorded through the gateway, scrubbed by script; 11 tests replay them. | Item 7. |
| 12 | last commit, separate | `config/profiles/demo.yaml`, `tests/test_runtime_policies.py` | `report_reserve_seconds` 120 to 75 (refine stays 200) with comments; tests pin the reserves against the limits and the `--deadline 300` warning. | Item 6; held back-able: it turns three tests owned by others red (`test_config.py`, `test_config_layout.py`, `test_cli_kruns.py`; 1290 passed, 3 failed) until the changes in the report's "for the other workstream" land. |

The order was not strictly test-first for `llm/partial.py`: its code was written before its unit tests; every guard was then mutation-checked (below).

## Live check (Haiku 4.5, Claude Code 2.1.288, `--setting-sources ""`)

| Call | Outcome | Numbers |
|---|---|---|
| raw probe (same argv shape, outside the gateway) | ok | 88 lines; 1,211 input tokens; 794 answer characters for 238 visible output tokens (3.34 per token); $0.00344 |
| `haiku_short` (gateway) | ok, 3 findings, 3 draft lines before the result line | 1,250 input, 520 output (293 thinking); 749 answer characters (3.30 per token); $0.00385; 7.6 s |
| `haiku_cut` (gateway, stage 1 limit 10.5 s) | `LLMDeadlineError`, 5 findings salvaged, 1 bound line, usage `null`, `deadline_cut` | estimate 1,270 input and 1,232 output (350 thinking + 2,909 characters at 3.3); billed cost unknown (the CLI reports none for a killed call) |
| `haiku_trivial` (gateway) | ok, text `ok` | 1,131 input tokens (hermetic; design M3 measured 1,137 with another prompt), 160 output; $0.00193; 3.7 s |

A first attempt at the cut call was refused by the runtime before sending (its budget was 9.99 s against the 10 s minimum attempt), so the limit was set to 10.5 s.
Spend: $0.0092 reported by the CLI, plus the cut call, estimated at about $0.007 at Haiku list prices; under $0.02 in all.
The CLI's `thinking_tokens` events ran high (320 and 417 estimated against 208 and 293 billed).

## Scrub

`scrub_stream.py` drops the init event's machine details and the rate-limit event and replaces session ids, uuids, message, request and tool-use ids (values and dict keys), signatures and timestamps.
`grep -c` per fixture for `sk-`, `oauth`, `malco`, `/Users/`, `/private/`, email addresses, `*token*` string values, non-placeholder session ids and API object ids: 0 in each, after a second pass found tool-use ids as keys of `wire_tool_inputs`.
`tests/test_stream_fixtures.py::test_fixtures_are_scrubbed` keeps that check in the suite.

## Mutation checks (cp backup, mutate, run the named tests, restore; `git diff` empty after)

| # | Claim removed | Result |
|---|---|---|
| M1 | escape handling in the scanner | SURVIVED first; KILLED after `51a25c4` |
| M2 | only the `StructuredOutput` block is the answer | KILLED |
| M3 | a scalar item ends at its separator | KILLED |
| M4 | a cut call's logged `usage` stays null | KILLED |
| M5 | a deadline cut is not retried | KILLED |
| M6 | the salvage reaches `LLMDeadlineError.partial` | KILLED |
| M7 | log keys avoid the constructor keywords | KILLED |
| M8 | the stage limit bounds the budget | KILLED |
| M9 | a deadline at `verdict_end` is scaled | KILLED |
| M10 | `extra_args` (`--setting-sources ""`) on every argv | KILLED |
| M11 | progress lines are one sanitised line | KILLED |
| M12 | drafts are labelled unverified | KILLED |
| M13 | the answer is the last `result` event | KILLED |
| M14 | lines are delivered live by the runner | KILLED |

## Gates at `51a25c4` (before the reserve commit)

`ruff check agent harness tests` exit 0; `pytest -q` 1292 passed, 0 skipped, exit 0; `sit-review selftest` exit 0; `make smoke` exit 0 (219 passed); `make test` exit 0 (1292 passed).

## Other notes

- The leakage check (robustness OVF-07) flagged the word "board" in the first naming of the open-call tracker; it was renamed `CallTracker`.
- No tool call was refused. One reply of mine, right after reading the design document, was stopped by a safety classifier; its content was not reproduced and the work continued from the files.
