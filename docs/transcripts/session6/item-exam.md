# Worker note: synthetic item exam_platform (synthetic-exam-platform-001)

Date: 2026-10-04 (finished 23:51 +08).
Brief: the SIT planner's S4 item-authoring brief under Malcolm's word of 4 Oct 2026 22:40 ("yes" to plan D: ten documents, five of them new), under his delegation of shot calling (3 Oct 02:50).
Branch `s4/item-exam` from 5f4eeb6; this worker wrote `design_v1.md`, `design_v2.md`, the key, the canonical key, the PDFs and the README.
Not opened: `eval/blind/`, `docs/live_runs/`, the source of `spec/convert_answer_keys.py` and `eval/build_pdfs.py`, the clinical_rpm, research_lakehouse and iot_fleet items, the hospital designs.
Read for shape: the payments_orchestration key, README and the first 60 lines of its design_v1.md; the hospital_scheduling README and worker note; the four hospital wrappers; `spec/taxonomy.yaml`; handover section 6.

## Process notes

- `eval/build_pdfs.py` and `spec/convert_answer_keys.py` list items in code. Both were run unchanged on disk through scratchpad wrappers copied from the hospital ones (`author_exam2/build_exam_pdfs.py`, `author_exam2/convert_exam.py`) that add this item to `ITEMS` (and `NEEDS_EXTERNAL = {"F05", "F06"}`) in memory only. The registering worker must add these entries for real.
- The `markdown` module was pip-installed into this worktree's `.venv` (an environment change, not a repository change). LibreOffice is `/opt/homebrew/bin/soffice`.
- `design_v2.md` is generated from `design_v1.md` by `author_exam2/make_v2.py`: 20 exact, single-occurrence replacements (title block, revision history and "Changes since version 1.0" section, then the seven changes, the 25.2 rewrite that carries F15, and the DEC-02, DEC-09, 21.2 and 29.2 rows that follow from them). `answer_key.json` is written by `author_exam2/make_key.py`, which reads the anchor pages from the PDFs through `sit_review_agent.ingest.pdf.ingest` and asserts each anchor quote is an exact, unique match on its page; every anchor is a fragment of one PDF line. `author_exam2/find_anchors.py` was used to pick the fragments (five first candidates spanned a line break and were shortened).
- F05's external fact: this worker fetched https://docs.aws.amazon.com/apigateway/latest/developerguide/limits.html on 2026-10-04 ("Throttle quota per account, per Region ... 10,000 requests per second (RPS) with an additional burst capacity provided by the token bucket algorithm, using a maximum bucket capacity of 5,000 requests", "Can be increased: Yes", and the footnote "For the following Regions, the default throttle quota is 2500 RPS and the default burst quota is 1250 RPS: ... Asia Pacific (Malaysia), Asia Pacific (Thailand), and Mexico (Central)"), and the companion page https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-request-throttling.html (per-Region account-level token bucket, 429 on overrun); recorded with `verified: true`. The design runs in ap-southeast-7, Asia Pacific (Thailand), and states the 10,000 / 5,000 default "in every Region". F06's external fact (PDPA Sections 26, 28 and 40) is recorded with `verified: false`.
- `scripts/leakage_grep.py` with this item present first reported, from this item: `schema_version` (name, Section 22), `Upper` (proper noun, from "National Upper Secondary Certificate"), `NOT_FOUND` (name, Section 20.3), `another candidate` (TF-IDF pair, 16.1 and the key), `json array` (TF-IDF pair, 13.1 and 21.2) and `Developer` (proper noun, "Developer Guide" in the key). Renamed: `schema_version` to `event_version`; "National Upper Secondary Certificate (NUSC)" to "National Secondary Certificate (NSC)"; `NOT_FOUND` to `NO_MATCH`; "another candidate's" to "a different candidate's" and "any other candidate" to "a different candidate" (designs and key); "as a JSON array" to "as a JSON list"; "AWS API Gateway Developer Guide" to "the AWS API Gateway documentation" (key only; the URL path `developerguide` stays). After that only `'never leave' (tfidf; from eval/synthetic/payments_orchestration)` against `agent/sit_review_agent/tools/gateway.py:1080` remains, the same hit the iot_fleet and hospital items surfaced; reported, not fixed (it needs an allow-list entry in the registering change). The renames changed no anchor quote and no flaw sentence's substance; v2, the PDFs, the key and the canonical key were regenerated after them (F15's anchor moved from page 14 to page 13 of design_v2.pdf).
- Tests: none run (no test enumerates `eval/synthetic/*`, per the sibling notes). Not edited: `eval/prereg.yaml`, `eval/build_pdfs.py`, `spec/convert_answer_keys.py`. Nothing pushed.
- Framing: every flaw in the designs, the key and this note is written as a design property or a missing or broken control, never as a procedure; F15 is non-security (a consistency contradiction between the v2 render schedule and the unchanged corrections window).

