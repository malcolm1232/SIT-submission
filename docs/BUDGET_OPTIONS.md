# Tier A budget options: three scoped evaluation plans

Date: 2026-10-03.
Basis: the measured per-run figures of `docs/BUDGET.md` §1.1 and the Tier A matrix of `eval/EVAL_PLAN.md` §1.2; every figure is the CLI's estimate, not a billed amount, measured on one document.
The owner must approve one figure; the pre-registered plan costs $3,282, and the question is what each cheaper plan gives up.
No code and no model call were made for this note; the only new arithmetic is shown inline.

## 1. Unit prices used

| Unit | USD | Basis |
|---|---|---|
| FULL, A5 or B0-$ agent run | 5.74 | measured (`rehearsal_concurrent_1`); B0-$ matched to FULL by definition |
| B0 agent run | 2.45 | derived, not measured |
| Scoring, pre-registered setup (shortlist, adaptive 3 pairwise samples, adjudication, G3 premise and citation judges) | 10.18 | mean of three measured scorings |
| Scoring with the grounding judges off | 3.70 | derived: 10.18 minus 18 findings × ($0.33 premise + $0.03 citation) = 10.18 - 6.48; the per-kind prices are `harness/README.md` estimates, not a measured judges-off run |
| Opus 5.5 grader, 2 samples of Pass A and Pass B | 5.30 | measured (4 calls) |
| Sonnet 5.5 control grader | 2.79 | derived from the planning ratio 0.30 / 0.57 |

The scoring cost is the only instrument that carries a claim: recall, precision, CDR and the v2 metrics all come from the matcher and adjudicator (prereg `matcher.only_source_of_recall`), while the grader is supporting only (prereg `grader.role_in_claims`).
That is why every cheaper plan cuts grading first and the matcher last.

## 2. The three plans

| Line | Plan A, as pre-registered | Plan B, same runs, cheaper instruments | Plan C, primary comparison only |
|---|---|---|---|
| A-1 dev iteration (support) | 16 FULL | 8 FULL, resume from checkpoints | 8 FULL |
| A-2 pilot, 3 S-dev | FULL, B0 × 3 = 18 | 18 | FULL, B0 × 2 = 12 |
| A-3 frozen, 3 S-dev | FULL, B0, B0-$, A5 × 3 = 36 | 36 | FULL, B0 × 3 and A5 × 1 = 21 |
| A-4 frozen, 2 S-heldout | FULL, B0, B0-$ × 3 = 18 | 18 | FULL, B0 × 3 = 12 |
| A-5 v2, fresh and with context | FULL × 2 × 3 = 18 | 18 | FULL × 2 × 1 = 6 |
| A-6 SIT v1 | FULL × 3 | 3 | 3 |
| A-7 SIT v2 fixture | FULL × 3 | 3 | dropped |
| A-8 robustness gate (support) | 12 | 12 | 6 |
| A-9 rehearsals (support) | 8 | 4 | 4 |
| Agent runs | 132 | 120 | 72 |
| Scored runs; matched runs (with 5 B-gen) | 96; 101 | 96; 101 | 54; 59 |
| Matcher | Opus, prereg setup, judges on | Opus, prereg setup, judges off | Opus, prereg setup, judges off |
| Graded reviews, Opus 2 samples | 101 | 33 (5 smoke, 5 frozen sample, 20 V1/V4/V10, 3 calibration) | 10 (5 smoke, 5 frozen sample) |
| Sonnet control grader | 101 | dropped | dropped |

Agent arithmetic: Plan B is $678.72 - 12 × $5.74 = $609.84; Plan C is A-1 $45.92 + A-2 (6 × $5.74 + 6 × $2.45 = $49.14) + A-3 (9 × $5.74 + 9 × $2.45 + 3 × $5.74 = $90.93) + A-4 (6 × $5.74 + 6 × $2.45 = $49.14) + A-5 $34.44 + A-6 $17.22 + A-8 $34.44 + A-9 $22.96 = $344.19.
Scoring arithmetic: Plan A 101 × $10.18 = $1,028.18; Plan B 101 × $3.70 = $373.70; Plan C 59 × $3.70 = $218.30.
Grading arithmetic: Plan A 101 × ($5.30 + $2.79) = $817.09; Plan B 33 × $5.30 = $174.90; Plan C 10 × $5.30 = $53.00.

