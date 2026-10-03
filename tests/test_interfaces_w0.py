"""W0 interface change of the latency redesign (docs/design/latency_and_demo_design.md sections 4, 5, 7).

Pins the new frozen types before any workstream builds on them: revision-only refine output, the
verdict-only report output, the salvaged partial answer on ``LLMDeadlineError``, the stage 1 group
and its transition rules, the checkpoint ordinal and the run's elapsed seconds.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from sit_eval.usage import from_call_log
from sit_review_agent.errors import LLMDeadlineError, LLMError, LLMTimeoutError
from sit_review_agent.llm.gateway import Usage, unrecorded_usage
from sit_review_agent.llm.outputs import (
    FindingDraft,
    FindingRevisionDraft,
    RefineRevisionsOutput,
    RevisionAction,
    VerdictOutput,
    apply_revisions,
    llm_facing_schema,
    revision_problems,
)
from sit_review_agent.llm.usage_budget import add_usage
from sit_review_agent.manifest import journal_usage
from sit_review_agent.report.coverage import _state
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.state.checkpoint import (
    Checkpoint,
    JournalOffsets,
    PinnedHashes,
    checkpoint_file_order,
    latest_checkpoint,
    load_checkpoint,
    write_checkpoint,
)
from sit_review_agent.state.run_state import Budget, RunState
from sit_review_agent.states import (
    PHASE_ORDER,
    STAGE_1_DEPENDS,
    STAGE_MEMBERS,
    STAGE_ON_CAP,
    STAGE_ORDER,
    STAGE_TRANSITIONS,
    PhaseName,
    Stage,
    stage1_close,
    stage1_ready,
    stage_of,
)

# --------------------------------------------------------------------------- refine revisions


def _keep(fid: str, rank: int | None, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "finding_id": fid, "action": "keep", "merge_into": None, "rank": rank, "severity": "high",
        "disposition": "refinement_now", "affected_decisions": [], "added_evidence": [], "next_step": None,
        "reason": "kept",
    }
    base.update(kw)
    return base


def _gone(fid: str, action: str, into: str | None = None, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "finding_id": fid, "action": action, "merge_into": into, "rank": None, "severity": None,
        "disposition": None, "affected_decisions": [], "added_evidence": [], "next_step": None, "reason": action,
    }
    base.update(kw)
    return base


def _out(*revs: dict[str, Any]) -> RefineRevisionsOutput:
    return RefineRevisionsOutput.model_validate({"revisions": list(revs)})


IDS = ["FND-001", "FND-002", "FND-003"]


def test_refine_revisions_round_trip() -> None:
    raw = {"revisions": [
        _keep("FND-001", 1, affected_decisions=[{"registry_id": "AD-002", "relation": "challenges",
                                                 "justification": "contradicts the approved queue"}],
              added_evidence=[{"evidence_id": "EV-007", "source_type": "external", "quote": "p99 is 40 ms",
                               "supports_claim": True, "derived_from": []}]),
        _gone("FND-002", "merge", "FND-001"),
        _gone("FND-003", "withdraw"),
    ]}
    out = RefineRevisionsOutput.model_validate(raw)
    assert out.revisions[1].action is RevisionAction.MERGE
    again = RefineRevisionsOutput.model_validate_json(out.model_dump_json())
    # prior_statuses (2026-10-03, delta reviews) is optional and dumps as [].
    assert again == out and json.loads(out.model_dump_json()) == {**raw, "prior_statuses": []}
    assert revision_problems(out, IDS) == []


def test_refine_revisions_never_carry_finding_text() -> None:
    """A revision is a patch: the finding body (title, statement, anchors, recommendation) is not in it."""
    fields = set(FindingRevisionDraft.model_fields)
    assert not fields & {"title", "statement", "doc_anchors", "recommendation", "evidence", "kind", "category"}
    with pytest.raises(ValueError):
        _out(_keep("FND-001", 1, title="re-emitted"))


def test_llm_facing_schemas_are_closed_and_offer_no_not_assessed() -> None:
    rs = llm_facing_schema(RefineRevisionsOutput)
    rev = rs["$defs"]["FindingRevisionDraft"]
    assert rev["additionalProperties"] is False
    assert set(rev["required"]) == set(FindingRevisionDraft.model_fields)    # every key required, null explicit
    assert rs["$defs"]["RevisionAction"]["enum"] == ["keep", "merge", "withdraw"]
    vs = llm_facing_schema(VerdictOutput)
    assert set(vs["properties"]) == {"verdict"}
    assert "not_assessed" not in vs["$defs"]["AssessedVerdictLabel"]["enum"]


def test_verdict_output_round_trip_and_rejects_old_fields() -> None:
    v = {"verdict": {"label": "fit_with_conditions", "rationale": "r", "confidence": 0.7,
                     "conditions": [{"text": "fix FND-001", "finding_ids": ["FND-001"]}],
                     "per_objective": [], "what_would_change_it": None}}
    out = VerdictOutput.model_validate(v)
    assert json.loads(out.model_dump_json()) == v
    with pytest.raises(ValueError):
        VerdictOutput.model_validate({**v, "unresolved": [], "limitations": []})
    with pytest.raises(ValueError):
        VerdictOutput.model_validate({"verdict": {**v["verdict"], "label": "not_assessed"}})


@pytest.mark.parametrize(("revs", "needle"), [
    ((_keep("FND-001", 1), _keep("FND-002", 2), _keep("FND-003", 3), _keep("FND-009", 4)),
     "unknown finding FND-009"),
    ((_keep("FND-001", 1), _gone("FND-002", "merge", "FND-002"), _keep("FND-003", 2)),
     "FND-002 merges into itself"),
    ((_keep("FND-001", 1), _gone("FND-002", "merge", "FND-003"), _gone("FND-003", "merge", "FND-002")),
     "merge into FND-003, which is not kept"),
    ((_keep("FND-001", 1), _gone("FND-002", "withdraw", severity="critical"), _keep("FND-003", 2)),
     "FND-002 is withdraw but sets severity"),
    ((_keep("FND-001", 1), _gone("FND-002", "merge", "FND-009"), _keep("FND-003", 2)),
     "merge into unknown finding FND-009"),
    ((_keep("FND-001", 1), _gone("FND-002", "merge", None), _keep("FND-003", 2)),
     "FND-002 is merge without merge_into"),
    ((_keep("FND-001", 1, merge_into="FND-003"), _keep("FND-002", 2), _keep("FND-003", 3)),
     "FND-001 is keep but sets merge_into"),
    ((_keep("FND-001", 1), _keep("FND-002", 2)), "no revision for FND-003"),
    ((_keep("FND-001", 1), _keep("FND-002", 2), _keep("FND-003", 3), _gone("FND-003", "withdraw")),
     "FND-003 has 2 revisions"),
    ((_keep("FND-001", 1), _keep("FND-002", 1), _keep("FND-003", 3)), "ranks of kept findings must be 1..3"),
    ((_keep("FND-001", 1), _keep("FND-002", None), _keep("FND-003", 3)), "FND-002 is keep without rank"),
    ((_keep("FND-001", 1), _keep("FND-002", 2, disposition=None), _keep("FND-003", 3)),
     "FND-002 is keep without disposition"),
    ((_keep("FND-001", 1), _gone("FND-002", "withdraw", added_evidence=[
        {"evidence_id": "EV-001", "source_type": "external", "quote": None, "supports_claim": True,
         "derived_from": []}]), _keep("FND-003", 2)), "FND-002 is withdraw but sets added_evidence"),
])
def test_revision_problems_adversarial(revs: tuple[dict[str, Any], ...], needle: str) -> None:
    problems = revision_problems(_out(*revs), IDS)
    assert any(needle in p for p in problems), problems


def test_revision_problems_two_merges_cycle_three_way() -> None:
    out = _out(_gone("FND-001", "merge", "FND-002"), _gone("FND-002", "merge", "FND-003"),
               _gone("FND-003", "merge", "FND-001"))
    problems = revision_problems(out, IDS)
    assert sum("which is not kept" in p for p in problems) == 3, problems


def test_keep_with_null_severity_is_a_final_value_not_a_change() -> None:
    """For ``keep`` every field states the final value; a null severity is legal (finding kinds
    without a severity) and is applied as null, never read as "unchanged"."""
    out = _out(_keep("FND-001", 1, severity=None), _keep("FND-002", 2), _keep("FND-003", 3))
    assert revision_problems(out, IDS) == []
    assert out.revisions[0].severity is None


# --------------------------------------------------------------------------- LLMDeadlineError salvage


def test_deadline_error_carries_partial_answer_and_estimated_usage() -> None:
    est = Usage(input_tokens=20_000, output_tokens=9_000)
    partial = {"findings": [{"id": "FND-001"}, {"id": "FND-002"}, {"id": "FND-003"}]}
    err = LLMDeadlineError("cut after 265 s", call_id="llm-0004", phase="assess",
                           partial=partial, estimated_usage=est)
    assert isinstance(err, LLMTimeoutError) and isinstance(err, LLMError) and err.exit_code == 3
    assert err.partial == partial and err.salvaged_items == 3
    assert err.estimated_usage == est
    assert err.usage is None            # an estimate is never presented as measured usage


def test_deadline_error_defaults_keep_old_semantics() -> None:
    billed = Usage(input_tokens=5, output_tokens=7)
    err = LLMDeadlineError("cut", usage=billed)
    assert err.usage == billed and err.partial is None and err.estimated_usage is None
    assert err.salvaged_items == 0


# --------------------------------------------------------------------------- stage 1 group


def test_stage_order_keeps_the_eight_phase_names() -> None:
    assert [p for s in STAGE_ORDER for p in STAGE_MEMBERS[s]] == [
        PhaseName.INGEST, PhaseName.UNDERSTAND, PhaseName.PLAN, PhaseName.RESEARCH, PhaseName.ASSESS,
        PhaseName.REFINE, PhaseName.VERIFY, PhaseName.REPORT]
    assert sorted(p for s in STAGE_ORDER for p in STAGE_MEMBERS[s]) == sorted(PHASE_ORDER)
    assert STAGE_MEMBERS[Stage.STAGE_1] == (PhaseName.UNDERSTAND, PhaseName.PLAN, PhaseName.RESEARCH,
                                           PhaseName.ASSESS)
    assert all(stage_of(p) in STAGE_ORDER for p in PHASE_ORDER)
    assert stage_of(PhaseName.ASSESS) is Stage.STAGE_1 and stage_of(PhaseName.REFINE) is Stage.REFINE


def test_stage_transitions_move_forward_and_caps_reach_verify() -> None:
    order = list(STAGE_ORDER)
    assert all(order.index(b) == order.index(a) + 1 for a, b in STAGE_TRANSITIONS.items() if b is not None)
    assert STAGE_TRANSITIONS[Stage.REPORT] is None
    assert all(order.index(b) > order.index(a) for a, b in STAGE_ON_CAP.items())
    assert STAGE_ON_CAP[Stage.STAGE_1] is Stage.VERIFY and STAGE_ON_CAP[Stage.REFINE] is Stage.VERIFY


def test_stage1_start_runs_understand_plan_and_assess_together() -> None:
    assert stage1_ready({}, set()) == {PhaseName.UNDERSTAND, PhaseName.PLAN, PhaseName.ASSESS}
    assert STAGE_1_DEPENDS[PhaseName.RESEARCH] == frozenset({PhaseName.UNDERSTAND, PhaseName.PLAN})


@pytest.mark.parametrize("first", [PhaseName.UNDERSTAND, PhaseName.PLAN])
def test_research_waits_for_both_understand_and_plan_in_any_order(first: PhaseName) -> None:
    second = PhaseName.PLAN if first is PhaseName.UNDERSTAND else PhaseName.UNDERSTAND
    running = {PhaseName.UNDERSTAND, PhaseName.PLAN, PhaseName.ASSESS}
    assert stage1_ready({first: "done"}, running - {first}) == set()
    assert stage1_ready({first: "done", second: "done"}, {PhaseName.ASSESS}) == {PhaseName.RESEARCH}
    # assess may end first; it never unblocks research
    assert stage1_ready({PhaseName.ASSESS: "done"}, {first, second}) == set()


def test_research_starts_after_a_cut_plan() -> None:
    """A cut plan ends with its deadline fallback (document-only questions); research may still run."""
    assert stage1_ready({PhaseName.UNDERSTAND: "done", PhaseName.PLAN: "cut"},
                        {PhaseName.ASSESS}) == {PhaseName.RESEARCH}


def test_stage1_close_cuts_running_and_skips_unstarted() -> None:
    ended = {PhaseName.UNDERSTAND: "done"}
    closed = stage1_close(ended, running={PhaseName.PLAN, PhaseName.ASSESS})
    assert closed == {PhaseName.UNDERSTAND: "done", PhaseName.PLAN: "cut", PhaseName.ASSESS: "cut",
                      PhaseName.RESEARCH: "skipped"}
    assert ended == {PhaseName.UNDERSTAND: "done"}          # input not mutated
    assert stage1_ready(closed, set()) == set()


def test_stage1_rejects_non_members() -> None:
    with pytest.raises(ValueError, match="not a stage 1 member"):
        stage1_ready({PhaseName.REFINE: "done"}, set())
    with pytest.raises(ValueError, match="both ended and running"):
        stage1_close({PhaseName.PLAN: "done"}, running={PhaseName.PLAN})


# --------------------------------------------------------------------------- checkpoint ordinal


def _ckpt(phase: PhaseName, ordinal: int | None = None) -> Checkpoint:
    kw: dict[str, Any] = {} if ordinal is None else {"ordinal": ordinal}
    return Checkpoint(run_id="r1", phase=phase, seq=PHASE_ORDER.index(phase) + 1, created_utc="2026-10-03T00:00:00Z",
                      hashes=PinnedHashes(effective_config="a", prompts_bundle="b", canonical_text="c"),
                      offsets=JournalOffsets(llm_jsonl=0, tools_jsonl=0, ledger_jsonl=0),
                      state=RunState(run_id="r1", created_utc="2026-10-03T00:00:00Z"), **kw)


def test_latest_checkpoint_is_chosen_by_ordinal_not_file_name(tmp_path) -> None:
    rd = RunDir(tmp_path / "run").create()
    # stage 1 members end out of phase order: assess (05-) first, then understand (02-)
    write_checkpoint(rd, _ckpt(PhaseName.ASSESS))
    write_checkpoint(rd, _ckpt(PhaseName.UNDERSTAND))
    latest = latest_checkpoint(rd)
    assert latest is not None and latest.phase is PhaseName.UNDERSTAND and latest.ordinal == 2
    assert load_checkpoint(rd.checkpoints / "05-assess.json").ordinal == 1


def test_rewritten_checkpoint_gets_a_new_ordinal(tmp_path) -> None:
    rd = RunDir(tmp_path / "run").create()
    write_checkpoint(rd, _ckpt(PhaseName.PLAN))
    write_checkpoint(rd, _ckpt(PhaseName.ASSESS))
    write_checkpoint(rd, _ckpt(PhaseName.PLAN))              # a re-run member (resume) writes again
    latest = latest_checkpoint(rd)
    assert latest is not None and latest.phase is PhaseName.PLAN and latest.ordinal == 3


def test_legacy_checkpoint_without_ordinal_reads_its_seq(tmp_path) -> None:
    rd = RunDir(tmp_path / "run").create()
    write_checkpoint(rd, _ckpt(PhaseName.PLAN))
    path = rd.checkpoints / "03-plan.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("ordinal")
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_checkpoint(path).ordinal == 3                # legacy runs wrote in phase order


def test_explicit_ordinal_is_kept(tmp_path) -> None:
    rd = RunDir(tmp_path / "run").create()
    write_checkpoint(rd, _ckpt(PhaseName.PLAN, ordinal=7))
    assert load_checkpoint(rd.checkpoints / "03-plan.json").ordinal == 7


# --------------------------------------------------------------------------- elapsed seconds


def test_budget_elapsed_seconds_restore_the_clock_not_the_phase_sum() -> None:
    b = Budget(phase_seconds={"understand": 136.0, "plan": 102.0, "assess": 205.0}, elapsed_s=209.5)
    assert b.elapsed_for_resume() == 209.5                   # overlapping stage 1 times do not sum
    legacy = Budget(phase_seconds={"understand": 136.0, "plan": 102.0})
    assert legacy.elapsed_for_resume() == 238.0              # older state.json: sequential phases did sum
    assert Budget().elapsed_for_resume() == 0.0
    with pytest.raises(ValueError):
        Budget(elapsed_s=-1.0)


# --------------------------------------------------------------------------- verifier additions (W0 verifier)
#
# The adversarial revision inputs the builder's tests did not cover, the patched-finding checks of
# ``revision_problems(..., drafts=)`` and the one exact application, ``apply_revisions``.


def _draft(fid: str, *, kind: str = "risk", severity: str | None = "high", disposition: str = "refinement_now",
           evidence: tuple[str, ...] = (), criteria: tuple[str, ...] = ("internal_consistency",),
           next_step: bool = False) -> FindingDraft:
    rec = None if disposition == "no_change" else {
        "issue": "i", "rationale": "r", "expected_benefit": "b", "change_summary": "c", "objective_refs": [],
        "supporting_evidence_ids": [], "verification": None}
    return FindingDraft.model_validate({
        "id": fid, "rank": int(fid[-3:]), "kind": kind, "category": None if kind == "strength" else "other",
        "severity": severity, "confidence": 0.8, "disposition": disposition, "secondary_dispositions": [],
        "title": f"title {fid}", "statement": f"statement {fid}",
        "doc_anchors": [{"doc_id": "D1", "section_ref": "2.1", "requirement_ids": [], "quote": "q", "page": 1}],
        "evidence": [{"evidence_id": e, "source_type": "doc", "quote": "q", "supports_claim": True,
                      "derived_from": []} for e in evidence],
        "recommendation": rec, "no_change_rationale": "sound as written" if disposition == "no_change" else None,
        "next_step": {"owner": "o", "action": "a"} if next_step else None, "affected_decisions": [],
        "acknowledged_in_doc": False, "tags": [], "reassessment": None, "criterion_ids": list(criteria)})


def _ev(eid: str) -> dict[str, Any]:
    return {"evidence_id": eid, "source_type": "external", "quote": "x", "supports_claim": True, "derived_from": []}


DRAFTS = [_draft("FND-001", evidence=("EV-001",)), _draft("FND-002", criteria=("verifiability",)),
          _draft("FND-003", kind="strength", severity=None, disposition="no_change")]
BY_ID = {d.id: d for d in DRAFTS}


def _strength_keep(rank: int) -> dict[str, Any]:
    return _keep("FND-003", rank, severity=None, disposition="no_change")


@pytest.mark.parametrize(("revs", "needle"), [
    # the merge target is itself withdrawn
    ((_keep("FND-001", 1), _gone("FND-002", "merge", "FND-003"), _gone("FND-003", "withdraw")),
     "FND-002: merge into FND-003, which is not kept"),
    # two findings merging into each other
    ((_keep("FND-001", 1), _gone("FND-002", "merge", "FND-003"), _gone("FND-003", "merge", "FND-002")),
     "FND-003: merge into FND-002, which is not kept"),
    # a rank sequence with a gap
    ((_keep("FND-001", 1), _keep("FND-002", 3), _strength_keep(4)), "ranks of kept findings must be 1..3"),
    # a rank of zero
    ((_keep("FND-001", 0), _keep("FND-002", 1), _strength_keep(2)), "ranks of kept findings must be 1..3"),
    # the same evidence added twice in one revision
    ((_keep("FND-001", 1), _keep("FND-002", 2, added_evidence=[_ev("EV-009"), _ev("EV-009")]), _strength_keep(3)),
     "FND-002 adds evidence EV-009 more than once"),
])
def test_revision_problems_adversarial_verifier(revs: tuple[dict[str, Any], ...], needle: str) -> None:
    problems = revision_problems(_out(*revs), IDS)
    assert any(needle in p for p in problems), problems


@pytest.mark.parametrize(("rev2", "needle"), [
    # severity null on keep is a final value: legal for a strength, a problem for a risk
    (_keep("FND-002", 2, severity=None), "FND-002 after keep: risk needs a category and a severity"),
    # a disposition the draft cannot support: no rationale for no_change, no next step for investigation
    (_keep("FND-002", 2, disposition="no_change"), "FND-002 after keep: no_change forbids a recommendation"),
    (_keep("FND-002", 2, disposition="needs_investigation"),
     "FND-002 after keep: disposition needs_investigation requires next_step"),
    # a challenge needs two evidence items after the append
    (_keep("FND-002", 2, affected_decisions=[{"registry_id": "AD-001", "relation": "challenges",
                                              "justification": "j"}], added_evidence=[_ev("EV-005")]),
     "FND-002 after keep: challenging an approved decision needs >= 2 evidence items"),
])
def test_revision_problems_check_the_kept_finding_against_the_spec_rules(rev2: dict[str, Any], needle: str) -> None:
    out = _out(_keep("FND-001", 1), rev2, _strength_keep(3))
    assert revision_problems(out, IDS) == []                 # without the drafts only the revision rules apply
    problems = revision_problems(out, IDS, drafts=BY_ID)
    assert any(needle in p for p in problems), problems


def test_revision_problems_refuse_evidence_the_draft_already_cites() -> None:
    out = _out(_keep("FND-001", 1, added_evidence=[_ev("EV-001")]), _keep("FND-002", 2), _strength_keep(3))
    assert revision_problems(out, IDS, drafts=BY_ID) == ["FND-001 adds evidence EV-001 it already cites"]


def test_a_strength_kept_with_null_severity_and_a_keep_that_changes_nothing_are_clean() -> None:
    out = _out(_keep("FND-001", 1), _keep("FND-002", 2), _strength_keep(3))
    assert revision_problems(out, IDS, drafts=BY_ID) == []
    kept = apply_revisions(DRAFTS, out)
    assert [k.model_dump() for k in kept] == [d.model_dump() for d in DRAFTS]   # same values, empty append


def test_an_unknown_registry_link_is_left_to_verify() -> None:
    """Defined meaning: refine may name a registry entry that does not exist; ``revision_problems`` does
    not know the registry, and verify drops the link and records the change (``phases/verify.py``)."""
    out = _out(_keep("FND-001", 1, affected_decisions=[{"registry_id": "AD-999", "relation": "preserves",
                                                        "justification": "j"}]), _keep("FND-002", 2),
               _strength_keep(3))
    assert revision_problems(out, IDS, drafts=BY_ID) == []


def test_apply_revisions_is_exact_and_leaves_the_drafts_alone() -> None:
    before = [d.model_dump() for d in DRAFTS]
    out = _out(_keep("FND-002", 1, severity="critical", added_evidence=[_ev("EV-007")],
                     affected_decisions=[{"registry_id": "AD-002", "relation": "refines", "justification": "j"}]),
               _gone("FND-001", "merge", "FND-002"), _gone("FND-003", "withdraw"))
    kept = apply_revisions(DRAFTS, out)
    assert [k.id for k in kept] == ["FND-002"]
    k = kept[0]
    assert (k.rank, k.severity, k.disposition) == (1, "critical", "refinement_now")
    assert [e.evidence_id for e in k.evidence] == ["EV-007"]
    assert [a.registry_id for a in k.affected_decisions] == ["AD-002"]
    assert k.criterion_ids == ["verifiability", "internal_consistency"]   # the merged finding's criterion
    assert k.title == DRAFTS[1].title and k.doc_anchors == DRAFTS[1].doc_anchors
    assert [d.model_dump() for d in DRAFTS] == before


def test_apply_revisions_orders_by_rank_and_refuses_a_set_with_problems() -> None:
    kept = apply_revisions(DRAFTS, _out(_keep("FND-001", 3), _keep("FND-002", 1), _strength_keep(2)))
    assert [(k.id, k.rank) for k in kept] == [("FND-002", 1), ("FND-003", 2), ("FND-001", 3)]
    with pytest.raises(ValueError, match="cannot be applied: no revision for FND-003"):
        apply_revisions(DRAFTS, _out(_keep("FND-001", 1), _keep("FND-002", 2)))


def test_estimated_usage_of_a_cut_call_never_reaches_measured_totals(tmp_path) -> None:
    """A cut call logged as the gateways log one today (``usage: null`` with ``usage_unrecorded``), even
    with its estimate written beside it under the literal key ``estimated_usage``: the manifest totals,
    the harness completeness read and the run's token budget count measured usage only, and the cut
    call is listed as unrecorded (the accounting commit's semantics)."""
    err = LLMDeadlineError("cut at 265 s", call_id="llm-0002", phase="assess",
                           partial={"findings": [{"id": "FND-001"}]},
                           estimated_usage=Usage(input_tokens=30_000, output_tokens=12_000))
    rd = RunDir(tmp_path / "run").create()
    log = JsonlWriter(rd.llm_log)
    log.append({"call_id": "llm-0001", "phase": "understand", "purpose": "understand", "attempt": 1,
                "outcome": "ok", "model": "claude-opus-5-5", "elapsed_s": 130.0,
                "usage": {"input_tokens": 100, "output_tokens": 50, "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 0}, "call_cost_usd": 0.0014})
    log.append({"call_id": err.call_id, "phase": err.phase, "purpose": "assess", "attempt": 1,
                "outcome": type(err).__name__, "error": str(err), "elapsed_s": 265.0,
                **unrecorded_usage("deadline_cut"), "estimated_usage": vars(err.estimated_usage)})
    tot = journal_usage(rd)
    assert (tot["input_tokens"], tot["output_tokens"]) == (100, 50)
    assert tot["cost_usd"] == 0.0014
    assert [c["reason"] for c in tot["calls_with_unrecorded_usage"]] == ["deadline_cut"]
    assert from_call_log(rd.llm_log).status == "unrecorded"
    budget = Budget()
    add_usage(budget, err.usage)
    assert (budget.input_tokens, budget.output_tokens) == (0, 0)


def test_resume_clock_from_overlapping_members_is_the_last_checkpoint_elapsed(tmp_path) -> None:
    """Stage 1 members overlap (design section 4 table): each member's checkpoint stores the run clock
    when it ended. The latest by ordinal (research, file 04-) carries the clock to restore; the last
    file name (05-assess) and the sum of the overlapping phase times are both wrong."""
    rd = RunDir(tmp_path / "run").create()
    phase_seconds: dict[str, float] = {}
    for phase, start, end in ((PhaseName.PLAN, 3.5, 106.0), (PhaseName.UNDERSTAND, 3.5, 140.0),
                              (PhaseName.ASSESS, 3.5, 208.0), (PhaseName.RESEARCH, 140.0, 265.0)):
        phase_seconds[phase.value] = end - start
        ck = _ckpt(phase)
        ck.state.budget = Budget(phase_seconds=dict(phase_seconds), elapsed_s=end)
        write_checkpoint(rd, ck)
    latest = latest_checkpoint(rd)
    assert latest is not None and latest.phase is PhaseName.RESEARCH
    assert latest.state.budget.elapsed_for_resume() == 265.0
    assert sum(latest.state.budget.phase_seconds.values()) > 265.0          # 102.5 + 136.5 + 204.5 + 125
    assert sorted(rd.checkpoints.glob("*.json"))[-1].name == "05-assess.json"


def test_coverage_and_raw_readers_take_the_latest_checkpoint_by_ordinal(tmp_path) -> None:
    rd = RunDir(tmp_path / "run").create()
    for phase in (PhaseName.ASSESS, PhaseName.UNDERSTAND):                  # assess ends first
        ck = _ckpt(phase)
        ck.state.run_id = phase.value
        write_checkpoint(rd, ck)
    files = sorted(rd.checkpoints.glob("*.json"), key=checkpoint_file_order)
    assert [f.name for f in files] == ["05-assess.json", "02-understand.json"]
    rd.state.unlink()                                       # a run directory without state.json
    state, source = _state(rd.root)
    assert (state["run_id"], source) == ("understand", "checkpoints/02-understand.json")
    # a legacy file (no ordinal) orders by seq; an unreadable one sorts first
    legacy = rd.checkpoints / "05-assess.json"
    data = json.loads(legacy.read_text(encoding="utf-8"))
    data.pop("ordinal")
    legacy.write_text(json.dumps(data), encoding="utf-8")
    (rd.checkpoints / "09-junk.json").write_text("{not json", encoding="utf-8")
    assert [checkpoint_file_order(f) for f in sorted(rd.checkpoints.glob("*.json"))] == [2, 5, 0]


def test_apply_revisions_returns_findings_that_share_nothing_with_the_drafts() -> None:
    """The refine phase edits the kept findings further (IDs, notes); that must never reach the drafts it
    keeps in run state for resume and ``explain``."""
    before = [d.model_dump() for d in DRAFTS]
    kept = apply_revisions(DRAFTS, _out(_keep("FND-001", 1), _keep("FND-002", 2), _strength_keep(3)))
    for k in kept:
        k.doc_anchors[0].quote = "edited"
        k.evidence.clear()
        k.criterion_ids.append("edited")
    assert [d.model_dump() for d in DRAFTS] == before


def test_stage1_rules_hold_for_every_member_state_and_finishing_order() -> None:
    """Exhaustive (the repo has no hypothesis): each of the four members not started, running, or ended
    done / cut / skipped (5^4 states), then every finishing order of a scheduler that starts what is
    ready and ends one running member at a time."""
    from itertools import permutations, product

    members = list(STAGE_1_DEPENDS)
    for states in product(("idle", "running", "done", "cut", "skipped"), repeat=4):
        ended = {p: s for p, s in zip(members, states, strict=True) if s in ("done", "cut", "skipped")}
        running = {p for p, s in zip(members, states, strict=True) if s == "running"}
        ready = stage1_ready(ended, running)
        assert not ready & (set(ended) | running)
        for p in members:
            idle = p not in ended and p not in running
            deps_ended = STAGE_1_DEPENDS[p] <= set(ended)
            assert (p in ready) == (idle and deps_ended), (states, p)
        closed = stage1_close(ended, running)
        assert set(closed) == set(members)
        assert all(closed[p] == ended[p] for p in ended)
        assert all(closed[p] == "cut" for p in running)
        assert all(closed[p] == "skipped" for p in members if p not in ended and p not in running)
        assert stage1_ready(closed, set()) == set()
    for order in permutations(members):
        ended: dict[PhaseName, Any] = {}
        running: set[PhaseName] = set()
        started: list[PhaseName] = []
        pending = list(order)                      # the order in which members would like to finish
        while len(ended) < len(members):
            new = stage1_ready(ended, running)
            running |= new
            started += sorted(new)
            done = next(p for p in pending if p in running)
            pending.remove(done)
            running.discard(done)
            ended[done] = "done"
        assert sorted(started) == sorted(members) and len(started) == len(set(started))
        r = started.index(PhaseName.RESEARCH)
        assert {PhaseName.UNDERSTAND, PhaseName.PLAN} <= set(list(ended)[:list(ended).index(PhaseName.RESEARCH)])
        assert r == 3                              # research is the last to start, whatever ends first
