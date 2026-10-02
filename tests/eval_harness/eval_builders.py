"""Builders shared by the harness tests (offline; FakeJudge only). Not a test module."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sit_eval.calls import JudgeRunner
from sit_eval.judge import FakeJudge, JudgeRequest
from sit_eval.loaders import DocInput, ReviewInput
from sit_eval.scoring import ScoreOptions, score_review
from sit_review_agent.ingest import Document

REPO = Path(__file__).resolve().parents[2]
LIVE_RUN = REPO / "docs" / "live_runs" / "live_cc_opus_payments_v1"
PAYMENTS_KEY = REPO / "eval" / "synthetic" / "payments_orchestration" / "answer_key.canonical.json"
PAYMENTS_PDF = REPO / "eval" / "synthetic" / "payments_orchestration" / "design_v1.pdf"

SECTION_SENTENCES = {
    "1": "The service shall authorise every payment request within two hundred milliseconds at peak load.",
    "2": "Idempotency keys are stored for twenty four hours in a shared cache keyed by the request id.",
    "3": "Settlement files are matched nightly against the ledger and every mismatch raises a ticket.",
    "4": "Operators sign in with a password and a one time code sent by text message to their phone.",
    "5": "The ledger is append only and every journal balances per currency at commit time always.",
    "8": "Fraud scoring is optional and the merchant may switch it off for any low value payment.",
    "9": "Webhooks are retried with exponential backoff for up to three days before being dropped.",
}


def doc_text() -> str:
    parts = []
    for page, (sec, sentence) in enumerate(SECTION_SENTENCES.items(), start=1):
        parts.append(f"[[PAGE {page}]]\n{sec} Section {sec} Heading\n{sentence}\n")
    return "".join(parts)


def page_of(section: str) -> int:
    return list(SECTION_SENTENCES).index(section) + 1


def make_flaw(fid: str, severity: str, section: str, *, category: str = "internal_contradiction",
              mode: str = "substance", introduced_in: str = "v1", v2_status: str = "not_applicable",
              label: str | None = None) -> dict[str, Any]:
    items = [{"id": "c1", "text": f"mechanism of {fid}", "role": "required"},
             {"id": "c2", "text": f"consequence of {fid}", "role": "required"},
             {"id": "c3", "text": "a remedy", "role": "supporting"}]
    return {"id": fid, "title": None, "kind": "risk", "acceptable_kinds": ["risk"], "category": category, "tags": [],
            "severity": severity,
            "severity_source": {"scale": "synthetic3" if label else "canonical4", "label": label or severity},
            "planted": True, "introduced_in": introduced_in, "introduced_by_fix_of": None, "v2_status": v2_status,
            "caused_regression_flaw_id": None, "v2_note": None,
            "location": {"sections": [section], "requirement_ids": [], "decision_ids": [], "anchor_quote": None,
                         "page": None},
            "description": f"Flaw {fid} described in section {section}.", "rationale": f"Why {fid} matters.",
            "core_insight": None,
            "credit": {"mode": mode, "items": items, "min_required": 1 if mode == "any_of" else None},
            "needs_external_research": False, "external_fact": None, "expected_disposition": None,
            "acceptable_dispositions": [], "affected_decisions": [], "acceptable_fix": None,
            "distractor_notes": None, "overlapping_sound_section_ids": [], "disambiguation": None}


def make_key(flaws: list[dict[str, Any]], *, sound: list[dict[str, Any]] | None = None, v2: bool = False,
             observations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "item": {"item_id": "test-item-001", "split": "S-dev", "domain": "test",
                 "documents": {"v1": {"path": "design_v1.md", "sha256": None},
                               "v2": {"path": "design_v2.md", "sha256": None} if v2 else None},
                 "document_id": None, "canary_guid": None, "author_type": "unknown", "author_model": None,
                 "generation_date": None, "generator_session_ref": None, "brief_sha256": None,
                 "key_reviewed_by": [], "notes": None,
                 "source_key": {"path": None, "format": "canonical", "sha256": None}},
        "scoring": {"matching_rule": "core_insight_plus_location_v1", "default_credit_mode": "substance",
                    "severity_mapping": {"source_scale": "canonical4", "variant": "primary"},
                    "severity_tolerance": None, "notes": None},
        "approved_decisions": [], "flaws": flaws, "sound_sections": sound or [],
        "still_valid_observations": observations or [],
        "v2": ({"changed_sections": [], "notes": None,
                "expected_open_flaw_ids": [f["id"] for f in flaws
                                           if f["v2_status"] in ("unchanged", "partially_fixed", "introduced")]}
               if v2 else None),
        "authoring_status": {"pending": ["core_insight", "author_model", "author_type"], "scored_run_ready": False},
    }


def make_sound(sid: str, section: str) -> dict[str, Any]:
    return {"id": sid, "location": {"sections": [section], "requirement_ids": [], "decision_ids": [],
                                    "anchor_quote": None, "page": None},
            "why_sound": "It is fine.", "trap": "Calling it unsafe.", "still_valid_observations": [],
            "overlapping_flaw_ids": [], "applies_to_versions": ["v1", "v2"], "bait": False, "disambiguation": None}


def make_finding(n: int, section: str, *, severity: str = "high", confidence: float = 0.8,
                 category: str = "internal_contradiction", rank: int | None = None, statement: str | None = None,
                 recommendation: bool = True, reassessment: dict[str, Any] | None = None) -> dict[str, Any]:
    fid = f"FND-{n:03d}"
    quote = SECTION_SENTENCES[section]
    ev = {"evidence_id": f"EV-{n:03d}", "source_type": "doc",
          "url_or_citation": f"doc:DOC-test#p{page_of(section)}/s{section}", "quote": quote, "supports_claim": True,
          "retrieved_at": None, "derived_from": []}
    rec = ({"issue": "an issue", "rationale": "a rationale", "expected_benefit": "FR-1 holds",
            "change_summary": "change it", "objective_refs": ["FR-1"], "supporting_evidence_ids": [ev["evidence_id"]],
            "verification": None} if recommendation else None)
    return {"id": fid, "rank": rank or n, "kind": "risk", "category": category, "severity": severity,
            "confidence": confidence, "disposition": "refinement_now", "secondary_dispositions": [],
            "title": f"Finding {n}", "statement": statement or f"Finding {n} says something about section {section}.",
            "doc_anchors": [{"doc_id": "DOC-test", "section_ref": section, "requirement_ids": [], "quote": quote,
                             "page": page_of(section)}],
            "evidence": [ev], "recommendation": rec, "no_change_rationale": None, "next_step": None,
            "affected_decisions": [], "acknowledged_in_doc": False, "tags": [], "reassessment": reassessment,
            "provenance": {"phase": "assess", "iteration": 0, "model": "claude-opus-5-5",
                           "prompt_hash": "0" * 64}}


def make_review(findings: list[dict[str, Any]], *, mode: str = "full") -> dict[str, Any]:
    ledger = [{"evidence_id": e["evidence_id"], "source_type": "doc", "authority": None, "tool": None,
               "url_or_citation": e["url_or_citation"], "title": None, "retrieved_at": None, "content_sha256": None,
               "snapshot_path": None, "excerpt": e["quote"], "read_before_cite": True, "derived_from": []}
              for f in findings for e in f["evidence"]]
    return {"schema_version": "1.0",
            "metadata": {"review_id": "REV-secret-run-opus", "run_id": "secret-run-opus", "review_mode": mode,
                         "created_at": "2026-10-02T00:00:00Z", "prior_review_id": None, "taxonomy_version": "1.0",
                         "documents": [{"doc_id": "DOC-test", "title": "Test", "version": "1.0",
                                        "role": "under_review", "sha256_pdf": None, "sha256_text": None,
                                        "text_path": "text/DOC-test.pages.txt", "page_count": 7}]},
            "findings": findings, "evidence_ledger": ledger, "sound_areas": [], "decision_registry": [],
            "research_log": {"tool_calls": []}, "stop_reason": {"code": "sufficient_evidence", "group": "decision"},
            "run_manifest": {"condition": "FULL-secret-condition", "split": "S-dev",
                             "usage": {"cost_usd": 1.5, "input_tokens": 10, "output_tokens": 5, "cached_tokens": 0,
                                       "tool_calls": 0}}}


def responder_from(table: dict[str, Callable[[JudgeRequest], dict[str, Any]]]
                   ) -> Callable[[JudgeRequest], dict[str, Any]]:
    """Dispatch on the purpose prefix (``match.pair``, ``adjudicate``, ...)."""
    def respond(req: JudgeRequest) -> dict[str, Any]:
        kind = req.purpose.split(":", 1)[0]
        return table[kind](req)
    return respond


_HINT = re.compile(r"overlapping the flaw's location: (.*)")
_K = re.compile(r"Return up to (\d+) finding ids")


def overlap_hint(user: str) -> list[str]:
    """The finding ids the shortlist prompt names as sharing a location with the flaw."""
    m = _HINT.search(user)
    text = m.group(1).strip() if m else "none"
    return [] if text == "none" else [x.strip() for x in text.split(",")]


def hint_shortlist(r: JudgeRequest) -> dict[str, Any]:
    """Fake shortlist that returns the location-hinted findings (up to K, in prompt order). With at most
    K overlapping findings per flaw, shortlist_bounded then scores the same pairs as overlap alone did."""
    k = int(_K.search(r.user).group(1))  # type: ignore[union-attr]
    return {"candidate_ids": overlap_hint(r.user)[:k], "rationale": "x"}


def default_table() -> dict[str, Callable[[JudgeRequest], dict[str, Any]]]:
    return {
        "match.shortlist": hint_shortlist,
        "match.pair": lambda r: pair(0),
        "adjudicate": lambda r: adj("VALID_UNPLANTED"),
        "ground.premise": lambda r: {"is_absence_claim": False, "premise": "p", "label": "SUPPORTED",
                                     "doc_passage": None, "rationale": "x"},
        "ground.cite": lambda r: {"items": [{"evidence_id": e, "support": "FULL", "rationale": "x"}
                                            for e in sorted(set(re.findall(r'"evidence_id": "([^"]+)"', r.user)))]},
        "rec": lambda r: {"benefit_follows": True, "rationale_explains": True, "rationale": "x"},
    }


def pair(score: int, location_ok: bool = True) -> dict[str, Any]:
    return {"score": score, "core_insight_present": "yes" if score == 3 else "no", "location_ok": location_ok,
            "credit_items_stated": [], "rationale": "x"}


def adj(cls: str, duplicate_of: str | None = None, obs: str | None = None) -> dict[str, Any]:
    return {"class": cls, "duplicate_of": duplicate_of, "matches_observation_id": obs, "rationale": "x"}


def options(**over: Any) -> ScoreOptions:
    base = dict(judge_kind="fake", model="claude-opus-5-5", effort="high", max_tokens=1000, samples=3, seed=7,
                granularity="pairwise", shortlist_k=3, severity_epsilon=0.01, concurrency=4, max_cost_usd=None,
                grounding_judges=True, recommendation_judge=False, theta_q=0.90, condition=None)
    base.update(over)
    return ScoreOptions(**base)


def run_pipeline(tmp_path: Path, review: dict[str, Any], key: dict[str, Any], responder: Callable[..., Any], *,
                 version: str = "v1", judge: Any = None, reserve_usd: float = 0.0, prior: dict[str, Any] | None = None,
                 out_dir: Path | None = None, **opts: Any) -> tuple[dict[str, Any], Any, JudgeRunner]:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(review), encoding="utf-8")
    key_path = tmp_path / "key.json"
    key_path.write_text(json.dumps(key), encoding="utf-8")
    doc = Document.from_page_marked_text(doc_text(), doc_id="DOC-test")
    docin = DocInput(document=doc, source="test", sha256_text=doc.sha256_text, sha256_matches_review=None)
    rin = ReviewInput(data=review, review=None, report_path=report, run_dir=tmp_path, manifest=None)  # type: ignore[arg-type]
    o = options(**opts)
    fake = judge if judge is not None else FakeJudge(responder)
    runner = JudgeRunner(fake, model=o.model, effort=o.effort, max_tokens=o.max_tokens, concurrency=o.concurrency,
                         max_cost_usd=o.max_cost_usd, reserve_usd=reserve_usd, out_dir=out_dir)
    prereg = {"frozen": False, "label": "pilot_unfrozen", "message": "unfrozen (test)"}
    prompts_info = {"bundle_sha256": "0" * 64, "lock_ok": True, "problems": []}
    scores = asyncio.run(score_review(rin=rin, key=key, key_path=key_path, docin=docin, version=version,
                                      runner=runner, opts=o, prereg=prereg, prompts_info=prompts_info,
                                      prior_scores=prior))
    return scores, fake, runner
