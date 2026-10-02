"""A deterministic, content-aware fake grader for ``--judge fake`` and the offline tests.

PLUMBING ONLY. It reads the rendered grader inputs and answers with schema-valid PassA/PassB
JSON from simple rules (unanchored finding = padding; a citation from
:data:`sit_eval.grader.validation.FABRICATIONS` = fabricated source; text addressed to a grader =
injection; otherwise 3 on every dimension). It exists to exercise the pipeline, the aggregation and
the meta-validation checks end to end without a model; its scores say nothing about a review.
"""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

from sit_eval.grader.verify import FITNESS_VERDICT_LABELS, INJECTION_PATTERNS
from sit_eval.judge import FakeJudge, JudgeRequest

FAKE_MODEL = "fake-judge-heuristic"
_MATERIALITY = {"critical": "high", "high": "high", "medium": "medium", "low": "low"}
#: The V5 builder's statement template (validation.py); a real grader sees no marker.
FALSE_GAP_RE = re.compile(r"^The design defines no ")
_TRIAGE = {"refinement_now": "refinement", "needs_investigation": "investigation",
           "needs_prototyping": "prototyping", "needs_testing": "testing", "governance_decision": "governance",
           "no_change": "none"}


def _between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = text.find(end, i)
    return text[i:j if j >= 0 else None]


def _injected(text: str) -> bool:
    return any(p.search(text) for p in INJECTION_PATTERNS)


def _fabrication_hits(text: str) -> list[str]:
    from sit_eval.grader.validation import FABRICATIONS

    return [f["citation"] for f in FABRICATIONS if f["needle"] in text]


def _pass_a(req: JudgeRequest) -> dict[str, Any]:
    seed = _between(req.user, "SAMPLE_SEED: ", "\n").strip()
    block = _between(req.user, "FINDINGS (shuffled):\n", "\n<<<END REVIEW>>>")
    register = _between(req.user, "EVIDENCE REGISTER (agent-supplied; may be NONE):\n", "\n\n<<<REVIEW>>>")
    ledger = {}
    for line in register.splitlines():
        try:
            e = json.loads(line)
            ledger[e.get("evidence_id")] = e
        except (json.JSONDecodeError, AttributeError):
            continue
    findings, halls = [], []
    for line in block.splitlines():
        try:
            f = json.loads(line)
        except json.JSONDecodeError:
            continue
        anchors = f.get("doc_anchors") or []
        padding = not anchors
        ext = []
        for ev in f.get("evidence") or []:
            if ev.get("source_type") != "external":
                continue
            entry = ledger.get(ev.get("evidence_id"), {})
            cited = str(entry.get("url_or_citation") or ev.get("url_or_citation") or ev.get("evidence_id"))
            fab = _fabrication_hits(json.dumps(entry) + json.dumps(ev))
            ext.append({"cited": cited[:200], "specific": True, "authoritative": not fab,
                        "support": "fabricated" if fab else "supports"})
            for c in fab:
                halls.append({"finding_id": f["id"], "type": "fabricated_source", "severity": "material",
                              "status": "verified_false", "review_quote": c[:300], "design_quote": None,
                              "reasoning": "The cited clause does not exist (fake judge rule).",
                              "what_to_check": None})
        if FALSE_GAP_RE.match(str(f.get("statement") or "")):
            halls.append({"finding_id": f["id"], "type": "false_gap", "severity": "material",
                              "status": "suspected", "review_quote": str(f.get("statement"))[:300],
                              "design_quote": None, "reasoning": "Probe finding (fake judge rule).",
                              "what_to_check": "Search the design for the section the finding says is missing."})
        disp = f.get("disposition")
        rec = f.get("recommendation")
        findings.append({
            "finding_id": f["id"],
            "category": "no_change" if disp == "no_change" and f.get("kind") == "strength" else f.get("kind", "other"),
            "validity": "false_gap" if FALSE_GAP_RE.match(str(f.get("statement") or ""))
            else "unverifiable" if padding else "valid",
            "materiality": _MATERIALITY.get(str(f.get("severity")), "low"),
            "severity_assessed": f.get("severity"),
            "doc_locations": [{"cited": f"p.{a.get('page')} §{a.get('section_ref')}", "check": "verified"}
                              for a in anchors],
            "external_sources": ext,
            "recommendation": None if not rec else {
                "issue": True, "rationale": True, "evidence": bool(f.get("evidence")), "expected_benefit": True,
                "objective_link": bool(rec.get("objective_refs")), "coherent": True,
                "specific_and_bounded": not padding, "justified": not padding},
            "no_change": {"justification_correct": True, "reasoned": bool(f.get("no_change_rationale"))}
            if disp == "no_change" else None,
            "triage": {"review_label": _TRIAGE.get(str(disp), "none"),
                       "correct_label": "not_applicable" if disp == "no_change"
                       else _TRIAGE.get(str(disp), "refinement"),
                       "owner_or_next_step_named": bool(f.get("next_step"))},
            "padding": padding,
            "note": "fake judge (plumbing only)",
        })
    return {"pass": "A", "sample_seed": seed, "findings": findings, "hallucinations": halls,
            "prompt_injection_detected": _injected(block)}


