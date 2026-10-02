"""``verify`` (code, plus one optional anchor-repair LLM call; workstream C).
Prompt: ``prompts/verify.md``. Output of the repair call: ``AnchorRepairOutput``.

1. Verify every anchor (findings, sound areas, registry, intent) with
   ``ingest.anchor.verify_finding_anchors``; one repair turn for failures; rows into
   ``state.anchor_table`` and ``anchors.json`` (resolved / repaired / unresolved).
2. Hydrate drafts into canonical ``Finding`` objects (:func:`hydrate_finding`): evidence from the
   ledger, provenance from ``finding_meta``; drop anchors beyond 3.
3. Code checks (fresh_eyes §1.6 "complete, consistent, accurate, traceable"): unknown evidence IDs,
   URLs in free text not in the ledger, registry conflicts, non-refinement findings in
   ``unresolved``, verdict vs severities. A finding with no resolvable anchor cannot carry a
   recommendation (ADR-007): it is moved to ``unresolved`` and reported as unverified.
Writes: ``state.findings``, ``state.sound_areas``, ``state.anchor_table``, degradations.

Rules decided here (ADR-007 leaves them open):

* **Anchor downgrade.** An anchor that is still unresolved after the single repair turn is
  removed from its owner and recorded in ``anchors.json`` as ``unresolved``. A finding that keeps
  at least one resolved anchor stays a finding (its explain record says how many anchors were
  dropped). A finding with no resolved anchor is not a ``Finding`` any more (the spec needs >= 1
  anchor and INV-04 needs every anchor to resolve): it becomes an ``unresolved[]`` item marked
  "Unverified" with no recommendation, and a degradation discloses it. A sound area with no
  resolved anchor is dropped. Intent anchors are dropped the same way; if none is left, a
  code-built anchor on the document's opening passage is used and disclosed.
* **Registry anchors** cannot change after research has recorded registry hashes (INV-10), so
  they are settled right after ``understand`` by :func:`settle_registry_anchors` (code only: the
  entry's own ID is located in the text) and are only re-checked here.
* **Hydration** (:func:`hydrate_finding`): a cited ``EV-`` ID missing from the ledger, or cited
  with the wrong source type, is a hard error: the finding is dropped with a degradation, never
  repaired by inventing an entry. For ``doc`` and ``external`` evidence the quote must occur in
  the ledger excerpt; otherwise the excerpt itself is used (hydration from the ledger) and the
  change is recorded in the finding's history. Supporting-evidence IDs that are not supporting
  evidence of the same finding are removed; a recommendation left with none is a hard error.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from sit_review_agent.context import RunContext
from sit_review_agent.errors import LedgerError, LLMDeadlineError, LLMRefusalError, LLMSchemaError, LLMTruncatedError
from sit_review_agent.hashing import sha256_json
from sit_review_agent.ingest.anchor import (
    NO_ANCHORS,
    TOO_MANY_ANCHORS,
    AnchorResult,
    anchor_table_entry,
    verify_anchor,
    verify_finding_anchors,
)
from sit_review_agent.ingest.pdf import Document
from sit_review_agent.ingest.text import PAGE_MARKER_RE
from sit_review_agent.invariants import MIN_TEXT_CHARS
from sit_review_agent.llm.backend import supports_native_pdf
from sit_review_agent.llm.gateway import LLMRequest
from sit_review_agent.llm.outputs import (
    AnchorRepairOutput,
    DocAnchorDraft,
    FindingDraft,
    ReassessmentDraft,
)
from sit_review_agent.llm.prefix import start_conversation
from sit_review_agent.models import (
    DecisionRelation,
    DegradationType,
    DocAnchor,
    DocumentRole,
    EvidenceItem,
    Finding,
    IntentSummary,
    NextStep,
    Provenance,
    ProvenancePhase,
    ReassessmentStatus,
    Recommendation,
    RegistryEntry,
    RegistryEntryType,
    ReviewMode,
    SoundArea,
    SourceType,
    UnresolvedItem,
    finding_id,
    sound_area_id,
)
from sit_review_agent.rundir import JsonlWriter, write_json_atomic
from sit_review_agent.state.decision_registry import DecisionRegistry
from sit_review_agent.state.evidence_ledger import EvidenceLedger
from sit_review_agent.state.run_state import FindingMeta, FindingRevision
from sit_review_agent.states import PROVENANCE_PHASE, PhaseName

CONVERSATION_ID = "verify"
REPAIR_PURPOSE = "anchor_repair"
#: Failures listed in the single repair turn (the rest stay unresolved).
MAX_REPAIRS_PER_CALL = 60
INTENT_OWNER = "intent"
_FINDING_ID_RE = re.compile(r"^FND-[0-9]{3,}$")
_NORM_WS = re.compile(r"\s+")
#: Placeholder text a hollow answer carries instead of content (robustness LLM-09).
_PLACEHOLDER = re.compile(r"^\W*(tbd|tba|tbc|todo|to do|n/?a|none|null|placeholder|lorem ipsum\b.*|x{3,})?\W*$",
                          re.IGNORECASE)


#: BEH-12 L0 check: a change that undoes something, and the content words of a decision.
_REVERSAL = re.compile(r"\b(replac\w*|remov\w*|drop|dropping|abandon\w*|retir\w*|revers\w*|eliminat\w*|"
                       r"stop using|get rid of|instead of|(?:switch\w*|migrat\w*|mov\w*) (?:away )?from)\b",
                       re.IGNORECASE)
_CONTENT_WORD = re.compile(r"[a-z][a-z0-9-]{3,}")
_COMMON_WORDS = frozenset({"with", "that", "this", "from", "into", "will", "uses", "using", "used", "built", "based",
                           "shall", "must", "should", "have", "each", "only", "their", "which", "when", "where"})


def unlabelled_conflicts(f: Finding, registry: Sequence[RegistryEntry]) -> list[str]:
    """Approved decisions that ``f``'s recommended change appears to reverse without an
    ``affected_decisions`` ``challenges`` label (robustness BEH-12, L0): the change summary uses a
    reversal verb and at least three of the decision's content words (all of them if it has fewer).
    Lexical, so it is disclosed, never used to drop a finding; paraphrased conflicts are the L1 judge's."""
    if f.recommendation is None:
        return []
    change = f.recommendation.change_summary.lower()
    if not _REVERSAL.search(change):
        return []
    words = set(_CONTENT_WORD.findall(change))
    labelled = {a.registry_id for a in f.affected_decisions if a.relation is DecisionRelation.CHALLENGES}
    out = []
    for e in registry:
        key = set(_CONTENT_WORD.findall(e.statement.lower())) - _COMMON_WORDS
        if e.type is RegistryEntryType.APPROVED_DECISION and e.registry_id not in labelled and key \
                and len(key & words) >= min(3, len(key)):
            out.append(e.registry_id)
    return out


