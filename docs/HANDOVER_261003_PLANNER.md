# SIT planner - handover, written 03 Oct 2026 14:40 +08 by the "SIT FABLE on the Mac" session

START HERE. This file is self-contained: a new session needs nothing else to continue.
To start the next session say: "Read ~/Desktop/SIT/docs/HANDOVER_261003_PLANNER.md on branch claude/happy-darwin-d0bl94 and continue as the SIT planner; you spawn Opus workers and make the calls; the answer-key signature and the budget approval stay Malcolm's."
Supersedes: `docs/HANDOVER_FULL.md` section 10 and `docs/HANDOVER_FABLE.md` (both carry a SUPERSEDED line).

## 1. Goal and where it stands

Malcolm's words, 3 Oct 2026 02:50: "you are fable now, u delegate tasks to opus agents to do? u can spawn them if youd like. and u make the shot calling, ok? u have explicit permission to shot call."
The product is a design-document review agent for the SIT AI Engineering Lab Exercise (brief at `~/Downloads/AI Engineer Lab Exercise.pdf`, nine pages, no time limit stated) plus a research-grade evaluation harness.
Done and verified on the pushed branch `claude/happy-darwin-d0bl94` at 9b5dd53: the latency redesign (concurrent first stage, refine as revisions, verdict-only call, salvage of cut calls), honest cost accounting, the scoring guard, the sign-off decisions applied to the keys, the measured rehearsals and their scoring, the probe of the SIT MCP servers, the redone budget with three options, the architecture document, the public snapshot exporter.
In flight at writing: ONE hub worker on branch `s4/final` (worktree `~/Desktop/SIT-wt/final`, last seen at 67c69e2) merging three unpushed builder branches, verifying them, and pushing: `s4/ui-out` d3792bd (the review UI, see `docs/design/ui_design.md`), `s4/fixrefs` d8274dc (finding IDs rewritten through the merge map, invariant INV-12), `s4/mcpfix` 3118a96 (MCP session reopen and retry, disclosure wording).
Next after the hub: the owner-only items of section 5, then the demo-day rehearsal with the UI on the lab document, then the small evaluation plan he picks.

| Step | What | Where | State |
|---|---|---|---|
| A | Hub merges and pushes the UI, the ID fix and the MCP fix | `s4/final` | in flight; item 1 below checks it |
| B | Demo-day rehearsal with the UI on the lab document, with tools | section 2 item 4 | not started |
| C | Evaluation plan A, B or C from `docs/BUDGET_OPTIONS.md` | section 5 | waits for his word |
| D | Submission documents per `docs/DOCUMENTATION_MAP.md` | `docs/` | not started |

## 2. Do this next

Mechanics first.
Item 1 runs before anything else.
The truth is the remote branch `origin/claude/happy-darwin-d0bl94` of the private repo `malcolm1232/SIT`; every piece of work is a branch `s4/<name>` in its own worktree under `~/Desktop/SIT-wt/`, merged and pushed only by a verifier that ran every gate (section 7).
The planner spawns one Opus worker per deliverable with the Agent tool (`model: "opus"`), a separate verifier per deliverable, and reads only their reports; a worker stopped by the safeguard is respawned on Fable with its notes and the facts inline (section 8).
Commits carry the identity `malcolm1232 <66200354+malcolm1232@users.noreply.github.com>` and never a co-author or agent line; scoped `git add` only.
"Item" means this list; "step" means the table in section 1.

1. Check the hub.
   Run `git -C ~/Desktop/SIT fetch origin && git -C ~/Desktop/SIT rev-parse --short origin/claude/happy-darwin-d0bl94`.
   If it prints something newer than 9b5dd53, read `docs/transcripts/session4/final_hub.md` on the remote tip (its "for the next session" section) and go to item 2.
   If it still prints 9b5dd53, the hub was stopped: read `git -C ~/Desktop/SIT-wt/final log --oneline 9b5dd53..HEAD` and `git -C ~/Desktop/SIT-wt/final status --porcelain`, then spawn a fresh Opus verifier with the brief in `docs/transcripts/session4/final_hub.md` if that file exists on `s4/final`, otherwise with this instruction: merge `s4/ui-out`, `s4/fixrefs`, `s4/mcpfix` into `s4/final`, run section 7 in full, record decisions #36 to #38 as described in section 4, update `docs/ARCHITECTURE.md` from "in build" to present tense for the UI, `finding_refs.py`, INV-12 and `progress.jsonl`, and push `s4/final:claude/happy-darwin-d0bl94` without force.
   Done when `git ls-remote origin claude/happy-darwin-d0bl94` shows a commit that contains `agent/sit_review_agent/ui/server.py` and `agent/sit_review_agent/finding_refs.py` (`git -C ~/Desktop/SIT ls-tree -r --name-only origin/claude/happy-darwin-d0bl94 | grep -c -E 'ui/server.py|finding_refs.py'` prints 2).
