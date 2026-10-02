# Research index

Each subfolder is a self-contained, reusable research note with its own README.

- `frameworks/` — agent framework selection and multi-level justification
- `models/` — LLM selection for the agent and for the grader (kept separate to limit self-preference bias)
- `kaggle/` — Kaggle competitions and datasets that can serve as external benchmarks or training signal
- `methodology/` — what "research-grade" evaluation means for this task: metrics, splits, baselines, ablations, leakage controls
- `grading/` — the "lecturer" grader: rubric, protocol, and how it maps to the SIT lab success criteria
- `robustness/` — every scenario and event the agent must be stress-tested against, including tool failure and overfitting checks
- `audit/` — loophole audits of the above
