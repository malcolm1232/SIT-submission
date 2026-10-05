"""Re-assessment of an updated artefact (lab §1.5): every prior finding gets exactly one status.

Drives the fake-gateway fixture pair the rehearsal defects call for
(``docs/transcripts/session4/reassessment_rehearsal.md`` "Defects" 1 and 2): a v1 review of the
selftest fixture, then a v2 review of a changed copy with ``--previous`` (``previous_run``), with the
scripted assess and refine answers set per test. No model calls; real phases throughout.

The v2 copy changes section 4.1 only. Its scripted assess answer carries:

* the e-mail finding forward as ``still_open`` (prior ID != its own ID is checked in the report);
* the testing finding as ``new_in_update`` (anchored in 4.1, which changed: a regression);
* the strength as ``new_in_update`` (anchored in 11.3, unchanged: not a regression);
* the invented finding (dropped by verify) as ``partially_addressed`` of the prior testing finding, so
  that prior finding loses its only successor after refine and must still get a status.

The prior strength finding is carried by no draft, so refine must give it a status.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.clock import FakeClock
from sit_review_agent.invariants import check_all, check_INV_13
from sit_review_agent.orchestrator import RunRequest, run_review
from sit_review_agent.progress import NullProgress
from sit_review_agent.selftest import FIXTURE_DIR, fixture_gateway, selftest_config
from test_run_and_resume import tools_factory

PDF = FIXTURE_DIR / "design.pages.txt"
MAIL = "E-mail plan cannot send peak-day reminders"
TESTING = "Peak-day reminder volume is not tested"
STRENGTH = "Accessibility is verified, not just promised"
INVENTED = "Room cancellation window is unspecified"
V2_DOC = "DOC-design_v2"
WITHDRAW_NOTE = "Accessibility is no longer claimed as verified in v1.1, so the strength is not asserted."


def _v2(tmp: Path) -> Path:
    text = PDF.read_text(encoding="utf-8")
    old = "4.1 Load. Peak exam-week days generate about 5,000 bookings, each with one reminder."
    assert old in text
    out = tmp / "design_v2.pages.txt"
    out.write_text(text.replace(old, old + " Reminders are now sent in hourly batches."), encoding="utf-8")
    return out


class Recorder:
    """Wraps the fixture gateway: scripted delta answers for assess and refine, and the refine
    requests seen (conversation ID and brief text)."""

    def __init__(self, prior: dict[str, str], refine_answers: list[list[dict[str, Any]] | None],
                 reassessments: dict[str, dict[str, Any]] | None = None) -> None:
        self.prior = prior
        self.refine_answers = list(refine_answers)
        self.refine_requests: list[tuple[str, str]] = []
        self.reassessments = reassessments or {}
        self.verdict_briefs: list[str] = []

    def reassessment(self, title: str) -> dict[str, Any]:
        if title in self.reassessments:
            return self.reassessments[title]
        if title == MAIL:
            return {"prior_finding_id": self.prior[MAIL], "status": "still_open", "note": "Quota still unaddressed."}
        if title == INVENTED:
            return {"prior_finding_id": self.prior[TESTING], "status": "partially_addressed",
                    "note": "Some batching added."}
        return {"prior_finding_id": None, "status": "new_in_update", "note": None}

    def __call__(self, rd: Any, clock: Any, progress: Any) -> Any:
        gw: Any = fixture_gateway(rd, clock=clock)
        assess, refine = gw.script["assess"][0], gw.script["refine"][0]
        rec = self

        def delta_assess(ledger: list[dict[str, Any]], req: Any) -> Any:
            resp = assess(ledger, req)
            # The fixture's anchors name the v1 document; in v2 they cite the document under review.
            resp.parsed["findings"] = [dict(f, reassessment=rec.reassessment(str(f["title"])),
                                            doc_anchors=[dict(a, doc_id=V2_DOC) for a in f["doc_anchors"]])
                                       for f in resp.parsed["findings"]]
            resp.parsed["sound_areas"] = [dict(a, doc_anchors=[dict(x, doc_id=V2_DOC) for x in a["doc_anchors"]])
                                          for a in resp.parsed["sound_areas"]]
            return resp

        def delta_refine(ledger: list[dict[str, Any]], req: Any) -> Any:
            from sit_review_agent.selftest import _brief_text

            rec.refine_requests.append((str(req.conversation_id), _brief_text(req)))
            resp = refine(ledger, req)
            statuses = rec.refine_answers.pop(0) if rec.refine_answers else None
            if statuses is not None:
                resp.parsed["prior_statuses"] = statuses
            return resp

        verdict = gw.script["report"][0]

        def delta_verdict(ledger: list[dict[str, Any]], req: Any) -> Any:
            from sit_review_agent.selftest import _brief_text

            rec.verdict_briefs.append(_brief_text(req))
            return verdict(ledger, req)

        for phase, fn in (("assess", delta_assess), ("refine", delta_refine), ("report", delta_verdict)):
            queue = gw.script[phase]
            n = len(queue)
            queue.clear()
            queue.extend(fn for _ in range(n))
        return gw


async def _run(cfg: Any, run_id: str, pdf: Path, llm_factory: Any = None, progress: Any = None, **kw: Any) -> Any:
    factory = llm_factory or (lambda rd, clock, progress: fixture_gateway(rd, clock=clock))
    out = await run_review(RunRequest(pdf=pdf, config=cfg, run_id=run_id, **kw), llm_factory=factory,
                           tools_factory=tools_factory, clock=FakeClock(), progress=progress or NullProgress())
    assert out.exit_code == 0, (out.run_dir / "failure.json").read_text() if (out.run_dir / "failure.json").exists() \
        else out
    return out


@pytest.fixture
def prior_run(tmp_path: Path) -> tuple[Any, Any, dict[str, str]]:
    import asyncio

    cfg = selftest_config(tmp_path / "runs")
    v1 = asyncio.run(_run(cfg, "v1", PDF))
    report = json.loads((v1.run_dir / "report.json").read_text(encoding="utf-8"))
    return cfg, v1, {f["title"]: f["id"] for f in report["findings"]}


def _delta(tmp_path: Path, prior_run: tuple[Any, Any, dict[str, str]],
           refine_answers: list[list[dict[str, Any]] | None],
           reassessments: dict[str, dict[str, Any]] | None = None,
           progress: Any = None) -> tuple[dict[str, Any], str, Recorder, Path]:
    import asyncio

    cfg, v1, prior = prior_run
    rec = Recorder(prior, refine_answers, reassessments)
    out = asyncio.run(_run(cfg, "v2", _v2(tmp_path), rec, progress, previous_run=v1.run_dir))
    report = json.loads((out.run_dir / "report.json").read_text(encoding="utf-8"))
    return report, (out.run_dir / "report.md").read_text(encoding="utf-8"), rec, out.run_dir


def _table(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["prior_id"]: e for e in report["prior_findings"]}


def test_every_prior_finding_gets_exactly_one_status(tmp_path: Path, prior_run: Any) -> None:
    """Refine omits the uncarried prior finding, is asked once, and withdraws it with a reason; the
    prior finding whose only successor verify dropped is recorded still_open, not re-examined."""
    _, _, prior = prior_run
    withdrawn = [{"prior_finding_id": prior[STRENGTH], "status": "withdrawn_on_reassessment", "note": WITHDRAW_NOTE}]
    report, md, rec, run_dir = _delta(tmp_path, prior_run, [None, withdrawn])
    assert len(rec.refine_requests) == 2                                  # asked once, after the omission
    assert rec.refine_requests[1][0].endswith("-r1") and prior[STRENGTH] in rec.refine_requests[1][1]
    table = _table(report)
    assert sorted(table) == sorted(prior.values())                       # every prior finding, once
    by_title = {f["title"]: f for f in report["findings"]}
    mail = table[prior[MAIL]]
    assert (mail["status"], mail["finding_ids"], mail["re_examined"]) == ("still_open", [by_title[MAIL]["id"]], True)
    gone = table[prior[STRENGTH]]
    assert (gone["status"], gone["finding_ids"], gone["note"]) == ("withdrawn_on_reassessment", [], WITHDRAW_NOTE)
    lost = table[prior[TESTING]]
    assert (lost["status"], lost["finding_ids"], lost["re_examined"]) == ("still_open", [], False)
    assert "not re-examined" in lost["note"]
    events = [d["event"] for d in report["research_log"]["degradations"]]
    assert any("not re-examined" in e and prior[TESTING] in e for e in events), events
    assert [r.inv_id for r in check_all(report, run_dir) if not r.passed] == []
    assert check_INV_13(report, run_dir).passed


def test_a_status_still_missing_after_the_retry_is_recorded_not_dropped(tmp_path: Path, prior_run: Any) -> None:
    _, _, prior = prior_run
    report, _, rec, run_dir = _delta(tmp_path, prior_run, [None, None])
    assert len(rec.refine_requests) == 2
    table = _table(report)
    assert sorted(table) == sorted(prior.values())
    for pid in (prior[STRENGTH], prior[TESTING]):
        assert (table[pid]["status"], table[pid]["re_examined"]) == ("still_open", False)
        assert "not re-examined" in table[pid]["note"]
    events = [d["event"] for d in report["research_log"]["degradations"]]
    assert any("not re-examined" in e and prior[STRENGTH] in e for e in events), events
    assert check_INV_13(report, run_dir).passed


def test_inv_13_fails_when_a_prior_finding_has_no_status(tmp_path: Path, prior_run: Any) -> None:
    report, _, _, run_dir = _delta(tmp_path, prior_run, [None, None])
    assert check_INV_13(report, run_dir).passed
    report["prior_findings"] = report["prior_findings"][1:]
    res = check_INV_13(report, run_dir)
    assert not res.passed and "no status" in res.problems[0]


def test_regression_is_marked_from_the_two_texts(tmp_path: Path, prior_run: Any) -> None:
    report, md, _, _ = _delta(tmp_path, prior_run, [None, None])
    by_title = {f["title"]: f for f in report["findings"]}
    assert by_title[TESTING]["reassessment"]["status"] == "new_in_update"
    assert by_title[TESTING]["reassessment"]["regression"] is True        # anchored in 4.1, which changed
    assert by_title[STRENGTH]["reassessment"]["regression"] is False      # 11.3 is unchanged
    assert by_title[MAIL]["reassessment"]["regression"] is False
    assert f"{by_title[TESTING]['id']} {TESTING} (regression)" in md


def test_the_report_prints_both_ids_and_keys_the_delta_on_the_prior_id(tmp_path: Path, prior_run: Any) -> None:
    _, _, prior = prior_run
    report, md, _, _ = _delta(tmp_path, prior_run, [None, None])
    mail = next(f for f in report["findings"] if f["title"] == MAIL)
    assert mail["reassessment"]["prior_finding_id"] == prior[MAIL]
    section = md[md.index("## Changes since the previous version"):]
    assert f"{mail['id']}, was {prior[MAIL]}" in section
    assert f"was {prior[TESTING]} (no finding in this review)" in section
    assert "3 prior findings, each with exactly one status below (2 recorded as still open" in section


def test_a_full_review_has_an_empty_delta_table(tmp_path: Path, prior_run: Any) -> None:
    _, v1, _ = prior_run
    report = json.loads((v1.run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["prior_findings"] == []
    assert check_INV_13(report, v1.run_dir).passed


@pytest.mark.parametrize("break_it, message", [
    (lambda r: r["prior_findings"].append(dict(r["prior_findings"][0])), "more than one status"),
    (lambda r: r["prior_findings"][0].update(status="withdrawn_on_reassessment", finding_ids=[], note=" "),
     "needs a one-line reason"),
    (lambda r: r["prior_findings"][1].update(finding_ids=list(r["prior_findings"][0]["finding_ids"]),
                                             re_examined=True), "does not carry it forward"),
    (lambda r: r["prior_findings"][0].update(finding_ids=[]), "not in its entry"),
    (lambda r: r["prior_findings"][1].update(status="resolved"), "not re-examined is still_open"),
])
def test_the_review_model_rejects_a_broken_delta_table(tmp_path: Path, prior_run: Any, break_it: Any,
                                                       message: str) -> None:
    from pydantic import ValidationError

    from sit_review_agent.invariants import spec_validator
    from sit_review_agent.models import Review

    report, _, _, _ = _delta(tmp_path, prior_run, [None, None])
    Review.model_validate(report)
    order = sorted(report["prior_findings"], key=lambda e: not e["finding_ids"])   # the carried entry first
    report["prior_findings"] = order
    break_it(report)
    with pytest.raises(ValidationError, match=message):
        Review.model_validate(report)
    if message in ("needs a one-line reason", "not re-examined is still_open"):
        assert list(spec_validator("Review").iter_errors(report))       # the schema says the same


# ------------------------------------------------- card A3: a resolved prior is a delta-table row only

RESOLVED_NOTE = "Hourly batching and a load test now cover peak-day reminders."


def _ids_in_lists(node: Any) -> set[str]:
    """Every ID in a ``finding_ids`` or ``related_finding_ids`` list of a JSON tree."""
    out: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("finding_ids", "related_finding_ids") and isinstance(v, list):
                out |= set(v)
            else:
                out |= _ids_in_lists(v)
    elif isinstance(node, list):
        for v in node:
            out |= _ids_in_lists(v)
    return out


def test_a_resolved_prior_is_a_table_row_not_a_finding(tmp_path: Path, prior_run: Any) -> None:
    """One finding reassessed resolved (prior TESTING), one still open (prior MAIL): the resolved one
    leaves the findings, the verdict input and the counts, and its prior row is resolved with no
    successor, re-examined, with the carrier's note."""
    from sit_review_agent.models import Review
    from sit_review_agent.phases.report import _severity_counts

    _, _, prior = prior_run
    withdrawn = [{"prior_finding_id": prior[STRENGTH], "status": "withdrawn_on_reassessment", "note": WITHDRAW_NOTE}]
    progress = NullProgress()
    report, _, rec, run_dir = _delta(tmp_path, prior_run, [withdrawn], {
        TESTING: {"prior_finding_id": prior[TESTING], "status": "resolved", "note": RESOLVED_NOTE},
        INVENTED: {"prior_finding_id": None, "status": "new_in_update", "note": None}}, progress)
    titles = [f["title"] for f in report["findings"]]
    assert TESTING not in titles and MAIL in titles
    moved_map = report["run_manifest"]["extra"]["finding_ids"]["report"]
    assert list(moved_map.values()) == ["resolved, moved to the prior table"]
    moved = next(iter(moved_map))
    assert moved not in {f["id"] for f in report["findings"]}

    table = _table(report)
    assert sorted(table) == sorted(prior.values())
    done = table[prior[TESTING]]
    assert (done["status"], done["finding_ids"], done["re_examined"], done["note"]) == \
        ("resolved", [], True, RESOLVED_NOTE)
    mail = table[prior[MAIL]]
    mail_id = next(f["id"] for f in report["findings"] if f["title"] == MAIL)
    assert (mail["status"], mail["finding_ids"], mail["re_examined"]) == ("still_open", [mail_id], True)

    # the verdict call saw only the open findings; the counts the verdict event gives exclude the moved one
    assert TESTING not in rec.verdict_briefs[-1] and MAIL in rec.verdict_briefs[-1]
    verdict_event = next(e for e in progress.records if e.event == "verdict")
    assert verdict_event.fields["findings"] == len(report["findings"])
    assert verdict_event.fields["by_severity"] == _severity_counts(Review.model_validate(report).findings)
    assert f"; {len(report['findings'])} findings," in verdict_event.message
    assert any(e.event == "resolved_to_prior_table" and e.fields["finding_ids"] == [moved]
               for e in progress.records)

    # no dangling reference to the moved finding
    for section in ("unresolved", "sound_areas", "verdict"):
        assert moved not in _ids_in_lists(report[section]), section
    assert [r.inv_id for r in check_all(report, run_dir) if not r.passed] == []
    assert check_INV_13(report, run_dir).passed


