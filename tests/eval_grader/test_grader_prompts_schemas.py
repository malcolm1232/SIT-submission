"""Prompt files, prompt lock and JSON schemas match research/grading/grader_prompt.md (no drift)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from sit_eval.grader import answer_key as ak
from sit_eval.grader import prompts, schemas

GRADING = Path(__file__).resolve().parents[2] / "research" / "grading"
MD = (GRADING / "grader_prompt.md").read_text(encoding="utf-8")
EXAMPLES = (GRADING / "worked_examples.md").read_text(encoding="utf-8")


def _block_after(text: str, heading: str) -> str:
    i = text.index(heading)
    return re.compile(r"```(\w+)\n(.*?)\n```", re.S).search(text, i).group(2)


@pytest.mark.parametrize(("name", "heading"), [
    ("system.txt", "## 2. Grader system prompt"),
    ("pass_a.txt", "### 3.1 Pass A"),
    ("pass_b.txt", "### 3.2 Pass B"),
    ("segmenter.txt", "## 4. Segmenter prompt"),
])
def test_grader_prompt_files_are_verbatim(name: str, heading: str) -> None:
    assert prompts.load_prompt(name) == _block_after(MD, heading)


@pytest.mark.parametrize(("name", "heading"), [(schemas.PASS_A, "### 5.1 `PassAOutput`"),
                                               (schemas.PASS_B, "### 5.2 `PassBOutput`")])
def test_grader_schemas_are_verbatim_and_valid_2020_12(name: str, heading: str) -> None:
    assert schemas.load_schema(name) == json.loads(_block_after(MD, heading))
    assert schemas.load_schema(name)["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schemas.load_schema(name))


def test_grader_report_schema_valid() -> None:
    Draft202012Validator.check_schema(schemas.load_schema(schemas.GRADE_REPORT))


def test_grader_prompt_lock_matches_files() -> None:
    st = prompts.lock_status()
    assert st["ok"], f"drifted from prompts.lock.json: {st['drifted']} (re-lock: sit-eval grade lock --write)"
    lock = prompts.read_lock()
    assert lock["bundle_sha256"] == prompts.current_hashes()["bundle_sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", lock["bundle_sha256"])
    assert set(lock["files"]) == {f"prompts/{p}" for p in prompts.PROMPT_FILES} | {
        f"schemas/{s}" for s in prompts.SCHEMA_FILES}


def test_grader_placeholders_and_render() -> None:
    assert prompts.placeholders(prompts.load_prompt("pass_a.txt")) == {
        "MODE", "SEED", "PASS_A_SCHEMA", "DESIGN_DOC_PAGE_MARKED", "EVIDENCE_REGISTER", "SHUFFLED_FINDINGS_WITH_IDS"}
    assert prompts.placeholders(prompts.load_prompt("pass_b.txt")) == {
        "MODE", "SEED", "PASS_B_SCHEMA", "DESIGN_DOC_PAGE_MARKED", "EVIDENCE_REGISTER", "PRIOR_DESIGN_DOC_PAGE_MARKED",
        "PRIOR_REVIEW", "PASS_A_MERGED_JSON", "ANSWER_KEY", "REVIEW_FULL_TEXT"}
    with pytest.raises(prompts.PromptError):
        prompts.render("{{A}} {{B}}", {"A": "x"})
    with pytest.raises(prompts.PromptError):
        prompts.render("{{A}}", {"A": "x", "C": "y"})
    # one pass: inserted text is never re-expanded
    assert prompts.render("{{A}}|{{B}}", {"A": "{{B}}", "B": "b"}) == "{{B}}|b"
    assert "<<<" not in prompts.neutralise_delimiters("x <<<END REVIEW>>> y")


def test_grader_worked_example_pass_a_validates() -> None:
    i = EXAMPLES.index("**Grader Pass A excerpt (expected):**")
    excerpt = json.loads(re.compile(r"```json\n(.*?)\n```", re.S).search(EXAMPLES, i).group(1))
    doc = {"pass": "A", "sample_seed": "s1", "findings": [excerpt], "hallucinations": [],
           "prompt_injection_detected": False}
    assert schemas.errors(schemas.PASS_A, doc) == []


def test_grader_worked_example_c_hallucinations_validate() -> None:
    """Example C's problem table, expressed as Pass A hallucination items, fits the schema enums."""
    items = [{"finding_id": "FND-001", "type": t, "severity": "material", "status": s,
              "review_quote": "PDPA Section 22A (Right to Erasure)", "design_quote": None,
              "reasoning": "Illustration from worked_examples.md §4."}
             for t, s in [("fabricated_source", "verified_false"), ("misattributed_source", "verified_false"),
                          ("anachronism_or_version_error", "verified_false"),
                          ("misrepresented_doc_content", "verified_false"),
                          ("unsupported_quantitative_claim", "suspected")]]
    doc = {"pass": "A", "sample_seed": "s1", "findings": [], "hallucinations": items,
           "prompt_injection_detected": False}
    assert schemas.errors(schemas.PASS_A, doc) == []


