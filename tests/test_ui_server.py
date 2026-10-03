"""``dra ui`` server (docs/design/ui_design.md sections 4, 8 and 9): loopback guard, run listing,
the review payload, the reviewed PDF, the ``dra review`` subprocess, Stop, and SSE from
``progress.jsonl``. Offline: a fake process, a fake chat client, the committed rehearsal run and
the recorded fixture stream ``tests/fixtures/ui/progress.jsonl`` (a fixture run on the fake gateway,
``tests/fixtures/ui/record_fixtures.py``)."""

from __future__ import annotations

import asyncio
import json
import shutil
import signal
import sys
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from sit_review_agent.cli import app as cli_app
from sit_review_agent.ui import events, rundata
from sit_review_agent.ui.launcher import Launcher, LaunchSpec
from sit_review_agent.ui.server import RemoteHostRefused, UIState, build_app, check_host

REPO = Path(__file__).resolve().parents[1]
LIVE_RUNS = REPO / "docs" / "live_runs"
REHEARSAL = LIVE_RUNS / "rehearsal_concurrent_1"
FIXTURE_EVENTS = Path(__file__).parent / "fixtures" / "ui" / "progress.jsonl"
RUN_FILES = ("report.json", "manifest.json", "anchors.json", "ledger.json", "state.json", "effective_config.json")
PROFILES = [{"name": "", "label": "default", "deadline_s": 3600,
             "stage_limits_s": {"stage_1_end": 2820, "refine_end": 3420, "verdict_end": 3540}, "effort": "high"},
            {"name": "demo", "label": "demo", "deadline_s": 540,
             "stage_limits_s": {"stage_1_end": 265, "refine_end": 465, "verdict_end": 530}, "effort": "medium"}]


class FakeProc:
    def __init__(self, argv: list[str], **kw: Any) -> None:
        self.argv = argv
        self.kw = kw
        self.pid = 4242
        self.code: int | None = None
        self.signals: list[int] = []

    def poll(self) -> int | None:
        return self.code

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)


class FakePopen:
    def __init__(self) -> None:
        self.procs: list[FakeProc] = []

    def __call__(self, argv: list[str], **kw: Any) -> FakeProc:
        p = FakeProc(argv, **kw)
        self.procs.append(p)
        return p


class NoChat:
    async def ask(self, **kw: Any) -> Any:  # pragma: no cover - the server tests never ask
        raise AssertionError("no chat call expected")


def make_state(runs_dir: Path, *, popen: FakePopen | None = None, can_launch: bool = True) -> UIState:
    return UIState(runs_dir=runs_dir.resolve(), repo_root=REPO,
                   launcher=Launcher(repo_root=REPO, popen=popen or FakePopen()), chat_client=NoChat(),
                   can_launch=can_launch, launch_note="" if can_launch else "not the run root",
                   profiles=PROFILES, tools=[{"name": "mcp-internet-search", "enabled": True}], commit="abc1234",
                   poll_s=0.01)


def copy_run(src: Path, dst: Path) -> Path:
    dst.mkdir(parents=True)
    for name in RUN_FILES:
        if (src / name).is_file():
            shutil.copy2(src / name, dst / name)
    return dst


@pytest.fixture
def live_client() -> TestClient:
    return TestClient(build_app(make_state(LIVE_RUNS)))


# ------------------------------------------------------------------ item 1: loopback only


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.2"])
def test_loopback_hosts_are_served_without_warning(host: str) -> None:
    assert check_host(host, allow_remote=False) is None


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "example.org", "::"])
def test_non_loopback_host_is_refused_without_allow_remote(host: str) -> None:
    with pytest.raises(RemoteHostRefused, match="--allow-remote"):
        check_host(host, allow_remote=False)


def test_allow_remote_prints_a_warning_about_no_authentication() -> None:
    warning = check_host("0.0.0.0", allow_remote=True)
    assert warning is not None and "no authentication" in warning


def test_cli_ui_refuses_a_remote_host_with_exit_2() -> None:
    res = CliRunner().invoke(cli_app, ["ui", "--host", "0.0.0.0", "--port", "8799"])
    assert res.exit_code == 2
    assert "not a loopback address" in res.output


