"""The delta table of a re-assessment (lab §1.5; rehearsal defects 1 and 2, 2026-10-03).

Every finding of the previous review gets exactly one status in ``Review.prior_findings``, keyed on
its ID there (``prior_id``; the previous review is never renumbered):

* carried forward by one or more findings of this review (``reassessment.prior_finding_id``, a
  status other than ``new_in_update``): their status; when several carry it, the least fixed one
  (still_open, then partially_addressed, then resolved), each successor named in the note;
* otherwise the status refine gave it (``state.prior_statuses``: resolved, partially_addressed,
  still_open, or withdrawn_on_reassessment with a one-line reason; refine is asked once when its
  answer omits one);
* otherwise ``still_open`` with ``re_examined`` false and the note "not re-examined", disclosed as a
  degradation. It is never dropped: a missing status and a fixed finding must not look the same.

``regression`` on a ``new_in_update`` finding is computed here, never by the model: one of its anchors
in the document under review falls in a section whose text differs from the same-numbered section of
the prior version (or that the prior version lacks). Both canonical texts are the run's own
(``text/``), so a reader can recompute it.

Pure functions over the run's objects; ``phases/report.py`` calls them when it assembles the Review,
after verify, so the table uses the final finding IDs.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from sit_review_agent.ingest.anchor import verify_anchor
from sit_review_agent.ingest.pdf import Document, Section
from sit_review_agent.ingest.text import PAGE_MARKER_RE
from sit_review_agent.llm.outputs import PriorStatusDraft
from sit_review_agent.models import (
    DocAnchor,
    Finding,
    PriorFindingEntry,
    PriorFindingStatus,
    ReassessmentStatus,
)

#: The note of a prior finding no answer gave a status (with ``re_examined`` false).
NOT_RE_EXAMINED = "not re-examined"
#: When several findings carry one prior finding forward, the least fixed status stands.
_LEAST_FIXED = (ReassessmentStatus.STILL_OPEN, ReassessmentStatus.PARTIALLY_ADDRESSED, ReassessmentStatus.RESOLVED)


def prior_findings_of(previous_run_dir: str | Path | None) -> list[dict[str, str]]:
    """``[{id, title}]`` of the previous review's findings in its order; ``[]`` when there is none
    (a ``--v1`` delta review, a full review) or its report cannot be read."""
    if not previous_run_dir:
        return []
    try:
        data = json.loads((Path(previous_run_dir) / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [{"id": str(f.get("id", "")), "title": str(f.get("title", ""))}
            for f in data.get("findings") or [] if isinstance(f, dict) and f.get("id")]


def carried_prior_ids(findings: Iterable[Any]) -> set[str]:
    """Prior IDs that a finding (or draft) carries forward: a reassessment with a prior ID and a
    status other than ``new_in_update``."""
    out = set()
    for f in findings:
        r = getattr(f, "reassessment", None)
        if r is not None and r.prior_finding_id and r.status is not ReassessmentStatus.NEW_IN_UPDATE:
            out.add(r.prior_finding_id)
    return out


def build_prior_table(prior: Sequence[Mapping[str, str]], findings: Sequence[Finding],
                      statuses: Sequence[PriorStatusDraft]) -> tuple[list[PriorFindingEntry], list[str]]:
    """The delta table (one entry per prior finding, in the previous review's order) and the prior
    IDs recorded as not re-examined. ``statuses`` is refine's answer for the prior findings no draft
    carried; an entry there for a prior finding a final finding carries is ignored (the finding's own
    reassessment is the status), as is one for an ID the previous review does not have."""
    by_prior: dict[str, list[Finding]] = {}
    for f in findings:
        r = f.reassessment
        if r is not None and r.prior_finding_id and r.status is not ReassessmentStatus.NEW_IN_UPDATE:
            by_prior.setdefault(r.prior_finding_id, []).append(f)
    given = {}
    for s in statuses:
        given.setdefault(s.prior_finding_id, s)
    table: list[PriorFindingEntry] = []
    missing: list[str] = []
    for p in prior:
        pid, title = p["id"], p.get("title", "")
        carriers = by_prior.get(pid, [])
        if carriers:
            worst = min((f.reassessment.status for f in carriers if f.reassessment is not None),
                        key=_LEAST_FIXED.index)
            if len(carriers) == 1:
                note = carriers[0].reassessment.note if carriers[0].reassessment is not None else None
            else:
                note = "carried forward by " + ", ".join(
                    f"{f.id} ({f.reassessment.status.value.replace('_', ' ')})" for f in carriers
                    if f.reassessment is not None) + "; the least fixed status stands"
            table.append(PriorFindingEntry(prior_id=pid, prior_title=title, status=PriorFindingStatus(worst.value),
                                           finding_ids=[f.id for f in carriers], note=note, re_examined=True))
        elif pid in given:
            s = given[pid]
            table.append(PriorFindingEntry(prior_id=pid, prior_title=title, status=s.status, finding_ids=[],
                                           note=" ".join(s.note.split()) or None, re_examined=True))
        else:
            missing.append(pid)
            table.append(PriorFindingEntry(prior_id=pid, prior_title=title, status=PriorFindingStatus.STILL_OPEN,
                                           finding_ids=[], note=NOT_RE_EXAMINED, re_examined=False))
    return table, missing


def unknown_prior_refs(prior: Sequence[Mapping[str, str]], findings: Sequence[Finding]) -> list[str]:
    """``FND-x -> FND-y`` for each finding whose reassessment cites a prior ID the previous review
    does not have (only when there is a previous review)."""
    known = {p["id"] for p in prior}
    if not known:
        return []
    return [f"{f.id} -> {f.reassessment.prior_finding_id}" for f in findings
            if f.reassessment is not None and f.reassessment.prior_finding_id
            and f.reassessment.prior_finding_id not in known]


# ------------------------------------------------------------------------------ regression


def _body(doc: Document, sec: Section) -> str:
    return " ".join(PAGE_MARKER_RE.sub(" ", doc.text[sec.char_start:sec.char_end]).split())


def changed_sections(under: Document, prior: Document) -> set[str]:
    """Section numbers of ``under`` whose text (page markers and whitespace aside) differs from the
    same-numbered section of ``prior``, or that ``prior`` does not have."""
    before: dict[str, str] = {}
    for sec in prior.sections:                       # the last one wins: body text follows any contents list
        before[sec.section_id] = _body(prior, sec)
    after: dict[str, str] = {}
    for sec in under.sections:
        after[sec.section_id] = _body(under, sec)
    return {sid for sid, text in after.items() if before.get(sid) != text}


def anchor_section(doc: Document, anchor: DocAnchor) -> str | None:
    """The section of ``doc`` the anchor's quote lies in (by its matched position), else the
    section its ``section_ref`` names."""
    res = verify_anchor(doc, anchor.quote, anchor.page, anchor.section_ref)
    if res.ok and res.char_start is not None:
        sec = doc.section_at(res.char_start)
        if sec is not None:
            return sec.section_id
    sec = doc.find_section(anchor.section_ref)
    return sec.section_id if sec is not None else None


def is_regression(finding: Finding, under: Document, changed: set[str]) -> bool:
    """A ``new_in_update`` finding with an anchor in the document under review that falls in a
    changed section."""
    r = finding.reassessment
    if r is None or r.status is not ReassessmentStatus.NEW_IN_UPDATE:
        return False
    return any(anchor_section(under, a) in changed for a in finding.doc_anchors if a.doc_id == under.doc_id)


def mark_regressions(findings: Sequence[Finding], under: Document | None, prior: Document | None) -> list[Finding]:
    """``findings`` with ``reassessment.regression`` set from the two texts (unchanged without both)."""
    if under is None or prior is None:
        return list(findings)
    changed = changed_sections(under, prior)
    out = []
    for f in findings:
        if f.reassessment is not None:
            flag = is_regression(f, under, changed)
            if flag != f.reassessment.regression:
                f = f.model_copy(update={"reassessment": f.reassessment.model_copy(update={"regression": flag})})
        out.append(f)
    return out
