"""W0 interface change of the latency redesign (docs/design/latency_and_demo_design.md sections 4, 5, 7).

Pins the new frozen types before any workstream builds on them: revision-only refine output, the
verdict-only report output, the salvaged partial answer on ``LLMDeadlineError``, the stage 1 group
and its transition rules, the checkpoint ordinal and the run's elapsed seconds.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from sit_review_agent.errors import LLMDeadlineError, LLMError, LLMTimeoutError
from sit_review_agent.llm.gateway import Usage
from sit_review_agent.llm.outputs import (
    FindingRevisionDraft,
    RefineRevisionsOutput,
    RevisionAction,
    VerdictOutput,
    llm_facing_schema,
    revision_problems,
)
from sit_review_agent.rundir import RunDir
from sit_review_agent.state.checkpoint import (
    Checkpoint,
    JournalOffsets,
    PinnedHashes,
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
        "disposition": "refinement_now", "affected_decisions": [], "added_evidence": [], "reason": "kept",
    }
    base.update(kw)
    return base


def _gone(fid: str, action: str, into: str | None = None, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "finding_id": fid, "action": action, "merge_into": into, "rank": None, "severity": None,
        "disposition": None, "affected_decisions": [], "added_evidence": [], "reason": action,
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
    assert again == out and json.loads(out.model_dump_json()) == raw
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
