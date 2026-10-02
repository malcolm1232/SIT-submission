# Session 4: integration builder report (2026-10-03)

Worker: the retry of the integration worker of session 3, which was stopped while reading and built nothing.
Branch `s4/integration`, from `0caa581`, in the worktree `SIT-wt/integration`.
Nothing was pushed.
The full edit log, with every file, the arithmetic and the mutation tests, is `research/audit/verify_runtime_cli_editlog.md`.

## Result

All six integration items are done, and the runtime policies (W1) and the demo CLI (W2) were checked together offline.

| Check | Result |
|---|---|
| `ruff check agent harness tests` | exit 0 |
| `pytest -q` | exit 0, 1011 passed, 0 skipped (baseline 983) |
| `sit-review selftest` | exit 0 |
| `make smoke` | exit 0, about 10 s (selftest plus 195 tests) |
| `make test` | exit 0 (ruff, then 1011 tests) |
| `make smoke` and `make test` in a fresh clone with its own virtualenv | exit 0 both |
| Robustness suite | 113 passed; results table regenerated: 49 PASS, 0 FAIL, 32 BLOCKED |
| Spec self-test (`spec/validate_examples.py`, blind directory filtered out) | all checks passed |
| `scripts/leakage_grep.py` | PASS |

## Commits

| Commit | Content |
|---|---|
| `e8a6c12` | Interface change: the `not_assessed` verdict in the spec, the models, the agent and the harness |
| `20a8947` | Two eval-derived hosts removed from the authority lists; the leakage gate now fails on them |
| `ab4d0b2` | `max_tokens` 128000; the CLI's output-cap error typed as a truncation |
| `dbc8218` | Integration check: coverage honesty and the deadline warning |
| `719f485` | `Makefile` with `smoke` and `test` |
| `2c416b0` | Runbook fixes and the test that pins its config listings |
| `329247f` | `eval/EVAL_PLAN.md` timing from the measurements |
| `e087db4` | k-run summary: `not_assessed` is not a verdict to agree on |
| `ae4587b` | Robustness results regenerated |
| (last) | This report and the edit log |

## The six items

1. **`not_assessed` verdict: done.**
   The label is in the schema, the taxonomy, the models, the report phase, the renderer, the harness grader gate, the scorer and the aggregator.
   The model cannot choose it: the verdict drafts use a three-label type, no LLM-facing schema contains the word, and a draft that carries it fails validation.
   Code sets it on two paths: the deadline skipped or cut assess, and the model declined the assess call twice.
   The schema and the models reject a `not_assessed` verdict that carries a confidence, a condition, a per-objective label, a finding or a sound area, and require a disclosed degradation.
   The grader's G4 gate does not count it as an explicit verdict; the old placeholder passed that gate.
2. **Hosts: done.**
   `stripe.com`, `stripe.com/blog` and `confluent.io` are out of `config/url_policy.yaml`.
   The sweep found no other clear-cut case; four single-item candidates are listed in the edit log and were kept.
3. **Runbook: done.**
   §5 uses `--profile demo`; the reserve wording and the timeline follow the profile; §4.1 lines are equal to the config files and a test now compares them; the explain example is real output.
4. **Makefile: done.**
   `make smoke` and `make test`; the interpreter is `.venv/bin/python` when it exists, else `python3`, with no absolute path.
5. **`eval/EVAL_PLAN.md` timing: done.**
   The 8-10 minute estimate is replaced by the measured figures, a floor and a cap; `docs/BUDGET.md` was not edited and its stale lines are listed in the edit log.
6. **`max_tokens` 128000: done, with one part not verified.**
   Verified on Haiku through the project's backend: the cap reaches `claude -p` as `CLAUDE_CODE_MAX_OUTPUT_TOKENS` and is enforced, and a value of 128000 is accepted.
   Not verified: that Opus 5.5 through the CLI can emit more than 64,000 tokens in one call.
   The config comment and the agent README say so.
   Spend: two Haiku calls, $0.0234 by the CLI's estimate.

## Defects found

Ten, each fixed with a regression test (edit log §2).
The ones that matter most:

- **A cap hit on the `claude -p` backend was treated as an outage.**
  The CLI does not report `stop_reason: max_tokens`; it returns an error result after its own recovery turns.
  The gateway retried that four times at the same cap.
  It is now a truncation, not retried by the gateway.
  This was found only because the Haiku check was run.
