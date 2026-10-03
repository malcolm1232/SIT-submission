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

import re
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


_LIST_ITEM = re.compile(r"^\s*(?:[-*\u2022]|\d{1,2}[.)])\s+\S")


def _md(text: str | None, indent: str = "") -> str:
    """``text`` as Markdown that keeps its bullet and numbered lists (``_one_line`` flattened them
    into " - " runs inside one paragraph: sit_sample_tools_1's fitness text and "What would change
    this verdict"). Prose lines are joined into paragraphs as before; each list item is one line,
    with its wrapped continuation lines joined to it; a blank line separates a paragraph from a list.
    Every line after the first is prefixed with ``indent`` (a list inside a bullet). Text with no
    list renders exactly as ``_one_line``."""
    lines = (text or "").splitlines()
    if not any(_LIST_ITEM.match(ln) for ln in lines):
        return _one_line(text)
    blocks: list[tuple[str, list[str]]] = []          # ("p", [lines]) | ("l", [items])
    for ln in lines:
        if not ln.strip():
            continue
        if _LIST_ITEM.match(ln):
            item = re.sub(r"^[*\u2022]\s+", "- ", ln.strip())
            item = re.sub(r"^-\s+", "- ", item)
            if not blocks or blocks[-1][0] != "l":
                blocks.append(("l", []))
            blocks[-1][1].append(_one_line(item))
        elif blocks and blocks[-1][0] == "l" and ln[:1].isspace():
            blocks[-1][1][-1] += " " + _one_line(ln)    # a wrapped list item
        else:
            if not blocks or blocks[-1][0] != "p":
                blocks.append(("p", []))
            blocks[-1][1].append(_one_line(ln))
    out = "\n\n".join(" ".join(b) if kind == "p" else "\n".join(b) for kind, b in blocks)
    if blocks[0][0] == "l":
        out = "\n\n" + out                            # a list never starts mid-line
    if indent:
        out = "\n".join((indent + ln) if i and ln else ln for i, ln in enumerate(out.split("\n")))
    return out


_NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
                 "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty")
_SEVERITY_COUNT = re.compile(r"\b(\d{1,3}|" + "|".join(_NUMBER_WORDS) + r")(\s+)(critical|high|medium|low)"
                             r"([- ]severity\b)"
                             r"(?:(\s+)(finding|issue|risk|gap|item|concern|defect|problem)(s?)\b"
                             r"(?:(\s+)(is|are|was|were|remains|remain|has|have)\b)?)?", re.IGNORECASE)
# The verb right after the counted noun, as (singular, plural): "finding remains", "findings remain".
_VERB_FORMS = (("is", "are"), ("was", "were"), ("remains", "remain"), ("has", "have"))


def _match_case(word: str, like: str) -> str:
    return word.capitalize() if like[:1].isupper() else word


def severity_counts(review: Review) -> dict[str, int]:
    """Findings per severity, as ``report.json`` holds them (strengths have none)."""
    out = {s.value: 0 for s in Severity}
    for f in review.findings:
        if f.severity is not None:
            out[f.severity.value] += 1
    return out


def reconcile_severity_counts(text: str, counts: dict[str, int]) -> str:
    """Make a "<n> high-severity" count in model prose equal the findings' own count. The verdict
    call wrote "seven high-severity findings are still open" in sit_sample_tools_1, where the
    review holds six; the number is computed from the findings, in the prose's own style (digits or
    a word, capitalised or not). A counted noun right after the count ("findings", "issues") and a
    verb right after that ("remain", "are") are made to agree with the new number, so a count
    rewritten to one reads "One high-severity finding remains". Text with no such count is
    returned unchanged."""

    def fix(m: re.Match[str]) -> str:
        n = counts.get(m.group(3).lower())
        if n is None:
            return m.group(0)
        num = m.group(1)
        if num.isdigit():
            new = str(n)
        else:
            new = _NUMBER_WORDS[n] if n < len(_NUMBER_WORDS) else str(n)
            if num[:1].isupper():
                new = new.capitalize()
        out = f"{new}{m.group(2)}{m.group(3)}{m.group(4)}"
        if m.group(6) is None:
            return out
        singular = n == 1
        out += f"{m.group(5)}{m.group(6)}{'' if singular else ('S' if m.group(6).isupper() else 's')}"
        if m.group(9) is not None:
            verb = m.group(9).lower()
            form = next(pair[0] if singular else pair[1] for pair in _VERB_FORMS if verb in pair)
            out += f"{m.group(8)}{_match_case(form, m.group(9))}"
        return out

    return _SEVERITY_COUNT.sub(fix, text)


