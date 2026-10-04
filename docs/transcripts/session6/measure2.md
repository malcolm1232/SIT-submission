# Measurement of the 4 Oct rehearsal run: worker note (4 Oct 2026)
## Task
Item 2 of `docs/HANDOVER_261004_PLANNER.md`: measure Malcolm's rehearsal run `ui-261004-034213-c5cb` (the SIT sample with tools from the review UI, six assess shards) against the six checks, and record it as `docs/live_runs/sit_sample_ui_2/`.
The run directory in `~/Desktop/SIT-wt/demo4` and the server on port 8791 were not touched; work was done in `~/Desktop/SIT-wt/measure2` on `s4/measure2` from `c136554`.

## Method
`manifest.json` and `report.json` were read by script for the named fields; `llm.jsonl`, `progress.jsonl` and `tools.jsonl` only by scripts that printed keys, ids, counts and durations (strings longer than an identifier were printed as their length).
The only text read was the header and evidence table of `report.md`, the limitation texts of `report.json` and the model note `docs/live_runs/sit_sample_ui_1/MEASUREMENT.md`.

## Checks
1. Stage 1 at or under 230 s with six shards: fails, 265.159 s with 6 shards.
2. Refine ended in full or its returned revisions applied: holds as worded (`llm-0012` ended in full; the repair `llm-0013` returned 4 revisions and 4 were applied), fails in effect (55 finished revisions set aside for 1 rule problem, 51 of 55 findings unrefined).
3. External evidence reaches the findings: fails, 0 of 41 external entries cited by the 52 findings.
4. `extra.tools.session_reopens` present: holds, 3.
5. "Tools used" names only servers with a call: holds, `mcp-internet-search` only (10 calls).
6. `output_basis` on calls that ended early: holds, `measured_rate` on both rows.

## Main finding
Three of six shards wrote their whole answer twice: the streamed item indices restart at 1, and shards 4 and 6 took 3 CLI turns instead of 2.
Their first complete answers were done by 151.0 s, 166.1 s and 217.2 s; keeping them would have ended stage 1 at about 217 s.
The shard that met the limit kept 5 findings from its second pass and lost its complete first answer of 13 findings.

## The record
The model record `sit_sample_ui_1` had been committed as a byte copy of its run directory, including the raw `llm.jsonl`; no script made it.
Per the brief (never a raw `llm.jsonl`), `sit_sample_ui_2` holds byte copies of every other file of the same list, plus `llm_calls.json`, a per-call summary made by script with no prompt, answer, argv or error text.
`report.md` keeps the document title's em dash because the copies are not edited.
`scripts/leakage_grep.py` printed `PASS: no unresolved hit in a gated area`.
