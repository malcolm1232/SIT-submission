# `sit_eval`: the evaluation harness

Scores one agent Review against one canonical answer key, then aggregates many scores. Definitions come
from `research/methodology/metrics.md` (MM) and `eval/prereg.yaml`; data shapes from `spec/`. The lecturer
grader lives in `sit_eval/grader/` (separate workstream) and is mounted as `sit-eval grade`.

The agent never imports this package (`tests/eval_harness/test_eval_isolation.py` walks the agent's AST).

## Commands

```bash
# plan only: call count, cost and time range, no model call
sit-eval score docs/live_runs/live_cc_opus_payments_v1 \
  --key eval/synthetic/payments_orchestration/answer_key.canonical.json --dry-run

# live scoring (default judge: headless `claude -p`, Opus, effort high), with a hard cost stop
sit-eval score docs/live_runs/live_cc_opus_payments_v1 \
  --key eval/synthetic/payments_orchestration/answer_key.canonical.json \
  --out runs/eval/live_cc_opus_payments_v1 --max-cost-usd 60

# cheaper variants
#   --no-grounding-judges          skip the G3 premise and citation-support judges (those metrics become null)
#   --granularity per_flaw_batch   one call per flaw and sample (DEVIATION from prereg; owner approval needed)
#   --judge fake                   deterministic offline plumbing (numbers are hashes, never a score)

sit-eval aggregate runs/eval/*/scores.json --compare FULL --compare B0 --out runs/eval/aggregate.json
sit-eval prompts                 # check prompts/PROMPTS.lock; exit 1 on drift
sit-eval prompts --write-lock    # after an intended prompt edit (before the prereg freeze only)
```

`score` writes `scores.json` (schema: `sit_eval/schemas/scores.schema.json`), `scores.md`, the per-attempt
call log `judge_calls.jsonl` (live judges; hashes of prompts, never their text) and the result cache
`judge_results.jsonl`. Re-running into the same `--out` re-pays nothing that already succeeded, so a run
stopped by `--max-cost-usd` (exit 3, `status: stopped_budget`) can be resumed with a higher limit.

Defaults live in `config/eval.yaml`; flags override them for one run.

## Pipeline (one review, one key)

1. **Load.** Review validated by `sit_review_agent.models.Review` and `spec/finding.schema.json`; key by
   `spec/answer_key.schema.json`. Document text: the agent's own `sit_review_agent.ingest.ingest` on the PDF
   (or the run's `text/*.pages.txt`); its SHA-256 is compared with the Review's `sha256_text`.
2. **Match** (MM §2, `sit_eval/matcher.py`). Candidates = location overlap (sections, ancestor sections and
   requirement/decision IDs) plus a listwise LLM shortlist of up to 3 per flaw. Pairwise 0-3 scores,
   3 samples, median. Hungarian assignment (`hungarian.py`, pure Python) on score + 0.01 x primary weight.
   Strict (3) and lenient (>= 2) results. Credit rule per flaw (`substance | all_of | any_of`).
3. **Adjudicate** unmatched findings into the six classes (deterministic DUPLICATE when a finding scores
   >= 2 against a flaw matched to another finding; LLM otherwise; still-valid observations pre-adjudicate
   VALID_UNPLANTED). A human-review queue (100 % VALID_UNPLANTED and HALLUCINATED, 20 % of the rest) is listed.
4. **Ground** (MM §5): G1 quote existence, G2 the agent's `verify_anchor`, G3 premise judge, citation
   provenance from the ledger and a citation-support judge.
5. **Metrics** (MM §3-§10) with `{value, reason, status}`; `value: null` always carries the reason.
6. **Statistics** (`stats.py`, `aggregate.py`): macro over documents, two-level cluster bootstrap, paired
   differences, exact document-level sign-flip test, stratified flaw-level permutation, McNemar, Holm, BH.

Blinding: prompts carry no run id, review id, model, condition, provenance, confidence or labels; findings
are shuffled per listwise call with a seed derived from `--seed` and recorded in `scores.json`.

## Freeze and locks

- `eval/prereg.yaml` `frozen: false` today: every score is labelled **UNFROZEN PILOT** and the CLI warns.
  Once `frozen: true`, `score` refuses to run unless `sha256(eval/prereg.yaml)` equals the hash in
  `eval/prereg.lock`, the prompts match `PROMPTS.lock`, and (if set) `matcher.prompt_sha256` equals the
  prompt bundle hash.
- `sit_eval/prompts/PROMPTS.lock`: SHA-256 of every judge prompt and judge output schema plus a bundle hash;
  the bundle hash is the value for prereg `matcher.prompt_sha256`.

## Cost of scoring one review (first live run: 20 findings, 14 v1 flaws, 80 overlap pairs)

| Mode | Judge calls | Cost at $0.05-0.15 per call | Wall time at concurrency 4 |
|---|---|---|---|
| pairwise (prereg), grounding judges on | 300-440 | $15-66 (about $37 typical) | 25-110 min |
| pairwise, `--no-grounding-judges` | 260-400 | $13-60 | 22-100 min |
| per_flaw_batch (deviation), judges on | 102-116 | $5-17 | 9-29 min |
| per_flaw_batch, `--no-grounding-judges` | 62-76 | $3-11 | 5-19 min |
| pairwise, `--adaptive-samples` (same medians; needs owner approval) | 220-440 | $11-66 | |
| per_flaw_batch, `--adaptive-samples` | 88-116 | $4-17 | |

Ranges come from `--dry-run`; the shortlist decides where in the range a run lands. The per-call prices
are unverified planning figures for Opus at effort high (see the `caveats` in the dry-run output): retries
are not counted, document-carrying calls cost more than pair calls, and thinking tokens dominate cost.
`--adaptive-samples` asks the third pairwise sample only when the first two disagree or one failed; the
median of three is then unchanged, so results are identical (verifier E1, 2026-10-02).

Live clients built by `build_judge` without options (the grader) take their timeout, retries and per-call
`--max-budget-usd` from `config/eval.yaml` `judge`. `ClaudeCodeJudge` and `AnthropicJudge` drop a root
`$schema` key before sending a schema. A call's reported cost includes its failed attempts; attempts with
unknown cost (timeouts) are charged one reserve each by the cost stop. `sit-eval score` still works if the
grader package fails to import (`grade` then reports the import error).

## Known gaps and choices (also in the workstream report)

- No embedding prefilter (prereg: optional, only if an embedding model is recorded at freeze).
- Message Batches is not used: `AnthropicJudge` makes synchronous streamed calls.
- `AnthropicJudge` reports cost only when given a price table (`price_per_mtok`); otherwise the cost stop
  charges each call its reserve.
- G1/G2 reuse the agent's normaliser and `verify_anchor`: character-level partial ratio (MM says
  token-level), exact match first, a section that cannot be resolved falls back to the page window.
  Doc-evidence quotes shorter than 8 tokens are allowed but must match exactly.
- A strict-unmatched finding whose best score is PARTIAL (2) against a flaw nobody matched goes to the
  LLM adjudicator like any unmatched finding (MM §13 pseudo-code); the flaw is recorded as
  `partial_key_flaw_id`. Primary P_a counts VALID_UNPLANTED only; the exploratory
  `precision_adjudicated_partial_credit` also credits such partial findings (unless DUPLICATE or
  HALLUCINATED). MM does not define this case (verifier E1, 2026-10-02).
- The result cache (`judge_results.jsonl`) is keyed by the client namespace too (`claude_code`,
  `anthropic_api`, `FakeJudge`), so fake answers are never reused by a live run in the same `--out`.
- Ties between findings for one flaw go to the agent's higher-ranked finding (a < 1e-4 weight term).
- Medians use the lower median when a failed sample leaves an even count.
- RJR_subst needs the optional recommendation judge; citation recall covers finding claims only (no claim
  splitter); copy-through needs `--prior-scores`; false_resolution_rate is a prereg proposed addition and
  stays null.
