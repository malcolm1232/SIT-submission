# Repair fallback (refine keep-good, failed repair call)

Base: 5653c0e on claude/happy-darwin-d0bl94.
Change: a repair call for the failing refine revisions that fails on the schema or with another model error returns the kept revisions (`PhaseCall.repair_error`) instead of raising; refine applies them and discloses the failure.
A persistent refusal of that repair call no longer adds refine to `declined_sections` when kept revisions were applied; refine adds it itself when nothing was applied.
A failure of the first call, and code-bug errors (FakeScriptExhausted, EffortChangedError, LLMBadRequestError), still raise.

Tests added in tests/test_refine_keep_good.py: 4 (schema failure of the repair, transport failure of the repair, first call off the schema still raises, declined repair keeps the 54 and refine is not declined).

Gates:
- ruff: All checks passed.
- full suite: 1965 passed, 1 skipped, 2 xfailed (1961 before plus 4).
- selftest: passed.
- PROMPTS.lock: up to date (bundle 6f0ee28ab9ac); no prompt changed.

Mutation: restoring the `raise` for the repair call's schema error fails the schema-failure test (1 failed, 12 passed); the file was restored byte for byte (cmp identical).
