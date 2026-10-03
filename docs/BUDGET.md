# Project budget

**Basis, 2026-10-03 (redone from measured runs; `docs/DECISIONS.md` ADR-011, `docs/USER_DECISIONS.md` #31 and #33).**
The per-run figures in §1 and the Tier A budget in §6 are now measured, not planned.
Agent: two timed rehearsals of the concurrent design on `eval/synthetic/payments_orchestration/design_v1.pdf`, document-only, through the `claude_code` backend: `docs/live_runs/rehearsal_concurrent_1/` (demo profile, `medium`, 382.3 s, $5.74) and `docs/live_runs/rehearsal_concurrent_high_1/` (`high` on every stage, 780.3 s, $8.21).
Instruments: the pre-registered scoring and the key-blind grading of those two runs and of the old sequential run (`docs/live_runs/QUALITY_COMPARISON.md`): scoring 95 calls $9.54, 93 calls $10.65 and 98 calls $10.36; grading 4 calls $5.30 for each new run and $4.85 for the old one.
Every cost is the CLI's estimate, not a billed amount, and n = 1 run per figure on one document.
Research with tools has not been measured: the with-research figures in §1 are a prediction and are marked so.
The arithmetic behind every figure on this page is in `research/audit/budget_redo_editlog.md`.
§2 to §4 (the full programme) are still at the 2026-10-02 planning prices and are kept as the reference; they are not redone here.

Date: 2026-10-02. Resolves audit P1 item 17 and M12 (`research/audit/research_audit.md`). Every figure comes from `research/models/cost_model.py` (run `python3 research/models/cost_model.py`; the "ALL-OPUS", "Budget matrix" and "Sensitivity" sections print all of them). Reconciled line by line against the script output on 2026-10-02 (`research/audit/verify_docs.md` item 2). Claude prices are from the `claude-api` skill (cached 2026-09-25); non-Claude prices are **UNVERIFIED**. The token base is **UNVERIFIED** until `messages.count_tokens` is run on the SIT PDF on the laptop (audit U3); re-run the script with the measured values and update this page.

## 1. Per-run cost, all Opus 5.5 (ADR-002)

### 1.1 Measured, 2026-10-03 (the basis of §6)

| Condition | Basis | USD per run | Run time |
|---|---|---|---|
| **FULL**, concurrent design, demo profile (`medium`, research `low`), document-only | Measured: `rehearsal_concurrent_1`, 8 calls, all usage recorded | **$5.74** | **382.3 s** |
| FULL with research (tools on) | **PREDICTION**, not measured: the measured run plus the design note's predicted research increment, $0.40 and 7 to 56 s | $6.14 | 389.3 to 438.3 s |
| A5 (every tool off) | The measured run is this condition: `--no-tools`, document text only | $5.74 | 382.3 s |
| A4b-high (FULL with `high` on every stage) | Measured: `rehearsal_concurrent_high_1`, 8 calls, all usage recorded | $8.21 | 780.3 s |
| B0 (one assess call with every criterion) | Derived, not measured: one call carrying the mean input of the medium run's calls and the four medium shards' combined output, at the reproduced prices below | $2.45 | 859.8 s |
| B0-$ (best-of-n B0, cost-matched to FULL) | Matched to FULL by its definition (prereg `conditions.tier_A`); n = 2 at the derived B0 cost, the n calls assumed to run one after another | $5.74 | 1,719.6 s |
| Old sequential agent at `high` (stale, ADR-011) | `live_cc_opus_payments_v1`: lower bound, four killed attempts unrecorded (#28) | at least $3.68 | 3,372 s |

| Instrument, per scored run | Basis | USD |
|---|---|---|
| Scoring: `sit-eval score`, pre-registered setup (matcher, adjudicator, G3 and citation judges) | Measured three times: 95 calls $9.54, 93 calls $10.65, 98 calls $10.36; the mean is used | $10.18 |
| Opus 5.5 grader, key-blind, 2 samples | Measured: 4 calls, $5.30 on both new runs ($4.85 on the old one) | $5.30 |
| Sonnet 5.5 control grader | Derived, not measured: the Opus figure scaled by the planning ratio of the two graders ($0.30 / $0.57) | $2.79 |

Arithmetic (all in `research/audit/budget_redo_editlog.md`):

- The CLI's two run costs are reproduced from their token counts if every cache write is priced at $8 per million (twice the $4 input price), cache reads at $0.20 and output at $20.
- Medium run: 344,568 cache-write tokens × $8/M = $2.7565, 16 uncached input tokens × $4/M = $0.0001, 148,957 output × $20/M = $2.9791; sum $5.7357, the CLI's $5.74.
- High run: 378,838 × $8/M = $3.0307, 18 uncached × $4/M = $0.0001, 71,971 cache reads × $0.20/M = $0.0144, 258,222 output × $20/M = $5.1644; sum $8.2096, the CLI's $8.21 (at a $0.40 read price the sum is $8.2240).
- So the CLI writes the whole context at the cache-write price on every call and the medium run read nothing back; that, and 148,957 output tokens against the 20,000 planned, is why FULL costs $5.74 and not $2.18.
- With research: the design note predicted $5.0 to $5.4 per FULL run and 443 s document-only, 450 to 499 s with research; taking $5.0 as its document-only figure, the predicted research increment is $5.4 - $5.0 = $0.40 and 450 - 443 = 7 s to 499 - 443 = 56 s; $5.74 + $0.40 = $6.14 and 382.3 + 7 = 389.3 s to 382.3 + 56 = 438.3 s.
- B0 input: 344,584 input tokens / 8 calls = 43,073 per call; × $8/M = $0.3446.
- B0 output: the four medium shards wrote 27,109 + 28,005 + 25,570 + 24,763 = 105,447 tokens; × $20/M = $2.1089; B0 = $0.3446 + $2.1089 = $2.4535, so $2.45.
- B0 time: the four medium shards took 218.0 + 230.3 + 209.9 + 201.6 = 859.8 s, taken as one call doing the same work; this counts each shard's start-up latency once more than one call would, so it is on the high side; the nearest measured single call is the old agent's 520 s assess call at `high`.
- B0-$: n = round($5.74 / $2.45) = round(2.34) = 2; 2 × $2.45 = $4.90, and the self-ranking call is not measured, so B0-$ is budgeted at FULL's $5.74; 2 × 859.8 s = 1,719.6 s.
- Scoring: ($9.54 + $10.65 + $10.36) / 3 = $30.55 / 3 = $10.18.
- Sonnet control: $5.30 × $0.30 / $0.57 = $2.79.

### 1.2 Planning figures, 2026-10-02 (superseded for Tier A; kept because §2 to §4 and prereg `costs.per_run_usd` cite them)

Opus 5.5: $4 input, $5 cache write (5-minute), $0.20 cache read, $20 output per million tokens. Batch API: 50 % off every token.

| Scenario | USD per run |
|---|---|
| **Planning figure (FULL agent):** native PDF + canonical text in the cached prefix (78K), 150K research, 20 calls, 20K output | **$2.18** |
| Native PDF only (65K base) | $2.07 |
| Text-only ingestion (20K base) | $1.67 |
| Large PDF (100K base) | $2.38 |
| 25 calls | $2.36 |
| Heavy thinking (60K output) | **$3.24** (worst case used for the stop-loss) |

Per methodology condition (same base): FULL $2.18, B0 $0.63, B0-$ $2.18, A1 $1.02, A2 $1.52, A3 $2.00, A4e $1.91, A5 $1.02.

## 2. Runs implied by the methodology

At the §1.2 planning prices (2026-10-02), not redone; at the §1.1 measured prices every USD figure in §2 to §4 would rise, and only Tier A (§6) is recomputed.

k runs × items × conditions, from `research/methodology/README.md` §4, §4b and §5, the audit's reclassified tiers (ADR-004) and the robustness gate. The script prints two matrices: **PLANNED**, which assumes the commissioned sets exist, and **CURRENT ITEMS**, which uses only what is in the repo today.

Docs counted for the planned primary comparison: 3 S-dev + 2 S-heldout + 4 Blind (assumed size of the commissioned set) + 1 OOD + 2 sound controls = 12. **Seven of these twelve do not exist yet** (Blind, OOD, sound controls; ADR-004).

| # | Line item | Runs | Agent USD |
|---|---|---|---|
| 1 | Development iteration on S-dev (FULL) | 60 | 131 |
| 2 | S-dev pilot: FULL vs B0, k = 3, 3 docs (audit P1 item 10) | 18 | 25 |
| 3 | Primary comparison: FULL and B0, k = 5, 12 docs | 120 | 169 |
| 4 | Ablations: B0-$, A1, A2, A3, A4e, A5; k = 3; 6 held-out and Blind docs | 108 | 174 |
| 5 | v2 re-review: FULL, k = 3, 3 synthetic v2 docs × **2 variants** (fresh session; v1 review supplied as context; methodology §5) | 18 | 39 |
| 6 | S-heldout milestone checks: 2 further accesses × 2 docs × k = 3 | 12 | 26 |
| 7 | Overfitting probes: paraphrase and reorder of 3 S-dev docs, k = 3 | 18 | 39 |
| 8 | Robustness L1 (minimum gate subset): about 15 LLM-dependent scenarios × k ≈ 4 | 60 | 131 |
| 9 | L2 rehearsals, cassette recording, fresh-clone check, demo day (the SIT v2 artefact arrives here) | 25 | 55 |
| 10 | Real-dev: SIT sample v1, FULL, k = 3 (rubric-graded only, no key; methodology §1.1) | 3 | 7 |
| | **Agent subtotal (planned)** | **442** | **796** |

B-gen needs no model calls. H (human expert) is dropped per the audit's one-person plan (§4.6).

**Corrections made on verification (2026-10-02, `research/audit/verify_docs.md` item 2).** The previous version listed 433 runs / $777. Line 5 counted one v2 run per (doc, k), but methodology §5 requires a fresh-session run **and** a with-v1-context run (the copy-through rate in `metrics.md` §8 needs the second); and it counted an "SIT v2" doc that only arrives on demo day, has no key, and is therefore line 9 work. Line 10 makes the Real-dev SIT runs explicit (they were implicit before). Net: 433 → 442 runs, $777 → $796.

### 2a. At the current item count

Today the repo holds 9 items: 3 synthetic docs × 2 versions, 2 S-heldout docs and the SIT sample. With those only, the same formula gives:

| # | Line item (current items) | Runs | Agent USD |
|---|---|---|---|
| 3 | Primary: FULL and B0, k = 5, **5 docs** (3 S-dev + 2 S-heldout) | 50 | 70 |
| 4 | Ablations: 6 conditions, k = 3, **2 S-heldout docs** | 36 | 58 |
| 1, 2, 5-10 | Unchanged from the table above | 214 | 454 |
| | **Agent subtotal (current items)** | **300** | **582** |

So **142 of the 442 planned runs ($214 of agent spend) depend on docs that have to be commissioned first.** With only 5 keyed docs the primary comparison is underpowered by methodology §4b's own numbers (a 0.10 macro-F1 difference at σ_d = 0.10 needs 8 docs at 80 % power); report it as exploratory until the Blind set exists.

## 3. Grading, matching and judging

Recomputed per audit C25: the grader is the full pipeline in `research/grading/README.md` §6.1 (segment, 2 × Pass A, 2 × Pass B, a third sample 30 % of the time; key-aware mode excluded); the matcher and judges follow `research/methodology/metrics.md` §2.3 and §5 (listwise shortlist, 3 candidates × 3 pairwise samples per flaw, adjudication, G3 and citation judge). The owner made this candidate rule binding on 2026-10-02 (the shortlist bounds pairwise scoring; `docs/USER_DECISIONS.md` #10); the figures below are to be redone from measured costs after a pilot under that rule.

- **Graded reviews: 291** (lines 3-6 and 10, plus about 30 grader meta-validation grades for V1-V13). Current items: 149.
- **Matched runs: 414** (lines **1-8**; the matcher is on the critical path for the robustness thresholds, audit C31). Current items: 272. (The previous text said "lines 2-8"; the script has always included line 1.)

| Branch (ADR-003) | Grader | Matcher + judges | Instruments total |
|---|---|---|---|
| A: cross-family key (GPT-6.1 Sol rates, UNVERIFIED; no batch assumed) | $0.57 / review → $165 | $1.05 / run → $433 | **$598** |
| B1: Anthropic only; Sonnet 5.5 grader in batch; matcher and judges on a local open-weight model | $0.30 → $86 | $0 API | $86 |
| B2: as B1 with an Opus 5.5 grader (all-Opus extended to instruments) | $0.57 → $165 | $0 API | $165 |
| B3: as B2, and the local model fails validation (audit U8), so matcher and judges run on Opus 5.5 in batch | $165 | $1.05 / run → $433 | $598 |

## 4. Total with a 30 % margin

| Branch | Agent | Instruments | Subtotal | **× 1.3** | Current items only (× 1.3) |
|---|---|---|---|---|---|
| A (cross-family) | $796 | $598 | $1,394 | **$1,812** | $1,236 |
| B1 (Anthropic only, Sonnet grader, local matcher) | $796 | $86 | $882 | $1,147 | $814 |
| B2 (Anthropic only, Opus grader, local matcher) | $796 | $165 | $961 | $1,249 | $866 |
| B3 (Anthropic only, worst case) | $796 | $598 | $1,394 | $1,812 | $1,236 |

**Smaller figure to approve first: Tier A, $3,282** (§6, redone from measured runs on 2026-10-03; it was $650 at the planning prices; the minimum research-grade core from `research/audit/fresh_eyes.md` §2.3, scoped in `eval/EVAL_PLAN.md`). The full programme below stays the reference at the planning prices.

**Budget to approve for the full programme: $1,812 (call it $1,850).** It covers every judge branch, so it does not depend on ADR-003. If the user confirms branch B1 or B2, the expected spend falls to about $1,150-1,250. Until the Blind, OOD and sound-control docs are commissioned, the spend that can actually be incurred is the current-items column (at most $1,236). Anthropic's share of the agent spend alone is $1,035 with margin; set the Anthropic Console spend limit for this project's workspace to the Anthropic portion of the chosen branch (for example $1,035 + Claude instrument spend).

**Unbudgeted risk: effort switches.** `config/agent.yaml` (runbook §4.1) runs `plan` at `high`, `research` at `medium` and the later stages at `high`. A top-level `effort` change invalidates the messages-tier prompt cache (claude-api skill, prompt caching "Invalidation hierarchy"), and the PDF and canonical text sit in `messages`, so each switch rewrites the whole context at the cache-write price. Two switches per run cost about **+$1.20 per FULL run** (`cost_model.py`, "Sensitivity"; $3.38 instead of $2.18), about $500 over the planned matrix, which is more than the 30 % margin on the agent line. The figures above assume this is avoided (ADR-002: one effort level per conversation, or the per-message effort beta). Confirm on the laptop from `cache_creation_input_tokens` at stage boundaries before the pilot.
Measured on 2026-10-03 for the `claude_code` backend: the medium rehearsal wrote all 344,568 cached tokens and read none, so every call already pays the full write and the measured $5.74 includes it; the switch cost above applies to the `anthropic_api` backend only.

Not in USD, but budgeted: about 20-25 person-hours of human labelling (audit §4.6 one-person plan), about 4 hours of laptop sessions for MCP probing and cassette recording, and about 440 agent runs of wall-clock run time on the laptop (the earlier 8-10 minutes per run is withdrawn; Tier A's run time at the measured figures is in §6, and the full programme's is not redone).

## 5. Stop-loss and cut order

**Track spend** from the manifests (`usage.cost_usd`), summed into `eval/costs.csv` after every run, by line item.

**Checkpoints:**
- After the S-dev pilot (line 2): if the median FULL run costs more than **$3.24** (the heavy-thinking worst case), stop and re-plan before the primary matrix: measure `count_tokens`, check the cache hit ratio (`cache_read_input_tokens` / total input should exceed 0.7), and lower effort for research turns if needed.
- Re-based for the latency design (prereg `stop_rule.pilot_checkpoint`, deviations entry 11): the cost figure for the concurrent agent is **$8.21**, the measured cost of the same agent at `high` on every stage (§1.1), the heaviest configuration measured; the predicted with-research FULL run ($6.14) sits below it with $8.21 - $6.14 = $2.07 of room. The wall-time gate stays the 540 s demo slot. Prereg `costs.per_run_usd.heavy_case_FULL` still reads $3.24; it is not in `freeze.fill_before_freeze`, so moving it to $8.21 needs an entry in `eval/prereg_deviations.md`, while the `pilot_checkpoint` text already re-bases its cost figure on this page; the prereg is not changed here. The cache-hit test above does not apply to the `claude_code` backend, which read nothing back in the medium rehearsal.
- Before the primary matrix (line 3): if spend so far exceeds **40 %** of the approved budget, apply cuts 1-3 below before continuing.
- Hard stop at the approved budget: no further runs without a new decision recorded in `docs/DECISIONS.md`.

**Cut first** (least damage to the claims first; savings before margin, branch A rates, at the §1.2 planning prices and not redone):

| Order | Cut | Saves | Cost to the claims |
|---|---|---|---|
| 1 | Development iteration: re-run only the changed stages from checkpoints (`resume` from the last unchanged stage) and cap full dev runs at 40 | about $65 | None; dev runs carry no claims |
| 2 | Robustness L1: the 20-item minimum gate only (robustness §4.2), k = 3, on short fixtures (60 → 30 runs) | about $97 | P1 L1 scenarios move to "not run"; disclosed |
| 3 | Matcher: 2 pairwise samples (one call plus a swapped re-ask) instead of 3 (methodology §2.3 allows this) | about $103 | Slightly noisier matching; validated against human labels anyway |
| 4 | Drop A4e (already weak under ADR-002) and run A5 only at L0 plus k = 1 per doc | about $95 | Loses an effort ablation; A5 honesty check kept |
| 5 | Overfitting probes: reorder only, drop paraphrase | about $29 | Weaker memorisation check; disclosed |
| 6 | Last resort: primary comparison k = 5 → 3 (still meets the k ≥ 3 minimum) | about $145 | Wider CIs; MDE rises; stated in `prereg.yaml` |

Cuts 1-6 together save about $535 before margin (about $695 with margin).

**Never cut:** the single Blind evaluation; the S-heldout evaluations; FULL against B0 and B0-$ (cost-matched baselines; methodology L29); matcher validation against human labels; the verify stage in the agent; demo rehearsals.

## 6. Tier A: minimum research-grade core (approve this first)

Added 2026-10-02; redone 2026-10-03 from the measured runs (Basis note at the top).
Scope from `research/audit/fresh_eyes.md` §2.3 (keep column), run matrix and claims in `eval/EVAL_PLAN.md` §1, decision rules in `eval/prereg.yaml`.
Per-run prices are the §1.1 figures: FULL $5.74 (measured), A5 $5.74 (measured), B0 $2.45 (derived), B0-$ $5.74 (matched to FULL); scoring $10.18 per matched run (measured mean), Opus grader $5.30 per review (measured), Sonnet control grader $2.79 per review (derived).
The 132 runs are 84 FULL, 9 A5, 24 B0 and 15 B0-$ (`eval/EVAL_PLAN.md` §1.2); Tier A has no A4b run, so the `high` cost enters only the sensitivity rows, the pilot checkpoint (§5) and Tier B line B-1.
The full programme in §2-§5 is unchanged and remains the reference at the planning prices; Tier A is a subset of it, not an addition.

| # | Line item (Tier A) | Runs | Agent USD |
|---|---|---|---|
| A-1 | Development iteration, FULL, resume from checkpoints (support; no claims) | 16 | 91.84 |
| A-2 | S-dev pilot before the freeze: FULL and B0, k = 3, 3 docs | 18 | 73.71 |
| A-3 | Frozen agent on S-dev: FULL, B0, B0-$, A5, k = 3, 3 docs | 36 | 177.03 |
| A-4 | Frozen agent on S-heldout (access 1 of 3): FULL, B0, B0-$, k = 3, 2 docs | 18 | 83.58 |
| A-5 | v2 re-review: FULL, fresh and with v1 context, k = 3, 3 v2 docs | 18 | 103.32 |
| A-6 | Real-dev: SIT sample v1, FULL, k = 3 (scored against the owner's key) | 3 | 17.22 |
| A-7 | Owner-written SIT v2 fixture, FULL delta mode, k = 3 | 3 | 17.22 |
| A-8 | Robustness minimum gate, live-LLM part (about 6 scenarios × 2) | 12 | 68.88 |
| A-9 | Rehearsals, cassette recording, fresh-clone check | 8 | 45.92 |
| | **Agent subtotal (Tier A)** (96 scored for $472.08 + 36 support for $206.64) | **132** | **678.72** |

By condition: FULL 84 × $5.74 = $482.16; A5 9 × $5.74 = $51.66; B0 24 × $2.45 = $58.80; B0-$ 15 × $5.74 = $86.10; sum $678.72.
Per line: a FULL, A5 or B0-$ run is $5.74 and a B0 run $2.45, so A-2 is 9 × $5.74 + 9 × $2.45 = $51.66 + $22.05 = $73.71, A-3 is 27 × $5.74 + 9 × $2.45 = $154.98 + $22.05 = $177.03, A-4 is 12 × $5.74 + 6 × $2.45 = $68.88 + $14.70 = $83.58, and every other line is its run count × $5.74.

| Instruments (Tier A) | Volume | USD |
|---|---|---|
| Scoring: matcher, adjudicator, G3 and citation judges (`sit-eval score`, pre-registered setup) | 101 matched runs (96 scored + 5 B-gen) × $10.18 | 1,028.18 |
| Opus 5.5 grader, effort `high` (`docs/USER_DECISIONS.md` #2) | 101 reviews × $5.30 | 535.30 |
| Sonnet 5.5 same-family control grader | 101 reviews × $2.79 | 281.79 |
| Second-provider grader | Not budgeted: Anthropic only for now (`docs/USER_DECISIONS.md` #23) | 0 |

| Tier A total | Subtotal | **× 1.3** |
|---|---|---|
| Agent | $678.72 | $882.34 |
| Scoring | $1,028.18 | $1,336.63 |
| Grading ($535.30 + $281.79) | $817.09 | $1,062.22 |
| **Total** | **$2,523.99** | **$3,281.19** |
| Sensitivity: FULL with research at the predicted $6.14 (84 runs × $0.40 = +$33.60) | $2,557.59 | $3,324.87 |
| Sensitivity: scoring at the highest measured $10.65 (101 × $0.47 = +$47.47) | $2,571.46 | $3,342.90 |
| Sensitivity: every FULL-shaped run (84 FULL + 9 A5 = 93) at the `high` cost $8.21 (93 × $2.47 = +$229.71) | $2,753.70 | $3,579.81 |
| Without the Sonnet control grader (-$281.79) | $2,242.20 | $2,914.86 |

The margin is the 30 % this page already uses: $2,523.99 × 1.3 = $3,281.19 ($882.34 + $1,336.63 + $1,062.22).
Scoring and grading are 73 % of the total before margin (($1,028.18 + $817.09) / $2,523.99 = $1,845.27 / $2,523.99 = 0.731), so the instruments, not the agent, set this budget.

**Against the previous figures (2026-10-02, $564 Anthropic only with margin, approval $650):**
agent $240.12 → $678.72, because FULL moved from $2.18 to $5.74 on measured prices (the CLI writes the whole context at $8 per million on every call and reads nothing back) and the redesign's four shards plus refine write 148,957 output tokens against the 20,000 planned;
scoring $106.05 → $1,028.18, because the pre-registered setup makes 93 to 98 judge calls per run at about $0.10 each against the planned $1.05 per run;
grading $87.87 ($57.57 + $30.30) → $817.09, because one Opus grading is 4 calls at $5.30 against the planned $0.57;
the second-provider branch is dropped (#23);
total with margin $564 → $3,281.19.

Wall time of the agent runs (run time, at the §1.1 per-run times):

| Condition | Runs × time | Run time |
|---|---|---|
| FULL | 84 × 382.3 s | 32,113.2 s |
| A5 | 9 × 382.3 s | 3,440.7 s |
| B0 (derived time) | 24 × 859.8 s | 20,635.2 s |
| B0-$ (derived time, n = 2 one after another) | 15 × 1,719.6 s | 25,794.0 s |
| **Total** | 132 runs | **81,983.1 s = 22.8 h** |

| Runs in parallel | Laptop wall time |
|---|---|
| 1 | 81,983.1 s / 3,600 = 22.8 h |
| 2 | 22.8 h / 2 = 11.4 h |
| 3 | 22.8 h / 3 = 7.6 h |

Prereg `runs_per_item.scheduling` allows one FULL run at a time until 12 concurrent CLI sessions are measured (a FULL run holds up to 6), so the 2 and 3 rows are not yet allowed for the FULL-shaped runs.
With research at the predicted 389.3 to 438.3 s, the 84 FULL runs add 84 × 7 s = 588 s to 84 × 56 s = 4,704 s, so the total is 22.9 to 24.1 h at one run at a time.
Instruments are not in these hours: at the old run's measured 245.6 s per scoring and 549.3 s per Opus grading (`eval/EVAL_PLAN.md`, "Run time"), 101 scorings take 6.9 h and 101 gradings 15.4 h, one at a time; the new runs' instrument times were not measured.
Mac load was about 5 in the medium rehearsal and 5.85 to 9.41 in the `high` one, which may have slowed both.

The §5 pilot checkpoint applies with its re-based figure: if the pilot's median FULL run costs more than $8.21, or its p95 wall time exceeds 540 s, stop and re-plan before the freeze.
Not in USD, unchanged: about 18 person-hours for one rater (`eval/human_labelling_protocol.md` §1; `eval/EVAL_PLAN.md` §1.3).

| Tier | Runs | USD with margin | Status |
|---|---|---|---|
| A (core; must finish before submission) | 132 | $3,281.19 (approve $3,282) | For the owner's approval below |
| B (if time; `eval/EVAL_PLAN.md` §2: A4b effort sweep, A4 Sonnet-as-agent, human-planted set, sound control, AI-platform rehearsal doc) | 63 | $278-323 at the planning prices, not redone; line B-1's 9 A4b-high runs alone are 9 × $8.21 = $73.89 of agent spend before margin, and A4b-xhigh is not measured | Approve after Tier A is on track |
| Full programme (§2-§4, reference) | 442 | $1,147-1,812 at the planning prices, not redone | Needs the commissioned Blind, OOD and sound-control docs |

### Owner approval

Figure to approve: **$3,282** for Tier A (agent, scoring and grading with the 30 % margin, Anthropic only; $3,281.19 rounded up to the next dollar).
Hard stop at the approved figure without a new decision in `docs/DECISIONS.md` (prereg `stop_rule`).

Approved by: ____________________ Date: ____________
