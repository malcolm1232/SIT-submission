# PHON: National Examinations Registration and Results Platform

## Detailed Design

*Architecture, requirements and validation criteria for build*

| | |
|---|---|
| **Version** | 1.1 |
| **Status** | Detailed design; Phase 1 build in progress (Section 30.2); revised after the October 2026 architecture review |
| **Last updated** | 2026-10-14 (architecture); consolidated 2026-10-16 |
| **Prepared by** | Siam Examinations and Certification Board (SECB), Digital Platforms Division |
| **Companion documents** | PHON Conceptual Design v1.3; Examination Regulations 2027 (Chief Examiner's Office); Marking Centre Operations Manual; Data Protection Impact Assessment (draft) |

| Version | Date | Sections changed |
|---|---|---|
| 1.0 | 2026-09-26 | First consolidated design |
| 1.1 | 2026-10-16 | 2.2 (NFR-3); 14.2; 14.3; 17.2; 18.2; 18.3; 18.4; 19.1; 21.2; 24.2; 25.2; 27 (DEC-02, DEC-09); 29.1 (FR-8, FR-11); 29.2 (NFR-2, NFR-3, NFR-6) |

---

## Table of Contents

1. Purpose and Scope
2. Requirements
3. Foundational Principles
4. Examination Cycle and Volumes
5. Target Architecture
6. Identity and Access
7. Candidate Registration
8. Fee Collection and Reconciliation
9. Timetabling, Venues and Seat Allocation
10. Special-Needs Accommodations
11. Script Tracking and Chain of Custody
12. Marking Centres and Marker Allocation
13. Marks Capture with Double Entry
14. Moderation and Mark Adjustment
15. Grade Computation and Grade Boundaries
16. Appeals, Re-marks and Clerical Corrections
17. Results Release and Embargo
18. Results Delivery Channels: Web, App and SMS
19. School Portal and Ministry Reporting
20. Certificates and Verification
21. Data Model
22. Event Bus and Transactional Outbox
23. Data Protection and Retention
24. Resilience, Availability and Recovery
25. Capacity and Performance
26. Observability and Audit
27. Confirmed Decisions
28. Pending Backlog
29. Validation and Acceptance Criteria
30. Implementation Readiness Assessment and Build Phases

---

## Changes since version 1.0

Version 1.1 revises the following sections after the architecture review of October 2026 and the Chief Examiner's Office's comments on the moderation design. Section 2.2 restates NFR-3 with a measurable threshold. Sections 14.2 and 14.3 record moderation adjustments per script in their own table. Section 17.2 describes how the results tier holds the embargo state it checks on each read. Sections 18.2 and 25.2 describe the results tier serving pre-rendered result objects, with the sizing restated for the observed release-day peak, and Section 18.3 describes the statement of results as rendered with the result object. Section 18.4 and DEC-09 add a second SMS aggregator. Section 19.1 changes the publication time of the school results files. Section 21.2 lists the marks capture tables after the moderation change. Section 24.2 and DEC-02 describe the marks capture database deployment. Section 29.1 revises the FR-8 and FR-11 acceptance tests and Section 29.2 the NFR-2, NFR-3 and NFR-6 tests. All other sections are unchanged from version 1.0.

---

## 1. Purpose and Scope

This document describes the architecture of PHON, the platform through which the Siam Examinations and Certification Board (SECB) registers candidates for the National Secondary Certificate (NSC), collects fees, allocates venues and seats, tracks examination scripts from the hall to the marking centre, captures and moderates marks, computes grades, handles appeals, releases results to about 500,000 candidates at a fixed time, issues certificates, answers verification requests from employers and universities, and reports to the Ministry of Education. It is written to the level of detail an engineering team needs to begin implementation. Section 30 states where that is and is not yet true.

PHON replaces four systems: a registration system run by a contractor since 2014, a marks system on an unsupported database, a results website that has failed on three of the last six release days, and a certificate register kept partly on paper. The platform is operated by SECB's Digital Platforms Division from AWS in the Asia Pacific (Thailand) Region, ap-southeast-7, with three Availability Zones.

### In scope

Candidate registration through schools and for private candidates; fee collection and reconciliation; timetabling, venue and seat allocation with special-needs accommodations; script tracking; marker allocation; marks capture with double entry; moderation; grade computation and grade boundaries; appeals; results release through web, mobile app and SMS; the school portal; ministry reporting; certificates and verification; data protection and retention; the event bus; resilience; capacity; observability.

### Out of scope

Question-paper setting and printing (a separate secure facility), on-screen marking (a later programme), the SECB finance ledger (results of fee reconciliation are exported to it), and the physical logistics of script transport, which the Marking Centre Operations Manual covers.

## 2. Requirements

### 2.1 Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | Schools shall register their candidates in bulk by file upload or through the school portal, and private candidates shall register themselves online, with a national identity number as the candidate identifier. |
| FR-2 | Every registration shall carry the candidate's subject choices, with a per-subject fee computed from the fee schedule in force for the sitting. |
| FR-3 | Fees shall be collected from schools by invoice and from private candidates by online payment, and every payment shall be reconciled to a registration before the registration is confirmed. |
| FR-4 | Every confirmed candidate shall be allocated a seat in an approved venue for each paper, with no two candidates in one seat for the same session and no candidate in two venues at the same time. |
| FR-5 | Candidates with approved accommodations (extra time, enlarged print, a reader, a scribe, a separate room, assistive technology) shall be seated and timetabled according to the accommodation. |
| FR-6 | Every script shall be tracked from the examination hall, through transport, to the marking centre and back to archive, and a script whose location is unknown for more than 24 hours shall be raised as a missing script. |
| FR-7 | Markers shall be allocated to components according to their accreditation, and no marker shall mark the scripts of a school they are employed by. |
| FR-8 | Every mark shall be keyed independently by two operators, and any difference between the two entries shall be resolved by a third operator before the mark is accepted. |
| FR-9 | Moderation shall adjust the marks of a component for each marker according to the formula approved by the Chief Examiner's Office for that marker, and the adjustment applied to every marker shall be recorded. |
| FR-10 | Grades shall be computed from moderated marks using grade boundaries set by the Awarding Committee, and every grade shall be reproducible from the stored marks and boundaries. |
| FR-11 | Results shall be released to all candidates at the published time, and no candidate shall be able to see a result before that time. |
| FR-12 | Candidates shall receive results through the web portal and the mobile app, and candidates who opted in shall receive their grades by SMS. |
| FR-13 | Schools shall receive the results of their candidates through the school portal. |
| FR-14 | A candidate may appeal a result within 14 days of release; on appeal the candidate's originally captured marks and the moderated marks are both re-examined, and the candidate is told whether any difference arises from capture or from moderation. |
| FR-15 | Certificates shall be issued to every candidate with at least one graded component, and a certificate shall be verifiable online by an employer or university. |
| FR-16 | The platform shall provide the Ministry of Education with the statistical reports it requires after each sitting. |
| FR-17 | Every change to a registration, a mark, a grade or a certificate shall be attributable to a user or a system process and retained with the record. |

### 2.2 Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | The registration portal shall be available 99.9 percent of the time during the registration window, measured monthly. |
| NFR-2 | The results portal and app shall serve every candidate's result during the first hour after release with no more than 0.1 percent of requests failing, at the release-day load described in Section 4. |
| NFR-3 | Results reads shall complete within 2 seconds at the 95th percentile, measured from the API Gateway request to the complete response, in every one-minute interval of the first hour after release at the release-day load described in Section 4. |
| NFR-4 | SMS results shall be delivered to every candidate who opted in within 20 minutes of release. |
| NFR-5 | A result shall be visible to the candidate it belongs to and to that candidate's school, and to nobody else outside SECB's results team. |
| NFR-6 | Registration data, captured marks, moderated marks and grades shall be recoverable to within 5 minutes of any failure, including the loss of a database instance or an Availability Zone. |
| NFR-7 | Personal data shall be handled in accordance with the Personal Data Protection Act B.E. 2562 (2019): collected for the stated purpose, kept no longer than that purpose requires, and protected by appropriate security measures. |
| NFR-8 | Marks capture shall support 2,400 concurrent operators across 42 marking centres with a keying response time under 300 ms at the 95th percentile. |
| NFR-9 | Every grade shall be reproducible: a re-run of grade computation on the stored marks and boundaries shall produce the released grades exactly. |
| NFR-10 | The verification service shall answer 99 percent of verification requests within 2 seconds. |

## 3. Foundational Principles

- **P1. The database is the record.** The state of a registration, a script, a mark or a grade is whatever the authoritative database says; caches, search indexes and portals are projections of it.
- **P2. Nothing is lost between capture and award.** Every mark captured in a marking centre is retained, and every adjustment to it is a separate, attributable fact.
- **P3. The embargo is absolute.** Results exist inside the platform before release day, and nothing derived from them is shown outside the results team before the embargo lifts.
- **P4. A candidate sees only their own record.** Every candidate-facing read is scoped to the signed-in candidate.
- **P5. Reproducibility over speed.** Grade computation is deterministic and re-runnable; it is not optimised at the expense of being auditable.
- **P6. Data minimisation.** The platform collects what the examination requires and keeps it for as long as the examination and the certificate require.
- **P7. One Region, three Zones.** PHON runs in ap-southeast-7 across three Availability Zones; cross-Region replication is not part of the design.
- **P8. Fail closed on release.** If the platform cannot confirm that the embargo has lifted, it shows no result.
- **P9. Operators are people under pressure.** Marks capture and script tracking screens are designed for operators working long shifts; defaults are safe and corrections are easy.

## 4. Examination Cycle and Volumes

The NSC main sitting runs for three weeks in March, with a supplementary sitting in October. Registration for the March 2027 sitting opens on 1 November 2026 and closes on 15 December 2026, with a late-registration window to 15 January 2027 at a surcharge. Results are released on a date announced in February, at 08:00 Indochina Time (UTC+7), in mid-May.

| Measure | March 2026 (actual, previous systems) | March 2027 (planning) |
|---|---|---|
| Candidates | 487,000 | 500,000 |
| Registering schools | 3,860 | 3,900 |
| Private candidates | 31,500 | 35,000 |
| Papers per candidate (mean) | 7.1 | 7.0 |
| Scripts | 3.46 million | 3.5 million |
| Venues | 2,140 | 2,200 |
| Marking centres | 42 | 42 |
| Markers | 17,800 | 18,000 |
| Marks capture operators | 2,300 | 2,400 |
| Candidates opting in to SMS results | 71 percent | 75 percent |
| Verification requests per year | 410,000 | 450,000 |

Traffic is seasonal and spiky. During the registration window the portal averages about 40 requests per second over the day with a peak of about 300 in the evenings before the deadline. On release day the previous results website's logs show 6,100 requests per second sustained over the first ten minutes after 08:00, falling to about 1,500 by 09:00 and 200 by noon: two orders of magnitude above the ordinary daily average. The three release-day outages of the past six years all occurred in the first five minutes.

## 5. Target Architecture

PHON is a set of services on Amazon EKS behind Amazon API Gateway and Amazon CloudFront, with Amazon Aurora PostgreSQL as the authoritative store for registration, results and certificates, an Amazon RDS for PostgreSQL instance for marks capture inside the marking-centre network, Amazon MSK (Apache Kafka) as the event bus, Amazon S3 for files and archives, and Amazon Cognito as the identity provider for candidates, schools and verifiers.

**Figure 1.** Candidates, schools, verifiers and the Ministry reach PHON through CloudFront and API Gateway. Behind them run the Registration Service, Fee Service, Allocation Service, Script Tracking Service, Marks Capture Service, Moderation Service, Grading Service, Results Service, Notification Service, Certificate Service and Reporting Service. Each service owns its tables in the core Aurora cluster, except Marks Capture, which owns the marks capture RDS instance. Services publish domain events to MSK through a transactional outbox (Section 22). Marking-centre workstations reach the Marks Capture Service over the SECB private network through AWS Direct Connect.

| Component | Technology | Role |
|---|---|---|
| Edge | Amazon CloudFront, AWS WAF | Static assets, TLS termination, rate limiting, bot control |
| API front door | Amazon API Gateway (REST) | Authentication of tokens, routing to services |
| Compute | Amazon EKS, three node groups across three AZs | All services |
| Core database | Aurora PostgreSQL 16, writer and two readers across three AZs | Registration, allocation, results, certificates, audit |
| Marks capture database | RDS for PostgreSQL 16 | Captured and moderated marks |
| Event bus | Amazon MSK, 3 brokers, replication factor 3 | Domain events |
| Files and archive | Amazon S3 with Object Lock for the archive bucket | Uploads, script scan images, certificates, reports |
| Identity | Amazon Cognito user pools (candidates, schools, verifiers); SECB staff through corporate SSO | Authentication |
| Messaging | SMS aggregator Ratchaphruek Messaging (REST API); Amazon SES for email | Notifications |
| Payments | Chao Phraya Payment Gateway (bank-hosted, national real-time rail and cards) | Private-candidate payments |

## 6. Identity and Access

### 6.1 Candidates

Candidates authenticate with Cognito. School-registered candidates receive their account at registration: the school portal creates the account with the candidate's national identity number, name and date of birth from the school's upload, and the candidate activates it with a one-time code sent to the mobile number the school supplied, then sets a password. Private candidates create their account during self-registration (Section 7.2) and are identity-proofed through the national digital identity service (Section 27, DEC-05).

A signed-in candidate holds a Cognito session with an ID token (one hour) and a refresh token (30 days). The ID token carries the candidate's `candidate_id` as a custom claim. API Gateway validates the token's signature and expiry on every call with a Cognito authorizer and forwards the claims to the service.

### 6.2 Schools and SECB staff

School users (a principal and up to five examination officers per school) authenticate with Cognito with mandatory TOTP multi-factor authentication. Their token carries the `school_id`, and every school-portal query is filtered by it in the Registration and Results Services. SECB staff use corporate SSO with hardware-key multi-factor authentication; roles are Registration Officer, Finance Officer, Allocation Officer, Accommodation Officer, Head of Accommodations, Marking Centre Supervisor, Capture Operator, Moderation Officer, Awarding Secretary, Results Officer, Appeals Officer and Certificate Officer, each with a least-privilege policy. Elevated actions (changing a confirmed registration, entering a clerical correction, re-issuing a certificate) require a second staff member's approval recorded against the action.

### 6.3 Verifiers

Employers and universities register for the verification API through a self-service form, are approved by the Certificate Officer, and receive an API key tied to the organisation. Verification is described in Section 20.

## 7. Candidate Registration

### 7.1 School registration

Schools upload a CSV of candidates (national identity number, name in Thai and in Latin script, date of birth, sex, subject codes, accommodation request flag) or enter candidates one at a time in the school portal. The Registration Service validates each row against the national identity number check digit, the subject catalogue for the sitting, the school's approved subject list and the candidate's age (16 to 25 for a school candidate). Rows that fail are returned to the school with a reason; rows that pass create a `registration` in state `DRAFT`. The school confirms the upload, which moves the registrations to `SUBMITTED` and raises the school's invoice (Section 8.1).

A candidate may appear in one school's registration only. A second school submitting the same national identity number receives a conflict, with the first school's name, and the two schools resolve it with the Registration Officer.

### 7.2 Private candidates

Private candidates create an account, prove their identity through the national digital identity service, choose subjects and a preferred examination district, upload a photograph taken in the app, and pay (Section 8.2). Their registration moves from `DRAFT` to `SUBMITTED` on payment and to `CONFIRMED` when the Fee Service reconciles the payment.

### 7.3 Amendments

Until the close of registration, a school may change a candidate's subjects, and a private candidate may change their own. After the close, changes go through the Registration Officer with a second approval and a surcharge where the fee schedule requires one. Every change creates an `registration_change` row with the before and after values, the actor and the approval.

## 8. Fee Collection and Reconciliation

### 8.1 School invoices

When a school confirms its upload, the Fee Service computes the invoice from the fee schedule (350 baht per subject in 2027, with the reductions for scholarship holders that the Ministry funds) and posts it to the school portal with a payment reference. Schools pay by bank transfer quoting the reference. SECB's bank delivers a daily statement file (ISO 20022 camt.053) to an S3 bucket; the Fee Service matches each credit to an invoice by the payment reference, and where the reference is missing or malformed, by amount and payer name with a confidence score, leaving low-confidence matches for a Finance Officer to confirm. A matched invoice moves every registration on it to `CONFIRMED` in one transaction with the ledger posting.

### 8.2 Private candidate payments

Private candidates pay through the Chao Phraya Payment Gateway, which supports the national real-time payment rail and cards. The Fee Service creates a payment intent with a unique `payment_ref`, redirects the candidate to the gateway, and receives the outcome by a signed webhook. Webhooks are at-least-once and may arrive out of order; the Fee Service records each webhook by its gateway event identifier in a `payment_event` table with a unique constraint, so that a redelivered webhook is acknowledged and not processed twice, and applies state transitions only forward (a `SETTLED` payment never returns to `PENDING` because a late `PENDING` webhook arrives). Where the webhook is delayed, a reconciliation job polls the gateway for intents older than 10 minutes.

### 8.3 Fee ledger

Every fee, payment, refund and surcharge is a double-entry posting in a `fee_journal` table: debit and credit lines that must balance per invoice, enforced by a deferred constraint at commit. Postings are append-only; a refund is a reversing posting. The journal is exported nightly to the SECB finance ledger. Registrations are never confirmed without a balancing posting, and a daily report lists invoices whose postings and bank credits differ.

### 8.4 Refunds

A candidate who withdraws before the close of registration is refunded the subject fee less an administration charge, through the original payment method; a school's refund is netted against its next invoice. Refunds require a Finance Officer's approval and are posted as reversing journals.

## 9. Timetabling, Venues and Seat Allocation

### 9.1 Timetable

The Chief Examiner's Office publishes the timetable (paper, date, session, duration) in September. Each paper is a `paper` row with a `session` (morning or afternoon) and a duration; clashes between a candidate's own papers are detected at registration and resolved by the Allocation Service by scheduling the second paper in a supervised holding arrangement that the Operations Manual defines.

### 9.2 Venues

Approved venues (2,200 for the 2027 sitting) are schools and public halls, each with rooms, a seat count per room, accessibility attributes (ground floor, step-free access, accessible toilet) and a list of available accommodation rooms. Venue data is maintained by Allocation Officers and audited annually.

### 9.3 Allocation

Allocation runs after late registration closes on 15 January and after the accommodation decisions for the sitting (Section 10.2) are complete, which the Head of Accommodations confirms in the allocation console; applications close on 31 January (Section 10.1), so the run is scheduled for the second week of February, well before the seat lists for the March papers. For each paper and venue, the Allocation Service assigns candidates to rooms and seats with these rules: a candidate sits all papers in the same venue unless an accommodation requires another; candidates from the same school are distributed so that no two candidates from the same school and subject are adjacent; candidates with accommodations are placed first (Section 10); seat capacity is never exceeded; and no seat is allocated to two candidates for the same session. Each `seat_allocation` row copies the paper's examination date and session (`exam_date`, `session`) from the `paper` row at insert, and both rules are keyed on them: the one-candidate-per-seat rule is enforced by a unique constraint on (`venue_id`, `room_id`, `seat_no`, `exam_date`, `session`), and the no-two-venues rule by a unique constraint on (`candidate_id`, `exam_date`, `session`), so that two papers sat in the same session can neither share a seat nor place one candidate in two venues, whatever the batch computed; a clash resolved under Section 9.1 is allocated under the holding arrangement's own `session` value. The allocation batch inserts into `seat_allocation` in transactions of one room at a time, so that a conflict fails one room and not the run. The batch is checkpointed per venue and resumes from the last completed venue on restart; a full run takes about 70 minutes.

Allocation Officers can move a candidate or a room through the allocation console, under the same constraints. Seat lists and attendance registers are generated per room as PDFs five days before each paper.

## 10. Special-Needs Accommodations

### 10.1 Applications

Schools submit accommodation applications with supporting evidence (a medical report, an educational psychologist's assessment, or the school's own record of the arrangements the candidate normally uses) by 31 January. Private candidates submit their own. Each application is an `accommodation_application` with the requested arrangements and the uploaded evidence in S3 under a key-management-service key separate from the general uploads key.

### 10.2 Decisions

Two Accommodation Officers review each application independently in the accommodation console; where they disagree, the Head of Accommodations decides. Approved arrangements are recorded as structured `accommodation` rows (type, parameter such as extra-time percentage, papers to which it applies). About 2.1 percent of candidates received an accommodation in 2026.

### 10.3 Effect on allocation and timetabling

The Allocation Service places candidates with accommodations before all others: a candidate with extra time is seated in a room where every candidate has the same extra-time percentage or in a room on their own; a candidate with a reader or scribe is seated in a separate room with the staff member recorded on the seat list; enlarged-print and modified papers are added to the venue's paper requisition; a candidate who needs step-free access is placed only in rooms with that attribute. The extra time changes the candidate's paper end time, and the attendance register shows the adjusted end time for each seat.

## 11. Script Tracking and Chain of Custody

### 11.1 Identifiers

Each script has a pre-printed barcode label carrying the `script_id` (a 12-digit number with a check digit) that is bound to a candidate and paper when the invigilator scans the candidate's seat card and the script label together at the start of the paper. Script bundles (one per room per paper) carry a bundle barcode, and transport bags carry a bag barcode and a tamper-evident seal number.

### 11.2 Scan points

Scans are made with the Script Tracking app on SECB-issued handhelds at six points: seat binding in the hall, bundle sealing in the hall, bag collection by the courier, bag receipt at the marking centre, bundle opening at the marking centre, and return to archive. Each scan is a `custody_event` (script or bundle or bag identifier, scan point, location, scanner identity, time). The app queues scans offline and uploads them when connected, since many venues have no reliable mobile coverage.

### 11.3 Custody state

Scan events are published to the `scripts.custody` topic keyed by the scanning station identifier, so that the busiest stations spread across partitions, and the custody consumer sets a script's current location to the location of each event as it is processed, the most recently processed event being the current state. A script with no custody event for 24 hours after its expected arrival at the next scan point is flagged under FR-6, and a daily exceptions report lists scripts whose current location is behind their bundle's. The script image, where a centre scans scripts for archive, is stored in S3 with the `script_id` in the key.

### 11.4 Missing scripts

A missing script raises an incident to the Marking Centre Supervisor and the venue's chief invigilator with the last known location, the bundle and bag it travelled in, and the courier's run. Resolution (found, or confirmed lost with an assessed grade under the Regulations) is recorded against the script.

## 12. Marking Centres and Marker Allocation

Markers are accredited per component by the Chief Examiner's Office and hold a `marker` record with their accreditations, their employer school and their marking centre. The Marker Allocation job assigns bundles to markers so that a marker never receives a bundle containing a script of a candidate registered by the marker's employer school (FR-7), the exclusion being evaluated against the school of every script in the bundle because a room, and so a bundle, seats candidates from several schools (Section 9.3), that each marker's load stays within the component's daily quota, and that each bundle is marked by a single marker with a sample of 10 percent second-marked by a team leader for standardisation. Allocation is recomputed daily as markers report absence.

Marked scripts are returned to the centre's capture room in their bundles, with the marker's mark sheet (paper) inside the bundle: a pre-printed sheet of `script_id` barcodes and mark boxes per question.

## 13. Marks Capture with Double Entry

### 13.1 Capture flow

Capture operators key marks from the mark sheets at workstations in the capture room. The operator scans the bundle barcode and the `script_id` barcode, and the capture screen shows the paper's question structure (question number and maximum mark). The operator keys each question's mark; the screen refuses a mark above the maximum and a non-numeric entry, and totals are computed by the service, never keyed. Each keyed script is a `capture_entry` row with the operator, workstation, time and the per-question marks as a JSON list.

### 13.2 Independent second entry

Each bundle is keyed twice, by two different operators, and the service enforces the independence: the second-entry queue for a bundle excludes the operator who keyed the first entry and anyone on the same shift team, and the second-entry screen shows no first-entry values. When both entries exist, the service compares them question by question. A bundle with no differences is accepted and its marks written to `script_mark`. A bundle with differences goes to a resolution queue from which the two operators who keyed the entries are excluded, where a third operator's screen shows the two entries side by side with the differing questions highlighted and the operator keys the resolved value from the mark sheet; the resolution is a third `capture_entry` with `role = RESOLUTION` and the resolving operator's identity. Only resolved values reach `script_mark`.

### 13.3 Performance and ergonomics

The capture service is stateless and horizontally scaled; every keystroke-level action is local to the browser, and the service is called once per script. Keying response time is measured per call and reported per centre against NFR-8. Capture screens use large type, a fixed tab order and audible confirmation, and an operator can mark a sheet as illegible, which routes it to the team leader.

### 13.4 Capture statistics

Per-operator discrepancy rates are computed daily and operators above twice the centre median are retrained; per-centre discrepancy rates are reported to the Chief Examiner's Office weekly.

## 14. Moderation and Mark Adjustment

### 14.1 Purpose

Moderation aligns marking standards across markers and centres. For each component, the Chief Examiner's Office compares the team leaders' second marks with the markers' marks, and approves an adjustment formula per marker (typically a linear adjustment of the form `adjusted = a + b * mark`, bounded to the mark range) where a marker's standard differs from the team leaders' by more than the tolerance for the component.

### 14.2 Applying adjustments

Adjustments are applied by writing one `mark_adjustment` row per script, carrying the `script_mark` row it applies to, the moderation run, the formula parameters, the captured mark and the resulting moderated mark; `script_mark.mark` is never updated after capture, and the moderated mark the Grading Service reads is the captured mark with the adjustment of the signed run applied, so that an appeal has both values and the difference between them. The moderation run records, per marker and component, the formula applied and the number of scripts affected. A moderation run for a component is executed once the component's capture is complete, by a Moderation Officer, and produces a moderation report listing each marker's formula and the distribution of marks before and after. The Chief Examiner's Office signs the report, and the component is then available to grade computation.

### 14.3 Re-runs

Where the Chief Examiner's Office changes a formula after a run, the Moderation Officer re-runs moderation for the affected marker's scripts with the new formula; the re-run writes new `mark_adjustment` rows and marks the earlier run's rows for those scripts `SUPERSEDED` (they are never deleted), and the report records both runs.

## 15. Grade Computation and Grade Boundaries

### 15.1 Boundaries

The Awarding Committee sets grade boundaries per component after moderation, using the mark distribution, the previous year's boundaries and a sample of scripts at each proposed boundary. Boundaries are recorded as a `grade_boundary_set` with a version, the approving committee minute reference and the committee chair's electronic signature, and are immutable once signed; a change creates a new version.

### 15.2 Computation

The Grading Service computes each candidate's component grade from the moderated mark and the signed boundary set, and the subject grade from the component grades according to the subject's aggregation rule (weighted sum of uniform marks per the Regulations). A computation run records the identifiers and versions of every input (the boundary set version, the moderation run identifiers and a SHA-256 hash of the moderated marks for the component) in a `grading_run` row, so that a re-run with the same inputs is verifiable against the released grades (NFR-9). The computation is a pure function of its inputs: it reads the inputs once into memory, computes, and writes `grade` rows in one transaction with the run record.

### 15.3 Checks

Before release, the Awarding Secretary runs the grade distribution report (grades per subject against the previous three years) and the anomaly report (candidates whose grade in three or more subjects differs by more than two grades from the median grade of their school's candidates in the same subject, and centres whose grade distribution for a component differs from the national distribution by more than the tolerance the Awarding Committee sets), both computed from the graded data itself, and signs off the run.

## 16. Appeals, Re-marks and Clerical Corrections

### 16.1 Clerical corrections before release

Between the Awarding Secretary's sign-off and release day, marking centres may report clerical errors (a mark keyed against a different candidate's script, a resolved value that does not match the mark sheet). The Results Officer enters a clerical correction with a second approval, and the Grading Service recomputes the affected candidate's grades; corrections may be entered until 07:00 on release day, and the results dataset is locked at 07:00 so that the result released at 08:00 reflects every correction entered before the lock.

### 16.2 Appeals after release

A candidate, or their school on their behalf, may request a clerical check or a re-mark within 14 days of release through the portal, paying the fee set in the Regulations (refunded if the grade changes). An Appeals Officer assigns the re-mark to a senior examiner who did not mark the script. The outcome is recorded as an `appeal` with its result and, if the grade changes, a new `grade` row supersedes the released one, the candidate and school are notified, and the certificate is re-issued (Section 20.2).

## 17. Results Release and Embargo

### 17.1 Embargo

The release time is 08:00 Indochina Time on the published release day. No result or statistic derived from the results leaves the platform before the embargo lifts, and this applies equally to candidates, schools and the Ministry. Inside SECB, only the Results Officer role (for clerical corrections and the release console) and the Awarding Secretary role (for the Section 15.3 reports and sign-off) can view results before release, and every such view is logged.

### 17.2 Release mechanism

The Results Service holds a `release` row per sitting with the `release_at` timestamp set by the Awarding Secretary and co-signed by the Director of Examinations. Each Results Service pod holds an embargo state: the `release_at` value for the sitting and the offset between the Aurora writer's clock and the pod's own clock, both refreshed from the writer every second, so that there is one clock, the writer's, and a replica's clock is not consulted. Every results read checks that state, and the Results Service refuses with HTTP 423 while the writer's time, computed from the pod's clock and the stored offset, has not reached `release_at`; a pod whose state is older than five seconds, or which holds no release row for the sitting, serves no result (P8). The once-a-second refresh of that state is the only database access on the release path.

### 17.3 Release-day operations

A release-day runbook covers the 48 hours around release: a change freeze from 48 hours before, scaling of the results tier at 06:00, a smoke test with synthetic candidates at 07:30, and a war room with the SMS aggregator and the Ministry's press office on a call bridge from 07:45. The Results Officer confirms the release at 08:00 from the console, which has no effect on the stored `release_at`; it records the confirmation only.

## 18. Results Delivery Channels: Web, App and SMS

### 18.1 Web portal and app

The results portal is a static single-page application served by CloudFront; the mobile app (iOS and Android) uses the same API. A candidate signs in with Cognito, and the app calls `GET /results/{candidate_id}` through API Gateway. The response carries each subject's grade, the component uniform marks, and the certificate number once issued.

### 18.2 Results Service

The Results Service authorises a request by validating the Cognito session token that API Gateway forwards, and it serves `GET /results/{candidate_id}` for any `candidate_id` in the path when the token is valid. The response is the rendered result object for that `candidate_id` in the results bucket (Section 25.2), returned as stored; on the release path the service reads its embargo state (Section 17.2) and the object, and nothing else.

### 18.3 Statement of results

The portal offers a PDF statement of results, rendered together with the result object (Section 25.2) from the same data, signed with the SECB document-signing key and served as stored; a statement rendered after the certificate is issued carries a QR code that resolves to the verification service (Section 20.3).

### 18.4 SMS results

Candidates who opted in receive one SMS per candidate at release, with the grade per subject in a fixed template (subject code and grade, separated by spaces) that fits a single message. The Notification Service queues one message per candidate in grade-independent order at 07:55 and begins sending at 08:00:00 through two aggregators, Ratchaphruek Messaging and Dok Bua Telecom, each over its REST API. The contracted throughput is 400 messages per second from Ratchaphruek Messaging and 200 from Dok Bua Telecom, 600 in all, so the 375,000 messages for candidates who opted in are handed to the aggregators within about 11 minutes of the embargo lifting, and with the aggregators' own delivery time of under 5 minutes at that rate the last message reaches its handset within about 16 minutes, inside NFR-4. Delivery receipts are stored against the message; a candidate whose message is rejected or expires receives an email instead.

### 18.5 Contact centre

SECB's contact centre has a read-only results console scoped to the candidate the agent has identified by national identity number and date of birth, with every lookup logged against the agent.

## 19. School Portal and Ministry Reporting

### 19.1 School results files

School result files, one CSV and one PDF per school listing each candidate's grades, are published to the school portal at 08:00 on release day, at the same moment as the candidate release, and the school's briefing to its candidates follows the release. School users download the files from the portal with their multi-factor session; downloads are logged.

### 19.2 School statistics

From 09:00 on release day the school portal shows the school's grade distribution per subject against the national distribution, and the school's three-year trend.

### 19.3 Ministry reporting

The Reporting Service produces the national results statistics for the Ministry of Education: grades per subject by province, by school type and by sex, and the pass rate per district. The statistics are computed in the core Aurora cluster and published to the Ministry's portal at 09:00 on release day. In addition, a nightly export of the candidate-level dataset (national identity number, name, date of birth, sex, school, province, subjects and grades) is written to the Ministry's analytics tenant, which is hosted for the Ministry by Lotus Insight Analytics in ap-southeast-1 (Singapore), so that the Ministry can run its own longitudinal analysis against earlier cohorts. The export runs from 1 June until the following sitting's registration opens.

## 20. Certificates and Verification

### 20.1 Issue

Certificates are generated by the Certificate Service as PDFs from the released grades once the appeals window has closed, each with a 16-character certificate number (a random number with a check character, allocated from a secrets-manager-backed generator, never sequential) and a digital signature by the SECB signing key held in AWS KMS. The PDF is written to the archive bucket under Object Lock (30 years) and made available to the candidate in the portal; a printed certificate is produced by the Board's printing contractor from the same PDF. A certificate is a `certificate` row referencing the `grading_run` and the `grade` rows it reflects.

### 20.2 Re-issue

A certificate is re-issued after a successful appeal or a name correction; the earlier certificate number is marked `SUPERSEDED` and verification of it returns that status with the date, so that a superseded certificate cannot be presented as current.

### 20.3 Verification

Verifiers call `POST /verify` with their API key and the certificate number, the candidate's name as printed and the candidate's date of birth; the service returns `VALID`, `SUPERSEDED` or `NO_MATCH`, and for `VALID` the grades on the certificate. It never searches by name alone and never returns a record for a certificate number without a matching name and date of birth, so that a verifier learns nothing it was not given by the candidate beyond the grades the candidate chose to present. Requests are rate-limited per verifier (600 per minute) and all requests are logged with the verifier identity for the candidate to see in their portal ("who verified my certificate"). The certificate, and any statement of results produced after the certificate is issued, carries a QR code encoding a signed, time-unlimited verification token that opens a page with the same fields; the token is bound to the certificate number and reveals nothing more than the certificate itself, and a statement produced before issue carries no QR code, since there is no certificate number to bind one to.

## 21. Data Model

### 21.1 Core cluster (Aurora PostgreSQL 16)

Principal tables: `candidate` (national identity number, names, date of birth, sex, contact details, school or private, Cognito identity), `registration` (candidate, sitting, state, subjects), `registration_change`, `fee_invoice`, `fee_journal`, `payment_event`, `accommodation_application`, `accommodation`, `venue`, `room`, `paper`, `seat_allocation`, `script` (`script_id`, candidate, paper, bundle), `custody_event`, `marker`, `marker_allocation`, `grade_boundary_set`, `grading_run`, `grade`, `appeal`, `release`, `certificate`, `verification_log`, `audit_log`. Large tables (`custody_event`, `verification_log`, `audit_log`) are partitioned by month.

### 21.2 Marks capture instance (RDS for PostgreSQL 16)

Tables: `capture_bundle`, `capture_entry` (one row per operator entry per script, `role` in `FIRST`, `SECOND`, `RESOLUTION`), `script_mark` (one row per script: `script_id`, component, `mark` as the accepted captured total, `question_marks` as a JSON list; immutable after acceptance), `mark_adjustment` (one row per script per moderation run: `script_mark` reference, `moderation_run_id`, formula parameters, captured mark, moderated mark, status `CURRENT` or `SUPERSEDED`), `moderation_run` (component, marker, formula parameters, scripts affected, signed-by, time). Moderated marks are read by the Grading Service through a read-only database role on the instance.

### 21.3 Identifiers and audit

Every table carries `created_at`, `created_by`, `updated_at` and `updated_by`; every write by a staff role is additionally recorded in `audit_log` with the before and after values (FR-17). Candidate-facing tables are keyed by a surrogate `candidate_id` (UUID); the national identity number is stored encrypted at rest with a column-level key and indexed by a keyed hash.

## 22. Event Bus and Transactional Outbox

Domain events (`registration.confirmed`, `payment.settled`, `allocation.completed`, `custody.scanned`, `capture.accepted`, `moderation.signed`, `grades.computed`, `results.released`, `certificate.issued`) are written to an `outbox` table in the same transaction as the state change they describe, and relayed to MSK by a relay with `acks=all` and an idempotent producer, with the outbox row marked published only after the broker acknowledges. Consumers deduplicate by `event_id` in the same local transaction as their effect. Topics are keyed by the aggregate identifier (candidate, script, bundle or certificate) so that the events of one aggregate are consumed in commit order, except where a section states a different key for throughput. The cluster has 3 brokers, replication factor 3 and `min.insync.replicas` 2; topics have 12 partitions and 7 days' retention, against a peak of about 400 events per second during capture. Every event carries a `event_version` and consumers ignore fields they do not know.

## 23. Data Protection and Retention

### 23.1 Legal basis and data classes

SECB processes candidate data under its statutory function in the Examinations Act and the PDPA. Data classes are: identity (national identity number, names, date of birth, sex, photograph), contact (mobile, email, address), examination (registration, allocation, marks, grades, appeals), accommodation (applications and supporting evidence, which is health data under the PDPA's sensitive-data provisions), financial (invoices, payments), and verification (who verified what). Access to each class is by role (Section 6.2), and the Data Protection Impact Assessment is a companion document.

### 23.2 Retention

Results and certificates are retained for 30 years, the period over which SECB must answer certificate queries; the candidate record, including the accommodation application and its supporting medical and psychological evidence, is retained for the same 30 years alongside the result so that any later query about the candidate's examination can be answered from a complete record. Contact details are deleted two years after the candidate's last sitting. Script images are deleted one year after release unless under appeal. Fee records are retained for ten years under the Revenue Code. Audit logs are retained for ten years. Deletion is performed by a monthly job that writes a deletion record (what class, how many rows, which rule) to the audit log.

### 23.3 Security measures

All data is encrypted at rest (KMS) and in transit (TLS 1.2 or later). The national identity number is encrypted at column level (Section 21.3). Accommodation evidence is stored under its own key with access limited to the Accommodation roles. Staff access is through corporate SSO with hardware keys and is logged; candidate and school access is through Cognito. An annual penetration test and a pre-release test of the results tier are part of the acceptance criteria (Section 29.2).

### 23.4 Candidate rights

Candidates can see their data, their verification log and their accommodation decision in the portal, and can request correction of names and contact details; corrections to names after certificate issue follow the re-issue process (Section 20.2). Requests for erasure are answered with reference to the statutory retention of results, and contact details are erased on request.

## 24. Resilience, Availability and Recovery

### 24.1 Core cluster

The core Aurora cluster has a writer and two readers in three Availability Zones, with automatic failover in under 60 seconds, continuous backup to S3 with point-in-time recovery to any second in the last 35 days, and a nightly snapshot copied to a second account. EKS node groups span the three zones with pod anti-affinity per service; MSK brokers are one per zone.

### 24.2 Marks capture instance

The marks capture database is a Multi-AZ RDS for PostgreSQL deployment (db.r6g.xlarge, with a synchronous standby in ap-southeast-7b) with continuous backup to S3 and point-in-time recovery to any second in the last 35 days, and on loss of the instance or its zone the standby is promoted within about two minutes with no committed transaction lost. The instance is isolated from the internet and reachable only from the capture service and the marking-centre network. Capture operators' sessions are held in the browser, so that an operator whose request fails can resubmit the script once the service is back.

### 24.3 Dependencies

Loss of the SMS aggregator delays SMS results; the web and app channels are unaffected and the queue is sent when the aggregator returns. Loss of the payment gateway blocks private-candidate payments; registrations remain in `DRAFT` and candidates are told to return later. Loss of Cognito blocks sign-in for candidates and schools; staff consoles use corporate SSO and remain available.

### 24.4 Recovery exercises

A quarterly exercise fails the Aurora writer and a capture-service node group; the release-day runbook is rehearsed in full in April with synthetic traffic.

## 25. Capacity and Performance

### 25.1 Registration tier

The registration tier is sized for the evening peak of about 300 requests per second with headroom to 1,000: six Registration Service pods, two Fee Service pods, and the core Aurora cluster at db.r6g.2xlarge. Bulk uploads are processed asynchronously with a progress view.

### 25.2 Results tier

The results tier is sized for the observed release-day peak and serves pre-rendered objects. At 02:00 on release day the Results Service renders every candidate's result (the JSON response and the PDF statement of results) from the results snapshot taken at that time into a private S3 bucket keyed by `candidate_id`, and a results read checks the pod's embargo state (Section 17.2) and returns the rendered object, so that the release path reads no database beyond the once-a-second refresh of that state. The tier is sized for 8,000 requests per second with 120 Results Service pods (40 per zone, each measured at 90 requests per second against S3 in the prototype), pre-warmed by the 06:00 runbook step (Section 17.3), with S3 request rates spread across 64 key prefixes. Rendered objects are immutable from the 02:00 render until the scheduled re-render at 20:00 on release day, which picks up the day's appeals and clerical entries, so that every candidate reads the same object throughout the release window and no read depends on the database or the cache state.

### 25.3 Front door

API Gateway sits in front of the results tier with a stage-level throttle set to 8,000 requests per second so that the gateway, rather than the services, sheds load in an extreme case. The account-level throttle that API Gateway applies by default is 10,000 requests per second with a burst of 5,000 requests in every Region, which is above the 6,100 requests per second observed on the previous release day, so no quota increase is requested. CloudFront serves the static portal assets and absorbs the asset requests that accompany each results read.

### 25.4 Marks capture tier

The capture tier is sized for 2,400 concurrent operators at one service call per script every 20 seconds (120 calls per second), served by six Marks Capture Service pods and the db.r6g.xlarge instance; the prototype measured 85 ms at the 95th percentile for the accept-script call at twice that load.

### 25.5 Batch windows

Allocation runs in about 70 minutes (Section 9.3); moderation runs per component in under 10 minutes; grade computation for the full cohort runs in about 25 minutes; certificate generation for 500,000 candidates runs over one night.

## 26. Observability and Audit

Every service emits structured logs, metrics and traces with the request identifier, the service, the candidate or school identifier where present (as the surrogate, never the national identity number), and the outcome. Release-day dashboards show request rate, error rate and latency per channel, SMS send and receipt rates, and the embargo state. Alerts page the on-call engineer for error rates above 0.5 percent over one minute, latency above the budget for five minutes, custody events not processed within 10 minutes, outbox lag above one minute, and any results read served while `release_at` is in the future. Audit logs (Section 21.3) are written to the archive bucket daily under Object Lock.

## 27. Confirmed Decisions

| ID | Decision | Rationale |
|---|---|---|
| DEC-01 | AWS, ap-southeast-7 (Thailand), three Availability Zones; no cross-Region replication | Data remains in the country; three zones meet NFR-6 for the core |
| DEC-02 | Aurora PostgreSQL 16 for the core; Multi-AZ RDS for PostgreSQL 16 with point-in-time recovery for marks capture, isolated in the marking-centre network | Separation of the capture tier from the internet-facing tier; NFR-6 for captured marks |
| DEC-03 | Amazon MSK with a transactional outbox for all domain events | No dual writes; per-aggregate ordering |
| DEC-04 | Amazon Cognito for candidates, schools and verifiers; corporate SSO for staff | Managed identity; MFA for schools and staff |
| DEC-05 | Private candidates are identity-proofed through the national digital identity service, at identity assurance level 2, from the opening of registration for the March 2027 sitting | Prevents impersonation at registration; removes the in-person document check at district offices |
| DEC-06 | Double entry by two independent operators with third-operator resolution for all marks | Capture accuracy; the Chief Examiner's Office requires it |
| DEC-07 | Moderation applied per marker by a linear formula approved by the Chief Examiner's Office | Established practice under the Regulations |
| DEC-08 | Release at 08:00 Indochina Time, embargo enforced by the Results Service against the writer clock | One clock, fail closed |
| DEC-09 | SMS results through two aggregators, Ratchaphruek Messaging (400 messages per second) and Dok Bua Telecom (200 messages per second) | Combined 600 messages per second covers NFR-4 with a second provider for resilience |
| DEC-10 | Certificates signed with a KMS-held key, random certificate numbers, verification by number plus name plus date of birth | Minimal disclosure; verifiable without an account |
| DEC-11 | Candidate-level nightly export to the Ministry's analytics tenant | Ministry's longitudinal analysis programme |
| DEC-12 | Results and certificates retained 30 years; contact details two years | Certificate queries; PDPA retention principle |

## 28. Pending Backlog

| ID | Item | Status |
|---|---|---|
| PB-01 | Contract renewal with the printing contractor for printed certificates | Procurement; decision by December 2026 |
| PB-02 | Agreement with the National Digital Identity Office for the national digital identity integration (identity assurance level 2 for private candidates) | Draft agreement under legal review; the production API is not expected before the third quarter of 2027, with sandbox access from April 2027 |
| PB-03 | On-screen marking pilot for two components in the October 2027 supplementary sitting | Scoping |
| PB-04 | WAF rule tuning for the mobile app's traffic pattern | Awaiting app beta traffic |
| PB-05 | Ministry statistics format for 2027 (the Ministry is revising its provincial boundaries) | Awaiting the Ministry |
| PB-06 | Accessibility audit of the results portal against WCAG 2.2 AA | Scheduled for the February 2027 build |

## 29. Validation and Acceptance Criteria

### 29.1 Functional

| Requirement | Acceptance test |
|---|---|
| FR-1 | A school uploads a 500-row CSV with 20 seeded invalid rows; the 480 valid rows create registrations and the 20 are returned with reasons. A private candidate registers end to end in the test environment. |
| FR-3 | A bank statement file with 1,000 credits, 50 with malformed references, is matched; the 950 are confirmed automatically and the 50 appear in the Finance queue. A redelivered payment webhook changes nothing. |
| FR-4 | Allocation for a test cohort of 50,000 candidates produces no duplicate seat and no candidate in two venues, as checked by direct database queries. |
| FR-5 | Twenty test candidates with each accommodation type are allocated, and the seat list shows the correct room type and adjusted end time for each. |
| FR-6 | A script with no scan at the marking centre 24 hours after its bag's receipt appears on the missing-script report. |
| FR-7 | Marker allocation for a test component places no bundle containing a script from a marker's employer school with that marker, as checked by a direct query joining `marker_allocation`, `script`, `candidate` and `marker`. |
| FR-8 | Two operators from different shift teams key a batch of 200 scripts in the first-entry and second-entry screens from two copies of the mark sheets into which 30 differences have been seeded; the comparison report must list exactly those 30 scripts, the resolution queue must offer them to a third operator only (the first two operators must not see them), and `script_mark` must hold only resolved values for the 30 and the agreed values for the 170. |
| FR-9 | A moderation run on a test component applies the approved formula; the moderation report lists each marker's formula and count. |
| FR-10, NFR-9 | A grade computation run is repeated on the same inputs and produces byte-identical `grade` rows. |
| FR-11 | At 07:59:50 a synthetic candidate's results read returns HTTP 423; at 08:00:00 by the writer's clock, the pods' embargo state having been refreshed within the preceding second (Section 17.2), it returns the result. |
| FR-12 | A synthetic candidate receives the result in the portal, the app and by SMS to a test handset. |
| FR-13 | A test school downloads its results file and the file matches the candidates' released grades. |
| FR-14 | A test appeal changes a grade; the new grade supersedes the old, the candidate and school are notified, and the certificate is re-issued as `SUPERSEDED` plus new. |
| FR-15 | A verifier submits a valid certificate number with matching name and date of birth and receives `VALID` with grades; the same number with another name receives `NO_MATCH`. |
| FR-16 | The Ministry confirms receipt of the national statistics on the test release day. |
| FR-17 | Every staff write in the test run has an `audit_log` row with before and after values. |

### 29.2 Non-functional

| Requirement | Acceptance test |
|---|---|
| NFR-1 | Availability of the registration portal is measured over the November test window from synthetic checks every minute. |
| NFR-2 | A load test replays the previous release day's request pattern scaled to 8,000 requests per second for 30 minutes against the production-sized results tier serving rendered objects for 500,000 synthetic candidates; failures are below 0.1 percent. |
| NFR-3 | During the NFR-2 test the 95th percentile response time is computed per one-minute interval from the API Gateway access logs and is under 2 seconds in every interval. |
| NFR-4 | 375,000 test messages are sent to the aggregator's test endpoint and the time to the last accepted message is recorded. |
| NFR-5 | A penetration test of the results tier before release day finds no way for a signed-in test candidate to see a different candidate's result. |
| NFR-6 | The core Aurora writer and the marks capture primary are each failed over during a write load and the committed transactions lost are counted (the target is none); point-in-time recovery of both to a chosen second is exercised in the April rehearsal and the recovered data is compared with the source. |
| NFR-7 | The Data Protection Impact Assessment is signed off by the Data Protection Officer before registration opens. |
| NFR-8 | 2,400 simulated operators key scripts for one hour and the 95th percentile response time is under 300 ms. |
| NFR-10 | 50 verification requests per second for 10 minutes; 99 percent answered within 2 seconds. |

## 30. Implementation Readiness Assessment and Build Phases

### 30.1 Readiness

| Area | Assessment |
|---|---|
| Registration and fees | Ready |
| Allocation and accommodations | Ready |
| Script tracking | Ready; handheld procurement in progress |
| Marks capture | Ready |
| Moderation and grading | Ready |
| Appeals | Ready |
| Results release and channels | Ready |
| School portal and Ministry reporting | Ready, subject to PB-05 for the statistics format |
| Certificates and verification | Ready |
| Data protection | Ready, subject to the DPIA sign-off |
| Resilience | Ready |

### 30.2 Build phases

| Phase | Scope | Dates | Dependencies outstanding |
|---|---|---|---|
| 1 | Identity, registration, fees, school portal (registration functions) | July to October 2026, live 1 November 2026 | None |
| 2 | Allocation, accommodations, script tracking, handheld app | November 2026 to January 2027 | Handheld procurement |
| 3 | Marks capture, moderation, grading, appeals (pre-release functions) | December 2026 to February 2027 | None |
| 4 | Results release, channels, school results, Ministry reporting, certificates, verification | January to April 2027, rehearsal in April, release in May 2027 | PB-05 |
| 5 | On-screen marking pilot | June to October 2027 | PB-03 |
