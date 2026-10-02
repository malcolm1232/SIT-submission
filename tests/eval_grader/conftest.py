"""Fixtures for the lecturer-grader tests. Offline: every judge here is a FakeJudge."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sit_eval.grader.fake import heuristic_responder
from sit_eval.judge import FakeJudge, JudgeRequest


@pytest.fixture
def graded_inputs(tmp_path: Path, review_dict: dict[str, Any], booking_pages: str) -> tuple[Path, Path]:
    """(review.json, pages.txt): the spec example Review with its document hash set to the real text hash."""
    pages = tmp_path / "DOC-booking-v1.pages.txt"
    pages.write_text(booking_pages, encoding="utf-8")
    review = copy.deepcopy(review_dict)
    review["metadata"]["documents"][0]["sha256_text"] = hashlib.sha256(booking_pages.encode("utf-8")).hexdigest()
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review), encoding="utf-8")
    return path, pages


@pytest.fixture
def write_review(tmp_path: Path) -> Callable[[dict[str, Any], str], Path]:
    def _write(review: dict[str, Any], name: str = "variant.json") -> Path:
        p = tmp_path / name
        p.write_text(json.dumps(review), encoding="utf-8")
        return p
    return _write


@pytest.fixture
def heuristic_judge() -> FakeJudge:
    return FakeJudge(heuristic_responder, model="fake-judge-heuristic")


def patched(fn: Callable[[JudgeRequest, dict[str, Any]], dict[str, Any] | None]) -> FakeJudge:
    """A FakeJudge that runs the heuristic responder and lets ``fn`` rewrite (or replace) its answer."""
    def responder(req: JudgeRequest) -> dict[str, Any]:
        base = heuristic_responder(req)
        out = fn(req, base)
        return base if out is None else out
    return FakeJudge(responder, model="fake-judge-patched")


@pytest.fixture
def make_judge() -> Callable[..., FakeJudge]:
    return patched
