"""``dra review <pdf> --k N`` (stability runs; metrics.md §7.2, REPRODUCIBILITY §9) and
``--profile NAME`` (config overlay recorded in the manifest and reused by ``resume``). Also checks
that ``dra --help`` lists every command of the runbook's CLI table (§9)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import sit_review_agent.progress  # noqa: F401 - bind ConsoleProgress's default stream before CliRunner swaps it
from sit_review_agent.cli import app
from sit_review_agent.paths import config_dir
from sit_review_agent.selftest import FIXTURE_DIR
from sit_review_agent.states import PhaseName

PDF = FIXTURE_DIR / "design.pages.txt"
CASSETTES = FIXTURE_DIR / "cassettes"


@pytest.fixture
def cfgdir(tmp_path: Path) -> Path:
    dst = tmp_path / "config"
    shutil.copytree(config_dir(), dst)
    agent = dst / "agent.yaml"
    agent.write_text(agent.read_text(encoding="utf-8").replace("run_root: runs", f"run_root: {tmp_path / 'runs'}"),
                     encoding="utf-8")
    (dst / "profiles").mkdir(exist_ok=True)
    (dst / "profiles" / "t.yaml").write_text("stop_rules:\n  deadline_seconds: 321\n", encoding="utf-8")
    return dst


def invoke(args: list[str]) -> Any:
    res = CliRunner().invoke(app, args)
    assert "Traceback" not in res.output, res.output
    return res


def base(cfgdir: Path) -> list[str]:
    return ["--config", str(cfgdir), "--transport", "fake", "--replay", str(CASSETTES),
            "--disable-tool", "mcp-research-information"]


def _patch_phase(monkeypatch: pytest.MonkeyPatch, phase: PhaseName, exc: type[BaseException],
                 *, only_first: bool = False) -> None:
    import sit_review_agent.phases as phases_mod

    real = phases_mod.default_phases
    calls = {"n": 0}

    class Boom:
        def __init__(self, inner: Any) -> None:
            self.inner, self.name = inner, inner.name

        async def run(self, ctx: Any) -> Any:
            calls["n"] += 1
            if only_first and calls["n"] > 1:
                return await self.inner.run(ctx)
            raise exc("planted")

    def patched() -> Any:
        out = real()
        out[phase] = Boom(out[phase])
        return out

    monkeypatch.setattr(phases_mod, "default_phases", patched)


def test_k_runs_are_independent_runs_with_a_group_manifest(cfgdir: Path) -> None:
    res = invoke(["review", str(PDF), *base(cfgdir), "--k", "3", "--run-id", "grp"])
    assert res.exit_code == 0, res.output
    runs = cfgdir.parent / "runs"
    dirs = [runs / f"grp-k{i}" for i in (1, 2, 3)]
    assert all((d / "report.json").is_file() for d in dirs)
    group = json.loads((runs / "grp.kgroup.json").read_text(encoding="utf-8"))
    assert group["k"] == 3 and group["group_id"] == "grp" and group["input_sha256"]
    assert [r["run_dir"] for r in group["runs"]] == [str(d) for d in dirs]
    assert all(r["status"] == "completed" and r["exit_code"] == 0 for r in group["runs"])
    assert group["summary"]["completed"] == 3 and group["summary"]["verdict_agreement"] == 1.0
    for i, d in enumerate(dirs, start=1):
        man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        assert man["extra"]["k_index"] == i and man["run_id"] == f"grp-k{i}"
        assert json.loads((d / "k_group.json").read_text(encoding="utf-8"))["group_id"] == "grp"
    # fresh, independent runs: separate journals, same config
    ids = {json.loads((d / "manifest.json").read_text())["config_sha256"] for d in dirs}
    assert len(ids) == 1
    out = res.output
    assert "k-run group grp: 3 run(s)" in out and "grp-k3" in out and "verdict agreement 1.00" in out
    assert "group manifest:" in out


def test_k_without_run_id_gets_a_generated_group(cfgdir: Path) -> None:
    res = invoke(["run", str(PDF), *base(cfgdir), "--k", "1"])
    assert res.exit_code == 0, res.output
    groups = list((cfgdir.parent / "runs").glob("*.kgroup.json"))
    assert len(groups) == 1
    gid = groups[0].name.removesuffix(".kgroup.json")
    assert (cfgdir.parent / "runs" / f"{gid}-k1" / "report.json").is_file()


def test_k_failed_runs_are_counted_not_replaced(cfgdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_phase(monkeypatch, PhaseName.REFINE, RuntimeError, only_first=True)
    res = invoke(["review", str(PDF), *base(cfgdir), "--k", "2", "--run-id", "itt"])
    assert res.exit_code == 4, res.output                                  # first failure's code
    group = json.loads((cfgdir.parent / "runs" / "itt.kgroup.json").read_text(encoding="utf-8"))
    assert [r["status"] for r in group["runs"]] == ["failed", "completed"]  # no rerun, k not extended
    assert group["runs"][0]["exit_code"] == 4 and group["runs"][0]["error"]
    assert group["summary"]["failed"] == 1 and group["stopped_early"] is None


def test_k_stops_on_ctrl_c(cfgdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_phase(monkeypatch, PhaseName.REFINE, KeyboardInterrupt)
    res = invoke(["review", str(PDF), *base(cfgdir), "--k", "3", "--run-id", "int"])
    assert res.exit_code == 130, res.output
    group = json.loads((cfgdir.parent / "runs" / "int.kgroup.json").read_text(encoding="utf-8"))
    assert [r["status"] for r in group["runs"]] == ["failed", "not started", "not started"]
    assert group["stopped_early"].startswith("interrupted")


def test_k_usage_errors(cfgdir: Path, tmp_path: Path) -> None:
    assert invoke(["review", str(PDF), *base(cfgdir), "--k", "0"]).exit_code == 2
    assert invoke(["review", str(PDF), *base(cfgdir), "--k", "2", "--plan-only"]).exit_code == 2
    assert invoke(["review", "--resume", str(tmp_path), "--k", "2", "--config", str(cfgdir)]).exit_code == 2
    stop = cfgdir / "stop_rules.yaml"                                       # a config error: nothing runs
    stop.write_text(stop.read_text(encoding="utf-8").replace("deadline]", "deadline, no_such_rule]"),
                    encoding="utf-8")
    res = invoke(["review", str(PDF), *base(cfgdir), "--k", "2", "--run-id", "bad"])
    assert res.exit_code == 2 and "no_such_rule" in res.output
    assert not (cfgdir.parent / "runs" / "bad-k2").exists()


def test_profile_is_recorded_and_reused_by_resume(cfgdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_phase(monkeypatch, PhaseName.VERIFY, KeyboardInterrupt)
    res = invoke(["review", str(PDF), *base(cfgdir), "--profile", "t", "--run-id", "prof"])
    assert res.exit_code == 130, res.output
    monkeypatch.undo()
    rd = cfgdir.parent / "runs" / "prof"
    eff = json.loads((rd / "effective_config.json").read_text(encoding="utf-8"))
    assert eff["cli_args"]["profile"] == "t" and eff["stop_rules"]["deadline_seconds"] == 321
    res = invoke(["resume", str(rd)])                                       # no drift: profile reapplied
    assert res.exit_code == 0, res.output
    man = json.loads((rd / "manifest.json").read_text(encoding="utf-8"))
    assert man["extra"]["config"]["cli_args"]["profile"] == "t"
    assert man["budgets"]["deadline_s"] == 321
    assert not any(d.startswith("--accept-drift") for d in man["extra"]["deviations"])


def test_demo_profile_and_a_deadline_that_does_not_fit_the_reserves(cfgdir: Path) -> None:
    """`--profile demo` (the real config/profiles/demo.yaml) with `--k`, and the warning a run prints
    when `--deadline` is shorter than the reserves it runs with (W1 deadline policy x W2 flags)."""
    res = invoke(["review", str(PDF), *base(cfgdir), "--profile", "demo", "--k", "2", "--run-id", "demo"])
    assert res.exit_code == 0, res.output
    assert "leaves research no time" not in res.output and "no model call can run" not in res.output
    runs = cfgdir.parent / "runs"
    for i in (1, 2):
        eff = json.loads((runs / f"demo-k{i}" / "effective_config.json").read_text(encoding="utf-8"))
        sr = eff["stop_rules"]
        assert (sr["deadline_seconds"], sr["report_reserve_seconds"], sr["assess_reserve_seconds"]) == (540, 120, 200)
        assert eff["agent"]["effort"]["assess"] == "medium" and eff["agent"]["effort"]["research"] == "low"
        man = json.loads((runs / f"demo-k{i}" / "manifest.json").read_text(encoding="utf-8"))
        assert man["budgets"]["deadline_s"] == 540 and man["extra"]["config"]["cli_args"]["profile"] == "demo"
        assert man["extra"]["k_index"] == i
    # the runbook's "short rerun" against the default reserves (180 s + 600 s): announced, not silent
    res = invoke(["review", str(PDF), *base(cfgdir), "--deadline", "300", "--run-id", "short"])
    assert res.exit_code == 0, res.output
    assert "WARN deadline 300 s leaves research no time" in res.output and "share 120 s" in res.output
    res = invoke(["review", str(PDF), *base(cfgdir), "--profile", "demo", "--deadline", "300", "--run-id", "short2"])
    assert res.exit_code == 0, res.output
    assert "WARN deadline 300 s leaves research no time" in res.output and "share 180 s" in res.output


def test_profile_errors_exit_2(cfgdir: Path) -> None:
    res = invoke(["review", str(PDF), *base(cfgdir), "--profile", "nope"])
    assert res.exit_code == 2 and "nope" in res.output
    res = invoke(["preflight", "--config", str(cfgdir), "--profile", "nope"])
    assert res.exit_code == 2 and "nope" in res.output


def test_help_lists_every_runbook_command() -> None:
    res = invoke(["--help"])
    assert res.exit_code == 0
    for cmd in ("preflight", "review", "explain", "coverage", "resume", "replay"):
        assert f" {cmd} " in res.output, cmd
    review = invoke(["review", "--help"]).output
    for flag in ("--deadline", "--previous", "--plan-only", "--max-tool-calls", "--disable-tool", "--no-tools",
                 "--transport", "--faults", "--allow-fallback", "--k", "--profile"):
        assert flag in review, flag
    pre = invoke(["preflight", "--help"]).output
    assert "--no-warm" in pre and "--keep-warm" in pre and "--profile" in pre
    assert "--run" in invoke(["explain", "--help"]).output
    assert "--run" in invoke(["coverage", "--help"]).output
