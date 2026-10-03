# Session 4: UI integration closeout

Branch `s4/ui-int`, worktree `/Users/malco/Desktop/SIT-wt/uiint`.
The last integration worker was stopped by a model-side safeguard at `4e31105` with the work almost done.
This closeout secured its last edits, fixed one test, ran the gates and wrote this record.
It made no model call and started no run.
The full table of commits and gates is in `research/audit/ui_integration_editlog.md`.

## What the four earlier commits delivered

`20c2343` makes the page read the agent's real `progress.jsonl` as the agent writes it, with recorded fixtures for a normal, a cut and a resumed run.
`e00a260` draws replay, cut and resume on the page and tests all three in Chromium.
`5f62065` moves the chat corpus from the user turn into the system prompt and cuts it to the report plus the ledger entries the findings cite.
`4e31105` commits the live run `ui_flow_1`, started from the page, with its two chat questions, without `progress.log`.

## What the closeout committed

`5cfa839` is the uncommitted `chat.py` change: a docstring addition only, recording the cache numbers of the system-prompt pair, and it matched the recorded usage.
`eb7558d` adds the two pictures `for_him_ui_live.png` and `for_him_ui_chat.png`.
`9c3494a` fixes the replay fixture in `tests/test_ui_page.py`, which failed with "input not found" when pytest ran from `/Users/malco`, because the rehearsal records its PDF relative to the repository; the fixture now passes the PDF by absolute path.

## The live run

`ui_flow_1` ended `completed_degraded` after 430 s with 22 findings, 8 model calls and a cost of 3.52 USD.
The earlier attempt `runs/ui_flow_1_attempt1` also ended `completed_degraded` (391 s, 22 findings, 4.80 USD, no cached tokens); it was left untouched and is not committed.

## The chat cache and the corpus decision

The first chat call wrote 55,069 cache tokens and read 613, for 0.4536 USD.
The second call wrote 705 and read 54,984, for 0.0272 USD.
With the corpus in the user turn, the earlier pair wrote it twice (71,451 then 70,511 tokens written, 943 read), because the CLI sets its cache breakpoint on the system prompt.
The decision stands: the corpus is the tail of the system prompt, the question alone is the user turn, and the schema is fixed, so the second question of a run reads the cache the first wrote.
`test_every_call_sends_the_same_prefix_so_the_second_reads_the_cache` in `tests/test_ui_chat.py` pins it.

## Gates

On `9c3494a`, every gate exited 0.
Ruff passed, pytest passed 1661 from the repo root and 1661 from `/Users/malco`, the selftest passed, `make smoke` passed 244, `make test` passed 1661, the leakage grep found no unresolved hit, and the robustness suite passed 159.

## For the verifier

Open the page against a fresh live run and check that each stage, shard and call is drawn as `progress.jsonl` records it, and that it settles on the report.
Check the chat guardrails: an invented citation is dropped and flagged, an unsupported answer shows no prose, the chat is off while a run is in progress, and the call and cost caps stop it.
Check the cut and resume views: a cut shard shows its disclosure ID and what it kept, and a resumed run continues on one sequence.
Check that `dra ui` refuses a non-loopback bind without its explicit flag.
The equality of the two recorded `system_sha256` values in the live chat log was not checked by script in this closeout; the 54,984-token cache read on the second call is the indirect evidence.
