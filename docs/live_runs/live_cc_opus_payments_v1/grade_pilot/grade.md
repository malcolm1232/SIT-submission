# Lecturer grade: REV-live_cc_opus_payments_v1

> Grader-derived score; validity tier: unvalidated (GR §7 smoke calibration not yet run); same-family grader

| | |
|---|---|
| Mode | key_blind (key-blind is the score) |
| Document | DOC-design_v1 (21 pages); matches review: True |
| Grader | claude-opus-5-5 (requested claude-opus-5-5, effort high) |
| Prompt | lecturer-v1, bundle sha256 64efe6b88489ac55... (lock ok: True) |
| Calls | 4; spent $4.8494 of $8.00 |

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

## Hallucination flags (6)

- FND-013 misrepresented_doc_content (material, suspected; flagged in s1, s2): "Section 9.2 relies on the stuck-payment sweeper to clear IN_PROGRESS locks, but Section 20.3 scans only payments in AUTHORISING."
- FND-018 misrepresented_doc_content (minor, suspected; flagged in s1, s2): "The FR-12 test expects 'exactly one event' per state change, whereas Section 17 specifies at-least-once delivery"
- FND-016 misrepresented_doc_content (minor, suspected; flagged in s1, s2): "The design sends device fingerprint, IP address, hashed email and phone, and addresses to FRV-1"
- FND-007 misrepresented_doc_content (minor, suspected; flagged in s1): "Section 8 records the authorization as a 'ledger journal', while Section 14.3 puts holds in a separate memo ledger"
- FND-006 wrong_doc_location (minor, verified_false; flagged in s1, s2): ""url_or_citation": "doc:DOC-design_v1#p13/s3""
- FND-004 wrong_doc_location (minor, verified_false; flagged in s1, s2): ""url_or_citation": "doc:DOC-design_v1#p1/s12.4""

## Harness checks (no model)

- Verdict present (code): True
- Anchor quotes: {'verified': 53, 'not_found': 0, 'other_document': 0}
- Injection pre-scan hits: 0
- Review schema errors: 0

## Needs human review

- suspected material hallucinations need verification (GR §4.3)
