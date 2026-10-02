# Blind review item B: BESS site energy management design

## What this item is

`design.md` is a pre-build design document (FDC-SEMS-DD-001 Rev C, about 8,900 words, 15 numbered sections with requirement IDs). It covers a site energy management system (SEMS) and battery energy storage controls for a fictional cold-chain distribution centre. The system includes a 2 MW / 4 MWh LFP BESS, 1.8 MWac of existing rooftop PV, a 500 kW export limit, utility demand response over IEEE 2030.5, and islanded backup of a 380 kW critical feeder. The interconnection context is US (IEEE 1547-2018, UL 1741 SB, UL 9540, NFPA 855, NEC).

The document contains purpose and scope, context and assumptions, functional and non-functional requirements, design principles, architecture, interfaces, operating modes and key flows, safety, cybersecurity, governance, operations, a decision log, open items, acceptance criteria and a phased plan. Most of it is intended to be sound and should survive a senior review unchanged.

## Seeded defects

The document contains **14 seeded defects** of varying severity (1 critical, 7 high, 6 medium). They cover safety-function architecture, failure-mode behaviour, external standards and protocol limits, timing feasibility, capacity and availability arithmetic, contractual constraints, security architecture, time synchronisation, verification coverage and schedule dependencies.

- At least four defects need an external fact to confirm: IEEE 1547-2018 island trip time, the Modbus FC03 register limit, UL 9540 vs UL 9540A, and IEEE 2030.5 TLS requirements.
- At least three are safety-relevant: the software-routed E-stop, unbounded hold-last-setpoint on communication loss, and the anti-islanding trip time.

**No defect is labelled, annotated, hinted at or clustered in `design.md`.** The document contains no reviewer notes, no markers and no wording that flags a passage as suspect. The defects are spread across sections and are written in the same voice and with the same confidence as the sound material. Several are only visible by cross-reading sections, for example a requirement in Section 3 against an interface rate in Section 6, or an assumption in Section 2 against a dispatch estimate in Section 7.

## Files

| File | Purpose | Give to reviewer? |
|---|---|---|
| `design.md` | The document under review | Yes |
| `answer_key.json` | Sealed key: each defect with id, category, severity, location (sections and requirement IDs), description, why it matters, what a review must say to earn credit, and an acceptable fix. It also lists 9 deliberately sound sections with the false positives a careless reviewer might raise there, plus non-keyed valid observations and scoring guidance | **No** (sealed) |
| `README.md` | This file | No |

## Suggested scoring

- Credit a defect only when the review meets every item in its `credit_requires` list (paraphrase is fine). A severity disagreement of one level is acceptable.
- Count findings that match a `deliberately_sound_sections` entry as false positives.
- Valid findings outside the key (see `non_keyed_observations_acceptable_but_not_required`) are neutral.

The site, organisations, document IDs and supplier documents are fictional. Public standards are cited by their real titles.
