# Session 4: latency and demo design report (2026-10-03)

Worker: the design-research worker for the 10-minute demo slot.
Branch `s4/demo`, from `feb1d9f`, in the worktree `SIT-wt/demo`.
Nothing was pushed; no product code, config, prompt or test was changed.
The deliverable is `docs/design/latency_and_demo_design.md` (227 lines).

## Result

The time of a run is output volume behind a fixed thinking block per model call, so no reserve or effort setting alone fits the sequential eight-phase chain into 540 s.
The recommended design runs understand, plan with research, and four assess shards concurrently, then one revision-only refine and a verdict-only report call, all at `medium`, in one profile for the demo and the evaluation.
Predicted total: 443 s document-only (slack 97 s), 450 to 499 s with research, from measured rates; every stage degrades gracefully when its limit fires, and `not_assessed` is left for a run in which no shard finished one finding by 265 s.
The note also records two findings outside the brief: the user-level hooks and plugins on this Mac add about 7 s and 1,433 input tokens to every `claude -p` call, and a cut call can be salvaged because the structured answer streams.

## Probes and spend

All calls went through `/Users/malco/.local/bin/claude -p` with both key variables removed, with the gateway's argv shape, from the scratchpad folder `latency_design/`.

| Probe | Calls | Model | CLI cost field | What it measured |
|---|---|---|---|---|
| A, A2: start-up and settings overhead | 10 | Haiku 4.5 | $0.033 | 0.02 s for `--version`; 9.6 to 12.7 s per trivial call with user settings, 3.0 to 3.5 s with `--setting-sources ""` or `--safe-mode` |
| B: 1, 4 and 8 simultaneous sessions | 14 | Haiku 4.5 | $1.415 | parallel, no error; per-call rate unchanged; output 5,366 to 42,606 tokens for one prompt |
| D: cache sharing across sessions | 10 | Haiku 4.5 | $0.163 | shared only with identical schema, system prompt and prefix bytes; a 4 s stagger lets the second session read |
| F: four concurrent assess shards | 4 | Opus 5.5 | $0 reported (cut) | thinking 99.5 to 110.8 s, JSON 304 to 316 chars/s, 18,028 to 21,034 chars streamed at the 170 s cut |
| Total | 38 | | $1.611 | |

The four Opus calls were cut by my own 170 s probe timeout while still streaming, so the CLI reported no cost for them.
Estimated from the streamed volume and the measured rates, they cost $2.0 to $2.4, so the true spend is about $3.6 to $4.0, and I stopped probing at that point.
Two probe design mistakes caused most of the spend: the Haiku prompt asked for an exact item count, which triggered 11,000 to 43,000 thinking tokens per call, and the shard timeout was set below the time a shard needs.
No full agent run, no tool call, nothing against the SIT MCP hosts, nothing on the SIT Memory Platform PDF, no scoring or grading, and no answer key opened.
Model output of the probes was written to scratch files and read only by script, for counts.

## Answers to the brief

- **Concurrency.** 4 and 8 `claude -p` sessions run in parallel on this Mac and login: 8 calls finished in 182 s against 135 s for one, with no 429 and no queueing visible.
- **Throughput.** Opus 5.5 through the CLI: thinking at about 110 estimated tokens/s, structured JSON at about 310 chars/s per session, whole calls at 99 to 141 tokens/s; the same at four concurrent sessions.
- **Effort levels.** Only `medium` was measured directly; `high` comes from the recorded first run; `low` is unmeasured.
- **Cache.** Sessions share an entry only when the `--json-schema` (the tool list), the system prompt and the prefix bytes are identical; today's layout never shares between phases, and shards could share only with the document in the system prompt, which the note recommends against for now.
- **Start-up.** 1.4 to 2.5 s to the first API message; the rest of the overhead is this login's user settings.
- **Thinking.** An assess call thinks for about 105 s at `medium` whatever its scope, so fan-out divides the typing, not the thinking.

## Files changed

| File | Change |
|---|---|
| `docs/design/latency_and_demo_design.md` | New: the design note (sections 1 to 9 as briefed) |
| `docs/transcripts/session4/latency_design.md` | This report |

Not edited: anything under `agent/`, `config/`, `prompts/`, `eval/`, `tests/`, `harness/`, or any other document.

## Gates

No code changed, so the suite was not run; `git status` shows only the two new files.

## Refused or stopped

- One Bash call of mine was blocked by the harness (a `sleep` chained with other commands); it was replaced by a condition loop and nothing was lost.
- No model call was refused.

## Not verified

- A finished assess shard at `medium`, its finding count and the duplicate rate across shards.
- Refine in revision form, the verdict call at `medium`, research turns on Opus, Opus at `low`, and a shard without the understand output.
- Cache reads between Opus sessions, more than 4 concurrent Opus sessions, the hermetic flag in a cloud session, fast mode, and the `anthropic_api` backend.
- Every number in section 4 of the note that is marked predicted; the first timed rehearsal is the check.
