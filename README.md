# SIT AI Engineering Lab — Design Review Agent

An autonomous agent that reviews technical design artefacts against their stated
objectives, researches what needs validating, and recommends evidence-based
refinements only when justified.

Built for the SIT AI Engineering Lab Exercise (September 2026).

## Layout

| Path | Purpose |
|---|---|
| `research/` | Reusable research notes: framework/model choice, Kaggle benchmarks, eval methodology, grading rubric, robustness scenarios, audits |
| `eval/synthetic/` | Synthetic design artefacts with sealed answer keys (planted flaws) for in-distribution evaluation |
| `eval/blind/` | Eval items authored by agents with no knowledge of this project (held-out / extended set) |
| `agent/` | The agent implementation (to come) |
| `docs/` | Submission documentation (to come) |

Each `research/<topic>/README.md` is self-contained so it can be reused outside this project.
