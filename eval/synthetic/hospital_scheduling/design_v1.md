# Bayu Kasih Healthcare: Temujanji Clinic and Theatre Scheduling Platform

## Detailed Design

*Architecture, requirements and validation criteria for build*

| | |
|---|---|
| **Version** | 1.0 |
| **Status** | Design phase, build not started |
| **Last updated** | 2026-08-28 (architecture), consolidated 2026-09-18 |
| **Prepared by** | Bayu Kasih Digital, Patient Access Platform Team |
| **Approvers** | Dr. Farah Iskandar (Group Chief Medical Officer); Daniel Teoh (Group Chief Information Officer); Kavitha Raman (Head of Patient Access) |
| **Companion documents** | Temujanji Conceptual Design v1.1; Privacy Impact Assessment (draft 0.4); Ombak EMR Integration Specification v2.3; Kirana Billing Interface Agreement |

---

## Table of Contents

1. Purpose and Scope
2. Requirements
3. Foundational Principles
4. Hospitals, Services and Users
5. Regulatory and Data Residency Obligations
6. Target Architecture
7. Patient Identity and Registration
8. Outpatient Slot Model
9. Booking Channels: Web, App and Call Centre
10. Waitlist, Slot Release and No-Shows
11. Patient Reminders over SMS and WhatsApp
12. Consultant Sessions, Leave and Bulk Rescheduling
13. Operating Theatre Scheduling
14. Surgeon and Anaesthetist Rostering
15. Bed and Equipment Allocation
16. Event Bus and Transactional Outbox
17. EMR and Billing Integration
18. FHIR Resource Mapping
19. Time, Calendars and Public Holidays
20. Data Model and Storage
21. Identity, Access and Audit
22. Reporting and Group Analytics
23. Resilience, Availability and Disaster Recovery
24. Capacity and Cost Budget
25. Observability and Operations
26. Confirmed Decisions
27. Pending Backlog
28. Validation and Acceptance Criteria
29. Implementation Readiness Assessment
30. Build Phases

---

## 1. Purpose and Scope

This document describes the architecture of Temujanji, the clinic and theatre scheduling platform of Bayu Kasih Healthcare Berhad ("the group"). Temujanji is the single system in which outpatient appointments are booked, operating theatre time is planned, surgeons and anaesthetists are rostered, beds and shared equipment are allocated, and patients are reminded of what has been booked for them. It is written to a level of detail sufficient for an engineering team to begin implementation; Section 29 gives an explicit assessment of where that is and is not yet true.

Today each of the group's six hospitals runs its own appointment book inside the scheduling module of its EMR instance, theatre lists are kept in spreadsheets shared by the theatre coordinators, and bed management is done by telephone between the admissions desk and the wards. The call centre cannot see availability across hospitals, a patient who books at two hospitals has two unrelated records, and no report shows group-wide waiting times. Temujanji replaces the hospital appointment books and the theatre spreadsheets with one platform, while the Ombak EMR remains the clinical record and Kirana Billing remains the financial system.

### In scope

Outpatient appointment booking through the patient web portal, the Bayu Kasih mobile app and the group call centre; consultant session templates, leave and bulk rescheduling; waitlists and slot release; no-show handling; patient reminders by SMS and WhatsApp; operating theatre scheduling; surgeon and anaesthetist rostering for theatre sessions; inpatient bed allocation at admission; allocation of shared theatre equipment; publication of schedule changes on an event bus; integration with the Ombak EMR and Kirana Billing over HL7 FHIR R4; group reporting.

### Out of scope

Clinical documentation, orders and results (Ombak EMR); pricing, deposits, guarantee letters from insurers and invoicing (Kirana Billing, which Temujanji calls but does not replace); nurse and allied health rostering (Workforce module of the HR system); emergency department triage and bed requests from the emergency department, which continue through the existing bed management desk until Phase 3.

### Volume baseline

| Measure | 2025 actual | 2028 planning figure |
|---|---:|---:|
| Hospitals | 6 | 7 |
| Licensed beds | 1,180 | 1,420 |
| Operating theatres (including 6 hybrid and catheterisation suites) | 52 | 61 |
| Resident and visiting consultants with clinic sessions | 640 | 760 |
| Outpatient appointments per year | 2.6 million | 3.2 million |
| Clinic days per year (Monday to Saturday, less public holidays) | 302 | 302 |
| Theatre cases per year | 46,000 | 55,000 |
| Inpatient admissions per year | 118,000 | 140,000 |
| Registered patients in the group master patient index | 1.9 million | 2.4 million |

On an average clinic day the group therefore handles about 8,600 outpatient appointments and about 150 theatre cases.

---

## 2. Requirements

Requirements carry stable IDs. Each is traced to its acceptance criterion in Section 28.

