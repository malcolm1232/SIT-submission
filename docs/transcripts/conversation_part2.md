
---

## Subagent report: Research-grade eval methodology

> I wrote the methodology spec and the formal metric definitions to `/home/user/SIT/research/methodology/`. I ran no git commands and wrote nothing outside that folder.
>
> 1. **Files.** `README.md` (about 7.4k words) is the spec and covers all 9 parts of the brief. `metrics.md` (about 4.9k words) has the formulas, the matching procedure, Python-style pseudo-code, and a worked example (nDCG 0.669, F1 0.444 strict / 0.545 adjudicated) that a scoring implementation should reproduce as a unit test.
> 2. **Matching a finding to a planted flaw.** A finding gets candidate flaws from section overlap, embedding similarity and an LLM shortlist. A matcher model from a different family than the agent then scores each pair 0–3, and a finding only counts as a match if it states the flaw's key point, not just its topic. Each flaw is credited at most once (Hungarian assignment); strict = score 3, lenient = 2 or more.
> 3. **Unmatched findings** go into six classes, including "valid but not in the key" and "hallucinated". A human checks every finding in those two classes. Precision is reported both strict and adjudicated. Before use, the matcher must agree with humans at κ ≥ 0.80, and a generic-checklist baseline must score recall ≤ 0.05.
> 4. **Metrics cover everything you listed**, plus a few extras tied to the lab PDF: preserving approved decisions (§1.3), stale findings and new-flaw recall on the v2 re-review (§1.5), and research yield and overrun for knowing when to stop (§3.2).
> 5. **Splits and leakage.** Splits are dev, held-out (at most 3 evaluations), blind (1 evaluation), out-of-domain, and the real SIT doc kept separate from any generalisation claim. Six leakage rules are paired with a six-step audit (term grep, n-gram overlap, canary strings, access scan, paraphrase probe, template-tell probe). One concrete risk: if the repo is public, an agent with web search can find the answer keys, so keys must be encrypted and the repo's domains blocked in the search tool.
> 6. **Baselines and ablations.** The spec defines baselines B0, B0-$ and B-gen, ablations A1–A5, and a human ceiling H. Each comes with a category-specific prediction to pre-register, all use the same output schema, and cost is reported throughout.
> 7. **Statistics.** Use at least 3 runs per doc (5 preferred), a doc-then-run cluster bootstrap, and paired differences. Correct the main comparisons with Holm and the per-category breakdowns with Benjamini–Hochberg. From the power calculations: detecting a 10-point recall difference takes about 33 docs of 8 flaws; about 15 blind docs can only rule out a large gap (≥ 0.15); trusting the LLM grader needs at least 100 doubly graded reviews.
> 8. **Overfitting.** The dev-to-blind gap is compared against the untuned B0 baseline's gap, because a harder blind set can cause a drop on its own. Further checks are reordering and paraphrase tests, an out-of-domain doc, and clean-versus-flawed pairs. The README also covers robustness reporting (fault-free and fault-injected runs reported separately, failed runs counted, disclosure rate), the run-manifest YAML, and a 10-table results template.
> 9. **Loopholes.** There are 40 numbered items in four groups (leakage, dataset construction, agent gaming, analysis), each with a control and the evidence the report must show.
> 10. **Sources and what is unverified.** All 43 references were checked by web search; arxiv.org could not be fetched, so details come from search summaries. Marked UNVERIFIED or PROPOSED DEFAULT: all numeric thresholds, the intra-doc correlation values behind the sample sizes, the "overrun" metric, the exact pass^k estimator, the claim that SPOT never validated its matcher, the SPOT author list, the `krippendorff` package API, and the content of arXiv:2605.08545.
>
> **Open item:** the default flaw taxonomy is aligned to lab §2.3 and should be replaced by the project taxonomy once it exists, since `research/` had no taxonomy file.

## Subagent report: Lecturer grader rubric design

