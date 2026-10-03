# UI v2 verifier: the merge of `s4/uibuild2` into `s4/final2`

Written on 2026-10-03 by the verifier worker that finished the merge a previous verifier had left in progress.
The pushed tip before this work was 7e242fd (the delta-path fixes); the v2 build tip was d6cab01.

## What was on disk

The worktree `/Users/malco/Desktop/SIT-wt/final2` held a merge in progress with three conflicted files, not the one the brief named: `agent/sit_review_agent/ui/static/app.css`, `agent/sit_review_agent/ui/static/app.js` and `tests/test_ui_honesty.py`.
`index.html`, `tokens.css`, the server modules and the other tests had auto-merged.

## How each conflict was resolved (fc03cca)

`app.css`, first hunk: the v2 app grid (rail, top bar, surface) replaced the v1 `.top` chrome and its `.tab` rules, which v2 restates at its own tab block.
`app.css`, second hunk: the v2 composer shell replaced the v1 `.composer` block, and the delta table rules of the delta fixes (`table.grid.delta`, the column widths, `tr.ddetail`) were kept at the end of the file.
`app.css`, the tab block: `.tab:disabled` now shares its rule with `.tab.off`, and `.tab.off.on` was kept, so a tab shown off by either mechanism looks the same.
`app.js`, first hunk: the v1 `topBar` function was dropped (no caller remained) and the v2 `railActive` kept.
`app.js`, the Delta tab: the v2 side tested `!P.derived.delta`, which could never be true because the merged server's `delta_view` always returns an object with `available` and `reason`; the resolution reads `available`, carries the server's `reason` as the tab's title and into the v2 `#tab-note` ("Delta is off: no previous version was given for this run."), and keeps the tab openable so the reason can be read on the tab itself (the delta fixes' behaviour, tested by `tests/test_ui_delta_tab.py`).
`app.js`, `renderTabs`: an off tab gets `aria-disabled="true"` and the class `off` instead of the `disabled` attribute, because a `disabled` button cannot be opened and the delta fixes' test clicks it to read the reason.
`tests/test_ui_honesty.py`: the v2 assertions were kept (one Delta tab, its title, the `#tab-note` sentence) with `aria-disabled` in place of `is_disabled()`.

## The strings check

After the resolution there are no conflict markers under `ui/static/`.
`app.js` renders "(was FND-nnn)" from `f.reassessment.prior_finding_id`, "new (regression)" from `deltaStatus`, and "No previous version was given for this run" as `NO_DELTA`.
"Ask the review" and "Every number on this page comes from the run directory" are in `index.html`; "Grounded in this review" is in both `index.html` and `app.js`.

## The seams fixed after the merge (b765616, 37c2b07)

`tests/test_ui_delta_tab.py` and `tests/test_reassessment_delta.py` imported their sibling modules as `tests.<module>`, which does not collect in this venv from any working directory because `tests/` is not a package; every other test imports siblings bare, so these two now do too, in ruff's import order.
No other seam was needed: the UI test files passed on the first run after that change (145 passed).

## The page check (450a4c8)

A server on port 8799 served `docs/live_runs`; Playwright at 1440 px shot the Review page, the finished review `sit_sample_tools_1` and the Delta tab of `reassess_payments_v2_1` into `docs/design/ui_mockup_v2/merged_1_review.png`, `merged_2_finished.png` and `merged_3_delta.png`.
The Delta tab showed 19 rows, 16 of them with a prior ID and this review's ID, every row with a status; the run predates the delta table, so the notice sentence is shown above the groups and there is no regression row in this data.
On page load 9 requests fired, none to `/tools/probe`; over the whole check 38 requests, all GET, all to 127.0.0.1:8799.
Visible differences from the mockup frames, Review page: the chips label reads "or a sample document from config/ui.yaml:" (the builder's change, chips come from `config/ui.yaml`), the link note says 50 MB (the fetch limit of decision #39, the mockup said 100), the tools note names the run that recorded the warm-up, the Start review note explains that this server reads `docs/live_runs` rather than the run root (true for this check), the run list scrolls at 8 runs where the mockup showed 4, and the profile select keeps the browser's own arrow where the mockup drew a chevron.
The one difference not forced by data was fixed: the "Document only" checkbox had lost its flex row and gap because `.field label` (display: block) outranked `.check`; the rule is now `.check, .field label.check`.
Finished review: the title is the document's own from report.json, with the long dash the document carries where the mockup wrote a comma, the verdict prose is the report's full text with its bullet lists, the confidence line adds the band ("0.72, medium"), there is no Run log tab because this run has no events file, and the notice line below the tabs is the export notice because no share link was asked for.

## Records (84065bc)

`docs/USER_DECISIONS.md` row 41 records the owner's words on the v2 mockup, "ok it looks good", with the consequence that the v2 look is the review UI and the v1 look is not kept; row 40 is not in the file, which the section says.
`docs/ARCHITECTURE.md` section 10 gained two sentences on the v2 look and on the tools status being the last recorded warm-up, never a probe on load.

## Gates (all exit 0)

`ruff check agent harness tests`: all checks passed.
Full suite from the repo root: 1865 passed in 250 s; from `/Users/malco`: 1865 passed in 226 s.
`sit-review selftest`: passed in 0.5 s.
`make smoke`: selftest plus 251 passed; `make test`: ruff plus 1865 passed.
Leakage check `tests/test_runtime_leakage.py`: 5 passed; robustness runner `tests/robustness`: 161 passed; `tests/test_export_public_snapshot.py`: 65 passed.
No em dash on any added line since 7e242fd; every commit is authored by `malcolm1232 <66200354+malcolm1232@users.noreply.github.com>` with no trailer.

## Not checked, for the next session

A live run started from the page (this server read `docs/live_runs`, where runs cannot start).
Real SMTP: the Email button was only seen disabled with its reason.
The share link opened from a second device.
`Probe now` against real tool servers: only the absence of a probe on load was confirmed.
The profile select's native arrow against the mockup's chevron, left as is.
Row 40 of `docs/USER_DECISIONS.md`, absent at the time of writing.
