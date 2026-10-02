# `sit_review_agent`: the design-review agent

A custom, explicit state machine on the Anthropic Python SDK (`anthropic==1.11.0`) with a direct
MCP client (`mcp==2.2.0`). The decisions behind it are in `docs/DECISIONS.md` (ADR-001, 002, 006,
007 and 009). The output contract is `spec/finding.schema.json`: one `Review` holding many `Finding`s.

```
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
ruff check agent tests && pytest              # offline: no key, no network (ADR-008)
sit-review states                             # state machine as Mermaid
sit-review run design.pdf [--v1 old.pdf] [--replay fixtures/] [--record] [--plan-only] ...
sit-review explain runs/<run_id> FND-003
sit-review coverage [--run runs/<run_id>]     # criteria x sections map (default: latest run)
sit-review run design.pdf --k 3 [--profile demo]   # 3 independent runs + runs/<group>.kgroup.json
sit-review replay runs/<run_id>               # offline re-run from llm.jsonl + tools.jsonl
sit-review selftest
```

`dra` is an alias of `sit-review`, and `review` is an alias of `run`, so the commands in
`docs/DEMO_DAY_RUNBOOK.md` work unchanged.

## State machine

`ingest -> understand -> plan -> research -> assess -> refine -> verify -> report`
(`states.py`: `PHASE_ORDER`, `TRANSITIONS`, `ON_CAP`, `EFFORT_KEY`, `PROVENANCE_PHASE`).

`orchestrator.Orchestrator.run` runs the phases in order. It skips phases that are disabled in
`config/agent.yaml` (only `research` and `refine` may be disabled). Before `plan`, `research`,
`assess` and `refine` it checks the between-phase caps (deadline and token budget); if one fires,
the run jumps to `verify` (or from `research` to `assess`), so a report is still produced and
the cap is recorded as a degradation. After every completed phase it writes an atomic checkpoint
(ADR-009) and prints a progress line. Errors are typed, and each maps to an exit code:
0 ok, 2 usage, 3 LLM unavailable, 4 stage crash, 5 resume drift, 130 interrupted. A run that
degrades and discloses it (a deadline cut, an answer truncated twice at the output cap, a model
that declined a stage) still writes its report and exits 0 with manifest outcome
`completed_degraded`.

## Module map

Status as checked by the integration verifier (2026-10-02): every row is implemented and covered
by offline tests; "UNVERIFIED live" marks behaviour that only a laptop run can confirm (ADR-008).

