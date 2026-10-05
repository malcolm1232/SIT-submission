SUPERSEDED by docs/HANDOVER_261005_PLANNER.md on 05 Oct 2026.
# SIT planner - handover, written 04 Oct 2026 10:45 +08 by the "SIT FABLE on the Mac, evening of 3 Oct" session

START HERE. This file is self-contained: a new session needs nothing else to continue.
To start the next session say: "Read ~/Desktop/SIT/docs/HANDOVER_261004_PLANNER.md on branch claude/happy-darwin-d0bl94 (git -C ~/Desktop/SIT show origin/claude/happy-darwin-d0bl94:docs/HANDOVER_261004_PLANNER.md) and continue as the SIT planner; you spawn Opus workers and make the calls; the answer-key signature, the evaluation plan letter and anything that needs the SIT MCP key stay Malcolm's."
Supersedes: `docs/HANDOVER_261003_PLANNER.md` (also on the truth branch; its sections 4 to 10 are carried forward here in shorter form).
This file is committed on the truth branch (the commit "Handover of 4 Oct 2026" is the tip at writing), so the `git show` form in the start line works; `~/Desktop/SIT/docs/` may not hold it because that checkout is on an older branch.
All times are Singapore time (+08).

## 1. Goal and where it stands

Malcolm's words, 3 Oct 2026 02:50: "you are fable now, u delegate tasks to opus agents to do? u can spawn them if youd like. and u make the shot calling, ok? u have explicit permission to shot call."
The product is a design-document review agent for the SIT AI Engineering Lab Exercise (brief `~/Downloads/AI Engineer Lab Exercise.pdf`: a walkthrough of the design, a live run on an artefact SIT hands over on the day, a re-assessment of an updated artefact, an on-the-spot modification, submission through a private GitHub repository; no time limit is stated) plus a research-grade evaluation harness.
Everything built is pushed and verified on `origin/claude/happy-darwin-d0bl94` at a7fbffb (code at fe50a34, 1925 tests passing, every gate of section 7 green): the concurrent redesign, the review UI in the DBSearch idiom, the MCP probe and session fix, two with-tools runs on the lab document, the re-assessment, the demo script and runbook, the submission documents, the budget options, the LangGraph comparison variant, the refine fallback, the five run fixes, the usage estimate of a call that ended early, and the six-shard test fakes.
Nothing is in flight: no worker, no server, no run.
Next is the rehearsal (item 1), which only Malcolm can start because the SIT MCP key lives in his Terminal.

| Step | What | Where | State |
|---|---|---|---|
| A | Rehearsal with the UI and the tools on the lab document, six shard groups | `~/Desktop/SIT-wt/demo4` at fe50a34, prepared | waits for his Terminal; item 1 |
| B | Measurement note of that run | item 2 | after A |
| C | Paired LangGraph runs, five more | item 3 | waits for his "go" (cost) |
| D | Freeze tag, re-record the demo runs, reproducibility | item 4 | after his plan letter and A |
| E | Submission rows that are his | item 5 | his |
| F | Evaluation plan A, B or C | section 5 | waits for his letter |

## 2. Do this next

Mechanics first.
"Item" means this list; "step" means the table in section 1.
Section 3 runs before item 1: its commands are `fetch`, `rev-parse`, `log`, `status`, `ls` and `pgrep`, which the planner may run itself (reading reports, logs and refs is planning; editing, testing and running the agent is not); never `checkout` or `pull` in `~/Desktop/SIT`.
Worker notes of this session go under `docs/transcripts/session6/`.
A new piece of work starts with `git -C ~/Desktop/SIT worktree add -b s4/<name> ~/Desktop/SIT-wt/<name> origin/claude/happy-darwin-d0bl94` and the venv line of section 7, both done by the worker, never by the planner.
A verifier pushes with `git -C ~/Desktop/SIT-wt/<name> push origin HEAD:claude/happy-darwin-d0bl94`; if the tip moved and the push is refused as non-fast-forward, it merges `origin/claude/happy-darwin-d0bl94` into its branch (clean only; a conflict is reported to the planner, who rules how to resolve it and respawns), reruns ruff, the full suite and selftest, and pushes again; never `--force`.
The truth is `origin/claude/happy-darwin-d0bl94` of the private repo `malcolm1232/SIT`; every piece of work is a branch `s4/<name>` in its own worktree under `~/Desktop/SIT-wt/` (`git -C ~/Desktop/SIT worktree list` prints them; `~/Desktop/SIT` itself is checked out on an older branch and is never worked in), merged and pushed only by a fresh-context verifier that ran every gate of section 7, as a fast-forward, never a force.
The planner spawns one Opus worker per deliverable with the Agent tool (`model: "opus"`), a separate verifier per deliverable, and reads only their reports; a worker stopped by the safeguard is respawned once with its notes after a planner checkpoint commit of its uncommitted edits, then the task is handed over rather than retried again (section 8).
Commits carry `malcolm1232 <66200354+malcolm1232@users.noreply.github.com>` (`git -c user.name=malcolm1232 -c user.email=66200354+malcolm1232@users.noreply.github.com commit`) and never a co-author or agent line; scoped `git add` only; no em dash anywhere.
No board exists for SIT: the record is `docs/USER_DECISIONS.md`, one note per worker under `docs/transcripts/session5/` (session6 for the next session), and this file.

