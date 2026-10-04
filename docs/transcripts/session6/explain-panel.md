# Explain panel ("What is happening"), worker note, 2026-10-04

Branch `s4/explain-panel` from `origin/claude/happy-darwin-d0bl94` at 8c3a291.
Decision row: `docs/USER_DECISIONS.md` #45.

## What was built

- A "What is happening" card at the top of the stage column on the open run's page, above "Stage 1, concurrent", labelled with the pill "explanation, not the record" and a footer saying the text is written in advance and only the numbers are this run's.
- It shows the entry of the current stage: the stage in flight (refine, verify or report), or every stage 1 member in flight (they run side by side), or the finished run's paragraph once the stream ends; a stop at a limit since the stage began adds the limits entry.
- A Why button at the end of every stage row opens that stage's entry in place under the row; a Why on the axis heading opens the limits entry.
- The text is the `#explain-map` JSON in `ui/static/index.html`; app.js `FACTS` fills each `{name}` from fields the reducer keeps (`recordFacts`); a sentence whose names are not in the stream yet falls back to its alternative or is left out.
- No new numeric literal in app.js; the honesty tests pass unchanged.

## Tests

`tests/test_ui_explain.py`, 10 tests: map shape; every placeholder is a FACT and every FACT is used; every FACT reads a field the reducer writes and the schema requires; every cited decision (#31, #34, #37, #40) is a row of USER_DECISIONS.md containing the claim; every named file exists and holds the named symbols; the panel is labelled explanation and sits above the rows; record by record over the three UI fixtures no entry shows an empty or undefined value; the repair counts and a lower-bound cost fill in; on the served page the panel moves from assess to refine to finished as lines are appended, and Why opens and closes in place; a finished run shows the summary.
A mutation of one placeholder name and one decision number made three tests fail; the file was restored.

Gates: ruff `All checks passed!`; full suite `1977 passed, 1 skipped, 2 xfailed` (1967 + 10); selftest passed; the UI tests also pass from `~`.

## Browser check

Own server on port 8797 (`dra ui --runs-dir runs`), a copy of `demo6/runs/ui-261004-034213-c5cb` under the ignored `runs/`, its progress.jsonl appended line by line into a fresh run folder with the page open (Playwright Chromium). Screenshots in `docs/transcripts/session6/explain-panel/`: `01_assess.png` and `01_assess_page.png` (seq 309: 3 of 6 shards answered), `02_refine.png` (seq 370: 55 merged findings), `03_finished.png` (52 findings, 41 ledger entries, 2 stops at a limit, cost at least $7.37), `04_why_understand.png`, `05_why_limits.png`. No page errors. Server stopped by pid.

## Open points for the planner

- "Cited external entries" is not in the record the page holds; the finished paragraph says the ledger entries research gathered (`research_stopped.ledger_entries`) instead.
- The server names come from the run's own `tool_round` records; before the first round the research entry says how many tools were offered.
- `docs/ARCHITECTURE.md` section 2 still says four assess shards; the config has six since #40. The panel reads the count from the run, so it is right either way, but the document is stale.
- The Why column narrows the status column a little, so long status texts wrap one line more than before.

## The entries in full

### ingest: Ingest: reading the PDF

- Ingest is code, not a model: the PDF is read into page-marked text of {pages} pages and {sections} sections, and every later quote is checked against these same bytes.
  - until those numbers are in the stream: Ingest is code, not a model: the PDF is read into page-marked text, and every later quote is checked against these same bytes.

From: `agent/sit_review_agent/phases/ingest.py; agent/sit_review_agent/ingest/text.py`

### understand: Understand: what the design says it is

- Understand is one model call that reads the whole document once and writes the intent summary (the design's objectives and constraints) and a registry of the decisions the document says it has approved.
- Each entry carries a verbatim quote as its anchor, and the registry is then frozen and hashed, so no later call can rewrite what the document decided: later findings link to these entries and quote the same page text, which is what makes every claim traceable.
- This run: {objectives} objectives, {constraints} constraints and {registry_entries} registry entries from {pages} pages.
  - until those numbers are in the stream: The document is {pages} pages and {sections} sections; the counts appear here when the call returns.

From: `agent/sit_review_agent/phases/understand.py; agent/sit_review_agent/state/decision_registry.py; docs/ARCHITECTURE.md sections 2 and 6`

### plan: Plan: what to check and what to look up

- Plan is one model call that turns the {criteria} review criteria into the questions to check, and marks the ones that need an outside source as research questions for the SIT MCP servers.
  - until those numbers are in the stream: Plan is one model call that turns the review criteria into the questions to check, and marks the ones that need an outside source as research questions for the SIT MCP servers.
- Code adds a document-only question for any criterion the model neither asked about nor skipped with a reason, so every criterion is checked; research starts once understand and plan have both ended, while the assess shards never wait for the plan.
- This run: {questions} questions, {external} of them for an outside source.

From: `agent/sit_review_agent/phases/plan.py build_plan; agent/sit_review_agent/states.py STAGE_1_DEPENDS`

### assess: Assess: the shards, side by side

- Assess is {shards} model calls running at the same time, one per group of criteria, each reading only the document and its own criteria: one pass over every criterion did not fit the slot, so the stage now takes as long as its slowest shard, not the sum of them.
  - until those numbers are in the stream: Assess is one model call per group of criteria, all running at the same time, each reading only the document and its own criteria: one pass over every criterion did not fit the slot, so the stage takes as long as its slowest shard, not the sum of them.
- Each shard drafts findings anchored to verbatim quotes with a page; a shard that reaches the stage 1 limit at {stage_1_end} keeps every finding it had finished, and only its criteria with no finished finding are marked not assessed.
  - until those numbers are in the stream: Each shard drafts findings anchored to verbatim quotes with a page; a shard that reaches the stage 1 limit keeps every finding it had finished, and only its criteria with no finished finding are marked not assessed.
- So far {shards_drafted} of {shards} shards have answered, {shards_cut} ended at the limit, and {drafts} draft findings have streamed.
- The merge, which is code, then numbered {merged_findings} findings in shard order, so no ID depends on which shard finished first.

From: `agent/sit_review_agent/phases/assess.py; config/agent.yaml assess.shards; decisions #31 and #40`

### research: Research: asking the SIT MCP servers

- Research asks the SIT MCP servers the plan's {research_questions} outside questions in rounds: the model asks for tool calls, the gateway runs them, and each result becomes a ledger entry (EV-nnn) before the model reads it, so it can cite only what it has read.
  - until those numbers are in the stream: Research asks the SIT MCP servers the plan's outside questions in rounds: the model asks for tool calls, the gateway runs them, and each result becomes a ledger entry (EV-nnn) before the model reads it, so it can cite only what it has read.
- It has asked {servers} with {tool_calls} tool calls; after each round the stop rules decide whether another round is worth it.
  - until those numbers are in the stream: {tools_offered} tools are offered from the enabled servers; after each round the stop rules decide whether another round is worth it.
  - until those numbers are in the stream: After each round the stop rules decide whether another round is worth it.
- The assess shards never see this evidence: they start at once, and waiting for research would not fit the slot, so refine applies it to the merged findings instead and the evidence is attached by the one call that has read it, never by a shard that did not (decision #37).
- Research stopped ({research_stop}) with {answered} of {research_questions} questions answered and {ledger_entries} entries in the ledger.

From: `agent/sit_review_agent/phases/research.py; agent/sit_review_agent/stop_rules.py; agent/sit_review_agent/state/evidence_ledger.py; decision #37`

### refine: Refine: one call over every finding

- Refine is one model call over all {merged_findings} merged findings that sees the research evidence, the frozen registry and every shard's findings together, so it can merge duplicates across shards, withdraw the unsupported ones, rank them and attach the outside evidence.
  - until those numbers are in the stream: Refine is one model call over all the merged findings that sees the research evidence, the frozen registry and every shard's findings together, so it can merge duplicates across shards, withdraw the unsupported ones, rank them and attach the outside evidence.
- It returns one revision per finding, not the findings again, and code checks each revision by rule: the ones that pass are kept as given and only the failing ones go to one repair call, so a repair ended by the limit at {refine_end} cannot cost the good revisions.
  - until those numbers are in the stream: It returns one revision per finding, not the findings again, and code checks each revision by rule: the ones that pass are kept as given and only the failing ones go to one repair call, so a repair ended by the limit cannot cost the good revisions.
- This run: {refine_kept} revisions passed and were kept, {refine_retry} went to the repair call.
- Result: {revised} revised, {merged} merged into another, {withdrawn} withdrawn and {unchanged} kept as drafted, leaving {refined_findings} findings.

From: `agent/sit_review_agent/phases/refine.py split_revisions, repair_outcome; agent/sit_review_agent/llm/outputs.py revision_problems`

### verify: Verify: every quote against the page

- Verify is code, not a model: each of the {anchors} anchors is searched for in the canonical page text, an exact match first, then a close match on the cited page or a page next to it.
  - until those numbers are in the stream: Verify is code, not a model: each anchor is searched for in the canonical page text, an exact match first, then a close match on the cited page or a page next to it.
- Evidence is filled in from the ledger, so the model never writes a URL; a finding left with no anchor that resolves moves to the unresolved list as Unverified and is disclosed, never dropped silently.
- This run: {resolved} of {anchors} anchors resolved, {unresolved_anchors} unresolved; {findings_verified} findings verified, {findings_unverified} unverified.

From: `agent/sit_review_agent/phases/verify.py; agent/sit_review_agent/ingest/anchor.py verify_anchor; agent/sit_review_agent/state/evidence_ledger.py hydrate`

### report: Report: the verdict and the record

- Report is one model call that writes only the verdict, by {verdict_end} at the latest, and code then assembles report.json and report.md from the findings and the evidence ledger: every claim cites its finding and evidence IDs, and an ID that does not exist fails the run.
  - until those numbers are in the stream: Report is one model call that writes only the verdict, and code then assembles report.json and report.md from the findings and the evidence ledger: every claim cites its finding and evidence IDs, and an ID that does not exist fails the run.
- The limitations section is written by code, one line per degradation (DEG-nnn): every limit reached, call ended early, failed tool or unverified finding is stated in the report rather than hidden, and only code can set the verdict to not assessed.
- Verdict: {verdict} at confidence {confidence}, {final_findings} findings, {unresolved} unresolved items, {limitations} limitations.

From: `agent/sit_review_agent/phases/report.py assemble_review; agent/sit_review_agent/invariants.py check_INV_05, check_INV_07, check_INV_12`

### limits: Why the run has stage limits

- Every stage has a fixed end on the run clock, not a share of the deadline: stage 1 by {stage_1_end}, refine by {refine_end}, the verdict by {verdict_end}, inside a {deadline} deadline, and each model call is bounded by the time left before its stage ends.
  - until those numbers are in the stream: Every stage has a fixed end on the run clock, not a share of the deadline, and each model call is bounded by the time left before its stage ends.
- The limits exist because the run is live in front of the panel and must end with a report; the figures are a configurable assumption, since the lab brief sets no time limit (decision #34).
- A call that reaches its limit keeps every item it had finished and the run goes on to verify and the report, so only unfinished work is lost, and each stop is disclosed as a degradation; stops at a stage limit in this run: {limits_reached}.
  - until those numbers are in the stream: A call that reaches its limit keeps every item it had finished and the run goes on to verify and the report, so only unfinished work is lost, and each stop is disclosed as a degradation.

From: `config/profiles/demo.yaml stage_limits_s; agent/sit_review_agent/llm/runtime.py RunDeadline; agent/sit_review_agent/orchestrator.py _cap; decision #34`

### finished: The run, in one paragraph

- The run finished ({outcome}) at {wall} on the run clock with the verdict {verdict} at confidence {confidence}: {final_findings} findings, {unresolved} unresolved items and {limitations} limitations, each limitation one disclosed degradation.
  - until those numbers are in the stream: The run stopped before its report: {run_error}.
  - until those numbers are in the stream: The run finished ({outcome}) at {wall} on the run clock.
- Research gathered {ledger_entries} outside entries into the ledger with {tool_calls} tool calls; stops at a stage limit in this run: {limits_reached}.
- The model cost is at least {cost_lower_bound}: a call ended by a limit logs its usage as unknown, never as zero.
  - until those numbers are in the stream: The model cost was {cost}.

From: `agent/sit_review_agent/manifest.py; agent/sit_review_agent/llm/gateway.py unrecorded_usage; docs/ARCHITECTURE.md section 6`

