{# prompts/report.md - phase brief for `report` (output: ReportOutput).
   Variables: findings_summary, objectives, degradations (list of {id, type, event, impact}),
   stop_reason. Owner: workstream C. Placeholder content. #}
# Phase: conclude the review

Decide whether the design is fit for purpose and state what remains open.

## Task
- Give one verdict: fit, fit_with_conditions (each condition linked to finding IDs) or not_fit,
  with a rationale, a confidence between 0 and 1, a verdict per objective, and what evidence would
  change it.
- List the unresolved issues with an owner role and next step.
- Write one limitation for each degradation below and cite its ID; say plainly what the review
  could not check and why.

## Required content rules
- The verdict is consistent with the findings' severities and dispositions.
- If no refinement is needed, say why the existing design remains appropriate.
- Evidence by EV ID only; never write a URL.

## Degradations
{% for d in degradations %}
- {{ d.id }} ({{ d.type }}): {{ d.event }}; impact: {{ d.impact }}
{% endfor %}
