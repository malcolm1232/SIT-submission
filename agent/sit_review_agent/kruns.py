"""``dra review <pdf> --k N``: the same review run N times as independent runs, for the stability
metrics (research/methodology/metrics.md §7.2; docs/REPRODUCIBILITY.md §9; eval/prereg.yaml
``runs_per_item``).

Semantics, from those documents:

* Each of the k runs is a complete, independent run (fresh run directory, fresh gateways, no
  shared state or cache), with the same input and the same effective config. Runs are sequential.
* Run IDs are ``<group_id>-k<i>``; ``--run-id`` names the group. Each run's ``manifest.json`` gets
  ``extra.k_index = i`` (1..k, REPRODUCIBILITY §8), and each run directory a ``k_group.json``
  naming its group.
* Intention-to-treat (methodology §6, REPRODUCIBILITY §9): a run that fails is counted and
  reported, never silently replaced or retried, and k is never extended. Later runs still start.
  Two things stop the group early: Ctrl-C (exit 130), and an error raised before a run directory
  exists (a config or input error, which every remaining run would hit too).
* The group manifest ``<run_root>/<group_id>.kgroup.json`` lists every run directory with its
  outcome, verdict, finding count, cost and wall time, and is rewritten after every run.

The stability metrics themselves (pairwise Jaccard of matched findings, detect-in-all-k) need the
answer key and the matcher, so they are computed by the evaluation harness from these run
directories; the summary here only reports verdict agreement and the spread of the counts.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sit_review_agent.clock import SystemClock, isoformat_z
from sit_review_agent.errors import AgentError, ExitCode
from sit_review_agent.hashing import sha256_file
from sit_review_agent.rundir import write_json_atomic

#: The code-set verdict of a run that produced no assessment (spec VerdictLabel).
NOT_ASSESSED = "not_assessed"


@dataclass
class KRun:
    k_index: int
    run_id: str
    run_dir: str | None = None
    status: str = "not started"         # completed | failed | not started
    exit_code: int | None = None
    outcome: str | None = None
    verdict: str | None = None
    findings: int | None = None
    cost_usd: float | None = None
    wall_s: float | None = None
    report_md: str | None = None
    error: str | None = None


@dataclass
class KGroup:
    group_id: str
    k: int
    input: str
    input_sha256: str | None
    created_utc: str
    run_root: str
    argv: list[str]
    cli_args: dict[str, Any]
    config_sha256: str
    mode: str
    runs: list[KRun] = field(default_factory=list)
    finished_utc: str | None = None
    stopped_early: str | None = None

    @property
    def path(self) -> Path:
        return Path(self.run_root) / f"{self.group_id}.kgroup.json"

    def summary(self) -> dict[str, Any]:
        done = [r for r in self.runs if r.status == "completed"]
        verdicts = Counter(r.verdict for r in done if r.verdict)
        counts = [r.findings for r in done if r.findings is not None]
        # Agreement is about fitness verdicts. `not_assessed` (a run with no assessment) is not one:
        # it never becomes the modal verdict, and it counts against agreement like any other run
        # that did not reach that verdict (intention-to-treat).
        fitness = Counter({v: n for v, n in verdicts.items() if v != NOT_ASSESSED})
        modal = fitness.most_common(1)[0] if fitness else None
        return {
            "runs_planned": self.k, "completed": len(done),
            "failed": sum(1 for r in self.runs if r.status == "failed"),
            "not_started": sum(1 for r in self.runs if r.status == "not started"),
            "verdicts": dict(verdicts), "not_assessed": verdicts.get(NOT_ASSESSED, 0),
            "verdict_agreement": round(modal[1] / len(done), 3) if modal and done else None,
            "findings_min": min(counts) if counts else None, "findings_max": max(counts) if counts else None,
            "findings_mean": round(sum(counts) / len(counts), 2) if counts else None,
            "cost_usd_total": round(sum(r.cost_usd or 0.0 for r in self.runs), 6),
            "wall_s_total": round(sum(r.wall_s or 0.0 for r in self.runs), 1),
        }

    def write(self) -> Path:
        data = {k: v for k, v in asdict(self).items() if k != "runs"}
        data["runs"] = [asdict(r) for r in self.runs]
        data["summary"] = self.summary()
        data["kind"] = "k-run group (dra review --k)"
        write_json_atomic(self.path, data)
        return self.path


def _read(path: Path) -> dict[str, Any]:
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def collect(run: KRun, run_dir: Path) -> None:
    """Fill ``run`` from its run directory (manifest and report)."""
    man = _read(run_dir / "manifest.json")
    rep = _read(run_dir / "report.json")
    run.run_dir = str(run_dir)
    run.outcome = man.get("outcome")
    run.cost_usd = ((man.get("usage") or {}).get("cost_usd"))
    if rep:
        run.verdict = (rep.get("verdict") or {}).get("label")
        run.findings = len(rep.get("findings") or [])
    if (run_dir / "report.md").is_file():
        run.report_md = str(run_dir / "report.md")
    if run.exit_code not in (None, 0) and (run_dir / "failure.json").is_file():
        run.error = str(_read(run_dir / "failure.json").get("message") or "")[:500] or run.error


def mark_run(run_dir: Path, group: KGroup, k_index: int) -> None:
    """``extra.k_index`` in the run's manifest and ``k_group.json`` next to it."""
    write_json_atomic(run_dir / "k_group.json", {"group_id": group.group_id, "k_index": k_index, "k": group.k,
                                                 "group_manifest": str(group.path)})
    man = run_dir / "manifest.json"
    data = _read(man)
    if data:
        data.setdefault("extra", {})["k_index"] = k_index
        write_json_atomic(man, data)


