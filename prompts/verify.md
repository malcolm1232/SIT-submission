{# prompts/verify.md - anchor-repair turn in `verify` (output: AnchorRepairOutput).
   Variables: failures (list of {owner_id, anchor_index, section_ref, page, quote, reason}).
   Owner: workstream C. Placeholder content. #}
# Phase: verify locations

Some quoted locations could not be found in the page-marked text. Re-quote each from the cited
section.

## Task
- For each failed location below, copy a verbatim passage of at least 8 words from the
  page-marked text that supports the same point, and give its page and section.
- If no passage in the document supports the point, say so by returning the location unchanged;
  the finding will be reported as unverified.

## Required content rules
- Copy text exactly; do not paraphrase, correct or join non-adjacent sentences.
- Do not write URLs.

## Failed locations
{% for f in failures %}
- {{ f.owner_id }} #{{ f.anchor_index }} (p{{ f.page }}, s{{ f.section_ref }}, {{ f.reason }}): "{{ f.quote }}"
{% endfor %}