def _norm(text: str) -> str:
    return _NORM_WS.sub(" ", text).strip().lower()


def hollow_fields(d: FindingDraft) -> list[str]:
    """Text fields of a draft that hold only a placeholder ("TBD", "N/A", "...", empty): such a
    finding is hollow and is dropped with a disclosure, never reported (robustness LLM-09)."""
    fields = {"title": d.title, "statement": d.statement, "no_change_rationale": d.no_change_rationale}
    if d.recommendation is not None:
        fields.update({f"recommendation.{k}": getattr(d.recommendation, k)
                       for k in ("issue", "rationale", "expected_benefit", "change_summary")})
    if d.next_step is not None:
        fields.update({"next_step.owner": d.next_step.owner, "next_step.action": d.next_step.action})
    return [k for k, v in fields.items() if v is not None and _PLACEHOLDER.match(v)]


# =============================================================================== hydration


def hydrate_finding(draft: FindingDraft, ledger: EvidenceLedger, meta: FindingMeta) -> Finding:
    """Canonical Finding from a draft: ``ledger.hydrate`` each citation, ``Provenance`` from
    ``meta`` (``states.PROVENANCE_PHASE[meta.last_phase]``, ``meta.model``, ``meta.prompt_hash``),
    ``criterion_ids`` dropped. Raises ``pydantic.ValidationError`` / ``LedgerError`` if invalid.

    ``ValueError`` (the base of ``ValidationError``) is also raised for the code-only rules the
    schema cannot express: recommendation text shorter than ``invariants.MIN_TEXT_CHARS`` (INV-06),
    a recommendation without supporting evidence of this finding, missing provenance."""
    evidence: list[EvidenceItem] = []
    seen: set[str] = set()
    for c in draft.evidence:
        if c.evidence_id in seen:
            continue
        seen.add(c.evidence_id)
        item = ledger.hydrate(c)                       # LedgerError: unknown ID or source-type mismatch
        entry = ledger.get(item.evidence_id)
        if item.source_type is SourceType.EXTERNAL and not entry.read_before_cite:
            continue                                   # only read sources may be cited (ADR-007)
        if item.source_type in (SourceType.DOC, SourceType.EXTERNAL):
            excerpt = entry.excerpt or ""
            if excerpt and (not item.quote or _norm(item.quote) not in _norm(excerpt)):
                item = item.model_copy(update={"quote": excerpt})
            elif not item.quote:
                item = item.model_copy(update={"quote": entry.title or entry.url_or_citation})
            item = EvidenceItem.model_validate(item.model_dump())
        evidence.append(item)

    rec: Recommendation | None = None
    if draft.recommendation is not None:
        r = draft.recommendation
        if not r.objective_refs or not any(x.strip() for x in r.objective_refs):
            raise ValueError(f"{draft.id}: recommendation names no objective")
        for name in ("issue", "rationale", "expected_benefit", "change_summary"):
            if len((getattr(r, name) or "").strip()) < MIN_TEXT_CHARS:
                raise ValueError(f"{draft.id}: recommendation.{name} is shorter than {MIN_TEXT_CHARS} characters")
        supporting = {e.evidence_id for e in evidence if e.supports_claim}
        ids = list(dict.fromkeys(x for x in r.supporting_evidence_ids if x in supporting))
        if not ids:
            raise ValueError(f"{draft.id}: recommendation cites no supporting evidence of this finding "
                             f"(cited {r.supporting_evidence_ids})")
        rec = Recommendation(issue=r.issue.strip(), rationale=r.rationale.strip(),
                             expected_benefit=r.expected_benefit.strip(), change_summary=r.change_summary.strip(),
                             objective_refs=[x for x in r.objective_refs if x.strip()],
                             supporting_evidence_ids=ids, verification=r.verification)

    phase = PROVENANCE_PHASE.get(meta.last_phase)
    if phase is None:
        raise ValueError(f"{draft.id}: last phase {meta.last_phase} cannot produce findings")
    if not meta.model or not meta.prompt_hash:
        raise ValueError(f"{draft.id}: provenance incomplete (model={meta.model!r}, prompt_hash={meta.prompt_hash!r})")
    nxt = NextStep(owner=draft.next_step.owner, action=draft.next_step.action) if draft.next_step else None
    return Finding.model_validate({
        "id": draft.id, "rank": draft.rank, "kind": draft.kind, "category": draft.category,
        "severity": draft.severity, "confidence": draft.confidence, "disposition": draft.disposition,
        "secondary_dispositions": list(dict.fromkeys(draft.secondary_dispositions)),
        "title": draft.title.strip(), "statement": draft.statement.strip(),
        "doc_anchors": [DocAnchor.model_validate(a.model_dump()).model_dump() for a in draft.doc_anchors[:3]],
        "evidence": [e.model_dump() for e in evidence],
        "recommendation": rec.model_dump() if rec else None,
        "no_change_rationale": draft.no_change_rationale,
        "next_step": nxt.model_dump() if nxt else None,
        "affected_decisions": [a.model_dump() for a in draft.affected_decisions],
        "acknowledged_in_doc": draft.acknowledged_in_doc, "tags": list(draft.tags),
        "reassessment": draft.reassessment.model_dump() if draft.reassessment else None,
        "provenance": Provenance(phase=phase, iteration=meta.iteration, model=meta.model,
                                 prompt_hash=meta.prompt_hash).model_dump(),
    })


