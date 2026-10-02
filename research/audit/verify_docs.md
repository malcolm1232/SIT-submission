# Verification of the governing documents (docs/) and the all-Opus model note

Date: 2026-10-02. Scope: `docs/DECISIONS.md`, `docs/REPRODUCIBILITY.md`, `docs/DEMO_DAY_RUNBOOK.md`, `docs/DOCUMENTATION_MAP.md`, `docs/SEALING.md`, `docs/BUDGET.md`, `research/models/README.md`, `research/models/cost_model.py`, plus the ablation section of `research/methodology/README.md`. API facts were checked against the `claude-api` skill (model table cached 2026-09-25; `SKILL.md`, `shared/model-migration.md` § Migrating to Claude Opus 5.5 and § `refusal` stop reason, `shared/prompt-caching.md`, `shared/cost-optimization.md`, `python/claude-api/batches.md`). The lab brief was read at pages 7-9. Files under `eval/blind/` were not opened (SEALING §6); only their names were listed.

Several files were being edited concurrently by another reconciliation pass (methodology README, frameworks README, models README). Edits here were made with exact-match replacements against the current on-disk state; nothing from that pass was reverted.

Verdicts: **OK** (matches the source), **Fixed** (was wrong or incomplete; corrected in place), **Added** (the docs were silent; the fact was added), **Open** (needs a decision or a file outside this scope).

---

## 1. API facts against the claude-api skill

