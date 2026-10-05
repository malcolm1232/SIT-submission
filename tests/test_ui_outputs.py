"""The three output actions of a finished review (decision #36, 2026-10-03): the self-contained HTML
export with ``report.md`` and ``report.json`` beside it, email through the SMTP server named in
``config/ui.yaml``, and the share link on this network. Offline: the committed run
``docs/live_runs/ui_flow_1`` (a live run with two chat turns), a local fake SMTP server in this file,
and an ``httpx.MockTransport`` for the pasted link, whose fetch is decision #39."""

from __future__ import annotations

import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from sit_review_agent.ui import export
from sit_review_agent.ui.launcher import Launcher
from sit_review_agent.ui.server import UIState, build_app

REPO = Path(__file__).resolve().parents[1]
LIVE_RUNS = REPO / "docs" / "live_runs"
FLOW = LIVE_RUNS / "ui_flow_1"
RUN_FILES = ("report.json", "report.md", "manifest.json", "anchors.json", "ledger.json", "state.json",
             "effective_config.json")


class NoChat:
    async def ask(self, **kw: object) -> object:  # pragma: no cover - never asked here
        raise AssertionError("no chat call expected")


def make_state(runs_dir: Path, **kw: object) -> UIState:
    return UIState(runs_dir=runs_dir.resolve(), repo_root=REPO, launcher=Launcher(repo_root=REPO),
                   chat_client=NoChat(), profiles=[], tools=[], **kw)  # type: ignore[arg-type]


def copy_run(src: Path, dst: Path, *, chat: bool = True) -> Path:
    dst.mkdir(parents=True)
    for name in RUN_FILES:
        if (src / name).is_file():
            shutil.copy2(src / name, dst / name)
    if chat and (src / "ui" / "chat.jsonl").is_file():
        (dst / "ui").mkdir()
        shutil.copy2(src / "ui" / "chat.jsonl", dst / "ui" / "chat.jsonl")
    return dst


def one_line(text: str | None) -> str:
    return " ".join((text or "").split())


