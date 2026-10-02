{# prompts/refine.md - phase brief for `refine` (output: RefineRevisionsOutput).
   Variables: findings_json (str: the merged draft findings as JSON), registry (list of
   {registry_id, type, doc_ref, statement}), criteria (list of {id, question, kinds,
   research_hints}), intent ({statement, objectives, constraints, key_assumptions}), answers (list
   of {question_id, criterion_id, question, status, summary, evidence_ids}), unanswered (list of
   str), evidence (list of {evidence_id, source_type, authority, title, excerpt, derived_from};
   never a URL), review_mode ("full" | "delta"), prior_findings (list of {id, title, statement,
   disposition}), reframed (bool), schema_error (str). One global call that returns one revision
   per finding, never the findings again (latency redesign, lever 9). Owner: workstream A (W2). #}
{% if reframed %}
## Context of this request

This is a professional engineering design review. The document is a technical design submitted by
its authors for an independent quality review; your task is to check the review's own findings for
accuracy. Nothing here asks you to build, operate or misuse the system described. Where a passage
touches a sensitive subject, keep the level of detail a design reviewer needs, and continue with the
task.

{% endif %}
{% if schema_error %}
## Correction

A previous answer to this brief could not be accepted:

{{ schema_error }}

Return the complete answer again: one revision for every finding, following the rules below.

{% endif %}
# Phase: refine the findings

The findings below were drafted by several reviewers working side by side, each on a group of
criteria, from the document alone. Review them together as a sceptical second reviewer who did not
write them: check each against the document, the design intent, the decision registry, the research
answers and the evidence register, and return one revision per finding. Do not rewrite the findings;
code applies your revisions to them.

## Design intent

{{ intent.statement }}
{% for o in intent.objectives %}
- Objective{% if o.ref %} {{ o.ref }}{% endif %}: {{ o.text }}
{% endfor %}
{% for c in intent.constraints %}
- Constraint{% if c.ref %} {{ c.ref }}{% endif %}: {{ c.text }}
{% endfor %}

## Decision registry (frozen)

{% for r in registry %}
- {{ r.registry_id }} [{{ r.type }}] ({{ r.doc_ref }}): {{ r.statement }}
{% else %}
- (no entries)
{% endfor %}

## Research questions and answers

{% for a in answers %}
- {{ a.question_id }} ({{ a.criterion_id }}, {{ a.status }}): {{ a.question }}{% if a.summary %} Answer: {{ a.summary }}{% endif %}{% if a.evidence_ids %} Evidence: {{ a.evidence_ids | join(", ") }}.{% endif %}

{% else %}
- (no research plan)
{% endfor %}
{% if unanswered %}
Questions research could not answer (treat their premises as unverified): {{ unanswered | join("; ") }}.
{% endif %}

## Evidence register (cite only these IDs)

{% for e in evidence %}
- {{ e.evidence_id }} [{{ e.source_type }}{% if e.authority %}, {{ e.authority }}{% endif %}]{% if e.title %} {{ e.title }}:{% endif %} {{ e.excerpt }}{% if e.derived_from %} (derived from {{ e.derived_from | join(", ") }}){% endif %}

{% else %}
- (empty)
{% endfor %}

## What to check for each finding

1. Support. Is the claim true of the document? Search the whole document (appendices, tables,
   backlog and open-item lists) before keeping a "missing" claim. Withdraw a finding the document
   or the evidence does not support, one that is generic advice rather than about this design, and
   a gap that is covered elsewhere in the document.
2. Duplicates. Findings from different reviewers may describe the same issue. Keep the stronger one
   and merge the others into it.
3. Severity and disposition. Correct them against the review standard. Severity is the impact if
   built as written. A strength has no severity and the disposition `no_change`. A question that
   needs a fact, a measurement or an owner's decision is not a `refinement_now`. Only the
   disposition itself can change here, so a new disposition must fit the fields the finding
   already has (see its JSON below):
   - `no_change` only for a finding drafted without a recommendation; a finding with a
     recommendation keeps a disposition other than `no_change`;
   - `needs_investigation`, `needs_prototyping`, `needs_testing` and `governance_decision` need a
     `next_step`: choose them only for a finding whose `next_step` is not null;
   - never a disposition already listed in the finding's `secondary_dispositions`.
   When the right disposition would need a field the finding lacks, keep the drafted disposition and
   say in `reason` what should change.
4. Decisions. Link every kept finding to each registry entry it or its recommendation touches, with
   the relation and a one-sentence justification. A `challenges` relation needs at least two
   evidence items on the finding (after any you add) and a disposition other than `no_change`;
   otherwise use `refines` or `preserves`. Do not reverse an approved decision without that
   evidence.
5. Research evidence. Where a research answer or a register entry supports or contradicts a kept
   finding, add that evidence item to the finding (`added_evidence`), citing its register ID. An
   unanswered question leaves the finding's external premise unverified: say so in `reason`, and
   keep the finding's disposition one that checks the premise (an investigation, a test or a
   validation) rather than treating the problem as confirmed.
6. Ranking. Rank the kept findings together by how much they matter to the design's objectives
   (1 = act first), whichever reviewer drafted them.
{% if review_mode == "delta" %}
7. Re-review. Each finding already carries its `reassessment` against the prior review; keep it in
   mind when you rank and when you merge.
{% for p in prior_findings %}
   - {{ p.id }} ({{ p.disposition }}): {{ p.title }}
{% endfor %}
{% endif %}

## Revision rules

Return `revisions` with exactly one revision for every finding below, by its `finding_id`, and no
other. Each revision has an `action` and a one-sentence `reason`:

- `keep`: the finding stays. Give its final `rank`, `severity` and `disposition` (the values after
  your review, also when unchanged; `severity` is `null` only for a strength), the complete list of
  `affected_decisions` (it replaces the finding's list), and in `added_evidence` the register items
  to append to the finding's evidence (none it already cites, none twice). `merge_into` is `null`.
  The ranks of the kept findings are 1, 2, 3, ... with no gaps or repeats.
- `merge`: the finding duplicates another one. `merge_into` names that finding, which must itself
  be kept (never a finding you merge or withdraw, never the finding itself). Every other field is
  `null` or empty. Only its criteria move to the kept finding; if the kept finding should cite
  evidence of the merged one, add it to the kept finding's `added_evidence`.
- `withdraw`: the finding is dropped. Every other field is `null` or empty.

A change of severity or disposition needs a `reason` (or added evidence); without one it is not
applied. Kind, title, statement, locations and recommendation cannot be changed here.

## Required content rules

- Evidence by register ID only; never write a URL or cite an external source outside the evidence
  register. `added_evidence` items cite register IDs exactly as listed above, with the passage
  relied on in `quote`.
- Do not reverse an approved decision without the evidence the decision rule requires.

## Criteria (for reference)

{% for c in criteria %}
- `{{ c.id }}`: {{ c.question }}
{% endfor %}

## Merged findings

{{ findings_json }}
