"""Finding-ID references in review text (merged-ID traceability, 2026-10-03).

An assess shard numbers its own findings ``FND-001..`` and cites them in its text (another finding's
statement, a sound area, a coverage note). The merge renumbers the findings in shard order, refine
merges duplicates into kept findings and withdraws others, and verify drops what it cannot keep.
The structured ID lists followed each step; the text did not, so both concurrent rehearsal runs
cited IDs in their reports that were no finding, or another finding than the one meant
(``docs/transcripts/session4/merged_id_references.md``).

Each step records its map in ``state.finding_ids`` (:class:`~sit_review_agent.state.run_state.FindingIdMap`)
and the text is rewritten through it. Text is read in the numbering it was written in:

* **shard**: what an assess shard wrote (its findings' fields, sound areas, coverage notes, and the
  statement of an item verify moved to unresolved): the shard's own IDs, then the draft chain below;
* **draft**: what refine wrote (decision links, a next step) and what was already moved to draft IDs:
  refine's map (merged ID to kept ID, withdrawn to removed), then verify's (renumbered, dropped);
* **final**: what the verdict call and code wrote after verify: the final IDs only.

A reference that ends at a finding of the report becomes that ID (a list of IDs loses repeats). A
reference that ends at no finding (withdrawn, dropped, unverified, or never a finding) is removed with
its clause: a parenthetical or a "see ..." clause that held only references goes, otherwise the ID
becomes "a finding not in this review". Disclosures (``research_log.degradations``, ``limitations``)
name drafts on purpose ("FND-030: placeholder text"); there a non-final ID becomes "draft FND-030",
which ``extra.finding_ids.final`` resolves. In delta mode an ID of the prior review that is no ID of
this run is kept: it cites the prior review.

Never rewritten nor checked (:data:`SKIP_KEYS`, :data:`SKIP_SECTIONS`): a finding's own ``id``,
verbatim passages (``quote``, ``excerpt``: document text and recorded evidence, append-only in the
ledger), ``reassessment`` (the prior review's numbering), and the ``metadata``, ``evidence_ledger``,
``run_manifest`` and ``prior_findings`` (the delta table, keyed on the prior review's IDs) sections.
INV-12 (:func:`~sit_review_agent.invariants.check_INV_12`) checks the result with :func:`iter_refs`,
which walks the review with the same rules.

Model briefs are never rewritten: refine reads the drafts and the verdict call reads the findings'
titles and statements as the shards wrote them, so a recorded run replays with the same requests.
Sound areas and coverage notes, which no later call reads, move to draft IDs at the merge (the only
place their shard is known); everything else is rewritten once, when the report is assembled.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sit_review_agent.state.run_state import FindingIdMap

#: A finding ID token.
FINDING_REF = re.compile(r"\bFND-\d{3,}\b")
#: The marker of a draft ID named in a disclosure.
DRAFT_PREFIX = "draft "
#: Keys whose values are never rewritten nor checked (see the module docstring).
SKIP_KEYS = frozenset({"id", "quote", "excerpt", "reassessment"})
#: Review sections never rewritten nor checked.
#: ``prior_findings`` (the delta table) is keyed on the prior review's IDs and its notes are in that
#: numbering; its current IDs are checked against the findings by ``models.Review`` instead.
SKIP_SECTIONS = frozenset({"metadata", "evidence_ledger", "run_manifest", "prior_findings"})
#: Keys holding a list of finding IDs.
ID_LIST_KEYS = frozenset({"finding_ids", "related_finding_ids"})
#: The words that replace a removed reference that cannot go with its clause.
GONE_ONE = "a finding not in this review"
GONE_MANY = "findings not in this review"

_ID = r"FND-\d{3,}"
_JOIN = r"(?:\s*,\s*(?:and|or)\s+|\s*,\s*|\s+(?:and|or)\s+|\s*/\s*)"
_RUN = re.compile(rf"\b{_ID}(?:{_JOIN}{_ID})*\b")
_LEAD = (r"(?:see also|see|also see|compare|cf\.|e\.g\.,?|i\.e\.,?|as in|also|per|via|in|by|covered in|"
         r"covered by|raised in|raised by|related to|related:?|duplicates?|same as)")
_PAREN_OPEN = re.compile(rf"\s*\(\s*(?:{_LEAD}\s+)?$", re.IGNORECASE)
_PAREN_CLOSE = re.compile(r"^\s*\)")
_SENTENCE_OPEN = re.compile(rf"(?:^|(?<=[.!?])\s+)\s*{_LEAD}\s+$", re.IGNORECASE)
_SENTENCE_CLOSE = re.compile(r"^\s*(?:[.!?;]|$)")
_CLAUSE_OPEN = re.compile(rf"\s*[;,]\s*{_LEAD}\s+$", re.IGNORECASE)
_CLAUSE_CLOSE = re.compile(r"^\s*(?:[.!?;)]|$)")
_SENTENCE_START = re.compile(r"(?:^|[.!?]\s+)$")

Resolver = Callable[[str], str | None]


@dataclass
class RewriteStats:
    """What a rewrite changed: references moved to another ID, removed, or marked as drafts."""

    remapped: int = 0
    removed: int = 0
    marked_draft: int = 0

    def add(self, other: RewriteStats) -> None:
        self.remapped += other.remapped
        self.removed += other.removed
        self.marked_draft += other.marked_draft

    def as_dict(self) -> dict[str, int]:
        return {"remapped": self.remapped, "removed": self.removed, "marked_draft": self.marked_draft}


def _join(ids: Sequence[str], run: str) -> str:
    conj = " or " if re.search(r"\bor\b", run) else " and " if re.search(r"\band\b", run) else None
    if conj is None:
        return ("/" if "/" in run and "," not in run else ", ").join(ids)
    if len(ids) == 1:
        return ids[0]
    return ", ".join(ids[:-1]) + conj + ids[-1]


def _removal(text: str, start: int, end: int, n_removed: int) -> tuple[int, int, str]:
    """The span to replace and its replacement when every ID of the run ``text[start:end]`` is gone."""
    before, after = text[:start], text[end:]
    m, c = _PAREN_OPEN.search(before), _PAREN_CLOSE.match(after)
    if m and c:
        return m.start(), end + c.end(), ""
    m, c = _CLAUSE_OPEN.search(before), _CLAUSE_CLOSE.match(after)
    if m and c:
        return m.start(), end, ""
    m, c = _SENTENCE_OPEN.search(before), _SENTENCE_CLOSE.match(after)
    if m and c:
        stop = end + c.end()
        if m.start() == 0:                         # the text began with the reference sentence
            while stop < len(text) and text[stop].isspace():
                stop += 1
        return m.start(), stop, ""
    return start, end, _gone(before, n_removed)


def _gone(before: str, n_removed: int) -> str:
    words = GONE_ONE if n_removed == 1 else GONE_MANY
    return words[0].upper() + words[1:] if _SENTENCE_START.search(before) else words


def _splice(text: str, start: int, end: int, repl: str) -> str:
    """``text`` with ``text[start:end]`` replaced; a removal leaves no doubled space and no space
    before the punctuation that follows it."""
    left, right = text[:start], text[end:]
    if not repl and left.endswith((" ", "\t")) and (not right or right[0] in " \t.,;:!?)"):
        left = left.rstrip(" \t")
    return left + repl + right


def rewrite_text(text: str, resolve: Resolver, stats: RewriteStats | None = None) -> str:
    """``text`` with every run of finding IDs (``FND-001``, ``FND-001 and FND-004``, ``FND-001, FND-002
    or FND-003``) rewritten through ``resolve`` (old ID to new ID, or ``None`` to remove): repeats
    dropped, the run's own form kept when nothing changes, removal as in the module docstring."""
    stats = stats if stats is not None else RewriteStats()
    out = text
    for m in reversed(list(_RUN.finditer(text))):
        run = m.group(0)
        tokens = FINDING_REF.findall(run)
        new: list[str] = []
        for t in tokens:
            r = resolve(t)
            if r is None:
                stats.removed += 1
                continue
            if r != t:
                stats.remapped += 1
            if r not in new:
                new.append(r)
        if new == tokens:
            continue
        if new:
            out = _splice(out, m.start(), m.end(), _join(new, run))
        else:
            removed = _splice(out, *_removal(out, m.start(), m.end(), len(tokens)))
            out = removed if removed.strip() else _splice(out, m.start(), m.end(),     # never empty a text
                                                          _gone(out[:m.start()], len(tokens)))
    return out


