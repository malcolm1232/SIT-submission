"""What each stage of a run produced, for the Run log's stage panel (5 Oct 2026). Read-only.

Every item comes from a file the run wrote, read as it is stored:

* ``checkpoints/NN-<phase>.json``: the run state when that phase ended (understand's registry and intent, the
  plan, research's question statuses, the merged drafts after assess, the refined set, the verified set);
* ``shards/NN-<name>.json``: one assess shard's own answer (its findings under the shard's own IDs, its sound
  areas and coverage rows) and its call;
* ``text/<doc>.sections.json``, ``anchors.json``, ``ledger.json``, ``report.json``, ``manifest.json``
  (``extra.finding_ids``: where every draft ID went) and ``effective_config.json`` (the criteria and the
  research budget);
* the records of ``progress.jsonl``, by ``type`` and ``fields`` (never ``message``).

A count is the length of a list in one of these files; nothing is estimated or recomputed. A file the run has not
written (a run in progress, a run cut short, or a directory written before the file existed) is named under
``missing`` with what it would hold, and the view shows what the other files give. Draft items (assess and merge)
are marked ``draft``: they have not been through refine or verify.

:func:`funnel` traces every merged draft finding to its fate (kept, merged into another, withdrawn, dropped or
moved to unresolved by verify, reported) from ``finding_ids`` of the refine and verify checkpoints, and checks it
against the manifest's ``finding_ids.final`` and the run's own ``refined`` and ``anchors_verified`` records.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any

from sit_review_agent.phases._model_calls import REFINE_FALLBACK_IMPACT
from sit_review_agent.ui import events
from sit_review_agent.ui.rundata import read_json

#: The stages in run order. Assess has one panel per shard (``assess-1`` ... ``assess-N``).
STAGES = ("ingest", "understand", "plan", "research", "assess", "merge", "refine", "verify", "report")
STAGE_RE = re.compile(r"^(ingest|understand|plan|research|merge|refine|verify|report|assess-(\d{1,3}))$")
#: The invariant checks the report phase runs before it writes report.json (``phases/report.py``, ``check_all``).
INVARIANTS = ("03", "04", "05", "06", "07", "08", "09", "10", "12", "13")


# ------------------------------------------------------------------ reading


class Reader:
    """One run directory, each file read once."""

    def __init__(self, run_dir: Path) -> None:
        self.rd = run_dir
        self._json: dict[str, Any] = {}
        self.evs = events.read_all(run_dir / "progress.jsonl")
        self.files: list[str] = []
        self.missing: list[dict[str, str]] = []

    def json(self, rel: str) -> Any:
        if rel not in self._json:
            self._json[rel] = read_json(self.rd / rel)
        return self._json[rel]

    def use(self, rel: str) -> Any:
        """``rel`` read and named as a source of the view (``None`` when absent)."""
        doc = self.json(rel)
        if doc is not None and rel not in self.files:
            self.files.append(rel)
        return doc

    def lack(self, rel: str, what: str) -> None:
        if not any(m["file"] == rel for m in self.missing):
            self.missing.append({"file": rel, "what": what})

    def checkpoint(self, phase: str) -> tuple[dict[str, Any] | None, str | None]:
        """The state the run checkpointed when ``phase`` ended, and the file's name."""
        d = self.rd / "checkpoints"
        for p in sorted(d.glob(f"*-{phase}.json")) if d.is_dir() else []:
            doc = self.use(f"checkpoints/{p.name}")
            if isinstance(doc, dict) and isinstance(doc.get("state"), dict):
                return doc["state"], f"checkpoints/{p.name}"
        return None, None

    def state_for(self, phase: str, what: str) -> tuple[dict[str, Any] | None, str | None]:
        """``phase``'s checkpoint, else ``state.json`` when the run's state there has completed the phase (a run
        written before per-phase checkpoints), else ``None`` with the checkpoint named as missing."""
        st, src = self.checkpoint(phase)
        if st is not None:
            return st, src
        latest = self.json("state.json")
        if isinstance(latest, dict) and phase in (latest.get("completed_phases") or []):
            self.use("state.json")
            return latest, "state.json"
        self.lack(f"checkpoints/NN-{phase}.json", what)
        return None, None

    def last(self, type_: str) -> dict[str, Any] | None:
        for ev in reversed(self.evs):
            if ev.get("type") == type_:
                return ev
        return None

    def all(self, type_: str) -> list[dict[str, Any]]:
        return [ev for ev in self.evs if ev.get("type") == type_]

    def config(self) -> dict[str, Any]:
        cfg = self.json("effective_config.json")
        return cfg if isinstance(cfg, dict) else {}

    def criteria(self) -> dict[str, str]:
        crit = self.config().get("criteria") or {}
        rows = crit.get("criteria") if isinstance(crit, dict) else None
        return {str(c["id"]): str(c.get("question") or "") for c in rows or [] if isinstance(c, dict) and c.get("id")}


def _fields(ev: dict[str, Any] | None) -> dict[str, Any]:
    return dict(ev.get("fields") or {}) if ev else {}


def _fact(label: str, value: Any, src: str | None = None, *, mono: bool = False) -> dict[str, Any]:
    return {"label": label, "value": value, "src": src, "mono": mono}


def _list(key: str, title: str, items: list[dict[str, Any]], *, src: str | None, groups: list[dict[str, Any]] |
          None = None, terms: list[str] | None = None, draft: bool = False, empty: str = "None.",
          note: str | None = None) -> dict[str, Any]:
    """One list of the panel: its items in order, the groups they fall in (in the order shown), the glossary terms
    its chips use, whether its items are drafts, what to say when it is empty."""
    return {"key": key, "title": title, "count": len(items), "items": items, "src": src, "groups": groups or [],
            "terms": terms or [], "draft": draft, "empty": empty, "note": note}


def _groups(items: list[dict[str, Any]], order: list[str] | None = None, *, term: str | None = None,
            label: Any = None) -> list[dict[str, Any]]:
    """The groups of ``items`` (by their ``group`` value), in ``order`` first, then as they come."""
    keys: list[str] = [k for k in order or [] if any(i["group"] == k for i in items)]
    keys += [i["group"] for i in items if i["group"] not in keys]
    keys = list(dict.fromkeys(keys))
    return [{"key": k, "label": label(k) if callable(label) else str(k).replace("_", " "),
             "term": f"{term}-{k}" if term else None, "count": sum(1 for i in items if i["group"] == k)}
            for k in keys]


def _view(r: Reader, stage: str, title: str, *, facts: list[dict[str, Any]], lists: list[dict[str, Any]],
          notes: list[dict[str, Any]] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"stage": stage, "title": title, "files": r.files, "missing": r.missing, "facts": facts,
            "notes": notes or [], "lists": lists, **(extra or {})}


