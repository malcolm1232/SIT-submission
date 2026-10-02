"""``sit-eval grade`` sub-commands. Owned by the grader workstream; mounted by ``sit_eval.cli``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from sit_eval.grader import costs, prompts

app = typer.Typer(help="Lecturer grader (research/grading/grader_prompt.md).", no_args_is_help=True)

JUDGE_KINDS = ("fake", "claude_code", "anthropic_api")


def _judge(kind: str, out_dir: Path) -> Any:
    if kind not in JUDGE_KINDS:
        typer.echo(f"--judge must be one of {', '.join(JUDGE_KINDS)}", err=True)
        raise typer.Exit(2)
    if kind == "fake":
        from sit_eval.grader.fake import heuristic_fake_judge

        typer.echo("judge: fake (deterministic heuristic; PLUMBING ONLY, scores carry no meaning)")
        return heuristic_fake_judge()
    from sit_eval.judge import build_judge

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        return build_judge(kind, out_dir=out_dir)
    except NotImplementedError as exc:
        typer.echo(f"judge {kind!r} is not available yet: {exc}", err=True)
        raise typer.Exit(2) from exc


def _print_plan(plan: dict[str, Any]) -> None:
    typer.echo(f"DRY RUN: no model call is made. Mode {plan['mode']}; findings {plan['findings']}; "
               f"model {plan['model']} effort {plan['effort']}.")
    typer.echo(f"Inputs: design {plan['design_chars']:,} chars, evidence register {plan['evidence_register_chars']:,}"
               f" chars, review {plan['review_chars']:,} chars.")
    for r in plan["calls"]:
        cond = " (conditional)" if r.get("conditional") else ""
        typer.echo(f"  {r['count']} x {r['call']}{cond}: ~{r['input_tokens']:,} in / ~{r['output_tokens']:,} out "
                   f"tokens, ~${r['cost_usd']:.2f} each")
    typer.echo(f"Planned calls: {plan['calls_min']} (up to {plan['calls_max']} with third samples).")
    typer.echo(f"Estimated cost: ${plan['cost_usd_min']:.2f} - ${plan['cost_usd_max']:.2f} ({plan['price_basis']}).")
    typer.echo("`claude -p` reports its own cost per call and the budget uses it. A two-finding smoke call on Haiku "
               "4.5 cost $0.11-0.13 (about 10k thinking tokens), so expect Opus calls on a real review to cost "
               "more than this list-price estimate.")
    lo, hi = plan["wall_time_s"]
    typer.echo(f"Wall time: about {lo // 60}-{-(-hi // 60)} min sequential.")
    for w in plan.get("warnings") or []:
        typer.echo(f"warning: {w}")


@app.command("run")
def run(
    review: Path = typer.Argument(..., exists=True, dir_okay=False, help="The agent's report.json (a Review)."),
    pdf: Path = typer.Option(..., "--pdf", exists=True, dir_okay=False,
                             help="Design PDF (ingested by the agent's own ingest) or canonical .pages.txt."),
    out: Path = typer.Option(Path("grade_out"), "--out", help="Output directory."),
    judge: str = typer.Option("fake", "--judge", help="fake | claude_code | anthropic_api"),
    answer_key: Path | None = typer.Option(None, "--answer-key", exists=True, dir_okay=False,
                                           help="Key-aware DIAGNOSTIC (canonical JSON or legacy YAML)."),
    v1_review: Path | None = typer.Option(None, "--v1-review", exists=True, dir_okay=False,
                                          help="Prior review: delta mode with D11."),
    v1_pdf: Path | None = typer.Option(None, "--v1-pdf", exists=True, dir_okay=False,
                                       help="Prior design document (delta mode)."),
    samples: int = typer.Option(2, "--samples", min=1, help="Samples per pass (prereg: 2)."),
    seed: int = typer.Option(0, "--seed"),
    max_cost_usd: float | None = typer.Option(None, "--max-cost-usd", help="Hard stop before a call that would "
                                                                             "cross this spend."),
    model: str = typer.Option("claude-opus-5-5", "--model"),
    effort: str = typer.Option("high", "--effort"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the planned calls and cost; call nothing."),
) -> None:
    """Grade one review (key-blind score; optional key-aware diagnostic)."""
    from sit_eval.grader.pipeline import GraderError, grade_review, plan_grade
    from sit_eval.grader.projection import GraderInputError

    try:
        if dry_run:
            _print_plan(plan_grade(review, pdf, answer_key=answer_key, v1_review=v1_review, v1_document=v1_pdf,
                                   samples=samples, model=model, effort=effort))
            return
        client = _judge(judge, out)
        res = grade_review(review, pdf, out, judge=client, answer_key=answer_key, v1_review=v1_review,
                           v1_document=v1_pdf, samples=samples, seed=seed, max_cost_usd=max_cost_usd, model=model,
                           effort=effort)
    except GraderInputError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc
    except (costs.BudgetExceeded, GraderError) as exc:
        typer.echo(f"stopped: {exc}\npartial results in {out / 'grade.json'}", err=True)
        raise typer.Exit(3) from exc
    rep = res.report
    typer.echo(rep["label"])
    typer.echo(f"S = {rep['S']} grade {rep['grade']} {'PASS' if rep['pass'] else 'FAIL'}; "
               f"calls {rep['calls']['count']}; spent ${rep['budget']['spent_usd']:.4f}; "
               f"needs human review: {rep['needs_human_review']}")
    typer.echo(f"wrote {res.grade_json}, {res.grade_md}, {res.call_log}")


@app.command("validate")
def validate(
    review: Path = typer.Argument(..., exists=True, dir_okay=False, help="Base review (R_base)."),
    pdf: Path = typer.Option(..., "--pdf", exists=True, dir_okay=False),
    out: Path = typer.Option(Path("grade_validation"), "--out"),
    judge: str = typer.Option("fake", "--judge", help="fake | claude_code | anthropic_api"),
    checks: str = typer.Option("V1,V4,V10", "--checks", help="Comma-separated GR §8 checks (prereg Tier A: "
                                                             "V1,V4,V10)."),
    runs: int = typer.Option(5, "--runs", min=1),
    samples: int = typer.Option(2, "--samples", min=1),
    seed: int = typer.Option(0, "--seed"),
    variant: list[str] = typer.Option([], "--variant", help="Authored variant, e.g. V6=path/review.json"),
    max_cost_usd: float | None = typer.Option(None, "--max-cost-usd"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Grader meta-validation (GR §8) with any judge."""
    from sit_eval.grader.pipeline import plan_grade
    from sit_eval.grader.projection import GraderInputError
    from sit_eval.grader.validation import ALL_CHECKS, plan_meta_validation, run_meta_validation

    wanted = [c.strip().upper() for c in checks.split(",") if c.strip()]
    bad = [c for c in wanted if c not in ALL_CHECKS]
    if bad:
        typer.echo(f"unknown checks {bad}", err=True)
        raise typer.Exit(2)
    bad_variants = [v for v in variant if "=" not in v]
    if bad_variants:
        typer.echo(f"--variant must be CHECK=path/review.json, got {bad_variants}", err=True)
        raise typer.Exit(2)
    variants = dict(v.split("=", 1) for v in variant)
    try:
        if dry_run:
            plan = plan_grade(review, pdf, samples=samples)
            mv = plan_meta_validation(plan["findings"], checks=wanted, runs=runs, samples=samples)
            per_call = (plan["cost_usd_min"] / max(plan["calls_min"], 1))
            typer.echo(f"DRY RUN: {mv['grades']} grades, {mv['calls_min']}-{mv['calls_max']} calls, "
                       f"~${mv['calls_min'] * per_call:.2f}-${mv['calls_max'] * per_call:.2f} at list price.")
            return
        client = _judge(judge, out)
        res = run_meta_validation(review, pdf, out, judge=client, checks=wanted, runs=runs, samples=samples,
                                  seed=seed, max_cost_usd=max_cost_usd, variants=variants)
    except (GraderInputError, ValueError) as exc:   # bad review or key; a check that needs --variant
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(res["label"])
    for o in res["outcomes"]:
        typer.echo(f"{o['check']}: passed={o['passed']} ({o['criterion']}; n={o['observations']})")
    typer.echo(f"status {res['status']}; wrote {out / 'meta_validation.json'}")
    if res["status"] != "complete":
        raise typer.Exit(3)


@app.command("lock")
def lock(write: bool = typer.Option(False, "--write", help="Rewrite prompts.lock.json from the current files.")
         ) -> None:
    """Show (or rewrite) the prompt lock; bundle_sha256 is prereg grader.prompt_sha256."""
    if write:
        path = Path(prompts.__file__).parent / "prompts" / prompts.LOCK_FILE
        path.write_text(prompts.lock_text(), encoding="utf-8")
        typer.echo(f"wrote {path}")
    st = prompts.lock_status()
    typer.echo(json.dumps(st, indent=2))
    if not st["ok"]:
        raise typer.Exit(1)
