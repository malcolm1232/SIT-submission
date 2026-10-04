# Worker note: synthetic item hospital_scheduling (synthetic-hospital-scheduling-001)

Date: 2026-10-04.
Brief: the SIT planner's S4 item-authoring brief under Malcolm's word of 4 Oct 2026 22:40 ("yes" to plan D: ten documents, five of them new), under his delegation of shot calling (3 Oct 02:50).
Branch `s4/item-hospital`; `design_v1.md` was committed by the planner at aab700e from an earlier worker's draft; this worker wrote the key, v2, the PDFs, the canonical key and the README.
Not opened: `eval/blind/`, `docs/live_runs/`, the source of `spec/convert_answer_keys.py` and `eval/build_pdfs.py`, the clinical_rpm and research_lakehouse items.
Read for shape: the payments_orchestration key and README, the iot_fleet README and worker note, the two iot wrappers.

## Process notes

- `eval/build_pdfs.py` and `spec/convert_answer_keys.py` list items in code. Both were run unchanged on disk through scratchpad wrappers copied from the iot_fleet ones (`author_hospital2/build_hospital_pdfs.py`, `author_hospital2/convert_hospital.py`) that add this item to `ITEMS` (and `NEEDS_EXTERNAL = {"F06", "F15"}`) in memory only. The registering worker must add these entries for real.
- The `markdown` module was not in any worktree venv; it was pip-installed into this worktree's `.venv` (an environment change, not a repository change). LibreOffice is `/opt/homebrew/bin/soffice`.
- `design_v2.md` is generated from `design_v1.md` by `author_hospital2/make_v2.py`: 17 exact, single-occurrence replacements (title block, revision history and "Changes since version 1.0" section, then the seven changes and the 17.3 rewrite that carries F15). `answer_key.json` is written by `author_hospital2/make_key.py`, which reads the anchor pages from the PDFs through `sit_review_agent.ingest.pdf.ingest` and asserts each anchor quote is an exact, unique match on its page; every anchor is a fragment of one PDF line so no whitespace normalisation is needed.
- F06's external fact: the planner fetched https://docs.aws.amazon.com/sms-voice/latest/userguide/sms-limitations-character.html on 2026-10-04 ("If your message contains any characters that are outside of the GSM 03.38 character set, it can have up to 70 characters", 67 per part for multipart); recorded with `verified: true`. F15's external fact (FHIR update replaces the whole resource) is recorded with `verified: false`.
- The converter's first run noted the F01, F03 and F10 anchors were under 8 tokens (a note, not a failure); they were lengthened to longer fragments of the same lines.
- `scripts/leakage_grep.py` with this item present first reported, from this item: `Loader` (proper noun, from "Analytics Loader"), `still fails` (TF-IDF pair, 17.3) and `acceptance criterion` (TF-IDF pair, 19 uses in the key and 3 in each design). Renamed: "Analytics Loader" to "Analytics Extract" in both designs; "When a call still fails after three retries" to "When a call has failed three times" (v1 and v2) and "an event that still fails" to "an event whose replays all fail" (v2); "Acceptance criterion" table headers and "its acceptance criterion in Section 28" to "acceptance test" in both designs and throughout the key. After that only `'never leave' (tfidf; from eval/synthetic/payments_orchestration)` against `agent/sit_review_agent/tools/gateway.py:1080` remains, the same hit the iot_fleet item surfaced; reported, not fixed (it needs an allow-list entry in the registering change). The renames changed no anchor quote and no flaw sentence's substance; the PDFs, key and canonical key were regenerated after them.
- Tests: none run (no test enumerates `eval/synthetic/*`, per the iot_fleet note). Not edited: `eval/prereg.yaml`, `eval/build_pdfs.py`, `spec/convert_answer_keys.py`. Nothing pushed.

