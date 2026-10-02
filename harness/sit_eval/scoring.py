"""``sit-eval score``: one review against one key -> ``scores.json`` + ``scores.md``.

The pipeline is :func:`score_review` (async, judge-agnostic). :func:`plan_calls` computes the
``--dry-run`` call count and cost range without any model call.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from sit_eval.calls import BudgetStop, JudgeRunner
from sit_eval.grounding import QuoteFinder, run_grounding
from sit_eval.loaders import DocInput, ReviewInput
from sit_eval.matcher import Matcher, MatcherSettings, MatchResult, finding_views, flaw_views
from sit_eval.metrics import compute_metrics
from sit_eval.paths import SCHEMAS_DIR

SCORES_SCHEMA_VERSION = "1.0"
PLUMBING_NOTE = ("PLUMBING ONLY: produced with the deterministic fake judge; the numbers are hashes, not judgements, "
                 "and must never be reported as a score")


@dataclass
class ScoreOptions:
    judge_kind: str
    model: str
    effort: str
    max_tokens: int
    samples: int
    seed: int
    granularity: str
    shortlist_k: int
    severity_epsilon: float
    concurrency: int
    max_cost_usd: float | None
    grounding_judges: bool
    recommendation_judge: bool
    theta_q: float
    condition: str | None = None
    embedding_prefilter: bool = False


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scores_schema() -> dict[str, Any]:
    return json.loads((SCHEMAS_DIR / "scores.schema.json").read_text(encoding="utf-8"))


def validate_scores(scores: dict[str, Any]) -> list[str]:
    v = Draft202012Validator(scores_schema())
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message[:200]}" for e in v.iter_errors(scores)]


# ----------------------------------------------------------------------------- dry run


def plan_calls(rin: ReviewInput, key: dict[str, Any], version: str, opts: ScoreOptions,
               per_call_usd: dict[str, float], per_call_s: dict[str, float]) -> dict[str, Any]:
    findings = finding_views(rin.data)
    flaws = flaw_views(key, version)
    N, G = len(findings), len(flaws)
    overlap = {g.id: [f.id for f in findings if f.loc.overlaps(g.loc)] for g in flaws}
    n_overlap = sum(len(v) for v in overlap.values())
    k = min(opts.shortlist_k, N)
    shortlist_calls = G if k > 0 and N > 0 else 0
    pairs_min, pairs_max = n_overlap, sum(min(N, len(v) + k) for v in overlap.values())
    if opts.granularity == "per_flaw_batch":
        flaws_min = sum(1 for v in overlap.values() if v)
        flaws_max = sum(1 for v in overlap.values() if v or k > 0)
        score_min, score_max = flaws_min * opts.samples, flaws_max * opts.samples
    else:
        score_min, score_max = pairs_min * opts.samples, pairs_max * opts.samples
    adj_min, adj_max = max(0, N - G), N
    premise = N if opts.grounding_judges else 0
    cite = sum(1 for f in findings if any(e.get("supports_claim") for e in f.data.get("evidence", []))) \
        if opts.grounding_judges else 0
    rec = sum(1 for f in findings if f.data.get("recommendation")) if opts.recommendation_judge else 0
    lo = shortlist_calls + score_min + adj_min + premise + cite + rec
    hi = shortlist_calls + score_max + adj_max + premise + cite + rec
    conc = max(1, opts.concurrency)
    return {
        "judge": opts.judge_kind, "granularity": opts.granularity, "samples": opts.samples,
        "findings_scored": N, "key_flaws": G, "location_overlap_pairs": n_overlap,
        "calls": {"shortlist": shortlist_calls, "pair_scoring": {"min": score_min, "max": score_max},
                  "adjudication": {"min": adj_min, "max": adj_max}, "premise_judge": premise,
                  "citation_judge": cite, "recommendation_judge": rec, "total": {"min": lo, "max": hi}},
        "cost_usd_estimate": {"low": round(lo * per_call_usd["low"], 2),
                              "typical": round((lo + hi) / 2 * per_call_usd["typical"], 2),
                              "high": round(hi * per_call_usd["high"], 2),
                              "basis": f"per call {per_call_usd} (config/eval.yaml cost_estimate); live costs vary"},
        "wall_time_min_estimate": {"low": round(lo * per_call_s["low"] / conc / 60, 1),
                                   "high": round(hi * per_call_s["high"] / conc / 60, 1), "concurrency": conc},
        "note": ("min assumes the shortlist adds no pair beyond location overlap and every flaw is matched; "
                 "max assumes it adds shortlist_k new pairs per flaw and every finding needs adjudication"),
    }


# ----------------------------------------------------------------------------- pipeline


async def score_review(*, rin: ReviewInput, key: dict[str, Any], key_path: Path, docin: DocInput, version: str,
                       runner: JudgeRunner | None, opts: ScoreOptions, prereg: dict[str, Any],
                       prompts_info: dict[str, Any], prior_scores: dict[str, Any] | None = None) -> dict[str, Any]:
    t0 = time.monotonic()
    warnings: list[str] = list(docin.warnings)
    if prereg.get("label") == "pilot_unfrozen":
        warnings.append(prereg["message"])
    if not key["authoring_status"]["scored_run_ready"]:
        warnings.append("answer key has scored_run_ready = false (pending: "
                        + ", ".join(key["authoring_status"]["pending"]) + "); core_insight is filled from the "
                        "description and credit items, so matcher scores are provisional")
    if prompts_info.get("problems"):
        warnings.append("judge prompts differ from prompts/PROMPTS.lock: " + "; ".join(prompts_info["problems"]))
    if opts.granularity != "pairwise":
        warnings.append("call granularity per_flaw_batch is a DEVIATION from prereg matcher.pairwise_scoring "
                        "(one call per pair); it needs the owner's approval before any scored run")
    if opts.samples != 3:
        warnings.append(f"samples = {opts.samples}: prereg matcher.pairwise_scoring says 3 samples, median")
    if not opts.grounding_judges:
        warnings.append("grounding judges switched off: G3 and citation support metrics are null")
    if opts.judge_kind == "fake":
        warnings.append(PLUMBING_NOTE)
    doc = docin.document
    doc_text = doc.text
    base = _base(rin, key, key_path, docin, version, opts, prereg, prompts_info)
    if runner is None:
        raise ValueError("a judge runner is required")
    matcher = Matcher(runner, MatcherSettings(granularity=opts.granularity, samples=opts.samples,
                                              shortlist_k=opts.shortlist_k, severity_epsilon=opts.severity_epsilon,
                                              seed=opts.seed), doc=doc)
    try:
        match = await matcher.run(rin.data, key, version, doc_text)
        finder = QuoteFinder(doc, opts.theta_q)
        grounding = await run_grounding(rin.data, match.findings, finder, runner, judges=opts.grounding_judges,
                                        recommendation_judge=opts.recommendation_judge, doc_text=doc_text)
    except BudgetStop as stop:
        await runner.drain()
        return {**base, "status": "stopped_budget", "warnings": warnings + [f"scoring stopped: {stop}"],
                "metrics": {}, "stop": {"reason": str(stop)}, "calls": runner.summary(),
                "elapsed_s": round(time.monotonic() - t0, 2)}
    metrics = compute_metrics(match=match, grounding=grounding, key=key, version=version, review=rin.data,
                              manifest=rin.manifest, doc=doc, prior_scores=prior_scores)
    failures = match.failures + grounding.failures
    if failures:
        warnings.append(f"{len(failures)} judge calls failed after retries; affected metrics are null or noted")
    status = "plumbing_only" if opts.judge_kind == "fake" else (
        "frozen" if prereg.get("label") == "frozen" else "pilot_unfrozen")
    return {**base, "status": status, "warnings": warnings, "metrics": metrics,
            **_details(match, grounding, opts.seed), "failures": failures, "calls": runner.summary(),
            "elapsed_s": round(time.monotonic() - t0, 2)}


def _base(rin: ReviewInput, key: dict[str, Any], key_path: Path, docin: DocInput, version: str, opts: ScoreOptions,
          prereg: dict[str, Any], prompts_info: dict[str, Any]) -> dict[str, Any]:
    rm = rin.data.get("run_manifest") or {}
    return {
        "schema_version": SCORES_SCHEMA_VERSION, "kind": "sit_eval.scores",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": {
            "report_path": str(rin.report_path), "report_sha256": file_sha256(rin.report_path),
            "review_id": rin.data["metadata"]["review_id"], "run_id": rin.data["metadata"]["run_id"],
            "review_mode": rin.data["metadata"]["review_mode"],
            "condition": opts.condition if opts.condition is not None else rm.get("condition"),
            "split": rm.get("split"),
            "key_path": str(key_path), "key_sha256": file_sha256(key_path), "item_id": key["item"]["item_id"],
            "key_split": key["item"]["split"], "scored_run_ready": key["authoring_status"]["scored_run_ready"],
            "doc_version": version, "doc_source": docin.source, "doc_sha256_text": docin.sha256_text,
            "doc_sha256_text_matches_review": docin.sha256_matches_review,
        },
        "prereg": prereg,
        "prompts": prompts_info,
        "judge": {**asdict(opts), "embedding_prefilter": False,
                  "blinding": "prompts carry no run id, model, condition, provenance or confidence; findings "
                              "shuffled per listwise call with the recorded seed"},
    }


def _details(match: MatchResult, grounding: Any, seed: int) -> dict[str, Any]:
    strict, lenient = match.assignments["strict"], match.assignments["lenient"]
    s_f2g, l_f2g = strict.finding_to_flaw, lenient.finding_to_flaw
    adj_s, adj_l = match.adjudication["strict"], match.adjudication["lenient"]
    best: dict[str, float] = {}
    for (_fid, gid), p in match.pairs.items():
        if p.median is not None:
            best[gid] = max(best.get(gid, 0.0), p.median)
    findings = [{"finding_id": f.id, "rank": f.rank, "kind": f.data.get("kind"), "category": f.data.get("category"),
                 "severity": f.severity, "confidence": f.data.get("confidence"), "statement": f.data.get("statement"),
                 "matched_flaw_strict": s_f2g.get(f.id), "matched_flaw_lenient": l_f2g.get(f.id),
                 "class_strict": adj_s[f.id].cls if f.id in adj_s else None,
                 "class_lenient": adj_l[f.id].cls if f.id in adj_l else None} for f in match.findings]
    s_g2f, l_g2f = strict.flaw_to_finding, lenient.flaw_to_finding
    flaws = [{"flaw_id": g.id, "severity": g.severity, "category": g.data["category"],
              "v2_status": g.data.get("v2_status"), "matched_finding_strict": s_g2f.get(g.id),
              "matched_finding_lenient": l_g2f.get(g.id), "best_score": best.get(g.id)} for g in match.flaws]
    pair_rows = [{"finding_id": p.finding_id, "flaw_id": p.flaw_id, "sources": p.sources, "samples": p.samples,
                  "median": p.median, "capped_samples": p.capped,
                  "rationales": [r.get("rationale") for r in p.raw if r]}
                 for p in sorted(match.pairs.values(), key=lambda p: (p.flaw_id, p.finding_id))]

    def adj_rows(adj: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"finding_id": d.finding_id, "class": d.cls, "basis": d.basis, "duplicate_of": d.duplicate_of,
                 "related_flaw_id": d.related_flaw_id, "observation_id": d.observation_id,
                 "rationale": d.rationale} for d in adj.values()]

    # human review queue (prereg matcher.adjudication.human_review; human_labelling_protocol T6)
    must = [d.finding_id for d in adj_s.values() if d.cls in ("VALID_UNPLANTED", "HALLUCINATED")]
    rest = sorted(d.finding_id for d in adj_s.values() if d.cls not in ("VALID_UNPLANTED", "HALLUCINATED"))
    rng = random.Random(seed)
    sample = sorted(rng.sample(rest, k=round(0.2 * len(rest)))) if rest else []
    return {
        "findings": findings, "flaws": flaws,
        "matching": {"granularity": match.granularity,
                     "candidates": {g: dict(sorted(c.items())) for g, c in sorted(match.candidates.items())},
                     "shortlist": match.shortlist, "pair_scores": pair_rows,
                     "strict": [{"finding_id": f, "flaw_id": g, "score": s} for f, g, s in strict.pairs],
                     "lenient": [{"finding_id": f, "flaw_id": g, "score": s} for f, g, s in lenient.pairs]},
        "adjudication": {"strict": adj_rows(adj_s), "lenient": adj_rows(adj_l),
                         "llm_answers": match.llm_adjudication},
        "grounding": {"quotes": [{"finding_id": q.finding_id, "origin": q.origin, "g1": q.g1,
                                  "g1_score": round(q.g1_score, 4), "g1_reason": q.g1_reason, "g2": q.g2,
                                  "g2_reasons": q.g2_reasons} for q in grounding.quotes],
                      "provenance": grounding.provenance, "premise": grounding.premise,
                      "citation": grounding.citation, "recommendation": grounding.recommendation},
        "human_review_queue": {"all_valid_unplanted_and_hallucinated": sorted(must),
                               "random_20pct_of_rest": sample,
                               "note": "S-heldout: a person reviews these (prereg matcher.adjudication.human_review); "
                                       "S-dev: the LLM first pass stands and is labelled as such"},
    }


def write_outputs(scores: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    from sit_eval.report_md import render_scores_md

    out_dir.mkdir(parents=True, exist_ok=True)
    js = out_dir / "scores.json"
    js.write_text(json.dumps(scores, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    md = out_dir / "scores.md"
    md.write_text(render_scores_md(scores), encoding="utf-8")
    return js, md