# =============================================================================== anchors


@dataclass
class _Owner:
    owner_id: str
    kind: str                                  # finding | sound_area | registry | intent
    anchors: list[Any]                         # DocAnchorDraft or DocAnchor
    results: list[AnchorResult] = field(default_factory=list)
    repaired: set[int] = field(default_factory=set)

    def resolved(self) -> list[Any]:
        return [a for a, r in zip(self.anchors, self.results, strict=False) if r.ok][:3]


def _verify_owner(docs: dict[str, Document], o: _Owner) -> None:
    o.results = verify_finding_anchors(docs, o.anchors) if o.anchors else [verify_finding_anchors(docs, [])[0]]


def _window(tokens: Sequence[str], start: int, size: int = 20, min_size: int = 8) -> tuple[int, int]:
    """Up to ``size`` tokens beginning at ``start``; starts earlier only if fewer than ``min_size`` remain."""
    start = max(0, min(start, len(tokens)))
    hi = min(len(tokens), start + size)
    return (start if hi - start >= min_size else max(0, hi - min_size)), hi


def code_anchor(doc: Document, offset: int, *, min_tokens: int = 8) -> DocAnchor | None:
    """A verbatim anchor built in code at ``offset`` of ``doc.text``: the line holding it (plus
    following lines until it has ``min_tokens`` tokens), cut to at most 20 tokens from ``offset``,
    with the page and section at that offset. ``None`` if no such passage verifies."""
    start = doc.text.rfind("\n", 0, offset) + 1
    end = doc.text.find("\n", offset)
    end = len(doc.text) if end < 0 else end
    line = doc.text[start:end]
    while len(line.split()) < min_tokens and end < len(doc.text):
        nxt = doc.text.find("\n", end + 1)
        nxt = len(doc.text) if nxt < 0 else nxt
        extra = doc.text[end + 1:nxt]
        if PAGE_MARKER_RE.fullmatch(extra.strip()):
            break
        line = f"{line} {extra}".strip()
        end = nxt
    tokens = line.split()
    if len(tokens) < min_tokens:
        return None
    before = len(doc.text[start:offset].split())
    lo, hi = _window(tokens, before)
    quote = " ".join(tokens[lo:hi])
    sec = doc.section_at(offset)
    section_ref = sec.section_id if sec else (doc.sections[0].section_id if doc.sections else "1")
    page = doc.page_at(offset) if doc.pages else None
    try:
        anchor = DocAnchor(doc_id=doc.doc_id, section_ref=section_ref, requirement_ids=[], quote=quote, page=page)
    except ValidationError:
        return None
    return anchor if verify_anchor(doc, anchor.quote, anchor.page, anchor.section_ref).ok else None


