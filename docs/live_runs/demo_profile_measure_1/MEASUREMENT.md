# Demo profile measurement run 1 (2026-10-03)

One live run of the review agent with `--profile demo`, measured against the 540 s demo deadline (USER_DECISIONS #12).
Runs used: one Opus run of the two allowed, plus one Haiku pre-flight call ($0.0062).

## Result

The run finished in 420 s with exit 0, but it did not assess the design: understand and plan took 241 s together, which left assess 179 s before the 420 s limit, and the assess call was cut there.
The report is honest about it: verdict `not_assessed`, confidence 0, no findings, four disclosed limitations.
At `medium` the demo profile does not fit a 10-minute slot, and no reserve value fixes that.

## Command and conditions

- Command, from the repo root: `sit-review review eval/synthetic/payments_orchestration/design_v1.pdf --profile demo --no-tools --run-id demo_profile_measure_1`, under `env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN`.
- Tree: branch `s4/demo` at `2d84f59`, clean; `make smoke` exit 0 (196 tests) before the run.
- Backend `claude_code` (Claude Code 2.1.287, `claude -p`), model `claude-opus-5-5` requested and served; neither key variable was set.
- `review` is an alias of `run` in today's CLI, so the handover's command ran unchanged; started 2026-10-02T20:03:05Z (04:03 local), ended 20:10:05Z.
- The Mac (8 cores) was running other work: load average 8.76 / 9.99 / 10.09 just before, 11.43 / 10.87 / 10.47 just after.
- The run's own process used 14.8 s of CPU in 421 s, so the time is model time; the load's effect on `claude -p` start-up is not measured.

## Per-phase table

| Phase | Wall | Output tokens | Cost (CLI estimate) | Effort | Attempts | Cache creation / read |
|---|---|---|---|---|---|---|
| ingest | 3.5 s | n/a | 0 | n/a | n/a | n/a |
| understand | 135.9 s | 18,033 | $0.608 | medium | 1 | 30,890 / 0 |
| plan | 101.7 s | 10,065 (22 questions, 7 external) | $0.493 | medium | 1 | 36,480 / 0 |
| research | 0.0 s (document-only, disclosed) | 0 | 0 | low | 0 | n/a |
| assess | 178.9 s, cut by the deadline at run time 420 s | not recorded (call killed) | not recorded | medium | 1, not retried | not recorded |
| refine | skipped: the deadline rule had fired | 0 | 0 | medium | 0 | n/a |
| verify | 0.007 s, no model call | 0 | 0 | medium | 0 | n/a |
| report | 0.11 s, no verdict call | 0 | 0 | medium | 0 | n/a |
| total | 420.1 s (manifest), 420.9 s (`/usr/bin/time`) | 28,098 recorded | $1.10 recorded | | 3 calls | 67,370 / 0 |

The cut assess call is billed but unrecorded; at the measured 99 to 133 output tokens per second it had produced about 18k to 24k tokens when it was killed.
At the blended $39 per million output tokens of the two finished calls that is $0.7 to $0.9, so the true cost is near $1.9 (an estimate, not a meter reading).
Run clock: understand ended at 139.4 s, plan at 241.1 s, assess was cut at 420.0 s, the report was written at 420.1 s.

## Against the 540 s deadline

- The run ended 120 s inside the deadline; that slack is the whole verify and report reserve, unused because a not-assessed report makes no model call.
- Research: not run (`--no-tools`), disclosed as DEG-002; with tools on it would also get no time, since it must end by 220 s and plan ended at 241 s.
- Assess: cut after 179 s, disclosed as DEG-003, and the verdict says "out of time before assessment".
- Refine: skipped by the deadline rule, disclosed as DEG-004.
- Verify and report: code only, no model call; 65 registry anchors resolved, 0 repaired, 0 unresolved; invariants INV-03 to INV-10 passed.
- DEG-001 is the text-only input (the backend takes no native PDF block); every skipped, cut or degraded phase is disclosed in `report.md`.

## Outcome against the first live run

| | First live run (`high`, 3,372 s) | This run (demo profile, 420 s) |
|---|---|---|
| Verdict | `fit_with_conditions`, confidence 0.68 | `not_assessed`, confidence 0 |
| Findings | 21 (1 critical, 11 high, 8 medium, 1 low) | 0 |
| Sound areas | 5 | 0 |
| Unresolved items | 12 | 0 (7 unanswered research questions are listed) |
| Anchors | every finding anchored, 1 repair call | no finding; 65 registry anchors resolved |

The demo profile lost all 21 findings, all 5 sound areas and the verdict; it kept the design-intent summary, the 62-entry registry of decisions and constraints, and the 22-question plan.
The answer key was not opened and nothing was scored.

## What `medium` bought, and are the reserves sized right?

Understand: 158 s and 22,227 output tokens at `high`, 136 s and 18,033 at `medium` (14 % less wall, 19 % fewer tokens).
Plan: 158 s and 17,003 tokens at `high`, 102 s and 10,065 at `medium` (36 % less wall, 41 % fewer tokens).
Assess at `high` took about 520 s and 63,392 tokens.
Scaled by the two measured token ratios, assess at `medium` would need about 310 to 420 s; it had 179 s.
That range is an estimate: a finished assess at `medium` has never been measured.

- `report_reserve_seconds: 120` was not tested, because verify and report made no model call; at `high` they took 33 s and 88 s, so 120 s at `medium` is plausible and unconfirmed.
- `assess_reserve_seconds: 200` is too small for assess by the estimate above, but it only limits research, and research already gets nothing.
- The binding sum is not a reserve: 3.5 + 135.9 + 101.7 = 241 s are gone before assess starts, so assess gets 540 - 120 - 241 = 179 s.
- With the report reserve cut to 60 s assess would get 239 s, and with it at 0 it would get 299 s: both under the 310 s low estimate, and the second leaves no time for a verdict.
- So no reserve was changed, and the second run was not used: there was no reserve adjustment to confirm.
- `config/profiles/demo.yaml` keeps its values and its comments now state what was measured; runbook section 5 carries the same note; section 4.1 is unchanged.
- An effort change (for example `low` for understand and plan) is a quality decision and belongs to the planner.

## Is the demo viable live in a 10-minute slot?

Not with this profile at `medium`.
A complete document-only run at `medium` is estimated at 3.5 + 136 + 102 + (310 to 420) + (0 to 33) + (52 to 71) = about 600 to 770 s without refine.
That is 10 to 13 minutes of run time, and the runbook starts the run at 0:30.

Recommendation: show a pre-recorded run with `dra replay`, and start a live run alongside it with a deadline that lets it finish (`--deadline 900` or more).
The live report is shown if it lands while the interview is still going; the replay carries the walk-through either way.
This needs one complete recorded run at the demo settings, which does not exist yet: this directory holds a not-assessed report, and the first live run has no `llm.jsonl`.
If a live run inside 540 s is required, the only lever left is effort (`low` on understand, plan and assess), which is unmeasured and needs one more approved run of about $2 to $3.
The runbook section 4 short rerun (`--profile demo --deadline 300`) cannot assess either: it gives understand, plan and assess 180 s together, and understand plus plan alone took 238 s.
The decision is the planner's.

## Prompt cache and replay

Not read: both finished calls wrote the prefix (30,890 and 36,480 cache-creation tokens) and read 0 tokens.
Plan started 136 s after understand, inside the 5-minute cache lifetime; each call was a new CLI session (`--session-id`, no resume), as in the first live run.
`dra replay docs/live_runs/demo_profile_measure_1` works offline on this directory: run with `claude` off the `PATH` and no API key, it exits 0 in 4.0 s with 3 model calls and 0 tool calls replayed.
The replayed report matches the recording (ignoring run IDs, times, paths and the run manifest).
Replay prints the recorded timeline at once; it does not pace itself to the recorded 420 s.

## What is and is not in this directory

- Committed: `report.md`, `report.json`, `manifest.json`, `effective_config.json`, `state.json`, `llm.jsonl`, `anchors.json`, `ledger.json`, `checkpoints/`, `text/`.
- Left out: `progress.log`, which `.gitignore` excludes (`*.log`), as in the first live run; replay does not need it.
- Secret scan (counts first, then field names with value lengths only): no key-shaped `sk-` string, no `Bearer`, no `oauth`, no e-mail address, no long encoded string.
- The matches are words of the synthetic design text, usage field names such as `output_tokens`, config key names, one environment variable name and two vendor host names; no value is a credential.
- `llm.jsonl` holds the three CLI session IDs (36-character identifiers of local sessions, not credentials).
- One absolute path with the user name is committed, `effective_config.json` `config_root`; the first live run's committed file holds the same field with a home-directory path, so that precedent was followed.

## Observations for the agent owners (not fixed here)

- A call cut by the deadline records no tokens and no cost, so the manifest under-reports spend ($1.10 against about $1.9); `llm.jsonl` entry `llm-0003` has `outcome: LLMDeadlineError` and zero usage.
- The manifest records the branch as `demo` for `s4/demo`; `agent/sit_review_agent/manifest.py` line 86 keeps only the last segment of the ref.
- `report.md` prints "Located at: p.1 §1, p.2 §1, p.2 §1", one location twice.

## Not verified

- Assess, refine, verify and report at `medium` to completion: none of them finished or made a model call here.
- Whether Opus 5.5 through `claude -p` can pass 64,000 output tokens: no call came near the cap.
- The true billed cost, where nested `claude -p` calls are billed, and the effect of the machine's load on these timings.
- Any run with tools; nothing touched the SIT MCP hosts.
