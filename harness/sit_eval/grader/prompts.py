"""Grader prompt files, placeholder rendering and the prompt lock.

The first four prompt files in ``grader/prompts/`` are verbatim copies of the fenced blocks in
``research/grading/grader_prompt.md`` §2 (system), §3.1 (Pass A), §3.2 (Pass B) and §4 (segmenter);
``tests/eval_grader`` checks they have not drifted. ``prompts.lock.json`` records the SHA-256 of every
prompt and schema file plus one bundle hash: the value ``eval/prereg.yaml`` ``grader.prompt_sha256``
takes at freeze. Re-lock with ``sit-eval grade lock --write`` after an intended edit.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import cache
from importlib import resources
from typing import Any

PROMPT_VERSION = "lecturer-v1"
PROMPT_FILES = ("system.txt", "pass_a.txt", "pass_b.txt", "segmenter.txt", "repair_note.txt")
SCHEMA_FILES = ("pass_a_output.schema.json", "pass_b_output.schema.json")
LOCK_FILE = "prompts.lock.json"

_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
#: The review and design are wrapped in these delimiters (grader_prompt.md §2 "SAFETY OF INPUTS").
_DELIMITER = re.compile(r"<<<|>>>")


class PromptError(ValueError):
    """A template placeholder was left unfilled, or a value was given for no placeholder."""


def _pkg_file(folder: str, name: str) -> str:
    return resources.files("sit_eval.grader").joinpath(folder, name).read_text(encoding="utf-8")


@cache
def load_prompt(name: str) -> str:
    """The prompt file ``name`` (e.g. ``"pass_a.txt"``) without its trailing newline.

    ``repair_note.txt`` is a harness addition (not in grader_prompt.md): it is appended to the user
    message of the one repair call made when an output fails the full schema. Its leading blank
    lines are kept.
    """
    if name not in PROMPT_FILES:
        raise KeyError(name)
    return _pkg_file("prompts", name).rstrip("\n")


def placeholders(template: str) -> set[str]:
    return set(_PLACEHOLDER.findall(template))


def neutralise_delimiters(text: str) -> str:
    """Break any ``<<<``/``>>>`` inside data so a review cannot close its own delimiter block."""
    return _DELIMITER.sub(lambda m: m.group(0)[0] + "​" + m.group(0)[1:], text)


def render(template: str, values: dict[str, str]) -> str:
    """Fill ``{{NAME}}`` placeholders literally, in one pass (inserted text is never re-scanned).

    Every placeholder must have a value and every value a placeholder (grader_prompt.md §1).
    """
    wanted = placeholders(template)
    missing, extra = wanted - values.keys(), values.keys() - wanted
    if missing or extra:
        raise PromptError(f"placeholders missing {sorted(missing)}, unexpected {sorted(extra)}")
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], template)


# ------------------------------------------------------------------------------------------ lock
def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def current_hashes() -> dict[str, Any]:
    """SHA-256 of every prompt and schema file as packaged, and the bundle hash over them."""
    files: dict[str, str] = {}
    for name in PROMPT_FILES:
        files[f"prompts/{name}"] = _sha(_pkg_file("prompts", name))
    for name in SCHEMA_FILES:
        files[f"schemas/{name}"] = _sha(_pkg_file("schemas", name))
    bundle = _sha("".join(f"{k} {v}\n" for k, v in sorted(files.items())))
    return {"prompt_version": PROMPT_VERSION, "algorithm": "sha256", "files": files, "bundle_sha256": bundle,
            "bundle_rule": "sha256 of the lines '<path> <sha256>\\n' sorted by path",
            "prereg_field": "grader.prompt_sha256 = bundle_sha256"}


def read_lock() -> dict[str, Any] | None:
    try:
        return json.loads(_pkg_file("prompts", LOCK_FILE))
    except FileNotFoundError:
        return None


def lock_status() -> dict[str, Any]:
    """Compare the packaged files with the lock. ``ok`` is false on any drift."""
    cur, lock = current_hashes(), read_lock()
    if lock is None:
        return {"ok": False, "bundle_sha256": cur["bundle_sha256"], "locked_bundle_sha256": None,
                "drifted": sorted(cur["files"])}
    drifted = sorted(k for k, v in cur["files"].items() if lock.get("files", {}).get(k) != v)
    drifted += sorted(k for k in lock.get("files", {}) if k not in cur["files"])
    return {"ok": not drifted and lock.get("bundle_sha256") == cur["bundle_sha256"],
            "bundle_sha256": cur["bundle_sha256"], "locked_bundle_sha256": lock.get("bundle_sha256"),
            "drifted": drifted}


def lock_text() -> str:
    return json.dumps(current_hashes(), indent=2, sort_keys=True) + "\n"
