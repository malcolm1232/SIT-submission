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
  not from the in-process gateway, so a resumed run reports the whole run. Failed attempts count
  too: a call truncated at ``max_tokens`` was billed, so its usage and cost are in the totals, and
  every truncated call is listed in ``extra.model.truncations`` (``call_id``, ``stage``,
  ``purpose``; robustness LLM-07). An attempt that was sent but left no usage report (cut by the
  deadline, killed at its timeout, a crashed ``claude -p``, a dropped stream, an interrupt) is
  never counted as zero: it is listed in ``extra.model.calls_with_unrecorded_usage`` and
  ``extra.model.cost_usd_lower_bound`` is true, so ``usage.cost_usd`` and the token totals are a
  lower bound (``report.md``, the console and the ``--k`` summary say so).
* A cut attempt may log an estimate of its usage (latency redesign). The estimate sits beside the
  measured-null record, never in it: ``extra.model.estimated_usage_of_unrecorded_calls`` has one row
  per such attempt (``estimated: true``, call ID, stage, purpose, attempt, reason, the four token
  fields) and ``extra.model.estimated_usage_totals`` sums them with a price-table cost. The measured
  totals, ``usage.cost_usd``, the unrecorded list and the lower-bound flag are unchanged by it.
* Counts of the concurrent phase structure, all read from ``llm.jsonl`` and 0 for a sequential run:
  ``extra.model.assess_shards`` is the number of distinct ``shard`` markers on assess attempts (the
  shard's name or index, logged on every attempt of the shard; a sequential run logs none),
  ``salvaged_calls`` the attempts that kept finished items of a cut answer (:func:`logged_salvage`)
  and ``salvaged_items`` the sum of those items.
* Timing: ``extra.timing.wall_clock_s`` is the run clock. ``per_stage_s`` (kept for the harness)
  maps each phase to its own wall seconds; stage 1 members overlap, so it does not sum to the run.
  ``extra.timing.stages`` groups them by stage (:func:`stage_timing`): ``members``, ``wall_s``
  (the stage's span, never the members' sum when they overlapped) and ``sum_of_member_s``.
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
from sit_review_agent.finding_refs import manifest_record
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
from sit_review_agent.states import EFFORT_KEY, PHASE_ORDER, STAGE_MEMBERS, STAGE_ORDER

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
    ``check_dirty``). ``branch`` is the full branch name (``s4/demo``), ``None`` on a detached
    HEAD; ``commit`` is ``None`` without a readable ``.git``. ``dirty`` is ``None`` when not
    checked or when ``git`` cannot be run (missing binary, not a repository)."""
    root = root or repo_root()
    gitdir = root / ".git"
    out: dict[str, Any] = {"commit": None, "branch": None, "dirty": None}
    try:
        if gitdir.is_file():                                   # worktree: "gitdir: <path>"
            gitdir = (root / gitdir.read_text(encoding="utf-8").split(":", 1)[1].strip()).resolve()
        head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            out["branch"] = ref.removeprefix("refs/heads/")      # full name: "s4/demo", not "demo"
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


#: Outcomes of an attempt that was killed before it could report usage, in ``llm.jsonl`` written
#: before 2026-10-03 (those entries logged zero usage instead of ``usage_unrecorded``).
_LEGACY_KILLED = {"LLMDeadlineError": "deadline_cut", "LLMTimeoutError": "timeout_kill"}


def unrecorded_reason(entry: dict[str, Any]) -> str | None:
    """Why a sent attempt's usage is unknown, or ``None`` when its usage is known (or nothing was
    sent). New entries say it (``usage_unrecorded``); an older entry of a deadline cut or timeout
    with zero usage, no cost and no HTTP status is read the same way. Unsent entries, injected
    faults and replayed entries spent nothing."""
    if entry.get("usage_unrecorded"):
        return str(entry["usage_unrecorded"])
    if entry.get("sent") is False or "fault" in entry or entry.get("replayed") or entry.get("fake"):
        return None
    reason = _LEGACY_KILLED.get(str(entry.get("outcome")))
    usage = entry.get("usage")
    if reason and isinstance(usage, dict) and not any(usage.values()) and entry.get("call_cost_usd") is None \
            and entry.get("status_code") is None:
        return reason
    return None


USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def _count(value: Any) -> int | None:
    """A non-negative integer count, or ``None`` (bools, floats, negatives and text are not counts)."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def logged_estimate(entry: dict[str, Any]) -> dict[str, int] | None:
    """The estimated usage logged for a cut attempt, or ``None``. Read under ``estimated_usage`` (the
    key the streaming gateway logs and ``replay.recorded_error`` maps) or ``usage_estimate`` (an earlier
    spelling, still read); every ``Usage`` field present must be a non-negative integer."""
    for key in ("estimated_usage", "usage_estimate"):
        raw = entry.get(key)
        if isinstance(raw, dict):
            counts = {k: _count(raw.get(k, 0)) for k in USAGE_FIELDS}
            if all(v is not None for v in counts.values()):
                return {k: int(v or 0) for k, v in counts.items()}
    return None


