SUPERSEDED by docs/HANDOVER_261007_SUBMISSION.md on 07 Oct 2026

# SIT Architectural design page (panel text and Important points) - handover, written 06 Oct 2026 17:37 local by the "archpage-important" session

START HERE. This file is self-contained for the Architectural design page work of 06 Oct 2026.
To start the next session say: "Read ~/Desktop/SIT-wt/ui-integration/docs/HANDOVER_261006_ARCHPAGE_IMPORTANT.md, run its section 3, then continue the SIT architecture page from its section 2."
Supersedes: `~/Desktop/SIT-wt/ui-integration/docs/HANDOVER_261006_ARCHPAGE_TEXT.md`.

## 1. Goal and where it stands

Goal: Malcolm marks up screenshots of the Architectural design page (bold, underline, strike-through) and the page must match them exactly; he also asked for an "Important points" section that explains the design to an evaluator.
Everything asked so far is DONE, tested, checked in screenshots, COMMITTED and PUSHED to the private repo `malcolm1232/SIT`, branch `s4/ui-integration`, tip `5222875`.
The page runs on `http://127.0.0.1:8765/?page=architecture` with the display name "Design Review Agent".
Nothing is in flight; the next work is whatever he marks up or asks next.

| Step | What | Commit |
|---|---|---|
| 1 | Simple-tab text of Merge, Refine, Verify, Report, Output as his markup; EV-nnn and FND-nnn shown as EV-(n), FND-(n) | `0023861`, `9ec135b`, `478d251`, `cb61dc7` |
| 2 | Hover tip on "Code runs 10 invariant checks" listing the checks (from `ui/stages.py` `INVARIANTS`); a "?" mark on every tip | `9ec135b` |
| 3 | Important points under the diagram: 8 cards as an accordion with Previous and Next | `cb61dc7`, `ce5e733`, `d244608`, `5222875` |

The 8 cards, in order: How it was built; Why not LangGraph; Two choke points; Choke point 2: the ToolGateway; How security is done: what stops it going rogue; The research loop is deliberately handwritten; The evidence ledger; Top 3 advantages and top 3 disadvantages.

## 2. Do this next

"Item" means this list.
The truth is branch `s4/ui-integration` in the worktree `~/Desktop/SIT-wt/ui-integration`.
Shipping here means: commit, then `git push origin s4/ui-integration`. He said on 06 Oct 2026 "yes push all the work" and confirmed the repo is private ("we are not touching public for now"): push only to `origin` (`https://github.com/malcolm1232/SIT.git`, PRIVATE), never to any public mirror or snapshot.
There is no deploy.
Commit messages are plain, with NO co-author line naming the agent (his global rule).

1. Run section 3, then wait for his next markup or request; there is no backlog beyond section 5.
   He pastes screenshots into the chat.
   Struck words are removed; a straight line under words is his underline; a blue wavy line is spell-check and is ignored.
   Panel keys for `?topic=<key>`: user, cli, ingest, orchestrator, state-machine, understand, plan, assess, research, research-reason, research-act, research-observe, merge, refine, verify, report, outputs, llm-gateway, tool-gateway, policy, state, evidence, checkpoints, budgets, faults, evaluation, philosophy.
   Text may instead sit in `tips` (hover boxes) or `important` (the 8 cards, same markup, titles included); search the whole file and edit the occurrence his screenshot shows.
   For a markup screenshot: find the panel's `simple` block in `agent/sit_review_agent/ui/static/architecture.json` (search the old text), apply bold as `**x**`, underline as `__x__`, delete struck text, keep everything else word for word.
   Verify with section 7, then commit and push.
2. Ask once about the Verify lead (section 5, first row): it is `topics.verify.simple.lead` in `architecture.json`, on the page now as his verbatim markup; change it only if he says so.
3. If he names the Australian case he meant (section 5), check it from a source before adding any line about it.

## 3. Check these facts first

- `git -C ~/Desktop/SIT-wt/ui-integration log -1 --format='%h %s'` printed `5222875 Architecture page: security card ...` at 17:37.
  Another session also commits on this branch; if the tip differs, read the new commits (`git log 5222875..HEAD`) before editing the same files.
