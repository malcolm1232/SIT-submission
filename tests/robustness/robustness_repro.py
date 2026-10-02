"""Reproductions of the P0 scenarios that fail because of an agent defect this workstream did not fix
(README.md, "Failing, needs decision"). Offline, no key, no network:

    python tests/robustness/robustness_repro.py            # all of them
    python tests/robustness/robustness_repro.py NET-02     # one

Each prints what the scenario expects and what the agent did. Not collected by pytest (the suite
never asserts known-wrong behaviour)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from robustness_harness import DOC, RunRecord, Scenario, ScenarioGateway, build_script, run  # noqa: E402


def _summary(rec: RunRecord) -> str:
    out = [f"exit {rec.exit_code}, virtual time {rec.virtual_s:.0f} s"]
    if rec.report is not None:
        r = rec.report
        out.append(f"report: verdict {r['verdict']['label']}, findings "
                   + json.dumps([(f["id"], f["title"][:40], f["severity"]) for f in r["findings"]]))
        out.append("degradations: " + json.dumps([d["event"][:100] for d in r["research_log"]["degradations"]]))
    elif rec.failure is not None:
        out.append("failure.json: " + json.dumps({k: rec.failure.get(k) for k in ("error", "message", "phase",
                                                                                   "completed_phases")}))
    out.append("run directory: " + ", ".join(sorted(p.name for p in rec.run_dir.root.iterdir())))
    return "\n  ".join(out)


def llm05() -> str:
    rec = run(Scenario(id="LLM-05", faults="LLM-05"))
    budget = rec.config.stop_rules.deadline_seconds + 30
    return (f"expected: INV-01, run ends within deadline + 30 s = {budget} s (virtual)\n  " + _summary(rec))


def net02() -> str:
    rec = run(Scenario(id="NET-02", faults="NET-02"))
    return "expected: non-zero exit with an actionable message within 10 s (virtual)\n  " + _summary(rec)


def inf08() -> str:
    """Live transport, MCP key unset, scripted model, network guarded (a session factory that raises)."""
    import asyncio
    import io

    from sit_review_agent.clock import FakeClock
    from sit_review_agent.config import load_config
    from sit_review_agent.orchestrator import RunRequest, run_review
    from sit_review_agent.progress import ConsoleProgress
    from sit_review_agent.tools import gateway as g

    def no_network(*a: Any, **k: Any) -> Any:
        raise AssertionError("network attempted")

    init = g.MCPToolGateway.__init__

    def guarded(self: Any, *a: Any, **k: Any) -> None:
        init(self, *a, **k)
        self.session_factory = no_network

    saved = os.environ.pop("SIT_MCP_API_KEY", None)
    g.MCPToolGateway.__init__ = guarded                                   # type: ignore[method-assign]
    try:
        tmp = Path(tempfile.mkdtemp(prefix="robustness-INF-08-"))
        cfg = load_config()
        cfg = cfg.model_copy(update={"agent": cfg.agent.model_copy(update={"run_root": str(tmp)})})
        clock, out = FakeClock(), io.StringIO()
        res = asyncio.run(run_review(
            RunRequest(pdf=DOC, config=cfg, run_id="INF-08"), clock=clock,
            llm_factory=lambda rd, c, p: ScenarioGateway(rd, c, build_script(cfg.criteria.ids(), None),
                                                         model=cfg.agent.model),
            progress=ConsoleProgress(clock=clock, stream=out)))
        llm = (tmp / "INF-08" / "llm.jsonl").read_text(encoding="utf-8").splitlines()
        return ("expected: exits within 5 s with an actionable message before any model call (or doc-only with "
                f"--no-tools)\n  exit {res.exit_code}; model calls made: {len(llm)}; "
                + "; ".join(ln for ln in out.getvalue().splitlines() if "SIT_MCP_API_KEY" in ln)[:300])
    finally:
        g.MCPToolGateway.__init__ = init                                  # type: ignore[method-assign]
        if saved is not None:
            os.environ["SIT_MCP_API_KEY"] = saved


REPROS: dict[str, Callable[[], str]] = {"LLM-05": llm05, "NET-02": net02, "INF-08": inf08}


def main(argv: list[str]) -> int:
    for sid in argv or list(REPROS):
        print(f"== {sid}\n  {REPROS[sid]()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
