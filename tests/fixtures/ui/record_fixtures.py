"""Record the page's ``progress.jsonl`` fixtures from real fixture runs on the fake gateway.

    .venv/bin/python tests/fixtures/ui/record_fixtures.py

Writes, beside this file:

* ``progress.jsonl``         the concurrent selftest path (``test_progress_events.concurrent_run``: understand,
                             plan and the four assess shards open together), exit 0;
* ``progress_cut.jsonl``     the same run with shard 2 cut by the stage 1 deadline (``cut_factory``), exit 0;
* ``progress_resume.jsonl``  a run that fails in understand (exit 3) and is resumed to exit 0; both halves
                             append to one file, so the sequence continues across the resume.

Every record is what ``sit_review_agent.progress.ProgressJsonl`` wrote, with two changes made here by
script: the scratch run root is replaced by ``<run_root>`` in every string, and the file is checked
before it is written: each record validates against ``spec/progress_event.schema.json``, and no string
of the run's model answers (``llm.jsonl``, read by ``test_progress_events.model_texts``) other than a
finding title appears anywhere in it. The clock is virtual (``FakeClock``) and steps a fixed amount on
every read, so ``t`` and ``run_s`` advance monotonically and the files are reproducible.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STEP_S = 0.5


def _records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _scrub(v: Any, root: str) -> Any:
    if isinstance(v, dict):
        return {k: _scrub(x, root) for k, x in v.items()}
    if isinstance(v, list):
        return [_scrub(x, root) for x in v]
    if isinstance(v, str):
        return v.replace(root, "<run_root>")
    return v


def _strings(v: Any, *, skip_key: str = "title") -> list[str]:
    out: list[str] = []
    if isinstance(v, dict):
        for k, x in v.items():
            if k != skip_key:
                out += _strings(x, skip_key=skip_key)
    elif isinstance(v, list):
        for x in v:
            out += _strings(x, skip_key=skip_key)
    elif isinstance(v, str):
        out.append(v)
    return out


async def _record(workdir: Path) -> dict[str, tuple[list[dict[str, Any]], Path]]:
    sys.path.insert(0, str(REPO / "tests"))
    from sit_review_agent.clock import FakeClock
    from sit_review_agent.orchestrator import RunRequest, resume_run, run_review
    from sit_review_agent.progress import ConsoleProgress
    from sit_review_agent.selftest import FIXTURE_DIR, selftest_config
    from test_progress_console import failing_understand_factory
    from test_progress_events import held_factory

    class SteppingClock(FakeClock):
        def monotonic(self) -> float:
            self.advance(STEP_S)
            return super().monotonic()

    pdf = FIXTURE_DIR / "design.pages.txt"
    out: dict[str, tuple[list[dict[str, Any]], Path]] = {}
    for name, cut in (("concurrent", False), ("cut", True)):
        root = workdir / name
        root.mkdir()
        clock = SteppingClock()
        path = root / "progress.jsonl"
        res = await run_review(RunRequest(pdf=pdf, config=selftest_config(root), run_id=f"ui_fixture_{name}"),
                               clock=clock, llm_factory=held_factory(cut),
                               progress=ConsoleProgress(clock=clock, stream=io.StringIO(), jsonl_path=path))
        assert res.exit_code == 0, (name, res.exit_code)
        out[name] = (_records(path), Path(res.run_dir))
    root = workdir / "resume"
    root.mkdir()
    cfg = selftest_config(root)
    path = root / "progress.jsonl"
    clock = SteppingClock()
    res = await run_review(RunRequest(pdf=pdf, config=cfg, run_id="ui_fixture_resume"), clock=clock,
                           llm_factory=failing_understand_factory,
                           progress=ConsoleProgress(clock=clock, stream=io.StringIO(), jsonl_path=path))
    assert res.exit_code == 3, res.exit_code
    clock2 = SteppingClock()
    res2 = await resume_run(res.run_dir, cfg, clock=clock2,
                            progress=ConsoleProgress(clock=clock2, stream=io.StringIO(), jsonl_path=path))
    assert res2.exit_code == 0, res2.exit_code
    out["resume"] = (_records(path), Path(res2.run_dir))
    return out


def main() -> int:
    import jsonschema

    from test_progress_events import model_texts

    schema = json.loads((REPO / "spec" / "progress_event.schema.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="sit-ui-fixtures-") as tmp:
        workdir = Path(tmp).resolve()
        recorded = asyncio.run(_record(workdir))
        for name, (records, run_dir) in recorded.items():
            prose = model_texts(run_dir)
            clean = [_scrub(r, str(workdir)) for r in records]
            for r in clean:
                jsonschema.validate(r, schema)
                for s in _strings(r):
                    leaked = [p for p in prose if p in s]
                    assert not leaked, f"{name}: seq {r['seq']} carries {len(leaked)} model text(s)"
                assert str(workdir) not in json.dumps(r), f"{name}: seq {r['seq']} keeps the scratch path"
            target = HERE / ("progress.jsonl" if name == "concurrent" else f"progress_{name}.jsonl")
            target.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in clean),
                              encoding="utf-8")
            types = sorted({r["type"] for r in clean})
            print(f"{target.name}: {len(clean)} records, seq 1..{clean[-1]['seq']}, {len(types)} types, "
                  f"last t {clean[-1]['t']:.1f} s, run_s {clean[-1]['run_s']}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(REPO / "tests"))
    sys.exit(main())
