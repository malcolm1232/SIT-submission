# Review UI v2: the DBSearch idiom with a sidebar, built (session 4, 2026-10-03)

The deliverable was the review page's v2 look as the approved mockup `docs/design/ui_mockup_v2/` shows it, with the server fields the rail needs, on branch `s4/uibuild2` from `446119a`.
The work is six commits: `b5053f0` (item 1, tokens, font, stylesheet), `bad3870` (item 2, server additions and their tests), `4b42c7f` (item 3, the pages, the composer, three honesty guards), `e3a2ea0` (item 4, the built pictures), `88722cd` (the chips moved to `config/ui.yaml` after the eval isolation guard refused the first routes, pictures reshot) and the closing commit (this report, the edit log `research/audit/ui_v2_editlog.md`, the README line and the two demo documents).
Everything ran offline: no model call, no MCP call, no probe against a server, nothing under `eval/blind/`, nothing under `docs/transcripts/` read, and no recorded model output printed.

## What was built

The page is DBSearch's app grid: a 248 px dark rail, a 56 px topbar and a centred surface (820 px on the Review page, 1120 px on the others).
The rail carries the brand, WORKSPACE (Review, Runs, Replay) and OPERATE (Tools, Settings, Developer) with the paper-on-ink active pill, the slot with the Runs and Tools lists, the note "Every number on this page comes from the run directory. Nothing is estimated." and the Collapse control (key `navrail-collapsed` in localStorage, default expanded).
A running run in the rail shows a green dot, its stage, the run clock and the open calls; the open run's entry is the page's own reduced stream, the other rows come from `GET /runs` and are re-read at the open run's status cadence (one `call_status` record per tick), on navigation and when a stream ends, never on a browser timer, because the honesty tests forbid `setInterval` and `setTimeout` in the page.
A finished run in the rail shows its verdict, confidence and wall time; the Tools list shows the four servers with a warm or off dot and "warm at hh:mm UTC · N tools", "this run: --no-tools" when the open run was document-only, or "off in config/tools.yaml".
The topbar carries "local · your subscription · no API key" (from `/meta.backend`, `claude_code`), "tools: N of 4 servers warm" (a link to the Tools page) and the profile selector (demo · 9:00, default · 60:00), kept in step with the Review form's profile; there is no sign-in.
The Review page is the empty state: the serif heading, the two-line subtitle, the drop zone with the pasted-link field, three sample-document chips (the `documents:` list of `config/ui.yaml`, served by `GET /documents`; a chip fetches the file from this server into the form and never starts a run, which the browser guard checks), the previous version, profile and tools controls (the checkbox and its label on one line), the run id, Start review and the argv line in monospace.
The run view has the document title and the serif run clock at the right, the stage-1 summary ("understand and plan done, 2 of 4 assess shards open"), the tracks with elapsed over the limit, disclosure lines under stage 1 for a document-only research or a cut shard naming its DEG id, the sequential rows, the legend, the argv line, the draft findings under the amber pill and the status feed.
The finished review has the verdict in the serif at 36 px with its confidence, band and condition count, the counts, the rationale, the conditions, "What would change it.", the objectives table with each objective's text from `intent_summary.objectives`, the findings by rank with the severity pill, the strengths, the sound areas, the unresolved issues and the limitations; the three outputs are quiet pills in the head (Download, Email opens the address field under the head, Share link opens the share box); the Delta tab is drawn disabled with the title "No previous version was given for this run" and the note under the tab row when the report carries no re-assessment.
The ask is DBSearch's composer at the foot of the review: "Ask the review" with the "reading aid, not the review" pill, the notice, the answers above the shell, the green "Grounded in this review" pill (grey with the reason when the chat is off), the dark Ask button, the uppercase mono footer "Enter to ask · Shift + Enter for a new line" and "Trimmed to this review · 20 asks or $3.00 per run" (the cap from `/meta.chat`), and the budget line with the calls used, the cost, the model, the log path and "outside the evaluated agent and its manifest".
Runs is the full table with a Started column; Replay explains `dra replay`, lists replayed runs and gives the command per finished run; Tools shows each server's last recorded warm-up with its time, tool count and calls, says what the dot means, and has the Probe now button; Settings shows the effective configuration by file (agent, profiles, stop rules, tools, url policy, ui) and changes nothing; Developer shows the restart command, the run directory, the version and commit, the open run's command and replay line, and the routes the page reads.
The uppercase mono caption appears in the rail's group labels, the slot heads and the composer footer only; nothing animates; the dark theme is deferred as decided.

## Endpoints added

`GET /runs` rows carry `stage`, `run_s` and `open_calls` from the records (`rundata.progress_state`), `started_at`, `profile`, `no_tools`, `model_calls`, `version`, and `argv` from the manifest for a terminal run.
`GET /tools` returns per server `enabled`, `warm`, `at`, `tools`, `status`, `calls_ok`, `calls_failed` from the newest run directory that recorded a warm-up (a `tools_list.jsonl`, or an `mcp_warmup` record with status `done` or `failed`; `none` and `skipped` never stand for the servers), plus `from_run`, `auth_env`, `key_present` and the last `probe`.
`GET /meta` carries `backend`, `model`, `version`, `config_files`, `auth_env`, `bind_host`, `port` and `ui_args`.
`POST /tools/probe` runs the gateway's own warm-up (initialize and tools/list on the enabled servers, the full cold-start allowance) only when the key named by `tools.auth_env` is set in the server's environment, and answers 409 with the reason otherwise, with no server enabled, or without an agent configuration; its lines pass the preflight's redaction.
`GET /documents` and `GET /documents/<name>` serve the chips from `config/ui.yaml`; they were first written as `/synthetic` routes reading `eval/synthetic` from the agent package, which the full suite's eval isolation guard refused, so the list moved to the config file (`config/ui.yaml` is outside the owned files and was edited for that reason).

