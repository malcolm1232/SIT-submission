"""A refine answer in a re-review whose only gap is some prior-finding statuses keeps every revision
(plan D v2 runs of 2026-10-05: a complete, rule-clean answer with one of the prior statuses missing was
asked again whole, the repair was cut with seconds left and the run fell back to the unmerged shard
drafts, so v2 precision fell to 0.11 to 0.25).

Now ``split_revisions`` keeps all revisions and the one repair call is asked for the missing statuses
only (by prior ID, in the correction). A repair that returns them completes ``state.prior_statuses``;
a repair cut at the limit or failed leaves the first answer applied and the missing priors out of
``prior_statuses``, so the delta table records them as not re-examined, INV-13 holds and the report
discloses it. In the fallback branch, drafts carrying the same prior finding are merged by code, one
draft per prior ID. Fake gateway only; the previous review is a ``report.json`` in a temporary folder.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sit_review_agent.config import EffectiveConfig, load_config
from sit_review_agent.context import RunContext
from sit_review_agent.delta import NOT_RE_EXAMINED, build_prior_table, prior_findings_of
from sit_review_agent.errors import LLMSchemaError, LLMUnavailableError
from sit_review_agent.invariants import check_INV_13
from sit_review_agent.llm.gateway import FakeResponse
from sit_review_agent.models import DegradationType, ReviewMode
from sit_review_agent.phases.assess import AssessPhase
from sit_review_agent.phases.refine import RefinePhase
from sit_review_agent.phases.report import _delta_table
from sit_review_agent.states import PhaseName
from test_llm_phases import Q_LOAD, Q_NOTIFY, brief_of, make_ctx, one_shard, shard_finding
from test_refine_keep_good import N, cut, fid, good, refine_degradations, refined_event, repair_request

#: The previous review's findings (its own numbering, independent of this run's merged IDs).
PRIOR = [f"FND-{100 + i}" for i in range(1, 6)]
MISSING = [PRIOR[1], PRIOR[3]]                     # the two statuses the first answer leaves out


@pytest.fixture(scope="module")
def cfg() -> EffectiveConfig:
    return load_config()


def status(pid: str, st: str = "resolved") -> dict[str, Any]:
    return {"prior_finding_id": pid, "status": st, "note": f"{pid} checked against the update"}


def previous_run(tmp_path: Path) -> Path:
    prev = tmp_path / "previous"
    prev.mkdir()
    findings = [{"id": pid, "title": f"Prior issue {pid}", "statement": f"Statement of {pid}.",
                 "disposition": "refinement_now"} for pid in PRIOR]
    (prev / "report.json").write_text(json.dumps({"findings": findings}), encoding="utf-8")
    return prev


async def delta_many(tmp_path: Path, cfg: EffectiveConfig, refine: list[FakeResponse], *,
                     reassessment: Callable[[int], dict[str, Any] | None] = lambda i: None,
                     criterion: Callable[[int], int] = lambda i: 0) -> RunContext:
    """55 merged findings of a re-review (first 20 high, the rest medium) and the scripted refine calls;
    finding ``i`` cites the configured criterion at index ``criterion(i)``."""
    c1 = one_shard(cfg)
    crits = c1.criteria.ids()
    findings = []
    for i in range(1, N + 1):
        f = shard_finding(f"F-{i}", i, Q_LOAD if i % 2 else Q_NOTIFY, 6 if i % 2 else 11, "4.1" if i % 2 else "6.2",
                          crits[criterion(i)], n=i, title=f"Issue {i}", severity="high" if i <= 20 else "medium")
        r = reassessment(i)
        if r is not None:
            f["reassessment"] = r
        findings.append(f)
    ctx = make_ctx(tmp_path, c1, {
        PhaseName.ASSESS: [FakeResponse(parsed={"findings": findings, "sound_areas": [], "coverage": []})],
        PhaseName.REFINE: refine}, review_mode=ReviewMode.DELTA)
    ctx.state.previous_run_dir = str(previous_run(tmp_path))
    await AssessPhase().run(ctx)
    assert [f.id for f in ctx.state.finding_drafts] == [fid(i) for i in range(1, N + 1)]
    return ctx


def first_answer() -> dict[str, Any]:
    """All 55 revisions rule-clean; statuses for 3 of the 5 prior findings."""
    return {"revisions": [good(i) for i in range(1, N + 1)],
            "prior_statuses": [status(pid) for pid in PRIOR if pid not in MISSING]}


def correction(brief: str) -> str:
    return brief.split("## Correction")[1].split("# Phase: refine")[0]


async def test_a_answer_missing_only_statuses_keeps_every_revision_and_asks_for_those(
        tmp_path: Path, cfg: EffectiveConfig) -> None:
    repair = FakeResponse(parsed={"revisions": [], "prior_statuses": [status(pid) for pid in MISSING]})
    ctx = await delta_many(tmp_path, cfg, [FakeResponse(parsed=first_answer()), repair])
    await RefinePhase().run(ctx)
    text = correction(brief_of(repair_request(ctx)))
    assert f"all {N} findings were accepted and are kept exactly as you gave them" in text
    assert f"only these 2 prior finding(s) of the previous review: {', '.join(MISSING)}" in text
    assert not [pid for pid in PRIOR if pid not in MISSING and pid in text]       # exactly the missing two
    [retry] = [e for e in ctx.progress.records if e.event == "call_retry"]
    assert (retry.fields["kept"], retry.fields["retry"], retry.fields["statuses"]) == (N, 0, 2)
    s = ctx.state
    assert len(s.finding_ids.refine_fields) == N                                    # every revision applied
    assert all(s.finding_meta[fid(i)].last_call_id == "llm-0002" for i in range(1, N + 1))   # from the first call
    assert all(f.severity.value == "medium" for f in s.finding_drafts[:10])


async def test_b_the_repair_returns_the_statuses_and_prior_statuses_is_complete(
        tmp_path: Path, cfg: EffectiveConfig) -> None:
    repair = FakeResponse(parsed={"revisions": [], "prior_statuses": [status(pid, "still_open") for pid in MISSING]})
    ctx = await delta_many(tmp_path, cfg, [FakeResponse(parsed=first_answer()), repair])
    await RefinePhase().run(ctx)
    s = ctx.state
    assert sorted(p.prior_finding_id for p in s.prior_statuses) == PRIOR
    assert {p.prior_finding_id: p.status.value for p in s.prior_statuses}[MISSING[0]] == "still_open"
    assert refine_degradations(ctx) == []
    e = refined_event(ctx)
    assert (e.fields["kept"], e.fields["repaired"], e.fields["retry"], e.fields["unrefined"]) == (N, 0, 0, 0)
    table, missing = build_prior_table(prior_findings_of(s.previous_run_dir), s.finding_drafts,  # type: ignore[arg-type]
                                       s.prior_statuses)
    assert missing == [] and all(e.re_examined for e in table)


@pytest.mark.parametrize(("error", "how"), [
    (lambda: cut(None), "was cut by the stage limit"),
    (lambda: LLMSchemaError("output did not validate", call_id="llm-0003", phase="refine"),
     "did not match the output schema"),
    (lambda: LLMUnavailableError("model unreachable after retries", call_id="llm-0003", phase="refine"),
     "failed (LLMUnavailableError)"),
])
async def test_c_a_cut_or_failed_repair_applies_the_first_answer_and_discloses_the_priors(
        tmp_path: Path, cfg: EffectiveConfig, error: Any, how: str) -> None:
    ctx = await delta_many(tmp_path, cfg, [FakeResponse(parsed=first_answer()), FakeResponse(raises=error())])
    await RefinePhase().run(ctx)                                                    # does not raise
    s = ctx.state
    assert len(s.finding_ids.refine_fields) == N and [f.rank for f in s.finding_drafts] == list(range(1, N + 1))
    assert all(s.finding_meta[fid(i)].last_call_id == "llm-0002" for i in range(1, N + 1))
    assert not [r for r in ctx.progress.records if r.event == "refine_fallback"]
    assert sorted(p.prior_finding_id for p in s.prior_statuses) == sorted(set(PRIOR) - set(MISSING))
    [d] = refine_degradations(ctx)
    assert d.event == ("the refine answer left out the status of 2 prior finding(s) of the previous review; the one "
                       f"repair call, asked for those only, {how}")
    assert f"{N} of {N} refine revisions" in d.impact
    assert "not re-examined" in d.impact
    if how.startswith("was cut"):
        assert d.type is DegradationType.BUDGET_OR_DEADLINE_HIT
    else:
        assert d.type is DegradationType.OTHER
    # delta: the two are still open, not re-examined
    table, missing = build_prior_table(prior_findings_of(s.previous_run_dir), s.finding_drafts,  # type: ignore[arg-type]
                                       s.prior_statuses)
    assert missing == MISSING
    rows = {e.prior_id: e for e in table}
    assert all((rows[p].status.value, rows[p].re_examined, rows[p].note) == ("still_open", False, NOT_RE_EXAMINED)
               for p in MISSING)
    # INV-13: every prior finding has exactly one status
    review = {"metadata": {"review_mode": "delta"}, "prior_findings": [e.model_dump(mode="json") for e in table]}
    assert check_INV_13(review, prior_ids=PRIOR).passed
    # the report discloses it
    _, report_table = _delta_table(ctx, list(s.finding_drafts))                    # type: ignore[arg-type]
    assert [e.prior_id for e in report_table if not e.re_examined] == MISSING
    assert any(x.event.startswith(f"2 of {len(PRIOR)} findings of the previous review were not re-examined")
               and all(p in x.event for p in MISSING) for x in s.degradations)


async def test_a_set_that_breaks_a_rule_with_statuses_missing_is_asked_again_whole(
        tmp_path: Path, cfg: EffectiveConfig) -> None:
    """Every revision holds on its own but the set does not (two rank 1): the kept-all path is not taken."""
    revisions = [good(i) for i in range(1, N + 1)]
    revisions[1] = {**revisions[1], "rank": 1}
    first = FakeResponse(parsed={"revisions": revisions, "prior_statuses": [status(PRIOR[0])]})
    repair = FakeResponse(parsed={"revisions": [good(i) for i in range(1, N + 1)],
                                  "prior_statuses": [status(pid) for pid in PRIOR]})
    ctx = await delta_many(tmp_path, cfg, [first, repair])
    await RefinePhase().run(ctx)
    text = correction(brief_of(repair_request(ctx)))
    assert "were accepted and are kept exactly as you gave them" not in text
    assert "ranks of kept findings must be 1..55" in text
    [retry] = [e for e in ctx.progress.records if e.event == "call_retry"]
    assert "kept" not in retry.fields and "statuses" not in retry.fields
    assert sorted(p.prior_finding_id for p in ctx.state.prior_statuses) == PRIOR


#: Fallback fixture: FND-001 (resolved) and FND-003 (still_open) carry PRIOR[0]; FND-005 carries
#: PRIOR[1]; FND-007 names PRIOR[0] but is new_in_update (carries nothing). FND-001 cites the second
#: configured criterion, every other finding the first.
CARRY = {1: (PRIOR[0], "resolved"), 3: (PRIOR[0], "still_open"), 5: (PRIOR[1], "partially_addressed"),
         7: (PRIOR[0], "new_in_update")}


def carry(i: int) -> dict[str, Any] | None:
    return {"prior_finding_id": CARRY[i][0], "status": CARRY[i][1], "note": f"note {i}"} if i in CARRY else None


async def fallback_with_same_prior(tmp_path: Path, cfg: EffectiveConfig) -> tuple[RunContext, list[Any]]:
    """A refine answer that fails every attempt (no revision at all, twice): the fallback branch."""
    unusable = {"revisions": [], "prior_statuses": []}
    ctx = await delta_many(tmp_path, cfg, [FakeResponse(parsed=unusable), FakeResponse(parsed=unusable)],
                           reassessment=carry, criterion=lambda i: 1 if i == 1 else 0)
    before = [d.model_copy(deep=True) for d in ctx.state.finding_drafts]
    assert len({c for d in before for c in d.criterion_ids}) == 2                  # two distinct criteria in play
    await RefinePhase().run(ctx)
    [fb] = [r for r in ctx.progress.records if r.event == "refine_fallback"]
    assert fb.fields["invalid"] is True and fb.fields["merged_same_prior"] == 1
    return ctx, before


async def test_the_fallback_merges_drafts_that_carry_the_same_prior_id(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx, before = await fallback_with_same_prior(tmp_path, cfg)
    s = ctx.state
    got = {f.id: f for f in s.finding_drafts}
    # one carrier per prior ID; the least fixed one (still_open over resolved) is kept
    carriers: dict[str, list[str]] = {}
    for f in s.finding_drafts:
        r = f.reassessment
        if r is not None and r.prior_finding_id and r.status.value != "new_in_update":
            carriers.setdefault(r.prior_finding_id, []).append(f.id)
    assert carriers == {PRIOR[0]: [fid(3)], PRIOR[1]: [fid(5)]}
    assert fid(1) not in got and got[fid(3)].reassessment.status.value == "still_open"   # type: ignore[union-attr]
    # the removed draft's criterion moved to the keeper, without duplicates
    removed = next(d for d in before if d.id == fid(1))
    keeper_before = next(d for d in before if d.id == fid(3))
    assert got[fid(3)].criterion_ids == [*keeper_before.criterion_ids, *removed.criterion_ids]
    assert len(set(got[fid(3)].criterion_ids)) == len(got[fid(3)].criterion_ids) == 2
    assert s.finding_meta[fid(3)].criterion_ids == got[fid(3)].criterion_ids
    # ranks 1..k without a gap, in the merged order
    assert [f.rank for f in s.finding_drafts] == list(range(1, N))
    assert [f.id for f in s.finding_drafts] == [d.id for d in before if d.id != fid(1)]
    # the ID map and the history
    assert s.finding_ids.refine == {fid(1): fid(3)}
    assert "merged into FND-003 by code" in s.finding_meta[fid(1)].history[-1].note
    assert s.finding_meta[fid(3)].history[-1].note.startswith("FND-001 merged into this finding by code")
    # coverage credits the moved criterion to the keeper and names no removed finding
    rows = {r.criterion_id: r for r in s.coverage}
    assert fid(3) in rows[removed.criterion_ids[0]].finding_ids
    assert not [r for r in s.coverage if fid(1) in r.finding_ids]
    # the delta table: one row for the prior, one successor, its reading unchanged (still_open)
    table, _ = build_prior_table(prior_findings_of(s.previous_run_dir), s.finding_drafts,  # type: ignore[arg-type]
                                 s.prior_statuses)
    rows_for = [e for e in table if e.prior_id == PRIOR[0]]
    assert len(rows_for) == 1 and rows_for[0].finding_ids == [fid(3)] and rows_for[0].status.value == "still_open"
    assert [e.finding_ids for e in table if e.prior_id == PRIOR[1]] == [[fid(5)]]


async def test_the_fallback_merge_leaves_drafts_without_a_carried_prior_untouched(
        tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx, before = await fallback_with_same_prior(tmp_path, cfg)
    got = {f.id: f for f in ctx.state.finding_drafts}
    untouched = [d for d in before if d.id not in (fid(1), fid(3))]
    assert fid(7) in got and got[fid(7)].reassessment.status.value == "new_in_update"   # type: ignore[union-attr]
    for d in untouched:                                     # every field but the re-derived rank is as merged
        assert got[d.id].model_dump(exclude={"rank"}) == d.model_dump(exclude={"rank"}), d.id
        assert not [h for h in ctx.state.finding_meta[d.id].history if "by code in the refine fallback" in h.note]
