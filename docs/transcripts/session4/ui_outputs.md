# UI outputs (decision #36): report

Branch `s4/ui-out` from eed6480, not pushed.
The finished-review page now has three actions above the verdict, in order: Download, Email, Share.
The drop screen also accepts a pasted https link to a PDF.

## What was built

Download saves one self-contained HTML file: the run's own `report.md` rendered as HTML by markdown-it, with `tokens.css` and `export.css` inlined, no script and no external resource.
`report.md` and `report.json` are separate downloads beside it, and "Open it in a new tab" shows the same file.
When `ui/chat.jsonl` exists, the export ends with a separate section headed "Reading-aid chat transcript (not part of the review)".
A replayed run carries the "replayed evidence" stamp in the export.
The export of `docs/live_runs/ui_flow_1` is 124,071 bytes.
Email sends the HTML file and `report.md` as two attachments through the SMTP server in `config/ui.yaml`, with the password read from `SIT_UI_SMTP_PASSWORD` at send time and never written.
Without the config or the variable, the button and field are disabled and the page says "Email is not configured: see config/ui.yaml" with what is missing.
Each attempt is logged to `runs/<id>/ui/outbox.jsonl` without the content.
Share shows `http://<lan-ip>:<port>/?run=<id>` with the sentence "Anyone on this network can open this link while this laptop serves it; there is no login, and the link dies when the server stops." when the server is bound to a non-loopback host.
A loopback server shows the restart line instead, for example `dra ui --host 0.0.0.0 --allow-remote --port 8791 --runs-dir docs/live_runs`.
A pasted link is checked (https only, no user info, the URL policy, every resolved address public, each redirect again, at most 5 redirects), downloaded with a 50 MB cap, required to start with `%PDF-`, and saved under `runs/<id>/ui/input/`, so the command on the page names the saved file.

## Deviations

The pasted PDF is saved under `runs/<id>/ui/input/`, where uploads already go, not under a shared `runs/input/`.
The export is rendered from `report.md`, the output of the one review renderer, not from the page's JavaScript; the page itself is unchanged.

## For the verifier

Read `research/audit/ui_outputs_editlog.md` for every edit, the mutation table and the gates.
Run `pytest -q tests/test_ui_outputs.py` (43 tests; the two Chromium tests skip without Playwright).
Look at `docs/design/ui_mockup/for_him_ui_outputs.png` (1440 px wide): tab 1 is the page served by `dra ui` on the committed run, tab 2 is the export opened from it.
No real mail was sent: the email tests use a fake SMTP server inside the test file.
Not verified: a real SMTP provider with STARTTLS, a real download over the internet, and the share link opened from a second device.
The DNS answer is resolved twice (check, then fetch), so DNS rebinding is not caught.
`markdown-it-py` and `playwright` are not declared in `pyproject.toml`.
