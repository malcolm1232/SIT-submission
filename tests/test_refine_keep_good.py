"""A refine answer that breaks the rules for some revisions keeps the valid ones (rehearsal of
2026-10-04: one of 55 revisions failed ``revision_problems``, the whole answer was asked again, the
repair call ran into the stage limit with 4 revisions and 51 findings were never refined).

Now ``call_model(split=...)`` keeps every revision that holds on its own and asks the one repair call
only for the failing findings (by ID, in the correction). Repair returned in full: repaired plus kept
are applied. Repair cut at the limit: the kept revisions plus whatever repaired revisions it had
finished. A revision that fails the check is never applied. The degradation states the counts. An
answer where nothing holds is asked again whole, as before. A repair call that fails on the schema
or with a transport error keeps the 54 (the run used to end at refine with no report), a persistent
refusal of it keeps them without counting refine as declined, and a failed first call still raises.
Fake gateway only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.config import EffectiveConfig, load_config
from sit_review_agent.context import RunContext
from sit_review_agent.errors import LLMDeadlineError, LLMSchemaError, LLMUnavailableError
from sit_review_agent.llm.gateway import FakeResponse
from sit_review_agent.models import DegradationType
from sit_review_agent.phases._model_calls import REFINE_FALLBACK_IMPACT
from sit_review_agent.phases.assess import AssessPhase
from sit_review_agent.phases.refine import RefinePhase
from sit_review_agent.states import PhaseName
from test_llm_phases import Q_LOAD, Q_NOTIFY, brief_of, gone, keep, make_ctx, one_shard, shard_finding
from test_refine_salvage import add_external

N = 55
BAD = 30                     # the one finding whose revision breaks a rule


@pytest.fixture(scope="module")
def cfg() -> EffectiveConfig:
    return load_config()


def fid(i: int) -> str:
    return f"FND-{i:03d}"


def good(i: int, **kw: Any) -> dict[str, Any]:
    """A keep that holds on its own and changes something (a severity for the first ten, a registry
    link for all), so every applied revision writes the finding's history."""
    kw.setdefault("reason", "bounded by the retry queue" if i <= 10 else "checked")
    kw.setdefault("affected_decisions", [{"registry_id": "AD-001", "relation": "refines", "justification": "j"}])
    return keep(fid(i), i, "medium" if i <= 10 or i > 20 else "high", "refinement_now", **kw)


def bad(i: int) -> dict[str, Any]:
    """A keep with a next step its disposition needs none of: fails ``revision_problems`` on its own."""
    return good(i, next_step={"owner": "Architecture board", "action": "Decide the owner"})


def first_answer() -> dict[str, Any]:
    return {"revisions": [bad(i) if i == BAD else good(i) for i in range(1, N + 1)]}


def cut(partial: dict[str, Any] | None) -> LLMDeadlineError:
    return LLMDeadlineError("cut at stage_limits_s.refine_end", call_id="llm-0003", partial=partial)


async def many(tmp_path: Path, cfg: EffectiveConfig, refine: list[FakeResponse]) -> RunContext:
    """55 merged findings (the first 20 high, the rest medium) and the scripted refine calls."""
    c1 = one_shard(cfg)
    crit = c1.criteria.ids()[0]
    findings = [shard_finding(f"F-{i}", i, Q_LOAD if i % 2 else Q_NOTIFY, 6 if i % 2 else 11,
                              "4.1" if i % 2 else "6.2", crit, n=i, title=f"Issue {i}",
                              severity="high" if i <= 20 else "medium")
                for i in range(1, N + 1)]
    ctx = make_ctx(tmp_path, c1, {
        PhaseName.ASSESS: [FakeResponse(parsed={"findings": findings, "sound_areas": [], "coverage": []})],
        PhaseName.REFINE: refine})
    await AssessPhase().run(ctx)
    assert [f.id for f in ctx.state.finding_drafts] == [fid(i) for i in range(1, N + 1)]
    return ctx


def refine_degradations(ctx: RunContext) -> list[Any]:
    return [d for d in ctx.state.degradations if "refine" in d.event]


def refined_event(ctx: RunContext) -> Any:
    [e] = [e for e in ctx.progress.records if e.event == "refined"]
    return e


def repair_request(ctx: RunContext) -> Any:
    first, repair = ctx.llm.calls[-2:]
    assert first.conversation_id == "refine-0" and repair.conversation_id == "refine-0-r1"
    return repair


