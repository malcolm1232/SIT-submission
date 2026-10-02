"""No LLM-facing schema description carries reStructuredText roles or backticked code references:
Pydantic sends each draft type's docstring as its ``description``, so it reaches the model as an
instruction (latency integration, planner ruling).
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from sit_review_agent.llm.outputs import PHASE_OUTPUT_TYPES, llm_facing_schema


def _descriptions(node: Any) -> list[str]:
    if isinstance(node, dict):
        return [v for k, v in node.items() if k == "description" and isinstance(v, str)] + [
            d for k, v in node.items() if k != "description" for d in _descriptions(v)]
    if isinstance(node, list):
        return [d for v in node for d in _descriptions(v)]
    return []


@pytest.mark.parametrize("phase", sorted(PHASE_OUTPUT_TYPES))
def test_no_llm_facing_description_carries_code_markup(phase: str) -> None:
    descs = _descriptions(llm_facing_schema(PHASE_OUTPUT_TYPES[phase]))
    bad = [d for d in descs if re.search(r":(func|class|meth|attr|data|mod):|`", d)]
    assert bad == []
