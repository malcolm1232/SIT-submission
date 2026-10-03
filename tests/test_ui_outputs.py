"""The three output actions of a finished review (decision #36, 2026-10-03): the self-contained HTML
export with ``report.md`` and ``report.json`` beside it, email through the SMTP server named in
``config/ui.yaml``, and the share link on this network. Offline: the committed run
``docs/live_runs/ui_flow_1`` (a live run with two chat turns), a local fake SMTP server in this file,
and an ``httpx.MockTransport`` for the pasted link."""

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


def test_the_export_is_self_contained_with_no_script_and_no_external_resource(flow_runs: Path) -> None:
    html = export.export_html(flow_runs / "ui_flow_1", replayed=False)
    doc = parse(html)
    tags = {t for t, _ in doc.tags}
    assert "script" not in tags and "link" not in tags and "img" not in tags and "iframe" not in tags
    for _, attrs in doc.tags:
        assert "src" not in attrs and not any(k.startswith("on") for k in attrs)
    assert "@import" not in html and "url(" not in html
    tokens = (export.STATIC_DIR / "tokens.css").read_text(encoding="utf-8")
    assert "--red-9:" in html and tokens.split(":root", 1)[1].split("}", 1)[0].strip() in html   # tokens inlined


def test_model_text_cannot_inject_markup_or_load_an_image(tmp_path: Path) -> None:
    rd = tmp_path / "r"
    rd.mkdir()
    (rd / "report.md").write_text('# Design review: x\n\n<script>alert(1)</script> ![p](https://example.org/p.png)'
                                  ' [j](javascript:alert(1))\n', encoding="utf-8")
    (rd / "report.json").write_text("{}", encoding="utf-8")
    html = export.export_html(rd, replayed=False)
    doc = parse(html)
    assert "script" not in {t for t, _ in doc.tags} and "img" not in {t for t, _ in doc.tags}
    assert all(not str(a.get("href", "")).startswith("javascript") for _, a in doc.tags)
    assert "&lt;script&gt;" in html


def test_the_chat_transcript_is_appended_apart_and_only_when_it_exists(flow_runs: Path, tmp_path: Path) -> None:
    html = export.export_html(flow_runs / "ui_flow_1", replayed=False)
    rows = [json.loads(ln) for ln in (FLOW / "ui" / "chat.jsonl").read_text(encoding="utf-8").splitlines()]
    doc = parse(html)
    assert export.CHAT_HEADING == "Reading-aid chat transcript (not part of the review)"
    assert doc.texts("h2")[-1] == export.CHAT_HEADING
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
    dl = client.get("/runs/ui_flow_1/export.html?download=1")
    assert dl.headers["content-disposition"] == 'attachment; filename="ui_flow_1_review.html"'
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
