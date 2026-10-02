"""The agent must never import the evaluation harness or reference an answer key (README of sit_eval;
prereg leakage controls). Walks the AST of every module under agent/sit_review_agent."""

from __future__ import annotations

import ast
import re
from pathlib import Path

AGENT = Path(__file__).resolve().parents[2] / "agent" / "sit_review_agent"
FORBIDDEN_STRING = re.compile(r"answer_key|sit_eval|eval/(blind|heldout|synthetic)|eval\\(blind|heldout|synthetic)",
                              re.I)


def _problems(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [f"import {a.name}" for a in node.names if a.name.split(".")[0] == "sit_eval"]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "sit_eval":
                out.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and FORBIDDEN_STRING.search(node.value):
            out.append(f"string constant {node.value[:80]!r} (line {node.lineno})")
        elif isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if "answer_key" in name.lower():
                out.append(f"identifier {name} (line {node.lineno})")
    return out


def test_agent_package_is_isolated_from_the_harness() -> None:
    files = sorted(AGENT.rglob("*.py"))
    assert len(files) > 20, "agent package not found where expected"
    bad = {str(p.relative_to(AGENT)): probs for p in files if (probs := _problems(p))}
    assert not bad, f"agent modules reference the harness or answer keys: {bad}"


def test_detector_catches_violations(tmp_path: Path) -> None:
    p = tmp_path / "m.py"
    p.write_text("import sit_eval.judge\nfrom sit_eval import x\nK = 'eval/synthetic/a/answer_key.canonical.json'\n"
                 "def f(answer_key_path):\n    return answer_key_path\n", encoding="utf-8")
    probs = _problems(p)
    assert any("import sit_eval" in x for x in probs) and any("from sit_eval" in x for x in probs)
    assert any("string constant" in x for x in probs) and any("identifier" in x for x in probs)
