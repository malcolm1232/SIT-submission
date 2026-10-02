# Latency redesign W1: gateway and streaming, report

Date: 2026-10-03.
Branch `s4/w1-latency` from `7be556d`, not pushed.
Commits: `f020d97` stage limits, `7d2ac15` partial parsing, `389880b` progress, `2aba936` streamed gateway and fixtures, `51a25c4` scanner test, then the edit log and this report, then the demo reserves alone as the last commit.
Edit log: `research/audit/latency_w1_editlog.md` (edits, live numbers, scrub, mutation table, gates).

## Deliverables

1. Streamed CLI output: DONE.
   Every argv carries `--output-format stream-json --verbose --include-partial-messages` (flags checked against `claude --help`, Claude Code 2.1.288).
   `subprocess_runner` reads stdout in chunks, hands each line to the attempt's `StreamParser` as it arrives and keeps what it read when the timeout kills the child (`StreamTimeout`).
   The answer is the last `result` event, which carries the same object `--output-format json` printed, so every error class is raised on the same condition; a stream with no `result` event is the old "without a JSON result" process fault.
   The JSON output mode is removed from the gateway, not kept behind a switch: nothing reads raw CLI stdout after the call (replay reads `llm.jsonl`, never stdout), and the parser still accepts a single JSON object, which is what the harness judges (`harness/sit_eval/live_judges.py`, own argv) and the injected test runners of other workstreams produce.
2. Partial parsing and salvage: DONE (`llm/partial.py`).
   The scanner reports each finished item of a root-level list (findings, revisions, registry entries, questions; inside `final` for the tool envelope) and each closed root field; an item counts only once its JSON closed.
   A deadline or stage-limit cut raises `LLMDeadlineError(partial=..., estimated_usage=...)`; measured `usage` stays `None`, the `llm.jsonl` entry keeps `usage: null` and `usage_unrecorded: deadline_cut`, and the estimate is logged apart as `usage_estimate` with `estimated: true` and its basis.
   Estimate: input tokens and cache counts from `message_start`; output tokens as the CLI's last `thinking_tokens` estimate plus streamed characters at 3.3 per token (measured on two Haiku answers: 3.30 and 3.34).
3. Stage limits as a reader: DONE (`llm/runtime.py`).
   A call's budget is the lesser of the time to the deadline and the time to its stage's limit (stage 1: understand, plan, research, assess; refine; verify and the verdict call share `verdict_end`); one progress line announces each bound.
   Choice: a `--deadline` at or below `verdict_end` SCALES the three limits by `deadline / (refine_end + report_reserve_seconds)` and says so on the first progress lines.
   Why: refusing would stop the runbook's `--profile demo --deadline 300` rerun before it starts; scaling keeps every stage and gives stage 1, the only source of findings, the largest share (147 s of 300), and a shard cut there keeps its finished findings.
   At the measured rates (thinking about 105 s per shard, then about 310 characters per second, design M6) 147 s leaves roughly 40 s of streaming per shard, about two findings each; that is a prediction, not a measurement.
4. Progress from the event stream: DONE (`progress.py`).
   `CallTracker` prints one line at least every 10 s listing each open call with its thinking estimate or streamed item count (one line for all concurrent calls); each finished item is a `DRAFT` line labelled draft and unverified; `milestone()` and `MILESTONES` name the four stage milestones for W2 to call.
   Every console and `progress.log` line is one sanitised physical line (no newline, ANSI sequence or control character from model text); progress never writes to the structured logs.
5. Hermetic settings: DONE.
   `--setting-sources ""` comes from `claude_code.extra_args` and is asserted on the first and the resumed argv in `tests/test_claude_code_gateway.py` and on every argv in `tests/test_stream_gateway.py`.
6. Demo reserves: DONE in the last commit, kept separate.
   `report_reserve_seconds` 120 to 75, `refine_reserve_seconds` stays 200; 540 - 75 - 200 = 265 and 540 - 75 = 465 match the stage limits (pinned by a new test).
   It turns three tests owned by others red until the changes listed below land: `tests/test_config.py::test_refine_reserve_replaces_assess_reserve`, `tests/test_config_layout.py::test_demo_profile_lines_named_by_the_runbook` and `tests/test_cli_kruns.py::test_demo_profile_and_a_deadline_that_does_not_fit_the_reserves`; the commit can be held back on its own.
7. Live check on Haiku: DONE, under $0.02.
   Three streams recorded through the gateway into `tests/fixtures/stream/` (a three-finding answer, an answer cut by a 10.5 s stage limit with 5 findings salvaged, a trivial text answer), scrubbed by `scrub_stream.py`; all grep counts 0.
   Hermetic input tokens on the trivial call: 1,131 (design M3: 1,137 with a different prompt and schema; 2,570 with the user settings, M2).

## Tests and gates

