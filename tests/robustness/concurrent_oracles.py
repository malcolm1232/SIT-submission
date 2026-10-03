"""Oracles of the concurrent-stage scenarios (``faults_concurrent/``, latency redesign of 2026-10-03).

Each ``check_<id>`` takes the faulted run, the fault-free control run and the resolved schedule
(:mod:`concurrent_schedules`) and returns the problems found (empty = pass). Every check calls the
agent's own invariants (:func:`sit_review_agent.invariants.check_all`, INV-03..INV-10 and INV-12) and then the
scenario's own expectation: what must be disclosed, which criteria are not assessed, that the other
shards' findings survive, and that nothing crashed. In the end-to-end form (the integration pass,
README.md) ``oracles.assert_oracles`` runs as well, as for every scenario.

Two names are the contract with the concurrent orchestrator and are checked here, not guessed per
test: :data:`NOT_ASSESSED`, the coverage outcome of a criterion whose shard did not finish
(``state.json`` ``coverage``, read through :func:`sit_review_agent.report.coverage.build_coverage`),
and :data:`DISCLOSURE`, the words a degradation uses for each way a shard or call ends. A degradation
about a shard names the shard's group (``assess.shards[].name``).

Confirmed against the orchestrator in the integration pass (2026-10-03): the output schema's coverage
outcomes are ``findings``, ``no_issue`` and ``not_applicable`` only, so a criterion no shard assessed
is written as ``not_applicable`` with a note starting
:data:`sit_review_agent.report.coverage.NOT_ASSESSED_NOTE` ("not assessed"), the form the report's
coverage map reads. :func:`is_not_assessed` is that predicate; :attr:`ConcurrentRun.coverage` reports
such a row as :data:`NOT_ASSESSED`, so every check keeps the one name.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from concurrent_schedules import ConcurrentSchedule, ShardTarget

from sit_review_agent.invariants import check_all
from sit_review_agent.report.coverage import NOT_ASSESSED_NOTE, build_coverage
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.state.evidence_ledger import EvidenceLedger

#: Coverage outcome of a criterion no shard assessed (a cut, declined, truncated or failed shard), as
#: :attr:`ConcurrentRun.coverage` reports it (see the module docstring for the form on disk).
NOT_ASSESSED = "not_assessed"


def is_not_assessed(row: Any) -> bool:
    """Whether a ``state.json`` coverage row (or ``(outcome, note)``) says the criterion was not assessed:
    outcome ``not_applicable`` and a note starting with ``NOT_ASSESSED_NOTE``."""
    outcome, note = (row.get("outcome"), row.get("note")) if isinstance(row, dict) else row
    return outcome == "not_applicable" and str(note or "").lower().startswith(NOT_ASSESSED_NOTE)


def mark_not_assessed(row: dict[str, Any], why: str = "fixture") -> None:
    """Write the orchestrator's form of a not-assessed criterion into a coverage row."""
    row["outcome"], row["finding_ids"], row["note"] = "not_applicable", [], f"{NOT_ASSESSED_NOTE}: {why}"
#: Words a degradation event uses for each ending (any one of them, case-insensitive).
DISCLOSURE: dict[str, tuple[str, ...]] = {
    "cut": ("cut", "out of time"),
    "declined": ("declined",),
    "truncated": ("truncated twice",),
    "failed": ("failed", "error", "exception"),
    "refine_fallback": ("refine",),
    "research_cut": ("research",),
}
CUT_OUTCOME = "LLMDeadlineError"
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
TRACEBACK = "Traceback (most recent call last)"
#: Canary keys of the robustness harness (``robustness_harness.CANARIES``; repeated so this module
#: imports without the harness).
CANARIES = ("CANARY-MCP-7f3a9c5e1d20", "CANARY-LLM-c21e0b4d8a63")


@dataclass
class ConcurrentRun:
    """What the oracles read of one run: the run directory and the process exit code."""

    root: Path
    exit_code: int | None
    stdout: str = ""

    @classmethod
    def from_record(cls, rec: Any) -> ConcurrentRun:
        from oracles import exit_code

        return cls(rec.run_dir.root, exit_code(rec), rec.stdout)

    def _json(self, name: str) -> Any:
        p = self.root / name
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    @cached_property
    def report(self) -> dict[str, Any] | None:
        return self._json("report.json")

    @cached_property
    def coverage(self) -> tuple[dict[str, str], dict[str, list[str]]]:
        """(criterion -> coverage outcome, criterion -> reported finding IDs)."""
        if self.report is None:
            return {}, {}
        cm = build_coverage(self.root)
        outcomes = {c: (NOT_ASSESSED if is_not_assessed((o, cm.notes.get(c))) else o) for c, o in cm.outcomes.items()}
        return outcomes, {c: list(ids) for c, ids in cm.criterion_findings.items()}

    def llm(self, phase: str | None = None) -> list[dict[str, Any]]:
        return [e for e in JsonlWriter(self.root / "llm.jsonl").read() if phase is None or e.get("phase") == phase]

    def faulted(self, phase: str) -> list[str]:
        """Outcomes of the injected-fault entries of ``phase`` in ``llm.jsonl``, in order."""
        return [str(e.get("outcome")) for e in self.llm(phase) if e.get("fault")]

    def titles(self) -> list[str]:
        return [f["title"] for f in (self.report or {}).get("findings", [])]

    def degradations(self) -> list[dict[str, Any]]:
        return list((self.report or {}).get("research_log", {}).get("degradations", []))


