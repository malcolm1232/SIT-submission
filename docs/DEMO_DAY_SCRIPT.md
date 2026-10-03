# Demo day script (lab §5.4), rehearse with a stopwatch

Written 2026-10-03 for the owner, from `docs/DEMO_DAY_RUNBOOK.md` (the procedure), `docs/ARCHITECTURE.md` §13 (the walkthrough) and the measurement notes cited on each number.
The runbook is the procedure and wins on any conflict; this file is the clock and the words.
The session is assumed to be about 40 minutes with a 10-minute live run inside it; the lab brief states no time limit (`docs/USER_DECISIONS.md` #34), so ask SIT for the slot length beforehand and shrink the walkthrough first if it is shorter.
The brief names three parts: "a walkthrough of the agent design, a live execution using a design artefact provided by SIT, and an on-the-spot modification exercise" (lab p.9 §5.4), and the agent must "take an updated version of the design artefact as inputs for it to re-assess" (lab p.3 §1.5).
Clock times are session time, `S+mm:ss`, from the moment the evaluators say go; run times are the agent's own clock, `run 0:00` at Start review.
Each block gives the clock, what to open, the one sentence to say, and the fallback.

## Measured numbers this script relies on

| Number | Value | Source |
|---|---|---|
| Full run, document only, demo profile | 382.3 s, $5.74 | `docs/live_runs/rehearsal_concurrent_1/MEASUREMENT.md`, `docs/live_runs/sit_sample_tools_1/MEASUREMENT.md` comparison table |
| Full run with tools on the lab's own sample | 428.0 s, $5.54, 112.0 s of slack | `docs/live_runs/sit_sample_tools_1/MEASUREMENT.md` "Result" |
| First draft finding on the console | 71 s (first DRAFT line of any kind 34 s); the runbook plans for about 125 s | `docs/live_runs/sit_sample_tools_1/MEASUREMENT.md` "Shards"; `docs/DEMO_DAY_RUNBOOK.md` §5 |
| Stage limits and deadline | stage 1 by 265 s, refine by 465 s, verdict call by 530 s, deadline 540 s | `config/profiles/demo.yaml` lines 27 and 42-44; runbook §5 |
| MCP cold starts | 34.4 s search, 29.3 s browser, 39.5 s research, 70.1 s document intelligence; 0.04 s warm | `research/robustness/mcp_probe_findings.md` "Latency" |
| `make smoke` | about 10 s offline | runbook header and §1 |
| Live modification targets | at most 3 min for config, 5 min for code | runbook §1 |
| Chat cap per review | 20 calls, $3.00 | `agent/sit_review_agent/ui/chat.py` `MAX_CALLS`, `MAX_COST_USD` |

## D-1: the day before

Opens: Window 2 (Terminal), the repo root.
Run `git status` (clean), `make test` (ruff and the whole suite), then `make smoke` (about 10 s, runbook §1).
Tag the freeze with `git tag demo-freeze`; after this only the live modifications are made (runbook §1).
Record the frozen v1 review of the SIT sample as `runs/sit_v1_frozen/` and the two backups of runbook §1 with the final code: `runs/demo_backup_sit_v1/` (the SIT sample) and `runs/demo_backup_delta/` (a v1 to v2 pair).
Check `dra replay runs/demo_backup_sit_v1` and `dra replay runs/demo_backup_delta` with Wi-Fi off: each must print the "Replayed evidence" stamp; a directory that lacks a file exits 2 and names it (runbook §1).
Set up the two Terminal windows: Window 1 (never on the projector) has tab 1 for `dra ui` and tab 2 for the keep-warm loop; Window 2 (on the projector, font at least 18 pt) is for commands, edits and the typed fallback.
Set up the browser: tab 1 the review page `http://127.0.0.1:8765`, tab 2 the repo on GitHub at `README.md`, tab 3 `docs/ARCHITECTURE.md` §13, tab 4 `docs/live_runs/QUALITY_COMPARISON.md`; the editor open on `config/`.
Print the one-page cheat sheet: the modification table below, the fallback words, and runbook §7.
Pack the charger and the phone for the hotspot; turn off sleep, power saving and notifications (runbook §2).
If it fails: a replay that refuses means the backup must be recorded again tonight; never take an older recording (`docs/USER_DECISIONS.md` #30).

## T-30 to T-3: on site

T-30: plug in the charger, join the venue Wi-Fi, run `dra preflight --no-warm --profile demo` (runbook §3).
T-10, Window 1 tab 1, off the projector: `export SIT_MCP_API_KEY=...` typed by hand, never `cat .env` (runbook §2); the agent does not read `.env` itself.
T-10, same tab: `dra ui --host 0.0.0.0 --allow-remote`; the page has no login, so anyone on this network can open it while it runs (runbook §5.2).
T-10, Window 2: `python3 scripts/probe_mcp_servers.py` touches all four servers (71.0 s in the owner's probe); its output file name is gitignored.
T-10, Window 1 tab 2: `dra preflight --warm --keep-warm 120 --profile demo`, left running; it keeps only the two enabled servers warm (`research/robustness/mcp_probe_findings.md` "Demo-day consequence").
T-5: open the backup review in the page, press Share, and put the network link on the projector so the evaluators can follow on their own laptops.
T-3: `dra preflight --profile demo` in Window 2: every line green, or the degraded mode named and accepted (runbook §3).
If it fails: Wi-Fi blocks `*.azurecontainerapps.io`, switch to the hotspot and rerun preflight; Share shows a restart line, the server is loopback-only, restart it with the line it shows.

## S+00:00 to S+01:00: opening

Opens: browser tab 2, `README.md`.
Says: "This agent reviews a design against its own objectives, anchors every finding to a quoted passage, and recommends a change only when it can justify one."
Does: start the stopwatch; say the plan: eight minutes of design, a ten-minute live run, the re-assessment, then your changes.

## S+01:00 to S+09:00: the walkthrough (ARCHITECTURE §13, 15 points, 32 s each)

| Clock | Opens | One sentence |
|---|---|---|
| 01:00 | `README.md` | It reviews against the design's own objectives and says "no change" when the design is fine. |
| 01:32 | `agent/sit_review_agent/states.py`, then `dra states` | Five stages, and the same graph printed from the code. |
| 02:04 | `agent/sit_review_agent/orchestrator.py` `_stage_1` | Understand, plan and four assess shards start together; research waits for the first two. |
| 02:36 | `config/agent.yaml` `assess.shards` | Four criterion groups, and a criterion added live becomes its own shard, a parallel call, not wall time. |
| 03:08 | `config/profiles/demo.yaml` | 540 s, three stage limits and two reserves, enforced inside each model call in `llm/runtime.py`. |
| 03:40 | `docs/live_runs/QUALITY_COMPARISON.md` | 3,372 s down to 382 s, 11 of 14 to 13 of 14 planted flaws, one document and one run per arm. |
| 04:12 | `agent/sit_review_agent/llm/gateway.py`, `llm/backend.py` | One gateway protocol, two backends, and the CLI backend needs no API key. |
| 04:44 | `agent/sit_review_agent/tools/gateway.py`, `tools/policy.py` | The tool layer stack, the URL policy and the argument sanitiser. |
| 05:16 | `config/tools.yaml`, `research/robustness/mcp_probe_findings.md` | Two servers on; browser off for its shared session, document intelligence off for rejecting input; a cold start costs 30 to 70 s. |
| 05:48 | `agent/sit_review_agent/ingest/anchor.py`, a `report.md` in `docs/live_runs/rehearsal_concurrent_1/` | Every quote is matched in code to a page and section. |
| 06:20 | `dra explain <finding-id> --run docs/live_runs/rehearsal_concurrent_1` | Anchors, evidence with its tool call, and the history across stages, in under 5 s. |
| 06:52 | `agent/sit_review_agent/phases/report.py` `not_assessed_verdict` | Only code can declare a design not assessed, and it says why. |
| 07:24 | `agent/sit_review_agent/state/checkpoint.py`, `replay.py` | A run resumes from its last checkpoint and replays exactly, stamped "replayed evidence". |
| 07:56 | `tests/robustness/results/robustness_summary.txt` | 87 scenarios, 55 passing offline, and the `--faults` flag that applies a schedule to a live run. |
| 08:28 | `harness/README.md`, `eval/prereg.yaml` | Planted flaws, a bounded matcher, a key-blind grader, a pre-registration, and unsigned-key scores marked exploratory. |

If it fails: a file will not open, read its row from the printed sheet and move on; never spend more than 32 s on one point.
If the evaluators interrupt with questions, drop points 6, 13 and 14 first; they are covered again in the live run.

## S+09:00 to S+19:00: the live run on SIT's artefact

S+09:00, opens: browser tab 1, the drop screen.
Does: drop their PDF on the drop zone, or paste their https link (`docs/USER_DECISIONS.md` #39: https only, public hosts, URL policy, at most 50 MB, must be a PDF).
Does: look at the title page and revision history; if it is an updated SIT design, go to the re-assessment block now and use this slot for it.
Does: choose profile `demo`, leave tools on, press Start review at about S+09:30 (run 0:00); the page shows the equivalent command.
Window 2: type `dra replay runs/demo_backup_sit_v1` and leave it unstarted (runbook §5).
Says: "The agent never saw this file; the page is the same `dra review` subprocess, so nothing here is outside the evaluated agent."
S+09:30 to S+13:55 (run 0:00 to 4:25, stage 1), points at the shard tracks: "Design content and research are kept apart; the four assessors read only the document and their own criteria, so they do not wait for the plan."
S+10:41 to S+11:35 (run 71 s to about 125 s): the first draft finding arrives in the right column, marked draft and unverified; say "IDs, ranks and severities can still change in refine."
While research runs, name its stop reason when it shows; on the lab sample it stopped after one of four iterations (`docs/live_runs/sit_sample_tools_1/MEASUREMENT.md` "Tools").
S+13:55 to S+17:15 (run 265 to 465 s, merge and refine): "The deadline is enforced inside each model call, so one slow call cannot take the report with it."
S+15:52 to S+16:38 (run 382 to 428 s, the two measured runs): the review appears; it must appear by S+18:30 (run 540 s) at the latest.
Opens: the verdict, its confidence and the counts strip; says "the verdict and confidence come first, every finding below carries its quote and page."
Opens: one finding expanded, then the Coverage tab, the same map as `dra coverage`, including "checked, no issue".
Opens: the chat, labelled "reading aid, not the review"; ask "Which finding has the most evidence?" and point at the verified citations.
Says: "The chat reads only the finished review, its citations are checked by the server, and it is capped at 20 calls."
Closes on the limitations section: degraded tools, unresolved anchors, and any cut stage.
If it fails: see the fallback block; the trigger is no draft finding by run 265 s (S+13:55).

## S+19:00 to S+27:00: the re-assessment of their updated artefact

S+19:00, opens: the drop screen.
Does: drop their updated PDF as the document and the version you reviewed as "previous version" (the run gets `--v1`), profile `demo`, Start review at about S+19:30.
CLI equivalent if the page fails: `dra review inbox/<updated>.pdf --profile demo --previous runs/sit_v1_frozen` for an update of the SIT sample (runbook §5).
Says: "This is the brief's re-assessment case: the agent takes the updated version and the earlier review and says what changed."
While it runs, open the editor on `config/` and start the modification block; the running review read its configuration when it started, so edits affect only the next run (not rehearsed).
S+26:00 to S+27:00 (run about 6:30 to 7:10, assumed equal to a plain run; no delta run of the concurrent design is measured): open the Delta tab.
Says, one line per group, in the page's order (`agent/sit_review_agent/ui/rundata.py` `DELTA_GROUPS`):
"Fixed means the update resolved an earlier finding, with the passage that shows it."
"Partially addressed means the update moved on it but the finding still stands in a smaller form."
"Unchanged means the finding is still open, with its original anchors."
"New in update covers what the update introduced, including regressions of things that were fine before."
If it fails: run past S+28:00 with no review, say the timing out loud and show `dra replay runs/demo_backup_delta`, stamped "replayed evidence".

## S+27:00 to S+36:00: the on-the-spot modification exercise

After every change: `make smoke` in Window 2 (about 10 s, offline; runbook §4) proves the config still loads and the pinned lines hold.
Then show it: the new value is in the next run's `effective_config.json` and manifest; a full rerun takes about 7 minutes, so start it at once and read the result during questions.
`--plan-only` shows a plan change without tools, but it still runs understand and plan, 124.2 s and 77.5 s on the lab sample (`docs/live_runs/sit_sample_tools_1/MEASUREMENT.md` "Stages"), so it is not under a minute.

| Request | Where (file, line) | Change | Under a minute? |
|---|---|---|---|
| A new criterion | `config/criteria.yaml`, append at the end | Six lines: `id`, `question`, `lab_ref`, `kinds`, `applies_to`, `research_hints`; it forms its own fifth shard (checked by loading the config, 2026-10-03) | Yes; a fifth shard's run time is not measured |
| A severity weight | none exists in the agent: severity is a closed enum the model assigns | Nearest knob: `config/agent.yaml` line 91 `report.min_severity: medium` moves low findings to the appendix | Yes; say plainly that there is no weight to change |
| The effort level | `config/profiles/demo.yaml` lines 19-24 (the profile overrides `config/agent.yaml` lines 4-9) | e.g. line 21 `assess: high` | Yes; `high` measured 780.3 s, past the 540 s deadline (`docs/live_runs/QUALITY_COMPARISON.md`) |
| A disabled tool | `config/tools.yaml` line 6 (search) or 9 (research), or no edit: `--disable-tool mcp-internet-search` | `enabled: false` | Yes; the report header lists the disabled tool |
| The deadline | `config/profiles/demo.yaml` line 27, or `--deadline N` on the command line | e.g. `deadline_seconds: 300` | Yes; at or below 530 s the three stage limits scale down and above 540 s they scale up, announced (300 s gives 147 / 258 / 294 s, 900 s gives 441 / 775 / 883 s; runbook §4, not rehearsed) |

A longer deadline lengthens the stages in proportion: above 540 s the runtime scales the three limits by the deadline over 540 s and announces it (`agent/sit_review_agent/llm/runtime.py` `effective_stage_limits`), so lines 42-44 of the profile need no edit.
Code changes offered only if time allows: the "two sources agree" stop rule, about 8 lines appended to `agent/sit_review_agent/stop_rules.py`, at most 5 minutes (runbook §4.2 row 2b).
Declined live, with the sentence to say:
"Another provider is a new gateway and a new evaluation, so I will show you the seam in `llm/backend.py` instead of changing it under you." (ADR-001)
"A new stop-reason code, a new output field or a new severity level changes the frozen schema, so it would fail the schema tests; I can show where it goes." (`spec/finding.schema.json`)
"A prompt edit breaks the prompt lock on purpose and voids every timing I have measured, so I would not ship it untested." (`prompts/PROMPTS.lock`)
"Browser automation shares one browser with no allowlist, and document intelligence rejected its only sample, so I keep them off." (`research/robustness/mcp_probe_findings.md`)
If it fails: `make smoke` red and the fix not obvious in a minute, `git checkout -- <file>`, rerun `make smoke`, and explain what the change would need (runbook §4).

## S+36:00 to S+40:00: questions and close

The modification rerun's review lands here; open it and point at the changed value in the manifest.
Says: "The outputs of today's runs go into the repository with their evidence, as the brief asks."
Does: offer the Download button for their copy; Email only if `config/ui.yaml` names a server.

## The fallback, any time

Rule: no draft finding by run 265 s (runbook §5), or no review by run 540 s, or no network at all.
Does: press Enter on the typed `dra replay runs/demo_backup_sit_v1` in Window 2, then walk `dra explain` and `dra coverage` on it while the live run finishes.
Says, exactly: "The live run is late, so while it finishes I am showing a recorded run of the SIT sample, replayed offline; it is stamped replayed evidence and it is not a review of your document."
A partial live review is shown first, with its disclosed cuts, and the replay only for depth (runbook §5).
A `not_assessed` verdict: show the replay, and rerun during questions with `--profile demo --deadline 900` if time allows; the stage limits scale up to 441 / 775 / 883 s (runbook §5, not rehearsed).
No internet at all: say the agent cannot review an unseen PDF offline, show both replays, and offer to run their PDF and send the outputs when the network returns (runbook §6).

## After the session

Copy each of today's run directories, without its `ui/` folder, into `outputs/lab_session/<date>/` (runbook §3; the chat log is not part of the review, `docs/design/ui_design.md` §6).
Commit them with a scoped `git add outputs/lab_session/<date>`, then push.
Check that `SIT-calebying` and `Makienhui-sit` are invited and have accepted under Settings, Collaborators; on 2026-10-03 neither was invited (`docs/SUBMISSION_GAPS.md`).
Stop the keep-warm loop and the `dra ui` server; unset the key in that shell.
