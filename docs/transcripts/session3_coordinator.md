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

## Report: R robustness P0 suite

**1. Result.** Ruff is clean on `agent harness tests`. The full `pytest -q` run passes 829 tests, including the other workstreams' tests. My suite is 96 tests in `tests/robustness` and takes about 15 s. It makes no network, key or `claude` calls.

**2. Coverage of the 81 P0 scenarios.**
- **Offline: 46.** 41 pass end to end. 5 fail because of agent defects and need a decision: LLM-05, NET-02, BEH-10, BEH-12, BEH-25.
- **Laptop only: 28.** Each has its exact command in the README table.
- **Not expressible as a schedule: 7.** 4 are covered by named existing tests. 3 need a decision: INF-08, LLM-10, OVF-07.

There are 29 fault YAMLs. A test loads each one through the agent's loader and checks that `--faults <ID>` resolves to it.

**3. Files changed.**
- **New:** everything under `tests/robustness/`: `README.md` (the 81-row coverage table, how to run, decisions); `faults/*.yaml` (29 files); `fixtures/cassettes/` (the selftest cassettes plus one scholarly record, so both servers are exercised); `fixtures/tools/*.json` (hand-made injected page, irrelevant results, SEO spam, benchmark evidence); `robustness_harness.py`, `oracles.py`, `robustness_coverage.py`, `robustness_results.py`, `robustness_repro.py`, `conftest.py`; test files `test_robustness_scenarios.py`, `test_robustness_schedules.py`, `test_robustness_regressions.py`, `test_robustness_results_csv.py`; `results/robustness_results.csv` and `results/robustness_summary.txt`.
- **New edit log:** `research/audit/robustness_suite_editlog.md`.
- **Agent edits:** each is small, has a regression test in `test_robustness_regressions.py`, and is in the edit log.
  1. `orchestrator.py`: when a deadline skipped a phase after research had already set the stop reason, nothing disclosed it. This hid refine being skipped, in the offline LLM-05 run and in the first live run. Now every skip is disclosed.
  2. `llm/gateway.py` (`FaultInjectingLLMGateway`): an LLM rule using `nth` never fired. So no schedule could fault only the first call of a stage. `nth` now means the stage's call index.
  3. Same class, plus `_run_build_llm`: on the fake transport an injected hang cost a hard-coded 600 s, not the configured 1800 s. The wrapper now takes the configured LLM policy.
  4. `phases/research.py`: "No external research was possible" was missing when every tool call failed but too few calls were made to open the breakers (INF-24).
  5. `phases/verify.py`: placeholder ("TBD") findings reached the report (LLM-09). They are now dropped and disclosed.
  6. `phases/_model_calls.py`: a "doc" citation whose quote is not in the document became a doc ledger entry holding that external text (BEH-17). It now falls back to the anchor's own quote.

**4. Defects found.**
- **Fixed:** the 6 above.
- **Failing, needs decision.** Reproduce any of the first six with `python tests/robustness/robustness_repro.py <ID>`.
  - **BEH-25:** a stage crash gives exit 4 and `failure.json`, but no partial report. ADR-009 and the scenario both require one.
  - **LLM-05:** one hang costs the full 1800 s per-attempt timeout. The run ends at 1802 s against the 540 s deadline, which breaks INV-01. The deadline only applies between phases, not to an in-flight model call.
  - **NET-02:** fully offline, the run exits with code 3 after 19 s virtual, past the 10 s criterion. It gives up only after the retry budget.
  - **BEH-10:** refine lowers a finding's severity with no new evidence and no reason, and it is accepted. The logged note is just "revised".
  - **BEH-12:** a recommendation that reverses an approved decision without the "challenges" label is not caught at L0.
  - **INF-08:** with the MCP key unset, `run` warns, makes 6 model calls and finishes doc-only. The scenario wants an exit within 5 s before any model call.
  - **LLM-10:** no reproduction. The agent does not count tokens before sending, and the 150-page fixture does not exist.
  - **OVF-07:** no reproduction. `tools/sources.py` lists `github.com/pgvector`, `pgvector.dev` and `kafka.apache.org`, which come from the sample's stack. `scripts/leakage_grep.py` does not exist.

