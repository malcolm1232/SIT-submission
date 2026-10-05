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

## Repair after the verifier's rejection (5 Oct 2026 07:50)

Two findings of the verifier, from its probes (scripted fake model answers, no live call):
1. Anchor hole: when a doc citation's quote is not in the document, `ResolveEvidence.doc_entry` records the finding's first anchor quote as the doc ledger excerpt, so a doc excerpt can be model text. `allowed_urls` read every doc excerpt, so a made-up URL in a made-up anchor became ledger-backed: at 88abd54 the probe wrote report.json with `made-up.example` three times and INV-05 passing (280c4b4 crashed fail-closed instead).
2. Cut URL: a quote that ends partway through a URL is a substring of its excerpt, so `_redact` keeps it and INV-05's scan failed the run on the cut URL (`https://rooms.campus.example/sta`).

### Commit e0c7925: a doc excerpt never backs a URL

- `allowed_urls` sources now: every `url_or_citation`, URLs in `external` excerpts (the tool result's text) and URLs in the canonical document texts. Never a doc excerpt, never an inference excerpt. A real doc excerpt's URL is in the document text anyway.
- `test_inv05_accepts_a_url_of_the_cited_excerpt_and_of_the_document` and `test_allowed_urls_ignores_inference_statements` assert the new rule (an excerpt URL passes only with the document text holding it; external excerpt URLs count).
- New `tests/test_adversarial_invariants.py::test_inv05_made_up_url_in_a_made_up_anchor_never_reaches_the_report` (the verifier's probe): the run ends fail-closed in the report phase, the only problem is `INV-05: URL/DOI in report text not in the ledger: https://made-up.example/paper`, and no report.json holds the URL. Fail-closed rather than redact: the kept quote equals a ledger excerpt holding the URL, and the ledger is not redacted, so redaction could not keep the URL out of report.json.
- ARCHITECTURE section 6: doc URLs are backed by the document text, external URLs by the tool result, and a doc excerpt is not itself a source of allowed URLs.
- Mutation: doc excerpts re-allowed in `allowed_urls`: 3 failed (the regression test and both unit tests); restored, `cmp` identical.

### Commit 2ef95e4: a quote cut inside a backed URL

- New `invariants.quote_backed_by_excerpt(quote, excerpt, allowed)`: the quote occurs in its excerpt and every URL of that excerpt is allowed. INV-05's URL scan skips such a doc or external `quote`; every other string (statements, anchors, other quotes) is scanned as before. The unused `_strings` helper went with it.
- `_redact` is unchanged: it still never rewrites a quote that occurs in its excerpt (rewriting would break the excerpt match). Where `_redact` keeps a quote that INV-05 does not exempt (an excerpt with an unbacked URL), the run fails closed, by design; that is the anchor-hole case above.
- Tests: `test_inv05_quote_cut_inside_a_document_url_is_kept` (end to end, a refine revision quotes the URL passage cut inside the URL: report written, every invariant passes, no `link removed`); `tests/test_invariants.py::test_inv05_quote_cut_inside_a_url_passes_only_when_the_excerpt_urls_are_backed` (backed excerpt passes; the mirror with the URL in no document fails on the cut URL; a quote with a URL of its own still fails).
- Mutations: exemption removed: 2 failed (both cut-URL tests); the "every excerpt URL allowed" condition removed: 3 failed (the anchor-hole regression test among them). Restored, `cmp` identical.

### Commit 3 (marker on a model-anchor doc entry): skipped

`LedgerEntry` is a `SpecModel` (`extra="forbid"`) and `spec/finding.schema.json` `$defs/LedgerEntry` is `additionalProperties: false` with all twelve fields required. No existing field fits: `title` is the source title, and `read_before_cite` is the audit C11 flag for fetched content (explain.py prints it; overloading it for doc entries would change its meaning). A new `excerpt_source` field would ripple into the spec schema, `tests/fixtures/review_example.json`, `spec/README.md` and the harness grader (`harness/sit_eval/grader/projection.py`, `validation.py`), a spec contract change. Since `allowed_urls` no longer reads doc excerpts, the marker is traceability only; left for a spec change on his word.

### Not done

- An anchor quote (INV-04, fuzzy match at 0.90) that ends inside a URL of the document is still scanned by INV-05 and would fail closed; the exemption covers doc and external citation quotes only, as briefed. Not seen in any run.
- A document URL broken across a line in the canonical text is not one URL match there, so a quote holding it whole is not backed. Not seen in any run.

### Gates at 2ef95e4 (code), before the note commit

- `ruff check agent harness tests`: All checks passed.
- Full suite: 1993 passed, 1 skipped, 2 xfailed.
- `sit-review selftest`: selftest passed.
- `make smoke`: exit 0 (256 passed, 1 skipped).
- `scripts/leakage_grep.py`: PASS; `sit_review_agent.prompts --check`: PROMPTS.lock up to date (bundle 2569a967015b).
- `tests/robustness`: 161 passed.
- Load before each run: 5-minute average 4.7 to 6.0, free memory 42 to 48 percent.
- Not pushed; the verifier re-checks.

### Follow-up: a URL whose letter case changed in a quote

- The verifier's probe: a refine revision quotes the document's URL passage with the URL path as `/STATS/Peak-Weeks` (the document has `/stats/peak-weeks`). `quote_in_excerpt` folds case, so verify kept the quote, `_redact` left it, INV-05's URL scan skipped it, and report.json carried a URL the document does not have. At 280c4b4 the same input failed closed.
- New `invariants.quote_urls_in_excerpt(quote, excerpt)`: every URL or DOI of the quote is, in exact case, a URL of the excerpt or the start of one (the cut-URL case). `quote_backed_by_excerpt` now requires it as well; prose outside URLs stays case-insensitive.
- `_redact` keeps its rule (a quote in its excerpt is never rewritten) and its docstring now names the case. Making it strict too was tried: the URL is then rewritten to the link-removed text and the run fails on `quote not in the ledger excerpt`, which hides the URL instead of naming it. Kept-and-scanned is what makes INV-05 name it.
- Tests: `tests/test_adversarial_invariants.py::test_inv05_url_case_change_in_a_quote_fails_closed` (end to end: fail-closed in the report phase, no report.json, the only problem is INV-05 naming `https://rooms.campus.example/STATS/Peak-Weeks`); `tests/test_invariants.py::test_inv05_quote_urls_must_match_their_excerpt_in_exact_case` (whole and cut URL in matching case pass with case-folded prose; the same with a path case change fails; `check_INV_05` names the URL). The existing backed and cut-URL tests still pass.
- Mutation: URL match made case-insensitive: 2 failed (both new tests); restored, `cmp` identical.
- Not covered: `URL_RE` matches only a lowercase `http`/`https` scheme, so `HTTPS://...` anywhere in report text is not seen as a URL by the redaction or by INV-05. Not seen in any run.
- Gates: ruff All checks passed; full suite 1995 passed, 1 skipped, 2 xfailed; selftest passed; `make smoke` exit 0; leakage grep PASS; PROMPTS.lock up to date; `tests/robustness` 161 passed. One full-suite run had a single failure in `tests/test_ui_export_bundle.py::test_the_sidebar_in_a_browser_and_every_section_without_script` (unrelated; passed 6 of 6 alone and on the rerun; it reads `all_inner_texts()` and `is_visible()` right after clicks without waiting, a likely race under load).
