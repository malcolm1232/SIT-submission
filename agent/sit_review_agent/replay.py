"""``dra replay <run_dir>``: re-run a recorded run offline, never inventing output (runbook §6,
docs/REPRODUCIBILITY.md §6-§7 level R0).

The run is executed again by the real orchestrator and phases, into a **new** run directory
(``<run_root>/<source_id>-replay-<hex>``, ``mode: replay``), with both gateways replaced:

* **Model calls** are served from the source run's ``llm.jsonl`` by :class:`ReplayLLMGateway`,
  in call order. Each request must match the recorded call's phase, purpose and request-body
  hash (recomputed with the recipe of the backend that made the call: ``anthropic_api``,
  ``claude_code`` or the fake gateway). A mismatch, an extra call, or a call the recording does
  not have raises :class:`ReplayDivergence` (exit 4). Recorded failures (a refusal, a schema
  error, an injected fault) are raised again as the same typed error.
* **Tool calls** are served from the source run's ``tools.jsonl`` by
  :class:`JournalReplayToolGateway` (strict: each recorded result once, matched by cassette key;
  anything else raises :class:`ReplayToolGap`, a ``ReplayMiss``). The recorded results already
  went through the tool policy (allowlist, URL policy, retries, budget), so no policy layer runs
  again. The tool catalogue offered to the model is recovered from the recorded Anthropic request
  bodies, or from the cassette directory the run used (``transport: replay|fake|record``).
* **Time** is virtual (:class:`ReplayClock`): it starts at the source run's ``created_utc`` and
  follows the recorded timeline (phase durations, call start times), so deadline and budget
  decisions see roughly the elapsed time the original run saw.

Which calls are replayed: the call IDs the final run state lists per phase (``state.llm_calls``,
``state.tool_calls``), so the calls of a stage that crashed and was re-run by ``resume`` are
served from the re-run, not from the abandoned attempt.

After the run, the replayed ``report.json`` is compared with the recorded one (run IDs, times,
paths and the run manifest are ignored); a difference is reported and exits 4. The replayed
``report.md`` starts with a "Replayed evidence" banner, the manifest records the replay as a
deviation, and ``replay.json`` holds the replay record (source, counts, comparison).

Run directories that lack what replay needs (no ``report.json``, no ``llm.jsonl``, response
content not logged, no recoverable tool catalogue, a missing input document, changed prompts)
are refused up front with :class:`ReplayDataError` (exit 2), naming the missing piece.
"""

from __future__ import annotations

import contextvars
import inspect
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sit_review_agent import errors as _errors
from sit_review_agent.clock import FakeClock, isoformat_z
from sit_review_agent.config import EffectiveConfig, Transport
from sit_review_agent.errors import AgentError, ExitCode, InputError, LLMError, ReplayMiss, ToolError
from sit_review_agent.hashing import sha256_file, sha256_json
from sit_review_agent.rundir import JsonlWriter, RunDir, write_json_atomic
from sit_review_agent.states import PhaseName

#: Line prepended to the replayed ``report.md`` (runbook §6: "stamped 'replayed evidence'").
BANNER_PREFIX = "> **Replayed evidence.**"

#: Backends whose request-hash recipe :func:`request_hash` knows.
KNOWN_BACKENDS = ("anthropic_api", "claude_code", "fake")


class ReplayDataError(InputError):
    """The source run directory lacks something replay needs (exit 2); the message names it."""


class ReplayDivergence(AgentError):
    """A replayed model request does not match the recording (exit 4). Deliberately not an
    :class:`~sit_review_agent.errors.LLMError`, so no phase can absorb it as a model failure."""

    exit_code = ExitCode.STAGE_CRASH


class ReplayToolGap(ReplayMiss):
    """A tool call (or tool listing) the recording cannot answer. A ``ReplayMiss`` subclass, so
    the research phase lets it propagate instead of degrading to doc-only (exit 4)."""

    def __init__(self, message: str, *, server: str = "?", tool: str = "?", key: str = "") -> None:
        ToolError.__init__(self, message)
        self.key = key
        self.server = server
        self.tool = tool


# ============================================================================ the source run


@dataclass
class RecordedCall:
    """One logical model call of the source run: its final ``llm.jsonl`` entry and attempts."""

    call_id: str
    entries: list[dict[str, Any]]

    @property
    def final(self) -> dict[str, Any]:
        return self.entries[-1]          # attempts are logged in order; the last one ended the call

    @property
    def phase(self) -> str:
        return str(self.final.get("phase") or "")

    @property
    def purpose(self) -> str:
        return str(self.final.get("purpose") or "")

    @property
    def ok(self) -> bool:
        return self.final.get("outcome", "ok") == "ok"

    @property
    def backend(self) -> str:
        for e in self.entries:
            if e.get("backend"):
                return str(e["backend"])
            if e.get("fake"):
                return "fake"
        return "unknown"


@dataclass
class SourceRun:
    """Everything replay reads from the recorded run directory."""

    rd: RunDir
    config: EffectiveConfig
    state: dict[str, Any]
    report: dict[str, Any]
    manifest: dict[str, Any]
    calls: list[RecordedCall]
    tool_entries: list[dict[str, Any]]
    catalogue: list[Any] | None                   # ToolSpec list, or None when not recoverable
    catalogue_source: str
    backend: str
    config_source: str = "effective_config.json"
    listings: list[list[Any]] | None = None       # tools_list.jsonl, when the run recorded it

    @property
    def run_id(self) -> str:
        return str(self.state.get("run_id") or self.rd.run_id)


def _read_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ReplayDataError(f"{path.parent}: no {path.name} ({what})") from None
    except (OSError, ValueError) as exc:
        raise ReplayDataError(f"{path}: unreadable ({type(exc).__name__}: {exc})") from None


def _final_state(rd: RunDir) -> dict[str, Any]:
    """``state.json``, else the latest checkpoint's state: the highest ordinal
    (:func:`~sit_review_agent.state.checkpoint.checkpoint_file_order`), never the last file name,
    because overlapping stage 1 members write their checkpoints in the order they end."""
    from sit_review_agent.state.checkpoint import checkpoint_file_order

    if rd.state.is_file():
        return dict(_read_json(rd.state, "final run state"))
    files = sorted(rd.checkpoints.glob("[0-9][0-9]-*.json")) if rd.checkpoints.is_dir() else []
    files.sort(key=checkpoint_file_order)                    # stable: equal ordinals keep file-name order
    if files:
        return dict(_read_json(files[-1], "checkpoint").get("state") or {})
    raise ReplayDataError(f"{rd.root}: neither state.json nor a checkpoint; replay needs the final run state "
                          "(which model and tool calls each stage used)")


