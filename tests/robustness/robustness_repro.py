"""Drills of the runtime policies decided on 2026-10-02 (README.md, "Runtime policies"): what the
agent now does in the three scenarios that used to fail and need a decision. Offline, no key, no
network:

    python tests/robustness/robustness_repro.py            # all of them
    python tests/robustness/robustness_repro.py NET-02     # one

Each prints what the scenario expects and what the agent did. Not collected by pytest (the suite's
own cases assert the same: test_robustness_scenarios.py LLM-05, NET-02, INF-08)."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from robustness_harness import RunRecord, Scenario, run  # noqa: E402

from sit_review_agent.config import Transport  # noqa: E402


def _summary(rec: RunRecord) -> str:
    code = rec.exit_code if rec.exit_code is not None else getattr(rec.raised, "exit_code", None)
    out = [f"exit {int(code) if code is not None else None}, virtual time {rec.virtual_s:.0f} s"]
    if rec.report is not None:
        r = rec.report
        out.append(f"report: verdict {r['verdict']['label']} (confidence {r['verdict']['confidence']}), findings "
                   + json.dumps([(f["id"], f["title"][:40], f["severity"]) for f in r["findings"]]))
        out.append("degradations: " + json.dumps([d["event"][:100] for d in r["research_log"]["degradations"]]))
    elif rec.failure is not None:
        out.append("failure.json: " + json.dumps({k: rec.failure.get(k) for k in ("error", "message", "phase",
                                                                                   "completed_phases")}))
    elif rec.raised is not None:
        out.append(f"raised before the run directory: {type(rec.raised).__name__}: {rec.raised}")
    if rec.run_dir.root.is_dir():
        out.append("run directory: " + ", ".join(sorted(p.name for p in rec.run_dir.root.iterdir())))
    return "\n  ".join(out)


def llm05() -> str:
    rec = run(Scenario(id="LLM-05", faults="LLM-05", overrides={"profile": "demo"}))
    budget = rec.config.stop_rules.deadline_seconds + 30
    return (f"expected: INV-01, run ends within deadline + 30 s = {budget} s (virtual), assess cut and "
            "disclosed\n  " + _summary(rec))


def net02() -> str:
    # the scheduling clock overlaps the six concurrent first calls' waits, as a wall clock would
    rec = run(Scenario(id="NET-02", faults="NET-02", clock="scheduling"))
    return "expected: non-zero exit with an actionable message within 10 s (virtual)\n  " + _summary(rec)


def inf08() -> str:
    rec = run(Scenario(id="INF-08", agent={"transport": Transport.LIVE}, env_unset=("SIT_MCP_API_KEY",)))
    return ("expected: exits within 5 s with an actionable message before any model call (or doc-only with "
            f"--no-tools)\n  wall {rec.wall_s:.2f} s; " + _summary(rec))


REPROS: dict[str, Callable[[], str]] = {"LLM-05": llm05, "NET-02": net02, "INF-08": inf08}


def main(argv: list[str]) -> int:
    for sid in argv or list(REPROS):
        print(f"== {sid}\n  {REPROS[sid]()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
