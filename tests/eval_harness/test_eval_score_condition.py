"""``sit-eval score --condition`` must agree with the run manifest's ``condition`` or refuse.

``sit-eval aggregate`` pairs runs by ``inputs.condition``, so a ``--condition`` that contradicts the run's own
manifest would misfile the row into the wrong arm of the comparison. The rule: a flag that differs from a
recorded condition is refused before any judge is built and before ``--out`` is created; a run whose manifest
records no condition (runs made before the B0 condition existed) takes the flag as given; without the flag the
manifest's condition is used, as before, unless ``manifest.json`` and the report's ``run_manifest`` record two
different non-null conditions, which is refused the same way.

Offline: the fake judge only, on temporary copies of the live payments run's report.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from eval_builders import LIVE_RUN, PAYMENTS_KEY
from typer.testing import CliRunner

from sit_eval import judge as judge_mod
from sit_eval.cli import app
from sit_eval.scoring import ConditionMismatch, check_condition, validate_scores

runner = CliRunner()
PDF = PAYMENTS_KEY.parent / "design_v1.pdf"


@pytest.fixture
def built(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Every judge client the CLI builds."""
    clients: list[Any] = []
    real = judge_mod.build_judge

    def counting(kind: str, **kw: Any) -> Any:
        c = real(kind, **kw)
        clients.append(c)
        return c

    monkeypatch.setattr(judge_mod, "build_judge", counting)
    return clients


def signed_key(tmp: Path) -> Path:
    k = json.loads(PAYMENTS_KEY.read_text(encoding="utf-8"))
    k["authoring_status"] = {"pending": [], "scored_run_ready": True}
    p = tmp / "signed_key.json"
    p.write_text(json.dumps(k, indent=1), encoding="utf-8")
    return p


_SAME = object()


