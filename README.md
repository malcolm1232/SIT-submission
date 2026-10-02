# SIT AI Engineering Lab — Design Review Agent

An autonomous agent that reviews technical design artefacts against their stated
objectives, researches what needs validating, and recommends evidence-based
refinements only when justified. Built for the SIT AI Engineering Lab Exercise
(September 2026).

**Status:** research and evaluation design complete and audited; agent code not yet started.
Start with `docs/DECISIONS.md`, then `research/audit/fresh_eyes.md` for the prioritised build plan.

## Layout

| Path | Purpose |
|---|---|
| `docs/` | Governing documents: decision records (ADRs), owner decisions, reproducibility policy, demo-day runbook, documentation map to lab §5.3, answer-key sealing, budget |
| `spec/` | Canonical flaw taxonomy, Finding/Review JSON schema, answer-key schema, validator, and the converter to canonical keys |
| `research/` | Reusable research notes (frameworks, models, Kaggle, methodology, grading, robustness) and the audit trail under `research/audit/` |
| `eval/synthetic/` | Three synthetic design artefacts (v1 + v2 re-review versions, PDFs, sealed answer keys) for development evaluation |
| `eval/blind/` | Two held-out items authored without project context (to be sealed; a true blind set is still to be commissioned) |
| `scripts/` | `probe_mcp_servers.py`: run on a laptop that can reach the SIT MCP servers to characterise auth, protocol, tools and cold start |
| `agent/` | The agent implementation (to come) |

## Reproducing checks

```
python3 spec/validate_examples.py      # schema + taxonomy self-tests
python3 spec/convert_answer_keys.py    # rebuild canonical answer keys
python3 eval/build_pdfs.py             # rebuild synthetic PDFs from markdown
```

Secrets: no API keys are committed. The agent reads `ANTHROPIC_API_KEY` and the
probe reads `SIT_MCP_API_KEY` from the environment. See `docs/SEALING.md` for
answer-key handling.
