# Access log: eval/blind (S-heldout)

This log records accesses to the held-out items under `eval/blind/`, as `docs/SEALING.md` §6 rules 4 and 6 require.
It is append-only: existing lines are never edited, and new entries are added at the end.
The pre-registration (`eval/prereg.yaml`) is not frozen yet, so this log carries no frozen prereg hash.
As of 2026-10-03 the earlier exposures listed in `docs/SEALING.md` §6 rule 4 and in `eval/prereg.yaml` (`access_log_policy.prior_exposures_to_record`) have not been entered here yet.

## Entry 1: 2026-10-03, interim-rule breach by the session 4 keys reviewer

Date: 2026-10-03 Singapore time (2026-10-02, about 19:17 UTC).
Who: the session 4 keys reviewer, an Opus subagent (a fresh-context agent session on `claude-opus-5-5`) working on branch `s4/keys`.
What happened: it ran `spec/validate_examples.py` directly in the worktree, and the script's legacy-coverage check read the two held-out `answer_key.json` files (`eval/blind/item_a/answer_key.json` and `eval/blind/item_b/answer_key.json`).
A scratch copy of the tracked files, made with `tar` over `git ls-files` for a trial of the owner's signing step, also copied the bytes of this folder; that copy was deleted unopened.
What was seen: counts only, namely one flaw count per key in the script's output; no content of either key was shown to the session.
Runs launched: none; no agent run, scoring run, grading run or model call used these items.
Remedy: `spec/validate_examples.py` run with no flags no longer lists or opens anything under `eval/blind`; reading the held-out keys now needs the explicit flag `--include-blind`, which prints a notice that the access must be recorded here.
The default is pinned by `tests/test_spec_validator_blind.py`.
Source of this entry: `research/audit/verify_key_signoff_s4_editlog.md`, section "Interim-rule breach by this verifier", copied here on 2026-10-03 when this log was created.

## Entry 2: 2026-10-03, exposure through derived copies by the session 4 keys close-out worker

Date: 2026-10-03 Singapore time (2026-10-02, about 19:20 to 19:30 UTC).
Who: the session 4 keys close-out worker, a fresh-context agent session on `claude-fable-5-1` working on branch `s4/keys`.
What happened: while changing the validator's default it read lines 1 to 130 of `spec/convert_answer_keys.py` and lines 215 to 229 of `spec/README.md`, which hold mapping constants and table rows that describe the two held-out items.
What was seen: section labels and flaw identifiers of the held-out items in the overlap table and the overlap constant, and two one-line audit observations about one held-out item in the audit-observation constant.
Nothing under `eval/blind/` was listed, opened, printed, copied or archived; this file was created after checking only whether this one path existed.
Runs launched: none.
Kind: exposure to derived copies outside `eval/blind/` (`eval/prereg.yaml`, `access_log_policy.exposure_entries`), not a read of a held-out file.
Ruling, 2026-10-03 (SIT FABLE for the owner, `docs/USER_DECISIONS.md` #24): entries 1 and 2 do not count against the three-evaluation budget for the held-out set, because no agent output was scored against these items and only flaw counts were seen in entry 1; the same holds for entry 2.

## Entry 3: 2026-10-05, unintended programmatic read of the held-out keys by the item converter

Date: 2026-10-05 Singapore time, about 00:30 +08 (2026-10-04, about 16:30 UTC).
Who: the session 6 register-items worker, a fresh-context agent session working on branch `s4/register-items` while registering five new synthetic items.
What happened: it ran `python spec/convert_answer_keys.py --help` to read the usage; the script has no `--help` option, so it ran a full write-mode conversion across every tier, which read the held-out keys under `eval/blind/`, and it printed its notice that the access must be recorded here.
The intended run was the synthetic-only form, `--tier synthetic`, as in `docs/HANDOVER_261004_PLANNER.md` §7.
What was seen: nothing; no key content was printed to, read by or held in the context of any person or model.
Files changed: none; `git status` was clean afterwards, so no file under `eval/blind/` changed.
Runs launched: none; no agent run, scoring run, grading run or model call used these items.
Kind: interim-rule breach (`docs/SEALING.md` §6 rule 1, a script opened files under `eval/blind/`), recorded under §6 rule 6; programmatic, unintended, no exposure.
The pre-registration is still not frozen, so this entry carries no frozen prereg hash.
Source of this entry: `docs/transcripts/session6/register-items.md`, section "Incident", copied here on 2026-10-05.
