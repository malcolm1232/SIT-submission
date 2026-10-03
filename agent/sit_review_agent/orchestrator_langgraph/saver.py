"""LangGraph's checkpointer for the variant, mapped onto the run directory.

LangGraph checkpoints its own graph state (the control channels of :mod:`graph`) through a
``BaseCheckpointSaver``. The repo's checkpoints (``checkpoints/<nn>-<phase>.json``, ADR-009) hold the
run state and are what ``resume`` reads; the graph state holds only which stage 1 members ended, so
it is not enough to resume from. This saver keeps LangGraph's checkpoints in memory for the run (the
``InMemorySaver`` the framework ships) and mirrors each one as a line of
``<run>/langgraph/graph_checkpoints.jsonl`` (thread, step, checkpoint ID, the control channels and
the framework's metadata), so a reader of the run directory can see what the framework knew at each
superstep beside what the repo's checkpoints knew. Nothing reads the mirror back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import ChannelVersions, Checkpoint, CheckpointMetadata
from langgraph.checkpoint.memory import InMemorySaver

#: Run-directory folder of everything the variant writes beside the product's files.
LANGGRAPH_DIR = "langgraph"
#: The mirror of the framework's checkpoints (one JSON object per superstep).
GRAPH_CHECKPOINTS = "graph_checkpoints.jsonl"
#: The control channels mirrored (the framework's own bookkeeping channels are left out).
CONTROL_CHANNELS = ("ended", "shards", "stop")


class RunDirSaver(InMemorySaver):
    """``InMemorySaver`` that also appends each checkpoint to the run directory's mirror file."""

    def __init__(self, run_root: Path) -> None:
        super().__init__()
        self.path = Path(run_root) / LANGGRAPH_DIR / GRAPH_CHECKPOINTS
        self.mirrored = 0

    def put(self, config: dict[str, Any], checkpoint: Checkpoint, metadata: CheckpointMetadata,
            new_versions: ChannelVersions) -> dict[str, Any]:
        out = super().put(config, checkpoint, metadata, new_versions)
        self._mirror(config, checkpoint, metadata)
        return out

    async def aput(self, config: dict[str, Any], checkpoint: Checkpoint, metadata: CheckpointMetadata,
                   new_versions: ChannelVersions) -> dict[str, Any]:
        out = await super().aput(config, checkpoint, metadata, new_versions)
        self._mirror(config, checkpoint, metadata)
        return out

    def _mirror(self, config: dict[str, Any], checkpoint: Checkpoint, metadata: CheckpointMetadata) -> None:
        values = checkpoint.get("channel_values") or {}
        record = {
            "thread_id": (config.get("configurable") or {}).get("thread_id"),
            "checkpoint_ns": (config.get("configurable") or {}).get("checkpoint_ns", ""),
            "checkpoint_id": checkpoint.get("id"),
            "ts": checkpoint.get("ts"),
            "step": metadata.get("step"),
            "source": metadata.get("source"),
            "channels": {k: values[k] for k in CONTROL_CHANNELS if k in values},
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self.mirrored += 1
        except OSError:
            pass                                    # the mirror is a reader's aid, never the run's state
