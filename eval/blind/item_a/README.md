# Blind review item A: Meridian Order Management and Returns Platform

## What this item is

`design.md` is a pre-build design document (about 8,400 words of prose, 13 numbered sections plus a glossary, with requirement IDs FR-*, NFR-*, CMP-*, DEC-*, OI-*, AC-*) for **Meridian**. Meridian is a fictional replacement order management and returns platform for a fictional multi-market retailer, Halden & Rowe, trading online in the UK, Ireland, Germany, the Netherlands and France. It covers order capture and orchestration, cancellation, self-service returns, refund orchestration, event publication, security and privacy, operations, decisions, open items, acceptance criteria and a phased market-by-market rollout. The target platform is AWS (DynamoDB, Aurora PostgreSQL, SNS/SQS, S3).

The document is meant to be realistic and mostly sound: the majority of it should survive a senior design review unchanged.

## Seeded defects

The document contains **14 seeded defects** across regulatory compliance, functional logic, platform limits, messaging scalability, consistency, idempotency, security, privacy, availability, rollout and testability. Severities: 2 Critical, 6 High, 5 Medium, 1 Low. Six defects require checking an external fact to confirm, such as EU/UK consumer-law refund rules, DynamoDB and SQS service limits, SQS FIFO message-group semantics, and GDPR or S3 Object Lock behaviour.

**No defect is labelled, annotated, hinted at or grouped in `design.md`.** The defects sit in different sections, in the same voice as the surrounding text. The document contains no comments, markers or wording that identifies them.

## Files

| File | Purpose |
|---|---|
| `design.md` | The document under review. Give only this file to the reviewer. |
| `answer_key.json` | Sealed key. For each defect it gives the id, category, severity, location (sections and requirement IDs), the external fact where relevant, the credit criteria and an acceptable fix. It also lists 8 deliberately sound areas, with the false positives a careless reviewer is likely to raise there. |
| `README.md` | This file. |

## Scoring guidance

- A finding earns credit only if it meets the `credit_requires` text for a defect. A finding in the right location that misses the stated reason does not.
- Findings against the `deliberately_sound_sections` count as false positives.
- Reasonable findings not in the key (for example, style or minor clarity points) should be neither rewarded nor penalised unless they are factually wrong.
- Keep `answer_key.json` away from the reviewer under evaluation.
