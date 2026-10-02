"""Pure-Python Hungarian assignment against brute force on small matrices."""

from __future__ import annotations

import itertools
import random

import pytest

from sit_eval.hungarian import assignment_weight, linear_sum_assignment_max


def brute_force(w: list[list[float]]) -> float:
    r, c = len(w), len(w[0])
    best = 0.0
    if r <= c:
        for cols in itertools.permutations(range(c), r):
            best = max(best, sum(w[i][cols[i]] for i in range(r)))
    else:
        for rows in itertools.permutations(range(r), c):
            best = max(best, sum(w[rows[j]][j] for j in range(c)))
    return best


@pytest.mark.parametrize("seed", range(150))
def test_matches_brute_force(seed: int) -> None:
    rng = random.Random(seed)
    r, c = rng.randint(1, 6), rng.randint(1, 6)
    kind = seed % 3
    if kind == 0:     # matcher-like: sparse eligible scores with severity tie-breaks
        w = [[(rng.choice([0, 0, 0, 3]) + 0.01 * rng.choice([1, 2, 4, 8])) if rng.random() < 0.5 else 0.0
              for _ in range(c)] for _ in range(r)]
    elif kind == 1:   # many ties
        w = [[float(rng.randint(0, 2)) for _ in range(c)] for _ in range(r)]
    else:
        w = [[rng.random() * 10 for _ in range(c)] for _ in range(r)]
    pairs = linear_sum_assignment_max(w)
    assert len({p[0] for p in pairs}) == len(pairs) and len({p[1] for p in pairs}) == len(pairs)
    assert len(pairs) == min(r, c)
    assert assignment_weight(w, pairs) == pytest.approx(brute_force(w))


def test_empty_and_degenerate() -> None:
    assert linear_sum_assignment_max([]) == []
    assert linear_sum_assignment_max([[]]) == []
    assert linear_sum_assignment_max([[0.0, 0.0]]) in ([(0, 0)], [(0, 1)])
    assert linear_sum_assignment_max([[5.0]]) == [(0, 0)]


def test_prefers_more_severe_flaw_on_tie() -> None:
    # one finding scores 3 on a low and a critical flaw; the epsilon term picks the critical one
    w = [[3 + 0.01 * 1, 3 + 0.01 * 8]]
    assert linear_sum_assignment_max(w) == [(0, 1)]