def load_recorded_calls(rd: RunDir, state: Mapping[str, Any]) -> list[RecordedCall]:
    """The model calls to replay, in ``llm.jsonl`` order: every call ID the final state lists
    under ``llm_calls`` (all logged calls when the state lists none). Entries without a call ID
    (an injected fault that was retried) are attempts of no logical call and are skipped."""
    if not rd.llm_log.is_file():
        raise ReplayDataError(f"{rd.root}: no llm.jsonl; replay serves model calls only from the recorded log")
    by_id: dict[str, RecordedCall] = {}
    order: list[str] = []
    for e in JsonlWriter(rd.llm_log).read():
        cid = e.get("call_id")
        if not cid:
            continue
        if cid not in by_id:
            by_id[cid] = RecordedCall(call_id=str(cid), entries=[])
            order.append(str(cid))
        by_id[cid].entries.append(e)
    wanted = {str(c) for ids in (state.get("llm_calls") or {}).values() for c in ids}
    if wanted:
        missing = sorted(wanted - set(by_id))
        if missing:
            raise ReplayDataError(f"{rd.llm_log}: the run state lists model calls the log does not have: "
                                  f"{', '.join(missing[:10])}")
        order = [c for c in order if c in wanted]
    calls = [by_id[c] for c in order]
    if not calls:
        raise ReplayDataError(f"{rd.llm_log}: no model call recorded")
    for c in calls:
        if c.ok and not isinstance(c.final.get("content"), list):
            raise ReplayDataError(
                f"{rd.llm_log}: call {c.call_id} ({c.phase}) has no logged response content; this run was "
                "recorded before llm.jsonl kept full responses and cannot be replayed")
    return calls


