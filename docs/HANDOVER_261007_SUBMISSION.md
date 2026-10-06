# SIT submission and Architectural design page - handover, written 07 Oct 2026 00:40 local by the "archpage-submission" session

START HERE. This file is enough to finish the SIT submission and to keep editing the Architectural design page; the agent's own build history is in `docs/HANDOVER_261006_PLANNER.md`.
To start the next session say: "Read ~/Desktop/SIT-wt/ui-integration/docs/HANDOVER_261007_SUBMISSION.md and continue the SIT submission: run section 3 first, then section 2."
Supersedes: `docs/HANDOVER_261006_ARCHPAGE_IMPORTANT.md` (architecture page work of 06 Oct 2026).

## 1. Goal and where it stands

"He" is Malcolm, GitHub `malcolm1232` (`gh auth status` shows that account logged in on 07 Oct 2026).
Goal: submit the SIT AI Engineering Lab design-review agent, and polish the "Architectural design" page he presents from on the demo day.
The brief states no submission deadline and no demo-day date; ask him if a step depends on them.
Submission, per the brief (`~/Downloads/AI Engineer Lab Exercise.pdf` section 5.2): invite GitHub IDs `SIT-calebying` and `Makienhui-sit` as collaborators on the repo before the deadline; a PUBLIC repo is NOT required.
Done and verified on 06-07 Oct 2026:
- New PRIVATE repo `malcolm1232/SIT-submission` created on his word; its `main` = `f7a5259` = the full history of `s4/ui-integration` (`claude/happy-darwin-d0bl94` was merged into it in merge commit `e5b4599`).
- Same commit pushed as backup to `origin` (`malcolm1232/SIT`) branch `s4/ui-integration`.
- Count-only secret check of the pushed history: the real SIT MCP key appears 0 times; the one `sk-ant-` shaped string is a 29-character fake in `tests/test_tool_gateways.py` (sanitiser test).
  Repeat it before EVERY push to `submission` (after the invites, each push reaches the evaluators); both commands print a count only, never a key:
  `git log -p HEAD | grep -F -c -f <(security find-generic-password -a "$USER" -s SIT_MCP_API_KEY -w)` must print `0`.
  `git log -p HEAD | grep -c -E "sk-ant-[A-Za-z0-9_-]{40,}"` must print `0` (a real key is about 100 characters; the test fake is 29).
- Architecture page: his text edits to the cards, 14 numbered repo links (now pointing at `SIT-submission/main`), own panels for the Logging, Recording and base tool layers, Esc closes any side panel, a line-break bug fixed; 346 UI tests passed.
Not done: the two collaborator invites (waits for his go), README "Status (3 October 2026)" section is stale, demo-day outputs to commit after the session.

## 2. Do this next

Order: run section 3 first, then the items below.
Mechanics: work in `~/Desktop/SIT-wt/ui-integration` on branch `s4/ui-integration`, which is the truth.
Every finished change is committed (only the files you changed, by name), then pushed to BOTH remotes: `git push submission HEAD:main` and `git push origin HEAD:s4/ui-integration`.
`submission` = `https://github.com/malcolm1232/SIT-submission.git`, `origin` = `https://github.com/malcolm1232/SIT.git`; both private.
No deploy exists: the page is served locally by `~/Desktop/SIT-wt/start_sit_ui.sh` on `http://127.0.0.1:8765`.
"Item" below means this list.

