"""Aggregation and inference (metrics.md §12, prereg ``statistics``). Pure Python, seeded.

* Point estimates: per run -> mean over a document's runs -> mean over documents (macro).
  Micro (pooled) ratios pool numerator and denominator across documents within each run index,
  then average over run indices.
* Two-level cluster bootstrap (documents, then runs within a document), percentile CI.
* Paired difference between conditions on the same documents (bootstrap CI and approximate p).
* Document-level exact sign-flip test (prereg small_cluster_caveat (a)).
* Flaw-level paired permutation test stratified by document (prereg (b)); the design-effect
  variance inflation needs the pilot's rho and is not applied here.
* McNemar on discordant flaws (sanity check), Holm, Benjamini-Hochberg, Wilson bounds.

The bootstrap uses :class:`random.Random`, not NumPy, so its draws differ from the metrics.md
pseudo-code for the same seed; the procedure is the same.
"""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Callable, Mapping, Sequence


def _finite(xs: Sequence[float | None]) -> list[float]:
    return [float(x) for x in xs if x is not None and math.isfinite(float(x))]


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def percentile(values: Sequence[float], q: float) -> float:
    """NumPy's default (linear interpolation) percentile."""
    v = sorted(values)
    if not v:
        raise ValueError("percentile of an empty sequence")
    pos = (len(v) - 1) * q / 100
    lo = math.floor(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def macro_point(per_doc_runs: Mapping[str, Sequence[float | None]]) -> float | None:
    docs = [_finite(v) for v in per_doc_runs.values()]
    docs = [d for d in docs if d]
    return mean([mean(d) for d in docs]) if docs else None


def micro_point(per_doc_runs: Mapping[str, Sequence[tuple[float, float] | None]]) -> float | None:
    """Pooled ratio per run index (num and den summed over documents), averaged over run indices."""
    k = max((len(v) for v in per_doc_runs.values()), default=0)
    vals = []
    for j in range(k):
        num = den = 0.0
        for runs in per_doc_runs.values():
            if j < len(runs) and runs[j] is not None:
                num += runs[j][0]
                den += runs[j][1]
        if den > 0:
            vals.append(num / den)
    return mean(vals) if vals else None


def cluster_bootstrap(per_doc_runs: Mapping[str, Sequence[float | None]], *, B: int = 10_000, seed: int = 0,
                      stat: Callable[[list[float]], float] = mean) -> tuple[float | None, tuple[float, float] | None]:
    """metrics.md §12.2: resample documents, then runs within each sampled document."""
    docs = {d: _finite(v) for d, v in per_doc_runs.items()}
    docs = {d: v for d, v in docs.items() if v}
    if not docs:
        return None, None
    names = sorted(docs)
    rng = random.Random(seed)
    boot = []
    for _ in range(B):
        means = []
        for d in (rng.choice(names) for _ in names):
            runs = docs[d]
            means.append(mean([rng.choice(runs) for _ in runs]))
        boot.append(stat(means))
    point = stat([mean(docs[d]) for d in names])
    return point, (percentile(boot, 2.5), percentile(boot, 97.5))


def cluster_bootstrap_ratio(per_doc_runs: Mapping[str, Sequence[tuple[float, float]]], *, B: int = 10_000,
                            seed: int = 0) -> tuple[float | None, tuple[float, float] | None]:
    """Micro (ratio) metrics: resample documents and runs, recompute the pooled ratio (§12.2 note)."""
    docs = {d: list(v) for d, v in per_doc_runs.items() if v}
    if not docs:
        return None, None
    names = sorted(docs)
    rng = random.Random(seed)
    boot = []
    for _ in range(B):
        num = den = 0.0
        for d in (rng.choice(names) for _ in names):
            for n_, d_ in (rng.choice(docs[d]) for _ in docs[d]):
                num += n_
                den += d_
        if den > 0:
            boot.append(num / den)
    num = sum(n for d in names for n, _ in docs[d])
    den = sum(x for d in names for _, x in docs[d])
    point = num / den if den else None
    return point, ((percentile(boot, 2.5), percentile(boot, 97.5)) if boot else None)


def paired_diff(per_a: Mapping[str, Sequence[float]], per_b: Mapping[str, Sequence[float]], *, B: int = 10_000,
                seed: int = 1) -> dict[str, object]:
    """metrics.md §12.3 on the documents both conditions share."""
    docs = sorted(d for d in set(per_a) & set(per_b) if _finite(per_a[d]) and _finite(per_b[d]))
    if not docs:
        return {"point": None, "ci": None, "p_two_sided": None, "p_greater": None, "p_less": None, "docs": []}
    a = {d: _finite(per_a[d]) for d in docs}
    b = {d: _finite(per_b[d]) for d in docs}
    rng = random.Random(seed)
    diffs = []
    for _ in range(B):
        ds = [rng.choice(docs) for _ in docs]
        ma = mean([mean([rng.choice(a[d]) for _ in a[d]]) for d in ds])
        mb = mean([mean([rng.choice(b[d]) for _ in b[d]]) for d in ds])
        diffs.append(ma - mb)
    point = mean([mean(a[d]) - mean(b[d]) for d in docs])
    le = sum(x <= 0 for x in diffs) / B
    ge = sum(x >= 0 for x in diffs) / B
    return {"point": point, "ci": (percentile(diffs, 2.5), percentile(diffs, 97.5)),
            "p_two_sided": min(2 * min(le, ge), 1.0), "p_greater": le, "p_less": ge, "docs": docs}


def non_inferiority_p(per_a: Mapping[str, Sequence[float]], per_b: Mapping[str, Sequence[float]], margin: float, *,
                      B: int = 10_000, seed: int = 1) -> float | None:
    """One-sided bootstrap p for H0: mean(A - B) <= -margin (prereg H3/H4)."""
    shifted = {d: [x + margin for x in _finite(v)] for d, v in per_a.items()}
    res = paired_diff(shifted, per_b, B=B, seed=seed)
    return res["p_greater"]  # type: ignore[return-value]


def sign_flip_test(doc_diffs: Mapping[str, float]) -> dict[str, float | int | None]:
    """Exact document-level sign-flip test on per-document mean differences (2^n patterns)."""
    d = [float(x) for x in doc_diffs.values()]
    n = len(d)
    if n == 0:
        return {"n_docs": 0, "observed": None, "p_two_sided": None, "p_greater": None, "p_less": None}
    obs = mean(d)
    stats = [mean([s * x for s, x in zip(signs, d, strict=True)]) for signs in itertools.product((1, -1), repeat=n)]
    eps = 1e-12
    total = len(stats)
    return {"n_docs": n, "observed": obs,
            "p_two_sided": sum(abs(s) >= abs(obs) - eps for s in stats) / total,
            "p_greater": sum(s >= obs - eps for s in stats) / total,
            "p_less": sum(s <= obs + eps for s in stats) / total,
            "min_attainable_one_sided_p": 1 / total}


def stratified_permutation_test(pairs_by_doc: Mapping[str, Sequence[tuple[int, int]]], *, B: int = 10_000,
                                seed: int = 2) -> dict[str, float | None]:
    """Flaw-level paired outcomes (A detected, B detected) per document; labels swapped within each
    pair at random. Statistic: mean over documents of the per-document mean difference."""
    docs = {d: list(v) for d, v in pairs_by_doc.items() if v}
    if not docs:
        return {"observed": None, "p_two_sided": None}

    def stat(data: Mapping[str, list[tuple[int, int]]]) -> float:
        return mean([mean([a - b for a, b in v]) for v in data.values()])

    obs = stat(docs)
    rng = random.Random(seed)
    hits = 0
    for _ in range(B):
        perm = {d: [(a, b) if rng.random() < 0.5 else (b, a) for a, b in v] for d, v in docs.items()}
        hits += abs(stat(perm)) >= abs(obs) - 1e-12
    return {"observed": obs, "p_two_sided": hits / B,
            "note": "design-effect variance inflation (pilot rho) not applied"}  # type: ignore[dict-item]


def mcnemar(b: int, c: int) -> dict[str, float | str | None]:
    """Discordant counts b (A only) and c (B only). Exact binomial when b + c < 25, else chi-square
    with continuity correction (metrics.md §12.3)."""
    n = b + c
    if n == 0:
        return {"method": "none", "statistic": None, "p_two_sided": 1.0}
    if n < 25:
        k = min(b, c)
        p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
        return {"method": "exact_binomial", "statistic": float(k), "p_two_sided": p}
    chi2 = (abs(b - c) - 1) ** 2 / n
    return {"method": "chi2_continuity", "statistic": chi2, "p_two_sided": math.erfc(math.sqrt(chi2 / 2))}


def holm(pvals: Sequence[float], alpha: float = 0.05) -> list[bool]:
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    reject = [False] * m
    for rank, i in enumerate(order):
        if pvals[i] <= alpha / (m - rank):
            reject[i] = True
        else:
            break
    return reject


def benjamini_hochberg(pvals: Sequence[float], q: float = 0.10) -> list[bool]:
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    k = 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            k = rank
    reject = [False] * m
    for i in order[:k]:
        reject[i] = True
    return reject


def wilson_interval(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)
