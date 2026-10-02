"""``sit-eval aggregate``: several ``scores.json`` -> per-condition estimates with cluster-bootstrap CIs
and, with ``--compare A B``, paired differences, the document-level sign-flip test, the stratified
flaw-level permutation test and McNemar (metrics.md §12, prereg ``statistics``).

Runs of A and B on the same document are paired by their order (sorted run id). Holm / BH are left
to the analysis step that knows the prereg families (``sit_eval.stats.holm``).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sit_eval import stats

DEFAULT_METRICS = ["recall", "lenient_recall", "precision_strict", "precision_adjudicated", "f1_adjudicated",
                   "severity_weighted_recall", "critical_recall", "hallucinated_finding_rate", "cdr",
                   "quote_fabrication_rate", "duplication_rate"]


def load_scores(paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    rows, warnings = [], []
    for p in paths:
        s = json.loads(Path(p).read_text(encoding="utf-8"))
        if s.get("kind") != "sit_eval.scores":
            warnings.append(f"{p}: not a scores.json; skipped")
            continue
        if s["status"] == "stopped_budget":
            warnings.append(f"{p}: stopped at the cost limit; counted as missing")
            continue
        if s["status"] == "plumbing_only":
            warnings.append(f"{p}: PLUMBING ONLY (fake judge)")
        if s["status"] == "pilot_unfrozen":
            warnings.append(f"{p}: unfrozen pilot score")
        s["_path"] = str(p)
        rows.append(s)
    return rows, warnings


def _doc(s: dict[str, Any]) -> str:
    return f"{s['inputs']['item_id']}:{s['inputs']['doc_version']}"


def _cond(s: dict[str, Any]) -> str:
    return s["inputs"].get("condition") or "unlabelled"


def aggregate(paths: list[Path], *, metrics: list[str] | None = None, compare: tuple[str, str] | None = None,
              B: int = 10_000, seed: int = 0, paired_seed: int = 1) -> dict[str, Any]:
    rows, warnings = load_scores(paths)
    metrics = metrics or DEFAULT_METRICS
    by: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for s in rows:
        by[_cond(s)][_doc(s)].append(s)
    for cond in by:
        for d in by[cond]:
            by[cond][d].sort(key=lambda s: s["inputs"]["run_id"])
    out: dict[str, Any] = {"kind": "sit_eval.aggregate", "inputs": [s["_path"] for s in rows], "warnings": warnings,
                           "aggregation": "per run -> mean over a document's runs -> mean over documents (macro); "
                                          "micro recall pools TP and G within each run index",
                           "bootstrap": {"B": B, "seed": seed, "paired_seed": paired_seed}, "conditions": {}}
    for cond, docs in sorted(by.items()):
        res: dict[str, Any] = {"documents": {d: len(v) for d, v in sorted(docs.items())}}
        for m in metrics:
            per = {d: [(s["metrics"].get(m) or {}).get("value") for s in v] for d, v in docs.items()}
            point, ci = stats.cluster_bootstrap(per, B=B, seed=seed)
            n_null = sum(x is None for v in per.values() for x in v)
            res[m] = {"macro": point, "ci95": list(ci) if ci else None, "runs": sum(len(v) for v in per.values()),
                      "undefined_runs": n_null}
        recall_nd = {d: [(s["metrics"]["recall"]["tp"], s["metrics"]["recall"]["g"]) for s in v
                         if "recall" in s["metrics"] and s["metrics"]["recall"].get("g")] for d, v in docs.items()}
        mp, mci = stats.cluster_bootstrap_ratio(recall_nd, B=B, seed=seed)
        res["recall_micro"] = {"value": stats.micro_point({d: list(v) for d, v in recall_nd.items()}),
                               "pooled": mp, "ci95": list(mci) if mci else None}
        out["conditions"][cond] = res
    if compare:
        out["comparison"] = _compare(by, compare, metrics, B=B, paired_seed=paired_seed)
    return out


def _compare(by: dict[str, Any], compare: tuple[str, str], metrics: list[str], *, B: int,
             paired_seed: int) -> dict[str, Any]:
    a_name, b_name = compare
    A, Bc = by.get(a_name, {}), by.get(b_name, {})
    docs = sorted(set(A) & set(Bc))
    res: dict[str, Any] = {"a": a_name, "b": b_name, "documents": docs}
    for m in metrics:
        pa = {d: [x for x in ((s["metrics"].get(m) or {}).get("value") for s in A[d]) if x is not None] for d in docs}
        pb = {d: [x for x in ((s["metrics"].get(m) or {}).get("value") for s in Bc[d]) if x is not None] for d in docs}
        pd = stats.paired_diff(pa, pb, B=B, seed=paired_seed)
        diffs = {d: stats.mean(pa[d]) - stats.mean(pb[d]) for d in docs if pa[d] and pb[d]}
        res[m] = {"paired_bootstrap": {**pd, "ci": list(pd["ci"]) if pd["ci"] else None},
                  "sign_flip": stats.sign_flip_test(diffs)}
    # flaw-level outcomes (strict detection), runs paired by order
    pairs_by_doc: dict[str, list[tuple[int, int]]] = {}
    b = c = 0
    for d in docs:
        rows = []
        for sa, sb in zip(A[d], Bc[d], strict=False):
            ga = {g["flaw_id"]: g["matched_finding_strict"] is not None for g in sa.get("flaws", [])}
            gb = {g["flaw_id"]: g["matched_finding_strict"] is not None for g in sb.get("flaws", [])}
            for g in sorted(set(ga) & set(gb)):
                rows.append((int(ga[g]), int(gb[g])))
                b += ga[g] and not gb[g]
                c += gb[g] and not ga[g]
        pairs_by_doc[d] = rows
    res["flaw_level"] = {"mcnemar": {"b_a_only": b, "c_b_only": c, **stats.mcnemar(b, c)},
                         "stratified_permutation": stats.stratified_permutation_test(pairs_by_doc, B=B,
                                                                                     seed=paired_seed + 1),
                         "note": "McNemar ignores clustering: sanity check only (metrics.md §12.3)"}
    return res
