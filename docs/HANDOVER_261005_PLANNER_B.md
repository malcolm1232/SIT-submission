SUPERSEDED by `docs/HANDOVER_261006_PLANNER.md` on 06 Oct 2026 14:40; read that file instead.
# SIT planner - handover, written 05 Oct 2026 15:45 +08 by the "SIT planner, 5 Oct afternoon" session

START HERE. This file is self-contained: a new session needs nothing else to continue.
To start the next session say: "Run git -C ~/Desktop/SIT fetch origin && git -C ~/Desktop/SIT show origin/claude/happy-darwin-d0bl94:docs/HANDOVER_261005_PLANNER_B.md, read that output as the SIT planner handover, and continue as the SIT planner; you spawn Opus workers and make the calls; the answer-key signatures, the held-out items, the money above plan D and anything that needs the SIT MCP key stay Malcolm's."
Supersedes: `docs/HANDOVER_261005_PLANNER.md` (written 09:20 the same day; its sections 4 to 10 are carried forward here in shorter form; its items 3 and 5 are done; its items 1, 2, 4, 6, 7 are items 4, 5, 6, 7, 8 below).
This file is committed on the truth branch, so the `git show` form works; `~/Desktop/SIT` is checked out on an older branch and never holds it.
All times are Singapore time (+08).

## 1. Goal and where it stands

Malcolm's words, 3 Oct 2026 02:50: "you are fable now, u delegate tasks to opus agents to do? u can spawn them if youd like. and u make the shot calling, ok? u have explicit permission to shot call."
The product is a design-document review agent for the SIT AI Engineering Lab Exercise (brief `~/Downloads/AI Engineer Lab Exercise.pdf`: a live run on a document SIT hands over, a re-assessment of an updated artefact, an on-the-spot modification, submission through a private GitHub repository) plus a research-grade evaluation harness.
Truth branch `origin/claude/happy-darwin-d0bl94`, tip 5ca659a (2032 tests passing, every gate of section 7 green at that tip).
Plan D (exploratory, keys unsigned) is complete and written up in `docs/COMPARISON_PLAN_D.md`: agent 98 of 112 planted flaws against 88 of 112 for a single call on eight documents, 0 hallucination flags, grades all B PASS; its v2 numbers describe a refine fallback defect, now fixed, not the agent.
Done this session (all on the tip): the refine prior-status fix (cards A1 and A2), the scorer condition guard, the v2 metrics fix (A4), the B0 verdict wording, the scorer refine-fallback warning (A5).
In flight: three branches stalled on a stream watchdog (no safeguard, no error of theirs), each with work on disk, listed in the table and in items 1 to 3; no server and no run is active.
Next: finish the three stalled branches (items 1 to 3), then his second rehearsal (item 4) and its measurement (item 5), then the v2 reruns on his money word (item 6).

| Step | What | Branch, worktree under `~/Desktop/SIT-wt/` | Tip | State |
|---|---|---|---|---|
| A | Refine keeps a rule-clean answer whose only gaps are prior statuses (A1) | merged | 5819a6d | on the tip |
| B | Refine fallback merges drafts with the same prior id (A2) | merged | c1409dd | on the tip |
| C | `sit-eval score --condition` must match the manifest | merged | 0dd8fa4 | on the tip |
| D | v2 metrics read the prior table (A4) | merged | a3ecdef | on the tip |
| E | B0 verdict wording | merged | 51946a9 | on the tip |
| F | Scorer warns and records a refine fallback (A5), status-only repair excluded | merged | d25f2bb, de7a4f0 | on the tip |
| G | INV-05 three edges (E1 quote cut inside a URL, E2 URL across lines, E3 redaction inside a non-exempt quote) plus the verifier's leak fix 4b85b5a | `s4/inv05-edges`, `inv05-edges` | 3224fed | VERIFIED (probes P1 to P5, E3 mutation killed), gates green after the merge of 5ca659a, NOT pushed (item 1) |
| H | A3 a resolved prior is a prior-table row only, decision row 47 | `s4/a3-resolved-prior`, `a3-resolved-prior` | 9e019bd | verifier stalled mid-mutation, tree clean, NOT pushed (item 2) |
| I | Scorer refuses when manifest.json and the report disagree on the condition | `s4/score-manifest-disagree`, `score-manifest-disagree` | 1a7220b | planner WIP checkpoint, untested, NOT pushed (item 3) |

## 2. Do this next

