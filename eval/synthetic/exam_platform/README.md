# Synthetic eval item: National Examinations Registration and Results Platform

`design_v1.md` is the detailed design for the registration and results-release platform of a fictional Thai national examinations board, the "Siam Examinations and Certification Board" (PHON v1.0, about 8,850 words, 30 numbered sections, FR and NFR IDs).
Its structure follows the other synthetic items: requirements, principles, architecture, flows, data model, confirmed decisions, pending backlog, acceptance criteria, readiness assessment and build phases.
The platform registers about 500,000 candidates a year through 3,900 schools and as private candidates, collects fees, allocates venues and seats with special-needs accommodations, tracks 3.5 million scripts from the hall to 42 marking centres, captures marks with double entry, moderates them, computes grades, handles appeals, releases results at 08:00 on one day over web, app and SMS (a spike two orders of magnitude above the daily average), issues and verifies certificates, retains data under the PDPA and reports to the Ministry, all in AWS ap-southeast-7 on Aurora PostgreSQL, RDS, Amazon MSK, API Gateway, CloudFront and Cognito.
The board, the platform, its people, the SMS aggregators (Ratchaphruek Messaging, Dok Bua Telecom), the payment gateway (Chao Phraya Payment Gateway), the analytics provider (Lotus Insight Analytics) and the National Digital Identity Office are invented; only public technologies, public laws and public vendor limits are named.

The document contains 14 planted flaws (4 critical, 6 major, 4 minor) across all eight taxonomy categories, including one quantitative claim you can check against the public AWS API Gateway quotas page (F05, the default account-level throttle in the Asia Pacific (Thailand) Region).
It also has five deliberately sound sections that a good reviewer should leave alone.
`design_v2.md` (v1.1, about 9,400 words) simulates an updated artefact for re-review: 7 flaws are fixed (F01, F03, F04, F07, F08, F11, F12), the F04 fix introduces one new critical regression (F15, results rendered at 02:00 and immutable until 20:00 while clerical corrections are allowed until the 07:00 lock), and the other 7 flaws are unchanged.
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
| F01 | critical | internal_contradiction | marks integrity, appeals | 14.2 against FR-14 and 16.2 |
| F02 | critical | security_privacy_gap | authorisation | 18.2 against NFR-5 and P4 |
| F03 | critical | internal_contradiction | recovery | 24.2 against NFR-6 |
| F04 | critical | scalability_failure_mode | release-day capacity | 25.2 against Section 4 |
| F05 | major | unjustified_quantitative_claim | front-door quota | 25.3 |
| F06 | major | missing_or_unverifiable_requirement | cross-border transfer | 19.3 and DEC-11 |
| F07 | major | internal_contradiction | embargo | 19.1 against 17.1 |
| F08 | major | acceptance_criterion_cannot_validate | testability | 29.1 (FR-8) |
| F09 | major | decision_depends_on_pending_item | plan | DEC-05 against PB-02 |
| F10 | major | scalability_failure_mode | script custody | 11.3 with 22 |
| F11 | minor | ambiguous_requirement | requirement clarity | NFR-3 |
| F12 | minor | unjustified_quantitative_claim | SMS arithmetic | 18.4 against NFR-4 |
| F13 | minor | security_privacy_gap | retention | 23.2 against NFR-7 and P6 |
| F14 | minor | missing_or_unverifiable_requirement | requirement gap | FR-16 |
| F15 (v2) | critical | internal_contradiction | results consistency | v2 Section 25.2 against 16.1 |

Sound sections: 8 Fee Collection and Reconciliation, 9.3 Allocation, 13 Marks Capture with Double Entry, 15 Grade Computation and Grade Boundaries, 20 Certificates and Verification.

## How to regenerate the PDFs and the canonical key

`eval/build_pdfs.py` and `spec/convert_answer_keys.py` list their items in code, and this item is not yet registered in them (nor in `eval/prereg.yaml`; one later change registers all new items).
Until then, both were run unchanged on disk with this item added to their lists in memory only, from the repository root:

- PDFs: `eval/build_pdfs.py` with `ITEMS = ["exam_platform"]`. Last rebuilt 2026-10-04: `design_v1.pdf` 16 pages, `design_v2.pdf` 16 pages, all probe checks passed.
- Canonical key: `spec/convert_answer_keys.py --tier synthetic --verify-anchors` with `("synthetic", "exam_platform", "synthetic_json_v0")` in `ITEMS` and `"exam_platform": {"F05", "F06"}` in `NEEDS_EXTERNAL`. Result: 0 keys failed validation, all 15 anchor quotes exact and unique on their recorded pages, `scored_run_ready` false (owner sign-off pending).

When the item is registered, add those two entries to the scripts and `exam_platform` to `ITEMS` in `eval/build_pdfs.py`.
With this item present, `scripts/leakage_grep.py` reports one unresolved hit, the generic pair `never leave` from the payments item against `agent/sit_review_agent/tools/gateway.py`, the same hit the iot_fleet and hospital_scheduling items surfaced; it needs an allow-list entry in the registering change.
Terms from this item that the script flagged (`schema_version`, `Upper`, `NOT_FOUND`, `another candidate`, `json array`, `Developer`) were renamed in both designs and the key before this README was written.

## Checklist: no flaw is labelled in the documents

- [x] Neither document contains a flaw ID or the words "flaw", "planted", "intentional", "deliberate", "bug", "TODO", "FIXME", "incorrect", "mistake", "wrong", "regression", "known issue" or "answer key". Command, run from this folder: `grep -ciE '\bF[0-9]{2}\b|flaw|planted|intentional|deliberate|bug|TODO|FIXME|incorrect|mistake|wrong|regression|known issue|answer key' design_v1.md design_v2.md`, output `design_v1.md:0` and `design_v2.md:0`.
- [x] No flaw sits in a callout, warning box, footnote, strikethrough or comment; every flawed statement is written in the same confident register as the sound text.
- [x] The readiness assessment and build phases (Section 30) do not flag any flawed area as risky; they mark them "Ready", consistent with how the authors present them.
- [x] The v2 revision-history row and the "Changes since version 1.0" section list the changed sections neutrally. They do not say which changes were fixes, and they do not mention F15 or the unchanged flaws.
- [x] Every flaw needs domain reasoning, arithmetic or cross-referencing to detect (for example the Region footnote on the API Gateway quotas page in F05, Section 14.2 against FR-14 in F01, Section 19.1 against 17.1 in F07, the 375,000 divided by 200 in F12, and v2 Section 25.2 against the unchanged 16.1 in F15).
- [x] No two flaws share a sentence; each flaw has one carrying sentence in v1.
- [x] Every flaw is described as a design property or a missing or broken control, never as a procedure.
- [x] Severity counts (4 critical / 6 major / 4 minor) and category counts (3 / 2 / 2 / 2 / 2 / 1 / 1 / 1) in `answer_key.json` match `flaw_counts`, as the converter confirms.
- [x] Neither document, the key nor this README contains an em dash.
