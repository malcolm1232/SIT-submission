# A local UI for the review agent: design note and one recommendation

Date: 2026-10-03.
Status: recommendation only; no product code was written.
Picture: `docs/design/ui_mockup/for_him_ui_composite.png` (three frames, 1440 px wide), built from `docs/design/ui_mockup/index.html` with real content from `docs/live_runs/rehearsal_concurrent_1/report.md`; `shoot.py` regenerates it.
Design reference: `QuantifyMe/design_mockups/RECOMMENDATION.md` section 1 and `research/research_anti_slop_craft.md` (cited below as "craft x.y").

## 1. What the UI is for

The lab judges the review (`report.md`, `report.json`, the evidence register), not a chat.
The UI therefore has three jobs: start a run without typing the command, show which stage the run is in while it streams, and let a reader navigate the finished review with its evidence.
The chat is a reading aid over the finished review and is kept visibly apart from it.
The CLI stays the product of record: the UI launches the same code path, writes the same run directory, and a run started in the UI replays with `dra replay`.

## 2. Three shapes

A. A single page in the repo, served on 127.0.0.1 by Starlette from the same Python package, with server-sent events from the progress stream.
Trade-offs: the most room to apply the craft rules (tokens, a 12 px floor, tabular numbers, hairlines, one ink primary; craft 8); page anchors can open the PDF page; the replay fallback drives the same page; needs a thin server and a page in the repo.

B. A terminal UI (Textual) with the same stages and no browser.
Trade-offs: cheapest and honest by nature, but the report cannot be read as a professional document, anchors cannot open the PDF page, a projector font at 18 pt leaves no room for parallel tracks beside a findings feed, and the chat lands in the same terminal as the run, which blurs the two.

C. A chat-first page where the run is a message thread.
Trade-offs: the stage view becomes scrolling chatter, the review ends up inside message bubbles, re-assessment deltas do not fit a thread, and it reads as a generic AI chatbot, the exact impression the lab's "professional design review" criterion (grading D10) punishes.
It also invites "ask the agent to run it again" paths that bypass the recorded run.

Weighed on the craft rules, the demo-day flow (runbook section 5), reproducibility and, last, build cost: A, with the chat as a side panel and never as the front.

## 3. Recommendation

Build A: `dra ui` starts a Starlette server on 127.0.0.1, serves one static page, launches runs as `dra review` subprocesses, streams their progress as SSE, renders `report.json`, and answers chat questions from the run directory only.
No cloud, no new backend service, no build step: one HTML file, one stylesheet of tokens, one script, all under `agent/sit_review_agent/ui/`.
Light theme first, authored on the Radix gray ramp (craft 3.1, 7.6); dark is authored separately later, never inverted (craft 3.3).

## 4. Page structure (what the picture shows)

Top bar: same background as the page with a 1 px hairline, the run and document, tabs as compact pills, the run's outcome, wall time, cost and commit, and one ghost action (craft 1.2 item 1, 8.2, 5.4).

Frame 1, the drop screen: one dashed drop zone with one line saying what it is, one line saying what to do and one button (craft 4.5); label-above fields for the optional previous version, the profile and the tools, with helper text under each (craft 5.1); "Start review" is the only filled control and stays disabled until a document is ingested; the equivalent command line is shown beside it; a recent-runs table with tabular, right-aligned numbers (craft 4.1).

Frame 2, the run: stage 1 as one row per concurrent track (ingest, understand, plan, research, assess 1 to 4), each with the call ID, a status pill, elapsed time against the stage limit on the run clock, and the latest status line.
The bar is elapsed over limit and nothing else, with a legend saying it is not an estimate of completion; there is no fake progress bar (craft 1.3 "honest state", 8.10).
Then merge, refine, verify, verdict and report as rows that say when each must end.
A cut track shows a red "cut at 04:25" pill and what it kept; a skipped research shows "skipped" and the degradation ID (DEG-002 in the rehearsal), exactly as the report will say it.
The right column is the draft-findings feed, headed by an amber "draft, unverified" pill and a sentence that IDs, ranks and severities can change, then the status feed as a structured list of time, phase and message, which is the same line the terminal prints (craft 4.4, not a raw log).
Motion: none beyond a 150 ms background change on hover; a new line appears without a fade (craft 1.3 interaction, 2.6 motion).

