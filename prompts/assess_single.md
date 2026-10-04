{# prompts/assess_single.md - the assess brief for condition B0 (the pre-registration's tier A):
   ONE call over every criterion of the run, the whole document, the same task and output schema as
   assess.md (output: AssessOutput). Derived from assess.md; only the scope paragraph differs (no
   shard wording). Variables: criteria (list of {id, question, kinds, research_hints}: every criterion),
   documents (list of {doc_id, role, title}), review_mode ("full" | "delta"), prior_findings (list of
   {id, title, statement, disposition}; delta mode only), reframed (bool), schema_error (str). No
   intent, registry, plan answers or evidence register: nothing else runs in this condition.
   Owner: evaluation (session 6, B0). #}
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
decisions, using the document. The aim is an accurate, prioritised assessment, not a long one.

## Scope of this assessment

You are the only reviewer. This assessment covers every review criterion, listed at the end of this
brief. Work from the document alone: the design's intent and decision register have not been
extracted, and no external research is available. No later reviewer links findings to the document's
approved decisions or attaches research evidence, so leave `affected_decisions` empty and do not
wait for facts you cannot check here.
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
   operations. Cover the kinds your criteria call for where the design warrants them, including a
   `strength` for a significant area that is genuinely fit for purpose.
2. List the findings in rank order, the most important first: if your answer is cut short, the
   findings written first are the ones kept.
3. For each finding fill:
   - `id` (`FND-001`, `FND-002`, ... in rank order) and `rank` (1 = most important to act on);
   - `kind`, `category` and `severity` by the review standard (`null` category and severity for a
     strength), and `confidence` by the calibration rule;
   - `title` (a short label naming the element and the problem) and `statement` (what is wrong or
     right, where, and why it matters for which objective or requirement; two to four sentences);
   - `doc_anchors`: 1 to 3 locations, the most specific first;
   - `evidence`: the items the finding rests on. A `doc` item is a passage of the document: give it
     a new temporary ID (`NEW-1`, `NEW-2`, ... unique across your answer) and put the verbatim
     passage in `quote`. An `inference` item is your own reasoning or arithmetic in one sentence in
     `quote`, with a new temporary ID and `derived_from` listing the `NEW-` IDs it combines. Code
     adds the items to the evidence register and replaces the temporary IDs. There is no external
     evidence in this assessment. `supports_claim: false` marks evidence that cuts against the
     finding;
   - `disposition` and `secondary_dispositions`, `recommendation` (every disposition except
     `no_change`; `supporting_evidence_ids` must be a subset of the finding's evidence IDs, and
     `objective_refs` name the objectives or requirements the change serves), `no_change_rationale`
     (only for `no_change`), and `next_step` with an owner role and action (investigation,
     prototyping, testing and governance dispositions);
   - `affected_decisions`: an empty list (decisions are linked later);
   - `acknowledged_in_doc: true` when the document already lists the issue (backlog, open items,
     risks), and then say in the statement what the review adds;
   - `tags`: a few free domain words; `criterion_ids`: the criteria of this assessment that produced
     the finding;
   - `reassessment`: `null` in a full review (see above for a re-review).
4. `sound_areas`: parts of the design within your criteria that need no change, each with the
   sections, why they are sound (tied to an objective or requirement), 1 to 3 locations, any
   supporting evidence IDs (the temporary IDs used in findings) and related finding IDs.
5. `coverage`: exactly one row per criterion of this assessment: `findings` (with the finding IDs),
   `no_issue` (checked, nothing material found; say what was checked in `note`) or `not_applicable`
   (say why).

## Required content rules

- Traceability: 1 to 3 locations per finding, each with a verbatim quote of at least 8 words from
  the page-marked text, the page and the section.
- Evidence by temporary `NEW-` ID only; never write a URL or cite an external source. Do not state
  an external fact (a product limit, a clause of a standard) as true: make the finding a
  `validation_need` or `needs_investigation` and say what to check.
- A finding that challenges an approved decision of the document says so and rests on at least two
  evidence items; otherwise frame it as a risk to monitor or a refinement within the decision.
- Recommendations are specific to this design: name the section or requirement, the change, and how
  it would be verified. No generic advice.
- Severity follows impact if built as written; do not inflate low-impact items.

## Criteria of this assessment

{% for c in criteria %}
- `{{ c.id }}`: {{ c.question }}{% if c.kinds %} Usual kinds: {{ c.kinds | join(", ") }}.{% endif %}

{% endfor %}
