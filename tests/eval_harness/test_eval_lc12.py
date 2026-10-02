"""LC12 in code (SIT FABLE ruling #26, docs/USER_DECISIONS.md): no scored run on an answer key that is not
signed off, unless ``--exploratory`` is given, and then every artefact says so.

Offline: the fake judge only. Every key here is a temporary copy of the payments key with its sign-off state
forced, so the tests hold before and after the owner signs the real keys (eval/KEY_SIGNOFF.md section 4); the
real keys under eval/synthetic are never written.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from eval_builders import LIVE_RUN, PAYMENTS_KEY, default_table, make_finding, make_flaw, make_key, make_review
from eval_builders import run_pipeline as pipeline
from typer.testing import CliRunner

from sit_eval import judge as judge_mod
from sit_eval import lc12
from sit_eval import prereg as prereg_mod
from sit_eval.calls import CACHE_NAME
from sit_eval.cli import app
from sit_eval.scoring import validate_scores

runner = CliRunner()
PDF = PAYMENTS_KEY.parent / "design_v1.pdf"
CONFIRMATORY_LINE = "may not be reported as confirmatory"


def key_copy(tmp: Path, *, signed: bool, name: str | None = None) -> Path:
    """A temporary copy of the payments key with its sign-off state forced (never the real key)."""
    k = json.loads(PAYMENTS_KEY.read_text(encoding="utf-8"))
    if signed:
        k["authoring_status"] = {"pending": [], "scored_run_ready": True}
    else:
        k["authoring_status"] = {"pending": ["core_insight", "key_second_review"], "scored_run_ready": False}
    p = tmp / (name or ("signed_key.json" if signed else "unsigned_key.json"))
    p.write_text(json.dumps(k, indent=1), encoding="utf-8")
    return p


@pytest.fixture
def built(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Every judge client the CLI builds (the fake judge counts its calls in ``.calls``)."""
    clients: list[Any] = []
    real = judge_mod.build_judge

    def counting(kind: str, **kw: Any) -> Any:
        c = real(kind, **kw)
        clients.append(c)
        return c

    monkeypatch.setattr(judge_mod, "build_judge", counting)
    return clients


def score(key: Path, out: Path, *extra: str) -> Any:
    return runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(key), "--doc", str(PDF), "--judge", "fake",
                               "--out", str(out), "--no-grounding-judges", *extra])


def judge_calls(clients: list[Any]) -> int:
    return sum(len(c.calls) for c in clients)


def console_json(output: str) -> dict[str, Any]:
    return json.loads(output[output.index("{"):output.rindex("}") + 1])


# ----------------------------------------------------------------------------- score: refusal


def test_score_refuses_an_unsigned_key_without_the_flag(tmp_path: Path, built: list[Any]):
    key = key_copy(tmp_path, signed=False)
    out = tmp_path / "out"
    res = score(key, out)
    assert res.exit_code == 2, res.output
    msg = " ".join(res.output.split())
    assert "refusing a scored run" in msg and str(key) in msg and "is not signed off" in msg
    assert "scored_run_ready is false (pending: core_insight, key_second_review)" in msg
    assert "--exploratory" in msg and "No judge call was made" in msg and "LC12" in msg
    assert built == [] and judge_calls(built) == 0          # no client built, so no call and no cost
    assert not (out / "scores.json").exists() and not (out / CACHE_NAME).exists()


def test_refusal_comes_before_a_live_judge_is_prepared(tmp_path: Path, built: list[Any]):
    cfg = tmp_path / "eval.yaml"
    cfg.write_text("judge:\n  executable: definitely-not-an-installed-claude-binary\n")
    res = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(key_copy(tmp_path, signed=False)), "--doc",
                              str(PDF), "--judge", "claude_code", "--config", str(cfg), "--out", str(tmp_path / "o")])
    assert res.exit_code == 2 and "is not signed off" in res.output and "not found on PATH" not in res.output
    assert built == []


def test_dry_run_on_an_unsigned_key_plans_and_says_a_real_run_would_refuse(tmp_path: Path, built: list[Any]):
    res = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(key_copy(tmp_path, signed=False)),
                              "--dry-run", "--out", str(tmp_path / "never")])
    assert res.exit_code == 0, res.output
    plan = json.loads(res.output)
    assert plan["lc12"]["scored_run_ready"] is False and plan["lc12"]["exploratory"] is False
    assert "refuses" in plan["lc12"]["note"] and "--exploratory" in plan["lc12"]["note"]
    assert built == [] and not (tmp_path / "never").exists()
    ok = json.loads(runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(key_copy(tmp_path, signed=True)),
                                        "--dry-run"]).output)
    assert ok["lc12"] == {"scored_run_ready": True, "exploratory": False, "note": None}


