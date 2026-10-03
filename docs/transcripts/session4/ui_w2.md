# UI-W2: the review page, its server and the grounded chat

Date: 2026-10-03 (clock read 2026-10-03 03:02 UTC).
Branch `s4/ui2` from `70bd658`; commits `4de574a`, `672280d`, `278ff15`, `82eedb6`, `9b80da6` and the docs commit; not pushed.
Edit log: `research/audit/ui_w2_editlog.md`.
Design: `docs/design/ui_design.md`, shape A, as the owner ruled ("1. Shape A as above. chat with opus. and build as recommended.").

## Status by deliverable

1. `dra ui [--host 127.0.0.1] [--port 8765] [--runs-dir DIR] [--allow-remote]`: done.
   It serves on loopback only; any other host exits 2 unless `--allow-remote` is given, and then it prints a warning that the page has no authentication.
   No authentication is the documented limitation, in the server's docstring and in that warning.
2. The page: done.
   It is plain HTML, `tokens.css` copied from the mockup, `app.css` and vanilla `app.js`, with no framework, no CDN, a light theme and system fonts.
   The drop screen takes one document plus an optional previous version, a profile and a document-only switch, and shows the command it will run.
   Start runs `python -m sit_review_agent review <doc> [--profile P] [--v1 <prev>] [--no-tools] --run-id <id>` as a subprocess in its own session, which writes the standard run directory; the page shows the command as `dra review ...`.
   The run view draws stage 1 as one row per track with elapsed time against the stage limit on the event clock, the sequential stages with their limits, drafts under the "draft, unverified" pill, cuts and skips with their IDs, and the status feed.
   The review view renders `report.json`: verdict, confidence and band, counts, rationale, objectives, findings by rank with severity pills, an expandable finding (anchors as `doc.pdf#page=N` links with the quote and match detail, evidence IDs, recommendation, next step, decisions with their relation, re-assessment), strengths, areas checked with no issue, unresolved issues and limitations, plus Coverage and Evidence tabs and a Run log tab when the run has events.
   The Delta tab appears only when findings carry a re-assessment, grouped in the note's four headings; without one it is absent, with no placeholder.
3. SSE and run pages: done.
   `GET /runs/<id>/events` tails `progress.jsonl` with the sequence number as the event ID; a reconnect resumes after `Last-Event-ID` (or `?after=N`); the stream ends after `run finished`, or when nothing more can be written.
   `GET /runs` lists every run directory under the runs dir, and `/?run=<id>` opens any of them, including a replayed one, which is stamped "replayed evidence".
4. The chat: done.
   One question is one `claude -p` call on Opus 5.5 at `medium` effort, with every CLI tool off and a strict JSON schema (`answer`, `cited_finding_ids`, `cited_evidence_ids`, `cited_other_ids`, `supported`).
   The corpus is that run's `report.json` (without the manifest and provenance hashes), its ledger, anchors and coverage map; never the PDF, the prompts, `llm.jsonl` or an earlier answer.
   Every cited ID is checked against the run; one that does not resolve is dropped and listed under the answer; an answer with `supported: false`, or with no citation left, renders as "The review does not answer this." with no prose.
   Calls are logged to `runs/<id>/ui/chat.jsonl` (question, prompt hash, model, effort, usage, cost, citations kept and dropped) by the chat's own client, never through `LLMGateway`.
   The cap is 20 calls or 3.00 USD per run, and the panel shows the running count, the cost and the log path; the chat is off while a run is in progress and cannot start, stop or change a run.
5. Honesty and anti-slop tests: done (`tests/test_ui_honesty.py`, 12 tests, one of them in Chromium).
6. Pictures: done.
   They are `docs/design/ui_mockup/built_1_drop.png`, `built_2_running.png`, `built_3_review.png` and the composite `for_him_ui_built.png`, all 1440 px wide, made by `docs/design/ui_mockup/shoot_built.py`.
7. Mutation round: done; 22 mutants, all caught in the end (two survivors explained and closed in the edit log).

## Server dependency

Starlette 1.7.0 with uvicorn 0.54.0, the note's own choice.
Both are already installed through `mcp==2.2.0`, so the UI adds no package to the environment; they are listed in `pyproject.toml` with minimum pins, as the brief asked, because `mcp` owns their exact versions.

## The chat's live check and its cost