def logged_salvage(entry: dict[str, Any]) -> int:
    """Finished items an attempt salvaged before its cut: the list fields of ``partial`` (or the earlier
    spelling ``salvaged_partial``), as ``LLMDeadlineError.salvaged_items`` counts them, else a logged
    ``salvaged_items`` count; 0 when nothing was salvaged."""
    for key in ("partial", "salvaged_partial"):
        raw = entry.get(key)
        if isinstance(raw, dict):
            return sum(len(v) for v in raw.values() if isinstance(v, list))
    return _count(entry.get("salvaged_items")) or 0


def logged_shard(entry: dict[str, Any]) -> str | None:
    """The assess shard an attempt belongs to: the entry's ``shard`` (the group name from
    ``assess.shards`` or its index, as text), on an attempt whose phase is ``assess``; ``None`` on any
    other attempt, so a run without shards (sequential) counts none."""
    raw = entry.get("shard")
    if entry.get("phase") != "assess" or isinstance(raw, bool) or not isinstance(raw, str | int):
        return None
    return str(raw)


def measured_output_rate(entries: list[dict[str, Any]]) -> tuple[float | None, int]:
    """The run's own output rate, for the estimate of a cut call: the MEDIAN output tokens per second of
    the attempts that reported usage (a logged ``usage`` with output tokens above 0 and wall seconds above 0;
    unsent, faulted, replayed and fake entries are left out), with the number of attempts it rests on.
    ``(None, 0)`` when no attempt qualifies. The median, not the mean, so one odd call (a short answer
    after a long wait) does not pull the rate."""
    rates: list[float] = []
    for e in entries:
        if e.get("sent") is False or "fault" in e or e.get("replayed") or e.get("fake") or unrecorded_reason(e):
            continue
        out = _count((e.get("usage") or {}).get("output_tokens")) if isinstance(e.get("usage"), dict) else None
        wall = _offset(e.get("elapsed_s"))
        if out and wall:
            rates.append(out / wall)
    if not rates:
        return None, 0
    rates.sort()
    mid = len(rates) // 2
    median = rates[mid] if len(rates) % 2 else (rates[mid - 1] + rates[mid]) / 2
    return median, len(rates)


def _estimate_cost(tot: dict[str, int]) -> float:
    p = PRICE_TABLE["usd_per_mtok"]
    return (tot["input_tokens"] * p["input"] + tot["cache_creation_input_tokens"] * p["cache_write"]
            + tot["cache_read_input_tokens"] * p["cache_read"] + tot["output_tokens"] * p["output"]) / 1e6


