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
    adaptive_samples: bool = False
    candidate_rule: str = "shortlist_bounded"   # union = DEVIATION (the pre-2026-10-02 rule, comparison only)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scores_schema() -> dict[str, Any]:
    return json.loads((SCHEMAS_DIR / "scores.schema.json").read_text(encoding="utf-8"))


def validate_scores(scores: dict[str, Any]) -> list[str]:
    v = Draft202012Validator(scores_schema())
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message[:200]}" for e in v.iter_errors(scores)]


# ----------------------------------------------------------------------------- dry run


def plan_calls(rin: ReviewInput, key: dict[str, Any], version: str, opts: ScoreOptions,
               per_call_usd: dict[str, float], per_call_s: dict[str, float],
               basis_model: str = "claude-opus-5-5", per_kind_usd: dict[str, float] | None = None) -> dict[str, Any]:
    """Call counts (min and max) for scoring one review, priced per call kind when ``per_kind_usd`` is
    given (else at the flat ``per_call_usd`` low / typical / high)."""
    findings = finding_views(rin.data)
    flaws = flaw_views(key, version)
    N, G = len(findings), len(flaws)
    overlap = {g.id: [f.id for f in findings if f.loc.overlaps(g.loc)] for g in flaws}
    n_overlap = sum(len(v) for v in overlap.values())
    k = min(opts.shortlist_k, N)
    shortlist_calls = G if k > 0 and N > 0 else 0
    union = opts.candidate_rule == "union"
    if union:
        per_flaw = {g: (len(v), min(N, len(v) + k)) for g, v in overlap.items()}
    else:   # shortlist_bounded: the shortlist returns 0..k findings per flaw and nothing else is scored
        per_flaw = {g: (0, k) for g in overlap}
    pairs_min, pairs_max = sum(a for a, _ in per_flaw.values()), sum(b for _, b in per_flaw.values())
    adaptive = opts.adaptive_samples and opts.samples == 3
    lo_samples = 2 if adaptive else opts.samples
    batch = opts.granularity == "per_flaw_batch"
    if batch:
        flaws_min = sum(1 for a, _ in per_flaw.values() if a)
        flaws_max = sum(1 for _, b in per_flaw.values() if b)
        score_min, score_max = flaws_min * lo_samples, flaws_max * opts.samples
    else:
        score_min, score_max = pairs_min * lo_samples, pairs_max * opts.samples
    adj_min, adj_max = max(0, N - G), N
    premise = N if opts.grounding_judges else 0
    cite = sum(1 for f in findings if any(e.get("supports_claim") for e in f.data.get("evidence", []))) \
        if opts.grounding_judges else 0
    rec = sum(1 for f in findings if f.data.get("recommendation")) if opts.recommendation_judge else 0
    lo = shortlist_calls + score_min + adj_min + premise + cite + rec
    hi = shortlist_calls + score_max + adj_max + premise + cite + rec
    conc = max(1, opts.concurrency)
    score_kind = "batch" if batch else "pair"
    kinds_min = {"shortlist": shortlist_calls, score_kind: score_min, "adjudicate": adj_min, "premise": premise,
                 "citation": cite, "recommendation": rec}
    kinds_max = {**kinds_min, score_kind: score_max, "adjudicate": adj_max}
    if per_kind_usd:
        def price(kind: str) -> float:
            return per_kind_usd.get(kind, per_call_usd["typical"])

        cost_lo = sum(n * price(kd) for kd, n in kinds_min.items())
        cost_hi = sum(n * price(kd) for kd, n in kinds_max.items())
        cost = {"low": round(cost_lo, 2), "typical": round((cost_lo + cost_hi) / 2, 2), "high": round(cost_hi, 2),
                "by_kind_at_max": {kd: round(n * price(kd), 2) for kd, n in kinds_max.items() if n},
                "basis": (f"per call kind {per_kind_usd} for {basis_model} at effort high via claude -p "
                          "(config/eval.yaml cost_estimate.per_kind_usd): shortlist, batch and adjudicate measured "
                          "on the 2026-10-02 pilot; pair, premise, citation and recommendation estimated. low = the "
                          "min call plan, high = the max call plan")}
    else:
        cost = {"low": round(lo * per_call_usd["low"], 2), "typical": round((lo + hi) / 2 * per_call_usd["typical"], 2),
                "high": round(hi * per_call_usd["high"], 2),
                "basis": f"flat per call {per_call_usd} for {basis_model} (config/eval.yaml cost_estimate)"}
    caveats = ["retries of failed attempts are not counted (each live call may retry up to judge.max_retries "
               "times, and a failed attempt can still cost money)",
               ("prices per call kind (USD): " + ", ".join(f"{kd} {v:g}" for kd, v in per_kind_usd.items())
                + "; shortlist, batch and adjudicate are pilot means (2026-10-02, claude -p, Opus high), the others "
                "were not in the pilot and are estimates; whole-document calls (adjudicate, premise) cost about ten "
                "times a pair call" if per_kind_usd else
                "adjudication and premise calls carry the whole document, so they cost several times a pair call; "
                "the flat per-call price averages over call kinds"),
               ("candidate_rule union: the shortlist decides where between min (overlap only) and max (overlap plus "
                "shortlist_k new findings per flaw) pair scoring lands" if union else
                "candidate_rule shortlist_bounded: the shortlist decides how many findings per flaw are scored, "
                f"between 0 and shortlist_k ({k}); the 2026-10-02 pilot shortlist returned 28 ids for 14 flaws "
                "(2.0 per flaw, two thirds of the max)")]
    if opts.model != basis_model:
        caveats.insert(0, f"per-call prices are a planning basis for {basis_model} (effort high); this run uses "
                          f"{opts.model}, so the USD figures do not apply to it (calls do)")
    if union:
        note = ("candidate_rule union (DEVIATION from the amended prereg): min assumes the shortlist adds no pair "
                "beyond location overlap and every flaw is matched; max assumes it adds shortlist_k new pairs per "
                "flaw and every finding needs adjudication")
    else:
        note = ("candidate_rule shortlist_bounded (prereg matcher.candidates as amended 2026-10-02): only "
                "shortlisted findings are scored, location overlap is a hint to the shortlist; min assumes every "
                "shortlist is empty and every flaw is matched, max assumes shortlist_k findings per flaw and every "
                "finding needs adjudication")
    return {
        "judge": opts.judge_kind, "granularity": opts.granularity, "candidate_rule": opts.candidate_rule,
        "samples": opts.samples, "adaptive_third_sample": adaptive,
        "findings_scored": N, "key_flaws": G, "location_overlap_pairs": n_overlap,
        "candidate_pairs": {"min": pairs_min, "max": pairs_max},
        "calls": {"shortlist": shortlist_calls, "pair_scoring": {"min": score_min, "max": score_max},
                  "adjudication": {"min": adj_min, "max": adj_max}, "premise_judge": premise,
                  "citation_judge": cite, "recommendation_judge": rec, "total": {"min": lo, "max": hi}},
        "cost_usd_estimate": cost,
        "wall_time_min_estimate": {"low": round(lo * per_call_s["low"] / conc / 60, 1),
                                   "high": round(hi * per_call_s["high"] / conc / 60, 1), "concurrency": conc},
        "note": note,
        "caveats": caveats,
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
    if opts.candidate_rule == "union":
        warnings.append("candidate_rule union (location overlap union shortlist) is a DEVIATION from prereg "
                        "matcher.candidates as amended 2026-10-02 (the shortlist bounds pairwise scoring); "
                        "comparison only")
    if opts.samples != 3:
        warnings.append(f"samples = {opts.samples}: prereg matcher.pairwise_scoring says 3 samples, median")
    elif opts.adaptive_samples:
        warnings.append("adaptive third sample: the third pairwise sample is asked only when the first two "
                        "disagree or one failed (the median of 3 is then unchanged); this reading of prereg "
                        "'3 samples, median' needs the owner's approval before any scored run")
    if not opts.grounding_judges:
        warnings.append("grounding judges switched off: G3 and citation support metrics are null")
    if opts.judge_kind == "fake":
        warnings.append(PLUMBING_NOTE)
    doc = docin.document
    doc_text = doc.text
    base = _base(rin, key, key_path, docin, version, opts, prereg, prompts_info)
    if runner is None:
        raise ValueError("a judge runner is required")
    matcher = Matcher(runner, MatcherSettings(granularity=opts.granularity, candidate_rule=opts.candidate_rule,
                                              samples=opts.samples,
                                              shortlist_k=opts.shortlist_k, severity_epsilon=opts.severity_epsilon,
                                              seed=opts.seed, adaptive_third_sample=opts.adaptive_samples),
                      doc=doc)
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
    if match.shortlist_failed and match.candidate_rule == "shortlist_bounded":
        warnings.append(f"shortlist failed for {', '.join(match.shortlist_failed)}: under shortlist_bounded these "
                        "flaws had no candidates and count as unmatched, so recall and the recall-based metrics "
                        "are lower bounds; re-run into the same --out to retry only the failed calls")
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
              "matched_finding_lenient": l_g2f.get(g.id), "best_score": best.get(g.id),
              "shortlist_ok": bool(match.shortlist.get(g.id, {}).get("ok", True))} for g in match.flaws]
    pair_rows = [{"finding_id": p.finding_id, "flaw_id": p.flaw_id, "sources": p.sources, "samples": p.samples,
                  "median": p.median, "capped_samples": p.capped, "skipped_samples": p.skipped,
                  "rationales": [r.get("rationale") for r in p.raw if r]}
                 for p in sorted(match.pairs.values(), key=lambda p: (p.flaw_id, p.finding_id))]

    def adj_rows(adj: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"finding_id": d.finding_id, "class": d.cls, "basis": d.basis, "duplicate_of": d.duplicate_of,
                 "related_flaw_id": d.related_flaw_id, "observation_id": d.observation_id,
                 "partial_key_flaw_id": d.partial_key_flaw_id, "rationale": d.rationale} for d in adj.values()]

    # human review queue (prereg matcher.adjudication.human_review; human_labelling_protocol T6)
    must = [d.finding_id for d in adj_s.values() if d.cls in ("VALID_UNPLANTED", "HALLUCINATED")]
    rest = sorted(d.finding_id for d in adj_s.values() if d.cls not in ("VALID_UNPLANTED", "HALLUCINATED"))
    rng = random.Random(seed)
    sample = sorted(rng.sample(rest, k=round(0.2 * len(rest)))) if rest else []
    return {
        "findings": findings, "flaws": flaws,
        "matching": {"granularity": match.granularity, "candidate_rule": match.candidate_rule,
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
