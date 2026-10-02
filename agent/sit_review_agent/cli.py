"""``sit-review`` (alias ``dra``) command line.

Commands::

    sit-review run <pdf> [--v1 <pdf>] [--previous <run_dir>] [--config <agent.yaml|dir>]
                         [--replay <fixtures>] [--record] [--faults <schedule.yaml>]
                         [--deadline S] [--max-tool-calls N] [--disable-tool NAME]... [--no-tools]
                         [--plan-only] [--allow-fallback] [--mode dev|eval|rehearsal|demo]
    sit-review review ...                      (alias of run; the runbook's name)
    sit-review explain <run_dir> <finding_id>
    sit-review selftest
    sit-review resume <run_dir> [--accept-drift]
    sit-review preflight [--warm] [--keep-warm S]
    sit-review states                          (print the state machine as Mermaid)

Exit codes: :class:`~sit_review_agent.errors.ExitCode` (0 ok, 2 usage, 3 LLM unavailable,
4 stage crash, 5 resume drift, 130 interrupted).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer

from sit_review_agent.config import ConfigOverrides, Transport, load_config
from sit_review_agent.errors import AgentError, ExitCode

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="SIT design-review agent (custom state machine on the Anthropic SDK).")


def _fail(exc: AgentError) -> None:
    typer.echo(f"error: {exc}", err=True)
    raise typer.Exit(int(exc.exit_code))


def _not_built(what: str, exc: NotImplementedError) -> None:
    typer.echo(f"{what} is not implemented yet ({exc})", err=True)
    raise typer.Exit(int(ExitCode.STAGE_CRASH))


ConfigOpt = Annotated[Path | None, typer.Option("--config", help="config/agent.yaml or its directory")]


@app.command("run")
def run_cmd(
    pdf: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="design artefact to review")],
    v1: Annotated[Path | None, typer.Option("--v1", exists=True, dir_okay=False,
                                            help="previous version PDF (delta review)")] = None,
    previous: Annotated[Path | None, typer.Option("--previous", exists=True, file_okay=False,
                                                  help="frozen run directory of the previous version")] = None,
    config: ConfigOpt = None,
    replay: Annotated[Path | None, typer.Option("--replay", exists=True, file_okay=False,
                                                help="serve tool calls from this cassette directory")] = None,
    record: Annotated[bool, typer.Option("--record", help="record redacted tool cassettes")] = False,
    faults: Annotated[Path | None, typer.Option("--faults", exists=True, dir_okay=False,
                                                help="robustness fault schedule")] = None,
    deadline: Annotated[int | None, typer.Option("--deadline", help="wall-clock budget in seconds")] = None,
    max_tool_calls: Annotated[int | None, typer.Option("--max-tool-calls")] = None,
    disable_tool: Annotated[list[str] | None, typer.Option("--disable-tool", help="server name; repeatable")] = None,
    no_tools: Annotated[bool, typer.Option("--no-tools", help="doc-only review")] = False,
    plan_only: Annotated[bool, typer.Option("--plan-only", help="print the plan and stop (zero tool calls)")] = False,
    allow_fallback: Annotated[bool, typer.Option("--allow-fallback",
                                                 help="demo only: server-side refusal fallback (recorded)")] = False,
    mode: Annotated[str, typer.Option("--mode", help="dev | eval | rehearsal | demo")] = "dev",
) -> None:
    """Review a design artefact and write runs/<run_id>/report.{json,md}."""
    from sit_review_agent.orchestrator import RunRequest, run_review

    if record and replay is not None:
        typer.echo("error: --record and --replay are mutually exclusive", err=True)
        raise typer.Exit(int(ExitCode.USAGE))
    if v1 is not None and previous is not None:
        typer.echo("error: give --v1 or --previous, not both", err=True)
        raise typer.Exit(int(ExitCode.USAGE))
    transport = Transport.REPLAY if replay is not None else (Transport.RECORD if record else None)
    ov = ConfigOverrides(deadline_seconds=deadline, max_tool_calls=max_tool_calls,
                         disable_tools=tuple(disable_tool or ()), no_tools=no_tools,
                         allow_fallback=True if allow_fallback else None, transport=transport,
                         replay_fixtures=str(replay) if replay is not None else None,
                         fault_schedule=str(faults) if faults is not None else None)
    try:
        cfg = load_config(config, ov)
        outcome = asyncio.run(run_review(RunRequest(pdf=pdf, config=cfg, v1_pdf=v1, previous_run=previous,
                                                    mode=mode, plan_only=plan_only)))  # type: ignore[arg-type]
    except AgentError as exc:
        _fail(exc)
    except NotImplementedError as exc:
        _not_built("run", exc)
    typer.echo(str(outcome.report_md or outcome.run_dir))
    raise typer.Exit(outcome.exit_code)


app.command("review", help="Alias of run (docs/DEMO_DAY_RUNBOOK.md).")(run_cmd)


@app.command("explain")
def explain_cmd(run_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
                finding_id: Annotated[str, typer.Argument(help="e.g. FND-007")]) -> None:
    """Show a finding's anchors, evidence, tool calls, criterion and history (reads the run dir only)."""
    from sit_review_agent.report.explain import explain, format_explain

    try:
        typer.echo(format_explain(explain(run_dir, finding_id)))
    except KeyError:
        typer.echo(f"error: {finding_id} not in {run_dir}/report.json", err=True)
        raise typer.Exit(int(ExitCode.USAGE)) from None
    except NotImplementedError as exc:
        _not_built("explain", exc)


@app.command("selftest")
def selftest_cmd() -> None:
    """Run the pipeline offline (FakeGateway + ReplayGateway on a built-in fixture) and assert
    the invariants INV-03..INV-10. Needs no key and no network."""
    from sit_review_agent.selftest import run_selftest

    try:
        results = asyncio.run(run_selftest())
    except AgentError as exc:
        _fail(exc)
    except NotImplementedError as exc:
        _not_built("selftest", exc)
    failed = [r for r in results if not r.passed]
    for r in results:
        typer.echo(f"{r.inv_id}: {'skip' if r.skipped else ('ok' if r.passed else 'FAIL')} {'; '.join(r.problems)}")
    raise typer.Exit(int(ExitCode.STAGE_CRASH) if failed else 0)


@app.command("resume")
def resume_cmd(run_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False)], config: ConfigOpt = None,
               accept_drift: Annotated[bool, typer.Option("--accept-drift")] = False) -> None:
    """Continue a run from its last completed phase (ADR-009)."""
    from sit_review_agent.orchestrator import resume_run

    try:
        outcome = asyncio.run(resume_run(run_dir, load_config(config), accept_drift=accept_drift))
    except AgentError as exc:
        _fail(exc)
    except NotImplementedError as exc:
        _not_built("resume", exc)
    raise typer.Exit(outcome.exit_code)


@app.command("preflight")
def preflight_cmd(config: ConfigOpt = None, warm: Annotated[bool, typer.Option("--warm/--no-warm")] = False,
                  keep_warm: Annotated[int | None, typer.Option("--keep-warm", help="ping every S seconds")] = None,
                  ) -> None:
    """Check keys (by name), the model, each enabled MCP server, and fallback data (runbook §2-§3)."""
    from sit_review_agent.selftest import run_preflight

    try:
        ok = asyncio.run(run_preflight(load_config(config), warm=warm, keep_warm_s=keep_warm))
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
