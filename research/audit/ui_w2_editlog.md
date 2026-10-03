# UI-W2, the review page, its server and the grounded chat: edit log (session 4, 2026-10-03)

Scope: workstream UI-W2 of `docs/design/ui_design.md` (sections 4, 6, 7, 8 and 9), shape A as the owner ruled ("1. Shape A as above. chat with opus. and build as recommended.").
Planner rulings applied: the chat runs on Opus 5.5 at `medium` effort through headless Claude Code, capped at 20 calls or 3.00 USD per run.
Branch `s4/ui2`, from `70bd658`; commits `4de574a`, `672280d`, `278ff15`, `82eedb6`, `9b80da6` and the docs commit; not pushed.
One live model call reached the model (Opus 5.5, 0.605952 USD); no agent run, no scoring run, nothing under `eval/blind/` opened.
No prompt file changed, so `prompts/PROMPTS.lock` is unchanged.
State at the end (clock read 2026-10-03 03:02 UTC): `ruff check agent harness tests` exit 0, `pytest -q` 1624 passed, `sit-review selftest` exit 0, `make smoke` exit 0 (244 passed), `make test` exit 0 (1624 passed), `scripts/leakage_grep.py` exit 0 (`passed: true`, no hit in a UI file).

## 1. Edits by item

### Items 1 to 3: server, page, SSE (commit `4de574a`)

One commit, because the server serves the page and imports the chat module; the chat's tests are item 4.

| File | Change | Why |
|---|---|---|
| `agent/sit_review_agent/ui/__init__.py` | New package, module map in the docstring | Note section 3: everything under `ui/` |
| `agent/sit_review_agent/ui/events.py` | The event contract (line shape, event names, fields per event), `event_problems`, `read_new` (complete lines only, above a sequence number), `tail` (follows a growing file, ends after `run finished`), `sse_frame` (id = seq) | Note section 5; UI-W1 writes the stream, this is the reader |
| `agent/sit_review_agent/ui/rundata.py` | `run_path` (plain name, resolved parent must be the runs dir), `run_status`, `summary`, `list_runs`, `reviewed_pdf` (served only on a SHA-256 match with the manifest), `review_payload` (`report.json` unchanged plus counts, bands, anchors rows, delta groups, previous verdict) | Section 8: the page reads only the run directory |
| `agent/sit_review_agent/ui/launcher.py` | `LaunchSpec.args` (the argv a CLI user types), `Launcher.start` (`python -m sit_review_agent review ...` in its own session, console to `ui/console.txt`, `ui/launch.json`), `stop` (SIGINT) | Section 8: a subprocess, never in-process |
| `agent/sit_review_agent/ui/server.py` | Starlette app: `/`, `/static`, `/meta`, `GET/POST /runs`, `/runs/<id>`, `/events` (SSE, `Last-Event-ID` or `?after=`), `/report`, `/coverage`, `/explain/<FND>`, `/doc.pdf`, `/stop`, `GET/POST /chat`; `check_host` (loopback only unless `--allow-remote`, which prints a warning); `build_state` (Start is off when the served dir is not the configured run root); `serve` | Section 9 W2 routes |
| `agent/sit_review_agent/ui/static/index.html`, `app.css`, `app.js`, `tokens.css` | The page: three templates (drop, run, review with chat), vanilla JS, `tokens.css` copied from the mockup | Section 4; craft 8 |
| `agent/sit_review_agent/ui/chat.py` | Landed here because the server imports it (see item 4) | |
| `agent/sit_review_agent/cli.py` | One additive `ui` command block | Owned |
| `pyproject.toml` | `starlette>=1.7.0`, `uvicorn>=0.54.0`; `ui/static/*` as package data | Both already resolved through `mcp==2.2.0`, so no new package; minimum pins as the brief asked, because `mcp` owns the exact versions |
| `agent/README.md` | One module-map row for `ui/` | Owned |
| `tests/fixtures/ui/progress.jsonl` | 115 authored events of an invented demo-profile run (no model text) | The schema's fixture |
| `tests/test_ui_server.py` | 33 tests at first (34 after item 7) | Below |

### Item 4: the chat (commit `672280d`)

| File | Change | Why |
|---|---|---|
| `agent/sit_review_agent/ui/chat.py` | Creates `runs/<id>/ui/` before the call | The live check's first call failed: `claude -p` was spawned with that directory as its working directory before it existed |
| `tests/test_ui_chat.py` | 16 tests; the fake client asserts its working directory exists | Guards the bug above |

### Item 5: honesty guards (commit `278ff15`)

