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
import shlex
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sit_review_agent.report.render import confidence_band
from sit_review_agent.ui import events

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
UI_DIR = "ui"
SEVERITIES = ("critical", "high", "medium", "low")
#: Delta groups in the order and with the headings of the design note, section 7, plus the status a
#: prior finding the agent no longer asserts gets (``withdrawn_on_reassessment``, 2026-10-03).
DELTA_GROUPS = (("resolved", "fixed (resolved)"), ("partially_addressed", "partially addressed"),
                ("still_open", "unchanged (still open)"), ("withdrawn_on_reassessment", "withdrawn on re-assessment"),
                ("new_in_update", "new in update, including regressions"))
#: What the Delta tab says when the run has no previous version (it is shown disabled, never hidden).
NO_PREVIOUS = "No previous version was given for this run"
#: What it says for a delta run written before the delta table existed (2026-10-03).
NO_TABLE = ("This run was written before the delta table existed: it lists this review's findings by their "
            "re-assessment, and a prior finding that no finding carries forward is not shown, so the page cannot "
            "say whether every prior finding has a status.")


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


#: Lines of ``progress.log`` the log route returns at most on a first read (the page keeps as many).
LOG_TAIL = 200


def tail_log(path: Path, *, after: int = 0, tail: int = LOG_TAIL) -> dict[str, Any]:
    """The complete lines of ``path`` (``progress.log``) from byte ``after``: at most the last ``tail`` of them,
    and the byte offset after the last complete line, so the next call with ``after=offset`` follows the file.
    A last line without its newline is left for the next read (the writer is mid-line); an ``after`` past the
    end of the file (the file was replaced) starts over. Read-only, text only, nothing interpreted."""
    if not path.is_file():
        return {"exists": False, "lines": [], "offset": 0, "skipped": 0, "tail": tail}
    size = path.stat().st_size
    if after > size:
        after = 0
    with path.open("rb") as fh:
        fh.seek(after)
        data = fh.read()
    end = data.rfind(b"\n")
    if end < 0:
        return {"exists": True, "lines": [], "offset": after, "skipped": 0, "tail": tail}
    lines = data[:end].decode("utf-8", "replace").split("\n")
    return {"exists": True, "lines": lines[-tail:], "offset": after + end + 1, "skipped": max(0, len(lines) - tail),
            "tail": tail}


#: The most of ``ui/console.txt`` a run page shows for a run that wrote no event: its last lines and bytes.
CONSOLE_TAIL_LINES = 40
CONSOLE_TAIL_BYTES = 16 * 1024


def console_tail(run_dir: Path) -> dict[str, Any] | None:
    """The end of ``ui/console.txt`` (the launched child's stdout and stderr), or ``None`` without one: the
    last :data:`CONSOLE_TAIL_LINES` lines of its last :data:`CONSOLE_TAIL_BYTES`, the last line kept even
    without its newline (the process has ended), and whether earlier output was left out."""
    path = run_dir / UI_DIR / "console.txt"
    if not path.is_file():
        return None
    size = path.stat().st_size
    with path.open("rb") as fh:
        fh.seek(max(0, size - CONSOLE_TAIL_BYTES))
        data = fh.read()
    lines = data.decode("utf-8", "replace").splitlines()
    if size > CONSOLE_TAIL_BYTES and lines:
        lines = lines[1:]                    # the first line read may start mid-line
    cut = size > CONSOLE_TAIL_BYTES or len(lines) > CONSOLE_TAIL_LINES
    return {"file": f"{UI_DIR}/console.txt", "lines": lines[-CONSOLE_TAIL_LINES:], "truncated": cut, "bytes": size}


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


#: Record phases that are not a stage of the run (the sink's own lines and the open-calls status line).
NOT_A_STAGE = ("run", "model", "tools", "")