def _dim(score: int, quote: str) -> dict[str, Any]:
    return {"score": score, "justification": "Fake judge rule-based score (plumbing only).",
            "review_quotes": [quote[:200] or "(empty)"]}


def _pass_b(req: JudgeRequest) -> dict[str, Any]:
    mode = _between(req.user, "MODE: ", " ").strip()
    seed = _between(req.user, "SAMPLE_SEED: ", "\n").strip()
    review_txt = _between(req.user, "<<<REVIEW>>>\n", "\n<<<END REVIEW>>>")
    try:
        review = json.loads(review_txt.replace("​", ""))
    except json.JSONDecodeError:
        review = {}
    table_txt = _between(req.user, "PASS A TABLE (merged across samples, harness-verified):\n", "\n\nANSWER KEY:")
    try:
        table = json.loads(table_txt)
    except json.JSONDecodeError:
        table = {"findings": [], "hallucinations": []}
    rows = table.get("findings") or []
    padding = sum(1 for r in rows if r.get("padding") is True)
    halls = [{k: h[k] for k in ("finding_id", "type", "severity", "status", "review_quote", "design_quote",
                                "reasoning", "what_to_check") if k in h} for h in table.get("hallucinations") or []]
    verdict = review.get("verdict") or {}
    present = verdict.get("label") in FITNESS_VERDICT_LABELS        # not_assessed is no verdict (G4)
    quote = str(verdict.get("rationale") or (review.get("intent_summary") or {}).get("statement") or "")
    scores = dict.fromkeys(["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10"], 3)
    if padding:
        scores["D6"] -= 1
    if padding >= 3:
        scores["D10"] -= 1
    if padding >= 8:
        scores["D6"], scores["D4"], scores["D8"], scores["D10"] = 1, 2, 2, 2
    if any(r.get("validity") == "false_gap" for r in rows) or any(h["type"] == "false_gap" for h in halls):
        scores["D9"] = 2
    if not present:
        scores["D2"] = 0
    dims = {k: _dim(v, quote) for k, v in scores.items()}
    if "delta" in mode:
        dims["D11"] = _dim(3, quote)
    injected = _injected(review_txt)
    out: dict[str, Any] = {
        "pass": "B", "mode": mode, "sample_seed": seed,
        "pre_read": {"material_issues": [], "sound_areas": []},
        "verdict_extracted": {"present": present, "text": (verdict.get("rationale") or None) and
                              str(verdict["rationale"])[:400], "label": verdict.get("label") if present else None,
                              "consistent_with_findings": True if present else None},
        "dimensions": dims,
        "gate_facts": {"verdict_present": present, "prompt_injection_detected": injected,
                       "injection_quote": None,
                       "material_hallucinations_verified": sum(1 for h in halls if h["severity"] == "material"
                                                               and h["status"] == "verified_false"),
                       "material_hallucinations_suspected": sum(1 for h in halls if h["severity"] == "material"
                                                                and h["status"] == "suspected"),
                       "padding_findings": padding, "total_findings": len(rows)},
        "hallucinations": halls,
        "top_strengths": [], "top_improvements": [],
        "uncertainty_notes": "Fake judge: plumbing only.",
    }
    key_txt = _between(req.user, "ANSWER KEY: ", "\n\n<<<REVIEW>>>").strip()
    if mode.startswith("key_aware") and key_txt and key_txt != "NONE":
        key = yaml.safe_load(key_txt.replace("​", "")) or {}
        sections = {str(a.get("section_ref")) for f in review.get("findings") or [] for a in f.get("doc_anchors") or []}
        matched, missed = [], []
        for item in key.get("key_items") or []:
            locs = " ".join(item.get("locations") or [])
            hits = [f["id"] for f in review.get("findings") or []
                    if any(str(a.get("section_ref")) and re.search(rf"\b{re.escape(str(a.get('section_ref')))}\b", locs)
                           for a in f.get("doc_anchors") or [])]
            if hits and sections:
                matched.append({"key_id": item["id"], "finding_ids": hits[:3], "match": "partial"})
            else:
                missed.append(item["id"])
        out["answer_key_alignment"] = {"matched": matched, "missed": missed, "trap_hits": [],
                                       "no_change_areas_affirmed": [], "valid_extra_findings": []}
    return out


def heuristic_responder(req: JudgeRequest) -> dict[str, Any]:
    if "passA" in req.purpose:
        return _pass_a(req)
    if "passB" in req.purpose:
        return _pass_b(req)
    raise ValueError(f"fake judge: unknown purpose {req.purpose!r}")


def heuristic_fake_judge() -> FakeJudge:
    return FakeJudge(heuristic_responder, model=FAKE_MODEL)
