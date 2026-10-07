# SIT AI Engineering Lab: Design Review Agent

This repository holds an autonomous agent that reviews a technical design document against its own stated objectives, researches the claims that need outside evidence through the SIT MCP servers, and recommends a change only when it can say what is wrong, why, and what evidence supports it.
Every finding in its report is anchored to a verbatim quote of the document, and every external citation is a tool call the agent actually made and logged.
Beside the agent sits the evaluation harness that measures it (planted-flaw scoring and a key-blind lecturer grader), built for the SIT AI Engineering Lab Exercise of September 2026.

Read `docs/ARCHITECTURE.md` to understand the design, this file to install and run it, and `docs/LIMITATIONS.md` for what it cannot claim.

## Requirements

| What | Detail |
|---|---|
| Python | 3.13 (tested with 3.13 from Homebrew); `pyproject.toml` declares `>=3.11`, but only 3.13 was used for the checks below |
| Operating system | macOS 15.6 on Apple silicon (arm64) is the only system this README was verified on; Linux and Windows are not verified |
| Model access | The Claude Code CLI (`claude`, tested at 2.1.288), installed and logged in; the agent runs it headless as `claude -p` and calls `claude-opus-5-5` through it, billed to that login (`docs/DECISIONS.md` ADR-010) |
| Anthropic API key | Not needed with the default backend; the agent strips `ANTHROPIC_API_KEY` from the CLI's environment so a call cannot bill a key by accident. The alternative `anthropic_api` backend reads it (`config/agent.yaml` `llm.backend`) |
| SIT MCP servers | The shared key from the lab brief §2.2, exported as `SIT_MCP_API_KEY`; only needed for reviews with tools on |
| Browser tests | Chromium for Playwright (`playwright install chromium`), only for the `dra ui` browser tests |
| Datasets | Three synthetic design documents with answer keys under `eval/synthetic/`; two held-out items under `eval/blind/`, which nobody opens before sealing (`docs/SEALING.md` §6) |

All Python dependencies are pinned in `pyproject.toml`; `docs/TECHNOLOGIES.md` lists them with their role.

## Install

```
git clone <this repository> sit && cd sit
python3.13 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/playwright install chromium        # once, for the dra ui browser tests
make smoke                                   # offline, under a minute: selftest plus the config, prompt-lock, CLI and leakage tests
```

`make smoke` passing on a fresh clone is the installation check; it needs no key and no network.
The commands below assume the virtualenv is active (`. .venv/bin/activate`) or are prefixed with `.venv/bin/`.

## Run

| Command | What it does |
|---|---|
| `sit-review review <pdf> --profile demo` | A full review with research through the MCP servers, on the 900 s demo profile; writes `runs/<run_id>/report.md`, `report.json` and every log |
| `sit-review review <pdf> --profile demo --no-tools` | The same review document-only, with no MCP key needed |
| `sit-review review <pdf> --profile demo --previous runs/<v1_run>` | Re-assess an updated document against the frozen review of its previous version |
| `dra preflight --profile demo --warm` | Checks the keys by name, the model and each enabled MCP server, and warms the servers before a run |
| `dra ui` | Serves the local review page on `http://127.0.0.1:8765`: start a run, follow its stages live, read the review, export it |
| `dra replay <run_dir>` | Re-runs a recorded run offline from its `llm.jsonl` and `tools.jsonl`; no key, no network |
| `dra coverage <run_dir>` | Prints the criteria by sections coverage map of a run, including "checked, no issue" |
| `dra explain <run_dir> FND-001` | Shows one finding's anchors, evidence, tool calls, criterion and history |
| `dra resume <run_dir>` | Continues an interrupted run from its last checkpoint |
| `dra states` | Prints the stage graph from the code as a Mermaid diagram |
| `sit-review selftest` | Runs the whole pipeline offline on a bundled fixture and checks the invariants |

`dra` and `sit-review` are the same program.
`docs/DEMO_DAY_RUNBOOK.md` is the procedure for the live session and `docs/DEMO_DAY_SCRIPT.md` the minute-by-minute script.
A run writes everything under `runs/`, which git ignores; a run worth keeping is copied into `docs/live_runs/` or `outputs/lab_session/`.