| USD | Plan A | Plan B | Plan C |
|---|---|---|---|
| Agent, before and after the 30 % margin | 678.72 / 882.34 | 609.84 / 792.79 | 344.19 / 447.45 |
| Scoring | 1,028.18 / 1,336.63 | 373.70 / 485.81 | 218.30 / 283.79 |
| Grading | 817.09 / 1,062.22 | 174.90 / 227.37 | 53.00 / 68.90 |
| Total | 2,523.99 / 3,281.19 | 1,158.44 / 1,505.97 | 615.49 / 800.14 |
| Figure to approve | 3,282 | 1,506 | 801 |
| Priced add-back | none | judges on for the 30 keyed FULL and B0 runs, 30 × $6.48 = $194.40, $252.72 with margin, total $1,758.69: keeps H5 tested | B0-$ × 3 on 5 docs, 15 × ($5.74 + $3.70) = $141.60, $184.08 with margin, total $984.22: keeps H2 |

Wall time of the agent runs at the measured and derived per-run times (FULL and A5 382.3 s, B0 859.8 s, B0-$ 1,719.6 s):

| Hours | Plan A | Plan B | Plan C |
|---|---|---|---|
| One run at a time | 81,983.1 s = 22.8 h | 72 × 382.3 + 9 × 382.3 + 24 × 859.8 + 15 × 1,719.6 = 77,395.5 s = 21.5 h | 48 × 382.3 + 3 × 382.3 + 21 × 859.8 = 37,553.1 s = 10.4 h |
| Two in parallel | 11.4 h | 10.7 h | 5.2 h |
| Instruments, one at a time, at the old run's 245.6 s per scoring and 549.3 s per grading | 6.9 h + 15.4 h | at most 6.9 h (judges off is untimed) + 5.0 h | at most 4.0 h + 1.5 h |

Prereg `runs_per_item.scheduling` allows one FULL run at a time until 12 concurrent CLI sessions are measured, so the two-in-parallel row is not yet allowed for the FULL-shaped runs.

## 3. What each plan can detect, and what it loses

The pre-registered power argument (prereg `minimum_detectable_effect`, methodology `metrics.md` §12.5 and README §4b item 6) is Connor's paired-proportion formula over the 70 keyed flaws with DEFF = 1 + 13 ρ, and a document-level formula over 5 documents with σ_d.
The measured between-run spread of one condition is unknown: the three runs in `docs/live_runs/QUALITY_COMPARISON.md` are three different agent configurations on one document (strict recall 0.786, 0.929, 0.929), and the two concurrent runs were identical on recall, so no between-run SD exists yet.
The figures below therefore use the methodology's assumed values, ρ = 0.10, ψ = 0.2 to 0.3 and σ_d = 0.10 to 0.15, which it marks UNVERIFIED; the pilot replaces them before the freeze.
At those values the minimum detectable difference in strict recall between FULL and B0 on the 5 keyed documents is 0.22 (ψ = 0.2) to 0.27 (ψ = 0.3), and 0.25 to 0.30 under the Holm-adjusted α of 0.025; at the document level it is 0.13 (σ_d = 0.10) to 0.19 (σ_d = 0.15); on the 2 held-out documents alone it is 0.33 to 0.40.
k enters only through the document-level σ_d, because the per-document mean over k runs carries the between-run variance divided by k; the flaw-level figures do not move with k, so every plan that keeps k = 3 on the FULL and B0 cells keeps the same MDE, and all three do.
The methodology gives no power row for severity-weighted recall; it is a weighted proportion whose weight sits on the critical flaws, so its effective flaw count is below 70 and its MDE is above the strict figure; every plan reports it with its bootstrap CI as a magnitude, never as a tested difference, and this note states no number for it.
The minimum effect of interest, 0.10, is below the MDE in every plan, as the prereg already says; a null is "no evidence at this n" in all three.

