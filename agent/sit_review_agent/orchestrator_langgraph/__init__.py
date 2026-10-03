"""The LangGraph variant of the orchestrator, selected by ``--orchestrator langgraph``.

:func:`run_review` and :func:`resume_run` are the product's own entry points
(:mod:`sit_review_agent.orchestrator`) run with :class:`LangGraphOrchestrator` in the place of
``Orchestrator``: the run directory, gateways, manifest, preflight, warm-up, failure records and
exit codes are the same code. ``orchestrator.py`` exposes no orchestrator-class seam (its
``_run_execute`` names the class), so the swap is made on the module for the duration of one call
(:func:`using_langgraph`); that is the one coupling the variant has to the product, and it is
recorded as an awkwardness in ``docs/COMPARISON_LANGGRAPH.md``.

Needs the optional extra ``pip install -e '.[langgraph]'`` (``langgraph==1.2.12`` as measured);
importing this package without it raises :class:`ImportError` naming the extra.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

try:
    import langgraph  # noqa: F401
except ImportError as exc:  # pragma: no cover - the extra is installed in the dev venv
    raise ImportError("the LangGraph orchestrator variant needs `pip install -e '.[langgraph]'`") from exc

from sit_review_agent.orchestrator_langgraph.graph import LangGraphOrchestrator

ORCHESTRATORS = ("custom", "langgraph")


@contextlib.contextmanager
def using_langgraph() -> Iterator[None]:
    """Run the product's entry points with the LangGraph orchestrator for the duration."""
    import sit_review_agent.orchestrator as mod

    previous = mod.Orchestrator
    mod.Orchestrator = LangGraphOrchestrator  # type: ignore[misc]
    try:
        yield
    finally:
        mod.Orchestrator = previous  # type: ignore[misc]


async def run_review(request: Any, **hooks: Any) -> Any:
    """``orchestrator.run_review`` through the LangGraph variant (same signature and hooks)."""
    from sit_review_agent.orchestrator import run_review as _run

    with using_langgraph():
        return await _run(request, **hooks)


async def resume_run(run_dir: Path, config: Any, **hooks: Any) -> Any:
    """``orchestrator.resume_run`` through the LangGraph variant (same signature and hooks)."""
    from sit_review_agent.orchestrator import resume_run as _resume

    with using_langgraph():
        return await _resume(run_dir, config, **hooks)


__all__ = ["ORCHESTRATORS", "LangGraphOrchestrator", "resume_run", "run_review", "using_langgraph"]
