"""Typed loader for ``config/*.yaml``: the "modify on the spot" surface (runbook §4).

``config/agent.yaml`` is the entry file. Its pinned lines 1-12 (model, per-stage effort,
max_tokens, allow_fallback, persona) are followed by free-layout keys (LLM retry policy, the
``claude_code`` block, the ``assess.shards`` criterion groups, phase flags, transport, fault
schedule, report options) and a ``files:`` block naming the other files:
``stop_rules.yaml`` (stop rules, budgets, reserves and ``stage_limits_s``), ``tools.yaml`` (servers
and tool allowlists), ``criteria.yaml``, ``endpoints.yaml``, ``url_policy.yaml`` and ``persona.yaml``. Paths in
``files:`` and ``tools.yaml url_policy`` are relative to the directory of ``agent.yaml``.

:func:`load_config` returns a frozen :class:`EffectiveConfig` (all files merged, CLI overrides
applied, every source file hashed) whose :meth:`EffectiveConfig.sha256` goes into the manifest.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_validator,
)

from sit_review_agent.errors import ConfigError
from sit_review_agent.hashing import sha256_file, sha256_json
from sit_review_agent.models import Kind, Severity
from sit_review_agent.paths import config_dir, repo_root
from sit_review_agent.states import EFFORT_KEY, OPTIONAL_PHASES, PhaseName

EffortLevel = Literal["low", "medium", "high", "xhigh", "max"]

#: Models accepted by the gateway: adaptive thinking plus ``output_config.effort`` (runbook §4.2 #4).
#: Anything other than ``claude-opus-5-5`` is a disclosed deviation from ADR-002.
SUPPORTED_MODELS: frozenset[str] = frozenset({
    "claude-opus-5-5", "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7",
    "claude-sonnet-5-5", "claude-sonnet-5",
})


class Transport(StrEnum):
    LIVE = "live"
    RECORD = "record"
    REPLAY = "replay"
    FAKE = "fake"


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ================================================================================= agent.yaml


class EffortConfig(_Cfg):
    """Per-stage effort (agent.yaml lines 3-9). One level per conversation (ADR-002)."""

    plan: EffortLevel
    research: EffortLevel
    assess: EffortLevel
    refine: EffortLevel
    verify: EffortLevel
    report: EffortLevel


class LLMSettings(_Cfg):
    timeout_s: float = 600.0
    max_retries: int = Field(4, ge=0, description="gateway-owned; the SDK runs with max_retries=0")
    backoff_base_s: float = 2.0
    backoff_max_s: float = 60.0
    refusal_retries: int = Field(1, ge=0, le=1)
    first_call_network_window_s: float = Field(
        10.0, ge=0, description="connection errors on the first model call of a run are retried only this long "
                                "(robustness NET-02); later calls keep max_retries")
    context_window_tokens: int | None = Field(
        None, ge=1, description="model context window for the pre-send size check (robustness LLM-10); "
                                "null = the known window of the configured model")
    backend: Literal["anthropic_api", "claude_code"] = Field(
        "anthropic_api", description="claude_code: headless Claude Code (ADR-010); anthropic_api: ANTHROPIC_API_KEY")


class ClaudeCodeSettings(_Cfg):
    """``claude_code:`` block, used when ``llm.backend`` is ``claude_code`` (ADR-010)."""

    executable: str = "claude"
    extra_args: list[str] = Field(default_factory=list)
    max_budget_usd_per_call: float | None = Field(None, gt=0, description="passed as --max-budget-usd when set")
    inherit_api_key: bool = Field(False, description="false: drop ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN from "
                                                     "the claude -p environment so it bills the subscription")


class AssessShard(_Cfg):
    """One criterion group of the concurrent assess stage: one model call that assesses these
    criteria from the document and the criteria only (design section 4)."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    criteria: list[str]

    @model_validator(mode="after")
    def _non_empty_and_unique(self) -> AssessShard:
        if not self.criteria:
            raise ValueError(f"assess.shards group {self.name!r} is empty: list at least one criterion id")
        seen: set[str] = set()
        for c in self.criteria:
            if c in seen:
                raise ValueError(f"criterion {c!r} is listed twice in group {self.name!r}")
            seen.add(c)
        return self


