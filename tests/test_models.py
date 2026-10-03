"""models.py matches spec/finding.schema.json: round trip, schema validation, enum parity, allOf rules."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from sit_review_agent import models as m
from sit_review_agent.invariants import spec_validator
from sit_review_agent.paths import finding_schema_path, spec_dir, taxonomy_path

SCHEMA = json.loads(finding_schema_path().read_text(encoding="utf-8"))
TAX = yaml.safe_load(taxonomy_path().read_text(encoding="utf-8"))


def readme_examples() -> dict[str, dict[str, Any]]:
    text = (spec_dir() / "README.md").read_text(encoding="utf-8")
    return {mm.group(1): json.loads(mm.group(2))
            for mm in re.finditer(r"<!-- example:finding:(\S+) -->\s*```json\n(.*?)```", text, re.S)}


def schema_errors(def_name: str, obj: Any) -> list[str]:
    return [e.message for e in spec_validator(def_name).iter_errors(obj)]


def test_review_round_trip_validates_against_schema(review_dict: dict[str, Any]) -> None:
    review = m.Review.model_validate(review_dict)
    dumped = review.model_dump(mode="json")
    assert dumped == review_dict                       # byte-faithful round trip
    assert schema_errors("Review", dumped) == []
    assert m.Review.model_validate(dumped) == review


@pytest.mark.parametrize("name", ["no_change", "recommendation"])
def test_readme_findings_round_trip(name: str) -> None:
    ex = readme_examples()[name]
    f = m.Finding.model_validate(ex)
    dumped = f.model_dump(mode="json")
    assert dumped == ex
    assert schema_errors("Finding", dumped) == []


def test_constructed_review_validates(review_dict: dict[str, Any]) -> None:
    """Build objects in code (not from JSON) and check the dump against the schema."""
    review = m.Review.model_validate(review_dict)
    anchor = m.DocAnchor(doc_id="DOC-booking-v1", section_ref="4.1", requirement_ids=[],
                         quote="Peak exam-week days generate about 5,000 bookings, each with one reminder.", page=6)
    gap = m.Finding(
        id=m.finding_id(9), rank=3, kind=m.Kind.GAP, category=m.Category.MISSING_OR_UNVERIFIABLE_REQUIREMENT,
        severity=m.Severity.MEDIUM, confidence=0.6, disposition=m.Disposition.NEEDS_INVESTIGATION,
        secondary_dispositions=[], title="Peak load source not stated", statement="The peak figure has no source.",
        doc_anchors=[anchor],
        evidence=[m.EvidenceItem(evidence_id="EV-005", source_type=m.SourceType.DOC,
                                 url_or_citation="doc:DOC-booking-v1#p6/s4.1",
                                 quote="Peak exam-week days generate about 5,000 bookings", supports_claim=True,
                                 retrieved_at=None, derived_from=[])],
        recommendation=m.Recommendation(issue="Unsourced peak load figure.", rationale="Capacity depends on it.",
                                        expected_benefit="Sizing rests on measured data.",
                                        change_summary="Cite the booking logs behind the figure in 4.1.",
                                        objective_refs=["FR-9"], supporting_evidence_ids=["EV-005"], verification=None),
        no_change_rationale=None, next_step=m.NextStep(owner="Product owner", action="Pull last year's peak logs."),
        affected_decisions=[], acknowledged_in_doc=False, tags=[], reassessment=None,
        provenance=m.Provenance(phase=m.ProvenancePhase.ASSESS, iteration=1, model="claude-opus-5-5",
                                prompt_hash="a" * 64))
    review.findings.append(gap)
    assert schema_errors("Review", review.model_dump(mode="json")) == []


def _schema_enum(name: str) -> set[str]:
    return set(SCHEMA["$defs"][name]["enum"])


@pytest.mark.parametrize("schema_name,enum_cls,tax_key", [
    ("Kind", m.Kind, "kinds"), ("Category", m.Category, "categories"), ("Severity", m.Severity, "severities"),
    ("Disposition", m.Disposition, "dispositions"), ("VerdictLabel", m.VerdictLabel, "verdicts"),
    ("SourceType", m.SourceType, "provenance_sources"), ("SourceAuthority", m.SourceAuthority, "source_authority"),
    ("StopReasonCode", m.StopReasonCode, "stop_reasons"),
    ("DecisionRelation", m.DecisionRelation, "decision_relations"),
    ("RegistryEntryType", m.RegistryEntryType, "registry_entry_types"), ("Phase", m.ProvenancePhase, "phases"),
    ("ReassessmentStatus", m.ReassessmentStatus, "reassessment_statuses"),
    ("PriorFindingStatus", m.PriorFindingStatus, "prior_finding_statuses"),
    ("DegradationType", m.DegradationType, "degradation_types"),
    ("ToolCallStatus", m.ToolCallStatus, "tool_call_statuses"),
])
def test_enum_parity_with_schema_and_taxonomy(schema_name: str, enum_cls: type, tax_key: str) -> None:
    values = {e.value for e in enum_cls}
    assert values == _schema_enum(schema_name)
    tax = {x["id"] if isinstance(x, dict) else x for x in TAX[tax_key]}
    assert values == tax


def test_stop_reason_groups_match_taxonomy() -> None:
    want = {s["id"]: s["group"] for s in TAX["stop_reasons"]}
    assert {k.value: v.value for k, v in m.STOP_REASON_GROUP.items()} == want


def test_every_spec_object_forbids_extra_keys() -> None:
    ex = copy.deepcopy(readme_examples()["recommendation"])
    ex["criterion_ids"] = ["x"]
    with pytest.raises(ValidationError):
        m.Finding.model_validate(ex)


@pytest.mark.parametrize("mutate,needle", [
    (lambda f: f.update(kind="strength"), "strength"),
    (lambda f: f.update(disposition="no_change"), "no_change"),
    (lambda f: f.update(secondary_dispositions=["refinement_now"]), "repeat"),
    (lambda f: f.update(doc_anchors=f["doc_anchors"] * 4), "at most 3"),
    (lambda f: f["doc_anchors"][0].update(quote="too short to count"), "pattern"),
    (lambda f: f["affected_decisions"].append({"registry_id": "AD-001", "relation": "challenges",
                                               "justification": "x"}) or f.update(evidence=f["evidence"][:1]), ">= 2"),
])
def test_schema_all_of_rules_enforced(mutate: Any, needle: str) -> None:
    ex = copy.deepcopy(readme_examples()["recommendation"])
    mutate(ex)
    with pytest.raises(ValidationError) as info:
        m.Finding.model_validate(ex)
    assert needle in str(info.value)
    assert schema_errors("Finding", ex)                 # the schema rejects it too


def test_stop_reason_group_checked() -> None:
    assert m.StopReason.of(m.StopReasonCode.DEADLINE).group is m.StopReasonGroup.CAP
    with pytest.raises(ValidationError):
        m.StopReason(code=m.StopReasonCode.DEADLINE, group=m.StopReasonGroup.DECISION, detail=None)


def test_delta_rules(review_dict: dict[str, Any]) -> None:
    bad = copy.deepcopy(review_dict)
    bad["metadata"]["review_mode"] = "delta"
    with pytest.raises(ValidationError):
        m.Review.model_validate(bad)
    assert schema_errors("Review", bad)


def test_id_helpers() -> None:
    assert (m.finding_id(7), m.evidence_id(12), m.registry_id(2), m.sound_area_id(1), m.degradation_id(1000)) == \
        ("FND-007", "EV-012", "AD-002", "SA-001", "DEG-1000")


def test_manifest_extra_fits_run_manifest(review_dict: dict[str, Any]) -> None:
    extra = m.ManifestExtra(mode="dev", prompts={"bundle_sha256": "0" * 64})
    rm = copy.deepcopy(review_dict["run_manifest"])
    rm["extra"] = extra.model_dump(mode="json")
    assert schema_errors("RunManifest", rm) == []
    assert m.RunManifest.model_validate(rm).extra["mode"] == "dev"
