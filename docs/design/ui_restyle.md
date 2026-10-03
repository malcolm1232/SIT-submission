# Restyling the review UI in the DBSearch idiom, with a sidebar that shows what is running

Date: 2026-10-03.
Status: mockup and recommendation only; no product code was changed.
Picture: `docs/design/ui_mockup_v2/for_him_ui_v2_composite.png` (three frames at 1440 px, also one PNG per frame beside it), built from `docs/design/ui_mockup_v2/index.html` and `tokens.css`; `shoot.py` regenerates it with the `.venv` Playwright.
The owner's ask: "make it like DBSearch, the UI in Draft, then a sidebar or something to show what's running, to make the UI look nicer".
Reference read: `DBSearch.AI/src/dbsearch/server/static/css/tokens.css`, `css/rail.css`, `css/app.css` (topbar, pills, chat empty state, composer), `js/ui/rail.js` (the rail's structure), `js/surfaces/draft.js` (the Draft surface), and the craft rules in `QuantifyMe/design_mockups/research/research_anti_slop_craft.md` (cited as "craft x.y").

## 1. What changes versus the built page

The page gets DBSearch's app grid: a 248 px dark rail on the left, a 56 px topbar, and the surface as one centred column (820 px on the Review page, 1120 px on the run and review pages), instead of the built page's 48 px bar over a full-width two-column layout.
The rail is DBSearch's `.navrail` verbatim in geometry and colour: brand in the serif, two small-caps group labels WORKSPACE (Review, Runs, Replay) and OPERATE (Tools, Settings, Developer), 16 px line icons that inherit the item colour, the active item as a paper pill on ink, a bottom note card, and the Collapse control.
The rail's content slot, the one region DBSearch lets a surface fill (rail.js #631), carries two lists: Runs (a running run shows a green dot, its current stage and the run clock; a finished one its verdict, confidence and wall time) and Tools (the four MCP servers with a warm or off dot and the last warm-up time).
The bottom card replaces DBSearch's permissions note with the page's own promise: "Every number on this page comes from the run directory. Nothing is estimated."
The topbar carries a green-dot status pill "local · your subscription · no API key", a hairline pill "tools: 2 of 4 servers warm", and the profile selector where DBSearch has its model selector; there is no sign-in, and the share dialog says "there is no login on the page" instead.
The Review page becomes DBSearch's empty state: a centred Instrument Serif heading "Review a design document", a two-line subtitle, the drop zone as a white card, and three suggestion chips for the synthetic documents in `eval/synthetic` (payments orchestration, clinical RPM, research lakehouse), which fill the form and never start a run (the rule draft.js states for its chips).
The run page gets a serif heading with the document title and a large tabular run clock "03:34 / 09:00" at the right, where the built page has them in the top bar; stage rows keep their elapsed bar against the limit, and a skip or a cut is a disclosure line under stage 1 naming its DEG id and what the report will say.
The finished review puts the verdict first in the serif at 36 px, then the counts, the rationale and "what would change it" in the report's own words, the objectives table, the findings by rank with one expanded; the Delta tab is shown disabled with "no previous version was given for this run".
The three outputs (Download, Email, Share link) become three quiet hairline pills in the page head, in the shape of DBSearch's sources pill, instead of a three-row form at the top of the review.
The chat becomes DBSearch's composer at the foot of the review column: one bordered shell with the text field, a green status pill "Grounded in this review", a dark "Ask" button, and the small-caps footer "ENTER TO ASK · SHIFT + ENTER FOR A NEW LINE" on the left and "TRIMMED TO THIS REVIEW · 20 ASKS OR $3 PER RUN" on the right in signal green.
The tools checkbox overlap of the built page (the label wraps into the help text because `.check` is 32 px high) is fixed: the control and its label sit on one non-wrapping line with a minimum height, and the help text has its own line.
Colour meaning is narrowed to DBSearch's rule that green is a signal and never a button fill: the running pill, the warm dot, the status pill and the "grounded" pill are the only green; done is ink on paper; severity keeps its red, amber and grey; critical stays the one saturated fill (craft 4.3, 8.5).
Nothing animates: DBSearch's pulsing status dot and its pop-in keyframe are left out, and hover stays a 150 ms background change (craft 1.3 interaction, 2.6 motion).

## 2. What stays

Every function of the built page is present: the drop zone, the pasted https link with its policy note, the previous version, the profile with its stage limits, the tools toggle with `--no-tools`, the run ID, Start review, the argv line in monospace, the stage tracks with limits, the amber draft pill and its disclaimer, the cut and skip disclosures, the status feed with the terminal's lines, the review from `report.json`, the Delta tab, the Coverage, Evidence and Run log tabs, the three outputs, the chat with its "reading aid, not the review" label and cap counter, and the "replayed evidence" stamp (named in the run legend; it sits in the page head of a replayed run).
The review stays the centre of the page and the chat stays a reading aid under it, never a chat-first front (ui_design.md section 2, shape C rejected).
The honesty rules of `app.js` are unchanged: every number comes from the run directory or the event stream, review text is inserted exactly as `report.json` has it, times are as of the last event and never ticked by the browser.
The recent-runs table moves from the Review page into the rail's Runs list and the Runs page; nothing is lost, and the Review page keeps one job.
The anti-slop choices of the built page stand: tabular numerals (craft 4.1), hairlines instead of nested boxes (craft 8.6), one line-icon set and no emoji (craft 8.8), 12 px as the floor for body text (craft 8.4), one primary action per view (craft 8.5), and every state designed (craft 8.10).
One exception is taken knowingly: DBSearch's single uppercase mono caption style at 10 px is used in exactly three places, the rail's group labels, the slot heads and the composer footer, which is the "one uppercase caption style used sparingly" that craft 1.2 item 10 allows and craft 1.3 would otherwise forbid.

## 3. DBSearch tokens reused

Copied verbatim into `ui_mockup_v2/tokens.css` section 1: the paper ramp (`--paper`, `--paper-2`, `--white`, `--ink-900` to `--ink-300`, `--rule`, `--rule-strong`), the signal green (`--accent`, `--accent-soft`, `--accent-bright`, `--accent-ring`), the ink action (`--action`, `--action-hover`, `--action-fg`), the semantic green, amber and red with their soft and border steps, the rail colours from `rail.css` (`#16161A`, `#9A9AA2`, `#6B6B73`, paper active pill, 248 px), the shadows, the radii (`--r-lg` 14, `--r-md` 10, `--r-sm` 7, pill, 6 px controls), the font stacks and the vendored Instrument Serif (`instrument-serif-latin.woff2`, copied so the page still loads no network font).
Section 2 maps the SIT page's own role names (`--bg-app`, `--bg-surface`, `--fg-muted`, `--border-subtle` and the rest) onto that palette, so `app.css` keeps every selector and only the tokens file changes for colour.
The CSS shapes reused by name: `.navrail`, `.navrail-group`, `.navrail-item.active`, `.navrail-slot`, `.navrail-note`, `.navrail-toggle`, `.edition-pill`, `.trust-chip`, `.model-pick`, `.chat-empty h2`, `.starter`, `.surface-head`, `.surface-title`, `.composer-shell`, `.chat-input`, `.ask-btn`, `.composer-hint`, `.composer-trust`, `.sources-pill`.
Two DBSearch things are deliberately not reused: the halo keyframe on the status dot, and the account control with its sign-in.

## 4. The sidebar's data sources

Runs list: `GET /runs` already returns one row per run directory with `run_id`, `status` (running, finished, ended), `document`, `verdict`, `confidence`, `findings`, `wall_s`, `cost_usd` and `replayed` (`ui/rundata.py` `summary`), which is everything a finished row shows.
A running row's stage and clock are not in that payload: they live only in the run's `progress.jsonl` (`phase_started`, `call_opened`, `call_status`, `run_s`) and the page reads them today only for the run it has open through `GET /runs/<id>/events`.
To add, server side: `stage` and `run_s` on each `/runs` row from the last record of `progress.jsonl` (`rundata.last_event` already reads it) plus `open_calls` from the last `call_status`, so the rail can show "assess · 03:34 · 2 shards open" without a stream per run; the rail refreshes this list every 2 s while any row is running, and the open run keeps its SSE stream as today.
Tools list: `GET /meta` returns each server's `name` and `enabled` from `config/tools.yaml`, which gives the off rows; warm or asleep and the last warm-up time are recorded only inside a run, as the `mcp_warmup` and `tool_status` events of `progress.jsonl` and the `tools` block of `manifest.json`.
To add: `GET /tools` in `ui/server.py` that returns, per server, `enabled`, the last `mcp_warmup` outcome and time found in the newest run directory that has one, the tool count from that run's `tools_list.jsonl`, and the last `tools_down` event if any; this is a read of files, no probe, no network.
The "warm" word is therefore "answered the last warm-up at HH:MM", not "awake now": the servers scale to zero (config/tools.yaml, cold starts of 29 to 70 s measured), so a live claim needs a live probe, which decision 3 below leaves to a button.
Settings: `GET /meta` has the profiles with `deadline_s` and `stage_limits_s`; the config file names come from the newest run's `run_manifest.extra.config.files` keys, or from `/meta` once it lists `config/*.yaml` by name (one line to add).
Developer: the exact CLI line is `argv` in `GET /runs/<id>` (from `ui/launch.json`) and the argv of a terminal run is in `manifest.json` `extra.code.argv`; the run directory is `/meta.runs_dir`; the version is `/meta.commit` plus `sit_review_agent_version` from the manifest, which `/meta` should carry too.
Topbar pills: "local · your subscription · no API key" is true whenever the backend is `claude_code` (every live run so far); the server should state the backend from the effective config rather than the page assuming it.

## 5. Build plan, one workstream

Files: `agent/sit_review_agent/ui/static/tokens.css` (replace with the v2 tokens), `app.css` (the grid, the rail, the topbar, the empty state, the composer; the run and review rules keep their selectors), `index.html` (the rail markup, the topbar, the chips, the three templates reshaped), `app.js` (the rail's runs and tools lists, the stage and clock on the rail, the chips filling the form, the composer at the foot of the review), `ui/server.py` and `ui/rundata.py` (`stage`, `run_s`, `open_calls` on `/runs` rows; `GET /tools`; `backend`, `version` and config file names on `/meta`), the font file beside `tokens.css`, and `tests/test_ui_server.py` plus `tests/test_ui_honesty.py` for the new fields and the no-estimate rule.
Order: tokens and the grid first (every page restyles at once), then the rail with its two lists, then the Review page, then the run and review pages, then the composer, each step screenshotted at 1440 px against the mockup frame before the next.
Estimated size: one agent shift for the server fields and one for the page, with the mockup's `index.html` as the reference and the existing selftest fixture run as the data.

## 6. Risks

The rail's runs list polls `/runs` while something runs, and `summary` reads `report.json`, `manifest.json`, `launch.json` and the whole `progress.jsonl` per directory; with many run directories that is a lot of file reads every 2 s, so `summary` should cache by mtime or the poll should ask only for the running rows.
A "warm" dot read from the newest run misleads if that run is hours old; the rail must show the time next to the dot and the Tools page must say what the dot means.
The serif heading and the dark rail make the page read as DBSearch's sibling; the brand "SIT review." must be the only wordmark so nobody reads it as DBSearch itself.
The tabs and the three output pills share one head row; on a narrow window one of them must drop below, and the built page's 1024 px minimum should stay.
The composer at the foot of a long review is far from the verdict; the page should pin it to the bottom of the viewport as DBSearch pins its composer (app.css #398), which `app.css` has to do with the sticky rule the chat panel uses today.
Frame 2's draft lines carry the rehearsal's real finding titles and severities, but their times and shard labels are placed inside the measured window (first finding at 77 s, stage 1 end at 232.6 s) because `progress.log` of that run is not committed; the built page will show the recorded values.

## 7. Decisions for him, each with the recommended answer

1. Adopt the DBSearch idiom (rail, topbar pills, serif headings, ink pill, composer) for the SIT page as drawn: yes.
2. Rail content: Runs and Tools as lists in the rail's slot, Settings and Developer as pages: yes.
3. Tools status: show the last recorded warm-up with its time, and add a "Probe now" button on the Tools page that runs the existing probe on demand and logs it, rather than probing on every page load (it would wake scale-to-zero containers and cost a cold start each visit): yes.
4. Chat placement: the composer at the foot of the review column, answers above it, no side panel: yes.
5. The three output actions as quiet pills in the head, with the email address field opening under the Email pill: yes.
6. Suggestion chips for the three synthetic documents on the Review page, filling the form and never starting a run: yes.
7. The uppercase mono caption in three places only (group labels, slot heads, composer footer): yes.
8. Dark theme: not now; DBSearch authors its dark palette separately and this page can take it later: defer.
9. Rail collapse: keep DBSearch's control and its localStorage key, default expanded on every page: yes.
