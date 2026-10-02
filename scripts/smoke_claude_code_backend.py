#!/usr/bin/env python3
"""Opt-in smoke test of the Claude Code LLM backend (ADR-010). Makes ONE real model call.

Run by hand from the repo root with the agent venv active (not collected by pytest):

    python scripts/smoke_claude_code_backend.py                           # claude-opus-5-5
    python scripts/smoke_claude_code_backend.py --model claude-haiku-4-5  # cheap check

It bills to whatever `claude` is logged in with (subscription or cloud credits).
ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN are removed from the child environment unless
`claude_code.inherit_api_key: true` in config/agent.yaml. The other `claude_code:` keys
(`executable`, `extra_args`, `max_budget_usd_per_call`) and `llm.timeout_s` / `llm.max_retries`
apply as in a run. config.SUPPORTED_MODELS rejects haiku, so the model is overridden on the
gateway after construction, not in the config.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

from sit_review_agent.config import load_config
from sit_review_agent.llm.claude_code import ClaudeCodeGateway
from sit_review_agent.llm.gateway import LLMRequest
from sit_review_agent.llm.outputs import PlanOutput
from sit_review_agent.rundir import RunDir
from sit_review_agent.states import PhaseName

FAKE_DOC = """[[PAGE 1]]
1 Purpose: the Room Booking service lets staff reserve meeting rooms.
2 Decision D-1: reservations stay in the existing PostgreSQL cluster.
3 Requirement R-1: confirmation emails go out within 60 seconds."""

BRIEF = ("Plan a design review of the document above. Return at most one research question, with "
         "criterion_id 'scalability', id 'RQ-001', capability 'search', one query, and section_refs ['2']. "
         "Leave criteria_skipped empty.")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="claude-opus-5-5", help="model for --model (default claude-opus-5-5)")
    ap.add_argument("--effort", default="high", help="effort level (default high)")
    ap.add_argument("--run-dir", type=Path, default=None, help="where llm.jsonl goes (default: a new temp dir)")
    args = ap.parse_args()

    cfg = load_config()
    root = args.run_dir or Path(tempfile.mkdtemp(prefix="sit-cc-smoke-"))
    run_dir = RunDir(root).create()
    gw = ClaudeCodeGateway(cfg, run_dir)
    gw.model = args.model
    await gw.preflight()

    request = LLMRequest(phase=PhaseName.PLAN, conversation_id="smoke", system="You are a careful design reviewer.",
                         messages=[{"role": "user", "content": [{"type": "text", "text": FAKE_DOC},
                                                                {"type": "text", "text": BRIEF}]}],
                         effort=args.effort, max_tokens=2000, output_schema=PlanOutput)
    res = await gw.call(request)
    print("parsed:        ", res.parsed.model_dump_json() if res.parsed else None)
    print("served model:  ", res.model, sorted(gw.served_models()))
    print("usage:         ", res.usage)
    print("total_cost_usd:", f"{gw.cost_total_usd:.4f} (client-side estimate)")
    print("latency_s:     ", f"{res.latency_s:.1f}", "attempts:", len(res.attempts))
    print("llm.jsonl:     ", run_dir.llm_log)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
