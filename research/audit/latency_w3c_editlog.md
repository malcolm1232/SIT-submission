# Latency W3c edit log (documentation and decision records), 2026-10-03

Branch `s4/w3c-latency`, base `87a0634`.
Every number written comes from the planner's brief (measured 2026-10-03 on the owner's Mac) or is computed from it below.
No model call was made.
`docs/design/`, `docs/transcripts/` (other than this worker's report) and `eval/blind/` were not opened.

## Commits

| Item | Commit | Files |
|---|---|---|
| 1 | `cd7d0d2` | `docs/DECISIONS.md`: ADR-011, ADR-012, ADR-002 amendment note, index rows 010-012 |
| 2 | `467dc45` | `docs/USER_DECISIONS.md`: row #31 |
| 3 | `4efb7dd` | `eval/prereg.yaml`, `eval/prereg_deviations.md` entry 11 |
| 4 | `61b7141` | `eval/EVAL_PLAN.md`, `docs/BUDGET.md` (top note only) |
| 5 | `142f2ac` | `docs/DEMO_DAY_RUNBOOK.md` §1, §4 intro, §4.1 paragraph, §5, §9 open point |
| 6 | `e2a1b31` | `agent/README.md` |
| 7 | `8a1186d` | `docs/HANDOFF.md` |

## Arithmetic

- Slack of the document-only prediction: 540 - 443 = 97 s.
- Run-time cap: 93 × 540 s = 50,220 s; 39 × 520 s = 20,280 s; sum 70,500 s; 70,500 / 3,600 = 19.58 h, written 19.6 h.
- Agent budget: 93 × $5.4 = $502.20; 39 × $1.6 = $62.40; sum $564.60, written $565 before margin.
- Sessions held by one FULL run in stage 1: understand + plan + 4 shards = 6; two runs at once = 2 × 6 = 12 (hence "one FULL run at a time until 12 concurrent sessions are measured"; 4 and 8 were measured).
- Runbook clock = run time + 0:30: 125 s = 2:05 -> 2:35; 265 s = 4:25 -> 4:55; 465 s = 7:45 -> 8:15; 530 s = 8:50 -> 9:20; 540 s = 9:00 -> 9:30; 443 s = 7:23 -> 7:53; 450 s = 7:30 -> 8:00; 499 s = 8:19 -> 8:49.
- Assess shards copied from `config/agent.yaml` `assess.shards` (lines 60-68) into prereg `agent_under_test.effort_per_stage.assess_shards`.

## Choices made

- ADR format: ADR-011 and ADR-012 follow ADR-001 to ADR-009 (`## ADR-0NN. Title`, Context, Decision, Consequences, Status), not ADR-010's variant. ADR-010 was missing from the index table and is added there with a plain dash in its title.
- The ADR-002 amendment is a dated note under ADR-002, in the style of ADR-003's closing note; ADR-002's text is not edited.
- Prereg `effort_per_stage` is filled as a mapping (profile, one key per stage including `understand`, the four shards). It is a `fill_before_freeze` field; it is logged in entry 11 because it departs from the draft's stated `high` default. No other fill value changed; `costs.per_run_usd.heavy_case_FULL` stays $3.24 and the pilot checkpoint text says it is re-based after the first rehearsal.
- Runbook §4 intro: the old `--deadline 300` example (reserves 120 s + 200 s) described the old design; replaced by what the README records about stage limits below a short deadline (W1 must clamp and announce; pending integration, not rehearsed). The string `--deadline 540` is avoided (a test forbids it).
- Runbook §4.2 row 4's remark that an effort change starts a new prompt cache was left as written.

## Open, not changed

- Prereg `conditions.tier_B` `A4b-medium` now differs from FULL only in research (`medium` against `low`); ruling #31 keeps `high` as the A4b comparison; the arms are not renamed. Noted in deviation entry 11 for the planner.

## Gates at `8a1186d`

| Gate | Exit | Result |
|---|---|---|
| `ruff check agent harness tests` | 0 | All checks passed |
| `pytest -q` | 1 | 1239 passed, 1 failed: `tests/test_config_layout.py::test_demo_profile_lines_named_by_the_runbook` |
| `sit-review selftest` | 0 | passes |
| `make smoke` | non-zero (make: Error 1) | the same test fails; 217 passed |
| `python -c "import yaml; yaml.safe_load(open('eval/prereg.yaml'))"` | 0 | parses |

The failing test asserts that `config/profiles/demo.yaml` holds `report_reserve_seconds: 120` and that the runbook contains the old-design sentences "Research stops by 220 s", "is cut at 420 s" and "verify and report keep 120 s".
The runbook now states the new design's limits (265 / 465 / 530 s, reserves 200 s and 75 s), so the needles are gone, and the 75 s reserve is not in this tree (W1 lands it).
The test was not edited or weakened; it is updated with W1's config at integration.
The three §4.1 listing tests (`test_runbook_listing_equals_the_config_file`) pass.
