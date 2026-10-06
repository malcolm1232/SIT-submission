SUPERSEDED by docs/HANDOVER_261006_ARCHPAGE_IMPORTANT.md on 06 Oct 2026.

# SIT Architectural design page text - handover, written 06 Oct 2026 13:30 local by the "meetbot-e5" session

START HERE. This file is self-contained for the architecture page work of 06 Oct 2026.
To start the next session say: "Read ~/Desktop/SIT-wt/ui-integration/docs/HANDOVER_261006_ARCHPAGE_TEXT.md and finish its section 2."
Supersedes: None.

## 1. Goal and where it stands

Goal: Malcolm marked up the Simple tabs of the Architectural design page (screenshots with bold, underline and strike-through) and asked for the page to match, plus a few diagram and naming changes.
All asked changes are DONE, tested and checked in screenshots, but NOT COMMITTED.
The page server runs on `http://127.0.0.1:8765/` with the display name "Design Review Agent" for his screenshots.

| Step | What | State |
|---|---|---|
| 1 | Panel text: Understand, Plan, Assess, Research, Reason, Act, Observe, State, Evidence | done, uncommitted |
| 2 | Markup in panel text: `**bold**`, `__underline__`, `{"text","sub"}` sub-points, `flow` box, `table`, `[words](tip:key)` hover tip, `[words](run:stage)` run link | done, uncommitted |
| 3 | Diagram: Observe to Reason loop arrow, Assess two-way arrow to "Isolated copy of the run state", arrows from Research and Assess into Merge, shard boxes are plain labels | done, uncommitted |
| 4 | Display name setting `SIT_DISPLAY_NAME` (`agent/sit_review_agent/ui/naming.py`), default "SIT" | done, uncommitted |
| 5 | Commit | NOT done: he has not asked yet |

## 2. Do this next

"Item" means this list.
Branch `s4/ui-integration` in the worktree `~/Desktop/SIT-wt/ui-integration` is the truth; no push or deploy is part of this work.

1. Ask him whether to commit.
   Do not commit before he says so (his rule: commit only when asked).
   If yes: run the tests in section 7, then `git add` exactly the files in section 10 row "Changed files" (not `ui_screens/`, which was untracked before this work), and commit with a plain message and no co-author line naming the agent.
2. If he wants the page back to "SIT": stop the server (`kill $(lsof -tiTCP:8765 -sTCP:LISTEN)`) and start it plainly: `cd ~/Desktop/SIT-wt/ui-integration && nohup .venv/bin/dra ui > /tmp/dra_ui.log 2>&1 &`.
3. Optional, only if he asks: the run pages, the export and the mail still say "SIT" (`ui/stages.py` "asking the SIT MCP servers", `ui/static/index.html` templates, `ui/export.py`, `ui/mail.py`, the terminal line in `ui/server.py`); the name setting does not cover them yet.

## 3. Check these facts first

- `git -C ~/Desktop/SIT-wt/ui-integration log -1 --format='%h %s'` printed `c7857de Merge branch 's4/evidence-links' into s4/ui-integration-2` at 13:25.
  Another session commits on this branch; read its new commits before committing.
- `git -C ~/Desktop/SIT-wt/ui-integration status --short` printed six modified UI files, `?? agent/sit_review_agent/ui/naming.py` and `?? ui_screens/`.
- `curl -s localhost:8765/meta | python3 -c "import json,sys;print(json.load(sys.stdin)['names']['brand'])"` printed `Design Review Agent`.

## 4. His decisions (do not re-ask)

- 06 Oct 2026: the page text is exactly his marked-up screenshots; struck text removed; bold and underline kept; wavy spell-check lines are not underlines.
- "AD-(n)" and "EV-(n)" as written by him, not AD-nnn.
- Plan jobs: all "**Job N**: lower case text." with colons (he said "u decide").
- Research: "It runs **after understand and plan**", never "after stage 1" (research is inside stage 1).
- Shard boxes: plain labels, no per-shard panels ("dont need to build, leave them as plain labels").
- Assess arrow: two-way to its isolated state copy; NO arrow between Assess and Research (they never exchange anything in the code).
- Understand keeps "The registry is then frozen and hashed." without the old ending.
- Display name for screenshots: "Design Review Agent", via one setting, default "SIT".
- Evidence: a table (Entry, What it is, Added by), and the last point replaced by the link "See Advanced: Merge: the shards' findings in one list" to the run log's Merge stage.

## 5. Open with him

- Commit the work?
  Recommendation: yes, one commit, after section 7 passes.
- Extend the display name to the run pages, export and mail?
  Recommendation: only if his screenshots need them.

## 6. Rules of this work

- Never an em dash in page text or docs; plain "-".
- The page script keeps the page rules tested in `tests/test_ui_architecture.py`: no number literals other than 0 and 1, no colour literals, no `innerHTML`.
- Every number on the page comes from `architecture.py` facts (config or code), never typed into the JSON.
- The server reads `architecture.json` once at start: restart it after any text edit.

## 7. How to verify a change

1. `cd ~/Desktop/SIT-wt/ui-integration && .venv/bin/python -m pytest -q tests/test_ui_architecture.py tests/test_ui_server.py tests/test_ui_outputs.py tests/test_ui_page.py` printed `118 passed` on 06 Oct 2026.
2. Restart the server (section 2 item 2, with `SIT_DISPLAY_NAME="Design Review Agent"` before the command if he wants that name).
3. Screenshot the panel with Playwright (`.venv/bin/python`, `chromium`, `http://127.0.0.1:8765/?page=architecture&topic=<key>`) and compare with his marked-up image.

## 8. Traps already paid for

- Killing the server by name failed once and a second server could not bind; kill by port: `kill $(lsof -tiTCP:8765 -sTCP:LISTEN)`.
- A tip box inside the scrolling panel was clipped; it is `position: fixed`, placed by `archPlaceTip`.
- `archRunLink` already existed (the "Open this stage in the run log" link); the new link is `archSeeLink`, which reuses it.
- A trailing "→" wrapped alone onto a line; it is joined with a no-break space.

## 9. Not done, on purpose

- No commit: he has not asked.
- The CallCopilot architecture page was handed over separately (`~/Desktop/CallCopilot/HANDOVER_261006_ARCHPAGE.md`); it is not part of this file.
- No cold-read test of this file: he asked to save tokens.

## 10. Where everything is

| Thing | Path |
|---|---|
| Worktree, branch `s4/ui-integration` | `~/Desktop/SIT-wt/ui-integration` |
| Changed files | `agent/sit_review_agent/ui/architecture.py`, `ui/server.py`, `ui/naming.py` (new), `ui/static/app.js`, `ui/static/architecture.css`, `ui/static/architecture.js`, `ui/static/architecture.json` |
| Page tests | `tests/test_ui_architecture.py` |
| Runtime | `.venv/bin/python` (Python 3.13), `.venv/bin/dra ui` on port 8765 |
| Transcript | `~/Desktop/conversation_history/` via `/saveconvo` (folder given by him) |
