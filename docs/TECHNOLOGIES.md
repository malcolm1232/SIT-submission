# Framework and technologies

This file answers lab §5.3 "the agent framework and technologies used".
The agent uses no agent framework: it is a hand-written state machine in Python that calls the model through one gateway and the SIT MCP servers through a direct MCP client, so every retry, cut and log line is the project's own code.
Why a custom loop won over LangGraph, PydanticAI and the others is in `docs/ARCHITECTURE.md` §3 and §12 and in `docs/DECISIONS.md` ADR-001.

## Model and model access

| Item | Choice | Where |
|---|---|---|
| Model | `claude-opus-5-5` for every call, one effort level per conversation | `config/agent.yaml`, `docs/DECISIONS.md` ADR-002 |
| Default backend | The Claude Code CLI run headless as `claude -p`, billed to the logged-in account | `agent/sit_review_agent/llm/claude_code.py`, `docs/DECISIONS.md` ADR-010 |
| Alternative backend | The Anthropic Python SDK with `ANTHROPIC_API_KEY` | `agent/sit_review_agent/llm/backend.py` |
| Tools | The four SIT MCP servers over streamable HTTP, two of them enabled | `agent/sit_review_agent/tools/mcp_client.py`, `config/tools.yaml` |

## Pinned Python dependencies

Every version below is the exact pin in `pyproject.toml`, which is the only source of truth.

| Package | Pin | Role |
|---|---|---|
| `anthropic` | 1.11.0 | Anthropic API backend |
| `mcp` | 2.2.0 | MCP client for the SIT servers |
| `httpx2`, `httpx` | 2.13.1, 0.28.1 | HTTP transports of `anthropic` and `mcp` |
| `pydantic` | 2.13.5 | Config, model outputs and the review objects |
| `pdfplumber` | 0.11.10 | PDF text extraction at ingest (`docs/DECISIONS.md` ADR-006) |
| `pyyaml` | 6.0.3 | Config files |
| `jsonschema` | 4.26.0 | Validation against `spec/finding.schema.json` |
| `jinja2` | 3.1.6 | Prompts and the report template, strict about undefined variables |
| `typer` | 0.27.2 | The `sit-review`, `dra` and `sit-eval` command lines |
| `rapidfuzz` | 3.14.6 | Fuzzy anchor matching in verify |
| `starlette`, `uvicorn` | at least 1.7.0, 0.54.0 | The local page of `dra ui` |
| `markdown-it-py` | at least 4.2.0 | The HTML export of `dra ui` |
| `pytest`, `pytest-asyncio`, `ruff`, `playwright` | 9.1.1, 1.4.0, 0.16.10, 1.63.0 | Development extra: tests, lint and the browser tests |

No lock file of the full resolved tree is committed yet (`docs/SUBMISSION_GAPS.md` row 4).