2. Commit this handover and the two SUPERSEDED lines.
   They sit uncommitted in `~/Desktop/SIT-wt/arch` on `s4/arch` (`docs/HANDOVER_261003_PLANNER.md`, `docs/HANDOVER_FULL.md`, `docs/HANDOVER_FABLE.md`).
   After item 1, run `git -C ~/Desktop/SIT-wt/arch fetch origin && git -C ~/Desktop/SIT-wt/arch merge --no-edit origin/claude/happy-darwin-d0bl94`, commit the three files with the message `Handover of 3 Oct 2026: the planner session`, and push `s4/arch:claude/happy-darwin-d0bl94`.
   Done when the remote tip contains `docs/HANDOVER_261003_PLANNER.md`.
3. Refresh the public snapshot after item 2 so it holds the merged UI and this handover.
   Run `~/Desktop/SIT-wt/arch/.venv/bin/python ~/Desktop/SIT-wt/arch/scripts/export_public_snapshot.py --target <empty dir in the scratchpad> --repo ~/Desktop/SIT-wt/arch --allow-file ~/Desktop/SIT-wt/arch/.public-allow --allow 'home-path:tests/test_export_public_snapshot.py' --init-git` with its output piped through `grep -E '^(included|GOOD|NOT GOOD)'` only (never print the scanner's matched values: three workers were stopped by the safeguard doing so).
   Then push that one commit to `https://github.com/malcolm1232/SIT-public` (`git -C <dir> remote add origin https://github.com/malcolm1232/SIT-public.git && git -C <dir> push --force origin HEAD:main`; the force is correct here, the snapshot has no history to keep).
   Done when the snapshot's `docs/ARCHITECTURE.md` says the UI is present tense.
4. Demo-day rehearsal with the UI on the lab document, with tools.
   Malcolm runs it; the MCP key lives only in his Terminal and the safeguard refuses any agent that touches it.
   Give him these lines for one Terminal window: `read -rs SIT_MCP_API_KEY && export SIT_MCP_API_KEY` (he pastes the key from the brief's "Shared API key (all 4)" line, nothing echoes), then `cd ~/Desktop/SIT-wt/final && env -u ANTHROPIC_API_KEY .venv/bin/sit-review preflight --warm --profile demo && env -u ANTHROPIC_API_KEY .venv/bin/dra ui --host 0.0.0.0 --allow-remote --port 8791 --runs-dir runs` (use whichever worktree holds the pushed tip with a venv), then he drops `runs/input/sit_sample_v1.pdf` (already in `~/Desktop/SIT-wt/live/runs/input/`, copy it) on the page and starts the run with the demo profile.
   A worker then reads the run directory by script (never printing `llm.jsonl`), writes `docs/live_runs/<run id>/MEASUREMENT.md` like `docs/live_runs/sit_sample_tools_1/MEASUREMENT.md`, checks that web search now works after the session fix (five calls failed in the first run because the server had closed the idle session), and commits.
   Done when the note exists and the search calls succeeded.
5. The evaluation plan, once he picks A, B or C (section 5): spawn one worker per chunk of at most ten runs, each chunk scored with `--exploratory` until the keys are signed, each with the harness's cost stop, resumable by its result cache.
6. Owner-only follow-ups when he is ready: sign the keys (section 5), re-score the old run `docs/live_runs/live_cc_opus_payments_v1` on the current key (about $10) so `docs/live_runs/QUALITY_COMPARISON.md` is like for like, declare the second pass of the effort sweep in `eval/EVAL_PLAN.md` Tier A (about $96), re-base `eval/prereg.yaml` `costs.per_run_usd.heavy_case_FULL` from $3.24 with a deviation entry.

## 3. Check these facts first

| Command | Expected on 03 Oct 2026 14:40 | If different |
|---|---|---|
| `git -C ~/Desktop/SIT rev-parse --short origin/claude/happy-darwin-d0bl94` (after `fetch`) | `9b5dd53` | newer: the hub pushed, item 1 is done |
| `git -C ~/Desktop/SIT-wt/final log --oneline -1` | `67c69e2` or later | the hub moved on; read its report |
| `git -C ~/Desktop/SIT-wt/arch status --porcelain` | three `M`/`??` lines: this file and the two SUPERSEDED lines | already committed: skip item 2 |
| `pgrep -fl 'dra ui'` | one server on port 8765 serving `~/Desktop/SIT-wt/uiint/runs` (started by this session for him to look at) | none: fine; kill it with `pkill -f 'dra ui --port 8765'` after checking its cwd |
| `gh repo view malcolm1232/SIT-public --json visibility` | `PUBLIC` (he flipped it himself at about 14:30) | PRIVATE: he has not flipped it; leave it |
| `ls ~/Desktop/SIT-wt/live/runs/input/sit_sample_v1.pdf` | exists (untracked, gitignored) | missing: copy from `~/Downloads/SIT_Memory_Platform_Detailed_Design.pdf` |
| `git -C ~/Desktop/SIT-wt/score status --porcelain` and `score2` | one untracked grader `inputs/` folder each | left uncommitted on purpose (prompt copies, 1 MB); never add them |

## 4. His decisions (do not re-ask)

All recorded in `docs/USER_DECISIONS.md` rows #17 to #35 (rows #36 to #38 are in the hub's brief, see item 1).
03 Oct 2026 02:55: "u can do whatever while im gone, if need my permision, build the rest first and when im back, u can ask me."
03 Oct 2026 03:05: judge stays Anthropic-only, his words: "judge: no" and "btw, NO FOR NOW, later i might change my mind." (#23).
03 Oct 2026 09:40: "rewrite then,, since ur rec." on dropping a co-author line from unpushed history (done).
03 Oct 2026 10:30: effort `medium` is the default on measured ground (#33, planner ruling under his row #1 clause); `high` stays the A4b arm; he may reverse.
03 Oct 2026 10:50: "lets assume there is not answer key" for the SIT Memory Platform PDF (#35): the SIT sample is a demo and rehearsal document, not an evaluation item; no human key will be written.
03 Oct 2026 10:35: UI shape A, "chat with opus. and build as recommended." (#31 and the UI design note).
03 Oct 2026 11:40: "yes" to the three review outputs (Download, Email, session-only share link; no hosted link) (#36, to be recorded by the hub).
03 Oct 2026 11:30: "make the public snapshot" and "(ill change to public)"; the snapshot repo exists and he made it public.
03 Oct 2026 11:00: slot length "about 10 mins" stays the working assumption; the lab brief states no limit (#34); venue is normal wifi; the PDF arrives by file or by a pasted https link (built).
02 Oct 2026 (earlier sessions): Opus 5.5 for every agent call (#1), Claude Code CLI backend so no API key is needed (#9), matcher rule (#10), partial matches (#14), no second provider (#16).

## 5. Open with him

1. Which evaluation plan: A ($3,282, the full pre-registered study), B ($1,506, every pre-registered test at full power, judges off, grading on 33 reviews), or C ($801, full agent versus single-call baseline on five documents, three runs each). The figures are the CLI's estimates; he pays through his Max subscription's weekly limit, which stood at 38 percent used on 3 Oct 11:55 after one night of building. My recommendation: C, run in chunks across weeks; B if he wants the research claims. Nothing runs until he says a letter.
2. Sign the answer keys: the one-liner in `eval/KEY_SIGNOFF.md` section 10, tested end to end on a copy; until then every scoring is exploratory and cannot go in the submission.
3. The email to SIT (two lines, drafted in the transcript of 3 Oct 2026): how long the live run may take, and how the PDF is handed over; and inviting the GitHub IDs `SIT-calebying` and `Makienhui-sit` as collaborators on the private repo before the submission deadline (lab brief p.8 §5.2).
4. Opus fast mode for the demo (double price, up to 2.5 times the output speed): measure once or not; the design does not depend on it.
5. A usage calibration: his usage percentage before and after one quiet $6 run, so the three plans can be restated as weeks of allowance; it was not possible on 3 Oct 2026 because workers ran all day.
6. The `/saveconvo` folder: no `SIT` folder exists under `~/Desktop/conversation_history/`; he has not said yes to creating one.

## 6. Rules of this work

The planner never reads source, edits, tests, runs the agent or scores; one Opus worker per deliverable, a fresh-context verifier per deliverable, briefs with the facts inline.
Workers get the Read tool for documents and are told to keep every recorded model transcript (`llm.jsonl`, judge logs, stream fixtures, `progress.jsonl` records) out of their context and to inspect them by script; see section 8.
Nothing runs on the SIT MCP hosts without the key, and the key is only ever in Malcolm's Terminal: a worker that tries to read it from a file or the clipboard is refused by the safeguard, so a with-tools run is started by him.
No agent run touches `eval/blind/` (sealed held-out items, three-evaluation budget, access log at `eval/blind/ACCESS_LOG.md`); `spec/validate_examples.py` needs `--include-blind` to read them and that access must be logged.
The synthetic answer keys are unsigned; the harness refuses a scored run without `--exploratory` (#26); only Malcolm signs.
The public snapshot never carries `eval/blind/`, answer keys, transcripts, raw model logs, the lab's documents, or the probe results; refresh it only with the exporter.
Billing: every model call goes through `claude -p` on his Claude subscription (Max 20x); dollar figures are the CLI's estimates; no Anthropic API key is set anywhere.
No em dash anywhere; commit messages in the repo's style with no attribution line; never `git add -A`; never force-push the private branch.
Every Bash call of a worker is one purpose; absolute paths; no `cd` in a compound command except a whole-call subshell.

## 7. How to verify a change

From a worktree with its venv (`/opt/homebrew/bin/python3.13 -m venv .venv && .venv/bin/pip install -e '.[dev]'`), one command per call, exit codes read:
1. `.venv/bin/ruff check agent harness tests` prints `All checks passed!`.
2. `( cd <worktree> && .venv/bin/pytest -q 2>&1 | tail -1 )` prints `N passed, 0 failed` (1704 on `s4/ui-out`, 1586 on `s4/mcpfix`, 1624 at 9b5dd53; the merged count is at least the union).
3. The same from `~` (`( cd ~ && <worktree>/.venv/bin/pytest -q <worktree> 2>&1 | tail -1 )`), because one test used to depend on the working directory.
4. `.venv/bin/sit-review selftest` prints `selftest passed`.
5. `( cd <worktree> && make smoke )` and `( cd <worktree> && make test )` exit 0.
6. The robustness runner (`( cd <worktree> && .venv/bin/pytest -q tests/robustness 2>&1 | tail -1 )`) and the results CSV regenerated by `tests/robustness/robustness_results.py`, diffing only in commit and duration columns.
7. `.venv/bin/python spec/convert_answer_keys.py --tier synthetic --check --verify-anchors` prints `0 key(s) failed validation`.
8. `.venv/bin/python scripts/leakage_grep.py` passes; the prompt lock check passes.
9. For a guard: remove the claim, see its test fail, restore from a `cp` backup, `cmp` the file.
10. Push only as a fast-forward after all of the above, then `git ls-remote origin claude/happy-darwin-d0bl94` equals the local HEAD.

## 8. Traps already paid for

The model-side safeguard (tag `reasoning_extraction`) stopped about fourteen workers on 3 Oct 2026, on Opus and Fable alike.
Every stop followed reading or printing material about streamed model output, thinking-token counts, recorded transcripts, or secret-shaped strings.
Put the facts inline in the brief, forbid those reads, inspect by script, split the task, commit per part.
A worker stopped mid-task leaves its edits on disk: check `git status` and `git log` in its worktree before respawning, and tell the retry what exists.
A line pasted into this chat never runs; Terminal only, without a leading `!`; a new Terminal window has no exported key.
`claude -p` reports a cap hit as an error, not a truncation: handled since the integration items (a truncation is typed, retried once, then disclosed).
A deadline-cut call logs no usage: handled; costs say "lower bound" when any call is unrecorded, and the harness mirrors that rule (`harness/sit_eval/usage.py`).
The MCP server closes an idle session within about two minutes: handled on `s4/mcpfix` (reopen and retry); unverified against the real servers until item 4.
`dra replay` reproduces a record only at its recorded commit; a changed report renderer makes replay report a divergence; never rewrite a committed run directory.
The lab brief says document-intelligence "rejects all inputs"; the probe showed it rejects anything but `file://` and `https://` sources; it stays disabled.
Pytest from `~` once failed on a repo-relative path: fixed, but run it both ways.
`gh` prints `credential-manager is not a git command` on every network call; harmless.

## 9. Not done, on purpose

No multi-provider model dropdown before the interview (the gateway seam exists; after the demo).
No persistent memory beyond re-assessing an updated artefact (the delta view).
No hosted public share link (only the session-only wifi link).
No second-model verifier inside the live run (the grader is the on-demand second opinion).
No Tier A runs yet (waits for his letter), no prompt freeze, no `prereg` freeze.
The refine and verdict prompts still see the shards' own finding numbers inside finding text (a prompt change with the replay consequence; after the demo).
The shards do not see external evidence (research runs beside them and feeds refine; #37 in the hub's brief).
`markdown-it-py` and Playwright declared in `pyproject.toml` by the hub if it got that far; check.
The second cold-read of the UI against the live page, SMTP against a real provider, the share link from a second device: listed in each report's "not verified".

## 10. Where everything is

Runtime: `/opt/homebrew/bin/python3.13` venvs per worktree; `claude` at `~/.local/bin/claude` logged in; Chromium via Playwright in the UI worktrees' venvs.
Board: none for SIT (the QuantifyMe board is a different project); the record is `docs/USER_DECISIONS.md`, `docs/transcripts/session4/*.md` and the edit logs under `research/audit/`.
End of session: `/handover` then `/saveconvo <alias> --agents` once a `SIT` folder exists (section 5 item 6).

| Thing | Path |
|---|---|
| Private repo, truth branch | `~/Desktop/SIT` (checked out on another branch; do not work there), `origin/claude/happy-darwin-d0bl94` |
| Worktrees | under `~/Desktop/SIT-wt/`, one folder per `s4/` branch (`git -C ~/Desktop/SIT worktree list` prints them); `~/Desktop/SIT-wt/final` is the hub, `~/Desktop/SIT-wt/arch` holds this file |
| Public snapshot | `https://github.com/malcolm1232/SIT-public`, exporter `scripts/export_public_snapshot.py` |
| Architecture and walkthrough | `docs/ARCHITECTURE.md` (sections 12 and 13) |
| Decisions | `docs/DECISIONS.md` (ADR-001 to ADR-012), `docs/USER_DECISIONS.md` |
| Latency design and UI design | `docs/design/latency_and_demo_design.md`, `docs/design/ui_design.md`, mockups and built screenshots under `docs/design/ui_mockup/` |
| Measured runs | `docs/live_runs/rehearsal_concurrent_1/`, `rehearsal_concurrent_high_1/`, `sit_sample_tools_1/`, `ui_flow_1/`, each with `MEASUREMENT.md`; `docs/live_runs/QUALITY_COMPARISON.md` |
| Budget | `docs/BUDGET.md` (section 6 awaits his approval), `docs/BUDGET_OPTIONS.md` |
| Demo | `docs/DEMO_DAY_RUNBOOK.md`, lab document copy at `~/Desktop/SIT-wt/live/runs/input/sit_sample_v1.pdf` (untracked) |
| Probe | `research/robustness/mcp_probe_findings.md`, `mcp_probe_results.redacted.json` |
| Evaluation | `harness/README.md`, `eval/EVAL_PLAN.md`, `eval/prereg.yaml`, `eval/prereg_deviations.md` (12 entries), `eval/KEY_SIGNOFF.md` |
| Session records | `docs/transcripts/session4/` (one file per worker), edit logs `research/audit/*_editlog.md` |
| Memory | `~/.claude/projects/-Users-malco/memory/project_sit_design_review_agent_261003.md` and `feedback_a_brief_that_reads_a_note_about_thinking_tokens_trips_the_safeguard.md` |
| Older handovers | `docs/HANDOVER_FULL.md` (sections 8 and 9 still describe the first live run and the harness), `docs/HANDOVER_FABLE.md`, `docs/HANDOFF.md` |
