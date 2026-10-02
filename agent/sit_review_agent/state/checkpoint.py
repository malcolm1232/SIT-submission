"""Per-phase on-disk checkpoints (docs/DECISIONS.md ADR-009).

After every completed phase the orchestrator writes ``checkpoints/<nn>-<phase>.json`` atomically.
A checkpoint pins the hashes of the effective config, the prompt bundle and the canonical text,
and the byte offsets of the three journals (``llm.jsonl``, ``tools.jsonl``, ``ledger.jsonl``).

Resume: load the latest checkpoint, refuse on hash drift unless ``accept_drift`` (recorded as a
deviation), truncate ``ledger.jsonl`` to the checkpoint offset (no duplicated ledger IDs), restart
the next phase, and serve tool calls already in ``tools.jsonl`` from there (``SelfReplayGateway``).
Model calls of the interrupted phase are re-issued and logged ``resumed: true``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from sit_review_agent.errors import CheckpointError, ResumeDriftError
from sit_review_agent.rundir import RunDir, write_json_atomic
from sit_review_agent.state.run_state import RunState
from sit_review_agent.states import PHASE_ORDER, PhaseName

CHECKPOINT_VERSION = 1


class PinnedHashes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_config: str
    prompts_bundle: str
    canonical_text: str


class JournalOffsets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_jsonl: int
    tools_jsonl: int
    ledger_jsonl: int


class Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_version: int = CHECKPOINT_VERSION
    run_id: str
    phase: PhaseName
    seq: int                    # 1-based position of the phase in PHASE_ORDER
    created_utc: str
    hashes: PinnedHashes
    offsets: JournalOffsets
    state: RunState


def checkpoint_path(run_dir: RunDir, phase: PhaseName) -> Path:
    seq = PHASE_ORDER.index(phase) + 1
    return run_dir.checkpoints / f"{seq:02d}-{phase.value}.json"


def journal_offsets(run_dir: RunDir) -> JournalOffsets:
    def size(p: Path) -> int:
        return p.stat().st_size if p.exists() else 0

    return JournalOffsets(llm_jsonl=size(run_dir.llm_log), tools_jsonl=size(run_dir.tools_log),
                          ledger_jsonl=size(run_dir.ledger_journal))


def write_checkpoint(run_dir: RunDir, ckpt: Checkpoint) -> Path:
    """Atomic write (temp file, fsync, ``os.replace``); also refreshes ``state.json``."""
    path = checkpoint_path(run_dir, ckpt.phase)
    try:
        data = ckpt.model_dump(mode="json")
        write_json_atomic(path, data)
        write_json_atomic(run_dir.state, data["state"])
    except OSError as exc:
        raise CheckpointError(f"cannot write checkpoint {path}: {exc}") from exc
    return path


def load_checkpoint(path: Path) -> Checkpoint:
    try:
        return Checkpoint.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise CheckpointError(f"cannot read checkpoint {path}: {exc}") from exc


def latest_checkpoint(run_dir: RunDir) -> Checkpoint | None:
    """The checkpoint of the last completed phase, or ``None`` if there is none."""
    files = sorted(run_dir.checkpoints.glob("[0-9][0-9]-*.json")) if run_dir.checkpoints.exists() else []
    return load_checkpoint(files[-1]) if files else None


def check_drift(ckpt: Checkpoint, current: PinnedHashes, *, accept_drift: bool = False) -> list[str]:
    """Differences between the pinned and current hashes. Raises :class:`ResumeDriftError` if any
    and ``accept_drift`` is false; otherwise returns them (to record as manifest deviations)."""
    drift = [f"{name}: {getattr(ckpt.hashes, name)[:12]} -> {getattr(current, name)[:12]}"
             for name in PinnedHashes.model_fields if getattr(ckpt.hashes, name) != getattr(current, name)]
    if drift and not accept_drift:
        raise ResumeDriftError(drift)
    return drift


def truncate_journal(path: Path, offset: int) -> None:
    """Cut an append-only journal back to ``offset`` bytes (entries of an incomplete phase)."""
    if path.exists() and path.stat().st_size > offset:
        with open(path, "r+b") as fh:
            fh.truncate(offset)
            fh.flush()
            os.fsync(fh.fileno())


def next_phase_after(ckpt: Checkpoint) -> PhaseName | None:
    i = PHASE_ORDER.index(ckpt.phase)
    return PHASE_ORDER[i + 1] if i + 1 < len(PHASE_ORDER) else None