| # | Claim in the docs | Where | What the skill says | Verdict | Fix applied |
|---|---|---|---|---|---|
| 1.1 | `claude-opus-5-5` is the exact ID; there is no dated snapshot; the bare ID is the most specific pin | ADR-002, REPRO §2, models §1 | Model table lists `claude-opus-5-5`; "use only the exact model ID strings ... never append date suffixes" | OK | None |
| 1.2 | `temperature`, `top_p`, `top_k` are rejected (400) on Opus 5.5 | ADR-002, REPRO §1 | Thinking table, Opus 5.5 row: sampling "Removed - 400" | OK | None |
| 1.3 | `budget_tokens` is rejected; thinking cannot be disabled | ADR-002, REPRO §1, models §1 | `{type:"disabled"}` and `{type:"enabled", budget_tokens}` "return 400 at every effort level" | OK | None |
| 1.4 | There is no `seed` parameter | REPRO §1, §9 | The skill documents no `seed` parameter anywhere in the Messages API surface; it does not state its absence explicitly | OK (not contradicted; skill silent) | None |
| 1.5 | Forced `tool_choice` `any`/`tool` and assistant prefill return 400 | ADR-002, models §7 | Both confirmed for Opus 5.5 | OK | None |
| 1.6 | `fallbacks: "default"` sends refused requests to "other models (`claude-opus-5`, `claude-opus-4-8`)" | ADR-002, REPRO §3, models §1 | Re-runs a declined request server-side on "the model Anthropic recommends for that category"; read permitted targets from `allowed_fallback_models` on `/v1/models` ("expect Claude Opus 5 / claude-opus-4-8"); per-category routing not published; **`reasoning_extraction` declines are not retried**; the fallback model runs **without Opus 5.5's thinking blocks**; if the fallback model is rate-limited, the refusal is returned with `stop_details.recommended_model`; Claude API and Claude Platform on AWS only; rejected on Batches | Fixed (accurate but incomplete; the target list was presented as fixed) | ADR-002, REPRO §3 and models §1 now describe category routing, `allowed_fallback_models`, the non-retried category, the dropped thinking blocks and the rate-limit case |
| 1.7 | Decision to send no `fallbacks` in eval runs, demo opt-in only | ADR-002, REPRO §3, models §1 | Skill default: "include the server-side `fallbacks` parameter by default ... Tell the user you've enabled it; drop it only if they decline" | OK (the user's all-Opus decision is a documented decline; fallback would change the serving model, which breaks the pinned-model policy) | ADR-002 now states explicitly that the all-Opus decision is the reason for declining the skill default |
| 1.8 | Fallback detection via `fallback_message` in `usage.iterations` and `response.model`; beta header `server-side-fallback-2026-07-01` on `client.beta.messages`; rejected on Batches | REPRO §3, models §7 | All confirmed ("served-by signal is a `fallback_message` entry in `usage.iterations`"; `-2026-07-01` pairs with the `"default"` scalar form; "Rejected on the Batches API") | OK | None |
| 1.9 | Native PDF document blocks supported, "600 pages, 32 MB" | ADR-006, models §1-2 | "Limits: **32 MB request**, 600 pages (100 for 200k-context models)" | Fixed (32 MB is the request limit; base64 inflates the PDF by 4/3 and the request also carries the canonical text, so the practical PDF ceiling is about 23 MB) | ADR-006 §3 and models §1 now say "request over 32 MB" and tell `ingest` to check encoded request size |
| 1.10 | Citations cannot be combined with `output_config.format` | ADR-006, ADR-007, REPRO §5 | "Incompatible with `output_config.format` (returns a 400)" | OK | None |
| 1.11 | Prompt caching: minimum cacheable prefix | (absent) | Opus 5.5: **512 tokens** | Added | ADR-002 and models §3: the ~78K prefix always clears 512 |
| 1.12 | Prompt caching: breakpoint limit | (absent) | "Max **4** `cache_control` breakpoints per request"; automatic caching consumes one slot | Added | ADR-002: plan uses 2 of 4 (one explicit after the canonical text, plus top-level automatic for the tail) |
| 1.13 | A top-level `effort` change invalidates the messages cache, "about $0.40 to rewrite a 78K prefix ... one cache rewrite per run" | models §3 | Invalidation hierarchy: `thinking` or `effort` change does not keep the messages-tier cache; the per-message effort system message (beta `mid-conversation-output-config-2026-07-01`) avoids it | Fixed (the rewrite covers the whole context at the switch call, not just the prefix, and the planned config has two switches: plan high → research medium → assess high). `cost_model.py` "Sensitivity": $3.38 instead of $2.18, **+$1.20 per FULL run** | models §3, ADR-002 consequences and BUDGET §4 (unbudgeted-risk paragraph); new function `opus_run_switches` in `cost_model.py` |
| 1.14 | Effort levels `low`..`max`; Opus 5.5 default is `medium`; set it explicitly | ADR-002, models §1-2 | "`low`/`medium`/`high`/`xhigh`/`max` - **default `medium`**"; "set it explicitly" | OK | ADR-002 now names all six stages (plan and refine were missing) to match runbook §4.1 |
| 1.15 | Refusal arrives as HTTP 200 with `stop_reason: "refusal"` and `stop_details.category`; check before reading content | REPRO §3, runbook §7 #4, models §7 | Confirmed, plus: **branch on `stop_reason`, never on `stop_details`** (category can be `null`); refusals can come **mid-stream** (discard the partial); classifier and model-own refusals both surface as `refusal`; a refusal still counts against rate limits | Fixed (incomplete) | REPRO §3 and runbook §7 #4: null category, mid-stream discard, rate-limit note |
| 1.16 | Runbook / LLM-06: retry once "with professional-review framing" | REPRO §3, runbook §7 #4 | "The docs give no prompt change that avoids Claude Opus 5.5's false positives" | Fixed (labelled as our heuristic; success rate to be measured, not assumed) | REPRO §3, ADR-002, runbook §7 #4 |
| 1.17 | Opus 5.5 classifiers `cyber`, `bio`, `reasoning_extraction`; `reasoning_extraction` not retried on fallback | ADR-002, models §2 | Confirmed in § Safeguards for Opus 5.5 | OK | None |
| 1.18 | Opus 5.5 prices $4 in, $5 cache write (5-min), $0.20 cache read, $20 out; Batch 50 % off every token incl. cache | BUDGET §1, models §3, `cost_model.py` | $4 / $20; cache read $0.20; write 1.25× = $5; batch "50% off every token in the request, including cache reads and writes" | OK | None |
| 1.19 | `models.retrieve` gives `id`, `created_at`, `max_input_tokens`, `max_tokens` | REPRO §2 | Confirmed (plus `display_name`, `capabilities`) | OK | None |
| 1.20 | 4.7+ tokenizer gives "about 30% more tokens" | models §2 | "~1×-1.35× as many tokens" relative to Opus 4.6 and earlier | Fixed | models §2 |
| 1.21 | Fast mode on Opus 5.5 is $8/$40, up to 2.5x output speed | models §2 | Confirmed | OK | None |
| 1.22 | Sonnet 5.5 server-side fallback covers only `cyber` and `frontier_llm` | models §2 | Confirmed | OK | None |

---

## 2. Budget arithmetic and run count

`python3 research/models/cost_model.py` was run before and after the fixes. Every figure in `docs/BUDGET.md` now traces to a printed line or to the arithmetic shown.

### 2.1 Per-run and per-condition figures (unchanged; all reconcile)

| BUDGET figure | Script line | Match |
|---|---|---|
| $2.18 / $2.07 / $1.67 / $2.38 / $2.36 / $3.24 | ALL-OPUS per-run section | Yes |
| FULL 2.18, B0 0.63, B0-$ 2.18, A1 1.02, A2 1.52, A3 2.00, A4e 1.91, A5 1.02 | per-condition section | Yes |
| Grader $0.57 (GPT-6.1 Sol), $0.30 (Sonnet batch), $0.57 (Opus batch); matcher+judges $1.05 | grading section | Yes |
| Cut 1 $65 = 20 runs × (2.18 + 1.05); cut 2 $97 = 30 × (2.18 + 1.05); cut 3 $103 = 14 flaws × 3 × (1.5K in + 0.3K out at GPT-6.1 Sol) × 408 runs = 0.252 × 408; cut 4 $95 = 18 × (1.91 + 1.05 + 0.57) + 12 × (1.02 + 1.05 + 0.57); cut 5 $29 = 9 × (2.18 + 1.05); cut 6 $145 = 24 × 2.18 + 24 × 0.63 + 48 × (1.05 + 0.57) | arithmetic | Yes ($534 ≈ "about $535"; × 1.3 = $695) |

### 2.2 Mismatches found and fixed

| # | Mismatch | Evidence | Fix |
|---|---|---|---|
| 2a | "Matched runs: 408 (lines 2-8)": lines 2-8 sum to 348. The script's 408 includes line 1 (dev iteration, 60) | `cost_model.py` `matched_runs` | Text now says lines **1-8** |
| 2b | Line 5 (v2 re-review) counted one run per (doc, k). Methodology §5 requires a fresh-session run **and** a variant with the v1 review supplied as context; `metrics.md` §8's copy-through rate needs the second | methodology §5 "v2 re-review" row | Line 5 = v2 docs × 2 variants × k |
| 2c | Line 5 counted "SIT v2" as a pre-demo item. The SIT update arrives on demo day, has no key (Real-dev) and is line 9 work | runbook intro; methodology §1.1 Real-dev | Line 5 = 3 synthetic v2 docs only |
| 2d | Real-dev SIT v1 runs (needed for `runs/sit_v1_frozen` and rubric grading) were implicit | methodology §1.1; runbook §1 | New line 10: FULL, k = 3, graded, not matched |
| 2e | 433 assumed 12 primary docs; 7 do not exist (4 Blind assumed, 1 OOD, 2 sound controls) | ADR-004; `eval/` listing | BUDGET §2a and the script now print a CURRENT-ITEMS matrix |

### 2.3 Run count against k × items × conditions

Current item count: 3 synthetic × 2 versions + 2 S-heldout + the SIT doc = **9 items**; keyed v1 docs = 5.

| Line | Formula | Planned (12 primary docs) | Current items |
|---|---|---|---|
| 1 Dev iteration | fixed | 60 | 60 |
| 2 Pilot | 3 S-dev × k3 × {FULL, B0} | 18 | 18 |
| 3 Primary | docs × k5 × {FULL, B0} | 12 × 10 = 120 | 5 × 10 = 50 |
| 4 Ablations | held-out/Blind docs × k3 × 6 conditions | 6 × 18 = 108 | 2 × 18 = 36 |
| 5 v2 re-review | 3 v2 docs × 2 variants × k3 | 18 (was 12) | 18 |
| 6 Milestones | 2 accesses × 2 docs × k3 | 12 | 12 |
| 7 Overfitting | 2 probes × 3 docs × k3 | 18 | 18 |
| 8 Robustness L1 | ~15 × k≈4 | 60 | 60 |
| 9 L2 / demo day | fixed | 25 | 25 |
| 10 Real-dev SIT | 1 × k3 | 3 (new) | 3 |
| **Total** | | **442** (was 433) | **300** |
| Agent USD | | **$796** (was $777) | $582 |
| Graded / matched | | 291 / 414 (was 282 / 408) | 149 / 272 |
| Budget to approve (worst branch × 1.3) | | **$1,812** (was $1,772) | $1,236 |

142 planned runs ($214) depend on commissioned docs. With 5 keyed docs the primary comparison is below methodology §4b's own 8-doc minimum for a 0.10 difference at σ_d = 0.10, so it is exploratory until Blind exists (stated in BUDGET §2a).

---

## 3. Lab brief coverage (pages 7-9)

| Lab item | Row in DOCUMENTATION_MAP | Verdict |
|---|---|---|
| 5.1 source code, configuration files, prompts, instructions, workflow definitions, memory configuration, orchestration logic, supporting documentation, dependencies, installation steps, execution procedures | §2, one row each (11 rows) | OK |
| 5.1 design review outputs from the lab session | §2 | OK |
| 5.1 supporting evidence, references and research findings | §2 | OK |
| 5.1 evaluators can understand, reproduce, review | §2 | OK |
| 5.2 GitHub repo, designated SIT officer invited as collaborator | §3 | OK (row reworded) |
| 5.2 must contain all materials to review, **deploy** and execute | — | **Added** row (README install/configure/run, REPRO §7, fresh-clone check) |
| 5.2 clearly organised; installation, configuration and execution instructions | §3 | OK |
| 5.2 material not shareable via GitHub goes by email | §3 | OK |
| 5.2 grant access **before the submission deadline** to `SIT-calebying`, `Makienhui-sit` | merged into one row | **Added** separate row (invitations sent and accepted; 7-day invitation expiry) |
| 5.2 repo **remains accessible throughout the evaluation period** | merged into one row | **Added** separate row (no delete/archive/rename/transfer/history rewrite; mirror never replaces the private repo) |
| 5.2 identify dependencies, datasets, configuration settings, model requirements, third-party services | §3 | OK |
| 5.2 secrets not committed; instructions to configure the environment | §3 | OK |
| 5.3 all eight topics | §1, one row each | OK (Memory row now cites ADR-009) |
| 5.4 session format (walkthrough, live execution on an SIT artefact, on-the-spot modification) | — | **Added** row |
| 5.4 a explain design (optional deck) | runbook §8 | OK |
| 5.4 b laptop that runs and can be modified | runbook §1-3 | OK (status now notes code dependencies) |
| 5.4 c run on a new SIT artefact, show output | runbook §5-7 | OK |
| 5.4 d modify on request, show new behaviour | runbook §4 | OK |

---

## 4. Internal consistency

| Check | DECISIONS / docs | spec / research | Verdict | Fix |
|---|---|---|---|---|
| Severity scale | Runbook uses "high or critical" | `Severity` enum critical/high/medium/low; weights 8/4/2/1 | OK | None |
| Disposition enum | Runbook "triage (refinement vs investigation / prototyping / testing / governance)"; `dra explain` printed `triage: prototyping` | `Disposition`: refinement_now, needs_investigation, needs_prototyping, needs_testing, governance_decision, no_change | Fixed (naming) | Runbook §5.1 uses `disposition` and the enum values |
| ≥ 8-token quote | ADR-007 "at least 8 tokens" | Schema `pattern` `^\s*\S+(\s+\S+){7,}\s*$`; taxonomy `min_quote_tokens: 8` | OK (ADR now says "whitespace-separated tokens" and cites both) | ADR-007 |
| Fuzzy ≥ 0.90 | ADR-007 `rapidfuzz` partial ratio ≥ 0.90 | `DocAnchor` description and taxonomy "fuzzy ratio >= 0.90"; metrics G1 "token-level partial-match ratio ≥ 0.90" | OK on threshold; scorer named differently in three places | Open (P2, spec) |
| ≤ 3 locations | ADR-007 "1 to 3, enforced in code" | `doc_anchors` `minItems: 1`, `maxItems: 3`; spec README: strict mode strips these, so code enforces | OK | ADR-007 cites the schema |
| Match window | ADR-007: cited page ±1 **and inside the cited section's span** | Taxonomy, `DocAnchor`, metrics G2: **cited section ±1** | **Contradiction** | ADR-007 now uses section ±1 plus page ±1; status note records the clarification. Spec does not state the page bound (Open, P2) |
| Field names | ADR-007 `locations[]` `{page, section_id, quote}`; per-finding `source` | `doc_anchors[]` `{doc_id, section_ref, requirement_ids, quote, page}`; `evidence[].source_type` | Fixed | ADR-007 |
| Where match metadata lives | ADR-007 stored `char_start` etc. and `anchor_status` on the finding | `DocAnchor` is `additionalProperties: false`; no `anchor_status` field | Fixed | ADR-007: `runs/<id>/anchors.json` anchor table (REPRO R0 already names an "anchor table") |
| Stop reasons | REPRO §8 enum | Taxonomy and `StopReasonCode` identical | OK | Runbook 2b now maps the new live rule to `sufficient_evidence` + `detail` |
| Frameworks "switch to LangGraph if we need pause/resume across processes" vs robustness P0 resume (OPS-04, NET-01, BEH-25, LLM-02) | ADR-001 had a one-line amendment only; nothing on intra-stage resume ("without repeating completed tool calls") | Frameworks conditions table was amended concurrently and already points to an "ADR-009" | **Was unresolved** | **ADR-009 added**: stage checkpoints written atomically, append-only journal (`tools.jsonl`, `llm.jsonl`, ledger) with replay-from-self so completed tool calls are not repeated, byte-exact replay of assistant turns (preserved thinking on Opus 5.5), refusal on config/prompt drift, exit codes 0/2/3/4/130, L0 tests; LangGraph only for durable human-in-the-loop interrupts or if the tests cannot pass within ~200 LOC (weighed against its `mcp<2` pin) |
| Stage vs phase names | Stages `refine`; effort key `refine` | Schema `Phase` uses `revise` | Inconsistent naming, not a contradiction (phase = provenance, stage = state) | Open (P3) |

---

## 5. Methodology amendment (A4 → A4e)

On arrival the concurrent reconciliation pass had already replaced the A4 row with **A4e** (same model, every stage at effort `low`) in `research/methodology/README.md` §4, and the results-table row. Added here:

- A one-line "What is lost by replacing A4 with A4e" note under the interpretation rules: no condition separates harness value from model value, so no result may be called model-independent; A4e only measures effort sensitivity within Opus 5.5.
- §4b item 5 Holm family made explicit: {A1, A2, A3, A4e, A5, B0, B0-$}.

Not changed: §7.1's manifest (already marked superseded) still lists `A4`; `metrics.md` §12's Holm family still lists `A4` (outside this scope; Open, P2).

---

## 6. Judge-provider branches

| Check | Before | After |
|---|---|---|
| Both branches described in ADR-003 and models §1 | Yes, but models §1 omitted the "local model fails validation → Claude in batch" path (BUDGET B3) | models §1 branch-B row adds it |
| What branch B discloses | ADR-003: headline claims rest only on code-checked and **locally judged** metrics; every **Claude**-judged number labelled "same-family, tentative"; limitation in `docs/LIMITATIONS.md`. Models §1: "judge-free metrics" and "every **LLM**-judged number" labelled | Models §1 aligned to ADR-003 wording, names `docs/LIMITATIONS.md` and the methodology amendment (R4, L35, §8 gates). Models §4.9 notes that planted-flaw recall depends on the (validated) matcher, so it is not strictly judge-free |
| All-Opus scoped to the agent, grader pending | ADR-002 said "every call" without stating scope | ADR-002 opens with "Scope: the agent only ... instruments are ADR-003, which is Pending"; ADR-003 context says ADR-002 does not bind instruments; models §1 agent row says the same |

---

## 7. SEALING.md feasibility

| Step | Check | Result | Fix |
|---|---|---|---|
| `age -p -o <out> <in>` | Usage in age 1.1.1 `--help` and the GitHub README: `age [--encrypt] --passphrase [--armor] [-o OUTPUT] [INPUT]` | Correct. Round trip run through a pseudo-terminal in the sandbox: exit 0, plaintext recovered | None |
| `age -d` with no identity | README: "Passphrase protected files are automatically detected at decrypt time" | Correct; tested, including decrypt to a redirected stdout while the passphrase is read from the tty | Unseal step 4 now streams to `tarfile` |
| Plaintext on stdin | Tested: age reads input from stdin and the passphrase from `/dev/tty` | Works | Seal step 4 streams the in-memory tar to stdin, so no plaintext tar touches disk |
| Empty passphrase | README: "By default age will automatically generate a secure passphrase" | Undocumented trap | SEALING §2 failure-modes row |
| Install on macOS / Linux | README: `brew install age`, `port install age`, `apt install age` (Debian 12+, Ubuntu 22.04+), `pacman -S age`, `apk add age` | Runnable on both | SEALING §2 setup row |
| Deterministic tar | GNU flags (`--sort=name`, `--mtime`) are absent from macOS bsdtar | Not portable as written | Use Python `tarfile` with fixed metadata |
| "Shred the plaintext tar" | `shred` is not on macOS; unreliable on SSD / copy-on-write file systems | Not portable | Replaced by never writing the plaintext tar |
| Round-trip check | Needs the passphrase a third time | Unstated | Stated |
| GPG alternative | `gpg --symmetric --cipher-algo AES256` is valid syntax; GnuPG 2.4.4 in the sandbox could not start `gpg-agent`, so the flow could not be exercised; not preinstalled on macOS; `--passphrase` also needs `--pinentry-mode loopback` | Plausible but untested here | SEALING §2 rows corrected |
| Interim rule | SEALING §6, six numbered rules, effective immediately | Stated | None |

---

## 8. Runbook dry-run

Walked as the participant, in order. "Planned" means named in DECISIONS, spec or the runbook's own §4.1 and marked as planned; "missing" means referenced but defined nowhere.

| Runbook step | Depends on | Exists today? | Defined / marked? | Finding |
|---|---|---|---|---|
| §1 freeze, `make smoke` | `Makefile`, L0 suite | No | Planned (robustness DEMO-13) | Listed in new §9 |
| §1 `runs/sit_v1_frozen`, backups, cassettes | Agent, recorder | No | Planned (ADR-008) | §9 |
| §2 `.env` keys, `dra preflight` | CLI | No | Planned | §9 |
| §2 model check: `config/agent.yaml` line 2 / line 11 | §4.1 layout | No | Planned; layout is self-consistent (line 2 `model`, line 11 `allow_fallback`) | OK |
| §3 `--no-warm`, `--warm --keep-warm 120` | CLI flags | No | Defined only here | §9 lists the flags |
| §4.2 #1 append criterion to `config/criteria.yaml` | File, 4-line entry format | No | Planned (DOC MAP §2) | OK as planned |
| §4.2 #2a `stop_rules.yaml` line 3 `max_tool_calls` | §4.1 | No | Planned; line numbers match | OK |
| §4.2 #2b new `@register` rule; line 2 `active`; uses `min_independent_sources` (line 8) | `agent/stop_rules.py`; stop-reason enum | No | Planned; **new code would not validate** because `StopReasonCode` is closed | Fixed: report `sufficient_evidence` with `detail: two_sources_agree` |
| §4.2 #3 `tools.yaml` lines 6/9/12 and 7/10/13 | §4.1 | No | Planned; lines match | OK. `auth_header` still UNVERIFIED (U1) |
| §4.2 #4 model on line 2, effort lines 4-9 | §4.1 | No | Planned | Fixed: preflight allowlist (models with adaptive thinking and `effort`; Haiku 4.5 refused), cross-provider not live, cache restart noted |
| Less likely: persona line 12, `config/persona.yaml` | persona file | No | Planned (robustness DEMO-09) | OK |
| Less likely: `executive_summary` "schema field already exists" | `spec/finding.schema.json` `Review` | Spec exists | **Field does not exist** (Review keys: schema_version ... run_manifest) | Fixed: add to schema before freeze or render in template only |
| §5 `dra review --deadline 540 --previous` | CLI, delta mode | No | Planned | §9 |
| §5.1 `dra explain` | Run directory, anchor table | No | Planned | Now reads `anchors.json` (ADR-007) |
| §6 replay, resume | Replay, ADR-009 | No | Planned | §9 |
| §7 `--faults <ID>` | Fault injection | No | Planned (robustness §5) | §9 |
| §7 #4 refusal drill | Gateway refusal handling | No | Planned | Fixed: null category, mid-stream discard, heuristic retry |
| Config `max_tokens: 64000` vs manifest `max_tokens_by_stage` | — | — | Mismatch | §9 open point (add keys below line 12 so pinned lines stay put) |

New runbook §9 lists every build dependency with the step that needs it.

---

## Edit log

| File | Edit |
|---|---|
| `docs/DECISIONS.md` | Index row for ADR-009 |
| | ADR-001: resume bullet points to ADR-009 |
| | ADR-002: "Scope: the agent only" bullet; reader-pattern cost compared on the same 65K base ($2.57 vs $2.07); effort list names all six stages; caching facts (512-token minimum, 4 breakpoints, effort-change invalidation); `fallbacks: "default"` described precisely and the decline justified; refusal-retry labelled heuristic; new "Effort switches cost cache" consequence with options; DEMO-04 consequence widened to Claude models with adaptive thinking and effort |
| | ADR-003: context says ADR-002 does not bind instruments |
| | ADR-006 §3: 32 MB is the request limit; ~23 MB practical PDF ceiling; check encoded size |
| | ADR-007: `doc_anchors[]` field names, schema and taxonomy citations, whitespace-token definition, `source_type`, section ±1 plus page ±1 window, `anchors.json` for match metadata and `anchor_status`, status clarification note |
| | ADR-009 added (durable resume) |
| `docs/REPRODUCIBILITY.md` | §3: refusal handling details (stop_reason not stop_details, null category, mid-stream discard, rate limits, heuristic retry); `fallbacks: "default"` semantics (category routing, `allowed_fallback_models`, non-retried category, thinking blocks dropped, rate-limited fallback) |
| `docs/BUDGET.md` | Header: reconciliation note. §2 table: line 5 two variants on 3 synthetic v2 (18 runs, $39), line 9 notes SIT v2, new line 10 (3 runs, $7), subtotal 442 / $796, correction paragraph. New §2a current-items matrix (300 runs, $582; 142 runs / $214 depend on commissioned docs; power caveat). §3: graded 291, matched 414 (lines 1-8), branch costs recomputed. §4: totals recomputed (A/B3 $1,812, B1 $1,147, B2 $1,249), current-items column, budget to approve $1,812, spend-limit figure $1,035, unbudgeted effort-switch risk paragraph, wall-clock line |
| `docs/DOCUMENTATION_MAP.md` | §1 memory row cites ADR-009. §3: collaborator row split into three (collaborator; access before deadline with acceptance and 7-day expiry; accessible through the evaluation period) and a new "review, deploy and execute" row. §4: session-format row; b-d statuses note code dependencies |
| `docs/DEMO_DAY_RUNBOOK.md` | Header: nothing exists yet except probe script and spec. §4.2 #2b: closed stop-reason enum mapping. §4.2 #4: preflight model allowlist, no live cross-provider, cache restart. Less-likely: `executive_summary` is not in the schema. §5.1: disposition naming and `anchors.json`. §7 #4: refusal details. New §9: build dependencies and open points |
| `docs/SEALING.md` | §2: install commands for macOS and Linux, GPG not on macOS and agent failure, empty-passphrase autogeneration, `--pinentry-mode loopback`. §3: Python `tarfile` for determinism, stream tar on stdin (no plaintext tar on disk, no shred), round trip needs a third passphrase entry, unseal streams `age -d` into `tarfile` with path checks, tests note that the pty flow was exercised |
| `research/models/README.md` | Agent row scoped to the agent; PDF 32 MB per request; branch-B row adds the B3 path, ADR-003 headline-claim wording, `docs/LIMITATIONS.md` and the methodology amendment; branch-B "why" says Claude-judged; fallback note describes category routing and dropped thinking; tokenizer 1.0-1.35x; reader pattern compared on the same base; caching paragraph corrected to whole-context rewrite (+$1.20 per run) plus 512-token minimum and 4 breakpoints; §4.9 matcher caveat |
| `research/models/cost_model.py` | Budget matrix rebuilt as `matrix(primary_docs, ablation_docs, v2_docs)` from the methodology formula (two v2 variants; line 10 Real-dev SIT); `counts()` for graded and matched runs (lines 1-8); prints PLANNED and CURRENT-ITEMS matrices with all four branches; new `opus_run_switches()` sensitivity |
| `research/methodology/README.md` | §4: "What is lost by replacing A4 with A4e" line. §4b item 5: Holm family lists A4e explicitly |

---

## Open issues

| Priority | Issue | Owner / next step |
|---|---|---|
| **P1** | Effort switches between stages rewrite the prompt cache: about +$1.20 per FULL run, ~$500 over the planned matrix, more than the agent-line margin. Not in the budget figures | Decide at build time: one effort per conversation, or the per-message effort beta (ADR-002); measure `cache_creation_input_tokens` at stage boundaries before the S-dev pilot |
| **P1** | 7 of the 12 planned primary docs (4 Blind, 1 OOD, 2 sound controls) do not exist; 142 runs depend on them; with 5 keyed docs the primary comparison is underpowered | Commission the Blind set (ADR-004) or pre-register the 5-doc comparison as exploratory |
| **P1** | Token base still UNVERIFIED (audit U3); every dollar figure scales with it | `messages.count_tokens` on the SIT PDF on the laptop, then re-run `cost_model.py` |
| **P1** | ADR-003 pending (which API keys exist) and ADR-005 awaiting the user | User |
| P2 | Spec does not state the page ±1 bound and names the fuzzy scorer differently from ADR-007 and `metrics.md` G1 ("fuzzy ratio" vs "partial ratio" vs "token-level partial-match ratio") | Amend `spec/taxonomy.yaml` `anchor_rules.quote_match` and the `DocAnchor` description to one scorer (`rapidfuzz.fuzz.partial_ratio` on normalised text) and the page bound |
| P2 | No schema for `runs/<id>/anchors.json` (ADR-007) | Add to `spec/` alongside the manifest |
| P2 | `Review` has no `executive_summary`; runbook DEMO-08 depends on a decision | Add an optional field to the schema before `demo-freeze`, or render it in the template only |
| P2 | `research/methodology/metrics.md` §12 Holm family still lists `A4` | Change to `A4e` (outside this change's scope) |
| P2 | Branch B requires amending methodology R4, L35 and the §8 gates to name same-family instruments (ADR-003 consequence) | After ADR-003 resolves |
| P2 | The reframed refusal retry is unmeasured | Count refusals and retry success in L1 (LLM-06, INP-14b) and report the rate |
| P2 | `config/agent.yaml` has one `max_tokens`; the manifest records `max_tokens_by_stage` | Decide at build; keep §4.1 pinned lines unchanged |
| P2 | S-heldout access budget (≤ 3): the ablations on S-heldout must run inside the primary evaluation's access, or they consume one | State in `prereg.yaml` |
| P3 | `Phase` enum uses `revise` while the state machine and config use `refine` | Align names or document the mapping in `docs/ARCHITECTURE.md` |
| P3 | GPG alternative could not be exercised in the sandbox (`gpg-agent` would not start) | Use `age` (recommended); test GPG on the laptop only if needed |
| P3 | GitHub invitations expire if not accepted in time | Send early; confirm acceptance; record the date |
