{# prompts/assess.md - phase brief for `assess` (output: AssessOutput).
   Variables: criteria, registry, answers (list of {question_id, status, summary, evidence_ids}),
   evidence (list of {evidence_id, source_type, excerpt}). Owner: workstream A. Placeholder content. #}
# Phase: assess the design

Judge the design against its objectives, using the document and the evidence register.

## Task
- Raise findings of six kinds: strength, risk, gap, ambiguity, unresolved_assumption,
  validation_need. Give each a defect category (none for strengths), a severity (none for
  strengths), a confidence between 0 and 1, and the criteria that produced it.
- Choose one primary disposition: refinement_now, needs_investigation, needs_prototyping,
  needs_testing, governance_decision, or no_change. Refinements carry a recommendation with the
  issue, rationale, supporting evidence IDs, expected benefit tied to an objective, and the change.
  Investigation, prototyping, testing and governance dispositions also name an owner role and the
  next action.
- `no_change` is allowed and expected where the design is sound: give the reason the existing
  design remains appropriate and no recommendation.
- Mark findings the document already acknowledges (open items, backlog) as acknowledged.
- Record sound areas, and for every criterion whether it produced findings, was checked with no
  issue, or did not apply.

## Required content rules
- Traceability: 1 to 3 locations per finding, each with a verbatim quote of at least 8 words from
  the page-marked text, the page and the section.
- Evidence by EV ID only; never write a URL or cite anything not in the register.
- A finding that challenges an approved decision says so and rests on at least two evidence items.
- Recommendations are specific to this design (name the section or requirement and the change).

## Criteria
{% for c in criteria %}
- `{{ c.id }}`: {{ c.question }}
{% endfor %}
