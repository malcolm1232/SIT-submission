"""SIT design-review agent.

A custom, explicit state machine (``ingest -> understand -> plan -> research -> assess -> refine ->
verify -> report``) on the official Anthropic SDK with a direct MCP client (docs/DECISIONS.md
ADR-001). The output contract is ``spec/finding.schema.json`` (Finding, Review); see
``agent/README.md`` for the module map and the interface-freeze rule.
"""

__version__ = "0.1.0"

#: Version of spec/finding.schema.json and spec/taxonomy.yaml this package implements.
SCHEMA_VERSION = "1.0"
TAXONOMY_VERSION = "1.0"

#: The only model the agent calls (ADR-002). The value actually used comes from config/agent.yaml.
DEFAULT_MODEL = "claude-opus-5-5"
