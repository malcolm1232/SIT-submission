# Synthetic eval item: Merchant Payment Orchestration Platform

`design_v1.md` is the detailed design for a merchant payment orchestration platform at a fictional Southeast Asian fintech, "Serindit Pay" (v1.0, about 8,200 words, 28 numbered sections, FR and NFR IDs). Its structure follows the SIT Memory Platform detailed design: requirements, principles, architecture, flows, data model, confirmed decisions, pending backlog, acceptance criteria, readiness assessment and build phases. The platform routes card, e-wallet and bank-transfer payments for about 15,000 merchants at about 2,000 TPS peak, covering retries, idempotency, reconciliation, PCI DSS scoping, a fraud hook and a merchant admin plane.

The document contains 14 planted flaws (4 critical, 6 major, 4 minor) across eight categories, including one quantitative claim you can check against public AWS DynamoDB documentation. It also has five deliberately sound sections that a good reviewer should leave alone. `design_v2.md` (v1.1, about 8,900 words) simulates an updated artefact for re-review: 6 flaws are fixed (F02, F03, F04, F06, F08, F12), the F04 fix introduces one new critical regression (F15, a cross-region idempotency race), and the other 8 flaws are unchanged. In `v2_changes`, the six fixed flaws all have status `fixed`; the one whose fix introduced the regression also carries `introduced_new_flaw_id: "F15"`. F15 is listed in `flaws[]` with `introduced_in: "v2"` and `introduced_by_fix_of`.

**How to use it:** give the agent one design document (Markdown or PDF) with no other context. Grade its findings against `answer_key.json` by substance, using the `what_a_correct_finding_must_mention` field, not exact wording. Count recommendations made against `sound_sections` as false positives (each entry has a `trap` field). For the re-review scenario, run v1 then v2 and score against `v2_changes` and `expected_v2_open_flaws`. The agent should report fixed items as resolved, keep reporting unchanged ones, and catch F15. Keep `answer_key.json` and this README sealed from the agent under test.

## Files

| File | Purpose |
|---|---|
| `design_v1.md` / `design_v1.pdf` | Artefact under review, v1.0 (14 flaws) |
| `design_v2.md` / `design_v2.pdf` | Updated artefact, v1.1 (6 fixed, 1 regression, 8 unchanged) |
| `answer_key.json` | Sealed key: flaws F01–F14 plus v2 regression F15 (all in `flaws[]`), sound sections, v2 change map |

How to regenerate the PDFs: run `python3 eval/build_pdfs.py` from the repository root. It applies one pipeline to all six synthetic PDFs (python-markdown with the `tables`, `fenced_code` and `sane_lists` extensions → HTML with a fixed embedded stylesheet → LibreOffice headless, `HTML (StarWriter)` import and `writer_pdf_Export`) and then checks each PDF's extracted text against its Markdown; `--check` verifies without rebuilding. Last rebuilt 2026-10-02: `design_v1.pdf` 21 pages, `design_v2.pdf` 22 pages. LibreOffice Writer must be installed (`libreoffice-writer-nogui` on a core-only install).

## Checklist: no flaw is labelled in the documents

- [x] Neither document contains the words "flaw", "planted", "bug", "known issue", "TODO", "FIXME", "regression", "answer key", or any flaw ID (F01–F15). Checked with a case-insensitive grep that returned 0 matches in both files.
- [x] No flaw sits in a callout, warning box, footnote, strikethrough or comment; every flawed statement is written in the same confident register as the sound text.
- [x] The readiness assessment (Section 27) and build phases (Section 28) do not flag any flawed area as risky. Where they reference the flawed areas they mark them "Ready", which is consistent with how the authors present them.
- [x] The v2 revision-history table lists changed sections neutrally, as a real revision log would. It does not say which changes were fixes, and it does not mention F15 or the unchanged flaws.
- [x] Every flaw needs domain reasoning or cross-referencing between sections to detect (for example, the ICT to SGT conversion in F02, Section 10.5 against Section 21.1 in F05, and the Redis key against Principle P3 in F09).
- [x] Severity counts (4 critical / 6 major / 4 minor) and category counts (3 / 2 / 2 / 2 / 2 / 1 / 1 / 1) in `answer_key.json` match the brief.
