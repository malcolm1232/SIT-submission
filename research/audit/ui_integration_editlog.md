# UI integration: edit log

Branch `s4/ui-int`, worktree `/Users/malco/Desktop/SIT-wt/uiint`.
The previous workers built the integration up to `4e31105`; the last of them was stopped by a model-side safeguard with an uncommitted docstring change and two uncommitted pictures.
This closeout secured those, fixed one test that depended on the working directory, and ran the gates.
The closeout made no model call and started no run.

## Commits

| Commit | Worker | Files | What |
|---|---|---|---|
| `20c2343` | previous | `ui/events.py`, `ui/rundata.py`, `ui/server.py`, `ui/static/*`, `phases/assess.py`, `phases/research.py`, `tests/fixtures/ui/*` | The page reads the agent's real `progress.jsonl` as written; the fixtures (normal, cut, resume) are recorded by `tests/fixtures/ui/record_fixtures.py`. |
| `e00a260` | previous | `ui/static/app.js`, `ui/static/app.css`, `tests/test_ui_page.py`, mockup pictures | Replay, cut and resume drawn on the page and tested in Chromium. |
| `5f62065` | previous | `ui/chat.py`, `tests/test_ui_chat.py`, `tests/test_ui_page.py`, `ui/static/*` | The chat corpus moves from the user turn into the system prompt and is cut to what the findings cite; the question alone is the user turn. |
| `4e31105` | previous | `docs/live_runs/ui_flow_1/` (28 files) | The live run `ui_flow_1`, started from the page, with its two chat questions; `progress.log` left out. |
| `5cfa839` | closeout | `ui/chat.py` | Docstring only: records the cache numbers of the system-prompt pair next to those of the user-turn pair. |
| `eb7558d` | closeout | `docs/design/ui_mockup/for_him_ui_live.png`, `for_him_ui_chat.png` | The two pictures of the live run and the chat on the page. |
| `9c3494a` | closeout | `tests/test_ui_page.py` | The replay fixture passes the rehearsal's PDF by absolute path; from `/Users/malco` it failed with "input not found" (4 errors), because the recording holds the input relative to the repository. |

## The uncommitted `chat.py` change

A three-line docstring addition, no code: in the system prompt the second call read 54,984 cached tokens and wrote 705 (0.45 then 0.03 USD).
The numbers match the usage recorded in `docs/live_runs/ui_flow_1/ui/chat.jsonl` (read by script, numbers only), and `tests/test_ui_chat.py` passed (17), so it was committed as it stood.

## Live run `ui_flow_1` (from the manifest and `report.json`, by script)

| Field | Value |
|---|---|
| Outcome | `completed_degraded` |
| Wall time | 430 s (manifest `timestamps`) |
| Findings | 22 |
| Model calls in `llm.jsonl` | 8 |
| Cost | 3.519921 USD (manifest `usage.cost_usd`) |
| Tokens | 136,549 input, 119,778 output, 160,125 cached |
| Fallback events | 0 |

`runs/ui_flow_1_attempt1` was not touched; its manifest also says `completed_degraded`, 391 s, 22 findings, 4.799856 USD, 0 cached tokens.
It is not committed.

## Chat cache (from `ui/chat.jsonl`, numbers only)

| Call | Cache write | Cache read | Output | Cost (USD) |
|---|---|---|---|---|
| 1 | 55,069 | 613 | 647 | 0.4536 |
| 2 | 705 | 54,984 | 529 | 0.0272 |

Both answers have 0 dropped citations (14 and 7 citations kept).
The earlier user-turn pair wrote the corpus twice (71,451 then 70,511 tokens written, 943 read); the corpus now rides in the system prompt, which is where the CLI sets its cache breakpoint, and is cut to the report without provenance hashes plus only the ledger entries the findings cite.

## Prefix pin

`system_for` builds the system prompt from `SYSTEM_PROMPT` plus the run's corpus only, `prompt_for` wraps the question alone, and the schema is the constant `ANSWER_SCHEMA`.
`tests/test_ui_chat.py::test_every_call_sends_the_same_prefix_so_the_second_reads_the_cache` pins it: same system text and schema on both calls, different prompts, equal `system_sha256` in the log, and argv that differs only in the budget cap.
No test was added.

## Gates on `9c3494a` (one per call, exit codes read)

| Gate | Exit | Result |
|---|---|---|
| `ruff check agent harness tests` | 0 | all checks passed |
| `pytest -q` from the repo root | 0 | 1661 passed |
| `pytest -q` from `/Users/malco` | 0 | 1661 passed (4 errors before `9c3494a`) |
| `sit-review selftest` | 0 | passed in 0.4 s |
| `make smoke` | 0 | 244 passed |
| `make test` | 0 | 1661 passed |
| `scripts/leakage_grep.py` | 0 | no unresolved hit in a gated area |
| `pytest tests/robustness` | 0 | 159 passed |

## Not done

A first attempt to inspect the shape of `ui/chat.jsonl` (field names and lengths) was stopped by a safety classifier and was not repeated; the cache numbers above come from that one output.
The equality of the two recorded `system_sha256` values in the live log was therefore not checked by script; the cache read of 54,984 tokens on the second call is the indirect evidence.