def mark_drafts(text: str, final: Iterable[str], prior: Iterable[str] = (), *,
                stats: RewriteStats | None = None) -> str:
    """A disclosure's text with each ID that is no final finding (nor, in delta mode, a prior one)
    written ``draft FND-nnn``; already marked IDs are left alone."""
    keep = set(final) | set(prior)
    stats = stats if stats is not None else RewriteStats()

    def sub(m: re.Match[str]) -> str:
        t = m.group(0)
        if t in keep or text[max(0, m.start() - len(DRAFT_PREFIX)):m.start()].lower() == DRAFT_PREFIX:
            return t
        stats.marked_draft += 1
        return DRAFT_PREFIX + t

    return FINDING_REF.sub(sub, text)


def rewrite_tree(node: Any, resolve: Resolver, stats: RewriteStats | None = None, *,
                 skip: frozenset[str] = SKIP_KEYS, override: Mapping[str, Resolver] | None = None) -> Any:
    """A JSON tree with its text and its ID lists rewritten through ``resolve``; keys in ``skip`` are
    copied as they are, and a key in ``override`` uses that resolver for its subtree."""
    stats = stats if stats is not None else RewriteStats()
    if isinstance(node, str):
        return rewrite_text(node, resolve, stats)
    if isinstance(node, list):
        return [rewrite_tree(v, resolve, stats, skip=skip, override=override) for v in node]
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k in skip:
                out[k] = v
            elif k in ID_LIST_KEYS and isinstance(v, list):
                out[k] = remap_ids(v, (override or {}).get(k, resolve), stats)
            elif override and k in override:
                out[k] = rewrite_tree(v, override[k], stats, skip=skip)
            else:
                out[k] = rewrite_tree(v, resolve, stats, skip=skip, override=override)
        return out
    return node


