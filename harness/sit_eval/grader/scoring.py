"""Weights, caps, gates, grade bands and sample aggregation (GR §4, §6.1 steps 5-6; prereg ``grader``).

Everything here is computed in code; the model only reports dimension scores and evidence
(grader_prompt.md §1). Conventions where the source leaves a choice (recorded in grade.json):

* Caps are applied to each sample's scores first (each sample with its own hallucination list),
  then the final score is the **median per dimension** of the capped samples (prereg ``samples``).
  With two samples the median is their mean, so a final dimension can be x.5.
* The final count of material verified-false hallucinations is the median of the per-sample
  counts; G3 caps the final scores when that median is >= 1 (>= 2: D4 <= 1).
* G3 with two or more hallucinations also keeps the one-hallucination caps (D9 <= 2, grade <= C);
  GR §4.2 states only D4 <= 1 for that row, and a weaker D9 cap for more fabrication would be odd.
* G4 uses the verdict fact computed in code from the structured review; the model's view is kept.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from typing import Any

WEIGHTS: dict[str, float] = {"D1": 10, "D2": 12, "D3": 10, "D4": 16, "D5": 14, "D6": 10, "D7": 8, "D8": 8,
                             "D9": 8, "D10": 4}
DIMS10 = tuple(WEIGHTS)
CRITICAL = ("D4", "D5", "D6")
DELTA_FACTOR = 0.9
D11_WEIGHT = 10.0
#: worked_examples.md §1: finding-level dimensions and their review-level weights (sum 74).
FQS_DIMS = ("D1", "D4", "D5", "D6", "D7", "D8", "D9")
THIRD_SAMPLE_DIM_DELTA = 2
THIRD_SAMPLE_S_DELTA = 8.0
PASS_THRESHOLD = 60.0


def weights(delta: bool = False) -> dict[str, float]:
    if not delta:
        return dict(WEIGHTS)
    w = {k: v * DELTA_FACTOR for k, v in WEIGHTS.items()}
    w["D11"] = D11_WEIGHT
    return w


def dims_for(delta: bool) -> tuple[str, ...]:
    return (*DIMS10, "D11") if delta else DIMS10


def weighted(scores: Mapping[str, float], delta: bool = False) -> float:
    """GR §4.1 ``S = sum(w_i * s_i / 4)``, rounded to one decimal."""
    w = weights(delta)
    return round(sum(w[k] * float(scores[k]) / 4 for k in w), 1)


def finding_quality_score(scores: Mapping[str, float]) -> float:
    """worked_examples.md §1 FQS = sum(w_i s_i / 4) / 74 x 100 over D1, D4-D9."""
    total = sum(WEIGHTS[k] for k in FQS_DIMS)
    return round(sum(WEIGHTS[k] * float(scores[k]) / 4 for k in FQS_DIMS) / total * 100, 1)


def material_verified(hallucinations: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for h in hallucinations if h.get("severity") == "material" and h.get("status") == "verified_false")


def material_suspected(hallucinations: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for h in hallucinations if h.get("severity") == "material" and h.get("status") == "suspected")


def apply_caps(dims: Mapping[str, float], *, n_verified: float, verdict_present: bool
               ) -> tuple[dict[str, float], list[str], str | None]:
    """``(capped dims, caps applied, grade cap)`` for G3 and G4 (GR §4.2)."""
    out = {k: float(v) for k, v in dims.items()}
    caps: list[str] = []
    grade_cap = None
    if not verdict_present:
        out["D2"] = 0.0
        caps.append("G4: no explicit fitness-for-purpose verdict -> D2=0")
    if n_verified >= 2:
        out["D4"] = min(out["D4"], 1.0)
        out["D9"] = min(out["D9"], 2.0)
        grade_cap = "C"
        caps.append(f"G3: {n_verified:g} material hallucinations -> D4<=1, D9<=2, grade<=C")
    elif n_verified >= 1:
        out["D4"] = min(out["D4"], 2.0)
        out["D9"] = min(out["D9"], 2.0)
        grade_cap = "C"
        caps.append(f"G3: {n_verified:g} material hallucination -> D4<=2, D9<=2, grade<=C")
    return out, caps, grade_cap


def gates(dims: Mapping[str, float], *, n_verified: float, verdict_present: bool, injection: bool
          ) -> dict[str, bool]:
    """True = the gate passes. Evaluated on capped scores (GR §4.2 "applied after caps")."""
    return {
        "G1": all(float(v) > 0 for v in dims.values()),
        "G2": all(float(dims[k]) >= 2 for k in CRITICAL),
        "G3": n_verified < 2,
        "G4": verdict_present,
        "G5": not injection,
    }


def grade_band(s: float, gates_ok: bool, dims: Mapping[str, float], grade_cap: str | None = None) -> str:
    """GR §4.4 bands, then the G3 grade cap."""
    if s < 50:
        g = "F"
    elif not gates_ok:
        g = "D"
    elif s >= 85 and min(float(v) for v in dims.values()) >= 3:
        g = "A"
    elif s >= 70:
        g = "B"
    elif s >= PASS_THRESHOLD:
        g = "C"
    else:
        g = "D"
    if grade_cap and "ABCDF".index(g) < "ABCDF".index(grade_cap):
        g = grade_cap
    return g


def score(dims: Mapping[str, float], *, delta: bool, n_verified: float, verdict_present: bool,
          injection: bool) -> dict[str, Any]:
    """Caps, S, gates, grade and pass for one set of dimension scores."""
    capped, caps, grade_cap = apply_caps(dims, n_verified=n_verified, verdict_present=verdict_present)
    g = gates(capped, n_verified=n_verified, verdict_present=verdict_present, injection=injection)
    s = weighted(capped, delta)
    ok = all(g.values())
    return {"dimensions_capped": capped, "caps_applied": caps, "S": s, "gates": g,
            "grade": grade_band(s, ok, capped, grade_cap), "pass": bool(s >= PASS_THRESHOLD and ok)}


def disagreement(samples: Sequence[Mapping[str, Any]], key: str = "dimensions_capped") -> dict[str, float]:
    """Largest per-dimension and S difference over every pair of samples."""
    max_dim, s_delta = 0.0, 0.0
    for i in range(len(samples)):
        for j in range(i + 1, len(samples)):
            a, b = samples[i][key], samples[j][key]
            max_dim = max(max_dim, *(abs(float(a[k]) - float(b[k])) for k in a))
            s_delta = max(s_delta, abs(float(samples[i]["S_raw"]) - float(samples[j]["S_raw"])))
    return {"max_dim_delta": max_dim, "S_delta": round(s_delta, 1)}


def needs_third_sample(dis: Mapping[str, float]) -> bool:
    """prereg ``grader.samples``: a third if any dimension differs by >= 2 or S by >= 8."""
    return dis["max_dim_delta"] >= THIRD_SAMPLE_DIM_DELTA or dis["S_delta"] >= THIRD_SAMPLE_S_DELTA


def median_dims(samples: Sequence[Mapping[str, Any]], dims: Sequence[str], key: str = "dimensions_capped"
                ) -> dict[str, float]:
    return {k: float(statistics.median(float(s[key][k]) for s in samples)) for k in dims}


def modal_agreement(values: Sequence[float]) -> float:
    """Share of values equal to the most common one (V13)."""
    if not values:
        return 0.0
    counts: dict[float, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts.values()) / len(values)
