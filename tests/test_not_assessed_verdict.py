"""The ``not_assessed`` verdict (spec VerdictLabel, 2026-10-03): the label of a run that produced no
assessment. It replaces the earlier placeholder (``not_fit`` at confidence 0), which read as a
judgement of the design and which the grader counted as an explicit fitness verdict.

* spec, taxonomy and models agree, and reject a ``not_assessed`` verdict that carries a judgement;
* the model cannot choose it: no LLM-facing schema offers it and a draft that carries it is refused;
* ``report`` sets it in code on both no-assessment paths (deadline, declined assess) without a
  verdict call, and ``report.md`` says so;
* the harness loads such a review, the scorer flags it, and the grader's G4 gate does not count it
  as a fitness verdict.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from sit_review_agent import models as m
from sit_review_agent.invariants import check_all, spec_validator
from sit_review_agent.llm.gateway import FakeResponse
from sit_review_agent.llm.outputs import PHASE_OUTPUT_TYPES, AssessedVerdictLabel, ReportOutput, llm_facing_schema
from sit_review_agent.llm.runtime import OUT_OF_TIME_BEFORE_ASSESSMENT
from sit_review_agent.manifest import start_manifest
from sit_review_agent.models import DegradationType, Review, VerdictLabel
from sit_review_agent.phases.report import ReportPhase, assessment_missing, not_assessed_verdict
from sit_review_agent.phases.verify import VerifyPhase
from sit_review_agent.report.render import render_markdown, verdict_label_text
from sit_review_agent.states import PhaseName
from test_ingest_verify_report import REPORT_OK, ingested

NOT_ASSESSED = "not_assessed"
DECLINED_EVENT = "the model declined the assess call after a reframed retry (refusal category: cyber)"


def schema_errors(obj: Any) -> list[str]:
    return [e.message for e in spec_validator("Review").iter_errors(obj)]


def not_assessed_review(review_dict: dict[str, Any]) -> dict[str, Any]:
    """The spec's example Review turned into the review of a run with no assessment."""
    d = copy.deepcopy(review_dict)
    d["verdict"] = not_assessed_verdict().model_dump(mode="json")
    d["findings"], d["sound_areas"], d["unresolved"] = [], [], []
    d["research_log"]["degradations"] = [{"id": "DEG-001", "type": "budget_or_deadline_hit",
                                          "event": f"{OUT_OF_TIME_BEFORE_ASSESSMENT}: the assess call was cut",
                                          "impact": "the design was not assessed"}]
    d["limitations"] = [{"text": "Out of time before assessment.", "degradation_ids": ["DEG-001"]}]
    d["stop_reason"] = {"code": "deadline", "group": "cap", "detail": None}
    return d


# ============================================================================ spec, taxonomy, models


def test_not_assessed_verdict_carries_no_judgement() -> None:
    v = not_assessed_verdict()
    assert v.label is VerdictLabel.NOT_ASSESSED and v.label.value == NOT_ASSESSED      # not the old `not_fit`
    assert v.confidence == 0.0 and v.conditions == [] and v.per_objective == []
    assert v.rationale.startswith("Not assessed") and "not a judgement" in v.rationale
    declined = not_assessed_verdict("declined")
    assert declined.label is VerdictLabel.NOT_ASSESSED and "declined the assess call" in declined.rationale


@pytest.mark.parametrize("patch,needle", [
    ({"confidence": 0.4}, "confidence 0"),
    ({"conditions": [{"text": "Fix it.", "finding_ids": ["FND-001"]}]}, "no conditions"),
    ({"per_objective": [{"objective_ref": "FR-9", "label": "fit", "finding_ids": []}]}, "no per_objective"),
])
def test_model_and_schema_reject_a_not_assessed_verdict_with_a_judgement(review_dict: dict[str, Any],
                                                                         patch: dict[str, Any], needle: str) -> None:
    good = not_assessed_review(review_dict)
    bad = copy.deepcopy(good)
    bad["verdict"].update(patch)
    with pytest.raises(ValidationError, match=needle):
        m.Verdict.model_validate(bad["verdict"])
    assert schema_errors(bad) and schema_errors(good) == []