> I wrote the three grading files; the grader has not been run on a real review yet.
>
> 1. **Rubric** (`/home/user/SIT/research/grading/README.md`): 10 dimensions scored 0–4 with descriptors per level, plus an optional D11 for re-reviewing an updated artefact. Every criterion is tied to a verbatim quote from the lab brief with page and section. Weights: evidence/traceability 16, recommendation quality 14, fitness verdict 12, restraint 10, intent 10, coverage 10, triage 8, research sufficiency 8, consistency/accuracy 8, professional quality 4.
> 2. **Pass rule**: weighted score ≥ 60 and all gates pass. Failing gates are any dimension at 0, evidence/recommendations/restraint below 2, two or more material hallucinations, a missing verdict, or text aimed at the grader. One material hallucination caps the grade at C. A needs ≥ 85 with no dimension below 3.
> 3. **Protocol**: a split-into-findings step, then Pass A (findings shuffled, scored one by one, two samples) and Pass B (whole review, two samples). Pass B starts with the grader listing the issues it sees before reading the review. Quoted design text is checked by string match in code. Any dimension differing by 2 or more triggers a third sample and a human-review flag. Key-blind is the headline score; key-aware runs in a separate context and never penalises valid findings outside the key.
> 4. **Grader prompt** (`/home/user/SIT/research/grading/grader_prompt.md`): the full system prompt, both user-message templates, the splitter prompt, two output schemas (checked as valid JSON Schema 2020-12), a harness report example and the answer-key format. Hallucinations are only marked "verified false" when the grader can show the contradiction; otherwise they are "suspected" and don't trigger caps.
> 5. **Human calibration**: one person blind-scores 5 reviews spanning strong, mediocre, padded, terse and hallucinated. Targets are weighted kappa ≥ 0.6, within-1 agreement ≥ 90%, score gap ≤ 8 points, and 5/5 pass/fail agreement. Fixes are re-checked on 5 new items, not the same ones.
> 6. **Grader validation**: 13 controlled tests (V1–V13) built from one competent review scoring 75. A heavily padded version should score 63 and fail on restraint; a terse correct version should score 75–78.5. Other tests cover a correct "no change" (must not lose marks), injected fake sources and false gaps, reordering, style changes, injected grader instructions, and re-opening confirmed design decisions.
> 7. **Worked examples** (`/home/user/SIT/research/grading/worked_examples.md`), on the Memory Platform doc: **A (100):** the pgvector issue. The approximate index applies the learner/slot filter only after its search, so "500–800 vectors searched" is unproven, and the NFR-2 test measures latency only. Supported by quotes from the pgvector README that I fetched and checked. **C (61.5):** a finding that only restates the doc's own self-assessment in section 28. **Looks good, scores low (14.2):** a fake "PDPA s.22A right to erasure", a misattributed HNSW paper, and "migrate to Pinecone" against a confirmed decision. **Bonus (94.6):** a correct "no change needed".
> 8. **Answer key** (illustrative): 10 key issues, 6 traps and 3 no-change areas, all checked against the PDF. A strong example is that Gateway Check 4 calls the admin plane during a live request, contradicting NFR-4.
> 9. **Unverified citations**: the XACML 3.0 reference (in the A-grade rewrite of the C example) and the HNSW paper's bibliographic details come from memory. The PDPA s.16/s.25 points come from a secondary source (IAPP), and the official statute site was not checked. The Microsoft token-lifetime question was left out because the docs site was blocked.
> 10. **Demo-day checklist**: likely evaluator probes for the four demo-day parts in section 5.4 and what earns marks, plus a 12-item rehearsal sheet. It flags that the MCP containers take 1–2 minutes to wake from idle, so warm them up before the live run.

## Coordinator

[Commit + push "Add research-grade evaluation methodology and metric definitions" (grading files swept into the same commit).]

Both the methodology and the grading work were already captured in the last push, since the grading files landed just before that commit. Everything is on the remote.

Six research deliverables are now done: models, Kaggle, frameworks, methodology, grading. Two things worth noting from the latest two:

- **The methodology spec flags a real leakage risk.** If the repo is public, an agent with web search could find its own answer keys. The keys need encrypting and the repo's domain blocked in the search tool before any blind evaluation counts.
- **The grader found a strong finding on the real SIT document** while writing worked examples: Gateway Check 4 calls the admin plane during a live request, which contradicts NFR-4's claim that the admin plane is never in the request path. That's a good seed for the agent's first real run.

Still running: robustness scenarios, three synthetic eval docs, and both blind items.

---

## Subagent report: Robustness and stress scenarios