- `git -C ~/Desktop/SIT-wt/ui-integration status --short` printed only `?? ui_screens/` (untracked before this work; do not commit it).
- `git -C ~/Desktop/SIT-wt/ui-integration status -sb | head -1` printed `## s4/ui-integration...origin/s4/ui-integration` (nothing unpushed).
- `lsof -tiTCP:8765 -sTCP:LISTEN` printed one pid (the page server, started by `start_sit_ui.sh` at 17:45).
  If empty, start it as in section 7 step 2.

## 4. His decisions (do not re-ask)

- 06 Oct 2026: page text is exactly his marked-up screenshots; struck text removed; wavy spell-check lines are not underlines.
- 06 Oct 2026: "i want: EV-(n)": the page says EV-(n) and FND-(n), never EV-nnn; code comments in back-end Python were left as they are.
- 06 Oct 2026: the hover explanation is shown with a "?" mark ("#explain with "?" onhover").
- 06 Oct 2026: the decision-matrix link opens in a new tab: `https://github.com/malcolm1232/SIT/tree/claude/eloquent-sagan-ah5ttk/research/frameworks#weighted-decision-matrix`.
- 06 Oct 2026: Important points are a dropdown accordion: click opens, Next opens the next card and the previous one closes.
- 06 Oct 2026: "How it was built" goes first, above "Why not LangGraph".
- 06 Oct 2026: push all work, private repo only.
- Earlier rulings still standing (from the superseded handover): AD-(n) and EV-(n) notation; Plan jobs "**Job N**: lower case text."; research runs "after understand and plan"; shard boxes are plain labels; no arrow between Assess and Research; display name "Design Review Agent" via `SIT_DISPLAY_NAME`, default "SIT".

## 5. Open with him

| Question | Options | Recommendation |
|---|---|---|
| Verify lead reads "checks code against every quoted anchor against the canonical text" (his markup, verbatim) | keep; or "the **platform**, __not the model__, __checks__ every quoted anchor __against the canonical text.__" | Change it: it says "against" twice and Verify checks quotes, not code. Only on his yes. |
| "3 agents competed against each other", "agents debated the metrics", "each agent spawned subagents" | add if he points to a SIT record; else leave out | Leave out: no SIT transcript shows them; the three-way contest in memory was Call Copilot (5 Oct 2026). |
| The "Australia, went rogue for a government database" comparison | add a line once he names the case; or leave out | Leave out until named and checked; if he means Robodebt, it was an automated debt system, not an AI agent. |
| "architecturally optimal" wording (already told to him; not live unless he raises it) | kept as "not picked by habit" | Keep: LangGraph scored 80 against 92, so "optimal" invites a challenge. |

