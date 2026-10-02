"""Run manifest assembly (docs/REPRODUCIBILITY.md §8, spec ``RunManifest``; INV-09).

``start_manifest`` writes ``manifest.json`` before the first model call (git commit and dirty
flag, config and prompt hashes, taxonomy hash, requested model, tools, budgets, fault schedule);
``finalise_manifest`` adds served models, usage and cost, timings, outcome and output hashes at
exit. Fields that the spec's ``RunManifest`` lacks go in ``extra`` (:class:`ManifestExtra`).
In eval mode a dirty tree, a stale ``PROMPTS.lock`` or ``served_models != {requested}`` is refused.
"""

from __future__ import annotations

from sit_review_agent.context import RunContext
from sit_review_agent.models import Outcome, RunManifest


def start_manifest(ctx: RunContext) -> RunManifest:
    raise NotImplementedError("phase 3: start_manifest (workstream C)")


def finalise_manifest(ctx: RunContext, outcome: Outcome) -> RunManifest:
    raise NotImplementedError("phase 3: finalise_manifest (workstream C)")
