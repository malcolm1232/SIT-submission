# Synthetic eval item: IoT Fleet Telematics and Cold-Chain Platform

`design_v1.md` is the detailed design for the telematics and cold-chain platform of a fictional Southeast Asian logistics company, "Rimbun Logistics" (ArusFleet v1.0, about 8,900 words, 30 numbered sections, FR and NFR IDs).
Its structure follows the other synthetic items: requirements, principles, architecture, flows, data model, confirmed decisions, pending backlog, acceptance criteria, readiness assessment and build phases.
The platform connects about 8,700 gateways (6,400 trucks and 2,300 reefer trailers) in Malaysia, Singapore, Thailand and Indonesia over MQTT and cellular to AWS IoT Core, Amazon MSK and Aurora PostgreSQL.
It covers offline buffering and backfill, geofencing, driver behaviour scoring, remote commands, over-the-air firmware updates, cold-chain excursion rules and alerting, a dispatcher console, consignee tracking links, data retention and the audit pack that pharmaceutical customers and GDP inspectors request.
The company, its people and its supplier (Halcyon Telematics) are invented; only public technologies and public vendor limits are named.

The document contains 14 planted flaws (4 critical, 6 major, 4 minor) across all eight taxonomy categories, including one quantitative claim you can check against public AWS IoT Core documentation (F03, the MQTT payload limit).
It also has five deliberately sound sections that a good reviewer should leave alone.
`design_v2.md` (v1.1, about 9,500 words) simulates an updated artefact for re-review: 7 flaws are fixed (F02, F03, F04, F06, F08, F10, F12), the F03 fix introduces one new critical regression (F15, backfill chunks published at QoS 0 and freed on socket write), and the other 7 flaws are unchanged.
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
| F01 | critical | security_privacy_gap | security, safety | 14.2, 14.3 |
| F02 | critical | scalability_failure_mode | safety | 13.3 |
| F03 | critical | unjustified_quantitative_claim | data integrity, compliance | 10 |
| F04 | critical | internal_contradiction | compliance, data integrity | 18.2, 18.3 against P3, 5 |
| F05 | major | scalability_failure_mode | scalability | 20.2, 21 |
| F06 | major | scalability_failure_mode | availability | 17.1 |
| F07 | major | security_privacy_gap | privacy | 19.3 against P6, 4 |
| F08 | major | security_privacy_gap | security | 22.2 |
| F09 | major | missing_or_unverifiable_requirement | operability | 17.3 against 5 |
| F10 | major | unjustified_quantitative_claim | cost | 24.2, 24.3 |
| F11 | minor | ambiguous_requirement | requirement clarity | 11.1 |
| F12 | minor | acceptance_criterion_cannot_validate | testability | 28.2 (NFR-4) |
| F13 | minor | decision_depends_on_pending_item | requirement conflict | DEC-06 against PB-03 |
| F14 | minor | internal_contradiction | requirement conflict | 11.2 against 25.3 |
| F15 (v2) | critical | scalability_failure_mode | data integrity, compliance | v2 Section 10 |

Sound sections: 8 Streaming Backbone, 9 Message Envelope Time and Deduplication, 12 Geofencing, 15 Firmware Rollout Waves and Rollback, 16 Cold-Chain Excursion Rules and Mean Kinetic Temperature.

## How to regenerate the PDFs and the canonical key

`eval/build_pdfs.py` and `spec/convert_answer_keys.py` list their items in code, and this item is not yet registered in them (nor in `eval/prereg.yaml`; one later change registers all new items).
Until then, both were run unchanged on disk with this item added to their lists in memory only, from the repository root:

- PDFs: `eval/build_pdfs.py` with `ITEMS = ["iot_fleet"]`. Last rebuilt 2026-10-04 after the cold read: `design_v1.pdf` 17 pages, `design_v2.pdf` 18 pages, all probe checks passed.
- Canonical key: `spec/convert_answer_keys.py --tier synthetic --verify-anchors` with `("synthetic", "iot_fleet", "synthetic_json_v0")` in `ITEMS` and `"iot_fleet": {"F03", "F15"}` in `NEEDS_EXTERNAL`. Result: 0 keys failed validation, all 15 anchor quotes exact and unique on their recorded pages, `scored_run_ready` false (owner sign-off pending).

When the item is registered, add those two entries to the scripts and `iot_fleet` to `ITEMS` in `eval/build_pdfs.py`.
Registering it also changes the corpus for `scripts/leakage_grep.py`: with this item present, the generic pair `never leave` (from the payments item) enters the TF-IDF top terms and is reported against `agent/sit_review_agent/tools/gateway.py`; it needs an allow-list entry in that change.

## Checklist: no flaw is labelled in the documents

- [x] Neither document contains a flaw ID or the words "flaw", "planted", "intentional", "deliberate", "bug", "TODO", "FIXME", "incorrect", "mistake", "wrong", "regression", "known issue" or "answer key". Command, run from this folder: `grep -ciE '\bF[0-9]{2}\b|flaw|planted|intentional|deliberate|bug|TODO|FIXME|incorrect|mistake|wrong|regression|known issue|answer key' design_v1.md design_v2.md`, output `design_v1.md:0` and `design_v2.md:0`.
- [x] No flaw sits in a callout, warning box, footnote, strikethrough or comment; every flawed statement is written in the same confident register as the sound text.
- [x] The readiness assessment (Section 29) and build phases (Section 30) do not flag any flawed area as risky; they mark them "Ready", consistent with how the authors present them.
- [x] The v2 revision-history row and the "Changes since version 1.0" section list the changed sections neutrally. They do not say which changes were fixes, and they do not mention F15 or the unchanged flaws.
- [x] Every flaw needs domain reasoning, arithmetic or cross-referencing to detect (for example the 128 KB AWS limit in F03, Section 5 item 4 and P3 against Section 18.2 in F04, Section 4's take-home trucks against the 30-day link in F07, and the UTC+7 depots against the 00:30 MYT job in F14).
- [x] No two flaws share a sentence; each flaw has one carrying sentence in v1.
- [x] Severity counts (4 critical / 6 major / 4 minor) and category counts (3 / 3 / 2 / 2 / 1 / 1 / 1 / 1) in `answer_key.json` match `flaw_counts`, as the converter confirms.
- [x] Neither document nor this README contains an em dash.
