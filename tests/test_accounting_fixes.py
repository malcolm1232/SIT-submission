"""Session 4 accounting fixes: what a run records about itself must not under-state it.

* the manifest records the full git branch (``s4/demo``, not ``demo``), and a detached HEAD or a
  missing ``git`` binary never crashes it;
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sit_review_agent.manifest import git_state

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