- **With `max_tokens` at 128000 the truncation retry stopped running**, so the first truncation would have ended the stage with exit 4.
- **A declined assess still got a model verdict** on a review with no findings.
- **`dra coverage` showed "checked, no issue" for a criterion whose finding had been dropped as unverified.**
- **`--deadline 300`, the runbook's own short rerun, silently produced an unassessed report** against the default reserves.
- **The runbook's config listings had drifted in four lines**, and the test that was meant to prevent that compared prefixes only.

## Judgement calls

The ten are in the edit log §5.
The three a planner may want to overrule:

1. The declined-assess path now reports `not_assessed` (the brief named only the placeholder paths).
2. At the output cap, a truncated answer gets one retry at the same cap, bounded by the run deadline.
3. No host beyond the three named entries was removed.

## Refused calls

None.
No tool call was refused in this run.

## Not verified

- Opus 5.5 through `claude -p` emitting more than 64,000 tokens with the cap at 128000.
- The `anthropic_api` backend at `max_tokens` 128000.
- The cost and number of the CLI's recovery turns at a large cap (4 turns seen at a cap of 256 on Haiku).
- Every timing in the demo profile and in the runbook §5 timeline.
- Research and refine run times, the single-call baselines, the Sonnet control grader, and parallel runs on `claude -p`.
- `dra replay` on a live run (fixture and fault-injected runs only; the committed live run has no `llm.jsonl`).
- The live grader on a not-assessed review (the code gate and the fake grader were checked).

## Proposed text for `eval/prereg_deviations.md` (not written; the sibling owns that file)

Item 1 changes no field of `eval/prereg.yaml`, so the log's rule does not require an entry.
If the planner wants the change recorded there as a note, this is the proposed text:

```
## 8. 2026-10-03: note on runs with no assessment (no prereg field changed)

- **Field:** none. `runs.population` is unchanged ("Intention-to-treat - every launched run counts").
- **What changed outside the prereg:** the agent's output schema has a fourth verdict label, `not_assessed`,
  set by code when a run produced no assessment (the deadline skipped or cut the assess stage, or the model
  declined it). Before, such a run reported `not_fit` at confidence 0.
- **Effect on scoring:** none on the primary metric. A not-assessed run has no findings, so it scores 0
  recall and is counted, as a crashed run is. `sit-eval score` records `inputs.verdict_label` and warns;
  `sit-eval aggregate` warns per run. The per-protocol view excludes such runs.
- **Effect on grading:** gate G4 (explicit verdict present) is false for such a run, so D2 is 0. Under the
  old placeholder the gate was true.
- **Reason:** `not_fit` read as a judgement of a design that nobody had assessed.
- **Who decided:** session-3 coordinator decision (HANDOVER_FULL §10), implemented in session 4.
- **Scored run already happened:** no frozen scored run. The three pilot runs on the first live run are
  unaffected (its verdict is `fit_with_conditions`).
```

## Merging with the keys work

While this branch was being built, the upstream branch `origin/claude/happy-darwin-d0bl94` gained 7 commits from the keys worker (`bf9fc63` to `2c7fba3`).
This branch does not contain them and was not rebased.
Both sides edit `README.md`, `spec/README.md` and `spec/validate_examples.py`.
A trial merge in a scratch clone (aborted afterwards, nothing written to the repository) merged automatically with no conflict.
On the merged tree: `make smoke` exit 0, `make test` exit 0 with 1018 passed, and `python3 spec/validate_examples.py` exit 0 with 37 negative and 29 adversarial cases.
The upstream commit `10ceb5a` also makes the spec validator skip `eval/blind/` unless `--include-blind` is given, which settles the first point of the edit log §7.

## For the next worker

- The demo measurement run (`docs/HANDOVER_FULL.md` §10 step 3) should be committed with its `llm.jsonl` and `state.json` so that `dra replay` has a live run to work on.
- That run also gives the first chance to see whether an Opus call can pass 64,000 output tokens, and what a truncation costs.
- `docs/BUDGET.md` and the cost lines of `eval/EVAL_PLAN.md` still carry the pre-measurement prices.
- Merge this branch with the keys work (see above); the trial merge was clean.
- `docs/HANDOVER_FULL.md` §10 still lists the six items as in flight.
