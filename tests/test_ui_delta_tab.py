"""The Delta tab (rehearsal defects 3 and 4, ``docs/transcripts/session4/reassessment_rehearsal.md``).

* Its rows show the prior ID, this review's ID, the status, the re-assessment note and the
  regression mark ("new (regression)"), keyed on the prior review's IDs (``report.prior_findings``).
* A run with no previous version shows the tab disabled with the sentence "No previous version was
  given for this run" instead of hiding it (no silent absence).
* A delta run written before the delta table (the committed rehearsal run) degrades honestly: its
  rows come from the findings' re-assessments and a notice says prior findings no finding carries are
  not shown.

``delta_view`` is checked directly; the page is checked in Chromium (skipped where Playwright or
Chromium is missing) against the real server on a loopback port.
"""

from __future__ import annotations

import json
import shutil
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from test_reassessment_delta import MAIL, STRENGTH, TESTING, WITHDRAW_NOTE, _delta, _run

from sit_review_agent.ui import rundata
from sit_review_agent.ui.launcher import Launcher
from sit_review_agent.ui.server import UIState, build_app

REPO = Path(__file__).resolve().parents[1]
FULL = REPO / "docs" / "live_runs" / "rehearsal_concurrent_1"
LEGACY = REPO / "docs" / "live_runs" / "reassess_payments_v2_1"
RUN_FILES = ("report.json", "manifest.json", "anchors.json", "ledger.json", "state.json", "effective_config.json")


@pytest.fixture(scope="module")
def delta_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    """A v2 fake-gateway run against a v1 one, its prior strength withdrawn by refine."""
    import asyncio

    from sit_review_agent.selftest import FIXTURE_DIR, selftest_config

    tmp = tmp_path_factory.mktemp("delta_pair")
    cfg = selftest_config(tmp / "runs")
    v1 = asyncio.run(_run(cfg, "v1", FIXTURE_DIR / "design.pages.txt"))
    prior = {f["title"]: f["id"] for f in json.loads((v1.run_dir / "report.json").read_text())["findings"]}
    withdrawn = [{"prior_finding_id": prior[STRENGTH], "status": "withdrawn_on_reassessment", "note": WITHDRAW_NOTE}]
    _, _, _, run_dir = _delta(tmp, (cfg, v1, prior), [None, withdrawn])
    return run_dir, prior


def _rows(view: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for g in view["groups"] for r in g["rows"]]


def test_a_full_review_has_the_tab_disabled_with_a_reason() -> None:
    report = json.loads((FULL / "report.json").read_text(encoding="utf-8"))
    assert rundata.delta_view(report) == {"available": False, "reason": "No previous version was given for this run"}


def test_the_delta_view_is_keyed_on_the_prior_id(delta_run: tuple[Path, dict[str, str]]) -> None:
    run_dir, prior = delta_run
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    view = rundata.delta_view(report)
    assert view["table"] and view["prior_count"] == 3 and view["not_re_examined"] == 1 and view["regressions"] == 1
    by_prior = {r["prior_id"]: r for r in _rows(view) if r["prior_id"]}
    assert sorted(by_prior) == sorted(prior.values())
    mail = next(f for f in report["findings"] if f["title"] == MAIL)
    row = by_prior[prior[MAIL]]
    assert (row["finding_ids"], row["note"]) == ([mail["id"]], "Quota still unaddressed.")
    assert by_prior[prior[STRENGTH]]["status"] == "withdrawn_on_reassessment"
    assert by_prior[prior[TESTING]]["re_examined"] is False
    new = next(g for g in view["groups"] if g["status"] == "new_in_update")["rows"]
    assert {r["title"]: r["regression"] for r in new} == {TESTING: True, STRENGTH: False}


def test_a_delta_run_written_before_the_table_says_so() -> None:
    report = json.loads((LEGACY / "report.json").read_text(encoding="utf-8"))
    view = rundata.delta_view(report)
    assert view["available"] and not view["table"] and view["notice"] == rundata.NO_TABLE
    pairs = {(r["prior_id"], r["finding_ids"][0]) for r in _rows(view) if r["prior_id"]}
    assert ("FND-002", "FND-003") in pairs                      # this run's FND-003 was the prior FND-002
    assert sum(len(g["rows"]) for g in view["groups"]) == len(report["findings"])


