# INV-05 redaction fix: worker note

Written 5 Oct 2026 07:29, branch `s4/inv05-redaction` from 280c4b4.
Diagnosis: `docs/transcripts/session6/inv05-diagnosis.md` (branch s4/inv05-diag, f15b2b9).
Ids and counts only; no model text, run folder or transcript was opened.

## Change

Fix commit: 6980c33.
Rule: a URL in the reviewed document's canonical text or in a `doc` or `external` ledger excerpt is ledger-backed; the report keeps it and INV-05 accepts it.
A model-written URL found in neither is still replaced by `[link removed: not in the evidence register]` and disclosed.

- `agent/sit_review_agent/invariants.py`: new `allowed_urls(ledger_entries, document_texts)` (every `url_or_citation`, plus `URL_RE` matches with `rstrip(".,;:")` in doc and external excerpts and in the document texts; inference excerpts are model statements and back nothing) and `quote_in_excerpt`.
- Call site 1: `check_INV_05` (new keyword `texts`, else `_load_texts` from `documents[].text_path`; `check_all` passes its `texts` to INV-05 as it does to INV-04).
- Call site 2: `phases/report.assemble_review` (texts from `ctx.documents`, the same text ingest writes to `text_path`).
- `phases/report._redact` never rewrites `url_or_citation`, `excerpt`, an anchor quote, or a doc or external quote that occurs in its ledger excerpt (as `settle_refs` skips `quote` and `excerpt`); inference quotes and free text are still redacted.
- `docs/ARCHITECTURE.md` section 6: two sentences stating the rule.

## Tests (5 new)

- `tests/test_invariants.py::test_inv05_accepts_a_url_of_the_cited_excerpt_and_of_the_document` (a): excerpt and quote share a URL, passes; a statement URL found only in the document passes with the text and fails without it; a made-up statement URL still fails (exactly one problem).
- `tests/test_invariants.py::test_allowed_urls_ignores_inference_statements`.
- `tests/test_adversarial_invariants.py::test_inv05_document_url_in_a_cited_passage_and_an_anchor_is_kept[cited-by-shard-and-refine]` (b) and `[anchor-only]` (c): fixture page 6 gets a sentence holding a URL; a fake shard cites it as doc evidence and as a second anchor, a fake refine revision cites the same EV with the register's `[link removed]` form; the report is written, both citations' quotes equal the excerpt and hold the URL, INV-04 and INV-05 pass, no link-removed degradation, no `link removed` in report.json.
- `tests/test_ingest_verify_report.py::test_redact_never_rewrites_a_verbatim_quote`: with an empty allowed set, the anchor quote, the contained doc quote and the excerpt keep the URL; an external quote not in its excerpt, an inference quote and a statement are redacted (3 replacements).
- (d) BEH-04 `test_inv05_model_written_url_and_unknown_evidence_id` unchanged and passing.

## Evidence

- Unfixed code (280c4b4 files) with the new e2e tests: both fail, no report; problems 2 x `INV-04 ... anchor p6 s4.1 unresolved (not_found)` (the latent twin) and 2 x `INV-05 ... evidence EV-005 quote not in the ledger excerpt` (the d_hospital_v1_1 crash shape).
- Mutation 1, the excerpt and document URLs removed from `allowed_urls`: 4 failed (the two unit tests and both e2e cases), 72 passed; restored, `cmp` identical, tree clean.
- Mutation 2, the verbatim-quote exemption removed from `_redact`: 1 failed (`test_redact_never_rewrites_a_verbatim_quote`); restored, `cmp` identical, tree clean.

## Gates at 6980c33

- `ruff check agent harness tests`: All checks passed.
- Full suite: 1990 passed, 1 skipped, 2 xfailed.
- `sit-review selftest`: selftest passed.
- `make smoke`: exit 0 (256 passed, 1 skipped).
- `scripts/leakage_grep.py`: PASS; `sit_review_agent.prompts --check`: lock up to date.
- Load before each run: 5-minute average 6.9 to 8.1, free memory 44 to 49 percent.

## Not done

- A quote that ends inside a URL (the model quoted part of an excerpt and cut the URL) holds a URL prefix that is in no set; the redaction keeps it (verbatim) and INV-05 would still flag it. Verify replaces a quote only when it is not in the excerpt, so such a prefix can reach the report. Not seen in any run; left as is.
- The register shown to the model still hides URLs (`_model_calls.evidence_vars`, by design: "Never the URL"); verify's copy of the excerpt covers the resulting quote mismatch.
- Not pushed; a verifier pushes.
