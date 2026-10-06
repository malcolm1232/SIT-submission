# SIT planner - handover, written 06 Oct 2026 14:40 +08 by the "SIT planner, 6 Oct" session

START HERE. This file is enough to run items 1 to 7 and to judge every item; items 8, 9 and 10 also read the named item of `docs/HANDOVER_261005_PLANNER_B.md` (the planner reads it with `git -C ~/Desktop/SIT show origin/claude/happy-darwin-d0bl94:docs/HANDOVER_261005_PLANNER_B.md` and inlines what the worker needs).
To start the next session say: "Run git -C ~/Desktop/SIT fetch origin && git -C ~/Desktop/SIT show origin/claude/happy-darwin-d0bl94:docs/HANDOVER_261006_PLANNER.md, read that output as the SIT planner handover, and continue as the SIT planner; you spawn Opus workers and make the calls; the answer-key signatures, the held-out items, the money for live runs and anything that needs the SIT MCP key stay Malcolm's."
Supersedes: `docs/HANDOVER_261005_PLANNER_B.md` (written 05 Oct 15:45; its items 1, 2, 3 are done and on the tip; its items 4 to 9 and section 5 are carried forward below, renumbered).
This file is committed on the truth branch, so the `git show` form works; `~/Desktop/SIT` is checked out on an older branch and never holds it.
All times are Singapore time (+08).
Facts marked "(planner)" come from the 6 Oct planner's report and were not re-run by the writer of this file; everything else was read from git or the disk at 14:36 on 06 Oct 2026.

## 1. Goal and where it stands

