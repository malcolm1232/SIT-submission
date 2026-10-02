"""Grader-facing projection of a Review (``spec/README.md`` §1 "Grader-facing projection").

The projection is built by **whitelist**: only the fields named below are copied, so a field
added to the spec later cannot leak into a grader input by default. On top of what the spec
drops (``run_manifest``, ``research_log``, every ``provenance`` block, ``evidence_ledger[].tool`` and
``snapshot_path``), the projection also drops what ``eval/prereg.yaml`` ``grader.input`` forbids
or what could reveal the condition: ``metadata.review_id``/``run_id``/``created_at``/``text_path``
and hashes, ``limitations[].degradation_ids`` (pointers into the dropped research log) and
``stop_reason.detail`` (free text written by the runner from its config, e.g. ``no_tools``).
Finally every string is scrubbed of identifying values found in the dropped parts (model IDs,
run and review IDs, git commit and branch, config and prompt hashes, tool call IDs), unless the
value also occurs in the design document itself.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

REDACTED = "[redacted]"

#: Model IDs of any provider, as they appear in manifests and provenance blocks.
MODEL_ID_RE = re.compile(
    r"\b(?:claude|gpt|gemini|o[1-9]|llama|mistral|command)-[a-z0-9][a-z0-9.\-]*\b", re.I)
#: A Claude model ID split into family and version, e.g. ``claude-opus-5-5`` -> ("opus", "5", "5").
_CLAUDE_ID_RE = re.compile(r"\bclaude-(opus|sonnet|haiku)-(\d+)(?:-(\d+))?\b", re.I)
_ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}(T[\d:.]+Z?)?$")
_MIN_SCRUB_LEN = 6

FINDING_KEYS = ("id", "rank", "kind", "category", "severity", "confidence", "disposition",
                "secondary_dispositions", "title", "statement", "doc_anchors", "evidence", "recommendation",
                "no_change_rationale", "next_step", "affected_decisions", "acknowledged_in_doc", "tags",
                "reassessment")
LEDGER_KEYS = ("evidence_id", "source_type", "authority", "url_or_citation", "title", "retrieved_at",
               "content_sha256", "excerpt", "read_before_cite", "derived_from")
DOCUMENT_KEYS = ("doc_id", "title", "version", "role", "page_count")
#: Top-level Review sections copied as-is (their nested types carry no run metadata in the spec).
VERBATIM_SECTIONS = ("intent_summary", "verdict", "sound_areas", "unresolved", "decision_registry")
#: Paths that must never appear in a projection (checked by :func:`leak_report`).
FORBIDDEN_KEYS = frozenset({"run_manifest", "research_log", "provenance", "prompt_hash", "snapshot_path",
                            "tool", "run_id", "review_id", "text_path", "sha256_pdf", "sha256_text",
                            "degradation_ids", "detail", "created_at", "prior_review_id"})


class GraderInputError(ValueError):
    """The review cannot be graded as given (not JSON, not a Review)."""


def load_review(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise GraderInputError(f"cannot read review {p}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GraderInputError(
            f"{p.name} is not JSON. The grader takes the structured Review (report.json); the segmenter "
            "path for unstructured reviews is not used in Tier A (every condition emits a Review).") from exc
    if not isinstance(data, dict) or "findings" not in data or "verdict" not in data:
        raise GraderInputError(f"{p.name} is not a Review (needs at least 'findings' and 'verdict')")
    return data


# ------------------------------------------------------------------------------- identifying values
def _strings(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)


def _walk_key(node: Any, key: str) -> Iterator[Any]:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                yield v
            yield from _walk_key(v, key)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_key(v, key)


def identifying_values(review: dict[str, Any]) -> set[str]:
    """Strings that would identify the run, model, prompts or condition if they reached the grader."""
    vals: set[str] = set()
    meta = review.get("metadata") or {}
    for k in ("review_id", "run_id", "prior_review_id"):
        if isinstance(meta.get(k), str):
            vals.add(meta[k])
    manifest = review.get("run_manifest") or {}
    for k in ("run_id", "git_commit", "config_sha256", "prompts_bundle_sha256", "bundle_sha256", "taxonomy_sha256",
              "prereg_sha256", "condition", "fault_schedule_id", "git_branch", "effective_config_sha256",
              "pyproject_sha256", "backend", "requested_model", "served_model", "model"):
        for v in _walk_key(manifest, k):
            # direct string values only: a nested object under e.g. "model" holds ordinary words
            if isinstance(v, str):
                vals.add(v)
            elif isinstance(v, list):
                vals.update(x for x in v if isinstance(x, str))
    for s in _strings(manifest):
        vals.update(m.group(0) for m in MODEL_ID_RE.finditer(s))
    # Display forms of the agent's own Claude model and backend ("Opus 5.5", "Claude Code"), which the
    # ID regex does not catch, and every runner flag on the command line (e.g. "--no-tools").
    for s in _strings(manifest):
        for m in _CLAUDE_ID_RE.finditer(s):
            fam, ver = m.group(1).capitalize(), f"{m.group(2)}.{m.group(3)}" if m.group(3) else m.group(2)
            vals.update({f"{fam} {ver}", f"Claude {fam} {ver}"})
    if any(v == "claude_code" for v in _walk_key(manifest, "backend")):
        vals.add("Claude Code")
    for argv in _walk_key(manifest, "argv"):
        if isinstance(argv, list):
            vals.update(a.split("=", 1)[0] for a in argv if isinstance(a, str) and a.startswith("--"))
    # The runner's stop detail is dropped from the projection; its value must not come back through
    # agent-written text (e.g. "no_tools" copied into a limitation).
    sr = review.get("stop_reason")
    if isinstance(sr, dict) and isinstance(sr.get("detail"), str):
        vals.add(sr["detail"])
    for prov in _walk_key(review, "provenance"):
        if isinstance(prov, dict):
            vals.update(str(prov.get(k)) for k in ("model", "prompt_hash") if prov.get(k))
    for tool in _walk_key(review.get("evidence_ledger") or [], "tool"):
        if isinstance(tool, dict):   # server and call id identify the run; a tool name is an ordinary word
            vals.update(str(tool[k]) for k in ("server", "call_id") if tool.get(k))
    for e in review.get("evidence_ledger") or []:
        if isinstance(e, dict) and e.get("snapshot_path"):
            vals.add(str(e["snapshot_path"]))
    log = review.get("research_log") or {}
    for call in log.get("tool_calls") or []:
        if isinstance(call, dict):
            vals.update(str(call[k]) for k in ("call_id", "server") if call.get(k))
    for d in meta.get("documents") or []:
        if isinstance(d, dict) and d.get("text_path"):
            vals.add(str(d["text_path"]))
    out = {v for v in vals if len(v) >= _MIN_SCRUB_LEN and not _ISO_TS.match(v)}
    # Condition names are short ("B0", "FULL", "A5"); they are identifying at any length.
    out.update(v for v in _walk_key(manifest, "condition") if isinstance(v, str) and len(v) >= 2)
    return out


def _value_pattern(values: set[str]) -> re.Pattern[str] | None:
    """Whole-token matches of ``values``, longest first (a run id inside a review id goes as a whole)."""
    if not values:
        return None
    alts = "|".join(re.escape(v) for v in sorted(values, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9_])(?:{alts})(?![A-Za-z0-9_])")


def _scrub(node: Any, pattern: re.Pattern[str] | None, counter: list[int]) -> Any:
    if isinstance(node, str):
        if pattern is None:
            return node
        new, n = pattern.subn(REDACTED, node)
        counter[0] += n
        return new
    if isinstance(node, list):
        return [_scrub(v, pattern, counter) for v in node]
    if isinstance(node, dict):
        return {k: _scrub(v, pattern, counter) for k, v in node.items()}
    return node


# ---------------------------------------------------------------------------------------- project
def project_review(review: dict[str, Any], *, design_text: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(projection, audit)``. ``audit`` records what was dropped and how many strings were scrubbed."""
    meta = review.get("metadata") or {}
    proj: dict[str, Any] = {
        "metadata": {
            "review_mode": meta.get("review_mode", "full"),
            "documents": [{k: d.get(k) for k in DOCUMENT_KEYS if k in d}
                          for d in meta.get("documents") or [] if isinstance(d, dict)],
        },
    }
    for sec in ("intent_summary", "verdict"):
        if sec in review:
            proj[sec] = review[sec]
    proj["findings"] = [{k: f[k] for k in FINDING_KEYS if k in f}
                        for f in review.get("findings") or [] if isinstance(f, dict)]
    for sec in ("sound_areas", "unresolved", "decision_registry"):
        proj[sec] = review.get(sec) or []
    proj["evidence_ledger"] = [{k: e[k] for k in LEDGER_KEYS if k in e}
                               for e in review.get("evidence_ledger") or [] if isinstance(e, dict)]
    proj["limitations"] = [{"text": lim.get("text")} for lim in review.get("limitations") or []
                           if isinstance(lim, dict)]
    sr = review.get("stop_reason")
    if isinstance(sr, dict):
        proj["stop_reason"] = {k: sr.get(k) for k in ("code", "group")}

    ident = {v for v in identifying_values(review) if v not in design_text}
    pattern = _value_pattern(ident)
    counter = [0]
    proj = _scrub(proj, pattern, counter)
    # model IDs anywhere in the remaining text, unless the design itself names them
    model_counter = [0]

    def scrub_models(node: Any) -> Any:
        if isinstance(node, str):
            def sub(m: re.Match[str]) -> str:
                if m.group(0) in design_text:
                    return m.group(0)
                model_counter[0] += 1
                return REDACTED
            return MODEL_ID_RE.sub(sub, node)
        if isinstance(node, list):
            return [scrub_models(v) for v in node]
        if isinstance(node, dict):
            return {k: scrub_models(v) for k, v in node.items()}
        return node

    proj = scrub_models(proj)
    audit = {"dropped_top_level": sorted(k for k in review if k not in proj),
             "dropped_metadata": sorted(k for k in meta if k not in ("review_mode", "documents")),
             "identifying_values": len(ident), "strings_scrubbed": counter[0] + model_counter[0]}
    return proj, audit