1. Rewrite the README's stale status section (no question needed: he was told on 06 Oct 2026 and it only describes the repo; keep every other README section as it is).
   Where: `README.md`, the section `## Status (3 October 2026)`; replace it with `## Status (<the date you write it, e.g. 07 October 2026>)` stating what the repo holds on that date, read from `docs/HANDOVER_261006_PLANNER.md` section 1 and this file section 1 (the agent's 900 s run deadline for the demo profile, the `dra ui` web page, the Architectural design page, assess split into 6 parallel shards, the research tool-failure fix), each claim checked against the code or docs before writing.
   Verify: `grep -n "^## Status" README.md` prints the new date; commit and push to both remotes.
   Done: the section describes the repo as of the date in its heading; history belongs in `docs/`, not there.
2. Ask him "go for the two invites?" and on his yes run:
   `gh api -X PUT repos/malcolm1232/SIT-submission/collaborators/SIT-calebying`
   `gh api -X PUT repos/malcolm1232/SIT-submission/collaborators/Makienhui-sit`
   (A repo owned by a personal account has no read-only collaborator role; the brief only asks for them as collaborators.
   GitHub emails each invitee; the brief asks for nothing else.)
   Verify: `gh api repos/malcolm1232/SIT-submission/invitations -q '.[].invitee.login'` prints both IDs.
   Done: both invitations pending or accepted.
   This is the act of submitting; never before his explicit yes in the session that runs it.
   Wrong ID or second thoughts: `gh api repos/malcolm1232/SIT-submission/invitations -q ".[] | [.id, .invitee.login]"`, then `gh api -X DELETE repos/malcolm1232/SIT-submission/invitations/<id>` (an accepted one: `gh api -X DELETE repos/malcolm1232/SIT-submission/collaborators/<login>`).
3. His open page questions in THIS file's section 5, one at a time, only on his yes.
4. After the demo day: commit the session's run folders (brief section 5.1 asks for the outputs generated during the lab session).
   Each run writes `runs/<run id>/` in this worktree (run ids like `ui-261005-170012-2648`, newest by `ls -t runs | head`); ask him which runs were the demo ones.
   Run the two secret counts on those files (`grep -rF -c -f <(security find-generic-password -a "$USER" -s SIT_MCP_API_KEY -w) runs/<id> | grep -v ":0$"` prints nothing) before `git add -f runs/<id>` (runs/ may be ignored), commit, push to both remotes.

## 3. Check these facts first

| Command (run in `~/Desktop/SIT-wt/ui-integration`) | Expected on 07 Oct 2026 00:40 | If different |
|---|---|---|
| `git branch --show-current; git rev-parse --short HEAD` | `s4/ui-integration`, `f7a5259` | Read the new commits (`git log f7a5259..HEAD --stat`) before editing |
| `gh auth status` | logged in as `malcolm1232` | Stop; ask him to log in (`! gh auth login`) |
| `git status --short` | only `?? ui_screens/` | Someone has uncommitted work; ask him before touching those files |
| `gh api repos/malcolm1232/SIT-submission/commits/main -q '.sha[0:7]'` | `f7a5259` | Local ahead: run the secret counts, then push `HEAD:main`. Remote ahead or diverged: `git fetch submission && git log HEAD..submission/main`, merge it (`git merge --no-edit submission/main`), never force-push |
| `gh api repos/malcolm1232/SIT-submission/collaborators -q '.[].login'` | `malcolm1232` only | If the two IDs are there, item 2 is already done |
| `gh repo view malcolm1232/SIT-submission --json visibility -q .visibility` | `PRIVATE` | Never change it without his word |
| `lsof -ti tcp:8765 -sTCP:LISTEN` | one PID while the page server runs (nothing after a reboot is normal) | Start it: `~/Desktop/SIT-wt/start_sit_ui.sh` (run in background) |

## 4. His decisions (do not re-ask)

- 06 Oct 2026: submit from a brand-new private repo containing the full SIT work, current branch as `main`, no export-and-redact pass ("malcolm1232/SIT. u can push to a completely new repo is fine so u dont have to screen everytig"; confirmed "yes").
- 06 Oct 2026: on-the-spot modification on the demo day is him telling the agent what to change; the runbook table (`docs/DEMO_DAY_RUNBOOK.md` section 4.2) holds the file and line per likely request.
- 06 Oct 2026: page card order: How it was built; Why a custom framework over the popular ones; How security is done; The research loop is deliberately handwritten; Two choke points; Choke point 2: the ToolGateway; The evidence ledger; Top 3 advantages and top 3 disadvantages.
- 06 Oct 2026: "Thinly measured so far" disadvantage removed; concurrency added as advantage (latency) AND as disadvantage (isolation and merge machinery); he pasted ChatGPT notes saying 4 assess shards, the code has 6 (`config/agent.yaml` shards).
- 06 Oct 2026: "How it was built" lead is "The architecture: **one Orchestrator agent spawned multiple sub-agents, one per task**. Agents are:"; every agent numbered and hyperlinked to its repo folder or file.
- 06 Oct 2026: Esc must close every side panel ("make sure it applies to all").
- 06 Oct 2026: Logging, Recording and the base layer get their own panels ("yes, proceed as per rec").

## 5. Open with him

| Question | Options | Recommendation |
|---|---|---|
| Send the two collaborator invites (item 2) | now; or after more polish | Now, after item 1: access must exist before the deadline and later pushes still reach them |
| Evidence ledger card: the "Finding, cites EV-002" box opens the Verify panel and he asked why | relabel subtitle "cites EV-002; Verify checks it"; or point it at another panel | Relabel: Verify is where code checks each cited EV exists in the ledger and drops URLs not in it |
| Verify panel lead says "against" twice ("checks code against every quoted anchor against the canonical text") | keep; or "**checks in code** that every quoted anchor is in __the canonical text__" | Change it, on his yes |
| Small diagram on the concurrency disadvantage (three agents, each its own state copy, into merge) | add; or leave text only | Offered, not asked for; only if he wants it |

## 6. Rules of this work

- Never restart the page server while he is presenting from it.
- Never change repo visibility, never invite anyone, never force-push, without his word in that session.
- Never start a review run from the page or the CLI: runs cost real money (about $6-7 each) and he has not asked.
- Commit only the files you changed, by name; never `git add -A`; `ui_screens/` stays untracked and untouched (it predates this session; owner unrecorded).
- No co-author or agent-name lines in commit messages (his global rule).
- Page rules enforced by `tests/test_ui_architecture.py`: no number literals other than 0 and 1 in `architecture.js` (write `i & 1`, not `i % 2`), no colour literals, no `innerHTML`, no `http(s)://` in JS or CSS.
- Page numbers come from `agent/sit_review_agent/ui/architecture.py` facts as `{placeholders}` (for example `{shard_count}`); an unknown placeholder is a KeyError.
- Every claim on the page must be backed by code or the repo's docs; check before writing.
- Repo links on the page use `https://github.com/malcolm1232/SIT-submission/(tree|blob)/main/<path>`; the evaluators cannot open `malcolm1232/SIT`.
- The server reads `architecture.json` once at start: restart after any JSON or Python edit; JS and CSS are served fresh on reload.
- No em dash anywhere; plain "-".

## 7. How to verify a change

1. `.venv/bin/python -m pytest -q tests/test_ui_architecture.py` prints `21 passed` (or more).
2. For JS changes also `.venv/bin/python -m pytest -q tests/ -k ui` (about 135 s; run it in the background) prints `346 passed, 1 skipped` or more (the skip is expected).
   These tests are offline: fake gateways, a local server, Playwright chromium; no model or MCP calls, no cost.
3. Restart the page: `kill $(lsof -ti tcp:8765 -sTCP:LISTEN)` (stops only the server on that port; `dra` is this repo's CLI, `.venv/bin/dra`, and `dra ui` is its web page), wait until `lsof -ti tcp:8765 -sTCP:LISTEN` prints nothing, then `~/Desktop/SIT-wt/start_sit_ui.sh` in the background; `curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8765/` prints `200`.
4. Screenshot the changed card with Playwright (`.venv/bin/python`, chromium, viewport 1500x1100, `?page=architecture`, click the `.ai-toggle` whose text is the card title, `.ai-card.open` screenshot) and look at it before telling him.
5. For a new link: `gh api "repos/malcolm1232/SIT-submission/contents/<path>?ref=main" --silent` succeeds (anonymous curl returns 404 because the repo is private).

## 8. Traps already paid for

- He saw old text after an edit: the server had not been restarted (JSON is read once at start).
  Restart and confirm with `curl -s http://127.0.0.1:8765/architecture | grep -c "<new words>"`.
- A restart failed with "address already in use": the old server was still dying.
  Wait on `lsof -ti tcp:8765 -sTCP:LISTEN`, not on `lsof -ti :8765` (that also lists browser client connections, for example PID 1556).
- Esc did nothing after a click elsewhere: handlers were on the panel only.
  Now document-level, each skipping a key event another handler already took (`e.defaultPrevented`).
- A sentence with a hyphen ("--record") rendered unbreakable and cut off: `archNoBreak` wrapped whole text pieces; now only its regex matches (odd split indices).
- A test clicked a layer box inside a closed card and timed out: open the card first, then `.ai-card.open .ai-layers .arch-box`.
- `git rev-parse --short A B` with two refs fails ("Needed a single revision"); one ref per call.

## 9. Not done, on purpose

- `malcolm1232/SIT-public` (old export, PRIVATE, last pushed 3 Oct 2026) is not updated and not used for submission.
- `scripts/export_public_snapshot.py` was not run: he ruled the full repo goes in as is.
- `origin/claude/great-hopper-hbx7h0` was not merged: its 2 commits are a 2 Oct 2026 `docs/HANDOVER_FABLE.md` superseded by the copy on `main`.
- `docs/HANDOVER_261006_ARCHPAGE_IMPORTANT.md` still names the old card list and old link base; it is history, superseded by this file.
- `build_agents_first_session` in `agent/sit_review_agent/ui/architecture.py` is now unused by the page (he removed the "36 agents" bullet); kept in case he restores it.
- From the older handover, still not on the page by choice: "3 agents competed", "agents debated the metrics", the Australia "went rogue" case (no SIT record backs them).

## 10. Where everything is

| Thing | Path |
|---|---|
| Live worktree and branch | `~/Desktop/SIT-wt/ui-integration`, `s4/ui-integration` |
| Submission repo | `https://github.com/malcolm1232/SIT-submission` (remote `submission`, branch `main`) |
| Private working repo | `https://github.com/malcolm1232/SIT` (remote `origin`) |
| Page server launcher (reads the MCP key from the macOS Keychain, never prints it) | `~/Desktop/SIT-wt/start_sit_ui.sh` |
| Page text and links | `agent/sit_review_agent/ui/static/architecture.json` |
| Page script and styles | `agent/sit_review_agent/ui/static/architecture.js`, `architecture.css` |
| Run log page script (stage panel Esc) | `agent/sit_review_agent/ui/static/app.js`, `xnav.js` |
| Page tests | `tests/test_ui_architecture.py`, `tests/test_ui_stages.py` |
| The brief | `~/Downloads/AI Engineer Lab Exercise.pdf` (sections 5.1, 5.2, 5.4) |
| Demo-day runbook (live modifications) | `docs/DEMO_DAY_RUNBOOK.md` section 4 |
| Agent build handover | `docs/HANDOVER_261006_PLANNER.md` |
| Memory | `~/.claude/projects/-Users-malco/memory/project_sit_design_review_agent_261003.md` (last paragraph) |
| Transcripts | `/saveconvo SIT` into `~/Desktop/conversation_history/SIT/` (folder exists, checked 07 Oct 2026) |
| Python | `~/Desktop/SIT-wt/ui-integration/.venv/bin/python` (pytest, Playwright chromium) |
| Board | none for SIT |

End of session: commit and push to both remotes, update this file or write the next one, then `/saveconvo SIT`.