## Differences from the mockup

The rail's Runs list gives way to the Tools list at a 900 px window (the runs scroll inside their part of the slot), so frame 1 shows two and a half runs where the mockup, 979 px tall, showed four.
Times are the server's UTC stamps with the suffix "UTC" (rail "warm at 04:26 UTC", run head "started 10:09 UTC"), where the mockup wrote a bare local hh:mm; the page holds no browser clock, so it converts nothing.
The chip lead reads "or a sample document from config/ui.yaml:" because the page copy may hold no digit (the mockup's "design_v1" did) and the agent package may not name the eval folder.
The tools help under the checkbox names the source run: "Both answered the last recorded warm-up at 04:26 UTC (run sit_sample_tools_1)."
The profile selector in the topbar is a native select with the mockup's label.
In the running frame the fixture stream has research done rather than skipped, so no disclosure line appears there; the line is drawn for `research_doc_only` and `shard_cut` records that carry a degradation id.
The stage-1 summary is built from the tracks ("understand and plan done, assess done") rather than the mockup's hand-written sentence, and the run head omits the version when the stream has none.
The legend keeps its two honesty sentences and says "cut with the time" where the mockup showed "cut at 4:25".
Under the tab row of a finished review there is one extra line the mockup did not draw: the download's companions ("Open it in a new tab · report.md · report.json") with the one-file note, kept from the built page.
The rail's Tools list in the finished frame reads the global state (the newest run with records, "2 of 4 warm", "warm at 04:26 UTC · 3 tools · 5 calls failed") where the mockup wrote "this run" with "(DEG-002)"; the per-run tool outcome stays in the report's limitations.
The budget line says "0 of 20 calls used" (the existing honesty test pins it) where the mockup said "asks"; the footer says "20 asks" as drawn.
The verdict line adds the confidence band ("confidence 0.72, moderate · 9 conditions") as the built page did.
The share box, drawn open in frame 3, opens from the Share link pill and is closed by default.

## Lines touched in the Delta tab

`app.js` is rewritten, so the other worker's lines 620 to 670 moved: `deltaBody` is now lines 914 to 923 with its text unchanged from the base; the lines I added for the tab are 943 (`NO_DELTA`), 952 (the tab entry with `off` and `title`) and 974 (the note "Delta is off: no previous version was given for this run."); the dispatch at 977 is unchanged.
The styling is `app.css` line 150 (`.tab:disabled`) and `index.html` line 138 (`#tab-note`).
`tests/test_ui_honesty.py` asserts the disabled tab, its title and the note in place of the old "no Delta tab" assertion.

## Mutation results

Four guards were mutated against a `cp` backup, each test failed, and each file was restored (`git diff --stat` empty): a fixed rail entry instead of the stream state, every tools dot warm, a probe posted on every page load, and the probe's key check removed on the server.

## Gates

Exit codes read one per call from the repo root: `ruff check agent harness tests` 0; `pytest -q --tb=no -p no:warnings` 0 (1846 passed, 0 failed, in 230.81 s; a first run had 1 failure, the eval isolation guard on the chips routes, fixed in `88722cd`); `sit-review selftest` 0; `make smoke` 0 (249 passed); `make test` 0 (ruff clean, 1846 passed); `scripts/leakage_grep.py` 0 (PASS: no unresolved hit in a gated area).

## For the verifier

Open the branch at its tip, create the virtualenv as the Makefile says, run `pytest -q tests/test_ui_server.py tests/test_ui_honesty.py tests/test_ui_page.py tests/test_ui_outputs.py tests/test_ui_chat.py` and expect 128 passed with Chromium installed.
Compare `docs/design/ui_mockup_v2/built_1_review.png`, `built_2_run.png` and `built_3_finished.png` with `frame_1_review.png`, `frame_2_run.png` and `frame_3_finished.png` beside them; the differences listed above are the ones I see.
To look at the page by hand, serve any run root with `dra ui --runs-dir <root>` and open `/`, `/?page=runs`, `/?page=replay`, `/?page=tools`, `/?page=settings`, `/?page=developer` and `/?run=<id>`; the scratch root the pictures used is described in the edit log, section 6.
Not verified here: a live review started from the page (no model call was made), the Probe now button against the real servers (no key, no network), a real SMTP send (the fake server only), the rail with a run started in a terminal while another is open in the page (the fixture run stood in for it), the collapse state across a browser restart, and the dark theme, which is deferred.
The honesty guard forbids browser timers, so the rail's other rows refresh at the open run's status cadence and on navigation, not every 2 s as the restyle note proposed; if the owner wants the 2 s poll, the guard `test_the_bar_is_elapsed_over_the_limit_and_nothing_else` must first allow a timer that polls the server without ticking any clock.
