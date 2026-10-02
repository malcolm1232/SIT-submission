# Architecture decision records

Date opened: 2026-10-02. Each entry is short: context, decision, consequences, status. When a decision changes, add a new ADR that supersedes the old one rather than editing it. Paths are relative to the repo root. "Audit" means `research/audit/research_audit.md`; "lab" means the SIT AI Engineering Lab brief (September 2026), which is not committed (ADR-005).

Status values: **Accepted** (build on it), **Pending** (blocked on a named input), **Awaiting user** (a recommendation exists; the user decides), **Proposed** (accepted for planning, to be confirmed by measurement).

| ADR | Title | Status |
|---|---|---|
| 001 | Custom state-machine loop on the Anthropic SDK with a direct MCP client | Accepted |
| 002 | Claude Opus 5.5 for every agent call | Accepted (user decision) |
| 003 | Judge / grader / matcher provider | Pending (which API keys exist) |
| 004 | Evaluation tiers: S-dev, S-heldout (sealed), Blind (to be commissioned) | Accepted |
| 005 | Repository privacy and SIT material | Awaiting user |
| 006 | PDF ingestion: native PDF block plus one canonical page-marked text | Accepted |
| 007 | Quote anchoring: quote + page + section in the structured output, verified in code | Accepted |
| 008 | Where things run: live on the laptop, offline fakes and fixtures in the cloud sandbox | Accepted (user decision) |

---

## ADR-001. Custom state-machine loop on the Anthropic SDK with a direct MCP client

**Context.** Lab §4.1 and §4.6 leave the framework open. On demo day the evaluator must understand the agent in a 10-minute walkthrough and watch it change live (lab §5.4a, d). The SIT MCP servers scale to zero (1-2 min cold start), one of them (`mcp-document-intelligence`) rejects every input, and their auth header is unverified (audit U1). `research/frameworks/README.md` scored eight frameworks; the custom loop led 92 against LangGraph's 80 and stayed ahead under every reweighting. Its lead holds only if we build the robustness pieces ourselves (audit §1.2).

**Decision.**
- Python, an explicit state machine `ingest → understand → plan → research → assess → refine → verify → report` (`agent/states.py` holds the enum and transition table and prints a Mermaid diagram).
- Official Anthropic Python SDK, pinned exactly (`anthropic==1.11.0` per the frameworks note; the exact pin is in `uv.lock`). Typed findings via `client.messages.parse()` / `output_config.format` (GA).
- Direct MCP client (`mcp==2.2.0`, streamable HTTP, header-carrying HTTP client). **Not** the server-side MCP connector (beta, OAuth token only, no hook for degradation).
- A hand-written research tool loop. **Not** `tool_runner` (beta), because the stop rules, budgets, timeouts and ledger writes are exactly the conditional logic it hides.
- One `LLMGateway` and one `ToolGateway` are the only paths to the outside. The SDK runs with `max_retries=0`, and the gateways own retries, backoff, timeouts, breakers and budgets (robustness §10 item 1).
- The architecture also absorbs the other ten robustness needs (robustness §10): background parallel warm-up and `preflight`; an evidence ledger with stable IDs; verified quote anchors (ADR-007); a pinned decision-and-constraint registry; a JSON checkpoint after every stage with `resume <run_id>` and distinct exit codes; config-driven criteria, stop rules, tools, model and persona; `explain <finding-id>` and a coverage map; spotlighting with fixed action *types* (queries adapt, the URL policy does not; audit C18); a Jinja-rendered report.
- Frameworks' "switch to LangGraph if we need pause/resume" trigger is amended to "if we need durable human-in-the-loop interrupts" (audit C17); per-stage checkpoints (about 60 LOC) cover resume.

**Consequences.** Everything the evaluator sees is our code, which is what makes live changes cheap. We own about 60 LOC of checkpointing and about 40 LOC of tool loop that a framework would provide. Cross-vendor model swap is not a live-demo feature (audit C24). Beta features are kept off the critical path.

**Status.** Accepted.

---

## ADR-002. Claude Opus 5.5 for every agent call

**Context.** `research/models/README.md` originally recommended an Opus 5.5 orchestrator with Sonnet 5.5 readers (about $1.85 per run against $2.07 all-Opus). The user decided on 2026-10-02 that the agent uses Opus 5.5 for every call. Facts below were checked against the `claude-api` skill (model table cached 2026-09-25).

