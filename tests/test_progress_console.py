"""The console lines of the progress stream stay byte for byte what they were before the structured
events were added (UI design note section 5: "all additive and all keeping the console line unchanged").

``tests/fixtures/progress/console_<scenario>.txt`` were written by this module's ``--write`` mode on
the code of commit 70bd658, before ``ProgressEvent`` gained its fields, from fixture runs on the fake
gateway: the selftest run, a run whose assess shard of ``claims_and_external_constraints`` is cut by
the stage 1 limit with one finished finding, and a run whose understand call fails (exit 3) followed
by its resume. The run directory is written as ``<tmp>``. Regenerated for the six assess shard groups
of USER_DECISIONS #40 (only the shard lines and the cut scenario's counts changed). Regenerate only
when a console line is meant to change:

    python tests/test_progress_console.py --write
"""

from __future__ import annotations

import asyncio
import io
import sys
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sit_review_agent.clock import FakeClock
from sit_review_agent.errors import LLMConnectionError, LLMDeadlineError
from sit_review_agent.llm.gateway import FakeResponse
from sit_review_agent.orchestrator import RunRequest, resume_run, run_review
from sit_review_agent.paths import repo_root
from sit_review_agent.progress import ConsoleProgress
from sit_review_agent.selftest import (
    FIXTURE_DIR,
    assess_answer,
    fixture_gateway,
    request_shard,
    selftest_config,
    shard_answer,
)

BASELINE = repo_root() / "tests" / "fixtures" / "progress"
SCENARIOS = ("selftest", "shard_cut", "fail_resume")
#: The criterion whose shard the cut scenario cuts. Its group holds one fixture finding (the e-mail
#: quota risk, which verify confirms, so the salvaged draft reaches the report) and a criterion with
#: none (assumptions_and_dependencies, which the cut leaves not assessed), in the four- and the
#: six-group configs alike.
CUT_CRITERION = "claims_and_external_constraints"


def configured_shards() -> list[Any]:
    """The assess shard groups of the repo config (what the fixture runs launch), in launch order."""
    from sit_review_agent.config import load_config

    cfg = load_config()
    return list(cfg.agent.assess.shards_for(cfg.criteria.ids()))


#: The number of assess shards a fixture run launches (four before decision #40, six since).
SHARD_COUNT = len(configured_shards())
#: The (1-based) shard the cut scenario cuts: the group of :data:`CUT_CRITERION`, so the scenario
#: follows any regrouping (shard 3 of the four-group config, shard 5 of the six-group one).
[CUT_SHARD] = [k for k, s in enumerate(configured_shards(), 1) if CUT_CRITERION in s.criteria]
#: The findings the cut stream had finished.
CUT_KEPT = 1


def console(clock: FakeClock, out: io.StringIO) -> ConsoleProgress:
    return ConsoleProgress(clock=clock, stream=out)


def cut_factory(kept: int = CUT_KEPT, shard: int = CUT_SHARD) -> Callable[..., Any]:
    """The fixture gateway with assess shard ``shard``'s call cut by the stage 1 limit after ``kept``
    finished findings (``LLMDeadlineError.partial``, as ``ClaudeCodeGateway`` raises it)."""

    def factory(rd: Any, clk: Any, prog: Any) -> Any:
        gw = fixture_gateway(rd, clock=clk)
        cfg_criteria = None
        groups: list[list[str]] = []
        import json

        data = json.loads(Path(rd.effective_config).read_text(encoding="utf-8"))
        cfg_criteria = [c["id"] for c in data["criteria"]["criteria"]]
        from sit_review_agent.config import AssessSettings

        groups = [list(s.criteria) for s in AssessSettings.model_validate(data["agent"]["assess"])
                  .shards_for(cfg_criteria)]
        original = list(gw.script["assess"])

        def wrap(entry: Any) -> Any:
            def resolve(ledger: list[dict[str, Any]], req: Any) -> FakeResponse:
                if req.conversation_id.endswith(f"-s{shard}"):
                    group = request_shard(req, groups) or []
                    findings = shard_answer(assess_answer(cfg_criteria), group)["findings"][:kept]
                    return FakeResponse(raises=LLMDeadlineError(
                        "the assess model call was cut after 263 s by the stage 1 limit (265 s on the run clock; "
                        "deadline 540 s; not retried past it)", call_id=f"llm-{gw._seq + 1:04d}", phase="assess",
                        partial={"findings": findings}))
                return entry(ledger, req) if callable(entry) else entry
            return resolve

        gw.script["assess"] = deque(wrap(e) for e in original)
        return gw

    return factory


def failing_understand_factory(rd: Any, clk: Any, prog: Any) -> Any:
    gw = fixture_gateway(rd, clock=clk)
    gw.script["understand"] = deque([FakeResponse(raises=LLMConnectionError("connection reset by the fixture"))])
    return gw


def normalise(text: str, root: Path) -> list[str]:
    return text.replace(str(root), "<tmp>").splitlines()


async def scenario(name: str, root: Path, *, progress: Callable[[FakeClock, io.StringIO], Any] = console
                   ) -> tuple[list[str], list[Any]]:
    """Run scenario ``name`` under ``root``; the normalised console lines and the sinks used."""
    pdf = FIXTURE_DIR / "design.pages.txt"
    cfg = selftest_config(root)
    out = io.StringIO()
    clock = FakeClock()
    sinks = [progress(clock, out)]
    if name == "selftest":
        res = await run_review(RunRequest(pdf=pdf, config=cfg, run_id="pc-selftest"), clock=clock, progress=sinks[0])
        assert res.exit_code == 0
    elif name == "shard_cut":
        res = await run_review(RunRequest(pdf=pdf, config=cfg, run_id="pc-cut"), clock=clock, progress=sinks[0],
                               llm_factory=cut_factory())
        assert res.exit_code == 0
    elif name == "fail_resume":
        res = await run_review(RunRequest(pdf=pdf, config=cfg, run_id="pc-fail"), clock=clock, progress=sinks[0],
                               llm_factory=failing_understand_factory)
        assert res.exit_code == 3
        clock2 = FakeClock()
        sinks.append(progress(clock2, out))
        res2 = await resume_run(res.run_dir, cfg, clock=clock2, progress=sinks[1])
        assert res2.exit_code == 0
    else:  # pragma: no cover - a typo in a test
        raise ValueError(name)
    return normalise(out.getvalue(), root), sinks


def baseline(name: str) -> list[str]:
    return (BASELINE / f"console_{name}.txt").read_text(encoding="utf-8").splitlines()


async def test_selftest_run_console_lines_are_unchanged(tmp_path: Path) -> None:
    lines, _ = await scenario("selftest", tmp_path)
    assert lines == baseline("selftest")


async def test_shard_cut_run_console_lines_are_unchanged(tmp_path: Path) -> None:
    lines, _ = await scenario("shard_cut", tmp_path)
    assert lines == baseline("shard_cut")


async def test_failed_and_resumed_run_console_lines_are_unchanged(tmp_path: Path) -> None:
    lines, _ = await scenario("fail_resume", tmp_path)
    assert lines == baseline("fail_resume")


def _write() -> None:  # pragma: no cover - the generator
    import tempfile

    BASELINE.mkdir(parents=True, exist_ok=True)
    for name in SCENARIOS:
        with tempfile.TemporaryDirectory() as tmp:
            lines, _ = asyncio.run(scenario(name, Path(tmp)))
        (BASELINE / f"console_{name}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"console_{name}.txt: {len(lines)} lines")


if __name__ == "__main__":  # pragma: no cover
    if sys.argv[1:] == ["--write"]:
        _write()
    else:
        print(__doc__)
