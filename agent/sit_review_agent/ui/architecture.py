"""The Architectural design view (5 Oct 2026): the agent's architecture as a diagram whose every box opens a
"Simple" and an "Advanced" account of that part. Read-only.

The words live in ``static/architecture.json``; every number and name they quote is a ``{placeholder}`` filled
here from the configuration and the code the agent itself runs with, so the page cannot drift from either:

* the assess shards and the criteria from ``config/agent.yaml`` and ``config/criteria.yaml``;
* the MCP servers, enabled or not, from ``config/tools.yaml``;
* the LLM backends from the ``llm.backend`` field of ``config.py`` and the default from ``config/agent.yaml``;
* the tool gateway's layers from the module docstring of ``tools/gateway.py`` (each name checked to be a class
  of that module);
* the stage order, the stage 1 members and their dependencies from ``states.py``;
* the research, verify and anchor limits from the constants and config the phases read;
* the demo profile's deadline and stage limits from ``config/profiles/demo.yaml``.

A placeholder this module cannot fill is an error (``KeyError``), never a blank.
"""

from __future__ import annotations

import json
import re
import string
from pathlib import Path
from typing import Any, get_args

STATIC_DIR = Path(__file__).parent / "static"
CONTENT = STATIC_DIR / "architecture.json"

#: ``<path>`` or ``<path> <symbol>``: a repository file, optionally with a name that must occur in it.
SRC_RE = re.compile(r"^(?P<path>[\w./-]+)(?: (?P<symbol>[\w.#-]+))?$")


def _join(items: list[str], last: str = "and") -> str:
    items = [str(i) for i in items]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {last} " + items[-1]


def tool_layers(gateway: Any = None) -> list[str]:
    """The tool gateway's layers, outermost first, as ``tools/gateway.py`` (or ``gateway``) lists them in its module
    docstring; the base line names its alternatives (live, cassette replay, fake). Only names that are classes there."""
    if gateway is None:
        from sit_review_agent.tools import gateway

    doc = gateway.__doc__ or ""
    block = doc.split("::", 1)[1] if "::" in doc else ""
    out: list[str] = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            if out:
                break
            continue
        name = line.split()[0]
        if name == "base":
            names = [n for n in re.findall(r"[A-Z]\w+", line) if isinstance(getattr(gateway, n, None), type)]
            out.append(" | ".join(names))
        elif isinstance(getattr(gateway, name, None), type):
            out.append(name)
    return out


#: The offline robustness results table (``tests/robustness/README.md``): its P0 row gives the scenario counts.
ROBUSTNESS_SUMMARY = Path("tests/robustness/results/robustness_summary.txt")


def robustness_summary(repo_root: Path | None = None) -> dict[str, Any]:
    """Total, pass, fail and blocked of the P0 row of the robustness summary, or "not recorded" when the file
    is not there (an installed package without the tests)."""
    from sit_review_agent.paths import repo_root as _root

    path = (repo_root or _root()) / ROBUSTNESS_SUMMARY
    keys = ("robust_total", "robust_pass", "robust_fail", "robust_blocked")
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            cells = line.split()
            if cells[:1] == ["P0"]:
                total, ok, fail, _flaky, blocked = (int(c) for c in cells[1:6])
                return dict(zip(keys, (total, ok, fail, blocked), strict=True))
    except (OSError, ValueError):
        pass
    return dict.fromkeys(keys, "not recorded")


