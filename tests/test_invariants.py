"""invariants.py on the spec's example Review (should pass) and on broken variants (should fail)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from sit_review_agent import invariants as inv


def test_example_review_passes(review_dict: dict[str, Any], booking_pages: str) -> None:
    results = inv.check_all(review_dict, texts={"DOC-booking-v1": booking_pages}, require_extra=False)
    failed = {r.inv_id: r.problems for r in results if not r.passed}
    assert failed == {}


def test_inv04_rejects_moved_quote(review_dict: dict[str, Any], booking_pages: str) -> None:
    bad = copy.deepcopy(review_dict)
    bad["findings"][0]["doc_anchors"][0]["page"] = 2
    assert not inv.check_INV_04(bad, texts={"DOC-booking-v1": booking_pages}).passed


def test_inv05_rejects_free_url_and_unknown_evidence(review_dict: dict[str, Any]) -> None:
    bad = copy.deepcopy(review_dict)
    bad["findings"][0]["statement"] += " See https://made-up.example/paper."
    bad["findings"][0]["evidence"][0]["evidence_id"] = "EV-999"
    problems = inv.check_INV_05(bad).problems
    assert any("made-up.example" in p for p in problems) and any("EV-999" in p for p in problems)


def test_inv07_requires_disclosure(review_dict: dict[str, Any]) -> None:
    bad = copy.deepcopy(review_dict)
    bad["stop_reason"] = {"code": "deadline", "group": "cap", "detail": None}
    assert not inv.check_INV_07(bad).passed


def test_inv08_finds_canary(tmp_path: Path) -> None:
    (tmp_path / "llm.jsonl").write_text('{"h": "CANARY-MCP-7f3a"}\n')
    assert not inv.check_INV_08(tmp_path, ["CANARY-MCP-7f3a"]).passed
    assert inv.check_INV_08(tmp_path, ["CANARY-OTHER"]).passed


def test_inv09_requires_manifest_extra(review_dict: dict[str, Any]) -> None:
    assert inv.check_INV_09(review_dict, require_extra=False).passed
    assert not inv.check_INV_09(review_dict).passed           # example has extra = {}


def test_inv10_registry_hash_constant(review_dict: dict[str, Any]) -> None:
    bad = copy.deepcopy(review_dict)
    bad["decision_registry"][0]["statement"] = "changed after iteration 1"
    assert not inv.check_INV_10(bad).passed
