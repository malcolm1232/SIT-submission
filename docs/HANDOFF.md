# Handoff: continuing this project in a new session

Written 2026-10-02 so a fresh Claude Code session (any account with access to
malcolm1232/SIT) can continue without the original conversation.

## Where everything is

Branch: `claude/great-hopper-hbx7h0` (continues `claude/eloquent-sagan-ah5ttk`). All work is committed and pushed; nothing
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
  reads `SIT_MCP_API_KEY`; the agent reads `ANTHROPIC_API_KEY` only with `llm.backend: anthropic_api`.

## State of the agent code (updated 2026-10-02, second session, branch `claude/great-hopper-hbx7h0`)

- The agent is implemented end to end: `agent/README.md` module map has no stubs left.
  `ruff check agent tests` clean; `pytest -q` = 444 passed, 0 skipped (~25 s);
  `sit-review selftest` passes offline in under 1 s on the bundled fixture.
- Two LLM backends behind one protocol (ADR-010): `claude_code` (default; headless `claude -p`,
  bills to the Claude Code login) and `anthropic_api` (`ANTHROPIC_API_KEY`). Switch with
  `config/agent.yaml: llm.backend`. The Claude Code backend was live-checked on Haiku and Opus
  (single calls, resume, and the envelope tool loop on Haiku); the Anthropic backend has NOT
  been run against the real API yet.
- Verification trail: `research/audit/verify_agent_integration_editlog.md` and the subagent
  reports in `docs/transcripts/` (second session).
- Not yet built: the eval harness (matcher, metrics, grader), the robustness P0 suite as
  runnable scenarios (the fault-injection machinery and 26 fault tests exist), the `--k`,
  `dra replay` and `dra coverage` commands from the runbook.
- First live run through the Claude Code backend: see `docs/HANDOVER_FULL.md` §8.

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