| Consequence | Plan A | Plan B | Plan C |
|---|---|---|---|
| H1 FULL vs B0 strict recall, 70 flaws, k = 3 | tested, MDE 0.22 to 0.27 | same | same |
| H2 FULL vs B0-$ (cost-matched) | tested | tested | not run; the MR §0(d) cost-matched criterion is unmet and CL3 is not made |
| H3, H4 precision and CDR guardrails | tested | tested | tested |
| H5 hallucinated-finding rate | tested | descriptive: HFR keeps only its G1 clause (every quote fails the code check), a lower bound, plus the adjudicator's HALLUCINATED count; citation precision is null | same as B |
| H6 A5 gate | 0 of 9, Wilson upper bound 0.30 | same | 0 of 3, Wilson upper bound 3.84 / (3 + 3.84) = 0.56 |
| H7 v2 metrics | exploratory, k = 3, 3 docs | same | counts only, k = 1, no within-document CI; claimed-fix accuracy not computed (A-7 dropped) |
| H8 DiD, H9 SIT | reported | reported | reported |
| H10 matcher κ on 100 pairs, B-gen floor | gate | gate | gate, but the pairs come from a k = 2 pilot (12 runs, the same 3 documents) |
| Grader validity tier | smoke plus 5-sample, V1/V4/V10, per-condition grader table, control agreement | smoke plus 5-sample, V1/V4/V10; no per-condition grader table, no control | smoke plus 5-sample only; V-tests not run |
| Pilot estimates (ρ, σ_d, ψ, between-run SD) | from 18 runs at k = 3 | same | from 12 runs at k = 2, a crude between-run SD |
| Bootstrap CI per scored item | every cell | every cell | FULL, B0 and SIT cells; not the A5 and v2 cells (k = 1 leaves no inner level) |
| Submission can still say | every claim CL1 to CL12 at the pre-registered strength | CL1 to CL12 except CL5, which becomes descriptive, and the grader numbers cover only the validation set | CL2, CL4, CL8, CL9, CL11, CL12 at the pre-registered strength; CL3 not made; CL5 descriptive; CL6 at 0 of 3; CL7 counts; CL10 grader part at smoke tier |

## 4. The levers, each with its saving and its cost in evidence

Savings are on the Plan A base before the margin; "deviation" means the lever changes a pre-registered semantic and needs an `eval/prereg_deviations.md` entry before the freeze.

