"""A refine revision may move a finding to a disposition that needs a next step (latency
integration, planner ruling on W2's Haiku check): ``FindingRevisionDraft.next_step`` carries the
step on a ``keep`` exactly when the new disposition needs one and the draft has none, and is null
otherwise.
"""

from __future__ import annotations

from typing import Any

import pytest

from sit_review_agent.llm.outputs import (
    FindingDraft,
    RefineRevisionsOutput,
    apply_revisions,
    llm_facing_schema,
    revision_problems,
)
from sit_review_agent.phases.refine import without_unexplained_changes

STEP = {"owner": "Notification service owner", "action": "Confirm the contracted daily quota."}


def _draft(fid: str, disposition: str = "refinement_now", *, next_step: bool = False) -> FindingDraft:
    return FindingDraft.model_validate({
        "id": fid, "rank": int(fid[-3:]), "kind": "risk", "category": "other", "severity": "high",
        "confidence": 0.8, "disposition": disposition, "secondary_dispositions": [], "title": f"title {fid}",
        "statement": f"statement {fid}",
        "doc_anchors": [{"doc_id": "D1", "section_ref": "2.1", "requirement_ids": [], "quote": "q", "page": 1}],
        "evidence": [], "recommendation": {"issue": "i", "rationale": "r", "expected_benefit": "b",
                                           "change_summary": "c", "objective_refs": [],
                                           "supporting_evidence_ids": [], "verification": None},
        "no_change_rationale": None, "next_step": STEP if next_step else None, "affected_decisions": [],
        "acknowledged_in_doc": False, "tags": [], "reassessment": None, "criterion_ids": ["verifiability"]})


def _keep(fid: str, rank: int, disposition: str, next_step: dict[str, str] | None = None,
          reason: str = "the quota is a fact to confirm, not a design change") -> dict[str, Any]:
    return {"finding_id": fid, "action": "keep", "merge_into": None, "rank": rank, "severity": "high",
            "disposition": disposition, "affected_decisions": [], "added_evidence": [], "next_step": next_step,
            "reason": reason}


def _gone(fid: str, action: str, into: str | None = None, **kw: Any) -> dict[str, Any]:
    return {"finding_id": fid, "action": action, "merge_into": into, "rank": None, "severity": None,
            "disposition": None, "affected_decisions": [], "added_evidence": [], "next_step": None,
            "reason": action, **kw}


def _out(*revs: dict[str, Any]) -> RefineRevisionsOutput:
    return RefineRevisionsOutput.model_validate({"revisions": list(revs)})


DRAFTS = [_draft("FND-001"), _draft("FND-002", next_step=True)]
BY_ID = {d.id: d for d in DRAFTS}
IDS = [d.id for d in DRAFTS]


def test_a_keep_moving_to_needs_investigation_carries_the_next_step() -> None:
    out = _out(_keep("FND-001", 1, "needs_investigation", STEP), _keep("FND-002", 2, "refinement_now"))
    assert revision_problems(out, IDS, drafts=BY_ID) == []
    kept = apply_revisions(DRAFTS, out)
    assert kept[0].disposition.value == "needs_investigation" and kept[0].next_step is not None
    assert kept[0].next_step.model_dump() == STEP
    assert DRAFTS[0].next_step is None                                     # the drafts are not changed


def test_the_next_step_is_required_when_the_new_disposition_needs_it() -> None:
    out = _out(_keep("FND-001", 1, "needs_investigation"), _keep("FND-002", 2, "refinement_now"))
    assert revision_problems(out, IDS, drafts=BY_ID) == [
        "FND-001 after keep: disposition needs_investigation requires next_step"]


@pytest.mark.parametrize(("revs", "needle"), [
    # a disposition that needs no next step
    ((_keep("FND-001", 1, "refinement_now", STEP), _keep("FND-002", 2, "refinement_now")),
     "FND-001 sets next_step, but refinement_now needs none"),
    # the draft already has one: a revision never replaces it
    ((_keep("FND-001", 1, "refinement_now"), _keep("FND-002", 2, "needs_testing", STEP)),
     "FND-002 sets next_step, but the draft already has one"),
    # merge and withdraw carry nothing
    ((_keep("FND-001", 1, "refinement_now"), _gone("FND-002", "merge", "FND-001", next_step=STEP)),
     "FND-002 is merge but sets next_step"),
    ((_keep("FND-001", 1, "refinement_now"), _gone("FND-002", "withdraw", next_step=STEP)),
     "FND-002 is withdraw but sets next_step"),
])
def test_the_next_step_is_forbidden_otherwise(revs: tuple[dict[str, Any], ...], needle: str) -> None:
    problems = revision_problems(_out(*revs), IDS, drafts=BY_ID)
    assert any(needle in p for p in problems), problems


