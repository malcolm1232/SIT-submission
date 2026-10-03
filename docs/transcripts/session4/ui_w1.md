# UI workstream W1: structured progress events

Date: 2026-10-03.
Branch `s4/ui1` from `70bd658`; commits `4e91e52`, `efbec74`, `b3111a6` and the edit log and report commit; not pushed.
Authority: `docs/design/ui_design.md` section 5, and the owner's ruling "1. Shape A as above. chat with opus. and build as recommended."
Edit log: `research/audit/ui_w1_editlog.md`.

## What was built

Every progress line the agent prints is now also a typed event with structured fields, so the page never parses a message.
Four new events have no console line: `run_started`, `call_opened`, `call_closed` and `run_finished`.
Each run appends its events to `runs/<id>/progress.jsonl` beside `progress.log`, one JSON object per line, written and closed per event so a reader can tail it live.
The console and `progress.log` are byte for byte what they were: three fixture runs are compared line for line with console lines recorded on `70bd658` before any product edit.
The record format is `spec/progress_event.schema.json` (version 1), documented in `agent/README.md` section "Progress events", and every record of every fixture run in the tests validates against it.

## The items

1. Done: every emit site in `orchestrator.py`, `phases/*.py`, `llm/runtime.py` and `llm/claude_code.py` gives its event a type and fields (call ID, stage, shard index and name, item index, severity, title, thinking tokens, items, chars, counts, stop-rule code, the cut call and what it kept); no fixture event is left as an untyped `status` line; the console-unchanged test is `tests/test_progress_console.py`.
2. Done: `call_opened` and `call_closed` for every logical model call on every backend, from `progress.CallEventsGateway`, the outermost LLM layer; opened carries call ID, stage, shard, shard name, purpose, attempt and iteration; closed adds the outcome, the error class, wall seconds, usage as measured or `null` with `usage_status: unknown`, and for a cut the items it kept.
3. Done: `run_started` is the first record of a run (run ID and directory, mode, review mode, documents, profile, model, backend, transport, deadline, the stage limits the runtime uses, the reserve, the criteria, the shard groups, the enabled phases) and `run_finished` the last (outcome from the manifest, exit code, report paths, run-clock seconds, cost and whether it is a lower bound), also on a setup failure and on resume.
4. Done: `progress.jsonl` with `seq`, `t`, `run_s`, `type` and `fields`; append-only, closed per event, continued by a resume; gitignored; no model prose (a line that quotes model text is written with a `public` message of codes and counts, and a draft keeps only a finding's title and severity; a test scans every long string of every model answer of two fixture runs and finds none in the file); the schema is validated in the tests.
5. Done: a concurrent fixture run on the fake gateway (stage 1 calls held open together, as a live run overlaps them) shows `run_started` first, all four shard `call_opened` before any `call_closed`, `shard_drafted` events with shard and per-draft severity, the milestones in order, and `run_finished` last with the report path; a deadline-cut run shows `shard_cut` with the cut call, one kept finding and its title, and the cut call closing as `cut` with `kept_items` 1.
6. Done: `dra replay` of a recorded fixture run writes the same event sequence (types, phases, kinds, messages and fields), apart from clock values (`t`, `run_s` and clock-measured durations) and the run's identity (run ID, paths, mode, transport, cost).
7. Done: sixteen mutations, each removing one claim, each failed its test, and each file was restored from a `cp` backup with `git diff` clean afterwards; the table is in the edit log.

## Results

Tests: 1576 passed (1557 at the base, 19 new).
Gates, exit codes read: `ruff check agent harness tests` 0, `pytest -q` 0, `sit-review selftest` 0, `make smoke` 0, `make test` 0, `python scripts/leakage_grep.py` 0.
`leakage_grep.py --strict` exits 1 on hits in files this workstream did not touch; it is not the gate.
No tool call was refused.

## Not verified

The events of a live `claude_code` run were not seen: the Claude Code path was checked on a scripted stream through the real gateway only, and the Anthropic API path not at all beyond the shared ID hook.
The run clock of a live run (`run_s`) and wall seconds of real calls were not seen; the fixture runs use a virtual clock.
In a replay, `call_opened` is written when the recorded call is served, just before `call_closed`, because the replay gateway takes its IDs from the recording; a page driven by a replay shows each call as opened and closed at once.
The UI page itself (W2) has not read this stream yet.
`docs/live_runs/` run directories recorded before this branch have no `progress.jsonl`.

## For the other workstream

W2 reads `runs/<id>/progress.jsonl` only; it never needs `effective_config.json` to draw the run.
Read it line by line from the start (a page opened late or reconnected replays the whole file), then tail it; each line is one complete JSON object.
The contract is `spec/progress_event.schema.json`; validate a line against it in tests, and treat an unknown `type` as a plain status line (`message` only), so a later additive type does not break the page.

The record envelope, every key always present:

- `v`: 1.
- `seq`: 1, 2, 3 ... in file order; a resumed run appends to the same file and continues the numbers, and its first new record is a second `run_started` with `resumed: true`.
- `t`: seconds since the sink's first event, which is the `[mm:ss]` the terminal prints.
- `run_s`: run-clock seconds, the clock the stage limits use (resume-adjusted); `null` before the orchestrator starts the run clock (setup events).
- `type`: the event type below.
- `phase`: the terminal's phase column (`ingest`, `understand`, `plan`, `research`, `assess`, `refine`, `verify`, `report`, `stage_1`, `run`, `model` or `tools`).
- `kind`: `step`, `wait`, `warn`, `done` or `draft`, the terminal's marker.
- `console`: true when the event is also a terminal line; the status feed shows exactly the records with `console: true`, in order, and `message` is the terminal's message text (with model text left out where the terminal quotes it).
- `message`: text built by code; never a model's prose.
- `fields`: the event's data; the keys each type always has are listed in the schema.

How the page should use them:

- Draw the limits from `run_started.fields`: `deadline_s`, `deadline_active`, `stage_limits_s` (`stage_1_end`, `refine_end`, `verdict_end`, absolute run-clock seconds, already scaled when `stage_limits_scaled`), and the four tracks from `shards` (`index`, `name`, `criteria`).
- A stage 1 row per member: `phase_started` / `phase_done` with `fields.stage == "stage_1"` and `phase` the member; assess shards by `shard_started`, `shard_drafted`, `shard_cut`, `shard_failed`, `shard_truncated`, `shard_declined` (all with `shard`, `shard_name`, `shards`); the call ID of a track from `call_opened` with the same `shard` (assess) or `phase` (other members).
- A cut track: `shard_cut.fields` has `call_id`, `cut_at_s` (run clock), `kept` and `kept_drafts`; a cut model call outside assess is `call_cut` (`kept_items`, `kept`); the matching `call_closed` has `outcome: "cut"`.
- The skipped research and its degradation: `research_skipped`, `research_doc_only`, or `phase_done` / `stop_rule`; the degradation ID itself is in `report.json`, not in the stream.
- The draft feed: `draft_item` (live backend, one per streamed item; `item`, `index`, `call_id`, `shard`, and for a finding `severity`, `kind`, `title`) and `shard_drafted.fields.drafts` (every backend, once per shard: `index`, `kind`, `severity`, `title`); both are unverified drafts.
- Open calls: `call_opened` / `call_closed` by `call_id`, and the 10 s `call_status` line (`calls`: `call_id`, `phase`, `label`, `thinking_tokens`, `items`, `chars`).
- Milestones: `milestone` with `name` (`intent`, `plan`, `merged`, `verified`) and its counts.
- The end: `run_finished` is the last record of a run (`outcome`, `exit_code`, `report_md`, `report_json`, `partial_report`, `wall_s`, `cost_usd`, `cost_is_lower_bound`); a run that is still going has none; a resumed run writes a new `run_started` and later its own `run_finished`.
- A replay writes the same sequence; its `run_started.fields.mode` is `replay`, which is where the "replayed evidence" stamp comes from.

One example line per event type follows.
The lines marked recorded were written by fixture runs of this branch (the selftest fixture, the cut and fail-and-resume scenarios, the concurrent cut run and the scripted Claude Code stream), with the temporary run directory shown as `runs/`; the lines marked illustrative were written by hand for types no fixture run reaches, and every one of them validates against the schema.

### Example lines

`anchor_repair` (recorded):

```json
{"v":1,"seq":75,"t":0.0,"run_s":0.0,"type":"anchor_repair","phase":"verify","kind":"step","console":true,"message":"2 anchor(s) unresolved; one repair turn","fields":{"unresolved":2,"repair":true,"slack_s":3420.0}}
```

`anchors_verified` (recorded):

```json
{"v":1,"seq":78,"t":0.0,"run_s":0.0,"type":"anchors_verified","phase":"verify","kind":"step","console":true,"message":"anchors: 6 resolved, 1 repaired, 1 unresolved; 3 findings verified, 1 unverified","fields":{"anchors":8,"resolved":6,"repaired":1,"unresolved":1,"findings_verified":3,"findings_unverified":1,"repair_call_id":"llm-0011"}}
```

`assess_started` (recorded):

```json
{"v":1,"seq":12,"t":0.0,"run_s":0.0,"type":"assess_started","phase":"assess","kind":"step","console":true,"message":"assessing 11 criteria in 4 concurrent shard(s)","fields":{"criteria":11,"shards":4,"finished_before":[],"groups":[{"index":1,"name":"intent_and_fitness","criteria":["design_intent","fitness_for_objectives","decision_preservation"]},{"index":2,"name":"requirements_and_consistency","criteria":["requirement_completeness","internal_consistency","verifiability"]},{"index":3,"name":"claims_and_assumptions","criteria":["claims_and_external_constraints","assumptions_and_dependencies"]},{"index":4,"name":"risk_and_operations","criteria":["security_and_privacy","scalability_and_failure_modes","operability_and_governance"]}]}}
```

`call_closed` (recorded):

```json
{"v":1,"seq":14,"t":0.0,"run_s":0.0,"type":"call_closed","phase":"understand","kind":"done","console":false,"message":"llm-0001 closed: ok","fields":{"call_id":"llm-0001","stage":"stage_1","shard":null,"shard_name":null,"purpose":"understand","attempt":0,"iteration":0,"outcome":"ok","error":null,"wall_s":0.0,"usage":{"input_tokens":1000,"output_tokens":200,"cache_creation_input_tokens":0,"cache_read_input_tokens":0},"usage_status":"measured","stop_reason":"end_turn","model":"claude-opus-5-5","attempts":1,"resumed":false}}
```

`call_opened` (recorded):

```json
{"v":1,"seq":13,"t":0.0,"run_s":0.0,"type":"call_opened","phase":"understand","kind":"step","console":false,"message":"llm-0001 opened","fields":{"call_id":"llm-0001","stage":"stage_1","shard":null,"shard_name":null,"purpose":"understand","attempt":0,"iteration":0}}
```

`call_status` (recorded):

```json
{"v":1,"seq":2,"t":0.0,"run_s":null,"type":"call_status","phase":"assess","kind":"wait","console":true,"message":"1 open call: llm-0001 assess: starting","fields":{"calls":[{"call_id":"llm-0001","phase":"assess","label":"","thinking_tokens":0,"items":0,"chars":0}]}}
```

`cost_lower_bound` (recorded):

```json
{"v":1,"seq":84,"t":0.0,"run_s":0.0,"type":"cost_lower_bound","phase":"report","kind":"warn","console":true,"message":"cost ~$0.09 is a lower bound: 1 model call with unrecorded usage (assess, deadline cut); their tokens and cost are not in the totals","fields":{}}
```

`document_ingested` (recorded):

```json
{"v":1,"seq":5,"t":0.0,"run_s":0.0,"type":"document_ingested","phase":"ingest","kind":"step","console":true,"message":"DOC-design (under_review): 19 pages, 5 sections, 1 requirement IDs, text sha256 fa118ac6b54a","fields":{"doc_id":"DOC-design","role":"under_review","pages":19,"sections":5,"requirement_ids":1,"sha256_text":"fa118ac6b54a","title":"Campus Room Booking Service - Detailed Design"}}
```

`draft_item` (recorded):

```json
{"v":1,"seq":7,"t":0.0,"run_s":null,"type":"draft_item","phase":"assess","kind":"draft","console":true,"message":"draft finding 1 (unverified; llm-0001 assess): [high] Finding 1","fields":{"item":"finding","list":"findings","index":1,"call_id":"llm-0001","shard":3,"id":"FND-001","severity":"high","title":"Finding 1"}}
```

`intent_ready` (recorded):

```json
{"v":1,"seq":15,"t":0.0,"run_s":0.0,"type":"intent_ready","phase":"understand","kind":"done","console":true,"message":"intent: 2 objectives, 1 constraints; registry: 1 approved_decision (frozen, sha256 857bd91b5f47)","fields":{"objectives":2,"constraints":1,"registry_entries":1,"registry_sha256":"857bd91b5f47"}}
```

`mcp_warmup` (recorded):

```json
{"v":1,"seq":2,"t":0.0,"run_s":null,"type":"mcp_warmup","phase":"run","kind":"step","console":true,"message":"no MCP warm-up for this tool transport; skipped","fields":{"status":"none"}}
```

`milestone` (recorded):

```json
{"v":1,"seq":48,"t":0.0,"run_s":0.0,"type":"milestone","phase":"understand","kind":"done","console":true,"message":"milestone intent: intent ready, registry 1 entries","fields":{"name":"intent","registry_entries":1}}
```

`phase_done` (recorded):

```json
{"v":1,"seq":6,"t":0.0,"run_s":0.0,"type":"phase_done","phase":"ingest","kind":"done","console":true,"message":"done in 0.0s","fields":{"stage":"ingest","seconds":0.0,"stopped_at_limit":false,"stage_closed":false}}
```

`phase_started` (recorded):

```json
{"v":1,"seq":4,"t":0.0,"run_s":0.0,"type":"phase_started","phase":"ingest","kind":"step","console":true,"message":"started","fields":{"stage":"ingest"}}
```

`plan_criteria_added` (recorded):

```json
{"v":1,"seq":18,"t":0.0,"run_s":0.0,"type":"plan_criteria_added","phase":"plan","kind":"warn","console":true,"message":"plan left out 10 criteria; added document-only questions for: design_intent, fitness_for_objectives, requirement_completeness, internal_consistency, security_and_privacy, scalability_and_failure_modes, assumptions_and_dependencies, verifiability, decision_preservation, operability_and_governance","fields":{"criteria":["design_intent","fitness_for_objectives","requirement_completeness","internal_consistency","security_and_privacy","scalability_and_failure_modes","assumptions_and_dependencies","verifiability","decision_preservation","operability_and_governance"]}}
```

`plan_question` (recorded):

```json
{"v":1,"seq":20,"t":0.0,"run_s":0.0,"type":"plan_question","phase":"plan","kind":"step","console":true,"message":"RQ-001 [none] design_intent","fields":{"question_id":"RQ-001","capability":"none","criterion_id":"design_intent","needs_external":false}}
```

`plan_ready` (recorded):

```json
{"v":1,"seq":19,"t":0.0,"run_s":0.0,"type":"plan_ready","phase":"plan","kind":"done","console":true,"message":"plan: 11 questions (1 need external research), 0 criteria skipped","fields":{"questions":11,"external":1,"criteria_skipped":0,"fallback":null}}
```

`plan_started` (recorded):

```json
{"v":1,"seq":11,"t":0.0,"run_s":0.0,"type":"plan_started","phase":"plan","kind":"step","console":true,"message":"planning the review over 11 criteria (capabilities: search)","fields":{"criteria":11,"capabilities":["search"]}}
```

`refine_started` (recorded):

```json
{"v":1,"seq":69,"t":0.0,"run_s":0.0,"type":"refine_started","phase":"refine","kind":"step","console":true,"message":"refining 4 merged findings as one global reviewer (revisions only)","fields":{"findings":4}}
```

`refined` (recorded):

```json
{"v":1,"seq":72,"t":0.0,"run_s":0.0,"type":"refined","phase":"refine","kind":"done","console":true,"message":"refined: 3 revised, 1 unchanged, 0 merged, 0 withdrawn; 4 findings","fields":{"call_id":"llm-0010","revised":3,"unchanged":1,"merged":0,"withdrawn":0,"findings":4}}
```

`report_written` (recorded):

```json
{"v":1,"seq":86,"t":0.0,"run_s":0.0,"type":"report_written","phase":"run","kind":"done","console":true,"message":"report: runs/pc-selftest/report.md","fields":{"report_md":"runs/pc-selftest/report.md","report_json":"runs/pc-selftest/report.json"}}
```

`research_iteration` (recorded):

```json
{"v":1,"seq":53,"t":0.0,"run_s":0.0,"type":"research_iteration","phase":"research","kind":"step","console":true,"message":"iteration 1/4: 1 open question(s), 30 tool call(s) left","fields":{"iteration":1,"max_iterations":4,"open_questions":1,"tool_calls_left":30}}
```

`research_started` (recorded):

```json
{"v":1,"seq":52,"t":0.0,"run_s":0.0,"type":"research_started","phase":"research","kind":"step","console":true,"message":"1 question(s) need external evidence; 2 tool(s) offered","fields":{"questions":1,"tools":2}}
```

`research_stopped` (recorded):

```json
{"v":1,"seq":63,"t":0.0,"run_s":0.0,"type":"research_stopped","phase":"research","kind":"done","console":true,"message":"research stopped: sufficient_evidence (sufficient_evidence); 1/1 answered, 2 tool call(s), 2 ledger entr(y/ies)","fields":{"code":"sufficient_evidence","detail":"sufficient_evidence","answered":1,"questions":1,"tool_calls":2,"ledger_entries":2}}
```

`run_dir` (recorded):

```json
{"v":1,"seq":3,"t":0.0,"run_s":null,"type":"run_dir","phase":"run","kind":"step","console":true,"message":"run pc-selftest: runs/pc-selftest","fields":{"run_id":"pc-selftest","run_dir":"runs/pc-selftest"}}
```

`run_error` (recorded):

```json
{"v":1,"seq":46,"t":0.0,"run_s":0.0,"type":"run_error","phase":"understand","kind":"warn","console":true,"message":"error (LLMConnectionError, exit 3); state saved; resume with `sit-review resume runs/pc-fail`","fields":{"error":"LLMConnectionError","exit_code":3,"resumable":true,"resume":"sit-review resume runs/pc-fail"}}
```

`run_finished` (recorded):

```json
{"v":1,"seq":87,"t":0.0,"run_s":0.0,"type":"run_finished","phase":"run","kind":"done","console":false,"message":"run pc-selftest finished: exit 0","fields":{"run_id":"pc-selftest","outcome":"completed_degraded","exit_code":0,"report_md":"runs/pc-selftest/report.md","report_json":"runs/pc-selftest/report.json","partial_report":null,"wall_s":0.0,"cost_usd":0.096,"cost_is_lower_bound":false}}
```

`run_resuming` (recorded):

```json
{"v":1,"seq":3,"t":0.0,"run_s":null,"type":"run_resuming","phase":"run","kind":"step","console":true,"message":"resuming run pc-fail at understand","fields":{"run_id":"pc-fail","start_at":"understand","accepted_drift":false}}
```

`run_started` (recorded):

```json
{"v":1,"seq":1,"t":0.0,"run_s":null,"type":"run_started","phase":"run","kind":"step","console":false,"message":"run pc-selftest started","fields":{"run_id":"pc-selftest","run_dir":"runs/pc-selftest","mode":"dev","review_mode":"full","resumed":false,"start_at":null,"plan_only":false,"documents":[{"doc_id":"DOC-design","role":"under_review","title":null,"version":null,"file":"design.pages.txt","pages":null}],"profile":null,"model":"claude-opus-5-5","backend":"claude_code","transport":"fake","deadline_active":true,"deadline_s":3600,"stage_limits_s":{"stage_1_end":2820.0,"refine_end":3420.0,"verdict_end":3540.0},"stage_limits_scaled":false,"report_reserve_s":180,"criteria":["design_intent","fitness_for_objectives","requirement_completeness","internal_consistency","claims_and_external_constraints","security_and_privacy","scalability_and_failure_modes","assumptions_and_dependencies","verifiability","decision_preservation","operability_and_governance"],"shards":[{"index":1,"name":"intent_and_fitness","criteria":["design_intent","fitness_for_objectives","decision_preservation"]},{"index":2,"name":"requirements_and_consistency","criteria":["requirement_completeness","internal_consistency","verifiability"]},{"index":3,"name":"claims_and_assumptions","criteria":["claims_and_external_constraints","assumptions_and_dependencies"]},{"index":4,"name":"risk_and_operations","criteria":["security_and_privacy","scalability_and_failure_modes","operability_and_governance"]}],"phases_enabled":["ingest","understand","plan","research","assess","refine","verify","report"]}}
```

`shard_cut` (recorded):

```json
{"v":1,"seq":40,"t":0.0,"run_s":0.0,"type":"shard_cut","phase":"assess","kind":"warn","console":true,"message":"assess shard 2/4 (requirements_and_consistency) cut by the stage 1 limit; 1 finished finding(s) kept","fields":{"shard":2,"shard_name":"requirements_and_consistency","shards":4,"call_id":"llm-0004","cut_at_s":0.0,"kept":1,"kept_drafts":[{"index":1,"kind":"validation_need","severity":"medium","title":"Peak-day reminder volume is not tested"}],"criteria_not_assessed":["requirement_completeness","internal_consistency"]}}
```

`shard_drafted` (recorded):

```json
{"v":1,"seq":37,"t":0.0,"run_s":0.0,"type":"shard_drafted","phase":"assess","kind":"done","console":true,"message":"assess shard 1/4 (intent_and_fitness): 1 draft finding(s) (1 strength), unverified","fields":{"shard":1,"shard_name":"intent_and_fitness","shards":4,"call_id":"llm-0003","findings":1,"sound_areas":1,"drafts":[{"index":1,"kind":"strength","severity":null,"title":"Accessibility is verified, not just promised"}]}}
```

`shard_started` (recorded):

```json
{"v":1,"seq":31,"t":0.0,"run_s":0.0,"type":"shard_started","phase":"assess","kind":"step","console":true,"message":"assess shard 1/4 (intent_and_fitness): design_intent, fitness_for_objectives, decision_preservation","fields":{"shard":1,"shard_name":"intent_and_fitness","shards":4,"criteria":["design_intent","fitness_for_objectives","decision_preservation"]}}
```

`shards_ended` (recorded):

```json
{"v":1,"seq":57,"t":0.0,"run_s":0.0,"type":"shards_ended","phase":"assess","kind":"step","console":true,"message":"4 shard(s) ended in 0.0s; merged when stage 1 closes","fields":{"shards":4,"seconds":0.0,"outcomes":{"1":"done","2":"done","3":"done","4":"done"}}}
```

`shards_kept` (recorded):

```json
{"v":1,"seq":4,"t":0.0,"run_s":0.0,"type":"shards_kept","phase":"assess","kind":"step","console":true,"message":"4 finished shard(s) kept from before the interruption: 1, 2, 3, 4","fields":{"shards":[1,2,3,4]}}
```

`shards_merged` (recorded):

```json
{"v":1,"seq":65,"t":0.0,"run_s":0.0,"type":"shards_merged","phase":"assess","kind":"done","console":true,"message":"merged 4 shard(s): 4 findings (1 gap, 1 risk, 1 strength, 1 validation_need); 1 sound areas; coverage: 4 findings, 7 no_issue; evidence: 3 doc and 0 inference entries added to the ledger","fields":{"shards":4,"findings":4,"sound_areas":1,"doc_evidence_added":3,"inference_evidence_added":0,"degraded_shards":[],"by_kind":{"risk":1,"validation_need":1,"gap":1,"strength":1},"coverage":{"no_issue":7,"findings":4}}}
```

`tool_round` (recorded):

```json
{"v":1,"seq":56,"t":0.0,"run_s":0.0,"type":"tool_round","phase":"research","kind":"step","console":true,"message":"tool round: 1 call(s) (mcp-internet-search__search)","fields":{"calls":1,"tools":["mcp-internet-search__search"],"not_executed":0,"iteration":1}}
```

`understand_started` (recorded):

```json
{"v":1,"seq":10,"t":0.0,"run_s":0.0,"type":"understand_started","phase":"understand","kind":"step","console":true,"message":"reading the design: intent, objectives, constraints and the decision registry","fields":{}}
```

`verdict` (recorded):

```json
{"v":1,"seq":83,"t":0.0,"run_s":0.0,"type":"verdict","phase":"report","kind":"step","console":true,"message":"verdict fit_with_conditions; 3 findings, 2 unresolved, 1 limitations; invariants INV-03..10 pass; wrote report.md","fields":{"label":"fit_with_conditions","confidence":0.75,"findings":3,"unresolved":2,"limitations":1,"by_severity":{"high":1,"medium":1,"none":1},"report_md":"runs/pc-selftest/report.md","report_json":"runs/pc-selftest/report.json"}}
```

`answer_unusable` (illustrative):

```json
{"v":1,"seq":120,"t":431.2,"run_s":431.2,"type":"answer_unusable","phase":"refine","kind":"warn","console":true,"message":"refine answer still unusable after one repair call (3 problem(s))","fields":{"stage":"refine","call_id":"llm-0012","problems":3}}
```

`call_bounded` (illustrative):

```json
{"v":1,"seq":41,"t":30.0,"run_s":30.0,"type":"call_bounded","phase":"assess","kind":"step","console":true,"message":"llm-0005 bounded at 235 s by the stage 1 limit (265 s on the run clock; deadline 540 s)","fields":{"call_id":"llm-0005","timeout_s":235.0,"bound":"stage_1_end","limit_s":265.0,"deadline_s":540}}
```

`call_cut` (illustrative):

```json
{"v":1,"seq":88,"t":265.0,"run_s":265.0,"type":"call_cut","phase":"plan","kind":"warn","console":true,"message":"plan: model call cut by the run deadline; the plan step was completed by code without model output","fields":{"stage":"plan","call_id":"llm-0002","at_s":265.0,"kept_items":0,"kept":{}}}
```

`call_retry` (illustrative):

```json
{"v":1,"seq":52,"t":61.4,"run_s":61.4,"type":"call_retry","phase":"assess","kind":"warn","console":true,"message":"LLMOverloadedError on llm-0006; retry 1/3 in 4 s","fields":{"reason":"transient","stage":"assess","call_id":"llm-0006","error":"LLMOverloadedError","attempt":1,"retries":3,"delay_s":4.0}}
```

`citations_dropped` (illustrative):

```json
{"v":1,"seq":97,"t":270.3,"run_s":270.3,"type":"citations_dropped","phase":"assess","kind":"warn","console":true,"message":"2 evidence citations dropped (not in the evidence register)","fields":{"count":2}}
```

`deadline_warning` (illustrative):

```json
{"v":1,"seq":3,"t":0.0,"run_s":null,"type":"deadline_warning","phase":"run","kind":"warn","console":true,"message":"deadline 300 s is not above this profile's stage limits (265 / 465 / 530 s for stage 1, refine and the verdict, set for a 540 s run): the three limits are scaled by 300/540 to 147 / 258 / 294 s; a model call still streaming at its limit is cut and its finished items are kept","fields":{"deadline_s":300}}
```

`declined` (illustrative):

```json
{"v":1,"seq":70,"t":140.0,"run_s":140.0,"type":"declined","phase":"understand","kind":"warn","console":true,"message":"model declined understand twice; continuing without it","fields":{"stage":"understand","call_id":"llm-0007","category":"cyber"}}
```

`fault_injected` (illustrative):

```json
{"v":1,"seq":30,"t":12.0,"run_s":12.0,"type":"fault_injected","phase":"assess","kind":"warn","console":true,"message":"injected fault: raise_in_stage in assess shard 2/4 (requirements_and_consistency)","fields":{"fault":"raise_in_stage","where":"assess shard 2/4 (requirements_and_consistency)"}}
```

`fault_schedule` (illustrative):

```json
{"v":1,"seq":4,"t":0.0,"run_s":null,"type":"fault_schedule","phase":"run","kind":"warn","console":true,"message":"fault schedule BEH-29: raise_in_stage armed (at the end of assess)","fields":{"schedule":"BEH-29","armed":true,"fault":"raise_in_stage","target":"assess","at":"end"}}
```

`heartbeat` (illustrative):

```json
{"v":1,"seq":18,"t":10.0,"run_s":10.0,"type":"heartbeat","phase":"research","kind":"wait","console":true,"message":"waiting for 2 tool call(s)","fields":{}}
```

`interrupted` (illustrative):

```json
{"v":1,"seq":60,"t":95.0,"run_s":95.0,"type":"interrupted","phase":"stage_1","kind":"warn","console":true,"message":"interrupted; state flushed (resume re-runs the unfinished members)","fields":{"where":"stage_1"}}
```

`not_assessed` (illustrative):

```json
{"v":1,"seq":110,"t":470.0,"run_s":470.0,"type":"not_assessed","phase":"report","kind":"warn","console":true,"message":"out of time before assessment: no verdict call; the report says the design was not assessed","fields":{"reason":"deadline"}}
```

`phase_skipped` (illustrative):

```json
{"v":1,"seq":70,"t":300.0,"run_s":300.0,"type":"phase_skipped","phase":"refine","kind":"step","console":true,"message":"skipped (disabled in config/agent.yaml)","fields":{"reason":"disabled","stage":"refine"}}
```

`plan_approval` (illustrative):

```json
{"v":1,"seq":35,"t":20.0,"run_s":20.0,"type":"plan_approval","phase":"plan","kind":"warn","console":true,"message":"plan_approval: stdin is not a terminal; plan approved automatically (non-interactive)","fields":{"approved":true,"interactive":false}}
```

`plan_approval_waiting` (illustrative):

```json
{"v":1,"seq":34,"t":20.0,"run_s":20.0,"type":"plan_approval_waiting","phase":"plan","kind":"wait","console":true,"message":"plan_approval is on: waiting for approval before research","fields":{}}
```

`plan_criterion_skipped` (illustrative):

```json
{"v":1,"seq":33,"t":20.0,"run_s":20.0,"type":"plan_criterion_skipped","phase":"plan","kind":"step","console":true,"message":"skipped operability_and_governance","fields":{"criterion_id":"operability_and_governance"}}
```

`plan_only_stop` (illustrative):

```json
{"v":1,"seq":40,"t":22.0,"run_s":22.0,"type":"plan_only_stop","phase":"plan","kind":"step","console":true,"message":"--plan-only: stopping after the plan (zero tool calls)","fields":{}}
```

`preflight` (illustrative):

```json
{"v":1,"seq":3,"t":0.0,"run_s":null,"type":"preflight","phase":"run","kind":"warn","console":true,"message":"LLM preflight not implemented by this backend; skipped","fields":{"status":"skipped"}}
```

`refine_fallback` (illustrative):

```json
{"v":1,"seq":101,"t":465.0,"run_s":465.0,"type":"refine_fallback","phase":"refine","kind":"warn","console":true,"message":"refine fallback: the merged findings stand, in severity and confidence order","fields":{"cut":true,"truncated":false,"invalid":false,"declined":false}}
```

`refine_skipped` (illustrative):

```json
{"v":1,"seq":100,"t":300.0,"run_s":300.0,"type":"refine_skipped","phase":"refine","kind":"done","console":true,"message":"no findings to refine; skipping the refine call","fields":{"findings":0}}
```

`registry_anchor` (illustrative):

```json
{"v":1,"seq":25,"t":140.0,"run_s":140.0,"type":"registry_anchor","phase":"understand","kind":"step","console":true,"message":"registry anchor check: AD-002 requoted","fields":{"registry_id":"AD-002","action":"requoted"}}
```

`research_answer_ignored` (illustrative):

```json
{"v":1,"seq":58,"t":180.0,"run_s":180.0,"type":"research_answer_ignored","phase":"research","kind":"warn","console":true,"message":"answer for an unknown question ignored","fields":{}}
```

`research_deadline` (illustrative):

```json
{"v":1,"seq":59,"t":265.0,"run_s":265.0,"type":"research_deadline","phase":"research","kind":"warn","console":true,"message":"deadline reserve reached; ending research without a wrap-up turn","fields":{"code":"deadline","detail":"stage_limits_s.stage_1_end"}}
```

`research_doc_only` (illustrative):

```json
{"v":1,"seq":45,"t":150.0,"run_s":150.0,"type":"research_doc_only","phase":"research","kind":"warn","console":true,"message":"No external research was possible: no tool gateway (--no-tools, or every server is disabled); continuing document-only","fields":{"detail":"no_tools"}}
```

`research_evidence_ignored` (illustrative):

```json
{"v":1,"seq":57,"t":180.0,"run_s":180.0,"type":"research_evidence_ignored","phase":"research","kind":"warn","console":true,"message":"RQ-002: 1 unknown evidence ID(s) ignored","fields":{"question_id":"RQ-002","count":1}}
```

`research_skipped` (illustrative):

```json
{"v":1,"seq":44,"t":150.0,"run_s":150.0,"type":"research_skipped","phase":"research","kind":"step","console":true,"message":"no question needs external evidence; research skipped","fields":{"reason":"no_external_questions"}}
```

`research_stop_ignored` (illustrative):

```json
{"v":1,"seq":56,"t":175.0,"run_s":175.0,"type":"research_stop_ignored","phase":"research","kind":"warn","console":true,"message":"model asked to stop; ignored (2 question(s) never attempted, 0 tool call(s) so far)","fields":{"never_attempted":2,"tool_calls":0}}
```

`review_inputs_found` (illustrative):

```json
{"v":1,"seq":24,"t":140.0,"run_s":140.0,"type":"review_inputs_found","phase":"understand","kind":"step","console":true,"message":"3 review comments or claimed fixes found in the document (treated as claims to check); 2 approved decisions to preserve","fields":{"review_inputs":3,"approved_decisions":2}}
```

`revision_rejected` (illustrative):

```json
{"v":1,"seq":99,"t":440.0,"run_s":440.0,"type":"revision_rejected","phase":"refine","kind":"warn","console":true,"message":"FND-004: severity rejected (no revision reason, no new evidence)","fields":{"finding_id":"FND-004","fields_rejected":["severity"]}}
```

`shard_declined` (illustrative):

```json
{"v":1,"seq":66,"t":200.0,"run_s":200.0,"type":"shard_declined","phase":"assess","kind":"warn","console":true,"message":"model declined assess shard 3/4 (claims_and_assumptions) twice; its criteria are not assessed","fields":{"shard":3,"shard_name":"claims_and_assumptions","shards":4,"call_id":"llm-0011","category":"cyber"}}
```

`shard_failed` (illustrative):

```json
{"v":1,"seq":65,"t":120.0,"run_s":120.0,"type":"shard_failed","phase":"assess","kind":"warn","console":true,"message":"assess shard 4/4 (risk_and_operations) failed (LLMOverloadedError); its criteria are not assessed","fields":{"shard":4,"shard_name":"risk_and_operations","shards":4,"error":"LLMOverloadedError","call_id":"llm-0006","criteria":["scalability_and_failure_modes"]}}
```

`shard_truncated` (illustrative):

```json
{"v":1,"seq":67,"t":230.0,"run_s":230.0,"type":"shard_truncated","phase":"assess","kind":"warn","console":true,"message":"assess shard 1/4 (intent_and_fitness): answer truncated twice at the output cap; its criteria are not assessed","fields":{"shard":1,"shard_name":"intent_and_fitness","shards":4,"call_ids":["llm-0004","llm-0013"],"max_tokens":128000}}
```

`stage_limit_passed` (illustrative):

```json
{"v":1,"seq":80,"t":295.0,"run_s":295.0,"type":"stage_limit_passed","phase":"stage_1","kind":"warn","console":true,"message":"stage 1 limit passed by 30 s; stopping research","fields":{"limit":"stage_1_end","limit_s":265,"grace_s":30.0,"stopped":["research"]}}
```

`status` (illustrative):

```json
{"v":1,"seq":90,"t":300.0,"run_s":300.0,"type":"status","phase":"run","kind":"step","console":true,"message":"a line from code that gives no data","fields":{}}
```

`stop_rule` (illustrative):

```json
{"v":1,"seq":81,"t":465.0,"run_s":465.0,"type":"stop_rule","phase":"refine","kind":"warn","console":true,"message":"stop rule deadline fired; skipping to verify","fields":{"code":"deadline","detail":"stage_limits_s.refine_end","stage":"refine","to":"verify"}}
```

`stopped_after_plan` (illustrative):

```json
{"v":1,"seq":41,"t":22.0,"run_s":22.0,"type":"stopped_after_plan","phase":"run","kind":"done","console":true,"message":"stopped after the plan; no report written","fields":{}}
```

`tool_status` (illustrative):

```json
{"v":1,"seq":47,"t":151.0,"run_s":151.0,"type":"tool_status","phase":"research","kind":"step","console":true,"message":"blocked mcp-internet-search__fetch by the tool policy","fields":{"tool":"mcp-internet-search__fetch","blocked":true}}
```

`tools_down` (illustrative):

```json
{"v":1,"seq":48,"t":152.0,"run_s":152.0,"type":"tools_down","phase":"research","kind":"warn","console":true,"message":"every tool server is unavailable; continuing document-only","fields":{}}
```

`truncated_twice` (illustrative):

```json
{"v":1,"seq":102,"t":450.0,"run_s":450.0,"type":"truncated_twice","phase":"refine","kind":"warn","console":true,"message":"refine: answer truncated twice at the output cap (max_tokens=128000); the merged assess findings are reported in severity and confidence order, without the global refine pass (no duplicates merged, no registry decisions linked, no research evidence attached)","fields":{"stage":"refine","max_tokens":128000,"call_ids":["llm-0012","llm-0013"]}}
```