class AssessSettings(_Cfg):
    """``assess:`` block of ``agent.yaml``: the criterion groups that run as concurrent shards in
    stage 1 (design section 4). Every criterion is in at most one group; the unknown-criterion check
    is cross-file (:class:`EffectiveConfig`). A criterion of the run that is in no group (one
    appended live, runbook §4.2 #1) forms its own shard: :meth:`shards_for`."""

    shards: list[AssessShard]

    @model_validator(mode="after")
    def _groups(self) -> AssessSettings:
        if not self.shards:
            raise ValueError("assess.shards is empty: at least one criterion group is needed "
                             "(design section 4 lists four)")
        owner: dict[str, str] = {}
        names: set[str] = set()
        for shard in self.shards:
            if shard.name in names:
                raise ValueError(f"assess.shards group name {shard.name!r} is used twice")
            names.add(shard.name)
            for c in shard.criteria:
                if c in owner:
                    raise ValueError(f"criterion {c!r} is in two groups: {owner[c]!r} and {shard.name!r}")
                owner[c] = shard.name
        return self

    def grouped_criteria(self) -> list[str]:
        return [c for s in self.shards for c in s.criteria]

    def shards_for(self, criterion_ids: Iterable[str]) -> list[AssessShard]:
        """The shards of a run whose criteria are ``criterion_ids`` (in the run's order): each
        configured group restricted to the criteria the run has (a group left with none is dropped),
        then one shard per criterion in no group, named after the criterion."""
        ids = list(dict.fromkeys(criterion_ids))
        present = set(ids)
        out = [s.model_copy(update={"criteria": [c for c in s.criteria if c in present]}) for s in self.shards]
        out = [s for s in out if s.criteria]
        grouped = set(self.grouped_criteria())
        out += [AssessShard(name=c, criteria=[c]) for c in ids if c not in grouped]
        return out


class PhasesConfig(_Cfg):
    ingest: bool = True
    understand: bool = True
    plan: bool = True
    research: bool = True
    assess: bool = True
    refine: bool = True
    verify: bool = True
    report: bool = True

    @model_validator(mode="after")
    def _mandatory(self) -> PhasesConfig:
        off = [p for p in PhaseName if not getattr(self, p.value) and p not in OPTIONAL_PHASES]
        if off:
            raise ValueError(f"phases {', '.join(off)} cannot be disabled (only {sorted(OPTIONAL_PHASES)})")
        return self

    def enabled(self, phase: PhaseName) -> bool:
        return bool(getattr(self, phase.value))


class ReplaySettings(_Cfg):
    fixtures: str | None = None
    strict: bool = True


class RecordSettings(_Cfg):
    cassette_dir: str = "tests/fixtures/cassettes"


class ReportSettings(_Cfg):
    min_severity: Severity = Severity.LOW
    template: Literal["standard", "risk_register"] = "standard"


class ConfigFiles(_Cfg):
    stop_rules: str = "stop_rules.yaml"
    tools: str = "tools.yaml"
    criteria: str = "criteria.yaml"
    endpoints: str = "endpoints.yaml"
    url_policy: str = "url_policy.yaml"
    persona: str = "persona.yaml"


class AgentConfig(_Cfg):
    """``config/agent.yaml``."""

    model: str
    effort: EffortConfig
    max_tokens: int = Field(ge=1, le=128000)
    allow_fallback: bool
    persona: str
    thinking_display: Literal["omitted", "summarized"] = "omitted"
    llm: LLMSettings = LLMSettings()
    claude_code: ClaudeCodeSettings = ClaudeCodeSettings()
    assess: AssessSettings
    phases: PhasesConfig = PhasesConfig()
    transport: Transport = Transport.LIVE
    replay: ReplaySettings = ReplaySettings()
    record: RecordSettings = RecordSettings()
    fault_schedule: str | None = None
    run_root: str = "runs"
    plan_approval: bool = False
    report: ReportSettings = ReportSettings()
    files: ConfigFiles = ConfigFiles()

    @field_validator("model")
    @classmethod
    def _supported(cls, v: str) -> str:
        if v not in SUPPORTED_MODELS:
            raise ValueError(f"model {v!r} is not supported (needs adaptive thinking and effort): "
                             f"{sorted(SUPPORTED_MODELS)}")
        return v


# ============================================================================ stop_rules.yaml


#: Config keys that were renamed; the old name is refused with the new one named, never read.
RENAMED_STOP_RULE_KEYS: dict[str, str] = {"assess_reserve_seconds": "refine_reserve_seconds"}


