# Project budget

Date: 2026-10-02. Resolves audit P1 item 17 and M12 (`research/audit/research_audit.md`). Every figure comes from `research/models/cost_model.py` (run `python3 research/models/cost_model.py`; the "ALL-OPUS" section prints all of them). Claude prices are from the `claude-api` skill (cached 2026-09-25); non-Claude prices are **UNVERIFIED**. The token base is **UNVERIFIED** until `messages.count_tokens` is run on the SIT PDF on the laptop (audit U3); re-run the script with the measured values and update this page.

## 1. Per-run cost, all Opus 5.5 (ADR-002)

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

k runs × items × conditions, from `research/methodology/README.md` §4 and §4b, the audit's reclassified tiers (ADR-004) and the robustness gate. Docs counted for the primary comparison: 3 S-dev + 2 S-heldout + 4 Blind (assumed size of the commissioned set) + 1 OOD + 2 sound controls = 12.

| # | Line item | Runs | Agent USD |
|---|---|---|---|
| 1 | Development iteration on S-dev (FULL) | 60 | 131 |
| 2 | S-dev pilot: FULL vs B0, k = 3, 3 docs (audit P1 item 10) | 18 | 25 |
| 3 | Primary comparison: FULL and B0, k = 5, 12 docs | 120 | 169 |
| 4 | Ablations: B0-$, A1, A2, A3, A4e, A5; k = 3; 6 held-out and Blind docs | 108 | 174 |
| 5 | v2 re-review: FULL, k = 3, 3 synthetic v2 + SIT v2 | 12 | 26 |
| 6 | S-heldout milestone checks: 2 further accesses × 2 docs × k = 3 | 12 | 26 |
| 7 | Overfitting probes: paraphrase and reorder of 3 S-dev docs, k = 3 | 18 | 39 |
| 8 | Robustness L1 (minimum gate subset): about 15 LLM-dependent scenarios × k ≈ 4 | 60 | 131 |
| 9 | L2 rehearsals, cassette recording, fresh-clone check, demo day | 25 | 55 |
| | **Agent subtotal** | **433** | **777** |

B-gen needs no model calls. H (human expert) is dropped per the audit's one-person plan (§4.6).

## 3. Grading, matching and judging

Recomputed per audit C25: the grader is the full pipeline in `research/grading/README.md` §6.1 (segment, 2 × Pass A, 2 × Pass B, a third sample 30 % of the time; key-aware mode excluded); the matcher and judges follow `research/methodology/metrics.md` §2.3 and §5 (listwise shortlist, 3 candidates × 3 pairwise samples per flaw, adjudication, G3 and citation judge).

- **Graded reviews: 282** (lines 3-6, plus about 30 grader meta-validation grades for V1-V13).
- **Matched runs: 408** (lines 2-8; the matcher is on the critical path for the robustness thresholds, audit C31).

| Branch (ADR-003) | Grader | Matcher + judges | Instruments total |
|---|---|---|---|
| A: cross-family key (GPT-6.1 Sol rates, UNVERIFIED; no batch assumed) | $0.57 / review → $160 | $1.05 / run → $427 | **$587** |
| B1: Anthropic only; Sonnet 5.5 grader in batch; matcher and judges on a local open-weight model | $0.30 → $83 | $0 API | $83 |
| B2: as B1 with an Opus 5.5 grader (all-Opus extended to instruments) | $0.57 → $160 | $0 API | $160 |
| B3: as B2, and the local model fails validation (audit U8), so matcher and judges run on Opus 5.5 in batch | $160 | $1.05 / run → $427 | $587 |

## 4. Total with a 30 % margin

| Branch | Agent | Instruments | Subtotal | **× 1.3** |
|---|---|---|---|---|
| A (cross-family) | $777 | $587 | $1,363 | **$1,772** |
| B1 (Anthropic only, Sonnet grader, local matcher) | $777 | $83 | $860 | $1,118 |
| B2 (Anthropic only, Opus grader, local matcher) | $777 | $160 | $936 | $1,217 |
| B3 (Anthropic only, worst case) | $777 | $587 | $1,363 | $1,772 |

**Budget to approve: $1,772 (call it $1,800).** It covers every judge branch, so it does not depend on ADR-003. If the user confirms branch B1 or B2, the expected spend falls to about $1,100-1,200. Anthropic's share of the agent spend alone is $1,010 with margin; set the Anthropic Console spend limit for this project's workspace to the Anthropic portion of the chosen branch (for example $1,010 + Claude instrument spend).

Not in USD, but budgeted: about 20-25 person-hours of human labelling (audit §4.6 one-person plan), about 4 hours of laptop sessions for MCP probing and cassette recording, and about 430 agent runs × 8-10 minutes ≈ 60-70 hours of wall-clock run time on the laptop (2-3 runs can run in parallel within rate limits; interleave conditions in time).

## 5. Stop-loss and cut order

**Track spend** from the manifests (`usage.cost_usd`), summed into `eval/costs.csv` after every run, by line item.

**Checkpoints:**
- After the S-dev pilot (line 2): if the median FULL run costs more than **$3.24** (the heavy-thinking worst case), stop and re-plan before the primary matrix: measure `count_tokens`, check the cache hit ratio (`cache_read_input_tokens` / total input should exceed 0.7), and lower effort for research turns if needed.
- Before the primary matrix (line 3): if spend so far exceeds **40 %** of the approved budget, apply cuts 1-3 below before continuing.
- Hard stop at the approved budget: no further runs without a new decision recorded in `docs/DECISIONS.md`.

**Cut first** (least damage to the claims first; savings before margin, branch A rates):

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