def _degs(st: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [d for d in (st or {}).get("degradations") or [] if isinstance(d, dict)]


def _new_degs(before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The degradations ``after``'s phase added: those whose ID is not in ``before``."""
    old = {d.get("id") for d in _degs(before)}
    return [d for d in _degs(after) if d.get("id") not in old]


def _deg_items(degs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "degradation", "key": str(d.get("id")), "group": "", "id": d.get("id"), "dtype": d.get("type"),
             "event": d.get("event"), "impact": d.get("impact")} for d in degs]


# ------------------------------------------------------------------ the stages


def view_ingest(r: Reader) -> dict[str, Any]:
    st, src = r.state_for("ingest", "the document as ingested: pages, hashes and what was sent to the model")
    docs = [d for d in (st or {}).get("documents") or [] if isinstance(d, dict)]
    ev = _fields(r.last("document_ingested"))
    facts: list[dict[str, Any]] = []
    lists: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    for d in docs:
        did = str(d.get("doc_id") or "")
        sec_rel = f"text/{did}.sections.json"
        sec = r.use(sec_rel)
        if not isinstance(sec, dict):
            r.lack(sec_rel, "the section list with page ranges and the page table")
            sec = {}
        pages = [p for p in sec.get("pages") or [] if isinstance(p, dict)]
        sections = [s for s in sec.get("sections") or [] if isinstance(s, dict)]
        image_only = [p.get("number") for p in pages if p.get("image_only")]
        role = str(d.get("role") or "")
        facts += [
            _fact("document", f"{d.get('title') or did} ({did}, {role.replace('_', ' ')})", src),
            _fact("pages", d.get("page_count"), src),
            _fact("sections", len(sections) if sections else ev.get("sections"), sec_rel if sections else
                  "progress.jsonl document_ingested"),
            _fact("SHA-256 of the PDF", d.get("sha256_pdf"), src, mono=True),
            _fact("SHA-256 of the extracted text", d.get("sha256_text"), src, mono=True),
            _fact("text extracted", f"{intl(sum(_span(p) for p in pages))} characters of page-marked text from "
                  f"{len(pages)} pages" if pages else None, sec_rel),
            _fact("pages with no text (image only)", ", ".join(str(n) for n in image_only) if image_only else "none",
                  sec_rel),
            _fact("PDF sent to the model as a document", "yes" if d.get("native_pdf") else
                  "no: the model read the extracted text only", src),
        ]
        if ev.get("requirement_ids") is not None and role == "under_review":
            facts.append(_fact("requirement IDs found in the text", ev.get("requirement_ids"),
                               "progress.jsonl document_ingested"))
        for w in sec.get("warnings") or []:
            notes.append({"text": f"Extraction warning: {w}", "src": sec_rel, "tone": "warn"})
        lists.append(_list("sections", f"Sections of {did}", [
            {"type": "section", "key": f"{did}:{s.get('section_id')}:{s.get('order')}", "group": "",
             "id": s.get("section_id"), "heading": s.get("heading"), "level": s.get("level"),
             "page_start": s.get("page_start"), "page_end": s.get("page_end"),
             "chars": _span(s)} for s in sections],
            src=sec_rel, empty="No section was found in the text (each page is then its own unit)."))
        lists.append(_list("pages", f"Pages of {did}", [
            {"type": "page", "key": f"{did}:p{p.get('number')}", "group": "", "number": p.get("number"),
             "chars": _span(p), "image_only": bool(p.get("image_only"))}
            for p in pages], src=sec_rel))
    degs = _degs(st)
    lists.append(_list("degradations", "What could not be extracted or sent (disclosed in the report)",
                       _deg_items(degs), src=src, terms=["id-DEG"],
                       empty="Nothing: the run recorded no input degradation at ingest."))
    return _view(r, "ingest", "Ingest: reading the PDF", facts=facts, lists=lists, notes=notes)


def _span(p: dict[str, Any]) -> int:
    """Characters of a page or section row: ``char_end - char_start``."""
    return int(p.get("char_end") or 0) - int(p.get("char_start") or 0)


def intl(n: Any) -> str:
    return f"{n:,}" if isinstance(n, int) else str(n)


REGISTRY_ORDER = ["approved_decision", "pending_decision", "constraint", "requirement"]


def _registry_items(reg: list[Any]) -> list[dict[str, Any]]:
    return [{"type": "registry", "key": str(e.get("registry_id")), "group": str(e.get("type") or ""),
             "id": e.get("registry_id"), "rtype": e.get("type"), "statement": e.get("statement"),
             "doc_ref": e.get("doc_ref"), "anchor": e.get("doc_anchor")} for e in reg if isinstance(e, dict)]


def view_understand(r: Reader) -> dict[str, Any]:
    st, src = r.state_for("understand", "the intent summary, the decision registry and the review inputs found")
    st = st or {}
    reg = _registry_items(st.get("registry") or [])
    intent = st.get("intent_summary") if isinstance(st.get("intent_summary"), dict) else {}
    hashes = [h for h in st.get("registry_hashes") or [] if isinstance(h, dict)]
    ready = _fields(r.last("intent_ready"))
    facts = [_fact("registry entries", len(reg) if st else ready.get("registry_entries"), src),
             _fact("registry frozen", ("yes" if st.get("registry_frozen") else "no") if st else None, src),
             _fact("registry SHA-256", hashes[-1].get("sha256") if hashes else None, src, mono=True),
             _fact("review inputs found", len(st.get("review_inputs_found") or []) if st else None, src)]
    lists = [
        _list("registry", "Decision registry", reg, src=f"{src} state.registry" if src else None,
              groups=_groups(reg, REGISTRY_ORDER, term="reg"), terms=["id-AD"]),
        _list("review_inputs", "Review inputs found in the document", [
            {"type": "text", "key": f"ri{i}", "group": "", "text": t, "term": "review-input"}
            for i, t in enumerate(st.get("review_inputs_found") or [])],
            src=f"{src} state.review_inputs_found" if src else None, terms=["review-input"],
            empty="The document holds no review comment or claimed fix."),
    ]
    for key, title in (("objectives", "Objectives"), ("constraints", "Constraints"),
                       ("key_assumptions", "Key assumptions")):
        lists.append(_list(key, title + " (intent summary)", [
            {"type": "intent", "key": f"{key}{i}", "group": "", "ref": o.get("ref"), "text": o.get("text")}
            for i, o in enumerate(intent.get(key) or []) if isinstance(o, dict)],
            src=f"{src} state.intent_summary.{key}" if src else None))
    lists.append(_list("intent_anchors", "Where the purpose and scope are stated", [
        {"type": "anchor_quote", "key": f"ia{i}", "group": "", "anchor": a}
        for i, a in enumerate(intent.get("doc_anchors") or []) if isinstance(a, dict)],
        src=f"{src} state.intent_summary.doc_anchors" if src else None))
    return _view(r, "understand", "Understand: what the design says it is", facts=facts, lists=lists,
                 extra={"statement": intent.get("statement")})


def _question_items(qs: list[Any], crit: dict[str, str]) -> list[dict[str, Any]]:
    return [{"type": "question", "key": str(q.get("id")), "group": str(q.get("criterion_id") or ""),
             "id": q.get("id"), "criterion": q.get("criterion_id"), "question": q.get("question"),
             "needs_external": bool(q.get("needs_external")), "capability": q.get("capability"),
             "queries": q.get("queries") or [], "rationale": q.get("rationale"), "section_refs": q.get("section_refs")
             or [], "status": q.get("status"), "summary": q.get("summary"), "evidence_ids": q.get("evidence_ids") or []}
            for q in qs if isinstance(q, dict)]


def view_plan(r: Reader) -> dict[str, Any]:
    st, src = r.state_for("plan", "the review plan: the questions per criterion")
    plan = (st or {}).get("plan") if isinstance((st or {}).get("plan"), dict) else {}
    crit = r.criteria()
    qs = _question_items(plan.get("questions") or [], crit)
    sr = r.config().get("stop_rules") or {}
    ready = _fields(r.last("plan_ready"))
    facts = [_fact("questions", len(qs) if plan else ready.get("questions"), src),
             _fact("of them needing external research", sum(1 for q in qs if q["needs_external"]) if plan
                   else ready.get("external"), src),
             _fact("criteria", len(crit) if crit else None, "effective_config.json criteria" if crit else None),
             _fact("plan approved", ("yes" if plan.get("approved") else "no") if plan else None, src),
             _fact("research budget for the whole run", f"at most {sr.get('max_research_iterations')} rounds and "
                   f"{sr.get('max_tool_calls')} tool calls; the plan sets no budget per question"
                   if sr.get("max_tool_calls") is not None else None, "effective_config.json stop_rules")]
    if ready.get("fallback"):
        facts.append(_fact("plan built by code", ready.get("fallback"), "progress.jsonl plan_ready"))
    if crit:
        r.use("effective_config.json")
    skipped = [c for c in plan.get("criteria_skipped") or []]
    lists = [
        _list("questions", "Questions, by the criterion each serves", qs, src=f"{src} state.plan.questions"
              if src else None, groups=_groups(qs, list(crit), term="crit"), terms=["id-RQ", "q-external"]),
        _list("criteria_skipped", "Criteria skipped, with the reason", [
            {"type": "skip", "key": f"sk{i}", "group": "", "rec": c} for i, c in enumerate(skipped)],
            src=f"{src} state.plan.criteria_skipped" if src else None,
            empty="None: every criterion has at least one question."),
    ]
    return _view(r, "plan", "Plan: what to check and what to look up", facts=facts, lists=lists,
                 extra={"criteria": crit})


def view_research(r: Reader) -> dict[str, Any]:
    st, src = r.state_for("research", "each research question's status, the tool calls and the stop reason")
    st = st or {}
    plan = st.get("plan") if isinstance(st.get("plan"), dict) else {}
    qs = [q for q in _question_items(plan.get("questions") or [], r.criteria()) if q["needs_external"]]
    stopped = _fields(r.last("research_stopped"))
    doc_only = _fields(r.last("research_doc_only"))
    skipped = r.last("research_skipped")
    stop = st.get("stop_reason") if isinstance(st.get("stop_reason"), dict) else {}
    off = stopped.get("code") == "tool_failure" and stopped.get("detail") == "no_tools"
    for q in qs:
        q["group"] = "left to the document" if off else str(q.get("status") or "")
    ledger = r.use("ledger.json")
    external = [e for e in ledger if isinstance(e, dict) and e.get("source_type") == "external"] \
        if isinstance(ledger, list) else []
    if not isinstance(ledger, list):
        r.lack("ledger.json", "the evidence ledger, with the entries research created")
    calls = [c for c in st.get("tool_calls") or [] if isinstance(c, dict)]
    if off:
        status = ("skipped: no tool gateway in this run (--no-tools, or every server disabled), so no outside "
                  "question was researched")
    elif skipped:
        status = "skipped: " + str(_fields(skipped).get("reason") or "").replace("_", " ")
    elif stopped:
        status = f"stopped: {stopped.get('code')}" + (f" ({stopped.get('detail')})" if stopped.get("detail") else "")
    else:
        status = None
    facts = [_fact("research", status, "progress.jsonl research_stopped" if stopped else None),
             _fact("disclosed as", doc_only.get("degradation_id"), "progress.jsonl research_doc_only")
             if doc_only.get("degradation_id") else None,
             _fact("stop reason recorded", f"{stop.get('code')} ({stop.get('detail')})" if stop else None, src),
             _fact("questions for an outside source", len(qs) if plan else stopped.get("questions"), src),
             _fact("answered", stopped.get("answered"), "progress.jsonl research_stopped"),
             _fact("tool calls", len(calls) if st else stopped.get("tool_calls"), src),
             _fact("ledger entries from outside sources", len(external) if isinstance(ledger, list) else None,
                   "ledger.json"),
             _fact("queries issued", st.get("queries_issued"), src)]
    order = ["left to the document", "answered", "partial", "conflicting", "unanswered", "open"]
    lists = [
        _list("questions", "Questions for an outside source, by status" if not off else
              "Questions for an outside source, left to the document", qs,
              src=f"{src} state.plan.questions (needs_external)" if src else None, groups=_groups(qs, order),
              terms=["id-RQ", "q-external"], empty="The plan has no question for an outside source."),
        _list("tool_calls", "Tool calls", [
            {"type": "tool_call", "key": str(c.get("call_id")), "group": str(c.get("server") or ""), "rec": c}
            for c in calls], src=f"{src} state.tool_calls" if src else None,
            empty="None: no tool was called in this run." if st else "Not recorded.",
            note="The run records each tool call with its server and status; it does not record which question a "
                 "call served (research_log.tool_calls has no question ID)." if calls else None),
        _list("ledger", "Ledger entries from outside sources", [
            {"type": "ledger", "key": str(e.get("evidence_id")), "group": "", "rec": e} for e in external],
            src="ledger.json (source_type external)", terms=["id-EV"],
            empty="None: research added no outside entry to the ledger."),
    ]
    facts = [f for f in facts if f is not None]
    return _view(r, "research", "Research: asking the SIT MCP servers", facts=facts, lists=lists,
                 extra={"off": off})


def _shard_files(r: Reader) -> dict[int, Path]:
    d = r.rd / "shards"
    out: dict[int, Path] = {}
    for p in sorted(d.glob("*.json")) if d.is_dir() else []:
        m = re.match(r"(\d+)-", p.name)
        if m:
            out[int(m.group(1))] = p
    return out


def _id_maps(r: Reader) -> dict[str, Any]:
    """``finding_ids`` of the newest state the run wrote (the merge, refine and verify maps accumulate)."""
    for phase in ("report", "verify", "refine", "assess"):
        st, _ = r.checkpoint(phase)
        if st is not None and isinstance(st.get("finding_ids"), dict):
            return st["finding_ids"]
    latest = r.json("state.json")
    if isinstance(latest, dict) and isinstance(latest.get("finding_ids"), dict):
        r.use("state.json")
        return latest["finding_ids"]
    return {}


def _finding_item(f: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"type": "finding", "key": str(extra.pop("key", None) or f.get("id")), "group": extra.pop("group", ""),
            "id": f.get("id"), "rec": f, **extra}


KIND_ORDER = ["risk", "gap", "ambiguity", "unresolved_assumption", "validation_need", "strength"]


def view_assess(r: Reader, n: int) -> dict[str, Any]:
    files = _shard_files(r)
    started = next((_fields(e) for e in r.all("shard_started") if _fields(e).get("shard") == n), {})
    plan = next((g for g in _fields(r.last("assess_started")).get("groups") or [] if g.get("index") == n), {})
    path = files.get(n)
    doc = r.use(f"shards/{path.name}") if path else None
    res = doc.get("result") if isinstance(doc, dict) and isinstance(doc.get("result"), dict) else None
    name = (res or {}).get("name") or started.get("shard_name") or plan.get("name")
    if res is None:
        r.lack(f"shards/{n:02d}-{name or '<name>'}.json", "the shard's own answer: its draft findings, sound areas "
               "and coverage rows (written when the shard ends)")
    out = (res or {}).get("output") if isinstance((res or {}).get("output"), dict) else {}
    to_merged = (_id_maps(r).get("shards") or {}).get(name) or {}
    fates = {row["draft_id"]: row for row in funnel_rows(r)} if to_merged else {}
    crit = r.criteria()
    criteria = (res or {}).get("criteria") or started.get("criteria") or plan.get("criteria") or []
    drafted = next((_fields(e) for e in r.all("shard_drafted") if _fields(e).get("shard") == n), {})
    cut = next((_fields(e) for e in r.all("shard_cut") if _fields(e).get("shard") == n), {})
    failed = next((_fields(e) for e in r.all("shard_failed") if _fields(e).get("shard") == n), {})
    call_id = (res or {}).get("call_id") or drafted.get("call_id") or cut.get("call_id")
    streamed: dict[str, list[int]] = {}
    for e in r.all("draft_item"):
        f = _fields(e)
        if f.get("call_id") == call_id and call_id:
            streamed.setdefault(str(f.get("list")), []).append(int(f.get("index") or 0))
    findings = []
    for f in out.get("findings") or []:
        if not isinstance(f, dict):
            continue
        merged = to_merged.get(str(f.get("id")))
        findings.append(_finding_item(f, key=f"s{n}:{f.get('id')}", group=str(f.get("kind") or ""), draft=True,
                                      local_id=f.get("id"), merged_id=merged,
                                      fate=(fates.get(merged) or {}).get("fate") if merged else None))
    sound = [{"type": "sound_area", "key": f"s{n}:sa{i}", "group": "", "rec": s}
             for i, s in enumerate(out.get("sound_areas") or []) if isinstance(s, dict)]
    cov = [{"type": "coverage", "key": f"s{n}:c{i}", "group": str(c.get("outcome") or ""), "rec": c}
           for i, c in enumerate(out.get("coverage") or []) if isinstance(c, dict)]
    budget = ((res or {}).get("delta") or {}).get("budget") or {}
    facts = [_fact("shard", f"{n} of {started.get('shards') or len(files) or '?'}: {name}", "progress.jsonl "
                   "shard_started"),
             _fact("model call", call_id, f"shards/{path.name}" if path else None),
             _fact("outcome", (res or {}).get("outcome") or ("cut" if cut else ("failed" if failed else None)),
                   f"shards/{path.name}" if path else None),
             _fact("model", (res or {}).get("model"), f"shards/{path.name}" if path else None),
             _fact("output tokens", budget.get("output_tokens"), f"shards/{path.name} delta.budget" if path else None),
             _fact("items salvaged from a cut", (res or {}).get("salvaged") or None,
                   f"shards/{path.name}" if path else None)]
    notes = []
    if (res or {}).get("detail"):
        notes.append({"text": str(res["detail"]), "src": f"shards/{path.name}" if path else None, "tone": "warn"})
    # The stream against the answer: a list whose item numbers started over is an answer the model wrote again.
    differ, restarts = [], 0
    for key, kept in (("findings", len(findings)), ("sound_areas", len(sound)), ("coverage", len(cov))):
        idx = streamed.get(key) or []
        restarts = max(restarts, sum(1 for a, b in zip(idx, idx[1:], strict=False) if b <= a))
        if res is not None and idx and len(idx) != kept:
            differ.append((key.replace("_", " "), len(idx), kept))
    if differ:
        notes.append({"text": "The call's stream carried " + ", ".join(f"{n} {k}" for k, n, _ in differ)
                      + (f"; its item numbers started over {restarts} time(s), as when the model writes its answer "
                         "again" if restarts else "")
                      + ". The shard's answer holds " + ", ".join(f"{kept} {k}" for k, _, kept in differ)
                      + ", the ones listed here.",
                      "src": "progress.jsonl draft_item; " + (f"shards/{path.name}" if path else "")})
    lists = [
        _list("criteria", "Criteria this shard checked against", [
            {"type": "criterion", "key": f"s{n}:{c}", "group": "", "id": c, "question": crit.get(str(c))}
            for c in criteria], src="effective_config.json criteria" if crit else None, terms=["run-shard"]),
        _list("findings", "Draft findings", findings, src=f"shards/{path.name} result.output.findings" if path
              else None, groups=_groups(findings, KIND_ORDER, term="kind"),
              terms=["run-draft", "kind-risk", "sev-high", "id-FND"], draft=True,
              empty="The shard's answer holds no finding." if res is not None else
              "Not written yet: the shard's answer appears here when the shard ends."),
        _list("sound_areas", "Sound areas (checked, no change needed)", sound,
              src=f"shards/{path.name} result.output.sound_areas" if path else None, terms=["id-SA", "run-draft"],
              draft=True),
        _list("coverage", "Coverage rows", cov, src=f"shards/{path.name} result.output.coverage" if path else None,
              groups=_groups(cov, ["findings", "no_issue", "not_applicable"], term="cov"), draft=True),
    ]
    if crit:
        r.use("effective_config.json")
    return _view(r, f"assess-{n}", f"Assess shard {n}: {str(name or '').replace('_', ' ')}", facts=facts,
                 lists=lists, notes=notes, extra={"shard": n, "shard_name": name, "call_id": call_id})


def _shard_of(maps: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """merged draft ID -> (shard name, the shard's own ID)."""
    out: dict[str, tuple[str, str]] = {}
    for name, m in (maps.get("shards") or {}).items():
        for local, merged in (m or {}).items():
            out[str(merged)] = (str(name), str(local))
    return out


def view_merge(r: Reader) -> dict[str, Any]:
    st, src = r.checkpoint("assess")
    if st is None:
        r.lack("checkpoints/NN-assess.json", "the merged list: every shard's findings renumbered in shard order, the "
               "sound areas and the coverage rows")
    st = st or {}
    shard_of = _shard_of(st.get("finding_ids") or {})
    index = {str(g.get("name")): int(g.get("index") or 0) for g in _fields(r.last("assess_started")).get("groups")
             or [] if isinstance(g, dict)}
    findings = []
    for f in st.get("finding_drafts") or []:
        if isinstance(f, dict):
            name, local = shard_of.get(str(f.get("id")), (None, None))
            findings.append(_finding_item(f, group=name or "", draft=True, shard=name,
                                          shard_index=index.get(name or ""), local_id=local))
    order = sorted({i["group"] for i in findings}, key=lambda k: index.get(k, 0))
    sound = [{"type": "sound_area", "key": str(s.get("id") or i), "group": "", "rec": s}
             for i, s in enumerate(st.get("sound_area_drafts") or []) if isinstance(s, dict)]
    cov = [{"type": "coverage", "key": f"c{i}", "group": str(c.get("outcome") or ""), "rec": c}
           for i, c in enumerate(st.get("coverage") or []) if isinstance(c, dict)]
    m = _fields(r.last("shards_merged"))
    facts = [_fact("findings", len(findings) if st else m.get("findings"), src),
             _fact("sound areas", len(sound) if st else m.get("sound_areas"), src),
             _fact("from shards", m.get("shards"), "progress.jsonl shards_merged"),
             _fact("evidence added to the ledger", f"{m.get('doc_evidence_added')} document passages and "
                   f"{m.get('inference_evidence_added')} inferences" if m.get("doc_evidence_added") is not None else
                   None, "progress.jsonl shards_merged"),
             _fact("degraded shards", ", ".join(str(x) for x in m.get("degraded_shards") or []) or "none"
                   if m else None, "progress.jsonl shards_merged")]

    def shard_label(k: str) -> str:
        return f"shard {index[k]}: {k.replace('_', ' ')}" if k in index else k.replace("_", " ")

    lists = [
        _list("findings", "Merged findings, by the shard each came from", findings,
              src=f"{src} state.finding_drafts" if src else None, groups=_groups(findings, order, label=shard_label),
              terms=["run-draft", "run-shard", "id-FND"], draft=True),
        _list("sound_areas", "Sound areas", sound, src=f"{src} state.sound_area_drafts" if src else None,
              terms=["id-SA"], draft=True),
        _list("coverage", "Coverage rows", cov, src=f"{src} state.coverage" if src else None,
              groups=_groups(cov, ["findings", "no_issue", "not_applicable"], term="cov"), draft=True),
    ]
    return _view(r, "merge", "Merge: the shards' findings in one list", facts=facts, lists=lists)


def _refine_history(meta: dict[str, Any], fid: str) -> dict[str, Any] | None:
    """The refine entry of ``fid``'s history in ``finding_meta`` (the revision applied to it), if any."""
    m = meta.get(fid) or {}
    hist = [h for h in m.get("history") or [] if isinstance(h, dict) and h.get("phase") == "refine"]
    return hist[-1] if hist else None


def view_refine(r: Reader) -> dict[str, Any]:
    before, bsrc = r.checkpoint("assess")
    after, asrc = r.checkpoint("refine")
    if after is None:
        r.lack("checkpoints/NN-refine.json", "the revision applied to each finding and the refined set")
    rows = funnel_rows(r)
    meta = (after or {}).get("finding_meta") or {}
    revisions = []
    for row in rows:
        h = _refine_history(meta, row["draft_id"]) if after else None
        revisions.append({"type": "revision", "key": row["draft_id"], "group": row["refine"], "id": row["draft_id"],
                          "into": row.get("merged_into"), "title": row.get("title"), "kind": row.get("kind"),
                          "severity": row.get("severity"), "note": (h or {}).get("note"),
                          "changed": sorted((h or {}).get("changed_fields") or {}),
                          "call_id": (h or {}).get("call_id")})
    refined = _fields(r.last("refined"))
    cut_ev = r.last("call_cut") if (r.last("call_cut") or {}).get("phase") == "refine" else None
    cut = _fields(cut_ev)
    # A run written before the cut line was corrected says the fallback sentence at the cut, before a salvage.
    cut_said_fallback = REFINE_FALLBACK_IMPACT in str((cut_ev or {}).get("message") or "")
    fallback = r.last("refine_fallback")
    rejected = [_fields(e) for e in r.all("revision_rejected")]
    kept = [f for f in (after or {}).get("finding_drafts") or [] if isinstance(f, dict)]
    refined_ids = set(((after or {}).get("finding_ids") or {}).get("refine_fields") or {})
    result = [_finding_item(f, draft=True, refined=f.get("id") in refined_ids) for f in kept]
    new = _new_degs(before, after)
    facts = [_fact("findings in", len((before or {}).get("finding_drafts") or []) if before else
                   _fields(r.last("refine_started")).get("findings"), bsrc),
             _fact("findings out", len(kept) if after else refined.get("findings"), asrc),
             _fact("revised", refined.get("revised"), "progress.jsonl refined"),
             _fact("unchanged", refined.get("unchanged"), "progress.jsonl refined"),
             _fact("merged into another", refined.get("merged"), "progress.jsonl refined"),
             _fact("withdrawn", refined.get("withdrawn"), "progress.jsonl refined")]
    if cut:
        facts.append(_fact("model call cut", f"{cut.get('call_id')} at {_mmss(cut.get('at_s'))} on the run clock, with "
                           f"{cut.get('kept_items')} finished revision(s)"
                           + (" (a complete answer)" if cut.get("complete") else ""), "progress.jsonl call_cut"))
    if refined.get("salvaged"):
        facts.append(_fact("revisions applied from the cut answer", f"{refined.get('applied')} of "
                           f"{refined.get('salvaged_items')} finished; {refined.get('dropped')} dropped",
                           "progress.jsonl refined"))
    notes = []
    if refined.get("salvaged"):
        notes.append({"text": f"The cut call's finished revisions were applied: {refined.get('applied')} of them "
                      f"({refined.get('merged')} merges into kept findings among them); "
                      f"{refined.get('dropped')} were dropped, and the findings they were for were not refined."
                      + (" The progress line written at the cut, before this salvage, says the merged findings are "
                         "reported without the refine pass; that line is superseded by the refined record."
                         if cut_said_fallback else ""),
                      "src": "progress.jsonl refined (salvaged true)", "tone": "warn"})
    if fallback:
        notes.append({"text": "Refine fell back: the merged findings stand as merged, in severity and confidence "
                      "order, with no revision applied.", "src": "progress.jsonl refine_fallback", "tone": "warn"})
    for rj in rejected:
        notes.append({"text": f"{rj.get('finding_id')}: {', '.join(rj.get('fields_rejected') or [])} change rejected "
                      "(no revision reason and no new evidence); the draft's value kept.",
                      "src": "progress.jsonl revision_rejected", "tone": "warn"})
    order = ["revised", "kept as drafted", "not refined (counted as unchanged)", "merged", "withdrawn", "not recorded"]
    lists = [
        _list("revisions", "The revision applied to each merged finding", revisions,
              src=f"{asrc} finding_ids.refine, finding_ids.refine_fields, finding_meta history" if asrc else None,
              groups=_groups(revisions, order), terms=["rev-keep", "rev-merge", "rev-withdraw", "id-FND"]),
        _list("lost", "What the cut or the fallback cost (disclosed in the report)", _deg_items(new), src=asrc,
              terms=["id-DEG"], empty="Nothing: refine recorded no degradation."),
        _list("result", "The refined set, in rank order", sorted(result, key=lambda i: (i["rec"].get("rank") or 0)),
              src=f"{asrc} state.finding_drafts" if asrc else None, terms=["run-draft", "rank", "id-FND"], draft=True,
              note="Still unverified: verify checks every quote of these next."),
    ]
    return _view(r, "refine", "Refine: one call over every finding", facts=facts, lists=lists, notes=notes)


def _mmss(s: Any) -> str | None:
    if not isinstance(s, int | float):
        return None
    t = max(0, int(s))
    return f"{t // 60:02d}:{t % 60:02d}"


def _owner_kind(owner: str) -> str:
    return {"FND": "findings", "AD": "registry entries", "SA": "sound areas"}.get(owner.split("-")[0], "intent summary")


def view_verify(r: Reader) -> dict[str, Any]:
    st, src = r.checkpoint("verify")
    if st is None:
        r.lack("checkpoints/NN-verify.json", "the verified findings and the unresolved list")
    anchors = r.use("anchors.json")
    if not isinstance(anchors, dict):
        r.lack("anchors.json", "one row per anchor: status, match method and score, page")
        anchors = {}
    rows = [a for a in anchors.get("rows") or [] if isinstance(a, dict)]
    st = st or {}
    quotes: dict[tuple[str, int], dict[str, Any]] = {}
    for f in st.get("findings") or []:
        for i, a in enumerate(f.get("doc_anchors") or []):
            quotes[(str(f.get("id")), i)] = a
    for e in st.get("registry") or []:
        if isinstance(e, dict) and isinstance(e.get("doc_anchor"), dict):
            quotes[(str(e.get("registry_id")), 0)] = e["doc_anchor"]
    for s in st.get("sound_areas") or []:
        for i, a in enumerate(s.get("doc_anchors") or []):
            quotes[(str(s.get("id")), i)] = a
    items = [{"type": "anchor", "key": f"{a.get('owner_id')}#{a.get('anchor_index')}",
              "group": _owner_kind(str(a.get("owner_id") or "")), "owner": a.get("owner_id"),
              "index": a.get("anchor_index"), "status": a.get("anchor_status"), "method": a.get("method"),
              "score": a.get("score"), "page": a.get("page"), "matched_page": a.get("matched_page"),
              "section_ref": a.get("section_ref"), "reasons": a.get("reasons") or [],
              "quote": (quotes.get((str(a.get("owner_id")), int(a.get("anchor_index") or 0))) or {}).get("quote")}
             for a in rows]
    by_owner: dict[str, list[dict[str, Any]]] = {}
    for a in items:
        by_owner.setdefault(str(a["owner"]), []).append(a)
    maps = st.get("finding_ids") or {}
    unverified = [str(x) for x in maps.get("unverified") or []]
    vmap = maps.get("verify") or {}
    per = []
    for f in st.get("findings") or []:
        fid = str(f.get("id"))
        own = by_owner.get(fid, [])
        ok = [a for a in own if a["status"] in ("resolved", "repaired")]
        per.append({"type": "verified", "key": fid, "group": "verified", "id": fid, "title": f.get("title"),
                    "kind": f.get("kind"), "severity": f.get("severity"), "anchors": own,
                    "why": f"{len(ok)} of {len(own)} anchor(s) resolve in the page text" if own else
                    "no anchor row in anchors.json"})
    for u in st.get("unresolved") or []:
        if isinstance(u, dict) and any(str(x) in unverified for x in u.get("finding_ids") or []):
            for fid in u.get("finding_ids") or []:
                per.append({"type": "verified", "key": f"u:{fid}", "group": "moved to unresolved (unverified)",
                            "id": fid, "title": u.get("text"), "anchors": by_owner.get(str(fid), []),
                            "why": "no anchor of it resolved: listed under the unresolved items, never dropped "
                                   "silently"})
    for old, new in vmap.items():
        if new is None and old not in unverified:
            per.append({"type": "verified", "key": f"d:{old}", "group": "dropped by verify", "id": old,
                        "anchors": by_owner.get(str(old), []), "why": "dropped by verify (finding_ids.verify maps it "
                        "to nothing)"})
        elif new is not None:
            per.append({"type": "verified", "key": f"r:{old}", "group": "renumbered by verify", "id": old,
                        "why": f"renumbered to {new}"})
    summary = anchors.get("summary") or {}
    rules = anchors.get("rules") or {}
    av = _fields(r.last("anchors_verified"))
    rep = _fields(r.last("anchor_repair"))
    facts = [_fact("anchors", summary.get("anchors", av.get("anchors")), "anchors.json summary"),
             _fact("resolved", summary.get("resolved", av.get("resolved")), "anchors.json summary"),
             _fact("repaired", summary.get("repaired", av.get("repaired")), "anchors.json summary"),
             _fact("unresolved", summary.get("unresolved", av.get("unresolved")), "anchors.json summary"),
             _fact("findings verified", av.get("findings_verified"), "progress.jsonl anchors_verified"),
             _fact("findings unverified", av.get("findings_unverified"), "progress.jsonl anchors_verified"),
             _fact("re-quote (repair) call", anchors.get("repair_call_id") or (
                 f"none: {rep.get('unresolved')} anchor(s) unresolved and {rep.get('slack_s')} s of slack before the "
                 "verify and verdict reserve" if rep and not rep.get("repair") else None), "anchors.json; "
                 "progress.jsonl anchor_repair"),
             _fact("match rules", ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in rules.items()) or None,
                   "anchors.json rules")]
    inv = invariant_items(r)
    lists = [
        _list("per_finding", "Each finding: verified or not, and why", per, src=f"{src} state.findings, "
              "finding_ids; anchors.json rows" if src else "anchors.json rows",
              groups=_groups(per, ["verified", "moved to unresolved (unverified)", "dropped by verify",
                                   "renumbered by verify"]), terms=["anchor-resolved", "anchor-unresolved"]),
        _list("anchors", "Every anchor checked", items, src="anchors.json rows (quotes from " + (src or "state")
              + ")", groups=_groups(items, ["findings", "registry entries", "sound areas", "intent summary"]),
              terms=["anchor-resolved", "anchor-repaired", "anchor-unresolved"]),
        _list("invariants", "Invariants checked before report.json is written", inv["items"], src=inv["src"],
              note=inv["note"]),
        _list("degradations", "What verify disclosed", _deg_items(_new_degs(r.checkpoint("refine")[0], st or None)),
              src=src, terms=["id-DEG"], empty="Nothing: verify recorded no degradation."),
    ]
    return _view(r, "verify", "Verify: every quote against the page", facts=facts, lists=lists)


def invariant_items(r: Reader) -> dict[str, Any]:
    """The invariants the report phase checks, each with the first sentence of its check's docstring and the
    result the run directory records: ``report.json`` is written only when every check passes
    (``phases/report.py``); a failing run writes ``report.invalid.json`` and ``failure.json`` instead."""
    from sit_review_agent import invariants

    failure = read_json(r.rd / "failure.json") if (r.rd / "failure.json").is_file() else None
    problems = [str(p) for p in (failure or {}).get("problems") or []] if isinstance(failure, dict) else []
    has_report = (r.rd / "report.json").is_file()
    items = []
    for n in INVARIANTS:
        fn = getattr(invariants, f"check_INV_{n}", None)
        doc = (inspect.getdoc(fn) or "").split("\n\n")[0].replace("\n", " ") if fn else ""
        doc = re.sub(r":\w+:`~?([^`]*)`", r"\1", doc).replace("``", "")      # the docstring's reST, as plain text
        mine = [p for p in problems if p.startswith(f"INV-{n}")]
        result = ("failed" if mine else ("passed" if has_report else ("failed (another check)" if problems else
                                                                        "not checked yet")))
        items.append({"type": "invariant", "key": f"INV-{n}", "group": "", "id": f"INV-{n}", "about": doc,
                      "result": result, "problems": mine})
    if has_report:
        r.use("report.json")
        note = ("The run records these as one result: report.json exists, and the report phase writes it only after "
                "every check passes (agent/sit_review_agent/phases/report.py, check_all). It does not record a "
                "separate result per invariant, nor which ones were skipped (INV-08 without canaries, INV-13 in a "
                "full review).")
    elif problems:
        r.use("failure.json")
        note = "The report phase stopped the run: failure.json lists the problems of each failing check."
    else:
        note = "The report phase has not run yet."
    return {"items": items, "src": "agent/sit_review_agent/invariants.py (what each checks); report.json or "
            "failure.json (the result)", "note": note}


def view_report(r: Reader) -> dict[str, Any]:
    rep = r.use("report.json")
    if not isinstance(rep, dict):
        r.lack("report.json", "the verdict, its conditions, the per-objective table and the final findings")
        rep = {}
    v = rep.get("verdict") or {}
    anchors = r.json("anchors.json") or {}
    by_owner: dict[str, list[dict[str, Any]]] = {}
    for a in anchors.get("rows") or [] if isinstance(anchors, dict) else []:
        if isinstance(a, dict):
            by_owner.setdefault(str(a.get("owner_id")), []).append(a)
    findings = sorted([_finding_item(f, group="strength" if f.get("kind") == "strength" else str(f.get("severity")),
                                     anchors=by_owner.get(str(f.get("id")), []))
                       for f in rep.get("findings") or [] if isinstance(f, dict)],
                      key=lambda i: i["rec"].get("rank") or 0)
    texts = {str(o.get("ref")): o.get("text") for o in ((rep.get("intent_summary") or {}).get("objectives") or [])
             if isinstance(o, dict)}
    call = next((_fields(e) for e in reversed(r.all("call_closed")) if _fields(e).get("purpose") == "verdict"), {})
    facts = [_fact("verdict", str(v.get("label") or "").replace("_", " ") or None, "report.json verdict"),
             _fact("confidence", v.get("confidence"), "report.json verdict"),
             _fact("findings", len(findings) if rep else None, "report.json findings"),
             _fact("unresolved items", len(rep.get("unresolved") or []) if rep else None, "report.json unresolved"),
             _fact("limitations", len(rep.get("limitations") or []) if rep else None, "report.json limitations"),
             _fact("verdict call", f"{call.get('call_id')}, {call.get('outcome')}" if call else None,
                   "progress.jsonl call_closed")]
    lists = [
        _list("conditions", "Conditions", [
            {"type": "condition", "key": f"c{i}", "group": "", "text": c.get("text"),
             "ids": c.get("finding_ids") or []}
            for i, c in enumerate(v.get("conditions") or []) if isinstance(c, dict)],
            src="report.json verdict.conditions", terms=[f"verdict-{v.get('label')}"] if v.get("label") else [],
            empty="None: the verdict has no condition."),
        _list("per_objective", "Verdict per objective", [
            {"type": "objective", "key": f"o{i}", "group": "", "ref": o.get("objective_ref"),
             "text": texts.get(str(o.get("objective_ref"))), "label": o.get("label"),
             "ids": o.get("finding_ids") or [], "rationale": o.get("rationale")}
            for i, o in enumerate(v.get("per_objective") or []) if isinstance(o, dict)],
            src="report.json verdict.per_objective"),
        _list("findings", "The reported findings, in rank order", findings, src="report.json findings",
              groups=_groups(findings, ["critical", "high", "medium", "low", "strength"], term="sev"),
              terms=["sev-high", "kind-risk", "confidence", "rank", "id-FND"]),
        _list("unresolved", "Unresolved items", [
            {"type": "unresolved", "key": f"u{i}", "group": "", "rec": u} for i, u in enumerate(rep.get("unresolved")
                                                                                                   or [])],
            src="report.json unresolved"),
        _list("limitations", "Evidence limitations", [
            {"type": "limitation", "key": f"l{i}", "group": "", "rec": x} for i, x in enumerate(rep.get("limitations")
                                                                                                  or [])],
            src="report.json limitations", terms=["id-DEG"]),
    ]
    return _view(r, "report", "Report: the verdict and the record", facts=facts, lists=lists,
                 extra={"rationale": v.get("rationale"), "what_would_change_it": v.get("what_would_change_it")})


def stage_view(run_dir: Path, name: str) -> dict[str, Any] | None:
    """The panel of stage ``name`` (one of :data:`STAGES`, ``assess-N`` for a shard); ``None`` for another name."""
    m = STAGE_RE.match(name)
    if not m:
        return None
    r = Reader(run_dir)
    if m.group(2):
        return view_assess(r, int(m.group(2)))
    return {"ingest": view_ingest, "understand": view_understand, "plan": view_plan, "research": view_research,
            "merge": view_merge, "refine": view_refine, "verify": view_verify, "report": view_report}[name](r)


# ------------------------------------------------------------------ the funnel


def funnel_rows(r: Reader) -> list[dict[str, Any]]:
    """One row per merged draft finding (assess checkpoint), with what refine, verify and the report did to it."""
    ass, _ = r.checkpoint("assess")
    ref, _ = r.checkpoint("refine")
    ver, _ = r.checkpoint("verify")
    rep = r.json("report.json") if (r.rd / "report.json").is_file() else None
    manifest = r.json("manifest.json") or {}
    final = (((manifest.get("extra") or {}).get("finding_ids") or {}).get("final") or {}) if isinstance(manifest,
                                                                                                       dict) else {}
    drafts = [f for f in (ass or {}).get("finding_drafts") or [] if isinstance(f, dict)]
    shard_of = _shard_of((ass or {}).get("finding_ids") or {})
    rmaps = (ref or {}).get("finding_ids") or {}
    rmap = rmaps.get("refine") or {}
    rfields = set(rmaps.get("refine_fields") or {})
    after_refine = {str(f.get("id")) for f in (ref or {}).get("finding_drafts") or [] if isinstance(f, dict)}
    meta = (ref or {}).get("finding_meta") or {}
    fallback = r.last("refine_fallback") is not None
    vmaps = (ver or {}).get("finding_ids") or {}
    vmap = vmaps.get("verify") or {}
    unverified = {str(x) for x in vmaps.get("unverified") or []}
    verified = {str(f.get("id")) for f in (ver or {}).get("findings") or [] if isinstance(f, dict)}
    reported = {str(f.get("id")) for f in (rep or {}).get("findings") or [] if isinstance(f, dict)} \
        if isinstance(rep, dict) else set()

    def after_verify(fid: str) -> tuple[str, str | None]:
        """(what verify did, the ID it left) for a finding kept by refine."""
        if ver is None:
            return "not verified yet", None
        if fid in unverified:
            return "moved to unresolved (unverified)", None
        if fid in vmap:
            return ("renumbered", vmap[fid]) if vmap[fid] else ("dropped by verify", None)
        return ("verified", fid) if fid in verified else ("not in the verified set", None)

    rows = []
    for d in drafts:
        fid = str(d.get("id"))
        name, local = shard_of.get(fid, (None, None))
        row: dict[str, Any] = {"draft_id": fid, "shard": name, "shard_local_id": local, "title": d.get("title"),
                               "kind": d.get("kind"), "severity": d.get("severity"), "merged_into": None}
        if ref is None:
            row["refine"] = "not recorded"
            row["refine_note"] = "refine has not written its checkpoint"
            target = None
        elif fid in rmap:
            into = rmap[fid]
            row["refine"] = "merged" if into else "withdrawn"
            row["merged_into"] = into
            target = str(into) if into else None
        elif fid in after_refine:
            h = _refine_history(meta, fid)
            if fallback or (rfields and fid not in rfields) or (not rfields and not h):
                row["refine"] = "not refined (counted as unchanged)"
            elif h and h.get("changed_fields"):
                row["refine"] = "revised"
            else:
                row["refine"] = "kept as drafted"
            target = fid
        else:
            row["refine"] = "not recorded"
            target = None
        if target is not None:
            vstep, vid = after_verify(target)
            row["verify"] = vstep
            row["final_id"] = vid if vid in reported else None
        else:
            row["verify"] = None
            row["final_id"] = None
        if row["refine"] == "withdrawn":
            row["fate"] = "withdrawn by refine"
        elif row["refine"] == "merged":
            row["fate"] = (f"merged into {row['merged_into']}" + (f", reported as {row['final_id']}"
                                                                   if row["final_id"] else
                                                                   f"; {row['merged_into']} {row['verify']}"))
        elif row["final_id"]:
            row["fate"] = f"reported as {row['final_id']}"
        elif row.get("verify"):
            row["fate"] = row["verify"]
        else:
            row["fate"] = "not recorded"
        mf = final.get(fid)
        row["manifest_final"] = mf
        row["agrees"] = None if not final or rep is None else (mf == row["final_id"] or (
            mf is not None and row["final_id"] is None and row["refine"] == "withdrawn"))
        rows.append(row)
    return sorted(rows, key=lambda x: _id_order(x["draft_id"]))


def _id_order(fid: str) -> tuple[int, str]:
    m = re.search(r"(\d+)$", fid)
    return (int(m.group(1)) if m else 0, fid)


#: What refine can do to a finding that stays (``refined`` counts the last two as unchanged).
KEPT = ("revised", "kept as drafted", "not refined (counted as unchanged)")


def funnel(run_dir: Path) -> dict[str, Any]:
    """The 66-to-30 path of a run: every merged draft with its fate, the totals by step, and the run's own counts
    (the ``refined`` and ``anchors_verified`` records, the report) beside them."""
    r = Reader(run_dir)
    rows = funnel_rows(r)
    ass, asrc = r.checkpoint("assess")
    ref, rsrc = r.checkpoint("refine")
    ver, vsrc = r.checkpoint("verify")
    rep = r.use("report.json")
    if ass is None:
        r.lack("checkpoints/NN-assess.json", "the merged draft findings")
    if ref is None:
        r.lack("checkpoints/NN-refine.json", "what refine did to each finding")
    if ver is None:
        r.lack("checkpoints/NN-verify.json", "what verify kept")
    if not isinstance(rep, dict):
        r.lack("report.json", "the reported findings")
    if isinstance(r.json("manifest.json"), dict):
        r.use("manifest.json")

    def count(key: str, value: str) -> int:
        return sum(1 for x in rows if x.get(key) == value)

    kept = [x for x in rows if x["refine"] in KEPT]
    totals = {"drafts": len(rows),
              "refine": {k: count("refine", k) for k in (*KEPT, "merged", "withdrawn", "not recorded")},
              "after_refine": len(kept) if ref is not None else None,
              "verify": {k: sum(1 for x in kept if x.get("verify") == k) for k in
                         ("verified", "moved to unresolved (unverified)", "dropped by verify", "renumbered",
                          "not in the verified set", "not verified yet")},
              "reported": len({x["final_id"] for x in kept if x.get("final_id")}) if isinstance(rep, dict) else None,
              "report_findings": len(rep.get("findings") or []) if isinstance(rep, dict) else None}
    recorded = {"merged": _fields(r.last("shards_merged")).get("findings"),
                "refined": _fields(r.last("refined")), "anchors_verified": _fields(r.last("anchors_verified")),
                "verdict_findings": _fields(r.last("verdict")).get("findings")}
    disagree = [x["draft_id"] for x in rows if x.get("agrees") is False]
    items = [{"type": "fate", "key": x["draft_id"], "group": _fate_group(x), **x} for x in rows]
    order = ["reported", "merged into another", "withdrawn by refine", "moved to unresolved (unverified)",
             "dropped by verify", "not recorded"]
    view = _view(r, "funnel", "The findings, from drafts to the report", facts=[], lists=[
        _list("fates", "Every merged draft and what became of it", items,
              src=f"{asrc}, {rsrc}, {vsrc} finding_ids; report.json findings" if asrc else None,
              groups=_groups(items, order), terms=["run-draft", "rev-keep", "rev-merge", "rev-withdraw", "id-FND"],
              empty="No merged draft is recorded yet.")])
    view.update(totals=totals, recorded=recorded, manifest_disagrees=disagree)
    return view


def _fate_group(row: dict[str, Any]) -> str:
    if row["refine"] == "merged":
        return "merged into another"
    if row["refine"] == "withdrawn":
        return "withdrawn by refine"
    if row.get("final_id"):
        return "reported"
    if row.get("verify") in ("moved to unresolved (unverified)", "dropped by verify"):
        return str(row["verify"])
    return "not recorded"


# ------------------------------------------------------------------ the glossary


def glossary(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """The page's legend: every term of the export's one vocabulary (``ui.xref.vocabulary``) as plain text with its
    source, for this run (its criteria and reporting threshold)."""
    from sit_review_agent.ui import xref

    rep = read_json(run_dir / "report.json")
    terms = xref.vocabulary(repo_root, run_dir, rep if isinstance(rep, dict) else {})
    return {"terms": {k: xref.term_text(t) for k, t in terms.items()}}
