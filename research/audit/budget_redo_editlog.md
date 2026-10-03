# Budget redo from measured runs: edit log (session 4, 2026-10-03)

Scope: `docs/BUDGET.md` redone from the two timed rehearsals of the concurrent design and the scoring and grading runs on them; `eval/EVAL_PLAN.md` markers replaced; `docs/USER_DECISIONS.md` rows #32 to #34; the 540 s assumption labelled in `docs/DEMO_DAY_RUNBOOK.md` and `config/profiles/demo.yaml`.
Branch `s4/budget`, from `8fd8bea`.
Documents only: no model call, no agent run, no scoring or grading run, no code changed, nothing under `eval/blind/` opened, no `llm.jsonl` opened.

## 1. Inputs (the only numbers used)

| Input | Value | Source |
|---|---|---|
| Medium run (concurrent, demo profile, document-only) | 382.3 s wall, $5.74 CLI estimate, 148,957 output tokens, 344,584 input tokens (344,568 cache writes, 0 reads) | `docs/live_runs/rehearsal_concurrent_1/MEASUREMENT.md`; cache split from `rehearsal_concurrent_high_1/MEASUREMENT.md` "Cost and tokens" |
| Medium shard outputs and walls | 27,109, 28,005, 25,570, 24,763 tokens; 218.0, 230.3, 209.9, 201.6 s | `rehearsal_concurrent_1/MEASUREMENT.md` "Shards" |
| High run (concurrent, `high` on every stage, document-only) | 780.3 s, $8.21, 258,222 output, 378,856 input (378,838 cache writes, 71,971 reads) | `rehearsal_concurrent_high_1/MEASUREMENT.md` |
| Scoring, pre-registered setup | 95 calls $9.54 (medium run), 93 calls $10.65 (high run), 98 calls $10.36 (old run) | `docs/live_runs/QUALITY_COMPARISON.md` |
| Grading | 4 calls $5.30 (each new run), $4.85 (old run) | `QUALITY_COMPARISON.md` |
| Research with tools | NOT measured; the design note predicted 443 s document-only, 450 to 499 s with research, $5.0 to $5.4 per FULL run | `eval/EVAL_PLAN.md` latency note |
| Old sequential run at `high` | 3,372 s wall, $3.68 lower bound (four killed attempts unrecorded) | `QUALITY_COMPARISON.md`, `docs/USER_DECISIONS.md` #28 |
| Old instrument times | scoring 245.6 s, Opus grading 549.3 s per review | `eval/EVAL_PLAN.md` "Run time" (old run) |
| Planning grader prices | Opus $0.57, Sonnet $0.30 per review | `docs/BUDGET.md` §3 |
| Run mix | 132 runs = 84 FULL + 9 A5 + 24 B0 + 15 B0-$; 101 matched runs; 101 graded reviews | `eval/EVAL_PLAN.md` §1.2 |

Run mix check: FULL = A-1 16 + A-2 9 + A-3 9 + A-4 6 + A-5 18 + A-6 3 + A-7 3 + A-8 12 + A-9 8 = 84; A5 = A-3 9; B0 = A-2 9 + A-3 9 + A-4 6 = 24; B0-$ = A-3 9 + A-4 6 = 15; 84 + 9 + 24 + 15 = 132.

## 2. Computations

### 2.1 Price reproduction