**Decision.**
- Model ID `claude-opus-5-5` for every call: planning, research digestion, assessment, refinement, verification and report assembly. No Sonnet or Haiku sub-tasks. The reader pattern is dropped from the architecture (it would cost $2.57 per run with Opus readers, more than the single loop's $2.18).
- `thinking: {type: "adaptive"}` (thinking cannot be disabled on Opus 5.5). Effort is set explicitly per stage in `config/agent.yaml`: `medium` for research and reading, `high` for assess, verify and report. The model's default is `medium`.
- Streaming for every call; prompt caching on a byte-stable prefix (tools, system prompt, document).
- `temperature`, `top_p`, `top_k`, `budget_tokens`, forced `tool_choice` (`any`/`tool`) and assistant prefill are never sent; all return 400 on Opus 5.5.
- **No server-side `fallbacks` in eval runs.** The skill's default advice is to opt into `fallbacks: "default"`, but its targets are other models (`claude-opus-5`, `claude-opus-4-8`), which would break this ADR and the reproducibility policy. Refusals are handled in the agent instead (robustness LLM-06). The demo can opt in with `--allow-fallback`; any fallback is recorded in the manifest (`docs/REPRODUCIBILITY.md` §3).
- `claude-opus-5-5` has no dated snapshot ID in the skill's model table; the bare ID is the most specific pin available (resolves audit U5). `response.model` is logged for every call.

**Consequences.**
- Planning cost is **$2.18 per full run** (hybrid ingestion, 20 calls, cached; range $1.67-$3.24). See `research/models/README.md` §3 and `docs/BUDGET.md`.
- One prompt-cache namespace, one effort scale and one classifier profile (`cyber`, `bio`, `reasoning_extraction`; narrower than Sonnet 5.5's). Prompts never ask the model to print its internal reasoning (that trips `reasoning_extraction`); they ask for a rationale per finding.
- Methodology ablation A4 ("different backbone model") becomes **A4e**: same model with every stage at effort `low`. The claim "results are not tied to one model" is dropped (audit C24).
- Robustness DEMO-04 ("swap the model") becomes a one-line config change *within the Opus line* or an effort change; a swap to another model is possible but is a disclosed deviation from this ADR.
- If refusals turn out to be frequent on the SIT documents (audit U6), revisit with a new ADR rather than enabling fallbacks silently.

**Status.** Accepted (user decision, 2026-10-02).

---

## ADR-003. Judge / grader / matcher provider

**Context.** Methodology requires a different model family for the matcher, the adjudicator, the G3 premise judge, the citation judge and the grader (audit C3). Whether the user holds a non-Anthropic key is unknown (audit U7). The research sandbox could not verify non-Claude model names or prices.

**Decision.** Record both branches. The user picks one after confirming which keys exist; until then nothing judge-dependent is frozen in `prereg.yaml`.

| Instrument | Branch A: a second provider's key exists | Branch B: Anthropic key only |
|---|---|---|
| Finding↔flaw matcher (short context, about 1-2K tokens per pair) | Cross-family model (GPT-6.1 Sol or Gemini 3.1 Pro; names and prices UNVERIFIED until one structured-output call succeeds) | Local open-weight model on the laptop, validated against the user's 150 labelled S-dev pairs (audit U8, §4.6). If it fails validation: Claude in batch, disclosed as same-family |
| Adjudicator, G3 premise judge, citation-support judge (short context) | Same cross-family model | Local open-weight model, same validation |
| Holistic "lecturer" grader (long context, document in the prompt) | Cross-family model | Claude, disclosed as same-family. Research recommendation: Sonnet 5.5 at effort `high` (a different model from the agent). If the user extends ADR-002's all-Opus rule to instruments: Opus 5.5. Mitigations: blinding, template normalisation, paraphrase test V9 |
| Code-checked metrics (quote existence G1/G2, page range, ledger-ID citation validity, URL resolution, planted-flaw recall from the matcher's assignments) | No model | No model |
| Headline claims rest on | Planted-flaw recall/precision, SWR, CDR, HFR, fabricated-citation rate; grader scores as support | **Only** the code-checked and locally judged metrics. Every Claude-judged number is labelled "same-family, tentative", and the limitation is stated in `docs/LIMITATIONS.md` |

**Consequences.** Branch A costs more in API (about $590 of instrument spend; `docs/BUDGET.md`) but supports a cross-family claim and the self-preference swap test (models §6 E1). Branch B is cheaper in API ($83-160 grader, $0 matcher) but costs laptop time, needs the local model to pass validation, and caps grader-based claims at "tentative" (audit C2 tiers). Methodology R4, L35 and the §8 gates need an amendment naming the same-family instruments in branch B.

**Status.** Pending: the user confirms which API keys they hold (audit P0 item 2).

---

## ADR-004. Evaluation tiers

**Context.** The current `eval/blind` items are not blind: developers can read them, the briefs carried knowledge of the eval design (fixed count of 14 flaws, sound-section traps, credit criteria), they share the synthetic template, and the generator was probably the agent's own model family (audit §4.3).

**Decision.**

| Tier | Contents | Who may read | Access budget |
|---|---|---|---|
| **S-dev** | `eval/synthetic/*` (3 items, v1 and v2) | Developers | Unlimited (tuning, calibration, pilot) |
| **Real-dev** | The SIT sample artefact | Everyone (already read) | Unlimited, qualitative only, never a generalisation claim; its distinctive terms never appear in prompts (methodology R5) |
| **S-heldout** | The current `eval/blind/item_a`, `item_b`, **reclassified** | The eval runner only, after unsealing | ≤ 3 logged evaluations in total; sealed per `docs/SEALING.md` |
| **Blind** | To be commissioned: an independent brief with no flaw count and no trap hints, a free-text author key, a different model family or a human author, PDFs with at least one figure and one table; delivered encrypted | Nobody until the final run | 1 evaluation, after `prereg.yaml` is frozen |
| **OOD** and **sound controls** | To be authored (at least 1 OOD doc, at least 2 fully sound docs; audit C22, M8) | Sealed | 1 evaluation |
| **Rehearsal pool** | Separate docs for DEMO-05 rehearsals (never the Blind set; audit C19) | Developers | Unlimited |

**Consequences.** DEMO-05 rehearsals and OVF-12 no longer touch Blind. With 2 S-heldout docs and 28 flaws, any dev→held-out gap is reported with its CI and as a difference-in-differences against B0, without a pass/fail threshold (audit C20). Per-category and ablation results are exploratory at the achieved n (audit C21). The `eval/blind` directory name is misleading and is renamed `eval/heldout` when it is sealed.

**Status.** Accepted. Sealing itself is not yet implemented; the interim rule in `docs/SEALING.md` §6 applies now.

---

## ADR-005. Repository privacy and SIT material

**Context.** Lab §5.2 requires a GitHub repository with two SIT GitHub IDs invited as collaborators, and no committed secrets. The lab brief is marked "SIT Internal" and "All rights reserved"; the brief prints a shared MCP key. The repo will hold answer keys (sealed or not) and research notes that quote the SIT sample at length.

**Options.**

| Option | For | Against |
|---|---|---|
| **1. Private repo; invite the two SIT IDs** | Meets lab §5.2 exactly. SIT material, quotes and S-dev keys stay out of public view and out of search engines and crawlers, so keys cannot leak into future model training. Sealed keys are still encrypted (defence in depth) | Nobody outside SIT can reproduce it; publishing later needs a clean-up pass |
| 2. Public repo with sealed keys | Anyone can reproduce; open-source credibility | S-dev keys and SIT quotes become public; SIT-internal content risk; eval items can be indexed and enter training corpora, which weakens every later held-out claim; the MCP key prefix in `research/robustness/scenarios.md` OPS-02 would be public |
| 3. Private now, sanitised public mirror after the evaluation period | Combines 1 with later openness | Extra work: strip SIT material, rotate canaries, decide what to do with sealed sets |

**Recommendation.** Option 1, with option 3 as an optional follow-up after SIT's evaluation ends. Independently of the choice: never commit the lab PDF, the SIT sample PDF, the MCP key or the Anthropic key (`.env` is gitignored, `.env.example` lists names only); replace the key prefix in OPS-02 with a pattern read from the environment (audit M6); run `gitleaks` in pre-commit and CI.

**Consequences.** Under option 1, sealing (ADR-004, `docs/SEALING.md`) protects held-out data against the developers and against the agent's own tools, not against the public. Evaluators reproduce from the private repo with their own keys (`docs/REPRODUCIBILITY.md` §7).

**Status.** Awaiting user.

---

## ADR-006. PDF ingestion: native PDF block plus one canonical page-marked text

**Context.** The research notes proposed four ingestion paths: native document block with a pypdf fallback (frameworks), native PDF (models), local pdfplumber/PyMuPDF then OCR (robustness), `pdftotext -layout` with `[[PAGE n]]` markers (grading). If the agent, the verifier, the matcher, the grader and the robustness oracles each read different text, "quote not found" becomes an artefact of the pipeline instead of a property of the agent (audit C14). The audit's instruction is to fix how PDFs are read and how quotes are anchored. The document-intelligence MCP server rejects every input. The SIT sample has 30 pages and 6 images; the lab input is always a PDF.

**Decision.**
1. **One canonical text, one extractor.** `ingest` runs a single pinned local extractor, **pdfplumber** (MIT licence; exact version pinned in `uv.lock`), over the PDF and writes `runs/<id>/doc.pages.txt`: page-marked text with `[[PAGE n]]` markers, normalised (Unicode NFKC, ligatures expanded, end-of-line de-hyphenation, whitespace collapsed), plus `doc.sections.json` (heading → section ID → page span). Its SHA-256 and the extractor version go in the manifest. Every verifier reads this file: the agent's verify stage, the matcher's G1/G2, the grader and the robustness oracles. PyMuPDF was rejected because its AGPL licence would attach to the submitted code; `pdftotext` because it is an external binary on the demo laptop.
2. **The model gets both views.** Every Opus call carries, in the cached prefix, the native PDF `document` block (so figures, tables rendered as images and layout are visible) **and** the canonical page-marked text as a text block. The system prompt instructs: quote only from the page-marked text.
3. **Fallbacks.** Over 600 pages or 32 MB, or if the native block is rejected: text only, disclosed in the report. A page with fewer than about 50 extracted characters but an image is flagged "image-only page" (robustness INP-04); OCR is a P1 add-on, not on the critical path.
4. `mcp-document-intelligence` is disabled by default (robustness INF-11).

**Why both views instead of native only.** Native only gives the model the best reading of figures, but its quotes come from Anthropic's internal text extraction, which the verifier cannot see; mismatches (ligatures, hyphenation, reading order) would be scored as hallucinated quotes. Text only is cheapest and fully consistent, but loses figures and image tables, which the lab's PDFs contain. Both views cost about 13K extra cached tokens (about $0.11 per run: $2.18 against $2.07) and make every quote checkable against exactly the text the model was told to quote from.

**Consequences.** Token counts for both paths must be measured with `messages.count_tokens` on the laptop (audit U3) and `research/models/cost_model.py` re-run. Native citations (`citations: {enabled: true}`) are not used for the scored output, because they cannot be combined with `output_config.format` (400). They may be used in an unscored analysis call.

**Status.** Accepted. The extractor choice is confirmed once it handles the SIT sample's tables and multi-page requirement tables (robustness INP-03).

---

## ADR-007. Quote anchoring

**Context.** The lab requires traceable findings (lab §2.4) and separation of document content from research (lab §4.2). Native citations cannot be combined with structured outputs (audit C13). The eval audit found loopholes: location-less findings escape CDR (G1), trivially short quotes pass fuzzy matching (G2), and many locations per finding widen the matcher's candidate set (G3).

**Decision.**
- Each finding in the structured output carries `locations[]` with **1 to 3** entries (the cap is enforced in code after parsing, since structured outputs do not accept length constraints). Each entry is `{page, section_id, quote}`.
- `quote` must be verbatim from `doc.pages.txt` and at least **8 tokens** long.
- External evidence is cited only by **evidence-ledger IDs** (`E-012`), never by URL; the renderer turns IDs into URLs. Each finding has `source: doc | external | inference` (audit C10, C11).
- **Verification in code** (the `verify` stage and `oracles.anchors_resolve()` share one function): normalise the quote the same way as the canonical text; try an exact substring match on the cited page; else fuzzy match (`rapidfuzz` partial ratio ≥ 0.90) restricted to the cited page ±1 **and** inside the cited section's span. On success, store `char_start`, `char_end`, `match_score` and `matched_page`.
- On failure: one repair turn asks the model to re-quote from the cited section. If it still fails, the finding is marked `anchor_status: unresolved`, shown in the report under "unverified", and counted as NON_SPECIFIC for precision.
- A finding with no resolvable location cannot be a recommendation (lab §2.3 requires an issue and evidence).

**Consequences.** Anchors are checkable by anyone from the run directory. The anchor-failure rate and the quote-length distribution are reported (audit G2). A cited ledger ID must have been read before it is cited (`read_before_cite`).

**Status.** Accepted. The 0.90 threshold and the 8-token minimum are PROPOSED DEFAULTS, calibrated on S-dev only, then frozen in `prereg.yaml`.

---

## ADR-008. Where things run

**Context.** The demo runs on the user's laptop (lab §5.4b). The cloud development sandbox has no Anthropic API key and cannot reach the SIT MCP servers (its proxy returned 403).

**Decision.**
- **Laptop:** all live runs, MCP probing (audit P0 item 1: auth header, protocol, `tools/list`, cold-start error shape, DI rejection text), cassette recording, `count_tokens` measurements, the S-dev pilot, every eval-matrix run, L1/L2 robustness, rehearsals and the demo.
- **Cloud sandbox:** code, L0 tests with `FakeLLM`, `FakeMCP` and `FakeClock`, strict replay of recorded cassettes (`tools.jsonl`) and recorded LLM responses (`llm.jsonl`), static checks. No test in the sandbox may need a network or a key; `pytest-socket` enforces it.
- Recorded fixtures flow one way: recorded on the laptop, redacted (no auth headers, no keys), committed, replayed in the sandbox.

**Consequences.** Until the first laptop recording session, every MCP behaviour in the fakes is an assumption (robustness §11) and is marked as such. Laptop sessions are scheduled work, not incidental.

**Status.** Accepted (user decision, 2026-10-02).
