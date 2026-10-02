"""Deterministic offline judge answers for plumbing tests and ``--judge fake``.

PLUMBING ONLY: every answer is a hash of the call's purpose and sample index, not a judgement.
Scores produced with it say nothing about the review's quality.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from sit_eval.judge import JudgeRequest

_FID = re.compile(r'"finding_id": "([^"]+)"')
_EID = re.compile(r'"evidence_id": "([^"]+)"')
CLASSES = ["VALID_UNPLANTED", "NON_SPECIFIC", "INVALID_OPINION", "HALLUCINATED", "OUT_OF_SCOPE", "VALID_UNPLANTED"]


def _h(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _score_entry(seed: int) -> dict[str, Any]:
    s = seed % 4
    return {"score": s, "core_insight_present": ["no", "no", "partly", "yes"][s], "location_ok": True,
            "credit_items_stated": ["c1"] if s >= 2 else [], "rationale": "plumbing-only fake answer"}


def plumbing_responder(req: JudgeRequest) -> dict[str, Any]:
    kind, _, rest = req.purpose.partition(":")
    if kind == "match.shortlist":
        ids = list(dict.fromkeys(_FID.findall(req.user)))
        picks = [i for i in ids if _h(rest, i) % 5 == 0][:3]
        return {"candidate_ids": picks, "rationale": "plumbing-only fake answer"}
    if kind == "match.pair":
        return _score_entry(_h(rest, req.sample_index))
    if kind == "match.batch":
        ids = list(dict.fromkeys(_FID.findall(req.user)))
        return {"scores": [{"finding_id": i, **_score_entry(_h(rest, i, req.sample_index))} for i in ids]}
    if kind == "adjudicate":
        return {"class": CLASSES[_h(rest) % len(CLASSES)], "duplicate_of": None, "matches_observation_id": None,
                "rationale": "plumbing-only fake answer"}
    if kind == "ground.premise":
        return {"is_absence_claim": _h(rest) % 4 == 0, "premise": "plumbing-only fake answer",
                "label": "SUPPORTED", "doc_passage": None, "rationale": "plumbing-only fake answer"}
    if kind == "ground.cite":
        ids = list(dict.fromkeys(_EID.findall(req.user)))
        return {"items": [{"evidence_id": i, "support": ["FULL", "PARTIAL", "FULL"][_h(rest, i) % 3],
                           "rationale": "plumbing-only fake answer"} for i in ids]}
    if kind == "rec":
        return {"benefit_follows": True, "rationale_explains": _h(rest) % 3 != 0,
                "rationale": "plumbing-only fake answer"}
    raise ValueError(f"plumbing responder: unknown purpose {req.purpose!r}")
