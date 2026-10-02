# Third coordinating session, 2026-10-02 (branch `claude/happy-darwin-d0bl94`)

Coordinator: started on Claude Fable 5.1, switched by the owner to Claude Opus 5.5 with `/model`
before any build work. All subagents: Claude Opus 5.5. The owner's instruction was "pls cont.",
taken as: continue `docs/HANDOVER_FULL.md` §6 with the delegation pattern of session 2.

## What the coordinator did, in order

1. Fast-forwarded this branch to `claude/great-hopper-hbx7h0` (session 2). Baseline: ruff clean,
   444 passed.
2. Froze the harness interfaces before fanning out (lesson 4 of §5): new package
   `harness/sit_eval` separate from the agent, console script `sit-eval`, `sit_eval/judge.py`
   (`JudgeRequest`, `JudgeResult`, `JudgeClient`, `FakeJudge`, `build_judge`), grader CLI mount
   point, package data. Untracked the generated egg-info.
3. Spawned three implementers in parallel with disjoint ownership: E1 matcher + metrics + live
   judges + `sit-eval score`; E2 lecturer grader; R robustness P0 suite (`tests/robustness/`).
   All offline; the coordinator runs live scoring after verification.

---

## Report: E2 lecturer grader

**1. Status.** My folders pass ruff. Repo-wide `ruff check agent harness tests` shows 2 errors, both in R's in-progress `tests/robustness/oracles.py` (I001 import order at line 15, E501 at line 177). I did not touch it. Full `pytest -q` passes: 732. My suite is 79 tests in about 4 s. Nothing is skipped or xfailed.

**2. Files changed.** All new; I edited nothing outside my folders.
- `harness/sit_eval/grader/`: `__init__.py` (the stub, rewritten), `cli.py` (the stub, rewritten; `app` kept), `pipeline.py`, `projection.py`, `verify.py`, `scoring.py`, `answer_key.py`, `costs.py`, `validation.py`, `fake.py`, `report.py`, `prompts.py`, `schemas.py`.
- `harness/sit_eval/grader/prompts/`: `system.txt`, `pass_a.txt`, `pass_b.txt`, `segmenter.txt`, `repair_note.txt`, `prompts.lock.json`.
- `harness/sit_eval/grader/schemas/`: `pass_a_output.schema.json`, `pass_b_output.schema.json`, `grade_report.schema.json`.
- `tests/eval_grader/`: `conftest.py` and `test_grader_{prompts_schemas,projection,scoring,pipeline,validation,e2e_live_run,cli}.py`.
- Bundle hash for prereg `grader.prompt_sha256`: `64efe6b88489ac5542d7028f62782ed3c0b3096b0dfbfc0ac9ead22b4db75df0`. It covers the 5 prompt files and the 2 output schemas. Re-lock with `sit-eval grade lock --write`.

