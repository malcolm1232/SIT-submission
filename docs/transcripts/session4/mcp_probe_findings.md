# Session 4: MCP probe findings worker (2026-10-03)

Worker: one Opus worker for the planner, worktree `SIT-wt/probe2`, branch `s4/probe2`, started from `8fd8bea` (the tip of `origin/claude/happy-darwin-d0bl94`).
Deliverable: prove the owner's probe results hold no secret, write the findings note, fix the tool configuration the probe settles, record decision #35, and push.
Nothing was sent to the SIT MCP hosts by this worker: no second probe and no agent run with tools.

## Commits

1. `f73cb80`: the redacted probe results, `research/robustness/mcp_probe_results.redacted.json`.
2. `cbe922b`: the findings note, `research/robustness/mcp_probe_findings.md`.
3. `4ab6f0e`: `config/tools.yaml` `auth_header: Authorization` (sent as `Bearer <key>`), the browser and document-intelligence comments, the runbook §4.1 listing, a runbook §1 warm-up item, and the tests.
4. `640cfb5`: `docs/HANDOFF.md` owner tasks 1 (done) and 3 (superseded), `docs/USER_DECISIONS.md` #35, `eval/EVAL_PLAN.md` note under §1, `eval/prereg.yaml` and `eval/prereg_deviations.md` entry 12.

## Secret proof

Counts only, on the raw `mcp_probe_results.json`: 64-character `[A-Za-z0-9_-]` tokens 0, 40 or more 0, `Bearer` with a value 0, `api_key=` with a value 0, `sk-` 0, e-mail 0, home paths or user name 0, `Bearer%20` 0.
The 13 bare `Bearer` and 2 `x-api-key` hits are variant labels and the servers' `WWW-Authenticate` challenge, inspected by field path and length only.
The probe's redaction covers the raw key and its `quote` and `quote_plus` forms.
Four server-issued `mcp-session-id` headers (32 hex each) were found and replaced in the committed copy; all counts on the committed copy are 0.
The raw name stays gitignored (`.gitignore` line 7, commit `b730cab`, fresh-eyes audit N4), per the planner's ruling; the reviewed copy is committed under the `.redacted.json` name.

## What the probe contradicted or settled, and what changed

- Auth header: `X-API-Key` (unverified, audit U1) was wrong; `Authorization: Bearer <key>` worked on all four servers and no-auth got 401. Config, runbook listing and tests changed; a new unit test checks the gateway builds exactly `{"Authorization": "Bearer <value>"}` from `SIT_MCP_API_KEY`, and the old value fails three tests (mutation check).
- Document intelligence: the console summary said it accepted a plain-text sample; the JSON shows `processing_status: "rejected"` ("only file:// and https:// are accepted") with `is_error: false`. The lab brief's "rejects all inputs" is neither confirmed nor refuted, so the server stays disabled, with the comment updated to cite the probe.
- Browser: the server states one global browser session for all callers and no domain allowlist, which answers fresh-eyes N15 against enabling it; it stays disabled.
- Cold starts: 29.3 s to 70.1 s against the 90 s assumed in robustness INF-01, inside the 150 s allowance; warm 0.04 s. The runbook §1 now says to warm all four servers before the slot, since preflight warms only enabled ones.
- Tool names and schemas: the agent hardcodes none; `fetch_url` takes a `urls` array, which the URL policy already polices element by element (now pinned by a test).

## Gates (exit codes)

`ruff check agent harness tests` 0; `pytest -q` 0 (1558 passed); `sit-review selftest` 0; `make smoke` 0 (238 passed); `scripts/leakage_grep.py` 0; `spec/validate_examples.py` (default mode, blind not read) 0.

## Not verified

- Whether `read_document` reads any real `https://` document.
- The result shapes of `fetch_url` and the seven research tools (no sample call was made on them).
- The containers' idle timeout before they scale back to zero.
- An agent run with tools against the real servers using the new header (a later, separate step).

## Merge note

Decisions #32 to #34 live on local branch `s4/budget` (`517c03e`), not on this line; #35 is appended in its own section, and `eval/EVAL_PLAN.md` is also changed on `s4/budget`, so merging that branch may need a small hand merge at the end of `docs/USER_DECISIONS.md`.
