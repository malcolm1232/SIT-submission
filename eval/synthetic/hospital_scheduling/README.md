# Synthetic eval item: Hospital Clinic and Theatre Scheduling Platform

`design_v1.md` is the detailed design for the clinic and theatre scheduling platform of a fictional Malaysian private hospital group, "Bayu Kasih Healthcare" (Jadwira v1.0, about 8,300 words, 30 numbered sections, FR and NFR IDs).
Its structure follows the other synthetic items: requirements, principles, architecture, flows, data model, confirmed decisions, pending backlog, acceptance criteria, readiness assessment and build phases.
The platform books about 2.6 million outpatient appointments a year across six hospitals through a web portal, a mobile app and a group call centre, schedules 52 operating theatres with surgeon and anaesthetist rosters, allocates beds and shared theatre equipment, sends SMS and WhatsApp reminders, and integrates with the EMR and billing over HL7 FHIR R4, all in AWS ap-southeast-5 on Aurora PostgreSQL, Amazon MSK and ECS.
The group, its hospitals, its people, its EMR and billing suppliers (Ombak, Kirana) and its SMS aggregator (Lintas Mesej) are invented; only public technologies, public standards and public vendor limits are named.

The document contains 14 planted flaws (4 critical, 6 major, 4 minor) across all eight taxonomy categories, including one quantitative claim you can check against public SMS documentation (F06, the single-message character limit for non-GSM alphabets).
It also has five deliberately sound sections that a good reviewer should leave alone.
`design_v2.md` (v1.1, about 9,200 words) simulates an updated artefact for re-review: 7 flaws are fixed (F01, F02, F04, F05, F06, F09, F11), the F04 fix introduces one new critical regression (F15, the FHIR Bridge retry topic lets a delayed old event overwrite a newer reschedule or cancellation in the EMR), and the other 7 flaws are unchanged.
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
| F01 | critical | security_privacy_gap | privacy, security | 11.2 with 20.1 and 21 |
| F02 | critical | scalability_failure_mode | safety, data integrity | 13.2 with 20.1 |
| F03 | critical | internal_contradiction | patient safety | 9.3 against P3 |
| F04 | critical | scalability_failure_mode | data integrity | 17.3 |
| F05 | major | internal_contradiction | recovery | NFR-6 against 23.3 |
| F06 | major | unjustified_quantitative_claim | messaging, cost | 11.3 with 24.2 |
| F07 | major | missing_or_unverifiable_requirement | patient safety | 15.1 against FR-11 and P5 |
| F08 | major | security_privacy_gap | privacy | 22.2 against NFR-5 and P6 |
| F09 | major | acceptance_criterion_cannot_validate | testability | 28.2 (NFR-3) |
| F10 | major | decision_depends_on_pending_item | plan | DEC-08 against PB-03 |
| F11 | minor | internal_contradiction | requirement conflict | 10.2 against 11.1 |
| F12 | minor | unjustified_quantitative_claim | sizing | 20.2 |
| F13 | minor | missing_or_unverifiable_requirement | requirement gap | FR-8 |
| F14 | minor | ambiguous_requirement | requirement clarity | FR-6 |
| F15 (v2) | critical | scalability_failure_mode | data integrity | v2 Section 17.3 against 16 and 18 |

Sound sections: 8 Outpatient Slot Model, 12 Consultant Sessions, Leave and Bulk Rescheduling, 16 Event Bus and Transactional Outbox, 18 FHIR Resource Mapping, 19 Time, Calendars and Public Holidays.

## How to regenerate the PDFs and the canonical key

`eval/build_pdfs.py` and `spec/convert_answer_keys.py` list their items in code, and this item is not yet registered in them (nor in `eval/prereg.yaml`; one later change registers all new items).
Until then, both were run unchanged on disk with this item added to their lists in memory only, from the repository root:

- PDFs: `eval/build_pdfs.py` with `ITEMS = ["hospital_scheduling"]`. Last rebuilt 2026-10-05 after the cold read: `design_v1.pdf` 16 pages, `design_v2.pdf` 17 pages, all probe checks passed.
- Canonical key: `spec/convert_answer_keys.py --tier synthetic --verify-anchors` with `("synthetic", "hospital_scheduling", "synthetic_json_v0")` in `ITEMS` and `"hospital_scheduling": {"F06", "F15"}` in `NEEDS_EXTERNAL`. Result: 0 keys failed validation, all 15 anchor quotes exact and unique on their recorded pages, `scored_run_ready` false (owner sign-off pending).

When the item is registered, add those two entries to the scripts and `hospital_scheduling` to `ITEMS` in `eval/build_pdfs.py`.
With this item present, `scripts/leakage_grep.py` reports one unresolved hit, the generic pair `never leave` from the payments item against `agent/sit_review_agent/tools/gateway.py`, the same hit the iot_fleet item surfaced; it needs an allow-list entry in the registering change.
Terms from this item that the script flagged (`Loader`, `still fails`, `acceptance criterion`) were reworded in both designs and the key before this README was written.

## Checklist: no flaw is labelled in the documents

- [x] Neither document contains a flaw ID or the words "flaw", "planted", "intentional", "deliberate", "bug", "TODO", "FIXME", "incorrect", "mistake", "wrong", "regression", "known issue" or "answer key". Command, run from this folder: `grep -ciE '\bF[0-9]{2}\b|flaw|planted|intentional|deliberate|bug|TODO|FIXME|incorrect|mistake|wrong|regression|known issue|answer key' design_v1.md design_v2.md`, output `design_v1.md:0` and `design_v2.md:0`.
- [x] No flaw sits in a callout, warning box, footnote, strikethrough or comment; every flawed statement is written in the same confident register as the sound text.
- [x] The readiness assessment (Section 29) and build phases (Section 30) do not flag any flawed area as risky; they mark them "Ready", consistent with how the authors present them.
- [x] The v2 revision-history row and the "Changes since version 1.0" section list the changed sections neutrally. They do not say which changes were fixes, and they do not mention F15 or the unchanged flaws.
- [x] Every flaw needs domain reasoning, arithmetic or cross-referencing to detect (for example the 70-character UCS-2 limit in F06, Section 9.3 against P3 in F03, the 24-hour reminder against the 12:00 release in F11, the 40 x 2.6 million product in F12, and Section 16's per-aggregate ordering against the v2 retry topic in F15).
- [x] No two flaws share a sentence; each flaw has one carrying sentence in v1.
- [x] Severity counts (4 critical / 6 major / 4 minor) and category counts (3 / 2 / 2 / 2 / 2 / 1 / 1 / 1) in `answer_key.json` match `flaw_counts`, as the converter confirms.
- [x] Neither document, the key nor this README contains an em dash.
