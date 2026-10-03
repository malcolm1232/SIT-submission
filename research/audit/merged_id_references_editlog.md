# Edit log: merged-ID references (Session 4)

Date: 2026-10-03 (local, UTC+8); clock read 2026-10-03 03:24 UTC at the gates.
Worker: a fresh Opus session, one deliverable; branch `s4/fixrefs`, worktree `SIT-wt/fixrefs`, from `a78d395`.
Report: `docs/transcripts/session4/merged_id_references.md`.
Offline only: no model call, fake gateway only, nothing under `eval/blind/` opened, no `llm.jsonl`, `progress.log` or recorded model output printed (the shards' drafts were read by code for IDs only).

## Commits

| Commit | Change |
|---|---|
| `e093650` | Reproduction on the fake gateway, `tests/test_merged_id_references.py` (two tests, `xfail(strict=True)`) |
| `14b57b4` | Interface change: `FindingIdMap` and `RunState.finding_ids`, `ManifestExtra.finding_ids`, `check_INV_12` (not yet in `check_all`), new module `finding_refs`, `tests/test_finding_refs.py`, the note in `agent/README.md` |
| `2643e87` | The fix: the maps recorded at the merge, refine and verify, the rewrite at report assembly, INV-12 in `check_all`, the `report.md` coverage check, INV-12 in the robustness docs |
| `b303859` | Tests: the report gate refuses a dangling reference; `check_all` runs INV-12 |

## Edits

| # | File | Change | Test |
|---|---|---|---|
| E1 | `agent/sit_review_agent/state/run_state.py` | `FindingIdMap` (shards' own IDs to merged draft IDs, refine's map and the fields refine wrote, verify's map and unverified drafts, prior IDs, rewrite counts); `RunState.finding_ids`, default empty | `test_state_and_manifest_carry_the_map` |
| E2 | `agent/sit_review_agent/models.py` | `ManifestExtra.finding_ids` (default `{}`; the schema's `extra` is a free object, so no schema change) | same |
| E3 | `agent/sit_review_agent/finding_refs.py` (new) | `rewrite_text` (ID runs remapped, repeats dropped, a reference to no finding removed with its parenthetical, "see ..." clause or sentence, else "a finding not in this review"; a text is never emptied), `mark_drafts`, `rewrite_tree`, `IdChain` (shard, draft and final numberings), `manifest_record`, `iter_refs` / `dangling_refs` (INV-12) | `tests/test_finding_refs.py` (29 cases) |
| E4 | `agent/sit_review_agent/invariants.py` | `check_INV_12`, then in `check_all` | `test_inv12_*`, `test_no_dangling_finding_reference_in_report_json_or_md` |
| E5 | `agent/sit_review_agent/manifest.py` | `extra.finding_ids` from `manifest_record` | `test_each_reference_follows_its_finding` |
| E6 | `agent/sit_review_agent/phases/assess.py` `merge` | records each shard's own IDs; moves sound-area text and coverage notes from the shard's numbering to the merged IDs (no later model call reads them); records the prior review's IDs | same |
| E7 | `agent/sit_review_agent/phases/refine.py` | records `refine` (merged ID to kept ID, withdrawn to null) and `refine_fields` | same |
| E8 | `agent/sit_review_agent/phases/verify.py` | records `verify` (renumbered, or null when dropped or unverified) and `unverified` | same |
| E9 | `agent/sit_review_agent/phases/report.py` | `settle_refs` after the verdict call: each text in the numbering it was written in; disclosures name drafts as `draft FND-nnn`; `state.coverage` notes for `report.md`; the report gate also checks the coverage notes | same, `test_the_report_gate_refuses_a_dangling_reference` |
| E10 | `research/robustness/README.md`, `tests/robustness/README.md`, `oracles.py`, `concurrent_oracles.py`, `test_robustness_scenarios.py` | INV-12 row and the invariant ranges in the docstrings (the oracles call `check_all`, so they run INV-12) | robustness suite |
| E11 | `agent/README.md` | interface-change note (callers named), module map row for `finding_refs.py` | none (text) |

Not changed: `llm/outputs.apply_revisions` (see the report for why), any prompt, any committed run directory, the robustness results CSV (regenerated to the scratchpad: equal but for commit, date and duration).

## Mutations

Each guard was removed in place after a `cp` backup, the tests run, and the file restored from the backup with `cp`; `git diff --quiet` on the file after every restore.

| # | Guard removed | Result |
|---|---|---|
| M1 | the merge records no shard map | killed (`test_each_reference_follows_its_finding`) |
| M2 | sound-area text stays in the shard's numbering | killed (same) |
| M3 | coverage notes stay in the shard's numbering | killed (same) |
| M4 | refine records no merge map | killed (same) |
| M5 | refine records no refine-written fields | killed (same) |
| M6 | verify records no unverified drafts | killed (same) |
| M7 | verify records no dropped drafts | killed (same, through the manifest map) |
| M8 | the report does not rewrite | killed (the run fails the INV-12 gate: 2 fixture errors) |
| M9 | the report reads findings in the draft numbering, not the shard's | killed (same test) |
| M10 | disclosures do not mark drafts | killed (`test_no_tools_is_a_doc_only_run`, `test_resume_after_two_of_four_shards_runs_exactly_the_other_two`) |
| M11 | the report leaves coverage notes | killed (the run fails the `report.md` coverage gate: 2 fixture errors) |
| M12 | the gate skips the `report.md` coverage check | killed (`test_the_report_gate_refuses_a_dangling_reference`) |
| M13 | `check_all` without INV-12 | killed (2 tests) |
| M14 | INV-12 reports nothing for a bare dangling ID | killed (5 tests) |
| M15 | the parenthetical removal rule | killed (3 tests) |
| M16 | the never-empty guard | killed (2 tests) |

All 16 killed; every file restored clean.

## Gates (exit codes read)

`ruff check agent harness tests` 0; `pytest -q` from the repo root 0 (1590 passed); `sit-review selftest` 0; `make smoke` 0 (239 passed); `make test` 0 (1590 passed); robustness runner `ROBUSTNESS_RESULTS_CSV=<scratchpad> pytest tests/robustness -q` 0 (159 passed, CSV equal to the committed one but for commit, date and duration); `python scripts/leakage_grep.py` 0 (PASS).

## Refused calls

None.

## Not verified

- No live run with the fix: the counts after the fix come from `dra replay` of the two recorded rehearsals through the new code.
- Verify's renumbering branch (`fates[old] = new`) is not exercised end to end: verify renumbers only an invalid or repeated ID, which the merge never produces.
- Delta mode (prior-review IDs kept) is covered by unit tests only.
- The refine and verdict briefs still show the shards' own IDs in the findings' text to the model; rewriting them would change the recorded requests (see the report).
- Evidence quotes and ledger excerpts are neither rewritten nor checked (verbatim or recorded, append-only); both rehearsals have no finding ID there.
