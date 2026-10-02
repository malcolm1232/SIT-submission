#!/usr/bin/env python3
"""Convert the five legacy answer keys to the canonical schema (spec/answer_key.schema.json).

Reads   eval/<tier>/<item>/answer_key.json          (never modified)
Writes  eval/<tier>/<item>/answer_key.canonical.json
Checks  each output against answer_key.schema.json and the cross-field rules in validate_examples.key_semantics,
        asserts the dropped legacy count fields equal the recomputed values, and prints per-key counts plus every
        legacy field it could not map.

Mapping follows spec/README.md §2 and taxonomy.yaml legacy_mappings. Fields that need a human (core_insight,
anchor quotes, expected dispositions, approved decisions, provenance, canary, external-fact verification, v2
changed sections) are written as null / [] and listed in authoring_status.pending. Nothing is invented by the
converter itself.

Agent drafts (spec/README.md §2.9). If a legacy key carries a top-level `authoring_drafts` block, its values are
copied into the canonical key, the drafted field names are listed in authoring_status.drafts.fields, and they stay
in authoring_status.pending until `authoring_drafts.signoff` names a signer, a date and the accepted fields.
scored_run_ready is true only when pending is empty (key_semantics then checks every flaw is complete).

Usage: python3 spec/convert_answer_keys.py [--check] [--tier synthetic|blind] [--verify-anchors]
  --check           validate only, do not write
  --tier T          convert only the items of tier T (repeatable). With only `synthetic`, the spec self-test that
                    this script runs on import is kept from reading eval/blind (its legacy-coverage glob is filtered),
                    so a synthetic-only run never opens a sealed S-heldout file (SEALING.md §6 rule 1).
  --verify-anchors  also check every flaw and approved-decision anchor quote against the PDF text produced by the
                    agent's own ingest (sit_review_agent.ingest.pdf.ingest): exact match and page. Needs the agent
                    package installed (e.g. `. .venv/bin/activate`).
"""
from __future__ import annotations

import contextlib
import glob
import hashlib
import io
import json
import os
import re
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _tiers_from_argv(argv: list[str]) -> set[str]:
    out = {argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--tier"}
    out |= {a.split("=", 1)[1] for a in argv if a.startswith("--tier=")}
    unknown = out - {"synthetic", "blind"}
    if unknown:
        sys.exit(f"unknown --tier {sorted(unknown)}; use synthetic or blind")
    return out or {"synthetic", "blind"}


TIERS = _tiers_from_argv(sys.argv[1:])
_BLIND_DIR = os.path.join(ROOT, "eval", "blind") + os.sep


@contextlib.contextmanager
def _no_blind_glob():
    """While validate_examples.py runs, keep its legacy-coverage glob out of eval/blind: an `eval/*/...` pattern is
    expanded tier by tier without ever listing or opening anything inside eval/blind."""
    real = glob.glob
    eval_dir = os.path.join(ROOT, "eval")
    wildcard = os.path.join(eval_dir, "*") + os.sep

    def filtered(pattern, *a, **kw):
        pattern = os.fspath(pattern)
        if os.path.abspath(pattern).startswith(wildcard):
            rest = os.path.abspath(pattern)[len(wildcard):]
            tiers = sorted(t for t in os.listdir(eval_dir) if t != "blind" and os.path.isdir(os.path.join(eval_dir, t)))
            hits = [h for t in tiers for h in real(os.path.join(eval_dir, t, rest), *a, **kw)]
        else:
            hits = real(pattern, *a, **kw)
        return [h for h in hits if not os.path.abspath(h).startswith(_BLIND_DIR)]

    glob.glob = filtered
    try:
        yield
    finally:
        glob.glob = real


# Reuse the validators and the taxonomy loaded by validate_examples.py (it also self-tests the spec).
_buf = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf), (_no_blind_glob() if "blind" not in TIERS else contextlib.nullcontext()):
        V = runpy.run_path(os.path.join(HERE, "validate_examples.py"))
except SystemExit as exc:  # validate_examples failed: the spec itself is broken
    sys.stdout.write(_buf.getvalue())
    sys.exit(f"spec self-test failed (exit {exc.code}); fix spec/ before converting")
