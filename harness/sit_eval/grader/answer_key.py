"""Key-aware **diagnostic** mode (grader_prompt.md §6; GR §5 and its reconciliation note).

Key-aware Pass B runs in fresh contexts after the key-blind score is final and never changes it.
Its output is reduced to counts of key-item alignment, trap hits, affirmed no-change areas and
valid extra findings. No ratio is emitted: recall, precision and SWR come only from the matcher
in ``research/methodology/metrics.md`` §2 (``spec/README.md`` §3 C4).

Two key formats are accepted:

* the canonical key (``spec/answer_key.schema.json``), projected to the legacy YAML the prompt
  expects as ``spec/README.md`` §1 "Grader-facing projection" specifies;
* the legacy YAML of grader_prompt.md §6 (as in worked_examples.md §6), used as is, except that
  key-item IDs are zero-padded to two digits (``K1`` -> ``K01``) because the PassBOutput schema
  requires ``key_id`` to match ``^[A-Z]{1,4}-?[0-9]{2,3}$``.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Any

import yaml

DIAGNOSTIC_LABEL = ("DIAGNOSTIC ONLY - key-aware alignment counts. Not recall: recall comes only from the "
                    "matcher (metrics.md §2; spec C4). Never averaged with the key-blind score.")
#: legacy_mappings.severity.grading_materiality (primary variant)
MATERIALITY = {"critical": "high", "high": "high", "medium": "medium", "low": "low"}
_SHORT_ID = re.compile(r"^([A-Z]{1,4}-?)([0-9])$")


def _pad(key_id: str) -> str:
    m = _SHORT_ID.match(key_id)
    return f"{m.group(1)}0{m.group(2)}" if m else key_id


def load_answer_key(path: str | Path) -> dict[str, Any]:
    """``{"format": "canonical" | "legacy", "key": <legacy-shaped dict>, "id_map": {...}, "source": ...}``."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    data = json.loads(text) if p.suffix == ".json" else yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{p.name}: not an answer key")
    if "flaws" in data and "sound_sections" in data:
        return {"format": "canonical", "canonical": data, "source": p.name}
    if "key_items" in data:
        return {"format": "legacy", "legacy": data, "source": p.name}
    raise ValueError(f"{p.name}: neither a canonical key (flaws, sound_sections) nor a legacy key (key_items)")


def _locations(loc: dict[str, Any]) -> list[str]:
    out = [str(s) for s in loc.get("sections") or []]
    if loc.get("page"):
        out.append(f"p.{loc['page']}")
    return out


def project_key(loaded: dict[str, Any], *, review_mode: str = "full") -> tuple[dict[str, Any], dict[str, str]]:
    """``(legacy-shaped key, id_map)`` for ``{{ANSWER_KEY}}``. ``id_map`` maps shown IDs to source IDs.

    For a full review the v1 flaws are shown; for a delta review the flaws open in v2
    (introduced in v2, unchanged or partially fixed).
    """
    if loaded["format"] == "legacy":
        src = loaded["legacy"]
        items, id_map = [], {}
        for it in src.get("key_items") or []:
            new = _pad(str(it.get("id")))
            id_map[new] = str(it.get("id"))
            items.append({**it, "id": new})
        return {**src, "key_items": items}, id_map

    key = loaded["canonical"]
    version = "v2" if review_mode == "delta" else "v1"
    flaws = [f for f in key.get("flaws") or []
             if (version == "v1" and f.get("introduced_in") == "v1")
             or (version == "v2" and (f.get("introduced_in") == "v2"
                                      or f.get("v2_status") in ("unchanged", "partially_fixed")))]
    key_items = [{
        "id": f["id"],
        "title": f.get("title") or f.get("description"),
        "locations": _locations(f.get("location") or {}),
        "category": f.get("kind"),
        "materiality": MATERIALITY.get(str(f.get("severity")), "medium"),
        "expected_triage": f.get("expected_disposition"),
    } for f in flaws]
    sounds = [s for s in key.get("sound_sections") or [] if version in (s.get("applies_to_versions") or ["v1"])]
    traps = [{"id": s["id"], "description": s.get("trap"), "truth": s.get("why_sound")} for s in sounds]
    no_change = [{"id": s["id"], "area": s.get("why_sound"), "locations": _locations(s.get("location") or {})}
                 for s in sounds]
    item = key.get("item") or {}
    legacy = {"artefact": item.get("document_id") or "design under review", "key_items": key_items,
              "traps": traps, "no_change_areas": no_change}
    return legacy, {i["id"]: i["id"] for i in key_items}


def render_key(legacy: dict[str, Any]) -> str:
    return yaml.safe_dump(legacy, sort_keys=False, allow_unicode=True, width=120).rstrip("\n")


def alignment_counts(alignment: dict[str, Any] | None, legacy: dict[str, Any]) -> dict[str, int]:
    """Counts from one PassBOutput ``answer_key_alignment`` (no shares, no recall)."""
    items = {str(i.get("id")): i for i in legacy.get("key_items") or []}
    high = {k for k, v in items.items() if v.get("materiality") == "high"}
    a = alignment or {}
    full = {m.get("key_id") for m in a.get("matched") or [] if m.get("match") == "full"} & items.keys()
    partial = ({m.get("key_id") for m in a.get("matched") or [] if m.get("match") == "partial"} & items.keys()) - full
    return {
        "key_items": len(items), "key_items_high": len(high),
        "aligned_full": len(full), "aligned_partial": len(partial),
        "aligned_full_high": len(full & high), "aligned_partial_high": len(partial & high),
        "not_aligned": len(items) - len(full) - len(partial),
        "trap_hits": len(a.get("trap_hits") or []),
        "no_change_areas_affirmed": len(a.get("no_change_areas_affirmed") or []),
        "valid_extras": len(a.get("valid_extra_findings") or []),
    }


def aggregate_counts(per_sample: list[dict[str, int]]) -> dict[str, float]:
    """Median per count over the key-aware samples."""
    if not per_sample:
        return {}
    return {k: float(statistics.median(s[k] for s in per_sample)) for k in per_sample[0]}
