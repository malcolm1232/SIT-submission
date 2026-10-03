# Re-assessment fixes: the four delta defects of rehearsal 1

Date: 2026-10-03, branch `s4/deltafix` from `9958706`.
The edit log is `research/audit/reassessment_fixes_editlog.md`.

## What was fixed

1. A prior finding can no longer disappear without a status.
Every finding of the previous review gets exactly one entry in the new `prior_findings` table of `report.json`: `resolved`, `partially_addressed`, `still_open`, or `withdrawn_on_reassessment` with a one-line reason.
Refine is asked once, through the repair path an invalid answer uses, for every prior finding no kept finding carries forward.
A status still missing after that, or a prior finding whose only successor verify dropped, is recorded `still_open` with `re_examined: false` and the note "not re-examined", and disclosed as a degradation.
INV-13 checks the table against the previous review before `report.json` is written, and the report phase stops with exit 4 when it fails.
A `new_in_update` finding anchored in a section the update changed carries `regression: true`, computed from the two canonical texts the run saves.
2. Finding IDs no longer read as one numbering.
The table is keyed on the prior review's ID, the prior review is not renumbered, and the delta section of `report.md` prints both IDs ("FND-003, was FND-002") or "was FND-011 (no finding in this review)".
3. The Delta tab rows show the prior ID, this review's ID, the status, the re-assessment note, and "new (regression)" for a regression.
4. Without a previous version the Delta tab is shown disabled with the sentence "No previous version was given for this run", and opening it shows that sentence.

## The committed rehearsal run re-derived through the new code

The script read `docs/live_runs/reassess_payments_v2_1` and its prior run without writing to either, with no refine statuses (the run has none recorded).
All 21 prior findings now carry exactly one status: 16 still open, 4 partially addressed, 1 resolved.
15 of the 21 are carried forward by a finding of the run; 6 had no status and are recorded still open, not re-examined.
Those six are FND-039, FND-011, FND-012, FND-013, FND-014 and FND-053.
The rehearsal transcript counted three dropped findings; FND-013 and FND-014 are also IDs of this run (defect 2), which can hide them from a count by ID, and why FND-053 was not counted there was not checked.
Prior FND-046 is carried by two findings, FND-022 (partially addressed) and FND-046 (resolved), so the least fixed status, partially addressed, stands.
All three new findings (FND-002, FND-014, FND-041) are marked regressions, because each is anchored in a section v1.1 rewrote; the mark is per section and does not judge whether the change caused the issue.

| Prior ID | Status | This review | Re-examined |
|---|---|---|---|
| FND-001 | still_open | FND-001 | yes |
| FND-002 | still_open | FND-003 | yes |
| FND-029 | partially_addressed | FND-030 | yes |
| FND-004 | partially_addressed | FND-013 | yes |
| FND-006 | still_open | FND-006 | yes |
| FND-005 | still_open | FND-005 | yes |
| FND-020 | partially_addressed | FND-044 | yes |
| FND-016 | still_open | FND-004 | yes |
| FND-021 | still_open | FND-008 | yes |
| FND-046 | partially_addressed | FND-022, FND-046 | yes |
| FND-009 | resolved | FND-047 | yes |
| FND-022 | still_open | FND-020 | yes |
| FND-023 | still_open | FND-021 | yes |
| FND-036 | still_open | FND-031 | yes |
| FND-039 | still_open | none | no |
| FND-051 | still_open | FND-043 | yes |
| FND-011 | still_open | none | no |
| FND-012 | still_open | none | no |
| FND-013 | still_open | none | no |
| FND-014 | still_open | none | no |
| FND-053 | still_open | none | no |

## The screenshot

`docs/design/ui_mockup/for_him_ui_delta_2.png` is the Delta tab of the committed run at 1440 px, served by the real server on a free loopback port.
The committed run predates the table, so the page says so in a notice above the rows, groups the run's findings by their re-assessment with both IDs per row, and does not claim that every prior finding has a status.
The page raised no script error.

## Gates

- `ruff check agent harness tests`: exit 0.
- `pytest -q` from the repository root: exit 0, 1855 passed, 0 failed.
- `sit-review selftest`: exit 0.
- `make smoke`: exit 0.
- `make test`: exit 0.
- `pytest tests/robustness -q` (the robustness runner): exit 0, 161 passed; the results CSV was not regenerated.

## For the runbook

- A delta run's `report.json` now has `prior_findings`, one entry per finding of the previous review; count its entries against the previous report's findings to confirm nothing was dropped.
- An entry with `re_examined: false` means the model gave that prior finding no status, and the report's limitations name it; say "not re-examined", never "fixed".
- "Regressed" is not a status: a regression is a `new_in_update` finding with `regression: true`, shown as "new (regression)" on the Delta tab.
- A run with no previous version shows the Delta tab greyed out; opening it says "No previous version was given for this run".
- A delta run recorded before 2026-10-03 (such as `reassess_payments_v2_1`) shows a notice on the Delta tab that prior findings with no successor are not listed.

## For the verifier

- The rule reaches the model through the schema description of `prior_statuses` and the repair message, not through `prompts/refine.md`, because a prompt edit stops the replay of committed runs; whether a live model fills `prior_statuses` on the first answer is not verified.
- No live delta run was made, so the counts above are from the committed run re-derived by code with no refine statuses; a new live run would show how many prior findings refine re-examines.
- The regression mark compares sections by number; a renumbered section reads as changed.
- Defects 1 and 2 landed in one commit and defects 3 and 4 in another, because each pair changes the same code.
- Defect 5 of the rehearsal (stage 1 tuning for delta mode) was not in this brief and is not addressed.