TAX, LM, V_KEY, errors, key_semantics = V["TAX"], V["LM"], V["V_KEY"], V["errors"], V["key_semantics"]
CAT_KINDS = {c["id"]: c["acceptable_kinds"] for c in TAX["categories"]}

ITEMS = [
    ("synthetic", "payments_orchestration", "synthetic_json_v0"),
    ("synthetic", "clinical_rpm", "synthetic_json_v0"),
    ("synthetic", "research_lakehouse", "synthetic_json_v0"),
    ("blind", "item_a", "blind_a_json_v0"),
    ("blind", "item_b", "blind_b_json_v0"),
]

# README §2.2: synthetic flaws whose external fact eval_data_audit Task 1 checked.
NEEDS_EXTERNAL = {
    "payments_orchestration": {"F01", "F04", "F06", "F07", "F11", "F15"},
    "clinical_rpm": {"F01", "F03", "F04", "F06", "F07", "F08", "F09", "F11", "F15"},
    "research_lakehouse": {"F04", "F05", "F06", "F10", "F15"},
}

# README §2.7 (eval_data_audit Task 6 / P1 #9): (legacy sound-section string prefix, flaw ids).
OVERLAPS = {
    "clinical_rpm": [("4 (", ["F05", "F06"])],
    "research_lakehouse": [("4 Data Classification", ["F01"]), ("14.6", ["F05"]), ("16 Audit", ["F08"]), ("9 Ingestion", ["F15"])],
    "item_a": [("3.1.3 FR-RET-01", ["D03"])],
    "item_b": [("7.5 ", ["DEF-03", "DEF-13"]), ("FR-GRID-01", ["DEF-14"]), ("5.5, 7.9 and D-02", ["DEF-02"])],
}
V1_ONLY_SOUND = {"research_lakehouse": ["9 Ingestion"]}  # README §2.2: lakehouse §9 WAP applies to v1 only

# eval_data_audit.md P2 #14 neutral observations, copied verbatim; placed on the sound section they concern, else item level.
AUDIT_OBSERVATIONS = {
    "item_a": [(None, "The collection offer removes the Art. 13(3) withholding right."),
               (None, "§6.7 idempotency is scoped by channel.")],
    "payments_orchestration": [("23 ", "§23: the 24-h attribution belongs to Stripe, not the IETF draft.")],
    "clinical_rpm": [("6.2", "§6.2: `device_ts` semantics are ambiguous, and batching against the 5-s tolerance may drop live messages.")],
    "research_lakehouse": [(None, "v2: the total run-rate breaches $80k once F04 is corrected."),
                           (None, "Glacier IR 128 KB minimum and initial CRR PUT costs.")],
}

DECISION_RE = re.compile(r"^D(EC)?-\d+$")
ID_RE = re.compile(r"\b[A-Z]{1,4}(?:-[A-Z]+)*-\d+\b")