def settle_registry_anchors(ctx: RunContext) -> list[str]:
    """Code-only check of the registry anchors right after ``understand`` (before any later phase
    has used the registry, so INV-10 holds). An unresolved anchor is rebuilt around the entry's own
    ID (``doc_ref``, e.g. ``D-3``) where the document states it; an entry that cannot be anchored is
    removed and disclosed. Returns notes.

    ``understand`` freezes the registry and records its hash as iteration 0 (so a run without
    research still has one); that freeze-time record is replaced by the settled registry's hash.
    Once a research iteration has recorded a hash, or any phase after ``understand`` has completed,
    this does nothing (the registry the later phases saw is what the report shows)."""
    hashes = ctx.registry.hashes()
    later = set(ctx.state.completed_phases) - {PhaseName.INGEST, PhaseName.UNDERSTAND}
    if any(h.iteration > 0 for h in hashes) or later or not ctx.documents:
        return []
    notes: list[str] = []
    kept: list[RegistryEntry] = []
    changed = False
    for e in ctx.registry.entries():
        doc = ctx.documents.get(e.doc_anchor.doc_id) or ctx.doc_under_review()
        a = e.doc_anchor
        if a.doc_id in ctx.documents and verify_anchor(doc, a.quote, a.page, a.section_ref).ok:
            kept.append(e)
            continue
        changed = True
        fixed: DocAnchor | None = None
        for ref in doc.requirement_index.get(e.doc_ref, []):
            fixed = code_anchor(doc, ref.char_start)
            if fixed is not None:
                fixed = fixed.model_copy(update={"requirement_ids": [e.doc_ref]})
                break
        if fixed is not None:
            kept.append(e.model_copy(update={"doc_anchor": fixed}))
            notes.append(f"{e.registry_id} ({e.doc_ref}): anchor re-quoted from the passage stating {e.doc_ref}")
        else:
            ctx.state.add_degradation(
                DegradationType.OTHER,
                f"decision registry entry {e.registry_id} ({e.doc_ref}) removed: its quote could not be "
                "located in the document",
                f"{e.doc_ref} was not used as an approved decision or constraint in this review")
            notes.append(f"{e.registry_id} ({e.doc_ref}): removed (no verifiable passage)")
    if changed:
        settled = DecisionRegistry(kept, frozen=ctx.registry.frozen)
        if hashes:                                   # re-record the freeze-time hash for the settled registry
            settled.record_iteration(0)
        ctx.registry = settled
        ctx.sync_state()
    for n in notes:
        ctx.emit(f"registry anchor check: {n}")
    return notes


def intent_fallback_anchor(doc: Document) -> DocAnchor | None:
    """Anchor for the intent summary when none of the model's resolves: the document's opening
    passage (first section body, else the first text line)."""
    starts = [s.char_start for s in doc.sections] or [p.char_start for p in doc.pages] or [0]
    for off in starts:
        a = code_anchor(doc, off)
        if a is not None:
            return a
    return None


# =============================================================================== phase


