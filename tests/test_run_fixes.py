"""Run fixes of 3 Oct 2026 (live review of a 30-page document with the tool servers).

B: every ``progress.jsonl`` record written during a run carries a number in ``run_s``, including
the records written while the run is set up (``run_started``, the MCP warm-up's ``waking`` lines).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from sit_review_agent.clock import FakeClock
from sit_review_agent.orchestrator import RunRequest, run_review
from sit_review_agent.progress import ConsoleProgress
from sit_review_agent.selftest import FIXTURE_DIR, selftest_config
from test_progress_console import scenario


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sinks(root: Path) -> Any:
    made: list[Path] = []

    def make(clock: FakeClock, out: io.StringIO) -> ConsoleProgress:
        path = root / f"progress-{len(made)}.jsonl"
        made.append(path)
        return ConsoleProgress(clock=clock, stream=out, jsonl_path=path)

    make.paths = made  # type: ignore[attr-defined]
    return make


def _no_null_run_s(records: list[dict[str, Any]]) -> list[str]:
    return [f"{r['seq']}:{r['type']}" for r in records
            if not isinstance(r.get("run_s"), int | float) or isinstance(r.get("run_s"), bool)]


# ------------------------------------------------------------------------------ B: run_s


async def test_b_every_record_of_a_run_and_its_resume_carries_run_s(tmp_path: Path) -> None:
    for name in ("selftest", "fail_resume"):
        make = _sinks(tmp_path / name)
        (tmp_path / name).mkdir()
        await scenario(name, tmp_path / name, progress=make)
        for path in make.paths:
            records = _jsonl(path)
            assert records and records[0]["type"] == "run_started"
            assert _no_null_run_s(records) == [], (name, path.name)


class _WakingTools:
    """A tool gateway whose warm-up writes its ``waking`` lines at once, as the live MCP gateway does
    while the run is still being set up (LLM preflight, models.retrieve)."""

    inner = None

    def __init__(self, progress: Any) -> None:
        self.progress = progress

    async def warm_up(self) -> dict[str, str]:
        self.progress.emit("tools", "waking mcp-research-information (~90 s)", "wait")
        self.progress.emit("tools", "waking mcp-standards (~90 s)", "wait")
        return {}

    async def list_tools(self) -> list[Any]:
        return []

    async def aclose(self) -> None:
        return None


async def test_b_waking_lines_written_during_setup_carry_run_s(tmp_path: Path) -> None:
    cfg = selftest_config(tmp_path)
    jsonl = tmp_path / "progress.jsonl"
    clock = FakeClock()
    prog = ConsoleProgress(clock=clock, stream=io.StringIO(), jsonl_path=jsonl)
    await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=cfg, run_id="rf-waking", plan_only=True),
                     clock=clock, progress=prog, tools_factory=lambda rd, off, clk, p: _WakingTools(p))
    records = _jsonl(jsonl)
    waking = [r for r in records if r["message"].startswith("waking ")]
    assert len(waking) == 2
    assert all(isinstance(r["run_s"], int | float) and r["run_s"] >= 0 for r in waking)
    assert _no_null_run_s(records) == []


# ------------------------------------------------------------------------------ C: Tools used


def _header_row(md: str, label: str) -> str:
    row = next(line for line in md.splitlines() if line.startswith(f"| {label} |"))
    return row.split("|")[2].strip()


def test_c_tools_used_lists_only_servers_that_received_a_call(review_dict: dict[str, Any]) -> None:
    from sit_review_agent.models import Review
    from sit_review_agent.report.render import render_markdown

    d = json.loads(json.dumps(review_dict))
    entry = {"enabled": True, "server_version": None, "mode": "live"}
    d["run_manifest"]["tools"] = [{**entry, "name": "mcp-search"},
                                  {**entry, "name": "mcp-research-information"},
                                  {**entry, "name": "mcp-standards", "enabled": False}]
    d["research_log"]["tool_calls_by_tool"] = {"mcp-search": 4, "mcp-research-information": 0}
    md = render_markdown(Review.model_validate(d))
    assert _header_row(md, "Tools used") == "mcp-search"
    assert _header_row(md, "Tools disabled") == "mcp-standards"

    d["research_log"]["tool_calls_by_tool"] = {}
    md = render_markdown(Review.model_validate(d))
    assert _header_row(md, "Tools used") == "none"


# ------------------------------------------------------------------------------ D: session reopens


def test_d_manifest_counts_the_session_reopens_of_the_gateway_stack() -> None:
    from types import SimpleNamespace

    from sit_review_agent.manifest import session_reopens

    base = SimpleNamespace(session_events=[
        {"server": "mcp-search", "reason": "closed by the server: x", "idle_s": 3.0, "at_s": 40.0},
        {"server": "mcp-search", "reason": "idle", "idle_s": 130.0, "at_s": 300.0},
        {"server": "mcp-standards", "reason": "idle", "idle_s": 140.0, "at_s": 310.0}])
    stack = SimpleNamespace(inner=SimpleNamespace(inner=base))
    assert session_reopens(SimpleNamespace(tools=stack)) == {
        "session_reopens": 3, "session_reopens_by_server": {"mcp-search": 2, "mcp-standards": 1}}
    empty = SimpleNamespace(tools=SimpleNamespace(inner=None, session_events=[]))
    assert session_reopens(empty)["session_reopens"] == 0
    assert session_reopens(SimpleNamespace(tools=None)) == {"session_reopens": 0, "session_reopens_by_server": {}}


def test_d_report_shows_the_session_reopen_line_zero_included(review_dict: dict[str, Any]) -> None:
    from sit_review_agent.models import Review
    from sit_review_agent.report.render import render_markdown

    d = json.loads(json.dumps(review_dict))
    tools = d["run_manifest"]["extra"].setdefault("tools", {})
    tools.update(session_reopens=0, session_reopens_by_server={})
    assert _header_row(render_markdown(Review.model_validate(d)), "Tool session reopens") == "0"
    tools.update(session_reopens=2, session_reopens_by_server={"mcp-search": 2})
    assert _header_row(render_markdown(Review.model_validate(d)), "Tool session reopens") == "2 (mcp-search: 2)"
    tools.pop("session_reopens")
    assert _header_row(render_markdown(Review.model_validate(d)), "Tool session reopens") == "not recorded"


async def test_d_a_run_records_the_reopen_count_in_its_manifest_and_report(tmp_path: Path) -> None:
    await scenario("selftest", tmp_path)
    run_dir = tmp_path / "pc-selftest"
    tools = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["extra"]["tools"]
    assert tools["session_reopens"] == 0 and tools["session_reopens_by_server"] == {}
    assert _header_row((run_dir / "report.md").read_text(encoding="utf-8"), "Tool session reopens") == "0"


# ------------------------------------------------------------------------------ E: sufficient_evidence


def _state(statuses: list[str], *, cited: list[str] = (), tool_calls: int = 3, rounds: int = 1,
           ok_calls: bool = True) -> Any:
    from types import SimpleNamespace as NS

    from sit_review_agent.models import ToolCallStatus

    status = ToolCallStatus.OK if ok_calls else ToolCallStatus.ERROR
    return NS(plan=NS(questions=[NS(status=s) for s in statuses]),
              findings=[NS(evidence=[NS(evidence_id=e) for e in cited])],
              budget=NS(tool_calls=tool_calls, research_iterations=rounds),
              tool_calls=[NS(status=status) for _ in range(tool_calls)])


def _ledger() -> list[Any]:
    from types import SimpleNamespace as NS

    from sit_review_agent.models import SourceType

    return [NS(evidence_id="EV-001", source_type=SourceType.EXTERNAL),
            NS(evidence_id="EV-002", source_type=SourceType.EXTERNAL),
            NS(evidence_id="EV-003", source_type=SourceType.DOC)]


PARAMS = __import__("types").SimpleNamespace(max_tool_calls=40, max_research_iterations=4)


def _settle(state: Any, detail: str = "model_stop_vote") -> Any:
    from sit_review_agent.models import StopReason, StopReasonCode
    from sit_review_agent.stop_rules import settle_sufficient_evidence

    return settle_sufficient_evidence(StopReason.of(StopReasonCode.SUFFICIENT_EVIDENCE, detail), state, PARAMS,
                                      _ledger())


def test_e_one_of_six_answered_is_not_sufficient_evidence() -> None:
    out = _settle(_state(["answered"] + ["unanswered"] * 5))
    assert out.code.value == "no_marginal_gain"
    assert "sufficient_evidence not met (model_stop_vote): 1 of 6" in out.detail


def test_e_half_rounded_up_is_sufficient() -> None:
    assert _settle(_state(["answered"] * 3 + ["unanswered"] * 3)).code.value == "sufficient_evidence"
    assert _settle(_state(["answered"] * 3 + ["unanswered"] * 2)).code.value == "sufficient_evidence"
    assert _settle(_state(["answered"] * 2 + ["unanswered"] * 3)).code.value != "sufficient_evidence"


def test_e_two_cited_external_entries_are_sufficient_one_is_not() -> None:
    few = ["answered"] + ["unanswered"] * 5
    assert _settle(_state(few, cited=["EV-001", "EV-002"])).code.value == "sufficient_evidence"
    assert _settle(_state(few, cited=["EV-001", "EV-003"])).code.value != "sufficient_evidence"


def test_e_the_fitting_reason_is_the_limit_that_ended_research() -> None:
    few = ["answered"] + ["unanswered"] * 5
    out = _settle(_state(few, tool_calls=40))
    assert (out.code.value, out.detail.split(";")[0]) == ("budget_tool_calls", "max_tool_calls")
    out = _settle(_state(few, rounds=4))
    assert (out.code.value, out.detail.split(";")[0]) == ("budget_tool_calls", "max_research_iterations")
    assert _settle(_state(few, ok_calls=False)).code.value == "tool_failure"


def test_e_a_refused_claim_returns_when_findings_later_cite_two_sources() -> None:
    from sit_review_agent.stop_rules import settle_sufficient_evidence

    few = ["answered"] + ["unanswered"] * 5
    refused = _settle(_state(few), "all_questions_answered")
    assert refused.code.value == "no_marginal_gain"
    again = settle_sufficient_evidence(refused, _state(few, cited=["EV-001", "EV-002"]), PARAMS, _ledger())
    assert again.code.value == "sufficient_evidence" and again.detail.startswith("all_questions_answered; ")
    assert settle_sufficient_evidence(refused, _state(few), PARAMS, _ledger()) is refused


def test_e_other_reasons_pass_unchanged() -> None:
    from sit_review_agent.models import StopReason, StopReasonCode
    from sit_review_agent.stop_rules import settle_sufficient_evidence

    cap = StopReason.of(StopReasonCode.DEADLINE, "stage_limits_s.refine_end")
    assert settle_sufficient_evidence(cap, _state(["unanswered"] * 6), PARAMS, _ledger()) is cap


# ------------------------------------------------------------------------------ G: launch record


def test_g_the_launch_record_carries_no_path_under_the_home_folder(tmp_path: Path, monkeypatch: Any) -> None:
    import hashlib

    from sit_review_agent.ui.launcher import Launcher, LaunchSpec
    from sit_review_agent.ui.rundata import reviewed_pdf
    from test_ui_server import FakePopen

    home = tmp_path / "Users" / "someone"
    monkeypatch.setenv("HOME", str(home))
    runs, repo, elsewhere = home / "runs", home / "repo", home / "Downloads"
    run_dir = runs / "ui-run-1"
    doc = run_dir / "ui" / "input" / "design.pdf"
    for d in (doc.parent, repo, elsewhere):
        d.mkdir(parents=True)
    doc.write_bytes(b"%PDF-1.4 under review")
    v1 = elsewhere / "old.pdf"
    v1.write_bytes(b"%PDF-1.4 old")
    Launcher(repo_root=repo, popen=FakePopen()).start(
        LaunchSpec(run_id="ui-run-1", document=doc, v1=v1, profile="demo"), run_dir)
    text = (run_dir / "ui" / "launch.json").read_text(encoding="utf-8")
    rec = json.loads(text)
    assert str(home) not in text and "someone" not in text
    assert rec["document"] == "ui-run-1/ui/input/design.pdf"
    assert rec["v1"] == "~/Downloads/old.pdf"
    assert rec["args"] == ["review", "~/runs/ui-run-1/ui/input/design.pdf", "--profile", "demo",
                           "--v1", "~/Downloads/old.pdf", "--run-id", "ui-run-1"]
    assert rec["display"] == "dra review ~/runs/ui-run-1/ui/input/design.pdf --profile demo --v1 " \
                             "~/Downloads/old.pdf --run-id ui-run-1"
    # The UI still finds the reviewed PDF from the relative record.
    sha = hashlib.sha256(doc.read_bytes()).hexdigest()
    (run_dir / "manifest.json").write_text(json.dumps({"extra": {"doc": {"sha256_pdf": sha}}}), encoding="utf-8")
    assert reviewed_pdf(run_dir, repo) == doc