The agent (not he) reworded his "Why not LangGraph" claim: the page does NOT say "LangGraph does not support these functions" (the repo's own research scores LangGraph second and credits its replay); it gives the research's reasons.
He has not objected.

## 6. Rules of this work

- `git remote -v` shows one remote, `origin` = `https://github.com/malcolm1232/SIT.git` (PRIVATE).
  There is no public mirror in this worktree; a public snapshot of SIT is a separate future step he has answered "not yet".
- If a push is rejected because another session pushed: `git pull --no-rebase --no-edit origin s4/ui-integration`, rerun section 7 step 1, then push; never force-push.
- Rollback of a pushed page change: `git revert --no-edit <sha>` of that non-merge commit, tested and pushed; never a reset of the shared branch.
- The four test files are offline (fake gateways, a local server, Playwright chromium) and make no model or MCP calls.
  Never start a review run from the page or the CLI for this work: runs cost real money and he has not asked.
- Another session has committed on this branch (the merges up to `c7857de`); who it is is not recorded.
  Before editing, read any commit after `5222875` that touches `ui/architecture.py` or `ui/static/architecture*`.

- No em dash in page text or docs; plain "-".
- `tests/test_ui_architecture.py` enforces page rules on `architecture.js` and `architecture.css`: no number literals other than 0 and 1 in the script, no colour literals, no `innerHTML`, no `http(s)://` in JS or CSS, transitions only on background-color and border-color.
- Every number on the page comes from `agent/sit_review_agent/ui/architecture.py` facts as a `{placeholder}`, never typed into the JSON (framework scores from `research/frameworks/README.md`, agent count from `docs/transcripts/README.md`, budgets from config).
  An unknown placeholder is a KeyError.
- Every claim on the page must be backed by the code or the repo's docs; check before writing (`docs/LIMITATIONS.md`, `docs/ARCHITECTURE.md`, `research/frameworks/README.md`).
- The server reads `architecture.json` once at start: restart it after any JSON or Python edit; JS and CSS are served fresh.
- Commit only the files you changed, by name (never `git add -A`).

## 7. How to verify a change

1. `cd ~/Desktop/SIT-wt/ui-integration && .venv/bin/python -m pytest -q tests/test_ui_architecture.py tests/test_ui_server.py tests/test_ui_outputs.py tests/test_ui_page.py` printed `120 passed` at 17:30 on 06 Oct 2026.
2. Restart always through the Keychain launcher, which exports `SIT_MCP_API_KEY` without printing it (plain `dra ui` drops the key and tools runs are refused): `kill $(lsof -tiTCP:8765 -sTCP:LISTEN); SIT_DISPLAY_NAME="Design Review Agent" nohup ~/Desktop/SIT-wt/start_sit_ui.sh > /tmp/dra_ui.log 2>&1 &`.
   It must print `SIT review UI on http://127.0.0.1:8765/` in `/tmp/dra_ui.log`, and `curl -s localhost:8765/meta` must show the brand "Design Review Agent".
   Only his page server listens on 8765; it is safe to restart.
3. Screenshot with Playwright, saving PNGs in the session scratchpad, never inside the worktree (`.venv/bin/python`, chromium, viewport 1400x1000): a panel at `http://127.0.0.1:8765/?page=architecture&topic=<key>`; an Important card by clicking `.ai-toggle` nth(n) then screenshotting `.ai-card` nth(n).
   Compare with his image.

## 8. Traps already paid for

- Restarting with plain `.venv/bin/dra ui` (done several times on 06 Oct 2026) left the page without the MCP key; use `start_sit_ui.sh` (section 7 step 2).

- In zsh, `F="a b"; git add $F` passes ONE path and fails; list the paths literally.
- An element screenshot of a long section shows the sticky top bar over it; that is the capture, not the page.
- Clicking an open accordion title closes it; a script that clicks the same card twice sees nothing.
- A long "Next: (card title)" ran past the card edge; the nav buttons are one line with an ellipsis and a full-title tooltip.
- `archTip` labels now go through `archInline`, so tip labels may carry `**` and `__`.

## 9. Not done, on purpose

- The four claims in section 5 are not on the page.
- The app is about 1024 px wide at phone width; accepted for this local desktop tool, outside this work.
- The run pages, export and mail still say "SIT"; the display-name setting does not cover them (he has not asked).
- `ui_screens/` stays untracked.

## 10. Where everything is

| Thing | Path |
|---|---|
| Worktree, branch `s4/ui-integration` | `~/Desktop/SIT-wt/ui-integration` |
| Page words, tips, Important points | `agent/sit_review_agent/ui/static/architecture.json` (`tips`, `important`, `topics`) |
| Page script and styles | `agent/sit_review_agent/ui/static/architecture.js` (`archImportant`, `archImpOpen`, `archInline`), `architecture.css` |
| Facts filled into the words | `agent/sit_review_agent/ui/architecture.py` (`facts`, `framework_scores`, `build_record`) |
| Page tests | `tests/test_ui_architecture.py` |
| Runtime | `.venv/bin/python` (Python 3.13), `.venv/bin/dra ui` on port 8765, log `/tmp/dra_ui.log` |
| Superseded handover | `docs/HANDOVER_261006_ARCHPAGE_TEXT.md` |
| Transcript | `/saveconvo sit` (case-insensitive alias) into `~/Desktop/conversation_history/SIT/` |