**5. Design decisions and deviations.**
1. Every offline run reviews the selftest fixture with a scripted model. This isolates the fault. Quality metrics stay L1.
2. The harness applies the schedule's `process:` faults (crash, Ctrl-C) by wrapping phases. It fires them at the end of the stage, so resume must re-serve that stage's tool calls.
3. LLM `nth` is the stage's call index; `attempt` stays the retry within one call.
4. Variants (INF-10's four malformed kinds, INF-18's ten seeds, LLM-03 persistent, LLM-06 once) patch a temp copy of the schedule. There is one YAML per ID.
5. ADV-05 runs the offline half of ADV-04: a scripted model obeys the injected page. BEH-03 and BEH-20 run their L0 halves only.
6. BEH-02 deviates: "exactly 2 refine cycles" assumes a verify-to-refine loop this state machine does not have. I assert one verify pass with one repair turn.
7. BEH-17 deviates: the agent takes each citation's source type from the ledger rather than rejecting the citation. I assert that outcome, plus fix 6.
8. NET-01 adds a 200 s plan latency and a 10 s first-call latency, so the network drop lands inside research. Resume is then checked not to repeat the completed call.
9. CSV status BLOCKED means "not evaluated by this offline suite"; the notes give the command or the covering test.
10. INV-01 is checked as virtual time ≤ deadline + 30 s, plus a 30 s real-time watchdog.

**6. Unverified (needs the laptop).** All 28 laptop rows, and the L1/L2 halves of the offline rows. The real gateways under faults: the suite drives the fault wrapper's copy of the retry policy, not `ClaudeCodeGateway` itself. Real cassette shapes; the scholarly and adversarial fixtures are invented. `ClaudeCodeGateway` logs no latency on successful calls, which OPS-10 asks for. The offline log check cannot see this.

**7. Writes beyond your list.** The CSV and summary are written under `tests/robustness/results/`, which is in my folder. CLI probes ran under the scratchpad, never the repo's `runs/`. I ran no git.

**8. For the verifier.**
- The agent ignores `process:` entries. `sit-review run --faults BEH-25` exits 0 with a clean report; I confirmed this.
- The MCP and LLM fault layers each measure `after_seconds` and offline windows from their own start. The research spec implies one shared run clock.
- The argument sanitiser lets up to 2,000 characters of verbatim document text into a search query. The whole 657-character fixture document passes. This is a policy decision.
- When every tool call fails and the model votes to stop, the stop reason stays "sufficient_evidence (model_stop_vote)" with zero evidence. Fix 4 adds the doc-only disclosure but leaves the stop reason.
- scenarios.md issues: BEH-02 and BEH-17 assume a different architecture. LLM-10 and OVF-07 name a fixture and a script that do not exist. DEMO-04 is tagged L0, but its simulation is L2 only. The 1800 s timeout against the 540 s default deadline also affects INF-17 and DEMO-05.

---

## Report: grader verifier

**1. Status.** `ruff check harness/sit_eval/grader tests/eval_grader` is clean. `pytest -q tests/eval_grader tests/test_*.py`: 538 passed. The grader suite alone is now 94 tests (was 79). Full `pytest -q`: 844 passed. Nothing is skipped or xfailed. The edit log is `research/audit/verify_grader_editlog.md`. The new tests are in `tests/eval_grader/test_grader_verify_fixes.py`.

