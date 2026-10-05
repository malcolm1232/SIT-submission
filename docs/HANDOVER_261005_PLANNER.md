# SIT planner - handover, written 05 Oct 2026 09:20 +08 by the "SIT planner, 4 Oct afternoon to 5 Oct morning" session

START HERE. This file is self-contained: a new session needs nothing else to continue.
To start the next session say: "Read ~/Desktop/SIT/docs/HANDOVER_261005_PLANNER.md on branch claude/happy-darwin-d0bl94 (git -C ~/Desktop/SIT show origin/claude/happy-darwin-d0bl94:docs/HANDOVER_261005_PLANNER.md) and continue as the SIT planner; you spawn Opus workers and make the calls; the answer-key signatures, the held-out items, the money above plan D and anything that needs the SIT MCP key stay Malcolm's."
Supersedes: `docs/HANDOVER_261004_PLANNER.md` (its sections 6 to 9 are carried forward here in shorter form; its items 1 and 2 are done).
This file is committed on the truth branch, so the `git show` form works; `~/Desktop/SIT` is checked out on an older branch and never holds it.
All times are Singapore time (+08).

## 1. Goal and where it stands

Malcolm's words, 3 Oct 2026 02:50: "you are fable now, u delegate tasks to opus agents to do? u can spawn them if youd like. and u make the shot calling, ok? u have explicit permission to shot call."
The product is a design-document review agent for the SIT AI Engineering Lab Exercise (brief `~/Downloads/AI Engineer Lab Exercise.pdf`: a live run on a document SIT hands over, a re-assessment of an updated artefact, an on-the-spot modification, submission through a private GitHub repository) plus a research-grade evaluation harness.
Everything built is pushed on `origin/claude/happy-darwin-d0bl94` at 880fac8 (2000 tests passing, every gate of section 7 green).
Done since the 4 Oct handover: his first rehearsal measured (three defects found and fixed), the review UI's live view, Logs panel, zip download and "What is happening" panel (decisions #43 to #45), the study sheet `docs/EXPLAIN_AS_IT_RUNS.md`, the docs refreshed to the code, five new synthetic evaluation items (ten keyed documents), the single-call baseline B0, plan D run and written up in `docs/COMPARISON_PLAN_D.md`, two report-stage crash classes fixed (INV-05 redaction, URL scheme case), the UI tests hardened against click races.
Plan D headline (exploratory, keys unsigned): agent 98 of 112 planted flaws against 88 of 112 for a single call, paired gain +0.089 (bootstrap +0.036 to +0.152, sign-flip p 0.0625), 0 hallucination flags on all v1 runs, grades all B PASS, mean 82.15; the v2 numbers are not yet meaningful (item 3).
In flight: nothing; no worker or run is active.
Next: his second rehearsal from `demo6` (item 1), its measurement (item 2), the refine fallback fix and the v2 reruns (items 3 and 4).

| Step | What | Tip | State |
|---|---|---|---|
| A | First rehearsal measured, record `docs/live_runs/sit_sample_ui_2` | fccf6d7 | done |
| B | UI: zip download, live view, labels, Logs panel, rail, panel | b2f1ac1 | done, decisions #43 to #45 |
| C | Agent fixes from the rehearsal: shard first answer, refine keeps good revisions, repair fallback | 8bcb7cf | done |
| D | Study sheet, docs refresh | 9cd3dce | done |
| E | Five new items, registration, access-log entry 3 | eba6974 | done |
| F | B0 baseline | 280c4b4 | done |
| G | INV-05 redaction fix, case rule, URL scheme | 6ca33e7 | done, not yet re-run live |
| H | Plan D runs, grades, write-up, deviation 14 | 880fac8 | done |
| I | Refine fallback on a missing prior status (card A1, A2) | WIP 1cc8d2b on `s4/refine-prior-status` | NOT for merge; item 3 |

## 2. Do this next

