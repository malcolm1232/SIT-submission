"""Run fixes of 3 Oct 2026 (live review of a 30-page document with the tool servers).

B: every ``progress.jsonl`` record written during a run carries a number in ``run_s``, including
the records written while the run is set up (``run_started``, the MCP warm-up's ``waking`` lines).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from sit_review_agent.clock import FakeClock
from sit_review_agent.orchestrator import RunRequest, run_review
from sit_review_agent.progress import ConsoleProgress
from sit_review_agent.selftest import FIXTURE_DIR, selftest_config
from test_progress_console import scenario


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sinks(root: Path) -> Any:
    made: list[Path] = []

    def make(clock: FakeClock, out: io.StringIO) -> ConsoleProgress:
        path = root / f"progress-{len(made)}.jsonl"
        made.append(path)
        return ConsoleProgress(clock=clock, stream=out, jsonl_path=path)

    make.paths = made  # type: ignore[attr-defined]
    return make


def _no_null_run_s(records: list[dict[str, Any]]) -> list[str]:
    return [f"{r['seq']}:{r['type']}" for r in records
            if not isinstance(r.get("run_s"), int | float) or isinstance(r.get("run_s"), bool)]


# ------------------------------------------------------------------------------ B: run_s


async def test_b_every_record_of_a_run_and_its_resume_carries_run_s(tmp_path: Path) -> None:
    for name in ("selftest", "fail_resume"):
        make = _sinks(tmp_path / name)
        (tmp_path / name).mkdir()
        await scenario(name, tmp_path / name, progress=make)
        for path in make.paths:
            records = _jsonl(path)
            assert records and records[0]["type"] == "run_started"
            assert _no_null_run_s(records) == [], (name, path.name)


class _WakingTools:
    """A tool gateway whose warm-up writes its ``waking`` lines at once, as the live MCP gateway does
    while the run is still being set up (LLM preflight, models.retrieve)."""

    inner = None

    def __init__(self, progress: Any) -> None:
        self.progress = progress

    async def warm_up(self) -> dict[str, str]:
        self.progress.emit("tools", "waking mcp-research-information (~90 s)", "wait")
        self.progress.emit("tools", "waking mcp-standards (~90 s)", "wait")
        return {}

    async def list_tools(self) -> list[Any]:
        return []

    async def aclose(self) -> None:
        return None


async def test_b_waking_lines_written_during_setup_carry_run_s(tmp_path: Path) -> None:
    cfg = selftest_config(tmp_path)
    jsonl = tmp_path / "progress.jsonl"
    clock = FakeClock()
    prog = ConsoleProgress(clock=clock, stream=io.StringIO(), jsonl_path=jsonl)
    await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=cfg, run_id="rf-waking", plan_only=True),
                     clock=clock, progress=prog, tools_factory=lambda rd, off, clk, p: _WakingTools(p))
    records = _jsonl(jsonl)
    waking = [r for r in records if r["message"].startswith("waking ")]
    assert len(waking) == 2
    assert all(isinstance(r["run_s"], int | float) and r["run_s"] >= 0 for r in waking)
    assert _no_null_run_s(records) == []