Two Opus calls under 0.60 USD were allowed; one reached the model and cost 0.605952 USD, 0.006 USD over the allowance.
The first call never started: the chat spawned `claude -p` in `runs/<id>/ui/` before that directory existed, a bug the fake client could not show; it is fixed, and the fake client now refuses a missing working directory.
Because the first call cost nothing, the script's guard let the second run.
That call filled the schema, answered as supported, and cited 5 IDs that all resolved in the run.
The corpus came to 73,963 input tokens, all written to the prompt cache, so one uncached call costs about 0.61 USD.
At that size the 3.00 USD cap allows about five uncached questions, not 20; a question asked within the cache lifetime should read the cache at a tenth of the price, but no second call was made, so that is not verified.
If 20 questions per run must fit under 3.00 USD, the corpus needs to shrink (for example the coverage rows and the ledger excerpts that findings already quote); that is the planner's call.

## Decisions taken here

The event schema of section 5 is not written down field by field in the note, so this workstream wrote it out in `ui/events.py` and authored the fixture in it.
The draft event's finding kind is `finding_kind`, because `kind` is already the event's own kind (`step`, `warn`, `draft`).
A run can be started only when the served directory is the configured run root, because `dra review` writes there; serving `docs/live_runs` opens runs but disables Start, with the reason on the page.
Times on the run view are run-clock times as of the last event; the browser clock is never used, so a stalled stream shows a stalled clock rather than an invented one.
An unsupported answer shows no prose, as the brief says; the note's "with whatever the review does say" is not followed.
The chat cap lives in `ui/chat.py` constants, not `config/ui.yaml`, because that file is not in this workstream's files.
Routes beyond the note's list: `GET /meta`, `GET /runs`, `GET /runs/<id>`, `/coverage` and `/explain/<FND>` (the existing `dra coverage` and `dra explain` code, read-only).
One run at a time may be started from one server.

## Not verified

No `dra review` was launched from the page; every launch test uses a fake process, as the brief required.
Stop has not signalled a real child, and a real run's `progress.jsonl` has not been streamed, because UI-W1's writer does not exist yet on this branch.
The delta view is tested on a rehearsal copy with invented re-assessments; no real delta run exists to picture it.
The anchor links are checked to point at `doc.pdf#page=N`; that the browser's PDF viewer opens at that page was not checked.
The chat answer's wording was not read in this session, and the cache reuse on a second call was not measured.
Serving with `--allow-remote` was checked only for its warning and refusal paths.

## For the integration pass

These are what to join with UI-W1's real events, in the order to check them.
1. Line shape: each line of `progress.jsonl` needs `seq` (1, 2, 3, ... in file order), `t` (run-clock seconds), `phase`, `kind`, `message` (the console line's text without the marker), `event` (a name below, or null) and `fields`.
2. Event names the page reads: `run started`, `phase started`, `phase done`, `milestone`, `call opened`, `call status`, `call closed`, `draft`, `stage cut`, `skipped`, `stop rule`, `run finished` (`ui/events.EVENTS`); W1's names must match these, or this tuple and the `applyEvent` switch in `app.js` must be renamed to W1's.
3. `run started` must carry `deadline_s`, `stage_limits_s` (`stage_1_end`, `refine_end`, `verdict_end`), `profile` and `document` (`title`, `pages`, `sections`); without them the page shows no limit rather than a guessed one.
4. `call opened` and `call closed` need `call_id` and `phase`, and an assess shard needs `shard_index`, `shard_count` and `shard_name`; `call closed` needs `outcome` (`ok`, `cut`, `error`, `declined`, `truncated`) and, for a cut, `kept_items`.
5. `call status` is one event per open call per tick with `thinking_tokens`, `items` and `chars`; the tracker today prints one combined line, so W1 either emits per-call events beside it or the page must read a list from one event.
6. `draft` needs `call_id`, `phase`, the shard fields, `index`, `finding_kind`, `severity` and `title`.
7. `skipped` needs `phase`, `degradation_id` and `reason` (the research skip is DEG-002 in the rehearsal); `stage cut` needs `stage`, `at_s`, `call_id` and `kept`.
8. `run finished` needs `outcome`, `exit_code` and `report_path`; the stream ends there.
9. The sequential rows expect phases named `merge`, `refine`, `verify`, `verdict` and `report`; if the integrated orchestrator emits other names, the `SEQ` table in `app.js` follows them.
10. Then replace the fixture with a recorded `progress.jsonl` from the selftest or a fake-gateway run, run `tests/test_ui_server.py` and `tests/test_ui_honesty.py`, and rerun `shoot_built.py` so the owner's picture shows a real stream.
11. Last, check that `dra replay` writes a `progress.jsonl` the page can open, so the demo can open a replayed run with its timeline.
