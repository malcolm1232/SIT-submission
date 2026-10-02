# SIT AI Engineering Lab — Design Review Agent

An autonomous agent that reviews technical design artefacts against their stated
objectives, researches what needs validating, and recommends evidence-based
refinements only when justified. Built for the SIT AI Engineering Lab Exercise
(September 2026).

**Status (2026-10-02):** research and evaluation design complete and audited; the agent is built and
verified offline (444 tests, `sit-review selftest` end to end). Model calls go through either the
Anthropic API or headless Claude Code (ADR-010). Start with `docs/HANDOFF.md`, then `agent/README.md`.

## Layout

| Path | Purpose |
|---|---|
| `docs/` | Governing documents: decision records (ADRs), owner decisions, reproducibility policy, demo-day runbook, documentation map to lab §5.3, answer-key sealing, budget |
| `spec/` | Canonical flaw taxonomy, Finding/Review JSON schema, answer-key schema, validator, and the converter to canonical keys |
| `research/` | Reusable research notes (frameworks, models, Kaggle, methodology, grading, robustness) and the audit trail under `research/audit/` |
| `eval/synthetic/` | Three synthetic design artefacts (v1 + v2 re-review versions, PDFs, sealed answer keys) for development evaluation |
| `eval/blind/` | Two held-out items authored without project context (to be sealed; a true blind set is still to be commissioned) |
| `scripts/` | `probe_mcp_servers.py`: run on a laptop that can reach the SIT MCP servers to characterise auth, protocol, tools and cold start |
| `agent/` | The agent (`sit_review_agent`): state machine, two LLM backends, direct MCP client, report, CLI. See `agent/README.md` |
| `config/`, `prompts/`, `tests/` | Live-change config files (runbook §4), prompt bundle with lock, offline test suite |

## Reproducing checks

```
python3 spec/validate_examples.py      # schema + taxonomy self-tests
python3 spec/convert_answer_keys.py    # rebuild canonical answer keys
python3 eval/build_pdfs.py             # rebuild synthetic PDFs from markdown
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
ruff check agent tests && pytest -q    # 444 offline tests
sit-review selftest                    # offline end-to-end run on a bundled fixture
```

Secrets: no API keys are committed. With `llm.backend: claude_code` (the default) the agent bills to
the Claude Code login (subscription or cloud credits) and strips `ANTHROPIC_API_KEY` from the CLI
environment; with `anthropic_api` it reads `ANTHROPIC_API_KEY`. The MCP client and the probe read
`SIT_MCP_API_KEY`. See `docs/SEALING.md` for
answer-key handling.
