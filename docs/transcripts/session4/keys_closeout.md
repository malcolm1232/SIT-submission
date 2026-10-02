# Session 4: keys close-out report (decisions #21-#23, access log, validator default)

Date: 2026-10-03 (local, UTC+8); clock read 2026-10-02 19:34 UTC.
Worker: one fresh-context agent session on `claude-fable-5-1`, worktree `/Users/malco/Desktop/SIT-wt/keys`, branch `s4/keys`, starting at `5b464ba`.
Authority: the planner's brief, which gave rulings #21 and #22 as final (SIT FABLE for the owner, 2026-10-03) and the owner's own decision #23 verbatim.
This worker made no key decision of its own.
No model call, agent run, scoring run or grading run was made, and nothing was signed.

## Commits

- `10ceb5a` Spec validator: never read eval/blind unless --include-blind.
- `a8ec7ee` Create eval/blind/ACCESS_LOG.md with the session 4 entries.
- `9738dc1` Record decisions #21-#23 (the last commit that changed the sheet; its message carries the sheet hash).
- This report and the edit-log lines are in the commit after `9738dc1`.

## Decisions recorded

Row #21 (SIT FABLE for the owner, 2026-10-03) clarifies #20: a decision row is linked to a flaw when (a) the flaw's location cites the section that row governs and (b) the flaw's defect is in the subject that row decides.
Condition (a) alone is necessary, not sufficient, and the links on the sheet stand as drafted and verified, including the deliberate non-links in item 7.
The rule text is written verbatim in `docs/USER_DECISIONS.md` and next to item 7 on the sheet, where it replaces the one-condition wording.
None of the 31 links the one-condition wording would add was added, and no link was removed.

Row #22 (SIT FABLE for the owner, 2026-10-03) has two parts.
Part (i): rule #19 applies to flaws scored in `substance` mode; lakehouse F05 and F06 are scored in `all_of` mode, so their core insights stand as drafted and their c2 items stay `supporting`.
Part (ii): where the session record gives a "Keep" text, the core insight equals it exactly, and a figure a credit item needs lives in the credit item (applied to payments F04 in `5b464ba`).
It is written in `docs/USER_DECISIONS.md`, next to item 10 on the sheet, and in the lakehouse F05 and F06 entries of sheet section 5.
The accept boxes of F05 and F06 were left unticked, because the ruling says the core insights stand and does not name an accept of the whole row.

Row #23 (the owner, 2026-10-03) records the owner's words verbatim: `"judge: no" - it stays Anthropic-only, disclosed as a limitation.` and, a few minutes later, `btw, NO FOR NOW, later i might change my mind.`
Consequence as written: #16 stands for now, the second-provider path in the harness and prereg stays in place and switchable, nothing is removed, and it is revisited on the owner's word.

## Premises checked before writing

Lakehouse F05 and F06 carry no per-flaw override: the canonical lakehouse key has `scoring.default_credit_mode: all_of`, all 15 flaws carry `credit.mode: all_of`, and the converter sets the mode per item, not per flaw.
So part (i) of #22 was written.

Payments F15 -> AD-004 meets condition (b), on this reading of `design_v2.md`.
Section 9.4 says the global table exists "to support the regional recovery posture in Section 20" and that a merchant retry can be sent to the Jakarta cell.
Section 20.2 describes the warm standby API cell in ap-southeast-3 that Route 53 shifts merchant traffic to.
The v2 "Disaster recovery" row adds "warm API cell in ap-southeast-3".
F15's defect is that duplicates arriving in different regions can both acquire the lock, and a duplicate can arrive in a second region only because of that cell.
Condition (b) therefore holds through the two-region write topology, not through the lock, which is AD-006's subject (sheet item 13).
One nuance for the planner: the words "both writable" for the two replicas are in the v2 "Idempotency store" row (AD-006), while the "Disaster recovery" row contributes the second-region API cell that sends writes there.

## Access log

`docs/SEALING.md` §6 rules 4 and 6 call for the log, and `eval/blind/ACCESS_LOG.md` did not exist (only that one path was checked), so it was created.
Entry 1 is the keys reviewer's breach, copied from `research/audit/verify_key_signoff_s4_editlog.md`: a direct run of `spec/validate_examples.py` read the two held-out `answer_key.json` files and printed flaw counts only, and a scratch archive copied the folder's bytes and was deleted unopened.
Entry 2 was added by this worker about itself and was not in the brief: while changing the validator's default it read lines 1 to 130 of `spec/convert_answer_keys.py` and lines 215 to 229 of `spec/README.md`, which hold mapping constants and table rows describing the held-out items.
That is an exposure to derived copies outside `eval/blind/` under the prereg's `access_log_policy.exposure_entries`, not a read of a held-out file.
Nothing under `eval/blind/` was listed, opened, printed, copied or archived by this worker.
The log says that the earlier exposures listed in `docs/SEALING.md` §6 rule 4 and in the prereg's `prior_exposures_to_record` are not entered yet.
The log is written as one sentence per line, as the brief asked, not as the Markdown table with a frozen-prereg header that the prereg's `access_log_policy.format` describes; the prereg is not frozen.

