"""Config profiles: named overlays over agent.yaml and stop_rules.yaml."""

import shutil
from pathlib import Path

import pytest

from sit_review_agent.config import ConfigOverrides, load_config
from sit_review_agent.errors import ConfigError
from sit_review_agent.paths import config_dir


def _copy_config(tmp_path: Path) -> Path:
    dst = tmp_path / "config"
    shutil.copytree(config_dir(), dst)
    (dst / "profiles").mkdir(exist_ok=True)
    return dst


def test_profile_overlays_agent_and_stop_rules(tmp_path: Path) -> None:
    root = _copy_config(tmp_path)
    (root / "profiles" / "t.yaml").write_text(
        "agent:\n  effort:\n    assess: medium\nstop_rules:\n  deadline_seconds: 321\n"
        "  stage_limits_s: {stage_1_end: 150, refine_end: 270, verdict_end: 310}\n")
    base = load_config(root)
    cfg = load_config(root, ConfigOverrides(profile="t"))
    assert cfg.agent.effort.assess == "medium"
    assert cfg.stop_rules.deadline_seconds == 321
    assert cfg.agent.model == base.agent.model                      # untouched keys keep their values
    assert cfg.cli_args.get("profile") == "t"
    assert any(k.endswith("profiles/t.yaml") for k in cfg.source_files)


def test_cli_deadline_still_wins_over_profile(tmp_path: Path) -> None:
    root = _copy_config(tmp_path)
    (root / "profiles" / "t.yaml").write_text(
        "stop_rules:\n  deadline_seconds: 321\n"
        "  stage_limits_s: {stage_1_end: 150, refine_end: 270, verdict_end: 310}\n")
    cfg = load_config(root, ConfigOverrides(profile="t", deadline_seconds=100))
    assert cfg.stop_rules.deadline_seconds == 100


@pytest.mark.parametrize("body", ["tools:\n  servers: []\n", "- a\n"])
def test_profile_rejects_other_sections(tmp_path: Path, body: str) -> None:
    root = _copy_config(tmp_path)
    (root / "profiles" / "bad.yaml").write_text(body)
    with pytest.raises(ConfigError):
        load_config(root, ConfigOverrides(profile="bad"))


@pytest.mark.parametrize("name", ["missing", "../agent", ".hidden"])
def test_unknown_or_unsafe_profile_is_a_config_error(tmp_path: Path, name: str) -> None:
    with pytest.raises(ConfigError):
        load_config(_copy_config(tmp_path), ConfigOverrides(profile=name))