### 2.1 Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | Patients can book, confirm, cancel and reschedule outpatient appointments through the web portal, the mobile app and the call centre, against one shared view of availability across all hospitals. |
| FR-2 | A slot search returns available slots by specialty, consultant, hospital, language spoken and earliest date. |
| FR-3 | Every booking is attached to exactly one patient in the group master patient index (MPI) and carries that patient's medical record number (MRN). |
| FR-4 | A patient may hold at most one future appointment with the same consultant for the same visit type. |
| FR-5 | Patients may join a waitlist for an earlier slot with a chosen consultant or for any consultant of a specialty. |
| FR-6 | Released slots are offered to waitlisted patients in a fair order, with clinically urgent patients given suitable priority. |
| FR-7 | No-shows are recorded, and patients with repeated no-shows are handled under the no-show policy of Section 10. |
| FR-8 | Patients receive appointment reminders by WhatsApp or SMS in their preferred language. |
| FR-9 | A theatre case can be booked only into a theatre session in which the theatre, the operating surgeon and the anaesthetist are all free for the whole planned duration including turnaround. |
| FR-10 | Theatre sessions are allocated to surgeons from a weekly master schedule, and anaesthetists are rostered to sessions. |
| FR-11 | At admission, each inpatient is allocated a bed that matches the ward, the room class and, for shared rooms, the patient's sex. |
| FR-12 | Shared theatre equipment (image intensifiers, surgical robots, lasers, navigation systems) is reserved per case, and a case that needs equipment cannot be confirmed without a reservation. |
| FR-13 | When a consultant takes leave, the affected appointments are rescheduled in bulk with clinical review of urgent patients and notification of every patient. |
| FR-14 | Every booking, change and cancellation reaches the Ombak EMR, and every chargeable booking reaches Kirana Billing. |
| FR-15 | The group can report waiting times, utilisation, no-show rates and theatre efficiency by hospital, specialty and consultant. |
| FR-16 | Every change to an appointment, theatre case or bed allocation is recorded with who made it, when and through which channel. |

### 2.2 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | Availability: booking, theatre scheduling and bed allocation are available 99.9 percent of each calendar month, measured at the API gateway. |
| NFR-2 | Latency: slot search returns within 800 ms and a booking is confirmed within 2 s, at the 95th percentile, at the 2028 planning volume. |
| NFR-3 | Reminder delivery: at least 97 percent of reminders are delivered to the patient's handset at least 20 hours before the appointment. |
| NFR-4 | Data residency: patient data is stored and processed only in Malaysia. |
| NFR-5 | Privacy: patient data is processed under the Personal Data Protection Act 2010 as amended in 2024, and each user and service sees only the patient data needed for its purpose. |
| NFR-6 | Recovery: recovery point objective (RPO) of at most 5 minutes and recovery time objective (RTO) of at most 4 hours for scheduling data, for any failure up to and including loss of the cloud region. |
| NFR-7 | Audit: the change history of FR-16 is retained for seven years and cannot be altered by application users. |
| NFR-8 | Growth: the platform supports the 2028 planning figures of Section 1 without architectural change. |
| NFR-9 | Accessibility: the web portal and the mobile app meet WCAG 2.2 level AA. |
| NFR-10 | Cost: recurring platform cost stays within RM 2.4 million a year at the 2028 planning volume. |

---

## 3. Foundational Principles

**P1. One book of availability.** There is exactly one place where a slot, a theatre session or a bed is free or taken: the Temujanji database. Every channel, every hospital and every downstream system reads availability from it or from events it publishes.

**P2. The EMR is the clinical record.** Temujanji holds scheduling facts only. Diagnoses, notes and orders stay in the Ombak EMR; Temujanji stores a referral reason code and a procedure code where scheduling needs them, nothing more.

**P3. Positive patient identification.** A booking is attached to an existing patient only on an exact match of a national identifier (MyKad number, or passport number and nationality) together with the date of birth. Where that cannot be done the patient is registered as new, and Medical Records merges any duplicate later.

**P4. Events, not shared tables.** Other systems learn about schedule changes from events on the event bus. No system reads Temujanji's tables directly.

**P5. Safety over throughput.** Where a scheduling rule protects a patient (theatre, surgeon or anaesthetist availability, equipment, a bed that suits the patient), the rule is enforced by the platform and cannot be overridden from a channel.

**P6. Least privilege.** Staff and services receive the narrowest access their role needs, scoped to their hospital unless their role is group-wide.

**P7. Malaysia only.** All storage, processing and backups of patient data stay in Malaysia, in the AWS Asia Pacific (Malaysia) Region and the group's Cyberjaya data centre.

---

## 4. Hospitals, Services and Users

The group operates six hospitals: Bayu Kasih Petaling Jaya (312 beds, 14 theatres), Cheras (226 beds, 10 theatres), Shah Alam (188 beds, 8 theatres), Penang (190 beds, 8 theatres), Johor Bahru (164 beds, 7 theatres) and Kota Kinabalu (100 beds, 5 theatres). A seventh hospital in Seremban opens in 2027. Each hospital runs specialist clinics six days a week, with evening clinics until 21:00 at Petaling Jaya and Cheras.

Consultants in Malaysian private hospitals are mostly independent practitioners who hold practising privileges at one or more of the group's hospitals. A consultant's clinic sessions, theatre sessions and leave are agreed with the hospital's medical affairs office. About 70 consultants hold privileges at two or more hospitals.

| User group | Approximate number | Main use of Temujanji |
|---|---:|---|
| Patients | 1.9 million registered | Book, confirm, cancel and reschedule; receive reminders |
| Call-centre agents (group contact centre, Petaling Jaya) | 85 | Book on behalf of patients for all hospitals |
| Clinic front-desk staff | 260 | Book, check in, mark attendance and no-shows |
| Consultants' clinic secretaries | 210 | Manage session templates and leave, book follow-ups |
| Theatre coordinators | 34 | Plan theatre lists, book and move cases |
| Admissions and bed managers | 70 | Allocate beds at admission |
| Medical affairs officers | 18 | Approve sessions and rosters |
| Group analysts | about 140 | Reporting (Section 22) |

---

## 5. Regulatory and Data Residency Obligations

