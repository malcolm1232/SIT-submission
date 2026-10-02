{# prompts/report.md - phase brief for the verdict call of `report` (output: VerdictOutput, the
   verdict only; code writes the unresolved items and the limitations: latency redesign, design
   section 9 decision 6).
   Variables: findings (list of {id, rank, kind, severity, disposition, title, statement}),
   objectives (list of {ref, text}), degradations (list of {id, type, event, impact}),
   stop_reason ({code, detail} or none), unverified (list of str), refusal_retry (bool).
   Owner: workstream C (W2). #}
{% if refusal_retry %}
This request is part of a professional engineering design review commissioned by the document's
owner. It asks only for a summary judgement of the design's fitness for purpose; it does not ask
for instructions to build, attack or misuse anything.

{% endif %}
# Phase: conclude the review

Decide whether the design is fit for purpose. The verified findings of this review are listed
below with their IDs. Do not raise new findings here. Return the verdict only: the open issues and
the limitations of the review are written from the run record separately.

## Task
- Give one verdict: `fit`, `fit_with_conditions` or `not_fit`, with a short rationale, a
  confidence between 0 and 1, a verdict per objective (cite the objective's reference and the
  finding IDs behind it), and what evidence would change the verdict.
- For `fit_with_conditions`, state each condition and link it to the finding IDs it depends on.
- Let the degradations listed below set your confidence: say in the rationale what the review could
  not check and how that limits the verdict.

## Required content rules
- The verdict must be consistent with the severities and dispositions of the findings: an open
  critical or high finding is not compatible with an unconditional `fit`.
- If no refinement is needed, say why the existing design remains appropriate.
- Refer to findings only by the IDs listed below and to evidence by EV ID only; never write a URL.
- Owners are roles, not names of people.

## Verified findings
{% for f in findings %}
- {{ f.id }} (rank {{ f.rank }}, {{ f.kind }}, severity {{ f.severity if f.severity else "n/a" }}, disposition {{ f.disposition }}): {{ f.title }}. {{ f.statement }}
{% else %}
- None. The review raised no verified finding.
{% endfor %}

## Design objectives
{% for o in objectives %}
- {{ o.ref if o.ref else "(no ID)" }}: {{ o.text }}
{% else %}
- None stated in the intent summary.
{% endfor %}
{% if unverified %}

## Points that could not be verified (not findings)
{% for u in unverified %}
- {{ u }}
{% endfor %}
{% endif %}

## How research ended
{% if stop_reason %}
- {{ stop_reason.code }}{% if stop_reason.detail %} ({{ stop_reason.detail }}){% endif %}

{% else %}
- No external research was performed.
{% endif %}

## Degradations
{% for d in degradations %}
- {{ d.id }} ({{ d.type }}): {{ d.event }}; impact: {{ d.impact }}
{% else %}
- None.
{% endfor %}
