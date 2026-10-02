# Config profiles

A profile is a named overlay selected with `--profile <name>` (recorded in the run manifest's CLI
arguments, so `resume` reproduces it). It may contain only `agent:` and `stop_rules:` sections, which
are deep-merged over `config/agent.yaml` and `config/stop_rules.yaml` before validation. Pinned line
numbers in those files (runbook §4) are unaffected.

`stop_rules.stage_limits_s` (stage 1, refine and verdict end seconds on the run clock) are absolute
seconds, not a fraction of the deadline: a profile that changes `deadline_seconds` sets its own three
values, and a profile without the block inherits the base file's. A renamed key (`assess_reserve_seconds`,
now `refine_reserve_seconds`) is refused with the new name in the message, in a profile as in the base file.