1. **Personal Data Protection Act 2010 (PDPA), as amended by the Personal Data Protection (Amendment) Act 2024.** Information about a person's physical or mental health is sensitive personal data and may be processed only with the patient's explicit consent or under one of the Act's exceptions. The amendments introduce mandatory notification of personal data breaches to the Commissioner, the appointment of a data protection officer, and a right to data portability. The group's data protection officer is the owner of the Privacy Impact Assessment that accompanies this design.
2. **Private Healthcare Facilities and Services Act 1998 (Act 586) and its regulations.** Medical records, which include appointment and admission records, are confidential, must be kept for the periods set by the regulations and the Ministry of Health's record-keeping guidance, and may be disclosed only for the patient's care or as the law allows.
3. **Group data residency policy (GDR-02).** Patient data is stored and processed in Malaysia only. This is the basis of NFR-4 and P7.
4. **Messaging channels.** WhatsApp messages from a business to a patient outside a 24-hour customer service window must use message templates approved in advance by Meta, and the patient must have opted in to receive them. SMS is sent through Lintas Mesej Sdn Bhd, an aggregator holding the required Malaysian Communications and Multimedia Commission licence.

---

## 6. Target Architecture

Temujanji runs in the AWS Asia Pacific (Malaysia) Region, ap-southeast-5, across three Availability Zones. Patient-facing traffic enters through Amazon CloudFront and an Application Load Balancer; staff traffic enters through the group network over AWS Direct Connect.

```
 Patients (web, app)    Call centre, clinics, theatres, admissions
        |                              |
   CloudFront + ALB              Direct Connect + ALB
        \                              /
         +---- API Gateway layer -----+
                     |
   +-----------+-----------+-----------+-----------+
   | Booking   | Theatre   | Bed and   | Reminder  |
   | Service   | Service   | Equipment | Service   |
   |           |           | Service   |           |
   +-----------+-----------+-----------+-----------+
          |  Aurora PostgreSQL 16 (writer + 2 readers)
          |  outbox table -> Outbox Relay -> Amazon MSK
          |                                    |
          |              +---------------------+------------------+
          |              |                     |                  |
          |        FHIR Bridge          Reminder Scheduler   Analytics Loader
          |        (Ombak EMR,          (SMS aggregator,      (group analytics
          |         Kirana Billing)      WhatsApp)              bucket)
          |
   ElastiCache (Redis OSS): theatre calendar cache, session store
```

### Layer responsibilities

| Component | Responsibility |
|---|---|
| API gateway layer | Authentication, rate limiting, request validation, routing to services |
| Booking Service | Outpatient slots, appointments, waitlists, no-shows, session templates, leave |
| Theatre Service | Theatre sessions, cases, surgeon and anaesthetist rosters, case equipment |
| Bed and Equipment Service | Bed allocation and equipment reservation |
| Reminder Service | Reminder content, consent, channel choice, delivery status |
| Aurora PostgreSQL 16 | System of record for all scheduling data (P1) |
| Outbox Relay | Publishes committed outbox rows to Amazon MSK (Section 16) |
| FHIR Bridge | Applies schedule events to the Ombak EMR and Kirana Billing (Section 17) |
| Analytics Loader | Nightly extract to the group analytics bucket (Section 22) |
| ElastiCache (Redis OSS) | Theatre calendar cache and patient web sessions |

All services are containers on Amazon ECS with AWS Fargate, three tasks or more per service spread across the three Availability Zones.

---

## 7. Patient Identity and Registration

The group master patient index (MPI) lives in the Ombak EMR, which issues the MRN. Temujanji keeps a local copy of the MPI fields it needs (MRN, name, date of birth, sex, national identifier, phone, email, address) refreshed from FHIR Patient events.

Patients who use the web portal or the app sign in through the patient identity provider, Amazon Cognito, with a verified mobile number. On first use the patient links the account to an MRN by entering the MyKad or passport number and the date of birth; the link is made on an exact match of both, in line with P3, or a new registration is created.

Front-desk staff register walk-in patients from the MyKad chip reader, which supplies the national identifier, name and date of birth directly. A new registration created by Temujanji is posted to the EMR as a FHIR Patient create, and the MRN returned by the EMR is stored on the booking before the booking is confirmed.

---

## 8. Outpatient Slot Model

A consultant's clinic sessions are generated from a session template: hospital, room, weekday, start and end time, slot length per visit type (new patient 20 minutes, follow-up 10 minutes by default) and the number of slots held back for urgent referrals. Templates generate concrete slots 26 weeks ahead in a nightly job.

Each slot is one row in `clinic_slot` with its consultant, hospital, room, period (`tstzrange`) and status. An appointment takes a slot by updating that row from `free` to `booked` in the same transaction that inserts the `appointment` row: `UPDATE clinic_slot SET status = 'booked', appointment_id = $1 WHERE slot_id = $2 AND status = 'free'`. If the update affects no row the slot has been taken in the meantime and the channel is shown the next free slots. Two exclusion constraints back this up: no two `booked` slots of the same consultant may overlap in time, and no two `booked` slots in the same room may overlap, enforced with `btree_gist` on (`consultant_id`, `period`) and (`room_id`, `period`). The FR-4 rule is a partial unique index on (`patient_id`, `consultant_id`, `visit_type`) for appointments in the future with status `booked`.

Slot search reads from the Aurora readers. A slot shown as free on a reader may already be taken on the writer, and that case is handled by the conditional update above, which runs on the writer. Urgent slots held back by the template are released for general booking 48 hours before the session if no urgent referral has taken them.

---

## 9. Booking Channels: Web, App and Call Centre

### 9.1 Web portal and mobile app

Signed-in patients search slots, book, confirm, cancel and reschedule their own appointments and those of dependants linked to their account (children under 18, and adults who have given the account holder a recorded authorisation). Rescheduling is a single transaction that takes the new slot and frees the old one.

### 9.2 Clinic front desk

Front-desk staff book follow-ups at the end of a consultation, check patients in on arrival and mark no-shows at the end of each session. They see their own hospital's appointments only.

