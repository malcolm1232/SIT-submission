"""Turning tool results into evidence-ledger entries.

Each MCP server returns results in its own shape (search hits, scholarly records, page text).
:func:`extract_sources` normalises one :class:`~sit_review_agent.tools.gateway.ToolResult` into
:class:`ExternalSource` items; the research phase writes one ledger entry per item
(:meth:`~sit_review_agent.state.evidence_ledger.EvidenceLedger.add_external`) and shows the model
the result text prefixed with the new ``EV-nnn`` IDs, so the model can only cite what it has seen.
"""

from __future__ import annotations

from dataclasses import dataclass

from sit_review_agent.models import SourceAuthority
from sit_review_agent.tools.gateway import ToolResult


@dataclass(frozen=True)
class ExternalSource:
    url_or_citation: str
    title: str | None
    excerpt: str                        # the snippet as the agent saw it
    content: str                        # full fetched content if read, else the excerpt
    authority: SourceAuthority
    read_in_full: bool                  # -> LedgerEntry.read_before_cite


def extract_sources(result: ToolResult) -> list[ExternalSource]:
    """Server-specific parsing of search hits / records / fetched pages (UNVERIFIED shapes until
    the laptop probe records real results). Authority is classified by domain heuristics."""
    raise NotImplementedError("phase 2: extract_sources (workstream B)")


def classify_authority(url: str) -> SourceAuthority:
    """Domain heuristics: standards bodies, regulators, official vendor docs -> primary_official;
    DOI / journals -> peer_reviewed; known reference sites -> secondary; else informal."""
    raise NotImplementedError("phase 2: classify_authority (workstream B)")