# ------------------------------------------------------------------ item 3: runs list and run pages


def test_runs_list_reads_every_run_directory(live_client: TestClient) -> None:
    rows = live_client.get("/runs").json()["runs"]
    by_id = {r["run_id"]: r for r in rows}
    r = by_id["rehearsal_concurrent_1"]
    report = json.loads((REHEARSAL / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((REHEARSAL / "manifest.json").read_text(encoding="utf-8"))
    assert r["findings"] == len(report["findings"])
    assert r["verdict"] == report["verdict"]["label"] and r["confidence"] == report["verdict"]["confidence"]
    assert r["wall_s"] == manifest["extra"]["timing"]["wall_clock_s"]
    assert r["cost_usd"] == manifest["usage"]["cost_usd"]
    assert r["status"] == "finished"


def test_run_page_for_a_recorded_run(live_client: TestClient) -> None:
    info = live_client.get("/runs/rehearsal_concurrent_1").json()
    assert info["has_report"] and not info["has_events"] and info["status"] == "finished"
    assert live_client.get("/").status_code == 200


@pytest.mark.parametrize("bad", ["..", ".hidden", "a..b", "%2e%2e", "x%2Fy", "..%2F..%2Fetc"])
def test_run_ids_cannot_leave_the_runs_dir(live_client: TestClient, bad: str) -> None:
    assert live_client.get(f"/runs/{bad}/report").status_code == 404


def test_run_path_rejects_names_outside(tmp_path: Path) -> None:
    (tmp_path / "ok").mkdir()
    assert rundata.run_path(tmp_path, "ok") == (tmp_path / "ok").resolve()
    for bad in ("..", "../ok", "ok/..", "/etc", ".ok", "a..b", ""):
        assert rundata.run_path(tmp_path, bad) is None
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    assert rundata.run_path(tmp_path, "escape") is None           # a symlink out of the runs dir


def test_report_payload_carries_report_json_unchanged(live_client: TestClient) -> None:
    payload = live_client.get("/runs/rehearsal_concurrent_1/report").json()
    report = json.loads((REHEARSAL / "report.json").read_text(encoding="utf-8"))
    assert payload["report"] == report
    c = payload["derived"]["counts"]
    issues = [f for f in report["findings"] if f["kind"] != "strength"]
    assert c["findings"] == len(report["findings"])
    assert c["critical"] == sum(1 for f in issues if f["severity"] == "critical")
    assert c["strengths"] == sum(1 for f in report["findings"] if f["kind"] == "strength")
    assert c["sound_areas"] == len(report["sound_areas"]) and c["unresolved"] == len(report["unresolved"])
    # No previous version: the Delta tab is shown disabled with this reason, never hidden.
    assert payload["derived"]["delta"] == {"available": False, "reason": "No previous version was given for this run"}


def test_delta_groups_follow_the_note_order(tmp_path: Path) -> None:
    rd = copy_run(REHEARSAL, tmp_path / "delta_run")
    report = json.loads((rd / "report.json").read_text(encoding="utf-8"))
    statuses = ["resolved", "partially_addressed", "still_open", "new_in_update"]
    for i, f in enumerate(report["findings"]):
        f["reassessment"] = {"prior_finding_id": f["id"], "status": statuses[i % 4], "note": "n"}
    report["metadata"]["review_mode"] = "delta"
    (rd / "report.json").write_text(json.dumps(report), encoding="utf-8")
    groups = rundata.delta_view(report)["groups"]
    assert [g["status"] for g in groups] == [*statuses[:3], "withdrawn_on_reassessment", "new_in_update"]
    assert [g["heading"] for g in groups][0] == "fixed (resolved)"
    assert sum(len(g["rows"]) for g in groups) == len(report["findings"])


def test_reviewed_pdf_is_served_only_when_its_hash_matches(live_client: TestClient, tmp_path: Path) -> None:
    res = live_client.get("/runs/rehearsal_concurrent_1/doc.pdf")
    assert res.status_code == 200 and res.headers["content-type"] == "application/pdf"
    rd = copy_run(REHEARSAL, tmp_path / "tampered")
    m = json.loads((rd / "manifest.json").read_text(encoding="utf-8"))
    m["extra"]["doc"]["sha256_pdf"] = "0" * 64
    (rd / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    client = TestClient(build_app(make_state(tmp_path)))
    assert client.get("/runs/tampered/doc.pdf").status_code == 404
    assert client.get("/runs/tampered/report").json()["derived"]["pdf_available"] is False


def test_explain_and_coverage_routes(live_client: TestClient) -> None:
    text = live_client.get("/runs/rehearsal_concurrent_1/explain/FND-001").text
    assert text.startswith("FND-001 ")
    assert live_client.get("/runs/rehearsal_concurrent_1/explain/FND-999").status_code == 404
    assert live_client.get("/runs/rehearsal_concurrent_1/explain/FND-001x").status_code == 404
    cov = live_client.get("/runs/rehearsal_concurrent_1/coverage").json()
    assert cov["criteria"] and cov["rows"]


# ------------------------------------------------------------------ item 2 and section 8: the subprocess


def test_start_launches_dra_review_as_a_subprocess(tmp_path: Path) -> None:
    popen = FakePopen()
    state = make_state(tmp_path, popen=popen)
    client = TestClient(build_app(state))
    before = set(tmp_path.rglob("*"))
    res = client.post("/runs", files={"document": ("My Design v2.pdf", b"%PDF-1.4 fixture", "application/pdf"),
                                      "previous": ("old.pdf", b"%PDF-1.4 old", "application/pdf")},
                      data={"profile": "demo", "no_tools": "1"})
    assert res.status_code == 201, res.text
    run_id = res.json()["run_id"]
    proc = popen.procs[0]
    doc = tmp_path.resolve() / run_id / "ui" / "input" / "My_Design_v2.pdf"
    prev = tmp_path.resolve() / run_id / "ui" / "input" / "previous" / "old.pdf"
    assert proc.argv == [sys.executable, "-m", "sit_review_agent", "review", str(doc), "--profile", "demo",
                         "--v1", str(prev), "--no-tools", "--run-id", run_id]
    assert proc.kw["start_new_session"] is True and proc.kw["cwd"] == str(REPO)
    assert res.json()["command"].startswith("dra review ")
    assert res.json()["command"].endswith(f"--no-tools --run-id {run_id}")
    launch = json.loads((tmp_path / run_id / "ui" / "launch.json").read_text(encoding="utf-8"))
    # Run fix G: the record keeps the arguments without an absolute path under the home folder.
    assert len(launch["args"]) == len(proc.argv) - 3 and launch["args"][-3:] == ["--no-tools", "--run-id", run_id]
    assert str(Path.home()) not in json.dumps(launch)
    assert launch["document"] == f"{run_id}/ui/input/My_Design_v2.pdf"
    assert launch["v1"] == f"{run_id}/ui/input/previous/old.pdf"
    created = set(tmp_path.rglob("*")) - before
    ui_root = tmp_path / run_id / "ui"
    assert all(p == tmp_path / run_id or ui_root in (p, *p.parents) for p in created)
    # One run at a time from this server.
    again = client.post("/runs", files={"document": ("d.pdf", b"%PDF", "application/pdf")})
    assert again.status_code == 409
    info = client.get(f"/runs/{run_id}").json()
    assert info["status"] == "running" and info["argv"] == res.json()["command"]


def test_a_run_id_given_on_the_form_names_the_run_directory(tmp_path: Path) -> None:
    popen = FakePopen()
    client = TestClient(build_app(make_state(tmp_path, popen=popen)))
    res = client.post("/runs", files={"document": ("d.pdf", b"%PDF", "application/pdf")}, data={"run_id": "ui_flow_1"})
    assert res.status_code == 201 and res.json()["run_id"] == "ui_flow_1"
    assert popen.procs[0].argv[-2:] == ["--run-id", "ui_flow_1"] and (tmp_path / "ui_flow_1" / "ui").is_dir()
    popen.procs[0].code = 0
    again = client.post("/runs", files={"document": ("d.pdf", b"%PDF", "application/pdf")},
                        data={"run_id": "ui_flow_1"})
    assert again.status_code == 409                                     # the directory exists
    for bad in ("../x", ".hidden", "a b", "x/y", "a" * 129):
        res = client.post("/runs", files={"document": ("d.pdf", b"%PDF", "application/pdf")}, data={"run_id": bad})
        assert res.status_code == 400, bad
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ui_flow_1"]


def test_stop_sends_sigint_to_the_child(tmp_path: Path) -> None:
    popen = FakePopen()
    client = TestClient(build_app(make_state(tmp_path, popen=popen)))
    run_id = client.post("/runs", files={"document": ("d.pdf", b"%PDF", "application/pdf")}).json()["run_id"]
    assert client.post(f"/runs/{run_id}/stop").json() == {"stopped": True, "signal": "SIGINT"}
    assert popen.procs[0].signals == [signal.SIGINT]
    popen.procs[0].code = 130
    assert client.post(f"/runs/{run_id}/stop").status_code == 409
    assert client.get(f"/runs/{run_id}").json()["exit_code"] == 130


def test_start_refuses_bad_input(tmp_path: Path) -> None:
    client = TestClient(build_app(make_state(tmp_path)))
    assert client.post("/runs", files={"document": ("d.docx", b"x", "application/octet-stream")}).status_code == 400
    assert client.post("/runs", files={"document": ("d.pdf", b"x", "application/pdf")},
                       data={"profile": "nope"}).status_code == 400
    off = TestClient(build_app(make_state(tmp_path, can_launch=False)))
    assert off.post("/runs", files={"document": ("d.pdf", b"x", "application/pdf")}).status_code == 409
    assert list(tmp_path.iterdir()) == []


def test_launch_spec_display_is_what_a_cli_user_types() -> None:
    spec = LaunchSpec(run_id="r1", document=REPO / "runs" / "r1" / "ui" / "input" / "a b.pdf", profile="demo")
    assert spec.display(REPO) == "dra review 'runs/r1/ui/input/a b.pdf' --profile demo --run-id r1"


# ------------------------------------------------------------------ item 3: SSE from progress.jsonl


def sse_ids(text: str) -> list[int]:
    return [int(line[4:]) for line in text.splitlines() if line.startswith("id: ")]


def fixture_run(tmp_path: Path, lines: int | None = None) -> Path:
    rd = tmp_path / "fixture_run"
    rd.mkdir()
    src = FIXTURE_EVENTS.read_text(encoding="utf-8").splitlines(keepends=True)
    (rd / "progress.jsonl").write_text("".join(src if lines is None else src[:lines]), encoding="utf-8")
    return rd


def test_sse_replays_the_whole_stream_and_ends(tmp_path: Path) -> None:
    fixture_run(tmp_path)
    n = len(events.read_all(FIXTURE_EVENTS))
    client = TestClient(build_app(make_state(tmp_path)))
    res = client.get("/runs/fixture_run/events")
    assert res.headers["content-type"].startswith("text/event-stream")
    assert sse_ids(res.text) == list(range(1, n + 1))
    assert "event: end" in res.text


def test_sse_reconnect_resumes_after_the_last_sequence(tmp_path: Path) -> None:
    fixture_run(tmp_path)
    n = len(events.read_all(FIXTURE_EVENTS))
    client = TestClient(build_app(make_state(tmp_path)))
    assert sse_ids(client.get("/runs/fixture_run/events", headers={"Last-Event-ID": "50"}).text) \
        == list(range(51, n + 1))
    assert sse_ids(client.get("/runs/fixture_run/events?after=60").text) == list(range(61, n + 1))
    # A reconnect past the end of a finished stream ends at once instead of following forever.
    late = client.get(f"/runs/fixture_run/events?after={n + 100}").text
    assert sse_ids(late) == [] and "event: end" in late
    assert client.get("/runs/fixture_run/events?after=x").status_code == 400


def test_a_stream_without_run_finished_is_a_running_run(tmp_path: Path) -> None:
    rd = fixture_run(tmp_path, lines=70)
    assert rundata.run_status(rd) == "running"
    (rd / "progress.jsonl").write_text(FIXTURE_EVENTS.read_text(encoding="utf-8"), encoding="utf-8")
    assert rundata.run_status(rd) == "ended"          # finished stream, no report.json


async def test_tail_follows_a_growing_file_and_waits_for_whole_lines(tmp_path: Path) -> None:
    lines = FIXTURE_EVENTS.read_text(encoding="utf-8").splitlines(keepends=True)
    path = tmp_path / "progress.jsonl"
    path.write_text("".join(lines[:5]) + lines[5][:20], encoding="utf-8")   # writer is mid-line
    seen: list[int] = []

    async def consume() -> None:
        async for ev in events.tail(path, poll_s=0.01):
            seen.append(ev["seq"])

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    assert seen == [1, 2, 3, 4, 5]
    with path.open("a", encoding="utf-8") as fh:
        fh.write(lines[5][20:] + "".join(lines[6:]))
    await asyncio.wait_for(task, 2)
    assert seen == list(range(1, len(lines) + 1))       # stopped by "run finished"


def test_bad_lines_are_skipped_not_invented(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    good = FIXTURE_EVENTS.read_text(encoding="utf-8").splitlines(keepends=True)[:3]
    path.write_text(good[0] + "not json\n" + json.dumps({"seq": 2, "t": "x"}) + "\n" + good[1] + good[2],
                    encoding="utf-8")
    res = events.read_new(path)
    assert [e["seq"] for e in res.events] == [1, 2, 3] and res.bad_lines == 2


def test_the_reader_takes_every_line_of_the_recorded_fixture() -> None:
    """The fixture is a real ``progress.jsonl`` (``tests/fixtures/ui/record_fixtures.py``); its schema
    check is in ``tests/test_ui_events.py``."""
    evs = events.read_all(FIXTURE_EVENTS)
    raw = FIXTURE_EVENTS.read_text(encoding="utf-8").splitlines()
    assert len(evs) == len(raw)
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))
    assert evs[0]["type"] == events.STARTED and evs[-1]["type"] == events.FINISHED
    assert all(e["t"] <= f["t"] for e, f in zip(evs, evs[1:], strict=False))


# ------------------------------------------------------------------ v2: what the rail reads (ui_restyle.md section 4)


def test_a_running_row_carries_its_stage_clock_and_open_calls_from_the_records(tmp_path: Path) -> None:
    rd = fixture_run(tmp_path, lines=70)
    evs = events.read_all(rd / "progress.jsonl")
    row = next(r for r in TestClient(build_app(make_state(tmp_path))).get("/runs").json()["runs"]
               if r["run_id"] == "fixture_run")
    assert row["status"] == "running"
    # The last record names the stage (refine, its call just opened) and the run clock is its run_s.
    assert row["stage"] == next(e["phase"] for e in reversed(evs) if e["phase"] not in rundata.NOT_A_STAGE)
    assert row["run_s"] == evs[-1]["run_s"]
    opened = {e["fields"]["call_id"] for e in evs if e["type"] == "call_opened"}
    closed = {e["fields"]["call_id"] for e in evs if e["type"] in ("call_closed", "call_cut")}
    assert row["open_calls"] == len(opened - closed) == 1
    # The whole stream: nothing open, the report stage last, the clock at the final record.
    (rd / "progress.jsonl").write_text(FIXTURE_EVENTS.read_text(encoding="utf-8"), encoding="utf-8")
    full = events.read_all(rd / "progress.jsonl")
    state = rundata.progress_state(full)
    assert state == {"stage": "report", "run_s": full[-1]["run_s"], "open_calls": 0}


def test_a_finished_row_carries_verdict_confidence_wall_and_the_recorded_command(live_client: TestClient) -> None:
    rows = {r["run_id"]: r for r in live_client.get("/runs").json()["runs"]}
    r = rows["sit_sample_tools_1"]
    report = json.loads((LIVE_RUNS / "sit_sample_tools_1" / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((LIVE_RUNS / "sit_sample_tools_1" / "manifest.json").read_text(encoding="utf-8"))
    assert (r["verdict"], r["confidence"]) == (report["verdict"]["label"], report["verdict"]["confidence"])
    assert r["wall_s"] == manifest["extra"]["timing"]["wall_clock_s"]
    assert r["model_calls"] == manifest["extra"]["model"]["calls_logged"]
    assert r["started_at"] == manifest["timestamps"]["start_utc"]
    assert r["version"] == report["metadata"]["documents"][0]["version"]
    assert r["argv"] == "dra " + " ".join(manifest["extra"]["code"]["argv"])
    assert r["stage"] is None and r["run_s"] is None and r["open_calls"] == 0   # no progress.jsonl was recorded


def test_meta_states_the_backend_version_and_config_files() -> None:
    from sit_review_agent import __version__
    from sit_review_agent.ui.server import build_state

    state = build_state(runs_dir=LIVE_RUNS, chat_client=NoChat())
    meta = TestClient(build_app(state)).get("/meta").json()
    assert meta["backend"] in ("claude_code", "anthropic_api") and meta["version"] == __version__
    assert meta["model"] and meta["auth_env"] == "SIT_MCP_API_KEY"
    assert "config/agent.yaml" in meta["config_files"] and "config/tools.yaml" in meta["config_files"]
    assert meta["config_files"][-1] == "config/ui.yaml"
    assert [t["name"] for t in meta["tools"]][:2] == ["mcp-internet-search", "mcp-research-information"]
    assert state.probe is not None


SERVERS = [{"name": "mcp-internet-search", "enabled": True}, {"name": "mcp-research-information", "enabled": True},
           {"name": "mcp-browser-automation-pw", "enabled": False},
           {"name": "mcp-document-intelligence", "enabled": False}]


def tools_state(runs: Path, **kw: Any) -> UIState:
    st = make_state(runs, **kw)
    st.tools = list(SERVERS)
    return st


def test_tools_read_the_newest_run_that_recorded_a_warm_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = tmp_path / "runs"
    sample = LIVE_RUNS / "sit_sample_tools_1"
    rd = copy_run(sample, runs / "sit_sample_tools_1")
    for name in ("tools_list.jsonl", "tools.jsonl"):
        shutil.copy2(sample / name, rd / name)
    copy_run(REHEARSAL, runs / "rehearsal_concurrent_1")       # no tool records: never the source
    monkeypatch.delenv("SIT_MCP_API_KEY", raising=False)
    out = TestClient(build_app(tools_state(runs))).get("/tools").json()
    assert out["from_run"] == "sit_sample_tools_1" and out["key_present"] is False and out["probe"] is None
    listed = json.loads((sample / "tools_list.jsonl").read_text(encoding="utf-8").splitlines()[0])
    by_server: dict[str, int] = {}
    for t in listed["tools"]:
        by_server[t["server"]] = by_server.get(t["server"], 0) + 1
    calls = [json.loads(ln) for ln in (sample / "tools.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = {r["name"]: r for r in out["servers"]}
    assert list(rows) == [s["name"] for s in SERVERS]
    for name, n in by_server.items():
        assert rows[name]["warm"] is True and rows[name]["tools"] == n and rows[name]["at"] == listed["listed_at"]
        assert rows[name]["calls_failed"] == sum(1 for c in calls if c["server"] == name and c["is_error"])
        assert rows[name]["calls_ok"] == sum(1 for c in calls if c["server"] == name and not c["is_error"])
    for name in ("mcp-browser-automation-pw", "mcp-document-intelligence"):
        assert rows[name] == {"name": name, "enabled": False, "warm": None, "at": None, "tools": None, "status": None,
                              "calls_ok": 0, "calls_failed": 0}


def test_tools_with_no_recorded_warm_up_claim_nothing(tmp_path: Path) -> None:
    copy_run(REHEARSAL, tmp_path / "rehearsal_concurrent_1")
    out = TestClient(build_app(tools_state(tmp_path))).get("/tools").json()
    assert out["from_run"] is None
    assert all(r["warm"] is None and r["at"] is None and r["tools"] is None for r in out["servers"])


def test_tools_take_the_warm_up_record_time_from_the_run_start(tmp_path: Path) -> None:
    rd = fixture_run(tmp_path)                                  # mcp_warmup "none" at t=0.5, no tools_list.jsonl
    (rd / "manifest.json").write_text(json.dumps({"timestamps": {"start_utc": "2026-10-03T04:24:22Z"}}),
                                      encoding="utf-8")
    client = TestClient(build_app(tools_state(tmp_path)))
    assert client.get("/tools").json()["from_run"] is None       # "none": no warm-up was attempted in that run
    lines = (rd / "progress.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
    for i, ln in enumerate(lines):
        ev = json.loads(ln)
        if ev["type"] == "mcp_warmup":
            ev["fields"]["status"] = "failed"
            lines[i] = json.dumps(ev) + "\n"
    (rd / "progress.jsonl").write_text("".join(lines), encoding="utf-8")
    out = client.get("/tools").json()
    assert out["from_run"] == "fixture_run"
    row = next(r for r in out["servers"] if r["name"] == "mcp-internet-search")
    assert row["status"] == "failed"
    assert row["warm"] is False and row["at"] is None            # no tools/list answer was recorded for it
    assert rundata._iso_plus("2026-10-03T04:24:22Z", 0.5) == "2026-10-03T04:24:22Z"
    assert rundata._iso_plus("2026-10-03T04:24:22Z", 61) == "2026-10-03T04:25:23Z"
    assert rundata._iso_plus(None, 61) is None


def test_the_probe_runs_only_with_the_key_in_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    async def fake_probe() -> dict[str, Any]:
        calls.append(1)
        return {"at": "2026-10-03T08:00:00Z", "servers": [{"name": "mcp-internet-search", "warm": True, "tools": 3,
                                                           "health": "ok", "error": None}], "auth_failed": False,
                "lines": []}

    st = tools_state(tmp_path)
    st.probe = fake_probe
    client = TestClient(build_app(st))
    monkeypatch.delenv("SIT_MCP_API_KEY", raising=False)
    res = client.post("/tools/probe")
    assert res.status_code == 409 and "SIT_MCP_API_KEY is not set" in res.json()["error"] and calls == []
    monkeypatch.setenv("SIT_MCP_API_KEY", "k")
    res = client.post("/tools/probe")
    assert res.status_code == 200 and calls == [1] and res.json()["servers"][0]["warm"] is True
    assert client.get("/tools").json()["probe"] == res.json()      # the last probe travels with the status
    st.tools = [dict(s, enabled=False) for s in SERVERS]
    assert client.post("/tools/probe").status_code == 409 and calls == [1]
    st.probe = None
    st.tools = list(SERVERS)
    assert client.post("/tools/probe").status_code == 409 and calls == [1]


def test_the_sample_documents_come_from_ui_yaml_and_missing_files_are_left_out(tmp_path: Path) -> None:
    from sit_review_agent.ui.server import load_documents

    pdf = REPO / "eval" / "synthetic" / "payments_orchestration" / "design_v1.pdf"
    (tmp_path / "ui.yaml").write_text(
        "email:\n  host: ''\ndocuments:\n"
        f"  - label: Payments orchestration\n    path: {pdf.relative_to(REPO)}\n"
        "  - label: Missing\n    path: eval/nowhere/design_v1.pdf\n"
        "  - label: Not a document\n    path: pyproject.toml\n"
        "  - path: no-label.pdf\n", encoding="utf-8")
    docs = load_documents(tmp_path / "ui.yaml", REPO)
    assert [d["label"] for d in docs] == ["Payments orchestration"]
    assert docs[0] == {"name": "doc-1", "label": "Payments orchestration", "path": str(pdf.relative_to(REPO)),
                       "file": "payments_orchestration_design_v1.pdf", "abspath": str(pdf)}
    assert load_documents(tmp_path / "absent.yaml", REPO) == []
    st = make_state(tmp_path)
    st.documents = docs
    client = TestClient(build_app(st))
    assert client.get("/documents").json() == {"items": [{k: docs[0][k] for k in ("name", "label", "file", "path")}]}
    res = client.get("/documents/doc-1")
    assert res.status_code == 200 and res.headers["content-type"] == "application/pdf"
    assert res.content == pdf.read_bytes()
    assert client.get("/documents/doc-2").status_code == 404
