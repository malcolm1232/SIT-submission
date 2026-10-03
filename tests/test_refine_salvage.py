"""A refine call cut at its stage limit applies the revisions it had finished (sit_sample_ui_1 defect 1).

Planner ruling of 2026-10-03: every finished revision in ``LLMDeadlineError.partial`` that passes
``revision_problems()`` is applied through ``apply_revisions``; findings without a revision keep their
merged form; the refine-cut degradation says how many of how many revisions were applied and that the
rest of the findings were not refined. A salvage that fails validation as a whole (a merge whose
target the cut lost, kept ranks with gaps) degrades to its independent revisions (keeps, withdrawals,
merges into a salvaged keep; ranks re-derived from the applied order). Evidence of an applied revision
reaches the ledger and the finding. A cut with nothing finished behaves as before. Fake gateway only.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

import pytest
from test_llm_phases import Q_LOAD, Q_NOTIFY, gone, keep, make_ctx, one_shard, shard_finding

from sit_review_agent.config import EffectiveConfig, load_config
from sit_review_agent.context import RunContext
from sit_review_agent.errors import LLMDeadlineError
from sit_review_agent.llm.gateway import FakeResponse
from sit_review_agent.models import DegradationType, SourceAuthority
from sit_review_agent.phases._model_calls import REFINE_FALLBACK_IMPACT
from sit_review_agent.phases.assess import AssessPhase
from sit_review_agent.phases.refine import RefinePhase
from sit_review_agent.states import PhaseName
from sit_review_agent.tools.gateway import FakeToolGateway, qualify
from sit_review_agent.tools.sources import ExternalSource

N = 20


@pytest.fixture(scope="module")
def cfg() -> EffectiveConfig:
    return load_config()


def fid(i: int) -> str:
    return f"FND-{i:03d}"


def cut_error(partial: dict[str, Any] | None) -> LLMDeadlineError:
    return LLMDeadlineError("cut at stage_limits_s.refine_end", call_id="llm-0099", partial=partial)


async def twenty(tmp_path: Path, cfg: EffectiveConfig, partial: dict[str, Any] | None) -> RunContext:
    """Twenty merged findings (FND-001..FND-010 high, FND-011..FND-020 medium) and a refine call cut
    with ``partial`` finished."""
    c1 = one_shard(cfg)
    crit = c1.criteria.ids()[0]
    findings = [shard_finding(f"F-{i}", i, Q_LOAD if i % 2 else Q_NOTIFY, 6 if i % 2 else 11,
                              "4.1" if i % 2 else "6.2", crit, n=i, title=f"Issue {i}",
                              severity="high" if i <= 10 else "medium")
                for i in range(1, N + 1)]
    ctx = make_ctx(tmp_path, c1, {
        PhaseName.ASSESS: [FakeResponse(parsed={"findings": findings, "sound_areas": [], "coverage": []})],
        PhaseName.REFINE: [FakeResponse(raises=cut_error(partial))]})
    await AssessPhase().run(ctx)
    assert [f.id for f in ctx.state.finding_drafts] == [fid(i) for i in range(1, N + 1)]
    return ctx


def cut_degradation(ctx: RunContext) -> Any:
    [d] = [d for d in ctx.state.degradations if d.event.startswith("the refine call was cut")]
    assert d.type is DegradationType.BUDGET_OR_DEADLINE_HIT
    return d


def refined_event(ctx: RunContext) -> Any:
    [e] = [e for e in ctx.progress.records if e.event == "refined"]
    return e


async def test_cut_after_10_of_20_revisions_applies_the_10(tmp_path: Path, cfg: EffectiveConfig) -> None:
    revs = [keep(fid(i), i, "medium" if i <= 5 else "high", "refinement_now",
                 reason="bounded by the retry queue" if i <= 5 else "checked") for i in range(1, 11)]
    ctx = await twenty(tmp_path, cfg, {"revisions": revs})
    before = {f.id: f for f in ctx.state.finding_drafts}
    await RefinePhase().run(ctx)
    s = ctx.state
    got = {f.id: f for f in s.finding_drafts}
    assert set(got) == set(before)
    for i in range(1, 6):                                   # five severity changes applied, with history
        f = got[fid(i)]
        assert f.severity is not None and f.severity.value == "medium"
        assert s.finding_meta[fid(i)].last_phase is PhaseName.REFINE
        assert s.finding_meta[fid(i)].history[-1].changed_fields["severity"] == ["high", "medium"]
        assert s.finding_meta[fid(i)].last_call_id == "llm-0099"
    for i in range(11, N + 1):                              # the other ten keep their merged form
        assert got[fid(i)].model_dump(exclude={"rank"}) == before[fid(i)].model_dump(exclude={"rank"})
        assert s.finding_meta[fid(i)].last_phase is PhaseName.ASSESS
        assert fid(i) not in s.finding_ids.refine_fields
    assert [f.rank for f in s.finding_drafts] == list(range(1, N + 1))
    assert [f.id for f in s.finding_drafts[10:]] == [fid(i) for i in range(11, N + 1)]
    d = cut_degradation(ctx)
    assert "10 of 20" in d.impact and "not refined" in d.impact
    assert d.impact != REFINE_FALLBACK_IMPACT
    e = refined_event(ctx)
    assert e.fields["salvaged"] is True
    assert (e.fields["salvaged_items"], e.fields["applied"], e.fields["dropped"]) == (10, 10, 0)
    assert not [r for r in ctx.progress.records if r.event == "refine_fallback"]


async def test_merge_whose_target_the_cut_lost_keeps_both(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """FND-002 merges into FND-015, whose revision was not finished: the set fails as a whole, the
    merge is dropped, both findings stand, and FND-001's keep is still applied."""
    revs = [keep(fid(1), 1, "high", "governance_decision", reason="needs an owner decision",
                 next_step={"owner": "Architecture board", "action": "Decide the notification owner"}),
            gone(fid(2), "merge", fid(15), reason="same issue")]
    ctx = await twenty(tmp_path, cfg, {"revisions": revs})
    await RefinePhase().run(ctx)
    s = ctx.state
    ids = {f.id for f in s.finding_drafts}
    assert {fid(2), fid(15)} <= ids and len(ids) == N
    assert s.finding_ids.refine == {}
    assert next(f for f in s.finding_drafts if f.id == fid(1)).disposition.value == "governance_decision"
    assert [f.rank for f in s.finding_drafts] == list(range(1, N + 1))
    d = cut_degradation(ctx)
    assert "1 of 20" in d.impact and "merge" in d.impact
    e = refined_event(ctx)
    assert (e.fields["salvaged_items"], e.fields["applied"], e.fields["dropped"]) == (2, 1, 1)