def journal_usage(run_dir: RunDir) -> dict[str, Any]:
    """Usage, served models, truncated calls and cost summed over every entry of ``llm.jsonl``,
    and the attempts whose usage is unknown (``calls_with_unrecorded_usage``: call ID, stage,
    purpose, attempt, wall seconds, reason). When any exist, the totals are a lower bound.

    Latency redesign: a cut attempt may log an estimate of its usage. Each one is listed in
    ``estimated_usage_of_unrecorded_calls`` (``estimated: true``) and summed in ``estimated_totals``,
    never in the measured totals, which sum logged ``usage`` only. ``salvaged_calls`` and
    ``salvaged_items`` count the attempts that kept finished items of a cut answer, and
    ``assess_shards`` the distinct ``shard`` markers of the assess attempts (:func:`logged_shard`)."""
    tot = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    est_rows: list[dict[str, Any]] = []
    est_tot = dict.fromkeys(USAGE_FIELDS, 0)
    salvaged_calls = 0
    salvaged_items = 0
    shards: set[str] = set()
    served: set[str] = set()
    cost_logged = 0.0
    have_cost = False
    calls = 0
    truncations: list[dict[str, Any]] = []
    unrecorded: list[dict[str, Any]] = []
    entries = list(JsonlWriter(run_dir.llm_log).read())
    rate, rate_calls = measured_output_rate(entries)
    bases: set[str] = set()
    for e in entries:
        calls += 1
        if e.get("outcome") == "LLMTruncatedError":
            truncations.append({"call_id": e.get("call_id"), "stage": e.get("phase"), "purpose": e.get("purpose")})
        reason = unrecorded_reason(e)
        if reason is not None:
            wall = e.get("elapsed_s")
            unrecorded.append({"call_id": e.get("call_id"), "stage": e.get("phase"), "purpose": e.get("purpose"),
                               "attempt": e.get("attempt"),
                               "wall_s": round(float(wall), 3) if isinstance(wall, int | float) else None,
                               "reason": reason})
            est = logged_estimate(e)
            if est is not None:
                logged_out = est["output_tokens"]
                wall_s = _offset(wall)
                if rate is not None and wall_s:
                    est["output_tokens"], basis = round(rate * wall_s), "measured_rate"
                else:
                    basis = "constant"                 # the logged figure (streamed characters at a constant)
                bases.add(basis)
                est_rows.append({"call_id": e.get("call_id"), "stage": e.get("phase"), "purpose": e.get("purpose"),
                                 "attempt": e.get("attempt"), "reason": reason, "estimated": True, **est,
                                 "logged_output_tokens": logged_out, "output_basis": basis})
                for k in USAGE_FIELDS:
                    est_tot[k] += est[k]
        items = logged_salvage(e)
        if items:
            salvaged_calls += 1
            salvaged_items += items
        shard = logged_shard(e)
        if shard is not None:
            shards.add(shard)
        for k in tot:
            tot[k] += int((e.get("usage") or {}).get(k) or 0)
        if e.get("outcome", "ok") == "ok" and e.get("model"):
            served.add(str(e["model"]))
        c = e.get("call_cost_usd")
        if isinstance(c, int | float):
            cost_logged += float(c)
            have_cost = True
    estimate = _estimate_cost(tot)
    return {**tot, "calls": calls, "served_models": sorted(served), "truncations": truncations,
            "calls_with_unrecorded_usage": unrecorded,
            "estimated_usage_of_unrecorded_calls": est_rows,
            "estimated_totals": {"estimated": True, "calls": len(est_rows), **est_tot,
                                 "cost_usd": round(_estimate_cost(est_tot), 6), "cost_source": "price table estimate",
                                 "output_basis": (bases.pop() if len(bases) == 1 else "mixed") if bases
                                 else ("measured_rate" if rate is not None else "constant"),
                                 "output_tokens_per_s": round(rate, 3) if rate is not None else None,
                                 "output_rate_calls": rate_calls},
            "salvaged_calls": salvaged_calls, "salvaged_items": salvaged_items,
            "assess_shards": len(shards),
            "cost_usd": round(cost_logged if have_cost else estimate, 6),
            "cost_source": "llm.jsonl call_cost_usd (client-side estimate)" if have_cost else "price table estimate"}


