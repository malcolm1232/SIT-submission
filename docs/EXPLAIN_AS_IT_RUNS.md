# Explain it as it runs: a study sheet for the review session

Written 4 Oct 2026 for Malcolm, to read aloud or paraphrase while the review page runs in front of the SIT panel.
Every claim was checked against the code at `8c3a291` on `claude/happy-darwin-d0bl94`; where a document and the code differ, this sheet follows the code and says so.
Every number carries its source in parentheses.
"Decision #n" means a row of `docs/USER_DECISIONS.md`; "ADR-nnn" means `docs/DECISIONS.md`.
The rehearsal of this morning is the run recorded in `docs/live_runs/sit_sample_ui_2/` and is called "rehearsal 1" below.

## 1. The one-minute version

The agent reads one technical design document, works out what the design is trying to achieve, checks it against eleven review criteria, researches the claims that need outside evidence, and writes a review (`docs/ARCHITECTURE.md` section 1, `config/criteria.yaml`).
It produces `report.md` and `report.json` in a run directory, plus every log needed to explain, resume or replay the run (`agent/sit_review_agent/rundir.py`).
Every finding is anchored to a quoted passage of the document, and every external citation is a tool call it actually made (`agent/sit_review_agent/ingest/anchor.py`, `agent/sit_review_agent/state/evidence_ledger.py`).
It recommends a change only when it can say what is wrong, why, what evidence supports that, and what the change would gain, and it says "no change" with a reason when the design is sound (`spec/finding.schema.json` `Recommendation`).

SIT judges the output on the words of the brief, page 5, section 2.4: the output must be "complete, consistent, accurate and traceable", "findings must be evidence-based, recommendations justified, and unresolved issues clearly stated" (`~/Downloads/AI Engineer Lab Exercise.pdf` p.5).
Each design choice serves one of those words:
- Complete: code adds a document-only plan question for any criterion the model left out, and the coverage table gives every criterion a row, including "checked, no issue" (`agent/sit_review_agent/phases/plan.py` `build_plan`, `phases/assess.py` coverage).
- Complete: in a re-assessment every prior finding gets exactly one status, and INV-13 fails the run if one is missing (`agent/sit_review_agent/delta.py`, `invariants.py` `check_INV_13`).
- Consistent: the decisions the document approved are frozen and hashed in understand, and a finding that would reverse one must say so as a challenge with at least two evidence items (`state/decision_registry.py`, `invariants.py` `check_INV_10`).
- Consistent: the page, the Markdown and the download are all rendered from the same `report.json` and `report.md`, so they cannot disagree (`report/render.py`, `ui/export.py`).
- Accurate: every anchor is searched for in the canonical text by code, exact first, then a fuzzy match of 0.90 or better within the cited page plus or minus one, narrowed to the cited section plus or minus one when that section resolves (`ingest/anchor.py` module docstring, `verify_anchor`).
- Traceable: the model never writes a URL; it cites ledger IDs (`EV-nnn`) and code fills in the URL and retrieval time from the ledger (`state/evidence_ledger.py` `hydrate`, `models.py` `EvidenceItem`).
- Traceable: `dra explain <finding-id>` shows a finding's anchors, its evidence with the tool call behind each item, and its history across phases (`report/explain.py`).
- Evidence-based: research results become ledger entries before the model sees them, so the model can only cite what it has read (`phases/research.py`, `tools/sources.py`).
- Recommendations justified: the schema requires issue, rationale, evidence and expected benefit on a recommendation, matching brief p.5 section 2.3 (`spec/finding.schema.json`).
- Unresolved issues stated: every degraded path becomes a numbered degradation `DEG-nnn` with one limitation in the report, written by code, never by the model (`state/run_state.py` `add_degradation`, `invariants.py` `check_INV_07`, `phases/report.py`).

## 2. The run, stage by stage, on the page's timeline

The run has five stages in a fixed order: ingest, a concurrent stage 1 (understand, plan, research, six assess shards), refine, verify, report (`agent/sit_review_agent/states.py` `STAGE_ORDER`).
The times below are rehearsal 1 on the lab's 30-page sample with tools (`docs/live_runs/sit_sample_ui_2/MEASUREMENT.md` "Stages").