Frame 3, the review: verdict label at 24 px with its confidence and band, a counts strip, the rationale, the objectives table, then findings ordered by rank with an ID column, a severity pill, the title, the disposition and the confidence.
Severity is the only colour on the page: step-3 background with step-11 text for high and medium, grey for low, green for strengths, and the one saturated fill for critical (craft 4.3, 8.5).
An expanded finding shows provenance (shard, call IDs, anchors verified, a `dra explain` link), the statement, each anchor as a page link that opens the PDF at that page with the verbatim quote and match detail, each evidence item with its ledger ID and source type, the recommendation as a key-value list, and the affected decisions with their relation.
Unresolved issues with owners and the evidence limitations close the page; Coverage, Evidence register and Run log are tabs.
Type: one sans and one mono, 12 px floor, 13 to 14 px default, weights 400, 500 and 600, tabular numerals (craft 6.4, 7.1, 8.4); no nested borders, one surface level plus hairlines (craft 8.6); one Lucide-style outline icon set and no emoji (craft 8.8).

## 5. The event contract

Today the orchestrator and phases emit `ProgressEvent(phase, message, kind, elapsed_s)` through `ProgressSink.emit` (`progress.py`), with `kind` in step, wait, warn, done, draft, printed as `[mm:ss] phase | marker message` and mirrored to `progress.log`.
The lines the code emits now, by source: `run <id>: <dir>` and `report: <path>` (orchestrator); `<phase> started` and `<phase> done in Ns` for every phase, with the refine line also saying "stage 1 closed, merged in"; the milestones `intent`, `plan`, `merged` and `verified` as done lines (`MILESTONES`); `stop rule <code> fired; skipping to <phase>`, `stage 1 limit passed by N s; stopping`, `N shard(s) ended in`, `interrupted; state flushed`, and `error (<Type>, exit N)` as warnings; ingest's page and section counts; plan's question count and one line per question; `assessing N criteria in K concurrent shard(s)`, `assess shard i/K (<name>): <criteria>`, `assess shard i/K (<name>): N draft finding(s) (...), unverified` and the shard-failed warning; research's iteration, tool-round, declined, stop and document-only lines; the `_model_calls` warnings (cut by the run deadline, truncated at the output cap, model declined, schema repair); report's `verdict <label>; N findings`; the gateway's status line `N open calls: <call> <phase>: thinking ~T tokens | N items streamed (C chars)` at least every 10 s (`CallTracker`); and one `draft <item> N (unverified; <call> <phase>): [severity] title` line per streamed item (`draft_line`).

What must be added, all additive and all keeping the console line unchanged:
1. A structured `fields` dict on `ProgressEvent`, filled at the emit sites that carry data: call_id, phase, shard index and name, item index, severity, kind and title of a draft, thinking tokens, items, chars, milestone counts, the stop-rule code, the cut call ID and what it kept.
The page must not parse message text.
2. Three events the code does not emit: `call opened` and `call closed` per model call (the tracker opens and closes calls but only prints the summary line), and `run finished` with outcome, exit code and the report path.
3. A per-run `progress.jsonl` beside `progress.log`, one event per line; the server tails it for SSE, a page opened late or reconnected replays it from the start, and `dra replay` can drive the same page from its recorded timeline.
4. A `run started` event carrying the profile's stage limits, the deadline and the document metadata, so the page needs nothing from `effective_config.json` to draw the limits.

## 6. The chat: grounding rule and guardrails

Grounding: the chat's corpus is the run directory only: `report.json` (findings, verdict, unresolved, limitations, sound areas), `ledger.json`, `anchors.json` and the coverage map, which is what `dra explain` and `dra coverage` read.
It never receives the PDF, the prompts or `llm.jsonl`, so it cannot form a new finding from the document.
Every answer is structured: `{answer, citations: [FND-, EV-, AD-, DEG-, coverage:<criterion>], supported: bool}`; the server resolves every citation against the run directory, drops one that does not resolve and marks the answer, and an answer with `supported: false` is rendered as "the review does not support an answer" with whatever the review does say (the MSK example in frame 3).
The chat has no tools, no write access, no way to start a run; a question that asks for a re-run gets a reply naming the command the person would run.
It is visibly distinct: its own column on a step-2 background, a "reading aid, not the review" pill, the assistant named "Review assistant", and the review column never shows chat text.
Logging and cost: each call is appended to `runs/<id>/ui/chat.jsonl` (question, prompt hash, model, usage, cost, citations, resolved or dropped) through its own small client, never through the agent's `LLMGateway`, so nothing reaches `llm.jsonl` or the manifest; a cap in `config/ui.yaml` (20 calls and 0.50 USD per review by default) stops the chat with a visible notice; the footer always shows calls used and the log path.
The chat is not part of the evaluated agent: the report, the manifest and `dra replay` are unchanged whether or not it was used, and the `ui/` subdirectory is excluded from `outputs/lab_session/`.

