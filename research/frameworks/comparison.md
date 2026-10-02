# Agent framework comparison: verified facts

Checked on **2026-10-02**. Every fact below was taken from a primary source on that date: the PyPI JSON API, the published wheel's source code (downloaded with `pip download <pkg>==<ver> --no-deps` and read directly), official docs pages, or the project's raw `CHANGELOG.md`/`MIGRATION.md` on GitHub. Anything not confirmed that way is marked **UNVERIFIED**.

Access notes for anyone re-running this check. The egress proxy blocked `ai.pydantic.dev`, `docs.langchain.com`, `openai.github.io` and `api.github.com`, so for PydanticAI, LangChain/LangGraph and the OpenAI Agents SDK the facts come from the **wheel source**, which is the code that actually runs, rather than from the docs sites. The proxy also blocked the SIT MCP hosts, so I could not probe the servers.

Abbreviations: "src:" means a file inside the published wheel for the stated version.

---

## 0. Facts that apply to every option

| Fact | Evidence |
|---|---|
| The MCP Python SDK is at **mcp 2.2.0** (2026-09-07). 2.0 shipped 2026-06-11, and the 1.x line is still patched (1.30.0 on 2026-09-07). | https://pypi.org/pypi/mcp/json |
| mcp 2.x renamed the client transport `streamablehttp_client` to **`streamable_http_client(url, *, http_client: httpx2.AsyncClient, terminate_on_close)`**. Headers are no longer a kwarg: you set them on the `httpx2.AsyncClient`. | src: `mcp/client/streamable_http.py` L680-705 (mcp 2.2.0) |
| mcp 2.x also renamed the server class `FastMCP` to `mcp.server.mcpserver.MCPServer`. The `mcp.server.fastmcp` package is gone. | src: mcp 2.2.0 `mcp/server/` listing |
| mcp 2.x client defaults: `MCP_DEFAULT_TIMEOUT = 30.0` s and `MCP_DEFAULT_SSE_READ_TIMEOUT = 300.0` s. `ClientSession` takes `read_timeout_seconds`, and each request can set `request_read_timeout_seconds`. | src: `mcp/shared/_httpx_utils.py` L12-14; `mcp/client/session.py` L408, L544 |
| **The ecosystem is split on mcp 1.x versus 2.x.** Needs mcp<2: `langchain-mcp-adapters` (`mcp<2.0.0,>=1.24.0`) and `crewai` (`mcp~=1.28.1`). Accept 2.x: anthropic `[mcp]` extra (`mcp<3,>=1.0`), `claude-agent-sdk` (`mcp<3,>=1.23`), `openai-agents` (`mcp<3,>=1.19`), pydantic-ai v2 (via `fastmcp-slim[client]` → `mcp<3,>=2.0`). | PyPI `requires_dist` for each package |
| **Current Claude models take no sampling parameters.** Since anthropic SDK 1.0, `temperature`, `top_p` and `top_k` are removed from `messages.create/stream/parse` and `tool_runner`. The migration guide says: "Current models do not use these sampling parameters; for an older model that still does, pass them through `extra_body`." So none of the frameworks gives you a determinism knob on current Claude models. | https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/MIGRATION.md ("Removed: deprecated request parameters"); src: `anthropic/resources/messages/messages.py` `create()` signature |
| SIT MCP servers: they speak streamable HTTP, share one API key, scale to zero with a 1-2 min cold start, and the document-intelligence server rejects all input. **The auth header name is UNVERIFIED.** The PDF only says "Shared API key". The servers were unreachable from this sandbox (proxy 403). | Assignment PDF §2.2 |

### Local smoke test of the "direct MCP client" path (run 2026-10-02)

Setup: `anthropic[mcp]==1.11.0`, `mcp==2.2.0`, and a local `MCPServer` behind middleware that checks an `X-API-Key` header and sleeps 8 s on its first request to simulate a cold start. Script: `scratchpad/smoke/{server,client}.py` (not committed).

