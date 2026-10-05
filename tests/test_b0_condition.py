"""Condition B0, the single-call baseline (``eval/prereg.yaml`` ``conditions.tier_A``):

    Single call, no tools, whole document plus the same task prompt and output schema (MR §4); the single
    call is the assess brief with all criteria in one call (with FULL's assess split into concurrent
    shards, ADR-011; deviations entry 11).

Offline, on ``eval/synthetic/payments_orchestration/design_v1.pdf`` (the harness tests read the same
item) with a ``FakeGateway`` scripted for ONE assess call. What it pins down:

* ``--condition B0`` reaches ``RunRequest`` and ``ConfigOverrides`` from the CLI and implies ``--no-tools``;
* the run makes exactly one model call (the assess call over every criterion, briefed by
  ``prompts/assess_single.md``): understand, plan, research and refine do not run, the report makes no
  verdict call (the verdict is derived by rule), verify makes no repair call;
* ``report.json`` validates against the finding schema and INV-03..INV-10 pass; the manifest says
  ``condition: "B0"`` and names the single-call mode in ``extra.model``;
* the harness scores the run with its fake judge (plumbing only: hashes, not judgements) and
  ``sit-eval aggregate --compare FULL --compare B0`` over a FULL run and the B0 run produces the comparison;
* the single call is bounded by the run deadline, not by the stage 1 limit;
* a FULL run is unchanged: its manifest says ``condition: "FULL"`` (the harness's default label).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import sit_review_agent.progress  # noqa: F401 - bind ConsoleProgress's default stream before CliRunner swaps it
from sit_review_agent.clock import FakeClock
from sit_review_agent.config import ConfigOverrides, EffectiveConfig, Transport, load_config
from sit_review_agent.invariants import check_all, spec_validator
from sit_review_agent.llm.gateway import FakeGateway, FakeResponse
from sit_review_agent.llm.runtime import RunDeadline, build_runtime
from sit_review_agent.orchestrator import RunRequest, run_review
from sit_review_agent.paths import repo_root
from sit_review_agent.phases.assess import B0_PROMPT, B0_SHARD_NAME
from sit_review_agent.progress import NullProgress
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.states import PhaseName

PDF = repo_root() / "eval" / "synthetic" / "payments_orchestration" / "design_v1.pdf"
KEY = repo_root() / "eval" / "synthetic" / "payments_orchestration" / "answer_key.canonical.json"
FULL_RUN = repo_root() / "docs" / "live_runs" / "live_cc_opus_payments_v1"      # the harness tests' FULL run
DOC = "DOC-design_v1"
CANARY = "CANARY-MCP-7f3a9c0e2e"

# Verbatim passages of the canonical text of design_v1.pdf (page, section as pdfplumber reads them).
Q_P5 = ("P5 The ledger is append-only. Corrections are new journals that reverse or adjust; nothing in the ledger is "
        "updated or deleted.")                                                                             # p4 s3
Q_RETRY = ("The Retry Engine maintains a per-card (PAN fingerprint) and per-merchant reattempt counter over a "
           "rolling 30-day")                                                                                # p9 s11.3
Q_FRAUD = "The Fraud Hook obtains the PAN through the Vault's"                                              # p11 s13
Q_LEDGER = "The ledger is a set of accounts and an append-only table of journals"                           # p11 s14.1
Q_WEBHOOK = "Webhooks At-least-once, HMAC-SHA256 timestamped signatures, 72-hour bounded retry, DLQ + replay"  # p19 s24

CRITERIA = ["design_intent", "fitness_for_objectives", "requirement_completeness", "internal_consistency",
            "claims_and_external_constraints", "security_and_privacy", "scalability_and_failure_modes",
            "assumptions_and_dependencies", "verifiability", "decision_preservation", "operability_and_governance"]


def anchor(section: str, page: int, quote: str) -> dict[str, Any]:
    return {"doc_id": DOC, "section_ref": section, "requirement_ids": [], "quote": quote, "page": page}


def rec(issue: str, change: str, support: list[str]) -> dict[str, Any]:
    return {"issue": issue, "rationale": "The design states a rule in one place that another section does not honour.",
            "expected_benefit": "Builders get one unambiguous rule and the reviewers one decision to make.",
            "change_summary": change, "objective_refs": ["Section 1: account for every movement of money"],
            "supporting_evidence_ids": support, "verification": None}


def finding(fid: str, rank: int, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": fid, "rank": rank, "kind": "risk", "category": "security_privacy_gap", "severity": "high",
        "confidence": 0.8, "disposition": "refinement_now", "secondary_dispositions": [], "title": "",
        "statement": "", "doc_anchors": [], "evidence": [], "recommendation": None, "no_change_rationale": None,
        "next_step": None, "affected_decisions": [], "acknowledged_in_doc": False, "tags": [], "reassessment": None,
        "criterion_ids": []}
    base.update(kw)
    return base


def doc_cite(eid: str, quote: str) -> dict[str, Any]:
    return {"evidence_id": eid, "source_type": "doc", "quote": quote, "supports_claim": True, "derived_from": []}


def assess_answer() -> FakeResponse:
    """The one scripted answer: four findings across five criteria, one sound area, a row per criterion."""
    findings = [
        finding("F1", 1, title="The fraud hook reads the raw PAN from the vault",
                statement="Section 13 has the Fraud Hook obtain the PAN through the Vault, which widens the "
                          "cardholder-data environment beyond the vault and the card adapter that section 12 scopes.",
                doc_anchors=[anchor("13", 11, Q_FRAUD)], evidence=[doc_cite("NEW-1", Q_FRAUD)],
                recommendation=rec("The fraud hook handles the PAN outside the scoped CDE.",
                                   "Score on the PAN fingerprint or a network token in section 13, or add the hook "
                                   "to the CDE scope table of section 12.", ["NEW-1"]),
                tags=["pci"], criterion_ids=["security_and_privacy"]),
        finding("F2", 2, kind="ambiguity", category="ambiguous_requirement", severity="medium",
                title="The rolling 30-day reattempt counter has no stated store",
                statement="Section 11.3 keeps a per-card and per-merchant counter over a rolling 30-day window "
                          "but names no store, retention or reset rule for it.",
                doc_anchors=[anchor("11.3", 9, Q_RETRY)],
                recommendation=rec("A rolling counter without a named store cannot be built or sized.",
                                   "Name the counter's store and its expiry in section 11.", []),
                criterion_ids=["requirement_completeness", "scalability_and_failure_modes"]),
        finding("F3", 3, kind="strength", category=None, severity=None, disposition="no_change",
                title="The ledger is append-only by principle and by model",
                statement="Principle P5 and the ledger model of section 14 agree that journals are never updated "
                          "or deleted.",
                doc_anchors=[anchor("3", 4, Q_P5), anchor("14.1", 11, Q_LEDGER)],
                no_change_rationale="An append-only journal with reversing corrections is the right foundation for "
                                    "the reconciliation the design promises.",
                criterion_ids=["fitness_for_objectives"]),
        finding("F4", 4, kind="validation_need", category="acceptance_criterion_cannot_validate", severity="medium",
                disposition="needs_testing", title="The 72-hour webhook retry bound is not exercised",
                statement="The confirmed decisions bound webhook retries at 72 hours, but no acceptance test "
                          "drives a merchant endpoint down for that long.",
                doc_anchors=[anchor("24", 19, Q_WEBHOOK)], evidence=[doc_cite("NEW-2", Q_WEBHOOK)],
                recommendation=rec("The retry bound is stated but not demonstrated.",
                                   "Add a long-outage webhook test to section 26 with the dead-letter outcome checked.",
                                   ["NEW-2"]),
                next_step={"owner": "Payments QA lead", "action": "Schedule a 72-hour webhook outage test."},
                criterion_ids=["verifiability"]),
    ]
    cited = {c for f in findings for c in f["criterion_ids"]}
    coverage = [{"criterion_id": c, "outcome": "findings" if c in cited else "no_issue", "finding_ids": [],
                 "note": "b0 test"} for c in CRITERIA]
    areas = [{"section_refs": ["14"], "why_sound": "The ledger is append-only with reversing corrections.",
              "doc_anchors": [anchor("14.1", 11, Q_LEDGER)], "evidence_ids": [], "related_finding_ids": ["F3"]}]
    return FakeResponse(parsed={"findings": findings, "sound_areas": areas, "coverage": coverage})


def config(tmp_path: Path, **overrides: Any) -> EffectiveConfig:
    cfg = load_config(overrides=ConfigOverrides(transport=Transport.FAKE, **overrides))
    agent = cfg.agent.model_copy(update={"run_root": str(tmp_path / "runs"), "fault_schedule": None,
                                         "plan_approval": False})
    return cfg.model_copy(update={"agent": agent})


def factory(script: dict[str, list[FakeResponse]]) -> Any:
    return lambda rd, clock, progress: FakeGateway(script, run_dir=rd, clock=clock)


async def run_b0(tmp_path: Path, run_id: str = "b0-a") -> tuple[RunDir, NullProgress]:
    cfg = config(tmp_path, condition="B0")
    assert cfg.tools.enabled_servers() == []                                   # B0 implies --no-tools
    progress = NullProgress()
    out = await run_review(RunRequest(pdf=PDF, config=cfg, run_id=run_id, condition="B0"),
                           llm_factory=factory({"assess": [assess_answer()]}), clock=FakeClock(),
                           progress=progress)
    rd = RunDir(out.run_dir)
    assert out.exit_code == 0, rd.failure.read_text(encoding="utf-8") if rd.failure.exists() else ""
    return rd, progress


@pytest.fixture(scope="module")
def b0_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[RunDir, NullProgress]:
    import asyncio

    return asyncio.run(run_b0(tmp_path_factory.mktemp("b0")))


def test_b0_makes_exactly_one_model_call_and_a_valid_report(b0_run: tuple[RunDir, NullProgress],
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIT_MCP_API_KEY", CANARY)
    rd, progress = b0_run
    report = json.loads(rd.report_json.read_text(encoding="utf-8"))
    assert [f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
            for e in spec_validator("Review").iter_errors(report)] == []
    results = check_all(report, rd.root, canaries=[CANARY])
    assert [(r.inv_id, r.problems) for r in results if not r.passed] == []

    # exactly one model call: the assess call over every criterion, from the single-call brief
    calls = JsonlWriter(rd.llm_log).read()
    assert [c["phase"] for c in calls] == ["assess"]
    assert calls[0]["conversation_id"] == "assess-0-s1"
    state = json.loads(rd.state.read_text(encoding="utf-8"))
    assert state["condition"] == "B0"
    assert state["plan"] is None and state["intent_summary"] is None and state["registry"] == []
    assert [p for p in state["completed_phases"]] == ["ingest", "assess", "verify", "report"]
    meta = next(iter(state["finding_meta"].values()))
    assert meta["created_phase"] == "assess" and meta["criterion_ids"]
    shards = sorted((rd.root / "shards").glob("*.json"))
    assert [p.name for p in shards] == [f"01-{B0_SHARD_NAME}.json"]
    stored = json.loads(shards[0].read_text(encoding="utf-8"))["result"]
    assert stored["criteria"] == CRITERIA and stored["outcome"] == "done"

    # the findings reached the report through the same verify and report path as FULL
    ids = [f["id"] for f in report["findings"]]
    assert ids == ["FND-001", "FND-002", "FND-004", "FND-003"]     # IDs in the model's rank order; ranked by
    assert [f["rank"] for f in report["findings"]] == [1, 2, 3, 4]  # severity in the report, the strength last
    assert {f["provenance"]["phase"] for f in report["findings"]} == {"assess"}
    assert report["verdict"]["label"] == "fit_with_conditions"              # by rule: open findings, none critical
    assert "condition B0" in report["verdict"]["rationale"]
    assert [c["criterion_id"] for c in state["coverage"]] == CRITERIA           # one row per criterion
    assert {c["outcome"] for c in state["coverage"]} == {"findings", "no_issue"}
    # the one disclosure is inherent to the condition (no understand phase, so no design-intent summary)
    assert report["research_log"]["tool_calls"] == []
    assert [d["event"] for d in report["research_log"]["degradations"]] == [
        "condition B0: no design-intent summary (the single-call baseline runs no understand phase)"]
    assert len(report["limitations"]) == 1 and report["unresolved"][0]["text"].startswith("FND-004")
    assert rd.report_md.is_file() and "FND-001" in rd.report_md.read_text(encoding="utf-8")

    # the manifest names the condition and the single-call mode
    manifest = json.loads(rd.manifest.read_text(encoding="utf-8"))
    assert manifest["condition"] == "B0"
    assert manifest["extra"]["model"]["assess_mode"].startswith("single_call")
    assert manifest["extra"]["model"]["assess_shards"] == 1
    assert manifest["outcome"] == "completed_degraded"               # the inherent disclosure above
    assert manifest["review_config"]["criteria"] == CRITERIA

    # progress: the skipped phases are announced as the condition's, the one assess call is bounded by the deadline
    events = progress.records
    skipped = {e.phase: e.fields.get("reason") for e in events if e.event == "phase_skipped"}
    assert skipped == {"understand": "condition B0", "plan": "condition B0", "research": "condition B0",
                       "refine": "condition B0"}
    started = next(e for e in events if e.event == "run_started")
    assert started.fields["shards"] == [{"index": 1, "name": B0_SHARD_NAME, "criteria": CRITERIA}]
    assert any(e.event == "verdict_by_rule" for e in events)
    assert not any(e.event == "anchor_repair" for e in events)          # every anchor verified: no repair needed


def test_b0_verdict_rationale_says_the_rule_verdict_is_by_design(b0_run: tuple[RunDir, NullProgress]) -> None:
    """B0 has no verdict call by design, so the rationale must not read as a missing model verdict."""
    rd, _ = b0_run
    rationale = json.loads(rd.report_json.read_text(encoding="utf-8"))["verdict"]["rationale"]
    assert "by design there is no separate verdict call" in rationale
    assert "no model verdict was available" not in rationale
    assert "See the limitations" not in rationale


def test_b0_brief_is_the_single_call_prompt(b0_run: tuple[RunDir, NullProgress]) -> None:
    """The one call rendered ``prompts/assess_single.md`` (its hash is the finding's prompt hash)."""
    from sit_review_agent.prompts import PromptBundle

    rd, _ = b0_run
    state = json.loads(rd.state.read_text(encoding="utf-8"))
    hashes = {m["prompt_hash"] for m in state["finding_meta"].values()}
    assert len(hashes) == 1
    bundle = PromptBundle.load()
    assert B0_PROMPT in bundle.files
    text = (bundle.root / B0_PROMPT).read_text(encoding="utf-8")
    assert "You are the only reviewer" in text and "shard" not in text.split("#}", 1)[1].lower()
    assert B0_PROMPT in (bundle.root / "PROMPTS.lock").read_text(encoding="utf-8")


def test_b0_call_is_bounded_by_the_run_deadline_not_the_stage_limit() -> None:
    cfg = load_config(overrides=ConfigOverrides(transport=Transport.FAKE, condition="B0", profile="demo"))
    clock = {"t": 0.0}
    full = build_runtime(cfg, lambda: clock["t"]).deadline
    b0 = build_runtime(cfg, lambda: clock["t"], deadline_bound=frozenset({PhaseName.ASSESS})).deadline
    assert isinstance(full, RunDeadline) and full.stage_limits is not None
    limits = full.stage_limits
    deadline = float(cfg.stop_rules.deadline_seconds)
    reserve = float(cfg.stop_rules.report_reserve_seconds)
    assert full.phase_budget(PhaseName.ASSESS) == limits["stage_1_end"]
    assert b0.phase_budget(PhaseName.ASSESS) == deadline - reserve > limits["stage_1_end"]
    assert "run deadline" in b0.describe_bound(PhaseName.ASSESS) and "stage 1 limit" in full.describe_bound(
        PhaseName.ASSESS)
    # the other phases keep their stage limits under B0
    assert b0.phase_budget(PhaseName.REPORT) == full.phase_budget(PhaseName.REPORT)
    clock["t"] = limits["stage_1_end"] + 1.0
    assert full.phase_budget(PhaseName.ASSESS) < 0 < b0.phase_budget(PhaseName.ASSESS)


def test_cli_condition_option_reaches_the_request(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import sit_review_agent.orchestrator as orch
    from sit_review_agent.cli import app

    seen: dict[str, Any] = {}

    async def fake_run_review(request: Any) -> Any:
        seen["request"] = request

        class Out:
            run_dir, exit_code, report_md = tmp_path, 0, None

        return Out()

    monkeypatch.setattr(orch, "run_review", fake_run_review)
    res = CliRunner().invoke(app, ["review", str(PDF), "--transport", "fake", "--condition", "B0", "--no-tools",
                                   "--run-id", "x"])
    assert res.exit_code == 0, res.output
    req = seen["request"]
    assert req.condition == "B0" and req.config.cli_args["condition"] == "B0"
    assert req.config.tools.enabled_servers() == []
    # the default is FULL, which the config does not record (exclude_defaults) and the manifest labels
    res = CliRunner().invoke(app, ["run", str(PDF), "--transport", "fake", "--no-tools", "--run-id", "y"])
    assert res.exit_code == 0, res.output
    assert seen["request"].condition == "FULL" and "condition" not in seen["request"].config.cli_args
    res = CliRunner().invoke(app, ["run", str(PDF), "--transport", "fake", "--condition", "B7"])
    assert res.exit_code == 2 and "expected FULL | B0" in res.output
    res = CliRunner().invoke(app, ["run", str(PDF), "--transport", "fake", "--condition", "B0", "--plan-only"])
    assert res.exit_code == 2 and "--plan-only" in res.output


# ------------------------------------------------------------------------------- the harness on a B0 run


def _score(run: Path, out: Path, *extra: str) -> dict[str, Any]:
    from sit_eval.cli import app as eval_app

    res = CliRunner().invoke(eval_app, ["score", str(run), "--key", str(KEY), "--judge", "fake", "--out", str(out),
                                        "--exploratory", "--no-grounding-judges", *extra])
    assert res.exit_code == 0, res.output
    return json.loads((out / "scores.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(not FULL_RUN.is_dir(), reason="the FULL run of the harness tests is not checked out")
def test_harness_scores_a_b0_run_and_compares_it_with_full(b0_run: tuple[RunDir, NullProgress],
                                                           tmp_path: Path) -> None:
    """PLUMBING ONLY: the fake judge answers with hashes, not judgements; nothing here is a score."""
    from sit_eval.cli import app as eval_app
    from sit_eval.scoring import validate_scores

    rd, _ = b0_run
    b0 = _score(rd.root, tmp_path / "b0")
    assert validate_scores(b0) == []
    assert b0["inputs"]["condition"] == "B0"                              # read from the run's manifest
    assert b0["inputs"]["doc_sha256_text_matches_review"] is True
    assert len(b0["findings"]) == 3 and b0["metrics"]["recall"]["value"] is not None   # the strength is not scored
    full = _score(FULL_RUN, tmp_path / "full", "--condition", "FULL")
    assert full["inputs"]["condition"] == "FULL"

    res = CliRunner().invoke(eval_app, ["aggregate", str(tmp_path / "full" / "scores.json"),
                                        str(tmp_path / "b0" / "scores.json"), "--compare", "FULL", "--compare", "B0",
                                        "--bootstrap-b", "100", "--exploratory", "--out", str(tmp_path / "agg.json")])
    assert res.exit_code == 0, res.output
    agg = json.loads((tmp_path / "agg.json").read_text(encoding="utf-8"))
    assert set(agg["conditions"]) == {"FULL", "B0"}
    comparison = agg["comparison"]
    assert (comparison["a"], comparison["b"]) == ("FULL", "B0") and comparison["documents"]
    assert "paired_bootstrap" in comparison["recall"] and "sign_flip" in comparison["recall"]


# ------------------------------------------------------------------------------- FULL is unchanged


async def test_full_manifest_is_labelled_full(tmp_path: Path) -> None:
    """A FULL run's manifest carries the condition label the harness compares on."""
    import test_e2e_synthetic as synth

    cfg = synth.config(tmp_path)
    out = await run_review(RunRequest(pdf=synth.PDF, config=cfg, run_id="full-a"), llm_factory=synth.factory(cfg),
                           clock=FakeClock(), progress=NullProgress())
    rd = RunDir(out.run_dir)
    assert out.exit_code == 0
    manifest = json.loads(rd.manifest.read_text(encoding="utf-8"))
    assert manifest["condition"] == "FULL" and "assess_mode" not in manifest["extra"]["model"]
    assert json.loads(rd.state.read_text(encoding="utf-8"))["condition"] == "FULL"
