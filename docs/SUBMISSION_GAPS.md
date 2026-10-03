# Submission gaps (lab §5.1 to §5.3)

Checked 2026-10-03 on branch `s4/demo2` against `docs/DOCUMENTATION_MAP.md` and the lab brief (pp.7-8 §5.1-§5.3).
Status: **Exists** (path given), **Partial** (some of it exists), **Missing**.
Ordered by what an evaluator opens first: access, then `README.md`, then setup, then the design documents, then the code, then the outputs.
`docs/DOCUMENTATION_MAP.md` itself is stale (it still says the agent, config and prompts are "Not yet"); the last row fixes it.

| # | Artefact (lab ref) | Status | Path | Task to finish it |
|---|---|---|---|---|
| 1 | Access for `SIT-calebying` and `Makienhui-sit` before the deadline (§5.2) | Missing | GitHub collaborators: only `malcolm1232`, no pending invitation (`gh api`, 2026-10-03) | Owner invites both under Settings, Collaborators, records the date in `README.md`, and re-sends if not accepted within 7 days |
| 2 | Repository privacy decision for the SIT material (§5.2) | Partial | `docs/DECISIONS.md` ADR-005, status "Awaiting user" | Owner rules on ADR-005 before access is granted, since history may not be rewritten afterwards |
| 3 | Instructions: what it does and how to start (§5.1, §5.2) | Partial | `README.md` (status line dated 2026-10-02, 865 tests; no Run section) | Rewrite the status line, add Install, Configure, Run (`dra review`, `dra ui`, `preflight`, `explain`, `coverage`, `resume`, `replay`) and link `docs/DEMO_DAY_SCRIPT.md` |
| 4 | Dependencies, model requirements, third-party services (§5.1, §5.2) | Partial | `pyproject.toml` (Python >= 3.11); no `uv.lock`, no `.python-version` | Add a `README.md` Requirements section (Python, the `claude` CLI login or `ANTHROPIC_API_KEY`, `claude-opus-5-5`, the SIT MCP servers and key) and commit a lock file, or drop the `uv sync --frozen` lines from runbook §2 |
| 5 | Installation steps (§5.1) | Partial | `README.md` "Reproducing checks" line 34 (`pip install -e ".[dev]"`) | Move it into an Install section with `playwright install chromium` for the browser tests and `make smoke` as the check |
| 6 | Environment configuration without secrets (§5.2) | Missing | no `.env.example`; the agent does not read `.env`, it reads the shell | Add `.env.example` with the names only (`SIT_MCP_API_KEY`, `ANTHROPIC_API_KEY`, `SIT_UI_SMTP_PASSWORD`) and say in `README.md` to export them |
| 7 | Overall agent architecture (§5.3) | Exists | `docs/ARCHITECTURE.md` | None; keep §13 in step with `docs/DEMO_DAY_SCRIPT.md` |
| 8 | Framework and technologies (§5.3) | Partial | `docs/DECISIONS.md` ADR-001, ADR-002, ADR-006, ADR-010; `docs/ARCHITECTURE.md` §4, §12 | Add a Technologies section to `docs/ARCHITECTURE.md` listing each pinned dependency |
| 9 | Context management (§5.3) | Partial | `docs/ARCHITECTURE.md` §2, §6 | Write `docs/CONTEXT_MANAGEMENT.md` (what each call sees, the document kept out of the system prompt, doc against external evidence) or point the map at those sections |
| 10 | Planning and execution (§5.3) | Partial | `docs/ARCHITECTURE.md` §2, §3; ADR-011, ADR-012 | Write `docs/PLANNING_EXECUTION.md` (stages, stop rules and the stop-reason enum, stage limits, refine) or point the map at those sections |
| 11 | Tool orchestration (§5.3) | Partial | `docs/ARCHITECTURE.md` §5; `research/robustness/mcp_probe_findings.md` | Write `docs/TOOL_ORCHESTRATION.md` (the gateway layers, warm-up, the session rule of #38, cassettes) or point the map at §5 |
| 12 | Memory and state management (§5.3) | Partial | `docs/ARCHITECTURE.md` §7, §11 | Write `docs/MEMORY_STATE.md` (run state, checkpoints, ledger, registry, `--previous`, no cross-run learning) or point the map at §7 |
| 13 | Validation and review (§5.3) | Partial | `docs/REPRODUCIBILITY.md`, `docs/SEALING.md`, `docs/ARCHITECTURE.md` §6, §9, `harness/README.md` | Write `docs/VALIDATION.md` joining the verify stage, invariants, robustness results and the evaluation results so far |
| 14 | Assumptions, limitations, known constraints (§5.3) | Missing | scattered: `docs/USER_DECISIONS.md` #34 and #37, the `MEASUREMENT.md` "Not verified" lists, `docs/HANDOFF.md` | Write `docs/LIMITATIONS.md`: the 540 s assumption, text-only PDF on the CLI backend, no offline review, same-family judge, n = 1 quality evidence, the unscored SIT sample |
| 15 | Source code and orchestration logic (§5.1) | Exists | `agent/sit_review_agent/` (`orchestrator.py`, `llm/`, `tools/`, `stop_rules.py`) | None |
| 16 | Configuration files (§5.1) | Exists | `config/` (`agent.yaml`, `criteria.yaml`, `stop_rules.yaml`, `tools.yaml`, `endpoints.yaml`, `url_policy.yaml`, `persona.yaml`, `ui.yaml`, `profiles/demo.yaml`) | None |
| 17 | Prompts (§5.1) | Exists | `prompts/*.md`, `prompts/PROMPTS.lock` | None |
| 18 | Workflow definitions (§5.1) | Partial | `agent/sit_review_agent/states.py`, `dra states`; no `docs/diagrams/state_machine.mmd` | Commit the `dra states` output as `docs/diagrams/state_machine.mmd`, or point the map at `docs/ARCHITECTURE.md` §2 |
| 19 | Memory configuration (§5.1) | Partial | checkpoint and ledger settings live in code and `config/agent.yaml` | Name the keys that configure memory and state in the memory document of row 12 |
| 20 | Execution procedures (§5.1) | Exists | `docs/DEMO_DAY_RUNBOOK.md`, `docs/DEMO_DAY_SCRIPT.md`, `agent/README.md` | Add the CLI reference to `README.md` (row 3) |
| 21 | Design review outputs generated during the lab session (§5.1) | Missing | `outputs/lab_session/<date>/` does not exist; produced on the day | After the session, copy each run directory without `ui/` and commit it (`docs/DEMO_DAY_SCRIPT.md` "After the session") |
| 22 | Supporting evidence, references and research findings (§5.1) | Missing | each run's `ledger.json`, `snapshots/` and the report's evidence register, with row 21 | Same task as row 21; check `snapshots/` is committed, since git skips an empty folder |
| 23 | "Reproduce the exercise" (§5.1) | Partial | `docs/REPRODUCIBILITY.md` §7; earlier live runs under `docs/live_runs/` | Add a fresh-clone check to `README.md`: clone, install, `make smoke` |
| 24 | Demo-day prerequisites (runbook §1, §9) | Missing in this checkout | no `demo-freeze` tag; `runs/` is gitignored, so `runs/sit_v1_frozen/` and the two backups cannot be checked here | Owner records them with the final code and checks `dra replay` on both the day before |
| 25 | Secret scanning (§5.2, ADR-005) | Partial | `scripts/export_public_snapshot.py`; no `gitleaks` pre-commit hook (runbook §9) | Add the hook, or state in `README.md` which scan is run before each push |
| 26 | The map of all of the above (§5.3) | Partial | `docs/DOCUMENTATION_MAP.md` (dated 2026-10-02) | Refresh every status in it from this list and link this file |

Not checked here: whether the answer keys are sealed as `docs/SEALING.md` plans (out of this worker's read scope), and anything on the owner's Mac outside this worktree.
