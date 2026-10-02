"""Tests for modules that are stubs today. Each names the build phase / workstream that unskips it
(agent/README.md). Remove the skip marker in the same change that implements the module."""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="phase 1 (workstream A): AnthropicGateway.build_body/call")
def test_anthropic_gateway_request_shape() -> None:
    """build_body: thinking adaptive, output_config.effort, no temperature/top_p/top_k/budget_tokens,
    no forced tool_choice, cache_control on the breakpointed block, fallbacks only if allowed."""


@pytest.mark.skip(reason="phase 1 (workstream A): AnthropicGateway retry policy with a fake client")
def test_anthropic_gateway_retry_and_stop_reasons() -> None:
    """429 honours retry-after; 529 backs off; refusal/max_tokens raise typed errors; max_retries=0 on the SDK."""


@pytest.mark.skip(reason="phase 1 (workstream A): understand/plan/assess/refine with FakeGateway")
def test_model_phases_with_fake_gateway() -> None:
    """Each phase writes the RunState fields its docstring lists."""


@pytest.mark.skip(reason="phase 2 (workstream B): MCPToolGateway against an in-process MCP server")
def test_mcp_gateway_cold_start_and_session_reinit() -> None:
    """One retry on cold-start-like failure; re-initialize on 404; 401 disables all servers."""


@pytest.mark.skip(reason="phase 2 (workstream B): fault injection INF-01/INF-07/INF-24/LLM-01..06/NET-01")
def test_fault_injection_drills() -> None:
    """Runbook §7 drills at L0 with FakeClock."""


@pytest.mark.skip(reason="phase 2 (workstream B): research loop with ReplayGateway + FakeGateway")
def test_research_loop_ledger_and_stop_rules() -> None:
    """Parallel tool results in one user message; ledger entries per source; stop rule recorded."""


@pytest.mark.skip(reason="phase 3 (workstream C): verify + report + render")
def test_verify_and_report_produce_valid_review() -> None:
    """Hydrated findings validate; report.json passes invariants.check_all; report.md has every section."""


@pytest.mark.skip(reason="phase 3 (workstream C): explain")
def test_explain_reads_run_dir_only() -> None:
    """explain(run_dir, finding_id) joins report, anchors, ledger, tools.jsonl and state."""


@pytest.mark.skip(reason="phase 3 (workstream C): resume (ADR-009: OPS-04, NET-01, BEH-25, LLM-02)")
def test_resume_reuses_completed_tool_calls() -> None:
    """No repeated tool call, no duplicate ledger ID, byte-identical replayed assistant turns."""


@pytest.mark.skip(reason="phase 3 (workstream C): sit-review selftest end to end")
def test_selftest_end_to_end() -> None:
    """run_selftest() returns INV-03..INV-10 all passing in under 60 s."""