# ------------------------------------------------------------------ the page


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def page(delta_run: tuple[Path, dict[str, str]], tmp_path_factory: pytest.TempPathFactory):
    uvicorn = pytest.importorskip("uvicorn")
    sync_api = pytest.importorskip("playwright.sync_api")
    runs = tmp_path_factory.mktemp("ui_runs")
    for src, name in ((FULL, "full"), (LEGACY, "legacy"), (delta_run[0], "delta")):
        (runs / name).mkdir()
        for f in RUN_FILES:
            if (src / f).is_file():
                shutil.copy2(src / f, runs / name / f)
    state = UIState(runs_dir=runs.resolve(), repo_root=REPO, launcher=Launcher(repo_root=REPO), chat_client=None,
                    profiles=[], tools=[])  # type: ignore[arg-type]
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(build_app(state), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Chromium not installed here
            pytest.skip(f"Chromium not available: {exc}")
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        yield pg, f"http://127.0.0.1:{port}", errors
        browser.close()
    server.should_exit = True
    th.join(timeout=5)
    assert errors == []


def _open(pg: Any, base: str, run_id: str, tab: str) -> None:
    pg.goto(base + f"/?run={run_id}&tab={tab}")
    pg.wait_for_selector("#review > div")


def test_the_page_shows_a_disabled_delta_tab_without_a_previous_version(page) -> None:
    pg, base, errors = page
    _open(pg, base, "full", "review")
    tab = pg.locator("#top-tabs .tab", has_text="Delta")
    assert tab.count() == 1 and tab.get_attribute("aria-disabled") == "true"
    assert tab.get_attribute("title") == "No previous version was given for this run"
    tab.click(force=True)            # aria-disabled keeps it focusable and openable, so the reason can be read
    pg.wait_for_selector("#review .delta-off")
    assert pg.locator("#review .delta-off").inner_text() == "No previous version was given for this run."
    assert errors == []


def test_the_page_shows_prior_id_status_note_and_regression(page, delta_run) -> None:
    pg, base, errors = page
    _, prior = delta_run
    _open(pg, base, "delta", "delta")
    tab = pg.locator("#top-tabs .tab", has_text="Delta")
    assert tab.get_attribute("aria-disabled") is None
    rows = pg.evaluate("[...document.querySelectorAll('#review tr.drow')].map(r => "
                       "[...r.querySelectorAll('td')].map(td => td.innerText))")
    by_prior = {r[0]: r for r in rows if r[0].startswith("FND-")}
    assert sorted(by_prior) == sorted(prior.values())
    mail = by_prior[prior[MAIL]]
    assert mail[2] == "still open" and mail[4] == "Quota still unaddressed."
    assert mail[1].startswith("FND-")                                        # this review's ID beside the prior one
    assert by_prior[prior[STRENGTH]][2:] == ["withdrawn on re-assessment", STRENGTH, WITHDRAW_NOTE], rows
    assert by_prior[prior[TESTING]][2] == "still open, not re-examined"
    new = [r for r in rows if r[0] == "new"]
    assert any(r[2] == "new (regression)" and r[3] == TESTING for r in new), new
    assert any(r[2] == "new" and r[3] == STRENGTH for r in new), new
    assert "3 prior findings, each with one status" in pg.locator("#review .delta-sum").inner_text()
    assert errors == []


def test_an_older_delta_run_degrades_honestly(page) -> None:
    pg, base, errors = page
    _open(pg, base, "legacy", "delta")
    assert pg.locator("#review .delta-notice").inner_text() == rundata.NO_TABLE
    rows = pg.evaluate("[...document.querySelectorAll('#review tr.drow')].map(r => "
                       "[...r.querySelectorAll('td')].map(td => td.innerText))")
    assert ["FND-002", "FND-003"] == next(r[:2] for r in rows if r[1] == "FND-003")
    assert errors == []