## Commands (from the worktree root, `S` = the scratchpad folder `author_exam2`)

    .venv/bin/python $S/make_v2.py
    .venv/bin/python $S/build_exam_pdfs.py /Users/malco/Desktop/SIT-wt/item-exam
    .venv/bin/python $S/find_anchors.py
    .venv/bin/python $S/make_key.py
    PYTHONPATH=agent .venv/bin/python $S/convert_exam.py /Users/malco/Desktop/SIT-wt/item-exam --tier synthetic --verify-anchors
    .venv/bin/python scripts/leakage_grep.py

Build output: `design_v1.pdf: 16 pages`, `design_v2.pdf: 16 pages`, `ALL CHECKS PASSED`.
Converter output for this item: `flaws 15 (v1 14, v2 1)`, `v2_status {'fixed': 7, 'unchanged': 7, 'introduced': 1}`, `needs_external_research 2; sound sections 5`, `note: flaw_counts equal to recomputed v1 counts`, `scored_run_ready False`; overall `60 flaws converted across 4 keys; 0 key(s) failed validation`. The other three canonical keys were rewritten byte-identical (git shows no change).

Anchor pages (design_v1 unless stated): F01 8, F02 10, F03 12, F04 13, F05 13, F06 10, F07 10, F08 15, F09 14, F10 7, F11 3, F12 10, F13 12, F14 2, F15 13 (design_v2).

## Word counts (wc -w)

        8849 design_v1.md
        9391 design_v2.md
       18240 total

## No-label scan

    $ grep -ciE '\bF[0-9]{2}\b|flaw|planted|intentional|deliberate|bug|TODO|FIXME|incorrect|mistake|wrong|regression|known issue|answer key' design_v1.md design_v2.md
    design_v1.md:0
    design_v2.md:0

Em dash count (grep -c of U+2014) in both designs, the key, the canonical key, the README and this note: 0 each.

## Per-flaw carrying sentences (v1) and their v2 state

Fixed in v2: F01, F03, F04, F07, F08, F11, F12. Unchanged: F02, F05, F06, F09, F10, F13, F14. New in v2: F15 (from the F04 change).

### F01 (critical, internal_contradiction)

- v1 (14.2): Adjustments are applied by updating `mark` on the `script_mark` row to the moderated value, and the moderation run records, per marker and component, the formula applied and the number of scripts affected. (Against FR-14 and 16.2: on appeal the originally captured marks and the moderated marks are both re-examined.)
- v2 (14.2): Adjustments are applied by writing one `mark_adjustment` row per script, carrying the `script_mark` row it applies to, the moderation run, the formula parameters, the captured mark and the resulting moderated mark; `script_mark.mark` is never updated after capture, and the moderated mark the Grading Service reads is the captured mark with the adjustment of the signed run applied, so that an appeal has both values and the difference between them. (14.3 and 21.2 follow.)

### F02 (critical, security_privacy_gap)

- v1 (18.2): The Results Service authorises a request by validating the Cognito session token that API Gateway forwards, and it serves `GET /results/{candidate_id}` for any `candidate_id` in the path when the token is valid.
- v2: (unchanged; only the following sentence, about what the response is built from, changed with the F04 fix)

### F03 (critical, internal_contradiction)

- v1 (24.2): The marks capture database is a single-Availability-Zone RDS for PostgreSQL instance (db.r6g.xlarge) in ap-southeast-7a with automated daily snapshots at 02:00 retained for 35 days, and on loss of the instance or its zone it is restored from the most recent snapshot into another zone. (Against NFR-6: recoverable to within 5 minutes including instance or zone loss.)
- v2 (24.2): The marks capture database is a Multi-AZ RDS for PostgreSQL deployment (db.r6g.xlarge, with a synchronous standby in ap-southeast-7b) with continuous backup to S3 and point-in-time recovery to any second in the last 35 days, and on loss of the instance or its zone the standby is promoted within about two minutes with no committed transaction lost. (DEC-02 and the NFR-6 test follow.)

### F04 (critical, scalability_failure_mode)

