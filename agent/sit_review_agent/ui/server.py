"""The ``dra ui`` server: Starlette on 127.0.0.1, one static page, JSON and SSE routes.

Routes (design note section 9, W2)::

    GET  /                          the page (``/?run=<id>`` opens a run)
    GET  /static/<file>             index.html, tokens.css, app.css, app.js
    GET  /favicon.ico               the page's icon, from the static files
    GET  /meta                      profiles, tools, backend, version, config file names, whether runs can start here
    GET  /limits                    the stage limits and warnings a run would get at ``?profile=&deadline_s=``
    GET  /tools                     per server: enabled, the last recorded warm-up and its time, tool count
    POST /tools/probe               the preflight warm-up of the enabled servers, on demand (never on page load)
    GET  /runs                      run directories under --runs-dir, newest first (a running row carries its
                                    stage, run clock and open calls from the last progress.jsonl records)
    GET  /documents                 the sample documents of config/ui.yaml, offered as chips on the Review page
    GET  /documents/<name>          one of them, for the chip to fill the form (never to start a run)
    POST /runs                      start ``dra review`` as a subprocess (multipart upload, or a pasted
                                    https link to a PDF in ``document_url``, fetched by ``ui.fetch``)
    GET  /runs/<id>                 one run's summary and status
    GET  /runs/<id>/events          progress.jsonl as server-sent events (Last-Event-ID or ?after=N)
    GET  /runs/<id>/log             the last lines of progress.log as JSON (?after=<byte offset> follows it)
    GET  /runs/<id>/report          report.json plus what the page joins from the run directory
    GET  /runs/<id>/review.html     the run's Review tab: the export's review document (``export.review_fragment``,
                                    the same renderer and links), an HTML fragment with no script; a run without a
                                    report.md, or one whose files cannot be drawn, is answered with what is missing.
                                    ``?view=coverage|evidence|delta``: that tab's body with the same linker, the
                                    document kept hidden beside it for its links' targets
    GET  /runs/<id>/coverage        the ``dra coverage`` map as JSON
    GET  /runs/<id>/explain/<FND>   the ``dra explain`` text
    GET  /runs/<id>/stage/<name>    what one stage produced (``ingest`` ... ``report``, ``assess-N`` per shard), read
                                    from the run's files by ``ui.stages``; a file not written is named, never an error
    GET  /runs/<id>/funnel          every merged draft finding and its fate (kept, merged, withdrawn, dropped, reported)
    GET  /architecture              the Architectural design view: its words, with every number and name filled from the
                                    config and the code (``ui.architecture``)
    GET  /runs/<id>/glossary        the legend: the export's vocabulary (``ui.xref``) as plain text with its sources
    GET  /runs/<id>/doc.pdf         the reviewed PDF, only if its SHA-256 matches the manifest
    GET  /runs/<id>/export.html     the review as one self-contained, cross-linked HTML page with a sidebar of
                                    its eight parts (``?download=1`` saves the bundle, as export.zip does)
    GET  /runs/<id>/export.zip      the bundle: index.html (that page), document.pdf (the reviewed PDF, when its
                                    hash matches the manifest), report.md, report.json
    GET  /runs/<id>/report.md       the run's report.md, as a download
    GET  /runs/<id>/report.json     the run's report.json, as a download
    GET  /runs/<id>/outputs         the bundle the Download saves (name, file count, size), whether Email is
                                    configured, and the share link (or how to get one)
    POST /runs/<id>/email           the export and report.md to one address (``ui.mail``)
    POST /runs/<id>/stop            SIGINT to a run this server started
    GET  /runs/<id>/chat            chat history and budget
    POST /runs/<id>/chat            one question, one model call (``ui.chat``)
    POST /runs/<id>/chat/stream     the same, streamed as server-sent events: ``partial`` (the answer's text so far,
                                    as the model writes it), then ``done`` (the turn as /chat answers it, and the
                                    budget), ``stopped``, ``refused`` or ``error``; closing the stream stops the call
    POST /runs/<id>/chat/stop       Stop: ends the answer being streamed; its stream sends ``stopped``

No authentication: the server binds to loopback, and :func:`serve` refuses any other host unless
``allow_remote`` is set (then it prints a warning). Anyone who can reach the port can start runs
and spend chat budget; that is the documented limitation.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
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
from sit_review_agent.errors import ExitCode
from sit_review_agent.ui import chat, events, export, fetch, mail, rundata, share, stages
from sit_review_agent.ui.launcher import DOC_SUFFIXES, Launcher, LaunchSpec, new_run_id, safe_name

STATIC_DIR = Path(__file__).parent / "static"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
#: The Review form's deadline field, in seconds: from 2 minutes (one model attempt and the reserves of the
#: smallest profile do not fit below it) to 2 hours (twice the default profile's 3600 s).
DEADLINE_MIN_S = 120
DEADLINE_MAX_S = 7200
FINDING_ID_RE = r"^FND-\d+$"
#: How often a streamed chat answer that has nothing new checks that its page is still there.
CHAT_POLL_S = 0.5
#: What the Review tab says when a run has report.json (so the run page opens on its review) but the review document
#: cannot be drawn: no report.md (a run cut between the two files, or written by an agent older than report.md), or
#: files in a shape the renderer cannot read.
REVIEW_NO_MD = ("This run has report.json but no report.md, the file the review is drawn from, so the review cannot be "
                "shown here. The Coverage and Evidence tabs read report.json.")
REVIEW_NOT_YET = ("This run has no report yet: neither report.md nor report.json is in its directory (a run in "
                  "progress, or one that ended before its report was written). The Run log shows how far it got.")
REVIEW_UNREADABLE = ("This run's report.md or report.json is in a shape the review page cannot read, so the review "
                     "cannot be shown here; report.md and report.json are its own files")


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
    #: The sample documents of ``config/ui.yaml`` ``documents:`` (:func:`load_documents`): the Review page's chips.
    documents: list[dict[str, Any]] = field(default_factory=list)
    #: Each profile's ``StopRulesConfig`` by name ("" is the default), for ``GET /limits``: the stage limits
    #: and warnings the runtime would give a run at another deadline, computed by the runtime's own functions.
    stop_rules: dict[str, Any] = field(default_factory=dict)
    #: The Architectural design view (``ui.architecture.view``), built once from the config; None until first read.
    architecture: dict[str, Any] | None = None
    #: ``--config`` as the server was started (None: the default config/agent.yaml), for the architecture view.
    config_path: Path | None = None
    #: The answer being streamed per run (run ID -> the event its Stop sets): one at a time per run.
    chat_stops: dict[str, Any] = field(default_factory=dict)


def tools_key_missing(state: UIState) -> str | None:
    """Why a run with tools would exit before its first model call, or ``None``: an enabled MCP server
    and no ``auth_env`` key in this server's environment (the child inherits it; ``orchestrator.
    _run_check_tool_key`` refuses the same case with exit 2). Names the variable, never its value."""
    servers = [t["name"] for t in state.tools if t.get("enabled")]
    if not servers or os.environ.get(state.auth_env, "").strip():
        return None
    return (f"{state.auth_env} is not set in this server's environment, and the enabled tool servers "
            f"({', '.join(servers)}) need it, so a run with tools would exit before its first model call.")


def tools_key_fix(state: UIState) -> str:
    """What to do about :func:`tools_key_missing`, said after it."""
    return (f"Tick Document only (--no-tools), or stop this server, run export {state.auth_env}=<key> in its shell "
            "and start dra ui again. The page never reads the key.")


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

    async def favicon(request: Request) -> Response:
        return FileResponse(STATIC_DIR / "favicon.ico", media_type="image/x-icon",
                            headers={"Cache-Control": "max-age=86400"})

    async def architecture_get(request: Request) -> Response:
        if state.architecture is None:
            state.architecture = architecture_view(state.config_path)
        return _json(state.architecture)

    async def meta(request: Request) -> Response:
        return _json({"profiles": state.profiles, "tools": state.tools, "can_launch": state.can_launch,
                      "launch_note": state.launch_note, "commit": state.commit, "version": state.version,
                      "backend": state.backend, "model": state.model, "config_files": list(state.config_files),
                      "auth_env": state.auth_env, "bind_host": state.bind_host, "port": state.port,
                      "ui_args": list(state.ui_args),
                      "runs_dir": str(state.runs_dir), "runs_dir_name": state.runs_dir.name,
                      "link_max_mb": fetch.MAX_BYTES // (1024 * 1024),
                      "deadline_bounds_s": [DEADLINE_MIN_S, DEADLINE_MAX_S],
                      # What Stop does, stated from the code: SIGINT is the CLI's Ctrl-C path (errors.ExitCode.SIGINT).
                      "stop_exit_code": int(ExitCode.SIGINT),
                      "chat": {"model": chat.MODEL, "effort": chat.EFFORT, "max_calls": chat.MAX_CALLS,
                               "max_cost_usd": chat.MAX_COST_USD, "label": chat.LABEL,
                               "stopped_error": chat.STOPPED_ERROR, "stopped_text": chat.STOPPED_TEXT}})

    async def list_runs(request: Request) -> Response:
        return _json({"runs": rundata.list_runs(state.runs_dir, alive=state.launcher.alive())})

    async def tools_get(request: Request) -> Response:
        out = rundata.tools_status(state.runs_dir, state.tools)
        out.update(auth_env=state.auth_env, key_present=bool(os.environ.get(state.auth_env, "").strip()),
                   key_missing=tools_key_missing(state), probe=state.last_probe)
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

    async def limits(request: Request) -> Response:
        """What a run of ``profile`` at ``deadline_s`` would be held to, from the runtime's own functions
        (``llm.runtime.effective_stage_limits`` and ``deadline_warnings``), so the form never re-derives them."""
        from sit_review_agent.llm.runtime import deadline_warnings, effective_stage_limits

        sr = state.stop_rules.get(request.query_params.get("profile") or "")
        if sr is None:
            return _err(404, "No such profile.")
        d = parse_deadline(request.query_params.get("deadline_s"))
        if isinstance(d, str):
            return _err(400, d)
        if d is not None:
            sr = sr.with_deadline(d)            # the one scaling (StopRulesConfig.effective), as load_config does
        lim, note = effective_stage_limits(sr)
        eff = sr.effective()
        warnings = deadline_warnings(eff)
        if note is not None and warnings[:1] == [note]:
            warnings = warnings[1:]              # the scaling note is "note"; "warnings" are the rest
        return _json({"deadline_s": eff.deadline_seconds, "stage_limits_s": lim, "scaled": note is not None,
                      "note": note, "warnings": warnings,
                      # research's own deadline rule (phases/research.py), on the same effective rules
                      "research_end_s": eff.research_end_s() if "deadline" in eff.active else None,
                      "report_reserve_s": eff.report_reserve_seconds, "refine_reserve_s": eff.refine_reserve_seconds})

    async def documents_list(request: Request) -> Response:
        """The sample documents offered as chips on the Review page: a chip fills the form with the file and
        never starts a run (the run starts only with the Start review button, as every run does)."""
        return _json({"items": [{k: d[k] for k in ("name", "label", "file", "path")} for d in state.documents]})

    async def document_file(request: Request) -> Response:
        name = request.path_params["name"]
        d = next((d for d in state.documents if d["name"] == name), None)
        if d is None or not Path(d["abspath"]).is_file():
            return _err(404, "No such sample document.")
        media = "application/pdf" if d["file"].lower().endswith(".pdf") else "text/plain; charset=utf-8"
        return FileResponse(d["abspath"], media_type=media,
                            headers={"Content-Disposition": f'inline; filename="{d["file"]}"'})

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
        deadline_s = parse_deadline(form.get("deadline_s"))
        if isinstance(deadline_s, str):
            return _err(400, deadline_s)
        own = next((p.get("deadline_s") for p in state.profiles if p["name"] == (profile or "")), None)
        if deadline_s is not None and deadline_s == own:
            deadline_s = None                    # the profile's own deadline: no --deadline on the command line
        if not no_tools and (missing := tools_key_missing(state)):
            return _err(409, f"{missing} {tools_key_fix(state)}")
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
                          source_url=link or None, deadline_s=deadline_s)
        launched = state.launcher.start(spec, run_dir)
        return _json({"run_id": run_id, "command": launched.display}, 201)

    async def run_info(request: Request) -> Response:
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        info = rundata.summary(rd, process_alive=alive(rd.name))
        info["exit_code"] = state.launcher.exit_code(rd.name)
        if info.get("console") is not None:
            from sit_review_agent.tools.cassette import Redactor

            # The child's own words; the key is never printed by the CLI, and is redacted here all the same.
            redact = Redactor.from_env((state.auth_env, "ANTHROPIC_API_KEY"))
            info["console"]["lines"] = [redact.text(ln) for ln in info["console"]["lines"]]
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

    async def run_log(request: Request) -> Response:
        """The tail of the run's ``progress.log`` (the same lines as the terminal), read-only: the last
        ``rundata.LOG_TAIL`` complete lines, or with ``?after=<offset>`` the lines written since that byte."""
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        raw = request.query_params.get("after") or "0"
        try:
            after = max(0, int(raw))
        except ValueError:
            return _err(400, "after must be a byte offset.")
        return _json(rundata.tail_log(rd / "progress.log", after=after))

    async def run_report(request: Request) -> Response:
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        payload = rundata.review_payload(rd, state.runs_dir, state.repo_root)
        if payload is None:
            return _err(404, "This run has no report.json.")
        return _json(payload)

    async def run_review_html(request: Request) -> Response:
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        if not (rd / "report.md").is_file():
            return _err(404, REVIEW_NO_MD if (rd / "report.json").is_file() else REVIEW_NOT_YET)
        view = request.query_params.get("view") or "review"
        if view not in export.VIEWS:
            return _err(400, f"No view named {view!r}; one of {', '.join(export.VIEWS)}.")
        pdf = rundata.reviewed_pdf(rd, state.repo_root)
        try:
            html = export.review_fragment(rd, pdf_href=f"/runs/{rd.name}/doc.pdf" if pdf is not None else None,
                                          view=view)
        except (OSError, AttributeError, KeyError, TypeError, ValueError) as exc:
            return _err(422, f"{REVIEW_UNREADABLE} ({type(exc).__name__}: {exc}).")
        return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})

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

    def stage_read(request: Request, read: Callable[[Path], dict[str, Any] | None], what: str) -> Response:
        """A stage panel, the funnel or the glossary: a run's files read as they are. A file in an unexpected shape
        (a run written by an older agent, a file being replaced) is answered with what could not be read, never a
        server error, so the panel can say so."""
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        try:
            out = read(rd)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            return _json({"stage": what, "unreadable": f"{type(exc).__name__}: {exc}", "files": [], "missing": [],
                          "facts": [], "notes": [], "lists": []})
        if out is None:
            return _err(404, f"No stage named {what!r}.")
        return _json(out)

    async def run_stage(request: Request) -> Response:
        name = request.path_params["name"]
        return stage_read(request, lambda rd: stages.stage_view(rd, name), name)

    async def run_funnel(request: Request) -> Response:
        return stage_read(request, stages.funnel, "funnel")

    async def run_glossary(request: Request) -> Response:
        return stage_read(request, lambda rd: stages.glossary(state.repo_root, rd), "glossary")

    async def run_pdf(request: Request) -> Response:
        rd = run_dir_of(request)
        pdf = rundata.reviewed_pdf(rd, state.repo_root) if rd is not None else None
        if pdf is None:
            return _err(404, "The reviewed PDF is not available (moved, not a PDF, or its hash differs).")
        return FileResponse(pdf, media_type="application/pdf",
                            headers={"Content-Disposition": f'inline; filename="{safe_name(pdf.name)}"'})

    async def run_export(request: Request) -> Response:
        """``export.html`` (the page), ``export.html?download=1`` and ``export.zip`` (the bundle: the page, the
        reviewed PDF when its hash matches the manifest, report.md and report.json)."""
        rd = run_dir_of(request)
        if rd is None or not (rd / "report.md").is_file():
            return _err(404, "This run has no report.md to export.")
        replayed = rundata.summary(rd)["replayed"]
        pdf = rundata.reviewed_pdf(rd, state.repo_root)
        if request.url.path.endswith(".zip") or request.query_params.get("download") == "1":
            return Response(export.export_zip(rd, replayed=replayed, pdf=pdf), media_type="application/zip",
                            headers={"Content-Disposition": f'attachment; filename="{export.bundle_name(rd.name)}"'})
        # beside the page on this server the PDF is the run's own doc.pdf route
        html = export.export_html(rd, replayed=replayed, pdf_href="doc.pdf" if pdf is not None else None)
        return Response(html, media_type="text/html; charset=utf-8",
                        headers={"Content-Disposition": f'inline; filename="{export.export_name(rd.name)}"'})

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
            # The size of the bundle the Download control saves (export.html?download=1), built as run_export builds it.
            pdf = rundata.reviewed_pdf(rd, state.repo_root)
            size = len(export.export_zip(rd, replayed=rundata.summary(rd)["replayed"], pdf=pdf))
            exp = {"size": f"{max(1, round(size / 1024))} KB", "has_chat": chat.log_path(rd).is_file(),
                   "name": export.bundle_name(rd.name), "files": len(export.bundle_names(rd, pdf))}
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

    async def chat_stream(request: Request) -> Response:
        """One question, its answer streamed (``chat.ask`` with ``on_partial``). The question is checked before the
        stream opens, so a refusal is an HTTP status as on /chat. The reader stops the call by closing the stream:
        the server sees the page go (a write fails, or the poll below finds it gone) and cancels the call, which
        ``chat.ask`` logs as a counted call with ``chat.STOPPED_ERROR``."""
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
            chat.precheck(rd, question, running=running)
        except chat.ChatRefused as exc:
            return _err(exc.status, exc.message)
        if rd.name in state.chat_stops:
            return _err(409, "An answer for this run is still being written; stop it or wait for it.")
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        stop = state.chat_stops[rd.name] = asyncio.Event()

        async def work() -> None:
            try:
                res = await chat.ask(rd, question, state.chat_client, running=running, stop=stop,
                                     on_partial=lambda text: queue.put_nowait(("partial", {"answer": text})))
                queue.put_nowait(("stopped" if res.get("stopped") else "done", res))
            except chat.ChatRefused as exc:
                queue.put_nowait(("refused", {"error": exc.message, "status": exc.status}))
            except Exception as exc:  # noqa: BLE001 - said in the stream, never a broken page
                queue.put_nowait(("error", {"error": f"{type(exc).__name__}: {exc}"}))

        async def gen() -> AsyncIterator[str]:
            task = asyncio.create_task(work())
            try:
                while True:
                    try:
                        kind, data = await asyncio.wait_for(queue.get(), CHAT_POLL_S)
                    except TimeoutError:
                        if await request.is_disconnected():
                            return
                        yield ": waiting\n\n"                      # a write that fails once the page has gone
                        continue
                    yield f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    if kind != "partial":
                        return
            finally:
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                if state.chat_stops.get(rd.name) is stop:
                    del state.chat_stops[rd.name]

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def chat_stop(request: Request) -> Response:
        """The page's Stop: ends the answer being streamed for this run; its stream then sends ``stopped`` with the
        turn as it is logged (counted, ``chat.STOPPED_ERROR``) and the budget."""
        rd = run_dir_of(request)
        if rd is None:
            return _err(404, "No such run.")
        stop = state.chat_stops.get(rd.name)
        if stop is None:
            return _err(409, "No answer is being written for this run.")
        stop.set()
        return _json({"stopping": True})

    routes = [
        Route("/", index),
        Route("/favicon.ico", favicon),
        Route("/meta", meta),
        Route("/architecture", architecture_get, methods=["GET"]),
        Route("/limits", limits, methods=["GET"]),
        Route("/tools", tools_get, methods=["GET"]),
        Route("/tools/probe", tools_probe, methods=["POST"]),
        Route("/documents", documents_list, methods=["GET"]),
        Route("/documents/{name}", document_file, methods=["GET"]),
        Route("/runs", list_runs, methods=["GET"]),
        Route("/runs", start_run, methods=["POST"]),
        Route("/runs/{run_id}", run_info),
        Route("/runs/{run_id}/events", run_events),
        Route("/runs/{run_id}/log", run_log),
        Route("/runs/{run_id}/report", run_report),
        Route("/runs/{run_id}/review.html", run_review_html),
        Route("/runs/{run_id}/coverage", run_coverage),
        Route("/runs/{run_id}/explain/{finding_id}", run_explain),
        Route("/runs/{run_id}/stage/{name}", run_stage),
        Route("/runs/{run_id}/funnel", run_funnel),
        Route("/runs/{run_id}/glossary", run_glossary),
        Route("/runs/{run_id}/doc.pdf", run_pdf),
        Route("/runs/{run_id}/export.html", run_export),
        Route("/runs/{run_id}/export.zip", run_export),
        Route("/runs/{run_id}/report.md", raw_file("report.md", "text/markdown; charset=utf-8")),
        Route("/runs/{run_id}/report.json", raw_file("report.json", "application/json")),
        Route("/runs/{run_id}/outputs", run_outputs),
        Route("/runs/{run_id}/email", run_email, methods=["POST"]),
        Route("/runs/{run_id}/stop", run_stop, methods=["POST"]),
        Route("/runs/{run_id}/chat", chat_get, methods=["GET"]),
        Route("/runs/{run_id}/chat", chat_post, methods=["POST"]),
        Route("/runs/{run_id}/chat/stream", chat_stream, methods=["POST"]),
        Route("/runs/{run_id}/chat/stop", chat_stop, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=STATIC_DIR), name="static"),
    ]
    app = Starlette(routes=routes)
    app.state.ui = state
    return app


def parse_deadline(raw: Any) -> int | str | None:
    """The form's ``deadline_s``: ``None`` when absent or empty, a whole number of seconds within
    :data:`DEADLINE_MIN_S` and :data:`DEADLINE_MAX_S`, else the message to refuse it with."""
    text = str(raw or "").strip() if raw is None or isinstance(raw, str) else None
    if text is None:
        return "The deadline must be a number of seconds."
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        return "The deadline must be a whole number of seconds."
    if not DEADLINE_MIN_S <= value <= DEADLINE_MAX_S:
        return (f"The deadline must be from {DEADLINE_MIN_S} to {DEADLINE_MAX_S} seconds "
                f"({DEADLINE_MIN_S // 60} to {DEADLINE_MAX_S // 60} minutes).")
    return value


# ------------------------------------------------------------------ building the state from config


def _git_commit(repo_root: Path) -> str | None:
    import subprocess

    try:
        out = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _profiles(config_path: Path | None, stop_rules: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """One row per loadable profile for the page; ``stop_rules``, when given, is filled with each one's
    ``StopRulesConfig`` by name."""
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
        if stop_rules is not None:
            stop_rules[n or ""] = sr
        out.append({"name": n or "", "label": n or "default", "deadline_s": sr.deadline_seconds,
                    "stage_limits_s": {"stage_1_end": lim.stage_1_end, "refine_end": lim.refine_end,
                                       "verdict_end": lim.verdict_end},
                    "effort": cfg.agent.effort.assess if hasattr(cfg.agent.effort, "assess") else None})
    return out


def architecture_view(config_path: Path | None = None) -> dict[str, Any]:
    """The Architectural design view from the agent's config (and the demo profile for its limits, when it exists)."""
    from sit_review_agent.config import ConfigOverrides, load_config
    from sit_review_agent.ui import architecture

    cfg = load_config(config_path)
    try:
        demo = load_config(config_path, ConfigOverrides(profile="demo"))
    except Exception:  # noqa: BLE001 - no demo profile: the base config's limits are quoted instead
        demo = None
    return architecture.view(cfg, demo)


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
    stop_rules: dict[str, Any] = {}
    profiles = _profiles(config_path, stop_rules)
    return UIState(runs_dir=rd, repo_root=root, launcher=launcher or Launcher(repo_root=root),
                   chat_client=chat_client or chat.ClaudeCodeChatClient.from_config(cfg),
                   can_launch=can_launch, launch_note=note, profiles=profiles, stop_rules=stop_rules, tools=tools,
                   commit=_git_commit(root), smtp=smtp, smtp_detail=smtp_detail, url_policy=cfg.url_policy,
                   backend=cfg.agent.llm.backend, model=cfg.agent.model, config_files=files,
                   auth_env=cfg.tools.auth_env, probe=probe_with(cfg),
                   documents=load_documents(Path(cfg.config_root) / "ui.yaml", root), config_path=config_path)


def load_documents(path: Path, repo_root: Path) -> list[dict[str, Any]]:
    """``documents:`` of ``config/ui.yaml``: ``label`` and ``path`` (relative to the repository root) per
    sample document. An entry whose file is missing or is not a reviewable document is left out. The file the
    form will carry is named after the label and the file (``payments_orchestration_design_v1.pdf``)."""
    import yaml

    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    out: list[dict[str, Any]] = []
    for i, d in enumerate(doc.get("documents") or [] if isinstance(doc, dict) else []):
        if not isinstance(d, dict) or not d.get("label") or not d.get("path"):
            continue
        p = Path(str(d["path"]))
        p = p if p.is_absolute() else repo_root / p
        if not p.is_file() or p.suffix.lower() not in DOC_SUFFIXES:
            continue
        slug = safe_name(str(d["label"]).lower().replace(" ", "_"), "document")
        out.append({"name": f"doc-{i + 1}", "label": str(d["label"]), "file": safe_name(f"{slug}_{p.name}"),
                    "path": str(d["path"]), "abspath": str(p)})
    return out


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
