"""Pins the line numbers of the live-change keys (docs/DEMO_DAY_RUNBOOK.md §4.1). If this fails,
update the runbook and this test together."""

from __future__ import annotations

import re

import pytest

from sit_review_agent.paths import config_dir, repo_root

PINNED = {
    "agent.yaml": {2: "model:", 3: "effort:", 4: "  plan:", 5: "  research:", 6: "  assess:", 7: "  refine:",
                   8: "  verify:", 9: "  report:", 10: "max_tokens:", 11: "allow_fallback:", 12: "persona:"},
    "stop_rules.yaml": {2: "active:", 3: "max_tool_calls:", 4: "max_research_iterations:", 5: "max_input_tokens:",
                        6: "deadline_seconds:", 7: "no_marginal_gain_window:", 8: "min_independent_sources:"},
    "tools.yaml": {2: "auth_env:", 3: "auth_header:", 4: "servers:", 5: "  - name: mcp-internet-search",
                   6: "    enabled:", 7: "    allow_tools:", 8: "  - name: mcp-research-information",
                   9: "    enabled:", 10: "    allow_tools:", 11: "  - name: mcp-browser-automation-pw",
                   12: "    enabled:", 13: "    allow_tools:", 14: "  - name: mcp-document-intelligence",
                   15: "    enabled:", 16: "    allow_tools:", 17: "url_policy:"},
}


@pytest.mark.parametrize("name", sorted(PINNED))
def test_pinned_lines(name: str) -> None:
    lines = (config_dir() / name).read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith(f"# config/{name}")
    for lineno, prefix in PINNED[name].items():
        assert lines[lineno - 1].startswith(prefix), f"{name}:{lineno} is {lines[lineno - 1]!r}, want {prefix!r}..."


def test_model_line_value() -> None:
    lines = (config_dir() / "agent.yaml").read_text(encoding="utf-8").splitlines()
    assert lines[1] == "model: claude-opus-5-5" and lines[10] == "allow_fallback: false"


RUNBOOK = repo_root() / "docs" / "DEMO_DAY_RUNBOOK.md"


@pytest.mark.parametrize("name", sorted(PINNED))
def test_runbook_listing_equals_the_config_file(name: str) -> None:
    """The numbered listing of each config file in runbook §4.1 is the file's own text, line for
    line. The prefix check above let the values drift (2026-10-03: `research: medium` against
    `high`, the browser server `enabled: true` against `false`, an old `url_policy:` path)."""
    text = RUNBOOK.read_text(encoding="utf-8")
    block = re.search(r"`config/" + re.escape(name) + r"`[^\n]*\n```yaml\n(.*?)```", text, re.S)
    assert block, f"runbook §4.1 has no listing of config/{name}"
    lines = (config_dir() / name).read_text(encoding="utf-8").splitlines()
    listed = [re.match(r"^\s*(\d+)  (.*)$", ln) for ln in block.group(1).splitlines()]
    assert all(listed) and [int(m.group(1)) for m in listed if m] == list(range(1, max(PINNED[name]) + 1))
    for m in listed:
        assert m is not None
        n, shown = int(m.group(1)), m.group(2)
        assert shown.rstrip() == lines[n - 1].rstrip(), f"runbook §4.1 config/{name} line {n}"


def test_demo_profile_lines_named_by_the_runbook() -> None:
    """Runbook §4.1 and §4.2 send a live effort or deadline change of a `--profile demo` run to
    config/profiles/demo.yaml lines 19-24 and 27, and §5 quotes its deadline and reserves."""
    lines = (config_dir() / "profiles" / "demo.yaml").read_text(encoding="utf-8").splitlines()
    want = {19: "    plan:", 20: "    research:", 21: "    assess:", 22: "    refine:", 23: "    verify:",
            24: "    report:", 27: "  deadline_seconds: 540"}
    for lineno, prefix in want.items():
        assert lines[lineno - 1].startswith(prefix), f"demo.yaml:{lineno} is {lines[lineno - 1]!r}"
    text = "\n".join(lines)
    assert "report_reserve_seconds: 120" in text and "assess_reserve_seconds: 200" in text
    runbook = RUNBOOK.read_text(encoding="utf-8")
    for needle in ("--profile demo`. Updated SIT design", "Research stops by 220 s", "is cut at 420 s",
                   "verify and report keep 120 s", "`config/profiles/demo.yaml` lines 19-24"):
        assert needle in runbook, needle
    assert "--deadline 540" not in runbook            # the demo deadline comes from the profile
