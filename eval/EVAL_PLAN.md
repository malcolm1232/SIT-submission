# Evaluation plan, scoped to three tiers

Date: 2026-10-02. Status: plan, to be executed after the build. The binding version of every hypothesis, metric, test and decision rule is `eval/prereg.yaml`; if this file and the pre-registration disagree, the pre-registration wins. The owner's labelling work is specified in `eval/human_labelling_protocol.md`.

Sources: the scope-cut table in `research/audit/fresh_eyes.md` §2.3 (FE), `research/audit/research_audit.md` §4.6 and §6 (RA), `research/methodology/README.md` and `metrics.md` (MR, MM), `docs/BUDGET.md`, `docs/USER_DECISIONS.md` (UD), `docs/DECISIONS.md` (ADR), `docs/SEALING.md`.

**Cost basis (redone 2026-10-03 from measured runs; `docs/BUDGET.md` §1.1 and §6, arithmetic in `research/audit/budget_redo_editlog.md`).**
Per run: FULL $5.74 and A5 $5.74 (measured, concurrent design, demo profile, document-only), B0 $2.45 (derived), B0-$ $5.74 (cost-matched to FULL); A4b-high $8.21 (measured).
Instruments per scored run: scoring $10.18 (mean of three measured scorings in the pre-registered setup), Opus 5.5 grader $5.30 (measured), Sonnet 5.5 control grader $2.79 (derived).
All totals carry the BUDGET 30 % margin.
Every cost is the CLI's estimate on one document, not a billed amount.
The 2026-10-02 planning figures (FULL $2.18, B0 $0.63, B0-$ $2.18, A5 $1.02, heavy case $3.24; instruments $1.05, $0.57, $0.30) are kept in `docs/BUDGET.md` §1.2 and in prereg `costs.per_run_usd`; they describe the planning model, not a measured run.

**Run time of the old sequential agent at `high` (stale since the latency redesign; kept as the record).** Measured on 2026-10-02, not estimated (`docs/HANDOVER_FULL.md` §8 and §10; artefacts under `docs/live_runs/live_cc_opus_payments_v1/`; arithmetic in `research/audit/verify_runtime_cli_editlog.md`). One FULL-shaped run at `high` on a 21-page PDF through the `claude -p` backend, document-only (no research) and without the refine stage, took 959 s (16.0 min) of successful work: ingest 2 s, understand 158 s, plan 158 s, assess 520 s, verify 33 s, report 88 s. Its wall time was 3,372 s (56.2 min), because four assess attempts were killed by a 600 s timeout that has since been raised to 1,800 s. Research and refine have not been timed, so 16.0 min is a floor for a FULL run, and the default deadline of 3,600 s (60 min, `config/stop_rules.yaml`) is the cap. The single-call conditions (B0, B0-$) have not been timed either; the nearest measured analogue is the 520 s (8.7 min) assess call. Scoring one review in the pre-registered setup took 245.6 s (4.1 min: 98 calls at concurrency 4, 943.7 s of call time), and grading one review took 549.3 s (9.2 min: two samples of Pass A and Pass B, run one after another), so the instruments add 794.9 s (13.2 min) per scored and graded run. The earlier estimate of 8-10 minutes per run (BUDGET §4) is withdrawn. Runs go 2-3 in parallel within rate limits (not yet tried on the `claude -p` backend), with conditions interleaved in a seeded order. The cost figures in this plan are still the estimates made before these measurements; `docs/BUDGET.md` is to be redone from the measured runs (`docs/HANDOVER_FULL.md` §10 step 4).