## Configure

| File or variable | What it sets |
|---|---|
| `config/agent.yaml` | Model, effort per stage, output cap, LLM backend, the six assess shards, phases on or off, transport, run root |
| `config/profiles/` | Named overlays chosen with `--profile`; `demo.yaml` sets the 900 s deadline, the three stage limits and `medium` effort |
| `config/stop_rules.yaml` | The active stop rules, deadline, stage limits, tool-call and research-iteration budgets, reserves |
| `config/tools.yaml` | The four SIT MCP servers (two enabled), the auth header, timeouts and the idle-session rule |
| `config/criteria.yaml`, `config/url_policy.yaml`, `config/persona.yaml`, `config/endpoints.yaml` | The eleven review criteria, the URL policy, the reviewer persona and the server endpoints |
| `config/ui.yaml` | The SMTP server for the Email action of `dra ui` (host, username and sender can come from the environment instead); the agent never reads it |
| `config/eval.yaml` | Judge model and settings of the evaluation harness |
| `SIT_MCP_API_KEY` | The shared SIT MCP key; a review with tools on fails fast without it |
| `SIT_UI_SMTP_PASSWORD` | Optional; the SMTP password for the Email action of `dra ui` |
| `SIT_UI_SMTP_HOST`, `SIT_UI_SMTP_USERNAME`, `SIT_UI_SMTP_FROM` | Optional; when not blank they win over the same fields of `config/ui.yaml`, so a personal address need not be committed |

The agent reads the shell environment, not a file: copy `.env.example` to `.env`, fill it in, and load it with `set -a; . ./.env; set +a` before running.

## Reproduce

| Check | Command | Needs |
|---|---|---|
| Smoke | `make smoke` | Nothing |
| Whole offline suite | `make test` (ruff, then `pytest -q`) | Chromium for the browser tests |
| Robustness suite | `pytest tests/robustness -q`, and `python tests/robustness/robustness_repro.py` for the runtime-policy drills | Nothing |
| Replay of a committed run | See below | Nothing |
| A new review | `sit-review review eval/synthetic/payments_orchestration/design_v1.pdf --profile demo --no-tools` | The Claude Code login |

A recorded run replays exactly only at the commit that recorded it, because the replay checks the config and prompt hashes and the code that turns model answers into the report.
At the current tip the committed runs under `docs/live_runs/` do not replay byte for byte (`dra replay` exits 4 with a named divergence, or 2 when the run lacks a log or its document), so replay one at its recorded commit, which the run's `manifest.json` names in `git_commit`:

```
R=$PWD; T=$(mktemp -d); git archive 5f62065 | tar -x -C "$T"
cp -R docs/live_runs/ui_flow_1 "$T/docs/live_runs/"
(cd "$T" && PYTHONPATH=agent:harness "$R/.venv/bin/python" -m sit_review_agent replay docs/live_runs/ui_flow_1)
```

It prints "replayed report matches the recording" and exits 0.
`docs/REPRODUCIBILITY.md` §7 defines the four levels of reproduction, from this re-render to a full live re-run.

## Evaluate

```
sit-eval score <run_dir> --key eval/synthetic/<item>/answer_key.canonical.json --dry-run      # planned calls and cost, no call
sit-eval score <run_dir> --key eval/synthetic/<item>/answer_key.canonical.json --exploratory  # Opus judges through the Claude Code login
sit-eval grade run <run_dir>/report.json --pdf <design.pdf> --judge claude_code              # key-blind lecturer grader
```

