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
    # shortlist_bounded = metrics.md §2.3 / prereg matcher.candidates as amended 2026-10-02 (USER_DECISIONS #10);
    # union = the earlier overlap-union-shortlist rule, a DEVIATION kept for comparison
    candidate_rule: Literal["shortlist_bounded", "union"] = "shortlist_bounded"
    call_granularity: Literal["pairwise", "per_flaw_batch"] = "pairwise"
    samples: int = Field(3, ge=1)
    shortlist_k: int = Field(3, ge=0)
    severity_epsilon: float = 0.01
    embedding_prefilter: bool = False
    adaptive_third_sample: bool = True   # owner decision 2026-10-02 (USER_DECISIONS #15); same median of 3


class GroundingCfg(_M):
    theta_q: float = 0.90
    judges: bool = True
    recommendation_judge: bool = False


class RunCfg(_M):
    concurrency: int = Field(4, ge=1)
    seed: int = 20261002
    max_cost_usd: float | None = None


#: Mean USD per call by call kind, claude-opus-5-5 at effort high through `claude -p`. shortlist, batch and
#: adjudicate are measured (pilot judge_calls.jsonl, 2026-10-02); the others are estimates (see eval.yaml).
PER_KIND_USD_DEFAULT = {"shortlist": 0.11, "pair": 0.03, "batch": 0.06, "adjudicate": 0.33, "premise": 0.33,
                        "citation": 0.03, "recommendation": 0.03}


class CostEstimateCfg(_M):
    per_call_usd: dict[str, float] = Field(default_factory=lambda: {"low": 0.03, "typical": 0.11, "high": 0.33})
    per_kind_usd: dict[str, float] | None = Field(default_factory=lambda: dict(PER_KIND_USD_DEFAULT))
    per_call_s: dict[str, float] = Field(default_factory=lambda: {"low": 5.0, "high": 20.0})
    basis_model: str = "claude-opus-5-5"   # the model the per-call prices are meant for


class StatisticsCfg(_M):
    bootstrap_b: int = 10000
    seed: int = 0
    paired_seed: int = 1


class GraderCfg(_M):
    # A grader call carries the whole review and design (about 64k-89k input tokens and up to ~22k output
    # tokens on Opus at high effort), so it needs a larger per-call cap than a matcher call. The first live
    # Pass A on the 21-finding payments review stopped at the $1.0 judge default (2026-10-02).
    max_budget_usd_per_call: float = Field(default=4.0, gt=0)


class EvalConfig(_M):
    judge: JudgeCfg = Field(default_factory=JudgeCfg)
    grader: GraderCfg = Field(default_factory=GraderCfg)
    matcher: MatcherCfg = Field(default_factory=MatcherCfg)
    grounding: GroundingCfg = Field(default_factory=GroundingCfg)
    run: RunCfg = Field(default_factory=RunCfg)
    cost_estimate: CostEstimateCfg = Field(default_factory=CostEstimateCfg)
    statistics: StatisticsCfg = Field(default_factory=StatisticsCfg)


def load_eval_config(path: str | Path | None = None) -> EvalConfig:
    p = Path(path) if path is not None else eval_config_path()
    data: Any = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    return EvalConfig.model_validate(data or {})
