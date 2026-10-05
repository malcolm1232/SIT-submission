# Worker note: UI tests wait for the state they assert (ui-test-waits)

Branch `s4/ui-test-waits` from `origin/claude/happy-darwin-d0bl94` at ecb4f84, tests only, no product code.
Model: 9315a2f (the export sidebar test's `wait_active` and the new tab's `wait_for_url`).

## What changed

Every read that came right after a click, fill, drop or new tab now waits first for the exact end state the assertion needs, with `wait_for_function` or `wait_for_url`; the assertions themselves are unchanged and no fixed sleep was added.

- `tests/test_ui_outputs.py`
  - `#out-open` new tab: `wait_for_load_state()` replaced by `wait_for_url(base + "/runs/ui_flow_1/export.html")` (the about:blank race of 9315a2f).
  - New helper `wait_open(pg, name)`: `#<name>-box` unhidden and `#<name>-btn` aria-expanded true; used after both `#email-btn` clicks and both `#share-btn` clicks.
  - After each `#email-to` fill: waits for `#email-send` disabled, then enabled.
  - After each `#doc-link` fill: waits for `#start-btn` disabled and `#link-error` shown, then `#start-btn` enabled, `#link-error` hidden and the command preview carrying `Payments_Design_v2.pdf`.
  - After the `#dropzone` drop: waits for the link field value and the preview to carry `/y.pdf`.
- `tests/test_ui_page.py`
  - After `#stop-btn` (arm): waits for the text `Confirm stop` and `#stop-keep` shown; after `#stop-keep`: `Stop run` and `#stop-keep` hidden.
  - New helper `wait_calls_open(pg, key)`: the row's `.name-btn` aria-expanded true and its `.calls` block present; used after both `.name-btn` clicks.
- `tests/test_ui_explain.py`
  - After the first Why click: the Why button aria-expanded true and the `.why[data-why="understand"] .xtext` block present; after the second: that block gone; after `#axis-why`: the limits entry present.
- `tests/test_ui_honesty.py`
  - After each finding row click: the `+ .expanded .statement` block present.

A scan of every `tests/test_ui*.py` for any read between an action and the next wait found no other site (`tests/test_ui_delta_tab.py` and `tests/test_ui_export_bundle.py` are clean); the scan script stays in the worker's scratchpad.

## Proof

Each file's affected tests ran 10 times under six `yes` busy loops (killed by pid afterwards); results and gates are in the commit's report to the planner.
