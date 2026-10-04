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
