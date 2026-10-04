# Refine keeps the good revisions and repairs only the failing ones, 4 Oct 2026

Worker note for branch `s4/refine-keep-good`, based on `cde5aaf` (the tip of `origin/claude/happy-darwin-d0bl94`).
Malcolm's word that covers this task: 3 Oct 2026 22:55, "fix what u need to fix", under his delegation of shot calling to the planner (3 Oct 02:50).

## The defect

In the 4 Oct rehearsal the refine phase made one call that returned 55 revisions for 55 findings.
One revision failed `revision_problems`.
The rule-repair retry in `call_model` set the whole answer aside and asked for the whole answer again.
The repair call ran into the stage limit and returned 4 revisions; those 4 were applied and 51 findings were never refined.
Research evidence is attached to findings only in refine, so none of the 41 external ledger entries reached a finding.

## Commit 1: refine keeps the good revisions (`df841bf`)

- `agent/sit_review_agent/phases/_model_calls.py`: `call_model` gains `split`, a callback given a complete answer with problems and the problems.
  When it returns `KeptItems` (the valid items, the IDs to ask again, an instruction for the correction), those items are kept, the one repair call asks only for the rest, and the call returns right after the repair call with `PhaseCall.first` (the first answer) and `PhaseCall.split` set, whatever the repair call's end: the repair answer in `result`, a cut with `partial`, a persistent refusal or a second truncation with neither.
  `check` and `ask` are not run on a repair answer that covers only part of the whole.
  With `None` from `split` the whole answer is asked again, as before.
  The prompt is untouched (a prompt edit breaks the replay of committed runs); the restriction travels in the correction text.
  The `call_retry` event of a rule repair carries `kept` and `retry` counts.
- `agent/sit_review_agent/phases/refine.py`: `split_revisions` keeps every revision that holds on its own (the salvage test, `independent_revisions`, factored out of `salvage_revisions`) and names the findings without one plus their free ranks.
  `repair_outcome` merges the kept revisions with what the repair call gave (its answer, or the finished revisions of a cut) through `salvage_revisions` as one set; a repaired revision that still fails is dropped, never applied, and its finding is unrefined (a keep of its merged values, ranked after the refined ones).
  A revision the repair gives for a kept finding is ignored, not counted as a duplicate (the prompt's fixed line still says "the complete answer").
  The disclosure (`repair_impact`) states the counts, for example "54 of 55 refine revisions (one per merged finding) were applied: 54 kept from the first answer, which broke the revision rules for 1 finding(s) (FND-030), and 0 repaired at the limit by the one repair call, which was cut by the stage limit with 0 revision(s) for them; 1 unrefined (FND-030): not refined ...".
  No degradation is recorded when every revision was applied as given.
  Each refined finding's history and `last_call_id` name the call that gave its revision (the first call for a kept one, the repair call for a repaired one).
  Prior statuses (re-review) are read from the repair answer first, then the first answer, so a repair asked for revisions only does not lose them.
  `_disclose_salvage` became `_disclose`: every degradation `call_model` recorded for this call (never a model fallback) gets the impact of what was applied.
- Tests: `tests/test_refine_keep_good.py` (9 tests, 55 findings, fake gateway): the repair brief names only the failing finding and its free rank; repair in full applies 55; repair cut with nothing applies 54 with the counts in a `budget_or_deadline_hit` degradation; repair cut after the fixed revision applies 55 ("1 repaired at the limit; 0 unrefined"); a repaired revision that still fails is dropped and listed unrefined; a kept revision's external ledger citation reaches the finding and hydrates from the ledger as external; a repair that re-sends all 55 is merged without drops; a withdrawal in the repair frees its rank (set re-ranked, all applied); an answer where nothing holds is asked again whole.
  `tests/test_llm_phases.py::test_refine_revisions_that_break_the_rules_get_one_repair_for_the_failing_ones` replaces the old whole-answer-fallback test: the keep and the withdrawal are applied, the bad merge leaves one finding unrefined.
- Mutation: with `kept = None` in place of the `split` call, 9 of the 10 tests fail (the "nothing holds" test passes, as it exercises the unchanged path); the file was restored byte for byte (`cmp`), tree clean.
- Gates after commit 1: ruff `All checks passed!`; refine, model-call, delta, truncation, budget, synthetic E2E and fault-injection tests 248 passed; `PROMPTS.lock up to date`.

## Does this fix alone let external evidence reach findings when refine ends degraded?

For the rehearsal's failure mode, yes; in general, only as far as the model cites it.
The only code path from an external ledger entry to a finding is `added_evidence` of a `keep` revision, resolved against the ledger by `resolve_evidence` after `apply_revisions` (`refine.py`).
Research answers (`QuestionAnswer`: `question_id`, `status`, `summary`, `evidence_ids`) are keyed to a plan question, which carries a `criterion_id` and no finding ID; `answer_vars` only puts them in the refine brief, and nothing in `research.py` or the state refers to a finding.
With this fix, a complete first answer whose revisions cite the ledger has those citations applied even when the repair call is cut, so the 41 entries of the rehearsal would have reached the findings their revisions cited.
It does not cover a first refine call that is itself cut (only the finished revisions carry citations; the existing salvage), the findings left unrefined, or a model that cites nothing.
A code-side link would need a key that does not exist today: a question-to-finding mapping, or a criterion-level fallback that would attach every answer's evidence to every finding of that criterion, which over-cites.
I would not add one now; if the next rehearsal shows the model leaving ledger entries uncited in a complete answer, a `check` rule ("an answered question's evidence is cited by at least one finding of its criterion") asked through the same repair is the precise lever.

## Commit 2: the shared repair path

The callers of `call_model` are `understand.py:79`, `plan.py:121`, `assess.py:301` (one call per shard, `disclose=False`) and `refine.py:485`.
Only refine passes `check`/`ask`, so only refine reaches the rule-repair retry; the other three come through the schema and transport retries, where a failed answer has no parsed items to keep.
Understand's answer is one object (intent, registry) and plan's question list is applied as a whole, so the whole-answer repair is right for them.
The assess shards' answer is a list of findings, independently applicable, but it is not rule-checked in `call_model` (findings are checked one by one later, in verify), so no repair discards them.
Commit 2 is therefore this note plus a comment at the retry saying so and that a later `check` over a list answer must also pass `split`.

## Shared lines with `s4/shard-first-answer`

Both branches edit `agent/sit_review_agent/phases/_model_calls.py`.
The one shared statement is the deadline return in `call_model` (`return PhaseCall(result=None, brief=brief, cut=True, partial=..., cut_id=exc.call_id)`): that branch adds `partial_complete=...`, this one adds `first=first, split=kept`; the merge keeps both keywords.
Both add fields to `PhaseCall` (`partial_complete` after `partial` there; `first` and `split` after `omitted` here), five lines apart, no overlap.
Nothing else overlaps: this branch does not touch `deadline_cut`, `errors.py`, `llm/partial.py`, `llm/claude_code.py` or `assess.py`.

## Not done

- A schema error on the repair call still raises out of `call_model` (existing contract, "a call already repaired once is not asked again"); with kept items that loses them. Left as is.
- A persistent refusal of the repair call still lists refine in `declined_sections` although the kept revisions are applied; the degradation's impact carries the counts.
- No re-review (delta) test of the prior-status merge across the two answers; the delta tests run end to end and were left unchanged (they pass).
- Not pushed; a verifier pushes.
