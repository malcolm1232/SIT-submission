# Synthetic eval item: Core Ledger Migration

`design_v1.md` is the detailed design for the migration of the core general ledger of a fictional Singapore digital bank, "Merbah Bank", from its mainframe batch ledger CORAL to Selasih, an event-sourced ledger service in the cloud (v1.0, about 8,150 words, 30 numbered sections, FR and NFR IDs).
Its structure follows the other synthetic items: requirements, principles, architecture, flows, data model, confirmed decisions, pending backlog, acceptance criteria, readiness assessment and build phases.
The design covers about 2.8 million accounts and 700,000 journals a day: double-entry invariants and idempotent postings, account processing over Amazon MSK, interest accrual and FX revaluation, the end-of-day close and regulatory reporting extracts, maker-checker for manual journals, access control and segregation of duties, a hash-chained audit trail, retention and archive, migration of seven years of history, a dual-run with daily reconciliation, a cut-over with a go/no-go gate and rollback, and disaster recovery across ap-southeast-1 and ap-southeast-3 on Aurora PostgreSQL.
The bank, its products, its people, its systems (CORAL, Selasih) and its extract supplier (Pelita Extract from Rambai Software) are invented; only public technologies, public standards and public vendor limits are named.

The document contains 14 planted flaws (4 critical, 6 major, 4 minor) across all eight taxonomy categories, including one quantitative claim you can check against public Amazon S3 documentation (F05, retrieval times for S3 Glacier Deep Archive).
It also has five deliberately sound sections that a good reviewer should leave alone.
`design_v2.md` (v1.1, about 8,700 words) simulates an updated artefact for re-review: 7 flaws are fixed (F01, F02, F04, F05, F07, F11, F14), the F07 fix introduces one new major regression (F15, a back-dated re-accrual reuses the original accrual's idempotency key and the run treats the 409 as already posted, so interest is reversed and not reposted), and the other 7 flaws are unchanged.
In `v2_changes`, the seven fixed flaws all have status `fixed`; the one whose fix introduced the regression also carries `introduced_new_flaw_id: "F15"`.
F15 is listed in `flaws[]` with `introduced_in: "v2"` and `introduced_by_fix_of`.

**How to use it:** give the agent one design document (Markdown or PDF) with no other context.
Grade its findings against `answer_key.json` by substance, using the `what_a_correct_finding_must_mention` field, not exact wording.
Count recommendations made against `sound_sections` as false positives (each entry has a `trap` field).
For the re-review scenario, run v1 then v2 and score against `v2_changes` and `expected_v2_open_flaws`.
The agent should report fixed items as resolved, keep reporting unchanged ones, and catch F15.
Keep `answer_key.json`, `answer_key.canonical.json` and this README sealed from the agent under test.

## Files

| File | Purpose |
|---|---|
| `design_v1.md` / `design_v1.pdf` | Artefact under review, v1.0 (14 flaws) |
| `design_v2.md` / `design_v2.pdf` | Updated artefact, v1.1 (7 fixed, 1 regression, 7 unchanged) |
| `answer_key.json` | Sealed key: flaws F01 to F14 plus v2 regression F15 (all in `flaws[]`), sound sections, v2 change map, `authoring_drafts` (core insights, anchor quotes with pages, dispositions, external facts; unsigned) |
| `answer_key.canonical.json` | The same key in the canonical schema, written by `spec/convert_answer_keys.py` |

## Flaw summary (sealed)

| ID | Severity | Category | Area | Where |
|---|---|---|---|---|
| F01 | critical | internal_contradiction | posting integrity | 9.2 against P2 and FR-1 |
| F02 | critical | acceptance_criterion_cannot_validate | reconciliation | 22.2 with 23.1 |
| F03 | critical | scalability_failure_mode | cut-over | 23.2 with 4 |
| F04 | critical | security_privacy_gap | segregation of duties | 14.3 against 16, FR-8 and P6 |
| F05 | major | unjustified_quantitative_claim | retention | 19 against NFR-4 |
| F06 | major | internal_contradiction | recovery | NFR-3 against 24.2 |
| F07 | major | scalability_failure_mode | accrual | 12.2 |
| F08 | major | security_privacy_gap | integrity of postings | 17.2 with 9.1 |
| F09 | major | missing_or_unverifiable_requirement | value dating | 14.1 against 4 |
| F10 | major | decision_depends_on_pending_item | plan | DEC-07 against PB-02 |
| F11 | minor | internal_contradiction | plan | 22.1 against 30 |
| F12 | minor | unjustified_quantitative_claim | migration sizing | 21.2 |
| F13 | minor | missing_or_unverifiable_requirement | requirement gap | NFR-5 |
| F14 | minor | ambiguous_requirement | requirement clarity | FR-5 and 13 |
| F15 (v2) | major | scalability_failure_mode | accrual | v2 Section 12.2 with 12.4 and 8 |

Sound sections: 7 Journal Model and Double-Entry Invariants, 8 Posting API and Idempotency, 10 Event Bus and Transactional Outbox, 11 Amounts, Currencies and Rounding, 18 Audit Trail.

## How to regenerate the PDFs and the canonical key

`eval/build_pdfs.py` and `spec/convert_answer_keys.py` list their items in code, and this item is not yet registered in them (nor in `eval/prereg.yaml`; one later change registers all new items).
Until then, both were run unchanged on disk with this item added to their lists in memory only, from the repository root:

- PDFs: `eval/build_pdfs.py` with `ITEMS = ["ledger_migration"]`. Last rebuilt 2026-10-05 (after the cold read): `design_v1.pdf` 15 pages, `design_v2.pdf` 16 pages, all probe checks passed.
- Canonical key: `spec/convert_answer_keys.py --tier synthetic --verify-anchors` with `("synthetic", "ledger_migration", "synthetic_json_v0")` in `ITEMS` and `"ledger_migration": {"F05"}` in `NEEDS_EXTERNAL`. Result: 0 keys failed validation, all 15 anchor quotes exact and unique on their recorded pages, `scored_run_ready` false (owner sign-off pending).

When the item is registered, add those two entries to the scripts and `ledger_migration` to `ITEMS` in `eval/build_pdfs.py`.
With this item present, `scripts/leakage_grep.py` reports one unresolved hit, the generic pair `never leave` from the payments item against `agent/sit_review_agent/tools/gateway.py`, the same hit the earlier new items surfaced; it needs an allow-list entry in the registering change.
The one term from this item that the script flagged (`never applied`, from the key's F03 text) was reworded in the key before this README was written.

## Checklist: no flaw is labelled in the documents

- [x] Neither document contains a flaw ID or the words "flaw", "planted", "intentional", "deliberate", "bug", "TODO", "FIXME", "incorrect", "mistake", "wrong", "regression", "known issue" or "answer key". Command, run from this folder: `grep -ciE '\bF[0-9]{2}\b|flaw|planted|intentional|deliberate|bug|TODO|FIXME|incorrect|mistake|wrong|regression|known issue|answer key' design_v1.md design_v2.md`, output `design_v1.md:0` and `design_v2.md:0`.
- [x] No flaw sits in a callout, warning box, footnote, strikethrough or comment; every flawed statement is written in the same confident register as the sound text.
- [x] The readiness assessment (Section 29) and build phases (Section 30) do not flag any flawed area as risky; they mark them "Ready", consistent with how the authors present them.
- [x] The v2 revision-history row and the "Changes since version 1.0" section list the changed sections neutrally. They do not say which changes were fixes, and they do not mention F15 or the unchanged flaws.
- [x] Every flaw needs domain reasoning, arithmetic or cross-referencing to detect (for example the Deep Archive retrieval tiers in F05, P2 against the per-leg rejection in F01, the 22:00 batch start (the extract's cut-off) against the 00:00 switch in F03, the 2.9 billion over 150,000 division in F12, and Section 12.4's re-accrual against the v2 key and 409 handling in F15).
- [x] No two flaws share a sentence; each flaw has one carrying sentence in v1.
- [x] Severity counts (4 critical / 6 major / 4 minor) and category counts (3 / 2 / 2 / 2 / 2 / 1 / 1 / 1) in `answer_key.json` match `flaw_counts`, as the converter confirms.
- [x] Neither document, the key nor this README contains an em dash.
