# Session 4: the first with-tools run on the lab's sample document

Date: 2026-10-03.
Run: `sit_sample_tools_1`, committed at `docs/live_runs/sit_sample_tools_1/`, measured in its `MEASUREMENT.md`.

## What happened

The owner ran the agent himself from his Terminal with the SIT MCP key, on the lab's own sample document ("SIT Institutional Memory Platform, Detailed Design", Version 2.0, 30 pages), with `--profile demo` and the tools enabled.
Before the run, the ingest was fixed on branch `s4/live` (`1b92baf`) so the document's contents list is read as contents; it now yields 33 sections instead of 2.
A worker then copied the run into the repository without `progress.log`, scanned it for secrets by count, measured it by script, read `report.md`, and wrote the measurement note.
No new agent run, no model call and no call to the SIT MCP hosts was made by the worker.

## Outcome in numbers

- Wall 428.0 s against the 540 s slot (112.0 s slack); stage 1 ended at 255.0 s against its 265 s limit.
- 12 model calls, $5.54, 135,599 output tokens; refine and the verdict call ran in full.
- Verdict `fit_with_conditions` at confidence 0.72; 22 issues (0 critical, 6 high, 14 medium, 2 low), 2 strength findings and 10 sound areas.
- 130 anchors, 129 resolved and 1 repaired, none unresolved.
- Tools: 6 calls; the 5 `search_web` calls all failed with "Connection closed" and the tool was disabled for the run; the 1 `search_research` call succeeded and added 10 external ledger entries from `doi.org`, of which 1 is cited (FND-026).

## What the agent said about the document

- Verdict: fit with conditions (confidence 0.72): coherent and traceable, but not yet fit to build unconditionally.
- High findings: the agent per-learner backup is an ungoverned copy (FND-011); the counselling hard wall is contradicted by Super Admin and MMP emergency access (FND-012); the async write path has no outcome for writes rejected after the ACK (FND-038); the MMP sits in the request path against NFR-4 (FND-013); a revoked token still gets data from the backup (FND-037); the filtered HNSW search-space claim behind NFR-2 is unverified (FND-026).
- Strengths: requirements with IDs traced to acceptance criteria and an honest readiness map (FND-010), and two-tier sensitive storage with separate credentials (FND-046).
- Limitations it disclosed: it read extracted text only, so figures were not checked (DEG-001), and web search failed (DEG-002), leaving the Entra ID token lifetime, pgvector filtered search and Azure pricing unverified.
- There is no answer key for this document (decision #35), so nothing was scored.

## Defects found

- A closed MCP session (`MCPError -32000`) is classified as a tool error, so the gateway neither reconnects nor retries, and disables the tool.
- DEG-002 reads as one failed call when five failed.
- The research stop reads `sufficient_evidence` with 0 of 9 questions answered.
- `report.md` says seven high findings where `report.json` has six, prints "vVersion 2.0", and flattens two bullet lists into paragraphs.
- Research starts after the shards, so no shard can use external evidence.

## Handling notes

- `text/` in the run directory holds the lab's extracted document text and must be excluded from any public snapshot.
- Nothing in `agent/` or `harness/` was changed by the measurement.
