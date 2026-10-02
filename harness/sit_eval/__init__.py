"""``sit_eval``: the evaluation harness (matcher, metrics, lecturer grader).

Separate from ``sit_review_agent`` on purpose: this package reads answer keys, the agent must
never import it (tests/eval_harness enforce the isolation). Driven by ``spec/`` and
``eval/prereg.yaml``; definitions from ``research/methodology/metrics.md`` and
``research/grading/grader_prompt.md``.
"""