def progress_state(evs: list[dict[str, Any]]) -> dict[str, Any]:
    """What the rail shows for a run from its stream: ``stage`` (the phase of the last record that
    names a stage), ``run_s`` (the last record's run clock, else its sink clock) and ``open_calls``
    (calls opened and not yet closed). Every value is read from the records, nothing is estimated."""
    stage: str | None = None
    run_s: float | None = None
    opened: set[str] = set()
    for ev in evs:
        if ev.get("phase") not in NOT_A_STAGE:
            stage = ev["phase"]
        run_s = ev["run_s"] if ev.get("run_s") is not None else ev.get("t")
        f = ev.get("fields") or {}
        if ev.get("type") == "call_opened" and f.get("call_id"):
            opened.add(f["call_id"])
        elif ev.get("type") in ("call_closed", "call_cut") and f.get("call_id"):
            opened.discard(f["call_id"])
    return {"stage": stage, "run_s": run_s, "open_calls": len(opened)}


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
    evs = events.read_all(run_dir / "progress.jsonl")
    started = events.started(evs)
    extra = (manifest or {}).get("extra") or {}
    mode = (started or {}).get("mode") or extra.get("mode")
    stamps = (manifest or {}).get("timestamps") or {}
    row: dict[str, Any] = {"run_id": run_dir.name, "status": run_status(run_dir, process_alive=process_alive),
                           "has_report": report is not None, "has_events": (run_dir / "progress.jsonl").is_file(),
                           "mode": mode,
                           "replayed": (run_dir / "replay.json").is_file() or mode == "replay",
                           "resumed": bool((started or {}).get("resumed")),
                           "wall_s": wall, "cost_usd": cost, "cost_lower_bound": lower,
                           "outcome": (manifest or {}).get("outcome"),
                           "commit": (manifest or {}).get("git_commit"),
                           "argv": (launch or {}).get("display") or _argv_display(extra),
                           "started_at": (launch or {}).get("started_at") or stamps.get("start_utc"),
                           "profile": (launch or {}).get("profile") or (started or {}).get("profile"),
                           "no_tools": (launch or {}).get("no_tools"),
                           "model_calls": (extra.get("model") or {}).get("calls_logged"),
                           "document": None, "version": None, "pages": None, "verdict": None, "confidence": None,
                           "findings": None, "mtime": run_dir.stat().st_mtime,
                           **progress_state(evs)}
    if isinstance(report, dict):
        docs = (report.get("metadata") or {}).get("documents") or []
        doc = next((d for d in docs if d.get("role") == "under_review"), docs[0] if docs else {})
        verdict = report.get("verdict") or {}
        row.update(document=doc.get("title"), version=doc.get("version"), pages=doc.get("page_count"),
                   verdict=verdict.get("label"), confidence=verdict.get("confidence"),
                   findings=len(report.get("findings") or []))
    else:
        doc = events.under_review(started)
        row["document"] = doc.get("title") or (launch or {}).get("document_name")
        row["pages"] = doc.get("pages")
    # A run that ended before its first event (a usage error, a missing key) left only its console output:
    # the run page shows the process's own message instead of an empty timeline.
    row["console"] = console_tail(run_dir) if not row["has_events"] and row["status"] != "running" else None
    row["launched_here"] = launch is not None
    return row


def _argv_display(extra: dict[str, Any]) -> str | None:
    """The command of a run started in a terminal, as its manifest recorded it (``dra`` + argv)."""
    argv = (extra.get("code") or {}).get("argv")
    if not isinstance(argv, list) or not argv:
        return None
    return "dra " + shlex.join(str(a) for a in argv)


def list_runs(runs_dir: Path, *, alive: set[str] | None = None) -> list[dict[str, Any]]:
    if not runs_dir.is_dir():
        return []
    rows = [summary(p, process_alive=p.name in (alive or set())) for p in runs_dir.iterdir()
            if RUN_ID_RE.match(p.name) and is_run_dir(p)]
    return sorted(rows, key=lambda r: r["mtime"], reverse=True)


# ------------------------------------------------------------------ the tool servers, as the newest run recorded them


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _iso_plus(base: str | None, seconds: float | None) -> str | None:
    """``base`` (an ISO-8601 UTC stamp) plus ``seconds``, as the same kind of stamp; None without a base."""
    if not base or seconds is None:
        return None
    try:
        t0 = datetime.fromisoformat(str(base).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t0 + timedelta(seconds=float(seconds))).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


