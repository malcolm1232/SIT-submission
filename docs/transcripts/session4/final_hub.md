# Session 4: final hub (2026-10-03)

The hub merged `s4/ui-out` (d3792bd), `s4/fixrefs` (d8274dc) and `s4/mcpfix` (3118a96) into `s4/final` from `9b5dd53`, in that order, each as a merge commit (23c7aaf, 5fa8ec4, d332ad5).
It verified each piece on the merged tree, fixed the seams and the test gaps it found, and brought the records up to date.
Every edit, conflict and mutation is in `research/audit/final_hub_editlog.md`.

## Verdict

Ready.
All five sections pass, every gate of section E exits 0, and nothing needed a behaviour judgement from the owner.

## Merge conflicts

The fixrefs merge conflicted in `phases/report.py` on the verdict line; the structured event of the UI side was kept with the INV-12 wording of the fixrefs side, and three golden console transcripts were updated by that string.
The replay fixture of `tests/test_ui_page.py` asserted that the rehearsal replays exactly; the ID rewrite changes one statement of that recording, so the fixture now allows differences only in the rewritten text fields.
The mcpfix merge conflicted in `agent/README.md` and `tests/robustness/README.md` (both sides kept) and in `phases/research.py` `_degrade` (it now both records and returns the degradation ID).

## A. UI: PASS, two tests FIXED

- PASS: `dra ui --host 0.0.0.0` without `--allow-remote` exits 2 with the reason.
- PASS: on port 8791 over `docs/live_runs`, the `ui_flow_1` page draws 22 findings, the same ID set as its `report.json`, with no page error (Playwright).
- PASS: the served `export.html` is byte-equal to `export.export_html` of the run; the export-equality test is killed by a renderer mutant.
- PASS: Email is disabled out of the box with "Email is not configured: see config/ui.yaml"; Share on loopback shows the restart line and the reason.
- PASS: the pasted-link guards (https only, public address, `%PDF-` body) each fail their tests when mutated.
- FIXED: the chat guardrails (unknown citation dropped, cap, off during a run) are killed by mutants, but `supported: false` with a resolving citation was untested; a new test kills that mutant.
- PASS: a replayed rehearsal served on port 8793 shows the "replayed evidence" stamp on the page and in the export; a live run shows none.
- PASS: the cut and resume views pass their browser tests on the fixture streams.
- PASS: a run started from the page by Playwright, on port 8792 with `transport: fake` over a scratch copy of the config, streamed four shard tracks (assess 1/4 to 4/4) and every stage to done, and "Open the review" rendered its 3 findings, equal to its `report.json`.
- FIXED: `markdown-it-py>=4.2.0` and `playwright==1.63.0` (dev) are declared in `pyproject.toml`; a fresh-venv resolve of `.[dev]` picks both.
- FIXED: `test_the_three_actions_in_a_browser` was flaky (it read the Download label before GET /outputs returned); it now waits for the outputs panel and passes with that response delayed by 1.5 s.

## B. Finding-ID mapping: PASS

- PASS: the merged-ID fixture (two merges, a withdrawal and a dropped draft across four shards) and the page-started concurrent fixture run cite no non-final finding ID in `report.json` or `report.md`, and INV-12 passes.
- PASS: with the ID map made the identity, the run exits 4 and INV-12 names the dangling references in `$.findings`, `$.sound_areas` and the report.md coverage; the file was restored from its backup.
- PASS: both committed rehearsal runs replay through the merged code; the only differences are `$.findings[17].statement` (concurrent_1) and `$.findings[20].statement` and `$.sound_areas[8].why_sound` (concurrent_high_1), each equal to the recording once finding IDs are masked, and the IDs they cited before were not findings of those reports.
- PASS: `run_manifest.extra.finding_ids` holds `shards`, `refine`, `verify`, `final`, `prior` and `rewrites` in every run checked.

## C. MCP session fix: PASS, one test FIXED

- PASS: a session closed after N calls is reopened once and the call retried once; an idle session over 60 s is reopened before the call; session errors alone never disable a tool; two genuine failures do (`tests/test_mcp_session_recovery.py`, 14 tests, including the real mcp client over an in-process server).
- PASS: DEG-002-style disclosures name the attempts, the failures with their error classes and the unverified questions; the stop reason is never `sufficient_evidence` with nothing answered.
- PASS: `report.md` takes its severity count from the findings, prints the version once and keeps bullet lists.
- Mutants of the reopen, the idle check, the disable limit, the genuine-failure rule, the stop reason, the count, the version and the list block are all killed.
- FIXED: the bullet-glyph normalisation survived its mutant; a new test kills it.
- PASS: NET-06 passes in the robustness runner.

## D. Cross-branch seams: PASS, two tests added

- PASS: a new test runs one review through both rewrites (a wrong "Three high-severity" count, a list and non-final IDs in the verdict); `report.md` says "One high-severity", keeps the list and cites no dangling ID, and the test is killed by the count mutant and by the list mutant.
- PASS: the UI export of each run checked contains its `report.md` rendered by the same renderer.
- PASS: the MCP fix added no event type: every literal event type in the agent is in the schema enum, the session reopen lines are `tool_status` records, and a new test validates them in `progress.jsonl` against `spec/progress_event.schema.json`; 600 recorded records across four run roots validate.

## E. Gates on the final tree: PASS

- `ruff check agent harness tests`: exit 0.
- `pytest -q` from the repository root: exit 0, 1835 passed; from `/Users/malco`: exit 0 after the flake fix.
- `sit-review selftest`: exit 0; `make smoke`: exit 0 (249 passed); `make test`: exit 0.
- Robustness runner with the CSV regenerated: exit 0, 161 tests; 88 P0 rows, 56 PASS, 0 FAIL, 32 BLOCKED, NET-06 PASS.
- `spec/convert_answer_keys.py --tier synthetic --check --verify-anchors`: exit 0, 45 flaws across 3 keys, 0 failed.
- Prompt lock: up to date (bundle 6f0ee28ab9ac), exit 0; leakage grep (default mode): exit 0, 0 unresolved; `spec/validate_examples.py`: exit 0.
- `pytest -q tests/test_export_public_snapshot.py`: 65 passed.
- The dry export into the scratchpad left out every answer key, transcript, `llm.jsonl`, `tools.jsonl`, UI chat log, outbox, `progress.log`, cassette, stream fixture, `sit_sample` run and `eval/blind` file (0 of each in 459 exported files).
- Its scan exits 1 on the same two `home-path` findings in `tests/test_export_public_snapshot.py` that it reports at `9b5dd53`; the three new false positives from the merges were reviewed and allowed, and the test addresses moved to `.test`.
- No em dash on added lines since `9b5dd53` outside recorded run directories; every commit is `malcolm1232` with no co-author or agent line; no secret-shaped string in the added lines.

## Refused or not done

No tool call was refused.
No live model call, no MCP host and nothing on the SIT Memory Platform PDF were touched.

## Not verified

The chat against the real `claude` client, a real SMTP server, a share link opened from a second device, and the MCP session fix against the live SIT servers were not verified.
The page-started run used the fake gateway, so its stages finished instantly and no track was seen in the "running" state.
DNS rebinding on the pasted link remains open, as the UI outputs report says.

## For the next session

The owner should make one with-tools run on the lab document with the MCP key to confirm the session fix live, and decide on the two `home-path` findings before any public snapshot.
The severity-count rewrite should agree the noun with the new number ("One high-severity finding").
Row #36 covers the three outputs; whether the pasted-link fetch, which cites #36, needs its own decision row is for the planner.
