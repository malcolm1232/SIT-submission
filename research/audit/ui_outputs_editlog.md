# UI outputs (decision #36) edit log

The three output actions of a finished review in `dra ui`, and the pasted link on the drop screen, on branch `s4/ui-out` from eed6480.
Baseline before the first edit: ruff clean, pytest 1656 passed and 5 skipped (Playwright was not installed in the fresh venv; with it installed the 5 browser tests run).
After: ruff clean, pytest 1704 passed, 0 failed, 0 skipped (Playwright 1.63.0 installed by hand in the worktree venv; it is not a declared dev dependency).
The export imports `markdown_it` (markdown-it-py 4.2.0), which arrives through typer and rich but is not declared in `pyproject.toml` (not an owned file): declaring it is a follow-up.
Every behaviour had a failing test first; every guard was mutated after its commit and restored from a `cp` backup.

## Edits

1. `agent/sit_review_agent/ui/export.py` (new): `export_html(run_dir, replayed=...)` renders the run's own `report.md` with markdown-it (CommonMark, tables on, raw HTML escaped, images off) inside a page with `tokens.css` and `static/export.css` inlined.
   No script, no external resource; a replayed run carries the "replayed evidence" stamp; `ui/chat.jsonl`, when present, follows under "Reading-aid chat transcript (not part of the review)".
   There is no second renderer of the review: the only renderer remains `report.render.render_markdown`, which wrote `report.md`.
2. `agent/sit_review_agent/ui/static/export.css` (new): the export's layout, tokens only, no motion, print rules.
3. `agent/sit_review_agent/ui/server.py`: routes `GET /runs/<id>/export.html` (inline, `?download=1` as an attachment named `<id>_review.html`), `GET /runs/<id>/report.md` and `/report.json` (attachments), `GET /runs/<id>/outputs` (export size, whether a transcript exists, email status, share info), `POST /runs/<id>/email`.
   `POST /runs` accepts `document_url` instead of a file (both together is a 400).
   `UIState` gains `smtp`, `smtp_detail`, `bind_host`, `port`, `ui_args`, `lan_ip`, `url_policy`, `fetch_transport`, `resolve`; `build_state` loads `config/ui.yaml` and the URL policy; `serve` records host, port, `--runs-dir` and `--config`.
   `/meta` gains `link_max_mb`.
4. `config/ui.yaml` (new): `email` with `host`, `port`, `starttls`, `username`, `from`; shipped empty, so Email is off by default.
   The agent's config loader reads only its named files, so this file is outside the effective config and its hash.
5. `agent/sit_review_agent/ui/mail.py` (new): `load_smtp` (the loader of `config/ui.yaml`), `status`, `send`.
   The password is read from `SIT_UI_SMTP_PASSWORD` at the moment of sending and never written; `starttls: true` with a server that does not offer STARTTLS is a failed send, never clear text.
   Each attempt is logged to `runs/<id>/ui/outbox.jsonl` (time, recipient, sender, SMTP host, attachment names and sizes, message size, result, error), never the content; a password inside an error text is replaced.
6. `agent/sit_review_agent/ui/share.py` (new): `lan_ipv4` (the IPv4 of the default-route interface via an unsent UDP connect, else the host name's addresses), `share_info` (network link with the fixed sentence, the loopback restart line, or "no address").
7. `agent/sit_review_agent/ui/fetch.py` (new): `check_link` and `fetch_pdf` for a pasted link: https only, no user info, the URL policy through `tools.policy.check_urls`, every resolved address public, each redirect checked again (at most 5), 50 MB cap on the declared length and while streaming, body must start with `%PDF-`.
   The file name is the link's last path segment made safe, ending in `.pdf`.
8. `agent/sit_review_agent/ui/launcher.py`: `LaunchSpec.source_url`, written to `ui/launch.json`.
9. `agent/sit_review_agent/ui/static/index.html`, `app.js`, `app.css`: the outputs section above the review (Download, Email, Share rows, hidden until `/outputs` answers), the link field and its error line in the drop zone, a dropped link fills the field, the command preview names the file the server will save.
10. `tests/test_ui_outputs.py` (new, 43 tests): export against `report.json` and `report.md`, self-containment, injection, transcript, replay stamp, routes; email with a local fake SMTP server; share modes; `serve` wiring; pasted-link policy, redirects, cap, non-PDF; two Chromium tests.
11. `agent/README.md` one line; `docs/DEMO_DAY_RUNBOOK.md` §5.2; `docs/design/ui_mockup/for_him_ui_outputs.png`.

## Mutations (each removed after its commit, restored from a `cp` backup, `git status` clean after)

| Guard | Mutation | Result |
|---|---|---|
| Export equals the renderer | `review_html` renders `report.md` with "### FND" rewritten | `test_the_export_is_report_md_rendered_...` failed |
| Email disabled without the password | `status` skips the `SIT_UI_SMTP_PASSWORD` check | `test_email_is_shown_disabled_...` failed |
| Email disabled without the config | `status` skips the `cfg is None` branch | `test_email_is_shown_disabled_...` failed |
| Email disabled on the page | `app.js` enables the field and button whatever the status | `test_the_three_actions_in_a_browser` failed |
| Share text when loopback | `share_info` skips the loopback branch | `test_a_loopback_server_shows_the_restart_line_not_a_link` failed |
| URL policy domains | `check_link` ignores `check_urls` | `test_the_url_policy_domains_apply_to_a_pasted_link` failed |
| Public addresses only | the non-global address check off | 6 tests failed (direct and redirect) |
| https only | `http` accepted | 2 tests failed |
| Size cap while streaming | the streamed check off | `test_the_size_cap_stops_a_large_download` failed |
| Size cap on the declared length | the declared check off | `test_the_size_cap_stops_a_large_download` failed |

## Gates (worktree venv, Python 3.13)

`ruff check agent harness tests` exit 0; `pytest -q` 1704 passed, 0 failed; `sit-review selftest` exit 0; `make smoke` exit 0 (248 passed); `make test` exit 0 (1704 passed); `scripts/leakage_grep.py` exit 0 (PASS).
