"""Adversarial pass on INV-03..INV-11 (research/robustness/README.md §2): each test constructs the
violation, mostly as a scripted model answer through ``run_review`` on the selftest fixture, and
checks the agent refuses it or records it. Where an earlier test already does this it is named
instead of duplicated:

* INV-06 (recommendation without issue/rationale/evidence/benefit): ``test_ingest_verify_report.py``
  ``test_hydrate_finding_rules`` and ``test_hydration_errors_drop_the_finding``; plus the
  agent-level case here.
* INV-07 (degradations disclosed): ``test_ingest_verify_report.py``
  ``test_assemble_review_discloses_failed_tool_calls_and_caps``, ``test_orchestrator.py``
  ``test_deadline_cap_skips_to_verify_and_is_disclosed``, ``test_fault_injection.py`` INF-03/07/24.
* INV-08 (no secret leaks): ``test_research_phase.py`` ``test_failed_and_refused_calls_go_back_as_is_error``
  (canary in a tool call blocked, absent from tools.jsonl), ``test_tool_gateways.py``
  ``test_mcp_401_twice_disables_every_server_and_never_leaks_the_key``,
  ``test_integration_seams.py`` ``test_1c_*`` (llm.jsonl), ``test_e2e_synthetic.py`` (whole run dir).
* INV-10 registry change after freeze: ``test_llm_phases.py``
  ``test_understand_writes_intent_registry_and_freezes`` (``RegistryFrozenError``) and
  ``test_invariants.py`` ``test_inv10_registry_hash_constant``.
* Effort change within a conversation (ADR-002) at the gateway: ``test_anthropic_gateway.py``
  ``test_effort_change_rejected``, ``test_claude_code_gateway.py``
  ``test_effort_change_within_conversation``, ``test_state_and_gateways.py``
  ``test_fake_gateway_typed_errors_and_effort_guard``; the run-level consequence is here.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import sit_review_agent.errors as errors_mod
from sit_review_agent.cli import app
from sit_review_agent.clock import FakeClock
from sit_review_agent.config import EffectiveConfig
from sit_review_agent.errors import AgentError, ExitCode
from sit_review_agent.invariants import check_all, check_INV_03, check_INV_04
from sit_review_agent.llm.gateway import FakeGateway, FakeResponse, LLMRequest, LLMResult
from sit_review_agent.orchestrator import RunRequest, run_review
from sit_review_agent.phases import default_phases
from sit_review_agent.progress import NullProgress
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.selftest import (
    FIXTURE_DIR,
    assess_answer,
    fixture_script,
    request_shard,
    selftest_config,
    shard_answer,
    verdict_answer,
)
from sit_review_agent.states import PhaseName

PDF = FIXTURE_DIR / "design.pages.txt"
Mutation = Callable[[dict[str, Any]], None]


class _Gateway(FakeGateway):
    """The selftest fixture script, with ``mutate`` applied to the whole assessment (the model's
    adversarial output; each shard then answers its own part of it, IDs as the merge gives them) and
    ``report`` replacing the verdict answer when given."""

    def __init__(self, rd: RunDir, clock: Any, criteria: list[str], mutate: Mutation | None,
                 report: dict[str, Any] | None, shards: list[list[str]]) -> None:
        script = fixture_script(criteria, shards)
        if report is not None:
            script["report"] = [FakeResponse(parsed=report)] * 2
        super().__init__(script, run_dir=rd, clock=clock)
        self.rd, self.mutate, self.criteria, self.shards = rd, mutate, criteria, shards

    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        q = self.script.get(str(request.phase))
        if q and callable(q[0]):
            resp = q[0](JsonlWriter(self.rd.ledger_journal).read(), request)
            if request.phase is PhaseName.ASSESS and self.mutate is not None:
                whole = assess_answer(self.criteria)
                self.mutate(whole)
                group = request_shard(request, self.shards)
                resp = FakeResponse(parsed=whole if group is None else shard_answer(whole, group))
            q[0] = resp
        return await super().call(request)


def config(tmp_path: Path, *, tools: bool = True) -> EffectiveConfig:
    """selftest config with refine off (assess's answer is what reaches verify)."""
    cfg = selftest_config(tmp_path / "runs")
    phases = cfg.agent.phases.model_copy(update={"refine": False})
    cfg = cfg.model_copy(update={"agent": cfg.agent.model_copy(update={"phases": phases})})
    if not tools:
        servers = [s.model_copy(update={"enabled": False}) for s in cfg.tools.servers]
        cfg = cfg.model_copy(update={"tools": cfg.tools.model_copy(update={"servers": servers})})
    return cfg


async def run(tmp_path: Path, mutate: Mutation | None = None, *, report: dict[str, Any] | None = None,
              tools: bool = True, phases: dict[PhaseName, Any] | None = None, run_id: str = "adv") -> Any:
    cfg = config(tmp_path, tools=tools)
    out = await run_review(
        RunRequest(pdf=PDF, config=cfg, run_id=run_id), phases=phases,
        llm_factory=lambda rd, clock, progress: _Gateway(
            rd, clock, cfg.criteria.ids(), mutate, report,
            [list(g.criteria) for g in cfg.agent.assess.shards_for(cfg.criteria.ids())]),
        clock=FakeClock(), progress=NullProgress())
    return out, RunDir(out.run_dir)


def finding(parsed: dict[str, Any], fid: str) -> dict[str, Any]:
    return next(f for f in parsed["findings"] if f["id"] == fid)


def load(rd: RunDir) -> dict[str, Any]:
    assert rd.report_json.is_file(), rd.failure.read_text(encoding="utf-8") if rd.failure.exists() else "no report"
    report = json.loads(rd.report_json.read_text(encoding="utf-8"))
    assert [(r.inv_id, r.problems) for r in check_all(report, rd.root) if not r.passed] == []
    return report


def degradation_events(report: dict[str, Any]) -> str:
    return json.dumps([d["event"] for d in report["research_log"]["degradations"]])


# ============================================================================== INV-03


async def test_inv03_non_refinement_finding_left_out_of_unresolved_is_added(tmp_path: Path) -> None:
    """The report answer is the verdict only, so it lists no unresolved item for the needs_testing
    finding FND-002; the assembly adds it in code (lab §2.4), and the checker rejects a Review
    without it."""
    out, rd = await run(tmp_path, report=verdict_answer(None))
    report = load(rd)
    assert "FND-002" in {x for u in report["unresolved"] for x in u["finding_ids"]}
    broken = copy.deepcopy(report)
    broken["unresolved"] = [u for u in broken["unresolved"] if "FND-002" not in u["finding_ids"]]
    assert any("FND-002" in p and "unresolved" in p for p in check_INV_03(broken, rd.root).problems)


# ============================================================================== INV-04


async def test_inv04_quote_under_eight_words_is_not_reported_as_a_finding(tmp_path: Path) -> None:
    def short(p: dict[str, Any]) -> None:
        finding(p, "FND-001")["doc_anchors"][0]["quote"] = "Accessibility is mostly fine here"     # 5 words, invented

    out, rd = await run(tmp_path, short)
    report = load(rd)
    assert "Accessibility is verified, not just promised" not in [f["title"] for f in report["findings"]]
    assert any(u["text"].startswith("Unverified (strength)") for u in report["unresolved"])
    rows = json.loads(rd.anchors.read_text(encoding="utf-8"))["rows"]
    assert any(r["owner_id"] == "FND-001" and "quote_too_short" in r["reasons"] for r in rows)
    assert "no anchor that could be verified" in degradation_events(report)
    broken = copy.deepcopy(report)
    broken["findings"][0]["doc_anchors"][0]["quote"] = "Section 6.2 assumes no limit"
    res = check_INV_04(broken, rd.root)
    assert not res.passed and any("quote_too_short" in p for p in res.problems)


# ============================================================================== INV-05


async def test_inv05_model_written_url_and_unknown_evidence_id(tmp_path: Path) -> None:
    """BEH-04: a URL the model wrote and an EV- ID that is not in the ledger."""
    def fabricate(p: dict[str, Any]) -> None:
        f = finding(p, "FND-004")
        f["statement"] += " See https://made-up.example/paper for the provider's real quota."
        f["evidence"].append({"evidence_id": "EV-999", "source_type": "external", "quote": "made up",
                              "supports_claim": True, "derived_from": []})
        f["recommendation"]["supporting_evidence_ids"].append("EV-999")

    out, rd = await run(tmp_path, fabricate)
    report = load(rd)
    for name in ("report.json", "report.md"):
        assert "made-up.example" not in (rd.root / name).read_text(encoding="utf-8")
    f1 = report["findings"][0]
    assert "[link removed: not in the evidence register]" in f1["statement"]
    ledger = {e["evidence_id"] for e in report["evidence_ledger"]}
    assert "EV-999" not in json.dumps(report["findings"]) and {e["evidence_id"] for e in f1["evidence"]} <= ledger
    deg = next(d for d in report["research_log"]["degradations"] if "not in the evidence register" in d["event"])
    assert any(deg["id"] in lim["degradation_ids"] for lim in report["limitations"])          # disclosed


async def test_inv05_doc_only_run_cannot_claim_external_evidence(tmp_path: Path) -> None:
    """--no-tools: a shard's answer cites a new item as external evidence (there is no such entry: no
    tool ran, and a shard is shown no register). The citation must be dropped, never re-pointed at a
    doc entry that the evidence resolver creates under the same ID in the same pass (defect fixed here)."""
    def external_claims(p: dict[str, Any]) -> None:
        f = finding(p, "FND-002")
        f["evidence"].append({"evidence_id": "NEW-9", "source_type": "external", "quote": "A vendor page says so.",
                              "supports_claim": True, "derived_from": []})

    out, rd = await run(tmp_path, external_claims, tools=False)
    report = load(rd)
    assert all(e["source_type"] != "external" for e in report["evidence_ledger"])
    for f in report["findings"]:
        for e in f["evidence"]:
            assert e["source_type"] != "external"
            entry = next(x for x in report["evidence_ledger"] if x["evidence_id"] == e["evidence_id"])
            assert e["quote"] is None or e["quote"] in (entry["excerpt"] or "")
    assert "No external research was possible" in degradation_events(report)
    assert "A vendor page says so." not in json.dumps(report["findings"])   # the fabricated external quote
    # The invented citation was not attached to a doc entry created for a finding's anchor: every doc
    # citation of a finding is one of that finding's own passages.
    ledger = {e["evidence_id"]: e for e in report["evidence_ledger"]}
    for f in report["findings"]:
        own = {" ".join(a["quote"].split()) for a in f["doc_anchors"]}
        for e in f["evidence"]:
            if e["source_type"] == "doc":
                assert " ".join(ledger[e["evidence_id"]]["excerpt"].split()) in own, (f["id"], e["evidence_id"])


# ============================================================================== INV-06


async def test_inv06_recommendation_without_a_real_issue_is_dropped_and_disclosed(tmp_path: Path) -> None:
    def thin(p: dict[str, Any]) -> None:
        finding(p, "FND-002")["recommendation"]["issue"] = "untested"

    out, rd = await run(tmp_path, thin)
    report = load(rd)
    assert "Peak-day reminder volume is not tested" not in [f["title"] for f in report["findings"]]
    assert "shorter than" in degradation_events(report)


# ============================================================================== INV-09


async def test_inv09_incomplete_manifest_is_refused_not_written(tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    import sit_review_agent.phases.report as report_mod

    real = report_mod.build_manifest

    def no_code(*a: Any, **k: Any) -> Any:
        m = real(*a, **k)
        return m.model_copy(update={"extra": {**m.extra, "code": {}}})

    monkeypatch.setattr(report_mod, "build_manifest", no_code)
    out, rd = await run(tmp_path)
    assert out.exit_code == int(ExitCode.STAGE_CRASH) and not rd.report_json.exists()
    assert (rd.root / "report.invalid.json").is_file()
    assert "INV-09" in rd.failure.read_text(encoding="utf-8")


# ============================================================================== INV-10


async def test_inv10_unsupported_challenge_and_unknown_registry_id(tmp_path: Path) -> None:
    """FND-004 challenges approved decision AD-001 with one evidence item (needs >= 2): not
    reported, disclosed. FND-002 cites AD-999, which is not in the registry: the reference is removed."""
    def challenge(p: dict[str, Any]) -> None:
        finding(p, "FND-004")["affected_decisions"] = [{"registry_id": "AD-001", "relation": "challenges",
                                                         "justification": "Front end should not use D-3."}]
        finding(p, "FND-002")["affected_decisions"] = [{"registry_id": "AD-999", "relation": "refines",
                                                         "justification": "Invented decision."}]

    out, rd = await run(tmp_path, challenge)
    report = load(rd)
    titles = [f["title"] for f in report["findings"]]
    assert "E-mail plan cannot send peak-day reminders" not in titles
    assert ">= 2 evidence items" in degradation_events(report)
    f3 = next(f for f in report["findings"] if f["title"] == "Peak-day reminder volume is not tested")
    assert f3["affected_decisions"] == []
    state = json.loads(rd.state.read_text(encoding="utf-8"))
    hist = [h for m in state["finding_meta"].values() for h in m["history"]]
    assert any("affected_decisions" in h["changed_fields"] for h in hist)


# ============================================================================== ADR-002 effort


class _EffortFlip:
    """A phase that changes effort inside one conversation (a bug ADR-002 forbids)."""

    name = PhaseName.UNDERSTAND

    async def run(self, ctx: Any) -> Any:
        for effort in ("high", "medium"):
            await ctx.llm.call(LLMRequest(phase=self.name, conversation_id="understand-0", system="s",
                                          messages=[{"role": "user", "content": "x"}], effort=effort,
                                          max_tokens=10))
        return ctx                                                       # pragma: no cover


async def test_effort_change_mid_conversation_stops_the_run_with_a_record(tmp_path: Path) -> None:
    phases = {**default_phases(), PhaseName.UNDERSTAND: _EffortFlip()}
    out, rd = await run(tmp_path, phases=phases)
    assert out.exit_code == int(ExitCode.STAGE_CRASH)
    rec = json.loads(rd.failure.read_text(encoding="utf-8"))
    assert rec["error"] == "EffortChangedError" and rec["phase"] == "understand"
    # the second call never left (plan and the assess shards run beside understand in stage 1)
    assert [e["conversation_id"] for e in JsonlWriter(rd.llm_log).read()].count("understand-0") == 1


# ============================================================================== INV-11


def _subclasses(cls: type) -> list[type]:
    out = []
    for sub in cls.__subclasses__():
        out += [sub, *_subclasses(sub)]
    return out


AGENT_ERRORS = sorted({c for c in _subclasses(AgentError) if c.__module__ == errors_mod.__name__},
                      key=lambda c: c.__name__)


def _instance(cls: type) -> AgentError:
    if cls is errors_mod.ResumeDriftError:
        return cls(["effective_config"])
    if cls is errors_mod.StageCrash:
        return cls("assess", RuntimeError("inner"))
    if cls is errors_mod.AssessShardsFailed:
        return cls([(1, "a", errors_mod.LLMOverloadedError("529", phase="assess"))])
    if cls is errors_mod.LLMTruncatedError:
        return cls("cut", max_tokens=10)
    if cls is errors_mod.LLMRateLimitError:
        return cls("429", retry_after_s=None)
    if cls is errors_mod.LLMRefusalError:
        return cls("declined", category=None)
    if cls is errors_mod.ReplayMiss:
        return cls("0" * 64, "mcp-internet-search", "search")
    return cls(f"planted {cls.__name__}")


class _Raise:
    name = PhaseName.INGEST

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    async def run(self, ctx: Any) -> Any:
        raise self.exc


@pytest.mark.parametrize("cls", AGENT_ERRORS, ids=lambda c: c.__name__)
async def test_inv11_every_agent_error_maps_to_its_exit_code(tmp_path: Path, cls: type) -> None:
    exc = _instance(cls)
    out, rd = await run(tmp_path, phases={**default_phases(), PhaseName.INGEST: _Raise(exc)})
    assert out.exit_code == int(exc.exit_code)
    rec = json.loads(rd.failure.read_text(encoding="utf-8"))
    assert rec["exit_code"] == int(exc.exit_code) and rec["error"] == cls.__name__


async def test_inv11_any_other_exception_is_exit_4_with_failure_json(tmp_path: Path) -> None:
    out, rd = await run(tmp_path, phases={**default_phases(), PhaseName.INGEST: _Raise(ZeroDivisionError("bug"))})
    assert out.exit_code == int(ExitCode.STAGE_CRASH)
    rec = json.loads(rd.failure.read_text(encoding="utf-8"))
    assert rec["error"] == "StageCrash" and "ZeroDivisionError" in rec["cause"]


def test_inv11_no_traceback_reaches_the_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Through the public CLI: a bug inside a phase, and a bug before any run directory exists."""
    import sit_review_agent.phases as phases_mod

    real = phases_mod.default_phases
    monkeypatch.setattr(phases_mod, "default_phases",
                        lambda: {**real(), PhaseName.INGEST: _Raise(KeyError("planted"))})
    args = ["run", str(PDF), "--transport", "fake", "--replay", str(FIXTURE_DIR / "cassettes"),
            "--disable-tool", "mcp-research-information", "--run-id", "cli-inv11"]
    cfg_dir = tmp_path / "config"
    import shutil

    from sit_review_agent.paths import config_dir

    shutil.copytree(config_dir(), cfg_dir)
    agent = cfg_dir / "agent.yaml"
    agent.write_text(agent.read_text(encoding="utf-8").replace("run_root: runs", f"run_root: {tmp_path / 'runs'}"),
                     encoding="utf-8")
    res = CliRunner().invoke(app, [*args, "--config", str(cfg_dir)])
    assert res.exit_code == 4 and "Traceback" not in res.output
    assert json.loads((tmp_path / "runs" / "cli-inv11" / "failure.json").read_text(encoding="utf-8"))["exit_code"] == 4
    import sit_review_agent.config as config_mod

    def broken(*a: Any, **k: Any) -> Any:
        raise RuntimeError("config loader bug")

    monkeypatch.setattr(config_mod, "load_config", broken)
    import sit_review_agent.cli as cli_mod

    monkeypatch.setattr(cli_mod, "load_config", broken)
    res = CliRunner().invoke(app, [*args, "--config", str(cfg_dir)])
    assert res.exit_code == 4 and "Traceback" not in res.output and "internal error" in res.output
