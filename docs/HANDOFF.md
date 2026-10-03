# Handoff: continuing this project in a new session

Written 2026-10-02 so a fresh Claude Code session (any account with access to
malcolm1232/SIT) can continue without the original conversation.

## Where everything is

Branch: `claude/happy-darwin-d0bl94` (continues `claude/great-hopper-hbx7h0`, which continues `claude/eloquent-sagan-ah5ttk`). All work is committed and pushed; nothing
lives only in the original cloud session.

Read in this order (about 30 minutes):
1. `README.md` (layout)
2. `docs/DECISIONS.md` and `docs/USER_DECISIONS.md` (what has been decided and why)
3. `research/audit/fresh_eyes.md` (prioritised build plan; the "minimum viable agent" section)
4. `eval/EVAL_PLAN.md` (Tier A: 132 runs, about $565-640 all-in, about 18 owner hours)
5. `agent/README.md` (module map and the interface freeze rule) and `harness/README.md` (the `sit-eval` harness)
7. `docs/HANDOVER_FABLE.md`: the handover for the SIT FABLE advisor session (decisions are delegated to it; the owner starts it)
6. `docs/HANDOVER_FULL.md` §10 (state at the end of session 3 and the next steps), §9, §6

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
- Third session (branch `claude/happy-darwin-d0bl94`): the evaluation harness (`harness/sit_eval`,
  `sit-eval score` and `sit-eval grade`) and the robustness P0 suite (`tests/robustness/`) are built
  and verified; ten agent defects found by the suite are fixed. `pytest -q` = 865 passed, 0 skipped.
  First live pilot scoring and grading of the first live run: `docs/HANDOVER_FULL.md` §9.
- Not yet built: the `--k`, `dra replay` and `dra coverage` commands from the runbook; `process:`
  entries in `--faults` are silently ignored.
- First live run through the Claude Code backend: see `docs/HANDOVER_FULL.md` §8.

**State on 2026-10-03 (latency redesign).**
The agent's phase structure is being redesigned for latency (`docs/DECISIONS.md` ADR-011 and ADR-012, both Proposed; `docs/USER_DECISIONS.md` #31): a concurrent first stage of understand, plan and four assess shards, a revision-only refine, a verdict-only model call and a code-rendered report, with stage limits at 265 / 465 / 530 s on the 540 s demo profile.
The build is on branches `s4/w1-latency` (streamed CLI output, salvage, stage limits), `s4/w2-latency` (stage orchestration and the new refine and verdict calls) and `s4/w3*-latency` (replay, manifest and these documents), none of them integrated yet.
Next: the integration pass, then the first timed rehearsal on payments v1, which confirms or replaces the predicted 443 s document-only and about $5.4 per FULL run; `docs/BUDGET.md` and the Tier A plan are redone after it.
What stays the owner's: the scored pilot and the with-tools rehearsal (which waits for the MCP key), the Tier A budget approval, Opus fast mode, the signature on the S-dev keys, and any reversal of ruling #31 (the evaluated agent at `medium`).
The first with-tools run on the lab's own sample document exists at `docs/live_runs/sit_sample_tools_1/` (owner's run, 428.0 s, $5.54, `fit_with_conditions` 0.72, measured in its `MEASUREMENT.md`): every `search_web` call failed on a closed MCP session that the gateway classifies as a tool error, and its `text/` folder must stay out of any public snapshot.

## Owner tasks on the critical path (cannot be delegated)

1. DONE 2026-10-03: the owner ran `scripts/probe_mcp_servers.py` on his Mac at 11:24.
   Results: `research/robustness/mcp_probe_results.redacted.json` (the raw
   `mcp_probe_results.json` name stays gitignored); findings:
   `research/robustness/mcp_probe_findings.md`. `Authorization: Bearer` works on all
   four servers and is now `config/tools.yaml` `auth_header`.
2. Report which API keys exist (Anthropic / OpenAI / Google) so the judge branch
   in `docs/DECISIONS.md` ADR-003 can be closed.
3. SUPERSEDED 2026-10-03 (`docs/USER_DECISIONS.md` #35): there is no answer key
   for the SIT Memory Platform PDF; it is a demo and rehearsal document, and the agent
   may run on it.
4. Approve the Tier A budget in `docs/BUDGET.md` §6.

## Open P0/P1 items

See the action lists at the end of `research/audit/research_audit.md`,
`research/audit/fresh_eyes.md`, and `research/audit/verify_*.md`. Highest value:
thin-slice agent, measured latency on the laptop, human SIT key, sealing the keys.