Mechanics first.
"Item" means this list; "step" means the table in section 1; "ADR-005", "Tier A", "INV-nn" and "#nn" are the repo's own names (an architecture decision record, see `docs/SUBMISSION_GAPS.md` row 2; the pre-registered study of `eval/EVAL_PLAN.md`, an invariant of `agent/sit_review_agent/invariants.py`, a row of `docs/USER_DECISIONS.md`).
Section 3 runs before item 1: its commands (`git fetch`, `rev-parse`, `log`, `show`, `ls-tree`, `status`, `ls`, `grep`, `wc`, `pgrep`, `lsof`, `uptime`, `memory_pressure`) are read-only and the planner runs them itself; editing, testing, running the agent and `kill` are workers' work, with one exception: the planner may `git add` and commit a stopped worker's uncommitted edits as a WIP checkpoint in that worker's worktree; never `checkout` or `pull` in `~/Desktop/SIT`.
Malcolm is reached with the PushNotification tool (one line, under 200 characters) whenever his word, his Terminal or his money is needed; if the tool is missing, the question goes in the chat and the planner works the items that need nothing from him; his answers are recorded by a worker as the next rows of `docs/USER_DECISIONS.md` (47 onward) with his words.
"Card" means an entry in the lists of this file (section 2 items 3 to 5) and in the two diagnosis notes (`docs/transcripts/session6/inv05-diagnosis.md`, `v2-diagnosis.md`); there is no board, so a card is spawned from this file and recorded by its worker note and commit.
Worker notes of this session go under `docs/transcripts/session7/` (branch names keep the `s4/` prefix, which is the repo's convention, not a session number); if session7 already has notes from another session, use session8.
A new piece of work starts with `git -C ~/Desktop/SIT fetch origin && git -C ~/Desktop/SIT worktree add -b s4/<name> ~/Desktop/SIT-wt/<name> origin/claude/happy-darwin-d0bl94` and the venv line of section 7, both done by the worker, never by the planner.
A verifier pushes with `git -C ~/Desktop/SIT-wt/<name> push origin HEAD:claude/happy-darwin-d0bl94`; if refused as non-fast-forward it merges `origin/claude/happy-darwin-d0bl94` into its branch (clean only; a conflict is reported to the planner, who rules and respawns), reruns ruff, the full suite and selftest, and pushes again; never `--force`.
Who pushes: code by a fresh-context verifier after the gates and the mutation; a docs record or write-up by its cold reader after recomputing every number; a tests-only change by its builder after the gates.
The planner (any model; this session ran on Fable) spawns one Opus worker per deliverable with the Agent tool (`model: "opus"`), a separate verifier per deliverable, and reads only their reports; a worker stopped by the safeguard is respawned ONCE (the retry may run on Fable) with its notes inlined after a planner checkpoint commit of its uncommitted edits, then the item stays in this file's list for a later, differently written brief (section 8 explains the stops).
Worker cap: three at once since 05 Oct 05:27 (the QM orchestrator's line "all the Mac's test slots are yours until he says otherwise"); two if a QM lane is running again (section 3 last row); every worker checks the load before a test run.
Commits carry `malcolm1232 <66200354+malcolm1232@users.noreply.github.com>` (`git -c user.name=malcolm1232 -c user.email=66200354+malcolm1232@users.noreply.github.com commit`) and never a co-author or agent line; scoped `git add` only; no em dash anywhere.
No board exists for SIT: the record is `docs/USER_DECISIONS.md` (last row 46), `eval/prereg_deviations.md` (last entry 14), one note per worker under `docs/transcripts/session6/` (session7 next), and this file.
The suite count grows with every change: a verifier expects "the tip's count plus the change's own tests", never a fixed number.
The submission deadline and the interview date are NOT known to this file or the repo; they are his (section 5 point 7) and set the priority of items 3 to 7; until he gives them, work the items in order.
Live model runs cost his Max subscription (CLI estimates: an agent run about $6 to $8, a B0 run about $0.80, a judges-off scoring $3 to $12, a grade about $5); plan D spent about $345 of the $350 to $400 he approved on 4 Oct 22:40; item 1 is his own run and item 2 costs nothing (no model call); every other live run (items 4 and 6, the LangGraph arm) needs his word first, and the worker that runs it keeps a running total in its table and stops at the figure he named.
A run-id is never reused: a rerun gets the next suffix (`_2`, `_3`), and a scoring that must be redone gets a new `--out` folder.
The subscription has a rolling session limit: on 5 Oct it refused every call from 06:05 to 07:10; a worker that sees "You've hit your session limit" stops, writes the reset time in its table, and reports; runs resume with `sit-review resume <run dir>`.

1. The second rehearsal, started by Malcolm (the live proof of step C and G).
   The worktree `~/Desktop/SIT-wt/demo6` is at 880fac8 (moved 05 Oct 09:10, selftest passed) and holds the venv, `runs/input/sit_sample_v1.pdf` and his first run `runs/ui-261004-034213-c5cb`; if a CODE push has moved the tip (a docs-only commit does not matter), a worker runs `git -C ~/Desktop/SIT-wt/demo6 merge --ff-only origin/claude/happy-darwin-d0bl94` after confirming no server runs from demo6.
   His old server (pid 5237, from `demo4`, port 8791) is still up and is HIS: no worker kills it; he stops it with Ctrl-C in its Terminal, then in the Terminal window where `SIT_MCP_API_KEY` is exported (a new window needs `read -rs SIT_MCP_API_KEY && export SIT_MCP_API_KEY` first) types: `cd ~/Desktop/SIT-wt/demo6 && env -u ANTHROPIC_API_KEY .venv/bin/sit-review preflight --warm --profile demo && env -u ANTHROPIC_API_KEY .venv/bin/dra ui --host 0.0.0.0 --allow-remote --port 8791 --runs-dir runs`, waits about 90 s for preflight, opens `http://127.0.0.1:8791/`, picks `runs/input/sit_sample_v1.pdf`, ticks every tool, starts.
   The three things he does, in his Terminal: Ctrl-C the old server; export the key if the window is new; the one long `cd ... && preflight ... && dra ui ...` line.
   The planner's part: give him those lines when he asks, wait for his word that the run ended, never kill a server on port 8791; "the key is rejected" means the SIT MCP key, which preflight reports.
   Done when he says it finished; the run folder is the newest under `~/Desktop/SIT-wt/demo6/runs/` other than `input` and the first run.
   If it crashes or the key is rejected: the page shows the error and `sit-review resume <run dir>` continues it from the last checkpoint; a worker diagnoses from the run's logs by script (counts and messages, never finding text); a second attempt is his, because the key is his; a `StageCrash` in report is a defect of step G and goes to a fix worker before any further live run.
2. Measure that run, one Opus worker after item 1, briefed with the facts inline (never pointing it at `docs/live_runs/`; the planner reads the record and inlines counts; see section 8): the six checks of the 4 Oct measurement (stage 1 at or under 230 s with six shards; refine applied in full or its returned revisions applied; external evidence cited by findings; `extra.tools.session_reopens` present; "Tools used" names only servers called; `output_basis` on calls that ended early) plus two new ones: `cli_answer_rejections` in `llm.jsonl` (counts and the rule names only) and no `StageCrash`.
   Expected against the first run: stage 1 at or under 230 s (was 265), every merged finding refined (the first run merged 55 findings and refined 4 of them), at least one external ledger entry cited by a finding (the first run had 41 external entries and 0 cited).
   A check that fails becomes a fix with its own worker, spawned without asking him (his word of 3 Oct 22:55): stage 1 over 230 s means the CLI schema rejection is still happening (read `cli_answer_rejections` rule names and fix the schema or the prompt); fewer refined than merged means the refine path again (compare with item 3); external cited still 0 means refine did not attach evidence (check the degradation entries first); a `StageCrash` means a new invariant class (diagnose read-only first, as `inv05-diagnosis.md` did).
   Reading the record safely: the worker inspects `llm.jsonl`, `progress.jsonl` and `tools.jsonl` only by a script it writes that prints call ids, phases, outcomes, durations, token counts and rule names (the 4 Oct worker's script is not in the repo); `llm_calls.json` is that script's summary, one row per call with keys such as call_id, phase, purpose, shard, attempt, outcome, stop_reason, elapsed_s, num_turns, usage and estimated usage counts, call_cost_usd, returned and kept item counts, and no text field; the planner reads only the worker's report and the committed `MEASUREMENT.md`, never a run folder or `llm_calls.json`.
   The record goes to `docs/live_runs/sit_sample_ui_3/`: the same file names as `git ls-files docs/live_runs/sit_sample_ui_2` lists (the planner runs that and inlines the list) minus any raw `llm.jsonl`, plus `llm_calls.json` and `MEASUREMENT.md`; `.venv/bin/python scripts/leakage_grep.py` must print PASS before the commit; a cold reader recomputes the numbers and pushes.
   The four `[TO FILL FROM REHEARSAL 2]` lines of `docs/EXPLAIN_AS_IT_RUNS.md` each say which number they want (stage 1 seconds, refined count, external cited, wall time and cost); the same cold reader fills them from `MEASUREMENT.md`.
3. The refine fallback on a missing prior status (cards A1 and A2 of `docs/transcripts/session6/v2-diagnosis.md`), the defect behind the v2 precision of 0.11 to 0.25 in plan D.
   Start from the WIP checkpoint 1cc8d2b in `~/Desktop/SIT-wt/refine-prior-status` (25 lines in `llm/outputs.py` and `phases/_model_calls.py`; read `git show 1cc8d2b` first; it is a start, not a design).
   Rule: when the only problems of a complete, rule-clean refine answer are missing prior-finding statuses, keep every revision and ask the repair only for those statuses (a `statuses` field on `KeptItems`, the ids in the instruction); a cut or failed repair applies the first answer and leaves the missing priors out of `state.prior_statuses` (delta.py then marks them not re-examined, INV-13 accepts it, report.py discloses it); in the fallback branch of `RefinePhase.run`, drafts carrying the same prior id are merged by code.
   Two Opus workers stopped on this brief (safeguard); the next attempt is a NEW brief with the facts above inlined and these two commits: commit 1 the `statuses` repair path (`llm/outputs.py` helper for the missing prior ids, `KeptItems.statuses`, `split_revisions` returning kept-all when only statuses are missing, the status-only `repair_impact` text, tests a to c), commit 2 the code merge of same-prior drafts in the fallback branch of `RefinePhase.run` with its test; if that attempt is stopped too, the item is Malcolm's to do in his own session.
   "Cut" in this file means a model call ended by a time limit (the stage limit or the deadline) with part of its output returned.
   Tests as in `tests/test_refine_keep_good.py` (fake gateway, 55 revisions; delta mode needs a small `previous_run_dir` with a report.json); mutation per section 7 item 9; verifier pushes.
4. Re-run on the fixed code, only after item 3 is on the tip AND his word on the money: about $92 in all (four v2 runs at about $7 each, their scorings at $5 to $12 each under the $24 cap, one hospital FULL run at about $7 plus its scoring), the worker stopping at $110; the hospital run repeats because `d_hospital_v1_1` crashed in report on the old code and the scored `d_hospital_v1_2` row is a rerun on that same old code, so no scored hospital run exists on the fixed code.
   If his money word arrives before item 3 is on the tip, the hospital run may go first (it does not depend on item 3); the v2 runs wait.
   Where: the worker fast-forwards `~/Desktop/SIT-wt/plan-d-runs` to the tip (`git -C ~/Desktop/SIT-wt/plan-d-runs merge --ff-only origin/claude/happy-darwin-d0bl94`; if `status -s` is not clean, it reports what is dirty and stops; the `runs/` folder is ignored and stays) and runs from that worktree, so the relative paths below hold and the new folders sit beside the old ones.
   Runs, one at a time: `env -u ANTHROPIC_API_KEY .venv/bin/dra review eval/synthetic/<folder>/design_v2.pdf --profile demo --no-tools --previous runs/d_<x>_v1_1 --run-id d_<x>_v2_2` where (folder, x) is (payments_orchestration, payments), (clinical_rpm, clinical), (research_lakehouse, lakehouse), (iot_fleet, iot); and `env -u ANTHROPIC_API_KEY .venv/bin/dra review eval/synthetic/hospital_scheduling/design_v1.pdf --profile demo --no-tools --run-id d_hospital_v1_3`.
   Scoring, after each run: `.venv/bin/sit-eval score runs/<run-id> --key eval/synthetic/<folder>/answer_key.canonical.json --out runs/<run-id>/eval_d --judge claude_code --model claude-opus-5-5 --effort high --samples 3 --seed 20261002 --concurrency 4 --max-cost-usd 24 --candidate-rule shortlist_bounded --no-grounding-judges --exploratory` (about $5 to $12 each; the cap counts committed spend plus $1 per call in flight).
   Rows go to `docs/live_runs/plan_d/RUNS.md` in its existing columns (the worker owns that file alone); then a worker updates `docs/COMPARISON_PLAN_D.md` sections 6 and 7 and a cold reader recomputes the numbers and pushes.
   The brief inlines these commands; it never points the worker at `docs/live_runs/` or `docs/transcripts/session4/`.
5. Small cards, one worker each, in any order: `sit-eval score --condition` must match the manifest's `condition` or refuse (`harness/sit_eval/scoring.py` about line 325); the B0 rationale's "See the limitations" wording (`phases/report.py`); harness v2 metrics `resolved_acknowledgement` and `stale_finding_rate` read 0.0 regardless of the prior table (card A4, `metrics.py::_v2_metrics`); `scoring.py::score_review` warns on a recorded refine fallback (A5); a resolved carry-over becomes a prior-table status, not a finding (A3, `delta.py` via `report.py::_delta_table`); the three edges of section 9.
6. Freeze and re-record before submission (unchanged from 4 Oct item 4): an annotated tag `demo-freeze` on the tip of that moment, pushed with `git push origin demo-freeze` by its verifier, the demo-day runs re-run at that commit (the SIT sample with tools from his Terminal; `eval/synthetic/payments_orchestration/design_v1.pdf` and then `design_v2.pdf` with `--previous`; about $25, his word needed), `docs/REPRODUCIBILITY.md` and the README replay recipe updated; after items 1 to 4 and after his answers to section 5 points 3 (keys) and 5 (plan letter), which decide whether the evaluation freeze shares the commit.
7. Submission: `docs/SUBMISSION_GAPS.md` rows 1 (collaborator invites), 2 (ADR-005), 24 (demo-day prerequisites) are his; a read-only worker reads the three rows and reports one line each.

## 3. Check these facts first

| Command | Expected on 05 Oct 2026 09:20 | If different |
|---|---|---|
| `git -C ~/Desktop/SIT fetch origin; git -C ~/Desktop/SIT log --oneline -1 origin/claude/happy-darwin-d0bl94` | the commit "Handover of 5 Oct 2026 ..." (this file; the code below it is 880fac8) | anything above it: `git -C ~/Desktop/SIT log --oneline 880fac8..origin/claude/happy-darwin-d0bl94` shows what landed; read the notes under `docs/transcripts/session7/` |
| `git -C ~/Desktop/SIT-wt/demo6 rev-parse --short HEAD; git -C ~/Desktop/SIT-wt/demo6 status -s` | `880fac8`, empty status (a docs-only handover commit above it does not matter for a run) | behind a CODE push: item 1's `merge --ff-only` by a worker, only while no server runs from demo6 and no rehearsal is in progress |
| `ls ~/Desktop/SIT-wt/demo6/runs/` | `input` and `ui-261004-034213-c5cb` | a third folder is his second rehearsal: item 2 can start |
| `pgrep -fl 'dra ui' \| cut -c1-60` | pid 5237 (his demo4 server on 8791) or none, or his new demo6 server on 8791 | any server on port 8791 is his, never killed; a server on another port whose cwd (`lsof -p <pid> \| grep cwd`) is a worker worktree was a worker's and is killed by pid only after that worker has reported or is known to be gone |
| `git -C ~/Desktop/SIT show origin/claude/happy-darwin-d0bl94:docs/USER_DECISIONS.md \| grep -c '^| [0-9]* |'` | 46 numbered rows (last row 46) | more: a later session recorded a decision; read the new rows |
| `git -C ~/Desktop/SIT show origin/claude/happy-darwin-d0bl94:eval/prereg_deviations.md \| grep -c '^## [0-9]*\.'` | 14 (last entry 14) | more: read the new entry |
| `git -C ~/Desktop/SIT ls-tree -r --name-only origin/claude/happy-darwin-d0bl94 docs/transcripts/session6/ \| grep -c '\.md$'` | 24 notes | more: a later worker's note in session6 (session7 is the new folder) |
| `git -C ~/Desktop/SIT-wt/refine-prior-status log --oneline -1` | `1cc8d2b WIP, planner checkpoint, NOT for merge ...` | gone or merged: item 3 moved; read its note |
| `git -C ~/Desktop/SIT show origin/claude/happy-darwin-d0bl94:eval/blind/ACCESS_LOG.md \| grep -c '^## Entry'` | 3 | 4 or more: someone touched the held-out items; read the entry |
| `uptime; memory_pressure \| tail -1` | 5-minute load under 10 and free memory over 35 percent before any test run | higher: QM lanes are running again; wait, and drop the worker cap to two |

## 4. His decisions (do not re-ask)

All in `docs/USER_DECISIONS.md` rows #17 to #46 (his own, and the planner's rulings under his delegation, each row saying which).
03 Oct 02:50: the planner makes the calls; 02:55 "u can do whatever while im gone, if need my permision, build the rest first and when im back, u can ask me"; 22:55 "fix what u need to fix".
03 Oct 03:05: judge stays Anthropic-only (#23); 10:30: effort medium default, high the ablation arm (#33), the 540 s deadline a configurable assumption (#34); 10:50: no answer key for the SIT sample (#35); 11:40: review outputs Download, Email, wifi share link, no hosted link (#36); 15:50: UI shape, the DBSearch idiom with the rail (#41).
04 Oct 11:55: "What happens if stop run? Timing isn't like PER SECOND ... more visibility on each of the stages": the live view (#44).
04 Oct 12:10: "break into different documents or different sidebar or both": the zip of eight parts plus the sidebar page (#43).
04 Oct 15:30: "I too, need to be able to explain it as to what is happening as it runs": the "What is happening" panel (#45) and `docs/EXPLAIN_AS_IT_RUNS.md`.
04 Oct 22:40: plan D, his words "just 10 documents is enough", "less runs, but more variants document wise", "all using medium", "yes" (#46, deviation 13); "no langchain, right?" "Right": the LangGraph arm is separate and unfunded.
04 Oct: a hosted public URL "like Orbitmesh" was asked about and answered (decision #36 stands; a hosted copy would move billing to an API key and need a login); not decided.
04 Oct: on resuming after a shutdown: "it can be done right?" and told yes (checkpoints, `sit-review resume`); no decision needed.
Rulings the planner made under his delegation and standing unless he reverses them: the early-end rule is off for calls with tools (research); B0 attempt counts are disclosed, not hidden; the two held-out items were not run in plan D (deviation 14); a URL counts as ledger-backed only when it is in the document text, a tool result or a ledger `url_or_citation`, never a doc excerpt; the demo start line with `--host 0.0.0.0 --allow-remote` was NOT written into the runbook (refused to a worker as exposing a local service; his to type or edit).

## 5. Open with him

1. The second rehearsal (item 1): three Terminal lines above; it proves steps C and G live and fills the study sheet.
2. Money: about $80 to re-run the four v2 documents and $12 for hospital on the fixed code (item 4), above the $350 to $400 he approved; recommendation: yes, after item 3, because SIT's day includes a live re-assessment and the current v2 numbers describe a fallback, not the agent.
3. Sign the answer keys: ten keys now (`eval/synthetic/*/answer_key.json`, `scored_run_ready: false` on all); the one-liner is in `eval/KEY_SIGNOFF.md` section 10; until then every score is exploratory.
   Recommendation: sign the eight synthetic ones; the two held-out ones are his to decide (point 4).
4. The held-out items: whether the converter's unintended programmatic read of 5 Oct (`eval/blind/ACCESS_LOG.md` entry 3, no exposure) counts against the three-evaluation budget (recommendation: no), and whether to spend one evaluation on them now or keep them for the frozen stage (recommendation: keep).
5. The plan letter A ($3,282), B ($1,506) or C ($801) for Tier A: plan D ($345 spent) gives the primary comparison on eight documents; recommendation: C only if he wants the pre-registered power analysis; otherwise plan D plus item 4 is the submission's evidence.
6. The LangGraph arm on the same eight documents, about $120: his "if I have time" of 4 Oct; recommendation: yes before the interview, in a quiet window, because "why not a framework" is a near-certain question and one pair is thin.
7. The SIT email and the two GitHub invitations (`SIT-calebying`, `Makienhui-sit`), the submission deadline and the interview date (nothing in the repo holds them); the email text is in the 4 Oct handover section 5 and still applies.
8. Review email on or off: `config/ui.yaml` host, username and from, password in `SIT_UI_SMTP_PASSWORD` in the shell that starts `dra ui`; off as shipped.
9. The demo start line with the share flags in `docs/DEMO_DAY_RUNBOOK.md` (his edit or his typing on the day).
10. A ledger field marking a doc excerpt that came from a model anchor (spec change: `spec/*.schema.json` has `additionalProperties: false`); traceability only, not needed for correctness.
11. Opus fast mode for the demo: unchanged recommendation, not before a timing problem shows.

## 6. Rules of this work

The planner never reads source, edits, tests, runs the agent or scores; one Opus worker per deliverable, a fresh-context verifier per deliverable, briefs with the facts inline; at most two SIT workers while QM lanes share the Mac (the QM orchestrator handed all three slots to SIT at 05:27 on 5 Oct "until he says otherwise"; keep the load courtesy: a worker reads `uptime` and `memory_pressure` before every test run and tests only under a 5-minute load of 10 with free memory over 35 percent).
Workers keep every recorded model transcript (`llm.jsonl`, `progress.jsonl` records, judge logs, stream fixtures, `ui/chat.jsonl`, `report.json` finding text) out of their context and inspect them by script that prints ids, counts, durations and metric values.
A brief never points a worker at `docs/live_runs/` or at `llm_calls.json` (reasoning-token fields trip the safeguard); the planner reads the record and inlines the counts.
Security flaws in synthetic items and in any brief are written as missing or broken controls, never as a procedure; the LLM-support-bot domain was dropped for this reason.
The SIT MCP key is only ever in Malcolm's Terminal; every with-tools run is started by him; evaluation runs use `--no-tools`.
No agent run touches `eval/blind/` (three-evaluation budget, `eval/blind/ACCESS_LOG.md` append-only); `spec/convert_answer_keys.py` is run with `--tier synthetic` (without a tier it reads the held-out keys and that must be logged).
The synthetic answer keys are unsigned; the harness refuses a scored run without `--exploratory` (#26); only Malcolm signs.
The public snapshot never carries `eval/blind/`, answer keys, transcripts, raw model logs, the lab's documents, the probe results or the plan D tables; refresh it only with `scripts/export_public_snapshot.py` (output filtered to rule names and counts); a refresh on 05 Oct 2026 fails its scan on 12 older findings (emails in the two planner handovers, a home path, oauth words in four synthetic designs, token64 in tests) that must be resolved first.
Billing: every model call goes through `claude -p` on his Max subscription; dollar figures are CLI estimates; no Anthropic API key is set; `env -u ANTHROPIC_API_KEY` on every run.
Every Bash call of a worker is one purpose; pytest with `--tb=line -p no:warnings 2>&1 | tail -N`; absolute paths; no `cd` in a compound command except a whole-call subshell; a refused call is never resent; a bare `sleep` is refused, wait with an `until` loop on the load.
Other sessions: QM planner sessions message this one through Claude Code's cross-session messages (`ListAgents`, `SendMessage`); their all-clear on load is a condition, never a permission.
At the close the planner updates `~/.claude/projects/-Users-malco/memory/project_sit_design_review_agent_261003.md` and its `MEMORY.md` line, writes the next handover, then runs `/saveconvo SIT --agents` last (`--agents` renders every worker transcript too; the day file is named by the session's START day).

## 7. How to verify a change

From a worktree with its venv (`/opt/homebrew/bin/python3.13 -m venv .venv && .venv/bin/pip install -e '.[dev,langgraph]' && .venv/bin/playwright install chromium`; `pip install markdown` for `eval/build_pdfs.py`), one command per call, exit codes read:
1. `.venv/bin/ruff check agent harness tests` prints `All checks passed!` (never `ruff check .`: it reaches files no gate covers).
2. `( cd <worktree> && .venv/bin/pytest -q --tb=line -p no:warnings 2>&1 | tail -2 )` prints `2000 passed, 1 skipped, 2 xfailed` at 880fac8 (plus the change's own tests) with no `failed` or `error` word.
3. The same from `~` (`( cd ~ && <worktree>/.venv/bin/pytest -q --tb=line -p no:warnings <worktree> 2>&1 | tail -2 )`).
4. `env -u ANTHROPIC_API_KEY .venv/bin/sit-review selftest` prints `selftest passed`.
5. `( cd <worktree> && make smoke )` exits 0 (256 passed, 1 skipped); `make test` is ruff plus pytest.
6. `( cd <worktree> && .venv/bin/pytest -q --tb=line -p no:warnings tests/robustness 2>&1 | tail -2 )` prints `161 passed`.
7. `.venv/bin/python spec/convert_answer_keys.py --tier synthetic --check --verify-anchors` prints `120 flaws converted across 8 keys; 0 key(s) failed validation`; `.venv/bin/python eval/build_pdfs.py --check` prints `ALL CHECKS PASSED`.
8. `.venv/bin/python scripts/leakage_grep.py` prints `PASS`; `.venv/bin/python -m sit_review_agent.prompts --check` prints the lock is up to date (bundle 2569a967015b); `tests/test_export_public_snapshot.py` passes (65).
9. For a guard: `cp` a backup, remove the claim, see its test fail, restore, `cmp` the file.
10. Push only as a fast-forward after all of the above; `git ls-remote origin claude/happy-darwin-d0bl94` equals the local HEAD.
11. Rollback: the truth branch is never force-pushed; a bad push is undone by a new commit that restores the affected files from the last good sha (`git checkout <good sha> -- <paths>`, commit, push), never by reverting a merge commit.
12. A UI change is verified in a browser: the worker starts its own `dra ui` on a port other than 8791 with `--runs-dir` at a `cp -R` copy of `~/Desktop/SIT-wt/demo6/runs/ui-261004-034213-c5cb`, replays `progress.jsonl` line by line for a live view, screenshots viewports (not full page: sticky elements paint at the scroll position), kills its server by pid.

## 8. Traps already paid for

The model-side safeguard (`reasoning_extraction`) stopped eleven workers on 4 and 5 Oct 2026: every one while reading or writing prose about the model's own steps (a UI test file about the clock, `llm_calls.json`, the key converter's source, a planning turn about injection flaws, the refine code twice); never during git, pytest or push.
What worked: facts inline, "do not open" lists, the content pass split from a mechanical pass (gates, merge, push), a planner checkpoint commit of a stopped worker's edits, one Fable retry; what did not: a third attempt of the same brief.
A permission classifier (not the safeguard) refused: a runbook start line binding the server to `0.0.0.0` ("Expose Local Services"; his to type), a wait loop on another process's pid ("Interfere With Workloads"), and on 3 Oct five live runs to a worker (on 5 Oct the live runs were NOT refused).
The subscription session limit (06:05 to 07:10 on 5 Oct) aborts runs with exit 3 and judge calls with `LLMUnavailableError`; a shell left waiting by a stopped worker resumed by itself at the reset and nearly duplicated the queue; always `pgrep` for a previous worker's scripts before starting the same work.
Two workers on one results folder corrupt the tables: one worker owns each `RUNS*.md`.
The key converter without `--tier` reads the held-out keys (entry 3 of the access log).
A fifth synthetic item shifted the leakage grep's TF-IDF ranking so a common English phrase was flagged against an unrelated file; with eight items it passes again; renaming invented ids and product names clears item-specific hits.
Cold reads of synthetic items found 4 to 6 real defects in every item's "sound" sections, real-world company and person names (FleetSense, Merbau, Kempen, Temujanji, Lumbung, Seroja and two real people), and changelog bullets that pointed at the regression: never register an item without a cold read, and read the design before the README (the README names the external fact).
INV-05 crashed a run because the report's URL redaction rewrote a quote that verify had copied from the excerpt (fixed); the first fix trusted doc excerpts and let a made-up URL through (caught by the verifier's probe, fixed); verifiers with probes are not optional on honesty code.
`sit-eval aggregate` pairs runs by manifest `condition`; FULL runs made before 280c4b4 carry null and appear as "unlabelled"; compare `unlabelled` with `B0` for those, and say so.
The scorer's `--max-cost-usd` fires at committed spend plus $1 per in-flight call, so an $18 cap stops near $15 at concurrency 4; the judge cache makes a rescore cheap.
Full-page screenshots of a scrolled page paint sticky elements mid-page; shoot viewports.
A line pasted into this chat never runs; Terminal only; a new window has no exported key; Esc while the Claude window is focused stops every worker.
`gh` and `git fetch` print `credential-manager is not a git command`; harmless.

## 9. Not done, on purpose

The two held-out items were not run (deviation 14); the LangGraph arm was not run (unfunded); the four v2 runs were not re-run (item 4 waits on item 3 and his word).
The fixed report code (step G) has not been re-run live; the scored hospital row is a rerun on the old code that happened not to hit the crash; his second rehearsal is the first live run on it.
The ledger marker for model-anchor excerpts (spec change, section 5 point 10).
Three INV-05 edges, none seen in a run: an anchor quote ending inside a document URL fails closed; a URL broken across lines in the document text does not count as backed; `_redact` keeps a quote INV-05 does not exempt, so such a run fails closed rather than redacting.
No multi-provider dropdown, no persistent memory beyond re-assessment, no hosted share link, no dark theme, no prompt or prereg freeze (item 6).
The shards do not see external evidence (#37); a second assess pass after research is a future variant.
The 80 worktrees under `~/Desktop/SIT-wt/` are all merged into the tip except `refine-prior-status` (WIP 1cc8d2b, not for merge) and `item-support-bot` (empty, dropped domain); `score` and `score2` hold uncommitted grader inputs on purpose; removing the rest is housekeeping for a quiet moment and NOT planned; if done, keep `demo6`, `demo4` (his old server's cwd until he stops it), `refine-prior-status`, `plan-d-runs`, `plan-d-b0`, `plan-d-grade` (their ignored `runs/` hold the plan D run folders item 4 needs and nothing else does), `plan-d-writeup` (this file was written there; merged by its push), `score`, `score2`.
`.venv` folders exist in most worktrees (about 1 GB each).

## 10. Where everything is

Runtime: `/opt/homebrew/bin/python3.13`, venv per worktree, Playwright Chromium for the UI tests, `claude -p` on his subscription for every model call, the SIT MCP servers only through his key.
End-of-session routine: update the memory file and its `MEMORY.md` line, write the next handover from `~/.claude/skills/handover/template.md`, then `/saveconvo SIT --agents`.

| Thing | Path |
|---|---|
| Truth branch | `origin/claude/happy-darwin-d0bl94` of `malcolm1232/SIT` (private), tip 880fac8 |
| Public snapshot | `malcolm1232/SIT-public` (older than the tip; refresh blocked by 12 scan findings, section 6) |
| His rehearsal worktree | `~/Desktop/SIT-wt/demo6` (s4/demo6), PDF `runs/input/sit_sample_v1.pdf`, first run `runs/ui-261004-034213-c5cb` |
| Plan D run folders (uncommitted) | `~/Desktop/SIT-wt/plan-d-runs/runs/` (FULL, v2, variance, ablation), `~/Desktop/SIT-wt/plan-d-b0/runs/` (B0), `~/Desktop/SIT-wt/plan-d-grade/runs/grades/` |
| Plan D tables and write-up | `docs/live_runs/plan_d/RUNS.md`, `RUNS_B0.md`, `GRADES.md`; `docs/COMPARISON_PLAN_D.md`; earlier `docs/live_runs/QUALITY_COMPARISON.md`, `docs/COMPARISON_LANGGRAPH.md` |
| First rehearsal record | `docs/live_runs/sit_sample_ui_2/MEASUREMENT.md` (counts only; a brief never points at it) |
| Evaluation items | `eval/synthetic/{payments_orchestration,clinical_rpm,research_lakehouse,iot_fleet,consent_service,hospital_scheduling,ledger_migration,exam_platform}/`; held-out `eval/blind/` (sealed) |
| Registration points | `spec/convert_answer_keys.py` ITEMS and NEEDS_EXTERNAL, `eval/build_pdfs.py` ITEMS, `eval/prereg.yaml` items |
| Decisions, deviations, sealing | `docs/USER_DECISIONS.md` (to row 46), `eval/prereg_deviations.md` (to entry 14), `docs/SEALING.md`, `eval/KEY_SIGNOFF.md`, `eval/blind/ACCESS_LOG.md` (3 entries) |
| Study sheet and architecture | `docs/EXPLAIN_AS_IT_RUNS.md`, `docs/ARCHITECTURE.md`, `docs/DEMO_DAY_SCRIPT.md`, `docs/DEMO_DAY_RUNBOOK.md`, `docs/LIMITATIONS.md` |
| UI code | `agent/sit_review_agent/ui/` (server.py, rundata.py, events.py, export.py, static/app.js, index.html, app.css, export.css) |
| Honesty code | `agent/sit_review_agent/invariants.py` (INV-04, INV-05, `allowed_urls`, `quote_backed_by_excerpt`), `phases/report.py` (`_redact`), `phases/verify.py` |
| Refine and model calls | `phases/refine.py`, `phases/_model_calls.py` (`call_model`, `KeptItems`, `split`), `llm/claude_code.py` (first-answer rule), `llm/partial.py` |
| B0 | `--condition B0` in `cli.py`, `Orchestrator._b0_stage`, `prompts/assess_single.md`, `tests/test_b0_condition.py` |
| Diagnoses | `docs/transcripts/session6/inv05-diagnosis.md`, `v2-diagnosis.md` (cards A1 to A6, B1) |
| Worker notes of 4 and 5 Oct | `docs/transcripts/session6/*.md` (24 notes, screenshots under `ui-live/`, `explain-panel/`, `export-bundle/`) |
| WIP not for merge | `~/Desktop/SIT-wt/refine-prior-status` at 1cc8d2b |
| Memory | `~/.claude/projects/-Users-malco/memory/project_sit_design_review_agent_261003.md`, `feedback_a_brief_that_reads_a_note_about_thinking_tokens_trips_the_safeguard.md` |
| Transcripts | folder `~/Desktop/conversation_history/SIT/`: this session (started 4 Oct) is saved last into the day file conversation_verbatim_261004.md with its agents folder; a session started on 5 Oct writes conversation_verbatim_261005.md |
| Older handovers | `docs/HANDOVER_261004_PLANNER.md` (superseded), `docs/HANDOVER_261003_PLANNER.md` |