> I wrote the scenario catalogue and the test plan: **166 scenarios**, of which 81 must pass before submission (P0), 68 before demo day (P1) and 17 are stretch goals (P2). Each scenario has a stable ID, category, trigger, expected behaviour, a deterministic way to simulate it, a pass/fail criterion, severity, priority and test level. Nothing has been run yet; these are the tests to build.
>
> 1. **Categories:** MCP tool and infrastructure failures (28), LLM API failures (12), network (5), input variations (32), adversarial content (24), agent behaviour (28), demo day (15), overfitting (12). I added an operational/environment category (10): fresh-clone reproduction, committed secrets, Ctrl-C and resume, awkward file paths.
> 2. **Facts from the brief that shaped the scenarios:** The shared key means one 401 disables all four servers at once. The key is printed in the brief, so a check that it never enters git history is P0. The document-intelligence server rejects everything, so local parsing must be the primary path. Scale-to-zero means a cold start is the normal first call on demo day, and it also drops MCP sessions (the spec requires re-initialising after a 404). The browser server keeps one Chromium session shared by every participant, so another user can change the page between our calls. DuckDuckGo signals rate limits inside an HTTP 200 response.
> 3. **Sample-document traps:** the requirements tables span pages 3 to 5, Figure 1 exists only as an image, section 8 has a heading but no text, and it cites a companion "Conceptual Design" that isn't supplied.
> 4. **Shared invariants:** 11 checks run after every test (INV-01 to INV-11). They include: always terminates, every finding's quote resolves to the doc, every citation resolves to a real tool call, degradations are disclosed, no secret leaks, approved decisions are preserved.
> 5. **Three test levels:** **L0:** fake LLM, fake or replayed tools and a virtual clock. Offline, under 60 s, so a 90 s cold start costs about 0 ms. **L1:** real LLM with recorded tool responses, run k times and scored as pass^k. Attack success rate and secret leaks must be zero in every run. **L2:** live servers, time-boxed rehearsals.
> 6. **Fault injection:** faults go in below the agent's retry and circuit-breaker logic, so that logic is what gets tested. One YAML schedule per scenario ID covers MCP, LLM, network and process faults (19 fault types). Real TLS, DNS and bandwidth faults use Toxiproxy or OS network isolation.
> 7. **Fixtures:** recorded MCP responses with strict replay and key redaction, which also give an offline fallback for the demo. Test documents are generated reproducibly (scanned, hidden-text, corrupted, 150-page, renamed, paraphrased, v2 variants), each with an answer-key file. Injection tests compare a clean twin against an injected twin.
> 8. **Priorities:** README section 4.2 gives a 20-item minimum gate if time runs short, then an implementation order (harness first) and a demo rehearsal protocol: 5 runs on held-out docs, servers left idle 30+ minutes so they start cold, 10-minute stopwatch, one random live change per run.
> 9. **Results template:** a CSV header plus a markdown table with status values and a per-tier summary.
> 10. **Caveats:** thresholds such as overlap ≥ 0.7 and recall ≥ 0.8 are my initial guesses and need calibrating once the agent exists. The live servers' error codes and MCP protocol version are inferred from the docs and should be confirmed on the first recording session. Without a local LLM, a fully offline laptop can only fail cleanly or replay recorded runs; it cannot review an unseen doc.
>
> README section 10 also lists 11 things the architecture needs for these tests to be passable (central tool and LLM gateways, an evidence ledger the model cites by ID, a decision registry, checkpoints, config-driven criteria and stop rules, an `explain` command), and it cites 37 references with URLs. I spot-checked several of the newer references by web search. arXiv itself was blocked from this environment, so the remaining arXiv IDs are from memory.

## Coordinator

[Commit + push "Add robustness scenario catalogue and stress-test plan".]

Robustness catalogue is committed and pushed: 166 scenarios across 9 categories, 81 of them must-pass before submission, with a three-level test design (offline fakes, real LLM with recorded tools, live rehearsals). Two findings from the brief that I hadn't spotted and that shape the build:

- **The shared MCP API key is printed in the lab PDF.** A check that it never enters git history is now a must-pass test.
- **The browser MCP server shares one Chromium session across all participants**, so another candidate can change the page between our calls. That tool should be treated as unreliable by default.

All six research notes are now done. Remaining: three synthetic eval docs and two blind items, all still running. Once they land I'll run the loophole auditor across the whole `research/` and `eval/` tree.

---

## Subagent report: Blind eval item B

> 1. Domain: the control system for a 2 MW / 4 MWh battery store at a fictional cold-storage warehouse that also has 1.8 MWac of rooftop solar. It covers the 500 kW export cap, utility demand-response events and backup power for a 380 kW critical feeder, under US grid and battery rules (IEEE 1547-2018, UL 9540, NFPA 855, IEEE 2030.5).
> 2. `/home/user/SIT/eval/blind/item_b/design.md` is about 8,900 words (excluding table markup), in 15 numbered sections with requirement IDs. It covers scope, requirements, principles, architecture, interfaces, key flows, safety, security, governance, operations, decisions, open items, acceptance criteria and a phased plan. No defect is labelled or hinted at; I checked the file for hint words.
> 3. There are 14 defects: 1 critical, 7 high, 6 medium. Four need an outside fact to confirm: IEEE 1547 requires an island trip within 2 s; the document says 5 s. A single Modbus read is limited to 125 registers; the document reads 200 in one request. UL 9540A is a test method, not a certification. IEEE 2030.5 requires TLS; the document sends it as plain HTTP.
> 4. Three defects are safety-relevant: an emergency stop that works through controller software, the inverter holding its last power command forever if communication is lost, and the 5 s island trip time. The rest are cross-section inconsistencies: a 5 s meter refresh against a 2 s export limit; a peak-shaving energy check that ignores the 35% backup reserve; a 99.95% availability claim alongside 48 h/yr of planned maintenance; planned battery cycling above the warranty's 365 cycles/yr; a supplier VPN that bypasses the DMZ; NTP time sync claimed at ±1 ms; unplanned islanding never tested; utility settings scheduled after grid-connected energisation.
> 5. `/home/user/SIT/eval/blind/item_b/answer_key.json` (valid JSON) gives each defect's location, why it matters, what a review must say for credit, and an acceptable fix. It also lists 9 deliberately sound sections with the false flags a careless reviewer might raise there. `/home/user/SIT/eval/blind/item_b/README.md` explains the item and confirms no defect is labelled. I ran no git commands.

## Coordinator

[Validated key JSON (14 defects, 9,866 words). Commit + push "Add blind eval item B: battery energy storage control system".]

