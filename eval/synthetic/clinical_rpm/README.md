# Synthetic eval item: clinical_rpm (synthetic-clinical-rpm-001)

This is a synthetic design-review evaluation item: a detailed design for a fictional Singapore public healthcare cluster's Remote Patient Monitoring Platform. Wearable and bedside IoT devices stream vitals over MQTT to Azure IoT Hub. The design covers Stream Analytics rules and partial NEWS2, an ML early-warning model, alert routing and escalation, clinician dashboards, HL7 FHIR R4 EMR integration, PDPA/MOH governance, and device lifecycle, for about 8,000 devices running 24/7. It follows the structure and register of the SIT Memory Platform Detailed Design.

`design_v1.md` (and `.pdf`) contains 14 planted flaws (4 critical, 6 major, 4 minor) across eight categories, plus five genuinely sound sections that a good reviewer should leave alone. `design_v2.md` (and `.pdf`) is the "updated artefact" for re-review. It fixes six flaws, one of those fixes introduces a new regression (F15), and the other eight flaws are unchanged.

To use the item, give the reviewing agent only `design_v1.md` or `.pdf` (and later `design_v2`), never `answer_key.json` or this README. Then score its findings against `answer_key.json`:

- Match each finding on section or requirement IDs plus the `what_a_correct_finding_must_mention` claims.
- Use `distractor_notes` to decide partial credit.
- Count any recommended change in a `sound_sections` entry as a false positive.
- For v2, use `v2_changes` to credit recognition of fixes, detection of F15, and re-raising of the unchanged flaws.

The organisation, hospitals, and policy document IDs (e.g. HPHC-ISP-07) are fictional. Public references (Azure IoT Hub quotas, PDPA s26, IEC 60601-1-8, NEWS2, LOINC, IHE PCD) are used as real-world anchors for checkable claims.

PDF conversion: the Markdown was converted to HTML with python-markdown and then to PDF with `soffice --headless --convert-to pdf:writer_web_pdf_Export`. The container shipped only `libreoffice-core`, so `libreoffice-writer-nogui` was installed via apt to make conversion possible.

## No-label checklist (verified for design_v1.md and design_v2.md)

- [x] No occurrence of "flaw", "planted", "intentional", "TODO", "FIXME", "bug", "known issue", "caveat", or "answer key" in either document (grep-checked).
- [x] No flaw is marked with emphasis, warnings, footnotes, or comments; flawed statements are written in the same confident register as sound ones.
- [x] Readiness (Section 23) and Build Phases (Section 24) present the flawed areas as "Ready", consistent with an author unaware of them.
- [x] The v2 revision history describes changes neutrally and does not mention remaining flaws or the regression.
- [x] Flaw IDs (F01–F15), categories, and severities appear only in `answer_key.json`.
- [x] Section numbering and requirement IDs are identical in v1 and v2, so key references hold for both.