def load_tool_entries(rd: RunDir, state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The tool results to replay: the first ``tools.jsonl`` entry of every call ID the final
    state lists under ``tool_calls`` (every logged call when the state has no such list)."""
    listed = state.get("tool_calls")
    wanted = {str(t.get("call_id")) for t in listed or [] if isinstance(t, Mapping) and t.get("call_id")}
    if not rd.tools_log.is_file():
        if wanted:
            raise ReplayDataError(f"{rd.root}: the run made {len(wanted)} tool call(s) but has no tools.jsonl")
        return []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for e in JsonlWriter(rd.tools_log).read():
        cid = str(e.get("call_id") or "")
        if not cid or cid in seen or (listed is not None and cid not in wanted):
            continue
        seen.add(cid)
        out.append(e)
    missing = sorted(wanted - seen)
    if missing:
        raise ReplayDataError(f"{rd.tools_log}: the run state lists tool calls the log does not have: "
                              f"{', '.join(missing[:10])}")
    return out


def recover_catalogue(config: EffectiveConfig, calls: Sequence[RecordedCall]) -> tuple[list[Any] | None, str]:
    """The tool catalogue the research phase offered the model, and where it came from:

    1. the ``tools`` of a recorded research request (the Anthropic request body, or a ``tools`` key
       on the ``llm.jsonl`` entry), exactly what the model saw;
    2. the cassette directory the run used: ``replay.fixtures`` for ``transport: replay|fake``,
       ``record.cassette_dir`` for ``transport: record`` (``tools_list/<server>.json``),
       filtered like the tool policy filters it (enabled servers, ``allow_tools``).

    ``(None, reason)`` when neither exists (a ``live`` run on the ``claude_code`` backend)."""
    from sit_review_agent.tools.gateway import ToolSpec, split_qualified

    caps = {srv: cap for cap, srv in config.tools.capabilities.items()}
    for c in calls:
        for e in c.entries:
            req = e.get("request")
            offered = e.get("tools") or (req.get("tools") if isinstance(req, dict) else None)
            if c.phase == PhaseName.RESEARCH.value and isinstance(offered, list) and offered:
                specs = []
                for t in offered:
                    server, name = split_qualified(str(t["name"]))
                    specs.append(ToolSpec(server=server, name=name, description=str(t.get("description") or ""),
                                          input_schema=dict(t.get("input_schema") or {"type": "object"}),
                                          capability=caps.get(server)))
                return specs, f"recorded request body of {c.call_id}"
    agent = config.agent
    root: str | None = None
    if agent.transport in (Transport.REPLAY, Transport.FAKE) and agent.replay.fixtures:
        root = agent.replay.fixtures
    elif agent.transport is Transport.RECORD:
        root = agent.record.cassette_dir
    if root is not None:
        path = config.resolve_repo_path(root)
        if (path / "tools_list").is_dir():
            enabled = {s.name for s in config.tools.enabled_servers()}
            specs = []
            for f in sorted((path / "tools_list").glob("*.json")):
                if f.stem not in enabled:
                    continue
                for t in json.loads(f.read_text(encoding="utf-8")):
                    if config.tool_allowed(f.stem, str(t["name"])):
                        specs.append(ToolSpec(server=f.stem, name=str(t["name"]),
                                              description=str(t.get("description") or ""),
                                              input_schema=dict(t.get("input_schema") or {"type": "object"}),
                                              capability=caps.get(f.stem)))
            return specs, f"cassette tool lists in {root}"
    return None, (f"transport {agent.transport.value} on backend {agent.llm.backend}: the tool catalogue offered "
                  "to the model is not recorded in the run directory")


def _replay_at_commit_hint(rd: RunDir) -> str:
    """Message tail for a record the current config schema refuses: the commit it was recorded at
    (``manifest.json`` ``git_commit``), where it replays. Empty when the manifest does not say."""
    try:
        commit = json.loads(rd.manifest.read_text(encoding="utf-8")).get("git_commit")
    except (OSError, ValueError, AttributeError):
        return ""
    if not isinstance(commit, str) or not commit:
        return ""
    return (f". The record was made at commit {commit[:7]} and replays only under the config schema and "
            f"phase graph of that commit: check out {commit[:7]} to replay it")


def recorded_config(rd: RunDir) -> tuple[EffectiveConfig, str]:
    """The run's exact effective config. ``effective_config.json`` is written with sorted keys, so
    the order of its mappings (``tools.capabilities``, which the plan prompt lists in order) is
    lost; the config is therefore rebuilt from the config files the run used (its ``config_root``,
    then the repo's ``config/``) plus its recorded CLI overrides, and used when its hash equals the
    recorded one. Otherwise the JSON is used as is, and the replay may diverge on mapping order."""
    from sit_review_agent.config import ConfigOverrides, load_config
    from sit_review_agent.paths import config_dir

    data = _read_json(rd.effective_config, "the run's effective config")
    try:
        recorded = EffectiveConfig.model_validate(data)
    except ValueError as exc:
        raise ReplayDataError(f"{rd.effective_config}: not a valid effective config ({exc})"
                              f"{_replay_at_commit_hint(rd)}") from None
    want = recorded.sha256()
    for root in dict.fromkeys([Path(str(data.get("config_root") or "")), config_dir()]):
        if not (root / "agent.yaml").is_file():
            continue
        try:
            cfg = load_config(root, ConfigOverrides.model_validate(dict(data.get("cli_args") or {})))
        except (AgentError, ValueError):
            continue
        if cfg.sha256() == want:
            return cfg, f"config files in {root} (hash matches the recorded effective config)"
    return recorded, "effective_config.json (no config directory reproduces its hash; mapping order may differ)"


def load_listings(rd: RunDir) -> list[list[Any]] | None:
    """The recorded tool listings (``tools_list.jsonl``: one ``{"listed_at", "tools": [{server, name,
    description, input_schema, capability}]}`` line per ``list_tools`` call), or ``None`` when the
    run did not record them."""
    from sit_review_agent.tools.gateway import ToolSpec

    path = rd.root / "tools_list.jsonl"
    if not path.is_file():
        return None
    out: list[list[Any]] = []
    for e in JsonlWriter(path).read():
        out.append([ToolSpec(server=str(t["server"]), name=str(t["name"]), description=str(t.get("description") or ""),
                             input_schema=dict(t.get("input_schema") or {"type": "object"}),
                             capability=t.get("capability")) for t in e.get("tools") or []])
    return out


def _needs_catalogue(config: EffectiveConfig, state: Mapping[str, Any]) -> bool:
    """Research lists tools when a tool gateway exists and a question needs external evidence."""
    if not config.tools.enabled_servers():
        return False
    qs = ((state.get("plan") or {}).get("questions") or [])
    return any(q.get("needs_external") and q.get("capability") != "none" for q in qs)


def load_source(run_dir: Path) -> SourceRun:
    """Read and check a recorded run directory; :class:`ReplayDataError` names what is missing."""
    from sit_review_agent.prompts import PromptBundle

    rd = RunDir(Path(run_dir))
    if not rd.root.is_dir():
        raise ReplayDataError(f"run directory not found: {rd.root}")
    has_ckpt = rd.checkpoints.is_dir() and any(rd.checkpoints.glob("[0-9][0-9]-*.json"))
    missing = [what for ok, what in (
        (rd.report_json.is_file(), "report.json (only completed runs can be replayed; an interrupted run "
                                   "continues with `dra resume`)"),
        (rd.effective_config.is_file(), "effective_config.json (the exact config the run used)"),
        (rd.llm_log.is_file(), "llm.jsonl (the recorded model outputs)"),
        (rd.state.is_file() or has_ckpt, "state.json or checkpoints/ (which calls each stage used)"),
    ) if not ok]
    if missing:
        raise ReplayDataError(f"cannot replay {rd.root}: it lacks " + "; ".join(missing))
    report = dict(_read_json(rd.report_json, "the recorded review"))
    manifest = dict(_read_json(rd.manifest, "run manifest")) if rd.manifest.is_file() else dict(
        report.get("run_manifest") or {})
    config, config_source = recorded_config(rd)
    state = _final_state(rd)
    calls = load_recorded_calls(rd, state)
    backends = {c.backend for c in calls}
    unknown = sorted(backends - set(KNOWN_BACKENDS) - {"unknown"})
    if unknown:
        raise ReplayDataError(f"{rd.llm_log}: calls from backend(s) {unknown}, whose request hash replay cannot "
                              "recompute")
    backend = next((c.backend for c in calls if c.backend != "unknown"), "unknown")
    if backend == "unknown":
        raise ReplayDataError(f"{rd.llm_log}: no entry names the backend that made the calls")
    tool_entries = load_tool_entries(rd, state)
    listings = load_listings(rd)
    catalogue, source = recover_catalogue(config, calls)
    if listings:
        catalogue, source = listings[0], "tools_list.jsonl (every listing, in order)"
    if catalogue is None and _needs_catalogue(config, state):
        raise ReplayDataError(f"{rd.root}: cannot replay the research stage: {source}. Replay needs the tool "
                              "list each research call offered (see the replay section of agent/README.md)")
    recorded = str(manifest.get("prompts_bundle_sha256") or "")
    current = PromptBundle.load().bundle_sha256
    if recorded and recorded != current:
        commit = manifest.get("git_commit") or "the run's commit"
        raise ReplayDataError(f"prompts changed since the run (bundle {recorded[:12]} recorded, {current[:12]} now); "
                              f"replay needs the prompts the run used: check out {commit}")
    return SourceRun(rd=rd, config=config, state=state, report=report, manifest=manifest, calls=calls,
                     tool_entries=tool_entries, catalogue=catalogue, catalogue_source=source, backend=backend,
                     config_source=config_source, listings=listings)


# ================================================================================ time


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


@dataclass
class _Member:
    """A phase being replayed: where its own clock stands (latency redesign: stage 1 members
    overlap, so each sees the run clock its recorded calls saw, whatever order the replay serves
    them in)."""

    phase: str
    start: float                                     # run clock when the member began
    elapsed: float                                   # the member's own position, never backwards
    wall_anchor: datetime | None = None              # first recorded call, for records without offsets


#: The member whose task is asking the clock (``None`` between phases and in the orchestrator).
_MEMBER: contextvars.ContextVar[_Member | None] = contextvars.ContextVar("replay_member", default=None)


class ReplayClock(FakeClock):
    """Virtual time following the recorded timeline.

    Inside a phase, the clock stands at the end of the last recorded call served to that phase:
    the call's recorded start offset on the run clock (``start_offset_s`` when the log has it, else
    ``started_at`` against the run's start, else its offset from the phase's first recorded call)
    plus its recorded ``elapsed_s``. Stage 1 members overlap (design section 5, "Replay"): each
    member is a task, and the clock answers each task with that member's own position, so a shard
    served after a later-ending member is not pushed past its recorded end, and a member's time
    never goes backwards. A member begins at the settled run clock (where the members that have
    ended left it, so members launched together begin together, whichever is served first); with no
    member asking, the clock is the latest position any member reached, so a stage ends with its
    latest member. ``sleep`` advances instantly."""

    def __init__(self, start: datetime, phase_seconds: Mapping[str, float]) -> None:
        super().__init__(start)
        self.phase_seconds = {str(k): float(v) for k, v in phase_seconds.items()}
        self._frontier = 0.0                              # latest position any member reached

    # -- the member asking
    @property
    def phase(self) -> str | None:
        m = _MEMBER.get()
        return m.phase if m is not None else None

    def monotonic(self) -> float:
        m = _MEMBER.get()
        return m.elapsed if m is not None else max(self._elapsed, self._frontier)

    def now_utc(self) -> datetime:
        return self._start + timedelta(seconds=self.monotonic())

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("cannot move a FakeClock backwards")
        m = _MEMBER.get()
        if m is not None:
            m.elapsed += seconds
            self._frontier = max(self._frontier, m.elapsed)
        else:
            self._elapsed = max(self._elapsed, self._frontier) + seconds
            self._frontier = self._elapsed

    def catch_up(self, elapsed: float) -> None:
        """Move the asking member (else the run clock) forward to ``elapsed``, never backwards."""
        if elapsed > self.monotonic():
            self.advance(elapsed - self.monotonic())

    # -- phases
    def begin_phase(self, phase: str) -> None:
        _MEMBER.set(_Member(phase=phase, start=self._elapsed, elapsed=self._elapsed))

    def end_phase(self, phase: str) -> None:
        m = _MEMBER.get()
        if m is not None:
            self.catch_up(m.start + self.phase_seconds.get(phase, 0.0))
            self._elapsed = max(self._elapsed, m.elapsed)   # settle: later members begin here
        _MEMBER.set(None)

    def at_recorded(self, started_at: str | None, elapsed_s: float | None = None,
                    start_offset_s: float | None = None) -> None:
        """Move the asking member to the end of a recorded call: its start on the run clock plus its
        recorded duration. ``start_offset_s`` (the run clock's elapsed seconds when the attempt
        started, logged by the streaming gateway) is exact; without it ``started_at`` against the run's
        start is used when it falls inside the member, else the offset from the member's first
        recorded call (a stage re-run by ``resume`` started on another wall clock)."""
        m = _MEMBER.get()
        if m is None:
            return
        duration = float(elapsed_s or 0.0)
        if isinstance(start_offset_s, int | float) and not isinstance(start_offset_s, bool) and start_offset_s >= 0:
            self.catch_up(float(start_offset_s) + duration)
            return
        if not started_at:
            return
        try:
            t = parse_utc(started_at)
        except ValueError:
            return
        absolute = (t - self._start).total_seconds()
        cap = self.phase_seconds.get(m.phase)
        # 1 s of slack: started_at has second precision (isoformat_z), the run clock has not
        if absolute >= m.start - 1.0 and (cap is None or absolute <= m.start + cap + 1.0):
            self.catch_up(absolute + duration)
            return
        if m.wall_anchor is None:
            m.wall_anchor = t
        offset = (t - m.wall_anchor).total_seconds() + duration
        if cap is not None:
            offset = min(offset, cap)
        self.catch_up(m.start + max(0.0, offset))


class _TimedPhase:
    """Wraps a phase so the replay clock knows which recorded phase is running."""

    def __init__(self, inner: Any, clock: ReplayClock) -> None:
        self.inner = inner
        self.name = inner.name
        self.clock = clock

    async def run(self, ctx: Any) -> Any:
        self.clock.begin_phase(self.name.value)
        ctx = await self.inner.run(ctx)
        self.clock.end_phase(self.name.value)
        return ctx


def timed_phases(clock: ReplayClock) -> dict[PhaseName, Any]:
    from sit_review_agent.phases import default_phases

    return {p: _TimedPhase(ph, clock) for p, ph in default_phases().items()}


# ================================================================================ model calls


def request_hash(backend: str, request: Any, config: EffectiveConfig, run_dir: RunDir) -> str:
    """The ``request_sha256`` the recorded backend computed for ``request``."""
    from sit_review_agent.llm.gateway import request_sha256

    model = config.agent.model
    common = {"system": request.system, "messages": request.messages, "tools": request.tools,
              "effort": request.effort, "max_tokens": request.max_tokens}
    if backend == "fake":
        return request_sha256({"model": model, **common})
    if backend == "claude_code":
        from sit_review_agent.llm.claude_code import BACKEND

        return request_sha256({"backend": BACKEND, "model": model, **common})
    if backend == "anthropic_api":
        from sit_review_agent.llm.gateway import AnthropicGateway, strip_pdf_bytes

        body = AnthropicGateway(config, run_dir).build_body(request)   # no client is created
        return sha256_json(strip_pdf_bytes(body)[0])
    raise ReplayDivergence(f"no request-hash recipe for backend {backend!r}")


def _logged_partial(value: Any) -> dict[str, Any] | None:
    """A logged ``partial`` (the finished items of a cut stream) as the dict ``LLMDeadlineError``
    takes: an object whose list fields hold the finished items; ``None`` when it is not one or holds
    no list (nothing was salvaged)."""
    if not isinstance(value, Mapping):
        return None
    out = {str(k): v for k, v in value.items() if isinstance(v, list)}
    return out or None


def _logged_usage(value: Any) -> Any:
    """A logged usage dict as a :class:`~sit_review_agent.llm.gateway.Usage`, or ``None``."""
    from sit_review_agent.llm.gateway import Usage

    if not isinstance(value, Mapping):
        return None
    counts = [value.get(k, 0) for k in Usage.__dataclass_fields__]
    if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in counts):
        return None
    return Usage(*counts)


def recorded_error(entry: Mapping[str, Any], request: Any, call_id: str) -> AgentError:
    """The typed error a failed recorded call raised, rebuilt from its ``llm.jsonl`` entry."""
    name = str(entry.get("outcome") or "")
    cls = getattr(_errors, name, None)
    message = str(entry.get("error") or entry.get("message") or name)
    phase = request.phase.value
    if not (isinstance(cls, type) and issubclass(cls, LLMError)):
        return ReplayDivergence(f"recorded call {call_id} ended with {name!r}, which replay cannot raise again")
    params = inspect.signature(cls.__init__).parameters
    details = entry.get("stop_details") if isinstance(entry.get("stop_details"), Mapping) else {}
    known = {"call_id": call_id, "phase": phase, "category": details.get("category"),
             "explanation": details.get("explanation"), "max_tokens": entry.get("max_tokens") or request.max_tokens,
             "retry_after_s": entry.get("retry_after_s"),
             # LLMError.usage is a Usage, set by ReplayLLMGateway from the recorded attempts (llm.gateway.billed);
             # the entry's own "usage" is a dict and must never reach the constructor (hub verification, session 4)
             "usage": None,
             # a cut call (latency redesign): the salvaged answer, and the estimate logged under the literal key
             # "estimated_usage" as a dict; each mapped to the constructor's type, or None when malformed
             "partial": _logged_partial(entry.get("partial")),
             "estimated_usage": _logged_usage(entry.get("estimated_usage"))}
    kwargs: dict[str, Any] = {}
    for arg, p in list(params.items())[2:]:                 # after self and the message
        if p.kind not in (p.KEYWORD_ONLY, p.POSITIONAL_OR_KEYWORD):
            continue
        if arg in known:
            kwargs[arg] = known[arg]
        elif arg in entry:
            kwargs[arg] = entry[arg]
        elif p.default is p.empty:
            kwargs[arg] = None                              # a detail the log does not keep
    try:
        return cls(message, **kwargs)  # type: ignore[no-any-return]
    except TypeError:
        return ReplayDivergence(f"recorded call {call_id} ended with {name}, which replay cannot rebuild")


class ReplayLLMGateway:
    """Serves the recorded model calls (see the module docstring). A request is matched to the
    first unserved recorded call of the same conversation whose request hash it reproduces, never
    by position: a concurrent stage 1 (latency redesign) logs its calls in completion order and
    the replay asks for them in whatever order its tasks reach the gateway. Identical requests of
    one conversation (a repair turn asked twice) are served in log order. A request no recorded
    call matches raises :class:`ReplayDivergence` and consumes nothing.

    Logs each served call to the new run's ``llm.jsonl`` with ``replayed: true``, the source call,
    zero usage (nothing was spent) and the recorded usage under ``recorded_usage``; the
    :class:`LLMResult` carries the recorded usage so token budgets behave as they did."""

    def __init__(self, source: SourceRun, run_dir: RunDir, config: EffectiveConfig, *,
                 clock: ReplayClock | None = None) -> None:
        from sit_review_agent.llm.gateway import LLMCallLog

        self.source = source
        self.calls = list(source.calls)
        self.run_dir = run_dir
        self.config = config
        self.clock = clock
        self.log = LLMCallLog(run_dir, secret_env=(config.tools.auth_env,))
        self.native_pdf = source.backend != "claude_code"
        self.served = 0
        self._pending: list[RecordedCall] = list(self.calls)
        self._usage: Any = None
        self._served: set[str] = set()
        self._fallbacks: list[Any] = []
        self._refusals: list[dict[str, Any]] = []

    def remaining(self) -> list[RecordedCall]:
        """The recorded calls not served yet, in log order."""
        return list(self._pending)

    def recorded_conversation(self, conversation_id: str) -> str:
        """The conversation ID as the source run logged it: research names its run in the
        conversation (``<run_id>-research-<n>``), and the replay runs under another run ID."""
        mine, theirs = self.run_dir.run_id, self.source.run_id
        if mine and mine != theirs and conversation_id.startswith(f"{mine}-"):
            return f"{theirs}-{conversation_id[len(mine) + 1:]}"
        return conversation_id

    @staticmethod
    def _recorded_hash(rec: RecordedCall) -> str | None:
        return next((str(e["request_sha256"]) for e in rec.entries if e.get("request_sha256")), None)

    def _match(self, request: Any) -> RecordedCall:
        """The first unserved recorded call this request reproduces, or a :class:`ReplayDivergence`
        that says what the recording has instead (nothing is consumed)."""
        conv = self.recorded_conversation(request.conversation_id)
        phase, purpose = request.phase.value, (request.purpose or "")
        n = self.served + 1
        same_conv = [r for r in self._pending if str(r.final.get("conversation_id") or conv) == conv]
        if not same_conv:
            raise ReplayDivergence(f"model call #{n} ({phase}/{purpose or '-'}, conversation {conv}) has no "
                                   f"recorded response: the recorded run made {len(self.calls)} call(s), "
                                   f"{len(self._pending)} unserved, none in that conversation")
        hashes: dict[str, str] = {}
        for rec in same_conv:
            recorded_hash = self._recorded_hash(rec)
            if recorded_hash is None:                        # a record without hashes: phase and purpose
                if rec.phase == phase and rec.purpose == purpose:
                    return rec
                continue
            backend = rec.backend if rec.backend != "unknown" else self.source.backend
            got = hashes.get(backend)
            if got is None:
                got = hashes[backend] = request_hash(backend, request, self.config, self.run_dir)
            if got == recorded_hash:
                if rec.phase != phase or rec.purpose != purpose:
                    raise ReplayDivergence(f"model call #{n} (recorded {rec.call_id}): the replay asked for "
                                           f"{phase}/{purpose or '-'}, the recording has {rec.phase}/"
                                           f"{rec.purpose or '-'}")
                return rec
        first = same_conv[0]
        got = next(iter(hashes.values()), "")
        raise ReplayDivergence(f"model call #{n} (recorded {first.call_id}) ({first.phase}/{first.purpose or '-'}): "
                               f"request body hash {got[:12]} differs from the recorded "
                               f"{str(self._recorded_hash(first))[:12]} of conversation {conv}; the replayed run is "
                               "no longer the recorded one (changed code, config, input or an earlier divergence)")

    async def call(self, request: Any) -> Any:
        from sit_review_agent.llm.gateway import LLMAttempt, LLMResult, ToolUse, Usage
        from sit_review_agent.models import FallbackEvent

        rec = self._match(request)
        entry = rec.final
        n = self.served + 1
        where = f"model call #{n} (recorded {rec.call_id})"
        recorded_hash = self._recorded_hash(rec)
        backend = rec.backend if rec.backend != "unknown" else self.source.backend
        self._pending.remove(rec)
        self.served += 1
        if self.clock is not None:
            self.clock.at_recorded(entry.get("started_at"), entry.get("elapsed_s"), entry.get("start_offset_s"))
        started = isoformat_z(self.clock.now_utc()) if self.clock is not None else str(entry.get("started_at") or "")
        u = entry.get("usage") or {}
        usage = Usage(int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
                      int(u.get("cache_creation_input_tokens") or 0), int(u.get("cache_read_input_tokens") or 0))
        self._usage = usage if self._usage is None else self._usage + usage
        model = str(entry.get("model") or self.config.agent.model)
        content = [dict(b) for b in entry.get("content") or [] if isinstance(b, Mapping)]
        self.log.log({"call_id": rec.call_id, "phase": rec.phase, "purpose": rec.purpose,
                      "conversation_id": request.conversation_id, "request_sha256": recorded_hash,
                      "model": model, "stop_reason": entry.get("stop_reason"),
                      "outcome": entry.get("outcome", "ok"), "started_at": started,
                      "usage": Usage().__dict__, "recorded_usage": usage.__dict__, "call_cost_usd": 0.0,
                      "content": content, "backend": "replay", "replayed": True,
                      "replayed_from": f"{self.source.run_id}/{rec.call_id}", "recorded_backend": backend})
        if not rec.ok:
            err = recorded_error(entry, request, rec.call_id)
            from sit_review_agent.errors import LLMRefusalError
            from sit_review_agent.llm.gateway import billed

            for e in rec.entries:                     # the recorded failure's billed usage, as the live
                ru = e.get("usage")                   # gateway reported it (LLMError.usage); none if unknown
                if isinstance(err, LLMError) and isinstance(ru, Mapping):
                    billed(err, Usage(int(ru.get("input_tokens") or 0), int(ru.get("output_tokens") or 0),
                                      int(ru.get("cache_creation_input_tokens") or 0),
                                      int(ru.get("cache_read_input_tokens") or 0)))

            if isinstance(err, LLMRefusalError):
                self._refusals.append({"call_id": rec.call_id, "stage": rec.phase, "category": err.category})
            raise err
        self._served.add(model)
        stop = str(entry.get("stop_reason") or "end_turn")
        text = "".join(str(b.get("text", "")) for b in content if b.get("type") == "text")
        tool_uses = [ToolUse(id=str(b.get("id")), name=str(b.get("name")), input=dict(b.get("input") or {}))
                     for b in content if b.get("type") == "tool_use"]
        parsed = None
        if stop not in ("tool_use", "pause_turn") and request.output_schema is not None:
            try:
                parsed = request.output_schema.model_validate_json(text)
            except ValueError as exc:
                raise ReplayDivergence(f"{where}: the recorded output does not parse as "
                                       f"{request.output_schema.__name__} ({str(exc)[:200]})") from None
        fallback = None
        fb = entry.get("fallback")
        if isinstance(fb, Mapping):
            fallback = FallbackEvent.model_validate(dict(fb))
        elif backend == "claude_code" and self.config.agent.allow_fallback and model != self.config.agent.model:
            fallback = FallbackEvent(role=rec.phase, from_model=self.config.agent.model, to_model=model,
                                     reason=f"claude_code --fallback-model ({rec.call_id})")
        if fallback is not None:
            self._fallbacks.append(fallback)
        attempts = [LLMAttempt(attempt=int(e.get("attempt") or i), started_at=str(e.get("started_at") or ""),
                               elapsed_s=float(e.get("elapsed_s") or 0.0), outcome=str(e.get("outcome", "ok")),
                               status_code=e.get("status_code"), retry_after_s=e.get("retry_after_s"))
                    for i, e in enumerate(rec.entries)]
        return LLMResult(call_id=rec.call_id, phase=request.phase, conversation_id=request.conversation_id,
                         model=model, stop_reason=stop, content=content, parsed=parsed, text=text,
                         tool_uses=tool_uses, usage=usage, request_id=entry.get("request_id"),
                         request_sha256=str(recorded_hash or ""), latency_s=0.0, attempts=attempts,
                         fallback=fallback, resumed=False)

    def usage_total(self) -> Any:
        from sit_review_agent.llm.gateway import Usage

        return self._usage or Usage()

    def served_models(self) -> set[str]:
        return set(self._served)

    def fallback_events(self) -> list[Any]:
        return list(self._fallbacks)

    def refusals(self) -> list[dict[str, Any]]:
        return list(self._refusals)


# ================================================================================ tool calls


class JournalReplayToolGateway:
    """Serves the recorded tool results (strict). Each recorded call is served once, matched by
    cassette key (or, for a call the policy refused, by server, tool and logged arguments).
    ``list_tools`` serves the recorded listings in order when the run logged them
    (``tools_list.jsonl``), else the recovered catalogue on every call (a server whose breaker
    opened mid-run is then still listed, and the replay diverges loudly)."""

    def __init__(self, entries: Sequence[Mapping[str, Any]], catalogue: Sequence[Any] | None, *,
                 catalogue_note: str = "", clock: ReplayClock | None = None,
                 listings: Sequence[Sequence[Any]] | None = None) -> None:
        self.pending = [dict(e) for e in entries]
        self.catalogue = list(catalogue) if catalogue is not None else None
        self.catalogue_note = catalogue_note
        self.clock = clock
        self.listings = [list(x) for x in listings] if listings else None
        self.served: list[str] = []

    async def list_tools(self) -> list[Any]:
        if self.listings is not None:
            if not self.listings:
                raise ReplayToolGap("the replay listed the tools more often than the recorded run did",
                                    tool="tools/list")
            return self.listings.pop(0)
        if self.catalogue is None:
            raise ReplayToolGap(f"the recording has no tool catalogue ({self.catalogue_note})",
                                tool="tools/list")
        return list(self.catalogue)

    def _take(self, server: str, tool: str, args: Mapping[str, Any]) -> dict[str, Any] | None:
        from sit_review_agent.tools.cassette import canonical_args, cassette_key

        key = cassette_key(server, tool, dict(args))
        for i, e in enumerate(self.pending):
            if e.get("cassette_key") == key:
                return self.pending.pop(i)
        cargs = canonical_args(dict(args))
        for i, e in enumerate(self.pending):
            if e.get("server") == server and e.get("tool") == tool and e.get("args") == cargs:
                return self.pending.pop(i)
        return None

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> Any:
        from sit_review_agent.errors import ToolNotAllowedError
        from sit_review_agent.tools.cassette import cassette_key
        from sit_review_agent.tools.gateway import ToolResult, split_qualified

        try:
            server, tool = split_qualified(tool_name)
        except ToolNotAllowedError:
            server, tool = "unknown", tool_name or "unknown"
        entry = self._take(server, tool, args)
        if entry is None:
            key = cassette_key(server, tool, dict(args))
            raise ReplayToolGap(f"tool call {server}/{tool} (key {key[:12]}) is not in the recording "
                                f"({len(self.pending)} recorded call(s) left)", server=server, tool=tool, key=key)
        self.served.append(str(entry["call_id"]))
        if self.clock is not None:
            self.clock.at_recorded(entry.get("started_at"), entry.get("elapsed_s"))
        return ToolResult.from_log_entry(entry)

    async def aclose(self) -> None:
        return None


# ================================================================================ comparison


#: Keys whose values legitimately differ between a run and its replay.
VOLATILE_KEYS = frozenset({"run_manifest", "run_id", "review_id", "created_at", "created_utc", "retrieved_at",
                           "started_at", "pdf_path", "snapshot_path"})


def compare_reports(recorded: Any, replayed: Any, path: str = "$") -> list[str]:
    """JSON paths where two reports differ, ignoring :data:`VOLATILE_KEYS` (run IDs, times,
    paths and the run manifest, which describes the run rather than the review)."""
    if isinstance(recorded, Mapping) and isinstance(replayed, Mapping):
        out: list[str] = []
        for k in sorted(set(recorded) | set(replayed)):
            if k in VOLATILE_KEYS:
                continue
            if k not in recorded or k not in replayed:
                out.append(f"{path}.{k}")
                continue
            out += compare_reports(recorded[k], replayed[k], f"{path}.{k}")
        return out
    if isinstance(recorded, list) and isinstance(replayed, list):
        if len(recorded) != len(replayed):
            return [f"{path} (length {len(recorded)} vs {len(replayed)})"]
        out = []
        for i, (a, b) in enumerate(zip(recorded, replayed, strict=True)):
            out += compare_reports(a, b, f"{path}[{i}]")
        return out
    return [] if recorded == replayed else [path]


# ================================================================================ the replay


@dataclass
class ReplayOutcome:
    run_dir: Path
    exit_code: int
    report_md: Path | None
    model_calls: int
    tool_calls: int
    differences: list[str]
    message: str


def replay_config(source: SourceRun, run_root: str) -> EffectiveConfig:
    """The source run's exact effective config, with the transport set to strict replay, no fault
    schedule (recorded faults are in the logs already), no plan approval, and ``run_root`` from
    the current config."""
    agent = source.config.agent.model_copy(update={
        "transport": Transport.REPLAY, "fault_schedule": None, "plan_approval": False, "run_root": run_root,
        "replay": source.config.agent.replay.model_copy(update={"strict": True})})
    return source.config.model_copy(update={"agent": agent})


def _documents(source: SourceRun, pdf: Path | None, v1: Path | None, previous: Path | None,
               scratch: Path) -> tuple[Path, Path | None, Path | None]:
    """The input document (and delta input) the replay ingests again, checked against the
    recording: a PDF must have the recorded SHA-256. A text input that has moved is rebuilt from
    the run's canonical text under its original file name (the same document ID)."""
    docs = list(source.state.get("documents") or [])
    under = next((d for d in docs if d.get("role") == "under_review"), None)
    prior = next((d for d in docs if d.get("role") == "prior_version"), None)
    if under is None:
        raise ReplayDataError(f"{source.rd.state}: no document under review")

    def resolve(ref: Mapping[str, Any], given: Path | None, flag: str) -> Path:
        recorded = Path(str(ref.get("pdf_path") or ""))
        path = given if given is not None else recorded
        if path.is_file():
            if path.suffix.lower() == ".pdf" and ref.get("sha256_pdf") and sha256_file(path) != ref["sha256_pdf"]:
                raise ReplayDataError(f"{path}: SHA-256 differs from the recorded input "
                                      f"({str(ref['sha256_pdf'])[:12]}); give the original with {flag}")
            return path
        if recorded.suffix.lower() == ".pdf" or given is not None:
            raise ReplayDataError(f"input not found: {path} (the recorded run reviewed {recorded.name}, "
                                  f"sha256 {str(ref.get('sha256_pdf') or '?')[:12]}); give it with {flag}")
        text = source.rd.root / str(ref.get("text_path") or "")
        if not text.is_file():
            raise ReplayDataError(f"input not found: {recorded} and no canonical text {text}; give it with {flag}")
        scratch.mkdir(parents=True, exist_ok=True)
        out = scratch / recorded.name
        out.write_text(text.read_text(encoding="utf-8"), encoding="utf-8")
        return out

    doc = resolve(under, pdf, "--pdf")
    prev_dir: Path | None = None
    v1_path: Path | None = None
    if source.state.get("previous_run_dir"):
        prev_dir = previous or Path(str(source.state["previous_run_dir"]))
        if not (prev_dir / "report.json").is_file():
            raise ReplayDataError(f"delta run: the previous run {prev_dir} is not available; give it with --previous")
    elif prior is not None:
        v1_path = resolve(prior, v1, "--v1")
    return doc, v1_path, prev_dir


def _stamp(rd: RunDir, source: SourceRun, outcome: ReplayOutcome) -> None:
    """Banner in ``report.md``, a deviation and the new ``report.md`` hash in ``manifest.json``."""
    from sit_review_agent.manifest import output_hashes

    note = (f"replayed evidence: re-run offline by `dra replay` from recorded run {source.run_id} "
            f"({outcome.model_calls} model call(s) from its llm.jsonl, {outcome.tool_calls} tool call(s) from its "
            "tools.jsonl); no model or tool was called")
    if rd.report_md.is_file():
        body = rd.report_md.read_text(encoding="utf-8")
        banner = (f"{BANNER_PREFIX} This report was re-run offline by `dra replay` from the recorded run "
                  f"`{source.run_id}`: model outputs come from its `llm.jsonl` and tool results from its "
                  "`tools.jsonl`. No model or tool was called, and nothing was generated anew.\n\n")
        if not body.startswith(BANNER_PREFIX):
            rd.report_md.write_text(banner + body, encoding="utf-8")
    if rd.manifest.is_file():
        m = json.loads(rd.manifest.read_text(encoding="utf-8"))
        extra = m.setdefault("extra", {})
        devs = extra.setdefault("deviations", [])
        if note not in devs:
            devs.append(note)
        extra.setdefault("outputs", {})["report_md_sha256"] = output_hashes(rd)["report_md_sha256"]
        write_json_atomic(rd.manifest, m)


async def replay_run(run_dir: Path, *, run_root: str | None = None, run_id: str | None = None,
                     pdf: Path | None = None, v1: Path | None = None, previous: Path | None = None,
                     progress: object = None) -> ReplayOutcome:
    """Replay a recorded run (module docstring). Raises :class:`ReplayDataError` (exit 2) before
    anything is written when the source lacks data; otherwise returns the outcome (exit 0 when the
    replayed report matches the recording, 4 when the replay diverged or failed)."""
    from sit_review_agent.orchestrator import RunRequest, run_review
    from sit_review_agent.tools.cassette import Redactor
    from sit_review_agent.tools.gateway import LoggingToolGateway

    source = load_source(run_dir)
    cfg = replay_config(source, run_root or source.config.agent.run_root)
    rid = run_id or f"{source.run_id}-replay-{uuid.uuid4().hex[:8]}"
    out_root = cfg.resolve_repo_path(cfg.agent.run_root) / rid
    if (out_root / "report.json").exists():
        raise ReplayDataError(f"{out_root} already holds a run; choose another --run-id")
    doc, v1_path, prev_dir = _documents(source, pdf, v1, previous, out_root / "input")
    budget = (source.state.get("budget") or {}).get("phase_seconds") or {}
    try:
        start = parse_utc(str(source.state.get("created_utc")))
    except ValueError:
        start = parse_utc("2026-01-01T00:00:00Z")
    clock = ReplayClock(start, budget)
    holders: dict[str, Any] = {}

    def llm_factory(rd: RunDir, clk: object, prog: object) -> ReplayLLMGateway:
        holders["llm"] = ReplayLLMGateway(source, rd, cfg, clock=clock)
        return holders["llm"]

    def tools_factory(rd: RunDir, resume_offset: object, clk: object, prog: object) -> Any:
        if not cfg.tools.enabled_servers():
            return None
        holders["tools"] = JournalReplayToolGateway(source.tool_entries, source.catalogue,
                                                    catalogue_note=source.catalogue_source, clock=clock,
                                                    listings=source.listings)
        return LoggingToolGateway(holders["tools"], rd, Redactor.from_env((cfg.tools.auth_env, "ANTHROPIC_API_KEY")))

    req = RunRequest(pdf=doc, config=cfg, v1_pdf=v1_path, previous_run=prev_dir, mode="replay", plan_only=False,
                     run_id=rid)
    outcome = await run_review(req, phases=timed_phases(clock), llm_factory=llm_factory,
                               tools_factory=tools_factory, clock=clock, progress=progress)
    rd = RunDir(outcome.run_dir)
    llm_gw: ReplayLLMGateway | None = holders.get("llm")
    tools_gw: JournalReplayToolGateway | None = holders.get("tools")
    n_llm = llm_gw.served if llm_gw is not None else 0
    n_tools = len(tools_gw.served) if tools_gw is not None else 0
    diffs: list[str] = []
    code = outcome.exit_code
    if code != 0:
        failure = {}
        if rd.failure.is_file():
            failure = json.loads(rd.failure.read_text(encoding="utf-8"))
        message = f"replay failed (exit {code}): {failure.get('message') or 'see failure.json'}"
    else:
        left_llm = llm_gw.remaining() if llm_gw is not None else []
        left_tools = tools_gw.pending if tools_gw is not None else source.tool_entries
        if left_llm:
            diffs.append(f"{len(left_llm)} recorded model call(s) never requested (first: {left_llm[0].call_id})")
        if left_tools:
            diffs.append(f"{len(left_tools)} recorded tool call(s) never requested "
                         f"(first: {left_tools[0].get('call_id')})")
        if rd.report_json.is_file():
            new = json.loads(rd.report_json.read_text(encoding="utf-8"))
            diffs += compare_reports(source.report, new)
        else:
            diffs.append("no report.json was produced")
        if diffs:
            code = int(ExitCode.STAGE_CRASH)
            message = (f"replay diverged from the recording: {len(diffs)} difference(s); first: {diffs[0]}")
        else:
            message = ("replayed report matches the recording (ignoring run IDs, times, paths and the run manifest)")
    result = ReplayOutcome(run_dir=rd.root, exit_code=code, report_md=rd.report_md if rd.report_md.is_file() else None,
                           model_calls=n_llm, tool_calls=n_tools, differences=diffs, message=message)
    if outcome.exit_code == 0:
        _stamp(rd, source, result)
    write_json_atomic(rd.root / "replay.json", {
        "replayed_evidence": True, "source_run_id": source.run_id, "source_run_dir": str(source.rd.root),
        "source_report_json_sha256": sha256_file(source.rd.report_json),
        "source_llm_jsonl_sha256": sha256_file(source.rd.llm_log),
        "source_tools_jsonl_sha256": sha256_file(source.rd.tools_log) if source.rd.tools_log.is_file() else None,
        "recorded_backend": source.backend, "tool_catalogue": source.catalogue_source,
        "config_source": source.config_source,
        "model_calls_replayed": n_llm, "model_calls_recorded": len(source.calls),
        "tool_calls_replayed": n_tools, "tool_calls_recorded": len(source.tool_entries),
        "exit_code": code, "matches_recording": code == 0, "differences": diffs[:200], "message": message,
    })
    return result
