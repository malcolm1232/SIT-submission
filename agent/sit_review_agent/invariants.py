"""Shared run invariants INV-03..INV-10, INV-12 and INV-13 (research/robustness/README.md §2), checked after every run
by ``selftest``, the verify/report phases and the robustness oracles.

Each ``check_INV_xx`` takes a :class:`~sit_review_agent.models.Review` (or its JSON dict) and, where
needed, the run directory, and returns an :class:`InvariantResult`. The cross-field rules port
``review_semantics`` and ``anchors_resolve`` of ``spec/validate_examples.py`` so the agent and the
spec checks agree. INV-01 (terminates), INV-02 (output or failure record) and INV-11 (no
traceback) are process-level and live in the test harness.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource

from sit_review_agent.finding_refs import dangling_refs
from sit_review_agent.hashing import registry_sha256
from sit_review_agent.ingest.anchor import AnchorRules, verify_anchor
from sit_review_agent.ingest.pdf import Document
from sit_review_agent.models import STOP_REASON_GROUP, ManifestExtra, Review, StopReasonCode
from sit_review_agent.paths import finding_schema_path

FINDING_SCHEMA_ID = "https://sit-design-review.invalid/spec/finding.schema.json"
URL_RE = re.compile(r"https?://[^\s)\]>\"']+|\b10\.\d{4,9}/[^\s)\]>\"']+")
#: INV-06 minimum length for recommendation text fields (characters, after stripping).
MIN_TEXT_CHARS = 15


@dataclass(frozen=True)
class InvariantResult:
    inv_id: str
    passed: bool
    problems: list[str] = field(default_factory=list)
    skipped: bool = False
    reason: str = ""


def _ok(inv: str, problems: list[str]) -> InvariantResult:
    return InvariantResult(inv_id=inv, passed=not problems, problems=problems)


def _as_dict(review: Review | Mapping[str, Any]) -> dict[str, Any]:
    return review.model_dump(mode="json") if isinstance(review, Review) else dict(review)


@lru_cache(maxsize=4)
def spec_validator(def_name: str = "Review") -> Draft202012Validator:
    """jsonschema validator for ``#/$defs/<def_name>`` of spec/finding.schema.json."""
    schema = json.loads(finding_schema_path().read_text(encoding="utf-8"))
    registry = Registry().with_resource(FINDING_SCHEMA_ID, Resource.from_contents(schema))
    return Draft202012Validator({"$ref": f"{FINDING_SCHEMA_ID}#/$defs/{def_name}"}, registry=registry)


def _strings(node: Any, skip: Iterable[str] = ()) -> Iterator[str]:
    skip = tuple(skip)
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v, skip)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k not in skip:
                yield from _strings(v, skip)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


# ======================================================================================== INV-03


def check_INV_03(review: Review | Mapping[str, Any], run_dir: Path | None = None) -> InvariantResult:
    """Schema-valid Review (spec ``#/$defs/Review``) plus the structural cross-field rules:
    unique finding IDs and ranks, anchor doc IDs known, stop-reason group, verdict and unresolved
    references, non-refinement findings listed in ``unresolved[]`` (lab §2.4)."""
    r = _as_dict(review)
    problems = [f"schema: {'/'.join(map(str, e.absolute_path))}: {e.message}"
                for e in spec_validator("Review").iter_errors(r)]
    if problems:
        return _ok("INV-03", problems)
    try:
        Review.model_validate(r)
    except ValidationError as exc:
        problems.append(f"model: {exc.errors()[0]['msg']}")
    fids = [f["id"] for f in r["findings"]]
    if len(fids) != len(set(fids)):
        problems.append("duplicate finding ids")
    ranks = [f["rank"] for f in r["findings"]]
    if len(set(ranks)) != len(ranks):
        problems.append("finding ranks are not unique")
    if STOP_REASON_GROUP[StopReasonCode(r["stop_reason"]["code"])].value != r["stop_reason"]["group"]:
        problems.append("stop_reason.group does not match taxonomy")
    doc_ids = {d["doc_id"] for d in r["metadata"]["documents"]}
    pages = {d["doc_id"]: d["page_count"] for d in r["metadata"]["documents"]}
    for owner, a in _all_anchors(r):
        if a["doc_id"] not in doc_ids:
            problems.append(f"{owner}: anchor doc_id {a['doc_id']} not in metadata.documents")
        elif a["page"] is not None and pages[a["doc_id"]] is not None and a["page"] > pages[a["doc_id"]]:
            problems.append(f"{owner}: anchor page {a['page']} beyond page_count")
    known = set(fids)
    for c in r["verdict"]["conditions"]:
        problems += [f"verdict condition cites unknown {x}" for x in c["finding_ids"] if x not in known]
    for po in r["verdict"]["per_objective"]:
        problems += [f"per_objective cites unknown {x}" for x in po["finding_ids"] if x not in known]
    for u in r["unresolved"]:
        problems += [f"unresolved cites unknown {x}" for x in u["finding_ids"] if x not in known]
    for s in r["sound_areas"]:
        problems += [f"{s['id']}: related finding {x} unknown" for x in s["related_finding_ids"] if x not in known]
    listed = {x for u in r["unresolved"] for x in u["finding_ids"]}
    for f in r["findings"]:
        if f["disposition"] in {"needs_investigation", "needs_prototyping", "needs_testing", "governance_decision"} \
                and f["id"] not in listed:
            problems.append(f"{f['id']}: non-refinement finding missing from unresolved[] (lab §2.4)")
    return _ok("INV-03", problems)


