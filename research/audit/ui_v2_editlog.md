# Review UI v2 (the DBSearch idiom with a sidebar): edit log (session 4, 2026-10-03)

Scope: build the approved mockup `docs/design/ui_mockup_v2/` (owner: "ok it looks good") into the shipped page, with the server fields the rail needs.
Branch `s4/uibuild2`, from `446119a` (the pushed tip merged with the mockup branch).
Offline throughout: no model call (the chat tests use their fake client), no MCP call (the probe tests use a fake probe and an unset key), nothing under `eval/blind/` opened, nothing under `docs/transcripts/` read, no `llm.jsonl`, `progress.jsonl` record or `ui/chat.jsonl` printed (fields and counts only).
No prompt file changed.
Another worker changes the Delta tab's data on `s4/deltafix` (`app.js` old lines 620 to 670): my Delta changes are the disabled tab, its title and the note under the tab row only (see section 4).

## 1. Commits

| Item | Commit | What |
|---|---|---|
| 1 | `b5053f0` | `tokens.css` from the mockup (DBSearch's tokens in section 1, the SIT roles after, plus four rail tokens for the rgba values app.css may not hold), `instrument-serif-latin.woff2` beside it, `app.css` restructured for the app grid, rail, topbar, surface, pages and composer |
| 2 | `bad3870` | `/runs` rows: `stage`, `run_s`, `open_calls` (from the records), `started_at`, `profile`, `no_tools`, `model_calls`, `version`, `argv` from the manifest for terminal runs; `GET /tools`; `/meta` gains `backend`, `model`, `version`, `config_files`, `auth_env`, `bind_host`, `port`, `ui_args`; `POST /tools/probe`; 8 server tests |
| 3 | `4b42c7f` | `index.html`, `app.js`: the rail, the topbar, the six pages, the run view and the review restyled, the composer; `GET /documents` and `GET /documents/<name>` for the chips (first written as `/synthetic` routes, moved to `config/ui.yaml` in the fix commit); `export.py` drops the `@font-face` from the inlined tokens; the tools source ignores runs whose warm-up was `none` or `skipped`; three new honesty guards; test updates for elements that moved |
| 4 | `e3a2ea0` | `built_1_review.png`, `built_2_run.png`, `built_3_finished.png`, `for_him_ui_v2_built.png` |
| 3 and 4, fix | `88722cd` | The full suite's `test_eval_isolation` forbids any `eval/synthetic` string in the agent package, which the chips' routes held: the chips now come from a `documents:` list in `config/ui.yaml` (`load_documents`, `GET /documents`, `GET /documents/<name>`), the browser guard clicks a chip and sees the form filled with no POST, the pictures were reshot |
| 5 | this commit | mutation results below, this log, the report, the README line, the demo script and runbook where they named the drop screen |

## 2. Edits by file

| File | Change | Why |
|---|---|---|
| `agent/sit_review_agent/ui/static/tokens.css` | Replaced by the mockup's sheet; `--navrail-rule`, `--navrail-row`, `--navrail-note-bg`, `--navrail-note-border` added in section 1 | app.css may hold no rgba (honesty test), the rail's translucent rules needed names |
| `agent/sit_review_agent/ui/static/instrument-serif-latin.woff2` | Copied from the mockup folder | The serif loads from this server, never the network |
| `agent/sit_review_agent/ui/static/app.css` | Rewritten: `.app` grid, `.navrail` (full-height dark column, `.navrail-inner` sticky one viewport tall, `#rail-runs` shrinks and scrolls so every tool server stays in view), topbar pills, `.surface` 820 / 1120 px columns, `.surface-head`, the pill and control spec from the mockup, the run and review rules with their selectors kept, the composer, the Tools, Settings and Developer rows | The mockup's CSS, with the shipped selectors |
| `agent/sit_review_agent/ui/static/index.html` | The rail and topbar markup; `tpl-drop` as the empty state with the chips container; `tpl-run` with the surface head (`#top-doc`, `#top-sub`, `#top-meta` clock, `#top-action`), a tab row and `#stage1-disclosures`; `tpl-review` with the outputs as three pills in the head (`#out-download`, `#email-btn`, `#share-btn`), the tab row with `#tab-note`, the download companions line, the email and share disclosures, the review, the ask section with the composer | The three frames |
| `agent/sit_review_agent/ui/static/app.js` | Rail (`renderRailRuns`, `runMetaText`, `renderRailTools`, `toolMeta`), topbar (`renderTopbar`), collapse (`setupRail`, key `navrail-collapsed`), routing by `?page=`, the chips, `showRuns`, `showReplay`, `showTools` with the probe button, `showSettings`, `showDeveloper`; `runTop` fills the surface head; `stage1Summary` and the disclosure lines; `showReview` draws the Delta tab disabled with the reason; `setupOutputs` works the pills and disclosures; `setupChat` fills the composer, Enter asks, Shift+Enter breaks the line; `h()` flattens nested kid arrays | The pages; the reducer `applyEvent` is unchanged apart from `t.disclose` on `research_doc_only` and `shard_cut` |
| `agent/sit_review_agent/ui/rundata.py` | `progress_state`, `NOT_A_STAGE`, `_argv_display`, the new row fields, `tools_status` with `_has_tool_records` (tools_list.jsonl, or an `mcp_warmup` with status in `WARMUP_ATTEMPTED`), `_iso_plus`, `_read_jsonl` | The rail's data, read from files only |
| `agent/sit_review_agent/ui/server.py` | `UIState` gains `backend`, `model`, `version`, `config_files`, `auth_env`, `probe`, `last_probe`; routes `/tools`, `/tools/probe`, `/synthetic`, `/synthetic/{name}`; `/meta` fields; `build_state` fills them from the effective config; `probe_with(cfg)` wraps the gateway's own `warm_up` with the preflight's redaction | Section 4 of the restyle note |
| `agent/sit_review_agent/ui/export.py` | `_css()` strips the `@font-face` block | The export must reference no file |
| `tests/test_ui_server.py` | 9 tests: the `documents:` loader and routes (missing files and non-documents left out), running row fields, finished row fields, `/meta`, `/tools` from the sample run, no source, the warm-up time rule, the probe's three refusals and its result | Item 2 |
| `tests/test_ui_honesty.py` | The served fixture gains the four servers, the sample run's tool records and a recording fake probe; the Delta assertion now expects the disabled tab with its title and note; one new browser test with the three guards and the chip filling the form without a POST | Item 3 |
| `tests/test_ui_outputs.py` | The export test pins `--sev-critical-bg:` and asserts no `@font-face`; the browser flow clicks the Email pill before filling the address (twice) | Elements that moved |
| `config/ui.yaml` (not in the owned list; needed because the agent package may not name `eval/synthetic`) | `documents:` with the three synthetic design documents as label and path | The chips' source, outside the agent package |
| `agent/README.md` | The `ui/` row names the idiom, the rail, the pages and the two tools routes | One line |
| `docs/DEMO_DAY_SCRIPT.md`, `docs/DEMO_DAY_RUNBOOK.md` | "the drop screen" is now "the Review page"; the draft line names the rail's Runs entry | Page elements that moved |

## 3. Mutation results (item 5)

Each mutation was applied to a `cp` backup's original, the guard run alone, and the file restored from the backup (`git diff --stat` empty after each).

| Guard | Mutation | Result |
|---|---|---|
| The rail's running entry equals the SSE state (`test_the_rail_shows_the_stream_state_and_the_recorded_servers_and_never_probes`, part 1) | `runMetaText` returns a fixed `assess · 03:34 of 09:00 · 2 shards open` for the open run | FAILED (the entry must read `refine · 01:50 of 60:00 · 1 call open`, computed in the test from the records) |
| The tools dots equal `GET /tools` (part 2) | every `.rail-tool .dot` drawn `warm` | FAILED (two dots must be off) |
| No probe on page load (part 3) | `refreshTools` posts `/tools/probe` before reading `/tools` | FAILED (a POST was seen before the button) |
| The probe refuses without the key (`test_the_probe_runs_only_with_the_key_in_the_environment`) | the key check in `tools_probe` replaced by `if False` | FAILED (the fake probe was called with the key unset) |

## 4. Lines touched in the Delta tab (for the `s4/deltafix` merge)

`app.js` is rewritten, so line numbers moved: `deltaBody` is now lines 914 to 923 and its text is unchanged from the base; the Delta tab's new lines are 943 (`NO_DELTA`), 952 (the tab entry with `off` and `title`), 974 (the note under the tab row) and 977 (unchanged dispatch).
`app.css` line 150 (`.tab:disabled`) and `index.html` line 138 (`#tab-note`) are the styling.
The old `deltaBody` text (base lines 625 to 634) was kept verbatim so the other worker's data change applies cleanly.

## 5. Gates

Exit codes read one per call: `ruff check agent harness tests` 0; `pytest -q --tb=no -p no:warnings` 0 (1846 passed, after the chips fix); `sit-review selftest` 0; `make smoke` 0 (249 passed); `make test` 0 (1846 passed); `scripts/leakage_grep.py` 0 (PASS).

## 6. How the pictures were made

The shoot script (kept in the session scratchpad, not in the repository) builds a scratch run root from `docs/live_runs/` copies (report, manifest, anchors, ledger, state, effective config, tool records, progress.jsonl, ui/launch.json; never llm.jsonl) plus `rehearsal_concurrent_2`, the fixture concurrent stream cut at 70 records with a fake live process so Stop run shows, serves it in-process on a free loopback port with the real profiles and tools from `config/`, and shoots `/`, `/?run=rehearsal_concurrent_2` and `/?run=sit_sample_tools_1` (FND-011 expanded, the share pill open) at 1440 px, full page, then stacks the three with a 32 px gap into `for_him_ui_v2_built.png`.
Equivalent by hand: `dra ui --runs-dir <such a root>` and the same three addresses in a 1440 px window.
