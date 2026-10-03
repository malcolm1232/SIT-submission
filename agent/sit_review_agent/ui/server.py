"""The ``dra ui`` server: Starlette on 127.0.0.1, one static page, JSON and SSE routes.

Routes (design note section 9, W2)::

    GET  /                          the page (``/?run=<id>`` opens a run)
    GET  /static/<file>             index.html, tokens.css, app.css, app.js
    GET  /meta                      profiles, tools, whether runs can be started here
    GET  /runs                      run directories under --runs-dir, newest first
    POST /runs                      start ``dra review`` as a subprocess (multipart upload)
    GET  /runs/<id>                 one run's summary and status
    GET  /runs/<id>/events          progress.jsonl as server-sent events (Last-Event-ID or ?after=N)
    GET  /runs/<id>/report          report.json plus what the page joins from the run directory
    GET  /runs/<id>/coverage        the ``dra coverage`` map as JSON
    GET  /runs/<id>/explain/<FND>   the ``dra explain`` text
    GET  /runs/<id>/doc.pdf         the reviewed PDF, only if its SHA-256 matches the manifest
    GET  /runs/<id>/export.html     the review as one self-contained HTML file (``?download=1`` saves it)
    GET  /runs/<id>/report.md       the run's report.md, as a download
    GET  /runs/<id>/report.json     the run's report.json, as a download
    POST /runs/<id>/stop            SIGINT to a run this server started
    GET  /runs/<id>/chat            chat history and budget
    POST /runs/<id>/chat            one question, one model call (``ui.chat``)

No authentication: the server binds to loopback, and :func:`serve` refuses any other host unless
``allow_remote`` is set (then it prints a warning). Anyone who can reach the port can start runs
and spend chat budget; that is the documented limitation.
"""

from __future__ import annotations

import ipaddress
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from sit_review_agent.ui import chat, events, export, rundata
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
                      "launch_note": state.launch_note, "commit": state.commit,
                      "runs_dir": str(state.runs_dir), "runs_dir_name": state.runs_dir.name,
                      "chat": {"model": chat.MODEL, "effort": chat.EFFORT, "max_calls": chat.MAX_CALLS,
                               "max_cost_usd": chat.MAX_COST_USD, "label": chat.LABEL}})

    async def list_runs(request: Request) -> Response:
        return _json({"runs": rundata.list_runs(state.runs_dir, alive=state.launcher.alive())})

    async def start_run(request: Request) -> Response:
        if not state.can_launch:
            return _err(409, state.launch_note or "Runs cannot be started from this server.")
        if state.launcher.alive():
            return _err(409, "A run started here is still in progress; stop it or wait for it to finish.")
        form = await request.form(max_part_size=MAX_UPLOAD_BYTES)
        doc = form.get("document")
        if doc is None or isinstance(doc, str) or not doc.filename:
            return _err(400, "No document was uploaded.")
        name = safe_name(doc.filename)
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
        inputs = run_dir / rundata.UI_DIR / "input"
        inputs.mkdir(parents=True, exist_ok=False)
        doc_path = inputs / name
        doc_path.write_bytes(await doc.read())
        v1_path = None
        if prev_name is not None and not isinstance(prev, str) and prev is not None:
            v1_dir = inputs / "previous"
            v1_dir.mkdir()
            v1_path = v1_dir / prev_name
            v1_path.write_bytes(await prev.read())
        spec = LaunchSpec(run_id=run_id, document=doc_path, profile=profile, v1=v1_path, no_tools=no_tools)
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
    return UIState(runs_dir=rd, repo_root=root, launcher=launcher or Launcher(repo_root=root),
                   chat_client=chat_client or chat.ClaudeCodeChatClient.from_config(cfg),
                   can_launch=can_launch, launch_note=note, profiles=_profiles(config_path), tools=tools,
                   commit=_git_commit(root))


def serve(*, host: str, port: int, runs_dir: Path | None, config_path: Path | None, allow_remote: bool,
          echo: Any = print) -> None:
    warning = check_host(host, allow_remote)
    if warning:
        echo(warning)
    import uvicorn

    state = build_state(runs_dir=runs_dir, config_path=config_path)
    state.runs_dir.mkdir(parents=True, exist_ok=True)
    echo(f"SIT review UI on http://{host}:{port}/  (runs: {state.runs_dir}; Ctrl-C stops the server, not the runs)")
    uvicorn.run(build_app(state), host=host, port=port, log_level="warning")
