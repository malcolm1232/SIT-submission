"""Content hashes used in the run manifest, checkpoints and cassette keys.

Canonical JSON is the spec's rule (``spec/validate_examples.py`` ``registry_sha256``): sorted keys,
no whitespace, UTF-8, ``ensure_ascii=False``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def canonical_json(obj: Any) -> str:
    """Serialise ``obj`` as canonical JSON (sorted keys, ``(",", ":")`` separators, UTF-8)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj: Any) -> str:
    """SHA-256 of the canonical JSON of ``obj``."""
    return sha256_text(canonical_json(obj))


def bundle_sha256(items: Iterable[tuple[str, str]]) -> str:
    """Hash over a sorted list of ``(path, sha256)`` pairs (prompts and config bundles, REPRODUCIBILITY §4)."""
    return sha256_json(sorted([list(p) for p in items]))


def registry_sha256(registry: list[dict[str, Any]]) -> str:
    """Hash of the canonical JSON of ``decision_registry`` (robustness INV-10)."""
    return sha256_json(registry)
