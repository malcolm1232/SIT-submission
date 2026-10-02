"""``sit-review selftest`` end to end and CLI smoke tests (workstream C, "phase 3").

Covers what tests/test_pending.py's ``test_selftest_end_to_end`` describes, plus the CLI surface
the runbook uses: ``run`` / ``review`` with the §4.2 override flags, ``explain`` (both argument
forms), ``resume`` and ``run --resume`` with drift refusal (exit 5) and ``--accept-drift``,
``--plan-only``, ``--no-tools``, exit codes per ``errors.ExitCode``, and no traceback (INV-11).
These runs use the real phases with ``transport: fake`` (the selftest fixture script) and the
fixture cassettes; nothing touches the network.
"""

from __future__ import annotations

import json
import shutil
import time
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from sit_review_agent.cli import app
from sit_review_agent.invariants import check_all
from sit_review_agent.paths import config_dir
from sit_review_agent.selftest import FIXTURE_DIR, run_selftest

PDF = FIXTURE_DIR / "design.pages.txt"
CASSETTES = FIXTURE_DIR / "cassettes"


async def test_selftest_end_to_end() -> None:
    t0 = time.monotonic()
    results = await run_selftest()
    elapsed = time.monotonic() - t0
    failed = {r.inv_id: r.problems for r in results if not r.passed}
    assert failed == {}
    ids = [r.inv_id for r in results]
    assert ids[:8] == [f"INV-{n:02d}" for n in range(3, 11)]
    assert {"selftest:schema", "selftest:explain", "selftest:resume", "selftest:anchor_repair"} <= set(ids)
    assert elapsed < 20


@pytest.fixture
def cfgdir(tmp_path: Path) -> Path:
    """A copy of config/ whose runs go under tmp_path (the repo's runs/ is never written)."""
    dst = tmp_path / "config"
    shutil.copytree(config_dir(), dst)
    agent = dst / "agent.yaml"
    text = agent.read_text(encoding="utf-8").replace("run_root: runs", f"run_root: {tmp_path / 'runs'}")
    agent.write_text(text, encoding="utf-8")
    return dst


def base_args(cfgdir: Path, run_id: str) -> list[str]:
    return ["--config", str(cfgdir), "--transport", "fake", "--replay", str(CASSETTES),
            "--disable-tool", "mcp-research-information", "--run-id", run_id]


def invoke(args: list[str]) -> Any:
    res = CliRunner().invoke(app, args)
    assert "Traceback" not in res.output, res.output
    return res


def test_cli_run_explain_and_resume_a_finished_run(cfgdir: Path, tmp_path: Path) -> None:
    res = invoke(["run", str(PDF), *base_args(cfgdir, "cli-1")])
    assert res.exit_code == 0, res.output
    rd = tmp_path / "runs" / "cli-1"
    assert str(rd / "report.md") in res.output
    report = json.loads((rd / "report.json").read_text(encoding="utf-8"))
    assert [r.inv_id for r in check_all(report, rd) if not r.passed] == []
    assert report["run_manifest"]["extra"]["config"]["cli_args"]["transport"] == "fake"
    fid = report["findings"][0]["id"]
    res = invoke(["explain", str(rd), fid])
    assert res.exit_code == 0 and "Document anchors" in res.output
    res = invoke(["explain", fid, "--run", str(rd)])
    assert res.exit_code == 0 and fid in res.output
    assert invoke(["explain", str(rd), "FND-999"]).exit_code == 2
    assert invoke(["explain", str(tmp_path / "nope"), "FND-001"]).exit_code == 2
    assert invoke(["run", "--resume", str(rd)]).exit_code == 0              # already complete: nothing to do
    res = invoke(["review", str(PDF), *base_args(cfgdir, "cli-alias")])     # runbook alias
    assert res.exit_code == 0, res.output


def test_dra_alias_entry_point() -> None:
    scripts = {e.name: e.value for e in entry_points(group="console_scripts")}
    assert scripts.get("dra") == scripts.get("sit-review") == "sit_review_agent.cli:main"


def test_cli_usage_errors_exit_2(cfgdir: Path, tmp_path: Path) -> None:
    assert invoke(["run", "--config", str(cfgdir)]).exit_code == 2                       # no input
    assert invoke(["run", str(tmp_path / "missing.pdf"), "--config", str(cfgdir)]).exit_code == 2
    assert invoke(["run", str(PDF), "--record", "--replay", str(CASSETTES)]).exit_code == 2
    assert invoke(["run", str(PDF), "--disable-tool", "no-such-server", "--config", str(cfgdir)]).exit_code == 2
    assert invoke(["run", str(PDF), "--mode", "party", "--config", str(cfgdir)]).exit_code == 2
    assert invoke(["run", str(PDF), "--accept-drift", "--config", str(cfgdir)]).exit_code == 2
    stop = cfgdir / "stop_rules.yaml"
    stop.write_text(stop.read_text(encoding="utf-8").replace("deadline]", "deadline, no_such_rule]"), encoding="utf-8")
    res = invoke(["run", str(PDF), *base_args(cfgdir, "bad-rule")])
    assert res.exit_code == 2 and "no_such_rule" in res.output


