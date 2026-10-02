"""Repository-relative locations of the spec, config and prompt files.

The package lives in ``<repo>/agent/sit_review_agent``. ``SIT_REPO_ROOT`` overrides the
detected root (useful when the package is installed non-editable).
"""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Return the repository root (the directory holding ``spec/`` and ``config/``)."""
    env = os.environ.get("SIT_REPO_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


def spec_dir() -> Path:
    return repo_root() / "spec"


def config_dir() -> Path:
    return repo_root() / "config"


def prompts_dir() -> Path:
    return repo_root() / "prompts"


def finding_schema_path() -> Path:
    return spec_dir() / "finding.schema.json"


def taxonomy_path() -> Path:
    return spec_dir() / "taxonomy.yaml"