# ----------------------------------------------------------------------------- score: the override


@pytest.fixture(scope="module")
def exploratory_run(tmp_path_factory) -> tuple[Path, Any]:
    tmp = tmp_path_factory.mktemp("lc12_expl")
    out = tmp / "out"
    res = score(key_copy(tmp, signed=False), out, "--exploratory")
    assert res.exit_code == 0, res.output
    return out, res


def test_exploratory_marks_every_artefact(exploratory_run):
    out, res = exploratory_run
    s = json.loads((out / "scores.json").read_text())
    assert validate_scores(s) == []
    assert s["exploratory"] is True and s["outside_preregistered_analysis"] is False
    assert CONFIRMATORY_LINE in s["exploratory_note"] and s["exploratory_note"].startswith("EXPLORATORY")
    assert any(w.startswith("EXPLORATORY") for w in s["warnings"])
    assert any("scored_run_ready = false" in w and "--exploratory" in w for w in s["warnings"])
    assert s["inputs"]["scored_run_ready"] is False
    md = (out / "scores.md").read_text()
    assert md.splitlines()[2].startswith("**EXPLORATORY**") and CONFIRMATORY_LINE in md.splitlines()[2]
    rows = [json.loads(x) for x in (out / CACHE_NAME).read_text().splitlines()]
    assert rows and all(r["exploratory"] is True for r in rows)
    console = console_json(res.stdout)
    assert console["exploratory"] is True and CONFIRMATORY_LINE in console["exploratory_note"]
    assert "EXPLORATORY" in res.stderr and CONFIRMATORY_LINE in res.stderr


def test_signed_key_scores_normally_with_no_marker(tmp_path: Path, built: list[Any]):
    out = tmp_path / "out"
    res = score(key_copy(tmp_path, signed=True), out)
    assert res.exit_code == 0, res.output
    s = json.loads((out / "scores.json").read_text())
    assert validate_scores(s) == []
    assert s["exploratory"] is False and s["exploratory_note"] is None and s["outside_preregistered_analysis"] is False
    assert s["inputs"]["scored_run_ready"] is True
    assert not any("EXPLORATORY" in w or "scored_run_ready" in w for w in s["warnings"])
    assert "EXPLORATORY" not in (out / "scores.md").read_text()
    assert all(json.loads(x)["exploratory"] is False for x in (out / CACHE_NAME).read_text().splitlines())
    assert console_json(res.stdout)["exploratory"] is False and "EXPLORATORY" not in res.stderr
    assert judge_calls(built) > 0


def test_the_flag_marks_a_run_on_a_signed_key_too(tmp_path: Path):
    res = score(key_copy(tmp_path, signed=True), tmp_path / "out", "--exploratory")
    assert res.exit_code == 0, res.output
    s = json.loads((tmp_path / "out" / "scores.json").read_text())
    assert s["exploratory"] is True and CONFIRMATORY_LINE in s["exploratory_note"]
    assert not any("scored_run_ready = false" in w for w in s["warnings"])


# ----------------------------------------------------------------------------- the result cache


def test_resume_from_an_exploratory_cache_does_not_bypass_the_guard(tmp_path: Path, built: list[Any]):
    out = tmp_path / "out"
    unsigned = key_copy(tmp_path, signed=False)
    assert score(unsigned, out, "--exploratory").exit_code == 0
    before = (out / "scores.json").read_bytes()
    n_built = len(built)
    res = score(unsigned, out)                                  # resume without the flag: still refused
    assert res.exit_code == 2 and "is not signed off" in res.output
    assert len(built) == n_built and (out / "scores.json").read_bytes() == before


def test_an_exploratory_cache_is_never_served_to_a_confirmatory_run(tmp_path: Path, built: list[Any]):
    out = tmp_path / "out"
    assert score(key_copy(tmp_path, signed=False), out, "--exploratory").exit_code == 0
    # control: a second exploratory run into the same --out is served entirely from the cache
    assert score(key_copy(tmp_path, signed=False), out, "--exploratory").exit_code == 0
    s = json.loads((out / "scores.json").read_text())
    assert s["calls"]["calls_live"] == 0 and s["calls"]["calls_cached"] > 0
    # the key is signed (same content otherwise, so the same prompts and request keys): nothing is reused
    n_rows = len((out / CACHE_NAME).read_text().splitlines())
    calls_before = judge_calls(built)
    res = score(key_copy(tmp_path, signed=True), out)
    assert res.exit_code == 0, res.output
    s = json.loads((out / "scores.json").read_text())
    assert s["exploratory"] is False and s["calls"]["calls_cached"] == 0 and s["calls"]["calls_live"] > 0
    assert judge_calls(built) - calls_before == s["calls"]["calls_live"]
    assert any(f"{n_rows} cached judge answers" in w and "not reused" in w for w in s["warnings"])
    # a confirmatory cache row is reused by the next confirmatory run
    assert score(key_copy(tmp_path, signed=True), out).exit_code == 0
    s = json.loads((out / "scores.json").read_text())
    assert s["calls"]["calls_live"] == 0 and s["calls"]["calls_cached"] > 0