def test_per_objective_label_can_never_be_not_assessed(review_dict: dict[str, Any]) -> None:
    bad = copy.deepcopy(review_dict)
    bad["verdict"]["per_objective"][0]["label"] = NOT_ASSESSED
    with pytest.raises(ValidationError, match="per-objective"):
        m.Review.model_validate(bad)
    assert schema_errors(bad)


def test_review_rules_for_a_not_assessed_verdict(review_dict: dict[str, Any]) -> None:
    good = not_assessed_review(review_dict)
    assert schema_errors(good) == []
    review = Review.model_validate(good)
    assert review.model_dump(mode="json") == good
    with_findings = copy.deepcopy(good)
    with_findings["findings"] = [review_dict["findings"][1]]
    with pytest.raises(ValidationError, match="no findings"):
        Review.model_validate(with_findings)
    assert schema_errors(with_findings)
    undisclosed = copy.deepcopy(good)
    undisclosed["research_log"]["degradations"], undisclosed["limitations"] = [], []
    undisclosed["stop_reason"] = review_dict["stop_reason"]
    with pytest.raises(ValidationError, match="disclose"):
        Review.model_validate(undisclosed)
    assert schema_errors(undisclosed)


# ============================================================================ the model cannot choose it


def test_no_llm_facing_schema_offers_not_assessed() -> None:
    assert {e.value for e in AssessedVerdictLabel} == {e.value for e in VerdictLabel} - {NOT_ASSESSED}
    for phase, out in PHASE_OUTPUT_TYPES.items():
        assert NOT_ASSESSED not in json.dumps(llm_facing_schema(out)), phase
        assert NOT_ASSESSED not in json.dumps(out.model_json_schema()), phase
    labels = llm_facing_schema(ReportOutput)["$defs"]["AssessedVerdictLabel"]["enum"]
    assert labels == ["fit", "fit_with_conditions", "not_fit"]


@pytest.mark.parametrize("where", ["verdict", "per_objective"])
def test_a_draft_that_says_not_assessed_is_refused(where: str) -> None:
    draft = copy.deepcopy(REPORT_OK.parsed)
    if where == "verdict":
        draft["verdict"]["label"] = NOT_ASSESSED
    else:
        draft["verdict"]["per_objective"] = [{"objective_ref": "FR-9", "label": NOT_ASSESSED, "finding_ids": []}]
    with pytest.raises(ValidationError):
        ReportOutput.model_validate(draft)


# ============================================================================ report phase


async def unassessed(tmp_path: Path, script: dict[str, list[FakeResponse]], *, reason: str) -> Any:
    """A run whose assess stage produced nothing: verified, ready for ``report``."""
    ctx = await ingested(tmp_path, script)
    if reason == "deadline":
        ctx.state.add_degradation(DegradationType.BUDGET_OR_DEADLINE_HIT,
                                  f"{OUT_OF_TIME_BEFORE_ASSESSMENT}: the assess call was cut by the run deadline",
                                  "the design was not assessed")
    else:
        ctx.state.add_degradation(DegradationType.OTHER, DECLINED_EVENT,
                                  "the assess step was completed without model output")
        ctx.state.declined_sections.append(PhaseName.ASSESS.value)
    ctx.registry.record_iteration(1)
    ctx.state.registry_hashes = ctx.registry.hashes()
    start_manifest(ctx)
    return await VerifyPhase().run(ctx)


@pytest.mark.parametrize("reason,shown", [
    ("deadline", "Not assessed (out of time before assessment)"),
    ("declined", "Not assessed (the model declined the assessment)"),
])
async def test_report_sets_not_assessed_in_code_without_a_verdict_call(tmp_path: Path, reason: str,
                                                                       shown: str) -> None:
    # The scripted verdict would certify the design; it must never be asked for.
    fit = FakeResponse(parsed={"verdict": {"label": "fit", "rationale": "Looks fine.", "confidence": 0.9,
                                           "conditions": [], "per_objective": [], "what_would_change_it": None},
                               "unresolved": [], "limitations": []})
    ctx = await unassessed(tmp_path, {"report": [fit]}, reason=reason)
    ctx = await ReportPhase().run(ctx)
    data = json.loads(ctx.run_dir.report_json.read_text(encoding="utf-8"))
    assert data["verdict"]["label"] == NOT_ASSESSED and data["verdict"]["confidence"] == 0
    assert data["findings"] == [] and data["sound_areas"] == []
    assert [c for c in ctx.llm.calls if c.phase is PhaseName.REPORT] == []
    assert [r.inv_id for r in check_all(data, ctx.run_dir.root) if not r.passed] == []
    md = ctx.run_dir.report_md.read_text(encoding="utf-8")
    assert f"| Verdict | **{shown.lower()}**" in md and f"**{shown}** (confidence 0.00)" in md
    assert "not fit" not in md.lower()
    review = Review.model_validate(data)
    assert verdict_label_text(review) == shown.lower() and render_markdown(review).count(shown) == 1


