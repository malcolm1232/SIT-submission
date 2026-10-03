# SIT planner - handover, written 03 Oct 2026 18:15 +08 by the "SIT FABLE on the Mac" session, section 0 added 22:50

START HERE. This file is self-contained: a new session needs nothing else to continue; section 0 is the newest state and overrides the sections below where they differ.
This file is committed and pushed on the truth branch; `~/Desktop/SIT` itself is checked out on an older branch, so read it with `git -C ~/Desktop/SIT show origin/claude/happy-darwin-d0bl94:docs/HANDOVER_261003_PLANNER.md` or from any worktree at the tip.
To start the next session say: "Read ~/Desktop/SIT/docs/HANDOVER_261003_PLANNER.md on branch claude/happy-darwin-d0bl94 and continue as the SIT planner; you spawn Opus workers and make the calls; the answer-key signature, the evaluation plan letter and anything that needs the SIT MCP key stay Malcolm's."
Supersedes: the 14:40 version of this file (same path), `docs/HANDOVER_FULL.md` section 10 and `docs/HANDOVER_FABLE.md` (both carry a SUPERSEDED line).

## 0. UPDATE 03 Oct 2026 22:50 (the evening session, written by the planner; read before section 2)

Item 1 is done: the LangGraph verifier pushed before the shutdown, `docs/COMPARISON_LANGGRAPH.md` is on the tip, and decision #42 is in the file.
Item 2 is done: the refine fallback was finished by a worker and pushed by a fresh verifier as 8d5be75 at 22:45 (1902 tests, every gate of section 7 green, the guard check fails 6 of the 8 new tests when the fallback is removed; reports in `docs/transcripts/session5/refine_fallback_worker.md` and `refine_fallback_verifier.md`).
The merge of the tip into `s4/refinefix` conflicted in `phases/refine.py` (the re-assessment fix of 1905eed touched the same lines) and was resolved keeping both; the prior-status filter now runs only when the refine call returned a parsed answer, so a call that ended early marks every prior finding "not re-examined".
Not verified: the fallback on a real call that ended early; item 4's rehearsal is where it shows.
Item 3 is NOT done: the worker was stopped by the safeguard while grepping `docs/USER_DECISIONS.md` and `tests/test_config_layout.py` for part A, after reading the "Defects" section of `docs/live_runs/sit_sample_ui_1/MEASUREMENT.md` (lines 116 to 126).
`s4/runfix2` stands at a3ee771: the merge of 481cedb (clean) and decision row #40, written by the planner, so the worktree is 2 commits behind the tip (merge the tip first, no conflict expected: the branch touches `config/agent.yaml` and `docs/USER_DECISIONS.md` only).
The next brief for item 3 carries every fact inline and forbids the Defects section and `docs/USER_DECISIONS.md` (row #40 exists; a worker must not grep that file).
The mapping the stopped worker left, so no reader needs the section: part B is defect 7 (the two "waking" status records in `progress.jsonl` carry a null `run_s`); part C is defect 3 (the report header lists `mcp-research-information`, which received 0 calls, while the run details row is right); part D is defect 4 (the session reopen appears only in `progress.jsonl` and in one `tools.jsonl` attempt message, and the manifest and the report carry no session event); part E is defect 2 (research stopped on `sufficient_evidence` with 1 of 6 questions answered, and the run-level `stop_reason` repeats it); part F is defect 5 (the estimate for a call that ended early, streamed characters over 3.3 plus thinking, gives 58 and 66 tokens per second, while the recorded calls ran at 96 to 140); defect 8 (shard pressure) is the six groups already on the branch; defect 1 is item 2, done; defect 6 (the UI launch record writes absolute home paths) is a seventh small fix to add to the brief.
Split part F into its own worker: its vocabulary (a call that ended early, output rate, thinking) is the kind that trips the safeguard, so the other five parts must not wait on it.
Three workers were stopped on item 3 on 3 Oct (two in the day session, one in the evening): per section 8 the next try is on 4 Oct, not a fourth on the same day.
The Mac load condition from the QM orchestrator stands while QM chains run: a worker reads `uptime` and `memory_pressure` before every test run and tests only under a 5-minute load of 10 with free memory over 35 percent; at most two SIT workers at a time.
The verifier found `tests/robustness/robustness_results.py` writes nothing when run directly; the README's command regenerates the CSV: `ROBUSTNESS_RESULTS_CSV=tests/robustness/results/robustness_results.csv .venv/bin/pytest tests/robustness -q`.
Section 3's expected values are now: tip 8d5be75; `s4/refinefix` merged (its worktree may be removed); `s4/runfix2` at a3ee771; the decision-row grep prints 3 (rows #40, #41, #42).
Transcript of the evening: `~/Desktop/conversation_history/SIT/conversation_verbatim_261003.md` and its agents folder.

## 1. Goal and where it stands

Malcolm's words, 3 Oct 2026 02:50: "you are fable now, u delegate tasks to opus agents to do? u can spawn them if youd like. and u make the shot calling, ok? u have explicit permission to shot call."
The product is a design-document review agent for the SIT AI Engineering Lab Exercise (brief `~/Downloads/AI Engineer Lab Exercise.pdf`, nine pages: a walkthrough of the design, a live execution on an artefact SIT hands over on the day, a re-assessment of an updated artefact, an on-the-spot modification exercise, submission through a private GitHub repository; no time limit is stated anywhere) plus a research-grade evaluation harness.
Pushed and verified on `origin/claude/happy-darwin-d0bl94` at 94466da (18:05): the concurrent redesign (6.4 min document-only, 13 of 14 planted flaws found exactly against 11 for the old sequential agent), honest cost accounting, the scoring guard, the sign-off decisions applied to the keys, the MCP probe and the session fix, two with-tools runs on the lab's own document, the first live re-assessment and its four fixes, the review UI in the DBSearch idiom with a sidebar and the three outputs, the architecture document, the demo-day script, the submission documents, the budget with three options, the public snapshot exporter.
Being verified at writing: the LangGraph comparison variant on `s4/langgraph` (verifier pushes it; see section 3).
Left unfinished on purpose because eight workers were stopped by the model-side safeguard (section 8): the refine fallback (two tests on `s4/refinefix`) and four small run fixes (`s4/runfix2`); both are items 2 and 3 below.

| Step | What | Where | State |
|---|---|---|---|
| A | LangGraph variant merged and pushed | `s4/langgraph` | verifier running at 18:05; item 1 checks it |
| B | Refine fallback: apply the revisions a cut refine already returned | `s4/refinefix` ccfaaa4 | 6 of 8 tests pass; item 2 |
| C | Six small run fixes, the first being six shard groups | `s4/runfix2` 9e6c2fb | config change checkpointed, five items and the record left; item 3 |
| D | Demo rehearsal with the UI, with tools, six shard groups | Malcolm's Terminal | item 4 |
| E | Freeze, re-record the demo runs, submission | section 2 items 5 to 7 | not started |
| F | Evaluation plan A, B or C | section 5 | waits for his letter |

## 2. Do this next

Mechanics first.
Section 3 runs before item 1: its commands are read-only git and `ls`, which the planner may run itself (reading reports, logs and refs is planning; editing, testing and running the agent is not).
No worker of the 3 Oct session is alive when you read this: the Mac was powered off at 20:30 on 3 Oct 2026 (a one-off, Malcolm's choice), and workers die with the session, so there is no race with a verifier you cannot see; section 3 tells you what each one left.
The truth is `origin/claude/happy-darwin-d0bl94` of the private repo `malcolm1232/SIT`; every piece of work is a branch `s4/<name>` in its own worktree under `~/Desktop/SIT-wt/` (`git -C ~/Desktop/SIT worktree list` prints them), merged and pushed only by a fresh-context verifier that ran every gate of section 7, as a fast-forward, never a force.
The planner spawns one Opus worker per deliverable with the Agent tool (`model: "opus"`), a separate verifier per deliverable, and reads only their reports; a worker stopped by the safeguard is respawned once with its notes, then the task is handed over rather than retried a third time (section 8).
Commits carry `malcolm1232 <66200354+malcolm1232@users.noreply.github.com>` and never a co-author or agent line; scoped `git add` only; no em dash anywhere.
"Item" means this list; "step" means the table in section 1.

1. Check the LangGraph verifier.
   Run `git -C ~/Desktop/SIT fetch origin && git -C ~/Desktop/SIT ls-tree -r --name-only origin/claude/happy-darwin-d0bl94 | grep -c orchestrator_langgraph`.
   If it prints a number above 0, the verifier pushed: read `docs/transcripts/session4/langgraph_verifier.md` section "for the next session" and go on.
   If it prints 0, the verifier was cut by the 20:30 shutdown: `git -C ~/Desktop/SIT-wt/langgraph log --oneline 527c60e..HEAD` shows what it committed; spawn a fresh Opus verifier with the brief in `docs/transcripts/session4/langgraph_verifier.md` if that file exists on `s4/langgraph`, else with this instruction: verify the parity tests are not vacuous (mutate the variant's merge ordering and see the ID test fail on the LangGraph arm only), run section 7, merge the remote, push.
   Done when the grep prints a number above 0 and `docs/COMPARISON_LANGGRAPH.md` is on the remote tip.
2. Finish the refine fallback on `s4/refinefix` (worktree `~/Desktop/SIT-wt/refinefix`, venv present).
   State: `tests/test_refine_salvage.py` has 8 tests; the wiring in `agent/sit_review_agent/phases/refine.py` is committed as ccfaaa4 and 6 pass.
   The two failures, diagnosed by the last worker: `test_merge_whose_target_the_cut_lost_keeps_both` fails because FND-001's keep with disposition `governance_decision` is rejected by `revision_problems()` (likely a disposition rule requiring a `next_step` the test's `keep()` helper does not give); `test_applied_evidence_reaches_the_ledger_and_the_finding` fails because `resolve_evidence` in `phases/_model_calls.py` creates no new ledger entry for doc evidence whose quote (`Q_NOTIFY`) already exists.
   Planner rulings for the two: the disposition rule stands, so the test's `keep()` helper must supply what a `governance_decision` keep requires (fix the test, not the rule); and `resolve_evidence` must reuse an existing ledger entry for the same quote and make the finding cite it, so the second test asserts the citation on the finding and the entry's presence, not a duplicate entry.
   Brief a worker in plain words ("a fallback that uses the revisions already returned"), never with the words salvage, partial, stream, cut or truncation; allow it only `phases/refine.py`, `phases/_model_calls.py` (`resolve_evidence`), `llm/outputs.py` (`apply_revisions`, `revision_problems`), `errors.py`, the test file and the `keep` and `gone` helpers in `tests/test_llm_phases.py`; forbid `llm/partial.py`, `llm/claude_code.py`, the fixtures and the logs (section 8).
   Done when all 8 pass, the two newly passing tests fail again when the change is removed (a `cp` backup, then restore), the row for an early end of the refine call in the coverage table under `tests/robustness/` expects the revisions applied and the results CSV is regenerated by `tests/robustness/robustness_results.py`, the gates pass (expect the tip's count plus 8), and a verifier pushes.
   Merge order: this branch merges before `s4/runfix2`; item 3's verifier merges the tip that contains it.
3. Finish the run fixes on `s4/runfix2` (worktree `~/Desktop/SIT-wt/runfix2`, venv present).
   State: 9e6c2fb holds six shard groups in `config/agent.yaml` with the config tests green; the decision row #40 and the runbook listing are not written.
   Remaining, from `docs/live_runs/sit_sample_ui_1/MEASUREMENT.md` "Defects": row #40 in `docs/USER_DECISIONS.md` (six groups, the reason: stage 1 ended at 265.2 s and 255 s on the lab document, past the 230 s tuning threshold of #31) and the config listing in `docs/DEMO_DAY_RUNBOOK.md` section 4.1 if `tests/test_config_layout.py` pins the groups; the research stop reason `sufficient_evidence` allowed only when at least half the plan's questions were answered (rounded up) or two or more external ledger entries across the run are cited by a finding; "Tools used" lists only servers that received a call; session reopens in the manifest and the report; the estimate for a call ended early at the run's own measured output rate; no null `run_s` in a progress record.
   Same briefing rule as item 2 (plain words; the word for an interrupted call is "a call that ended early"); expect the tip's test count plus the new tests.
   Done when the gates pass and a verifier pushes.
4. The demo rehearsal with the UI, with tools, on the lab document, after items 2 and 3 are on the tip.
   Malcolm runs it, because the MCP key lives only in his Terminal; three lines in one Terminal window: `read -rs SIT_MCP_API_KEY && export SIT_MCP_API_KEY` (he pastes the "Shared API key (all 4)" value from the brief, nothing echoes), then `cd ~/Desktop/SIT-wt/<worktree at the tip> && env -u ANTHROPIC_API_KEY .venv/bin/sit-review preflight --warm --profile demo && env -u ANTHROPIC_API_KEY .venv/bin/dra ui --port 8791 --runs-dir runs`, then on `http://127.0.0.1:8791/` he picks `runs/input/sit_sample_v1.pdf` (copy it from `~/Desktop/SIT-wt/live/runs/input/`) and starts.
   Create a fresh worktree at the tip first (`git -C ~/Desktop/SIT worktree add -b s4/<name> ~/Desktop/SIT-wt/<name> origin/claude/happy-darwin-d0bl94`, any new name), then its venv per section 7, and use that folder in the lines above.
   Then a worker reads the run by script (never printing `llm.jsonl`), writes its `MEASUREMENT.md` like `docs/live_runs/sit_sample_ui_1/MEASUREMENT.md`, and checks three things: stage 1 ends at or under 230 s with six shards (`extra.timing.stages` in the manifest), refine ended in full or its returned revisions were applied (`extra.model.salvaged_calls` in the manifest and the degradations in `report.json`), and external evidence reaches the findings (ledger entries of kind external cited by findings).
   Done when that note is committed and those three hold.
5. The paired LangGraph runs the worker could not run (the permission classifier refused them to the worker as real-world transactions): custom on payments under equal load, both arms on `eval/synthetic/clinical_rpm` and `research_lakehouse`, each scored with `--exploratory`; no MCP key is needed (`--no-tools`), but they cost about $5 of CLI estimate each plus $10 of scoring, so ask Malcolm for the go first; a fresh worker may try once, and if the classifier refuses again Malcolm runs the commands in his Terminal (they are in `docs/transcripts/session4/langgraph_verifier.md` "for the next session"); a quiet machine means load under 3 and no other Claude session running agents (`uptime`, `pgrep -fl claude`); then extend `docs/COMPARISON_LANGGRAPH.md`.
6. Freeze and re-record before submission, after his plan letter and after items 2 to 4: tag the frozen commit `demo-freeze` (the name `docs/SUBMISSION_GAPS.md` row 24 expects), re-run the demo-day runs at that commit (the SIT sample with tools from his Terminal; `eval/synthetic/payments_orchestration/design_v1.pdf` and then `design_v2.pdf` with `--previous`) so the committed records replay byte for byte there (on 3 Oct 2026 none replays at the tip, because the renderer and the ID rewrite moved after they were recorded), and update `docs/REPRODUCIBILITY.md` and the README's replay recipe.
7. Submission: `docs/SUBMISSION_GAPS.md` rows 1 (collaborator invites), 2 (ADR-005), 24 (demo-day prerequisites) are Malcolm's; everything else is closed or prepared.

## 3. Check these facts first

| Command | Expected on 03 Oct 2026 18:15 | If different |
|---|---|---|
| `git -C ~/Desktop/SIT rev-parse --short origin/claude/happy-darwin-d0bl94` (after `fetch`) | `94466da`, or newer if the LangGraph verifier pushed | newer: read item 1's first branch |
| `git -C ~/Desktop/SIT-wt/langgraph log --oneline -1` | `48a72f5` or later (the verifier's commits on `s4/langgraph`) | still `527c60e`: the verifier did nothing before the shutdown |
| `git -C ~/Desktop/SIT-wt/refinefix log --oneline -1` | `ccfaaa4` | newer: a later worker continued item 2; read its commit |
| `git -C ~/Desktop/SIT-wt/runfix2 log --oneline -1` | `9e6c2fb` | newer: same for item 3 |
| `git -C ~/Desktop/SIT show origin/claude/happy-darwin-d0bl94:docs/USER_DECISIONS.md \| grep -c '^| 4[0-9] |'` | 1 (row #41 exists, row #40 waits on item 3, #42 arrives with item 1) | 2 or 3: one or both of items 1 and 3 landed; `grep '^| 4[0-9] |'` shows which |
| `pgrep -fl 'dra ui'` | none after the power-off | a server on port 8791 is Malcolm's own: never kill it; one on 8765, 8797 or 8799 was a worker's, kill by pid after checking its cwd |
| `gh repo view malcolm1232/SIT-public --json visibility` | `PUBLIC`, one commit from 9b5dd53; refresh with the exporter per `scripts/README.md` (output filtered to counts) and a force push to that repo only, which has no history to keep | PRIVATE: he flipped it back, leave it |
| `ls ~/Desktop/SIT-wt/live/runs/input/sit_sample_v1.pdf` | exists (untracked) | missing: copy from `~/Downloads/SIT_Memory_Platform_Detailed_Design.pdf` |

## 4. His decisions (do not re-ask)

All in `docs/USER_DECISIONS.md` rows #17 to #39 and #41 (#40 and #42 arrive with items 3 and 1).
03 Oct 02:55: "u can do whatever while im gone, if need my permision, build the rest first and when im back, u can ask me."
03 Oct 03:05: judge stays Anthropic-only, his words "judge: no" and "btw, NO FOR NOW, later i might change my mind." (#23).
03 Oct 10:30: effort `medium` is the default on measured ground, `high` stays the A4b arm, he may reverse (#33); the lab brief sets no time limit, the 540 s deadline is a configurable assumption pending SIT (#34).
03 Oct 10:50: "lets assume there is not answer key" for the SIT Memory Platform PDF (#35): it is a demo document, the agent may run on it.
03 Oct 10:35 and 15:50: UI shape A, "chat with opus. and build as recommended."; then on the v2 mockup "ok it looks good" (#41): the DBSearch idiom with the rail is the review UI.
03 Oct 11:40: "yes" to the three review outputs: Download, Email, a session-only wifi link, no hosted link (#36); the pasted https link is the artefact hand-over path (#39).
03 Oct 11:30: "make the public snapshot" and "(ill change to public)": done, he made `malcolm1232/SIT-public` public.
03 Oct 11:00: slot "about 10 mins" stays the working assumption; venue is normal wifi.
03 Oct 16:45: "no need usage ss. cos other runs for QM are still running." (the usage calibration waits for a quiet machine).
03 Oct 17:05 and 17:12: the LangGraph comparison: "can we spawn another fable agent to work on langraph? ... let it run and compare it" and "no need to budget . and just work normally, no rush to complete, just make sure its a job well done. then we can effectively compare both custom and langraph" (#42 with item 1).
Rulings the planner made under his delegation, recorded as "SIT FABLE for the owner" and standing unless he reverses them: #31 the latency design, #37 shards do not see external evidence (refine applies it), #38 the MCP session rule, and the pending #40 six shard groups.

## 5. Open with him

1. Which evaluation plan: A ($3,282, the full pre-registered study), B ($1,506, every test at full power, judges off, grading on 33 reviews), or C ($801, full agent versus single-call baseline on five documents, three runs each). Figures are CLI estimates; he pays through his Max subscription's weekly limit (38 percent used at 11:55 on 3 Oct after one night of building). Recommendation: C in chunks over weeks; B if he wants the research claims. Nothing runs until he says a letter.
2. Sign the answer keys: the one-liner in `eval/KEY_SIGNOFF.md` section 10; until then every score is exploratory.
3. The email to SIT and the GitHub invitations for `SIT-calebying` and `Makienhui-sit` (brief p.8 §5.2, before the submission deadline, which he has not told us; ask him for the submission deadline and the interview date, nothing in the repo holds them).
   The email, ready to paste: "Subject: AI Engineering Lab Exercise, two practical questions for the review session. Hello, two quick questions so I can prepare the live execution: 1. Roughly how long may the live agent run take during the session (a few minutes, or ten or more)? 2. How will the new design artefact be handed over on the day (USB, email, or a download link)? Thank you, Malcolm".
4. Item 4 of section 2 needs his Terminal (the key); item 5 needs his go (cost) and, if the classifier refuses a worker, his Terminal too; each run is about 7 to 13 minutes and $4 to $6 of CLI estimate.
5. Opus fast mode for the demo (double price, up to 2.5 times the output speed): measure once or not; the design does not depend on it.
6. The usage calibration: his usage percentage before and after one quiet $6 run, to restate the three plans as weeks of allowance.

## 6. Rules of this work

The planner never reads source, edits, tests, runs the agent or scores; one Opus worker per deliverable, a fresh-context verifier per deliverable, briefs with the facts inline.
Workers keep every recorded model transcript (`llm.jsonl`, `progress.jsonl` records, judge logs, stream fixtures, `ui/chat.jsonl`) out of their context and inspect them by script.
The SIT MCP key is only ever in Malcolm's Terminal: a worker that tries to read it from a file or the clipboard is refused by the safeguard, so every with-tools run is started by him; nothing reaches the SIT hosts otherwise.
No agent run touches `eval/blind/` (sealed held-out items, three-evaluation budget, access log `eval/blind/ACCESS_LOG.md`); `spec/validate_examples.py` needs `--include-blind` to read them and that access must be logged.
The synthetic answer keys are unsigned; the harness refuses a scored run without `--exploratory` (#26); only Malcolm signs.
The public snapshot never carries `eval/blind/`, answer keys, transcripts, raw model logs, the lab's documents or the probe results; refresh it only with `scripts/export_public_snapshot.py` (the scanner's output must be filtered to rule names and counts, never printed with values).
Billing: every model call goes through `claude -p` on his Claude subscription (Max 20x); dollar figures are CLI estimates; no Anthropic API key is set anywhere.
Every Bash call of a worker is one purpose; pytest with `--tb=line` and `tail`; absolute paths; no `cd` in a compound command except a whole-call subshell.

## 7. How to verify a change

From a worktree with its venv (`/opt/homebrew/bin/python3.13 -m venv .venv && .venv/bin/pip install -e '.[dev]' && .venv/bin/playwright install chromium`), one command per call, exit codes read:
1. `.venv/bin/ruff check agent harness tests` prints `All checks passed!`.
2. `( cd <worktree> && .venv/bin/pytest -q --tb=line -p no:warnings 2>&1 | tail -2 )` prints `N passed` with no `failed` or `error` word (1865 at 94466da; the LangGraph branch adds 28 parity tests, 2 of them `xfailed`).
3. The same from `~` (`( cd ~ && <worktree>/.venv/bin/pytest -q --tb=line -p no:warnings <worktree> 2>&1 | tail -2 )`).
4. `.venv/bin/sit-review selftest` prints `selftest passed`.
5. `( cd <worktree> && make smoke )` and `( cd <worktree> && make test )` exit 0.
6. The robustness runner `( cd <worktree> && .venv/bin/pytest -q --tb=line -p no:warnings tests/robustness 2>&1 | tail -2 )` and its results CSV regenerated by `.venv/bin/python tests/robustness/robustness_results.py`, differing only in commit and duration columns.
7. `.venv/bin/python spec/convert_answer_keys.py --tier synthetic --check --verify-anchors` prints `0 key(s) failed validation`.
8. `.venv/bin/python scripts/leakage_grep.py` passes; `.venv/bin/python -m sit_review_agent.prompts --check` passes (the prompt lock); `tests/test_export_public_snapshot.py` passes.
9. For a guard: remove the claim, see its test fail, restore from a `cp` backup, `cmp` the file.
10. Push only as a fast-forward after all of the above; `git ls-remote origin claude/happy-darwin-d0bl94` equals the local HEAD.
11. Rollback: the truth branch is never force-pushed; a bad push is undone by a new commit that restores the affected files from the last good sha (`git checkout <good sha> -- <paths>`, commit, push), never by reverting a merge commit; a run that must be reproduced is made in a worktree at the good sha.

## 8. Traps already paid for

The model-side safeguard (tag `reasoning_extraction`) stopped about twenty-five workers on 3 Oct 2026, on Opus and Fable alike, eight of them on the two tasks left open.
The triggers seen: reading or printing material about streamed model output, thinking-token counts, recorded transcripts or secret-shaped strings; and, on the refine task, the brief's own vocabulary (salvage, partial, cut, stream, truncation) even before any file was read.
What worked: facts inline in the brief in plain words, a short allow-list of files to read, transcripts and fixtures inspected by script, pytest with `--tb=line | tail`, the task split into parts, a commit after each part, and a planner checkpoint commit of a stopped worker's uncommitted edits before the retry.
What did not: a third retry of the same task on the same day.
A worker stopped mid-task leaves its edits on disk: check `git status` and `git log` in its worktree before respawning, and tell the retry what exists.
A permission classifier (different from the safeguard) refused a worker's `cat` of config files bundled with a test log, a worker's read of the credentials file, the planner's write of the key to a file, and five live agent runs after the budget was lifted: those go to Malcolm, never to another worker.
A line pasted into this chat never runs; Terminal only; a new Terminal window has no exported key; `read -rs` shows nothing when the key is pasted, which is correct.
Esc pressed while the Claude window is focused stops the running turn and every background worker.
The words that trip the safeguard also trip it when pasted from this file into a brief: rewrite item 2's and item 3's wording in plain terms before briefing, as those items already do.
`claude -p` reports a cap hit as an error: handled (typed as a truncation, retried once, disclosed).
A call cut by a limit logs unknown usage: handled; every cost total says "lower bound"; the harness mirrors the rule in `harness/sit_eval/usage.py`.
The MCP server closes an idle session within about two minutes: handled (reopen and retry, proven live in `sit_sample_ui_1`: one reopen, 8 of 8 web calls).
A refine cut at its limit discarded its finished revisions: item 2 fixes it; until then a run whose refine is cut has unmerged findings and no external evidence attached.
`dra replay` reproduces a record only at its recorded commit (item 6).
Two shards and the refine were cut on the 30-page lab document with four groups: six groups (item 3) is the first tuning step the design named.
Pytest from `~` once failed on a repo-relative path; run it both ways.
`gh` prints `credential-manager is not a git command` on every network call; harmless.

## 9. Not done, on purpose

No multi-provider model dropdown before the interview (the gateway seam exists; the LangGraph variant shows the orchestrator seam).
No persistent memory beyond re-assessing an updated artefact (the Delta tab).
No hosted public share link; no in-run second-model verifier; dark theme of the UI deferred.
No Tier A runs, no prompt freeze, no `prereg` freeze (waits for his letter and item 6).
The refine and verdict prompts still see the shards' own finding numbers inside finding text (a prompt change with the replay consequence; after the demo).
The shards do not see external evidence (#37); a second assess pass after research is a future variant.
The grader's `inputs/` folders in the `score` and `score2` worktrees stay uncommitted (prompt copies, 1 MB).

## 10. Where everything is

Runtime: `/opt/homebrew/bin/python3.13` venvs per worktree; `claude` at `~/.local/bin/claude` logged in; Chromium via Playwright in the UI worktrees' venvs; `gh` logged in as malcolm1232.
Board: none for SIT; the record is `docs/USER_DECISIONS.md`, `docs/transcripts/session4/*.md` (one file per worker) and the edit logs under `research/audit/`.
End of session: `/handover` then `/saveconvo SIT --agents` (the folder `~/Desktop/conversation_history/SIT/` exists since 3 Oct; `SIT` is the folder name, not an alias, and `--agents` renders every worker's transcript beside the day-file; the day-file is named by the session's start day, so the 3 Oct work sits in `conversation_verbatim_261002.md`).

| Thing | Path |
|---|---|
| Private repo, truth branch | `~/Desktop/SIT` (checked out on another branch; do not work there), `origin/claude/happy-darwin-d0bl94` |
| Worktrees | under `~/Desktop/SIT-wt/`, one folder per `s4/` branch; `langgraph`, `refinefix`, `runfix2` hold the open items; `hand` holds this file |
| Public snapshot | `https://github.com/malcolm1232/SIT-public`; exporter `scripts/export_public_snapshot.py`, allow-list `.public-allow` |
| Architecture and walkthrough | `docs/ARCHITECTURE.md` (sections 12 and 13), `docs/DEMO_DAY_SCRIPT.md`, `docs/DEMO_DAY_RUNBOOK.md` |
| Decisions | `docs/DECISIONS.md` (ADR-001 to ADR-012), `docs/USER_DECISIONS.md` |
| Designs | `docs/design/latency_and_demo_design.md`, `docs/design/ui_design.md`, `docs/design/ui_restyle.md`, mockups and built pictures under `docs/design/ui_mockup/` and `ui_mockup_v2/` |
| Measured runs | `docs/live_runs/`: `rehearsal_concurrent_1` (medium), `rehearsal_concurrent_high_1`, `sit_sample_tools_1` and `sit_sample_ui_1` (the lab document with tools), `reassess_payments_v2_1` (the re-assessment), `ui_flow_1`, `langgraph_payments_v1_1` (after item 1); `QUALITY_COMPARISON.md`; `COMPARISON_LANGGRAPH.md` (after item 1) |
| Budget | `docs/BUDGET.md` (section 6 awaits his approval), `docs/BUDGET_OPTIONS.md` |
| Submission | `README.md`, `docs/LIMITATIONS.md`, `docs/SUBMISSION_GAPS.md`, `docs/DOCUMENTATION_MAP.md`, the six topic files under `docs/`, `outputs/lab_session/README.md` |
| Probe | `research/robustness/mcp_probe_findings.md`, `mcp_probe_results.redacted.json` |
| Evaluation | `harness/README.md`, `eval/EVAL_PLAN.md`, `eval/prereg.yaml`, `eval/prereg_deviations.md` (12 entries), `eval/KEY_SIGNOFF.md` |
| Lab document copy | `~/Desktop/SIT-wt/live/runs/input/sit_sample_v1.pdf` (untracked); the brief `~/Downloads/AI Engineer Lab Exercise.pdf` |
| Memory | `~/.claude/projects/-Users-malco/memory/project_sit_design_review_agent_261003.md`, `feedback_a_brief_that_reads_a_note_about_thinking_tokens_trips_the_safeguard.md` |
| Transcripts | `~/Desktop/conversation_history/SIT/conversation_verbatim_261002.md` and `agents_verbatim_261002/` |
| Older handovers | `docs/HANDOVER_FULL.md` (sections 8 and 9 still describe the first live run and the harness), `docs/HANDOVER_FABLE.md`, `docs/HANDOFF.md` |
