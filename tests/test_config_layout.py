"""Pins the line numbers of the live-change keys (docs/DEMO_DAY_RUNBOOK.md §4.1). If this fails,
update the runbook and this test together."""

from __future__ import annotations

import pytest

from sit_review_agent.paths import config_dir

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