1. The rehearsal, started by Malcolm.
   The worktree is ready: `~/Desktop/SIT-wt/demo4` at fe50a34, venv with `[dev,langgraph]`, Chromium installed, `selftest passed`, the lab document at `~/Desktop/SIT-wt/demo4/runs/input/sit_sample_v1.pdf` (1,632,705 bytes, untracked and ignored).
   He types three lines in ONE Terminal window (not in this chat; a line pasted into the chat never runs): `read -rs SIT_MCP_API_KEY && export SIT_MCP_API_KEY` (he pastes the "Shared API key (all 4)" value from the lab brief; nothing echoes, which is correct), then `cd ~/Desktop/SIT-wt/demo4 && env -u ANTHROPIC_API_KEY .venv/bin/sit-review preflight --warm --profile demo && env -u ANTHROPIC_API_KEY .venv/bin/dra ui --port 8791 --runs-dir runs`, then on `http://127.0.0.1:8791/` he picks `runs/input/sit_sample_v1.pdf`, ticks the tools, and starts.
   He ticks every tool the page offers (the lab's four servers share the one key); the six shard groups come from `config/agent.yaml` and need no setting.
   The planner's part is to give him those lines when he asks, wait for his word that the run ended, and never kill the server on port 8791 (it is his; section 3's "none" holds only while no rehearsal is running).
   If the run crashes or the key is rejected, a worker diagnoses it from the run's logs by script (counts and messages, never transcript content) and the second attempt is his, because the key is his.
   Done when he says the run finished; the run folder is the newest folder under `~/Desktop/SIT-wt/demo4/runs/` other than `input` (`ls -t ~/Desktop/SIT-wt/demo4/runs/ | head -2`); it stays there, ignored by git, until item 4 is done.
