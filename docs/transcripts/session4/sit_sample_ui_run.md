# Session 4: measuring the UI with-tools run on the lab's sample (2026-10-03)

A worker read, measured, compared and committed the owner's run `ui-261003-082941-36e8`, launched from the review UI page with the SIT MCP key on the lab's sample document after the MCP session fix.
No new run was made, no model was called, and nothing was sent to the SIT MCP hosts.

## What was done

1. Merged `origin/claude/happy-darwin-d0bl94` into `s4/final` with a merge commit (no conflict).
2. Copied the run to `docs/live_runs/sit_sample_ui_1/` without `progress.log`, `ui/console.txt` (the same console stream) and `ui/input/sit_sample_v1.pdf` (the lab's document); no `ui/chat.jsonl` existed; `progress.jsonl` stays out by `.gitignore`.
3. Ran a count-only secret scan over the copy and committed it before measuring.
4. Extracted every number by script from `manifest.json`, `llm.jsonl`, `tools.jsonl`, `report.json`, `anchors.json`, the shard files and `progress.jsonl` (structural fields only); read `report.md`.
5. Wrote `docs/live_runs/sit_sample_ui_1/MEASUREMENT.md` in the shape of `sit_sample_tools_1/MEASUREMENT.md`, and added a state line to `docs/HANDOFF.md`.

## Findings

- 506.9 s against the 540 s slot (slack 33.1 s), $3.68 as a lower bound (about $4.49 with the estimate for the two cut calls), 11 model calls.
- Assess shard 2 was cut at 265.2 s with 8 findings kept; refine was cut at 465.0 s with 30 revisions kept but none applied.
- Verdict `fit_with_conditions` at 0.65; 41 issues (19 high, 19 medium, 3 low, several unmerged duplicates), 3 strengths, 8 sound areas, 169 anchors all resolved.
- The session fix held live: one proactive reopen of the internet-search session after 122 s idle, then 7 of 7 `search_web` and 1 `fetch_url` calls succeeded.
- 30 external ledger entries from 15 domains, none cited by any finding, because refine (the stage that attaches evidence) was cut.
- Research stopped on `sufficient_evidence` with 1 of 6 questions answered; `mcp-research-information` was not called.
- Another Opus run shared the Mac, by the caller's account; completed calls streamed at the usual rate, so the two cuts are attributed to load or design, not separable here.

## Defects recorded, not fixed

The cut refine discards its salvaged revisions; the research stop rule reads sufficient with 1 of 6 answered; the report header lists an unused server as used; the session reopen is absent from the manifest and report; the cut-call usage estimate looks low; a UI launch records absolute home-directory paths; two status records carry a null `run_s`; and the stage limits sit close to what shard 2 and refine need on this document.
