# Worker note: synthetic item ledger_migration (synthetic-ledger-migration-001)

Date: 2026-10-04.
Brief: the SIT planner's S4 item-authoring brief under Malcolm's word of 4 Oct 2026 22:40 ("yes" to plan D: ten documents, five of them new), under his delegation of shot calling (3 Oct 02:50).
Branch `s4/item-ledger` from `origin/claude/happy-darwin-d0bl94` at 5f4eeb6; this worker wrote both designs, the key, the PDFs, the canonical key and the README.
Not opened: `eval/blind/`, `docs/live_runs/`, the source of `spec/convert_answer_keys.py` and `eval/build_pdfs.py`, the other synthetic items except the payments_orchestration model (README, key, first 60 lines of v1) and the hospital sibling's README and note.

## Process notes

- `eval/build_pdfs.py` and `spec/convert_answer_keys.py` list items in code. Both were run unchanged on disk through scratchpad wrappers copied from the hospital ones (`author_ledger/build_ledger_pdfs.py`, `author_ledger/convert_ledger.py`) that add this item to `ITEMS` (and `NEEDS_EXTERNAL = {"F05"}`) in memory only. The registering worker must add these entries for real.
- The worktree venv was made per the handover (section 7) and `markdown` pip-installed into it (an environment change, not a repository change).
- `design_v2.md` is generated from `design_v1.md` by `author_ledger/make_v2.py`: exact, single-occurrence replacements (title block, revision history, "Changes since version 1.0", then the seven changes; the F07 change also adds the reversal-key sentence to 12.4). `answer_key.json` is written by `author_ledger/make_key.py`, which reads anchor pages from the PDFs through `sit_review_agent.ingest.pdf.ingest`, asserts each anchor quote is an exact, unique match on its page, and asserts the severity and category counts. Every anchor is a fragment of one PDF line.
- F05's external fact: fetched https://docs.aws.amazon.com/AmazonS3/latest/userguide/restoring-objects-retrieval-options.html on 2026-10-04. Its table lists S3 Glacier Deep Archive as Expedited "Not available", Standard "Within 12 hours", Bulk "Within 48 hours". Recorded with `verified: true`. The Aurora Global Database page (https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database.html, "latency typically under a second") was also read to keep F06's v1 wording accurate; F06 is an internal contradiction and carries no external fact.
- `scripts/leakage_grep.py` with this item present first flagged `never applied` (TF-IDF pair from this item's key, F03 text, against `agent/sit_review_agent/phases/refine.py:75`). Reworded in the key only ("not processed", "reach neither ledger"); no design text or anchor changed. After that only `'never leave' (tfidf; from eval/synthetic/payments_orchestration)` against `agent/sit_review_agent/tools/gateway.py:1080` remains, pre-existing; reported, not fixed (allow-list entry for the registering change).
- Tests: none run (no test enumerates `eval/synthetic/*`). Not edited: `eval/prereg.yaml`, `eval/build_pdfs.py`, `spec/convert_answer_keys.py`. Nothing pushed.
- One assistant turn of this worker was stopped by the safety classifier while it was reading the sibling's scratchpad scripts; the work continued from files already read, and nothing in the item depends on the withheld output.

## Commands (from the worktree root, `S` = the scratchpad folder `author_ledger`)

    python3 $S/make_v2.py
    .venv/bin/python $S/build_ledger_pdfs.py /Users/malco/Desktop/SIT-wt/item-ledger
    .venv/bin/python $S/make_key.py
    PYTHONPATH=agent .venv/bin/python $S/convert_ledger.py /Users/malco/Desktop/SIT-wt/item-ledger --tier synthetic --verify-anchors
    .venv/bin/python scripts/leakage_grep.py

Build output: `design_v1.pdf: 15 pages`, `design_v2.pdf: 16 pages`, `ALL CHECKS PASSED` (also with `--check`).
Converter output for this item: `flaws 15 (v1 14, v2 1)`, `v2_status {'fixed': 7, 'unchanged': 7, 'introduced': 1}`, `needs_external_research 1; sound sections 5`, `note: flaw_counts equal to recomputed v1 counts`, `could not map: none`, `scored_run_ready False`, no anchor notes; overall `60 flaws converted across 4 keys; 0 key(s) failed validation`. The other three canonical keys were rewritten byte-identical (git shows no change).

Anchor pages (design_v1 unless stated): F01 5, F02 11, F03 12, F04 8, F05 10, F06 12, F07 7, F08 9, F09 7, F10 13, F11 15, F12 11, F13 3, F14 2, F15 7 (design_v2).

## Word counts (wc -w)

        7948 design_v1.md
        8472 design_v2.md
       16420 total

## No-label scan

    $ grep -ciE '\bF[0-9]{2}\b|flaw|planted|intentional|deliberate|bug|TODO|FIXME|incorrect|mistake|wrong|regression|known issue|answer key' design_v1.md design_v2.md
    design_v1.md:0
    design_v2.md:0

Em dash count (grep -c of U+2014, and of the escape `u2014` in the JSON files) in both designs, the key, the canonical key, the README and this note: 0 each.

## Per-flaw carrying sentences (v1) and their v2 state

Fixed in v2: F01, F02, F04, F05, F07, F11, F14. Unchanged: F03, F06, F08, F09, F10, F12, F13. New in v2: F15 (from the F07 change).
Each sentence below was asserted by `author_ledger/selfcheck.py` to occur exactly once in v1 and, for unchanged flaws, exactly once in v2; for fixed flaws the v1 sentence is absent from v2 and the v2 sentence present once.

### F01

- v1: A leg that would take a non-overdraft account below zero, or that posts to a frozen or closed account, is rejected by its Account Processor, which records it in `rejected_leg` and notifies the source system, while the other legs of the journal, applied by their own processors, stand.
- v2: The Posting Service checks these rules for every leg of a journal in the same transaction that inserts the journal: it reads each account's status from the `account_limit` table in the Journal Store and, for a debit to a non-overdraft account, takes a row lock on that account's `account_limit` row, checks the committed balance less active holds, and updates the committed balance before commit. If any leg fails a rule, the whole journal is refused with 422 and nothing is written.

### F02

- v1: The daily reconciliation compares, for each currency, the total debits and the total credits posted by CORAL and by Lumbung for the business day, and a day on which both totals agree to the cent is a matched day.
- v2: The daily reconciliation compares the closing balance of every mapped account in each currency held by CORAL and by Lumbung, and matches each CORAL posting to the Lumbung journal that carries its transaction ID as idempotency key, comparing accounts, amounts and value dates; a day on which every balance agrees to the cent and every posting is matched is a matched day.

### F03

- v1: Postings that reach CORAL's online interface between the 22:00 extract and the 00:00 switch are held in CORAL's memo-post queue for the following business day's batch, and CORAL's batch schedule is disabled at 00:00.
- v2: (unchanged, same sentence)

### F04

- v1: Close adjustments raised during the close window are entered by a Financial Controller in the Close Console and posted on submission, so that the close is not held up waiting for a second approver.
- v2: Close adjustments raised during the close window are entered by a Financial Controller in the Close Console and approved by a second Financial Controller or by the Head of Financial Reporting before they post; the close rota always names two Financial Controllers on call, so an approval is available inside the window.

### F05

- v1: For a record older than 13 months, the Archive Service requests an Expedited retrieval from S3 Glacier Deep Archive, which returns the object within 5 minutes, so the four-hour limit of NFR-4 is met with a wide margin.
- v2: For an older record the Archive Service requests a Standard retrieval from S3 Glacier Deep Archive, which completes within 12 hours, inside the 48 hours NFR-4 allows for those records.

### F06

- v1: The ledger clusters replicate to the secondary at the storage layer asynchronously, with lag typically under one second, and on region loss the runbook promotes the secondary.
- v2: (unchanged, same sentence)

### F07

- v1: A run that fails part-way is restarted from the first account under a new run_id, and each accrual journal's idempotency key is the run_id followed by the account number.
- v2: A run that fails part-way resumes from the first account it has not yet posted, and each accrual journal's idempotency key is `ACR-` followed by the account number and the accrual date, so a restarted run cannot post one account's accrual for one date twice.

### F08

- v1: To keep onboarding simple, every workload in the ledger AWS account runs under the shared `ledger-workload` IAM role, which is granted `kafka-cluster:WriteData` on all topics matching `ledger.*`.
- v2: (unchanged, same sentence)

### F09

- v1: Once a business day is closed, its balances are final: a posting that arrives after the close carries the next business day's value date, whatever value date the source system sent.
- v2: (unchanged, same sentence)

### F10

- v1: | DEC-07 | History migration reads CORAL's VSAM history through the Pelita Extract utility, in Phase 3 (January and February 2027) | The only supported reader for CORAL's packed-decimal history files |
- v2: (unchanged, same sentence)

### F11

- v1: | 4. Dual-run | 8 Mar to 2 Apr 2027 (4 weeks) | Dual-feed adapter live, daily reconciliation, go/no-go on 1 Apr |
- v2: | 4. Dual-run | 1 Feb to 2 Apr 2027 (9 weeks) | Dual-feed adapter live, daily reconciliation, go/no-go on 1 Apr |

### F12

- v1: The seven-year history holds about 2.9 billion posting legs; the loader writes 150,000 legs per second into the partitioned `leg` table, so a full load completes in about 90 minutes, and each migration rehearsal loads the full history in the Saturday 02:00 to 06:00 window.
- v2: (unchanged, same sentence)

### F13

- v1: | NFR-5 | The ledger scales to accommodate the bank's future growth without redesign. |
- v2: (unchanged, same sentence)

### F14

- v1: | FR-5 | Non-SGD monetary positions are revalued to SGD at the closing rate at each month end, with the difference posted to unrealised FX gain or loss. |
- v2: The Treasury closing rate for a currency is the mid rate against SGD that Treasury fixes at 17:00 SGT on the last business day of the month and publishes to the `ref.fx_rate` table through the rate service; the revaluation job reads the rate with that business date and refuses to run if any currency's rate is missing.

### F15 (new in v2, from the F07 change)

- v1: (absent; v1 12.4 re-accrual is unaffected because each run has its own run_id)
- v2: The Posting API's 409 response for a key that already holds a journal is treated as confirmation that the account's accrual for that date is posted, and the run moves on to the next account. (together with the unchanged 12.4: 'the run posts a reversal of the original accrual journal and then a new accrual journal at the corrected rate.')


## Cold read

Date: 2026-10-05 00:08, by a fresh-context cold reader under the same brief (plan D, his "yes" of 4 Oct 22:40).
`design_v1.md` was read in full before the key and the README; `design_v2.md` next; then the key, the README and this note.
Scripts in the scratchpad folder `coldread_ledger/` (copies of the `author_ledger/` wrappers plus `edit_v1.py` and `edit_key.py`).

### Flaws found cold

Found cold, by substance: F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, and F15 in v2.
Missed cold: F14 ("the closing rate" read as the standard accounting term; the missing source, side and time are findable from FR-5 and Section 13, so the flaw stands as written).

### Defects of the item, fixed

1. F03 was not cleanly findable: the dual-feed adapter stayed on until 00:15, so the 22:00 to 00:00 postings did reach Selasih through it, against the key's "reach neither ledger"; and an extract "from the master files at the start of the batch" missed the whole day's memo posts, a second gap the key did not describe. Section 23.2 now disables the adapter at 22:00 and takes the extract at 22:40 once the batch has applied the day's memo posts; the carrying sentence keeps its anchor. Key F03 description, why, first credit item and core insight updated.
2. Sound Section 8: its unique constraint on `journal` could not exist, because Section 20 partitioned `journal` by month on `business_date` (a PostgreSQL unique constraint on a partitioned table must include the partition key). `journal` is now unpartitioned, `leg` carries `business_date` and is the partitioned table, Section 5 no longer names a separate idempotency registry, and "enforced by the database at commit" reads "enforced by the database".
3. Sound Section 7: "for all time" from the legs could not hold once journals older than 13 months leave the Journal Store. The close now adds the day's totals to cumulative totals carried in `close_run`.
4. Sound Section 10: "arrive at one partition in commit order" is not what a relay reading by insert-time sequence gives, and Sections 9.4 and 14.2 used sequence numbers as watermarks. Section 10 now claims only one partition and one processor per account (a balance being a sum is order-independent); 9.4 uses per-leg applied status and 14.2 waits on published outbox rows.
5. Sound Section 18: one hash chain written inside each posting transaction serialises every journal commit, the daily digest left a day-long window, and nothing tied an audit record to the journal's content (NFR-8). Records now carry the journal's hash, a separate insert-only chaining job builds the chain in `audit_chain`, and the chain head goes to the Object Lock bucket every five minutes. Data model updated.
6. v2's F01 fix updated the committed balance only on debits, so credits never reached it. v2 9.2 now locks each touched customer account's `account_limit` row in account order and applies every leg; its lead sentence no longer says the Account Processors apply the rules.
7. The v2 changelog bullet for 12.2 and 12.4 said "the run's handling of the Posting API's responses is stated", which pointed at the 409 handling that carries F15. Reworded to "a failed accrual run resumes where it stopped, and accrual and reversal journals have new idempotency keys".
8. Unkeyed contradictions removed from non-sound sections: the accrual run's 900 journals per second exceeded NFR-1's 600 (NFR-1, 9.3 and 28.2 now 1,000); accrual journals posted after the 23:30 roll would have carried the next business date (14.1 now exempts the close's own journals, ahead of the F09 sentence); a rollback replaying Selasih's own accrual into CORAL would accrue twice (23.3); the bulk-journal file had no rule for the SGD 1,000,000 second checker (16); archive retention of ten years from writing fell short of ten years from the financial year end for monthly-exported audit records (19); "201 Accepted" now "201 Created"; Sections 12 and 23 subsections put in numeric order.
9. Key F11: the four-week dual-run cannot reach twenty consecutive matched days at all (17 business days from 8 to 31 March 2027, Good Friday 26 March; the 1 April reconciliation runs after the go/no-go); the why now says so. Key F13 updated for NFR-1 at 1,000. Sound-section `why_sound` and `trap` text for 7, 8, 10 and 18 updated to the new wording.
10. Names: "Lumbung" matches Lumbung Dana, an OJK-licensed Indonesian lending fintech; "Seroja Systems" is close to Serojatech Sdn Bhd, a Malaysian enterprise IT supplier; "Rosalind Teo" is the name of real bank treasury staff. Renamed to "Selasih", "Rambai Software" and "Marguerite Liew" (web searches for each returned no matching organisation, product or banker). "Merbah Bank", its product names, "CORAL" and "Pelita Extract" returned no real match.

### Checks

- F05 external fact re-fetched 2026-10-05 from https://docs.aws.amazon.com/AmazonS3/latest/userguide/restoring-objects-retrieval-options.html: table row "S3 Glacier Deep Archive ... | Not available | 9-12 hours | Within 12 hours | Within 48 hours"; text "Standard retrievals typically finish within 12 hours for the S3 Glacier Deep Archive storage class". The key's wording holds.
- F09 anchor moved inside its sentence to stay on one PDF line: "a posting that arrives after the close carries the next business day's value date, whatever".
- Rebuild: `design_v1.pdf` 15 pages, `design_v2.pdf` 16 pages, ALL CHECKS PASSED; converter `0 key(s) failed validation`, `flaws 15 (v1 14, v2 1)`, `v2_status {'fixed': 7, 'unchanged': 7, 'introduced': 1}`, flaw_counts equal; the other canonical keys unchanged. Canary unchanged.
- Anchor pages now: F01 5, F02 11, F03 12, F04 8, F05 10, F06 13, F07 7, F08 9, F09 7, F10 14, F11 15, F12 11, F13 3, F14 2, F15 7 (design_v2).
- Label scan on both designs: 0 and 0. Em dash count: 0 in both designs, both keys, the README and this note. `scripts/leakage_grep.py`: only the pre-existing `never leave` hit.
- Word counts: design_v1 8,161, design_v2 8,685.

### Left as they are (true but unkeyed, for the human labeller as VALID_UNPLANTED)

Section 28.1 has no acceptance test for FR-3, FR-6, FR-7 or FR-13; Section 9.3 assumes legs spread evenly over 96 partitions although every FAST payment also posts to the one FAST settlement account; Section 24.4's rebuild of the Balance Store by replaying legs cannot restore holds (not journals) or months already archived; pre-April 2020 history read "through the existing tape retrieval process" outlives the mainframe (CORAL read-only for twelve months, contract ends 2028); Section 29 marks account processing "Ready" while PB-05's load test is open.
