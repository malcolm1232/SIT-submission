"""Pre-registration freeze check (eval/prereg.yaml ``freeze.procedure``, leakage control LC1).

If ``frozen: true``, a scored run is refused unless ``sha256(eval/prereg.yaml)`` equals the hash in
``eval/prereg.lock`` (one line: hash plus commit id). While ``frozen: false`` every score is a
pilot/unfrozen score and says so.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from sit_eval.paths import prereg_lock_path, prereg_path

_HEX64 = re.compile(r"\b[0-9a-f]{64}\b")
UNFROZEN_WARNING = ("eval/prereg.yaml is not frozen (frozen: false): these scores are UNFROZEN PILOT scores, "
                    "exploratory only, and carry no confirmatory claim")


class PreregRefusal(RuntimeError):
    """A scored run must not start (frozen prereg whose hash does not match the lock)."""


def prereg_status(prereg: Path | None = None, lock: Path | None = None) -> dict[str, Any]:
    p = prereg or prereg_path()
    lk = lock or prereg_lock_path()
    if not p.exists():
        return {"path": str(p), "exists": False, "frozen": False, "sha256": None, "lock_sha256": None,
                "ok_to_score": True, "label": "pilot_unfrozen", "message": f"{p} not found; scores are unfrozen"}
    raw = p.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    data = yaml.safe_load(raw) or {}
    frozen = data.get("frozen") is True
    lock_sha = None
    if lk.exists():
        m = _HEX64.search(lk.read_text(encoding="utf-8"))
        lock_sha = m.group(0) if m else None
    matcher_sha = (data.get("matcher") or {}).get("prompt_sha256")
    if not frozen:
        return {"path": str(p), "exists": True, "frozen": False, "sha256": sha, "lock_sha256": lock_sha,
                "matcher_prompt_sha256": matcher_sha, "ok_to_score": True, "label": "pilot_unfrozen",
                "message": UNFROZEN_WARNING}
    ok = lock_sha is not None and lock_sha == sha
    msg = ("frozen; hash matches eval/prereg.lock" if ok else
           f"frozen, but sha256 {sha} {'does not match' if lock_sha else 'has no'} eval/prereg.lock entry "
           f"({lock_sha}); refusing a scored run")
    return {"path": str(p), "exists": True, "frozen": True, "sha256": sha, "lock_sha256": lock_sha,
            "matcher_prompt_sha256": matcher_sha, "ok_to_score": ok, "label": "frozen" if ok else "refused",
            "message": msg}


PILOT_COST_FIELD = "costs.per_run_usd.heavy_case_FULL"


def pilot_cost_threshold_usd(prereg: Path | None = None) -> float | None:
    """The pilot checkpoint's FULL-run cost threshold (``stop_rule.pilot_checkpoint`` reads
    ``costs.per_run_usd.heavy_case_FULL``); ``None`` when the prereg or the field is missing."""
    p = prereg or prereg_path()
    if not p.exists():
        return None
    data = yaml.safe_load(p.read_bytes()) or {}
    node: Any = data
    for part in PILOT_COST_FIELD.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return float(node) if isinstance(node, int | float) and not isinstance(node, bool) else None


def enforce(status: dict[str, Any], *, prompt_bundle_sha256: str, prompt_lock_problems: list[str]) -> None:
    """Raise :class:`PreregRefusal` when a frozen prereg forbids this run."""
    if not status["frozen"]:
        return
    if not status["ok_to_score"]:
        raise PreregRefusal(status["message"])
    if prompt_lock_problems:
        raise PreregRefusal("prereg is frozen but the judge prompts differ from prompts/PROMPTS.lock: "
                            + "; ".join(prompt_lock_problems))
    want = status.get("matcher_prompt_sha256")
    if want and want != prompt_bundle_sha256:
        raise PreregRefusal(f"prereg matcher.prompt_sha256 {want} != prompt bundle {prompt_bundle_sha256}")
