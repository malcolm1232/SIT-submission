"""Run-directory layout (docs/REPRODUCIBILITY.md §6) and the append-only JSONL journal (ADR-009).

``runs/<run_id>/``::

    manifest.json            written before the first model call, finalised at exit
    effective_config.json    merged config after CLI flags (hash = effective_config_sha256)
    llm.jsonl                every model call (LLMGateway)
    tools.jsonl              every tool call (ToolGateway), incl. cassette key
    ledger.jsonl             evidence-ledger journal, one LedgerEntry per line (append-only)
    ledger.json              ledger snapshot (JSON array), written by the report phase
    snapshots/               stored copy of every fetched page (EV-nnn.<ext>)
    text/<doc_id>.pages.txt  canonical page-marked text, one per document (ADR-006)
    text/<doc_id>.sections.json
    anchors.json             anchor table: finding/anchor -> AnchorResult (ADR-007)
    state.json               latest RunState (convenience copy of the last checkpoint's state)
    checkpoints/NN-<phase>.json
    progress.log             every progress line printed to the console
    report.json, report.md   the Review and its rendering
    failure.json             structured failure record when no report can be produced (INV-02)

``text/<doc_id>.pages.txt`` replaces the single ``doc.pages.txt`` of ADR-006 so that delta mode
(two documents) has one canonical text per document; ``DocumentMeta.text_path`` points at it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunDir:
    root: Path

    @property
    def run_id(self) -> str:
        return self.root.name

    def create(self) -> RunDir:
        for d in (self.root, self.snapshots, self.text_dir, self.checkpoints):
            d.mkdir(parents=True, exist_ok=True)
        return self

    # files
    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def effective_config(self) -> Path:
        return self.root / "effective_config.json"

    @property
    def llm_log(self) -> Path:
        return self.root / "llm.jsonl"

    @property
    def tools_log(self) -> Path:
        return self.root / "tools.jsonl"

    @property
    def ledger_journal(self) -> Path:
        return self.root / "ledger.jsonl"

    @property
    def ledger(self) -> Path:
        return self.root / "ledger.json"

    @property
    def anchors(self) -> Path:
        return self.root / "anchors.json"

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def progress_log(self) -> Path:
        return self.root / "progress.log"

    @property
    def report_json(self) -> Path:
        return self.root / "report.json"

    @property
    def report_md(self) -> Path:
        return self.root / "report.md"

    @property
    def failure(self) -> Path:
        return self.root / "failure.json"

    # directories
    @property
    def snapshots(self) -> Path:
        return self.root / "snapshots"

    @property
    def text_dir(self) -> Path:
        return self.root / "text"

    @property
    def checkpoints(self) -> Path:
        return self.root / "checkpoints"

    def doc_text(self, doc_id: str) -> Path:
        return self.text_dir / f"{doc_id}.pages.txt"

    def doc_sections(self, doc_id: str) -> Path:
        return self.text_dir / f"{doc_id}.sections.json"

    def relative(self, path: Path) -> str:
        """Run-relative path for ``DocumentMeta.text_path`` and ``snapshot_path``."""
        return str(path.relative_to(self.root))


class JsonlWriter:
    """Append-only JSONL journal: one JSON object per line, flushed and fsynced per entry.

    :meth:`append` returns the byte offset *after* the entry, which checkpoints record
    (ADR-009 item 1) so a resume knows which entries belong to completed stages.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, obj: dict[str, Any]) -> int:
        line = json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n"
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
            return fh.tell()

    def offset(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0

    def read(self, upto: int | None = None) -> list[dict[str, Any]]:
        """Entries in file order, optionally only those that end at or before byte ``upto``."""
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        pos = 0
        with open(self.path, "rb") as fh:
            for raw in fh:
                pos += len(raw)
                if upto is not None and pos > upto:
                    break
                if raw.strip():
                    out.append(json.loads(raw))
        return out


def write_json_atomic(path: Path, obj: Any) -> None:
    """Write JSON atomically: temp file in the same directory, fsync, ``os.replace`` (ADR-009)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
