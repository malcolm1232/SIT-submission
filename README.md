# SIT AI Engineering Lab — Design Review Agent

An autonomous agent that reviews technical design artefacts against their stated
objectives, researches what needs validating, and recommends evidence-based
refinements only when justified. Built for the SIT AI Engineering Lab Exercise
(September 2026).

**Status (2026-10-02, third session):** research and evaluation design complete and audited; the agent
is built and verified offline (`sit-review selftest` end to end); the evaluation harness (`sit-eval`:
matcher, metrics, statistics, lecturer grader) and the robustness P0 suite are built and verified,
865 offline tests in all. Model calls go through either the Anthropic API or headless Claude Code
(ADR-010). Start with `docs/HANDOFF.md`, then `agent/README.md` and `harness/README.md`.

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
| `harness/` | The evaluation harness (`sit_eval`, command `sit-eval`): matcher, metrics, statistics, lecturer grader, live judges. Never imported by the agent. See `harness/README.md` |
| `config/`, `prompts/`, `tests/` | Live-change config files (runbook §4, plus `config/eval.yaml` for the harness), prompt bundle with lock, offline test suite (`tests/robustness/` is the P0 robustness suite) |

## Reproducing checks

```
python3 spec/validate_examples.py      # schema + taxonomy self-tests; never reads eval/blind unless --include-blind
python3 spec/convert_answer_keys.py --tier synthetic   # rebuild the S-dev canonical keys; without --tier it reads eval/blind too
python3 eval/build_pdfs.py             # rebuild synthetic PDFs from markdown
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
make smoke                             # offline, about 10 s: selftest + config, prompt-lock, CLI and leakage tests
make test                              # ruff check agent harness tests, then the whole offline suite (pytest -q)
sit-review selftest                    # offline end-to-end run on a bundled fixture
sit-eval score --help                  # score a run against an answer key (use --dry-run first)
```

Secrets: no API keys are committed. With `llm.backend: claude_code` (the default) the agent bills to
the Claude Code login (subscription or cloud credits) and strips `ANTHROPIC_API_KEY` from the CLI
environment; with `anthropic_api` it reads `ANTHROPIC_API_KEY`. The MCP client and the probe read
`SIT_MCP_API_KEY`. See `docs/SEALING.md` for
answer-key handling.
