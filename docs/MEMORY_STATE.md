# Memory and state management

This file answers lab §5.3 "memory and state management approach" and the "memory configuration" deliverable of lab §5.1.
The agent's memory is the run directory: everything a run knows is written there as it happens, so a run can be resumed after a crash, explained finding by finding, and replayed offline.
There is deliberately no memory that carries learning from one run to the next; the only link between runs is re-assessing an updated document against the frozen review of its previous version.
The architecture text is `docs/ARCHITECTURE.md` §7 (state, checkpoints, resume and replay) and §11 (what is not built); `docs/DECISIONS.md` ADR-009 records the checkpoint design.

## Where each part lives

| Part | Where it is implemented |
|---|---|
| The run directory and its files | `agent/sit_review_agent/rundir.py` |
| The serialisable run state that a checkpoint holds | `agent/sit_review_agent/state/run_state.py` |
| Checkpoints after every ended phase, pinned to the config, prompt and text hashes | `agent/sit_review_agent/state/checkpoint.py` |
| The evidence ledger, an append-only journal with a snapshot | `agent/sit_review_agent/state/evidence_ledger.py` |
| The registry of the document's approved decisions, frozen and hashed after understand | `agent/sit_review_agent/state/decision_registry.py` |
| The manifest, written before the first call and finalised at exit | `agent/sit_review_agent/manifest.py` |
| Resume from the last checkpoint, and replay of a recorded run | `agent/sit_review_agent/orchestrator.py` `resume_run`, `agent/sit_review_agent/replay.py` |
| Re-assessment against a previous run (`--previous`), run live once in `docs/live_runs/reassess_payments_v2_1/` | `agent/sit_review_agent/orchestrator.py` `RunRequest.previous_run` |

## The settings that configure it

| Setting | What it controls |
|---|---|
| `config/agent.yaml` `run_root` | Where run directories are written (`runs/`, ignored by git) |
| `config/agent.yaml` `transport`, `replay`, `record` | Whether tool calls are live, recorded to cassettes, or served from them, and how strictly |
| `sit-review review --run-id`, `--resume`, `--accept-drift`, `--previous` | The run's name, continuing a run, accepting recorded hash drift, and the frozen previous review |

Checkpoint frequency and the files a run keeps are fixed in code, not configurable.
