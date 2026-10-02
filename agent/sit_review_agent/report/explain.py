"""``sit-review explain <run_dir> <finding_id>`` (runbook §5.1, robustness DEMO-06).

Reads only the run directory (works offline and in replay; < 5 s). Shows, for one finding:
the finding as reported; each doc anchor with page, section, quote, match method/score and
character span (``anchors.json``); each evidence item with its ledger entry and, for external
evidence, the tool call (server, tool, arguments, retrieval time, snapshot path) from
``tools.jsonl``; the criterion(s) that produced it and its history across phases with the
``llm.jsonl`` call IDs (``state.json`` ``finding_meta``); registry relations and checks.

Files read: ``report.json``, ``anchors.json``, ``ledger.json`` (``ledger.jsonl`` if the snapshot
is missing), ``tools.jsonl``, ``llm.jsonl``, ``state.json`` and ``effective_config.json`` (for the
criterion text). Nothing else, and no network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sit_review_agent.rundir import JsonlWriter


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
    # Extra context (not in the frozen field list above, all optional):
    run_id: str = ""
    verdict_refs: list[str] = field(default_factory=list)                 # where the verdict cites the finding
    llm_call_details: list[dict[str, Any]] = field(default_factory=list)  # {call_id, phase, model, purpose}
    text_paths: dict[str, str] = field(default_factory=dict)              # doc_id -> run-relative text path


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def explain(run_dir: str | Path, finding_id: str) -> ExplainRecord:
    """Join ``report.json``, ``anchors.json``, ``ledger.json``, ``tools.jsonl`` and ``state.json``
    for ``finding_id``. Raises ``KeyError`` if the finding is not in the report."""
    root = Path(run_dir)
    report = _read_json(root / "report.json", None)
    if report is None:
        raise KeyError(f"{root}/report.json not found")
    finding = next((f for f in report.get("findings", []) if f.get("id") == finding_id), None)
    if finding is None:
        raise KeyError(finding_id)

    state = _read_json(root / "state.json", {})
    meta = (state.get("finding_meta") or {}).get(finding_id) or {}
    cfg = _read_json(root / "effective_config.json", {})
    criteria_cfg = {c.get("id"): c for c in ((cfg.get("criteria") or {}).get("criteria") or [])}
    criteria = [{"id": cid, "question": (criteria_cfg.get(cid) or {}).get("question", "(not in the run's config)"),
                 "lab_ref": (criteria_cfg.get(cid) or {}).get("lab_ref")} for cid in meta.get("criterion_ids", [])]

    anchors_doc = _read_json(root / "anchors.json", {})
    rows = anchors_doc.get("rows", anchors_doc) if isinstance(anchors_doc, dict) else anchors_doc
    anchors = [r for r in rows if r.get("owner_id") == finding_id]

    ledger_list = _read_json(root / "ledger.json", None)
    if ledger_list is None:
        ledger_list = JsonlWriter(root / "ledger.jsonl").read()
    ledger = {e["evidence_id"]: e for e in ledger_list}
    tool_rows: dict[str, dict[str, Any]] = {}
    for e in JsonlWriter(root / "tools.jsonl").read():
        cid = e.get("call_id")
        if cid and cid not in tool_rows:
            tool_rows[cid] = e

    evidence: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    checks: list[str] = []
    for item in finding.get("evidence", []):
        le = ledger.get(item["evidence_id"])
        if le is None:
            checks.append(f"{item['evidence_id']}: NOT IN LEDGER")
            continue
        evidence.append({**le, "cited_as": item})
        tool = le.get("tool")
        if tool:
            row = tool_rows.get(tool.get("call_id"))
            if row is not None and row not in tool_calls:
                tool_calls.append(row)
            if row is None:
                checks.append(f"{le['evidence_id']}: tool call {tool.get('call_id')} not in tools.jsonl")
        if le.get("source_type") == "external":
            checks.append(f"{le['evidence_id']}: read_before_cite {'ok' if le.get('read_before_cite') else 'NO'}")

    llm_by_id: dict[str, dict[str, Any]] = {}
    for e in JsonlWriter(root / "llm.jsonl").read():
        if e.get("call_id") and e.get("outcome", "ok") == "ok":
            llm_by_id.setdefault(e["call_id"], e)
    history = [{"phase": meta.get("created_phase"), "call_id": meta.get("created_call_id"), "changed_fields": {},
                "note": "created"}] if meta else []
    history += list(meta.get("history") or [])
    calls = [c for c in dict.fromkeys([meta.get("created_call_id"), *[h.get("call_id") for h in history],
                                       meta.get("last_call_id")]) if c]
    details = [{"call_id": c, "phase": (llm_by_id.get(c) or {}).get("phase"), "model": (llm_by_id.get(c) or {}).get(
        "model"), "purpose": (llm_by_id.get(c) or {}).get("purpose")} for c in calls]

    registry = {e["registry_id"]: e for e in report.get("decision_registry", [])}
    reg = [{**registry.get(a["registry_id"], {"registry_id": a["registry_id"]}), "relation": a["relation"],
            "justification": a["justification"]} for a in finding.get("affected_decisions", [])]

    n_ok = sum(1 for a in anchors if a.get("anchor_status") in ("resolved", "repaired"))
    n_bad = sum(1 for a in anchors if a.get("anchor_status") == "unresolved")
    checks.insert(0, f"anchors {n_ok}/{len(finding.get('doc_anchors', []))} in the report verified"
                  + (f"; {n_bad} unresolved anchor(s) dropped in verify" if n_bad else ""))
    challenges = [a for a in finding.get("affected_decisions", []) if a.get("relation") == "challenges"]
    checks.append(f"registry: challenges {', '.join(a['registry_id'] for a in challenges)} (labelled)"
                  if challenges else "registry: no challenge to an approved decision")
    unresolved_refs = [u["text"] for u in report.get("unresolved", []) if finding_id in u.get("finding_ids", [])]
    if unresolved_refs:
        checks.append("listed in unresolved: " + " | ".join(unresolved_refs))
    verdict = report.get("verdict") or {}
    vrefs = [f"condition: {c['text']}" for c in verdict.get("conditions", []) if finding_id in c.get("finding_ids", [])]
    vrefs += [f"objective {o['objective_ref']}: {o['label']}" for o in verdict.get("per_objective", [])
              if finding_id in o.get("finding_ids", [])]
    texts = {d["doc_id"]: d["text_path"] for d in (report.get("metadata") or {}).get("documents", [])}
    return ExplainRecord(finding=finding, criteria=criteria, anchors=anchors, evidence=evidence, tool_calls=tool_calls,
                         history=history, llm_calls=calls, registry=reg, checks=checks,
                         run_id=(report.get("metadata") or {}).get("run_id", root.name), verdict_refs=vrefs,
                         llm_call_details=details, text_paths=texts)


def _q(text: Any) -> str:
    return " ".join(str(text or "").split())


def format_explain(record: ExplainRecord) -> str:
    """Human-readable text in the runbook §5.1 order."""
    f = record.finding
    out: list[str] = []
    sev = f.get("severity") or "n/a"
    out.append(f"{f['id']} ({f['kind']}, severity {sev}, disposition: {f['disposition']}, rank {f['rank']}, "
               f"confidence {f['confidence']:.2f})  run {record.run_id}")
    out.append(f"  {_q(f['title'])}")
    out.append(f"  {_q(f['statement'])}")
    out.append("  Verdict impact: " + ("; ".join(record.verdict_refs) if record.verdict_refs
                                       else "not cited by the verdict"))
    out.append("")
    out.append("1. Document anchors")
    for i, a in enumerate(f.get("doc_anchors", [])):
        cands = [r for r in record.anchors if r.get("anchor_status") != "unresolved"
                 and r.get("page") == a.get("page") and r.get("section_ref") == a.get("section_ref")]
        row = next((r for r in cands if r.get("anchor_index") == i), cands[0] if cands else None)
        out.append(f"  [{i + 1}] {a['doc_id']} p.{a.get('page')} §{a['section_ref']}"
                   + (f" ({', '.join(a['requirement_ids'])})" if a.get("requirement_ids") else ""))
        out.append(f"      \"{_q(a['quote'])}\"")
        if row is not None:
            span = f"chars {row.get('char_start')}-{row.get('char_end')} in {record.text_paths.get(a['doc_id'], '?')}"
            out.append(f"      {row['anchor_status']}: {row.get('method')} match, score {row.get('score')}, "
                       f"matched page {row.get('matched_page')}, {span}")
        else:
            out.append("      (no anchors.json row)")
    for r in record.anchors:
        if r.get("anchor_status") == "unresolved":
            out.append(f"  [dropped] p.{r.get('page')} §{r.get('section_ref')}: unresolved "
                       f"({', '.join(r.get('reasons') or [])})")
    out.append("")
    out.append("2-3. Evidence (ledger) and the tool calls behind it")
    if not record.evidence:
        out.append("  none cited")
    calls = {c.get("call_id"): c for c in record.tool_calls}
    for e in record.evidence:
        cited = e["cited_as"]
        out.append(f"  {e['evidence_id']} {e['source_type']}{' (' + e['authority'] + ')' if e.get('authority') else ''}"
                   f", {'supports' if cited.get('supports_claim') else 'contrary'}: {e['url_or_citation']}")
        if cited.get("quote"):
            out.append(f"      quote: \"{_q(cited['quote'])}\"")
        if e.get("title"):
            out.append(f"      title: {_q(e['title'])}")
        if e.get("retrieved_at"):
            out.append(f"      retrieved: {e['retrieved_at']}")
        if e.get("snapshot_path"):
            out.append(f"      snapshot: {e['snapshot_path']}")
        if e.get("excerpt") and e["source_type"] != "inference":
            out.append(f"      snippet as seen: \"{_q(e['excerpt'])[:300]}\"")
        if e["source_type"] == "inference":
            src = ", ".join(e.get("derived_from") or [])
            out.append(f"      inference: \"{_q(e.get('excerpt'))}\" derived from {src}")
        tool = e.get("tool")
        if tool:
            c = calls.get(tool.get("call_id"))
            if c is None:
                out.append(f"      tool call {tool.get('call_id')}: {tool.get('server')}/{tool.get('tool_name')} "
                           "(not in tools.jsonl)")
            else:
                out.append(f"      tool call {c['call_id']}: {c.get('server')}/{c.get('tool')} "
                           f"args {json.dumps(c.get('args'), sort_keys=True)} status {c.get('status')} "
                           f"at {c.get('started_at')}{' (replayed)' if c.get('replayed') else ''}")
    out.append("")
    out.append("4. Criteria that produced it")
    for c in record.criteria or [{"id": "(none recorded)", "question": "", "lab_ref": None}]:
        out.append(f"  {c['id']}: {_q(c['question'])}" + (f" (lab {c['lab_ref']})" if c.get("lab_ref") else ""))
    out.append("")
    out.append("5. History")
    for h in record.history:
        changed = h.get("changed_fields") or {}
        diff = "; ".join(f"{k}: {v[0]!r} -> {v[1]!r}" if isinstance(v, list) and len(v) == 2 else f"{k}: {v!r}"
                         for k, v in changed.items())
        out.append(f"  {h.get('phase')} ({h.get('call_id') or 'no model call'}): {h.get('note') or ''}"
                   + (f" [{diff}]" if diff else ""))
    prov = f.get("provenance") or {}
    out.append(f"  provenance: phase {prov.get('phase')}, iteration {prov.get('iteration')}, "
               f"model {prov.get('model')}, prompt {str(prov.get('prompt_hash'))[:12]}")
    out.append("  LLM calls: " + (", ".join(
        f"{d['call_id']} ({d.get('phase') or '?'}{', ' + d['purpose'] if d.get('purpose') else ''}, "
        f"{d.get('model') or '?'})" for d in record.llm_call_details) or "none recorded"))
    out.append("")
    out.append("6. Checks")
    for c in record.checks:
        out.append(f"  {c}")
    for r in record.registry:
        out.append(f"  decision {r.get('registry_id')} {r.get('doc_ref', '')}: {r['relation']}: "
                   f"{_q(r['justification'])}")
    return "\n".join(out)
