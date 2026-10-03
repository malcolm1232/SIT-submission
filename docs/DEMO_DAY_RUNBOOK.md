# Demo day runbook (lab §5.4)

Date written: 2026-10-02, before the agent code exists. Commands, file paths and line numbers describe the **planned** layout; **nothing named here exists yet** except `scripts/probe_mcp_servers.py` and the `spec/` files. §9 lists what must be built before this runbook can be walked. They are binding on the build: `tests/test_config_layout.py` must assert that every key named in §4 sits on the line given here, so this runbook cannot drift from the code. Update both together.

The session has four parts (lab §5.4): (a) explain the design; (b) run on a laptop that can be modified; (c) live run on a new SIT artefact; (d) on-the-spot modification. The new artefact is probably an **updated version** of the SIT design (lab §1.5), so a frozen v1 review of the SIT sample is prepared in advance for delta mode.

Unknowns to settle with SIT beforehand: slot length (assumed: 10-minute live run inside a longer interview; audit U4; the lab brief states no time limit for the live execution, so the 540 s demo deadline is a project assumption pending SIT's answer, kept as a configurable safety net, `docs/USER_DECISIONS.md` #34), how the PDF is handed over (USB, email, shared drive), and whether venue Wi-Fi allows outbound HTTPS to `*.azurecontainerapps.io` and `api.anthropic.com`.

CLI (one entry point, `dra`, alias of `sit-review`; all built, see `dra --help`): `dra preflight`, `dra review` (`--k N` runs N independent runs plus a group manifest; `--profile NAME` overlays `config/profiles/NAME.yaml`), `dra explain`, `dra coverage`, `dra resume`, `dra replay`; `make smoke` runs the offline check in about 10 s (the selftest plus the config, prompt-lock, CLI and leakage tests) and `make test` runs ruff and the whole suite (`Makefile`, built 2026-10-03).

---

## 1. The day before (T−1 day)

- [ ] Code freeze: tag `demo-freeze`. After this, only the live modifications in §4 are made, and only during the session.
- [ ] `make smoke` passes offline in ≤ 60 s (robustness DEMO-13).
- [ ] Frozen v1 review of the SIT sample by the final agent exists at `runs/sit_v1_frozen/` (needed for `--previous`; audit M9).
- [ ] Backup recorded runs for the fallback (§5 and §6), recorded with the final code **after** the freeze: one complete run of the SIT sample, `runs/demo_backup_sit_v1/`, and one delta pair, `runs/demo_backup_delta/` (a synthetic v1→v2 pair), each a complete run directory (`llm.jsonl`, `tools.jsonl`, `state.json`, `checkpoints/`, `effective_config.json`, `text/`) so `dra replay` works with no network. A run recorded before the latency redesign does not replay (`docs/USER_DECISIONS.md` #30), so neither may be an older recording. Check `dra replay` on both the day before (it refuses, exit 2, a directory that lacks what it needs and names it; see `agent/README.md` "Replay").
- [ ] Fresh tool cassettes recorded on the laptop within the last 7 days for the SIT sample (`--transport record`, servers warm).
- [ ] Rehearsal log shows the last 3 rehearsals (robustness DEMO-05 on the rehearsal pool, never on Blind) finished inside 10 minutes, and each §4 modification was timed (≤ 3 min config, ≤ 5 min code; audit C23).
- [ ] Printed one-page cheat sheet: §4 table, §5 command, §7 drills.
- [ ] Plan to warm all four MCP servers before the slot, not only the two enabled ones. The owner's probe of 2026-10-03 measured cold starts of 34.4 s (internet search), 29.3 s (browser), 39.5 s (research) and 70.1 s (document intelligence), against 0.04 s warm (`research/robustness/mcp_probe_findings.md`). `dra preflight --warm` warms only the servers enabled in `config/tools.yaml`, so a server switched on live in §4 starts cold: either enable it before the T−10 warm-up, or accept up to 70 s of cold start on its first call.

## 2. Environment checklist (laptop)

| Item | Check | Pass |
|---|---|---|
| Python and dependencies | `uv sync --frozen --offline` | Succeeds without network (robustness OPS-08) |
| Secrets | `.env` has `ANTHROPIC_API_KEY` and `SIT_MCP_API_KEY`; nothing printed on screen. Never `cat .env` on the projector | `dra preflight` reports both present by name only |
| Model | `config/agent.yaml` line 2 is `model: claude-opus-5-5`; line 11 is `allow_fallback: false` | Preflight's 1-token call and `models.retrieve` succeed |
| MCP servers | Enabled set in `config/tools.yaml`; document intelligence disabled | Preflight table green, or the degraded mode named |
| Fallback data | `runs/sit_v1_frozen/`, `runs/demo_backup_*`, cassettes present | `dra preflight` checks they exist |
| Git state | Clean tree at `demo-freeze` | `git status` clean |
| Disk and power | ≥ 20 GB free; charger; power-saving and sleep disabled | |
| Network | Venue Wi-Fi plus a phone hotspot as backup | `dra preflight` passes on each |
| Screen | Terminal font ≥ 18 pt; editor open on `config/`; report viewer ready; notifications off | |
| Timer | A visible stopwatch | |

## 3. Timeline on the day

| When | Action | Command |
|---|---|---|
| T−30 min | Set up laptop and network. Run the checklist in §2. Do not warm servers yet (warming too early risks them scaling back to zero) | `dra preflight --no-warm` |
| **T−10 min** | **Pre-warm the MCP servers.** Sends `initialize` and `tools/list` to every enabled server in parallel with a 150 s cold-start allowance and one retry, then keeps pinging every 120 s until stopped. The idle timeout of the containers is unknown, so a single warm-up 10 minutes early is not enough on its own | `dra preflight --warm --keep-warm 120` (leave running in a second terminal) |
| T−3 min | Final status table: each server, the LLM, fallback data. Every dependency green, or the degraded mode named and accepted (robustness DEMO-14) | `dra preflight` |
| T−0 | Start the walkthrough (part a); the keep-warm loop keeps running | |
| End of session | Copy the session's run directories into `outputs/lab_session/<date>/` (lab §5.1 requires the outputs generated during the lab session, with evidence) and commit them | |

## 4. On-the-spot modifications (part d)

The four most likely requests, with the exact file and lines each one touches. Every change is followed by `make smoke` (≤ 60 s, offline) and then a demonstration: `dra review <pdf> --plan-only` (prints the plan, zero tool calls) when the change shows in the plan, or a short live rerun (`--profile demo --deadline 300`) when it shows in behaviour. The new value appears in the run manifest. A deadline shorter than the profile's stage limits (265 / 465 / 530 s on the run clock, `config/profiles/demo.yaml` `stage_limits_s`) is allowed: the limits are absolute seconds, so a rerun such as `--deadline 300` holds a deadline below them, and the runtime scales the three limits by the deadline over 540 s and announces it on the first progress lines (`WARN deadline 300 s is not above this profile's stage limits ... scaled by 300/540 to 147 / 258 / 294 s`; not rehearsed). What such a short rerun produces is not yet measured, so prefer `--plan-only` where the change shows in the plan, and otherwise rerun with the profile's own deadline. A deadline longer than 540 s scales the three limits up by the same rule, announced the same way (`--deadline 900` gives 441 / 775 / 883 s), so a longer rerun gives every stage its share of the added time; a deadline from 531 to 540 s keeps them as set.

### 4.1 Planned config files (line numbers are part of the contract)

`config/agent.yaml`
```yaml
 1  # config/agent.yaml - line numbers pinned by tests/test_config_layout.py
 2  model: claude-opus-5-5
 3  effort:
 4    plan: high
 5    research: high
 6    assess: high
 7    refine: high
 8    verify: high
 9    report: high
10  max_tokens: 128000
11  allow_fallback: false
12  persona: generalist_architect
```

`config/stop_rules.yaml`
```yaml
 1  # config/stop_rules.yaml - line numbers pinned by tests/test_config_layout.py
 2  active: [sufficient_evidence, no_marginal_gain, budget_tool_calls, budget_tokens, deadline]
 3  max_tool_calls: 30
 4  max_research_iterations: 4
 5  max_input_tokens: 4000000
 6  deadline_seconds: 3600
 7  no_marginal_gain_window: 2
 8  min_independent_sources: 2
```

Line 6 is the default for runs without `--deadline` or a profile (3600 s since 2026-10-02, sized for a high-effort run). The demo runs at 540 s through `config/profiles/demo.yaml` (`--profile demo`), which also sets per-stage effort (`medium`, research `low`), the two reserves (refine 200 s, verify and verdict 75 s) and the three stage limits on the run clock (stage 1 ends by 265 s, refine by 465 s, the verdict call by 530 s; `docs/DECISIONS.md` ADR-011); the pinned lines are unchanged by it. The three listings in this section are checked against the config files by `tests/test_config_layout.py`. The profile's values win over `config/agent.yaml` lines 4-9 and `config/stop_rules.yaml` line 6: in a run with `--profile demo`, an effort or deadline change goes in `config/profiles/demo.yaml` (effort lines 19-24, deadline line 27) or on the command line (`--deadline`), not in the pinned lines.

`config/tools.yaml` (server URLs live in `config/endpoints.yaml` so these line numbers stay fixed)
```yaml
 1  # config/tools.yaml - line numbers pinned by tests/test_config_layout.py
 2  auth_env: SIT_MCP_API_KEY
 3  auth_header: Authorization        # sent as "Bearer <key>"; probe 2026-10-03, all four servers
 4  servers:
 5    - name: mcp-internet-search
 6      enabled: true
 7      allow_tools: ["*"]
 8    - name: mcp-research-information
 9      enabled: true
10      allow_tools: ["*"]
11    - name: mcp-browser-automation-pw
12      enabled: false
13      allow_tools: ["*"]
14    - name: mcp-document-intelligence
15      enabled: false
16      allow_tools: []
17  url_policy: url_policy.yaml
```

`config/criteria.yaml`: a list under `criteria:`; new criteria are always **appended at the end of the file** (each entry is 4 lines: `id`, `description`, `applies_to`, `research_hints`).

`agent/sit_review_agent/stop_rules.py`: a registry; each rule is a function decorated with `@register("<name>")` that receives the run state, the stop-rule config and the elapsed seconds, and returns `StopDecision(stop, code, detail)`. New rules are appended at the end of the file.

### 4.2 The requests

| # | Likely request | File and lines | Change | Show it | Target |
|---|---|---|---|---|---|
| 1 | "Add a review criterion, e.g. operational cost / accessibility / data residency" (robustness DEMO-01) | `config/criteria.yaml`, append 4 lines at end of file | `- id: operational_cost` / `description: "Is running cost estimated, bounded and monitored?"` / `applies_to: [all]` / `research_hints: ["cost benchmarks for the named services"]` | `--plan-only`: the criterion appears in the plan; full run: it appears in the coverage map and the report (as a finding or "checked, no issue") | ≤ 3 min |
| 2a | "Stop after at most 5 searches" (DEMO-02) | `config/stop_rules.yaml` line 3 | `max_tool_calls: 5` (or CLI `--max-tool-calls 5`, no edit) | Live rerun: ledger has ≤ 5 tool calls; `stop_reason: budget_tool_calls` in the manifest | ≤ 3 min |
| 2b | "Stop when two independent sources agree" (a new rule) | `agent/sit_review_agent/stop_rules.py`, append about 8 lines at end of file; `config/stop_rules.yaml` line 2 | New `@register("two_sources_agree")` function: stop when every high or critical finding that needs external evidence has ≥ `min_independent_sources` distinct-domain ledger entries supporting it. Add `two_sources_agree` to the `active:` list on line 2. The stop-reason code is a **closed enum** (`spec/finding.schema.json` `StopReasonCode`, `spec/taxonomy.yaml` `stop_reasons`), so the rule reports `code: sufficient_evidence`, `group: decision`, `detail: "two_sources_agree"`; adding a new code live would also mean editing the schema and taxonomy and would fail `spec/validate_examples.py` | `make smoke` (the L0 stop-rule test runs the new rule against the fake transcript); live rerun shows `stop_reason.detail: two_sources_agree` | ≤ 5 min |
| 3 | "Disable a tool / run without web search" (DEMO-03) | `config/tools.yaml` line 6 (internet search), 9 (research), 12 (browser) | `enabled: false`; or narrow line 7, 10 or 13 to a list of tool names (`allow_tools: ["search"]`). No edit: `--disable-tool mcp-internet-search` or `--no-tools` | `--plan-only`: the plan no longer uses the tool; report header lists disabled tools; zero calls to it in `tools.jsonl` | ≤ 3 min |
| 4 | "Change the model / make it think harder or faster" (DEMO-04) | `config/agent.yaml` line 2 (model), lines 4-9 (effort per stage) | Within ADR-002: change effort, e.g. line 5 `research: low` for speed, or line 6 `assess: max` for depth (for a run with `--profile demo`, edit the same key in `config/profiles/demo.yaml` lines 19-24 instead: the profile overrides lines 4-9). If the evaluator asks for another model: change line 2 (e.g. `claude-opus-5` or `claude-sonnet-5-5`); preflight validates it (LLM-12) and accepts only models that take adaptive thinking plus `output_config.effort` (Opus 5.5, Opus 5, Opus 4.8, Opus 4.7, Sonnet 5.5, Sonnet 5); Haiku 4.5 is refused (no `effort`, `budget_tokens` only, 200K context and a 100-page PDF limit). The manifest records it; say clearly that this deviates from the all-Opus decision. Another *provider* is not a live change (ADR-001; audit C24). Note that a model or top-level effort change starts a new prompt cache, so the first rerun call is slower and dearer | Rerun; manifest `effort_by_stage` / `requested_model` and `served_models` show the change | ≤ 3 min |

Less likely, prepared: change the persona (`config/agent.yaml` line 12 → `security_architect`, defined in `config/persona.yaml`; DEMO-09); add an executive summary of ≤ 150 words (`agent/sit_review_agent/report/templates/report.md.j2`, uncomment the `executive_summary` block; DEMO-08). **The `Review` schema in `spec/finding.schema.json` v1.0 has no `executive_summary` field**: either add it (optional, `maxLength`-checked in code) to the schema before `demo-freeze`, or render the summary from existing fields (`verdict`, top-ranked `findings`) in the template only; show the plan before execution (`--plan-only`; DEMO-12).

**If a live change breaks something:** run `make smoke`; if it fails and the fix is not obvious within a minute, revert the file (`git checkout -- <file>`), rerun `make smoke`, and explain what the change would need.

## 5. The 10-minute live run (part c)

| Clock | Step | What to say and show |
|---|---|---|
| 0:00 | Receive the PDF. Save it to `inbox/`. Look at its title page and revision history: is it a new design or an updated version of the SIT sample? | "The agent never saw this file; it only knows its hash once ingested." |
| 0:30 | Start the run. New design: `dra review inbox/<file>.pdf --profile demo`. Updated SIT design: add `--previous runs/sit_v1_frozen`. In a second terminal, type `dra replay runs/demo_backup_sit_v1` and leave it unstarted (the fallback below) | The demo profile sets a 540 s deadline (a minute of margin in the assumed 10-minute slot; the 540 s figure is a project assumption pending SIT's answer on slot length, `docs/USER_DECISIONS.md` #34), `medium` effort on every stage (research `low`) and three stage limits on the run's own clock: stage 1 ends by 265 s, refine by 465 s, the verdict call by 530 s (`docs/DECISIONS.md` ADR-011). Every clock time below is the run time plus 0:30. Measured once, document-only: the report at 382.3 s (clock 6:52; `docs/live_runs/rehearsal_concurrent_1/MEASUREMENT.md`). Predicted, not measured, with research: 389.3 to 438.3 s (clock 6:59 to 7:48; `docs/BUDGET.md` §1.1) |
| 0:30-4:55 | **Stage 1 (run time 0-265 s): ingest, then understand, plan and four assess shards at once**; research starts when understand and plan are both done and is cut at 265 s. A status line appears at least every 10 s. From about run time 125 s (clock 2:35), a line per draft finding as each completes, labelled draft and unverified | "Design content and external research are kept apart: research enters only as ledger entries with IDs. The four assessors read only the document and their own criteria, so they do not wait for the plan." Point at the draft findings as they arrive; name the research stop reason |
| 4:55-8:15 | **Merge and refine (run time 265-465 s)**: the shard findings are merged in code, then one refine call returns a revision per finding (merge, withdraw, rank, severity, disposition, decision links, research evidence). Refine is cut at 465 s at the latest | "The deadline is enforced inside the model calls, so one slow call cannot take the report with it." If refine is cut, the merged findings stand, ordered by severity and confidence, and the report says so |
| 8:15-9:30 | **Verify, verdict, report (run time 465-540 s)**: anchor verification in code (resolved / repaired / unresolved; one repair call only when more than 60 s of slack remains), a verdict-only model call that ends by 530 s (clock 9:20) or gives way to the rule-based verdict, then the code-rendered `report.md`, by 9:30 at the latest (run time 540 s) and earlier when the stages finish early | "Every quote is checked in code against the canonical page text; unresolved anchors are reported, not hidden." Verdict and confidence on the first page; for updated designs, the delta section (resolved / open / regressed / new) |
| Report to 10:00 | Walk one finding: issue, rationale, evidence, expected benefit, link to the design objective. Then `dra explain <finding-id>` (§5.1) and `dra coverage` (criteria × sections, including "checked, no issue") | Close on the limitations section (degraded tools, unresolved items) |

**Cuts and what the report says.** A shard cut at 265 s keeps every finding it finished; its criteria without a finding are marked not assessed, and the report says so. A cut research stops with `stop_reason: deadline` and the report carries a partial-evidence caveat (robustness BEH-24). A cut refine leaves the merged findings ordered by severity and confidence, disclosed. A cut verdict call gives the rule-based verdict. Only when no shard finished a single finding by 265 s is the verdict `not_assessed`, headed "Not assessed (out of time before assessment)": it is not a judgement of the design (robustness LLM-05).

**The fallback (replay).** Keep `dra replay runs/demo_backup_sit_v1` typed and unstarted in the second terminal from 0:30.

- If no draft finding has appeared by run time 265 s (clock 4:55), say so, start the replay, and walk `explain` and `coverage` on it while the live run finishes.
- If the live report is partial, show it first with its disclosed cuts, then the replay for depth.
- If it is `not_assessed`, show the replay, and rerun with `--profile demo --deadline 900` during questions: the runtime scales the three stage limits up by 900/540 to 441 / 775 / 883 s on the run clock and says so on the first progress lines (`WARN deadline 900 s is longer than the 540 s run ... scaled up by 900/540 to 441 / 775 / 883 s`; not rehearsed).
- The replay shows the SIT sample only, never the unseen PDF. It is stamped "replayed evidence"; say that aloud.

### 5.1 `dra explain <finding-id>` (provenance)

Reads only the run directory (works offline and in replay). Returns in under 5 s (robustness DEMO-06). Default run: the latest; `--run runs/<id>` to pick one. Prints:

- **Header:** the finding as reported: ID (`FND-nnn`), kind, severity, disposition (schema enum: `refinement_now`, `needs_investigation`, `needs_prototyping`, `needs_testing`, `governance_decision`, `no_change`), rank, confidence, title, statement and verdict impact (the verdict conditions and per-objective labels that cite it).
- **1. Document anchors:** for each `doc_anchors[]` entry, document, page and `section_ref`, the verbatim quote, the anchor status and match method (exact or fuzzy, with the score), and the character span in `text/<doc_id>.pages.txt` (read from the run's anchor table `anchors.json`, ADR-007).
- **2-3. Evidence and the tool calls behind it:** for each ledger ID (`EV-nnn`), the source tag (`doc`, `external` with its authority class, or `inference` with the entries it is derived from), whether it supports the claim, the URL or citation, the quote, the title, the retrieval time, the snippet as the agent saw it, and the tool call (`call-nnnn`: server/tool, arguments, status, time, and whether it was replayed).
- **4. Criteria that produced it:** the configured criterion IDs and their questions.
- **5. History:** the stage that created the finding, every stage that changed it (with a before/after diff of the fields that changed), the provenance, and the `llm.jsonl` call IDs involved (`llm-nnnn`).
- **6. Checks:** how many anchors verified, `read_before_cite` for each external entry, and any challenge to the approved-decision registry (`AD-nnn`).

Real output, abridged (2026-10-03, the built-in selftest fixture: an invented room-booking design, served offline with `--transport fake`). The explain help uses `FND-007` as its example ID; this run has `FND-001` to `FND-003`:

```
$ dra explain FND-001
FND-001 (risk, severity high, disposition: refinement_now, rank 1, confidence 0.92)  run demo-k1
  E-mail plan cannot send peak-day reminders
  Section 6.2 assumes the e-mail service has no daily sending limit, but the published plan allows 2,000 messages a day, ...
  Verdict impact: condition: Move to an e-mail plan whose daily quota covers peak-day reminders.; objective Reminder before each slot: fit_with_conditions

1. Document anchors
  [1] DOC-design p.11 §6.2
      "The selected e-mail service has no daily sending limit, so reminders are sent individually as each slot approaches."
      resolved: exact match, score 1.0, matched page 11, chars 276-391 in text/DOC-design.pages.txt

2-3. Evidence (ledger) and the tool calls behind it
  EV-002 external (primary_official), supports: https://docs.example-mail.invalid/plans
      quote: "The Starter plan allows up to 2,000 messages per day."
      tool call call-0002: mcp-internet-search/fetch args {"url": "https://docs.example-mail.invalid/plans"} status ok at 2026-10-02T19:17:01Z (replayed)

4. Criteria that produced it
  claims_and_external_constraints: Are factual and quantitative claims about products, standards, regulations and platform limits correct and current? (lab §1.2, §3.2)

5. History
  assess (llm-0006): created
  refine (llm-0007): revised: Confidence raised: the quota is stated by the provider itself. [confidence: 0.85 -> 0.92]
  verify (llm-0008): verify: anchors checked, evidence hydrated from the ledger [repaired_anchors: [] -> [1]]

6. Checks
  anchors 2/2 in the report verified
  EV-002: read_before_cite ok
  registry: no challenge to an approved decision
```

An ID that is not in the report exits 2 with `error: FND-099 not in <run_dir>/report.json`.

### 5.2 Handing the review over from `dra ui`

The finished-review page has three actions above the verdict, in this order.
**Download** saves the review as one HTML file (the run's `report.md` shown as HTML, no script, nothing loaded from the network, the chat transcript appended as "not part of the review"), with `report.md` and `report.json` beside it; a replayed run keeps its "replayed evidence" stamp.
**Email** sends the HTML file and `report.md` to one typed address through the SMTP server in `config/ui.yaml`; set `host`, `username` and `from` there the day before, and `export SIT_UI_SMTP_PASSWORD=...` in the shell that starts `dra ui` (the password is never written to a file). Without both, the button is disabled and says "Email is not configured: see config/ui.yaml". Each send is logged to `runs/<id>/ui/outbox.jsonl` without the content.
**Share** shows the page's address on the laptop's network only when the server was started with `dra ui --host 0.0.0.0 --allow-remote`; anyone on that network can open it while the laptop serves it, with no login. A loopback server shows the restart line instead.
On the Review page, a pasted https link to a PDF is fetched by the server when the review starts (URL policy checks, public hosts only, at most 50 MB) and saved under `runs/<id>/ui/input/`, so the command shown names the saved file.

## 6. Offline and degraded fallbacks

| Situation | What still works | Do this |
|---|---|---|
| SIT MCP servers down or key revoked, internet and Anthropic fine | Doc-only review of the new PDF, live (robustness INF-24, INF-07) | Run normally; the agent switches to doc-only and the report says "No external research was possible". Narrate it as designed behaviour. If `SIT_MCP_API_KEY` is not set at all, the run stops at once with exit 2 before any model call (INF-08): set the key, or rerun with `--no-tools` |
| Venue network blocks the MCP hosts but not Anthropic | Same as above, or `--transport replay` for the SIT sample only | Prefer the live doc-only run of the new PDF |
| No internet at all | **Cannot review an unseen PDF** (no local model; robustness NET-02). The run exits 3 with "no network" within about 10 s of its first model call. Can show recorded runs | Switch to the phone hotspot first. If that fails: `dra replay runs/demo_backup_sit_v1` and `dra replay runs/demo_backup_delta` (both stamped "replayed evidence"), walk through `explain` and the coverage map, and offer to run the new PDF as soon as connectivity returns and send the outputs to the SIT officer |
| Anthropic API down or rate-limited for a long time | Checkpoints up to the last completed stage | `dra resume <run_id>` when it recovers; meanwhile, show the replayed backups |

Replay uses strict cassettes and the recorded `llm.jsonl`; it never calls a network and never invents output.

## 7. Failure drills: top 5 robustness scenarios

Each drill is rehearsed before the day with the fault-injection flag (`--faults <SCENARIO-ID>`, robustness §5) and once for real where possible.

| # | Scenario | How it shows up live | What the agent does (designed) | What you do and say | Rehearse with |
|---|---|---|---|---|---|
| 1 | **INF-01 cold start** (a server slept despite the warm-up) | Progress line "waking mcp-research-information (~90 s)" | Warm-ups run in parallel with ingest and understand, which need no tools; 150 s cold-start allowance; the server is not marked dead inside that window | "The containers scale to zero; we warm them in the background while the document is read, so this costs us almost nothing." Keep narrating ingest | `--faults INF-01`; live: leave servers idle ≥ 30 min, then run |
| 2 | **INF-07 shared-key 401 / INF-24 all tools down** | Preflight or first call reports 401, or every server times out | One confirmation retry, then all four servers are disabled together (they share one key); the run continues doc-only; the message names `SIT_MCP_API_KEY`, never its value; the report header says no external research was possible | Check the key name in `.env` off-screen; if it is right, continue doc-only and explain the degradation in the limitations section | `--faults INF-07`, `--faults INF-24`, `--no-tools` |
| 3 | **LLM-01/02/03 rate limit, spend cap or overload** | Progress line shows backoff ("429, retry after 15 s" or "529, retry 2/5") | Honour `retry-after`; jittered backoff; SDK retries off so attempts are counted once; **no model switch** (ADR-002). After the budget: checkpoint and exit with the "LLM unavailable" exit code | Wait through short backoffs. If it exits: `dra resume <run_id>` once it recovers; if the cause is the spend cap, raise the limit in the Anthropic Console (off-screen) and resume. Meanwhile show a replayed backup | `--faults LLM-01`, `LLM-02`, `LLM-03` |
| 4 | **LLM-06 refusal** (a security-heavy section trips a classifier) | Progress line "assess §7: model declined (category: cyber); retrying with review framing" | Checks `stop_reason` before parsing (never `stop_details`, whose category may be `null`: the progress line then says "category: none given"); a mid-stream refusal's partial output is discarded; one retry with professional-review framing (our heuristic; the skill documents no prompt fix for Opus 5.5 false positives); if it persists, marks that section "model declined" and completes every other section. No fallback model in eval mode; on demo day, `--allow-fallback` is available but is recorded in the manifest and the report | "The model's safety classifier declined one section; the agent records it rather than guessing, and the rest of the review is complete." Do not toggle `--allow-fallback` mid-run | `--faults LLM-06`; L1 with the clinical-protocol fixture (INP-14b) |
| 5 | **NET-01 network lost mid-run** | Tool and LLM calls fail as network errors; progress line "offline, checkpointed at stage research" | Checkpoint after every stage; ledger already holds earlier tool results; tools go doc-only; if the LLM stays unreachable, the run halts with a resumable checkpoint | Switch to the hotspot, then `dra resume <run_id>`: it continues from the last completed stage without repeating completed tool calls | `--faults NET-01`; physical drill: turn Wi-Fi off at about 200 s, back on after 2 min |

Also drilled, lower priority: Ctrl-C then `resume` (OPS-04; `--faults OPS-04` interrupts research, `--faults BEH-25` crashes assess with a partial report); `max_tokens` mid-JSON (LLM-07); a broken live code change (DEMO-13, §4).

## 8. Talking points for part (a), in order

1. The problem framed as the lab frames it (lab §1.2-1.4): review against objectives; recommend only when justified; explain "no change" when the design is fine.
2. Architecture: `docs/ARCHITECTURE.md` is the document to study for this part (its §13 is a 15-point walkthrough script naming the file to open at each point); the state machine diagram printed from `agent/sit_review_agent/states.py`; the two gateways; the ledger; the registry of approved decisions; checkpoints (`agent/README.md`, sections "State machine", "Module map" and "The phase contract").
3. Why a custom loop and why all Opus 5.5 (`docs/DECISIONS.md` ADR-001, ADR-002).
4. How documents are read and quotes anchored (ADR-006, ADR-007).
5. How it decides to stop researching (`config/stop_rules.yaml`, the stop-reason enum).
6. How we know it works: judge-free metrics on planted flaws, held-out data sealed, k runs with CIs (`docs/REPRODUCIBILITY.md`, `docs/SEALING.md`), and the limitations we disclose.

## 9. Build dependencies (what must exist before this runbook can be walked)

Verified on 2026-10-02 by walking the runbook as the participant (`research/audit/verify_docs.md` item 8). Only `scripts/probe_mcp_servers.py`, `spec/` and the docs exist today. Everything below is **to be created**; each line names the runbook step that needs it.

| Needed | Used by | Defined in |
|---|---|---|
| `dra` CLI entry point with `preflight` (`--no-warm`, `--warm`, `--keep-warm`), `review` (`--deadline`, `--previous`, `--plan-only`, `--max-tool-calls`, `--disable-tool`, `--no-tools`, `--transport`, `--faults`, `--allow-fallback`, `--k`), `explain` (`--run`), `coverage`, `resume`, `replay`. **Built** (2026-10-02; also `--profile`, `coverage --run/--depth/--json`, `replay --pdf/--v1/--previous`); `dra replay` of a live run on the `claude_code` backend with live tools still needs the tool-catalogue logging named in `agent/README.md` "Replay" | §2-§7 | this runbook; `docs/REPRODUCIBILITY.md` §6-§7 |
| `config/agent.yaml`, `stop_rules.yaml`, `tools.yaml` with the exact line layout of §4.1; `criteria.yaml`, `endpoints.yaml`, `url_policy.yaml`, `persona.yaml` (with `generalist_architect` and `security_architect`) | §2, §4 | §4.1; ADR-001; `docs/SEALING.md` §5 |
| `tests/test_config_layout.py` pinning §4.1 line numbers | Header contract | this runbook |
| `agent/sit_review_agent/stop_rules.py` registry with `@register`; `agent/sit_review_agent/states.py`; `agent/sit_review_agent/report/templates/report.md.j2` with a commented `executive_summary` block | §4.2, §8 | ADR-001; §4.1 |
| `Makefile` targets `smoke` (offline, about 10 s) and `test` (ruff plus the whole suite): **built** (2026-10-03). `hooks` (the pre-commit hook of `docs/SEALING.md` §3) is not built | §1, §4 | robustness DEMO-13; `docs/SEALING.md` §3 |
| Fault injection (`--faults <SCENARIO-ID>`) for INF-01, INF-07, INF-24, LLM-01/02/03, LLM-06, NET-01 | §7 | `research/robustness/` §5 |
| Checkpoints, journal and `resume` | §6, §7 | ADR-009 |
| Run artefacts: `runs/sit_v1_frozen/`, `runs/demo_backup_sit_v1/`, `runs/demo_backup_delta/`, fresh cassettes | §1, §2, §6 | ADR-008 (recorded on the laptop) |
| `inbox/` and `outputs/lab_session/` directories | §3, §5 | DOCUMENTATION_MAP §2 |
| The rehearsal pool (not the Blind set) and a rehearsal log | §1 | ADR-004 |

Open points the build must settle: `auth_header` is settled (`Authorization`, sent as `Bearer <key>`; the owner's probe of 2026-10-03 reached all four servers with it and got HTTP 401 without it, audit U1 closed); per-stage effort is kept (settled 2026-10-03: every call is its own conversation and on the `claude_code` backend phases never share a cache entry, ADR-002 amendment note); `max_tokens` is one value in `config/agent.yaml` while the manifest records `max_tokens_by_stage` (apply the single value to every stage, or add per-stage keys **below** line 12 so the pinned lines do not move).
