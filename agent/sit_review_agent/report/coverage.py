"""``dra coverage [--run runs/<id>]``: the criteria x sections coverage map of a run (runbook §5).

Reads only the run directory (offline, well under 5 s). Rows are the document's sections (rolled
up to ``depth`` levels of the section number, so ``4.1`` and ``4.3`` count under ``4``), columns
are the configured review criteria, in config order. A cell is:

* ``nX``: ``n`` reported findings for this criterion anchored in this section; ``X`` is the worst
  severity (C critical, H high, M medium, L low; S when they are all strengths, which have none);
* ``ok``: "checked, no issue" here: the criterion was reported as checked for the whole document
  (coverage outcome ``findings`` or ``no_issue``) and no finding for it is anchored in this section;
* ``?``: the criterion raised findings but none of them is in the report (verify could not confirm
  their anchors, or a code check dropped them), so no section can be called clear for it;
* ``-``: the criterion was reported not applicable, was not assessed (a run with no assessment), or
  was not reported as checked at all.

The ``SA`` column lists the sound areas (sections checked and found sound) in each row.

Sources, all in the run directory: ``report.json`` (findings, anchors, sound areas, criteria);
the coverage rows and finding-to-criterion links from ``state.json`` (or the latest checkpoint);
the section list from ``text/<doc_id>.sections.json``. A run directory that only keeps the report
(as ``docs/live_runs/`` does) falls back to the coverage table in ``report.md`` and to the section
references the report itself cites; the output says which sources were used.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sit_review_agent.state.checkpoint import checkpoint_file_order

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}
SEVERITY_LETTER = {"critical": "C", "high": "H", "medium": "M", "low": "L"}
CHECKED = ("findings", "no_issue")
LEGEND = ("nX = n findings for this criterion anchored in this section, worst severity X (C critical, "
          "H high, M medium, L low; S strength, no severity); ok = checked, no issue in this section "
          "(criterion checked for the whole document, no finding anchored here); ? = the criterion raised "
          "findings that could not be verified and are not in the report, so no section is cleared (see the "
          "report's unresolved items); - = not applicable, not assessed or not reported as checked; "
          "SA = sound areas")
#: How ``assess`` starts the note of every coverage row when the run produced no assessment.
NOT_ASSESSED_NOTE = "not assessed"


@dataclass
class CoverageRow:
    key: str
    heading: str
    cells: dict[str, str] = field(default_factory=dict)          # criterion_id -> cell text
    findings: dict[str, list[str]] = field(default_factory=dict)  # criterion_id -> finding IDs
    sound_areas: list[str] = field(default_factory=list)


@dataclass
class CoverageMap:
    run_id: str
    title: str
    verdict: str
    criteria: list[str]
    outcomes: dict[str, str]                     # criterion_id -> findings | no_issue | not_applicable | not reported
    criterion_findings: dict[str, list[str]]
    notes: dict[str, str]
    rows: list[CoverageRow]
    unanchored: list[str]                        # findings with no anchor in the document under review
    depth: int
    sources: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "title": self.title, "verdict": self.verdict, "criteria": self.criteria,
                "outcomes": self.outcomes, "criterion_findings": self.criterion_findings, "notes": self.notes,
                "depth": self.depth, "sources": self.sources, "unanchored_findings": self.unanchored,
                "rows": [{"section": r.key, "heading": r.heading, "cells": r.cells, "findings": r.findings,
                          "sound_areas": r.sound_areas} for r in self.rows]}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _state(root: Path) -> tuple[dict[str, Any], str]:
    st = _read_json(root / "state.json")
    if isinstance(st, dict):
        return st, "state.json"
    files = sorted((root / "checkpoints").glob("[0-9][0-9]-*.json")) if (root / "checkpoints").is_dir() else []
    files.sort(key=checkpoint_file_order)            # latest by ordinal, not by file name (stage 1 ends in any order)
    if files:
        ck = _read_json(files[-1])
        if isinstance(ck, dict) and isinstance(ck.get("state"), dict):
            return ck["state"], f"checkpoints/{files[-1].name}"
    return {}, ""


def coverage_rows_from_markdown(md: str) -> list[dict[str, Any]]:
    """The "Review coverage" table of a rendered ``report.md`` as coverage rows."""
    out: list[dict[str, Any]] = []
    lines = md.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip().lower() == "## review coverage")
    except StopIteration:
        return out
    for ln in lines[start + 1:]:
        if ln.startswith("## "):
            break
        cells = [c.strip() for c in ln.strip().strip("|").split("|")] if ln.strip().startswith("|") else []
        if len(cells) < 3 or cells[0] in ("Criterion", "") or set(cells[0]) <= {"-"}:
            continue
        ids = [] if cells[2] in ("-", "") else [x.strip() for x in cells[2].split(",") if x.strip()]
        out.append({"criterion_id": cells[0], "outcome": cells[1].replace(" ", "_"), "finding_ids": ids,
                    "note": cells[3] if len(cells) > 3 else ""})
    return out


def section_key(ref: str, depth: int) -> str:
    """``4.3.2`` -> ``4`` at depth 1, ``4.3`` at depth 2; a non-numbered reference is its own key."""
    ref = (ref or "").strip()
    if depth <= 0 or not re.match(r"^[A-Za-z0-9]+(\.[A-Za-z0-9]+)*$", ref):
        return ref
    return ".".join(ref.split(".")[:depth])


def _natural(key: str) -> list[Any]:
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"[.\s]+", key)]


def build_coverage(run_dir: str | Path, *, depth: int = 1) -> CoverageMap:
    """The coverage map of ``run_dir``. Raises ``FileNotFoundError`` without ``report.json``."""
    root = Path(run_dir)
    report = _read_json(root / "report.json")
    if not isinstance(report, dict):
        raise FileNotFoundError(f"{root}/report.json not found or unreadable")
    sources = ["report.json"]
    state, state_src = _state(root)
    cfg = _read_json(root / "effective_config.json") or {}
    criteria = [c.get("id") for c in ((cfg.get("criteria") or {}).get("criteria") or []) if c.get("id")]
    if not criteria:
        criteria = list(((report.get("run_manifest") or {}).get("review_config") or {}).get("criteria") or [])
    rows = list(state.get("coverage") or [])
    if rows:
        sources.append(f"{state_src} (coverage)")
    elif (root / "report.md").is_file():
        rows = coverage_rows_from_markdown((root / "report.md").read_text(encoding="utf-8"))
        if rows:
            sources.append("report.md (coverage table; no state.json in this run directory)")
    for r in rows:
        if r.get("criterion_id") and r["criterion_id"] not in criteria:
            criteria.append(r["criterion_id"])

    findings = {f["id"]: f for f in report.get("findings") or [] if f.get("id")}
    by_criterion: dict[str, list[str]] = {c: [] for c in criteria}
    outcomes: dict[str, str] = {c: "not reported" for c in criteria}
    notes: dict[str, str] = {}
    for r in rows:
        cid = r.get("criterion_id")
        if cid not in by_criterion:
            continue
        outcomes[cid] = str(r.get("outcome") or "not reported")
        notes[cid] = str(r.get("note") or "")
        by_criterion[cid] += [i for i in r.get("finding_ids") or [] if i in findings]
    for fid, meta in (state.get("finding_meta") or {}).items():
        for cid in (meta or {}).get("criterion_ids") or []:
            if fid in findings and cid in by_criterion:
                by_criterion[cid].append(fid)
    by_criterion = {c: list(dict.fromkeys(ids)) for c, ids in by_criterion.items()}

    docs = (report.get("metadata") or {}).get("documents") or []
    under = next((d for d in docs if d.get("role") == "under_review"), docs[0] if docs else {})
    doc_id = under.get("doc_id")
    order: list[str] = []
    headings: dict[str, str] = {}
    sections = _read_json(root / "text" / f"{doc_id}.sections.json") if doc_id else None
    if isinstance(sections, dict) and sections.get("sections"):
        sources.append(f"text/{doc_id}.sections.json")
        for s in sorted(sections["sections"], key=lambda s: s.get("order", 0)):
            sid = str(s.get("section_id") or "")
            key = section_key(sid, depth)
            if not key:
                continue
            if key not in headings:
                order.append(key)
                headings[key] = str(s.get("heading") or "") if sid == key else ""
            elif sid == key and not headings[key]:
                headings[key] = str(s.get("heading") or "")
            if not headings[key] and s.get("heading"):
                headings[key] = f"({s['heading']})"

    def anchored_keys(anchors: list[dict[str, Any]]) -> list[str]:
        return list(dict.fromkeys(section_key(str(a.get("section_ref") or ""), depth) for a in anchors
                                  if a.get("section_ref") and (doc_id is None or a.get("doc_id") in (None, doc_id))))

    finding_keys = {fid: anchored_keys(f.get("doc_anchors") or []) for fid, f in findings.items()}
    sa_keys = {s["id"]: list(dict.fromkeys([*anchored_keys(s.get("doc_anchors") or []),
                                             *(section_key(x, depth) for x in s.get("section_refs") or [])]))
               for s in report.get("sound_areas") or [] if s.get("id")}
    extra = sorted({k for ks in [*finding_keys.values(), *sa_keys.values()] for k in ks} - set(order), key=_natural)
    order += extra

    out_rows: list[CoverageRow] = []
    for key in order:
        row = CoverageRow(key=key, heading=headings.get(key, ""))
        row.sound_areas = [sid for sid, ks in sa_keys.items() if key in ks]
        for cid in criteria:
            here = [fid for fid in by_criterion[cid] if key in finding_keys.get(fid, [])]
            row.findings[cid] = here
            if here:
                row.cells[cid] = f"{len(here)}{_worst(findings[f] for f in here)}"
            elif outcomes.get(cid) == "findings" and not by_criterion[cid]:
                row.cells[cid] = "?"            # raised, but nothing verified: not "checked, no issue"
            elif outcomes.get(cid) in CHECKED:
                row.cells[cid] = "ok"
            else:
                row.cells[cid] = "-"
        out_rows.append(row)
    verdict = (report.get("verdict") or {}).get("label") or "?"
    return CoverageMap(run_id=str((report.get("metadata") or {}).get("run_id") or root.name),
                       title=str(under.get("title") or doc_id or ""), verdict=str(verdict), criteria=criteria,
                       outcomes=outcomes, criterion_findings=by_criterion, notes=notes, rows=out_rows,
                       unanchored=[fid for fid, ks in finding_keys.items() if not ks], depth=depth, sources=sources)


def _worst(findings: Any) -> str:
    """Letter of the worst severity among ``findings``; ``S`` when all are strengths (no severity)."""
    fs = list(findings)
    sevs = [f.get("severity") for f in fs if f.get("severity")]
    if sevs:
        return SEVERITY_LETTER.get(max(sevs, key=lambda s: SEVERITY_ORDER.get(s, 0)), "?")
    return "S" if all(f.get("kind") == "strength" for f in fs) else "?"


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: max(0, n - 1)] + "~"


def format_coverage(cm: CoverageMap, *, label_width: int = 30) -> str:
    """Plain-text table for a terminal (about 80 columns with 11 criteria)."""
    n_findings = len({f for ids in cm.criterion_findings.values() for f in ids} | set(cm.unanchored))
    lines = [f"Coverage map: run {cm.run_id}",
             f"{_clip(cm.title, 70)} | verdict {cm.verdict} | {n_findings} finding(s) | "
             f"{len(cm.criteria)} criteria x {len(cm.rows)} section(s)"
             + (f" (section depth {cm.depth})" if cm.depth > 0 else " (every section)"), ""]
    cols = [f"C{i + 1}" for i in range(len(cm.criteria))]
    header = f"{'Section':<{label_width}} " + " ".join(f"{c:>3}" for c in cols) + "  SA"
    lines += [header, "-" * len(header)]
    for r in cm.rows:
        label = _clip(f"{r.key} {r.heading}".strip(), label_width)
        cells = " ".join(f"{r.cells[c]:>3}" for c in cm.criteria)
        lines.append(f"{label:<{label_width}} {cells}  {', '.join(r.sound_areas)}".rstrip())
    if not cm.rows:
        lines.append("(no sections found in the run directory)")
    lines += ["", "Criteria:"]
    for col, cid in zip(cols, cm.criteria, strict=True):
        ids = cm.criterion_findings.get(cid) or []
        outcome = cm.outcomes.get(cid, "not reported").replace("_", " ")
        note = " ".join((cm.notes.get(cid) or "").split())
        if ids:
            detail = f" ({len(ids)}: {_clip(', '.join(ids), 60)})"
        elif cm.outcomes.get(cid) == "findings":
            detail = " (none in the report: raised but not verified; see the report's unresolved items)"
        elif cm.outcomes.get(cid) == "not_applicable" and note.lower().startswith(NOT_ASSESSED_NOTE):
            outcome, detail = _clip(note, 80), ""        # a run with no assessment: not "not applicable"
        else:
            detail = ""
        lines.append(f"  {col:>3} {cid}: {outcome}{detail}")
    if cm.unanchored:
        lines.append(f"Findings with no section anchor: {', '.join(cm.unanchored)}")
    lines += ["", _wrap("Legend: " + LEGEND, 100), f"Sources: {', '.join(cm.sources)}"]
    return "\n".join(lines)


def _wrap(text: str, width: int) -> str:
    out: list[str] = []
    line = ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = "  " + word
        else:
            line = f"{line} {word}" if line else word
    if line:
        out.append(line)
    return "\n".join(out)
