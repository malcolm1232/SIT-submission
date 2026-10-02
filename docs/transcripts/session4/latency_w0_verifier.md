# Latency redesign W0: verifier report

Date: 2026-10-03.
Branch `s4/w0-interfaces`; merge `5c9d67f`, fixes `a10cd75`, tests and docs `54b1a23`.
Edit log: `research/audit/latency_w0_editlog.md`, "Session 4 verifier".
Hand-off: `docs/design/latency_w0_handoff.md`.

## Verdict

The W0 interfaces are correct against design sections 4, 5 and 7 after the fixes below.
Not ready to push: the full gate run on the final HEAD was stopped by the tool layer after ruff and was not resent, so item 9 is unconfirmed and nothing was pushed.

## Items

1. Freeze rule: PASS for one type commit and one config commit; FIXED the reader lists (missed `cli.py` `states`, `tests/robustness/README.md`, the prompt headers and `prompts/README.md`, `replay._final_state`, `replay.recorded_error` keys, `harness/sit_eval/usage.py` and `metrics.py`). `models.py` and `spec/` unchanged apart from main's docstring; pinned config lines unmoved.
2. Revision-only refine output: FIXED. Merge semantics were undefined and a kept finding could break the spec's rules after the patch (null severity on a risk, unsupported disposition, a challenge with one evidence item); `revision_problems(..., drafts=)` now refuses these and `apply_revisions` is the one exact application. The LLM-facing projection holds only fields the model sets.
3. Verdict-only output: PASS; `VerdictOutput` holds the verdict only. W2 must stop reading model unresolved items and limitations; `assemble_review` already writes them from findings and degradations.
4. Deadline error: PASS; an `estimated_usage` entry key is ignored by `journal_usage`, the harness completeness read and the budget, and the cut call stays `usage: null` with `deadline_cut` (test added).
5. States: PASS; exhaustive enumeration of 625 member states and every finishing order (no hypothesis in the repo).
6. Checkpoint ordinal and elapsed: PASS; FIXED `report/coverage.py` to sort by `checkpoint_file_order`; overlapping-members test added. `replay._final_state` has the same file-name pick and goes to W3.
7. Config keys: PASS; 11 criteria in exactly one of four groups; six builder mutations re-run, all caught.
8. Replay deviation: FIXED; the refusal now names the record, the key and commit 2d84f59 (exit 2, no traceback); decision #30 recorded.
9. Gates: ruff exit 0 at `54b1a23`; the rest not confirmed (see verdict). No em dash on added lines; commits carry the owner's noreply identity and no co-author line.
10. Hand-off written.

## Open decisions

- A disposition change across the `no_change` boundary is not expressible in a revision; options are three more revision fields or a second pass, and the recommendation is to measure in the rehearsal first.
- Model-written unresolved items not tied to a finding are lost with `VerdictOutput`; W2 decides whether code writes them.