| Lever | Saves | Cost in evidence | Prereg | Used in |
|---|---|---|---|---|
| Fewer runs per item, k = 3 to 2 | about a third of the scored agent and scoring lines, about $560 | below the methodology minimum k = 3; between-run SD from two runs; every CI widens | deviation (`runs_per_item.k`) | none; Plan C cuts cells instead |
| Drop B0-$ | 15 × ($5.74 + $10.18 + $8.09) = $360.15 | H2 not run; BUDGET §5 lists B0-$ under "never cut" | deviation (`conditions.tier_A`, H2) | C, with the add-back |
| A5 at k = 1 per document | 6 × $24.01 = $144.06 | H6 bound 0.30 to 0.56 | deviation (H6 decision rule, `runs_per_item`) | C |
| Score every run, grade a subset | Plan A to B: 68 × $5.30 = $360.40 | sound: no claim rests on a grader score; loses per-condition grader tables | plan change only, if V1/V4/V10, the 5 smoke and the 5 sample reviews stay | B, C |
| Grade every run, score a subset | would save about $10 per unscored run | not sound: recall exists only through the matcher, so an unscored run contributes nothing to any hypothesis | not applicable | none |
| Grounding judges off | 101 × $6.48 = $654.48 | H5 descriptive, citation precision null; G1 and G2 stay (code) | deviation (`grounding.G3_premise_judge`, citation support judge, H5) | B, C |
| Two pairwise samples instead of the adaptive third | well under $0.50 per run (pair calls are $0.03 and the third is asked only on disagreement) | changes the median-of-three rule for a negligible saving | deviation (`matcher.pairwise_scoring`) | none |
| Cheaper matcher model with an Opus calibration subset | about 47 % of the matcher share, roughly $4.80 per run at the planning ratio, less the subset | H10 would validate the cheaper matcher against the 100 owner pairs, so it is sound in principle, but it adds a second matcher to validate and the same-family disclosure stays | deviation (`matcher.model` branch_B) | none; the next lever if Plan B must shrink without losing H5 |
| Drop the Sonnet control grader | $281.79 | loses the same-family agreement figure | deviation (`grader.control`) | B, C |
| Message Batches at half price | $0 | the `claude_code` backend makes synchronous `claude -p` calls and Batches is not implemented (deviations entry 7); it needs the `anthropic_api` backend and a Console key, which the owner declined (`docs/USER_DECISIONS.md` #6) | not available | none |
| Trim support runs (dev 16 to 8 by resuming from checkpoints, rehearsals 8 to 4) | 12 × $5.74 = $68.88 | none; BUDGET §5 cut 1 | none | B, C |

Harness changes: Plan A needs none; Plans B and C need `sit-eval score --no-grounding-judges` on every run or the `config/eval.yaml` default flipped, the grader run list in `eval/EVAL_PLAN.md` §1.2 cut to the validation reviews, and the run schedule written for the smaller matrix; Plan C also leaves `costs.b0_dollar_matching_n` unfilled.
Prereg changes: Plan A needs only the pending `heavy_case_FULL` re-base to $8.21; Plan B needs entries for the grounding judges, H5 and the control grader; Plan C needs those plus entries for B0-$ and H2, the H6 rule, k = 1 on the A5 and v2 cells, the k = 2 pilot, A-7 and the grader meta-validation.
Owner hours: unchanged in A and B at about 18 h; Plan C drops T8 (the SIT v2 fixture, 3 h) and T5b.

## 5. What the figures mean in subscription terms

Every figure is the CLI's estimate at $8 per million cache-write tokens, $0.20 per million cache reads and $20 per million output tokens; nothing is billed in dollars, because the agent and both instruments run through the Claude Code login (`docs/USER_DECISIONS.md` #6, ADR-010).
What the owner actually spends is Opus throughput inside his subscription's usage windows, so the binding constraint is how many hours of Opus the plan needs per week, not the dollar figure, and this note does not claim to know his plan's limit.
From the measured per-run counts (FULL 344,584 input and 148,957 output tokens; B0 43,073 and 105,447 derived; B0-$ twice B0), the agent runs alone are: Plan A 93 FULL-shaped + 24 B0 + 15 B0-$ = 34.4 M input and 19.5 M output tokens; Plan B 81 + 24 + 15 = 30.2 M and 17.8 M; Plan C 51 + 21 = 18.5 M and 9.8 M.
The instruments' token counts are not recorded in the files this note read; converting their cost with the agent's measured split (48 % cache write, 52 % output) gives about 111 M input and 48 M output tokens for Plan A, 33 M and 14 M for Plan B, 16 M and 7 M for Plan C, and that conversion is an assumption, since judge calls write far less than the agent does.
If the spend lands on the $250 cloud-credit accounts of `docs/USER_DECISIONS.md` #8 rather than on a subscription, even Plan C exceeds one account at the CLI's rates, so the owner should say which pool pays before approving a figure.

## 6. Recommendation

Approve Plan B at $1,506, and $1,759 if the owner will also keep H5 tested.
Plan B runs every pre-registered cell at k = 3, so the primary and guardrail tests keep the power the prereg promised and nothing in the run matrix is lost; what it cuts is evidence that by the prereg's own words carries no claim (the grader beyond its validation set and the same-family control) and one judge whose loss turns a guardrail into a described lower bound.
Plan A buys the per-condition grader tables, the control grader and the premise judge for $1,776 more, which is a high price for supporting evidence; Plan C saves a further $705 by not running a primary hypothesis and by breaking the k = 3 minimum on two cells, which is the kind of cut the submission would have to explain.
Figures to approve: Plan A $3,282, Plan B $1,506 (or $1,759 with H5), Plan C $801 (or $985 with B0-$).