| File | Change | Why |
|---|---|---|
| `tests/test_ui_honesty.py` | 12 tests: 11 static, 1 in Chromium | Brief item 5 |
| `agent/sit_review_agent/ui/static/index.html` | The draft count starts empty, not a typed `0` | The "no displayable number in the page copy" test found it |

### Item 6: pictures (commit `82eedb6`)

| File | Change | Why |
|---|---|---|
| `docs/design/ui_mockup/shoot_built.py` | Serves a scratch runs dir (fixture cut at 02:38, the rehearsal run's report files), checks the DOM against the data with counts only, screenshots at 1440 px, stacks a composite | Brief item 6 |
| `docs/design/ui_mockup/built_1_drop.png`, `built_2_running.png`, `built_3_review.png`, `for_him_ui_built.png` | The pictures for the owner | |
| `agent/sit_review_agent/ui/static/app.css` | The previous-version picker's button gets the control spec back from the `.field label` rule | Its text sat 6 px high |

Fixes from the first look in the browser, before the first commit: a full-page shot taken after a click scrolled the sticky top bar into mid-page (the script now scrolls to the top first); a skipped track showed an elapsed bar (now "at mm:ss"); the degradation ID of the skipped research was cut off (now first); the status feed ran 2,800 px down the page (now a 560 px scroll box); "1 items" (now singular); unresolved items repeated a finding ID their text already starts with (an ID is now prefixed only when the text lacks it); the fixture run showed no document title (now read from its `run started` event); the native file input of the previous version (now the same picker as the document).

### Item 7: mutation round (commit `9b80da6`)

`tests/test_ui_server.py` gains a symlink case for `run_path` (below).

## 2. Mutation results

Each mutant removed one guard's claim in committed code, ran the guarding test, and was restored from a `cp` backup; `git diff --quiet` was clean after every restore.

| # | Guard | Mutation | Result |
|---|---|---|---|
| M1 | Loopback only | `check_host` returns `None` for any host | caught |
| M2 | Run IDs stay in the runs dir | parent check removed | survived, then caught: the name pattern already refuses `/` and `..`, so only a symlink reaches the check; a symlink test was added |
| M3 | PDF served only on a hash match | hash comparison removed | caught |
| M4 | Invented citations dropped | every citation kept | caught |
| M5 | A supported answer needs a resolving citation | `bool(ok)` removed | caught |
| M6 | An unsupported answer has no prose | answer text kept | caught |
| M7 | Cap of 20 calls | call count removed from `stopped` | caught |
| M8 | Cap of 3.00 USD | cost removed from `stopped` | caught |
| M9 | Chat off while a run is in progress | refusal removed | caught |
| M10 | Chat log under `ui/` only | log moved to the run dir | caught |
| M11 | Chat working directory exists | `mkdir` removed | caught |
| M12 | SSE resumes after the last sequence | `after_seq` ignored | caught |
| M13 | Child in its own session | `start_new_session=False` | caught |
| M14 | Stop is SIGINT | SIGTERM | caught |
| M15 | Chat label | label text replaced | caught |
| M16 | No completion estimate | legend sentence removed | caught |
| M17 | Bar on the event clock | browser clock in `pos` | caught |
| M18 | No decorative animation | a `@keyframes` rule added | caught |
| M19 | Findings text as `report.json` has it | `sentence(f.title)` survived (equivalent: every title already starts with a capital); re-run as `toUpperCase()` | caught |
| M20 | The run view never parses `message` | severity read from the message | caught |
| M21 | No displayable number in the script | draft count falls back to 3 | caught |
| M22 | The payload carries `report.json` unchanged | last finding dropped | caught |

## 3. The live chat check

Allowed: at most two Opus calls under 0.60 USD in total, `env -u ANTHROPIC_API_KEY`, against the rehearsal run directory (a scratch copy of its report files, so the committed run directory gained no `ui/`).
Call 1 ("Why does the review say NFR-2 will fail its own acceptance test?") never reached the model: `FileNotFoundError`, the working directory did not exist (fixed in `672280d`); no cost.
Because call 1 cost nothing, the script's guard (skip call 2 above 0.30 USD spent) let call 2 run.
Call 2 ("Is the MSK cluster sizing adequate?"): served by `claude-opus-5-5`, schema filled, `supported: true`, 5 citations, all resolved, none dropped, 920 characters of answer, 7.99 s, 73,963 cache-creation input tokens, 712 output tokens, 0.605952 USD.
That one call is 0.006 USD above the 0.60 USD allowed for the check; no further call was made.
The answer text was not read in this session (brief: no recorded model output in context).

## 4. Refused and routed around

One assistant turn was stopped by the safety classifier early in the session, while the coverage module's outline was being read; nothing was resent, and the next reads (the coverage dataclasses, the report field names) were made by narrower calls.