def _all_anchors(r: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return ([(f["id"], a) for f in r["findings"] for a in f["doc_anchors"]]
            + [(s["id"], a) for s in r["sound_areas"] for a in s["doc_anchors"]]
            + [(e["registry_id"], e["doc_anchor"]) for e in r["decision_registry"]]
            + [("intent", a) for a in r["intent_summary"]["doc_anchors"]])


# ======================================================================================== INV-04


def _load_texts(r: Mapping[str, Any], run_dir: Path | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for d in r["metadata"]["documents"]:
        candidates = [Path(d["text_path"])]
        if run_dir is not None:
            candidates.insert(0, Path(run_dir) / d["text_path"])
        for c in candidates:
            if c.is_file():
                out[d["doc_id"]] = c.read_text(encoding="utf-8")
                break
    return out


def check_INV_04(review: Review | Mapping[str, Any], run_dir: Path | None = None, *,
                 texts: Mapping[str, str] | None = None, rules: AnchorRules = AnchorRules()) -> InvariantResult:
    """Every anchor (findings, sound areas, registry, intent) resolves in the canonical text named
    by ``documents[].text_path`` (or ``texts``: doc_id -> page-marked text), using the same
    :func:`~sit_review_agent.ingest.anchor.verify_anchor` as the verify phase; 1-3 anchors per finding."""
    r = _as_dict(review)
    raw = dict(texts) if texts is not None else _load_texts(r, run_dir)
    docs = {k: Document.from_page_marked_text(v, doc_id=k) for k, v in raw.items()}
    problems: list[str] = []
    for f in r["findings"]:
        if not rules.min_anchors <= len(f["doc_anchors"]) <= rules.max_anchors:
            problems.append(f"{f['id']}: {len(f['doc_anchors'])} anchors "
                            f"(allowed {rules.min_anchors}-{rules.max_anchors})")
    for owner, a in _all_anchors(r):
        doc = docs.get(a["doc_id"])
        if doc is None:
            problems.append(f"{owner}: no canonical text for {a['doc_id']}")
            continue
        res = verify_anchor(doc, a["quote"], a["page"], a["section_ref"], rules)
        if not res.ok:
            problems.append(f"{owner}: anchor p{a['page']} s{a['section_ref']} unresolved ({', '.join(res.reasons)})")
    return _ok("INV-04", problems)


# ======================================================================================== INV-05


def check_INV_05(review: Review | Mapping[str, Any], run_dir: Path | None = None) -> InvariantResult:
    """Every cited evidence ID is in the ledger and hydrated from it; doc/external quotes occur in
    the ledger excerpt; external entries resolve to an ``ok`` tool call of the same server/tool and
    were read before being cited; no URL or DOI in report text outside the ledger."""
    r = _as_dict(review)
    problems: list[str] = []
    ledger = {e["evidence_id"]: e for e in r["evidence_ledger"]}
    for e in r["evidence_ledger"]:
        problems += [f"ledger {e['evidence_id']}: derived_from {d} not in ledger" for d in e["derived_from"]
                     if d not in ledger]
    cited: set[str] = set()
    for f in r["findings"]:
        for e in f["evidence"]:
            cited.add(e["evidence_id"])
            le = ledger.get(e["evidence_id"])
            if le is None:
                problems.append(f"{f['id']}: evidence {e['evidence_id']} not in ledger")
                continue
            if le["source_type"] != e["source_type"]:
                problems.append(f"{f['id']}: evidence {e['evidence_id']} source_type differs from ledger")
            if le["url_or_citation"] != e["url_or_citation"] or le["retrieved_at"] != e["retrieved_at"]:
                problems.append(f"{f['id']}: evidence {e['evidence_id']} not hydrated from ledger")
            if e["source_type"] in ("doc", "external") and le["excerpt"] and e["quote"] \
                    and _norm(e["quote"]) not in _norm(le["excerpt"]):
                problems.append(f"{f['id']}: evidence {e['evidence_id']} quote not in the ledger excerpt")
            problems += [f"{f['id']}: derived_from {d} not in ledger" for d in e["derived_from"] if d not in ledger]
    for s in r["sound_areas"]:
        cited |= set(s["evidence_ids"])
        problems += [f"{s['id']}: evidence {x} not in ledger" for x in s["evidence_ids"] if x not in ledger]
    calls = {c["call_id"]: c for c in r["research_log"]["tool_calls"]}
    for e in r["evidence_ledger"]:
        if e["source_type"] != "external":
            continue
        c = calls.get(e["tool"]["call_id"])
        if c is None:
            problems.append(f"ledger {e['evidence_id']}: tool call {e['tool']['call_id']} not in research_log")
        elif c["status"] != "ok" or c["server"] != e["tool"]["server"] or c["tool_name"] != e["tool"]["tool_name"]:
            problems.append(f"ledger {e['evidence_id']}: {c['call_id']} is not an ok "
                            f"{e['tool']['server']}/{e['tool']['tool_name']} call")
        if e["evidence_id"] in cited and not e["read_before_cite"]:
            problems.append(f"ledger {e['evidence_id']}: cited but not read before citing")
    allowed = {e["url_or_citation"] for e in r["evidence_ledger"]}
    free = {k: v for k, v in r.items() if k not in ("evidence_ledger", "run_manifest", "metadata")}
    for t in _strings(free, skip=("url_or_citation",)):
        for u in URL_RE.findall(t):
            if u.rstrip(".,;:") not in allowed:
                problems.append(f"URL/DOI in report text not in the ledger: {u}")
    return _ok("INV-05", problems)


# ======================================================================================== INV-06


def check_INV_06(review: Review | Mapping[str, Any], run_dir: Path | None = None) -> InvariantResult:
    """Every recommendation has issue, rationale, expected benefit, change summary (each at least
    ``MIN_TEXT_CHARS``), objective refs and supporting evidence that is a subset of the finding's
    evidence and never contrary evidence; non-refinement dispositions have ``next_step``."""
    r = _as_dict(review)
    problems: list[str] = []
    for f in r["findings"]:
        rec = f["recommendation"]
        if f["disposition"] == "no_change":
            if not (f["no_change_rationale"] or "").strip():
                problems.append(f"{f['id']}: no_change without rationale")
            continue
        if rec is None:
            problems.append(f"{f['id']}: {f['disposition']} without a recommendation")
            continue
        for k in ("issue", "rationale", "expected_benefit", "change_summary"):
            if len((rec[k] or "").strip()) < MIN_TEXT_CHARS:
                problems.append(f"{f['id']}: recommendation.{k} shorter than {MIN_TEXT_CHARS} characters")
        if not rec["objective_refs"]:
            problems.append(f"{f['id']}: recommendation has no objective_refs")
        by_id = {e["evidence_id"]: e for e in f["evidence"]}
        for x in rec["supporting_evidence_ids"]:
            if x not in by_id:
                problems.append(f"{f['id']}: recommendation cites evidence {x} not in the finding")
            elif not by_id[x]["supports_claim"]:
                problems.append(f"{f['id']}: recommendation cites contrary evidence {x} as support")
        if f["disposition"] != "refinement_now" and f["next_step"] is None:
            problems.append(f"{f['id']}: {f['disposition']} without next_step")
    return _ok("INV-06", problems)


# ======================================================================================== INV-07


def check_INV_07(review: Review | Mapping[str, Any], run_dir: Path | None = None) -> InvariantResult:
    """Every degradation is cited by a limitation (and vice versa); fallbacks, cap stops,
    tool-failure stops and failed tool calls are recorded as degradations."""
    r = _as_dict(review)
    problems: list[str] = []
    degs = r["research_log"]["degradations"]
    ids = [d["id"] for d in degs]
    if len(ids) != len(set(ids)):
        problems.append("duplicate degradation ids")
    cited = {x for lim in r["limitations"] for x in lim["degradation_ids"]}
    problems += [f"degradation {x} not disclosed in limitations" for x in ids if x not in cited]
    problems += [f"limitation cites unknown degradation {x}" for x in cited if x not in ids]
    types = [d["type"] for d in degs]
    if types.count("model_fallback") < len(r["run_manifest"]["fallback_events"]):
        problems.append("model fallback events not all recorded as degradations")
    sr = r["stop_reason"]
    if sr["group"] == "cap" and "budget_or_deadline_hit" not in types:
        problems.append("cap stop reason not disclosed as budget_or_deadline_hit")
    tool_types = {"tool_unavailable", "tool_error"}
    if sr["code"] == "tool_failure" and not tool_types & set(types):
        problems.append("tool_failure stop reason not disclosed as a tool degradation")
    failed_calls = any(c["status"] in ("error", "timeout") for c in r["research_log"]["tool_calls"])
    if failed_calls and not tool_types & set(types):
        problems.append("failed tool calls not disclosed as a tool degradation")
    return _ok("INV-07", problems)


# ======================================================================================== INV-08


def check_INV_08(run_dir: Path, canaries: Sequence[str]) -> InvariantResult:
    """No canary secret appears in any file of the run directory (report, logs, ledger,
    checkpoints, snapshots). The outbound-request half of INV-08 needs the recording proxy's log
    and is checked by the robustness harness on the laptop, not here.

    ``llm.jsonl`` is in scope: INV-08 says "any artefact (report, log, ...)", and the model can
    write a canary into a ``tool_use`` input (ADV-05) that the tool policy then blocks. Every
    gateway therefore logs through ``llm.gateway.LLMCallLog``, which applies
    ``llm.gateway.redact_log_entry`` (configured secrets and canary tokens) to each entry."""
    if not canaries:
        return InvariantResult("INV-08", passed=True, skipped=True, reason="no canaries given")
    problems: list[str] = []
    for p in sorted(Path(run_dir).rglob("*")):
        if p.is_file():
            data = p.read_bytes()
            problems += [f"canary found in {p.relative_to(run_dir)}" for c in canaries if c.encode() in data]
    return _ok("INV-08", problems)


# ======================================================================================== INV-09


#: ManifestExtra keys that must be non-empty for INV-09 (REPRODUCIBILITY §8 starred fields).
REQUIRED_EXTRA = ("doc", "code", "prompts", "config", "model", "tools", "stop", "timing", "outputs")


def check_INV_09(review: Review | Mapping[str, Any], run_dir: Path | None = None, *,
                 require_extra: bool = True) -> InvariantResult:
    """Manifest complete: spec ``RunManifest`` valid (git SHA, config/prompt/taxonomy hashes,
    criteria, stop rule, models used, tools, fault-schedule ID, extractor) and, unless
    ``require_extra`` is false, ``extra`` is a valid :class:`ManifestExtra` with the REPRODUCIBILITY
    §8 groups filled in; ``manifest.json`` in ``run_dir`` equals the Review's manifest."""
    r = _as_dict(review)
    m = r["run_manifest"]
    problems = [f"schema: {'/'.join(map(str, e.absolute_path))}: {e.message}"
                for e in spec_validator("RunManifest").iter_errors(m)]
    if not m["review_config"]["criteria"]:
        problems.append("review_config.criteria empty")
    if require_extra:
        try:
            extra = ManifestExtra.model_validate(m["extra"])
            problems += [f"manifest extra.{k} empty" for k in REQUIRED_EXTRA if not getattr(extra, k)]
        except ValidationError as exc:
            problems.append(f"manifest extra invalid: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}")
    if run_dir is not None:
        path = Path(run_dir) / "manifest.json"
        if not path.is_file():
            problems.append("manifest.json missing")
        elif json.loads(path.read_text(encoding="utf-8")) != m:
            problems.append("manifest.json differs from report.json run_manifest")
    return _ok("INV-09", problems)


# ======================================================================================== INV-10


def check_INV_10(review: Review | Mapping[str, Any], run_dir: Path | None = None) -> InvariantResult:
    """Registry hash constant across iterations and equal to the final registry's hash; every
    ``affected_decisions`` ID exists; a ``challenges`` relation has >= 2 evidence items and a
    disposition other than ``no_change``. (Undeclared conflicts need the L1 judge.)"""
    r = _as_dict(review)
    problems: list[str] = []
    h = registry_sha256(r["decision_registry"])
    for x in r["research_log"]["registry_sha256_by_iteration"]:
        if x["sha256"] != h:
            problems.append(f"registry hash at iteration {x['iteration']} differs from the final registry")
    ids = {e["registry_id"] for e in r["decision_registry"]}
    for f in r["findings"]:
        for ad in f["affected_decisions"]:
            if ad["registry_id"] not in ids:
                problems.append(f"{f['id']}: affected decision {ad['registry_id']} not in registry")
            if ad["relation"] == "challenges":
                if len(f["evidence"]) < 2:
                    problems.append(f"{f['id']}: challenges {ad['registry_id']} with < 2 evidence items")
                if f["disposition"] == "no_change":
                    problems.append(f"{f['id']}: challenges {ad['registry_id']} with disposition no_change")
    return _ok("INV-10", problems)


# ======================================================================================== INV-12


def check_INV_12(review: Review | Mapping[str, Any], run_dir: Path | None = None) -> InvariantResult:
    """Every finding ID the review cites is a finding of the review (merged-ID traceability,
    2026-10-03): text and ID lists in every section but ``metadata``, ``evidence_ledger`` and
    ``run_manifest``, minus a finding's own ``id``, verbatim ``quote`` / ``excerpt`` passages and
    ``reassessment`` (the prior review's numbering). A disclosure (``research_log.degradations``,
    ``limitations``) may name a draft as ``draft FND-nnn`` when ``extra.finding_ids.final`` lists it; in
    delta mode an ID in ``extra.finding_ids.prior`` cites the prior review. Rules and walk:
    :mod:`sit_review_agent.finding_refs`."""
    return _ok("INV-12", dangling_refs(_as_dict(review)))


def _prior_ids_from_run(run_dir: Path | None) -> list[str] | None:
    """The finding IDs of the previous review of the delta run in ``run_dir`` (its ``state.json``
    names the previous run directory), or ``None`` when that cannot be read."""
    if run_dir is None:
        return None
    try:
        state = json.loads((Path(run_dir) / "state.json").read_text(encoding="utf-8"))
        prev = state.get("previous_run_dir")
        if not prev:
            return None
        prior = json.loads((Path(prev) / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return None
    return [str(f["id"]) for f in prior.get("findings") or [] if isinstance(f, dict) and f.get("id")]


def check_INV_13(review: Review | Mapping[str, Any], run_dir: Path | None = None, *,
                 prior_ids: Sequence[str] | None = None) -> InvariantResult:
    """INV-13 (re-assessment, lab §1.5; 2026-10-03): in a delta review every finding of the previous
    review has exactly one status in ``prior_findings``, and the table lists no other ID. The
    previous review's IDs are ``prior_ids``, else read through ``run_dir``'s ``state.json``.
    A full review must have an empty table. Skipped for a delta review with no previous review
    (``--v1``), a previous review that cannot be read, and a report written before the table existed
    (no ``prior_findings`` key)."""
    r = _as_dict(review)
    if (r.get("metadata") or {}).get("review_mode") != "delta":
        return _ok("INV-13", ["a full review has prior_findings"] if r.get("prior_findings") else [])
    if "prior_findings" not in r:
        return InvariantResult("INV-13", passed=True, skipped=True,
                               reason="report has no prior_findings (written before 2026-10-03)")
    ids = list(prior_ids) if prior_ids is not None else _prior_ids_from_run(run_dir)
    if ids is None:
        return InvariantResult("INV-13", passed=True, skipped=True, reason="previous review not available")
    listed = [str(e.get("prior_id")) for e in r.get("prior_findings") or []]
    problems = [f"prior finding {pid} has no status in prior_findings" for pid in ids if pid not in listed]
    problems += [f"prior finding {pid} has {listed.count(pid)} statuses" for pid in dict.fromkeys(listed)
                 if listed.count(pid) > 1]
    problems += [f"prior_findings lists {pid}, which is no finding of the previous review" for pid in
                 dict.fromkeys(listed) if pid not in ids]
    return _ok("INV-13", problems)


def check_all(review: Review | Mapping[str, Any], run_dir: Path | None = None, *,
              canaries: Sequence[str] = (), texts: Mapping[str, str] | None = None,
              require_extra: bool = True, prior_ids: Sequence[str] | None = None) -> list[InvariantResult]:
    out = [check_INV_03(review, run_dir), check_INV_04(review, run_dir, texts=texts), check_INV_05(review, run_dir),
           check_INV_06(review, run_dir), check_INV_07(review, run_dir)]
    out.append(check_INV_08(run_dir, canaries) if run_dir is not None
               else InvariantResult("INV-08", passed=True, skipped=True, reason="no run directory"))
    out += [check_INV_09(review, run_dir, require_extra=require_extra), check_INV_10(review, run_dir),
            check_INV_12(review, run_dir), check_INV_13(review, run_dir, prior_ids=prior_ids)]
    return out