- Medium: 344,584 - 344,568 = 16 uncached input tokens.
- Medium: 344,568 × $8/M = $2.756544; 16 × $4/M = $0.000064; 148,957 × $20/M = $2.979140; sum $5.735748, CLI $5.74.
- High: 378,856 - 378,838 = 18 uncached input tokens (the manifest's input count excludes the 71,971 reads).
- High: 378,838 × $8/M = $3.030704; 18 × $4/M = $0.000072; 71,971 × $0.20/M = $0.014394; 258,222 × $20/M = $5.164440; sum $8.209610, CLI $8.21.
- High at a $0.40 read price: $3.030704 + $0.000072 + $0.028788 + $5.164440 = $8.224004.
- Reading: the CLI's estimates match cache writes at $8 per million (2 × the $4 input price of `docs/BUDGET.md` §1.2), reads at $0.20 and output at $20; this is a reproduction, not a check against a bill.

### 2.2 Per-run figures

- FULL document-only = A5 = $5.74, 382.3 s (measured; the medium run was `--no-tools`, which is the A5 condition).
- With research, PREDICTION: increment $5.4 - $5.0 = $0.40 (taking the low end of the predicted range as the document-only figure); time increment 450 - 443 = 7 s to 499 - 443 = 56 s.
- With research: $5.74 + $0.40 = $6.14; 382.3 + 7 = 389.3 s; 382.3 + 56 = 438.3 s.
- A4b-high = $8.21, 780.3 s (measured).
- B0 input: 344,584 / 8 = 43,073 tokens per call; 43,073 × $8/M = $0.344584.
- B0 output: 27,109 + 28,005 + 25,570 + 24,763 = 105,447 tokens; 105,447 × $20/M = $2.108940.
- B0 = $0.344584 + $2.108940 = $2.453524, budgeted $2.45 (derived, assumption: one call does the four shards' output).
- B0 time: 218.0 + 230.3 + 209.9 + 201.6 = 859.8 s (derived; high side, since it counts four start-ups).
- B0-$: $5.74 / $2.45 = 2.343, n = 2; 2 × $2.45 = $4.90 plus an unmeasured self-ranking call, budgeted at FULL's $5.74 (cost-matched by definition); time 2 × 859.8 = 1,719.6 s (n calls assumed one after another).
- Scoring: $9.54 + $10.65 + $10.36 = $30.55; / 3 = $10.1833, budgeted $10.18.
- Opus grader: $5.30 (both new runs).
- Sonnet control grader: $5.30 × 0.30 / 0.57 = $2.7895, budgeted $2.79 (derived; Sonnet not measured).

### 2.3 Tier A agent cost

- FULL 84 × $5.74 = $482.16; A5 9 × $5.74 = $51.66; B0 24 × $2.45 = $58.80; B0-$ 15 × $5.74 = $86.10.
- Sum: $482.16 + $51.66 + $58.80 + $86.10 = $678.72.
- Lines: A-1 16 × $5.74 = $91.84; A-2 9 × $5.74 + 9 × $2.45 = $51.66 + $22.05 = $73.71; A-3 27 × $5.74 + 9 × $2.45 = $154.98 + $22.05 = $177.03; A-4 12 × $5.74 + 6 × $2.45 = $68.88 + $14.70 = $83.58; A-5 18 × $5.74 = $103.32; A-6 3 × $5.74 = $17.22; A-7 $17.22; A-8 12 × $5.74 = $68.88; A-9 8 × $5.74 = $45.92.
- Line sum: $91.84 + $73.71 + $177.03 + $83.58 + $103.32 + $17.22 + $17.22 + $68.88 + $45.92 = $678.72.
- Scored (A-2 to A-7): $73.71 + $177.03 + $83.58 + $103.32 + $17.22 + $17.22 = $472.08; support (A-1, A-8, A-9): $91.84 + $68.88 + $45.92 = $206.64; $472.08 + $206.64 = $678.72.

### 2.4 Tier A instruments and total

- Scoring: 101 × $10.18 = $1,028.18.
- Opus grading: 101 × $5.30 = $535.30; Sonnet control: 101 × $2.79 = $281.79; grading $535.30 + $281.79 = $817.09.
- Second-provider grader: $0 (Anthropic only, `docs/USER_DECISIONS.md` #23).
- Subtotal: $678.72 + $1,028.18 + $817.09 = $2,523.99.
- Margin (30 %, as `docs/BUDGET.md` already uses): $2,523.99 × 1.3 = $3,281.187, $3,281.19.
- By component: $678.72 × 1.3 = $882.336; $1,028.18 × 1.3 = $1,336.634; $817.09 × 1.3 = $1,062.217; rounded $882.34 + $1,336.63 + $1,062.22 = $3,281.19.
- Approval figure: $3,281.19 rounded up to the next dollar, $3,282.
- Instrument share: ($1,028.18 + $817.09) / $2,523.99 = $1,845.27 / $2,523.99 = 0.731.

### 2.5 Sensitivities

- With research predicted: 84 × $0.40 = $33.60; $2,523.99 + $33.60 = $2,557.59; × 1.3 = $3,324.867, $3,324.87.
- Scoring at the highest measured $10.65: 101 × ($10.65 - $10.18) = 101 × $0.47 = $47.47; $2,571.46; × 1.3 = $3,342.898, $3,342.90.
- Every FULL-shaped run at `high`: 93 × ($8.21 - $5.74) = 93 × $2.47 = $229.71; $2,753.70; × 1.3 = $3,579.81.
- Without the Sonnet control: $2,523.99 - $281.79 = $2,242.20; × 1.3 = $2,914.86; the control costs $281.79 × 1.3 = $366.33 with margin.

### 2.6 Wall time

- FULL 84 × 382.3 = 32,113.2 s; A5 9 × 382.3 = 3,440.7 s; B0 24 × 859.8 = 20,635.2 s; B0-$ 15 × 1,719.6 = 25,794.0 s.
- Sum: 32,113.2 + 3,440.7 + 20,635.2 + 25,794.0 = 81,983.1 s; / 3,600 = 22.77 h.
- 2 in parallel: 22.77 / 2 = 11.39 h; 3 in parallel: 22.77 / 3 = 7.59 h (shown as 22.8, 11.4 and 7.6 h).
- With research: 84 × 7 = 588 s and 84 × 56 = 4,704 s; (81,983.1 + 588) / 3,600 = 22.94 h; (81,983.1 + 4,704) / 3,600 = 24.08 h.
- Instruments at the old measured times: 101 × 245.6 s = 24,805.6 s = 6.89 h; 101 × 549.3 s = 55,479.3 s = 15.41 h.
- Owner hours: about 18 h, unchanged (`eval/EVAL_PLAN.md` §1.3; the plan's human tasks did not change).

### 2.7 Comparison with the previous figures

- FULL $2.18 → $5.74: × 2.63 ($5.74 / $2.18 = 2.633).
- Agent $240.12 → $678.72.
- Scoring $1.05 → $10.18 per run (× 9.70); $106.05 → $1,028.18.
- Opus grading $0.57 → $5.30 per review (× 9.30); grading $57.57 + $30.30 = $87.87 → $817.09.
- Tier A with margin, Anthropic only: $564 → $3,281.19; approval $650 → $3,282.
- Pilot checkpoint cost figure: $3.24 → $8.21 (the measured `high` run); $8.21 - $6.14 = $2.07 above the predicted with-research FULL run.
- Tier B line B-1: 9 A4b-high runs × $8.21 = $73.89 before margin; A4b-xhigh not measured; the rest of Tier B not redone.

### 2.8 EVAL_PLAN E1 schedule cell

- A-3 and A-5 hold 36 FULL-shaped runs (A-3 9 FULL + 9 A5, A-5 18 FULL), 9 B0 and 9 B0-$.
- 36 × 382.3 s = 13,762.8 s; 9 × 859.8 s = 7,738.2 s; 9 × 1,719.6 s = 15,476.4 s; sum 36,977.4 s; / 3,600 = 10.27 h; / 2 = 5.14 h; / 3 = 3.42 h (shown as 10.3, 5.1 and 3.4 h).

## 3. Edits

| File | Change | Why |
|---|---|---|
| `docs/BUDGET.md` | Top note replaced by a dated Basis paragraph; §1.1 measured per-run table with arithmetic; old §1 kept as §1.2 planning figures; §2 to §5 marked as planning prices, not redone; §4 Tier A pointer $650 → $3,282; §4 effort-switch note on the `claude_code` backend; §5 checkpoint re-based to $8.21 with the prereg field left as it is; §6 Tier A recomputed with comparison, wall-time tables and an owner approval line left blank | Item 1 |
| `eval/EVAL_PLAN.md` | Cost basis paragraph replaced by the measured figures with a pointer to `docs/BUDGET.md` §1.1 and §6; the old run-time note labelled as the old sequential agent; the "to be re-measured after the first rehearsal" note replaced by the measured figures; §1.2 agent USD column, instruments table, totals and approval line at the measured prices; the pilot-score paragraph labels the old numbers as the old agent and cites `docs/live_runs/QUALITY_COMPARISON.md`; the checkpoint line names the re-based $8.21; the second "to be re-measured" line replaced by the measured run time; E1 schedule cell recomputed; Tier B line B-1 and the Tier A plus B line marked as not redone; one pre-existing em dash placeholder in the run table replaced by "-" | Item 2 |
| `docs/USER_DECISIONS.md` | Rows #32 (the owner: no agent run on the SIT Memory Platform PDF before his key exists), #33 (SIT FABLE: `medium` stays the default on measured ground, `high` is the A4b arm) and #34 (SIT FABLE: the lab brief sets no live-run time limit; 540 s is an assumption) in two new dated sections; nothing renumbered | Item 3 |
| `docs/DEMO_DAY_RUNBOOK.md` | Line 7 (unknowns) and the §5 clock row at 0:30 say the 540 s figure is an assumption pending SIT's answer and name #34; the §5 prediction replaced by the measured 382.3 s (clock 6:52) and the predicted with-research 389.3 to 438.3 s (clock 6:59 to 7:48) | Item 4 |
| `config/profiles/demo.yaml` | One comment line inserted as line 28, after the pinned line 27 (`deadline_seconds: 540`); no value changed and no pinned line moved (`tests/test_config_layout.py` 9 passed) | Item 4 |
| `docs/transcripts/session4/budget_and_records.md`, this file | The session report and this edit log | Item 5 |

### 3.1 Runbook clock arithmetic

- 382.3 s + 30 s = 412.3 s = 6 min 52 s; 389.3 + 30 = 419.3 s = 6:59; 438.3 + 30 = 468.3 s = 7:48.

## 4. Findings left open

- Row #33 says the ablation is re-run in Tier A at larger n, but `eval/EVAL_PLAN.md` still has A4b in Tier B (line B-1); this pass changes neither the run matrix nor the Tier A budget for it; 9 A4b-high runs would add 9 × $8.21 = $73.89 before margin, $96.06 with it (9 × $8.21 × 1.3 = $96.057).
- Prereg `costs.per_run_usd` still holds the planning figures, including `heavy_case_FULL: 3.24`; it is not a `fill_before_freeze` field, so the re-base to $8.21 needs a deviations entry.
- The Sonnet control grader, B0 and B0-$ costs and times are derived, not measured; research with tools is predicted, not measured.
- `docs/BUDGET.md` §2 to §5 (full programme, cut savings) and `eval/EVAL_PLAN.md` Tier B are still at the planning prices.
