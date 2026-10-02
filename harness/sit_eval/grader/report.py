"""``grade.md``: the human-readable view of ``grade.json``."""

from __future__ import annotations

from typing import Any

from sit_eval.grader.scoring import weights

NAMES = {"D1": "Design-intent understanding", "D2": "Fitness-for-purpose judgement", "D3": "Coverage",
         "D4": "Evidence quality and traceability", "D5": "Recommendation quality",
         "D6": "Restraint and justified no change", "D7": "Issue triage", "D8": "Research sufficiency",
         "D9": "Output integrity", "D10": "Professional quality", "D11": "Re-assessment (delta)"}


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    return "-" if v is None else str(v)


def render_markdown(rep: dict[str, Any]) -> str:
    out = [f"# Lecturer grade: {rep.get('review_id') or 'review'}", ""]
    out.append(f"> {rep.get('label')}")
    out.append("")
    if rep.get("status") != "complete":
        out += [f"**Status: {rep.get('status')}.** {rep.get('error') or ''}", ""]
    out += ["| | |", "|---|---|",
            f"| Mode | {rep.get('mode')} (key-blind is the score) |",
            f"| Document | {rep['document']['doc_id']} ({_fmt(rep['document']['page_count'])} pages); "
            f"matches review: {rep['document']['matches_review']} |",
            f"| Grader | {rep.get('grader_model') or '-'} (requested {rep.get('grader_model_requested')}, "
            f"effort {rep.get('grader_effort')}) |",
            f"| Prompt | {rep.get('grader_prompt_version')}, bundle sha256 "
            f"{str(rep.get('grader_prompt_sha256'))[:16]}..."
            f" (lock ok: {rep.get('grader_prompt_lock_ok')}) |",
            f"| Calls | {rep['calls']['count']}; spent ${rep['budget']['spent_usd']:.4f}"
            + (f" of ${rep['budget']['max_cost_usd']:.2f}" if rep['budget']['max_cost_usd'] is not None else "")
            + " |", ""]
    if rep.get("S") is not None:
        out += [f"## Result: S = {rep['S']:g}, grade {rep['grade']}, {'PASS' if rep['pass'] else 'FAIL'}", ""]
        gates = rep.get("gates") or {}
        out.append("Gates: " + ", ".join(f"{k} {'pass' if v else 'FAIL'}" for k, v in gates.items()))
        if rep.get("caps_applied"):
            out.append("Caps: " + "; ".join(rep["caps_applied"]))
        out.append("")
        samples = rep.get("samples") or []
        head = "| Dim | Name | Weight | " + " | ".join(s["seed"] for s in samples) + " | Final |"
        out += [head, "|" + "---|" * (4 + len(samples))]
        w_mode = weights("delta" in str(rep.get("mode")))   # delta mode: D1-D10 x 0.9, D11 10
        for k, v in (rep.get("dimensions_final") or {}).items():
            w = w_mode.get(k, 0)
            cells = " | ".join(_fmt(s["dimensions_capped"].get(k)) for s in samples)
            out.append(f"| {k} | {NAMES.get(k, k)} | {w:g} | {cells} | {_fmt(v)} |")
        out.append("| S | | | " + " | ".join(_fmt(s["S_raw"]) for s in samples) + f" | {_fmt(rep['S'])} |")
        dis = rep.get("disagreement") or {}
        out += ["", f"Disagreement: max dimension delta {_fmt(dis.get('max_dim_delta'))}, S delta "
                    f"{_fmt(dis.get('S_delta'))}; third sample run: {dis.get('third_sample_run')}.", ""]
    halls = rep.get("hallucinations") or []
    out.append(f"## Hallucination flags ({len(halls)})")
    out.append("")
    for h in halls:
        out.append(f"- {h.get('finding_id') or '-'} {h.get('type')} ({h.get('severity')}, {h.get('status')}; "
                   f"flagged in {', '.join(h.get('flagged_in') or [])}): \"{h.get('review_quote', '')[:160]}\"")
    if not halls:
        out.append("None.")
    out.append("")
    hc = rep.get("harness_checks") or {}
    out += ["## Harness checks (no model)", "",
            f"- Verdict present (code): {hc.get('verdict_present')}",
            f"- Anchor quotes: {hc.get('anchors')}",
            f"- Injection pre-scan hits: {len(hc.get('injection_scan') or [])}",
            f"- Review schema errors: {len(hc.get('review_schema_errors') or [])}", ""]
    if rep.get("needs_human_review"):
        out += ["## Needs human review", ""] + [f"- {r}" for r in rep.get("human_review_reasons") or []] + [""]
    kd = rep.get("key_alignment_diagnostic")
    if kd:
        out += ["## Key-aware alignment (diagnostic only)", "", f"> {kd['label']}", ""]
        out += [f"- {k}: {_fmt(v)}" for k, v in kd["counts_median"].items()]
        out.append("")
    if rep.get("warnings"):
        out += ["## Warnings", ""] + [f"- {w}" for w in rep["warnings"]] + [""]
    return "\n".join(out).rstrip("\n") + "\n"