def sha256_file(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def split_ids(ids: list[str]) -> tuple[list[str], list[str]]:
    return [i for i in ids if not DECISION_RE.match(i)], [i for i in ids if DECISION_RE.match(i)]


def role_of(item: str, idx: int, text: str) -> str:
    if text.lstrip().lower().startswith("(supporting"):
        return "supporting"
    if item == "research_lakehouse" and idx >= 2:  # legacy "first two must_mention items" rule (README §2.6)
        return "supporting"
    return "required"


def readme_section(text: str | None, heading: str) -> str | None:
    if not text:
        return None
    m = re.search(rf"^##+ {re.escape(heading)}\s*\n(.*?)(?=^##+ |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else None


def convert(tier: str, item: str, fmt: str) -> tuple[dict, dict]:
    base = os.path.join(ROOT, "eval", tier, item)
    src_path = os.path.join(base, "answer_key.json")
    with open(src_path, encoding="utf-8") as fh:
        k = json.load(fh)
    report = {"unmapped": [], "notes": [], "pending": set()}
    synthetic = tier == "synthetic"
    pending = report["pending"]
    consumed_top = {"item_id", "domain"}

    # ---------------- item metadata
    if synthetic:
        docs = {"v1": {"path": "design_v1.md", "sha256": sha256_file(os.path.join(base, "design_v1.md"))},
                "v2": {"path": "design_v2.md", "sha256": sha256_file(os.path.join(base, "design_v2.md"))}}
    else:
        docs = {"v1": {"path": k["document"], "sha256": sha256_file(os.path.join(base, k["document"]))}, "v2": None}
        consumed_top.add("document")
    notes = k.get("version_notes") if synthetic else k.get("readme_notes_moved_at_sealing")
    consumed_top |= {"version_notes", "readme_notes_moved_at_sealing", "document_id"}
    pending |= {"canary_guid", "author_type", "author_model", "generation_date"}
    meta = {
        "item_id": k["item_id"], "split": "S-dev" if synthetic else "S-heldout", "domain": k["domain"], "documents": docs,
        "document_id": k.get("document_id"), "canary_guid": None, "author_type": "unknown", "author_model": None,
        "generation_date": None, "generator_session_ref": None, "brief_sha256": None, "key_reviewed_by": [], "notes": notes,
        "source_key": {"path": os.path.relpath(src_path, ROOT), "format": fmt, "sha256": sha256_file(src_path)},
    }

    # ---------------- scoring
    if item == "item_a":
        legacy_rule = readme_section(k.get("readme_notes_moved_at_sealing"), "Scoring guidance")
    elif item == "item_b" or item == "clinical_rpm":
        legacy_rule = k.get("scoring_guidance")
    elif item == "payments_orchestration":
        legacy_rule = "README: grade findings by substance, using what_a_correct_finding_must_mention, not exact wording."
    else:
        legacy_rule = "version_notes: a finding matches if it names the cited sections/requirements and at least the first two must-mention items."
    consumed_top |= {"scoring_guidance"}
    if legacy_rule is None:
        report["unmapped"].append("scoring rule text (not found)")
    mode = "all_of" if item in ("research_lakehouse", "item_a", "item_b") else "substance"
    scale = {"item_a": "blind4_capitalised", "item_b": "blind4"}.get(item, "synthetic3")
    scoring = {"matching_rule": "core_insight_plus_location_v1", "default_credit_mode": mode,
               "severity_mapping": {"source_scale": scale, "variant": "primary"},
               "severity_tolerance": 1 if item == "item_b" else None,
               "notes": None if legacy_rule is None else
               "Superseded by matching_rule core_insight_plus_location_v1 (audit C5); credit.mode operationalises it. Legacy rule: " + legacy_rule}

    # ---------------- flaws
    raw = k["flaws"] if synthetic else k["defects"]
    consumed_top |= {"flaws", "defects", "v2_new_flaws"}
    if "v2_new_flaws" in k:
        raw = raw + k["v2_new_flaws"]
    changes = {c["flaw_id"]: c for c in k.get("v2_changes", [])}
    consumed_top |= {"v2_changes"}
    cat_map = LM["synthetic_categories"] if synthetic else LM["blind_a_categories"] if item == "item_a" else LM["blind_b_categories"]
    overrides = LM["blind_a_flaw_overrides"] if item == "item_a" else {}
    sev_map = LM["severity"][scale]["primary"]
    consumed_flaw = {"id", "title", "category", "severity", "introduced_in", "introduced_by_fix_of", "section_refs", "requirement_ids",
                     "location", "description", "why_it_is_a_flaw", "why_it_matters", "what_a_correct_finding_must_mention",
                     "credit_requires", "requires_external_fact", "external_fact", "acceptable_recommendation", "acceptable_fix",
                     "distractor_notes", "disambiguation"}
    flaws, ext_fallbacks = [], []
    for f in raw:
        report["unmapped"] += [f"flaw {f['id']}.{x}" for x in f if x not in consumed_flaw]
        tgt = overrides.get(f["id"]) or cat_map[f["category"]]
        loc_src = f["location"] if "location" in f else {"sections": f["section_refs"], "requirement_ids": f["requirement_ids"]}
        req_ids, dec_ids = split_ids(loc_src["requirement_ids"])
        intro = f.get("introduced_in") or "v1"
        if synthetic:
            ch = changes.get(f["id"])
            if intro == "v2":
                v2_status, caused, v2_note = "introduced", None, None
            elif ch is None:
                v2_status, caused, v2_note = "unchanged", None, None
                report["notes"].append(f"{f['id']}: no v2_changes entry; assumed unchanged")
            else:
                status = ch["status"]
                caused = ch.get("introduced_new_flaw_id") or ch.get("new_flaw_id")
                v2_status = "fixed" if status == "regressed" else status
                v2_note = ch.get("note") or None
                extra = set(ch) - {"flaw_id", "status", "introduced_new_flaw_id", "new_flaw_id", "note"}
                report["unmapped"] += [f"v2_changes[{f['id']}].{x}" for x in sorted(extra)]
        else:
            v2_status, caused, v2_note = "not_applicable", None, None
        # credit
        if synthetic:
            texts = f["what_a_correct_finding_must_mention"]
        elif isinstance(f["credit_requires"], str):
            texts = [f["credit_requires"]]
        else:
            texts = f["credit_requires"]
        items = [{"id": f"c{i + 1}", "text": t, "role": role_of(item, i, t)} for i, t in enumerate(texts)]
        # external fact
        if synthetic:
            needs_ext = f["id"] in NEEDS_EXTERNAL[item]
        elif item == "item_a":
            needs_ext = bool(f.get("requires_external_fact"))
        else:
            needs_ext = f.get("external_fact") not in (None, "", "None")
        ext = None
        if needs_ext:
            pending.add("external_fact_verification")
            if synthetic:
                urls = re.findall(r"https?://\S+", f.get("distractor_notes") or "")
                ext = {"claim": f["why_it_is_a_flaw"], "source": " ".join(u.rstrip(".,;)") for u in urls) or "unspecified in legacy key"}
            else:
                s = f["external_fact"]
                head, sep, tail = s.partition(": ")
                if sep and len(head) <= 150:
                    ext = {"source": head, "claim": tail}
                else:
                    ext = {"source": "unspecified in legacy key (citation embedded in claim)", "claim": s}
                    ext_fallbacks.append(f["id"])
            note = "Not independently verified in this key; see research/audit/eval_data_audit.md Task 1."
            if synthetic:
                note += " claim is a placeholder copied from why_it_is_a_flaw (spec/README.md §2.2); restate it as the external fact when verifying."
            ext.update({"verified": False, "verified_source_url": None, "verified_at": None, "verification_note": note})
        pending |= {"core_insight", "anchor_quote", "expected_disposition"}
        flaws.append({
            "id": f["id"], "title": f.get("title"), "kind": tgt["kind"], "acceptable_kinds": CAT_KINDS[tgt["category"]],
            "category": tgt["category"], "tags": [] if synthetic else [f["category"]],
            "severity": sev_map[f["severity"]], "severity_source": {"scale": scale, "label": f["severity"]},
            "planted": True, "introduced_in": intro, "introduced_by_fix_of": f.get("introduced_by_fix_of"),
            "v2_status": v2_status, "caused_regression_flaw_id": caused, "v2_note": v2_note,
            "location": {"sections": loc_src["sections"], "requirement_ids": req_ids, "decision_ids": dec_ids, "anchor_quote": None, "page": None},
            "description": f["description"], "rationale": f.get("why_it_is_a_flaw") or f.get("why_it_matters"),
            "core_insight": None, "credit": {"mode": mode, "items": items, "min_required": None},
            "needs_external_research": needs_ext, "external_fact": ext,
            "expected_disposition": None, "acceptable_dispositions": [], "affected_decisions": [],
            "acceptable_fix": f.get("acceptable_recommendation") or f.get("acceptable_fix"),
            "distractor_notes": f.get("distractor_notes"), "overlapping_sound_section_ids": [],
            "disambiguation": f.get("disambiguation"),
        })
    if ext_fallbacks:
        report["notes"].append(f"external_fact not split into source/claim (no short 'source: claim' prefix): {', '.join(ext_fallbacks)}")
    by_id = {f["id"]: f for f in flaws}

    # ---------------- sound sections
    raw_s = k["sound_sections"] if synthetic else k["deliberately_sound_sections"]
    consumed_top |= {"sound_sections", "deliberately_sound_sections"}
    obs_n = 0
    sounds = []
    for i, s in enumerate(raw_s):
        where = s.get("section_ref") or s.get("location") or s.get("section")
        trap = s.get("trap") or s.get("careless_flag") or s.get("likely_false_positive")
        report["unmapped"] += [f"sound[{i}].{x}" for x in s if x not in
                               {"section_ref", "location", "section", "why_sound", "trap", "careless_flag", "likely_false_positive",
                                "disambiguation", "still_valid_observations"}]
        ids = [m.group(0) for m in ID_RE.finditer(where)]
        req_ids, dec_ids = split_ids(ids)
        obs = []
        for t in s.get("still_valid_observations", []):
            obs_n += 1
            obs.append({"id": f"O{obs_n:02d}", "text": t, "origin": "eval_audit", "related_flaw_ids": []})
        for prefix, t in AUDIT_OBSERVATIONS.get(item, []):
            if prefix and where.startswith(prefix):
                obs_n += 1
                obs.append({"id": f"O{obs_n:02d}", "text": t, "origin": "eval_audit", "related_flaw_ids": []})
        v1_only = any(where.startswith(p) for p in V1_ONLY_SOUND.get(item, []))
        sounds.append({
            "id": f"S{i + 1:02d}",
            "location": {"sections": [where], "requirement_ids": req_ids, "decision_ids": dec_ids, "anchor_quote": None, "page": None},
            "why_sound": s["why_sound"], "trap": trap, "still_valid_observations": obs, "overlapping_flaw_ids": [],
            "applies_to_versions": ["v1"] if (not synthetic or v1_only) else ["v1", "v2"], "bait": False,
            "disambiguation": s.get("disambiguation"),
        })
    pending.add("sound_overlap_annotations")
    for prefix, fids in OVERLAPS.get(item, []):
        hits = [s for s in sounds if s["location"]["sections"][0].startswith(prefix)]
        if len(hits) != 1:
            report["unmapped"].append(f"overlap row '{prefix}' matched {len(hits)} sound sections")
            continue
        for fid in fids:
            hits[0]["overlapping_flaw_ids"].append(fid)
            by_id[fid]["overlapping_sound_section_ids"].append(hits[0]["id"])
    # cross-check against the free-text disambiguation fields added by the eval fixes
    for f in flaws:
        if f["disambiguation"] and not f["overlapping_sound_section_ids"]:
            report["notes"].append(f"{f['id']} has a disambiguation note but no overlap row in README §2.7")
    for s in sounds:
        if s["disambiguation"] and not s["overlapping_flaw_ids"]:
            report["notes"].append(f"{s['id']} has a disambiguation note but no overlap row in README §2.7")

    # ---------------- item-level observations
    item_obs = []
    for t in k.get("non_keyed_observations_acceptable_but_not_required", []):
        obs_n += 1
        item_obs.append({"id": f"O{obs_n:02d}", "text": t, "origin": "key_author", "related_flaw_ids": []})
    consumed_top.add("non_keyed_observations_acceptable_but_not_required")
    for prefix, t in AUDIT_OBSERVATIONS.get(item, []):
        if prefix is None:
            obs_n += 1
            item_obs.append({"id": f"O{obs_n:02d}", "text": t, "origin": "eval_audit", "related_flaw_ids": []})
    for o in item_obs + [o for s in sounds for o in s["still_valid_observations"]]:
        o["related_flaw_ids"] = sorted({m for m in re.findall(r"\b(?:F|D|DEF-)\d{2}\b", o["text"]) if m in by_id})

    # ---------------- v2 block
    v2 = None
    if synthetic:
        open_ids = sorted(f["id"] for f in flaws if f["v2_status"] in {"unchanged", "partially_fixed", "introduced"})
        if "expected_v2_open_flaws" in k and sorted(k["expected_v2_open_flaws"]) != open_ids:
            report["notes"].append(f"expected_v2_open_flaws {k['expected_v2_open_flaws']} != derived {open_ids}")
        consumed_top.add("expected_v2_open_flaws")
        rev = None
        with open(os.path.join(base, "design_v2.md"), encoding="utf-8") as fh:
            d2 = fh.read()
        m = re.search(r"^\|\s*(?:1\.1|2\.0)\s*\|[^|]*\|\s*(.*?)\s*\|\s*$", d2, re.M) or \
            re.search(r"^#+ Changes since version 1\.0\s*\n(.*?)(?=^#)", d2, re.S | re.M)
        if m:
            rev = "v2 revision history (verbatim): " + m.group(1).strip()
        else:
            report["unmapped"].append("v2 revision-history text (not found in design_v2.md)")
        v2 = {"changed_sections": [], "expected_open_flaw_ids": open_ids, "notes": rev}
        pending.add("v2_changed_sections")

    # ---------------- dropped legacy counts: assert they equal the recomputed values
    v1 = [f for f in raw if (f.get("introduced_in") or "v1") == "v1"]
    if "flaw_counts" in k:
        fc = k["flaw_counts"]
        ok = fc["total_v1"] == len(v1) and fc["by_severity"] == _count(v1, "severity") and fc["by_category"] == _count(v1, "category")
        report["notes"].append(f"flaw_counts {'equal to' if ok else 'DIFFER FROM'} recomputed v1 counts")
    if "category_counts_v1" in k:
        ok = k["category_counts_v1"] == _count(v1, "category")
        report["notes"].append(f"category_counts_v1 {'equal to' if ok else 'DIFFER FROM'} recomputed")
    if "defect_count" in k:
        report["notes"].append(f"defect_count {'equal to' if k['defect_count'] == len(raw) else 'DIFFERS FROM'} len(defects)")
    if "category_taxonomy" in k:
        missing = sorted({f["category"] for f in raw} - set(k["category_taxonomy"]))
        report["notes"].append("category_taxonomy covers every defect label" if not missing else f"labels outside category_taxonomy: {missing}")
    if "severity_scale" in k:
        report["notes"].append(f"severity_scale labels {sorted(k['severity_scale'])} == scale {scale}: {sorted(k['severity_scale']) == sorted(sev_map)}")
    consumed_top |= {"flaw_counts", "category_counts_v1", "defect_count", "category_taxonomy", "severity_scale",
                     "authoring_drafts"}
    report["unmapped"] += [f"top-level {x}" for x in k if x not in consumed_top]

    pending |= {"approved_decisions", "key_second_review"}
    key = {
        "schema_version": "1.0", "item": meta, "scoring": scoring, "approved_decisions": [], "flaws": flaws,
        "sound_sections": sounds, "still_valid_observations": item_obs, "v2": v2,
        "authoring_status": {"pending": [], "scored_run_ready": False},
    }
    drafts = apply_drafts(k.get("authoring_drafts"), key, report, pending)
    status = key["authoring_status"]
    status["pending"] = [p for p in KEY_PENDING_ORDER if p in pending]
    status["scored_run_ready"] = not pending
    if drafts is not None:
        status["drafts"] = drafts
    return key, report


# ---------------------------------------------------------------- agent drafts and owner sign-off (README §2.9)
PROVENANCE_FIELDS = ("author_type", "author_model", "generation_date", "generator_session_ref", "brief_sha256",
                     "canary_guid")


def apply_drafts(d: dict | None, key: dict, report: dict, pending: set[str]) -> dict | None:
    """Copy an `authoring_drafts` block into `key`; return the authoring_status.drafts record (or None).

    Provenance facts taken from the record (author_type / author_model / generation_date) leave `pending` when set.
    Every judgement field drafted here stays in `pending` and is listed in the drafts record until `signoff`
    accepts it. Nothing here sets scored_run_ready; the caller derives it from `pending`."""
    if not d:
        return None
    drafted: set[str] = set()
    meta = key["item"]
    it = d.get("item") or {}
    for f in PROVENANCE_FIELDS:
        if it.get(f) is not None:
            meta[f] = it[f]
    if meta["author_type"] != "unknown":
        pending.discard("author_type")
    for f in ("author_model", "generation_date"):
        if meta[f] is not None:
            pending.discard(f)
    if meta["canary_guid"] is not None and it.get("canary_embedded_in_documents"):
        pending.discard("canary_guid")

    by_id = {f["id"]: f for f in key["flaws"]}
    for fid, fd in (d.get("flaws") or {}).items():
        f = by_id.get(fid)
        if f is None:
            report["unmapped"].append(f"authoring_drafts.flaws.{fid} (no such flaw)")
            continue
        if fd.get("core_insight"):
            f["core_insight"] = fd["core_insight"]
            drafted.add("core_insight")
        if fd.get("anchor_quote"):
            f["location"]["anchor_quote"] = fd["anchor_quote"]
            f["location"]["page"] = fd.get("anchor_page")
            drafted.add("anchor_quote")
            if len(fd["anchor_quote"].split()) < 8:
                report["notes"].append(f"{fid}: anchor quote under 8 tokens")
        if fd.get("expected_disposition"):
            f["expected_disposition"] = fd["expected_disposition"]
            f["acceptable_dispositions"] = fd.get("acceptable_dispositions") or [fd["expected_disposition"]]
            drafted.add("expected_disposition")
        ext = fd.get("external_fact")
        if ext and f["external_fact"] is not None:
            for x in ("claim", "source", "verification_note", "verified", "verified_source_url", "verified_at"):
                if x in ext and ext[x] is not None:
                    f["external_fact"][x] = ext[x]
            drafted.add("external_fact_verification")
        elif ext:
            report["unmapped"].append(f"authoring_drafts.flaws.{fid}.external_fact (flaw needs no external fact)")
    missing = sorted(set(by_id) - set(d.get("flaws") or {}))
    if d.get("flaws") and missing:
        report["notes"].append(f"no draft for flaws {', '.join(missing)}")

    if d.get("approved_decisions"):
        key["approved_decisions"] = d["approved_decisions"]
        for a in key["approved_decisions"]:
            for fid in a["flaw_ids"]:
                if fid in by_id and a["id"] not in by_id[fid]["affected_decisions"]:
                    by_id[fid]["affected_decisions"].append(a["id"])
        drafted.add("approved_decisions")

    split = d.get("sound_sections") or {}
    legacy_refs = {s["location"]["sections"][0] for s in key["sound_sections"]}
    for s in key["sound_sections"]:
        sd = split.get(s["location"]["sections"][0])
        if sd and sd.get("sections"):
            s["location"]["sections"] = sd["sections"]
    if "sound_sections" in d:
        report["unmapped"] += [f"authoring_drafts.sound_sections[{u!r}] (no such sound section)"
                               for u in sorted(set(split) - legacy_refs)]
        drafted.add("sound_overlap_annotations")

    if d.get("v2_changed_sections") is not None and key["v2"] is not None:
        key["v2"]["changed_sections"] = d["v2_changed_sections"]
        if d.get("v2_changed_sections_note"):
            prior = (key["v2"]["notes"] or "").rstrip("-\n ")
            key["v2"]["notes"] = (prior + "\n\n" + d["v2_changed_sections_note"]).strip()
        drafted.add("v2_changed_sections")

    so = d.get("signoff") or {}
    if so.get("signed_by") and so.get("signed_on"):
        accepted = set(so.get("accepted") or [])
        bad = accepted - set(KEY_PENDING_ORDER)
        if bad:
            report["unmapped"].append(f"signoff.accepted has unknown fields {sorted(bad)}")
        pending -= accepted
        drafted -= accepted
        signer = f"{so['signed_by']} (signed {so['signed_on']})"
        meta["key_reviewed_by"] = sorted(set(meta["key_reviewed_by"]) | {signer})
        if "external_fact_verification" in accepted and any(
                f["external_fact"] and not f["external_fact"]["verified"] for f in key["flaws"]):
            report["notes"].append("signoff accepts external_fact_verification while some external_fact.verified "
                                   "is false (owner accepted the eval-audit verification notes)")
    elif so.get("accepted"):
        report["notes"].append("signoff.accepted ignored: signed_by and signed_on are both required")
    note = d.get("note")
    if so.get("signed_by") and so.get("signed_on"):
        acc = ", ".join(p for p in KEY_PENDING_ORDER if p in set(so.get("accepted") or [])) or "nothing"
        note = ((note or "") + f" Owner sign-off by {so['signed_by']} on {so['signed_on']} accepted: {acc}.").strip()
    return {"drafted_by": d["drafted_by"], "drafted_on": d["drafted_on"],
            "fields": [p for p in KEY_PENDING_ORDER if p in drafted and p in pending], "note": note}


def verify_anchors(tier: str, item: str, key: dict) -> list[str]:
    """Exact-match every flaw and approved-decision anchor quote against the agent-ingested PDF text."""
    try:
        from sit_review_agent.ingest.pdf import ingest
        from sit_review_agent.ingest.text import flatten_for_match, normalise_quote
    except ImportError:
        return ["--verify-anchors skipped: sit_review_agent is not importable (activate the venv)"]
    base = os.path.join(ROOT, "eval", tier, item)
    docs: dict[str, object] = {}
    out = []
    rows = [(f["id"], "v2" if f["introduced_in"] == "v2" else "v1", f["location"]) for f in key["flaws"]]
    rows += [(a["id"], "v1", a["location"]) for a in key["approved_decisions"]]
    for rid, ver, loc in rows:
        q = loc.get("anchor_quote")
        if not q:
            continue
        pdf = os.path.join(base, f"design_{ver}.pdf")
        if not os.path.exists(pdf):
            out.append(f"{rid}: {os.path.basename(pdf)} not found")
            continue
        if ver not in docs:
            docs[ver] = ingest(pdf)
        doc = docs[ver]
        hay = flatten_for_match(doc.text)
        nq = normalise_quote(q)
        i = hay.find(nq)
        if i < 0:
            out.append(f"{rid}: anchor quote not found verbatim in {os.path.basename(pdf)}")
        elif hay.count(nq) > 1:
            out.append(f"{rid}: anchor quote occurs {hay.count(nq)} times in {os.path.basename(pdf)}")
        elif doc.page_at(i) != loc.get("page"):
            out.append(f"{rid}: anchor quote is on page {doc.page_at(i)}, key says {loc.get('page')}")
    return out


def _count(flaws: list[dict], field: str) -> dict:
    out: dict[str, int] = {}
    for f in flaws:
        out[f[field]] = out.get(f[field], 0) + 1
    return out


KEY_PENDING_ORDER = V["KD"]["PendingField"]["enum"]


def main() -> int:
    write = "--check" not in sys.argv
    check_anchors = "--verify-anchors" in sys.argv
    failures = 0
    total = 0
    items = [x for x in ITEMS if x[0] in TIERS]
    for tier, item, fmt in items:
        key, rep = convert(tier, item, fmt)
        errs = errors(V_KEY, key) + key_semantics(key)
        st = key["authoring_status"]
        if st.get("drafts") and not set(st["drafts"]["fields"]) <= set(st["pending"]):
            errs.append("authoring_status.drafts.fields must be a subset of pending")
        if check_anchors:
            errs += [f"anchor: {e}" for e in verify_anchors(tier, item, key)]
        out = os.path.join(ROOT, "eval", tier, item, "answer_key.canonical.json")
        if write and not errs:
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(key, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
        fl = key["flaws"]
        total += len(fl)
        n_req = sum(1 for f in fl for c in f["credit"]["items"] if c["role"] == "required")
        n_sup = sum(1 for f in fl for c in f["credit"]["items"] if c["role"] == "supporting")
        n_obs = len(key["still_valid_observations"]) + sum(len(s["still_valid_observations"]) for s in key["sound_sections"])
        cats = _count(fl, "category")
        print(f"== {tier}/{item} -> {os.path.relpath(out, ROOT)} {'(written)' if write and not errs else '(not written)'}")
        print(f"   flaws {len(fl)} (v1 {sum(f['introduced_in'] == 'v1' for f in fl)}, v2 {sum(f['introduced_in'] == 'v2' for f in fl)}); "
              f"severity {_count(fl, 'severity')}; kinds {_count(fl, 'kind')}")
        print(f"   categories {cats}")
        print(f"   v2_status {_count(fl, 'v2_status')}; credit mode {key['scoring']['default_credit_mode']}: {n_req} required / {n_sup} supporting items")
        print(f"   needs_external_research {sum(f['needs_external_research'] for f in fl)}; sound sections {len(key['sound_sections'])}; "
              f"overlap links {sum(len(f['overlapping_sound_section_ids']) for f in fl)}; still-valid observations {n_obs}")
        print(f"   pending: {', '.join(key['authoring_status']['pending'])}; scored_run_ready "
              f"{key['authoring_status']['scored_run_ready']}")
        if key["authoring_status"].get("drafts"):
            drafted = ", ".join(key["authoring_status"]["drafts"]["fields"]) or "none"
            print(f"   drafted (awaiting sign-off): {drafted}; "
                  f"approved decisions {len(key['approved_decisions'])}")
        for n in rep["notes"]:
            print(f"   note: {n}")
        print(f"   could not map: {', '.join(rep['unmapped']) if rep['unmapped'] else 'none'}")
        for e in errs:
            print(f"   INVALID: {e}")
        failures += bool(errs)
    print(f"\n{total} flaws converted across {len(items)} keys; {failures} key(s) failed validation")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
