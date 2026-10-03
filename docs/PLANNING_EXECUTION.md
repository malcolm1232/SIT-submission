# Planning and execution

This file answers lab §5.3 "planning and execution approach".
A run is a fixed pipeline of stages whose order is code, while the model plans the content inside it: which questions need outside evidence, which searches to make, and when the evidence is enough.
Every stage ends by an absolute time on the run clock, so a slow call is cut and disclosed instead of taking the report with it.
The architecture text is `docs/ARCHITECTURE.md` §2 (the stage graph and each stage), §3 (why this shape, with the measured times) and §6 (how a cut is disclosed); `docs/DECISIONS.md` ADR-011 and ADR-012 record the redesign.

## Where each part lives

| Part | Where it is implemented or configured |
|---|---|
| The stage order and the stage 1 dependency table; `dra states` prints the graph from it | `agent/sit_review_agent/states.py` |
| The run loop, the concurrent first stage and the cap checks between stages | `agent/sit_review_agent/orchestrator.py` |
| The plan: research questions per criterion, with a document-only question added by code for any criterion the model left out | `agent/sit_review_agent/phases/plan.py` |
| The research tool loop, one round of tool calls at a time | `agent/sit_review_agent/phases/research.py` |
| The stop rules, evaluated after each research round, reporting a closed stop-reason code | `agent/sit_review_agent/stop_rules.py`, `config/stop_rules.yaml` `active` |
| The stop-reason enum | `agent/sit_review_agent/models.py` `StopReasonCode` |
| The deadline, stage limits and reserves of the demo profile | `config/profiles/demo.yaml`, `config/stop_rules.yaml` |
| The deadline enforced inside each model call | `agent/sit_review_agent/llm/runtime.py` `RunDeadline` |
| Refine: one revision per finding (keep, merge or withdraw) | `agent/sit_review_agent/phases/refine.py` |
| An optional pause to approve the plan before research | `config/agent.yaml` `plan_approval`, `sit-review review --plan-approval` |
| The workflow definition, as a diagram generated from the code | `dra states` (Mermaid), drawn in `docs/ARCHITECTURE.md` §2 |

The research stop on the first with-tools run is a known weak point: it reported `sufficient_evidence` with none of its nine questions answered (`docs/live_runs/sit_sample_tools_1/MEASUREMENT.md` "Defects this run exposes", item 3).
