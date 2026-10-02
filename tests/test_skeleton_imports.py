"""Every module of the package imports, and the CLI wires up (interface freeze smoke test)."""

from __future__ import annotations

import importlib
import pkgutil

import pytest
from typer.testing import CliRunner

import sit_review_agent

MODULES = sorted(m.name for m in pkgutil.walk_packages(sit_review_agent.__path__, prefix="sit_review_agent."))

EXPECTED = {
    "sit_review_agent.models", "sit_review_agent.config", "sit_review_agent.cli", "sit_review_agent.invariants",
    "sit_review_agent.orchestrator", "sit_review_agent.states", "sit_review_agent.stop_rules",
    "sit_review_agent.context", "sit_review_agent.prompts", "sit_review_agent.manifest", "sit_review_agent.selftest",
    "sit_review_agent.llm.gateway", "sit_review_agent.llm.outputs", "sit_review_agent.llm.prefix",
    "sit_review_agent.tools.gateway", "sit_review_agent.tools.faults", "sit_review_agent.tools.cassette",
    "sit_review_agent.tools.sources", "sit_review_agent.ingest.pdf", "sit_review_agent.ingest.anchor",
    "sit_review_agent.ingest.text", "sit_review_agent.state.evidence_ledger",
    "sit_review_agent.state.decision_registry", "sit_review_agent.state.checkpoint",
    "sit_review_agent.state.run_state", "sit_review_agent.report.render", "sit_review_agent.report.explain",
    *(f"sit_review_agent.phases.{p}" for p in
      ("base", "ingest", "understand", "plan", "research", "assess", "refine", "verify", "report")),
}


def test_expected_modules_exist() -> None:
    assert EXPECTED <= set(MODULES), sorted(EXPECTED - set(MODULES))


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    importlib.import_module(name)


def test_every_phase_satisfies_protocol() -> None:
    from sit_review_agent.phases import Phase, default_phases
    from sit_review_agent.states import PHASE_ORDER

    phases = default_phases()
    assert list(phases) == list(PHASE_ORDER)
    for name, p in phases.items():
        assert isinstance(p, Phase) and p.name is name


def test_gateways_satisfy_protocols(tmp_path) -> None:
    from sit_review_agent.config import load_config
    from sit_review_agent.llm.gateway import AnthropicGateway, FakeGateway, LLMGateway
    from sit_review_agent.rundir import RunDir
    from sit_review_agent.tools.gateway import (
        FakeToolGateway,
        MCPToolGateway,
        ReplayGateway,
        ToolGateway,
        build_tool_gateway,
    )

    cfg = load_config()
    rd = RunDir(tmp_path / "run").create()
    assert isinstance(FakeGateway({}), LLMGateway)
    assert isinstance(AnthropicGateway(cfg, rd), LLMGateway)
    assert isinstance(ReplayGateway(tmp_path), ToolGateway)
    assert isinstance(FakeToolGateway([], {}), ToolGateway)
    assert isinstance(MCPToolGateway(cfg.tools, cfg.endpoints.servers), ToolGateway)
    assert isinstance(build_tool_gateway(cfg, rd), ToolGateway)


@pytest.mark.parametrize("cmd", ["run", "review", "explain", "selftest", "resume", "preflight", "states"])
def test_cli_commands_have_help(cmd: str) -> None:
    from sit_review_agent.cli import app

    res = CliRunner().invoke(app, [cmd, "--help"])
    assert res.exit_code == 0, res.output


def test_cli_states_prints_mermaid() -> None:
    from sit_review_agent.cli import app

    res = CliRunner().invoke(app, ["states"])
    assert res.exit_code == 0 and "stateDiagram-v2" in res.output