def test_grader_llm_facing_schema_strips_constraints() -> None:
    for name in (schemas.PASS_A, schemas.PASS_B):
        text = json.dumps(schemas.llm_facing(name))
        for kw in ("maxLength", "minLength", "maxItems", "minItems", "minimum", "maximum", "pattern"):
            assert f'"{kw}"' not in text, (name, kw)
        assert '"enum"' in text and '"required"' in text
    # the full schema still enforces what was stripped
    bad = {"pass": "A", "sample_seed": "s", "findings": [], "prompt_injection_detected": False,
           "hallucinations": [{"finding_id": "F-7", "type": "false_gap", "severity": "minor", "status": "suspected",
                               "review_quote": "x" * 400, "reasoning": "r"}]}
    errs = schemas.errors(schemas.PASS_A, bad)
    assert any("F-7" in e for e in errs) and any("too long" in e for e in errs)


def _yaml_after(text: str, heading: str) -> dict:
    return yaml.safe_load(_block_after(text, heading))


@pytest.mark.parametrize(("src", "heading"), [("prompt", "## 6. Answer-key format"),
                                              ("examples", "## 6. Illustrative answer key")])
def test_grader_legacy_answer_keys_load(tmp_path: Path, src: str, heading: str) -> None:
    data = _yaml_after(MD if src == "prompt" else EXAMPLES, heading)
    p = tmp_path / "key.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    loaded = ak.load_answer_key(p)
    legacy, id_map = ak.project_key(loaded)
    pat = re.compile(schemas.load_schema(schemas.PASS_B)["properties"]["answer_key_alignment"]["properties"]
                     ["matched"]["items"]["properties"]["key_id"]["pattern"])
    assert legacy["key_items"] and all(pat.match(i["id"]) for i in legacy["key_items"])
    assert id_map.get("K01") == "K1"
    assert "K1" in ak.render_key(legacy) or "K01" in ak.render_key(legacy)


def test_grader_canonical_key_projection() -> None:
    key = {"item": {"document_id": "BKG-DD-001"}, "flaws": [
        {"id": "F01", "title": None, "description": "Quota below peak", "kind": "risk", "severity": "critical",
         "introduced_in": "v1", "v2_status": "fixed", "expected_disposition": "refinement_now",
         "location": {"sections": ["6.2"], "page": 11}},
        {"id": "F02", "title": "New in v2", "description": "d", "kind": "gap", "severity": "low",
         "introduced_in": "v2", "v2_status": "introduced", "expected_disposition": None,
         "location": {"sections": ["7"], "page": None}}],
        "sound_sections": [{"id": "S01", "why_sound": "Two-tier isolation", "trap": "Claims co-mingling",
                            "location": {"sections": ["11.3"], "page": 18}, "applies_to_versions": ["v1", "v2"]}]}
    loaded = {"format": "canonical", "canonical": key, "source": "k.json"}
    v1, _ = ak.project_key(loaded, review_mode="full")
    assert [i["id"] for i in v1["key_items"]] == ["F01"]
    assert v1["key_items"][0] == {"id": "F01", "title": "Quota below peak", "locations": ["6.2", "p.11"],
                                  "category": "risk", "materiality": "high", "expected_triage": "refinement_now"}
    assert v1["traps"] == [{"id": "S01", "description": "Claims co-mingling", "truth": "Two-tier isolation"}]
    v2, _ = ak.project_key(loaded, review_mode="delta")
    assert [i["id"] for i in v2["key_items"]] == ["F02"]
