"""A run given a deadline other than its profile's own run length (USER_DECISIONS #48, the owner on 5 Oct 2026:
"yes fix it"): the three stage limits AND the two reserves scale by the same factor, in one place
(``config.StopRulesConfig.effective``), which ``load_config`` applies and every reader goes through; a run at its
profile's own deadline is unchanged; a stage left less than one model attempt is named before the first call."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from sit_review_agent.config import ConfigOverrides, load_config
from sit_review_agent.paths import config_dir
from test_cli_kruns import PDF, base, cfgdir, invoke  # noqa: F401 - cfgdir is a fixture

PACKAGE = Path(__file__).resolve().parents[1] / "agent" / "sit_review_agent"

#: deadline -> (stage limits, report reserve, refine reserve, research end), from the shipped profiles.
DEMO = {
    540: ((264, 465, 529), 75, 200, 264),       # the former 540 s profile's clock (265 / 465 / 530, 75, 200)
    300: ((147, 258, 294), 41, 111, 147),
    900: ((441, 775, 883), 125, 334, 441),      # its own deadline: as set
    1800: ((882, 1550, 1766), 250, 668, 882),
}
DEFAULT = {
    540: ((423, 513, 531), 27, 90, 423),
    300: ((235, 285, 295), 15, 50, 235),
    900: ((705, 855, 885), 45, 150, 705),
    1800: ((1410, 1710, 1770), 90, 300, 1410),
    3600: ((2820, 3420, 3540), 180, 600, 2820),  # its own deadline: as set
}


@pytest.mark.parametrize("profile,table", [("demo", DEMO), (None, DEFAULT)])
def test_limits_and_reserves_scale_together(profile: str | None, table: dict) -> None:
    for d, (limits, report, refine, research) in table.items():
        sr = load_config(overrides=ConfigOverrides(profile=profile, deadline_seconds=d)).stop_rules
        got = (tuple(sr.stage_limits_s.as_dict().values()), sr.report_reserve_seconds, sr.refine_reserve_seconds,
               sr.research_end_s())
        assert got == (limits, report, refine, research), (profile, d, got)
        own = sr.planned_seconds() == d and sr.scaled_from is None
        assert own == (d == (900 if profile == "demo" else 3600)), (profile, d)
        if not own:
            # the split the profile encodes is kept: refine still ends a report reserve before the deadline
            assert sr.stage_limits_s.refine_end <= d - sr.report_reserve_seconds
            assert sr.scaled_from is not None and sr.scaled_from.scaled_from is None
            note = sr.scaling_note()
            assert note is not None and f"so research ends by {research} s" in note


def _profiles() -> list[str | None]:
    return [None, *sorted(p.stem for p in (config_dir() / "profiles").glob("*.yaml"))]


@pytest.mark.parametrize("profile", _profiles())
def test_a_run_at_its_profiles_own_deadline_is_unchanged(profile: str | None) -> None:
    """Every profile in config/profiles (and the default): loaded as is, or with ``--deadline`` equal to its own
    deadline, the stop rules dump byte for byte as the merged files give them, nothing is scaled, and the
    effective config's hash is the one the rules would have without the scaling step."""
    plain = load_config(overrides=ConfigOverrides(profile=profile))
    sr = plain.stop_rules
    again = load_config(overrides=ConfigOverrides(profile=profile, deadline_seconds=sr.deadline_seconds)).stop_rules
    assert sr.scaled_from is None and sr.effective() is sr and sr.scaling_note() is None
    assert again.model_dump_json() == sr.model_dump_json()
    assert sr.planned_seconds() >= sr.deadline_seconds > sr.stage_limits_s.verdict_end


def test_every_reader_of_the_reserves_goes_through_the_one_computation() -> None:
    """No module reads the reserves or the stage limits off ``config.stop_rules`` without ``.effective()``, and
    no second copy of the scaling arithmetic exists (``deadline / planned`` appears in config.py only)."""
    pattern = re.compile(r"stop_rules\.(report_reserve_seconds|refine_reserve_seconds|stage_limits_s)")
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        if path.name == "config.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line) and not line.lstrip().startswith(("#", "``", '"""')) and "``" not in line:
                offenders.append(f"{path.relative_to(PACKAGE)}:{n}: {line.strip()}")
    assert offenders == []
    scaling = [p.relative_to(PACKAGE) for p in PACKAGE.rglob("*.py")
               if re.search(r"/\s*planned\b|planned_seconds\(\)\s*$", p.read_text(encoding="utf-8"))]
    assert [str(p) for p in scaling] == ["config.py"]


def test_the_run_says_so_before_its_first_model_call(cfgdir: Path) -> None:  # noqa: F811
    """A deadline too short for a stage to start one model attempt (10 s, llm.runtime.MIN_ATTEMPT_S): the run
    names that stage in a WARN line, after the scaling line and before any model call is opened."""
    res = invoke(["review", str(PDF), *base(cfgdir), "--deadline", "30", "--run-id", "tight"])
    assert "WARN deadline 30 s leaves refine 5 s, less than one model attempt" in res.output
    assert "WARN deadline 30 s leaves the verdict call 1 s, less than one model attempt" in res.output
    evs = [json.loads(ln) for ln in (cfgdir.parent / "runs" / "tight" / "progress.jsonl").read_text(
        encoding="utf-8").splitlines()]
    kinds = [(e["type"], e["message"]) for e in evs]
    first_call = next(i for i, (t, _) in enumerate(kinds) if t == "call_opened")
    warned = [i for i, (t, m) in enumerate(kinds) if t == "deadline_warning" and "less than one model attempt" in m]
    assert len(warned) == 2 and max(warned) < first_call


def test_the_band_kept_as_set_is_verdict_end_plus_one_to_the_planned_run() -> None:
    """Demo (verdict_end 883 s, planned 900 s): 884 to 900 s keep limits and reserves as set; 883 s and 901 s
    scale, down and up, both limits and reserves."""
    def at(d: int) -> object:
        return load_config(overrides=ConfigOverrides(profile="demo", deadline_seconds=d)).stop_rules

    for d in (884, 900):
        assert at(d).scaled_from is None and at(d).report_reserve_seconds == 125
    for d in (883, 901):
        sr = at(d)
        assert sr.scaled_from is not None and sr.scaled_from.deadline_seconds == 900, d
    assert at(901).refine_reserve_seconds == 334 and "scaled up by 901/900" in (at(901).scaling_note() or "")
    assert at(883).refine_reserve_seconds == int(334 * 883 / 900) == 327
