"""Decision and constraint registry (robustness §10 item 5, INV-10, BEH-12).

Extracted once in ``understand`` from the document (approved and pending decisions, constraints,
key requirements), then :meth:`DecisionRegistry.freeze`\\ d and injected into every later prompt.
Its hash must be identical at the end of every iteration. A finding that touches an entry declares
it in ``affected_decisions`` (``preserves | refines | challenges``); ``challenges`` needs >= 2
evidence items and a disposition other than ``no_change``.
"""

from __future__ import annotations

from collections.abc import Iterable

from sit_review_agent.errors import RegistryFrozenError
from sit_review_agent.hashing import registry_sha256
from sit_review_agent.llm.outputs import FindingDraft, RegistryEntryDraft
from sit_review_agent.models import (
    DecisionRelation,
    Disposition,
    DocAnchor,
    RegistryEntry,
    RegistryEntryType,
    RegistryHash,
    registry_id,
)


class DecisionRegistry:
    def __init__(self, entries: Iterable[RegistryEntry] = (), *, frozen: bool = False) -> None:
        self._entries: list[RegistryEntry] = list(entries)
        self._frozen = frozen
        self._hashes: list[RegistryHash] = []

    @property
    def frozen(self) -> bool:
        return self._frozen

    def entries(self) -> list[RegistryEntry]:
        return list(self._entries)

    def ids(self) -> set[str]:
        return {e.registry_id for e in self._entries}

    def get(self, rid: str) -> RegistryEntry:
        for e in self._entries:
            if e.registry_id == rid:
                return e
        raise KeyError(rid)

    def approved(self) -> list[RegistryEntry]:
        return [e for e in self._entries if e.type is RegistryEntryType.APPROVED_DECISION]

    def add(self, draft: RegistryEntryDraft) -> RegistryEntry:
        """Add one entry from the ``understand`` output; assigns ``AD-nnn``. Raises once frozen.
        The anchor is validated against the spec here; its quote is verified by the verify phase."""
        if self._frozen:
            raise RegistryFrozenError("decision registry is frozen after understand (INV-10)")
        entry = RegistryEntry(registry_id=registry_id(len(self._entries) + 1), type=draft.type, doc_ref=draft.doc_ref,
                              statement=draft.statement,
                              doc_anchor=DocAnchor.model_validate(draft.doc_anchor.model_dump()))
        self._entries.append(entry)
        return entry

    def freeze(self) -> str:
        """Freeze the registry; returns its hash."""
        self._frozen = True
        return self.sha256()

    def sha256(self) -> str:
        return registry_sha256([e.model_dump(mode="json") for e in self._entries])

    def record_iteration(self, iteration: int) -> RegistryHash:
        """Append ``{iteration, sha256}`` for ``research_log.registry_sha256_by_iteration``."""
        h = RegistryHash(iteration=iteration, sha256=self.sha256())
        self._hashes.append(h)
        return h

    def hashes(self) -> list[RegistryHash]:
        return list(self._hashes)

    def check_finding(self, f: FindingDraft) -> list[str]:
        """Code-checkable INV-10 rules for one finding: referenced IDs exist; ``challenges`` has
        >= 2 evidence items and is not ``no_change``. Undeclared conflicts need a judge (L1)."""
        out: list[str] = []
        for ad in f.affected_decisions:
            if ad.registry_id not in self.ids():
                out.append(f"{f.id}: affected decision {ad.registry_id} not in registry")
            if ad.relation is DecisionRelation.CHALLENGES:
                if len(f.evidence) < 2:
                    out.append(f"{f.id}: challenges {ad.registry_id} with < 2 evidence items")
                if f.disposition is Disposition.NO_CHANGE:
                    out.append(f"{f.id}: challenges {ad.registry_id} but disposition is no_change")
        return out
