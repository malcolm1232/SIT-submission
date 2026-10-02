{# prompts/verify.md - the single anchor-repair turn in `verify` (output: AnchorRepairOutput).
   Variables: failures (list of {owner_id, anchor_index, section_ref, page, quote, reason}).
   Owner: workstream C. Sent at most once per run (ADR-007). #}
# Phase: verify quoted locations

Some quoted locations given earlier in this review could not be found in the page-marked text at
the cited page and section. Each one is listed below with the reason the check failed. This is
the only chance to correct them.

## Task
- For each failed location, find the passage of the page-marked text that states the point the
  location was meant to support, and return one repair with the same `owner_id` and
  `anchor_index`, the document ID, the section reference as printed, the page number from the
  nearest preceding `[[PAGE n]]` marker, any requirement or decision IDs at that place, and a
  verbatim quote of at least 8 words.
- If no passage in the document supports the point, leave that location out of your answer. It
  will be reported as unverified; do not substitute a passage about something else.

## Required content rules
- Copy the quote exactly from the page-marked text: no paraphrase, no corrections, no ellipses,
  and no joining of sentences that are not adjacent in the text.
- The page must be the page on which the quote appears, and the section must be the section that
  contains it (or the one next to it).
- Do not write URLs or cite sources; this step concerns the document only.

## Failed locations
{% for f in failures %}
- `{{ f.owner_id }}` anchor {{ f.anchor_index }}: cited page {{ f.page if f.page is not none else "none" }}, section "{{ f.section_ref }}" (check failed: {{ f.reason }})
  Quote given: "{{ f.quote }}"
{% endfor %}
