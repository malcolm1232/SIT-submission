"""``sit-eval aggregate``: several ``scores.json`` -> per-condition estimates with cluster-bootstrap CIs
and, with ``--compare A B``, paired differences, the document-level sign-flip test, the stratified
flaw-level permutation test and McNemar (metrics.md §12, prereg ``statistics``).

Runs of A and B on the same document are paired by their order (sorted run id). Holm / BH are left
to the analysis step that knows the prereg families (``sit_eval.stats.holm``).

LC12 (``sit_eval.lc12``): exploratory scores (``exploratory: true``, or a file written before the guard
whose key was not signed off) are refused, alone or mixed with confirmatory ones, unless
``exploratory=True`` (``--exploratory``); the aggregate is then marked exploratory itself.

Cost and tokens (MM §10; SIT FABLE ruling #28): per condition, the median and IQR of ``cost_usd``,
``input_tokens`` and ``output_tokens`` over the fully accounted runs, with the count and share of runs
excluded because a model call's usage was unrecorded or the run's completeness is unknown, and beside
them the median over every run at its lower bound. No figure mixes the two. The share of runs with any
cut call is reported intention-to-treat. The prereg pilot checkpoint (``stop_rule.pilot_checkpoint``,
threshold ``costs.per_run_usd.heavy_case_FULL``) is ``fail`` when the lower-bound median over all FULL runs
exceeds the threshold, ``pass`` only when every FULL run is fully accounted and the median is at or below
it, else ``not_evaluable``: a lower bound can fail the check but never pass it.

Dropped inputs (SIT FABLE ruling #29): a scores file is left out of every statistic when its scoring was stopped
by the judge budget before any statistic (``judge_budget_stop``), when it cannot be read as JSON
(``unreadable``), when it is not a scores object with the fields the aggregate reads (``schema_invalid``), or
when it carries no statistic (``incomplete``). Each is listed in ``dropped_inputs`` with its reason, and a
dropped run is a run of unknown cost: when any dropped file is a FULL run, or one whose condition cannot be
read, the pilot checkpoint is ``not_evaluable``. The check is structural, not the full scores schema, so a
scores file written before a later schema field (ruling #28's legacy files) still aggregates.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sit_eval import lc12, stats
from sit_eval import usage as usage_mod
from sit_eval.paths import SCHEMAS_DIR

DEFAULT_METRICS = ["recall", "lenient_recall", "precision_strict", "precision_adjudicated", "f1_adjudicated",
                   "severity_weighted_recall", "critical_recall", "hallucinated_finding_rate", "cdr",
                   "quote_fabrication_rate", "duplication_rate"]
#: Usage figures summarised per condition (median and IQR over fully accounted runs, lower-bound median over all).
USAGE_FIGURES = ["cost_usd", "input_tokens", "output_tokens"]
#: The condition the prereg pilot checkpoint reads ("the pilot median FULL cost").
CHECKPOINT_CONDITION = "FULL"
USAGE_NOTE = ("median and IQR over fully accounted runs only (every billed model call's usage recorded); the "
              "lower-bound median counts every run at its recorded figure, which is a lower bound for a run with an "
              "unrecorded call or unknown completeness, and can only rise as unknown usage is filled in; a run that "
              "reports no figure counts at 0; no figure mixes the two")


#: Why a scores file was dropped from an aggregate (ruling #29).
DROP_BUDGET_STOP, DROP_UNREADABLE, DROP_SCHEMA_INVALID, DROP_INCOMPLETE = (
    "judge_budget_stop", "unreadable", "schema_invalid", "incomplete")
#: The identity fields the aggregate reads from ``inputs`` to pair runs.
_IDENTITY = ("item_id", "doc_version", "run_id")


def _statuses() -> list[str]:
    schema = json.loads((SCHEMAS_DIR / "scores.schema.json").read_text(encoding="utf-8"))
    return schema["properties"]["status"]["enum"]


def _dropped(p: Path, reason: str, detail: str, s: Any = None) -> dict[str, Any]:
    """A dropped file's record. Its condition is read only from a scores object's ``inputs`` (``unlabelled`` when
    it names none, like a kept run); for anything else it is ``None``: unknown, so it may be a FULL run."""
    cond = None
    if isinstance(s, dict) and s.get("kind") == "sit_eval.scores" and isinstance(s.get("inputs"), dict):
        cond = s["inputs"].get("condition") or "unlabelled"
    return {"path": str(p), "reason": reason, "detail": detail, "condition": cond}


def _drop_reason(s: Any, statuses: list[str]) -> tuple[str, str] | None:
    if not isinstance(s, dict) or s.get("kind") != "sit_eval.scores":
        return DROP_SCHEMA_INVALID, "not a sit_eval.scores object"
    if s.get("status") == "stopped_budget":
        return DROP_BUDGET_STOP, "scoring stopped at the judge cost limit before any statistic"
    if s.get("status") not in statuses:
        return DROP_SCHEMA_INVALID, f"status {s.get('status')!r} is not one of {statuses}"
    inputs = s.get("inputs")
    missing = [k for k in _IDENTITY if not isinstance(inputs, dict) or not isinstance(inputs.get(k), str)]
    if missing:
        return DROP_SCHEMA_INVALID, f"inputs lacks {', '.join(missing)}"
    if not isinstance(s.get("metrics"), dict):
        return DROP_SCHEMA_INVALID, "no metrics object"
    if not s["metrics"]:
        return DROP_INCOMPLETE, f"status {s['status']!r} but no statistic was computed (metrics empty)"
    return None


def load_scores_with_drops(paths: list[Path]) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """The usable scores, the warnings, and every dropped file with its reason and condition (ruling #29)."""
    rows, warnings, dropped = [], [], []
    statuses = _statuses()
    for p in paths:
        try:
            s = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            dropped.append(_dropped(p, DROP_UNREADABLE, f"{type(exc).__name__}: {str(exc)[:200]}"))
            warnings.append(f"{p}: dropped ({DROP_UNREADABLE}); counted as missing, a run of unknown cost")
            continue
        why = _drop_reason(s, statuses)
        if why:
            dropped.append(_dropped(p, *why, s))
            warnings.append(f"{p}: dropped ({why[0]}: {why[1]}); counted as missing, a run of unknown cost")
            continue
        if s["status"] == "plumbing_only":
            warnings.append(f"{p}: PLUMBING ONLY (fake judge)")
        if s["status"] == "pilot_unfrozen":
            warnings.append(f"{p}: unfrozen pilot score")
        if s["inputs"].get("verdict_label") == "not_assessed":
            warnings.append(f"{p}: the review was not assessed (verdict not_assessed); counted intention-to-treat")
        s["_path"] = str(p)
        rows.append(s)
    return rows, warnings, dropped


def load_scores(paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    rows, warnings, _ = load_scores_with_drops(paths)
    return rows, warnings


def _doc(s: dict[str, Any]) -> str:
    return f"{s['inputs']['item_id']}:{s['inputs']['doc_version']}"


def _cond(s: dict[str, Any]) -> str:
    return s["inputs"].get("condition") or "unlabelled"


def _median_iqr(values: list[float]) -> tuple[float | None, list[float] | None]:
    if not values:
        return None, None
    return stats.percentile(values, 50), [stats.percentile(values, 25), stats.percentile(values, 75)]


def _share(k: int, n: int) -> float | None:
    return None if n == 0 else k / n


def usage_summary(runs: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """One usage figure (``cost_usd``, ``input_tokens``, ...) over a condition's runs: median and IQR over the
    fully accounted runs, the runs excluded (unrecorded usage, unknown completeness) with their share, and the
    median and IQR of every run's lower bound. The two medians never share a figure."""
    values = [(s["metrics"].get("efficiency") or {}).get("value") for s in runs]
    status = [usage_mod.status_of(v) for v in values]
    complete = [v[name] for v, st in zip(values, status, strict=True)
                if st == usage_mod.COMPLETE and v.get(name) is not None]
    # a run that reports no figure at all still counts in the lower-bound median, at 0 (usage is never negative);
    # leaving it out would let the median of the rest overstate the bound and fail the checkpoint unsoundly
    bounds = [usage_mod.lower_bound_of(v, name) for v in values]
    lower = [0 if x is None else x for x in bounds]
    n = len(runs)
    med, iqr = _median_iqr(complete)
    lmed, liqr = _median_iqr(lower)
    n_unrec = sum(st == usage_mod.UNRECORDED for st in status)
    n_unk = sum(st == usage_mod.UNKNOWN for st in status)
    return {"runs": n, "runs_fully_accounted": len(complete),
            "median_fully_accounted": med, "iqr_fully_accounted": iqr,
            "excluded_unrecorded": {"count": n_unrec, "share": _share(n_unrec, n)},
            "excluded_unknown": {"count": n_unk, "share": _share(n_unk, n)},
            "median_lower_bound_all_runs": lmed, "iqr_lower_bound_all_runs": liqr,
            "runs_with_a_lower_bound": sum(x is not None for x in bounds),
            "runs_without_a_figure_counted_at_zero": sum(x is None for x in bounds), "note": USAGE_NOTE}


def _runs_with(runs: list[dict[str, Any]], status: str) -> dict[str, Any]:
    ids = sorted(s["inputs"]["run_id"] for s in runs
                 if usage_mod.status_of((s["metrics"].get("efficiency") or {}).get("value")) == status)
    return {"count": len(ids), "share": _share(len(ids), len(runs)), "runs": ids}


def pilot_checkpoint(summary: dict[str, Any], threshold_usd: float | None, condition: str,
                     dropped: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Prereg ``stop_rule.pilot_checkpoint`` on the condition's ``cost_usd`` summary. ``fail`` when the
    lower-bound median over all runs exceeds the threshold (a median can only rise as unknown costs are
    filled in); ``pass`` only when every run is fully accounted and the median is at or below it; otherwise
    ``not_evaluable``. A lower bound can fail the check but never pass it. ``dropped`` are the scores files of
    the condition (or of unknown condition) left out of the aggregate: any makes the check ``not_evaluable``,
    since a dropped run is a run of unknown cost (ruling #29)."""
    n, n_acc = summary["runs"], summary["runs_fully_accounted"]
    med, lmed = summary["median_fully_accounted"], summary["median_lower_bound_all_runs"]
    dropped = list(dropped or [])
    out = {"condition": condition, "threshold_usd": threshold_usd, "runs": n, "runs_fully_accounted": n_acc,
           "median_fully_accounted": med, "median_lower_bound_all_runs": lmed, "dropped_inputs": dropped,
           "rule": "not_evaluable if any scores file of the condition, or of unknown condition, was dropped; else "
                   "fail if the lower-bound median over all runs exceeds the threshold; pass only if every run is "
                   "fully accounted and the median is at or below it; else not_evaluable (prereg "
                   "stop_rule.pilot_checkpoint, SIT FABLE rulings #28 and #29)"}
    if threshold_usd is None:
        return {**out, "verdict": "not_evaluable", "reason": "no threshold (prereg costs.per_run_usd.heavy_case_FULL)"}
    if dropped:
        listed = "; ".join(f"{d['path']} ({d['reason']}"
                           + (f", condition unknown, so it may be a {condition} run)" if d["condition"] is None
                              else ")") for d in dropped)
        return {**out, "verdict": "not_evaluable",
                "reason": f"{len(dropped)} scores file{'s' if len(dropped) != 1 else ''} dropped from the aggregate, "
                          f"each a run of unknown cost: {listed}"}
    if n == 0:
        return {**out, "verdict": "not_evaluable", "reason": f"no {condition} run in the inputs"}
    if lmed is not None and lmed > threshold_usd:
        return {**out, "verdict": "fail",
                "reason": f"the lower-bound median over all {n} {condition} runs, ${lmed:.2f}, exceeds "
                          f"${threshold_usd:.2f}"
                          + ("" if n_acc == n else f" ({n - n_acc} of them not fully accounted; the true median is "
                                                   "at least this)")}
    if n_acc == n and med is not None and med <= threshold_usd:
        return {**out, "verdict": "pass",
                "reason": f"every {condition} run is fully accounted and the median, ${med:.2f}, is at or below "
                          f"${threshold_usd:.2f}"}
    if n_acc < n:
        return {**out, "verdict": "not_evaluable",
                "reason": f"{n - n_acc} of {n} {condition} runs are not fully accounted; the lower-bound median "
                          f"({f'${lmed:.2f}' if lmed is not None else 'none'}) does not exceed "
                          f"${threshold_usd:.2f}, and a lower bound never passes the check"}
    return {**out, "verdict": "not_evaluable", "reason": f"no {condition} run reports a cost"}


def aggregate(paths: list[Path], *, metrics: list[str] | None = None, compare: tuple[str, str] | None = None,
              B: int = 10_000, seed: int = 0, paired_seed: int = 1, exploratory: bool = False,
              prereg_frozen: bool = False, pilot_threshold_usd: float | None = None) -> dict[str, Any]:
    """Raises :class:`~sit_eval.lc12.ExploratoryInputRefusal` before any statistic when exploratory inputs
    reach a run without ``exploratory``. ``pilot_threshold_usd`` is the prereg's
    ``costs.per_run_usd.heavy_case_FULL`` (``sit_eval.prereg.pilot_cost_threshold_usd``)."""
    rows, warnings, dropped = load_scores_with_drops(paths)
    expl = [lc12.describe_exploratory(s["_path"], s) for s in rows if lc12.scores_are_exploratory(s)]
    lc12.require_confirmatory_inputs(expl, len(rows), exploratory=exploratory)
    if expl and len(expl) < len(rows):
        warnings.append(f"the inputs mix exploratory and confirmatory scores (--exploratory): {'; '.join(expl)}")
    metrics = metrics or DEFAULT_METRICS
    by: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for s in rows:
        by[_cond(s)][_doc(s)].append(s)
    for cond in by:
        for d in by[cond]:
            by[cond][d].sort(key=lambda s: s["inputs"]["run_id"])
    out: dict[str, Any] = {"kind": "sit_eval.aggregate", **lc12.marker(exploratory, prereg_frozen=prereg_frozen),
                           "exploratory_inputs": [s["_path"] for s in rows if lc12.scores_are_exploratory(s)],
                           "inputs": [s["_path"] for s in rows],
                           "dropped_inputs": dropped,
                           "warnings": lc12.notes(exploratory, prereg_frozen=prereg_frozen) + warnings,
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
        runs = [s for v in docs.values() for s in v]
        for name in USAGE_FIGURES:
            res[name] = usage_summary(runs, name)
        res["runs_with_unrecorded_usage"] = _runs_with(runs, usage_mod.UNRECORDED)   # intention-to-treat
        res["runs_with_unknown_usage_completeness"] = _runs_with(runs, usage_mod.UNKNOWN)
        out["conditions"][cond] = res
    full = [s for v in by.get(CHECKPOINT_CONDITION, {}).values() for s in v]
    full_dropped = [d for d in dropped if d["condition"] in (CHECKPOINT_CONDITION, None)]
    out["pilot_checkpoint"] = {**pilot_checkpoint(usage_summary(full, "cost_usd"), pilot_threshold_usd,
                                                  CHECKPOINT_CONDITION, full_dropped),
                               "threshold_source": "eval/prereg.yaml costs.per_run_usd.heavy_case_FULL"}
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
