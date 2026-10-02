"""ingest, verify (anchors, the one repair call, hydration) and report (assembly, invariants,
rendering, explain) - workstream C, "phase 3".

Covers what tests/test_pending.py's ``test_verify_and_report_produce_valid_review`` and
``test_explain_reads_run_dir_only`` describe (that shared file is not edited here).
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.clock import FakeClock, isoformat_z
from sit_review_agent.config import load_config
from sit_review_agent.context import RunContext
from sit_review_agent.errors import InputError, LedgerError, StageCrash
from sit_review_agent.hashing import sha256_file, sha256_text
from sit_review_agent.ingest.pdf import Document
from sit_review_agent.ingest.text import normalise
from sit_review_agent.invariants import check_all
from sit_review_agent.llm.gateway import FakeGateway, FakeResponse
from sit_review_agent.llm.outputs import FindingDraft, RegistryEntryDraft, SoundAreaDraft
from sit_review_agent.manifest import report_json_sha256, start_manifest
from sit_review_agent.models import (
    DegradationType,
    DocumentRole,
    IntentSummary,
    Review,
    Severity,
    SourceAuthority,
    StopReason,
    StopReasonCode,
    ToolCallStatus,
)
from sit_review_agent.phases.ingest import IngestPhase, doc_id_for, placeholder_ref
from sit_review_agent.phases.report import ReportPhase, assemble_review, fallback_verdict
from sit_review_agent.phases.verify import VerifyPhase, hydrate_finding, settle_registry_anchors
from sit_review_agent.progress import NullProgress
from sit_review_agent.prompts import PromptBundle
from sit_review_agent.report.explain import explain, format_explain
from sit_review_agent.report.render import SECTION_ORDER, render_markdown
from sit_review_agent.rundir import RunDir
from sit_review_agent.state.decision_registry import DecisionRegistry
from sit_review_agent.state.evidence_ledger import EvidenceLedger
from sit_review_agent.state.run_state import FindingMeta, RunState
from sit_review_agent.states import PhaseName
from sit_review_agent.tools.gateway import ToolResult
from sit_review_agent.tools.sources import ExternalSource

FIXTURES = Path(__file__).parent / "fixtures"
BOOKING = FIXTURES / "booking_v1.pages.txt"
DOC_ID = "DOC-booking_v1"
Q_MAIL = ("The selected e-mail service has no daily sending limit, so reminders are sent individually as each slot "
          "approaches.")
Q_LOAD = "Peak exam-week days generate about 5,000 bookings, each with one reminder."
Q_A11Y = ("Every booking screen is tested against WCAG 2.2 level AA with automated checks and a manual "
          "screen-reader pass.")
Q_D3 = "D-3 Confirmed: the booking front end is built from the campus design system component library."
Q_FAKE = "Students may cancel a booking at any time before the slot begins without any penalty."


# ============================================================================ tiny PDF writer


def make_pdf(pages: list[list[str]], *, title: str = "Tiny design") -> bytes:
    """A minimal valid PDF (Helvetica text lines, one content stream per page), no PDF library."""
    objs: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b"",
                         b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", f"<< /Title ({title}) >>".encode()]
    kids = []
    for lines in pages:
        ops = ["BT /F1 11 Tf 72 740 Td 14 TL"] + [f"({ln}) Tj T*" for ln in lines] + ["ET"]
        stream = "\n".join(ops).encode("latin-1")
        content_no = len(objs) + 2
        page_no = len(objs) + 1
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                    f"/Contents {content_no} 0 R >>".encode())
        objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        kids.append(f"{page_no} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info 4 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


# ============================================================================ context helper


def make_ctx(tmp_path: Path, script: dict[str, list[FakeResponse]] | None = None, *, source: Path = BOOKING,
             run_id: str = "run-c") -> RunContext:
    clock = FakeClock()
    cfg = load_config().model_copy(update={"agent": load_config().agent.model_copy(
        update={"run_root": str(tmp_path / "runs")})})
    rd = RunDir(tmp_path / "runs" / run_id).create()
    (rd.effective_config).write_text(json.dumps(cfg.model_dump(mode="json")), encoding="utf-8")
    state = RunState(run_id=run_id, created_utc=isoformat_z(clock.now_utc()),
                     documents=[placeholder_ref(source, DocumentRole.UNDER_REVIEW)])
    return RunContext(config=cfg, run_dir=rd, state=state, llm=FakeGateway(script or {}, run_dir=rd, clock=clock),
                      tools=None, ledger=EvidenceLedger(rd, clock=clock), registry=DecisionRegistry(),
                      prompts=PromptBundle.load(), clock=clock, progress=NullProgress())


def anchor(section: str, page: int, quote: str, req: list[str] | None = None) -> dict[str, Any]:
    return {"doc_id": DOC_ID, "section_ref": section, "requirement_ids": req or [], "quote": quote, "page": page}


def draft(fid: str, *, anchors: list[dict[str, Any]], evidence: list[dict[str, Any]] | None = None,
          kind: str = "risk", disposition: str = "refinement_now", rank: int = 1, **kw: Any) -> FindingDraft:
    ev_ids = [e["evidence_id"] for e in (evidence or [])]
    base: dict[str, Any] = {
        "id": fid, "rank": rank, "kind": kind, "category": None if kind == "strength" else "other",
        "severity": None if kind == "strength" else "high", "confidence": 0.8, "disposition": disposition,
        "secondary_dispositions": [], "title": f"Title of {fid}", "statement": f"Statement of {fid}.",
        "doc_anchors": anchors, "evidence": evidence or [],
        "recommendation": None if disposition == "no_change" else {
            "issue": "The issue is stated in enough words.", "rationale": "The rationale is stated in enough words.",
            "expected_benefit": "The benefit is stated against an objective.",
            "change_summary": "Change section 6.2 so that reminders fit the quota.", "objective_refs": ["FR-9"],
            "supporting_evidence_ids": ev_ids, "verification": None},
        "no_change_rationale": "The design already meets the objective." if disposition == "no_change" else None,
        "next_step": {"owner": "Test lead", "action": "Run the test."} if disposition not in (
            "refinement_now", "no_change") else None,
        "affected_decisions": [], "acknowledged_in_doc": False, "tags": [], "reassessment": None,
        "criterion_ids": ["claims_and_external_constraints"]}
    base.update(kw)
    return FindingDraft.model_validate(base)


def meta(fid: str, phase: PhaseName = PhaseName.REFINE) -> FindingMeta:
    return FindingMeta(finding_id=fid, criterion_ids=["claims_and_external_constraints"],
                       created_phase=PhaseName.ASSESS, created_call_id="llm-0001", last_phase=phase,
                       last_call_id="llm-0002", model="claude-opus-5-5", prompt_hash=sha256_text("p"))


def tool_result(call_id: str = "call-0001", tool: str = "fetch") -> ToolResult:
    return ToolResult(call_id=call_id, server="mcp-internet-search", tool_name=tool,
                      args={"url": "https://docs.example-mail.invalid/plans"}, status=ToolCallStatus.OK,
                      is_error=False, content=[], text="page", structured_content=None,
                      started_at="2026-10-02T09:00:00Z", elapsed_s=0.1, cassette_key="k")


def add_external(ctx: RunContext, *, read: bool = True, call_id: str = "call-0001") -> str:
    tr = tool_result(call_id)
    ctx.state.tool_calls.append(tr.research_log_entry())
    e = ctx.ledger.add_external(tr, ExternalSource(
        url_or_citation="https://docs.example-mail.invalid/plans", title="Plans and sending limits",
        excerpt="The Starter plan allows up to 2,000 messages per day.", content="page",
        authority=SourceAuthority.PRIMARY_OFFICIAL, read_in_full=read))
    return e.evidence_id


def ext_cite(eid: str, quote: str | None = "The Starter plan allows up to 2,000 messages per day.") -> dict[str, Any]:
    return {"evidence_id": eid, "source_type": "external", "quote": quote, "supports_claim": True, "derived_from": []}


async def ingested(tmp_path: Path, script: dict[str, list[FakeResponse]] | None = None) -> RunContext:
    ctx = make_ctx(tmp_path, script)
    ctx = await IngestPhase().run(ctx)
    ctx.state.intent_summary = IntentSummary(statement="Students reserve rooms.", objectives=[], constraints=[],
                                             key_assumptions=[], doc_anchors=[anchor("1", 2, "The service lets "
                                                                              "students reserve study rooms for "
                                                                              "one-hour slots across campus.")])
    ctx.registry.add(RegistryEntryDraft.model_validate({"type": "approved_decision", "doc_ref": "D-3",
                                                        "statement": "Front end from the design system.",
                                                        "doc_anchor": anchor("20", 19, Q_D3, ["D-3"])}))
    ctx.registry.freeze()
    ctx.state.stop_reason = StopReason.of(StopReasonCode.SUFFICIENT_EVIDENCE)
    return ctx


REPORT_OK = FakeResponse(parsed={
    "verdict": {"label": "fit_with_conditions", "rationale": "Reminders fail on peak days.", "confidence": 0.7,
                "conditions": [{"text": "Fix the quota.", "finding_ids": ["FND-001", "FND-404"]},
                               {"text": "Cites nothing known.", "finding_ids": ["FND-999"]}],
                "per_objective": [], "what_would_change_it": None},
    "unresolved": [], "limitations": [{"text": "Unknown degradation.", "degradation_ids": ["DEG-999"]}]})
REPAIR = FakeResponse(parsed={"repairs": [{"owner_id": "FND-001", "anchor_index": 1,
                                           "doc_anchor": anchor("4.1", 6, Q_LOAD)}]})


# ============================================================================ ingest


async def test_ingest_text_fixture(tmp_path: Path) -> None:
    ctx = await IngestPhase().run(make_ctx(tmp_path))
    doc = ctx.documents[DOC_ID]
    assert [s.section_id for s in doc.sections] == ["1", "4.1", "6.2", "11.3", "20"]
    assert [s.heading for s in doc.sections] == ["Overview", "Load", "Notifications", "Accessibility", "Decisions"]
    assert doc.page_count == 19 and doc.requirement_index["D-3"][0].page == 19
    ref = ctx.state.documents[0]
    assert ref.text_path == "text/DOC-booking_v1.pages.txt" and ref.sha256_pdf is None and not ref.native_pdf
    assert ref.sha256_text == sha256_text(ctx.run_dir.doc_text(DOC_ID).read_text(encoding="utf-8"))
    side = json.loads(ctx.run_dir.doc_sections(DOC_ID).read_text(encoding="utf-8"))
    assert side["sha256_text"] == ref.sha256_text and len(side["sections"]) == 5
    assert ctx.state.degradations == []                  # a text input is not a degraded PDF


async def test_ingest_generated_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "tiny.pdf"
    pdf.write_bytes(make_pdf([["Tiny design", "1 Overview", "The service lets students book quiet rooms for an hour."],
                              ["2 Requirements", "FR-1 Every booking receives one reminder an hour before the slot."]]))
    ctx = make_ctx(tmp_path, source=pdf)
    ctx = await IngestPhase().run(ctx)
    doc = ctx.documents["DOC-tiny"]
    assert doc.page_count == 2 and doc.title == "Tiny design" and doc.pdf_bytes == pdf.read_bytes()
    assert "[[PAGE 2]]" in doc.text and "FR-1" in doc.requirement_index
    assert [s.section_id for s in doc.sections] == ["1", "2"]
    ref = ctx.state.documents[0]
    assert ref.sha256_pdf == sha256_file(pdf) and ref.native_pdf is True    # FakeGateway accepts native PDF


async def test_ingest_pdf_with_text_only_backend_is_disclosed(tmp_path: Path) -> None:
    pdf = tmp_path / "tiny.pdf"
    pdf.write_bytes(make_pdf([["1 Overview", "The service lets students book quiet rooms for an hour each day."]]))
    ctx = make_ctx(tmp_path, source=pdf)
    ctx.llm.native_pdf = False                           # like ClaudeCodeGateway (ADR-010)
    ctx = await IngestPhase().run(ctx)
    assert not ctx.state.documents[0].native_pdf
    assert ctx.state.degradations[0].type is DegradationType.INPUT_DEGRADED


@pytest.mark.parametrize("content", [b"not a pdf at all", make_pdf([[]]), b""])
async def test_ingest_rejects_unreadable_or_empty_input(tmp_path: Path, content: bytes) -> None:
    pdf = tmp_path / "bad.pdf"
    pdf.write_bytes(content)
    with pytest.raises(InputError):
        await IngestPhase().run(make_ctx(tmp_path, source=pdf))


def test_doc_ids() -> None:
    assert doc_id_for("inbox/design v2.pdf") == "DOC-design-v2"
    assert doc_id_for("x/DOC-a.pages.txt") == "DOC-a"
    assert doc_id_for("v1/design.pdf", DocumentRole.PRIOR_VERSION, taken={"DOC-design"}) == "DOC-design-prior"


def test_heading_heuristic_on_booking_fixture(booking_pages: str) -> None:
    doc = Document.from_page_marked_text(normalise(booking_pages), doc_id=DOC_ID)
    assert [(s.section_id, s.page_start) for s in doc.sections] == [("1", 2), ("4.1", 6), ("6.2", 11), ("11.3", 18),
                                                                    ("20", 19)]


# ============================================================================ verify


async def test_verify_resolved_anchors_make_no_model_call(tmp_path: Path) -> None:
    ctx = await ingested(tmp_path)                     # empty script: any call would raise
    ev = add_external(ctx)
    ctx.state.finding_drafts = [draft("FND-001", anchors=[anchor("6.2", 11, Q_MAIL)], evidence=[ext_cite(ev)])]
    ctx.state.finding_meta = {"FND-001": meta("FND-001")}
    ctx = await VerifyPhase().run(ctx)
    [f] = ctx.state.findings
    assert f.provenance.phase.value == "revise" and f.provenance.model == "claude-opus-5-5"
    assert "criterion_ids" not in f.model_dump() and ctx.state.finding_meta["FND-001"].criterion_ids
    assert f.evidence[0].url_or_citation == "https://docs.example-mail.invalid/plans"
    assert f.evidence[0].retrieved_at == "2026-10-02T09:00:00Z"
    table = json.loads(ctx.run_dir.anchors.read_text(encoding="utf-8"))
    assert table["summary"] == {"anchors": 3, "resolved": 3, "repaired": 0, "unresolved": 0}
    assert table["repair_call_id"] is None and ctx.state.llm_calls.get("verify") is None


async def test_verify_one_repair_call_repaired_and_unresolved(tmp_path: Path) -> None:
    ctx = await ingested(tmp_path, {"verify": [REPAIR]})            # a second call would exhaust the script
    ev = add_external(ctx)
    ctx.state.finding_drafts = [
        draft("FND-001", anchors=[anchor("6.2", 11, Q_MAIL), anchor("4.1", 2, Q_LOAD)], evidence=[ext_cite(ev)]),
        draft("FND-002", anchors=[anchor("1", 2, Q_FAKE)], evidence=[ext_cite(ev)], rank=2),
        draft("FND-003", anchors=[anchor("6.2", 11, Q_MAIL), anchor("1", 2, Q_FAKE)], evidence=[ext_cite(ev)],
              rank=3)]
    ctx.state.finding_meta = {f"FND-00{i}": meta(f"FND-00{i}") for i in (1, 2, 3)}
    ctx = await VerifyPhase().run(ctx)
    assert len(ctx.llm.calls) == 1 and ctx.llm.calls[0].purpose == "anchor_repair"
    assert ctx.llm.calls[0].effort == ctx.config.effort_for(PhaseName.VERIFY)
    assert ctx.state.llm_calls["verify"] == ["llm-0001"]
    by_id = {f.id: f for f in ctx.state.findings}
    assert set(by_id) == {"FND-001", "FND-003"}
    assert [a.page for a in by_id["FND-001"].doc_anchors] == [11, 6]          # repaired
    assert [a.page for a in by_id["FND-003"].doc_anchors] == [11]             # unresolved anchor dropped
    assert [f.rank for f in ctx.state.findings] == [1, 2]
    assert ctx.state.unresolved and ctx.state.unresolved[0].text.startswith("Unverified")
    rows = json.loads(ctx.run_dir.anchors.read_text(encoding="utf-8"))["rows"]
    status = {(r["owner_id"], r["anchor_index"]): r["anchor_status"] for r in rows}
    assert status[("FND-001", 1)] == "repaired" and status[("FND-002", 0)] == "unresolved"
    assert status[("FND-003", 1)] == "unresolved"
    hist = ctx.state.finding_meta["FND-003"].history[-1]
    assert hist.phase is PhaseName.VERIFY and hist.changed_fields["doc_anchors"] == [2, 1]
    assert any("unverified" in d.event for d in ctx.state.degradations)


async def test_verify_repair_refusal_is_a_degradation(tmp_path: Path) -> None:
    ctx = await ingested(tmp_path, {"verify": [FakeResponse(stop_reason="refusal", refusal_category=None)]})
    ctx.state.finding_drafts = [draft("FND-001", anchors=[anchor("1", 2, Q_FAKE)], kind="strength",
                                      disposition="no_change")]
    ctx.state.finding_meta = {"FND-001": meta("FND-001")}
    ctx = await VerifyPhase().run(ctx)
    assert ctx.state.findings == [] and any("repair call failed" in d.event for d in ctx.state.degradations)


async def test_hydration_errors_drop_the_finding(tmp_path: Path) -> None:
    ctx = await ingested(tmp_path)
    ev = add_external(ctx)
    unread = add_external(ctx, read=False, call_id="call-0002")
    a = [anchor("6.2", 11, Q_MAIL)]
    ctx.state.finding_drafts = [
        draft("FND-001", anchors=a, evidence=[ext_cite("EV-999")]),                          # not in ledger
        draft("FND-002", anchors=a, evidence=[{**ext_cite(ev), "source_type": "doc"}], rank=2),   # wrong type
        draft("FND-003", anchors=a, evidence=[ext_cite(unread)], rank=3),                     # unread only
        draft("F-7", anchors=a, evidence=[ext_cite(ev, "a paraphrase the page never said")], rank=4)]
    ctx.state.finding_meta = {x: meta(x) for x in ("FND-001", "FND-002", "FND-003", "F-7")}
    ctx = await VerifyPhase().run(ctx)
    [f] = ctx.state.findings
    assert f.id == "FND-004" and f.rank == 1                         # invalid ID renumbered
    assert f.evidence[0].quote == "The Starter plan allows up to 2,000 messages per day."   # from the ledger
    dropped = next(d for d in ctx.state.degradations if "dropped by code checks" in d.event)
    assert "EV-999" in dropped.event and "FND-002" in dropped.event and "FND-003" in dropped.event
    assert ctx.state.finding_meta["FND-001"].history[-1].note.startswith("dropped in hydration")


def test_hydrate_finding_rules(tmp_path: Path) -> None:
    led = EvidenceLedger(None, clock=FakeClock())
    tr = tool_result()
    e = led.add_external(tr, ExternalSource(url_or_citation="https://x.invalid/a", title="A", excerpt="Alpha beta.",
                                            content="c", authority=SourceAuthority.SECONDARY, read_in_full=True))
    d = draft("FND-001", anchors=[anchor("6.2", 11, Q_MAIL)], evidence=[ext_cite(e.evidence_id, "Alpha beta.")])
    f = hydrate_finding(d, led, meta("FND-001", PhaseName.ASSESS))
    assert f.provenance.phase.value == "assess" and f.evidence[0].url_or_citation == "https://x.invalid/a"
    with pytest.raises(LedgerError):
        hydrate_finding(draft("FND-002", anchors=[anchor("6.2", 11, Q_MAIL)], evidence=[ext_cite("EV-404")]),
                        led, meta("FND-002"))
    short = d.model_copy(update={"recommendation": d.recommendation.model_copy(update={"issue": "too short"})})
    with pytest.raises(ValueError, match="shorter than"):
        hydrate_finding(short, led, meta("FND-001"))
    other = d.model_copy(update={"recommendation": d.recommendation.model_copy(
        update={"supporting_evidence_ids": ["EV-777"]})})
    with pytest.raises(ValueError, match="no supporting evidence"):
        hydrate_finding(other, led, meta("FND-001"))
    with pytest.raises(ValueError, match="cannot produce findings"):
        hydrate_finding(d, led, meta("FND-001", PhaseName.PLAN))


async def test_registry_anchors_settled_after_understand(tmp_path: Path) -> None:
    ctx = await IngestPhase().run(make_ctx(tmp_path))
    ctx.registry.add(RegistryEntryDraft.model_validate({"type": "approved_decision", "doc_ref": "D-3",
                                                        "statement": "Design system front end.",
                                                        "doc_anchor": anchor("20", 3, "D-3 says the front end must "
                                                                             "use the campus design system now.")}))
    ctx.registry.add(RegistryEntryDraft.model_validate({"type": "constraint", "doc_ref": "C-9",
                                                        "statement": "Invented constraint.",
                                                        "doc_anchor": anchor("1", 2, Q_FAKE)}))
    ctx.registry.freeze()
    notes = settle_registry_anchors(ctx)
    assert len(notes) == 2 and ctx.registry.frozen
    [entry] = ctx.registry.entries()
    assert entry.registry_id == "AD-001" and entry.doc_anchor.page == 19 and entry.doc_anchor.quote.startswith("D-3")
    assert any("AD-002" in d.event for d in ctx.state.degradations)
    ctx.registry.record_iteration(1)
    assert settle_registry_anchors(ctx) == []                    # never after research recorded hashes


# ============================================================================ report


async def verified(tmp_path: Path, script: dict[str, list[FakeResponse]]) -> RunContext:
    ctx = await ingested(tmp_path, script)
    ev = add_external(ctx)
    ctx.state.finding_drafts = [
        draft("FND-001", anchors=[anchor("6.2", 11, Q_MAIL)], evidence=[ext_cite(ev)]),
        draft("FND-002", anchors=[anchor("11.3", 18, Q_A11Y)], kind="strength", disposition="no_change", rank=2,
              affected_decisions=[{"registry_id": "AD-001", "relation": "preserves", "justification": "Uses D-3."}]),
        draft("FND-003", anchors=[anchor("4.1", 6, Q_LOAD)], evidence=[ext_cite(ev)], kind="validation_need",
              disposition="needs_testing", rank=3,
              statement="Peak load is not tested; see https://made-up.invalid/blog for details.")]
    ctx.state.sound_area_drafts = [SoundAreaDraft(section_refs=["11.3"], why_sound="Verified accessibility.",
                                                  doc_anchors=[anchor("11.3", 18, Q_A11Y)], evidence_ids=["EV-404"],
                                                  related_finding_ids=["FND-002", "FND-999"])]
    ctx.state.finding_meta = {f"FND-00{i}": meta(f"FND-00{i}") for i in (1, 2, 3)}
    ctx.registry.record_iteration(1)
    ctx.state.registry_hashes = ctx.registry.hashes()
    start_manifest(ctx)
    return await VerifyPhase().run(ctx)


async def test_report_writes_valid_review_and_passes_invariants(tmp_path: Path) -> None:
    ctx = await verified(tmp_path, {"report": [REPORT_OK]})
    ctx = await ReportPhase().run(ctx)
    rd = ctx.run_dir
    data = json.loads(rd.report_json.read_text(encoding="utf-8"))
    review = Review.model_validate(data)
    assert [r.inv_id for r in check_all(data, rd.root) if not r.passed] == []
    assert review.verdict.conditions[0].finding_ids == ["FND-001"]           # unknown IDs removed
    assert len(review.verdict.conditions) == 1
    assert {"FND-003"} <= {x for u in review.unresolved for x in u.finding_ids}   # non-refinement listed
    assert review.sound_areas[0].evidence_ids == [] and review.sound_areas[0].related_finding_ids == ["FND-002"]
    assert "made-up.invalid" not in rd.report_json.read_text() and "[link removed" in review.findings[2].statement
    cited = {x for lim in review.limitations for x in lim.degradation_ids}
    assert cited == {d.id for d in review.research_log.degradations} and cited
    assert all("DEG-999" not in lim.degradation_ids for lim in review.limitations)
    outs = review.run_manifest.extra["outputs"]
    assert outs["report_json_sha256"] == report_json_sha256(data)
    assert outs["report_md_sha256"] == sha256_file(rd.report_md) and outs["ledger_sha256"] == sha256_file(rd.ledger)
    assert json.loads(rd.manifest.read_text(encoding="utf-8")) == data["run_manifest"]
    assert review.research_log.tool_calls_by_tool == {"mcp-internet-search": 1}
    assert review.research_log.sources_retrieved == 1 and review.research_log.sources_cited == 1
    md = rd.report_md.read_text(encoding="utf-8")
    for key, heading in SECTION_ORDER:
        if key not in ("header", "delta"):
            assert f"## {heading}" in md, heading


async def test_report_falls_back_to_rule_verdict_after_two_refusals(tmp_path: Path) -> None:
    refusal = FakeResponse(stop_reason="refusal", refusal_category="cyber")
    ctx = await verified(tmp_path, {"report": [refusal, refusal]})
    ctx = await ReportPhase().run(ctx)
    data = json.loads(ctx.run_dir.report_json.read_text(encoding="utf-8"))
    assert data["verdict"]["label"] == "fit_with_conditions" and "derived by rule" in data["verdict"]["rationale"]
    assert len(ctx.state.llm_calls["report"]) == 2
    assert [c.purpose for c in ctx.llm.calls if c.phase is PhaseName.REPORT] == ["verdict", "refusal_retry"]
    assert any(d["event"].startswith("verdict call failed") for d in data["research_log"]["degradations"])
    assert [r.inv_id for r in check_all(data, ctx.run_dir.root) if not r.passed] == []


async def test_invariant_violation_is_a_stage_crash_not_a_silent_fix(tmp_path: Path,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    import sit_review_agent.phases.report as report_mod
    from sit_review_agent.invariants import InvariantResult

    ctx = await verified(tmp_path, {"report": [REPORT_OK]})
    monkeypatch.setattr(report_mod, "check_all", lambda review, run_dir: [
        InvariantResult("INV-04", passed=False, problems=["planted violation"])])
    with pytest.raises(StageCrash) as info:
        await ReportPhase().run(ctx)
    assert "planted violation" in str(info.value)
    assert not ctx.run_dir.report_json.exists() and (ctx.run_dir.root / "report.invalid.json").is_file()
    assert "planted violation" in ctx.run_dir.failure.read_text(encoding="utf-8")


async def test_assemble_review_discloses_failed_tool_calls_and_caps(tmp_path: Path) -> None:
    ctx = await verified(tmp_path, {})
    from sit_review_agent.models import ResearchLogEntry

    ctx.state.tool_calls.append(ResearchLogEntry(call_id="call-0002", server="mcp-internet-search", tool_name="search",
                                                 status=ToolCallStatus.TIMEOUT, started_at="2026-10-02T09:00:00Z"))
    ctx.state.stop_reason = StopReason.of(StopReasonCode.DEADLINE, "deadline")
    review = assemble_review(ctx)
    types = [d.type for d in review.research_log.degradations]
    assert DegradationType.TOOL_ERROR in types and DegradationType.BUDGET_OR_DEADLINE_HIT in types
    from sit_review_agent.invariants import check_INV_07

    assert check_INV_07(review).passed


def test_fallback_verdict_rules() -> None:
    data = json.loads((FIXTURES / "review_example.json").read_text(encoding="utf-8"))
    r = Review.model_validate(data)
    assert fallback_verdict(r.findings, "x").label.value == "fit_with_conditions"
    crit = [r.findings[0].model_copy(update={"severity": Severity.CRITICAL})]
    assert fallback_verdict(crit, "x").label.value == "not_fit"
    assert fallback_verdict([r.findings[1]], "x").label.value == "fit"


# ============================================================================ render


def test_render_templates_threshold_and_delta(review_dict: dict[str, Any]) -> None:
    r = Review.model_validate(review_dict)
    std = render_markdown(r)
    reg = render_markdown(r, template="risk_register", min_severity=Severity.CRITICAL)
    assert "## Risk register" not in std and "Likelihood (confidence)" in reg
    assert "Appendix: findings below the reporting threshold (critical)" in reg
    assert "| FND-001 |" in reg.split("## Appendix")[1]               # the high finding moved to the appendix
    assert "## Strengths" in reg.split("## Appendix")[0]               # strengths are never filtered
    assert "https://docs.example-mail.invalid/plans" in std          # ledger URL rendered
    assert "## Changes since the previous version" not in std
    with pytest.raises(ValueError):
        render_markdown(r, template="poster")
    d = copy.deepcopy(review_dict)
    d["metadata"]["review_mode"] = "delta"
    d["metadata"]["prior_review_id"] = "REV-old"
    d["metadata"]["documents"].append({**d["metadata"]["documents"][0], "doc_id": "DOC-booking-v0",
                                       "role": "prior_version"})
    for i, f in enumerate(d["findings"]):
        f["reassessment"] = {"prior_finding_id": "FND-010", "status": "still_open", "note": None} if i == 0 else \
            {"prior_finding_id": None, "status": "new_in_update", "note": "new"}
    delta = render_markdown(Review.model_validate(d))
    assert "## Changes since the previous version" in delta and "### Still open" in delta
    assert render_markdown(r) == std                                  # deterministic


# ============================================================================ explain


async def test_explain_reads_only_the_run_directory(tmp_path: Path) -> None:
    ctx = await verified(tmp_path, {"report": [REPORT_OK]})
    ctx = await ReportPhase().run(ctx)
    ctx.sync_state()
    ctx.run_dir.state.write_text(json.dumps(ctx.state.model_dump(mode="json")), encoding="utf-8")
    copy_dir = tmp_path / "elsewhere"
    shutil.copytree(ctx.run_dir.root, copy_dir)
    rec = explain(copy_dir, "FND-001")
    assert rec.criteria[0]["id"] == "claims_and_external_constraints" and rec.criteria[0]["question"].startswith("Are")
    assert rec.anchors[0]["anchor_status"] == "resolved" and rec.evidence[0]["evidence_id"] == "EV-001"
    assert rec.tool_calls == [] and any("not in tools.jsonl" in c for c in rec.checks)
    text = format_explain(rec)
    for needle in ("FND-001", "1. Document anchors", "exact match", "EV-001", "read_before_cite ok",
                   "4. Criteria", "5. History", "llm-0002", "6. Checks", "Verdict impact: condition"):
        assert needle in text, needle
    with pytest.raises(KeyError):
        explain(copy_dir, "FND-404")
