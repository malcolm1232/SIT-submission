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

# live scoring (default judge: headless `claude -p`, Opus, effort high), with a hard cost stop; the S-dev
# keys are not signed off yet (scored_run_ready false), so LC12 refuses them without --exploratory
sit-eval score docs/live_runs/live_cc_opus_payments_v1 \
  --key eval/synthetic/payments_orchestration/answer_key.canonical.json \
  --out runs/eval/live_cc_opus_payments_v1 --max-cost-usd 60 --exploratory

# variants
#   --candidate-rule union         overlap union shortlist, the pre-2026-10-02 rule (DEVIATION; comparison only)
#   --no-grounding-judges          skip the G3 premise and citation-support judges (those metrics become null)
#   --granularity per_flaw_batch   one call per flaw and sample (DEVIATION from prereg; owner approval needed)
#   --judge fake                   deterministic offline plumbing (numbers are hashes, never a score)
#   --exploratory                  LC12 override for a key that is not signed off; every artefact says exploratory

# refuses exploratory scores (alone or mixed with confirmatory ones) unless given --exploratory too
sit-eval aggregate runs/eval/*/scores.json --compare FULL --compare B0 --out runs/eval/aggregate.json
# key-blind grade plus the key-aware diagnostic; the diagnostic reads the key, so LC12 applies as for score
sit-eval grade run docs/live_runs/live_cc_opus_payments_v1/report.json \
  --pdf eval/synthetic/payments_orchestration/design_v1.pdf \
  --answer-key eval/synthetic/payments_orchestration/answer_key.canonical.json --judge claude_code --exploratory
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
   pays only for the overlap-only pairs. Pairwise 0-3 scores, 3 samples, median (the third sample only
   when the first two disagree or one failed; owner decision #15). Hungarian assignment (`hungarian.py`,
   pure Python) on score + 0.01 x primary weight.
   Strict (3) and lenient (>= 2) results. Credit rule per flaw (`substance | all_of | any_of`).
3. **Adjudicate** unmatched findings: deterministic DUPLICATE when a finding scores >= 2 against a flaw
   matched to another finding; else (strict) deterministic PARTIAL_KEY_MATCH when it scores PARTIAL (2)
   against a flaw nobody matched (UD #14); otherwise the LLM gives one of the six classes, and a
   still-valid observation match is VALID_UNPLANTED. Both deterministic labels use scored pairs only. A human-review queue (100 % VALID_UNPLANTED and HALLUCINATED, 20 % of the rest) is listed.
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

## LC12: signed keys only (`sit_eval/lc12.py`)

Prereg LC12 says every key used for scoring has `scored_run_ready: true`, which only the owner's sign-off sets (`eval/KEY_SIGNOFF.md` section 4).
Since SIT FABLE ruling #26 (`docs/USER_DECISIONS.md`, 2026-10-03) the harness enforces it instead of warning.
`sit-eval score`, and `sit-eval grade run` with `--answer-key`, refuse a key that is not signed off with exit 2, before any judge is built, so no call is made and nothing is spent.
The message names the key, the pending sign-off fields and the override.
A legacy YAML grader key carries no sign-off, so it is always refused; the key-blind grade (no `--answer-key`) reads no key and is not affected.
`--exploratory` lets the run proceed, and every artefact it writes says so: `scores.json` and `grade.json` carry `exploratory: true`, `exploratory_note` and `outside_preregistered_analysis`; `scores.md` and `grade.md` open with an EXPLORATORY line; the console prints the same line; each row of `judge_results.jsonl` records `exploratory`.
The flag marks the run even on a signed key.
With `eval/prereg.yaml` frozen, an `--exploratory` run also says that it is outside the pre-registered analysis; it can never be a confirmatory run.
A confirmatory run reuses only cache rows marked `"exploratory": false`, so answers from an exploratory run, or from a cache written before this guard (such as the pilots'), are paid for again and never served as confirmatory; the number of rows not reused is in the warnings.
`sit-eval aggregate` treats a `scores.json` as exploratory when it says so, or when it predates the guard and its key was not signed off; it refuses such inputs, alone or mixed with confirmatory ones, unless it is given `--exploratory`, and then its output carries the same marker.
`--dry-run` still plans the calls and adds an `lc12` note saying that a real run would refuse.
`score_review` and `grade_review` apply the same rule when called as a library.

## Cost and tokens of the run under test: unknown usage is not zero (`sit_eval/usage.py`)

The `efficiency` metric (MM §10) reads the agent run's `usage.cost_usd` and token counts from its manifest.
Since 2026-10-03 the runtime logs a model call that was killed or cut (run deadline, timeout, a crashed `claude -p`, a dropped stream, an interrupt) with `usage: null`, lists it in `extra.model.calls_with_unrecorded_usage` and sets `extra.model.cost_usd_lower_bound`; `usage.cost_usd` then sums the recorded calls only.
SIT FABLE ruling #28 (`docs/USER_DECISIONS.md`) makes the harness honest about such runs.
Completeness is read in this order: the manifest field when present (`complete` when the list is empty, else `unrecorded`); for a manifest that predates the field, the runtime's rule applied by the harness to the `llm.jsonl` beside `report.json` (a deadline cut or timeout logged with zero usage, no cost and no HTTP status; unsent, fault, replayed and fake entries spend nothing), read by code only and named in `usage_source` and a warning; with neither, `unknown`.
The rule lives once in `sit_eval/usage.py` and `tests/eval_harness/test_eval_usage_completeness.py` pins it to the runtime's behaviour with the demo run's `llm-0003` entry as the legacy fixture.
`tests/eval_harness/test_eval_usage_verifier.py` runs the same entries through this copy and the runtime's `unrecorded_reason`, and the demo run's real `llm.jsonl` through both readers, so a change to either copy fails a test.
A fully accounted run is unchanged except for the new fields `usage_completeness: complete`, `usage_reason: null`, `usage_source` and `calls_with_unrecorded_usage: []`.
Any other run has `cost_usd`, `input_tokens`, `output_tokens` and `cached_tokens` null with `usage_reason` `unrecorded_usage` (the `usage_note` names the count and each call) or `usage_completeness_unknown`, and the recorded figures beside them as `cost_usd_lower_bound`, `input_tokens_lower_bound`, `output_tokens_lower_bound` and `cached_tokens_lower_bound`; `scores.schema.json` refuses a cost figure on such a run.
`scores.md` opens the efficiency section with a LOWER BOUND or COMPLETENESS UNKNOWN line, the `score` console prints a `cost` entry with the completeness and a line on stderr, and `scores.json` carries a warning.
`sit-eval aggregate` reports per condition `cost_usd`, `input_tokens` and `output_tokens` as `median_fully_accounted` and `iqr_fully_accounted` over fully accounted runs, `excluded_unrecorded` and `excluded_unknown` (count and share), and `median_lower_bound_all_runs` over every run at its lower bound (a run that reports no figure counts at 0, shown in `runs_without_a_figure_counted_at_zero`); no figure mixes the two.
`runs_with_unrecorded_usage` is the intention-to-treat share of runs with any cut call; `runs_with_unknown_usage_completeness` stands beside it.
A `scores.json` written before the ruling (cost present, no completeness) aggregates as unknown.
The top-level `pilot_checkpoint` is the prereg `stop_rule.pilot_checkpoint` on the FULL runs against `costs.per_run_usd.heavy_case_FULL`: `fail` if the lower-bound median over all FULL runs exceeds the threshold, `pass` only if every FULL run is fully accounted and the median is at or below it, else `not_evaluable`; a lower bound can fail the check but never pass it.
`sit-eval aggregate` drops a scores file whose scoring the judge budget stopped before any statistic (`judge_budget_stop`), one it cannot read as JSON (`unreadable`), one that is not a scores object with a schema status, the `inputs` identity fields and a `metrics` object (`schema_invalid`), and one with no statistic (`incomplete`); the check is structural rather than the full schema, so a scores file written before a later schema field still aggregates.
Every dropped file is listed in the top-level `dropped_inputs` with its reason, detail and condition (`null` when it cannot be read), in the warnings, and on stderr.
A dropped run is a run of unknown cost (SIT FABLE ruling #29): when any dropped file is a FULL run, or of unknown condition, `pilot_checkpoint` is `not_evaluable` and its own `dropped_inputs` names those files; a dropped file of another condition is listed but does not affect the checkpoint.
The first live run's manifest predates the field and its `llm.jsonl` is not in the repository, so its $3.68 is reported as a lower bound of unknown completeness.

## Cost of scoring one review (first live run: 20 findings, 14 v1 flaws, 80 location-overlap pairs)

| Mode | Judge calls | Cost (per-kind prices below) | Wall time at concurrency 4 |
|---|---|---|---|
| pairwise, shortlist_bounded (prereg), grounding judges on | 74-200 | $9.94-19.12 | 2-17 min |
| pairwise, shortlist_bounded, `--no-grounding-judges` | 34-160 | $2.74-11.92 | 1-13 min |
| per_flaw_batch (deviation), shortlist_bounded, judges on | 68-116 | $9.58-17.86 | 1-10 min |
| per_flaw_batch, shortlist_bounded, `--no-grounding-judges` | 28-76 | $2.38-10.66 | 1-6 min |
| pairwise, `--candidate-rule union` (deviation), judges on | 214-440 | $13.54-26.32 | 5-37 min |
| pairwise, `--candidate-rule union`, `--no-grounding-judges` | 174-400 | $6.34-19.12 | 4-33 min |

Ranges come from `--dry-run` with the default adaptive third sample (`--no-adaptive-samples`: pairwise
shortlist_bounded 74-200 calls, $10.54-19.12; union 294-440, $15.94-26.32). The bounds are true bounds,
not scenarios (verify_matcher_rule, 2026-10-02): a finding with no scored pair always goes to the
adjudicator, and a finding with one can avoid it (matched, deterministic DUPLICATE or deterministic
PARTIAL_KEY_MATCH). So the fewest calls under shortlist_bounded come from empty shortlists (no pair
scored, all 20 findings adjudicated), while the lowest cost comes from giving every finding one scored
pair ($0.06-0.09) instead of an adjudication ($0.33); the two minima are different outcomes. (The first
version reported 60 calls and $10.72, which assumed 0 pair calls and 14 matched flaws at once.) Under
shortlist_bounded the shortlist decides how many findings per flaw are scored (0 to 3; the 2026-10-02
pilot shortlist returned 2.0 per flaw), so pair scoring lands between 0 and 126 calls. The dry run prices each call kind
separately (`config/eval.yaml` `cost_estimate.per_kind_usd`, Opus 5.5 at effort high through `claude -p`):
shortlist $0.11, per-flaw batch $0.06 and adjudication $0.33 (whole document) are means measured on the
pilot (`docs/live_runs/live_cc_opus_payments_v1/eval_pilot/judge_calls.jsonl`, 57 calls); a single pair
call ($0.03, from batch cost against candidate count), the premise judge ($0.33, whole document) and the
citation judge ($0.03) were not in the pilot and are estimates. Whole-document calls (adjudication,
premise) now dominate the cost of a run. Retries are not counted. The adaptive third sample (on by
default, `docs/USER_DECISIONS.md` #15; `--no-adaptive-samples` turns it off for one run) asks the third
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
- G1/G2 reuse the agent's normaliser and `verify_anchor`: character-level partial ratio (MM §5.1 says so
  since 2026-10-02), exact match first, a section that cannot be resolved falls back to the page window.
  The 8-token minimum applies to the agent's `doc_anchors` quotes; doc-evidence quotes shorter than 8
  tokens are allowed but must match exactly.
- A strict-unmatched finding whose best median is PARTIAL (2) against a flaw nobody matched is labelled
  `PARTIAL_KEY_MATCH` by the harness, with the flaw in `partial_key_flaw_id` (owner decision 2026-10-02,
  `docs/USER_DECISIONS.md` #14; MM §2.3 step 4). No adjudicator call. It counts as correct for P_a
  (P_a = (TP + VALID_UNPLANTED + PARTIAL_KEY_MATCH) / N, the flaw must be in the version's gold set),
  is reported as `partial_key_match_count`, is never VALID_UNPLANTED, never enters the pooled key G+, and
  never removes a sound unit (nor counts as a false positive on one). DUPLICATE is checked first. The
  exploratory `precision_adjudicated_partial_credit` of verifier E1 is gone (P_a now covers it).
- The result cache (`judge_results.jsonl`) is keyed by the client namespace too (`claude_code`,
  `anthropic_api`, `FakeJudge`), so fake answers are never reused by a live run in the same `--out`.
- Ties between findings for one flaw go to the agent's higher-ranked finding (a < 1e-4 weight term).
- Medians use the lower median when a failed sample leaves an even count.
- RJR_subst needs the optional recommendation judge; citation recall covers finding claims only (no claim
  splitter); copy-through needs `--prior-scores`, and so do stale_finding_rate and resolved_acknowledgement
  on a delta review with a prior table (the v1 scores map each prior finding ID to its key flaw; without
  them both are null, not 0.0); false_resolution_rate is a prereg proposed addition and stays null.
