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
    (("agent.yaml", "max_tokens: 128000", "max_tokens: 128000\nunknown_key: 1"), "unknown_key"),
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


# ------------------------------------------------- latency redesign W0 (design sections 4, 5 and 7)


def _edit(d: Path, name: str, old: str, new: str) -> None:
    p = d / name
    text = p.read_text(encoding="utf-8")
    assert old in text, f"{name} has no {old!r}"
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def _profile(d: Path, body: str) -> None:
    (d / "profiles").mkdir(exist_ok=True)
    (d / "profiles" / "t.yaml").write_text(body, encoding="utf-8")


def test_assess_shards_are_the_four_groups_of_design_section_4() -> None:
    """Design section 4: intent and fitness (3 criteria), requirements and consistency (3), claims and
    assumptions (2), risk and operations (3); every shipped criterion is in exactly one group."""
    cfg = load_config()
    shards = cfg.agent.assess.shards
    assert [(s.name, len(s.criteria)) for s in shards] == [
        ("intent_and_fitness", 3), ("requirements_and_consistency", 3), ("claims_and_assumptions", 2),
        ("risk_and_operations", 3)]
    grouped = [c for s in shards for c in s.criteria]
    assert sorted(grouped) == sorted(cfg.criteria.ids()) and len(grouped) == len(set(grouped)) == 11
    assert cfg.agent.assess.shards_for(cfg.criteria.ids()) == list(shards)


def test_a_criterion_in_no_group_forms_its_own_shard() -> None:
    """A criterion appended live (runbook §4.2 #1) has no group: it becomes a parallel shard of its own,
    after the configured groups. A group keeps only the criteria the run has, and a group with none is left
    out; the order of the run's criteria is kept."""
    cfg = load_config()
    ids = cfg.criteria.ids()
    out = cfg.agent.assess.shards_for([*ids, "operational_cost"])
    assert [s.name for s in out][-1] == "operational_cost" and out[-1].criteria == ["operational_cost"]
    assert out[:-1] == list(cfg.agent.assess.shards)
    partial = cfg.agent.assess.shards_for(["verifiability", "new_one", "design_intent"])
    assert [(s.name, s.criteria) for s in partial] == [
        ("intent_and_fitness", ["design_intent"]), ("requirements_and_consistency", ["verifiability"]),
        ("new_one", ["new_one"])]
    assert cfg.agent.assess.shards_for([]) == []


@pytest.mark.parametrize("edit,needle", [
    (("agent.yaml", "    criteria: [claims_and_external_constraints, assumptions_and_dependencies]",
      "    criteria: [claims_and_external_constraints, assumptions_and_dependencies, design_intent]"),
     "criterion 'design_intent' is in two groups: 'intent_and_fitness' and 'claims_and_assumptions'"),
    (("agent.yaml", "assumptions_and_dependencies]", "assumptions_and_dependencies, no_such_criterion]"),
     "group 'claims_and_assumptions' names an unknown criterion 'no_such_criterion'"),
    (("agent.yaml", "    criteria: [claims_and_external_constraints, assumptions_and_dependencies]",
      "    criteria: []"), "group 'claims_and_assumptions' is empty"),
    (("agent.yaml", "    criteria: [claims_and_external_constraints, assumptions_and_dependencies]",
      "    criteria: [claims_and_external_constraints, claims_and_external_constraints]"),
     "criterion 'claims_and_external_constraints' is listed twice in group 'claims_and_assumptions'"),
    (("agent.yaml", "  - name: claims_and_assumptions", "  - name: intent_and_fitness"),
     "group name 'intent_and_fitness' is used twice"),
])
def test_invalid_shards_are_rejected_with_the_problem_named(tmp_path: Path, edit: tuple[str, str, str],
                                                           needle: str) -> None:
    d = _copy_config(tmp_path)
    _edit(d, *edit)
    with pytest.raises(ConfigError) as info:
        load_config(d)
    assert needle in str(info.value), str(info.value)