def remap_ids(ids: Iterable[str], resolve: Resolver, stats: RewriteStats | None = None) -> list[str]:
    """An ID list through ``resolve``: removed IDs dropped, repeats dropped, order kept."""
    out: list[str] = []
    for i in ids:
        r = resolve(i)
        if stats is not None:
            if r is None:
                stats.removed += 1
            elif r != i:
                stats.remapped += 1
        if r is not None and r not in out:
            out.append(r)
    return out


# ============================================================================ the run's ID map


@dataclass
class IdChain:
    """Resolution of an ID through the run's maps (the module docstring's three numberings).

    ``shards`` maps each shard to {its own ID: draft ID}, ``refine`` a draft ID to the kept ID or
    ``None``, ``verify`` a draft ID to its new ID or ``None``; ``final`` are the report's finding IDs
    and ``prior`` the prior review's (delta mode)."""

    shards: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    refine: Mapping[str, str | None] = field(default_factory=dict)
    verify: Mapping[str, str | None] = field(default_factory=dict)
    final: frozenset[str] = frozenset()
    prior: frozenset[str] = frozenset()

    def final_id(self, t: str) -> str | None:
        """The final numbering: a final ID, or a prior-review ID that is no ID of this run."""
        if t in self.final:
            return t
        return t if t in self.prior and not self._of_this_run(t) else None

    def after_verify(self, t: str) -> str | None:
        if t in self.verify:
            v = self.verify[t]
            return v if v is not None and v in self.final else None
        return self.final_id(t)

    def draft(self, t: str) -> str | None:
        """The draft numbering (after the merge): refine's map, then verify's."""
        if t in self.refine:
            k = self.refine[t]
            return None if k is None else self.after_verify(k)
        return self.after_verify(t)

    def shard(self, name: str | None) -> Resolver:
        """The numbering of shard ``name`` (its own IDs first); the draft numbering for text whose
        shard is not known (a run recorded before the map existed)."""
        own = self.shards.get(name) if name is not None else None
        if own is None:
            return self.draft

        def resolve(t: str) -> str | None:
            if t in own:
                return self.draft(own[t])
            return t if t in self.prior else None

        return resolve

    def shard_to_draft(self, name: str) -> Resolver:
        """Shard ``name``'s own IDs to draft IDs only (the merge's rewrite of sound areas and
        coverage notes); an ID the shard never gave is removed, a prior-review ID kept."""
        own = self.shards.get(name, {})
        return lambda t: own.get(t, t if t in self.prior else None)

    def final_map(self) -> dict[str, str | None]:
        """Every draft ID of the run to the final ID it became, or ``None``."""
        drafts = {d for own in self.shards.values() for d in own.values()} | set(self.refine) | set(self.verify)
        drafts |= {k for k in self.refine.values() if k is not None}
        return {d: self.draft(d) for d in sorted(drafts)}

    def origin(self) -> dict[str, str]:
        """Draft ID -> the shard that wrote it."""
        return {d: name for name, own in self.shards.items() for d in own.values()}

    def _of_this_run(self, t: str) -> bool:
        return (t in self.refine or t in self.verify
                or any(t in own.values() for own in self.shards.values()))