- v1 (25.2): The results tier is sized from the sustained average of the previous release day (about 40 requests per second over the 24 hours) with a multiplier of 3 for the release hour, giving a design load of 120 requests per second served by six Results Service pods (two per zone, each measured at 40 requests per second in the prototype) reading from one Aurora reader at db.r6g.large added for the day. (Against Section 4: 6,100 requests per second over the first ten minutes.)
- v2 (25.2): The results tier is sized for the observed release-day peak and serves pre-rendered objects. At 02:00 on release day the Results Service renders every candidate's result (the JSON response and the PDF statement of results) from the results snapshot taken at that time into a private S3 bucket keyed by `candidate_id`, and a results read returns the rendered object, so that the release path touches no database. The tier is sized for 8,000 requests per second with 120 Results Service pods (40 per zone, each measured at 90 requests per second against S3 in the prototype), pre-warmed by the 06:00 runbook step (Section 17.3), with S3 request rates spread across 64 key prefixes.

### F05 (major, unjustified_quantitative_claim)

- v1 (25.3): The account-level throttle that API Gateway applies by default is 10,000 requests per second with a burst of 5,000 requests in every Region, which is above the 6,100 requests per second observed on the previous release day, so no quota increase is requested. (The documented default for Asia Pacific (Thailand) is 2,500 RPS with a 1,250 burst.)
- v2: (unchanged)

### F06 (major, missing_or_unverifiable_requirement)

- v1 (19.3): In addition, a nightly export of the candidate-level dataset (national identity number, name, date of birth, sex, school, province, subjects and grades) is written to the Ministry's analytics tenant, which is hosted for the Ministry by Lotus Insight Analytics in ap-southeast-1 (Singapore), so that the Ministry can run its own longitudinal analysis against earlier cohorts. (No requirement covers the cross-border transfer or the processor; DEC-01 says data remains in the country.)
- v2: (unchanged)

### F07 (major, internal_contradiction)

- v1 (19.1): School result files, one CSV and one PDF per school listing each candidate's grades, are published to the school portal at 06:00 on release day so that schools can prepare their briefing to candidates before the candidates see their own results. (Against 17.1: no result leaves the platform before the embargo lifts, equally for candidates, schools and the Ministry.)
- v2 (19.1): School result files, one CSV and one PDF per school listing each candidate's grades, are published to the school portal at 08:00 on release day, at the same moment as the candidate release, and the school's briefing to its candidates follows the release.

### F08 (major, acceptance_criterion_cannot_validate)

- v1 (29.1): | FR-8 | The tester keys a batch of 200 scripts in the first-entry screen, then keys the same batch again in the second-entry screen, and confirms that the comparison report shows zero differences and that the marks appear in `script_mark`. |
- v2 (29.1): | FR-8 | Two operators from different shift teams key a batch of 200 scripts in the first-entry and second-entry screens from two copies of the mark sheets into which 30 differences have been seeded; the comparison report must list exactly those 30 scripts, the resolution queue must offer them to a third operator only (the first two operators must not see them), and `script_mark` must hold only resolved values for the 30 and the agreed values for the 170. |

### F09 (major, decision_depends_on_pending_item)

- v1 (27): | DEC-05 | Private candidates are identity-proofed through the national digital identity service, at identity assurance level 2, from the opening of registration for the March 2027 sitting | Prevents impersonation at registration; removes the in-person document check at district offices | (Against PB-02: draft agreement, production API not before Q3 2027; registration opens 1 November 2026.)
- v2: (unchanged; PB-02 and Phase 1 unchanged too)

### F10 (major, scalability_failure_mode)

- v1 (11.3): Scan events are published to the `scripts.custody` topic keyed by the scanning station identifier, so that the busiest stations spread across partitions, and the custody consumer sets a script's current location to the location of each event as it is processed, the most recently processed event being the current state. (Against 22: ordering holds per key; 11.2: handhelds upload offline queues later.)
- v2: (unchanged)

### F11 (minor, ambiguous_requirement)

- v1 (2.2): | NFR-3 | Results pages shall load quickly for the great majority of candidates throughout the release window. |
- v2 (2.2): | NFR-3 | Results reads shall complete within 2 seconds at the 95th percentile, measured from the API Gateway request to the complete response, in every one-minute interval of the first hour after release at the release-day load described in Section 4. | (The 29.2 test follows.)

### F12 (minor, unjustified_quantitative_claim)