def _degrade(ctx: RunContext, event: str, impact: str) -> None:
    ctx.state.add_degradation(DegradationType.OTHER, event, impact)


def _meta_from_log(ctx: RunContext, draft: FindingDraft) -> FindingMeta:
    """Provenance for a draft whose phase did not record ``finding_meta``: the last call of the
    last finding-producing phase that ran, read from ``state.llm_calls`` and ``llm.jsonl``."""
    phase = next((p for p in (PhaseName.REFINE, PhaseName.ASSESS) if ctx.state.llm_calls.get(p.value)),
                 PhaseName.ASSESS)
    call_id = (ctx.state.llm_calls.get(phase.value) or [None])[-1]
    return FindingMeta(finding_id=draft.id, criterion_ids=list(draft.criterion_ids), created_phase=phase,
                       created_call_id=call_id, last_phase=phase, last_call_id=call_id, model=None,
                       prompt_hash=None)


def _complete_meta(ctx: RunContext, meta: FindingMeta, calls: dict[str, dict[str, Any]]) -> FindingMeta:
    upd: dict[str, Any] = {}
    entry = calls.get(meta.last_call_id or "") or {}
    if not meta.model:
        served = sorted(ctx.llm.served_models())
        upd["model"] = entry.get("model") or (served[0] if served else ctx.config.agent.model)
    if not meta.prompt_hash:
        upd["prompt_hash"] = entry.get("request_sha256") or sha256_json({"call_id": meta.last_call_id})
    return meta.model_copy(update=upd) if upd else meta


def _llm_calls_by_id(ctx: RunContext) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in JsonlWriter(ctx.run_dir.llm_log).read():
        if e.get("call_id") and e.get("outcome", "ok") == "ok":
            out[e["call_id"]] = e
    return out