def test_a_cache_written_before_the_guard_is_never_served_to_a_confirmatory_run(tmp_path: Path):
    out = tmp_path / "out"
    assert score(key_copy(tmp_path, signed=False), out, "--exploratory").exit_code == 0
    rows = [json.loads(x) for x in (out / CACHE_NAME).read_text().splitlines()]
    for r in rows:      # the pilots' judge_results.jsonl rows carry no marker
        del r["exploratory"]
    (out / CACHE_NAME).write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert score(key_copy(tmp_path, signed=True), out).exit_code == 0
    assert json.loads((out / "scores.json").read_text())["calls"]["calls_cached"] == 0


# ----------------------------------------------------------------------------- the library


def test_score_review_refuses_an_unsigned_key_with_zero_judge_calls(tmp_path: Path):
    key = make_key([make_flaw("F01", "high", "1")])
    assert key["authoring_status"]["scored_run_ready"] is False
    with pytest.raises(lc12.UnsignedKeyRefusal, match="not signed off"):
        pipeline(tmp_path, make_review([make_finding(1, "1")]), key, None, exploratory=False)
    calls: list[Any] = []

    class Counting:
        async def complete(self, request):   # pragma: no cover - must never be reached
            calls.append(request)
            raise AssertionError("judge called")

    with pytest.raises(lc12.UnsignedKeyRefusal):
        pipeline(tmp_path, make_review([make_finding(1, "1")]), key, None, judge=Counting(), exploratory=False)
    assert calls == []


def test_score_review_refuses_a_runner_whose_cache_mode_differs(tmp_path: Path):
    key = make_key([make_flaw("F01", "high", "1")])
    key["authoring_status"] = {"pending": [], "scored_run_ready": True}
    with pytest.raises(ValueError, match="exploratory"):
        pipeline(tmp_path, make_review([make_finding(1, "1")]), key, default_table(), exploratory=False,
                 runner_exploratory=True)


# ----------------------------------------------------------------------------- aggregate


@pytest.fixture(scope="module")
def two_scores(tmp_path_factory, exploratory_run) -> tuple[Path, Path]:
    tmp = tmp_path_factory.mktemp("lc12_conf")
    out = tmp / "out"
    assert score(key_copy(tmp, signed=True), out).exit_code == 0
    return exploratory_run[0] / "scores.json", out / "scores.json"


def aggregate(*args: str) -> Any:
    return runner.invoke(app, ["aggregate", *args, "--bootstrap-b", "100"])


def test_aggregate_refuses_to_mix_exploratory_and_confirmatory(two_scores, tmp_path: Path):
    expl, conf = two_scores
    res = aggregate(str(expl), str(conf), "--out", str(tmp_path / "agg.json"))
    assert res.exit_code == 2
    msg = " ".join(res.output.split())
    assert "refusing" in msg and str(expl) in msg and "--exploratory" in msg and "mix" in msg
    assert not (tmp_path / "agg.json").exists()


def test_aggregate_refuses_a_confirmatory_analysis_of_exploratory_inputs(two_scores):
    expl, _ = two_scores
    res = aggregate(str(expl))
    assert res.exit_code == 2 and "exploratory" in res.output and "--exploratory" in res.output


def test_aggregate_refuses_scores_written_before_the_guard_on_an_unsigned_key(two_scores, tmp_path: Path):
    s = json.loads(two_scores[0].read_text())
    for k in ("exploratory", "exploratory_note", "outside_preregistered_analysis"):
        del s[k]
    old = tmp_path / "pilot_scores.json"
    old.write_text(json.dumps(s))
    res = aggregate(str(old))
    assert res.exit_code == 2 and "predates" in " ".join(res.output.split())


