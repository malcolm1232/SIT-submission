# Budget redo and decision records (session 4, 2026-10-03)

Worker: the session 4 budget worker, one deliverable, documents only.
Branch `s4/budget`, from `8fd8bea`.
No model call, no agent run, no scoring or grading run, no code changed.
Nothing under `eval/blind/` was opened, no `llm.jsonl` was opened, and nothing under `docs/design/` or `docs/transcripts/` was read.
Every computation is in `research/audit/budget_redo_editlog.md`.

## What was done

1. `docs/BUDGET.md` is redone from measured numbers.
The dated top note is replaced by a Basis paragraph that names the two rehearsals (`rehearsal_concurrent_1`, `rehearsal_concurrent_high_1`) and the scoring and grading runs (`docs/live_runs/QUALITY_COMPARISON.md`).
§1.1 holds the measured per-run figures with their arithmetic, and the old planning figures are kept as §1.2 because §2 to §4 and prereg `costs.per_run_usd` cite them.
§6 recomputes Tier A for the run mix of `eval/EVAL_PLAN.md` and ends with an owner approval line left blank.
2. `eval/EVAL_PLAN.md` replaces its "to be re-measured" markers with the measured figures and points at `docs/BUDGET.md`.
The old-run numbers are labelled as the old agent, and the pilot-score paragraph cites `QUALITY_COMPARISON.md`.
3. `docs/USER_DECISIONS.md` gains rows #32, #33 and #34 in two new dated sections; nothing was renumbered.
4. `docs/DEMO_DAY_RUNBOOK.md` line 7 and the §5 clock, and a new comment line 28 in `config/profiles/demo.yaml`, say the 540 s figure is an assumption pending SIT's answer and name #34.
5. This report and the edit log.

## Per-run figures used

FULL $5.74 and 382.3 s, measured, document-only at `medium`.
A5 $5.74 and 382.3 s, the same measured run, which ran with every tool off.
A4b-high $8.21 and 780.3 s, measured.
FULL with research $6.14 and 389.3 to 438.3 s, a PREDICTION: the measured run plus the design note's predicted increment of $0.40 and 7 to 56 s.
B0 $2.45 and 859.8 s, derived: the mean input of the medium run's calls and the four medium shards' combined output and wall time, in one call.
B0-$ $5.74 (cost-matched to FULL) and 1,719.6 s (n = 2 B0 calls one after another), derived.
Scoring $10.18 per matched run, the mean of the three measured scorings ($9.54, $10.65, $10.36).
Opus grader $5.30 per review, measured; Sonnet control grader $2.79, derived from the planning ratio $0.30 / $0.57.
The CLI's two run costs are reproduced from their token counts with cache writes at $8 per million, reads at $0.20 and output at $20 ($5.7357 and $8.2096).

## Tier A total

Agent $678.72 (84 FULL × $5.74 + 9 A5 × $5.74 + 24 B0 × $2.45 + 15 B0-$ × $5.74).
Scoring $1,028.18 (101 matched runs × $10.18).
Grading $817.09 (101 × $5.30 + 101 × $2.79).
Subtotal $2,523.99; with the 30 % margin $3,281.19 ($882.34 + $1,336.63 + $1,062.22).
Figure for the owner's approval: $3,282, against $650 before.
Sensitivities with margin: research at the predicted cost $3,324.87; scoring at the highest measured $10.65 $3,342.90; every FULL-shaped run at the `high` cost $3,579.81; without the Sonnet control $2,914.86.
The instruments are 73 % of the subtotal, so they, not the agent, set this budget.

## Wall time

The 132 runs take 81,983.1 s = 22.8 h of run time, 11.4 h at 2 and 7.6 h at 3 in parallel.
With research at the predicted times the total is 22.9 to 24.1 h at one run at a time.
Prereg scheduling allows only one FULL run at a time until 12 concurrent CLI sessions are measured, so the parallel rows are not yet allowed for FULL-shaped runs.
Owner hours stay at about 18 h.

## Why the figures moved

FULL rose from $2.18 to $5.74 on measured prices: the CLI writes the whole context at the cache-write price on every call and read nothing back, and the redesign's four shards plus refine write 148,957 output tokens against the 20,000 planned.
Scoring rose from $1.05 to $10.18 per run because the pre-registered setup makes 93 to 98 judge calls per run.
Opus grading rose from $0.57 to $5.30 per review, 4 calls each.
The second-provider grader is not budgeted (#23).

## Pilot checkpoint

`docs/BUDGET.md` §5 re-bases the checkpoint's cost figure to $8.21, the measured cost of the same agent at `high`, as prereg `stop_rule.pilot_checkpoint` delegates.
Prereg `costs.per_run_usd.heavy_case_FULL` still reads $3.24 and was not changed; it is not a `fill_before_freeze` field, so moving it needs a deviations entry.

## Records

- #32, the owner: no agent run on the SIT Memory Platform PDF until his key exists; his words "sure then, as per ur rec." to recommendation (a).
- #33, SIT FABLE for the owner: `medium` stays the default on measured ground, `high` remains the A4b arm, n = 1 document, the owner may reverse.
- #34, SIT FABLE for the owner: the lab brief states no live-run time limit; 540 s is a project assumption (U4) kept as a configurable safety net.

## Gates

`ruff check agent harness tests` exit 0.
`pytest -q` exit 0, 1,557 passed.
`make smoke` exit 0, 238 passed.
`yaml.safe_load` of `eval/prereg.yaml` exit 0.

## Open

- Row #33 says the ablation is re-run in Tier A, but `eval/EVAL_PLAN.md` still has A4b in Tier B (line B-1); the run matrix and the Tier A budget were not changed for it, and 9 A4b-high runs would add $96.06 with margin.
- B0, B0-$, the Sonnet control grader and research with tools are not measured.
- `docs/BUDGET.md` §2 to §5 and the EVAL_PLAN Tier B figures stay at the planning prices.
- All costs are CLI estimates on one document, not billed amounts; Mac load (about 5, and up to 9.41 in the `high` run) may have slowed the timed runs.