def leak_report(texts: Iterable[str], review: dict[str, Any], *, design_text: str = "") -> list[str]:
    """Identifying values or forbidden field names found in rendered grader inputs (empty = clean)."""
    hits: list[str] = []
    ident = {v for v in identifying_values(review) if v not in design_text}
    for t in texts:
        body = t.replace(design_text, "") if design_text else t
        pat = _value_pattern(ident)
        hits += sorted({m.group(0) for m in pat.finditer(body)}) if pat else []
        for key in ("run_manifest", "research_log", "provenance", "prompt_hash", "snapshot_path"):
            if f'"{key}"' in body:
                hits.append(f"field:{key}")
        hits += sorted({m.group(0) for m in MODEL_ID_RE.finditer(body) if m.group(0) not in design_text})
    return sorted(set(hits))


# ------------------------------------------------------------------------------------- rendering
def _compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))


def findings_for_pass_a(proj: dict[str, Any]) -> list[dict[str, Any]]:
    """Findings as Pass A sees them: no ``rank`` (order is withheld, GR §6.2 "Position / order"),
    and ``affected_decisions`` resolved against the decision registry so the finding is readable
    without the framing."""
    reg = {d.get("registry_id"): d for d in proj.get("decision_registry") or [] if isinstance(d, dict)}
    out = []
    for f in proj.get("findings") or []:
        g = {k: v for k, v in f.items() if k != "rank"}
        if g.get("affected_decisions"):
            g["affected_decisions"] = [
                {**ad, "decision": {k: reg[ad.get("registry_id")].get(k) for k in ("type", "doc_ref", "statement")}}
                if isinstance(ad, dict) and ad.get("registry_id") in reg else ad
                for ad in g["affected_decisions"]]
        out.append(g)
    return out