def test_without_the_drafts_only_the_disposition_rule_applies() -> None:
    assert revision_problems(_out(_keep("FND-001", 1, "refinement_now", STEP), _keep("FND-002", 2, "refinement_now")),
                             IDS) == ["FND-001 sets next_step, but refinement_now needs none"]
    assert revision_problems(_out(_keep("FND-001", 1, "needs_testing", STEP), _keep("FND-002", 2, "needs_testing")),
                             IDS) == []


def test_an_unexplained_disposition_change_is_reverted_with_its_next_step() -> None:
    """BEH-10: a keep that changes the disposition with no reason keeps the draft's value; the next
    step that came with the change goes too, so the reverted revision is clean."""
    out = _out(_keep("FND-001", 1, "needs_investigation", STEP, reason=""), _keep("FND-002", 2, "refinement_now"))
    fixed = without_unexplained_changes(out, BY_ID)
    assert fixed.revisions[0].disposition.value == "refinement_now" and fixed.revisions[0].next_step is None
    assert revision_problems(fixed, IDS, drafts=BY_ID) == []


def test_the_schema_requires_the_key_and_allows_null() -> None:
    rev = llm_facing_schema(RefineRevisionsOutput)["$defs"]["FindingRevisionDraft"]
    assert "next_step" in rev["required"]
    branches = rev["properties"]["next_step"]["anyOf"]
    assert {"type": "null"} in branches and any("$ref" in b for b in branches)



# ---------------------------------------------------------------------------- verifier's own set

THREE = [_draft("FND-001"), _draft("FND-002", next_step=True), _draft("FND-003")]
THREE_BY_ID = {d.id: d for d in THREE}
THREE_IDS = [d.id for d in THREE]


@pytest.mark.parametrize(("revs", "needle"), [
    # a move to a disposition that needs a next step, without one
    ((_keep("FND-001", 1, "governance_decision"), _keep("FND-002", 2, "refinement_now"),
      _keep("FND-003", 3, "refinement_now")), "FND-001 after keep: disposition governance_decision requires next_step"),
    # a next step where the new disposition forbids one
    ((_keep("FND-001", 1, "refinement_now"), _keep("FND-002", 2, "refinement_now"),
      _keep("FND-003", 3, "refinement_now", STEP)), "FND-003 sets next_step, but refinement_now needs none"),
    # a merge into a withdrawn finding
    ((_keep("FND-001", 1, "refinement_now"), _gone("FND-002", "withdraw"), _gone("FND-003", "merge", "FND-002")),
     "FND-003: merge into FND-002, which is not kept"),
    # two kept findings with the same rank
    ((_keep("FND-001", 1, "refinement_now"), _keep("FND-002", 1, "refinement_now"),
      _keep("FND-003", 2, "refinement_now")), "ranks of kept findings must be 1..3 with no gaps or repeats"),
    # a revision for a finding that does not exist
    ((_keep("FND-001", 1, "refinement_now"), _keep("FND-002", 2, "refinement_now"),
      _keep("FND-003", 3, "refinement_now"), _keep("FND-009", 4, "refinement_now")),
     "revision for unknown finding FND-009"),
    # a move across the no_change boundary: the draft's recommendation stays, so the move is refused
    ((_keep("FND-001", 1, "no_change"), _keep("FND-002", 2, "refinement_now"),
      _keep("FND-003", 3, "refinement_now")), "FND-001 after keep: no_change forbids a recommendation"),
])
def test_verifier_adversarial_revisions_are_refused(revs: tuple[dict[str, Any], ...], needle: str) -> None:
    problems = revision_problems(_out(*revs), THREE_IDS, drafts=THREE_BY_ID)
    assert any(needle in p for p in problems), problems
    with pytest.raises(ValueError, match="cannot be applied"):
        apply_revisions(THREE, _out(*revs))


def test_verifier_valid_set_applies_exactly() -> None:
    out = _out(_keep("FND-003", 1, "needs_testing", STEP), _gone("FND-001", "merge", "FND-003"),
               _keep("FND-002", 2, "refinement_now"))
    assert revision_problems(out, THREE_IDS, drafts=THREE_BY_ID) == []
    kept = apply_revisions(THREE, out)
    assert [(f.id, f.rank, f.disposition.value) for f in kept] == [("FND-003", 1, "needs_testing"),
                                                                    ("FND-002", 2, "refinement_now")]
    assert kept[0].next_step is not None and kept[0].next_step.model_dump() == STEP
    assert kept[1].next_step is not None and kept[1].next_step == THREE[1].next_step     # never replaced
    assert kept[0].criterion_ids == ["verifiability"]                                  # no duplicate criterion