class _Interrupt:
    def __init__(self, name: Any) -> None:
        self.name = name

    async def run(self, ctx: Any) -> Any:
        raise KeyboardInterrupt


class _Crash(_Interrupt):
    async def run(self, ctx: Any) -> Any:
        raise RuntimeError("planted bug")


def _patch_phase(monkeypatch: pytest.MonkeyPatch, phase: str, cls: type) -> None:
    import sit_review_agent.phases as phases_mod
    from sit_review_agent.states import PhaseName

    real = phases_mod.default_phases

    def patched() -> Any:
        out = real()
        out[PhaseName(phase)] = cls(PhaseName(phase))
        return out

    monkeypatch.setattr(phases_mod, "default_phases", patched)


def test_cli_interrupt_resume_drift_and_accept(cfgdir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_phase(monkeypatch, "refine", _Interrupt)
    res = invoke(["run", str(PDF), *base_args(cfgdir, "cli-int")])
    assert res.exit_code == 130, res.output
    monkeypatch.undo()
    rd = tmp_path / "runs" / "cli-int"
    res = invoke(["run", "--resume", str(rd), "--deadline", "300"])        # a changed flag = config drift
    assert res.exit_code == 5 and "resume refused" in res.output
    res = invoke(["run", "--resume", str(rd), "--deadline", "300", "--accept-drift"])
    assert res.exit_code == 0, res.output
    devs = json.loads((rd / "manifest.json").read_text(encoding="utf-8"))["extra"]["deviations"]
    assert any(d.startswith("--accept-drift: effective_config") for d in devs)


def test_cli_resume_command_uses_the_runs_recorded_flags(cfgdir: Path, tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_phase(monkeypatch, "verify", _Interrupt)
    assert invoke(["run", str(PDF), *base_args(cfgdir, "cli-res")]).exit_code == 130
    monkeypatch.undo()
    res = invoke(["resume", str(tmp_path / "runs" / "cli-res")])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "runs" / "cli-res" / "report.md").is_file()


def test_cli_stage_crash_exit_4_without_traceback(cfgdir: Path, tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_phase(monkeypatch, "assess", _Crash)
    res = invoke(["run", str(PDF), *base_args(cfgdir, "cli-crash")])
    assert res.exit_code == 4
    failure = json.loads((tmp_path / "runs" / "cli-crash" / "failure.json").read_text(encoding="utf-8"))
    assert failure["phase"] == "assess" and "planted bug" in failure["cause"]


def test_cli_internal_error_is_one_line(cfgdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sit_review_agent.orchestrator as orch

    async def broken(*a: Any, **k: Any) -> Any:
        raise ValueError("unexpected")

    monkeypatch.setattr(orch, "run_review", broken)
    res = invoke(["run", str(PDF), *base_args(cfgdir, "cli-broken")])
    assert res.exit_code == 4 and "internal error" in res.output


def test_cli_plan_only_and_no_tools(cfgdir: Path, tmp_path: Path) -> None:
    res = invoke(["run", str(PDF), *base_args(cfgdir, "cli-plan"), "--plan-only"])
    assert res.exit_code == 0 and "Research plan" in res.output
    rd = tmp_path / "runs" / "cli-plan"
    assert not (rd / "report.json").exists() and not (rd / "tools.jsonl").exists()
    res = invoke(["run", str(PDF), *base_args(cfgdir, "cli-doc-only"), "--no-tools"])
    assert res.exit_code == 0, res.output
    rd = tmp_path / "runs" / "cli-doc-only"
    md = (rd / "report.md").read_text(encoding="utf-8")
    assert "No external research was possible" in md
    report = json.loads((rd / "report.json").read_text(encoding="utf-8"))
    assert all(e["source_type"] != "external" for e in report["evidence_ledger"])
    assert [r.inv_id for r in check_all(report, rd) if not r.passed] == []


def test_cli_override_flags_reach_the_manifest(cfgdir: Path, tmp_path: Path) -> None:
    res = invoke(["run", str(PDF), *base_args(cfgdir, "cli-flags"), "--deadline", "300", "--max-tool-calls", "5",
                  "--allow-fallback", "--no-plan-approval"])
    assert res.exit_code == 0, res.output
    m = json.loads((tmp_path / "runs" / "cli-flags" / "manifest.json").read_text(encoding="utf-8"))
    assert m["budgets"] == {"max_tool_calls": 5, "max_tokens": 4000000, "deadline_s": 300}
    assert m["extra"]["model"]["fallbacks"] == "default"
    assert m["extra"]["config"]["cli_args"]["disable_tools"] == ["mcp-research-information"]
    assert {t["name"]: t["enabled"] for t in m["tools"]}["mcp-research-information"] is False


def test_cli_states_and_selftest_commands() -> None:
    res = invoke(["states"])
    assert res.exit_code == 0 and "stateDiagram-v2" in res.output
    res = invoke(["selftest"])
    assert res.exit_code == 0, res.output
    assert "INV-04: ok" in res.output and "selftest passed" in res.output


def test_config_copy_is_pinned_layout(cfgdir: Path) -> None:
    data = yaml.safe_load((cfgdir / "agent.yaml").read_text(encoding="utf-8"))
    assert data["model"] == "claude-opus-5-5"
