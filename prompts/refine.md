{# prompts/refine.md - phase brief for `refine` (output: RefineOutput).
   Variables: findings_json (the current drafts), registry. Owner: workstream A. Placeholder content. #}
# Phase: refine the findings

Review your own findings as a sceptical second reviewer and return the corrected full set.

## Task
- Withdraw findings the evidence does not support; merge duplicates; correct kind, category,
  severity and disposition against their definitions.
- Make every recommendation specific and bounded; keep the expected benefit tied to an objective.
- Check every finding against the decision registry and label any challenge explicitly.
- Keep "no change" findings where the design is sound; do not invent problems to fill a category.
- List each change you made with its reason.

## Required content rules
- Traceability, evidence by EV ID only, no URLs, no citation outside the evidence register.
- Do not add a new location or quote unless it is copied verbatim from the page-marked text.

## Current findings
{{ findings_json }}
