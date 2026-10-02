"""Robustness fault-schedule format (research/robustness/README.md §5.2-5.3).

Schedules live in ``tests/robustness/faults/<SCENARIO-ID>.yaml`` and are selected with
``--faults`` or ``agent.yaml fault_schedule``; the schedule ID and file hash go in the manifest
(INV-09). This module is pure data + loader; the injectors are
:class:`~sit_review_agent.tools.gateway.FaultInjectingGateway` (MCP) and
:class:`~sit_review_agent.llm.gateway.FaultInjectingLLMGateway` (LLM).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sit_review_agent.errors import ConfigError
from sit_review_agent.hashing import sha256_file


class FaultType(StrEnum):
    LATENCY = "latency"
    HANG = "hang"
    HTTP_STATUS = "http_status"
    AUTH = "auth"
    CONNECTION_RESET = "connection_reset"
    MALFORMED_BODY = "malformed_body"
    TOOL_ERROR = "tool_error"
    SESSION_EXPIRED = "session_expired"
    SCHEMA_DRIFT = "schema_drift"
    EMPTY_RESULT = "empty_result"
    PARTIAL_RESULT = "partial_result"
    TRUNCATE_TEXT = "truncate_text"
    REPLACE_CONTENT = "replace_content"
    OVERSIZE = "oversize"
    URL_MISMATCH = "url_mismatch"
    DOWN = "down"
    FLAKY = "flaky"
    STOP_REASON = "stop_reason"
    SCHEMA_VIOLATION = "schema_violation"
    OFFLINE = "offline"
    RAISE_IN_STAGE = "raise_in_stage"
    SIGINT_IN_STAGE = "sigint_in_stage"
    CLOCK_JUMP = "clock_jump"


class FaultSpec(BaseModel):
    """``{type: ..., <type-specific params>}``; params kept loose (``seconds``, ``status``,
    ``retry_after``, ``p``, ``inner``, ``value``, ``truncate_at_fraction``, ``fixture``, ...)."""

    model_config = ConfigDict(extra="allow")

    type: FaultType


class FaultMatch(BaseModel):
    """All keys optional, combined with AND."""

    model_config = ConfigDict(extra="forbid")

    server: str | None = None          # glob
    tool: str | None = None            # glob
    call_index: int | None = None      # per server, 0-based
    nth: list[int] | None = None       # per tool, 0-based list
    stage: str | None = None
    attempt: int | None = None
    after_seconds: float | None = None
    args_regex: str | None = None


class FaultRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match: FaultMatch = Field(default_factory=FaultMatch)
    fault: FaultSpec


class FaultSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    seed: int = 0
    clock: Literal["virtual", "real"] = "virtual"
    time_scale: float = 1.0
    mcp: list[FaultRule] = Field(default_factory=list)
    llm: list[FaultRule] = Field(default_factory=list)
    network: list[FaultSpec] = Field(default_factory=list)
    process: list[FaultSpec] = Field(default_factory=list)
    sha256: str | None = Field(default=None, description="hash of the source file, set by the loader")

    def manifest_entry(self) -> dict[str, Any]:
        return {"profile": self.id, "schedule_sha256": self.sha256}


def load_fault_schedule(path: str | Path) -> FaultSchedule:
    p = Path(path)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        sched = FaultSchedule.model_validate(data)
    except FileNotFoundError as exc:
        raise ConfigError(f"fault schedule not found: {p}") from exc
    except (yaml.YAMLError, ValidationError) as exc:
        raise ConfigError(f"invalid fault schedule {p}: {exc}") from exc
    return sched.model_copy(update={"sha256": sha256_file(p)})
