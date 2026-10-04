# Docs refresh: reader-facing documents brought in line with the code

Date: 4 October 2026, branch `s4/docs-refresh` from `origin/claude/happy-darwin-d0bl94` at 49dcf73.
Owner's word: 3 Oct 2026 22:55, "fix what u need to fix", under the planner's delegated shot calling.
Each item was checked against the named code before the edit.

## Items and evidence

1. Six assess shards, not four.
   Evidence: `config/agent.yaml` `shards` lists six groups, "Six groups since USER_DECISIONS #40".
   Fixed: `docs/ARCHITECTURE.md` §2 text and diagram (A5, A6 added), §3, §12 row 2, §13 points 3 and 4; `docs/DEMO_DAY_SCRIPT.md` rows 02:04, 02:36, the S+09:30 line, and the new-criterion row (a fifth shard is now a seventh); `config/profiles/demo.yaml` `stage_1_end` comment; `docs/LIMITATIONS.md`; `README.md` config table.
   Left as history: handovers, `docs/HANDOFF.md`, `docs/BUDGET.md` line 205 (a record of a past cost change), `docs/USER_DECISIONS.md`, transcripts, live-run records.
2. Robustness 88 scenarios, 56 passing: `tests/robustness/results/robustness_summary.txt` (P0 88, PASS 56, BLOCKED 32); DEMO_DAY_SCRIPT row 07:56 fixed.
3. `config/profiles/demo.yaml` header: "does NOT fit 540 s" replaced by the two measurements (3 Oct cut at assess, 4 Oct ended at 508.5 s, from `docs/EXPLAIN_AS_IT_RUNS.md`) and 540 s as a configurable assumption (USER_DECISIONS #34).
   The header keeps four lines, so the pinned lines 19-24 and 27 and the words `UNMEASURED`, `USER_DECISIONS #1`, `forks` that `tests/test_config_layout.py` and `tests/test_runtime_policies.py` read are unchanged.
4. `docs/LIMITATIONS.md`:
   - MCP session fix seen live on 4 Oct (8 calls retried after 3 reopens, all succeeded; `docs/EXPLAIN_AS_IT_RUNS.md` line 94).
   - Cost with working search: $7.37 lower bound, about $8.86 with the estimate (`docs/EXPLAIN_AS_IT_RUNS.md` lines 169 and 269).
   - Prior-finding classification: `agent/sit_review_agent/delta.py` (`not re-examined`), `llm/outputs.py` `prior_status_problems`, `invariants.py` `check_INV_13` (commit 1905eed, after the 3 Oct re-assessment run 353390b).
   - External evidence: the cold reader was right. `FindingRevisionDraft.added_evidence` (refine keep) is the only path from the ledger into a finding; the verdict call's `VerdictOutput` has no evidence field and `prompts/report.md` gives it the findings, objectives, research stop reason and degradations, not the ledger. Written that way.
5. ARCHITECTURE §4: `llm/partial.py` `StreamParser.partial` returns `_last_complete()` else the scanner snapshot (5b3908b); `llm/claude_code.py` passes `stop_on_repeat=self._runner_streams and not request.tools` (af12daf, 95e2f0d).
6. ARCHITECTURE §2 refine: `phases/refine.py` docstring "Repair for the failing revisions only", `split_revisions`, `repair_outcome`, `salvage_revisions` (df841bf, c1117f3).
7. ARCHITECTURE §6-§8:
   - hydration: `models.EvidenceItem` has `url_or_citation` and `retrieved_at`, no title.
   - resume: `tools/gateway.py` `SelfReplayGateway` serves only entries with status ok and no `is_error`, before the checkpoint offset.
   - retry-after: the API backend reads `retry-after` (`llm/gateway.py` `_anthropic_retry_after`); the CLI `_classify` sets `retry_after_s=None` and `_backoff` is jittered exponential.
   - anchor window: `ingest/anchor.py` page +/- 1 intersected with section +/- 1 when the section resolves.
8. UI of 4 Oct (USER_DECISIONS #43 and #44): ARCHITECTURE §10 and DEMO_DAY_SCRIPT now name the head clock with limits, expandable stage rows, the Logs panel (`ui/server.py` `run_log`), the two-click Stop and its sentence (`ui/static/app.js` `stopSentence`), and the zip download (`ui/export.py` `GROUPS`, `export_zip`).
9. `docs/live_runs/sit_sample_ui_2/MEASUREMENT.md`: one `sed -i ''` on the single line matching "four single-pass shards", now "three single-pass shards (1, 2 and 5)"; the rest of that file was not read.

No em dash was added; every edited file had none before and has none after.

## Verifier fixes

1. Resume replay: `SelfReplayGateway` reads `tools.jsonl` up to `upto_offset`, which `orchestrator.py` sets to the log's size when the run is resumed (`tools_offset = rd.tools_log.stat().st_size`), not to the checkpoint offset; ARCHITECTURE §8 now says "when the run is resumed", each logged call served once.
2. Download: `ui/export.py` adds the reading-aid chat transcript, when `ui/chat.jsonl` exists, as its own section headed "not part of the review"; ARCHITECTURE §10 now says the review in the export says nothing the report does not, and names that section.
