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

# variants
#   --candidate-rule union         overlap union shortlist, the pre-2026-10-02 rule (DEVIATION; comparison only)
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
2. **Match** (MM §2, `sit_eval/matcher.py`). Candidates: **the shortlist bounds pairwise scoring**
   (`matcher.candidate_rule: shortlist_bounded`, the default; owner decision 2026-10-02,
   `docs/USER_DECISIONS.md` #10). One listwise shortlist call per flaw sees every finding (shuffled with a
   recorded seed) and returns up to `shortlist_k` (3) ids; only those pairs are scored. Location overlap
   (sections, ancestor or descendant sections, requirement/decision IDs) is a hint: the shortlist prompt
   names the overlapping findings in a `<location_hint>` block and asks the model to look at them first,
   but overlap adds no pair by itself. Location compatibility still governs the score (a 3 with
   `location_ok: false` is capped at 2). If a shortlist call still fails after retries, that flaw has no
   candidates and counts as unmatched; the failure is listed in `failures`, the flaw row has
   `shortlist_ok: false`, the recall metrics carry `shortlist_failed_flaws` and a lower-bound note, and a
   warning says so. It never falls back to the overlap set; re-running into the same `--out` retries only
   the failed calls. `matching.shortlist.<flaw>` records the hint (`overlap_hint_ids`) and the provenance
   (`shortlisted_with_overlap`, `shortlisted_without_overlap`, `overlap_not_shortlisted`); a candidate's
   `sources` is `["overlap", "shortlist"]` or `["shortlist"]`. `--candidate-rule union` restores the
   earlier rule (overlap union shortlist, sources may be `["overlap"]` alone) for comparison; it uses the
   same shortlist prompt, so a union run into the same `--out` reuses the shortlist and pair answers and
   pays only for the overlap-only pairs. Pairwise 0-3 scores, 3 samples, median. Hungarian assignment (`hungarian.py`, pure Python) on score + 0.01 x primary weight.
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

## Cost of scoring one review (first live run: 20 findings, 14 v1 flaws, 80 location-overlap pairs)

| Mode | Judge calls | Cost (per-kind prices below) | Wall time at concurrency 4 |
|---|---|---|---|
| pairwise, shortlist_bounded (prereg), grounding judges on | 60-200 | $10.72-19.12 | 5-50 min |
| pairwise, shortlist_bounded, `--no-grounding-judges` | 20-160 | $3.52-11.92 | 2-40 min |
| per_flaw_batch (deviation), shortlist_bounded, judges on | 60-116 | $10.72-17.86 | 5-29 min |
| per_flaw_batch, shortlist_bounded, `--no-grounding-judges` | 20-76 | $3.52-10.66 | 2-19 min |
| pairwise, `--candidate-rule union` (deviation), judges on | 300-440 | $17.92-26.32 | 25-110 min |
| pairwise, `--candidate-rule union`, `--no-grounding-judges` | 260-400 | $10.72-19.12 | 22-100 min |

Ranges come from `--dry-run`. Under shortlist_bounded the shortlist decides how many findings per flaw
are scored (0 to 3; the 2026-10-02 pilot shortlist returned 2.0 per flaw), so pair scoring lands between
0 and 126 calls; adjudication lands between N - G and N calls. The dry run prices each call kind
separately (`config/eval.yaml` `cost_estimate.per_kind_usd`, Opus 5.5 at effort high through `claude -p`):
shortlist $0.11, per-flaw batch $0.06 and adjudication $0.33 (whole document) are means measured on the
pilot (`docs/live_runs/live_cc_opus_payments_v1/eval_pilot/judge_calls.jsonl`, 57 calls); a single pair
call ($0.03, from batch cost against candidate count), the premise judge ($0.33, whole document) and the
citation judge ($0.03) were not in the pilot and are estimates. Whole-document calls (adjudication,
premise) now dominate the cost of a run. Retries are not counted. `--adaptive-samples` asks the third
pairwise sample only when the first two disagree or one failed; the median of three is then unchanged, so
results are identical (verifier E1, 2026-10-02); it lowers the floor of pair scoring only.

Live clients built by `build_judge` without options (the grader) take their timeout, retries and per-call
`--max-budget-usd` from `config/eval.yaml` `judge`. `ClaudeCodeJudge` and `AnthropicJudge` drop a root
`$schema` key before sending a schema. A call's reported cost includes its failed attempts; attempts with
unknown cost (timeouts) are charged one reserve each by the cost stop. `sit-eval score` still works if the
grader package fails to import (`grade` then reports the import error).

## Known gaps and choices (also in the workstream report)

- Under shortlist_bounded the shortlist is the only way into scoring: a true match it leaves out scores 0
  and lowers recall. `matching.shortlist.<flaw>.overlap_not_shortlisted` lists the overlapping findings
  that were not scored, which is where to look for such misses; a match at a non-overlapping location
  that the shortlist misses leaves no trace. The deterministic DUPLICATE rule also needs the duplicate to
  be shortlisted; otherwise the duplicate goes to the LLM adjudicator, which can still call it DUPLICATE.

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
