"""The concurrent-stage scenarios (``faults_concurrent/``, latency redesign of 2026-10-03).

Their schedules execute only against the concurrent orchestrator (W2), which is not in this tree, so
here the loader and the oracles are tested on fixtures: each fixture is the fault-free control run
directory (scripted fake model, invented document) copied and edited into the outcome the design
promises for that fault (a shard's findings removed and its criteria marked not assessed, the
degradation and limitation added, the faulted calls appended to ``llm.jsonl``). The oracle must pass
on that fixture and fail on each broken variant. ``test_concurrent_scenario_end_to_end`` is the
end-to-end form; it is skipped until the integration pass sets ``AWAITING_INTEGRATION`` to false.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import oracles
import pytest
from concurrent_oracles import CHECKS, ConcurrentRun, _merged_order, is_not_assessed, mark_not_assessed
from concurrent_schedules import ConcurrentSchedule, concurrent_files, load_concurrent_schedule, schedule_path
from robustness_coverage import AWAITING_INTEGRATION, CONCURRENT, COVERAGE
from robustness_harness import RunRecord, Scenario, run

from sit_review_agent.report.coverage import build_coverage

SIDS = sorted(CONCURRENT)
#: The shard each schedule faults, in launch order of the committed config/agent.yaml.
TARGETS = {"LLM-13": (2, "claims_and_assumptions"), "LLM-14": (0, "intent_and_fitness"),
           "LLM-15": (1, "requirements_and_consistency"), "BEH-29": (3, "risk_and_operations"),
           "LLM-16": None, "LLM-17": None}


# ============================================================================= fixture builders


def _read(root: Path, name: str) -> Any:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _write(root: Path, name: str, data: Any) -> None:
    (root / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def drop_criteria(root: Path, lost: tuple[str, ...]) -> list[str]:
    """Remove the findings whose criteria all lie in ``lost`` and mark ``lost`` not assessed."""
    found = build_coverage(root).criterion_findings
    meta = _read(root, "state.json").get("finding_meta") or {}
    gone = sorted({fid for c in lost for fid in found.get(c, []) if set(meta[fid]["criterion_ids"]) <= set(lost)})
    r = _read(root, "report.json")
    r["findings"] = [f for f in r["findings"] if f["id"] not in gone]
    for i, f in enumerate(r["findings"], 1):
        f["rank"] = i
    for owner, key in ((r["verdict"], "conditions"), (r["verdict"], "per_objective"), (r, "unresolved")):
        kept = []
        for c in owner[key]:                                             # an item that only cited a removed
            ids = [x for x in c["finding_ids"] if x not in gone]         # finding goes with it
            if ids or not c["finding_ids"]:
                kept.append({**c, "finding_ids": ids})
        owner[key] = kept
    if not r["verdict"]["conditions"] and r["verdict"]["label"] == "fit_with_conditions":
        r["verdict"]["conditions"] = [{"text": "Resolve the remaining findings (fixture).",   # the verdict call
                                       "finding_ids": [r["findings"][0]["id"]]}]          # cites what is left
    for s in r["sound_areas"]:
        s["related_finding_ids"] = [x for x in s["related_finding_ids"] if x not in gone]
    _write(root, "report.json", r)
    st = _read(root, "state.json")
    for row in st["coverage"]:
        if row["criterion_id"] in lost:
            mark_not_assessed(row)
    st["finding_meta"] = {k: v for k, v in st["finding_meta"].items() if k not in gone}
    _write(root, "state.json", st)
    return gone


def add_degradation(root: Path, dtype: str, event: str) -> str:
    r = _read(root, "report.json")
    degs = r["research_log"]["degradations"]
    did = f"DEG-{len(degs) + 1:03d}"
    degs.append({"id": did, "type": dtype, "event": event, "impact": "part of the review is missing; disclosed"})
    r["limitations"].append({"text": f"{event} (invented fixture text)", "degradation_ids": [did]})
    _write(root, "report.json", r)
    return did


def add_faulted_calls(root: Path, phase: str, outcomes: list[str]) -> None:
    with (root / "llm.jsonl").open("a", encoding="utf-8") as fh:
        for o in outcomes:
            fh.write(json.dumps({"call_id": None, "phase": phase, "outcome": o, "fault": "injected"}) + "\n")


def edit_report(root: Path, fn: Callable[[dict[str, Any]], None]) -> None:
    r = _read(root, "report.json")
    fn(r)
    _write(root, "report.json", r)


def salvaged(sid: str, control: RunRecord, cs: ConcurrentSchedule, tmp: Path) -> ConcurrentRun:
    """The control run directory edited into the outcome the design promises under ``sid``."""
    root = tmp / f"fixture-{sid}"
    shutil.copytree(control.run_dir.root, root)
    t = cs.targets[0] if cs.targets else None
    if sid == "LLM-13":
        assert t is not None
        drop_criteria(root, t.criteria)
        add_degradation(root, "budget_or_deadline_hit",
                        f"assess shard {t.name} cut at the stage 1 limit (265 s); its criteria are not assessed")
        add_faulted_calls(root, "assess", ["LLMDeadlineError"])
    elif sid == "LLM-14":
        assert t is not None
        drop_criteria(root, t.criteria)
        add_degradation(root, "other", f"the model declined assess shard {t.name} twice; its criteria are not assessed")
        add_faulted_calls(root, "assess", ["LLMRefusalError"] * 2)
    elif sid == "LLM-15":
        assert t is not None
        drop_criteria(root, t.criteria)
        add_degradation(root, "other", f"assess shard {t.name}: the answer was truncated twice at the output cap")
        add_faulted_calls(root, "assess", ["LLMTruncatedError"] * 2)
    elif sid == "BEH-29":
        assert t is not None
        drop_criteria(root, t.criteria)
        add_degradation(root, "other", f"assess shard {t.name} failed with an error; its criteria are not assessed")
    elif sid == "LLM-16":
        def merged(r: dict[str, Any]) -> None:
            order = _merged_order(r["findings"])
            r["findings"] = sorted(r["findings"], key=lambda f: order.index(f["id"]))
            for i, f in enumerate(r["findings"], 1):
                f["rank"] = i
                f["provenance"]["phase"] = "assess"
        edit_report(root, merged)
        add_degradation(root, "budget_or_deadline_hit",
                        "refine cut at the refine limit (465 s): the merged findings stand, by severity and confidence")
        add_faulted_calls(root, "refine", ["LLMDeadlineError"])
    elif sid == "LLM-17":
        edit_report(root, lambda r: r.update(stop_reason={"code": "deadline", "group": "cap",
                                                          "detail": "research cut at the stage 1 limit"}))
        add_degradation(root, "budget_or_deadline_hit", "research cut at the stage 1 limit (265 s); the ledger "
                                                        "keeps the evidence of the rounds before it")
        add_faulted_calls(root, "research", ["LLMDeadlineError"])
    return ConcurrentRun(root, 0, "")


@pytest.fixture(scope="module")
def schedules() -> dict[str, ConcurrentSchedule]:
    return {sid: load_concurrent_schedule(schedule_path(sid)) for sid in SIDS}


def _check(sid: str, fixture: ConcurrentRun, control: RunRecord, cs: ConcurrentSchedule) -> list[str]:
    return CHECKS[sid](fixture, ConcurrentRun.from_record(control), cs)


# ============================================================================= schedules and registry


def test_not_assessed_is_the_orchestrators_form_and_not_a_model_verdict() -> None:
    """The contract (concurrent_oracles docstring): outcome ``not_applicable`` with a note starting
    "not assessed" is a criterion no shard assessed; a criterion the model itself reported not
    applicable (any other note) is an assessment and never counts as lost."""
    row: dict[str, Any] = {"criterion_id": "x", "outcome": "no_issue", "finding_ids": [], "note": "checked"}
    mark_not_assessed(row, "the shard was cut")
    assert row["outcome"] == "not_applicable" and row["note"].startswith("not assessed") and is_not_assessed(row)
    assert not is_not_assessed({"outcome": "not_applicable", "note": "not applicable: no external API in scope"})
    assert not is_not_assessed({"outcome": "not_applicable", "note": ""})
    assert not is_not_assessed({"outcome": "no_issue", "note": "not assessed: fixture"})
    assert is_not_assessed(("not_applicable", "Not assessed: out of time")) and not is_not_assessed(("findings", ""))


def test_every_concurrent_schedule_is_registered_and_checked() -> None:
    assert concurrent_files() == set(CONCURRENT) == set(CHECKS) == set(TARGETS)
    assert not set(CONCURRENT) & set(COVERAGE)                           # new IDs, not scenarios.md P0 rows


@pytest.mark.parametrize("sid", SIDS)
def test_schedule_resolves_to_the_targeted_shard(sid: str, schedules: dict[str, ConcurrentSchedule]) -> None:
    cs = schedules[sid]
    assert cs.id == sid and cs.schedule.sha256 and len(cs.shards) == 4
    want = TARGETS[sid]
    assert [(t.index, t.name) for t in cs.targets] == ([want] if want else [])
    for rule in cs.schedule.llm:                                         # nothing of the shard keys is left
        assert not (rule.match.model_extra or {})
    text = cs.agent_yaml()
    assert "shard_call" not in text and "shard:" not in text.replace("shard: 3", "")


def test_control_has_findings_in_and_outside_the_faulted_shards(control: RunRecord,
                                                                 schedules: dict[str, ConcurrentSchedule]) -> None:
    """The fixtures prove something only if the control run has findings both in a faulted shard (so
    its loss is visible) and outside it (so 'others survive' is not vacuous)."""
    found = build_coverage(control.run_dir.root).criterion_findings
    for sid in ("LLM-13", "LLM-15"):
        t = schedules[sid].targets[0]
        assert any(found.get(c) for c in t.criteria), sid
        assert any(ids for c, ids in found.items() if c not in t.criteria), sid


# ============================================================================= oracles on fixtures


@pytest.mark.parametrize("sid", SIDS)
def test_oracle_passes_on_the_salvaged_fixture(sid: str, control: RunRecord, tmp_path: Path,
                                               schedules: dict[str, ConcurrentSchedule]) -> None:
    cs = schedules[sid]
    fixture = salvaged(sid, control, cs, tmp_path)
    assert _check(sid, fixture, control, cs) == []


def _undisclose(root: Path) -> None:
    def fn(r: dict[str, Any]) -> None:
        r["research_log"]["degradations"].pop()
        r["limitations"].pop()
    edit_report(root, fn)


def _uncite(root: Path) -> None:
    edit_report(root, lambda r: r["limitations"].pop())


def _lose_other_shard(root: Path) -> None:
    drop_criteria(root, ("fitness_for_objectives",))                     # shard 0's finding


def _criteria_still_assessed(root: Path) -> None:
    st = _read(root, "state.json")
    for row in st["coverage"]:
        if is_not_assessed(row):
            row["outcome"], row["note"] = "no_issue", "checked: no issue (broken fixture)"
    _write(root, "state.json", st)


def _not_assessed_verdict(root: Path) -> None:
    edit_report(root, lambda r: r["verdict"].update(label="not_assessed"))


def _crashed(root: Path) -> None:
    (root / "failure.json").write_text(json.dumps({"exit_code": 4, "completed_phases": []}), encoding="utf-8")


def _partial(root: Path) -> None:
    (root / "report.partial.md").write_text("# Partial report (fixture)\n", encoding="utf-8")


def _traceback(root: Path) -> None:
    (root / "progress.log").write_text("Traceback (most recent call last):\n", encoding="utf-8")


def _swap_first_two(root: Path) -> None:
    def fn(r: dict[str, Any]) -> None:
        f = r["findings"]
        f[0], f[1] = f[1], f[0]
        f[0]["rank"], f[1]["rank"] = 1, 2
    edit_report(root, fn)


def _revised(root: Path) -> None:
    edit_report(root, lambda r: r["findings"][0]["provenance"].update(phase="revise"))


def _decision_stop(root: Path) -> None:
    edit_report(root, lambda r: r.update(stop_reason={"code": "sufficient_evidence", "group": "decision",
                                                      "detail": None}))


def _no_external(root: Path) -> None:
    edit_report(root, lambda r: r.update(evidence_ledger=[e for e in r["evidence_ledger"]
                                                          if e["source_type"] != "external"]))


def _calls(phase: str, outcomes: list[str]) -> Callable[[Path], None]:
    return lambda root: add_faulted_calls(root, phase, outcomes)


#: (scenario, how the fixture is broken, exit code, a substring of the expected problem)
BROKEN: list[tuple[str, Callable[[Path], None], int, str]] = [
    ("LLM-13", _undisclose, 0, "no degradation of type budget_or_deadline_hit naming claims_and_assumptions"),
    ("LLM-13", _lose_other_shard, 0, "lost"),
    ("LLM-13", _criteria_still_assessed, 0, "expected 'not_assessed'"),
    ("LLM-13", _calls("assess", ["LLMDeadlineError"]), 0, "cut, not retried"),
    ("LLM-13", _not_assessed_verdict, 0, "verdict not_assessed"),
    ("LLM-14", _calls("assess", ["LLMRefusalError"]), 0, "faulted assess calls"),
    ("LLM-14", _undisclose, 0, "naming intent_and_fitness"),
    ("LLM-15", _crashed, 4, "exit 4"),
    ("LLM-15", _lose_other_shard, 0, "lost"),
    ("BEH-29", _partial, 0, "report.partial.md written"),
    ("BEH-29", _uncite, 0, "not cited by a limitation"),
    ("BEH-29", _traceback, 0, "traceback in progress.log"),
    ("LLM-16", _swap_first_two, 0, "merged order"),
    ("LLM-16", _revised, 0, "revised although refine was cut"),
    ("LLM-16", _undisclose, 0, "no degradation of type budget_or_deadline_hit"),
    ("LLM-17", _decision_stop, 0, "expected 'deadline'"),
    ("LLM-17", _no_external, 0, "no external evidence"),
    ("LLM-17", _calls("research", ["LLMTimeoutError"]), 0, "faulted research calls"),
]


@pytest.mark.parametrize(("sid", "breaker", "code", "needle"), BROKEN,
                         ids=[f"{s}-{b.__name__.strip('_') if b.__name__ != '<lambda>' else 'calls'}"
                              for s, b, _, _ in BROKEN])
def test_oracle_fails_on_a_broken_fixture(sid: str, breaker: Callable[[Path], None], code: int, needle: str,
                                          control: RunRecord, tmp_path: Path,
                                          schedules: dict[str, ConcurrentSchedule]) -> None:
    cs = schedules[sid]
    fixture = salvaged(sid, control, cs, tmp_path)
    breaker(fixture.root)
    problems = _check(sid, ConcurrentRun(fixture.root, code, ""), control, cs)
    assert any(needle in p for p in problems), problems


def test_invariants_are_part_of_every_oracle(control: RunRecord, tmp_path: Path,
                                             schedules: dict[str, ConcurrentSchedule]) -> None:
    """A degradation no limitation cites fails INV-07 through the oracle's ``check_all`` call."""
    for sid in SIDS:
        fixture = salvaged(sid, control, schedules[sid], tmp_path / sid)
        add_degradation(fixture.root, "other", "an extra event (fixture)")
        edit_report(fixture.root, lambda r: r["limitations"].pop())
        problems = _check(sid, fixture, control, schedules[sid])
        assert any(p.startswith("INV-07:") for p in problems), (sid, problems)


