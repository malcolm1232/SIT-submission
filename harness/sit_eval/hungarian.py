"""Maximum-weight bipartite assignment (Hungarian / Kuhn-Munkres), pure Python.

Replaces ``scipy.optimize.linear_sum_assignment(W, maximize=True)`` (metrics.md §2.3 step 3) so the
harness needs no new dependency. Rectangular matrices are padded with zeros to a square; padded
cells are never returned. O(n^3) in the larger dimension, which is tiny here (about 21 x 15).
"""

from __future__ import annotations

from collections.abc import Sequence

_INF = float("inf")


def linear_sum_assignment_max(weights: Sequence[Sequence[float]]) -> list[tuple[int, int]]:
    """Row/column pairs of a maximum-total-weight one-to-one assignment.

    Every row is assigned when there are at most as many rows as columns (and vice versa); pairs of
    weight 0 are returned too, so callers drop ineligible pairs themselves, exactly as with scipy.
    Pairs are sorted by row index.
    """
    n_rows = len(weights)
    n_cols = max((len(r) for r in weights), default=0)
    if n_rows == 0 or n_cols == 0:
        return []
    n = max(n_rows, n_cols)
    big = max((abs(float(x)) for r in weights for x in r), default=0.0)
    # Minimisation on cost = big - weight; padded cells cost `big` (weight 0).
    cost = [[big - (float(weights[i][j]) if i < n_rows and j < len(weights[i]) else 0.0) for j in range(n)]
            for i in range(n)]
    # Classic O(n^3) potentials algorithm (1-based arrays; e-maxx formulation).
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)        # p[j] = row matched to column j
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [_INF] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = _INF
            j1 = 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    pairs = [(p[j] - 1, j - 1) for j in range(1, n + 1) if p[j] != 0]
    return sorted((r, c) for r, c in pairs if r < n_rows and c < n_cols)


def assignment_weight(weights: Sequence[Sequence[float]], pairs: Sequence[tuple[int, int]]) -> float:
    return sum(float(weights[r][c]) for r, c in pairs)
