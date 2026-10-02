"""Regression tests for the defects found by the E2 grader verifier (research/audit/verify_grader_editlog.md)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft7Validator
from typer.testing import CliRunner

from sit_eval.cli import app
from sit_eval.grader import BudgetExceeded, GraderError, grade_review, schemas
from sit_eval.grader import cli as grader_cli
from sit_eval.grader import projection as pj
from sit_eval.grader.answer_key import load_answer_key
from sit_eval.grader.costs import Budget
from sit_eval.grader.fake import heuristic_responder
from sit_eval.grader.report import render_markdown
from sit_eval.judge import FakeJudge, JudgeRequest, JudgeResult

runner = CliRunner()
REPO = Path(__file__).resolve().parents[2]
LIVE_REVIEW = REPO / "docs" / "live_runs" / "live_cc_opus_payments_v1" / "report.json"


def _keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in _keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in _keys(v)}
    return set()


# ------------------------------------------------------------------ 1. LLM-facing schema and claude -p
@pytest.mark.parametrize("name", [schemas.PASS_A, schemas.PASS_B])
def test_grader_llm_facing_schema_drops_dollar_schema(name: str) -> None:
    """``claude -p --json-schema`` rejected the whole schema while it named draft 2020-12 (live check)."""
    llm = schemas.llm_facing(name)
    assert "$schema" not in _keys(llm)
    Draft7Validator.check_schema(llm)                 # the CLI's validator default is draft-07
    assert "$schema" in schemas.load_schema(name)     # the full schema (and the prompt hash) is unchanged
    assert set(llm["properties"]) == set(schemas.load_schema(name)["properties"])


# ------------------------------------------------------------------------ 2. any judge exception
class _Raiser:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.calls: list[JudgeRequest] = []

    async def complete(self, request: JudgeRequest) -> JudgeResult:
        self.calls.append(request)
        raise self.exc


@pytest.mark.parametrize("exc", [TimeoutError("slow backend"), RuntimeError("client bug")])
def test_grader_non_judge_error_ends_grade_cleanly(tmp_path: Path, graded_inputs, exc: Exception) -> None:
    out = tmp_path / "o"
    with pytest.raises(GraderError, match=type(exc).__name__):
        grade_review(*graded_inputs, out, judge=_Raiser(exc))
    rep = json.loads((out / "grade.json").read_text())
    assert rep["status"] == "failed" and type(exc).__name__ in rep["error"]
    log = [json.loads(x) for x in (out / "grader_calls.jsonl").read_text().splitlines()]
    assert log and log[0]["ok"] is False and type(exc).__name__ in log[0]["error"]


def test_grader_cli_judge_exception_exits_3(tmp_path: Path, graded_inputs, monkeypatch) -> None:
    review, pages = graded_inputs
    monkeypatch.setattr(grader_cli, "_judge", lambda kind, out, exploratory=False: _Raiser(TimeoutError("slow")))
    r = runner.invoke(app, ["grade", "run", str(review), "--pdf", str(pages), "--out", str(tmp_path / "o")])
    assert r.exit_code == 3, r.output
    assert json.loads((tmp_path / "o" / "grade.json").read_text())["status"] == "failed"


# ------------------------------------------------------------------------------ 3. budget boundary
def test_grader_budget_allows_a_call_landing_exactly_on_the_limit() -> None:
    b = Budget(max_cost_usd=0.3)
    b.add(0.1)
    b.check("x", 0.2)                 # 0.1 + 0.2 is 0.30000000000000004 in floats; still allowed
    b.add(0.2)
    b.check("y", 0.0)
    with pytest.raises(BudgetExceeded):
        b.check("z", 0.0001)
    assert [r["purpose"] for r in b.refused] == ["z"]


class _Costly:
    """Reports $0.25 per call; with a $1.00 limit the fourth call lands exactly on it."""

    def __init__(self) -> None:
        self.calls: list[JudgeRequest] = []

    async def complete(self, request: JudgeRequest) -> JudgeResult:
        self.calls.append(request)
        return JudgeResult(data=heuristic_responder(request), model="fake-costly", cost_usd=0.25)


def test_grader_budget_boundary_in_pipeline(tmp_path: Path, graded_inputs, monkeypatch) -> None:
    from sit_eval.grader import costs

    def est(model: str, input_chars: int, output_tokens: int) -> dict[str, Any]:
        return {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.25}

    monkeypatch.setattr(costs, "estimate_call", est)
    judge = _Costly()
    rep = grade_review(*graded_inputs, tmp_path / "o", judge=judge, max_cost_usd=1.0).report
    assert rep["status"] == "complete" and len(judge.calls) == 4 and rep["budget"]["spent_usd"] == 1.0
    judge = _Costly()
    with pytest.raises(BudgetExceeded):
        grade_review(*graded_inputs, tmp_path / "p", judge=judge, max_cost_usd=0.9999)
    assert len(judge.calls) == 3


# ------------------------------------------------------------------- 4. third-sample rule, 3+ samples
def _disagreeing(req: JudgeRequest) -> dict[str, Any]:
    out = heuristic_responder(req)
    if "passB" in req.purpose and req.sample_index == 1:
        out["dimensions"]["D4"]["score"] = 1
    return out


def test_grader_three_samples_never_get_a_fourth(tmp_path: Path, graded_inputs) -> None:
    judge = FakeJudge(_disagreeing)
    rep = grade_review(*graded_inputs, tmp_path / "o", judge=judge, samples=3).report
    assert [c.purpose for c in judge.calls].count("grader:passB") == 3 and len(rep["samples"]) == 3
    assert rep["disagreement"]["third_sample_run"] is False and rep["disagreement"]["max_dim_delta"] == 2
    assert any("disagreed" in r for r in rep["human_review_reasons"])
    judge2 = FakeJudge(_disagreeing)
    rep2 = grade_review(*graded_inputs, tmp_path / "p", judge=judge2).report     # prereg: 2, then a third
    assert len(rep2["samples"]) == 3 and rep2["disagreement"]["third_sample_run"] is True


# -------------------------------------------------- 5. samples split on a verified-false hallucination
def test_grader_split_hallucination_count_needs_human_review(tmp_path: Path, graded_inputs) -> None:
    def responder(req: JudgeRequest) -> dict[str, Any]:
        out = heuristic_responder(req)
        if "passB" in req.purpose and req.sample_index == 0:
            out["hallucinations"] = [{"finding_id": "FND-001", "type": "fabricated_source", "severity": "material",
                                      "status": "verified_false", "review_quote": "the published plan",
                                      "design_quote": None, "reasoning": "No such plan page exists."}]
        return out

    rep = grade_review(*graded_inputs, tmp_path / "o", judge=FakeJudge(responder)).report
    # median count 0.5: no G3 cap on the final score (prereg median rule) ...
    assert rep["material_hallucinations_verified_median"] == 0.5 and rep["caps_applied"] == []
    assert rep["dimensions_final"]["D4"] == 2.5          # ... but sample 1 was capped, so the median moved
    # ... and the merged list shows the flag as verified_false, so a human must look
    assert [h["status"] for h in rep["hallucinations"]] == ["verified_false"]
    assert rep["needs_human_review"] is True
    assert any("disagree on the number of material verified-false" in r for r in rep["human_review_reasons"])


# --------------------------------------------------------------------------- 6. answer key errors
def test_grader_bad_answer_key_is_an_input_error(tmp_path: Path, graded_inputs) -> None:
    review, pages = graded_inputs
    bad = {"k.yaml": "foo: 1\n", "b.yaml": "key_items: [unclosed\n", "j.json": "{not json"}
    for name, text in bad.items():
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        with pytest.raises(pj.GraderInputError):
            load_answer_key(p)
        r = runner.invoke(app, ["grade", "run", str(review), "--pdf", str(pages), "--out", str(tmp_path / "o"),
                                "--answer-key", str(p)])
        assert r.exit_code == 2, (name, r.output)


# ------------------------------------------------------------------------- 7. validate CLI inputs
def test_grader_validate_cli_bad_inputs_exit_2(tmp_path: Path, graded_inputs) -> None:
    review, pages = graded_inputs
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    cases = [
        [str(broken), "--pdf", str(pages), "--dry-run"],
        [str(broken), "--pdf", str(pages), "--out", str(tmp_path / "a"), "--runs", "1"],
        [str(review), "--pdf", str(pages), "--out", str(tmp_path / "b"), "--variant", "V6"],
        [str(review), "--pdf", str(pages), "--out", str(tmp_path / "c"), "--checks", "V6", "--runs", "1"],
    ]
    for args in cases:
        r = runner.invoke(app, ["grade", "validate", *args])
        assert r.exit_code == 2, (args, r.output)
        assert r.exception is None or isinstance(r.exception, SystemExit), (args, r.exception)


# ------------------------------------------------------------------- 8. dry runs never build a judge
def test_grader_dry_runs_never_build_a_judge(graded_inputs, monkeypatch) -> None:
    review, pages = graded_inputs

    def forbidden(*a: Any, **k: Any) -> Any:
        raise AssertionError("a judge was built during a dry run")

    monkeypatch.setattr(grader_cli, "_judge", forbidden)
    monkeypatch.setattr("sit_eval.judge.build_judge", forbidden)
    for cmd in (["run", str(review), "--pdf", str(pages), "--judge", "claude_code", "--dry-run"],
                ["validate", str(review), "--pdf", str(pages), "--judge", "anthropic_api", "--dry-run"]):
        r = runner.invoke(app, ["grade", *cmd])
        assert r.exit_code == 0, (cmd, r.output, r.exception)


# --------------------------------------------------------------------------------- 9. leakage
LEAKS = ["Opus 5.5", "Claude Opus 5.5", "Claude Code", "--no-tools", "no_tools", "great-hopper-hbx7h0",
         "live_cc_opus_payments_v1", "claude-opus-5-5", "claude_code", "B0"]


def _poison_live(review: dict[str, Any]) -> dict[str, Any]:
    """The real live review, with identifying text planted in every agent-written string field kind."""
    r = copy.deepcopy(review)
    r["run_manifest"]["condition"] = "B0"
    plant = " (run with --no-tools, i.e. no_tools, condition B0, by Claude Opus 5.5 via Claude Code on branch " \
            "great-hopper-hbx7h0)"
    r["limitations"][0]["text"] += plant
    r["verdict"]["rationale"] += plant
    r["verdict"]["conditions"][0]["text"] += plant
    r["intent_summary"]["statement"] += plant
    f = r["findings"][0]
    f["title"] += " Opus 5.5"
    f["statement"] += plant
    f["tags"] = ["B0", "no_tools", "payments"]
    f["evidence"][0]["quote"] += plant
    f["doc_anchors"][0]["section_ref"] += " Claude Code"
    f["affected_decisions"][0]["justification"] += plant
    if f.get("recommendation"):
        f["recommendation"]["rationale"] += plant
    r["evidence_ledger"][0]["excerpt"] += plant
    r["decision_registry"][0]["statement"] += plant
    r["sound_areas"][0]["why_sound"] += plant
    r["unresolved"][0]["text"] += plant
    return r


def test_grader_live_review_planted_identity_never_reaches_the_projection() -> None:
    review = json.loads(LIVE_REVIEW.read_text(encoding="utf-8"))
    poisoned = _poison_live(review)
    proj, audit = pj.project_review(poisoned, design_text="")
    text = json.dumps(proj, ensure_ascii=False)
    for s in LEAKS:
        assert s not in text, s
    assert "payments" in proj["findings"][0]["tags"]          # ordinary words survive
    assert audit["strings_scrubbed"] >= 30
    texts = [pj.review_full_text(proj), pj.evidence_register(proj), pj.shuffle_findings(proj, 1)[0]]
    assert pj.leak_report(texts, poisoned) == []
    # the guard sees each planted value if the scrub is bypassed
    raw = json.dumps(poisoned["limitations"][0]["text"])
    assert {"--no-tools", "no_tools", "B0", "Claude Opus 5.5", "Claude Code"} <= set(pj.leak_report([raw], poisoned))


def test_grader_plain_word_stop_detail_is_not_scrubbed(review_dict: dict[str, Any]) -> None:
    r = copy.deepcopy(review_dict)
    r["stop_reason"]["detail"] = "deadline"
    r["findings"][0]["statement"] += " The deadline in NFR-8 is tight."
    proj, _ = pj.project_review(r)
    assert "The deadline in NFR-8 is tight." in proj["findings"][0]["statement"]


# ------------------------------------------------------------------------- 10. grade.md weights
def test_grader_markdown_shows_delta_weights(tmp_path: Path, graded_inputs, review_dict, write_review) -> None:
    v1 = write_review(copy.deepcopy(review_dict), "v1.json")
    res = grade_review(*graded_inputs, tmp_path / "o", judge=FakeJudge(heuristic_responder), v1_review=v1)
    md = render_markdown(res.report)
    assert "| D4 | Evidence quality and traceability | 14.4 |" in md
    assert "| D11 | Re-assessment (delta) | 10 |" in md