class VerifyPhase:
    name = PhaseName.VERIFY

    async def run(self, ctx: RunContext) -> RunContext:
        state = ctx.state
        docs = ctx.documents
        settle_registry_anchors(ctx)       # no-op once research recorded registry hashes (INV-10)

        # ---- 1. stable IDs (FND-nnn unique, SA-nnn) and owners
        drafts = [d.model_copy(deep=True) for d in state.finding_drafts]
        id_map = self._normalise_ids(drafts)
        sa_drafts = [s.model_copy(deep=True) for s in state.sound_area_drafts]
        owners: list[_Owner] = [_Owner(d.id, "finding", list(d.doc_anchors)) for d in drafts]
        owners += [_Owner(sound_area_id(i + 1), "sound_area", list(s.doc_anchors)) for i, s in enumerate(sa_drafts)]
        owners += [_Owner(e.registry_id, "registry", [e.doc_anchor]) for e in ctx.registry.entries()]
        if state.intent_summary is not None:
            owners.append(_Owner(INTENT_OWNER, "intent", list(state.intent_summary.doc_anchors)))
        for o in owners:
            _verify_owner(docs, o)

        # ---- 2. one repair turn (ADR-007), never for the frozen registry
        call_id = await self._repair(ctx, owners)

        # ---- 3. anchor table
        rows = [anchor_table_entry(o.owner_id, i, a, r, repaired=i in o.repaired)
                for o in owners for i, (a, r) in enumerate(zip(o.anchors, o.results, strict=False))]
        rows += [anchor_table_entry(o.owner_id, 0, _EmptyAnchor(), o.results[0]) for o in owners if not o.anchors]
        by_owner = {o.owner_id: o for o in owners}
        n_unresolved = sum(1 for r in rows if r["anchor_status"] == "unresolved")
        n_repaired = sum(1 for r in rows if r["anchor_status"] == "repaired")

        # ---- 4. findings: drop unresolved anchors, hydrate, or move to unverified
        calls = _llm_calls_by_id(ctx)
        findings: list[tuple[int, Finding]] = []
        unverified: list[UnresolvedItem] = []
        dropped: list[str] = []
        metas = dict(state.finding_meta)
        registry_ids = ctx.registry.ids()
        delta = state.review_mode is ReviewMode.DELTA
        for idx, d in enumerate(drafts):
            o = by_owner[d.id]
            old_id = next((k for k, v in id_map.items() if v == d.id), d.id)
            meta = metas.get(d.id) or metas.get(old_id) or _meta_from_log(ctx, d)
            meta = _complete_meta(ctx, meta.model_copy(update={"finding_id": d.id,
                                                               "criterion_ids": list(d.criterion_ids)}), calls)
            history = list(meta.history)
            hollow = hollow_fields(d)
            if hollow:
                why = f"placeholder text in {', '.join(hollow)}"
                dropped.append(f"{d.id}: {why} (hollow answer)")
                metas[d.id] = meta.model_copy(update={"history": history + [FindingRevision(
                    phase=PhaseName.VERIFY, call_id=call_id, note=f"dropped: {why}")]})
                continue
            resolved = o.resolved()
            if not resolved:
                unverified.append(_unverified_item(d))
                metas[d.id] = meta.model_copy(update={"history": history + [FindingRevision(
                    phase=PhaseName.VERIFY, call_id=call_id, note="no anchor resolved: moved to unresolved as "
                    "unverified (ADR-007)")]})
                continue
            changes: dict[str, list[Any]] = {}
            if len(resolved) != len(d.doc_anchors):
                changes["doc_anchors"] = [len(d.doc_anchors), len(resolved)]
            if o.repaired:
                changes["repaired_anchors"] = [[], sorted(o.repaired)]
            d.doc_anchors = [DocAnchorDraft.model_validate(a.model_dump()) for a in resolved]
            unknown = [a.registry_id for a in d.affected_decisions if a.registry_id not in registry_ids]
            if unknown:
                d.affected_decisions = [a for a in d.affected_decisions if a.registry_id in registry_ids]
                changes["affected_decisions"] = [unknown, []]
            if delta and d.reassessment is None:
                d.reassessment = ReassessmentDraft(prior_finding_id=None, status=ReassessmentStatus.NEW_IN_UPDATE,
                                                   note="no reassessment given; treated as new in this version")
                changes["reassessment"] = [None, "new_in_update"]
            try:
                f = hydrate_finding(d, ctx.ledger, meta)
            except (LedgerError, ValueError) as exc:
                dropped.append(f"{d.id}: {_short(exc)}")
                metas[d.id] = meta.model_copy(update={"history": history + [FindingRevision(
                    phase=PhaseName.VERIFY, call_id=call_id, note=f"dropped in hydration: {_short(exc)}")]})
                continue
            cited = {c.evidence_id: c.quote for c in d.evidence}
            replaced = [e.evidence_id for e in f.evidence if cited.get(e.evidence_id) != e.quote]
            if replaced:
                changes["evidence_quotes_from_ledger"] = [[], replaced]
            unread = [x for x in cited if x not in {e.evidence_id for e in f.evidence}]
            if unread:
                changes["evidence_dropped_not_read_before_cite"] = [unread, []]
            if delta:
                f = f.model_copy(update={"provenance": f.provenance.model_copy(
                    update={"phase": ProvenancePhase.DELTA_REVIEW})})
            if changes:
                history.append(FindingRevision(phase=PhaseName.VERIFY, call_id=call_id, changed_fields=changes,
                                               note="verify: anchors checked, evidence hydrated from the ledger"))
            metas[d.id] = meta.model_copy(update={"history": history})
            findings.append((idx, f))

        # ---- 5. ranks 1..n in the model's order; drop meta of renamed drafts
        findings.sort(key=lambda t: (t[1].rank, t[0]))
        state.findings = [f.model_copy(update={"rank": i + 1}) for i, (_, f) in enumerate(findings)]
        kept_ids = {f.id for f in state.findings}
        for old, new in id_map.items():
            if old != new:
                metas.pop(old, None)
        state.finding_meta = metas
        for f in state.findings:                       # BEH-12: undeclared reversal of an approved decision
            for rid in unlabelled_conflicts(f, ctx.registry.entries()):
                e = ctx.registry.get(rid)
                _degrade(ctx, f"{f.id}'s recommendation appears to reverse approved decision {rid} ({e.doc_ref}) "
                         "without a 'challenges' label", "the conflict is not declared and not backed by the two "
                         "evidence items a challenge needs; check it against the decision before acting on it")

        # ---- 6. sound areas
        sound: list[SoundArea] = []
        for i, s in enumerate(sa_drafts):
            o = by_owner[sound_area_id(i + 1)]
            resolved = o.resolved()
            if not resolved:
                dropped.append(f"{o.owner_id}: no anchor resolved")
                continue
            if _PLACEHOLDER.match(s.why_sound):
                dropped.append(f"{o.owner_id}: placeholder text in why_sound (hollow answer)")
                continue
            ev = [x for x in dict.fromkeys(s.evidence_ids) if x in ctx.ledger and (
                ctx.ledger.get(x).source_type is not SourceType.EXTERNAL or ctx.ledger.get(x).read_before_cite)]
            related = [id_map.get(x, x) for x in s.related_finding_ids]
            refs = [x for x in s.section_refs if x.strip()] or [a.section_ref for a in resolved]
            try:
                sound.append(SoundArea(id=o.owner_id, section_refs=refs, why_sound=s.why_sound.strip(),
                                       doc_anchors=[DocAnchor.model_validate(a.model_dump()) for a in resolved],
                                       evidence_ids=ev,
                                       related_finding_ids=[x for x in dict.fromkeys(related) if x in kept_ids]))
            except ValidationError as exc:
                dropped.append(f"{o.owner_id}: {_short(exc)}")
        state.sound_areas = sound

        # ---- 7. intent anchors
        if state.intent_summary is not None:
            state.intent_summary = self._settle_intent(ctx, state.intent_summary, by_owner[INTENT_OWNER])

        # ---- 8. coverage IDs follow renumbering; unverified items; disclosures; anchors.json
        state.coverage = [c.model_copy(update={"finding_ids": [id_map.get(x, x) for x in c.finding_ids
                                                               if id_map.get(x, x) in kept_ids]})
                          for c in state.coverage]
        state.unresolved = unverified
        if unverified:
            _degrade(ctx, f"{len(unverified)} finding(s) had no anchor that could be verified in the document "
                     "after one repair turn and are listed as unverified",
                     "unverified findings carry no recommendation and are not counted as findings (ADR-007)")
        if dropped:
            _degrade(ctx, f"{len(dropped)} item(s) dropped by code checks in verify: " + "; ".join(dropped)[:900],
                     "these items are not part of the review; see the run directory for the drafts")
        state.anchor_table = rows
        write_json_atomic(ctx.run_dir.anchors, {
            "rules": {"min_quote_tokens": 8, "fuzzy_threshold": 0.90, "page_window": 1, "section_window": 1},
            "repair_call_id": call_id,
            "summary": {"anchors": len(rows), "resolved": sum(1 for r in rows if r["anchor_status"] == "resolved"),
                        "repaired": n_repaired, "unresolved": n_unresolved},
            "rows": rows})
        ctx.emit(f"anchors: {len(rows) - n_unresolved - n_repaired} resolved, {n_repaired} repaired, "
                 f"{n_unresolved} unresolved; {len(state.findings)} findings verified, {len(unverified)} unverified")
        return ctx

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _normalise_ids(drafts: list[FindingDraft]) -> dict[str, str]:
        """Keep valid unique ``FND-nnn`` IDs; give the rest the next free number. Returns old -> new."""
        used = {d.id for d in drafts if _FINDING_ID_RE.match(d.id)}
        seen: set[str] = set()
        mapping: dict[str, str] = {}
        n = 0
        for d in drafts:
            new = d.id
            if not _FINDING_ID_RE.match(d.id) or d.id in seen:
                n += 1
                while finding_id(n) in used or finding_id(n) in seen:
                    n += 1
                new = finding_id(n)
            seen.add(new)
            mapping.setdefault(d.id, new)
            d.id = new
        return mapping

    async def _repair(self, ctx: RunContext, owners: list[_Owner]) -> str | None:
        """At most ONE model call (ADR-007). Returns its call ID or ``None``."""
        failures: list[tuple[_Owner, int]] = []
        for o in owners:
            if o.kind == "registry":
                continue
            for i, r in enumerate(o.results[:len(o.anchors)]):
                if not r.ok and not set(r.reasons) & {TOO_MANY_ANCHORS, NO_ANCHORS}:
                    failures.append((o, i))
        if not failures:
            return None
        failures = failures[:MAX_REPAIRS_PER_CALL]
        listed = [{"owner_id": o.owner_id, "anchor_index": i, "section_ref": o.anchors[i].section_ref,
                   "page": o.anchors[i].page, "quote": o.anchors[i].quote,
                   "reason": ", ".join(o.results[i].reasons) or "not found"} for o, i in failures]
        persona = ctx.config.persona()
        system = ctx.prompts.render("system.md", persona_title=persona.title, persona_emphasis=persona.emphasis)
        brief = ctx.prompts.render("verify.md", failures=listed)
        docs = [ctx.doc_under_review()] + [d for d in ctx.documents.values() if d.role is not DocumentRole.UNDER_REVIEW]
        messages, bp = start_conversation(docs, brief.text, native_pdf=supports_native_pdf(ctx.llm))
        req = LLMRequest(phase=PhaseName.VERIFY, conversation_id=CONVERSATION_ID, system=system.text,
                         messages=messages, effort=ctx.config.effort_for(PhaseName.VERIFY),
                         max_tokens=ctx.config.agent.max_tokens, output_schema=AnchorRepairOutput,
                         cache_breakpoints=(bp,), thinking_display=ctx.config.agent.thinking_display,
                         purpose=REPAIR_PURPOSE)
        ctx.emit(f"{len(failures)} anchor(s) unresolved; one repair turn")
        try:
            res = await ctx.llm.call(req)
        except (LLMRefusalError, LLMSchemaError, LLMTruncatedError, LLMDeadlineError) as exc:
            if exc.call_id:
                ctx.state.llm_calls.setdefault(PhaseName.VERIFY.value, []).append(exc.call_id)
            if isinstance(exc, LLMRefusalError):
                ctx.state.refusals.append({"call_id": exc.call_id, "stage": PhaseName.VERIFY.value,
                                           "category": exc.category})
            _degrade(ctx, f"anchor repair call failed ({type(exc).__name__})",
                     "unresolved anchors were not re-quoted; affected findings may be listed as unverified")
            return exc.call_id
        ctx.state.llm_calls.setdefault(PhaseName.VERIFY.value, []).append(res.call_id)
        b = ctx.state.budget
        b.input_tokens += res.usage.total_input_tokens
        b.output_tokens += res.usage.output_tokens
        b.cache_read_input_tokens += res.usage.cache_read_input_tokens
        b.cache_creation_input_tokens += res.usage.cache_creation_input_tokens
        if res.fallback is not None:
            ctx.state.fallback_events.append(res.fallback)
            ctx.state.add_degradation(DegradationType.MODEL_FALLBACK,
                                      f"verify call {res.call_id} was served by {res.fallback.to_model} instead of "
                                      f"{res.fallback.from_model}",
                                      "part of this review was produced by another model; the run is not eval evidence")
        out: AnchorRepairOutput | None = res.parsed
        if out is None:
            return res.call_id
        wanted = {(o.owner_id, i): o for o, i in failures}
        for rep in out.repairs:
            o = wanted.get((rep.owner_id, rep.anchor_index))
            if o is None:
                continue
            a = rep.doc_anchor
            doc = ctx.documents.get(a.doc_id)
            if doc is None:
                continue
            r = verify_anchor(doc, a.quote, a.page, a.section_ref)
            if r.ok:
                o.anchors[rep.anchor_index] = a
                o.results[rep.anchor_index] = r
                o.repaired.add(rep.anchor_index)
        return res.call_id

    def _settle_intent(self, ctx: RunContext, intent: IntentSummary, o: _Owner) -> IntentSummary:
        resolved = [DocAnchor.model_validate(a.model_dump()) for a in o.resolved()]
        if resolved:
            return intent.model_copy(update={"doc_anchors": resolved})
        fb = intent_fallback_anchor(ctx.doc_under_review())
        if fb is None:
            return intent                    # INV-04 will report it; nothing verifiable to anchor on
        _degrade(ctx, "no intent-summary anchor could be verified; anchored to the document's opening passage",
                 "the design-intent summary is traceable only to the opening of the document")
        return intent.model_copy(update={"doc_anchors": [fb]})


class _EmptyAnchor:
    """Stand-in for an owner with no anchors at all (one ``no_anchors`` row in anchors.json)."""

    doc_id = None
    page = None
    section_ref = None


def _short(exc: BaseException) -> str:
    if isinstance(exc, ValidationError) and exc.errors():
        # The first line of a ValidationError only says "1 validation error for Finding"; the
        # disclosure must say which rule the finding broke.
        e = exc.errors()[0]
        loc = ".".join(str(x) for x in e.get("loc", ())) or exc.title
        return f"{type(exc).__name__}: {loc}: {e.get('msg', '')}"[:200]
    text = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    return f"{type(exc).__name__}: {text}"[:200]


def _unverified_item(d: FindingDraft) -> UnresolvedItem:
    owner = d.next_step.owner if d.next_step and d.next_step.owner.strip() else "Design review lead"
    return UnresolvedItem(
        text=f"Unverified ({d.kind.value}): {d.title.strip() or d.statement.strip()[:80]}. "
             f"{d.statement.strip()} No quoted location could be verified in the document, so this is not "
             "reported as a finding.",
        finding_ids=[],
        next_step=NextStep(owner=owner, action="Locate the passage of the design that supports or refutes this "
                                              "point and re-review it."))