def test_zero_shard_groups_is_an_error(tmp_path: Path) -> None:
    d = _copy_config(tmp_path)
    text = (d / "agent.yaml").read_text(encoding="utf-8")
    head, _, _ = text.partition("assess:\n  shards:")
    (d / "agent.yaml").write_text(head + "assess:\n  shards: []\n", encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        load_config(d)
    assert "assess.shards is empty: at least one criterion group is needed" in str(info.value)


def test_refine_reserve_replaces_assess_reserve() -> None:
    cfg = load_config()
    assert cfg.stop_rules.refine_reserve_seconds == 600 and cfg.stop_rules.report_reserve_seconds == 180
    demo = load_config(overrides=ConfigOverrides(profile="demo")).stop_rules
    assert (demo.refine_reserve_seconds, demo.report_reserve_seconds) == (200, 120)
    assert not hasattr(cfg.stop_rules, "assess_reserve_seconds")


@pytest.mark.parametrize("where", ["stop_rules.yaml", "profile"])
def test_the_old_reserve_key_is_an_error_that_names_the_new_key(tmp_path: Path, where: str) -> None:
    """``assess_reserve_seconds`` is neither ignored nor mapped: the loader refuses it and says what
    replaced it, in the base file and in a profile alike."""
    d = _copy_config(tmp_path)
    if where == "stop_rules.yaml":
        _edit(d, "stop_rules.yaml", "refine_reserve_seconds: 600", "assess_reserve_seconds: 600")
        overrides = None
    else:
        _profile(d, "stop_rules:\n  assess_reserve_seconds: 200\n")
        overrides = ConfigOverrides(profile="t")
    with pytest.raises(ConfigError) as info:
        load_config(d, overrides)
    msg = str(info.value)
    assert "assess_reserve_seconds" in msg and "refine_reserve_seconds" in msg and "renamed" in msg
    assert ("profiles/t.yaml" if where == "profile" else "stop_rules.yaml") in msg


def test_stage_limits_are_absolute_seconds_per_profile() -> None:
    """Design section 4: stage 1 ends by 265 s, refine by 465 s, the verdict call by 530 s on the 540 s
    demo profile. The base file keeps the same shape at 3600 s."""
    base = load_config().stop_rules
    assert (base.stage_limits_s.stage_1_end, base.stage_limits_s.refine_end, base.stage_limits_s.verdict_end) \
        == (2820, 3420, 3540)
    assert base.stage_limits_s.stage_1_end == base.deadline_seconds - base.report_reserve_seconds \
        - base.refine_reserve_seconds
    assert base.stage_limits_s.refine_end == base.deadline_seconds - base.report_reserve_seconds
    demo = load_config(overrides=ConfigOverrides(profile="demo")).stop_rules
    assert (demo.stage_limits_s.stage_1_end, demo.stage_limits_s.refine_end, demo.stage_limits_s.verdict_end) \
        == (265, 465, 530)
    assert demo.stage_limits_s.as_dict() == {"stage_1_end": 265, "refine_end": 465, "verdict_end": 530}
    text = (config_dir() / "stop_rules.yaml").read_text(encoding="utf-8")
    assert "stage_limits_s:" in text and "not a fraction of the deadline" in text


@pytest.mark.parametrize("body,needle", [
    ("stop_rules:\n  stage_limits_s: {stage_1_end: 465, refine_end: 265, verdict_end: 530}\n",
     "stage_limits_s must increase: stage_1_end < refine_end < verdict_end, got 465 / 265 / 530"),
    ("stop_rules:\n  stage_limits_s: {stage_1_end: 265, refine_end: 265, verdict_end: 530}\n",
     "stage_limits_s must increase"),
    ("stop_rules:\n  deadline_seconds: 540\n  stage_limits_s: {stage_1_end: 265, refine_end: 465, verdict_end: 540}\n",
     "stage_limits_s.verdict_end 540 s is not below deadline_seconds 540 s"),
    ("stop_rules:\n  deadline_seconds: 321\n",
     "stage_limits_s.verdict_end 3540 s is not below deadline_seconds 321 s"),
    ("stop_rules:\n  stage_limits_s: {stage_1_end: 0, refine_end: 465, verdict_end: 530}\n",
     "greater than or equal to 1"),
])
def test_stage_limits_must_increase_and_fit_the_deadline(tmp_path: Path, body: str, needle: str) -> None:
    """A profile that lowers the deadline under the inherited limits is refused too: absolute seconds
    never move with the deadline, so the profile must set its own."""
    d = _copy_config(tmp_path)
    _profile(d, body)
    with pytest.raises(ConfigError) as info:
        load_config(d, ConfigOverrides(profile="t"))
    assert needle in str(info.value), str(info.value)


def test_a_profile_without_stage_limits_inherits_the_base_values(tmp_path: Path) -> None:
    d = _copy_config(tmp_path)
    _profile(d, "stop_rules:\n  deadline_seconds: 4000\n")
    sr = load_config(d, ConfigOverrides(profile="t")).stop_rules
    assert sr.deadline_seconds == 4000 and sr.stage_limits_s.as_dict() == {"stage_1_end": 2820, "refine_end": 3420,
                                                                           "verdict_end": 3540}
    _profile(d, "stop_rules:\n  stage_limits_s:\n    verdict_end: 3590\n")
    sr = load_config(d, ConfigOverrides(profile="t")).stop_rules
    assert sr.stage_limits_s.as_dict() == {"stage_1_end": 2820, "refine_end": 3420, "verdict_end": 3590}


def test_cli_deadline_below_the_stage_limits_still_loads() -> None:
    """``--deadline`` is applied after validation (like the reserves, whose mismatch ``llm.runtime
    .deadline_warnings`` announces); the limits keep their file values and W1's runtime clamps them."""
    cfg = load_config(overrides=ConfigOverrides(deadline_seconds=300))
    assert cfg.stop_rules.deadline_seconds == 300 and cfg.stop_rules.stage_limits_s.verdict_end == 3540


def test_default_claude_code_argv_is_hermetic(tmp_path: Path) -> None:
    """``claude_code.extra_args: ["--setting-sources", ""]`` (design lever 10, ADR-012 draft): every
    ``claude -p`` argv built from the shipped config ends with the pair. Unverified in a cloud session."""
    from sit_review_agent.llm.claude_code import ClaudeCodeGateway
    from sit_review_agent.llm.gateway import LLMRequest
    from sit_review_agent.rundir import RunDir

    cfg = load_config()
    assert cfg.agent.claude_code.extra_args == ["--setting-sources", ""]
    gw = ClaudeCodeGateway(cfg, RunDir(tmp_path / "run").create())
    req = LLMRequest(phase=PhaseName.ASSESS, conversation_id="c", system="s", messages=[], effort="medium",
                     max_tokens=100)
    argv = gw.build_argv(req, system_text="s", schema_json="{}", session_uuid="u")
    assert argv[-2:] == ["--setting-sources", ""]
    assert argv.count("--setting-sources") == 1
