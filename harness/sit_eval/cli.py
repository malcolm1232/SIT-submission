"""``sit-eval`` command line. Owned by the matcher workstream.

Commands: ``score`` (one review against one key), ``aggregate`` (several scores.json), ``prompts``
(check or write the judge prompt lock) and ``grade`` (the lecturer grader, mounted from
``sit_eval.grader.cli``).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

import typer

app = typer.Typer(help="SIT evaluation harness.", no_args_is_help=True)

try:  # the grader is another workstream's package: an import error there must not disable `score`
    from sit_eval.grader.cli import app as grade_app
except Exception as _grader_exc:  # noqa: BLE001 - reported by the stub command below
    _GRADER_IMPORT_ERROR = f"{type(_grader_exc).__name__}: {_grader_exc}"

    @app.command("grade", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
    def grade_unavailable() -> None:
        """The lecturer grader (unavailable: its package failed to import)."""
        typer.echo(f"error: sit_eval.grader failed to import: {_GRADER_IMPORT_ERROR}", err=True)
        raise typer.Exit(2)
else:
    app.add_typer(grade_app, name="grade")

JUDGE_KINDS = ("fake", "claude_code", "anthropic_api")


def _fail(msg: str, code: int = 2) -> None:
    typer.echo(f"error: {msg}", err=True)
    raise typer.Exit(code)


@app.command()
def score(
    run: Path = typer.Argument(..., help="Run directory (holding report.json) or a report.json file."),
    key: Path = typer.Option(..., "--key", help="Canonical answer key (answer_key.canonical.json)."),
    doc: Path | None = typer.Option(None, "--doc", help="Document PDF or .pages.txt (default: the run's text, "
                                                         "else the PDF next to the key)."),
    out: Path | None = typer.Option(None, "--out", help="Output directory (default runs/eval/<run_id>)."),
    judge: str | None = typer.Option(None, "--judge", help="fake | claude_code | anthropic_api"),
    samples: int | None = typer.Option(None, "--samples", min=1, help="Pairwise samples (prereg: 3)."),
    seed: int | None = typer.Option(None, "--seed", help="Seed for shuffles and the adjudication sample."),
    max_cost_usd: float | None = typer.Option(None, "--max-cost-usd", help="Hard stop: refuse a call that would "
                                                                         "cross this total."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the planned call count and cost; call nothing."),
    granularity: str | None = typer.Option(None, "--granularity", help="pairwise (prereg) | per_flaw_batch "
                                                                       "(deviation)"),
    concurrency: int | None = typer.Option(None, "--concurrency", min=1),
    adaptive_samples: bool | None = typer.Option(None, "--adaptive-samples/--no-adaptive-samples",
                                                 help="Ask the third pairwise sample only when the first two "
                                                      "disagree (same median; needs owner approval)."),
    grounding_judges: bool | None = typer.Option(None, "--grounding-judges/--no-grounding-judges",
                                                 help="G3 premise and citation support judges."),
    recommendation_judge: bool | None = typer.Option(None, "--recommendation-judge/--no-recommendation-judge"),
    condition: str | None = typer.Option(None, "--condition", help="Condition label for aggregate (else the "
                                                                   "manifest's)."),
    doc_version: str | None = typer.Option(None, "--doc-version", help="v1 | v2 (default: inferred)."),
    prior_scores: Path | None = typer.Option(None, "--prior-scores", help="v1 scores.json (v2 copy-through)."),
    model: str | None = typer.Option(None, "--model", help="Judge model (default config/eval.yaml)."),
    effort: str | None = typer.Option(None, "--effort"),
    config: Path | None = typer.Option(None, "--config", help="Path to eval.yaml."),
) -> None:
    """Score one review against one answer key; writes scores.json, scores.md and the judge call log."""
    from sit_eval import prereg as prereg_mod
    from sit_eval import prompts as prompts_mod
    from sit_eval.calls import JudgeRunner
    from sit_eval.config import load_eval_config
    from sit_eval.judge import build_judge
    from sit_eval.loaders import LoadError, infer_doc_version, load_document, load_key, load_review
    from sit_eval.scoring import ScoreOptions, plan_calls, score_review, validate_scores, write_outputs

    cfg = load_eval_config(config)
    kind = judge or cfg.judge.kind
    if kind not in JUDGE_KINDS:
        _fail(f"--judge must be one of {', '.join(JUDGE_KINDS)}")
    gran = granularity or cfg.matcher.call_granularity
    if gran not in ("pairwise", "per_flaw_batch"):
        _fail("--granularity must be pairwise or per_flaw_batch")
    opts = ScoreOptions(
        judge_kind=kind, model=model or cfg.judge.model, effort=effort or cfg.judge.effort,
        max_tokens=cfg.judge.max_tokens, samples=samples or cfg.matcher.samples,
        seed=cfg.run.seed if seed is None else seed, granularity=gran, shortlist_k=cfg.matcher.shortlist_k,
        severity_epsilon=cfg.matcher.severity_epsilon, concurrency=concurrency or cfg.run.concurrency,
        max_cost_usd=max_cost_usd if max_cost_usd is not None else cfg.run.max_cost_usd,
        grounding_judges=cfg.grounding.judges if grounding_judges is None else grounding_judges,
        recommendation_judge=(cfg.grounding.recommendation_judge if recommendation_judge is None
                              else recommendation_judge),
        theta_q=cfg.grounding.theta_q, condition=condition,
        adaptive_samples=cfg.matcher.adaptive_third_sample if adaptive_samples is None else adaptive_samples)
    try:
        rin = load_review(run)
        key_data = load_key(key)
    except LoadError as exc:
        _fail(str(exc))
    if doc_version not in (None, "v1", "v2"):
        _fail("--doc-version must be v1 or v2")
    version = doc_version or infer_doc_version(rin, key_data, doc)

    if dry_run:
        plan = plan_calls(rin, key_data, version, opts, cfg.cost_estimate.per_call_usd, cfg.cost_estimate.per_call_s)
        plan["max_cost_usd"] = opts.max_cost_usd
        typer.echo(json.dumps(plan, indent=1))
        return

    status = prereg_mod.prereg_status()
    problems = prompts_mod.check_lock()
    bundle = prompts_mod.compute_lock()["bundle_sha256"]
    try:
        prereg_mod.enforce(status, prompt_bundle_sha256=bundle, prompt_lock_problems=problems)
    except prereg_mod.PreregRefusal as exc:
        _fail(f"refusing a scored run: {exc}")
    if not status["frozen"]:
        typer.echo(f"WARNING: {status['message']}", err=True)
    if problems:
        typer.echo("WARNING: judge prompts differ from prompts/PROMPTS.lock: " + "; ".join(problems), err=True)

    try:
        docin = load_document(rin, key=key_data, key_path=key, doc=doc, version=version)
    except LoadError as exc:
        _fail(str(exc))
    out_dir = out or Path("runs") / "eval" / rin.data["metadata"]["run_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    options: dict[str, object] = {}
    if kind == "claude_code":
        options = {"executable": cfg.judge.executable, "timeout_s": cfg.judge.timeout_s,
                   "max_retries": cfg.judge.max_retries, "backoff_base_s": cfg.judge.backoff_base_s,
                   "backoff_max_s": cfg.judge.backoff_max_s,
                   "max_budget_usd_per_call": cfg.judge.max_budget_usd_per_call,
                   "inherit_api_key": cfg.judge.inherit_api_key}
    elif kind == "anthropic_api":
        options = {"timeout_s": cfg.judge.timeout_s, "max_retries": cfg.judge.max_retries,
                   "backoff_base_s": cfg.judge.backoff_base_s, "backoff_max_s": cfg.judge.backoff_max_s}
    if kind == "claude_code" and shutil.which(cfg.judge.executable) is None:
        _fail(f"Claude Code executable {cfg.judge.executable!r} not found on PATH; install it and log in, or use "
              "--judge anthropic_api")
    if kind == "anthropic_api" and not os.environ.get("ANTHROPIC_API_KEY"):
        _fail("--judge anthropic_api needs ANTHROPIC_API_KEY in the environment")
    client = build_judge(kind, out_dir=out_dir, **options)
    reserve = cfg.judge.max_budget_usd_per_call or cfg.cost_estimate.per_call_usd.get("high", 0.15)
    runner = JudgeRunner(client, model=opts.model, effort=opts.effort, max_tokens=opts.max_tokens,
                         concurrency=opts.concurrency, max_cost_usd=opts.max_cost_usd,
                         reserve_usd=0.0 if kind == "fake" else reserve, out_dir=out_dir)
    prior = json.loads(prior_scores.read_text(encoding="utf-8")) if prior_scores else None
    prompts_info = {"bundle_sha256": bundle, "lock_ok": not problems, "problems": problems}
    scores = asyncio.run(score_review(rin=rin, key=key_data, key_path=key, docin=docin, version=version,
                                      runner=runner, opts=opts, prereg=status, prompts_info=prompts_info,
                                      prior_scores=prior))
    errs = validate_scores(scores)
    js, md = write_outputs(scores, out_dir)
    if errs:
        _fail(f"scores.json written to {js} but violates schemas/scores.schema.json: {'; '.join(errs[:5])}", 1)
    m = scores.get("metrics") or {}
    headline = {k: (m.get(k) or {}).get("value") for k in ("recall", "lenient_recall", "precision_adjudicated",
                                                            "severity_weighted_recall", "hallucinated_finding_rate")}
    typer.echo(json.dumps({"status": scores["status"], "scores_json": str(js), "scores_md": str(md),
                           "headline": headline, "calls": {k: scores["calls"][k] for k in
                                                           ("calls_total", "calls_live", "calls_failed",
                                                            "cost_usd_reported")}}, indent=1, default=str))
    if scores["status"] == "stopped_budget":
        raise typer.Exit(3)


@app.command("aggregate")
def aggregate_cmd(
    scores: list[Path] = typer.Argument(..., help="scores.json files."),
    out: Path | None = typer.Option(None, "--out", help="Write the aggregate JSON here."),
    metric: list[str] | None = typer.Option(None, "--metric", help="Metric to aggregate (repeatable)."),
    compare: list[str] | None = typer.Option(None, "--compare", help="Two condition labels: A then B."),
    bootstrap_b: int | None = typer.Option(None, "--bootstrap-b", min=100),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    """Aggregate several scores.json: macro means, cluster-bootstrap CIs, paired tests."""
    from sit_eval.aggregate import aggregate
    from sit_eval.config import load_eval_config

    cfg = load_eval_config(config)
    if compare and len(compare) != 2:
        _fail("--compare takes exactly two condition labels (repeat the option twice)")
    res = aggregate(list(scores), metrics=metric or None, compare=tuple(compare) if compare else None,
                    B=bootstrap_b or cfg.statistics.bootstrap_b, seed=cfg.statistics.seed,
                    paired_seed=cfg.statistics.paired_seed)
    text = json.dumps(res, indent=1, default=str)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    typer.echo(text)


@app.command()
def prompts(write_lock: bool = typer.Option(False, "--write-lock", help="Rewrite prompts/PROMPTS.lock.")) -> None:
    """Check (default) or rewrite the SHA-256 lock of the judge prompts and schemas."""
    from sit_eval import prompts as prompts_mod

    if write_lock:
        lock = prompts_mod.write_lock()
        typer.echo(f"wrote {prompts_mod.PROMPTS_LOCK} bundle_sha256={lock['bundle_sha256']}")
        return
    problems = prompts_mod.check_lock()
    if problems:
        for p in problems:
            typer.echo(p, err=True)
        raise typer.Exit(1)
    typer.echo(f"prompts match the lock; bundle_sha256={prompts_mod.compute_lock()['bundle_sha256']}")


def main() -> None:
    app()