2. The measurement of that run, by one Opus worker after item 1.
   Brief it with the facts inline and in plain words (the words "ended early", "revisions already returned" and the field names are fine; never the words salvage, partial, cut, stream, truncation): the run folder path, the six checks below, and the shape of `docs/live_runs/sit_sample_ui_1/MEASUREMENT.md` as the model (the worker may Read that one file; it must inspect `llm.jsonl`, `progress.jsonl` and `tools.jsonl` only by script that prints counts, keys and durations, never content).
   The six checks: stage 1 ends at or under 230 s with six shards (`extra.timing.stages` in the manifest; 230 s is the tuning threshold of decision #31, and a near miss is reported as a number, not rounded); the refine call ended in full or its returned revisions were applied (`extra.model.salvaged_calls` in the manifest, the degradations in `report.json`); external evidence reaches the findings (ledger entries of kind external cited by findings); `extra.tools.session_reopens` is present in the manifest; the report's "Tools used" line names only servers that received a call; `output_basis` is present on any call that ended early.
   The worker lists what the model record holds with `git -C <worktree> ls-files docs/live_runs/sit_sample_ui_1` and copies the run's files under the same names into `docs/live_runs/sit_sample_ui_2/`, never `runs/input/` or the PDF, never a raw `llm.jsonl` (the record holds redacted and summarised files only; `scripts/leakage_grep.py` must print `PASS` before the commit), writes `MEASUREMENT.md` there, commits on a branch `s4/measure2` (its own worktree and venv per the mechanics above), and a verifier pushes.
   Done when that note is on the tip and says which of the six checks hold; a check that fails becomes a card-sized fix with its own worker, spawned without asking him (his word of 3 Oct 22:55, "fix what u need to fix").
3. The paired LangGraph runs, only after Malcolm says "go" (he asked on 3 Oct 23:00 "can we compare evaluation between langchain and current orchestration?" and was told the cost; he has not said go).
   Facts: the comparison so far is one paired run on the payments design (custom loop 382 s and 13 of 14 planted flaws exactly; LangGraph 425 s and 12 of 14; `docs/COMPARISON_LANGGRAPH.md`); five more are planned: the custom loop on payments again under equal load, and both arms on `eval/synthetic/clinical_rpm` and `eval/synthetic/research_lakehouse`, each scored with `--exploratory`; no MCP key is needed (`--no-tools`); about $5 of CLI estimate per run plus $10 of scoring, so about $35; the commands are in `docs/transcripts/session4/langgraph_verifier.md` under the heading "For the next session" (line 35; a worker may Read that section only).
   Conditions: a quiet machine (5-minute load under 3 on `uptime`; `pgrep -fl claude | wc -l` is informative only, it always counts this session and his other planner sessions), because the wall-time comparison is only fair under equal load; and his go.
   Run order: payments custom first (the one that gives equal load against the recorded LangGraph run), then clinical custom, clinical LangGraph, lakehouse custom, lakehouse LangGraph, one at a time, each scored right after it.
   A fresh worker tries the runs once; on 3 Oct the permission classifier refused five live runs to a worker as real-world transactions, so if it refuses again the commands go to Malcolm's Terminal, never to another worker.
   Then a worker extends `docs/COMPARISON_LANGGRAPH.md` with the new rows and a verifier pushes.
   Done when the comparison holds six paired runs and the tip has them.
4. Freeze and re-record before submission, after his plan letter (because the letter decides whether the evaluation's `prereg` freeze shares the same commit) and after items 1 and 2: an annotated tag `demo-freeze` on the tip of that moment (the name `docs/SUBMISSION_GAPS.md` row 24 expects), pushed with `git push origin demo-freeze` by the verifier of that item, re-run the demo-day runs at that commit (the SIT sample with tools from his Terminal; `eval/synthetic/payments_orchestration/design_v1.pdf` and then `design_v2.pdf` with `--previous`) so the committed records replay byte for byte there (none replays at the tip, because the renderer and the ID rewrite moved after they were recorded), and update `docs/REPRODUCIBILITY.md` and the README's replay recipe.
5. Submission: `docs/SUBMISSION_GAPS.md` rows 1 (collaborator invites), 2 (ADR-005), 24 (demo-day prerequisites) are Malcolm's; everything else is closed or prepared.
   The planner does not hold the text of those rows: a read-only worker reads the three rows and reports in one line each what he must do, and the planner puts that in front of him with section 5.

## 3. Check these facts first

| Command | Expected on 04 Oct 2026 10:45 | If different |
|---|---|---|
| `git -C ~/Desktop/SIT fetch origin; git -C ~/Desktop/SIT log --oneline -1 origin/claude/happy-darwin-d0bl94` | the commit "Handover of 4 Oct 2026 ..." (the one that added this file; code below it at fe50a34) | newer: `git -C ~/Desktop/SIT log --oneline fe50a34..origin/claude/happy-darwin-d0bl94` shows what landed; read its notes under `docs/transcripts/` |
| `git -C ~/Desktop/SIT-wt/demo4 log --oneline -1` and `git -C ~/Desktop/SIT-wt/demo4 status -s` | `fe50a34`, empty status | a run folder under `runs/` is ignored and does not show; commits there mean a worker used it, read them |
| `ls ~/Desktop/SIT-wt/demo4/runs/` | only `input` | a second folder is his rehearsal run: item 2 can start |
| `git -C ~/Desktop/SIT show origin/claude/happy-darwin-d0bl94:docs/USER_DECISIONS.md \| grep -c '^| 4[0-9] |'` | 3 (rows are written `\| 40 \|` in the file, "#40" only in prose) | 4 or more: a later session recorded a decision; read it |
| `git -C ~/Desktop/SIT ls-tree -r --name-only origin/claude/happy-darwin-d0bl94 docs/transcripts/session5/ \| wc -l` | 6 | more: a later worker's note; read it |
| `pgrep -fl 'dra ui'` | none (or his, on port 8791, while a rehearsal runs) | a server on port 8791 is Malcolm's own: never kill it; one on any other port was a worker's, kill by pid after checking its cwd |
| `gh repo view malcolm1232/SIT-public --json visibility` | `PUBLIC` (one commit from 9b5dd53, older than the tip; no refresh is planned before item 4) | PRIVATE: he flipped it back, leave it; a refresh uses only the exporter per `scripts/README.md`, output filtered to counts, and pushes to the remote URL `https://github.com/malcolm1232/SIT-public.git` spelled out in the push command, never to `origin` |
| `uptime; memory_pressure \| tail -1` | load under 10 and free memory over 35 percent before any test run; load under 3 before item 3 | higher: QM lanes are running; wait, and keep SIT to two workers |

## 4. His decisions (do not re-ask)

All in `docs/USER_DECISIONS.md` rows #17 to #42 (his own, and the planner's rulings under his delegation, each row saying which).
03 Oct 02:55: "u can do whatever while im gone, if need my permision, build the rest first and when im back, u can ask me."
03 Oct 03:05: judge stays Anthropic-only, "judge: no" and "btw, NO FOR NOW, later i might change my mind." (#23).
03 Oct 10:30: effort `medium` is the default on measured ground, `high` stays the A4b arm (#33); the lab brief sets no time limit, the 540 s deadline is a configurable assumption (#34).
03 Oct 10:50: "lets assume there is not answer key" for the SIT Memory Platform PDF (#35): a demo document, the agent may run on it.
03 Oct 10:35 and 15:50: UI shape A, then on the v2 mockup "ok it looks good" (#41): the DBSearch idiom with the rail is the review UI.
03 Oct 11:40: "yes" to the three review outputs: Download, Email, a session-only wifi link, no hosted link (#36); the pasted https link is the artefact hand-over path (#39).
03 Oct 11:30: "make the public snapshot" and "(ill change to public)": done, `malcolm1232/SIT-public` is public.
03 Oct 11:00: slot "about 10 mins" stays the working assumption; venue is normal wifi.
03 Oct 16:45: "no need usage ss. cos other runs for QM are still running." (the usage calibration waits for a quiet machine).
03 Oct 17:05 and 17:12: the LangGraph variant: "let it run and compare it", "no need to budget . and just work normally, no rush to complete, just make sure its a job well done. then we can effectively compare both custom and langraph" (#42).
03 Oct 22:55: "fix what u need to fix": the run fixes were built and pushed that night.
Rulings the planner made under his delegation, recorded "SIT FABLE for the owner" and standing unless he reverses them: #31 the latency design, #37 shards do not see external evidence (refine applies it), #38 the MCP session rule, #40 six shard groups; and, not in the decisions file, the rule of the research stop reason (`sufficient_evidence` only with half the questions answered or two cited external entries; a skipped research keeps `sufficient_evidence` with detail `no_external_questions`) and the output estimate of a call that ended early (the run's measured median rate).

## 5. Open with him

1. Which evaluation plan: A ($3,282, the full pre-registered study), B ($1,506, every test at full power, judges off, grading on 33 reviews), or C ($801, full agent versus single-call baseline on five documents, three runs each); figures are CLI estimates on his Max subscription's weekly limit. Recommendation: C in chunks over weeks; B if he wants the research claims. Nothing runs until he says a letter.
2. Sign the answer keys: the one-liner in `eval/KEY_SIGNOFF.md` section 10; until then every score is exploratory.
3. The email to SIT and the GitHub invitations for `SIT-calebying` and `Makienhui-sit` (brief p.8 section 5.2, before the submission deadline, which he has not told us; ask him for the submission deadline and the interview date, nothing in the repo holds them; the recipient address is in the lab brief, not in the repo, and he sends the email himself).
   The email, ready to paste: "Subject: AI Engineering Lab Exercise, two practical questions for the review session. Hello, two quick questions so I can prepare the live execution: 1. Roughly how long may the live agent run take during the session (a few minutes, or ten or more)? 2. How will the new design artefact be handed over on the day (USB, email, or a download link)? Thank you, Malcolm".
4. Item 1 needs his Terminal (the three lines are in item 1); item 3 needs his "go" (about $35) and a quiet Mac.
5. Opus fast mode for the demo (double price, up to 2.5 times the output speed): measure once or not; the design does not depend on it. Recommendation: not before the rehearsal shows a timing problem.
6. The usage calibration: his usage percentage before and after one quiet $6 run, to restate the three plans as weeks of allowance. Recommendation: fold it into item 3's first run.

## 6. Rules of this work

The planner never reads source, edits, tests, runs the agent or scores; one Opus worker per deliverable, a fresh-context verifier per deliverable, briefs with the facts inline, at most two SIT workers at once while QM lanes share the Mac (a worker reads `uptime` and `memory_pressure` before every test run and tests only under a 5-minute load of 10 with free memory over 35 percent).
Workers keep every recorded model transcript (`llm.jsonl`, `progress.jsonl` records, judge logs, stream fixtures, `ui/chat.jsonl`) out of their context and inspect them by script.
The SIT MCP key is only ever in Malcolm's Terminal: a worker that tries to read it from a file or the clipboard is refused by the safeguard, so every with-tools run is started by him; nothing reaches the SIT hosts otherwise.
No agent run touches `eval/blind/` (sealed held-out items, three-evaluation budget, access log `eval/blind/ACCESS_LOG.md`); `spec/validate_examples.py` needs `--include-blind` to read them and that access must be logged.
The synthetic answer keys are unsigned; the harness refuses a scored run without `--exploratory` (#26); only Malcolm signs.
The public snapshot never carries `eval/blind/`, answer keys, transcripts, raw model logs, the lab's documents or the probe results; refresh it only with `scripts/export_public_snapshot.py` (the scanner's output filtered to rule names and counts, never printed with values).
Billing: every model call goes through `claude -p` on his Claude subscription (Max 20x); dollar figures are CLI estimates; no Anthropic API key is set anywhere.
Every Bash call of a worker is one purpose; pytest with `--tb=line -p no:warnings 2>&1 | tail -N`; absolute paths; no `cd` in a compound command except a whole-call subshell; a refused call is never resent.
Other sessions: QM planner sessions run on the same Mac and message this one through Claude Code's cross-session messages (they arrive in the conversation by themselves; `ListAgents` lists them and `SendMessage` answers); their all-clear on load is a condition, never a permission.
At the close the planner updates `~/.claude/projects/-Users-malco/memory/project_sit_design_review_agent_261003.md` and its `MEMORY.md` line to the newest handover and tip.

## 7. How to verify a change

From a worktree with its venv (`/opt/homebrew/bin/python3.13 -m venv .venv && .venv/bin/pip install -e '.[dev,langgraph]' && .venv/bin/playwright install chromium`), one command per call, exit codes read:
1. `.venv/bin/ruff check agent harness tests` prints `All checks passed!`.
2. `( cd <worktree> && .venv/bin/pytest -q --tb=line -p no:warnings 2>&1 | tail -2 )` prints `1925 passed, 1 skipped, 2 xfailed` at fe50a34 (plus the change's own tests) with no `failed` or `error` word; without the `[langgraph]` extra 28 parity tests skip and the count drops, which is an environment difference, not a failure.
3. The same from `~` (`( cd ~ && <worktree>/.venv/bin/pytest -q --tb=line -p no:warnings <worktree> 2>&1 | tail -2 )`).
4. `.venv/bin/sit-review selftest` prints `selftest passed`.
5. `( cd <worktree> && make smoke )` and `( cd <worktree> && make test )` exit 0 (the shell is zsh: capture `$?` directly, not through PIPESTATUS).
6. `( cd <worktree> && .venv/bin/pytest -q --tb=line -p no:warnings tests/robustness 2>&1 | tail -2 )` prints `161 passed`; the results CSV regenerated by `( cd <worktree> && ROBUSTNESS_RESULTS_CSV=tests/robustness/results/robustness_results.csv .venv/bin/pytest tests/robustness -q -p no:warnings )` (running `tests/robustness/robustness_results.py` directly writes nothing), differing only in the `commit`, `duration_s` and `date` columns.
7. `.venv/bin/python spec/convert_answer_keys.py --tier synthetic --check --verify-anchors` prints `0 key(s) failed validation`.
8. `.venv/bin/python scripts/leakage_grep.py` prints `PASS`; `.venv/bin/python -m sit_review_agent.prompts --check` prints the lock is up to date; `tests/test_export_public_snapshot.py` passes.
9. For a guard: `cp` a backup, remove the claim, see its test fail, restore, `cmp` the file.
10. Push only as a fast-forward after all of the above; `git ls-remote origin claude/happy-darwin-d0bl94` equals the local HEAD.
11. Rollback: the truth branch is never force-pushed; a bad push is undone by a new commit that restores the affected files from the last good sha (`git checkout <good sha> -- <paths>`, commit, push), never by reverting a merge commit; a run that must be reproduced is made in a worktree at the good sha.

## 8. Traps already paid for

The model-side safeguard (tag `reasoning_extraction`) stopped about thirty workers on 3 Oct 2026, Opus and Fable alike, four of them in the evening on harmless calls (a grep of two docs files, an `uptime` check, a line count of worker notes, a response right after writing code).
Triggers seen: reading or printing material about streamed model output, thinking-token counts, recorded transcripts or secret-shaped strings; the brief's own vocabulary (salvage, partial, cut, stream, truncation) even before any file is read; and, less predictably, any long turn.
What worked: facts inline in plain words, a short allow-list of files, transcripts and fixtures inspected by script, the task split into parts with a commit after each, a planner checkpoint commit of a stopped worker's uncommitted edits (`git add <paths>; git commit -m "WIP: ... (planner checkpoint before a retry)"`), then ONE respawn with the previous worker's notes.
What did not: a third retry of the same brief.
A permission classifier (different from the safeguard) refused a worker's `cat` of config files bundled with a test log, a worker's read of the credentials file, a bare `sleep 120` call (workers wait with an `until` loop on the load instead), and five live agent runs after the budget was lifted: those go to Malcolm, never to another worker.
"Config tests green" is not "the suite is green": the six-group change of 3 Oct broke 62 tests unseen for nine hours because only `tests/test_config.py` was run; every branch runs the full suite before its verifier.
A merge of the tip into a branch that touches `phases/refine.py` can conflict (the re-assessment fix of 1905eed moved the same lines); a worker told to abort on conflict will, and the planner then rules how to resolve (keep both sides) and respawns.
A line pasted into this chat never runs; Terminal only; a new Terminal window has no exported key; `read -rs` shows nothing when the key is pasted, which is correct.
Esc pressed while the Claude window is focused stops the running turn and every background worker.
`claude -p` reports a cap hit as an error: handled (typed as a truncation, retried once, disclosed).
A call cut by a limit logs unknown usage: handled; every cost total says "lower bound"; the output estimate now uses the run's measured rate.
The MCP server closes an idle session within about two minutes: handled (reopen and retry; the count is now in the manifest).
`dra replay` reproduces a record only at its recorded commit (item 4).
Pytest from `~` once failed on a repo-relative path; run it both ways.
`gh` and `git fetch` print `credential-manager is not a git command` on every network call; harmless.
The verifier of the run fixes had to fetch the tracking ref explicitly before `origin/claude/happy-darwin-d0bl94` updated in its worktree; a plain `git fetch origin` is usually enough, check the sha after it.

## 9. Not done, on purpose

No multi-provider model dropdown before the interview (the gateway seam exists; the LangGraph variant shows the orchestrator seam).
No persistent memory beyond re-assessing an updated artefact (the Delta tab).
No hosted public share link; no in-run second-model verifier; dark theme of the UI deferred.
No Tier A runs, no prompt freeze, no `prereg` freeze (waits for his letter and item 4).
The refine and verdict prompts still see the shards' own finding numbers inside finding text (a prompt change with the replay consequence; after the demo).
The shards do not see external evidence (#37); a second assess pass after research is a future variant.
The session reopen count covers the current process only; reopens before a resume are not added.
The concurrent fault schedules of the robustness suite run on fixtures only; their `shard_of` targeting is proven by loader tests.
`MERGED_ID` in `tests/test_e2e_synthetic.py` is a constant that follows the configured group order; a regrouping that changes the order fails `test_merged_ids_follow_the_configured_shard_order` first, which prints the new order to write in.
The grader's `inputs/` folders in the `score` and `score2` worktrees stay uncommitted (prompt copies, 1 MB).
The 44 worktrees under `~/Desktop/SIT-wt/` are all merged into the tip (`s4/demo4` is at fe50a34, an ancestor; `s4/handover` is merged by the push of this file) and clean; removing them is housekeeping for a quiet moment and not planned, and if done it keeps `demo4`, `hand`, `score` and `score2` (the last two hold the uncommitted grader inputs).

## 10. Where everything is

Runtime: `/opt/homebrew/bin/python3.13` venvs per worktree; `claude` at `~/.local/bin/claude` logged in; Chromium via Playwright in `demo4` and the UI worktrees; `gh` logged in as malcolm1232.
Board: none for SIT; the record is `docs/USER_DECISIONS.md`, `docs/transcripts/session4/*.md` and `session5/*.md` (one file per worker), and the edit logs under `research/audit/`.
End of session: `/handover planner SIT` then `/saveconvo SIT --agents` (the folder `~/Desktop/conversation_history/SIT/` exists and the script accepts an existing folder name as well as an alias, proven on 3 Oct; `--agents` renders every worker's transcript beside the day-file; the day-file is named by the session's start day).

| Thing | Path |
|---|---|
| Private repo, truth branch | `~/Desktop/SIT` (checked out on another branch; do not work there), `origin/claude/happy-darwin-d0bl94` at a7fbffb |
| Rehearsal worktree | `~/Desktop/SIT-wt/demo4` (branch `s4/demo4` at fe50a34), the lab document in `runs/input/sit_sample_v1.pdf` |
| Handover worktree | `~/Desktop/SIT-wt/hand` (branch `s4/handover`, this file) |
| Public snapshot | `https://github.com/malcolm1232/SIT-public`; exporter `scripts/export_public_snapshot.py`, allow-list `.public-allow` |
| Architecture and walkthrough | `docs/ARCHITECTURE.md` (sections 12 and 13), `docs/DEMO_DAY_SCRIPT.md`, `docs/DEMO_DAY_RUNBOOK.md` |
| Decisions | `docs/DECISIONS.md` (ADR-001 to ADR-012), `docs/USER_DECISIONS.md` (#17 to #42) |
| Designs | `docs/design/latency_and_demo_design.md`, `docs/design/ui_design.md`, `docs/design/ui_restyle.md`, mockups under `docs/design/ui_mockup/` and `ui_mockup_v2/` |
| Measured runs | `docs/live_runs/`: `rehearsal_concurrent_1`, `rehearsal_concurrent_high_1`, `sit_sample_tools_1`, `sit_sample_ui_1` (the lab document with tools, the model for item 2), `reassess_payments_v2_1`, `ui_flow_1`, `langgraph_payments_v1_1`; `QUALITY_COMPARISON.md`; `COMPARISON_LANGGRAPH.md` |
| Worker notes of the night | `docs/transcripts/session5/`: `refine_fallback_worker.md`, `refine_fallback_verifier.md`, `run_fixes_worker.md`, `usage_estimate_worker.md`, `shards6_worker.md`, `run_fixes_verifier.md` |
| LangGraph run commands | `docs/transcripts/session4/langgraph_verifier.md`, heading "For the next session" |
| Budget | `docs/BUDGET.md` (section 6 awaits his approval), `docs/BUDGET_OPTIONS.md` |
| Submission | `README.md`, `docs/LIMITATIONS.md`, `docs/SUBMISSION_GAPS.md`, `docs/DOCUMENTATION_MAP.md`, `outputs/lab_session/README.md` |
| Probe | `research/robustness/mcp_probe_findings.md`, `mcp_probe_results.redacted.json` |
| Evaluation | `harness/README.md`, `eval/EVAL_PLAN.md`, `eval/prereg.yaml`, `eval/prereg_deviations.md`, `eval/KEY_SIGNOFF.md` |
| Lab brief | `~/Downloads/AI Engineer Lab Exercise.pdf` |
| Memory | `~/.claude/projects/-Users-malco/memory/project_sit_design_review_agent_261003.md`, `feedback_a_brief_that_reads_a_note_about_thinking_tokens_trips_the_safeguard.md` |
| Transcripts | `~/Desktop/conversation_history/SIT/conversation_verbatim_261002.md` (the day session), `conversation_verbatim_261003.md` (the evening session), `agents_verbatim_261002/` and `agents_verbatim_261003/` |
| Older handovers | `docs/HANDOVER_261003_PLANNER.md` (superseded; its sections 0 and 0a hold the night's detail), `docs/HANDOVER_FULL.md`, `docs/HANDOVER_FABLE.md`, `docs/HANDOFF.md` |
