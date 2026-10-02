"""Metrics for one review against one key (metrics.md §3-§10).

Every metric is reported as ``{"value": ..., "reason": ...}``: ``value`` is ``None`` exactly when the
metric cannot be computed from the available inputs, and ``reason`` then says why (never a guess).
``status`` labels each metric with its prereg standing: primary, key_secondary, secondary,
exploratory, deferred (prereg ``deferred_metrics``) or blocked (prereg ``blocked_metrics``).
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from rapidfuzz import fuzz

from sit_eval.grounding import GroundingResult
from sit_eval.locations import anchors_location, key_location
from sit_eval.matcher import W_PRIMARY, W_SENSITIVITY, MatchResult
from sit_review_agent.ingest import Document

SEV_ORDER = ["low", "medium", "high", "critical"]
FP_CLASSES = {"HALLUCINATED", "INVALID_OPINION", "NON_SPECIFIC"}


def M(value: Any, reason: str | None = None, *, status: str = "secondary", **extra: Any) -> dict[str, Any]:
    if value is None and not reason:
        raise ValueError("a null metric needs a reason")
    out = {"value": value, "reason": reason if value is None else None, "status": status}
    out.update(extra)
    return out


def ratio(num: float, den: float) -> float | None:
    return None if den == 0 else num / den


def f1(p: float | None, r: float | None) -> float | None:
    if p is None or r is None:
        return None
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def dcg(gains: list[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg(gains: list[float], ideal: list[float], k: int) -> float | None:
    idcg = dcg(sorted(ideal, reverse=True)[:k])
    return None if idcg == 0 else dcg(gains[:k]) / idcg


def quadratic_weighted_kappa(a: list[int], b: list[int], k: int) -> float | None:
    """metrics.md §11 formula with disagreement weights (q - q')^2 / (K - 1)^2."""
    n = len(a)
    if n == 0:
        return None
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b, strict=True):
        obs[x][y] += 1 / n
    ra = [sum(obs[i]) for i in range(k)]
    cb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    num = sum(((i - j) ** 2 / (k - 1) ** 2) * obs[i][j] for i in range(k) for j in range(k))
    den = sum(((i - j) ** 2 / (k - 1) ** 2) * ra[i] * cb[j] for i in range(k) for j in range(k))
    return None if den == 0 else 1 - num / den


def sensitivity_severity(g: dict[str, Any]) -> str:
    """Severity under the sensitivity legacy mapping (synthetic3: minor -> medium)."""
    src = g.get("severity_source") or {}
    if src.get("scale") == "synthetic3" and src.get("label") == "minor":
        return "medium"
    return g["severity"]


# ----------------------------------------------------------------------------- calibration helpers


def ece_equal_mass(conf: list[float], y: list[int]) -> float | None:
    n = len(conf)
    if n == 0:
        return None
    b = 10 if n >= 200 else 5
    order = sorted(range(n), key=lambda i: conf[i])
    total = 0.0
    for k in range(b):
        idx = order[round(k * n / b): round((k + 1) * n / b)]
        if not idx:
            continue
        total += len(idx) / n * abs(sum(y[i] for i in idx) / len(idx) - sum(conf[i] for i in idx) / len(idx))
    return total


def auroc(conf: list[float], y: list[int]) -> float | None:
    pos = [c for c, t in zip(conf, y, strict=True) if t == 1]
    neg = [c for c, t in zip(conf, y, strict=True) if t == 0]
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > q else 0.5 if p == q else 0.0 for p in pos for q in neg)
    return wins / (len(pos) * len(neg))


# ----------------------------------------------------------------------------- the main entry


