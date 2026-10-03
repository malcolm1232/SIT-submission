# Worker report: the LangGraph orchestrator variant (session 4, 2026-10-03)

Branch `s4/langgraph` in the worktree `/Users/malco/Desktop/SIT-wt/langgraph`, from `430321d`; not pushed.
The deliverable is `docs/COMPARISON_LANGGRAPH.md`; the edit log with every command is `research/audit/langgraph_variant_editlog.md`.

## What was built

A LangGraph `StateGraph` variant of the orchestrator in `agent/sit_review_agent/orchestrator_langgraph/` whose nodes call the same phase objects, gateways, checkpoint and progress writers as the custom loop, selected by `sit-review run --orchestrator langgraph` (also on `review` and `resume`) and absent by default.
Stage 1 is a `Send` fan-out to one node per assess shard and to a subgraph that runs understand and plan in parallel and research after a join of the two; merge, refine, verify and report follow, with the cap skips as conditional edges.
The bookkeeping is inherited from `Orchestrator`, so the variant replaces the 153 lines of scheduling and keeps the 203 lines of checkpointing, merging and disclosure; the variant itself is 436 lines.
`pyproject.toml` gains the optional extra `[langgraph]` (`langgraph==1.2.12`); `orchestrator.py`, the phases, the LLM and tool stacks, the report, replay and manifest modules are unchanged.

## What was measured

The parity file `tests/test_parity_langgraph.py` runs ten behaviours through both orchestrators: 26 pass and 2 are expected failures of the variant, named in the file (the parallel start order of the stage 1 members, and a process fault around the whole assess member).
The one live Opus run, `docs/live_runs/langgraph_payments_v1_1/`, reviewed the payments design on the demo profile without tools in 424.7 s at $4.71 (a lower bound: one shard was cut at the stage 1 limit and its usage is estimated) with 18 findings and 3 strengths and the verdict `not_fit` at 0.75; the custom loop's run on the same setup took 382.3 s at $5.74 with 18 findings, 3 strengths and `not_fit` at 0.78.
The one scoring in the pre-registered setup with `--exploratory` gave strict recall 12 of 14 against the custom loop's 13 of 14, lenient recall 14 of 14 in both, adjudicated precision 0.944 in both, severity-weighted recall 0.867 against 0.933 and critical recall 1.000 in both; the whole difference is F07, matched partially instead of strictly.
The conclusion in the note: on one document and one run per arm there is no quality difference to claim; the framework paid for itself in the fan-out, the join and the drawing and charged for it in a subgraph forced by the superstep barrier, a shadow state, side effects in routers, a hand-written backstop and sibling cancellation and a swapped class name; the custom loop stays and the variant stays in the tree behind one flag.

## Gates at the stop

`ruff check agent harness tests` exit 0; `sit-review selftest` exit 0; `make smoke` exit 0; `pytest -q --tb=no -p no:warnings` 1866 passed and 2 xfailed; `make test` ruff clean and 1866 passed, 2 xfailed (exit codes in the edit log section 4; the pytest and make test codes are read from their summary lines, because the reruns that captured them to a scratch file could not be read back after the classifier's refusal).

## Precautions kept

Nothing against the SIT MCP hosts (every live run `--no-tools`, every offline run on the fake gateway); nothing under `eval/blind/` opened; nothing under `docs/transcripts/` read; `docs/design/` not read; no model output, `llm.jsonl` or `progress.jsonl` record printed (every inspection by script); no call resent; the batch of five further live runs was refused by the permission classifier (real-world transactions) and left for the next session.
Model calls: one Opus agent run (about $4.71 plus the unrecorded cut call) and one scoring ($9.45 reported); no Haiku call was needed.

## State at the stop

Commits on `s4/langgraph`, in order: `bee5f8e` (the variant and the flag), `c4d94b9` (the parity checklist), `7b07e92` (the live run), `99d64d5` (its measurement note), `f74beda` (the scoring), then the comparison note, the section 12 row, the edit log and this report.
Every gate passed at the last commit; the working tree is clean apart from `runs/` (gitignored).
The venv is the worktree's own (`.venv`, Python 3.13.13) with the `[dev]` and `[langgraph]` extras installed.

## For the next session

- A verifier merges `s4/langgraph` into the main line; nothing here is pushed.
- The comparison rests on one document and one run per arm; the owner lifted the budget line during the session, and the five further live runs this worker then queued (the custom loop paired on payments, both arms on the two other documents) were refused by the permission classifier and not retried, so the next step is the same pair of runs on `eval/synthetic/clinical_rpm/design_v1.pdf` and `eval/synthetic/research_lakehouse/design_v1.pdf` (the custom loop has no demo-profile run on either), scored the same way, and a second paired run on the payments design under the same Mac load, since the one visible difference (shard 2 cut at the limit) came at a load average of 15.8 against about 5.
- The two expected failures are design limits of the variant, not bugs; if the start order of parallel nodes matters for a reader, the variant could name its nodes so the framework's order equals `STAGE_1` order, which would turn the first expected failure into a pass at the cost of odd node names.
- `tests/test_orchestrator.py` and five tests of `test_run_and_resume.py` and `test_e2e_synthetic.py` assert the custom loop's launch order and fail under the variant; the parity file re-asserts those behaviours order-free, and nothing else in the suite differs.
