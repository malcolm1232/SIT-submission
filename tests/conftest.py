"""Shared fixtures. Every test runs offline with no key (ADR-008)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def review_dict() -> dict[str, Any]:
    """The complete example Review built by spec/validate_examples.py (invented, prompt-safe)."""
    return json.loads((FIXTURES / "review_example.json").read_text(encoding="utf-8"))


@pytest.fixture
def booking_pages() -> str:
    """Sparse page-marked text that the example Review's anchors resolve against."""
    return (FIXTURES / "booking_v1.pages.txt").read_text(encoding="utf-8")
