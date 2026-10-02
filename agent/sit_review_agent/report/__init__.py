"""Report rendering and provenance (``explain``)."""

from sit_review_agent.report.explain import ExplainRecord, explain, format_explain
from sit_review_agent.report.render import SECTION_ORDER, render_markdown

__all__ = ["SECTION_ORDER", "ExplainRecord", "explain", "format_explain", "render_markdown"]
