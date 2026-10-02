{# prompts/assess.md - phase brief for `assess` (output: AssessOutput).
   Variables: criteria (list of {id, question, kinds, research_hints}), registry (list of
   {registry_id, type, doc_ref, statement}), intent ({statement, objectives, constraints,
   key_assumptions}), answers (list of {question_id, criterion_id, question, status, summary,
   evidence_ids}), evidence (list of {evidence_id, source_type, authority, title, excerpt,
   derived_from}; never a URL), documents (list of {doc_id, role, title}), unanswered (list of str),
   review_inputs (list of str), review_mode ("full" | "delta"), prior_findings (list of {id, title,
   statement, disposition}; delta mode only), reframed (bool), schema_error (str).
   Owner: workstream A. #}
{% if reframed %}
## Context of this request

This is a professional engineering design review. The document is a technical design submitted by
its authors for an independent quality review; your task is to assess whether it is fit for its
stated purpose. Nothing here asks you to build, operate or misuse the system described. Where a
passage touches a sensitive subject, assess it at the level of detail a design reviewer needs (what
the design states, what it is missing, how it could fail), and continue with the task.

{% endif %}
{% if schema_error %}
## Correction

A previous answer to this brief could not be accepted because it did not match the required output
structure:

{{ schema_error }}

Return the complete answer again, in the required structure, with every field present.

{% endif %}
# Phase: assess the design

Judge the design against its own objectives, requirements, principles, constraints and approved
decisions, using the document and the evidence register below. The aim is an accurate, prioritised
assessment, not a long one.

## Design intent (from the understand phase)

{{ intent.statement }}
{% for o in intent.objectives %}
- Objective{% if o.ref %} {{ o.ref }}{% endif %}: {{ o.text }}
{% endfor %}
{% for c in intent.constraints %}
- Constraint{% if c.ref %} {{ c.ref }}{% endif %}: {{ c.text }}
{% endfor %}
{% for a in intent.key_assumptions %}
- Assumption{% if a.ref %} {{ a.ref }}{% endif %}: {{ a.text }}
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
- (empty: no external evidence was gathered; external claims stay unverified)
{% endfor %}
{% if review_inputs %}

## Claims by other reviewers found in the document

Check each against the document; a claimed fix that is not actually present is a finding.
{% for x in review_inputs %}
- {{ x }}
{% endfor %}
{% endif %}
{% if review_mode == "delta" %}

## Re-review of an updated document

The conversation holds the updated document (under review) and its prior version. Anchor findings in
the updated document. Give every finding a `reassessment`: `new_in_update` for an issue introduced
or first visible in the update, `still_open`, `partially_addressed` or `resolved` for a prior
finding (with `prior_finding_id`). Check that claimed fixes are real and that a fix did not
introduce a new issue.
{% for p in prior_findings %}
- {{ p.id }} ({{ p.disposition }}): {{ p.title }}. {{ p.statement }}
{% endfor %}
{% endif %}

## Task

1. Assess the design criterion by criterion. Raise a finding only for something material: it
   changes the fitness verdict, a requirement's achievability, or the risk to people, data, cost or
   operations. Cover the six kinds where the design warrants them, including at least one
   `strength` for a significant area that is genuinely fit for purpose.
2. For each finding fill:
   - `id` (`FND-001`, `FND-002`, ... in rank order) and `rank` (1 = most important to act on);
   - `kind`, `category` and `severity` by the review standard (`null` category and severity for a
     strength), and `confidence` by the calibration rule;
   - `title` (a short label naming the element and the problem) and `statement` (what is wrong or
     right, where, and why it matters for which objective or requirement; two to four sentences);
   - `doc_anchors`: 1 to 3 locations, the most specific first;
   - `evidence`: the items the finding rests on. `external` items cite register IDs only. A `doc`
     item is a passage of the document: cite its register ID if it is already in the register,
     otherwise give it a new temporary ID (`NEW-1`, `NEW-2`, ... unique across your answer) and put
     the verbatim passage in `quote`. An `inference` item is your own reasoning or arithmetic in one
     sentence in `quote`, with a new temporary ID and `derived_from` listing the register or `NEW-`
     IDs it combines. Code adds the new items to the register and replaces the temporary IDs.
     `supports_claim: false` marks evidence that cuts against the finding;
   - `disposition` and `secondary_dispositions`, `recommendation` (every disposition except
     `no_change`; `supporting_evidence_ids` must be a subset of the finding's evidence IDs, and
     `objective_refs` name the objectives or requirements the change serves), `no_change_rationale`
     (only for `no_change`), and `next_step` with an owner role and action (investigation,
     prototyping, testing and governance dispositions);
   - `affected_decisions`: every registry entry the finding or its recommendation touches, with the
     relation and a one-sentence justification;
   - `acknowledged_in_doc: true` when the document already lists the issue (backlog, open items,
     risks), and then say in the statement what the review adds;
   - `tags`: a few free domain words; `criterion_ids`: the criteria that produced the finding;
   - `reassessment`: `null` in a full review (see above for a re-review).
3. `sound_areas`: parts of the design that need no change, each with the sections, why they are
   sound (tied to an objective or requirement), 1 to 3 locations, any supporting evidence IDs
   (register IDs or the temporary IDs used in findings) and related finding IDs.
4. `coverage`: exactly one row per criterion: `findings` (with the finding IDs), `no_issue`
   (checked, nothing material found; say what was checked in `note`) or `not_applicable` (say why).

## Required content rules

- Traceability: 1 to 3 locations per finding, each with a verbatim quote of at least 8 words from
  the page-marked text, the page and the section.
- Evidence by EV ID only (plus temporary `NEW-` IDs for new document passages and inferences);
  never write a URL or cite an external source that is not in the register. Do not state an
  external fact (a product limit, a clause of a standard) as true unless the register supports it;
  otherwise make the finding a `validation_need` or `needs_investigation` and say what to check.
- A finding that challenges an approved decision says so and rests on at least two evidence items;
  otherwise frame it as a risk to monitor or a refinement within the decision.
- Recommendations are specific to this design: name the section or requirement, the change, and how
  it would be verified. No generic advice.
- Severity follows impact if built as written; do not inflate low-impact items.

## Criteria

{% for c in criteria %}
- `{{ c.id }}`: {{ c.question }}{% if c.kinds %} Usual kinds: {{ c.kinds | join(", ") }}.{% endif %}

{% endfor %}