**Run-time and cost basis after the latency redesign (2026-10-03): measured on two rehearsals; `docs/BUDGET.md` §1.1 and §6.**
The run-time note above describes the old sequential agent at `high`.
The evaluated agent is now the demo profile (`medium` on every stage, research `low`, 540 s deadline) with a concurrent first stage (`docs/DECISIONS.md` ADR-011, ADR-012; `docs/USER_DECISIONS.md` #31 and #33; prereg deviations entry 11).
Measured FULL run, document-only (`docs/live_runs/rehearsal_concurrent_1/MEASUREMENT.md`): 382.3 s, $5.74, 148,957 output tokens, 344,584 input tokens, all written to the cache and none read.
The same agent at `high` on every stage (`docs/live_runs/rehearsal_concurrent_high_1/MEASUREMENT.md`): 780.3 s, $8.21, 258,222 output tokens.
With research: NOT measured; predicted 389.3 to 438.3 s and $6.14 (the measured run plus the design note's predicted research increment of 7 to 56 s and $0.40).
Single-call conditions: not measured; B0 is derived at $2.45 and 859.8 s, B0-$ at $5.74 and 1,719.6 s (`docs/BUDGET.md` §1.1).
Run time of the 132 runs: 84 × 382.3 s + 9 × 382.3 s + 24 × 859.8 s + 15 × 1,719.6 s = 81,983.1 s = 22.8 h at one run at a time, 11.4 h at 2 and 7.6 h at 3 in parallel.
Agent cost: 84 × $5.74 + 9 × $5.74 + 24 × $2.45 + 15 × $5.74 = $678.72 before margin, against the $240.12 planned; Tier A with scoring, grading and the 30 % margin is $3,281.19 (`docs/BUDGET.md` §6).
Scheduling: one FULL run at a time until 12 concurrent CLI sessions are measured, because a FULL run holds up to 6 (prereg `runs_per_item.scheduling`).
Still to measure before Tier A: the with-tools rehearsal (waits for the MCP key, `docs/USER_DECISIONS.md` #31 ruling 9).

---

## 1. Tier A: minimum research-grade core (must finish before submission)

### 1.1 What is in it

| Area | Tier A content |
|---|---|
| Items | S-dev: the 3 synthetic items, v1 and v2 (`eval/synthetic/clinical_rpm`, `payments_orchestration`, `research_lakehouse`). S-heldout: `eval/blind/item_a`, `item_b`, sealed, one access. Real-dev: the SIT sample v1 with a key the owner writes independently (FE R-01), and an owner-written SIT v2 fixture with a gold diff (FE R-06) |
| k | 3 runs per (document, condition) for every scored cell |
| Baselines and ablations | FULL, B0, B0-$, B-gen, A5. B0-$ is moved up from FE's "keep if time" (see 1.5) |
| Primary metric | Recall (strict, sealed key, macro over documents) |
| Key secondary metrics | Precision, adjudicated; Severity-weighted recall; Hallucinated-finding rate; CDR; Fabricated-citation rate; the v2 metrics plus the false-resolution rate; cost and wall time |
| Statistics | Paired two-level cluster bootstrap, Holm over {FULL vs B0, FULL vs B0-$} on Recall and over the three guard-rail tests, BH (q = 0.10) for every breakdown; MDE stated |
| Matcher | Branch A cross-family model if a second key exists, else Opus 5.5 in batch, disclosed as same-family; validated against 100 owner-labelled S-dev pairs |
| Grounding | Code-checked quote existence and location (G1/G2), G3 and citation-support judges on the matcher's model, disclosed |
| Grader | Opus 5.5 at effort `high` (key-blind primary); a second-provider grader at `high` as the headline grader score if a key exists; Sonnet 5.5 control. Supporting only. Meta-validation V1, V4, V10. Human smoke calibration (5 reviews) plus a 5-review frozen-agent sample |
| Governance | `prereg.yaml` frozen and timestamped externally before the first scored run; S-heldout sealed with the derived copies (FE R-03); leakage controls LC1-LC12; access log |
| Robustness and demo | The LLM-dependent part of the robustness minimum gate (robustness §4.2) and demo rehearsals, as support runs that carry no eval claim |

### 1.2 Run matrix and cost

Agent USD at the measured per-run figures of `docs/BUDGET.md` §1.1 (FULL, A5 and B0-$ $5.74, B0 $2.45), redone 2026-10-03; the line arithmetic is in `research/audit/budget_redo_editlog.md` §2.3.

| Line | What | Documents | Conditions × k | Runs | Agent USD |
|---|---|---|---|---:|---:|
| A-1 | Development iteration (support; no claims). Resume from stage checkpoints where possible | S-dev v1, SIT v1 (after the owner's key exists) | FULL | 16 | 91.84 |
| A-2 | Pilot before the freeze (calibration; exploratory): estimates ρ, σ_d, ψ, cost, latency; produces the matcher validation pairs | 3 S-dev v1 | FULL, B0 × 3 | 18 | 73.71 |
| A-3 | Frozen agent on S-dev | 3 S-dev v1 | FULL, B0, B0-$, A5 × 3 | 36 | 177.03 |
| A-4 | Frozen agent on S-heldout (access 1 of 3) | 2 S-heldout | FULL, B0, B0-$ × 3 | 18 | 83.58 |
| A-5 | v2 re-review, fresh and with the A-3 v1 review of the same run index as context | 3 S-dev v2 | FULL × 2 variants × 3 | 18 | 103.32 |
| A-6 | Real-dev: SIT sample v1 | 1 | FULL × 3 | 3 | 17.22 |
| A-7 | SIT v2 fixture, delta mode with a SIT v1 review as context | 1 | FULL × 3 | 3 | 17.22 |
| A-8 | Robustness gate, live LLM part (INF-01, INF-24, LLM-06, BEH-24, ADV-01/04, INP-03; about 6 scenarios × 2). The L0 items run on fakes at no API cost | fixtures | FULL × 2 | 12 | 68.88 |
| A-9 | Rehearsals, cassette recording, fresh-clone check | SIT, rehearsal | FULL | 8 | 45.92 |
| - | B-gen floor (no model call; matched only) | 5 keyed v1 | 1 each | 0 | 0 |
| | **Scored runs (A-2 to A-7)** | | | **96** | **472.08** |
| | **Support runs (A-1, A-8, A-9)** | | | **36** | **206.64** |
| | **Agent total** | | | **132** | **678.72** |

Scoring against a key that is not signed off (LC12).
The harness refuses to score, or to run the grader's key-aware diagnostic, on a key whose `scored_run_ready` is false, unless the command is given `--exploratory` (SIT FABLE ruling #26, `docs/USER_DECISIONS.md`; `harness/README.md`, "LC12").
A pilot scored before the owner signs the S-dev keys (T3) is therefore an exploratory run: it uses `--exploratory`, every artefact it writes is marked exploratory, and it may not be reported as confirmatory.
The three pilots under `docs/live_runs/live_cc_opus_payments_v1/` (`eval_pilot/`, `eval_pilot2_bounded/`, `grade_pilot/`) predate the guard and are exploratory; a note file in each says so.
Their numbers (strict recall 11 of 14, adjudicated precision 0.95, severity-weighted recall 0.73, grader S 83.8) describe the OLD sequential single-call agent at `high` and are stale for the latency design (ADR-011); they are not a baseline for the new agent.
The pilot scores of the new agent are in `docs/live_runs/QUALITY_COMPARISON.md` (exploratory, unsigned key, unfrozen prereg, one document, one run per arm): concurrent `medium` and concurrent `high` each match 13 of 14 flaws strictly, adjudicated precision 0.944 and 0.947, severity-weighted recall 0.933 both, grader S 83.0 and 83.8.
Lines A-3 to A-7 score only signed keys; `sit-eval aggregate` refuses to put an exploratory score into their analysis.

Instruments:

| Instrument | Volume | USD |
|---|---|---:|
| Scoring: matcher, adjudicator, G3 and citation judges (`sit-eval score`, pre-registered setup) | 101 matched runs (96 scored + 5 B-gen) × $10.18 (mean of three measured scorings) | 1,028.18 |
| Opus 5.5 grader (primary) | 101 reviews (78 Tier A reviews from A-3 to A-7, 20 V-test grades for R_base, V1, V4, V10 × 5, 3 constructed calibration variants) × $5.30 (measured) | 535.30 |
| Sonnet 5.5 control grader | 101 × $2.79 (derived, not measured) | 281.79 |
| Second-provider grader | Not budgeted: Anthropic only for now (`docs/USER_DECISIONS.md` #23) | 0 |

| Total | Subtotal | **× 1.3** |
|---|---:|---:|
| Agent | $678.72 | $882.34 |
| Scoring | $1,028.18 | $1,336.63 |
| Grading | $817.09 | $1,062.22 |
| **Tier A, Anthropic only** | **$2,523.99** | **$3,281.19** |
| Sensitivity: FULL with research at the predicted $6.14 (+$0.40 × 84 runs) | $2,557.59 | $3,324.87 |
| Sensitivity: every FULL-shaped run at the measured `high` cost $8.21 (+$2.47 × 93 runs) | $2,753.70 | $3,579.81 |

**Tier A figure for the owner's approval: $3,282** (`docs/BUDGET.md` §6, "Owner approval"; it was $650 at the planning prices). The `high` sensitivity row is what the pilot checkpoint protects against: if the pilot median FULL cost exceeds the re-based $8.21, re-plan before freezing (BUDGET §5).

The checkpoint's median is `sit-eval aggregate` `conditions.FULL.cost_usd.median_fully_accounted`, over FULL runs in which every billed model call's usage was recorded (prereg `costs.usage_completeness`; SIT FABLE ruling #28, 2026-10-03).
A run with a model call that was killed or cut has null cost and tokens with its recorded figures beside them as lower bounds, is excluded from that median and counted; the aggregate's `pilot_checkpoint` is `fail` if the lower-bound median over all FULL runs exceeds $3.24, `pass` only if every FULL run is fully accounted and the median is at or below it, else `not_evaluable`.
A lower bound can fail the checkpoint but never pass it.
For the latency design the checkpoint's cost figure is re-based on `docs/BUDGET.md` §5 as redone from the rehearsals: $8.21 per FULL run, the measured cost of the same agent at `high` (prereg `costs.per_run_usd.heavy_case_FULL` still reads $3.24 and is not changed by this pass), and its wall-time gate stays the 540 s demo slot (prereg `stop_rule.pilot_checkpoint`, deviations entry 11).

Wall time of the OLD sequential agent, from the run-time note above (stale; kept as the record): the 132 runs are 93 FULL-shaped runs (84 FULL and 9 A5) and 39 single-call runs (24 B0 and 15 B0-$). Floor: 93 × 959 s + 39 × 520 s = 109,467 s = 30.4 h of run time, which is 10.1-15.2 h of laptop wall time at 2-3 in parallel. Cap: 132 × 3,600 s = 132 h of run time, which is 44-66 h of wall time at 2-3 in parallel. The pilot (A-2) times research and refine and replaces the floor with a measured median. Instruments: scoring 101 matched runs × 245.6 s = 6.9 h, and Opus grading 101 reviews × 549.3 s = 15.4 h; the Sonnet control grader has not been timed. The earlier line (132 runs × 8-10 min ≈ 18-22 h, about 7-11 h of wall time) is withdrawn.

Since the latency redesign (2026-10-03) the floor and cap above describe the old agent.
Measured for the new agent (`docs/BUDGET.md` §6): 84 FULL × 382.3 s + 9 A5 × 382.3 s + 24 B0 × 859.8 s + 15 B0-$ × 1,719.6 s = 81,983.1 s = 22.8 h of run time, 11.4 h of wall time at 2 and 7.6 h at 3 in parallel; the B0 and B0-$ times are derived, and with research at the predicted 389.3 to 438.3 s the total is 22.9 to 24.1 h.

### 1.3 Grading and human workload (one person, the owner)

Details, rules and time per item are in `eval/human_labelling_protocol.md`.

| Task | When | Hours |
|---|---|---:|
| T1 Independent SIT key, written before any model output on the SIT document is seen | Before the first agent run on the SIT sample | 3.5 |
| T2 Onboarding: codebook, grading README §1-§4, worked examples (only after T1) | Build day 2 | 0.75 |
| T3 Sign off `core_insight` for the 45 S-dev flaws | Before the matcher is validated | 1.5 |
| T4 Label 100 matcher candidate pairs from the pilot | After A-2 | 1.75 |
| T5 Grader smoke calibration, 5 reviews | After A-2 | 2.1 |
| T5b Hand-edit R_base for V1, V4, V10 | After A-6 | 0.5 |
| T6 Sign off `core_insight` for the 28 S-heldout flaws (blind to outputs), then review adjudication labels on S-heldout runs | Access-1 session, after A-4 | 1.0 + 2.0 |
| T7 Grader sample: 5 frozen-agent reviews | After A-3 to A-7 | 1.8 |
| **Labelling subtotal** | | **14.9** |
| T8 Write the SIT v2 fixture and its gold diff (authoring, FE R-06) | Build days 3-4 | 3.0 |
| **Tier A total** | | **about 18 h** |

FE's core estimate of 8-10 h counted matcher pairs and adjudication only; the difference is the SIT key (T1), the SIT v2 fixture (T8), the `core_insight` sign-offs that RA action 8 assigns to a human (FE N12), and the grader calibration the protocol asks for. All sessions are 90 minutes or shorter.

### 1.4 Claims the submission will make, and the runs that support each

Tier A must be sufficient on its own. Each claim is worded at the strength its evidence allows; the decision rules are in `prereg.yaml`.

| # | Claim (as it will be worded) | Hypothesis | Runs | Metric(s) |
|---|---|---|---|---|
| CL1 | The agent completes the review and its output is complete and traceable: schema-valid, every quote verified against the document text, every external source cited by ledger ID | descriptive | A-3 to A-7 FULL (39 runs) | Run outcome counts (ITT), Quote fabrication rate, Source-type accuracy, RJR_struct |
| CL2 | On planted flaws in 5 keyed documents, the agent finds more than a single call with the same schema (or: no evidence of a difference at this n, with the MDE) | H1 | A-3, A-4 FULL and B0 (30 runs) | Recall |
| CL3 | Whether the gain survives a cost-matched single-call baseline, reported either way | H2 | A-3, A-4 FULL and B0-$ (30 runs) | Recall |
| CL4 | Higher recall is not bought with lower precision or more unjustified changes to sound sections | H3, H4 | A-3, A-4 FULL and B0 | Precision, adjudicated; CDR |
| CL5 | Findings stay grounded in the document | H5 | A-3, A-4 FULL and B0 | Hallucinated-finding rate |
| CL6 | With every tool off, the agent invents no external source and says no research was done | H6 | A-3 A5 (9 runs); A-8 INF-24 | Fabricated-citation rate, disclosure |
| CL7 | On a revised document the agent recognises fixes, keeps open flaws open and does not mark unchanged text resolved (exploratory; 3 documents, 3 introduced flaws) | H7 | A-5 (18 runs); A-7 (3 runs) | v2 metrics, false_resolution_rate |
| CL8 | Results on two sealed held-out documents, with the S-dev to S-heldout gap read against B0 (no generalisation claim) | H8 | A-3, A-4 FULL and B0 | Recall DiD |
| CL9 | On the SIT document, how the agent's findings compare with a key the owner wrote independently: both-found, owner-only, model-only | H9 | A-6 (3 runs); T1 | Recall vs the owner key, counts |
| CL10 | The measuring instruments are valid enough for the numbers reported, at the tier reached | H10 | A-2 pairs; B-gen; grader V1, V4, V10; T4, T5, T7 | Matcher κ, B-gen Recall, grader agreement |
| CL11 | Cost and run time per review, by condition | descriptive | All 132 runs' manifests | Cost (USD), tokens, tool calls, wall time; median and IQR over fully accounted runs, the share excluded for unrecorded usage, a lower-bound median over all runs, and the intention-to-treat share of runs with any cut model call (ruling #28) |
| CL12 | The evaluation was pre-registered and leak-checked: frozen hash timestamped outside the repo, held-out access logged, leakage audit clean | LC1-LC12 | Leakage audit; access log | Leakage table |

Claims the submission will **not** make in Tier A: that research, iteration or the verify stage each contribute (A1-A3 not run); that the results hold for another model (A4 is Tier B and within one family in any case); that `high` is the best effort level (A4b is Tier B); anything about independently authored designs (no Blind set), other domains (no OOD document), confidence calibration or ranking quality.

### 1.5 Deviations from the FE scope table, and why

| FE said | This plan | Reason |
|---|---|---|
| B0-$ "keep if time" | Tier A | MR §0(d) makes cost-matched baselines part of "research-grade", and BUDGET §5 lists B0-$ under "never cut". It adds 15 runs ($32.70). Without it CL2 could only be worded "more than a cheaper baseline" |
| Grader "V1, V4, V10 only" with no human grading | V1, V4, V10 plus 10 owner-graded reviews | The labelling brief asks for 5 calibration items and a sample. Grader numbers stay supporting |
| Matcher "about 100 pairs" | 100 pairs; intra-rater re-label in Tier B | Same as FE |
| A1-A4e deferred | A1-A3 deferred; A4 (Sonnet as agent) and A4b (effort sweep) in Tier B | UD #5 redefines A4 and adds A4b; A4e (effort `low`) is superseded |
| "about 90-100 runs" | 96 scored runs plus 36 support runs | FE's figure matches the scored matrix; the support runs (dev, robustness gate, rehearsals) are listed so the budget is complete |

### 1.6 Day-by-day schedule

The deadline is still unknown (FE N1). Days are counted from the first build day. The schedule fits a 4-day build (B5 and B6 collapse into B4) or a 6-day build.

| Day | Build (developer and coding sessions) | Owner (human) | Eval runs |
|---|---|---|---|
| B0 | `.gitignore`, `.env.example`; seal S-heldout and the derived copies (LC3, LC4); commit this plan and the draft `prereg.yaml` | **T1 SIT key** (3.5 h); hash it and commit the hash before any agent run on the SIT document | none |
| B1 | Thin slice on one S-dev v1 document: ingest → understand → plan → research → assess → verify → report; manifest and logs | Approve the Tier A budget; confirm which API keys exist (fixes the grader and matcher branch) | A-1 (dev, S-dev only) |
| B2 | Research loop over the 2 MCP servers with timeouts and doc-only fallback; ledger; whole-report verification (FE R-12); latency per stage (FE N3) | T2 onboarding (0.75 h) | A-1 (first SIT v1 runs allowed now) |
| B3 | Delta mode with a code text diff (FE R-09); B0, B0-$, A5, B-gen harnessed on the same schema; `eval/score.py` with the MM §14 unit test (LC9); matcher | T3 S-dev `core_insight` sign-off (1.5 h); start T8 SIT v2 | A-1 |
| B4 | Fix what the pilot shows; matcher validation; grader pipeline; robustness gate | T4 100 matcher pairs (1.75 h); T5 grader smoke (2.1 h); finish T8 (3.0 h total) | **A-2 pilot** (18), A-8 |
| B5 | Pilot-driven fixes; leakage tooling (LC5-LC8, LC10, LC11) | Review matcher κ; if κ < 0.60 apply protocol §7 | A-1 (last), A-9 |
| B6 | **Freeze**: fill the pilot fields in `prereg.yaml`, flip `frozen`, hash, external timestamp (LC1); tag the agent commit | Send the hash to the SIT officer, or push the signed tag | none |
| E1 | none | none | **A-3** (36) and **A-5** (18), interleaved; at the measured and derived per-run times (`docs/BUDGET.md` §1.1) 36 FULL-shaped × 382.3 s + 9 B0 × 859.8 s + 9 B0-$ × 1,719.6 s = 13,762.8 s + 7,738.2 s + 15,476.4 s = 36,977.4 s = 10.3 h of run time, 5.1 h at 2 and 3.4 h at 3 in parallel (FULL runs one at a time until 12 concurrent CLI sessions are measured), so E1 can run into a second day; the old agent's floor was 12.2 h |
| E2 | Leakage audit (LC10) → unseal (access 1) → render the held-out PDFs by script | T6a held-out `core_insight` sign-off after the runs (1.0 h) | **A-4** (18), **A-6** (3), **A-7** (3) |
| E3 | Matching, adjudication first pass, grader batches, runtime access scan (LC11) | T6b held-out adjudication review (2.0 h); T5b R_base (0.5 h); T7 grader sample (1.8 h) | V-tests (grader only) |
| E4 | `eval/score.py` once on the complete set; tables; write results and limitations | Read the results and sign the rater statement | none |
| E5 | Buffer, or start Tier B | Tier B intra-rater re-label if ≥ 7 days have passed since T4 | Tier B |

### 1.7 What unblocks what

```
T1 SIT key (hashed) ─────────────────────────────► first agent run on the SIT document (A-1 SIT, A-6)
schema + scorer + baselines (B3) ─► A-2 pilot ─┬─► ρ, σ_d, ψ, cost, latency ─► prereg fields ─► FREEZE (LC1) ─► A-3, A-5
                                               ├─► candidate pairs ─► T4 labels ─┐
T3 S-dev core_insight sign-off ──────────────────────────────────────────────────┴─► matcher validation (H10) ─► any matcher number
pilot reviews ─► T5 grader smoke ─► grader numbers (supporting)
FREEZE + sealing + LC2-LC10 ─► unseal access 1 ─► A-4 ─► T6a held-out core_insight ─► matching ─► T6b adjudication ─► P_adj, HFR on S-heldout
A-3 v1 reviews ─► A-5 with-context variant;   SIT v1 review + T8 SIT v2 ─► A-7
all scored runs + LC11 ─► score.py (once) ─► report
```

The critical path is: thin slice → pilot → matcher validation and freeze → frozen runs → held-out access → adjudication → scoring. Human tasks T1 and T3 must not slip, because the first SIT run and the matcher validation wait on them.

---

## 2. Tier B: if time

Pre-registered as exploratory in `prereg.yaml` (`tier_B_hypotheses`). In priority order:

| Line | What | Runs | Agent USD | Human hours | Supports |
|---|---|---:|---:|---:|---|
| B-1 | A4b effort sweep: FULL with every stage at `high` (A4b-high) and at `xhigh` (A4b-xhigh) on 3 S-dev v1 × 3; the A-3 FULL run (the demo profile, `medium`) is the reference (prereg deviation 11). The USD figure predates the latency redesign (`medium` at $2.18, `xhigh` at $3.24 per run) and is not redone; at the measured `high` cost the 9 A4b-high runs alone are 9 × $8.21 = $73.89, and A4b-xhigh is not measured (`docs/BUDGET.md` §6) | 18 | 48.78 | 0 | HB1: whether `high` is justified and whether any stage merits `xhigh` (UD #1, #5) |
| B-2 | Intra-rater re-label of 40 matcher pairs, ≥ 7 days after T4; 50 more pairs to reach RA's 150 | 0 | 0 | 0.75 + 0.9 | Matcher reliability ceiling |
| B-3 | Grader sample extended to 20 reviews (the tentative tier) | 0 | 0 | 3.7 | Grader validity tier "tentative" |
| B-4 | A4: Sonnet 5.5 as the agent model, FULL and B0 on the 5 keyed documents × 3 (S-heldout access 2). Per-run cost derived from `cost_model.py` (Sonnet $1.30 central, scaled to hybrid ingestion: about $1.37; B0 about $0.40), UNVERIFIED | 30 | 26.55 | 0 | HB2 (within one family) |
| B-5 | Human-planted mini-set: 5-8 owner-planted flaws in a public design document; FULL and B0 × 3 | 6 | 8.43 | 3.5 | HB3, the only non-LLM flaw distribution (FE §2.2) |
| B-6 | One fully sound control document; FULL and B0 × 3 | 6 | 8.43 | 3.0 | HB4; unblocks INP-28 and Fully-sound doc accuracy |
| B-7 | One AI-platform-family rehearsal document (FE R-07), FULL × 3, not scored | 3 | 6.54 | 2.0 | Demo protection (refusal and latency) |
| B-8 | Author `approved_decisions[]` and `expected_disposition` in the S-dev keys | 0 | 0 | 1.5 | Unblocks Approved-decision violation rate and Action-type accuracy (S-dev only) |
| B-9 | Spot-check 8 audit fact verdicts against primary sources (FE §2.2) | 0 | 0 | 1.5 | Key correctness |
| B-10 | Critical recall and stability (Jaccard over k) from Tier A runs | 0 | 0 | 0 | Secondary, no new runs |
| | **Tier B total** | **63** | **98.73** | **about 17** | |

Instruments for Tier B: 60 matched runs × $1.05 = $63.00; 60 reviews × ($0.57 + $0.30) = $52.20; second-provider grader 60 × $0.57 = $34.20 if a key exists. **Tier B with margin: $278 (Anthropic only) or $323 (with a second-provider grader).** These Tier B figures are at the 2026-10-02 planning prices and are not redone; Tier A is now $3,281.19 at measured prices (`docs/BUDGET.md` §6), so a Tier A plus Tier B sum would mix the two bases and is not given.

---

## 3. Tier C: deferred, stated as limitations

Each item goes in `docs/LIMITATIONS.md` with the reason and what it would have shown.

| Deferred | What the submission cannot claim without it |
|---|---|
| The commissioned Blind set and its single evaluation | Any generalisation to designs written by people or models with no knowledge of this project; S-heldout shares the generator family and template |
| OOD document | Behaviour outside software and data-platform designs |
| A1 (no research), A2 (no iteration), A3 (no verification) | That each component contributes; only the whole agent vs single-call baselines is tested |
| A4e (effort `low`) | Superseded by A4b (UD #5) |
| Cross-provider agent | That results are not tied to Claude (ADR-002) |
| Paraphrase and rename probe, section reorder probe, template-tell probe | That the agent does not exploit surface strings or the shared template (RA §4.2) |
| Capture-recapture on synthetic items, base-document audit | How incomplete the synthetic keys are |
| nDCG@k, MRR_crit, ECE, Brier, AUROC, Research yield, Overrun, Citation recall, RJR_subst | Ranking quality, confidence calibration, research efficiency, substantive recommendation quality |
| Local open-weight judges; full grader V1-V13; ≥ 100 doubly graded reviews; a peer rater | Cross-family or human-human reliability; grader validity beyond the tier reached |
| S-heldout milestone checks (accesses 2-3 used only for Tier B or an infrastructure re-run) | Development-time held-out tracking |
| H (human expert ceiling) | An absolute ceiling for recall |
| Robustness P1 and P2 scenarios; the remaining P0 items beyond the minimum gate | Robustness beyond the demo-critical failures |
| k = 5 on the primary comparison | Tighter intervals; the MDE stays about 0.22-0.27 recall |
| Multiple input documents; instrument-failure scenarios (RA §3) | Behaviour when several designs arrive together or a judge fails |

---

## 4. Pre-registration status

`eval/prereg.yaml` is a draft (`frozen: false`). Its hypotheses and tests are fixed now; only the pilot-measured fields listed in `freeze.fill_before_freeze` may change before the freeze. The SHA-256 of the draft as written on 2026-10-02 is recorded below so the freeze diff can be checked against it:

```
63cd8a6fcb52dfea54874defffb06a7cff00405007272493af0631c11b464c40  eval/prereg.yaml (draft, 2026-10-02)
```