#: ``mcp_warmup`` outcomes that are a warm-up: ``none`` and ``skipped`` say no warm-up was attempted
#: (a document-only run, a transport without one), so such a run never stands for the servers' state.
WARMUP_ATTEMPTED = ("done", "failed")


def _has_tool_records(run_dir: Path) -> bool:
    if (run_dir / "tools_list.jsonl").is_file():
        return True
    return any(ev.get("type") == "mcp_warmup" and (ev.get("fields") or {}).get("status") in WARMUP_ATTEMPTED
               for ev in events.read_all(run_dir / "progress.jsonl"))


def tools_status(runs_dir: Path, servers: list[dict[str, Any]]) -> dict[str, Any]:
    """One row per configured server from the newest run directory that recorded a warm-up: whether
    the server answered ``tools/list`` (``warm``), when (``at``), how many tools it listed, the
    ``mcp_warmup`` outcome, and its calls in that run. A read of files: no probe, no network.
    "Warm" therefore means "answered the last recorded warm-up", never "awake now"."""
    newest: Path | None = None
    if runs_dir.is_dir():
        cands = [p for p in runs_dir.iterdir() if RUN_ID_RE.match(p.name) and is_run_dir(p) and _has_tool_records(p)]
        newest = max(cands, key=lambda p: p.stat().st_mtime) if cands else None
    listed: dict[str, int] = {}
    listed_at: str | None = None
    warmup: dict[str, Any] | None = None
    warm_at: str | None = None
    calls: dict[str, dict[str, int]] = {}
    no_tools = False
    if newest is not None:
        for rec in _read_jsonl(newest / "tools_list.jsonl"):
            listed_at = rec.get("listed_at") or listed_at
            for t in rec.get("tools") or []:
                if isinstance(t, dict) and t.get("server"):
                    listed[t["server"]] = listed.get(t["server"], 0) + 1
        evs = events.read_all(newest / "progress.jsonl")
        wu = next((ev for ev in evs if ev.get("type") == "mcp_warmup"), None)
        if wu is not None:
            warmup = dict(wu.get("fields") or {})
            manifest = read_json(newest / "manifest.json") or {}
            launch = read_json(newest / UI_DIR / "launch.json") or {}
            base = ((manifest.get("timestamps") or {}).get("start_utc")) or launch.get("started_at")
            warm_at = _iso_plus(base, wu.get("t"))
        started = events.started(evs) or {}
        no_tools = started.get("transport") == "none" or bool((read_json(newest / UI_DIR / "launch.json") or {})
                                                              .get("no_tools"))
        for rec in _read_jsonl(newest / "tools.jsonl"):
            srv = rec.get("server")
            if not srv:
                continue
            c = calls.setdefault(srv, {"ok": 0, "failed": 0})
            c["failed" if rec.get("is_error") else "ok"] += 1
    rows = []
    for s in servers:
        name, enabled = s["name"], bool(s.get("enabled"))
        n = listed.get(name)
        warm: bool | None = None
        if enabled and newest is not None:
            warm = n is not None and n > 0
        c = calls.get(name, {})
        rows.append({"name": name, "enabled": enabled, "warm": warm,
                     "at": (listed_at or warm_at) if warm else None,
                     "tools": n, "status": (warmup or {}).get("status") if enabled and newest is not None else None,
                     "calls_ok": c.get("ok", 0), "calls_failed": c.get("failed", 0)})
    return {"from_run": newest.name if newest is not None else None, "no_tools": no_tools, "servers": rows}


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
    from sit_review_agent.ui.launcher import resolve_recorded

    cands: list[Path] = []
    launch = read_json(run_dir / UI_DIR / "launch.json") or {}
    if launch.get("document"):
        cands += resolve_recorded(str(launch["document"]), run_dir.parent, repo_root)
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


