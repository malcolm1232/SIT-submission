{# prompts/refine.md - phase brief for `refine` (output: RefineOutput).
   Variables: findings_json (str: the current drafts as JSON), registry (list of {registry_id, type,
   doc_ref, statement}), criteria (list of {id, question, kinds, research_hints}), intent
   ({statement, objectives, constraints, key_assumptions}), evidence (list of {evidence_id,
   source_type, authority, title, excerpt, derived_from}; never a URL), review_mode ("full" |
   "delta"), prior_findings (list of {id, title, statement, disposition}), reframed (bool),
   schema_error (str). Owner: workstream A. #}
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

A previous answer to this brief could not be accepted because it did not match the required output
structure:

{{ schema_error }}

Return the complete answer again, in the required structure, with every field present.

{% endif %}
# Phase: refine the findings

Review the findings below as a sceptical second reviewer who did not write them, check each against
the document and the evidence register, and return the corrected full set.

## Design intent

{{ intent.statement }}
{% for o in intent.objectives %}
- Objective{% if o.ref %} {{ o.ref }}{% endif %}: {{ o.text }}
{% endfor %}

## Decision registry (frozen)

{% for r in registry %}
- {{ r.registry_id }} [{{ r.type }}] ({{ r.doc_ref }}): {{ r.statement }}
{% else %}
- (no entries)
{% endfor %}

## Evidence register (cite only these IDs)

{% for e in evidence %}
- {{ e.evidence_id }} [{{ e.source_type }}{% if e.authority %}, {{ e.authority }}{% endif %}]{% if e.title %} {{ e.title }}:{% endif %} {{ e.excerpt }}{% if e.derived_from %} (derived from {{ e.derived_from | join(", ") }}){% endif %}

{% else %}
- (empty)
{% endfor %}

## Task

For each finding, check and correct:

1. Support. Is the claim true of the document? Search the whole document (appendices, tables,
   backlog and open-item lists) before keeping a "missing" claim; a gap that is covered elsewhere is
   withdrawn, and one the document already acknowledges gets `acknowledged_in_doc: true` and a
   statement of what the review adds. Withdraw findings the document or the evidence does not
   support, and findings that are generic advice rather than about this design.
2. Duplicates. Merge findings that describe the same issue: keep the stronger one (its ID), fold the
   other's locations and evidence into it (at most 3 locations), and withdraw the other.
3. Labels. Correct `kind`, `category`, `severity` and `disposition` against the review standard.
   A strength has no category, no severity, disposition `no_change` and no recommendation. Severity
   is the impact if built as written. A question that needs a fact, a measurement or an owner's
   decision is not a `refinement_now`.
4. Recommendations. Each has the issue, the rationale, supporting evidence IDs that are among the
   finding's evidence, the expected benefit tied to a named objective or requirement, and a change
   that names where in the document it applies and how it would be verified. Make vague ones
   specific and bounded; remove recommendations from `no_change` findings.
5. Locations and quotes. Each location's quote must be copied verbatim from the page-marked text,
   at least 8 words, with the right page and section. Fix or replace a location only by copying text
   from the page-marked text.
6. Decisions. Every finding that touches a registry entry lists it in `affected_decisions`; a
   `challenges` relation needs at least two evidence items and a disposition other than
   `no_change`, otherwise reduce it to `refines` or `preserves` and adjust the statement.
7. Confidence. Re-check it against the calibration rule.
8. Ranking. Rank the remaining findings by how much they matter to the design's objectives
   (1 = act first), and keep at least one well-founded `strength` or `no_change` judgement where the
   design is sound. Do not invent problems to fill a kind.
{% if review_mode == "delta" %}
9. Re-review. Every finding needs a `reassessment` (`new_in_update`, `still_open`,
   `partially_addressed` or `resolved`, with `prior_finding_id` except for new issues).
{% for p in prior_findings %}
   - {{ p.id }} ({{ p.disposition }}): {{ p.title }}
{% endfor %}
{% endif %}

Return in `findings` the complete corrected set (unchanged findings too, with their IDs). Keep the ID
of every finding you keep; give a new finding the next unused `FND-` number. In `revisions`, list one
entry per finding you revised, merged, withdrew or added (`change` = `revised`, `merged`,
`withdrawn`, `added` or `unchanged`) with a one-sentence reason and the evidence IDs behind the
change. New document passages and inferences get temporary IDs `NEW-1`, `NEW-2`, ... as in the
assessment.

## Required content rules

- Traceability, evidence by EV ID only, no URLs, no citation of an external source outside the
  evidence register.
- Do not add a new location or quote unless it is copied verbatim from the page-marked text.
- Do not reverse an approved decision without the evidence the decision rule requires.

## Criteria (IDs for `criterion_ids`)

{% for c in criteria %}
- `{{ c.id }}`: {{ c.question }}
{% endfor %}

## Current findings

{{ findings_json }}
