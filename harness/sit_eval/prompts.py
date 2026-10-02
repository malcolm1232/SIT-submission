"""Judge prompt templates, judge output schemas and their lock file.

Templates live in ``harness/sit_eval/prompts/*.md`` and use ``{{NAME}}`` placeholders, rendered
strictly (a missing or unused value is an error). The judge output schemas are
``harness/sit_eval/schemas/judge_*.schema.json``. ``prompts/PROMPTS.lock`` records the SHA-256 of
every one of these files plus a bundle hash over all of them; the bundle hash is the value
``eval/prereg.yaml matcher.prompt_sha256`` takes at freeze. ``sit-eval prompts`` checks the lock,
``sit-eval prompts --write-lock`` rewrites it.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from sit_eval.paths import PROMPTS_DIR, PROMPTS_LOCK, SCHEMAS_DIR

_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
LOCK_VERSION = 1


def _locked_files() -> list[Path]:
    return sorted(PROMPTS_DIR.glob("*.md")) + sorted(SCHEMAS_DIR.glob("judge_*.schema.json"))


def _rel(p: Path) -> str:
    return f"{p.parent.name}/{p.name}"


def file_sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def compute_lock() -> dict[str, Any]:
    files = {_rel(p): file_sha256(p) for p in _locked_files()}
    bundle = hashlib.sha256("".join(f"{k}\0{v}\n" for k, v in sorted(files.items())).encode()).hexdigest()
    return {"lock_version": LOCK_VERSION, "bundle_sha256": bundle, "files": files,
            "note": "bundle_sha256 is the value eval/prereg.yaml matcher.prompt_sha256 takes at freeze"}


def read_lock(path: Path = PROMPTS_LOCK) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_lock(path: Path = PROMPTS_LOCK) -> dict[str, Any]:
    lock = compute_lock()
    path.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return lock


def check_lock(path: Path = PROMPTS_LOCK) -> list[str]:
    """Differences between the lock file and the files on disk (empty list = in sync)."""
    want = read_lock(path)
    if want is None:
        return [f"{path.name} is missing; run `sit-eval prompts --write-lock`"]
    have = compute_lock()
    problems = []
    for name in sorted(set(want.get("files", {})) | set(have["files"])):
        a, b = want.get("files", {}).get(name), have["files"].get(name)
        if a != b:
            problems.append(f"{name}: lock {a or 'absent'} != disk {b or 'absent'}")
    if not problems and want.get("bundle_sha256") != have["bundle_sha256"]:
        problems.append("bundle_sha256 differs")
    return problems


@cache
def template(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def render(name: str, **values: str) -> str:
    """Render ``prompts/<name>.md``; every placeholder must be given and every value used."""
    text = template(name)
    wanted = set(_PLACEHOLDER.findall(text))
    missing = wanted - set(values)
    unused = set(values) - wanted
    if missing or unused:
        raise KeyError(f"prompt {name}: missing {sorted(missing)}, unused {sorted(unused)}")
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), text)


@cache
def _schema(name: str) -> dict[str, Any]:
    data = json.loads((SCHEMAS_DIR / f"judge_{name}.schema.json").read_text(encoding="utf-8"))
    data.pop("$schema", None)   # meta keyword; not sent to structured outputs
    return data


def judge_schema(name: str) -> dict[str, Any]:
    """Output schema for judge call kind ``name`` (shortlist, pair, batch, adjudicate, premise,
    citation, recommendation). A fresh copy each time."""
    return copy.deepcopy(_schema(name))
