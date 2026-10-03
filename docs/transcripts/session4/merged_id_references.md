# Session 4: merged-ID references (2026-10-03)

Worker: a fresh Opus session, one deliverable.
Branch `s4/fixrefs`, worktree `SIT-wt/fixrefs`, from `a78d395`.
Edits, mutations and gates are in `research/audit/merged_id_references_editlog.md`.

## Commits

| Commit | Item |
|---|---|
| `e093650` | Reproduction on the fake gateway (xfail) |
| `14b57b4` | Interface change: the run's finding-ID map, the manifest field, `check_INV_12` |
| `2643e87` | The fix and INV-12 in the report gate |
| `b303859` | The gate and `check_all` tested |

Not pushed.

## The defect

Both concurrent rehearsal runs cite finding IDs in their reports that are not findings of the report.
Counted by script (below) on the committed run directories:

| Run | `report.json` dangling references | `report.md` references to no finding |
|---|---|---|
| `rehearsal_concurrent_1` | 2 (FND-003, FND-010, both in FND-012's statement) | 2 |
| `rehearsal_concurrent_high_1` | 3 (FND-002 in FND-014's statement; FND-004 and FND-013 in SA-009) | 6 (adds the decision_preservation coverage note: FND-003, FND-008, FND-011) |

## The cause

There are two causes, not one.
Each assess shard numbers its own findings `FND-001`, `FND-002`, ... and cites them by those numbers in its text.
The merge renumbers the findings in shard order and remaps the structured ID lists, but not the text, so the text of shards 2 to 4 keeps the shard's own numbers.
Refine then merges duplicates and withdraws drafts; `apply_revisions` moves only the criteria, and the refine phase remaps the structured lists of sound areas and coverage rows, but not the text.

The brief's reading of SA-009 was partly wrong, and this matters for the fix.
SA-009 came from shard 2, and its "FND-004, FND-013 and FND-014" were shard 2's own numbers for FND-018, FND-027 and FND-028 (merged into FND-034).
FND-014 was not dangling at all: it is a kept finding of the report (the design-intent strength), so it pointed at the wrong finding without any check noticing.
Remapping with refine's merge map alone would have sent FND-013 to FND-058, another wrong finding.
The decision_preservation note and FND-014's "FND-002" came from shard 1, whose numbers equal the merged ones, so those were refine merges only.

## The fix

Each step records where the IDs went, in `state.finding_ids` (`FindingIdMap`), and the text is rewritten through that record.
The assess merge records each shard's own IDs against the merged ones.
Refine records each merged ID against its kept ID, each withdrawn ID as null, and the fields it wrote itself (decision links, a next step), whose text cites merged IDs, not a shard's own.
Verify records renumbered IDs and the drafts it dropped or moved to unresolved.

Each text is read in the numbering it was written in (`finding_refs.IdChain`).
A finding's fields use its shard's numbering, and the fields refine wrote use the merged numbering.
Verify's unverified items use their draft's shard's numbering.
The verdict and code-written text use the final numbering.
A reference that ends at a finding of the report becomes that finding's ID, and a list loses its repeats ("FND-001 and FND-004", both merged into FND-004, becomes "FND-004").
A reference that ends at no finding (withdrawn, dropped by verify, unverified, or never a finding) is removed with its clause.
A parenthetical that held only references goes ("(see FND-005)"), and so does a "; see also ..." clause or a "Compare FND-005." sentence.
Otherwise the ID becomes "a finding not in this review", and a text is never emptied.
Disclosures (degradations and limitations) name drafts on purpose ("FND-030: placeholder text"), so there a non-final ID becomes "draft FND-030".
In delta mode an ID of the prior review that is no ID of this run is kept.
Verbatim document quotes, evidence excerpts and `reassessment` are never rewritten.

Why not in `apply_revisions`: it sees only the findings, not sound areas, coverage notes, the verdict or unresolved items, and it cannot know a shard's numbering.
Why not in place at the merge or in refine: refine's brief carries every field of every draft, and the verdict call's brief carries the findings' titles and statements.
Rewriting that text before those calls changes their requests, so the two recorded rehearsals would stop at the refine call on a request-hash mismatch and never replay.
So the maps are recorded where the IDs change, and the text is rewritten once, when the report is assembled after the verdict call.
Sound areas and coverage notes, which no later call reads, move to the merged IDs at the merge itself, the only place their shard is known.

The evidence ledger has no finding-ID field (there is no `supports` list in `models.LedgerEntry`), so it needs no remap.

## Where the ID map is

`run_manifest.extra.finding_ids` in `report.json` and `manifest.json`, and `finding_ids` in `state.json`.
It holds `shards` (each shard's own ID to its merged draft ID), `refine` (merged ID to kept ID, withdrawn to null), `verify`, `final` (every draft ID to the final ID it became, or null), `prior`, and `rewrites` (the counts of remapped, removed and draft-marked references).
A reader of a shard file under `shards/` follows a shard's `FND-004` through `shards.<shard name>` to its merged ID and then through `final`.

## The invariant

INV-12: every finding ID the review cites is a finding of the review.
It walks every section of `report.json` except `metadata`, `evidence_ledger` and `run_manifest`, minus a finding's own `id`, verbatim `quote` and `excerpt` passages and `reassessment`.
A disclosure may name a draft as `draft FND-nnn` when `extra.finding_ids.final` lists it, and in delta mode an ID in `extra.finding_ids.prior` is allowed.
It is in `invariants.check_all`, so the report phase refuses a report that breaks it (exit 4, `report.invalid.json`), and so do `selftest` and the robustness oracles.
The report phase also checks the coverage notes, which are in `report.md` only.
`tests/robustness/` has no `invariants.py`: its `oracles.py` and `concurrent_oracles.py` call `check_all`, so every robustness scenario now checks INV-12.

## The reproduction

`tests/test_merged_id_references.py` runs every real phase on the synthetic PDF with a scripted fake gateway.
Shard 1 and shard 2 each number their findings from FND-001, refine merges two duplicates and withdraws one draft, and verify leaves one draft unverified.
The shards' text cites their own IDs in another finding's statement, a sound area, two coverage notes and the unverified item, refine's decision link cites a merged ID, and the verdict cites one.
On the old code (the reproduction commit `e093650`, before the unverified draft joined the scenario) the run's `report.json` had four dangling references: the decision link, a statement, a sound area and the verdict.
The test stopped there; the shard 2 references in two statements, a sound area and a coverage note read as other findings by construction, since shard 2's FND-001 is the merged FND-004.
On the new code every reference ends at the intended finding or is removed, and the manifest map is checked entry by entry.

## Before and after on the rehearsal runs

Both runs were replayed through the new code with `dra replay` (all 8 recorded model calls served, every request hash matched).
The committed run directories were not touched; the replays went to `runs/` (ignored by git).

| Run | Before: `report.json` / `report.md` | After: `report.json` / `report.md` |
|---|---|---|
| `rehearsal_concurrent_1` | 2 / 2 | 0 / 0 |
| `rehearsal_concurrent_high_1` | 3 / 6 | 0 / 0 |

What changed in the text:

- Run 1, FND-012: "CVC retention (FND-003)" and "the network-token dependency (FND-010)" now cite FND-029 and FND-036, the findings they were merged into.
- High run, FND-014: "contradictions such as FND-001 and FND-002" now cites FND-001 and FND-046.
- High run, SA-009: "covered in FND-004, FND-013 and FND-014" now cites FND-018, FND-027 and FND-034; the old FND-014 was the silent wrong pointer.
- High run, decision_preservation coverage note: FND-003, FND-008 and FND-011 now cite FND-049, FND-048 and FND-026.

The script (run from the repo root with the venv's Python):

```python
import json, re, sys
from sit_review_agent.finding_refs import dangling_refs
TOK = re.compile(r"\bFND-\d{3,}\b")
for d in sys.argv[1:]:
    r = json.load(open(f"{d}/report.json"))
    final = {f["id"] for f in r["findings"]}
    md = [t for t in TOK.findall(open(f"{d}/report.md").read()) if t not in final]
    print(d, len(dangling_refs(r)), len(md))
```

## Replay

`dra replay` keeps working on both runs: it reads them, serves every recorded call, and writes the fixed report.
It then compares the replayed `report.json` with the recorded one and exits 4 with "replay diverged from the recording".
For run 1 it names one difference, `$.findings[17].statement`.
For the high run it names two, `$.findings[20].statement` and `$.sound_areas[8].why_sound`.
Those are exactly the rewritten references and nothing else; `report.md`, where the coverage note also changed, is not compared.

The rule that a record replays at its commit applies in this sense: the committed `report.json` of each run is reproduced exactly only at the commit it was recorded at (`d008a74` for run 1, `70bd658` for the high run).
At this commit the replay is not refused (config, prompts and requests are unchanged); its difference list is the evidence of the fix.

## Not verified

- No live run with the fix; the "after" counts come from replays of the recorded runs.
- The refine and verdict models still read the shards' own IDs in the findings' text, as before; the report is now right, but a model could still be misled by them.
- Changing that means rewriting the briefs, after which runs recorded before the change replay only at their commit.
- Verify's renumbering branch is not exercised end to end, because the merge never produces an invalid or repeated ID.
- Delta mode is covered by unit tests only.
- A finding that cited its own duplicate now cites itself after the merge; that is not dangling and is left as it is.