| Scenario | Observed |
|---|---|
| Cold start with `httpx2.Timeout(2.0)` | `ExceptionGroup` wrapping `httpx2.ReadTimeout` after 2.1 s. **Handlers must unwrap `BaseExceptionGroup`.** |
| Retry after the server is warm, timeout 30 s | Connected in 0.1 s. `async_mcp_tool()` converted both tools, and `search` returned `[{'type':'text',...}]`. |
| Tool returns MCP `isError` (simulates the document server's rejections) | `anthropic.lib.tools.ToolError("Error executing tool broken")` is raised from `tool.call()`. The tool runner turns that into a `tool_result` with `is_error: true`. |
| Wrong API key | A nested `ExceptionGroup` at connect time, which is distinguishable from a timeout. |

Conclusion: a custom header plus a cold-start-tolerant client works with about 15 lines of our own code. One "wake then retry" attempt is enough.

---

## 1. Custom loop on the official Anthropic Python SDK (our hypothesis)

| Item | Verified fact | Source |
|---|---|---|
| Version / maintenance | **anthropic 1.11.0** (2026-09-30). **1.0.0 shipped 2026-08-20** with breaking changes. There were 25 releases in the last 90 days. CI runs breaking-change detection on every push (changelog 0.122.0). | https://pypi.org/pypi/anthropic/json ; https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/CHANGELOG.md |
| HTTP stack | Built on **`httpx2`**, not `httpx`. OpenTelemetry/Sentry/respx/vcrpy patch `httpx` and "can silently fail" unless you call `httpx2.alias_httpx()` first. | MIGRATION.md §"Tracing, instrumentation and mocking libraries" |
| MCP, option A: **MCP connector** (server-side) | Beta (`mcp-client-2025-11-20`; `mcp-client-2026-09-15` adds tool-list pinning). Auth is **only `authorization_token`** (an OAuth Bearer token). There is no arbitrary-header field. Only MCP tools are supported, and the server must be publicly reachable. Not available on Bedrock or Vertex, and not ZDR-eligible. Connector timeout and cold-start behaviour: **UNVERIFIED**. | https://platform.claude.com/docs/en/agents-and-tools/mcp-connector ; src: `types/beta/beta_request_mcp_server_url_definition_param.py` (fields: name, type, url, authorization_token, tool_configuration) |
| MCP, option B: **direct client + SDK helpers** | `anthropic.lib.tools.mcp` provides `mcp_tool`, `async_mcp_tool`, `mcp_content`, `mcp_message` and `mcp_resource_to_content`. These convert an `mcp.ClientSession` tool into a runnable tool, and support both mcp<2 camelCase and mcp>=2 snake_case fields. Custom headers go on the `httpx2.AsyncClient` (smoke test above). | src: `anthropic/lib/tools/mcp.py` L1-80, L316-380 |
| Tool loop | `client.beta.messages.tool_runner(...)` is **beta**. It loops until there is no tool use or `max_iterations`. You can iterate it, call `append_messages()` or `generate_tool_call_response()`, `add_tools()`/`remove_tools()`, or `compact_before_next_turn()`. Tool exceptions become `tool_result` with `is_error: True`, an unknown tool gives "Error: Tool 'x' not found", and there are **no tool retries**. The docs say: "When you need human-in-the-loop approval, custom logging, or conditional execution, use the manual loop instead." | src: `anthropic/lib/tools/_beta_runner.py` L146-175, L340-345, L482-545 ; https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner |
| Structured output | **GA.** Pass `output_config={"format": {"type":"json_schema", ...}}` or call `client.messages.parse(..., output_format=PydanticModel)` (non-beta `parse` exists). Strict tool use is `strict: true`. JSON outputs and strict tools work in the same request. Schemas cannot use numeric or string length constraints, recursion, or `additionalProperties` other than false. | https://platform.claude.com/docs/en/build-with-claude/structured-outputs ; src: `resources/messages/messages.py` L1178 |
| Checkpoint / resume | None built in. Conversation state is a plain `messages` list plus our own state object, so we serialise it to JSON ourselves. | (design) |
| Observability | No tracing framework. You get raw request/response objects, `with_raw_response`, `_request_id` and usage, and you do your own JSONL logging. OTel needs the httpx2 alias above. | MIGRATION.md |
| Provider swap | Anthropic-only API surface (plus Bedrock, Vertex and Foundry clients in `anthropic.lib`). Any other vendor needs our own adapter. Its size is an **UNVERIFIED estimate of 150-250 LOC** for OpenAI-style tools and JSON schema. | src: `anthropic/lib/{bedrock,vertex,foundry.py}` |
| "Magic" | No hidden prompts. **Hidden retries do exist at the transport level: `DEFAULT_MAX_RETRIES = 2`** (408/409/429/5xx/connection errors) and `DEFAULT_TIMEOUT = 600 s`. Both are configurable per client or per request. The tool runner has no prompt templates, but it does append messages for you. | src: `anthropic/_constants.py` L9-10; `lib/_retry.py` |

## 2. LangGraph (with langchain-anthropic + langchain-mcp-adapters)

| Item | Verified fact | Source |
|---|---|---|
| Version / maintenance | **langgraph 1.2.12** (2026-09-21). 1.0 shipped 2025-08-27. 5 releases in 90 days. Depends on `langchain-core<2,>=1.4.7`, `langgraph-checkpoint<5,>=4.1`, `langgraph-prebuilt<1.2,>=1.1`. | https://pypi.org/pypi/langgraph/json ; wheel METADATA |
| MCP | `langchain-mcp-adapters 0.3.2` (2026-08-06). `MultiServerMCPClient` config `{"transport": "streamable_http", "url", "headers", "timeout", "sse_read_timeout", "httpx_client_factory", "auth"}`. By default it opens **a new MCP session per tool call**. **It pins `mcp<2.0.0`.** `pip` reports `ResolutionImpossible` with `mcp==2.2.0`. | src: `langchain_mcp_adapters/sessions.py` L165-192, `client.py` L85, L175; pip dry-run 2026-10-02 |
| MCP error surfacing | An MCP `isError` result becomes `ToolException`, which is shown to the model. "Transport/session failures ... are not ToolException subclasses ... and propagate", so a cold-start timeout crashes the run unless you catch it. | src: `langchain_mcp_adapters/tools.py` L99-135 |
| ToolNode default | `_default_handle_tool_errors` returns argument-validation errors to the model and **re-raises everything else**. When enabled, the error template is `"Error: {error}\n Please fix your mistakes."` | src: `langgraph/prebuilt/tool_node.py` L111, L383-391 (langgraph-prebuilt 1.1.0) |
| Structured output | Through `ChatAnthropic.with_structured_output`, or LangChain `create_agent(response_format=ToolStrategy / ProviderStrategy / AutoStrategy)`. | src: `langchain/agents/structured_output.py` L196, L271, L457 |
| Checkpoint / resume | First-class. Checkpointers come from `langgraph-checkpoint` (InMemory) and `langgraph-checkpoint-sqlite 3.1.1` (2026-07-30). You also get `interrupt()`, `Command`, and time travel. `RetryPolicy(initial_interval=0.5, max_attempts=3, ...)` is **opt-in per node**. | src: `langgraph/types.py` L427-445, L827, L880 ; https://pypi.org/pypi/langgraph-checkpoint-sqlite/json |
| Observability | LangSmith callbacks plus `get_graph().draw_mermaid_png()` for a graph diagram. | src: `langgraph/pregel/main.py` L845, L919 |
| Provider swap | Change the `BaseChatModel` (`init_chat_model("provider:model")`). | src: `langchain/chat_models/base.py` L197 |
| "Magic" | `StateGraph` itself is thin. The recursion limit default is `LANGGRAPH_DEFAULT_RECURSION_LIMIT=10007`. `ChatAnthropic.max_retries = 2`. Prebuilt agents add the error template above and synthetic structured-output tools. | src: `langgraph/_internal/_config.py` L32; `langchain_anthropic/chat_models.py` L1420 |
| Install check | `langgraph==1.2.12 langchain-anthropic==1.7.5 langchain-mcp-adapters==0.3.2` resolves to anthropic 1.11.0, **mcp 1.30.0**, httpx 0.28.1 **and** httpx2 (two HTTP stacks). | pip dry-run 2026-10-02 |

## 3. Plain LangChain (`create_agent`)

| Item | Verified fact | Source |
|---|---|---|
| Version | **langchain 1.4.3** (2026-09-28), langchain-core 1.6.6 (2026-09-29). 15 releases in 90 days. `create_agent` runs on LangGraph (`langgraph<1.3,>=1.2.11`). | https://pypi.org/pypi/langchain/json ; wheel METADATA |
| API | `create_agent(model, tools, system_prompt, middleware, response_format, state_schema, context_schema, checkpointer, store, ...)`. | src: `langchain/agents/factory.py` L824-834 |
| MCP, structured output, checkpointing, tracing, provider swap | Same as LangGraph above: the same adapters, the same `mcp<2` pin, the same ToolNode defaults. | as §2 |
| "Magic" | The middleware stack and prebuilt ToolNode prompt templates sit between you and the model. Control flow is the prebuilt ReAct loop, so changing it means writing middleware or dropping down to LangGraph. | src as above |

## 4. PydanticAI

| Item | Verified fact | Source |
|---|---|---|
| Version / maintenance | **pydantic-ai 2.53.0** (2026-10-02). **v2.0 shipped 2026-05-21.** The v1 line is still patched (1.107.7 on 2026-09-30). **66 releases in 90 days.** | https://pypi.org/pypi/pydantic-ai/json |
| MCP | `MCPToolset(url_or_client, *, max_retries, init_timeout, read_timeout, headers, http_client, tool_error_behavior, ...)`. It is built on the FastMCP `Client` (`fastmcp-slim[client] 4.x`, mcp>=2). **Defaults are `init_timeout=5` s and `read_timeout=300` s, and a 1-2 min cold start fails init unless you raise it.** `headers` and `http_client` are mutually exclusive. `tool_error_behavior`: `'retry'` (default; raises `ModelRetry`), `'error'`, or `'failed'`. The v1 class `MCPServerStreamableHTTP` no longer exists in v2. | src: `pydantic_ai/mcp.py` L717-770, L869-1055 |
| Structured output | `output_type=` accepts a Pydantic model, a union, `ToolOutput`, `NativeOutput`, `PromptedOutput` or `TextOutput`. Output validators can raise `ModelRetry`. | src: `pydantic_ai/output.py` L103-351 |
| Checkpoint / resume | Message history is serialisable via `ModelMessagesTypeAdapter`. Durable execution integrations exist for Temporal, DBOS and Prefect. | src: `pydantic_ai/messages.py` L3050; `pydantic_ai/durable_exec/{temporal,dbos,prefect}` |
| Observability | OpenTelemetry built in (`Agent.instrument_all()`, `logfire` extra). | src: `pydantic_ai/agent/__init__.py` L1144 |
| Provider swap | Strongest of all the options: a model string such as `'anthropic:...'` or `'openai:...'`. There are 20+ model modules (anthropic, openai, google, bedrock, groq, mistral, cohere, ollama, openrouter, xai, ...) plus a `FallbackModel`. | src: `pydantic_ai/models/` listing |
| "Magic" | Default `retries` is 1 for tools and output. A retry injects a user-visible prompt ending `"Fix the errors and try again."`. Final output goes through an output tool by default (`ToolOutput`). `UsageLimits.request_limit` defaults to 50. | src: `pydantic_ai/agent/__init__.py` L642-650; `messages.py` L1854; `usage.py` L482 |
| Install check | `pydantic-ai-slim[anthropic,mcp]==2.53.0` resolves to anthropic 1.11.0, mcp 2.2.0 and httpx2 only (65 packages). | pip dry-run 2026-10-02 |

## 5. Claude Agent SDK (Python)

| Item | Verified fact | Source |
|---|---|---|
| Version / maintenance | **claude-agent-sdk 0.2.163** (2026-09-30). Still **0.x**, with **53 releases in 90 days**. The wheel is about **232 MB unpacked** because it bundles the Claude Code CLI binary (`_bundled/claude`), which the SDK drives as a subprocess. | https://pypi.org/pypi/claude-agent-sdk/json ; wheel contents |
| MCP | `mcp_servers={"name": {"type": "http", "url": ..., "headers": {...}}}`. Custom headers are supported. In code you must use `"http"`; `"streamable-http"` is only an alias in JSON config. Tools are named `mcp__<server>__<tool>` and must be allowed via `allowed_tools`. **Connection timeout defaults to 30 s** (`MCP_TIMEOUT`); tool-call time is `MCP_TOOL_TIMEOUT`. Failed servers do **not** raise: you check `status` in the init message (`failed`/`needs-auth`/`pending`). There are 5 automatic reconnection attempts, and "Claude can fall back to built-in tools when the server is unavailable." | https://code.claude.com/docs/en/agent-sdk/mcp |
| Structured output | `ClaudeAgentOptions.output_format: dict` (JSON schema). | src: `claude_agent_sdk/types.py` (ClaudeAgentOptions) |
| Checkpoint / resume | `resume`, `continue_conversation`, `fork_session`, `resume_session_at`, `enable_file_checkpointing`. | src: same |
| Observability | `hooks` covering PreToolUse, PostToolUse, PostToolUseFailure, UserPromptSubmit, Stop, SubagentStop, PreCompact, Notification, SubagentStart and PermissionRequest. There is also an `otel` extra, and `stderr`/`debug_stderr` options. | src: `types.py` L284-296 |
| Provider swap | Claude models only (`model`, `fallback_model`). Bedrock, Vertex or a gateway only via CLI env vars (**UNVERIFIED** in this check). | src: ClaudeAgentOptions |
| "Magic" | The most of any option. It is the full Claude Code harness: its own system prompt (`{"type":"preset","preset":"claude_code"}` or a custom one), its own built-in tools (`tools` preset), tool search on by default, auto-compaction, subagents, permissions, and `setting_sources` that load `.mcp.json`, CLAUDE.md and skills from disk. Limits are `max_turns` and `max_budget_usd`. | src: ClaudeAgentOptions fields; docs above |

## 6. OpenAI Agents SDK

| Item | Verified fact | Source |
|---|---|---|
| Version / maintenance | **openai-agents 0.22.3** (2026-09-17). Still 0.x, with 17 releases in 90 days. Requires `openai<4,>=3.0.0`, `httpx2`, and `mcp<3,>=1.19`. | https://pypi.org/pypi/openai-agents/json |
| MCP | `MCPServerStreamableHttp(params={"url", "headers", "timeout" (default 5 s), "sse_read_timeout" (5 min), "terminate_on_close", "httpx_client_factory", "auth"}, cache_tools_list=False, client_session_timeout_seconds=5, max_retry_attempts=0, retry_backoff_seconds_base=1.0, ...)`. `failure_error_function` turns MCP failures into a model-visible message, or set it to `None` to raise. | src: `agents/mcp/server.py` L540-590, L2160-2260 |
| Structured output | `Agent(output_type=...)` with a strict JSON schema (`ensure_strict_json_schema`). | src: `agents/agent_output.py` |
| Checkpoint / resume | `RunState.to_json()` / `from_json()`, plus `SQLiteSession` memory. | src: `agents/run_state.py` L764, L1784, L2266; `agents/memory/sqlite_session.py` |
| Observability | Built-in tracing that exports to OpenAI by default. Turn it off with `set_tracing_disabled(True)` or `OPENAI_AGENTS_DISABLE_TRACING`. Without `OPENAI_API_KEY` it logs "skipping trace export". | src: `agents/tracing/provider.py` L348; `tracing/processors.py` L109-142 |
| Provider swap | `extensions/models/litellm_model.py` and `any_llm_model.py`. Claude runs through LiteLLM, which is an extra translation layer. | src: `agents/extensions/models/` |
| "Magic" | `DEFAULT_MAX_TURNS = 10`, handoff prompt prefix (`RECOMMENDED_PROMPT_PREFIX`), and guardrail hooks. Moderate. | src: `agents/run_config.py` L45; `extensions/handoff_prompt.py` |

## 7. CrewAI

| Item | Verified fact | Source |
|---|---|---|
| Version / maintenance | **crewai 1.15.23** (2026-09-28). There were **94 releases in 90 days**, including daily `.devYYYYMMDD` builds. Requires Python `<3.14,>=3.10`, `pydantic<2.13`, `openai<3` (the current OpenAI SDK is 3.x), `mcp~=1.28.1`, chromadb and lancedb. **The `[anthropic]` extra pins `anthropic~=0.73.0`.** `crewai[anthropic]` with `anthropic==1.11.0` gives `ResolutionImpossible`. The default resolution pulls 137 packages. | https://pypi.org/pypi/crewai/json ; pip dry-run 2026-10-02 |
| MCP | `MCPServerHTTP(url, headers, streamable=True)`. | src: `crewai/mcp/config.py` L57-78 |
| Structured output | Task `output_pydantic`/`output_json` (**UNVERIFIED** in this check; not read in source). | — |
| Checkpoint / resume | Flow `@persist` / `FlowPersistence`. | src: `crewai/flow/persistence/{base,decorators}.py` |
| Observability | OpenTelemetry deps, plus anonymous telemetry to `https://telemetry.crewai.com:4319`. The opt-out env var was **UNVERIFIED** in source. | src: `crewai/telemetry/constants.py` L9 |
| "Magic" | Heavy. `translations/en.json` holds 36 prompt "slices" ("You are {role}. {backstory}\nYour personal goal is: {goal}", ReAct `Thought/Action/Observation` formats, summariser prompts). `max_iter=25`, `max_retry_limit=2`, and `respect_context_window=True` summarises context automatically. | src: `crewai/translations/en.json`; `agent/core.py` L298-305; `agents/agent_builder/base_agent.py` L286 |

## 8. smolagents

| Item | Verified fact | Source |
|---|---|---|
| Version / maintenance | **smolagents 1.26.0** (2026-05-29). **No release in the last 90 days.** | https://pypi.org/pypi/smolagents/json |
| MCP | `MCPClient({"url", "transport": "streamable-http", ...}, structured_output=...)` goes through `mcpadapt` 0.1.19, which requires `mcp[ws]>=1.10.1` with no upper bound and imports `from mcp.client.streamable_http import streamablehttp_client`. **Verified broken:** a fresh `pip install "smolagents[mcp]==1.26.0"` resolves mcp 2.2.0, and `MCPClient(...)` raises `ImportError: cannot import name 'streamablehttp_client'`. The workaround is to pin `mcp<2`. | src: `smolagents/mcp_client.py` L41-112; `mcpadapt/core.py` L20-26, L112; live install test 2026-10-02 |
| Structured output | `final_answer_checks`, plus a `structured_output` flag for MCP tool output. There is no provider-native schema-constrained output for the final answer (**UNVERIFIED** beyond the source read). | src: `smolagents/agents.py` L287-335 |
| Checkpoint / resume | None built in (in-memory `AgentMemory` only; **UNVERIFIED** whether a replay/serialise API exists). | src: `smolagents/memory.py` |
| Observability | `step_callbacks`, plus an OTel `telemetry` extra. | src: `agents.py` L282-351 |
| Provider swap | `LiteLLMModel`, `InferenceClientModel`, `AmazonBedrockModel`, `OpenAIServerModel`. There is no native Anthropic class. | src: `smolagents/models.py` L1205-1859 |
| "Magic" | Large YAML system prompts (`code_agent.yaml` 313 lines, `toolcalling_agent.yaml` 242 lines). The flagship `CodeAgent` **executes model-written Python** on the evaluator's laptop. `max_steps=20`. | src: `smolagents/prompts/*.yaml`; `agents.py` L300 |

---

## Release cadence summary (PyPI, as of 2026-10-02)

| Package | Latest | Released | Releases in last 90 d | Last major |
|---|---|---|---|---|
| anthropic | 1.11.0 | 2026-09-30 | 25 | 1.0 on 2026-08-20 |
| mcp | 2.2.0 | 2026-09-07 | 10 | 2.0 on 2026-06-11 |
| langgraph | 1.2.12 | 2026-09-21 | 5 | 1.0 on 2025-08-27 |
| langchain | 1.4.3 | 2026-09-28 | 15 | 1.0 on 2025-08-27 |
| langchain-mcp-adapters | 0.3.2 | 2026-08-06 | 2 | 0.x |
| pydantic-ai | 2.53.0 | 2026-10-02 | 66 | 2.0 on 2026-05-21 |
| claude-agent-sdk | 0.2.163 | 2026-09-30 | 53 | 0.x |
| openai-agents | 0.22.3 | 2026-09-17 | 17 | 0.x |
| crewai | 1.15.23 | 2026-09-28 | 94 (incl. dev builds) | 1.0 on 2025-09-28 |
| smolagents | 1.26.0 | 2026-05-29 | 0 | 1.0 on 2024-12-31 |

Method: `curl https://pypi.org/pypi/<pkg>/json`, counting release files uploaded on or after 2026-07-02.

## Not verified (open items)

- The exact auth header the SIT MCP servers expect (`Authorization: Bearer` vs `X-API-Key` or similar). This decides whether the server-side MCP connector is usable at all.
- The MCP connector's connect timeout against a 1-2 min cold start.
- GitHub stars, open-issue counts and commit activity (api.github.com was blocked).
- CrewAI task structured-output parameters and the telemetry opt-out variable.
- The size of a non-Anthropic provider adapter for the custom loop (estimated 150-250 LOC).