**3. Design decisions.**
1. **Copied verbatim and drift-tested.** The prompt and schema files are extracted from the code blocks in grader_prompt.md. A test fails if they drift from that file or from the lock.
2. **Whitelist projection.** I copy only known fields, so a new spec field cannot leak by default. I also drop more than the spec list: `metadata.review_id`, `run_id`, `created_at`, `text_path` and the hashes, plus `limitations[].degradation_ids` and `stop_reason.detail`.
3. **Scrubbing.** Identifying values are replaced with `[redacted]` as whole tokens unless the design itself contains them. These are model IDs, run and review IDs, git commit and branch, config and prompt hashes, tool servers and call IDs.
4. **Leak guard before every call.** The harness checks the rendered system and user text and refuses to send if anything identifying is there.
5. **No segmenter.** Every Tier A condition emits a structured Review. A non-JSON review is rejected with a clear error.
6. **What the grader sees.** Pass B gets the projection as compact JSON in rank order, so D10 judges the structured output, not report.md. Pass A hides each finding's `rank` and spells out the approved decisions a finding refers to.
7. **Shuffle seeds and the verify step.** The Pass A shuffle seed is `seed*1000+i+1`, recorded with the order shown. The no-model verify step uses the agent's own `verify_anchor` for anchor quotes.
8. **Grader quotes are checked.** If the grader marks a hallucination `verified_false` but quotes design text that is not in the document, it is downgraded to `suspected`. That flag cannot trigger a cap and is sent for human review.
9. **Aggregation.** Caps are applied per sample, then the median is taken per dimension. With 2 samples the median is the mean, so a score can be x.5. The final hallucination count is the median count. G4 (verdict present) is computed in code.
10. **G5 (prompt injection).** It fails on the harness pre-scan or on any model flag, and always asks for human review.
11. **One repair call.** If an output fails the full schema, one repair call is made with `repair_note.txt` appended. A second failure stops the grade with `status: failed`.
12. **LLM-facing schema.** The schema sent in `JudgeRequest.schema` has `min/maxLength`, `min/maxItems`, `minimum/maximum`, `pattern` and `format` stripped, per spec "LLM-facing schema". Outputs are always validated against the full schema.
13. **Budget and logs.** The budget is shared and checks before each call, using a list-price token estimate. After a call it counts the client's reported `cost_usd`, falling back to the estimate. Inputs and outputs are saved per call in `inputs/` and `outputs/`.
14. **Fake judge.** `--judge fake` is a deterministic, content-aware fake used to test the pipeline end to end. Its scores are meaningless, and `grade.json` and `grade.md` label it "PLUMBING ONLY".
15. **Meta-validation.**
    - Built automatically from any base review: V1, V2, V3, V4 (5 fabricated clauses that do not exist), V5, V7, V8, V10, V11 and V13.
    - V6, V9 and V12 need an author and are passed in with `--variant`.
    - Pass rules for all 13 run on graded base/variant sample pairs.
    - The V1/V4/V10 runner works with any JudgeClient. Tests show it passes with the heuristic fake and fails with a lenient fake.

**4. Deviations.**
- **Two extra keyword arguments on `grade_review`.** I added `v1_document`, `model` and `effort`, all optional. Without the prior design text, D11 can only see the prior review.
- **Key-alignment output is counts, not shares.** §5.3 `key_alignment_diagnostic` has `aligned_high_share` and `aligned_all_share`. I emit counts only (full, partial, high, traps, extras). A share of key items aligned is recall in all but name, and the brief forbids that. A test checks that no "recall" or "share" key appears anywhere.
- **Legacy key IDs are padded.** `K1` becomes `K01`, because the PassBOutput `key_id` pattern `^[A-Z]{1,4}-?[0-9]{2,3}$` rejects K1–K9. A map back to the original ID is kept.
- **G3 with two or more hallucinations also keeps D9 ≤ 2 and grade ≤ C.** GR §4.2 states only D4 ≤ 1 for that row.
- **Cited URLs are not fetched (offline).** They are marked `not_checked_offline`.
- **The repair note is not in grader_prompt.md.** It is in the lock instead.
- **V8 re-ranks findings.** My projection sorts by rank, so shuffling the list alone would change nothing.

**5. Expected cost to grade the live run once.**
- **Calls:** 4, or 5 with a third sample (2 Pass A, 2–3 Pass B).
- **Inputs per call:** about 64k tokens for Pass A and 89k for Pass B. The review alone is 159k characters.
- **Cost:** about $2.15–2.70 at Opus 5.5 list price, uncached; about half that with Message Batches.
- **Your $0.05–0.15 per call does not hold here.** That figure is for `claude -p`, but this review's inputs are large, so per-call cost will probably be higher. The budget will use whatever the client reports.
- **Wall time:** about 4–10 minutes, sequential.
- **Meta-validation for V1, V4 and V10 at 5 runs × 2 samples:** 20 grades and 80–100 calls.

**6. Unverified (needs a live call).**
- Whether Claude structured outputs (or `claude -p`) accept the stripped schemas. They still contain `enum` with `null`, `type` arrays, `const`, `$ref`/`$defs`, and `additionalProperties: false`.
- Whether Pass A output for 21 findings fits within `max_tokens` 32000 at effort high.
- Real per-call cost and time.
- Whether the model echoes the exact `mode` string (I enforce it; a mismatch triggers the repair call).
- How well the grader maps spec dispositions onto the prompt's older triage labels.
- Whether any real grader passes V1, V4 and V10.

