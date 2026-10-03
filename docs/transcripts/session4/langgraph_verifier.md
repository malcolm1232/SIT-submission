# The independent verification of the LangGraph variant (2026-10-03)

A verifier in a fresh context checked the builder's seven commits on `s4/langgraph` (430321d to 527c60e), fixed what failed, and merged the branch onto `claude/happy-darwin-d0bl94`.
No model call was made and nothing was sent to the SIT MCP hosts.
The step-by-step evidence is `research/audit/langgraph_verifier_editlog.md`.

## Verdict per claim

1. Isolation: FIXED.
The product paths have no diff against 430321d apart from `cli.py` and `pyproject.toml`, and without `--orchestrator` the CLI runs the custom loop.
In a venv without the `[langgraph]` extra the agent imported and `sit-review selftest` passed, but `make smoke` failed on the skeleton import test and the parity module could not be collected.
Both now skip the variant when langgraph is absent; after the fix, without langgraph, `make smoke` passes and the full suite has 0 failures.
2. Parity: PASS.
26 passed and 2 xfailed with the stated reasons.
The fixture swaps the class the product's entry points look up at call time, so the ID, shard-cut and replay tests run the graph on the LangGraph arm.
A merge-order mutation of the variant failed the finding-ID test on the LangGraph arm only; the file was restored from a backup.
3. The live run: FIXED.
`dra replay` exits 0 and matches the recording; the orchestrator is in the manifest's `argv` and in `langgraph/variant.json`; the secret scan is clean; wall, cost, verdict, cut and kept counts match the manifest and report.
`MEASUREMENT.md` said "21 findings plus 3 strengths"; the run has 18 findings plus 3 strengths, and it now says so.
4. The scoring: PASS.
The scoring is marked exploratory, and both columns of the comparison table match `scores.json`, `QUALITY_COMPARISON.md` and the custom run's own files.
5. The note: FIXED.
Every cited file and line exists, the line counts recount exactly, the conclusion names one document and one run per arm and the heavier Mac load, and there is no em dash.
The claim that the stage 1 members started at 1.9 s to 2.1 s "in both runs" had no committed source for the custom loop's run (its ingest ended at 2.228 s), so the note and the measurement now give each run's own figure.
Decision #42 is recorded in `docs/USER_DECISIONS.md`, and row 8 of `docs/SUBMISSION_GAPS.md` cites the comparison.
6. Gates: PASS, with exit codes and counts in the edit log, and again after the merge.

## Not verified

The note's statement that six launch-order assertions of `tests/test_orchestrator.py` fail under the variant was not re-run.
The "356 lines with two helpers" total of the custom `Orchestrator` was not recounted (the 153 replaced and the 436 of the variant were).
The builder's report has no "Not verified" section to check against.
The Mac load figures are the builder's readings at the time and cannot be re-measured.

## For the next session

The comparison rests on one paired document; the five further runs below were refused to the builder by the permission classifier and need the owner or a session allowed to make model calls.
Each run is `--profile demo --no-tools` at the demo profile's `medium` effort, as the two existing runs were, and each is scored with the same command as `langgraph_payments_v1_1`.
1. The custom loop on payments again: `dra review eval/synthetic/payments_orchestration/design_v1.pdf --profile demo --no-tools --run-id custom_payments_v1_2`.
2. The custom loop on clinical: `dra review eval/synthetic/clinical_rpm/design_v1.pdf --profile demo --no-tools --run-id custom_clinical_v1_1`.
3. The variant on clinical: `dra review eval/synthetic/clinical_rpm/design_v1.pdf --profile demo --no-tools --orchestrator langgraph --run-id langgraph_clinical_v1_1`.
4. The custom loop on lakehouse: `dra review eval/synthetic/research_lakehouse/design_v1.pdf --profile demo --no-tools --run-id custom_lakehouse_v1_1`.
5. The variant on lakehouse: `dra review eval/synthetic/research_lakehouse/design_v1.pdf --profile demo --no-tools --orchestrator langgraph --run-id langgraph_lakehouse_v1_1`.
Score each with `sit-eval score runs/<run_id> --key eval/synthetic/<doc>/answer_key.canonical.json --out runs/<run_id>/eval_pilot_bounded --judge claude_code --model claude-opus-5-5 --effort high --samples 3 --seed 20261002 --concurrency 4 --max-cost-usd 18 --candidate-rule shortlist_bounded --exploratory`.
Run the two arms of a pair back to back under a similar Mac load, and record the load average in each `MEASUREMENT.md`, since the one paired run so far differed by 15.8 against about 5.
