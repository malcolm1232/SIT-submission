# Verifier edit log: workstream E2, lecturer grader (2026-10-02)

Scope: `harness/sit_eval/grader/**` and `tests/eval_grader/**`. No edits were made to `judge.py`, E1's files, R's
files, the prompt files or the schema files. The prompt bundle hash is unchanged:
`64efe6b88489ac5542d7028f62782ed3c0b3096b0dfbfc0ac9ead22b4db75df0` (`sit-eval grade lock` reports ok).

Live calls: 2 calls, `claude -p --model claude-haiku-4-5`, `ANTHROPIC_API_KEY` unset. Cost: $0.1071 (Pass A)
and $0.1298 (Pass B), $0.2369 in total. A first attempt was rejected by the CLI before any model call ($0).

## Edits

| # | File | What | Why |
|---|---|---|---|
| 1 | `harness/sit_eval/grader/schemas.py` | `llm_facing()` also drops the `$schema` meta keyword (`META_KEYWORDS`). | Live check: `claude -p --json-schema` refused the stripped Pass A schema with "no schema with key or ref https://json-schema.org/draft/2020-12/schema". Every live grade would have failed on its first call. After the fix, Pass A and Pass B were accepted, and both `structured_output` objects validate against the full schemas. The matcher's judge schemas already drop `$schema` (`sit_eval/prompts.py`). |
| 2 | `harness/sit_eval/grader/pipeline.py` (`_call`) | Any exception from `judge.complete` (not only `JudgeError`) is logged and becomes a `GraderError`. | Probe: a `TimeoutError` or `RuntimeError` from the client escaped. No `grade.json` was written, nothing went to the call log, and the CLI ended in a traceback instead of exit 3. |
| 3 | `harness/sit_eval/grader/costs.py` (`Budget.check`) | Added a 1e-9 USD tolerance (`BUDGET_EPS_USD`). | Probe: with a limit of $0.30 and $0.10 already spent, a $0.20 call was refused, because 0.1 + 0.2 > 0.3 in floating point. A call landing exactly on the limit is now allowed. |
| 4 | `harness/sit_eval/grader/costs.py` | `THINKING_ALLOWANCE` raised from 3000 to 12000 tokens. | Live check: each Haiku smoke call used about 10.5k thinking tokens, so the pre-call estimate behind the hard budget stop was about 3x too low. |
| 5 | `harness/sit_eval/grader/pipeline.py` (`run_pass_b`) | A third Pass B sample is added only when exactly 2 samples were run. Disagreement is computed over all samples. | Probe: `--samples 3` with disagreement ran a 4th sample. Prereg: "2 per review …; a third if …". |
| 6 | `harness/sit_eval/grader/pipeline.py` (`build_report`, `CONVENTIONS`) | Two new human-review reasons: (a) samples disagree on the count of material verified-false hallucinations; (b) samples disagree beyond the third-sample threshold when 3+ samples were requested. Both are recorded in the conventions. | Probe: one sample flagged a verified-false material fabrication and the other flagged none. The median count was 0.5, so no G3 cap applied. The merged list still showed the flag as `verified_false`, and `needs_human_review` was false. The scoring rule (prereg median) is unchanged; only the flag was added. |
| 7 | `harness/sit_eval/grader/answer_key.py` | Read, parse and shape errors in `load_answer_key` raise `GraderInputError` (a `ValueError` subclass). | Probe: a malformed `--answer-key` gave a traceback and exit 1. It now gives a clean message and exit 2. |
| 8 | `harness/sit_eval/grader/cli.py` (`validate`) | A `--variant` without `=`, a malformed review, and a check that needs an authored variant now exit 2 with a message. | Probe: all three gave tracebacks and exit 1. |
| 9 | `harness/sit_eval/grader/cli.py` (`_print_plan`) | Replaced "Opus via `claude -p` … roughly $0.05-0.15 per call" with the measured smoke cost and a warning. | That figure was not supported. A two-finding Haiku call already cost $0.11-0.13. |
| 10 | `harness/sit_eval/grader/projection.py` (`identifying_values`) | Now also scrubbed as whole tokens: display forms of the agent's Claude model ("Opus 5.5", "Claude Opus 5.5"); "Claude Code" when the backend is `claude_code`; every `--flag` on the runner argv (e.g. `--no-tools`); a snake_case `stop_reason.detail` (e.g. `no_tools`); the condition name at any length ≥ 2 (`B0`, `FULL`); `bundle_sha256`, the key the real manifest uses. | Leakage probe on the live review: agent-written text (limitations, verdict, tags, evidence quotes, anchors, registry, sound areas, unresolved items) could carry these values through. The scrub missed them and the leak guard did not see them. The agent's own degradation text includes "(--no-tools, …)", which a limitation can copy. A plain-word detail such as "deadline" is not scrubbed. |
| 11 | `harness/sit_eval/grader/report.py` | `grade.md` shows the mode's weights (delta: D1-D10 × 0.9, D11 10). | `grade.md` showed non-delta weights for a delta grade. Display only; S was already correct. |
| 12 | `tests/eval_grader/test_grader_pipeline.py` (`test_grader_budget_stops_mid_grade`) | Limit 1.0 → 1.3, with a comment. | Edit 4 raised the per-call estimate, so a $1.00 limit stops before the 3rd call. The test still checks a mid-grade stop after 3 calls with spend under the limit. |
| 13 | `tests/eval_grader/test_grader_verify_fixes.py` (new, 15 tests) | Regression tests for edits 1-3, 5-8, 10 and 11, plus a test that a dry run (`run` and `validate`) never builds a judge. | Each edit fails its test without the fix. The exceptions are the dry-run test and the plain-word stop detail test, which guard behaviour that was already correct or was just added. |

## Deviation decisions (implementer's list)

- **Extra G3 cap (D9 ≤ 2, grade ≤ C with ≥ 2 hallucinations). Keep.** This reads the GR §4.2 rows as cumulative: two or more hallucinations also meet the one-hallucination row. The grade cap has no effect, because G2 already fails. The D9 cap keeps scores monotone, so two fabrications can never leave D9 higher than one does. Recommend that the coordinator add one clarifying clause to GR §4.2 before the prereg freeze, because prereg cites GR §4 for gates.
- **Counts instead of shares in the key-alignment diagnostic. Keep.** The denominators are emitted (`key_items`, `key_items_high`), so any share can be derived. Whether "aligned_high_share" counts partial matches is not defined in §5.3. Recommend updating §5.3 to the counts form.
- **Padding K1 → K01. Keep.** It matches the canonical `FlawId` pattern (`^[A-Z]{1,4}-?[0-9]{2,3}$`), and `key_id_map` keeps the original IDs. The other option, relaxing the schema pattern, would change the locked prompt bundle.
- **Median giving x.5 versus GR P9. Keep.** P9 tells the model how to choose between two anchors. It is not an aggregation rule. Prereg `grader.samples` says "median per dimension", and prereg wins.
- **Other deviations. Keep all.** These are the extra `grade_review` kwargs, offline URL checks marked `not_checked_offline`, the repair note held in the lock, and V8 re-ranking.

## Not changed (reported)

See the verifier's report to the coordinator. In short: no per-call `--max-budget-usd` reaches the live judge from the grader CLI. `claude -p` writes its cache at the 1-hour rate. The meta-validation criteria for V1 (median), V4 (counts `suspected` flags) and V10 (the harness regex flags the fixed text) are lenient. The `stop_reason.code` value `tool_failure` reveals a doc-only run, by design of the spec.
