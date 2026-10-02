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