def version_label(version: str | None) -> str | None:
    """The document version as the header shows it: "v2.0" for "2.0", "v2.0", "V2.0" or "Version 2.0"
    (sit_sample_tools_1 printed "vVersion 2.0"); a version that is not a number ("Draft 3") as is."""
    from sit_review_agent.phases.understand import normalise_version

    v = normalise_version(version)
    if not v:
        return None
    return f"v{v}" if v[:1].isdigit() else v


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
        "title_cell": _cell(f.title), "statement": _md(f.statement),
        "anchors": [{"page": a.page, "section": a.section_ref, "req": list(a.requirement_ids),
                     "quote": _one_line(a.quote), "doc_id": a.doc_id} for a in f.doc_anchors],
        "evidence": ev,
        "recommendation": None if rec is None else {
            "issue": _md(rec.issue, "    "), "rationale": _md(rec.rationale, "    "),
            "benefit": _one_line(rec.expected_benefit), "change": _one_line(rec.change_summary),
            "change_cell": _cell(rec.change_summary), "benefit_cell": _cell(rec.expected_benefit),
            "objectives": list(rec.objective_refs), "evidence_ids": list(rec.supporting_evidence_ids),
            "verification": _md(rec.verification, "    ") if rec.verification else None},
        "no_change_rationale": _md(f.no_change_rationale, "  ") if f.no_change_rationale else None,
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


#: The delta table's statuses in report order (``Review.prior_findings``), then the new findings.
PRIOR_STATUS_ORDER = ("resolved", "partially_addressed", "still_open", "withdrawn_on_reassessment")


