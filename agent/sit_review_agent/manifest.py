"""Run manifest assembly (docs/REPRODUCIBILITY.md §8, spec ``RunManifest``; INV-09).

``start_manifest`` writes ``manifest.json`` before the first model call (git commit and dirty
flag, config and prompt hashes, taxonomy hash, requested model, tools, budgets, fault schedule);
``finalise_manifest`` adds served models, usage and cost, timings, outcome and output hashes at
exit. Fields that the spec's ``RunManifest`` lacks go in ``extra`` (:class:`ManifestExtra`).
In eval mode a dirty tree, a stale ``PROMPTS.lock`` or ``served_models != {requested}`` is refused.

Decisions taken here:

* The manifest written at start has ``outcome: crashed`` and ``end_utc: null``; a run that dies
  without finalising therefore reads as crashed, never as completed.
* Usage, served models and cost are summed from ``llm.jsonl`` (every attempt, across resumes),
  not from the in-process gateway, so a resumed run reports the whole run.
* ``git_dirty`` is ``const false`` in the spec. Outside eval mode the tree is not inspected (no
  ``git`` subprocess): the commit is read from ``.git`` files and ``extra.code.git_dirty`` is
  ``null`` ("not checked"). Eval mode runs ``git status --porcelain`` and refuses a dirty tree.
* ``extra.outputs.report_json_sha256`` is the SHA-256 of the canonical JSON of ``report.json``
  with that one key removed (a file cannot contain its own hash); the other output hashes are
  plain file hashes. ``report.md`` never prints ``extra.outputs``, so its hash is stable.
* ``extra.deviations`` and ``extra.model.models_retrieve`` written by an earlier manifest of the
  same run (start, resume) are carried forward.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

from sit_review_agent.clock import isoformat_z
from sit_review_agent.config import EffectiveConfig, Transport
from sit_review_agent.context import RunContext
from sit_review_agent.errors import ConfigError, PromptError
from sit_review_agent.hashing import bundle_sha256, sha256_file, sha256_json, sha256_text
from sit_review_agent.ingest.text import NORMALISATION_VERSION, PAGE_MARKER_LABEL
from sit_review_agent.llm.gateway import FALLBACK_BETA
from sit_review_agent.models import (
    Budgets,
    DocumentRole,
    ExtractorInfo,
    FallbackEvent,
    ManifestExtra,
    ModelUse,
    Outcome,
    ReviewConfigEcho,
    RunManifest,
    Timestamps,
    ToolManifestEntry,
    ToolMode,
    UsageSummary,
)
from sit_review_agent.paths import repo_root, taxonomy_path
from sit_review_agent.rundir import JsonlWriter, RunDir, write_json_atomic
from sit_review_agent.states import EFFORT_KEY, PHASE_ORDER

SAMPLING = "provider-default (not settable)"
#: Opus 5.5 list prices per million tokens (docs/BUDGET.md, claude-api skill cached 2026-09-25).
PRICE_TABLE: dict[str, Any] = {
    "source": "docs/BUDGET.md (claude-api skill, cached 2026-09-25)", "date": "2026-09-25",
    "usd_per_mtok": {"input": 4.0, "cache_write": 5.0, "cache_read": 0.20, "output": 20.0},
}
UNKNOWN_COMMIT = "0000000"


# ============================================================================== helpers


def git_state(root: Path | None = None, *, check_dirty: bool = False) -> dict[str, Any]:
    """``{commit, branch, dirty}`` from the ``.git`` directory (no subprocess unless
    ``check_dirty``). ``dirty`` is ``None`` when not checked."""
    root = root or repo_root()
    gitdir = root / ".git"
    out: dict[str, Any] = {"commit": None, "branch": None, "dirty": None}
    try:
        if gitdir.is_file():                                   # worktree: "gitdir: <path>"
            gitdir = (root / gitdir.read_text(encoding="utf-8").split(":", 1)[1].strip()).resolve()
        head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            out["branch"] = ref.rsplit("/", 1)[-1]
            common = gitdir
            cd = gitdir / "commondir"
            if cd.is_file():
                common = (gitdir / cd.read_text(encoding="utf-8").strip()).resolve()
            for base in (gitdir, common):
                p = base / ref
                if p.is_file():
                    out["commit"] = p.read_text(encoding="utf-8").strip()
                    break
            else:
                packed = common / "packed-refs"
                if packed.is_file():
                    for line in packed.read_text(encoding="utf-8").splitlines():
                        if line.endswith(" " + ref):
                            out["commit"] = line.split(" ", 1)[0]
        else:
            out["commit"] = head
    except (OSError, IndexError):
        pass
    if check_dirty:
        try:
            res = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True,
                                 timeout=30, check=False)
            out["dirty"] = bool(res.stdout.strip()) if res.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            out["dirty"] = None
    return out


def _pkg(name: str) -> str | None:
    try:
        return pkg_version(name)
    except PackageNotFoundError:
        return None


def _file_sha(path: Path) -> str | None:
    return sha256_file(path) if path.is_file() else None


def journal_usage(run_dir: RunDir) -> dict[str, Any]:
    """Usage, served models, refusals and cost summed over every entry of ``llm.jsonl``."""
    tot = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    served: set[str] = set()
    cost_logged = 0.0
    have_cost = False
    calls = 0
    for e in JsonlWriter(run_dir.llm_log).read():
        calls += 1
        for k in tot:
            tot[k] += int((e.get("usage") or {}).get(k) or 0)
        if e.get("outcome", "ok") == "ok" and e.get("model"):
            served.add(str(e["model"]))
        c = e.get("call_cost_usd")
        if isinstance(c, int | float):
            cost_logged += float(c)
            have_cost = True
    p = PRICE_TABLE["usd_per_mtok"]
    estimate = (tot["input_tokens"] * p["input"] + tot["cache_creation_input_tokens"] * p["cache_write"]
                + tot["cache_read_input_tokens"] * p["cache_read"] + tot["output_tokens"] * p["output"]) / 1e6
    return {**tot, "calls": calls, "served_models": sorted(served),
            "cost_usd": round(cost_logged if have_cost else estimate, 6),
            "cost_source": "llm.jsonl call_cost_usd (client-side estimate)" if have_cost else "price table estimate"}


def merged_refusals(ctx: RunContext) -> list[dict[str, Any]]:
    """Every refusal of the run, once: ``state.refusals`` (written by the phases, survives resume)
    plus the gateway's own record (``LLMGateway.refusals()``, this process only) for any refusal a
    phase did not record. Entries are matched on ``(call_id, stage)`` as a multiset, so a refusal
    known to both is counted once and an injected refusal without a call ID is not doubled."""
    out = [dict(r) for r in ctx.state.refusals]
    pool = [(r.get("call_id"), r.get("stage")) for r in out]
    for r in ctx.llm.refusals():
        key = (r.get("call_id"), r.get("stage"))
        if key in pool:
            pool.remove(key)
        else:
            out.append(dict(r))
    return out


def merged_fallback_events(ctx: RunContext) -> list[FallbackEvent]:
    """Every model fallback of the run, once: ``state.fallback_events`` plus the gateway's events
    that no phase recorded (multiset by equality; each event's ``reason`` names its call ID)."""
    out = list(ctx.state.fallback_events)
    pool = list(out)
    for ev in ctx.llm.fallback_events():
        if ev in pool:
            pool.remove(ev)
        else:
            out.append(ev)
    return out


def tool_call_ids(run_dir: RunDir) -> list[str]:
    """Distinct tool call IDs in ``tools.jsonl`` (replayed entries share their original ID)."""
    return list(dict.fromkeys(str(e["call_id"]) for e in JsonlWriter(run_dir.tools_log).read() if e.get("call_id")))


def output_hashes(run_dir: RunDir) -> dict[str, Any]:
    """Plain file hashes of the run outputs that exist (``null`` for missing files)."""
    rj = run_dir.report_json
    report_json = None
    if rj.is_file():
        data = json.loads(rj.read_text(encoding="utf-8"))
        report_json = report_json_sha256(data)
    return {"report_json_sha256": report_json, "report_md_sha256": _file_sha(run_dir.report_md),
            "ledger_sha256": _file_sha(run_dir.ledger), "llm_jsonl_sha256": _file_sha(run_dir.llm_log),
            "tools_jsonl_sha256": _file_sha(run_dir.tools_log), "anchors_sha256": _file_sha(run_dir.anchors)}


def report_json_sha256(review: dict[str, Any]) -> str:
    """Hash of a Review dict with ``run_manifest.extra.outputs.report_json_sha256`` removed."""
    data = json.loads(json.dumps(review))
    outs = ((data.get("run_manifest") or {}).get("extra") or {}).get("outputs")
    if isinstance(outs, dict):
        outs.pop("report_json_sha256", None)
    return sha256_json(data)


def _previous_extra(run_dir: RunDir) -> dict[str, Any]:
    if not run_dir.manifest.is_file():
        return {}
    try:
        return dict(json.loads(run_dir.manifest.read_text(encoding="utf-8")).get("extra") or {})
    except (OSError, json.JSONDecodeError):
        return {}


def transport_label(config: EffectiveConfig) -> str:
    t = config.agent.transport
    if t is Transport.REPLAY:
        return "replay-strict" if config.agent.replay.strict else "replay-lenient"
    if t is Transport.FAKE:
        return "fake" + ("+replay-strict" if config.agent.replay.fixtures and config.agent.replay.strict else "")
    return t.value


def _tool_mode(config: EffectiveConfig) -> ToolMode:
    t = config.agent.transport
    if t is Transport.RECORD:
        return ToolMode.RECORD
    if t is Transport.LIVE:
        return ToolMode.LIVE
    return ToolMode.REPLAY


def _cassette_set_sha256(config: EffectiveConfig) -> str | None:
    if not config.agent.replay.fixtures or config.agent.transport not in (Transport.REPLAY, Transport.FAKE):
        return None
    root = config.resolve_repo_path(config.agent.replay.fixtures)
    if not root.is_dir():
        return None
    return bundle_sha256((str(p.relative_to(root)), sha256_file(p)) for p in sorted(root.rglob("*.json")))


def automatic_deviations(ctx: RunContext) -> list[str]:
    a = ctx.config.agent
    out: list[str] = []
    if a.model != "claude-opus-5-5":
        out.append(f"model {a.model} instead of claude-opus-5-5 (ADR-002)")
    if a.allow_fallback:
        out.append("allow_fallback: server-side refusal fallback enabled (demo only; not eval evidence)")
    if a.transport is Transport.FAKE:
        out.append("transport fake: scripted model responses (selftest), not a model run")
    return out


# ============================================================================== build


def build_manifest(ctx: RunContext, outcome: Outcome, *, end_utc: str | None = None,
                   outputs: dict[str, Any] | None = None, deviations: list[str] | None = None,
                   models_retrieve: dict[str, Any] | None = None, git_dirty: bool | None = None) -> RunManifest:
    """The complete :class:`RunManifest` for the run as it stands."""
    cfg, st, rd = ctx.config, ctx.state, ctx.run_dir
    prev = _previous_extra(rd)
    prev_model = prev.get("model") or {}
    devs = list(dict.fromkeys([*(prev.get("deviations") or []), *automatic_deviations(ctx), *(deviations or [])]))
    mr = models_retrieve or prev_model.get("models_retrieve") or {"status": "not retrieved"}
    git = git_state(check_dirty=False)
    if git_dirty is not None:
        git["dirty"] = git_dirty
    elif (prev.get("code") or {}).get("git_dirty") is not None:
        git["dirty"] = prev["code"]["git_dirty"]
    usage = journal_usage(rd)
    served = sorted(set(usage["served_models"]) | set(ctx.llm.served_models()))
    tool_ids = tool_call_ids(rd)
    efforts = {p.value: cfg.effort_for(p) for p in PHASE_ORDER if p in EFFORT_KEY}
    effort_values = set(efforts.values())
    betas = [FALLBACK_BETA] if cfg.agent.allow_fallback else []
    fallbacks = merged_fallback_events(ctx)
    refusals = merged_refusals(ctx)

    under = next((d for d in st.documents if d.role is DocumentRole.UNDER_REVIEW), None)
    doc_obj = next((d for d in ctx.documents.values() if d.role is DocumentRole.UNDER_REVIEW), None)
    extractor = doc_obj.extractor if doc_obj is not None else ExtractorInfo(
        name="pdfplumber", version=_pkg("pdfplumber") or "unknown", page_marker=PAGE_MARKER_LABEL)
    docs_extra = []
    for d in st.documents:
        src = Path(d.pdf_path) if d.pdf_path else None
        docs_extra.append({"id": d.doc_id, "role": d.role.value, "sha256_pdf": d.sha256_pdf, "pages": d.page_count,
                           "bytes": src.stat().st_size if src is not None and src.is_file() else None,
                           "canonical_text_sha256": d.sha256_text or None, "native_pdf_block": d.native_pdf})
    doc_extra: dict[str, Any] = {
        "id": under.doc_id if under else None, "sha256_pdf": under.sha256_pdf if under else None,
        "pages": under.page_count if under else None,
        "canonical_text_sha256": (under.sha256_text or None) if under else None,
        "extractor": {"name": extractor.name, "version": extractor.version},
        "normalisation_version": NORMALISATION_VERSION,
        "native_pdf_block": under.native_pdf if under else None, "documents": docs_extra}
    root = repo_root()
    lock = next((p for p in (root / "uv.lock", root / "requirements.lock") if p.is_file()), None)
    url_policy = cfg.resolve_path(cfg.tools.url_policy)
    endpoints = cfg.endpoints.servers

    sched_id, sched_sha = None, None
    if cfg.agent.fault_schedule:
        try:
            from sit_review_agent.tools.faults import load_fault_schedule

            sched = load_fault_schedule(cfg.resolve_repo_path(cfg.agent.fault_schedule))
            sched_id, sched_sha = sched.id, sched.sha256
        except ConfigError:
            sched_id = Path(cfg.agent.fault_schedule).stem
    extra = ManifestExtra(
        mode=st.mode, previous_run_id=Path(st.previous_run_dir).name if st.previous_run_dir else None,
        doc=doc_extra,
        code={"git_commit": git["commit"], "git_branch": git["branch"], "git_dirty": git["dirty"],
              "package_lock_sha256": _file_sha(lock) if lock else None,
              "pyproject_sha256": _file_sha(root / "pyproject.toml"),
              "python": platform.python_version(), "os": f"{platform.system()} {platform.release()}",
              "anthropic_sdk_version": _pkg("anthropic"), "mcp_version": _pkg("mcp"),
              "sit_review_agent_version": _pkg("sit-review-agent"), "argv": list(sys.argv[1:])},
        prompts={"files": {f"prompts/{n}": h for n, h in sorted(ctx.prompts.files.items())},
                 "bundle_sha256": ctx.prompts.bundle_sha256},
        config={"files": dict(sorted(cfg.source_files.items())), "effective_config_sha256": cfg.sha256(),
                "cli_args": dict(cfg.cli_args)},
        model={"requested_model": cfg.agent.model, "backend": cfg.agent.llm.backend, "models_retrieve": mr,
               "served_models": served, "sampling": SAMPLING,
               "thinking": {"type": "adaptive", "display": cfg.agent.thinking_display},
               "effort_by_stage": efforts, "max_tokens_by_stage": {p: cfg.agent.max_tokens for p in efforts},
               "betas": betas, "fallbacks": "default" if cfg.agent.allow_fallback else "none",
               "fallback_events": [{"role": f.role, "from_model": f.from_model, "to_model": f.to_model,
                                    "category": f.reason} for f in fallbacks],
               "refusals": refusals,
               "sdk_client": {"max_retries": 0, "timeout_s": cfg.agent.llm.timeout_s,
                              "gateway_max_retries": cfg.agent.llm.max_retries},
               "calls_logged": usage["calls"]},
        tools={"transport": transport_label(cfg), "cassette_set_sha256": _cassette_set_sha256(cfg),
               "url_policy_sha256": _file_sha(url_policy),
               "servers": [{"name": s.name, "enabled": s.enabled,
                            "url_sha256": sha256_text(endpoints[s.name]) if s.name in endpoints else None,
                            "allow_tools": list(s.allow_tools), "protocol_version": None,
                            "tools_list_sha256": None, "health_at_start": None} for s in cfg.tools.servers],
               "tool_calls": len(tool_ids)},
        stop={"active_rules": list(cfg.stop_rules.active), "params": cfg.stop_rules.model_dump(mode="json"),
              "stop_reason": st.stop_reason.model_dump(mode="json") if st.stop_reason else None},
        fault_injection={"profile": sched_id or "none", "schedule_sha256": sched_sha},
        timing={"wall_clock_s": round(max(0.0, ctx.elapsed_s()), 3) if st.budget.started_monotonic else 0.0,
                "per_stage_s": dict(st.budget.phase_seconds)},
        outputs=dict(outputs) if outputs else {},
        deviations=devs,
    )
    return RunManifest(
        run_id=st.run_id,
        git_commit=git["commit"] if git["commit"] and _is_hex(git["commit"]) else UNKNOWN_COMMIT,
        git_dirty=False,
        config_sha256=cfg.sha256(),
        prompts_bundle_sha256=ctx.prompts.bundle_sha256,
        taxonomy_sha256=sha256_file(taxonomy_path()),
        schema_version="1.0",
        extractor=extractor,
        models_used=[ModelUse(
            role="agent", requested_model=cfg.agent.model, served_models=served or [cfg.agent.model],
            thinking="adaptive",
            effort=effort_values.pop() if len(effort_values) == 1 else "per-stage (extra.model.effort_by_stage)",
            max_tokens=cfg.agent.max_tokens, betas=betas, sampling=SAMPLING)],
        fallback_events=fallbacks,
        tools=[ToolManifestEntry(name=s.name, enabled=s.enabled, server_version=None, mode=_tool_mode(cfg))
               for s in cfg.tools.servers],
        budgets=Budgets(max_tool_calls=cfg.stop_rules.max_tool_calls, max_tokens=cfg.stop_rules.max_input_tokens,
                        deadline_s=cfg.stop_rules.deadline_seconds),
        usage=UsageSummary(input_tokens=usage["input_tokens"] + usage["cache_creation_input_tokens"],
                           output_tokens=usage["output_tokens"], cached_tokens=usage["cache_read_input_tokens"],
                           tool_calls=len(tool_ids), cost_usd=usage["cost_usd"],
                           price_table_date=PRICE_TABLE["date"]),
        timestamps=Timestamps(start_utc=st.created_utc, end_utc=end_utc),
        outcome=outcome,
        prereg_sha256=_file_sha(root / "eval" / "prereg.yaml") if st.mode == "eval" else None,
        split=None,
        condition=None,
        review_config=ReviewConfigEcho(criteria=cfg.criteria.ids(), stop_rule=cfg.stop_rules.model_dump(mode="json"),
                                       persona=cfg.agent.persona),
        fault_schedule_id=sched_id,
        extra=extra.model_dump(mode="json"),
    )


def _is_hex(s: str) -> bool:
    return 7 <= len(s) <= 40 and all(c in "0123456789abcdef" for c in s)


def write_manifest(run_dir: RunDir, manifest: RunManifest) -> None:
    write_json_atomic(run_dir.manifest, manifest.model_dump(mode="json"))


def check_eval_preconditions(ctx: RunContext) -> dict[str, Any]:
    """Eval mode only: refuse a dirty or unverifiable tree and a stale ``PROMPTS.lock``."""
    stale = ctx.prompts.check_lock()
    if stale:
        raise PromptError("eval mode refuses a stale PROMPTS.lock: " + "; ".join(stale))
    git = git_state(check_dirty=True)
    if git["dirty"] is not False:
        raise ConfigError("eval mode refuses to start: the git tree is dirty or its state could not be checked")
    return git


def start_manifest(ctx: RunContext, *, deviations: list[str] | None = None,
                   models_retrieve: dict[str, Any] | None = None) -> RunManifest:
    """Write ``manifest.json`` before the first model call (outcome ``crashed`` until finalised)."""
    dirty = check_eval_preconditions(ctx)["dirty"] if ctx.state.mode == "eval" else None
    m = build_manifest(ctx, Outcome.CRASHED, deviations=list(deviations or []), models_retrieve=models_retrieve,
                       git_dirty=dirty)
    write_manifest(ctx.run_dir, m)
    return m


def outcome_for(ctx: RunContext) -> Outcome:
    """``completed_degraded`` if anything was disclosed as a degradation, else ``completed_nominal``."""
    return Outcome.COMPLETED_DEGRADED if ctx.state.degradations else Outcome.COMPLETED_NOMINAL


def finalise_manifest(ctx: RunContext, outcome: Outcome) -> RunManifest:
    """Final manifest at exit (outcome, end time, output hashes); written to ``manifest.json``.
    In eval mode a run whose served models differ from the requested model is recorded as a
    deviation (it is excluded from evidence, REPRODUCIBILITY §2)."""
    devs: list[str] = []
    served = set(journal_usage(ctx.run_dir)["served_models"]) | ctx.llm.served_models()
    if ctx.state.mode == "eval" and served and served != {ctx.config.agent.model}:
        devs.append(f"served_models {sorted(served)} != requested {ctx.config.agent.model}: run invalid as evidence")
    m = build_manifest(ctx, outcome, end_utc=isoformat_z(ctx.clock.now_utc()), outputs=output_hashes(ctx.run_dir),
                       deviations=devs)
    write_manifest(ctx.run_dir, m)
    return m