- v1 (18.4): The aggregator's contracted throughput is 200 messages per second, so the 375,000 messages for candidates who opted in are all delivered within 15 minutes of the embargo lifting, inside NFR-4. (375,000 / 200 is about 31 minutes; NFR-4 says 20.)
- v2 (18.4): The contracted throughput is 400 messages per second from Ratchaphruek Messaging and 200 from Dok Bua Telecom, 600 in all, so the 375,000 messages for candidates who opted in are handed to the aggregators within about 11 minutes of the embargo lifting, and with the aggregators' own delivery time of under 5 minutes at that rate the last message reaches its handset within about 16 minutes, inside NFR-4. (DEC-09 follows.)

### F13 (minor, security_privacy_gap)

- v1 (23.2): Results and certificates are retained for 30 years, the period over which SECB must answer certificate queries; the candidate record, including the accommodation application and its supporting medical and psychological evidence, is retained for the same 30 years alongside the result so that any later query about the candidate's examination can be answered from a complete record. (Against NFR-7 and P6; 23.1 classes the evidence as health data.)
- v2: (unchanged)

### F14 (minor, missing_or_unverifiable_requirement)

- v1 (2.1): | FR-16 | The platform shall provide the Ministry of Education with the statistical reports it requires after each sitting. | (The 29.1 test: the Ministry confirms receipt.)
- v2: (unchanged)

### F15 (critical, internal_contradiction, introduced in v2 by the F04 change)

- v1: (not present in v1; introduced in v2)
- v2 (25.2): Rendered objects are immutable from the 02:00 render until the scheduled re-render at 20:00 on release day, which picks up the day's appeals and clerical entries, so that every candidate reads the same object throughout the release window and no read depends on the database or the cache state. (Against the unchanged 16.1: corrections may be entered until 07:00 on release day, and the results dataset is locked at 07:00 so that the result released at 08:00 reflects every correction entered before the lock.)

## Cold read (2026-10-05, finished 00:13 +08)

Applied by a second worker from the cold reader's findings, under the same delegation (Malcolm's word of 3 Oct 2026 02:50 and his "yes" to plan D, 4 Oct 22:40).
Scripts in the scratchpad folder `coldread_exam2/` (the four authoring wrappers copied from `author_exam2/`, plus `apply_fixes.py`, 18 exact replacements in v1 and 25 in v2, and `patch_make_key.py`, 11 replacements in the copied `make_key.py`).
Every fix is a design property or a control; nothing is labelled, and the register of the surrounding text is kept.
F15's carrying sentence in v2 25.2 and the F02 sentence in 18.2 are byte-identical to before (asserted by the script).

### Fixes applied (identically in v1 and v2 unless marked v2 only)

