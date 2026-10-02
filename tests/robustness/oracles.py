"""Post-run oracles: the shared invariants INV-01..INV-11 (research/robustness/README.md §2) plus the
run-level checks several P0 scenarios share (OPS-10 log completeness, BEH-23 unresolved stated,
BEH-28 report sections, DEMO-06 explain).

INV-03..INV-10 are the agent's own checks (:func:`sit_review_agent.invariants.check_all`, the same
functions the report phase and ``selftest`` run); this module only calls them. What lives here is
what the agent cannot check about itself: termination and the watchdog (INV-01), "a report or a
failure record, never both and never neither" (INV-02), the outbound-request half of INV-08 (the
harness's outbound log stands in for the recording proxy), and "no traceback" (INV-11).

Each oracle returns an :class:`OracleResult`; :func:`run_oracles` runs every applicable one and
:func:`assert_oracles` fails a test with every problem listed.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sit_review_agent.errors import AgentError, ExitCode
from sit_review_agent.invariants import check_all, check_INV_08
from sit_review_agent.report.explain import explain, format_explain
from sit_review_agent.state.evidence_ledger import EvidenceLedger

from robustness_harness import CANARIES, RunRecord

#: Documented exit codes (``errors.ExitCode``; agent/README.md "State machine").
EXIT_CODES = frozenset(int(c) for c in ExitCode)
#: INV-01 slack over the configured wall-clock budget (README §2).
INV01_SLACK_S = 30.0
TRACEBACK = "Traceback (most recent call last)"
#: Sections the brief requires (lab §2.3) as the report template renders them (BEH-28).
REQUIRED_SECTIONS = ("Design intent", "Fitness for purpose", "Strengths", "Risks", "Gaps", "Ambiguities",
                     "Unresolved assumptions", "Validation needs", "Recommended refinements",
                     "Areas where no change is needed", "Unresolved issues and next steps", "Evidence limitations")
#: DEMO-06: what ``explain`` must show for every finding, and how fast.
EXPLAIN_NEEDLES = ("Document anchors", "Evidence", "History", "LLM calls")
EXPLAIN_MAX_S = 5.0


@dataclass(frozen=True)
class OracleResult:
    oracle_id: str
    passed: bool
    problems: list[str] = field(default_factory=list)
    skipped: bool = False


def _r(oid: str, problems: list[str]) -> OracleResult:
    return OracleResult(oid, not problems, problems)


def exit_code(rec: RunRecord) -> int | None:
    """The process exit code: the outcome's, or a typed error's own code when the entry point
    raised it before the run directory existed (the CLI maps it, one line, no traceback)."""
    if rec.exit_code is not None:
        return rec.exit_code
    if isinstance(rec.raised, AgentError):
        return int(rec.raised.exit_code)
    return None


# ============================================================================= INV-01, INV-02, INV-11


def inv01_terminates(rec: RunRecord, *, budget_s: float | None = None) -> OracleResult:
    """Nothing waits forever: the real-time watchdog did not fire, and the run's virtual time stays
    within the configured budget (``stop_rules.deadline_seconds``) plus 30 s."""
    problems: list[str] = []
    if isinstance(rec.raised, TimeoutError):
        problems.append("watchdog fired: the run did not finish in real time")
    budget = (budget_s if budget_s is not None else rec.config.stop_rules.deadline_seconds) + INV01_SLACK_S
    if rec.virtual_s > budget:
        problems.append(f"virtual run time {rec.virtual_s:.0f} s > budget + slack {budget:.0f} s")
    return _r("INV-01", problems)


def inv02_output(rec: RunRecord) -> OracleResult:
    """A full or partial report, or a structured failure record with a documented, distinct exit
    code; never a report from a failed run, never a failed run without a record."""
    code = exit_code(rec)
    problems: list[str] = []
    if code is None:
        return _r("INV-02", [f"no exit code (raised {type(rec.raised).__name__})"])
    if code not in EXIT_CODES:
        problems.append(f"exit code {code} not in the documented set {sorted(EXIT_CODES)}")
    has_report = rec.run_dir.report_json.is_file()
    if code == 0:
        if rec.run_dir.root.is_dir() and not has_report and not _stopped_after_plan(rec):
            problems.append("exit 0 without report.json")
        if has_report and not rec.run_dir.report_md.is_file():
            problems.append("report.json without report.md")
    else:
        if has_report:
            problems.append(f"exit {code} but a report.json exists (a failed run must not look complete)")
        if rec.run_dir.root.is_dir():
            fail = rec.failure
            if fail is None:
                problems.append(f"exit {code} without failure.json")
            elif fail.get("exit_code") != code or "completed_phases" not in fail:
                problems.append(f"failure.json does not match exit {code}: {fail}")
        elif not isinstance(rec.raised, AgentError):
            problems.append(f"exit {code} with neither a run directory nor a typed error")
    return _r("INV-02", problems)


def _stopped_after_plan(rec: RunRecord) -> bool:
    return "stopped after the plan" in rec.stdout


def inv11_no_traceback(rec: RunRecord) -> OracleResult:
    """No unhandled exception: nothing but a typed :class:`AgentError` escaped the entry point,
    and no traceback text is in the console output or any run-directory file."""
    problems: list[str] = []
    if rec.raised is not None and not isinstance(rec.raised, AgentError):
        problems.append(f"unhandled {type(rec.raised).__name__}: {rec.raised}")
    if TRACEBACK in rec.stdout:
        problems.append("traceback in console output")
    if rec.run_dir.root.is_dir():
        for p in sorted(rec.run_dir.root.rglob("*")):
            if p.is_file() and TRACEBACK.encode() in p.read_bytes():
                problems.append(f"traceback in {p.relative_to(rec.run_dir.root)}")
    return _r("INV-11", problems)


# ============================================================================= INV-03..INV-10 (agent)


def agent_invariants(rec: RunRecord) -> list[OracleResult]:
    """INV-03..INV-10 from :mod:`sit_review_agent.invariants` when a report exists; INV-08 (files)
    alone otherwise (a failed run's directory must not hold a secret either)."""
    report = rec.report
    if report is None:
        if not rec.run_dir.root.is_dir():
            return [OracleResult("INV-08", True, skipped=True)]
        r = check_INV_08(rec.run_dir.root, CANARIES)
        return [OracleResult(r.inv_id, r.passed, list(r.problems))]
    return [OracleResult(r.inv_id, r.passed, list(r.problems), r.skipped)
            for r in check_all(report, rec.run_dir.root, canaries=CANARIES)]


def inv08_outbound(rec: RunRecord) -> OracleResult:
    """INV-08, outbound half: no canary in any request that reached the tool transport."""
    text = json.dumps(rec.outbound, ensure_ascii=False)
    return _r("INV-08-outbound", [f"canary {c[:12]}... in an outbound request" for c in CANARIES if c in text])


# ============================================================================= shared scenario checks


def log_complete(rec: RunRecord) -> OracleResult:
    """OPS-10: the provenance logs are complete. Every tool call (server, tool, args and their
    cassette key, status, latency) is in ``tools.jsonl`` and every research-log call is there;
    every model call (call ID, phase, model, stop reason, outcome, token usage) is in
    ``llm.jsonl``; every completed phase has a checkpoint and a started/done progress line; and
    replaying ``ledger.jsonl`` rebuilds the reported ledger exactly. (The fake model gateway logs
    no latency; the live gateways' latency fields are a laptop check.)"""
    problems: list[str] = []
    tools = rec.jsonl("tools.jsonl")
    for e in tools:
        missing = [k for k in ("call_id", "server", "tool", "args", "cassette_key", "status", "elapsed_s", "phase")
                   if k not in e]
        if missing:
            problems.append(f"tools.jsonl {e.get('call_id')}: missing {missing}")
    for e in rec.jsonl("llm.jsonl"):
        need = ["phase", "outcome"] + (["call_id", "model", "stop_reason", "usage"] if e.get("outcome") == "ok" else [])
        missing = [k for k in need if e.get(k) in (None, "")]
        if missing:
            problems.append(f"llm.jsonl {e.get('call_id')}: missing {missing}")
        elif e.get("outcome") == "ok" and not {"input_tokens", "output_tokens"} <= set(e["usage"]):
            problems.append(f"llm.jsonl {e.get('call_id')}: usage without token counts")
    state = rec.state
    done = state.get("completed_phases", [])
    ckpts = {p.stem.split("-", 1)[1] for p in rec.run_dir.checkpoints.glob("*.json")} if rec.run_dir.checkpoints.is_dir() \
        else set()
    problems += [f"no checkpoint for completed phase {p}" for p in done if p not in ckpts]
    progress = rec.run_dir.progress_log.read_text(encoding="utf-8") if rec.run_dir.progress_log.is_file() else ""
    for p in done:
        if f"{p:<10} | started" not in progress or not any(f"{p:<10} | OK done" in ln for ln in progress.splitlines()):
            problems.append(f"progress.log lacks the started/done transition of {p}")
    report = rec.report
    if report is not None:
        logged = {e.get("call_id") for e in tools}
        problems += [f"research_log call {c['call_id']} not in tools.jsonl"
                     for c in report["research_log"]["tool_calls"] if c["call_id"] not in logged]
        rebuilt = [e.model_dump(mode="json") for e in EvidenceLedger.load(rec.run_dir).entries()]
        snapshot = json.loads(rec.run_dir.ledger.read_text(encoding="utf-8")) \
            if rec.run_dir.ledger.is_file() else None
        if snapshot is not None and rebuilt != snapshot:
            problems.append("ledger.jsonl replay does not rebuild ledger.json")
        if rebuilt != report["evidence_ledger"]:
            problems.append("ledger.jsonl replay does not rebuild the report's evidence_ledger")
    return _r("OPS-10", problems)


def unresolved_stated(rec: RunRecord) -> OracleResult:
    """BEH-23: whenever the run had an evidence gap or a fault (a degradation, a failed tool call,
    an unanswered question), the report says so: limitations are non-empty and the report renders
    its "Unresolved issues" and "Evidence limitations" sections."""
    report = rec.report
    if report is None:
        return OracleResult("BEH-23", True, skipped=True)
    log = report["research_log"]
    gap = bool(log["degradations"] or log["unanswered_questions"]
               or any(c["status"] != "ok" for c in log["tool_calls"]))
    problems: list[str] = []
    md = rec.run_dir.report_md.read_text(encoding="utf-8")
    for heading in ("## Unresolved issues and next steps", "## Evidence limitations"):
        if heading not in md:
            problems.append(f"report.md lacks {heading!r}")
    if gap and not report["limitations"]:
        problems.append("evidence gap or fault in the run but no limitation in the report")
    if gap and "## Evidence limitations" in md:
        section = md.split("## Evidence limitations", 1)[1].split("\n## ", 1)[0]
        if not section.strip():
            problems.append("the Evidence limitations section is empty")
    return _r("BEH-23", problems)


def report_sections(rec: RunRecord) -> OracleResult:
    """BEH-28: every section the brief requires is rendered (the schema half is INV-03)."""
    if rec.report is None:
        return OracleResult("BEH-28", True, skipped=True)
    md = rec.run_dir.report_md.read_text(encoding="utf-8")
    return _r("BEH-28", [f"report.md lacks section {s!r}" for s in REQUIRED_SECTIONS if f"## {s}" not in md])


def explain_all(rec: RunRecord) -> OracleResult:
    """DEMO-06: ``explain <finding_id>`` works for every finding, shows anchors, evidence, history
    and model calls, and answers in under 5 s."""
    report = rec.report
    if report is None:
        return OracleResult("DEMO-06", True, skipped=True)
    problems: list[str] = []
    for f in report["findings"]:
        t0 = time.monotonic()
        try:
            text = format_explain(explain(rec.run_dir.root, f["id"]))
        except Exception as exc:  # noqa: BLE001 - reported as a failed check
            problems.append(f"explain {f['id']}: {type(exc).__name__}: {exc}")
            continue
        if time.monotonic() - t0 > EXPLAIN_MAX_S:
            problems.append(f"explain {f['id']} took more than {EXPLAIN_MAX_S:.0f} s")
        problems += [f"explain {f['id']} lacks {n!r}" for n in (f["id"], *EXPLAIN_NEEDLES) if n not in text]
        if "NOT IN LEDGER" in text:
            problems.append(f"explain {f['id']} shows evidence that is not in the ledger")
    return _r("DEMO-06", problems)


# ============================================================================= aggregate


def run_oracles(rec: RunRecord, *, budget_s: float | None = None) -> list[OracleResult]:
    out = [inv01_terminates(rec, budget_s=budget_s), inv02_output(rec), *agent_invariants(rec),
           inv08_outbound(rec), inv11_no_traceback(rec)]
    if rec.run_dir.root.is_dir():
        out.append(log_complete(rec))
    out += [unresolved_stated(rec), report_sections(rec), explain_all(rec)]
    return out


def failures(results: Iterable[OracleResult]) -> list[str]:
    return [f"{r.oracle_id}: {p}" for r in results if not r.passed for p in r.problems]


def assert_oracles(rec: RunRecord, *, budget_s: float | None = None) -> list[OracleResult]:
    results = run_oracles(rec, budget_s=budget_s)
    bad = failures(results)
    assert not bad, f"{rec.scenario.id}: oracle failures:\n  " + "\n  ".join(bad) + _context(rec)
    return results


def _context(rec: RunRecord) -> str:
    fail = rec.failure
    return f"\n  exit={exit_code(rec)} raised={rec.raised!r} failure={json.dumps(fail)[:600] if fail else None}"


def report_text(rec: RunRecord) -> str:
    """report.json + report.md as one string (for "is it disclosed" checks)."""
    report: Any = rec.report
    md = rec.run_dir.report_md.read_text(encoding="utf-8") if rec.run_dir.report_md.is_file() else ""
    return json.dumps(report, ensure_ascii=False) + "\n" + md