async def test_merge_into_a_salvaged_keep_is_applied(tmp_path: Path, cfg: EffectiveConfig) -> None:
    revs = [keep(fid(1), 1, "high", "refinement_now"), gone(fid(2), "merge", fid(1), reason="same issue")]
    ctx = await twenty(tmp_path, cfg, {"revisions": revs})
    await RefinePhase().run(ctx)
    s = ctx.state
    assert fid(2) not in {f.id for f in s.finding_drafts} and len(s.finding_drafts) == N - 1
    assert s.finding_ids.refine == {fid(2): fid(1)}
    assert [f.rank for f in s.finding_drafts] == list(range(1, N))
    assert "2 of 20" in cut_degradation(ctx).impact


async def test_ranks_with_gaps_keep_the_independent_revisions(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """Kept ranks 4 and 2 (1 and 3 lost with the cut): the set fails as a whole; the keeps and the
    withdrawal are applied, ranks re-derived from the salvaged order, the rest after them."""
    revs = [keep(fid(1), 4, "high", "refinement_now"), gone(fid(2), "withdraw", reason="generic"),
            keep(fid(3), 2, "high", "refinement_now")]
    ctx = await twenty(tmp_path, cfg, {"revisions": revs})
    await RefinePhase().run(ctx)
    s = ctx.state
    assert [f.id for f in s.finding_drafts[:2]] == [fid(3), fid(1)]
    assert fid(2) not in {f.id for f in s.finding_drafts}
    assert [f.rank for f in s.finding_drafts] == list(range(1, N))
    assert s.finding_ids.refine == {fid(2): None}
    assert "3 of 20" in cut_degradation(ctx).impact
    e = refined_event(ctx)
    assert (e.fields["salvaged_items"], e.fields["applied"], e.fields["dropped"]) == (3, 3, 0)


async def add_external(ctx: RunContext) -> str:
    """One external ledger entry, as research adds it; returns its ID."""
    name = qualify("mcp-internet-search", "search")
    fake = FakeToolGateway([], {name: lambda a: "Plan allows 2,000 messages per day."})
    res = await fake.call(name, {"query": "q"})
    src = ExternalSource(url_or_citation="https://docs.example.invalid/limits", title="Limits",
                         excerpt="Plan allows 2,000 messages per day.", content="Plan allows 2,000 messages per day.",
                         authority=SourceAuthority.PRIMARY_OFFICIAL, read_in_full=True)
    return ctx.ledger.add_external(res, src).evidence_id


async def test_applied_evidence_reaches_the_ledger_and_the_finding(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = await twenty(tmp_path, cfg, None)
    ext = await add_external(ctx)
    added = [{"evidence_id": ext, "source_type": "external", "quote": "Plan allows 2,000 messages per day.",
              "supports_claim": True, "derived_from": []},
             {"evidence_id": "NEW-1", "source_type": "doc", "quote": Q_NOTIFY, "supports_claim": True,
              "derived_from": []}]
    revs = [keep(fid(1), 1, "high", "refinement_now", reason="the vendor limit confirms it", added_evidence=added)]
    ctx.llm.script["refine"] = deque([FakeResponse(raises=cut_error({"revisions": revs}))])
    [notify] = [e.evidence_id for e in ctx.ledger if e.excerpt == Q_NOTIFY]   # cited by the even findings
    assert notify not in {c.evidence_id for c in ctx.state.finding_drafts[0].evidence}
    await RefinePhase().run(ctx)
    f = next(x for x in ctx.state.finding_drafts if x.id == fid(1))
    cited = [c.evidence_id for c in f.evidence]
    assert ext in cited
    assert notify in cited                                  # the document quote reuses its ledger entry
    assert [e.evidence_id for e in ctx.ledger if e.excerpt == Q_NOTIFY] == [notify]   # no duplicate entry
    assert "NEW-1" not in cited
    assert "1 of 20" in cut_degradation(ctx).impact


async def test_a_salvaged_revision_that_breaks_the_rules_is_dropped(tmp_path: Path, cfg: EffectiveConfig) -> None:
    revs = [keep(fid(1), 1, "high", "refinement_now", next_step={"owner": "x", "action": "y"}),  # needs none
            keep(fid(3), 2, "medium", "refinement_now", reason="bounded"),
            {"finding_id": fid(4), "action": "keep"}]                                         # not a revision
    ctx = await twenty(tmp_path, cfg, {"revisions": revs})
    await RefinePhase().run(ctx)
    got = {f.id: f for f in ctx.state.finding_drafts}
    assert got[fid(1)].next_step is None and got[fid(3)].severity.value == "medium"
    assert ctx.state.finding_meta[fid(1)].last_phase is PhaseName.ASSESS
    assert "1 of 20" in cut_degradation(ctx).impact
    e = refined_event(ctx)
    assert (e.fields["salvaged_items"], e.fields["applied"], e.fields["dropped"]) == (3, 1, 2)


@pytest.mark.parametrize("partial", [None, {"revisions": []}])
async def test_cut_with_nothing_finished_keeps_the_old_fallback(tmp_path: Path, cfg: EffectiveConfig,
                                                               partial: dict[str, Any] | None) -> None:
    ctx = await twenty(tmp_path, cfg, partial)
    before = [f.model_dump() for f in ctx.state.finding_drafts]
    meta = dict(ctx.state.finding_meta)
    await RefinePhase().run(ctx)
    assert [f.model_dump() for f in ctx.state.finding_drafts] == before
    assert ctx.state.finding_meta == meta
    assert cut_degradation(ctx).impact == REFINE_FALLBACK_IMPACT
    assert [r.fields["cut"] for r in ctx.progress.records if r.event == "refine_fallback"] == [True]
    assert not [r for r in ctx.progress.records if r.event == "refined"]