- A1 (9.3): the seat rule and the no-two-venues rule are keyed on the examination date and session (`exam_date`, `session`, copied onto `seat_allocation` from `paper`) instead of `paper_id`; a Section 9.1 clash is allocated under the holding arrangement's own `session` value; the run starts after late registration closes on 15 January and after the accommodation decisions are complete (applications close 31 January), so it is scheduled for the second week of February. Key: `why_sound` and `trap` of "9.3 Allocation" updated to match.
- A2 (15.3): the anomaly report is computed from the graded data itself (a candidate's grades against the median of their school's candidates in the same subject; a centre's component distribution against the national one) instead of a school prediction that 7.1 never collects. Key: `why_sound` of "15" updated.
- A3 (20.3 and 18.3): the QR code appears on the certificate and on statements produced after the certificate is issued; a statement produced before issue carries none, since there is no certificate number to bind one to. Key: `why_sound` of "20" updated.
- A4 (13.2): the resolution queue excludes the two operators who keyed the entries. Key: `why_sound` of "13" updated.
- A5 (6.2): Finance Officer, Accommodation Officer and Head of Accommodations added to the staff role list; "Finance user" in 8.1 and 8.4 (and in the key's "8" `why_sound`) renamed Finance Officer.
- B6 (4): "The NUSC main sitting" is now "The NSC main sitting".
- B7 (title block): status reads "Detailed design; Phase 1 build in progress (Section 30.2)" in v1 and the same with the review clause in v2; the dates are unchanged.
- B8 (17.1): the Results Officer (clerical corrections, release console) and the Awarding Secretary (15.3 reports and sign-off) are the roles that can view results before release.
- B9 (FR-9, 14.1, 21.2): moderation is per marker everywhere, as DEC-07 already said; `moderation_run` is (component, marker, ...).
- B10 (12 and the FR-7 test): the exclusion is evaluated against the school of every script in the bundle, because a room, and so a bundle, mixes schools; the test joins `marker_allocation`, `script`, `candidate` and `marker`.
- B11 (21.2): the Grading Service reads moderated marks through a read-only database role on the instance; the replica endpoint that 24.2 never deployed is gone.
- C (v2 only): 17.2 describes a per-pod embargo state (`release_at` plus the writer-clock offset) refreshed from the Aurora writer every second, failing closed (state older than five seconds or no release row means no result), as the only database access on the release path; 18.2 and 25.2 say the release path reads that state and the object and nothing else; 18.3 says the statement is rendered together with the result object (25.2) and served as stored; the FR-11 test states the one-second refresh; 17.2, 18.3 and 29.1 (FR-11) are listed in the revision row and the "Changes since version 1.0" paragraph, neutrally. Key: `v2_changed_sections` and the F04 `v2_changes` note updated.

### Checks

- No-label scan (`grep -ciE '\bF[0-9]{2}\b|flaw|planted|intentional|deliberate|bug|TODO|FIXME|incorrect|mistake|wrong|regression|known issue|answer key'`): `design_v1.md:0`, `design_v2.md:0`.
- Em dash (U+2014) count: 0 in `design_v1.md`, `design_v2.md`, `README.md`, `answer_key.json`, `answer_key.canonical.json` and this note.
- Name checks (web search, 2026-10-05): "Siam Examinations and Certification Board" no match (only SIAM/EXIN service-management certifications); "PHON" no platform or product match (Thai place names, a surname); "National Secondary Certificate" no exact match (Trinidad and Tobago's "National Certificate of Secondary Education" and South Africa's "National Senior Certificate" differ in name; kept); "Ratchaphruek Messaging" and "Dok Bua Telecom" no match (a road and a restaurant); "Chao Phraya Payment Gateway" no match ("Chao Phraya Gateway" is a Bangkok property development, a different name); "Lotus Insight Analytics" no match; "National Digital Identity Office" no exact match (Thailand's real operator is National Digital ID Company Limited, NDID, a different name; kept as the fictional government office). No person is named in the designs (roles only). No rename was needed.
- Fact check (F05): https://docs.aws.amazon.com/apigateway/latest/developerguide/limits.html re-fetched 2026-10-05. Account-level throttle per Region: "10,000 requests per second (RPS) with an additional burst capacity provided by the token bucket algorithm, using a maximum bucket capacity of 5,000 requests", "Can be increased: Yes"; footnote: "For the following Regions, the default throttle quota is 2500 RPS and the default burst quota is 1250 RPS: Africa (Cape Town), Europe (Milan), Asia Pacific (Jakarta), Middle East (UAE), Asia Pacific (Hyderabad), Asia Pacific (Melbourne), Europe (Spain), Europe (Zurich), Israel (Tel Aviv), Canada West (Calgary), Asia Pacific (Malaysia), Asia Pacific (Thailand), and Mexico (Central)". The key's F05 `external_fact` is confirmed; its `verification_note` records the re-fetch.
- PDFs rebuilt (`coldread_exam2/build_exam_pdfs.py`): `design_v1.pdf` 16 pages, `design_v2.pdf` 17 pages, `ALL CHECKS PASSED`.
- Anchor pages re-measured by `make_key.py` from the new PDFs: F01 8, F02 10, F03 13 (was 12), F04 13, F05 13, F06 11 (was 10), F07 10, F08 15, F09 14, F10 7, F11 3, F12 10, F13 12, F14 2, F15 14 (was 13, design_v2). F15's anchor fragment shortened to "02:00 render until the scheduled re-render at 20:00 on release day" because the longer fragment now spans a PDF line break; the sentence itself is unchanged.
- Converter (`coldread_exam2/convert_exam.py --tier synthetic --verify-anchors`): exam_platform `flaws 15 (v1 14, v2 1)`, `v2_status {'fixed': 7, 'unchanged': 7, 'introduced': 1}`, `needs_external_research 2; sound sections 5`, `note: flaw_counts equal to recomputed v1 counts`, `scored_run_ready False` (sign-off pending); overall `60 flaws converted across 4 keys; 0 key(s) failed validation`. The other three canonical keys were rewritten byte-identical (git shows no change).
- `scripts/leakage_grep.py`: one unresolved hit, the pre-existing `'never leave' (tfidf; from eval/synthetic/payments_orchestration)` against `agent/sit_review_agent/tools/gateway.py:1080`, expected; nothing from this item.
- Word counts (wc -w): 9126 design_v1.md, 9820 design_v2.md; README updated.
- Not opened: `eval/blind/`, `docs/live_runs/`, the other synthetic items, `spec/taxonomy.yaml`, the source of `spec/convert_answer_keys.py` and `eval/build_pdfs.py`. Nothing pushed.