**7. Writes beyond my list.** None. Throwaway smoke output went to my scratchpad. I ran no git. I opened nothing under `eval/blind/`. One minor exposure: one command printed the key *names* of `spec/taxonomy.yaml` `legacy_mappings` (e.g. `blind_a_categories`), not their contents.

**8. For E1 and the verifier.**
- **Seams:**
  - I call `build_judge(kind, out_dir=out)` with no other options; the model and effort travel in each `JudgeRequest`.
  - Purposes: `grader:passA`, `grader:passB`, `grader:passB_key_aware`, with a `:repair` suffix on repair calls. `sample_index` is 0–2.
  - `max_tokens` is 32000. The request schema is the stripped version, and I re-validate every answer against the full schema myself.
  - Please return `cost_usd` (or token counts) so `--max-cost-usd` stays accurate.
  - My call log is `grader_calls.jsonl`; pick a different name for yours in the same `out_dir`.
  - The CLI catches `NotImplementedError` from `build_judge` and exits with code 2. The dry run never builds a judge.
- **Inconsistencies in the source documents:**
  - The `key_id` pattern versus K1–K9 in grader_prompt.md §6 and worked_examples.md §6.
  - The §5.3 share fields versus spec C4.
  - spec/README.md's projection list keeps `metadata.review_id`, `run_id` and `stop_reason.detail`. In the live run these leak the backend and condition (`REV-live_cc_opus_…`, `no_tools`). The spec should drop them.
  - GR §6.1 lists "URL checks", which cannot be done offline.
  - Prereg says the median per dimension, while GR P9 says take the lower score. With 2 samples the median gives x.5, which I kept.
  - Prereg names Message Batches as the API for the primary grader. Batching belongs in the client; my pipeline runs calls one after another.
- **What checks out:** the worked Pass A excerpt and the Example C hallucination types validate against the schemas. The FQS numbers (100, 61.5, 14.2, 94.6) and the §8 profile (75.0, 63.0 failing G2, 78.5) reproduce in tests.

---

## Report: E1 matcher, metrics, live judges, scoring CLI

