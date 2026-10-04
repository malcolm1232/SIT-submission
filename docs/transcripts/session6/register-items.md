# Worker note: register the five new synthetic items (2026-10-05)

Under the owner's word of 4 Oct 2026 22:40 ("yes" to plan D) and the planner's delegated shot calling (3 Oct 02:50).

## What was done

- Merged `s4/item-iot-fleet` (9d408ad), `s4/item-consent` (9311d3f), `s4/item-hospital` (1fa9fd0), `s4/item-ledger` (f7f4ac1) and `s4/item-exam` (5880599) into `s4/register-items`, no conflicts; `eval/synthetic/` lists eight items.
- Registered `iot_fleet`, `consent_service`, `hospital_scheduling`, `ledger_migration` and `exam_platform` in `spec/convert_answer_keys.py` (`ITEMS`, and `NEEDS_EXTERNAL` as iot_fleet {F03, F15}, consent_service {F05, F15}, hospital_scheduling {F06, F15}, ledger_migration {F05}, exam_platform {F05, F06}), in `eval/build_pdfs.py` (`ITEMS`; the docstring now says sixteen PDFs) and in the S-dev `items:` list of `eval/prereg.yaml` (path, item_id, documents).
- The converter in write mode (`--tier synthetic --verify-anchors`) left all eight canonical keys byte-identical: 120 flaws across 8 keys, 0 key(s) failed validation.
- `eval/build_pdfs.py --check`: ALL CHECKS PASSED for all sixteen PDFs.
- Pre-registration deviation: `eval/prereg_deviations.md` entry 13 (plan D).
- Decision: `docs/USER_DECISIONS.md` row 46.
- Leakage allow-list: no entry added. `scripts/leakage_grep.py` printed PASS on the first run with the eight items; the expected `never leave` hit did not appear, so nothing needed resolving.
- The public-snapshot exporter selects answer keys by glob (`eval/synthetic/*/answer_key*.json`), so it needed no item list change.

## Not changed

- `eval/prereg.yaml` beyond the items list: the S-dev `counts` line and the run counts in `conditions` and `stop_rule` keep their old text and are superseded by deviation 13.
- The item designs and keys were not read.

## Incident

- Before the registration run, `spec/convert_answer_keys.py --help` was run to read its usage; the script has no `--help` and ran a full write-mode conversion of all tiers, which reads the held-out keys under `eval/blind/` (it printed its access notice). No file changed (`git status -s` clean of keys) and no key content was printed to the worker. `eval/blind/ACCESS_LOG.md` was not edited by this worker; the planner decides whether to log it.

## Gates (last lines)

- `ruff check agent harness tests`: All checks passed!
- full suite from the worktree: 1977 passed, 1 skipped, 2 xfailed
- full suite from `~`: 1977 passed, 1 skipped, 2 xfailed
- `sit-review selftest`: selftest passed in 0.4 s
- `make smoke`: exit 0, 254 passed, 1 skipped
- `tests/robustness`: 161 passed
- `spec/convert_answer_keys.py --tier synthetic --check --verify-anchors`: 120 flaws converted across 8 keys; 0 key(s) failed validation
- `scripts/leakage_grep.py`: PASS: no unresolved hit in a gated area
- `python -m sit_review_agent.prompts --check`: PROMPTS.lock up to date (bundle 6f0ee28ab9ac)
- `tests/test_export_public_snapshot.py`: 65 passed
