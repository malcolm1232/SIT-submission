# Worker note: B0 verdict wording

## Change
`fallback_verdict(findings, reason, *, by_design: bool = False)` in `agent/sit_review_agent/phases/report.py` gains a keyword-only `by_design` flag.
When it is true the rationale reads: "Verdict derived by rule from the severities and dispositions of the verified findings: condition B0 is the single-call baseline, whose one model call is the assessment, so by design there is no separate verdict call."
Otherwise the existing text now ends "See Evidence limitations."

## Callers reached
The B0 condition call passes `by_design=True`.
The backstop caller in `assemble_review` keeps the default and so gets the new "See Evidence limitations." ending.

## Tests
`test_b0_verdict_rationale_says_the_rule_verdict_is_by_design` in `tests/test_b0_condition.py`.
`test_fallback_verdict_rationale_wording` in `tests/test_ingest_verify_report.py`.
Both were red before the edit.

## Gates
Targeted files: 32 passed.
Ruff: All checks passed!
Full suite: 2012 passed, 1 skipped, 2 xfailed.
Selftest: selftest passed.

Pushed by the gate worker after the builder was stopped; no verifier because the change is wording plus tests.
