"""config.py loads the shipped config/*.yaml and applies CLI overrides."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sit_review_agent import stop_rules
from sit_review_agent.config import ConfigOverrides, Transport, load_config
from sit_review_agent.errors import ConfigError
from sit_review_agent.models import StopReasonCode
from sit_review_agent.paths import config_dir
from sit_review_agent.states import PhaseName


def test_shipped_config_loads() -> None:
    cfg = load_config()
    assert cfg.agent.model == "claude-opus-5-5"
    assert cfg.agent.allow_fallback is False
    assert cfg.agent.transport is Transport.LIVE
    assert cfg.agent.llm.backend == "claude_code" and cfg.agent.claude_code.executable == "claude"
    assert {cfg.effort_for(p) for p in PhaseName if p is not PhaseName.INGEST} == {"high"}
    assert cfg.persona().title
    assert len(cfg.criteria.criteria) >= 10
    assert all(c.question and c.lab_ref and c.kinds for c in cfg.criteria.criteria)
    assert [s.name for s in cfg.tools.enabled_servers()] == ["mcp-internet-search", "mcp-research-information"]
    assert not cfg.tool_allowed("mcp-document-intelligence", "anything")
    assert cfg.tool_allowed("mcp-internet-search", "search")
    assert set(cfg.source_files) >= {"config/agent.yaml", "config/criteria.yaml", "config/stop_rules.yaml",
                                     "config/tools.yaml", "config/url_policy.yaml"}
    assert len(cfg.sha256()) == 64


def test_stop_rules_are_registered_and_closed() -> None:
    cfg = load_config()
    resolved = stop_rules.resolve(cfg.stop_rules.active)
    assert [n for n, _ in resolved] == cfg.stop_rules.active
    with pytest.raises(ConfigError):
        stop_rules.resolve(["two_sources_agree_not_registered"])
    assert {c.value for c in StopReasonCode} >= {"sufficient_evidence", "deadline"}


def test_overrides_apply_and_change_hash() -> None:
    base = load_config()
    cfg = load_config(overrides=ConfigOverrides(max_tool_calls=5, deadline_seconds=300,
                                                disable_tools=("mcp-internet-search",), allow_fallback=True))
    assert cfg.stop_rules.max_tool_calls == 5 and cfg.stop_rules.deadline_seconds == 300
    assert not cfg.tool_allowed("mcp-internet-search", "search")
    assert cfg.agent.allow_fallback is True
    assert cfg.cli_args["max_tool_calls"] == 5
    assert cfg.sha256() != base.sha256()
    assert load_config(overrides=ConfigOverrides(no_tools=True)).tools.enabled_servers() == []
    with pytest.raises(ConfigError):
        load_config(overrides=ConfigOverrides(disable_tools=("no-such-server",)))


def _copy_config(tmp_path: Path) -> Path:
    dst = tmp_path / "config"
    shutil.copytree(config_dir(), dst)
    return dst


def test_runbook_four_line_criterion_append(tmp_path: Path) -> None:
    """Runbook §4.2 #1: appending id / description / applies_to / research_hints loads."""
    d = _copy_config(tmp_path)
    with open(d / "criteria.yaml", "a", encoding="utf-8") as fh:
        fh.write('\n  - id: operational_cost\n    description: "Is running cost estimated, bounded and monitored?"\n'
                 '    applies_to: [all]\n    research_hints: ["cost benchmarks for the named services"]\n')
    cfg = load_config(d)
    c = cfg.criteria.get("operational_cost")
    assert c.question.startswith("Is running cost") and c.kinds == []


@pytest.mark.parametrize("edit,needle", [
    (("agent.yaml", "model: claude-opus-5-5", "model: claude-haiku-4-5"), "not supported"),
    (("agent.yaml", "  verify: true", "  verify: false"), "cannot be disabled"),
    (("agent.yaml", "persona: generalist_architect", "persona: nobody"), "persona"),
    (("agent.yaml", "max_tokens: 64000", "max_tokens: 64000\nunknown_key: 1"), "unknown_key"),
])
def test_invalid_config_is_rejected(tmp_path: Path, edit: tuple[str, str, str], needle: str) -> None:
    d = _copy_config(tmp_path)
    name, old, new = edit
    p = d / name
    p.write_text(p.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        load_config(d)
    assert needle in str(info.value)


def test_optional_phases_can_be_disabled(tmp_path: Path) -> None:
    d = _copy_config(tmp_path)
    p = d / "agent.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("  research: true", "  research: false"), encoding="utf-8")
    assert not load_config(d).agent.phases.enabled(PhaseName.RESEARCH)