| Module | Role | Status |
|---|---|---|
| `models.py` | Pydantic v2 copy of `spec/finding.schema.json` (Finding, DocAnchor, EvidenceItem, Recommendation, Provenance, LedgerEntry, RegistryEntry, SoundArea, Verdict, StopReason, ResearchLog / ResearchLogEntry, RunManifest, Review, plus `ManifestExtra` for REPRODUCIBILITY §8). The schema's `allOf` rules are validators | done |
| `config.py` | Typed loader for `config/*.yaml`, CLI overrides, `EffectiveConfig.sha256()` | done |
| `states.py`, `stop_rules.py` | Phase enum and transitions; `@register` stop-rule registry; closed `StopReasonCode` | done |
| `orchestrator.py` | `Orchestrator.run`; `run_review` (missing MCP key check before anything is built (INF-08), run dir, gateways, run limits attached to the LLM stack (`llm/runtime.py`), background MCP warm-up started right after the tool stack, LLM preflight before `models.retrieve` (NET-02), the schedule's `process:` faults around phases (new runs only), exit-code mapping, `failure.json` for every failure after the run dir exists) and `resume_run` (ADR-009: drift check, ledger truncation, `SelfReplayGateway`, call IDs continued via `llm.gateway.prepare_resume` and `CallIds.advance_to`) | done |
| `context.py` | `RunContext`: the run state plus services, passed to every phase | done |
| `state/run_state.py` | `RunState`, the serialisable checkpoint payload | done |
| `state/evidence_ledger.py` | Append-only ledger with `EV-nnn` IDs, `ledger.jsonl` journal, `hydrate()` | done |
| `state/decision_registry.py` | `AD-nnn` registry, `freeze()`, hash per iteration, INV-10 checks | done |
| `state/checkpoint.py` | Atomic per-phase checkpoints, drift check, journal truncation | done |
| `llm/gateway.py` | `LLMGateway` protocol, `LLMRequest` / `LLMResult` / `Usage`; `LLMCallLog` (redacts secrets and canaries, flags `resumed: true`); `AnthropicGateway` (streamed `output_config.format`, gateway-owned retries, typed stop reasons, `models_retrieve`, `preflight`); `FakeGateway`; `FaultInjectingLLMGateway`; `prepare_resume` | done (A, B); Anthropic API behaviour UNVERIFIED live |
| `llm/outputs.py` | Structured-output draft types for each phase (`UnderstandOutput` … `ReportOutput`, `FindingDraft`) and `llm_facing_schema` (the schema both backends send) | done |
| `llm/prefix.py` | Byte-stable cached prefix: PDF block plus canonical text, one breakpoint | done |
| `llm/claude_code.py` | `ClaudeCodeGateway`: the `LLMGateway` over headless `claude -p` (subscription / cloud credits, ADR-010); envelope tool loop, forked CLI sessions per call (`--resume --fork-session`), retry policy, `llm.jsonl` logging, `preflight` | done; envelope tool loop UNVERIFIED live on Opus |
| `llm/backend.py` | `build_llm_gateway` (picks `ClaudeCodeGateway` or `AnthropicGateway` from `llm.backend`), `supports_native_pdf` | done |
| `llm/usage_budget.py` | `add_usage`: the one way phases add a call's usage to `state.budget` (read by the `budget_tokens` stop rule), for a result (`LLMResult.usage`) and for a failed call (`LLMError.usage`, 2026-10-03) | done |
| `llm/runtime.py` | Run limits every gateway honours (2026-10-02): `RunDeadline` (attempt timeout = min(`llm.timeout_s`, time left - reserve), LLM-05), `ContextGuard` (pre-send size estimate, LLM-10), `FirstCallNetwork` (NET-02); `attach_runtime`, `build_runtime` | done; live behaviour UNVERIFIED |
| `tools/gateway.py` | `ToolGateway` protocol, `ToolSpec` / `ToolResult` / `ToolAttempt`, `CallIds`, the layer stack and `build_tool_gateway`: `MCPToolGateway`, `ReplayGateway`, `RecordingGateway`, `FakeToolGateway`, `FaultInjectingGateway`, `SelfReplayGateway`, `PolicyToolGateway`, `LoggingToolGateway` | done (B, C); live MCP behaviour UNVERIFIED (auth header, cold starts) |
| `tools/mcp_client.py` | Live MCP plumbing for `MCPToolGateway`: httpx2 + streamable-HTTP session factory with an error-status hook, failure classification, one owner task per server session, `find_layer` / `start_warm_up` | done (B) |
| `tools/policy.py` | Pure policy checks for `PolicyToolGateway`: URL policy (`fetch_only_from_results`, added query strings), argument sanitiser (secrets, canaries, key-shaped tokens, bulk text), `scrub_args` | done (B) |
| `tools/fault_apply.py` | Rule matching shared by the MCP and LLM fault injectors (seeded `flaky`, `offline` windows, latency) | done (B) |
| `tools/faults.py` | Robustness fault-schedule model and loader (refuses malformed `process:` entries) | done |
| `tools/cassette.py` | Cassette key, argument canonicalisation, `Redactor` | done |
| `tools/sources.py` | `ExternalSource`; `extract_sources` (search hits, JSON records, fetched pages), `classify_authority` (host lists from `config/url_policy.yaml` `authority:`, OVF-07), `independence_key` | done (B) |
| `ingest/text.py` | Normalisation and the `[[PAGE n]]` marker | done |
| `ingest/pdf.py` | `ingest()` (pdfplumber), `Document` (pages, sections, requirement index, PDF block) | done (heading detection is heuristic; since 2026-10-02 section numbers must go forward, so numbered list items inside a section are no longer extra sections) |
| `ingest/anchor.py` | `verify_anchor`, `verify_finding_anchors`, anchor-table rows | done |
| `phases/ingest.py`, `verify.py`, `report.py` | Ingest (pdfplumber in a worker thread), anchor verification with one repair turn and registry-anchor settlement after `understand`, hydration, report assembly and invariant gate | done (C) |
| `phases/understand.py`, `plan.py`, `assess.py`, `refine.py` | The model phases of workstream A | done (A) |
| `phases/_model_calls.py` | Private plumbing of A's phases: `call_model` (refusal reframing, schema repair, `max_tokens` retry, bookkeeping), anchor fixes (`extend_quote`), finding normalisation, coverage reconciliation, `resolve_evidence` (model `NEW-n` doc/inference evidence into the ledger; invented IDs dropped) | done (A) |
| `phases/research.py` | The hand-written research tool loop (B) | done (B) |
| `report/render.py`, `report/explain.py`, `manifest.py`, `selftest.py` | Markdown report, `explain`, manifest (refusals and fallbacks merged from run state and gateway), `selftest` and `preflight` | done (B, C) |
| `invariants.py` | `check_INV_03` … `check_INV_10`, `check_all` (ports `spec/validate_examples.py`) | done; the outbound-request half of INV-08 runs in the harness |
| `prompts.py` | Prompt bundle, `PROMPTS.lock`, StrictUndefined rendering | done |
| `rundir.py`, `progress.py`, `clock.py`, `hashing.py`, `errors.py`, `paths.py` | Run-directory layout and JSONL journal; progress lines and heartbeat; `FakeClock`; hashes; typed errors and exit codes | done |
| `cli.py` | `sit-review` / `dra`: `run` (`review`, with `--k` and `--profile`), `resume`, `explain`, `coverage`, `replay`, `selftest`, `preflight` (`--profile`), `states`; typed errors to exit codes, never a traceback (INV-11) | done (C, W2) |
| `kruns.py` | `--k N`: N independent sequential runs `<group>-k1..kN`, intention-to-treat (failures counted, never rerun; Ctrl-C or a setup error stops the group), `extra.k_index` and `k_group.json` per run, group manifest `<run_root>/<group>.kgroup.json` with per-run outcome, verdict, findings, cost and wall time; verdict agreement is over fitness verdicts (a `not_assessed` run is counted separately and never as the modal verdict) | done (W2) |
| `report/coverage.py` | `dra coverage`: criteria x sections map from the run directory (`nX` findings with worst severity, `ok` = checked, no issue, `?` = the criterion raised findings that verify did not keep, `-` = not applicable, not assessed or not reported, sound areas); falls back to the `report.md` coverage table for report-only run directories | done (W2) |
| `replay.py` | `dra replay`: re-runs a recorded run through the real phases with `ReplayLLMGateway` (recorded `llm.jsonl` outputs, request hash checked per backend) and `JournalReplayToolGateway` (recorded `tools.jsonl` results, strict), on a `ReplayClock` that follows the recorded timeline; compares the new `report.json` with the recorded one and stamps the output "replayed evidence" | done (W2); replay of a live `claude_code` run with live tools needs the logging below |

## The phase contract

Every phase is `class XPhase: name: PhaseName; async def run(self, ctx: RunContext) -> RunContext`
(`phases/base.py`). `run` is async because MCP and the async Anthropic client are async, and the
background MCP warm-up overlaps `ingest` and `understand`. Rules:

1. Read from `ctx.state`, `ctx.documents` and `ctx.config`. Write only the `RunState` fields that
   the phase docstring lists under "Writes".
2. Call the model only through `ctx.llm.call(LLMRequest(...))`. Use one `conversation_id` per
   phase and `effort=ctx.config.effort_for(phase)`; the gateway rejects an effort change within a
   conversation (ADR-002). Start the conversation with `llm.prefix.start_conversation(...)` so the
   cached prefix is identical across phases. Render prompts only through `ctx.prompts.render`, and
   record call IDs in `ctx.state.llm_calls[phase]`.
3. Call tools only through `ctx.tools`. Add evidence only through `ctx.ledger`. The model cites
   `EV-` IDs and never writes a URL.
4. Expected failures (a tool down, a refusal after its one retry, a budget hit) become
   `ctx.state.add_degradation(...)` and the phase completes. Only gateway errors raised after
   the retry budget, and bugs, propagate; the orchestrator then flushes state and maps the error
   to an exit code.
5. A phase must be safe to re-run from the previous checkpoint (resume).
6. Emit a progress line at least every 10 s (`ctx.emit`, `progress.heartbeat`).

Data flow: `understand` writes `UnderstandOutput` into `intent_summary` and the registry, which
is then frozen. `plan` writes `PlanOutput` into `state.plan`. `research` runs the tool loop and
writes ledger entries, question answers and the stop reason. `assess` writes `FindingDraft`s,
sound areas and coverage. `refine` revises the drafts. `verify` checks anchors, writes
`anchors.json` and hydrates the drafts into `Finding`s. `report` produces the verdict text,
assembles the `Review`, runs the invariants, and writes `report.json` / `report.md` and the
manifest.

## Workstreams for the three parallel implementers

All three workstreams are merged; `tests/test_pending.py` (the skipped placeholders) was removed
once every entry was covered by a real test. Cross-workstream seams are pinned by
`tests/test_integration_seams.py`, `tests/test_e2e_synthetic.py` (real phases on a synthetic PDF,
doc-only, resume) and `tests/test_adversarial_invariants.py` (INV-03..INV-11).

| Workstream | Owns | Done when |
|---|---|---|
| **A: model calls** (phase 1) | `llm/gateway.py` `AnthropicGateway` (build_body, streaming call, retry policy, typed stop-reason errors, `llm.jsonl` logging, `models_retrieve`, `preflight`), `llm_facing_schema`; `phases/understand.py`, `plan.py`, `assess.py`, `refine.py`; `prompts/system.md`, `understand.md`, `plan.md`, `assess.md`, `refine.md` | Phase tests with `FakeGateway` pass; a gateway request-shape test against a fake SDK client passes |
| **B: tools and research** (phase 2) | `tools/gateway.py` `MCPToolGateway` (reuse the `scripts/probe_mcp_servers.py` client pattern), `PolicyToolGateway`, `FaultInjectingGateway`; `llm/gateway.py` `FaultInjectingLLMGateway`; `tools/sources.py`; `phases/research.py`; `prompts/research.md`; `selftest.run_preflight` | The research loop passes on `ReplayGateway` + `FakeGateway`; the runbook §7 drills pass at L0 with `FakeClock` |
| **C: verification, report and run** (phase 3) | `phases/ingest.py`, `verify.py` (`hydrate_finding`), `report.py` (`assemble_review`); `report/render.py` and the template; `report/explain.py`; `manifest.py`; `orchestrator.run_review` / `resume_run`; `tools/gateway.py` `SelfReplayGateway`; `selftest.run_selftest` plus its fixture script; `prompts/verify.md`, `report.md` | `sit-review selftest` passes INV-03..10 offline; the resume tests pass (ADR-009) |

Shared rule: A and B both touch `llm/gateway.py`, but in different classes. Neither edits the
other's class.

## Interface freeze

The following are **frozen**: every public signature, dataclass and Pydantic model, protocol,
enum and constant in `models.py`, `config.py` (and the YAML keys), `states.py`, `context.py`,
`state/*`, `llm/gateway.py` (protocol and request/result types), `llm/outputs.py`,
`tools/gateway.py` (protocol, `ToolSpec`, `ToolResult`, `ToolErrorClass`, layer constructors),
`tools/faults.py`, `ingest/*`, `invariants.py`, `errors.py`, `rundir.py` and `phases/base.py`.

- Implementers fill in stub bodies; they do not change these interfaces.
- Adding a new private helper, or a new module that only your workstream uses, is fine.
- A frozen interface that has to change needs an "interface change" note in the PR description
  that names every caller. That change is made **alone**, in its own PR, before any work that
  depends on it, and all three workstreams rebase onto it.
- Interface changes made under this rule (the commit message is the "interface change" note):
  2026-10-03, `errors.LLMError` gained the keyword `usage` (default `None`), the usage a failed call
  was billed for. Writers: `AnthropicGateway`, `ClaudeCodeGateway`, `FakeGateway`,
  `FaultInjectingLLMGateway` (`schema_violation`), `ReplayLLMGateway` (via `llm.gateway.billed`).
  Readers: `phases/_model_calls.call_model`, `phases/research.py`, `phases/verify.py`,
  `phases/report.py` (via `llm.usage_budget.add_usage`). Additive: no existing constructor call changes.
- `models.py` changes only together with `spec/finding.schema.json`. `tests/test_models.py`
  checks enum parity and validates against the schema on every run.
- `config/agent.yaml` lines 1-12, `stop_rules.yaml` lines 1-8 and `tools.yaml` lines 1-17 are
  pinned by `tests/test_config_layout.py` (runbook §4.1). Add new keys below those lines.
- Prompt edits need `python -m sit_review_agent.prompts --write-lock`, because
  `tests/test_prompts.py` fails on a stale lock.

## Decisions taken here that the docs left open

- **Page marker:** `[[PAGE n]]`, as in ADR-006, `spec/validate_examples.py` and the grader input.
- **Per-document canonical text:** each document gets `runs/<id>/text/<doc_id>.pages.txt` instead
  of a single `doc.pages.txt`, because delta mode has two documents. `DocumentMeta.text_path`
  points at the file.
- **Ledger files:** the ledger journal is `ledger.jsonl`, appended per entry; checkpoints store its
  offset. `ledger.json` is the snapshot written by `report`.
- **Effort for `understand`:** `understand` uses the `plan` effort level, because the runbook's
  pinned `effort:` block has no `understand` key. All levels are `high` (USER_DECISIONS #1).
- **Provenance phase:** `refine` findings carry provenance phase `revise`, and `ingest` and `plan`
  never create findings (`states.PROVENANCE_PHASE`).
- **Iteration cap:** the research-iteration cap reports `budget_tool_calls` with detail
  `max_research_iterations`, because the closed stop-reason enum has no iteration code.
- **Model tool names:** tools appear to the model as `<server>__<tool>`; tool call IDs are
  `call-nnnn` and LLM call IDs are `llm-nnnn`.
- **Criteria format:** each criterion has `question` (with `description` accepted as an alias,
  so the runbook's 4-line append works), `lab_ref`, and `kinds`, a list where empty means any kind.
- **Browser server:** `mcp-browser-automation-pw` is off by default until the probe shows
  per-client isolation (fresh_eyes N15).
- **Config paths:** paths in `config/` are relative to the `agent.yaml` directory; run, cassette
  and fixture paths are repo-relative.

### Replay (`dra replay`)

`dra replay <run_dir>` re-runs a **completed** run into `<run_root>/<id>-replay-<hex>` (`mode: replay`)
with no network. Model calls are served in order from the run's `llm.jsonl` (the call IDs the final
`state.json` lists per phase, so a stage re-run by `resume` is served from its re-run); each request
must match the recorded phase, purpose and request hash, or the replay stops (exit 4, never an
invented answer). Recorded failures (refusal, truncation, schema error, injected faults) are raised
again. Tool calls are served once each from `tools.jsonl`. The replayed `report.json` must equal the
recorded one apart from run IDs, times and the run manifest (else exit 4, differences in
`replay.json`); `report.md` gets a "Replayed evidence" banner and the manifest a deviation.

Needs, in the run directory: `report.json`, `effective_config.json`, `llm.jsonl` with response
`content`, `state.json` or `checkpoints/`, `tools.jsonl` if tools were called, and the input document
at its recorded path (or `--pdf`; a moved text input is rebuilt from `text/`). The prompts bundle
must be the one the run used. A directory that lacks any of these is refused with exit 2.

**Tool catalogue (open logging gap).** Research offers the model the tool list from
`list_tools()`; replay must offer the same list. It is recovered from the Anthropic request body in
`llm.jsonl`, or from the cassette directory of a `replay`/`fake`/`record` run. A `live` run on the
`claude_code` backend records neither, so its research stage cannot be replayed until the gateways
log it: either a `tools` key (`request.tools`) on the attempt-0 `llm.jsonl` entry of
`ClaudeCodeGateway.call`, or one line per `list_tools()` call in `runs/<id>/tools_list.jsonl`
(`{"listed_at", "tools": [{server, name, description, input_schema, capability}]}`, written by
`LoggingToolGateway.list_tools`). Replay already reads both.

### Runtime policies (2026-10-02; robustness LLM-05, NET-02, INF-08, LLM-10, OVF-07)

- **Deadline inside model calls.** With the `deadline` rule active, every model attempt's timeout is
  `min(llm.timeout_s, time left - reserve)` from the one run clock; the reserve is
  `stop_rules.report_reserve_seconds` (verify + report) and, for research, also
  `assess_reserve_seconds`. A cut attempt raises `LLMDeadlineError` and is not retried; no attempt
  or retry starts with less than 10 s left. Research ends (`deadline`); a cut or skipped assess gives
  a report that says "out of time before assessment" with no finding and the verdict `not_assessed`
  (confidence 0, shown as "Not assessed (out of time before assessment)" in `report.md`); the same
  verdict is reported when the assess answer is truncated twice at the output cap (LLM-07) and when the
  model declines the assess call twice (LLM-06), each with its own reason. `not_assessed` is set by
  code only: the model's output schema offers `fit`, `fit_with_conditions` and `not_fit`
  (`llm.outputs.AssessedVerdictLabel`). A cut refine keeps the assess findings. Default deadline 3600 s; the demo uses `--profile demo` (540 s).
- **A deadline that does not fit its reserves is announced.** `--deadline` and a profile each set one
  side of the sum, so the pair can be inconsistent (`--deadline 300` against the default 180 s + 600 s).
  The run then prints `WARN deadline 300 s leaves research no time ...` (or `... no model call can run
  before verify ...`) on its first progress lines (`llm.runtime.deadline_warnings`); it still runs.
- **No network at start.** Connection-type errors on the first model call of a run get a 10 s window,
  then exit 3 "no network"; `anthropic_api` runs its no-retry preflight before `models.retrieve`.
- **Missing MCP key.** Live tool transport, servers enabled, key unset: exit 2 before any model call.
- **Size before sending.** Input estimated at 3 characters per token (+2,000 tokens per native PDF
  page) against 80 % of the context window; over it, `LLMContextTooLongError` (exit 2), never sent.
  Errors raised before an attempt is made are logged to `llm.jsonl` with `sent: false` (for replay).
- **Logs.** `ClaudeCodeGateway` logs `elapsed_s` and `timeout_s`; tool listings go to `tools_list.jsonl`.
- **Output cap (2026-10-03).** `config/agent.yaml` `max_tokens` is 128000, the model's maximum and the
  largest value `config.py` accepts. A truncated answer gets one retry: at double the cap when the
  configured value is below 128000, else at the same cap. A second truncation is never retried again and
  never repaired (LLM-07): the stage degrades like a deadline cut (Session 4 ruling). The degradation
  "the <stage> answer was truncated twice at the output cap" names the cap and both call IDs, and the
  stage continues with its deadline fallback: understand without intent or registry, plan with one
  document-only question per criterion, assess with no findings and the verdict `not_assessed` ("Not
  assessed (answer truncated twice at the output cap)"), refine with the assess findings kept unrefined.
  The run writes its report and exits 0 (`completed_degraded`); the manifest lists both calls in
  `extra.model.truncations`, and their tokens and cost are in its totals
  (`tests/robustness/test_robustness_regressions.py` and `tests/test_truncation_fallback.py`). Research,
  verify and report make no truncation retry: one truncation already ends research (`error`,
  `max_tokens`), skips the anchor repair, or gives the verdict by rule. Known limitation: a second
  truncation is not recovered by splitting the stage, so an assessment that does not fit the cap stays
  unassessed; `sit-review resume` on such a run serves the finished report and makes no model call, and a
  rerun is a new run that may or may not fit (answer length varies between calls). `ClaudeCodeGateway` passes the cap as `CLAUDE_CODE_MAX_OUTPUT_TOKENS`
  (checked on Haiku with Claude Code 2.1.287: a cap of 256 was enforced). When the cap is hit, `claude -p`
  does not report `stop_reason: max_tokens`: after its own recovery turns it returns an error result
  ("... exceeded the N output token maximum ..."), which the gateway types as `LLMTruncatedError` and does
  not retry. Whether Opus 5.5 through the CLI can emit more than 64,000 tokens in one call is UNVERIFIED.

### LLM backends (ADR-010)

`config/agent.yaml` `llm.backend` selects the live gateway through `llm.backend.build_llm_gateway`:
`claude_code` (default; headless Claude Code, billed to the Claude subscription or cloud credits) or
`anthropic_api` (`ANTHROPIC_API_KEY`). Both implement the same `LLMGateway` protocol, so phases do not
change. With every CLI tool switched off, `ClaudeCodeGateway` cannot emit native `tool_use` blocks.
When a request carries `tools`, it renders them into the system prompt (`render_tool_catalogue`) and
asks, via `--json-schema`, for an envelope `{"tool_calls": [{id, name, input}], "final": <schema> | null}`.
A non-empty `tool_calls` becomes a `tool_use` result with `ToolUse`s (ids made unique per run as
`call-nnnn`). `tool_calls: []` with `final` becomes `end_turn` with `parsed`. `tool_result` blocks are sent
back as text. Each call is a new CLI session forked from the last good one (`--resume <id> --fork-session`), and only the new
user turns go to stdin. The gateway rejects assistant turns it did not produce. `ClaudeCodeGateway.native_pdf`
is `False`: native PDF blocks are dropped (logged as `pdf_dropped`), and callers should check
`supports_native_pdf(gw)` (`getattr(gw, "native_pdf", True)`) before building the PDF block.
