# Worker note: INV-05 edges (5 Oct 2026)

Branch s4/inv05-edges from 20b12be, one commit per edge, each test written red first.

## E1 - a quote that ends inside a document URL (b5a1533)

New `quote_in_document` in invariants.py: a quote that is a contiguous run of a reviewed document's text (whitespace and case folded, each URL an exact-case URL of that text or its start) is exempt from INV-05's URL scan, for anchor and evidence quotes alike.
Tests: `test_inv05_quote_that_ends_inside_a_document_url_is_backed_by_the_document` (unit) and `test_inv05_anchor_quote_that_ends_inside_a_document_url_is_kept` (run_review; red was the StageCrash naming the cut URL).
Mutation: removing the `quote_in_document` clause fails both tests; restored, cmp identical.

## E2 - a URL the document breaks across lines (a9ccb16)

New `_broken_urls` feeds `allowed_urls`: a document URL that runs to a line end is joined with the next line, both with its last character kept and with a break hyphen dropped.
No ledger or finding field records which form matched, and none was added.
Tests: `test_inv05_url_the_document_breaks_across_lines_is_backed` (unit, 3 forms) and `test_inv05_url_the_document_breaks_across_lines_is_kept` (run_review, 3 forms).
Mutation: without `_broken_urls` 5 of 6 fail (the run-level break-hyphen case already passed, because ingest's de-hyphenation joins it); without the hyphen-dropped form the unit break-hyphen case fails; restored, cmp identical.
Finding: ingest's `normalise` drops a hyphen at a line end between two lower-case letters, so a real URL hyphen there ("peak-\nweeks") is lost before any invariant reads the text; the run-level URL-hyphen case therefore breaks before a digit.

## E3 - redaction inside a quote INV-05 did not exempt (b51de7a)

`report._redact` now keeps a quote only when it is an anchor or `quote_exempt` (the one predicate INV-05's scan uses); any other quote has its disallowed URLs replaced by the link-removed marker.
INV-05 accepts such a quote when it matches its excerpt with each marker read as the excerpt's URL in that place (`excerpt_urls_behind_removed_links`), and names that excerpt URL when it is not allowed, so a made-up URL the register carries still fails closed.
`LINK_REMOVED` moved to invariants.py (report.py imports it); ARCHITECTURE.md and EXPLAIN_AS_IT_RUNS.md updated.
Tests: `test_report_redaction_covers_a_url_inside_a_quote_inv05_does_not_exempt` (new); `test_inv05_url_case_change_in_a_quote_fails_closed` became `test_inv05_url_case_change_in_a_quote_is_redacted` and `test_redact_never_rewrites_a_verbatim_quote` now expects the non-exempt doc quote redacted (both asserted the old E3 behaviour).
`test_inv05_made_up_url_in_a_made_up_anchor_never_reaches_the_report` is unchanged and green.
Mutation: the old `_verbatim_quote` rule fails the 3 E3 tests; dropping the allowed check on excerpt URLs fails the made-up-anchor test; restored, cmp identical.

## Gates (last lines)

ruff: All checks passed!
pytest: 2021 passed, 1 skipped, 2 xfailed.
selftest: selftest passed.
robustness: 161 passed.

## Not verified

No live model run and no rerun of a recorded run; the edges are shown on fixtures and the scripted selftest pipeline only.
A made-up URL in an inference ledger excerpt is still not scanned by INV-05 (unchanged, not in scope).
Anchor quotes are never redacted, so an anchor that is not a run of the document and holds a disallowed URL still fails closed.
