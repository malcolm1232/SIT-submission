# Handoff: continuing this project in a new session

Written 2026-10-02 so a fresh Claude Code session (any account with access to
malcolm1232/SIT) can continue without the original conversation.

## Where everything is

Branch: `claude/eloquent-sagan-ah5ttk`. All work is committed and pushed; nothing
lives only in the original cloud session.

Read in this order (about 30 minutes):
1. `README.md` (layout)
2. `docs/DECISIONS.md` and `docs/USER_DECISIONS.md` (what has been decided and why)
3. `research/audit/fresh_eyes.md` (prioritised build plan; the "minimum viable agent" section)
4. `eval/EVAL_PLAN.md` (Tier A: 132 runs, about $565-640 all-in, about 18 owner hours)
5. `agent/README.md` (module map and the interface freeze rule) once the skeleton lands

## Operating rules that were in force

- Coordinator stays thin; all substantive work is delegated to subagents on **Opus**
  (never Fable; cost). One subagent per deliverable, each writes only inside its
  own folder, never runs git. Coordinator commits and pushes after each lands.
- Every deliverable gets a verification pass by a separate subagent afterwards.
- Agent model is Opus 5.5 for every call; effort may be high. Grader is Opus 5.5
  high plus a different-provider judge if a key exists (pending the key report).
- Repo is private. Answer keys are still plaintext; `docs/SEALING.md` is the plan.
- Secrets: never commit the SIT MCP key or any API key. `scripts/probe_mcp_servers.py`
  reads `SIT_MCP_API_KEY`; the agent reads `ANTHROPIC_API_KEY`.

## State of the agent code

- `agent/`, `config/`, `prompts/`, `tests/`, `pyproject.toml`: skeleton with frozen
  interfaces (if present when you read this; otherwise the skeleton build was
  interrupted and should be re-run from the brief in `agent/README.md` or the
  fresh-eyes "minimum viable agent" section).
- Next build steps, in order, each as its own subagent with disjoint module ownership:
  1. `llm/gateway.py` (AnthropicGateway with structured outputs, caching, typed errors)
     and `ingest/pdf.py`.
  2. `tools/gateway.py` (direct MCP client, fault injection, record/replay) using the
     verified pattern in `scripts/probe_mcp_servers.py`.
  3. `phases/*` and `orchestrator.py` (the state machine), `report/`, `cli.py`.
  4. Eval harness: matcher + metrics from `research/methodology/metrics.md`, grader
     from `research/grading/grader_prompt.md`, using `spec/` schemas.
  5. Robustness tests from `research/robustness/scenarios.md` P0 list (81 scenarios).

## Owner tasks on the critical path (cannot be delegated)

1. Run `scripts/probe_mcp_servers.py` on a laptop (see `scripts/README.md`) and
   commit the redacted `mcp_probe_results.json` under `research/robustness/`.
2. Report which API keys exist (Anthropic / OpenAI / Google) so the judge branch
   in `docs/DECISIONS.md` ADR-003 can be closed.
3. Write the human answer key for the SIT Memory Platform PDF BEFORE any agent
   run on it, per `eval/human_labelling_protocol.md`.
4. Approve the Tier A budget in `docs/BUDGET.md` §6.

## Open P0/P1 items

See the action lists at the end of `research/audit/research_audit.md`,
`research/audit/fresh_eyes.md`, and `research/audit/verify_*.md`. Highest value:
thin-slice agent, measured latency on the laptop, human SIT key, sealing the keys.
