"""``sit-review selftest`` and ``sit-review preflight``.

selftest: runs the full pipeline offline on the built-in fixture in
``sit_review_agent/fixtures/selftest/`` (an invented "campus room-booking" design, prompt-safe:
``design.pages.txt``; tool cassettes under ``cassettes/``; a scripted :class:`FakeGateway`
response per phase to be added as ``script.json``) with ``transport=replay`` (strict), then runs
:func:`sit_review_agent.invariants.check_all` on the produced Review and run directory. No key and
no network are needed (ADR-008). ``make smoke`` wraps it (runbook §1, ≤ 60 s).

preflight: keys present (by name only), ``models.retrieve`` + 1-token call, each enabled MCP
server initialised and listed (with ``--warm``: in parallel with a 150 s cold-start allowance,
then pinged every ``--keep-warm`` seconds), fallback run directories present (runbook §2-§3).
"""

from __future__ import annotations

from pathlib import Path

from sit_review_agent.config import EffectiveConfig
from sit_review_agent.invariants import InvariantResult

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "selftest"


async def run_selftest(workdir: Path | None = None) -> list[InvariantResult]:
    """Run the offline pipeline in ``workdir`` (default: a temp dir) and return INV-03..INV-10."""
    raise NotImplementedError("phase 3: run_selftest (workstream C)")


async def run_preflight(config: EffectiveConfig, *, warm: bool = False, keep_warm_s: int | None = None) -> bool:
    """Print the preflight status table; return True if every dependency is green or its
    degraded mode is named."""
    raise NotImplementedError("phase 2: run_preflight (workstream B)")