1292 passed, 0 skipped at `51a25c4` (1231 at `7be556d`: 61 new tests); ruff, `sit-review selftest`, `make smoke` and `make test` exit 0.
At the reserve commit the three tests named in item 6 fail by design (1290 passed, 3 failed); ruff passes.
Fourteen mutations, all killed; the first (the scanner's escape handling) survived until `51a25c4` added a string with an escaped quote before structure.

## Not verified

- Any Opus stream: the characters-per-token figure, the thinking estimate and the event shapes were seen on Haiku only; an Opus shard streams 1,154 to 1,358 deltas (design M7) and was not recorded.
- A cloud session: `--setting-sources ""` and the stream flags with `--resume --fork-session` were not run there.
- The scaled 300 s run producing findings: no agent run was made; the claim rests on the design's measured rates.
- The billed cost of a killed call: the CLI reports none, so the estimate is unchecked against a bill.
- The open-call status line in a live multi-call run (tested with injected runners and real asyncio time only).

## Writes beyond my list

None.
`research/audit/latency_w1_editlog.md` and this report are the two files the brief asked for.

## For the other workstream

W2 (orchestrator, phases):
- `orchestrator.py`: call `sit_review_agent.progress.milestone(ctx.progress, "intent", "understand", registry_entries=<n>)` when understand ends, `milestone(..., "plan", "plan", questions=<n>)` when plan ends, `milestone(..., "merged", "refine", findings=<n>, shards=<k>)` after the merge, and `milestone(..., "verified", "report", findings=<n>)` when the report is written.
- `phases/assess.py` (and refine, understand, plan): on `LLMDeadlineError`, read `err.partial` (`{"findings": [...]}` for a shard; for a tool-envelope call it is already the content of `final`), validate each item against its draft type one by one and drop the ones that fail; budget from `err.usage` only, never `err.estimated_usage`.
- The runtime now bounds assess by `stage_1_end`, so the current sequential orchestrator gives a demo assess call at most 265 s minus understand and plan; the concurrent stage 1 must land before a demo rehearsal.
- `phases/research._ResearchRun` still keeps `report_reserve_seconds + refine_reserve_seconds` as its own reserve (`tests/test_runtime_policies.py::test_research_keeps_the_refine_reserve` pins it); the model calls inside research are now bounded by `stage_1_end` as well, which on the shipped profiles is the same second.

W3 (replay, manifest, docs, robustness):
- `replay.py` `recorded_error`: for an `LLMDeadlineError` entry, map `salvaged_partial` to `partial` and `usage_estimate` to `estimated_usage=Usage(input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens)` (drop `estimated` and `basis`); ignore `salvaged_items`. The entry has no key named `partial` or `estimated_usage` (pinned by `tests/test_stream_gateway.py`).
- `manifest.py`: cut calls are entries with `usage_unrecorded: deadline_cut`; count them with `estimated: true` from `usage_estimate`, and the salvage count is the sum of their `salvaged_items`.
- `docs/DEMO_DAY_RUNBOOK.md` line 50: replace "(`WARN deadline 300 s leaves research no time ...`): at 300 s the demo profile's reserves (120 s + 200 s) leave research nothing and give understand, plan and assess 180 s together, so the rerun is document-only" with "(`WARN deadline 300 s is not above this profile's stage limits ... scaled by 300/540 to 147 / 258 / 294 s ...`): the rerun keeps every stage, stage 1 ends by 147 s and a shard still streaming then keeps its finished findings".
- Runbook line 82: "the two reserves (verify + report 120 s, assess 200 s)" becomes "the two reserves (verify and the verdict 75 s, refine 200 s) and the stage limits 265 / 465 / 530 s".
- Runbook line 128: "Research stops by 220 s at the latest, so that assess keeps 200 s. Every model call before verify is cut at 420 s, so that verify and report keep 120 s." becomes "Stage 1 (understand, plan, research and the four assess shards) ends by 265 s, so that refine keeps 200 s. Refine is cut at 465 s, so that verify and the verdict keep 75 s."; lines 130 and 131 need the same times (4:10 and 7:30 become the stage 1 and refine limits) once W2's order is final.
- Then `tests/test_config_layout.py` line 67: `"report_reserve_seconds: 120"` becomes `"report_reserve_seconds: 75"`; lines 69-70: the needles `"Research stops by 220 s"`, `"is cut at 420 s"`, `"verify and report keep 120 s"` become `"Stage 1 (understand, plan, research and the four assess shards) ends by 265 s"`, `"Refine is cut at 465 s"`, `"verify and the verdict keep 75 s"`.
- `tests/test_config.py` line 180 (W0's file, integration pass): `(200, 120)` becomes `(200, 75)`.
- `tests/test_cli_kruns.py` (integration pass): line 165 `(540, 120, 200)` becomes `(540, 75, 200)`; line 176 becomes `assert "WARN deadline 300 s is not above this profile's stage limits" in res.output and "scaled by 300/540 to 147 / 258 / 294 s" in res.output and "leaves research no time" not in res.output` (with the demo reserves of 75 s and 200 s, research keeps 25 s at 300 s, so only the scaling note is printed). Line 173 (default reserves) still holds.
- `agent/README.md` module map: `llm/partial.py` (new), `llm/runtime.py` stage limits, `progress.py` `CallTracker`, draft lines and milestones. No frozen interface changed (`llm/gateway.py` gained only a call to `announce_bound`).
- `tests/robustness`: LLM-05 can now expect `err.partial` from a recorded cut; `tests/fixtures/stream/haiku_cut.jsonl` with `StreamTimeout` is a ready input.
