# Worker note: condition B0, the single-call baseline (2026-10-05)

Under the owner's word of 4 Oct 2026 22:40 ("yes" to plan D: the full agent against a single-call baseline on ten documents) and the planner's delegated shot calling (3 Oct 02:50).
Branch `s4/b0-baseline` from eba6974; nothing pushed, a verifier pushes.

## The definition followed

`eval/prereg.yaml` line 431, `conditions.tier_A`, id `B0`:

> Single call, no tools, whole document plus the same task prompt and output schema (MR §4); the single call is the assess brief with all criteria in one call (with FULL's assess split into concurrent shards, ADR-011; deviations entry 11)

H1 (line 78) compares FULL with B0 on strict recall.

## How to run B0 on a document

```
env -u ANTHROPIC_API_KEY .venv/bin/dra review <pdf> --profile demo --no-tools --condition B0 --run-id <id>
```

`--condition B0` implies `--no-tools`, so the flag may be left out; it is harmless to give.
`--condition` is also on `dra run` (the same command), takes `FULL` (default) or `B0`, is recorded in `effective_config.json` `cli_args` and so reused by `dra resume`, and refuses `--plan-only` and `--orchestrator langgraph`.
`--k N` makes N independent B0 runs.
The manifest of every run now carries `condition` (`"B0"` or `"FULL"`); the harness reads it (`sit-eval score` labels the scores file with it unless `--condition` is given) and `sit-eval aggregate --compare FULL --compare B0` compares the two.

## Design

- `RunRequest.condition` and `RunState.condition` (`Literal["FULL", "B0"]`, default `FULL`), `ConfigOverrides.condition` (B0 disables every tool server).
- `Orchestrator.run`: under B0 the stage 1 slot runs `_b0_stage` instead of `_stage_1`, and the refine stage is skipped (`_b0_skip`, a `phase_skipped` event with reason `condition B0`).
- `_b0_stage`: announces understand, plan and research as skipped, freezes the empty decision registry and records its iteration-0 hash (the report needs one), checks the between-phase caps (the deadline itself, never a stage limit), then runs `AssessPhase.run_shards` with the ONE shard `AssessPhase.shards(ctx)` returns under B0 (`all_criteria`: every criterion of `config/criteria.yaml`, in the run's order), the prompt `assess_single.md`, the label "the single assess call (B0)" and the limit name "run deadline".
  The finished call is stored under `shards/` like a FULL shard, so a resume keeps it; the merge, the `assess` checkpoint, verify, report and the manifest are FULL's code.
- The one call is bounded by the run deadline less the report reserve and by no stage limit: `RunDeadline.deadline_bound` (`llm/runtime.py`) names the phases exempt from `stage_limits_s`; `_run_attach_runtime` sets it to `{assess}` under B0.
  A call the deadline cuts keeps the findings it had finished, as FULL's shards do (the same salvage path in `run_shard`, with "run deadline" in the disclosure instead of "stage 1 limit").
- Exactly one model call: the report phase makes no verdict call under B0 (`fallback_verdict` over the verified findings; the rationale says "condition B0: the single-call baseline makes no verdict call"; an event, not a degradation, because it is the condition's design) and verify makes no anchor-repair call (disclosed as a degradation, because unresolved anchors do affect the review).
- One disclosure is inherent to B0 and kept: "condition B0: no design-intent summary (the single-call baseline runs no understand phase)", so a B0 run's manifest outcome is `completed_degraded` with that one limitation.
- Effort and the profile apply as for FULL (the assess effort key, `--profile`).
- The manifest's top-level `condition` is written from the run state for every run (it was `null` before; FULL runs now say `"FULL"`), and under B0 `extra.model.assess_mode` says `single_call: condition B0, one assess call over every criterion (prompts/assess_single.md), no understand, plan, research or refine`.
  `extra.mode` stays the run mode (its type is the run-mode literal).
- The `run_started` progress event lists the one shard under B0.

## The prompt file

`prompts/assess_single.md`, derived from `prompts/assess.md`: the header comment and the "Scope of this assessment" paragraph differ (one reviewer, every criterion, no later reviewer links decisions or attaches research), everything else is byte-identical (task, content rules, criteria list, delta-review block, reframed and correction blocks).
It is in `REQUIRED_PROMPTS`, in `prompts/PROMPTS.lock` (bundle 2569a967015b) and in the README table; the lock check and the leakage test cover it.

## The replay guard (the one change beyond the brief)

Adding a prompt file changes the bundle hash, and `dra replay` refused every recorded run with "prompts changed since the run" (10 errors in `tests/test_ui_page.py`, which replays the committed rehearsal run).
The guard now checks the prompt files the run recorded (`manifest.extra.prompts.files`, path to SHA-256): a recorded file missing or changed refuses, naming the file; a file added since does not; a manifest without the file map is held to the whole bundle hash as before.
The request-body hash of every replayed call remains the hard check.
`tests/test_cli_replay.py` pins all three branches.

## Tests (`tests/test_b0_condition.py`, eight tests)

- A fake-gateway B0 run on `eval/synthetic/payments_orchestration/design_v1.pdf` (the item the harness tests read) with one scripted assess answer: `report.json` validates against the finding schema and INV-03..INV-10 pass; `llm.jsonl` holds exactly one call (`assess`, conversation `assess-0-s1`); no plan, no intent summary, empty registry; completed phases ingest, assess, verify, report; one stored shard `01-all_criteria.json` with every criterion; four findings through verify and the report with `provenance.phase == assess`; the verdict by rule; one coverage row per criterion; the manifest `condition: "B0"`, `assess_mode` single call, `assess_shards` 1; the four skipped phases announced; no repair call.
- The rendered brief is `assess_single.md` (one prompt hash across the findings; the file has no shard wording).
- `RunDeadline`: under B0 the assess budget is the deadline less the report reserve and exceeds `stage_1_end`; the other phases keep their stage limits.
- The CLI: `--condition B0` reaches `RunRequest` and `cli_args` and disables the tool servers; the default is FULL and is not recorded; `B7` and `--plan-only` are refused.
- The harness scores the B0 run with the fake judge (`--exploratory`, plumbing only: hashes, not judgements) and labels it `B0` from the manifest; the FULL run of the harness tests is scored with `--condition FULL`; `sit-eval aggregate --compare FULL --compare B0` produces `comparison` with `a FULL`, `b B0`, the paired document and the recall paired bootstrap and sign-flip entries.
- A FULL run's manifest says `condition: "FULL"` and has no `assess_mode`.

Mutation: with `b0 = False` in `Orchestrator.run` (the B0 branch never taken) the three run-based B0 tests error (the FULL path exhausts the one-call script) while the CLI, deadline and FULL-manifest tests still pass; `orchestrator.py` restored and `cmp` clean.

## Gates (last lines)

- `ruff check agent harness tests`: All checks passed!
- full suite from the worktree: 1985 passed, 1 skipped, 2 xfailed in 258.48s
- full suite from `~`: 1985 passed, 1 skipped, 2 xfailed in 250.30s
- `sit-review selftest`: selftest passed in 0.4 s
- `make smoke`: exit 0; 256 passed, 1 skipped in 12.98s
- `python -m sit_review_agent.prompts --check`: PROMPTS.lock up to date (bundle 2569a967015b)
- `scripts/leakage_grep.py`: PASS: no unresolved hit in a gated area

Load before every test run: 5-minute average between 5.3 and 9.1, free memory 38 to 47 percent.

## Not done

- No live model call was made; B0 has not been run on a real document.
- The quote and anchor rule learnt here: section `11` of the payments document spans only its heading line, so a quote in its body anchors to `11.3`; the FULL agent is held to the same rule.
- `docs/live_runs/` and `eval/blind/` were not opened; the harness tests read the committed FULL run by script.