def test_a_still_open_carrier_keeps_the_row_open_when_another_is_resolved(tmp_path: Path, prior_run: Any) -> None:
    """Two carriers of the prior MAIL finding, one resolved and one still open: the still-open
    carrier stays and gives the row; the resolved one leaves the findings."""
    _, _, prior = prior_run
    statuses = [{"prior_finding_id": prior[STRENGTH], "status": "withdrawn_on_reassessment", "note": WITHDRAW_NOTE},
                {"prior_finding_id": prior[TESTING], "status": "still_open", "note": "Not tested yet."}]
    report, _, _, run_dir = _delta(tmp_path, prior_run, [statuses], {
        TESTING: {"prior_finding_id": prior[MAIL], "status": "resolved", "note": RESOLVED_NOTE},
        INVENTED: {"prior_finding_id": None, "status": "new_in_update", "note": None}})
    titles = [f["title"] for f in report["findings"]]
    assert TESTING not in titles and MAIL in titles
    mail_id = next(f["id"] for f in report["findings"] if f["title"] == MAIL)
    mail = _table(report)[prior[MAIL]]
    assert (mail["status"], mail["finding_ids"], mail["re_examined"]) == ("still_open", [mail_id], True)
    assert [r.inv_id for r in check_all(report, run_dir) if not r.passed] == []
    assert check_INV_13(report, run_dir).passed