## Commands (from the worktree root, `S` = the scratchpad folder `author_hospital2`)

    .venv/bin/python $S/make_v2.py
    .venv/bin/python $S/build_hospital_pdfs.py /Users/malco/Desktop/SIT-wt/item-hospital
    .venv/bin/python $S/make_key.py
    PYTHONPATH=agent .venv/bin/python $S/convert_hospital.py /Users/malco/Desktop/SIT-wt/item-hospital --tier synthetic --verify-anchors
    .venv/bin/python scripts/leakage_grep.py

Build output: `design_v1.pdf: 15 pages`, `design_v2.pdf: 17 pages`, `ALL CHECKS PASSED`.
Converter output for this item: `flaws 15 (v1 14, v2 1)`, `v2_status {'fixed': 7, 'unchanged': 7, 'introduced': 1}`, `needs_external_research 2; sound sections 5`, `note: flaw_counts equal to recomputed v1 counts`, `scored_run_ready False`; overall `60 flaws converted across 4 keys; 0 key(s) failed validation`. The other three canonical keys were rewritten byte-identical (git shows no change).

Anchor pages (design_v1 unless stated): F01 7, F02 8, F03 6, F04 10, F05 13, F06 7, F07 9, F08 12, F09 15, F10 14, F11 7, F12 12, F13 3, F14 3, F15 11 (design_v2).

## Word counts (wc -w)

        7990 design_v1.md
        8869 design_v2.md
       16859 total

## No-label scan

    $ grep -ciE '\bF[0-9]{2}\b|flaw|planted|intentional|deliberate|bug|TODO|FIXME|incorrect|mistake|wrong|regression|known issue|answer key' design_v1.md design_v2.md
    design_v1.md:0
    design_v2.md:0

Em dash count (grep -c of U+2014) in both designs, the key, the canonical key, the README and this note: 0 each.

## Per-flaw carrying sentences (v1) and their v2 state

Fixed in v2: F01, F02, F04, F05, F06, F09, F11. Unchanged: F03, F07, F08, F10, F12, F13, F14. New in v2: F15 (from the F04 change).

### F01

- v1: Each reminder carries a manage-booking link of the form `https://book.bayukasih-health.my/b/{booking_no}`, which opens a page showing the patient's full name, the consultant, the specialty clinic, the date and time, and buttons to confirm, cancel or reschedule without signing in.
- v2: Each reminder carries a manage-booking link of the form `https://bkh.my/r/{token}`, where `token` is a random 128-bit value generated for that reminder, stored hashed on the reminder row and valid until the appointment time. The page it opens shows the date and time, the hospital and the clinic, and a confirm button that works in one tap; it shows no name, consultant or specialty. Cancelling or rescheduling from the page requires a one-time code sent to the patient's registered mobile number, or signing in to the portal.

### F02

- v1: The Theatre Service checks the requested theatre, the surgeon and the anaesthetist for overlapping cases against the theatre calendar held in ElastiCache, which the schedule-change consumer refreshes from the event bus, and when it finds no overlap it inserts the case into `theatre_case`.
- v2: The booking itself is decided by the database: the Theatre Service inserts the case into `theatre_case` with its `theatre_id` and a `planned_period` that includes the turnaround, and three exclusion constraints with `btree_gist` on (`theatre_id`, `planned_period`), (`surgeon_id`, `planned_period`) and (`anaesthetist_id`, `planned_period`) reject any case that overlaps another in the same theatre or with the same surgeon or anaesthetist, whatever the cache showed.

### F03

- v1: To keep calls short, the agent searches by the caller's name and date of birth, and when the search returns exactly one patient Temujanji attaches the booking to that patient's MRN without asking for the MyKad number.
- v2: (unchanged)

### F04

- v1: The bridge consumes with automatic offset commits every 5 seconds. When a call has failed three times, the bridge writes the event and the error to its log and continues with the next event, so that one bad record never blocks the partition.
- v2: The bridge commits offsets manually, and only after every FHIR call for an event has succeeded or the event has been handed to the retry path, so that a bridge task that stops mid-event resumes from that event. When a call has failed three times, the bridge publishes the event unchanged, with its original key, to the retry topic `schedule.retry`, commits the offset and continues with the next event in the partition, so that one unreachable record never delays the records behind it.

### F05

