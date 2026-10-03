# Tool orchestration

This file answers lab §5.3 "tool orchestration approach".
The model never talks to a tool server directly: it asks for tool calls, and one gateway made of stacked layers decides whether each call is allowed, runs it, records it and turns its result into numbered evidence.
The servers scale to zero, so the run warms them in the background while the document is being read, and a server that fails is cut off without stopping the review.
The architecture text is `docs/ARCHITECTURE.md` §5; the measured behaviour of the four SIT servers is `research/robustness/mcp_probe_findings.md`.

## Where each part lives

| Part | Where it is implemented or configured |
|---|---|
| The layer stack: logging, policy, self-replay on resume, fault injection, recording, then the live client, a cassette or a fake | `agent/sit_review_agent/tools/gateway.py` `build_tool_gateway` |
| The direct MCP client, one long-lived session per server | `agent/sit_review_agent/tools/mcp_client.py` |
| Which servers are on, the auth header, connect and call timeouts, the idle-session reopen | `config/tools.yaml`, `config/endpoints.yaml` |
| The closed-session rule: reopen once, retry once, disable a tool only after two genuine failures | `agent/sit_review_agent/tools/gateway.py`, `docs/USER_DECISIONS.md` #38 |
| The background warm-up at the start of a run, and `dra preflight --warm` before one | `agent/sit_review_agent/orchestrator.py`, `agent/sit_review_agent/cli.py` |
| The allowlist, the URL policy and the argument sanitiser | `agent/sit_review_agent/tools/policy.py`, `config/url_policy.yaml` |
| Results parsed into sources and ledger entries | `agent/sit_review_agent/tools/sources.py`, `agent/sit_review_agent/state/evidence_ledger.py` |
| Record and replay of tool calls (cassettes) | `agent/sit_review_agent/tools/cassette.py`, `config/agent.yaml` `transport` |
| Fault schedules for the robustness suite and `--faults` | `agent/sit_review_agent/tools/faults.py`, `tests/robustness/faults/` |

The reasons two of the four servers are off, and what is still unverified about the live servers, are in `docs/LIMITATIONS.md`.
