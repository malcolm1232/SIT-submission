# Context management

This file answers lab §5.3 "context management approach".
The design keeps each model call's context small and specific: every call starts from the same document prefix, then sees only the inputs its job needs, and anything taken from outside the document arrives as a numbered ledger entry rather than as loose text.
The architecture text is `docs/ARCHITECTURE.md` §2 (what each stage sees), §4 (the size guard and the hermetic CLI call) and §6 (anchors and ledger IDs); this file is a guide to it, not a second copy.

## What decides what a call sees

| Rule | Where it is implemented |
|---|---|
| Every conversation opens with the same byte-stable prefix: the system prompt, then the canonical page-marked text of the document (and the native PDF block on a backend that accepts it), with nothing volatile in it so it can be cached | `agent/sit_review_agent/llm/prefix.py`, `prompts/system.md` |
| The phase's own brief follows in a separate turn, so the prefix is identical across phases | `agent/sit_review_agent/llm/prefix.py`, `prompts/` |
| An assess shard sees the document and its own criterion group only, which is why it can start before the plan exists | `agent/sit_review_agent/phases/assess.py`, `config/agent.yaml` `assess.shards` |
| Refine sees the merged findings, the frozen decision registry, the plan answers and the ledger, and returns revisions, not the findings again | `agent/sit_review_agent/phases/refine.py` |
| External results reach the model prefixed with their new `EV-nnn` IDs, so it can cite only what it has read, and the model never writes a URL | `agent/sit_review_agent/state/evidence_ledger.py`, `agent/sit_review_agent/tools/sources.py` |
| Each ledger entry is marked as document, external or inference, so document evidence and outside evidence stay apart | `agent/sit_review_agent/state/evidence_ledger.py` |
| A request is estimated against 80 % of the context window before sending and refused if it does not fit | `agent/sit_review_agent/llm/runtime.py` `ContextGuard` |
| A CLI call loads none of the user's own settings, hooks or plugins | `config/agent.yaml` `claude_code.extra_args` |

One document fits in one context, so nothing is summarised or compacted during a run.
What the shards cannot see (external evidence) is a recorded limitation (`docs/LIMITATIONS.md`, `docs/USER_DECISIONS.md` #37).
