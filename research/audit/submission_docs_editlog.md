# Edit log: submission documentation (2026-10-03, branch `s4/subdocs`)

Scope: close the rows of `docs/SUBMISSION_GAPS.md` that need no owner action and no new runs.
Base: `ab11a0a`.
Environment: macOS 15.6 arm64, Python 3.13.13 (Homebrew), a fresh `.venv` with `pip install -e '.[dev]'`, Claude Code 2.1.288 on PATH (no model call was made).

## Commits

1. `1eff4cf` `README.md` rewritten for a cold clone.
2. `9a1c093` `.env.example`, and `!.env.example` in `.gitignore`, because the existing `.env.*` rule would have ignored the example.
3. `b029bb5` `docs/LIMITATIONS.md` (63 lines, one sentence per line).
4. `3236c93` `docs/TECHNOLOGIES.md`, `docs/CONTEXT_MANAGEMENT.md`, `docs/PLANNING_EXECUTION.md`, `docs/TOOL_ORCHESTRATION.md`, `docs/MEMORY_STATE.md`, `docs/VALIDATION.md`; `docs/DOCUMENTATION_MAP.md` §1 to §3 refreshed; `docs/ARCHITECTURE.md` §8 and §13 robustness counts corrected from 87 and 55 to 88 and 56.
5. `611c40b` `outputs/lab_session/README.md`, and gap row 21 marked Prepared.
6. `2cec90c` `docs/SUBMISSION_GAPS.md` rows updated.

## Commands written into the README, and how each was verified

- `sit-review --help`, `sit-review review --help`: exit 0; the options `--profile`, `--no-tools`, `--previous`, `--run-id`, `--resume`, `--accept-drift`, `--plan-approval` exist.
- `dra ui --help`, `dra replay --help`, `dra coverage --help`, `dra explain --help`, `dra preflight --help`, `dra resume --help`: help printed; default UI address 127.0.0.1:8765 read from the help.
- `sit-review selftest`: exit 0.
- `dra coverage docs/live_runs/rehearsal_concurrent_1` and `dra explain docs/live_runs/rehearsal_concurrent_1 FND-001`: exit 0 (output sent to a file, not read).
- `dra states`: exit 0, prints a Mermaid `stateDiagram-v2`.
- `make smoke`: exit 0, 249 passed; also on a fresh `git clone` of this branch into the scratchpad with a new venv: pip exit 0, `make smoke` exit 0, 249 passed.
- `pytest tests/robustness` is part of the full suite below; `python tests/robustness/robustness_repro.py`: exit 0.
- `sit-eval score <run> --key ... --dry-run`: exit 0, its `lc12` block says a real run refuses the unsigned key.
- `sit-eval score <run> --key ... --judge fake`: exit 2 with "refusing a scored run: answer key ... is not signed off"; with `--exploratory`: exit 0, writes `scores.json`, `scores.md`, `judge_results.jsonl`.
- `sit-eval grade run <report.json> --pdf <pdf> --judge fake`: exit 0.
- `sit-review review <pdf> --profile demo` with and without `--no-tools`, `dra preflight --warm`, `dra resume` and the live judges: NOT executed (they make model or MCP calls); only their argument parsing was checked through `--help`.

## Replay of the committed runs

At the tip, `dra replay` on each committed run under `docs/live_runs/`:
- `rehearsal_concurrent_1`: exit 4, 8 model calls replayed, 1 difference, first `$.findings[17].statement`.
- `rehearsal_concurrent_high_1`: exit 4, 2 differences, first `$.findings[20].statement`.
- `ui_flow_1`: exit 4, 1 difference, first `$.findings[13].statement`.
- `sit_sample_tools_1`: exit 2, its input PDF is not committed (the lab's document).
- `live_cc_opus_payments_v1`: exit 2, lacks `llm.jsonl`.
- `demo_profile_measure_1`: exit 2, its effective config predates the config redesign (as `tests/test_cli_replay.py` expects).
At its recorded commit (`manifest.json` `git_commit` 5f620651ba95), with the tree taken by `git archive` and the run directory copied in, `ui_flow_1` replays with exit 0 and "replayed report matches the recording".
The README carries that exact three-line recipe, run once more verbatim (exit 0).
Why the tip diverges was not investigated; it is recorded in `docs/LIMITATIONS.md` and gap row 23.

## Numbers and their sources

No figure was computed in this change; each is copied from the file named beside it.
- 382 s, $5.74, 13 of 14, 14 of 14, 0.944, 83.0, 3,372 s: `docs/live_runs/QUALITY_COMPARISON.md` "Side by side".
- 428.0 s, $5.54, 0.72, 112.0 s: `docs/live_runs/sit_sample_tools_1/MEASUREMENT.md` "Result".
- 88, 56, 32: `tests/robustness/results/robustness_summary.txt` line 2, and a count of `robustness_results.csv` (88 rows: PASS 56, BLOCKED 32).
- 132 runs: `docs/BUDGET.md` §6.
- Package pins: `pyproject.toml`.
- Claude Code 2.1.288 and macOS 15.6: `claude --version` and `sw_vers` on this machine.

## Link check

A script (scratchpad `subdocs_linkcheck.py`) took every backticked or linked path that starts with a top-level folder or file name in `README.md`, `docs/LIMITATIONS.md`, `docs/DOCUMENTATION_MAP.md`, the six topic files, `outputs/lab_session/README.md` and `docs/SUBMISSION_GAPS.md`, and tested that it exists.
Final result: 222 paths checked, 3 missing, all expected: `.env` (in `README.md` and `docs/SUBMISSION_GAPS.md`) is meant to be absent because git ignores it, and `docs/slides/` is a pre-existing "optional, not made" mention in the map's §4.

## Gates

`ruff check agent harness tests`: exit 0.
`pytest -q`: exit 0, 1836 passed, 0 failed (also 1836 passed at the base before any edit).
`make smoke`: exit 0, 249 passed.

## Incidents

- One replay check used a broad `grep` over the replay's console output and printed one recorded model line (a plan question) to this session; later checks printed only lines starting `replay`, `replayed` or `error`.
- One commit command used `cd` in a compound command rather than `git -C`; it ran in the worktree and committed only `docs/LIMITATIONS.md`.

## Left open

Owner rows 1 (collaborator invitations), 2 (ADR-005) and 24 (demo-day prerequisites) are unchanged.
Row 4 still lacks a lock file; row 25 still lacks a `gitleaks` hook; rows 21 and 22 are filled on the day.
