"""The chat panel (docs/design/ui_design.md section 6, planner rulings 2026-10-03): one Opus 5.5 call
at medium effort per question, grounded in the run directory only, citations resolved against the
run, unsupported answers shown with no prose, a cap of 20 calls or 3.00 USD per run, logged to
``runs/<id>/ui/chat.jsonl`` and nowhere else. Offline: a fake client and a fake ``claude`` runner."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from sit_review_agent.llm.claude_code import CompletedRun
from sit_review_agent.ui import chat
from sit_review_agent.ui.launcher import Launcher
from sit_review_agent.ui.server import UIState, build_app

REPO = Path(__file__).resolve().parents[1]
REHEARSAL = REPO / "docs" / "live_runs" / "rehearsal_concurrent_1"
FIXTURE_EVENTS = Path(__file__).parent / "fixtures" / "ui" / "progress.jsonl"
RUN_FILES = ("report.json", "manifest.json", "anchors.json", "ledger.json", "state.json", "effective_config.json")


class FakeChat:
    """Returns scripted answers and records what it was sent."""

    def __init__(self, *answers: dict[str, Any] | None, cost: float | None = 0.05) -> None:
        self.answers = list(answers)
        self.cost = cost
        self.calls: list[dict[str, Any]] = []

    async def ask(self, **kw: Any) -> chat.ChatReply:
        # The real client spawns `claude` in this directory; a missing cwd failed the first live call.
        assert Path(kw["cwd"]).is_dir(), f"cwd {kw['cwd']} does not exist"
        self.calls.append(kw)
        data = self.answers.pop(0) if self.answers else None
        return chat.ChatReply(data, {"input_tokens": 10, "output_tokens": 5}, self.cost, chat.MODEL, 0.4,
                              None if data is not None else "scripted failure")


def answer(text: str = "Because of FND-005.", *, fnd: list[str] | None = None, ev: list[str] | None = None,
           other: list[str] | None = None, supported: bool = True) -> dict[str, Any]:
    return {"answer": text, "cited_finding_ids": fnd if fnd is not None else ["FND-005"],
            "cited_evidence_ids": ev or [], "cited_other_ids": other or [], "supported": supported}


@pytest.fixture
def run(tmp_path: Path) -> Path:
    rd = tmp_path / "runs" / "rehearsal_concurrent_1"
    rd.mkdir(parents=True)
    for name in RUN_FILES:
        shutil.copy2(REHEARSAL / name, rd / name)
    return rd


def client_for(run: Path, fake: FakeChat) -> TestClient:
    state = UIState(runs_dir=run.parent.resolve(), repo_root=REPO, launcher=Launcher(repo_root=REPO),
                    chat_client=fake, profiles=[], tools=[])
    return TestClient(build_app(state))


def files_under(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file()}


def test_a_resolving_answer_is_shown_with_its_citations(run: Path) -> None:
    criterion = sorted(chat.run_ids(run).criteria)[0]
    fake = FakeChat(answer(fnd=["FND-005"], ev=["EV-017", "EV-045"],
                           other=["AD-011", "DEG-002", f"coverage:{criterion}"]))
    res = client_for(run, fake).post("/runs/rehearsal_concurrent_1/chat", json={"question": "Why NFR-2?"})
    assert res.status_code == 200, res.text
    turn = res.json()["turn"]
    assert turn["rendered_as"] == "answer" and turn["answer"] == "Because of FND-005."
    assert turn["citations"][:3] == ["FND-005", "EV-017", "EV-045"] and turn["dropped"] == []
    assert f"coverage:{criterion}" in turn["citations"]


def test_an_invented_citation_is_dropped_and_flagged(run: Path) -> None:
    fake = FakeChat(answer(fnd=["FND-005", "FND-999"], ev=["EV-9999"], other=["AD-999", "RQ-001"]))
    turn = client_for(run, fake).post("/runs/rehearsal_concurrent_1/chat", json={"question": "q"}).json()["turn"]
    assert turn["citations"] == ["FND-005"]
    assert turn["dropped"] == ["FND-999", "EV-9999", "AD-999", "RQ-001"]
    assert turn["rendered_as"] == "answer"          # one citation still resolves; the rest are flagged


def test_an_unsupported_answer_renders_with_no_prose(run: Path) -> None:
    fake = FakeChat(answer("Probably fine, the sizing looks generous.", fnd=[], supported=False))
    turn = client_for(run, fake).post("/runs/rehearsal_concurrent_1/chat", json={"question": "MSK?"}).json()["turn"]
    assert turn["rendered_as"] == "unsupported" and turn["answer"] == ""
    assert "does not answer" in turn["unsupported_reason"]


def test_a_supported_answer_with_no_resolving_citation_is_unsupported(run: Path) -> None:
    fake = FakeChat(answer("FND-777 says so.", fnd=["FND-777"]))
    turn = client_for(run, fake).post("/runs/rehearsal_concurrent_1/chat", json={"question": "q"}).json()["turn"]
    assert turn["rendered_as"] == "unsupported" and turn["answer"] == ""
    assert turn["dropped"] == ["FND-777"] and turn["unsupported_reason"] == "no citation resolves in this run"


def test_the_cap_stops_the_21st_call(run: Path) -> None:
    fake = FakeChat(*[answer() for _ in range(25)], cost=0.01)
    client = client_for(run, fake)
    for _ in range(chat.MAX_CALLS):
        assert client.post("/runs/rehearsal_concurrent_1/chat", json={"question": "q"}).status_code == 200
    res = client.post("/runs/rehearsal_concurrent_1/chat", json={"question": "q"})
    assert res.status_code == 429 and "cap" in res.json()["error"]
    assert len(fake.calls) == chat.MAX_CALLS
    b = client.get("/runs/rehearsal_concurrent_1/chat").json()["budget"]
    assert b["calls_used"] == 20 and b["stopped"] is True


def test_the_cost_cap_stops_the_chat(run: Path) -> None:
    fake = FakeChat(answer(), answer(), cost=1.6)
    client = client_for(run, fake)
    assert client.post("/runs/rehearsal_concurrent_1/chat", json={"question": "q"}).status_code == 200
    second = client.post("/runs/rehearsal_concurrent_1/chat", json={"question": "q"})
    assert second.status_code == 200
    assert fake.calls[1]["max_budget_usd"] == pytest.approx(chat.MAX_COST_USD - 1.6)
    assert client.post("/runs/rehearsal_concurrent_1/chat", json={"question": "q"}).status_code == 429
    assert len(fake.calls) == 2


def test_a_failed_call_counts_and_is_logged(run: Path) -> None:
    fake = FakeChat(None, cost=None)
    turn = client_for(run, fake).post("/runs/rehearsal_concurrent_1/chat", json={"question": "q"}).json()["turn"]
    assert turn["rendered_as"] == "error" and turn["counted"] is True and turn["error"] == "scripted failure"
    assert chat.budget(run)["calls_used"] == 1 and chat.budget(run)["calls_with_unknown_cost"] == 1


def test_the_chat_writes_only_its_log_under_ui(run: Path) -> None:
    root = run.parent.parent
    before = files_under(root)
    client_for(run, FakeChat(answer())).post("/runs/rehearsal_concurrent_1/chat", json={"question": "q"})
    created = files_under(root) - before
    assert created == {run / "ui" / "chat.jsonl"}
    entry = json.loads((run / "ui" / "chat.jsonl").read_text(encoding="utf-8"))
    for key in ("question", "prompt_sha256", "requested_model", "effort", "usage", "cost_usd", "citations", "dropped"):
        assert key in entry
    assert entry["requested_model"] == "claude-opus-5-5" and entry["effort"] == "medium"
    assert not (run / "llm.jsonl").exists()


def test_the_chat_is_off_while_the_run_is_in_progress(run: Path) -> None:
    lines = FIXTURE_EVENTS.read_text(encoding="utf-8").splitlines(keepends=True)[:40]
    (run / "report.json").rename(run / "report.json.bak")
    (run / "progress.jsonl").write_text("".join(lines), encoding="utf-8")
    fake = FakeChat(answer())
    client = client_for(run, fake)
    assert client.get("/runs/rehearsal_concurrent_1/chat").json()["running"] is True
    res = client.post("/runs/rehearsal_concurrent_1/chat", json={"question": "q"})
    assert res.status_code == 409 and "in progress" in res.json()["error"]
    assert fake.calls == []


def test_the_corpus_is_the_run_directory_only(run: Path) -> None:
    (run / "llm.jsonl").write_text('{"canary": "LLM-JSONL-CANARY"}\n', encoding="utf-8")
    (run / "doc.pdf").write_bytes(b"%PDF PDF-CANARY")
    fake = FakeChat(answer("FIRST-ANSWER-CANARY"), answer())
    client = client_for(run, fake)
    client.post("/runs/rehearsal_concurrent_1/chat", json={"question": "one"})
    client.post("/runs/rehearsal_concurrent_1/chat", json={"question": "two"})
    second = fake.calls[1]["prompt"]
    assert "<question>\ntwo\n</question>" in second and "<question>\none" not in second
    assert "FIRST-ANSWER-CANARY" not in second and "LLM-JSONL-CANARY" not in second and "PDF-CANARY" not in second
    data = json.loads(second.split("<review_data>\n", 1)[1].split("\n</review_data>", 1)[0])
    assert set(data) >= {"findings", "verdict", "evidence_ledger", "anchors", "coverage", "unresolved", "limitations"}
    assert "run_manifest" not in data and all("provenance" not in f for f in data["findings"])
    assert fake.calls[1]["schema"] == chat.ANSWER_SCHEMA and fake.calls[1]["cwd"] == run / "ui"


def test_the_answer_schema_is_strict() -> None:
    s = chat.ANSWER_SCHEMA
    assert s["additionalProperties"] is False
    assert set(s["required"]) == {"answer", "cited_finding_ids", "cited_evidence_ids", "cited_other_ids", "supported"}
    assert s["properties"]["supported"]["type"] == "boolean"


@pytest.mark.parametrize("q,status", [("", 400), ("x" * (chat.MAX_QUESTION_CHARS + 1), 400)])
def test_bad_questions_are_refused_without_a_call(run: Path, q: str, status: int) -> None:
    fake = FakeChat(answer())
    assert client_for(run, fake).post("/runs/rehearsal_concurrent_1/chat", json={"question": q}).status_code == status
    assert fake.calls == []


# ------------------------------------------------------------------ the Claude Code client


def stream_result(structured: Any, *, cost: float = 0.12, is_error: bool = False) -> str:
    result = {"type": "result", "subtype": "error" if is_error else "success", "is_error": is_error,
              "result": "boom" if is_error else "", "structured_output": structured, "total_cost_usd": cost,
              "usage": {"input_tokens": 1000, "output_tokens": 200}, "modelUsage": {"claude-opus-5-5": {}}}
    return json.dumps({"type": "system", "subtype": "init"}) + "\n" + json.dumps(result) + "\n"


async def test_client_argv_env_and_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def runner(argv: list[str], stdin: str, env: dict[str, str], cwd: Path, timeout_s: float) -> CompletedRun:
        seen.update(argv=argv, stdin=stdin, env=env, cwd=cwd, timeout_s=timeout_s)
        return CompletedRun(0, stream_result(answer()), "")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder-not-a-key")
    client = chat.ClaudeCodeChatClient(executable="claude", extra_args=("--setting-sources", ""), runner=runner)
    reply = await client.ask(system="S", prompt="P", schema=chat.ANSWER_SCHEMA, cwd=tmp_path, max_budget_usd=2.5)
    argv = seen["argv"]
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"
    assert argv[argv.index("--effort") + 1] == "medium"
    assert json.loads(argv[argv.index("--json-schema") + 1]) == chat.ANSWER_SCHEMA
    assert argv[argv.index("--tools") + 1] == "" and "--resume" not in argv and "--bare" not in argv
    assert argv[argv.index("--max-budget-usd") + 1] == "2.50" and argv[-2:] == ["--setting-sources", ""]
    assert "ANTHROPIC_API_KEY" not in seen["env"] and seen["stdin"] == "P" and seen["cwd"] == tmp_path
    assert reply.data == answer() and reply.cost_usd == 0.12 and reply.model == "claude-opus-5-5"
    assert reply.usage == {"input_tokens": 1000, "output_tokens": 200} and reply.error is None


async def test_client_reports_an_error_result(tmp_path: Path) -> None:
    async def runner(*a: Any, **k: Any) -> CompletedRun:
        return CompletedRun(1, stream_result(None, is_error=True), "")

    reply = await chat.ClaudeCodeChatClient(runner=runner).ask(system="S", prompt="P", schema={}, cwd=tmp_path,
                                                               max_budget_usd=None)
    assert reply.data is None and reply.error and reply.cost_usd == 0.12


async def test_client_reports_no_result(tmp_path: Path) -> None:
    async def runner(*a: Any, **k: Any) -> CompletedRun:
        return CompletedRun(2, "", "not logged in")

    reply = await chat.ClaudeCodeChatClient(runner=runner).ask(system="S", prompt="P", schema={}, cwd=tmp_path,
                                                               max_budget_usd=None)
    assert reply.data is None and "no result" in (reply.error or "")
