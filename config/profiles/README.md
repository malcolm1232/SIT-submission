# Config profiles

A profile is a named overlay selected with `--profile <name>` (recorded in the run manifest's CLI
arguments, so `resume` reproduces it). It may contain only `agent:` and `stop_rules:` sections, which
are deep-merged over `config/agent.yaml` and `config/stop_rules.yaml` before validation. Pinned line
numbers in those files (runbook §4) are unaffected.