# ============================================================================= end to end (integration pass)


@pytest.mark.skipif(AWAITING_INTEGRATION, reason="awaiting integration: the concurrent orchestrator (W2) is not "
                                                 "in this tree; README.md 'Concurrent stage 1 scenarios'")
@pytest.mark.parametrize("sid", SIDS)
def test_concurrent_scenario_end_to_end(sid: str, tmp_path: Path, control: RunRecord, results_sink: Any,
                                        schedules: dict[str, ConcurrentSchedule]) -> None:
    cs = schedules[sid]
    resolved = tmp_path / f"{sid}.resolved.yaml"
    resolved.write_text(cs.agent_yaml(), encoding="utf-8")
    with results_sink.row(sid, notes=CONCURRENT[sid].how[:120]) as row:
        # the scheduling clock: concurrent waits overlap as on a wall clock (a hang in one shard does
        # not move the clock for the shards that have not started their call)
        rec = run(Scenario(id=sid, faults=str(resolved), overrides={"profile": "demo"}, clock="scheduling"),
                  tmp_path / "v0")
        oracles.assert_oracles(rec)
        problems = CHECKS[sid](ConcurrentRun.from_record(rec), ConcurrentRun.from_record(control), cs)
        assert not problems, problems
        row.duration_s, row.artefacts = rec.wall_s, f"<pytest tmp>/runs/{rec.run_dir.root.name}"
        row.key_metric, row.value, row.threshold = "oracle problems", 0, "== 0"
