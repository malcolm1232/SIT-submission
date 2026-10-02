{# prompts/understand.md - phase brief for `understand` (output: UnderstandOutput).
   Variables: criteria (list of {id, question}). Owner: workstream A. Placeholder content. #}
# Phase: understand the design

Explain the design intent before judging it.

## Task
- Summarise the design's purpose and scope in a few sentences.
- List its objectives, constraints and key assumptions, each with the document's own ID when it has one.
- Extract the decision registry: every approved decision, pending decision, binding constraint and
  key requirement, each with its document ID, a one-sentence statement and one location.
- Note any review comments or claims of fixes from other reviewers that the document contains; treat
  them as claims to check, not as facts.

## Required content rules
- Every location follows the traceability rule (section, page, IDs, verbatim quote of at least 8 words).
- Do not judge the design yet; no findings in this phase.
- Do not write URLs.

## Criteria the review will apply
{% for c in criteria %}
- `{{ c.id }}`: {{ c.question }}
{% endfor %}
