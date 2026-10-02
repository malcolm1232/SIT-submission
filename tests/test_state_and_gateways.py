"""Implemented infrastructure: FakeGateway, replay/record cassettes, ledger, registry, checkpoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from sit_review_agent.clock import FakeClock
from sit_review_agent.errors import (
    EffortChangedError,
    FakeScriptExhausted,
    LedgerError,
    LLMRefusalError,
    LLMTruncatedError,
    RegistryFrozenError,
    ReplayMiss,
    ResumeDriftError,
)
from sit_review_agent.llm.gateway import MAX_CACHE_BREAKPOINTS, CacheBreakpoint, FakeGateway, FakeResponse, LLMRequest
from sit_review_agent.llm.outputs import (
    DocAnchorDraft,
    EvidenceCitation,
    PlanOutput,
    RegistryEntryDraft,
)
from sit_review_agent.models import RegistryEntryType, SourceAuthority, SourceType, ToolCallStatus
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.state.checkpoint import PinnedHashes, check_drift, truncate_journal
from sit_review_agent.state.decision_registry import DecisionRegistry
from sit_review_agent.state.evidence_ledger import EvidenceLedger
from sit_review_agent.states import PhaseName
from sit_review_agent.tools.cassette import Redactor, canonical_args, cassette_key
from sit_review_agent.tools.gateway import FakeToolGateway, RecordingGateway, ReplayGateway, ToolSpec, qualify
from sit_review_agent.tools.sources import ExternalSource


def req(phase: PhaseName = PhaseName.PLAN, effort: str = "high", conv: str = "c1", schema=PlanOutput) -> LLMRequest:
    return LLMRequest(phase=phase, conversation_id=conv, system="s", messages=[{"role": "user", "content": "x"}],
                      effort=effort, max_tokens=1000, output_schema=schema)  # type: ignore[arg-type]


async def test_fake_gateway_parses_and_logs(tmp_path: Path) -> None:
    rd = RunDir(tmp_path / "r").create()
    gw = FakeGateway({PhaseName.PLAN: [FakeResponse(parsed={"questions": [], "criteria_skipped": []})]}, run_dir=rd)
    res = await gw.call(req())
    assert isinstance(res.parsed, PlanOutput) and res.model == "claude-opus-5-5"
    assert res.assistant_message()["content"][0]["type"] == "thinking"
    assert JsonlWriter(rd.llm_log).read()[0]["phase"] == "plan"
    with pytest.raises(FakeScriptExhausted):
        await gw.call(req())


async def test_fake_gateway_typed_errors_and_effort_guard() -> None:
    gw = FakeGateway({PhaseName.ASSESS: [FakeResponse(stop_reason="refusal", refusal_category=None),
                                         FakeResponse(stop_reason="max_tokens"), FakeResponse(text="ok")]})
    with pytest.raises(LLMRefusalError) as info:
        await gw.call(req(PhaseName.ASSESS, schema=None))
    assert info.value.category is None and gw.refusals()[0]["stage"] == "assess"
    with pytest.raises(LLMTruncatedError):
        await gw.call(req(PhaseName.ASSESS, schema=None))
    with pytest.raises(EffortChangedError):
        await gw.call(req(PhaseName.ASSESS, effort="max", schema=None))


def test_cache_breakpoint_limit() -> None:
    with pytest.raises(ValueError):
        LLMRequest(phase=PhaseName.PLAN, conversation_id="c", system="s", messages=[], effort="high", max_tokens=1,
                   cache_breakpoints=tuple(CacheBreakpoint(0, i) for i in range(MAX_CACHE_BREAKPOINTS)))


def test_cassette_key_canonicalisation_and_redaction() -> None:
    a = cassette_key("srv", "search", {"query": "  HNSW   Latency ", "limit": 10, "request_id": "x1"})
    b = cassette_key("srv", "search", {"limit": 10, "query": "hnsw latency"})
    assert a == b
    assert canonical_args({"q": "A  B", "nested": {"timestamp": 1, "k": "v"}}) == {"q": "a b", "nested": {"k": "v"}}
    red = Redactor(["sekret/key"])
    assert red.deep({"h": "Bearer sekret/key", "u": "x?k=sekret%2Fkey"}) == {"h": "Bearer ***REDACTED***",
                                                                             "u": "x?k=***REDACTED***"}


async def test_record_then_strict_replay(tmp_path: Path) -> None:
    spec = ToolSpec(server="mcp-internet-search", name="search", description="d", input_schema={"type": "object"})
    name = qualify(spec.server, spec.name)
    fake = FakeToolGateway([spec], {name: lambda args: f"results for {args['query']} key=sekret"})
    rec = RecordingGateway(fake, tmp_path, Redactor(["sekret"]), clock=FakeClock())
    await rec.list_tools()
    live = await rec.call(name, {"query": "Room Booking"})
    assert live.ok
    replay = ReplayGateway(tmp_path, strict=True)
    assert [t.qualified_name for t in await replay.list_tools()] == [name]
    again = await replay.call(name, {"query": "room   booking"})
    assert again.replayed and again.text == "results for Room Booking key=***REDACTED***"
    with pytest.raises(ReplayMiss):
        await replay.call(name, {"query": "something else"})
    lenient = await ReplayGateway(tmp_path, strict=False).call(name, {"query": "something else"})
    assert lenient.status is ToolCallStatus.OK and lenient.error_class.value == "replay_miss"


async def test_ledger_is_append_only_and_hydrates(tmp_path: Path) -> None:
    rd = RunDir(tmp_path / "r").create()
    led = EvidenceLedger(rd, clock=FakeClock())
    spec_name = qualify("mcp-internet-search", "search")
    fake = FakeToolGateway([], {spec_name: lambda a: "Plan allows 2,000 messages per day."})
    res = await fake.call(spec_name, {"query": "q"})
    src = ExternalSource(url_or_citation="https://docs.example.invalid/limits", title="Limits",
                         excerpt="Plan allows 2,000 messages per day.", content="Plan allows 2,000 messages per day.",
                         authority=SourceAuthority.PRIMARY_OFFICIAL, read_in_full=True)
    e1 = led.add_external(res, src)
    e2 = led.add_doc(doc_id="DOC-x", page=3, section_ref="6.2", excerpt="no daily sending limit")
    e3 = led.add_inference(statement="5,000 > 2,000", derived_from=[e1.evidence_id, e2.evidence_id])
    assert [e.evidence_id for e in led] == ["EV-001", "EV-002", "EV-003"]
    assert e1.tool is not None and e1.tool.call_id == res.call_id
    item = led.hydrate(EvidenceCitation(evidence_id="EV-001", source_type=SourceType.EXTERNAL, quote="2,000 messages",
                                        supports_claim=True, derived_from=[]))
    assert item.url_or_citation == src.url_or_citation and item.retrieved_at == res.started_at
    with pytest.raises(LedgerError):
        led.hydrate(EvidenceCitation(evidence_id="EV-999", source_type=SourceType.DOC, quote="x",
                                     supports_claim=True, derived_from=[]))
    with pytest.raises(LedgerError):
        led.add_inference(statement="x", derived_from=["EV-404"])
    offset = led.offset()
    led.add_doc(doc_id="DOC-x", page=1, section_ref="1", excerpt="later")
    assert len(EvidenceLedger.load(rd)) == 4 and len(EvidenceLedger.load(rd, upto=offset)) == 3
    truncate_journal(rd.ledger_journal, offset)
    assert len(EvidenceLedger.load(rd)) == 3 and e3.url_or_citation == "inference:EV-003"


def test_registry_freezes_and_hashes() -> None:
    reg = DecisionRegistry()
    anchor = DocAnchorDraft(doc_id="DOC-x", section_ref="6", requirement_ids=["D-1"],
                            quote="D-1 Confirmed: reservations remain in the existing PostgreSQL cluster", page=6)
    e = reg.add(RegistryEntryDraft(type=RegistryEntryType.APPROVED_DECISION, doc_ref="D-1", statement="Keep PG.",
                                   doc_anchor=anchor))
    assert e.registry_id == "AD-001"
    h = reg.freeze()
    with pytest.raises(RegistryFrozenError):
        reg.add(RegistryEntryDraft(type=RegistryEntryType.CONSTRAINT, doc_ref="C-1", statement="x", doc_anchor=anchor))
    assert reg.record_iteration(1).sha256 == h == reg.sha256()


def test_checkpoint_drift_refused() -> None:
    from sit_review_agent.state.checkpoint import Checkpoint, JournalOffsets
    from sit_review_agent.state.run_state import RunState

    pinned = PinnedHashes(effective_config="a" * 64, prompts_bundle="b" * 64, canonical_text="c" * 64)
    ck = Checkpoint(run_id="r", phase=PhaseName.PLAN, seq=3, created_utc="2026-10-02T09:00:00Z", hashes=pinned,
                    offsets=JournalOffsets(llm_jsonl=0, tools_jsonl=0, ledger_jsonl=0),
                    state=RunState(run_id="r", created_utc="2026-10-02T09:00:00Z"))
    assert check_drift(ck, pinned) == []
    changed = pinned.model_copy(update={"prompts_bundle": "d" * 64})
    with pytest.raises(ResumeDriftError) as info:
        check_drift(ck, changed)
    assert int(info.value.exit_code) == 5
    assert check_drift(ck, changed, accept_drift=True)
