# Worker note: the study sheet `docs/EXPLAIN_AS_IT_RUNS.md`, 4 Oct 2026

Malcolm's word for this task, 4 Oct 2026 15:30: "since it's an interview and they are testing me and I'm studying the architecture, I too, need to be able to explain it as to what is happening as it runs, so I need to create visibility".
Branch `s4/study-sheet` from `origin/claude/happy-darwin-d0bl94` at `8c3a291`; docs only, no code changed.

## Sources read

- `docs/HANDOVER_261004_PLANNER.md` (all sections; 1, 5, 6 and 7 used).
- `docs/ARCHITECTURE.md` sections 1 to 13.
- `docs/DEMO_DAY_SCRIPT.md`.
- `docs/USER_DECISIONS.md` rows 17 to 44.
- `docs/COMPARISON_LANGGRAPH.md`, `docs/LIMITATIONS.md`.
- `config/agent.yaml`, `config/profiles/demo.yaml`, `config/stop_rules.yaml`, `config/tools.yaml` (the enabled lines and two timeouts).
- `agent/sit_review_agent/orchestrator.py` (module docstring, `_cap`, `_skip_on_cap`, `_stage_1`, the function list), `states.py` `STAGE_ON_CAP`.
- Module docstrings of every file under `agent/sit_review_agent/phases/`, plus `verify.py` `REPAIR_MIN_SLACK_S` and `_model_calls.py` `REFINE_FALLBACK_IMPACT`.
- `agent/sit_review_agent/llm/claude_code.py` module docstring.
- `agent/sit_review_agent/ui/events.py` (docstring and `TYPES`), `ui/export.py` docstring, `ui/chat.py` caps, `ui/static/app.js` (grep for the clock, the limits and the Logs panel).
- `agent/sit_review_agent/delta.py` docstring, `stop_rules.py` registered rules, `cli.py` usage lines, `invariants.py` (INV-13 exists).
- `scripts/leakage_grep.py` docstring; `tests/robustness/results/robustness_summary.txt` (the totals line).
- `docs/live_runs/sit_sample_ui_2/MEASUREMENT.md` (the only file opened under `docs/live_runs/`).
- The "what changed" parts of `docs/transcripts/session6/shard-first-answer.md`, `repeat-off-with-tools.md`, `refine-keep-good.md`, `repair-fallback.md`.
- The lab brief `~/Downloads/AI Engineer Lab Exercise.pdf` pages 3, 5, 8 and 9 (extracted with `pdftotext`, lines that looked like keys filtered out).

## Where a document and the code disagree (the sheet follows the code)

1. `docs/ARCHITECTURE.md` sections 2 (text and diagram), 3, 12 (row 2) and 13 (points 3 and 4) say four assess shards; `config/agent.yaml` has six groups since decision #40.
2. `docs/DEMO_DAY_SCRIPT.md` says four shards in the walkthrough rows at 02:04 and 02:36 and in the S+09:30 line ("the four assessors").
3. `docs/DEMO_DAY_SCRIPT.md` row 07:56 says "87 scenarios, 55 passing offline"; `tests/robustness/results/robustness_summary.txt` and `docs/ARCHITECTURE.md` section 8 say 88 and 56.
4. `config/profiles/demo.yaml`: the comment on `stage_1_end` says "the four assess shards"; the header comment "MEASURED ONCE ... this profile does NOT fit 540 s" describes the sequential design before the redesign, not the current one (rehearsal 1 ended at 508.5 s).
5. `docs/LIMITATIONS.md`:
   - "The four assess shards start at about 2 s" (six since #40).
   - "The MCP session fix ... has not been run against the live servers": rehearsal 1 ran it live, 8 calls met a closed session and succeeded on the retry after 3 reopens (`sit_sample_ui_2/MEASUREMENT.md` "Tools").
   - "The cost with research on was measured once, on a run whose web searches all failed": rehearsal 1 measured a run whose searches all worked ($7.37 lower bound).
   - "Nothing requires every prior finding to be classified": `delta.py` now gives every prior finding one status, records a missing one as "not re-examined", and INV-13 checks it (`docs/ARCHITECTURE.md` section 11 agrees with the code).
6. `docs/ARCHITECTURE.md` section 4 says the gateway "keeps the finished items of a call that a limit cuts"; since `5b3908b` it keeps the last complete answer when there is one, and since `af12daf` a call without tools ends at its first accepted complete answer (`llm/partial.py`, `llm/claude_code.py` docstring).
7. `docs/ARCHITECTURE.md` section 2 calls refine "one model call"; the code makes one call plus at most one repair call that, since `df841bf`, asks only for the failing revisions.

## Not sourced, or not on the tip

- The "What is happening" panel named in the brief is not on the tip at `8c3a291` (no match for "happening" under `agent/`); the sheet says it is being built in parallel and to point at it only if it has landed.
- The expected numbers after the fixes wait for the second rehearsal: four marked placeholder lines in section 4 of the sheet (`[TO FILL FROM REHEARSAL 2: ...]`).
- Numbers of runs other than rehearsal 1 are cited through the documents that quote them (`docs/ARCHITECTURE.md`, `docs/COMPARISON_LANGGRAPH.md`, decisions #33 and #40), because no other file under `docs/live_runs/` was opened.

## Gates

- No em dash in `docs/EXPLAIN_AS_IT_RUNS.md` or this note (`grep -c` 0).
- `scripts/leakage_grep.py` (run with `/opt/homebrew/bin/python3.13`, no venv needed): `PASS: no unresolved hit in a gated area`.
- Every cited code symbol was found with `git grep` under `agent/`, every cited path with `git ls-files`, and the five cited commits exist.
