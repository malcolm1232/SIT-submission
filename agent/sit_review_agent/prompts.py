"""Prompt files: loading, hashing, the lock file, and rendering (REPRODUCIBILITY §4).

* Every prompt is a file in ``prompts/*.md`` (no prompt strings inline in Python).
* Rendered with Jinja ``StrictUndefined``: a missing variable is an error, never an empty string.
* ``prompts/PROMPTS.lock`` lists ``<sha256>  <file>`` for every prompt; ``bundle_sha256`` is the
  hash over the sorted ``(path, sha256)`` list and goes into the manifest. A stale lock fails
  ``tests/test_prompts.py``; regenerate with ``python -m sit_review_agent.prompts --write-lock``.
* ``prompt_hash`` of a call (``Finding.provenance.prompt_hash``) is the SHA-256 of the rendered text.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import jinja2

from sit_review_agent.errors import PromptError
from sit_review_agent.hashing import bundle_sha256, sha256_file, sha256_text
from sit_review_agent.paths import prompts_dir

LOCK_NAME = "PROMPTS.lock"
#: Prompt files every build must have (one per LLM phase plus the shared system prompt).
REQUIRED_PROMPTS = ("system.md", "understand.md", "plan.md", "research.md", "assess.md", "refine.md",
                    "verify.md", "report.md")
#: Files in prompts/ that are documentation, not prompts (not hashed into the bundle).
NON_PROMPT_FILES = frozenset({"README.md"})


@dataclass(frozen=True)
class RenderedPrompt:
    name: str
    text: str
    sha256: str          # prompt_hash


@dataclass
class PromptBundle:
    root: Path
    files: dict[str, str] = field(default_factory=dict)       # name -> sha256 of the file

    @classmethod
    def load(cls, root: str | Path | None = None) -> PromptBundle:
        r = Path(root) if root is not None else prompts_dir()
        missing = [n for n in REQUIRED_PROMPTS if not (r / n).is_file()]
        if missing:
            raise PromptError(f"missing prompt files in {r}: {missing}")
        files = {p.name: sha256_file(p) for p in sorted(r.glob("*.md")) if p.name not in NON_PROMPT_FILES}
        return cls(root=r, files=files)

    @property
    def bundle_sha256(self) -> str:
        return bundle_sha256((f"prompts/{n}", h) for n, h in self.files.items())

    def lock_text(self) -> str:
        return "".join(f"{h}  {n}\n" for n, h in sorted(self.files.items()))

    def check_lock(self) -> list[str]:
        """Differences between the files and ``PROMPTS.lock`` (empty = up to date)."""
        lock = self.root / LOCK_NAME
        if not lock.exists():
            return [f"{LOCK_NAME} missing"]
        want = {}
        for line in lock.read_text(encoding="utf-8").splitlines():
            if line.strip():
                h, _, n = line.partition("  ")
                want[n.strip()] = h.strip()
        out = [f"{n}: lock {want.get(n, 'absent')[:12]} != file {h[:12]}" for n, h in self.files.items()
               if want.get(n) != h]
        out += [f"{n}: in lock but no such prompt" for n in want if n not in self.files]
        return out

    def write_lock(self) -> Path:
        path = self.root / LOCK_NAME
        path.write_text(self.lock_text(), encoding="utf-8")
        return path

    def render(self, name: str, **variables: object) -> RenderedPrompt:
        """Render ``prompts/<name>`` with ``StrictUndefined``."""
        if name not in self.files:
            raise PromptError(f"unknown prompt {name!r}")
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(self.root)), undefined=jinja2.StrictUndefined,
                                 autoescape=False, keep_trailing_newline=True, trim_blocks=True, lstrip_blocks=True)
        try:
            text = env.get_template(name).render(**variables)
        except jinja2.UndefinedError as exc:
            raise PromptError(f"{name}: {exc}") from exc
        return RenderedPrompt(name=name, text=text, sha256=sha256_text(text))


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - tiny CLI
    args = sys.argv[1:] if argv is None else argv
    bundle = PromptBundle.load()
    if "--write-lock" in args:
        print(f"wrote {bundle.write_lock()} (bundle {bundle.bundle_sha256[:12]})")
        return 0
    problems = bundle.check_lock()
    print("\n".join(problems) if problems else f"{LOCK_NAME} up to date (bundle {bundle.bundle_sha256[:12]})")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