# ============================================================================= shared checks


def no_crash(run: ConcurrentRun) -> list[str]:
    """A salvaged review, never a crash: exit 0, report.json and report.md, no failure record and no
    partial report, no traceback in the console or the run directory."""
    out: list[str] = []
    if run.exit_code != 0:
        out.append(f"exit {run.exit_code}, expected 0 (a salvaged, disclosed report)")
    if run.report is None:
        out.append("no report.json")
    elif not (run.root / "report.md").is_file():
        out.append("report.json without report.md")
    out += [f"{n} written: the run must not look failed" for n in ("failure.json", "report.partial.md")
            if (run.root / n).is_file()]
    if TRACEBACK in run.stdout:
        out.append("traceback in console output")
    if run.root.is_dir():
        out += [f"traceback in {p.relative_to(run.root)}" for p in sorted(run.root.rglob("*"))
                if p.is_file() and TRACEBACK.encode() in p.read_bytes()]
    return out


def invariants(run: ConcurrentRun) -> list[str]:
    """INV-03..INV-10 and INV-12 from :mod:`sit_review_agent.invariants` on the report and run directory."""
    if run.report is None:
        return []                                                        # no_crash reports the missing report
    return [f"{r.inv_id}: {p}" for r in check_all(run.report, run.root, canaries=CANARIES)
            if not r.passed for p in r.problems]


def disclosed(run: ConcurrentRun, kind: str, *names: str, deg_type: str | None = None) -> list[str]:
    """A degradation whose event names every one of ``names`` and uses a :data:`DISCLOSURE` word of
    ``kind`` (and has type ``deg_type`` when given), cited by a limitation."""
    words = DISCLOSURE[kind]
    cited = {x for lim in (run.report or {}).get("limitations", []) for x in lim["degradation_ids"]}
    for d in run.degradations():
        event = d["event"].lower()
        if all(n.lower() in event for n in names) and any(w in event for w in words) \
                and (deg_type is None or d["type"] == deg_type):
            return [] if d["id"] in cited else [f"degradation {d['id']} ({kind}) not cited by a limitation"]
    want = f" of type {deg_type}" if deg_type else ""
    return [f"no degradation{want} naming {', '.join(names) or 'the event'} with one of {list(words)}"]


def criteria_not_assessed(run: ConcurrentRun, target: ShardTarget) -> list[str]:
    """Every criterion of the faulted shard without a finding is reported not assessed."""
    outcomes, found = run.coverage
    out: list[str] = []
    for c in target.criteria:
        if found.get(c):
            continue                                                     # kept: finished before the end
        if outcomes.get(c) != NOT_ASSESSED:
            out.append(f"criterion {c} of shard {target.name}: coverage {outcomes.get(c)!r}, expected {NOT_ASSESSED!r}")
    return out


def others_survive(run: ConcurrentRun, control: ConcurrentRun, lost: Iterable[str]) -> list[str]:
    """Every fault-free finding whose criteria are all outside ``lost`` is in the run (by title), and
    no criterion outside ``lost`` is reported not assessed."""
    lost = set(lost)
    _, control_found = control.coverage
    criteria_of: dict[str, set[str]] = {}
    for c, ids in control_found.items():
        for fid in ids:
            criteria_of.setdefault(fid, set()).add(c)
    titles = set(run.titles())
    out = [f"finding {f['id']} of criteria {sorted(criteria_of.get(f['id'], ()))} lost"
           for f in (control.report or {}).get("findings", [])
           if criteria_of.get(f["id"]) and not criteria_of[f["id"]] & lost and f["title"] not in titles]
    outcomes, _ = run.coverage
    out += [f"criterion {c} outside the faulted shard reported not assessed"
            for c, o in outcomes.items() if c not in lost and o == NOT_ASSESSED]
    return out


def verdict_assessed(run: ConcurrentRun) -> list[str]:
    """A partial review still has a verdict: ``not_assessed`` only when no shard finished a finding."""
    r = run.report or {}
    out: list[str] = []
    if r.get("verdict", {}).get("label") == "not_assessed":
        out.append("verdict not_assessed although other shards finished findings")
    if not r.get("findings"):
        out.append("no finding although other shards finished")
    return out


def _calls(run: ConcurrentRun, phase: str, expected: Sequence[str]) -> list[str]:
    got = run.faulted(phase)
    return [] if got == list(expected) else [f"faulted {phase} calls {got}, expected {list(expected)}"]


def _shard(cs: ConcurrentSchedule) -> ShardTarget:
    if len(cs.targets) != 1:
        raise ValueError(f"{cs.id}: expected exactly one faulted shard, got {[t.name for t in cs.targets]}")
    return cs.targets[0]


