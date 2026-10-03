# Lecturer grade: REV-rehearsal_concurrent_high_1

**EXPLORATORY** - this run was started with --exploratory (eval/prereg.yaml LC12 override); these scores are exploratory and may not be reported as confirmatory

> Grader-derived score; validity tier: unvalidated (GR §7 smoke calibration not yet run); same-family grader

| | |
|---|---|
| Mode | key_blind (key-blind is the score) |
| Document | DOC-design_v1 (21 pages); matches review: True |
| Grader | claude-opus-5-5 (requested claude-opus-5-5, effort high) |
| Prompt | lecturer-v1, bundle sha256 64efe6b88489ac55... (lock ok: True) |
| Calls | 4; spent $5.2964 of $8.00 |

## Result: S = 83.8, grade B, PASS

Gates: G1 pass, G2 pass, G3 pass, G4 pass, G5 pass

| Dim | Name | Weight | s1 | s2 | Final |
|---|---|---|---|---|---|
| D1 | Design-intent understanding | 10 | 4 | 4 | 4 |
| D2 | Fitness-for-purpose judgement | 12 | 4 | 4 | 4 |
| D3 | Coverage | 10 | 4 | 4 | 4 |
| D4 | Evidence quality and traceability | 16 | 3 | 3 | 3 |
| D5 | Recommendation quality | 14 | 4 | 4 | 4 |
| D6 | Restraint and justified no change | 10 | 4 | 3 | 3.5 |
| D7 | Issue triage | 8 | 4 | 4 | 4 |
| D8 | Research sufficiency | 8 | 1 | 1 | 1 |
| D9 | Output integrity | 8 | 2 | 2 | 2 |
| D10 | Professional quality | 4 | 3 | 3 | 3 |
| S | | | 85 | 82.5 | 83.8 |

Disagreement: max dimension delta 1, S delta 2.5; third sample run: False.

## Hallucination flags (1)

- FND-027 misrepresented_doc_content (minor, suspected; flagged in s1): "the sweeper scans payments in AUTHORISING, so a pod that crashes after the DynamoDB put but before the payment row is created leaves an IN_PROGRESS record with "

## Harness checks (no model)

- Verdict present (code): True
- Anchor quotes: {'verified': 61, 'not_found': 0, 'other_document': 0}
- Injection pre-scan hits: 0
- Review schema errors: 0

## Warnings

- EXPLORATORY: this run was started with --exploratory (eval/prereg.yaml LC12 override); these scores are exploratory and may not be reported as confirmatory