class StageLimits(_Cfg):
    """``stop_rules.stage_limits_s``: the run-clock second by which each stage of the concurrent
    design must have ended (design section 4: stage 1 by 265 s, refine by 465 s, the verdict call by
    530 s on a 540 s run; 441 / 775 / 883 s on the 900 s demo profile). Absolute seconds per profile,
    not a fraction of the deadline: the thinking block of a model call is a fixed cost (about 105 s for
    an assess shard at ``medium``), so the limits do not scale with ``deadline_seconds``; a profile that changes the
    deadline sets its own. Readers: W1 (``llm/runtime.py``) and W2 (``orchestrator.py``)."""

    stage_1_end: int = Field(ge=1, description="understand, plan, research and every assess shard end by here")
    refine_end: int = Field(ge=1, description="the refine call ends by here, else the merged findings stand")
    verdict_end: int = Field(ge=1, description="the verdict call ends by here, else the rule-based verdict")

    @model_validator(mode="after")
    def _increasing(self) -> StageLimits:
        if not (self.stage_1_end < self.refine_end < self.verdict_end):
            raise ValueError("stage_limits_s must increase: stage_1_end < refine_end < verdict_end, got "
                             f"{self.stage_1_end} / {self.refine_end} / {self.verdict_end}")
        return self

    def as_dict(self) -> dict[str, int]:
        return {"stage_1_end": self.stage_1_end, "refine_end": self.refine_end, "verdict_end": self.verdict_end}


