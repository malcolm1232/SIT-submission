# Documentation map

Date: 2026-10-03 (refreshed from `docs/SUBMISSION_GAPS.md`; first written 2026-10-02). Maps every documentation requirement in the lab brief to the file that will satisfy it, so nothing is left out of the submission (audit M10). Lab §5.3 says the repository "may include sufficient documentation to explain" eight topics; §5.1 lists the deliverables; §5.2 the repository rules; §5.4 the demo.

Status: **Exists** (written, may still grow), **Partial** (some of it exists), **Prepared** (the place exists, the content comes on the day), **Owner action** (only the owner can do it). "Sources" are the research notes and decisions the file draws on. All paths are relative to the repo root.

## 1. Lab §5.3 documentation topics

Each topic file states its subject in its own words and points at the `docs/ARCHITECTURE.md` section and the files that implement it, so the architecture text is not copied.

| Lab §5.3 topic | File that satisfies it | Status | Sources it points at |
|---|---|---|---|
| The overall agent architecture | `docs/ARCHITECTURE.md`: what the agent does, the stage graph, why this shape with the measured times, model access, tools, honesty and traceability, state, robustness, the evaluation harness, the UI, frozen interfaces, comparisons and trade-offs, and the walkthrough script | Exists | `docs/DECISIONS.md` ADR-001, ADR-010 to ADR-012; `docs/live_runs/QUALITY_COMPARISON.md` |
| The agent framework and technologies used | `docs/TECHNOLOGIES.md`: why no framework, the model and backends, every pinned dependency with its role | Exists | `pyproject.toml`; `docs/ARCHITECTURE.md` §3, §12; ADR-001, ADR-002, ADR-006, ADR-010 |
| Context management approach | `docs/CONTEXT_MANAGEMENT.md`: the shared cached prefix, what each stage sees, ledger IDs that keep outside evidence apart, the size guard | Exists | `docs/ARCHITECTURE.md` §2, §4, §6 |
| Planning and execution approach | `docs/PLANNING_EXECUTION.md`: the fixed stage order, the plan and research loop, stop rules and the stop-reason enum, stage limits, refine | Exists | `docs/ARCHITECTURE.md` §2, §3; ADR-011, ADR-012 |
| Tool orchestration approach | `docs/TOOL_ORCHESTRATION.md`: the gateway layers, the MCP client, warm-up, the closed-session rule, the URL policy, cassettes | Exists | `docs/ARCHITECTURE.md` §5; `research/robustness/mcp_probe_findings.md` |
| Memory and state management approach | `docs/MEMORY_STATE.md`: the run directory, checkpoints, ledger, registry, resume, replay, `--previous`, no cross-run learning, and the settings that configure them | Exists | `docs/ARCHITECTURE.md` §7, §11; ADR-009 |
| Validation and review approach | `docs/VALIDATION.md`: the in-run checks and invariants, the harness, the pre-registration, the robustness suite and the results so far | Exists | `docs/ARCHITECTURE.md` §6, §8, §9; `docs/REPRODUCIBILITY.md`; `docs/SEALING.md` |
| Assumptions, limitations or known constraints | `docs/LIMITATIONS.md`: what the agent and the evaluation cannot claim, each with the file that records it | Exists | `docs/USER_DECISIONS.md`; the `MEASUREMENT.md` files under `docs/live_runs/`; `docs/live_runs/QUALITY_COMPARISON.md` |

## 2. Lab §5.1 deliverables

| Lab §5.1 deliverable | Where it lives | Status |
|---|---|---|
| Source code | `agent/` (the agent) and `harness/` (the evaluation harness) | Exists |
| Configuration files | `config/` (`agent.yaml`, `criteria.yaml`, `stop_rules.yaml`, `tools.yaml`, `endpoints.yaml`, `url_policy.yaml`, `persona.yaml`, `ui.yaml`, `eval.yaml`, `profiles/`) | Exists |
| Prompts | `prompts/*.md` with `prompts/PROMPTS.lock` | Exists |
| Instructions | `README.md`: what it is, requirements, install, run, configure, reproduce, evaluate, status | Exists |
| Workflow definitions | `agent/sit_review_agent/states.py`, printed by `dra states`; explained in `docs/PLANNING_EXECUTION.md` | Exists |
| Memory configuration | `docs/MEMORY_STATE.md` "The settings that configure it" | Exists |
| Orchestration logic | `agent/sit_review_agent/orchestrator.py`, explained in `docs/PLANNING_EXECUTION.md` and `docs/TOOL_ORCHESTRATION.md` | Exists |
| Supporting documentation | `docs/` (this map lists it); `research/` notes | Exists |
| Dependencies | `pyproject.toml` (exact pins), listed in `docs/TECHNOLOGIES.md`; no lock file of the resolved tree | Partial |
| Installation steps | `README.md` "Install" | Exists |
| Execution procedures | `README.md` "Run"; `docs/DEMO_DAY_RUNBOOK.md`; `docs/DEMO_DAY_SCRIPT.md` | Exists |
| Design review outputs generated during the lab session | `outputs/lab_session/` (prepared, empty until the session; see its `README.md`) | Prepared |
| Supporting evidence, references and research findings used in the final conclusions | Each lab-session run's `ledger.json` and `snapshots/` under `outputs/lab_session/` | Prepared (with the row above) |
| "Allow evaluators to understand the agent design, reproduce the exercise and review the outputs" | `docs/ARCHITECTURE.md` (understand), `README.md` "Reproduce" and `docs/REPRODUCIBILITY.md` §7 (reproduce), `outputs/lab_session/` and `docs/live_runs/` (review) | Partial (lab-session outputs come on the day) |

