# Edit log: latency redesign W2, orchestration, phases and prompts

Date: 2026-10-03 (Singapore time; clock read 2026-10-02 23:13 UTC).
Worker: a fresh-context agent session on `claude-opus-5-5`.
Scope: branch `s4/w2-latency`, base `7be556d`, worktree `/Users/malco/Desktop/SIT-wt/w2`.
Authority: `docs/design/latency_and_demo_design.md` sections 3, 4, 5, 7 and 8, `docs/design/latency_w0_handoff.md`, and the W2 brief.

Isolation: nothing under `eval/blind/` was opened or listed; `docs/transcripts/session3_coordinator.md` was not read; no model transcript was printed.
Model calls: two Haiku 4.5 calls through `ClaudeCodeGateway` with `env -u ANTHROPIC_API_KEY` (the schema check below); no Opus call and no agent run on a real document.
No call was refused.

## Commits

| Commit | Purpose |
|---|---|
| `047a8cb` | Concurrent stage 1, assess shards, revision-only refine, verdict-only report, prompts and lock, tests |
| `6b491a7` | Remove deprecated W0 names (outputs), switch `PHASE_OUTPUT_TYPES`, stage diagram |
| `b1b03be` | Repair-slack and state-isolation tests; drop an unreachable ledger-offset hold |
| `4031fca` | Retrieve every shard exception, also when stage 1 stops the shards |
| this commit | This edit log and the report |

## Edits

| # | File | What changed | Why |
|---|---|---|---|
| 1 | `agent/sit_review_agent/phases/_isolation.py` (new) | `isolate`, `merge_member`, `StateDelta`, `state_delta`, `apply_delta`, `guarded`, `MemberInterrupted`. | Members run on their own copy of the run state and registry; a checkpoint never holds a running member's half-written state; Ctrl-C inside a task becomes a typed interruption instead of escaping the event loop. |
| 2 | `agent/sit_review_agent/orchestrator.py` | Stage loop over `STAGE_ORDER`; stage 1 as asyncio tasks (`stage1_ready`, `STAGE_1_DEPENDS`); member checkpoints with ordinals; `budget.elapsed_s` at every checkpoint; stage limits as caps; backstop `stage1_grace_s` and `stage1_poll_s`; finished shards stored in `shards/`; `resume_start`; resume restores the clock with `elapsed_for_resume()`; process faults wrap the shards. | Design sections 4 and 5, W2 row of section 7, ADR-009. |
| 3 | `agent/sit_review_agent/phases/assess.py` | K shards (`shards_for`), `ShardResult`, salvage of a cut stream, per-shard disclosures, merge in shard order, ranking by severity and confidence, the stage-level not-assessed rule. | Levers 1 and 8; deterministic IDs; partial reviews instead of crashes. |
| 4 | `agent/sit_review_agent/phases/refine.py` | `RefineRevisionsOutput` via `revision_problems(..., drafts=)` and `apply_revisions`; BEH-10 revert; history notes for keep, merge, withdraw; disclosed fallback. | Lever 9 and the W0 hand-off. |
| 5 | `agent/sit_review_agent/phases/report.py` | `VerdictOutput`; `settle_report_output` returns the verdict only; a cut verdict call falls back by rule (deadline-typed degradation). | Decision 6 of design section 9. |
| 6 | `agent/sit_review_agent/phases/_model_calls.py` | `call_model(conversation=, disclose=, check=)`, `PhaseCall.partial` and `invalid`; `resolve_evidence(shown=)`; `reconcile_coverage(criteria=)`; refine fallback wording. | Shards disclose in their own terms; refine treats unusable revisions like an invalid answer. |
| 7 | `agent/sit_review_agent/phases/plan.py` | Brief without intent, registry and review inputs. | Lever 8. |
| 8 | `agent/sit_review_agent/phases/research.py` | Deadline rule bounded by `stage_limits_s.stage_1_end`. | Research is bounded in stage 1. |
| 9 | `agent/sit_review_agent/phases/verify.py` | The repair call only with more than 60 s of slack before the verify and verdict reserve; otherwise skipped and disclosed. | Design section 4. |
| 10 | `prompts/assess.md`, `plan.md`, `refine.md`, `report.md`, `README.md`, `PROMPTS.lock` | Shard scope paragraph and group only; plan without intent or registry; refine revision rules as `llm/outputs.py` defines them; verdict only; lock regenerated with `python -m sit_review_agent.prompts --write-lock`. | Design section 5, prompts row. |
| 11 | `agent/sit_review_agent/llm/outputs.py` | Deleted `RefineOutput`, `RevisionNote`, `ReportOutput`, `UnresolvedDraft`, `LimitationDraft`; `PHASE_OUTPUT_TYPES` maps refine and report to the new types. | No caller left. |
| 12 | `agent/sit_review_agent/states.py` | `mermaid()` draws the stage table; the deprecation note of `TRANSITIONS` and `ON_CAP` names their last reader. | `TRANSITIONS` and `ON_CAP` still have a reader in a W3 file, so they stay. |
| 13 | `tests/test_orchestrator.py`, `test_llm_phases.py`, `test_run_and_resume.py`, `test_not_assessed_verdict.py`, `test_e2e_synthetic.py` | Updated to the stage order and the new outputs; new tests listed in the report. | Tests in the owned files, none weakened: each changed expectation follows a stated design change. |

## Order of work

The brief asked for failing tests first.
The code and the new tests were written in the same pass, so the failing-first order was not kept for every test; each guard was instead mutation-tested against its test after the commit (report, "Mutation results").

## Haiku schema check

Script: session scratchpad `w2_haiku_schema_check.py`, run directory `w2_haiku_run` (not in the repo).
One refine call and one verdict call on Haiku 4.5 at effort `low`, a guard that answers any second call per phase with a cut so no third call is sent.
Refine: the answer parsed as `RefineRevisionsOutput` (keep, merge, keep); `revision_problems` found one problem, "FND-001 after keep: disposition needs_investigation requires next_step".
The prompt was then made explicit about which dispositions need fields a revision cannot add; that change was not re-checked live (the two-call budget was used).
Verdict: the answer parsed as `VerdictOutput` (`fit_with_conditions`).
Usage: refine 17,934 cache-write, 6,973 cache-read, 17 input and 11,579 output tokens; verdict 4,217 cache-write, 9 input and 2,559 output tokens; the CLI logged no cost, so the spend is an estimate at Haiku 4.5 list prices: about $0.10.