### 9.3 Call centre

The group contact centre takes about 6,200 calls a day, of which about 3,900 lead to a booking, a change or a cancellation. Agents can book at any hospital. To keep calls short, the agent searches by the caller's name and date of birth, and when the search returns exactly one patient Temujanji attaches the booking to that patient's MRN without asking for the MyKad number. When the search returns no patient or more than one, the agent asks for the MyKad or passport number. Average handling time in the pilot was 3 minutes 40 seconds, against 5 minutes 50 seconds in the current per-hospital process.

### 9.4 Referral bookings

Referrals from general practitioners arrive through the referral inbox of each hospital and are triaged by the receiving clinic's nurse as routine, soon (within 14 days) or urgent (within 3 days). The triage category is stored on the waitlist entry or appointment and drives the urgent slots of Section 8.

---

## 10. Waitlist, Slot Release and No-Shows

### 10.1 Waitlist

A patient with a booked appointment may join the waitlist for an earlier slot with the same consultant, or with any consultant of the same specialty at chosen hospitals. Patients without an appointment may also be waitlisted where a clinic has no free slots in the next 26 weeks. Waitlist entries carry the triage category of Section 9.4 where there is a referral.

### 10.2 Slot release

An appointment that has not been confirmed by 12:00 on the day before it is released to the waitlist, and the patient is told by the same channel as the reminders that the slot has been released and how to rebook. Patients confirm by replying to a reminder, in the app or portal, or through the call centre.

When a slot is freed by a cancellation or a release, the Booking Service offers it to waitlisted patients one at a time. Each offer is sent by the patient's reminder channel and is held for 30 minutes; an accepted offer moves the patient's appointment into the slot and frees the patient's old slot, which is offered in turn.

### 10.3 No-shows

Front-desk staff mark an appointment as a no-show when the patient has not arrived by the end of the session. A patient with three no-shows within 12 months is flagged, and the call centre must confirm any new booking by telephone with the patient the day before. No-shows do not lead to a charge; consultation fees are billed only on attendance.

---

## 11. Patient Reminders over SMS and WhatsApp

### 11.1 Schedule and channels

Reminders are sent 48 hours and 24 hours before each appointment, by WhatsApp to patients who have opted in to WhatsApp and by SMS to all others. Reminders are not sent between 22:00 and 08:00; a reminder that falls in that window is sent at 08:00. In the pilot, 70 percent of patients chose WhatsApp.

The Reminder Scheduler reads `appointment.booked` and `appointment.rescheduled` events, computes the reminder times, and keeps a reminder schedule in its own table; a cancellation event removes pending reminders. Reminder content is rendered from approved templates, one per language and channel.

### 11.2 Content and the manage-booking link

Reminders carry the patient's first name, the date and time, the hospital and the clinic. Each reminder carries a manage-booking link of the form `https://book.bayukasih-health.my/b/{booking_no}`, which opens a page showing the patient's full name, the consultant, the specialty clinic, the date and time, and buttons to confirm, cancel or reschedule without signing in. The link lets the large share of patients who never install the app act on a reminder in one tap; in the pilot, 61 percent of confirmations came through it.

### 11.3 SMS templates

| Template | Language | Length (characters, with a typical link and hospital name) |
|---|---|---:|
| RMD-SMS-MS | Malay | 151 |
| RMD-SMS-EN | English | 138 |
| RMD-SMS-ZH | Chinese | 96 |
| RMD-SMS-TA | Tamil | 142 |

Every reminder template, in each of the four languages, is kept within 160 characters, so each reminder is delivered and billed as a single SMS message. The Lintas Mesej account is configured to reject concatenated messages, which keeps the monthly SMS bill predictable and avoids partial deliveries on older handsets.

### 11.4 WhatsApp templates

WhatsApp reminders use templates in the utility category approved by Meta for each language, sent through the WhatsApp Business Platform Cloud API. Patients opt in during booking or by replying START to the group number; opt-in and opt-out are stored with time and channel. A patient's reply of 1 confirms and 2 cancels; any other reply opens a conversation with the call centre.

### 11.5 Delivery status

The Reminder Service records the provider's acceptance of each message. WhatsApp delivery and read statuses arrive by webhook, and SMS delivery receipts arrive from Lintas Mesej by HTTP callback; both are stored on the reminder row. A WhatsApp reminder that has not been delivered after 2 hours is resent by SMS.

---

## 12. Consultant Sessions, Leave and Bulk Rescheduling

A consultant or the clinic secretary requests leave in Temujanji at least six weeks ahead where possible; the hospital's medical affairs officer approves it. Approval closes the consultant's sessions in the leave period, and the affected appointments enter a rescheduling worklist instead of being cancelled outright.

The worklist groups appointments by triage category. Urgent and soon patients are reviewed by the clinic nurse, who may move them to a covering consultant of the same specialty the consultant has nominated; routine patients are offered the consultant's next free slots after the leave. Every affected patient is told by their reminder channel, and patients who do not respond within 72 hours are called by the call centre. No appointment is cancelled until the patient has accepted a new slot, declined, or failed to respond to two calls. Emergency leave (illness, bereavement) follows the same flow with the call centre calling every patient with an appointment in the next 48 hours.

The worklist records who moved each appointment and why, and the consultant's practising-privilege dates are checked before a covering consultant is offered.

---

## 13. Operating Theatre Scheduling

### 13.1 Sessions and lists

Each theatre has morning (08:00 to 13:00), afternoon (13:30 to 18:30) and, at Petaling Jaya and Cheras, evening (18:30 to 22:00) sessions. Sessions are allocated to surgeons from the weekly master schedule (Section 14). A theatre list is the ordered set of cases in a session; theatre coordinators and surgeons' secretaries book cases into sessions, and the coordinator finalises the list at 14:00 on the day before.

