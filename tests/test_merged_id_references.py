"""Finding-ID references survive the shard merge and refine (traceability defect of both concurrent
rehearsal runs, ``docs/transcripts/session4/merged_id_references.md``).

End to end on the synthetic PDF with every real phase and a scripted ``FakeGateway`` (offline, no
key). Each assess shard numbers its own findings ``FND-001..`` (as the live model does), the merge
renumbers them in shard order, and refine merges two duplicates and withdraws one draft. The shards'
text cites their own IDs: a coverage note, a sound area and another finding's statement; refine's
decision link cites a merged ID, and the verdict cites one. Every one of those references must end
as a finding of the final list, or be removed, in ``report.json`` and in ``report.md``.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.clock import FakeClock
from sit_review_agent.invariants import check_all
from sit_review_agent.llm.gateway import FakeGateway, FakeResponse
from sit_review_agent.orchestrator import RunRequest, run_review
from sit_review_agent.progress import NullProgress
from sit_review_agent.rundir import RunDir
from test_e2e_synthetic import (  # type: ignore[import-not-found]
    CANARY,
    PDF,
    Q_AUDIT,
    Q_GENMODEL,
    Q_P7,
    Q_RTO,
    anchor,
    assess_findings,
    build_script,
    config,
    finding,
    rec,
)

TOKEN = re.compile(r"\bFND-\d{3,}\b")

#: Which drafts each shard returns, under the shard's own IDs (the model numbers per call).
SHARDS: dict[int, list[tuple[str, str]]] = {
    1: [("FND-001", "F3"), ("FND-002", "F3dup"), ("FND-003", "F2")],
    2: [("FND-001", "F1"), ("FND-002", "F4"), ("FND-003", "F5"), ("FND-004", "F1dup"), ("FND-005", "F6"),
        ("FND-006", "F8")],
    3: [],
    4: [],
}
#: The merged draft IDs (shard order, then each shard's rank order).
DRAFT = {"F3": "FND-001", "F3dup": "FND-002", "F2": "FND-003", "F1": "FND-004", "F4": "FND-005",
         "F5": "FND-006", "F1dup": "FND-007", "F6": "FND-008", "F8": "FND-009"}
FINAL = {DRAFT[x] for x in ("F1", "F2", "F3", "F4", "F5")}


def drafts_by_name() -> dict[str, dict[str, Any]]:
    base = {f["id"]: f for f in assess_findings()}
    out = copy.deepcopy(base)
    out["F3dup"] = finding("F3dup", 9, kind="strength", category=None, severity=None, disposition="no_change",
                           title="The audit store is write-once",
                           statement="The audit store uses S3 Object Lock in compliance mode for seven years.",
                           doc_anchors=[anchor("20", 17, Q_AUDIT)],
                           no_change_rationale="Write-once storage keeps the audit trail tamper-evident.",
                           criterion_ids=["fitness_for_objectives"])
    out["F1dup"] = finding("F1dup", 9, severity="high", title="Vendor LLM receives Restricted content",
                           statement="Restricted content reaches the vendor LLM API named in section 20.",
                           doc_anchors=[anchor("20", 17, Q_GENMODEL)],
                           no_change_rationale=None, disposition="needs_investigation",
                           next_step={"owner": "Architect", "action": "Confirm the content classes sent."},
                           criterion_ids=["internal_consistency"])
    out["F6"] = finding("F6", 9, kind="ambiguity", category="ambiguous_requirement", severity="low",
                        title="Recovery wording is loose", statement="Section 2.2 words recovery loosely.",
                        doc_anchors=[anchor("2.2", 3, Q_RTO, ["NFR-11"])], disposition="needs_investigation",
                        next_step={"owner": "SRE lead", "action": "Check the recovery wording."},
                        criterion_ids=["verifiability"])
    out["F8"] = finding("F8", 9, severity="low", title="Unanchored claim", disposition="needs_investigation",
                        statement="The catalog has no owner. Same root cause as FND-001.",
                        doc_anchors=[anchor("9", 5, "This sentence does not appear anywhere in the design document.")],
                        recommendation=rec("Nobody owns the catalog, so nobody fixes its entries.",
                                           "Name an owner for the catalog in section 20.", []),
                        next_step={"owner": "Data lead", "action": "Name the catalog owner."},
                        criterion_ids=["internal_consistency"])          # no anchor resolves: unverified in verify
    # Cross-references in the shards' own numbering. Shard 1: F2 cites F3dup (merged into F3).
    # Shard 2: F5 cites F1 (local FND-001, which is F3 in the merged numbering), F4 cites F6 (local
    # FND-005, withdrawn by refine).
    out["F2"]["statement"] += " The write-once audit store (FND-002) does not help here."
    out["F5"]["statement"] += " Related: FND-001."
    out["F4"]["statement"] += " Compare FND-005."
    return out


def build(shards: list[Any]) -> dict[str, list[Any]]:
    script = build_script(shards)
    by_name = drafts_by_name()

    def shard(i: int) -> FakeResponse:
        mine = []
        for rank, (local, name) in enumerate(SHARDS[i], start=1):
            f = copy.deepcopy(by_name[name])
            f.update(id=local, rank=rank, affected_decisions=[])
            mine.append(f)
        notes = {"fitness_for_objectives": "Raised in FND-001 and FND-002.",
                 "internal_consistency": "Raised in FND-001, FND-004 and FND-006."}
        cited = {c for f in mine for c in f["criterion_ids"]}
        coverage = [{"criterion_id": c, "outcome": "findings" if c in cited else "no_issue", "finding_ids": [],
                     "note": notes.get(c, "e2e")} for c in shards[i - 1].criteria]
        areas: list[dict[str, Any]] = []
        if i == 1:
            areas = [{"section_refs": ["20"],
                      "why_sound": "The audit store is write-once for seven years (see FND-002).",
                      "doc_anchors": [anchor("20", 17, Q_AUDIT)], "evidence_ids": [],
                      "related_finding_ids": ["FND-001", "FND-002"]}]
        elif i == 2:
            areas = [{"section_refs": ["3"],
                      "why_sound": "The audit plane is separate from the data plane (see FND-005).",
                      "doc_anchors": [anchor("3", 3, Q_P7)], "evidence_ids": [], "related_finding_ids": []}]
        return FakeResponse(parsed={"findings": mine, "sound_areas": areas, "coverage": coverage})

    def rev(name: str, action: str = "keep", **kw: Any) -> dict[str, Any]:
        base: dict[str, Any] = {"finding_id": DRAFT[name], "action": action, "merge_into": None, "rank": None,
                                "severity": None, "disposition": None, "affected_decisions": [],
                                "added_evidence": [], "next_step": None, "reason": "Checked."}
        base.update(kw)
        return base

    script["assess"] = [shard(i) for i in range(1, len(shards) + 1)]
    script["refine"] = [FakeResponse(parsed={"revisions": [
        rev("F1", rank=1, severity="critical", disposition="refinement_now",
            reason="NFR-5's wording confirms the conflict with AD-001.",
            affected_decisions=[{"registry_id": "AD-001", "relation": "challenges",
                                 "justification": "The confirmed generation model breaks NFR-5; see also FND-002."}]),
        rev("F2", rank=2, severity="high", disposition="needs_investigation"),
        rev("F4", rank=3, severity="medium", disposition="refinement_now"),
        rev("F5", rank=4, severity="medium", disposition="needs_testing"),
        rev("F3", rank=5, severity=None, disposition="no_change"),
        rev("F8", rank=6, severity="low", disposition="needs_investigation"),
        rev("F3dup", "merge", merge_into=DRAFT["F3"], reason="Duplicate of the audit strength."),
        rev("F1dup", "merge", merge_into=DRAFT["F1"], reason="Same conflict."),
        rev("F6", "withdraw", reason="Too vague to act on."),
    ]})]
    script["verify"] = [FakeResponse(parsed={"repairs": [{"owner_id": DRAFT["F5"], "anchor_index": 0,
                                                           "doc_anchor": anchor("2.2", 3, Q_RTO, ["NFR-11"])}]})]
    script["report"] = [FakeResponse(parsed={"verdict": {
        "label": "not_fit", "rationale": "Restricted content would leave Westmoor accounts (FND-004, FND-007).",
        "confidence": 0.8,
        "conditions": [{"text": "Resolve the generation-model conflict with NFR-5.", "finding_ids": [DRAFT["F1"]]}],
        "per_objective": [{"objective_ref": "Governed multi-tenant research platform", "label": "not_fit",
                           "finding_ids": [DRAFT["F1"], DRAFT["F2"]]}],
        "what_would_change_it": "A Westmoor-hosted model for Restricted content."}})]
    return script


def factory(cfg: Any) -> Any:
    shards = cfg.agent.assess.shards_for(cfg.criteria.ids())
    assert len(shards) == len(SHARDS)
    return lambda rd, clock, progress: FakeGateway(build(shards), run_dir=rd, clock=clock)


def cited(node: Any, path: str = "$") -> list[tuple[str, str]]:
    """(path, ID) for every finding ID in a JSON tree."""
    if isinstance(node, dict):
        return [x for k, v in node.items() for x in cited(v, f"{path}.{k}")]
    if isinstance(node, list):
        return [x for i, v in enumerate(node) for x in cited(v, f"{path}[{i}]")]
    return [(path, t) for t in TOKEN.findall(node)] if isinstance(node, str) else []


@pytest.fixture
async def run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunDir:
    monkeypatch.setenv("SIT_MCP_API_KEY", CANARY)
    cfg = config(tmp_path)
    out = await run_review(RunRequest(pdf=PDF, config=cfg, run_id="refs"), llm_factory=factory(cfg),
                           clock=FakeClock(), progress=NullProgress())
    rd = RunDir(out.run_dir)
    assert out.exit_code == 0, rd.failure.read_text(encoding="utf-8") if rd.failure.exists() else ""
    return rd


async def test_no_dangling_finding_reference_in_report_json_or_md(run: RunDir) -> None:
    report = json.loads(run.report_json.read_text(encoding="utf-8"))
    assert {f["id"] for f in report["findings"]} == FINAL
    review = {k: v for k, v in report.items() if k not in ("run_manifest", "evidence_ledger")}
    dangling = [(p, t) for p, t in cited(review) if t not in FINAL]
    assert dangling == [], dangling
    md = run.report_md.read_text(encoding="utf-8")
    md_dangling = sorted({t for t in TOKEN.findall(md) if t not in FINAL})
    assert md_dangling == [], md_dangling
    results = check_all(report, run.root, canaries=[CANARY])
    assert "INV-12" in {r.inv_id for r in results}
    assert [(r.inv_id, r.problems) for r in results if not r.passed] == []


async def test_each_reference_follows_its_finding(run: RunDir) -> None:
    """Shard-local IDs read in the shard's numbering, merged IDs point at the kept finding, and a
    reference to a withdrawn or unverified draft is removed with its clause."""
    report = json.loads(run.report_json.read_text(encoding="utf-8"))
    by_id = {f["id"]: f for f in report["findings"]}
    assert by_id[DRAFT["F2"]]["statement"].endswith(" The write-once audit store (FND-001) does not help here.")
    assert by_id[DRAFT["F5"]]["statement"].endswith(" Related: FND-004.")
    assert by_id[DRAFT["F4"]]["statement"] == ("The answer cache is faculty-scoped, so a cached answer can cross "
                                               "project boundaries.")
    assert by_id[DRAFT["F1"]]["affected_decisions"][0]["justification"] == (
        "The confirmed generation model breaks NFR-5; see also FND-001.")
    areas = {a["why_sound"] for a in report["sound_areas"]}
    assert areas == {"The audit store is write-once for seven years (see FND-001).",
                     "The audit plane is separate from the data plane."}
    assert report["verdict"]["rationale"] == "Restricted content would leave Westmoor accounts (FND-004)."
    md = run.report_md.read_text(encoding="utf-8")
    assert "Raised in FND-001." in md and "Raised in FND-004." in md
    ids = report["run_manifest"]["extra"]["finding_ids"]
    assert ids["shards"]["intent_and_fitness"] == {"FND-001": "FND-001", "FND-002": "FND-002", "FND-003": "FND-003"}
    assert ids["shards"]["requirements_and_consistency"] == {
        "FND-001": "FND-004", "FND-002": "FND-005", "FND-003": "FND-006", "FND-004": "FND-007", "FND-005": "FND-008",
        "FND-006": "FND-009"}
    assert ids["refine"] == {"FND-002": "FND-001", "FND-007": "FND-004", "FND-008": None}
    assert ids["verify"] == {"FND-009": None}
    assert ids["final"] == {**{DRAFT[x]: DRAFT[x] for x in ("F1", "F2", "F3", "F4", "F5")},
                            "FND-002": "FND-001", "FND-007": "FND-004", "FND-008": None, "FND-009": None}
    unverified = [u["text"] for u in report["unresolved"] if u["text"].startswith("Unverified")]
    assert len(unverified) == 1 and "The catalog has no owner. Same root cause as FND-004." in unverified[0]
    assert report["run_manifest"]["extra"]["finding_ids"]["rewrites"]["removed"] >= 3


async def test_the_report_gate_refuses_a_dangling_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the rewrite, the report phase refuses the report (exit 4, ``report.invalid.json``):
    INV-12 names the dangling references of report.json, and the coverage check those of report.md."""
    from sit_review_agent.phases import report as report_phase

    monkeypatch.setenv("SIT_MCP_API_KEY", CANARY)
    monkeypatch.setattr(report_phase, "settle_refs", lambda ctx, body: body)
    cfg = config(tmp_path)
    out = await run_review(RunRequest(pdf=PDF, config=cfg, run_id="refs-gate"), llm_factory=factory(cfg),
                           clock=FakeClock(), progress=NullProgress())
    rd = RunDir(out.run_dir)
    assert out.exit_code == 4 and not rd.report_json.exists()
    problems = json.loads(rd.failure.read_text(encoding="utf-8"))["problems"]
    assert "INV-12: $.sound_areas[0].why_sound: FND-002 is not a finding of this review" in problems
    assert any(p.startswith("INV-12 (report.md): $.coverage[") for p in problems)