async def test_the_repair_call_asks_only_for_the_failing_finding(tmp_path: Path, cfg: EffectiveConfig) -> None:
    fixed = FakeResponse(parsed={"revisions": [good(BAD)]})
    ctx = await many(tmp_path, cfg, [FakeResponse(parsed=first_answer()), fixed])
    await RefinePhase().run(ctx)
    brief = brief_of(repair_request(ctx))
    assert "## Correction" in brief
    assert f"{fid(BAD)} sets next_step, but refinement_now needs none" in brief
    assert "54 of the 55 findings were accepted and are kept exactly as you gave them" in brief
    assert f"one revision for each of these 1 finding(s) only: {fid(BAD)}" in brief
    assert "free ranks 30 " in brief
    assert fid(1) not in brief.split("## Correction")[1].split("# Phase: refine")[0]   # only the failing ID is named
    [retry] = [e for e in ctx.progress.records if e.event == "call_retry"]
    assert retry.fields["reason"] == "rule_repair" and (retry.fields["kept"], retry.fields["retry"]) == (54, 1)


async def test_repair_returned_in_full_applies_all_55(tmp_path: Path, cfg: EffectiveConfig) -> None:
    fixed = FakeResponse(parsed={"revisions": [good(BAD)]})
    ctx = await many(tmp_path, cfg, [FakeResponse(parsed=first_answer()), fixed])
    await RefinePhase().run(ctx)
    s = ctx.state
    assert [f.id for f in s.finding_drafts] == [fid(i) for i in range(1, N + 1)]
    assert [f.rank for f in s.finding_drafts] == list(range(1, N + 1))
    assert all(f.severity.value == "medium" for f in s.finding_drafts[:10])      # kept revisions applied
    assert s.finding_drafts[BAD - 1].affected_decisions[0].registry_id == "AD-001"
    assert s.finding_drafts[BAD - 1].next_step is None
    assert all(s.finding_meta[fid(i)].last_phase is PhaseName.REFINE for i in range(1, N + 1))
    assert s.finding_meta[fid(1)].last_call_id == "llm-0002"                     # the first call
    assert s.finding_meta[fid(BAD)].last_call_id == "llm-0003"                   # the repair call
    assert set(s.finding_ids.refine_fields) == {fid(i) for i in range(1, N + 1)}
    assert refine_degradations(ctx) == []
    assert len(s.llm_calls["refine"]) == 2
    e = refined_event(ctx)
    assert (e.fields["kept"], e.fields["repaired"], e.fields["retry"], e.fields["unrefined"]) == (54, 1, 1, 0)
    assert (e.fields["salvaged_items"], e.fields["applied"], e.fields["dropped"]) == (55, 55, 0)


