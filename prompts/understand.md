{# prompts/understand.md - phase brief for `understand` (output: UnderstandOutput).
   Variables: criteria (list of {id, question, kinds, research_hints}), documents (list of
   {doc_id, role, title}), review_mode ("full" | "delta"), reframed (bool: professional-review
   framing after a refusal), schema_error (str: validation error of the previous answer, or "").
   Owner: workstream A. #}
{% if reframed %}
## Context of this request

This is a professional engineering design review. The document is a technical design submitted by
its authors for an independent quality review; your task is to restate its intent and list its
decisions so that the review can check it. Nothing here asks you to build, operate or misuse the
system described. Where a passage touches a sensitive subject, describe what the design states at
the level of detail a design reviewer needs, and continue with the task.

{% endif %}
{% if schema_error %}
## Correction

A previous answer to this brief could not be accepted because it did not match the required output
structure:

{{ schema_error }}

Return the complete answer again, in the required structure, with every field present.

{% endif %}
# Phase: understand the design

Explain the design intent before judging it. The rest of the review measures the design against
what you record here, so record what the document says, not what you would have designed.

## Documents

{% for d in documents %}
- `{{ d.doc_id }}` ({{ d.role }}): {{ d.title }}
{% endfor %}
{% if review_mode == "delta" %}

This is a re-review: record the intent and decisions of the document under review (the updated
version); the prior version is there for comparison only.
{% endif %}

## Task

1. `intent_summary.statement`: the design's purpose and scope in two to four sentences, in neutral
   words, as the document states them.
2. `intent_summary.objectives`, `constraints` and `key_assumptions`: one entry each, with `ref` set
   to the document's own ID when it has one (for example a goal, requirement, principle or
   assumption number) and `null` otherwise. Include design principles under objectives when the
   document treats them as goals. Do not invent IDs.
3. `intent_summary.doc_anchors`: 1 to 3 locations where the purpose and scope are stated.
4. `registry`: every entry the later review must respect, each with its document ID or heading in
   `doc_ref`, a one-sentence `statement`, and exactly one location in `doc_anchor`:
   - `approved_decision`: a decision the document marks as confirmed, approved, agreed or final;
   - `pending_decision`: a decision the document marks as proposed, open, pending or to be decided;
   - `constraint`: a binding limit the design must work within (regulatory, contractual, budget,
     platform, schedule, an existing system that must be kept);
   - `requirement`: a key requirement the objectives depend on (the material ones, not every line).
   Use the status the document gives. Keep a decision's own wording of its status; a decision that
   is "confirmed" but depends on an open item is still recorded as approved (the dependency is a
   matter for the assessment).
5. `document_version`: the version or revision label printed in the document, or `null`.
6. `review_inputs_found`: comments, review notes or claims of fixes by other people that the
   document contains (for example a change log entry saying an issue was fixed, or a reviewer's
   remark), each as one short sentence with its location. Treat them as claims to check, not as
   facts. Use an empty list if there are none.

## Required content rules

- Every location follows the traceability rule: document ID, section as printed, page from the
  nearest preceding `[[PAGE n]]` marker, requirement or decision IDs at that place, and a verbatim
  quote of at least 8 words copied exactly from the page-marked text.
- Do not judge the design yet: no findings, risks or recommendations in this phase.
- Separate what the document states as decided from what it lists as pending, open or planned, and
  from its own self-assessment (for example a risks section or a backlog).
- Do not write URLs.

## Criteria the review will apply later (for context only)

{% for c in criteria %}
- `{{ c.id }}`: {{ c.question }}
{% endfor %}