## 7. The delta view

A run with a previous version (`--v1` or `--previous`) gives every finding a `reassessment.status`: resolved, partially_addressed, still_open or new_in_update, and `report.md` already has a "Changes since the previous version" section.
The Delta tab groups by those four statuses in that order, each finding with its prior ID and the reassessment note, and the verdict line shows the previous verdict beside the new one.
The headings read "fixed (resolved)", "partially addressed", "unchanged (still open)" and "new in update, including regressions", because the schema has no separate regressed status and `models.py` changes only with `spec/finding.schema.json`.
Without a previous version the tab is shown disabled and says so, as in frame 3.

## 8. Reproducible and off the evaluation path

The server launches `dra review <pdf> --profile <p> [--previous <dir>] --run-id <id>` as a subprocess with the same environment as the terminal; it never calls `run_review` in-process, so a server crash does not end the run and the run is indistinguishable from a CLI run in its manifest.
The command line is the first line of the run log, so what the page did can be typed back.
The page reads only `progress.jsonl`, `report.json`, `ledger.json`, `anchors.json`, `coverage` output and the PDF; it writes only under `runs/<id>/ui/`.
A run started in the UI replays with `dra replay runs/<id>` because nothing in the run directory differs; the replay's `progress.jsonl` drives the same page, stamped "replayed evidence" in the top bar.
Stop in the UI sends the subprocess SIGINT, which is the CLI's Ctrl-C path (exit 130, state flushed, `dra resume` continues).

## 9. Build plan: three workstreams with disjoint files

W1, events: `agent/sit_review_agent/progress.py` (fields on `ProgressEvent`, `progress.jsonl` writer, `call opened` and `call closed`), the emit sites in `orchestrator.py`, `phases/assess.py`, `llm/claude_code.py`; tests `tests/test_progress_events.py` (every emit site yields the documented fields; the console line is byte-identical to today's).
W2, server and page: `agent/sit_review_agent/ui/server.py` (Starlette routes: `POST /runs`, `GET /runs/<id>/events` SSE, `GET /runs/<id>/report`, `GET /runs/<id>/doc.pdf`, `POST /runs/<id>/stop`), `ui/static/index.html`, `app.js`, `tokens.css`, the `dra ui` command in `cli.py`; tests `tests/test_ui_server.py` on the selftest fixture run (Starlette TestClient, a fake subprocess, an SSE replay of a recorded `progress.jsonl`).
W3, chat: `agent/sit_review_agent/ui/chat.py` (corpus bundle, answer schema, citation resolver, cap, `chat.jsonl`), `config/ui.yaml`; tests `tests/test_ui_chat.py` with a fake model (an invented citation is dropped and flagged; an unsupported answer renders as such; the cap stops the 21st call; nothing is written outside `ui/`).
W2 and W3 share only the route `POST /runs/<id>/chat`, which W2 stubs and W3 fills; `make smoke` stays offline because every test uses fakes and the fixture run.

## 10. Risks

The subprocess's stdout and the SSE stream can disagree if an emit site forgets its fields; the W1 test that checks every site guards this.
A page open on the projector while the terminal also runs is two consumers of one `progress.jsonl`; both read, neither writes, so this is safe.
The chat can be read by an evaluator as "the agent"; the pill, the column and the manifest exclusion are the answer, and the runbook should say the sentence aloud.
Venue network: the page loads no external font or script, so it works offline; system fonts render on the laptop (Inter is self-hosted later, craft 6.4).
The page is the first user interface the lab sees, so slop there costs more than its absence; the token sheet and the hex grep gate (craft 8.1) keep it to one system.

## 11. Decisions for him, each with the recommended answer

1. Shape: A, the page with a side chat; not B, not C.
2. Launch: runs start as `dra review` subprocesses, never in-process; yes.
3. Chat model and cap: Sonnet 5.5 at low effort, 20 calls and 0.50 USD per review, logged to `runs/<id>/ui/chat.jsonl`; yes.
4. Chat corpus: the review, ledger, anchors and coverage only, never the PDF; yes.
5. A `regressed` reassessment status: not before the demo, since it touches the schema, `models.py` and the grader; label new_in_update as including regressions.
6. Demo day: the page on the projector with the terminal in a second window, both rehearsed, the runbook amended after the first timed rehearsal with the UI; yes.
7. PDF page links: the browser's own viewer at `doc.pdf#page=N` in a new tab, no PDF library; yes.
8. Theme and fonts: light only, system font stack now, self-hosted Inter and a mono later; yes.
9. Where the page lives: inside the Python package so `pip install -e .` ships it and `dra ui` finds it; yes.
