"""Human-readable ``scores.md`` from ``scores.json``."""

from __future__ import annotations

from typing import Any

HEADLINE = ["recall", "lenient_recall", "precision_strict", "precision_adjudicated", "lenient_precision_adjudicated",
            "f1_strict", "f1_adjudicated", "severity_weighted_recall", "critical_recall", "severity_agreement_qwk",
            "hallucinated_finding_rate", "hallucinated_finding_rate_without_g3", "quote_fabrication_rate",
            "citation_precision", "fabricated_citation_rate", "source_type_accuracy", "cdr", "balanced_unit_accuracy",
            "rjr_struct", "rjr_subst", "unjustified_recommendation_rate", "duplication_rate", "non_specific_rate",
            "ndcg_at_G", "ndcg_at_5", "mrr_critical", "critical_in_top3", "ece", "brier", "auroc",
            "action_type_accuracy", "approved_decision_violation_rate", "bait_resistance", "pooled_recall",
            "stale_finding_rate", "resolved_acknowledgement", "persisted_recall", "new_flaw_recall",
            "copy_through_rate"]


def _fmt(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, float):
        return f"{v:.3f}"
    if isinstance(v, dict):
        return ", ".join(f"{k}: {_fmt(x)}" for k, x in v.items())
    return str(v)


def render_scores_md(s: dict[str, Any]) -> str:
    inp = s["inputs"]
    lines = [f"# Scores: {inp['run_id']} vs {inp['item_id']} ({inp['doc_version']})", ""]
    banner = {"plumbing_only": "**PLUMBING ONLY** - fake judge; these numbers are not a score.",
              "pilot_unfrozen": "**UNFROZEN PILOT** - eval/prereg.yaml is not frozen; exploratory only.",
              "stopped_budget": "**STOPPED** - the cost limit was reached; no metrics were computed.",
              "frozen": "Frozen pre-registration; hash checked."}[s["status"]]
    lines += [banner, ""]
    j = s["judge"]
    lines += [f"- Review: `{inp['report_path']}` (sha256 {inp['report_sha256'][:12]}), condition: "
              f"{inp['condition'] or 'unlabelled'}",
              f"- Key: `{inp['key_path']}` (sha256 {inp['key_sha256'][:12]}), scored_run_ready: "
              f"{_fmt(inp['scored_run_ready'])}",
              f"- Document text: {inp['doc_source']} (sha256 {inp['doc_sha256_text'][:12]}, matches the review: "
              f"{_fmt(inp['doc_sha256_text_matches_review'])})",
              f"- Judge: {j['judge_kind']} / {j['model']} / effort {j['effort']}; {j['granularity']}, "
              f"candidates {j.get('candidate_rule', 'union (pre-2026-10-02 run)')}, "
              f"{j['samples']} samples, seed {j['seed']}; grounding judges {_fmt(j['grounding_judges'])}",
              f"- Prompt bundle: {s['prompts']['bundle_sha256'][:12]} (lock ok: {_fmt(s['prompts']['lock_ok'])})",
              ""]
    c = s["calls"]
    lines += [f"Judge calls: {c['calls_total']} ({c['calls_live']} live, {c['calls_cached']} cached, "
              f"{c['calls_failed']} failed); reported cost ${_fmt(c.get('cost_usd_reported'))}"
              + (f"; STOPPED: {c['budget'].get('stop_detail')}" if c["budget"].get("stopped") else ""), ""]
    if s.get("warnings"):
        lines += ["## Warnings", ""] + [f"- {w}" for w in s["warnings"]] + [""]
    m = s.get("metrics") or {}
    if m:
        lines += ["## Metrics", "", "| Metric | Value | Status | Reason / note |", "|---|---|---|---|"]
        for name in HEADLINE + sorted(set(m) - set(HEADLINE) - {"per_category", "calibration_inputs", "efficiency"}):
            if name not in m:
                continue
            x = m[name]
            note = x.get("reason") or x.get("note") or ""
            lines.append(f"| {name} | {_fmt(x['value'])} | {x['status']} | {note} |")
        lines.append("")
        pc = m.get("per_category", {}).get("value") or {}
        if pc:
            lines += ["## Per category (exploratory)", "", "| Category | Gold | Matched | Recall | Agent findings | "
                      "Precision |", "|---|---|---|---|---|---|"]
            for cat, v in pc.items():
                lines.append(f"| {cat} | {v['gold']} | {v['matched']} | {_fmt(v['recall'])} | {v['agent_findings']} "
                             f"| {_fmt(v['precision'])} |")
            lines.append("")
        eff = m.get("efficiency", {}).get("value") or {}
        if eff:
            lines += ["## Efficiency (from the run manifest)", ""] + [f"- {k}: {_fmt(v)}" for k, v in eff.items()]
            lines.append("")
    if s.get("flaws"):
        lines += ["## Key flaws", "", "| Flaw | Severity | Strict match | Lenient match | Best median score |",
                  "|---|---|---|---|---|"]
        for g in s["flaws"]:
            lines.append(f"| {g['flaw_id']} | {g['severity']} | {g['matched_finding_strict'] or '-'} | "
                         f"{g['matched_finding_lenient'] or '-'} | {_fmt(g.get('best_score'))} |")
        lines.append("")
    if s.get("findings"):
        lines += ["## Findings", "", "| Finding | Rank | Severity | Strict | Class (strict) | Lenient |",
                  "|---|---|---|---|---|---|"]
        for f in s["findings"]:
            lines.append(f"| {f['finding_id']} | {f['rank']} | {f.get('severity')} | {f['matched_flaw_strict'] or '-'} "
                         f"| {f['class_strict'] or '-'} | {f['matched_flaw_lenient'] or '-'} |")
        lines.append("")
    if s.get("failures"):
        lines += ["## Failed judge calls", ""] + [f"- {x}" for x in s["failures"]] + [""]
    return "\n".join(lines)
