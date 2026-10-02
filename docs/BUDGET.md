# Project budget

Date: 2026-10-02. Resolves audit P1 item 17 and M12 (`research/audit/research_audit.md`). Every figure comes from `research/models/cost_model.py` (run `python3 research/models/cost_model.py`; the "ALL-OPUS", "Budget matrix" and "Sensitivity" sections print all of them). Reconciled line by line against the script output on 2026-10-02 (`research/audit/verify_docs.md` item 2). Claude prices are from the `claude-api` skill (cached 2026-09-25); non-Claude prices are **UNVERIFIED**. The token base is **UNVERIFIED** until `messages.count_tokens` is run on the SIT PDF on the laptop (audit U3); re-run the script with the measured values and update this page.

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

**Smaller figure to approve first: Tier A, $650** (§6; the minimum research-grade core from `research/audit/fresh_eyes.md` §2.3, scoped in `eval/EVAL_PLAN.md`). The full programme below stays the reference.

**Budget to approve for the full programme: $1,812 (call it $1,850).** It covers every judge branch, so it does not depend on ADR-003. If the user confirms branch B1 or B2, the expected spend falls to about $1,150-1,250. Until the Blind, OOD and sound-control docs are commissioned, the spend that can actually be incurred is the current-items column (at most $1,236). Anthropic's share of the agent spend alone is $1,035 with margin; set the Anthropic Console spend limit for this project's workspace to the Anthropic portion of the chosen branch (for example $1,035 + Claude instrument spend).

**Unbudgeted risk: effort switches.** `config/agent.yaml` (runbook §4.1) runs `plan` at `high`, `research` at `medium` and the later stages at `high`. A top-level `effort` change invalidates the messages-tier prompt cache (claude-api skill, prompt caching "Invalidation hierarchy"), and the PDF and canonical text sit in `messages`, so each switch rewrites the whole context at the cache-write price. Two switches per run cost about **+$1.20 per FULL run** (`cost_model.py`, "Sensitivity"; $3.38 instead of $2.18), about $500 over the planned matrix, which is more than the 30 % margin on the agent line. The figures above assume this is avoided (ADR-002: one effort level per conversation, or the per-message effort beta). Confirm on the laptop from `cache_creation_input_tokens` at stage boundaries before the pilot.

Not in USD, but budgeted: about 20-25 person-hours of human labelling (audit §4.6 one-person plan), about 4 hours of laptop sessions for MCP probing and cassette recording, and about 440 agent runs × 8-10 minutes ≈ 60-75 hours of wall-clock run time on the laptop (2-3 runs can run in parallel within rate limits; interleave conditions in time).

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

## 6. Tier A: minimum research-grade core (approve this first)

Added 2026-10-02. Scope from `research/audit/fresh_eyes.md` §2.3 (keep column), run matrix and claims in `eval/EVAL_PLAN.md` §1, decision rules in `eval/prereg.yaml`. Per-run prices are the §1 per-condition figures (FULL $2.18, B0 $0.63, B0-$ $2.18, A5 $1.02); instrument rates are §3's (matcher and judges $1.05 per matched run, Opus 5.5 grader $0.57 per review in batch, Sonnet 5.5 control $0.30). The full programme in §2-§5 is unchanged and remains the reference; Tier A is a subset of it, not an addition.

| # | Line item (Tier A) | Runs | Agent USD |
|---|---|---|---|
| A-1 | Development iteration, FULL, resume from checkpoints (support; no claims) | 16 | 34.88 |
| A-2 | S-dev pilot before the freeze: FULL and B0, k = 3, 3 docs | 18 | 25.29 |
| A-3 | Frozen agent on S-dev: FULL, B0, B0-$, A5, k = 3, 3 docs | 36 | 54.09 |
| A-4 | Frozen agent on S-heldout (access 1 of 3): FULL, B0, B0-$, k = 3, 2 docs | 18 | 29.94 |
| A-5 | v2 re-review: FULL, fresh and with v1 context, k = 3, 3 v2 docs | 18 | 39.24 |
| A-6 | Real-dev: SIT sample v1, FULL, k = 3 (scored against the owner's key) | 3 | 6.54 |
| A-7 | Owner-written SIT v2 fixture, FULL delta mode, k = 3 | 3 | 6.54 |
| A-8 | Robustness minimum gate, live-LLM part (about 6 scenarios × 2) | 12 | 26.16 |
| A-9 | Rehearsals, cassette recording, fresh-clone check | 8 | 17.44 |
| | **Agent subtotal (Tier A)** (96 scored + 36 support) | **132** | **240.12** |

| Instruments (Tier A) | Volume | USD |
|---|---|---|
| Matcher, adjudicator, G3 and citation judges (Opus 5.5 batch, or the second provider) | 101 matched runs | 106.05 |
| Opus 5.5 grader, effort `high` (`docs/USER_DECISIONS.md` #2) | 101 reviews | 57.57 |
| Sonnet 5.5 same-family control grader | 101 reviews | 30.30 |
| Second-provider grader, only if a key exists (price UNVERIFIED) | 101 reviews | 57.57 |

| Tier A total | Subtotal | **× 1.3** |
|---|---|---|
| Anthropic only | $434 | **$564** |
| With a second-provider grader | $492 | **$639** |
| Sensitivity: every FULL-shaped run (99) at the $3.24 heavy-thinking cost | $539-597 | $701-776 |

**Tier A approval figure: $650.** It covers both grader branches at the planning cost. The §5 pilot checkpoint applies unchanged: if the pilot's median FULL run costs more than $3.24, stop and re-plan before the freeze. Hard stop at $650 without a new decision in `docs/DECISIONS.md`. Not in USD: about 18 person-hours for one rater (`eval/human_labelling_protocol.md` §1) and about 7-11 hours of laptop wall time (132 runs × 8-10 min, 2-3 in parallel).

| Tier | Runs | USD with margin | Status |
|---|---|---|---|
| A (core; must finish before submission) | 132 | $564-639 (approve $650) | Approve now |
| B (if time; `eval/EVAL_PLAN.md` §2: A4b effort sweep, A4 Sonnet-as-agent, human-planted set, sound control, AI-platform rehearsal doc) | 63 | $278-323 | Approve after Tier A is on track |
| A + B | 195 | $842-962 | |
| Full programme (§2-§4, reference) | 442 | $1,147-1,812 | Needs the commissioned Blind, OOD and sound-control docs |