def test_assessment_missing_names_the_reason() -> None:
    cut = [f"{OUT_OF_TIME_BEFORE_ASSESSMENT}: stop rule deadline (deadline) fired before assess"]
    assert assessment_missing(cut, []) == "deadline"
    assert assessment_missing([DECLINED_EVENT], ["assess"]) == "declined"
    assert assessment_missing(cut, ["assess"]) == "deadline"
    assert assessment_missing(["stop rule deadline (deadline) before refine"], ["research", "refine"]) is None


async def test_a_model_verdict_of_not_assessed_never_reaches_the_report(tmp_path: Path) -> None:
    """A model that answers ``not_assessed`` breaks the output schema; the verdict then comes from
    the rule over the findings, never from the model's label."""
    from test_ingest_verify_report import verified

    bad = copy.deepcopy(REPORT_OK.parsed)
    bad["verdict"].update(label=NOT_ASSESSED, confidence=0, conditions=[])
    ctx = await verified(tmp_path, {"report": [FakeResponse(text=json.dumps(bad))]})
    ctx = await ReportPhase().run(ctx)
    data = json.loads(ctx.run_dir.report_json.read_text(encoding="utf-8"))
    assert data["findings"] and data["verdict"]["label"] == "fit_with_conditions"
    assert "derived by rule" in data["verdict"]["rationale"]


# ============================================================================ harness


def test_harness_loads_flags_and_does_not_credit_a_not_assessed_review(tmp_path: Path,
                                                                       review_dict: dict[str, Any]) -> None:
    from sit_eval.aggregate import load_scores
    from sit_eval.grader import fake as grader_fake
    from sit_eval.grader.verify import FITNESS_VERDICT_LABELS, verdict_present
    from sit_eval.loaders import load_review
    from sit_eval.scoring import NOT_ASSESSED_NOTE, _verdict_label, validate_scores

    data = not_assessed_review(review_dict)
    (tmp_path / "report.json").write_text(json.dumps(data), encoding="utf-8")
    rin = load_review(tmp_path)                                   # spec schema and the agent model both accept it
    assert rin.review.verdict.label is VerdictLabel.NOT_ASSESSED and _verdict_label(rin) == NOT_ASSESSED
    # G4: no explicit fitness verdict. The old placeholder (`not_fit` at confidence 0) passed this gate.
    assert NOT_ASSESSED not in FITNESS_VERDICT_LABELS and grader_fake.FITNESS_VERDICT_LABELS is FITNESS_VERDICT_LABELS
    assert verdict_present(data) is False
    placeholder = copy.deepcopy(data)
    placeholder["verdict"]["label"] = "not_fit"
    assert verdict_present(placeholder) is True
    assert "intention-to-treat" in NOT_ASSESSED_NOTE
    scores = {"kind": "sit_eval.scores", "status": "pilot_unfrozen", "inputs": {"verdict_label": NOT_ASSESSED}}
    p = tmp_path / "scores.json"
    p.write_text(json.dumps(scores), encoding="utf-8")
    rows, warnings = load_scores([p])
    assert len(rows) == 1 and any("not assessed" in w for w in warnings)
    assert not [e for e in validate_scores({"inputs": {"verdict_label": NOT_ASSESSED}}) if "verdict_label" in e]
    assert [e for e in validate_scores({"inputs": {"verdict_label": "unknown"}}) if "verdict_label" in e]