class StopRulesConfig(_Cfg):
    """``config/stop_rules.yaml``. Rule names in ``active`` are resolved against the registry in
    :mod:`sit_review_agent.stop_rules` when the run starts (unknown name = ConfigError)."""

    active: list[str]
    max_tool_calls: int = Field(ge=0)
    max_research_iterations: int = Field(ge=0)
    max_input_tokens: int = Field(ge=0)
    deadline_seconds: int = Field(ge=1)
    no_marginal_gain_window: int = Field(ge=1)
    min_independent_sources: int = Field(ge=1)
    report_reserve_seconds: int = Field(60, ge=0)
    refine_reserve_seconds: int = Field(0, ge=0, description="stage 1 (research and the assess shards) ends this "
                                                             "long before the report reserve so refine keeps its "
                                                             "time (robustness LLM-05; replaced "
                                                             "assess_reserve_seconds on 2026-10-03)")
    stage_limits_s: StageLimits
    max_output_tokens: int | None = None
    #: The rules as the profile set them, when :meth:`effective` scaled these from them for another deadline;
    #: ``None`` for rules at their own run length. Private: never dumped or hashed, so a run at its profile's
    #: own deadline keeps its effective_config.json byte for byte.
    _scaled_from: StopRulesConfig | None = PrivateAttr(default=None)

    @model_validator(mode="before")
    @classmethod
    def _renamed_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            _refuse_renamed_keys(data)
        return data

    @property
    def scaled_from(self) -> StopRulesConfig | None:
        return self._scaled_from

    def planned_seconds(self) -> int:
        """The run length the stage limits and reserves were set for: ``refine_end + report_reserve_seconds``
        (775 + 125 = 900 s on the demo profile, 3420 + 180 = 3600 s on the default)."""
        lim = self.stage_limits_s
        return max(lim.refine_end + self.report_reserve_seconds, lim.verdict_end + 1)

    def effective(self) -> StopRulesConfig:
        """These rules at their own ``deadline_seconds``: the ONE place a deadline other than the profile's run
        length reaches the stage limits and the two reserves (USER_DECISIONS #47 and #48).

        A deadline from ``verdict_end + 1`` to :meth:`planned_seconds` keeps everything as set (a profile's own
        deadline included). Any other deadline multiplies the three stage limits AND the two reserves by
        ``deadline / planned``, each rounded down to whole seconds: so research's own deadline rule, the
        model-call timeouts, the verify slack and the between-phase rule all keep the split the profile encodes
        (``--profile demo --deadline 540``: limits 264 / 465 / 529 s, reserves 75 s and 200 s, research ends by
        264 s, as on the former 540 s profile). Scaling down keeps every stage and stage 1 the largest share,
        which is where findings come from; scaling up gives every stage its share of the added time. Limits
        that rounding would leave out of order (a deadline of a few seconds) fall back to a quarter, a half and
        three quarters of the deadline; below 4 s no three whole-second limits fit and the deadline is refused.
        Already effective rules are returned as they are, so every reader may call this."""
        if self._scaled_from is not None:
            return self
        lim = self.stage_limits_s.as_dict()
        d, planned = self.deadline_seconds, self.planned_seconds()
        if lim["verdict_end"] < d <= planned:
            return self
        f = d / planned
        new = {k: max(1, int(v * f)) for k, v in lim.items()}
        if not (new["stage_1_end"] < new["refine_end"] < new["verdict_end"] < d):
            new = {"stage_1_end": max(1, d // 4), "refine_end": max(2, d // 2), "verdict_end": max(3, 3 * d // 4)}
            if not (new["stage_1_end"] < new["refine_end"] < new["verdict_end"] < d):
                raise ValueError(f"deadline {d} s is too short for three stage limits in whole seconds (at least 4 s)")
        out = self.model_copy(update={"stage_limits_s": StageLimits(**new),
                                      "report_reserve_seconds": int(self.report_reserve_seconds * f),
                                      "refine_reserve_seconds": int(self.refine_reserve_seconds * f)})
        out._scaled_from = self
        return out

    def with_deadline(self, deadline_seconds: int) -> StopRulesConfig:
        """The profile's rules (before any scaling) at ``deadline_seconds``, made :meth:`effective`."""
        base = self._scaled_from or self
        return base.model_copy(update={"deadline_seconds": deadline_seconds}).effective()

    def research_end_s(self) -> int:
        """Run-clock second by which research's own deadline rule ends it: the deadline less both reserves,
        and never after the stage 1 limit (``phases/research.py``). Read on effective rules."""
        return min(self.deadline_seconds - self.report_reserve_seconds - self.refine_reserve_seconds,
                   self.stage_limits_s.stage_1_end)

    def scaling_note(self) -> str | None:
        """The announcement of :meth:`effective`'s scaling (the first progress lines of the run, the Review
        form), or ``None`` when nothing was scaled."""
        base = self._scaled_from
        if base is None:
            return None
        keys = ("stage_1_end", "refine_end", "verdict_end")
        old_l, new_l = base.stage_limits_s.as_dict(), self.stage_limits_s.as_dict()
        d, planned = self.deadline_seconds, base.planned_seconds()
        old = " / ".join(f"{old_l[k]}" for k in keys)
        new = " / ".join(f"{new_l[k]}" for k in keys)
        reserves = (f"; the two reserves with them, verify and verdict {base.report_reserve_seconds} -> "
                    f"{self.report_reserve_seconds} s and refine {base.refine_reserve_seconds} -> "
                    f"{self.refine_reserve_seconds} s, so research ends by {self.research_end_s()} s")
        if d > planned:
            return (f"deadline {d} s is longer than the {planned} s run this profile's stage limits were set for "
                    f"({old} s for stage 1, refine and the verdict): the three limits are scaled up by "
                    f"{d}/{planned} to {new} s, so every stage gets its share of the added time{reserves}")
        return (f"deadline {d} s is not above this profile's stage limits ({old} s for stage 1, refine and the "
                f"verdict, set for a {planned} s run): the three limits are scaled by {d}/{planned} to {new} s"
                f"{reserves}; a model call still streaming at its limit is cut and its finished items are kept")

    def stage_limits_problem(self) -> str | None:
        """Why the stage limits do not fit ``deadline_seconds``, or ``None``. A file-level rule
        (:func:`load_config` refuses the base file or profile that breaks it), not a model invariant:
        ``--deadline`` is applied after it, so a run may legitimately hold a deadline below its
        profile's limits; the runtime clamps and announces that (W1), as it does for the reserves."""
        if self.stage_limits_s.verdict_end >= self.deadline_seconds:
            return (f"stage_limits_s.verdict_end {self.stage_limits_s.verdict_end} s is not below deadline_seconds "
                    f"{self.deadline_seconds} s: the limits are absolute seconds, so a profile that lowers the "
                    f"deadline must set its own stage_limits_s")
        return None


def _refuse_renamed_keys(data: dict[str, Any], source: str = "") -> None:
    """An old key is an error that names the new one; it is never read, dropped or mapped."""
    for old, new in RENAMED_STOP_RULE_KEYS.items():
        if old in data:
            where = f"{source}: " if source else ""
            raise ValueError(f"{where}{old} was renamed {new} on 2026-10-03 (latency redesign: stage 1 ends this "
                             f"long before the report reserve so refine keeps its time); rename the key, it is "
                             f"not read under its old name")


# ================================================================================= tools.yaml


class ServerConfig(_Cfg):
    name: str
    enabled: bool
    allow_tools: list[str]

    def allows(self, tool_name: str) -> bool:
        return self.enabled and any(fnmatch.fnmatchcase(tool_name, pat) for pat in self.allow_tools)


class ToolsConfig(_Cfg):
    auth_env: str
    auth_header: str
    servers: list[ServerConfig]
    url_policy: str
    connect_timeout_s: float = 150.0
    call_timeout_s: float = 60.0
    cold_start_retries: int = Field(1, ge=0)
    #: Reopen a server's session before a call when it has been idle longer than this (0 = never);
    #: sit_sample_tools_1 lost every web search to a session held idle for 130 s (NET-06).
    session_idle_reopen_s: float = Field(60.0, ge=0)
    capabilities: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _capabilities_known(self) -> ToolsConfig:
        names = {s.name for s in self.servers}
        unknown = sorted(set(self.capabilities.values()) - names)
        if unknown:
            raise ValueError(f"capabilities name unknown servers: {unknown}")
        return self

    def server(self, name: str) -> ServerConfig | None:
        return next((s for s in self.servers if s.name == name), None)

    def enabled_servers(self) -> list[ServerConfig]:
        return [s for s in self.servers if s.enabled]


# ============================================================================== criteria.yaml


class Criterion(_Cfg):
    """One review criterion. ``description`` is accepted as an alias of ``question`` so the
    runbook's 4-line live append (id / description / applies_to / research_hints) loads."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    question: str = Field(min_length=1, validation_alias=AliasChoices("question", "description"))
    lab_ref: str | None = None
    kinds: list[Kind] = Field(default_factory=list, description="empty = any kind")
    applies_to: list[str] = Field(default_factory=lambda: ["all"])
    research_hints: list[str] = Field(default_factory=list)


class CriteriaConfig(_Cfg):
    criteria: list[Criterion] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> CriteriaConfig:
        ids = [c.id for c in self.criteria]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate criterion ids: {dupes}")
        return self

    def ids(self) -> list[str]:
        return [c.id for c in self.criteria]

    def get(self, criterion_id: str) -> Criterion:
        for c in self.criteria:
            if c.id == criterion_id:
                return c
        raise KeyError(criterion_id)


# ===================================================================== endpoints, url, persona


class EndpointsConfig(_Cfg):
    servers: dict[str, str]


class AuthorityHosts(_Cfg):
    """``url_policy.yaml`` ``authority:``: host lists behind ``tools.sources.classify_authority``
    (``spec/taxonomy.yaml`` ``source_authority``). An entry is a domain (subdomains match) or
    ``domain/path-prefix``. Domain-general only: no host taken from an evaluated document's own
    stack (robustness OVF-07)."""

    standards: list[str] = Field(default_factory=list)       # primary_official
    vendor_docs: list[str] = Field(default_factory=list)     # primary_official
    peer_reviewed: list[str] = Field(default_factory=list)
    preprint: list[str] = Field(default_factory=list)        # secondary
    secondary: list[str] = Field(default_factory=list)
    informal: list[str] = Field(default_factory=list)        # checked first
    docs_prefixes: list[str] = Field(default_factory=list)   # host prefixes that mean official docs


class UrlPolicy(_Cfg):
    mode: Literal["deny", "allow"] = "deny"
    allow_domains: list[str] = Field(default_factory=list)
    deny_domains: list[str] = Field(default_factory=list)
    fetch_only_from_results: bool = True
    reject_added_query_strings: bool = True
    authority: AuthorityHosts = AuthorityHosts()


class Persona(_Cfg):
    title: str
    emphasis: str


class PersonasConfig(_Cfg):
    personas: dict[str, Persona]


# ================================================================================= overrides


class ConfigOverrides(_Cfg):
    """CLI flags that override config without editing files (runbook §4.2). ``None`` = keep."""

    deadline_seconds: int | None = None
    max_tool_calls: int | None = None
    disable_tools: tuple[str, ...] = ()
    no_tools: bool = False
    allow_fallback: bool | None = None
    transport: Transport | None = None
    replay_fixtures: str | None = None
    fault_schedule: str | None = None
    plan_approval: bool | None = None
    profile: str | None = None      # overlay config/profiles/<name>.yaml (e.g. "demo"); recorded in the manifest
    condition: Literal["FULL", "B0"] = "FULL"   # --condition; B0 (eval/prereg.yaml tier_A) implies --no-tools


# ============================================================================ effective config


class EffectiveConfig(_Cfg):
    """All config files merged, overrides applied. Frozen; hash with :meth:`sha256`."""

    agent: AgentConfig
    stop_rules: StopRulesConfig
    tools: ToolsConfig
    criteria: CriteriaConfig
    endpoints: EndpointsConfig
    url_policy: UrlPolicy
    personas: PersonasConfig
    config_root: str = Field(description="directory of agent.yaml (absolute)")
    source_files: dict[str, str] = Field(default_factory=dict, description="repo-relative path -> sha256")
    cli_args: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _cross_file(self) -> EffectiveConfig:
        if self.agent.persona not in self.personas.personas:
            raise ValueError(f"persona {self.agent.persona!r} not defined in persona.yaml")
        missing = sorted({s.name for s in self.tools.enabled_servers()} - set(self.endpoints.servers))
        if missing:
            raise ValueError(f"enabled servers without an endpoint in endpoints.yaml: {missing}")
        known = set(self.criteria.ids())
        for shard in self.agent.assess.shards:
            for c in shard.criteria:
                if c not in known:
                    raise ValueError(f"assess.shards group {shard.name!r} names an unknown criterion {c!r} "
                                     f"(criteria.yaml has {sorted(known)})")
        return self

    def sha256(self) -> str:
        """``effective_config_sha256``: canonical JSON of the merged config (no paths, no hashes)."""
        return sha256_json(self.model_dump(mode="json", exclude={"config_root", "source_files"}))

    def effort_for(self, phase: PhaseName) -> EffortLevel:
        """Effort level of ``phase``'s conversation (``states.EFFORT_KEY``)."""
        return getattr(self.agent.effort, EFFORT_KEY[phase])

    def persona(self) -> Persona:
        return self.personas.personas[self.agent.persona]

    def tool_allowed(self, server: str, tool_name: str) -> bool:
        s = self.tools.server(server)
        return bool(s and s.allows(tool_name))

    def resolve_path(self, rel: str) -> Path:
        """Resolve a config-relative path (``files:``, ``url_policy``) to an absolute path."""
        p = Path(rel)
        return p if p.is_absolute() else Path(self.config_root) / p

    def resolve_repo_path(self, rel: str) -> Path:
        """Resolve a repo-relative path (``run_root``, ``record.cassette_dir``, fixtures)."""
        p = Path(rel)
        return p if p.is_absolute() else repo_root() / p


def _read_yaml(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc


def _parse(model: type[BaseModel], data: Any, path: Path) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root()))
    except ValueError:
        return str(path.resolve())


def apply_overrides(agent: AgentConfig, stop: StopRulesConfig, tools: ToolsConfig,
                    ov: ConfigOverrides) -> tuple[AgentConfig, StopRulesConfig, ToolsConfig]:
    """Return copies of the three configs with the CLI overrides applied."""
    a: dict[str, Any] = {}
    if ov.allow_fallback is not None:
        a["allow_fallback"] = ov.allow_fallback
    if ov.transport is not None:
        a["transport"] = ov.transport
    if ov.replay_fixtures is not None:
        a["replay"] = agent.replay.model_copy(update={"fixtures": ov.replay_fixtures})
    if ov.fault_schedule is not None:
        a["fault_schedule"] = ov.fault_schedule
    if ov.plan_approval is not None:
        a["plan_approval"] = ov.plan_approval
    s: dict[str, Any] = {}
    if ov.deadline_seconds is not None:
        s["deadline_seconds"] = ov.deadline_seconds
    if ov.max_tool_calls is not None:
        s["max_tool_calls"] = ov.max_tool_calls
    servers = list(tools.servers)
    no_tools = ov.no_tools or ov.condition == "B0"            # the single-call baseline is a doc-only review
    if no_tools or ov.disable_tools:
        unknown = sorted(set(ov.disable_tools) - {x.name for x in servers})
        if unknown:
            raise ConfigError(f"--disable-tool names unknown servers: {unknown}")
        servers = [x.model_copy(update={"enabled": False}) if (no_tools or x.name in ov.disable_tools) else x
                   for x in servers]
    return (agent.model_copy(update=a), stop.model_copy(update=s), tools.model_copy(update={"servers": servers}))


PROFILE_SECTIONS = ("agent", "stop_rules")


def _deep_merge(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = dict(base)
        for k, v in overlay.items():
            out[k] = _deep_merge(base.get(k), v) if k in base else v
        return out
    return overlay


def _read_profile(root: Path, name: str) -> tuple[Path, dict[str, Any]]:
    """``<config root>/profiles/<name>.yaml``: a mapping with optional ``agent`` and ``stop_rules``
    sections, deep-merged over those files before validation (a profile never changes the tools,
    criteria, endpoints or persona files)."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ConfigError(f"invalid profile name: {name!r}")
    path = root / "profiles" / f"{name}.yaml"
    data = _read_yaml(path)
    if not isinstance(data, dict) or set(data) - set(PROFILE_SECTIONS):
        raise ConfigError(f"{path}: a profile may only contain the sections {', '.join(PROFILE_SECTIONS)}")
    return path, data


def load_config(path: str | Path | None = None, overrides: ConfigOverrides | None = None) -> EffectiveConfig:
    """Load ``agent.yaml`` (default ``<repo>/config/agent.yaml``; a directory means
    ``<dir>/agent.yaml``) and every file it names, apply ``overrides``, validate across files.

    Raises :class:`~sit_review_agent.errors.ConfigError` with the file name on any problem.
    """
    agent_path = Path(path) if path is not None else config_dir() / "agent.yaml"
    if agent_path.is_dir():
        agent_path = agent_path / "agent.yaml"
    root = agent_path.resolve().parent
    ov = overrides or ConfigOverrides()
    profile_path, profile = _read_profile(root, ov.profile) if ov.profile else (None, {})
    agent = _parse(AgentConfig, _deep_merge(_read_yaml(agent_path), profile.get("agent", {})), agent_path)
    files = agent.files
    paths = {
        "stop_rules": root / files.stop_rules, "tools": root / files.tools, "criteria": root / files.criteria,
        "endpoints": root / files.endpoints, "persona": root / files.persona,
    }
    profile_stop = profile.get("stop_rules", {})
    if isinstance(profile_stop, dict):
        try:
            _refuse_renamed_keys(profile_stop, str(profile_path))
        except ValueError as exc:
            raise ConfigError(str(exc)) from None
    stop = _parse(StopRulesConfig, _deep_merge(_read_yaml(paths["stop_rules"]), profile_stop), paths["stop_rules"])
    problem = stop.stage_limits_problem()
    if problem:
        raise ConfigError(f"{profile_path if profile_stop else paths['stop_rules']}: {problem}")
    tools = _parse(ToolsConfig, _read_yaml(paths["tools"]), paths["tools"])
    criteria = _parse(CriteriaConfig, _read_yaml(paths["criteria"]), paths["criteria"])
    endpoints = _parse(EndpointsConfig, _read_yaml(paths["endpoints"]), paths["endpoints"])
    personas = _parse(PersonasConfig, _read_yaml(paths["persona"]), paths["persona"])
    url_path = root / tools.url_policy
    url_policy = _parse(UrlPolicy, _read_yaml(url_path), url_path)
    profile_rules = stop
    agent, stop, tools = apply_overrides(agent, stop, tools, ov)
    try:
        stop = stop.effective()             # the one scaling of limits and reserves to a non-profile deadline
    except ValueError as exc:
        raise ConfigError(f"--deadline: {exc}") from None
    if stop.scaled_from is not None:
        stop._scaled_from = profile_rules   # what they were scaled from, with the profile's own deadline
    hashed = [agent_path, *paths.values(), url_path, *([profile_path] if profile_path else [])]
    try:
        return EffectiveConfig(
            agent=agent, stop_rules=stop, tools=tools, criteria=criteria, endpoints=endpoints,
            url_policy=url_policy, personas=personas, config_root=str(root),
            source_files={_rel(p): sha256_file(p) for p in hashed},
            cli_args=ov.model_dump(mode="json", exclude_defaults=True),
        )
    except ValidationError as exc:
        raise ConfigError(f"{agent_path}: {exc}") from exc
