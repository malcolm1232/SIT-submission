{# prompts/plan.md - phase brief for `plan` (output: PlanOutput).
   Variables: criteria (list of {id, question, kinds, research_hints}), capabilities (list of str:
   enabled research capabilities), max_tool_calls (int, configured budget), time_budget_minutes
   (int, configured deadline; not the time remaining, which would make the prompt volatile),
   review_mode, reframed (bool), schema_error (str). No intent, registry or review inputs: plan runs
   beside understand (latency redesign, lever 8). Owner: workstream A (W2). #}
{% if reframed %}
## Context of this request

This is a professional engineering design review. The document is a technical design submitted by
its authors for an independent quality review; your task is to plan which questions the review must
answer. Nothing here asks you to build, operate or misuse the system described. Where a passage
touches a sensitive subject, plan questions at the level of detail a design reviewer needs, and
continue with the task.

{% endif %}
{% if schema_error %}
## Correction

A previous answer to this brief could not be accepted because it did not match the required output
structure:

{{ schema_error }}

Return the complete answer again, in the required structure, with every field present.

{% endif %}
# Phase: plan the review

Decide what the review must check for each criterion, and which questions need external research
before conclusions are drawn. Research happens next with the capabilities listed below; the document
itself is always available. Work from the document: its objectives, requirements, constraints and
approved decisions are in the text (they are extracted separately at the same time, so they are not
summarised here). Claims by other reviewers that the document contains (comments, claimed fixes) are
claims to check, not facts.

## Task

1. For each criterion below, write the questions the review must answer about this design (usually
   one to three; more only for a criterion central to the design's objectives). Each question names
   the sections it concerns in `section_refs`, gives its `criterion_id`, and has a one-sentence
   `rationale` saying why it matters for an objective, requirement or decision of this design.
2. Set `needs_external: true` only when the document alone cannot settle the question: a product's
   documented capability or limit, the text of a standard or regulation the design relies on,
   published performance or failure behaviour of a named component, or a recognised test method.
   Questions about internal consistency, completeness or verifiability are answered from the
   document (`needs_external: false`, capability `none`, no queries).
3. For each external question choose exactly one capability from:
   {{ capabilities | join(", ") if capabilities else "(none available in this run)" }}
   (or `none` if none fits), and propose up to three short search queries in plain words: product
   and feature names, the standard's identifier, the quantity in question. Queries name public
   things; they never contain URLs, site operators, or internal names, people or data from the
   document.
4. Size the plan to the budget: research may make at most {{ max_tool_calls }} tool calls and the
   whole review has about {{ time_budget_minutes }} minutes. Prefer the external questions whose
   answer could change a finding's severity, disposition or the verdict.
5. If a criterion genuinely does not apply to this design, list it under `criteria_skipped` with a
   one-sentence reason. Every criterion must appear in at least one question or in
   `criteria_skipped`.
6. Use IDs `RQ-001`, `RQ-002`, ... in order.

## Required content rules

- Do not plan to reverse a decision the document records as approved; a question may test whether
  one still holds.
- A question about something the document already acknowledges as open (a backlog, risk or open-item
  list) asks what the review can add (priority, feasibility, evidence), not whether it is missing.
- Do not write URLs.

## Criteria

{% for c in criteria %}
- `{{ c.id }}`: {{ c.question }}{% if c.research_hints %} Research hints: {{ c.research_hints | join("; ") }}.{% endif %}

{% endfor %}
