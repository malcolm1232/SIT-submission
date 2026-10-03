"""Run directories read for the page. Read-only; the page writes nothing here.

Files read: ``report.json``, ``manifest.json``, ``ledger.json``, ``anchors.json``, ``progress.jsonl``,
``replay.json`` (only whether it exists), ``ui/launch.json`` and the reviewed PDF (checked against the
manifest's SHA-256 before it is served). Every number the page shows comes from one of these or
from the event stream.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from sit_review_agent.report.render import confidence_band
from sit_review_agent.ui import events

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
UI_DIR = "ui"
SEVERITIES = ("critical", "high", "medium", "low")
#: Delta groups in the order and with the headings of the design note, section 7.
DELTA_GROUPS = (("resolved", "fixed (resolved)"), ("partially_addressed", "partially addressed"),
                ("still_open", "unchanged (still open)"), ("new_in_update", "new in update, including regressions"))


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run_path(runs_dir: Path, run_id: str) -> Path | None:
    """``runs_dir/run_id`` when ``run_id`` is a plain name of a directory inside ``runs_dir``."""
    if not RUN_ID_RE.match(run_id) or ".." in run_id:
        return None
    root = runs_dir.resolve()
    p = (root / run_id).resolve()
    if p.parent != root or not p.is_dir():
        return None
    return p


def is_run_dir(p: Path) -> bool:
    return p.is_dir() and any((p / n).is_file() for n in ("report.json", "progress.jsonl", "manifest.json")) \
        or (p / UI_DIR / "launch.json").is_file()


def _wall_and_cost(manifest: dict[str, Any] | None) -> tuple[float | None, float | None, bool]:
    if not isinstance(manifest, dict):
        return None, None, False
    extra = manifest.get("extra") or {}
    wall = ((extra.get("timing") or {}).get("wall_clock_s"))
    cost = (manifest.get("usage") or {}).get("cost_usd")
    lower = bool((extra.get("model") or {}).get("cost_usd_lower_bound"))
    return wall, cost, lower


def last_event(run_dir: Path) -> dict[str, Any] | None:
    evs = events.read_all(run_dir / "progress.jsonl")
    return evs[-1] if evs else None


def finished_event(run_dir: Path) -> dict[str, Any] | None:
    """The stream's final ``run_finished``: the last record, when it is one. A ``run_finished``
    with records after it ended a failed run that was then resumed, so it is not the end."""
    ev = last_event(run_dir)
    return ev if ev is not None and ev.get("type") == events.FINISHED else None


def run_status(run_dir: Path, *, process_alive: bool = False) -> str:
    """``running`` while a launched process lives or the stream has not finished and no report
    exists; ``finished`` once a report exists; ``ended`` for a stream that finished with no report
    or a run that left neither."""
    has_report = (run_dir / "report.json").is_file()
    if process_alive:
        return "running"
    if has_report:
        return "finished"
    if (run_dir / "progress.jsonl").is_file() and finished_event(run_dir) is None:
        return "running"
    return "ended"


def summary(run_dir: Path, *, process_alive: bool = False) -> dict[str, Any]:
    """One row of the runs table, and the head of a run page."""
    report = read_json(run_dir / "report.json")
    manifest = read_json(run_dir / "manifest.json")
    launch = read_json(run_dir / UI_DIR / "launch.json")
    wall, cost, lower = _wall_and_cost(manifest)
    started = events.started(events.read_all(run_dir / "progress.jsonl"))
    mode = (started or {}).get("mode") or ((manifest or {}).get("extra") or {}).get("mode")
    row: dict[str, Any] = {"run_id": run_dir.name, "status": run_status(run_dir, process_alive=process_alive),
                           "has_report": report is not None, "has_events": (run_dir / "progress.jsonl").is_file(),
                           "mode": mode,
                           "replayed": (run_dir / "replay.json").is_file() or mode == "replay",
                           "resumed": bool((started or {}).get("resumed")),
                           "wall_s": wall, "cost_usd": cost, "cost_lower_bound": lower,
                           "outcome": (manifest or {}).get("outcome"),
                           "commit": (manifest or {}).get("git_commit"),
                           "argv": (launch or {}).get("display"),
                           "document": None, "pages": None, "verdict": None, "confidence": None,
                           "findings": None, "mtime": run_dir.stat().st_mtime}
    if isinstance(report, dict):
        docs = (report.get("metadata") or {}).get("documents") or []
        doc = next((d for d in docs if d.get("role") == "under_review"), docs[0] if docs else {})
        verdict = report.get("verdict") or {}
        row.update(document=doc.get("title"), pages=doc.get("page_count"), verdict=verdict.get("label"),
                   confidence=verdict.get("confidence"), findings=len(report.get("findings") or []))
    else:
        doc = events.under_review(started)
        row["document"] = doc.get("title") or (launch or {}).get("document_name")
        row["pages"] = doc.get("pages")
    return row


def list_runs(runs_dir: Path, *, alive: set[str] | None = None) -> list[dict[str, Any]]:
    if not runs_dir.is_dir():
        return []
    rows = [summary(p, process_alive=p.name in (alive or set())) for p in runs_dir.iterdir()
            if RUN_ID_RE.match(p.name) and is_run_dir(p)]
    return sorted(rows, key=lambda r: r["mtime"], reverse=True)


# ------------------------------------------------------------------ the reviewed PDF


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def reviewed_pdf(run_dir: Path, repo_root: Path) -> Path | None:
    """The PDF this run reviewed, only when its SHA-256 equals the one the manifest recorded:
    the UI's own upload (``ui/launch.json``), else the input argument of the recorded command."""
    manifest = read_json(run_dir / "manifest.json") or {}
    extra = manifest.get("extra") or {}
    doc = extra.get("doc") or {}
    want = doc.get("sha256_pdf")
    cands: list[Path] = []
    launch = read_json(run_dir / UI_DIR / "launch.json") or {}
    if launch.get("document"):
        cands.append(Path(launch["document"]))
    argv = (extra.get("code") or {}).get("argv") or []
    if len(argv) >= 2 and argv[0] in ("run", "review") and not str(argv[1]).startswith("-"):
        cands.append(Path(argv[1]))
    for c in cands:
        p = c if c.is_absolute() else repo_root / c
        if p.suffix.lower() == ".pdf" and p.is_file() and want and _sha256_file(p) == want:
            return p
    return None


