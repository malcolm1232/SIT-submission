#!/usr/bin/env python3
"""Convert the five legacy answer keys to the canonical schema (spec/answer_key.schema.json).

Reads   eval/<tier>/<item>/answer_key.json          (never modified)
Writes  eval/<tier>/<item>/answer_key.canonical.json
Checks  each output against answer_key.schema.json and the cross-field rules in validate_examples.key_semantics,
        asserts the dropped legacy count fields equal the recomputed values, and prints per-key counts plus every
        legacy field it could not map.

Mapping follows spec/README.md §2 and taxonomy.yaml legacy_mappings. Fields that need a human (core_insight,
anchor quotes, expected dispositions, approved decisions, provenance, canary, external-fact verification, v2
changed sections) are written as null / [] and listed in authoring_status.pending. Nothing is invented.

Usage: python3 spec/convert_answer_keys.py [--check]   (--check: validate only, do not write)
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Reuse the validators and the taxonomy loaded by validate_examples.py (it also self-tests the spec).
_buf = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf):
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
    consumed_top |= {"flaw_counts", "category_counts_v1", "defect_count", "category_taxonomy", "severity_scale"}
    report["unmapped"] += [f"top-level {x}" for x in k if x not in consumed_top]

    pending |= {"approved_decisions", "key_second_review"}
    order = KEY_PENDING_ORDER
    key = {
        "schema_version": "1.0", "item": meta, "scoring": scoring, "approved_decisions": [], "flaws": flaws,
        "sound_sections": sounds, "still_valid_observations": item_obs, "v2": v2,
        "authoring_status": {"pending": [p for p in order if p in pending], "scored_run_ready": False},
    }
    return key, report


def _count(flaws: list[dict], field: str) -> dict:
    out: dict[str, int] = {}
    for f in flaws:
        out[f[field]] = out.get(f[field], 0) + 1
    return out


KEY_PENDING_ORDER = V["KD"]["PendingField"]["enum"]


def main() -> int:
    write = "--check" not in sys.argv
    failures = 0
    total = 0
    for tier, item, fmt in ITEMS:
        key, rep = convert(tier, item, fmt)
        errs = errors(V_KEY, key) + key_semantics(key)
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
        print(f"   pending: {', '.join(key['authoring_status']['pending'])}")
        for n in rep["notes"]:
            print(f"   note: {n}")
        print(f"   could not map: {', '.join(rep['unmapped']) if rep['unmapped'] else 'none'}")
        for e in errs:
            print(f"   INVALID: {e}")
        failures += bool(errs)
    print(f"\n{total} flaws converted across {len(ITEMS)} keys; {failures} key(s) failed validation")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
