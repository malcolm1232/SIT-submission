"""Robustness suite fixtures (research/robustness/README.md §6.1): the ``scenario`` marker, one
fault-free control run shared by the scenarios that compare against it, and the results sink
that writes ``robustness_results.csv`` at the end of the session (a temp directory unless
``ROBUSTNESS_RESULTS_CSV`` names the real file; see README.md)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from robustness_harness import RunRecord, Scenario, run
from robustness_results import ResultSink, write_csv


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "scenario(id): robustness scenario ID (research/robustness/scenarios.md)")


@pytest.fixture(scope="session")
def control(tmp_path_factory: pytest.TempPathFactory) -> RunRecord:
    """The fault-free run of the scripted fixture (the baseline that INF-11, INF-18, LLM-06/07/08,
    NET-01 and OPS-04 compare against)."""
    rec = run(Scenario(id="CONTROL"), tmp_path_factory.mktemp("robustness-control"))
    assert rec.exit_code == 0, rec.failure
    return rec


@pytest.fixture(scope="session")
def results_sink(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ResultSink]:
    sink = ResultSink()
    yield sink
    target = os.environ.get("ROBUSTNESS_RESULTS_CSV")
    path = Path(target) if target else tmp_path_factory.mktemp("robustness-results") / "robustness_results.csv"
    write_csv(path, sink.rows)
