"""Review -> Markdown report (robustness §10 item 11: the model fills fields, the template owns the
structure). Template: ``agent/sit_review_agent/report/templates/report.md.j2`` (Jinja,
StrictUndefined), rendered from the Review only, so ``report.md`` can be regenerated offline
(REPRODUCIBILITY R0) and without an LLM call (fresh_eyes R-08).

Section order follows lab §2.3 (``SECTION_ORDER``). A kind with no findings still gets its
section with "None found" and the criteria that were checked (fresh_eyes §1.6). URLs appear only
as rendered from ledger entries (INV-05).

Two layouts (``config/agent.yaml`` ``report.template``): ``standard`` (one block per finding) and
``risk_register`` (findings as a table with Likelihood / Impact / Owner columns; fresh_eyes §1.8).
Findings below ``report.min_severity`` move to an appendix in both layouts; strengths (no
severity) are never filtered. The template never reads ``run_manifest.extra.outputs``, so the
hash of ``report.md`` can be stored in the manifest that the report itself shows.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import jinja2

from sit_review_agent.llm.outputs import CriterionCoverage
from sit_review_agent.llm.usage_budget import describe_unrecorded
from sit_review_agent.models import (
    SEVERITY_RANK,
    Disposition,
    Finding,
    Kind,
    Review,
    ReviewMode,
    Severity,
    VerdictLabel,
)

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
TEMPLATE_DIR = Path(__file__).parent / "templates"
APPENDIX_HEADING = "Appendix: findings below the reporting threshold"
EXEC_SUMMARY_MAX_WORDS = 150


@lru_cache(maxsize=1)
def _env() -> jinja2.Environment:
    return jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)), undefined=jinja2.StrictUndefined,
                              autoescape=False, keep_trailing_newline=True, trim_blocks=True, lstrip_blocks=True)


def confidence_band(c: float) -> str:
    """Verbal band derived from the number (spec README: high >= 0.8, medium >= 0.5, low)."""
    return "high" if c >= 0.8 else ("medium" if c >= 0.5 else "low")


def _one_line(text: str | None) -> str:
    return " ".join((text or "").split())


def _cell(text: str | None) -> str:
    return _one_line(text).replace("|", "\\|")


def _finding_view(f: Finding, ledger: dict[str, dict[str, Any]], registry: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ev = []
    for e in f.evidence:
        le = ledger.get(e.evidence_id, {})
        ev.append({"id": e.evidence_id, "source_type": e.source_type.value, "supports": e.supports_claim,
                   "quote": _one_line(e.quote), "citation": e.url_or_citation, "title": le.get("title"),
                   "retrieved_at": e.retrieved_at, "derived_from": list(e.derived_from),
                   "is_url": e.url_or_citation.startswith(("http://", "https://"))})
    rec = f.recommendation
    return {
        "id": f.id, "rank": f.rank, "kind": f.kind.value, "category": f.category.value if f.category else None,
        "severity": f.severity.value if f.severity else None, "confidence": f"{f.confidence:.2f}",
        "band": confidence_band(f.confidence), "disposition": f.disposition.value,
        "secondary": [d.value for d in f.secondary_dispositions], "title": _one_line(f.title),
        "title_cell": _cell(f.title), "statement": _one_line(f.statement),
        "anchors": [{"page": a.page, "section": a.section_ref, "req": list(a.requirement_ids),
                     "quote": _one_line(a.quote), "doc_id": a.doc_id} for a in f.doc_anchors],
        "evidence": ev,
        "recommendation": None if rec is None else {
            "issue": _one_line(rec.issue), "rationale": _one_line(rec.rationale),
            "benefit": _one_line(rec.expected_benefit), "change": _one_line(rec.change_summary),
            "change_cell": _cell(rec.change_summary), "benefit_cell": _cell(rec.expected_benefit),
            "objectives": list(rec.objective_refs), "evidence_ids": list(rec.supporting_evidence_ids),
            "verification": _one_line(rec.verification) if rec.verification else None},
        "no_change_rationale": _one_line(f.no_change_rationale) if f.no_change_rationale else None,
        "next_step": {"owner": f.next_step.owner, "action": _one_line(f.next_step.action)} if f.next_step else None,
        "owner_cell": _cell(f.next_step.owner) if f.next_step else "Design owner",
        "decisions": [{"id": a.registry_id, "relation": a.relation.value, "justification": _one_line(a.justification),
                       "doc_ref": registry.get(a.registry_id, {}).get("doc_ref", "")} for a in f.affected_decisions],
        "acknowledged": f.acknowledged_in_doc, "tags": list(f.tags),
        "reassessment": None if f.reassessment is None else {
            "status": f.reassessment.status.value, "prior": f.reassessment.prior_finding_id,
            "note": _one_line(f.reassessment.note) if f.reassessment.note else None},
        "provenance": f.provenance.phase.value,
    }


def _coverage_outcome(outcome: str, note: str | None) -> str:
    """The coverage table's outcome cell. A run with no assessment stores ``not_applicable`` with a
    note starting "not assessed" (``phases.assess``); the cell says "not assessed", as ``dra
    coverage`` does, because the criterion was never judged inapplicable."""
    from sit_review_agent.report.coverage import NOT_ASSESSED_NOTE

    if outcome == "not_applicable" and (note or "").lower().startswith(NOT_ASSESSED_NOTE):
        return NOT_ASSESSED_NOTE
    return outcome.replace("_", " ")


def not_assessed(review: Review) -> bool:
    """The run produced no assessment: the verdict label is ``not_assessed``
    (``phases.report.not_assessed_verdict``; the deadline stopped the review before assessment,
    robustness LLM-05, the assess answer was truncated twice at the output cap, LLM-07, or the
    model declined the assess call, LLM-06)."""
    return review.verdict.label is VerdictLabel.NOT_ASSESSED


def verdict_label_text(review: Review) -> str:
    """The verdict label as shown in ``report.md``; a not-assessed verdict names its reason."""
    if not_assessed(review):
        from sit_review_agent.llm.runtime import DECLINED_EVERY_ASSESS_SHARD
        from sit_review_agent.phases.report import NOT_ASSESSED_WHY, assessment_missing

        events = [d.event for d in review.research_log.degradations]
        declined = ["assess"] if any(e.startswith(DECLINED_EVERY_ASSESS_SHARD)
                                     or e.startswith("the model declined the assess call") for e in events) else []
        missing = assessment_missing(events, declined)
        return f"not assessed ({NOT_ASSESSED_WHY[missing]})" if missing else "not assessed"
    return review.verdict.label.value.replace("_", " ")


def executive_summary(review: Review, *, max_words: int = EXEC_SUMMARY_MAX_WORDS) -> str:
    """At most ``max_words`` words from existing fields only (verdict + top-ranked findings;
    runbook DEMO-08: the Review schema has no executive_summary field)."""
    v = review.verdict
    parts = [f"Verdict: {verdict_label_text(review)} (confidence {v.confidence:.2f}). {_one_line(v.rationale)}"]
    top = [f for f in sorted(review.findings, key=lambda f: f.rank) if f.disposition is not Disposition.NO_CHANGE][:3]
    if top:
        parts.append("Top findings: " + "; ".join(f"{f.id} {_one_line(f.title)}" for f in top) + ".")
    words = " ".join(parts).split()
    return " ".join(words[:max_words]) + (" ..." if len(words) > max_words else "")



def intent_locations(review: Review) -> list[dict[str, Any]]:
    """The intent summary's locations for "Located at", each once in first-seen order, with the
    number of anchored passages there. Two distinct quotes in one section are one location, so the
    line never repeats itself; ``passages`` keeps it in agreement with ``report.json``."""
    out: dict[tuple[str, int | None, str], dict[str, Any]] = {}
    for a in review.intent_summary.doc_anchors:
        loc = out.setdefault((a.doc_id, a.page, a.section_ref), {"page": a.page, "section": a.section_ref,
                                                                  "passages": 0})
        loc["passages"] += 1
    return list(out.values())

def render_markdown(review: Review, *, template: str = "standard", min_severity: Severity = Severity.LOW,
                    coverage: list[CriterionCoverage] | None = None) -> str:
    """Render ``review``. ``min_severity`` moves lower-severity findings to an appendix (live
    change "only report high and critical"); ``template="risk_register"`` renders findings as a
    Likelihood / Impact / Owner table (fresh_eyes §1.8)."""
    if template not in TEMPLATES:
        raise ValueError(f"unknown report template {template!r}; expected one of {TEMPLATES}")
    min_severity = Severity(min_severity)
    ledger = {e.evidence_id: e.model_dump(mode="json") for e in review.evidence_ledger}
    registry = {e.registry_id: e.model_dump(mode="json") for e in review.decision_registry}
    threshold = SEVERITY_RANK[min_severity]
    ordered = sorted(review.findings, key=lambda f: f.rank)
    main = [f for f in ordered if f.severity is None or SEVERITY_RANK[f.severity] >= threshold]
    appendix = [f for f in ordered if f.severity is not None and SEVERITY_RANK[f.severity] < threshold]
    views = {f.id: _finding_view(f, ledger, registry) for f in ordered}
    cov = list(coverage or [])
    checked = [c.criterion_id for c in cov if c.outcome != "not_applicable"]

    kinds = []
    for key, heading in SECTION_ORDER:
        if key.startswith("kind:"):
            k = Kind(key.split(":", 1)[1])
            kinds.append({"kind": k.value, "heading": heading,
                          "findings": [views[f.id] for f in main if f.kind is k]})
    m = review.run_manifest
    extra = m.extra or {}
    md = review.metadata
    doc_by_role = {d.role.value: d for d in md.documents}
    under = doc_by_role.get("under_review", md.documents[0])
    delta = None
    if md.review_mode is ReviewMode.DELTA:
        groups: dict[str, list[dict[str, Any]]] = {}
        for f in ordered:
            st = f.reassessment.status.value if f.reassessment else "new_in_update"
            groups.setdefault(st, []).append(views[f.id])
        delta = [{"status": s, "label": s.replace("_", " "), "findings": groups[s]}
                 for s in ("resolved", "partially_addressed", "still_open", "new_in_update") if s in groups]
    used = {e.evidence_id for f in review.findings for e in f.evidence} | {
        x for s in review.sound_areas for x in s.evidence_ids}
    ctx = {
        "template": template,
        "headings": dict(SECTION_ORDER),
        "title": _one_line(under.title) or under.doc_id,
        "documents": [{"doc_id": d.doc_id, "title": _one_line(d.title) or d.doc_id, "role": d.role.value,
                       "version": d.version, "pages": d.page_count, "sha256_text": d.sha256_text}
                      for d in md.documents],
        "review_id": md.review_id, "run_id": md.run_id, "created_at": md.created_at,
        "review_mode": md.review_mode.value, "prior_review_id": md.prior_review_id,
        "disabled_tools": [t.name for t in m.tools if not t.enabled],
        "enabled_tools": [t.name for t in m.tools if t.enabled],
        "no_external": not any(e.source_type.value == "external" for e in review.evidence_ledger),
        "intent": {"statement": _one_line(review.intent_summary.statement),
                   "objectives": [{"ref": o.ref, "text": _one_line(o.text)} for o in review.intent_summary.objectives],
                   "constraints": [{"ref": o.ref, "text": _one_line(o.text)}
                                   for o in review.intent_summary.constraints],
                   "assumptions": [{"ref": o.ref, "text": _one_line(o.text)}
                                   for o in review.intent_summary.key_assumptions],
                   "anchors": intent_locations(review)},
        "verdict": {"label": review.verdict.label.value, "label_text": verdict_label_text(review),
                    "confidence": f"{review.verdict.confidence:.2f}",
                    "band": confidence_band(review.verdict.confidence),
                    "rationale": _one_line(review.verdict.rationale),
                    "conditions": [{"text": _one_line(c.text), "ids": c.finding_ids}
                                   for c in review.verdict.conditions],
                    "per_objective": [{"ref": o.objective_ref, "label": o.label.value, "ids": o.finding_ids}
                                      for o in review.verdict.per_objective],
                    "what_would_change_it": _one_line(review.verdict.what_would_change_it)
                    if review.verdict.what_would_change_it else None},
        "executive_summary": executive_summary(review),
        "kinds": kinds,
        "checked": checked,
        "main": [views[f.id] for f in main],
        "recommendations": [views[f.id] for f in main if f.recommendation is not None],
        "no_change": [views[f.id] for f in main if f.disposition is Disposition.NO_CHANGE],
        "sound_areas": [{"id": s.id, "sections": ", ".join(s.section_refs), "why": _one_line(s.why_sound),
                         "anchors": [{"page": a.page, "section": a.section_ref, "quote": _one_line(a.quote)}
                                     for a in s.doc_anchors],
                         "evidence_ids": s.evidence_ids, "related": s.related_finding_ids}
                        for s in review.sound_areas],
        "unresolved": [{"text": _one_line(u.text), "ids": u.finding_ids,
                        "owner": u.next_step.owner if u.next_step else None,
                        "action": _one_line(u.next_step.action) if u.next_step else None}
                       for u in review.unresolved],
        "delta": delta,
        "limitations": [{"text": _one_line(lim.text), "ids": lim.degradation_ids} for lim in review.limitations],
        "unanswered": [_one_line(q) for q in review.research_log.unanswered_questions],
        "evidence": [{"id": e.evidence_id, "source_type": e.source_type.value,
                      "authority": e.authority.value if e.authority else None,
                      "title": _one_line(e.title) if e.title else None, "citation": e.url_or_citation,
                      "is_url": e.url_or_citation.startswith(("http://", "https://")),
                      "retrieved_at": e.retrieved_at, "excerpt": _one_line(e.excerpt)[:300] if e.excerpt else None,
                      "tool": f"{e.tool.server}/{e.tool.tool_name} {e.tool.call_id}" if e.tool else None,
                      "cited": e.evidence_id in used, "derived_from": e.derived_from}
                     for e in review.evidence_ledger],
        "coverage": [{"id": c.criterion_id, "outcome": _coverage_outcome(c.outcome, c.note), "ids": c.finding_ids,
                      "note": _cell(c.note)} for c in cov],
        "appendix": [views[f.id] for f in appendix],
        "appendix_heading": APPENDIX_HEADING,
        "min_severity": min_severity.value,
        "run": {
            "outcome": m.outcome.value, "requested_model": m.models_used[0].requested_model if m.models_used else "",
            "served_models": ", ".join(sorted({s for u in m.models_used for s in u.served_models})),
            "effort": m.models_used[0].effort if m.models_used else None,
            "transport": (extra.get("tools") or {}).get("transport", ""),
            "stop": f"{review.stop_reason.code.value} ({review.stop_reason.group.value})"
                    + (f": {review.stop_reason.detail}" if review.stop_reason.detail else ""),
            "iterations": review.research_log.iterations,
            "tool_calls": review.research_log.tool_calls_by_tool,
            "sources": (f"{review.research_log.sources_cited} cited of "
                        f"{review.research_log.sources_retrieved} retrieved"),
            "usage": m.usage.model_dump(mode="json"),
            "unrecorded": describe_unrecorded((extra.get("model") or {}).get("calls_with_unrecorded_usage") or []),
            "config_sha256": m.config_sha256, "prompts_sha256": m.prompts_bundle_sha256,
            "git_commit": m.git_commit, "fault_schedule": m.fault_schedule_id,
            "persona": m.review_config.persona, "criteria": ", ".join(m.review_config.criteria),
            "fallbacks": len(m.fallback_events), "deviations": list(extra.get("deviations") or []),
            "extractor": f"{m.extractor.name} {m.extractor.version}",
            "start": m.timestamps.start_utc,
        },
    }
    return _env().get_template("report.md.j2").render(**ctx)
