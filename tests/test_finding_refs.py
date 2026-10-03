"""``finding_refs``: the rewrite of finding-ID references through the run's ID map, and INV-12's walk
(merged-ID traceability, 2026-10-03)."""

from __future__ import annotations

from typing import Any

import pytest

from sit_review_agent.finding_refs import (
    IdChain,
    RewriteStats,
    dangling_refs,
    iter_refs,
    manifest_record,
    mark_drafts,
    rewrite_text,
    rewrite_tree,
)
from sit_review_agent.invariants import check_INV_12
from sit_review_agent.models import ManifestExtra
from sit_review_agent.state.run_state import FindingIdMap, RunState

#: FND-002 merged into FND-001, FND-007 merged into FND-004, FND-005 and FND-008 withdrawn.
MAP = {"FND-002": "FND-001", "FND-007": "FND-004", "FND-005": None, "FND-008": None}


def resolve(t: str) -> str | None:
    return MAP.get(t, t)


@pytest.mark.parametrize(("text", "want"), [
    ("The audit store is write-once (see FND-002).", "The audit store is write-once (see FND-001)."),
    ("Raised in FND-001 and FND-002.", "Raised in FND-001."),
    ("Covered by FND-003, FND-005 and FND-007.", "Covered by FND-003 and FND-004."),
    ("Either FND-003 or FND-007 applies.", "Either FND-003 or FND-004 applies."),
    ("FND-001, FND-002, FND-003", "FND-001, FND-003"),
    ("The plane is separate (see FND-005).", "The plane is separate."),
    ("The plane is separate (FND-005, FND-008).", "The plane is separate."),
    ("It breaks NFR-5; see also FND-005.", "It breaks NFR-5."),
    ("The cache crosses projects. Compare FND-005.", "The cache crosses projects."),
    ("See FND-005. The rest stays.", "The rest stays."),
    ("FND-005 shows that the cache leaks.", "A finding not in this review shows that the cache leaks."),
    ("As FND-005 and FND-008 show, it leaks.", "As findings not in this review show, it leaks."),
    ("Raised in FND-008.", "Raised in a finding not in this review."),       # the whole text: never emptied
    ("Raised in FND-008. Checked otherwise.", "Checked otherwise."),
    ("(see FND-005)", "(see a finding not in this review)"),
    ("Leaves accounts (FND-004, FND-008).", "Leaves accounts (FND-004)."),
    ("No reference here.", "No reference here."),
    ("FND-003 and FND-004 are separate.", "FND-003 and FND-004 are separate."),
])
def test_rewrite_text(text: str, want: str) -> None:
    assert rewrite_text(text, resolve) == want


def test_rewrite_counts_remapped_and_removed() -> None:
    stats = RewriteStats()
    rewrite_text("Covered by FND-003, FND-005 and FND-007.", resolve, stats)
    assert stats.as_dict() == {"remapped": 1, "removed": 1, "marked_draft": 0}


def test_mark_drafts_names_non_final_ids_as_drafts_once() -> None:
    text = "2 item(s) dropped by code checks in verify: FND-030: hollow; draft FND-031: x; FND-001 kept"
    assert mark_drafts(text, {"FND-001"}) == ("2 item(s) dropped by code checks in verify: draft FND-030: hollow; "
                                              "draft FND-031: x; FND-001 kept")


def test_rewrite_tree_skips_own_id_quotes_and_reassessment_and_overrides_a_subtree() -> None:
    node: dict[str, Any] = {
        "id": "FND-002", "statement": "Same as FND-002.", "doc_anchors": [{"quote": "see FND-002"}],
        "reassessment": {"prior_finding_id": "FND-005", "note": "FND-005 resolved"},
        "affected_decisions": [{"justification": "As FND-009 says."}], "related_finding_ids": ["FND-002", "FND-001"]}
    out = rewrite_tree(node, resolve, override={"affected_decisions": lambda t: "FND-003"})
    assert out["id"] == "FND-002" and out["doc_anchors"] == node["doc_anchors"]
    assert out["reassessment"] == node["reassessment"]
    assert out["statement"] == "Same as FND-001."
    assert out["affected_decisions"] == [{"justification": "As FND-003 says."}]
    assert out["related_finding_ids"] == ["FND-001"]