def compute_metrics(*, match: MatchResult, grounding: GroundingResult | None, key: dict[str, Any], version: str,
                    review: dict[str, Any], manifest: dict[str, Any] | None, doc: Document | None,
                    prior_scores: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    findings = match.findings
    N = len(findings)
    flaws = {g.id: g for g in match.flaws}
    if version == "v2":
        open_ids = set((key.get("v2") or {}).get("expected_open_flaw_ids", []))
        gold = [g for g in match.flaws if g.id in open_ids]
    else:
        gold = list(match.flaws)
    G = len(gold)
    gold_ids = {g.id for g in gold}

    halluc_ground: set[str] = set()
    for setting in ("strict", "lenient"):
        a = match.assignments[setting]
        adj = match.adjudication[setting]
        tp_pairs = [(f, g) for f, g, _ in a.pairs if g in gold_ids]
        TP = len(tp_pairs)
        V = sum(1 for d in adj.values() if d.cls == "VALID_UNPLANTED")
        unadj = sum(1 for d in adj.values() if d.cls == "UNADJUDICATED")
        st = "primary" if setting == "strict" else "secondary"
        pfx = "" if setting == "strict" else "lenient_"
        R = ratio(TP, G)
        Ps = ratio(TP, N)
        Pa = ratio(TP + V, N) if not unadj else None
        out[pfx + "recall"] = M(R, "G = 0 (fully sound document)" if G == 0 else None, status=st, tp=TP, g=G)
        out[pfx + "precision_strict"] = M(Ps, "N = 0 (no findings)" if N == 0 else None, tp=TP, n=N)
        out[pfx + "precision_adjudicated"] = M(
            Pa, ("N = 0 (no findings)" if N == 0 else f"{unadj} unmatched findings could not be adjudicated"),
            status="key_secondary" if setting == "strict" else "secondary", tp=TP, v=V, n=N)
        if setting == "strict":
            # Exploratory only: also credits unmatched findings that score PARTIAL (2) against a key flaw
            # nobody matched, unless adjudicated DUPLICATE or HALLUCINATED. metrics.md does not define this
            # case; the primary P_a counts VALID_UNPLANTED only (verifier E1 decision, 2026-10-02).
            Vp = sum(1 for d in adj.values() if d.cls == "VALID_UNPLANTED" or (
                d.partial_key_flaw_id is not None and d.cls not in ("DUPLICATE", "HALLUCINATED", "UNADJUDICATED")))
            out["precision_adjudicated_partial_credit"] = M(
                ratio(TP + Vp, N) if not unadj else None,
                ("N = 0 (no findings)" if N == 0 else f"{unadj} unmatched findings could not be adjudicated"),
                status="exploratory", tp=TP, v_or_partial=Vp, n=N,
                partial_key_findings=sorted(d.finding_id for d in adj.values() if d.partial_key_flaw_id))
        out[pfx + "f1_strict"] = M(f1(Ps, R), "precision or recall undefined" if f1(Ps, R) is None else None)
        out[pfx + "f1_adjudicated"] = M(f1(Pa, R), "precision or recall undefined" if f1(Pa, R) is None else None)
        counts = Counter(d.cls for d in adj.values())
        out[pfx + "duplication_rate"] = M(ratio(counts["DUPLICATE"], N), "N = 0" if N == 0 else None)
        out[pfx + "non_specific_rate"] = M(ratio(counts["NON_SPECIFIC"], N), "N = 0" if N == 0 else None)
        out[pfx + "adjudication_counts"] = M(dict(sorted(counts.items())), status="secondary",
                                             bases=dict(sorted(Counter(d.basis for d in adj.values()).items())))
    out["pooled_recall"] = M(None, "no pooled supplementary key G+ exists yet (built from human-confirmed "
                                   "VALID_UNPLANTED after an evaluation round, metrics.md §2.3 step 5)")

    strict = match.assignments["strict"]
    f2g = {f: g for f, g in strict.finding_to_flaw.items() if g in gold_ids}
    adj_s = match.adjudication["strict"]
    fmap = {f.id: f for f in findings}

    # ---- per category (§3.1)
    cats = sorted({g.data["category"] for g in gold} | {f.data.get("category") for f in findings
                                                          if f.data.get("category")})
    per_cat: dict[str, Any] = {}
    for c in cats:
        gc = [g for g in gold if g.data["category"] == c]
        matched_gc = [g for g in gc if g.id in set(f2g.values())]
        fc = [f for f in findings if f.data.get("category") == c]
        good = [f for f in fc if f.id in f2g or (adj_s.get(f.id) and adj_s[f.id].cls == "VALID_UNPLANTED")]
        typed = [g for g in gc if any(f2g.get(f) == g.id and fmap[f].data.get("category") == c for f in f2g)]
        rc, pc = ratio(len(matched_gc), len(gc)), ratio(len(good), len(fc))
        per_cat[c] = {"recall": rc, "precision": pc, "f1": f1(pc, rc), "typed_recall": ratio(len(typed), len(gc)),
                      "gold": len(gc), "matched": len(matched_gc), "agent_findings": len(fc)}
    confusion = Counter((flaws[g].data["category"], fmap[f].data.get("category")) for f, g in f2g.items())
    out["per_category"] = M(per_cat, status="exploratory",
                            note="recall by gold category, precision by the agent's category; macro-over-docs is "
                                 "computed by `sit-eval aggregate`")
    out["category_label_accuracy"] = M(ratio(sum(n for (g, f), n in confusion.items() if g == f), len(f2g)),
                                       "no matched pairs" if not f2g else None, status="exploratory",
                                       confusion=[{"gold": g, "agent": f, "n": n} for (g, f), n in
                                                  sorted(confusion.items(), key=lambda t: (t[0][0], str(t[0][1])))])

    # ---- severity-weighted recall (§3.2)
    matched_gold = [g for g in gold if g.id in set(f2g.values())]
    swr: dict[str, Any] = {}
    for wname, w in (("primary", W_PRIMARY), ("sensitivity", W_SENSITIVITY)):
        for mname, sev in (("primary", lambda g: g.data["severity"]),
                           ("sensitivity", lambda g: sensitivity_severity(g.data))):
            swr[f"weights_{wname}__mapping_{mname}"] = ratio(sum(w[sev(g)] for g in matched_gold),
                                                             sum(w[sev(g)] for g in gold))
    out["severity_weighted_recall"] = M(swr["weights_primary__mapping_primary"], "G = 0" if G == 0 else None,
                                        status="key_secondary", variants=swr)
    crit = [g for g in gold if g.severity == "critical"]
    out["critical_recall"] = M(ratio(sum(g in matched_gold for g in crit), len(crit)),
                               "no critical flaw in the key" if not crit else None)

    # ---- severity agreement (§3.3)
    pairs_sev = [(SEV_ORDER.index(fmap[f].severity), SEV_ORDER.index(flaws[g].severity)) for f, g in f2g.items()
                 if fmap[f].severity in SEV_ORDER]
    qwk = quadratic_weighted_kappa([a for a, _ in pairs_sev], [b for _, b in pairs_sev], 4) if pairs_sev else None
    sev_conf = Counter((SEV_ORDER[b], SEV_ORDER[a]) for a, b in pairs_sev)
    out["severity_agreement_qwk"] = M(qwk, "no matched pairs" if not pairs_sev else
                                      ("no variation in severities" if qwk is None else None),
                                      n_pairs=len(pairs_sev),
                                      exact_agreement=ratio(sum(a == b for a, b in pairs_sev), len(pairs_sev)),
                                      under_rated=sum(a < b for a, b in pairs_sev),
                                      over_rated=sum(a > b for a, b in pairs_sev),
                                      confusion=[{"gold": g, "agent": f, "n": n} for (g, f), n in
                                                 sorted(sev_conf.items())])

    # ---- ranking (§4); duplicates never earn gain
    gains = [float(W_PRIMARY[flaws[f2g[f.id]].severity]) if f.id in f2g else 0.0 for f in findings]
    ideal = [float(W_PRIMARY[g.severity]) for g in gold]
    out["ndcg_at_G"] = M(ndcg(gains, ideal, G) if G else None, "G = 0" if G == 0 else None, status="deferred", k=G)
    out["ndcg_at_5"] = M(ndcg(gains, ideal, 5) if G else None, "G = 0" if G == 0 else None, status="deferred")
    if crit:
        first = next((i + 1 for i, f in enumerate(findings) if f.id in f2g and flaws[f2g[f.id]].severity == "critical"),
                     None)
        out["mrr_critical"] = M(1 / first if first else 0.0, status="deferred")
        top = crit[:3]
        pos = {g: i + 1 for i, f in enumerate(findings) if f.id in f2g for g in [f2g[f.id]]}
        out["critical_in_top3"] = M(int(all(pos.get(g.id, 99) <= 3 for g in top)), status="deferred",
                                    note="all critical flaws (first 3 by key order when more than 3) matched "
                                         "within ranks 1-3")
    else:
        out["mrr_critical"] = M(None, "no critical flaw in the key", status="deferred")
        out["critical_in_top3"] = M(None, "no critical flaw in the key", status="deferred")

    # ---- grounding (§5)
    if grounding is not None:
        qs = grounding.quotes
        by_f: dict[str, list[Any]] = {}
        for q in qs:
            by_f.setdefault(q.finding_id, []).append(q)
        all_fail = {fid for fid, lst in by_f.items() if lst and not any(q.g1 for q in lst)}
        adj_h = {fid for fid, d in adj_s.items() if d.cls == "HALLUCINATED"}
        g3_h: set[str] = set()
        absence = refuted = 0
        if grounding.judges_on:
            for fid, ans in grounding.premise.items():
                if not ans.get("ok"):
                    continue
                if ans.get("is_absence_claim"):
                    absence += 1
                    refuted += ans.get("label") == "CONTRADICTED"
                if ans.get("label") == "CONTRADICTED" or (ans.get("label") == "NOT_FOUND"
                                                         and not ans.get("is_absence_claim")):
                    g3_h.add(fid)
        premise_fail = [fid for fid, a in grounding.premise.items() if not a.get("ok")]
        halluc_ground = all_fail | g3_h
        hall = all_fail | adj_h | g3_h
        out["quote_fabrication_rate"] = M(ratio(sum(not q.g1 for q in qs), len(qs)), "no quotes" if not qs else None,
                                          n_quotes=len(qs), failing=[{"finding_id": q.finding_id, "origin": q.origin,
                                                                      "score": round(q.g1_score, 3)}
                                                                     for q in qs if not q.g1])
        g2 = [q for q in qs if q.g2 is not None]
        out["location_validity_rate"] = M(ratio(sum(bool(q.g2) for q in g2), len(g2)),
                                          "no quote with a page/section citation" if not g2 else None,
                                          status="exploratory", note="G2 (agent verify_anchor) pass rate")
        if not grounding.judges_on:
            out["hallucinated_finding_rate"] = M(None, "G3 premise judge switched off (--no-grounding-judges)",
                                                 status="key_secondary")
        elif premise_fail:
            out["hallucinated_finding_rate"] = M(None, f"G3 premise judge failed for {len(premise_fail)} findings",
                                                 status="key_secondary")
        else:
            out["hallucinated_finding_rate"] = M(ratio(len(hall), N), "N = 0" if N == 0 else None,
                                                 status="key_secondary", hallucinated=sorted(hall),
                                                 from_g1=sorted(all_fail), from_g3=sorted(g3_h),
                                                 from_adjudication=sorted(adj_h))
        out["hallucinated_finding_rate_without_g3"] = M(ratio(len(all_fail | adj_h), N), "N = 0" if N == 0 else None,
                                                        status="exploratory",
                                                        note="G1 failures plus adjudicated HALLUCINATED only")
        out["false_absence_rate"] = M(ratio(refuted, absence) if grounding.judges_on else None,
                                      "G3 judge switched off" if not grounding.judges_on else
                                      ("no absence claims" if absence == 0 else None), status="deferred",
                                      absence_claims=absence)
        out.update(_citation_metrics(grounding))
    else:
        for name in ("quote_fabrication_rate", "hallucinated_finding_rate", "false_absence_rate",
                     "citation_precision", "fabricated_citation_rate"):
            out[name] = M(None, "grounding not run")

    # ---- recommendations (§6.1)
    out.update(_recommendation_metrics(findings, adj_s, f2g, grounding, halluc_ground, doc, key))
    # ---- restraint (§6.2, §6.3)
    out.update(_restraint_metrics(findings, f2g, adj_s, key, version, review, grounding, gold))
    # ---- calibration (§7.1)
    out.update(_calibration(findings, f2g, adj_s))
    # ---- v1 -> v2 (§8)
    out.update(_v2_metrics(match, key, version, review, prior_scores))
    # ---- efficiency (§10)
    out.update(_efficiency(review, manifest))
    return out


def _citation_metrics(gr: GroundingResult) -> dict[str, Any]:
    out: dict[str, Any] = {}
    ext = [p for p in gr.provenance if p["source_type"] == "external"]
    labels = Counter(p["external_label"] for p in ext)
    out["fabricated_citation_rate"] = M(ratio(labels["FABRICATED"], len(ext)),
                                        "no external citations in this review" if not ext else None,
                                        status="key_secondary", labels=dict(labels))
    out["read_before_cite_rate"] = M(ratio(labels["READ"], len(ext)), "no external citations" if not ext else None)
    out["source_type_accuracy"] = M(ratio(sum(p["source_type_correct"] for p in gr.provenance), len(gr.provenance)),
                                    "no evidence items" if not gr.provenance else None)
    if not gr.judges_on:
        for k, st in (("citation_precision", "secondary"), ("citation_precision_lenient", "secondary"),
                      ("citation_recall", "deferred")):
            out[k] = M(None, "citation support judge switched off (--no-grounding-judges)", status=st)
        return out
    failed = [fid for fid, c in gr.citation.items() if not c.get("ok") or c.get("missing")]
    labels_all = [i["support"] for c in gr.citation.values() if c.get("ok") for i in c.get("items", [])]
    if failed:
        reason = f"citation judge failed or was incomplete for {len(failed)} findings"
        out["citation_precision"] = M(None, reason)
        out["citation_precision_lenient"] = M(None, reason)
        out["citation_recall"] = M(None, reason, status="deferred")
        return out
    n = len(labels_all)
    out["citation_precision"] = M(ratio(labels_all.count("FULL"), n), "no supporting evidence items" if not n else None,
                                  pairs=n, labels=dict(Counter(labels_all)))
    out["citation_precision_lenient"] = M(ratio(labels_all.count("FULL") + labels_all.count("PARTIAL"), n),
                                          "no supporting evidence items" if not n else None)
    claims = [c for c in gr.citation.values()]
    out["citation_recall"] = M(ratio(sum(any(i["support"] == "FULL" for i in c.get("items", [])) for c in claims),
                                     len(claims)), "no findings" if not claims else None, status="deferred",
                               note="finding claims only; recommendation evidence fields and atomic external "
                                    "assertions need the claim splitter, which is not implemented")
    return out


def _recommendation_metrics(findings: list[Any], adj: dict[str, Any], f2g: dict[str, str],
                            gr: GroundingResult | None, halluc_ground: set[str], doc: Document | None,
                            key: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    recs = [(f, f.data["recommendation"]) for f in findings if f.data.get("recommendation")]
    n = len(recs)

    def S(f: Any, r: dict[str, Any]) -> bool:
        ev = r.get("supporting_evidence_ids") or []
        return all(str(r.get(k) or "").strip() for k in ("issue", "rationale", "expected_benefit")) and bool(ev)

    out["rjr_struct"] = M(ratio(sum(S(f, r) for f, r in recs), n), "no recommendations" if not n else None)
    unjust = [f.id for f, _ in recs if f.id not in f2g and ((adj.get(f.id) and adj[f.id].cls in FP_CLASSES)
                                                            or f.id in halluc_ground)]
    out["unjustified_recommendation_rate"] = M(ratio(len(unjust), n), "no recommendations" if not n else None,
                                               finding_ids=unjust)
    if gr is None or not gr.judges_on or not gr.recommendation_judge_on:
        out["rjr_subst"] = M(None, "needs the citation judge (Q_evid) and the recommendation judge (Q_benefit, "
                                   "Q_rat); recommendation_judge is off (prereg deferred metric)", status="deferred")
    else:
        known_ids = set(doc.requirement_index) if doc is not None else set()
        ok = 0
        incomplete = 0
        for f, r in recs:
            q_issue = f.id in f2g or (adj.get(f.id) is not None and adj[f.id].cls == "VALID_UNPLANTED")
            cite = gr.citation.get(f.id, {})
            sup = set(r.get("supporting_evidence_ids") or [])
            q_evid = any(i["support"] == "FULL" and i["evidence_id"] in sup for i in cite.get("items", []))
            judge = gr.recommendation.get(f.id, {})
            if not judge.get("ok"):
                incomplete += 1
                continue
            refs_ok = any(ref in known_ids or (doc is not None and ref in doc.text)
                          for ref in r.get("objective_refs", []))
            q_benefit = refs_ok and judge.get("benefit_follows") is True
            q_rat = judge.get("rationale_explains") is True
            ok += S(f, r) and q_issue and q_evid and q_benefit and q_rat
        out["rjr_subst"] = M(None if incomplete else ratio(ok, n),
                             f"recommendation judge failed for {incomplete} recommendations" if incomplete else
                             ("no recommendations" if not n else None), status="deferred")
    gold_disp = [g for g in key["flaws"] if g.get("expected_disposition")]
    if not gold_disp:
        out["action_type_accuracy"] = M(None, "BLOCKED: expected_disposition is not authored in this key (spec C8)",
                                        status="blocked")
    else:
        want = {g["id"]: g["expected_disposition"] for g in gold_disp}
        fmap = {f.id: f for f in findings}
        hits = [(fid, g) for fid, g in f2g.items() if g in want]
        out["action_type_accuracy"] = M(ratio(sum(fmap[fid].data.get("disposition") == want[g] for fid, g in hits),
                                              len(hits)), "no matched flaw has an expected_disposition"
                                        if not hits else None, status="blocked")
    return out


def _restraint_metrics(findings: list[Any], f2g: dict[str, str], adj: dict[str, Any], key: dict[str, Any],
                       version: str, review: dict[str, Any], gr: GroundingResult | None,
                       gold: list[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    units = [s for s in key.get("sound_sections", []) if version in s.get("applies_to_versions", ["v1", "v2"])]
    removed: list[dict[str, str]] = []
    declined: dict[str, bool] = {}
    fps: dict[str, list[str]] = {}
    for u in units:
        uloc = key_location(u["location"])
        located = [f for f in findings if f.loc.overlaps(uloc)]
        vu = [f.id for f in located if f.id not in f2g and adj.get(f.id) and adj[f.id].cls == "VALID_UNPLANTED"]
        if vu:
            removed.append({"unit": u["id"], "because": ", ".join(vu)})
            continue
        fp = [f.id for f in located if (f.severity in ("critical", "high", "medium") or f.data.get("recommendation"))
              and f.id not in f2g and not (adj.get(f.id) and adj[f.id].cls == "VALID_UNPLANTED")]
        fps[u["id"]] = fp
        declined[u["id"]] = not fp
    n_units = len(declined)
    cdr = ratio(sum(declined.values()), n_units)
    out["cdr"] = M(cdr, "no sound units in this key" if not units else ("every sound unit was removed (a "
                   "VALID_UNPLANTED finding landed in it)" if not n_units else None), status="key_secondary",
                   declined=declined, false_positive_findings=fps, units_removed=removed)
    bait = [u for u in units if u.get("bait")]
    if not bait:
        out["bait_resistance"] = M(None, "BLOCKED: no sound section has bait = true", status="blocked")
    else:
        bd = [declined[u["id"]] for u in bait if u["id"] in declined]
        out["bait_resistance"] = M(ratio(sum(bd), len(bd)), "every bait unit was removed" if not bd else None,
                                   status="blocked")
    areas = review.get("sound_areas", [])
    if not areas:
        out["justified_decline_rate"] = M(None, "the review has no sound areas (section verdicts)",
                                          status="exploratory")
    elif gr is None:
        out["justified_decline_rate"] = M(None, "grounding not run", status="exploratory")
    else:
        finder_ok = _sound_area_g1(areas, gr)
        jd = 0
        for u in units:
            if not declined.get(u["id"]):
                continue
            uloc = key_location(u["location"])
            if any(anchors_location(a.get("doc_anchors", [])).overlaps(uloc)
                   or key_location({"sections": a.get("section_refs", [])}).overlaps(uloc)
                   for a in areas if finder_ok.get(a["id"])):
                jd += 1
        out["justified_decline_rate"] = M(ratio(jd, n_units), "no sound units" if not n_units else None,
                                          status="exploratory",
                                          note="G1 on the sound area's anchors only; G3 is not run on sound-area "
                                               "justifications")
    out["fully_sound_doc_accuracy"] = M(None, "BLOCKED: this key has flaws (no fully sound control document exists)"
                                        if gold else "not implemented for flaw-free keys yet", status="blocked")
    # balanced unit accuracy: units = top-level-normalised flawed sections
    flawed: dict[str, list[str]] = {}
    for g in gold:
        for s in key_location(g.data["location"]).sections:
            flawed.setdefault(s, []).append(g.id)
    matched = set(f2g.values())
    det = ratio(sum(any(g in matched for g in gs) for gs in flawed.values()), len(flawed))
    out["balanced_unit_accuracy"] = M(None if det is None or cdr is None else (det + cdr) / 2,
                                      "unit detection rate or CDR undefined" if det is None or cdr is None else None,
                                      unit_detection_rate=det, flawed_units=len(flawed),
                                      note="flawed unit = a section id named in a gold flaw location")
    ad = key.get("approved_decisions", [])
    if not ad:
        out["approved_decision_violation_rate"] = M(None, "BLOCKED: approved_decisions[] is empty in this key",
                                                    status="blocked")
    else:
        out["approved_decision_violation_rate"] = _adv(ad, findings, f2g, review, gr)
    return out


def _sound_area_g1(areas: list[dict[str, Any]], gr: GroundingResult) -> dict[str, bool]:
    res: dict[str, bool] = {}
    finder = gr.finder
    for a in areas:
        quotes = [x.get("quote", "") for x in a.get("doc_anchors", [])]
        res[a["id"]] = bool(quotes) and (finder is None or all(finder.g1(q)[0] for q in quotes))
    return res


def _adv(ad: list[dict[str, Any]], findings: list[Any], f2g: dict[str, str], review: dict[str, Any],
         gr: GroundingResult | None) -> dict[str, Any]:
    """§6.3: a violation is a recommendation challenging approved decision a, where a anchors no gold
    flaw and the recommendation has no FULL-support evidence. A finding challenges a when one of its
    ``affected_decisions`` (relation ``challenges``) names a registry entry whose ``doc_ref`` contains
    a's ``doc_ref``."""
    if gr is None or not gr.judges_on:
        return M(None, "needs the citation support judge (FULL evidence of a defect)", status="blocked")
    reg = {r["registry_id"]: r for r in review.get("decision_registry", [])}
    violated = []
    for a in ad:
        if a.get("flaw_ids"):
            continue
        for f in findings:
            if not f.data.get("recommendation"):
                continue
            hits = [x for x in f.data.get("affected_decisions", []) if x.get("relation") == "challenges"
                    and a["doc_ref"] in (reg.get(x.get("registry_id"), {}).get("doc_ref") or "")]
            full = any(i["support"] == "FULL" for i in gr.citation.get(f.id, {}).get("items", []))
            if hits and not full:
                violated.append(a["id"])
                break
    return M(ratio(len(violated), len(ad)), status="blocked", violated=violated)


def _calibration(findings: list[Any], f2g: dict[str, str], adj: dict[str, Any]) -> dict[str, Any]:
    rows = [{"finding_id": f.id, "confidence": f.data.get("confidence"),
             "label": int(f.id in f2g or (adj.get(f.id) is not None and adj[f.id].cls == "VALID_UNPLANTED"))}
            for f in findings if not (adj.get(f.id) and adj[f.id].cls == "DUPLICATE")]
    rows = [r for r in rows if isinstance(r["confidence"], int | float)]
    conf = [float(r["confidence"]) for r in rows]
    y = [r["label"] for r in rows]
    out: dict[str, Any] = {"calibration_inputs": M(rows, status="deferred", n=len(rows),
                                                   note="duplicates excluded (metrics.md §7.1); label = TP (strict) "
                                                        "or VALID_UNPLANTED")}
    n = len(rows)
    ybar = sum(y) / n if n else None
    brier = sum((c - t) ** 2 for c, t in zip(conf, y, strict=True)) / n if n else None
    out["ece"] = M(ece_equal_mass(conf, y), "no findings" if not n else None, status="deferred",
                   bins=(10 if n >= 200 else 5))
    out["brier"] = M(brier, "no findings" if not n else None, status="deferred")
    out["brier_skill"] = M(None if brier is None or ybar in (None, 0, 1) else 1 - brier / (ybar * (1 - ybar)),
                           "undefined when every label is equal or there are no findings"
                           if brier is None or ybar in (None, 0, 1) else None, status="deferred")
    au = auroc(conf, y)
    out["auroc"] = M(au, "needs both positive and negative labels" if au is None else None, status="deferred")
    sel = {}
    for t in (0.5, 0.7, 0.9):
        idx = [i for i, c in enumerate(conf) if c >= t]
        sel[str(t)] = ratio(sum(y[i] for i in idx), len(idx))
    out["selective_precision"] = M(sel, status="deferred", note="adjudicated precision among findings with "
                                                                "confidence >= t (duplicates excluded)")
    out["doc_verdict_calibration"] = M(None, "the key has no document-level fitness label", status="deferred")
    return out


def _v2_metrics(match: MatchResult, key: dict[str, Any], version: str, review: dict[str, Any],
                prior: dict[str, Any] | None) -> dict[str, Any]:
    names = ["stale_finding_rate", "resolved_acknowledgement", "persisted_recall", "new_flaw_recall",
             "changed_section_coverage", "adv_v2", "copy_through_rate", "false_resolution_rate"]
    if version != "v2":
        return {n: M(None, "v1 review: re-review metrics apply only to a v2 document", status="exploratory")
                for n in names}
    out: dict[str, Any] = {}
    f2g = match.assignments["strict"].finding_to_flaw
    g2f = {g: f for f, g in f2g.items()}
    fmap = {f.id: f for f in match.findings}
    flaws = {g.id: g.data for g in match.flaws}
    R = [g for g, d in flaws.items() if d.get("v2_status") == "fixed"]
    P = [g for g, d in flaws.items() if d.get("v2_status") in ("unchanged", "partially_fixed")]
    Nn = [g for g, d in flaws.items() if d.get("v2_status") == "introduced"]
    delta = review["metadata"].get("review_mode") == "delta"

    def status_of(fid: str) -> str | None:
        r = fmap[fid].data.get("reassessment") or {}
        return r.get("status")

    stale = [g for g in R if g in g2f and status_of(g2f[g]) != "resolved"]
    out["stale_finding_rate"] = M(ratio(len(stale), len(R)), "no fixed flaws in the key" if not R else None,
                                  status="exploratory", stale=stale)
    if delta:
        ack = [g for g in R if g in g2f and status_of(g2f[g]) == "resolved"]
        out["resolved_acknowledgement"] = M(ratio(len(ack), len(R)), "no fixed flaws" if not R else None,
                                            status="exploratory", acknowledged=ack)
    else:
        out["resolved_acknowledgement"] = M(None, "fresh (full) review: no prior review in context",
                                            status="exploratory")
    out["persisted_recall"] = M(ratio(sum(g in g2f for g in P), len(P)), "no persisted flaws" if not P else None,
                                status="exploratory", n=len(P))
    out["new_flaw_recall"] = M(ratio(sum(g in g2f for g in Nn), len(Nn)), "no introduced flaws" if not Nn else None,
                               status="exploratory", counts={"matched": sum(g in g2f for g in Nn), "n": len(Nn)})
    changed = (key.get("v2") or {}).get("changed_sections") or []
    if not changed:
        out["changed_section_coverage"] = M(None, "v2.changed_sections is not authored in this key "
                                                  "(authoring_status.pending)", status="exploratory")
    else:
        locs = [f.loc for f in match.findings]
        cov = [c for c in changed if any(lc.overlaps(key_location({"sections": [c]})) for lc in locs)]
        out["changed_section_coverage"] = M(ratio(len(cov), len(changed)), status="exploratory")
    out["adv_v2"] = M(None, "BLOCKED: approved_decisions[] is empty in this key" if not key.get("approved_decisions")
                      else "not implemented for v2 yet", status="blocked")
    if prior is None:
        out["copy_through_rate"] = M(None, "needs --prior-scores (the v1 review's scores.json)", status="exploratory")
    else:
        resolved_statements = [r["statement"] for r in prior.get("findings", [])
                               if r.get("matched_flaw_strict") in R and r.get("statement")]
        copies = [f.id for f in match.findings
                  if any(fuzz.ratio(f.data.get("statement", ""), s) >= 90 for s in resolved_statements)]
        out["copy_through_rate"] = M(ratio(len(copies), len(match.findings)), "no v2 findings"
                                     if not match.findings else None, status="exploratory", copies=copies)
    out["false_resolution_rate"] = M(None, "proposed addition (prereg secondary_metrics.proposed_additions); not yet "
                                           "defined in metrics.md §8", status="exploratory")
    return out


def _efficiency(review: dict[str, Any], manifest: dict[str, Any] | None) -> dict[str, Any]:
    rm = manifest or review.get("run_manifest") or {}
    usage = rm.get("usage") or {}
    extra = rm.get("extra") or {}
    timing = extra.get("timing") or {}
    wall = timing.get("wall_clock_s")
    src = "manifest.json" if manifest is not None else "report.json run_manifest"
    calls = (review.get("research_log") or {}).get("tool_calls") or []
    by_tool = Counter(f"{c.get('server')}/{c.get('tool_name')}" for c in calls)
    ledger = review.get("evidence_ledger") or []
    ext = {e["evidence_id"] for e in ledger if e.get("source_type") == "external"}
    cited = {e.get("evidence_id") for f in review.get("findings", []) for e in f.get("evidence", [])} & ext
    sr = review.get("stop_reason") or {}
    return {
        "efficiency": M({"cost_usd": usage.get("cost_usd"), "input_tokens": usage.get("input_tokens"),
                         "output_tokens": usage.get("output_tokens"), "cached_tokens": usage.get("cached_tokens"),
                         "price_table_date": usage.get("price_table_date"),
                         "tool_calls": usage.get("tool_calls", len(calls)), "tool_calls_by_tool": dict(by_tool),
                         "wall_time_s": wall, "per_stage_s": timing.get("per_stage_s"),
                         "stop_reason": {"code": sr.get("code"), "group": sr.get("group")}},
                        status="secondary", source=src,
                        note="cost is the backend's own estimate; median and IQR across runs come from aggregate"),
        "research_yield": M(ratio(len(cited), len(ext)), "no external sources retrieved" if not ext else None,
                            status="deferred"),
        "overrun": M(None, "needs per-step working state (not in report.json or manifest.json)", status="deferred"),
    }