**1. Status.** Not fully green yet, and only R's in-progress files block it.
- **ruff:** my files are clean. `ruff check agent harness tests` reports 2 errors, both in `tests/robustness/oracles.py` (R's file, in progress).
- **pytest -q:** 771 passed, 3 failed. All 3 are `tests/robustness/test_robustness_scenarios.py` [NET-01, ADV-05, BEH-17]. They do not import `sit_eval`; I re-ran and they still fail on R's side.
- **Without R:** `--ignore=tests/robustness` gives 733 passed, 0 failed. That includes E2's grader tests, which go through my `build_judge`.
- **Mine:** 210 tests in `tests/eval_harness`, about 7-8 s.

**2. Files.**
- **New code** in `harness/sit_eval/`: `aggregate.py`, `calls.py`, `config.py`, `fakes.py`, `grounding.py`, `hungarian.py`, `live_judges.py`, `loaders.py`, `locations.py`, `matcher.py`, `metrics.py`, `paths.py`, `prereg.py`, `prompts.py`, `report_md.py`, `scoring.py`, `stats.py`.
- **New prompts:** 12 `.md` prompt files plus `PROMPTS.lock` in `harness/sit_eval/prompts/`.
- **New schemas:** 7 `judge_*.schema.json` files plus `scores.schema.json` in `harness/sit_eval/schemas/`.
- **New tests** in `tests/eval_harness/`: `eval_builders.py` (helpers) and `test_eval_{worked_example,hungarian,isolation,live_judges,runner,matcher,stats,grounding_metrics,e2e,prereg_prompts}.py`.
- **Other new:** `config/eval.yaml`, `harness/README.md`.
- **Edited:**
  - `harness/sit_eval/judge.py`: only the body and docstring of `build_judge`. No signature changed.
  - `harness/sit_eval/cli.py`: rewritten; it still mounts `grade`.
- **Untouched:** `pyproject.toml`. No new dependency; there is no numpy or scipy, so everything is pure Python.

**3. Design decisions.**
1. A `JudgeRunner` sits between the pipeline and any `JudgeClient`. It handles concurrency (default 4), re-checks every answer against its schema, and keeps a result cache in `judge_results.jsonl`. Re-running into the same `--out` re-pays nothing, so a stopped run can be resumed.
2. **Cost stop:** a call is refused if spend so far, plus the reserve of calls in flight, plus its own reserve would cross `--max-cost-usd`.
   - The reserve is `max_budget_usd_per_call` ($1 by default), so the stop is conservative: about $5 below the limit at concurrency 4.
   - Calls in flight at the stop are allowed to finish and are recorded. Status becomes `stopped_budget` and the CLI exits 3.
3. Each live attempt is a fresh `claude -p` session, so per-call cost is that call's own total. The code still subtracts any previously seen cumulative total for the same session, and the log records which basis applied.
4. **Imports from the agent backend:** `subprocess_runner`, `CompletedRun`, `API_KEY_ENV_VARS`, `FORBIDDEN_FLAGS`, `MAX_ARGV_TEXT_CHARS`, and the private helpers `_classify` and `_error_text` from `claude_code.py`, plus `_anthropic_classify` from `gateway.py`. If someone renames those private helpers, my imports break.
5. **G2 is exactly the agent's `verify_anchor`**, with `fuzzy_threshold = theta_q`.
6. **G1** uses the agent's normaliser and searches the whole document. It differs from the metrics.md wording in four ways:
   - the ratio is character-level partial ratio; metrics.md says token-level;
   - exact match is tried first, case-sensitive;
   - a section that cannot be resolved falls back to the page window alone;
   - doc-evidence quotes under 8 tokens are allowed, but must match exactly. The 8-token rule still applies to anchor quotes.
7. **Grounding judges:** the G3 judge and the citation judge each make one call per finding, with the whole document in the prompt. For an absence claim, the whole document is the retrieval. `--no-grounding-judges` makes HFR and the citation metrics null with a reason; the variant without G3 is still reported.
8. Every metric is `{value, reason, status}`. A null value always carries a reason (schema-enforced). Status is one of primary, key_secondary, secondary, exploratory, deferred or blocked, following the prereg.
9. Prompts never contain the run id, review id, model, condition, provenance, confidence or finding labels; a test checks this. Shuffle seeds are derived from `--seed` and recorded in `scores.json`.
10. `build_judge` also accepts `"fake"`, a deterministic responder whose answers are hashes and always labelled plumbing-only. Unknown options raise `ValueError`.

**4. Deviations from the brief or the prereg/metrics text.**
- **Unmatched finding with PARTIAL (2) against a flaw nobody matched:** I label it VALID_UNPLANTED with basis `partial_key_match`, deterministically. metrics.md does not define this case. It never joins the pooled key or removes a sound unit. Please confirm or change.
- **Ties in the assignment** go to the agent's higher-ranked finding, through a weight term below 1e-4. The §14 example depends on this, because f1 and f4 tie on F2.
- **Lower median** when a failed sample leaves an even count. A score of 3 with `location_ok: false` is capped at 2, because MATCH requires a compatible location.
- **Not implemented, as allowed:** embedding prefilter; Message Batches (prereg `branch_B` names it; the default path is `claude -p`, synchronous); live URL/DOI resolution; claim splitter (citation recall covers finding claims only); DEFF inflation in the stratified permutation test (needs the pilot's rho).
- **Partly computed:** JDR uses G1 only, with no G3 on sound areas. "Flawed units" for balanced unit accuracy are defined as section ids named in gold flaw locations. Critical-in-top-3 uses the first 3 criticals in key order when there are more than 3. RJR_subst needs the optional recommendation judge, which is off by default. copy-through needs `--prior-scores`. `false_resolution_rate` stays null: it is a proposed addition not yet in metrics.md.
- **Computed though deferred:** the deferred metrics (nDCG, ECE and so on) are computed and labelled deferred.
- **Statistics:** the bootstrap uses `random.Random`, so its draws differ from the numpy pseudo-code for the same seed.
- **`--granularity per_flaw_batch` is a prereg deviation** (prereg says one call per pair, 3 samples). It must be approved by you before any scored run, and `scores.json` warns when it is used.

**5. Expected cost to score the live run** (20 findings, 14 v1 flaws, 80 location-overlap pairs). Figures are from `--dry-run`, at $0.05-0.15 per call and concurrency 4:

| Mode | Judge calls | Cost (typical) | Wall time |
|---|---|---|---|
| Pairwise (prereg default), grounding judges on | 300-440 | $15-66 (~$37) | 25-110 min |
| Pairwise, `--no-grounding-judges` | 260-400 | $13-60 | 22-100 min |
| Per-flaw batch (deviation; needs your approval), judges on | 102-116 | $5-17 (~$11) | 9-29 min |
| Per-flaw batch, `--no-grounding-judges` | 62-76 | $3-11 | 5-19 min |

- I expect a real run near the low end: the shortlist will mostly pick findings that already overlap by location.
- Suggested command: `sit-eval score docs/live_runs/live_cc_opus_payments_v1 --key eval/synthetic/payments_orchestration/answer_key.canonical.json --out runs/eval/live_cc_opus_payments_v1 --max-cost-usd <cap>`.

**6. Unverified; only a live call can confirm.**
- **Schemas:** that `--json-schema` (and the API's `output_config.format`) accepts these schemas, especially the integer `enum: [0, 1, 2, 3]`.
- **Billing:** real per-call cost and latency, and whether nested `claude -p` bills to cloud credits.
- **Sampling:** whether 3 samples at provider-default sampling actually vary through the CLI.
- **Caching:** whether the 15k-token document prefix of the adjudicator and premise calls gets cached.
- **Per-call budget:** how tightly `--max-budget-usd` caps a single call.
- **API judge:** that `AnthropicJudge`'s request body works live. It mirrors the agent's gateway but has not been called live, and it has no price table, so its cost is null unless one is given.

**7. Writes beyond my list.** Yes, one. I ran `ruff check --fix harness/sit_eval` once without excluding the grader folder. At 13:31:36 UTC it applied lint-only autofixes (likely import sorting and pyupgrade) to four E2 files: `harness/sit_eval/grader/pipeline.py`, `prompts.py`, `schemas.py`, `verify.py`. I could not diff them, because git was off-limits. E2 should re-read those files before its next edit. After that, I ran fixes on my own paths only. Temporary output went only to the scratchpad.

**8. For the other workstreams and the verifier.**
- **Grader seam (E2):** E2 calls `build_judge(kind, out_dir=...)` with no options, so it gets a 1200 s timeout, 3 retries and no per-call budget. The model and effort come from each `JudgeRequest`. `ClaudeCodeJudge` passes `system` on argv, so `system` is limited to 100,000 characters. Long text such as the design document must go in `user`. Both workstreams log to `<out_dir>/judge_calls.jsonl`.
- **Answer key:** every payments flaw has `core_insight: null` and `scored_run_ready: false`. The matcher substitutes description plus required credit items, and warns. Prereg LC12 forbids scored runs on such keys.
- **Key locations:** sections "2.2" and "24" and FR-5 appear in most flaws, so location overlap is broad (80 pairs). That breadth is what drives the pairwise cost.
- **Live report findings:** 5 doc-evidence quotes are under 8 tokens (table cells). EV-016 cites p1/s12.4 for a title-page quote, so G2 fails on it. The agent's verify stage does not check evidence citations' page or section.
- **Prereg text to update:** it names `eval/score.py` (LC9, stop_rule); the tool is now `sit-eval score`. `matcher.prompt_sha256` should take `PROMPTS.lock`'s `bundle_sha256` (currently `d9e14df5…`).
- **Leakage check LC7:** the overlap check between judge prompts and agent prompts was not run. The adjudicator sees the key summary: flaw descriptions plus sound-section traps.
- **Held-out set:** I did not run `spec/validate_examples.py`, because it globs `eval/blind` (FE R-03). I opened nothing under `eval/blind/`. I also skipped spec/README §2.4, §2.6 and §2.7.

---

