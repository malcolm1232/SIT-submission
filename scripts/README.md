# MCP server probe

`probe_mcp_servers.py` characterises the four SIT lab MCP servers (streamable HTTP on Azure Container Apps). It reports:

- which auth header carries the shared API key
- the negotiated MCP `protocolVersion` and `serverInfo`
- the full tool list with input schemas
- cold-start and warm initialize latency
- one harmless search call on `mcp-internet-search`
- the verbatim rejection message from `mcp-document-intelligence`

The browser server only gets `tools/list`. None of its navigation tools are called.

## Install (macOS, Python 3.11+)

```bash
cd scripts
python3 -m venv .venv && . .venv/bin/activate && pip install "mcp>=2,<3" httpx
```

The macOS system `python3` may be 3.9. If it is, install a newer one first (`brew install python@3.12`) and use `python3.12 -m venv .venv`.

## Provide the API key without committing it

Copy the **"Shared API key (all 4)"** value from section 2.2 (page 4) of the lab brief PDF. Export it only in your shell:

```bash
read -rs SIT_MCP_API_KEY && export SIT_MCP_API_KEY   # paste the key, press Enter (not echoed, not in shell history)
```

Do not put the key in a file inside the repo, including `.env` files and comments. The script refuses to run if `SIT_MCP_API_KEY` is unset. It redacts the key from everything it prints or writes.

## Run

```bash
python probe_mcp_servers.py                              # all four servers, in parallel
python probe_mcp_servers.py --only mcp-internet-search   # one server (repeatable flag)
python probe_mcp_servers.py --sequential                 # one at a time
python probe_mcp_servers.py --self-test                  # offline check against a local in-process MCP echo server
```

**Expected runtime:** up to about 10 minutes. The containers scale to zero and take 1-2 minutes to wake. The first request to each server waits up to 180 s and retries once if the failure looks like a cold start. Later requests use a 30 s timeout. For a meaningful `cold_start_s`, run after the servers have been idle for a while (about 15+ minutes).

The script always exits 0, even when some servers fail, so you always get a results file. The exception is `--self-test`, which exits 1 if a check fails.

## Output

The script writes `./mcp_probe_results.json` and prints a summary table. For each server, the JSON contains:

- `winning_header_variant`
- `attempts` (HTTP status, initialize result and timing for each header variant)
- `protocol_version`
- `server_info`
- `tools`
- `cold_start_s`, `warm_s` and `first_response_s`
- `no_auth_control` (whether the server also accepts requests with no key)
- `sample_call`
- `errors`

**Paste the contents of `mcp_probe_results.json` back into the Claude session.**

# Claude Code backend smoke test (ADR-010)

`smoke_claude_code_backend.py` makes **one real model call** through `ClaudeCodeGateway` (headless `claude -p`) to check that the `llm.backend: claude_code` path works on this machine. It is opt-in: pytest does not collect it, and every test stays offline.

```bash
. .venv/bin/activate                                          # the agent venv (pip install -e ".[dev]")
claude --version                                              # Claude Code installed and logged in
python scripts/smoke_claude_code_backend.py                   # claude-opus-5-5, effort high
python scripts/smoke_claude_code_backend.py --model claude-haiku-4-5   # cheap check (overrides the gateway's model, not the config)
```

It asks for a tiny `PlanOutput` against a 3-line fake document and prints the parsed answer, the served model, token usage, `total_cost_usd` (a client-side estimate, not the bill), latency and the path of the `llm.jsonl` it wrote (a temp run directory unless `--run-dir` is given). The call bills to whatever `claude` is logged in with; check the usage or credit meter before and after if you want to confirm where it lands.