def _offset(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0 else None


def call_spans(run_dir: RunDir) -> dict[str, tuple[float, float]]:
    """Per phase, the run-clock span of its model attempts: from the earliest ``start_offset_s`` to
    the latest ``start_offset_s + elapsed_s``. Attempts without a start offset (a log written before
    the latency redesign) are left out, so a sequential run's log gives no spans."""
    spans: dict[str, tuple[float, float]] = {}
    for e in JsonlWriter(run_dir.llm_log).read():
        start = _offset(e.get("start_offset_s"))
        if start is None or not e.get("phase"):
            continue
        end = start + (_offset(e.get("elapsed_s")) or 0.0)
        phase = str(e["phase"])
        lo, hi = spans.get(phase, (start, end))
        spans[phase] = (min(lo, start), max(hi, end))
    return spans


def stage_timing(phase_seconds: dict[str, float], spans: dict[str, tuple[float, float]]) -> dict[str, Any]:
    """``extra.timing.stages``: per stage that ran, its members' own wall seconds (``members``), their
    plain sum (``sum_of_member_s``) and the stage's wall time (``wall_s``), which is never the sum
    when members overlapped. ``wall_basis`` says how ``wall_s`` was reached:

    * ``single_member``: the one member's seconds;
    * ``member_spans``: the span from the earliest member start to the latest member end on the run
      clock, read from the members' model attempts (``call_spans``), and at least the longest member;
      a lower bound of the stage's wall time (code work before a member's first call is not seen);
    * ``sequential_sum``: the log has no start offsets (a run before the latency redesign, whose
      members ran one after another), so the sum is the wall time.

    A member's row carries ``start_offset_s`` and ``end_offset_s`` of its model attempts, or ``null``."""
    out: dict[str, Any] = {}
    for stage in STAGE_ORDER:
        ran = [p.value for p in STAGE_MEMBERS[stage] if p.value in phase_seconds]
        if not ran:
            continue
        members = {}
        for p in ran:
            span = spans.get(p)
            members[p] = {"seconds": round(float(phase_seconds[p]), 3),
                          "start_offset_s": round(span[0], 3) if span else None,
                          "end_offset_s": round(span[1], 3) if span else None}
        total = round(sum(m["seconds"] for m in members.values()), 3)
        seen = [spans[p] for p in ran if p in spans]
        if len(ran) == 1:
            wall, basis = members[ran[0]]["seconds"], "single_member"
        elif seen:
            span_s = max(hi for _, hi in seen) - min(lo for lo, _ in seen)
            wall, basis = round(max(span_s, *(m["seconds"] for m in members.values())), 3), "member_spans"
        else:
            wall, basis = total, "sequential_sum"
        out[stage.value] = {"members": members, "wall_s": wall, "sum_of_member_s": total, "wall_basis": basis}
    return out


def session_reopens(ctx: RunContext) -> dict[str, Any]:
    """The tool-server session reopens of this process (``MCPToolGateway.session_events``, found
    through the gateway stack): ``session_reopens`` (the count, 0 when none or a doc-only run) and
    ``session_reopens_by_server``. Only counts and server names: a reason can quote a server error."""
    from sit_review_agent.tools.mcp_client import find_attr

    events = find_attr(ctx.tools, "session_events") if ctx.tools is not None else None
    by_server: dict[str, int] = {}
    for ev in events if isinstance(events, list) else []:
        server = str(ev.get("server")) if isinstance(ev, dict) else "unknown"
        by_server[server] = by_server.get(server, 0) + 1
    return {"session_reopens": sum(by_server.values()), "session_reopens_by_server": dict(sorted(by_server.items()))}


def run_clock_s(ctx: RunContext) -> float:
    """The run's wall total: the live run clock, else the clock recorded at the last checkpoint
    (``budget.elapsed_s``), else 0.0."""
    b = ctx.state.budget
    if b.started_monotonic:
        return round(max(0.0, ctx.elapsed_s()), 3)
    return round(b.elapsed_s, 3)


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
        mode=st.mode, k_index=st.k_index,
        previous_run_id=Path(st.previous_run_dir).name if st.previous_run_dir else None,
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
               "refusals": refusals, "truncations": usage["truncations"],
               "calls_with_unrecorded_usage": usage["calls_with_unrecorded_usage"],
               "cost_usd_lower_bound": bool(usage["calls_with_unrecorded_usage"]),
               "estimated_usage_of_unrecorded_calls": usage["estimated_usage_of_unrecorded_calls"],
               "estimated_usage_totals": usage["estimated_totals"],
               "assess_shards": usage["assess_shards"],
               # condition B0 only (eval/prereg.yaml tier_A): the assess stage was one call over every criterion
               **({"assess_mode": "single_call: condition B0, one assess call over every criterion "
                                  "(prompts/assess_single.md), no understand, plan, research or refine"}
                  if st.condition == "B0" else {}),
               "salvaged_calls": usage["salvaged_calls"], "salvaged_items": usage["salvaged_items"],
               "sdk_client": {"max_retries": 0, "timeout_s": cfg.agent.llm.timeout_s,
                              "gateway_max_retries": cfg.agent.llm.max_retries},
               "calls_logged": usage["calls"]},
        tools={"transport": transport_label(cfg), "cassette_set_sha256": _cassette_set_sha256(cfg),
               "url_policy_sha256": _file_sha(url_policy),
               "servers": [{"name": s.name, "enabled": s.enabled,
                            "url_sha256": sha256_text(endpoints[s.name]) if s.name in endpoints else None,
                            "allow_tools": list(s.allow_tools), "protocol_version": None,
                            "tools_list_sha256": None, "health_at_start": None} for s in cfg.tools.servers],
               "tool_calls": len(tool_ids), **session_reopens(ctx)},
        stop={"active_rules": list(cfg.stop_rules.active), "params": cfg.stop_rules.model_dump(mode="json"),
              "stop_reason": st.stop_reason.model_dump(mode="json") if st.stop_reason else None,
              # params are the effective rules; a deadline other than the profile's adds what they were scaled from
              **({"scaled_from": cfg.stop_rules.scaled_from.model_dump(mode="json")}
                 if cfg.stop_rules.scaled_from is not None else {})},
        fault_injection={"profile": sched_id or "none", "schedule_sha256": sched_sha},
        timing={"wall_clock_s": run_clock_s(ctx),
                "per_stage_s": dict(st.budget.phase_seconds),
                "stages": stage_timing(st.budget.phase_seconds, call_spans(rd))},
        outputs=dict(outputs) if outputs else {},
        deviations=devs,
        finding_ids=manifest_record(st.finding_ids, [f.id for f in st.findings]),
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
        condition=st.condition,
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