def count_lists(report: dict[str, Any]) -> dict[str, list[Any]]:
    """The items each number of the counts strip counts, from the lists of ``report.json``: every finding, the
    findings that are not strengths by severity, the strengths, the sound areas, the unresolved items and the
    limitations. The run view lists exactly these under each number (``ui.reviewtabs``)."""
    findings = [f for f in report.get("findings") or [] if isinstance(f, dict)]
    issues = [f for f in findings if f.get("kind") != "strength"]
    out: dict[str, list[Any]] = {"findings": findings}
    for s in SEVERITIES:
        out[s] = [f for f in issues if f.get("severity") == s]
    out["strengths"] = [f for f in findings if f.get("kind") == "strength"]
    out["sound_areas"] = list(report.get("sound_areas") or [])
    out["unresolved"] = list(report.get("unresolved") or [])
    out["limitations"] = list(report.get("limitations") or [])
    return out


def counts(report: dict[str, Any]) -> dict[str, int]:
    """The counts strip: every number is the length of one of :func:`count_lists`."""
    return {k: len(v) for k, v in count_lists(report).items()}


def _new_row(f: dict[str, Any]) -> dict[str, Any]:
    r = f.get("reassessment") or {}
    return {"prior_id": None, "finding_ids": [f["id"]], "title": f.get("title", ""), "status": "new_in_update",
            "note": r.get("note"), "re_examined": True, "regression": bool(r.get("regression"))}


def delta_view(report: dict[str, Any]) -> dict[str, Any]:
    """The Delta tab, keyed on the prior review's IDs. A full review (no previous version) gives
    ``{"available": False, "reason": NO_PREVIOUS}``: the page shows the tab disabled with that
    sentence. A delta review gives one group per status in :data:`DELTA_GROUPS` order, each row with
    the prior ID, this review's finding ID(s), the title, the status, the note, whether it was
    re-examined, and the regression mark of a new finding. With the delta table
    (``report.prior_findings``) every prior finding is a row; a delta report written before it
    (``table`` false) is grouped from its findings' reassessments and says so (:data:`NO_TABLE`)."""
    if (report.get("metadata") or {}).get("review_mode") != "delta":
        return {"available": False, "reason": NO_PREVIOUS}
    findings = [f for f in report.get("findings") or [] if isinstance(f, dict)]
    by_id = {f.get("id"): f for f in findings}
    rows: list[dict[str, Any]] = []
    table = isinstance(report.get("prior_findings"), list)
    if table:
        for e in report["prior_findings"]:
            ids = list(e.get("finding_ids") or [])
            title = (by_id.get(ids[0]) or {}).get("title") if ids else None
            rows.append({"prior_id": e.get("prior_id"), "finding_ids": ids, "title": title or e.get("prior_title", ""),
                         "status": e.get("status"), "note": e.get("note"), "re_examined": bool(e.get("re_examined")),
                         "regression": False})
    for f in findings:
        r = f.get("reassessment")
        if not isinstance(r, dict):
            continue
        if r.get("status") == "new_in_update" or not r.get("prior_finding_id"):
            rows.append(_new_row(f))
        elif not table:
            rows.append({"prior_id": r.get("prior_finding_id"), "finding_ids": [f["id"]], "title": f.get("title", ""),
                         "status": r.get("status"), "note": r.get("note"), "re_examined": True, "regression": False})
    prior_rows = [x for x in rows if x["status"] != "new_in_update"]
    return {"available": True, "table": table, "notice": None if table else NO_TABLE,
            "prior_count": len(prior_rows) if table else None,
            "not_re_examined": sum(1 for x in prior_rows if not x["re_examined"]),
            "regressions": sum(1 for x in rows if x["regression"]),
            "groups": [{"status": st, "heading": h, "rows": [x for x in rows if x["status"] == st]}
                       for st, h in DELTA_GROUPS]}


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
        "delta": delta_view(report),
        "previous_verdict": previous_verdict(run_dir, runs_dir),
        "pdf_available": reviewed_pdf(run_dir, repo_root) is not None,
    }
    return {"report": report, "derived": derived, "summary": summary(run_dir)}