Mechanics first.
"Item" means this list; "step" means the table in section 1; "A1" to "A5", "INV-nn", "#nn" are the repo's own names (cards of `docs/transcripts/session6/v2-diagnosis.md`, an invariant of `agent/sit_review_agent/invariants.py`, a row of `docs/USER_DECISIONS.md`).
Section 3 runs before item 1; its commands are read-only and the planner runs them itself.
Editing, testing, running the agent, scoring and `kill` are workers' work, with one exception: the planner may `git add` and commit a stopped worker's uncommitted edits as a WIP checkpoint in that worker's worktree; never `checkout` or `pull` in `~/Desktop/SIT`.
Malcolm is reached with the PushNotification tool (one line, under 200 characters) whenever his word, his Terminal or his money is needed; his answers are recorded by a worker as the next rows of `docs/USER_DECISIONS.md` (48 onward; row 47 belongs to the A3 branch of item 2 even before it lands) with his words.
There is no board for SIT: a card is an entry in this file, recorded by its worker note under `docs/transcripts/session7/` (6 notes on the tip, more on the three branches) and its commit.
The planner (Fable this session) spawns one Opus worker per deliverable with the Agent tool (`model: "opus"`), a separate fresh-context verifier per code deliverable, and reads only their reports.
A worker stopped by the model safeguard (`reasoning_extraction`) is respawned ONCE after a planner checkpoint commit of its edits, and the retry is MECHANICAL: a brief that forbids opening the source files, runs the tests and gates from tool output only, and commits; this closed three stopped items on 5 Oct 2026 (steps A, E, and the gates of H), a content retry on Fable did not (section 8).
Items 1 to 3 run ONE AT A TIME in that order, not in parallel: all three push to the truth branch, and items 1 and 2 both change `agent/sit_review_agent/phases/report.py` (item 1 its `_redact`, item 2 its `_delta_table` and the verdict path).
Once this handover's commit is on the tip, no push of those branches is a fast-forward any more: the normal path is merge the tip (clean only), rerun ruff, the full suite and selftest, push; a conflict is reported to the planner with file and hunk, and the planner rules and respawns; `--force` is never used.
The PushNotification tool may be absent from a session's tool list; then the question goes in the chat and the planner works the items that need nothing from him.
A worker stalled by the stream watchdog ("no progress for 600s") is simply respawned with the same brief plus the state on disk; it is not a safeguard stop.
Worker cap: three at once (the QM orchestrator's line of 05 Oct 05:27 "all the Mac's test slots are yours until he says otherwise"); every worker checks the load before a test run (section 6).
Commits carry `malcolm1232 <66200354+malcolm1232@users.noreply.github.com>` (`git -c user.name=malcolm1232 -c user.email=66200354+malcolm1232@users.noreply.github.com commit`) and never a co-author or agent line; scoped `git add` only; no em dash anywhere.
Who pushes: code by its verifier after the gates and a mutation; a wording-plus-tests or harness-guard change by its builder after the gates; a docs record by its cold reader after recomputing every number.
A verifier pushes with `git -C ~/Desktop/SIT-wt/<name> push origin HEAD:claude/happy-darwin-d0bl94`; if refused as non-fast-forward it merges `origin/claude/happy-darwin-d0bl94` into its branch (clean only; a conflict is reported to the planner), reruns ruff, the full suite and selftest, and pushes again; never `--force`.
The suite count grows with every change: a verifier expects "the tip's count plus the change's own tests", never a fixed number (2032 at 5ca659a).
Live model runs cost his Max subscription (CLI estimates: an agent run $5 to $8, a B0 run about $0.80, a scoring $3.50 to $16, a grade about $5); plan D spent about $345 of the $350 to $400 he approved on 4 Oct 22:40; every further live run needs his word first (item 6), the rehearsal is his own run.
A run-id is never reused: a rerun gets the next suffix.
The subscription has a rolling session limit ("You've hit your session limit", exit 3, `LLMUnavailableError`): a worker that sees it stops, writes the reset time in its table, reports; runs resume with `sit-review resume <run dir>`.

1. Push step G (INV-05 edges), one mechanical Opus worker: worktree `~/Desktop/SIT-wt/inv05-edges` at 3224fed, tree clean, history: the builder's three edge commits b5a1533, a9ccb16, b51de7a and note 33e5c27; the verifier's leak fix 4b85b5a ("INV-05 never joins two URLs on adjacent lines into a third", with `test_inv05_two_document_urls_on_adjacent_lines_never_join_into_a_third`); the verifier's note b20a894 whose last section records probes P1 to P5 passed, the E3 mutation killed and gates `2024 passed, 1 skipped, 2 xfailed` before the merge; then 3224fed, a clean merge of the tip 5ca659a, after which the verifier reported "gates green" and stalled.
   The worker: `git -C ~/Desktop/SIT-wt/inv05-edges status -s` clean; read with the Read tool only the last 8 lines of `docs/transcripts/session7/inv05-edges.md` and confirm the "Verifier" section says P1 to P5 passed (if it does not, stop and report: a verifier, not a push, is then owed); `git -C ~/Desktop/SIT fetch origin`; `git -C ~/Desktop/SIT-wt/inv05-edges merge origin/claude/happy-darwin-d0bl94` (the tip is this handover's docs-only commit, the merge is clean); load check; `.venv/bin/ruff check agent harness tests`; the full suite from the worktree, expecting 2032 plus the branch's own tests (`( cd <wt> && .venv/bin/pytest --collect-only -q 2>&1 | tail -1 )` gives the exact total; no `failed` or `error`); `env -u ANTHROPIC_API_KEY .venv/bin/sit-review selftest`; `.venv/bin/python scripts/leakage_grep.py` PASS; then `git -C ~/Desktop/SIT-wt/inv05-edges push origin HEAD:claude/happy-darwin-d0bl94`.
   Done when `git ls-remote origin claude/happy-darwin-d0bl94` equals the worktree HEAD.
   What the change does (for the record, not for re-review): E1 a quote that is a contiguous run of document text is not scanned for URLs; E2 `allowed_urls` accepts a URL the document breaks across lines, and never joins two different URLs on adjacent lines; E3 `_redact` redacts a disallowed URL inside a quote INV-05 does not exempt, and still fails closed when the excerpt URL is itself not allowed (`test_inv05_made_up_url_in_a_made_up_anchor_never_reaches_the_report` unchanged); two old tests renamed to the redaction behaviour; `docs/ARCHITECTURE.md` and `docs/EXPLAIN_AS_IT_RUNS.md` updated.
   The verifier left two residuals, NOT fixed, which become item 9: a URL at a line end still joins the next line's first word (so `https://a.example/xfor` counts as allowed), and `quote_in_document` checks a quote's URL as a prefix of ANY document URL, not the one at the quote's position.
2. Finish step H (A3), one fresh Opus verifier: worktree `~/Desktop/SIT-wt/a3-resolved-prior` at 9e019bd (b975a2e code, 6c213ae decision row 47, 8bc98dc gates note, 9e019bd the first verifier's extra test "a less fixed prior status stands, a withdrawal gives..."), tree clean, based on 7fad84e; if `status -s` is NOT clean, a stalled mutation is on disk: `git -C ~/Desktop/SIT-wt/a3-resolved-prior checkout -- .` first.
   Runs after item 1 has pushed, so its merge brings step G in.
   The first verifier reported mutation 1 (disable the split) killed and stalled while applying mutation 2 (ignore the less-fixed-stands rule); its review lines and probe results are lost with it, so the new verifier redoes the review: read `git diff 7fad84e..HEAD -- agent tests docs/USER_DECISIONS.md`, judge the split happens before the verdict call, `st.prior_statuses` gets the note and a less fixed existing entry stands, dangling ids are removed from unresolved items, sound-area evidence, verdict text and the `cited` set, the Review validator (`models.py` about 805 to 815) still holds, a non-delta run is unchanged; probes (two resolved carriers plus one new finding; a resolved carrier whose prior already has a still_open refine status; a non-delta run); both mutations; the gate chain of section 7; merge the tip (after item 1 it holds step G, which also touches `phases/report.py` in `_redact`; a conflict is reported with file and hunk, not resolved); the expected suite count is the tip's count plus the branch's own tests, and `pytest --collect-only -q | tail -1` on the merged tree gives the exact total (the branch adds `test_a_resolved_prior_is_a_table_row_not_a_finding`, `test_a_still_open_carrier_keeps_the_row_open_when_another_is_resolved` and the first verifier's test from 9e019bd); add a verified line to `docs/transcripts/session7/a3-resolved-prior.md`; push.
   The intended change, for the review: a current finding whose reassessment status is RESOLVED becomes a `PriorStatusDraft(prior_finding_id, resolved, note)` in `st.prior_statuses` and is dropped from the findings before the verdict call and before `assemble_review`; ids are kept; the prior row then has `finding_ids=[]`, `re_examined=True`; where another carrier of the same prior is still open, that carrier stands; the assess prompt and `ReassessmentStatus` are unchanged; for agent output the v2 metrics then come from the prior-table branch of `harness/sit_eval/metrics.py` (needs `--prior-scores`).
   Done when pushed and `ls-remote` matches.
   If this verifier is stopped by the safeguard: checkpoint its disk, respawn ONCE with the same brief plus its notes; if stopped again, a mechanical worker (no source reads) runs the gate chain and pushes, and the note records "one review lost to the safeguard; mutation 1 killed by the first verifier; mutation 2 and the probes not run" so the next live run is read with that in mind.
3. Finish step I, one Opus worker: worktree `~/Desktop/SIT-wt/score-manifest-disagree` at 1a7220b, which sits directly on 5ca659a (a planner checkpoint of untested edits in `harness/sit_eval/cli.py`, `harness/sit_eval/scoring.py`, `tests/eval_harness/test_eval_score_condition.py`; the builder stalled after "Now the guard change").
   The rule: `sit-eval score` WITHOUT `--condition`, when `manifest.json` and the report's `run_manifest` are both present, non-null and different, refuses the way `check_condition` does (exit 2, one line naming both files and values, before `out_dir.mkdir` and `build_judge`); one copy null or missing behaves as before; with the flag unchanged.
   The worker reads the diff `git diff 5ca659a..HEAD`, completes or corrects it, runs the three tests named in the rule (disagreement refuses with no out folder, agreement scores, one null scores), ruff, the suite (the tip's count plus the three tests; `pytest --collect-only -q | tail -1` gives the total), selftest, `make smoke`, a mutation (disable the refusal), then `reset --soft 5ca659a` (safe: 1a7220b is the only commit above it) and one proper commit "sit-eval score refuses a run whose manifest.json and report run_manifest disagree on the condition", a note `docs/transcripts/session7/score-manifest-disagree.md`, merge the tip (after items 1 and 2), rerun ruff, the suite and selftest, then `git -C ~/Desktop/SIT-wt/score-manifest-disagree push origin HEAD:claude/happy-darwin-d0bl94` (a harness guard plus tests: the builder pushes).
4. The second rehearsal, started by Malcolm (the live proof of the refine fix, the report crash fixes and, once item 1 lands, the INV-05 edges).
   The worktree `~/Desktop/SIT-wt/demo6` is at 880fac8 and holds the venv, `runs/input/sit_sample_v1.pdf` and his first run `runs/ui-261004-034213-c5cb`; the tip has moved with CODE since, so a worker first runs `git -C ~/Desktop/SIT-wt/demo6 merge --ff-only origin/claude/happy-darwin-d0bl94` (after items 1 to 3 are pushed, and after `pgrep -fl 'dra ui'` shows no server from demo6), then `( cd ~/Desktop/SIT-wt/demo6 && .venv/bin/pip install -e '.[dev,langgraph]' -q && env -u ANTHROPIC_API_KEY .venv/bin/sit-review selftest )` prints `selftest passed`.
   The Mac rebooted at 12:34 on 5 Oct: his old demo4 server (pid 5237, port 8791) is gone, no Ctrl-C is needed.
   His part, two lines in a Terminal window: `read -rs SIT_MCP_API_KEY && export SIT_MCP_API_KEY`, then `cd ~/Desktop/SIT-wt/demo6 && env -u ANTHROPIC_API_KEY .venv/bin/sit-review preflight --warm --profile demo && env -u ANTHROPIC_API_KEY .venv/bin/dra ui --host 0.0.0.0 --allow-remote --port 8791 --runs-dir runs`, wait about 90 s, open `http://127.0.0.1:8791/`, pick `runs/input/sit_sample_v1.pdf`, tick every tool, start.
   The planner's part: give him those lines when he asks, wait for his word that the run ended, never kill a server on port 8791; "the key is rejected" means the SIT MCP key, which preflight reports.
   Done when he says it finished; the run folder is the newest under `~/Desktop/SIT-wt/demo6/runs/` other than `input` and the first run.
   If it crashes: the page shows the error and `sit-review resume <run dir>` continues from the last checkpoint; a worker diagnoses from the run's logs by script (counts and messages, never finding text); a second attempt is his; a `StageCrash` in report goes to a fix worker before any further live run.
5. Measure that run, one Opus worker after item 4, briefed with the facts inline (never pointing it at `docs/live_runs/`): the six checks of the 4 Oct measurement (stage 1 at or under 230 s with six shards; refine applied in full or its returned revisions applied; external evidence cited by findings; `extra.tools.session_reopens` present; "Tools used" names only servers called; `output_basis` on calls that ended early) plus three more, nine checks in all: `cli_answer_rejections` in `llm.jsonl` (counts and rule names only); no `StageCrash`; the degradation list has no refine fallback entry (new this session; if it has one, the run is read as a fallback run and the refine fix gets a diagnosis worker).
   Expected against the first run: stage 1 at or under 230 s (was 265), every merged finding refined (the first run merged 55 and refined 4), at least one external ledger entry cited (the first run had 41 entries and 0 cited).
   A failed check becomes a fix with its own worker, spawned without asking (his word of 3 Oct 22:55 "fix what u need to fix").
   The worker inspects `llm.jsonl`, `progress.jsonl` and `tools.jsonl` only by a script it writes that prints call ids, phases, outcomes, durations, token counts and rule names; `llm_calls.json` is that script's summary with no text field; the planner reads only the worker's report and the committed `MEASUREMENT.md`.
   The record goes to `docs/live_runs/sit_sample_ui_3/` with the same file names as `sit_sample_ui_2` (read on 5 Oct: `MEASUREMENT.md`, `anchors.json`, `checkpoints/01-ingest.json` to `08-report.json`, `effective_config.json`, `ledger.json`, `ledger.jsonl`, `llm_calls.json`, `manifest.json`, `report.json`, `report.md`, `shards/01-intent_and_fitness.json` to `06-security_and_failure.json`, `state.json`, `text/DOC-sit_sample_v1.pages.txt`, `text/DOC-sit_sample_v1.sections.json`, `tools.jsonl`, `tools_list.jsonl`, `ui/launch.json`; no raw `llm.jsonl`); `scripts/leakage_grep.py` PASS before the commit; a cold reader recomputes the numbers, fills the four `[TO FILL FROM REHEARSAL 2]` lines of `docs/EXPLAIN_AS_IT_RUNS.md` (stage 1 seconds; refined count; external cited; wall time and cost on one line) and pushes.
6. The v2 reruns on the fixed code, only after items 1 to 3 are on the tip AND his word on the money (section 5 point 1): four v2 runs at about $7 each, their scorings $5 to $12 each under the $24 cap, one hospital FULL run plus scoring, about $92 in all, the worker stopping at $110; plus, cheap through the judge cache, a rescore of the two already scored v2 runs with `--prior-scores`.
   Where: the worker fast-forwards `~/Desktop/SIT-wt/plan-d-runs` (`git -C ~/Desktop/SIT-wt/plan-d-runs merge --ff-only origin/claude/happy-darwin-d0bl94`; if `status -s` is not clean it reports and stops; `runs/` is ignored and stays), reinstalls the venv (`pip install -e '.[dev,langgraph]'`), runs from that worktree so the relative paths hold.
   Existing folders under `~/Desktop/SIT-wt/plan-d-runs/runs/` (from `docs/live_runs/plan_d/RUNS.md`, read on 5 Oct): `d_<x>_v1_1` for all eight documents; `d_<x>_v2_1` for payments, clinical, lakehouse, iot (payments and clinical scored; lakehouse and iot scorings stopped on the $18 cap) and consent (crashed in report twice on the old code, not in this round); `d_hospital_v1_1` (crashed) and `d_hospital_v1_2` (scored on the old code); the worker lists the folder first and picks the next free suffix if a name is taken.
   Runs, one at a time: `env -u ANTHROPIC_API_KEY .venv/bin/dra review eval/synthetic/<folder>/design_v2.pdf --profile demo --no-tools --previous runs/d_<x>_v1_1 --run-id d_<x>_v2_2` for (folder, x) in (payments_orchestration, payments), (clinical_rpm, clinical), (research_lakehouse, lakehouse), (iot_fleet, iot); and `env -u ANTHROPIC_API_KEY .venv/bin/dra review eval/synthetic/hospital_scheduling/design_v1.pdf --profile demo --no-tools --run-id d_hospital_v1_3`.
   Scoring after each run: `.venv/bin/sit-eval score runs/<run-id> --key eval/synthetic/<folder>/answer_key.canonical.json --out runs/<run-id>/eval_d --judge claude_code --model claude-opus-5-5 --effort high --samples 3 --seed 20261002 --concurrency 4 --max-cost-usd 24 --candidate-rule shortlist_bounded --no-grounding-judges --exploratory` (`--effort high` here is the JUDGE's effort, decision #33 is about the agent), and for a v2 run ALSO `--prior-scores runs/d_<x>_v1_1/eval_d/scores.json` (new this session: without it the two re-assessment metrics are null with a reason; the worker checks that path exists first and reports if the v1 scoring lives elsewhere).
   The rescore of the old v2 runs: `d_payments_v2_1` and `d_clinical_v2_1` with the same command plus `--prior-scores`, `--out runs/<run-id>/eval_d2` (a new out folder, never reuse), cache hits cost nothing.
   The scorer now prints a warning and writes `inputs.refine_fallback_recorded` when a run recorded a refine fallback; the worker records that column in its table.
   Spend: each run's `manifest.json` carries the CLI's cost estimate (the RUNS.md "cost USD (lower bound)" column) and each scoring prints its total; the worker keeps a running sum in its table after every run and scoring and stops at $110.
   Rows go to `docs/live_runs/plan_d/RUNS.md` in its existing columns (one worker owns that file); then a worker updates `docs/COMPARISON_PLAN_D.md` sections 6 and 7, and a cold reader recomputes the numbers and pushes.
7. Freeze and re-record before submission (unchanged): an annotated tag `demo-freeze` on the tip of that moment, pushed by its verifier, the demo-day runs re-run at that commit (the SIT sample with tools from his Terminal; `eval/synthetic/payments_orchestration/design_v1.pdf` then `design_v2.pdf` with `--previous`; about $25, his word), `docs/REPRODUCIBILITY.md` and the README replay recipe updated; after items 1 to 6 and his answers to section 5 points 3 and 5.
9. INV-05 residuals from step G's verifier (after item 1 lands), one Opus builder then a probing verifier: (a) a URL at a line end must not join the next line's first word into an allowed URL (at 3224fed `https://a.example/xfor` counts as allowed when the document has `https://a.example/x` at a line end followed by `for`); rule: a line-end join is accepted only when the joined text matches a URL that appears whole elsewhere in the document, a tool result or a ledger `url_or_citation`, or when the next line's fragment itself looks like a URL path or query continuation and no word of the document's running text starts it; the verifier probes the `xfor` case and a legitimate break (`https://a.example/long-` then `path`) and greps report.json and report.md for the joined host; (b) `quote_in_document` must check a quote's URL against the document URL at the quote's own position, not as a prefix of any document URL; both with tests, mutations, the gate chain of section 7, a verifier that pushes.
8. Submission rows that are his (read on 5 Oct from `docs/SUBMISSION_GAPS.md`, 26 rows): row 1 collaborator invites `SIT-calebying` and `Makienhui-sit` (Missing; he invites under Settings > Collaborators, the date goes in the README); row 2 ADR-005 repository privacy ("Awaiting user"; his ruling before any access is granted, history cannot be rewritten after); row 24 demo-day prerequisites (tag, frozen run, two backups; comes with item 7).

## 3. Check these facts first

| Command | Expected on 05 Oct 2026 15:45 | If different |
|---|---|---|
| `git -C ~/Desktop/SIT fetch origin; git -C ~/Desktop/SIT log --oneline -1 origin/claude/happy-darwin-d0bl94` | this file's handover commit above 5ca659a | anything else above 5ca659a: `git -C ~/Desktop/SIT log --oneline 5ca659a..origin/claude/happy-darwin-d0bl94`; read the notes under `docs/transcripts/session7/` |
| `git -C ~/Desktop/SIT-wt/inv05-edges log --oneline -1; git -C ~/Desktop/SIT-wt/inv05-edges status -s` | `3224fed Merge ...`, empty status | pushed already: item 1 is done; dirty: a worker reads the diff first |
| `git -C ~/Desktop/SIT-wt/a3-resolved-prior log --oneline -1; git -C ~/Desktop/SIT-wt/a3-resolved-prior status -s` | `9e019bd Test split_resolved ...`, empty status | dirty: a stalled mutation is on disk, the verifier restores with `git checkout -- <file>` before anything else |
| `git -C ~/Desktop/SIT-wt/score-manifest-disagree log --oneline -1` | `1a7220b WIP, planner checkpoint ...` | moved: read its note |
| `git -C ~/Desktop/SIT-wt/demo6 rev-parse --short HEAD; ls ~/Desktop/SIT-wt/demo6/runs/` | `880fac8`; `input` and `ui-261004-034213-c5cb` | a third folder is his second rehearsal: item 5 can start; a newer sha: a worker already fast-forwarded it |
| `pgrep -fl 'dra ui' \| cut -c1-60` | none | a server on port 8791 is his even when no rehearsal was announced, never killed, ask him; a server on another port whose cwd (`lsof -p <pid> \| grep cwd`) is a worker worktree is killed by pid only after that worker reported or is known gone |
| `git -C ~/Desktop/SIT show "origin/claude/happy-darwin-d0bl94:docs/USER_DECISIONS.md" \| grep -c '^| [0-9]* |'` | 46 (47 once item 2 lands) | more: read the new rows |
| `git -C ~/Desktop/SIT show "origin/claude/happy-darwin-d0bl94:eval/prereg_deviations.md" \| grep -c '^## [0-9]*\.'` | 14 | more: read the new entry |
| `git -C ~/Desktop/SIT ls-tree -r --name-only origin/claude/happy-darwin-d0bl94 docs/transcripts/session7/ \| grep -c '\.md$'` | 6 (9 once items 1 to 3 land) | more: read the new notes |
| `git -C ~/Desktop/SIT show "origin/claude/happy-darwin-d0bl94:eval/blind/ACCESS_LOG.md" \| grep -c '^## Entry'` | 3 | 4 or more: someone touched the held-out items; read the entry |
| `uptime; memory_pressure \| tail -1` | the second load number under 10; the line `System-wide memory free percentage: NN%` with NN over 35, before any test run | higher: QM lanes are running again; wait, and drop the worker cap to two |

In zsh write `"${B}:eval/..."` with braces: `$B:e` is a history modifier and eats the `:e` (bit this session).

## 4. His decisions (do not re-ask)

All in `docs/USER_DECISIONS.md` rows #17 to #46 on the tip, #47 on the A3 branch (his own, and the planner's rulings under his delegation, each row saying which).
03 Oct 02:50: the planner makes the calls; 02:55 "u can do whatever while im gone, if need my permision, build the rest first and when im back, u can ask me"; 22:55 "fix what u need to fix".
03 Oct: judge Anthropic-only (#23); effort medium default, high the ablation arm (#33); the 540 s deadline configurable (#34); no answer key for the SIT sample (#35); review outputs Download, Email, wifi share link, no hosted link (#36); UI shape the DBSearch idiom with the rail (#41).
04 Oct: the live view (#44), the zip of eight parts plus the sidebar page (#43), the "What is happening" panel (#45) and `docs/EXPLAIN_AS_IT_RUNS.md`.
04 Oct 22:40: plan D, "just 10 documents is enough", "less runs, but more variants document wise", "all using medium" (#46, deviation 13); "no langchain, right?" "Right": the LangGraph arm is separate and unfunded.
05 Oct (this session), his words at the start: "i think we doing testing for sit, can we continue?" and at the close "is ok , /saveconvo sit, and write /handover note."; he gave no money word and no ruling on anything else.
Planner rulings under his delegation this session, standing unless he reverses them: the refine degradation text does not list the missing prior ids because the delta table names them (an assertion clause was removed, not the code); card A3 lands before the v2 reruns so the reruns measure the final output shape (row 47); a status-only repair failure is not a refine fallback for the scorer's warning.
Older planner rulings standing: the early-end rule is off for calls with tools; B0 attempt counts are disclosed; the two held-out items were not run in plan D (deviation 14); a URL counts as ledger-backed only when it is in the document text, a tool result or a ledger `url_or_citation`, never a doc excerpt; the demo start line with `--host 0.0.0.0 --allow-remote` is his to type, not written into the runbook.

## 5. Open with him

1. Money for item 6: about $92 (four v2 runs, their scorings, one hospital run and scoring), worker stop at $110, plus the near-free rescore; recommendation yes, because SIT's day includes a live re-assessment and the current v2 numbers describe the old fallback.
   Asked twice on 5 Oct (chat and a Terminal notification); no answer yet.
2. The second rehearsal (item 4): his three Terminal lines are in item 4; it proves the fixes live and fills the study sheet.
3. Sign the answer keys: ten keys (`eval/synthetic/*/answer_key.json`, `scored_run_ready: false` on all); the one-liner is in `eval/KEY_SIGNOFF.md` section 10; recommendation: sign the eight synthetic ones; the two held-out ones are point 4.
4. The held-out items: whether the converter's unintended programmatic read of 5 Oct (`eval/blind/ACCESS_LOG.md` entry 3, no exposure) counts against the three-evaluation budget (recommendation: no), and whether to spend one evaluation now or keep them for the frozen stage (recommendation: keep).
5. The plan letter A ($3,282), B ($1,506) or C ($801) for Tier A: recommendation C only if he wants the pre-registered power analysis; otherwise plan D plus item 6 is the submission's evidence.
6. The LangGraph arm on the same eight documents, about $120: his "if I have time" of 4 Oct; recommendation yes before the interview, in a quiet window.
7. The SIT email, the two GitHub invitations (item 8 row 1), ADR-005 (item 8 row 2), the submission deadline and the interview date (nothing in the repo holds them; they set the priority of items 6 and 7).
8. Review email on or off (`config/ui.yaml`, password in `SIT_UI_SMTP_PASSWORD`); off as shipped.
9. The demo start line with the share flags in `docs/DEMO_DAY_RUNBOOK.md` (his edit or his typing on the day).
10. A ledger field marking a doc excerpt that came from a model anchor (spec change; traceability only).
11. A structured report field for a refine fallback, so the scorer's warning (step F) stops depending on the agent's wording; small design change, recommendation yes after item 6.

## 6. Rules of this work

The planner never reads source, edits, tests, runs the agent or scores; one Opus worker per deliverable, a fresh-context verifier per code deliverable, briefs with the facts inline; at most three SIT workers (two if QM lanes run again); a worker reads `uptime` and `memory_pressure` before every test run and tests only under a 5-minute load of 10 with free memory over 35 percent.
Workers keep every recorded model transcript (`llm.jsonl`, `progress.jsonl`, judge logs, stream fixtures, `ui/chat.jsonl`, `report.json` finding text) out of their context and inspect them by script that prints ids, counts, durations and metric values.
A brief never points a worker at `docs/live_runs/`, `docs/transcripts/` (other than its own card's note) or `llm_calls.json`; the planner reads the record and inlines the counts.
Security flaws in synthetic items and in any brief are written as missing or broken controls, never as a procedure.
The SIT MCP key is only ever in Malcolm's Terminal; every with-tools run is started by him; evaluation runs use `--no-tools`.
No agent run touches `eval/blind/`; `spec/convert_answer_keys.py` is run with `--tier synthetic`.
The synthetic answer keys are unsigned; the harness refuses a scored run without `--exploratory` (#26); only Malcolm signs.
The public snapshot never carries `eval/blind/`, answer keys, transcripts, raw model logs, the lab's documents, the probe results or the plan D tables; refresh only with `scripts/export_public_snapshot.py`; a refresh still fails its scan on 12 older findings (emails in the planner handovers, a home path, oauth words in four synthetic designs, token64 in tests) that must be resolved first; touching a synthetic design is an evaluation-item change and needs a deviation entry.
Billing: every model call goes through `claude -p` on his Max subscription; no Anthropic API key is set; `env -u ANTHROPIC_API_KEY` on every run.
Every Bash call of a worker is one purpose; pytest with `--tb=line -p no:warnings 2>&1 | tail -N`; absolute paths; no `cd` in a compound command except a whole-call subshell; a refused call is never resent; a bare `sleep` is refused, wait with an `until` loop on the load.
Other sessions: QM planner sessions message this one through Claude Code's cross-session messages (`ListAgents`, `SendMessage`); their all-clear on load is a condition, never a permission.
At the close the planner updates `~/.claude/projects/-Users-malco/memory/project_sit_design_review_agent_261003.md` and its `MEMORY.md` line, writes the next handover, then runs `/saveconvo SIT --agents` last.

## 7. How to verify a change

From a worktree with its venv (`/opt/homebrew/bin/python3.13 -m venv .venv && .venv/bin/pip install -e '.[dev,langgraph]' && .venv/bin/playwright install chromium`; `pip install markdown` for `eval/build_pdfs.py`), one command per call, exit codes read:
1. `.venv/bin/ruff check agent harness tests` prints `All checks passed!` (never `ruff check .`).
2. `( cd <worktree> && .venv/bin/pytest -q --tb=line -p no:warnings 2>&1 | tail -2 )` prints `2032 passed, 1 skipped, 2 xfailed` at 5ca659a (plus the change's own tests) with no `failed` or `error` word.
3. The same from `~` (`( cd ~ && <worktree>/.venv/bin/pytest -q --tb=line -p no:warnings <worktree> 2>&1 | tail -2 )`).
4. `( cd <worktree> && env -u ANTHROPIC_API_KEY .venv/bin/sit-review selftest )` prints `selftest passed`.
5. `( cd <worktree> && make smoke )` exits 0 (256 passed, 1 skipped).
6. `( cd <worktree> && .venv/bin/pytest -q --tb=line -p no:warnings tests/robustness 2>&1 | tail -2 )` prints `161 passed`.
7. `.venv/bin/python spec/convert_answer_keys.py --tier synthetic --check --verify-anchors` prints `120 flaws converted across 8 keys; 0 key(s) failed validation`; `.venv/bin/python eval/build_pdfs.py --check` prints `ALL CHECKS PASSED`.
8. `.venv/bin/python scripts/leakage_grep.py` prints `PASS`; `.venv/bin/python -m sit_review_agent.prompts --check` prints `PROMPTS.lock up to date (bundle 2569a967015b)`; `tests/test_export_public_snapshot.py` passes.
9. For a guard: `cp` a backup, remove the claim, see its test fail, restore, `cmp` the file; a verifier runs a DIFFERENT mutation from the builder's (on 5 Oct 2026 a `revision_problems` guard survived the builder's and fell to the verifier's).
10. Push only as a fast-forward after all of the above; `git ls-remote origin claude/happy-darwin-d0bl94` equals the local HEAD.
11. Rollback: the truth branch is never force-pushed; a bad push is undone by a new commit that restores the affected files from the last good sha (`git checkout <good sha> -- <paths>`, commit, push), never by reverting a merge commit.
12. A UI change is verified in a browser: the worker starts its own `dra ui` on a port other than 8791 with `--runs-dir` at a `cp -R` copy of `~/Desktop/SIT-wt/demo6/runs/ui-261004-034213-c5cb`, replays `progress.jsonl` line by line, screenshots viewports, kills its server by pid.

## 8. Traps already paid for

The model safeguard (`reasoning_extraction`) stopped five workers on 5 Oct 2026 (refine fix twice, B0 wording twice, A3 once) and three more were cut mid-turn but carried on; every stop came while reading or writing the agent's own phase code or prose about it, never during git, pytest or push.
What closed the items: a planner checkpoint commit of whatever was on disk, then a MECHANICAL worker forbidden to open the source that ran the tests and gates and committed; a content retry of the same item on Fable stopped too, so do not spend one.
A mechanical worker's brief must state the one assertion to change exactly as the previous report quoted it; one round was lost when the brief guessed where the ids were and the guess was wrong.
Three agents stalled at once at about 15:20 with "no progress for 600s (stream watchdog did not recover)": not a safeguard; check the worktree (`status -s`, `log -1`) and respawn with the state on disk; a stalled verifier may leave a mutation on disk.
A verifier that stalls loses its review lines and probe results with it; the INV-05 verifier had written its result section into the worker note (b20a894) BEFORE its last gates, so item 1 could stand on it, the A3 verifier had not, so item 2 redoes the review: a verifier writes its result line into the note as soon as the probes and mutations are done, before the merge and the final suite.
The auto-mode harness note that prefers Bash for reading made one worker use `sed` over source despite the brief; harmless there, but the Read tool rule exists because a `cat` over a handover was refused on 25 Sep.
`sit-eval score` detection of a refine fallback is keyed on the agent's wording (no structured field); a rewording in `phases/refine.py` or `_model_calls.py` silently stops the warning (section 5 point 11).
`--prior-scores` existed all along; the plan D v2 scorings never passed it, which is why both re-assessment metrics read 0.0 (now null with a reason without it).
The subscription session limit aborts runs with exit 3 and judge calls with `LLMUnavailableError`; always `pgrep` for a previous worker's scripts before starting the same work.
Two workers on one results folder corrupt the tables: one worker owns each `RUNS*.md`.
The key converter without `--tier` reads the held-out keys (entry 3 of the access log).
INV-05 crashed a run because the report's URL redaction rewrote a quote that verify had copied from the excerpt (fixed 3 Oct); the first fix trusted doc excerpts (caught by a verifier's probe); verifiers with probes are not optional on honesty code, and E3 of step G was built with that guard kept.
Ingest removes a line-end hyphen between two lowercase letters before INV-05 sees the text, so a real URL hyphen there is lost (noted by the E2 builder, not changed).
`sit-eval aggregate` pairs runs by manifest `condition`; FULL runs made before 280c4b4 carry null and appear as "unlabelled".
The scorer's `--max-cost-usd` fires at committed spend plus $1 per in-flight call.
A line pasted into this chat never runs; Terminal only; a new window has no exported key; Esc while the Claude window is focused stops every worker.
`gh` and `git fetch` print `credential-manager is not a git command`; harmless.

## 9. Not done, on purpose

The three stalled branches (steps G, H, I) are not pushed: items 1 to 3.
No live run on the fixed code yet: the refine fix, the fallback merge, A3 and the INV-05 edges rest on fake-gateway tests and probes; his second rehearsal is the first live proof.
The v2 reruns (item 6) wait on his money word; the LangGraph arm is unfunded; the two held-out items were not run (deviation 14).
Step F's detection stays text-keyed (section 5 point 11); the verifier's design note that not-re-examined rows are not counted stale in the v2 metrics stands as the written definition reads.
The stricter A3 variant (drop `resolved` from the assess prompt and `ReassessmentStatus`) was not done; the prompt lock is unchanged.
The ledger marker for model-anchor excerpts (section 5 point 10); the public snapshot refresh (section 6).
No multi-provider dropdown, no persistent memory beyond re-assessment, no hosted share link, no dark theme, no prompt or prereg freeze (item 7).
Worktree housekeeping: about 88 worktrees under `~/Desktop/SIT-wt/`; keep `demo6`, `demo4`, `plan-d-runs`, `plan-d-b0`, `plan-d-grade` (their ignored `runs/` hold the plan D run folders item 6 needs), `score`, `score2`, `inv05-edges`, `a3-resolved-prior`, `score-manifest-disagree`, `handover-261005b`; `refine-prior-status` (its WIP is superseded by 5819a6d) and the rest are merged and may go in a quiet moment; not planned.

## 10. Where everything is

Runtime: `/opt/homebrew/bin/python3.13`, venv per worktree (about 1 GB each), Playwright Chromium for the UI tests, `claude -p` on his subscription for every model call, the SIT MCP servers only through his key.
End-of-session routine: update the memory file and its `MEMORY.md` line, write the next handover from `~/.claude/skills/handover/template.md`, then `/saveconvo SIT --agents`.

| Thing | Path |
|---|---|
| Truth branch | `origin/claude/happy-darwin-d0bl94` of `malcolm1232/SIT` (private), tip 5ca659a plus this file |
| Public snapshot | `malcolm1232/SIT-public` (older than the tip; refresh blocked, section 6) |
| Unpushed work | `~/Desktop/SIT-wt/inv05-edges` 3224fed, `~/Desktop/SIT-wt/a3-resolved-prior` 9e019bd, `~/Desktop/SIT-wt/score-manifest-disagree` 1a7220b |
| His rehearsal worktree | `~/Desktop/SIT-wt/demo6` (s4/demo6), PDF `runs/input/sit_sample_v1.pdf`, first run `runs/ui-261004-034213-c5cb` |
| Plan D run folders (uncommitted) | `~/Desktop/SIT-wt/plan-d-runs/runs/` (FULL, v2, variance, ablation), `~/Desktop/SIT-wt/plan-d-b0/runs/` (B0), `~/Desktop/SIT-wt/plan-d-grade/runs/grades/` |
| Plan D tables and write-up | `docs/live_runs/plan_d/RUNS.md`, `RUNS_B0.md`, `GRADES.md`; `docs/COMPARISON_PLAN_D.md` |
| First rehearsal record | `docs/live_runs/sit_sample_ui_2/MEASUREMENT.md` (counts only; a brief never points at it) |
| Evaluation items | `eval/synthetic/{payments_orchestration,clinical_rpm,research_lakehouse,iot_fleet,consent_service,hospital_scheduling,ledger_migration,exam_platform}/`; held-out `eval/blind/` (sealed) |
| Decisions, deviations, sealing | `docs/USER_DECISIONS.md` (to row 46; 47 on the A3 branch), `eval/prereg_deviations.md` (to entry 14), `docs/SEALING.md`, `eval/KEY_SIGNOFF.md`, `eval/blind/ACCESS_LOG.md` (3 entries) |
| Study sheet and architecture | `docs/EXPLAIN_AS_IT_RUNS.md`, `docs/ARCHITECTURE.md`, `docs/DEMO_DAY_SCRIPT.md`, `docs/DEMO_DAY_RUNBOOK.md`, `docs/LIMITATIONS.md`, `docs/SUBMISSION_GAPS.md` |
| Refine and model calls | `agent/sit_review_agent/phases/refine.py` (`merge_same_prior`, the kept-all path), `phases/_model_calls.py` (`KeptItems.statuses`, `split_revisions`), `llm/outputs.py` (`missing_prior_statuses`), `delta.py` (`LEAST_FIXED`, `build_prior_table`) |
| Honesty code | `invariants.py` (INV-05, `allowed_urls`, `quote_in_document`, `quote_exempt`, `LINK_REMOVED` on the G branch), `phases/report.py` (`_redact`, `_delta_table`, `fallback_verdict`), `phases/verify.py` |
| Scorer | `harness/sit_eval/scoring.py` (`check_condition`, `ConditionMismatch`, the refine-fallback detection), `harness/sit_eval/cli.py`, `harness/sit_eval/metrics.py::_v2_metrics`, `harness/sit_eval/schemas/scores.schema.json` |
| Worker notes of 5 Oct afternoon | `docs/transcripts/session7/*.md` (6 on the tip: score-condition-check, v2-metrics-a4, refine-prior-status, b0-verdict-wording, score-warn-fallback, refine-fallback-merge; inv05-edges and a3-resolved-prior on their branches) |
| Diagnoses | `docs/transcripts/session6/inv05-diagnosis.md`, `v2-diagnosis.md` (cards A1 to A6, B1) |
| Memory | `~/.claude/projects/-Users-malco/memory/project_sit_design_review_agent_261003.md` |
| Transcripts | folder `~/Desktop/conversation_history/SIT/`, day file conversation_verbatim_261005.md (this session, started 5 Oct 12:35, written at its close) with its agents folder; the morning session is in `conversation_verbatim_261004.md` |
| Older handovers | `docs/HANDOVER_261005_PLANNER.md` (superseded), `docs/HANDOVER_261004_PLANNER.md`, `docs/HANDOVER_261003_PLANNER.md` |
