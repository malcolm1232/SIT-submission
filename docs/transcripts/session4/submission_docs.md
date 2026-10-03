# Submission documentation: worker report (2026-10-03)

Branch `s4/subdocs`, base `ab11a0a`; the edit log with every check is `research/audit/submission_docs_editlog.md`.

## What was done

`README.md` was rewritten for an evaluator who clones the repository cold, with Requirements, Install, Run, Configure, Reproduce, Evaluate, Layout, Status (3 October 2026), Limitations and Secrets.
`.env.example` names `SIT_MCP_API_KEY` and `SIT_UI_SMTP_PASSWORD` with empty values, and `.gitignore` now lets it in, since its `.env.*` rule would have ignored it.
`docs/LIMITATIONS.md` lists what the agent and the evaluation cannot claim, one sentence per item, each with the file that records it.
Six §5.3 topic files were added (`docs/TECHNOLOGIES.md`, `docs/CONTEXT_MANAGEMENT.md`, `docs/PLANNING_EXECUTION.md`, `docs/TOOL_ORCHESTRATION.md`, `docs/MEMORY_STATE.md`, `docs/VALIDATION.md`), each pointing at its `docs/ARCHITECTURE.md` section and the implementing files.
`docs/DOCUMENTATION_MAP.md` §1 to §3 now carry current statuses and link the gap list.
`outputs/lab_session/README.md` prepares the folder for the day's runs, empty by design.
`docs/SUBMISSION_GAPS.md` rows 3, 5, 6, 8 to 14, 18 to 20, 23 and 26 are closed, rows 21 and 22 prepared, rows 4 and 25 narrowed, and the owner rows 1, 2 and 24 are unchanged.
`docs/ARCHITECTURE.md` §8 and §13 said 87 robustness scenarios with 55 passing, and now say 88 and 56, as the results file does.

## Key findings

The remote moved during the work and was merged without conflict; it brought the live re-assessment run `docs/live_runs/reassess_payments_v2_1/`, which `docs/LIMITATIONS.md` and the README now cite.

No committed run under `docs/live_runs/` replays byte for byte at the tip: three diverge on a finding statement (exit 4) and three are refused (exit 2).
`ui_flow_1` replays exactly at its recorded commit `5f62065`, and the README gives that recipe, run verbatim with exit 0.
The cause of the divergence at the tip was not investigated.

## Gates

`ruff check agent harness tests` exit 0; `pytest -q` exit 0 with 1837 passed and 0 failed after merging the moved remote; `make smoke` exit 0 with 249 passed, also on a fresh clone.
The link check found 223 paths and 3 missing, all expected (`.env` twice, and a pre-existing optional `docs/slides/`).

## Not verified

A live review, `dra preflight --warm`, `dra resume` and the live judges were not run, because they make model or MCP calls; only their options were checked.
Linux and Windows were not tried.