`--judge fake` runs either command offline with a scripted judge, which checks the pipeline but scores nothing.
The answer keys are not signed off by the owner, so `sit-eval score` refuses them with exit 2 unless `--exploratory` is given, and every score made that way is marked exploratory and may never be reported as confirmatory (`docs/USER_DECISIONS.md` #26).
`harness/README.md` describes the matcher, the metrics and the blinding; `eval/prereg.yaml` is the pre-registered analysis.

## Layout

| Path | What is there |
|---|---|
| `agent/` | The agent package `sit_review_agent`: stages, model and tool gateways, ledger, report, CLI, UI (`agent/README.md`) |
| `harness/` | The evaluation package `sit_eval`, which the agent never imports (`harness/README.md`) |
| `config/` | Every setting a run uses, including the live-change files of the runbook |
| `prompts/` | The prompt bundle and its hash lock `PROMPTS.lock` |
| `spec/` | The finding and review JSON schema, the flaw taxonomy and the answer-key schema |
| `eval/` | The synthetic evaluation items, the held-out items, the pre-registration and the evaluation plan |
| `docs/` | Architecture, the §5.3 topic files, decisions, runbook, budget, live runs with their measurements |
| `outputs/lab_session/` | The review outputs of the lab session, committed after the session |
| `research/` | Research notes and the audit trail behind the decisions |
| `scripts/` | The MCP probe, the leakage grep, the public-snapshot exporter |
| `tests/` | The offline test suite; `tests/robustness/` is the robustness suite |

`docs/DOCUMENTATION_MAP.md` maps every requirement of lab §5.1 to §5.3 to its file.

## Status (7 October 2026)

What the repository holds:
- The review agent, `sit-review` (alias `dra`), with a demo profile whose run deadline is 900 s (`config/profiles/demo.yaml`); assess runs as 6 criterion shards side by side (`config/agent.yaml`).
- `dra ui`, the local review page: start a run from a dropped PDF or link, follow each stage live, read the review in its Review, Coverage and Evidence tabs, ask follow-up questions in chat, and download the review as a zip (one cross-linked HTML page, the reviewed PDF, `report.md`, `report.json`).
- The "Architectural design" page inside `dra ui`, which explains the agent's design with links to the code in this repository.
- A research fix of 6 October 2026: a tool failure reported inside a tool's answer is marked as failed and never enters the evidence ledger (`agent/sit_review_agent/tools/inband.py`).
- Sample review outputs with their measurements in `docs/live_runs/`, each folder holding the run's `report.md`, `report.json`, evidence ledger and `MEASUREMENT.md` where one was written.

Measured, each on one document and one run:
- Document-only on the synthetic payments design at the demo profile: 382 s and $5.74, strict recall 13 of 14 planted flaws, lenient recall 14 of 14, adjudicated precision 0.944, grader 83.0 (B); the earlier sequential design took 3,372 s (`docs/live_runs/QUALITY_COMPARISON.md`).
- With tools, from `dra ui`, on the lab's own sample document with 6 assess shards: 508.5 s, verdict `fit_with_conditions` at 0.60; all 10 web tool calls succeeded, 8 of them after reopening a closed MCP session (`docs/live_runs/sit_sample_ui_2/MEASUREMENT.md`).
- Re-assessment of the updated payments design (v2) against the v1 review, document-only: 422.8 s, verdict `not_fit` at 0.75, 2 prior findings resolved, 4 partially addressed, 10 still open and 3 new, unscored (`docs/live_runs/reassess_payments_v2_1/MEASUREMENT.md`).
- Robustness: 88 P0 scenarios, 56 passing offline, 32 blocked as laptop-only or static, none failing (`tests/robustness/results/robustness_summary.txt`).

Not measured: the research fix of 6 October against the live servers, any run repeated k times, the held-out items, and the 132-run Tier A study, which awaits budget approval (`docs/BUDGET.md` §6).
Every score so far is exploratory (`docs/LIMITATIONS.md`).

## Limitations

`docs/LIMITATIONS.md` lists everything the agent and its evaluation cannot claim, each with the file that records it.

## Secrets

No key, password or token is committed, and `.gitignore` excludes `.env`.
The secret environment variables are `SIT_MCP_API_KEY` (the MCP servers) and `SIT_UI_SMTP_PASSWORD` (optional email); `.env.example` names them, and the optional `SIT_UI_SMTP_*` address variables, with empty values.
The agent's logs redact secrets, and the held-out answer keys are handled as `docs/SEALING.md` describes.