def _delta_view(review: Review, ordered: list[Any], views: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The "Changes since the previous version" section. With the delta table (``prior_findings``,
    2026-10-03) it is keyed on the prior review's IDs: one row per prior finding, each with both IDs
    ("FND-003, was FND-002") or "(no finding in this review)", its status and note; then the findings
    new in the update, a regression marked. A report without the table (written earlier, or a
    ``--v1`` review with no prior review) lists this review's findings by their reassessment, as before."""
    by_id = {f.id: f for f in review.findings}
    entries = list(review.prior_findings)
    new = [{**views[f.id], "regression": bool(f.reassessment and f.reassessment.regression)} for f in ordered
           if f.reassessment is None or f.reassessment.status.value == "new_in_update"]
    if not entries:
        groups: dict[str, list[dict[str, Any]]] = {}
        for f in ordered:
            st = f.reassessment.status.value if f.reassessment else "new_in_update"
            if st != "new_in_update":
                groups.setdefault(st, []).append({
                    "label": f"{f.id}, was {f.reassessment.prior_finding_id}" if f.reassessment else f.id,
                    "title": _one_line(f.title),
                    "note": _one_line(f.reassessment.note) if f.reassessment and f.reassessment.note else None})
        return {"table": False, "prior_count": None, "not_re_examined": 0, "new": new,
                "groups": [{"status": s, "label": s.replace("_", " "), "rows": groups[s]}
                           for s in PRIOR_STATUS_ORDER if s in groups]}
    rows: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        if e.finding_ids:
            label = "; ".join(f"{fid}, was {e.prior_id}" for fid in e.finding_ids)
            title = _one_line(by_id[e.finding_ids[0]].title) if e.finding_ids[0] in by_id else _one_line(e.prior_title)
        else:
            label = f"was {e.prior_id} (no finding in this review)"
            title = _one_line(e.prior_title)
        rows.setdefault(e.status.value, []).append({"label": label, "title": title,
                                                    "note": _one_line(e.note) if e.note else None})
    return {"table": True, "prior_count": len(entries), "not_re_examined": sum(not e.re_examined for e in entries),
            "new": new, "groups": [{"status": s, "label": s.replace("_", " "), "rows": rows[s]}
                                   for s in PRIOR_STATUS_ORDER if s in rows]}


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


def _session_reopens(tools_extra: dict[str, Any]) -> str:
    """The run details' tool session line: the reopen count (zero included) and, when any, per
    server; ``not recorded`` for a manifest written before the count existed."""
    n = tools_extra.get("session_reopens")
    if not isinstance(n, int) or isinstance(n, bool):
        return "not recorded"
    by = tools_extra.get("session_reopens_by_server") or {}
    detail = ", ".join(f"{k}: {v}" for k, v in sorted(by.items())) if isinstance(by, dict) else ""
    return f"{n}" + (f" ({detail})" if n and detail else "")


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
    delta = _delta_view(review, ordered, views) if md.review_mode is ReviewMode.DELTA else None
    counts = severity_counts(review)
    used = {e.evidence_id for f in review.findings for e in f.evidence} | {
        x for s in review.sound_areas for x in s.evidence_ids}
    ctx = {
        "template": template,
        "headings": dict(SECTION_ORDER),
        "title": _one_line(under.title) or under.doc_id,
        "documents": [{"doc_id": d.doc_id, "title": _one_line(d.title) or d.doc_id, "role": d.role.value,
                       "version": version_label(d.version), "pages": d.page_count, "sha256_text": d.sha256_text}
                      for d in md.documents],
        "review_id": md.review_id, "run_id": md.run_id, "created_at": md.created_at,
        "review_mode": md.review_mode.value, "prior_review_id": md.prior_review_id,
        "disabled_tools": [t.name for t in m.tools if not t.enabled],
        "enabled_tools": [t.name for t in m.tools if t.enabled],
        # "Tools used": enabled servers that received at least one call in this run.
        "used_tools": [t.name for t in m.tools
                       if t.enabled and review.research_log.tool_calls_by_tool.get(t.name, 0) > 0],
        "no_external": not any(e.source_type.value == "external" for e in review.evidence_ledger),
        "intent": {"statement": _md(review.intent_summary.statement),
                   "objectives": [{"ref": o.ref, "text": _one_line(o.text)} for o in review.intent_summary.objectives],
                   "constraints": [{"ref": o.ref, "text": _one_line(o.text)}
                                   for o in review.intent_summary.constraints],
                   "assumptions": [{"ref": o.ref, "text": _one_line(o.text)}
                                   for o in review.intent_summary.key_assumptions],
                   "anchors": intent_locations(review)},
        "verdict": {"label": review.verdict.label.value, "label_text": verdict_label_text(review),
                    "confidence": f"{review.verdict.confidence:.2f}",
                    "band": confidence_band(review.verdict.confidence),
                    "rationale": reconcile_severity_counts(_md(review.verdict.rationale), counts),
                    "conditions": [{"text": reconcile_severity_counts(_md(c.text, "  "), counts),
                                    "ids": c.finding_ids} for c in review.verdict.conditions],
                    "per_objective": [{"ref": o.objective_ref, "label": o.label.value, "ids": o.finding_ids}
                                      for o in review.verdict.per_objective],
                    "what_would_change_it": reconcile_severity_counts(_md(review.verdict.what_would_change_it),
                                                                      counts)
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
            "session_reopens": _session_reopens(extra.get("tools") or {}),
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
