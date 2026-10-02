"""Review -> Markdown report (robustness §10 item 11: the model fills fields, the template owns the
structure). Template: ``agent/sit_review_agent/report/templates/report.md.j2`` (Jinja,
StrictUndefined), rendered from the Review only, so ``report.md`` can be regenerated offline
(REPRODUCIBILITY R0) and without an LLM call (fresh_eyes R-08).

Section order follows lab §2.3 (``SECTION_ORDER``). A kind with no findings still gets its
section with "None found" and the criteria that were checked (fresh_eyes §1.6). URLs appear only
as rendered from ledger entries (INV-05).
"""

from __future__ import annotations

from sit_review_agent.llm.outputs import CriterionCoverage
from sit_review_agent.models import Review, Severity

#: (section key, heading). ``kind:<k>`` sections list findings of that kind.
SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("header", "Design review"),
    ("intent", "Design intent"),
    ("verdict", "Fitness for purpose"),
    ("kind:strength", "Strengths"),
    ("kind:risk", "Risks"),
    ("kind:gap", "Gaps"),
    ("kind:ambiguity", "Ambiguities"),
    ("kind:unresolved_assumption", "Unresolved assumptions"),
    ("kind:validation_need", "Validation needs"),
    ("recommendations", "Recommended refinements"),
    ("no_change", "Areas where no change is needed"),
    ("unresolved", "Unresolved issues and next steps"),
    ("delta", "Changes since the previous version"),      # delta mode only
    ("limitations", "Evidence limitations"),
    ("evidence", "Evidence register"),
    ("coverage", "Review coverage"),
    ("run", "Run details"),
)

TEMPLATES = ("standard", "risk_register")


def render_markdown(review: Review, *, template: str = "standard", min_severity: Severity = Severity.LOW,
                    coverage: list[CriterionCoverage] | None = None) -> str:
    """Render ``review``. ``min_severity`` moves lower-severity findings to an appendix (live
    change "only report high and critical"); ``template="risk_register"`` renders findings as a
    Likelihood / Impact / Owner table (fresh_eyes §1.8)."""
    raise NotImplementedError("phase 3: render_markdown (workstream C)")