Malcolm's words, 3 Oct 2026 02:50: "you are fable now, u delegate tasks to opus agents to do? u can spawn them if youd like. and u make the shot calling, ok? u have explicit permission to shot call."
The product is a design-document review agent for the SIT AI Engineering Lab Exercise (a live run on a document SIT hands over, a re-assessment of an updated artefact, an on-the-spot modification, submission through a private GitHub repository) plus a research-grade evaluation harness.
Truth branch `origin/claude/happy-darwin-d0bl94`, tip c7857de before this file's commit (2190 tests pass there, planner); the backup branch `origin/s4/ui-integration` equals c7857de.
Done on his words of 5 and 6 Oct, all merged into the tip (86 commits since the 5 Oct handover 3fbf06b): the three stalled branches of 5 Oct (INV-05 edges, A3 resolved prior = decision #49, the scorer manifest guard), demo deadline 900 s (#47), reserves scaled with the limits (#48), the cross-linked export and the app's Review, Coverage and Evidence tabs on one renderer, the run log stage panels and findings funnel, the Architectural design view, the research defect fix (#50, deviation 17), the flaky rail test fix.
In flight: his other session is editing the live UI tree uncommitted (item 1); his second rehearsal, tools on at 15 min, his words "im still doing" (item 9).
Next: merge his UI session when it commits (item 1), his one-line commit of a worker note (item 2), then the small fixes of items 3, 4 and 6 by workers.

| Step | What (all on the tip c7857de) | Key files |
|---|---|---|
| A | Demo profile deadline 900 s, stage limits 441 / 775 / 883 s, reserves 125 / 334 s (#47, deviation 15) | `config/profiles/demo.yaml` |
| B | Reserves scale with the limits when a run's deadline is not the profile's; `--deadline 540` gives the former clock, research ends by 264 s (#48, deviation 16) | `llm/runtime.py`, `StopRulesConfig.effective` |
| C | Export cross-linked: every FND/EV/DEG/AD/SA/RQ/P/FR/NFR/section/page/[doc:] id a link, a Reference part with a sourced glossary, a side pane that never moves the main column, a hover card that stays open and scrolls, PDF table rows rebuilt with pdfplumber, outside sources as safe links, the PDF in the zip, no part files | `ui/xref.py`, `ui/static/xnav.js`, `ui/static/review.css`, `export.review_fragment` |
| D | The app's Review, Coverage and Evidence tabs drawn by the export's renderer; a counts row with pane lists; glossary "How findings are scored"; chat streams with Stop and shows no money; the Delta tab explains itself; Download popover; favicon | `ui/server.py`, `ui/static/app.js` |
| E | Run log stage panels for every stage and the findings funnel (on his document-only run: 66 drafts to 30 reported, 64 of 66 refine revisions salvaged, 36 merges, planner); the cut-time WARN line that wrongly said no refine pass ran is fixed | `ui/stages.py`, routes `/runs/{id}/stage/{name}`, `/funnel`, `/glossary`; `phases/_model_calls.py` |
| F | The "Architectural design" view in the rail: 27 topics, Simple and Advanced tabs, names read from config and code | `ui/architecture.py`, `ui/static/architecture.{js,css,json}` |
| G | Research defects: an in-band tool failure is `ok=False` in the gateways, so it never reaches the ledger; external excerpts are readable text (#50, deviation 17) | `tools/inband.py` |
| H | INV-05 edges, A3 (#49), scorer guard (`sit-eval score` refuses when `manifest.json` and the report's `run_manifest` disagree on the condition) | notes under `docs/transcripts/session7/` |

Paths in the table are under `agent/sit_review_agent/`.

## 2. Do this next

Mechanics first.
"Item" means this list; "step" means the table in section 1; "#nn" is a row of `docs/USER_DECISIONS.md`; "deviation nn" an entry of `eval/prereg_deviations.md`.
Section 3 runs before item 1; its commands are read-only and the planner runs them itself.
The planner never reads source, edits, tests or runs the agent: one Opus worker per deliverable (Agent tool, `model: "opus"`), a fresh-context Opus verifier per code deliverable, briefs with the facts inline; the planner may commit a stopped worker's edits as a WIP checkpoint in that worker's worktree; the `/delegator` skill describes this role and may be loaded, it changes nothing here.
Order when nothing is blocked: item 3, then item 4 (after item 1 if possible), then item 6 (a) to (d), then item 10; items 1, 2 and 9 run whenever their trigger arrives.
A new worker writes its note in its commit message body and its report, never under `docs/transcripts/` (section 8); the planner carries the essentials into the next handover.
One worker at a time owns `docs/USER_DECISIONS.md` and `eval/prereg_deviations.md`, so row numbers never collide.
Before `git worktree add -b <name>`, check `git -C ~/Desktop/SIT branch --list <name>`; if the name is taken, add a suffix (`-2`).
A gate that fails at the tip before any change (a flake, a count other than 2190) is fixed as its own item first (his standing rule: lint, test failures and flakiness are always fixed), never retried away.
Malcolm is reached with the PushNotification tool (one line, under 200 characters) whenever his word, his Terminal or his money is needed; if the tool is absent, ask in the chat and work the items that need nothing from him.
His answers are recorded by a worker as the next rows of `docs/USER_DECISIONS.md` (51 onward) with his words.
Code ships by push to the truth branch only, as a fast-forward, by the worker or verifier after the gates of section 7; never `--force`; no deploy exists, the app runs on his Mac.
The live page is his: `~/Desktop/SIT-wt/start_sit_ui.sh` starts `dra ui` from `~/Desktop/SIT-wt/ui-integration` (branch `s4/ui-integration`) on 127.0.0.1:8765, with the SIT MCP key read from the macOS Keychain item `SIT_MCP_API_KEY` (saved 6 Oct; never printed, never in a file) (planner).
Never kill, restart or merge into that tree while his server runs from it: merge in the sibling worktree `~/Desktop/SIT-wt/ui-integration-2` (branch `s4/ui-integration-2`, clean at c7857de) and fast-forward (section 8).
Commits use the repo's configured identity (`git -C <wt> config user.name` prints `malcolm1232`), never a co-author or agent line even when a harness reminder asks for one (his CLAUDE.md wins); scoped `git add <file>` only; no em dash anywhere.
Worker cap: three at once; every worker reads `uptime` and `memory_pressure` before a test run (section 6).
Live model runs cost his Max subscription and each needs his word first; a run-id is never reused.

1. Merge his UI session when it commits.
   Now: `git -C ~/Desktop/SIT-wt/ui-integration status -s` shows six modified files (`ui/architecture.py`, `ui/server.py`, `ui/static/app.js`, `ui/static/architecture.{css,js,json}`) and two untracked (`ui/naming.py`, `ui_screens/`): placeholders for the product name and research stop-rule tips, his other session's work (planner).
   His edits are real features (product-name placeholders in the UI copy and tips on the research stop rule), not scratch; they are his session's to finish.
   Do not touch that tree; check at the start of each turn with `git -C ~/Desktop/SIT-wt/ui-integration log --oneline -1` whether a commit above c7857de appeared.
   Merge only when `status -s` there shows no modified tracked file (his session is done); a commit that leaves modified files behind means it is still working: wait, or ask him.
   When it is done, one Opus worker in `~/Desktop/SIT-wt/ui-integration-2`: `git fetch origin`; `git merge --ff-only origin/claude/happy-darwin-d0bl94` (brings this file); `git diff --stat HEAD s4/ui-integration` and report the file list (anything outside `agent/`, `tests/`, `docs/`, for example screenshots from `ui_screens/`, is NOT merged without his word); `git merge -m "Merge s4/ui-integration (his UI session) into s4/ui-integration-2" s4/ui-integration` (the local branch is shared across worktrees; a conflict is reported with file and hunk, not resolved); the gates of section 7, plus a fresh-context review of his diff as for any code deliverable, plus the browser check: the Architectural design view opens from the rail, both tabs render all topics, no console error, screenshots at 1024 and 1440 px; then push `HEAD:claude/happy-darwin-d0bl94` only.
   Then notify him; he runs (or allows a worker to run) `git -C ~/Desktop/SIT-wt/ui-integration merge --ff-only origin/claude/happy-darwin-d0bl94 && git -C ~/Desktop/SIT-wt/ui-integration push origin HEAD:s4/ui-integration`, safe only with that tree clean; a server restart for new Python code is his (`~/Desktop/SIT-wt/start_sit_ui.sh`).
   Done when `git ls-remote origin claude/happy-darwin-d0bl94` equals the merged HEAD; the fast-forward of his tree may lag on his word and does not block other items.
   If items 3, 4 or 6 push first, the worker merges the tip in the same way; item 4 touches the pane code beside his `app.js` edits, so run item 4 after item 1 when possible.
2. His commit of a worker note (he runs it; the auto-mode classifier refuses an agent reading or committing anything under `docs/transcripts/`).
   The note `docs/transcripts/session7/score-manifest-disagree.md` is on disk, untracked, in `~/Desktop/SIT-wt/score-manifest-disagree` (branch `s4/score-manifest-disagree` at 2341d39, already merged into the tip).
   The planner's line of 6 Oct pushed from 2341d39, which is now behind the tip, so it would be refused as non-fast-forward; the line below fast-forwards first (the untracked note is not on the tip, so the fast-forward is clean).
   His one line, in a Terminal: `cd ~/Desktop/SIT-wt/score-manifest-disagree && git fetch origin && git merge --ff-only origin/claude/happy-darwin-d0bl94 && git add docs/transcripts/session7/score-manifest-disagree.md && git commit -m "Worker note: scorer manifest guard, verified" && git push origin HEAD:claude/happy-darwin-d0bl94`.
   Done when `git ls-tree -r --name-only origin/claude/happy-darwin-d0bl94 docs/transcripts/session7/ | grep -c '\.md$'` prints 9.
3. Escape `|` in the evidence register, one Opus worker in a new worktree off the tip (`git -C ~/Desktop/SIT worktree add -b s4/pipe-escape ~/Desktop/SIT-wt/pipe-escape origin/claude/happy-darwin-d0bl94`, then the venv of section 7).
   Defect: `agent/sit_review_agent/report/templates/report.md.j2` does not escape `|` in an evidence-register title, so two rows split into extra columns in `report.md` of his tools run `ui-261005-170012-2648` (planner; the row ids were not recorded, the worker finds them by script counting `|` per table row).
   Fix in the template or a filter, applied to every table cell of that template whose value comes from a document, a tool or a model (titles, quotes, notes, citations), not only the title; test: a title with `a | b` renders as one row with the column count of the header; a mutation (remove the escape) fails it; gates of section 7; push.
4. The side pane at 1024 px, one Opus UI worker after item 1: at 1024 px the pane overlays about half the links of the Review tab and of the exported review (planner, on his document-only run); the planner's proposed fix, not yet ruled and the worker may propose better: open the pane on the left when the clicked link would be covered.
   Files `ui/static/xnav.js`, `ui/static/review.css`; same behaviour in the export and the app (one renderer); browser screenshots at 1024, 1280 and 1440 px, the clicked link visible and the main column unmoved; gates of section 7.
5. The old tools run `ui-261005-170012-2648` still cites the failed search EV-001 in FND-044: the fix of step G applies to new runs only.
   No worker action; a past run is a record and is not rewritten; his next tools-on run (item 9) is the proof; say so if he shows that run.
6. Run records that are missing, one sub-item at a time, each a builder then a verifier: (a) which research question each tool call served; (b) the time and call budget each question had and used, recorded only, no new limit; (c) per-invariant results of verify (pass or fail per INV id); (d) the two refine revisions that were dropped (64 of 66 salvaged) and why.
   These are additions to what a run writes (`tools.jsonl`, `progress.jsonl`, `report.json` extras) and to the run log panels; existing fields are unchanged and old runs still load; the planner rules the field names from the worker's proposal and records each as a decision row under the delegation.
   Brief them at the gateway and record level: name the record file and the field, never ask the worker to study `phases/research.py`, `phases/verify.py` or tool payloads (section 8); (a) and (c) need a small hook in those phases: give the worker the exact function name to wrap and forbid reading beyond it; if a sub-item still stops on the safeguard, checkpoint and park it in the next handover.
7. The public snapshot `malcolm1232/SIT-public` is the 3 Oct snapshot; a refresh is blocked by 12 scan findings and his word is "not yet"; nothing to do until he says go.
8. The v2 reruns (about $92, stop at $110), his word "not yet"; the plan and commands are in `docs/HANDOVER_261005_PLANNER_B.md` item 6.
   New since then: the demo profile now runs to 900 s, while the plan D v1 runs ran at 540 s; section 5 point 2 asks which clock.
9. His second rehearsal, tools on, 15 min, in his live page; his words "im still doing".
   When he says it ended, the newest folder in `~/Desktop/SIT-wt/ui-integration/runs/` is the run; one Opus worker copies it with `cp -R` into its own worktree (reading his tree is allowed, writing is not) and measures the copy by script (counts, ids, durations, rule names; never finding text) against the nine checks of `docs/HANDOVER_261005_PLANNER_B.md` item 5, plus: research questions answered (the 5 Oct tools run answered 0 of 8 because SIT's search server failed on every search, DuckDuckGo "no results" and Tavily "TAVILY_API_KEY not configured", planner) and no ledger entry from a failed call.
   The record goes to `docs/live_runs/sit_sample_ui_3/`; a cold reader fills the four `[TO FILL FROM REHEARSAL 2]` lines of `docs/EXPLAIN_AS_IT_RUNS.md` (lines 189 to 192) and pushes.
   If every search fails again, that is SIT's server, not the agent: the worker reports it and the planner tells him (section 5 point 4).
10. INV-05 residuals (carried from the 5 Oct item 9, not started): (a) a URL at a line end joins the next line's first word (`https://a.example/xfor` counts as allowed when the document has `https://a.example/x` at a line end followed by `for`); (b) `quote_in_document` checks a quote's URL as a prefix of any document URL, not the one at its position.
    The rule for (a): a line-end join is accepted only when the joined text matches a URL that appears whole elsewhere in the document, a tool result or a ledger `url_or_citation`, or when the next line's fragment itself looks like a URL path or query continuation and no word of the running text starts it.
    One Opus builder then a probing verifier (the `xfor` case, a legitimate break `https://a.example/long-` then `path`, a grep of `report.json` and `report.md` for the joined host), tests, mutations, gates, push.
11. Freeze and re-record before submission (unchanged): an annotated tag `demo-freeze`, the demo-day runs re-run at that commit (his word, about $25), `docs/REPRODUCIBILITY.md` and the README replay recipe updated; after items 1 to 6, 9 and 10; items 7 and 8 do not block it unless he says so.

## 3. Check these facts first

| Command | Expected on 06 Oct 2026 14:36 | If different |
|---|---|---|
| `git -C ~/Desktop/SIT fetch origin; git -C ~/Desktop/SIT log --oneline -1 origin/claude/happy-darwin-d0bl94` | this file's commit, message starting `Handover of 6 Oct 2026`, directly above c7857de (it was pushed with it) | more above: `git -C ~/Desktop/SIT log --oneline c7857de..origin/claude/happy-darwin-d0bl94` and read the messages |
| `git -C ~/Desktop/SIT rev-parse --short origin/s4/ui-integration` | `c7857de` | moved: his session or item 1 pushed; read the log |
| `git -C ~/Desktop/SIT-wt/ui-integration log --oneline -1; git -C ~/Desktop/SIT-wt/ui-integration status -s` | `c7857de Merge branch 's4/evidence-links' ...`; the 6 modified and 2 untracked files of item 1 | a new commit: item 1 starts; clean at c7857de: his session dropped the edits, ask him |
| `git -C ~/Desktop/SIT-wt/ui-integration-2 status -s; git -C ~/Desktop/SIT-wt/ui-integration-2 log --oneline -1` | empty; `c7857de` | dirty: a worker of a later session left work; `git -C <wt> diff --stat` tells what, and the planner checkpoints or discards it before item 1 |
| `ls ~/Desktop/SIT-wt/ui-integration/runs/` | `ui-261005-125221-0958` (holds only `ui/`: a start that never ran), `ui-261005-125426-adaa`, `ui-261005-170012-2648` | a fourth folder is his second rehearsal (item 9) |
| `pgrep -fl 'dra ui' \| cut -c1-60` | one process (pid 86899 at writing); `lsof -p <pid> \| grep -E 'cwd\|LISTEN'` shows cwd `~/Desktop/SIT-wt/ui-integration` and port 8765 (`ultraseek-http` in lsof) | a server with that cwd or port is his: never killed; a server whose cwd is a worker worktree is killed by a worker, by pid, after that worker reported or is known gone |
| `git -C ~/Desktop/SIT-wt/score-manifest-disagree status -s` | `?? docs/transcripts/session7/score-manifest-disagree.md` | empty: he ran item 2 |
| `git -C ~/Desktop/SIT show "origin/claude/happy-darwin-d0bl94:docs/USER_DECISIONS.md" \| grep -c '^\| [0-9]* \|'` | 50 | more: read the new rows |
| `git -C ~/Desktop/SIT show "origin/claude/happy-darwin-d0bl94:eval/prereg_deviations.md" \| grep -c '^## [0-9]*\.'` | 17 | more: read the new entry |
| `git -C ~/Desktop/SIT ls-tree -r --name-only origin/claude/happy-darwin-d0bl94 docs/transcripts/session7/ \| grep -c '\.md$'` | 8 (9 after item 2) | other: read the commit list |
| `git -C ~/Desktop/SIT show "origin/claude/happy-darwin-d0bl94:eval/blind/ACCESS_LOG.md" \| grep -c '^## Entry'` | 3 | 4 or more: someone touched the held-out items; read the entry |
| `uptime; memory_pressure \| tail -1` | load near 3 (3.77 2.88 2.35 at writing); free memory 47% | second load number over 10 or free memory under 35%: wait, cap workers at two |

In zsh, with a variable such as `B=origin/claude/happy-darwin-d0bl94`, write `"${B}:eval/..."` with braces: `$B:e` is a history modifier and eats the `:e`.

## 4. His decisions (do not re-ask)

All in `docs/USER_DECISIONS.md` rows #17 to #50 (his own, and the planner's rulings under his delegation, each row saying which).
03 Oct 02:50: the planner makes the calls; 22:55 "fix what u need to fix".
03 Oct: judge Anthropic-only (#23); effort medium default (#33); no answer key for the SIT sample (#35); review outputs Download, Email, wifi share link, no hosted link (#36).
04 Oct 22:40: plan D (#46): "just 10 documents is enough", "less runs, but more variants document wise", "all using medium"; the LangGraph arm is separate and unfunded.
05 Oct: demo deadline "longer than 9 mins", set to 900 s (#47); the reserves fix "yes fix it", the demo default stays 900 s (#48).
05 Oct, planner under delegation: a resolved prior is a prior-table row only (#49).
06 Oct: "yes: fix the research defects, before any demo" (#50); the public snapshot refresh "not yet"; the $92 v2 reruns "not yet"; the second rehearsal "im still doing" (all three planner).
06 Oct: "/handover, let it be done by opus" (this file).
Standing planner rulings of 3 to 5 Oct (carried from the 5 Oct handover section 4): the early-end rule is off for calls with tools; a URL counts as ledger-backed only when it is in the document text, a tool result or a ledger `url_or_citation`; the demo start line with share flags is his to type.

## 5. Open with him

1. Item 2: his one-line commit of the worker note (the command is in item 2); it unblocks nothing else but keeps the record whole.
2. The v2 reruns (item 8), about $92: when he says go, which clock; recommendation: `--deadline 540` so they compare with plan D's v1 runs at 540 s (with #48 the reserves scale), and a deviation entry either way.
3. The public snapshot refresh (item 7): his "not yet"; when he says go, a worker resolves the 12 scan findings first (emails and a home path in older handovers, a word in four synthetic designs that needs a deviation entry, a 64-character token in tests).
4. If his rehearsal's searches fail again: the search provider behind SIT's MCP server is not configured on SIT's side ("TAVILY_API_KEY not configured"); options: tell SIT, or demo with fetch only; recommendation: tell SIT before the demo day.
5. `~/Desktop/SIT_arch_study/FACT_CHECK.md` (outside the repo) lists 12 corrections to his interview script against the code (planner): six shards not four; no stage 2, research runs inside stage 1 beside the shards and meets the findings at refine; no backward state transitions; no Codex or OpenAI gateways; the PDF is dropped on the Claude Code backend; and others; he reads it before the interview.
6. His own, carried: sign the answer keys (`eval/KEY_SIGNOFF.md` section 10; recommendation: the eight synthetic ones); invite the two SIT reviewers `SIT-calebying` and `Makienhui-sit` (Settings > Collaborators) after his ADR-005 ruling (repository privacy, row 2 of `docs/SUBMISSION_GAPS.md`: who may see the private repo; history cannot be rewritten after access is granted); the plan letter A ($3,282), B ($1,506) or C ($801) for the Tier A evaluation (`docs/BUDGET_OPTIONS.md`) (recommendation: plan D plus the v2 reruns suffice unless he wants the power analysis); the held-out budget ruling (recommendation: the converter's read of 5 Oct, access log entry 3, does not count; keep both items for the frozen stage).
7. Carried, low priority: the LangGraph arm (about $120); review email on or off (`config/ui.yaml`, off as shipped); a ledger field marking a model-anchor excerpt; a structured report field for a refine fallback so the scorer's warning stops depending on wording; the submission deadline and interview date (nothing in the repo holds them).

## 6. Rules of this work

The planner never reads source, edits, tests, runs the agent or scores; at most three SIT workers at once (two when the load row of section 3 says so; other projects' lanes are not counted); a worker tests only under a 5-minute load of 10 with free memory over 35 percent, and waits with an `until` loop, never a bare `sleep`.
Workers keep recorded model text (`llm.jsonl`, `progress.jsonl`, judge logs, `ui/chat.jsonl`, finding text in `report.json`) out of their context and inspect it by script that prints ids, counts, durations and rule names.
A brief never points a worker at `docs/live_runs/`, `docs/transcripts/` or `llm_calls.json`, and never at tool payloads; the planner inlines the counts.
`docs/transcripts/` is refused by the auto-mode classifier for reading and for committing: a worker may write its note there, but he commits it (item 2 form).
The SIT MCP key is only in his Keychain and his Terminal; every tools-on run is started by him; evaluation runs use `--no-tools`.
No agent run touches `eval/blind/`; `spec/convert_answer_keys.py` runs with `--tier synthetic`; only Malcolm signs answer keys.
Billing: every model call goes through `claude -p` on his Max subscription; `env -u ANTHROPIC_API_KEY` on every run.
`~/Desktop/SIT-wt/ui-integration` belongs to him and his other session; workers never edit, merge or reset there.
At the close the planner updates the SIT memory file `project_sit_design_review_agent_261003.md` in the `memory/` folder of his home-directory project under `~/.claude/projects/` (the folder whose `MEMORY.md` carries the SIT line) and that line, writes the next handover, then runs `/saveconvo SIT --agents` last (the folder `~/Desktop/conversation_history/SIT/` exists, so `SIT` is accepted; `--agents` also saves the workers' transcripts, as on 5 Oct).

## 7. How to verify a change

From a worktree with its venv (`/opt/homebrew/bin/python3.13 -m venv .venv && .venv/bin/pip install -e '.[dev,langgraph]' && .venv/bin/playwright install chromium`), one command per call, exit codes read:
1. `.venv/bin/ruff check agent harness tests` prints `All checks passed!`.
2. `( cd <wt> && .venv/bin/pytest -q --tb=line -p no:warnings 2>&1 | tail -2 )`: 2190 passing at c7857de (planner) plus the change's own tests, no `failed` or `error`; `pytest --collect-only -q | tail -1` gives the exact total.
3. `( cd <wt> && env -u ANTHROPIC_API_KEY .venv/bin/sit-review selftest )` prints `selftest passed`.
4. `( cd <wt> && make smoke )` exits 0.
Steps 2 to 4 and a worker's own `dra ui` replaying a copied run use fake gateways and make no model call, so they need no word from him (they ran as gates every day since 3 Oct); a worker never presses Start in its own `dra ui`.
5. `.venv/bin/python scripts/leakage_grep.py` exits 0 (it gates `agent/`, `prompts/`, `config/`); `.venv/bin/python -m sit_review_agent.prompts --check` reports the lock up to date.
6. A guard: `cp` a backup, remove the claim, see its test fail, restore, `cmp`; a verifier runs a different mutation from the builder's.
7. A UI change: the worker starts its own `dra ui` on port 8800 plus its item number (item 4 uses 8804; 8765 is his live page, 8791 his old rehearsal port) with `--runs-dir` at a `cp -R` copy of `ui-261005-125426-adaa` and `ui-261005-170012-2648` from `~/Desktop/SIT-wt/ui-integration/runs/`, screenshots at 1024, 1280 and 1440 px, kills its own server by pid.
8. Push only as a fast-forward; `git ls-remote origin claude/happy-darwin-d0bl94` equals the local HEAD.
9. Rollback: never force-push; undo a bad push with a new commit restoring the affected files from the last good sha (`git checkout <good sha> -- <paths>`), never by reverting a merge commit.

## 8. Traps already paid for

Seven safeguard stops on 6 Oct 2026, all while a worker read `phases/research.py`, `phases/verify.py` or tool payloads with "reason" and "extracted_text" fields; a gateway-only brief and a docs-only brief went through (planner).
After a stop: checkpoint the worker's disk with a WIP commit, then send a narrower worker (gateway or record level, or mechanical: run tests and gates from tool output only); do not retry the same brief.
`docs/transcripts/` is refused by the classifier for reading and for committing: leave those notes to him (item 2).
Never merge inside the tree a live server reads: a conflicted file breaks his page; merge in a sibling worktree and fast-forward.
`dra ui --runs-dir` disables the Start button, so his live tree keeps his runs in its own `runs/` and is started without that flag.
The cut-time WARN line that said no refine pass ran was wrong (64 of 66 revisions had been salvaged); fixed in `_model_calls.py`; read a WARN against the funnel before acting on it.
A tool result that reports its own failure in its body looked like a success and became citable evidence (EV-001 in FND-044); fixed for new runs by `tools/inband.py`.
`test_the_open_runs_row_stays_in_view_beside_the_logs_panel` was flaky on a null read; fixed with a null-safe wait; a new flake in the UI tests is fixed, never retried away.
Commit ab5035b's message says "decision 49" for the research fix; after renumbering the research fix is #50 and A3 is #49; the file is right, the message is not.
The 5 Oct traps still hold: a stalled verifier loses its review lines (write the result into the note before the final suite); the subscription session limit exits 3 (`sit-review resume <run dir>`); two workers on one results folder corrupt its tables; `gh` and `git fetch` print `credential-manager is not a git command`, harmless.

## 9. Not done, on purpose

Items 7 and 8 wait on his "not yet"; item 9 is his run.
The old tools run keeps its EV-001 citation (item 5): past runs are not rewritten.
The LangGraph arm is unfunded; the two held-out items were not run (deviation 14).
External-evidence counts are not comparable across the step G change (deviation 17).
No hosted share link, no multi-provider dropdown, no prompt or prereg freeze before item 11.
`~/Desktop/SIT-wt/demo6` (880fac8) is stale and no longer his rehearsal tree; it and about 100 other worktrees under `~/Desktop/SIT-wt/` stay; keep `ui-integration`, `ui-integration-2`, `plan-d-runs`, `plan-d-b0`, `plan-d-grade` (their ignored `runs/` hold run folders) and `score-manifest-disagree` until item 2 is done.

## 10. Where everything is

Runtime: `/opt/homebrew/bin/python3.13`, a venv per worktree, Playwright Chromium for UI tests, `claude -p` on his subscription for every model call, the SIT MCP servers only through his key.
There is no board for SIT: a card is an item in this file, recorded by its worker note and its commit.
End-of-session routine: section 6, last line.

| Thing | Path |
|---|---|
| Truth branch | `origin/claude/happy-darwin-d0bl94` of `malcolm1232/SIT` (private), c7857de plus this file |
| Backup of the live tree | `origin/s4/ui-integration` (c7857de) |
| His live page | `~/Desktop/SIT-wt/start_sit_ui.sh`, tree `~/Desktop/SIT-wt/ui-integration`, http://127.0.0.1:8765/ |
| Merge worktree | `~/Desktop/SIT-wt/ui-integration-2` (`s4/ui-integration-2`), with a venv |
| This file's worktree | `~/Desktop/SIT-wt/handover-261006` (`s4/handover-261006`, no venv) |
| His runs | `~/Desktop/SIT-wt/ui-integration/runs/ui-261005-125426-adaa` (document-only, demo profile, 8:48, about $5.71, fit with conditions, 30 findings); `ui-261005-170012-2648` (tools on, 6:24, about $7.30, 28 findings, 0 of 8 research questions answered) (planner) |
| Untracked worker note | `~/Desktop/SIT-wt/score-manifest-disagree` (item 2) |
| Interview fact check | `~/Desktop/SIT_arch_study/FACT_CHECK.md` (outside the repo) |
| Export and review renderer | `agent/sit_review_agent/ui/xref.py`, `ui/static/xnav.js`, `ui/static/review.css`, `export.py` |
| Run log panels and architecture view | `ui/stages.py`, `ui/architecture.py`, `ui/static/architecture.{js,css,json}` |
| Report template | `agent/sit_review_agent/report/templates/report.md.j2` |
| Research gateways | `agent/sit_review_agent/tools/inband.py` |
| Decisions, deviations | `docs/USER_DECISIONS.md` (50 rows), `eval/prereg_deviations.md` (17 entries), `eval/KEY_SIGNOFF.md`, `eval/blind/ACCESS_LOG.md` (3 entries) |
| Study sheet and architecture | `docs/EXPLAIN_AS_IT_RUNS.md`, `docs/ARCHITECTURE.md`, `docs/DEMO_DAY_SCRIPT.md`, `docs/DEMO_DAY_RUNBOOK.md`, `docs/SUBMISSION_GAPS.md` |
| Plan D | `docs/COMPARISON_PLAN_D.md`, `docs/live_runs/plan_d/RUNS.md`; run folders under `~/Desktop/SIT-wt/plan-d-runs/runs/` |
| Memory | `project_sit_design_review_agent_261003.md` in the `memory/` folder of his home-directory project under `~/.claude/projects/` |
| Transcripts | `~/Desktop/conversation_history/SIT/`, day files conversation_verbatim_261005.md and conversation_verbatim_261006.md |
| Older handovers | `docs/HANDOVER_261005_PLANNER_B.md` (superseded; the v2 rerun commands and the measurement checks), `docs/HANDOVER_261005_PLANNER.md`, `docs/HANDOVER_261004_PLANNER.md` |
