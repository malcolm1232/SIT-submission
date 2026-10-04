# Synthetic eval item: Customer Consent and Preference Service

`design_v1.md` is the detailed design for Izin, the customer consent and preference service of a fictional Singapore telco-and-retail group, "Merbau Group" (v1.0, about 8,500 words, 30 numbered sections, FR and NFR IDs).
Its structure follows the other synthetic items: requirements, principles, architecture, flows, data model, confirmed decisions, pending backlog, acceptance criteria, readiness assessment and build phases.
The service records PDPA consent per purpose for about 8.7 million customers of the group's mobile, fibre, retail and loyalty businesses, captured in web, app, contact centre, stores and two partner channels.
It covers the purpose catalogue and notice versions, the consent record model, withdrawal and its propagation over Kafka to marketing, analytics, CRM and partner systems, an Eligibility API, Do Not Call (DNC) Registry checks, consent receipts, retention, the regulator evidence export, data residency and partner data sharing, and migration of the legacy marketing flags.
The company, its people, products and partners (Seri Assurance, Lintang Bank) are invented; only public technologies (AWS, Aurora PostgreSQL, Amazon MSK and Kafka, an OIDC identity provider) and public regulator rules are named.

The document contains 14 planted flaws (4 critical, 6 major, 4 minor) across all eight taxonomy categories, including one quantitative claim you can check against public PDPC documentation (F05, the validity period of DNC Registry results).
It also has five deliberately sound sections that a good reviewer should leave alone.
`design_v2.md` (v1.1, about 9,000 words) simulates an updated artefact for re-review: 7 flaws are fixed (F01, F02, F04, F05, F06, F11, F12), the F05 fix introduces one new critical regression (F15, DNC results older than 21 days served until the next successful refresh), and the other 7 flaws are unchanged.
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
| `answer_key.json` | Sealed key: flaws F01 to F14 plus v2 regression F15 (all in `flaws[]`), sound sections, v2 change map, `authoring_drafts` (core insights, anchor quotes with pages, dispositions, approved decisions, external facts; unsigned) |
| `answer_key.canonical.json` | The same key in the canonical schema, written by `spec/convert_answer_keys.py` |

## Flaw summary (sealed)

| ID | Severity | Category | Area | Where |
|---|---|---|---|---|
| F01 | critical | internal_contradiction | lawful basis | 25 against P2, FR-2 |
| F02 | critical | scalability_failure_mode | withdrawal propagation | 14.2 with 14.3, 15 |
| F03 | critical | internal_contradiction | evidence and record retention | 19 against NFR-5, 20, P3 |
| F04 | critical | security_privacy_gap | security | 17 |
| F05 | major | unjustified_quantitative_claim | DNC compliance | 16 |
| F06 | major | unjustified_quantitative_claim | capacity | 24.2 |
| F07 | major | missing_or_unverifiable_requirement | cross-border transfer | 22 against 4, 5, NFR-7 |
| F08 | major | security_privacy_gap | privacy | 14.3 with 14.2 against P7, NFR-6 |
| F09 | major | missing_or_unverifiable_requirement | number recycling | 8 against 4 |
| F10 | major | scalability_failure_mode | withdrawal propagation | 14.4 against NFR-2 |
| F11 | minor | ambiguous_requirement | requirement clarity | FR-9, 17 |
| F12 | minor | acceptance_criterion_cannot_validate | testability | 28.2 (NFR-2) |
| F13 | minor | decision_depends_on_pending_item | requirement conflict | DEC-09 against PB-03 |
| F14 | minor | internal_contradiction | sizing | 24.3 against 1 |
| F15 (v2) | critical | scalability_failure_mode | DNC compliance | v2 Section 16 |

Sound sections: 7 Purpose Catalogue and Notice Versioning, 9 Consent Record Model, 10 Capture in Web and App, 13 Withdrawal Semantics, 23 Resilience and Disaster Recovery.

## External fact

F05 and F15 rest on the PDPC Advisory Guidelines on the Do Not Call Provisions (revised 1 February 2021), fetched on 2026-10-04 from https://www.pdpc.gov.sg/-/media/Files/PDPC/PDF-Files/Advisory-Guidelines/Advisory-Guidelines-on-the-DNC-Provisions-1-Feb-2021.pdf.
The guidelines say the prescribed duration for checking with the DNC Registry before sending a specified message is 21 days, and that results received from 1 February 2021 onwards are valid for 21 days from receipt.
Version 1.0 of the design states 30 days; version 1.1 states 21 days.

## How to regenerate the PDFs and the canonical key

`eval/build_pdfs.py` and `spec/convert_answer_keys.py` list their items in code, and this item is not yet registered in them (nor in `eval/prereg.yaml`; one later change registers all new items).
Until then, both were run unchanged on disk with this item added to their lists in memory only, from the repository root:

- PDFs: `eval/build_pdfs.py` with `ITEMS = ["consent_service"]`. Last rebuilt 2026-10-04: `design_v1.pdf` 17 pages, `design_v2.pdf` 18 pages, all probe checks passed.
- Canonical key: `spec/convert_answer_keys.py --tier synthetic --verify-anchors` with `("synthetic", "consent_service", "synthetic_json_v0")` in `ITEMS` and `"consent_service": {"F05", "F15"}` in `NEEDS_EXTERNAL`. Result: 0 keys failed validation, all 15 flaw anchor quotes and 12 approved-decision anchor quotes exact and unique on their recorded pages, `scored_run_ready` false (owner sign-off pending).

When the item is registered, add those two entries to the scripts and `consent_service` to `ITEMS` in `eval/build_pdfs.py`.
`scripts/leakage_grep.py` prints PASS with this item present.

## Checklist: no flaw is labelled in the documents

- [x] Neither document contains a flaw ID or the words "flaw", "planted", "intentional", "deliberate", "bug", "TODO", "FIXME", "incorrect", "mistake", "wrong", "regression", "known issue" or "answer key". Command, run from this folder: `grep -ciE '\bF[0-9]{2}\b|flaw|planted|intentional|deliberate|bug|TODO|FIXME|incorrect|mistake|wrong|regression|known issue|answer key' design_v1.md design_v2.md`, output `design_v1.md:0` and `design_v2.md:0`.
- [x] No flaw sits in a callout, warning box, footnote, strikethrough or comment; every flawed statement is written in the same confident register as the sound text.
- [x] The readiness assessment (Section 29) and build phases (Section 30) do not flag any flawed area as risky; they mark them "Ready", consistent with how the authors present them.
- [x] The v2 revision-history row and the "Changes since version 1.0" section list the changed sections neutrally. They do not say which changes were fixes, and they do not mention F15 or the unchanged flaws.
- [x] Every flaw needs domain reasoning, arithmetic or cross-referencing to detect (for example the 21-day PDPC rule in F05, P2 against the migration rule in F01, Section 4's number quarantine and reassignment against Section 8 in F09, and 3.0 million in an hour against 83 per second in F06).
- [x] No two flaws share a sentence; each flaw has one carrying sentence in v1.
- [x] Severity counts (4 critical / 6 major / 4 minor) and category counts (3 / 2 / 2 / 2 / 2 / 1 / 1 / 1) in `answer_key.json` match `flaw_counts`, as the converter confirms.
- [x] Neither document, the key nor this README contains an em dash.
