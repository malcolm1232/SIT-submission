"""JSON schemas of the grader's model outputs (grader_prompt.md §5.1, §5.2) and of ``grade.json``.

``pass_a_output`` and ``pass_b_output`` are verbatim copies of §5.1 and §5.2. Outputs are always
validated against these **full** schemas in code. The schema sent with the call
(:func:`llm_facing`) is derived from them the way ``spec/README.md`` "LLM-facing schema" describes:
Claude structured outputs reject numeric and string-length constraints, so they are stripped
there and enforced here instead.
"""

from __future__ import annotations

import copy
import json
from functools import cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

PASS_A = "pass_a_output"
PASS_B = "pass_b_output"
GRADE_REPORT = "grade_report"
_NAMES = {PASS_A: "pass_a_output.schema.json", PASS_B: "pass_b_output.schema.json",
          GRADE_REPORT: "grade_report.schema.json"}

#: Keywords stripped from the LLM-facing schema (spec/README.md "LLM-facing schema" step 2).
STRIP_KEYWORDS = frozenset({"minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
                            "exclusiveMaximum", "minItems", "maxItems", "pattern", "format"})


@cache
def _load(name: str) -> str:
    return resources.files("sit_eval.grader").joinpath("schemas", _NAMES[name]).read_text(encoding="utf-8")


def load_schema(name: str) -> dict[str, Any]:
    return json.loads(_load(name))


def schema_text(name: str) -> str:
    """The schema as it is pasted into ``{{PASS_A_SCHEMA}}`` / ``{{PASS_B_SCHEMA}}`` (file text, verbatim)."""
    return _load(name).rstrip("\n")


@cache
def validator(name: str) -> Draft202012Validator:
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def errors(name: str, data: Any) -> list[str]:
    """Human-readable validation errors (empty if valid), sorted for stable logs."""
    out = []
    for e in validator(name).iter_errors(data):
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        msg = e.message if len(e.message) <= 300 else f"{e.message[:140]} ... {e.message[-140:]}"
        out.append(f"{path}: {msg}")
    return sorted(out)


def llm_facing(name: str) -> dict[str, Any]:
    """Derived schema for the structured-output call: constraints in :data:`STRIP_KEYWORDS` removed.

    Property names that collide with a stripped keyword (none today) are kept, because stripping
    only happens on schema nodes, never inside ``properties`` maps.
    """
    def strip(node: Any, in_props: bool = False) -> Any:
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if not in_props and k in STRIP_KEYWORDS:
                    continue
                out[k] = strip(v, in_props=(k in ("properties", "$defs") and not in_props))
            return out
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return strip(copy.deepcopy(load_schema(name)))
