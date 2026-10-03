"""``report.md`` defects of sit_sample_tools_1 (docs/live_runs/sit_sample_tools_1/MEASUREMENT.md
defects 4 to 6): a severity count in the verdict prose that disagrees with the findings ("seven"
high where ``report.json`` holds six), the doubled version prefix ("vVersion 2.0"), and bullet
lists flattened into one paragraph. Pinned on the committed ``report.json`` of that run (read by
field names and counts only: no model text is printed or compared verbatim) and on the example
Review fixture.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sit_review_agent.models import Review
from sit_review_agent.phases.understand import normalise_version
from sit_review_agent.report.render import (
    _NUMBER_WORDS,
    _md,
    _one_line,
    reconcile_severity_counts,
    render_markdown,
    severity_counts,
    version_label,
)

RUN = Path(__file__).resolve().parents[1] / "docs" / "live_runs" / "sit_sample_tools_1"
BULLET = re.compile(r"(?m)^\s*(?:[-*]|\d{1,2}[.)])\s+\S")
COUNT = re.compile(r"\b(\d{1,3}|" + "|".join(_NUMBER_WORDS) + r")\s+(critical|high|medium|low)[- ]severity\b",
                   re.IGNORECASE)


def _number(word: str) -> int:
    return int(word) if word.isdigit() else _NUMBER_WORDS.index(word.lower())


def _counts_in(text: str) -> list[tuple[str, int]]:
    return [(m.group(2).lower(), _number(m.group(1))) for m in COUNT.finditer(text)]


def _section(md: str, heading: str) -> str:
    return md.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]


def _bullet_items(text: str) -> list[str]:
    return [_one_line(re.sub(r"^\s*[-*]\s+", "- ", ln.strip())) for ln in text.splitlines() if BULLET.match(ln)]


# =============================================================================== the live run


def live_review() -> Review:
    return Review.model_validate(json.loads((RUN / "report.json").read_text(encoding="utf-8")))


def test_live_run_severity_count_in_prose_is_computed_from_the_findings() -> None:
    review = live_review()
    counts = severity_counts(review)
    assert counts["high"] == 6                                         # report.json's own findings
    stated = _counts_in(review.verdict.rationale)
    assert ("high", 6) not in stated and any(sev == "high" for sev, _ in stated)   # the defect, as recorded
    md = render_markdown(review)
    fitness = _section(md, "Fitness for purpose")
    rendered = _counts_in(fitness)
    assert rendered and all(n == counts[sev] for sev, n in rendered), rendered


def test_live_run_version_has_one_prefix() -> None:
    review = live_review()
    raw = review.metadata.documents[0].version
    assert raw is not None and raw.lower().startswith("version")       # the model's wording, as recorded
    md = render_markdown(review)
    assert "vVersion" not in md
    assert f" v{normalise_version(raw)}" in md.split("\n## ", 1)[0]


def test_live_run_bullet_lists_survive_in_the_fitness_text_and_what_would_change() -> None:
    review = live_review()
    md = render_markdown(review)
    fitness = _section(md, "Fitness for purpose")
    lines = set(fitness.splitlines())
    for field in (review.verdict.rationale, review.verdict.what_would_change_it or ""):
        items = _bullet_items(field)
        assert items, "the recorded field holds a list"
        for item in items:
            text = reconcile_severity_counts(item, severity_counts(review))
            assert text in lines, "a list item is not on a line of its own"
            assert f" {text}" not in fitness.replace(f"\n{text}", "")    # never inlined after other text
    prose = [ln for ln in fitness.splitlines() if not ln.lstrip().startswith(("- ", "| "))]
    assert not any(" - " in ln for ln in prose), "a list was flattened into a paragraph"


# =============================================================================== the fixture


def fixture_review(review_dict: dict[str, Any]) -> Review:
    d = json.loads(json.dumps(review_dict))
    d["metadata"]["documents"][0]["version"] = "Version 3.1"
    d["verdict"]["rationale"] = ("Fit once the open items close. Eleven high-severity findings remain:\n"
                                 "- the reminder volume exceeds the provider limit\n"
                                 "- the region is not named\n"
                                 "  in the deployment section\n"
                                 "Both are cheap to fix.")
    d["verdict"]["what_would_change_it"] = "1. A published sending limit\n2. A named region"
    return Review.model_validate(d)


def test_fixture_count_version_and_lists(review_dict: dict[str, Any]) -> None:
    review = fixture_review(review_dict)
    counts = severity_counts(review)
    md = render_markdown(review)
    fitness = _section(md, "Fitness for purpose")
    word = _NUMBER_WORDS[counts["high"]].capitalize()
    assert f"{word} high-severity findings remain:" in fitness and "Eleven" not in fitness
    assert ("Fit once the open items close. " + f"{word} high-severity findings remain:\n\n"
            "- the reminder volume exceeds the provider limit\n"
            "- the region is not named in the deployment section\n\n"
            "Both are cheap to fix.") in fitness
    assert "What would change this verdict: \n\n1. A published sending limit\n2. A named region" in fitness
    assert " v3.1" in md and "vVersion" not in md


def test_text_without_a_list_renders_as_before() -> None:
    for text in ("one line", "two\nlines joined", "  spaced   out  ", "", None, "a - b - c"):
        assert _md(text) == _one_line(text)


def test_version_label_and_normalise() -> None:
    assert [version_label(v) for v in ("Version 2.0", "v2.0", "2.0", "Rev. 3", "Draft 3", "Validation 2", None)] \
        == ["v2.0", "v2.0", "v2.0", "v3", "Draft 3", "Validation 2", None]
    assert normalise_version("Document Version 1.4") == "1.4" and normalise_version("  ") is None


def test_counts_keep_the_prose_style() -> None:
    counts = {"critical": 0, "high": 6, "medium": 14, "low": 2}
    assert reconcile_severity_counts("seven high-severity and 3 low severity", counts) == \
        "six high-severity and 2 low severity"
    assert reconcile_severity_counts("Seven high-severity", counts) == "Six high-severity"
    assert reconcile_severity_counts("seven high risks", counts) == "seven high risks"   # not a severity count