## Validator default

`spec/validate_examples.py` run with no flags now takes the tier names from `eval/` and globs each tier except `blind`, so nothing under `eval/blind` is listed or opened.
`--include-blind` reads the held-out keys and prints one line on stderr saying the access must be recorded in `eval/blind/ACCESS_LOG.md`.
Abbreviated flags are refused (`allow_abbrev=False`), so `--inc` cannot switch the read on.
A `runpy` caller opts in with `init_globals={"INCLUDE_BLIND": True}`, and the caller's command line is never read.
`spec/convert_answer_keys.py` passes `INCLUDE_BLIND` only when the blind tier is converted, and keeps its glob filter as a second guard.
`tests/test_spec_validator_blind.py` (7 tests) runs a copy of the validator in a temporary tree whose `eval/blind` trips on any listing, stat or open.
Teeth: with a `cp` backup taken (sha256 `bd820b14...7520`), the default was flipped back (`held_out_skipped = False`) and the two default-run tests failed with "os.scandir() touched the held-out tier" (2 failed, 5 passed); the file was restored from the backup, compared with `cmp`, and 7 passed.
`spec/README.md` (file table, §2.8, §6) and the root `README.md` ("Reproducing checks") describe the new default.
The root `README.md` converter line now says `--tier synthetic`, because the converter without `--tier` reads the held-out keys.
The empty-cell marker in the two rows of the `spec/README.md` file table is now a plain dash, so no line this pass wrote carries the long dash.

## Open gap recorded, no code change

One line was added to `research/audit/verify_key_signoff_s4_editlog.md`: `sit_eval/scoring.py` only warns on `scored_run_ready: false` although prereg LC12 allows no scored run on such a key, and a later worker will make that a refusal with an explicit exploratory override.
A second line there says the reviewer's access is now entry 1 of the access log.
`harness/` was not touched.

## Gates (exit codes)

`.venv/bin/python spec/convert_answer_keys.py --tier synthetic --check --verify-anchors`: exit 0, "45 flaws converted across 3 keys; 0 key(s) failed validation", each key `scored_run_ready False`.
`.venv/bin/python spec/validate_examples.py` (new default mode): exit 0, "ALL CHECKS PASSED", 32 negative tests, 28 adversarial cases, INV-04 oracle 1 positive and 2 negative, three synthetic keys covered, "eval/blind not read".
`.venv/bin/ruff check agent harness tests`: exit 0 (`spec/` is excluded from lint in `pyproject.toml`).
`.venv/bin/pytest -q`: exit 0, 990 passed (983 plus the 7 new tests), 0 skipped, 0 failed.
Nothing is signed: every `signoff` block has `signed_by: null`, `signed_on: null` and `accepted: []`, and all three canonical keys say `scored_run_ready: false` with nine fields pending.
No file under `eval/synthetic/`, `agent/`, `harness/`, `config/` or `prompts/` differs from `5b464ba`.

## Hashes (sha256)

`eval/KEY_SIGNOFF.md` (the sheet, after this pass): b87e60fba8afeed7e3d24738775b126d4f2f4080abbd0dffb3934ce0e92d60dc.
`spec/convert_answer_keys.py`: ce2eff3382af27950ac05c71d73e74b177160ababf6a6d63ece97c6694cd120e (was 7986801c...; sheet section 9 re-hashed).
The six key hashes in sheet section 9 are unchanged and match the files.

## Not verified

- The converter's blind-tier call path (`--tier blind` or no `--tier`) was not run, because it reads the held-out keys; the opt-in through `init_globals` is covered only by the temporary-tree test of the validator.
- The `--include-blind` flag was run only in the temporary tree, never against the repository's `eval/blind`.
- Whether entry 1 of the access log counts against the S-heldout budget of 3 evaluations is not decided here.
- The 31-link count and its per-key split (12, 11, 8) are taken from the reviewer's report, not re-derived.
- The row-to-section reading behind "F15 meets (b)" is this worker's reading of three passages, not a key fact.
- Whether the external facts are true, and the harness under a frozen prereg with a signed key, remain unverified as in the reviewer's report.
