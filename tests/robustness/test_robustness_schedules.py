"""The fault schedules and the coverage table: every ``faults/*.yaml`` loads through the agent's own
loader and resolves through ``sit-review run --faults <ID>``; every fixture a schedule names exists;
the coverage registry, the README table, the scenario cases and scenarios.md agree on the 81 P0
IDs; the cassettes are keyed correctly; no fixture holds a secret."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from robustness_coverage import COVERAGE, p0_rows, schedule_files
from robustness_harness import CASSETTES, FAULTS_DIR, HERE
from test_robustness_scenarios import CASES

from sit_review_agent.cli import _resolve_faults
from sit_review_agent.paths import repo_root
from sit_review_agent.tools.cassette import cassette_key
from sit_review_agent.tools.faults import FaultType, load_fault_schedule
from sit_review_agent.tools.policy import CANARY_RE, SECRET_PATTERNS

SCHEDULES = sorted(FAULTS_DIR.glob("*.yaml"))
KIND_LABEL = {"offline": "offline", "laptop": "laptop", "not_schedule": "not a schedule"}


@pytest.mark.parametrize("path", SCHEDULES, ids=[p.stem for p in SCHEDULES])
def test_schedule_loads_and_resolves(path: Path) -> None:
    sched = load_fault_schedule(path)                                    # the agent's loader (ConfigError if bad)
    assert sched.id == path.stem and sched.description and sched.sha256
    assert sched.mcp or sched.llm or sched.network or sched.process
    assert _resolve_faults(path.stem) == repo_root() / "tests" / "robustness" / "faults" / path.name
    for rule in [*sched.mcp, *sched.llm]:
        fixture = (rule.fault.model_extra or {}).get("fixture") or (rule.fault.model_extra or {}).get("tools_list")
        if fixture:
            assert (repo_root() / fixture).is_file(), fixture
    for spec in sched.process:                                           # applied by the harness (README)
        assert spec.type in (FaultType.RAISE_IN_STAGE, FaultType.SIGINT_IN_STAGE, FaultType.CLOCK_JUMP)
        assert (spec.model_extra or {}).get("stage")


def test_every_schedule_is_a_p0_scenario_and_registered() -> None:
    files = schedule_files()
    assert files <= set(p0_rows())
    assert files == {sid for sid, c in COVERAGE.items() if c.schedule}


def test_coverage_registry_is_exactly_the_p0_scenarios() -> None:
    rows = p0_rows()
    assert len(rows) == 81                                               # scenarios.md "Counts" (README §9 parser)
    assert set(COVERAGE) == set(rows)
    for sid, c in COVERAGE.items():
        assert c.kind in KIND_LABEL, sid
        if c.kind == "laptop":
            assert c.laptop, sid
        if c.kind == "not_schedule":
            assert c.covered_by, sid


def test_offline_cases_match_the_registry() -> None:
    cases = {c.id for c in CASES}
    passing = {sid for sid, c in COVERAGE.items() if c.kind == "offline" and not c.decision}
    assert cases == passing                                              # every offline P0 scenario runs
    assert not cases & {sid for sid, c in COVERAGE.items() if c.decision}   # needs-decision ones do not


def test_readme_table_lists_every_p0_scenario_with_its_coverage() -> None:
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    found: dict[str, list[str]] = {}
    for line in readme.splitlines():
        m = re.match(r"^\| ([A-Z]+-\d\d) \|", line)
        if m:
            found[m.group(1)] = [c.strip() for c in line.strip("|").split("|")]
    assert set(found) == set(COVERAGE)
    for sid, cells in found.items():
        c = COVERAGE[sid]
        assert cells[3] == KIND_LABEL[c.kind] + (" (needs decision)" if c.decision else ""), (sid, cells[3])
        assert cells[4] == ("yes" if c.schedule else "-"), sid


def test_cassettes_are_keyed_by_their_arguments() -> None:
    files = sorted((CASSETTES / "tools").rglob("*.json"))
    assert files
    for f in files:
        rec = json.loads(f.read_text(encoding="utf-8"))
        key = cassette_key(rec["server"], rec["tool"], rec["args"])
        assert f.stem == rec["key"] == key, f
        assert f.parent.name == rec["tool"] and f.parent.parent.name == rec["server"]
    listed = {p.stem for p in (CASSETTES / "tools_list").glob("*.json")}
    assert listed == {"mcp-internet-search", "mcp-research-information"}


def test_fixtures_hold_no_secret() -> None:
    """OPS-02 for this folder: no key-shaped value or canary in a schedule, fixture or cassette (the
    canary constants live only in robustness_harness.py, and they are fake)."""
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or p.suffix not in (".yaml", ".json", ".md", ".csv", ".txt"):
            continue
        text = p.read_text(encoding="utf-8")
        assert not CANARY_RE.search(text) or p.suffix == ".md", p        # the README names the canary format
        for label, pat in SECRET_PATTERNS:
            assert not pat.search(text), (p, label)
        assert not re.search(r"X-API-Key\s*[:=]\s*\S{8,}", text, re.IGNORECASE), p