What is on the page while it runs, and what each thing means (`agent/sit_review_agent/ui/static/app.js`, decision #44):
- The head clock is the run clock of the last recorded event plus the wall seconds since that event arrived, ticking once a second, and it says so in its label; it never estimates completion and shows no percentage (`ui/static/app.js` header comment and `clock-label`, decision #44 (B)).
- The axis under it runs from 0 to the deadline, with the recorded limits as markers: stage 1 by 265 s, refine by 465 s, verdict by 530 s, deadline 540 s (`config/profiles/demo.yaml` `stage_limits_s`); the markers come from the `run_started` record, not from the page (`ui/static/app.js` `limitMarks`).
- Each stage row expands to its model calls; each shard row shows its drafted finding titles as they arrive, with severity and kind but no other model text, labelled draft (decision #44 (C), `ui/events.py` `shard_drafted`, `draft_item`).
- A limit that fires is written under the axis in plain words with the counts kept (`ui/static/app.js` `noteLimit`).
- The Logs panel in the rail tails `progress.log` through a read-only route (decision #44 (D), `ui/static/app.js` "The Logs panel").
- Stop asks for confirmation and says what it does: SIGINT, exit 130, `state.json` kept, no report, resume with `dra resume <run_id>` (decision #44 (A)).
- A "What is happening" panel is being built in parallel on another branch; it is not on the tip at `8c3a291`, so point at it only if it has landed by the day.

### Ingest (run 0 to about 3 s)

What happens: code extracts the PDF with pdfplumber, normalises the text, marks pages as `[[PAGE n]]` and writes the canonical text and the section index to `text/` (`phases/ingest.py`, `ingest/pdf.py`).
Rehearsal 1: 2.7 s, no model call (`sit_sample_ui_2/MEASUREMENT.md` "Stages").
At the same moment a background warm-up of the MCP servers starts, because they scale to zero and a cold start measured 29 to 70 s (`orchestrator.py` `run_review`, `research/robustness/mcp_probe_findings.md` as quoted in `docs/ARCHITECTURE.md` section 5).
Point at: the document card (title, pages, sections) from the `document_ingested` event (`ui/events.py`).
Say:
> Ingest is code, not a model.
> Every quote later in the review is checked against these exact bytes, so the anchors are verified by code, not by trust.

### Understand (run about 3 s to 109 s)

What happens: one model call returns the design's intent and a registry of its approved decisions and constraints; the registry is then frozen and hashed (`phases/understand.py`, `state/decision_registry.py`).
Rehearsal 1: 106.3 s, 53 registry entries (`sit_sample_ui_2/MEASUREMENT.md` "Stages").
Why this way: the brief asks the agent to understand "objectives, assumptions, constraints, requirements and decisions" before judging fitness (brief p.3 section 2.1), and freezing the registry means no later phase can rewrite what the document decided (`invariants.py` `check_INV_10`).
Point at: the understand row and its open call in the expanded row.
Say:
> First the agent works out what the design is trying to do and what it has already decided.
> Those decisions are frozen, so a finding that wants to reverse one has to call itself a challenge and bring two pieces of evidence.

### Plan (run about 3 s to 75 s, beside understand)

What happens: one model call returns research questions per criterion; code drops questions with URLs, renumbers them `RQ-001` onwards and adds a document-only question for any criterion the model left out (`phases/plan.py`).
Rehearsal 1: 71.4 s, 21 plan questions (`sit_sample_ui_2/MEASUREMENT.md` "Stages").
Why this way: plan sees the document and the criteria only, not the intent, so it does not have to wait for understand (`phases/plan.py` docstring; decision #31 ruling 1).
Point at: plan and understand both started at about 3 s; the first draft item in the event stream, a plan question, arrived at 28.6 s (`sit_sample_ui_2/MEASUREMENT.md` "Shards").
Say:
> Plan and understand start together.
> Plan decides what needs outside evidence, and code makes sure every criterion has at least one question or a stated reason for skipping it, so nothing is silently skipped.

### Assess, six shards (run about 3 s to 265 s)

What happens: six model calls run side by side, one per criterion group, each seeing only the document and its own criteria (`phases/assess.py`, `config/agent.yaml` `assess.shards`).
The six groups are intent and fitness, decisions and governance, requirements and consistency, verifiability, claims and assumptions, security and failure (`config/agent.yaml` lines under `shards`).
When stage 1 closes, code merges the shards' findings, numbers them `FND-nnn` in shard order (never in finishing order) and ranks them by severity then confidence (`phases/assess.py` `AssessPhase.merge`).
Why this way: the first sequential version took 3,372 s on the payments design because one assess call wrote 63k output tokens; the concurrent version took 382 s with strict recall 13 of 14 against 11 of 14 (`docs/ARCHITECTURE.md` section 3 citing `docs/live_runs/QUALITY_COMPARISON.md`; ADR-011, decision #31).
Why six and not four: stage 1 ended at 265.2 s and 255 s with four shards on the lab document, over the 230 s threshold that decision #31 ruling 3 set, so the planner took the K = 6 step (decision #40).
Rehearsal 1: shards 1, 2 and 5 finished between 131.4 s and 177.9 s; shards 4 and 6 at 235.4 s and 257.2 s; shard 3 ended at the 265 s limit (`sit_sample_ui_2/MEASUREMENT.md` "Shards").
First draft finding on the page at 54.5 s (`sit_sample_ui_2/MEASUREMENT.md` "Shards").
Point at: the six shard rows with their drafted finding titles, the "draft, unverified" label, and the stage 1 marker at 265 s on the axis.
Say:
> The criteria are split into six groups that run at the same time, so adding a criterion adds a parallel call, not wall time.
> The findings you see arriving are drafts: IDs, ranks and severities can still change in refine, and the numbering is fixed by shard order so it never depends on which shard finished first.

### Research with the MCP servers (starts when understand and plan have both ended; run about 109 s to 207 s)

What happens: a hand-written tool loop; the model asks for tool calls, the gateway runs them on the MCP servers, each result becomes ledger entries `EV-nnn` before the model sees it, and the stop rules decide whether to continue: the cap rules after every tool round, every active rule after every iteration (`phases/research.py` module docstring, `stop_rules.py`).
Two servers are on, internet search and research information; browser automation is off because it shares one browser between callers with no domain allowlist, and document intelligence is off because its only probed call rejected the sample (`config/tools.yaml`, `docs/ARCHITECTURE.md` section 5).
The budget is 30 tool calls and 4 iterations (`config/stop_rules.yaml` lines 3 and 4).
A session the server closed is reopened once and the call retried once; a session idle over 60 s is reopened before the next call; a tool is disabled only after two genuine failures in a row (decision #38, `tools/gateway.py`, `config/tools.yaml` `session_idle_reopen_s`).
The policy layer refuses a URL to fetch that did not appear in an earlier result or in the document, and refuses any argument carrying a secret, a key-shaped token or bulk document text (`tools/policy.py` `check_urls`, `sanitise_args`).
Rehearsal 1: 97.2 s, one iteration, 9 web searches and 1 fetch, all succeeded; 8 met a closed session first and succeeded on the retry after 3 reopens; 41 external ledger entries (`sit_sample_ui_2/MEASUREMENT.md` "Tools").
Why research runs beside the shards: it starts at about 110 s while the shards started at about 3 s, so the shards never see external evidence; refine applies it instead, a trade accepted for the time slot (decision #37).
Point at: the research row, its stop reason when it shows, and the Logs panel lines for the tool calls.
Say:
> Research is a loop I wrote by hand, so every retry and every stop is our code.
> Each result goes into the evidence register before the model reads it, and the model can only cite register IDs, so it cannot invent a source.

### Refine (run 265 s to at most 465 s)

What happens: one model call sees all merged findings, the frozen registry, the research answers and the ledger, and returns one revision per finding: keep (with rank, severity, decision links and research evidence to add), merge into another, or withdraw (`phases/refine.py`, `llm/outputs.py` `FindingRevisionDraft`).
Since today, if some revisions break a rule, the good ones are kept and one repair call asks only for the failing ones (`phases/refine.py` `split_revisions`, `phases/_model_calls.py` `call_model` `split`; commits `df841bf` and `c1117f3`).
Why revisions and not the findings again: writing every finding a second time is the output the old design paid for; a revision is short (ADR-011, decision #31).
Why refine is the only place evidence reaches a finding: the only code path from an external ledger entry to a finding is the `added_evidence` of a keep revision (`phases/refine.py` `resolve_evidence`; `docs/transcripts/session6/refine-keep-good.md`).
If refine cannot run or is cut with nothing usable, the merged findings stand in severity and confidence order, disclosed (`phases/_model_calls.py` `REFINE_FALLBACK_IMPACT`).
Rehearsal 1: the refine call returned all 55 revisions in 152.1 s, one broke a rule, the whole answer was set aside, the repair ended at the limit with 4 (`sit_sample_ui_2/MEASUREMENT.md` "Refine"); section 4 tells this story.
Point at: the refine row, the refine marker at 465 s, and any limit note under the axis.
Say:
> Refine is the one call that sees everything at once.
> It merges duplicates, links findings to the design's own decisions and attaches the research evidence, and it does it as small revisions so it finishes in time.

### Verify (code, under a second)

What happens: every anchor is searched for in the canonical text, drafts are hydrated into canonical findings from the ledger, and a finding with no resolvable anchor moves to the unresolved list as "Unverified", with no recommendation (`phases/verify.py`, `ingest/anchor.py`).
One anchor-repair model call is made only when more than 60 s of slack remain before the verdict reserve (`phases/verify.py` `REPAIR_MIN_SLACK_S`).
Rehearsal 1: 0.02 s; 193 anchors, 192 exact, 1 not found; the repair was skipped at -0.054 s of slack (`sit_sample_ui_2/MEASUREMENT.md` "Shards" and "Stages").
Point at: the `anchors_verified` milestone in the Logs panel.
Say:
> Verify is code, not a second model.
> A quote that is not in the document cannot stay a finding.

### Report (the verdict call, then code; run about 465 s to 509 s)

What happens: one model call returns only the verdict, `fit`, `fit_with_conditions` or `not_fit`; code assembles the review, writes the unresolved items and limitations, checks the invariants and renders `report.md` from a template (`phases/report.py`, `report/render.py`).
`not_assessed` is never offered to the model: only code sets it, with the reason `deadline`, `truncated` or `declined` (decision #25, `phases/report.py` `not_assessed_verdict`).
The verdict call is cut at 530 s, and a cut or failed call gives a rule-based verdict, disclosed (`phases/report.py` `fallback_verdict`, `config/profiles/demo.yaml`).
Rehearsal 1: verdict call 43.4 s, run ended at 508.5 s, `fit_with_conditions` at 0.60, 52 findings, 5 disclosed limitations (`sit_sample_ui_2/MEASUREMENT.md` "Result").
Point at: the verdict and confidence, the counts strip, one finding with its quote and page, the Coverage tab, then the limitations.
Say:
> The model gives the verdict and nothing else at this point; the report is put together by code.
> The model can never say a design was not assessed; only code can, and it has to say why.

## 3. The limits, and what ending early means

The brief sets no time limit for the live run (decision #34; brief p.9 section 5.4 names the three parts and no duration).
The 540 s deadline is a project assumption, a configurable safety net kept until SIT answers the slot-length question (decision #34, `config/profiles/demo.yaml` comment on `deadline_seconds`).
Why limits at all: in a live demo a run with no end is worse than a run that ends with a disclosed gap, so each stage has an absolute end on the run clock: stage 1 by 265 s, refine by 465 s, the verdict call by 530 s (`config/profiles/demo.yaml` `stage_limits_s`).
They are absolute seconds, not fractions of the deadline, because a model call's thinking is a fixed cost, about 105 s per assess shard at medium (`config/stop_rules.yaml` comment on `stage_limits_s`).
The limit is enforced inside each model call, as its attempt timeout, so one slow call cannot take the report with it (`llm/runtime.py` `RunDeadline`).
`--deadline N` changes them: at or below 530 s or above 540 s the three limits scale by N / 540 and the run says so first, for example 900 s gives 441, 775 and 883 s (`config/profiles/demo.yaml` comment, `llm/runtime.py` `effective_stage_limits`).
Stage 1 also has a 30 s grace after its limit, after which members still running are stopped and disclosed (`orchestrator.py` `stage1_grace_s`).
Before stage 1 and before refine the orchestrator checks the caps, and a cap that fires jumps to verify, so a report is always written (`orchestrator.py` `_cap`, `_skip_on_cap`; `states.py` `STAGE_ON_CAP`).

What the agent keeps when a call ends at a limit:
- A call that streamed a complete answer and was writing it a second time keeps the complete answer, since today (`llm/partial.py` `partial`, `partial_complete`; commit `5b3908b`).
- A call cut inside its first answer keeps the items it had finished (`phases/assess.py` docstring, "cut by the stage 1 limit").
- A shard cut with no finished finding leaves its criteria marked not assessed, and the other shards' findings stand (`orchestrator.py` `_cut_shard`, `docs/ARCHITECTURE.md` section 8).
- A refine repair call cut at the limit keeps the revisions already accepted from the first answer plus whatever the repair finished (`phases/refine.py` `repair_outcome`).

What the report discloses:
- One degradation per ended-early call, naming the call, the time and what was kept, for example "5 finished finding(s) kept (cut call llm-0005)" (`sit_sample_ui_2/MEASUREMENT.md` "Disclosed limitations", DEG-002).
- The cost as a lower bound whenever a call's usage was not recorded, with the estimate kept apart and labelled (decision #28, `manifest.py` `journal_usage`, `llm/gateway.py` `unrecorded_usage`).
- The estimate uses the run's measured output rate, 118.6 tokens per second in rehearsal 1 (`sit_sample_ui_2/MEASUREMENT.md` check 6).
Say:
> The time limits are a safety net I chose, not something the brief asked for.
> When a call meets one, the agent keeps what was complete, says exactly what it lost, and still writes the report.

## 4. This morning's rehearsal and what it taught

The story in one line: we measured, found three defects that cost time or evidence (of the eight the measurement lists), fixed them the same day, and re-measure in the second rehearsal.

The numbers of rehearsal 1 (`sit_sample_ui_2/MEASUREMENT.md` unless noted):
- Wall time 508.5 s, 31.5 s of slack against 540 s.
- Stage 1 ended at 265.2 s with six shards, 35.2 s over the 230 s threshold; shard 3 ended at the limit.
- Refine returned 55 revisions; 1 broke a rule; the repair ended at the limit with 4; 51 findings were not refined.
- 41 external ledger entries; 0 cited by any of the 52 findings.
- Cost $7.37 recorded, about $8.86 with the $1.50 estimate for the two calls that ended early.
- 14 model calls, 5 disclosed limitations.

Defect 1, in plain words: the Claude Code CLI checks each structured answer against the schema itself, and when its own check rejected a complete answer, the model wrote the whole answer again (`docs/transcripts/session6/shard-first-answer.md` "The cause").
Three of six shards did this; shards 4 and 6 took 3 CLI turns instead of 2 and wrote about twice the output (30,271 and 33,576 tokens against 15,248 to 20,662) (`sit_sample_ui_2/MEASUREMENT.md` "Shards").
Had the first complete answers been kept, the last shard would have finished at about 217 s, under 230 s (`sit_sample_ui_2/MEASUREMENT.md` "Shards").
Shard 3 was the worst case: it had a complete answer of 13 findings by 217.2 s, started again, and at the limit only the 5 findings of the unfinished repeat were kept (`sit_sample_ui_2/MEASUREMENT.md` "Shards").
The fix, two parts: the gateway now checks every complete answer as it closes, and when the CLI starts another message after an answer the gateway accepts, it ends the call and uses that answer (`llm/claude_code.py` module docstring "First complete answer", commit `af12daf`); and a call that meets the limit while repeating keeps the last complete answer (commit `5b3908b`).
A call with tools (research) is excluded, because its next call resumes the same CLI session, which would end in the CLI's rejection of the answer the gateway took (`llm/claude_code.py` docstring; commit `95e2f0d`; `docs/transcripts/session6/repeat-off-with-tools.md`).

Defect 2, in plain words: one bad revision out of 55 threw all 55 away, and the repair could not redo them in the 48 s left (`sit_sample_ui_2/MEASUREMENT.md` "Refine").
The fix: refine keeps every revision that holds on its own and the one repair call asks only for the failing ones (commit `df841bf`); if that repair call fails, the kept revisions are still applied and the failure is disclosed (commit `c1117f3`, `docs/transcripts/session6/repair-fallback.md`).

Defect 3, in plain words: evidence only reaches findings through refine, so when refine was degraded, all 41 external entries were wasted for the findings (`sit_sample_ui_2/MEASUREMENT.md` defect 4).
The fix is defect 2's fix: with the good revisions kept, any external citation they carry reaches its finding even when the repair is cut, which a test proves on a fake gateway (`docs/transcripts/session6/refine-keep-good.md` "Does this fix alone").
What it does not fix: a model that cites nothing, or a first refine call that is itself cut; the precise next lever, if the second rehearsal shows uncited evidence in a complete answer, is a rule that an answered question's evidence is cited by at least one finding of its criterion (`docs/transcripts/session6/refine-keep-good.md`).

What the second rehearsal should show (to be filled in):
- [TO FILL FROM REHEARSAL 2: stage 1 end with six shards, against 265.2 s before and 230 s target; calls that ended at their first answer]
- [TO FILL FROM REHEARSAL 2: refine revisions applied, against 4 of 55 before]
- [TO FILL FROM REHEARSAL 2: findings citing external evidence, against 0 of 52 before]
- [TO FILL FROM REHEARSAL 2: wall time and cost, against 508.5 s and about $8.86 before]

Say:
> The first rehearsal on your sample told me three things I could not have guessed from offline tests.
> I measured them from the run's own logs, fixed each with a test that fails without the fix, and ran it again. [UNVERIFIED: true only once rehearsal 2 has run; at `8c3a291` it has not]
> That loop, measure, find, fix, re-measure, is how I worked the whole way.

## 5. The honesty rules

Nothing on the page or in the report that the record does not hold:
- The page draws only from `progress.jsonl` event types and fields and never parses message text (`ui/events.py` module docstring).
- No model text reaches the live view beyond the drafted finding titles; the honesty tests were rewritten for this contract, not deleted (decision #44).
- The review on the page is rendered from `report.json`, the same object the Markdown template renders (`docs/ARCHITECTURE.md` section 10, `report/render.py`).
- The tools status means "answered the last recorded warm-up", never "awake now"; the page never probes on load (`ui/rundata.py` `tools_status`).

The clock contract: every time on the page is the record's run clock; the only browser-clock read adds the seconds since the last event and stops with the stream; no completion estimate or percentage is ever shown; every limit comes from the `run_started` record (decision #44, `ui/static/app.js` header comment).

The degradation disclosures: each degraded path is one `DEG-nnn` with its event and impact, and the report has one limitation per degradation, checked by INV-07 (`invariants.py` `check_INV_07`).
A free-text URL that is not in the ledger is replaced by "[link removed: not in the evidence register]" and disclosed (`phases/report.py` docstring, INV-05).
A finding ID the review cites that is not one of its findings fails the run (INV-12, `invariants.py` `check_INV_12`).
The manifest is written as `crashed` before the first model call and finalised at exit, so a run that dies never reads as completed (`manifest.py` `start_manifest`).

Why the export says nothing `report.md` does not: there is no second renderer; the HTML is the run's own `report.md` converted to HTML, cut at its own headings into eight parts, with raw HTML escaped and images off, so model text cannot add markup (decision #43, `ui/export.py` module docstring, `tests/test_ui_outputs.py`).
The one addition is the chat log, which when it exists follows in its own headed section, labelled as the reading aid it is (`ui/export.py` `CHAT_HEADING`).

The leakage rules for the public snapshot `malcolm1232/SIT-public`: it never carries `eval/blind/`, the answer keys, transcripts, raw model logs, the lab's documents or the probe results; it is refreshed only with `scripts/export_public_snapshot.py`, whose reviewed list of accepted scan findings is `.public-allow` (`docs/HANDOVER_261004_PLANNER.md` section 6, `scripts/export_public_snapshot.py` `RULES`).
`scripts/leakage_grep.py` gates the agent's code, prompts and config against answer-key text and document-specific strings (`scripts/leakage_grep.py` docstring).
Recorded runs commit summaries, not raw model logs: rehearsal 1 commits `llm_calls.json` (ids, timings, usage, counts) instead of `llm.jsonl`, and its `text/` folder is the lab's material, kept out of any public snapshot (`sit_sample_ui_2/MEASUREMENT.md` "What is and is not in this directory").

Say:
> Everything the page shows is in the run's record, and everything the agent could not do is written in the report by code.
> If you see a number on this page, you can find it in a file.

## 6. Custom loop versus LangGraph

The measured comparison, one pair so far, payments design, demo profile, no tools (`docs/COMPARISON_LANGGRAPH.md`):
- Wall time: custom loop 382.3 s, LangGraph 424.7 s.
- Strict recall: 13 of 14 against 12 of 14; lenient 14 of 14 both; adjudicated precision 0.944 both.
- The one strict-recall difference is flaw F07, partial in the LangGraph run.
- The 42 s difference is explained by one shard reaching the stage 1 limit under a Mac load average of 15.8 against about 5, and the limit is enforced by the runtime in both arms, not by the framework.
- Parity tests: 26 of 28 pass, the 2 expected failures named (start order, and a fault wrapper around the whole assess member) (`tests/test_parity_langgraph.py`).
- Lines: the variant is 436 lines and replaces 153 lines of hand-written scheduling.
- Five more paired runs are planned (the custom loop on payments again under equal load, both arms on the clinical and lakehouse designs) and wait for Malcolm's go, about $35 (`docs/HANDOVER_261004_PLANNER.md` section 2 item 3).

How to answer "why not a framework" honestly:
"I chose a custom loop on a weighted matrix first, 92 against LangGraph 80 (ADR-001, `research/frameworks/README.md`).
Then I built the same agent on LangGraph behind a flag and ran both on the same document.
LangGraph made the fan-out, the join and the graph drawing easier.
It made other things harder: research needs to wait for understand and plan but not for the shards, which needed a subgraph because a superstep is a barrier; there is no per-node time limit, so the stage backstop is still hand-written; and its checkpoint holds only control state, so resume still reads my own checkpoints.
On one pair the quality is the same within noise, and I say plainly that one pair cannot show a difference either way.
I kept the custom loop because every retry, cut and disclosure is code I can show you and test, and I kept the variant so anyone can run both with one flag."

## 7. Twenty likely questions

1. How do you stop hallucinated citations?
The model never writes a URL: it cites ledger IDs, code hydrates the URL from the ledger, and a free-text URL not in the ledger is replaced by a visible "link removed" marker; INV-05 fails the run on a cited evidence ID that is not in the ledger (`state/evidence_ledger.py` `hydrate`, `phases/report.py` `LINK_REMOVED`, `invariants.py` `check_INV_05`).

2. How do you stop invented quotes?
Every finding carries one to three anchors of at least 8 tokens, and verify searches the canonical text for each; a finding with no resolvable anchor becomes an "Unverified" unresolved item with no recommendation (`ingest/anchor.py`, `phases/verify.py`).

3. What if the MCP server is down?
A missing key fails the run before any model call, unless `--no-tools` asks for a document-only review; a key revoked mid-run degrades to document-only and the report says so; a closed session is reopened once, and a tool is disabled only after two genuine failures (`orchestrator.py` `_run_check_tool_key`, decisions #13 and #38).

4. Why six shards?
Four shards ended stage 1 at 265.2 s and 255 s on the lab document, over the 230 s threshold that decision #31 set, so the planned next step was six; each group has at most two criteria (decision #40, `config/agent.yaml`).

5. Six shards did not bring stage 1 under 230 s this morning; was it the wrong call?
Not on the evidence: the three single-pass shards (1, 2 and 5) finished by 177.9 s, and the overrun came from three shards writing their answer twice, which is fixed (`sit_sample_ui_2/MEASUREMENT.md` "Comparison", commit `af12daf`); the second rehearsal checks it.

6. What does resume do?
`dra resume` loads the latest checkpoint, refuses on hash drift of config, prompts or text unless `--accept-drift` is given and recorded, restores the run clock, re-runs only the members and shards that had not finished, and serves tool calls that already succeeded from `tools.jsonl`, so none of them is made again (`orchestrator.py` `resume_run`, `tools/gateway.py` `SelfReplayGateway`).

7. And replay?
`dra replay` re-runs the real phases with model and tool calls served from the recorded logs and a virtual clock; a request that does not match stops with exit 4, and it reproduces exactly only at the recorded commit (`replay.py`).

8. How is cost controlled?
Calls go through `claude -p` on the subscription with the API key stripped from the child environment; effort is `medium` (research `low`); research is capped at 30 tool calls and 4 iterations; the stage limits bound every call; the page chat is capped at 20 calls and $3.00 (`config/agent.yaml` `claude_code.inherit_api_key`, decision #33, `config/stop_rules.yaml`, `ui/chat.py`).

9. How much does a run cost?
Rehearsal 1 recorded $7.37 and about $8.86 with the estimate for the two calls that ended early; these are CLI estimates, not billed amounts (`sit_sample_ui_2/MEASUREMENT.md`, `docs/LIMITATIONS.md` "Time and cost").

10. Why `medium` effort and not `high`?
On the payments design both found the same 13 of 14 flaws with precision 0.944 and 0.947, at 382 s and $5.74 against 780 s and $8.21; one document, one run per arm, exploratory (decision #33).

11. How would you re-assess an updated artefact?
Give the updated PDF and the previous version (`--v1 <pdf>`) or the frozen previous run (`--previous <run_dir>`); with `--previous` every prior finding gets exactly one status (resolved, partially addressed, still open, withdrawn with a reason), a missing status is recorded as "not re-examined" and disclosed, and a new finding in a changed section is marked a regression by code (`cli.py`, `delta.py`, INV-13).

12. Has the re-assessment run live?
Once, document-only, on the synthetic payments v1 and v2 pair, not graded against the key (`docs/LIMITATIONS.md` "Re-assessment").

13. What did the model get wrong in testing?
In rehearsal 1: three shards wrote their answer twice, one refine revision broke a rule, no finding cited the 41 external entries, one anchor was not found (FND-004), and one recommendation reversed approved decision AD-008 without the challenge label, which the run caught and disclosed as DEG-005 (`sit_sample_ui_2/MEASUREMENT.md`).

14. Can the model decide the design was not assessed?
No: its verdict schema offers `fit`, `fit_with_conditions` and `not_fit`; only code sets `not_assessed`, with reason `deadline`, `truncated` or `declined` (decision #25, `llm/outputs.py` `AssessedVerdictLabel`).

15. Why do the shards not see the research?
They start at about 3 s and research at about 110 s; waiting would add research's time to the critical path, so refine applies the evidence; a second assess pass after research is a future variant (decision #37, `sit_sample_ui_2/MEASUREMENT.md` "Stages").

16. How do you know the agent is any good?
Three synthetic designs with 14 planted flaws each, a bounded matcher, a key-blind grader and a pre-registration; on payments the concurrent agent found 13 of 14 strictly; the keys are unsigned, so every score is exploratory (`docs/ARCHITECTURE.md` section 9, decision #26).

17. What is not built, and why?
No multi-provider dropdown (the gateway seam exists; another provider is a new evaluation), no persistent memory beyond re-assessment (an overfitting channel on a small evaluation set), no hosted share link (an unseen SIT document never sits on a server), no in-run second-model verifier (an independent judge belongs in the harness where it can be blinded) (`docs/ARCHITECTURE.md` section 11).

18. What happens if I press Stop?
The run gets SIGINT, exits 130, keeps `state.json`, writes no report, and `dra resume <run_id>` continues it (decision #44 (A), `orchestrator.py` module docstring).

19. Why can I trust the clock on the page?
Every time is the record's run clock; the head clock adds only the seconds since the last event, says so, and stops with the stream; there is no progress percentage (decision #44, `ui/static/app.js` header comment).

20. How do you handle a model that refuses or a rate limit?
A refusal is retried once with professional-review framing, then recorded as declined and the phase falls back to code; a rate limit is retried with jittered exponential backoff, honouring `retry-after` on the API backend (the CLI backend gets none); no model switch happens unless `--allow-fallback` is set and recorded (`phases/_model_calls.py`, `llm/claude_code.py` `_classify` and `_backoff`, `config/agent.yaml` `llm.refusal_retries`, `allow_fallback: false`).

## 8. A two-minute closing

What I would do next with more time, in order:
1. Re-measure: the second rehearsal checks today's three fixes; then the five paired LangGraph runs, so the framework comparison stands on six pairs instead of one (`docs/HANDOVER_261004_PLANNER.md` section 2 items 1 and 3).
2. Evaluate at a size that can carry a claim: the plans are A, the full pre-registered study at $3,282; B, every test at full power with judges off and grading on 33 reviews at $1,506; C, the full agent against a single-call baseline on five documents, three runs each, at $801; the figures are CLI estimates, and nothing runs until Malcolm picks a letter (`docs/HANDOVER_261004_PLANNER.md` section 5 item 1).
3. Sign the answer keys, so scores can become confirmatory rather than exploratory (decision #26, `eval/KEY_SIGNOFF.md`).
4. Let the shards use the research: a second assess pass after research, or a rule that an answered question's evidence is cited by a finding of its criterion (decision #37, `docs/transcripts/session6/refine-keep-good.md`).
5. Close the known limits: images in the PDF are invisible to the model on the CLI backend; the search tools fetch pages on the server side, where the agent's URL policy cannot see them; the re-assessment has not run on the lab document or with tools; the agent, judge and grader are the same model family (`docs/LIMITATIONS.md`).
6. Freeze and re-record: tag the demo commit, re-record the demo runs so they replay byte for byte there (`docs/HANDOVER_261004_PLANNER.md` section 2 item 4).

The closing, to say:
"What I built is an agent that reviews a design against its own objectives, cites only what it has read, and tells you what it could not do.
I measured every design choice where it could be measured: the concurrent stage against the sequential one, medium against high effort, my loop against LangGraph, and this morning a full rehearsal on your sample that found three defects I fixed the same day.
Every one of those numbers is one document and one run per arm, and I say that out loud, because the honest next step is evaluation at scale, which I have costed in three sizes.
With more time I would run that evaluation, give the assessors the research evidence directly, and close the limits listed in the repository.
The parts that are not built are not built on purpose, and each has its reason written down."