def run_group(request: Any, k: int, *, group_id: str | None = None,
              runner: Callable[[Any], Any] | None = None, echo: Callable[[str], None] | None = None) -> KGroup:
    """Run ``request`` (an ``orchestrator.RunRequest``; its ``run_id`` is ignored) ``k`` times.
    ``runner(request) -> RunOutcome`` defaults to ``asyncio.run(run_review(request))``. Re-raises an
    :class:`AgentError` raised before the first run directory exists (nothing ran), and
    ``KeyboardInterrupt``; returns the group otherwise."""
    from dataclasses import replace

    from sit_review_agent.orchestrator import new_run_id, run_review

    if k < 1:
        raise ValueError("k must be at least 1")
    say = echo or (lambda s: print(s, file=sys.stderr, flush=True))
    run = runner or (lambda req: asyncio.run(run_review(req)))
    cfg = request.config
    created = isoformat_z(SystemClock().now_utc())
    gid = group_id or new_run_id(created)
    pdf = Path(request.pdf)
    group = KGroup(group_id=gid, k=k, input=str(pdf), input_sha256=sha256_file(pdf) if pdf.is_file() else None,
                   created_utc=created, run_root=str(cfg.resolve_repo_path(cfg.agent.run_root)),
                   argv=list(sys.argv[1:]), cli_args=dict(cfg.cli_args), config_sha256=cfg.sha256(),
                   mode=str(request.mode), runs=[KRun(k_index=i, run_id=f"{gid}-k{i}") for i in range(1, k + 1)])
    Path(group.run_root).mkdir(parents=True, exist_ok=True)
    group.write()
    for kr in group.runs:
        say(f"--- k-run {kr.k_index}/{k}: {kr.run_id}")
        t0 = time.monotonic()
        try:
            outcome = run(replace(request, run_id=kr.run_id))
        except KeyboardInterrupt:
            kr.status, kr.exit_code, kr.error = "failed", int(ExitCode.SIGINT), "interrupted"
            group.stopped_early = f"interrupted during run {kr.k_index}"
            _finish(group, kr, t0)
            raise
        except AgentError as exc:
            # Raised, not returned: the run failed before or while its directory was set up, so
            # every later run would fail the same way. Recorded, then the group stops.
            kr.status, kr.exit_code, kr.error = "failed", int(exc.exit_code), f"{type(exc).__name__}: {exc}"[:500]
            rd = Path(group.run_root) / kr.run_id
            if rd.is_dir():
                collect(kr, rd)
            group.stopped_early = f"run {kr.k_index} failed during setup: {kr.error}"
            group.finished_utc = isoformat_z(SystemClock().now_utc())
            _finish(group, kr, t0)
            if kr.k_index == 1:
                raise
            return group
        kr.exit_code = int(outcome.exit_code)
        kr.status = "completed" if kr.exit_code == 0 else "failed"
        collect(kr, Path(outcome.run_dir))
        mark_run(Path(outcome.run_dir), group, kr.k_index)
        _finish(group, kr, t0)
        if kr.exit_code == int(ExitCode.SIGINT):
            group.stopped_early = f"interrupted during run {kr.k_index}"
            break
    group.finished_utc = isoformat_z(SystemClock().now_utc())
    group.write()
    return group


def _finish(group: KGroup, kr: KRun, t0: float) -> None:
    kr.wall_s = round(time.monotonic() - t0, 1)
    group.write()


def group_exit_code(group: KGroup) -> int:
    """0 when every run completed; otherwise the first failed run's exit code (130 if stopped by
    Ctrl-C)."""
    if group.stopped_early and group.stopped_early.startswith("interrupted"):
        return int(ExitCode.SIGINT)
    for r in group.runs:
        if r.exit_code not in (None, 0):
            return int(r.exit_code)
    return 0


def format_group(group: KGroup) -> str:
    """The per-run summary table printed after ``--k``."""
    lines = [f"k-run group {group.group_id}: {group.k} run(s) of {Path(group.input).name}", "",
             f"{'k':>2}  {'run':<36} {'outcome':<20} {'verdict':<22} {'findings':>8} {'cost $':>8} {'wall s':>8}"]
    for r in group.runs:
        outcome = r.outcome or (r.status if r.exit_code in (None, 0) else f"{r.status} (exit {r.exit_code})")
        lines.append(f"{r.k_index:>2}  {r.run_id[:36]:<36} {str(outcome)[:20]:<20} {str(r.verdict or '-')[:22]:<22} "
                     f"{'-' if r.findings is None else r.findings:>8} "
                     f"{'-' if r.cost_usd is None else f'{r.cost_usd:.2f}':>8} "
                     f"{'-' if r.wall_s is None else f'{r.wall_s:.1f}':>8}")
    s = group.summary()
    agree = "-" if s["verdict_agreement"] is None else f"{s['verdict_agreement']:.2f}"
    unassessed = f", not assessed {s['not_assessed']}" if s["not_assessed"] else ""
    lines += ["", f"completed {s['completed']}/{s['runs_planned']}{unassessed}, failed {s['failed']}, not started "
                  f"{s['not_started']}; verdict agreement {agree}; findings "
                  f"{s['findings_min']}-{s['findings_max']} (mean {s['findings_mean']}); "
                  f"cost ${s['cost_usd_total']:.2f}; wall {s['wall_s_total']:.1f} s"]
    if group.stopped_early:
        lines.append(f"stopped early: {group.stopped_early}")
    lines.append(f"group manifest: {group.path}")
    return "\n".join(lines)