## 3. Lab §5.2 repository rules

| Lab §5.2 requirement | Where | Status |
|---|---|---|
| Submission through a GitHub repository, with the SIT officers invited as collaborators | `docs/DECISIONS.md` ADR-005 (privacy decision) | Owner action (`docs/SUBMISSION_GAPS.md` rows 1 and 2) |
| Grant access to `SIT-calebying` and `Makienhui-sit` before the submission deadline | GitHub Settings, Collaborators; invitations expire if not accepted within 7 days | Owner action (`docs/SUBMISSION_GAPS.md` row 1) |
| The repository remains accessible throughout the evaluation period | Do not delete, archive, rename or transfer the repository, revoke the invitations or rewrite history until SIT confirms the evaluation is over | Owner action |
| All materials needed to review, deploy and execute the agent | `README.md` "Install", "Configure", "Run"; `docs/REPRODUCIBILITY.md` §7 | Exists |
| Clearly organised; installation, configuration and execution instructions | `README.md` | Exists |
| Identify dependencies, datasets, configuration settings, model requirements, third-party services | `README.md` "Requirements" and "Configure"; `docs/TECHNOLOGIES.md` | Exists |
| No secrets committed; instructions to configure the environment | `.env.example` (names only), `README.md` "Configure" and "Secrets"; no `gitleaks` hook yet | Partial (`docs/SUBMISSION_GAPS.md` row 25) |
| Material that cannot go through GitHub goes by email to the SIT officer | Expected: none; the SIT PDFs are SIT's own and are not committed | Owner action |

The row-by-row status and the task left for each row are in `docs/SUBMISSION_GAPS.md`.

## 4. Lab §5.4 demo day

| Lab §5.4 item | Where | Status |
|---|---|---|
| Session format: design walkthrough, live execution on an SIT artefact, on-the-spot modification | `docs/DEMO_DAY_RUNBOOK.md` intro and §3 timeline | Exists |
| (a) Explain the design, choices and reasons; optional short deck | `docs/DEMO_DAY_RUNBOOK.md` §8 (talking points); `docs/ARCHITECTURE.md` (§13 is the walkthrough script); optional `docs/slides/` | Exists (deck optional, not made) |
| (b) Laptop that runs the agent and can be modified | `docs/DEMO_DAY_RUNBOOK.md` §1-3 | Exists (procedure; every step depends on code listed in runbook §9) |
| (c) Run on a new artefact provided by SIT during the interview and show the output | `docs/DEMO_DAY_RUNBOOK.md` §5-7 | Exists (procedure; depends on runbook §9) |
| (d) Modify on request and show the new behaviour | `docs/DEMO_DAY_RUNBOOK.md` §4 | Exists (procedure; depends on runbook §9) |

## 5. Governance documents (this set)

| File | Purpose | Status |
|---|---|---|
| `docs/DECISIONS.md` | Architecture decision records | Exists |
| `docs/REPRODUCIBILITY.md` | Reproducibility policy and run-manifest schema | Exists |
| `docs/DEMO_DAY_RUNBOOK.md` | Demo-day procedure | Exists |
| `docs/SEALING.md` | Sealing of answer keys and held-out sets | Exists |
| `docs/BUDGET.md` | Project cost budget | Exists |
| `docs/DOCUMENTATION_MAP.md` | This map | Exists |
| `docs/SUBMISSION_GAPS.md` | Every artefact of lab §5.1 to §5.3 with its status and the task left | Exists |
| `docs/LIMITATIONS.md` | Limitations, assumptions and known constraints | Exists |

## 6. Where each research note feeds in

| Research note | Feeds |
|---|---|
| `research/frameworks/` | ARCHITECTURE, ADR-001, TOOL_ORCHESTRATION |
| `research/models/` | ADR-002, ADR-003, BUDGET, CONTEXT_MANAGEMENT |
| `research/methodology/` | VALIDATION, REPRODUCIBILITY, SEALING, ADR-004 |
| `research/grading/` | VALIDATION, DEMO_DAY_RUNBOOK §8 |
| `research/robustness/` | ARCHITECTURE, TOOL_ORCHESTRATION, MEMORY_STATE, VALIDATION, DEMO_DAY_RUNBOOK §7 |
| `research/kaggle/` | VALIDATION (techniques only; no Kaggle data is used) |
| `research/audit/` | LIMITATIONS, and the ADRs that resolve its items |
