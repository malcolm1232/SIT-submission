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
0 ok, 2 usage, 3 LLM unavailable, 4 stage crash, 5 resume drift, 130 interrupted.

## Module map

Status as checked by the integration verifier (2026-10-02): every row is implemented and covered
by offline tests; "UNVERIFIED live" marks behaviour that only a laptop run can confirm (ADR-008).

| Module | Role | Status |
|---|---|---|
| `models.py` | Pydantic v2 copy of `spec/finding.schema.json` (Finding, DocAnchor, EvidenceItem, Recommendation, Provenance, LedgerEntry, RegistryEntry, SoundArea, Verdict, StopReason, ResearchLog / ResearchLogEntry, RunManifest, Review, plus `ManifestExtra` for REPRODUCIBILITY §8). The schema's `allOf` rules are validators | done |
| `config.py` | Typed loader for `config/*.yaml`, CLI overrides, `EffectiveConfig.sha256()` | done |
| `states.py`, `stop_rules.py` | Phase enum and transitions; `@register` stop-rule registry; closed `StopReasonCode` | done |
| `orchestrator.py` | `Orchestrator.run`; `run_review` (run dir, gateways, manifest, background MCP warm-up started right after the tool stack, LLM preflight, exit-code mapping, `failure.json` for every failure after the run dir exists) and `resume_run` (ADR-009: drift check, ledger truncation, `SelfReplayGateway`, call IDs continued via `llm.gateway.prepare_resume` and `CallIds.advance_to`) | done |
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
| `tools/gateway.py` | `ToolGateway` protocol, `ToolSpec` / `ToolResult` / `ToolAttempt`, `CallIds`, the layer stack and `build_tool_gateway`: `MCPToolGateway`, `ReplayGateway`, `RecordingGateway`, `FakeToolGateway`, `FaultInjectingGateway`, `SelfReplayGateway`, `PolicyToolGateway`, `LoggingToolGateway` | done (B, C); live MCP behaviour UNVERIFIED (auth header, cold starts) |
| `tools/mcp_client.py` | Live MCP plumbing for `MCPToolGateway`: httpx2 + streamable-HTTP session factory with an error-status hook, failure classification, one owner task per server session, `find_layer` / `start_warm_up` | done (B) |
| `tools/policy.py` | Pure policy checks for `PolicyToolGateway`: URL policy (`fetch_only_from_results`, added query strings), argument sanitiser (secrets, canaries, key-shaped tokens, bulk text), `scrub_args` | done (B) |
| `tools/fault_apply.py` | Rule matching shared by the MCP and LLM fault injectors (seeded `flaky`, `offline` windows, latency) | done (B) |
| `tools/faults.py` | Robustness fault-schedule model and loader | done |
| `tools/cassette.py` | Cassette key, argument canonicalisation, `Redactor` | done |
| `tools/sources.py` | `ExternalSource`; `extract_sources` (search hits, JSON records, fetched pages), `classify_authority`, `independence_key` | done (B) |
| `ingest/text.py` | Normalisation and the `[[PAGE n]]` marker | done |
| `ingest/pdf.py` | `ingest()` (pdfplumber), `Document` (pages, sections, requirement index, PDF block) | done (heading detection is heuristic: numbered lists inside tables become extra sections) |
| `ingest/anchor.py` | `verify_anchor`, `verify_finding_anchors`, anchor-table rows | done |
| `phases/ingest.py`, `verify.py`, `report.py` | Ingest (pdfplumber in a worker thread), anchor verification with one repair turn and registry-anchor settlement after `understand`, hydration, report assembly and invariant gate | done (C) |
| `phases/understand.py`, `plan.py`, `assess.py`, `refine.py` | The model phases of workstream A | done (A) |
| `phases/_model_calls.py` | Private plumbing of A's phases: `call_model` (refusal reframing, schema repair, `max_tokens` retry, bookkeeping), anchor fixes (`extend_quote`), finding normalisation, coverage reconciliation, `resolve_evidence` (model `NEW-n` doc/inference evidence into the ledger; invented IDs dropped) | done (A) |
| `phases/research.py` | The hand-written research tool loop (B) | done (B) |
| `report/render.py`, `report/explain.py`, `manifest.py`, `selftest.py` | Markdown report, `explain`, manifest (refusals and fallbacks merged from run state and gateway), `selftest` and `preflight` | done (B, C) |
| `invariants.py` | `check_INV_03` … `check_INV_10`, `check_all` (ports `spec/validate_examples.py`) | done; the outbound-request half of INV-08 runs in the harness |
| `prompts.py` | Prompt bundle, `PROMPTS.lock`, StrictUndefined rendering | done |
| `rundir.py`, `progress.py`, `clock.py`, `hashing.py`, `errors.py`, `paths.py` | Run-directory layout and JSONL journal; progress lines and heartbeat; `FakeClock`; hashes; typed errors and exit codes | done |
| `cli.py` | `sit-review` / `dra`: `run` (`review`), `resume`, `explain`, `selftest`, `preflight`, `states`; typed errors to exit codes, never a traceback (INV-11) | done (C) |

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
