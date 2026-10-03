# Limitations, assumptions and known constraints

Date: 3 October 2026.
This file answers lab §5.3 "any assumptions, limitations or known constraints".
Each item says what the agent or its evaluation cannot claim, and names the file where it is recorded or measured.

## The agent

### Evidence and input

When the SIT MCP servers are down, unreachable or revoked mid-run, the review is document-only, and the report discloses it as a degradation (`docs/ARCHITECTURE.md` §5, `docs/USER_DECISIONS.md` #13).
On the first with-tools run on the lab's document every web search failed on a closed MCP session, so that review rests on the document and one scholarly search (`docs/live_runs/sit_sample_tools_1/MEASUREMENT.md` "Tools").
The agent does not see images in a PDF: the default Claude Code backend accepts text only, so figures, diagrams and tables drawn as images are invisible to the model, and the report says so as `DEG-001` (`docs/live_runs/sit_sample_tools_1/MEASUREMENT.md` "Disclosed limitations").
The four assess shards start at about 2 s and research at about 126 s, so no shard sees external evidence; only refine and the verdict call can apply it, a trade accepted for the time slot (`docs/USER_DECISIONS.md` #37).
The search tool's `fetch_top_n` and the research server's content retrieval fetch pages on the server side, where the agent's URL policy cannot see them, and this is still an open decision (`research/robustness/mcp_probe_findings.md` "For a follow-up worker").

### Tools that are off

The document-intelligence server is disabled because its only probed call was rejected and no `https://` document has ever been read through it (`config/tools.yaml`, `research/robustness/mcp_probe_findings.md`).
The browser-automation server is disabled because it keeps one browser session shared by every caller and has no domain allowlist (`config/tools.yaml`, `research/robustness/mcp_probe_findings.md`).

### Time and cost

The 540 s deadline of the demo profile is a project assumption, because the lab brief states no time limit for the live run; it is a configurable safety net, not a product limit (`docs/USER_DECISIONS.md` #34, `config/profiles/demo.yaml`).
Every cost in this repository is the Claude Code CLI's estimate, not a billed amount (`docs/BUDGET.md` basis note, `docs/live_runs/QUALITY_COMPARISON.md` "Caveats").
A model call cut by a limit is logged with unknown usage, so the cost of such a run is a lower bound and is labelled as one (`docs/USER_DECISIONS.md` #28, `docs/ARCHITECTURE.md` §6).
The cost with research on was measured once, on a run whose web searches all failed, so the cost of a run with working search is not measured (`docs/live_runs/sit_sample_tools_1/MEASUREMENT.md`, `docs/BUDGET.md` §1.1).

### Robustness fixes not yet seen live

The MCP session fix (reopen a closed session, retry once, reopen a session idle over 60 s) passes offline tests but has not been run against the live servers (`docs/HANDOFF.md` "State on 2026-10-03 (final hub of session 4)", `docs/USER_DECISIONS.md` #38).
The real idle timeout of the SIT servers is not known, so the 60 s reopen threshold is a guess from one run (`config/tools.yaml` `session_idle_reopen_s`).
32 of the 88 robustness scenarios are blocked offline as laptop-only or static and have not been run (`tests/robustness/results/robustness_summary.txt`).

### Re-assessment of an updated document

The re-assessment path (`--previous`) has been run live once, document-only, on the synthetic payments v1 and v2 pair, and never on the lab's document or with tools (`docs/live_runs/reassess_payments_v2_1/MEASUREMENT.md`).
That run was not graded against the answer key, so its resolved and still-open classification is unscored (`docs/live_runs/reassess_payments_v2_1/MEASUREMENT.md` "Not verified").
Nothing requires every prior finding to be classified, so a reader cannot tell a fixed prior finding from one that was not re-examined; three were left out in that run (`docs/live_runs/reassess_payments_v2_1/MEASUREMENT.md` "Prior findings not accounted for").
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
