"""``sit-review explain <run_dir> <finding_id>`` (runbook §5.1, robustness DEMO-06).

Reads only the run directory (works offline and in replay; < 5 s). Shows, for one finding:
the finding as reported; each doc anchor with page, section, quote, match method/score and
character span (``anchors.json``); each evidence item with its ledger entry and, for external
evidence, the tool call (server, tool, arguments, retrieval time, snapshot path) from
``tools.jsonl``; the criterion(s) that produced it and its history across phases with the
``llm.jsonl`` call IDs (``state.json`` ``finding_meta``); registry relations and checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExplainRecord:
    finding: dict[str, Any]                                   # the Finding as in report.json
    criteria: list[dict[str, Any]] = field(default_factory=list)          # {id, question, lab_ref}
    anchors: list[dict[str, Any]] = field(default_factory=list)           # anchors.json rows
    evidence: list[dict[str, Any]] = field(default_factory=list)          # ledger entries cited
    tool_calls: list[dict[str, Any]] = field(default_factory=list)        # tools.jsonl rows behind them
    history: list[dict[str, Any]] = field(default_factory=list)           # FindingRevision rows
    llm_calls: list[str] = field(default_factory=list)
    registry: list[dict[str, Any]] = field(default_factory=list)          # affected registry entries
    checks: list[str] = field(default_factory=list)                       # anchor status, read_before_cite, ...


def explain(run_dir: str | Path, finding_id: str) -> ExplainRecord:
    """Join ``report.json``, ``anchors.json``, ``ledger.json``, ``tools.jsonl`` and ``state.json``
    for ``finding_id``. Raises ``KeyError`` if the finding is not in the report."""
    raise NotImplementedError("phase 3: explain (workstream C)")


def format_explain(record: ExplainRecord) -> str:
    """Human-readable text in the runbook §5.1 order."""
    raise NotImplementedError("phase 3: format_explain (workstream C)")
