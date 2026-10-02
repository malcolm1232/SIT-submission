"""``sit-review`` (alias ``dra``) command line.

Commands::

    sit-review run <pdf> [--v1 <pdf>] [--previous <run_dir>] [--config <agent.yaml|dir>] [--profile NAME]
                         [--replay <fixtures>] [--record] [--transport T] [--faults|--fault-schedule <yaml>]
                         [--deadline S] [--max-tool-calls N] [--disable-tool NAME]... [--no-tools]
                         [--plan-only] [--plan-approval] [--allow-fallback] [--mode dev|eval|rehearsal|demo]
                         [--run-id ID] [--k N]
    sit-review run --resume <run_dir> [--accept-drift]
    sit-review review ...                      (alias of run; the runbook's name)
    sit-review explain <run_dir> <finding_id>  (or: explain <finding_id> [--run <run_dir>], default latest run)
    sit-review coverage [<run_dir>|--run <run_dir>] [--depth N] [--json]   (default latest run)
    sit-review replay <run_dir> [--pdf <pdf>] [--v1 <pdf>] [--previous <run_dir>] [--run-id ID]
    sit-review selftest
    sit-review resume <run_dir> [--accept-drift]
    sit-review preflight [--warm/--no-warm] [--keep-warm S] [--profile NAME]
    sit-review states                          (print the state machine as Mermaid)

``--k N`` runs the review N times as independent runs (``kruns``); ``replay`` re-runs a recorded
run offline from its logs (``replay``); ``coverage`` prints the criteria x sections map
(``report.coverage``).

Exit codes: :class:`~sit_review_agent.errors.ExitCode` (0 ok, 2 usage, 3 LLM unavailable,
4 stage crash, 5 resume drift, 130 interrupted). ``replay`` exits 4 when the replay diverges
from the recording.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, TypeVar

import typer

from sit_review_agent.config import ConfigOverrides, EffectiveConfig, Transport, load_config
from sit_review_agent.errors import AgentError, ExitCode

T = TypeVar("T")

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="SIT design-review agent (custom state machine on the Anthropic SDK).")


def _fail(exc: AgentError) -> None:
    typer.echo(f"error: {exc}", err=True)
    raise typer.Exit(int(exc.exit_code))


def _not_built(what: str, exc: NotImplementedError) -> None:
    typer.echo(f"{what} is not implemented yet ({exc})", err=True)
    raise typer.Exit(int(ExitCode.STAGE_CRASH))


ConfigOpt = Annotated[Path | None, typer.Option("--config", help="config/agent.yaml or its directory")]
ProfileOpt = Annotated[str | None, typer.Option("--profile", help="overlay config/profiles/<NAME>.yaml (e.g. demo); "
                                                                  "recorded in the manifest, reused by resume")]


def _guarded(what: str, fn: Callable[[], T]) -> T:
    """Run ``fn``; typed errors exit with their code, Ctrl-C with 130, anything else with 4 and a
    one-line message (never a traceback, robustness INV-11)."""
    try:
        return fn()
    except AgentError as exc:
        _fail(exc)
    except NotImplementedError as exc:
        _not_built(what, exc)
    except KeyboardInterrupt:
        typer.echo("interrupted", err=True)
        raise typer.Exit(int(ExitCode.SIGINT)) from None
    except (typer.Exit, typer.Abort):
        raise
    except Exception as exc:  # noqa: BLE001 - INV-11: no traceback reaches the user
        typer.echo(f"error: internal error in {what}: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(int(ExitCode.STAGE_CRASH)) from None
    raise AssertionError("unreachable")  # pragma: no cover


def _resume_config(run_dir: Path, config: Path | None, extra: ConfigOverrides | None = None) -> EffectiveConfig:
    """The config a resumed run had: the run's recorded CLI overrides (``effective_config.json``
    ``cli_args``) applied to the config files (``--config`` or the run's config directory), plus
    any flags given now (which then show up as drift)."""
    data: dict[str, Any] = {}
    eff = run_dir / "effective_config.json"
    if eff.is_file():
        data = json.loads(eff.read_text(encoding="utf-8"))
    args = dict(data.get("cli_args") or {})
    if extra is not None:
        args.update(extra.model_dump(mode="json", exclude_defaults=True))
    if config is None and data.get("config_root") and (Path(data["config_root"]) / "agent.yaml").is_file():
        config = Path(data["config_root"])
    return load_config(config, ConfigOverrides.model_validate(args))


def _finish(outcome: Any) -> None:
    typer.echo(str(outcome.report_md or outcome.run_dir))
    raise typer.Exit(outcome.exit_code)


@app.command("run")
def run_cmd(
    pdf: Annotated[Path | None, typer.Argument(dir_okay=False, help="design artefact to review (PDF, or a "
                                               "page-marked .txt / Markdown file)")] = None,
    v1: Annotated[Path | None, typer.Option("--v1", exists=True, dir_okay=False,
                                            help="previous version PDF (delta review)")] = None,
    previous: Annotated[Path | None, typer.Option("--previous", exists=True, file_okay=False,
                                                  help="frozen run directory of the previous version")] = None,
    config: ConfigOpt = None,
    replay: Annotated[Path | None, typer.Option("--replay", exists=True, file_okay=False,
                                                help="serve tool calls from this cassette directory")] = None,
    record: Annotated[bool, typer.Option("--record", help="record redacted tool cassettes")] = False,
    transport: Annotated[Transport | None, typer.Option("--transport", help="live | record | replay | fake")] = None,
    faults: Annotated[str | None, typer.Option("--faults", "--fault-schedule",
                                               help="fault schedule file or scenario ID (tests/robustness/faults/"
                                                    "<ID>.yaml)")] = None,
    deadline: Annotated[int | None, typer.Option("--deadline", help="wall-clock budget in seconds")] = None,
    max_tool_calls: Annotated[int | None, typer.Option("--max-tool-calls")] = None,
    disable_tool: Annotated[list[str] | None, typer.Option("--disable-tool", help="server name; repeatable")] = None,
    no_tools: Annotated[bool, typer.Option("--no-tools", help="doc-only review")] = False,
    plan_only: Annotated[bool, typer.Option("--plan-only", help="print the plan and stop (zero tool calls)")] = False,
    plan_approval: Annotated[bool | None, typer.Option(
        "--plan-approval/--no-plan-approval", help="print the plan and wait for y/N before research")] = None,
    allow_fallback: Annotated[bool, typer.Option("--allow-fallback",
                                                 help="demo only: server-side refusal fallback (recorded)")] = False,
    mode: Annotated[str, typer.Option("--mode", help="dev | eval | rehearsal | demo")] = "dev",
    run_id: Annotated[str | None, typer.Option("--run-id", help="name of the run directory")] = None,
    resume: Annotated[str | None, typer.Option("--resume", help="continue this run (directory or run ID) "
                                                                "instead of starting one")] = None,
    accept_drift: Annotated[bool, typer.Option("--accept-drift",
                                               help="with --resume: accept hash drift (recorded)")] = False,
    profile: ProfileOpt = None,
    k: Annotated[int | None, typer.Option("--k", help="run the review K times as independent runs (stability; "
                                                      "run IDs <group>-k1..kK, --run-id names the group)")] = None,
) -> None:
    """Review a design artefact and write runs/<run_id>/report.{json,md}."""
    from sit_review_agent.orchestrator import RunRequest, resume_run, run_review

    def usage(msg: str) -> None:
        typer.echo(f"error: {msg}", err=True)
        raise typer.Exit(int(ExitCode.USAGE))

    if record and replay is not None:
        usage("--record and --replay are mutually exclusive")
    if v1 is not None and previous is not None:
        usage("give --v1 or --previous, not both")
    if mode not in ("dev", "eval", "rehearsal", "demo", "replay"):
        usage(f"--mode {mode!r}: expected dev | eval | rehearsal | demo")
    if accept_drift and resume is None:
        usage("--accept-drift only applies with --resume")
    if k is not None and k < 1:
        usage(f"--k {k}: expected a number of runs >= 1")
    if k is not None and resume is not None:
        usage("--k starts new runs; it cannot be combined with --resume")
    if k is not None and plan_only:
        usage("--k repeats complete reviews; it cannot be combined with --plan-only")
    if transport is None:
        transport = Transport.REPLAY if replay is not None else (Transport.RECORD if record else None)
    fault_file = _resolve_faults(faults) if faults is not None else None
    if faults is not None and fault_file is None:
        usage(f"--faults {faults}: no such file or scenario (tests/robustness/faults/{faults}.yaml)")
    ov = ConfigOverrides(deadline_seconds=deadline, max_tool_calls=max_tool_calls,
                         disable_tools=tuple(disable_tool or ()), no_tools=no_tools,
                         allow_fallback=True if allow_fallback else None, transport=transport,
                         replay_fixtures=str(replay) if replay is not None else None,
                         fault_schedule=str(fault_file) if fault_file is not None else None,
                         plan_approval=plan_approval, profile=profile)
    if resume is not None:
        if pdf is not None:
            usage("give a PDF or --resume <run_dir>, not both")
        res = _resolve_run_dir(resume, config)
        if res is None:
            usage(f"--resume {resume}: no such run directory or run ID")
        outcome = _guarded("resume", lambda: asyncio.run(resume_run(
            res, _resume_config(res, config, ov), accept_drift=accept_drift)))  # type: ignore[arg-type]
        _finish(outcome)
    if pdf is None:
        usage("missing the design artefact to review (or --resume <run_dir>)")
    if not pdf.is_file():  # type: ignore[union-attr]
        usage(f"input not found: {pdf}")
    doc = pdf

    def request() -> Any:
        return RunRequest(pdf=doc, config=load_config(config, ov), v1_pdf=v1, previous_run=previous,  # type: ignore[arg-type]
                          mode=mode, plan_only=plan_only, run_id=run_id)  # type: ignore[arg-type]

    if k is not None:
        from sit_review_agent.kruns import format_group, group_exit_code, run_group

        group = _guarded("run --k", lambda: run_group(request(), k, group_id=run_id))
        typer.echo(format_group(group))
        raise typer.Exit(group_exit_code(group))
    _finish(_guarded("run", lambda: asyncio.run(run_review(request()))))


app.command("review", help="Alias of run (docs/DEMO_DAY_RUNBOOK.md).")(run_cmd)


def _resolve_faults(value: str) -> Path | None:
    """A fault-schedule path, or a scenario ID under ``tests/robustness/faults/`` (runbook §7)."""
    from sit_review_agent.paths import repo_root

    for cand in (Path(value), repo_root() / "tests" / "robustness" / "faults" / f"{value}.yaml"):
        if cand.is_file():
            return cand
    return None


def _resolve_run_dir(value: str, config: Path | None) -> Path | None:
    """A run directory path, or a run ID under the configured ``run_root`` (``dra resume <run_id>``)."""
    p = Path(value)
    if p.is_dir():
        return p
    try:
        cfg = load_config(config)
    except AgentError:
        return None
    cand = cfg.resolve_repo_path(cfg.agent.run_root) / value
    return cand if cand.is_dir() else None


def _latest_run(config: Path | None) -> Path | None:
    cfg = load_config(config)
    root = cfg.resolve_repo_path(cfg.agent.run_root)
    runs = sorted((p for p in root.glob("*/report.json")), key=lambda p: p.stat().st_mtime) if root.is_dir() else []
    return runs[-1].parent if runs else None


@app.command("explain")
def explain_cmd(target: Annotated[str, typer.Argument(help="run directory, or the finding ID (then --run or the "
                                                      "latest run is used)")],
                finding_id: Annotated[str | None, typer.Argument(help="e.g. FND-007")] = None,
                run: Annotated[Path | None, typer.Option("--run", help="run directory (default: latest)")] = None,
                config: ConfigOpt = None) -> None:
    """Show a finding's anchors, evidence, tool calls, criterion and history (reads the run dir only)."""
    from sit_review_agent.report.explain import explain, format_explain

    if finding_id is None:
        finding_id, run_dir = target, run or _guarded("explain", lambda: _latest_run(config))
    else:
        run_dir = Path(target)
    if run_dir is None or not Path(run_dir).is_dir():
        typer.echo(f"error: run directory not found: {run_dir or '(no run with a report)'}", err=True)
        raise typer.Exit(int(ExitCode.USAGE))
    fid = finding_id

    def go() -> str:
        try:
            return format_explain(explain(run_dir, fid))
        except KeyError:
            typer.echo(f"error: {fid} not in {run_dir}/report.json", err=True)
            raise typer.Exit(int(ExitCode.USAGE)) from None

    typer.echo(_guarded("explain", go))


@app.command("coverage")
def coverage_cmd(target: Annotated[str | None, typer.Argument(help="run directory or run ID (default: latest run)")]
                 = None,
                 run: Annotated[Path | None, typer.Option("--run", help="run directory (default: latest)")] = None,
                 depth: Annotated[int, typer.Option("--depth", help="section-number levels per row (0: every "
                                                                    "section)")] = 1,
                 as_json: Annotated[bool, typer.Option("--json", help="print the map as JSON")] = False,
                 config: ConfigOpt = None) -> None:
    """Criteria x sections coverage map of a run, including "checked, no issue" (reads the run dir only)."""
    from sit_review_agent.report.coverage import build_coverage, format_coverage

    if target is not None and run is not None:
        typer.echo("error: give the run as an argument or with --run, not both", err=True)
        raise typer.Exit(int(ExitCode.USAGE))
    if depth < 0:
        typer.echo(f"error: --depth {depth}: expected 0 or more", err=True)
        raise typer.Exit(int(ExitCode.USAGE))
    if target is not None:
        run_dir = _resolve_run_dir(target, config)
    else:
        run_dir = run or _guarded("coverage", lambda: _latest_run(config))
    if run_dir is None or not Path(run_dir).is_dir() or not (Path(run_dir) / "report.json").is_file():
        typer.echo(f"error: no run with a report.json: {run_dir or target or '(no run with a report)'}", err=True)
        raise typer.Exit(int(ExitCode.USAGE))
    rd = Path(run_dir)

    def go() -> str:
        cm = build_coverage(rd, depth=depth)
        return json.dumps(cm.as_dict(), indent=1, ensure_ascii=False) if as_json else format_coverage(cm)

    typer.echo(_guarded("coverage", go))


@app.command("replay")
def replay_cmd(run: Annotated[str, typer.Argument(help="recorded run directory or run ID")],
               pdf: Annotated[Path | None, typer.Option("--pdf", dir_okay=False,
                                                        help="the reviewed document, when it is no longer at "
                                                             "the recorded path (checked by SHA-256)")] = None,
               v1: Annotated[Path | None, typer.Option("--v1", dir_okay=False,
                                                       help="delta runs: the prior version, if moved")] = None,
               previous: Annotated[Path | None, typer.Option("--previous", file_okay=False,
                                                             help="delta runs: the previous run, if moved")] = None,
               run_id: Annotated[str | None, typer.Option("--run-id", help="name of the replay's run directory")]
               = None,
               config: ConfigOpt = None) -> None:
    """Re-run a recorded run offline from its llm.jsonl and tools.jsonl; stamped "replayed evidence"."""
    from sit_review_agent.replay import replay_run

    src = _resolve_run_dir(run, config)
    if src is None:
        typer.echo(f"error: no such run directory or run ID: {run}", err=True)
        raise typer.Exit(int(ExitCode.USAGE))

    def go() -> Any:
        try:
            root: str | None = load_config(config).agent.run_root
        except AgentError:
            root = None
        return asyncio.run(replay_run(src, run_root=root, run_id=run_id, pdf=pdf, v1=v1, previous=previous))

    outcome = _guarded("replay", go)
    typer.echo(f"replayed {outcome.model_calls} model call(s) and {outcome.tool_calls} tool call(s) from {src}")
    typer.echo(outcome.message)
    for d in outcome.differences[1:10]:
        typer.echo(f"  differs: {d}")
    typer.echo(str(outcome.report_md or outcome.run_dir))
    raise typer.Exit(outcome.exit_code)


@app.command("selftest")
def selftest_cmd() -> None:
    """Run the pipeline offline (FakeGateway + ReplayGateway on a built-in fixture) and assert
    the invariants INV-03..INV-10. Needs no key and no network."""
    import time

    from sit_review_agent.selftest import run_selftest

    t0 = time.monotonic()
    results = _guarded("selftest", lambda: asyncio.run(run_selftest()))
    failed = [r for r in results if not r.passed]
    for r in results:
        status = "skip" if r.skipped else ("ok" if r.passed else "FAIL")
        typer.echo(f"{r.inv_id}: {status} {'; '.join(r.problems)}".rstrip())
    typer.echo(f"selftest {'FAILED' if failed else 'passed'} in {time.monotonic() - t0:.1f} s")
    raise typer.Exit(int(ExitCode.STAGE_CRASH) if failed else 0)


@app.command("resume")
def resume_cmd(run: Annotated[str, typer.Argument(help="run directory or run ID")], config: ConfigOpt = None,
               accept_drift: Annotated[bool, typer.Option("--accept-drift")] = False) -> None:
    """Continue a run from its last completed phase (ADR-009)."""
    from sit_review_agent.orchestrator import resume_run

    run_dir = _resolve_run_dir(run, config)
    if run_dir is None:
        typer.echo(f"error: no such run directory or run ID: {run}", err=True)
        raise typer.Exit(int(ExitCode.USAGE))
    rd = run_dir
    outcome = _guarded("resume", lambda: asyncio.run(resume_run(rd, _resume_config(rd, config),
                                                                accept_drift=accept_drift)))
    _finish(outcome)


@app.command("preflight")
def preflight_cmd(config: ConfigOpt = None, warm: Annotated[bool, typer.Option("--warm/--no-warm")] = False,
                  keep_warm: Annotated[int | None, typer.Option("--keep-warm", help="ping every S seconds")] = None,
                  profile: ProfileOpt = None) -> None:
    """Check keys (by name), the model, each enabled MCP server, and fallback data (runbook §2-§3)."""
    from sit_review_agent.selftest import run_preflight

    try:
        ok = asyncio.run(run_preflight(load_config(config, ConfigOverrides(profile=profile)), warm=warm,
                                       keep_warm_s=keep_warm))
    except AgentError as exc:
        _fail(exc)
    except NotImplementedError as exc:
        _not_built("preflight", exc)
    raise typer.Exit(0 if ok else int(ExitCode.USAGE))


@app.command("states")
def states_cmd() -> None:
    """Print the state machine as a Mermaid diagram."""
    from sit_review_agent.states import mermaid

    typer.echo(mermaid())


def main() -> None:
    """Console-script entry point."""
    try:
        app()
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(int(ExitCode.SIGINT))
