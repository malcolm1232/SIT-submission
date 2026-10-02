# User decisions log

Decisions given by the project owner in conversation. These override research recommendations. Fold into DECISIONS.md ADRs when editing that file.

## 2026-10-02

| # | Question | Decision | Consequence |
|---|---|---|---|
| 1 | Agent model | Claude Opus 5.5 for every agent call. No Sonnet/Haiku sub-tasks. Effort may be high throughout; token budget is sufficient, but spend must be justified, not excessive. | All-Opus cost model stands. Effort default for agent phases: `high` (not `medium`); `xhigh` only where a measured ablation shows gain. |
| 2 | Grader model | Owner defers to coordinator judgement. | Coordinator decision: primary holistic grader is Opus 5.5 at `high` effort; if the Mac reports an OpenAI or Google key, add a different-provider judge at high effort as the headline bias-controlled score and report agreement between the two; Sonnet 5.5 runs as a same-family control. If Anthropic-only, disclose the same-family limitation per research/models/README.md. |
| 3 | API keys held | Being retrieved from the Mac session. | Judge branch chosen when the report arrives. |
| 4 | Repo privacy | Repository is already private. | Sealing of answer keys is still required (collaborators and future tooling can read the repo), but the web-search leakage path is closed. SEALING.md interim rule applies. |
| 5 | Ablation A4 ("different model") | Owner defers; low effort not required. | Coordinator decision: A4 remains a genuine different-model ablation, run with Sonnet 5.5 as the AGENT model for that experiment only (the product stays all-Opus). Add A4b: an effort sweep on Opus 5.5 (medium / high / xhigh) to justify the chosen effort level with data. |

## 2026-10-02 (later)

| # | Question | Decision | Consequence |
|---|---|---|---|
| 6 | Billing for agent model calls | Owner wants all agent LLM calls on cloud credits / subscription usage, not a Console API key. | ADR-010 proposed: `claude_code` backend default, `anthropic_api` kept as an option. Pending owner confirmation of ADR-010. |
| 7 | Second-provider judge | Owner will top up OpenAI and/or Google later. | ADR-003 judge branch A stays open; revisit when keys are funded. |
| 8 | Cloud credits | This account: $36 of $250 left after this session (~$214 used). Two other accounts with $250 each, expiring 5 Nov. | Continue build in another account per docs/HANDOFF.md. |
| 9 | ADR-010 (Claude Code backend) | Owner replied "CAN U CONTINUE on it please?" to the request for confirmation. Taken as confirmation. | ADR-010 accepted. `llm.backend: claude_code` is the default in `config/agent.yaml`; `anthropic_api` stays available for evaluators with an API key. |

