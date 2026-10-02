"""LC12 for the grader (SIT FABLE ruling #26): the key-aware diagnostic of ``sit-eval grade run --answer-key``
reads an answer key, so it refuses a key that is not signed off unless ``--exploratory`` is given; the
key-blind grade is not affected. Offline: FakeJudge only; keys are temporary copies with a forced state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from sit_eval import lc12
from sit_eval import prereg as prereg_mod
from sit_eval.cli import app
from sit_eval.grader import fake as fake_mod
from sit_eval.grader.pipeline import grade_review

REPO = Path(__file__).resolve().parents[2]
PAYMENTS_KEY = REPO / "eval" / "synthetic" / "payments_orchestration" / "answer_key.canonical.json"
CONFIRMATORY_LINE = "may not be reported as confirmatory"
runner = CliRunner()


def key_copy(tmp: Path, *, signed: bool) -> Path:
    k = json.loads(PAYMENTS_KEY.read_text(encoding="utf-8"))
    k["authoring_status"] = ({"pending": [], "scored_run_ready": True} if signed else
                             {"pending": ["core_insight"], "scored_run_ready": False})
    p = tmp / ("signed.json" if signed else "unsigned.json")
    p.write_text(json.dumps(k), encoding="utf-8")
    return p


def legacy_key(tmp: Path) -> Path:
    p = tmp / "legacy.yaml"
    p.write_text(yaml.safe_dump({"artefact": "A", "key_items": [{"id": "K1", "title": "t", "locations": ["1"],
                                                                 "category": "c", "materiality": "high"}]}))
    return p


@pytest.fixture
def built(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    clients: list[Any] = []
    real = fake_mod.heuristic_fake_judge

    def counting() -> Any:
        c = real()
        clients.append(c)
        return c

    monkeypatch.setattr(fake_mod, "heuristic_fake_judge", counting)
    return clients


def grade(review: Path, pages: Path, out: Path, *extra: str) -> Any:
    return runner.invoke(app, ["grade", "run", str(review), "--pdf", str(pages), "--out", str(out), "--judge", "fake",
                               *extra])


def test_key_aware_grade_refuses_an_unsigned_key(tmp_path: Path, graded_inputs, built: list[Any]) -> None:
    key = key_copy(tmp_path, signed=False)
    out = tmp_path / "out"
    r = grade(*graded_inputs, out, "--answer-key", str(key))
    assert r.exit_code == 2, r.output
    msg = " ".join(r.output.split())
    assert str(key) in msg and "is not signed off" in msg and "scored_run_ready is false (pending: core_insight)" in msg
    assert "--exploratory" in msg and "--answer-key" in msg and "No judge call was made" in msg
    assert built == [] and not (out / "grade.json").exists()


def test_a_legacy_key_carries_no_signoff_and_is_refused(tmp_path: Path, graded_inputs, built: list[Any]) -> None:
    r = grade(*graded_inputs, tmp_path / "out", "--answer-key", str(legacy_key(tmp_path)))
    assert r.exit_code == 2 and "legacy grader key format carries no sign-off" in " ".join(r.output.split())
    assert built == []


def test_key_aware_grade_with_the_flag_marks_every_artefact(tmp_path: Path, graded_inputs, built) -> None:
    out = tmp_path / "out"
    r = grade(*graded_inputs, out, "--answer-key", str(key_copy(tmp_path, signed=False)), "--exploratory")
    assert r.exit_code == 0, r.output
    rep = json.loads((out / "grade.json").read_text())
    assert rep["exploratory"] is True and CONFIRMATORY_LINE in rep["exploratory_note"]
    assert rep["outside_preregistered_analysis"] is False
    assert rep["key_alignment_diagnostic"]["exploratory"] is True and rep["key_alignment_diagnostic"]["counts_median"]
    assert rep["key_alignment_diagnostic"]["scored_run_ready"] is False
    md = (out / "grade.md").read_text()
    assert "**EXPLORATORY**" in md and CONFIRMATORY_LINE in md
    assert "EXPLORATORY" in r.stdout and CONFIRMATORY_LINE in r.stdout
    assert sum(len(c.calls) for c in built) > 0


def test_key_aware_grade_on_a_signed_key_has_no_marker(tmp_path: Path, graded_inputs) -> None:
    out = tmp_path / "out"
    r = grade(*graded_inputs, out, "--answer-key", str(key_copy(tmp_path, signed=True)))
    assert r.exit_code == 0, r.output
    rep = json.loads((out / "grade.json").read_text())
    assert rep["exploratory"] is False and rep["exploratory_note"] is None
    assert rep["key_alignment_diagnostic"]["exploratory"] is False
    assert rep["key_alignment_diagnostic"]["scored_run_ready"] is True
    assert "EXPLORATORY" not in (out / "grade.md").read_text() and "EXPLORATORY" not in r.output


def test_key_blind_grade_is_not_affected(tmp_path: Path, graded_inputs) -> None:
    out = tmp_path / "out"
    r = grade(*graded_inputs, out)
    assert r.exit_code == 0, r.output
    rep = json.loads((out / "grade.json").read_text())
    assert rep["exploratory"] is False and rep["key_alignment_diagnostic"] is None


def test_dry_run_with_an_unsigned_key_warns_and_calls_nothing(tmp_path: Path, graded_inputs, built) -> None:
    review, pages = graded_inputs
    r = runner.invoke(app, ["grade", "run", str(review), "--pdf", str(pages), "--judge", "claude_code", "--dry-run",
                            "--answer-key", str(key_copy(tmp_path, signed=False))])
    assert r.exit_code == 0, r.output
    assert "DRY RUN" in r.output and "a real run refuses" in r.output and "--exploratory" in r.output
    assert built == []


def test_grade_review_refuses_an_unsigned_key_with_zero_calls(tmp_path: Path, graded_inputs, heuristic_judge) -> None:
    with pytest.raises(lc12.UnsignedKeyRefusal, match="not signed off"):
        grade_review(*graded_inputs, tmp_path / "o", judge=heuristic_judge, answer_key=key_copy(tmp_path, signed=False))
    assert heuristic_judge.calls == [] and not (tmp_path / "o" / "grade.json").exists()


def test_frozen_prereg_exploratory_grade_is_outside_the_preregistered_analysis(
        tmp_path: Path, graded_inputs, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib

    p = tmp_path / "prereg.yaml"
    p.write_text("frozen: true\n", encoding="utf-8")
    lock = tmp_path / "prereg.lock"
    lock.write_text(hashlib.sha256(p.read_bytes()).hexdigest() + "\n", encoding="utf-8")
    monkeypatch.setattr(prereg_mod, "prereg_path", lambda: p)
    monkeypatch.setattr(prereg_mod, "prereg_lock_path", lambda: lock)
    out = tmp_path / "out"
    r = grade(*graded_inputs, out, "--answer-key", str(key_copy(tmp_path, signed=False)), "--exploratory")
    assert r.exit_code == 0, r.output
    rep = json.loads((out / "grade.json").read_text())
    assert rep["outside_preregistered_analysis"] is True
    assert "OUTSIDE THE PRE-REGISTERED ANALYSIS" in rep["exploratory_note"]
    assert "OUTSIDE THE PRE-REGISTERED ANALYSIS" in (out / "grade.md").read_text()
    assert "OUTSIDE THE PRE-REGISTERED ANALYSIS" in r.stdout