When the coordinator finalises a list, Temujanji fixes the case order and planned start times, sends the list to the ward and the pre-operative assessment clinic, and sends each patient the fasting instructions and arrival time that the anaesthetist has set for the case. Changes after finalisation are possible but each one re-sends the arrival time to the patient and the ward and is shown in red on the list until the ward acknowledges it.

### 13.2 Booking a case

A case booking names the patient, the procedure, the operating surgeon, the anaesthetist, the planned duration (from the surgeon's own median for that procedure, or the group median when the surgeon has fewer than ten cases) and the equipment it needs. A turnaround of 20 minutes is added after each case, or 40 minutes after a case needing a laminar-flow clean.

The Theatre Service checks the requested theatre, the surgeon and the anaesthetist for overlapping cases against the theatre calendar held in ElastiCache, which the schedule-change consumer refreshes from the event bus, and when it finds no overlap it inserts the case into `theatre_case`. The cache keeps the check fast enough for the interactive list editor, which re-validates the whole list on every drag and drop. A booked case appears on the theatre list, in the EMR and on the ward's pre-operative worklist.

### 13.3 Changes on the day

Cases may be moved between sessions and theatres on the day by the theatre coordinator. A case that overruns pushes the following cases later; when a case would end after the session end, the coordinator chooses to extend the session (with the anaesthetist's and the theatre manager's agreement) or move the case.

### 13.4 Emergency cases

Each hospital with more than eight theatres keeps one theatre unbooked for emergency cases during the day; the others book emergency cases into the next suitable gap, displacing elective cases if the on-call surgeon and anaesthetist agree.

---

## 14. Surgeon and Anaesthetist Rostering

The weekly master schedule assigns each theatre session to a surgeon (or to a specialty for shared sessions). It is agreed by the hospital's theatre committee each quarter. A surgeon who will not use an allocated session releases it at least 10 days ahead; released sessions are offered to the specialty's waitlist of surgeons.

Anaesthetists are rostered to sessions weekly. An anaesthetist may cover only one theatre at a time, except for sedation lists where one anaesthetist supervises two adjacent endoscopy rooms, which the roster marks explicitly.

Before a surgeon is given a session or a case, Temujanji checks that the surgeon holds current practising privileges at that hospital for the procedure's specialty (Decision DEC-08).

---

## 15. Bed and Equipment Allocation

### 15.1 Beds

The group has 1,180 beds in 74 wards, of which 64 are single rooms with negative pressure for airborne isolation and 112 are other single rooms. Elective admissions are booked in Temujanji with an expected date and length of stay; on the day of admission the admissions desk allocates a bed.

Admission requests carry the patient's infection-control flags from the EMR (for example MRSA, CRE, or suspected or confirmed tuberculosis), which are displayed on the admission screen. The allocator proposes the first free bed that matches the requested ward, the room class covered by the patient's guarantee letter or deposit, and the patient's sex for shared rooms, and the admissions officer confirms it with one click. Bed status (free, occupied, being cleaned, blocked) is updated by ward staff and housekeeping from the ward tablet.

### 15.2 Equipment

Shared theatre equipment is registered per hospital with its type and the theatres it can be used in. A case that needs equipment reserves one unit of the type for the case's planned period plus 30 minutes for set-up and cleaning. Equipment reservations are held in `equipment_reservation`, which has an exclusion constraint on (`equipment_id`, `period`) so a unit cannot be reserved twice for overlapping periods. Equipment that is out of service for maintenance is blocked by biomedical engineering.

---

## 16. Event Bus and Transactional Outbox

Every service writes its domain events to an `outbox` table in the same transaction as the change they describe. The Outbox Relay polls the outbox every 200 ms, publishes each row to Amazon MSK with the producer settings `acks=all` and `enable.idempotence=true`, and marks the row published only after the broker has acknowledged it. A relay that crashes between publish and mark republishes the row, so consumers see each event at least once and must deduplicate by `event_id`.

Topics are `schedule.appointment`, `schedule.theatre`, `schedule.bed` and `patient.registration`, each with 12 partitions, replication factor 3 and `min.insync.replicas=2`. The message key is the aggregate's ID (appointment ID, case ID, admission ID), so all events of one appointment or case are in one partition and are consumed in the order in which they were committed. Events carry a schema version and are validated against a schema registry on publish. Retention is 7 days.

Consumers deduplicate with a `processed_event` table of their own, keyed by `event_id` and written in the same local transaction as the consumer's effect, so a republished event is recognised and skipped. Schema changes are backward compatible within a major version; a breaking change publishes to a new topic version in parallel until every consumer has moved.

Peak event volume is about 30 events per second during the morning booking peak, which is far below what a three-broker MSK cluster sustains, so the bus is sized for durability and availability, not throughput.

---

## 17. EMR and Billing Integration

### 17.1 Direction of flow

Temujanji owns scheduling (P1); the Ombak EMR owns the patient record and the MPI (P2). Patient registrations and demographic changes flow from the EMR to Temujanji as FHIR Patient events through the EMR's subscription interface. Schedule changes flow from Temujanji to the EMR and to Kirana Billing through the FHIR Bridge.

### 17.2 FHIR Bridge

The FHIR Bridge is a consumer group on the three `schedule.*` topics. For each event it builds the FHIR resources of Section 18 and calls the Ombak EMR FHIR R4 endpoint and, for chargeable events (theatre case booked, admission booked, consultation attended), the Kirana Billing FHIR endpoint, using OAuth 2.0 client credentials. Each call is retried three times with exponential backoff from 1 second.

### 17.3 Errors and offsets

The bridge consumes with automatic offset commits every 5 seconds. When a call still fails after three retries, the bridge writes the event and the error to its log and continues with the next event, so that one bad record never blocks the partition. The integration support team reviews the bridge's error log each morning.

### 17.4 Volumes

About 26,000 schedule events a day reach the bridge, which makes about 31,000 FHIR calls a day to the EMR and 2,400 to billing. The Ombak EMR's FHIR endpoint is rated by its supplier at 50 requests per second per hospital instance.

---

## 18. FHIR Resource Mapping

Temujanji uses HL7 FHIR R4 (4.0.1) resources as follows.

| Temujanji concept | FHIR R4 resource | Notes |
|---|---|---|
| Clinic session | Schedule | `actor` references the Practitioner and the Location (clinic room) |
| Clinic slot | Slot | `status` is `free`, `busy` or `busy-unavailable` |
| Outpatient appointment | Appointment | `status` is `booked`, `arrived`, `fulfilled`, `cancelled` or `noshow`; waitlist entries use `waitlist` |
| Theatre case | Appointment with `serviceType` theatre, plus ServiceRequest for the procedure | Participants: Patient, operating surgeon, anaesthetist, theatre Location |
| Admission | Encounter (`class` IMP) with `location` the allocated bed | Status `planned`, then `in-progress` |
| Equipment reservation | Appointment participant of type Device | Device resource per equipment unit |

Every resource carries Temujanji's own identifier in `identifier` with the system `https://fhir.bayukasih-health.my/temujanji`. Creates are sent as conditional creates (`If-None-Exist` on that identifier), so a resent event does not create a duplicate. Updates are sent as conditional updates on the same identifier with the full current state of the resource. A theatre case's Appointment and ServiceRequest are sent together as a Bundle of type `transaction`, which the FHIR specification requires the server to process as a single unit that succeeds or fails as a whole. Patient references use the MRN identifier, never a name.

---

## 19. Time, Calendars and Public Holidays

All timestamps are stored as `timestamptz` in UTC and displayed in Malaysia Time (MYT, UTC+8). Peninsular Malaysia, Sabah and Sarawak all observe UTC+8 and Malaysia has no daylight saving time, so one display zone serves every hospital, including Kota Kinabalu.

Public holidays differ between states: national holidays apply everywhere, while state holidays (for example Thaipusam in Selangor, Penang and Johor but not in Sabah, and Harvest Festival in Sabah only) apply per hospital. The holiday calendar is a table keyed by state and date, loaded each November from the federal and state gazettes for the following year and approved by the group's medical affairs office. Session templates skip holidays of the hospital's state. Holidays declared at short notice (for example a replacement holiday) are added by medical affairs and trigger the bulk rescheduling flow of Section 12 for the affected sessions.

Islamic holidays whose dates depend on moon sighting are loaded with their expected dates and confirmed or moved by medical affairs when the date is announced; the rescheduling flow handles a move.

---

## 20. Data Model and Storage

### 20.1 Main tables (Aurora PostgreSQL 16)

| Table | Key columns | Notes |
|---|---|---|
| `patient` | `patient_id`, `mrn`, `national_id`, `name`, `dob`, `sex`, `phone`, `email`, `whatsapp_opt_in` | Local copy of MPI fields (Section 7) |
| `clinic_session` | `session_id`, `consultant_id`, `hospital_id`, `room_id`, `period` | Generated from templates |
| `clinic_slot` | `slot_id`, `session_id`, `period`, `status`, `appointment_id` | Exclusion constraints (Section 8) |
| `appointment` | `appointment_id`, `booking_no`, `patient_id`, `slot_id`, `status`, `channel`, `triage` | |
| `waitlist_entry` | `entry_id`, `patient_id`, `specialty`, `consultant_id`, `triage`, `created_at` | |
| `theatre_session` | `session_id`, `theatre_id`, `surgeon_id`, `anaesthetist_id`, `period` | |
| `theatre_case` | `case_id`, `session_id`, `patient_id`, `procedure_code`, `surgeon_id`, `anaesthetist_id`, `planned_period` | |
| `equipment_reservation` | `reservation_id`, `equipment_id`, `case_id`, `period` | Exclusion constraint (Section 15.2) |
| `admission` | `admission_id`, `patient_id`, `bed_id`, `expected_period`, `status` | |
| `reminder` | `reminder_id`, `appointment_id`, `channel`, `due_at`, `status` | |
| `booking_audit` | `audit_id`, `entity`, `entity_id`, `action`, `actor`, `channel`, `before`, `after`, `created_at` | Append-only (Section 21) |
| `outbox` | `event_id`, `topic`, `key`, `payload`, `published_at` | Section 16 |

The `booking_no` is a 9-digit number allocated from a single group-wide sequence, printed on appointment cards and quoted by patients to the call centre and front desk. It is unique across all hospitals so that one number identifies a booking anywhere in the group.

### 20.2 Physical design

`clinic_slot` and `appointment` are partitioned by month on the slot start; partitions older than 25 months are detached and archived to Amazon S3 in Parquet. At about 40 audit rows per appointment and 2.6 million appointments a year, `booking_audit` grows by about 10 million rows a year, so it stays a single unpartitioned table for the full seven-year retention period. The writer is a db.r7g.2xlarge instance with two readers of the same size.

---

## 21. Identity, Access and Audit

Staff sign in through the group's OIDC identity provider with multi-factor authentication. Roles are assigned per hospital (front desk, theatre coordinator, admissions, medical affairs) or group-wide (call-centre agent, group analyst, platform administrator). A front-desk user sees appointments of their own hospital only; call-centre agents see appointments at all hospitals because they book for all of them.

Patients sign in through Amazon Cognito as described in Section 7. Patient-facing APIs require a Cognito session, except the manage-booking page of Section 11.2, which is the only patient page that works without signing in so that reminders can be acted on in one tap.

Service-to-service calls use IAM roles; the FHIR Bridge's client credentials for the EMR and billing are held in AWS Secrets Manager and rotated every 90 days. All data is encrypted at rest with AWS KMS keys owned by the group and in transit with TLS 1.2 or later.

Every change to an appointment, theatre case, equipment reservation or admission writes a `booking_audit` row in the same transaction, with the actor, channel, and the before and after state. Application roles have `INSERT` and `SELECT` on `booking_audit` but no `UPDATE` or `DELETE`; a nightly job copies the day's audit rows to an S3 bucket with Object Lock in compliance mode and seven-year retention, which meets NFR-7.

---

## 22. Reporting and Group Analytics

### 22.1 Operational reports

Clinic managers and theatre managers see live dashboards for their hospital: today's clinics and lists, utilisation, late starts, overruns and cancellations. These read from the Aurora readers.

### 22.2 Group analytics

The Analytics Loader runs nightly at 02:00. It copies the previous day's appointment, theatre_case and admission rows, each with the patient's name, MyKad number, phone number, referral reason code and procedure code, into the group analytics bucket in Amazon S3, where every user with the Group Analyst role (about 140 staff across finance, marketing, operations and the clinical quality unit) can query them with Amazon Athena. Keeping the patient identifiers in the extract lets analysts join appointments to the EMR's diagnosis data and to campaign responses without a separate request to Medical Records.

Standard group reports (waiting time to first appointment by specialty, theatre utilisation, no-show rate, cancellation reasons) are built on the analytics bucket and published weekly to the group executive committee.

---

## 23. Resilience, Availability and Disaster Recovery

### 23.1 Within the region

Every service runs at least three tasks across three Availability Zones. Aurora PostgreSQL has its writer and two readers in different zones and fails over to a reader in about 30 seconds on loss of the writer. MSK has three brokers, one per zone. ElastiCache runs with one replica per shard in a second zone. Loss of one Availability Zone does not lose committed data and is absorbed within the NFR-1 target.

### 23.2 Dependencies

When the Ombak EMR is unavailable, bookings continue and the bridge's events wait in the topics until the EMR returns. When Lintas Mesej or the WhatsApp Business Platform is unavailable, reminders are queued and the other channel is used for reminders that would otherwise be late. When the patient identity provider is unavailable, patients cannot sign in and are directed to the call centre.

### 23.3 Region loss

AWS Backup takes a daily snapshot of the Aurora cluster at 01:00 and copies it to the group's Cyberjaya data centre over Direct Connect, where it is kept for 35 days; the MSK topics are not copied. On loss of the ap-southeast-5 Region, the platform is restored in the Cyberjaya data centre from the most recent nightly snapshot onto the group's on-premises PostgreSQL cluster and VMware hosts, which have been sized to run Temujanji at reduced capacity. P7 rules out a second AWS Region outside Malaysia.

### 23.4 Downtime procedure

Each clinic and theatre prints the next day's lists at 18:00 so that, if Temujanji is unavailable, the day can run from paper; bookings made on paper are entered when the platform returns.

---

## 24. Capacity and Cost Budget

### 24.1 Load

| Measure | 2025 | 2028 |
|---|---:|---:|
| Appointments per clinic day | 8,600 | 10,600 |
| Bookings, changes and cancellations per clinic day (all channels) | 21,000 | 26,000 |
| Peak bookings per second (08:00 to 10:00, 35 percent of the day's bookings) | 1.0 | 1.3 |
| Slot searches per second at peak | 22 | 29 |
| Reminders per clinic day (two per appointment) | 17,200 | 21,200 |
| SMS reminders per clinic day (30 percent of reminders) | 5,160 | 6,360 |

### 24.2 Recurring cost at the 2028 volume

| Item | RM per year |
|---|---:|
| Compute (ECS on Fargate, all services) | 412,000 |
| Aurora PostgreSQL (writer, two readers, storage, I/O, backups) | 498,000 |
| Amazon MSK (three brokers, storage) | 156,000 |
| ElastiCache, CloudFront, load balancers, API layer | 188,000 |
| S3, Athena, AWS Backup | 64,000 |
| SMS through Lintas Mesej (6,360 per day x 302 days x RM 0.07 per message) | 134,000 |
| WhatsApp utility templates (14,840 per day x 302 days x RM 0.06 per message) | 269,000 |
| Monitoring and logging | 96,000 |
| Direct Connect and the Cyberjaya recovery environment | 210,000 |
| **Total** | **2,027,000** |

The total is within the NFR-10 limit of RM 2.4 million with a margin of about 16 percent.

---

## 25. Observability and Operations

Services emit structured logs, metrics and traces to Amazon CloudWatch with AWS X-Ray tracing. Dashboards per service show request rate, errors and latency; business dashboards show bookings per channel, reminder delivery rate and theatre list changes. Alarms page the on-call platform engineer for: API 5xx rate above 1 percent for 5 minutes, booking latency p95 above 2 s for 10 minutes, outbox rows older than 60 seconds, consumer lag above 5 minutes on any `schedule.*` topic, and Aurora replica lag above 30 seconds.

Each alarm links to a runbook in the platform repository that names the first checks, the safe actions (for example restarting a relay task, or failing Aurora over to a reader) and the people to inform. Runbooks are exercised in a quarterly game day in the staging environment, in which the team removes an Availability Zone, stops the EMR sandbox and floods the booking API with search traffic, and records what the dashboards showed and how long recovery took.

The platform team runs a weekly on-call rotation of six engineers. The integration support team (three analysts, office hours) owns the FHIR Bridge's error log and the EMR and billing interfaces.

---

## 26. Confirmed Decisions

| ID | Decision | Rationale |
|---|---|---|
| DEC-01 | AWS ap-southeast-5 as the only cloud Region | Data residency (P7, NFR-4) |
| DEC-02 | Aurora PostgreSQL 16 as the system of record | Exclusion constraints, mature tooling, team skills |
| DEC-03 | Amazon MSK as the event bus with a transactional outbox | Durable ordered events per aggregate; no dual writes |
| DEC-04 | HL7 FHIR R4 for EMR and billing integration | Both suppliers support it; replaces four HL7 v2 feeds |
| DEC-05 | WhatsApp as the default reminder channel, SMS for patients who have not opted in | Lower cost per message and higher confirmation rate in the pilot |
| DEC-06 | Manage-booking links in reminders without sign-in | 61 percent of pilot confirmations came through the link |
| DEC-07 | Call centre books for all hospitals | One number for patients; staffing flexibility |
| DEC-08 | Theatre case booking and session allocation check the surgeon's practising privileges through the Credentialing Service API, from Phase 2 go-live of theatre scheduling | Patient safety; the medical advisory committees require it |
| DEC-09 | Cyberjaya data centre as the recovery site for region loss | P7; existing facility with spare capacity |

---

## 27. Pending Backlog

| ID | Item | Owner | Status |
|---|---|---|---|
| PB-01 | Seremban hospital onboarding (2027) | Patient Access | Planned for Phase 3 |
| PB-02 | Emergency department bed requests in Temujanji | Bed Management | Phase 3 |
| PB-03 | Replacement of the credentialing register, today a spreadsheet kept by each hospital's medical advisory committee secretariat, by a Credentialing Service with an API | Medical Affairs | Vendor selection not started; earliest API availability first quarter of 2028 |
| PB-04 | Self check-in kiosks in clinic lobbies | Patient Access | Not scheduled |
| PB-05 | Online payment of deposits at booking | Finance | Depends on Kirana Billing release 9 |
| PB-06 | Data protection officer review of the Privacy Impact Assessment | Group DPO | Draft 0.4 under review |

---

## 28. Validation and Acceptance Criteria

### 28.1 Functional requirements

| Req | Acceptance criterion |
|---|---|
| FR-1 | In UAT, scripted users book, confirm, cancel and reschedule through all three channels for all six hospitals; every change is visible in the other channels within 2 seconds. |
| FR-3 | Every appointment in UAT carries an MRN that exists in the EMR test MPI. |
| FR-4 | A second booking of the same visit type with the same consultant is refused in every channel. |
| FR-6 | In UAT, 50 released slots are offered and each is taken by a waitlisted patient. |
| FR-8 | Reminders are received on test handsets in all four languages on both channels. |
| FR-9 | Scripted bookings of overlapping cases for the same theatre, surgeon and anaesthetist are refused. |
| FR-11 | 200 simulated admissions are each allocated a bed matching ward, room class and sex. |
| FR-13 | A two-week leave for a consultant with 300 appointments produces a complete worklist, and every patient is notified. |
| FR-14 | Over a one-week parallel run, every appointment and case in Temujanji is present in the EMR with the same status, and every chargeable event is present in Kirana Billing. |
| FR-16 | Every action in the FR-1 script has an audit row with actor and channel. |

### 28.2 Non-functional requirements

| Req | Acceptance criterion |
|---|---|
| NFR-1 | Availability measured over the first three months in production. |
| NFR-2 | A load test at 1.5 times the 2028 peak for one hour meets both percentiles. |
| NFR-3 | In UAT, 2,000 reminders are sent through Lintas Mesej and the WhatsApp Business Platform, and at least 97 percent are accepted by the provider APIs with an HTTP 2xx response. |
| NFR-4 | AWS Config rules show no resource holding patient data outside ap-southeast-5; the Cyberjaya environment is inspected. |
| NFR-6 | A recovery exercise restores the platform in Cyberjaya within 4 hours. |
| NFR-7 | An application role's attempt to update or delete an audit row is refused; Object Lock retention is verified. |
| NFR-9 | An external WCAG 2.2 AA audit of the portal and the app passes. |

---

## 29. Implementation Readiness Assessment

| Area | Readiness | Comment |
|---|---|---|
| Outpatient slot model and booking channels | Ready | Pilot at Shah Alam ran 11 weeks |
| Waitlist, release and no-shows | Ready | |
| Reminders | Ready | Templates approved by Meta for all four languages |
| Consultant leave and rescheduling | Ready | |
| Theatre scheduling and rostering | Ready | List editor prototype tested with Petaling Jaya coordinators |
| Bed and equipment allocation | Ready | |
| Event bus and FHIR Bridge | Ready | EMR supplier sandbox available |
| Reporting and group analytics | Ready | |
| Resilience and recovery | Ready | Cyberjaya capacity confirmed |
| Privacy Impact Assessment | In progress | PB-06 |

---

## 30. Build Phases

| Phase | Scope | Target |
|---|---|---|
| Phase 1 | Outpatient booking (all channels), waitlist, reminders, EMR and billing integration for outpatients, at Shah Alam and Penang, then all hospitals | Go-live March 2027 |
| Phase 2 | Theatre scheduling, rostering with privilege checks (DEC-08), equipment, beds, group analytics | Go-live August 2027 |
| Phase 3 | Seremban hospital, emergency department bed requests, kiosks | 2028 |
