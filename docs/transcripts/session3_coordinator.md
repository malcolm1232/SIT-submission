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
4. Committed each workstream as it landed (WIP snapshots in between, because the stop hook demands a
   clean tree) and spawned one verifier per workstream, each with write access and a mandatory edit
   log; the two harness verifiers got a small live Haiku budget. Relayed the grader verifier's `$schema`
   finding to the matcher verifier mid-run.
5. Ran the first live pilot scoring of `docs/live_runs/live_cc_opus_payments_v1` (57 Opus calls,
   $6.89; artefacts in that folder's `eval_pilot/`).
6. Ran the live grader on the same review: the first Pass A call stopped at the $1 per-call cap the
   verifier had warned about. Added `grader.max_budget_usd_per_call` (4.0) with tests and re-ran.
7. Updated README, HANDOFF, HANDOVER_FULL (§5 lessons 17-20, §6 rewritten, new §9) and this record.

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

## Report: E1 verifier (matcher, metrics, statistics, live judges, `sit-eval score`)

**1. Status.** `ruff check harness tests/eval_harness` is clean. `pytest -q tests/eval_harness tests/eval_grader tests/test_*.py` gives 757 passed, 0 failed (219 of them in eval_harness). I did not run or touch `tests/robustness`.

**2. Defects found and fixed.** Every edit is in `research/audit/verify_eval_harness_editlog.md`. No prompt or judge schema changed, so the `PROMPTS.lock` bundle stays `d9e14df5…`.
1. **Fake answers reused by live runs.** The result cache key ignored which client had answered, and `--out` defaults to the same folder for every judge kind, so a `--judge fake` run followed by a live run would reuse fake answers as real judgements. Fix: the cache key includes the client. Test: `test_eval_verifier_e1.py::test_cache_never_serves_fake_answers_to_a_live_client`.
2. **Retries were not costed.** A call that succeeded after retries reported only its last attempt's cost; a failed attempt with a known cost was charged a flat reserve. Fix: `ClaudeCodeJudge` sums every attempt and counts unknown-cost attempts; the runner charges known cost plus one reserve per unknown attempt. Two tests.
3. **A grader error stopped `sit-eval score` from starting** (seen live: the grader verifier's in-progress edit had a syntax error and `cli.py` imported the grader at startup). Fix: guarded import; `grade` exits 2 with the error, `score` still works. Test: `test_score_cli_survives_a_broken_grader_package`.
4. **The dry run gave misleading prices** (priced every model at Opus; showed $1-5 for a run that cost $0.32). Fix: names the price model, warns on mismatch, adds caveats (retries not counted, whole-document calls cost more, thinking unmeasured, prices UNVERIFIED). Test: `test_dry_run_flags_a_model_outside_the_price_basis`; also pins 80 overlap pairs and 300-440 calls for the live run.
5. **Coordinator requests.** Both live clients drop a root `$schema` before sending (the harness's own schemas were already stripped in `prompts._schema`). `build_judge` fills options the caller leaves out from `config/eval.yaml`, so the grader gets the per-call `--max-budget-usd` (1.0), timeout and retries; explicit options win. One test each.
6. **New option, `--adaptive-samples` (off by default).** Third pairwise sample only when the first two disagree or one fails; the median of three is then the same. Test: identical medians and assignments with fewer calls. Needs owner approval as a reading of prereg's "3 samples, median".

**3. Decisions on the listed deviations.**
- **Unmatched PARTIAL against an unmatched flaw becomes VALID_UNPLANTED: REVERTED.** It inflated strict P_a; metrics.md defines VALID_UNPLANTED as an issue "missing from the key". These findings now go to the LLM adjudicator, as in the §13 pseudo-code, with the flaw recorded as `partial_key_flaw_id`. A new exploratory metric, `precision_adjudicated_partial_credit`, shows the old reading. Live example: the LLM called one such finding INVALID_OPINION; P_a was 0.33; the old rule would have given 0.67.
- **G1 character-level ratio: KEEP.** prereg, ADR-006/007 and the superseding note all say "the same function as the agent's verify stage", which is a character-level partial ratio; metrics.md's "token-level" wording is stale.
- **Short doc-evidence quotes must match exactly: KEEP.** The spec puts the 8-token minimum only on `DocAnchor`.
- **Exact match first, page-window fallback: KEEP. Lower median: KEEP. 3 with `location_ok: false` capped at 2: KEEP** (§2.2; absorbed one noisy sample live). **Ties to the higher-ranked finding: KEEP** (term at most 0.0014, below the 0.01 severity step). **The rest: KEEP as labelled.**

Also checked with no defect: Hungarian matched brute force on 3000 random matrices up to 6x6, rectangular and with ties. §14 recomputed by hand: R .5, Ps .4, Pa .6, F1 .444 / .545, SWR .8, nDCG .669, MRR 1/3, HFR .2, dup .2, calibration n 4 with labels [1,1,1,0]; the test checks exactly these. Blinding, credit modes, thresholds, still-valid observations. Cluster bootstrap and paired difference match §12.2-12.3; sign-flip, permutation, McNemar, Holm, BH, aggregation order. Null metrics carry reasons. Resume cache key covers prompt, seed, model, effort, schema. Exit codes 0 ok, 1 schema failure, 2 refusal/usage, 3 cost stop. Isolation holds; nothing under `eval/blind/` read. Grader seam: separate `grader_calls.jsonl`; `judge_calls.jsonl` append-only one line per write; system prompts 2 KB (harness) and 11 KB (grader); documents always in `user`.

**4. Cost and the candidate set.** The code is not broader than the text: metrics.md §2.3 and prereg `matcher.candidates` say the candidate set is the union of location overlap and the shortlist, uncapped, with overlap checked against the flaw's `location`. The key's `location.sections` (legacy `section_refs`) lists every place a flaw touches, including requirement tables 2.1/2.2, decision list 24 and acceptance criteria 26.x; `anchor_quote` is still pending. The 80 pairs come from 2.2 (20), FR-5 (16), 26.x (12), 24 (11), 2.1 (8).

| Option | Total calls | Typical cost (UNVERIFIED planning prices) |
|---|---|---|
| Prereg pairwise (union) | 300-440 | ~$37 |
| Same, adaptive | 220-440 | ~$33 |
| Same, `--no-grounding-judges` | 260-400 | ~$33 |
| per_flaw_batch | 102-116 | ~$11 |
| per_flaw_batch, adaptive | 88-116 | ~$10 |
| per_flaw_batch, no judges | 62-76 | ~$7 |

| Candidate rule (computed, not a CLI option) | Overlap pairs | Total calls |
|---|---|---|
| Union, as now | 80 | 300-440 |
| Drop listing sections 2.1/2.2/24/26.x | 39 | 177-317 |
| Requirement/decision IDs only | 33 | 159-299 |
| Shortlist bounds pairwise scoring | 0 | 60-200 |

BUDGET.md §3 assumed 3 candidates x 3 samples per flaw (126 pair calls), 0.3k output tokens, 2k-token G3 inputs and batch pricing: $1.05 per run, $106 for Tier A. That matches "shortlist bounds pairwise", not the text. At the measured counts, Tier A instruments would cost roughly $1k-6k. The live run can only be an exploratory pilot (prereg unfrozen; key `scored_run_ready: false`, LC12). Before freezing Tier A the owner must choose: amend MM §2.3 and prereg so the shortlist bounds pairwise scoring; drop the listing sections from overlap; approve per_flaw_batch; add Message Batches; or raise the instrument budget. H10 matcher validation must use the same rule.

**5. Live check** (claude-haiku-4-5, effort low, made-up 2 flaws / 3 findings / short document) through the real `sit-eval score` CLI: 27 live calls, $0.32. All 7 call types' schemas accepted, including the integer `enum [0,1,2,3]`. Every answer validated; every cost logged. The cost stop fired at $0.60 (`stopped_budget`, exit 3); in-flight calls finished and were cached; the re-run resumed with 0 live calls. per_flaw_batch reused the cache and added 6 batch calls. Samples vary (one pair scored 3, 2, 3). Haiku used 0.6k-4.8k output tokens per call.

**6. Found but not fixed.** The cost stop can overshoot: the in-flight reserve covers one attempt; a retried call can spend up to (1+3) x $1, about $12 worst case at concurrency 4. The grader now inherits a $1 per-call cap that a long Opus Pass B might hit. Judge failures exit 0 with null metrics, so batch scripts must check `failures`. For v2 documents, the flaw-level McNemar and permutation tests also count fixed flaws (exploratory). Identical prompts share one cached answer. LC7 prompt-overlap check not run; the harness imports private agent helpers. Proposed text changes: MM §2.3 (whether the shortlist bounds pairwise scoring; what "flaw anchor" means); MM §2.3 step 4 (PARTIAL against an unmatched flaw); MM §5.1 G1 (character-level); prereg `matcher.pairwise_scoring` (adaptive third sample); prereg LC9 / stop_rule (`sit-eval score`; `matcher.prompt_sha256` = `d9e14df5…`); BUDGET.md §3 matcher cost model.

**7. Still unverified.** Opus cost and thinking per call at high effort; document-prompt caching across fresh `claude -p` sessions; `AnthropicJudge` live and Message Batches; how tightly `--max-budget-usd` caps a call; whether `$schema` really breaks the CLI on the harness path; the robustness suite.

---

## Report: R verifier

**1. Summary.** Ruff is clean on `agent harness tests`. The full `pytest -q` run passes 865 tests, with no skips or xfails. `tests/robustness` passes 108 tests, three runs in a row with no flakes, about 15-16 s each. No git, no network, no `claude` CLI, nothing opened under `eval/blind/`, no prompt changed.

**2. Defects found and fixed** (logged under "Verifier edits" in `research/audit/robustness_suite_editlog.md`; each regression test fails with its fix reverted in a scratch copy):
1. **INF-07's test missed its main claim.** Mutation testing showed it still passed when "a confirmed 401 disables every server" was removed. The test now asserts only the first call reaches the transport.
2. **Fix 5's end-to-end regression test only checked wording.** "TBD" in `recommendation.rationale` was already rejected by the 15-character minimum. The test now also covers `title` on a strength finding, which has no length floor.
3. **Wrong stop reason with zero evidence.** A model stop vote was reported as `sufficient_evidence (model_stop_vote)` with no external evidence. Fix in `phases/research.py`: `tool_failure` if no call succeeded, `no_marginal_gain` if calls succeeded but found nothing. INF-24 asserts this.
4. **BEH-25, BEH-10 and BEH-12** fixed (section 3).

The six implementer fixes are correct and minimal, and each test fails when its fix is reverted. The `nth` change: before the fix the LLM layer never passed `nth`, so no existing test relied on it; all 26 tests in `test_fault_injection.py` pass. Thirteen offline scenarios mutation-tested across INF, LLM, NET, OPS, ADV and BEH: 12 failed as they should; INF-07 was the gap. The oracles call `invariants.check_all` and `check_INV_08`. No key or key prefix in any fixture, YAML, cassette or the CSV (compared against the real `SIT_MCP_API_KEY` without printing it).

**3. The four fix items.**
- **BEH-25: fixed.** On a stage crash (exit 4) the run writes `report.partial.md`, named in `failure.json`: completed stages and the crashed stage, counts of planned questions, evidence entries and unverified drafts, and the resume command. No finding is shown, and it is not `report.json`, so INV-02 holds. The "illegal transition raises" half has no `transition()` function to call; the test checks the transition table only moves forward.
- **BEH-10: fixed.** In `refine`, a change to severity, disposition or kind with no stated reason and no new evidence is rejected; the earlier version is kept and the rejection is written to the finding's history. A change with a reason still goes through.
- **BEH-12: fixed.** `verify` flags a recommendation whose change summary uses a reversal verb and shares at least 3 words with an approved decision when the finding has no `challenges` label for it. The flag shows in the report's limitations; it never drops the finding.
- **NET-02: not fixed.** On the `claude_code` backend preflight only runs `claude --version`, so offline shows up at the first model call and its retries. Making the fault wrapper fail fast would pass the test without changing live behaviour. Options: (a) a connectivity probe in preflight that respects `HTTPS_PROXY`; (b) connection errors on the very first model call of a run get a 10 s retry window; (c) relax the criterion. Recommended (b) in both live gateways, plus running the no-retry preflight before `models.retrieve` for `anthropic_api`.

**4. Owner options.**
- **LLM-05** (one hung call costs the full 1800 s timeout against a 540 s deadline): (a) bound each attempt by the remaining deadline; (b) keep the timeout and set the demo deadline consistently; (c) idle-stream timeout. Recommended (a) for deadline-limited runs, decided together with the demo effort and deadline.
- **INF-08** (MCP key unset: warns, makes 6 model calls, finishes doc-only): (a) fail fast unless `--no-tools`; (b) continue doc-only (runbook §6 for a revoked key). Recommended (a) for a missing key, (b) for a key revoked mid-run.
- **LLM-10** (no token count before sending): (a) the API's count_tokens (not available on `claude_code`); (b) character estimate with a 0.8 margin. Recommended (b) plus building the 150-page fixture.
- **OVF-07** (`tools/sources.py` lists the sample's own hosts `github.com/pgvector`, `pgvector.dev`, `kafka.apache.org`): (a) remove; (b) move the vendor host list into config. Recommended (b) plus building `scripts/leakage_grep.py`.

**5. Coverage.** BEH-10, BEH-12 and BEH-25 moved into the passing suite. Offline 46 (2 need a decision: LLM-05, NET-02), laptop 28, not a schedule 7 (3 need a decision). Needs decision 8 -> 5. INF-11 now names `test_fault_injection.py::test_inf11_tool_error_not_retried_then_unusable`. CSV: 44 PASS, 5 FAIL, 32 BLOCKED.

**6. Found but not fixed.** `sit-review run --faults` silently ignores `process:` entries (BEH-25 and OPS-04 run clean through the CLI). After a successful resume, `report.partial.md` and `failure.json` remain. Fix 5 drops a whole finding when `next_step.owner` is exactly "TBD" (policy). The MCP and LLM fault layers measure time from their own start. The argument sanitiser lets up to 2,000 characters of document text into a search query (policy).

**7. Still unverified.** The 28 laptop rows and the L1/L2 halves; live gateways under faults; BEH-12 false-alarm rate on real documents; the `no_marginal_gain` branch end to end.

---

## Owner decisions later in the session

- "go with your recommendation on the matcher rule": the shortlist bounds pairwise scoring (USER_DECISIONS #10).
- "can u proceed to build end to end and u decide what is necessary": remaining build decisions delegated to the coordinator.
- Demo package approved (demo effort profile, deadline inside model calls, one $3-4 measurement run); the four robustness policies, the separate label for partial matches and the adaptive third sample "as per ur rec"; no second-provider judge.

## Report: matcher rule implementer (shortlist bounds pairwise scoring)

1. **Checks:** `ruff check agent harness tests` clean; `pytest -q` 884 passed, 0 skipped (867 before).
2. **Files:** code `harness/sit_eval/{matcher,scoring,config,cli,metrics,report_md}.py`, `schemas/scores.schema.json`, `prompts/matcher_shortlist.md`, `prompts/PROMPTS.lock`, `config/eval.yaml`; tests new `tests/eval_harness/test_eval_candidate_rule.py` (9), updated `eval_builders.py`, `test_eval_matcher.py`, `test_eval_e2e.py`, `test_eval_verifier_e1.py`, `test_eval_worked_example.py` (tests that pinned 80 overlap pairs and 300-440 calls now run `union` explicitly; none deleted); text `research/methodology/metrics.md` (§2.3 steps 1 and 6, §13 pseudo-code, dated amendment note), `eval/prereg.yaml` (`matcher.candidates`, `deviations_log` comment), new `eval/prereg_deviations.md` (entry 1), `eval/human_labelling_protocol.md` (T4 source), `docs/USER_DECISIONS.md` (#10), `harness/README.md`, `docs/BUDGET.md` (pointer sentence only).
3. **Design:** shortlist failure (after the runner's 3 retries) leaves the flaw with no candidates, unmatched, listed in `failures`, `shortlist_ok: false`; `recall` and `lenient_recall` carry `shortlist_failed_flaws` and a lower-bound note; no fallback to overlap (it would mix two rules). Under `union` a failed flaw keeps its overlap candidates. Hint: findings stay in seeded random order; a `<location_hint>` block lists overlapping ids or "none"; the prompt says look at those first, the hint is not a verdict, only returned findings get scored. `union` uses the same prompt. The optional embedding top-3 is also a hint only. Audit trail per flaw: `overlap_hint_ids`, `shortlisted_with_overlap`, `shortlisted_without_overlap`, `overlap_not_shortlisted`; `matching.candidate_rule` recorded. §14 example runs under both rules with an explicit shortlist fixture; same expected numbers. Default test fake shortlist returns the hinted ids up to K.
4. **Dry run on the live run** (20 findings, 14 flaws), priced per call kind:

| Mode | Calls | Pair scoring | Cost |
|---|---|---|---|
| Bounded, pairwise, grounding judges on | 60-200 | 0-126 | $10.72-19.12 |
| Bounded, judges off | 20-160 | 0-126 | $3.52-11.92 |
| Union, judges on | 300-440 | 240-366 | $17.92-26.32 |
| Union, judges off | 260-400 | 240-366 | $10.72-19.12 |

   Bounded with judges on: 14 shortlist, 6-20 adjudication, 20 premise, 20 citation calls. Bounded per_flaw_batch: 60-116 calls with judges, 20-76 without. Pilot prices check out (shortlist $0.110, batch $0.062, adjudication $0.332). A single pair call is not measured (the pilot had none); a fit of batch cost against candidate count gives about $0.03. Premise ($0.33) and citation ($0.03) are estimates. `per_call_s` changed to 5-20 s to match the pilot. Whole-document calls now dominate run cost, not pair scoring.
5. **New matcher prompt bundle hash:** `ac35d198ecef1c5a9176acd29e3d82fd9203c35eee4f4624d86da2b429ecc156` (was `d9e14df5…`), written into the deviations entry.
6. **Risks:** the shortlist is now the only way into scoring; a match it leaves out scores 0 and lowers recall with no error. With k=3 a flaw with more than 3 plausible findings can miss one; on the payments key the hint is long (sections 2.2, 24, 26.x, FR-5). `overlap_not_shortlisted` is where to look; a miss at a non-overlapping location leaves no trace. H10/T4 now samples shortlisted pairs only, so it checks the scorer, not shortlist recall; suggested a small T4 sample of `overlap_not_shortlisted` pairs. A deterministic DUPLICATE now needs the duplicate shortlisted too, otherwise it costs a $0.33 adjudication call. The dry-run minimum is now 0 pair calls; at the pilot's rate a run lands at about two thirds of the maximum. The old pilot `scores.json` was made under the union rule and left as is.

---

## Report: W3 answer-key drafts

All three keys are drafted and validate, and all stay at `scored_run_ready: false`. Nothing is signed. The owner reviews `eval/KEY_SIGNOFF.md` and then signs.

**1. Counts.** Flaws drafted: 15 per item, 45 in total (14 v1 flaws plus the v2-only F15 in each); the protocol's T3 line counts 45. Each flaw got a `core_insight`, an `anchor_quote` with its page, an `expected_disposition` and `acceptable_dispositions`. Approved decisions: 57 rows from the "Confirmed Decisions" tables (payments 19, 10 linked to a flaw; clinical 20, 11 linked; lakehouse 18, 10 linked); each flaw's `affected_decisions` filled from these links. All 20 `external_fact` entries now have claim, source and an audit note from the eval-data audit; `verified` stays false. `v2.changed_sections` filled from a section-level diff of v1 against v2. Sound-section overlaps rechecked and complete; two sound sections split into sub-locations (clinical §4, lakehouse §16). Filled from the session record: `author_type` (llm), `author_model` (claude-opus-5-5), `generation_date` (2026-10-02), `generator_session_ref`, `brief_sha256`. Still pending: the seven drafted fields until the owner signs; `key_second_review` (the owner's signature is the second review); `canary_guid` (one S-dev GUID assigned but not embedded in the documents, since embedding changes the PDFs and their hashes; owner decides).

**2. Files and schema addition.** `eval/synthetic/{payments_orchestration,clinical_rpm,research_lakehouse}/answer_key.json`: new top-level `authoring_drafts` block with every draft plus an empty `signoff` record; legacy fields untouched. `answer_key.canonical.json` regenerated. New `eval/KEY_SIGNOFF.md`. `spec/answer_key.schema.json`: optional `authoring_status.drafts` (`drafted_by`, `drafted_on`, `fields[]`, `note`); rejects `scored_run_ready: true` while `drafts.fields` is not empty. `spec/convert_answer_keys.py`: copies drafts into the canonical key, keeps drafted fields in `pending`, applies `signoff {signed_by, signed_on, accepted[]}` and sets `scored_run_ready` true only when nothing is pending (nobody sets it by hand); new `--tier synthetic` (never lists or opens `eval/blind`) and `--verify-anchors`. `spec/README.md`: §2.8 paragraph and new §2.9. `validate_examples.py` passes (32 negative, 28 adversarial) in a scratch copy without `eval/blind`; converter run under an audit hook recorded zero blind opens; a trial sign-off in a scratch copy turned `scored_run_ready` true and validated.

**3. Anchor quotes.** All 45 flaw quotes and 57 decision quotes are exact, case-sensitive, unique matches in `sit_review_agent.ingest.pdf.ingest` text of `design_v1.pdf` (`design_v2.pdf` for the three F15 flaws); page from the match; also verbatim in the Markdown. Re-check with `python3 spec/convert_answer_keys.py --tier synthetic --check --verify-anchors`. No fuzzy quotes. Seven decision quotes are under 8 tokens (short table cells). Clinical F09 (§17.4) and lakehouse F03 (§13) match exactly but the agent's `verify_anchor` section check fails: the ingest heading heuristic reads numbered list items inside those sections as headings (an `agent/` ingest bug).

**4. Look at first.** Lakehouse F05 (HNSW memory formula required by the legacy "first two items" rule; the audit called it supporting; too strict). Lakehouse F06 (correct NIST controls required; strict). Lakehouse F04 (cost breach only supporting; left out of the core insight). Clinical F05 (arguable per the audit; depends on where NFR-2 timing starts). Clinical F03, clinical F12, payments F04 (an optional "or / at least one of" item dropped from the core insight). The three "decision depends on pending item" flaws drafted as `governance_decision` (policy choice; several others borderline). Decision links left out on purpose: lakehouse Catalog/F10, lakehouse Primary storage class/F04, payments Fraud/F01. The v2 change logs omit some sections that actually changed.

**5. Tests.** Ruff clean; full `pytest -q` 932 passed; one transient robustness failure during parallel edits passed on re-run. No test failed because of key content.

**6. Owner review time.** About 3 hours in three sessions: 45 flaws at about 3 minutes (2.25 h), 57 decision rows (0.3 h), 20 external facts (0.3 h), v2 sections, sound splits, canary decision and signing (0.25 h). The 42 v1 flaws alone take about 2.1 h.

---

## Report: W2 demo CLI

**1. Checks:** ruff clean; full `pytest -q` 932 passed, 0 skipped; one transient failure in W1's mid-edit robustness file passed alone and on the final run.

**2. Files.** New `agent/sit_review_agent/replay.py`, `kruns.py`, `report/coverage.py`; tests `tests/test_cli_replay.py`, `test_cli_coverage.py`, `test_cli_kruns.py`; edited `cli.py`; Edit-only `agent/README.md` (CLI lines, three module rows, "Replay" section) and `docs/DEMO_DAY_RUNBOOK.md` (line 9, line 18, §9 CLI row; no line numbers moved).

**3. Commands.** `--profile NAME` on `run`/`review` and `preflight`, recorded in `cli_args`; `resume` reuses it (tested: interrupted profile run resumes with no drift; unknown profile exits 2). `--k N` (REPRODUCIBILITY §9, prereg `runs_per_item`): N independent sequential runs `<group>-k1..kN`, intention-to-treat (a failed run counts, never rerun, k never extended), stops early only on Ctrl-C or setup/config error; `<run_root>/<group>.kgroup.json` after every run (dir, outcome, verdict, findings, cost, wall, summary with verdict agreement and findings range); each run gets `extra.k_index` and `k_group.json`; exit 0 if all completed else the first failing code; `--k 0`, with `--resume` or `--plan-only` are usage errors. Jaccard and detect-in-all-k stay in the harness. `dra coverage [RUN | --run DIR] [--depth N] [--json]`: latest run by default, reads only the run dir (~4 ms); rows are sections rolled up by number, columns criteria C1..Cn; cells `nX` (n findings, worst severity X; S strengths), `ok` checked no issue, `-` not applicable; sound-areas column; report-only dirs fall back to report.md's coverage table. `dra --help` lists preflight, review, explain, coverage, resume, replay (tested with every review flag in the runbook table).

**4. Replay.** `llm.jsonl` already stores full response content for both backends. Replay re-runs the real phases into `<id>-replay-<hex>` with `mode: replay`; model calls from `llm.jsonl` by the call IDs the final state lists per phase (a stage re-run by `resume` is served from the re-run); each request must match the recorded phase, purpose and request hash, recomputed with the recipe of the backend that made the call, unit-tested against the real gateways; a mismatch exits 4, never invents. Recorded failures are raised again (refusal, truncation, schema errors, 401, 429, injected faults). Tool calls from `tools.jsonl`, strictly once each. A virtual clock follows recorded durations. At the end the new `report.json` is compared with the recorded one (ignoring IDs, times, manifest); a difference exits 4. `report.md` gets a "Replayed evidence" banner, the manifest a deviation, `replay.json` the comparison. Sockets disabled in tests. It reproduced the report exactly for normal, resumed, doc-only, moved-input runs and LLM-06/07/08, LLM-01, INF-04, INF-07, INF-24 fault runs. It refuses with exit 2 naming what is missing (report/config/`llm.jsonl`/state, response content, changed prompts, missing or changed input, unrecoverable tool list). The committed `docs/live_runs/live_cc_opus_payments_v1` cannot be replayed (no `llm.jsonl`, no state). Logging changes needed from W1: (1) tool listings logged (attempt-0 `tools` or a `tools_list.jsonl`), required for live claude_code runs with tools; (2) errors raised before an attempt (deadline, context too long) logged to `llm.jsonl`; (3) optional `k_index` through RunRequest/RunState into `build_manifest`; (4) `effective_config.json` sorted keys lose `tools.capabilities` order that the plan prompt depends on (worked around); (5) `ConsoleProgress.stream` captures `sys.stderr` at import time.

**5. Runbook items still missing:** `make smoke` (no Makefile); the runbook's `dra explain F-07` example does not match the ID format (`FND-007`).

**6. Not verified (live only):** end-to-end replay of real anthropic_api or claude_code runs; replay clock against deadline decisions on long live timelines; `--k` live; W1's `demo.yaml`.

---