def chain_of(ids: FindingIdMap, final: Iterable[str]) -> IdChain:
    """The :class:`IdChain` of a run's recorded map and its final finding IDs."""
    return IdChain(shards=ids.shards, refine=ids.refine, verify=ids.verify, final=frozenset(final),
                   prior=frozenset(ids.prior))


def manifest_record(ids: FindingIdMap, final: Iterable[str]) -> dict[str, Any]:
    """``extra.finding_ids`` of the manifest: the recorded maps, ``final`` (every draft ID to the final
    ID it became, or null), the prior review's IDs and the report's rewrite counts."""
    return {"shards": {k: dict(v) for k, v in ids.shards.items()}, "refine": dict(ids.refine),
            "verify": dict(ids.verify), "final": chain_of(ids, final).final_map(), "prior": list(ids.prior),
            "rewrites": dict(ids.rewrites)}


# ============================================================================ checking (INV-12)


@dataclass(frozen=True)
class Ref:
    """One finding-ID reference in a review: where, which ID, and whether it is marked ``draft``."""

    path: str
    finding_id: str
    draft: bool
    disclosure: bool


def _disclosure(path: str) -> bool:
    return path.startswith("$.research_log.degradations") or path.startswith("$.limitations")


def iter_refs(review: Mapping[str, Any]) -> Iterator[Ref]:
    """Every finding-ID reference of a review JSON, by the module's rules (skipped keys and
    sections excluded, a finding's own ``id`` excluded)."""

    def walk(node: Any, path: str) -> Iterator[Ref]:
        if isinstance(node, str):
            for m in FINDING_REF.finditer(node):
                marked = node[max(0, m.start() - len(DRAFT_PREFIX)):m.start()].lower() == DRAFT_PREFIX
                yield Ref(path, m.group(0), marked, _disclosure(path))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from walk(v, f"{path}[{i}]")
        elif isinstance(node, Mapping):
            for k, v in node.items():
                if k not in SKIP_KEYS:
                    yield from walk(v, f"{path}.{k}")

    for k, v in review.items():
        if k not in SKIP_SECTIONS:
            yield from walk(v, f"$.{k}")


def dangling_refs(review: Mapping[str, Any]) -> list[str]:
    """INV-12's problems: each reference that is no finding of the review. A disclosure may name a
    draft as ``draft FND-nnn`` when ``run_manifest.extra.finding_ids.final`` lists it; in delta mode an
    ID listed in ``extra.finding_ids.prior`` is the prior review's."""
    final = {f["id"] for f in review.get("findings", [])}
    ids = ((review.get("run_manifest") or {}).get("extra") or {}).get("finding_ids") or {}
    drafts = set(ids.get("final") or {})
    prior = set(ids.get("prior") or [])
    problems = []
    for r in iter_refs(review):
        if r.draft and r.disclosure:
            if r.finding_id not in drafts:
                problems.append(f"{r.path}: draft {r.finding_id} is not in extra.finding_ids.final")
        elif r.finding_id not in final and r.finding_id not in prior:
            problems.append(f"{r.path}: {r.finding_id} is not a finding of this review")
    return problems