class Text(HTMLParser):
    """Text of each element by tag, and every tag and attribute seen."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, list[str]]] = []
        self.done: list[tuple[str, str]] = []
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        if tag not in ("br", "hr", "meta", "img", "input"):
            self.stack.append((tag, []))

    def handle_endtag(self, tag: str) -> None:
        while self.stack:
            t, parts = self.stack.pop()
            text = "".join(parts)
            self.done.append((t, text))
            if self.stack:
                self.stack[-1][1].append(text)
            if t == tag:
                break

    def handle_data(self, data: str) -> None:
        if self.stack:
            self.stack[-1][1].append(data)

    def texts(self, tag: str) -> list[str]:
        return [one_line(t) for g, t in self.done if g == tag]


def parse(html: str) -> Text:
    p = Text()
    p.feed(html)
    p.close()
    return p


@pytest.fixture
def flow_runs(tmp_path: Path) -> Path:
    runs = tmp_path / "runs"
    copy_run(FLOW, runs / "ui_flow_1")
    return runs


# ------------------------------------------------------------------ item 1: the HTML export


def test_the_export_is_report_md_rendered_and_its_finding_text_equals_report_json(flow_runs: Path) -> None:
    rd = flow_runs / "ui_flow_1"
    html = export.export_html(rd, replayed=False, exported_at="2026-10-03T12:00:00Z")
    report = json.loads((rd / "report.json").read_text(encoding="utf-8"))
    doc = parse(html)
    h3 = doc.texts("h3")
    paragraphs = doc.texts("p")
    for f in report["findings"]:
        assert f"{f['id']} {one_line(f['title'])}" in h3, f["id"]
        assert one_line(f["statement"]) in paragraphs, f["id"]
        for a in f["doc_anchors"]:
            assert one_line(a["quote"]) in html.replace("&quot;", '"').replace("&#x27;", "'"), f["id"]
    # the same renderer as report.md: every heading of report.md is a heading of the export, in order
    md_heads = [one_line(re.sub(r"[*`]", "", ln.lstrip("#"))) for ln in
                (rd / "report.md").read_text(encoding="utf-8").splitlines() if re.match(r"#{1,3} ", ln)]
    html_heads = [t for g, t in ((g, one_line(t)) for g, t in doc.done) if g in ("h1", "h2", "h3")]
    review_heads = html_heads[html_heads.index(md_heads[0]):][:len(md_heads)]
    assert review_heads == md_heads
    v = report["verdict"]
    assert f"confidence {v['confidence']:.2f}" in html
    for deg in report["research_log"]["degradations"]:
        assert deg["id"] in html                       # every disclosed degradation is named
    for o in v["per_objective"]:
        assert o["objective_ref"] in html


def test_the_export_is_self_contained_with_one_fixed_script_and_no_external_resource(flow_runs: Path) -> None:
    html = export.export_html(flow_runs / "ui_flow_1", replayed=False)
    doc = parse(html)
    tags = {t for t, _ in doc.tags}
    assert "link" not in tags and "img" not in tags and "iframe" not in tags
    # the one script is the sidebar's own (decision #43), never model text
    assert [t for t, _ in doc.tags].count("script") == 1 and f"<script>{export.NAV_JS}</script>" in html
    for _, attrs in doc.tags:
        assert "src" not in attrs and not any(k.startswith("on") for k in attrs)
    assert "@import" not in html and "url(" not in html
    tokens = (export.STATIC_DIR / "tokens.css").read_text(encoding="utf-8")
    assert "--sev-critical-bg:" in html
    assert tokens.split(":root", 1)[1].split("}", 1)[0].strip() in html   # tokens inlined
    assert "@font-face" not in html                     # the vendored serif is a file beside tokens.css, not inlined


def test_the_export_stylesheet_keeps_the_page_rules() -> None:
    for name in ("export.css", "review.css"):          # the page around the review, and the review document
        css = (export.STATIC_DIR / name).read_text(encoding="utf-8")
        _page_rules(css)
    # the review document's element rules are scoped, so the app's Review tab can load the sheet beside app.css
    review = (export.STATIC_DIR / "review.css").read_text(encoding="utf-8")
    bare = [ln for ln in review.splitlines() if re.match(r"\s*(h[1-6]|p|ul|li|a|table|th|td|tr|code|b|strong)\b", ln)]
    assert bare == []


def _page_rules(css: str) -> None:
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", css) and not re.search(r"\brgba?\(|\bhsla?\(", css)
    assert "animation" not in css and "transition" not in css and "@keyframes" not in css
    assert "http" not in css and "url(" not in css and "@import" not in css


def test_model_text_cannot_inject_markup_or_load_an_image(tmp_path: Path) -> None:
    rd = tmp_path / "r"
    rd.mkdir()
    (rd / "report.md").write_text('# Design review: x\n\n<script>alert(1)</script> ![p](https://example.org/p.png)'
                                  ' [j](javascript:alert(1))\n', encoding="utf-8")
    (rd / "report.json").write_text("{}", encoding="utf-8")
    html = export.export_html(rd, replayed=False)
    doc = parse(html)
    assert [t for t, _ in doc.tags].count("script") == 1 and f"<script>{export.NAV_JS}</script>" in html
    assert "img" not in {t for t, _ in doc.tags}
    assert all(not str(a.get("href", "")).startswith("javascript") for _, a in doc.tags)
    assert "&lt;script&gt;" in html


def test_the_chat_transcript_is_appended_apart_and_only_when_it_exists(flow_runs: Path, tmp_path: Path) -> None:
    html = export.export_html(flow_runs / "ui_flow_1", replayed=False)
    rows = [json.loads(ln) for ln in (FLOW / "ui" / "chat.jsonl").read_text(encoding="utf-8").splitlines()]
    assert export.CHAT_HEADING == "Reading-aid chat transcript (not part of the review)"
    review_h2 = parse(html.split('<div class="x-reference">', 1)[0]).texts("h2")
    assert review_h2[-1] == export.CHAT_HEADING           # after the review, before the Reference part
    transcript = html.split(export.CHAT_HEADING, 1)[1]
    review = html.split(export.CHAT_HEADING, 1)[0]
    said = set(parse(transcript).texts("p"))
    for r in rows:
        assert one_line(r["question"]) in said
        assert one_line(r["answer"]) in said
        assert one_line(r["question"])[:60] not in review   # chat text never enters the review part
    bare = copy_run(FLOW, tmp_path / "bare" / "ui_flow_1", chat=False)
    assert export.CHAT_HEADING not in export.export_html(bare, replayed=False)


def test_a_replayed_run_carries_the_stamp_in_the_export(flow_runs: Path) -> None:
    rd = flow_runs / "ui_flow_1"
    assert export.REPLAY_STAMP not in export.export_html(rd, replayed=False)
    (rd / "replay.json").write_text("{}", encoding="utf-8")
    client = TestClient(build_app(make_state(flow_runs)))
    res = client.get("/runs/ui_flow_1/export.html")
    assert res.status_code == 200
    assert f'<span class="pill">{export.REPLAY_STAMP}</span>' in res.text


def test_export_and_raw_downloads_are_served(flow_runs: Path) -> None:
    client = TestClient(build_app(make_state(flow_runs)))
    view = client.get("/runs/ui_flow_1/export.html")
    assert view.status_code == 200 and view.headers["content-type"].startswith("text/html")
    assert view.headers["content-disposition"].startswith("inline")
    dl = client.get("/runs/ui_flow_1/export.html?download=1")      # the Download control: the bundle (#43)
    assert dl.headers["content-type"] == "application/zip"
    assert dl.headers["content-disposition"] == 'attachment; filename="ui_flow_1_review.zip"'
    md = client.get("/runs/ui_flow_1/report.md")
    assert md.content == (FLOW / "report.md").read_bytes()
    assert md.headers["content-disposition"] == 'attachment; filename="ui_flow_1_report.md"'
    js = client.get("/runs/ui_flow_1/report.json")
    assert js.content == (FLOW / "report.json").read_bytes()
    assert js.headers["content-disposition"] == 'attachment; filename="ui_flow_1_report.json"'
    assert client.get("/runs/nope/export.html").status_code == 404
    (flow_runs / "ui_flow_1" / "report.md").unlink()
    assert client.get("/runs/ui_flow_1/export.html").status_code == 404
    assert client.get("/runs/ui_flow_1/report.md").status_code == 404


# ------------------------------------------------------------------ item 2: email through config/ui.yaml


class FakeSMTP:
    """A local SMTP server for one test: EHLO, AUTH PLAIN, MAIL, RCPT, DATA, QUIT, and nothing else (no
    STARTTLS). ``refuse_auth`` answers 535 to AUTH."""

    def __init__(self, *, refuse_auth: bool = False) -> None:
        import socketserver
        import threading

        self.messages: list[dict[str, object]] = []
        self.auth: list[bytes] = []
        self.connections = 0
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                outer.connections += 1
                send = lambda line: self.wfile.write(line.encode() + b"\r\n")  # noqa: E731
                send("220 fake ESMTP")
                env: dict[str, object] = {"rcpt": []}
                while True:
                    raw = self.rfile.readline()
                    if not raw:
                        return
                    line = raw.decode().rstrip("\r\n")
                    cmd = line.split(" ", 1)[0].upper()
                    if cmd in ("EHLO", "HELO"):
                        send("250-fake")
                        send("250 AUTH PLAIN")
                    elif cmd == "AUTH":
                        import base64

                        outer.auth.append(base64.b64decode(line.split()[2]))
                        send("535 authentication refused" if refuse_auth else "235 ok")
                    elif cmd == "MAIL":
                        env["from"] = line
                        send("250 ok")
                    elif cmd == "RCPT":
                        env["rcpt"].append(line)  # type: ignore[union-attr]
                        send("250 ok")
                    elif cmd == "DATA":
                        send("354 go")
                        data = b""
                        while not data.endswith(b"\r\n.\r\n"):
                            chunk = self.rfile.readline()
                            if not chunk:
                                return
                            data += chunk
                        env["data"] = data
                        outer.messages.append(dict(env))
                        send("250 queued")
                    elif cmd == "QUIT":
                        send("221 bye")
                        return
                    else:
                        send("502 not here")

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


PASSWORD = "pw-never-written-7Q"


@pytest.fixture
def smtp():
    s = FakeSMTP()
    yield s
    s.close()


def smtp_cfg(port: int, *, starttls: bool = False):
    from sit_review_agent.ui.mail import SmtpConfig

    return SmtpConfig(host="127.0.0.1", port=port, starttls=starttls, username="reviewer", sender="sit@example.org")


def test_the_shipped_config_leaves_email_off_with_the_reason(tmp_path: Path, monkeypatch) -> None:
    from sit_review_agent.ui import mail

    monkeypatch.setenv(mail.PASSWORD_ENV, PASSWORD)
    cfg, detail = mail.load_smtp(REPO / "config" / "ui.yaml")
    assert cfg is None and detail == "host, username and from are empty"
    assert mail.NOT_CONFIGURED == "Email is not configured: see config/ui.yaml"
    missing, detail = mail.load_smtp(tmp_path / "ui.yaml")
    assert missing is None and detail == "the file does not exist"
    full = tmp_path / "full.yaml"
    full.write_text("email:\n  host: smtp.example.org\n  port: 587\n  starttls: true\n  username: me\n"
                    "  from: me@example.org\n", encoding="utf-8")
    cfg, detail = mail.load_smtp(full)
    assert cfg == mail.SmtpConfig(host="smtp.example.org", port=587, starttls=True, username="me",
                                  sender="me@example.org") and detail == ""


def test_outputs_reports_the_bundle_the_download_saves(flow_runs: Path) -> None:
    """GET /outputs names the zip that export.html?download=1 saves, its file count and its size."""
    client = TestClient(build_app(make_state(flow_runs)))
    out = client.get("/runs/ui_flow_1/outputs").json()["export"]
    res = client.get("/runs/ui_flow_1/export.html?download=1")
    assert res.status_code == 200 and f'filename="{out["name"]}"' in res.headers["content-disposition"]
    assert out["name"] == "ui_flow_1_review.zip"
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        names = z.namelist()
    assert out["files"] == len(names) and names[0] == export.INDEX_NAME and names[-2:] == ["report.md", "report.json"]
    kb = int(out["size"].removesuffix(" KB"))
    assert abs(kb * 1024 - len(res.content)) <= 1024   # the zip, not the single page (only the export stamp differs)


def test_email_is_shown_disabled_with_the_reason_without_config_or_password(flow_runs: Path, smtp: FakeSMTP,
                                                                           monkeypatch) -> None:
    from sit_review_agent.ui import mail

    monkeypatch.delenv(mail.PASSWORD_ENV, raising=False)
    for state in (make_state(flow_runs), make_state(flow_runs, smtp=smtp_cfg(smtp.port))):
        client = TestClient(build_app(state))
        email = client.get("/runs/ui_flow_1/outputs").json()["email"]
        assert email["enabled"] is False and email["reason"] == mail.NOT_CONFIGURED and email["detail"]
        res = client.post("/runs/ui_flow_1/email", json={"to": "someone@example.org"})
        assert res.status_code == 409 and res.json()["error"].startswith(mail.NOT_CONFIGURED)
    assert smtp.connections == 0
    assert not (flow_runs / "ui_flow_1" / "ui" / mail.OUTBOX).exists()


def test_email_sends_the_export_and_report_md_and_logs_no_content(flow_runs: Path, smtp: FakeSMTP,
                                                                  monkeypatch) -> None:
    import email as email_lib
    from email import policy

    from sit_review_agent.ui import mail

    monkeypatch.setenv(mail.PASSWORD_ENV, PASSWORD)
    client = TestClient(build_app(make_state(flow_runs, smtp=smtp_cfg(smtp.port))))
    status = client.get("/runs/ui_flow_1/outputs").json()["email"]
    assert status == {"enabled": True, "reason": None, "detail": None, "from": "sit@example.org",
                      "host": "127.0.0.1"}
    res = client.post("/runs/ui_flow_1/email", json={"to": "Reader@Example.org"})
    assert res.status_code == 200, res.text
    assert res.json()["result"] == "sent"
    assert smtp.auth == [b"\0reviewer\0" + PASSWORD.encode()]
    (msg_env,) = smtp.messages
    assert "reader@example.org" in str(msg_env["rcpt"]).lower()
    msg = email_lib.message_from_bytes(msg_env["data"], policy=policy.default)  # type: ignore[arg-type]
    names = {p.get_filename(): p.get_content() for p in msg.iter_attachments()}
    assert set(names) == {"ui_flow_1_review.html", "ui_flow_1_report.md"}
    raw = {p.get_filename(): p.get_payload(decode=True) for p in msg.iter_attachments()}
    assert raw["ui_flow_1_report.md"] == (FLOW / "report.md").read_bytes()
    assert names["ui_flow_1_report.md"] == (FLOW / "report.md").read_text(encoding="utf-8")
    assert export.CHAT_HEADING in names["ui_flow_1_review.html"]
    assert msg["From"] == "sit@example.org" and msg["To"] == "Reader@Example.org"
    rows = [json.loads(ln) for ln in (flow_runs / "ui_flow_1" / "ui" / mail.OUTBOX).read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["to"] == "Reader@Example.org" and row["result"] == "sent" and row["error"] is None
    assert {a["name"] for a in row["attachments"]} == set(names)
    assert all(isinstance(a["bytes"], int) and a["bytes"] > 1000 for a in row["attachments"])
    assert set(row) == {"at", "to", "from", "smtp_host", "attachments", "message_bytes", "result", "error"}
    for p in (flow_runs / "ui_flow_1").rglob("*"):
        if p.is_file():
            assert PASSWORD.encode() not in p.read_bytes(), p
    assert PASSWORD not in json.dumps(client.get("/runs/ui_flow_1/outputs").json())


@pytest.mark.parametrize("to", ["", "nobody", "a@b", "a@b.test, c@d.test", "a@b.test\r\nBcc: x@y.test",
                                "a b@c.test", "x" * 250 + "@b.test"], ids=range(7))
def test_a_bad_address_is_refused_before_any_connection(flow_runs: Path, smtp: FakeSMTP, monkeypatch,
                                                        to: str) -> None:
    from sit_review_agent.ui import mail

    monkeypatch.setenv(mail.PASSWORD_ENV, PASSWORD)
    client = TestClient(build_app(make_state(flow_runs, smtp=smtp_cfg(smtp.port))))
    res = client.post("/runs/ui_flow_1/email", json={"to": to})
    assert res.status_code == 400
    assert smtp.connections == 0
    assert not (flow_runs / "ui_flow_1" / "ui" / mail.OUTBOX).exists()


def test_a_refused_login_or_a_missing_starttls_is_logged_as_failed(flow_runs: Path, monkeypatch) -> None:
    from sit_review_agent.ui import mail

    monkeypatch.setenv(mail.PASSWORD_ENV, PASSWORD)
    bad = FakeSMTP(refuse_auth=True)
    try:
        for cfg in (smtp_cfg(bad.port), smtp_cfg(bad.port, starttls=True)):
            client = TestClient(build_app(make_state(flow_runs, smtp=cfg)))
            res = client.post("/runs/ui_flow_1/email", json={"to": "someone@example.org"})
            assert res.status_code == 502 and res.json()["error"].startswith("The mail was not sent")
        assert bad.messages == []
        assert len(bad.auth) == 1                    # with starttls the server's lack of STARTTLS stops it first
    finally:
        bad.close()
    rows = [json.loads(ln) for ln in (flow_runs / "ui_flow_1" / "ui" / mail.OUTBOX).read_text().splitlines()]
    assert [r["result"] for r in rows] == ["failed", "failed"]
    assert all(r["error"] and PASSWORD not in r["error"] for r in rows)


# ------------------------------------------------------------------ item 3: the share link on this network


def test_a_loopback_server_shows_the_restart_line_not_a_link(flow_runs: Path) -> None:
    from sit_review_agent.ui import share

    called: list[int] = []
    state = make_state(flow_runs, bind_host="127.0.0.1", port=8771, lan_ip=lambda: called.append(1) or "10.1.2.3")
    s = TestClient(build_app(state)).get("/runs/ui_flow_1/outputs").json()["share"]
    assert s == {"mode": "loopback", "url": None, "text": share.LOOPBACK_TEXT,
                 "restart": "dra ui --host 0.0.0.0 --allow-remote --port 8771"}
    assert called == []                                # no address is looked up for a loopback server
    state = make_state(flow_runs, bind_host="localhost", port=8765, ui_args=["--runs-dir", "my runs"])
    s = TestClient(build_app(state)).get("/runs/ui_flow_1/outputs").json()["share"]
    assert s["restart"] == "dra ui --host 0.0.0.0 --allow-remote --port 8765 --runs-dir 'my runs'"


def test_a_remote_server_shows_the_page_address_on_this_network(flow_runs: Path) -> None:
    from sit_review_agent.ui import share

    assert share.SHARE_TEXT == ("Anyone on this network can open this link while this laptop serves it; there is no "
                                "login, and the link dies when the server stops.")
    state = make_state(flow_runs, bind_host="0.0.0.0", port=8771, lan_ip=lambda: "192.168.1.23")
    s = TestClient(build_app(state)).get("/runs/ui_flow_1/outputs").json()["share"]
    assert s == {"mode": "network", "url": "http://192.168.1.23:8771/?run=ui_flow_1", "text": share.SHARE_TEXT,
                 "restart": None}
    state = make_state(flow_runs, bind_host="10.0.0.5", port=9000, lan_ip=lambda: "192.168.1.23")
    s = TestClient(build_app(state)).get("/runs/ui_flow_1/outputs").json()["share"]
    assert s["url"] == "http://10.0.0.5:9000/?run=ui_flow_1"
    state = make_state(flow_runs, bind_host="0.0.0.0", port=8771, lan_ip=lambda: None)
    s = TestClient(build_app(state)).get("/runs/ui_flow_1/outputs").json()["share"]
    assert s["mode"] == "no_address" and s["url"] is None and s["text"] == share.NO_ADDRESS_TEXT


def test_the_lan_address_is_a_non_loopback_ipv4_or_none() -> None:
    import ipaddress

    from sit_review_agent.ui import share

    ip = share.lan_ipv4()
    assert ip is None or (ipaddress.ip_address(ip).version == 4 and not ipaddress.ip_address(ip).is_loopback)


def test_serve_hands_its_host_port_and_arguments_to_the_page(monkeypatch, tmp_path: Path) -> None:
    import uvicorn

    from sit_review_agent.ui import server

    seen: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(state=app.state.ui, **kw))
    runs = tmp_path / "runs"
    server.serve(host="0.0.0.0", port=8799, runs_dir=runs, config_path=None, allow_remote=True,
                 echo=lambda s: None)
    st = seen["state"]
    assert (st.bind_host, st.port, st.ui_args) == ("0.0.0.0", 8799, ["--runs-dir", str(runs)])  # type: ignore[attr-defined]


# ------------------------------------------------------------------ item 4: a pasted https link to a PDF


class FakePopen:
    def __init__(self) -> None:
        self.argvs: list[list[str]] = []

    def __call__(self, argv: list[str], **kw: object) -> object:
        self.argvs.append(argv)

        class P:
            pid = 4243

            def poll(self) -> None:
                return None
        return P()


PDF = b"%PDF-1.7\n" + b"x" * 2000 + b"\n%%EOF\n"
PUBLIC = {"docs.example.org": ["93.184.215.14"], "cdn.example.net": ["151.101.1.1"],
          "intranet.example.org": ["10.20.30.40"], "meta.example.org": ["169.254.169.254"],
          "local.example.org": ["127.0.0.1"], "mixed.example.org": ["93.184.215.15", "192.168.0.7"]}


def link_state(runs: Path, handler, *, policy=None, popen: FakePopen | None = None) -> tuple[UIState, list[str]]:
    import httpx

    from sit_review_agent.config import UrlPolicy

    seen: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return handler(request)

    def resolve(host: str) -> list[str]:
        return PUBLIC.get(host, [])

    launcher = Launcher(repo_root=REPO, popen=popen or FakePopen())
    state = UIState(runs_dir=runs.resolve(), repo_root=REPO, launcher=launcher, chat_client=NoChat(),  # type: ignore[arg-type]
                    profiles=[], tools=[], url_policy=policy or UrlPolicy(),
                    fetch_transport=httpx.MockTransport(record), resolve=resolve)
    return state, seen


def pdf_handler(request):
    import httpx

    return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})


def test_a_pasted_link_is_fetched_saved_with_the_run_and_named_in_the_argv(tmp_path: Path) -> None:
    popen = FakePopen()
    state, seen = link_state(tmp_path, pdf_handler, popen=popen)
    client = TestClient(build_app(state))
    url = "https://docs.example.org/specs/Payments%20Design%20v2.pdf?dl=1"
    res = client.post("/runs", data={"document_url": url, "run_id": "from_link"})
    assert res.status_code == 201, res.text
    saved = tmp_path.resolve() / "from_link" / "ui" / "input" / "Payments_Design_v2.pdf"
    assert saved.read_bytes() == PDF
    assert popen.argvs[0][3:5] == ["review", str(saved)]
    assert str(saved) in res.json()["command"] or "from_link/ui/input/Payments_Design_v2.pdf" in res.json()["command"]
    launch = json.loads((tmp_path / "from_link" / "ui" / "launch.json").read_text(encoding="utf-8"))
    assert launch["source_url"] == url and launch["document_name"] == "Payments_Design_v2.pdf"
    assert seen == [url]
    meta = TestClient(build_app(state)).get("/meta").json()
    assert meta["link_max_mb"] == 50


@pytest.mark.parametrize(("url", "why"), [
    ("http://docs.example.org/a.pdf", "Only an https:// link"),
    ("ftp://docs.example.org/a.pdf", "Only an https:// link"),
    ("https://user:pw@docs.example.org/a.pdf", "user name or password"),
    ("https://local.example.org/a.pdf", "loopback, private or link-local"),
    ("https://intranet.example.org/a.pdf", "loopback, private or link-local"),
    ("https://meta.example.org/latest/a.pdf", "loopback, private or link-local"),
    ("https://mixed.example.org/a.pdf", "loopback, private or link-local"),
    ("https://127.0.0.1/a.pdf", "loopback, private or link-local"),
    ("https://nowhere.example.org/a.pdf", "could not be resolved"),
    ("https://docs.example.org/a b.pdf", "not one link"),
], ids=range(10))
def test_a_link_outside_the_policy_is_refused_before_any_request(tmp_path: Path, url: str, why: str) -> None:
    state, seen = link_state(tmp_path, pdf_handler)
    res = TestClient(build_app(state)).post("/runs", data={"document_url": url})
    assert res.status_code == 400 and why in res.json()["error"], res.text
    assert seen == [] and list(tmp_path.iterdir()) == []


def test_the_url_policy_domains_apply_to_a_pasted_link(tmp_path: Path) -> None:
    from sit_review_agent.config import UrlPolicy

    deny = UrlPolicy(mode="deny", deny_domains=["example.org"])
    state, seen = link_state(tmp_path, pdf_handler, policy=deny)
    res = TestClient(build_app(state)).post("/runs", data={"document_url": "https://docs.example.org/a.pdf"})
    assert res.status_code == 400 and "url_policy.yaml" in res.json()["error"] and seen == []
    allow = UrlPolicy(mode="allow", allow_domains=["example.net"])
    state, seen = link_state(tmp_path, pdf_handler, policy=allow)
    res = TestClient(build_app(state)).post("/runs", data={"document_url": "https://docs.example.org/a.pdf"})
    assert res.status_code == 400 and "allow_domains" in res.json()["error"] and seen == []
    res = TestClient(build_app(state)).post("/runs", data={"document_url": "https://cdn.example.net/a.pdf"})
    assert res.status_code == 201, res.text


def test_each_redirect_is_checked_again(tmp_path: Path) -> None:
    import httpx

    hops = {"https://docs.example.org/a.pdf": "https://intranet.example.org/a.pdf",
            "https://docs.example.org/b.pdf": "http://docs.example.org/b.pdf",
            "https://docs.example.org/c.pdf": "https://cdn.example.net/c.pdf"}

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if u in hops:
            return httpx.Response(302, headers={"location": hops[u]})
        if u.startswith("https://docs.example.org/loop"):
            return httpx.Response(302, headers={"location": u + "x"})
        return pdf_handler(request)

    state, seen = link_state(tmp_path, handler)
    client = TestClient(build_app(state))
    for url, why in (("https://docs.example.org/a.pdf", "loopback, private or link-local"),
                     ("https://docs.example.org/b.pdf", "Only an https:// link"),
                     ("https://docs.example.org/loop", "more than 5 redirects")):
        res = client.post("/runs", data={"document_url": url})
        assert res.status_code == 400 and why in res.json()["error"], (url, res.text)
    assert not any("intranet" in u or u.startswith("http://") for u in seen)
    res = client.post("/runs", data={"document_url": "https://docs.example.org/c.pdf", "run_id": "hop"})
    assert res.status_code == 201 and (tmp_path / "hop" / "ui" / "input" / "c.pdf").read_bytes() == PDF
    assert sorted(p.name for p in tmp_path.iterdir()) == ["hop"]


def test_the_size_cap_stops_a_large_download(tmp_path: Path, monkeypatch) -> None:
    import httpx

    from sit_review_agent.ui import fetch

    assert fetch.MAX_BYTES == 50 * 1024 * 1024
    declared = TestClient(build_app(link_state(tmp_path, lambda r: httpx.Response(
        200, headers={"content-length": str(fetch.MAX_BYTES + 1)}, content=b""))[0]))
    res = declared.post("/runs", data={"document_url": "https://docs.example.org/big.pdf"})
    assert res.status_code == 400 and "larger than 50 MB" in res.json()["error"]
    monkeypatch.setattr(fetch, "MAX_BYTES", 1000)

    async def chunks():
        for part in (PDF[:600], PDF[600:1200], PDF[1200:]):
            yield part

    def streamed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=chunks())                  # no declared length

    res = TestClient(build_app(link_state(tmp_path, streamed)[0])).post(
        "/runs", data={"document_url": "https://docs.example.org/big.pdf"})
    assert res.status_code == 400 and "larger than" in res.json()["error"]
    assert list(tmp_path.iterdir()) == []


def test_a_link_that_is_not_a_pdf_or_fails_is_refused(tmp_path: Path) -> None:
    import httpx

    for handler, why in ((lambda r: httpx.Response(200, content=b"<html>login</html>"), "is not a PDF"),
                         (lambda r: httpx.Response(404, content=b"no"), "HTTP 404")):
        res = TestClient(build_app(link_state(tmp_path, handler)[0])).post(
            "/runs", data={"document_url": "https://docs.example.org/a.pdf"})
        assert res.status_code == 400 and why in res.json()["error"], res.text
    res = TestClient(build_app(link_state(tmp_path, pdf_handler)[0])).post(
        "/runs", files={"document": ("d.pdf", PDF, "application/pdf")},
        data={"document_url": "https://docs.example.org/a.pdf"})
    assert res.status_code == 400 and "not both" in res.json()["error"]
    assert list(tmp_path.iterdir()) == []


# ------------------------------------------------------------------ item 5: the three actions in a browser


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def browser_page(tmp_path: Path, monkeypatch):
    """The flow run on a loopback server with email pointed at a fake SMTP server, in Chromium (skipped
    where Playwright or its Chromium is not installed)."""
    import threading
    import time

    uvicorn = pytest.importorskip("uvicorn")
    sync_api = pytest.importorskip("playwright.sync_api")
    from sit_review_agent.ui import mail

    monkeypatch.setenv(mail.PASSWORD_ENV, PASSWORD)
    runs = tmp_path / "runs"
    copy_run(FLOW, runs / "ui_flow_1")
    copy_run(FLOW, runs / "no_mail")
    fake = FakeSMTP()
    port = _free_port()
    states = {"ui_flow_1": make_state(runs, smtp=smtp_cfg(fake.port), bind_host="127.0.0.1", port=port)}
    server = uvicorn.Server(uvicorn.Config(build_app(states["ui_flow_1"]), host="127.0.0.1", port=port,
                                           log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - Chromium not installed here
            pytest.skip(f"Chromium not available: {exc}")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        pg = ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        yield pg, ctx, f"http://127.0.0.1:{port}", runs, fake, states["ui_flow_1"]
        browser.close()
    server.should_exit = True
    th.join(timeout=5)
    fake.close()
    assert errors == []


def wait_open(pg, name: str) -> None:
    """Wait until the ``name`` pill's box is open: its click handler unhides ``#<name>-box`` and sets the pill's
    aria-expanded in one task, so once this holds the box can be read; reading right after the click raced that task
    under load."""
    pg.wait_for_function("(n) => !document.getElementById(n + '-box').hidden"
                         " && document.getElementById(n + '-btn').getAttribute('aria-expanded') === 'true'", arg=name)


def test_the_three_actions_in_a_browser(browser_page) -> None:
    from sit_review_agent.ui import mail, share

    pg, ctx, base, runs, fake, state = browser_page
    pg.goto(base + "/?run=ui_flow_1")
    pg.wait_for_selector("#rv .report")
    pg.wait_for_selector("#outputs", state="visible")   # filled by GET /outputs after the review renders
    heads = pg.locator("#outputs h3").all_inner_texts()
    assert heads == ["Download", "Email", "Share"]
    # 1. Download: the bundle saves under its name, its size on the label; "Open it in a new tab" shows the same review.
    out = json.loads(pg.evaluate("fetch('/runs/ui_flow_1/outputs').then(r => r.text())"))["export"]
    assert out["name"] == "ui_flow_1_review.zip"
    assert pg.locator("#out-download").inner_text() == f"Download review (zip, {out['size']})"
    help_text = pg.locator("#out-download-help").inner_text()
    assert help_text.startswith("A zip of one cross-linked review page with a sidebar, whose one script shows and "
                                "hides")
    assert "the reviewed PDF its page references open, report.md and report.json" in help_text
    with pg.expect_download() as dl:
        pg.click("#out-download")
    assert dl.value.suggested_filename == "ui_flow_1_review.zip"     # the bundle (decision #43)
    import zipfile

    with zipfile.ZipFile(dl.value.path()) as z:
        assert len(z.namelist()) == out["files"] and z.namelist()[0] == export.INDEX_NAME
        saved = z.read(export.INDEX_NAME).decode("utf-8")
    assert export.CHAT_HEADING in saved and saved.count("<script") == 1
    with pg.expect_download() as md:
        pg.click("#out-md")
    assert md.value.suggested_filename == "ui_flow_1_report.md"
    assert Path(md.value.path()).read_bytes() == (FLOW / "report.md").read_bytes()
    with ctx.expect_page() as tab:
        pg.click("#out-open")
    exp = tab.value
    # The new tab can be handed over still on about:blank, whose load has already fired; wait for the review file
    # itself to load (the same race as the export sidebar test's part tab).
    exp.wait_for_url(base + "/runs/ui_flow_1/export.html")
    report = json.loads((FLOW / "report.json").read_text(encoding="utf-8"))
    first = min(report["findings"], key=lambda f: f["rank"])
    assert exp.get_by_role("heading", name=f"{first['id']} {one_line(first['title'])}").count() == 1
    exp.close()
    # 2. Email: the pill in the head opens the address field under it (ui_restyle.md decision 5); the send is
    # enabled only for one plain address, reaches the (fake) server and is reported.
    assert pg.locator("#email-box").is_hidden()
    pg.click("#email-btn")
    wait_open(pg, "email")
    send = pg.locator("#email-send")
    assert send.inner_text() == "Email the review" and send.is_disabled()
    pg.fill("#email-to", "not an address")
    pg.wait_for_function("document.getElementById('email-send').disabled")
    assert send.is_disabled()
    pg.fill("#email-to", "reader@example.org")
    pg.wait_for_function("!document.getElementById('email-send').disabled")
    assert send.is_enabled()
    send.click()
    pg.wait_for_selector("#email-result.ok")
    assert pg.locator("#email-result").inner_text().startswith("Sent to reader@example.org at ")
    assert len(fake.messages) == 1
    # 3. Share: a loopback server shows the restart line and says why there is no link.
    assert pg.locator("#share-box").is_hidden()
    pg.click("#share-btn")
    wait_open(pg, "share")
    assert pg.locator("#share-line").inner_text() == f"dra ui --host 0.0.0.0 --allow-remote --port {state.port}"
    assert pg.locator("#share-text").inner_text() == share.LOOPBACK_TEXT
    state.bind_host, state.lan_ip = "0.0.0.0", lambda: "192.168.1.23"
    pg.reload()
    pg.wait_for_selector("#rv .report")
    pg.wait_for_selector("#outputs", state="visible")   # filled by GET /outputs after the review renders
    pg.click("#share-btn")
    wait_open(pg, "share")
    assert pg.locator("#share-line").inner_text() == f"http://192.168.1.23:{state.port}/?run=ui_flow_1"
    assert pg.locator("#share-text").inner_text() == share.SHARE_TEXT
    # Without the password the button is disabled and says why, never a silent no-op.
    import os

    del os.environ[mail.PASSWORD_ENV]
    pg.goto(base + "/?run=no_mail")
    pg.wait_for_selector("#rv .report")
    pg.wait_for_selector("#outputs", state="visible")   # filled by GET /outputs after the review renders
    pg.click("#email-btn")
    wait_open(pg, "email")
    assert pg.locator("#email-send").is_disabled() and pg.locator("#email-to").is_disabled()
    assert pg.locator("#email-help").inner_text().startswith(mail.NOT_CONFIGURED + " (")


def test_a_pasted_link_on_the_drop_screen(browser_page) -> None:
    pg, ctx, base, runs, fake, state = browser_page
    state.can_launch = True
    pg.goto(base + "/")
    pg.wait_for_selector("#doc-link")
    assert pg.locator("#link-max").inner_text() == "50"
    start = pg.locator("#start-btn")
    assert start.is_disabled()
    pg.fill("#doc-link", "http://docs.example.org/a.pdf")
    pg.wait_for_function("document.getElementById('start-btn').disabled"
                         " && !document.getElementById('link-error').hidden")
    assert start.is_disabled() and pg.locator("#link-error").is_visible()
    pg.fill("#run-id", "linked")
    pg.fill("#doc-link", "https://docs.example.org/specs/Payments%20Design%20v2")
    pg.wait_for_function("!document.getElementById('start-btn').disabled"
                         " && document.getElementById('link-error').hidden"
                         " && document.getElementById('cmd-preview').textContent.includes('Payments_Design_v2.pdf')")
    assert start.is_enabled() and pg.locator("#link-error").is_hidden()
    assert "review runs/linked/ui/input/Payments_Design_v2.pdf " in pg.locator("#cmd-preview").inner_text()
    dropped = pg.evaluate_handle("() => { const d = new DataTransfer(); "
                                 "d.setData('text/uri-list', 'https://cdn.example.net/x/y.pdf'); return d; }")
    pg.dispatch_event("#dropzone", "drop", {"dataTransfer": dropped})
    pg.wait_for_function("document.getElementById('doc-link').value === 'https://cdn.example.net/x/y.pdf'"
                         " && document.getElementById('cmd-preview').textContent.includes('/y.pdf')")
    assert pg.locator("#doc-link").input_value() == "https://cdn.example.net/x/y.pdf"
    assert "runs/linked/ui/input/y.pdf" in pg.locator("#cmd-preview").inner_text()
