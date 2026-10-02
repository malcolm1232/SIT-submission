# Documentation map

Date: 2026-10-02. Maps every documentation requirement in the lab brief to the file that will satisfy it, so nothing is left out of the submission (audit M10). Lab §5.3 says the repository "may include sufficient documentation to explain" eight topics; §5.1 lists the deliverables; §5.2 the repository rules; §5.4 the demo.

Status: **Exists** (written, may still grow), **Partial** (some content exists elsewhere and must be consolidated), **Not yet** (planned). "Sources" are the research notes and decisions the file draws on. All paths are relative to the repo root.

## 1. Lab §5.3 documentation topics

| Lab §5.3 topic | File that satisfies it | Status | Sources to draw on |
|---|---|---|---|
| The overall agent architecture | `docs/ARCHITECTURE.md`: state-machine diagram generated from `agent/states.py`; the LLM and Tool gateways; evidence ledger; decision-and-constraint registry; checkpoints and exit codes; `explain` and coverage map; report template (audit M13) | Not yet | `docs/DECISIONS.md` ADR-001; `research/frameworks/README.md`; `research/robustness/README.md` §10; audit §1.2 |
| The agent framework and technologies used | `docs/DECISIONS.md` ADR-001 (custom loop, Anthropic SDK, direct MCP client), ADR-002 (Claude Opus 5.5), ADR-006 (pdfplumber); a "Technologies" section in `docs/ARCHITECTURE.md` listing every pinned dependency from `uv.lock` | Partial (ADRs exist) | `research/frameworks/README.md` and `comparison.md`; `research/models/README.md` |
| Context management approach | `docs/CONTEXT_MANAGEMENT.md`: what each stage sees; the cached prefix (tools, system prompt, native PDF block, canonical page-marked text); how document content and external research are kept apart (`source: doc \| external \| inference`, ledger IDs, spotlighting of untrusted text); context size per call; why compaction is not needed for one document | Not yet | ADR-006, ADR-007; `research/models/README.md` §3; lab §4.2 |
| Planning and execution approach | `docs/PLANNING_EXECUTION.md`: stage-by-stage flow; plan schema; fixed action types with adaptive queries (audit C18); stop rules and the stop-reason enum; deadline-aware planner; refine loop and when conclusions are revised | Not yet | `research/frameworks/README.md`; `research/robustness/scenarios.md` BEH-01, BEH-24; lab §4.3, §4.5 |
| Tool orchestration approach | `docs/TOOL_ORCHESTRATION.md`: ToolGateway (timeouts, retries, breakers, budgets, URL policy); parallel warm-up and `preflight`; per-server health; tool allowlist; how tool errors reach the model; record/replay cassettes | Not yet | `research/frameworks/README.md` §4; `research/robustness/README.md` §5, §6.2; `docs/DEMO_DAY_RUNBOOK.md` §4.1 (config spec) |
| Memory and state management approach | `docs/MEMORY_STATE.md`: run state object; per-stage checkpoints and `resume`; the evidence ledger; the approved-decision registry (preserved across iterations; INV-10); previous-run memory for v2 re-review (`--previous`); deliberately no cross-run learning (overfitting control) | Not yet | `research/robustness/README.md` §10 items 3, 5, 6; audit C17; `docs/DECISIONS.md` ADR-009 (checkpoints, journal, resume) |
| Validation and review approach | `docs/VALIDATION.md`: the agent's own verify stage (anchor checks, ledger checks, registry checks, completeness against lab §2.3); invariants INV-01 to INV-11; the evaluation design (tiers, metrics, baselines, k runs) and its results; grading; robustness results table. Supported by `docs/REPRODUCIBILITY.md` and `docs/SEALING.md` | Partial (`REPRODUCIBILITY.md`, `SEALING.md` exist) | `research/methodology/`; `research/grading/`; `research/robustness/`; ADR-003, ADR-004, ADR-007 |
| Assumptions, limitations or known constraints | `docs/LIMITATIONS.md`: same-family instruments if ADR-003 resolves to branch B; small n and exploratory per-category results; template homogeneity of the synthetic set; one human rater; possible silent model updates behind `claude-opus-5-5`; unverified MCP behaviour until probed; no offline review of unseen documents; refusal handling; budget cuts actually taken (`docs/BUDGET.md` §5) | Not yet | audit §3, §4; `research/robustness/README.md` §11; `research/methodology/README.md` §11 |

## 2. Lab §5.1 deliverables

