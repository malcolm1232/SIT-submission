# Session 4 worker report: docs/ARCHITECTURE.md

Date: 2026-10-03.
Branch `s4/arch`, started from d735dcf; this worker is the retry of one stopped by a tool-layer classifier before it wrote anything.

## Deliverable

`docs/ARCHITECTURE.md`, 200 lines, one full sentence per line, no em dash, thirteen sections: what it does; the shape of a run with a Mermaid stage graph; why this shape; model access; tools; honesty and traceability; state, checkpoints, resume and replay; robustness; the evaluation harness; the UI; frozen interfaces and what is deliberately not built; comparisons made and trade-offs (the coordinator's mid-task addition, a nine-row table); a fifteen-point walkthrough script.
Every factual claim names its implementing file in parentheses: 111 parenthetical references naming 98 distinct repository paths, and a script that strips the fenced diagram, collects every slash-bearing backticked token and tests it against the tree found every one present.
`docs/DEMO_DAY_RUNBOOK.md` §8 item 2 now points at `docs/ARCHITECTURE.md` and its §13 script, and `docs/DOCUMENTATION_MAP.md` lists the file as Exists in §1 row 1, §2 "understand" row and §4 row (a).

## The stale paragraph in agent/README.md

The "Latency redesign" paragraph under "State machine" said the W1 and W2 branches were pending integration and the tree still ran the sequential order.
`orchestrator.py` walks `states.STAGE_ORDER` (ingest, stage 1, refine, verify, report) and `_stage_1` starts understand, plan and the assess shards as asyncio tasks, so the paragraph was stale; it now says the redesign is integrated and that `PHASE_ORDER` is the phase numbering, not the run order.

## What the tree does not hold that the brief named

- No `agent/sit_review_agent/ui/` package, no `ui/server.py` or `ui/chat.py`: the UI is described from `docs/design/ui_design.md` (named, not read) as in build, and the document says so.
- No `agent/sit_review_agent/finding_refs.py` and no INV-12 anywhere in `agent/`, `harness/`, `spec/` or `tests/`: the document describes the finding-ID map that exists today (`assess.merge`, `verify._normalise_ids`, `_model_calls.normalise_findings` and `reconcile_coverage`, the verdict's unknown-ID removal) and states that the dedicated invariant is designed and not in this tree.
- No `progress.jsonl` and no `spec/progress_event.schema.json`: `rundir.py` lists `progress.log` only, so the document says the structured journal is part of the UI build and does not quote the 77 event types.
- No decision #36 in `docs/USER_DECISIONS.md` (35 rows): the outputs line of the UI section cites the design file instead.

## Precautions kept

Not read: `docs/DECISIONS.md`, anything under `docs/transcripts/` or `docs/design/`, `llm/claude_code.py`, `llm/partial.py`, `tests/fixtures/`, any `llm.jsonl`; `eval/blind/` was neither opened nor listed (the tree listing filtered it out).
The gateway is described from `llm/gateway.py` docstrings and `agent/README.md`.
No model calls; no call was refused.

## Commits on s4/arch

Six commits for the document, two sections at a time, then one for the runbook pointer, the map rows, the README fix and this report.