# ------------------------------------------------------------------ the review payload


def _anchor_rows(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    doc = read_json(run_dir / "anchors.json") or {}
    rows = doc.get("rows", []) if isinstance(doc, dict) else doc
    by_owner: dict[str, list[dict[str, Any]]] = {}
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and r.get("owner_id"):
            keep = {k: r.get(k) for k in ("anchor_index", "page", "section_ref", "anchor_status", "method", "score",
                                          "matched_page", "char_start", "char_end", "doc_id")}
            by_owner.setdefault(r["owner_id"], []).append(keep)
    return by_owner


def counts(report: dict[str, Any]) -> dict[str, int]:
    """The counts strip: every number is a length of a list in ``report.json``."""
    findings = report.get("findings") or []
    issues = [f for f in findings if f.get("kind") != "strength"]
    out = {"findings": len(findings)}
    for s in SEVERITIES:
        out[s] = sum(1 for f in issues if f.get("severity") == s)
    out["strengths"] = sum(1 for f in findings if f.get("kind") == "strength")
    out["sound_areas"] = len(report.get("sound_areas") or [])
    out["unresolved"] = len(report.get("unresolved") or [])
    out["limitations"] = len(report.get("limitations") or [])
    return out


def delta_groups(report: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Findings grouped by ``reassessment.status``; ``None`` when no finding has a reassessment
    (the page then hides the Delta view)."""
    findings = [f for f in report.get("findings") or [] if isinstance(f.get("reassessment"), dict)]
    if not findings:
        return None
    return [{"status": s, "heading": h, "finding_ids": [f["id"] for f in findings
                                                       if f["reassessment"].get("status") == s]}
            for s, h in DELTA_GROUPS]


def previous_verdict(run_dir: Path, runs_dir: Path) -> dict[str, Any] | None:
    manifest = read_json(run_dir / "manifest.json") or {}
    prev = (manifest.get("extra") or {}).get("previous_run_id")
    if not prev:
        return None
    p = run_path(runs_dir, str(prev))
    rep = read_json(p / "report.json") if p else None
    v = (rep or {}).get("verdict") if isinstance(rep, dict) else None
    return {"run_id": prev, "label": v.get("label"), "confidence": v.get("confidence")} if v else None


def review_payload(run_dir: Path, runs_dir: Path, repo_root: Path) -> dict[str, Any] | None:
    """``report.json`` unchanged under ``report``, and beside it only what the page joins from
    other run files or derives by counting (``derived``)."""
    report = read_json(run_dir / "report.json")
    if not isinstance(report, dict):
        return None
    findings = report.get("findings") or []
    verdict = report.get("verdict") or {}
    derived = {
        "counts": counts(report),
        "verdict_band": confidence_band(float(verdict["confidence"]))
        if isinstance(verdict.get("confidence"), int | float) else None,
        "finding_bands": {f["id"]: confidence_band(float(f["confidence"])) for f in findings
                          if isinstance(f.get("confidence"), int | float)},
        "anchors": _anchor_rows(run_dir),
        "delta": delta_groups(report),
        "previous_verdict": previous_verdict(run_dir, runs_dir),
        "pdf_available": reviewed_pdf(run_dir, repo_root) is not None,
    }
    return {"report": report, "derived": derived, "summary": summary(run_dir)}
