# Validation and review

This file answers lab §5.3 "validation and review approach".
Validation happens at two levels that never share code: inside each run the agent checks its own output with code before it writes the report, and outside the agent a separate harness measures the reviews against planted flaws and grades them on the lab's rubric.
A third level, the robustness suite, checks that every failure the agent can meet ends in a disclosed degradation and not a wrong or missing report.
The architecture text is `docs/ARCHITECTURE.md` §6 (honesty and traceability), §8 (robustness) and §9 (the evaluation harness).

## Inside each run

| Check | Where it is implemented |
|---|---|
| Every finding's quotes are found in the canonical text, exactly or by a close fuzzy match on the cited page | `agent/sit_review_agent/ingest/anchor.py`, `agent/sit_review_agent/phases/verify.py` |
| Every cited evidence ID exists in the ledger, and URLs come only from the ledger | `agent/sit_review_agent/state/evidence_ledger.py`, `agent/sit_review_agent/phases/report.py` |
| The run invariants (schema, anchors, citations, complete recommendations, disclosed degradations, no secrets, complete manifest, constant registry hash, existing finding IDs) | `agent/sit_review_agent/invariants.py` |
| `not_assessed` can be set only by code, with a reason | `agent/sit_review_agent/phases/report.py` |

## Outside the agent

| Check | Where it lives |
|---|---|
| Scoring a review against planted flaws, with strict and lenient recall, adjudicated precision and grounding judges | `harness/sit_eval/`, `harness/README.md`, `sit-eval score` |
| The key-blind lecturer grader | `harness/sit_eval/grader/`, `sit-eval grade run` |
| The pre-registered analysis and its deviations | `eval/prereg.yaml`, `eval/prereg_deviations.md` |
| The refusal to score an unsigned key without `--exploratory` | `harness/sit_eval/lc12.py`, `docs/USER_DECISIONS.md` #26 |
| Reproducibility policy and the run manifest | `docs/REPRODUCIBILITY.md` |
| Sealing of the held-out answer keys | `docs/SEALING.md` |
| The robustness scenarios, fault schedules and results | `research/robustness/scenarios.md`, `tests/robustness/`, `tests/robustness/results/robustness_summary.txt` |

## Results so far

The only quality results are three exploratory scorings and gradings on one synthetic document, one run per arm (`docs/live_runs/QUALITY_COMPARISON.md`).
The robustness results are 88 P0 scenarios, 56 passing offline and 32 blocked, none failing (`tests/robustness/results/robustness_summary.txt`).
What these results do not show is in `docs/LIMITATIONS.md`.
