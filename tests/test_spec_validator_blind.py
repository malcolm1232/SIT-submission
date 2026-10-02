"""``spec/validate_examples.py`` leaves the held-out tier alone unless it is asked (docs/SEALING.md §6 rule 1).

Every test runs a copy of the real validator inside a temporary tree. A tripwire wraps the calls that list,
stat or open a path, and trips on any path at or under that tree's ``eval/blind``. Nothing here touches the
repository's own ``eval/blind``.
"""

from __future__ import annotations

import builtins
import json
import os
import runpy
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

SPEC = Path(__file__).resolve().parents[1] / "spec"
SPEC_FILES = ("validate_examples.py", "taxonomy.yaml", "finding.schema.json", "answer_key.schema.json", "README.md")
NOTICE = "record the access in eval/blind/ACCESS_LOG.md"


class Tripwire:
    """Records every guarded call on a path at or under ``root``; raises before the real call when ``strict``."""

    def __init__(self, root: Path, *, strict: bool) -> None:
        self.root = str(root)
        self.strict = strict
        self.hits: list[tuple[str, str]] = []

    def _guards(self, path: Any) -> bool:
        if isinstance(path, int):  # a file descriptor, not a path
            return False
        p = os.path.abspath(os.fsdecode(path))
        return p == self.root or p.startswith(self.root + os.sep)

    def wrap(self, name: str, real: Callable[..., Any]) -> Callable[..., Any]:
        def guarded(path: Any = ".", *args: Any, **kwargs: Any) -> Any:
            if self._guards(path):
                self.hits.append((name, os.fsdecode(path)))
                if self.strict:
                    raise AssertionError(f"{name}() touched the held-out tier: {os.fsdecode(path)}")
            return real(path, *args, **kwargs)

        return guarded

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(builtins, "open", self.wrap("open", builtins.open))
        for name in ("open", "scandir", "listdir", "stat", "lstat"):
            monkeypatch.setattr(os, name, self.wrap(f"os.{name}", getattr(os, name)))


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A repository-shaped tree: the real spec files, one open tier and one held-out tier, one empty key each."""
    (tmp_path / "spec").mkdir()
    for name in SPEC_FILES:
        shutil.copy(SPEC / name, tmp_path / "spec" / name)
    for tier, item, body in (("synthetic", "demo", {"flaws": []}), ("blind", "item_a", {"defects": []})):
        (tmp_path / "eval" / tier / item).mkdir(parents=True)
        (tmp_path / "eval" / tier / item / "answer_key.json").write_text(json.dumps(body), encoding="utf-8")
    return tmp_path


def run_validator(
    tree: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    strict: bool,
    argv: list[str],
    direct: bool,
    init_globals: dict[str, Any] | None = None,
) -> Tripwire:
    """Run the tree's validator in this process: ``direct`` as ``python3 spec/validate_examples.py``, else as a
    runpy caller such as the converter does."""
    script = str(tree / "spec" / "validate_examples.py")
    trip = Tripwire(tree / "eval" / "blind", strict=strict)
    monkeypatch.setattr(sys, "argv", [script, *argv] if direct else argv)
    trip.install(monkeypatch)
    if direct:
        runpy.run_path(script, run_name="__main__")
    else:
        runpy.run_path(script, init_globals=init_globals)
    return trip


def test_direct_run_with_no_flags_never_touches_blind(
    tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    trip = run_validator(tree, monkeypatch, strict=True, argv=[], direct=True)
    out, err = capsys.readouterr()
    assert trip.hits == []
    assert "ALL CHECKS PASSED" in out
    assert "eval/synthetic/demo/answer_key.json: 0 flaws mapped" in out
    assert "eval/blind/item_a" not in out
    assert "eval/blind not read" in out
    assert NOTICE not in err


def test_runpy_caller_never_touches_blind_and_its_command_line_is_not_read(
    tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    caller_argv = ["convert_answer_keys.py", "--tier", "blind", "--include-blind"]
    trip = run_validator(tree, monkeypatch, strict=True, argv=caller_argv, direct=False)
    out, err = capsys.readouterr()
    assert trip.hits == []
    assert "ALL CHECKS PASSED" in out
    assert "eval/blind/item_a" not in out
    assert NOTICE not in err


def test_include_blind_flag_reads_blind_and_prints_the_notice(
    tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    trip = run_validator(tree, monkeypatch, strict=False, argv=["--include-blind"], direct=True)
    out, err = capsys.readouterr()
    blind_key = str(tree / "eval" / "blind" / "item_a" / "answer_key.json")
    assert ("open", blind_key) in trip.hits  # the tripwire does see a read of the held-out key
    assert "eval/blind/item_a/answer_key.json: 0 flaws mapped" in out
    assert "ALL CHECKS PASSED" in out
    assert [line for line in err.splitlines() if NOTICE in line] == [
        "NOTICE: this run reads the held-out answer keys under eval/blind; "
        "record the access in eval/blind/ACCESS_LOG.md (docs/SEALING.md §6)."
    ]


def test_runpy_caller_opts_in_through_init_globals(
    tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    caller_argv = ["convert_answer_keys.py"]
    opt_in = {"INCLUDE_BLIND": True}
    trip = run_validator(tree, monkeypatch, strict=False, argv=caller_argv, direct=False, init_globals=opt_in)
    out, err = capsys.readouterr()
    assert any(name == "open" and path.endswith("answer_key.json") for name, path in trip.hits)
    assert "eval/blind/item_a/answer_key.json: 0 flaws mapped" in out
    assert NOTICE in err


@pytest.mark.parametrize("flag", ["--blind", "--include", "--include-blin"])
def test_unknown_or_shortened_flag_is_refused(tree: Path, monkeypatch: pytest.MonkeyPatch, flag: str) -> None:
    with pytest.raises(SystemExit) as exc:
        run_validator(tree, monkeypatch, strict=True, argv=[flag], direct=True)
    assert exc.value.code == 2
