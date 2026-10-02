"""Session 4 accounting fixes: what a run records about itself must not under-state it.

* the manifest records the full git branch (``s4/demo``, not ``demo``), and a detached HEAD or a
  missing ``git`` binary never crashes it;
* ``report.md`` "Located at" names each intent location once (with the number of passages there)
  and the understand phase keeps an exact duplicate anchor once, so ``report.json`` and
  ``report.md`` agree;
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.config import EffectiveConfig, load_config
from sit_review_agent.llm.gateway import FakeResponse
from sit_review_agent.llm.outputs import FindingDraft, SoundAreaDraft
from sit_review_agent.manifest import git_state
from sit_review_agent.models import Review
from sit_review_agent.phases._model_calls import normalise_findings, normalise_sound_areas
from sit_review_agent.phases.understand import UnderstandPhase
from sit_review_agent.report.render import render_markdown
from sit_review_agent.states import PhaseName
from test_llm_phases import DOC_ID, Q_A11Y, Q_NOTIFY, Q_OVERVIEW, anchor, finding, make_ctx, understand_output

SHA = "2d84f59" + "0" * 33


# ============================================================================== git branch


def _repo(root: Path, head: str, refs: dict[str, str] | None = None) -> Path:
    git = root / ".git"
    git.mkdir(parents=True)
    (git / "HEAD").write_text(head + "\n", encoding="utf-8")
    for ref, sha in (refs or {}).items():
        p = git / ref
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(sha + "\n", encoding="utf-8")
    return root


def test_branch_with_a_slash_is_recorded_in_full(tmp_path: Path) -> None:
    root = _repo(tmp_path, "ref: refs/heads/s4/demo", {"refs/heads/s4/demo": SHA})
    assert git_state(root) == {"commit": SHA, "branch": "s4/demo", "dirty": None}


def test_branch_in_packed_refs_and_a_linked_worktree(tmp_path: Path) -> None:
    main = _repo(tmp_path / "main", "ref: refs/heads/main")
    (main / ".git" / "packed-refs").write_text(f"# pack-refs with: peeled\n{SHA} refs/heads/s4/integration\n",
                                               encoding="utf-8")
    wt_git = main / ".git" / "worktrees" / "integration"
    wt_git.mkdir(parents=True)
    (wt_git / "HEAD").write_text("ref: refs/heads/s4/integration\n", encoding="utf-8")
    (wt_git / "commondir").write_text("../..\n", encoding="utf-8")
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {wt_git}\n", encoding="utf-8")
    assert git_state(wt) == {"commit": SHA, "branch": "s4/integration", "dirty": None}


def test_detached_head_has_no_branch(tmp_path: Path) -> None:
    root = _repo(tmp_path, SHA)
    assert git_state(root) == {"commit": SHA, "branch": None, "dirty": None}


def test_no_git_directory_and_no_git_binary_do_not_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))           # no `git` on the PATH
    assert git_state(tmp_path, check_dirty=True) == {"commit": None, "branch": None, "dirty": None}
    root = _repo(tmp_path / "r", "ref: refs/heads/s4/demo", {"refs/heads/s4/demo": SHA})
    assert git_state(root, check_dirty=True) == {"commit": SHA, "branch": "s4/demo", "dirty": None}


# ============================================================================== Located at


def _located_at(md: str) -> str:
    return next(line for line in md.splitlines() if line.startswith("Located at: "))


def test_located_at_names_each_location_once(review_dict: dict[str, Any]) -> None:
    data = copy.deepcopy(review_dict)
    first = data["intent_summary"]["doc_anchors"][0]
    data["intent_summary"]["doc_anchors"] = [               # the live run's shape: two passages in p.2 section 1
        {**first, "page": 1, "section_ref": "1", "quote": "the first passage of the overview text on page one"},
        {**first, "page": 2, "section_ref": "1", "quote": "the second passage of the overview text on page two"},
        {**first, "page": 2, "section_ref": "1", "quote": "a third passage, also on page two in section one"}]
    review = Review.model_validate(data)
    assert _located_at(render_markdown(review)) == "Located at: p.1 §1, p.2 §1 (2 passages)."
    data["intent_summary"]["doc_anchors"] = data["intent_summary"]["doc_anchors"][:1]
    assert _located_at(render_markdown(Review.model_validate(data))) == "Located at: p.1 §1."


@pytest.fixture(scope="module")
def cfg() -> EffectiveConfig:
    return load_config()


async def test_understand_keeps_a_repeated_anchor_once(tmp_path: Path, cfg: EffectiveConfig) -> None:
    out = understand_output()
    out["intent_summary"]["doc_anchors"] = [anchor(Q_OVERVIEW, 2, "1"), anchor(Q_OVERVIEW, 2, "1")]
    ctx = make_ctx(tmp_path, cfg, {PhaseName.UNDERSTAND: [FakeResponse(parsed=out)]})
    await UnderstandPhase().run(ctx)
    assert ctx.state.intent_summary is not None
    assert [(a.doc_id, a.page, a.quote) for a in ctx.state.intent_summary.doc_anchors] == [(DOC_ID, 2, Q_OVERVIEW)]


def test_finding_and_sound_area_anchors_keep_a_repeat_once(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = make_ctx(tmp_path, cfg, {})
    twice = [anchor(Q_NOTIFY, 11, "6.2"), anchor("  " + Q_NOTIFY, 11, "6.2"), anchor(Q_A11Y, 18, "11.3")]
    [f], _ = normalise_findings(ctx, [FindingDraft.model_validate(finding("FND-001", 1, doc_anchors=twice))])
    assert [(a.page, a.section_ref) for a in f.doc_anchors] == [(11, "6.2"), (18, "11.3")]
    area = SoundAreaDraft.model_validate({"section_refs": ["6.2"], "why_sound": "ok", "doc_anchors": twice,
                                          "evidence_ids": [], "related_finding_ids": []})
    [a] = normalise_sound_areas(ctx, [area], {}, set())
    assert len(a.doc_anchors) == 2
