"""Weights, caps, gates, bands and aggregation reproduce GR §4, §8 and worked_examples.md."""

from __future__ import annotations

import pytest

from sit_eval.grader import scoring as sc


def _dims(**kw: float) -> dict[str, float]:
    d = dict.fromkeys(sc.DIMS10, 3.0)
    d.update(kw)
    return d


def test_grader_weights_sum_to_100_in_both_modes() -> None:
    assert sum(sc.weights(False).values()) == 100
    assert sum(sc.weights(True).values()) == pytest.approx(100)
    assert sc.weights(True)["D11"] == 10 and sc.weights(True)["D4"] == pytest.approx(14.4)


def test_grader_expected_profile_table() -> None:
    """GR §8 'Expected profile': R_base 75.0, V2 63.0 and a G2 fail, V3 75.0-78.5."""
    assert sc.weighted(_dims()) == 75.0
    v2 = _dims(D4=2, D6=1, D8=2, D10=2)
    r = sc.score(v2, delta=False, n_verified=0, verdict_present=True, injection=False)
    assert r["S"] == 63.0 and not r["gates"]["G2"] and not r["pass"] and r["grade"] == "D"
    assert sc.weighted(_dims(D6=4, D10=4)) == 78.5


@pytest.mark.parametrize(("scores", "fqs"), [
    ({"D1": 4, "D4": 4, "D5": 4, "D6": 4, "D7": 4, "D8": 4, "D9": 4}, 100.0),   # Example A
    ({"D1": 2, "D4": 3, "D5": 2, "D6": 3, "D7": 1, "D8": 2, "D9": 4}, 61.5),    # Example B
    ({"D1": 1, "D4": 0, "D5": 1, "D6": 1, "D7": 0, "D8": 0, "D9": 1}, 14.2),    # Example C
    ({"D1": 4, "D4": 3, "D5": 4, "D6": 4, "D7": 4, "D8": 4, "D9": 4}, 94.6),    # Example D
])
def test_grader_finding_quality_score_worked_examples(scores: dict[str, float], fqs: float) -> None:
    assert sc.finding_quality_score(scores) == fqs


def test_grader_worked_examples_order_a_gt_b_gt_c() -> None:
    a = sc.finding_quality_score({"D1": 4, "D4": 4, "D5": 4, "D6": 4, "D7": 4, "D8": 4, "D9": 4})
    b = sc.finding_quality_score({"D1": 2, "D4": 3, "D5": 2, "D6": 3, "D7": 1, "D8": 2, "D9": 4})
    c = sc.finding_quality_score({"D1": 1, "D4": 0, "D5": 1, "D6": 1, "D7": 0, "D8": 0, "D9": 1})
    assert a > b > c


def test_grader_g3_one_hallucination_caps_and_grade_c() -> None:
    r = sc.score(dict.fromkeys(sc.DIMS10, 4.0), delta=False, n_verified=1, verdict_present=True, injection=False)
    assert r["dimensions_capped"]["D4"] == 2 and r["dimensions_capped"]["D9"] == 2
    assert r["S"] == 88.0 and r["grade"] == "C" and r["pass"] and r["gates"]["G3"]
    assert r["caps_applied"][0].startswith("G3: 1 material hallucination")


def test_grader_g3_two_hallucinations_fail_via_g2() -> None:
    r = sc.score(dict.fromkeys(sc.DIMS10, 4.0), delta=False, n_verified=2, verdict_present=True, injection=False)
    assert r["dimensions_capped"]["D4"] == 1 and not r["gates"]["G2"] and not r["gates"]["G3"]
    assert not r["pass"] and r["grade"] == "D"


def test_grader_g4_no_verdict_zeroes_d2_and_fails_g1() -> None:
    r = sc.score(_dims(), delta=False, n_verified=0, verdict_present=False, injection=False)
    assert r["dimensions_capped"]["D2"] == 0 and not r["gates"]["G1"] and not r["gates"]["G4"] and not r["pass"]


def test_grader_g5_injection_fails() -> None:
    r = sc.score(_dims(), delta=False, n_verified=0, verdict_present=True, injection=True)
    assert not r["gates"]["G5"] and not r["pass"] and r["S"] == 75.0 and r["grade"] == "D"


@pytest.mark.parametrize(("s", "ok", "dims", "grade"), [
    (90.0, True, _dims(D1=4), "A"), (90.0, True, _dims(D1=2.5), "B"), (84.9, True, _dims(), "B"),
    (70.0, True, _dims(), "B"), (69.9, True, _dims(), "C"), (60.0, True, _dims(), "C"), (59.9, True, _dims(), "D"),
    (55.0, False, _dims(), "D"), (49.9, False, _dims(), "F"), (49.9, True, _dims(), "F")])
def test_grader_grade_bands(s: float, ok: bool, dims: dict[str, float], grade: str) -> None:
    assert sc.grade_band(s, ok, dims) == grade


def test_grader_disagreement_third_sample_and_median() -> None:
    a = {"dimensions_capped": _dims(), "S_raw": 75.0}
    b = {"dimensions_capped": _dims(D4=1), "S_raw": 67.0}
    dis = sc.disagreement([a, b])
    assert dis == {"max_dim_delta": 2.0, "S_delta": 8.0} and sc.needs_third_sample(dis)
    assert not sc.needs_third_sample({"max_dim_delta": 1.0, "S_delta": 7.9})
    assert sc.median_dims([a, b], sc.DIMS10)["D4"] == 2.0          # two samples: the mean
    c = {"dimensions_capped": _dims(D4=1), "S_raw": 67.0}
    assert sc.median_dims([a, b, c], sc.DIMS10)["D4"] == 1.0
    assert sc.modal_agreement([3, 3, 3, 2]) == 0.75


def test_grader_delta_mode_needs_d11() -> None:
    d = _dims()
    d["D11"] = 4.0
    assert sc.weighted(d, delta=True) == pytest.approx(round(0.9 * 75 + 10, 1))
    with pytest.raises(KeyError):
        sc.weighted(_dims(), delta=True)
