"""File locations used by the harness (repository root from the agent's own resolver)."""

from __future__ import annotations

from pathlib import Path

from sit_review_agent.paths import repo_root

PACKAGE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = PACKAGE_DIR / "prompts"
SCHEMAS_DIR = PACKAGE_DIR / "schemas"
PROMPTS_LOCK = PROMPTS_DIR / "PROMPTS.lock"


def eval_config_path() -> Path:
    return repo_root() / "config" / "eval.yaml"


def prereg_path() -> Path:
    return repo_root() / "eval" / "prereg.yaml"


def prereg_lock_path() -> Path:
    return repo_root() / "eval" / "prereg.lock"


def answer_key_schema_path() -> Path:
    return repo_root() / "spec" / "answer_key.schema.json"


def finding_schema_path() -> Path:
    return repo_root() / "spec" / "finding.schema.json"
