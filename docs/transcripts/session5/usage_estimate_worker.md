# Usage estimate of a cut call: worker report (3 Oct 2026)

## The rule
A model call that ended early reports no usage, so its output tokens are estimated.
The manifest now estimates them as the run's measured output rate times the call's wall seconds.
The rate is the median output tokens per second over the calls of the same run that reported usage (output tokens above 0, wall seconds above 0; unsent, faulted, replayed and fake calls left out).
When no call qualifies, or the cut call has no wall seconds, the logged constant-based figure is kept.
Each estimate row carries `output_basis` (`measured_rate` or `constant`) and `logged_output_tokens`.
`estimated_totals` gains `output_basis` (`mixed` when rows differ), `output_tokens_per_s` and `output_rate_calls`.
Measured totals never include an estimate, and the run stays a lower bound.

## Files changed
- `agent/sit_review_agent/manifest.py`: `measured_output_rate` and the replacement in `journal_usage` (checkpoint f613d9b, reviewed, no change needed).
- `tests/test_usage_estimate.py`: three new tests (f613d9b).
- `tests/test_manifest_concurrent.py`: only the expected figures of one test (8744f49).

## Tests
- `test_a_cut_calls_output_estimate_uses_the_runs_measured_output_rate`: rates 100 and 140 give median 120, times 200 s = 24000, basis `measured_rate`, logged 11600 kept, measured totals untouched.
- `test_a_cut_calls_output_estimate_falls_back_to_the_constant_without_measured_usage`: no qualifying call, basis `constant`, the logged 11600 stays.
- `test_replayed_faulted_and_timeless_calls_do_not_set_the_rate`: only the 50 tokens/s call counts, so the cut call of 100 s gets 5000.
- `test_a_cut_calls_estimate_sits_beside_its_measured_null_record`: the measured call runs at 5 tokens/s, so 850 per row and 1700 in total.

## Guard check
`journal_usage` was made to keep the logged figure (`if False and rate ...`), from a `cp` backup in the scratch folder.
Three tests failed: the measured-rate test, the replayed/faulted/timeless test and the concurrent manifest test.
The file was restored, `cmp` was clean, and the 14 tests of the two files passed again.

## Gates
- `ruff check agent harness tests`: `All checks passed!`
- `sit-review selftest`: `selftest passed in 0.4 s`
- Full pytest on the branch: `62 failed, 1841 passed, 1 skipped, 2 xfailed, 2 errors in 240.30s (0:04:00)`.
- The 62 failures and 2 errors are not from this fix: they come from a3ee771 (decision 40, six assess shard groups in `config/agent.yaml`), already on the branch before f613d9b.
- The synthetic runs key their fake assess answers to four shards (`SHARD_FINDINGS` in `tests/test_e2e_synthetic.py`), so a fifth shard raises `KeyError: 5`.
- With `config/agent.yaml` from 481cedb put back for the run only: `2 failed, 1903 passed, 1 skipped, 2 xfailed`, the 2 being `tests/test_config.py`, which a3ee771 updated for six groups.

## Not verified
- No live run: the rate has not been checked against a real run's log.
- The six-shard test breakage is left open for its own card: the synthetic fakes need answers for six shards.
