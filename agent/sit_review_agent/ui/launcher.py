"""Runs started from the page are ``dra review`` subprocesses (design note section 8).

The server never calls ``run_review`` in-process: the child is the CLI a person would type, in its
own session (a server crash or Ctrl-C does not end the run), writing the standard run directory.
The page shows the command (``display``) and ``ui/launch.json`` keeps it. Stop sends SIGINT, the
CLI's Ctrl-C path (exit 130, state flushed, ``dra resume`` continues). The child's console output
goes to ``runs/<id>/ui/console.txt``; the server writes nothing else outside ``ui/``.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sit_review_agent.ui.rundata import UI_DIR

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
DOC_SUFFIXES = (".pdf", ".txt", ".md")


@dataclass
class LaunchSpec:
    run_id: str
    document: Path
    profile: str | None = None
    v1: Path | None = None
    no_tools: bool = False
    #: The pasted link the document was downloaded from (``ui.fetch``); kept in ``ui/launch.json`` only.
    source_url: str | None = None

    def args(self) -> list[str]:
        """The arguments after ``dra``, exactly as a CLI user would type them."""
        out = ["review", str(self.document)]
        if self.profile:
            out += ["--profile", self.profile]
        if self.v1 is not None:
            out += ["--v1", str(self.v1)]
        if self.no_tools:
            out.append("--no-tools")
        return out + ["--run-id", self.run_id]

    def display(self, repo_root: Path) -> str:
        def word(a: str) -> str:            # a leading ~/ stays unquoted, so a shell still expands it
            return "~/" + shlex.quote(a[2:]) if a.startswith("~/") else shlex.quote(a)

        return " ".join(["dra", *[word(portable_arg(a, repo_root)) for a in self.args()]])


@dataclass
class Launched:
    run_id: str
    proc: Any
    display: str
    started_at: str
    exit_code: int | None = None


Popen = Callable[..., Any]


@dataclass
class Launcher:
    """Owns the children it started. ``popen`` is injectable (tests use a fake process)."""

    repo_root: Path
    popen: Popen = subprocess.Popen
    python: str = sys.executable
    runs: dict[str, Launched] = field(default_factory=dict)

    def alive(self) -> set[str]:
        out = set()
        for rid, item in self.runs.items():
            code = item.proc.poll()
            if code is None:
                out.add(rid)
            else:
                item.exit_code = code
        return out

    def exit_code(self, run_id: str) -> int | None:
        item = self.runs.get(run_id)
        if item is None:
            return None
        code = item.proc.poll()
        item.exit_code = code
        return code

    def start(self, spec: LaunchSpec, run_dir: Path) -> Launched:
        ui = run_dir / UI_DIR
        ui.mkdir(parents=True, exist_ok=True)
        display = spec.display(self.repo_root)
        started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        argv = [self.python, "-m", "sit_review_agent", *spec.args()]
        console = (ui / "console.txt").open("ab")
        try:
            proc = self.popen(argv, cwd=str(self.repo_root), stdin=subprocess.DEVNULL, stdout=console,
                              stderr=subprocess.STDOUT, start_new_session=True, env=dict(os.environ))
        finally:
            console.close()
        # The record carries no absolute path under the home folder (no user name): documents
        # relative to the runs directory, the command relative to the repo, anything else with ~.
        runs_dir = run_dir.parent
        (ui / "launch.json").write_text(json.dumps({
            "run_id": spec.run_id, "display": display,
            "args": [portable_arg(a, self.repo_root) for a in spec.args()], "started_at": started,
            "pid": getattr(proc, "pid", None), "document": portable_path(spec.document, runs_dir),
            "document_name": spec.document.name, "v1": portable_path(spec.v1, runs_dir) if spec.v1 else None,
            "profile": spec.profile, "no_tools": spec.no_tools, "source_url": spec.source_url}, indent=1),
            encoding="utf-8")
        item = Launched(spec.run_id, proc, display, started)
        self.runs[spec.run_id] = item
        return item

    def stop(self, run_id: str) -> bool:
        """SIGINT to a live child this server started; false when there is none."""
        item = self.runs.get(run_id)
        if item is None or item.proc.poll() is not None:
            return False
        item.proc.send_signal(signal.SIGINT)
        return True


def _relative(p: Path, base: Path) -> str | None:
    for a, b in ((p, base), (p.resolve(), base.resolve())):
        try:
            return str(a.relative_to(b))
        except ValueError:
            continue
    return None


def home_tilde(p: Path) -> str:
    """``p`` with the home folder written as ``~`` (no user name), else as given."""
    rel = _relative(p, Path.home())
    return str(p) if rel is None else ("~" if rel == "." else f"~/{rel}")


def portable_path(p: Path | str, runs_dir: Path) -> str:
    """A path for ``ui/launch.json``: relative to the runs directory when under it, else with the
    home folder as ``~``. A relative path is kept as given."""
    p = Path(p)
    if not p.is_absolute():
        return str(p)
    rel = _relative(p, runs_dir)
    return rel if rel is not None else home_tilde(p)


def portable_arg(a: str, repo_root: Path) -> str:
    """A command argument as shown and recorded: an absolute path relative to the repository (the
    child's working directory) when under it, else with the home folder as ``~``; other arguments
    unchanged."""
    p = Path(a)
    if not p.is_absolute():
        return a
    rel = _relative(p, repo_root)
    return rel if rel is not None else home_tilde(p)


def resolve_recorded(value: str, runs_dir: Path, repo_root: Path) -> list[Path]:
    """Where a path recorded by :func:`portable_path` (or an older absolute one) may be: ``~``
    expanded, a relative path under the runs directory, then under the repository."""
    if value.startswith("~"):
        return [Path(value).expanduser()]
    p = Path(value)
    return [p] if p.is_absolute() else [runs_dir / p, repo_root / p]


def safe_name(name: str, default: str = "document") -> str:
    base = SAFE_NAME_RE.sub("_", Path(name or "").name).strip("._") or default
    return base[:100]


def new_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"ui-{now.strftime('%y%m%d-%H%M%S')}-{os.urandom(2).hex()}"
