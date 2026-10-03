# Edit log: MCP session recovery and the defects of sit_sample_tools_1

Date: 2026-10-03 (Singapore time; clock read 13:29 +08 before this log was written).
Worker: a fresh-context agent session on `claude-opus-5-5`.
Scope: branch `s4/mcpfix`, base `8901ccd`, worktree `/Users/malco/Desktop/SIT-wt/mcpfix`; not pushed.
Source: `docs/live_runs/sit_sample_tools_1/MEASUREMENT.md`, section "Defects this run exposes", defects 1 to 6 (defect 7 is reported, not changed).

Isolation: nothing under `eval/blind/` was opened or listed.
Nothing under `docs/design/` or `docs/transcripts/` was read; only `MEASUREMENT.md` of the run was read.
`llm.jsonl`, `progress.log` and the recorded model output were never printed; `report.json` and `tools.jsonl` were inspected by script, by field names and counts.
One test failure printed a fragment of the rendered `report.md` verdict conditions; the assertion was rewritten so failures no longer print report text.
No call reached the SIT MCP hosts and no model call was made: every test uses fake sessions, the in-process MCP server over `httpx2.ASGITransport`, or the strict cassettes.
`agent/sit_review_agent/ui/` and the stage logic of `orchestrator.py` were not changed.

## Reproduction before the change

The new tests were written against the run's shape and failed on the base where they test a defect.
A fake server that closes its session after an idle period, with five concurrent `search_web` calls after 130 s idle, gave five `tool_error` results on the base classifier (`MCPError -32000` fell through to `TOOL_ERROR`).
The research fixture with five failing web searches, one scholarly success and a model stop vote with nothing answered reported `sufficient_evidence (model_stop_vote)`, as the run did.

## Edits

| # | Commit | File | What changed | Why |
|---|---|---|---|---|
| 0 | `6923a69` | `tools/gateway.py`, `tools/faults.py`, `config.py`, `config/tools.yaml`, `agent/README.md` | Interface change, additive: `ToolErrorClass.SESSION_CLOSED`, `FaultType.SESSION_CLOSED`, `ToolsConfig.session_idle_reopen_s` (default 60) with the YAML key below the pinned lines and a comment citing the run and the probe. | The freeze rule in `agent/README.md`: a frozen enum or config key changes alone, with the callers named. |
| 1 | `7678db2` | `tools/mcp_client.py` | `-32000` (mcp `CONNECTION_CLOSED`), anyio closed, broken and ended streams, a connection reset or broken pipe (also when wrapped by `httpx2.ReadError`) on an established session classify as `SESSION_CLOSED`; on first contact they keep their cold-start or connection meaning. | Defect 1: a closed session was a tool error. |
| 1 | `7678db2` | `tools/gateway.py` `MCPToolGateway` | On `SESSION_CLOSED` the session is reopened once (unless a concurrent call already replaced that connection) and the call repeated once; a second failure is returned and the session dropped. A session idle longer than `session_idle_reopen_s` with no call in flight is reopened before the call. Each reopen is a progress line, an entry in `session_events` and the message of the call's attempt. | Defect 1, and the run's five concurrent calls on one dead session. |
| 2 | `3488d81` | `tools/gateway.py` `PolicyToolGateway`, `genuine_failure` | A tool is disabled after two genuine failures in a row: a tool error from a live session, or a closed session met again after the reopen. Per-tool counts are kept and named in the disclosure. | The run disabled `search_web` on session errors alone. |
| 3 | `b86cbcb` | `phases/research.py` | At the end of research each `tool_error` degradation is restated: N of M calls failed (class xN), the last error, whether the tool was disabled, successes, and the unanswered questions of its capability. One degradation per server, tool and class. | Defect 2: DEG-002 read as one failed call. |
| 4 | `52f83b0` | `phases/research.py`, `tests/test_research_phase.py` | A model stop vote maps to `sufficient_evidence` only with an answered question; otherwise `tool_failure` (every call failed, or an offered tool was disabled) or `no_marginal_gain`. No new enum value. `test_model_stop_vote_is_advisory` now expects `no_marginal_gain` for its vote with nothing answered. | Defect 3. |
| 5 | `c9f6540` | `report/render.py`, `report/templates/report.md.j2`, `phases/understand.py` | Severity counts in the verdict prose rewritten to the findings' counts; the document version stored without its word prefix and shown through `version_label`; `_md` keeps bullet and numbered lists. | Defects 4, 5 and 6. |
| 6 | `d23af50` | `tests/test_mcp_session_recovery.py` | The run's recorded tool results replay as recorded through `JournalReplayToolGateway`. | Item 6 of the brief. |
| 7 | `d5fa341` | `tests/robustness/*`, `research/robustness/scenarios.md`, `research/robustness/README.md` | NET-06 row (S1, P0, L0), schedule, harness live-MCP base over the cassettes, oracle, counts 81 to 82, results regenerated. | Item 7 of the brief. |

## Decisions taken here

- The idle default is 60 s: the probe measured cold starts of 29 to 70 s against 0.04 s warm on scale-to-zero containers, and the run's session died somewhere between 2 s and 132 s idle; the real idle timeout is unknown.
- The stop-reason rule is stricter than the brief's "an answer or new external evidence": with that rule the run would still have reported `sufficient_evidence`, because the one scholarly call added 10 ledger entries while 0 of 9 questions were answered.
- The brief's names `no_usable_tools` and `model_stopped_early` map to the existing `tool_failure` and `no_marginal_gain`, so `spec/finding.schema.json`, `spec/taxonomy.yaml` and `models.StopReasonCode` are unchanged.
- The report fixes live in the renderer (and, for the version, in `understand` too); `report.json` keeps the model's own text.
- NET-06 is a new P0 row rather than a seventh concurrent scenario, so the P0 count moved from 81 to 82 everywhere it is pinned.
- No existing robustness row assumed that a closed session is a tool error; none was rewritten.

## Mutation testing

Every guard was mutated from a `cp` backup, the tests run, and the file restored.
Item 1: 9 guards, 9 killed (one by a hang past the 90 s limit: an unbounded retry); the concurrent-reopen guard and the `limit > 0` guard first survived and were killed after a late-failure test and a reason assertion were added.
Item 2: 5 guards, 5 killed; the "any session error counts" mutant first survived and was killed by a test of an unrecovered session error.
Item 3: 4 of 4 killed. Item 4: 3 of 3 killed. Item 5: 5 of 5 killed. NET-06 oracle: 3 of 3 killed.

## Gates (exit codes)

- `ruff check agent harness tests`: 0.
- `pytest -q` from the repo root: 0, 1586 passed (1559 at the base).
- `sit-review selftest`: 0.
- `make smoke`: 0. `make test`: 0.
- `pytest tests/robustness -q`: 0, 161 passed; results regenerated with `ROBUSTNESS_RESULTS_CSV` (P0 88 rows, 56 PASS, 32 BLOCKED, 0 FAIL).
- `python scripts/leakage_grep.py`: 0.

## Not verified

- The SIT servers' real idle timeout, and whether a reopen succeeds against them.
- The full `dra replay` of `sit_sample_tools_1`: the lab's PDF is not in this worktree, so the replay stops at exit 2 naming the missing input.
