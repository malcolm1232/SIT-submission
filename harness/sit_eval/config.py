"""Typed loader for ``config/eval.yaml``."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from sit_eval.paths import eval_config_path


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JudgeCfg(_M):
    kind: Literal["claude_code", "anthropic_api", "fake"] = "claude_code"
    model: str = "claude-opus-5-5"
    effort: str = "high"
    max_tokens: int = 16000
    timeout_s: float = 1200.0
    max_retries: int = 3
    backoff_base_s: float = 5.0
    backoff_max_s: float = 120.0
    max_budget_usd_per_call: float | None = 1.0
    inherit_api_key: bool = False
    executable: str = "claude"


class MatcherCfg(_M):
    call_granularity: Literal["pairwise", "per_flaw_batch"] = "pairwise"
    samples: int = Field(3, ge=1)
    shortlist_k: int = Field(3, ge=0)
    severity_epsilon: float = 0.01
    embedding_prefilter: bool = False
    adaptive_third_sample: bool = False


class GroundingCfg(_M):
    theta_q: float = 0.90
    judges: bool = True
    recommendation_judge: bool = False


class RunCfg(_M):
    concurrency: int = Field(4, ge=1)
    seed: int = 20261002
    max_cost_usd: float | None = None


class CostEstimateCfg(_M):
    per_call_usd: dict[str, float] = Field(default_factory=lambda: {"low": 0.05, "typical": 0.10, "high": 0.15})
    per_call_s: dict[str, float] = Field(default_factory=lambda: {"low": 20.0, "high": 60.0})
    basis_model: str = "claude-opus-5-5"   # the model the per-call prices are meant for


class StatisticsCfg(_M):
    bootstrap_b: int = 10000
    seed: int = 0
    paired_seed: int = 1


class EvalConfig(_M):
    judge: JudgeCfg = Field(default_factory=JudgeCfg)
    matcher: MatcherCfg = Field(default_factory=MatcherCfg)
    grounding: GroundingCfg = Field(default_factory=GroundingCfg)
    run: RunCfg = Field(default_factory=RunCfg)
    cost_estimate: CostEstimateCfg = Field(default_factory=CostEstimateCfg)
    statistics: StatisticsCfg = Field(default_factory=StatisticsCfg)


def load_eval_config(path: str | Path | None = None) -> EvalConfig:
    p = Path(path) if path is not None else eval_config_path()
    data: Any = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    return EvalConfig.model_validate(data or {})
