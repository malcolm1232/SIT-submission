# Plan D grades (key-blind lecturer grader)

Grader: `sit-eval grade run`, key-blind, 2 samples, seed 0, Opus `high`, `--max-cost-usd 8`; one v1 agent review per document.

| run-id | document | status | S | grade | pass | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | halluc. flags | material | needs human review | grader calls | cost USD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| d_payments_v1_1 | payments_orchestration | complete | 84.8 | B | PASS | 4.0 | 4.0 | 4.0 | 3.0 | 4.0 | 3.5 | 3.0 | 1.5 | 3.0 | 3.0 | 7 | no | yes | 4 | 5.3903 |
| d_clinical_v1_1 | clinical_rpm | complete | 77.0 | B | PASS | 4.0 | 4.0 | 4.0 | 3.0 | 3.0 | 3.0 | 3.0 | 1.0 | 2.0 | 3.0 | 4 | no | yes | 5 | 7.2604 |
| d_lakehouse_v1_1 | research_lakehouse | complete | 80.5 | B | PASS | 4.0 | 4.0 | 4.0 | 3.0 | 3.0 | 4.0 | 3.0 | 1.5 | 2.0 | 3.0 | 5 | no | yes | 4 | 5.1185 |
| d_iot_v1_1 | iot_fleet | complete | 80.5 | B | PASS | 4.0 | 4.0 | 4.0 | 3.0 | 3.0 | 4.0 | 3.5 | 1.0 | 2.0 | 3.0 | 4 | no | no | 4 | 5.3183 |
| d_consent_v1_1 | consent_service | complete | 83.0 | B | PASS | 4.0 | 4.0 | 4.0 | 3.0 | 4.0 | 4.0 | 3.0 | 1.0 | 2.0 | 3.0 | 6 | no | yes | 5 | 6.4323 |
| d_ledger_v1_1 | ledger_migration | complete | 83.2 | B | PASS | 4.0 | 4.0 | 4.0 | 3.0 | 3.0 | 3.5 | 3.5 | 2.0 | 3.0 | 3.0 | 2 | no | no | 4 | 4.8626 |
| d_exam_v1_1 | exam_platform | complete | 82.0 | B | PASS | 4.0 | 4.0 | 4.0 | 3.0 | 3.0 | 3.0 | 4.0 | 1.5 | 3.0 | 3.0 | 7 | no | no | 4 | 4.619 |
| d_hospital_v1_2 | hospital_scheduling | complete | 86.2 | B | PASS | 4.0 | 4.0 | 4.0 | 3.0 | 3.5 | 4.0 | 4.0 | 1.5 | 3.0 | 3.0 | 4 | no | no | 4 | 4.4275 |

Notes:
- d_iot_v1_1: the first attempt stopped at the subscription session limit (reset 07:10 SGT, 5 Oct 2026) after 3 calls and $2.43; it was set aside (`runs/grades/d_iot_v1_1_attempt1_session_limit`) and the row above is a fresh grade.
- d_hospital_v1_1 crashed in report (no report.json) and is not graded; hospital is graded on its rerun d_hospital_v1_2.
- Totals: 8 grades, mean S 82.15, all B and PASS; grading cost $43.43 for the rows, $45.86 with the stopped attempt.
