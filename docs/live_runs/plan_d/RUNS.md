# Plan D live runs

Live runs of the design-review agent on the eight synthetic documents, plan D (Malcolm's word 4 Oct 2026 22:40).
Every run: `dra review <pdf> --profile demo --no-tools --run-id <id>` (CLI backend on the subscription, `ANTHROPIC_API_KEY` unset), one at a time, under the load gate (5-minute load under 10, free memory over 35 percent).
Every score: `sit-eval score runs/<id> --key eval/synthetic/<doc>/answer_key.canonical.json --out runs/<id>/eval_d --judge claude_code --model claude-opus-5-5 --effort high --samples 3 --seed 20261002 --concurrency 4 --max-cost-usd 18 --candidate-rule shortlist_bounded --no-grounding-judges --exploratory`.
Run folders stay under the ignored `runs/`; this file carries numbers only.
Loads are the 1-, 5- and 15-minute averages.

## Runs

| run-id | document | condition | effort | wall s | stage 1 end s | outcome | findings | cost USD (lower bound) | external cited | load before | load after |
|---|---|---|---|---|---|---|---|---|---|---|---|
| d_payments_v1_1 | payments_orchestration | FULL | medium | 431 | 241.0 | completed_degraded | 25 | 7.51 | 0 | 6.32/6.00/5.62 | 3.93/4.89/5.30 |
| d_clinical_v1_1 | clinical_rpm | FULL | medium | 504 | 259.4 | completed_degraded | 31 | 7.93 | 0 | 6.11/5.19/5.38 | 3.56/4.47/5.06 |
| d_lakehouse_v1_1 | research_lakehouse | FULL | medium | 450 | 265.4 | completed_degraded | 26 | 6.39 (lb) | 0 | 3.46/4.39/5.02 | 4.85/5.26/5.30 |
| d_iot_v1_1 | iot_fleet | FULL | medium | 432 | 265.0 | completed_degraded | 31 | 5.40 (lb) | 0 | 4.85/5.26/5.30 | 6.18/6.39/5.93 |
| d_consent_v1_1 | consent_service | FULL | medium | 367 | 174.0 | completed_degraded | 23 | 5.82 | 0 | 6.18/6.39/5.93 | 4.87/7.27/6.87 |
| d_hospital_v1_1 | hospital_scheduling | FULL | medium | 385 | 219.6 | crashed in report (rc=4; StageCrash, INV-05 evidence quote invariant) | - | 5.91 | - | 4.87/7.27/6.87 | 5.28/6.64/6.80 |
| d_ledger_v1_1 | ledger_migration | FULL | medium | 390 | 239.1 | completed_degraded | 24 | 6.13 | 0 | 5.28/6.64/6.80 | 6.06/5.45/6.06 |
| d_exam_v1_1 | exam_platform | FULL | medium | 372 | 201.4 | completed_degraded | 21 | 6.16 | 0 | 6.06/5.45/6.06 | 5.75/7.54/7.11 |
| d_payments_v2_1 | payments_orchestration | FULL | medium | 496 | 265.2 | completed_degraded | 38 | 5.84 (lb) | 0 | 5.75/7.54/7.11 | 4.85/6.30/6.84 |
| d_clinical_v2_1 | clinical_rpm | FULL | medium | 447 | 265.4 | completed_degraded | 35 | 7.34 (lb) | 0 | 4.85/6.30/6.84 | 4.38/6.15/6.68 |
| d_lakehouse_v2_1 | research_lakehouse | FULL | medium | 505 | 265.5 | completed_degraded | 69 | 7.61 (lb) | 0 | 4.38/6.15/6.68 | 3.32/5.46/6.20 |
| d_iot_v2_1 | iot_fleet | FULL | medium | 521 | 265.4 | completed_degraded | 70 | 6.98 (lb) | 0 | 3.32/5.46/6.20 | 4.18/5.74/6.24 |
| d_consent_v2_1 | consent_service | FULL | medium | 256 | 229.2 | aborted_graceful in refine (rc=3) | - | 5.76 | - | 4.18/5.74/6.24 | 7.87/6.89/6.63 |

## Scores

| run-id | document | strict recall (tp/g) | lenient recall | precision | severity-weighted | critical recall | hallucination flags | scoring cost USD | wall s | load before | load after |
|---|---|---|---|---|---|---|---|---|---|---|---|
| d_payments_v1_1 | payments_orchestration | 14/14 (1.000) | 1.000 | 0.700 strict / 0.950 adj | 1.000 | 1.000 | 0 of 20 | 4.91 | 209 | 3.65/4.78/5.26 | 5.60/5.81/5.63 |
| d_clinical_v1_1 | clinical_rpm | 10/14 (0.714) | 0.929 | 0.385 strict / 0.885 adj | 0.717 | 0.750 | 0 of 26 | 7.92 | 314 | 3.46/4.39/5.02 | 6.67/5.73/5.46 |
| d_lakehouse_v1_1 | research_lakehouse | 13/14 (0.929) | 0.929 | 0.591 strict / 0.864 adj | 0.983 | 1.000 | 0 of 22 | 5.38 | 229 | 4.85/5.26/5.30 | 7.41/6.48/5.84 |
| d_iot_v1_1 | iot_fleet | 11/14 (0.786) | 0.929 | 0.423 strict / 0.923 adj | 0.783 | 0.750 | 0 of 26 | 7.40 | 271 | 6.18/6.39/5.93 | 6.78/8.32/7.15 |
| d_consent_v1_1 | consent_service | 14/14 (1.000) | 1.000 | 0.700 strict / 0.900 adj | 1.000 | 1.000 | 0 of 20 | 4.53 | 227 | 4.87/7.27/6.87 | 8.82/7.96/7.23 |
| d_ledger_v1_1 | ledger_migration | 12/14 (0.857) | 0.929 | 0.632 strict / 0.842 adj | 0.917 | 1.000 | 0 of 19 | 4.24 | 211 | 6.06/5.45/6.06 | 13.39/9.49/7.60 |
| d_exam_v1_1 | exam_platform | 12/14 (0.857) | 0.929 | 0.750 strict / 0.938 adj | 0.917 | 1.000 | 0 of 16 | 3.57 | 211 | 5.75/7.54/7.11 | 9.33/8.46/7.61 |
| d_payments_v2_1 | payments_orchestration | 8/9 (0.889) | 1.000 | 0.286 strict / 0.821 adj | 0.905 | 1.000 | 0 of 28 | 11.51 | 359 | 4.85/6.30/6.84 | 7.49/7.07/7.04 |
| d_clinical_v2_1 | clinical_rpm | 6/9 (0.667) | 0.889 | 0.207 strict / 0.862 adj | 0.710 | 1.000 | 0 of 29 | 11.76 | 388 | 4.38/6.15/6.68 | 7.15/6.71/6.69 |
| d_lakehouse_v2_1 | research_lakehouse | stopped_budget (--max-cost-usd 18 reached, rc=3; no metrics written) | - | - | - | - | - | 15.90 | 376 | 3.32/5.46/6.20 | 6.18/6.84/6.67 |
| d_iot_v2_1 | iot_fleet | not scored: stopped by hand at 06:20 after the subscription session limit (291 of 337 judge calls errored; rescored after the 07:10 reset) | - | - | - | - | - | - | - | 4.18/5.74/6.24 | 4.80/5.46/6.06 |
