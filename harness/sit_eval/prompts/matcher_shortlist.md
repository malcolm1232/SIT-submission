Find the review findings that could be the same defect as this key flaw. Only the findings you return are scored against this flaw; a finding you leave out cannot match it.

<key_flaw>
{{FLAW}}
</key_flaw>

<findings order="random">
{{FINDINGS}}
</findings>

<location_hint>
Findings that cite a section or requirement id overlapping the flaw's location: {{OVERLAP_IDS}}
</location_hint>

Look at the findings named in the location hint first. The hint is not a verdict: a finding named there may describe a different defect, and a finding not named there (for example one that cites a section cross-referencing the flaw's, or cites no section) may be the right one.

Return up to {{K}} finding ids, most likely first, whose statement could state this flaw's core insight (a later step scores each one carefully). If more than {{K}} could, keep the ones that state the core insight most directly. Return an empty list if no finding is about this defect. Use only ids that appear above.
