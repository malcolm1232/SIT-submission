# Submission gaps (lab §5.1 to §5.3)

Checked 2026-10-03 on branch `s4/demo2` against `docs/DOCUMENTATION_MAP.md` and the lab brief (pp.7-8 §5.1-§5.3).
Status: **Exists** (path given), **Partial** (some of it exists), **Prepared** (the place exists, the content comes on the day), **Missing**.
Updated 2026-10-03 on branch `s4/subdocs`: rows 3, 5, 6, 8 to 14, 18 to 20, 23 and 26 closed, rows 21 and 22 prepared, rows 4 and 25 narrowed; rows 1, 2 and 24 are the owner's and unchanged (`research/audit/submission_docs_editlog.md`).
Ordered by what an evaluator opens first: access, then `README.md`, then setup, then the design documents, then the code, then the outputs.

| # | Artefact (lab ref) | Status | Path | Task to finish it |
|---|---|---|---|---|
| 1 | Access for `SIT-calebying` and `Makienhui-sit` before the deadline (§5.2) | Missing | GitHub collaborators: only `malcolm1232`, no pending invitation (`gh api`, 2026-10-03) | Owner invites both under Settings, Collaborators, records the date in `README.md`, and re-sends if not accepted within 7 days |
| 2 | Repository privacy decision for the SIT material (§5.2) | Partial | `docs/DECISIONS.md` ADR-005, status "Awaiting user" | Owner rules on ADR-005 before access is granted, since history may not be rewritten afterwards |
| 3 | Instructions: what it does and how to start (§5.1, §5.2) | Exists | `README.md` (rewritten 2026-10-03: what it is, Requirements, Install, Run with `review`, `--no-tools`, `--previous`, `preflight`, `ui`, `replay`, `coverage`, `explain`, `resume`, `states`, `selftest`; links `docs/DEMO_DAY_SCRIPT.md`) | None |
| 4 | Dependencies, model requirements, third-party services (§5.1, §5.2) | Partial | `README.md` "Requirements" (Python 3.13, the Claude Code CLI login, `claude-opus-5-5`, no API key with the default backend, the SIT MCP key, macOS only verified); `docs/TECHNOLOGIES.md` (every pin of `pyproject.toml`) | Still open: commit a lock file of the resolved tree, or drop the `uv sync --frozen` lines from runbook §2 and `docs/REPRODUCIBILITY.md` §7 |
| 5 | Installation steps (§5.1) | Exists | `README.md` "Install" (venv, `pip install -e '.[dev]'`, `playwright install chromium`, `make smoke`); checked on a fresh clone 2026-10-03, `make smoke` exit 0 | None |
| 6 | Environment configuration without secrets (§5.2) | Exists | `.env.example` (`SIT_MCP_API_KEY`, `SIT_UI_SMTP_PASSWORD`, empty; a comment on why `ANTHROPIC_API_KEY` is not needed); `.gitignore` keeps `.env` out and lets `.env.example` in; `README.md` "Configure" and "Secrets" say to load it into the shell | None |
| 7 | Overall agent architecture (§5.3) | Exists | `docs/ARCHITECTURE.md` | None; keep §13 in step with `docs/DEMO_DAY_SCRIPT.md` |
| 8 | Framework and technologies (§5.3) | Exists | `docs/TECHNOLOGIES.md` (why no framework, model and backends, every pinned dependency with its role); `docs/ARCHITECTURE.md` §3, §12; ADR-001, ADR-002, ADR-006, ADR-010; `docs/COMPARISON_LANGGRAPH.md` (the same agent on LangGraph behind `--orchestrator langgraph`, measured against the custom loop on one paired document, decision #42) | None |
| 9 | Context management (§5.3) | Exists | `docs/CONTEXT_MANAGEMENT.md`, pointing at `docs/ARCHITECTURE.md` §2, §4, §6 and the implementing files | None |
| 10 | Planning and execution (§5.3) | Exists | `docs/PLANNING_EXECUTION.md`, pointing at `docs/ARCHITECTURE.md` §2, §3, ADR-011, ADR-012 and the implementing files | None |
| 11 | Tool orchestration (§5.3) | Exists | `docs/TOOL_ORCHESTRATION.md`, pointing at `docs/ARCHITECTURE.md` §5, `research/robustness/mcp_probe_findings.md` and the implementing files | None |
| 12 | Memory and state management (§5.3) | Exists | `docs/MEMORY_STATE.md`, pointing at `docs/ARCHITECTURE.md` §7, §11, ADR-009 and the implementing files | None |
| 13 | Validation and review (§5.3) | Exists | `docs/VALIDATION.md` (in-run checks and invariants, the harness, prereg, robustness, results so far) | None |
| 14 | Assumptions, limitations, known constraints (§5.3) | Exists | `docs/LIMITATIONS.md` (one sentence per item, each with the file that records it) | None |
| 15 | Source code and orchestration logic (§5.1) | Exists | `agent/sit_review_agent/` (`orchestrator.py`, `llm/`, `tools/`, `stop_rules.py`) | None |
| 16 | Configuration files (§5.1) | Exists | `config/` (`agent.yaml`, `criteria.yaml`, `stop_rules.yaml`, `tools.yaml`, `endpoints.yaml`, `url_policy.yaml`, `persona.yaml`, `ui.yaml`, `profiles/demo.yaml`) | None |
| 17 | Prompts (§5.1) | Exists | `prompts/*.md`, `prompts/PROMPTS.lock` | None |
| 18 | Workflow definitions (§5.1) | Exists | `agent/sit_review_agent/states.py`, printed by `dra states`; `docs/PLANNING_EXECUTION.md` and the map point at it and at `docs/ARCHITECTURE.md` §2 | None (no generated `.mmd` is committed, so it cannot drift from the code) |
| 19 | Memory configuration (§5.1) | Exists | `docs/MEMORY_STATE.md` "The settings that configure it" (`run_root`, `transport`, `replay`, `record`, and the run flags) | None |
| 20 | Execution procedures (§5.1) | Exists | `README.md` "Run"; `docs/DEMO_DAY_RUNBOOK.md`, `docs/DEMO_DAY_SCRIPT.md`, `agent/README.md` | None |
| 21 | Design review outputs generated during the lab session (§5.1) | Prepared | `outputs/lab_session/README.md` (the folder exists, empty by design, with the copy, commit and push commands) | After the session, copy each run directory without `progress.log` and `ui/` and commit it (`outputs/lab_session/README.md`, `docs/DEMO_DAY_SCRIPT.md` "After the session") |
| 22 | Supporting evidence, references and research findings (§5.1) | Prepared | each run's `ledger.json`, `snapshots/` and the report's evidence register, copied with row 21 into `outputs/lab_session/` | Same task as row 21; check `snapshots/` is committed, since git skips an empty folder |
| 23 | "Reproduce the exercise" (§5.1) | Exists | `README.md` "Install" (fresh clone, install, `make smoke`) and "Reproduce" (smoke, suite, robustness, the replay of `docs/live_runs/ui_flow_1` at its recorded commit `5f62065`, which matches); `docs/REPRODUCIBILITY.md` §7 | Note: at the current tip the committed runs do not replay byte for byte (exit 4 or 2); the README says so and gives the at-commit recipe |
| 24 | Demo-day prerequisites (runbook §1, §9) | Missing in this checkout | no `demo-freeze` tag; `runs/` is gitignored, so `runs/sit_v1_frozen/` and the two backups cannot be checked here | Owner records them with the final code and checks `dra replay` on both the day before |
| 25 | Secret scanning (§5.2, ADR-005) | Partial | `scripts/export_public_snapshot.py`; `README.md` "Secrets" and `.env.example`; no `gitleaks` pre-commit hook (runbook §9) | Add the hook, or name in `README.md` the scan run before each push |
| 26 | The map of all of the above (§5.3) | Exists | `docs/DOCUMENTATION_MAP.md` (refreshed 2026-10-03 from this list, links it) | None |

Not checked here: whether the answer keys are sealed as `docs/SEALING.md` plans (out of this worker's read scope), and anything on the owner's Mac outside this worktree.
