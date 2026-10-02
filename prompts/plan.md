{# prompts/plan.md - phase brief for `plan` (output: PlanOutput).
   Variables: criteria, capabilities (list of str), max_tool_calls, remaining_seconds, registry
   (list of {registry_id, doc_ref, statement}). Owner: workstream A. Placeholder content. #}
# Phase: plan the review

Decide what must be checked and what needs external research before conclusions are drawn.

## Task
- For each criterion, write the questions the review must answer about this design. Mark a question
  `needs_external` only when the document alone cannot settle it (for example a product limit, a
  standard or a regulation the design relies on).
- For each external question choose exactly one capability from: {{ capabilities | join(", ") }}
  (or `none`) and propose search queries.
- Size the plan to the budget: at most {{ max_tool_calls }} tool calls and about
  {{ remaining_seconds }} seconds remain.
- If a criterion does not apply to this design, list it under `criteria_skipped` with a reason.

## Required content rules
- Questions reference the sections they concern.
- Do not plan to reverse an approved decision; a question may test whether one still holds.
- Do not write URLs.

## Decision registry
{% for r in registry %}
- {{ r.registry_id }} ({{ r.doc_ref }}): {{ r.statement }}
{% endfor %}