def test_aggregate_with_the_flag_marks_its_output(two_scores, tmp_path: Path):
    expl, conf = two_scores
    res = aggregate(str(expl), str(conf), "--exploratory", "--out", str(tmp_path / "agg.json"))
    assert res.exit_code == 0, res.output
    for agg in (json.loads((tmp_path / "agg.json").read_text()), console_json(res.stdout)):
        assert agg["exploratory"] is True and CONFIRMATORY_LINE in agg["exploratory_note"]
        assert agg["exploratory_inputs"] == [str(expl)]
        assert any("mix exploratory and confirmatory" in w for w in agg["warnings"])
    assert "EXPLORATORY" in res.stderr


def test_aggregate_of_confirmatory_inputs_has_no_marker(two_scores):
    res = aggregate(str(two_scores[1]))
    assert res.exit_code == 0, res.output
    agg = console_json(res.stdout)
    assert agg["exploratory"] is False and agg["exploratory_note"] is None and agg["exploratory_inputs"] == []


# ----------------------------------------------------------------------------- frozen prereg


@pytest.fixture
def frozen_prereg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib

    p = tmp_path / "prereg.yaml"
    p.write_text("frozen: true\nmatcher:\n  prompt_sha256: null\n", encoding="utf-8")
    lock = tmp_path / "prereg.lock"
    lock.write_text(hashlib.sha256(p.read_bytes()).hexdigest() + " deadbeef\n", encoding="utf-8")
    monkeypatch.setattr(prereg_mod, "prereg_path", lambda: p)
    monkeypatch.setattr(prereg_mod, "prereg_lock_path", lambda: lock)


def test_frozen_prereg_exploratory_run_says_it_is_outside_the_preregistered_analysis(tmp_path: Path, frozen_prereg):
    out = tmp_path / "out"
    res = score(key_copy(tmp_path, signed=False), out, "--exploratory")
    assert res.exit_code == 0, res.output
    s = json.loads((out / "scores.json").read_text())
    assert s["prereg"]["frozen"] is True and s["exploratory"] is True and s["outside_preregistered_analysis"] is True
    assert "OUTSIDE THE PRE-REGISTERED ANALYSIS" in s["exploratory_note"]
    assert "OUTSIDE THE PRE-REGISTERED ANALYSIS" in (out / "scores.md").read_text()
    assert "OUTSIDE THE PRE-REGISTERED ANALYSIS" in res.stderr
    assert console_json(res.stdout)["outside_preregistered_analysis"] is True
    # without the flag a frozen prereg still refuses the unsigned key
    assert score(key_copy(tmp_path, signed=False), tmp_path / "o2").exit_code == 2
    agg = aggregate(str(out / "scores.json"), "--exploratory")
    assert agg.exit_code == 0 and "OUTSIDE THE PRE-REGISTERED ANALYSIS" in console_json(agg.stdout)["exploratory_note"]


def test_frozen_prereg_signed_key_is_a_confirmatory_run(tmp_path: Path, frozen_prereg):
    out = tmp_path / "out"
    res = score(key_copy(tmp_path, signed=True), out)
    assert res.exit_code == 0, res.output
    s = json.loads((out / "scores.json").read_text())
    assert s["prereg"]["frozen"] is True and s["exploratory"] is False
    assert "OUTSIDE" not in res.output and "OUTSIDE" not in (out / "scores.md").read_text()


# ----------------------------------------------------------------------------- live judges' call log


def test_live_judges_log_the_run_mode_in_every_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from sit_eval.live_judges import AnthropicJudge, CallLog, ClaudeCodeJudge

    log = CallLog(tmp_path, tags={"exploratory": True})
    log.write({"purpose": "x"})
    assert json.loads((tmp_path / log.path.name).read_text())["exploratory"] is True
    for cls in (ClaudeCodeJudge, AnthropicJudge):
        assert cls(out_dir=tmp_path / cls.__name__, log_tags={"exploratory": False}).log.tags == {"exploratory": False}

    seen: list[dict[str, Any]] = []

    class Stop(Exception):
        pass

    def capture(kind: str, **kw: Any) -> Any:
        seen.append(kw)
        raise Stop

    monkeypatch.setattr(judge_mod, "build_judge", capture)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    for flag, signed in ((["--exploratory"], False), ([], True)):
        res = runner.invoke(app, ["score", str(LIVE_RUN), "--key", str(key_copy(tmp_path, signed=signed)), "--doc",
                                  str(PDF), "--judge", "anthropic_api", "--out", str(tmp_path / "o"), *flag])
        assert isinstance(res.exception, Stop)
        assert seen[-1]["log_tags"] == {"exploratory": bool(flag)}
