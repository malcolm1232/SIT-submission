"""The ``dra ui`` server: Starlette on 127.0.0.1, one static page, JSON and SSE routes.

Routes (design note section 9, W2)::

    GET  /                          the page (``/?run=<id>`` opens a run)
    GET  /static/<file>             index.html, tokens.css, app.css, app.js
    GET  /meta                      profiles, tools, backend, version, config file names, whether runs can start here
    GET  /tools                     per server: enabled, the last recorded warm-up and its time, tool count
    POST /tools/probe               the preflight warm-up of the enabled servers, on demand (never on page load)
    GET  /runs                      run directories under --runs-dir, newest first (a running row carries its
                                    stage, run clock and open calls from the last progress.jsonl records)
    POST /runs                      start ``dra review`` as a subprocess (multipart upload, or a pasted
                                    https link to a PDF in ``document_url``, fetched by ``ui.fetch``)
    GET  /runs/<id>                 one run's summary and status
    GET  /runs/<id>/events          progress.jsonl as server-sent events (Last-Event-ID or ?after=N)
    GET  /runs/<id>/report          report.json plus what the page joins from the run directory
    GET  /runs/<id>/coverage        the ``dra coverage`` map as JSON
    GET  /runs/<id>/explain/<FND>   the ``dra explain`` text
    GET  /runs/<id>/doc.pdf         the reviewed PDF, only if its SHA-256 matches the manifest
    GET  /runs/<id>/export.html     the review as one self-contained HTML file (``?download=1`` saves it)
    GET  /runs/<id>/report.md       the run's report.md, as a download
    GET  /runs/<id>/report.json     the run's report.json, as a download
    GET  /runs/<id>/outputs         whether Email is configured, and the share link (or how to get one)
    POST /runs/<id>/email           the export and report.md to one address (``ui.mail``)
    POST /runs/<id>/stop            SIGINT to a run this server started
    GET  /runs/<id>/chat            chat history and budget
    POST /runs/<id>/chat            one question, one model call (``ui.chat``)

No authentication: the server binds to loopback, and :func:`serve` refuses any other host unless
``allow_remote`` is set (then it prints a warning). Anyone who can reach the port can start runs
and spend chat budget; that is the documented limitation.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from sit_review_agent import __version__
from sit_review_agent.config import UrlPolicy
from sit_review_agent.ui import chat, events, export, fetch, mail, rundata, share
from sit_review_agent.ui.launcher import DOC_SUFFIXES, Launcher, LaunchSpec, new_run_id, safe_name

STATIC_DIR = Path(__file__).parent / "static"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
FINDING_ID_RE = r"^FND-\d+$"


class RemoteHostRefused(ValueError):
    pass


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_host(host: str, allow_remote: bool) -> str | None:
    """``None`` for a loopback host; the warning to print for a remote one with ``allow_remote``;
    raises :class:`RemoteHostRefused` otherwise."""
    if is_loopback(host):
        return None
    if not allow_remote:
        raise RemoteHostRefused(f"--host {host} is not a loopback address; the UI has no authentication, so it "
                                "binds to 127.0.0.1 only. Pass --allow-remote to bind elsewhere anyway.")
    return (f"WARNING: serving on {host} with no authentication. Anyone who can reach this port can start "
            "reviews, stop them and spend the chat budget.")


@dataclass
class UIState:
    runs_dir: Path
    repo_root: Path
    launcher: Launcher
    chat_client: chat.ChatClient
    can_launch: bool = True
    launch_note: str = ""
    profiles: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    commit: str | None = None
    poll_s: float = 0.25
    smtp: mail.SmtpConfig | None = None
    smtp_detail: str = ""
    bind_host: str = "127.0.0.1"
    port: int = 8765
    #: ``--runs-dir`` / ``--config`` as the server was started, repeated in the share restart line.
    ui_args: list[str] = field(default_factory=list)
    lan_ip: Callable[[], str | None] = share.lan_ipv4
    url_policy: UrlPolicy = field(default_factory=UrlPolicy)
    fetch_transport: Any = None
    resolve: Callable[[str], list[str]] = fetch.resolve_host
    #: The effective config as the server states it to the page: the LLM backend (``claude_code`` means
    #: "your subscription, no API key"), the model, the package version and the config files by name.
    backend: str | None = None
    model: str | None = None
    version: str = __version__
    config_files: list[str] = field(default_factory=list)
    #: The env var that holds the MCP key (``tools.auth_env``); its value is never read into the page.
    auth_env: str = "SIT_MCP_API_KEY"
    #: Runs the preflight warm-up of the enabled servers and returns its rows; None when the server has
    #: no agent configuration to probe with.
    probe: Callable[[], Awaitable[dict[str, Any]]] | None = None
    last_probe: dict[str, Any] | None = None


def _json(data: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status)


def _err(status: int, message: str) -> JSONResponse:
    return _json({"error": message}, status)


def build_app(state: UIState) -> Starlette:
    def run_dir_of(request: Request) -> Path | None:
        return rundata.run_path(state.runs_dir, request.path_params["run_id"])

    def alive(run_id: str) -> bool:
        return run_id in state.launcher.alive()

    async def index(request: Request) -> Response:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    async def meta(request: Request) -> Response:
        return _json({"profiles": state.profiles, "tools": state.tools, "can_launch": state.can_launch,
                      "launch_note": state.launch_note, "commit": state.commit, "version": state.version,
                      "backend": state.backend, "model": state.model, "config_files": list(state.config_files),
                      "auth_env": state.auth_env, "bind_host": state.bind_host, "port": state.port,
                      "ui_args": list(state.ui_args),
                      "runs_dir": str(state.runs_dir), "runs_dir_name": state.runs_dir.name,
                      "link_max_mb": fetch.MAX_BYTES // (1024 * 1024),
                      "chat": {"model": chat.MODEL, "effort": chat.EFFORT, "max_calls": chat.MAX_CALLS,
                               "max_cost_usd": chat.MAX_COST_USD, "label": chat.LABEL}})

    async def list_runs(request: Request) -> Response:
        return _json({"runs": rundata.list_runs(state.runs_dir, alive=state.launcher.alive())})

    async def tools_get(request: Request) -> Response:
        out = rundata.tools_status(state.runs_dir, state.tools)
        out.update(auth_env=state.auth_env, key_present=bool(os.environ.get(state.auth_env, "").strip()),
                   probe=state.last_probe)
        return _json(out)

    async def tools_probe(request: Request) -> Response:
        """The preflight warm-up (initialize + tools/list on every enabled server), only on this request:
        the page never probes on load, because the servers scale to zero and each probe is a cold start."""
        if state.probe is None:
            return _err(409, "This server has no agent configuration to probe with.")
        if not any(t.get("enabled") for t in state.tools):
            return _err(409, "No tool server is enabled in config/tools.yaml, so there is nothing to probe.")
        if not os.environ.get(state.auth_env, "").strip():
            return _err(409, f"{state.auth_env} is not set in this server's environment: export it in the shell "
                             "that starts dra ui, then probe again. The page never reads the key.")
        state.last_probe = await state.probe()
        return _json(state.last_probe)

    async def start_run(request: Request) -> Response:
        if not state.can_launch:
            return _err(409, state.launch_note or "Runs cannot be started from this server.")
        if state.launcher.alive():
            return _err(409, "A run started here is still in progress; stop it or wait for it to finish.")
        form = await request.form(max_part_size=MAX_UPLOAD_BYTES)
        doc = form.get("document")
        has_file = doc is not None and not isinstance(doc, str) and bool(doc.filename)
        link = str(form.get("document_url") or "").strip()
        if has_file and link:
            return _err(400, "Give a file or a link, not both.")
        if not has_file and not link:
            return _err(400, "No document was uploaded.")
        if has_file:
            name = safe_name(doc.filename)  # type: ignore[union-attr]
            if Path(name).suffix.lower() not in DOC_SUFFIXES:
                return _err(400, "The document must be a PDF, or a page-marked .txt or Markdown file.")
        prev = form.get("previous")
        prev_name = None
        if prev is not None and not isinstance(prev, str) and prev.filename:
            prev_name = safe_name(prev.filename, "previous")
            if Path(prev_name).suffix.lower() not in DOC_SUFFIXES:
                return _err(400, "The previous version must be a PDF, or a page-marked .txt or Markdown file.")
        profile = str(form.get("profile") or "").strip() or None
        if profile is not None and profile not in {p["name"] for p in state.profiles if p["name"]}:
            return _err(400, f"Unknown profile {profile!r}.")
        no_tools = str(form.get("no_tools") or "") in ("1", "true", "on")
        run_id = str(form.get("run_id") or "").strip() or new_run_id()
        if not rundata.RUN_ID_RE.match(run_id) or ".." in run_id:
            return _err(400, "The run ID may hold letters, digits, dot, dash and underscore only, and must start "
                             "with a letter or digit.")
        run_dir = state.runs_dir / run_id
        if run_dir.exists():
            return _err(409, f"A run directory named {run_id!r} already exists; choose another run ID.")
        if link:
            try:
                got = await fetch.fetch_pdf(link, state.url_policy, transport=state.fetch_transport,
                                            resolve=state.resolve)
            except fetch.LinkRefused as exc:
                return _err(400, exc.message)
            name, content = got.name, got.data
        else:
            content = await doc.read()  # type: ignore[union-attr]
        if run_dir.exists():
            return _err(409, f"A run directory named {run_id!r} already exists; choose another run ID.")
        inputs = run_dir / rundata.UI_DIR / "input"
        inputs.mkdir(parents=True, exist_ok=False)
        doc_path = inputs / name
        doc_path.write_bytes(content)
        v1_path = None
        if prev_name is not None and not isinstance(prev, str) and prev is not None:
            v1_dir = inputs / "previous"
            v1_dir.mkdir()
            v1_path = v1_dir / prev_name
            v1_path.write_bytes(await prev.read())
        spec = LaunchSpec(run_id=run_id, document=doc_path, profile=profile, v1=v1_path, no_tools=no_tools,
                          source_url=link or None)
        launched = state.launcher.start(spec, run_dir)
        return _json({"run_id": run_id, "command": launched.display}, 201)

    async def run_info(request: Request) -> Response:
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        info = rundata.summary(rd, process_alive=alive(rd.name))
        info["exit_code"] = state.launcher.exit_code(rd.name)
        info["chat"] = chat.budget(rd)
        return _json(info)

    async def run_events(request: Request) -> Response:
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        after = 0
        raw = request.headers.get("last-event-id") or request.query_params.get("after") or "0"
        try:
            after = max(0, int(raw))
        except ValueError:
            return _err(400, "after / Last-Event-ID must be a sequence number.")
        rid = rd.name

        def stop() -> bool:
            # Stop following when nothing more can be written: no live child of ours and either a
            # report exists or the directory has no event file at all.
            if alive(rid):
                return False
            return (rd / "report.json").is_file() or not (rd / "progress.jsonl").is_file() \
                or state.launcher.exit_code(rid) is not None

        async def gen() -> AsyncIterator[str]:
            yield "retry: 2000\n\n"
            async for ev in events.tail(rd / "progress.jsonl", after_seq=after, poll_s=state.poll_s, stop=stop):
                if await request.is_disconnected():
                    return
                yield events.sse_frame(ev)
            code = state.launcher.exit_code(rid)
            yield f"event: end\ndata: {{\"exit_code\": {'null' if code is None else code}}}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def run_report(request: Request) -> Response:
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        payload = rundata.review_payload(rd, state.runs_dir, state.repo_root)
        if payload is None:
            return _err(404, "This run has no report.json.")
        return _json(payload)

    async def run_coverage(request: Request) -> Response:
        rd = run_dir_of(request)
        if rd is None or not (rd / "report.json").is_file():
            return _err(404, "This run has no report.json.")
        from sit_review_agent.report.coverage import build_coverage

        return _json(build_coverage(rd).as_dict())

    async def run_explain(request: Request) -> Response:
        import re

        from sit_review_agent.report.explain import explain, format_explain

        rd = run_dir_of(request)
        fid = request.path_params["finding_id"]
        if rd is None or not re.match(FINDING_ID_RE, fid):
            return _err(404, "No such run or finding.")
        try:
            return PlainTextResponse(format_explain(explain(rd, fid)))
        except KeyError:
            return _err(404, f"{fid} is not in this run's report.json.")

    async def run_pdf(request: Request) -> Response:
        rd = run_dir_of(request)
        pdf = rundata.reviewed_pdf(rd, state.repo_root) if rd is not None else None
        if pdf is None:
            return _err(404, "The reviewed PDF is not available (moved, not a PDF, or its hash differs).")
        return FileResponse(pdf, media_type="application/pdf",
                            headers={"Content-Disposition": f'inline; filename="{safe_name(pdf.name)}"'})

    async def run_export(request: Request) -> Response:
        rd = run_dir_of(request)
        if rd is None or not (rd / "report.md").is_file():
            return _err(404, "This run has no report.md to export.")
        html = export.export_html(rd, replayed=rundata.summary(rd)["replayed"])
        how = "attachment" if request.query_params.get("download") == "1" else "inline"
        return Response(html, media_type="text/html; charset=utf-8",
                        headers={"Content-Disposition": f'{how}; filename="{export.export_name(rd.name)}"'})

    def raw_file(name: str, media_type: str) -> Any:
        async def handler(request: Request) -> Response:
            rd = run_dir_of(request)
            if rd is None or not (rd / name).is_file():
                return _err(404, f"This run has no {name}.")
            return FileResponse(rd / name, media_type=media_type,
                                headers={"Content-Disposition": f'attachment; filename="{rd.name}_{name}"'})
        return handler

    async def run_outputs(request: Request) -> Response:
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        exp = None
        if (rd / "report.md").is_file():
            size = len(export.export_html(rd, replayed=rundata.summary(rd)["replayed"]).encode("utf-8"))
            exp = {"size": f"{max(1, round(size / 1024))} KB", "has_chat": chat.log_path(rd).is_file(),
                   "name": export.export_name(rd.name)}
        return _json({"export": exp, "email": mail.status(state.smtp, state.smtp_detail),
                      "share": share.share_info(bind_host=state.bind_host, port=state.port, run_id=rd.name,
                                                ui_args=state.ui_args, lan_ip=state.lan_ip)})

    async def run_email(request: Request) -> Response:
        from starlette.concurrency import run_in_threadpool

        rd = run_dir_of(request)
        if rd is None or not (rd / "report.md").is_file():
            return _err(404, "This run has no report.md to send.")
        try:
            body = await request.json()
        except ValueError:
            return _err(400, "Expected a JSON body with the address.")
        to = str((body or {}).get("to") or "")
        html = export.export_html(rd, replayed=rundata.summary(rd)["replayed"])
        info = rundata.summary(rd)
        attachments = [(export.export_name(rd.name), html.encode("utf-8"), "text", "html"),
                       (f"{rd.name}_report.md", (rd / "report.md").read_bytes(), "text", "markdown")]
        try:
            row = await run_in_threadpool(mail.send, rd, to, state.smtp, title=str(info["document"] or rd.name),
                                          attachments=attachments)
        except mail.EmailRefused as exc:
            if exc.status == 409:
                return _err(409, f"{mail.NOT_CONFIGURED} ({mail.status(state.smtp, state.smtp_detail)['detail']}).")
            return _err(exc.status, exc.message)
        return _json(row)

    async def run_stop(request: Request) -> Response:
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        if not state.launcher.stop(rd.name):
            return _err(409, "This server has no live process for this run (a run started in a terminal is "
                             "stopped there with Ctrl-C).")
        return _json({"stopped": True, "signal": "SIGINT"})

    async def chat_get(request: Request) -> Response:
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        running = rundata.run_status(rd, process_alive=alive(rd.name)) == "running"
        return _json({"turns": chat.history(rd), "budget": chat.budget(rd), "running": running,
                      "has_report": (rd / "report.json").is_file()})

    async def chat_post(request: Request) -> Response:
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        try:
            body = await request.json()
        except ValueError:
            return _err(400, "Expected a JSON body with a question.")
        question = str((body or {}).get("question") or "")
        running = rundata.run_status(rd, process_alive=alive(rd.name)) == "running"
        try:
            return _json(await chat.ask(rd, question, state.chat_client, running=running))
        except chat.ChatRefused as exc:
            return _err(exc.status, exc.message)

    routes = [
        Route("/", index),
        Route("/meta", meta),
        Route("/tools", tools_get, methods=["GET"]),
        Route("/tools/probe", tools_probe, methods=["POST"]),
        Route("/runs", list_runs, methods=["GET"]),
        Route("/runs", start_run, methods=["POST"]),
        Route("/runs/{run_id}", run_info),
        Route("/runs/{run_id}/events", run_events),
        Route("/runs/{run_id}/report", run_report),
        Route("/runs/{run_id}/coverage", run_coverage),
        Route("/runs/{run_id}/explain/{finding_id}", run_explain),
        Route("/runs/{run_id}/doc.pdf", run_pdf),
        Route("/runs/{run_id}/export.html", run_export),
        Route("/runs/{run_id}/report.md", raw_file("report.md", "text/markdown; charset=utf-8")),
        Route("/runs/{run_id}/report.json", raw_file("report.json", "application/json")),
        Route("/runs/{run_id}/outputs", run_outputs),
        Route("/runs/{run_id}/email", run_email, methods=["POST"]),
        Route("/runs/{run_id}/stop", run_stop, methods=["POST"]),
        Route("/runs/{run_id}/chat", chat_get, methods=["GET"]),
        Route("/runs/{run_id}/chat", chat_post, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=STATIC_DIR), name="static"),
    ]
    app = Starlette(routes=routes)
    app.state.ui = state
    return app


# ------------------------------------------------------------------ building the state from config


def _git_commit(repo_root: Path) -> str | None:
    import subprocess

    try:
        out = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _profiles(config_path: Path | None) -> list[dict[str, Any]]:
    from sit_review_agent.config import ConfigOverrides, load_config

    names: list[str | None] = [None]
    base = load_config(config_path)
    pdir = Path(base.config_root) / "profiles"
    names += sorted(p.stem for p in pdir.glob("*.yaml")) if pdir.is_dir() else []
    out = []
    for n in names:
        try:
            cfg = load_config(config_path, ConfigOverrides(profile=n))
        except Exception:  # noqa: BLE001 - a broken profile is left out of the list, not fatal
            continue
        sr = cfg.stop_rules
        lim = sr.stage_limits_s
        out.append({"name": n or "", "label": n or "default", "deadline_s": sr.deadline_seconds,
                    "stage_limits_s": {"stage_1_end": lim.stage_1_end, "refine_end": lim.refine_end,
                                       "verdict_end": lim.verdict_end},
                    "effort": cfg.agent.effort.assess if hasattr(cfg.agent.effort, "assess") else None})
    return out


def build_state(*, runs_dir: Path | None, config_path: Path | None = None,
                chat_client: chat.ChatClient | None = None, launcher: Launcher | None = None) -> UIState:
    from sit_review_agent.config import load_config
    from sit_review_agent.paths import repo_root

    cfg = load_config(config_path)
    root = repo_root()
    run_root = cfg.resolve_repo_path(cfg.agent.run_root).resolve()
    rd = (runs_dir if runs_dir is not None else run_root).resolve()
    can_launch, note = True, ""
    if rd != run_root:
        can_launch = False
        note = (f"Runs start in the configured run root ({run_root}); this server reads {rd}, so the Start button "
                "is off. Serve the run root to start runs here.")
    tools = [{"name": s.name, "enabled": s.enabled} for s in cfg.tools.servers]
    smtp, smtp_detail = mail.load_smtp(Path(cfg.config_root) / "ui.yaml")
    files = sorted(cfg.source_files)
    try:
        files.append(str((Path(cfg.config_root) / "ui.yaml").relative_to(root)))
    except ValueError:
        files.append(str(Path(cfg.config_root) / "ui.yaml"))
    return UIState(runs_dir=rd, repo_root=root, launcher=launcher or Launcher(repo_root=root),
                   chat_client=chat_client or chat.ClaudeCodeChatClient.from_config(cfg),
                   can_launch=can_launch, launch_note=note, profiles=_profiles(config_path), tools=tools,
                   commit=_git_commit(root), smtp=smtp, smtp_detail=smtp_detail, url_policy=cfg.url_policy,
                   backend=cfg.agent.llm.backend, model=cfg.agent.model, config_files=files,
                   auth_env=cfg.tools.auth_env, probe=probe_with(cfg))


def probe_with(cfg: Any) -> Callable[[], Awaitable[dict[str, Any]]]:
    """The on-demand probe: the gateway's own warm-up (initialize + ``tools/list`` on every enabled
    server, the full cold-start allowance), then one row per server. Its progress lines are kept
    with the result after the key redaction the preflight uses."""

    async def probe() -> dict[str, Any]:
        import io

        from sit_review_agent.clock import SystemClock
        from sit_review_agent.progress import ConsoleProgress
        from sit_review_agent.tools.cassette import Redactor
        from sit_review_agent.tools.gateway import MCPToolGateway, ServerHealth

        out = io.StringIO()
        redact = Redactor.from_env((cfg.tools.auth_env,))
        clock = SystemClock()
        gw = MCPToolGateway(cfg.tools, cfg.endpoints.servers, clock=clock, progress=ConsoleProgress(stream=out))
        at = clock.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = []
        try:
            health = await gw.warm_up()
            for s in cfg.tools.enabled_servers():
                h = health.get(s.name, ServerHealth.DOWN)
                n = len(getattr(gw, "_tools", {}).get(s.name, []))
                err = getattr(gw, "last_errors", {}).get(s.name)
                rows.append({"name": s.name, "warm": h is ServerHealth.OK and n > 0, "tools": n, "health": h.value,
                             "error": redact.text(str(err)) if err else None})
        finally:
            await gw.aclose()
        return {"at": at, "servers": rows, "auth_failed": bool(getattr(gw, "auth_failed", False)),
                "lines": [redact.text(ln) for ln in out.getvalue().splitlines() if ln.strip()]}

    return probe


def serve(*, host: str, port: int, runs_dir: Path | None, config_path: Path | None, allow_remote: bool,
          echo: Any = print) -> None:
    warning = check_host(host, allow_remote)
    if warning:
        echo(warning)
    import uvicorn

    state = build_state(runs_dir=runs_dir, config_path=config_path)
    state.runs_dir.mkdir(parents=True, exist_ok=True)
    state.bind_host, state.port = host, port
    state.ui_args = [*(["--runs-dir", str(runs_dir)] if runs_dir is not None else []),
                     *(["--config", str(config_path)] if config_path is not None else [])]
    echo(f"SIT review UI on http://{host}:{port}/  (runs: {state.runs_dir}; Ctrl-C stops the server, not the runs)")
    uvicorn.run(build_app(state), host=host, port=port, log_level="warning")