def facts(cfg: Any, demo: Any | None = None) -> dict[str, Any]:
    """Every value the content quotes, from ``cfg`` (the effective config) and, for the demo numbers, ``demo``
    (the same config with the demo profile; ``cfg`` when there is none)."""
    from sit_review_agent.config import LLMSettings, Transport
    from sit_review_agent.ingest.anchor import AnchorRules
    from sit_review_agent.llm.runtime import CONTEXT_MARGIN
    from sit_review_agent.orchestrator import Orchestrator
    from sit_review_agent.phases import research, verify
    from sit_review_agent.states import PHASE_ORDER, STAGE_1_DEPENDS, STAGE_MEMBERS, STAGE_ORDER, Stage
    from sit_review_agent.tools.gateway import PolicyToolGateway
    from sit_review_agent.ui.stages import INVARIANTS
    from sit_review_agent.ui import naming

    demo = demo or cfg
    criteria = [c.id for c in cfg.criteria.criteria]
    shards = cfg.agent.assess.shards_for(criteria)
    servers = list(cfg.tools.servers)
    enabled = [s.name for s in servers if s.enabled]
    disabled = [s.name for s in servers if not s.enabled]
    backends = list(get_args(LLMSettings.model_fields["backend"].annotation))
    sr, dr = cfg.stop_rules, demo.stop_rules
    rules = AnchorRules()
    waits = {p.value: [d.value for d in PHASE_ORDER if d in deps] for p, deps in STAGE_1_DEPENDS.items()}
    layers = tool_layers()
    return {
        "shard_count": len(shards),
        "shards": [{"name": s.name, "criteria": list(s.criteria)} for s in shards],
        "shard_names": _join([s.name for s in shards]),
        "criteria_count": len(criteria),
        "stage_count": len(STAGE_ORDER),
        "stage_order": " -> ".join(s.value.replace("_", " ") for s in STAGE_ORDER),
        "stage_1_members": _join([p.value for p in STAGE_MEMBERS[Stage.STAGE_1]]),
        "research_waits_for": _join(waits["research"]),
        "backends": backends,
        "backend_list": _join(backends, "or"),
        "backend_list_marked": _join([f"__{b}__" for b in backends], "or"),  # each name underlined in a panel
        "backend_default": cfg.agent.llm.backend,
        "transports": " | ".join(t.value for t in Transport),
        "tool_layers": layers,
        "tool_layer_chain": " -> ".join(layers),
        "servers": [{"name": s.name, "enabled": s.enabled} for s in servers],
        "server_count": len(servers),
        "servers_enabled": _join(enabled) or "none",
        "servers_enabled_count": len(enabled),
        "servers_disabled": _join(disabled) or "none",
        "max_tool_calls": sr.max_tool_calls,
        "max_research_iterations": sr.max_research_iterations,
        "min_independent_sources": sr.min_independent_sources,
        "active_stop_rules": _join(list(sr.active)),
        "stop_rules_active": list(sr.active),
        "no_marginal_gain_window": sr.no_marginal_gain_window,
        "max_input_tokens": f"{sr.max_input_tokens:,}",
        "report_reserve_s": f"{sr.report_reserve_seconds:.0f}",
        "max_rounds_per_iteration": research.MAX_ROUNDS_PER_ITERATION,
        "max_tool_text_chars": f"{research.MAX_TOOL_TEXT_CHARS:,}",
        "repair_min_slack_s": f"{verify.REPAIR_MIN_SLACK_S:.0f}",
        "fuzzy_threshold": f"{rules.fuzzy_threshold:.2f}",
        "min_quote_tokens": rules.min_quote_tokens,
        "invariant_count": len(INVARIANTS),
        "deadline_s": sr.deadline_seconds,
        "demo_deadline_s": dr.deadline_seconds,
        "demo_stage_1_end": dr.stage_limits_s.stage_1_end,
        "demo_refine_end": dr.stage_limits_s.refine_end,
        "demo_verdict_end": dr.stage_limits_s.verdict_end,
        "max_tokens": f"{cfg.agent.max_tokens:,}",
        "model": cfg.agent.model,
        # the capabilities plan offers the model: those whose server is enabled (phases/plan.py enabled_capabilities)
        "capabilities": _join(sorted(c for c, srv in cfg.tools.capabilities.items() if srv in enabled), "or") or "none",
        "stage1_grace_s": f"{Orchestrator.stage1_grace_s:.0f}",
        "session_idle_reopen_s": f"{cfg.tools.session_idle_reopen_s:.0f}",
        "connect_timeout_s": f"{cfg.tools.connect_timeout_s:.0f}",
        "tool_error_limit": PolicyToolGateway.TOOL_ERROR_LIMIT,
        "context_margin_pct": f"{CONTEXT_MARGIN * 100:.0f}",
        "first_call_window_s": f"{cfg.agent.llm.first_call_network_window_s:.0f}",
        **robustness_summary(),
        **naming.names(),
    }


class _Strict(string.Formatter):
    """``str.format`` over ``facts`` that refuses a name it does not know (KeyError) and a list value."""

    def get_value(self, key: Any, args: Any, kwargs: Any) -> Any:
        value = kwargs[key]
        if isinstance(value, (list, dict)):
            raise KeyError(f"{key} is not a text value")
        return value


def _fill(node: Any, values: dict[str, Any]) -> Any:
    fmt = _Strict()
    if isinstance(node, str):
        return fmt.format(node, **values)
    if isinstance(node, list):
        return [_fill(n, values) for n in node]
    if isinstance(node, dict):
        return {k: (v if k in ("src", "stages", "key") else _fill(v, values)) for k, v in node.items()}
    return node


def load_content(path: Path = CONTENT) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def view(cfg: Any, demo: Any | None = None, *, path: Path = CONTENT) -> dict[str, Any]:
    """The content with every placeholder filled, plus the facts themselves (the diagram draws its shard and server
    boxes from them)."""
    values = facts(cfg, demo)
    content = load_content(path)
    out = _fill(content, values)
    # the stop-rules tip lists the active rules only, in the order they are configured
    for tip in out.get("tips", {}).values():
        if "by_rule" in tip:
            by_rule = tip.pop("by_rule")
            tip["items"] = [by_rule[r] for r in values["stop_rules_active"] if r in by_rule]
    out["facts"] = values
    return out


def sources(content: dict[str, Any]) -> list[str]:
    """Every ``src`` entry of the content, in order."""
    out: list[str] = []
    for topic in content["topics"].values():
        for block in topic.get("advanced", []):
            out += [s.strip() for s in str(block.get("src", "")).split(";") if s.strip()]
    return out


def missing_sources(content: dict[str, Any], repo_root: Path) -> list[str]:
    """Each ``src`` entry whose file does not exist under ``repo_root`` or does not contain its symbol."""
    bad: list[str] = []
    for src in sources(content):
        m = SRC_RE.match(src)
        if m is None:
            bad.append(f"{src} (not '<path>' or '<path> <symbol>')")
            continue
        p = repo_root / m["path"]
        if not p.is_file():
            bad.append(f"{src} (no such file)")
        elif m["symbol"] and m["symbol"] not in p.read_text(encoding="utf-8"):
            bad.append(f"{src} ({m['symbol']} does not occur in the file)")
    return bad