def shuffle_findings(proj: dict[str, Any], shuffle_seed: int) -> tuple[str, list[str]]:
    """``(text, order)``: Pass A findings shuffled with ``random.Random(shuffle_seed)``, one JSON object
    per line. ``order`` lists the finding IDs in the order shown (recorded in grade.json)."""
    items = findings_for_pass_a(proj)
    random.Random(shuffle_seed).shuffle(items)
    return "\n".join(_compact(f) for f in items), [str(f.get("id")) for f in items]


def review_full_text(proj: dict[str, Any]) -> str:
    """The intact review for Pass B: the projection without the ledger (sent as the evidence
    register), findings in the review's own rank order, one top-level section and one list item
    per line."""
    body = {k: v for k, v in proj.items() if k != "evidence_ledger"}
    if isinstance(body.get("findings"), list):
        body["findings"] = sorted(body["findings"], key=lambda f: (f.get("rank") is None, f.get("rank") or 0))
    lines = ["{"]
    keys = list(body)
    for i, k in enumerate(keys):
        v = body[k]
        comma = "," if i < len(keys) - 1 else ""
        if isinstance(v, list) and v:
            lines.append(f'"{k}": [')
            lines += [_compact(x) + ("," if j < len(v) - 1 else "") for j, x in enumerate(v)]
            lines.append("]" + comma)
        else:
            lines.append(f'"{k}": {_compact(v)}{comma}')
    lines.append("}")
    return "\n".join(lines)


def evidence_register(proj: dict[str, Any]) -> str:
    ledger = proj.get("evidence_ledger") or []
    return "\n".join(_compact(e) for e in ledger) if ledger else "NONE"
