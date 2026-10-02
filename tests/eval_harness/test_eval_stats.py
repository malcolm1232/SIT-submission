"""Statistics helpers (metrics.md §12, prereg statistics)."""

from __future__ import annotations

import math

import pytest

from sit_eval import stats


def test_percentile_matches_numpy_linear():
    v = [1, 2, 3, 4, 10]
    assert stats.percentile(v, 50) == 3
    assert stats.percentile(v, 2.5) == pytest.approx(1.1)
    assert stats.percentile(v, 97.5) == pytest.approx(9.4)
    assert stats.percentile([5], 97.5) == 5


def test_macro_and_micro_aggregation():
    per = {"d1": [0.5, 0.7, None], "d2": [1.0, 1.0, 1.0]}
    assert stats.macro_point(per) == pytest.approx((0.6 + 1.0) / 2)
    nd = {"d1": [(7, 14), (8, 14)], "d2": [(10, 14), (12, 14)]}
    assert stats.micro_point(nd) == pytest.approx(((17 / 28) + (20 / 28)) / 2)


def test_cluster_bootstrap_is_seeded_and_brackets_the_point():
    per = {"d1": [0.5, 0.6, 0.55], "d2": [0.8, 0.7, 0.75], "d3": [0.4, 0.45, 0.5]}
    p1, ci1 = stats.cluster_bootstrap(per, B=2000, seed=0)
    p2, ci2 = stats.cluster_bootstrap(per, B=2000, seed=0)
    assert (p1, ci1) == (p2, ci2)
    assert p1 == pytest.approx((0.55 + 0.75 + 0.45) / 3)
    assert ci1[0] <= p1 <= ci1[1] and ci1[0] >= 0.4 and ci1[1] <= 0.8
    assert stats.cluster_bootstrap({"d": [None]}, B=10) == (None, None)
    pr, cir = stats.cluster_bootstrap_ratio({"d1": [(7, 14), (8, 14)], "d2": [(12, 14)]}, B=500, seed=0)
    assert pr == pytest.approx(27 / 42) and cir[0] <= pr <= cir[1]


def test_paired_diff_and_non_inferiority():
    a = {"d1": [0.8, 0.9], "d2": [0.7, 0.8], "d3": [0.9, 0.9]}
    b = {"d1": [0.5, 0.5], "d2": [0.4, 0.5], "d3": [0.6, 0.5]}
    r = stats.paired_diff(a, b, B=2000, seed=1)
    assert r["point"] == pytest.approx(((0.85 - 0.5) + (0.75 - 0.45) + (0.9 - 0.55)) / 3)
    assert r["ci"][0] > 0 and r["p_two_sided"] < 0.05 and r["docs"] == ["d1", "d2", "d3"]
    assert stats.non_inferiority_p(b, a, 0.10, B=1000) > 0.5      # B is clearly worse by more than 0.10


def test_sign_flip_exact():
    r = stats.sign_flip_test({f"d{i}": 0.1 * (i + 1) for i in range(5)})
    assert r["p_greater"] == pytest.approx(1 / 32) and r["p_two_sided"] == pytest.approx(2 / 32)
    assert r["min_attainable_one_sided_p"] == pytest.approx(1 / 32)
    mixed = stats.sign_flip_test({"a": 0.2, "b": -0.2})
    assert mixed["p_two_sided"] == pytest.approx(1.0)


def test_mcnemar_exact_and_chi2():
    r = stats.mcnemar(1, 9)
    assert r["method"] == "exact_binomial" and r["p_two_sided"] == pytest.approx(2 * 11 / 1024)
    r = stats.mcnemar(5, 25)
    assert r["method"] == "chi2_continuity" and r["statistic"] == pytest.approx(19 ** 2 / 30)
    assert r["p_two_sided"] == pytest.approx(math.erfc(math.sqrt(19 ** 2 / 30 / 2)))
    assert stats.mcnemar(0, 0)["p_two_sided"] == 1.0


def test_holm_and_bh():
    assert stats.holm([0.01, 0.04, 0.03, 0.005]) == [True, False, False, True]
    assert stats.holm([0.001, 0.2]) == [True, False]
    assert stats.benjamini_hochberg([0.01, 0.04, 0.03, 0.005], q=0.05) == [True, True, True, True]
    assert stats.benjamini_hochberg([0.5, 0.04, 0.03, 0.2], q=0.10) == [False, True, True, False]


def test_stratified_permutation_and_wilson():
    pairs = {"d1": [(1, 0)] * 6 + [(1, 1)] * 8, "d2": [(1, 0)] * 5 + [(0, 0)] * 9}
    r = stats.stratified_permutation_test(pairs, B=2000, seed=3)
    assert r["observed"] > 0 and r["p_two_sided"] < 0.01
    lo, hi = stats.wilson_interval(0, 9)
    assert lo == 0.0 and hi == pytest.approx(0.299, abs=0.002)    # prereg: 0 of 9 -> about 0.30
