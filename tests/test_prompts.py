"""Prompt files: present, lock fresh, StrictUndefined rendering, no eval leakage."""

from __future__ import annotations

import pytest

from sit_review_agent.errors import PromptError
from sit_review_agent.paths import prompts_dir
from sit_review_agent.prompts import REQUIRED_PROMPTS, PromptBundle

#: Names that must never appear in a prompt (eval items, answer-key machinery). See prompts/README.md.
FORBIDDEN = ("legacy_mappings", "answer_key", "answer key", "payments_orchestration", "clinical_rpm",
             "research_lakehouse", "item_a", "item_b", "eval/", "planted", "sound_sections")


def test_required_prompts_and_lock() -> None:
    bundle = PromptBundle.load()
    assert set(REQUIRED_PROMPTS) <= set(bundle.files)
    assert "README.md" not in bundle.files
    assert bundle.check_lock() == [], "run: python -m sit_review_agent.prompts --write-lock"
    assert len(bundle.bundle_sha256) == 64


@pytest.mark.parametrize("name", REQUIRED_PROMPTS)
def test_no_eval_leakage(name: str) -> None:
    text = (prompts_dir() / name).read_text(encoding="utf-8").lower()
    assert not [w for w in FORBIDDEN if w.lower() in text]


@pytest.mark.parametrize("name", [n for n in REQUIRED_PROMPTS if n != "system.md"])
def test_phase_prompts_state_the_content_rules(name: str) -> None:
    text = (prompts_dir() / name).read_text(encoding="utf-8")
    assert "Required content rules" in text
    assert "URL" in text


def test_system_prompt_rules() -> None:
    text = (prompts_dir() / "system.md").read_text(encoding="utf-8")
    for needle in ("at least 8 words", "evidence ID", "Never write a URL", "No change needed", "page-marked text"):
        assert needle in text


def test_render_is_strict() -> None:
    bundle = PromptBundle.load()
    with pytest.raises(PromptError):
        bundle.render("system.md")
    r = bundle.render("system.md", persona_title="Principal solution architect", persona_emphasis="Balanced.")
    assert "Principal solution architect" in r.text and len(r.sha256) == 64
    again = bundle.render("system.md", persona_title="Principal solution architect", persona_emphasis="Balanced.")
    assert again.sha256 == r.sha256          # byte-stable (cached prefix)