def test_id_chain_reads_each_numbering() -> None:
    chain = IdChain(shards={"s1": {"FND-001": "FND-001", "FND-002": "FND-002"},
                            "s2": {"FND-001": "FND-003", "FND-002": "FND-004", "FND-003": "FND-005"}},
                    refine={"FND-002": "FND-001", "FND-005": None}, verify={"FND-004": None},
                    final=frozenset({"FND-001", "FND-003"}), prior=frozenset({"FND-009"}))
    s1, s2 = chain.shard("s1"), chain.shard("s2")
    assert [s1("FND-001"), s1("FND-002"), s1("FND-003")] == ["FND-001", "FND-001", None]
    assert [s2("FND-001"), s2("FND-002"), s2("FND-003")] == ["FND-003", None, None]
    assert [chain.draft("FND-002"), chain.draft("FND-004"), chain.draft("FND-005")] == ["FND-001", None, None]
    assert chain.final_id("FND-002") is None and chain.final_id("FND-009") == "FND-009"
    assert s2("FND-009") == "FND-009"                                 # delta mode: the prior review's ID
    assert chain.shard_to_draft("s2")("FND-002") == "FND-004" and chain.shard_to_draft("s2")("FND-004") is None
    assert chain.shard(None)("FND-002") == "FND-001"                  # no shard known: draft numbering
    assert chain.final_map() == {"FND-001": "FND-001", "FND-002": "FND-001", "FND-003": "FND-003",
                                 "FND-004": None, "FND-005": None}


def review(**kw: Any) -> dict[str, Any]:
    r: dict[str, Any] = {
        "findings": [{"id": "FND-001", "statement": "Fine.", "doc_anchors": [{"quote": "FND-777 in the doc"}],
                      "reassessment": {"prior_finding_id": "FND-555", "note": "FND-555"}}],
        "sound_areas": [{"why_sound": "See FND-001.", "related_finding_ids": ["FND-001"]}],
        "verdict": {"rationale": "FND-001 matters."},
        "research_log": {"degradations": [{"event": "dropped: draft FND-004", "impact": "x"}]},
        "limitations": [{"text": "dropped: draft FND-004"}],
        "evidence_ledger": [{"excerpt": "FND-888"}], "metadata": {"run_id": "FND-999"},
        "run_manifest": {"extra": {"finding_ids": {"final": {"FND-001": "FND-001", "FND-004": None}, "prior": []}}},
    }
    r.update(kw)
    return r


def test_inv12_passes_a_clean_review() -> None:
    assert dangling_refs(review()) == []
    assert check_INV_12(review()).passed
    assert {r.finding_id for r in iter_refs(review())} == {"FND-001", "FND-004"}


@pytest.mark.parametrize(("change", "problem"), [
    ({"verdict": {"rationale": "FND-002 matters."}}, "$.verdict.rationale: FND-002 is not a finding of this review"),
    ({"sound_areas": [{"why_sound": "x", "related_finding_ids": ["FND-003"]}]},
     "$.sound_areas[0].related_finding_ids[0]: FND-003 is not a finding of this review"),
    ({"limitations": [{"text": "dropped: draft FND-006"}]},
     "$.limitations[0].text: draft FND-006 is not in extra.finding_ids.final"),
    ({"verdict": {"rationale": "draft FND-004 matters."}},
     "$.verdict.rationale: FND-004 is not a finding of this review"),        # a draft mark only in disclosures
])
def test_inv12_names_each_dangling_reference(change: dict[str, Any], problem: str) -> None:
    assert dangling_refs(review(**change)) == [problem]
    assert not check_INV_12(review(**change)).passed


def test_inv12_admits_a_prior_review_id_in_delta_mode() -> None:
    r = review(verdict={"rationale": "FND-555 of the prior review is resolved."})
    assert dangling_refs(r) != []
    r["run_manifest"]["extra"]["finding_ids"]["prior"] = ["FND-555"]
    assert dangling_refs(r) == []


def test_state_and_manifest_carry_the_map() -> None:
    st = RunState(run_id="r", created_utc="2026-10-03T00:00:00Z")
    assert st.finding_ids == FindingIdMap()
    st.finding_ids.shards = {"s1": {"FND-001": "FND-001", "FND-002": "FND-002"}}
    st.finding_ids.refine = {"FND-002": "FND-001"}
    rec = manifest_record(st.finding_ids, ["FND-001"])
    assert rec["final"] == {"FND-001": "FND-001", "FND-002": "FND-001"}
    extra = ManifestExtra(mode="dev", finding_ids=rec)
    assert ManifestExtra.model_validate(extra.model_dump(mode="json")).finding_ids == rec
    assert ManifestExtra(mode="dev").finding_ids == {}                       # a manifest written before
    assert RunState.model_validate_json(st.model_dump_json()).finding_ids == st.finding_ids
