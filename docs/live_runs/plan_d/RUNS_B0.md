# Plan D, condition B0 (single-call baseline)

Every run: `dra review <doc>/design_v1.pdf --profile demo --condition B0 --no-tools`, on the Claude Code CLI backend.
Scoring: `sit-eval score` with judge claude_code, claude-opus-5-5, effort high, 3 samples, seed 20261002, `--no-grounding-judges --exploratory`.
Attempts are the entries of `llm.jsonl`, counted by script.
Hallucination flags count G1 failures plus adjudicated HALLUCINATED findings (the G3 premise judge is off).

| run-id | document | condition | effort | wall s | outcome | findings | attempts | cost lower bound USD | load before (5-min, free %) | load after | strict recall | lenient recall | precision (adjudicated) | severity-weighted recall | critical recall | hallucination flags (G1 + adjudicated, no G3) | scoring cost USD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| d_b0_payments_v1_1 | payments_orchestration | B0 | medium | 363 | completed_degraded | 18 | 1 | 1.08 | 7.32, 45 | 6.38, 40 | 13 of 14 | 0.929 | 1.000 | 0.933 | 1.000 | 0 | 3.89 |
| d_b0_clinical_v1_1 | clinical_rpm | B0 | medium | 290 | completed_degraded | 16 | 1 | 0.91 | 6.84, 42 | 5.56, 40 | 8 of 14 | 0.929 | 1.000 | 0.567 | 0.500 | 0 | 2.84 |
| d_b0_lakehouse_v1_1 | research_lakehouse | B0 | medium | 256 | completed_degraded | 16 | 1 | 0.83 | 6.37, 43 | 6.07, 38 | 10 of 14 | 0.857 | 1.000 | 0.883 | 1.000 | 0 | 3.05 |
| d_b0_iot_v1_1 | iot_fleet | B0 | medium | 333 | completed_degraded | 19 | 1 | 0.96 | 7.12, 42 | 6.05, 40 | 10 of 14 | 1.000 | 0.941 | 0.767 | 0.750 | 0 | 3.75 |
| d_b0_consent_v1_1 | consent_service | B0 | medium | 30 | aborted_graceful | - | 5 | 0.00 | 6.72, 47 | 6.54, 48 | - | - | - | - | - | - | - |
| d_b0_consent_v1_2 | consent_service | B0 | medium | 249 | completed_degraded | 14 | 1 | 0.77 | 5.41, 49 | 4.48, 53 | 11 of 14 | 0.786 | 0.917 | 0.900 | 1.000 | 0 | 2.82 |
| d_b0_hospital_v1_2 | hospital_scheduling | B0 | medium | 217 | completed_degraded | 15 | 1 | 0.69 | 4.50, 53 | 8.01, 49 | 12 of 14 | 0.857 | 1.000 | 0.967 | 1.000 | 0 | 2.42 |
| d_b0_ledger_v1_1 | ledger_migration | B0 | medium | 281 | completed_degraded | 19 | 1 | 0.83 | 7.86, 49 | 6.75, 47 | 12 of 14 | 0.929 | 1.000 | 0.917 | 1.000 | 0 | 3.84 |

Notes

- d_b0_iot_v1_1: the run completed; its first scoring failed, all 31 judge calls (124 attempts) refused by the subscription's session limit (LLMUnavailableError, resets 07:10 SGT 5 Oct 2026); rescored at 07:13 after the reset (230 s), the row carries that score and its cost.
- d_b0_consent_v1_1: crashed in assess after 30 s on the same session limit (exit 3, 5 attempts, resumable); rerun after the reset as d_b0_consent_v1_2.
- d_b0_hospital_v1_1: started at the limit and stopped by the worker before it ran; its folder was set aside, the run-id is still unused.
