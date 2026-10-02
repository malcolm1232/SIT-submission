"""Typed loader for ``config/*.yaml``: the "modify on the spot" surface (runbook §4).

``config/agent.yaml`` is the entry file. Its pinned lines 1-12 (model, per-stage effort,
max_tokens, allow_fallback, persona) are followed by free-layout keys (LLM retry policy, phase
flags, transport, fault schedule, report options) and a ``files:`` block naming the other files:
``stop_rules.yaml`` (stop rules and budgets), ``tools.yaml`` (servers and tool allowlists),
``criteria.yaml``, ``endpoints.yaml``, ``url_policy.yaml`` and ``persona.yaml``. Paths in
``files:`` and ``tools.yaml url_policy`` are relative to the directory of ``agent.yaml``.

:func:`load_config` returns a frozen :class:`EffectiveConfig` (all files merged, CLI overrides
applied, every source file hashed) whose :meth:`EffectiveConfig.sha256` goes into the manifest.
"""

from __future__ import annotations

import fnmatch
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

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
    assess_reserve_seconds: int = Field(0, ge=0, description="research ends this long before the report reserve "
                                                             "so assess keeps its time (robustness LLM-05)")
    max_output_tokens: int | None = None


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
    if ov.no_tools or ov.disable_tools:
        unknown = sorted(set(ov.disable_tools) - {x.name for x in servers})
        if unknown:
            raise ConfigError(f"--disable-tool names unknown servers: {unknown}")
        servers = [x.model_copy(update={"enabled": False}) if (ov.no_tools or x.name in ov.disable_tools) else x
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
    stop = _parse(StopRulesConfig, _deep_merge(_read_yaml(paths["stop_rules"]), profile.get("stop_rules", {})),
                  paths["stop_rules"])
    tools = _parse(ToolsConfig, _read_yaml(paths["tools"]), paths["tools"])
    criteria = _parse(CriteriaConfig, _read_yaml(paths["criteria"]), paths["criteria"])
    endpoints = _parse(EndpointsConfig, _read_yaml(paths["endpoints"]), paths["endpoints"])
    personas = _parse(PersonasConfig, _read_yaml(paths["persona"]), paths["persona"])
    url_path = root / tools.url_policy
    url_policy = _parse(UrlPolicy, _read_yaml(url_path), url_path)
    agent, stop, tools = apply_overrides(agent, stop, tools, ov)
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
