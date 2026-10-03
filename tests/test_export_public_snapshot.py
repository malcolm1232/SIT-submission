"""``scripts/export_public_snapshot.py``: the exclusion rules, the secret scan and the dirty-worktree guard.

Every test builds a throwaway git repository under ``tmp_path``; nothing reads the real tree's private
material, and no test pushes or touches a network.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_public_snapshot.py"


def _load():
    spec = importlib.util.spec_from_file_location("export_public_snapshot_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


eps = _load()

#: One file of each excluded kind, with the group it must land in.
EXCLUDED = {
    "eval/blind/item_x/design_v1.md": "sealed",
    "eval/blind/item_x/answer_key.json": "sealed",
    "eval/synthetic/demo/answer_key.json": "answer-keys",
    "eval/synthetic/demo/answer_key.canonical.json": "answer-keys",
    "eval/synthetic/demo/answer_key.yaml": "answer-keys",
    "eval/KEY_SIGNOFF.md": "answer-keys",
    "notes/key_draft_notes.md": "answer-keys",          # names a key field, not reviewed
    "docs/live_runs/run_a/llm.jsonl": "transcripts",
    "docs/live_runs/run_a/eval_pilot/judge_calls.jsonl": "transcripts",
    "docs/live_runs/run_a/eval_pilot/scores.md": "transcripts",
    "docs/live_runs/run_a/grade_pilot2/grader_calls.jsonl": "transcripts",
    "docs/live_runs/run_a/judge_results.jsonl": "transcripts",
    "docs/live_runs/run_a/ledger.jsonl": "transcripts",
    "docs/live_runs/run_a/state.json": "transcripts",
    "docs/live_runs/run_a/checkpoints/01.json": "transcripts",
    "docs/live_runs/run_a/shards/s1.json": "transcripts",
    "docs/live_runs/run_a/snapshots/x.json": "transcripts",
    "docs/live_runs/run_a/text/p1.txt": "transcripts",
    "runs/r1/ui/chat.jsonl": "transcripts",
    "docs/transcripts/session1.md": "transcripts",
    "docs/live_runs/sit_sample_v1/report.md": "lab-material",
    "research/robustness/mcp_probe_results.redacted.json": "lab-material",
    "docs/SIT_Memory_notes.md": "lab-material",
    "docs/Lab Exercise brief.pdf": "lab-material",
    "tests/fixtures/stream/haiku.jsonl": "recorded-streams",
    "tests/fixtures/cassettes/tools/x.json": "recorded-streams",
    "tests/robustness/fixtures/cassettes/tools_list/y.json": "recorded-streams",
    ".claude/settings.json": "local-secrets",
    ".env.local": "local-secrets",
    "deploy/server.pem": "local-secrets",
    "deploy/server.key": "local-secrets",
    "docs/archive.jsonl.gz": "unscannable",
    ".public-allow": "private-tooling",
}

#: Files that must survive, including near misses of the rules above.
INCLUDED = [
    "agent/pkg/__init__.py",
    "harness/sit_eval/scoring.py",                       # names a key field, reviewed (harness code)
    "spec/answer_key.schema.json",                       # the schema, not a key
    "tests/test_something.py",
    "tests/fixtures/review_example.json",
    "docs/ARCHITECTURE.md",
    "docs/live_runs/QUALITY_COMPARISON.md",
    "docs/live_runs/run_a/report.md",
    "docs/live_runs/run_a/report.json",
    "docs/live_runs/run_a/manifest.json",
    "docs/live_runs/run_a/MEASUREMENT.md",
    "docs/live_runs/run_a/effective_config.json",
    "docs/live_runs/run_a/anchors.json",
    "eval/synthetic/demo/design_v1.md",
    "eval/synthetic/demo/design_v2.md",
    "README.md",
    "Makefile",
    "pyproject.toml",
    ".gitignore",
]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def _make_repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(root, "add", "--all", ".")
    _git(root, "commit", "-q", "--no-verify", "-m", "fixture")
    return root


def _fixture_files() -> dict[str, str]:
    files = {p: "plain content\n" for p in [*EXCLUDED, *INCLUDED]}
    files["notes/key_draft_notes.md"] = "F01 core_insight: drafted text\n"
    files["harness/sit_eval/scoring.py"] = "# reads scored_run_ready from the key\n"
    return files


def _run(repo: Path, target: Path, **kw) -> tuple[int, list[str]]:
    lines: list[str] = []
    kw.setdefault("user", "nobodyuser")
    kw.setdefault("home", "/nonexistent/home/nobodyuser")
    kw.setdefault("today", "2026-10-03")
    rc = eps.export(repo, target, out=lines.append, **kw)
    return rc, lines


@pytest.mark.parametrize(("path", "group"), sorted(EXCLUDED.items()))
def test_each_excluded_kind_is_classified(path: str, group: str) -> None:
    blob = b"F01 core_insight: drafted text\n" if path == "notes/key_draft_notes.md" else b"x\n"
    rule = eps.classify(path, blob)
    assert rule is not None and rule.group == group, (path, rule)


@pytest.mark.parametrize("path", INCLUDED)
def test_included_files_are_not_classified(path: str) -> None:
    assert eps.classify(path, b"x\n") is None


def test_export_drops_every_excluded_kind_and_keeps_the_rest(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo", _fixture_files())
    target = tmp_path / "out"
    rc, lines = _run(repo, target)
    assert rc == 0, "\n".join(lines)
    exported = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
    assert not exported & set(EXCLUDED)
    assert set(INCLUDED) <= exported
    assert exported == set(INCLUDED) | {"PUBLIC_SNAPSHOT.md"}
    log = "\n".join(lines)
    assert "item_x" not in log                               # sealed names are withheld from the log
    assert "eval/blind/** (2 files, names withheld)" in log
    assert "EXCLUDE  answer-keys      notes/key_draft_notes.md" in log
    note = (target / "PUBLIC_SNAPSHOT.md").read_text(encoding="utf-8")
    sha = _git(repo, "rev-parse", "HEAD").strip()
    assert sha in note and "2026-10-03" in note and "QUALITY_COMPARISON.md" in note and "exploratory" in note
    assert "MCP API key is not in this tree" in note


def test_export_reads_head_not_the_working_tree(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo", {"README.md": "committed\n"})
    (repo / "README.md").write_text("uncommitted edit\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("never exported\n", encoding="utf-8")
    rc, _ = _run(repo, tmp_path / "out", allow_dirty=True)
    assert rc == 0
    assert (tmp_path / "out" / "README.md").read_text(encoding="utf-8") == "committed\n"
    assert not (tmp_path / "out" / "untracked.txt").exists()


def test_scanner_flags_a_planted_64_char_token(tmp_path: Path) -> None:
    token = "".join(chr(ord("A") + i % 26) + str(i % 10) for i in range(32))   # 64 chars, built at run time
    assert len(token) == 64
    repo = _make_repo(tmp_path / "repo", {"README.md": "clean\n", "config/x.yaml": f"value: {token}\n"})
    rc, lines = _run(repo, tmp_path / "out")
    assert rc == 1
    log = "\n".join(lines)
    assert "FINDING token64:config/x.yaml  n=1 lengths={64: 1}  at line 1" in log
    assert token not in log                                  # the value itself is never printed
    assert "No commit made" in log
    rc2, lines2 = _run(repo, tmp_path / "out2", allow=["token64:config/x.yaml"], init_git=True)
    assert rc2 == 0, "\n".join(lines2)


def test_scanner_reports_json_fields_and_owner_paths(tmp_path: Path) -> None:
    home = "/" + "Users/someone"
    files = {"a.json": json.dumps({"run": {"config_root": f"{home}/repo/config"}})}
    repo = _make_repo(tmp_path / "repo", files)
    rc, lines = _run(repo, tmp_path / "out", user="someone", home=home)
    log = "\n".join(lines)
    assert rc == 1
    assert "FINDING owner-home:a.json" in log and "at $.run.config_root" in log
    assert "FINDING owner-user:a.json" in log and "FINDING home-path:a.json" in log


def test_scanner_passes_a_clean_tree_and_init_git_makes_one_commit(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo", {"README.md": "# clean\n", "agent/a.py": "x = 1\n" + "# " + "-" * 64 + "\n"})
    target = tmp_path / "out"
    rc, lines = _run(repo, target, init_git=True)
    assert rc == 0, "\n".join(lines)
    assert "scan clean" in lines
    log = _git(target, "log", "--format=%s").splitlines()
    sha = _git(repo, "rev-parse", "HEAD").strip()
    assert log == [f"Public snapshot of malcolm1232/SIT at {sha[:12]}"]
    assert _git(target, "remote").strip() == ""             # nothing to push to


def test_dirty_worktree_is_refused_unless_allowed(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo", {"README.md": "x\n"})
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(eps.UsageError, match="allow-dirty"):
        _run(repo, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    rc, lines = _run(repo, tmp_path / "out", allow_dirty=True)
    assert rc == 0 and any("worktree dirty" in ln for ln in lines)


def test_target_must_be_empty_and_outside_the_repo(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo", {"README.md": "x\n"})
    with pytest.raises(eps.UsageError, match="inside the repository"):
        _run(repo, repo / "export")
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "f").write_text("x", encoding="utf-8")
    with pytest.raises(eps.UsageError, match="not empty"):
        _run(repo, busy)


def test_allow_file_needs_a_reason(tmp_path: Path) -> None:
    good = tmp_path / "good"
    good.write_text("# comment\n\nhex64:*  # sha256 digests\n", encoding="utf-8")
    assert eps.read_allow_file(good) == ["hex64:*"]
    bad = tmp_path / "bad"
    bad.write_text("hex64:*\n", encoding="utf-8")
    with pytest.raises(eps.UsageError, match="reason"):
        eps.read_allow_file(bad)


def test_main_exit_code_on_dirty_worktree(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo", {"README.md": "x\n"})
    (repo / "new.txt").write_text("untracked\n", encoding="utf-8")
    assert eps.main(["--repo", str(repo), "--target", str(tmp_path / "out")]) == 2
