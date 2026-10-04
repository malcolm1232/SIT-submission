# Plan D grades (key-blind lecturer grader)

Grader: `sit-eval grade run`, key-blind, 2 samples, seed 0, Opus `high`, `--max-cost-usd 8`; one v1 agent review per document.

| run-id | document | status | S | grade | pass | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | halluc. flags | material | needs human review | grader calls | cost USD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| d_payments_v1_1 | payments_orchestration | complete | 84.8 | B | PASS | 4.0 | 4.0 | 4.0 | 3.0 | 4.0 | 3.5 | 3.0 | 1.5 | 3.0 | 3.0 | 7 | no | yes | 4 | 5.3903 |
| d_clinical_v1_1 | clinical_rpm | complete | 77.0 | B | PASS | 4.0 | 4.0 | 4.0 | 3.0 | 3.0 | 3.0 | 3.0 | 1.0 | 2.0 | 3.0 | 4 | no | yes | 5 | 7.2604 |
| d_lakehouse_v1_1 | research_lakehouse | complete | 80.5 | B | PASS | 4.0 | 4.0 | 4.0 | 3.0 | 3.0 | 4.0 | 3.0 | 1.5 | 2.0 | 3.0 | 5 | no | yes | 4 | 5.1185 |
| d_iot_v1_1 | iot_fleet | failed |  |  | n/a |  |  |  |  |  |  |  |  |  |  | 0 | no | yes | 3 | 2.4275 |
