# Plan D: the full agent against a single call on eight documents (5 Oct 2026)

This file reports the plan D evaluation of the design-review agent: what was run, what it scored, and what the numbers do and do not allow anyone to say.
Every score here is exploratory: the answer keys are unsigned and the pre-registration is not frozen, so nothing below is a confirmatory result.
Every number names its source: a row of `docs/live_runs/plan_d/RUNS.md`, `RUNS_B0.md` or `GRADES.md`, a field of a run's `eval_d/scores.json`, or the aggregate written by `sit-eval aggregate`.
The run folders are not committed; they are in `~/Desktop/SIT-wt/plan-d-runs/runs/<run-id>/` (FULL) and `~/Desktop/SIT-wt/plan-d-b0/runs/<run-id>/` (B0), and every `scores.json` path below is relative to the run folder.
Times are Singapore time (UTC+8) unless marked Z.

## 1. What was run and why

Plan D is decision #46 of `docs/USER_DECISIONS.md` and entry 13 of `eval/prereg_deviations.md`: Malcolm's word of 4 Oct 2026 22:40, "less runs, but more variants document wise", all at effort medium.
Entry 13 names ten keyed documents (three S-dev synthetic items, two S-heldout items and five new synthetic items), one full-agent run and one single-call baseline run per document, five v2 re-assessments, two extra full-agent runs on each of two documents, and one low and one high effort run on one document.
What ran is eight of those ten documents: the two S-heldout items in `eval/blind/` were not run, by the planner's ruling under the owner's delegation, to keep the held-out set's budget of three evaluations for the frozen stage (`docs/SEALING.md`, access budget S-heldout 3) and because the keys are unsigned.
That departure from the text of entry 13 is recorded as entry 14 of `eval/prereg_deviations.md`.
The eight documents are `payments_orchestration`, `clinical_rpm`, `research_lakehouse`, `iot_fleet`, `consent_service`, `hospital_scheduling`, `ledger_migration` and `exam_platform` under `eval/synthetic/`, each with 14 planted flaws in its v1 key (`scores.json` `metrics.recall.g` = 14 on every v1 row).
FULL is the agent (`dra review <doc>/design_v1.pdf --profile demo --no-tools`) and B0 is the single-call baseline (`--condition B0 --no-tools`), both on the Claude Code CLI backend at effort medium, one run per document (`RUNS.md` and `RUNS_B0.md` headers).
Both conditions ran with tools off (`--no-tools`), so neither did external research: every FULL run cites 0 external sources (`RUNS.md` column "external cited").
The other runs were five v2 re-assessments (`--previous runs/d_<doc>_v1_1`, from each run's `manifest.json` `extra.code.argv`), two variance repeats each on payments and iot, and one low and one high effort run on payments (`RUNS.md`).
The FULL runs were made at code eba6974 and B0 at 280c4b4: each run's `manifest.json` records the commit of its branch (`s4/plan-d-runs` or `s4/plan-d-b0`), and every recorded commit differs from eba6974 or 280c4b4 only under `docs/` (`git diff --name-only`).
280c4b4 is eba6974 plus the B0 condition, and that diff touches files on the FULL path as well (`orchestrator.py`, `phases/assess.py`, `phases/report.py`, `phases/verify.py`, `llm/runtime.py`); no FULL run was made at 280c4b4, so whether FULL behaves the same there is not measured.
Scoring was `sit-eval score` with the Opus judge at effort high, 3 samples, seed 20261002, `--candidate-rule shortlist_bounded --no-grounding-judges --exploratory` (`RUNS.md` and `RUNS_B0.md` headers).
With the grounding judges off, the G3 premise metric is null and the harness reports hallucination as G1 failures plus adjudicated HALLUCINATED findings only (`scores.json` `metrics.hallucinated_finding_rate.reason` and `metrics.hallucinated_finding_rate_without_g3.note`).
The FULL scorings were capped at $18 (`scores.json` `judge.max_cost_usd` = 18.0), two v2 rescores at $24, and the B0 scorings record no cap (`judge.max_cost_usd` null).
Grading was the key-blind lecturer grader, `sit-eval grade run`, 2 samples, seed 0, Opus high, `--max-cost-usd 8` (`GRADES.md` header).

The runs and scorings took place on 5 Oct 2026: the first FULL model call started at 04:35:57 and the last at 08:11:03 (the consent v2 resume; the last scored FULL run's last call was at 08:03:34), the B0 calls from 05:37:55 to 07:29:08 (each run's `llm.jsonl` `started_at`), the scorings were written from 04:43 to 08:10 (`scores.json` `generated_at`), and the grader calls ran from 05:32 to 08:13 (`grader_calls.jsonl` `ts` of each grade folder).
The Claude subscription's session limit interrupted the work from 06:05 to 07:10: the first refused call is at 06:05:32 (`d_consent_v2_1/llm.jsonl`, outcome `LLMUnavailableError`) and the limit reset at 07:10 (`RUNS_B0.md` notes).
It affected six things, and no scored row comes from a call made during it:
- `d_consent_v2_1` aborted in refine after 15 refused attempts (`llm.jsonl` outcome counts); it was resumed after the reset and then crashed on INV-04 (section 7).
- The first scoring of `d_iot_v2_1` was stopped by hand at 06:20 with 291 of 337 judge calls errored and was rescored after the reset (`RUNS.md` Scores); its judge log holds 340 entries from 06:05:43 to 06:20:45, 46 ok and 294 errored, at $5.03 (`eval_d/judge_calls.jsonl` `outcome` and `call_cost_usd`, counted by script), three entries more than `RUNS.md` counted.
- The first scoring of `d_b0_iot_v1_1` had all 31 judge calls (124 attempts) refused; it was rescored at 07:13 and the row carries that score (`RUNS_B0.md` notes).
- `d_b0_consent_v1_1` crashed in assess after 30 s and 5 refused attempts; its rerun `d_b0_consent_v1_2` is the scored B0 consent row (`RUNS_B0.md`).
- `d_b0_hospital_v1_1` started at the limit and was stopped by the worker; `d_b0_hospital_v1_2` is the scored B0 hospital row (`RUNS_B0.md`).
- The first grade of `d_iot_v1_1` stopped after 3 calls and $2.43 and was set aside; the row in `GRADES.md` is a fresh grade (`GRADES.md` notes).

## 2. Headline: FULL against B0 per document

Sources: FULL recall, precision, severity-weighted, critical, flags and scoring cost from `RUNS.md` Scores, FULL wall and run cost from `RUNS.md` Runs, B0 from `RUNS_B0.md`, B0 strict precision and B0 flag denominators from each `scores.json` (`metrics.precision_strict`).
Hallucination flags are G1 failures plus adjudicated HALLUCINATED, without G3, over the scored findings; "lb" marks a run cost that is a lower bound because a call was cut and its usage not recorded.
The FULL hospital row is the rerun `d_hospital_v1_2` (section 7) and the B0 consent and hospital rows are the reruns `_v1_2` (section 1).

| Document | Condition | Strict recall | Lenient recall | Strict precision | Adjudicated precision | Severity-weighted recall | Critical recall | Hallucination flags | Run wall s | Run cost USD | Scoring cost USD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| payments | FULL | 14 of 14 | 1.000 | 0.700 | 0.950 | 1.000 | 1.000 | 0 of 20 | 431 | 7.51 | 4.91 |
| payments | B0 | 13 of 14 | 0.929 | 0.765 | 1.000 | 0.933 | 1.000 | 0 of 17 | 363 | 1.08 | 3.89 |
| clinical | FULL | 10 of 14 | 0.929 | 0.385 | 0.885 | 0.717 | 0.750 | 0 of 26 | 504 | 7.93 | 7.92 |
| clinical | B0 | 8 of 14 | 0.929 | 0.571 | 1.000 | 0.567 | 0.500 | 0 of 14 | 290 | 0.91 | 2.84 |
| lakehouse | FULL | 13 of 14 | 0.929 | 0.591 | 0.864 | 0.983 | 1.000 | 0 of 22 | 450 | 6.39 lb | 5.38 |
| lakehouse | B0 | 10 of 14 | 0.857 | 0.714 | 1.000 | 0.883 | 1.000 | 0 of 14 | 256 | 0.83 | 3.05 |
| iot | FULL | 11 of 14 | 0.929 | 0.423 | 0.923 | 0.783 | 0.750 | 0 of 26 | 432 | 5.40 lb | 7.40 |
| iot | B0 | 10 of 14 | 1.000 | 0.588 | 0.941 | 0.767 | 0.750 | 0 of 17 | 333 | 0.96 | 3.75 |
| consent | FULL | 14 of 14 | 1.000 | 0.700 | 0.900 | 1.000 | 1.000 | 0 of 20 | 367 | 5.82 | 4.53 |
| consent | B0 | 11 of 14 | 0.786 | 0.917 | 0.917 | 0.900 | 1.000 | 0 of 12 | 249 | 0.77 | 2.82 |
| hospital | FULL | 12 of 14 | 0.929 | 0.571 | 0.762 | 0.850 | 0.750 | 0 of 21 | 480 | 5.05 lb | 4.68 |
| hospital | B0 | 12 of 14 | 0.857 | 0.923 | 1.000 | 0.967 | 1.000 | 0 of 13 | 217 | 0.69 | 2.42 |
| ledger | FULL | 12 of 14 | 0.929 | 0.632 | 0.842 | 0.917 | 1.000 | 0 of 19 | 390 | 6.13 | 4.24 |
| ledger | B0 | 12 of 14 | 0.929 | 0.706 | 1.000 | 0.917 | 1.000 | 0 of 17 | 281 | 0.83 | 3.84 |
| exam | FULL | 12 of 14 | 0.929 | 0.750 | 0.938 | 0.917 | 1.000 | 0 of 16 | 372 | 6.16 | 3.57 |
| exam | B0 | 12 of 14 | 0.929 | 0.857 | 0.929 | 0.917 | 1.000 | 0 of 14 | 207 | 0.67 | 2.77 |
| **Total or mean** | **FULL** | **98 of 112** | **106 of 112** | **0.594** | **0.883** | **0.896** | **0.906** | **0 of 170** | **3,426** | **50.39 (lower bound)** | **42.63** |
| **Total or mean** | **B0** | **88 of 112** | **101 of 112** | **0.755** | **0.973** | **0.856** | **0.906** | **0 of 118** | **2,196** | **6.74** | **25.38** |

The totals were recomputed from the rows: the recall and flag counts are sums of `scores.json` `metrics.recall.tp`, `metrics.lenient_recall.tp` and the scored-finding counts, the precision, severity and critical columns are means over the eight documents, and the wall and cost columns are sums of the rows as printed.
The strict recall totals agree with the tables: 98 of 112 for FULL and 88 of 112 for B0.
Summed before rounding, FULL run cost is $50.40 (`manifest.json` `usage.cost_usd`) and B0 scoring cost $25.39 (`scores.json` `calls.cost_usd_reported`); the wall column is `RUNS.md` "wall s", which is within 3 s per run of `manifest.json` `extra.timing.wall_clock_s` (sums 3,418.8 s and 2,188.8 s).
Every run's outcome is `completed_degraded` (`RUNS.md`, `RUNS_B0.md`): every report lists an `input_degraded` entry, every FULL report a `tool_unavailable` entry (tools were off), and the FULL runs carry 0 to 2 deadline cuts of calls each (`report.json` `research_log.degradations` types, counted by script).
B0 is one logical model call: `llm.jsonl` holds 1 attempt for each of the eight scored B0 runs (`RUNS_B0.md` column "attempts").

Per document, FULL found more planted flaws strictly than B0 on five documents (payments +1, clinical +2, lakehouse +3, iot +1, consent +3) and the same number on three (hospital, ledger, exam), and B0 found more on none (the rows above).
FULL had lower strict precision than B0 on all eight documents, and lower adjudicated precision on seven; exam is the one document where FULL's adjudicated precision is higher, 0.938 against 0.929 (the rows above).
FULL cost about 7.5 times B0 per run at the lower bound ($50.39 against $6.74 over eight runs) and took 1.56 times the wall time (3,426 s against 2,196 s).

The aggregate was made with `sit-eval aggregate` over the sixteen v1 `scores.json` files (the eight FULL rows and the eight B0 rows above), `--exploratory`, bootstrap B = 10,000, seed 0, paired seed 1, into the ignored `runs/aggregate_plan_d.json` of this worktree.
The FULL scorings were made without `--condition`, so their `scores.json` `inputs.condition` is null and the harness files them under the label `unlabelled`; the B0 scorings carry `B0`.
The command as briefed, `--compare FULL --compare B0`, therefore paired no documents (kept as `runs/aggregate_plan_d_literal.json`), and the comparison below is `--compare unlabelled --compare B0`, which pairs all eight documents.
The relabelling is only of the label the harness reads; no score file was edited.

| Aggregate (FULL minus B0, eight documents, one run each) | Point | 95% interval | Test p, two-sided |
|---|---|---|---|
| Strict recall, paired bootstrap | +0.089 | +0.036 to +0.152 | 0.0004 (bootstrap) |
| Strict recall, document-level sign-flip | +0.089 | none given | 0.0625 (one-sided 0.031) |
| Strict recall, flaw-level stratified permutation | +0.089 | none given | 0.0117 |
| Strict recall, flaw-level McNemar (12 FULL only, 2 B0 only) | | | 0.0129 (sanity check only) |
| Lenient recall, paired bootstrap | +0.045 | -0.009 to +0.107 | 0.124; sign-flip 0.3125 |
| Severity-weighted recall, paired bootstrap | +0.040 | -0.019 to +0.090 | 0.180; sign-flip 0.281 |
| Critical recall, paired bootstrap | 0.000 | -0.094 to +0.094 | 1.0; sign-flip 1.0 |
| Strict precision, paired bootstrap | -0.161 | -0.227 to -0.107 | 0.0 (bootstrap); sign-flip 0.0078 |
| Adjudicated precision, paired bootstrap | -0.090 | -0.148 to -0.038 | 0.0 (bootstrap); sign-flip 0.0156 |

Source: `runs/aggregate_plan_d.json` `comparison.<metric>.paired_bootstrap` and `.sign_flip`, and `comparison.flaw_level`.
Per condition the macro strict recall is 0.875 (95% interval 0.813 to 0.938) for FULL and 0.786 (0.705 to 0.857) for B0 (`conditions.<label>.recall`).
The sign-flip p of 0.0625 is the honest document-level test: five documents favour FULL and three tie, and with five non-zero differences the smallest two-sided p it can give is 2 of 32.
The harness labels the flaw-level McNemar "McNemar ignores clustering: sanity check only (metrics.md §12.3)" and the stratified permutation "design-effect variance inflation (pilot rho) not applied" (`comparison.flaw_level`).
The harness's own caveat labels on this aggregate are `exploratory: true` with the note "EXPLORATORY: this run was started with --exploratory (eval/prereg.yaml LC12 override); these scores are exploratory and may not be reported as confirmatory", and on every input "unfrozen pilot score" (`runs/aggregate_plan_d.json` `exploratory_note` and `warnings`).
Every input `scores.json` has `status: pilot_unfrozen` with the message "eval/prereg.yaml is not frozen (frozen: false): these scores are UNFROZEN PILOT scores, exploratory only, and carry no confirmatory claim" (`prereg.message`).
The prereg pilot checkpoint came out `not_evaluable`, "no FULL run in the inputs", because of the missing label (`pilot_checkpoint`).
Applied by hand to the `unlabelled` figures, the checkpoint rule would give `fail`: the lower-bound median FULL run cost is $6.15 over 8 runs (5 fully accounted, median $6.16) against the threshold $3.24 of `eval/prereg.yaml` `costs.per_run_usd.heavy_case_FULL` (`conditions.unlabelled.cost_usd` and `pilot_checkpoint.threshold_usd`).

## 3. Run-to-run variance

Payments was run three times at medium and found 14, 14 and 13 of 14 flaws strictly (`d_payments_v1_1`, `_v1_2`, `_v1_3` in `RUNS.md` Scores).
Iot was run three times and found 11, 12 and 11 of 14 (`d_iot_v1_1`, `_v1_2`, `_v1_3` in `RUNS.md` Scores).
On both documents the same agent on the same document moved by one flaw, 0.071 of strict recall, between runs; adjudicated precision moved from 0.857 to 0.950 on payments and from 0.815 to 0.923 on iot (same rows).
So a one-flaw difference between FULL and B0 on a single document, as on payments and iot in section 2, is within the spread one run can show, and only the clinical (+2), lakehouse (+3) and consent (+3) differences are larger than any spread seen here.
This rests on two documents, three runs each, for FULL only; B0's run-to-run spread was not measured.
One run per document is what plan D chose (decision #46: between-document variance dominates), and it means every per-document row above is one draw; the paired statistics in section 2 treat the document as the unit and do not see run-to-run variance at all.

## 4. Effort ablation on payments

Effort was set by a copied config folder with two extra profiles, `demo_low` and `demo_high`, passed as `--config config_effort --profile demo_low` or `demo_high` (`manifest.json` `extra.code.argv` and `extra.config.files` of each run).
The effective per-stage effort was low on every stage for the low run, and high on plan, assess, refine, verify and report for the high run, with research at low as in the medium profile (`effective_config.json` `agent.effort`).
Low found 11 of 14 strictly in 241 s at $4.62, adjudicated precision 0.933 (`d_payments_v1_low` in `RUNS.md`).
Medium found 14, 14 and 13 of 14 in 431, 449 and 444 s at $7.51, $5.53 (lower bound) and $6.37 (lower bound) (section 3 rows).
High found 12 of 14 in 509 s, adjudicated precision 0.818 (`d_payments_v1_high` in `RUNS.md`).
The high run is not a clean measurement of effort: 7 of its 10 model calls were cut at a deadline (`llm.jsonl` outcome `LLMDeadlineError`, and 7 `budget_or_deadline_hit` entries in `report.json`), so its recorded cost of $1.36 is a far lower bound and its findings come from a run that lost most of its calls to the time limits.
The conclusion is unchanged: medium stays the default (decision #33), because low lost three flaws and high did not gain any within the run's time limits.
This is n = 1 run per arm on one document, exploratory, as decision #33 itself said of the earlier ablation (13 of 14 for both medium and high on payments, `docs/live_runs/QUALITY_COMPARISON.md` line 22).

## 5. Grades from the key-blind grader

| Run | Document | S | Grade | Pass | D1 to D10 | Grader hallucination flags | Material | Needs human review |
|---|---|---|---|---|---|---|---|---|
| d_payments_v1_1 | payments | 84.8 | B | PASS | 4, 4, 4, 3, 4, 3.5, 3, 1.5, 3, 3 | 7 | no | yes |
| d_clinical_v1_1 | clinical | 77.0 | B | PASS | 4, 4, 4, 3, 3, 3, 3, 1, 2, 3 | 4 | no | yes |
| d_lakehouse_v1_1 | lakehouse | 80.5 | B | PASS | 4, 4, 4, 3, 3, 4, 3, 1.5, 2, 3 | 5 | no | yes |
| d_iot_v1_1 | iot | 80.5 | B | PASS | 4, 4, 4, 3, 3, 4, 3.5, 1, 2, 3 | 4 | no | no |
| d_consent_v1_1 | consent | 83.0 | B | PASS | 4, 4, 4, 3, 4, 4, 3, 1, 2, 3 | 6 | no | yes |
| d_ledger_v1_1 | ledger | 83.2 | B | PASS | 4, 4, 4, 3, 3, 3.5, 3.5, 2, 3, 3 | 2 | no | no |
| d_exam_v1_1 | exam | 82.0 | B | PASS | 4, 4, 4, 3, 3, 3, 4, 1.5, 3, 3 | 7 | no | no |
| d_hospital_v1_2 | hospital | 86.2 | B | PASS | 4, 4, 4, 3, 3.5, 4, 4, 1.5, 3, 3 | 4 | no | no |

Source: `docs/live_runs/plan_d/GRADES.md`.
All eight FULL reviews graded B and PASS, mean S 82.15 (the eight S values summed and divided by eight), seven of eight at or above the internal target of 80 key-blind (`research/grading/README.md` section 4.4; clinical 77.0 is below), at $43.43 for the eight grades and $45.86 with the stopped attempt (`GRADES.md` notes).
No grader hallucination flag was material in any review, and four of the eight reviews were marked for human review (`GRADES.md` columns "material" and "needs human review").
The grader scores the written review on ten weighted dimensions from 0 to 4, from design-intent understanding (D1) to professional quality (D10), and S is the weighted sum on a 0 to 100 scale computed in code (`research/grading/README.md` section 3.1 and `harness/sit_eval/grader/scoring.py`).
Key-blind means the grader judges coverage against its own pre-read of the design, written before it reads the review, without the answer key (`research/grading/README.md` section 5, "Modes").
It does not measure recall of the planted flaws (that is the scorer's job in section 2), and the grading README itself says headline claims rest on judge-free metrics because iterating on grader scores risks Goodhart effects (`research/grading/README.md` section 4.4, superseded note of 2026-10-02).
D8 (research sufficiency and stopping) is 1.0 to 2.0 on every review, which is what tools off should give: the runs did no external research (section 1).
The grader is the same model family as the agent and the scoring judge (Opus at effort high, `GRADES.md` header), and B0 was not graded, so the grades say nothing about FULL against B0.

## 6. v2 re-assessment

Five v2 re-assessments ran with `--previous runs/d_<doc>_v1_1` (`manifest.json` `extra.code.argv`); four were scored against the v2 keys and one crashed (`RUNS.md`).

| Run | Strict recall (v2 key) | Lenient recall | Strict precision | Adjudicated precision | Scored findings | Duplicates (adjudicated) | Hallucination flags | Scoring cost USD |
|---|---|---|---|---|---|---|---|---|
| d_payments_v2_1 | 8 of 9 | 1.000 | 0.286 | 0.821 | 28 | 4 | 0 of 28 | 11.51 |
| d_clinical_v2_1 | 6 of 9 | 0.889 | 0.207 | 0.862 | 29 | 2 | 0 of 29 | 11.76 |
| d_lakehouse_v2_1 (rescore, cap 24) | 7 of 9 | 0.889 | 0.111 | 0.254 | 63 | 46 | 0 of 63 | 11.33 |
| d_iot_v2_1 (rescore, cap 24) | 7 of 8 | 0.875 | 0.121 | 0.224 | 58 | 43 | 1 of 58 | 5.00 |

Source: `RUNS.md` Scores for recall, precision, flags and cost; `scores.json` `metrics.precision_strict.n` and `metrics.adjudication_counts` for the scored findings and duplicates.
The two rescores at the $24 cap reused judge answers cached by the stopped scorings (103 of 126 calls on lakehouse, 113 of 124 on iot, `scores.json` `calls.calls_cached`), so their $11.33 and $5.00 cover only the 23 and 11 live calls; the full v2 scoring spend is in section 7.
Recall against the v2 keys was 8 of 9, 6 of 9, 7 of 9 and 7 of 8.
Precision fell sharply on lakehouse and iot: 0.111 strict and 0.254 adjudicated over 63 findings, and 0.121 and 0.224 over 58.
The harness adjudicated 46 of the 63 lakehouse findings and 43 of the 58 iot findings as DUPLICATE (duplication rate 0.730 and 0.741), against 4 of 28 and 2 of 29 on payments and clinical v2 (`metrics.adjudication_counts` and `metrics.duplication_rate`).
The one hallucination flag of plan D is on iot v2: 1 of 58 findings adjudicated HALLUCINATED (`metrics.adjudication_counts`, and `RUNS.md` "1 of 58").
Consent v2 did not score: its first attempt aborted in refine at the session limit, and the resume crashed in report on the INV-04 invariant (rc=4, `RUNS.md` rows `d_consent_v2_1` and `d_consent_v2_1 (resumed)`).
A separate read-only diagnosis (`docs/transcripts/session6/v2-diagnosis.md` committed as 2a91b83 on branch `s4/v2-diag`, 5 Oct 2026, not yet verified or merged) classifies the scored findings of lakehouse v2 (63) and iot v2 (58): 7 and 7 strict matches to an open gold flaw, 1 and 0 lenient-only matches, 0 and 0 matched to a flaw the v2 key marks fixed, 3 and 2 new unmatched non-duplicates (one of the iot two is the HALLUCINATED flag), and 46 and 43 adjudicated DUPLICATE.
It finds that 36 of the 46 and 35 of the 43 duplicates share their duplicate target's prior finding id, so most of the surplus is several assess shards carrying the same v1 finding forward.
Its stated root cause is that refine did not complete on these two runs: the first refine answer was complete but left out the status of one prior finding, the repair call was cut by the deadline with 18 s and 45 s left, and refine fell back to the unmerged drafts, so 41 and 42 planned merges were not applied (against 49 and 30 merges in the v1 runs).
It proposes agent and harness changes and a re-run of the two v2 documents after them; a fix to the refine path is in progress (worktree branch `s4/refine-prior-status`, nothing committed or merged when this was checked), and no re-run has been made.
So the lakehouse and iot v2 precision figures describe a run whose refine fell back to unmerged drafts, not the agent's refine working as designed.

## 7. Defects the evaluation found, and their state

- INV-05 report crash: `d_hospital_v1_1` crashed in report (rc=4, StageCrash, INV-05 evidence quote invariant) after 385 s and $5.91 (`RUNS.md` Runs).
  The fix is on the truth branch `claude/happy-darwin-d0bl94` in four commits, 6980c33, e0c7925, 2ef95e4 and 6ca319d, plus 6ca33e7 for a URL scheme in any letter case (`git log 280c4b4..6ca33e7 -- agent`); 0da6c61 and 88abd54 are worker notes, not code.
  So the cause of the hospital crash is fixed on the tip, but the fixed code has not been re-run on hospital: the scored FULL hospital row is the rerun `d_hospital_v1_2` on the old code (eba6974 plus docs), which did not hit the crash (`RUNS.md`, `manifest.json` `extra.code.git_commit` 764c3f0).
  No plan D run, FULL or B0, was made on the fixed code (eba6974 and 280c4b4 are both ancestors of 6980c33, and no run commit contains it).
- INV-04 crash on resume: `d_consent_v2_1 (resumed)` crashed in report on the INV-04 invariant (quote-anchor verification, `agent/sit_review_agent/invariants.py`), not scored (`RUNS.md`).
  The same unverified diagnosis note (`docs/transcripts/session6/v2-diagnosis.md`, Question B, 2a91b83 on `s4/v2-diag`) finds that the report phase's redaction on the run's code rewrote a document URL inside a sound-area anchor quote, the same cause the INV-05 repair 6980c33 addressed, and that at 6ca319d the check passes on the crashed report with the quote restored.
  It proposes resuming the run on the repaired code and scoring it, plus a guard; neither has been done, so consent v2 has no score.
- Two scorings stopped at the $18 judge cap: `d_lakehouse_v2_1` stopped_budget at a recorded $15.90 and the first post-reset `d_iot_v2_1` rescore stopped_budget at $15.62, each rc=3 with no metrics (`RUNS.md` Scores).
  Both were rescored at a $24 cap, at $11.33 and $5.00, and those are the rows used (`RUNS.md`, `scores.json` `judge.max_cost_usd` = 24.0).
  The cap fired below $18 by its own rule: the scorer refuses to start a call when committed spend plus a reserve for every call in flight and for the next call would pass the cap (`harness/sit_eval/calls.py` `JudgeRunner._check_budget`), the reserve is the judge's per-call limit of $1.00 (`harness/sit_eval/config.py` `max_budget_usd_per_call`, recorded as `scores.json` `calls.budget.reserve_usd` 1.0), and at concurrency 4 it can stop once committed spend passes $14; the figure recorded is the committed spend after the calls in flight finished.
  The judge logs agree: the stopped lakehouse scoring made 103 calls at $15.90 and the stopped iot rescore 67 calls at $15.62, all ok (`eval_d/judge_calls.jsonl`, counted by script).
  The v2 scoring spend is therefore $27.23 on lakehouse ($15.90 plus $11.33) and $25.65 on iot ($5.03 for the hand-stopped first scoring, from its judge log, plus $15.62 plus $5.00).

## 8. Caveats

- Exploratory: every score was made with `--exploratory`, the LC12 override for keys that are not signed off, and the harness says "these scores are exploratory and may not be reported as confirmatory" (`scores.json` `exploratory_note`).
- Keys unsigned: every key has `scored_run_ready = false` (`scores.json` warnings), and only Malcolm signs them (decision #26).
- Prereg unfrozen: "eval/prereg.yaml is not frozen (frozen: false): these scores are UNFROZEN PILOT scores, exploratory only, and carry no confirmatory claim" (`scores.json` `prereg.message`).
- Plan D ran eight of the ten documents named in prereg deviation entry 13; the two held-out items were not run, so nothing here is measured on held-out material (entry 14 of `eval/prereg_deviations.md`, section 1).
- Same model family: the agent, the B0 call, the scoring judge (Opus, effort high) and the grader (Opus, high) are all the same model family (`RUNS.md`, `RUNS_B0.md` and `GRADES.md` headers), so a shared blind spot would not show.
- One run per document: each per-document row is one draw, the run-to-run spread is one flaw on the two documents where it was measured, and B0's spread was not measured (section 3).
- Who wrote the documents: five of the eight documents (`iot_fleet`, `consent_service`, `hospital_scheduling`, `ledger_migration`, `exam_platform`) and their keys were authored by the same model family within this project (worker notes `docs/transcripts/session6/item-*.md`; decision #46); the two held-out items in `eval/blind/` were not touched.
- B0 is one logical call with the same retry path as the agent's calls; its attempts are recorded in `llm.jsonl` and every scored B0 run has 1 (`RUNS_B0.md`).
- Tools off: both conditions ran with `--no-tools`, so this compares the agent's structure, not its research; the with-tools agent is not measured here.
- Code differs between arms: FULL at eba6974, B0 at 280c4b4, and the diff touches files on the FULL path (section 1).
- Unlabelled agent scorings: the FULL scorings carry no `--condition`, so the aggregate compares `unlabelled` with `B0`, and the prereg pilot cost checkpoint reads `not_evaluable`; applied by hand it would read `fail`, a $6.15 lower-bound median FULL run cost against the $3.24 threshold (section 2).
- Hospital row: the scored FULL hospital row is the rerun `d_hospital_v1_2` on the old code, after the first run crashed on INV-05; the fixed code was not run on hospital (section 7).
- Session limit: the subscription's session limit refused calls from 06:05 to 07:10, which aborted the first consent v2 run and voided two scorings, one grade and two B0 runs that were then redone; no scored row comes from a call made during it (section 1).
- Judge caps: two v2 scorings stopped at the $18 cap and were rescored at a $24 cap from the cached judge answers, so their table cost covers only the live calls (sections 6 and 7).
- Effort ablation: the high-effort run lost 7 of its 10 model calls to deadline cuts, so it measures the time limits as much as the effort (section 4).
- v2 figures: the lakehouse and iot v2 precision reflects a refine fallback to unmerged drafts (unverified diagnosis, section 6), a fix for it is in progress and not merged, and consent v2 has no score.
- Cost figures are the CLI's estimates on the subscription, not billed amounts, and three of the eight FULL v1 costs are lower bounds (section 2).
- Grounding judges off: G3 and citation-support metrics are null (`scores.json` warnings), so "hallucination flags" here means G1 failures plus adjudicated HALLUCINATED only.
- Load: runs and scorings shared the Mac with other work, under a gate of a 5-minute load below 10 and over 35 percent free memory (`RUNS.md` header); load can change wall time, not scores.

## 9. What this allows Malcolm to say, and what it does not

He can say:
- "In an exploratory test on eight synthetic design documents with 14 planted flaws each, one run per document, the agent matched 98 of 112 flaws strictly (recall 0.875), against 88 of 112 (0.786) for a single model call on the same documents."
- "The paired gain is +0.089 in strict recall, with a 95 percent bootstrap interval of +0.036 to +0.152, but the document-level sign-flip test gives only p = 0.0625, because five documents favoured the agent and three tied."
- "The scorer flagged no finding as hallucinated in any of the agent's fourteen scored v1 runs (0 of 170 findings on the eight compared runs, without the grounding judges), and a key-blind grader of the same model family passed all eight reviews at grade B, mean 82.15 of 100."

He cannot say:
- That the agent is better than a single call in a confirmatory sense: the keys are unsigned, the prereg is unfrozen, and every figure is labelled exploratory by the harness.
- That the agent is more precise: it is less precise, 0.594 against 0.755 strict and 0.883 against 0.973 adjudicated (section 2), and on two v2 re-assessments most of its findings were duplicates (section 6).
- That it is worth its cost: it cost about 7.5 times as much per run at the lower bound, $50.39 against $6.74 for eight runs (section 2).
- Anything about the held-out items, real-world documents, or the agent with tools, none of which were run.
- That a one-flaw difference on one document means anything: the agent's own repeats move by one flaw (section 3).