async def test_repair_cut_with_nothing_applies_the_54_kept(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = await many(tmp_path, cfg, [FakeResponse(parsed=first_answer()), FakeResponse(raises=cut(None))])
    before = {f.id: f for f in ctx.state.finding_drafts}
    await RefinePhase().run(ctx)
    s = ctx.state
    got = {f.id: f for f in s.finding_drafts}
    assert all(got[fid(i)].severity.value == "medium" for i in range(1, 11))
    assert s.finding_meta[fid(1)].last_call_id == "llm-0002"
    f = got[fid(BAD)]                                        # unrefined: merged form, ranked after the refined ones
    assert f.model_dump(exclude={"rank"}) == before[fid(BAD)].model_dump(exclude={"rank"}) and f.rank == N
    assert s.finding_meta[fid(BAD)].last_phase is PhaseName.ASSESS
    assert fid(BAD) not in s.finding_ids.refine_fields and len(s.finding_ids.refine_fields) == N - 1
    assert [x.rank for x in s.finding_drafts] == list(range(1, N + 1))
    [d] = refine_degradations(ctx)
    assert d.type is DegradationType.BUDGET_OR_DEADLINE_HIT and d.event.startswith("the refine call was cut")
    assert "54 of 55 refine revisions" in d.impact and "54 kept from the first answer" in d.impact
    assert "0 repaired at the limit" in d.impact and f"1 unrefined ({fid(BAD)})" in d.impact
    assert "which was cut by the stage limit with 0 revision(s) for them" in d.impact
    assert d.impact != REFINE_FALLBACK_IMPACT
    e = refined_event(ctx)
    assert (e.fields["kept"], e.fields["repaired"], e.fields["unrefined"]) == (54, 0, 1)
    assert not [r for r in ctx.progress.records if r.event == "refine_fallback"]


async def test_repair_cut_after_the_fixed_revision_applies_all_55(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = await many(tmp_path, cfg, [FakeResponse(parsed=first_answer()),
                                     FakeResponse(raises=cut({"revisions": [good(BAD)]}))])
    await RefinePhase().run(ctx)
    s = ctx.state
    assert s.finding_drafts[BAD - 1].id == fid(BAD) and s.finding_drafts[BAD - 1].next_step is None
    assert s.finding_meta[fid(BAD)].last_call_id == "llm-0003"
    [d] = refine_degradations(ctx)
    assert "55 of 55 refine revisions" in d.impact and "1 repaired at the limit" in d.impact
    assert d.impact.endswith("; 0 unrefined")


async def test_a_repaired_revision_that_still_fails_is_not_applied(tmp_path: Path, cfg: EffectiveConfig) -> None:
    still_bad = FakeResponse(parsed={"revisions": [bad(BAD)]})
    ctx = await many(tmp_path, cfg, [FakeResponse(parsed=first_answer()), still_bad])
    await RefinePhase().run(ctx)
    s = ctx.state
    f = next(x for x in s.finding_drafts if x.id == fid(BAD))
    assert f.next_step is None and f.rank == N and s.finding_meta[fid(BAD)].last_phase is PhaseName.ASSESS
    assert len(s.finding_ids.refine_fields) == N - 1
    [d] = refine_degradations(ctx)
    assert d.type is DegradationType.OTHER
    assert d.event == ("the refine answer broke the revision rules for 1 finding(s); the one repair call, asked for "
                       "those only, returned in full")
    assert "54 of 55 refine revisions" in d.impact and "0 repaired by the one repair call" in d.impact
    assert f"1 dropped: {fid(BAD)} ({fid(BAD)} sets next_step, but refinement_now needs none)" in d.impact
    assert f"1 unrefined ({fid(BAD)})" in d.impact
    assert (refined_event(ctx).fields["unrefined"], refined_event(ctx).fields["dropped"]) == (1, 1)


async def test_a_kept_revision_with_external_evidence_reaches_the_finding(tmp_path: Path,
                                                                        cfg: EffectiveConfig) -> None:
    """Research evidence is attached to findings in refine, so a kept revision's citation of an
    external ledger entry has to survive a repair call that ends at the limit."""
    ctx = await many(tmp_path, cfg, [])
    ext = await add_external(ctx)
    cite = [{"evidence_id": ext, "source_type": "external", "quote": "Plan allows 2,000 messages per day.",
             "supports_claim": True, "derived_from": []}]
    answer = first_answer()
    answer["revisions"][0] = good(1, added_evidence=cite, reason="the vendor limit confirms it")
    ctx.llm.script["refine"].extend([FakeResponse(parsed=answer), FakeResponse(raises=cut(None))])
    await RefinePhase().run(ctx)
    f = next(x for x in ctx.state.finding_drafts if x.id == fid(1))
    assert ext in [c.evidence_id for c in f.evidence]
    [cited] = [ctx.ledger.hydrate(c) for c in f.evidence if c.evidence_id == ext]   # what verify hydrates
    assert cited.source_type.value == "external" and "2,000 messages" in cited.quote
    assert ctx.state.finding_meta[fid(1)].history[-1].changed_fields["evidence"] is not None
    assert "54 of 55 refine revisions" in refine_degradations(ctx)[0].impact


async def test_a_repair_that_resends_everything_is_merged_without_drops(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """The prompt's fixed line still says "the complete answer"; a model that sends all 55 again loses
    nothing: its revisions for kept findings are ignored, not counted as duplicates."""
    whole = {"revisions": [good(i) for i in range(1, N + 1)]}
    ctx = await many(tmp_path, cfg, [FakeResponse(parsed=first_answer()), FakeResponse(parsed=whole)])
    await RefinePhase().run(ctx)
    assert [f.rank for f in ctx.state.finding_drafts] == list(range(1, N + 1))
    assert ctx.state.finding_drafts[BAD - 1].next_step is None
    assert refine_degradations(ctx) == []
    e = refined_event(ctx)
    assert (e.fields["applied"], e.fields["dropped"], e.fields["repaired"]) == (55, 0, 1)


async def test_a_withdrawal_in_the_repair_frees_its_rank(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """The repair withdraws the failing finding instead of keeping it: the 54 kept ranks have a gap at
    30, so the merged set is re-ranked from the given order and everything is still applied."""
    withdrawn = FakeResponse(parsed={"revisions": [gone(fid(BAD), "withdraw", reason="generic")]})
    ctx = await many(tmp_path, cfg, [FakeResponse(parsed=first_answer()), withdrawn])
    await RefinePhase().run(ctx)
    s = ctx.state
    assert fid(BAD) not in {f.id for f in s.finding_drafts} and len(s.finding_drafts) == N - 1
    assert [f.rank for f in s.finding_drafts] == list(range(1, N))
    assert s.finding_ids.refine == {fid(BAD): None}
    [d] = refine_degradations(ctx)
    assert "55 of 55 refine revisions" in d.impact and "did not hold together" in d.impact and "ranks" in d.impact
    assert d.impact.endswith("; 0 unrefined")


async def test_an_answer_where_nothing_holds_is_asked_again_whole(tmp_path: Path, cfg: EffectiveConfig) -> None:
    every_bad = {"revisions": [bad(i) for i in range(1, N + 1)]}
    whole = FakeResponse(parsed={"revisions": [good(i) for i in range(1, N + 1)]})
    ctx = await many(tmp_path, cfg, [FakeResponse(parsed=every_bad), whole])
    await RefinePhase().run(ctx)
    brief = brief_of(repair_request(ctx))
    assert "accepted and are kept" not in brief
    assert [f.rank for f in ctx.state.finding_drafts] == list(range(1, N + 1))
    assert refine_degradations(ctx) == []
    assert refined_event(ctx).fields["salvaged"] is False


def schema_error() -> LLMSchemaError:
    return LLMSchemaError("output did not validate against RefineRevisionsOutput", call_id="llm-0003", phase="refine")


@pytest.mark.parametrize(("error", "how"), [
    (schema_error, "did not match the output schema"),
    (lambda: LLMUnavailableError("model unreachable after retries", call_id="llm-0003", phase="refine"),
     "failed (LLMUnavailableError)"),
])
async def test_a_failed_repair_call_keeps_the_54(tmp_path: Path, cfg: EffectiveConfig, error: Any, how: str) -> None:
    """A repair call that fails on the schema or in transport used to raise: the run ended at refine
    with no report and the 54 valid revisions only in the raw model log."""
    ctx = await many(tmp_path, cfg, [FakeResponse(parsed=first_answer()), FakeResponse(raises=error())])
    await RefinePhase().run(ctx)                                    # does not raise
    s = ctx.state
    got = {f.id: f for f in s.finding_drafts}
    assert all(got[fid(i)].severity.value == "medium" for i in range(1, 11))
    assert len(s.finding_ids.refine_fields) == N - 1 and fid(BAD) not in s.finding_ids.refine_fields
    assert s.finding_meta[fid(1)].last_call_id == "llm-0002" and got[fid(BAD)].rank == N
    [d] = refine_degradations(ctx)
    assert d.type is DegradationType.OTHER
    assert d.event == ("the refine answer broke the revision rules for 1 finding(s); the one repair call, asked for "
                       f"those only, {how}")
    assert "54 of 55 refine revisions" in d.impact and f"which {how} with 0 revision(s)" in d.impact
    assert f"1 unrefined ({fid(BAD)})" in d.impact
    assert "refine" not in s.declined_sections
    e = refined_event(ctx)
    assert (e.fields["kept"], e.fields["repaired"], e.fields["unrefined"]) == (54, 0, 1)
    [u] = [r for r in ctx.progress.records if r.event == "answer_unusable"]
    assert u.fields["error"] == type(error()).__name__ and u.fields["kept"] == 54


async def test_a_failed_first_call_still_raises(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """Only a repair call with kept items falls back; a first answer off the schema gets its one repair
    call and a second schema failure propagates as before."""
    ctx = await many(tmp_path, cfg, [FakeResponse(raises=schema_error()), FakeResponse(raises=schema_error())])
    with pytest.raises(LLMSchemaError):
        await RefinePhase().run(ctx)


async def test_a_declined_repair_keeps_the_54_and_refine_is_not_declined(tmp_path: Path,
                                                                        cfg: EffectiveConfig) -> None:
    """A persistent refusal of the repair call: the kept revisions are applied, so refine is not a
    declined section (declined_sections drives the report's "the model declined" text)."""
    refusal = FakeResponse(stop_reason="refusal")
    ctx = await many(tmp_path, cfg, [FakeResponse(parsed=first_answer()), refusal, refusal])
    await RefinePhase().run(ctx)
    s = ctx.state
    assert len(s.finding_ids.refine_fields) == N - 1
    assert "refine" not in s.declined_sections
    [d] = refine_degradations(ctx)
    assert "54 of 55 refine revisions" in d.impact and "which was declined with 0 revision(s)" in d.impact
