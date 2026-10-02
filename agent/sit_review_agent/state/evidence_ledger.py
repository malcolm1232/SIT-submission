"""Evidence ledger (robustness §10 item 3, ADR-007): append-only, stable ``EV-nnn`` IDs.

* External entries are created only from an ``ok`` tool call of this run and carry its
  ``call_id`` (INV-05: every external citation resolves to a real or replayed tool call).
* Doc entries cite the canonical text (``doc:<doc_id>#p<page>/s<section>``); inference entries
  list what they are ``derived_from`` (every ID must already be in the ledger).
* The model cites entries by ID only; :meth:`EvidenceLedger.hydrate` copies ``url_or_citation``
  and ``retrieved_at`` into the finding. Nothing is ever updated or deleted.
* Every entry is appended to ``ledger.jsonl`` (flushed per entry; the resume journal, ADR-009);
  ``ledger.json`` is the array snapshot the report phase writes.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sit_review_agent.clock import Clock, SystemClock, isoformat_z
from sit_review_agent.errors import LedgerError
from sit_review_agent.hashing import sha256_text
from sit_review_agent.llm.outputs import EvidenceCitation
from sit_review_agent.models import EvidenceItem, LedgerEntry, LedgerToolRef, SourceType, evidence_id
from sit_review_agent.rundir import JsonlWriter, RunDir, write_json_atomic
from sit_review_agent.tools.gateway import ToolResult
from sit_review_agent.tools.sources import ExternalSource


class EvidenceLedger:
    def __init__(self, run_dir: RunDir | None = None, *, clock: Clock | None = None) -> None:
        self.run_dir = run_dir
        self.clock = clock or SystemClock()
        self._entries: dict[str, LedgerEntry] = {}
        self._journal = JsonlWriter(run_dir.ledger_journal) if run_dir is not None else None

    # ------------------------------------------------------------------ read
    def __contains__(self, eid: object) -> bool:
        return eid in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[LedgerEntry]:
        return iter(self._entries.values())

    def get(self, eid: str) -> LedgerEntry:
        try:
            return self._entries[eid]
        except KeyError:
            raise LedgerError(f"unknown evidence ID {eid}") from None

    def entries(self) -> list[LedgerEntry]:
        return list(self._entries.values())

    def by_call(self, call_id: str) -> list[LedgerEntry]:
        return [e for e in self._entries.values() if e.tool is not None and e.tool.call_id == call_id]

    def offset(self) -> int:
        return self._journal.offset() if self._journal is not None else 0

    # ------------------------------------------------------------------ append
    def _next_id(self) -> str:
        return evidence_id(len(self._entries) + 1)

    def _append(self, entry: LedgerEntry) -> LedgerEntry:
        if entry.evidence_id in self._entries:
            raise LedgerError(f"duplicate evidence ID {entry.evidence_id}")
        self._entries[entry.evidence_id] = entry
        if self._journal is not None:
            self._journal.append(entry.model_dump(mode="json"))
        return entry

    def add_external(self, result: ToolResult, source: ExternalSource, *,
                     snapshot_path: str | None = None) -> LedgerEntry:
        """One external source seen in an ``ok`` tool result (search hit, record, fetched page)."""
        if not result.ok:
            raise LedgerError(f"external evidence needs an ok tool call; {result.call_id} is {result.status}")
        return self._append(LedgerEntry(
            evidence_id=self._next_id(), source_type=SourceType.EXTERNAL, authority=source.authority,
            tool=LedgerToolRef(server=result.server, tool_name=result.tool_name, call_id=result.call_id),
            url_or_citation=source.url_or_citation, title=source.title, retrieved_at=result.started_at,
            content_sha256=sha256_text(source.content), snapshot_path=snapshot_path, excerpt=source.excerpt,
            read_before_cite=source.read_in_full, derived_from=[]))

    def add_doc(self, *, doc_id: str, page: int | None, section_ref: str, excerpt: str) -> LedgerEntry:
        """A passage of the document under review (verbatim from the canonical text)."""
        loc = f"doc:{doc_id}#p{page}/s{section_ref}" if page is not None else f"doc:{doc_id}#s{section_ref}"
        return self._append(LedgerEntry(
            evidence_id=self._next_id(), source_type=SourceType.DOC, authority=None, tool=None,
            url_or_citation=loc, title=None, retrieved_at=None, content_sha256=None, snapshot_path=None,
            excerpt=excerpt, read_before_cite=True, derived_from=[]))

    def add_inference(self, *, statement: str, derived_from: list[str]) -> LedgerEntry:
        """The agent's own reasoning or arithmetic over existing entries."""
        missing = [d for d in derived_from if d not in self._entries]
        if not derived_from or missing:
            raise LedgerError(f"inference must derive from existing entries; missing {missing or 'all'}")
        eid = self._next_id()
        return self._append(LedgerEntry(
            evidence_id=eid, source_type=SourceType.INFERENCE, authority=None, tool=None,
            url_or_citation=f"inference:{eid}", title=None, retrieved_at=None, content_sha256=None,
            snapshot_path=None, excerpt=statement, read_before_cite=True, derived_from=list(derived_from)))

    # ------------------------------------------------------------------ hydrate / persist
    def hydrate(self, c: EvidenceCitation) -> EvidenceItem:
        """Canonical evidence item for a model citation; ``url_or_citation`` and ``retrieved_at``
        come from the ledger. Raises :class:`LedgerError` for an unknown ID or a source-type mismatch."""
        e = self.get(c.evidence_id)
        if e.source_type is not c.source_type:
            raise LedgerError(f"{c.evidence_id} is {e.source_type}, cited as {c.source_type}")
        return EvidenceItem(evidence_id=e.evidence_id, source_type=e.source_type, url_or_citation=e.url_or_citation,
                            quote=c.quote, supports_claim=c.supports_claim, retrieved_at=e.retrieved_at,
                            derived_from=list(e.derived_from) if e.source_type is SourceType.INFERENCE else [])

    def snapshot(self) -> list[dict[str, Any]]:
        return [e.model_dump(mode="json") for e in self._entries.values()]

    def write_snapshot(self) -> None:
        if self.run_dir is None:
            raise LedgerError("ledger has no run directory")
        write_json_atomic(self.run_dir.ledger, self.snapshot())

    @classmethod
    def load(cls, run_dir: RunDir, *, upto: int | None = None, clock: Clock | None = None) -> EvidenceLedger:
        """Rebuild from ``ledger.jsonl`` (entries up to byte offset ``upto``; resume)."""
        led = cls(None, clock=clock)
        for raw in JsonlWriter(run_dir.ledger_journal).read(upto):
            e = LedgerEntry.model_validate(raw)
            led._entries[e.evidence_id] = e
        led.run_dir = run_dir
        led._journal = JsonlWriter(run_dir.ledger_journal)
        return led

    def now(self) -> str:
        return isoformat_z(self.clock.now_utc())