**2. Defects found and fixed.** Each new test fails without its fix.
1. **`claude -p` rejected every grader schema (the most serious one).** Found by the live check. The schema sent still had `"$schema": draft 2020-12`, and the CLI refused it ("no schema with key or ref"). Every live grade would have failed on its first call. Fix: `schemas.llm_facing()` now also drops `$schema`. The full schemas and the prompt hash are unchanged. Test: `test_grader_llm_facing_schema_drops_dollar_schema`.
2. **A judge exception other than `JudgeError` escaped.** A `TimeoutError` or client bug left no `grade.json` and no call-log entry, and the CLI ended in a traceback. Fix: `_call` now catches any exception, logs it and raises `GraderError`; the CLI exits 3. Tests: `test_grader_non_judge_error_ends_grade_cleanly`, `test_grader_cli_judge_exception_exits_3`.
3. **The budget boundary refused a call that lands exactly on the limit** (0.1 + 0.2 > 0.3 in floating point). Fix: a 1e-9 USD tolerance in `Budget.check`. Tests: `test_grader_budget_allows_a_call_landing_exactly_on_the_limit`, `test_grader_budget_boundary_in_pipeline`.
4. **The cost estimate behind the hard budget stop was about 3x too low.** Each Haiku call used about 10.5k thinking tokens; the estimate allowed 3k. Fix: `THINKING_ALLOWANCE` raised to 12000, and the misleading "$0.05-0.15 per call" CLI text replaced. The limit in `test_grader_budget_stops_mid_grade` was raised from 1.0 to 1.3 so it still checks a stop after 3 calls.
5. **`--samples 3` with disagreement ran a fourth sample.** Fix: a third sample is added only to a two-sample grade; with 3+ samples a disagreement is flagged for human review. Test: `test_grader_three_samples_never_get_a_fourth`.
6. **A split hallucination verdict was silent.** One sample flagged a verified-false material hallucination and the other did not; the median count was 0.5, so no G3 cap applied and `needs_human_review` was false. Fix: a human-review reason is added when samples disagree on that count; the scoring rule is unchanged. Test: `test_grader_split_hallucination_count_needs_human_review`.
7. **A bad `--answer-key` gave a traceback (exit 1).** Fix: `GraderInputError`, exit 2. Test: `test_grader_bad_answer_key_is_an_input_error`.
8. **`grade validate` crashed on bad input** (malformed review, `--variant V6` without `=`, V6 without a variant). Fix: all exit 2 with a message. Test: `test_grader_validate_cli_bad_inputs_exit_2`.
9. **Leakage through agent-written text.** Planted values in limitations, verdict, tags, evidence quotes, anchors, registry, sound areas and unresolved items passed through the leak guard: "Opus 5.5", "Claude Opus 5.5", "Claude Code", `--no-tools`, `no_tools`, condition `B0`. Realistic, since the agent's own degradation text contains "(--no-tools, …)". Fix: these are scrubbed and caught by the leak guard; a plain-word stop detail such as "deadline" is left alone. Tests: `test_grader_live_review_planted_identity_never_reaches_the_projection`, `test_grader_plain_word_stop_detail_is_not_scrubbed`.
10. **`grade.md` showed non-delta weights in delta mode** (display only). Test: `test_grader_markdown_shows_delta_weights`.

Also added `test_grader_dry_runs_never_build_a_judge` (already correct). Confirmed clean: prompts and schemas verbatim; weights, gates, caps, bands and the third-sample rule match GR §4 and prereg; §5.3 computed in code; hand recomputation of Example C FQS = 14.2, Example D = 94.6, V2 = 63.0, R_base with one hallucination = 69.0 grade C; rendered live-run prompts carry no model, run, backend or condition ID; key-blind calls never contain the key.

**3. Deviation decisions.** All kept. Extra G3 cap: the GR §4.2 rows read as cumulative; add a clarifying clause to GR §4.2 before freeze. Counts instead of shares: denominators are emitted so shares can be derived; update §5.3 to the counts form. K1 to K01: matches the canonical `FlawId` pattern; `key_id_map` keeps originals. Median x.5 versus P9: P9 is anchor choice for the model; aggregation follows prereg. The rest kept.

**4. Live check.** Two calls with `claude -p --model claude-haiku-4-5`, `ANTHROPIC_API_KEY` unset, no `--bare`, on an invented 2-finding fixture. First attempt rejected by the CLI before any model call ($0): defect 1. After the fix, Pass A $0.1071 and Pass B $0.1298, $0.2369 total. Both stripped schemas accepted; both `structured_output` objects validate against the full schemas; Pass B returned the exact `mode` string.

**5. Found but not fixed.** Per-call budget cap: the grader calls `build_judge(kind, out_dir=out)` with no options, so no `--max-budget-usd` reaches `claude -p` (`config/eval.yaml` sets 1.0 but the grader does not read it). Cache pricing: `claude -p` writes its cache at the 1-hour rate (about 2x input), so the dry-run estimate is not an upper bound. Lenient meta-validation criteria (V1 on median ΔS; V4 counts suspected and Pass A flags; V10's G5 flag guaranteed by the harness regex). `stop_reason.code: tool_failure` stays in the projection.

**6. Still unverified.** Opus as grader: real cost, time and thinking volume; whether Pass A for 21 findings fits in 32k tokens. The `ClaudeCodeJudge` path end to end. Message Batches. Whether any real grader passes V1, V4 and V10.

**7. Prompt bundle hash:** unchanged, `64efe6b88489ac5542d7028f62782ed3c0b3096b0dfbfc0ac9ead22b4db75df0`.

---