- v1: On loss of the ap-southeast-5 Region, the platform is restored in the Cyberjaya data centre from the most recent nightly snapshot onto the group's on-premises PostgreSQL cluster and VMware hosts, which have been sized to run Temujanji at reduced capacity.
- v2: The Cyberjaya data centre holds a continuously updated copy of the scheduling database: a PostgreSQL logical replication publication on the Aurora writer covers every table of Section 20.1, including `outbox` and `booking_audit`, and a subscription on the group's on-premises PostgreSQL cluster applies the changes over Direct Connect. Replication lag is measured every 30 seconds from the subscriber and alarmed at 2 minutes. (The NFR-6 acceptance test in 28.2 now measures the data loss.)

### F06

- v1: Every reminder template, in each of the four languages, is kept within 160 characters, so each reminder is delivered and billed as a single SMS message. The Lintas Mesej account is configured to reject concatenated messages, which keeps the monthly SMS bill predictable and avoids partial deliveries on older handsets.
- v2: The Malay and English templates use only characters of the GSM 03.38 set and are kept within 160 characters, so each goes as a single SMS message. The Chinese and Tamil templates contain characters outside that set, so the aggregator sends them as UCS-2, where a single message holds at most 70 characters and each part of a concatenated message holds 67; the Chinese template therefore goes as two parts and the Tamil template as three, which the handset reassembles into one message. (Section 24.2's SMS line now counts 1.5 parts on average; total RM 2,095,000, margin about 13 percent.)

### F07

- v1: The allocator proposes the first free bed that matches the requested ward, the room class covered by the patient's guarantee letter or deposit, and the patient's sex for shared rooms, and the admissions officer confirms it with one click.
- v2: (unchanged)

### F08

- v1: It copies the previous day's appointment, theatre_case and admission rows, each with the patient's name, MyKad number, phone number, referral reason code and procedure code, into the group analytics bucket in Amazon S3, where every user with the Group Analyst role (about 140 staff across finance, marketing, operations and the clinical quality unit) can query them with Amazon Athena.
- v2: (unchanged)

### F09

- v1: | NFR-3 | In UAT, 2,000 reminders are sent through Lintas Mesej and the WhatsApp Business Platform, and at least 97 percent are accepted by the provider APIs with an HTTP 2xx response. |
- v2: | NFR-3 | In UAT, 2,000 reminders are sent through Lintas Mesej and the WhatsApp Business Platform to test handsets, and for at least 97 percent a delivery receipt (SMS) or a delivered status (WhatsApp) is recorded on the reminder row with a delivery time at least 20 hours before the appointment time; the same measure is reported from the `reminder` table for every reminder in the first month of production. |

### F10

- v1: | DEC-08 | Theatre case booking and session allocation check the surgeon's practising privileges through the Credentialing Service API, from Phase 2 go-live of theatre scheduling | Patient safety; the medical advisory committees require it |
- v2: (unchanged; PB-03 unchanged too)

### F11

- v1: Reminders are sent 48 hours and 24 hours before each appointment, by WhatsApp to patients who have opted in to WhatsApp and by SMS to all others. (against 10.2: An appointment that has not been confirmed by 12:00 on the day before it is released to the waitlist)
- v2: Reminders are sent 72 hours and 36 hours before each appointment, by WhatsApp to patients who have opted in to WhatsApp and by SMS to all others. (10.2 adds: The 36-hour reminder of Section 11.1 reaches every patient between 20:00 two days before and 09:00 on the day before, so every patient has at least three hours after the second reminder in which to confirm before the slot is released.)

### F12

- v1: At about 40 audit rows per appointment and 2.6 million appointments a year, `booking_audit` grows by about 10 million rows a year, so it stays a single unpartitioned table for the full seven-year retention period.
- v2: (unchanged)

### F13

- v1: | FR-8 | Patients receive appointment reminders by WhatsApp or SMS in their preferred language. |
- v2: (unchanged)

### F14

- v1: | FR-6 | Released slots are offered to waitlisted patients in a fair order, with clinically urgent patients given suitable priority. |
- v2: (unchanged)

### F15

- v1: (not present in v1; introduced in v2)
- v2: When a call has failed three times, the bridge publishes the event unchanged, with its original key, to the retry topic `schedule.retry`, commits the offset and continues with the next event in the partition, so that one unreachable record never delays the records behind it. A separate retry consumer replays `schedule.retry` with waits of 1, 5 and 30 minutes between attempts, applying each event exactly as the main consumer would have from the resources built from the event payload, so a replayed event needs no special handling.

## Cold read

Date: 2026-10-05. A fresh-context reviewer read `design_v1.md`, listed the problems it saw, and only then opened the key.
Caveat: the item's README (which the brief listed first) carries the sealed flaw table, so the reader knew the flaw locations before reading v1; the read tested whether each flaw is findable from its section, not whether it is found blind.
Not opened: `eval/blind/`, `docs/live_runs/`, the other synthetic items, and the source of `spec/convert_answer_keys.py` and `eval/build_pdfs.py`.

### Flaws found cold

- Found from the document alone: F01, F02, F03, F04, F05, F07, F08, F09, F10, F11, F12, F14.
- F06 needs the planned external fact (the 70-character single-message limit for non-GSM text); with it, the 96- and 142-character Chinese and Tamil templates are plainly over the limit.
- Missed: F13. The reader saw FR-8 as thin but looked for missing timing or opt-out rules, not for the missing preferred-language field. It is findable (the field lists in Section 7 and the `patient` table in 20.1 have no language column); the miss was the reader's. No wording change.

### Problems found in the sound sections (each would have scored a correct finding as a false positive)

1. Section 8 with 20.2: `clinic_slot` and `appointment` were partitioned by month, but PostgreSQL 16 cannot hold an exclusion constraint on a partitioned table, and a unique index there must include the partition key, so the overlap constraints and the FR-4 index could not be built. Section 20.2 now keeps both tables unpartitioned (rows older than 25 months copied to S3 and deleted, about 8 million rows each).
2. Section 8: the FR-4 index was a partial index "for appointments in the future"; a partial index predicate cannot depend on the current time, and `appointment` had no consultant or visit-type column. The index is now partial on status `booked` (check-in, no-show marking and cancellation leave that status), and `appointment` carries `consultant_id` and `visit_type` (20.1); `clinic_slot` lists `consultant_id` and `room_id`.
3. Section 12: covering consultants had their "practising-privilege dates checked", which needs the credentialing register that PB-03 says does not exist yet (the F10 dependency, in a sound section). Cover is now limited to consultants who already hold clinic sessions at that hospital.
4. Section 12: leave closed "sessions" but said nothing of booked theatre cases, and a non-responder was called only after 72 hours even when the appointment came sooner. Leave now closes clinic and theatre sessions, booked cases go to the theatre coordinator, and non-responders are called after 72 hours or by 48 hours before the appointment, whichever is first.
5. Section 16 with 6: the per-aggregate ordering claim did not hold if the relay ran as several tasks (Section 6 put three or more tasks on every service). The relay is now one active task holding an advisory lock with a standby, publishing in outbox `seq` order, which is commit order per aggregate; Section 6 and the `outbox` row of 20.1 match.
6. Section 16: "about 30 events per second" had no basis against 1.3 bookings a second in Section 24.1. Now "a few events per second", derived from 24.1.
7. Section 18: "Appointment participant of type Device" is now "whose `actor` is a Device" (R4 `participant.type` is a role).
8. Section 19: the Harvest Festival is a Sabah and Labuan holiday, not Sabah only.

### Other fixes (sections that are not sound sections, edited identically in v1 and v2)

9. Section 2 said every requirement is traced to an acceptance test in Section 28, which lists only some; it now says Section 28 covers those verified in UAT and early production.
10. Section 17.4: 2,400 billing calls a day could not carry the chargeable attended consultations (about 8,000 a day by Section 1); now about 32,000 events, 38,000 EMR calls and 8,500 billing calls a day.
11. Section 23.2: bookings "continue" during an EMR outage, yet Section 7 needs an EMR-issued MRN before confirming a new patient; and SMS outages fell back to WhatsApp for patients who had not opted in to it (Section 5 item 4). Both corrected.

### v2-only fixes (the fixed flaws must be cleanly fixed)

12. 13.2 (F02 fix): sedation-list cases were said not to conflict because the session covers two rooms, yet the constraint is on cases, so two simultaneous endoscopy cases with one anaesthetist would be rejected. Those cases now carry a `sedation_list` flag that the anaesthetist constraint's `WHERE` clause leaves out; 20.1 lists the column.
13. 23.3 (F05 fix): logical replication carries neither sequences nor DDL, so after failover the `booking_no` sequence would restart. Migrations now go to Cyberjaya first and sequences are set above the replicated values on failover.
14. 11.2 (F01 fix): the token link host `bkh.my` (a short domain someone may own) is now `book.bayukasih-health.my`.

### Names

15. "Temujanji" is the Malay word for appointment and the name of real Malaysian hospital appointment systems (for example Hospital Sungai Buloh's "Sistem Temujanji"); the platform is renamed "Jadwira" (no match found) in both designs, the key, the canonical key, the README and the FHIR identifier system.
16. "Daniel Teoh" matched a real healthcare executive who was a CIO (Healthway Medical Group, later MaNaDr); the Group CIO is now "Desmond Yap" (no healthcare CIO match).
17. No exact real match for "Bayu Kasih Healthcare", "Bayu Kasih Digital", "Ombak" as an EMR, "Kirana Billing" as a hospital product (only Indian grocery-store billing software uses "kirana" generically), "Lintas Mesej", "Dr. Farah Iskandar" or "Kavitha Raman" in this role.

### Key consistency checked

- Severity and category of F01 to F15 match their substance and the taxonomy (the converter maps `scalability_failure_mode` and `unjustified_quantitative_claim`).
- Numbers recomputed: F12 40 x 2.6 million = 104 million a year; F06 96/67 gives 2 parts and 142/67 gives 3; v2 SMS 0.65 + 0.4 + 0.45 = 1.5 parts, RM 201,676, total RM 2,095,000, margin 12.7 percent; v1 cost lines and total RM 2,027,000; F11 v2 window 20:00 to 09:00 holds for appointments from 08:00 to 21:00 with quiet hours.
- `flaw_counts` match (4 / 6 / 4; 3 / 2 / 2 / 2 / 2 / 1 / 1 / 1). `v2_changes` match the diff: the seven fixed flaws are gone in v2, the seven unchanged keep their sentence, and F15 is only in v2 17.3, carried by the F04 change. `expected_v2_open_flaws` is right. `distractor_notes` do not leak.
- Key text updated: Section 8, 12 and 16 `why_sound`; F12 recommendation ("like the other large tables" removed); the F02 and F05 `v2_changes` notes.
- F06 source re-fetched on 2026-10-05: https://docs.aws.amazon.com/sms-voice/latest/userguide/sms-limitations-character.html says "If your message contains any characters that are outside of the GSM 03.38 character set, it can have up to 70 characters", with 153 and 67 characters per part for multipart messages. The key's quote stands.

### Checks after the edits

- PDFs rebuilt through `coldread_hospital/build_hospital_pdfs.py`: `design_v1.pdf` 16 pages, `design_v2.pdf` 17 pages, all probe checks passed.
- Anchors: F02 moved to page 9 and F06 to page 8; F12's quote is now "booking_audit grows by about 10 million rows a year, so it stays a single unpartitioned" (the old one broke across a line). All 15 anchors exact and unique on their recorded pages.
- Canonical key through `coldread_hospital/convert_hospital.py --tier synthetic --verify-anchors`: `60 flaws converted across 4 keys; 0 key(s) failed validation`; the other three canonical keys are unchanged.
- No-label scan: `design_v1.md:0`, `design_v2.md:0`. Em dash count 0 in both designs, both keys, the README and this note. `scripts/leakage_grep.py`: only the known `never leave` hit from the payments item.