def _shard_scenario(run: ConcurrentRun, control: ConcurrentRun, cs: ConcurrentSchedule, kind: str,
                    *, deg_type: str | None = None) -> list[str]:
    t = _shard(cs)
    return [*no_crash(run), *invariants(run), *disclosed(run, kind, t.name, deg_type=deg_type),
            *criteria_not_assessed(run, t), *others_survive(run, control, t.criteria), *verdict_assessed(run)]


# ============================================================================= the six scenarios


def check_llm13(run: ConcurrentRun, control: ConcurrentRun, cs: ConcurrentSchedule) -> list[str]:
    """One shard hangs: cut at the stage 1 end, not retried, disclosed as budget_or_deadline_hit."""
    got = run.faulted("assess")
    calls = [] if got and got[-1] == CUT_OUTCOME and got.count(CUT_OUTCOME) == 1 else \
        [f"faulted assess calls {got}: the hang must end in one {CUT_OUTCOME} (cut, not retried)"]
    return [*_shard_scenario(run, control, cs, "cut", deg_type="budget_or_deadline_hit"), *calls]


def check_llm14(run: ConcurrentRun, control: ConcurrentRun, cs: ConcurrentSchedule) -> list[str]:
    """One shard declines: the call and one reframed retry, no third call, 'declined' disclosed."""
    return [*_shard_scenario(run, control, cs, "declined"), *_calls(run, "assess", ["LLMRefusalError"] * 2)]


def check_llm15(run: ConcurrentRun, control: ConcurrentRun, cs: ConcurrentSchedule) -> list[str]:
    """One shard truncates twice: the call and one retry, no third call, 'truncated twice' disclosed."""
    return [*_shard_scenario(run, control, cs, "truncated"), *_calls(run, "assess", ["LLMTruncatedError"] * 2)]


def check_beh29(run: ConcurrentRun, control: ConcurrentRun, cs: ConcurrentSchedule) -> list[str]:
    """One shard raises: a partial review (exit 0), the failure disclosed, never a crash."""
    return _shard_scenario(run, control, cs, "failed")


def _merged_order(findings: Sequence[dict[str, Any]]) -> list[str]:
    return [f["id"] for f in sorted(findings, key=lambda f: (-SEVERITY_RANK.get(f.get("severity") or "", 0),
                                                              -float(f["confidence"])))]


def check_llm16(run: ConcurrentRun, control: ConcurrentRun, cs: ConcurrentSchedule) -> list[str]:
    """Refine is cut at refine_end: the merged findings stand, ordered by severity then confidence,
    none revised; the fallback is disclosed; the verdict is still assessed."""
    out = [*no_crash(run), *invariants(run), *verdict_assessed(run),
           *disclosed(run, "refine_fallback", deg_type="budget_or_deadline_hit")]
    got = run.faulted("refine")
    if got != [CUT_OUTCOME]:
        out.append(f"faulted refine calls {got}, expected [{CUT_OUTCOME!r}] (cut, not retried)")
    findings = (run.report or {}).get("findings", [])
    if [f["id"] for f in findings] != _merged_order(findings):
        out.append("findings not in merged order (severity, then confidence)")
    if [f["rank"] for f in findings] != list(range(1, len(findings) + 1)):
        out.append("finding ranks do not follow the merged order")
    out += [f"{f['id']} revised although refine was cut" for f in findings if f["provenance"]["phase"] == "revise"]
    return out


def check_llm17(run: ConcurrentRun, control: ConcurrentRun, cs: ConcurrentSchedule) -> list[str]:
    """Research is cut at the stage 1 end: stop reason deadline, the ledger keeps what it had and
    replays exactly, the cut is disclosed; the assess shards are not affected."""
    out = [*no_crash(run), *invariants(run), *verdict_assessed(run),
           *disclosed(run, "research_cut", deg_type="budget_or_deadline_hit"),
           *others_survive(run, control, ())]
    r = run.report or {}
    if r.get("stop_reason", {}).get("code") != "deadline":
        out.append(f"stop reason {r.get('stop_reason', {}).get('code')!r}, expected 'deadline'")
    got = run.faulted("research")
    if got != [CUT_OUTCOME]:
        out.append(f"faulted research calls {got}, expected [{CUT_OUTCOME!r}] (cut, not retried)")
    ledger = r.get("evidence_ledger", [])
    if not [e for e in ledger if e["source_type"] == "external"]:
        out.append("no external evidence kept from the rounds before the cut")
    if r and [e.model_dump(mode="json") for e in EvidenceLedger.load(RunDir(run.root)).entries()] != ledger:
        out.append("ledger.jsonl replay does not rebuild the report's evidence_ledger")
    return out


Check = Callable[[ConcurrentRun, ConcurrentRun, ConcurrentSchedule], list[str]]
CHECKS: dict[str, Check] = {"LLM-13": check_llm13, "LLM-14": check_llm14, "LLM-15": check_llm15,
                            "LLM-16": check_llm16, "LLM-17": check_llm17, "BEH-29": check_beh29}
