"""End to end on a real PDF through the public ``run_review`` / ``resume_run`` entry points, with
every real phase (A's understand/plan/assess/refine, B's research, C's ingest/verify/report) and a
``FakeGateway`` whose answers were written against ``eval/synthetic/research_lakehouse/design_v1.pdf``
(S-dev tier, developers may read it; ADR-004). Doc-only (``--no-tools``), offline, no key.

What it pins down (integration verifier, cross-workstream seams):

* the report validates against ``spec/finding.schema.json`` and INV-03..INV-10 pass (INV-08 with a
  canary key in the environment);
* the plan's question IDs are renumbered ``RQ-001..`` whatever the model wrote (seam 1g), and a
  ``--no-tools`` run discloses that no external research was possible even though ``plan`` gives
  every question capability ``none`` (seam found here);
* a registry entry whose anchor cites the wrong page is re-anchored right after ``understand``
  (seam found here: ``understand`` records the iteration-0 registry hash, which used to turn the
  settlement into a no-op and fail INV-04 at report);
* assess runs as four concurrent shards (one per criterion group of ``config/agent.yaml``), the
  merge numbers the findings in shard order and ranks them by severity, and turns the model's
  ``NEW-n`` doc/inference evidence into ledger entries without a tool reference; a short verbatim
  quote is extended to 8 words, and one anchor is repaired in verify;
* refine answers with revisions (keep, merge, withdraw) and links the registry decision assess no
  longer links; the verdict call returns the verdict only;
* ``explain`` works for every finding;
* a run interrupted inside ``refine`` (after its model call) resumes from the ``assess`` checkpoint
  and reproduces the same ``report.json`` (ADR-009), with the re-issued call logged
  ``resumed: true`` under a new call ID.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.clock import FakeClock
from sit_review_agent.config import ConfigOverrides, EffectiveConfig, Transport, load_config
from sit_review_agent.context import RunContext
from sit_review_agent.errors import ExitCode
from sit_review_agent.invariants import check_all, spec_validator
from sit_review_agent.llm.gateway import FakeGateway, FakeResponse, LLMRequest, LLMResult
from sit_review_agent.orchestrator import RunRequest, resume_run, run_review
from sit_review_agent.paths import repo_root
from sit_review_agent.phases import default_phases
from sit_review_agent.progress import NullProgress
from sit_review_agent.report.explain import explain, format_explain
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.states import PhaseName

PDF = repo_root() / "eval" / "synthetic" / "research_lakehouse" / "design_v1.pdf"
DOC = "DOC-design_v1"
CANARY = "CANARY-MCP-7f3a9c0e2e"

# Verbatim passages of the canonical text of design_v1.pdf (page, section as pdfplumber reads them).
Q_INTENT = ("governed, multi-tenant platform that consolidates research datasets, publications and electronic lab "
            "notebooks from all")                                                                    # p1 s1
Q_NFR5 = ("Content classified Restricted or Controlled shall not be transmitted to, or processed by, any service "
          "outside Westmoor-controlled")                                                             # p3 s2.2
Q_GENMODEL = ("Commercial frontier LLM via vendor enterprise API, zero-data-retention terms, for Public, Internal "
              "and Restricted")                                                                      # p17 s20
Q_FR4 = ("active DSA that grants access to it. Faculty or department affiliation alone shall never grant "
         "access.")                                                                                  # p2 s2.1
Q_NOTEBOOK = "Notebook credentials Faculty analytics service principal per faculty"                  # p17 s20
Q_AUDIT = "Audit store Separate account, S3 Object Lock compliance mode, 7 years, hash-chained daily manifests"  # p17
Q_P7 = "P7 The audit plane sits outside the data plane. Separate AWS account, separate operators, write-once storage."
Q_RTO = ("NFR-11 Region-loss RPO ≤ 24 h and RTO ≤ 24 h for all tiers; accidental deletion or corruption of a table "
         "shall be recoverable within 4 h.")                                                         # p3 s2.2
Q_CACHE_SHORT = "faculty-scoped, cosine ≥ 0.97"                                                      # p17 s20, 4 words


def anchor(section: str, page: int | None, quote: str, req: list[str] | None = None) -> dict[str, Any]:
    return {"doc_id": DOC, "section_ref": section, "requirement_ids": req or [], "quote": quote, "page": page}


def rec(issue: str, change: str, support: list[str]) -> dict[str, Any]:
    return {"issue": issue, "rationale": "The design states two rules that cannot both hold for the same content.",
            "expected_benefit": "Builders get one unambiguous rule and the review board one decision to make.",
            "change_summary": change, "objective_refs": ["Governed multi-tenant research platform"],
            "supporting_evidence_ids": support, "verification": None}


def finding(fid: str, rank: int, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": fid, "rank": rank, "kind": "risk", "category": "internal_contradiction", "severity": "high",
        "confidence": 0.8, "disposition": "refinement_now", "secondary_dispositions": [], "title": "",
        "statement": "", "doc_anchors": [], "evidence": [], "recommendation": None, "no_change_rationale": None,
        "next_step": None, "affected_decisions": [], "acknowledged_in_doc": False, "tags": [], "reassessment": None,
        "criterion_ids": []}
    base.update(kw)
    return base


def doc_cite(eid: str, quote: str | None) -> dict[str, Any]:
    return {"evidence_id": eid, "source_type": "doc", "quote": quote, "supports_claim": True, "derived_from": []}


def assess_findings(ev: dict[str, str] | None = None, *, refined: bool = False) -> list[dict[str, Any]]:
    """The model's findings. ``ev`` maps the temporary ``NEW-n`` IDs to ledger IDs (refine cites the
    register entries assess created, as the model sees them in the refine brief)."""
    e = ev or {}

    def i(x: str) -> str:
        return e.get(x, x)

    return [
        finding("F1", 1, severity="critical", confidence=0.95 if refined else 0.85,
                title="Restricted content goes to an external LLM vendor",
                statement="Section 20 confirms a commercial frontier LLM via a vendor API for Restricted content, "
                          "but NFR-5 forbids sending Restricted content to any service outside Westmoor-controlled "
                          "AWS accounts.",
                doc_anchors=[anchor("20", 17, Q_GENMODEL), anchor("2.2", 3, Q_NFR5, ["NFR-5"])],
                evidence=[doc_cite(i("NEW-1"), Q_NFR5),
                          {"evidence_id": i("NEW-2"), "source_type": "inference",
                           "quote": "Sending Restricted content to a vendor API breaks NFR-5.", "supports_claim": True,
                           "derived_from": [i("NEW-1")]}],
                recommendation=rec("The generation-model decision contradicts NFR-5 for Restricted content.",
                                   "Limit the vendor LLM to Public and Internal content in section 20, or host a "
                                   "model inside Westmoor accounts for Restricted content.", [i("NEW-1")]),
                affected_decisions=[{"registry_id": "AD-001", "relation": "challenges",
                                     "justification": "The confirmed generation model breaks NFR-5."}],
                tags=["privacy"], criterion_ids=["internal_consistency", "security_and_privacy"]),
        finding("F2", 2, category="security_privacy_gap", disposition="needs_investigation",
                title="Faculty service principals bypass project-scoped access",
                statement="Notebooks use one analytics service principal per faculty, while FR-4 says faculty "
                          "affiliation alone never grants access to a dataset.",
                doc_anchors=[anchor("20", 17, Q_NOTEBOOK), anchor("2.1", 2, Q_FR4, ["FR-4"])],
                evidence=[doc_cite(i("NEW-3"), Q_FR4)],
                recommendation=rec("Faculty-wide credentials can read data of projects the user is not on.",
                                   "Issue per-user, project-scoped credentials to notebooks instead of one service "
                                   "principal per faculty.", [i("NEW-3")]),
                next_step={"owner": "Platform security lead", "action": "Trace a notebook read to its credential."},
                criterion_ids=["security_and_privacy"]),
        finding("F3", 3, kind="strength", category=None, severity=None, disposition="no_change",
                title="The audit plane is separated from the data plane",
                statement="Principle P7 keeps the audit plane in a separate account with separate operators and "
                          "write-once storage.",
                doc_anchors=[anchor("3", 3, Q_P7)],
                no_change_rationale="Separate account, operators and Object Lock storage make the audit trail "
                                    "tamper-evident as NFR-8 requires.",
                criterion_ids=["fitness_for_objectives"]),
        finding("F4", 4, kind="ambiguity", category="ambiguous_requirement", severity="medium",
                title="Faculty-scoped answer cache is not project-scoped",
                statement="The answer cache is faculty-scoped, so a cached answer can cross project boundaries.",
                doc_anchors=[anchor("20", 17, Q_CACHE_SHORT)],          # 4 words, verbatim: extended in code
                recommendation=rec("A faculty-scoped cache can serve one project's answer to another.",
                                   "Scope the answer cache by project and entitlement set in section 20.", []),
                criterion_ids=["requirement_completeness"]),
        finding("F5", 5, kind="validation_need", category="acceptance_criterion_cannot_validate",
                severity="medium", disposition="needs_testing",
                title="Region-loss recovery targets are not exercised end to end",
                statement="NFR-11 sets 24 h RPO and RTO for every tier, but no test restores the catalog and "
                          "the lakehouse together in the DR region.",
                doc_anchors=[anchor("2.2", 9, Q_RTO, ["NFR-11"])],      # wrong page: repaired in verify
                evidence=[doc_cite(i("NEW-5"), Q_RTO)],
                recommendation=rec("The recovery targets are stated but not demonstrated.",
                                   "Add a full region-failover exercise with measured RPO and RTO to section 22.",
                                   [i("NEW-5")]),
                next_step={"owner": "SRE lead", "action": "Schedule a region-failover exercise."},
                criterion_ids=["verifiability"]),
    ]


def shard_findings(shards: list[Any]) -> dict[int, list[str]]:
    """Which planted finding each assess shard drafts, dealt by the shard groups the config gives:
    a finding goes to the (1-based) shard whose criteria hold its first criterion, in rank order.
    Every shard gets an entry (possibly empty), so any configured group count is served."""
    out: dict[int, list[str]] = {k: [] for k in range(1, len(shards) + 1)}
    for f in assess_findings():
        home = [k for k, s in enumerate(shards, 1) if f["criterion_ids"][0] in s.criteria]
        assert len(home) == 1, (f["id"], f["criterion_ids"][0], "is in no configured shard group")
        out[home[0]].append(f["id"])
    return out


#: The IDs the merge gives them: shard order, then each shard's own rank order. The planted
#: criteria put F3 first (intent and fitness), then F1 and F4 (requirements and consistency),
#: then F5 (verifiability), then F2 (security), for the four- and the six-group configs alike;
#: ``test_merged_ids_follow_the_configured_shard_order`` checks this against the live config.
MERGED_ID = {"F3": "FND-001", "F1": "FND-002", "F4": "FND-003", "F5": "FND-004", "F2": "FND-005"}


def build_script(shards: list[Any]) -> dict[str, list[Any]]:
    understand = FakeResponse(parsed={
        "intent_summary": {
            "statement": "A governed, multi-tenant research lakehouse with project-scoped access, embargo and DSA "
                         "enforcement, and an entitlement-aware RAG service.",
            "objectives": [{"ref": None, "text": "Governed multi-tenant research platform"},
                           {"ref": "FR-9", "text": "Entitlement-aware retrieval"}],
            "constraints": [{"ref": "NFR-5", "text": "Restricted content stays in Westmoor accounts."}],
            "key_assumptions": [], "doc_anchors": [anchor("1", 1, Q_INTENT)]},
        "registry": [
            {"type": "approved_decision", "doc_ref": "Section 20 (generation model)",
             "statement": "A commercial frontier LLM via a vendor API serves Public, Internal and Restricted content.",
             "doc_anchor": anchor("20", 17, Q_GENMODEL)},
            {"type": "constraint", "doc_ref": "NFR-5", "statement": "Restricted content is never sent outside "
             "Westmoor-controlled AWS accounts.", "doc_anchor": anchor("2.2", 3, Q_NFR5, ["NFR-5"])},
            {"type": "constraint", "doc_ref": "NFR-11", "statement": "Region-loss RPO and RTO of 24 h.",
             "doc_anchor": anchor("2.2", 9, Q_RTO, ["NFR-11"])},       # wrong page: settled after understand
        ],
        "document_version": "1.0", "review_inputs_found": []})
    plan = FakeResponse(parsed={
        "questions": [
            {"id": "Q-a", "criterion_id": "internal_consistency", "question": "Do section 20's decisions contradict "
             "the requirements?", "rationale": "Confirmed decisions are listed apart from the requirements.",
             "needs_external": False, "capability": "none", "queries": [], "section_refs": ["20", "2.2"]},
            {"id": "Q-b", "criterion_id": "claims_and_external_constraints", "question": "Does the vendor's "
             "zero-data-retention term satisfy NFR-5?", "rationale": "Needs the vendor's published terms.",
             "needs_external": True, "capability": "search", "queries": ["vendor zero data retention terms"],
             "section_refs": ["20"]}],
        "criteria_skipped": [{"criterion_id": "operability_and_governance", "reason": "Out of scope for this pass."}]})

    by_title = {f["id"]: f for f in assess_findings()}
    dealt = shard_findings(shards)

    def shard(i: int) -> FakeResponse:
        mine = [by_title[x] for x in dealt[i]]
        for f in mine:
            f["affected_decisions"] = []                          # assess shards link no decisions
        cited = {c for f in mine for c in f["criterion_ids"]}
        coverage = [{"criterion_id": c, "outcome": "findings" if c in cited else "no_issue", "finding_ids": [],
                     "note": "e2e"} for c in shards[i - 1].criteria]
        areas = ([{"section_refs": ["20"], "why_sound": "The audit store is write-once for seven years.",
                   "doc_anchors": [anchor("20", 17, Q_AUDIT)], "evidence_ids": [], "related_finding_ids": ["F3"]}]
                 if "F3" in dealt[i] else [])
        return FakeResponse(parsed={"findings": mine, "sound_areas": areas, "coverage": coverage})

    def keep(fx: str, rank: int, severity: str | None, disposition: str, **kw: Any) -> dict[str, Any]:
        return {"finding_id": MERGED_ID[fx], "action": "keep", "merge_into": None, "rank": rank, "severity": severity,
                "disposition": disposition, "affected_decisions": [], "added_evidence": [], "next_step": None,
                "reason": "Checked.", **kw}

    refine = FakeResponse(parsed={"revisions": [
        keep("F1", 1, "critical", "refinement_now", reason="NFR-5's wording confirms the conflict with AD-001.",
             affected_decisions=[{"registry_id": "AD-001", "relation": "challenges",
                                  "justification": "The confirmed generation model breaks NFR-5."}]),
        keep("F2", 2, "high", "needs_investigation"), keep("F4", 3, "medium", "refinement_now"),
        keep("F5", 4, "medium", "needs_testing"), keep("F3", 5, None, "no_change")]})

    verify = FakeResponse(parsed={"repairs": [{"owner_id": MERGED_ID["F5"], "anchor_index": 0,
                                               "doc_anchor": anchor("2.2", 3, Q_RTO, ["NFR-11"])}]})
    report = FakeResponse(parsed={
        "verdict": {"label": "not_fit", "rationale": "Restricted content would leave Westmoor accounts through the "
                    "confirmed generation model, which NFR-5 forbids.", "confidence": 0.8,
                    "conditions": [{"text": "Resolve the generation-model conflict with NFR-5.",
                                    "finding_ids": [MERGED_ID["F1"]]}],
                    "per_objective": [{"objective_ref": "Governed multi-tenant research platform",
                                       "label": "not_fit", "finding_ids": [MERGED_ID["F1"], MERGED_ID["F2"]]}],
                    "what_would_change_it": "A Westmoor-hosted model for Restricted content."}})
    return {"understand": [understand], "plan": [plan], "assess": [shard(i) for i in range(1, len(shards) + 1)],
            "refine": [refine], "verify": [verify], "report": [report]}


class ScriptedGateway(FakeGateway):
    """``FakeGateway`` whose script entries may be callables ``(ledger_entries, request)`` resolved
    when their turn comes (the model cites the ``EV-`` IDs that exist at that point)."""

    def __init__(self, rd: RunDir, clock: Any, shards: list[Any]) -> None:
        super().__init__(build_script(shards), run_dir=rd, clock=clock)
        self.rd = rd

    async def call(self, request: LLMRequest) -> LLMResult[Any]:
        q = self.script.get(str(request.phase))
        if q and callable(q[0]):
            q[0] = q[0](JsonlWriter(self.rd.ledger_journal).read(), request)
        return await super().call(request)


def config(tmp_path: Path) -> EffectiveConfig:
    cfg = load_config(overrides=ConfigOverrides(transport=Transport.FAKE, no_tools=True))
    agent = cfg.agent.model_copy(update={"run_root": str(tmp_path / "runs"), "fault_schedule": None,
                                         "plan_approval": False})
    return cfg.model_copy(update={"agent": agent})


def factory(cfg: EffectiveConfig) -> Any:
    shards = cfg.agent.assess.shards_for(cfg.criteria.ids())
    assert sorted(shard_findings(shards)) == list(range(1, len(shards) + 1))
    return lambda rd, clock, progress: ScriptedGateway(rd, clock, shards)


class RefineThenInterrupt:
    """The real refine phase, then Ctrl-C before its checkpoint (its model call is in llm.jsonl)."""

    name = PhaseName.REFINE

    async def run(self, ctx: RunContext) -> RunContext:
        await default_phases()[PhaseName.REFINE].run(ctx)
        raise KeyboardInterrupt


def comparable(rd: Path) -> dict[str, Any]:
    r = json.loads((rd / "report.json").read_text(encoding="utf-8"))
    r.pop("run_manifest")
    r["metadata"].pop("run_id")
    r["metadata"].pop("review_id")
    return r


async def test_e2e_synthetic_pdf_doc_only_then_resume_after_assess(tmp_path: Path,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    t0 = time.monotonic()
    monkeypatch.setenv("SIT_MCP_API_KEY", CANARY)
    cfg = config(tmp_path)
    assert cfg.tools.enabled_servers() == []                                  # --no-tools

    # ---- run A: straight through
    out = await run_review(RunRequest(pdf=PDF, config=cfg, run_id="e2e-a"), llm_factory=factory(cfg),
                           clock=FakeClock(), progress=NullProgress())
    rd = RunDir(out.run_dir)
    assert out.exit_code == 0, rd.failure.read_text(encoding="utf-8") if rd.failure.exists() else ""
    report = json.loads(rd.report_json.read_text(encoding="utf-8"))
    assert [f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
            for e in spec_validator("Review").iter_errors(report)] == []
    results = check_all(report, rd.root, canaries=[CANARY])
    assert [(r.inv_id, r.problems) for r in results if not r.passed] == []
    assert not any(r.skipped for r in results)                               # INV-08 really ran

    # plan: model IDs renumbered, a criterion the model left out gets a doc-only question (seam 1g)
    state = json.loads(rd.state.read_text(encoding="utf-8"))
    qids = [q["id"] for q in state["plan"]["questions"]]
    assert qids == [f"RQ-{i + 1:03d}" for i in range(len(qids))] and "Q-a" not in json.dumps(report)
    # --no-tools: disclosed, the external question is unanswered, no external evidence
    assert report["stop_reason"]["code"] == "tool_failure"
    assert any(d["type"] == "tool_unavailable" and d["event"].startswith("No external research was possible")
               for d in report["research_log"]["degradations"])
    ext_q = next(q for q in state["plan"]["questions"] if q["needs_external"])
    assert ext_q["status"] == "unanswered" and any(ext_q["id"] in u for u in report["research_log"]
                                                   ["unanswered_questions"])
    assert all(e["source_type"] != "external" and e["tool"] is None for e in report["evidence_ledger"])
    assert not rd.tools_log.exists()
    # registry: the NFR-11 entry cited page 9 and was re-anchored right after understand
    nfr11 = next(e for e in report["decision_registry"] if e["doc_ref"] == "NFR-11")
    assert nfr11["doc_anchor"]["page"] == 3
    assert {h["iteration"] for h in report["research_log"]["registry_sha256_by_iteration"]} == {0}
    # findings: numbered in shard order, ranked by refine, short quote extended, anchor repaired,
    # inference derived from a doc entry
    by_id = {f["id"]: f for f in report["findings"]}
    assert sorted(by_id) == sorted(MERGED_ID.values())
    assert [f["id"] for f in sorted(report["findings"], key=lambda f: f["rank"])] == [
        MERGED_ID[x] for x in ("F1", "F2", "F4", "F5", "F3")]
    f4 = by_id[MERGED_ID["F4"]]
    assert len(f4["doc_anchors"][0]["quote"].split()) >= 8
    assert by_id[MERGED_ID["F5"]]["doc_anchors"][0]["page"] == 3
    anchors = json.loads(rd.anchors.read_text(encoding="utf-8"))
    assert anchors["summary"]["repaired"] == 1 and anchors["summary"]["unresolved"] == 0
    f1 = by_id[MERGED_ID["F1"]]
    assert [e["source_type"] for e in f1["evidence"]] == ["doc", "inference"]
    assert f1["affected_decisions"][0]["relation"] == "challenges"                # linked by refine
    assert f1["provenance"]["phase"] == "revise" and f1["confidence"] == 0.85     # a revision keeps confidence
    assert by_id[MERGED_ID["F3"]]["provenance"]["phase"] == "assess"             # unchanged by refine
    assert report["verdict"]["label"] == "not_fit"
    assert sorted(p.name for p in (rd.root / "shards").iterdir()) == [   # one file per configured group
        f"{k:02d}-{s.name}.json" for k, s in enumerate(cfg.agent.assess.shards_for(cfg.criteria.ids()), 1)]
    # explain works for every finding
    for fid in by_id:
        text = format_explain(explain(rd.root, fid))
        assert fid in text and "NOT IN LEDGER" not in text
    llm_ids = [e["call_id"] for e in JsonlWriter(rd.llm_log).read()]
    k = len(cfg.agent.assess.shards_for(cfg.criteria.ids()))
    assert llm_ids == [f"llm-{i:04d}" for i in range(1, k + 6)]              # research made no model call
    convs = [e["conversation_id"] for e in JsonlWriter(rd.llm_log).read() if e["phase"] == "assess"]
    assert convs == [f"assess-0-s{i}" for i in range(1, k + 1)]

    # ---- run B: dies inside refine after its model call, resumes from the assess checkpoint
    phases = {**default_phases(), PhaseName.REFINE: RefineThenInterrupt()}
    out_b = await run_review(RunRequest(pdf=PDF, config=cfg, run_id="e2e-b"), phases=phases,
                             llm_factory=factory(cfg), clock=FakeClock(), progress=NullProgress())
    assert out_b.exit_code == int(ExitCode.SIGINT)
    rdb = RunDir(out_b.run_dir)
    ledger_before = len(JsonlWriter(rdb.ledger_journal).read())
    res = await resume_run(rdb.root, cfg, llm_factory=factory(cfg), clock=FakeClock(), progress=NullProgress())
    assert res.exit_code == 0, rdb.failure.read_text(encoding="utf-8") if rdb.failure.exists() else ""
    assert comparable(rdb.root) == comparable(rd.root)                        # ADR-009: same report
    entries = JsonlWriter(rdb.llm_log).read()
    ids = [e["call_id"] for e in entries]
    assert len(ids) == len(set(ids)) == k + 6                                 # refine re-issued under a new ID
    refine = [e for e in entries if e["phase"] == "refine"]
    assert [e.get("resumed", False) for e in refine] == [False, True]
    assert not any(e.get("resumed") for e in entries if e["phase"] != "refine")
    ev_ids = [e["evidence_id"] for e in JsonlWriter(rdb.ledger_journal).read()]
    assert len(ev_ids) == len(set(ev_ids)) and len(ev_ids) >= ledger_before - 0
    report_b = json.loads(rdb.report_json.read_text(encoding="utf-8"))
    assert [r.inv_id for r in check_all(report_b, rdb.root, canaries=[CANARY]) if not r.passed] == []
    assert any(d.startswith("resumed after phase assess") for d in report_b["run_manifest"]["extra"]["deviations"])
    assert time.monotonic() - t0 < 10.0