| Lab §5.1 deliverable | Where it lives | Status |
|---|---|---|
| Source code | `agent/` | Not yet |
| Configuration files | `config/agent.yaml`, `criteria.yaml`, `stop_rules.yaml`, `tools.yaml`, `endpoints.yaml`, `url_policy.yaml`, `persona.yaml`. Layout specified in `docs/DEMO_DAY_RUNBOOK.md` §4.1 | Not yet (spec exists) |
| Prompts | `prompts/*.md` with `prompts/PROMPTS.lock` (content hashes; `docs/REPRODUCIBILITY.md` §4) | Not yet |
| Instructions | `README.md`: what the agent does, quick start, links into `docs/` | Partial (`README.md` exists without install or run steps) |
| Workflow definitions | `agent/states.py` (enum and transition table) and the generated `docs/diagrams/state_machine.mmd` | Not yet |
| Memory configuration | `docs/MEMORY_STATE.md` plus the checkpoint and ledger settings in `config/agent.yaml` | Not yet |
| Orchestration logic | `agent/` (loop, gateways, stop rules) explained in `docs/PLANNING_EXECUTION.md` and `docs/TOOL_ORCHESTRATION.md` | Not yet |
| Supporting documentation | `docs/` (this map lists it all); `research/` notes | Partial |
| Dependencies | `pyproject.toml`, `uv.lock`, `.python-version` | Not yet |
| Installation steps | `README.md` § Install (`uv sync --frozen`) | Not yet |
| Execution procedures | `README.md` § Run (CLI reference: `dra review`, `preflight`, `explain`, `coverage`, `resume`, `replay`); `docs/DEMO_DAY_RUNBOOK.md` | Partial (runbook exists) |
| Design review outputs generated during the lab session | `outputs/lab_session/<date>/` with each run directory (report, manifest, `llm.jsonl`, `tools.jsonl`) | Not yet (produced on demo day; runbook §3 last row) |
| Supporting evidence, references and research findings used in the final conclusions | `outputs/lab_session/<date>/<run>/ledger.json` and `snapshots/`, rendered as the report's evidence register | Not yet |
| "Allow evaluators to understand the agent design, reproduce the exercise and review the outputs" | `docs/ARCHITECTURE.md` (understand), `docs/REPRODUCIBILITY.md` §7 (reproduce: R0-R3), `outputs/lab_session/` (review) | Partial (`REPRODUCIBILITY.md` exists) |

## 3. Lab §5.2 repository rules

| Lab §5.2 requirement | Where | Status |
|---|---|---|
| Submission through a GitHub repository, with the designated SIT officer invited as a collaborator | `docs/DECISIONS.md` ADR-005 (privacy decision) and a submission checklist in `README.md` | Partial (ADR awaiting user) |
| Grant access to the GitHub IDs `SIT-calebying` and `Makienhui-sit` **before the submission deadline** | `README.md` submission checklist: both invitations sent and **accepted** (check under Settings → Collaborators), with the date recorded; GitHub invitations expire if not accepted within 7 days, so send them early and re-send if needed | Not yet |
| The repository **remains accessible throughout the evaluation period** | `README.md` submission checklist: do not delete, archive, rename or transfer the repo, revoke the invitations, or rewrite history (SEALING §4 purge only before access is granted) until SIT confirms the evaluation is over; the optional public mirror of ADR-005 option 3 never replaces the private repo | Not yet |
| The repository contains **all materials needed to review, deploy and execute** the agent | `README.md` § Install / Configure / Run; `docs/REPRODUCIBILITY.md` §7 (R0-R3); the fresh-clone check (`docs/BUDGET.md` line 9, robustness OPS-08: `uv sync --frozen` on a clean clone, then `make smoke`) | Not yet |
| Clearly organised; installation, configuration and execution instructions | `README.md` | Partial |
| Identify dependencies, datasets, configuration settings, model requirements, third-party services | `README.md` § Requirements: Python version, `uv`, Anthropic API key and model `claude-opus-5-5`, SIT MCP servers and key, judge provider per ADR-003, datasets under `eval/` (with sealed parts named) | Not yet |
| No secrets committed; instructions to configure the environment | `.env.example` (names only: `ANTHROPIC_API_KEY`, `SIT_MCP_API_KEY`), `README.md` § Configure, `gitleaks` pre-commit hook | Not yet |
| Material that cannot go through GitHub goes by email to the SIT officer | Note in `README.md` (expected: none; the SIT PDFs are SIT's own and are not committed; sealed-set passphrases are never shared) | Not yet |

## 4. Lab §5.4 demo day

| Lab §5.4 item | Where | Status |
|---|---|---|
| Session format: design walkthrough, live execution on an SIT artefact, on-the-spot modification | `docs/DEMO_DAY_RUNBOOK.md` intro and §3 timeline | Exists |
| (a) Explain the design, choices and reasons; optional short deck | `docs/DEMO_DAY_RUNBOOK.md` §8 (talking points); `docs/ARCHITECTURE.md`; optional `docs/slides/` | Partial |
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
