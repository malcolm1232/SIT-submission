# Limitations, assumptions and known constraints

Date: 3 October 2026, brought in line with the code on 4 October 2026.
This file answers lab §5.3 "any assumptions, limitations or known constraints".
Each item says what the agent or its evaluation cannot claim, and names the file where it is recorded or measured.

## The agent

### Evidence and input

When the SIT MCP servers are down, unreachable or revoked mid-run, the review is document-only, and the report discloses it as a degradation (`docs/ARCHITECTURE.md` §5, `docs/USER_DECISIONS.md` #13).
On the first with-tools run on the lab's document every web search failed on a closed MCP session, so that review rests on the document and one scholarly search (`docs/live_runs/sit_sample_tools_1/MEASUREMENT.md` "Tools").
The agent does not see images in a PDF: the default Claude Code backend accepts text only, so figures, diagrams and tables drawn as images are invisible to the model, and the report says so as `DEG-001` (`docs/live_runs/sit_sample_tools_1/MEASUREMENT.md` "Disclosed limitations").
The six assess shards start at about 2 s, before research, so no shard sees external evidence, a trade accepted for the time slot (`docs/USER_DECISIONS.md` #37 and #40).
External evidence reaches a finding only through refine, whose `keep` revisions append ledger entries as `added_evidence`; the verdict call sees the verified findings and how research ended, not the ledger, so a finding refine did not reach carries no external evidence (`agent/sit_review_agent/llm/outputs.py` `FindingRevisionDraft`, `prompts/report.md`).
The search tool's `fetch_top_n` and the research server's content retrieval fetch pages on the server side, where the agent's URL policy cannot see them, and this is still an open decision (`research/robustness/mcp_probe_findings.md` "For a follow-up worker").

### Tools that are off

The document-intelligence server is disabled because its only probed call was rejected and no `https://` document has ever been read through it (`config/tools.yaml`, `research/robustness/mcp_probe_findings.md`).
The browser-automation server is disabled because it keeps one browser session shared by every caller and has no domain allowlist (`config/tools.yaml`, `research/robustness/mcp_probe_findings.md`).

### Time and cost

The 900 s deadline of the demo profile is the owner's choice of 2026-10-05, not yet measured, because the lab brief states no time limit for the live run; it is a configurable value, not a product limit (`docs/USER_DECISIONS.md` #34 and #47, `config/profiles/demo.yaml`).
A deadline other than the profile's scales the stage limits and the two reserves by the same factor; a run at such a deadline is not measured, and one so short that a stage cannot start one model attempt says so in a WARN line before its first model call (`docs/USER_DECISIONS.md` #48).
Every cost in this repository is the Claude Code CLI's estimate, not a billed amount (`docs/BUDGET.md` basis note, `docs/live_runs/QUALITY_COMPARISON.md` "Caveats").
A model call cut by a limit is logged with unknown usage, so the cost of such a run is a lower bound and is labelled as one (`docs/USER_DECISIONS.md` #28, `docs/ARCHITECTURE.md` §6).
The cost with working search was measured once, on the rehearsal of 4 October 2026: $7.37 recorded, a lower bound because two calls ended early, about $8.86 with an estimate for them (`docs/live_runs/sit_sample_ui_2/MEASUREMENT.md`, `docs/EXPLAIN_AS_IT_RUNS.md`).

### Robustness seen live and not

The MCP session fix (reopen a closed session, retry once, reopen a session idle over 60 s) held on the live servers on 4 October 2026: 8 calls met a closed session, were retried after 3 reopens and all succeeded (`docs/live_runs/sit_sample_ui_2/MEASUREMENT.md` "Tools", `docs/USER_DECISIONS.md` #38).
The real idle timeout of the SIT servers is not known, so the 60 s reopen threshold is a guess from one run (`config/tools.yaml` `session_idle_reopen_s`).
32 of the 88 robustness scenarios are blocked offline as laptop-only or static and have not been run (`tests/robustness/results/robustness_summary.txt`).

### Re-assessment of an updated document

The re-assessment path (`--previous`) has been run live once, document-only, on the synthetic payments v1 and v2 pair, and never on the lab's document or with tools (`docs/live_runs/reassess_payments_v2_1/MEASUREMENT.md`).
That run was not graded against the answer key, so its resolved and still-open classification is unscored (`docs/live_runs/reassess_payments_v2_1/MEASUREMENT.md` "Not verified").
In that run three prior findings were left out of the classification (`docs/live_runs/reassess_payments_v2_1/MEASUREMENT.md` "Prior findings not accounted for"); since then every prior finding gets exactly one status with `--previous`: refine is asked once for any it left out, the rest are recorded as still open and "not re-examined" and disclosed, and INV-13 fails a report that misses one (`agent/sit_review_agent/delta.py`, `agent/sit_review_agent/invariants.py` `check_INV_13`).
That rule has not been run live yet.
Three of its assess calls were cut by the stage limit, so its cost of $4.50 is a lower bound (`docs/live_runs/reassess_payments_v2_1/MEASUREMENT.md` "Result").

### Scope of the build

The chat on the `dra ui` page is a reading aid over the finished review, kept off the evaluated path; it is not part of the review and was not evaluated (`docs/ARCHITECTURE.md` §10, `agent/sit_review_agent/ui/chat.py`).
There is no persistent memory across runs beyond re-assessing an updated document against a frozen prior review, by design, because cross-run learning on a small evaluation set would be an overfitting channel (`docs/ARCHITECTURE.md` §11).
There is one model provider: another provider would be one more `LLMGateway`, but none is built (`docs/ARCHITECTURE.md` §11, `agent/sit_review_agent/llm/backend.py`).
The Anthropic API backend exists behind the same protocol but every live run so far went through the Claude Code CLI (`docs/HANDOFF.md`, `docs/DECISIONS.md` ADR-010).

## Reproducibility

Claude Opus 5.5 has no temperature or seed, so a re-run reproduces the distribution of results, not the same review; only everything downstream of the recorded model answers is reproducible byte for byte (`docs/REPRODUCIBILITY.md` §1).
Anthropic can update the model behind `claude-opus-5-5` without changing the ID, and that drift cannot be ruled out (`docs/REPRODUCIBILITY.md` §2).
A recorded run replays byte for byte only at the commit that recorded it; at the current tip the committed runs diverge or are refused (`README.md` "Reproduce").
The reproducibility levels R2 and R3 need a Claude login and, for R3, the SIT servers, which may not exist after the evaluation period (`docs/REPRODUCIBILITY.md` §7).
The repository was installed and checked on macOS only (`README.md` "Requirements").

## The evaluation

The quality comparison is one document and one run per arm, so no difference in it is statistically meaningful (`docs/live_runs/QUALITY_COMPARISON.md` "Caveats").
The answer keys are not signed off by the owner, so every score is exploratory and none may be reported as confirmatory (`docs/USER_DECISIONS.md` #26, `harness/sit_eval/lc12.py`).
The pre-registration is not frozen yet (`docs/live_runs/QUALITY_COMPARISON.md` "Caveats").
The agent, the scoring judge and the grader are all Claude Opus 5.5, a same-family judge disclosed as such; a second-provider judge was declined for now (`docs/USER_DECISIONS.md` #16 and #23).
The grader is not validated against human grades (`docs/live_runs/QUALITY_COMPARISON.md` "Caveats").
There is no answer key for the lab's own sample document, so the agent's verdict on it is not scored (`docs/USER_DECISIONS.md` #35).
The planted flaws come from three synthetic documents written for this project, and the two held-out items have not been run (`docs/ARCHITECTURE.md` §9, `docs/SEALING.md` §6 rule 3, `docs/BUDGET.md` §6 line A-4).
The 132-run Tier A study, which would give the first statistical results, is costed but not approved or run (`docs/BUDGET.md` §6).
