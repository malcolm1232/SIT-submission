"""``sit-eval score`` says so when the scored run ended its refine phase through the fallback.

A run whose refine answer was rejected, declined, cut or whose one repair call failed applies the merged
assess findings unrefined (or the first answer's kept revisions) and records that as a degradation in
``research_log.degradations``. Its precision is then the fallback's, not the refined agent's, so the scorer
prints one stderr warning naming the run id and the event, and writes ``inputs.refine_fallback_recorded`` and
``inputs.refine_fallback_events`` beside the other run-level fields. No metric value changes. A refine
degradation that is not a fallback (a repair call that returned in full, a model fallback) records false.

Offline: the fake judge only, on builder reviews.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from eval_builders import default_table, make_finding, make_flaw, make_key, make_review, responder_from, run_pipeline

from sit_eval.scoring import refine_fallback_events, validate_scores
from sit_review_agent.phases._model_calls import REFINE_FALLBACK_IMPACT

RUN_ID = "secret-run-opus"   # make_review's run id

INVALID = {"id": "DEG-001", "type": "other",
           "event": "the refine revisions could not be applied after one repair call: FND-002: rank 3 is taken twice",
           "impact": REFINE_FALLBACK_IMPACT}
DECLINED = {"id": "DEG-001", "type": "other",
            "event": "the model declined the refine call after a reframed retry (refusal category: none given)",
            "impact": "the refine step was completed without model output; see the report's limitations"}
REPAIR_FAILED = {"id": "DEG-001", "type": "other",
                 "event": "the refine answer broke the revision rules for 1 finding(s); the one repair call, asked "
                          "for those only, failed (LLMTransportError)",
                 "impact": "1 of 2 refine revisions (one per merged finding) were applied: 1 kept from the first "
                           "answer, which broke the revision rules for 1 finding(s) (FND-002), and 0 repaired by the "
                           "one repair call, which failed (LLMTransportError) with 0 revision(s) for them; 1 "
                           "unrefined (FND-002)"}
DEADLINE_CUT = {"id": "DEG-001", "type": "budget_or_deadline_hit",
                "event": "the refine call was cut by the run deadline (deadline reached)",
                "impact": REFINE_FALLBACK_IMPACT}
REPAIR_RETURNED = {"id": "DEG-001", "type": "other",
                   "event": "the refine answer broke the revision rules for 1 finding(s); the one repair call, asked "
                            "for those only, returned in full",
                   "impact": "2 of 2 refine revisions (one per merged finding) were applied: 1 kept from the first "
                             "answer, which broke the revision rules for 1 finding(s) (FND-002), and 1 repaired by "
                             "the one repair call, which returned in full with 1 revision(s) for them. The merged set "
                             "did not hold together (rank gap), so only its independent revisions were applied; "
                             "0 unrefined"}
MODEL_FALLBACK = {"id": "DEG-002", "type": "model_fallback",
                  "event": "refine call CALL-0007 was served by claude-sonnet-4-5 instead of claude-opus-5-5",
                  "impact": "part of this review was produced by another model; the run is not eval evidence"}


def _review(degradations: list[dict[str, Any]] | None) -> dict[str, Any]:
    review = make_review([make_finding(1, "1"), make_finding(2, "3")])
    if degradations is not None:
        review["research_log"]["degradations"] = degradations
    return review


def _score(tmp_path: Path, degradations: list[dict[str, Any]] | None) -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    key = make_key([make_flaw("FLAW-01", "high", "1"), make_flaw("FLAW-02", "medium", "3")])
    scores, _, _ = run_pipeline(tmp_path, _review(degradations), key, responder_from(default_table()))
    assert validate_scores(scores) == []
    return scores


@pytest.mark.parametrize("deg", [INVALID, DECLINED, REPAIR_FAILED, DEADLINE_CUT],
                         ids=["invalid", "declined", "repair_failed", "deadline_cut"])
def test_refine_fallback_warns_and_records_true(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                deg: dict[str, Any]):
    scores = _score(tmp_path, [deg])
    err = capsys.readouterr().err
    lines = [ln for ln in err.splitlines() if "refine fallback" in ln]
    assert len(lines) == 1, err
    assert RUN_ID in lines[0] and deg["event"][:120] in lines[0]
    assert scores["inputs"]["refine_fallback_recorded"] is True
    assert scores["inputs"]["refine_fallback_events"] == [deg["event"]]
    assert any("refine fallback" in w for w in scores["warnings"])


def test_refine_fallback_changes_no_metric(tmp_path: Path):
    clean = _score(tmp_path / "a", [])
    fell_back = _score(tmp_path / "b", [INVALID, MODEL_FALLBACK])
    assert fell_back["metrics"] == clean["metrics"]
    assert fell_back["inputs"]["refine_fallback_events"] == [INVALID["event"]]


@pytest.mark.parametrize("degs", [None, []], ids=["absent", "empty"])
def test_no_degradations_records_false_and_prints_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                          degs: list[dict[str, Any]] | None):
    scores = _score(tmp_path, degs)
    assert "refine fallback" not in capsys.readouterr().err
    assert scores["inputs"]["refine_fallback_recorded"] is False
    assert scores["inputs"]["refine_fallback_events"] == []
    assert not any("refine fallback" in w for w in scores["warnings"])


def test_refine_degradation_that_is_not_a_fallback_records_false(tmp_path: Path,
                                                                 capsys: pytest.CaptureFixture[str]):
    scores = _score(tmp_path, [REPAIR_RETURNED, MODEL_FALLBACK])
    assert "refine fallback" not in capsys.readouterr().err
    assert scores["inputs"]["refine_fallback_recorded"] is False
    assert scores["inputs"]["refine_fallback_events"] == []


def test_refine_fallback_events_unit():
    assert refine_fallback_events({}) == []
    assert refine_fallback_events({"research_log": None}) == []
    assert refine_fallback_events({"research_log": {"degradations": [REPAIR_RETURNED, MODEL_FALLBACK]}}) == []
    both = {"research_log": {"degradations": [INVALID, REPAIR_RETURNED, DECLINED]}}
    assert refine_fallback_events(both) == [INVALID["event"], DECLINED["event"]]
