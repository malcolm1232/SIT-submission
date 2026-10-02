# Handover: the SIT FABLE advisor session (2026-10-02, evening)

For the next session that takes the "SIT FABLE" role. Read this, then `docs/HANDOVER_FULL.md`
§6-§8 and `docs/transcripts/session2_coordinator.md`. Expect 10 minutes.

## 1. Who does what now

| Session | Model | Branch | Role |
|---|---|---|---|
| **SIT OPUS** (`session_018SdTdStnsTAKtinMtMs1so`) | Opus 5.5 | `claude/happy-darwin-d0bl94` | **Main session.** Builds, verifies, commits. Owner's choice on cost grounds. |
| **SIT FABLE** (was "SIT MAC", `session_01XFmYhcJBBHVd1QkUXyauBg`, now out of context) | Fable 5.1 | `claude/great-hopper-hbx7h0` (final at f6b4673 plus this note) | **Advisor.** Answers SIT OPUS's decision requests on the owner's behalf. The owner said: "anything u make the shot call. ok? i give u full access to do it." |

The two sessions talk through the Claude Code Remote `send_message` tool by session ID. A message
arrives in the other session as a user turn, queued until its current turn ends (`priority: next`).
Both branches share the same history up to f6b4673; SIT OPUS has 31+ commits on top (eval harness,
grader, robustness P0 suite, demo CLI, config profiles, two live gradings of the first live run,
answer-key drafts). Nothing on the FABLE branch is missing from the OPUS branch except this file.

## 2. Operating rules the owner agreed

1. SIT OPUS is main. Fable is reserved for decisions, for design moments with many interacting
   constraints (e.g. freezing the eval harness interfaces), and for ONE fresh-eyes audit of the
   whole submission before Tier A. Not for routine verification: verifiers stay Opus subagents.
2. The FABLE session does not commit to the OPUS branch while OPUS is mid-turn. Give OPUS exact
   instructions instead; do work yourself only when OPUS reports idle, and tell it the commit.
3. Answer with a decision, not options. Record every decision that changes the evaluation design
   in `docs/USER_DECISIONS.md` (on the OPUS branch, since OPUS applies it), attributed
   "SIT FABLE for the owner, <date>". The owner's own signature steps stay the owner's.
4. One turn per answer; spawn subagents only when a question needs real investigation. Each Fable
   turn is 2.5x an Opus turn.

## 3. What was decided in the FABLE role so far (already sent to SIT OPUS, 2026-10-02 ~18:50 UTC)

SIT OPUS asked four questions about the answer-key sign-off sheet (`eval/KEY_SIGNOFF.md` on its
branch). The reply, in full, is in the FABLE session log; the substance:

1. **Canary:** key-only for the three S-dev items (do not touch `design_v*.md` or the PDFs; the
   live run and pilots cite their hashes). Embed a canary in every future held-out item before its
   first run.
2. **External facts (20 entries):** accept `research/audit/eval_data_audit.md` as the verification
   for S-dev (`verified` stays false with the audit note). Owner re-check only for held-out keys and,
   before Tier A, for any S-dev fact a graded finding's credit turns on.
3. **Core insights, rule for `substance` mode:** the core insight states the defect and why it is a
   defect, nothing else; numbers, parentheticals and secondary consequences come out unless a
   credit item requires them. Applied: payments F04 and F11 trimmed; clinical F03 and F05 accepted;
   clinical F09 replaced with the verifier's item-12 text; lakehouse F01 loses the zero-data-retention
   clause; lakehouse F04 accepted; lakehouse F05 and F06 get their c2 made supporting in
   `spec/convert_answer_keys.py role_of()`; all drafted dispositions accepted.
4. **payments F15 → AD-004:** link it; rule written down: a decision row is linked when the flaw's
   location cites the section that row governs.

SIT OPUS was told to apply these, re-run `python3 spec/convert_answer_keys.py --tier synthetic
--verify-anchors`, re-hash the sheet, and leave only the owner's signature. It was told to reply
only if something cannot be applied as written. **Check whether it replied** (read notifications,
or `list_events` on its session with kinds user/assistant) before doing anything else.

## 4. Open items you may be asked about next

- **Demo shape** (`HANDOVER_FULL.md` §6 item 1): at `high` effort the five model calls alone take
  ~16 min without research; the 10-minute demo needs `medium` effort, a trimmed assess prompt, or a
  pre-recorded `--replay`. `deadline_seconds: 540` is unreachable with the Claude Code backend at
  `high`. Nobody has decided this yet. My lean: demo at `medium` via a config profile (OPUS added
  `--profile`), keep `high` for Tier A, and say so in the pre-registration.
- **Tier A budget**, redone from the measured cost (≈$3.5-4 per doc-only run at `high`, more with
  research; `HANDOVER_FULL.md` §8). Owner approves `docs/BUDGET.md` §6.
- **The first live run's `assess` used 63,392 of 64,000 `max_tokens`.** If OPUS has not raised
  `max_tokens` or split assess, that is the first thing to decide when a run truncates.
- **Prompt cache misses with the Claude Code backend** (every phase wrote the prefix, read it once).
  Worth one investigation before Tier A; a 1-hour TTL is not selectable through the CLI.
- **Second-provider judge:** owner will fund OpenAI or Google later (USER_DECISIONS #7). Until then
  Anthropic-only with the disclosed same-family limitation.
- **Fresh-eyes audit before Tier A** is the one Fable job left in the plan; do it only when OPUS
  reports prompts and `prereg.yaml` are ready to freeze.

## 5. Money, as last seen (session list, 2026-10-02 18:40 UTC)

| Session | Cloud-credit cost so far |
|---|---|
| SIT OPUS | ≈ $122 |
| SIT FABLE (this role's first session) | ≈ $68 |
| First live agent run (Opus, claude_code backend, doc-only) | $3.68 recorded, likely $8-10 true |

Cloud credits expire 5 November. Model calls of the agent itself bill to the Claude Code login
(ADR-010), not to Console API credit.

## 6. How to resume as SIT FABLE

Start a Fable session on `malcolm1232/SIT`, any branch that has this file, and send:

```
You are SIT FABLE, the advisor session. Read docs/HANDOVER_FABLE.md, then HANDOVER_FULL.md §6-§8.
Check for messages from SIT OPUS (session_018SdTdStnsTAKtinMtMs1so) and answer any decision request
on the owner's behalf per HANDOVER_FABLE.md §2. Do not build; do not commit to the OPUS branch while
it is mid-turn.
```

The scheduled 3-hour check-in that the previous FABLE session had armed was cancelled at handover
(it would have fired into a session that is out of context). Re-arm one with `send_later` if you want
a safety net: read-only, commit log plus session status, intervene only on a failed turn or a wrong
turn against `docs/DECISIONS.md` / `docs/USER_DECISIONS.md`.