def run_with(tmp: Path, condition: str | None, *, manifest_file: bool = True, drop_field: bool = False,
             file_condition: Any = _SAME) -> Path:
    """A run folder holding a copy of the live report whose manifest records ``condition``, with a
    ``manifest.json`` beside it unless ``manifest_file`` is false (lacking the field when ``drop_field``,
    recording ``file_condition`` instead of ``condition`` when given)."""
    d = tmp / "run"
    d.mkdir()
    shutil.copy(LIVE_RUN / "report.json", d / "report.json")
    report = json.loads((d / "report.json").read_text(encoding="utf-8"))
    rm = report["run_manifest"]
    rm["condition"] = condition   # the Review schema requires the field in the report (null allowed)
    (d / "report.json").write_text(json.dumps(report), encoding="utf-8")
    if manifest_file:
        m = dict(rm)
        if file_condition is not _SAME:
            m["condition"] = file_condition
        if drop_field:   # an older manifest.json may lack the field altogether
            m.pop("condition")
        (d / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    return d


def score(run: Path, key: Path, out: Path, *extra: str) -> Any:
    return runner.invoke(app, ["score", str(run), "--key", str(key), "--doc", str(PDF), "--judge", "fake",
                               "--out", str(out), "--no-grounding-judges", *extra])


# ----------------------------------------------------------------------------- refusal


def test_score_refuses_a_condition_that_contradicts_the_manifest(tmp_path: Path, built: list[Any]):
    out = tmp_path / "out"
    res = score(run_with(tmp_path, "B0"), signed_key(tmp_path), out, "--condition", "FULL")
    assert res.exit_code != 0
    assert "--condition FULL" in res.output and "B0" in res.output
    assert not out.exists()
    assert built == []


def test_score_refuses_a_contradiction_recorded_only_in_the_report(tmp_path: Path, built: list[Any]):
    out = tmp_path / "out"
    res = score(run_with(tmp_path, "FULL", manifest_file=False), signed_key(tmp_path), out, "--condition", "B0")
    assert res.exit_code != 0
    assert "--condition B0" in res.output and "FULL" in res.output
    assert not out.exists() and built == []


def test_dry_run_refuses_a_contradicting_condition_too(tmp_path: Path, built: list[Any]):
    res = runner.invoke(app, ["score", str(run_with(tmp_path, "B0")), "--key", str(signed_key(tmp_path)),
                              "--doc", str(PDF), "--condition", "FULL", "--dry-run"])
    assert res.exit_code != 0 and "B0" in res.output
    assert "{" not in res.stdout   # no call plan printed


def test_check_condition_unit():
    with pytest.raises(ConditionMismatch, match="B0"):
        check_condition("FULL", {"condition": "B0"}, {"condition": "B0"})
    with pytest.raises(ConditionMismatch):
        check_condition("FULL", None, {"condition": "B0"})
    check_condition("FULL", {"condition": "FULL"}, {"condition": "FULL"})
    check_condition("B0", {"condition": None}, {})
    check_condition("B0", None, None)
    check_condition(None, {"condition": "B0"}, {"condition": "B0"})
    with pytest.raises(ConditionMismatch, match="manifest.json condition FULL.*run_manifest condition B0"):
        check_condition(None, {"condition": "FULL"}, {"condition": "B0"})
    check_condition(None, {"condition": None}, {"condition": "B0"})
    check_condition(None, {"condition": "FULL"}, {"condition": None})
    check_condition(None, None, {"condition": "B0"})


def test_score_without_the_flag_refuses_disagreeing_recorded_conditions(tmp_path: Path, built: list[Any]):
    out = tmp_path / "out"
    res = score(run_with(tmp_path, "B0", file_condition="FULL"), signed_key(tmp_path), out)
    assert res.exit_code == 2, res.output
    assert "manifest.json condition FULL" in res.output and "run_manifest condition B0" in res.output
    assert not out.exists() and built == []


# ----------------------------------------------------------------------------- acceptance


def test_score_accepts_a_condition_that_matches_the_manifest(tmp_path: Path, built: list[Any]):
    out = tmp_path / "out"
    res = score(run_with(tmp_path, "B0"), signed_key(tmp_path), out, "--condition", "B0")
    assert res.exit_code == 0, res.output
    s = json.loads((out / "scores.json").read_text(encoding="utf-8"))
    assert validate_scores(s) == [] and s["inputs"]["condition"] == "B0"
    assert len(built) == 1


@pytest.mark.parametrize("drop_field", [False, True], ids=["null", "absent"])
def test_score_accepts_the_flag_when_the_manifest_records_no_condition(tmp_path: Path, built: list[Any],
                                                                       drop_field: bool):
    out = tmp_path / "out"
    res = score(run_with(tmp_path, None, drop_field=drop_field), signed_key(tmp_path), out, "--condition", "FULL")
    assert res.exit_code == 0, res.output
    s = json.loads((out / "scores.json").read_text(encoding="utf-8"))
    assert s["inputs"]["condition"] == "FULL"


def test_score_without_the_flag_reads_the_manifest_condition(tmp_path: Path, built: list[Any]):
    out = tmp_path / "out"
    res = score(run_with(tmp_path, "B0"), signed_key(tmp_path), out)
    assert res.exit_code == 0, res.output
    assert json.loads((out / "scores.json").read_text(encoding="utf-8"))["inputs"]["condition"] == "B0"


@pytest.mark.parametrize(("report_cond", "file_cond"), [("B0", None), (None, "FULL")],
                         ids=["manifest-json-null", "report-null"])
def test_score_without_the_flag_accepts_one_recorded_condition_null(tmp_path: Path, built: list[Any],
                                                                    report_cond: str | None, file_cond: str | None):
    out = tmp_path / "out"
    res = score(run_with(tmp_path, report_cond, file_condition=file_cond), signed_key(tmp_path), out)
    assert res.exit_code == 0, res.output
    assert validate_scores(json.loads((out / "scores.json").read_text(encoding="utf-8"))) == []
    assert len(built) == 1
