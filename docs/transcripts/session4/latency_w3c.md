# Latency W3c report: documentation and decision records, 2026-10-03

Worker: latency W3c (documentation), branch `s4/w3c-latency`, base `87a0634`, not pushed.
The edit log with every computation is `research/audit/latency_w3c_editlog.md`.

## Done

1. `docs/DECISIONS.md` (`cd7d0d2`): ADR-011 "Concurrent first stage and revision-only refine" and ADR-012 "Streamed CLI output, salvage and hermetic settings", both Proposed, plus a dated amendment note under ADR-002 and index rows for ADR-010 to ADR-012.
2. `docs/USER_DECISIONS.md` (`467dc45`): row #31 with the nine rulings, attributed to SIT FABLE for the owner, 2026-10-03; rows #27 to #30 are unchanged.
3. `eval/prereg.yaml` and `eval/prereg_deviations.md` entry 11 (`4efb7dd`): `effort_per_stage` filled from the demo profile with the four shards, the B0 wording, the scheduling rule, the pilot checkpoint re-base, and the cut and salvage reporting; `frozen: false` stays.
4. `eval/EVAL_PLAN.md` and `docs/BUDGET.md` (`61b7141`): the run-time and cost basis is marked to be re-measured after the first rehearsal, the predictions are shown (19.6 h cap, about $5.4 per FULL run, $565 before margin), the pilot numbers are flagged as describing the old agent, and the budget has only a dated top note.
5. `docs/DEMO_DAY_RUNBOOK.md` (`142f2ac`): §1 backup recordings made with the final code after the freeze and checked with `dra replay`, §5 clock from the stage limits with the replay fallback, the §4.1 paragraph with reserves of 200 s and 75 s, and the §4 intro no longer promising the old reserve arithmetic.
6. `agent/README.md` (`e2a1b31`): the module map gains `llm/partial.py`, the deprecated names are marked pending integration, and the state machine section describes stage 1 as concurrent.
7. `docs/HANDOFF.md` (`8a1186d`): one state paragraph dated 2026-10-03.

## Gates

`ruff check agent harness tests` exited 0.
`pytest -q` exited 1 with 1239 passed and 1 failed: `tests/test_config_layout.py::test_demo_profile_lines_named_by_the_runbook`.
That test asserts the old reserve value 120 s in `config/profiles/demo.yaml` and the old-design runbook sentences "Research stops by 220 s", "is cut at 420 s" and "verify and report keep 120 s".
The runbook now states the new design, and the 75 s reserve lands with W1's config, which is not in this tree.
The test was not weakened.
`make smoke` fails on the same test; `sit-review selftest` exited 0; the prereg YAML parses (exit 0).

## Open for the planner

Prereg `conditions.tier_B` `A4b-medium` now differs from FULL only in research; ruling #31 keeps `high` as the A4b comparison, but the A4b arms were not renamed.

## Not verified

All latency figures are the brief's predictions or measurements; nothing was re-measured here.
The descriptions of W1 and W2 code (`llm/partial.py`, stage tables, clamping of a short deadline) follow the W0 interface notes in `agent/README.md`, not the code on those branches.
No model call was made, and no refused tool call occurred during the edits.