Blind item B is validated and pushed: a battery energy storage control system design, about 9,900 words, with 14 defects including 4 that require checking an external standard and 3 that are safety-relevant. This one went through fine despite being an energy-control domain, so the earlier classifier stop on item A was specific to that draft rather than the category.

Still running: three synthetic docs and the blind item A retry.

`[stop hook → commit + push]`

---

## Subagent report: Synthetic eval doc: clinical IoT

> 1. **v1 is written:** `/home/user/SIT/eval/synthetic/clinical_rpm/design_v1.md` is a 24-section remote patient monitoring design for a fictional Singapore cluster (HPHC), about 7,600 prose words, with requirement IDs FR-1–16, NFR-1–12, P1–P9, D-1–20 and B-1–8.
> 2. **14 flaws are planted, none labelled:** 4 critical, 6 major, 4 minor, in the requested category counts. Examples: IoT Hub S2 quota stated as 60M/day (Microsoft's documented figure is 6M), the device group-enrollment key shipped in firmware, a single-replica alert dispatcher with no heartbeat, ML made the primary home-patient alert while its HSA review is still in the backlog, and Stream Analytics dropping late events despite device clock skew. Five sound sections are recorded as traps for over-eager reviewers.
> 3. **v2 is written:** `/home/user/SIT/eval/synthetic/clinical_rpm/design_v2.md` fixes 6 flaws (F02, F04, F07, F08, F10, F12: 3 critical, 2 major, 1 minor) and leaves 8 unchanged. The F10 fix introduces a new major flaw, F15: a blocking first-in-first-out delivery queue with no expiry and no dead-letter queue. v2 is about 8,300 prose words.
> 4. **Answer key is complete:** `/home/user/SIT/eval/synthetic/clinical_rpm/answer_key.json` (valid JSON) has 15 flaw entries with all requested fields, 5 sound sections, the per-flaw v2 status, and scoring guidance.
> 5. **README and PDFs are done:** `/home/user/SIT/eval/synthetic/clinical_rpm/README.md` has the usage paragraph and the no-label checklist, checked by grep across both docs. I checked page images of both PDFs and they render cleanly. The container's LibreOffice had no Writer component, so I installed `libreoffice-writer-nogui` with apt to make the conversion work; the README notes this.
> 6. **Caveats:** the IoT Hub figures (S2 6M/day and 120 msg/s, S3 300M/day and 6,000 msg/s) are from my own knowledge and were not looked up during this run. v2's new FR-7 acceptance test (d), a device with its clock 10 minutes behind, would in practice expose the unchanged late-event flaw (F11), and the key says to credit that. No git commands were run.

## Coordinator

[Validated (15 flaws, 5 sound). Commit + push "Add synthetic eval item: clinical remote patient monitoring (v1, v2, key)".]

Clinical remote patient monitoring item is validated and pushed: v1 and v2 in markdown and PDF, 14 planted flaws plus the v2 regression flaw, 5 sound-section traps. One caveat it flagged for the audit: the Azure IoT Hub quota figures it used as a "checkable against vendor docs" flaw came from memory, not a lookup, so the auditor should verify them.

Remaining: two synthetic docs and blind item A.

---

## Subagent report: Blind eval item A (retry)

> 1. Domain: e-commerce order management and returns. The design document describes "Meridian", a fictional replacement for a retailer's old order system, trading online in the UK, Ireland, Germany, the Netherlands and France and built on AWS. It is in `/home/user/SIT/eval/blind/item_a/design.md`: about 8,400 words of prose in 13 numbered sections plus a glossary, with requirement IDs, written in four appends.
> 2. It contains 14 defects: 2 Critical, 6 High, 5 Medium, 1 Low. Six need an external fact to confirm: EU/UK rules on refund timing and on refunding delivery charges, the DynamoDB 400 KB item limit, the 14-day SQS retention maximum, how SQS FIFO message groups serialise processing, and GDPR erasure rules combined with how S3 Object Lock compliance mode works.
> 3. The other defects are spread through the document: return window counted from order date instead of delivery date, event lost because the order write and the event publish are not atomic, a new PSP refund idempotency key on every retry, an unauthenticated return-status endpoint with guessable IDs that shows names and addresses, a 99.95% availability target that a 99.5% fraud-check dependency makes impossible, money stored as floating point, a rollback that strands orders already in Meridian, and a load test run at only half of peak.
> 4. The answer key is `/home/user/SIT/eval/blind/item_a/answer_key.json` and is valid JSON. For each defect it gives category, severity, location, why it matters, what a review must say for credit, and a fix. It also lists 8 deliberately sound areas, such as the lawful return exclusions, the return-shipping charge and the notification queues, and says what a careless reviewer would wrongly flag there.
> 5. `/home/user/SIT/eval/blind/item_a/README.md` describes the item and confirms no defect is labelled or hinted at in the document; a word search found no marker terms. Before seeding the defects I removed several accidental errors (Aurora PostgreSQL has no backtrack, the German retention period, the mattress hygiene ruling, and a decommission date inside the change freeze). I wrote only the three files and ran no git commands.

## Coordinator

[Validated (14 defects, 9,440 words). Commit + push "Add blind eval item A: e-commerce order management and returns".]

Blind item A retry succeeded and is pushed: an e-commerce order management and returns system, about 9,400 words, 14 defects, 6 of which require checking an external fact such as consumer-rights refund rules or AWS service limits. Both blind items are now complete.

Remaining: payments orchestration and research lakehouse synthetic docs. Once those land I'll launch the loophole auditor.

`[stop hook → commit + push]`

---

## Subagent report: Synthetic eval doc: data platform (research lakehouse)

> 1. I wrote `design_v1.md` (8,422 words, 24 numbered sections, FR-1..15 and NFR-1..12) for "Westmoor University Research Data Lakehouse and Retrieval Platform", a fictional institution. It follows the reference document's structure: scope, requirements, principles, architecture, data model, flows, governance, prior art, confirmed decisions, pending backlog, acceptance criteria, readiness and build phases. The stack is S3, Iceberg, Polaris, OPA, Trino/Spark, and RAG on OpenSearch.
> 2. It plants exactly 14 flaws in the requested category counts, rated 4 critical, 6 major and 4 minor. The critical ones are F01 (Restricted content sent to an external LLM, against the no-external-processing requirement), F03 (consent-withdrawal erasure undone by snapshot, tag and object-version retention), F08 (a faculty-wide service credential in notebook environment variables) and F09 (a faculty-scoped answer cache that leaks embargoed content). F04 can be checked against AWS docs: it relies on the opt-in Intelligent-Tiering Deep Archive tier, which needs a restore before reads. F05 can be checked against OpenSearch's k-NN memory formula: it counts float32 vectors as 1 byte per dimension.
> 3. Five sections are deliberately sound and recorded in the key as traps: §4 classification tiers, §6 identity and roles, §9 ingestion (write-audit-publish), §14.6 latency budget, and §16 audit plane. Each has a note on what a weak reviewer would wrongly flag there.
> 4. `design_v2.md` (8,997 words) fixes F03, F05, F06, F08, F10 and F13 (2 critical, 2 major, 2 minor). The F10 fix adds a new critical flaw, F15: an active-active cross-region Iceberg catalog with last-writer-wins replication, which can silently lose commits. The other 8 flaws are unchanged; I checked that with grep. It includes a neutral "Changes since 1.0" list that names only the sections touched.
> 5. `answer_key.json` contains every field you specified, plus a `v2_new_flaws` array holding F15. I recorded F10 as "regressed" with `new_flaw_id` F15 and a note that its original single-point-of-failure issue is resolved. The README is one paragraph plus a no-label checklist; a regex scan found 0 flaw-hinting words in either document.
> 6. Both PDFs converted successfully (python-markdown, then `soffice` with the Writer/Web PDF filter: 28 and 29 pages). All files are in `/home/user/SIT/eval/synthetic/research_lakehouse/`: `design_v1.md`, `design_v1.pdf`, `design_v2.md`, `design_v2.pdf`, `answer_key.json` and `README.md`. Nothing was committed to git.

## Coordinator

[Validated (14 flaws, 5 sound); already captured in the preceding WIP push.]

The research lakehouse item was already captured in the push a moment ago, so it's on the remote: 14 flaws, 5 sound-section traps, both PDFs rendered. Only the payments orchestration item is still running, and its three core files are already on disk, so it's close.

Once it reports, I'll launch the loophole auditor over everything.

---

## Subagent report: Synthetic eval doc: payments

> 1. `design_v1.md` (about 8,200 words, 28 sections) is a design for a fictional SEA fintech, "Serindit Pay", in the same shape as the reference PDF. It has 14 planted flaws (4 critical, 6 major, 4 minor) in exactly the category counts you asked for, plus 5 sound sections: ledger, amounts/FX, webhooks, back-office console and prior art.
> 2. The quantitative flaw that can be checked against vendor docs is F04: the doc claims 10,000 WCU per DynamoDB partition, but AWS documents 1,000, and it keys by merchant_id with an LSI. The other critical flaws are F06 (cites PCI DSS 3.2.1/3.3.2 as allowing CVC retention until settlement), F08 (payout bank account can be changed without MFA), F10 (a timed-out payment is cascaded to another acquirer, which can double-charge), and F01 (full PAN goes to the fraud vendor from a service declared out of PCI scope). F09, the subtle security gap, is the Redis idempotency key missing the merchant scope.
> 3. `design_v2.md` (about 8,900 words) fixes 6 flaws: F02 and F12 (minor), F03 and F04 (major), F06 and F08 (critical). The F04 fix adds a new critical flaw, F15: a two-region writable DynamoDB global table with a false claim that its conditional write guarantees one winner across regions. The other 8 flaws are unchanged.
> 4. `answer_key.json` has every field you specified. I added `v2_new_flaws` (for F15), `flaw_counts` and `expected_v2_open_flaws`, and marked F04 as "regressed", pointing to F15.
> 5. `README.md` covers the item, how to grade it, and the checklist. A grep for flaw-labelling terms and flaw IDs found 0 matches in both docs. v2 has a neutral revision-history table, as a real revision log would; it doesn't say which changes are fixes.
> 6. Both PDFs converted successfully (python-markdown → HTML → LibreOffice). All files are in `/home/user/SIT/eval/synthetic/payments_orchestration/`; no git commands were run.

## Coordinator

[Validated (14 flaws, 5 sound). Commit + push "Add synthetic eval item: payments orchestration (v1, v2, key, PDFs)". Listed all 37 deliverable files. Launched two auditors on Opus: (1) research package loophole audit over the six notes — cross-document consistency, unverified load-bearing claims, coverage against the user's bar, eval-design loopholes including whether the blind set is actually blind and whether synthetic docs are template-like, missing pieces, prioritised actions; (2) eval data integrity audit — verify every external-fact flaw against primary sources, label leakage grep, v2 diff integrity, schema consistency, realism spot-check, sound-section overlap.]

All 11 deliverables are in and pushed. Now the audit pass. I'll run two auditors in parallel on Opus: one checks the research notes for loopholes and cross-consistency, the other fact-checks and integrity-checks the eval data, since several "checkable against vendor docs" flaws were written from memory.

Both auditors are running. Everything produced so far is on the branch:

| Area | Files | Status |
|---|---|---|
| Framework selection | `research/frameworks/` | Done, pushed |
| Model and judge selection | `research/models/` | Done, pushed |
| Kaggle benchmarks | `research/kaggle/` | Done, pushed |
| Eval methodology and metrics | `research/methodology/` | Done, pushed |
| Lecturer grader rubric and prompt | `research/grading/` | Done, pushed |
| Robustness scenarios (166) | `research/robustness/` | Done, pushed |
| Synthetic eval items (3, each v1 + v2 + key + PDFs) | `eval/synthetic/` | Done, pushed |
| Blind eval items (2) | `eval/blind/` | Done, pushed |
| Research loophole audit | `research/audit/research_audit.md` | Running |
| Eval data integrity audit | `research/audit/eval_data_audit.md` | Running |

The data auditor is specifically fact-checking every "verifiable against vendor docs" flaw against primary sources, because three authors admitted writing those figures from memory. If a planted flaw's "correct" value is itself wrong, the key would penalise a correct reviewer, which is the worst dataset defect possible. I'll report what both audits find and commit them when they land.

---

## Subagent report: Research loophole audit

> I wrote the audit to `/home/user/SIT/research/audit/research_audit.md` and changed no other file. Each note is strong on its own, but the package is not research-grade yet: the notes contradict each other on the basics, and the eval data cannot support the generalisation claims. There are 24 actions: **7 P0, 10 P1, 7 P2**.
>
> 1. **Cross-document conflicts (32, each with one resolution).** The notes use six answer-key formats, five matching rules, four severity scales, five category taxonomies, three verdict vocabularies and two competing recall instruments. Grading's 0–4 scale and models' 0–3 is one of them (C1); models' grader choice against methodology's "different family" rules is another (C3).
> 2. **Robustness vs frameworks.** The frameworks decision covers only about 4 of robustness's 11 architecture needs. Its own "switch to LangGraph if we need resume" condition is triggered by robustness's P0 resume requirements (C17).
> 3. **11 class-(a) unverified claims**, each with how to check it. The worst: the SIT MCP auth header and live server behaviour were never probed. The "60K-token document" is attributed to a brief that contains no such figure (the SIT sample is 30 pages, about 7.6K words). Nobody recorded which model generated the eval items.
> 4. **Coverage against your bar.** Tool-failure robustness, explicit metrics and judge bias are strong. Overfitting verification, data-side bias and cost (no total budget) are weak. Capability is argued but not yet measured.
> 5. **The synthetic set is template-like.** All 3 items have 14 flaws, identical category and severity counts, the SIT section layout and 0 embedded images. There are tells: every flawed area is marked "Ready", and "Prior Art" is a sound section in 2 of the 3 documents.
> 6. **The blind set is not blind.** Its READMEs name the defects and sit in the dev tree. The authors knew the eval design (both items also have exactly 14 defects), and the items are probably from the agent's own model family. Recommendation: reclassify it as a sealed held-out set and commission a new blind set.
> 7. **Anthropic-only fallback for the judge.** First try to get one key from another provider (about $40 of grading). Otherwise send the short-context instruments (matcher, citation support) to a local open-weight model, and keep the holistic grader on Claude Sonnet with the same-family limitation disclosed.
> 8. **Human labelling.** There is no consolidated plan. The methodology needs 600+ labelled items and two raters, about 55–60 hours for one person. The audit proposes a one-person plan of about 20–25 hours and caps the claims it can support at "tentative".
> 9. **Missing before build:** a taxonomy file, one shared finding schema and one answer-key schema, `prereg.yaml`, encrypted storage for sealed keys in a private repo, a demo-day runbook, a documentation map for lab §5.3, and a budget.
>
> **P0 blockers:** Probe the live MCP servers. Confirm which provider keys you hold and fix the judge routing. Write the taxonomy file. Write the canonical finding schema. Fix how PDFs are read and how quotes are anchored. Set the reproducibility policy (no temperature or seeds on current Claude; no silent model fallback). Seal the blind set and decide on repo privacy.

## Coordinator

[Commit + push "Add research package loophole audit".]

The research audit is in and pushed. It's the useful kind of harsh: each note is strong alone, but the package isn't research-grade yet because the six authors never agreed on basics. The headline findings:

- **32 cross-document conflicts.** Six answer-key formats, five matching rules, four severity scales, five flaw taxonomies. The fix is one canonical taxonomy file and one shared finding schema, which the audit lists as P0.
- **The "blind" set isn't blind.** The two blind authors were given a domain exclusion list that revealed the synthetic set's design, both landed on exactly 14 defects, and their READMEs name the defects while sitting in the dev tree. The audit recommends reclassifying them as a sealed held-out set and commissioning a genuinely blind one later, with a different author model.
- **The synthetic set is template-like.** All three items share the SIT section layout, identical flaw counts, and tells like every flawed area marked "Ready". An agent could learn the template.
- **Nobody has probed the live SIT MCP servers.** Which auth header they expect decides part of the architecture. That's a P0 that needs your laptop or a network that can reach them.
- **Human labelling has no plan.** Full rigour needs 55 to 60 hours of one person's time. The audit proposes a cut-down 20 to 25 hour plan and caps what it can claim.

Seven P0 blockers, ten P1, seven P2, all in `research/audit/research_audit.md` with effort estimates.

The eval data integrity audit is still running. I'll report when it lands, then give you a consolidated picture and a proposed next step.

---

## Subagent report: Eval data integrity audit

> The audit is written to `/home/user/SIT/research/audit/eval_data_audit.md`. **2 answer-key entries are wrong, both partially**; no planted "correct" value is outright false. Nothing in `eval/` was modified and no git commands were run.
>
> 1. **Key-wrong #1: blind/item_a D01.** The key states the UK refund rule wrongly. Under UK reg. 34(5), where the trader hasn't offered to collect, the 14 days run from receipt of the goods or evidence of sending, not from notification. Under CRD Art. 13(3), offering collection (which the design does in UK and DE) removes the right to withhold. A reviewer who cites UK law correctly would fail the literal `credit_requires`. The defect itself is real.
> 2. **Key-wrong #2: research_lakehouse sound section §16 (audit plane).** Its rationale "audit holds only pseudonyms" ignores that pseudonymised data is still personal data under GDPR, and the doc's own NFR-7 invokes GDPR Art. 17. The trap is too broad: it would score as a false positive a valid point that the Art. 17(3) exemption basis should be documented.
> 3. **External facts.** About 35 checked, using vendor-owned GitHub mirrors (awsdocs, MicrosoftDocs, opensearch-project, postgres) plus search snippets, because the vendor and legislation sites are blocked; each source is labelled. Confirmed: DynamoDB: 1,000 WCU per partition, 400 KB items, LSIs block split-for-heat, global tables are last-writer-wins. SQS: 14-day maximum retention; one message group is processed serially at 300 msg/s. S3: Object Lock compliance mode; Intelligent-Tiering archive tiers are opt-in and need a restore. OpenSearch HNSW memory formula `1.1*(4d+8M)`. Azure: IoT Hub S2 = 6M msgs/day and 120 sends/s per unit; DPS group-key guidance; Stream Analytics late-arrival drop. CloudHSM: at least 2 HSMs across AZs. Standards and law: PCI 3.3.1/3.3.1.2/3.3.2; NIST 800-171 3.1.1 vs 3.13.11/16; PDPA s26 and the 3-day breach rule; Modbus 125-register limit; UL 9540A is a test method; IEEE 2030.5 TLS and cipher suite; IEEE 1547 2 s islanding trip. pgvector is not referenced in any doc. IEEE 1547 is the one caveat: the standard is paywalled, so I couldn't rule out a utility-agreement extension clause.
> 4. **Label leakage: none.** The only hits are benign (two uses of "deliberately", "wrong window", enum names, and "unintentional" matching the regex). Phrase-overlap checks found only the key quoting the docs.
> 5. **v2 integrity: all 42 statuses across the three synthetic items match the text** (with v2 line references), and F15 is present in each. One labelling ambiguity: `regressed` entries count as 5 fixed instead of the README's 6.
> 6. **Sound-section overlaps.** Some flaws cite sections the same key lists as sound. The high-risk one is lakehouse F08, which cites §16 with no disambiguation. Medium-risk ones are clinical F05/§4.3, lakehouse F01/§4, item_a D03/FR-RET-01, and item_b DEF-03/DEF-13/§7.5 and DEF-14/FR-GRID-01. No sound section hides an unplanted material defect.
> 7. **Over-strict credit rules (in P0).** Some keys require a specific fix rather than detection, e.g. item_b DEF-12 demands GNSS/PTP and clinical F06 item 3 is a remedy. Correct reviewers with other valid fixes would fail.
> 8. **Schema.** The five keys disagree on field names, severity scales (3-level vs 4-level), where v2 flaws live, and credit rules ("by substance", "core claims", "first two items", "every item"). The report proposes one canonical schema with an explicit per-flaw credit mode and a rename map for each key.
> 9. **Realism.** All five would pass as real design docs to a senior engineer; item_a and item_b are the strongest. Fixable tells: lakehouse §23 mentions "an AI coding assistant", and the payments v2 header date (2026-10-12) is later than today.
> 10. **Fix list.** P0 (5 items): D01, the lakehouse §16 rationale, F08 vs §16, the remedy-as-requirement credit items, and the DEF-03 tolerance. P1: v2 status semantics, a missing `introduced_by_fix_of` on clinical F15, and overlap annotations. P2: schema adoption, counts, neutral observations to add, and the realism nits above.

## Coordinator

[Appended a status section to research/README.md. Commit + push "Add eval data integrity audit and research status note". 28 files under research/ and eval/, clean tree.]

Everything is done and pushed to `claude/eloquent-sagan-ah5ttk`. Working tree is clean.

### What the research phase produced

Six research notes, five evaluation items, and two audits, all on the branch under `research/` and `eval/`. Every subagent ran on Opus after your correction.

### The decisions, now evidence-backed

- **Framework: custom Python state-machine loop on the Anthropic SDK.** Scored 92/100 against LangGraph 80 and PydanticAI 77. Four corrections from the evidence: use a direct MCP client (the server-side connector can't send SIT's API key header), write our own tool loop, set SDK retries explicitly, and accept that temperature no longer exists so reproducibility comes from pinning and recorded tool calls.
- **Agent model: Opus 5.5, Sonnet 5.5 for sub-tasks.** About $2 to $3 per full review with caching. Fable rejected as 2.5x the cost with multi-minute turns.
- **Grader: different provider from the agent.** Fifteen papers put same-family judge bias at 3 to 8 percentage points. If you only hold an Anthropic key, the fallback is code-checked metrics plus a local open-weight matcher, with the limitation disclosed.
- **Kaggle: techniques, not data.** No competition has ever targeted design review. Transferable: score both answer orders, length-bias controls, and quadratic weighted kappa for ordinal rubrics.

### What the audits caught

The eval data audit fact-checked about 35 external claims against vendor-owned sources and found the planted "correct" values hold up. Two answer-key entries are partially wrong: one misstates the UK refund timing rule, one sound-section trap would penalise a valid GDPR point. Zero label leakage, all 42 v2 flaw statuses verified against the text.

The research audit is the one to read first. It found 32 conflicts between the six independently written notes, and two structural problems I should own: the "blind" set isn't blind because I gave those authors a domain exclusion list that revealed the design, and the synthetic set is template-like because I gave all three authors identical flaw counts. Both are fixable and the audit says how.

### Seven P0 blockers before any code

1. Write one canonical flaw taxonomy file.
2. Write one shared finding JSON schema used by agent, matcher, and grader.
3. Probe the live SIT MCP servers for their auth header. This needs your laptop or a network that can reach them; the sandbox proxy blocks those hosts.
4. Confirm which provider keys you hold, which decides the judge routing.
5. Fix the five answer-key errors.
6. Set the reproducibility policy.
7. Seal the held-out set and decide whether the repo will be private, since a web-searching agent could otherwise find its own answer keys.

Items 3 and 4 need you. The rest I can do next. Say the word and I'll start with the taxonomy and schema, then fix the keys, then build the agent skeleton.

---

## User

> btw im onc loud and not local, right?

## Coordinator

Yes, this session runs in the cloud. Everything happened in an isolated container on Anthropic's infrastructure, not on your machine. That has three practical consequences for this project:

- **Nothing lives on your laptop yet.** All the work is on the `claude/eloquent-sagan-ah5ttk` branch at github.com/malcolm1232/SIT. When you want it locally, clone the repo and check out that branch.
- **This container is ephemeral.** It gets reclaimed after inactivity, which is why I've been pushing after every agent. Anything not pushed would be lost.
- **The network is restricted.** That's why several agents reported blocked sites (kaggle.com, arXiv, OpenAI and Google docs), and why nobody could probe the live SIT MCP servers. The outbound policy was set when the environment was created. Two of the P0 blockers from the audit, probing the SIT servers and confirming your API keys, need to happen on your laptop or in a session with a more open network policy. Docs on how the environment and its network policy are configured are at https://code.claude.com/docs/en/claude-code-on-the-web.

For demo day, the lab requires the agent to run on your own laptop, so at some point the workflow becomes: I build and push here, you pull and run locally against the real MCP servers with your real key. The robustness note already plans for that split with recorded tool fixtures that let tests run offline here and live runs happen on your machine.
